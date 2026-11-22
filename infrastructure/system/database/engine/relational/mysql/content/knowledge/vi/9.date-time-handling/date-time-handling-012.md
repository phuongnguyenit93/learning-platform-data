# Lọc khoảng thời gian nửa mở và thiết kế truy vấn khai thác chỉ mục

Truy vấn theo thời gian xuất hiện ở hầu hết ứng dụng MySQL: lấy đơn hàng trong ngày, đọc log trong một giờ, tổng hợp doanh thu theo tháng hoặc tìm các sự kiện giao nhau với một khoảng lịch. Cách viết điều kiện thời gian ảnh hưởng đồng thời đến tính đúng của kết quả và khả năng sử dụng index. Một điều kiện tưởng như đơn giản như `DATE(created_at) = '2025-06-10'` có thể khiến MySQL phải tính hàm trên từng hàng thay vì đi thẳng đến vùng dữ liệu cần đọc qua index.

Một mẫu truy vấn thường dễ kiểm soát và thân thiện với index là **khoảng nửa mở**: lấy giá trị từ thời điểm bắt đầu trở đi và loại trừ thời điểm kết thúc, viết thành `column >= start AND column < end`. Cách này tránh phải đoán chữ số cuối của ngày, hoạt động với nhiều độ chính xác phần giây và cho phép ghép các khoảng liền kề mà không trùng hoặc bỏ sót dữ liệu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích khoảng thời gian đóng, mở và nửa mở; chọn quy ước `[start, end)` cho truy vấn theo thời gian.
- Viết điều kiện lọc ngày, tháng, giờ và khoảng tùy chỉnh mà không phụ thuộc FSP của cột.
- Tránh bọc cột có index trong các hàm như `DATE()`, `YEAR()` hoặc `DATE_FORMAT()` khi lọc theo khoảng.
- Thiết kế index đơn và index ghép phù hợp với điều kiện equality, range và `ORDER BY`.
- Dùng `EXPLAIN` để đánh giá kế hoạch truy vấn và xác minh MySQL có thể khai thác index.
- Xử lý đúng ranh giới múi giờ, ngày có thay đổi DST và độ chính xác `DATETIME`/`TIMESTAMP`.
- Viết truy vấn tìm các khoảng thời gian giao nhau và phân trang ổn định theo thời gian.

## 1. Khoảng thời gian đóng, mở và nửa mở

Một khoảng thời gian cần xác định rõ có bao gồm hai đầu mút hay không. Ba quy ước thường gặp:

| Ký hiệu | Điều kiện | Ý nghĩa |
|---|---|---|
| `[start, end]` | `value >= start AND value <= end` | Bao gồm cả đầu và cuối |
| `(start, end)` | `value > start AND value < end` | Loại trừ cả đầu và cuối |
| `[start, end)` | `value >= start AND value < end` | Bao gồm đầu, loại trừ cuối |

Với dữ liệu sự kiện, log và lịch sử giao dịch, khoảng nửa mở `[start, end)` thường là quy ước thuận tiện nhất. Nếu một khoảng kết thúc đúng lúc khoảng kế tiếp bắt đầu, một sự kiện ở ranh giới chỉ thuộc về một khoảng.

Ví dụ hai ngày liên tiếp:

```text
Ngày 10: [2025-06-10 00:00:00, 2025-06-11 00:00:00)
Ngày 11: [2025-06-11 00:00:00, 2025-06-12 00:00:00)
                         ^
                         thời điểm này chỉ thuộc ngày 11
```

Với hai khoảng trên, bản ghi đúng `2025-06-11 00:00:00` không bị tính hai lần trong báo cáo ngày và cũng không bị bỏ sót.

## 2. Vì sao không nên dùng BETWEEN cho toàn bộ một ngày?

`BETWEEN` bao gồm cả hai đầu mút, tương đương `value >= start AND value <= end`. Nếu viết:

```sql
SELECT order_id, created_at
FROM sales_order
WHERE created_at BETWEEN '2025-06-10 00:00:00'
                      AND '2025-06-10 23:59:59';
```

