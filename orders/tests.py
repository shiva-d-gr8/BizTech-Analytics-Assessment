
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import Customer, Order, OrderItem


class OrderSummaryTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Test Customer",
            email="customer@example.com",
        )
        self.order = Order.objects.create(
            customer=self.customer,
            status="completed",
        )
        OrderItem.objects.create(
            order=self.order,
            product_name="Keyboard",
            quantity=2,
            unit_price=Decimal("50.00"),
        )
        OrderItem.objects.create(
            order=self.order,
            product_name="Mouse",
            quantity=1,
            unit_price=Decimal("25.00"),
        )

    def test_summary_returns_order_and_customer(self):
        response = self.client.get(reverse("order_summary"))

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data["orders"]), 1)
        self.assertEqual(data["orders"][0]["customer"], "Test Customer")
        self.assertEqual(data["orders"][0]["status"], "completed")

    def test_home_page_returns_links_to_app_sections(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/api/orders/summary/")
        self.assertContains(response, "/admin/")

    def test_summary_calculates_item_count_and_total(self):
        response = self.client.get(reverse("order_summary"))

        self.assertEqual(response.status_code, 200)

        order = response.json()["orders"][0]
        self.assertEqual(order["item_count"], 2)
        self.assertEqual(Decimal(order["total"]), Decimal("125"))

    def test_summary_uses_a_bounded_number_of_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        # Capture the SQL queries made by the endpoint request.
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(reverse("order_summary"))

        self.assertEqual(response.status_code, 200)

        # Exclude Silk's profiling queries and count SELECTs on the orders table.
        order_queries = [
            query["sql"]
            for query in captured.captured_queries
            if '"orders_order"' in query["sql"]
            and query["sql"].lstrip().upper().startswith("SELECT")
        ]

        self.assertEqual(
            len(order_queries),
            1,
            "Expected one optimized order-summary SELECT query",
        )

    def test_unoptimized_related_access_reproduces_n_plus_one_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for index in range(199):
            order = Order.objects.create(customer=self.customer)
            item_count = 3 if index < 100 else 2
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        product_name=f"Test item {item_index}",
                        quantity=1,
                        unit_price=Decimal("10.00"),
                    )
                    for item_index in range(item_count)
                ]
            )

        with CaptureQueriesContext(connection) as captured:
            results = [
                (order.customer.name, order.items.count())
                for order in Order.objects.order_by("pk")
            ]

        self.assertEqual(len(results), 200)
        select_queries = [
            query["sql"]
            for query in captured.captured_queries
            if query["sql"].lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(
            len(select_queries),
            401,
            "Expected one order query plus customer and item queries per order",
        )
