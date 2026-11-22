# Giới hạn của view và cách lưu kết quả báo cáo bằng bảng riêng

Bài học thuộc chương **View và bảng tạm** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. View giúp đặt tên cho một câu truy vấn và cung cấp giao diện dữ liệu thống nhất, nhưng MySQL không lưu kết quả view như một materialized view tự động làm mới. Khi báo cáo cần dữ liệu đã tính trước, truy cập nhanh, dùng chung giữa nhiều session hoặc giữ ảnh chụp tại một thời điểm, cần thiết kế bảng lưu kết quả và quy trình cập nhật riêng.

Sau bài này, bạn có thể nhận diện giới hạn của view trong MySQL, phân biệt MERGE với TEMPTABLE, hiểu vì sao view không có index riêng và không thể tham chiếu temporary table, lựa chọn view hay bảng báo cáo, thiết kế bảng snapshot/summary, làm mới toàn bộ hoặc tăng dần, công bố dữ liệu mới an toàn và theo dõi độ mới của báo cáo.

## 1. View là gì và dữ liệu được lưu ở đâu?

View là một đối tượng database lưu định nghĩa SELECT. Khi ứng dụng truy vấn view, MySQL xử lý định nghĩa đó để tạo result set từ các bảng hoặc view nền.

Ví dụ:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;

CREATE VIEW v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM orders
WHERE status = 'PAID';
~~~

View v_paid_orders lưu câu SELECT và metadata của view. Nó không lưu một bản sao cố định của các hàng PAID.

Khi bảng orders thay đổi, lần truy vấn view tiếp theo nhìn thấy dữ liệu theo trạng thái và transaction hiện tại của các bảng nền. Không cần chạy lệnh refresh cho view thông thường.

Có thể kiểm tra:

~~~sql
SELECT *
FROM v_paid_orders
ORDER BY created_at DESC, order_id DESC;
~~~

Câu truy vấn vẫn phải đọc dữ liệu từ bảng nền. Nếu bảng có hàng triệu bản ghi, view không tự biến truy vấn thành thao tác đọc một bảng kết quả đã tính sẵn.

### View không phải materialized view

Một số hệ quản trị có materialized view, tức lưu kết quả truy vấn và có cơ chế refresh. MySQL không cung cấp đối tượng materialized view native tương đương theo cú pháp CREATE MATERIALIZED VIEW.

Trong MySQL, cần phân biệt:

| Cơ chế | Có lưu kết quả lâu dài? | Ai cập nhật? | Dùng giữa nhiều session? |
|---|---|---|---|
| View thông thường | Không | MySQL thực thi SELECT khi được gọi | Có |
| View dùng ALGORITHM=TEMPTABLE | Chỉ có bảng tạm phục vụ statement | MySQL trong lúc thực thi statement | Không phải cache kết quả dùng chung |
| Temporary table | Có trong phạm vi session | Ứng dụng hoặc stored program | Không, chỉ session tạo bảng |
| Bảng báo cáo/snapshot | Có | Job, ứng dụng hoặc quy trình ETL | Có |

ALGORITHM=TEMPTABLE không biến view thành materialized view. Temporary table được tạo để xử lý một lần thực thi; dữ liệu đó không phải bản lưu báo cáo lâu dài cho lần gọi sau.

## 2. Hai thuật toán xử lý view: MERGE và TEMPTABLE

MySQL hỗ trợ ba giá trị ALGORITHM trong CREATE VIEW hoặc ALTER VIEW:

- MERGE
- TEMPTABLE
- UNDEFINED

### MERGE

Với MERGE, MySQL kết hợp định nghĩa view vào câu truy vấn tham chiếu view. Các cột, điều kiện và biểu thức của view được đưa vào truy vấn ngoài.

Ví dụ:

~~~sql
CREATE ALGORITHM = MERGE VIEW v_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM orders
WHERE status = 'PAID';
~~~

Truy vấn:

~~~sql
SELECT
    order_id,
    total_amount
FROM v_paid_orders
WHERE customer_id = 42;
~~~

Về mặt khái niệm, MySQL có thể xử lý như:

~~~sql
SELECT
    order_id,
    total_amount
FROM orders
WHERE status = 'PAID'
  AND customer_id = 42;
~~~

Nhờ MERGE, optimizer có cơ hội đẩy điều kiện của truy vấn ngoài xuống bảng nền, dùng index của bảng nền và tối ưu kế hoạch tổng thể.

MERGE thường hiệu quả khi view chỉ là lớp đặt tên, lọc hoặc chiếu các cột từ bảng nền.

### TEMPTABLE

Với TEMPTABLE, MySQL lấy kết quả của view vào một internal temporary table, sau đó dùng bảng tạm đó để hoàn thành statement.

Ví dụ:

~~~sql
CREATE ALGORITHM = TEMPTABLE VIEW v_customer_totals AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Khi truy vấn:

~~~sql
SELECT *
FROM v_customer_totals
WHERE total_amount >= 10000;
~~~

MySQL cần tính kết quả nhóm của view rồi sử dụng kết quả tạm cho phần truy vấn ngoài. Đây là một bước materialization trong quá trình thực thi statement, không phải dữ liệu được lưu bền vững sau khi statement kết thúc.

Một lý do có thể chọn TEMPTABLE là MySQL có thể giải phóng khóa trên các bảng nền sau khi đã tạo xong bảng tạm, trước khi tiếp tục xử lý phần còn lại của statement. Điều này đôi khi giúp giảm thời gian giữ khóa trên bảng nền.

### UNDEFINED

UNDEFINED cho phép MySQL tự chọn thuật toán. Nếu có thể, MySQL ưu tiên MERGE vì thường hiệu quả hơn và view được xử lý bằng temporary table thì không thể cập nhật.

Nếu không ghi ALGORITHM, thuật toán mặc định còn phụ thuộc cấu hình optimizer, bao gồm cờ derived_merge trong optimizer_switch.

Kiểm tra:

~~~sql
SELECT @@optimizer_switch;
~~~

Không nên cố định TEMPTABLE hoặc MERGE chỉ dựa trên tên gọi. Hãy dùng EXPLAIN để xem view được xử lý như thế nào và đo trên truy vấn thực tế.

### Khi nào MERGE không thể áp dụng?

Một số cấu trúc làm view không thể được merge, ví dụ:

- DISTINCT.
- GROUP BY.
- HAVING.
- Aggregate function.
- Một số truy vấn có LIMIT.
- UNION hoặc cấu trúc cần materialization khác.

