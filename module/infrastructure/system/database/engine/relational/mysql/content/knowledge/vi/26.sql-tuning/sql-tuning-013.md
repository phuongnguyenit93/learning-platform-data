# Kiểm soát truy vấn không có điều kiện giới hạn hoặc đọc quá nhiều dữ liệu

Một truy vấn có thể trả về rất ít hàng nhưng vẫn buộc MySQL đọc một lượng dữ liệu rất lớn. Ngược lại, một truy vấn trả về nhiều hàng chưa chắc là vấn đề nếu phạm vi đọc được giới hạn, có index phù hợp và kết quả được xử lý theo lô.

Khi kiểm soát truy vấn, cần phân biệt ba giới hạn:

- **Giới hạn kết quả**: số hàng và số byte trả về cho ứng dụng.
- **Giới hạn công việc đọc**: số hàng/index entry phải quét để tìm kết quả.
- **Giới hạn tài nguyên và thời gian**: thời gian chạy, bộ nhớ, I/O, lock và mức tải đồng thời.

LIMIT chỉ giới hạn số hàng trả về. Nó không tự động giới hạn số hàng phải đọc hoặc sắp xếp. Một truy vấn không có WHERE, một điều kiện quá rộng, một ORDER BY không có index hỗ trợ hoặc một phép join thiếu điều kiện đều có thể đọc và xử lý nhiều dữ liệu hơn dự kiến.

Bài viết trình bày cách thiết kế truy vấn có phạm vi rõ ràng, dùng index để giới hạn công việc, phân trang ổn định, đọc/xử lý dữ liệu theo lô, bảo vệ câu SELECT bằng timeout và theo dõi rows examined so với rows sent.

## 1. Chuẩn bị bảng minh họa

Các ví dụ dùng bảng đơn hàng:

~~~sql
CREATE TABLE sales_orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status_code TINYINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    total DECIMAL(13, 2) NOT NULL,
    payload JSON NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_created
        (tenant_id, created_at, order_id),
    KEY idx_orders_tenant_status_created
        (tenant_id, status_code, created_at, order_id),
    KEY idx_orders_created
        (created_at, order_id)
) ENGINE = InnoDB;
~~~

Index được thiết kế cho các kiểu truy vấn thường gặp:

| Index | Mục đích |
|---|---|
| PRIMARY (order_id) | Đọc hoặc xử lý theo khóa chính |
| (tenant_id, created_at, order_id) | Lọc theo tenant và khoảng thời gian, sắp xếp theo thời gian |
| (tenant_id, status_code, created_at, order_id) | Lọc theo tenant, trạng thái và thời gian |
| (created_at, order_id) | Quét theo thời gian trên toàn hệ thống |

Đây là schema minh họa. Không tạo tất cả index trên production chỉ vì chúng xuất hiện trong bài; hãy chọn index theo workload thực tế và đo chi phí ghi.

## 2. Nhận diện truy vấn không có giới hạn

Một truy vấn không có điều kiện lọc:

~~~sql
SELECT *
FROM sales_orders;
~~~

có thể phải đọc toàn bộ bảng và gửi toàn bộ kết quả về client. Khi bảng tăng từ vài nghìn lên hàng chục triệu hàng, cùng một câu SQL có thể trở thành nguồn tải lớn cho database, network và ứng dụng.

Một truy vấn có WHERE nhưng phạm vi vẫn quá rộng:

~~~sql
SELECT order_id, customer_id, total
FROM sales_orders
WHERE created_at >= '2020-01-01';
~~~

Nếu dữ liệu từ năm 2020 chiếm gần như toàn bộ bảng, điều kiện này không giới hạn đáng kể lượng dữ liệu cần đọc.

Một truy vấn có LIMIT nhưng vẫn có thể đọc nhiều:

~~~sql
SELECT order_id, customer_id, total
FROM sales_orders
WHERE YEAR(created_at) = 2026
ORDER BY total DESC
LIMIT 20;
~~~

Hàm YEAR() áp dụng lên cột và ORDER BY total không được hỗ trợ bởi một index phù hợp cho toàn bộ điều kiện. MySQL có thể phải đọc nhiều hàng thỏa điều kiện, tính biểu thức, rồi sắp xếp trước khi trả 20 hàng.

### 2.1. Đừng chỉ nhìn số hàng trả về

Hai đại lượng cần phân biệt:

- rows sent: số hàng gửi cho client.
- rows examined: số hàng được server/storage engine kiểm tra trong quá trình thực thi, theo cách MySQL ghi nhận.

Ví dụ, truy vấn trả 20 hàng nhưng đọc 500.000 hàng có tỷ lệ examined/sent rất cao. Đây là tín hiệu cần điều tra, dù response của API rất nhỏ.

Tỷ lệ này chỉ là chỉ báo. Với truy vấn trả 0 hàng, phép chia không có ý nghĩa; với truy vấn tổng hợp, số hàng gửi có thể là 1 dù phải đọc hàng triệu hàng. Hãy xem thêm plan, thời gian, I/O và loại truy vấn.

## 3. Giới hạn kết quả bằng điều kiện nghiệp vụ

Truy vấn tốt nên thể hiện rõ phạm vi mà người dùng hoặc tác vụ cần:

~~~sql
SELECT order_id, customer_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

Truy vấn này có:

- tenant_id để giới hạn phạm vi dữ liệu của tenant.
- Khoảng thời gian nửa mở để giới hạn ngày cần đọc.
- ORDER BY ổn định với order_id làm tie-breaker.
- LIMIT để giới hạn số hàng trả về.
- Chỉ chọn các cột cần cho màn hình.

### 3.1. Dùng khoảng thời gian nửa mở

Khi lọc DATETIME theo ngày hoặc tháng, ưu tiên:

~~~sql
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00'
~~~

Khoảng này bao gồm mọi thời điểm trong tháng 1 và không cần đoán giá trị thời gian cuối ngày. Nó cũng giữ cột created_at ở dạng trực tiếp để index range có thể được sử dụng.

Tránh viết:

~~~sql
WHERE DATE(created_at) = '2026-01-01'
~~~

vì hàm DATE() được áp dụng lên cột. Nếu nghiệp vụ bắt buộc lọc theo biểu thức, có thể cân nhắc functional index hoặc generated column; nếu chỉ cần một ngày lịch, khoảng nửa mở thường đơn giản hơn.

### 3.2. Không cho client tự chọn phạm vi vô hạn

Với API tìm kiếm hoặc báo cáo, kiểm soát đầu vào ở tầng ứng dụng:

- Bắt buộc tenant hoặc phạm vi quyền truy cập.
- Yêu cầu khoảng ngày tối đa, ví dụ không cho tải nhiều năm trong một request đồng bộ.
- Giới hạn page size và đặt giá trị mặc định.
- Từ chối hoặc chuyển sang job nền nếu người dùng yêu cầu export quá lớn.
- Không cho tham số rỗng làm mất toàn bộ điều kiện WHERE ngoài ý muốn.

Điều kiện tenant là một ví dụ; hệ thống không đa tenant vẫn cần điều kiện nghiệp vụ phù hợp như trạng thái, thời gian hoặc nhóm dữ liệu.

## 4. LIMIT giới hạn kết quả, không bảo đảm giới hạn dữ liệu đọc

LIMIT:

~~~sql
SELECT order_id, total
FROM sales_orders
ORDER BY total DESC
LIMIT 10;
~~~

chỉ yêu cầu trả tối đa 10 hàng. Nếu MySQL không có index phù hợp với thứ tự total DESC, nó có thể phải đọc và sắp xếp nhiều hàng để xác định 10 hàng lớn nhất.

Khi có index phù hợp với điều kiện lọc và thứ tự sắp xếp, MySQL có thể đi theo index và dừng sau khi tìm đủ số hàng cần thiết. Ví dụ:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Index (tenant_id, created_at, order_id) có thể hỗ trợ lọc tenant và đọc theo thứ tự thời gian. Với hai key part sắp xếp cùng chiều, InnoDB có thể quét ngược B-tree index tăng dần để phục vụ thứ tự giảm dần.

### 4.1. LIMIT có thể vẫn cần scan hoặc sort lớn

Các tình huống thường gặp:

- Không có WHERE và không có index phù hợp.
- WHERE dùng hàm hoặc phép chuyển đổi làm mất khả năng range access.
- ORDER BY không khớp thứ tự index.
- GROUP BY hoặc DISTINCT cần xử lý nhiều hàng trước khi biết kết quả cuối.
- Join tạo ra nhiều hàng trung gian trước khi LIMIT được áp dụng.
- OFFSET lớn buộc MySQL bỏ qua nhiều hàng trước khi trả trang cần thiết.

Vì vậy, hãy xem EXPLAIN để biết LIMIT có thể dừng sớm trên index hay vẫn phải xử lý một tập dữ liệu lớn.

### 4.2. ORDER BY phải có thứ tự xác định

Nếu nhiều hàng có cùng created_at, chỉ ORDER BY created_at có thể cho kết quả khác nhau giữa các lần chạy. Thêm khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Thứ tự xác định giúp phân trang ổn định và giảm nguy cơ một hàng xuất hiện lặp hoặc bị bỏ qua khi các hàng có cùng giá trị sắp xếp.

## 5. Chỉ đọc các cột cần thiết

Tránh dùng SELECT * trong các API hoặc báo cáo chỉ cần một vài trường:

~~~sql
SELECT *
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 100;
~~~

Nếu payload chứa JSON lớn, truy vấn có thể truyền hàng trăm kilobyte hoặc nhiều megabyte dù màn hình chỉ cần mã đơn, ngày và tổng tiền.

Viết rõ cột:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

Lợi ích:

- Giảm byte đọc từ storage hoặc buffer pool khi có thể dùng covering index.
- Giảm byte truyền qua network.
- Giảm bộ nhớ ứng dụng dùng để deserialize và giữ kết quả.
- Giảm công việc serialize JSON hoặc map object.
- Giúp schema thay đổi ít gây tác động đến API.

Không phải SELECT liệt kê ít cột là chắc chắn covering index. Kiểm tra EXPLAIN và cấu trúc index để biết MySQL còn phải đọc clustered record hay không.

## 6. Phân trang mà không đọc lại quá nhiều hàng

OFFSET lớn là một nguồn đọc dư thừa phổ biến:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 500000;
~~~

MySQL cần đi qua các hàng đứng trước vị trí OFFSET rồi mới trả 50 hàng tiếp theo. Khi OFFSET tăng, lượng công việc có thể tăng theo.

