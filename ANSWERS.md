# Architecture Review Answers

## A. Django Admin Performance with 500,000+ Rows

I would first use Django Silk or database query logging to find where the page
spends its time. Since the primary key is already indexed, I would check these
three areas next:

1. Related-object queries: If `list_display` methods access a foreign-key
   object for every row, Django may issue a separate query for each one. In
   the `ModelAdmin`, I would set `list_select_related` for the foreign keys
   shown in the list. For many-to-many or reverse relationships, I would use
   `prefetch_related` where it fits. I would also check custom display methods
   for repeated database lookups.
2. Counting and pagination: Django Admin may run an exact count to show
   the total number of matching rows. Counting a large filtered table can
   take time. If the full count is not needed, I would set
   `ModelAdmin.show_full_result_count = False` and choose a sensible
   `list_per_page` value. If the normal paginator count is still too slow, I
   would use a custom paginator that avoids the exact count. Staff should know
   that the displayed total may then be approximate or unavailable.
3. Search and filters: Broad searches or filters on unindexed fields can
   make the database scan many rows. I would review `search_fields` and
   `list_filter`, remove fields the team does not need, and add indexes only
   for fields supported by real query plans and usage patterns. I would avoid
   expensive substring searches across large text fields.

I would also keep `list_display` focused on information staff actually need.
After each change, I would test with representative data and compare query
counts, query plans, response time, and database load. I would not add indexes
or disable counts without first checking which operation is causing the delay.

## B. Offset Pagination vs. Cursor Pagination

Offset pagination uses a page number or an offset, such as `LIMIT 50 OFFSET
5000`. It is easy to understand and lets users jump to a particular page.
That can be useful in an admin screen. The cost is that the database may have
to scan or skip many rows before returning results, so deep pages can become
slower as the data grows.

Changes to the data can also shift offset pages. For example, if new records
are inserted before a user's current page the next request may repeat records
or skip some. This is especially noticeable in a mobile app's infinite scroll,
where users expect each page to continue from the last one.

Cursor pagination instead uses the last record's position as the starting
point for the next page. I would use a stable ordering such as
`(created_at, id)` where `id` breaks ties and include both values in the
cursor. With a matching index, the database can seek to records after that
position rather than skipping all earlier rows. New records before the cursor
are less likely to shift the next page. Deletions or changes to ordering
fields can still affect results, so cursor pagination is not a snapshot of
the data.

Cursor pagination works well for large, frequently updated feeds and mobile
infinite scroll, but it does not naturally support jumping to an arbitrary
page number. Offset pagination is reasonable for smaller lists where direct
page navigation matters. I would choose based on how people navigate the
results, then test the query plan and performance with realistic data and
indexes.