Khi MERGE không khả dụng, MySQL có thể chuyển sang cách xử lý bằng temporary table. Nếu khai báo ALGORITHM=MERGE nhưng view chỉ có thể xử lý bằng temporary table, MySQL phát warning và đặt thuật toán thành UNDEFINED.

## 3. Giới hạn quan trọng: view không có index riêng

Không thể tạo index trực tiếp trên view trong MySQL.

Ví dụ sau không hợp lệ:

~~~sql
CREATE INDEX idx_v_paid_customer
ON v_paid_orders (customer_id);
~~~

Index phải được tạo trên bảng nền:

~~~sql
CREATE INDEX idx_orders_status_customer
ON orders (status, customer_id);
~~~

Với view dùng MERGE, optimizer có thể sử dụng index của bảng nền như thể truy vấn đang tham chiếu bảng đó.

Với view dùng TEMPTABLE, kết quả view được materialize vào internal temporary table. View dạng này không thể tận dụng index của bảng nền cho việc truy cập kết quả tạm theo cùng cách MERGE; index có thể được sử dụng trong quá trình tạo temporary table, nhưng không có index do người dùng định nghĩa trực tiếp trên view.

Điều đó dẫn đến hai kết luận:

1. View không thay thế thiết kế index trên bảng nền.
2. Nếu báo cáo cần đọc nhanh một tập kết quả đã tổng hợp, một bảng báo cáo riêng có index phù hợp có thể hữu ích hơn việc tính lại view mỗi lần.

### View có thể làm truy vấn khó tối ưu hơn

Một view phức tạp có thể chứa JOIN, GROUP BY, DISTINCT hoặc nhiều lớp view lồng nhau. Khi đó, việc truy vấn view có thể tạo ra materialization, sort hoặc bước trung gian lớn.

Hãy kiểm tra:

~~~sql
EXPLAIN FORMAT=TREE
SELECT *
FROM v_customer_totals
WHERE total_amount >= 10000;
~~~

Nếu phiên bản/cách hiển thị EXPLAIN không hỗ trợ TREE cho trường hợp cụ thể, dùng EXPLAIN mặc định hoặc FORMAT=JSON.

Tìm các dấu hiệu:

- Materialize.
- Temporary table.
- Aggregate.
- Sort.
- Full scan trên bảng nền.
- Ước lượng rows lớn ở các iterator trung gian.

Không kết luận mọi view đều chậm. View MERGE đơn giản thường chỉ là lớp trừu tượng cho truy vấn nền và có thể có kế hoạch tương đương SQL viết trực tiếp.

## 4. View không phải lúc nào cũng cập nhật được

Một số view cho phép INSERT, UPDATE hoặc DELETE thông qua view để thay đổi bảng nền. Nhưng điều này chỉ hợp lệ khi MySQL xác định được quan hệ một-một giữa hàng view và hàng bảng nền, đồng thời view đáp ứng các điều kiện updatability.

Các cấu trúc thường làm view không cập nhật được:

- Aggregate như SUM, COUNT, MIN, MAX.
- Window function.
- DISTINCT.
- GROUP BY.
- HAVING.
- UNION hoặc UNION ALL.
- Subquery trong select list.
- Một số loại JOIN.
- Tham chiếu một view không updatable trong FROM.
- ALGORITHM=TEMPTABLE.
- Chỉ chọn literal mà không có bảng nền.

Ví dụ view tổng hợp:

~~~sql
CREATE VIEW v_customer_order_summary AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id;
~~~

Không thể cập nhật một hàng tổng hợp như thể đó là một hàng orders cụ thể:

~~~sql
UPDATE v_customer_order_summary
SET total_amount = 1000
WHERE customer_id = 42;
~~~

MySQL từ chối vì một giá trị tổng hợp không ánh xạ một-một về một hàng nền.

Kiểm tra trạng thái:

~~~sql
SELECT
    TABLE_NAME,
    IS_UPDATABLE,
    CHECK_OPTION,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = DATABASE();
~~~

IS_UPDATABLE cho biết cờ updatability được xác định khi tạo view. View updatable vẫn có thể không insertable nếu thiếu cột bắt buộc hoặc cột view là biểu thức.

Đừng thiết kế view báo cáo tổng hợp với kỳ vọng người dùng có thể sửa số tổng rồi MySQL tự suy ra cách cập nhật các hàng nguồn.

## 5. View có thể bị vô hiệu khi schema bảng nền thay đổi

Định nghĩa view được cố định tại thời điểm CREATE VIEW. Ví dụ:

~~~sql
CREATE VIEW v_order_basic AS
SELECT *
FROM orders;
~~~

Nếu sau đó thêm cột mới vào orders, cột mới không tự động xuất hiện trong view. SELECT * đã được mở rộng thành danh sách cột tại thời điểm tạo view.

Nếu một cột đang được view tham chiếu bị DROP hoặc đổi theo cách không còn tương thích, việc truy vấn view có thể lỗi.

MySQL không nhất thiết cảnh báo ngay khi ALTER/DROP bảng nền làm view mất hiệu lực. Lỗi có thể chỉ xuất hiện khi view được sử dụng.

Kiểm tra:

~~~sql
CHECK TABLE v_order_basic;
~~~

Lấy định nghĩa:

~~~sql
SHOW CREATE VIEW v_order_basic;
~~~

Quy tắc thiết kế:

- Tránh SELECT * trong view dùng lâu dài.
- Ghi rõ danh sách cột.
- Sau migration bảng nền, kiểm tra các view phụ thuộc.
- Cập nhật view trong cùng kế hoạch release schema.
- Không coi việc ALTER TABLE thành công là bằng chứng mọi view vẫn hợp lệ.

## 6. Các giới hạn cú pháp và phụ thuộc khác

MySQL áp dụng một số giới hạn riêng cho định nghĩa view:

- SELECT trong view không được tham chiếu system variable hoặc user-defined variable.
- Trong stored program, view không được tham chiếu parameter hoặc local variable của chương trình.
- Không thể tham chiếu parameter của prepared statement trong định nghĩa view.
- Mọi bảng/view được tham chiếu phải tồn tại khi tạo view.
- Không thể tham chiếu TEMPORARY table trong định nghĩa view.
- Không thể tạo TEMPORARY view.
- Không thể gắn trigger trực tiếp vào view.
- Một view có thể tham chiếu tối đa 61 bảng trong định nghĩa.

