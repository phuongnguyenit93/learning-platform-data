# ORDER BY, thứ tự NULL và yêu cầu sắp xếp xác định

`ORDER BY` sắp xếp các hàng trong kết quả truy vấn theo một hoặc nhiều biểu thức. Bạn có thể chọn chiều tăng dần (`ASC`), giảm dần (`DESC`), điều khiển vị trí của giá trị `NULL` bằng biểu thức, và bổ sung khóa phụ để kết quả có thứ tự ổn định.

Trong MySQL, `NULL` được xem là nhỏ hơn mọi giá trị không `NULL` khi sắp xếp: `ASC` đưa `NULL` lên trước, còn `DESC` đưa `NULL` xuống cuối. Nếu nghiệp vụ cần vị trí khác, hãy chỉ định rõ trong `ORDER BY`. Đặc biệt, khi dùng `LIMIT`, phân trang hoặc xử lý theo thứ tự ưu tiên, cần tạo một thứ tự xác định bằng cách bổ sung cột phân biệt duy nhất, thường là khóa chính.

## 1. Cú pháp cơ bản của ORDER BY

Cú pháp tổng quát:

```sql
SELECT column_list
FROM table_name
WHERE condition
ORDER BY expression [ASC | DESC], expression [ASC | DESC];
```

- `ASC` sắp xếp tăng dần và là mặc định nếu không ghi chiều.
- `DESC` sắp xếp giảm dần.
- Có thể sắp xếp theo nhiều cột hoặc biểu thức. MySQL xét biểu thức sau trước; nếu hai hàng bằng nhau ở biểu thức đó, nó xét biểu thức kế tiếp.
- `ORDER BY` nằm ở cuối truy vấn, sau `WHERE`, `GROUP BY` và `HAVING` nếu các mệnh đề này có mặt.

Ví dụ sắp xếp sản phẩm theo giá tăng dần:

```sql
SELECT id, name, price
FROM products
ORDER BY price ASC;
```

Sắp xếp giá giảm dần:

```sql
SELECT id, name, price
FROM products
ORDER BY price DESC;
```

Có thể bỏ `ASC` vì đó là chiều mặc định:

```sql
SELECT id, name, price
FROM products
ORDER BY price;
```

## 2. Sắp xếp theo nhiều cột

Khi sắp xếp theo nhiều biểu thức, thứ tự ưu tiên đi từ trái sang phải. Ví dụ, hiển thị đơn hàng theo trạng thái rồi theo thời gian tạo:

```sql
SELECT id, status, created_at
FROM orders
ORDER BY status ASC, created_at DESC, id DESC;
```

MySQL thực hiện theo thứ tự:

1. Nhóm các hàng theo `status` tăng dần.
2. Trong cùng một trạng thái, xếp `created_at` mới nhất trước.
3. Nếu hai hàng có cùng trạng thái và cùng thời điểm tạo, xếp `id` giảm dần.

Chiều sắp xếp có thể khác nhau giữa các cột. Điều này hữu ích khi cần ưu tiên một nhóm theo thứ tự nghiệp vụ nhưng vẫn muốn sắp xếp thời gian hoặc mã theo chiều khác.

Ví dụ ưu tiên đơn hàng đang chờ trước, sau đó đến đơn đã xác nhận, rồi sắp xếp mới nhất trong mỗi nhóm:

```sql
SELECT id, status, created_at
FROM orders
ORDER BY
    CASE status
        WHEN 'pending' THEN 1
        WHEN 'confirmed' THEN 2
        WHEN 'shipped' THEN 3
        WHEN 'cancelled' THEN 4
        ELSE 5
    END ASC,
    created_at DESC,
    id DESC;
```

`CASE` thể hiện thứ tự nghiệp vụ tường minh, không phụ thuộc thứ tự từ điển của chuỗi trạng thái.

## 3. Thứ tự mặc định của NULL trong MySQL

MySQL xem `NULL` nhỏ hơn các giá trị không `NULL` khi sắp xếp. Vì vậy:

| Câu lệnh | Vị trí của NULL |
| --- | --- |
| `ORDER BY column ASC` | Đầu kết quả |
| `ORDER BY column DESC` | Cuối kết quả |

Ví dụ với thời hạn công việc:

```sql
CREATE TABLE tasks (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(150) NOT NULL,
    due_at DATETIME NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO tasks (title, due_at) VALUES
    ('Viết tài liệu', '2026-11-20 09:00:00'),
    ('Rà soát schema', NULL),
    ('Kiểm thử truy vấn', '2026-11-19 15:00:00'),
    ('Cập nhật ví dụ', NULL);
```

Sắp xếp thời hạn tăng dần:

```sql
SELECT id, title, due_at
FROM tasks
ORDER BY due_at ASC;
```

Hai công việc chưa có thời hạn (`NULL`) xuất hiện trước các công việc có thời hạn. Khi sắp xếp giảm dần:

```sql
SELECT id, title, due_at
FROM tasks
ORDER BY due_at DESC;
```

Các thời hạn mới hơn xuất hiện trước, còn hàng `NULL` nằm cuối.

Không nên giả định MySQL xử lý `NULL` giống mọi hệ quản trị cơ sở dữ liệu khác. Khi chuyển ứng dụng giữa các database, hãy kiểm tra quy tắc sắp xếp NULL của hệ quản trị đích.

## 4. Đưa NULL lên đầu hoặc xuống cuối một cách tường minh

Mặc định của MySQL đã đưa `NULL` lên đầu khi `ASC` và xuống cuối khi `DESC`. Nhưng đôi khi nghiệp vụ cần `NULL` ở vị trí ngược lại, ví dụ công việc chưa có thời hạn phải xuất hiện sau những công việc đã được lên lịch, bất kể chiều sắp xếp.

### 4.1. NULL ở cuối khi sắp xếp tăng dần

```sql
SELECT id, title, due_at
FROM tasks
ORDER BY
    due_at IS NULL ASC,
    due_at ASC,
    id ASC;
```

Biểu thức `due_at IS NULL` trả về `0` với giá trị không `NULL` và `1` với giá trị `NULL`. Sắp xếp biểu thức này tăng dần khiến hàng có thời hạn (`0`) đứng trước hàng chưa có thời hạn (`1`).

### 4.2. NULL ở đầu khi sắp xếp giảm dần

```sql
SELECT id, title, due_at
FROM tasks
ORDER BY
    due_at IS NULL DESC,
    due_at DESC,
    id DESC;
```

Sắp xếp cờ `IS NULL` giảm dần đưa hàng `NULL` lên trước; trong từng nhóm, `due_at` được sắp xếp giảm dần.

### 4.3. Bảng tổng hợp cách điều khiển vị trí NULL

| Mục tiêu | ORDER BY |
| --- | --- |
| Tăng dần, NULL đầu (mặc định) | `column ASC` |
| Tăng dần, NULL cuối | `column IS NULL ASC, column ASC` |
| Giảm dần, NULL cuối (mặc định) | `column DESC` |
| Giảm dần, NULL đầu | `column IS NULL DESC, column DESC` |

Trong truy vấn thực tế, hãy thêm khóa phụ duy nhất sau các biểu thức trên để phân định các hàng có cùng giá trị:

```sql
ORDER BY due_at IS NULL ASC, due_at ASC, id ASC;
```

## 5. Vì sao cần thứ tự xác định?

Nếu nhiều hàng có cùng giá trị của tất cả biểu thức trong `ORDER BY`, MySQL không cam kết thứ tự tương đối giữa những hàng đó. Kết quả có thể thay đổi giữa các lần chạy do kế hoạch thực thi, index, dữ liệu mới, thống kê hoặc phiên bản server.

Ví dụ:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC
LIMIT 10;
```

Nếu nhiều bài viết có cùng `created_at`, truy vấn không xác định bài nào đứng trước trong nhóm trùng thời điểm. Khi dùng `LIMIT 10`, ranh giới giữa hàng thứ 10 và hàng thứ 11 có thể thay đổi.

Hãy bổ sung một cột hoặc tổ hợp cột bảo đảm duy nhất:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 10;
```

