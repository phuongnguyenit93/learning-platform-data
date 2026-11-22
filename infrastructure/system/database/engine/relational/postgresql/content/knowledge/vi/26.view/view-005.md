# Materialized view và sự đánh đổi độ mới của dữ liệu trong PostgreSQL

Một hệ thống bán hàng có thể nhận hàng nghìn đơn mỗi phút nhưng màn hình báo cáo vẫn phải hiển thị tổng doanh thu theo ngày, theo vùng. Nếu mỗi lần mở dashboard đều chạy `JOIN`, `GROUP BY` và `SUM` trên hàng triệu đơn hàng, thời gian phản hồi có thể tăng cao. Một giải pháp trong PostgreSQL là **materialized view** (*khung nhìn vật hóa*): lưu kết quả của một truy vấn dưới dạng dữ liệu vật lý để có thể đọc lại nhiều lần.

Ví dụ, thay vì tính doanh thu từ đầu mỗi lần:

~~~sql
SELECT
    (o.created_at AT TIME ZONE 'UTC')::date AS report_date,
    c.region,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS revenue
FROM orders AS o
JOIN customers AS c ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
GROUP BY
    (o.created_at AT TIME ZONE 'UTC')::date,
    c.region;
~~~

ứng dụng có thể đọc một materialized view đã tính sẵn:

~~~sql
SELECT report_date, region, paid_orders, revenue
FROM daily_paid_revenue_mv
WHERE report_date >= DATE '2026-01-01'
ORDER BY report_date, region;
~~~

**Đổi lại, materialized view không tự cập nhật ngay khi bảng nguồn thay đổi.** Nếu đơn mới được ghi lúc 10:01 nhưng lần refresh gần nhất kết thúc lúc 10:00, dashboard có thể tiếp tục hiển thị số cũ cho tới khi refresh tiếp theo hoàn thành.

~~~text
Bảng nguồn (orders, customers)
    |
    +--- INSERT / UPDATE / DELETE liên tục
    |
    +--- Truy vấn tổng hợp tốn chi phí
                |
                v
       REFRESH MATERIALIZED VIEW
                |
                v
     Materialized view lưu kết quả
                |
                +--- SELECT dashboard nhanh hơn
                |
                +--- Dữ liệu có thể trễ so với nguồn
~~~

Sự đánh đổi không chỉ là **tốc độ so với độ mới**. Mỗi lần refresh cũng tiêu thụ CPU, I/O, bộ nhớ, WAL và có thể tạo tranh chấp khóa. Bài học này phân tích đầy đủ cơ chế, cú pháp, tính nhất quán, `REFRESH` thường và `CONCURRENTLY`, chỉ mục, quy trình theo dõi freshness, vận hành, phương án thay thế và các tình huống cần quyết định dựa trên nhu cầu nghiệp vụ.

## 1. Mục tiêu học tập

Hoàn thành bài, bạn có thể:

1. Phân biệt `VIEW` thông thường với `MATERIALIZED VIEW`.
2. Giải thích materialized view lưu kết quả tại một thời điểm và vì sao dữ liệu có thể **stale**.
3. Tạo materialized view bằng `CREATE MATERIALIZED VIEW ... AS SELECT ... WITH DATA`.
4. Dùng `WITH NO DATA`, hiểu trạng thái chưa được populate và cách khởi tạo.
5. Cập nhật dữ liệu bằng `REFRESH MATERIALIZED VIEW`.
6. Xác định điều kiện và đánh đổi khi dùng `REFRESH MATERIALIZED VIEW CONCURRENTLY`.
7. Tạo **UNIQUE index** hợp lệ để refresh concurrent.
8. Phân biệt **độ mới**, **tính nhất quán snapshot** và **thời gian thực thi refresh**.
9. Tạo một bộ dữ liệu lab và quan sát kết quả trước/sau `INSERT`, `UPDATE`, `DELETE`.
10. Theo dõi mốc refresh thành công, tuổi dữ liệu và rủi ro job bị lỗi.
11. Thiết kế lịch refresh theo SLA, sức chịu tải nguồn và thời gian chạy thực tế.
12. Nhận diện khi nên chọn view thường, bảng tổng hợp cập nhật tăng dần, cache hoặc kiến trúc khác.

## 2. View thường và materialized view khác nhau thế nào?

Một **view thường** trong PostgreSQL lưu **định nghĩa truy vấn**, không tự lưu một bộ kết quả đầy đủ:

~~~sql
CREATE VIEW reporting.v_daily_paid AS
SELECT ... FROM ...;
~~~

Khi ứng dụng truy vấn view, PostgreSQL thực thi một kế hoạch tương ứng trên nguồn, có thể áp dụng tối ưu hóa/pushdown thích hợp.

Ngược lại, **materialized view** lưu **các hàng kết quả** của truy vấn định nghĩa:

~~~sql
CREATE MATERIALIZED VIEW reporting.mv_daily_paid AS
SELECT ... FROM ...
WITH DATA;
~~~

Ứng dụng đọc bảng kết quả đã vật hóa; dữ liệu này **chỉ đổi khi có thao tác refresh được thực hiện thành công** hoặc materialized view được xây dựng lại theo quy trình phù hợp.

| Tiêu chí | VIEW | MATERIALIZED VIEW |
| --- | --- | --- |
| Lưu gì? | Định nghĩa truy vấn | Định nghĩa + dữ liệu kết quả vật lý |
| Khi SELECT | Đọc nguồn theo plan được tối ưu | Đọc kết quả đã lưu |
| Dữ liệu mới ghi vào nguồn | Có thể thấy theo snapshot của SELECT tiếp theo | Chưa thấy cho tới refresh |
| Chi phí SELECT phức tạp | Có thể phải JOIN/aggregate lại | Thường giảm nếu kết quả nhỏ, có index |
| Dung lượng lưu riêng cho kết quả | Không đáng kể | Có, gồm dữ liệu và indexes |
| Tạo index trực tiếp lên view? | Không như bảng vật lý | Có |
| Refresh thủ công | Không áp dụng | Có |
| Độ mới | Theo cơ chế đọc nguồn/MVCC | Theo lần refresh gần nhất |
| Phù hợp | Dữ liệu cần mới, query không quá đắt | Dashboard/báo cáo chấp nhận trễ |

### 2.1. “View thường luôn chậm” là nhận định sai

Một view thường có predicate chọn lọc, index nguồn phù hợp và lượng dữ liệu nhỏ có thể rất nhanh. Materialized view chỉ đáng cân nhắc khi chi phí **tính lại thường xuyên** cao hơn chi phí lưu, refresh và vận hành kết quả.

### 2.2. “Materialized view luôn nhanh” cũng sai

Nếu materialized view vẫn có hàng chục triệu dòng, query không có index thích hợp hoặc phải sort/aggregate thêm, SELECT có thể vẫn chậm. PostgreSQL không tự bảo đảm chỉ vì có chữ `MATERIALIZED` thì workload được tối ưu.

### 2.3. Materialized view không phải cơ chế cache vô hình

PostgreSQL không tự động thay truy vấn nguồn bằng một materialized view tương đương chỉ vì bạn đã tạo view đó. Ứng dụng hoặc tầng truy vấn phải **chủ động SELECT từ materialized view**.

## 3. Tính nhất quán khác với độ mới

Đây là hai tính chất độc lập cần hiểu trước khi dùng materialized view.

**Độ mới (*freshness*):** Kết quả gần với trạng thái bảng nguồn hiện tại tới đâu?

**Tính nhất quán (*consistency*):** Các hàng có phản ánh một trạng thái dữ liệu hợp lệ thay vì sự pha trộn nửa cũ nửa mới từ một refresh đang dở không?

Một materialized view có thể **nhất quán nhưng cũ**. Ví dụ:

~~~text
09:00:00  REFRESH lấy snapshot dữ liệu nguồn
09:00:12  REFRESH hoàn thành
09:00:15  Có đơn hàng mới COMMIT
09:00:20  Dashboard SELECT từ materialized view
~~~

Dashboard có thể đọc một tập kết quả nhất quán được tạo từ snapshot lúc refresh, nhưng **không chứa đơn mới** commit sau snapshot.

### 3.1. Refresh hoàn thành không đồng nghĩa thấy mọi commit trước lúc hoàn thành

Nếu một đơn được commit **sau khi snapshot dùng để xây dựng refresh đã được xác lập**, đơn ấy có thể chưa có trong kết quả, dù commit xảy ra trước khi refresh hoàn tất. Do đó nhãn `last_refreshed_at` không phải lúc nào cũng là **ranh giới chính xác của toàn bộ thay đổi nguồn đã được bao gồm**.

### 3.2. Người đọc không thấy kết quả refresh nửa chừng

Theo cơ chế giao dịch/MVCC và khóa của PostgreSQL, người đọc không được xem một bộ kết quả bị cập nhật dở như một trạng thái thành công. Tuy nhiên, với refresh thường họ **có thể phải chờ khóa**; với refresh concurrent, những SELECT phù hợp có thể tiếp tục đọc dữ liệu cũ cho đến khi dữ liệu mới được công bố.

### 3.3. Snapshot consistency không đảm bảo business freshness

Số doanh thu từ 10 phút trước có thể vẫn được tính đúng theo dữ liệu của snapshot ấy. Nhưng nếu báo cáo dùng để quyết toán tức thời, độ trễ 10 phút có thể **không được chấp nhận**, dù truy vấn trả rất nhanh và nhất quán.

## 4. Chuẩn bị lab PostgreSQL

Ví dụ sau chạy trong **database thử nghiệm**. Không tạo schema, khóa hoặc refresh bảng dùng chung trên production. Chúng ta tạo nguồn đơn giản để kiểm chứng thay đổi dữ liệu.

### 4.1. Tạo schema

~~~sql
CREATE SCHEMA mv_lab;
~~~

### 4.2. Tạo bảng khách hàng

~~~sql
CREATE TABLE mv_lab.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    region text NOT NULL
);
~~~

### 4.3. Tạo bảng đơn hàng

~~~sql
CREATE TABLE mv_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES mv_lab.customers(customer_id),
    created_at timestamptz NOT NULL,
    status text NOT NULL CHECK (
        status IN ('paid', 'pending', 'cancelled')
    ),
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
~~~

Chúng ta giữ `customer_id` và `created_at` là cột quan hệ có kiểu rõ ràng để việc lọc, JOIN, tổng hợp và quản lý thời gian dễ hiểu.

### 4.4. Chèn khách hàng

~~~sql
INSERT INTO mv_lab.customers (
    customer_id, customer_name, region
) VALUES
    (1, 'An',   'north'),
    (2, 'Bình', 'south'),
    (3, 'Chi',  'north'),
    (4, 'Dung', 'central');
~~~

### 4.5. Chèn tám đơn hàng

~~~sql
INSERT INTO mv_lab.orders (
    customer_id, created_at, status, total_amount
) VALUES
    (1, '2026-01-10 09:00:00+00', 'paid',      120.00),
    (2, '2026-01-10 10:00:00+00', 'paid',       80.00),
    (1, '2026-01-10 11:00:00+00', 'cancelled',  60.00),
    (3, '2026-01-10 12:00:00+00', 'paid',       50.00),
    (4, '2026-01-11 09:00:00+00', 'paid',      200.00),
    (2, '2026-01-11 10:00:00+00', 'pending',    30.00),
    (2, '2026-01-11 11:00:00+00', 'paid',       70.00),
    (1, '2026-01-12 08:00:00+00', 'paid',       40.00);
~~~

Các `order_id` của dữ liệu mẫu thường là 1 đến 8 trên bảng mới tạo. Nếu schema đã có dữ liệu trước đó hoặc sequence đã thay đổi, không dựa vào ID cố định cho thao tác trên môi trường không sạch.

### 4.6. Vì sao chọn ngày UTC?

Chúng ta dùng ngày báo cáo UTC:

~~~sql
(created_at AT TIME ZONE 'UTC')::date
~~~

Điều này giúp kết quả ổn định theo timezone của ứng dụng. Nếu nghiệp vụ yêu cầu báo cáo theo múi giờ Việt Nam hoặc từng cửa hàng, phải thiết kế ranh giới ngày và khóa nhóm theo timezone ấy; **không thay UTC thành timezone khác mà không đánh giá sự thay đổi kết quả**.

## 5. Xây VIEW thường làm mốc so sánh

~~~sql
CREATE VIEW mv_lab.v_daily_paid AS
SELECT
    (o.created_at AT TIME ZONE 'UTC')::date AS report_date,
    c.region,
    COUNT(*)::bigint AS paid_orders,
    SUM(o.total_amount)::numeric(14, 2) AS revenue,
    MAX(o.created_at) AS latest_paid_order_at
FROM mv_lab.orders AS o
JOIN mv_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
GROUP BY
    (o.created_at AT TIME ZONE 'UTC')::date,
    c.region;
~~~

### 5.1. Truy vấn view

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.v_daily_paid
ORDER BY report_date, region;
~~~

Dữ liệu khởi đầu có năm nhóm:

| report_date (UTC) | region | paid_orders | revenue |
| --- | --- | ---: | ---: |
| 2026-01-10 | north | 2 | 170.00 |
| 2026-01-10 | south | 1 | 80.00 |
| 2026-01-11 | central | 1 | 200.00 |
| 2026-01-11 | south | 1 | 70.00 |
| 2026-01-12 | north | 1 | 40.00 |

Đơn `cancelled` và `pending` không được tính. Cột `latest_paid_order_at` là **ngày tạo mới nhất của đơn paid trong nhóm**, không phải thời điểm view hay materialized view được refresh.

### 5.2. Phải kiểm tra JOIN cardinality

Vì mỗi đơn tham chiếu đúng một customer, JOIN này không nhân số đơn ngoài chủ ý. Nếu bạn JOIN thêm một bảng một-nhiều như `order_events` trước khi `SUM`, tổng doanh thu có thể bị nhân lên. **Vật hóa một truy vấn tổng hợp sai chỉ giúp trả kết quả sai nhanh hơn.**

## 6. Tạo materialized view

~~~sql
CREATE MATERIALIZED VIEW mv_lab.mv_daily_paid AS
SELECT
    report_date,
    region,
    paid_orders,
    revenue,
    latest_paid_order_at
FROM mv_lab.v_daily_paid
WITH DATA;
~~~

`WITH DATA` là yêu cầu thực thi truy vấn ngay trong lúc tạo để materialized view có dữ liệu từ đầu.

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.mv_daily_paid
ORDER BY report_date, region;
~~~

Lúc này kết quả giống view thường vì mới vật hóa cùng truy vấn nguồn.

### 6.1. Chỗ nào lưu dữ liệu?

`mv_daily_paid` là một quan hệ vật lý có dữ liệu. PostgreSQL có thể quản lý storage, statistics và index cho quan hệ ấy tương tự những đối tượng chứa dữ liệu khác, nhưng materialized view không phải bảng tùy ý để ứng dụng tự `INSERT`/`UPDATE` dữ liệu.

### 6.2. Materialized view có thể có index

Vì có dữ liệu vật lý, bạn có thể tạo index:

~~~sql
CREATE INDEX idx_mv_daily_paid_date
ON mv_lab.mv_daily_paid (report_date);
~~~

Index này hỗ trợ một số truy vấn lọc ngày nếu planner thấy có lợi. Nó **chưa thỏa điều kiện UNIQUE cho concurrent refresh** vì là index thường.

### 6.3. ORDER BY khi đọc

Ngay cả khi truy vấn định nghĩa materialized view có `ORDER BY`, PostgreSQL **không bảo đảm** mỗi lần đọc sau refresh giữ đúng thứ tự ấy. Muốn kết quả sắp theo ngày/vùng, luôn ghi:

~~~sql
ORDER BY report_date, region
~~~

trong câu SELECT thực tế.

## 7. Thấy dữ liệu cũ sau khi nguồn thay đổi

Chèn thêm một đơn paid vào nhóm ngày 10/1 vùng north:

~~~sql
INSERT INTO mv_lab.orders (
    customer_id, created_at, status, total_amount
) VALUES (
    1,
    '2026-01-10 17:30:00+00',
    'paid',
    30.00
);
~~~

### 7.1. Đọc VIEW thường

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.v_daily_paid
WHERE report_date = DATE '2026-01-10'
  AND region = 'north';
~~~

Trong một snapshot mới sau khi INSERT đã commit, view thường thấy **3 đơn paid, doanh thu 200.00**.

### 7.2. Đọc MATERIALIZED VIEW

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.mv_daily_paid
WHERE report_date = DATE '2026-01-10'
  AND region = 'north';
~~~

Materialized view **vẫn có 2 đơn, doanh thu 170.00** nếu chưa refresh.

### 7.3. Đây không phải lỗi transaction

INSERT đã thành công nhưng materialized view chưa cập nhật là hành vi **đúng thiết kế**. Materialized view không phải trigger tự động nhận mọi thay đổi từ bảng nguồn.

### 7.4. Độ trễ có thể khiến nhiều quyết định sai

Ví dụ:

- Dashboard hiển thị doanh thu ít hơn nguồn.
- API xuất tồn kho dựa trên snapshot cũ dẫn tới quyết định sai.
- Báo cáo số đơn chờ xử lý không phản ánh tình trạng mới.

Độ trễ chỉ chấp nhận được khi sản phẩm **có SLA freshness rõ ràng** và người dùng biết đó là số gần đúng theo thời điểm làm mới.

## 8. REFRESH MATERIALIZED VIEW thông thường

~~~sql
REFRESH MATERIALIZED VIEW mv_lab.mv_daily_paid;
~~~

PostgreSQL chạy lại truy vấn định nghĩa để cập nhật **nội dung được lưu** trong materialized view.

Sau đó:

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.mv_daily_paid
WHERE report_date = DATE '2026-01-10'
  AND region = 'north';
~~~

Kỳ vọng **3 đơn, 200.00** nếu không có thay đổi nguồn khác trong lúc refresh.

### 8.1. REFRESH không phải incremental mặc định

PostgreSQL core không tự biết “chỉ thêm một đơn 30.00” để cộng trực tiếp vào hàng tổng hợp theo cơ chế incremental materialized view maintenance. `REFRESH MATERIALIZED VIEW` về nguyên tắc **thực hiện lại truy vấn định nghĩa** để xây kết quả mới, dù kỹ thuật áp dụng kết quả khi refresh thường hay concurrent có khác nhau.

### 8.2. Thời gian refresh phụ thuộc query nguồn

Nếu `mv_daily_paid` chỉ có 30 hàng nhưng được tính từ 500 triệu đơn, materialized view rất nhỏ vẫn có thể cần đọc và aggregate **lượng dữ liệu nguồn rất lớn** mỗi lần refresh.

### 8.3. Refresh không tự được lên lịch

PostgreSQL không có một lịch tự động mặc định kiểu “cứ mỗi phút refresh tất cả materialized views”. Bạn cần scheduler/automation hoặc cơ chế do hệ thống triển khai, ví dụ job ứng dụng, hệ điều hành hoặc extension phù hợp.

### 8.4. Khi SELECT từ nguồn vẫn cần thiết

Một API yêu cầu dữ liệu vừa được người dùng ghi và xác nhận ngay có thể phải đọc bảng nguồn hoặc một read model đồng bộ phù hợp; không thể ép API ấy đọc materialized view đã cũ chỉ vì SELECT nhanh.

## 9. WITH NO DATA và trạng thái chưa có dữ liệu

Khi tạo materialized view lớn, có thể muốn khai báo đối tượng trước nhưng **chưa chạy truy vấn nguồn**:

~~~sql
CREATE MATERIALIZED VIEW mv_lab.mv_daily_paid_unpopulated AS
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.v_daily_paid
WITH NO DATA;
~~~

### 9.1. Chưa populated không chỉ là một bảng rỗng bình thường

Materialized view tạo với `WITH NO DATA` ở trạng thái **unpopulated / unscannable**. Truy vấn:

~~~sql
-- Minh họa lỗi: view chưa được populate.
SELECT * FROM mv_lab.mv_daily_paid_unpopulated;
~~~

sẽ không đơn giản trả 0 hàng như một bảng rỗng đã hợp lệ; PostgreSQL yêu cầu populate trước khi có thể scan.

### 9.2. Populate lần đầu

~~~sql
REFRESH MATERIALIZED VIEW
    mv_lab.mv_daily_paid_unpopulated;
~~~

Sau khi refresh thành công, materialized view chuyển thành trạng thái populated và có thể SELECT.

### 9.3. REFRESH ... WITH NO DATA

~~~sql
REFRESH MATERIALIZED VIEW
    mv_lab.mv_daily_paid_unpopulated
WITH NO DATA;
~~~

Lệnh này bỏ dữ liệu đang lưu và đánh dấu materialized view **không được populate**, nên không thể SELECT kết quả cho đến khi refresh với data trở lại.

### 9.4. Tạo trước đối tượng không giúp dashboard đọc được

Một pipeline triển khai phải xác định rõ **khi nào materialized view đã được populate và đủ sẵn sàng** để ứng dụng chuyển sang đọc nó. Không chuyển traffic chỉ vì DDL `CREATE MATERIALIZED VIEW ... WITH NO DATA` đã thành công.

## 10. Hai chế độ refresh và hành vi khóa

PostgreSQL có hai lựa chọn thường dùng:

~~~sql
REFRESH MATERIALIZED VIEW mv_lab.mv_daily_paid;
~~~

và:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

Chúng có mục đích giống nhau là cập nhật kết quả vật hóa, nhưng **ảnh hưởng tới người đọc và chi phí thực thi khác nhau**.

| Tiêu chí | REFRESH thường | REFRESH CONCURRENTLY |
| --- | --- | --- |
| Có thể refresh khi chưa populated? | Có, để populate lần đầu | Không |
| Cần UNIQUE index đặc biệt? | Không | Có |
| SELECT song song với refresh | Có thể bị chặn bởi khóa | Có thể tiếp tục SELECT dữ liệu cũ |
| Tác động lên người đọc | Dễ có khoảng chờ | Giảm chặn đọc, nhưng vẫn có tranh chấp tài nguyên/khóa ngắn |
| Chi phí triển khai | Đơn giản hơn | Có thêm yêu cầu và chi phí so khớp thay đổi |
| Luôn nhanh hơn? | Không cam kết | Không; đôi khi chậm hơn |
| Cập nhật tăng dần tự động từ WAL? | Không | Không |

### 10.1. REFRESH thường và ACCESS EXCLUSIVE

Refresh không dùng `CONCURRENTLY` phải giữ khóa có khả năng **chặn SELECT** trên materialized view trong thời gian lệnh chạy. Vì vậy, một dashboard liên tục được đọc có thể gặp latency hoặc timeout khi job refresh kéo dài.

### 10.2. REFRESH CONCURRENTLY và availability

Concurrent refresh được thiết kế để những SELECT phù hợp vẫn có thể dùng materialized view trong lúc refresh. Người đọc có thể nhìn dữ liệu cũ cho tới khi kết quả mới được công bố qua giao dịch.

### 10.3. CONCURRENTLY không có nghĩa hoàn toàn không khóa

Concurrent refresh vẫn dùng lock, transaction và tài nguyên hệ thống; nó có thể cần chờ transaction khác, tạo I/O/WAL và ảnh hưởng tải chung. “Ít chặn đọc” không đồng nghĩa “miễn phí, không khóa”.

### 10.4. Chỉ một refresh cùng lúc cho một materialized view

PostgreSQL không cho nhiều refresh đồng thời chạy thực sự trên **cùng một materialized view**. Khi scheduler kích hoạt chồng lấn, job có thể phải chờ hoặc bị timeout theo cấu hình. Cần có chính sách tránh chạy lại vô hạn.

## 11. Điều kiện UNIQUE index cho CONCURRENTLY

Để dùng:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

materialized view phải:

1. **Đã populated**, không ở trạng thái `WITH NO DATA`.
2. Có **ít nhất một UNIQUE index hợp lệ** trên materialized view.
3. UNIQUE index ấy phải dùng **chỉ tên cột**, không phải index trên biểu thức.
4. UNIQUE index phải bao phủ **mọi hàng**, không phải partial index có `WHERE`.

### 11.1. Tạo UNIQUE index đúng cho báo cáo

Mỗi nhóm nguồn được định nghĩa bởi cặp `(report_date, region)`. Trong lab, `region` luôn `NOT NULL` và mỗi cặp là duy nhất:

~~~sql
CREATE UNIQUE INDEX uq_mv_daily_paid_date_region
ON mv_lab.mv_daily_paid (report_date, region);
~~~

Sau đó:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

là một cách làm hợp lệ về điều kiện UNIQUE index và trạng thái populated của lab.

### 11.2. UNIQUE index không phải chỉ để “tăng tốc”

Trong concurrent refresh, PostgreSQL cần một cách nhận diện các hàng của kết quả hiện tại và mới. UNIQUE index đầy đủ là điều kiện kỹ thuật cho thuật toán refresh concurrent.

### 11.3. UNIQUE index thường không thay việc lập kế hoạch GROUP BY

Nếu query nguồn thực tế có thể sinh nhiều hàng cho cùng cặp `(report_date, region)` do thiết kế sai, xây unique index sẽ gặp lỗi trùng khóa. Index giúp **phát hiện thiết kế không đúng**, không tự “gộp trùng” thành kết quả đúng.

## 12. Những UNIQUE index không đáp ứng điều kiện

### 12.1. Index thường không UNIQUE

~~~sql
CREATE INDEX idx_mv_daily_paid_region
ON mv_lab.mv_daily_paid (region);
~~~

Nó có thể giúp truy vấn vùng nhưng **không đủ** để bật `CONCURRENTLY`.

### 12.2. Partial UNIQUE index

~~~sql
-- Ví dụ minh họa index không đáp ứng yêu cầu
-- toàn bộ các hàng để concurrent refresh:
CREATE UNIQUE INDEX uq_mv_paid_north_only
ON mv_lab.mv_daily_paid (report_date, region)
WHERE region = 'north';
~~~