Ví dụ không thể tạo view dựa trên bảng tạm:

~~~sql
CREATE TEMPORARY TABLE tmp_daily_orders (
    order_id BIGINT NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;

CREATE VIEW v_tmp_daily_orders AS
SELECT *
FROM tmp_daily_orders;
~~~

Lệnh CREATE VIEW thất bại vì view definition không được tham chiếu temporary table.

Ngoài ra, temporary table chỉ tồn tại trong session tạo nó. Một session khác không thể dùng tên bảng tạm đó để truy vấn kết quả.

### ORDER BY và LIMIT bên trong view

ORDER BY được phép trong định nghĩa view, nhưng nếu truy vấn ngoài có ORDER BY riêng, thứ tự trong view bị bỏ qua.

Ví dụ:

~~~sql
CREATE VIEW v_recent_orders AS
SELECT
    order_id,
    created_at
FROM orders
ORDER BY created_at DESC;
~~~

Truy vấn:

~~~sql
SELECT *
FROM v_recent_orders
ORDER BY order_id;
~~~

Kết quả được sắp xếp theo order_id của truy vấn ngoài.

Không dựa vào ORDER BY bên trong view để bảo đảm thứ tự của mọi truy vấn sử dụng view. Nếu kết quả cần thứ tự xác định, hãy đặt ORDER BY tại câu SELECT cuối cùng.

Không nên đặt LIMIT trong view rồi thêm LIMIT khác ở truy vấn ngoài. MySQL mô tả tác động của các clause như LIMIT trong cả hai tầng là không xác định; hãy đặt giới hạn ở đúng tầng truy vấn thể hiện yêu cầu nghiệp vụ.

## 7. View và quyền truy cập dữ liệu

View có thể đóng vai trò lớp giao diện bảo mật, nhưng cần chọn đúng SQL SECURITY.

- SQL SECURITY DEFINER: kiểm tra quyền truy cập bảng nền theo tài khoản DEFINER của view.
- SQL SECURITY INVOKER: kiểm tra quyền theo tài khoản gọi view.

Ví dụ:

~~~sql
CREATE DEFINER = 'report_owner'@'localhost'
SQL SECURITY DEFINER
VIEW v_public_order_report AS
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID';
~~~

Ứng dụng có thể được cấp SELECT trên view mà không được cấp SELECT trực tiếp trên toàn bộ bảng orders, tùy chính sách quyền.

Kiểm tra:

~~~sql
SHOW CREATE VIEW v_public_order_report;
~~~

Cần quản lý tài khoản DEFINER, quyền trên bảng nền và vòng đời tài khoản. Nếu DEFINER không còn tồn tại hoặc mất quyền cần thiết, view có thể không hoạt động như mong đợi.

View không tự bảo đảm rằng dữ liệu nhạy cảm đã được ẩn nếu vẫn cấp quyền truy cập bảng nền trực tiếp cho người dùng.

## 8. Khi nào nên dùng view?

View phù hợp khi:

- Cần tái sử dụng câu SELECT.
- Muốn che giấu JOIN hoặc điều kiện lọc lặp lại.
- Muốn cung cấp một giao diện cột ổn định cho ứng dụng.
- Muốn giới hạn cột/hàng được phép đọc qua SQL SECURITY phù hợp.
- Kết quả cần phản ánh dữ liệu hiện tại mỗi lần truy vấn.
- Chi phí tính toán truy vấn đủ thấp.

Ví dụ view đơn giản:

~~~sql
CREATE ALGORITHM = MERGE
SQL SECURITY INVOKER
VIEW v_customer_paid_orders AS
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM orders
WHERE status = 'PAID';
~~~

View phù hợp cho ứng dụng cần truy vấn các đơn PAID mới nhất theo từng customer. Ứng dụng vẫn có thể kết hợp WHERE, ORDER BY và LIMIT trên view.

## 9. Khi nào nên lưu kết quả báo cáo vào bảng riêng?

Nên cân nhắc bảng báo cáo khi có một hoặc nhiều yêu cầu:

- Báo cáo tổng hợp nặng được nhiều người truy cập lặp lại.
- Cần giữ snapshot theo ngày, tháng, kỳ chốt sổ hoặc thời điểm chạy.
- Cần index riêng cho kết quả báo cáo.
- Cần lưu kết quả để đối soát hoặc audit.
- Cần kiểm soát độ mới dữ liệu theo lịch.
- Cần tránh tính lại nhiều JOIN/GROUP BY trên bảng giao dịch lớn.
- Muốn tách tải báo cáo khỏi workload giao dịch.

Ví dụ báo cáo doanh thu theo ngày và sản phẩm. Nếu mỗi dashboard request phải JOIN orders, order_items và products rồi GROUP BY trên hàng chục triệu dòng, việc tính lại có thể tốn CPU, I/O và ảnh hưởng giao dịch.

Một bảng summary lưu sẵn số lượng đơn và doanh thu theo ngày giúp dashboard đọc ít hàng hơn.

### Snapshot table và summary table

| Loại bảng | Lưu gì? | Ví dụ | Mục tiêu |
|---|---|---|---|
| Snapshot | Trạng thái dữ liệu tại một thời điểm | Số dư tài khoản cuối ngày | Đối soát, lịch sử, báo cáo chốt kỳ |
| Summary/Aggregate | Giá trị đã nhóm/tổng hợp | Doanh thu theo ngày, sản phẩm, khu vực | Dashboard, phân tích nhanh |
| Report cache | Kết quả truy vấn được lưu để đọc lại | Danh sách Top sản phẩm tuần | Giảm tính toán lặp |
| Staging table | Dữ liệu đang được xây dựng trước khi công bố | Bản summary mới của ngày | Tách bước tính khỏi bước publish |

Bảng báo cáo là dữ liệu được quản lý riêng. Nó không tự cập nhật khi bảng nguồn thay đổi; phải có quy trình refresh.

## 10. Thiết kế bảng báo cáo có schema rõ ràng

Không nên tạo bảng báo cáo một cách tùy tiện chỉ bằng CREATE TABLE ... SELECT rồi mặc định nó có toàn bộ đặc tính của bảng nguồn.

CREATE TABLE ... SELECT có thể tạo cột từ biểu thức SELECT, nhưng một số thuộc tính không được giữ nguyên như mong đợi. Ví dụ AUTO_INCREMENT không được giữ lại theo cách sao chép schema thông thường; VARCHAR có thể được chuyển thành CHAR tùy biểu thức và kiểu suy luận.

Hãy khai báo schema đích rõ ràng:

~~~sql
CREATE TABLE report_daily_sales (
    report_date DATE NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    quantity_sold DECIMAL(18,3) NOT NULL,
    revenue DECIMAL(18,2) NOT NULL,
    refreshed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (report_date, product_id),
    KEY idx_report_product_date (product_id, report_date)
) ENGINE=InnoDB;
~~~

Các quyết định cần đưa ra:

- Grain: một hàng đại diện cho ngày, sản phẩm hay ngày + sản phẩm?
- Khóa chính: tổ hợp nào xác định duy nhất một hàng?
- Kiểu dữ liệu: đủ precision cho tổng tiền và số lượng?
- Index: dashboard thường lọc theo ngày hay sản phẩm?
- Thời gian: dùng DATE, DATETIME hoặc timestamp theo múi giờ nghiệp vụ?
- Freshness: dữ liệu được cập nhật đến thời điểm nào?
- Retention: giữ snapshot bao lâu?
- Rebuild: có thể tạo lại từ dữ liệu nguồn hay không?

Grain phải rõ. Nếu một hàng đại diện cho ngày + sản phẩm, khóa chính phù hợp là (report_date, product_id). Không được dùng product_id đơn lẻ nếu một sản phẩm xuất hiện ở nhiều ngày.

## 11. Xây dựng bảng summary từ dữ liệu nguồn

Giả sử có ba bảng:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(18,3) NOT NULL,
    unit_price DECIMAL(18,2) NOT NULL,
    KEY idx_items_order (order_id),
    KEY idx_items_product (product_id)
) ENGINE=InnoDB;
~~~

