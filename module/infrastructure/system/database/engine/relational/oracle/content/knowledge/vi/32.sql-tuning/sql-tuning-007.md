# Giảm round trip, truy vấn lặp và mô hình N+1 từ ứng dụng

Một ứng dụng có thể chạy từng câu SQL rất nhanh nhưng toàn bộ request vẫn chậm vì phải gửi quá nhiều câu SQL qua mạng đến Oracle. Mỗi lần ứng dụng gửi lệnh, database xử lý và trả kết quả đều có chi phí: network latency, protocol, parse/execute/fetch, quản lý cursor và đồng bộ giữa application tier với database tier. Khi ứng dụng phát sinh hàng trăm hoặc hàng nghìn truy vấn nhỏ cho một màn hình, chi phí round trip có thể lớn hơn thời gian database thực hiện từng câu lệnh.

Mô hình **N+1 query** là nguyên nhân phổ biến: ứng dụng chạy một truy vấn lấy N bản ghi cha, sau đó chạy thêm một truy vấn cho từng bản ghi cha để lấy dữ liệu liên quan. Một trang hiển thị 100 đơn hàng có thể tạo 101 round trip dù dữ liệu có thể được lấy bằng một JOIN hoặc một vài truy vấn batch.

Bài học này tập trung vào cách nhận diện và giảm round trip trong ứng dụng dùng Oracle Database:
- Hiểu chi phí round trip và phân biệt round trip với số operation trong execution plan.
- Nhận diện N+1 trong code, ORM, API và log SQL.
- Chuyển truy vấn lặp thành JOIN, EXISTS, aggregation hoặc truy vấn theo tập hợp.
- Batch đọc và ghi, array binding, collection binding và staging table.
- Phân biệt JDBC fetch size với giải pháp xử lý N+1.
- Thiết kế pagination, cache và API dữ liệu phù hợp.
- Đo số lần execute, fetch, parse, latency và database work.
- Thực hành tối ưu một màn hình đơn hàng có quan hệ cha/con.

Các ví dụ dùng Oracle Database 19c và Java/JDBC ở mức khái niệm. Tên API ORM cụ thể có thể khác theo framework và phiên bản. Mục tiêu là giảm số lần ứng dụng phải trao đổi với database mà vẫn giữ đúng kết quả, transaction semantics và khả năng mở rộng.

## 1. Round trip là gì?

Round trip là một lượt trao đổi request/response giữa ứng dụng và database qua kết nối. Với JDBC, một câu lệnh thường đi qua các bước như gửi execute request, database xử lý và trả trạng thái/kết quả; truy vấn trả nhiều hàng còn cần các lần fetch để chuyển dữ liệu về client theo từng đợt.

Một round trip không đồng nghĩa với một operation trong execution plan. Một SQL có thể thực hiện nhiều operation nội bộ trong database nhưng ứng dụng chỉ gửi một execute request. Ngược lại, một vòng lặp Java có thể gửi cùng một câu SELECT 500 lần, tạo nhiều round trip dù mỗi câu chỉ chạy một index lookup rất nhỏ.

### 1.1. Các thành phần tạo độ trễ

Tổng thời gian request có thể được hình dung:

~~~text
Application request
    |
    | 1. Chuẩn bị SQL và bind values
    v
Network request --------------------+
    |                                |
    v                                |
Oracle parse / execute               |
    |                                |
    v                                |
Database work                        |
    |                                |
    v                                |
Network response <-------------------+
    |
    v
Application xử lý kết quả
    |
    +-- Có thể gửi query tiếp theo
~~~

Thời gian người dùng cảm nhận gồm:
- Thời gian xử lý ở application tier.
- Thời gian chờ mạng cho mỗi lần trao đổi.
- Thời gian parse/execute ở Oracle.
- Thời gian đọc block, join, sort và xử lý SQL.
- Thời gian truyền các hàng kết quả về client.
- Thời gian ORM ánh xạ row thành object và chạy logic ứng dụng.

Khi round trip nhiều, network latency và chi phí điều phối có thể cộng dồn. Ví dụ minh họa, nếu mỗi lượt trao đổi tốn trung bình 4 ms và ứng dụng thực hiện 300 lượt tuần tự, chỉ phần chờ round trip đã khoảng 1,2 giây, chưa tính database work và mapping. Đây là phép tính để thấy hiệu ứng cộng dồn, không phải cam kết latency thực tế của mọi hệ thống.

### 1.2. Round trip tuần tự và song song

Nếu ứng dụng thực hiện query thứ hai chỉ sau khi nhận kết quả query thứ nhất, thời gian chờ cộng tuần tự. Chạy nhiều query song song có thể giảm wall-clock time trong một số tình huống, nhưng vẫn tiêu thụ nhiều database sessions/cursors, CPU, I/O và kết nối; nó không tự loại bỏ chi phí N+1.

Không nên sửa N+1 bằng cách mở hàng trăm query đồng thời. Hãy giảm số câu SQL và chọn tập dữ liệu cần lấy.

### 1.3. Parse, execute và fetch

Một SQL SELECT thường có các giai đoạn:
- Parse: Oracle phân tích cú pháp, kiểm tra object/privilege và tìm hoặc tạo cursor phù hợp.
- Execute: thực thi statement với bind values.
- Fetch: lấy từng batch hàng kết quả từ cursor về ứng dụng.

Prepared statement và cursor reuse có thể giảm parse overhead. Fetch size có thể giảm số lượt fetch cho result set lớn. Nhưng hai kỹ thuật này không biến 101 câu SELECT thành một câu SELECT; chúng giải quyết các loại chi phí khác nhau.

## 2. Mô hình N+1 query

N+1 xảy ra khi ứng dụng lấy một danh sách N entity, rồi với mỗi entity lại truy vấn dữ liệu liên quan bằng một SQL riêng.

### 2.1. Ví dụ đơn hàng và chi tiết đơn hàng

Giả sử cần hiển thị danh sách đơn hàng cùng tên khách hàng và tổng số dòng hàng.

Cách viết dễ mắc N+1:

~~~java
List<Order> orders = orderRepository.findRecentOrders();

for (Order order : orders) {
    Customer customer =
        customerRepository.findById(order.getCustomerId());

    List<OrderLine> lines =
        orderLineRepository.findByOrderId(order.getId());

    render(order, customer, lines);
}
~~~

Nếu danh sách có 100 đơn:
- 1 query lấy đơn hàng.
- 100 query lấy customer nếu chưa cache.
- 100 query lấy order lines.

Tổng cộng có thể là 201 câu SQL. Nếu mỗi đơn chỉ cần tổng số dòng hoặc tổng tiền, tải toàn bộ OrderLine cho từng đơn còn làm tăng lượng dữ liệu truyền và object được tạo.

Một biến thể chỉ lấy customer trong vòng lặp có 1 + N query. Đây là tên gọi N+1 phổ biến nhất.

### 2.2. Timeline N+1

