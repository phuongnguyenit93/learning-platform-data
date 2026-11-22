# Ảnh hưởng của SELECT *, DISTINCT và sắp xếp không cần thiết

Trong **Database SQL**, hai câu truy vấn có thể trả về cùng dữ liệu về mặt nghiệp vụ nhưng tiêu thụ lượng tài nguyên rất khác nhau. Một trong những lý do thường gặp là truy vấn **đọc nhiều cột hơn cần thiết**, **loại trùng không có mục đích**, hoặc **yêu cầu sắp xếp dù người dùng không quan tâm thứ tự**.

Ba dấu hiệu dễ gặp trong code:

```sql
SELECT *
FROM orders;

SELECT DISTINCT customer_id, status, ordered_at, total_amount
FROM orders;

SELECT customer_id, total_amount
FROM orders
ORDER BY total_amount;
```

Không có câu nào tự động là “SQL sai”. Vấn đề là mỗi cấu trúc yêu cầu một công việc khác nhau từ DBMS:

- `SELECT *` có thể tăng **bề rộng dữ liệu đọc/trả về**, số trang phải đọc và số byte qua mạng; cũng có thể làm mất cơ hội truy vấn chỉ bằng index.
- `DISTINCT` đòi bảo đảm các hàng đầu ra là duy nhất theo **toàn bộ biểu thức được chọn**. Engine có thể cần hash, sort hoặc cơ chế loại trùng khác.
- `ORDER BY` đòi kết quả có thứ tự cụ thể. Nếu không tận dụng được thứ tự sẵn có từ index hay toán tử trước đó, engine có thể phải **Sort**, thậm chí sắp xếp bằng file tạm trên đĩa.

Bài học thuộc phần **Chỉ mục và kế hoạch**. Mục tiêu không phải là áp đặt quy tắc “cấm `*`, `DISTINCT` hay `ORDER BY`”, mà là biết **khi nào mỗi cấu trúc thật sự cần**, đọc kế hoạch thực thi, đánh giá chi phí và viết lại truy vấn **mà không đổi ý nghĩa kết quả**.

## 1. Trước hết, hãy xác định yêu cầu đầu ra

Trước khi tối ưu một truy vấn, cần trả lời ba câu hỏi:

1. **Những cột nào thật sự cần?** Màn hình danh sách có cần cột ghi chú dài, JSON payload và toàn bộ thông tin khách hàng không?
2. **Kết quả có cần loại bản ghi trùng không?** “Mỗi khách hàng một dòng” khác “mỗi đơn hàng một dòng”, và khác “tất cả dòng JOIN nhưng không có dòng giống nhau”.
3. **Người tiêu thụ dữ liệu có cần thứ tự không?** Nếu là trang “20 đơn mới nhất”, câu trả lời là có. Nếu chỉ cần tổng số lượng hay tập ID để xử lý tiếp, thứ tự có thể không cần.

Ví dụ một màn hình hiển thị “20 đơn PAID mới nhất” chỉ cần `order_id`, `ordered_at`, `total_amount`:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Đây là một yêu cầu rõ ràng: cột hẹp, có thứ tự, số dòng giới hạn. Không nên loại `ORDER BY` vì đó chính là **định nghĩa “mới nhất”**. Ngược lại, lấy toàn bộ hàng bằng `SELECT *` rồi chỉ dùng ba cột có thể gây thừa dữ liệu, đặc biệt trên bảng có trường văn bản lớn.

## 2. Bốn khái niệm phải phân biệt: lọc, chiếu, loại trùng, sắp xếp

Một câu truy vấn có nhiều loại công việc khác nhau:

| Công việc | Cú pháp quen thuộc | Câu hỏi trả lời | Ảnh hưởng tiềm năng |
| --- | --- | --- | --- |
| **Lọc hàng (selection)** | `WHERE` | Hàng nào được xem xét? | Giảm số dòng nếu điều kiện chọn lọc |
| **Chọn cột (projection)** | Danh sách cột sau `SELECT` | Cần những thuộc tính nào? | Ảnh hưởng kích thước hàng và cơ hội dùng covering index |
| **Loại trùng** | `DISTINCT` | Những tổ hợp giá trị nào chỉ được xuất hiện một lần? | Có thể dùng sort, hash, index hoặc bỏ qua nếu chứng minh đã duy nhất |
| **Sắp xếp** | `ORDER BY` | Dòng đầu ra theo thứ tự nào? | Có thể cần Sort/Top-N hoặc dùng thứ tự từ index |

Cần phân biệt **kết quả logic** và **cách engine thực thi**. Ví dụ:

```sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY customer_id;
```

về mặt logic yêu cầu **ID khách hàng không trùng và đã sắp xếp**. Engine có thể dùng một bước sort rồi loại trùng, dùng hash để loại trùng rồi sort, hoặc tận dụng một index có thứ tự. Không thể kết luận “có `DISTINCT` thì chắc chắn hai lần sort”.

## 3. SELECT * là gì, và tại sao đôi khi tốn kém?

`SELECT *` yêu cầu tất cả cột được biểu thức `FROM` công bố. Nếu một bảng có 30 cột, kết quả không tự biết rằng ứng dụng chỉ dùng ba cột.

```sql
-- Trả tất cả cột của orders.
SELECT *
FROM orders
WHERE customer_id = 42;
```

Trong khi:

```sql
-- Chỉ trả các cột màn hình thực sự cần.
SELECT order_id, ordered_at, total_amount
FROM orders
WHERE customer_id = 42;
```

có thể cho phép engine làm ít việc hơn ở nhiều tầng.

### 3.1. Số byte trả về

Một dòng kết quả gồm ba cột số/ngày thường nhỏ hơn một dòng gồm ba cột đó cộng thêm email, mô tả hàng nghìn ký tự hoặc nội dung JSON dài. Với 10.000 dòng, chênh lệch có thể trở thành hàng megabyte hoặc hơn trên mạng.

Ngoài băng thông, ứng dụng còn phải:

- Nhận dữ liệu từ driver/JDBC hoặc giao thức DBMS.
- Chuyển dữ liệu sang object/map/DTO.
- Cấp phát bộ nhớ, quản lý GC hoặc cache.
- Truyền tiếp dữ liệu qua API tới frontend nếu tầng ứng dụng không loại bỏ cột thừa.

Ngay cả khi database thực thi nhanh, tổng thời gian phản hồi vẫn có thể dài vì quá trình truyền và xử lý dữ liệu.

### 3.2. Bề rộng hàng ảnh hưởng thao tác trung gian

Nếu một phép sort phải giữ thêm nhiều cột đầu ra, khối dữ liệu trung gian **có thể** lớn hơn. Chẳng hạn:

```sql
SELECT *
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC;
```

so với:

```sql
SELECT order_id, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC;
```

Khi cần sort, engine có thể phải mang theo thông tin cần để xây dựng kết quả cuối. Tuy nhiên từng DBMS có kỹ thuật tối ưu khác nhau, chẳng hạn chỉ mang khóa/hàng tham chiếu ở một giai đoạn. **Không suy chi phí sort chỉ từ độ dài câu SELECT; hãy đọc kế hoạch và số byte thực tế.**

### 3.3. SELECT * có thể làm mất cơ hội index-only/covering scan

Giả sử index chứa `customer_id`, `ordered_at`, `order_id` và `total_amount`. Truy vấn chỉ cần các cột này có thể đọc phần lớn dữ liệu từ index mà không phải lấy đầy đủ mọi cột ở bảng. Thêm `note`, `payload` bằng `SELECT *` có thể buộc engine quay lại bảng chính để lấy phần thiếu.

Tùy DBMS, thao tác bổ sung có tên và chi phí khác nhau: **heap fetch**, **key lookup**, **table access by rowid**...

### 3.4. SELECT * còn là vấn đề giao diện

Khi schema phát triển, `SELECT *` có thể làm thay đổi tập cột mà ứng dụng, export CSV hoặc API nhận được. Việc bổ sung cột nhạy cảm vào bảng cũng có thể làm tăng rủi ro công bố dữ liệu ngoài mong muốn.

Ngoài ra, khi `JOIN` hai bảng có cùng tên cột, `SELECT *` có thể tạo các cột trùng tên:

```sql
SELECT *
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id;
```

Ứng dụng ánh xạ kết quả theo tên cột có thể khó phân biệt `customer_id` của mỗi bảng. Nên đặt danh sách cột và alias rõ ràng.

## 4. SELECT * không phải lúc nào cũng là lỗi hiệu năng

Các tình huống `SELECT *` có thể hợp lý:

- Truy vấn khám phá dữ liệu ngắn trong môi trường phát triển.
- Công cụ quản trị muốn hiển thị đầy đủ một bản ghi theo khóa chính.
- Bảng rất hẹp, tất cả cột đều được dùng.
- Truy vấn dùng một hàng duy nhất và khối lượng dữ liệu nhỏ.
- Một số cấu trúc bên trong như `EXISTS (SELECT 1 ...)`: danh sách SELECT bên trong `EXISTS` thường không được dùng như projection đầu ra.

Ví dụ:

```sql
SELECT *
FROM orders
WHERE order_id = 123;
```

Nếu thực sự cần toàn bộ đơn hàng, `SELECT *` có thể là yêu cầu đúng. Nhưng trong code ứng dụng lâu dài, danh sách cột tường minh vẫn giúp xác định hợp đồng dữ liệu tốt hơn.

**Không nên lấy `SELECT *` làm chỉ báo duy nhất về tốc độ.** Truy vấn chọn một cột nhưng trả 10 triệu dòng vẫn có thể chậm; truy vấn chọn cả hàng nhưng chỉ lấy một dòng theo khóa chính có thể rất nhanh.

## 5. DISTINCT thực sự so sánh những gì?

`DISTINCT` loại các dòng trùng nhau theo **toàn bộ danh sách biểu thức trong SELECT**, không phải theo một cột mà người viết “ngầm nghĩ”.

```sql
SELECT DISTINCT customer_id, status
FROM orders;
```

cho một dòng cho mỗi **cặp** `(customer_id, status)` khác nhau.

Nếu khách 42 có đơn PAID và PENDING, kết quả vẫn có hai dòng:

| customer_id | status |
| ---: | --- |
| 42 | PAID |
| 42 | PENDING |

Muốn danh sách khách hàng:

```sql
SELECT DISTINCT customer_id
FROM orders;
```

Nếu thêm `order_id`, một khóa định danh duy nhất mỗi đơn:

```sql
SELECT DISTINCT order_id, customer_id
FROM orders;
```

thì mỗi đơn vẫn là một dòng vì `order_id` vốn duy nhất. Lúc này `DISTINCT` **thừa về mặt logic** nếu dữ liệu không bị nhân từ `JOIN`. Tối ưu hóa có thể nhận biết ràng buộc UNIQUE/PRIMARY KEY và không cần bước loại trùng, nhưng không phải luôn luôn; đừng chủ động dựa vào việc DBMS sẽ tự sửa mọi truy vấn dư thừa.

### DISTINCT với NULL

Trong kết quả `SELECT DISTINCT col`, các giá trị `NULL` được xử lý như **một nhóm giá trị không phân biệt** để loại trùng: nhiều dòng có `NULL` ở cùng vị trí không tạo nhiều bản sao chỉ vì đều là `NULL`.

Điều này không đồng nghĩa với `NULL = NULL` trả TRUE trong điều kiện `WHERE`; SQL dùng logic ba giá trị khi so sánh thông thường.

### DISTINCT và quy tắc so sánh chuỗi

Collation/kiểu dữ liệu quyết định khi nào hai chuỗi được xem là tương đương trong phép so sánh. Tùy DBMS, collation phân biệt hoặc không phân biệt hoa/thường, dấu, khoảng trắng... có thể ảnh hưởng số nhóm `DISTINCT`. Do đó không mặc định mọi hệ sẽ coi `'abc'` và `'ABC'` là khác nhau.

## 6. DISTINCT có thể cần nhiều bộ nhớ và CPU ở đâu?

Để bảo đảm không có dòng trùng, DBMS phải biết các giá trị đã xuất hiện hoặc xử lý dữ liệu theo nhóm.

### 6.1. Hash-based duplicate elimination

Một dạng kế hoạch có thể dùng **HashAggregate** hoặc toán tử hash distinct. Engine xây cấu trúc hash để ghi nhận các tổ hợp giá trị khác nhau.

Phù hợp khi:

- Có nhiều hàng đầu vào.
- Số khóa phân biệt vừa phải.
- Có đủ bộ nhớ và thao tác hash hợp lý.

Rủi ro: khi dữ liệu lớn hoặc số lượng tổ hợp khác nhau cao, hash table có thể chiếm nhiều bộ nhớ hoặc phải chia batch/ghi dữ liệu tạm tùy DBMS.

### 6.2. Sort-based duplicate elimination

Một dạng kế hoạch khác có thể:

1. Sắp xếp dữ liệu theo các cột của `DISTINCT`.
2. Đọc dãy đã sắp xếp và bỏ các hàng giống hàng liền trước.

Trong PostgreSQL có thể thấy toán tử **Sort** kết hợp **Unique**, hoặc kế hoạch dùng index có thứ tự.

Rủi ro: sort lớn có thể vượt bộ nhớ cấp phát và chuyển sang **external merge / disk sort**.

### 6.3. Tận dụng index hoặc tính duy nhất đã biết

Nếu index đã lưu các khóa theo thứ tự phù hợp, hoặc optimizer chứng minh đầu ra vốn duy nhất, thao tác loại trùng có thể ít tốn kém hơn hoặc biến mất.

**Kết luận đúng:** `DISTINCT` tạo **một ràng buộc ngữ nghĩa** và có **chi phí tiềm năng**. Không có quy tắc “DISTINCT luôn thực hiện full sort”, cũng không có quy tắc “DISTINCT luôn chậm”.

## 7. DISTINCT và GROUP BY: giống, khác ở đâu?

Hai câu:

```sql
SELECT DISTINCT customer_id
FROM orders;
```

và:

```sql
SELECT customer_id
FROM orders
GROUP BY customer_id;
```

thường trả cùng tập customer ID, nếu không kèm phép tổng hợp khác.

Nhưng:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id;
```

vừa **nhóm**, vừa tính chỉ tiêu theo nhóm. `DISTINCT` đơn thuần không thay thế biểu thức aggregate.

Về hiệu năng, `DISTINCT` và `GROUP BY` đôi khi được optimizer chuyển về kế hoạch tương tự. Không nên thay `DISTINCT` bằng `GROUP BY` chỉ vì tin rằng cái này luôn nhanh hơn.

**Chú ý thứ tự:** `GROUP BY` **không bảo đảm** trả các nhóm theo thứ tự khóa nhóm. Nếu kết quả cần sắp xếp, phải có `ORDER BY` ở truy vấn cuối, dù một kế hoạch hiện tại tình cờ trả ra có thứ tự.

## 8. DISTINCT không nên là cách vá JOIN nhân dòng

Một nguồn `DISTINCT` thừa rất phổ biến là câu `JOIN` một-nhiều.

Ví dụ một đơn có hai tag:

```text
orders                  order_tags
order_id | customer_id   order_id | tag
      10 |         42          10 | sale
                                10 | email
```

Khi JOIN:

```sql
SELECT o.order_id, o.customer_id
FROM orders AS o
JOIN order_tags AS t
  ON t.order_id = o.order_id;
```

đơn 10 xuất hiện **hai lần**. Nhiều người “sửa” bằng:

```sql
SELECT DISTINCT o.order_id, o.customer_id
FROM orders AS o
JOIN order_tags AS t
  ON t.order_id = o.order_id;
```

Cách này có thể đưa kết quả về đúng tập đơn, nhưng phải đọc các dòng đã bị nhân rồi mới loại trùng. Quan trọng hơn, nó **che giấu cấu trúc quan hệ**: thực ra yêu cầu nghiệp vụ có thể chỉ là “đơn nào có ít nhất một tag”.

Khi chỉ cần kiểm tra tồn tại, viết:

```sql
SELECT o.order_id, o.customer_id
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM order_tags AS t
    WHERE t.order_id = o.order_id
);
```

`EXISTS` không tạo một dòng kết quả cho mỗi tag. Tùy DBMS, optimizer có thể dùng **semi join**, giúp tránh sinh ra những bản sao không cần thiết.

Nhưng **không thay mọi JOIN + DISTINCT bằng EXISTS một cách máy móc**. Nếu cần đưa cột `tag` ra đầu ra, hoặc đếm số tag, hoặc giữ quan hệ chi tiết từng tag, `EXISTS` không đủ; phải định nghĩa đúng phép tổng hợp hoặc dạng kết quả.

## 9. ORDER BY yêu cầu điều gì?

`ORDER BY` yêu cầu sắp xếp theo biểu thức và chiều sắp xếp.

```sql
SELECT order_id, ordered_at, total_amount
FROM orders
ORDER BY ordered_at DESC, order_id DESC;
```

Câu trên yêu cầu đơn mới hơn xuất hiện trước; khi hai đơn có cùng `ordered_at`, `order_id` lớn hơn đứng trước.

**Nếu không có ORDER BY ở truy vấn ngoài cùng**, SQL không cam kết thứ tự các hàng, kể cả khi:

- Bảng có primary key.
- Kế hoạch dùng index scan.
- Lần chạy thử hiện tại ra đúng thứ tự.
- `GROUP BY` hay `DISTINCT` vô tình dùng sort.
- View hoặc subquery từng có `ORDER BY`.

Vì thế, bỏ `ORDER BY` chỉ khi thứ tự **không phải yêu cầu**. Không bỏ ORDER BY ở API phân trang, bảng xếp hạng, top-N, timeline hoặc báo cáo cần thứ tự ổn định.

## 10. ORDER BY tốn chi phí thế nào?

Nếu engine không nhận được dữ liệu theo thứ tự yêu cầu từ một đường truy cập/plan phù hợp, nó có thể cần toán tử **Sort**.

Giả sử bảng có một triệu đơn. Câu:

```sql
SELECT order_id, ordered_at, total_amount
FROM orders
ORDER BY total_amount DESC;
```

có thể cần:

1. Đọc các hàng.
2. So sánh khóa `total_amount`.
3. Sắp xếp tập kết quả.
4. Gửi hàng đã sắp xếp.

Nếu không có điều kiện giới hạn số dòng, đây có thể là thao tác đắt hơn scan không cần thứ tự. Độ phức tạp thường được mô tả gần với `O(N log N)` cho sort tổng quát, dù thuật toán cụ thể và chi phí thực tế thay đổi.

Nếu dữ liệu không đủ bộ nhớ cho sort, DBMS có thể ghi tạm xuống đĩa. Khi đó cần quan sát:

- Bộ nhớ được cấp/sử dụng.
- Lượng dữ liệu tạm.
- Loại sort trong execution plan.
- Số hàng và bề rộng hàng.
- Mức độ song song.
- Khả năng dùng index để giảm hoặc tránh sort.

**Đừng mặc định có `ORDER BY` là luôn có node Sort.** Nếu index và bộ lọc đã tạo đúng thứ tự, engine có thể phát hàng theo thứ tự index.

## 11. Index có thể giúp ORDER BY ra sao?

B-tree index lưu khóa theo thứ tự. Một index phù hợp có thể hỗ trợ cả **lọc** và **trả kết quả đã có thứ tự**.

Ví dụ:

```sql
CREATE INDEX idx_orders_status_time
ON orders (status, ordered_at DESC, order_id DESC);
```

Truy vấn:

```sql
SELECT order_id, ordered_at, total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