truy vấn có thể bỏ sót những bản ghi sau `23:59:59`, ví dụ `23:59:59.250000` trong cột `DATETIME(6)`. Nếu thay mốc cuối bằng `23:59:59.999999`, truy vấn lại phụ thuộc vào độ chính xác tối đa hiện tại; nó trở nên khó bảo trì khi FSP hoặc kiểu dữ liệu thay đổi.

Hãy viết:

```sql
SELECT order_id, created_at
FROM sales_order
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00';
```

Điều kiện không cần biết cột là `DATETIME`, `DATETIME(3)` hay `DATETIME(6)`. Mọi thời điểm trước nửa đêm ngày kế tiếp đều được lấy; đúng nửa đêm ngày kế tiếp được loại trừ.

`BETWEEN` vẫn phù hợp khi nghiệp vụ thật sự muốn bao gồm cả hai giá trị đầu cuối, ví dụ lọc một dải số hoặc hai mốc timestamp cụ thể có ý nghĩa inclusive. Với truy vấn theo ngày/giờ liên tiếp, hãy ưu tiên khoảng nửa mở.

## 3. Tạo dữ liệu mẫu có ranh giới thời gian

Các ví dụ tiếp theo dùng bảng đơn hàng đơn giản. Hãy thực hành trong database sandbox:

```sql
CREATE TABLE temporal_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

INSERT INTO temporal_order_demo
    (order_id, customer_id, status, created_at, total_amount)
VALUES
    (1, 101, 'PAID',      '2025-06-09 23:59:59.999999', 120000.00),
    (2, 101, 'PAID',      '2025-06-10 00:00:00.000000', 250000.00),
    (3, 102, 'PENDING',   '2025-06-10 09:15:00.123456',  90000.00),
    (4, 101, 'PAID',      '2025-06-10 23:59:59.999999', 450000.00),
    (5, 103, 'CANCELLED', '2025-06-11 00:00:00.000000',  70000.00),
    (6, 102, 'PAID',      '2025-06-11 12:30:00.500000', 180000.00);
```

Bảng có dữ liệu ở sát ranh giới ngày 10/06. Index trên `created_at` sẽ được tạo ở mục 7 để có thể so sánh kế hoạch truy vấn trước và sau khi thêm index. Kiểm tra toàn bộ dữ liệu:

```sql
SELECT order_id, status, created_at
FROM temporal_order_demo
ORDER BY created_at, order_id;
```

## 4. Lọc một ngày bằng khoảng nửa mở

Lấy đơn hàng trong ngày 10/06/2025:

```sql
SELECT order_id, customer_id, status, created_at, total_amount
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00.000000'
  AND created_at <  '2025-06-11 00:00:00.000000'
ORDER BY created_at, order_id;
```

Kết quả gồm các đơn `2`, `3`, `4`. Đơn `1` nằm trước đầu khoảng; đơn `5` đúng thời điểm kết thúc nên thuộc ngày 11 và không được lấy.

Với cột `DATETIME(6)`, có thể ghi rõ sáu chữ số trong literal để dễ đọc. Với cột FSP 0 hoặc 3, cùng nguyên tắc vẫn đúng:

```sql
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'
```

Không cần dùng `CAST()` hoặc `DATE()` lên cột. Hai mốc thời gian là hằng số/parameter ở phía phải của phép so sánh; cột được giữ nguyên để MySQL có thể tìm một vùng liên tục trong index.

## 5. Tính mốc bắt đầu và kết thúc cho ngày, tháng và giờ

Ứng dụng nên tính hai mốc theo múi giờ nghiệp vụ rồi truyền chúng dưới dạng parameter. Nếu tính trong SQL, hãy tạo mốc kết thúc bằng cách cộng một đơn vị vào đầu khoảng, thay vì cố tìm “giây cuối cùng” của đơn vị thời gian.

### 5.1. Một ngày cụ thể

