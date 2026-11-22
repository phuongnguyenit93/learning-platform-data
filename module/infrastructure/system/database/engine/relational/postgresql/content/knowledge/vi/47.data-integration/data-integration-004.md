# Đẩy điều kiện, JOIN và tổng hợp sang máy chủ từ xa trong PostgreSQL

Khi PostgreSQL truy vấn dữ liệu qua foreign table, câu SQL được gửi từ database cục bộ tới máy chủ từ xa có thể được thực hiện theo hai cách rất khác nhau. Máy chủ cục bộ có thể yêu cầu nhiều rows từ xa rồi tự lọc, JOIN và GROUP BY; hoặc nó có thể gửi một phần lớn công việc tới máy chủ từ xa, chỉ nhận các rows hoặc kết quả tổng hợp cuối cùng. Cách thứ hai được gọi là **query pushdown** (đẩy xử lý truy vấn xuống máy chủ từ xa).

Pushdown thường giảm dữ liệu truyền qua mạng, giảm số lần trao đổi giữa hai máy chủ và tận dụng indexes, CPU, statistics cùng tài nguyên của máy chủ đang sở hữu dữ liệu. Nhưng PostgreSQL chỉ đẩy một biểu thức khi foreign-data wrapper (FDW) xác định rằng biểu thức đó có thể được thực hiện an toàn và giữ nguyên ngữ nghĩa. Với **postgres_fdw**, điều kiện WHERE, JOIN giữa các foreign tables cùng server, aggregate, ORDER BY và LIMIT có thể được đẩy xuống trong các trường hợp phù hợp. Planner vẫn có quyền chọn một kế hoạch khác nếu ước lượng chi phí cho thấy cách đó tốt hơn.

Vì vậy, không thể nhìn vào câu SQL rồi mặc định rằng toàn bộ câu lệnh đã chạy ở remote server. Cần đọc execution plan bằng EXPLAIN VERBOSE, đặc biệt là phần Remote SQL, để biết chính xác điều gì được gửi đi và điều gì vẫn chạy tại local server.

Bài học tập trung vào predicate pushdown, join pushdown và aggregate pushdown với postgres_fdw; đồng thời giải thích điều kiện shippability, user mappings, kiểu dữ liệu/collation, cost estimates, transaction semantics, cách quan sát và xử lý các trường hợp không push được.

~~~text
                  Local PostgreSQL
                         |
                    SQL query
                         |
                         v
                  Query planner
                         |
             +-----------+-----------+
             |                       |
             v                       v
      Shippable expressions     Local-only work
             |                       |
             v                       v
       Remote SQL request       Local Filter/Join/
             |                  Aggregate/Sort
             v                       ^
        Remote server                |
      WHERE / JOIN / GROUP BY        |
             |                       |
             v                       |
       Reduced result set -----------+
                         |
                         v
                   Final result
~~~

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Tích hợp dữ liệu**, với đề tài **“Đẩy điều kiện, JOIN và tổng hợp sang máy chủ từ xa”**.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích query pushdown và lý do cần giảm dữ liệu truyền giữa các PostgreSQL servers.
2. Phân biệt xử lý tại local server với xử lý tại remote server.
3. Mô tả vai trò của FDW và postgres_fdw.
4. Thiết lập foreign server, user mapping và foreign tables để thực hành.
5. Nhận diện projection pushdown và predicate pushdown.
6. Giải thích điều kiện WHERE nào có thể được gửi tới remote server.
7. Hiểu khái niệm shippable expression và yêu cầu IMMUTABLE.
8. Cấu hình extensions option để cho phép một số extension functions/operators được ship.
9. Giải thích join pushdown và điều kiện các foreign tables phải cùng foreign server/user mapping.
10. Nhận biết trường hợp planner quyết định fetch từng bảng riêng thay vì gửi JOIN.
11. Hiểu aggregate pushdown, GROUP BY, HAVING và các giới hạn theo biểu thức/FDW version.
12. Dùng EXPLAIN VERBOSE để xem Remote SQL.
13. Phân biệt Remote SQL với Filter, Hash Join, HashAggregate hoặc Sort ở local plan.
14. Đọc chi phí Foreign Scan và hiểu use_remote_estimate.
15. Cập nhật statistics của foreign tables bằng ANALYZE.
16. Điều chỉnh fetch_size và hiểu giới hạn của nó.
17. Phân biệt fetch_size với batch_size.
18. Hiểu tác động của data types, collations và khác biệt version lên pushdown.
19. Giải thích user mapping ảnh hưởng đến khả năng JOIN pushdown và quyền remote như thế nào.
20. Theo dõi query tại cả local server và remote server.
21. Phân biệt pushdown có lợi với pushdown gây quá tải remote server.
22. Thiết kế query để tăng khả năng pushdown mà vẫn giữ đúng semantics.
23. Điều tra query bị lọc/tổng hợp cục bộ ngoài dự kiến.
24. Xây dựng checklist, runbook và lab để đo hiệu quả pushdown.

**Phạm vi:** Trọng tâm là postgres_fdw giữa các PostgreSQL servers. Các FDW khác có thể hỗ trợ tập pushdown khác nhau. Khả năng cụ thể phụ thuộc PostgreSQL version, remote server version, extension, schema, user mapping và cost estimates. Luôn kiểm tra execution plan thực tế trên đúng môi trường.

---

## 2. Query pushdown là gì?

Query pushdown là việc FDW chuyển một phần phép toán của query sang hệ thống từ xa để hệ thống đó thực hiện. Local PostgreSQL vẫn điều phối query và có thể tiếp tục xử lý phần còn lại.

### 2.1. Không pushdown

Giả sử remote table có 10 triệu rows, nhưng ứng dụng chỉ cần 500 rows thỏa điều kiện ngày và trạng thái.

Nếu điều kiện không được push xuống:

1. Local server yêu cầu rows từ foreign table.
2. Remote server trả về một lượng dữ liệu lớn.
3. Local server thực hiện Filter.
4. Local server giữ lại 500 rows.

Phần dữ liệu không cần thiết đã đi qua network.

### 2.2. Có predicate pushdown

Nếu WHERE được ship:

1. Local server gửi câu query có điều kiện tới remote server.
2. Remote server dùng indexes hoặc scan phù hợp để lọc.
3. Remote server chỉ trả các rows thỏa điều kiện.
4. Local server xử lý kết quả nhỏ hơn.

### 2.3. Có JOIN pushdown

Nếu hai foreign tables ở cùng remote server và cùng user mapping, FDW có thể gửi JOIN để remote server thực hiện.

Thay vì tải cả hai bảng về local rồi JOIN, local server nhận kết quả JOIN đã được lọc.

### 2.4. Có aggregate pushdown

Nếu GROUP BY và aggregate expressions có thể ship, remote server có thể trả một row cho mỗi group thay vì gửi toàn bộ rows thô về local.

Ví dụ, remote có 20 triệu orders nhưng chỉ cần tổng doanh thu theo tháng và khu vực. Nếu aggregate được push, lượng dữ liệu trả về có thể chỉ còn vài trăm rows.

### 2.5. Pushdown không phải một switch toàn cục

Một query có thể được push một phần:
- WHERE được ship, nhưng một điều kiện khác chạy local.
- JOIN được ship, nhưng JOIN với local table chạy local.
- Aggregate được ship, nhưng một expression trong SELECT chạy local.
- ORDER BY hoặc LIMIT được ship trong một số plan, nhưng phần khác vẫn local.

Cần đọc từng node trong plan.

---

## 3. FDW và postgres_fdw

Foreign Data Wrapper là lớp tích hợp cho phép PostgreSQL truy cập dữ liệu nằm ngoài database hiện tại bằng các foreign tables.

### 3.1. Các thành phần

| Thành phần | Vai trò |
| --- | --- |
| Extension | Cài FDW implementation |
| Foreign server | Mô tả nguồn dữ liệu từ xa và connection options |
| User mapping | Ánh xạ local role sang remote credentials/identity |
| Foreign table | Schema cục bộ đại diện cho remote table/view |
| FDW planner hooks | Quyết định expressions và operations nào có thể push |
| FDW executor | Thực hiện remote request và chuyển rows về local |

### 3.2. postgres_fdw

postgres_fdw là FDW đi kèm PostgreSQL contrib modules, dùng để truy cập dữ liệu ở PostgreSQL server khác. Nó cung cấp SQL syntax tự nhiên qua foreign tables và có thể tối ưu WHERE, JOIN cùng một số upper-level operations.

### 3.3. Foreign table không chứa bản sao dữ liệu

Foreign table là metadata ở local server. Rows được đọc từ remote server khi query chạy, trừ khi dữ liệu được materialize/copy riêng.

### 3.4. Pushdown do FDW quyết định

PostgreSQL planner hỏi FDW về những paths có thể thực hiện ở remote. Mỗi FDW có khả năng khác nhau. Một FDW truy cập PostgreSQL khác có thể push nhiều loại expressions hơn một FDW truy cập CSV, REST API hoặc hệ thống NoSQL.

### 3.5. Không đồng nghĩa với distributed query engine đầy đủ

postgres_fdw cho phép kết hợp dữ liệu remote và local, nhưng không tự biến nhiều PostgreSQL servers thành một cluster phân tán có global optimizer, distributed transaction 2PC hoặc global statistics hoàn chỉnh.

---

## 4. Chuẩn bị postgres_fdw

Các ví dụ giả định có một local PostgreSQL server và một remote PostgreSQL server. Thay hostname, database, roles và schema bằng thông tin của môi trường lab.

### 4.1. Cài extension ở local server

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
~~~

postgres_fdw phải được cài trong database local cần tạo foreign server.

### 4.2. Tạo foreign server

~~~sql
CREATE SERVER sales_remote
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'remote-db.example.test',
    port '5432',
    dbname 'sales'
);
~~~

Foreign server mô tả remote endpoint. Không đặt username/password ở đây; credentials thuộc user mapping hoặc cơ chế xác thực phù hợp.

### 4.3. Tạo user mapping

~~~sql
CREATE USER MAPPING FOR reporting_user
SERVER sales_remote
OPTIONS (
    user 'sales_reader',
    password 'replace-with-secret-reference'
);
~~~

Ví dụ dùng placeholder. Không ghi password thật vào migration repository, ticket hoặc logs. Trong production, dùng secret management và authentication policy được phê duyệt.

### 4.4. Tạo schema local

~~~sql
CREATE SCHEMA remote_sales;
~~~

Schema này chỉ là namespace local để chứa foreign table definitions.

### 4.5. Import foreign schema