Ở đây `id` là khóa chính nên mỗi hàng có thứ tự phân biệt. Thứ tự theo `created_at` vẫn là tiêu chí chính; `id` chỉ phân định khi thời điểm tạo bằng nhau.

Một thứ tự xác định cần có tính chất: với hai hàng bất kỳ trong tập kết quả, tổ hợp biểu thức sắp xếp phải phân biệt được chúng. Dùng khóa chính làm biểu thức cuối thường là cách đơn giản và đáng tin cậy.

## 6. ORDER BY không có nghĩa là thứ tự vật lý của bảng

Nếu truy vấn không có `ORDER BY`, SQL không bảo đảm thứ tự hàng trả về. Thứ tự nhìn thấy có thể tình cờ giống thứ tự chèn, thứ tự primary key hoặc thứ tự một index, nhưng đó không phải hợp đồng của truy vấn.

Ví dụ:

```sql
SELECT id, title
FROM articles;
```

Không thể dựa vào thứ tự kết quả này để hiển thị bài viết mới nhất, xử lý theo FIFO hoặc phân trang. Muốn có thứ tự, phải chỉ định `ORDER BY` trong truy vấn ngoài cùng.

Ngay cả khi truy vấn con hoặc view có `ORDER BY`, truy vấn bên ngoài vẫn cần `ORDER BY` riêng nếu ứng dụng yêu cầu kết quả có thứ tự. Quan hệ thứ tự không tự động được bảo toàn qua mọi phép biến đổi truy vấn.

## 7. ORDER BY với biểu thức và alias

MySQL cho phép sắp xếp theo cột, alias trong danh sách `SELECT` hoặc biểu thức:

```sql
SELECT
    id,
    quantity,
    unit_price,
    quantity * unit_price AS line_total
FROM order_items
ORDER BY line_total DESC, id ASC;
```

Có thể dùng trực tiếp biểu thức:

```sql
SELECT id, quantity, unit_price
FROM order_items
ORDER BY quantity * unit_price DESC, id ASC;
```

Alias giúp câu lệnh dễ đọc khi biểu thức dài hoặc được hiển thị như một cột kết quả. Nếu tên alias trùng tên cột nguồn, quy tắc phân giải tên có thể gây nhầm lẫn; hãy đặt alias khác biệt và dùng tên rõ ràng.

Không nên phụ thuộc vào vị trí cột dạng số trong `ORDER BY`:

```sql
-- Có thể chạy nhưng khó bảo trì
SELECT id, title, created_at
FROM articles
ORDER BY 3 DESC;
```

Nếu sau này thay đổi thứ tự cột trong `SELECT`, ý nghĩa `ORDER BY 3` cũng thay đổi. Dùng `ORDER BY created_at DESC` rõ ràng hơn.

## 8. Collation ảnh hưởng đến sắp xếp chuỗi

Khi sắp xếp cột văn bản, MySQL dùng collation của biểu thức để so sánh chuỗi. Collation quyết định các khác biệt như chữ hoa/thường, dấu và quy tắc ngôn ngữ.

Ví dụ:

```sql
SELECT id, display_name
FROM customers
ORDER BY display_name ASC, id ASC;
```

Nếu collation không phân biệt hoa/thường, `An` và `an` có thể được xem là tương đương trong phép so sánh. Nếu collation không phân biệt dấu, một số biến thể có/không dấu cũng có thể có cùng trọng số sắp xếp. Khi đó, thêm `id` làm khóa phụ để kết quả có thứ tự xác định.

Có thể chỉ định collation cho biểu thức sắp xếp:

```sql
SELECT id, display_name
FROM customers
ORDER BY display_name COLLATE utf8mb4_0900_as_cs ASC, id ASC;
```

Collation `utf8mb4_0900_as_cs` là ví dụ trên MySQL 8.0; cần chọn collation thực sự có trong phiên bản và charset của cột. Ép collation khác có thể thay đổi thứ tự và ảnh hưởng khả năng tận dụng index, vì vậy hãy kiểm tra bằng `EXPLAIN`.