```sql
SET @day_start = CAST('2025-06-10 00:00:00' AS DATETIME);
SET @day_end = DATE_ADD(@day_start, INTERVAL 1 DAY);

SELECT order_id, created_at
FROM temporal_order_demo
WHERE created_at >= @day_start
  AND created_at <  @day_end
ORDER BY created_at, order_id;
```

### 5.2. Một tháng cụ thể

Lấy toàn bộ tháng 6/2025:

```sql
SET @month_start = '2025-06-01 00:00:00';
SET @next_month_start = DATE_ADD(@month_start, INTERVAL 1 MONTH);

SELECT order_id, created_at, total_amount
FROM temporal_order_demo
WHERE created_at >= @month_start
  AND created_at <  @next_month_start
ORDER BY created_at, order_id;
```

Cách tính này tự xử lý tháng có 28, 29, 30 hoặc 31 ngày. Không cần gọi `LAST_DAY(created_at)` trên từng hàng.

### 5.3. Một giờ cụ thể

Lấy các đơn hàng trong giờ 09:00 đến trước 10:00:

```sql
SET @hour_start = '2025-06-10 09:00:00';
SET @next_hour_start = DATE_ADD(@hour_start, INTERVAL 1 HOUR);

SELECT order_id, created_at
FROM temporal_order_demo
WHERE created_at >= @hour_start
  AND created_at <  @next_hour_start;
```

### 5.4. Khoảng tùy chỉnh

Một API báo cáo có thể nhận `from` và `to` theo hợp đồng `[from, to)`:

```sql
SELECT order_id, status, created_at
FROM temporal_order_demo
WHERE created_at >= ?
  AND created_at <  ?
ORDER BY created_at, order_id;
```

Ứng dụng bind hai giá trị thời gian qua prepared statement. Cần xác thực `from < to`, giới hạn độ dài khoảng truy vấn và chuẩn hóa múi giờ trước khi gọi database. Không ghép trực tiếp chuỗi đầu vào vào SQL.

## 6. Giữ điều kiện trên cột ở dạng có thể dùng index

Một điều kiện được gọi là *sargable* khi có dạng giúp bộ tối ưu tìm kiếm qua index. Với index B-tree trên `created_at`, dạng so sánh trực tiếp cột với mốc thời gian thường có thể dùng range access:

```sql
-- Dạng thân thiện với index
SELECT order_id, created_at
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00';
```

Các cách viết sau thường khiến index trên `created_at` khó được dùng để định vị vùng thời gian, vì hàm được áp dụng lên từng giá trị cột:

```sql
-- Tránh khi cần range access trên index created_at
SELECT order_id, created_at
FROM temporal_order_demo
WHERE DATE(created_at) = '2025-06-10';

SELECT order_id, created_at
FROM temporal_order_demo
WHERE YEAR(created_at) = 2025
  AND MONTH(created_at) = 6;

SELECT order_id, created_at
FROM temporal_order_demo
WHERE DATE_FORMAT(created_at, '%Y-%m') = '2025-06';
```

Các truy vấn này có thể trả đúng kết quả nhưng thường phải đánh giá biểu thức trên nhiều hàng. Hãy chuyển điều kiện thành khoảng:

```sql
-- Tương đương lọc theo ngày
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'

-- Tương đương lọc tháng 6/2025
WHERE created_at >= '2025-06-01 00:00:00'
  AND created_at <  '2025-07-01 00:00:00'
```

MySQL 8.0.13 trở lên có functional index, và một số phiên bản hỗ trợ index trên generated column. Nếu nghiệp vụ thường xuyên truy vấn theo biểu thức ngày đã chuẩn hóa, đây có thể là lựa chọn thiết kế riêng. Tuy nhiên, với truy vấn khoảng thời gian thông thường, index trên cột thời gian gốc cùng điều kiện range vẫn là phương án đơn giản, linh hoạt và dễ tái sử dụng.

## 7. Thiết kế index đơn cho truy vấn thời gian

Nếu truy vấn chủ yếu lọc theo `created_at`, index B-tree trên cột này là điểm bắt đầu:

```sql
CREATE INDEX idx_temporal_order_created_at
ON temporal_order_demo (created_at);
```