~~~sql
IMPORT FOREIGN SCHEMA public
LIMIT TO (orders, customers)
FROM SERVER sales_remote
INTO remote_sales;
~~~

Lệnh tạo foreign table definitions dựa trên remote objects. Có thể dùng CREATE FOREIGN TABLE thủ công nếu cần kiểm soát tên, columns hoặc options.

### 4.6. Kiểm tra foreign tables

~~~sql
SELECT
    foreign_table_schema,
    foreign_table_name,
    foreign_server_name
FROM information_schema.foreign_tables
ORDER BY foreign_table_schema, foreign_table_name;
~~~

### 4.7. Đối chiếu metadata

Kiểu dữ liệu, tên columns và collation của foreign table nên khớp với remote table. Khai báo sai có thể gây conversion bất ngờ hoặc làm điều kiện được đánh giá khác nhau.

### 4.8. Quyền truy cập

Local role cần quyền sử dụng foreign server, schema và foreign tables. Remote mapped role cần quyền SELECT trên remote objects. Pushdown không bỏ qua quyền của remote user.

---

## 5. Projection pushdown: chỉ lấy columns cần thiết

Projection pushdown là việc FDW chỉ yêu cầu những columns mà query thực sự cần.

### 5.1. Ví dụ lấy toàn bộ columns

~~~sql
SELECT *
FROM remote_sales.orders;
~~~

Query yêu cầu mọi columns. Nếu bảng có payload lớn hoặc nhiều columns ít dùng, dữ liệu truyền có thể nhiều.

### 5.2. Chỉ chọn columns cần thiết

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM remote_sales.orders;
~~~

FDW có thể chỉ lấy các columns cần cho query và những expressions phía local.

### 5.3. Projection kết hợp predicate

~~~sql
SELECT
    order_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid'
  AND created_at >= DATE '2026-01-01';
~~~

Nếu WHERE được ship, remote server vừa lọc vừa chỉ trả columns cần thiết.

### 5.4. Lợi ích

- Giảm bytes truyền qua network.
- Giảm serialization/deserialization.
- Giảm memory và tuple processing tại local.
- Có thể tận dụng index-only hoặc index scans nếu remote plan phù hợp.

### 5.5. SELECT * trong view/reporting

Một view dùng SELECT * có thể vô tình kéo thêm columns khi schema remote thay đổi. Với query tích hợp, nên chọn columns cụ thể để giữ payload ổn định.

---

## 6. Predicate pushdown với WHERE

Predicate pushdown là việc gửi các điều kiện lọc tới remote server.

### 6.1. Điều kiện built-in

~~~sql
SELECT
    order_id,
    total_amount
FROM remote_sales.orders
WHERE customer_id = 42
  AND total_amount > 1000;
~~~

Các kiểu dữ liệu và operators built-in thường có thể được ship nếu semantics tương thích.

### 6.2. Kết hợp nhiều predicates

~~~sql
SELECT
    order_id,
    customer_id,
    created_at
FROM remote_sales.orders
WHERE status IN ('paid', 'shipped')
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-02-01 00:00:00';
~~~

Remote server có thể áp dụng các conditions trước khi gửi kết quả.

### 6.3. AND và OR

Một biểu thức boolean có thể được ship nếu toàn bộ các thành phần cần thiết đều shippable. Nếu một phần không ship được, FDW có thể chỉ ship các clauses an toàn và giữ phần còn lại ở local, tùy cách planner tách expression.

### 6.4. Điều kiện trên join keys

Điều kiện WHERE lọc một foreign table trước JOIN có thể giảm lượng rows cần join. Nếu JOIN cũng được ship, remote server có thể kết hợp filter và join trong cùng remote query.

### 6.5. Range predicates

Các điều kiện khoảng thời gian hoặc số thường có ích khi remote table có index phù hợp:

~~~sql
SELECT order_id, created_at
FROM remote_sales.orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+00';
~~~

Dùng half-open interval giúp tránh lỗi ở ranh giới cuối kỳ.

### 6.6. Predicate pushdown không tự tạo index

FDW chỉ gửi điều kiện. Remote server vẫn cần index hoặc execution plan phù hợp. Nếu remote server phải sequential scan toàn bảng, network có thể giảm nhưng remote CPU/I/O vẫn lớn.

---

## 7. Shippability: điều kiện để expression được gửi đi

Shippability là khả năng một expression có thể được thực hiện an toàn ở remote server với cùng semantics mà local query yêu cầu.

### 7.1. Built-in types, operators và functions

Mặc định postgres_fdw chỉ xem các WHERE clauses dùng built-in types, operators và functions là candidates để ship. Điều này giảm rủi ro local và remote hiểu cùng tên function/operator theo cách khác nhau.

### 7.2. IMMUTABLE

Functions và operators trong clauses được ship phải đáp ứng yêu cầu IMMUTABLE. Một function IMMUTABLE được PostgreSQL cam kết trả cùng kết quả cho cùng arguments, không phụ thuộc thời gian, session settings hoặc database state.

### 7.3. STABLE và VOLATILE

Các functions có volatility STABLE hoặc VOLATILE không đáp ứng điều kiện IMMUTABLE để ship theo cơ chế này. Ví dụ, hàm phụ thuộc thời gian hiện tại hoặc random value có thể cho kết quả khác nếu thực hiện ở hai server hoặc hai thời điểm khác nhau.

### 7.4. User-defined function

~~~sql
CREATE FUNCTION public.normalize_code(value TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT upper(trim(value));
$$;
~~~

Dù function được khai báo IMMUTABLE, nó không tự động được ship chỉ vì có thuộc tính này. Mặc định function không thuộc built-in set. Cần extension shippability configuration hoặc giữ expression ở local.

### 7.5. Không khai báo IMMUTABLE chỉ để tăng tốc

Volatility declaration là cam kết về semantics. Khai báo sai có thể làm query sai do constant folding, caching và pushdown. Không thay volatility của function nếu function phụ thuộc table, config, timezone hoặc external state.

### 7.6. Expressions hỗn hợp

Một WHERE clause có thể chứa:
- Remote column.
- Built-in operator.
- Built-in function.
- Local parameter.
- User-defined function.
- Collation-sensitive operation.

FDW cần đánh giá toàn expression và có thể chỉ ship phần an toàn.

### 7.7. Constants và parameters

Constants có thể được biểu diễn trong remote SQL. Các values đến từ local expressions hoặc parameters cần được xem trong context của plan. Không tự giả định mọi correlated subquery hoặc local parameter đều được chuyển thành remote predicate.

---

## 8. Cho phép extension functions được ship

postgres_fdw có server option extensions để chỉ định các PostgreSQL extensions được cài ở cả local và remote với versions tương thích.

### 8.1. Cấu hình

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD extensions 'my_immutable_extension');
~~~

Nếu đã có option, dùng SET thay vì ADD. Option là danh sách tên extensions, không phải danh sách function names.

### 8.2. Điều kiện

- Extension phải tồn tại ở cả local và remote.
- Versions phải tương thích.
- Functions/operators được ship phải IMMUTABLE.
- Semantics phải giống nhau giữa hai servers.

### 8.3. Trách nhiệm của operator

Khai báo extension trong extensions option là cam kết rằng extension đó tồn tại và hoạt động tương đương trên cả hai phía. PostgreSQL không tự chứng minh hai bản extension có cùng behavior.

### 8.4. Không liệt kê toàn bộ extensions

Chỉ thêm extension thật sự cần thiết và đã xác minh. Không mở rộng shippability cho extension có behavior phụ thuộc external state hoặc version khác nhau.

### 8.5. Kiểm tra function volatility

~~~sql
SELECT
    n.nspname,
    p.proname,
    p.provolatile,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.proname = 'normalize_code';
~~~

provolatile có các giá trị biểu thị immutable, stable và volatile. Kiểm tra catalog ở cả local và remote nếu function được ship.

### 8.6. Khi không thể đảm bảo tương đương

Để function chạy local hoặc chuẩn hóa dữ liệu trước khi đưa vào foreign query. Đừng đánh đổi tính đúng đắn để giảm network traffic.

---

## 9. Collation và data type compatibility

Predicate có thể được ship nhưng cho kết quả khác nếu local và remote không hiểu type/collation giống nhau.

### 9.1. Khai báo đúng data types

Foreign table nên khai báo columns với cùng data types như remote table. Tránh ánh xạ remote numeric sang text hoặc timestamp sang type khác nếu không có lý do rõ ràng.

### 9.2. Collation của text

So sánh và sắp xếp text phụ thuộc collation. Nếu local và remote dùng provider/locale khác nhau, một điều kiện hoặc JOIN trên text có thể cho semantics khác.

### 9.3. Import collations

IMPORT FOREIGN SCHEMA có option import_collate. Tắt import collation có thể tránh lỗi tên collation không tồn tại, nhưng có nguy cơ nghiêm trọng làm collation local không khớp với dữ liệu remote.

### 9.4. Kiểm tra collation

~~~sql
SELECT
    n.nspname,
    c.collname,
    c.collprovider,
    c.collcollate,
    c.collctype
FROM pg_catalog.pg_collation AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.collnamespace
ORDER BY n.nspname, c.collname;
~~~

So sánh kết quả trên hai servers và xác nhận các columns/indexes dùng collation tương ứng.

### 9.5. Timestamp và timezone

postgres_fdw thiết lập một số session parameters cho remote sessions, gồm TimeZone UTC, DateStyle ISO và IntervalStyle postgres. Điều này giúp ổn định biểu diễn, nhưng ứng dụng vẫn phải thống nhất timezone semantics.

### 9.6. Numeric precision

Kiểm tra numeric precision/scale, floating-point behavior và casts. Local/remote conversions có thể ảnh hưởng predicates và grouping.

### 9.7. Cross-version built-ins

postgres_fdw có thể coi built-in immutable functions/operators là shippable. Nếu remote PostgreSQL cũ không có function mới được local server biết tới, remote query có thể báo function does not exist. Cần kiểm tra version compatibility hoặc viết query sao cho expression đó chạy local.

---

## 10. JOIN pushdown

JOIN pushdown cho phép remote server kết hợp dữ liệu từ nhiều foreign tables trước khi trả rows về local.

### 10.1. Hai foreign tables trên cùng remote server

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    o.total_amount
FROM remote_sales.orders AS o
JOIN remote_sales.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid';
~~~

Nếu planner chọn join pushdown, Remote SQL sẽ chứa JOIN và WHERE. Remote server có thể dùng indexes trên join keys và filter columns.

### 10.2. Điều kiện cùng foreign server