## 9. ORDER BY với LIMIT

`LIMIT` giới hạn số hàng trả về. Khi kết hợp với `ORDER BY`, nó thường dùng để lấy top-N hoặc một trang kết quả:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Truy vấn lấy 20 bài mới nhất theo thứ tự xác định. Nếu bỏ `ORDER BY`, 20 hàng được trả về không đại diện cho “20 bài mới nhất” hay bất kỳ thứ tự nghiệp vụ nào.

Có thể dùng `LIMIT offset, row_count`:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20, 10;
```

Truy vấn bỏ qua 20 hàng đầu rồi lấy 10 hàng tiếp theo. Thứ tự xác định giúp kết quả phân trang ổn định hơn, nhưng offset lớn vẫn có thể tốn chi phí vì MySQL phải tìm và đi qua các hàng bị bỏ qua.

## 10. Phân trang ổn định bằng keyset pagination

Với bảng lớn, keyset pagination (seek method) thường hiệu quả hơn offset pagination. Thay vì bỏ qua một số lượng hàng, ứng dụng gửi giá trị khóa sắp xếp cuối cùng của trang trước để lấy các hàng kế tiếp.

Giả sử `created_at` và `id` đều `NOT NULL`, truy vấn trang đầu:

```sql
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Giả sử hàng cuối trang có `created_at = '2026-11-18 10:30:00'` và `id = 500`. Truy vấn trang tiếp theo:

```sql
SELECT id, title, created_at
FROM articles
WHERE created_at < '2026-11-18 10:30:00'
   OR (
       created_at = '2026-11-18 10:30:00'
       AND id < 500
   )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Điều kiện khớp với thứ tự giảm dần của cặp `(created_at, id)`: lấy những hàng đứng sau khóa cuối trang. Trong ứng dụng, hai giá trị cursor nên được truyền dưới dạng tham số hóa.

Keyset pagination có các ưu điểm:

- Không cần quét và bỏ qua hàng nghìn bản ghi trước vị trí trang.
- Ít bị dịch chuyển trang khi có hàng mới được thêm trước vị trí cursor.
- Dùng tốt với index phù hợp trên các cột sắp xếp.

Nó vẫn cần một thứ tự duy nhất và có thể chịu ảnh hưởng nếu các cột sắp xếp của hàng bị cập nhật trong lúc người dùng duyệt. Nếu cần một ảnh chụp dữ liệu nhất quán xuyên nhiều trang, hãy cân nhắc transaction snapshot hoặc một mốc dữ liệu cố định theo yêu cầu nghiệp vụ.

Ví dụ trên giả định cột sắp xếp không `NULL`. Nếu cột nullable, cần thiết kế điều kiện cursor khớp chính xác với quy tắc NULL đã chọn; không dùng phép so sánh `<`/`>` đơn giản vì so sánh với `NULL` trả `UNKNOWN`.

## 11. Index và hiệu năng của ORDER BY

MySQL có thể dùng index để trả kết quả theo thứ tự mà không cần thực hiện một bước sort riêng nếu cấu trúc index và truy vấn phù hợp. Ví dụ:

```sql
CREATE INDEX idx_articles_created_id
ON articles (created_at DESC, id DESC);

SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Index ghép có thể hỗ trợ thứ tự khi các cột và chiều sắp xếp phù hợp. Các điều kiện lọc, thứ tự cột trong index, chiều ASC/DESC, collation và biểu thức trong `ORDER BY` đều ảnh hưởng quyết định của optimizer.

Kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT id, title, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Nếu phần `Extra` hiển thị `Using filesort`, MySQL cần thực hiện một bước sắp xếp bổ sung thay vì lấy toàn bộ thứ tự trực tiếp từ index. Tên `filesort` không đồng nghĩa chắc chắn dữ liệu sort được ghi ra đĩa; thuật toán có thể dùng bộ nhớ hoặc file tạm tùy kích thước và cấu hình.

Không nên thêm index chỉ để loại bỏ `Using filesort` mà chưa đo lợi ích. Index làm tăng dung lượng và chi phí ghi. Hãy dùng dữ liệu thực tế, `EXPLAIN` hoặc `EXPLAIN ANALYZE` trên phiên bản hỗ trợ để đánh giá.