Index giúp MySQL xác định vị trí bắt đầu và kết thúc của vùng timestamp cần đọc. Hiệu quả phụ thuộc tỷ lệ hàng nằm trong khoảng, kích thước bảng, độ phân bố dữ liệu, chi phí truy cập hàng và thống kê của optimizer. Nếu truy vấn lấy phần lớn bảng, full table scan vẫn có thể là lựa chọn rẻ hơn.

Kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT order_id, customer_id, status, created_at, total_amount
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'
ORDER BY created_at, order_id;
```

Các cột quan trọng trong `EXPLAIN` dạng truyền thống:

| Cột | Cách đọc |
|---|---|
| `type` | Kiểu truy cập; `range` thường cho biết optimizer dùng một khoảng index |
| `possible_keys` | Các index có thể được xem xét |
| `key` | Index được chọn thực tế; `NULL` nghĩa là không chọn index |
| `key_len` | Độ dài phần index được sử dụng |
| `rows` | Số hàng ước lượng cần đọc |
| `filtered` | Tỷ lệ hàng ước lượng còn lại sau điều kiện lọc |
| `Extra` | Thông tin bổ sung như `Using where`, `Using index` hoặc `Using filesort` |

Không nên kết luận truy vấn nhanh chỉ vì `key` khác `NULL`. Hãy xem thêm `rows`, `type`, `Extra`, số hàng thực tế và thời gian thực thi. Một range scan có thể vẫn đọc rất nhiều hàng nếu khoảng lọc quá rộng.

## 8. Index ghép: điều kiện equality trước, range sau

Một truy vấn thực tế thường lọc theo khách hàng và khoảng thời gian:

```sql
SELECT order_id, status, created_at, total_amount
FROM temporal_order_demo
WHERE customer_id = 101
  AND created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-12 00:00:00'
ORDER BY created_at, order_id;
```

Index ghép phù hợp có thể là:

```sql
CREATE INDEX idx_temporal_order_customer_created
ON temporal_order_demo (customer_id, created_at);
```

Với index `(customer_id, created_at)`, MySQL có thể định vị vùng của một `customer_id` cụ thể, rồi quét range theo `created_at` bên trong vùng đó. Đây là ví dụ phổ biến của nguyên tắc: cột equality đứng trước, cột range đứng sau.

Index ghép tuân theo quy tắc leftmost prefix. Index `(customer_id, created_at)` hỗ trợ tốt truy vấn lọc theo `customer_id`, và truy vấn lọc theo `customer_id` cùng khoảng `created_at`. Nó không tương đương index độc lập trên `created_at` cho truy vấn chỉ lọc thời gian, vì `created_at` không phải cột đầu tiên của index.

Nếu hệ thống có cả hai nhóm truy vấn — một nhóm lọc theo thời gian toàn hệ thống, nhóm kia lọc theo khách hàng và thời gian — có thể cần hai index khác nhau. Quyết định phải dựa trên workload và chi phí ghi, dung lượng index, không chỉ một câu SQL đơn lẻ.

### 8.1. Khi có thêm trạng thái

Ví dụ truy vấn đơn hàng đã thanh toán của một khách hàng trong khoảng thời gian:

```sql
SELECT order_id, created_at, total_amount
FROM temporal_order_demo
WHERE customer_id = 101
  AND status = 'PAID'
  AND created_at >= '2025-06-01 00:00:00'
  AND created_at <  '2025-07-01 00:00:00'