Bảng orders đã có status và created_at như phần trước.

Tạo summary theo ngày và sản phẩm:

~~~sql
INSERT INTO report_daily_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    DATE(o.created_at) AS report_date,
    oi.product_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity) AS quantity_sold,
    SUM(oi.quantity * oi.unit_price) AS revenue,
    CURRENT_TIMESTAMP(6) AS refreshed_at
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY
    DATE(o.created_at),
    oi.product_id;
~~~

Đây là ví dụ minh họa. Trong hệ thống thực tế, cần xác định chính xác quy tắc doanh thu:

- Dùng giá tại thời điểm đặt hàng hay giá hiện tại của sản phẩm?
- Trừ discount ở cấp order hay order item?
- Xử lý hoàn tiền và hủy đơn thế nào?
- Có tính thuế, phí vận chuyển hay không?
- Đơn đổi trạng thái sau khi đã tổng hợp được xử lý ra sao?

Nếu nghiệp vụ có refund hoặc điều chỉnh sau thanh toán, bảng summary cần phản ánh quy tắc kế toán/kinh doanh thay vì chỉ SUM(quantity * unit_price).

## 12. Làm mới toàn bộ bảng báo cáo bằng DELETE + INSERT

Cách đơn giản là xóa dữ liệu hiện tại và chèn lại trong một transaction InnoDB:

~~~sql
START TRANSACTION;

DELETE FROM report_daily_sales;

INSERT INTO report_daily_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    DATE(o.created_at),
    oi.product_id,
    COUNT(DISTINCT o.order_id),
    SUM(oi.quantity),
    SUM(oi.quantity * oi.unit_price),
    CURRENT_TIMESTAMP(6)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY
    DATE(o.created_at),
    oi.product_id;

COMMIT;
~~~

Với InnoDB, thay đổi DELETE và INSERT chỉ được nhìn thấy như một transaction đã commit. Reader chạy theo MVCC có thể tiếp tục đọc phiên bản đã commit trước đó trong khi refresh chưa hoàn tất; sau COMMIT, reader mới thấy dữ liệu mới.

Ưu điểm:

- Dễ triển khai.
- Có thể rollback toàn bộ nếu INSERT thất bại.
- Không để người đọc thấy bảng bị xóa sạch ở giữa transaction.

Nhược điểm:

- DELETE nhiều hàng tạo undo và redo.
- Transaction dài giữ tài nguyên, có thể ảnh hưởng purge và replication.
- Cần đủ dung lượng undo/log và thời gian khóa phù hợp.
- Nếu báo cáo lớn, transaction rebuild có thể gây áp lực I/O.

Đây là lựa chọn phù hợp khi bảng báo cáo vừa phải và thời gian rebuild chấp nhận được.

## 13. Vì sao không dùng TRUNCATE rồi INSERT trong cùng transaction?

TRUNCATE TABLE nhanh hơn DELETE toàn bộ hàng trong nhiều trường hợp, nhưng TRUNCATE là DDL và gây implicit commit.

Ví dụ:

~~~sql
START TRANSACTION;

TRUNCATE TABLE report_daily_sales;

INSERT INTO report_daily_sales (...)
SELECT ...;

ROLLBACK;
~~~

Không được kỳ vọng ROLLBACK khôi phục dữ liệu cũ. TRUNCATE gây commit ngầm và không thể rollback như DML. Nếu INSERT sau đó thất bại, bảng báo cáo có thể vẫn rỗng hoặc chỉ chứa dữ liệu được chèn một phần tùy cách xử lý lỗi.

TRUNCATE còn:

- Không kích hoạt DELETE trigger.
- Có yêu cầu quyền DROP.
- Có giới hạn khi bảng bị bảng khác tham chiếu bằng foreign key.
- Đặt lại AUTO_INCREMENT về giá trị bắt đầu.
- Được ghi binary log như DDL.

Dùng TRUNCATE chỉ khi chấp nhận rõ ràng tính chất DDL và đã có phương án publish an toàn. Không ghép TRUNCATE với INSERT trong một transaction rồi tin rằng ROLLBACK sẽ bảo vệ dữ liệu cũ.

## 14. Làm mới an toàn bằng staging table và RENAME TABLE

Với bảng báo cáo lớn, có thể xây dựng phiên bản mới ở một bảng staging rồi đổi tên để công bố.

Luồng:

1. Giữ bảng report_current phục vụ người đọc.
2. Chuẩn bị report_next có cùng schema.
3. Xóa dữ liệu cũ trong report_next.
4. Tính toàn bộ dữ liệu mới vào report_next.
5. Kiểm tra row count, tổng tiền, khoảng ngày và các điều kiện chất lượng.
6. Dùng một câu RENAME TABLE nhiều bảng để đổi current và next.
7. Bảng cũ trở thành report_next cho lần refresh sau.