Index này chỉ bao phủ một phần view; không đáp ứng yêu cầu UNIQUE index toàn bộ hàng của `REFRESH CONCURRENTLY`.

### 12.3. UNIQUE index trên biểu thức

~~~sql
-- Ví dụ không thay thế UNIQUE index đúng yêu cầu:
CREATE UNIQUE INDEX uq_mv_daily_paid_expression
ON mv_lab.mv_daily_paid ((lower(region)), report_date);
~~~

Index này có **biểu thức `lower(region)`**, không chỉ tên cột, nên không đáp ứng điều kiện kỹ thuật của concurrent refresh.

### 12.4. Không cần tạo các index ví dụ trên

Trong lab, chỉ cần index `uq_mv_daily_paid_date_region` đã nêu. Các lệnh minh họa partial/expression ở đây dùng để phân biệt điều kiện; **không nên tạo index thừa khi chưa có query thực tế**.

### 12.5. Cẩn thận với NULL và tính duy nhất

Một UNIQUE index thông thường của PostgreSQL có ngữ nghĩa riêng đối với nhiều giá trị SQL `NULL`. Nếu khóa nhóm có thể chứa NULL, cần kiểm tra đầy đủ ngữ nghĩa uniqueness và cách thuật toán refresh nhận diện hàng; một khóa nhóm **NOT NULL và xác định rõ** thường đơn giản hơn cho materialized view dùng concurrent refresh.

Trong lab, `report_date` được tính từ `created_at NOT NULL`, `region` đến từ cột `NOT NULL`, nên tránh được tình huống này.

## 13. Thử nghiệm REFRESH CONCURRENTLY

Khi materialized view đã có dữ liệu và đã tạo UNIQUE index, chèn một đơn paid mới:

~~~sql
INSERT INTO mv_lab.orders (
    customer_id, created_at, status, total_amount
) VALUES (
    2,
    '2026-01-11 15:00:00+00',
    'paid',
    25.00
);
~~~

### 13.1. Trước refresh

~~~sql
SELECT paid_orders, revenue
FROM mv_lab.v_daily_paid
WHERE report_date = DATE '2026-01-11'
  AND region = 'south';

SELECT paid_orders, revenue
FROM mv_lab.mv_daily_paid
WHERE report_date = DATE '2026-01-11'
  AND region = 'south';
~~~

View thường nhìn thấy giá trị mới; materialized view vẫn chứa kết quả từ lần refresh trước.

### 13.2. Refresh concurrent

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

### 13.3. Sau refresh

~~~sql
SELECT paid_orders, revenue
FROM mv_lab.mv_daily_paid
WHERE report_date = DATE '2026-01-11'
  AND region = 'south';
~~~

Với dữ liệu đã chèn theo thứ tự trong lab và không có thay đổi khác: nhóm này có **2 đơn paid, tổng 95.00**.

### 13.4. CONCURRENTLY không tự làm mới theo từng INSERT

Mỗi lần dữ liệu nguồn thay đổi, materialized view vẫn có thể cũ **cho đến khi một refresh mới chạy và commit**. Từ `CONCURRENTLY` chỉ nói về **cách refresh tương tác với người đọc**, không có nghĩa cập nhật tức thời.

## 14. UPDATE, DELETE và dữ liệu cũ

Không chỉ INSERT gây stale data. Hãy thử trong một transaction có rollback để giữ nguyên dữ liệu lab:

~~~sql
BEGIN;

-- Một đơn paid thay đổi tiền.
UPDATE mv_lab.orders
SET total_amount = 150.00
WHERE order_id = 1;

-- Xóa một đơn đã paid.
DELETE FROM mv_lab.orders
WHERE order_id = 8;

-- View thường phản ánh thay đổi trong transaction này.
SELECT report_date, region, paid_orders, revenue
FROM mv_lab.v_daily_paid
ORDER BY report_date, region;

-- Materialized view vẫn chưa tự thay đổi.
SELECT report_date, region, paid_orders, revenue
FROM mv_lab.mv_daily_paid
ORDER BY report_date, region;

ROLLBACK;
~~~

### 14.1. UPDATE trạng thái còn ảnh hưởng tập kết quả

Nếu một đơn đổi `pending` thành `paid`, nhóm aggregate có thể tăng số lượng và doanh thu. Ngược lại, đổi `paid` thành `cancelled` có thể làm giảm hoặc **biến mất hẳn một nhóm** nếu không còn đơn paid nào.

### 14.2. DELETE không phải chỉ trừ một con số

Một lần xóa có thể làm đổi nhiều aggregate: `COUNT`, `SUM`, `MIN`, `MAX`, `AVG`, số khách duy nhất và các logic có JOIN. Điều này làm thiết kế incremental maintenance tự viết khó hơn nhìn bề ngoài.

### 14.3. Thay đổi bảng JOIN cũng quan trọng

Trong lab, `region` lấy từ bảng `customers`. Nếu khách chuyển từ `north` sang `south`, **báo cáo vùng** có thể thay đổi dù không có đơn hàng mới. Lịch refresh phải tính tới mọi bảng ảnh hưởng query, không chỉ bảng đơn.

## 15. Tác động của khoảng thời gian refresh

Giả sử một job được lên lịch mỗi 5 phút và mất 40 giây để chạy.

~~~text
10:00:00  Bắt đầu refresh A; snapshot nguồn được chọn
10:00:40  A hoàn thành
10:02:00  Một đơn mới COMMIT
10:05:00  Bắt đầu refresh B
10:05:40  B hoàn thành
~~~

Trong khoảng từ 10:02 đến khi B công bố kết quả, dashboard có thể chưa bao gồm đơn mới.

### 15.1. Chu kỳ lịch không bằng SLA freshness

“Refresh mỗi 5 phút” **không bảo đảm mọi dữ liệu trễ tối đa 5 phút**, vì còn:

- Job có thể bắt đầu muộn.
- Job có thể chạy lâu.
- Job có thể lỗi và phải retry.
- Job có thể chờ khóa hoặc resource contention.
- Snapshot nguồn của refresh được xác lập **trước** thời điểm hoàn tất.
- Giao dịch nguồn dài có thể commit sau snapshot.

### 15.2. Định nghĩa freshness theo nghiệp vụ

Ví dụ:

- “Dashboard chấp nhận số liệu chậm tối đa 15 phút trong điều kiện vận hành bình thường.”
- “Sau mỗi refresh thành công, banner hiển thị lần cập nhật gần nhất.”
- “Nếu chưa có refresh thành công trong 30 phút, cảnh báo và ẩn một số hành động dựa trên số liệu.”

SLA nên gắn với **hậu quả kinh doanh của dữ liệu cũ**, không chỉ tần suất scheduler.

### 15.3. Không chọn chu kỳ refresh chỉ vì dễ cấu hình

Refresh mỗi phút có thể quá nặng nếu truy vấn tổng hợp toàn bộ lịch sử mất 50 giây và hệ thống nguồn bận. Refresh mỗi giờ có thể quá thưa nếu dashboard vận hành cần kiểm tra các đơn đang xử lý. Cần đo query nguồn và thu thập yêu cầu người dùng.

## 16. Chi phí của một lần REFRESH

Một materialized view có ít hàng không đồng nghĩa lần refresh rẻ.

### 16.1. Đọc dữ liệu nguồn

PostgreSQL phải thực thi truy vấn định nghĩa. Nếu query aggregate toàn bộ hàng paid từ đầu lịch sử, mỗi refresh có thể phải:

1. Đọc một lượng lớn hàng nguồn.
2. JOIN với bảng khách hàng hoặc bảng liên quan.
3. Lọc trạng thái.
4. GROUP BY và tính aggregate.
5. Tạo hoặc cập nhật dữ liệu vật hóa theo cơ chế refresh.
6. Duy trì indexes tương ứng.

### 16.2. CPU và memory

Sort, hash aggregate, hash join và xử lý biểu thức đều có chi phí. Nếu thiếu `work_mem` cho các node thích hợp, một số thao tác có thể spill ra temporary storage.

### 16.3. I/O và WAL

Thay đổi dữ liệu vật hóa và indexes có thể tạo I/O/WAL đáng kể. Trên hệ thống có replication, WAL volume có thể ảnh hưởng độ trễ replica.

### 16.4. Tranh chấp với workload ghi

Một refresh lớn làm tăng lưu lượng đọc, áp lực cache và tài nguyên, ảnh hưởng các câu INSERT/UPDATE sản xuất ngay cả khi dùng `CONCURRENTLY`.

### 16.5. Chi phí storage

Materialized view lưu dữ liệu riêng và indexes riêng; nếu có nhiều bản materialized view gần giống nhau, storage và maintenance có thể bị nhân lên.

## 17. Vì sao CONCURRENTLY đôi khi chậm hơn REFRESH thường?

Refresh concurrent có nhiệm vụ cập nhật mà không chặn SELECT dài như refresh thường. Nó cần cơ chế xác định khác biệt giữa dữ liệu mới và nội dung hiện có, với các index/ràng buộc tương ứng.

### 17.1. Không phải chỉ áp vài thay đổi từ WAL

`CONCURRENTLY` trong PostgreSQL core **không đồng nghĩa incremental view maintenance** đọc một danh sách đơn đã thêm và cộng delta tương ứng. Query định nghĩa vẫn phải được tính lại để tạo bộ kết quả mới cần so khớp.

### 17.2. Đổi lấy khả năng phục vụ đọc

Với dashboard rất nhiều người đọc, giảm chặn SELECT có thể đáng giá hơn việc refresh nhanh hơn vài giây. Ngược lại, một materialized view chỉ dùng cho job chạy ban đêm có thể phù hợp refresh thường đơn giản hơn.

### 17.3. Dữ liệu thay đổi nhiều hay ít cũng ảnh hưởng

Khi gần như mọi hàng tổng hợp đổi sau một đợt ghi lớn, lợi ích từ việc xử lý theo khác biệt có thể thấp. Khi kết quả thay đổi ít, chi phí so khớp vẫn tồn tại và không có bảo đảm một chế độ luôn vượt trội.

### 17.4. Đo cả khả năng phục vụ người đọc

Benchmark cần xem:

- Tổng thời gian refresh.
- Thời gian các SELECT phải chờ lock.
- Latency dashboard p95/p99 khi refresh.
- CPU, I/O, WAL, temp files.
- Dung lượng và chi phí index.

Nếu chỉ đo thời gian refresh riêng lẻ, bạn có thể bỏ qua mục tiêu quan trọng nhất của `CONCURRENTLY` là giảm gián đoạn đọc.

## 18. Theo dõi trạng thái materialized view

PostgreSQL có view hệ thống `pg_matviews`:

~~~sql
SELECT
    schemaname,
    matviewname,
    matviewowner,
    ispopulated,
    hasindexes,
    definition
FROM pg_matviews
WHERE schemaname = 'mv_lab'
ORDER BY matviewname;
~~~

### 18.1. ispopulated

`ispopulated` cho biết materialized view đã có trạng thái có thể scan hay chưa. Nó **không nói dữ liệu mới đến mức nào**.

### 18.2. hasindexes

`hasindexes` cho biết có index, **không khẳng định có UNIQUE index phù hợp với `CONCURRENTLY`**.

### 18.3. definition

`definition` giúp xem SQL nguồn. Cần xác nhận query có bộ lọc, JOIN và logic thời gian đúng trước khi quyết định lịch refresh.

### 18.4. PostgreSQL không cung cấp sẵn last_refresh_at đáng tin cậy cho mọi MV

`pg_matviews` không phải nhật ký lịch refresh đầy đủ. Muốn biết refresh gần nhất thành công khi nào, cần **ghi log/metrics trong cơ chế vận hành của bạn** hoặc sử dụng hệ thống monitoring phù hợp.

## 19. Tạo bảng log riêng cho refresh

Để theo dõi lịch sử các lần refresh thành công:

~~~sql
CREATE TABLE mv_lab.refresh_log (
    refresh_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    matview_name text NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    refresh_mode text NOT NULL
        CHECK (refresh_mode IN ('blocking', 'concurrent')),
    note text
);
~~~

### 19.1. Ghi thành công trong cùng transaction

Ví dụ lab sau dùng refresh thường:

~~~sql
BEGIN;

REFRESH MATERIALIZED VIEW mv_lab.mv_daily_paid;

INSERT INTO mv_lab.refresh_log (
    matview_name, finished_at, refresh_mode, note
) VALUES (
    'mv_lab.mv_daily_paid',
    clock_timestamp(),
    'blocking',
    'Refresh completed inside transaction'
);

COMMIT;
~~~

Do refresh và log nằm trong cùng transaction, khi `COMMIT` thành công, các thay đổi đều được công bố phù hợp với giao dịch. Nếu refresh thất bại, transaction cần rollback và không ghi một thành công giả.

### 19.2. finished_at không nhất thiết là nguồn snapshot cutoff

`finished_at` ở ví dụ là thời điểm ghi log sau khi lệnh refresh hoàn tất trong transaction, **không nhất thiết trùng** thời điểm snapshot nguồn được lấy. Nó hữu ích để đo trạng thái vận hành, nhưng không thay thế source watermark.