ORDER BY created_at;
```

Có thể thử index:

```sql
CREATE INDEX idx_temporal_order_customer_status_created
ON temporal_order_demo (customer_id, status, created_at);
```

Hai cột equality đứng trước cột range. Nhưng thứ tự tốt nhất còn tùy độ chọn lọc, các truy vấn khác và cách dữ liệu phân bố. Nếu `status` chỉ có vài giá trị, index bắt đầu bằng `status` có thể không hiệu quả cho nhiều truy vấn. Hãy so sánh kế hoạch và số hàng đọc trước khi giữ index.

### 8.2. ORDER BY và index

Index `(customer_id, created_at)` có thể giúp truy vấn một khách hàng đọc theo thứ tự `created_at`. Nếu truy vấn yêu cầu `ORDER BY created_at, order_id`, InnoDB có thể sử dụng phần khóa chính được gắn vào secondary index để phân định hàng, nhưng khả năng tránh sort phụ thuộc cấu trúc index, hướng sắp xếp và kế hoạch thực tế. Hãy kiểm tra `Extra` trong `EXPLAIN`; không mặc định rằng có index là luôn loại bỏ được `filesort`.

## 9. Tránh chuyển đổi kiểu dữ liệu trên cột thời gian

Một lỗi khác là so sánh cột temporal với chuỗi không chuẩn hoặc biểu thức không cùng kiểu. MySQL có thể chuyển đổi ngầm, nhưng kết quả và khả năng dùng index khó dự đoán hơn khi dữ liệu đầu vào không chuẩn.

Nên bind tham số có kiểu thời gian rõ ràng từ driver. Nếu cần kiểm tra bằng SQL literal, dùng định dạng chuẩn:

```sql
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'
```

Tránh viết điều kiện như:

```sql
WHERE DATE(created_at) >= '2025-06-10'
```

hoặc ép kiểu cột trong `WHERE` khi không cần thiết. Nếu cần chuyển đổi đầu vào, hãy chuyển đổi parameter hoặc tính sẵn hai mốc trước khi truy vấn để cột được so sánh trực tiếp.

## 10. Múi giờ và ngày có thay đổi DST

Khoảng `[start, end)` chỉ chính xác khi `start` và `end` được tính theo đúng múi giờ mà nghiệp vụ yêu cầu. Đây là điểm cần đặc biệt chú ý với `TIMESTAMP` và báo cáo theo ngày địa phương.

### 10.1. DATETIME và TIMESTAMP

- `DATETIME` lưu thành phần ngày giờ theo đúng giá trị được ghi; MySQL không tự chuyển đổi theo session time zone.
- `TIMESTAMP` chuyển đổi giữa múi giờ session và UTC khi ghi/đọc.

Nếu lưu sự kiện theo UTC, một chiến lược phổ biến là chuẩn hóa input về UTC trước khi bind vào `TIMESTAMP` hoặc lưu vào `DATETIME` theo hợp đồng UTC rõ ràng. Khi truy vấn, dùng cùng quy ước cho cả hai mốc.

### 10.2. Lọc một ngày địa phương

Một ngày theo múi giờ địa phương không phải lúc nào cũng dài đúng 24 giờ ở những khu vực có Daylight Saving Time (DST). Khi đồng hồ chuyển sang giờ mùa hè, có ngày dài 23 giờ; khi quay lại giờ chuẩn, có ngày dài 25 giờ.

Đối với báo cáo theo ngày địa phương:

1. Xác định múi giờ IANA của nghiệp vụ, ví dụ `Asia/Ho_Chi_Minh` hoặc `America/New_York`.
2. Tính thời điểm bắt đầu ngày địa phương và thời điểm bắt đầu ngày kế tiếp trong múi giờ đó.
3. Chuyển cả hai mốc sang UTC nếu cột lưu UTC.
4. Bind hai mốc UTC vào điều kiện `timestamp_column >= start_utc AND timestamp_column < end_utc`.

Không nên luôn lấy `start_utc + INTERVAL 24 HOUR` để tạo ngày kết thúc nếu ngày nghiệp vụ nằm trong múi giờ có DST. Hãy tính nửa đêm ngày kế tiếp theo múi giờ địa phương rồi mới chuyển sang UTC. Với `Asia/Ho_Chi_Minh`, hiện không có chuyển đổi DST theo quy tắc hiện hành, nhưng ứng dụng đa vùng vẫn nên dùng quy trình tính biên ngày theo timezone database thay vì giả định mọi nơi đều giống nhau.

### 10.3. Tránh chuyển đổi cột trong WHERE

Nếu cột `created_at` lưu UTC, tránh:

```sql
WHERE CONVERT_TZ(created_at, '+00:00', 'America/New_York') >= ?
```

Biểu thức chuyển đổi trên cột có thể ngăn range access trực tiếp trên index. Thay vào đó, chuyển hai mốc địa phương sang UTC ở ứng dụng hoặc tính trước thành biến, rồi so sánh trực tiếp cột UTC:

```sql
WHERE created_at >= ?  -- start_utc
  AND created_at <  ?  -- end_utc