Với danh sách lớn, cân nhắc keyset pagination (phân trang theo khóa tiếp nối). Trang đầu:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Giả sử hàng cuối trang trước có created_at = '2026-02-15 10:30:00' và order_id = 9000. Trang tiếp theo:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
  AND (created_at, order_id) < ('2026-02-15 10:30:00', 9000)
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Điều kiện tuple tiếp nối bắt đầu sau khóa cuối trang trước theo thứ tự giảm dần. Index (tenant_id, created_at, order_id) có thể hỗ trợ tìm vị trí tiếp theo và đọc 50 hàng.

Keyset pagination phù hợp với danh sách cuộn liên tục hoặc API cần đi qua tập dữ liệu lớn. Nó không cung cấp số trang tùy ý như OFFSET; client cần giữ cursor gồm các giá trị sắp xếp cuối cùng.

### 6.1. Cursor phải chứa đủ key sắp xếp

Nếu chỉ lưu created_at nhưng nhiều đơn có cùng timestamp, trang tiếp theo có thể lặp hoặc bỏ sót hàng. Cursor cần tất cả cột ORDER BY, trong đó có khóa duy nhất làm tie-breaker.

Nếu thứ tự là:

~~~sql
ORDER BY status_code ASC, created_at DESC, order_id DESC
~~~

cursor phải chứa status_code, created_at và order_id, đồng thời điều kiện tiếp nối phải phản ánh đúng chiều sắp xếp của từng cột. Không dùng một phép so sánh tuple đơn giản nếu chiều ASC/DESC trộn lẫn mà chưa kiểm tra logic.

### 6.2. Dữ liệu thay đổi trong lúc phân trang

Keyset pagination tránh chi phí bỏ qua OFFSET, nhưng không tự tạo một snapshot bất biến giữa các request. Nếu hàng được thêm, xóa hoặc thay đổi cột sắp xếp trong lúc client đang duyệt, tập kết quả có thể thay đổi.

Tùy nghiệp vụ, có thể:

- Chấp nhận danh sách phản ánh dữ liệu mới nhất ở mỗi trang.
- Gắn một mốc thời gian hoặc high-water mark vào cursor.
- Chạy export nền với một tập khóa đã chốt.
- Dùng consistent snapshot trong một transaction nếu cần tính nhất quán nghiêm ngặt, đồng thời đánh giá chi phí transaction dài.

## 7. Đọc dữ liệu lớn theo lô

Khi cần xử lý toàn bộ dữ liệu cho export, migration hoặc đồng bộ, đừng mặc định tải toàn bộ kết quả vào bộ nhớ ứng dụng.

Một cách phổ biến là quét theo khóa chính từng lô:

~~~sql
SELECT order_id, tenant_id, created_at, total
FROM sales_orders
WHERE order_id > 0
  AND order_id <= 9000000
ORDER BY order_id
LIMIT 1000;
~~~

Ứng dụng lưu order_id cuối cùng đã xử lý. Lô kế tiếp dùng giá trị đó:

~~~sql
SELECT order_id, tenant_id, created_at, total
FROM sales_orders
WHERE order_id > 1250
  AND order_id <= 9000000
ORDER BY order_id
LIMIT 1000;
~~~

Trong triển khai thực tế, thay 1250 bằng checkpoint cuối cùng của lô trước. Khóa chính giúp định vị vùng tiếp theo mà không phải bỏ qua tất cả hàng đã xử lý.

### 7.1. Chốt high-water mark

Nếu tác vụ cần xử lý tập dữ liệu tại thời điểm bắt đầu, lấy một mốc trên trước khi chạy:

~~~sql
SELECT MAX(order_id) AS high_water_mark
FROM sales_orders;
~~~

Giả sử kết quả là 9000000. Mỗi lô dùng điều kiện:

~~~sql
WHERE order_id > ?
  AND order_id <= 9000000
ORDER BY order_id
LIMIT 1000;
~~~

Các hàng được thêm với order_id lớn hơn mốc sẽ không kéo dài tác vụ vô hạn. High-water mark không tự bảo đảm snapshot nhất quán cho các hàng cũ bị cập nhật hoặc xóa; nếu điều đó quan trọng, cần thiết kế thêm cơ chế snapshot hoặc versioning.

### 7.2. Xử lý checkpoint an toàn

Một tiến trình theo lô nên:

1. Đọc tối đa N hàng sau checkpoint.
2. Xử lý và ghi kết quả theo cách idempotent nếu có thể.
3. Chỉ lưu checkpoint sau khi lô đã được xử lý thành công.
4. Nếu lỗi giữa lô, chạy lại lô mà không tạo tác dụng phụ trùng lặp.
5. Ghi log checkpoint, số hàng và thời gian từng lô.

Không cập nhật checkpoint trước khi dữ liệu lô được ghi nhận thành công; nếu tiến trình dừng giữa chừng, dữ liệu có thể bị bỏ qua.

### 7.3. Kích thước lô

Lô quá lớn có thể:

- Giữ transaction lâu.
- Giữ nhiều row lock hoặc undo record.
- Tạo lượng dữ liệu tạm và bộ nhớ ứng dụng lớn.
- Tăng thời gian phản hồi và ảnh hưởng workload khác.