Các foreign tables tham gia join pushdown phải thuộc cùng foreign server object, tức cùng remote endpoint/database theo cấu hình đó.

### 10.3. Điều kiện user mapping

Các table references phải sử dụng cùng user mapping. Nếu chúng được truy cập bằng các remote identities khác nhau, postgres_fdw không thể đơn giản gửi một JOIN duy nhất dưới một remote identity.

### 10.4. Shippability của join clauses

Join expressions phải dùng types/operators/functions có thể ship. Điều kiện join chứa local-only functions hoặc semantics không tương thích có thể khiến join được thực hiện tại local.

### 10.5. Planner vẫn có thể không push JOIN

Ngay cả khi JOIN có thể ship, postgres_fdw có thể đánh giá rằng fetch từng bảng riêng sẽ hiệu quả hơn. Cost, cardinality, local joins và query shape ảnh hưởng quyết định.

### 10.6. JOIN giữa hai foreign servers khác nhau

~~~sql
SELECT *
FROM remote_sales.orders AS o
JOIN remote_hr.employees AS e
    ON e.employee_id = o.sales_rep_id;
~~~

Nếu hai tables thuộc các foreign servers khác nhau, không thể gửi một JOIN thông thường tới một remote server duy nhất. Local PostgreSQL thường phải lấy rows từ từng phía rồi join, trừ khi FDW/distributed system cụ thể cung cấp cơ chế khác.

### 10.7. JOIN giữa foreign table và local table

~~~sql
SELECT
    o.order_id,
    d.department_name
FROM remote_sales.orders AS o
JOIN public.department AS d
    ON d.department_id = o.department_id;
~~~

Remote server không có local table public.department. Local server phải thực hiện phần JOIN này. Predicate chỉ tham chiếu remote columns vẫn có thể được ship trước khi rows được chuyển về.

### 10.8. Filter trước join

Đặt điều kiện có ý nghĩa trên remote tables vào query để planner có cơ hội push xuống. Tuy nhiên, không rewrite query chỉ theo hình thức; cần giữ semantics và xác nhận bằng EXPLAIN.

### 10.9. Outer joins

LEFT/RIGHT/FULL JOIN có semantics về NULL extension. Một điều kiện đặt trong ON và một điều kiện đặt trong WHERE không tương đương trong mọi trường hợp. Không chuyển predicates giữa ON/WHERE chỉ để ép pushdown nếu điều đó thay đổi kết quả.

### 10.10. Lateral và correlated operations

LATERAL, correlated subqueries hoặc local parameters có thể tạo parameterized foreign scans. Khả năng pushdown phụ thuộc FDW và plan. Đọc Remote SQL và số lần Foreign Scan được thực hiện; không giả định một remote request duy nhất.

---

## 11. Aggregate pushdown: GROUP BY và hàm tổng hợp

Aggregate pushdown cho phép remote server tính kết quả tổng hợp trước khi trả dữ liệu về local.

### 11.1. Ví dụ GROUP BY

~~~sql
SELECT
    date_trunc('month', created_at) AS month,
    status,
    count(*) AS order_count,
    sum(total_amount) AS revenue
FROM remote_sales.orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY 1, 2
ORDER BY 1, 2;
~~~

Nếu expressions và aggregate calls shippable, remote server có thể thực hiện filter, grouping và aggregation. Local server chỉ nhận các group rows.

### 11.2. Aggregate functions

Các aggregate phổ biến như count, sum, min, max và avg thường có thể push khi function/operator/type tương ứng shippable và query shape được hỗ trợ.

### 11.3. GROUP BY expressions

Expressions trong GROUP BY phải có thể ship. Một grouping key chứa function local-only có thể ngăn aggregate pushdown hoặc khiến một phần xử lý diễn ra local.

### 11.4. HAVING

HAVING lọc các groups sau aggregation. Các điều kiện HAVING shippable có thể được gửi remote. Nếu một condition không ship được, planner có thể giữ condition ở local hoặc không push aggregate theo cấu trúc cần thiết.

### 11.5. FILTER trong aggregate

~~~sql
SELECT
    customer_id,
    count(*) AS all_orders,
    count(*) FILTER (WHERE status = 'paid') AS paid_orders,
    sum(total_amount) FILTER (WHERE status = 'paid') AS paid_revenue
FROM remote_sales.orders
GROUP BY customer_id;
~~~

FILTER expressions và aggregate implementation phải shippable. Hỗ trợ cụ thể phụ thuộc PostgreSQL/FDW version và query plan; kiểm tra Remote SQL.

### 11.6. DISTINCT trong aggregate

~~~sql
SELECT
    customer_id,
    count(DISTINCT product_id)
FROM remote_sales.order_items
GROUP BY customer_id;
~~~

DISTINCT trong aggregate có thể ảnh hưởng khả năng deparse/ship theo loại aggregate và FDW version. Không áp dụng một quy tắc chung cho mọi aggregate. Dùng EXPLAIN VERBOSE để xác nhận.

### 11.7. ORDER BY trong aggregate

~~~sql
SELECT
    customer_id,
    string_agg(product_name, ', ' ORDER BY product_name)
FROM remote_sales.order_items
GROUP BY customer_id;
~~~

Aggregate có ORDER BY cần remote sort semantics và sort operators tương thích. Đây là trường hợp phải xác minh thực tế, nhất là với collation hoặc custom type.

### 11.8. Grouping sets, ROLLUP và CUBE

Các grouping constructs nâng cao có thể không được pushdown bởi postgres_fdw trong các plan/version nhất định. Nếu không ship, local server có thể phải lấy rows rồi tổng hợp. Hãy kiểm tra plan thay vì giả định GROUP BY nào cũng được xử lý remote.

### 11.9. Aggregate không shippable

Một user-defined aggregate hoặc aggregate function không có mặt/không tương thích trên remote sẽ không thể được thực hiện an toàn ở remote. Nếu local cần tính, dữ liệu đầu vào có thể phải truyền về.

### 11.10. DISTINCT ở cấp query

SELECT DISTINCT không giống DISTINCT bên trong aggregate. Đừng suy luận khả năng pushdown của một loại DISTINCT từ loại còn lại.

### 11.11. Aggregate và JOIN cùng lúc

Một query có thể cần join foreign tables trước, rồi group. Nếu JOIN và aggregate đều push được, remote server có thể thực hiện toàn bộ pipeline. Nếu join không push được, aggregate cũng có thể bị kéo về local do input được tạo tại local.

### 11.12. Kiểm tra số rows sau aggregation

Lợi ích thường lớn nhất khi số groups nhỏ hơn nhiều so với số input rows. Nếu mỗi row tạo một group duy nhất, aggregate pushdown có thể không giảm đáng kể payload.

---

## 12. ORDER BY, LIMIT và OFFSET pushdown

Các upper-level operations như sorting và limiting cũng có thể được ship khi semantics tương đương và FDW hỗ trợ.

### 12.1. ORDER BY

~~~sql
SELECT order_id, created_at
FROM remote_sales.orders
WHERE status = 'paid'
ORDER BY created_at DESC;
~~~

Nếu ORDER BY được ship, remote server có thể dùng index hoặc sort trước khi gửi rows.

### 12.2. LIMIT

~~~sql
SELECT order_id, created_at
FROM remote_sales.orders
WHERE status = 'paid'
ORDER BY created_at DESC
LIMIT 100;
~~~

Nếu remote thực hiện LIMIT, chỉ 100 rows được chuyển về thay vì toàn bộ rows thỏa điều kiện.

### 12.3. OFFSET

~~~sql
SELECT order_id
FROM remote_sales.orders
ORDER BY order_id
LIMIT 100 OFFSET 500;
~~~

OFFSET có thể được push trong trường hợp phù hợp, nhưng pagination sâu vẫn có thể tốn công remote scan/sort. Keyset pagination thường có hiệu năng ổn định hơn khi có index phù hợp.

### 12.4. ORDER BY phải có semantics giống nhau

Collation, NULL ordering, data type và operator differences có thể làm remote order khác local order. FDW chỉ nên ship khi đảm bảo semantics an toàn.

### 12.5. LIMIT không thay thế filter

Nếu query không có điều kiện selective, LIMIT chỉ giới hạn số rows trả về; remote server vẫn có thể phải scan/sort nhiều rows để tìm top rows.

---

## 13. Query plan: EXPLAIN VERBOSE là công cụ quan trọng nhất

Không thể xác nhận pushdown chỉ từ câu SQL hoặc thời gian chạy. Hãy đọc plan.

### 13.1. EXPLAIN

~~~sql
EXPLAIN
SELECT
    order_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid';
~~~

EXPLAIN hiển thị plan local và cost estimates.

### 13.2. EXPLAIN VERBOSE

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    order_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid';
~~~

Với postgres_fdw, output Foreign Scan có thể hiển thị phần Remote SQL. Đây là câu SQL được gửi tới remote server.

### 13.3. Ví dụ plan có predicate pushdown

Output minh họa:

~~~text
Foreign Scan on remote_sales.orders
  Output: order_id, total_amount
  Remote SQL: SELECT order_id, total_amount
              FROM public.orders
              WHERE (status = 'paid'::text)
~~~

Điều kiện status được gửi remote. Tên bảng/schema và casts thực tế phụ thuộc foreign table mapping.

### 13.4. Ví dụ local Filter

~~~text
Foreign Scan on remote_sales.orders
  Output: order_id, status, total_amount
  Filter: (local_normalize(status) = 'paid'::text)
  Remote SQL: SELECT order_id, status, total_amount
              FROM public.orders
~~~

Trong ví dụ, local_normalize không được ship. Remote server gửi rows/columns cần thiết, local server thực hiện Filter.

### 13.5. Ví dụ JOIN pushdown

~~~text
Foreign Scan
  Remote SQL: SELECT o.order_id, c.customer_name
              FROM public.orders o
              JOIN public.customers c
                ON c.customer_id = o.customer_id
              WHERE (o.status = 'paid'::text)
~~~

Remote SQL chứa JOIN. Điều này cho thấy join được thực hiện ở remote.

### 13.6. Ví dụ aggregate pushdown

~~~text
Foreign Scan
  Remote SQL: SELECT status, count(*), sum(total_amount)
              FROM public.orders
              GROUP BY status
~~~

Nếu Aggregate node vẫn nằm ở local plan phía trên Foreign Scan, cần kiểm tra xem Remote SQL đã group hay local đang tiếp tục tổng hợp.

### 13.7. Local plan có thể có nhiều Foreign Scans

Một query có thể tạo nhiều Foreign Scan nodes. Đọc toàn plan để xác định join/aggregate nằm ở node nào và remote query được gửi bao nhiêu lần.