~~~text
Request màn hình danh sách
  |
  +-- Q1: SELECT 100 orders
  |
  +-- Q2: SELECT customer WHERE id = 1
  +-- Q3: SELECT customer WHERE id = 2
  +-- Q4: SELECT customer WHERE id = 3
  |      ...
  +-- Q101: SELECT customer WHERE id = 100
  |
  v
Render response
~~~

Nếu mỗi query chỉ mất 1 ms ở database nhưng round trip tuần tự tốn thêm vài ms, thời gian request vẫn tăng mạnh.

### 2.3. N+1 không chỉ nằm trong vòng for

N+1 có thể phát sinh gián tiếp:
- ORM lazy loading một relationship khi getter được gọi.
- Serializer JSON truy cập một collection lazy.
- Template engine gọi getter cho từng row.
- Mapper hoặc DTO assembler gọi repository trong vòng lặp.
- GraphQL resolver tải relation riêng cho từng parent object.
- Service gọi API/database cho từng phần tử của danh sách.
- Một stored procedure gọi routine con nhiều lần, mỗi routine lại phát sinh SQL riêng.

Vì vậy chỉ tìm vòng lặp trong controller chưa đủ. Hãy theo dõi SQL được phát sinh khi serialize/render response và khi truy cập association.

### 2.4. N+1 khác với nhiều operation trong một query

Một câu SQL có HASH JOIN, TABLE ACCESS FULL và SORT vẫn chỉ là một câu SQL do ứng dụng gửi. Nhiều operation nội bộ có thể hiệu quả hơn hàng trăm round trip nhỏ. Tối ưu phải xem cả execution plan và số lần SQL được gọi.

## 3. Nhận diện N+1 trong ứng dụng

### 3.1. Đếm số lần thực thi theo request

Một dấu hiệu mạnh là cùng một SQL shape được thực thi nhiều lần trong một request, mỗi lần bind một ID khác nhau.

Ví dụ log:

~~~text
SELECT * FROM customers WHERE customer_id = :1
  bind :1 = 101
SELECT * FROM customers WHERE customer_id = :1
  bind :1 = 102
SELECT * FROM customers WHERE customer_id = :1
  bind :1 = 103
...
~~~

SQL text giống nhau và chỉ bind value thay đổi. PreparedStatement có thể reuse cursor, nhưng mỗi execute vẫn là một lần trao đổi với database.

### 3.2. Dấu hiệu ở APM và application tracing

Trong trace của một HTTP request, tìm:
- Số span JDBC/SQL.
- Thời lượng từng database span.
- Cùng SQL fingerprint xuất hiện lặp.
- Bind key thay đổi tuần tự.
- Một query parent theo sau bởi N query child.
- Thời gian chờ database chiếm phần lớn request.

Gắn request ID/correlation ID vào log để gom các câu SQL cùng một request. Có thể dùng module/action của Oracle để phân loại workload từ database.

### 3.3. Dấu hiệu trong Oracle

V$SQL có các thông tin như SQL_ID, EXECUTIONS, PARSE_CALLS, FETCHES, ROWS_PROCESSED, ELAPSED_TIME và BUFFER_GETS. Các counter thường tích lũy theo cursor trong shared pool, không tự chia theo HTTP request. Cần kết hợp SQL_ID, module/action, client identifier, thời gian và tracing để quy về request cụ thể.

Ví dụ tìm SQL được thực thi nhiều:

~~~sql
SELECT
    sql_id,
    executions,
    parse_calls,
    fetches,
    rows_processed,
    elapsed_time,
    buffer_gets,
    module,
    action,
    SUBSTR(sql_text, 1, 1000) AS sql_text
FROM v$sql
WHERE executions > 100
ORDER BY executions DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Một SQL có EXECUTIONS lớn chưa chắc là N+1; nó có thể là query hợp lệ chạy cho nhiều request độc lập. Cần so với số request, module/action và SQL trace.

### 3.4. Đếm SQL ở tầng ứng dụng

Có thể dùng datasource proxy, JDBC instrumentation, ORM statistics hoặc APM để đếm:
- Số statement execute.
- Số prepared statement.
- Số result set fetch.
- Số batch execute.
- Tổng thời gian database.
- Số hàng trả về.

Đặt ngưỡng cho từng endpoint. Ví dụ endpoint danh sách 20 đơn không nên tăng từ 5 query lên 45 query chỉ vì có thêm 20 đơn. Ngưỡng cụ thể phải dựa vào thiết kế endpoint và workload.

## 4. Thay N+1 bằng JOIN

Nếu dữ liệu quan hệ có thể lấy bằng một câu SQL, JOIN thường là lựa chọn đầu tiên.

### 4.1. Truy vấn lặp

~~~sql
SELECT order_id, customer_id, order_date
FROM orders
WHERE order_date >= :p_from_date;
~~~

Sau đó ứng dụng lặp từng order và gọi:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id = :p_customer_id;
~~~

### 4.2. JOIN trong một câu

~~~sql
SELECT
    o.order_id,
    o.order_date,
    o.status,
    c.customer_id,
    c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_date >= :p_from_date
ORDER BY o.order_date DESC, o.order_id DESC;
~~~

Ứng dụng nhận order và customer trong cùng result set. Database tối ưu join và thực hiện nhiều operation nội bộ mà không cần một round trip cho mỗi customer.

### 4.3. Khi nào dùng LEFT JOIN?

Nếu order có thể chưa gắn customer hoặc muốn giữ order ngay cả khi không có row customer tương ứng, dùng LEFT JOIN:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name
FROM orders o
LEFT JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_date >= :p_from_date;
~~~

Điều kiện lọc bảng bên phải đặt sai vị trí có thể vô tình biến LEFT JOIN thành INNER JOIN. Ví dụ điều kiện c.active_flag = 'Y' trong WHERE sẽ loại các row không có customer. Nếu muốn giữ order nhưng chỉ nối customer active, đặt điều kiện trong ON hoặc xử lý logic tương ứng.

### 4.4. JOIN có thể nhân số hàng

Nếu một order có 5 order lines, JOIN orders với order_lines sẽ trả 5 dòng cho order đó. Đây là kết quả quan hệ đúng, nhưng ứng dụng phải nhóm các dòng thành object graph nếu API cần một order chứa danh sách lines.

Không dùng DISTINCT để che việc join nhân hàng mà chưa hiểu quan hệ. DISTINCT có thể tốn sort/hash và làm mất các dòng thực sự khác nhau.

## 5. Thay N+1 bằng aggregation

Nếu màn hình chỉ cần tổng số dòng, tổng số lượng hoặc tổng tiền, hãy aggregate trong database thay vì tải tất cả child rows.

### 5.1. Scalar subquery aggregation

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM order_lines l
        WHERE l.order_id = o.order_id
    ) AS line_count,
    (
        SELECT SUM(l.quantity * l.unit_price)
        FROM order_lines l
        WHERE l.order_id = o.order_id
    ) AS order_total
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_date >= :p_from_date;
~~~

Đây vẫn là một câu SQL do ứng dụng gửi. Optimizer có thể biến đổi subquery hoặc chọn access path phù hợp. Không nên giả định scalar subquery luôn được thực thi độc lập đúng một lần cho từng row; hãy xem plan và runtime statistics.