### 11.1. Index ghép và leftmost prefix

Giả sử truy vấn lấy đơn hàng của một khách hàng theo thời gian mới nhất:

```sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Một index có thể phù hợp:

```sql
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at DESC, id DESC);
```

`customer_id` đứng đầu để lọc một khách hàng; các key part tiếp theo hỗ trợ thứ tự thời gian và ID trong nhóm đó. Khả năng dùng index còn tùy kế hoạch thực thi và cấu trúc dữ liệu thực tế.

### 11.2. ORDER BY biểu thức và vị trí NULL

Khi viết:

```sql
ORDER BY due_at IS NULL ASC, due_at ASC, id ASC
```

biểu thức `due_at IS NULL` có thể khiến MySQL cần bước sort riêng, ngay cả khi có index trên `due_at`. Hãy xác minh bằng `EXPLAIN`. Nếu mẫu truy vấn này quan trọng và dữ liệu lớn, có thể đánh giá generated column hoặc functional index phù hợp với phiên bản, nhưng chỉ sau khi đo hiệu năng và kiểm tra chi phí ghi.

Không dùng `COALESCE(due_at, '9999-12-31')` hoặc một sentinel tùy tiện nếu giá trị sentinel có thể xuất hiện hợp lệ, làm thay đổi ngữ nghĩa hoặc khiến optimizer không tận dụng được index như mong muốn. Biểu thức `IS NULL` thể hiện ý định rõ ràng hơn.

## 12. ORDER BY với UNION và truy vấn lồng nhau

Với `UNION`, `ORDER BY` ở cuối áp dụng cho tập kết quả hợp nhất:

```sql
SELECT id, name, created_at, 'customer' AS source_type
FROM customers
UNION ALL
SELECT id, name, created_at, 'supplier' AS source_type
FROM suppliers
ORDER BY created_at DESC, source_type ASC, id DESC;
```

Các nhánh `SELECT` cần trả về số cột tương thích. `ORDER BY` cuối cùng sắp xếp kết quả chung; không dựa vào thứ tự từng nhánh.

Với truy vấn lồng nhau, hãy đặt `ORDER BY` ở truy vấn ngoài cùng nếu ứng dụng cần thứ tự cuối cùng:

```sql
SELECT id, title, created_at
FROM (
    SELECT id, title, created_at
    FROM articles
    WHERE status = 'published'
) AS published_articles
ORDER BY created_at DESC, id DESC;
```

Thứ tự bên trong derived table không tự bảo đảm thứ tự của kết quả ngoài. Chỉ truy vấn ngoài cùng có `ORDER BY` mới xác định thứ tự hàng được trả về cho client.

## 13. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| Không ghi `ORDER BY` nhưng kết quả vẫn có vẻ đúng thứ tự | Thứ tự đó không được SQL bảo đảm | Viết `ORDER BY` rõ ràng |
| `ORDER BY created_at` luôn xác định thứ tự | Các hàng cùng thời điểm vẫn hòa nhau | Thêm khóa duy nhất như `id` |
| `ASC` đưa NULL xuống cuối | MySQL đưa NULL lên đầu khi ASC | Dùng `column IS NULL ASC` để đưa NULL xuống cuối |
| `DESC` đưa NULL lên đầu | MySQL đưa NULL xuống cuối khi DESC | Dùng `column IS NULL DESC` nếu muốn NULL lên đầu |
| `LIMIT` tự chọn các hàng mới nhất | LIMIT không có ý nghĩa thứ tự nếu thiếu ORDER BY | Kết hợp ORDER BY và khóa phân định |
| View hoặc truy vấn con đã ORDER BY nên bên ngoài không cần | Truy vấn ngoài không được bảo đảm thứ tự từ truy vấn trong | ORDER BY ở truy vấn ngoài cùng |
| `Using filesort` luôn nghĩa là sort ra đĩa | Có thể sort trong bộ nhớ hoặc dùng file tạm | Đánh giá kích thước sort và kế hoạch thực thi |
| Thêm index luôn làm ORDER BY nhanh hơn | Index tăng chi phí ghi và có thể không phù hợp thứ tự truy vấn | Đo bằng EXPLAIN/EXPLAIN ANALYZE |

## 14. Quy trình thiết kế ORDER BY đáng tin cậy

Khi viết truy vấn có sắp xếp, hãy kiểm tra lần lượt:

1. **Xác định thứ tự nghiệp vụ:** cột nào là tiêu chí chính, chiều tăng hay giảm?
2. **Quyết định vị trí NULL:** dùng mặc định của MySQL hay cần biểu thức `IS NULL`?
3. **Bổ sung tie-breaker:** thêm primary key hoặc tổ hợp unique để tạo thứ tự tổng thể.
4. **Kiểm tra collation và kiểu dữ liệu:** chuỗi có được so sánh theo quy tắc mong muốn không; ngày giờ có được lưu đúng kiểu không?
5. **Kết hợp LIMIT đúng cách:** luôn sắp xếp xác định trước khi cắt top-N hoặc phân trang.
6. **Chọn chiến lược pagination:** offset cho trang nhỏ; keyset khi tập dữ liệu lớn và thứ tự phù hợp.
7. **Đánh giá index:** xem điều kiện lọc, thứ tự key part và chiều sort.
8. **Đọc kế hoạch:** dùng `EXPLAIN`, đo thực tế và cân nhắc `Using filesort` trong bối cảnh tải.
9. **Kiểm thử dữ liệu biên:** NULL, giá trị trùng, chuỗi khác hoa/thường, thời điểm trùng và dữ liệu mới được thêm đồng thời.

## 15. Bài tập thực hành

1. Tạo bảng `tasks` có `due_at` nullable và chèn ít nhất hai hàng có `NULL`, hai hàng có cùng thời hạn và hai hàng có thời hạn khác nhau.
2. Chạy `ORDER BY due_at ASC` và `ORDER BY due_at DESC`; ghi nhận vị trí của `NULL`.
3. Viết truy vấn tăng dần nhưng đưa `NULL` xuống cuối bằng `due_at IS NULL`.
4. Viết truy vấn giảm dần nhưng đưa `NULL` lên đầu.
5. Tạo nhiều hàng có cùng `created_at`; chạy `ORDER BY created_at DESC LIMIT 3` và so sánh với truy vấn có thêm `id DESC`.
6. Tạo index ghép theo `customer_id`, `created_at`, `id`; dùng `EXPLAIN` kiểm tra truy vấn lấy đơn hàng mới nhất của một khách hàng.
7. So sánh offset pagination với keyset pagination trên một bảng có nhiều bản ghi.
8. Tạo một cột tên có collation không phân biệt hoa/thường; kiểm tra các giá trị có trọng số sắp xếp bằng nhau và bổ sung khóa phụ.
9. Dùng `UNION ALL` để kết hợp hai tập dữ liệu, sau đó sắp xếp ở cuối tập kết quả.

## 16. Ghi nhớ

`ORDER BY` là cách duy nhất để yêu cầu thứ tự hàng trong kết quả truy vấn. MySQL mặc định đặt `NULL` ở đầu khi `ASC` và cuối khi `DESC`; có thể điều khiển ngược lại bằng biểu thức `column IS NULL`. Khi nhiều hàng có cùng giá trị sắp xếp, thứ tự giữa chúng không được bảo đảm, vì vậy hãy thêm khóa duy nhất như primary key để tạo thứ tự xác định.

Kết hợp `ORDER BY` với `LIMIT` để lấy top-N hoặc phân trang; với dữ liệu lớn, cân nhắc keyset pagination. Index có thể hỗ trợ sắp xếp nếu thứ tự key part và truy vấn phù hợp, nhưng biểu thức, collation, NULL và chiều sort có thể yêu cầu bước sort bổ sung. Luôn xác định quy tắc nghiệp vụ, vị trí NULL, tie-breaker và kiểm tra kế hoạch thực thi trước khi đưa truy vấn vào production.