có thể tận dụng index theo ba bước:

1. Tìm đoạn index có `status = 'PAID'`.
2. Đọc theo `ordered_at DESC, order_id DESC` sẵn có.
3. Dừng sau khi tìm đủ 20 hàng phù hợp.

Như vậy engine có cơ hội tránh sort toàn bộ hàng PAID. Đây là ví dụ index hỗ trợ rất tốt câu hỏi “20 đơn mới nhất”.

Tuy nhiên:

- Nếu `status` có chọn lọc thấp và cần phần lớn bảng, một scan khác cộng sort vẫn có thể rẻ hơn.
- Nếu cần cột không nằm trong index, phải đọc thêm bảng gốc; chi phí random I/O có thể làm thay đổi kế hoạch.
- Nếu `ORDER BY total_amount DESC` thay vì `ordered_at DESC`, index trên không còn cho thứ tự đúng.
- Nếu đổi chiều của một số khóa hoặc dùng biểu thức/hàm, phải kiểm tra khả năng dùng thứ tự index theo DBMS.
- Với query có `LIMIT` nhỏ, index thường hấp dẫn hơn, nhưng lựa chọn cuối cùng vẫn do optimizer.

**Chỉ mục “có cột xuất hiện trong ORDER BY” chưa chắc đủ.** Thứ tự các cột trong composite index, điều kiện equality/range, chiều sort và khóa phụ đều quan trọng.

## 12. LIMIT không thay thế ORDER BY

```sql
SELECT order_id, ordered_at
FROM orders
LIMIT 20;
```

chỉ yêu cầu **20 hàng bất kỳ mà kế hoạch trả ra trước**; không có nghĩa là “20 đơn mới nhất”. Một thay đổi index, thống kê hoặc execution plan có thể thay đổi tập hàng được chọn.

Nếu cần mới nhất:

```sql
SELECT order_id, ordered_at
FROM orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Với `LIMIT` và `ORDER BY`, engine có thể dùng **Top-N sort** (chỉ duy trì các ứng viên tốt nhất) thay vì sort đầy đủ. Trong PostgreSQL có thể thấy `top-N heapsort` ở thuộc tính `Sort Method`; ở DBMS khác có dạng `Top`/`Top N Sort`.

Không phải lúc nào cũng bỏ được sort bằng cách thêm `LIMIT`. Nếu không có đường index phù hợp, engine vẫn cần xét đủ các hàng có thể nằm trong top N trước khi kết luận kết quả.

## 13. ORDER BY không cần thiết thường xuất hiện ở đâu?

### 13.1. Truy vấn dùng để kiểm tra tồn tại

Nếu chỉ cần biết một khách có đơn PAID hay không:

```sql
-- Dư thứ tự nếu mục tiêu chỉ là tồn tại.
SELECT order_id
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY ordered_at DESC;
```

Dùng:

```sql
SELECT EXISTS (
    SELECT 1
    FROM orders
    WHERE customer_id = 42
      AND status = 'PAID'
) AS has_paid_order;
```

Đây là một câu hỏi khác: chỉ trả TRUE/FALSE, không cần danh sách hay thứ tự. DBMS có thể dừng khi tìm được dòng phù hợp.

### 13.2. Truy vấn tổng hợp mà thứ tự không cần

```sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status
ORDER BY status;
```

Nếu đưa số liệu sang một hệ thống tự sắp xếp riêng, có thể bỏ `ORDER BY status`. Nhưng nếu báo cáo hiển thị theo thứ tự trạng thái cố định, giữ ORDER BY là hợp lý.

### 13.3. ORDER BY trong subquery nhưng ngoài không cần

```sql
-- Không nên dựa vào thứ tự bên trong để cam kết thứ tự cuối.
SELECT customer_id
FROM (
    SELECT customer_id
    FROM orders
    ORDER BY ordered_at DESC
) AS x;
```

Nếu không có thành phần tiêu thụ thứ tự này, nên bỏ sort trong subquery:

```sql
SELECT customer_id
FROM orders;
```

Một số optimizer có thể loại `ORDER BY` vô ích; một số trường hợp có thể giữ hoặc bị ràng buộc cú pháp khác. Vì vậy xóa một thứ tự **không có giá trị ngữ nghĩa** giúp truy vấn diễn đạt ý định rõ hơn, nhưng tốc độ phải đo thay vì suy diễn.

### 13.4. ORDER BY chỉ để “cho kết quả trông đẹp” trong API nội bộ

Nếu API nhận một tập khóa mà tầng sau dùng như một set và **không hiển thị hay phân trang**, việc sắp xếp hàng triệu khóa có thể là lãng phí.

Ngược lại, nếu API hứa trả dữ liệu đã sắp xếp cho người tiêu dùng, `ORDER BY` là **một phần hợp đồng** và không được bỏ tùy tiện.

## 14. Những ORDER BY thực sự có ý nghĩa ngữ nghĩa

Không được bỏ các thứ tự sau chỉ vì nhìn thấy từ khóa `ORDER BY`.

### 14.1. Top-N theo một tiêu chí

```sql
SELECT order_id, total_amount
FROM orders
ORDER BY total_amount DESC, order_id DESC
LIMIT 10;
```

Bỏ sort làm mất ý nghĩa “10 đơn có giá trị lớn nhất”.

### 14.2. Window functions

```sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    ) AS rn
FROM orders;
```

`ORDER BY` bên trong `OVER (...)` định nghĩa thứ tự để đánh số trong từng nhóm khách hàng; bỏ nó thay đổi ý nghĩa `ROW_NUMBER`. Tuy nhiên **thứ tự các dòng trả ra cuối cùng** vẫn cần một `ORDER BY` ở ngoài nếu ứng dụng cần.

### 14.3. Ordered aggregates

PostgreSQL hỗ trợ thứ tự bên trong aggregate:

```sql
SELECT
    customer_id,
    ARRAY_AGG(order_id ORDER BY ordered_at DESC, order_id DESC)
        AS order_ids_newest_first
FROM orders
GROUP BY customer_id;
```

Thứ tự này xác định phần tử trong mảng; nó không chỉ trang trí kết quả. Ở DBMS khác, cú pháp cho hàm kết hợp chuỗi/mảng có thể khác.

### 14.4. Chọn một hàng cụ thể bằng subquery ORDER BY LIMIT

```sql
SELECT order_id, ordered_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 1;
```

Thứ tự và giới hạn ở đây chọn đơn mới nhất của khách 42; bỏ sort có thể chọn đơn bất kỳ.

**Phân biệt thứ tự “để xác định tập kết quả” và thứ tự “chỉ để trình bày”.** Cái thứ nhất có ảnh hưởng nghiệp vụ trực tiếp.

## 15. Thứ tự ổn định: ORDER BY cột không duy nhất là chưa đủ

Giả sử nhiều đơn có cùng thời điểm `ordered_at`. Truy vấn:

```sql
SELECT order_id, ordered_at
FROM orders
ORDER BY ordered_at DESC
LIMIT 20;
```

không xác định thứ tự tương đối của các đơn có cùng `ordered_at`. Nếu hai lần phân trang chạy ở thời điểm khác nhau hoặc có plan khác nhau, phần tử ranh giới trang có thể không ổn định.

Nên dùng khóa phụ duy nhất:

```sql
SELECT order_id, ordered_at
FROM orders
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

`order_id` ở đây là khóa duy nhất nên tạo thứ tự xác định giữa các hàng có cùng ngày giờ.

Điểm này quan trọng với:

- Phân trang bằng `LIMIT/OFFSET`.
- Keyset/cursor pagination.
- Top-N, chọn bản ghi mới nhất mỗi nhóm.
- Các API cần thứ tự ổn định.

**Ngay cả thứ tự xác định cũng không bảo đảm phân trang OFFSET không bị trôi khi dữ liệu được thêm/sửa/xóa giữa các request.** Đó là vấn đề về snapshot và biến động dữ liệu; pagination kiểu keyset thường giúp giảm một phần rủi ro khi dùng đúng.

## 16. DISTINCT kết hợp ORDER BY: hiểu thứ tự thao tác

Ví dụ:

```sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY customer_id;
```

Engine phải trả các customer ID duy nhất theo thứ tự tăng dần. Nhưng nếu muốn:

> “Danh sách khách hàng, sắp xếp theo lần đặt hàng gần đây nhất”

thì câu:

```sql
-- PostgreSQL: không hợp lệ vì ordered_at không nằm trong SELECT DISTINCT.
SELECT DISTINCT customer_id
FROM orders
ORDER BY ordered_at DESC;
```

không diễn đạt đúng yêu cầu. Một khách có nhiều `ordered_at`; không rõ lấy thời điểm nào để xếp hạng khách.

Cách đúng là xác định **mốc thời gian cho từng khách**:

```sql
SELECT
    customer_id,
    MAX(ordered_at) AS last_ordered_at
FROM orders
GROUP BY customer_id
ORDER BY last_ordered_at DESC, customer_id;
```

Ở đây mỗi khách được gắn một `last_ordered_at` rõ ràng, rồi sắp xếp theo mốc đó. Đây là thay đổi **thiết kế truy vấn theo ý nghĩa nghiệp vụ**, không chỉ là mẹo tăng tốc.

Tùy DBMS, quy tắc `ORDER BY` khi dùng `DISTINCT` có khác biệt cú pháp; trong PostgreSQL, các biểu thức ORDER BY trong câu `SELECT DISTINCT` cần xuất hiện trong danh sách SELECT.

## 17. Bộ dữ liệu thực hành PostgreSQL

Các phần tiếp theo dùng **PostgreSQL**. Lệnh chạy trong một database thử nghiệm, không cần truy cập bảng thật. Bộ dữ liệu đủ để quan sát sự khác nhau của projection, index, DISTINCT và sort, nhưng **thời gian chạy và kế hoạch là kết quả phụ thuộc môi trường**, không có output plan cố định.

### 17.1. Tạo schema và bảng

```sql
CREATE SCHEMA sql330;

CREATE TABLE sql330.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    ordered_at TIMESTAMP NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL,
    note TEXT,
    payload TEXT
);
```

`payload` đại diện cho cột văn bản lớn mà màn hình danh sách **không cần hiển thị**, còn `note` đại diện cho dữ liệu không phải lúc nào cũng có.

### 17.2. Tạo 50.000 đơn giả

```sql
INSERT INTO sql330.orders
    (customer_id, status, ordered_at, total_amount, note, payload)
SELECT
    1 + (g % 1000) AS customer_id,
    CASE
        WHEN g % 10 < 7 THEN 'PAID'
        WHEN g % 10 < 9 THEN 'PENDING'
        ELSE 'CANCELLED'
    END AS status,
    TIMESTAMP '2026-01-01 00:00:00'
        + g * INTERVAL '1 minute' AS ordered_at,
    (10 + (g % 300))::NUMERIC(12,2) AS total_amount,
    CASE WHEN g % 5 = 0
         THEN 'Ghi chú thử nghiệm'
         ELSE NULL
    END AS note,
    REPEAT('payload-', 40) AS payload
FROM GENERATE_SERIES(1, 50000) AS gs(g);
```

Kết quả kỳ vọng:

- **50.000** hàng, `order_id` là khóa chính.
- **1.000** khách hàng khác nhau.
- `status` có `PAID`, `PENDING` và `CANCELLED`.
- `ordered_at` trải qua nhiều ngày kể từ đầu năm 2026.
- `payload` chứa chuỗi dài để dễ thấy ảnh hưởng bề rộng cột.

Nếu máy học có tài nguyên hạn chế, có thể hạ `GENERATE_SERIES(1, 50000)` xuống `(1, 5000)`; các chỉ số số lượng và khả năng thấy Sort spill sẽ khác.

### 17.3. Tạo bảng tag để mô phỏng JOIN một-nhiều

```sql
CREATE TABLE sql330.order_tags (
    order_id BIGINT NOT NULL
        REFERENCES sql330.orders(order_id),
    tag TEXT NOT NULL,
    PRIMARY KEY (order_id, tag)
);

INSERT INTO sql330.order_tags (order_id, tag)
SELECT o.order_id, x.tag
FROM sql330.orders AS o
CROSS JOIN (
    VALUES ('sale'), ('email')
) AS x(tag)
WHERE o.order_id <= 1000;
```

Mỗi đơn từ 1 đến 1.000 được gắn **hai tag**. Vì vậy JOIN với `order_tags` cho mỗi đơn này thành hai dòng.

### 17.4. Tạo index phục vụ lọc và thứ tự

```sql
CREATE INDEX sql330_idx_status_time
ON sql330.orders (
    status,
    ordered_at DESC,
    order_id DESC
);

CREATE INDEX sql330_idx_customer_time
ON sql330.orders (
    customer_id,
    ordered_at DESC,
    order_id DESC
);

CREATE INDEX sql330_idx_customer_cover
ON sql330.orders (
    customer_id
)
INCLUDE (ordered_at, total_amount);
```

Index thứ ba dùng cú pháp `INCLUDE` của PostgreSQL để chứa thêm các cột có thể được trả về mà không cần chúng tham gia thứ tự khóa index. Không suy rằng index này có thể hỗ trợ mọi `ORDER BY ordered_at`: các cột trong `INCLUDE` **không tạo thứ tự tìm kiếm như key columns**.

### 17.5. Cập nhật thống kê

```sql
ANALYZE sql330.orders;
ANALYZE sql330.order_tags;
```

`ANALYZE` cung cấp thống kê cho optimizer. Không thể so sánh kế hoạch một cách có ý nghĩa nếu bảng vừa nạp dữ liệu nhưng thống kê bị thiếu/cũ trên môi trường quan sát.

## 18. Cách đọc EXPLAIN để nhận diện chi phí thừa

Trên PostgreSQL, dùng:

```sql
EXPLAIN
SELECT
    order_id, customer_id, ordered_at
FROM sql330.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

`EXPLAIN` hiển thị kế hoạch dự kiến mà **không chạy SELECT để trả dữ liệu**. Khi cần đo thật:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id, customer_id, ordered_at
FROM sql330.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Với `SELECT` ở lab, `ANALYZE` thực thi truy vấn để đo thời gian; `BUFFERS` hiển thị hoạt động bộ đệm. **Không dùng `EXPLAIN ANALYZE` tùy tiện trên UPDATE/DELETE/INSERT sản xuất**, vì những lệnh đó có thể thật sự thay đổi dữ liệu.

### Các node/thuộc tính thường gặp

| Tên trong kế hoạch PostgreSQL | Cách đọc |
| --- | --- |
| `Seq Scan` | Đọc bảng theo thứ tự vật lý, thường phù hợp nếu cần nhiều hàng |
| `Index Scan` | Truy cập qua index rồi có thể về bảng lấy cột khác |
| `Index Only Scan` | Có cơ hội trả giá trị từ index; vẫn có thể có `Heap Fetches` vì kiểm tra MVCC |
| `Bitmap Heap Scan` | Dùng bitmap để xác định vị trí hàng, rồi truy cập các trang bảng |
| `Sort` | Thực hiện sắp xếp theo `Sort Key` |
| `Unique` | Loại trùng trên dữ liệu được cấp theo cách phù hợp |
| `HashAggregate` | Có thể dùng hash để nhóm/loại trùng |
| `GroupAggregate` | Tổng hợp từ đầu vào theo nhóm, thường dựa vào thứ tự phù hợp |
| `Limit` | Giới hạn số dòng kết quả cuối |
| `Nested Loop`, `Hash Join`, `Merge Join` | Các chiến lược JOIN với đặc điểm khác nhau |

Ngoài tên node, xem:

- **`actual rows`**: thực tế bao nhiêu dòng đi qua?
- **`rows` ước tính**: khác số thực tế lớn không?
- **`width`**: ước tính bề rộng hàng ở node.
- **`Sort Method`** và `Memory`/`Disk` nếu có.
- **`Heap Fetches`** của Index Only Scan.
- **`Buffers: shared hit/read`**, temp read/written tùy plan.
- **Execution Time** và số lần lặp `loops`.

Một node Sort không tự chứng minh truy vấn kém; cần xét **tổng chi phí, số dòng, bề rộng, tài nguyên và yêu cầu kết quả**.

## 19. Thử nghiệm 1: SELECT * so với danh sách cột

Đo hai câu trên cùng bộ lọc:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM sql330.orders
WHERE customer_id = 42;
```

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at, total_amount
FROM sql330.orders
WHERE customer_id = 42;
```

Quan sát:

1. Giá trị **`width`** ước tính của các node có khác không?
2. Plan có chọn `Index Scan`, `Bitmap Heap Scan` hay `Seq Scan`?
3. Số hàng trả có bằng nhau không? Nếu query không thêm giới hạn, cả hai đều lấy mọi đơn thuộc khách 42.
4. Có phát sinh `Heap Fetches` nếu dùng `Index Only Scan` không?
5. Thời gian máy client nhận toàn bộ kết quả (ngoài EXPLAIN) có khác khi cột `payload` được truyền qua mạng không?

Cột `payload` nhiều byte có thể làm `SELECT *` nặng hơn, nhưng optimizer vẫn có thể chọn cùng đường scan cho cả hai câu. Trong PostgreSQL, index-only scan **không bảo đảm không đụng heap**: kiểm tra khả năng hiển thị hàng của MVCC phụ thuộc trạng thái visibility map.

Để quan sát sự khác biệt, có thể thử thêm:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, ordered_at, total_amount
FROM sql330.orders
WHERE customer_id = 42;
```