### 5.2. GROUP BY và JOIN

Một cách rõ ràng khác:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    NVL(x.line_count, 0) AS line_count,
    x.order_total
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
LEFT JOIN (
    SELECT
        order_id,
        COUNT(*) AS line_count,
        SUM(quantity * unit_price) AS order_total
    FROM order_lines
    GROUP BY order_id
) x
  ON x.order_id = o.order_id
WHERE o.order_date >= :p_from_date;
~~~

Subquery tổng hợp child rows trước rồi join kết quả với parent. Nếu chỉ quan tâm một tập order nhỏ, có thể cân nhắc giới hạn parent trước khi aggregate để tránh quét quá nhiều child rows; optimizer và statistics sẽ quyết định plan, nên đo với dữ liệu thật.

### 5.3. EXISTS khi chỉ cần biết có child row

Không cần JOIN nếu chỉ muốn kiểm tra có ít nhất một dòng chi tiết:

~~~sql
SELECT o.order_id, o.order_date
FROM orders o
WHERE EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.order_id
      AND l.quantity > 0
);
~~~

EXISTS diễn đạt đúng ý nghĩa semi-join: chỉ cần biết có match. JOIN có thể nhân parent rows khi có nhiều child rows rồi buộc ứng dụng DISTINCT hoặc GROUP BY.

## 6. Lấy object graph bằng một hoặc vài truy vấn

Một màn hình có thể cần danh sách parent cùng child collections. Có hai chiến lược phổ biến: join fetch hoặc batch fetch.

### 6.1. JOIN fetch

~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    l.line_id,
    l.product_id,
    l.quantity,
    l.unit_price
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
LEFT JOIN order_lines l
  ON l.order_id = o.order_id
WHERE o.order_id IN (:order_ids)
ORDER BY o.order_id, l.line_id;
~~~

Một câu query lấy toàn bộ dữ liệu cần thiết. Ứng dụng nhóm các dòng theo order_id để tạo object graph.

Ưu điểm:
- Ít round trip.
- Một snapshot statement nhất quán theo read consistency của Oracle.
- Có thể tận dụng join và index ở database.

Nhược điểm:
- Row parent bị lặp theo số child.
- Nhiều collection to-many JOIN cùng lúc có thể nhân tích Descartes.
- Kết quả truyền qua mạng có thể rất lớn.
- Pagination parent khó hơn nếu join trực tiếp với collection.

### 6.2. Hai query batch

Một chiến lược cân bằng là:
1. Lấy danh sách parent và customer bằng một query.
2. Lấy tất cả child rows cho danh sách parent bằng một query.

~~~sql
SELECT
    order_id,
    order_date,
    customer_id
FROM orders
WHERE order_date >= :p_from_date
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Sau đó lấy lines cho 50 order:

~~~sql
SELECT
    order_id,
    line_id,
    product_id,
    quantity,
    unit_price
FROM order_lines
WHERE order_id IN (
    :p_id_1, :p_id_2, :p_id_3
    -- bind các ID còn lại
)
ORDER BY order_id, line_id;
~~~

Thực tế ứng dụng cần tạo bind placeholders theo số ID trong batch hoặc dùng collection/table-valued input. Với danh sách rất lớn, không nên nối literal vào SQL; dùng phương pháp collection binding, staging table hoặc chia batch phù hợp.

Cách này thường giữ số query cố định theo số loại association thay vì tăng tuyến tính theo số parent. Nó cũng tránh row multiplication quá lớn của một JOIN nhiều collection.

### 6.3. Nhóm child rows ở application tier

Sau query thứ hai, tạo map từ order_id tới danh sách lines:

~~~java
Map<Long, List<OrderLine>> linesByOrder = new HashMap<>();

for (OrderLine line : fetchedLines) {
    linesByOrder
        .computeIfAbsent(line.getOrderId(), key -> new ArrayList<>())
        .add(line);
}

for (Order order : orders) {
    order.setLines(
        linesByOrder.getOrDefault(order.getId(), List.of())
    );
}
~~~

Đây là xử lý trong bộ nhớ, không tạo thêm query. Độ phức tạp thường gần O(number of parents + number of child rows).

### 6.4. Khi nào chọn JOIN và khi nào chọn batch?

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Parent + một quan hệ many-to-one | JOIN |
| Parent + một child collection nhỏ | JOIN fetch hoặc batch fetch |
| Parent + nhiều collection to-many | Nhiều query batch thường tránh row explosion |
| Chỉ cần count/sum/exists | Aggregation hoặc EXISTS |
| Danh sách parent có pagination | Page parent trước, rồi batch fetch children |
| Chi tiết của một parent duy nhất | JOIN hoặc một query parent + một query child tùy payload |

Không có quy tắc rằng luôn phải gom thành một query. Mục tiêu là số round trip hợp lý và lượng dữ liệu cần truyền nhỏ nhất, đồng thời vẫn giữ logic đơn giản.

## 7. Batch fetch trong ORM

ORM thường hỗ trợ lazy/eager loading và batch fetching. Tên cấu hình khác nhau theo framework, nhưng ý tưởng chung là gom nhiều khóa ngoại thành một lần truy vấn.

### 7.1. Lazy loading

Lazy loading chỉ tải association khi code truy cập. Nó có thể tiết kiệm dữ liệu nếu association không được dùng. Nhưng khi vòng lặp truy cập association của từng parent, lazy loading có thể tạo N+1.

~~~java
for (Order order : orders) {
    // Có thể kích hoạt SELECT riêng cho từng order.
    render(order.getCustomer().getName());
}
~~~

### 7.2. Eager loading

Eager loading yêu cầu lấy association sớm. Tùy ORM, framework có thể dùng JOIN hoặc query phụ. Eager không đảm bảo luôn chỉ có một SQL; hãy kiểm tra SQL thực tế được sinh ra.

### 7.3. Batch loading

Batch loading gom các entity/association chưa được tải vào một query dùng nhiều ID:

~~~sql
SELECT *
FROM customers
WHERE customer_id IN (:id1, :id2, :id3, ...);
~~~

Nếu 100 order có 70 customer khác nhau, batch loading có thể lấy 70 customer trong một hoặc vài query thay vì 70 query riêng.

### 7.4. Fetch join và pagination

Fetch join collection to-many có thể làm một parent xuất hiện nhiều dòng. Nếu áp dụng OFFSET/FETCH hoặc pagination trực tiếp trên result đã join, số dòng SQL có thể bị giới hạn trước khi ORM khôi phục đầy đủ parent/child, hoặc ORM phải xử lý pagination trong bộ nhớ tùy framework.

Chiến lược an toàn thường là:
1. Query page parent IDs với ORDER BY ổn định.
2. Query parent/customer cho page đó.
3. Query child rows bằng tập parent IDs.
4. Ghép object graph trong ứng dụng.

### 7.5. Kiểm tra SQL ORM thực tế

Không dựa vào tên annotation như EAGER, LAZY hoặc FETCH để kết luận số query. Bật SQL logging trong môi trường dev/test, đếm số câu theo request và kiểm tra cả lúc serialize response. Đặc biệt chú ý N+1 phát sinh từ getter hoặc serializer.

