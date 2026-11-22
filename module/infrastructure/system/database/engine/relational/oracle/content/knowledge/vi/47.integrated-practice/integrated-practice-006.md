# Test

A query filters by customer_id with a bind variable.

~~~sql
SELECT * FROM orders WHERE customer_id = :customer_id;
~~~