Vì ba cột này có trong index `sql330_idx_customer_cover`, truy vấn có **cơ hội** dùng index-only scan, tùy ước tính chi phí và trạng thái MVCC. Không nên kỳ vọng mọi lần chạy đều cho cùng plan.

**Chú ý:** `EXPLAIN ANALYZE` tập trung vào công việc ở DBMS; nó không đo đầy đủ chi phí truyền tất cả hàng về ứng dụng như một API thật. Khi so sánh dữ liệu trả lớn, cần benchmark ở cả database và phía client.

## 20. Thử nghiệm 2: DISTINCT và dữ liệu đã duy nhất

Truy vấn A:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT customer_id
FROM sql330.orders;
```

Truy vấn B:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT order_id
FROM sql330.orders;
```

Truy vấn C:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM sql330.orders;
```

Ý nghĩa:

- A cần trả 1.000 customer ID khác nhau từ 50.000 đơn; engine cần bảo đảm loại trùng.
- B chỉ chọn `order_id`, cột đã có ràng buộc `PRIMARY KEY`, nên tập đầu ra vốn duy nhất.
- C không yêu cầu DISTINCT; với cùng `order_id`, tập giá trị logic bằng B.

So sánh **plan B và C** để xem optimizer có tận dụng thông tin tính duy nhất hay không. Không khẳng định chắc B luôn chạy y hệt C: nó tùy khả năng suy luận của optimizer và kế hoạch được chọn.

Kiểm tra số dòng:

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(DISTINCT customer_id) AS unique_customers,
    COUNT(DISTINCT order_id) AS unique_orders
FROM sql330.orders;
```

Kỳ vọng `all_orders = 50000`, `unique_customers = 1000`, `unique_orders = 50000`.

## 21. Thử nghiệm 3: DISTINCT để sửa JOIN hay EXISTS?

### 21.1. JOIN + DISTINCT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT
    o.order_id,
    o.customer_id
FROM sql330.orders AS o
JOIN sql330.order_tags AS t
  ON t.order_id = o.order_id
WHERE t.tag IN ('sale', 'email');
```

### 21.2. EXISTS

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.customer_id
FROM sql330.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM sql330.order_tags AS t
    WHERE t.order_id = o.order_id
      AND t.tag IN ('sale', 'email')
);
```

Cả hai mong đợi có **1.000 đơn** (ID 1–1.000), mỗi đơn một lần.

`EXISTS` biểu đạt ý nghĩa “có ít nhất một tag hợp lệ”. Nó không buộc engine phải tạo tập kết quả với hai dòng rồi loại trùng như cách viết JOIN + DISTINCT về mặt logic. Tuy nhiên optimizer có thể tự biến đổi nhiều truy vấn; kết quả hiệu năng thực tế vẫn cần đo.

Nếu yêu cầu “mỗi tag của một đơn là một dòng”, **không** dùng EXISTS thay JOIN. Việc tối ưu phải giữ nguyên ý nghĩa dữ liệu.

## 22. Thử nghiệm 4: ORDER BY có index và ORDER BY khác khóa index

**A.** Sắp theo thời gian khi đã lọc status:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id, ordered_at, total_amount
FROM sql330.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Index `sql330_idx_status_time` phù hợp với `status = 'PAID'` và thứ tự yêu cầu.

**B.** Sắp theo số tiền:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id, ordered_at, total_amount
FROM sql330.orders
WHERE status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 20;
```

Các index đã tạo **không** có thứ tự phù hợp với `total_amount DESC, order_id DESC` cho tập PAID. Engine có thể cần Sort/Top-N sort. Nhưng nó vẫn có lựa chọn scan và các phép tối ưu khác; không cố định tên node.

**C.** Bỏ thứ tự khi thật sự không cần:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id, ordered_at, total_amount
FROM sql330.orders
WHERE status = 'PAID'
LIMIT 20;
```

C có thể rẻ hơn, nhưng **không thay thế được A hoặc B** nếu yêu cầu là “20 đơn mới nhất” hoặc “20 đơn giá trị cao nhất”. C chỉ là “20 đơn bất kỳ”.

### Cách ghi kết quả đo

| Thử nghiệm | Số dòng trả | Có Sort? | Scan loại gì? | Execution Time | Ghi chú |
| --- | ---: | --- | --- | --- | --- |
| A — thời gian + LIMIT | Điền khi chạy | Điền | Điền | Điền | Thứ tự khớp index |
| B — tiền + LIMIT | Điền khi chạy | Điền | Điền | Điền | Thứ tự không khớp index đã tạo |
| C — LIMIT không sort | Điền khi chạy | Điền | Điền | Điền | Ngữ nghĩa khác A/B |

Không điền con số giả định làm “kết quả EXPLAIN chuẩn”. Mục đích thực hành là đọc **kế hoạch có thật ở máy bạn**.

## 23. Khi sort spill ra đĩa, điều chỉnh thế nào?

Với bộ dữ liệu lớn, một Sort không dùng index có thể phải lưu trung gian nhiều hơn bộ nhớ cho phép. PostgreSQL có thể hiển thị trong `EXPLAIN ANALYZE` dạng:

```text
Sort
  Sort Key: total_amount DESC
  Sort Method: external merge  Disk: ...
```

Đây chỉ là **mẫu tên node/thuộc tính**, không phải output đo của bài lab.

Các hướng xử lý, theo thứ tự suy nghĩ:

1. **Có thực sự cần thứ tự này không?** Nếu không, bỏ `ORDER BY`.
2. **Có thể lọc sớm không?** Thu hẹp `WHERE` theo thời gian, trạng thái, tenant trước khi sort.
3. **Có thể lấy top-N thay vì tất cả?** Nếu nghiệp vụ chỉ cần 20 dòng, dùng `ORDER BY ... LIMIT 20`.
4. **Có index phù hợp không?** Xem điều kiện lọc, cột sort, thứ tự, chiều và khóa phụ.
5. **Có thể giảm bề rộng kết quả/trung gian không?** Chỉ chọn cột cần dùng.
6. **Có thể tối ưu JOIN/aggregation trước không?** Tránh nhân dữ liệu làm sort nhiều dòng hơn.
7. **Có thiếu thống kê không?** Chạy `ANALYZE` nếu cần và được phép.
8. **Có thực sự thiếu bộ nhớ cho Sort hợp lý không?** Chỉ cân nhắc điều chỉnh cấu hình sau khi đo chi phí và mức đồng thời.

### Về work_mem trong PostgreSQL

`work_mem` ảnh hưởng bộ nhớ cho các thao tác như Sort và một số hash operation, nhưng không nên tăng toàn hệ thống chỉ để một query hết spill. Nhiều thao tác trong cùng truy vấn và nhiều session chạy đồng thời có thể dùng bộ nhớ riêng, gây áp lực tổng thể.

Ví dụ trong session thử nghiệm:

```sql
SHOW work_mem;
```

Không đưa một giá trị `work_mem` “phù hợp cho mọi hệ thống”; cần đo, hiểu workload và kiểm soát concurrency. Trong nhiều trường hợp, giảm dữ liệu thừa hoặc thiết kế index đúng hiệu quả và an toàn hơn tăng bộ nhớ.

## 24. Index-only scan và covering index: giới hạn cần nhớ

Trong PostgreSQL, một truy vấn có cơ hội `Index Only Scan` nếu:

- Kiểu index hỗ trợ đáp ứng cột truy vấn theo yêu cầu.
- Các cột cần trả/lọc có thể lấy từ index tương ứng.
- Optimizer đánh giá đường đi đó có lợi.
- Điều kiện MVCC/visibility map cho phép ít phải truy cập heap để kiểm tra khả năng nhìn thấy tuple.

Ví dụ:

```sql
CREATE INDEX sql330_idx_customer_cover
ON sql330.orders (customer_id)
INCLUDE (ordered_at, total_amount);
```

(Đã tạo tại mục 17; không chạy lại lệnh tạo nếu index tồn tại.)

Truy vấn phù hợp:

```sql
SELECT customer_id, ordered_at, total_amount
FROM sql330.orders
WHERE customer_id = 42;
```

Truy vấn dễ mất lợi thế:

```sql
SELECT *
FROM sql330.orders
WHERE customer_id = 42;
```

vì `*` còn cần `status`, `note`, `payload`, `order_id` và các cột khác ngoài index chứa dữ liệu bổ sung đó. Đừng lập index có `INCLUDE` mọi cột chỉ để hỗ trợ `SELECT *`; index rộng làm tốn dung lượng, tăng chi phí ghi, vacuum và bộ nhớ cache, có thể lợi bất cập hại.

### Các DBMS gọi cơ chế này thế nào?

- **PostgreSQL:** `Index Only Scan` và `Heap Fetches`, phụ thuộc khả năng hiển thị MVCC.
- **SQL Server:** covering nonclustered index, `INCLUDE`, đôi khi `Key Lookup` để lấy cột thiếu.
- **MySQL/InnoDB:** secondary index chứa các khóa index và khóa chính cần thiết; “covering index” phụ thuộc cột truy vấn, không giống trực tiếp MVCC/INCLUDE của PostgreSQL.
- **SQLite:** covering index có thể tránh phải tra bảng khi cột được yêu cầu nằm trong index.
- **Oracle:** có các biến thể truy cập index/table phù hợp, bao gồm truy cập bảng theo ROWID nếu cần cột chưa có.

**Cùng một ý tưởng “truy vấn hẹp dễ được index bao phủ” nhưng đường thực thi và tên node khác nhau theo DBMS.**

## 25. DISTINCT ON và ROW_NUMBER: “mỗi nhóm một hàng” là bài toán khác

Một mục tiêu phổ biến:

> “Mỗi khách chỉ lấy **đơn PAID mới nhất**, kèm `order_id` và `total_amount` của chính đơn đó.”

Không thể giải quyết đúng chỉ bằng:

```sql
-- Không thể xác định "đơn mới nhất" bằng DISTINCT đơn thuần.
SELECT DISTINCT customer_id, order_id, total_amount
FROM sql330.orders
WHERE status = 'PAID';
```

Vì `order_id` khác nhau, mỗi đơn vẫn là một dòng.

### 25.1. PostgreSQL DISTINCT ON

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    total_amount
FROM sql330.orders
WHERE status = 'PAID'
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
```

`DISTINCT ON` là mở rộng của PostgreSQL. Nó giữ **dòng đầu tiên trong mỗi nhóm customer_id theo ORDER BY**. Vì vậy thứ tự `ordered_at DESC, order_id DESC` là **thiết yếu để chọn đúng đơn**.

Lưu ý trong PostgreSQL, các biểu thức trong `DISTINCT ON (...)` phải khớp các biểu thức đứng đầu của `ORDER BY` theo yêu cầu cú pháp. Không dùng như câu SQL đa hệ không cần chỉnh sửa.

### 25.2. ROW_NUMBER đa hệ hơn

```sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sql330.orders
    WHERE status = 'PAID'
)
SELECT
    customer_id,
    order_id,
    ordered_at,
    total_amount
FROM ranked
WHERE rn = 1;
```

Cách này diễn đạt rõ “xếp hạng từng đơn trong mỗi nhóm rồi chọn hạng 1”. Cần `ORDER BY` trong window để biết **mới nhất**; không thể bỏ vì nghĩ mọi ORDER BY đều chậm.

Nếu muốn **kết quả cuối** cũng xếp theo khách:

```sql
-- Thêm vào cuối câu SELECT phía ngoài:
ORDER BY customer_id;
```

Thứ tự trong window chọn bản ghi đúng, nhưng không tự bảo đảm thứ tự trình bày của toàn bộ hàng đầu ra.

## 26. DISTINCT, ORDER BY và phân trang

### 26.1. OFFSET sâu có thể tốn kém

```sql
SELECT order_id, ordered_at, total_amount
FROM sql330.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20 OFFSET 20000;
```

Dù có index phù hợp, DBMS vẫn có thể phải đi qua rất nhiều hàng trước khi trả 20 hàng ở vị trí sâu. `OFFSET` lớn không có nghĩa engine tự “nhảy” đến đúng dòng thứ 20.001 trong thứ tự logic với chi phí O(1).

### 26.2. Keyset pagination

Khi client đã nhận một trang, lưu **khóa sort của dòng cuối**: `last_ordered_at` và `last_order_id`.

Trang tiếp theo:

```sql
-- :last_ordered_at và :last_order_id là tham số client
-- lấy từ hàng cuối của trang trước, không phải chuỗi SQL tự nối.
SELECT
    order_id,
    ordered_at,
    total_amount
FROM sql330.orders
WHERE status = 'PAID'
  AND (ordered_at, order_id)
      < (:last_ordered_at, :last_order_id)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Với thứ tự giảm trên cả hai khóa, điều kiện cặp `(ordered_at, order_id) < (...)` lấy các hàng nằm **sau cursor** trong thứ tự từ mới đến cũ, nếu các khóa không `NULL`. PostgreSQL hỗ trợ so sánh row constructor như trên; DBMS khác có thể phải viết:

```sql
AND (
    ordered_at < :last_ordered_at
    OR (
        ordered_at = :last_ordered_at
        AND order_id < :last_order_id
    )
)
```

Các tham số `:...` là ký hiệu minh họa của client/framework, **không phải biến SQL đã tự khai báo trong psql**. Khi chạy thực tế, thay bằng bind parameter đúng driver.

Keyset giúp tránh việc bỏ qua số lượng hàng lớn theo `OFFSET`, nhưng yêu cầu thứ tự ổn định và xử lý thay đổi dữ liệu/cursor cẩn thận. Không áp dụng trực tiếp nếu người dùng cần nhảy tới trang bất kỳ theo số trang mà không có cursor.

### 26.3. DISTINCT làm phân trang phức tạp hơn

Nếu một tập kết quả bị nhân dòng do JOIN, thêm `DISTINCT` sau khi `LIMIT` theo cách không đúng có thể khiến trang không đủ số bản ghi duy nhất. Ngược lại, `SELECT DISTINCT ... ORDER BY ... LIMIT` có thể cần xử lý loại trùng trước khi xác định top N. Tốt hơn là hiểu **đơn vị kết quả** và loại bỏ nguồn nhân dòng bằng `EXISTS`/aggregate khi phù hợp.

## 27. Truy vấn có ba vấn đề đồng thời: cách viết lại

Giả sử một danh sách đơn PAID có tag `sale` được viết như sau:

```sql
-- Có thể làm nhiều việc không cần thiết.
SELECT DISTINCT o.*
FROM sql330.orders AS o
JOIN sql330.order_tags AS t
  ON t.order_id = o.order_id
WHERE o.status = 'PAID'
  AND t.tag = 'sale'
ORDER BY o.ordered_at DESC;
```

Bối cảnh của ví dụ: ứng dụng chỉ cần **20 đơn mới nhất có tag sale**, hiển thị `order_id`, `ordered_at`, `total_amount`.

Cách viết rõ mục tiêu hơn:

```sql
SELECT
    o.order_id,
    o.ordered_at,
    o.total_amount
FROM sql330.orders AS o
WHERE o.status = 'PAID'
  AND EXISTS (
      SELECT 1
      FROM sql330.order_tags AS t
      WHERE t.order_id = o.order_id
        AND t.tag = 'sale'
  )
ORDER BY
    o.ordered_at DESC,
    o.order_id DESC
LIMIT 20;
```

So sánh:

| Khía cạnh | Truy vấn ban đầu | Truy vấn viết lại |
| --- | --- | --- |
| Cột kết quả | `o.*` gồm payload/note | Chỉ ba cột cần hiển thị |
| Loại trùng | `DISTINCT` dự phòng hàng JOIN | `EXISTS` diễn đạt quan hệ tồn tại |
| Thứ tự | Chỉ `ordered_at DESC`, chưa xác định khi trùng thời điểm | `ordered_at DESC, order_id DESC` |
| Số dòng | Không giới hạn | `LIMIT 20` theo yêu cầu |
| Mục tiêu | Danh sách rộng chưa rõ ý nghĩa | 20 đơn PAID mới nhất có tag sale |

**Không nhận định hai truy vấn là tương đương hoàn toàn.** Chúng khác cả số cột và số hàng, vì **yêu cầu nghiệp vụ** đã được xác định lại. Đây là điều quan trọng trong tối ưu: một truy vấn “chạy nhanh” chỉ có giá trị nếu trả **đúng những gì người dùng cần**.

Nếu bài toán thật cần toàn bộ các đơn có tag sale và tất cả cột, không thể tùy tiện thêm LIMIT hay bỏ cột. Khi ấy chỉ tối ưu những phần thật sự dư thừa.

## 28. Cách đo công bằng thay vì tối ưu theo cảm giác

Một thí nghiệm có ý nghĩa cần chú ý:

### 28.1. So sánh truy vấn tương đương

Nếu A trả 50.000 hàng và B trả 20 hàng, B nhanh hơn không chứng minh chỉ vì bỏ `SELECT *`. Bạn đã thay đổi **khối lượng và ngữ nghĩa**. Tách từng biến để biết phần nào mang lại lợi ích.