## 8. Batch read và danh sách ID lớn

Một cách phổ biến để giảm N+1 là gom ID vào một tập rồi truy vấn một lần. Nhưng cách truyền tập ID vào Oracle cần chọn phù hợp.

### 8.1. IN list với bind variables

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id IN (:id1, :id2, :id3);
~~~

Bind variables giúp tránh nối literal và hỗ trợ cursor reuse. Trong Oracle 19c, một biểu thức IN list có giới hạn số expression (thường gặp ORA-01795 khi vượt 1000). Với danh sách lớn, chia batch hoặc dùng collection/staging table.

Không tạo SQL text khác nhau cho mọi giá trị nếu có thể bind; nhưng số lượng placeholder khác nhau vẫn có thể tạo SQL text khác nhau giữa các kích thước batch.

### 8.2. Chia batch

Nếu cần lấy 5.000 ID, chia thành các nhóm phù hợp, ví dụ mỗi batch vài trăm ID. Số round trip trở thành số batch thay vì số parent. Kích thước batch cần cân nhắc:
- Giới hạn IN list.
- Kích thước bind và payload.
- PGA/SQL memory.
- Số row kết quả.
- Network packet và latency.
- Thời gian giữ cursor/transaction.

Batch size không có một con số tối ưu cho mọi ứng dụng. Đo và chọn theo kích thước thực tế.

### 8.3. Global temporary table

Khi tập ID lớn hoặc được dùng trong nhiều câu SQL, có thể nạp ID vào global temporary table (GTT) rồi join:

~~~sql
CREATE GLOBAL TEMPORARY TABLE request_order_ids (
    order_id NUMBER PRIMARY KEY
) ON COMMIT DELETE ROWS;
~~~

Nạp ID bằng batch insert, rồi query:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    l.line_id,
    l.quantity
FROM request_order_ids r
JOIN orders o
  ON o.order_id = r.order_id
LEFT JOIN order_lines l
  ON l.order_id = o.order_id;
~~~

GTT lưu definition vĩnh viễn nhưng dữ liệu tạm thời theo session hoặc transaction tùy ON COMMIT DELETE ROWS/PRESERVE ROWS. Với connection pool, phải hiểu session affinity và cleanup để tránh đọc nhầm dữ liệu cũ trong cùng session.

### 8.4. SQL collection và TABLE()

Có thể định nghĩa SQL collection type rồi bind collection để join như một row source. Ví dụ kiểu SQL-level:

~~~sql
CREATE TYPE number_list_t AS TABLE OF NUMBER;
/
~~~

Truy vấn:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN TABLE(:p_customer_ids) ids
  ON ids.COLUMN_VALUE = c.customer_id;
~~~

Cách bind collection phụ thuộc Oracle JDBC driver và SQL type đã tạo. Trong JDBC Oracle, thường dùng API Oracle-specific như createOracleArray với tên SQL type; cần kiểm tra hướng dẫn driver đúng phiên bản. Không nhầm PL/SQL associative array với SQL nested table type có thể dùng trực tiếp trong SQL.
 
### 8.5. JSON_TABLE cho input dạng JSON

Nếu API đã nhận một danh sách ID trong JSON và cần biến thành hàng SQL, JSON_TABLE có thể chuyển array thành row source:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN JSON_TABLE(
    :p_ids_json,
    '$[*]'
    COLUMNS (
        customer_id NUMBER PATH '$'
    )
) ids
  ON ids.customer_id = c.customer_id;
~~~

Đây là một lựa chọn khi input đã là JSON. Cần xác thực JSON và giới hạn số lượng phần tử. Không chọn JSON chỉ vì có thể; SQL collection hoặc GTT có thể phù hợp hơn nếu dữ liệu nội bộ đã ở dạng ID list.

## 9. Giảm round trip khi ghi dữ liệu

N+1 cũng xuất hiện ở thao tác ghi: ứng dụng insert/update từng hàng trong vòng lặp, mỗi lần execute một statement riêng.

### 9.1. Nhiều execute đơn lẻ

~~~java
for (OrderLine line : lines) {
    try (PreparedStatement ps = connection.prepareStatement(
            "insert into order_lines(order_id, product_id, quantity) values (?, ?, ?)")) {
        ps.setLong(1, line.getOrderId());
        ps.setLong(2, line.getProductId());
        ps.setInt(3, line.getQuantity());
        ps.executeUpdate();
    }
}
~~~

Nếu có 1.000 lines, ứng dụng có thể thực hiện 1.000 execute và nhiều lần parse/round trip. Việc tạo/đóng PreparedStatement trong vòng lặp còn tăng chi phí quản lý statement.

### 9.2. Reuse PreparedStatement và JDBC batch

~~~java
String sql =
    "insert into order_lines(order_id, product_id, quantity) values (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderLine line : lines) {
        ps.setLong(1, line.getOrderId());
        ps.setLong(2, line.getProductId());
        ps.setInt(3, line.getQuantity());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

JDBC batch cho phép driver gửi nhiều DML cùng batch thay vì execute từng statement độc lập. Driver có thể chia batch hoặc dùng cơ chế array binding tùy loại statement, driver và cấu hình; không nên giả định một executeBatch luôn tương đương đúng một network packet/round trip.

### 9.3. Batch size

Không nhất thiết đưa hàng triệu row vào một batch. Chia theo chunk:
- Giữ bộ nhớ ứng dụng trong giới hạn.
- Giảm thời gian một batch giữ transaction/lock.
- Dễ retry phần thất bại.
- Tránh payload quá lớn.
- Cho phép commit theo đơn vị nghiệp vụ đã xác định.

Batch size phải phù hợp transaction semantics. Nếu toàn bộ import cần atomic, không commit từng chunk tùy tiện; nếu mỗi chunk là một đơn vị độc lập, thiết kế idempotency và restart rõ ràng.

### 9.4. Array binding và bulk DML

Oracle JDBC có thể tối ưu batch DML bằng array binding. PL/SQL có FORALL để thực hiện bulk DML trên collection trong database. Cả hai đều giảm overhead so với gọi procedure hoặc execute từng row một.

Nếu ứng dụng có thể gửi một tập dữ liệu vào stored procedure và procedure dùng FORALL, có thể giảm round trip từ nhiều lần gọi xuống một lần gọi cộng xử lý bulk bên database. Nhưng cần quản lý kiểu SQL collection, kích thước payload, exception và transaction boundary.

### 9.5. Set-based DML thường tốt hơn batch

Nếu mọi hàng có cùng phép biến đổi, một câu UPDATE có thể thay thế batch:
 
~~~sql
UPDATE order_lines
SET status = 'ARCHIVED'
WHERE order_date < :p_cutoff;
~~~

Nếu cần cập nhật từ bảng staging:
 
~~~sql
MERGE INTO inventory target
USING inventory_stage source
ON (target.product_id = source.product_id)
WHEN MATCHED THEN
    UPDATE SET target.quantity = source.quantity