### 13.8. EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT
    status,
    count(*)
FROM remote_sales.orders
GROUP BY status;
~~~

EXPLAIN ANALYZE thực thi query thật. Chỉ dùng khi hiểu workload và tác động. Local BUFFERS không tự cung cấp toàn bộ remote buffer usage; cần quan sát thêm trên remote server.

### 13.9. EXPLAIN không phải bằng chứng remote query đã nhanh

Remote SQL được ship không đồng nghĩa remote plan tốt. Chạy EXPLAIN trên remote server với câu SQL tương ứng, kiểm tra indexes, rows, buffers, waits và query duration.

### 13.10. Lưu plan trước/sau

Khi tối ưu, lưu:
- SQL.
- EXPLAIN VERBOSE.
- EXPLAIN ANALYZE phù hợp.
- Remote SQL.
- Estimated/actual rows.
- Bytes transferred nếu có telemetry.
- Local/remote CPU và I/O.
- Thời gian end-to-end.

---

## 14. Cost estimation và lựa chọn pushdown

Planner chọn plan dựa trên ước lượng rows và costs. Pushdown có thể hợp lệ nhưng không được chọn nếu cost model đánh giá phương án khác rẻ hơn.

### 14.1. use_remote_estimate

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD use_remote_estimate 'true');
~~~

Option này yêu cầu postgres_fdw gửi remote EXPLAIN để lấy row count/cost estimates. Có thể cấu hình ở foreign table để override server setting.

### 14.2. Khi use_remote_estimate=false

postgres_fdw dùng local estimates và cộng overhead của FDW. Estimates có thể thiếu chính xác nếu local statistics của foreign table cũ hoặc chưa có.

### 14.3. ANALYZE foreign table

~~~sql
ANALYZE remote_sales.orders;
~~~

ANALYZE đọc dữ liệu remote để tạo local statistics cho foreign table. Đây là cách cải thiện local estimates khi không dùng remote estimates.

### 14.4. Chi phí của remote estimates

Remote EXPLAIN thêm network round trip và planning overhead. Với query đơn giản hoặc latency cao, chi phí planning có thể đáng kể.

### 14.5. fdw_startup_cost

Option này biểu diễn overhead khởi tạo foreign scan như connection, remote parse/planning và setup.

### 14.6. fdw_tuple_cost

Option này biểu diễn chi phí bổ sung cho mỗi tuple truyền giữa remote và local. Có thể cần điều chỉnh theo network latency/bandwidth, nhưng không nên thay chỉ để ép planner chọn plan mong muốn.

### 14.7. Statistics bị stale

Nếu remote table thay đổi thường xuyên, local statistics có thể nhanh chóng lỗi thời. Kế hoạch tốt hôm qua có thể trở thành kém hiệu quả sau khi cardinality thay đổi.

### 14.8. Planner có thể chọn fetch riêng từng bảng

Ngay cả khi JOIN pushdown hợp lệ, planner có thể ước lượng rằng fetch từng bảng rồi join local rẻ hơn. Kiểm tra estimates và remote indexes trước khi ép thay đổi.

### 14.9. Đừng tune cost bằng cảm tính

So sánh:
- Network latency và throughput.
- Remote CPU/I/O.
- Số rows và bytes trả về.
- Local CPU/memory.
- Remote query duration.
- Planning overhead.
- Concurrency của remote server.

---

## 15. fetch_size và số lần round trip

fetch_size quyết định số rows postgres_fdw lấy trong mỗi fetch operation.

### 15.1. Default

Giá trị mặc định thường là 100 rows. Có thể đặt ở foreign server hoặc foreign table.

### 15.2. Cấu hình ở server

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD fetch_size '1000');
~~~

Nếu option đã tồn tại, dùng SET.

### 15.3. Cấu hình ở table

~~~sql
ALTER FOREIGN TABLE remote_sales.orders
OPTIONS (ADD fetch_size '2000');
~~~

Table-level setting override server-level setting.

### 15.4. fetch_size không phải predicate pushdown

fetch_size thay đổi cách rows đã được chọn được lấy theo batches. Nó không làm WHERE hoặc JOIN trở nên shippable.

### 15.5. fetch_size quá nhỏ

Có thể tạo nhiều round trips, tăng latency và protocol overhead.

### 15.6. fetch_size quá lớn

Có thể tăng memory usage và lượng dữ liệu được giữ cùng lúc. Chọn theo row width, network và concurrency.

### 15.7. Đo thay vì đoán

Benchmark với nhiều giá trị fetch_size và đo latency, memory, network traffic. Dùng workload representative, không chỉ một query nhỏ.

---

## 16. async_capable và nhiều foreign scans

postgres_fdw có tùy chọn async_capable cho một số Append plans.

### 16.1. Ý nghĩa

Async execution cho phép nhiều phần của Append node được thực hiện đồng thời thay vì tuần tự, nếu plan và FDW support phù hợp.

### 16.2. Cấu hình

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD async_capable 'true');
~~~

Hoặc cấu hình ở foreign table theo version/option scope hỗ trợ.

### 16.3. Default

Tùy chọn này mặc định false. Bật nó không bảo đảm mọi query sẽ chạy song song.

### 16.4. Cùng foreign server và user mapping

Để bảo đảm tính nhất quán dữ liệu, postgres_fdw thường dùng một connection cho một foreign server và chạy các queries tuần tự trên connection đó, trừ khi các table references dùng user mappings khác nhau. Vì vậy async có thể không mang lại lợi ích trong một số trường hợp.

### 16.5. Async không thay JOIN pushdown

Async Append xử lý nhiều subplans song song. Nó không phải cơ chế gửi một JOIN giữa hai bảng sang remote.

### 16.6. Quan sát plan

Kiểm tra node Async Append/Append và actual behavior. Không kết luận từ việc đã bật option.

---

## 17. Những lý do thường khiến pushdown không xảy ra

| Nguyên nhân | Hệ quả thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Function không shippable | Filter chạy local | Remote SQL và local Filter |
| Operator/type không tương thích | Expression không ship | Catalog, type mapping |
| Function không IMMUTABLE | Không đủ điều kiện ship | pg_proc.provolatile |
| Extension chưa khai báo trong extensions | Extension function chạy local | Foreign server options |
| Extension versions khác nhau | Không an toàn hoặc remote error | Local/remote extension inventory |
| Khác foreign servers | JOIN local | Foreign server mapping |
| Khác user mappings | JOIN pushdown bị hạn chế | User mapping identities |
| Local table tham gia JOIN | Phần JOIN phải local | Plan nodes |
| Planner ước lượng remote join đắt | Fetch riêng rồi join | Costs và statistics |
| Collation khác | Không ship hoặc semantics nguy hiểm | Type/collation metadata |
| Remote server version cũ | Function/operator không tồn tại | Remote SQL và server version |
| GROUP BY/aggregate expression không ship | Aggregate local | Aggregate/Foreign Scan nodes |
| Grouping construct không được hỗ trợ | Local aggregation | EXPLAIN VERBOSE |
| Query shape có local expressions | Một phần query local | Remote SQL |
| Statistics lỗi thời | Plan chọn không tốt | ANALYZE/remote EXPLAIN |

### 17.1. Không phải mọi Filter local đều là lỗi

Một expression có thể cần local evaluation để giữ semantics. Mục tiêu là giảm dữ liệu truyền trong khi vẫn đúng, không phải ship mọi thứ bằng mọi giá.

### 17.2. Kiểm tra từng expression

Tách query phức tạp thành:
- Predicates built-in.
- User-defined functions.
- Collation-sensitive conditions.
- Local-table joins.
- Aggregate expressions.

Dùng EXPLAIN VERBOSE sau mỗi thay đổi để xác định expression nào ảnh hưởng pushdown.

---

## 18. Tối ưu predicate để giảm dữ liệu truyền

### 18.1. Lọc sớm bằng conditions shippable

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+00';
~~~

Đây là những điều kiện built-in dễ được ship khi schema tương thích.

### 18.2. Tránh bọc remote column bằng function local-only

~~~sql
SELECT order_id
FROM remote_sales.orders
WHERE public.local_normalize(status) = 'paid';
~~~

Nếu function không shippable, remote có thể phải trả nhiều rows để local xử lý.

Nếu logic có thể được thực hiện an toàn bằng built-in expression hoặc extension đã được cấu hình shippable, kiểm tra lại plan. Không đổi logic nếu behavior khác.

### 18.3. Dùng range thay cho function trên column khi semantics cho phép

Thay vì:

~~~sql
WHERE date_trunc('day', created_at) = TIMESTAMP '2026-11-14 00:00:00'
~~~

Có thể viết:

~~~sql
WHERE created_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00'
~~~

Cách viết range thường thân thiện với index trên created_at và tránh phụ thuộc function trên từng row. Cần xử lý timezone đúng với kiểu timestamp và nghiệp vụ.

### 18.4. Tránh cast không cần thiết trên remote column

~~~sql
WHERE customer_id::text = '42'
~~~

Cast có thể làm mất cơ hội dùng index hoặc thay đổi shippability. Dùng literal có type phù hợp:

~~~sql
WHERE customer_id = 42
~~~

### 18.5. Không chuyển điều kiện từ WHERE sang local chỉ để dễ viết

Mọi thay đổi query cần bảo toàn NULL semantics, timezone, collation và type coercion.

---

## 19. Tối ưu JOIN pushdown

### 19.1. Giữ các remote tables trên cùng foreign server

Nếu hai bảng nằm cùng remote PostgreSQL database, khai báo chúng qua cùng foreign server object để planner có cơ hội join pushdown.

### 19.2. Giữ user mapping nhất quán

Nếu một table dùng mapping A và table khác dùng mapping B, postgres_fdw không thể coi chúng là cùng một remote identity cho join pushdown thông thường.

### 19.3. Kiểm tra remote indexes

Remote server cần indexes phù hợp với:
- Join keys.
- Filter predicates.
- Sort keys.
- Grouping keys nếu có.

### 19.4. Chọn columns vừa đủ

Không kéo columns lớn không cần thiết vào SELECT/JOIN. Điều này giảm network payload nếu join vẫn phải local.

### 19.5. Tránh local expression trong join key nếu có thể

Nếu JOIN key dùng function local-only hoặc cast không tương thích, join có thể không ship. Chuẩn hóa kiểu dữ liệu và schema ở remote khi có thể.

### 19.6. Không ép tất cả joins về remote

Remote server có thể bị quá tải hoặc local server có thể có dataset nhỏ hơn. So sánh cost và resource trước khi tối ưu.