### Tạo bảng staging

Nếu bảng báo cáo không có foreign key cần sao chép:

~~~sql
CREATE TABLE report_next LIKE report_current;
~~~

CREATE TABLE ... LIKE sao chép cột và index, cùng một số thuộc tính schema, nhưng không sao chép foreign key definitions. Nếu bảng có CHECK constraints, MySQL tạo constraint names mới. Cần xác minh lại các đặc tính khác như trigger, partition, tablespace option và quyền trước khi dùng cách này trong production.

Nếu report_next đã tồn tại từ lần chạy trước, có thể làm rỗng staging trước khi nạp:

~~~sql
TRUNCATE TABLE report_next;
~~~

Đây là thao tác DDL trên bảng staging, không phải bảng current. Nó vẫn gây implicit commit trong session, nên thực hiện ngoài transaction nghiệp vụ khác.

### Nạp dữ liệu mới

~~~sql
INSERT INTO report_next (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    DATE(o.created_at),
    oi.product_id,
    COUNT(DISTINCT o.order_id),
    SUM(oi.quantity),
    SUM(oi.quantity * oi.unit_price),
    CURRENT_TIMESTAMP(6)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY
    DATE(o.created_at),
    oi.product_id;
~~~

### Kiểm tra trước khi publish

~~~sql
SELECT
    COUNT(*) AS report_rows,
    MIN(report_date) AS first_report_date,
    MAX(report_date) AS last_report_date,
    SUM(revenue) AS total_revenue
FROM report_next;
~~~

So sánh với truy vấn đối soát hoặc các số liệu kiểm soát độc lập. Không publish nếu staging chưa đầy đủ hoặc sai tổng.

### Hoán đổi tên bảng

Giả sử report_current và report_next đều là InnoDB và report_previous không tồn tại:

~~~sql
RENAME TABLE
    report_current TO report_previous,
    report_next TO report_current,
    report_previous TO report_next;
~~~

Các thao tác rename được thực hiện theo thứ tự trái sang phải trong cùng câu lệnh. Sau khi hoàn tất:

- report_current chứa dữ liệu mới.
- report_next chứa phiên bản cũ.
- Người đọc sử dụng tên report_current và thấy bảng đã được công bố.

Với InnoDB, RENAME TABLE nhiều bảng là atomic DDL khi tất cả các bảng liên quan dùng engine hỗ trợ atomic DDL. Atomic DDL bảo vệ tính nguyên tử của thao tác DDL, nhưng DDL vẫn gây implicit commit; nó không trở thành một phần có thể rollback của transaction ứng dụng.

### Các điểm phải kiểm tra trước khi dùng rename swap

- Tất cả bảng tham gia có storage engine hỗ trợ atomic DDL.
- Không có tên report_previous bị chiếm.
- Người đọc có thể chịu metadata lock trong thời gian rename.
- View, foreign key, trigger, grant và ứng dụng phụ thuộc tên bảng đã được đánh giá.
- Quy trình rollback sau publish được diễn tập.
- Bảng cũ được giữ lại đủ lâu để đối soát rồi mới xóa hoặc tái sử dụng.
- Job refresh có khóa điều phối để không chạy hai lần chồng lấn.

RENAME TABLE có thể ảnh hưởng các đối tượng phụ thuộc tên bảng. Không mặc định rằng mọi view hoặc foreign key sẽ tự được cập nhật đúng theo ý muốn sau khi đổi tên. Hãy kiểm tra SHOW CREATE VIEW, metadata và thử migration trên staging.

## 15. Làm mới tăng dần (incremental refresh)

Nếu bảng nguồn rất lớn, tính lại toàn bộ báo cáo mỗi lần có thể tốn kém. Incremental refresh chỉ tính lại phần dữ liệu bị ảnh hưởng.

Ví dụ chỉ làm mới các ngày gần đây:

~~~sql
DELETE FROM report_daily_sales
WHERE report_date >= CURRENT_DATE - INTERVAL 7 DAY;

INSERT INTO report_daily_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    DATE(o.created_at),
    oi.product_id,
    COUNT(DISTINCT o.order_id),
    SUM(oi.quantity),
    SUM(oi.quantity * oi.unit_price),
    CURRENT_TIMESTAMP(6)
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
  AND o.created_at >= CURRENT_DATE - INTERVAL 7 DAY
GROUP BY
    DATE(o.created_at),
    oi.product_id;
~~~

Nên chạy hai bước DML trong cùng transaction nếu cần người đọc chỉ nhìn thấy dữ liệu cũ hoặc dữ liệu mới, không nhìn thấy khoảng trống giữa chúng.

### Vì sao phải tính lại cả khoảng thời gian?

Nếu đơn hàng cũ đổi từ PENDING sang PAID, nó có thể làm thay đổi báo cáo của ngày tạo đơn. Nếu đơn bị refund, hủy, sửa số lượng hoặc điều chỉnh giá, dữ liệu của ngày cũ cũng phải được cập nhật.

Một incremental refresh chỉ đọc đơn mới theo created_at có thể bỏ sót thay đổi xảy ra trên dữ liệu cũ.

Các cách xác định phần bị ảnh hưởng:

- Dùng updated_at để tìm bản ghi thay đổi.
- Dùng change log hoặc event table.
- Ghi nhận ngày/nhóm cần rebuild khi nghiệp vụ cập nhật.
- Recompute một cửa sổ thời gian gần đây để xử lý dữ liệu đến trễ.
- Có job đối soát định kỳ để phát hiện chênh lệch.

Nếu dữ liệu có thể sửa sau nhiều tháng, cửa sổ bảy ngày không đủ. Cần cơ chế change tracking hoặc rebuild theo khóa nghiệp vụ.

### UPSERT vào summary table

Với khóa duy nhất theo ngày + sản phẩm:

~~~sql
INSERT INTO report_daily_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
VALUES
    ('2026-11-18', 100, 12, 25.000, 5000.00, CURRENT_TIMESTAMP(6))
AS new
ON DUPLICATE KEY UPDATE
    order_count = new.order_count,
    quantity_sold = new.quantity_sold,
    revenue = new.revenue,
    refreshed_at = new.refreshed_at;
~~~

Cú pháp row alias sau VALUES có trong các phiên bản MySQL hiện đại. Nếu ứng dụng hỗ trợ nhiều phiên bản cũ, hãy dùng cú pháp tương thích với phiên bản triển khai và kiểm thử trước.

UPSERT chỉ cập nhật các nhóm có trong nguồn mới. Nếu một nhóm trước đó có dữ liệu nhưng nay không còn hàng nguồn, câu UPSERT không tự xóa nhóm cũ. Cần xóa/rebuild phạm vi bị ảnh hưởng hoặc dùng một quy trình reconcile.

## 16. Đảm bảo báo cáo phản ánh một thời điểm dữ liệu rõ ràng

Bảng báo cáo phải trả lời được câu hỏi: “Số liệu này đúng tại thời điểm nào?”

Nên lưu metadata refresh:

~~~sql
CREATE TABLE report_refresh_state (
    report_name VARCHAR(100) NOT NULL PRIMARY KEY,
    refresh_started_at DATETIME(6) NULL,
    refresh_completed_at DATETIME(6) NULL,
    source_watermark DATETIME(6) NULL,
    row_count BIGINT UNSIGNED NULL,
    status ENUM('RUNNING', 'SUCCEEDED', 'FAILED') NOT NULL,
    error_message VARCHAR(1000) NULL
) ENGINE=InnoDB;
~~~

Các trường này giúp dashboard hoặc người vận hành biết:

- Job đang chạy hay đã hoàn thành.
- Lần refresh thành công gần nhất.
- Dữ liệu nguồn đã được xử lý đến mốc nào.
- Có bao nhiêu hàng đã được tạo.
- Lần chạy gần nhất thất bại vì lý do gì.

Không cập nhật trạng thái SUCCEEDED trước khi dữ liệu đã được publish thành công. Nếu dùng staging + rename, cập nhật metadata sau bước publish và dùng một transaction DML ngắn cho bảng trạng thái.

### Snapshot theo thời điểm

Nếu cần báo cáo “cuối ngày 2026-11-18”, đừng chỉ lưu ngày mà không xác định múi giờ và thời điểm chốt.

Ví dụ:

- Ngày nghiệp vụ theo Asia/Ho_Chi_Minh.
- Mốc chốt 23:59:59 theo múi giờ đó.
- Nguồn dữ liệu đã được xử lý đến một watermark cụ thể.
- Có quy tắc xử lý đơn đến muộn hoặc điều chỉnh sau ngày chốt.

Lưu thời điểm refresh bằng DATETIME(6) theo quy ước UTC hoặc quy ước thống nhất của hệ thống. Đừng trộn timestamp local và UTC trong cùng báo cáo.

### Nhất quán khi đọc nhiều bảng nguồn

Báo cáo thường JOIN nhiều bảng. Cần quyết định liệu mọi bảng nguồn phải được đọc từ cùng một snapshot hay chấp nhận dữ liệu thay đổi trong lúc job chạy.

Với InnoDB, consistent read và isolation level ảnh hưởng việc nhìn thấy thay đổi đồng thời. Transaction kéo dài có thể giữ read view và gây áp lực undo/purge. Với báo cáo rất lớn, hãy cân nhắc chạy trên read replica phù hợp, tạo snapshot theo watermark hoặc chia batch có quy tắc rõ ràng.

Không kéo dài transaction hàng giờ mà không đo tác động đến purge, replication lag và dung lượng undo.

## 17. Temporary table không thay thế bảng báo cáo dùng chung

Temporary table hữu ích để lưu dữ liệu trung gian trong một session:

~~~sql
CREATE TEMPORARY TABLE tmp_customer_totals (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    total_amount DECIMAL(18,2) NOT NULL
) ENGINE=InnoDB;
~~~

Sau đó:

~~~sql
INSERT INTO tmp_customer_totals (customer_id, total_amount)
SELECT
    customer_id,
    SUM(total_amount)
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

Temporary table phù hợp cho:

- Nhiều bước xử lý trong cùng session.
- Tập dữ liệu trung gian của một request/job.
- Tách truy vấn phức tạp thành các bước dễ kiểm tra.
- Tránh tính lại một tập trung gian nhiều lần trong cùng session.

Nhưng temporary table có giới hạn:

- Chỉ session tạo bảng mới nhìn thấy nó.
- Bảng tự biến mất khi session kết thúc.
- Một session khác không thể đọc kết quả.
- Không thể tham chiếu temporary table trong định nghĩa view.
- Không thể tạo TEMPORARY view.
- Không thể tham chiếu cùng một temporary table nhiều lần trong một câu truy vấn; có thể gặp lỗi Can't reopen table.
- Temporary table không phải nơi lưu snapshot báo cáo lâu dài.

Nếu ứng dụng dùng connection pool, temporary table có thể tồn tại lâu hơn request cho đến khi connection bị đóng hoặc bảng được DROP. Phải chủ động dọn dẹp trước khi trả connection về pool để request tiếp theo không vô tình đọc nhầm dữ liệu cũ.

## 18. Chọn view, temporary table hay bảng báo cáo

| Tiêu chí | View | Temporary table | Bảng báo cáo |
|---|---|---|---|
| Lưu kết quả lâu dài | Không | Không | Có |
| Phạm vi sử dụng | Nhiều session | Session tạo bảng | Nhiều session |
| Tự phản ánh dữ liệu nguồn mới | Có, mỗi lần truy vấn | Không, trừ khi nạp lại | Không, cần refresh |
| Có index riêng | Không | Có thể tạo index | Có |
| Dùng để lưu snapshot | Không | Chỉ trong session | Có |
| Phù hợp báo cáo nặng lặp lại | Tùy query và optimizer | Tùy một job/session | Có thể phù hợp |
| Quản lý độ mới | Dữ liệu nguồn hiện tại | Thời điểm nạp temp table | Watermark/refresh metadata |
| Dùng cho nhiều người đọc | Có | Không | Có |

Một ứng dụng có thể kết hợp cả ba:

1. View cung cấp giao diện dữ liệu trực tiếp.
2. Temporary table hỗ trợ xử lý trung gian trong một job.
3. Bảng báo cáo lưu kết quả đã tổng hợp để nhiều người đọc.

## 19. Bài thực hành: chuyển báo cáo nặng từ view sang bảng riêng

Bài lab tạo một view tổng hợp doanh thu, sau đó lưu kết quả vào bảng báo cáo có index.

### Bước 1: tạo database lab

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_report_table_lab;
USE mysql_report_table_lab;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(12,3) NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    KEY idx_items_order (order_id),
    KEY idx_items_product (product_id)
) ENGINE=InnoDB;
~~~