WHEN NOT MATCHED THEN
    INSERT (product_id, quantity)
    VALUES (source.product_id, source.quantity);
~~~

Set-based DML giúp optimizer nhìn toàn bộ tập dữ liệu và chọn plan phù hợp. Dùng batch khi mỗi row có input riêng hoặc không thể biểu diễn thao tác thành một câu SQL set-based đơn giản.

## 10. Fetch size và result set lớn

Fetch size là số hàng driver cố gắng lấy mỗi lần fetch từ database. Nó có thể giảm số fetch round trips khi result set lớn.

### 10.1. JDBC setFetchSize

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "select order_id, order_date from orders order by order_id")) {

    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            process(rs.getLong("ORDER_ID"), rs.getDate("ORDER_DATE"));
        }
    }
}
~~~

Fetch size 500 gợi ý driver lấy dữ liệu theo các batch khoảng 500 hàng. Hành vi chính xác phụ thuộc driver và result set type.

### 10.2. Fetch size không chữa N+1

Nếu ứng dụng vẫn chạy 100 câu SELECT customer theo từng order, setFetchSize không làm chúng thành một query. Nó chỉ ảnh hưởng cách fetch hàng của từng result set. N+1 cần được xử lý bằng JOIN, batch loading, collection input hoặc cache phù hợp.

### 10.3. Fetch size quá lớn

Fetch size lớn có thể:
- Giảm số lần fetch.
- Tăng bộ nhớ client.
- Làm ứng dụng nhận dữ liệu nhiều hơn nhu cầu.
- Tăng latency trước khi xử lý xong một batch lớn.
- Tạo áp lực GC hoặc memory trong ứng dụng.

Chọn fetch size dựa trên row width, số hàng, memory budget và cách ứng dụng tiêu thụ dữ liệu. Không đặt cực lớn cho mọi truy vấn.

### 10.4. Streaming và xử lý từng hàng

Nếu chỉ cần xuất dữ liệu lớn, xử lý theo streaming để không materialize toàn bộ result set trong bộ nhớ. Đảm bảo ResultSet, Statement và Connection được đóng đúng vòng đời; không giữ cursor mở lâu hơn cần thiết.

## 11. Pagination để tránh tải quá nhiều

Một nguyên nhân khiến ứng dụng phát sinh nhiều query là API không có pagination rõ ràng, rồi phải gọi thêm từng trang nhỏ hoặc tải toàn bộ dữ liệu.

### 11.1. OFFSET/FETCH

~~~sql
SELECT order_id, order_date, status
FROM orders
ORDER BY order_date DESC, order_id DESC
OFFSET :p_offset ROWS
FETCH NEXT :p_page_size ROWS ONLY;
~~~

OFFSET/FETCH đơn giản cho pagination. Nhưng ở offset lớn, Oracle có thể phải đọc/bỏ qua nhiều hàng trước khi trả page. ORDER BY phải có thứ tự ổn định, thường thêm primary key làm tie-breaker.

### 11.2. Keyset pagination

Với dữ liệu sắp theo order_date và order_id giảm dần, dùng keyset:
 
~~~sql
SELECT order_id, order_date, status
FROM orders
WHERE order_date < :p_last_order_date
   OR (
       order_date = :p_last_order_date
       AND order_id < :p_last_order_id
   )
ORDER BY order_date DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Request tiếp theo gửi giá trị cuối của trang trước làm cursor. Keyset pagination thường hiệu quả hơn cho trang sâu khi có index phù hợp và tránh chi phí OFFSET lớn.

### 11.3. Page parent trước, load child sau

Nếu màn hình cần order lines, hãy giới hạn page parent trước, sau đó lấy child rows cho page IDs bằng một batch query. Không join tất cả child rows rồi áp pagination lên kết quả đã nhân hàng nếu mục tiêu là page theo parent.

## 12. Caching và giảm query lặp

Caching có thể loại bỏ truy vấn lặp cho dữ liệu ít thay đổi, nhưng cần chính sách invalidation và consistency.

### 12.1. Request-scoped cache

Trong một request, nếu nhiều order cùng customer_id, giữ customer đã tải trong Map để không query lại cùng một customer nhiều lần. Đây là giải pháp đơn giản cho duplicate lookup, nhưng không thay thế batch loading khi mỗi order có một customer khác nhau.

### 12.2. Application cache

Cache có thể phù hợp cho:
- Danh mục sản phẩm.
- Mã quốc gia/tỉnh thành.
- Cấu hình ít thay đổi.
- Metadata dùng chung.

Không cache tùy tiện số dư, tồn kho hoặc trạng thái giao dịch cần nhất quán mạnh. Xác định TTL, invalidation, versioning và quyền dữ liệu.

### 12.3. Oracle result cache

Oracle có SQL query result cache và PL/SQL function result cache trong trường hợp phù hợp. Result cache lưu kết quả để tái sử dụng khi dependency không thay đổi theo quy tắc cache. Nó không phải cache tổng quát cho mọi query và không thay thế thiết kế batch/join.

Đọc execution plan và note để biết result cache có được dùng hay không. Đánh giá invalidation, memory và tính phù hợp của dữ liệu trước khi bật.

### 12.4. Cache không chữa N+1 về cấu trúc

Nếu cache hit cho một số ID, số query có thể giảm. Nhưng khi cache miss theo từng entity, N+1 vẫn còn. Hãy sửa cấu trúc truy vấn trước; dùng cache như lớp bổ sung cho dữ liệu có semantics phù hợp.

## 13. Thiết kế API để giảm chattiness

Round trip không chỉ xảy ra giữa ứng dụng và Oracle. Một ứng dụng có thể gọi service khác nhiều lần cho từng phần tử rồi service đó lại gọi database.

### 13.1. API theo tập hợp

Thay API kiểu:
 
~~~text
GET /customers/101
GET /customers/102
GET /customers/103
~~~

Bằng API batch:
 
~~~text
POST /customers:batchGet
{
  "ids": [101, 102, 103]
}
~~~

Service nhận danh sách ID, truy vấn một lần hoặc vài batch và trả map kết quả. Điều này giảm chattiness giữa các service và giữa service với database.

### 13.2. DTO/projection theo màn hình

Không tải toàn bộ entity graph nếu màn hình chỉ cần order ID, ngày, customer name và total. Tạo projection/DTO với đúng cột cần trả về:
 
~~~sql
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    SUM(l.quantity * l.unit_price) AS total_amount
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
LEFT JOIN order_lines l
  ON l.order_id = o.order_id
WHERE o.order_date >= :p_from_date
GROUP BY
    o.order_id,
    o.order_date,
    c.customer_name;
~~~

DTO giảm dữ liệu truyền, mapping và nhu cầu tải association không cần thiết. Đảm bảo phép aggregate đúng ý nghĩa khi một order không có lines.

### 13.3. GraphQL DataLoader pattern

Trong GraphQL, resolver có thể phát sinh N+1 khi mỗi parent resolver tải một relation riêng. DataLoader pattern gom các key trong một execution window rồi gọi batch loader, sau đó ánh xạ kết quả trở lại đúng key.