### 19.7. Remote views

Một remote view có thể gom logic JOIN ở remote. Foreign table có thể trỏ tới view thông qua schema/table mapping. Cách này hữu ích khi logic thuộc về remote data owner, nhưng cần quản lý version và dependencies của view.

---

## 20. Tối ưu aggregate pushdown

### 20.1. Tổng hợp trên remote khi dữ liệu cùng nguồn

Nếu dữ liệu cần GROUP BY đều nằm ở cùng remote server, viết query để FDW có thể ship grouping và aggregate expressions.

### 20.2. Giảm số groups

Aggregate pushdown hữu ích nhất khi input rows lớn nhưng số groups nhỏ. Ví dụ doanh thu theo tháng/khu vực thường giảm dữ liệu đáng kể.

### 20.3. Kiểm tra aggregate functions

Dùng built-in aggregates trước. Với custom aggregates, xác nhận remote có cùng definition và FDW xem chúng là shippable theo version.

### 20.4. Grouping expressions

Ưu tiên built-in expressions và types tương thích. Function local-only trong GROUP BY có thể buộc local aggregate.

### 20.5. HAVING

Nếu HAVING có thể ship, remote server loại bỏ groups không cần trước khi trả về. Nếu HAVING chứa local-only expressions, có thể cần local processing.

### 20.6. Window functions

Window functions là một nhóm phép toán khác với ordinary aggregates. Không mặc định rằng aggregate pushdown đồng nghĩa window operations cũng được push. Kiểm tra plan cụ thể.

### 20.7. Grouping sets

ROLLUP, CUBE và GROUPING SETS cần kiểm tra khả năng hỗ trợ của PostgreSQL/FDW version. Nếu không ship, cân nhắc remote view/materialized view hoặc chấp nhận local aggregation với dữ liệu đầu vào đã lọc.

### 20.8. Materialized aggregate ở remote

Với báo cáo lặp lại, remote materialized view hoặc summary table có thể hiệu quả hơn việc tính aggregate mỗi lần. Cần thiết kế refresh schedule, freshness SLA và quyền truy cập.

---

## 21. Kết hợp remote và local data

Không phải mọi query đều có thể thực hiện hoàn toàn ở remote. Một số trường hợp phải chia pipeline.

### 21.1. Remote filter rồi local join

~~~sql
SELECT
    o.order_id,
    d.region_name
FROM (
    SELECT order_id, region_id
    FROM remote_sales.orders
    WHERE created_at >= DATE '2026-01-01'
      AND status = 'paid'
) AS o
JOIN public.region_dimension AS d
    ON d.region_id = o.region_id;
~~~

Remote server có thể lọc orders trước. Local server chỉ nhận order_id/region_id rồi join với local dimension.

### 21.2. Remote join rồi local enrichment

Nếu remote join giữa orders/customers push được, local có thể chỉ enrich kết quả bằng bảng currency mapping hoặc reporting configuration.

### 21.3. Local aggregate sau remote filtering

Khi aggregate expression không ship được, vẫn nên push các predicates an toàn để giảm input rows cho local aggregate.

### 21.4. Materialize local result

Nếu dữ liệu remote được dùng lặp lại nhiều lần và có freshness window cho phép, có thể copy vào staging table/materialized view local. Cách này đổi bài toán query-time network thành batch synchronization và storage.

### 21.5. Đánh giá consistency

Materialize dữ liệu có thể tạo độ trễ so với remote source. Ghi rõ refresh timestamp, watermark và semantics của báo cáo.

---

## 22. Transaction và snapshot semantics

Pushdown ảnh hưởng cách dữ liệu được đọc qua nhiều statements trong cùng local transaction.

### 22.1. Remote transaction

Khi local query truy cập foreign table, postgres_fdw mở remote transaction tương ứng với local transaction nếu chưa có.

### 22.2. Isolation level

Remote transaction dùng SERIALIZABLE khi local transaction là SERIALIZABLE; nếu không, remote transaction dùng REPEATABLE READ theo behavior được tài liệu hóa.

### 22.3. Snapshot consistency

Cách này giúp nhiều scans trên remote server trong cùng local transaction nhìn thấy dữ liệu nhất quán.

### 22.4. READ COMMITTED surprise

Ở local READ COMMITTED, người dùng có thể kỳ vọng mỗi statement thấy snapshot mới. Nhưng remote transaction tương ứng có thể giữ REPEATABLE READ snapshot trong local transaction, nên successive queries có thể vẫn thấy cùng remote data snapshot.

### 22.5. Savepoints

postgres_fdw quản lý remote savepoints tương ứng với local subtransactions.

### 22.6. Two-phase commit

postgres_fdw hiện không hỗ trợ prepare remote transaction cho two-phase commit. Không xem một transaction ghi local và remote như một distributed atomic transaction được bảo đảm bởi 2PC.

### 22.7. Transaction dài

Local transaction mở lâu có thể giữ remote transaction/connection và snapshot. Giữ transaction ngắn, tránh idle-in-transaction và theo dõi remote connections.

---

## 23. Security và quyền truy cập khi pushdown

### 23.1. Remote identity

Query remote chạy bằng identity được cấu hình qua user mapping. Quyền remote role quyết định tables/views nào được đọc.

### 23.2. Row-level security

Nếu remote tables dùng RLS, remote user mapping và remote policies ảnh hưởng rows remote trả về. Local role không tự động thay thế remote identity.

### 23.3. Least privilege

Tạo remote role chỉ có SELECT trên các schemas/tables cần dùng. Không dùng remote superuser cho reporting FDW.

### 23.4. User mappings

User mappings có thể chứa credentials. Hạn chế ai có quyền xem/thay đổi mapping và không đưa raw options vào logs/tickets.

### 23.5. Public user mapping

Public mapping có thể mở quyền kết nối cho nhiều local roles. Chỉ dùng khi chủ đích và remote privileges được giới hạn nghiêm ngặt.

### 23.6. TLS

Bảo vệ kết nối local-to-remote bằng TLS theo policy. Pushdown giảm bytes truyền nhưng không thay thế transport encryption.

### 23.7. EXPLAIN VERBOSE

Remote SQL hiển thị query structure, table names và literals. Không đưa dữ liệu nhạy cảm hoặc secrets vào SQL literals. Hạn chế chia sẻ plan ngoài nhóm được phép.

### 23.8. Remote search_path

postgres_fdw thiết lập remote search_path chỉ gồm pg_catalog cho các sessions do nó mở. Các functions/triggers/rules chạy trên remote cần schema-qualify object names hoặc đặt search_path phù hợp trong function definition.

### 23.9. Function side effects

Chỉ ship functions có behavior phù hợp và được xác nhận immutable. Không dùng extension allowlist để chạy function có side effects hoặc phụ thuộc remote state.

---

## 24. Theo dõi query ở hai phía

Tối ưu pushdown cần quan sát cả local và remote.

### 24.1. Local pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE query ILIKE '%remote_sales%'
ORDER BY query_start;
~~~

Local query text thường hiển thị SQL mà client gửi. Nó không nhất thiết chứa đầy đủ remote SQL đã deparse.

### 24.2. Remote pg_stat_activity

Trên remote server, tìm connections từ local host hoặc application_name tương ứng:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS query_age,
    left(query, 500) AS remote_query
FROM pg_catalog.pg_stat_activity
WHERE application_name LIKE '%postgres_fdw%'
ORDER BY query_start;
~~~

Tên application_name có thể được cấu hình; điều chỉnh filter theo môi trường.

### 24.3. postgres_fdw.application_name

Có thể cấu hình application name để nhận diện remote sessions trong pg_stat_activity/logs. Đặt tên có ý nghĩa như reporting_fdw hoặc analytics_gateway.

### 24.4. Remote logs

Bật logging theo policy để xác định remote SQL, duration và errors. Tránh log parameters/secrets nhạy cảm.

### 24.5. Wait events

Local Foreign Scan có thể chờ network/remote response. Remote backend có thể chờ I/O, lock hoặc CPU. Cần xác định server nào đang là bottleneck.

### 24.6. Connection reuse

postgres_fdw mặc định giữ remote connections để tái sử dụng trong local session. Nhiều local sessions có thể tạo nhiều remote backends; theo dõi connection capacity ở remote.

---

## 25. Đọc dấu hiệu pushdown trong plan

| Plan observation | Diễn giải |
| --- | --- |
| Remote SQL có WHERE | Predicate được ship |
| Remote SQL chỉ chọn vài columns | Projection được ship |
| Remote SQL có JOIN | Join được ship |
| Remote SQL có GROUP BY/aggregate | Aggregate được ship |
| Foreign Scan có local Filter | Một predicate vẫn chạy local |
| Hash Join phía trên Foreign Scan | Có join local |
| HashAggregate phía trên Foreign Scan | Aggregate local |
| Sort phía trên Foreign Scan | Sort local |
| Nhiều Foreign Scan nodes | Có thể có nhiều remote scans/queries |
| Rows thực tế cao hơn estimate nhiều | Statistics/cost estimates có thể stale |
| Remote query chậm nhưng local ít CPU | Bottleneck ở remote hoặc network |
| Remote trả nhiều rows rồi local lọc | Predicate pushdown chưa hiệu quả |

### 25.1. Remote SQL là bằng chứng trực tiếp

Không chỉ nhìn node Foreign Scan. Đọc phần Remote SQL để biết SELECT list, WHERE, JOIN, GROUP BY, ORDER BY và LIMIT thực sự được gửi.

### 25.2. Local node vẫn có thể xuất hiện sau pushdown

Một phần query có thể chạy remote và phần còn lại chạy local. Điều đó không tự động có nghĩa plan kém.

### 25.3. Actual rows quan trọng

Nếu estimates sai nhiều, planner có thể chọn join order hoặc pushdown decision không phù hợp. So sánh estimated rows với actual rows.

### 25.4. Remote plan cần được kiểm tra riêng

Copy Remote SQL và chạy EXPLAIN trên remote server để xem index scan, join algorithm, aggregate strategy, sort và buffers.

---

## 26. Tuning remote estimates và statistics

### 26.1. Bật remote estimates

~~~sql
ALTER SERVER sales_remote
OPTIONS (ADD use_remote_estimate 'true');
~~~

Điều này cho phép postgres_fdw hỏi remote server về estimates. Cân nhắc planning overhead và remote load.

### 26.2. Phân tích foreign table tại local

~~~sql
ANALYZE remote_sales.orders;
~~~

Local statistics có thể hữu ích khi use_remote_estimate=false.

### 26.3. Foreign table thay đổi thường xuyên