### Bước 2: nạp dữ liệu mẫu

~~~sql
INSERT INTO orders (order_id, status, created_at)
VALUES
    (1, 'PAID', '2026-11-18 09:00:00'),
    (2, 'PAID', '2026-11-18 10:00:00'),
    (3, 'PENDING', '2026-11-18 11:00:00'),
    (4, 'PAID', '2026-11-19 08:00:00');

INSERT INTO order_items
    (order_item_id, order_id, product_id, quantity, unit_price)
VALUES
    (101, 1, 10, 2.000, 100.00),
    (102, 1, 20, 1.000, 250.00),
    (103, 2, 10, 3.000, 100.00),
    (104, 3, 20, 2.000, 250.00),
    (105, 4, 10, 1.000, 100.00);
~~~

### Bước 3: tạo view báo cáo

~~~sql
CREATE ALGORITHM = TEMPTABLE VIEW v_daily_product_sales AS
SELECT
    DATE(o.created_at) AS report_date,
    oi.product_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity) AS quantity_sold,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders AS o
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY
    DATE(o.created_at),
    oi.product_id;
~~~

Đọc view:

~~~sql
SELECT *
FROM v_daily_product_sales
ORDER BY report_date, product_id;
~~~

Mỗi lần SELECT, MySQL phải thực hiện truy vấn tổng hợp để tạo kết quả cho statement.