Batch loader phải giữ mapping key/result ổn định và xử lý key không tìm thấy. Cache của DataLoader thường scoped theo request để tránh rò rỉ dữ liệu giữa người dùng hoặc tenant.

## 14. Stored procedure và ranh giới database API

Một số workload có thể giảm round trip bằng cách gửi một lời gọi PL/SQL thay cho nhiều SQL riêng:
 
~~~sql
BEGIN
    order_api.create_order(
        p_customer_id => :p_customer_id,
        p_items_json  => :p_items_json,
        p_order_id    => :p_order_id
    );
END;
/
~~~

Procedure có thể validate input, insert header và lines bằng FORALL, rồi trả order ID. Ứng dụng chỉ cần một lần gọi API database cho toàn bộ nghiệp vụ.

### 14.1. Lợi ích
- Giảm số lần ứng dụng gọi database.
- Giữ logic dữ liệu gần database.
- Dùng FORALL/set-based SQL.
- Có thể giảm payload qua lại.
- Tạo transaction boundary rõ nếu contract được thiết kế tốt.

### 14.2. Trade-off
- Logic nghiệp vụ có thể bị phân tán giữa Java và PL/SQL.
- Versioning và deploy package cần phối hợp.
- Test và observability cần công cụ phù hợp.
- Procedure quá tổng quát có thể khó tối ưu.
- Không nên đưa mọi business logic vào database chỉ để giảm một vài round trip.

Chọn stored API khi nghiệp vụ dữ liệu có tính nguyên tử, khối lượng DML lớn hoặc cần một contract ổn định. Giữ rõ ai sở hữu COMMIT/ROLLBACK: thông thường ứng dụng/service quản lý transaction, procedure không tự commit trừ khi contract yêu cầu rõ ràng.

## 15. Transaction consistency khi gộp truy vấn

Giảm round trip bằng cách thay nhiều query thành một query có thể thay đổi snapshot semantics.

Oracle cung cấp statement-level read consistency ở READ COMMITTED: mỗi câu SELECT nhìn thấy dữ liệu đã commit tại thời điểm statement bắt đầu. Nếu ứng dụng chạy 100 query riêng, các query có thể nhìn thấy các snapshot ở những thời điểm khác nhau khi transaction khác commit giữa chừng.

Một JOIN duy nhất đọc các bảng trong cùng statement snapshot, thường giúp dữ liệu hiển thị nhất quán hơn giữa parent và child tại thời điểm câu lệnh bắt đầu.

Nếu dùng hai query batch (parent rồi child), ở READ COMMITTED hai statement có thể có snapshot khác nhau. Trong một số nghiệp vụ, điều này có thể tạo trường hợp parent thay đổi hoặc child được thêm/xóa giữa hai query. Nếu cần nhất quán xuyên suốt nhiều statement, cân nhắc transaction/isolation phù hợp như SERIALIZABLE hoặc read-only transaction, đồng thời hiểu chi phí, retry và ORA-08177 có thể phát sinh trong SERIALIZABLE.

Không dùng SERIALIZABLE chỉ để chữa N+1. Trước hết tối ưu số query; sau đó chọn consistency model theo yêu cầu nghiệp vụ.

## 16. Các anti-pattern cần tránh

### 16.1. Query trong getter

Một getter như getCustomerName() không nên âm thầm gọi database. Nó làm chi phí truy cập dữ liệu khó nhìn thấy và serializer có thể kích hoạt N+1.

### 16.2. Repository call trong vòng lặp

Không gọi findById hoặc findChildren trong vòng lặp nếu có thể batch. Nếu mỗi iteration có điều kiện riêng, gom key cần xử lý trước rồi tải tập hợp.

### 16.3. Tạo PreparedStatement mới cho từng row

Reuse statement và dùng JDBC batch. PreparedStatement caching giảm parse overhead nhưng không thay thế batch execution.

### 16.4. SELECT * cho object graph lớn

Lấy đúng cột cần thiết. SELECT * tăng bytes, network transfer và mapping cost, đặc biệt khi bảng có CLOB/BLOB.

### 16.5. JOIN mọi collection to-many

Join nhiều collection độc lập có thể nhân hàng theo tích số lượng phần tử. Ví dụ một order có 4 lines và 3 payments có thể tạo 12 dòng cho cùng order. Dùng query batch riêng cho từng collection hoặc aggregate trước khi join.

### 16.6. Dùng IN list bằng cách nối literal

Không nối ID vào SQL text. Dùng bind variables, collection binding hoặc staging table. Nối literal tạo SQL text biến thiên, khó reuse cursor và mở rủi ro SQL injection.

### 16.7. Song song hóa N+1 vô hạn

Mở nhiều future/thread để chạy hàng trăm query cùng lúc có thể làm pool cạn, tăng concurrent sessions và gây áp lực lên Oracle. Batch và set-based query trước; nếu vẫn cần song song, giới hạn concurrency rõ ràng.

### 16.8. Cache dữ liệu giao dịch thiếu invalidation

Cache stale có thể trả số dư/tồn kho sai. Đặt consistency contract trước khi cache và không coi cache là thay thế cho transaction.

## 17. Đo lường trước và sau tối ưu

Không chỉ đếm query. Cần đo cả số round trip, dữ liệu truyền, database work và thời gian request.

### 17.1. Chỉ số ở application tier

- SQL execute count mỗi request.
- Số lần prepare/parse phía driver.
- Số lần fetch và số row fetch.
- Tổng database span duration.
- Request p50/p95/p99.
- Bytes gửi/nhận nếu instrumentation hỗ trợ.
- Số connection được mượn và thời gian chờ pool.
- Số query trùng lặp theo fingerprint.

### 17.2. Chỉ số ở Oracle

V$SQL cung cấp các counter tích lũy theo cursor:
 
~~~sql
SELECT
    sql_id,
    executions,
    parse_calls,
    fetches,
    rows_processed,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads,
    module,
    action
FROM v$sql
WHERE parsing_schema_name = 'APP'
ORDER BY elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Các counter là tổng theo cursor trong shared pool từ khi cursor được nạp/reset; chúng không tự tương ứng với một HTTP request. Chia elapsed_time cho executions chỉ cho một trung bình gần đúng và có thể bị lệch bởi nhiều execution có kích thước khác nhau.

### 17.3. Gắn module/action

Ứng dụng có thể thiết lập module/action cho session để DBA phân loại SQL:
 
~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'OrderService',
        action_name => 'ListOrders'
    );
END;
/
~~~

Trong connection pool, cần reset module/action khi connection được trả về pool hoặc khi request mới bắt đầu. Nếu không, SQL sau có thể bị gán nhầm module/action của request trước.

### 17.4. SQL trace và TKPROF

SQL trace có thể ghi parse, execute, fetch, waits và thống kê theo session. TKPROF định dạng trace để phân tích:
- Số lần parse/execute/fetch.
- CPU và elapsed time.
- Logical/physical reads.
- Số hàng xử lý.
- Wait events.

