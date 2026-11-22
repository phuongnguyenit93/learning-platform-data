# Invisible index và thử nghiệm bỏ chỉ mục khỏi bộ tối ưu

Khi một chỉ mục có vẻ không còn cần thiết, xóa ngay có thể gây rủi ro: một truy vấn ít được chú ý có thể đang phụ thuộc vào chỉ mục đó và đột ngột chậm đi sau khi xóa. MySQL 8.0 cung cấp **invisible index** (chỉ mục ẩn) để thử nghiệm việc loại một chỉ mục khỏi lựa chọn của bộ tối ưu mà vẫn giữ chỉ mục trong bảng.

Khi index được đặt `INVISIBLE`, optimizer không dùng nó trong kế hoạch truy vấn thông thường. Tuy nhiên, InnoDB vẫn duy trì chỉ mục khi dữ liệu được thêm, sửa hoặc xóa. Nhờ vậy, nhóm vận hành có thể quan sát ảnh hưởng đến kế hoạch đọc trước khi quyết định khôi phục `VISIBLE` hay xóa hẳn chỉ mục.

## 1. Invisible index là gì?

Invisible index là một chỉ mục vẫn tồn tại trong cấu trúc lưu trữ nhưng được đánh dấu không hiển thị với optimizer. Đây là tính năng có từ MySQL 8.0.

Các điểm cần phân biệt:

- Chỉ mục `VISIBLE` có thể được optimizer xem xét bình thường.
- Chỉ mục `INVISIBLE` bị optimizer bỏ qua trong truy vấn thông thường.
- InnoDB vẫn cập nhật invisible index khi `INSERT`, `UPDATE` hoặc `DELETE` làm thay đổi các cột liên quan.
- Invisible index vẫn chiếm dung lượng lưu trữ và vẫn phát sinh chi phí bảo trì khi ghi.
- Nếu là unique index, ràng buộc duy nhất vẫn được thực thi dù index đang invisible.
- Primary key không thể được chuyển thành invisible.

Vì index vẫn tồn tại, invisible index hữu ích để kiểm tra tác động đến lựa chọn kế hoạch truy vấn. Nó không mô phỏng đầy đủ tác động đến dung lượng và chi phí ghi nếu xóa chỉ mục.

## 2. Tạo và chuyển đổi trạng thái index

Ví dụ bảng sản phẩm có chỉ mục theo danh mục và thời điểm tạo:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    created_at DATETIME NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_products_category_created (category_id, created_at)
) ENGINE = InnoDB;
```

Chuyển chỉ mục sang trạng thái invisible:

```sql
ALTER TABLE products
ALTER INDEX idx_products_category_created INVISIBLE;
```

Khôi phục để optimizer sử dụng chỉ mục:

```sql
ALTER TABLE products
ALTER INDEX idx_products_category_created VISIBLE;
```

Có thể kiểm tra trạng thái qua `SHOW INDEX`:

```sql
SHOW INDEX FROM products;
```

Trong MySQL 8.0, kết quả có cột `Visible` cho biết chỉ mục đang `YES` hay `NO`. Có thể xem metadata chi tiết qua `INFORMATION_SCHEMA.STATISTICS`:

```sql
SELECT INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX, IS_VISIBLE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'products'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

`IS_VISIBLE` cho biết trạng thái hiển thị của từng thành phần chỉ mục. Với index ghép, có thể thấy nhiều dòng cùng `INDEX_NAME`, mỗi dòng tương ứng một cột trong chỉ mục.

## 3. Kiểm tra kế hoạch trước khi ẩn index

Trước khi thử nghiệm, cần xác định truy vấn nào có thể đang dùng chỉ mục. Ví dụ:

```sql
EXPLAIN
SELECT product_id, product_name, created_at
FROM products
WHERE category_id = 20
ORDER BY created_at DESC
LIMIT 30;
```

Ghi nhận các thông tin:

- `key`: chỉ mục optimizer đang chọn.
- `type`: kiểu truy cập, chẳng hạn `ref`, `range` hoặc `ALL`.
- `rows`: số hàng ước lượng cần đọc.
- `Extra`: có thể cho biết truy vấn cần `Using filesort` hay có thể dùng index.

Nếu `key` là `idx_products_category_created`, chỉ mục đang góp phần thực thi truy vấn này. Đây là một ứng viên cần kiểm tra kỹ trước khi thử đặt invisible.