### 28.2. Cố gắng đo nhiều lần

Các nguồn biến động:

- Cache lần đầu “lạnh” so với lần sau “nóng”.
- Tác vụ DBMS khác chạy đồng thời.
- CPU, bộ nhớ, SSD và tải hệ điều hành.
- Thống kê và kích thước bảng.
- Kế hoạch đổi do số lượng tham số hoặc phân bố dữ liệu.
- Cấu hình `work_mem`, song song hóa.
- Chi phí mạng và driver nếu đo end-to-end.

Không lấy một lần `Execution Time` vài mili-giây để kết luận chênh lệch nhỏ đã chắc chắn có ý nghĩa.

### 28.3. Không ép planner khi chưa có bằng chứng

PostgreSQL có các tham số như `enable_seqscan` phục vụ điều tra, nhưng ép bỏ seq scan không phải chiến lược tối ưu mặc định. Seq scan có thể đúng khi đọc phần lớn bảng; index scan có thể tốn nhiều random I/O.

Cách làm nên theo chu trình:

```text
Xác định đầu ra đúng
        |
        v
Ghi nhận SQL + chỉ mục hiện tại
        |
        v
EXPLAIN (ANALYZE, BUFFERS)
        |
        v
Xem rows / width / Sort / Unique / HashAggregate / Heap Fetches
        |
        v
Đổi MỘT điểm có giả thuyết rõ ràng
        |
        v
Chạy lại, đối chiếu kết quả dữ liệu và tài nguyên
        |
        v
Giữ thay đổi khi cải thiện đáng kể mà vẫn đúng nghĩa
```

Đây là cách tối ưu đáng tin hơn danh sách “mẹo” áp dụng mù quáng.

## 29. Khác biệt giữa các hệ quản trị

Các khái niệm projection, distinct và sort tồn tại rộng rãi, nhưng cú pháp và kế hoạch có thể khác.

| DBMS | Giới hạn số dòng | Công cụ/kế hoạch | Điểm cần nhớ |
| --- | --- | --- | --- |
| PostgreSQL | `LIMIT ... OFFSET ...` | `EXPLAIN (ANALYZE, BUFFERS)`, `Sort`, `Unique`, `HashAggregate`, `Index Only Scan` | `DISTINCT ON` riêng của PostgreSQL; visibility map ảnh hưởng index-only |
| MySQL/MariaDB | `LIMIT ... OFFSET ...` | `EXPLAIN`, `EXPLAIN ANALYZE` trên phiên bản hỗ trợ; `Using filesort`, temporary table khi liên quan | `Using filesort` là tên phương pháp sort, không tự đồng nghĩa luôn ghi ra file trên đĩa |
| SQL Server | `TOP (n)`, `OFFSET ... FETCH` theo ngữ cảnh; `ORDER BY` | Actual/estimated execution plan, `Sort`, `Hash Match (Aggregate)`, `Stream Aggregate`, `Key Lookup` | `TOP` cần `ORDER BY` để chọn “top” có ý nghĩa, có thể thấy `Top N Sort` |
| Oracle | `FETCH FIRST n ROWS ONLY` hoặc cơ chế tương ứng | `EXPLAIN PLAN`, `DBMS_XPLAN`, các toán tử sort/index/table access | Kiểm tra cách engine xử lý top-N và truy cập bảng theo ROWID |
| SQLite | `LIMIT ... OFFSET ...` | `EXPLAIN QUERY PLAN`, thông tin index và temporary B-tree khi liên quan | Covering index và sort B-tree có thể thấy trong plan |

Ví dụ SQL Server:

```sql
SELECT TOP (20)
    order_id,
    ordered_at,
    total_amount
FROM dbo.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC;
```

Ví dụ Oracle:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Trong cả hai câu, `ORDER BY` không dư thừa: nó định nghĩa **20 dòng nào** được chọn.

Không so sánh trực tiếp số “cost” trong execution plan giữa hai DBMS khác nhau; đơn vị và mô hình ước lượng không đồng nhất.

## 30. Những hiểu lầm thường gặp

| Nhận định | Vì sao chưa đúng | Cách nghĩ phù hợp |
| --- | --- | --- |
| “`SELECT *` luôn chậm” | Một dòng theo PK và tất cả cột cần dùng có thể rất nhanh | Chỉ chọn cột theo nhu cầu và đo dữ liệu thực |
| “`SELECT *` không ảnh hưởng index” | Cột ngoài index có thể cần truy cập bảng chính | Xem khả năng covering/index-only |
| “`DISTINCT` sửa mọi duplicate” | Nó chỉ loại dòng trùng theo toàn bộ SELECT, có thể che lỗi JOIN | Hiểu đúng cardinality và khóa kết quả |
| “`DISTINCT` luôn sort toàn bảng” | Có thể dùng hash, index hoặc optimizer chứng minh unique | Đọc plan thay vì suy từ cú pháp |
| “`GROUP BY` luôn nhanh hơn DISTINCT” | Cùng tập giá trị có thể được lập kế hoạch tương đương | Chọn cú pháp theo ý nghĩa |
| “`GROUP BY` tự sắp xếp kết quả” | Không có bảo đảm thứ tự trả về | Dùng ORDER BY ngoài cùng khi cần |
| “`ORDER BY` luôn thừa” | Top-N, window và pagination phụ thuộc thứ tự | Chỉ bỏ thứ tự không thuộc yêu cầu |
| “Không có ORDER BY thì có thứ tự PK” | Scan/index/optimizer có thể đổi | Không dựa vào thứ tự ngẫu nhiên |
| “Có index cho cột sort thì chắc chắn không Sort” | Compound index, filter, chiều và chi phí có thể không khớp | So khớp toàn bộ khóa/plan |
| “`LIMIT 20` là 20 dòng mới nhất” | Thiếu thứ tự thì 20 dòng tùy kế hoạch | `ORDER BY ... LIMIT 20` |
| “`ORDER BY ordered_at` đủ ổn định” | Ties chưa xác định | Thêm khóa phụ duy nhất |
| “Nhiều `Heap Fetches` trong Index Only Scan là bug” | MVCC visibility có thể buộc đọc heap | Xem visibility map, workload, vacuum và plan |
| “Tăng work_mem là tối ưu tốt nhất” | Có thể làm tăng tổng tiêu thụ bộ nhớ khi nhiều session | Tối ưu số dòng/bề rộng/index trước |
| “Subquery ORDER BY bảo đảm thứ tự toàn bộ kết quả” | Thứ tự cuối cần yêu cầu ở SELECT ngoài cùng | Đặt ORDER BY tại nơi tiêu thụ thứ tự |

## 31. Bài tập thực hành

Dùng bộ dữ liệu `sql330.orders` và `sql330.order_tags` đã tạo, trừ khi bài yêu cầu giải thích thuần lý thuyết.

### Bài 1 — Thu hẹp projection

Một API chỉ trả `order_id`, `ordered_at`, `total_amount` của các đơn PAID cho khách 42. Viết truy vấn không dùng `SELECT *`. Nêu hai khoản chi phí có thể giảm so với lấy toàn bộ cột.

### Bài 2 — Hiểu DISTINCT

Dự đoán ý nghĩa hai câu:

```sql
SELECT DISTINCT customer_id FROM sql330.orders;
SELECT DISTINCT customer_id, status FROM sql330.orders;
```

Vì sao số dòng của hai câu có thể khác?

### Bài 3 — DISTINCT thừa về logic

Bảng `sql330.orders` có khóa chính `order_id`. Vì sao `SELECT DISTINCT order_id FROM sql330.orders` không cần loại trùng về mặt dữ liệu? Có chắc DBMS không thực hiện thêm thao tác nào không?

### Bài 4 — JOIN một-nhiều

Viết câu trả về mỗi đơn có ít nhất một tag `'sale'` hoặc `'email'` **một lần** mà không dùng `DISTINCT`. So với JOIN + DISTINCT, câu đó thể hiện yêu cầu nghiệp vụ gì rõ ràng hơn?

### Bài 5 — ORDER BY và LIMIT

Viết câu lấy 10 đơn PAID mới nhất, sắp ổn định khi hai đơn có cùng `ordered_at`. Vì sao `LIMIT 10` mà không ORDER BY không đúng?

### Bài 6 — Index phù hợp

Trong các index đã tạo, index nào có thể hỗ trợ `WHERE status='PAID' ORDER BY ordered_at DESC, order_id DESC LIMIT 20`? Vì sao index `(customer_id) INCLUDE (ordered_at, total_amount)` không có thứ tự sắp xếp tương đương?

### Bài 7 — Thực nghiệm

Chạy `EXPLAIN (ANALYZE, BUFFERS)` trên hai câu ở mục 19. Ghi số dòng, width, scan type, buffers và execution time. Giải thích tại sao không thể kết luận chỉ từ một lần đo thời gian.

### Bài 8 — GROUP BY không tạo thứ tự hợp đồng