### 19.3. Nếu log nằm ngoài transaction

Nếu scheduler chỉ ghi log **sau** khi lệnh refresh commit, có thể có khoảng nhỏ giữa hai thao tác hoặc một lỗi ghi log. Phải phân biệt trạng thái **refresh thực tế** và **số liệu quan sát**, đồng thời có cách retry/reconcile.

### 19.4. Ghi lỗi ở đâu?

Nếu refresh lỗi, không thể ghi một dòng failure trong cùng transaction đang aborted. Scheduler/worker phải rollback rồi ghi lỗi qua một giao dịch hoặc hệ thống logging khác, bảo đảm biết rõ job thất bại và không cập nhật mốc thành công.

## 20. Tính tuổi lần refresh thành công

~~~sql
SELECT
    matview_name,
    MAX(finished_at) AS last_successful_refresh,
    EXTRACT(
        EPOCH FROM (
            clock_timestamp() - MAX(finished_at)
        )
    ) AS seconds_since_success
FROM mv_lab.refresh_log
WHERE matview_name = 'mv_lab.mv_daily_paid'
GROUP BY matview_name;
~~~

### 20.1. Không có log là trạng thái cần xử lý

Nếu chưa có dòng log, query trên có thể không trả dòng nào. Dashboard vận hành phải biểu diễn rõ **“chưa biết/chưa có lần refresh thành công được ghi nhận”**; không mặc định độ trễ bằng 0.

### 20.2. Thời gian tuổi không phải số đơn chưa đồng bộ

`seconds_since_success` là số giây từ mốc log, không cho biết có bao nhiêu thay đổi chưa được đưa vào materialized view. Nếu nguồn không đổi, dữ liệu có thể vẫn chính xác dù mốc refresh đã cũ. Nếu nguồn thay đổi rất nhanh, một refresh vừa xong cũng có thể đã trễ một số commit.

### 20.3. Gắn nhãn cho người dùng

Ví dụ dashboard hiển thị:

~~~text
Doanh thu theo ngày — số liệu được làm mới lúc 10:05:40 UTC
Nguồn đơn hàng có thể đã thay đổi sau thời điểm xử lý.
~~~

Lưu ý timezone của thời gian hiển thị phải phù hợp người dùng; tránh cho họ hiểu một timestamp UTC là giờ địa phương.

## 21. Source watermark và freshness thực

Một báo cáo tổng hợp có thể cần định nghĩa **nguồn đã được xử lý đến mốc nào** thay vì chỉ dựa vào thời gian job kết thúc.

### 21.1. Không dùng MAX(created_at) làm refresh timestamp

Trong lab có cột:

~~~sql
MAX(o.created_at) AS latest_paid_order_at
~~~

Nó là **thời điểm tạo đơn paid mới nhất trong từng nhóm**. Không có lý do gì nó phải bằng thời điểm refresh. Một tài liệu nhập muộn với `created_at` cũ cũng có thể làm thay đổi doanh thu tháng trước.

### 21.2. Bảng nguồn cần cơ chế theo dõi thay đổi

Một hệ thống có thể dùng:

- `updated_at` được quản lý nhất quán.
- Sequence hoặc event offset trong luồng thay đổi.
- CDC/WAL-based processing phù hợp.
- Mốc hoàn tất batch ingestion.
- Job ID/partition ID đã được xác minh.

Nhưng phải cân nhắc **UPDATE/DELETE và thay đổi bảng JOIN**. `MAX(created_at)` của orders không phát hiện khách đổi vùng hay một đơn cũ bị hoàn tiền.

### 21.3. updated_at cũng không giải quyết mọi thứ tự động

Một hàng bị DELETE không còn để truy vấn `MAX(updated_at)`. Nếu timestamp do ứng dụng tự đặt không đồng bộ hoặc giao dịch commit khác thứ tự timestamp, watermark có thể thiếu thay đổi. Cần thiết kế audit/change log hoặc cơ chế đồng bộ tương ứng với SLA.

### 21.4. Định nghĩa “fresh” phải kiểm chứng được

Nếu SLO là “mọi thay đổi đã commit trước T phải có trong báo cáo”, kiến trúc cần một **nguồn thứ tự thay đổi** và cơ chế xác nhận xử lý tới T. Một mốc log refresh đơn thuần thường chưa đủ để chứng minh điều đó.

## 22. Lịch refresh và vận hành định kỳ

Giả sử nhóm vận hành chấp nhận báo cáo trễ tối đa khoảng 15 phút trong điều kiện bình thường, và refresh bình quân mất 1–2 phút.

Một lịch thô có thể bắt đầu ở khoảng 5 phút, nhưng phải kiểm tra:

1. Tỉ lệ job hoàn thành đúng hạn.
2. P95/p99 thời gian refresh, không chỉ trung bình.
3. Thời gian xếp hàng/chờ khóa.
4. Tần suất job thất bại, chính sách retry.
5. Tải CPU/I/O của primary database.
6. Mức ảnh hưởng tới các query giao dịch.

### 22.1. Ví dụ scheduler bên ngoài

Một job có thể thực thi:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

đúng theo lịch và ghi metadata kết quả. Scheduler có thể nằm trong job ứng dụng, công cụ orchestration, hệ điều hành hoặc một extension được cài và cấu hình riêng.

### 22.2. Không giả định pg_cron có sẵn

`pg_cron` là extension có thể hỗ trợ scheduling trong một số môi trường PostgreSQL, nhưng **không phải lúc nào cũng được cài, bật hoặc cấp quyền**. Nếu muốn dùng, cần kiểm tra tài liệu của phiên bản/nhà cung cấp và chính sách vận hành.

### 22.3. Scheduler phải xử lý job trùng

Nếu lịch 5 phút nhưng một refresh mất 8 phút, đợt tiếp theo có thể chồng lên đợt cũ. Nên có cơ chế skip, queue hoặc lock điều phối và cảnh báo, thay vì để nhiều worker chờ dây chuyền.

### 22.4. Retry phải có giới hạn

Retry liên tục khi database quá tải có thể làm sự cố nặng hơn. Thiết kế backoff, số lần thử, timeout và cơ chế chuyển báo cáo sang trạng thái degraded/stale.

### 22.5. Thông báo cho người tiêu thụ

Nếu báo cáo quá hạn, API/UI nên hiển thị mốc refresh và cảnh báo thay vì lặng lẽ trình bày số liệu cũ như dữ liệu thời gian thực.

## 23. Điều phối tránh refresh chồng lấn

PostgreSQL vốn ngăn nhiều refresh đồng thời trên cùng materialized view, nhưng scheduler vẫn cần tránh **xếp hàng quá nhiều job**.

### 23.1. Một worker cho mỗi materialized view

Cách đơn giản nhất là tạo một hàng đợi hoặc job đơn luồng:

~~~text
Trigger lịch 10:00
      |
      v
Nếu job đang chạy?
      +-- Có  -> bỏ qua lượt này / đánh dấu trễ
      +-- Không -> bắt đầu REFRESH
                        |
                        v
                  ghi kết quả
~~~

### 23.2. Advisory lock có thể hỗ trợ

Trong một số kiến trúc, scheduler dùng PostgreSQL advisory locks để điều phối. Chú ý advisory lock là công cụ **tự nguyện** giữa các worker dùng cùng quy ước khóa; nó không thay thế khóa nội bộ của `REFRESH`, quyền truy cập hay transaction semantics.

### 23.3. Chọn key và phạm vi khóa

Nếu dùng advisory lock, cần quy định rõ lock key theo materialized view, loại session-level/transaction-level lock, phương án giải phóng khi worker lỗi và monitoring. Không dùng một khóa chung cho mọi materialized view nếu không có lý do.

### 23.4. Không refresh không giới hạn trong request HTTP

Một nút “Làm mới ngay” không nên tùy tiện cho hàng nghìn người gọi trực tiếp `REFRESH`. Thường tốt hơn là tạo yêu cầu cho scheduler, rate limit và trả trạng thái tiến độ/hạn mức.

## 24. Đo chi phí đọc nguồn và đọc materialized view

Trước khi tạo materialized view, nên xem chi phí query nguồn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.v_daily_paid
WHERE report_date BETWEEN DATE '2026-01-10'
                      AND DATE '2026-01-12';
~~~

Sau đó so với:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.mv_daily_paid
WHERE report_date BETWEEN DATE '2026-01-10'
                      AND DATE '2026-01-12';
~~~

### 24.1. Hai kế hoạch có thể rất khác

- View thường có thể có scan `orders`, JOIN `customers` và aggregate.
- Materialized view có thể chỉ scan một quan hệ nhỏ hoặc dùng index theo `report_date`.

### 24.2. Bảng lab quá nhỏ để benchmark

Tám đến mười đơn không đủ thể hiện lợi ích khi nguồn có hàng triệu dòng. PostgreSQL có thể chọn `Seq Scan` cho cả hai truy vấn và thời gian tương đương. Mục tiêu lab là **quan sát ngữ nghĩa**, không chứng minh mức tăng tốc thực tế.

### 24.3. Đo cả workload refresh

Nếu 100 người dùng đọc mỗi phút, materialized view giúp tiết kiệm nhiều lần aggregate. Nhưng nếu mỗi phút bạn refresh lại toàn bộ hàng trăm triệu đơn, tải nền có thể rất lớn. Phải đo tổng chi phí:

\[
\text{Tổng tải} \approx
(\text{lượt đọc}\times\text{chi phí mỗi đọc})
+(\text{số refresh}\times\text{chi phí mỗi refresh})
\]

Đây là mô hình tư duy đơn giản, không phải công thức chính xác cho CPU/I/O khi concurrency, caching và replication tham gia.

## 25. Những chỉ số nên đo với EXPLAIN

| Chỉ số | Giá trị khi đánh giá |
| --- | --- |
| `Execution Time` | Thời gian thực thi server của SELECT |
| `Planning Time` | Chi phí xây plan |
| `Seq Scan`/`Index Scan` | Cách truy cập nguồn/materialized view |
| `HashAggregate`/`GroupAggregate` | Chi phí tổng hợp của view thường |
| `Hash Join`/`Nested Loop` | Cách JOIN các bảng nguồn |
| `actual rows`, `loops` | Khối lượng dữ liệu ở từng node |
| `Buffers: shared hit/read` | Footprint truy cập block |
| `Sort`, `Sort Method` | Có sort, có spill hay không |
| `temp read/written` | I/O cho dữ liệu tạm, nếu có |

### 25.1. Không coi Buffers là số hàng

`shared hit=1000` không nghĩa có đúng 1.000 dòng được đọc; một block chứa nhiều rows và có thể được chạm nhiều lần.

### 25.2. Không cộng Buffers qua tất cả node

Một số thống kê `BUFFERS` trên node cha bao gồm cả hoạt động từ node con. Cộng chúng như các số độc lập có thể đếm trùng.

### 25.3. Query latency khác dashboard latency

Dashboard còn có network, driver, serialization, authentication và render. Một query nhanh trên server chưa chắc end-to-end đáp ứng yêu cầu nếu tải lớn hoặc payload rộng.

### 25.4. Kiểm tra actual vs estimated

Nếu planner ước lượng số hàng rất sai, có thể dẫn tới chọn scan/join/sort không hợp lý. Chạy `ANALYZE` trên nguồn và materialized view khi thích hợp; đừng chỉ tạo index.

## 26. Index materialized view theo truy vấn đọc

Giả sử dashboard lọc theo khoảng ngày và vùng:

~~~sql
SELECT report_date, region, paid_orders, revenue
FROM mv_lab.mv_daily_paid
WHERE region = 'north'
  AND report_date >= DATE '2026-01-01'
ORDER BY report_date DESC;
~~~

Một index có thể cân nhắc:

~~~sql
CREATE INDEX idx_mv_daily_paid_region_date
ON mv_lab.mv_daily_paid (region, report_date DESC);
~~~

### 26.1. UNIQUE index và read index có thể khác mục tiêu

`UNIQUE(report_date, region)` cần cho concurrent refresh, có thể hỗ trợ một số query lọc ngày. Nhưng query chủ yếu lọc `region` trước rồi sort ngày có thể hưởng lợi từ index `(region, report_date DESC)`.

### 26.2. Không tạo index nếu materialized view quá nhỏ

Một materialized view chỉ vài chục dòng thường nhanh ngay cả khi Seq Scan. Index tăng chi phí refresh/storage; lợi ích phải được đo.

### 26.3. Index theo số liệu aggregate

Nếu dashboard thường tìm “các ngày doanh thu cao nhất”, index trên `revenue DESC` có thể hữu ích trong một số truy vấn. Nhưng index phục vụ ORDER BY/LIMIT và các điều kiện lọc khác cần được đánh giá theo workload thật.

### 26.4. Đừng quên quyền và dữ liệu nhạy cảm

Index không phải bảo vệ quyền truy cập. Materialized view lưu một bản sao dữ liệu; nếu chứa thông tin khách hàng hoặc doanh thu nhạy cảm, cần kiểm soát quyền `SELECT` và chu kỳ xóa lưu giữ phù hợp.