Không chỉ xem một truy vấn mẫu. Hãy thu thập các truy vấn quan trọng trong workload, gồm truy vấn đọc theo khóa, lọc, join, sắp xếp, nhóm dữ liệu và các câu lệnh chạy định kỳ ít thường xuyên. Một index có thể không xuất hiện trong truy vấn hàng ngày nhưng vẫn cần cho báo cáo cuối tháng hoặc tác vụ bảo trì.

## 4. Thử nghiệm bỏ index khỏi optimizer

Sau khi ghi nhận kế hoạch ban đầu, chuyển index sang invisible:

```sql
ALTER TABLE products
ALTER INDEX idx_products_category_created INVISIBLE;
```

Chạy lại `EXPLAIN` với cùng câu truy vấn:

```sql
EXPLAIN
SELECT product_id, product_name, created_at
FROM products
WHERE category_id = 20
ORDER BY created_at DESC
LIMIT 30;
```

Optimizer không còn chọn `idx_products_category_created`. Nó có thể chọn một index khác, thực hiện table scan hoặc dùng kế hoạch khác. So sánh `key`, `type`, `rows`, `Extra` và thời gian thực thi để đánh giá tác động.

Nếu cần xem một invisible index có thể tạo ra kế hoạch nào, có thể bật tùy chọn `use_invisible_indexes` trong session thử nghiệm:

```sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'use_invisible_indexes=on';

EXPLAIN
SELECT product_id, product_name, created_at
FROM products
WHERE category_id = 20
ORDER BY created_at DESC
LIMIT 30;

SET SESSION optimizer_switch = @saved_optimizer_switch;
```

Khi `use_invisible_indexes=on`, optimizer được phép xem xét các invisible index trong session đó. Tùy chọn này hữu ích để so sánh kế hoạch khi index đang ẩn và khi được đưa trở lại tập lựa chọn. Ví dụ lưu lại toàn bộ giá trị `optimizer_switch` ban đầu trong biến session rồi khôi phục sau thử nghiệm, đặc biệt khi dùng kết nối từ connection pool.

`EXPLAIN ANALYZE` có thể cung cấp thời gian và số hàng thực tế cho truy vấn `SELECT` trên MySQL 8.0.18 trở lên:

```sql
EXPLAIN ANALYZE
SELECT product_id, product_name, created_at
FROM products
WHERE category_id = 20
ORDER BY created_at DESC
LIMIT 30;
```

Lệnh này thực sự chạy truy vấn. Chỉ sử dụng với câu đọc có thể thực thi an toàn và cân nhắc tải bổ sung khi chạy trên production.

## 5. Quy trình đánh giá một chỉ mục có thể bỏ hay không

Một quy trình thử nghiệm nên có các bước rõ ràng:

1. **Ghi nhận hiện trạng:** tên index, các cột, thứ tự cột, unique hay không, kích thước và các truy vấn đang dùng nó.
2. **Đo baseline:** lưu kế hoạch `EXPLAIN`, thời gian, số hàng đọc và các chỉ số workload trong điều kiện tải đại diện.
3. **Đặt invisible:** chuyển đúng một index sang `INVISIBLE` để xác định ảnh hưởng của riêng index đó.
4. **Quan sát workload:** chạy truy vấn quan trọng, báo cáo, tác vụ định kỳ và luồng nghiệp vụ thực tế; theo dõi độ trễ và tài nguyên.
5. **Quyết định:** nếu có truy vấn suy giảm, khôi phục `VISIBLE`; nếu không thấy ảnh hưởng qua thời gian quan sát đủ đại diện, cân nhắc bước xóa có kiểm soát.
6. **Xác minh sau thay đổi:** tiếp tục theo dõi kế hoạch và độ trễ sau khi khôi phục hoặc xóa index.

Không nên ẩn nhiều index cùng lúc trong lần thử đầu. Nếu kết quả xấu đi, việc xác định index nào gây ra thay đổi sẽ khó hơn.

## 6. Khôi phục và xóa hẳn chỉ mục

Nếu phát hiện truy vấn quan trọng bị chậm, khôi phục ngay trạng thái visible:

```sql
ALTER TABLE products
ALTER INDEX idx_products_category_created VISIBLE;
```

Sau đó kiểm tra lại kế hoạch và hiệu năng của các truy vấn liên quan.

Nếu đã thử nghiệm đủ lâu và xác nhận chỉ mục không còn cần thiết, có thể xóa:

```sql
DROP INDEX idx_products_category_created ON products;
```

Xóa index giải phóng dung lượng và loại bỏ chi phí duy trì index trong các thao tác ghi. Đây là khác biệt quan trọng so với invisible index: invisible chỉ loại index khỏi lựa chọn của optimizer, còn `DROP INDEX` loại bỏ cấu trúc index.

Trước khi drop, hãy kiểm tra index có phục vụ unique constraint, foreign key hoặc truy vấn ít thường xuyên nào không. Đặc biệt, invisible unique index vẫn tiếp tục kiểm tra tính duy nhất; xóa nó sẽ làm mất ràng buộc duy nhất đó. Các index cần thiết cho ràng buộc quan hệ phải được xử lý theo đúng yêu cầu của InnoDB và schema.

## 7. Giới hạn và tác động cần hiểu

### Invisible không đồng nghĩa với disabled

InnoDB vẫn phải duy trì invisible index. Ví dụ, nếu thêm một sản phẩm mới có `category_id` hoặc `created_at` thay đổi, các mục tương ứng trong invisible index vẫn được thêm hoặc cập nhật. Do đó, thử nghiệm invisible không cho biết chính xác mức tiết kiệm thời gian ghi và dung lượng sẽ có sau khi drop.

### Unique index vẫn bảo vệ tính duy nhất

Nếu `email` được bảo vệ bởi unique index đang invisible, hai hàng vẫn không thể có cùng email. Optimizer bỏ qua index để truy vấn, nhưng cơ chế kiểm tra uniqueness vẫn hoạt động khi ghi.

### Primary key không thể invisible

Trong InnoDB, primary key là clustered index và tổ chức dữ liệu của bảng. Không thể dùng invisible index để thử bỏ primary key khỏi optimizer. Cần phân biệt primary key với các secondary index có thể chuyển trạng thái hiển thị.

### Ràng buộc và phụ thuộc schema

Trước khi thay đổi trạng thái một index, kiểm tra xem index có được dùng để đáp ứng ràng buộc hoặc phụ thuộc schema hay không. Không giả định rằng mọi index đều có thể ẩn hoặc xóa tùy ý. Thử thao tác trên môi trường staging với schema tương đương để xác nhận MySQL chấp nhận thay đổi.

### Thay đổi DDL vẫn cần kế hoạch triển khai

`ALTER TABLE` có thể cần metadata lock và có thể ảnh hưởng đến các phiên đang truy cập bảng. Hãy kiểm tra phiên bản MySQL, kích thước bảng, trạng thái transaction dài và quy trình triển khai DDL của hệ thống. Thực hiện trong thời điểm phù hợp và theo dõi sau thay đổi.

## 8. Khi nào nên dùng invisible index?

| Tình huống | Cách xử lý |
|---|---|
| Nghi ngờ một secondary index không còn được truy vấn dùng | Đặt invisible trong giai đoạn quan sát trước khi drop |
| Muốn đo kế hoạch khi optimizer không có một index cụ thể | Đặt invisible rồi so sánh `EXPLAIN` và thời gian |
| Muốn kiểm tra kế hoạch có thể dùng một invisible index | Bật `use_invisible_indexes` trong session thử nghiệm |
| Truy vấn quan trọng suy giảm sau khi ẩn index | Khôi phục `VISIBLE` và điều tra truy vấn bị ảnh hưởng |
| Muốn giảm dung lượng và chi phí ghi thực sự | Chỉ drop sau khi đánh giá đầy đủ và kiểm tra ràng buộc |

Invisible index là công cụ giảm rủi ro khi đánh giá index dư thừa. Nó không thay thế việc thu thập workload, kiểm tra ràng buộc và đo hiệu năng trên dữ liệu đại diện.

## 9. Tự kiểm tra

1. Invisible index khác gì với `DROP INDEX`?
2. Vì sao invisible index vẫn làm phát sinh chi phí khi `INSERT`, `UPDATE` và `DELETE`?
3. Unique index đang invisible có còn ngăn dữ liệu trùng không?
4. Tùy chọn `use_invisible_indexes` có tác dụng gì và nên bật ở phạm vi nào?
5. Vì sao cần quan sát cả các truy vấn ít thường xuyên trước khi drop index?
6. Primary key có thể được chuyển thành invisible không? Vì sao?
7. Vì sao thử nghiệm invisible không đo được đầy đủ lợi ích về chi phí ghi sau khi drop index?