### Bước 4: tạo bảng báo cáo

~~~sql
CREATE TABLE report_daily_product_sales (
    report_date DATE NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    quantity_sold DECIMAL(18,3) NOT NULL,
    revenue DECIMAL(18,2) NOT NULL,
    refreshed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (report_date, product_id),
    KEY idx_report_product_date (product_id, report_date)
) ENGINE=InnoDB;
~~~

### Bước 5: nạp kết quả

~~~sql
INSERT INTO report_daily_product_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    CURRENT_TIMESTAMP(6)
FROM v_daily_product_sales;
~~~

Bảng báo cáo giờ lưu kết quả đã tính. Truy vấn dashboard có thể dùng index riêng:

~~~sql
SELECT
    report_date,
    product_id,
    revenue
FROM report_daily_product_sales
WHERE product_id = 10
  AND report_date >= '2026-11-18'
ORDER BY report_date DESC;
~~~

### Bước 6: so sánh kế hoạch

~~~sql
EXPLAIN
SELECT *
FROM v_daily_product_sales
WHERE product_id = 10;

EXPLAIN
SELECT *
FROM report_daily_product_sales
WHERE product_id = 10;
~~~

Với view, optimizer xử lý truy vấn tổng hợp từ bảng nền. Với bảng báo cáo, truy vấn có thể dùng index idx_report_product_date để đọc các hàng đã tổng hợp.

Dữ liệu lab nhỏ nên chênh lệch thời gian không có ý nghĩa benchmark. Mục tiêu là quan sát cấu trúc kế hoạch và sự khác biệt giữa tính lại với đọc kết quả lưu sẵn.

### Bước 7: refresh bảng báo cáo trong transaction

~~~sql
START TRANSACTION;

DELETE FROM report_daily_product_sales;

INSERT INTO report_daily_product_sales (
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    refreshed_at
)
SELECT
    report_date,
    product_id,
    order_count,
    quantity_sold,
    revenue,
    CURRENT_TIMESTAMP(6)
FROM v_daily_product_sales;

COMMIT;
~~~

Nếu INSERT thất bại trước COMMIT, ứng dụng có thể ROLLBACK để giữ lại phiên bản báo cáo đã commit trước đó.

### Bước 8: kiểm tra số liệu

~~~sql
SELECT
    COUNT(*) AS report_rows,
    SUM(revenue) AS total_revenue,
    MAX(refreshed_at) AS refreshed_at
FROM report_daily_product_sales;
~~~

Đối chiếu với:

~~~sql
SELECT
    SUM(revenue) AS view_revenue
FROM v_daily_product_sales;
~~~

Hai tổng doanh thu phải bằng nhau nếu dữ liệu nguồn không thay đổi giữa hai lần tính và cùng quy tắc nghiệp vụ.

### Dọn dẹp

~~~sql
DROP DATABASE mysql_report_table_lab;
~~~

Chỉ chạy DROP DATABASE trên database lab vừa tạo.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| View truy vấn chậm | Mỗi lần gọi phải tính lại JOIN/GROUP BY lớn | Kiểm tra EXPLAIN; cân nhắc bảng summary nếu báo cáo lặp lại |
| Không tạo được index trên view | MySQL không hỗ trợ index trực tiếp trên view | Tạo index trên bảng nền hoặc lưu kết quả vào bảng riêng |
| View không cập nhật được | Có GROUP BY, aggregate, DISTINCT, UNION, window function hoặc TEMPTABLE | Kiểm tra IS_UPDATABLE và thiết kế lại thao tác trên bảng nền |
| View không thấy cột mới | SELECT * đã được mở rộng tại thời điểm CREATE VIEW | ALTER/CREATE OR REPLACE VIEW với danh sách cột rõ ràng |
| View lỗi sau ALTER/DROP bảng nền | Định nghĩa view tham chiếu cột hoặc bảng không còn hợp lệ | CHECK TABLE, SHOW CREATE VIEW và sửa dependency |
| Không tạo được view từ temporary table | MySQL cấm view definition tham chiếu TEMPORARY table | Dùng bảng thường hoặc CTE phù hợp |
| Session khác không thấy temporary table | Temporary table có phạm vi session | Dùng bảng thường nếu cần chia sẻ |
| Báo cáo trống trong lúc refresh | Dùng TRUNCATE/DELETE rồi INSERT theo nhiều bước commit riêng | Dùng transaction DELETE+INSERT hoặc staging + rename |
| ROLLBACK không phục hồi sau TRUNCATE | TRUNCATE gây implicit commit và không rollback được | Dùng DELETE trong transaction hoặc staging table |
| Bảng summary không cập nhật đơn cũ | Incremental refresh chỉ đọc dữ liệu mới | Theo dõi updated_at/change log hoặc rebuild phạm vi bị ảnh hưởng |
| Tổng doanh thu không khớp | Quy tắc refund, discount, status hoặc late-arriving data chưa được tính | Xác định grain và quy tắc nghiệp vụ, thêm đối soát |
| Hai job refresh chạy chồng lấn | Không có cơ chế điều phối | Dùng scheduler lock, job registry hoặc khóa điều phối |
| Bảng staging thiếu index/constraint | CREATE TABLE ... SELECT không giữ toàn bộ schema; CREATE TABLE LIKE không copy foreign keys | Khai báo schema và kiểm tra metadata trước publish |
| Rename swap làm view lỗi | View/dependency tham chiếu tên bảng hoặc schema cũ | Kiểm tra dependency và thử trên staging trước khi đổi tên |
| Dashboard hiển thị dữ liệu cũ | Không theo dõi thời điểm refresh | Lưu refreshed_at, watermark và trạng thái job |