Lập lịch ANALYZE theo tốc độ thay đổi và độ nhạy của planner. Statistics cũ làm cardinality estimates sai.

### 26.4. Remote table statistics

Remote server cũng cần ANALYZE/autoanalyze bình thường. Remote planner dựa vào statistics của chính nó để chọn index/join/aggregate plan.

### 26.5. Hai tầng statistics

- Local statistics: giúp local planner ước lượng Foreign Scan.
- Remote statistics: giúp remote planner tối ưu Remote SQL.

Cải thiện một tầng không tự sửa tầng còn lại.

### 26.6. Kiểm tra pg_stats

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals
FROM pg_catalog.pg_stats
WHERE schemaname = 'remote_sales'
  AND tablename = 'orders';
~~~

Đây là local stats của foreign table nếu đã được thu thập; không phải catalog stats trực tiếp của remote table.

### 26.7. ANALYZE sampling

Một số PostgreSQL versions hỗ trợ analyze_sampling option để chọn sampling phía remote hoặc local. Kiểm tra documentation của version đang dùng trước khi cấu hình.

---

## 27. Các option postgres_fdw liên quan tới hiệu năng

| Option | Phạm vi | Tác động |
| --- | --- | --- |
| use_remote_estimate | Server/table | Hỏi remote EXPLAIN để lấy cost/row estimates |
| fdw_startup_cost | Server | Overhead khởi tạo Foreign Scan |
| fdw_tuple_cost | Server | Overhead mỗi tuple truyền về |
| extensions | Server | Allowlist extensions có immutable functions/operators được ship |
| fetch_size | Server/table | Số rows lấy mỗi fetch |
| async_capable | Server/table theo version | Cho phép async execution trong Append plans |
| keep_connections | Server | Giữ hoặc đóng remote connections sau transaction |
| application_name | Server/config | Nhận diện remote sessions |
| batch_size | Server/table | Số rows gửi mỗi insert batch, không phải fetch read size |

### 27.1. Chỉ chỉnh option khi có giả thuyết

Ví dụ:
- Network latency cao và fetch_size nhỏ: thử tăng fetch_size.
- Local estimates sai: thử ANALYZE hoặc use_remote_estimate.
- Remote query không được nhận diện: đặt application_name.
- Nhiều Append scans: đánh giá async_capable.

### 27.2. Batch size không giúp SELECT pushdown

batch_size chủ yếu liên quan insert/COPY vào foreign tables. Không dùng nó để xử lý SELECT trả nhiều rows.

### 27.3. Keep connections

Giữ connection có thể giảm connect overhead. Đổi lại, remote server phải phục vụ nhiều idle connections hơn. Đánh giá pool/connection limits và lifecycle.

---

## 28. Cross-version compatibility

Local và remote server không nhất thiết cùng major version.

### 28.1. Remote thiếu built-in function

Một function built-in mới ở local có thể bị coi là shippable, nhưng remote server cũ chưa có function đó. Remote SQL sẽ thất bại.

### 28.2. Kiểm tra function availability

Trước khi ship expressions có function mới, xác nhận function tồn tại và semantics tương đương trên remote.

### 28.3. Workaround optimization fence

Trong một số trường hợp được tài liệu hóa, có thể đặt foreign table trong subquery có OFFSET 0 để ngăn một expression mới/không tương thích bị đẩy xuống bên trong subquery, rồi đánh giá expression ở local:

~~~sql
SELECT
    public.local_only_function(remote_rows.status)
FROM (
    SELECT status
    FROM remote_sales.orders
    OFFSET 0
) AS remote_rows;
~~~

Đây là kỹ thuật kiểm soát planner, không phải cách tối ưu mặc định. Nó có thể làm thay đổi plan và chi phí. Luôn xác nhận bằng EXPLAIN VERBOSE.

### 28.4. Remote extension versions

Nếu dùng extensions option, local/remote extension versions phải tương thích và functions/operators có semantics giống nhau.

### 28.5. Data type differences

Kiểu dữ liệu mới hoặc casts khác nhau có thể khiến Remote SQL không thực thi hoặc kết quả chuyển đổi khác. Dùng schema compatibility matrix cho các hệ thống tích hợp lâu dài.

---

## 29. Lựa chọn khi pushdown không khả thi

### 29.1. Chấp nhận local processing

Nếu dữ liệu đầu vào nhỏ, local join/aggregate có thể đủ nhanh và đơn giản.

### 29.2. Tạo remote view

Đặt JOIN/aggregate logic tại remote server và khai báo foreign table trỏ tới view. Điều này hữu ích khi logic cần được quản lý cùng dữ liệu nguồn.

### 29.3. Materialized view ở remote

Dùng khi aggregate nặng được truy vấn lặp lại và có thể chấp nhận độ trễ refresh.

### 29.4. Materialize local

Copy một tập dữ liệu có giới hạn vào local staging/materialized view nếu nhiều local queries cần dùng lại. Theo dõi freshness và incremental refresh.

### 29.5. Đồng bộ dữ liệu thay vì query trực tiếp

Nếu ứng dụng chạy report liên tục trên dữ liệu remote lớn, ETL/CDC vào analytics store có thể phù hợp hơn FDW query-time.

### 29.6. Chọn đúng kiến trúc

FDW phù hợp cho tích hợp truy vấn và truy cập dữ liệu từ xa. Nó không luôn là lựa chọn tốt nhất cho analytical workloads khối lượng lớn hoặc join xuyên nhiều nguồn có network latency cao.

---

## 30. Đo hiệu quả pushdown

Không đánh giá chỉ bằng việc Remote SQL dài hay ngắn.

### 30.1. Các metrics cần đo

- Query end-to-end latency.
- Remote execution time.
- Local execution time.
- Rows trả về từ remote.
- Bytes truyền qua network.
- Number of fetch round trips.
- Remote CPU/I/O.
- Local CPU/memory.
- Planning time.
- Connection count.
- Concurrent query impact.

### 30.2. So sánh hai plan

Tạo baseline không pushdown hoặc query tương đương, sau đó so sánh với plan pushdown. Đảm bảo cùng kết quả và cùng data snapshot.

### 30.3. Đo selective predicates

Một predicate chỉ giữ 0.1% rows thường có tiềm năng giảm network lớn. Predicate giữ 95% rows có thể ít lợi ích hơn.

### 30.4. Đo aggregate reduction

So sánh số input rows ở remote với số groups được trả về. Nếu group count gần bằng input count, aggregate pushdown không giảm nhiều data.

### 30.5. Remote server load

Pushdown chuyển CPU work sang remote. Nếu remote server đã bận với workload chính, query local có thể làm remote service degradation.

### 30.6. Concurrency

Benchmark một query đơn lẻ có thể cho kết quả tốt nhưng không phản ánh nhiều sessions đồng thời. Đo ở concurrency gần production.

### 30.7. Cache effects

Chạy nhiều lần có thể làm dữ liệu nằm trong cache. Ghi rõ warm/cold cache state và không so sánh các lượt test có điều kiện khác nhau.

---

## 31. Ví dụ tổng hợp: predicate pushdown

Giả sử remote orders có hàng chục triệu rows và index trên created_at/status.

### 31.1. Query

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    order_id,
    customer_id,
    total_amount
FROM remote_sales.orders
WHERE status = 'paid'
  AND created_at >= DATE '2026-11-01'
  AND created_at <  DATE '2026-12-01';
~~~

### 31.2. Điều cần tìm

Remote SQL cần chứa các predicates status và created_at. Nếu chỉ có SELECT columns mà không có WHERE, local plan có thể phải lọc sau khi fetch.

### 31.3. Kiểm tra remote index

Trên remote server, chạy EXPLAIN với Remote SQL tương đương. Kiểm tra index scan/bitmap scan/sequential scan và actual rows.

### 31.4. Thử local-only expression

Thêm một user-defined function không được khai báo shippable rồi so sánh Remote SQL. Quan sát local Filter.

### 31.5. Kết luận

Predicate pushdown có giá trị khi remote có thể lọc gần nguồn và trả về ít rows hơn đáng kể.

---

## 32. Ví dụ tổng hợp: join pushdown

### 32.1. Hai foreign tables cùng server

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    o.order_id,
    c.customer_name,
    o.total_amount
FROM remote_sales.orders AS o
JOIN remote_sales.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid';
~~~

### 32.2. Kiểm tra Remote SQL

Tìm JOIN và WHERE trong Remote SQL. Nếu có, remote server đang xử lý phần join/filter đó.

### 32.3. Thêm local table

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    o.order_id,
    d.region_name
FROM remote_sales.orders AS o
JOIN public.region_dimension AS d
    ON d.region_id = o.region_id
WHERE o.status = 'paid';
~~~

Quan sát Foreign Scan và local Join node. Remote filter có thể vẫn được ship trong khi local join không thể ship.

### 32.4. Thử mapping khác

Tạo foreign server/table mapping riêng để minh họa join pushdown bị hạn chế khi các references dùng different user mappings. Không dùng credential production cho lab.

### 32.5. Kết luận

Cùng server và mapping tạo điều kiện cho JOIN pushdown; planner vẫn quyết định theo cost và shippability.

---

## 33. Ví dụ tổng hợp: aggregate pushdown

### 33.1. Query

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*) AS order_count,
    sum(total_amount) AS revenue
FROM remote_sales.orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY status
HAVING count(*) > 100
ORDER BY status;
~~~

### 33.2. Điều cần tìm

Remote SQL nên có WHERE, GROUP BY và các aggregate calls nếu toàn bộ biểu thức được ship.

### 33.3. Thử expression không shippable

Thêm local-only function vào grouping expression hoặc HAVING. Quan sát xem aggregate được giữ remote, tách một phần hay chạy local.

### 33.4. Thử grouping sets

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*)
FROM remote_sales.orders
GROUP BY ROLLUP(status);
~~~

Kiểm tra plan cụ thể; grouping sets không nên được giả định là pushable trên mọi version.

### 33.5. Đo số rows

So sánh remote input cardinality với số group rows được trả về. Đánh giá network savings.

### 33.6. Kết luận

Aggregate pushdown giảm dữ liệu mạnh khi số groups nhỏ, nhưng phải xác minh khả năng ship của aggregate và toàn bộ grouping expressions.

---

## 34. Runbook: predicate không được pushdown

### Bước 1: Lấy plan

Chạy EXPLAIN VERBOSE và lưu Remote SQL.

### Bước 2: Xác định local Filter

Tìm Filter node phía trên Foreign Scan và biểu thức không xuất hiện trong Remote SQL.

### Bước 3: Phân loại expression