## 27. Chỉ mục ở bảng nguồn ảnh hưởng chi phí REFRESH

Materialized view đọc nhanh nhưng refresh phải chạy query nguồn. Vì vậy indexes trên nguồn vẫn có vai trò.

~~~sql
CREATE INDEX idx_orders_paid_created
ON mv_lab.orders (created_at)
WHERE status = 'paid';
~~~

### 27.1. Khi index nguồn có thể hữu ích

Một query nguồn chỉ tính các đơn paid trong 7 ngày gần đây có điều kiện thời gian chọn lọc có thể tận dụng index phù hợp.

### 27.2. Khi index chưa chắc giúp

Nếu query của materialized view tổng hợp **mọi đơn paid từ trước tới nay**, và paid chiếm phần lớn bảng, PostgreSQL có thể chọn Seq Scan trên nguồn vì đọc tuần tự rẻ hơn đi qua index rồi nhiều heap fetches.

### 27.3. Partition pruning

Với bảng nguồn được partition theo ngày và truy vấn refresh chỉ cần dữ liệu trong một cửa sổ xác định, predicate trên partition key có thể loại nhiều partition. Nhưng nếu materialized view tổng hợp toàn bộ lịch sử, partition pruning theo cửa sổ không tự xuất hiện.

### 27.4. Không thêm điều kiện thời gian nếu làm sai báo cáo

Nếu người dùng cần tổng doanh thu **toàn bộ lịch sử**, không tự giới hạn `WHERE created_at >= now()-interval '30 days'` chỉ để refresh nhanh hơn mà không đổi định nghĩa báo cáo.

## 28. ANALYZE và thống kê sau REFRESH

PostgreSQL planner cần statistics để ước lượng selectivity và chọn index.

~~~sql
ANALYZE mv_lab.mv_daily_paid;
~~~

### 28.1. REFRESH và statistics là hai công việc khác nhau

Đừng mặc định `REFRESH MATERIALIZED VIEW` luôn lập tức cập nhật mọi thống kê planner tương đương `ANALYZE`. Với những lần thay đổi kích thước/phân bố lớn, chạy `ANALYZE` theo chính sách vận hành.

### 28.2. Xem kích thước vật lý

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('mv_lab.mv_daily_paid'::regclass)
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('mv_lab.mv_daily_paid'::regclass)
    ) AS index_size,
    pg_size_pretty(
        pg_total_relation_size('mv_lab.mv_daily_paid'::regclass)
    ) AS total_size;
~~~

### 28.3. MV có thể tốn hơn mong muốn

Nếu materialized view lưu cả dữ liệu raw JSON hoặc trường text rất rộng thay vì chỉ lưu aggregate đủ dùng, kích thước và chi phí refresh sẽ tăng. Chọn projection cẩn thận.

### 28.4. Thống kê ở nguồn

~~~sql
ANALYZE mv_lab.orders;
ANALYZE mv_lab.customers;
~~~

giúp planner tối ưu query nguồn, nhưng không thay việc lựa chọn lịch refresh phù hợp.

## 29. Thống kê hoạt động và monitoring

Một số catalog/statistics views có thể giúp quan sát:

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'mv_lab'
ORDER BY relname;
~~~

### 29.1. Không dùng last_analyze làm last_refresh

`last_analyze` là lần thống kê được cập nhật, **không phải** lần materialized view refresh. Không lấy chỉ số ấy làm mốc freshness.

### 29.2. Có thể quan sát khóa và query đang chạy

Nếu có quyền phù hợp, `pg_stat_activity`/`pg_locks` hỗ trợ điều tra một refresh đang chờ hoặc đang chặn SELECT:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start,
    left(query, 180) AS query_prefix
FROM pg_stat_activity
WHERE query ILIKE '%REFRESH MATERIALIZED VIEW%'
ORDER BY query_start;
~~~

Kết quả có thể gồm chính câu SQL truy vấn monitoring; nên lọc/diễn giải theo ngữ cảnh, tránh xem chuỗi match là chứng cứ tuyệt đối có job refresh đang chạy.

### 29.3. Không đo polling quá dày

Monitoring nên đủ để phát hiện job chậm, lỗi và quá hạn mà không tạo hàng nghìn truy vấn thống kê mỗi giây. Nếu số lượng materialized views lớn, tập trung vào metric của scheduler/observability phù hợp.

## 30. Thiết kế refresh theo cửa sổ dữ liệu

Một tối ưu thường được đề xuất là chỉ lưu 30 ngày gần nhất:

~~~sql
CREATE MATERIALIZED VIEW mv_lab.mv_paid_last_30_days AS
SELECT
    (o.created_at AT TIME ZONE 'UTC')::date AS report_date,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS revenue
FROM mv_lab.orders AS o
WHERE o.status = 'paid'
  AND o.created_at >= clock_timestamp()
                      - INTERVAL '30 days'
GROUP BY (o.created_at AT TIME ZONE 'UTC')::date
WITH DATA;
~~~

### 30.1. Cửa sổ động thay đổi theo mỗi refresh

Ngưỡng “30 ngày trước hiện tại” được đánh giá khi truy vấn refresh thực thi. Kết quả vật hóa có thể chứa nhóm/hàng đã ra khỏi cửa sổ khi thời gian trôi qua, **cho tới lần refresh sau**.

### 30.2. Không phải index trên cửa sổ cố định

Một materialized view cửa sổ động không phải đồng nghĩa bảng nguồn được tự partition/prune theo logic thời gian khi mọi query dùng nó. Refresh vẫn phải thực thi query có predicate, và khả năng dùng index phụ thuộc kiểu predicate và dữ liệu.

### 30.3. 30 ngày rolling khác “30 ngày lịch”

`clock_timestamp() - interval '30 days'` diễn đạt khoảng 30 ngày tương đối tới thời điểm thực thi, không nhất thiết tương đương 30 ngày lịch UTC hoàn chỉnh. Nếu báo cáo theo ngày, nên làm rõ ranh giới ngày/tháng và timezone.

### 30.4. Mối nguy từ thời gian không ổn định trong query

`clock_timestamp()` có thể thay đổi trong một câu truy vấn đang chạy. Nếu cần một ranh giới thống nhất cho cả lần refresh, nên sử dụng mốc thời gian ổn định trong statement hoặc thiết kế một cut-off được kiểm soát rõ ở tầng orchestration. Bài này dùng ví dụ để phân biệt **cửa sổ động và thời điểm refresh**, không khuyến nghị dùng nó bừa bãi cho báo cáo tài chính.

### 30.5. Cân nhắc thiết kế partition/batch thay vì cửa sổ động

Với báo cáo lịch sử lớn, có thể chia dữ liệu theo ngày/tháng, cập nhật phần mới và khóa các giai đoạn đã chốt theo chính sách nghiệp vụ. Đây là một bài toán kiến trúc tổng hợp riêng, không được PostgreSQL core giải quyết tự động chỉ bằng câu `REFRESH`.

## 31. Truy vấn dữ liệu mới và cũ cùng lúc

Đôi khi dashboard cần:

- Dữ liệu lịch sử tổng hợp nhanh từ materialized view.
- Dữ liệu vài phút mới nhất đọc trực tiếp từ bảng nguồn.

Một kiến trúc **hybrid** có thể phân tách:

~~~text
Lịch sử đã chốt / tính sẵn -> materialized view
Vùng dữ liệu mới            -> live aggregate
                               |
                               v
                           hợp nhất kết quả
~~~

### 31.1. Phải tránh đếm trùng

Nếu materialized view đã bao gồm một phần ngày hiện tại rồi query live cũng tổng hợp toàn bộ ngày hiện tại, một phép `UNION ALL` đơn giản có thể **đếm trùng doanh thu**.

### 31.2. Cần ranh giới dữ liệu xác định

Một cách có thể dùng là materialize dữ liệu tới một **cutoff/batch watermark** đã xác nhận, còn truy vấn live chỉ lấy dữ liệu sau cutoff ấy. Việc này phải xét cập nhật/hủy đơn cũ và giao dịch đến muộn.

### 31.3. Late-arriving changes phá giả định “lịch sử bất biến”

Đơn tạo tháng trước nhưng hôm nay mới bị hủy/được hoàn tiền sẽ ảnh hưởng aggregate lịch sử. Nếu hệ thống cho phép thay đổi quá khứ, chiến lược “chỉ tính delta từ ngày hôm nay” là không đầy đủ.

### 31.4. Không xây hybrid chỉ để tránh refresh nếu nghiệp vụ đơn giản

Hợp nhất hai nguồn tăng độ phức tạp, kiểm thử và rủi ro số liệu sai. Nếu báo cáo chấp nhận trễ 10 phút, một MV refresh định kỳ có thể đơn giản hơn nhiều.

## 32. Incremental summary table: một phương án khác

Một số hệ thống duy trì **bảng tổng hợp** và cập nhật theo sự kiện/transaction thay vì chạy lại toàn bộ query.

Ví dụ bảng:

~~~sql
CREATE TABLE mv_lab.daily_paid_summary (
    report_date date NOT NULL,
    region text NOT NULL,
    paid_orders bigint NOT NULL,
    revenue numeric(14, 2) NOT NULL,
    PRIMARY KEY (report_date, region)
);
~~~

### 32.1. Có thể cập nhật tăng dần bằng UPSERT

Một sự kiện xác nhận đơn paid mới có thể làm tăng tổng của đúng nhóm:

~~~sql
INSERT INTO mv_lab.daily_paid_summary (
    report_date, region, paid_orders, revenue
) VALUES (
    DATE '2026-01-10',
    'north',
    1,
    30.00
)
ON CONFLICT (report_date, region)
DO UPDATE SET
    paid_orders = mv_lab.daily_paid_summary.paid_orders
                  + EXCLUDED.paid_orders,
    revenue = mv_lab.daily_paid_summary.revenue
              + EXCLUDED.revenue;
~~~

### 32.2. Đây chỉ là minh họa, chưa phải pipeline đủ an toàn

Nếu sự kiện được xử lý lặp, ví dụ retry cùng một đơn, bộ tổng có thể **cộng hai lần**. Nếu đơn bị hủy hoặc giá trị sửa, cần tính delta âm/dương và xử lý chuyển nhóm. Hệ thống cần idempotency, source-of-truth, transaction boundaries và cơ chế reconcile.

### 32.3. MAX/MIN/COUNT DISTINCT khó cập nhật hơn SUM

Với `SUM`/`COUNT` đơn giản, delta có thể dễ tính khi biết old/new state. Nhưng nếu xóa phần tử đang là `MAX`, phải tìm giá trị mới; `COUNT(DISTINCT)` cần quản lý tập các giá trị. Incremental maintenance không phải lúc nào cũng dễ.

### 32.4. Ưu/nhược điểm

| Cách | Ưu điểm | Rủi ro/chi phí |
| --- | --- | --- |
| Materialized view refresh full | Đơn giản về logic, tính lại từ nguồn | Refresh đắt, stale |
| Bảng tổng hợp incremental | Có thể gần thời gian thực và ít tính lại | Đồng bộ/đếm trùng/delta/khôi phục phức tạp |
| VIEW thường | Mới theo query snapshot, ít pipeline | Mỗi query có thể phải tính lại |
| Cache ngoài DB | Giảm đọc DB, TTL linh hoạt | Invalidation, consistency, deployment |

### 32.5. Materialized view PostgreSQL core khác extension incremental

Một số extension/giải pháp bên ngoài có khả năng incremental view maintenance, nhưng **không phải cú pháp REFRESH core tự động hỗ trợ mọi chiến lược incremental**. Không dựa vào extension chưa cài/quyền chưa cấp trong thiết kế mặc định.

## 33. Read replicas và freshness nhiều tầng

Một kiến trúc có thể gồm primary database, streaming replica và materialized view.

~~~text
Primary: đơn hàng mới COMMIT
            |
            v
Replication lag
            |
            v
Replica: dữ liệu nguồn có thể trễ
            |
            v
Materialized view: snapshot từ lần refresh
            |
            v
Dashboard
~~~

### 33.1. Staleness có thể cộng dồn

Nếu báo cáo được refresh dựa trên một nguồn đã có replication lag, cộng thêm khoảng cách lịch refresh, kết quả có thể trễ nhiều tầng. Một thiết kế production phải biết **refresh chạy ở đâu và lấy dữ liệu từ đâu**.

### 33.2. Không mặc định refresh trên standby

Khả năng chạy DDL/DML trên standby PostgreSQL bị giới hạn theo chế độ read-only. Không giả định có thể tự `REFRESH MATERIALIZED VIEW` trên mọi read replica. Cần kiểm tra topology và nơi có quyền ghi.

### 33.3. Đọc từ replica cũng cần SLA

Ngay cả khi materialized view trên primary vừa refresh, ứng dụng đọc một replica còn lag có thể vẫn nhìn phiên bản cũ. Đo replication lag và khả năng đọc nhất quán theo yêu cầu.

## 34. Snapshot của refresh và giao dịch đồng thời

Materialized view được xây từ một **snapshot hợp lệ** của truy vấn nguồn theo semantics giao dịch PostgreSQL.