Lô quá nhỏ làm tăng số round trip và overhead điều phối. Bắt đầu bằng kích thước vừa phải, đo thời gian, rows examined, lock wait, CPU và I/O rồi điều chỉnh. Không có một batch size đúng cho mọi hệ thống.

## 8. Kiểm soát UPDATE và DELETE diện rộng

UPDATE hoặc DELETE không có WHERE có thể tác động toàn bộ bảng:

~~~sql
UPDATE sales_orders
SET status_code = 9;

DELETE FROM sales_orders;
~~~

Nếu mục tiêu chỉ là xử lý một tập hàng, điều kiện phải xác định chính xác phạm vi. Với tác vụ lớn, chia thành các lô theo khóa ổn định:

~~~sql
UPDATE sales_orders
SET status_code = 9
WHERE order_id > 100000
  AND order_id <= 101000
  AND status_code = 1;
~~~

Sau khi xác nhận lô đầu, tiến trình có thể tiếp tục các khoảng khóa kế tiếp. Một cách khác là chọn các khóa tiếp theo bằng ORDER BY và LIMIT trong câu lệnh một bảng:

~~~sql
UPDATE sales_orders
SET status_code = 9
WHERE status_code = 1
ORDER BY order_id
LIMIT 1000;
~~~

UPDATE/DELETE một bảng có thể dùng ORDER BY và LIMIT trong MySQL. Hãy xác minh kế hoạch và số hàng bị tác động trước khi chạy lặp lại. Với UPDATE/DELETE nhiều bảng, cú pháp và giới hạn khác nhau; không giả định LIMIT áp dụng giống câu lệnh một bảng.

Trong schema minh họa, không có index bắt đầu bằng status_code. Nếu giá trị status_code = 1 hiếm, MySQL có thể phải đọc nhiều hàng theo khóa chính mới tìm đủ 1.000 hàng để cập nhật. LIMIT vẫn giới hạn số hàng bị thay đổi, nhưng không bảo đảm chỉ đọc 1.000 hàng. Hãy xem xét index phù hợp hoặc chia theo khoảng order_id đã xác định.

### 8.1. Chạy mỗi lô trong transaction ngắn

Với InnoDB, một lô có thể được thực hiện trong transaction riêng:

~~~sql
START TRANSACTION;

UPDATE sales_orders
SET status_code = 9
WHERE order_id > 100000
  AND order_id <= 101000
  AND status_code = 1;

COMMIT;
~~~

Transaction ngắn giúp giải phóng lock và undo history sớm hơn so với một transaction khổng lồ. Đổi lại, nếu cần tính nguyên tử cho toàn bộ chiến dịch, phải thiết kế cơ chế tiến độ, retry và rollback ở cấp tác vụ.

### 8.2. Kiểm tra phạm vi trước khi ghi

Trước UPDATE/DELETE, dùng SELECT với cùng điều kiện để ước lượng tập hàng:

~~~sql
SELECT COUNT(*)
FROM sales_orders
WHERE order_id > 100000
  AND order_id <= 101000
  AND status_code = 1;
~~~

Với tác vụ lớn, COUNT(*) cũng có chi phí; không cần chạy COUNT toàn bảng chỉ để xác nhận mỗi lô nhỏ. Có thể dùng SELECT khóa với LIMIT hoặc số hàng thực tế của DML để theo dõi.

Nếu cần kiểm tra execution plan cho DML, dùng EXPLAIN UPDATE hoặc EXPLAIN DELETE trên phiên bản hỗ trợ. EXPLAIN ANALYZE không phải công cụ để đo UPDATE/DELETE trong quy trình này; hãy đo thời gian và số hàng tác động của từng lô trên môi trường thử nghiệm phù hợp.

## 9. COUNT(*) và phân trang giao diện

Một mẫu phổ biến là chạy hai truy vấn cho mỗi trang:

~~~sql
SELECT COUNT(*)
FROM sales_orders
WHERE tenant_id = 42;

SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

COUNT(*) chính xác có thể phải đọc một lượng lớn index entry, đặc biệt khi điều kiện tenant khớp nhiều hàng. Nếu giao diện chỉ cần biết còn trang tiếp theo hay không, có thể lấy page_size + 1:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 51;
~~~

Nếu nhận được 51 hàng, hiển thị 50 hàng đầu và đánh dấu has_next = true. Nếu chỉ có tối đa 50 hàng, không có trang tiếp theo theo snapshot của truy vấn đó.

Không thay COUNT chính xác bằng một số ước lượng nếu nghiệp vụ cần số liệu chính xác. Với dashboard, có thể dùng bảng tổng hợp hoặc cache số liệu được cập nhật theo lịch; cần ghi rõ thời điểm dữ liệu được làm mới.

## 10. Tránh tạo tập trung gian quá lớn khi JOIN

Một truy vấn có LIMIT ở cuối vẫn có thể tạo nhiều hàng trung gian trước khi trả kết quả:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    so.order_id,
    so.total
FROM employees AS e
JOIN sales_orders AS so
  ON so.employee_id = e.employee_id
ORDER BY so.total DESC
LIMIT 100;
~~~

Nếu một nhân viên có nhiều đơn hàng, join có thể tạo rất nhiều cặp hàng. Nếu thứ tự total không được hỗ trợ bởi index phù hợp, MySQL có thể cần xử lý và sắp xếp tập kết quả lớn trước khi trả 100 hàng.