DBA có thể bật trace theo session/module/service bằng DBMS_MONITOR theo quyền phù hợp. Trace có thể chứa SQL text và bind values nhạy cảm; bảo vệ file trace và chỉ bật trong khoảng thời gian cần thiết.

### 17.5. So sánh workload tương đương

Trước/sau phải dùng cùng:
- Dataset và trạng thái dữ liệu.
- Bind values hoặc phân bố bind đại diện.
- Số request/concurrency.
- Cache warm/cold conditions được ghi rõ.
- Transaction boundaries.
- Môi trường và execution plan.

Một tối ưu giảm query count nhưng trả gấp 100 lần dữ liệu có thể không cải thiện latency. Hãy so sánh tổng bytes, CPU, buffers, p95 và tải đồng thời.

## 18. Lab: sửa N+1 cho màn hình đơn hàng

Lab tạo ba bảng nhỏ và dữ liệu để so sánh cách truy vấn.

### 18.1. Tạo bảng

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);

CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR2(20),
    CONSTRAINT lab_orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers(customer_id)
);

CREATE TABLE lab_order_lines (
    line_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    product_name VARCHAR2(100),
    quantity NUMBER NOT NULL,
    unit_price NUMBER(12, 2) NOT NULL,
    CONSTRAINT lab_lines_order_fk
        FOREIGN KEY (order_id)
        REFERENCES lab_orders(order_id)
);

CREATE INDEX lab_orders_customer_ix
ON lab_orders(customer_id);

CREATE INDEX lab_lines_order_ix
ON lab_order_lines(order_id);
~~~

### 18.2. Nạp dữ liệu mẫu

~~~sql
BEGIN
    FOR i IN 1 .. 20 LOOP
        INSERT INTO lab_customers(customer_id, customer_name)
        VALUES (i, 'Customer ' || i);
    END LOOP;

    FOR i IN 1 .. 100 LOOP
        INSERT INTO lab_orders(
            order_id,
            customer_id,
            order_date,
            status
        )
        VALUES (
            i,
            MOD(i - 1, 20) + 1,
            DATE '2025-01-01' + MOD(i, 30),
            CASE WHEN MOD(i, 3) = 0 THEN 'PAID' ELSE 'OPEN' END
        );

        FOR j IN 1 .. MOD(i, 4) + 1 LOOP
            INSERT INTO lab_order_lines(
                line_id,
                order_id,
                product_name,
                quantity,
                unit_price
            )
            VALUES (
                i * 10 + j,
                i,
                'Product ' || j,
                j,
                100 + j * 10
            );
        END LOOP;
    END LOOP;

    COMMIT;
END;
/
~~~

### 18.3. Mô phỏng N+1

Query parent:
 
~~~sql
SELECT order_id, customer_id, order_date, status
FROM lab_orders
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Với mỗi order, ứng dụng tiếp tục chạy:
 
~~~sql
SELECT customer_id, customer_name
FROM lab_customers
WHERE customer_id = :p_customer_id;
~~~

Nếu lấy cả lines, mỗi order còn phát sinh:
 
~~~sql
SELECT line_id, product_name, quantity, unit_price
FROM lab_order_lines
WHERE order_id = :p_order_id;
~~~

Đếm số câu SQL thực tế trong ứng dụng. Có thể có 1 + 20 hoặc 1 + 20 + 20 query tùy cách tải association.

### 18.4. Tối ưu bằng JOIN và aggregation

~~~sql
SELECT
    o.order_id,
    o.order_date,
    o.status,
    c.customer_name,
    COUNT(l.line_id) AS line_count,
    NVL(SUM(l.quantity * l.unit_price), 0) AS order_total
FROM (
    SELECT order_id, customer_id, order_date, status
    FROM lab_orders
    ORDER BY order_date DESC, order_id DESC
    FETCH FIRST 20 ROWS ONLY
) o
JOIN lab_customers c
  ON c.customer_id = o.customer_id
LEFT JOIN lab_order_lines l
  ON l.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_date,
    o.status,
    c.customer_name
ORDER BY o.order_date DESC, o.order_id DESC;
~~~

Parent được giới hạn trước, rồi JOIN customer/lines và aggregate. Ứng dụng chỉ cần một query để render danh sách summary. Nếu cần đầy đủ từng line, dùng thêm một query batch cho 20 order IDs.

### 18.5. Tối ưu bằng hai query batch

Query 1:
 
~~~sql
SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.status,
    c.customer_name
FROM (
    SELECT order_id, customer_id, order_date, status
    FROM lab_orders
    ORDER BY order_date DESC, order_id DESC
    FETCH FIRST 20 ROWS ONLY
) o
JOIN lab_customers c
  ON c.customer_id = o.customer_id
ORDER BY o.order_date DESC, o.order_id DESC;
~~~

Query 2: lấy lines cho tập order IDs của page. Với số ID nhỏ, bind từng placeholder; với số ID lớn, cân nhắc SQL collection hoặc GTT.
 
~~~sql
SELECT
    order_id,
    line_id,
    product_name,
    quantity,
    unit_price
FROM lab_order_lines
WHERE order_id IN (
    :id1, :id2, :id3
    -- bind các ID còn lại của page
)
ORDER BY order_id, line_id;
~~~

Ứng dụng nhóm lines theo order_id. Số query là hai cho cả page thay vì tăng theo số order.

### 18.6. Đo và so sánh

Ghi lại:
- Số query/execute mỗi request.
- Tổng thời gian database spans.
- Tổng rows trả về.
- Bytes truyền nếu có.
- Request elapsed time.
- Buffers/Reads và execution plan của query batch.

Kết quả kỳ vọng là query count giảm mạnh. Tuy nhiên, JOIN có thể trả nhiều dòng hơn nếu tải child collection; chọn cách summary aggregation hay batch detail theo payload thực sự cần.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Màn hình chậm dù từng SQL nhanh | N+1 hoặc nhiều round trip tuần tự | Đếm SQL theo request, batch hoặc JOIN |
| Thêm fetch size nhưng vẫn nhiều SQL | Fetch size chỉ điều chỉnh fetch result set | Sửa cấu trúc truy vấn N+1 |
| Eager loading vẫn tạo nhiều query | ORM chọn secondary selects | Bật SQL log, batch fetch hoặc projection |
| JOIN làm duplicate parent | Quan hệ one-to-many tạo nhiều dòng | Group/aggregate hoặc batch fetch |
| JOIN nhiều collection làm row explosion | Tích số lượng các quan hệ to-many | Tách query batch theo collection |
| IN list quá lớn báo ORA-01795 | Vượt giới hạn expression trong IN list | Chia batch, collection binding hoặc GTT |
| Batch insert vẫn chậm | Batch quá lớn/nhỏ, index/trigger hoặc commit không phù hợp | Đo batch size và dùng set-based DML nếu có thể |
| PreparedStatement vẫn N+1 | Reuse giảm parse, không loại execute lặp | Gom ID hoặc đổi thành một query |
| Chạy query song song làm DB quá tải | Concurrency không giới hạn | Giảm query count và giới hạn worker |
| Pagination thiếu child rows | Paginate trực tiếp trên JOIN to-many | Page parent IDs trước, fetch child sau |
| Cache trả dữ liệu cũ | Invalidation/TTL không phù hợp | Xác định consistency contract |
| Query batch đọc quá nhiều | Batch ID hoặc projection quá rộng | Giới hạn tập ID và chọn cột cần thiết |
| Gộp query làm dữ liệu không nhất quán | Nhiều statement trước đó dùng snapshot khác nhau | Chọn transaction/isolation theo nghiệp vụ |
| V$SQL executions cao bị hiểu nhầm là N+1 | Counter tích lũy nhiều request | Kết hợp tracing và module/action |
| Gọi stored procedure nhưng vẫn nhiều round trip | Procedure gọi SQL qua database link hoặc client gọi lặp | Đo toàn bộ call chain và thiết kế batch API |