```

Đây vừa là cách giữ ngữ nghĩa múi giờ rõ ràng vừa thân thiện với index.

## 11. Tìm các bản ghi có khoảng thời gian giao nhau

Không phải truy vấn thời gian nào cũng lọc theo một cột timestamp. Với lịch phòng họp, phiên làm việc hoặc hợp đồng, mỗi bản ghi có `starts_at` và `ends_at`. Để tìm các khoảng giao nhau với khoảng yêu cầu `[requested_start, requested_end)`, dùng:

```sql
existing.starts_at < requested_end
AND existing.ends_at > requested_start
```

Hai khoảng nửa mở giao nhau khi điểm bắt đầu của khoảng hiện có nhỏ hơn điểm kết thúc yêu cầu và điểm kết thúc của khoảng hiện có lớn hơn điểm bắt đầu yêu cầu.

Ví dụ:

```sql
SELECT booking_id, starts_at, ends_at
FROM room_booking
WHERE starts_at <  '2025-06-10 11:00:00'
  AND ends_at   >  '2025-06-10 10:00:00';
```

Truy vấn trả về các booking giao với khoảng 10:00 đến trước 11:00. Một booking kết thúc đúng 10:00 không giao nhau; một booking bắt đầu đúng 11:00 cũng không giao nhau. Hai khoảng tiếp giáp nhau không bị xem là chồng lấn.

Hãy xác định chính sách cho khoảng rỗng hoặc không hợp lệ. Nếu `starts_at = ends_at` biểu thị khoảng không có thời lượng, thường không nên xem nó là booking chiếm thời gian. Nếu `ends_at` có thể là `NULL` để biểu thị khoảng chưa kết thúc, cần mở rộng điều kiện, ví dụ `AND (ends_at IS NULL OR ends_at > requested_start)`, và định nghĩa rõ ý nghĩa của trạng thái đó.

Về index, truy vấn overlap có điều kiện range trên hai cột khác nhau. Một index ghép `(starts_at, ends_at)` có thể hỗ trợ phần lọc bắt đầu, nhưng không thể luôn biến cả hai điều kiện thành một range index duy nhất. Hãy kiểm tra kế hoạch với dữ liệu thực tế, chọn chiến lược phù hợp hoặc cân nhắc mô hình dữ liệu chuyên biệt nếu workload truy vấn overlap rất lớn.

## 12. Phân trang theo thời gian ổn định

Khi một bảng log có nhiều hàng cùng timestamp, phân trang chỉ bằng `created_at` có thể làm bản ghi bị lặp hoặc bỏ sót giữa các trang. Hãy thêm khóa duy nhất làm tie-breaker:

```sql
SELECT order_id, created_at, status
FROM temporal_order_demo
WHERE created_at >= ?
  AND created_at <  ?
ORDER BY created_at, order_id
LIMIT 50;
```

Với keyset pagination, trang tiếp theo dùng cặp giá trị cuối cùng của trang trước:

```sql
SELECT order_id, created_at, status
FROM temporal_order_demo
WHERE created_at >= ?
  AND created_at <  ?
  AND (
        created_at > ?
        OR (created_at = ? AND order_id > ?)
      )