Khi nghiệp vụ cần Top-N đơn hàng, truy vấn trực tiếp bảng đơn hàng thường rõ ràng hơn:

~~~sql
SELECT order_id, employee_id, total
FROM sales_orders
ORDER BY total DESC, order_id DESC
LIMIT 100;
~~~

Nếu cần tên nhân viên, có thể join sau khi đã xác định 100 đơn:

~~~sql
SELECT
    top_orders.order_id,
    top_orders.total,
    e.employee_name
FROM (
    SELECT order_id, employee_id, total
    FROM sales_orders
    ORDER BY total DESC, order_id DESC
    LIMIT 100
) AS top_orders
JOIN employees AS e
  ON e.employee_id = top_orders.employee_id
ORDER BY top_orders.total DESC, top_orders.order_id DESC;
~~~

Derived table giới hạn trước 100 đơn rồi mới join để lấy tên nhân viên. Kết quả cuối vẫn có ORDER BY vì thứ tự bên trong derived table không tự bảo đảm thứ tự kết quả bên ngoài.

Không phải lúc nào cũng có thể đẩy LIMIT vào một nhánh trước JOIN mà vẫn giữ nguyên ngữ nghĩa. Chỉ làm khi tập hàng được giới hạn chính là tập Top-N mà nghiệp vụ cần.

### 10.1. Kiểm tra điều kiện JOIN

JOIN thiếu điều kiện hoặc dùng điều kiện không đủ chọn lọc có thể tạo tích Descartes hoặc số hàng nhân lên ngoài dự kiến:

~~~sql
SELECT e.employee_id, so.order_id
FROM employees AS e
JOIN sales_orders AS so;
~~~

Không có ON, kết quả là tích Descartes giữa hai bảng. Trước khi chạy truy vấn nhiều bảng, xác nhận:

- Mỗi quan hệ JOIN có điều kiện nối đúng khóa.
- Cardinality một-nhiều có được hiểu rõ.
- Bộ lọc được áp dụng ở bảng phù hợp.
- Các index hỗ trợ cột nối và điều kiện lọc.
- Số hàng ước lượng và số hàng thực tế không tăng đột biến ở iterator join.

## 11. Kiểm soát IN list và UNION lớn

Mẫu prepared statement với danh sách IN (số placeholder thực tế được tạo theo số khóa; ví dụ dưới đây được rút gọn):

~~~sql
SELECT order_id, total
FROM sales_orders
WHERE order_id IN (?, ?, ?);
~~~

Khi danh sách có hàng nghìn hoặc hàng chục nghìn khóa, câu SQL và số placeholder tăng lớn, làm tăng chi phí parse/optimize và tạo nhiều lookup. Nếu danh sách khóa đến từ một bảng khác hoặc một tác vụ, cân nhắc nạp khóa vào temporary/staging table có index rồi JOIN.

Ví dụ với bảng tạm:

~~~sql
CREATE TEMPORARY TABLE requested_order_ids (
    order_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

SELECT so.order_id, so.total
FROM requested_order_ids AS requested
JOIN sales_orders AS so
  ON so.order_id = requested.order_id;
~~~

Temporary table phù hợp khi danh sách lớn được tái sử dụng trong nhiều truy vấn của cùng session. Nếu chỉ có vài chục khóa, IN list có thể đơn giản và hiệu quả hơn; hãy đo thay vì áp dụng máy móc.

UNION hoặc UNION DISTINCT trên nhiều nhánh lớn có thể tạo lượng dữ liệu trung gian và chi phí khử trùng lặp đáng kể. Kiểm tra mỗi nhánh có điều kiện giới hạn riêng, có index phù hợp và có thực sự cần loại trùng hay không.

## 12. Export lớn: stream hoặc chạy job nền

Không nên để một request web đồng bộ tải hàng triệu hàng, giữ toàn bộ kết quả trong RAM rồi mới trả file.

Các lựa chọn:

- Chạy export như background job và trả trạng thái/progress cho người dùng.
- Đọc theo lô bằng khóa chính hoặc cursor ổn định.
- Chỉ chọn các cột cần có trong file.
- Ghi từng lô ra file hoặc object storage thay vì giữ toàn bộ trong bộ nhớ.
- Giới hạn tốc độ đọc để không cạnh tranh tài nguyên với workload giao dịch.
- Ghi checkpoint để tiếp tục sau lỗi.

Một số driver có chế độ streaming hoặc cursor/fetch size, nhưng cách hoạt động khác nhau. Có driver buffer toàn bộ kết quả ở client dù API có tên fetch size; hãy xác minh tài liệu và đo bộ nhớ thực tế.

### 12.1. Consistency của export theo lô

Nếu mỗi lô chạy trong một transaction riêng, dữ liệu có thể thay đổi giữa các lô. Điều này có thể phù hợp với báo cáo gần nhất, nhưng không bảo đảm một snapshot nhất quán.

Nếu giữ một consistent snapshot cho toàn bộ export, transaction có thể tồn tại lâu, giữ read view cũ và làm chậm purge undo history trong InnoDB. Hãy cân nhắc:

- Export cần snapshot tại một thời điểm hay chấp nhận dữ liệu thay đổi?
- Có thể chốt high-water mark hoặc version không?
- Có thể xuất từ replica hoặc bản sao dữ liệu không?
- Transaction có thể chia nhỏ mà vẫn đáp ứng nghiệp vụ không?

Dùng replica giúp tách một phần tải đọc khỏi primary, nhưng không làm cho truy vấn không giới hạn trở nên rẻ. Replica vẫn phải đọc dữ liệu và có thể bị tăng replication lag nếu export chiếm nhiều tài nguyên.

## 13. Giới hạn thời gian cho SELECT

MySQL có biến max_execution_time, tính bằng mili giây, để giới hạn thời gian thực thi của một số câu SELECT chỉ đọc trong session.

Ví dụ đặt giới hạn 2 giây cho session:

~~~sql
SET SESSION max_execution_time = 2000;
~~~

Hoặc dùng optimizer hint cho một truy vấn:

~~~sql
SELECT /*+ MAX_EXECUTION_TIME(2000) */
    order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

Giá trị 2000 là 2.000 mili giây. Giá trị 0 có nghĩa không đặt giới hạn bằng biến này.

### 13.1. Timeout là lớp bảo vệ, không phải cách tối ưu truy vấn

max_execution_time có ích để ngăn một SELECT đọc hoặc xử lý quá lâu chiếm tài nguyên vô hạn. Nhưng nó không sửa được:

- Thiếu điều kiện lọc.
- Index không phù hợp.
- Sort lớn.
- Join tạo quá nhiều hàng.
- Kết quả quá lớn gửi về client.

Timeout chỉ giới hạn thời gian; nó không bảo đảm câu truy vấn đã đọc ít dữ liệu. Một truy vấn có thể thường xuyên bị timeout vì thiết kế chưa tốt.

### 13.2. Phạm vi áp dụng

max_execution_time áp dụng cho SELECT chỉ đọc theo quy tắc của phiên bản MySQL. Không xem nó là timeout chung cho UPDATE, DELETE, INSERT hoặc toàn bộ transaction. DML diện rộng cần giới hạn phạm vi, chia lô, theo dõi lock và quản lý transaction riêng.

Timeout của client, connection pool và proxy cũng có thể dừng request ở tầng khác. Hãy xác định timeout nào đã kích hoạt từ error log, application log và Performance Schema; không giả định client timeout đồng nghĩa server đã dừng xử lý ngay.

## 14. Đọc EXPLAIN để phát hiện scan quá rộng

EXPLAIN cho biết optimizer dự kiến đọc bảng theo cách nào:

~~~sql
EXPLAIN
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

Các dấu hiệu cần xem:

- type: ALL có thể là full table scan; range/ref thường cho thấy truy cập có điều kiện hơn.
- possible_keys và key: index ứng viên và index được chọn.
- rows: số hàng ước lượng mà optimizer cần đọc.
- filtered: tỷ lệ hàng dự kiến còn lại sau điều kiện lọc.
- Extra: Using where, Using filesort, Using temporary hoặc Using index.

Không kết luận chỉ từ một giá trị. ALL trên bảng nhỏ có thể hợp lý; range trên hàng triệu entry vẫn có thể tốn kém.

### 14.1. EXPLAIN ANALYZE

Trên MySQL 8.0.18 trở lên:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total
FROM sales_orders
WHERE tenant_id = 42
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

EXPLAIN ANALYZE thực thi SELECT và cho biết actual rows, loops và thời gian của iterator. Đây là cách kiểm tra liệu LIMIT có giúp dừng sớm hay truy vấn vẫn đọc nhiều hàng trước khi trả kết quả.

Chỉ chạy EXPLAIN ANALYZE với truy vấn có chi phí đã được đánh giá và trên môi trường phù hợp; đây là một lần thực thi thật.

### 14.2. Thống kê có thể làm optimizer ước lượng sai

Nếu EXPLAIN dự đoán số hàng rất khác thực tế, kiểm tra thống kê và phân bố dữ liệu. Có thể cập nhật thống kê:

~~~sql
ANALYZE TABLE sales_orders;
~~~

Sau đó so sánh kế hoạch và số liệu thực tế. ANALYZE TABLE cập nhật thống kê, không bảo đảm index cụ thể sẽ được chọn.

## 15. Theo dõi truy vấn đọc nhiều dữ liệu

### 15.1. Slow query log

Slow query log có thể ghi nhận truy vấn vượt ngưỡng thời gian và các số liệu liên quan. Một số trường hữu ích:

- Query_time: thời gian truy vấn.
- Lock_time: thời gian chờ lock được ghi nhận.
- Rows_sent: số hàng gửi về client.
- Rows_examined: số hàng server đã kiểm tra.

Có thể xem cấu hình:

~~~sql
SHOW VARIABLES LIKE 'slow_query_log';
SHOW VARIABLES LIKE 'long_query_time';
SHOW VARIABLES LIKE 'min_examined_row_limit';
~~~

Đặt ngưỡng ghi log dựa trên workload và dung lượng log. Nếu chỉ lọc theo thời gian, một truy vấn rất nhanh nhưng đọc hàng triệu hàng có thể không xuất hiện; min_examined_row_limit có thể giúp phát hiện các truy vấn đọc nhiều dù thời gian thấp.

Slow query log có thể chứa SQL text và giá trị literal nhạy cảm. Hãy áp dụng quyền truy cập, lưu trữ và retention phù hợp.

### 15.2. Performance Schema theo digest

Performance Schema tổng hợp câu lệnh theo digest, giúp tìm nhóm truy vấn có tổng lượng rows examined lớn:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    ROUND(
        SUM_ROWS_EXAMINED / NULLIF(SUM_ROWS_SENT, 0),
        2
    ) AS examined_per_sent,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_seconds
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST_TEXT IS NOT NULL
ORDER BY SUM_ROWS_EXAMINED DESC
LIMIT 20;
~~~

Các cột cho biết:

- COUNT_STAR: số lần câu lệnh được ghi nhận.
- SUM_ROWS_EXAMINED: tổng số hàng được kiểm tra.
- SUM_ROWS_SENT: tổng số hàng gửi về client.
- examined_per_sent: tỷ lệ đọc trên số hàng trả về, khi mẫu số khác 0.
- total_seconds: tổng thời gian chờ được quy đổi từ timer picosecond sang giây.

Tỷ lệ examined_per_sent cao là một tín hiệu để điều tra, không phải bằng chứng duy nhất. Với câu lệnh aggregate, một hàng kết quả có thể đại diện cho hàng triệu hàng nguồn. Với truy vấn không trả kết quả, tỷ lệ là NULL.

Performance Schema có thể bị giới hạn bởi cấu hình instrumentation và kích thước history/summary. Người dùng cần quyền phù hợp để đọc các bảng này.

### 15.3. Theo dõi theo tác vụ

Với export hoặc batch job, ghi lại ở tầng ứng dụng:

- Tên tác vụ và phạm vi tenant/thời gian.
- Checkpoint đầu/cuối của mỗi lô.
- Số hàng đọc, số hàng xử lý và số hàng ghi.
- Thời gian từng lô và tổng thời gian.
- Retry, lỗi, timeout và số lần chạy lại.
- Bộ nhớ ứng dụng và tốc độ ghi file.

Những số liệu này giúp phân biệt truy vấn chậm do MySQL với xử lý chậm do serialize, network hoặc ghi file.

## 16. Guardrail ở tầng ứng dụng

Một API tìm kiếm nên có hợp đồng giới hạn rõ ràng:

| Guardrail | Ví dụ |
|---|---|
| Page size mặc định | 25 hàng |
| Page size tối đa | 100 hàng |
| Khoảng ngày tối đa | 31 ngày cho request đồng bộ |
| Điều kiện bắt buộc | tenant_id hoặc phạm vi quyền truy cập |
| Timeout | Giới hạn cho SELECT đọc |
| Export lớn | Chuyển sang background job |
| Tải đồng thời | Rate limit theo người dùng/tenant |

Các con số chỉ là ví dụ. Hãy chọn dựa trên độ trễ mục tiêu, phần cứng, kích thước hàng và tải đồng thời.

### 16.1. Không để tham số rỗng làm mất điều kiện lọc

Một lỗi phổ biến là tạo SQL động bằng cách chỉ thêm WHERE khi người dùng nhập bộ lọc. Nếu người dùng không nhập gì, ứng dụng có thể vô tình chạy:

~~~sql
SELECT order_id, created_at, total
FROM sales_orders;
~~~

Thay vào đó, xác định bộ lọc bắt buộc trước khi tạo truy vấn. Nếu tìm kiếm toàn bộ là một tính năng hợp lệ, yêu cầu người dùng chọn phạm vi rõ ràng hoặc chuyển thao tác sang export nền.

### 16.2. Giới hạn ở server, không tin client

Client có thể gửi page_size = 1000000 dù giao diện chỉ hiển thị 25. Server cần tự áp dụng mức tối đa, kiểm tra quyền truy cập và validate khoảng thời gian. Không dựa vào việc ẩn nút hoặc giới hạn control ở trình duyệt.

Dùng prepared statement cho giá trị tham số; tên cột và hướng sắp xếp động cần được chọn từ allow-list thay vì nối trực tiếp chuỗi người dùng vào SQL.

## 17. Khi nào full scan là lựa chọn hợp lý?

Không phải mọi full table scan đều cần loại bỏ. Full scan có thể là lựa chọn tốt khi:

- Bảng nhỏ.
- Truy vấn phân tích cần phần lớn dữ liệu.
- Đọc tuần tự rẻ hơn nhiều lần lookup ngẫu nhiên qua secondary index.
- Tác vụ export cần mọi hàng và đã được thiết kế để chạy theo lô.
- Optimizer đánh giá index không đủ chọn lọc.

Nếu nghiệp vụ thực sự cần đọc toàn bộ dữ liệu, hãy kiểm soát cách thực hiện:

- Chạy dưới dạng background job.
- Dùng batch và checkpoint.
- Giới hạn số job đồng thời.
- Theo dõi I/O, CPU, buffer pool và replication lag.
- Ưu tiên replica hoặc hệ thống phân tích khi phù hợp.
- Lưu kết quả tổng hợp để tránh quét lặp lại cho cùng một báo cáo.

Mục tiêu là làm cho lượng dữ liệu đọc tương xứng với công việc cần thực hiện và không gây ảnh hưởng ngoài dự kiến đến workload khác.

## 18. Những lỗi thường gặp

**“Có LIMIT là truy vấn đã được giới hạn.”** Không. LIMIT giới hạn số hàng trả về; MySQL vẫn có thể đọc và sắp xếp một tập dữ liệu lớn trước khi trả kết quả.

**“Trả 20 hàng nghĩa là chỉ đọc 20 hàng.”** Không. So sánh rows examined với rows sent và xem execution plan.

**“WHERE có điều kiện là đủ.”** Không. Điều kiện có thể quá rộng, không chọn lọc hoặc không dùng được index.

**“SELECT * không ảnh hưởng nếu LIMIT nhỏ.”** Không. Cột BLOB/JSON lớn có thể làm tăng I/O, network và bộ nhớ dù số hàng ít.

**“ORDER BY một cột luôn ổn định.”** Không. Nếu có giá trị trùng, thêm khóa duy nhất làm tie-breaker.

**“Keyset pagination tự bảo đảm snapshot nhất quán.”** Không. Nó giảm chi phí phân trang nhưng dữ liệu vẫn có thể thay đổi giữa các request.

**“Chia batch là chỉ cần thêm LIMIT.”** Không. Cần checkpoint ổn định, high-water mark khi phù hợp, retry idempotent và lưu checkpoint sau khi lô thành công.

**“Một transaction lớn an toàn hơn nhiều transaction nhỏ.”** Không. Transaction dài có thể giữ lock và undo history lâu; transaction ngắn cần cơ chế tiến độ và retry phù hợp.

**“COUNT(*) luôn rẻ vì chỉ trả một con số.”** Không. MySQL có thể phải đọc nhiều index entry để tính số chính xác.

**“EXISTS luôn tốt hơn JOIN.”** Không. Hãy so sánh kết quả và execution plan; optimizer có thể biến EXISTS thành semijoin.

**“max_execution_time giải quyết truy vấn không giới hạn.”** Không. Nó là lớp bảo vệ thời gian cho SELECT chỉ đọc; không thay thế điều kiện lọc, index và batching.

**“Replica có thể xử lý mọi truy vấn nặng miễn phí.”** Không. Replica vẫn dùng CPU, I/O và có thể tăng replication lag.

## 19. Quy trình kiểm soát truy vấn đọc quá nhiều

1. Xác định mục đích: API, trang danh sách, báo cáo, export, migration hay DML diện rộng.
2. Xác định phạm vi nghiệp vụ bắt buộc: tenant, thời gian, trạng thái hoặc khóa.
3. Chỉ chọn cột cần thiết; tránh truyền payload lớn nếu không dùng.
4. Dùng WHERE có thể tận dụng index và khoảng thời gian nửa mở.
5. Dùng ORDER BY ổn định và LIMIT phù hợp với page size.
6. Với tập lớn, dùng keyset pagination hoặc quét theo khóa chính từng lô.
7. Với DML diện rộng, chia batch, transaction ngắn, checkpoint và retry an toàn.
8. Đặt timeout phù hợp cho SELECT và giới hạn tải đồng thời.
9. Chạy EXPLAIN; kiểm tra rows, access method, sort và temporary table.
10. Dùng EXPLAIN ANALYZE khi phù hợp để đo actual rows, loops và thời gian.
11. Theo dõi slow query log, Performance Schema và rows examined/rows sent.
12. Benchmark với dữ liệu và tải đại diện trước khi triển khai.

## 20. Checklist trước khi phát hành

- [ ] Truy vấn có điều kiện giới hạn theo nghiệp vụ.
- [ ] Khoảng thời gian hoặc phạm vi dữ liệu có giới hạn hợp lý.
- [ ] Index hỗ trợ điều kiện lọc, JOIN và thứ tự sắp xếp.
- [ ] LIMIT có giá trị tối đa được kiểm soát ở server.
- [ ] ORDER BY có tie-breaker duy nhất.
- [ ] Không dùng OFFSET lớn cho luồng duyệt tập dữ liệu lớn nếu có thể dùng keyset.
- [ ] Chỉ SELECT các cột thực sự cần.
- [ ] COUNT chính xác chỉ chạy khi nghiệp vụ cần.
- [ ] Export lớn chạy theo lô hoặc background job.
- [ ] Batch có checkpoint, high-water mark khi cần và retry an toàn.
- [ ] Transaction không giữ lock/undo lâu ngoài dự kiến.
- [ ] Timeout và giới hạn đồng thời đã được cấu hình phù hợp.
- [ ] EXPLAIN/EXPLAIN ANALYZE đã được kiểm tra trên dữ liệu đại diện.
- [ ] Rows examined, rows sent và thời gian được theo dõi.
- [ ] Đã xác định hành vi khi client ngắt kết nối hoặc job bị dừng giữa lô.

## Kết luận

Kiểm soát truy vấn không giới hạn không chỉ là thêm LIMIT. Cần giới hạn đồng thời phạm vi nghiệp vụ, số hàng phải đọc, kích thước kết quả, thời gian chạy và mức tải đồng thời.

Với request tương tác, dùng điều kiện lọc có index, projection hẹp, thứ tự ổn định và page size tối đa. Với export hoặc migration lớn, dùng keyset/batch theo khóa, checkpoint, transaction ngắn và job nền. Cuối cùng, xác minh bằng EXPLAIN, EXPLAIN ANALYZE, slow query log và Performance Schema để biết MySQL thực sự đọc bao nhiêu dữ liệu so với số hàng ứng dụng nhận được.