## 20. Checklist thiết kế

Trước khi phát hành một endpoint đọc/ghi dữ liệu:

1. Đếm số SQL execute cho một request có kích thước đại diện.
2. Tìm query fingerprint lặp với bind ID thay đổi.
3. Kiểm tra lazy association có bị kích hoạt trong loop/serializer không.
4. Chọn JOIN nếu dữ liệu quan hệ cần lấy cùng nhau và row count hợp lý.
5. Chọn EXISTS/aggregation nếu chỉ cần boolean/count/sum.
6. Chọn batch fetch nếu có nhiều collection to-many.
7. Page parent trước khi lấy child rows.
8. Dùng bind variables, collection input hoặc GTT cho tập ID.
9. Dùng JDBC batch/array binding cho DML lặp.
10. Dùng fetch size để tối ưu fetch của result set lớn, không coi nó là cách chữa N+1.
11. Giới hạn concurrency và kích thước batch.
12. Xác định transaction consistency khi tách thành nhiều query.
13. Đo query count, bytes, buffers, latency và p95 trước/sau.
14. Kiểm tra connection pool và reset module/action khi dùng pooling.
15. Đánh giá cache theo tính nhất quán và invalidation.
16. Kiểm tra quyền, SQL trace và dữ liệu nhạy cảm trước khi bật instrumentation.

## 21. Bài tập thực hành

Sử dụng LAB_CUSTOMERS, LAB_ORDERS và LAB_ORDER_LINES trong mục 18.

### Bài 1 — Đếm N+1

Viết chương trình lấy 20 order rồi gọi query customer cho từng order. Đếm tổng execute. Thử thêm query lines và ghi lại số query mới.

### Bài 2 — JOIN

Thay query customer lặp bằng JOIN. So sánh query count, rows trả về và thời gian request.

### Bài 3 — Aggregation

Viết một query trả line_count và order_total cho mỗi order. So sánh với cách tải tất cả lines rồi tính tổng ở Java.

### Bài 4 — Batch fetch

Lấy 20 order trong query đầu và toàn bộ lines trong query thứ hai. Nhóm lines theo order_id trong Java. Xác nhận query count không tăng theo số order.

### Bài 5 — Pagination

Tạo hai page theo OFFSET/FETCH rồi chuyển sang keyset pagination. Kiểm tra thứ tự ổn định khi nhiều order có cùng order_date.

### Bài 6 — JDBC batch

Insert nhiều order lines bằng executeUpdate từng row, sau đó dùng addBatch/executeBatch. So sánh số execute, thời gian và transaction behavior.

### Bài 7 — Fetch size

Truy vấn một tập nhiều hàng, thử fetch size 50, 200 và 500. Quan sát thời gian, memory và số fetch nếu driver instrumentation hỗ trợ. Giải thích vì sao kết quả này không giải quyết query N+1.

### Bài 8 — GTT hoặc collection binding

Tạo một tập nhiều order IDs, nạp vào GTT hoặc SQL collection, rồi JOIN để lấy dữ liệu. So sánh với IN list nhiều bind placeholders.

### Bài 9 — Transaction consistency

Trong hai session, chạy hai query batch parent/child trong khi session còn lại sửa dữ liệu. Quan sát READ COMMITTED và đánh giá có cần transaction/isolation khác theo yêu cầu màn hình hay không.

### Bài 10 — Instrumentation

Gắn MODULE/ACTION cho endpoint lab. Lấy V$SQL hoặc trace để đếm execute/fetch. Viết báo cáo trước/sau tối ưu gồm query count, rows, buffers và p95 latency.

## 22. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP TABLE lab_order_lines PURGE;
DROP TABLE lab_orders PURGE;
DROP TABLE lab_customers PURGE;
~~~

Nếu đã tạo thêm GTT, SQL collection type hoặc object khác trong bài tập, chỉ xóa đúng object lab của mình. Không xóa object nghiệp vụ hoặc bảng dùng chung.

## Tổng kết

N+1 xuất hiện khi ứng dụng lấy một tập parent rồi truy vấn riêng dữ liệu liên quan cho từng parent. Chi phí không chỉ nằm ở SQL execution mà còn ở network round trip, parse/execute/fetch, ORM mapping và số lần chờ tuần tự. PreparedStatement reuse giảm parse overhead; fetch size giảm fetch round trip cho result set lớn; cả hai không tự loại bỏ N+1.

Hãy ưu tiên set-based SQL, JOIN, EXISTS và aggregation khi phù hợp. Với object graph có nhiều collection to-many, page parent trước rồi batch fetch từng collection bằng tập ID, SQL collection hoặc GTT. Với DML lặp, dùng JDBC batch/array binding hoặc PL/SQL FORALL; nếu có thể biểu diễn bằng một UPDATE/MERGE set-based thì hãy cân nhắc trước. Chọn batch size, fetch size, pagination và cache theo workload thực tế.

Giảm query count phải đi cùng kiểm soát lượng dữ liệu truyền, transaction consistency, connection pool và runtime plan. Dùng application tracing, SQL fingerprint, module/action, V$SQL và SQL trace để đo trước/sau. Một tối ưu tốt làm giảm round trip mà vẫn trả đúng dữ liệu, giữ đúng transaction semantics và cải thiện latency dưới concurrency thực tế.

## Tài liệu Oracle và JDBC tham khảo

- [Oracle Database JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC statements, result sets, batching và LOB/array APIs.
- [Oracle Database JDBC Developer's Guide — Performance Extensions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/performance-extensions.html) — statement caching, batching và fetch behavior.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — optimizer, execution plan và SQL performance.
- [Oracle Database PL/SQL Language Reference — FORALL Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/FORALL-statement.html) — bulk DML trong PL/SQL.
- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — joins, subqueries, row limiting và query syntax.
- [Oracle Database SQL Language Reference — CREATE TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html) — global temporary tables.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html) — gắn module/action cho session.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_MONITOR (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_MONITOR.html) — SQL trace theo session, client identifier, service và module.
- [Oracle Database Reference — V$SQL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html) — executions, fetches, elapsed time và buffer gets.

Khi triển khai trên Oracle release hoặc JDBC driver khác 19c, hãy đối chiếu tài liệu driver đúng phiên bản, đặc biệt batch execution, array binding, collection binding, fetch size và các giới hạn SQL/IN list.
