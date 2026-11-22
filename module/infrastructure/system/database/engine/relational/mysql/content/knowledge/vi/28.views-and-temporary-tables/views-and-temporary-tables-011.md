# Chọn view, CTE, bảng tạm hoặc bảng lưu kết quả theo bài toán

MySQL có nhiều cách tổ chức một tập kết quả để tái sử dụng: **view**, **CTE**, **temporary table** và **bảng lưu kết quả** do ứng dụng hoặc job ETL quản lý. Chúng có vẻ giống nhau vì đều có thể đại diện cho dữ liệu được truy vấn, nhưng khác nhau về phạm vi tồn tại, khả năng tái sử dụng, tính mới của dữ liệu, index và chi phí lưu trữ.

Bài học thuộc phần **View và bảng tạm** của MySQL. Mục tiêu là chọn đúng cấu trúc theo bài toán: view cho logic truy vấn dùng lại, CTE cho một câu SQL cần chia thành các bước dễ đọc, bảng tạm cho dữ liệu trung gian trong một session hoặc quy trình nhiều bước, và bảng lưu kết quả cho dữ liệu tổng hợp cần phục vụ nhiều session với thời gian đọc ổn định.

## 1. Bốn lựa chọn giải quyết bốn nhu cầu khác nhau

| Lựa chọn | Phạm vi và vòng đời | Dữ liệu có được lưu sẵn? | Phù hợp khi |
| --- | --- | --- | --- |
| View | Định nghĩa tồn tại trong schema; truy vấn được từ nhiều session có quyền. | Thông thường không; view lưu câu SELECT, dữ liệu được đọc từ các bảng nguồn khi truy vấn. | Muốn tái sử dụng logic, chuẩn hóa cách truy cập hoặc tạo lớp giao diện cho dữ liệu. |
| CTE (`WITH`) | Chỉ tồn tại trong một statement. | Không phải đối tượng lưu trữ lâu dài; optimizer có thể merge hoặc materialize trong lúc thực thi. | Muốn chia câu SQL phức tạp thành các bước có tên, dùng đệ quy hoặc tổ chức truy vấn nhiều tầng. |
| Temporary table | Chỉ session tạo bảng nhìn thấy; tự mất khi session kết thúc hoặc được drop. | Có; chứa các dòng được ghi vào bảng tạm. | Cần giữ một tập trung gian qua nhiều statement, tạo index riêng hoặc xử lý theo nhiều bước. |
| Bảng lưu kết quả (summary/cache/staging table) | Đối tượng schema tồn tại cho nhiều session cho đến khi được xóa hoặc thay thế. | Có; dữ liệu được tạo và làm mới theo quy trình ứng dụng/ETL. | Nhiều người dùng cần đọc cùng kết quả tổng hợp, chấp nhận độ trễ làm mới có kiểm soát. |

Điểm quyết định không phải cú pháp nào ngắn nhất. Hãy xác định ai cần dùng dữ liệu, trong bao lâu, có cần dữ liệu mới nhất không, có cần index riêng không và chi phí tính toán nên trả ở thời điểm đọc hay thời điểm làm mới.

## 2. Dùng view khi cần tái sử dụng logic truy vấn

View là một đối tượng schema lưu định nghĩa SELECT. Khi truy vấn view, MySQL thường kết hợp định nghĩa view với truy vấn bên ngoài hoặc materialize kết quả tùy algorithm và cấu trúc câu lệnh. View thông thường không lưu bản sao dữ liệu riêng.

Ví dụ, ứng dụng thường xuyên cần danh sách đơn hàng đã thanh toán:

```sql
CREATE OR REPLACE VIEW v_paid_orders AS
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID';
```

Các truy vấn sau có thể dùng cùng định nghĩa:

```sql
SELECT order_id, created_at, total_amount
FROM v_paid_orders
WHERE customer_id = 1001
ORDER BY created_at DESC;

SELECT COUNT(*) AS paid_order_count
FROM v_paid_orders
WHERE created_at >= '2026-01-01';
```

Lợi ích của view:

- Gom logic dùng chung vào một định nghĩa có tên.
- Giảm lặp lại biểu thức JOIN và điều kiện lọc trong nhiều câu SQL.
- Có thể giới hạn cột được công bố cho một nhóm người dùng, kết hợp với quyền trên view và quyền nền phù hợp.
- Giúp ứng dụng ít phụ thuộc vào chi tiết cấu trúc bảng nguồn hơn.

View không tự làm truy vấn nhanh hơn. Nếu view chứa nhiều JOIN, aggregate hoặc biểu thức tốn kém, mỗi lần truy vấn vẫn có thể phải thực hiện công việc tương ứng. Muốn tăng tốc, cần xem execution plan, index bảng nguồn hoặc cân nhắc lưu kết quả đã tính.

### MERGE, TEMPTABLE và cách view được thực thi

MySQL hỗ trợ các algorithm của view:

- `MERGE`: optimizer kết hợp định nghĩa view vào câu truy vấn bên ngoài khi có thể.
- `TEMPTABLE`: kết quả view được materialize vào một bảng tạm nội bộ trong quá trình thực thi.
- `UNDEFINED`: để MySQL tự chọn algorithm phù hợp; đây là lựa chọn mặc định nếu không chỉ định.

Ví dụ khai báo algorithm:

```sql
CREATE ALGORITHM = MERGE VIEW v_customer_orders AS
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
```

`MERGE` có thể cho phép điều kiện từ truy vấn ngoài được đẩy vào các bảng nguồn. Tuy nhiên, một số cấu trúc như aggregate, `DISTINCT`, `GROUP BY`, `HAVING`, `LIMIT`, `UNION` hoặc biểu thức không tương thích có thể ngăn merge. Trong những trường hợp đó, MySQL có thể phải materialize hoặc từ chối một algorithm được yêu cầu tùy định nghĩa.

View dùng `TEMPTABLE` có thể hữu ích khi cần tạo kết quả trung gian trước khi xử lý tiếp, nhưng có thể tăng chi phí ghi/đọc bảng tạm. Nó cũng ảnh hưởng khả năng cập nhật view: view được materialize không có cùng khả năng updatable như view merge.

### View có cập nhật được không?

Một số view đơn giản có thể dùng trong `INSERT`, `UPDATE` hoặc `DELETE`. Khả năng updatable phụ thuộc cấu trúc view. View có aggregate, `GROUP BY`, `DISTINCT`, `UNION`, một số subquery hoặc phép biến đổi làm mất ánh xạ một-một tới dòng bảng nguồn thường không updatable.

Ví dụ view đơn giản:

```sql
CREATE OR REPLACE VIEW v_active_customers AS
SELECT customer_id, customer_name, email
FROM customers
WHERE status = 'ACTIVE';
```

Một thao tác cập nhật qua view có thể được chuyển tới bảng nguồn nếu view thỏa quy tắc updatable:

```sql
UPDATE v_active_customers
SET email = 'new-address@example.com'
WHERE customer_id = 1001;
```

Không nên giả định mọi view đều ghi được. Kiểm tra định nghĩa, `CHECK OPTION` nếu cần ràng buộc dòng ghi qua view và thử hành vi trên môi trường phù hợp. View không có index riêng; index phải được tạo trên bảng nguồn.

## 3. Dùng CTE khi cần tổ chức một statement nhiều bước

CTE (Common Table Expression) được khai báo bằng `WITH` và chỉ có hiệu lực trong statement theo sau. CTE giúp đặt tên cho một tập kết quả logic, chia truy vấn thành các bước có thể đọc và kiểm tra riêng.