## 21. Checklist chọn view hay bảng báo cáo

- [ ] Đã xác định dữ liệu cần phản ánh hiện tại hay snapshot tại thời điểm cụ thể.
- [ ] Đã đánh giá tần suất truy cập báo cáo và chi phí tính lại.
- [ ] Đã kiểm tra view dùng MERGE hay TEMPTABLE.
- [ ] Đã hiểu view không có index riêng.
- [ ] Đã kiểm tra các giới hạn updatability.
- [ ] Đã tránh SELECT * trong view dùng lâu dài.
- [ ] Đã kiểm tra dependency sau migration schema.
- [ ] Đã chọn SQL SECURITY DEFINER hoặc INVOKER có chủ đích.
- [ ] Nếu dùng bảng báo cáo, đã xác định grain và khóa duy nhất.
- [ ] Đã thiết kế kiểu dữ liệu, precision và index cho truy vấn dashboard.
- [ ] Đã xác định quy tắc doanh thu, refund, discount và đơn đến muộn.
- [ ] Đã chọn full refresh hay incremental refresh.
- [ ] Đã xác định cách công bố dữ liệu mới mà không để người đọc thấy trạng thái dở dang.
- [ ] Không dùng TRUNCATE như DML có thể rollback.
- [ ] Đã có staging validation và phương án phục hồi nếu dùng rename swap.
- [ ] Đã có watermark, refreshed_at và trạng thái job.
- [ ] Đã có cơ chế ngăn hai job refresh chạy chồng lấn.
- [ ] Đã có quy trình đối soát số liệu nguồn với bảng báo cáo.
- [ ] Đã đánh giá transaction dài, undo, purge, replication lag và dung lượng staging.
- [ ] Đã kiểm thử trên staging với dữ liệu có quy mô gần production.

## 22. Nguyên tắc cần ghi nhớ

1. View lưu định nghĩa SELECT, không lưu kết quả báo cáo lâu dài.
2. MySQL không cung cấp materialized view native; muốn lưu kết quả cần quản lý bảng báo cáo riêng.
3. MERGE kết hợp định nghĩa view vào truy vấn ngoài; TEMPTABLE materialize kết quả tạm cho statement.
4. View không có index riêng; MERGE có thể dùng index bảng nền.
5. TEMPTABLE không làm view trở thành bảng cache lâu dài và view TEMPTABLE không updatable.
6. Aggregate, GROUP BY, DISTINCT, HAVING, UNION và window function thường làm view không updatable.
7. View definition không được tham chiếu temporary table; không thể tạo temporary view hoặc trigger trên view.
8. ORDER BY bên trong view không bảo đảm thứ tự cho truy vấn ngoài.
9. SELECT * trong view không tự mở rộng khi bảng nền được thêm cột.
10. Bảng báo cáo phải có grain, khóa, kiểu dữ liệu và index được thiết kế rõ ràng.
11. DELETE + INSERT trong cùng transaction InnoDB có thể công bố kết quả mới theo cách nguyên tử đối với reader.
12. TRUNCATE là DDL, gây implicit commit và không thể rollback như DELETE.
13. Staging + RENAME TABLE có thể giúp công bố snapshot mới nhanh; cần kiểm tra atomic DDL, metadata lock và dependency.
14. Incremental refresh phải xử lý cả dữ liệu cũ bị sửa, xóa, refund hoặc đến muộn.
15. Mọi bảng báo cáo cần metadata về thời điểm refresh và watermark để người đọc hiểu độ mới.
16. Temporary table chỉ dùng trong session; không thay thế bảng báo cáo chia sẻ giữa nhiều người dùng.

## Tài liệu tham khảo chính thức

Các hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual**:

1. [Using Views](https://dev.mysql.com/doc/refman/9.7/en/views.html): khái niệm view, cách tạo và sử dụng.
2. [View Processing Algorithms](https://dev.mysql.com/doc/refman/9.7/en/view-algorithms.html): MERGE, TEMPTABLE, UNDEFINED và materialization.
3. [Restrictions on Views](https://dev.mysql.com/doc/refman/9.7/en/view-restrictions.html): giới hạn index, số bảng, dependency và index hints.
4. [Updatable and Insertable Views](https://dev.mysql.com/doc/refman/9.7/en/view-updatability.html): điều kiện updatability và các cấu trúc không cập nhật được.
5. [CREATE VIEW Statement](https://dev.mysql.com/doc/refman/9.7/en/create-view.html): định nghĩa view, SQL SECURITY, giới hạn temporary table và hành vi ORDER BY/LIMIT.
6. [CREATE TABLE ... SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table-select.html): tạo bảng từ SELECT và các thuộc tính không được giữ nguyên.
7. [CREATE TABLE ... LIKE Statement](https://dev.mysql.com/doc/refman/9.7/en/create-table-like.html): sao chép schema và các thuộc tính không được sao chép như foreign key.
8. [TRUNCATE TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/truncate-table.html): implicit commit, không rollback, trigger và foreign key restrictions.
9. [Atomic DDL Statement Support](https://dev.mysql.com/doc/refman/9.7/en/atomic-ddl.html): atomic DDL và giới hạn phân biệt với transactional DDL.
10. [RENAME TABLE Statement](https://dev.mysql.com/doc/refman/9.7/en/rename-table.html): đổi tên nhiều bảng trong một câu lệnh và thứ tự thực hiện.
11. [Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/9.7/en/implicit-commit.html): các câu lệnh DDL gây implicit commit.
12. [INFORMATION_SCHEMA VIEWS Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-views-table.html): metadata về IS_UPDATABLE, CHECK_OPTION, DEFINER và SECURITY_TYPE.
13. [Temporary Table Problems](https://dev.mysql.com/doc/refman/9.7/en/temporary-table-problems.html): giới hạn phạm vi session và lỗi Can't reopen table.