ORDER BY created_at, order_id
LIMIT 50;
```

Index `(created_at, order_id)` có thể phù hợp cho dạng phân trang này. Nếu InnoDB dùng secondary index, primary key được lưu cùng entry secondary index; tuy nhiên hãy kiểm tra index thực tế và kế hoạch thực thi. Tie-breaker phải duy nhất để thứ tự phân trang có tính xác định.

Offset pagination (`LIMIT 50 OFFSET 50000`) có thể phải đọc và bỏ qua nhiều hàng khi offset lớn. Keyset pagination thường phù hợp hơn cho luồng sự kiện tăng dần vì trang tiếp theo bắt đầu từ vị trí cuối đã đọc.

## 13. Đọc kế hoạch và đo truy vấn

Để so sánh truy vấn dùng hàm trên cột với truy vấn range, chạy `EXPLAIN` trên cả hai:

```sql
EXPLAIN
SELECT order_id
FROM temporal_order_demo
WHERE DATE(created_at) = '2025-06-10';

EXPLAIN
SELECT order_id
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00';
```

Với bảng mẫu nhỏ, optimizer có thể chọn table scan ngay cả khi có index vì đọc toàn bảng rẻ hơn. Điều đó không chứng minh range predicate không dùng được index. Hãy thử với dữ liệu đủ lớn và phân bố gần workload thực tế.

Trong MySQL 8.0.18 trở lên, `EXPLAIN ANALYZE` thực thi câu truy vấn và báo số liệu thực tế như thời gian, số vòng lặp và số hàng. Chỉ dùng trên truy vấn an toàn và môi trường có tải phù hợp; câu lệnh có thể tiêu tốn tài nguyên vì nó thực sự chạy truy vấn.

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM temporal_order_demo
WHERE created_at >= '2025-06-10 00:00:00'
  AND created_at <  '2025-06-11 00:00:00'
ORDER BY created_at, order_id;
```

Khi đánh giá, hãy xem:

- Optimizer có chọn index dự kiến không?
- Có range scan hay table scan?
- Số hàng ước lượng có gần số hàng thực tế không?
- Truy vấn có cần filesort hoặc temporary table không?
- Thời gian thực tế và số hàng đọc có đáp ứng mục tiêu không?
- Kế hoạch có thay đổi khi khoảng thời gian rộng hơn hoặc hẹp hơn không?

## 14. Checklist thiết kế truy vấn thời gian có index

- Đã xác định rõ hai mốc bắt đầu và kết thúc, cùng quy ước bao gồm/loại trừ đầu mút.
- Đã dùng `[start, end)` với `>= start` và `< end` cho khoảng ngày/giờ liền kề.
- Đã tính mốc kết thúc bằng đầu đơn vị tiếp theo, không đoán `23:59:59.999999`.
- Đã giữ cột thời gian nguyên bản trong `WHERE`, tránh bọc bằng `DATE()`, `YEAR()`, `DATE_FORMAT()` hoặc `CONVERT_TZ()`.
- Đã bind parameter có kiểu và độ chính xác phù hợp với cột.
- Đã chọn index đơn hoặc ghép theo workload; với index ghép, đã cân nhắc leftmost prefix và equality trước range.
- Đã xem xét cả `ORDER BY`, tie-breaker và phân trang ổn định.
- Đã tính ranh giới theo múi giờ nghiệp vụ; với vùng có DST, đã tính hai đầu ngày riêng biệt.
- Đã kiểm tra truy vấn overlap theo quy tắc khoảng nửa mở và chính sách `NULL`.
- Đã dùng `EXPLAIN` hoặc `EXPLAIN ANALYZE` phù hợp để xác minh kế hoạch và chi phí.
- Đã thử khoảng hẹp, rộng, ranh giới nửa đêm và giá trị có FSP cao.

Khoảng nửa mở giúp truy vấn thời gian không phụ thuộc chữ số cuối của ngày hoặc FSP, đồng thời tránh trùng lặp ở ranh giới giữa các khoảng. Giữ cột thời gian nguyên bản trong điều kiện range và thiết kế index theo các cột equality, range cùng thứ tự sắp xếp sẽ giúp MySQL có cơ hội khai thác B-tree hiệu quả. Cuối cùng, hãy xác minh bằng `EXPLAIN` và dữ liệu thực tế, vì lựa chọn index luôn phụ thuộc phân bố dữ liệu và phạm vi truy vấn.