Kiểm tra:
- Function/operator built-in hay user-defined.
- Volatility.
- Extension membership.
- Type/collation.
- Remote version compatibility.

### Bước 4: Kiểm tra extension option

Nếu expression thuộc extension, xác nhận extension có trên cả hai servers, versions tương thích và đã được khai báo trong extensions option.

### Bước 5: Kiểm tra semantics

Xác nhận function/operator thực sự có behavior giống nhau. Không khai báo extension shippable chỉ để loại bỏ local Filter.

### Bước 6: Rewrite an toàn nếu phù hợp

Dùng built-in predicates hoặc range conditions khi tương đương. Kiểm tra NULL/timezone/collation semantics.

### Bước 7: Re-run EXPLAIN

Xác nhận predicate xuất hiện trong Remote SQL và kết quả query không đổi.

---

## 35. Runbook: JOIN không được pushdown

### Bước 1: Xem Foreign Scan nodes

Xác định mỗi table được truy cập qua foreign server nào.

### Bước 2: Kiểm tra user mapping

Xác định các table references có cùng remote identity không.

### Bước 3: Kiểm tra local relations

Nếu query join với local table, phần join đó phải được thực hiện local.

### Bước 4: Kiểm tra join expressions

Kiểm tra types, casts, collations, functions và operators trong join condition.

### Bước 5: Kiểm tra cost

Planner có thể chọn fetch riêng từng bảng nếu estimate cho thấy rẻ hơn. So sánh rows/costs và remote indexes.

### Bước 6: Kiểm tra Remote SQL

Nếu Remote SQL chứa cả hai remote tables và JOIN, pushdown đã xảy ra. Nếu không, xác định node join local.

### Bước 7: Điều chỉnh schema/query có kiểm soát

Chuẩn hóa types/collations hoặc dùng remote view nếu phù hợp. Re-test kết quả và performance.

---

## 36. Runbook: aggregate chạy local ngoài dự kiến

### Bước 1: Xem Aggregate node

Xác định HashAggregate/GroupAggregate nằm phía trên Foreign Scan hay không.

### Bước 2: Đọc Remote SQL

Kiểm tra có GROUP BY và aggregate calls không.

### Bước 3: Kiểm tra shippability

Xem aggregate function, input expressions, GROUP BY expressions và HAVING.

### Bước 4: Kiểm tra query shape

Xem local joins, grouping sets, window functions, subqueries hoặc expressions có thể ngăn aggregate pushdown.

### Bước 5: Kiểm tra remote compatibility

Đảm bảo remote server có cùng functions/types/operators và semantics phù hợp.

### Bước 6: Tối ưu phần có thể ship

Đẩy predicates shippable trước aggregation để giảm input rows nếu aggregate không thể push toàn bộ.

### Bước 7: Cân nhắc remote view/materialization

Nếu query aggregate quan trọng và chạy thường xuyên, remote view hoặc materialized view có thể là lựa chọn rõ ràng hơn.

---

## 37. Lab 1: cài postgres_fdw và tạo foreign tables

Dùng hai PostgreSQL instances trong development/staging. Một instance đóng vai local, instance còn lại là remote.

### 37.1. Tạo dữ liệu trên remote

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL
);

CREATE TABLE sales.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL
);

CREATE INDEX orders_status_created_idx
    ON sales.orders(status, created_at);

CREATE INDEX orders_customer_idx
    ON sales.orders(customer_id);
~~~

### 37.2. Nạp sample data

~~~sql
INSERT INTO sales.customers
SELECT
    g,
    'Customer ' || g,
    CASE WHEN g % 3 = 0 THEN 'north'
         WHEN g % 3 = 1 THEN 'central'
         ELSE 'south'
    END
FROM generate_series(1, 1000) AS g;

INSERT INTO sales.orders
SELECT
    g,
    ((g - 1) % 1000) + 1,
    CASE WHEN g % 4 = 0 THEN 'paid'
         WHEN g % 4 = 1 THEN 'pending'
         ELSE 'shipped'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g % 300) * INTERVAL '1 day',
    (g % 10000) / 10.0
FROM generate_series(1, 500000) AS g;
~~~

### 37.3. Cài postgres_fdw ở local

~~~sql
CREATE EXTENSION IF NOT EXISTS postgres_fdw;
~~~

### 37.4. Tạo server và mapping

~~~sql
CREATE SERVER sales_lab
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (
    host 'remote-host',
    port '5432',
    dbname 'remote_db'
);

CREATE USER MAPPING FOR CURRENT_USER
SERVER sales_lab
OPTIONS (
    user 'sales_reader',
    password 'lab-only-secret'
);
~~~

Dùng credentials riêng cho lab và không commit chúng vào repository.

### 37.5. Import tables

~~~sql
CREATE SCHEMA remote_sales;

IMPORT FOREIGN SCHEMA sales
LIMIT TO (customers, orders)
FROM SERVER sales_lab
INTO remote_sales;
~~~

### 37.6. Xác nhận

~~~sql
SELECT count(*) FROM remote_sales.orders;
SELECT count(*) FROM remote_sales.customers;
~~~

### 37.7. Kết luận

Foreign tables cho phép query remote data bằng SQL local. Bước tiếp theo là quan sát query được gửi tới remote.

---

## 38. Lab 2: quan sát predicate pushdown

### 38.1. Query không filter

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT order_id, status, created_at
FROM remote_sales.orders;
~~~

Quan sát Remote SQL và số columns được lấy.

### 38.2. Query có filter

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT order_id, created_at
FROM remote_sales.orders
WHERE status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-06-01 00:00:00+00';
~~~

### 38.3. Xác nhận Remote SQL

Remote SQL nên chứa các conditions status và created_at nếu được ship.

### 38.4. Thử function built-in

Thêm lower/upper hoặc phép toán built-in phù hợp trên text. Xem function có xuất hiện trong Remote SQL không.

### 38.5. Thử user-defined function

Tạo một function local không nằm trong extension allowlist rồi dùng trong WHERE. Quan sát local Filter và Remote SQL.

### 38.6. Kết luận

Predicate pushdown được xác nhận bằng Remote SQL; local Filter cho biết còn expression xử lý tại local.

---

## 39. Lab 3: quan sát JOIN pushdown

### 39.1. JOIN hai foreign tables

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    o.order_id,
    c.customer_name,
    o.total_amount
FROM remote_sales.orders AS o
JOIN remote_sales.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid';
~~~

### 39.2. Xem Remote SQL

Kiểm tra câu SQL remote có JOIN giữa sales.orders và sales.customers hay không.

### 39.3. JOIN với local table

Tạo bảng local:

~~~sql
CREATE TABLE public.region_bonus (
    region TEXT PRIMARY KEY,
    bonus_rate NUMERIC(5,4) NOT NULL
);
~~~

Chạy query join foreign tables với region_bonus. Quan sát local join node và Remote SQL.

### 39.4. Thử different mappings

Trong môi trường lab, tạo mapping khác cho một foreign table/server reference và quan sát ảnh hưởng đến join pushdown.

### 39.5. Đọc actual rows

Chạy EXPLAIN ANALYZE trên dataset lab. So sánh rows remote trả về với rows trước JOIN.

### 39.6. Kết luận

JOIN pushdown phụ thuộc cùng foreign server, user mapping, shippability và cost decision.

---

## 40. Lab 4: aggregate pushdown

### 40.1. GROUP BY đơn giản

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*) AS order_count,
    sum(total_amount) AS revenue
FROM remote_sales.orders
WHERE created_at >= DATE '2026-01-01'
GROUP BY status;
~~~

### 40.2. Kiểm tra Remote SQL

Tìm GROUP BY, count và sum trong Remote SQL.

### 40.3. Thêm HAVING

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*) AS order_count
FROM remote_sales.orders
GROUP BY status
HAVING count(*) > 100;
~~~

Kiểm tra HAVING có được ship không.

### 40.4. Thử grouping expression

Thêm date_trunc hoặc một built-in expression vào GROUP BY. Xác nhận expression được remote hỗ trợ.

### 40.5. Thử grouping sets

~~~sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    status,
    count(*)
FROM remote_sales.orders
GROUP BY ROLLUP(status);
~~~

Quan sát xem aggregate có còn nằm ở local hay được ship.

### 40.6. So sánh row counts

Dùng remote count/EXPLAIN và local result cardinality để ước lượng mức giảm dữ liệu.

### 40.7. Kết luận

Aggregate pushdown có thể giảm hàng trăm nghìn rows thành vài groups, nhưng phụ thuộc expressions và query shape.

---

## 41. Lab 5: cost estimates và fetch_size

### 41.1. Bật remote estimate

~~~sql
ALTER SERVER sales_lab
OPTIONS (ADD use_remote_estimate 'true');
~~~

### 41.2. Chạy EXPLAIN

Chạy lại query filter/join/aggregate và quan sát estimated rows/costs. Planning có thể phát sinh remote EXPLAIN requests.

### 41.3. Tắt remote estimate và ANALYZE

~~~sql
ALTER SERVER sales_lab
OPTIONS (SET use_remote_estimate 'false');

ANALYZE remote_sales.orders;
ANALYZE remote_sales.customers;
~~~

### 41.4. So sánh estimates

So sánh plans trước và sau ANALYZE. Nếu remote tables thay đổi, lặp lại ANALYZE theo nhu cầu.

### 41.5. Thử fetch_size

~~~sql
ALTER SERVER sales_lab
OPTIONS (ADD fetch_size '1000');
~~~

Chạy query trả nhiều rows, đo thời gian và memory. Sau đó thử giá trị khác phù hợp.

### 41.6. Phân biệt fetch_size và pushdown

Thay fetch_size không làm WHERE/JOIN/aggregate xuất hiện trong Remote SQL. Nó chỉ thay đổi cách nhận rows đã được remote query chọn.

### 41.7. Kết luận

Cost estimates ảnh hưởng plan selection; fetch_size ảnh hưởng transfer batches. Hai cơ chế giải quyết hai phần khác nhau của hiệu năng.

---

## 42. Bài tập thực hành

### Bài 1 — Khái niệm

Định nghĩa query pushdown và phân biệt với việc copy dữ liệu về local.

### Bài 2 — Các lớp pushdown

Giải thích projection, predicate, join, aggregate, sort và limit pushdown.

### Bài 3 — FDW architecture

Mô tả extension, foreign server, user mapping và foreign table.

### Bài 4 — Setup

Viết SQL cài postgres_fdw, tạo server, mapping và import foreign schema.

### Bài 5 — Projection

Viết query chỉ lấy ba columns từ foreign table và giải thích lợi ích so với SELECT *.