### 34.1. Hai transaction nguồn

Giả sử:

~~~text
T1: INSERT đơn A, chưa COMMIT
T2: REFRESH materialized view, chọn snapshot
T1: COMMIT đơn A
T2: hoàn thành refresh
~~~

Kết quả refresh của T2 **không buộc phải có đơn A** vì tại thời điểm snapshot thích hợp, A chưa được commit và nhìn thấy.

### 34.2. Không có “nửa đơn”

Nếu một transaction nguồn thay đổi nhiều bảng theo cách nguyên tử, query refresh theo snapshot sẽ thấy trạng thái phù hợp với các quy tắc MVCC; nó không nên đọc một nửa transaction đã commit trong điều kiện thông thường.

### 34.3. Một người dùng đang giữ transaction dài

Đọc materialized view trong transaction với isolation cao hơn có thể tiếp tục nhìn một snapshot cũ theo quy tắc transaction isolation, dù refresh khác đã commit. Không coi thời điểm commit refresh là bảo đảm **mọi connection đang mở lập tức quan sát dữ liệu mới** trong mọi isolation level.

### 34.4. Freshness là cam kết ở cả ứng dụng

Nếu API cần “đọc lại ngay sau khi tôi vừa ghi”, đọc materialized view không có cơ chế chờ/synchronization thích hợp sẽ phá kỳ vọng *read-your-writes*. Cần chọn nguồn đọc hoặc trình bày độ trễ đúng.

## 35. Khi nào không nên dùng materialized view?

### 35.1. Quyết định tiền/tồn kho theo thời gian thực

Tồn kho để chấp nhận một giao dịch mới hoặc số dư cần kiểm soát ràng buộc giao dịch không nên dựa chỉ vào một aggregate có thể stale. Dùng bảng nguồn và transaction/locking phù hợp với tính đúng.

### 35.2. Dữ liệu thay đổi cực nhanh nhưng SLA gần bằng 0

Nếu cần mọi commit vừa ghi xuất hiện ngay lập tức, refresh định kỳ không đáp ứng được nếu thiếu thiết kế đồng bộ phức tạp; một read model incremental hoặc query trực tiếp có thể hợp lý hơn.

### 35.3. Query nguồn rẻ và ít được gọi

Nếu một báo cáo chạy một lần mỗi tuần, dữ liệu chỉ vài nghìn hàng và query nguồn mất vài chục ms, tạo một materialized view/cron/monitoring có thể làm vận hành phức tạp không cần thiết.

### 35.4. Kết quả thay đổi theo từng user/permission

Materialized view lưu một tập kết quả dùng chung theo câu SELECT nguồn. Nếu ứng dụng cần những phép lọc bảo mật phụ thuộc từng người dùng hoặc tenant, phải thiết kế quyền, predicate và phân vùng dữ liệu tương ứng. Không tạo một bản sao toàn hệ thống rồi cấp quyền SELECT rộng để “tăng tốc”.

### 35.5. Kết quả quá lớn hoặc refresh không đủ cửa sổ

Nếu materialized view chứa gần như mọi hàng raw và refresh mất lâu hơn lịch dự kiến, chi phí có thể lớn hơn lợi ích. Cần đánh giá index trên nguồn, partitioning, cách tổng hợp và phương án incremental.

## 36. Quản lý quyền với materialized view

Materialized view là một đối tượng database có quyền sở hữu và quyền truy cập riêng.

### 36.1. Quyền đọc không đồng nhất quyền đọc bảng nguồn

Người có quyền `SELECT` trên materialized view có thể đọc dữ liệu đã vật hóa theo các quyền của đối tượng đó, ngay cả khi ứng dụng không cấp cùng quyền trên toàn bộ bảng nguồn. Vì vậy materialized view có thể trở thành **bản sao dữ liệu nhạy cảm** cần quản lý.

### 36.2. Quyền REFRESH

Lệnh `REFRESH MATERIALIZED VIEW` có các yêu cầu quyền/ownership phù hợp phiên bản PostgreSQL. Không trao quyền làm mới hoặc quyền sở hữu rộng cho tài khoản dashboard chỉ cần SELECT.

### 36.3. Khi dữ liệu nguồn bị xóa

Nếu một hàng nguồn bị xóa để tuân thủ yêu cầu privacy, nội dung materialized view có thể vẫn chứa thông tin tổng hợp hoặc dữ liệu sao chép của hàng ấy cho tới refresh. Nếu yêu cầu xóa có SLA nghiêm ngặt, phải tính cả materialized view và các bản sao/cache khác.

### 36.4. Row Level Security cần đánh giá riêng

RLS trên bảng nguồn không được coi là bảo đảm rằng mọi người đọc materialized view tự động được lọc đúng theo quyền người đó. Cần kiểm tra thiết kế security context của truy vấn vật hóa và quyền đọc materialized view một cách tường minh.

## 37. Schema migrations ảnh hưởng materialized view

Nếu bảng nguồn hoặc view nguồn đổi lược đồ:

- Đổi tên/xóa cột được materialized view tham chiếu có thể bị PostgreSQL từ chối do dependency hoặc yêu cầu migration.
- Đổi công thức doanh thu có thể làm định nghĩa materialized view cũ không còn đúng nghiệp vụ.
- Thay đổi kiểu dữ liệu có thể đòi tái tạo materialized view và indexes.

### 37.1. Không mặc định CREATE OR REPLACE giống VIEW

Đối với materialized view, thay định nghĩa truy vấn không đơn giản như `CREATE OR REPLACE VIEW` thường. Khi cần đổi cấu trúc, một phương án là tạo materialized view mới, xây đủ dữ liệu/index, kiểm tra rồi chuyển ứng dụng sang tên/phiên bản mới theo quy trình an toàn.

### 37.2. Rolling cutover minh họa

~~~text
mv_daily_paid_v1  -> đang phục vụ dashboard

1. Tạo mv_daily_paid_v2 với query mới.
2. Populate v2 và dựng index cần thiết.
3. Xác nhận kết quả và quyền truy cập.
4. Chuyển ứng dụng đọc v2 theo cơ chế triển khai phù hợp.
5. Theo dõi và giữ khả năng rollback trong cửa sổ cần thiết.
6. Chỉ sau đó dọn v1.
~~~

### 37.3. Không đổi tên/drop một cách tự phát

Đổi tên, drop và tạo lại materialized view liên quan quyền, dependencies, locks và các connection đang chạy. Cần chuẩn bị rollout để tránh gián đoạn hoặc làm mất kết quả mới/nhật ký refresh.

### 37.4. UNIQUE index phải tồn tại trên phiên bản mới

Nếu v2 dùng `REFRESH CONCURRENTLY`, sau khi populate lần đầu phải tạo UNIQUE index đầy đủ, hợp lệ theo group key của v2. Không giả định index từ v1 tự chuyển sang v2.

## 38. Recovery, lỗi refresh và dữ liệu cuối cùng tốt

Một refresh có thể thất bại do:

- Thiếu dung lượng storage/temp.
- Hết timeout hoặc deadlock/lock timeout.
- Query nguồn lỗi do DDL/schema thay đổi.
- UNIQUE constraint/index không hợp lệ với kết quả mới.
- Database restart hoặc kết nối scheduler gián đoạn.

### 38.1. Không đánh dấu refresh thành công khi lỗi

Log/scheduler phải phân biệt:

~~~text
started -> running -> succeeded
                |
                +-> failed
~~~

Nếu refresh thất bại, **không cập nhật last_successful_refresh** bằng timestamp bắt đầu hoặc thời điểm retry.

### 38.2. Có thể tiếp tục phục vụ dữ liệu cũ

Trong nhiều trường hợp materialized view đã populated và refresh gặp lỗi, ứng dụng có thể tiếp tục đọc dữ liệu từ lần refresh thành công trước đó. Tuy nhiên cần xác nhận tình trạng đối tượng và thông báo freshness rõ ràng, không mặc định mọi lỗi đều không ảnh hưởng availability.

### 38.3. Nếu unpopulated thì không có fallback sẵn

Một materialized view tạo `WITH NO DATA` mà chưa refresh thành công không thể dùng như nguồn báo cáo; nếu cutover quá sớm sẽ gây lỗi.

### 38.4. Retry sau khi sửa nguyên nhân

Nếu thiếu unique index, tạo index đúng trước. Nếu query nguồn quá nặng, cần tối ưu/cấp tài nguyên hoặc đổi lịch. Không retry với tần suất rất cao chỉ để hy vọng lỗi biến mất.

## 39. Thiết kế SLO/SLA theo ba trục

Một quyết định dùng materialized view nên mô tả ít nhất ba trục:

1. **Read latency:** API/dashboard cần phản hồi nhanh đến đâu?
2. **Freshness:** dữ liệu có thể trễ bao lâu so với thay đổi nguồn?
3. **Availability khi refresh:** người đọc có được phép chờ/chặn không?

| Ví dụ use case | Read latency | Freshness | Thiết kế có thể cân nhắc |
| --- | --- | --- | --- |
| Báo cáo doanh thu theo ngày | Thấp | Chấp nhận vài phút | MV refresh định kỳ |
| Dashboard lãnh đạo theo giờ | Thấp | Chấp nhận hàng chục phút | MV hoặc batch summary |
| Xác nhận thanh toán | Rất thấp | Gần commit-time | Transaction nguồn/read model đồng bộ |
| Thống kê lịch sử nhiều năm | Thấp | Có thể cập nhật ít lần | MV refresh theo lịch hoặc bảng tổng hợp |
| Phân tích tùy ý ad hoc | Tùy mức | Có thể cần ảnh chụp mới | Query nguồn/analytics store |

### 39.1. Không có một đáp án cho mọi trường hợp

Độ mới và tốc độ phản hồi luôn có ngữ cảnh nghiệp vụ. Một báo cáo ngày hôm qua có thể chấp nhận trễ vài giờ; màn hình kiểm tra một giao dịch vừa tạo thì không.

### 39.2. Con số SLA cần gắn với measurement

Nếu đặt “freshness p99 trong 15 phút”, phải có cách đo khoảng thời gian từ dữ liệu nguồn được cam kết/đưa vào hệ thống tới khi kết quả được phản ánh, hoặc một proxy được định nghĩa rõ. Chỉ đo `now()-last_refresh_finished_at` không luôn chứng minh toàn bộ cam kết ấy.

### 39.3. Phải quyết định degraded behavior

Khi refresh quá hạn:

- Có trả số liệu cũ kèm nhãn không?
- Có chặn thao tác nhạy cảm không?
- Có fallback query trực tiếp nguồn không?
- Có giới hạn concurrency khi fallback để tránh đánh sập database không?

Đây là quyết định sản phẩm và SRE, không phải một tùy chọn SQL đơn giản.

## 40. Quy trình triển khai materialized view an toàn

Một quy trình thực tế có thể gồm:

1. **Xác định truy vấn nguồn** và kiểm chứng đúng kết quả trên dữ liệu đại diện.
2. **Đặt ranh giới nghiệp vụ**, timezone, trạng thái đơn và cách xử lý chỉnh sửa lịch sử.
3. **Đo baseline** query nguồn bằng `EXPLAIN (ANALYZE, BUFFERS)`.
4. **Chọn projection và group key** không tạo dữ liệu thừa.
5. **Tạo materialized view mới** trong schema/quyền phù hợp; populate ban đầu.
6. **Xây UNIQUE index đầy đủ** nếu sẽ dùng concurrent refresh.
7. **Xây read indexes cần thiết** theo workload; tránh trùng lặp.
8. **ANALYZE** materialized view và nguồn khi phù hợp.
9. **Đo cả thời gian REFRESH và latency SELECT** trong điều kiện có tải.
10. **Thiết lập scheduler**, chống chồng lấn, timeout và retry có kiểm soát.
11. **Ghi log/mốc refresh thành công** và cảnh báo quá hạn.
12. **Chuyển API sang nguồn mới** chỉ khi materialized view sẵn sàng.
13. **Quan sát độ trễ và correctness** khi thay đổi bảng nguồn.
14. **Chuẩn bị rollback/fallback** nếu refresh thất bại hoặc freshness vi phạm SLO.
15. **Định kỳ đánh giá** chi phí storage, WAL, schema changes và dữ liệu nhạy cảm.

Đặc biệt, không coi bước tạo xong một materialized view là hoàn thành toàn bộ bài toán. **Lịch refresh, kiểm soát stale data và failure handling là một phần không thể thiếu của thiết kế.**

## 41. Những lỗi thường gặp

### Lỗi 1. Nghĩ materialized view tự cập nhật theo bảng nguồn

`INSERT`, `UPDATE`, `DELETE` trên nguồn không tự làm mới kết quả vật hóa. Phải có refresh hoặc kiến trúc incremental riêng.

### Lỗi 2. Coi refresh every 5 minutes là freshness <= 5 minutes

Job có thể mất thời gian, trễ lịch, lỗi, chờ khóa; snapshot nguồn thường được lấy trước khi job hoàn thành.

### Lỗi 3. Nhầm dữ liệu cũ với dữ liệu không nhất quán

