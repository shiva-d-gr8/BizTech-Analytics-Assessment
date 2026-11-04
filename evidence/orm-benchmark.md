# ORM Performance Investigation

## Investigation log

1. Reproduce the reported behavior through `GET /api/orders/summary/` and
   inspect the URL route and view before changing database settings.
2. Trace each relation access in a deliberately unoptimized queryset loop.
   Reading `order.customer.name` lazily loads the customer, while calling
   `order.items.count()` issues a separate count query for each order.
3. Verify that query shape with 200 orders. The regression test constructs
   that dataset and asserts 401 SELECTs: one order query and two related-object
   queries for each order.
4. Replace per-order relation reads and calculations with
   `select_related("customer")` and database-side aggregates, then measure the
   endpoint again. The existing query-count test asserts one order-summary
   SELECT for the optimized view.

The local reproduction demonstrates an ORM N+1 query problem. This repository
does not include production query logs or deployment telemetry, so the
reproduction supports this diagnosis but cannot establish what changed in the
production deployment described in the scenario.

## Environment

- Framework: Django 6.1.2
- Database: SQLite for local development
- Dataset: 200 orders, 500 order items, and 1 customer
- Profiling tools: Django Silk 5.6.0 and Django query logging

## Results

| Measurement | Baseline ORM | Optimized ORM |
|---|---:|---:|
| Orders processed | 200 | 200 |
| SQL query count | 401 | 1 |
| Query-count reduction | — | 99.75% |

## Baseline

The regression test models the baseline by loading the orders and then
accessing each order's customer and item count in a loop. This results in one
initial query, followed by separate customer and item-count queries for every
order: 401 SELECTs in total for 200 orders.

## Optimization

The optimized query uses `select_related("customer")` and database-side
aggregation with `Count`, `Sum`, and `ExpressionWrapper`. It returned all
200 orders and calculated the first order's item count as 2 and total as 125
with a single SQL query.

## Limitations

These figures are local SQLite query counts, not production latency
measurements. The test does not reproduce the reported increase from 80 ms to
30 seconds, and no claim is made about elapsed-time improvements. SQLite
timings should not be treated as representative of PostgreSQL performance in
production.

## Profiling evidence

Django Silk recorded the optimized `GET /api/orders/summary/` request with
200 orders. The screenshot in this directory shows the successful response
and its single database query. The test suite verifies the unoptimized
401-query baseline; a separate Silk screenshot of that baseline is not
included.