### Bài 6 — Predicate

Viết query lọc orders theo status và date range. Nêu Remote SQL cần có gì.

### Bài 7 — Shippability

Giải thích vì sao postgres_fdw mặc định chỉ ship built-in operators/functions trong WHERE.

### Bài 8 — IMMUTABLE

Phân biệt IMMUTABLE, STABLE và VOLATILE. Vì sao volatility ảnh hưởng pushdown?

### Bài 9 — User-defined function

Một function được khai báo IMMUTABLE nhưng không thuộc built-in set. Cần làm gì để postgres_fdw có thể ship nó?

### Bài 10 — Extensions option

Giải thích extensions option và trách nhiệm khi khai báo một extension shippable.

### Bài 11 — Type compatibility

Một remote numeric column được khai báo local thành text. Những vấn đề nào có thể phát sinh?

### Bài 12 — Collation

Vì sao local/remote collations khác nhau có thể làm predicates hoặc ORDER BY cho kết quả khác?

### Bài 13 — Join pushdown

Viết JOIN giữa remote orders và customers, cùng foreign server/user mapping.

### Bài 14 — Different servers

Hai foreign tables thuộc hai foreign servers khác nhau. Vì sao postgres_fdw không thể gửi một JOIN thông thường tới một server duy nhất?

### Bài 15 — Different mappings

Giải thích ảnh hưởng của user mappings khác nhau tới JOIN pushdown.

### Bài 16 — Local join

Viết query JOIN foreign orders với local dimension. Phần nào có thể ship và phần nào phải local?

### Bài 17 — Outer join semantics

Giải thích vì sao chuyển predicate từ ON sang WHERE có thể làm thay đổi kết quả LEFT JOIN.

### Bài 18 — Aggregate pushdown

Viết query GROUP BY status, COUNT và SUM; nêu điều kiện cần để aggregate được ship.

### Bài 19 — HAVING

Phân biệt WHERE và HAVING. Khi nào HAVING có thể được đẩy remote?

### Bài 20 — Aggregate FILTER

Viết query COUNT(*) FILTER và xác định những expressions cần shippable.

### Bài 21 — DISTINCT aggregate

Phân biệt COUNT(DISTINCT x) với SELECT DISTINCT. Vì sao phải kiểm tra plan thay vì suy luận chung?

### Bài 22 — Grouping sets

Kiểm tra ROLLUP/CUBE/GROUPING SETS trên target version và giải thích plan khi không push được.

### Bài 23 — Window functions

Phân biệt ordinary aggregate pushdown với window-function execution.

### Bài 24 — ORDER BY/LIMIT

Viết query top 100 orders và xác nhận remote SQL có ORDER BY/LIMIT hay không.

### Bài 25 — EXPLAIN VERBOSE

Giải thích Remote SQL, local Filter, Hash Join và HashAggregate trong Foreign Scan plan.

### Bài 26 — EXPLAIN ANALYZE

Nêu rủi ro khi chạy EXPLAIN ANALYZE trên query remote lớn và cách thu thập remote metrics.

### Bài 27 — use_remote_estimate

Giải thích option này và tradeoff giữa remote planning round trip với local estimates.

### Bài 28 — ANALYZE foreign table

Viết lệnh cập nhật local statistics cho foreign table và giải thích khi nào cần chạy lại.

### Bài 29 — fdw_startup_cost/fdw_tuple_cost

Giải thích hai options và vì sao không nên thay đổi chúng chỉ để ép planner chọn pushdown.

### Bài 30 — fetch_size

Giải thích fetch_size, default behavior và ảnh hưởng của giá trị quá nhỏ/quá lớn.

### Bài 31 — batch_size

Phân biệt batch_size với fetch_size và nêu vì sao batch_size không tối ưu SELECT.

### Bài 32 — async_capable

Mô tả async execution trong Append và vì sao bật option không bảo đảm chạy song song.

### Bài 33 — Cross-version

Remote server thiếu một built-in function mới mà local planner coi là shippable. Mô tả lỗi và hướng khắc phục.

### Bài 34 — Remote RLS

Remote table có row-level security. User mapping nào quyết định rows được trả về và cần xác minh gì?

### Bài 35 — Snapshot

Giải thích remote REPEATABLE READ behavior trong local READ COMMITTED transaction và tác động với successive queries.

### Bài 36 — Two-phase commit

Vì sao không nên giả định postgres_fdw cung cấp distributed 2PC cho local/remote writes?

### Bài 37 — Remote monitoring

Viết query tìm postgres_fdw sessions trên remote server và nêu metrics cần quan sát.

### Bài 38 — Predicate troubleshooting

Một function trong WHERE vẫn chạy local. Thiết kế trình tự kiểm tra volatility, extension allowlist, type/collation và Remote SQL.

### Bài 39 — Join troubleshooting

Một JOIN giữa hai foreign tables không được push. Liệt kê nguyên nhân có thể và cách xác nhận.

### Bài 40 — End-to-end tuning

Một report cần join hai remote tables, lọc theo tháng, group theo khu vực và join với local currency table. Xây dựng foreign server/mapping, viết query, xác nhận từng pushdown stage, tune statistics/fetch_size, đo network và remote CPU, rồi đề xuất phương án nếu aggregate hoặc JOIN không thể ship.

---

## 43. Checklist triển khai pushdown

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| FDW | Đúng wrapper và version |
| Remote endpoint | Host/port/database đúng |
| User mapping | Remote identity và least privilege |
| Foreign tables | Column names/types khớp remote |
| Collations | Local/remote semantics tương thích |
| Projection | Chỉ lấy columns cần |
| Predicate | WHERE xuất hiện trong Remote SQL |
| Function volatility | Expressions được ship đáp ứng IMMUTABLE |
| Extension allowlist | Chỉ extension tương thích trong extensions option |
| JOIN server | Các tables cùng foreign server |
| JOIN mapping | Các references dùng cùng user mapping |
| JOIN expressions | Types/operators/functions shippable |
| Aggregate | Aggregate functions và grouping expressions ship được |
| HAVING | Conditions có thể ship |
| Grouping sets | Kiểm tra support của version/FDW |
| ORDER BY/LIMIT | Remote SQL có phần sort/limit mong đợi |
| Cost estimates | use_remote_estimate hoặc local stats phù hợp |
| Local statistics | Foreign tables được ANALYZE theo nhu cầu |
| Remote statistics | Remote tables được ANALYZE/autoanalyze |
| fetch_size | Được benchmark theo row width/concurrency |
| batch_size | Chỉ tune cho write/COPY workload |
| Async | Plan thực sự có async-capable Append |
| Remote indexes | Indexes phù hợp predicates/join/sort |
| Remote load | CPU/I/O/connections không bị quá tải |
| Network | Rows/bytes/round trips được đo |
| EXPLAIN | Remote SQL và local nodes được lưu |
| EXPLAIN ANALYZE | Chỉ chạy khi hiểu tác động |
| Remote monitoring | pg_stat_activity/logs/query stats |
| Security | TLS, grants, RLS và secret handling |
| Transaction | Snapshot/remote transaction behavior đã rõ |
| Compatibility | Remote server/extensions có version tương thích |
| Correctness | Kết quả trước/sau rewrite được đối chiếu |
| Operations | Runbook xử lý lỗi và owner được xác định |

## Kết luận

Đẩy điều kiện, JOIN và tổng hợp sang máy chủ từ xa giúp PostgreSQL giảm dữ liệu truyền qua network và tận dụng khả năng xử lý tại nơi dữ liệu đang nằm. Với postgres_fdw, predicate pushdown phụ thuộc built-in hoặc extension objects được cho phép, đồng thời functions/operators phải đáp ứng yêu cầu shippability và IMMUTABLE. JOIN pushdown cần các foreign tables cùng foreign server và cùng user mapping, còn aggregate pushdown phụ thuộc aggregate functions, grouping expressions và query shape mà FDW hỗ trợ.

Những nguyên tắc cần nhớ:

1. **Pushdown là quyết định của FDW và planner.** Không suy luận từ cú pháp SQL.
2. **WHERE shippable mới được gửi remote.** Built-in objects là mặc định; extension functions cần được khai báo và xác minh.
3. **IMMUTABLE là điều kiện quan trọng.** Không khai báo volatility sai chỉ để ép pushdown.
4. **JOIN pushdown có ranh giới server và identity.** Cùng foreign server và user mapping là điều kiện then chốt.
5. **Aggregate pushdown phải được kiểm chứng.** Kiểm tra aggregate, GROUP BY, HAVING và các expressions trong Remote SQL.
6. **EXPLAIN VERBOSE là bằng chứng trực tiếp.** Đọc Remote SQL cùng local Filter/Join/Aggregate nodes.
7. **Statistics ảnh hưởng quyết định plan.** Remote estimates và local ANALYZE giải quyết hai tầng estimates khác nhau.
8. **fetch_size không tạo pushdown.** Nó chỉ điều chỉnh cách fetch rows đã được chọn.
9. **Kiểu dữ liệu và collation phải tương thích.** Khác biệt có thể gây lỗi hoặc thay đổi semantics.
10. **Pushdown chuyển tải công việc sang remote.** Đo cả remote CPU/I/O và network, không chỉ local query time.
11. **Transaction semantics vẫn quan trọng.** postgres_fdw quản lý remote transaction/snapshot cùng local transaction nhưng không cung cấp 2PC.
12. **Không phải mọi query cần push toàn bộ.** Kết hợp remote filtering với local join/aggregate có thể là kế hoạch hợp lý.
13. **Security đi theo remote identity.** User mapping, RLS, TLS và secret handling phải được kiểm soát.
14. **Tối ưu phải giữ kết quả đúng.** Luôn so sánh output, plan và workload metrics trước/sau thay đổi.

Một quy trình tuning tốt bắt đầu bằng EXPLAIN VERBOSE, xác định rows và expressions nào còn chạy local, kiểm tra shippability cùng user mapping, rồi đo tác động ở cả hai máy chủ. Mục tiêu là giảm dữ liệu truyền và tổng chi phí end-to-end mà vẫn giữ nguyên semantics, quyền truy cập và tính nhất quán của dữ liệu.

## Tài liệu tham khảo

- [PostgreSQL 18 — postgres_fdw](https://www.postgresql.org/docs/18/postgres-fdw.html)
- [PostgreSQL 18 — EXPLAIN](https://www.postgresql.org/docs/18/sql-explain.html)
- [PostgreSQL 18 — Foreign Data Wrappers](https://www.postgresql.org/docs/18/ddl-foreign-data.html)