Một materialized view có thể cũ nhưng vẫn phản ánh một snapshot nguồn hợp lệ. Cần phân biệt correctness của snapshot với việc snapshot chưa mới.

### Lỗi 4. Nghĩ CONCURRENTLY cập nhật tự động theo từng giao dịch

`CONCURRENTLY` giảm chặn SELECT trong lúc refresh, không tạo tự động incremental maintenance.

### Lỗi 5. Dùng CONCURRENTLY khi chưa có UNIQUE index

Phải có UNIQUE index trên tên cột, không partial, không expression, bao phủ mọi hàng.

### Lỗi 6. Dùng CONCURRENTLY trên materialized view WITH NO DATA

Materialized view phải populated trước; lần đầu dùng refresh thường.

### Lỗi 7. Nghĩ UNIQUE index trên biểu thức đủ điều kiện

Một index trên `lower(region)` không thay UNIQUE index trên cột đầy đủ theo yêu cầu concurrent refresh.

### Lỗi 8. Nghĩ partial UNIQUE index đủ

Index chỉ trên `region='north'` không bao phủ mọi hàng của materialized view.

### Lỗi 9. Bỏ qua NULL trong group key

UNIQUE index có semantics với NULL; group key phải được xác định rõ và kiểm tra uniqueness để tránh kỳ vọng sai.

### Lỗi 10. Nghĩ CONCURRENTLY luôn nhanh hơn

Nó có thể tốn công xây/so khớp kết quả mới và cập nhật khác biệt; lợi ích chính là giảm ảnh hưởng tới người đọc.

### Lỗi 11. Nghĩ refresh chỉ đọc những hàng nguồn mới

PostgreSQL core thường thực thi lại truy vấn định nghĩa, không tự áp delta từ WAL.

### Lỗi 12. Nghĩ MV nhỏ thì REFRESH nhẹ

Một aggregate 10 hàng có thể được tính từ hàng trăm triệu rows nguồn.

### Lỗi 13. Không kiểm tra JOIN trước aggregate

JOIN một-nhiều có thể nhân doanh thu trước khi vật hóa. MV chỉ lưu kết quả sai ấy và trả nhanh.

### Lỗi 14. Lấy latest_paid_order_at làm last_refresh_at

`MAX(created_at)` của đơn là thời điểm nghiệp vụ của hàng, không phải lúc refresh chạy hoặc source cutoff.

### Lỗi 15. Dùng pg_matviews.ispopulated làm chỉ báo freshness

`ispopulated` chỉ nói object có thể scan, không nói bao nhiêu phút trễ so với nguồn.

### Lỗi 16. Dùng last_analyze làm last_refresh

`ANALYZE` cập nhật planner statistics, không có nghĩa MV vừa được refresh.

### Lỗi 17. Ghi log success trước khi refresh commit

Nếu refresh lỗi/rollback nhưng log vẫn báo thành công, monitoring sẽ đánh lừa người dùng.

### Lỗi 18. Không xử lý lỗi scheduler

Không có alert/retry/fallback khiến dữ liệu cũ tồn tại nhiều ngày mà dashboard vẫn báo bình thường.

### Lỗi 19. Refresh chạy chồng lấn

Nhiều job bị queue/chờ cùng một MV làm tăng độ trễ và tranh chấp. Cần điều phối.

### Lỗi 20. Quên ANALYZE/index cho MV

MV là đối tượng chứa dữ liệu; query đọc lớn có thể cần index và statistics thích hợp.

### Lỗi 21. Tạo quá nhiều indexes

Mỗi index làm tăng storage và chi phí refresh; đo theo workload chứ không tạo index cho mọi cột.

### Lỗi 22. Dùng MV làm nguồn phân quyền thời gian thực

MV là bản sao có quyền riêng và có thể stale; cần kiểm soát access và các quy định bảo mật độc lập.

### Lỗi 23. Bỏ qua UPDATE/DELETE lịch sử

Chỉ tính thêm đơn mới không đủ nếu giao dịch cũ đổi trạng thái, giá, vùng hoặc bị xóa.

### Lỗi 24. Hybrid dữ liệu cũ/mới không có cutoff

Hợp nhất MV với dữ liệu live không phân định ranh giới có thể đếm trùng hoặc bỏ sót.

### Lỗi 25. REINDEX thay cho REFRESH

`REINDEX` xây lại index từ các hàng đang lưu; nó không chạy lại query nguồn để cập nhật aggregate.

### Lỗi 26. REFRESH thay cho schema migration

Refresh làm mới dữ liệu theo định nghĩa hiện có; không tự sửa cấu trúc/logic báo cáo đã lỗi thời.

### Lỗi 27. Chuyển ứng dụng sang MV chưa populated

`WITH NO DATA` tạo đối tượng unscannable; phải populate trước khi cho traffic đọc.

### Lỗi 28. Tin ORDER BY trong định nghĩa giữ thứ tự vật lý mãi

Không bảo đảm sau refresh. Mỗi SELECT cần `ORDER BY` nếu muốn thứ tự.

### Lỗi 29. Không đo nguồn replica lag

Nếu refresh/đọc qua các tầng dữ liệu trễ, freshness thực có thể lớn hơn thời gian kể từ lần refresh trên primary.

### Lỗi 30. Coi mọi use case đều phù hợp materialized view

Truy vấn giao dịch cần mới ngay, security-sensitive data hoặc nguồn nhỏ có thể không phù hợp đánh đổi này.

## 42. Bài tập thực hành

Làm trên schema `mv_lab` của bài. Với câu tạo index/table, chỉ chạy trong môi trường lab. Các câu yêu cầu mô tả kế hoạch vận hành không nên tự áp dụng trực tiếp lên production.

### Bài 1. Phân biệt VIEW và MV

Nêu hai khác biệt quan trọng nhất giữa view thường và materialized view đối với nguồn dữ liệu mới ghi và chi phí SELECT.

### Bài 2. Độ mới

Một đơn paid được commit sau lần refresh cuối. Materialized view có tự cập nhật doanh thu ngay không? Vì sao?

### Bài 3. Tính nhất quán

Một báo cáo chưa chứa đơn vừa tạo nhưng được tính đúng theo snapshot trước đó. Báo cáo ấy “không nhất quán” hay “stale”?

### Bài 4. Tạo VIEW thường

Viết view tổng hợp theo ngày UTC và vùng, chỉ đếm các đơn `paid`.

### Bài 5. Tạo materialized view

Viết DDL tạo materialized view từ `mv_lab.v_daily_paid`, có dữ liệu ngay.

### Bài 6. Truy vấn sau INSERT

Nếu chèn thêm đơn paid `30.00` vào `north` ngày 10/1/2026, view thường và MV sẽ trả doanh thu gì trước refresh?

### Bài 7. Refresh

Viết lệnh cập nhật `mv_lab.mv_daily_paid` sau khi nguồn đổi.

### Bài 8. WITH NO DATA

Một materialized view tạo `WITH NO DATA` có SELECT được không? Muốn populate lần đầu cần lệnh gì?

### Bài 9. ispopulated

Viết câu SQL đọc `pg_matviews` để xem trạng thái populated của MV trong `mv_lab`.

### Bài 10. Concurrent refresh