Ví dụ tính tổng đơn hàng theo khách hàng rồi lọc nhóm có doanh thu cao:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS total_spent
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT customer_id, total_spent
FROM customer_totals
WHERE total_spent >= 10000
ORDER BY total_spent DESC;
```

CTE phù hợp khi:

- Một câu SQL cần nhiều bước logic có tên rõ ràng.
- Cùng một tập kết quả được tham chiếu nhiều lần trong một statement.
- Cần viết truy vấn đệ quy để duyệt cây, quan hệ cha con hoặc chuỗi liên kết.
- Muốn tách phần lọc, tổng hợp và phép JOIN để dễ kiểm tra.

CTE không tồn tại sau khi statement kết thúc. Nếu một session cần sử dụng cùng dữ liệu trung gian trong nhiều statement, CTE không thay thế được temporary table.

### CTE không đồng nghĩa luôn materialize

MySQL có thể merge một CTE không đệ quy vào query block bên ngoài hoặc materialize kết quả tùy cấu trúc và lựa chọn optimizer. CTE được tham chiếu nhiều lần có thể được materialize một lần và dùng lại trong statement; optimizer có thể tạo index nội bộ trên kết quả materialized khi hữu ích. Không nên mặc định mỗi CTE luôn tạo một bảng tạm vật lý hoặc luôn được tính lại cho từng lần tham chiếu.

Kiểm tra kế hoạch:

```sql
EXPLAIN FORMAT = TREE
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS total_spent
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
)
SELECT customer_id, total_spent
FROM customer_totals
WHERE total_spent >= 10000;
```

Nếu cần biết số liệu thực tế, có thể dùng `EXPLAIN ANALYZE` cho SELECT phù hợp. CTE giúp tổ chức SQL; execution plan mới cho biết optimizer thực thi ra sao.

### Recursive CTE cho dữ liệu phân cấp

Recursive CTE phù hợp để duyệt cấu trúc cây như danh mục, nhân viên và quản lý, hoặc các node cha con:

```sql
WITH RECURSIVE category_tree AS (
    SELECT category_id, parent_id, category_name, 0 AS depth
    FROM categories
    WHERE category_id = 10

    UNION ALL

    SELECT c.category_id, c.parent_id, c.category_name, ct.depth + 1
    FROM categories AS c
    JOIN category_tree AS ct
      ON c.parent_id = ct.category_id
)
SELECT category_id, parent_id, category_name, depth
FROM category_tree
ORDER BY depth, category_id;
```

Phần anchor tìm node gốc; phần recursive lấy các node con của tập đã tìm được. Cần có điều kiện dừng hợp lý và tránh dữ liệu chu trình gây đệ quy quá sâu. MySQL có giới hạn độ sâu đệ quy (`cte_max_recursion_depth`) và có thể cấu hình timeout cho câu SELECT phù hợp.

## 4. Dùng temporary table khi cần giữ kết quả qua nhiều statement

Temporary table do session tạo ra chỉ nhìn thấy trong session đó. Session khác không thể truy vấn bảng tạm này; bảng tự bị xóa khi session kết thúc hoặc có thể được xóa sớm bằng `DROP TEMPORARY TABLE`.

Ví dụ, một quy trình cần chọn khách hàng đủ điều kiện, sau đó kiểm tra và cập nhật nhiều bước:

```sql
CREATE TEMPORARY TABLE tmp_target_customers (
    customer_id BIGINT NOT NULL PRIMARY KEY,
    total_spent DECIMAL(14, 2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO tmp_target_customers (customer_id, total_spent)
SELECT customer_id, SUM(total_amount)
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
GROUP BY customer_id;

SELECT COUNT(*) AS target_count
FROM tmp_target_customers;

SELECT c.customer_id, c.customer_name, t.total_spent
FROM customers AS c
JOIN tmp_target_customers AS t
  ON t.customer_id = c.customer_id;

DROP TEMPORARY TABLE tmp_target_customers;
```

Temporary table hữu ích khi:

- Cùng một tập trung gian được dùng trong nhiều statement của một session.
- Cần tạo index riêng cho dữ liệu trung gian.
- Muốn chia quy trình thành các bước và kiểm tra số dòng giữa các bước.
- Muốn tránh tính lại một tập kết quả đắt tiền nhiều lần trong cùng session.
- Cần lưu kết quả xử lý trung gian mà không tạo đối tượng dùng chung cho toàn schema.

### Temporary table và phạm vi session

Hai session có thể cùng tạo temporary table với tên giống nhau; mỗi session nhìn thấy bảng tạm của chính mình. Trong session tạo bảng tạm, bảng đó có thể che khuất một bảng permanent cùng tên khi phân giải tên không kèm schema. Vì vậy, dùng tiền tố như `tmp_` và drop bảng tạm rõ ràng để tránh nhầm lẫn.

```sql
CREATE TEMPORARY TABLE tmp_session_result (
    id BIGINT PRIMARY KEY,
    score DECIMAL(8, 2)
) ENGINE = InnoDB;
```

Temporary table có thể dùng engine như InnoDB hoặc MEMORY tùy yêu cầu và khả năng hỗ trợ. InnoDB phù hợp khi cần kiểu dữ liệu và đặc tính lưu trữ rộng hơn; MEMORY lưu dữ liệu trong RAM, có giới hạn về kiểu cột và tiêu thụ bộ nhớ theo session. Không chọn MEMORY chỉ vì tên gọi có vẻ nhanh hơn.

### Temporary table có thể có index

Khác CTE và view, temporary table do người dùng tạo có thể khai báo primary key và secondary index:

```sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT NOT NULL,
    total_spent DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY ix_total_spent (total_spent)
) ENGINE = InnoDB;
```

Index hữu ích nếu nhiều statement tiếp theo JOIN hoặc lọc tập trung gian. Nhưng tạo index cũng có chi phí ghi và bộ nhớ/đĩa; nếu chỉ quét một lần, index có thể không đáng tạo.

### Lưu ý về transaction và vòng đời

Temporary table không chia sẻ giữa session và sẽ bị dọn khi session đóng. Tuy nhiên, không nên xem thao tác tạo/xóa temporary table như một thay đổi dữ liệu nghiệp vụ có thể rollback hoàn toàn: một số thao tác DDL trên temporary table không gây implicit commit nhưng bản thân thao tác tạo/xóa bảng tạm không được rollback như DML. Hãy tách rõ vòng đời cấu trúc bảng tạm với transaction cập nhật dữ liệu nghiệp vụ.

Trong connection pool, session có thể được tái sử dụng cho request khác. Bảng tạm còn sót lại có thể gây xung đột tên hoặc rò rỉ dữ liệu giữa các luồng logic nếu ứng dụng không drop hoặc reset session đúng cách. Hãy dùng tên rõ ràng, xóa bảng tạm khi hoàn tất và kiểm tra chính sách reset connection của pool.

## 5. Dùng bảng lưu kết quả khi nhiều session cần đọc cùng dữ liệu

Nếu nhiều người dùng hoặc nhiều service cần đọc cùng một tập tổng hợp và việc tính lại mỗi lần quá đắt, có thể lưu kết quả vào một bảng permanent. Ứng dụng hoặc job ETL chịu trách nhiệm tạo và làm mới dữ liệu.

Ví dụ bảng tổng hợp doanh thu ngày:

```sql
CREATE TABLE daily_sales_summary (
    sales_date DATE NOT NULL,
    customer_id BIGINT NOT NULL,
    order_count BIGINT NOT NULL,
    revenue DECIMAL(16, 2) NOT NULL,
    refreshed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (sales_date, customer_id),
    KEY ix_customer_date (customer_id, sales_date)
) ENGINE = InnoDB;
```

Job có thể tổng hợp dữ liệu nguồn rồi ghi vào bảng:

```sql
INSERT INTO daily_sales_summary (
    sales_date,
    customer_id,
    order_count,
    revenue,
    refreshed_at
)
SELECT
    DATE(created_at),
    customer_id,
    COUNT(*),
    SUM(total_amount),
    CURRENT_TIMESTAMP
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-03-01'
  AND created_at <  '2026-03-02'
GROUP BY DATE(created_at), customer_id;
```

Ví dụ này minh họa việc nạp kết quả tổng hợp của một ngày. Khi làm mới nhiều ngày, cần xác định cách xử lý nhóm đã biến mất khỏi nguồn: insert đơn thuần không tự xóa các nhóm cũ không còn kết quả. Có thể xóa phạm vi ngày cần làm mới trong cùng transaction rồi insert lại, hoặc dùng staging và quy trình thay thế có kiểm soát. Nếu chọn upsert, hãy dùng cú pháp phù hợp với phiên bản MySQL và xác định rõ unique key nào có thể xung đột.

### Ưu điểm và chi phí của bảng lưu kết quả

Ưu điểm:

- Nhiều session đọc cùng dữ liệu mà không phải tính lại truy vấn tổng hợp nặng.
- Có thể tạo index, partition và quyền truy cập riêng.
- Kiểm soát được lịch làm mới và thời điểm dữ liệu được công bố.
- Có thể lưu thêm `refreshed_at`, batch ID hoặc source watermark để theo dõi độ mới.

Chi phí:

- Tốn dung lượng lưu trữ và index.
- Phải thiết kế full refresh, incremental refresh hoặc xử lý bù khi dữ liệu nguồn thay đổi.
- Dữ liệu có thể cũ hơn bảng nguồn; ứng dụng phải hiểu freshness contract.
- Cần xử lý đồng thời giữa job refresh và truy vấn đọc.
- Có nguy cơ dữ liệu tổng hợp sai nếu job retry, bỏ sót khoảng hoặc cập nhật không idempotent.

Bảng lưu kết quả không phải view materialized tự động. MySQL không có materialized view tích hợp theo cách một số hệ quản trị khác cung cấp; việc lưu, refresh và đồng bộ phải do ứng dụng hoặc quy trình ETL thiết kế.

## 6. Làm mới bảng kết quả: full refresh và incremental refresh

### Full refresh theo phạm vi nhỏ

Nếu chỉ làm mới một ngày hoặc một kỳ nhỏ, có thể xóa dữ liệu cũ trong phạm vi rồi insert kết quả mới trong cùng transaction:

```sql
START TRANSACTION;

DELETE FROM daily_sales_summary
WHERE sales_date = '2026-03-01';

INSERT INTO daily_sales_summary (
    sales_date,
    customer_id,
    order_count,
    revenue,
    refreshed_at
)
SELECT
    DATE(created_at),
    customer_id,
    COUNT(*),
    SUM(total_amount),
    CURRENT_TIMESTAMP
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-03-01'
  AND created_at <  '2026-03-02'
GROUP BY DATE(created_at), customer_id;

COMMIT;
```

Nếu insert thất bại trước commit, có thể rollback cả thao tác xóa và insert vì bảng dùng InnoDB. Tuy nhiên, transaction lớn có thể giữ khóa và tạo undo/redo đáng kể. Với phạm vi lớn, dùng staging table hoặc refresh theo từng phần có checkpoint.

### Incremental refresh

Incremental refresh chỉ tính lại phần dữ liệu thay đổi kể từ watermark hoặc CDC position. Cách này giảm lượng dữ liệu cần quét nhưng phức tạp hơn:

- Phải xác định thay đổi insert, update và delete ở bảng nguồn.
- Cần xử lý sự kiện đến trễ hoặc cập nhật ngược ngày.
- Phải lưu watermark bền vững và cập nhật cùng transaction công bố kết quả.
- Cần có cách đối soát định kỳ với kết quả full refresh.

Nếu nguồn có thể sửa dữ liệu của tháng trước, incremental refresh chỉ đọc dữ liệu mới nhất theo `created_at` có thể bỏ sót cập nhật. Hãy chọn watermark dựa trên cột thay đổi hoặc cơ chế change data capture phù hợp.

### Staging và công bố kết quả

Với refresh lớn, có thể nạp kết quả vào bảng staging, kiểm tra số dòng và tổng kiểm soát, sau đó công bố theo một thao tác thay thế có kiểm soát. Ví dụ về ý tưởng:

```sql
CREATE TABLE daily_sales_summary_stage LIKE daily_sales_summary;

-- Nạp và kiểm tra dữ liệu trong daily_sales_summary_stage.
-- Sau khi xác minh, lập kế hoạch thay thế bảng theo quy trình vận hành.
```

Không chạy `RENAME TABLE` hoặc drop/replace bảng thật chỉ dựa trên ví dụ khung. DDL có metadata lock và quy tắc implicit commit; cần xem xét quyền, view phụ thuộc, foreign key, trigger, backup, replication và khả năng rollback trước khi công bố. Với bảng lớn hoặc hệ thống quan trọng, hãy thử quy trình swap trên bản sao tương đương production.

## 7. So sánh độ mới dữ liệu và chi phí đọc

Một cách chọn nhanh là xác định độ mới dữ liệu mà ứng dụng yêu cầu:

| Yêu cầu dữ liệu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Luôn đọc dữ liệu nguồn hiện tại, logic dùng ở nhiều nơi | View | Không cần quy trình refresh riêng; mỗi truy vấn đọc bảng nguồn. |
| Chỉ cần tập trung gian trong một statement | CTE | Scope rõ ràng và không cần quản lý vòng đời đối tượng. |
| Cần kết quả trung gian qua nhiều statement trong cùng session | Temporary table | Có thể lưu dòng, index và tái sử dụng trong session. |
| Nhiều session cần đọc kết quả tính sẵn, chấp nhận dữ liệu trễ | Bảng lưu kết quả | Kết quả được lưu và refresh theo lịch hoặc sự kiện. |
| Cần duyệt cây hoặc quan hệ nhiều cấp trong một truy vấn | Recursive CTE | Biểu đạt đệ quy trực tiếp trong SQL. |
| Cần kết quả riêng cho từng request, không chia sẻ giữa session | Temporary table hoặc CTE | Chọn theo số statement và nhu cầu index. |

Ví dụ dashboard doanh thu chấp nhận trễ 5 phút có thể đọc bảng summary được refresh mỗi 5 phút. Màn hình chi tiết đơn hàng cần trạng thái hiện tại có thể đọc view hoặc bảng nguồn trực tiếp. Một báo cáo chỉ cần nhiều bước tính trong một câu có thể dùng CTE. Một quy trình import cần đối chiếu nhiều bước trong một kết nối có thể dùng temporary table.

## 8. Quyền truy cập và bảo mật

View có thể tạo lớp truy cập chỉ công bố các cột được phép. Kết hợp `SQL SECURITY DEFINER` hoặc `SQL SECURITY INVOKER` để xác định quyền được dùng khi view chạy:

```sql
CREATE SQL SECURITY DEFINER VIEW v_public_customer AS
SELECT customer_id, customer_name
FROM customers
WHERE status = 'ACTIVE';
```

- `DEFINER`: quyền kiểm tra truy cập vào các đối tượng nền được xác định theo tài khoản definer của view.
- `INVOKER`: quyền được kiểm tra theo tài khoản gọi view.

Phải quản lý definer và quyền của tài khoản đó cẩn thận. Một view dùng definer có thể cho phép người dùng đọc dữ liệu nền mà họ không có quyền SELECT trực tiếp, nếu view và quyền được cấu hình phù hợp. Không cấp quyền rộng cho definer và không xem view là ranh giới bảo mật tự động.

Temporary table có phạm vi session, nhưng dữ liệu của nó vẫn có thể chứa thông tin nhạy cảm trong suốt vòng đời session. Bảng lưu kết quả là đối tượng permanent và cần phân quyền, backup, retention, audit như bảng nghiệp vụ khác. CTE chỉ tồn tại trong statement nhưng câu truy vấn vẫn cần quyền đọc các bảng nguồn theo cơ chế quyền tương ứng.

## 9. Các yếu tố hiệu năng cần kiểm tra

Khi lựa chọn một trong bốn cách, hãy kiểm tra:

1. **Execution plan:** view có merge hay materialize; CTE có materialize; temporary table có scan hay dùng index; bảng summary có access path phù hợp không.
2. **Chi phí tính toán:** logic được tính lại mỗi lần đọc hay chỉ tính khi refresh.
3. **Số lần tái sử dụng:** một statement, nhiều statement trong session hay nhiều session.
4. **Kích thước trung gian:** số dòng, độ rộng row và index cần tạo.
5. **Concurrency:** nhiều session có cùng refresh hoặc ghi temporary/result table không.
6. **Freshness:** dữ liệu cần mới đến mức nào và có thể chấp nhận stale read bao lâu.
7. **Vận hành:** ai tạo, refresh, drop, theo dõi lỗi và dọn dữ liệu cũ.

Các công cụ kiểm tra:

```sql
EXPLAIN FORMAT = TREE
SELECT *
FROM v_paid_orders
WHERE customer_id = 1001;

EXPLAIN ANALYZE
WITH recent_orders AS (
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE created_at >= CURRENT_DATE - INTERVAL 7 DAY
)
SELECT customer_id, SUM(total_amount)
FROM recent_orders
GROUP BY customer_id;
```

`EXPLAIN ANALYZE` thực thi truy vấn. Dùng với SELECT an toàn, giới hạn dữ liệu và môi trường phù hợp. Đừng đánh giá chỉ bằng độ ngắn của SQL hoặc số dòng code.

## 10. Tình huống lựa chọn thực tế

### Tình huống A: nhiều màn hình dùng cùng bộ lọc khách hàng hoạt động

Chọn view nếu nhiều truy vấn cần cùng logic lọc và join đơn giản, đồng thời cần dữ liệu mới từ bảng nguồn. Tạo index trên bảng nguồn theo các điều kiện truy vấn; kiểm tra view merge và quyền truy cập.

### Tình huống B: một báo cáo cần nhiều bước tổng hợp trong một câu

Chọn CTE để đặt tên các bước như `paid_orders`, `customer_totals`, `ranked_customers`. Nếu CTE được tham chiếu nhiều lần hoặc kết quả lớn, kiểm tra optimizer có materialize và chi phí thực tế.

### Tình huống C: job import cần dùng cùng tập khóa trong nhiều bước

Chọn temporary table để lưu tập khóa, tạo primary key/index và dùng trong nhiều statement. Drop bảng khi xong; bảo đảm connection pool không tái sử dụng session với dữ liệu tạm còn sót.

### Tình huống D: dashboard có nhiều người dùng và phép tổng hợp rất nặng

Chọn bảng lưu kết quả nếu dashboard có thể chấp nhận dữ liệu trễ theo một SLA rõ ràng. Thiết kế refresh idempotent, watermark, thời điểm công bố, chỉ số freshness và quy trình đối soát.

### Tình huống E: cần dữ liệu tổng hợp tạm thời chỉ trong một truy vấn

CTE thường là lựa chọn dễ đọc nhất. Không cần tạo view permanent hoặc bảng tạm nếu kết quả chỉ được dùng trong một statement.

## 11. Bảng quyết định nhanh

| Câu hỏi | Nếu câu trả lời là “có” | Lựa chọn nên xem xét |
| --- | --- | --- |
| Logic SELECT cần tái sử dụng giữa nhiều câu lệnh và session? | Có | View |
| Kết quả chỉ cần trong một statement? | Có | CTE |
| Cần giữ dữ liệu trung gian qua nhiều statement trong một session? | Có | Temporary table |
| Cần index riêng trên tập trung gian? | Có, và chỉ trong session | Temporary table |
| Nhiều session cần đọc kết quả đã tính sẵn? | Có | Bảng lưu kết quả |
| Có thể chấp nhận dữ liệu trễ và có quy trình refresh? | Có | Bảng lưu kết quả |
| Cần dữ liệu mới nhất từ bảng nguồn ở mỗi lần đọc? | Có | View hoặc truy vấn trực tiếp; CTE nếu cần cấu trúc nhiều bước |

Không nhất thiết chỉ dùng một loại. Một quy trình có thể dùng CTE để tính kết quả, nạp vào temporary table để kiểm tra nhiều bước, rồi ghi vào bảng lưu kết quả sau khi xác minh. Hãy chọn theo ranh giới dữ liệu và vòng đời, không ghép thêm cấu trúc nếu không có nhu cầu rõ ràng.

## 12. Quy trình thiết kế và vận hành

1. Viết rõ yêu cầu freshness: đọc ngay dữ liệu nguồn, snapshot trong statement, trong session hay kết quả refresh theo lịch.
2. Xác định số người dùng và phạm vi tái sử dụng: một câu, một session hay toàn hệ thống.
3. Xác định khối lượng trung gian và nhu cầu index.
4. Chọn view, CTE, temporary table hoặc bảng lưu kết quả theo ma trận ở trên.
5. Dùng EXPLAIN để kiểm tra merge/materialization, access path và số dòng ước lượng.
6. Nếu materialize hoặc lưu kết quả, đo thời gian tạo, dung lượng, index và thời gian đọc lại.
7. Thiết kế vòng đời: drop temporary table, refresh summary, dọn staging và theo dõi lỗi job.
8. Thiết kế quyền truy cập phù hợp, đặc biệt với view definer và bảng kết quả chứa dữ liệu nhạy cảm.
9. Kiểm tra concurrency, connection pool, transaction, metadata lock và khả năng retry.
10. Ghi rõ độ mới dữ liệu và thời điểm refresh để người dùng không hiểu nhầm kết quả đã cập nhật tức thời.

## 13. Lỗi lựa chọn thường gặp

- **Dùng view với kỳ vọng dữ liệu được lưu sẵn.** View thông thường lưu định nghĩa, không lưu kết quả; truy vấn vẫn phải đọc nguồn.
- **Dùng CTE như bảng dùng chung giữa nhiều statement.** CTE chỉ có scope trong một statement.
- **Tạo temporary table nhưng quên session scope.** Session khác không thấy dữ liệu; connection pool có thể giữ lại bảng tạm khi session được tái sử dụng.
- **Tạo bảng summary mà không có refresh contract.** Người đọc không biết dữ liệu cũ đến đâu và job có bỏ sót thay đổi không.
- **Cho rằng CTE luôn materialize.** Optimizer có thể merge hoặc materialize tùy cấu trúc và kế hoạch.
- **Cho rằng view luôn updatable.** Aggregate, DISTINCT, GROUP BY và các cấu trúc khác có thể làm view không cập nhật được.
- **Tạo index cho mọi temporary table.** Index có chi phí; chỉ tạo khi các bước sau thực sự dùng.
- **Dùng `CREATE OR REPLACE VIEW` mà không kiểm tra quyền/phụ thuộc.** Thay đổi định nghĩa có thể ảnh hưởng ứng dụng và quyền truy cập.
- **Làm mới bảng kết quả bằng nhiều statement không nguyên tử.** Người đọc có thể nhìn thấy dữ liệu trộn giữa hai lần refresh; cần transaction hoặc quy trình staging/công bố phù hợp.

## 14. Bài tập tự kiểm tra

1. View lưu định nghĩa hay lưu kết quả? Vì sao view không tự động tăng tốc truy vấn?
2. Khi nào MySQL có thể merge view và khi nào có thể materialize?
3. CTE khác temporary table ở phạm vi và vòng đời như thế nào?
4. Vì sao không nên mặc định CTE luôn được materialize?
5. Nêu một trường hợp recursive CTE phù hợp hơn view hoặc temporary table.
6. Khi nào temporary table có lợi thế nhờ index riêng và tái sử dụng qua nhiều statement?
7. Vì sao connection pool cần dọn temporary table trước khi tái sử dụng session?
8. Khi nào nên lưu kết quả vào summary table thay vì tính lại bằng view?
9. Phân biệt full refresh và incremental refresh; watermark cần bảo đảm điều gì?
10. Làm thế nào công bố kết quả refresh để session đọc không thấy dữ liệu nửa cũ nửa mới?

Chọn cấu trúc phù hợp bằng cách trả lời bốn câu hỏi: **dữ liệu cần mới đến đâu, ai cần tái sử dụng, cần giữ trong bao lâu và có cần index riêng không**. View và CTE tổ chức logic truy vấn; temporary table giữ kết quả trung gian trong session; bảng lưu kết quả phục vụ nhiều session khi có quy trình refresh và kiểm soát freshness rõ ràng.