Viết truy vấn đếm số đơn theo trạng thái, không yêu cầu thứ tự. Sau đó sửa để sắp theo số đơn giảm dần, cùng khóa phụ ổn định nếu hai trạng thái có số lượng bằng nhau.

### Bài 9 — DISTINCT để chọn đơn mới nhất?

Vì sao `SELECT DISTINCT customer_id, order_id, ordered_at FROM sql330.orders` không trả một dòng mỗi khách? Viết cách dùng `ROW_NUMBER` để lấy đơn mới nhất theo khách.

### Bài 10 — ORDER BY trong subquery

Giả sử cần danh sách `customer_id` không cần thứ tự và không giới hạn số dòng. Có nên viết subquery sắp `ordered_at DESC` rồi SELECT `customer_id` từ ngoài? Vì sao thứ tự đó không phải cam kết đầu ra cuối?

### Bài 11 — Top-N và sort

So sánh nhu cầu tài nguyên giữa: (A) trả tất cả 50.000 đơn sắp theo `total_amount DESC`; (B) chỉ trả 10 đơn có `total_amount` cao nhất. Vì sao B có thể dùng Top-N sort và cần ORDER BY?

### Bài 12 — Pagination

Một truy vấn dùng `OFFSET 20000 LIMIT 20` trên dữ liệu sắp `ordered_at DESC, order_id DESC`. Nêu nhược điểm và viết điều kiện keyset cho trang tiếp theo với cursor từ hàng cuối trang hiện tại.

### Bài 13 — Chọn đúng nơi loại trùng

Trong báo cáo đếm đơn theo customer, bạn thấy:

```sql
SELECT DISTINCT customer_id, COUNT(*)
FROM sql330.orders
GROUP BY customer_id;
```

`DISTINCT` có ý nghĩa gì khi `GROUP BY customer_id` đã tạo một dòng mỗi khách? Có nên bỏ không? Vì sao?

### Bài 14 — Kế hoạch không có Sort

Bạn chạy `ORDER BY ordered_at DESC` nhưng execution plan không có node Sort. Có phải DBMS bỏ qua yêu cầu ORDER BY không? Hãy nêu ít nhất hai lý do có thể giải thích plan không có Sort.

### Bài 15 — Phân biệt tối ưu với đổi nghĩa

Một truy vấn báo cáo trả toàn bộ đơn PAID, tất cả cột, theo thứ tự thời gian. Bạn đề xuất thay bằng ba cột và `LIMIT 20`. Tại sao phải xác nhận yêu cầu trước khi gọi đó là “bản tối ưu tương đương”?

## 32. Gợi ý đáp án

**Bài 1.**

```sql
SELECT order_id, ordered_at, total_amount
FROM sql330.orders
WHERE customer_id = 42 AND status = 'PAID';
```

Có thể giảm byte truyền qua mạng, serialization phía ứng dụng, và tăng cơ hội index bao phủ dữ liệu. Hiệu quả thực tế phụ thuộc plan và dữ liệu.

**Bài 2.** Câu đầu lấy mỗi `customer_id` một lần; với dữ liệu mẫu có 1.000 khách. Câu hai lấy mỗi tổ hợp `(customer_id, status)` một lần, một khách có nhiều status sẽ xuất hiện nhiều dòng.

**Bài 3.** `order_id` đã unique/PK. `DISTINCT` không cần thiết về ngữ nghĩa. Optimizer có thể tận dụng thông tin đó, nhưng cần đọc plan để biết có thêm công việc hay không.

**Bài 4.**

```sql
SELECT o.order_id, o.customer_id
FROM sql330.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM sql330.order_tags AS t
    WHERE t.order_id = o.order_id
      AND t.tag IN ('sale','email')
);
```

`EXISTS` thể hiện đúng yêu cầu **tồn tại ít nhất một tag phù hợp**, không cần sinh ra một dòng mỗi tag.

**Bài 5.**

```sql
SELECT order_id, ordered_at, total_amount
FROM sql330.orders
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 10;
```

Thiếu `ORDER BY` thì engine có quyền trả bất kỳ mười hàng nào theo kế hoạch.

**Bài 6.** `sql330_idx_status_time` có các khóa `status, ordered_at DESC, order_id DESC` phù hợp. Index `sql330_idx_customer_cover` có `customer_id` làm key; `ordered_at` trong `INCLUDE` là payload của index, **không** quy định thứ tự khóa theo thời gian.

**Bài 7.** Phải ghi số đo thực của máy mình; không có một plan/timing bắt buộc. Cache, ước lượng thống kê, tải hệ thống, dữ liệu và chi phí truyền dữ liệu có thể làm thay đổi kết quả.

**Bài 8.**

```sql
SELECT status, COUNT(*) AS order_count
FROM sql330.orders
GROUP BY status;

SELECT status, COUNT(*) AS order_count
FROM sql330.orders
GROUP BY status
ORDER BY order_count DESC, status ASC;
```

**Bài 9.** `order_id` khác nhau làm mỗi đơn là một tổ hợp riêng, `DISTINCT` không chọn đơn mới nhất.

```sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM sql330.orders
)
SELECT customer_id, order_id, ordered_at
FROM ranked
WHERE rn = 1;
```

**Bài 10.** Không cần sort subquery nếu dữ liệu đầu ra không yêu cầu thứ tự hoặc không có toán tử nào cần thứ tự bên trong. Truy vấn ngoài cùng không có `ORDER BY` thì không được bảo đảm thứ tự hàng.

**Bài 11.** A yêu cầu trả toàn bộ tập đã sắp, có thể cần sort nhiều hàng. B chỉ cần top 10; một số engine có thể dùng cấu trúc Top-N với ít bộ nhớ hơn, nhưng vẫn phải chọn đúng mười giá trị lớn nhất nên `ORDER BY` là thiết yếu.

**Bài 12.** `OFFSET 20000` có thể buộc DBMS duyệt/bỏ nhiều hàng, và dữ liệu thay đổi giữa request có thể làm trôi trang. Với cursor `(:last_time, :last_id)`:

```sql
WHERE status = 'PAID'
  AND (
      ordered_at < :last_time
      OR (ordered_at = :last_time AND order_id < :last_id)
  )
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20
```

Kết hợp trong một câu `SELECT ... FROM sql330.orders`, bind hai giá trị từ hàng cuối của trang trước.

**Bài 13.** Khi `GROUP BY customer_id` đã tạo một dòng mỗi customer, thêm `DISTINCT` trên `customer_id, COUNT(*)` không thay đổi số hàng. Có thể bỏ để làm câu SQL rõ ràng, rồi kiểm tra plan.

**Bài 14.** Có thể engine đọc index vốn đúng thứ tự, hoặc nhận đầu vào đã có thứ tự từ phép toán trước đó. Không có node Sort không có nghĩa DBMS bỏ điều kiện `ORDER BY`.

**Bài 15.** Bản mới đổi cả danh sách cột và số hàng; nếu báo cáo thật cần tất cả dữ liệu thì sai nghĩa. Chỉ gọi là tối ưu hợp lệ khi xác nhận ứng dụng thực sự chỉ cần 20 hàng và ba cột.

## 33. Dọn dữ liệu học tập

Sau khi hoàn thành các phép đo và bài tập, nếu chắc chắn các đối tượng thuộc **riêng bài thực hành**, có thể xóa schema thử:

```sql
-- Chỉ chạy trong database học tập do bạn quản lý.
DROP SCHEMA sql330 CASCADE;
```

`CASCADE` xóa cả bảng, index và đối tượng bên trong hoặc phụ thuộc vào schema; tuyệt đối không dùng với schema chung hay sản xuất khi chưa xem dependency.

## 34. Kết luận

Ba cấu trúc **`SELECT *`, `DISTINCT` và `ORDER BY`** không xấu tự thân. Chúng chỉ gây công việc thừa khi **không phục vụ yêu cầu thật**:

- Dùng **danh sách cột tường minh** khi giao diện chỉ cần một phần dữ liệu; điều này có thể giảm lượng truyền và tạo cơ hội cho covering/index-only scan.
- Dùng **`DISTINCT` khi cần duy nhất theo toàn bộ biểu thức SELECT**; đừng dùng nó để che JOIN một-nhiều khi mục tiêu thật sự là phép kiểm tra tồn tại.
- Dùng **`ORDER BY` ở đúng nơi cần thứ tự**: phân trang, top-N, window, ordered aggregate hoặc giao diện hiển thị. Bỏ sắp xếp chỉ khi không ảnh hưởng ý nghĩa đầu ra.
- Thiết kế **index theo bộ lọc và thứ tự**, không chỉ theo tên cột; xem bề rộng hàng, số dòng, hash/sort và khả năng truy cập bảng gốc.
- Kiểm chứng bằng **`EXPLAIN` và đo thực tế**, đồng thời đối chiếu số hàng và nội dung dữ liệu trước/sau khi viết lại.

Nguyên tắc cuối cùng: **truy vấn tốt không phải truy vấn có ít từ khóa nhất, mà là truy vấn diễn đạt đúng yêu cầu và tránh được công việc không cần thiết theo kế hoạch thực thi thực tế.**