Nêu ba điều kiện chính để dùng `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

### Bài 11. UNIQUE index

Viết UNIQUE index hợp lệ theo cặp `(report_date, region)`.

### Bài 12. Partial UNIQUE

Vì sao UNIQUE index chỉ trên `region='north'` không đủ cho concurrent refresh?

### Bài 13. Expression UNIQUE

Một UNIQUE index trên `lower(region)` có đáp ứng yêu cầu cho concurrent refresh không?

### Bài 14. Khóa đọc

Sự khác nhau về khả năng phục vụ `SELECT` khi dùng refresh thường và concurrent?

### Bài 15. Không phải incremental

Vì sao `REFRESH ... CONCURRENTLY` không đồng nghĩa “chỉ tính các đơn mới từ lần trước”?

### Bài 16. Freshness với lịch

Job refresh mỗi 5 phút, chạy 2 phút và có một lần lỗi. Có thể đảm bảo độ trễ tối đa đúng 5 phút không?

### Bài 17. Trạng thái cuối cùng

Người dùng thấy báo cáo “cập nhật 10:05” nhưng một transaction commit lúc 10:04 vẫn vắng mặt. Điều đó có thể xảy ra không?

### Bài 18. Refresh log

Viết bảng log lưu tên MV, thời điểm hoàn tất và chế độ refresh.

### Bài 19. Đo tuổi log

Viết query lấy lần refresh thành công gần nhất và số giây kể từ thời điểm đó.

### Bài 20. Source watermark

Vì sao `MAX(orders.created_at)` không đáng tin để chứng minh mọi thay đổi bảng nguồn đã vào MV?

### Bài 21. EXPLAIN

Viết hai câu `EXPLAIN (ANALYZE, BUFFERS)` so sánh SELECT từ view thường và MV.

### Bài 22. Index cho read query

Thiết kế index cho query lọc `region='north'` và `ORDER BY report_date DESC`.

### Bài 23. ANALYZE

Viết SQL cập nhật statistics cho materialized view; nó có làm mới doanh thu không?

### Bài 24. Size

Viết query đo heap/index/total size của MV.

### Bài 25. UPDATE/DELETE

Vì sao một chiến lược chỉ cộng thêm doanh thu từ INSERT mới có thể sai sau refund/hủy đơn?

### Bài 26. Tính lại full

Nếu MV có 12 dòng nhưng nguồn có 200 triệu đơn, vì sao refresh vẫn có thể kéo dài?

### Bài 27. Read replicas

Nếu app đọc một read replica có replication lag, tại sao trạng thái MV còn có thể cũ dù primary vừa refresh?

### Bài 28. Chọn kiến trúc

Một dashboard lãnh đạo chấp nhận trễ 10 phút; một API xác nhận tồn kho không được trễ. Chọn cách đọc cho hai trường hợp và giải thích.

### Bài 29. Nguồn đa bảng

Doanh thu theo `customers.region` có thể thay đổi do cập nhật bảng customers không? Refresh chỉ quan sát đơn mới có đủ không?

### Bài 30. Giới hạn hybrid

Điều gì xảy ra nếu MV đã có đơn ngày hôm nay, rồi dashboard cộng thêm live aggregate cũng chứa toàn bộ đơn hôm nay?

### Bài 31. Index sai mục đích

`CREATE INDEX ON mv_daily_paid(report_date)` có đủ để dùng `CONCURRENTLY` không? Vì sao?

### Bài 32. Đồng thời

Scheduler khởi động job mỗi 5 phút nhưng một lượt mất 9 phút. Hãy đề xuất chính sách tránh refresh chồng lấn.

### Bài 33. Rollout phiên bản mới

Mô tả thứ tự triển khai MV v2 khi cần thay công thức aggregate nhưng dashboard vẫn đang dùng MV v1.

### Bài 34. Quyền truy cập

Vì sao không nên cấp quyền SELECT rộng cho một MV chứa dữ liệu tổng hợp nhạy cảm chỉ vì bảng nguồn đã có RLS?

### Bài 35. Lỗi refresh

Nếu refresh thất bại, timestamp “last successful refresh” có được cập nhật không? Dashboard nên hiển thị gì?

### Bài 36. Thiết kế SLA

Đề xuất những thông số tối thiểu cần đo để tuyên bố báo cáo đáp ứng freshness SLO 15 phút.

## 43. Gợi ý lời giải

### Bài 1–3. Khác biệt cốt lõi

View thường chạy query nguồn để đọc theo snapshot mới; materialized view đọc kết quả đã lưu, chỉ thay đổi sau refresh. Một kết quả đúng theo snapshot cũ là **stale**, không tự động đồng nghĩa một kết quả bị tính không nhất quán.

### Bài 4. VIEW nguồn

~~~sql
CREATE VIEW mv_lab.v_daily_paid_answer AS
SELECT
    (o.created_at AT TIME ZONE 'UTC')::date AS report_date,
    c.region,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS revenue
FROM mv_lab.orders AS o
JOIN mv_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
GROUP BY
    (o.created_at AT TIME ZONE 'UTC')::date,
    c.region;
~~~

### Bài 5. Tạo MV WITH DATA

~~~sql
CREATE MATERIALIZED VIEW mv_lab.mv_daily_paid_answer AS
SELECT *
FROM mv_lab.v_daily_paid
WITH DATA;
~~~

Từ `WITH DATA`, lần tạo sẽ chạy query nguồn để populate.

### Bài 6–7. Trước/sau refresh

Với dữ liệu ban đầu, north ngày 10/1 có doanh thu 170.00. Sau khi thêm đơn paid 30.00 nhưng chưa refresh: view thường có 200.00, MV vẫn 170.00.

~~~sql
REFRESH MATERIALIZED VIEW mv_lab.mv_daily_paid;
~~~

Sau refresh thành công và nếu nguồn không đổi tiếp, MV lên 200.00.

### Bài 8. WITH NO DATA

`WITH NO DATA` làm MV unpopulated, không thể SELECT như một bảng rỗng thường.

~~~sql
REFRESH MATERIALIZED VIEW
    mv_lab.mv_daily_paid_unpopulated;
~~~

Lần đầu không dùng `CONCURRENTLY`.

### Bài 9. pg_matviews

~~~sql
SELECT
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_lab';
~~~

### Bài 10–13. CONCURRENTLY và UNIQUE

MV phải **populated**, có ít nhất một UNIQUE index **trên các cột**, **không partial**, bao phủ mọi hàng.

~~~sql
CREATE UNIQUE INDEX uq_mv_daily_paid_answer
ON mv_lab.mv_daily_paid (report_date, region);
~~~

*Lưu ý:* Trong lab đã có thể tạo UNIQUE index tương đương `uq_mv_daily_paid_date_region`, nên không cần tạo index đáp án thứ hai. Partial UNIQUE hoặc expression UNIQUE không đáp ứng điều kiện concurrent refresh.

### Bài 14–15. Lock và full recomputation

Refresh thường có thể chặn SELECT; concurrent refresh cho phép SELECT tiếp tục trong lúc cập nhật theo cơ chế phù hợp, nhưng có chi phí riêng. Cả hai vẫn phải thực thi truy vấn định nghĩa; `CONCURRENTLY` không phải cập nhật incremental tự động từ WAL.

### Bài 16–17. Thời gian

Không bảo đảm trễ tối đa 5 phút khi job chạy 2 phút hoặc lỗi. Một commit lúc 10:04 có thể không có trong snapshot được chọn lúc 10:03 dù refresh hoàn thành/được ghi nhận lúc 10:05.

### Bài 18. Bảng log

~~~sql
CREATE TABLE mv_lab.refresh_log_answer (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    matview_name text NOT NULL,
    finished_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    refresh_mode text NOT NULL
);
~~~

### Bài 19. Tuổi refresh

~~~sql
SELECT
    MAX(finished_at) AS last_success,
    EXTRACT(
        EPOCH FROM (
            clock_timestamp() - MAX(finished_at)
        )
    ) AS age_seconds
FROM mv_lab.refresh_log
WHERE matview_name = 'mv_lab.mv_daily_paid';
~~~

### Bài 20. Watermark

`MAX(created_at)` không phát hiện thay đổi trạng thái đơn cũ, DELETE, đổi vùng khách, hay những giao dịch được commit muộn với business timestamp cũ. Nó không phải mốc đã xử lý mọi thay đổi.

### Bài 21. EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM mv_lab.v_daily_paid
WHERE report_date >= DATE '2026-01-01';

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM mv_lab.mv_daily_paid
WHERE report_date >= DATE '2026-01-01';
~~~

Đọc loại scan, JOIN/Aggregate/Sort, `actual rows`, `Buffers` và `Execution Time`; không kết luận về tốc độ từ dữ liệu lab ít hàng.

### Bài 22–23. Read index và ANALYZE

~~~sql
CREATE INDEX idx_mv_region_date_answer
ON mv_lab.mv_daily_paid (region, report_date DESC);

ANALYZE mv_lab.mv_daily_paid;
~~~

`ANALYZE` cập nhật statistics, **không refresh doanh thu**.

### Bài 24. Storage

~~~sql
SELECT
    pg_relation_size(
        'mv_lab.mv_daily_paid'::regclass
    ) AS heap_bytes,
    pg_indexes_size(
        'mv_lab.mv_daily_paid'::regclass
    ) AS index_bytes,
    pg_total_relation_size(
        'mv_lab.mv_daily_paid'::regclass
    ) AS total_bytes;
~~~

### Bài 25–26. Chi phí

Refund/hủy có thể làm giảm `SUM`/`COUNT`, chuyển nhóm hoặc xóa nhóm; chỉ cộng đơn mới sẽ sai. Dù MV có 12 rows, query nguồn cần aggregate 200 triệu đơn có thể rất tốn CPU/I/O.

### Bài 27. Replica lag

Replica có thể chưa nhận WAL/commit chứa kết quả refresh từ primary; app vẫn nhìn phiên bản cũ. Cần đo replication lag và xác định nơi đọc.

### Bài 28. Kiến trúc

Dashboard chấp nhận 10 phút trễ có thể dùng MV refresh định kỳ và nhãn freshness. API xác nhận tồn kho cần dữ liệu phù hợp consistency của giao dịch, không dựa duy nhất vào MV có thể stale.

### Bài 29–30. Thay đổi đa bảng và hybrid

Đổi region của khách có thể làm thay đổi phân nhóm doanh thu của đơn cũ; chỉ xem đơn mới không đủ. Cộng live aggregate trùng với khoảng đã có trong MV sẽ đếm hai lần; cần cutoff/watermark có chứng minh và xử lý late changes.

### Bài 31. Index không UNIQUE

Index thường trên `report_date` không đủ cho concurrent refresh. Cần UNIQUE index trên cột, không partial/không expression, bao phủ mọi hàng.

### Bài 32. Scheduler

Dùng một worker/queue cho MV, nếu job trước chưa xong thì skip hoặc gộp các yêu cầu, có alert về lịch trễ. Không để lịch 5 phút tạo nhiều refresh chờ nhau vô hạn.

### Bài 33. Cutover

Tạo MV v2, populate, tạo indexes (kể cả UNIQUE phục vụ concurrent), xác nhận kết quả và quyền, rồi chuyển dashboard/ứng dụng sang v2. Giữ v1 đủ cho rollback; chỉ xóa khi không còn phụ thuộc.

### Bài 34. Security

MV lưu một bản sao có quyền SELECT riêng. RLS của bảng nguồn không phải bằng chứng rằng mọi người dùng SELECT MV được lọc đúng quyền trên từng row; cần thiết kế quyền truy cập, scope và nội dung được vật hóa.

### Bài 35. Failure

Không cập nhật timestamp success khi refresh lỗi. Hiển thị mốc refresh thành công cuối, tuổi dữ liệu và cảnh báo “stale/degraded”; tùy SLA có thể fallback hoặc hạn chế hành động nhạy cảm.

### Bài 36. Freshness SLO

Cần ít nhất: lịch/bắt đầu/kết thúc refresh, duration p95/p99, tỉ lệ thành công, chờ khóa, độ trễ scheduler, nguồn snapshot/watermark nếu có, thời gian commit của thay đổi nguồn và thời điểm nó xuất hiện ở kết quả, cùng tuổi dữ liệu hiển thị. Chỉ số “lần refresh gần nhất” là cần thiết nhưng chưa đủ chứng minh mọi thay đổi đã được xử lý.

## 44. Bảng tra cứu nhanh

| Nhu cầu | Cú pháp hoặc nguyên tắc |
| --- | --- |
| View luôn dựa trên nguồn | `CREATE VIEW ... AS SELECT ...` |
| Lưu kết quả truy vấn | `CREATE MATERIALIZED VIEW ... AS SELECT ... WITH DATA` |
| Tạo MV chưa populate | `CREATE MATERIALIZED VIEW ... WITH NO DATA` |
| Populate lần đầu | `REFRESH MATERIALIZED VIEW mv_name` |
| Làm mới thường | `REFRESH MATERIALIZED VIEW mv_name` |
| Làm mới giảm chặn SELECT | `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_name` |
| Yêu cầu concurrent | MV populated + UNIQUE index đủ điều kiện |
| UNIQUE index đủ điều kiện | `CREATE UNIQUE INDEX ... ON mv(cols...)`, không expression/partial |
| Bỏ dữ liệu, unpopulate | `REFRESH MATERIALIZED VIEW mv_name WITH NO DATA` |
| Xem trạng thái populated | `pg_matviews.ispopulated` |
| Xem có index | `pg_matviews.hasindexes` |
| Đọc MV theo thứ tự | `SELECT ... FROM mv ORDER BY ...` |
| Đo SELECT plan | `EXPLAIN (ANALYZE, BUFFERS)` |
| Cập nhật statistics | `ANALYZE mv_name` |
| Đo dữ liệu vật lý | `pg_relation_size`, `pg_indexes_size` |
| Ghi refresh thành công | Bảng log hoặc scheduler/observability |
| Tuổi refresh | `clock_timestamp() - MAX(finished_at)` |
| Source watermark | Thiết kế xử lý thay đổi/CDC, không dựa đơn thuần `MAX(created_at)` |
| Tránh job chồng lấn | Queue/lock điều phối, retry và timeout |
| Xử lý báo cáo cần mới ngay | Đọc nguồn hoặc read model đồng bộ thích hợp |
| Cập nhật theo delta | Bảng tổng hợp incremental/architecture riêng |
| Thay đổi định nghĩa MV | Migration/versioned cutover, không coi REFRESH là thay query |

## 45. Checklist trước khi triển khai

1. **Truy vấn nguồn có đúng nghiệp vụ không?** Đã kiểm tra JOIN cardinality và aggregation?
2. **Báo cáo được phép cũ bao lâu?** Người tiêu thụ có hiểu nhãn refresh?
3. **Thời gian refresh p95/p99** đã đo trên lượng dữ liệu gần production?
4. **Refresh thường có thể chặn SELECT?** Nếu không chấp nhận, có đủ điều kiện `CONCURRENTLY`?
5. **UNIQUE index có dùng tên cột, không partial/expression, bao phủ mọi hàng?**
6. **MV đã populated?** Có chuyển traffic trước khi populate xong?
7. **Query đọc có index cần thiết?** Có index dư gây thêm storage/refresh cost?
8. **Nguồn có index/partitioning hợp với truy vấn refresh?**
9. **Có đo CPU, I/O, WAL, temp files và replication lag?**
10. **Scheduler có chống job chồng lấn**, timeout, backoff và retry có giới hạn?
11. **Có ghi last_successful_refresh đáng tin cậy?** Có xử lý không có log?
12. **Có theo dõi source watermark nếu SLO yêu cầu?**
13. **Có cách cảnh báo khi freshness quá hạn?**
14. **Có policy fallback/degraded mode nếu refresh thất bại?**
15. **Có những bảng JOIN khác ngoài fact table làm thay đổi kết quả?**
16. **Dữ liệu có UPDATE/DELETE quá khứ hoặc late-arriving events không?**
17. **Nếu hybrid, cutoff có tránh đếm trùng/bỏ sót?**
18. **Có đảm bảo quyền SELECT trên MV đúng chính sách dữ liệu?**
19. **Các bản sao/cache/read replicas có SLA freshness riêng?**
20. **Schema migrations có kế hoạch rebuild/cutover MV?**
21. **Stats ANALYZE có được duy trì sau các đợt refresh lớn?**
22. **Kết quả có yêu cầu ORDER BY tường minh?**
23. **Có đo cả read latency và refresh overhead, không chỉ một phía?**
24. **Có định kỳ kiểm tra MV còn mang lại lợi ích so với VIEW hoặc summary table?**

## 46. Tổng kết

**Materialized view là sự đánh đổi có chủ đích giữa tốc độ truy vấn và độ mới của dữ liệu.** Nó lưu kết quả của một câu SELECT để các lượt đọc tiếp theo không cần tính lại toàn bộ JOIN/aggregate trên bảng nguồn. Vì vậy nó phù hợp với dashboard và báo cáo đọc nhiều, tính toán tốn kém, **chấp nhận dữ liệu trễ**.

Những nguyên tắc quan trọng nhất:

1. **VIEW thường** đọc nguồn theo snapshot của truy vấn; **MATERIALIZED VIEW** đọc kết quả vật hóa từ lần refresh gần nhất.
2. `REFRESH MATERIALIZED VIEW` phải được gọi/chạy theo lịch; PostgreSQL core **không tự cập nhật tăng dần theo từng INSERT/UPDATE/DELETE**.
3. `REFRESH MATERIALIZED VIEW CONCURRENTLY` giúp giảm chặn SELECT, nhưng cần một **UNIQUE index đầy đủ trên các cột**, MV đã populated, và vẫn tiêu thụ tài nguyên lớn khi query nguồn nặng.
4. **Dữ liệu nhất quán nhưng cũ** vẫn có thể gây quyết định sai. Mốc refresh thành công và mốc snapshot/source watermark không phải luôn là một thời điểm.
5. Để vận hành tốt, cần **lịch refresh, monitoring, alert, retry, quản lý chồng lấn, chính sách degraded mode và kiểm soát quyền**.
6. Khi cần freshness gần thời gian thực hoặc cập nhật delta phức tạp, hãy cân nhắc **bảng tổng hợp incremental**, đọc trực tiếp nguồn, cache có invalidation hoặc giải pháp chuyên dụng, thay vì cố refresh toàn bộ liên tục.

Trước khi chọn materialized view, hãy trả lời ba câu hỏi: **“Một lượt SELECT từ nguồn tốn bao nhiêu?”, “Người dùng chấp nhận số liệu chậm tối đa bao lâu?”, và “Mỗi lần làm mới có gây tải hoặc gián đoạn đọc không?”**. Khi cân bằng được cả ba, materialized view sẽ là một thành phần hữu ích trong kiến trúc PostgreSQL, thay vì chỉ là một bản sao dữ liệu nhanh nhưng không biết đã cũ đến mức nào.
