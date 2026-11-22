# Phân trang theo độ lệch và giới hạn khi dữ liệu thay đổi

Khi một truy vấn SQL trả về hàng nghìn hoặc hàng triệu dòng, ứng dụng thường không hiển thị tất cả cùng lúc. **Phân trang theo độ lệch (offset pagination)** chia kết quả thành các trang có kích thước cố định: bỏ qua một số dòng đầu và lấy tối đa một số dòng tiếp theo. Cách làm này dễ hiểu, cho phép người dùng mở trực tiếp trang 2, trang 3 hoặc trang bất kỳ, và được nhiều hệ quản trị cơ sở dữ liệu (DBMS) hỗ trợ.

Tuy nhiên, phân trang không chỉ là viết `LIMIT` và `OFFSET`. Nếu dữ liệu được **thêm, xóa hoặc cập nhật giữa hai lần tải trang**, những dòng đã thấy có thể xuất hiện lại, một số dòng chưa thấy có thể bị bỏ qua, và số trang có thể thay đổi. Ngay cả khi không ai sửa dữ liệu, một truy vấn thiếu `ORDER BY` đủ rõ ràng cũng có thể trả về các trang không ổn định.

Bài học này giải thích cách phân trang theo độ lệch, cách chọn thứ tự sắp xếp ổn định, những giới hạn khi dữ liệu thay đổi, cơ chế snapshot và các phương án thay thế khi cần duyệt tập kết quả nhất quán.

## 1. OFFSET và LIMIT hoạt động thế nào?

Về mặt logic, để hiển thị một trang kết quả, SQL cần:

1. Xác định các dòng đáp ứng điều kiện `WHERE`.
2. Sắp xếp chúng theo `ORDER BY`.
3. **Bỏ qua (skip)** số dòng được chỉ định bởi `OFFSET`.
4. **Trả về (take)** tối đa số dòng được chỉ định bởi `LIMIT`.

Ví dụ trên **PostgreSQL**, MySQL/MariaDB và SQLite:

```sql
SELECT product_id, product_name, created_at
FROM products
ORDER BY created_at DESC, product_id DESC
LIMIT 10 OFFSET 20;
```

Ý nghĩa: sắp xếp các sản phẩm mới nhất lên trước; bỏ qua **20 dòng đầu của kết quả đã sắp xếp**; lấy tối đa **10 dòng tiếp theo**. Nếu đánh số trang từ 1 và mỗi trang có 10 dòng, đây là **trang 3**.

`OFFSET` không phải “ID của dòng đầu tiên”. `OFFSET 20` nghĩa là bỏ qua 20 **dòng trong thứ tự truy vấn hiện tại**, chứ không phải `WHERE product_id > 20`.

### Ví dụ danh sách nhỏ

Giả sử dữ liệu đã được sắp theo `id ASC`:

```text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
```

Với `LIMIT 3`:

| Trang (đánh số từ 1) | OFFSET | Các ID nhận được |
| ---: | ---: | --- |
| 1 | 0 | 1, 2, 3 |
| 2 | 3 | 4, 5, 6 |
| 3 | 6 | 7, 8, 9 |
| 4 | 9 | 10, 11 |
| 5 | 12 | Không có dòng |

Nếu phần còn lại ít hơn `LIMIT`, DBMS trả về **ít hơn giới hạn**. Nếu `OFFSET` lớn hơn hoặc bằng số dòng của tập kết quả, trang có thể **rỗng**. Đây không tự động là lỗi SQL.

### Công thức tính độ lệch

Với hệ thống đánh số trang từ **1**:

\[
\text{offset} = (\text{page} - 1) \times \text{pageSize}
\]

Ví dụ `page = 4`, `pageSize = 25`:

\[
(4 - 1) \times 25 = 75
\]

Câu SQL lấy trang 4:

```sql
SELECT product_id, product_name
FROM products
ORDER BY product_id ASC
LIMIT 25 OFFSET 75;
```

Nếu API đánh số trang từ **0**, công thức là `offset = pageIndex * pageSize`. Phải xác định rõ quy ước đầu vào của API để tránh lỗi **lệch một trang (off-by-one)**.

| Quy ước | Trang đầu | Trang thứ hai | OFFSET với kích thước 25 |
| --- | ---: | ---: | --- |
| Trang bắt đầu từ 1 | `page=1` | `page=2` | 0, 25 |
| Trang bắt đầu từ 0 | `pageIndex=0` | `pageIndex=1` | 0, 25 |

## 2. ORDER BY là điều kiện cần để phân trang có ý nghĩa

Trong SQL, nếu không có `ORDER BY`, **thứ tự các dòng không được bảo đảm**. Dữ liệu có thể tình cờ xuất hiện theo thứ tự khóa chính hoặc thứ tự lưu trên đĩa, nhưng DBMS được quyền thay đổi kế hoạch thực thi, dùng chỉ mục khác hoặc chạy song song; vì vậy từng trang có thể khác nhau giữa các lần truy vấn.

**Không nên viết:**

```sql
SELECT product_id, product_name
FROM products
LIMIT 10 OFFSET 10;
```

Đoạn SQL này có thể chạy được ở một số DBMS, nhưng không xác định rõ dòng nào thuộc trang 2. Thứ tự vật lý, ID tự tăng hay việc lần chạy trước trả cùng kết quả **không thay thế** `ORDER BY`.

**Nên viết:**

```sql
SELECT product_id, product_name
FROM products
ORDER BY product_id ASC
LIMIT 10 OFFSET 10;
```

Ở đây `product_id` được giả định là **khóa chính duy nhất**. Khi dữ liệu không thay đổi, hai câu truy vấn cho các trang khác nhau có cùng quy tắc sắp xếp và không bị mơ hồ vì các giá trị trùng nhau.

### ORDER BY theo cột không duy nhất vẫn có thể không ổn định

Giả sử các dòng có cùng `created_at`:

| product_id | created_at | product_name |
| ---: | --- | --- |
| 15 | 2026-03-01 09:00:00 | A |
| 16 | 2026-03-01 09:00:00 | B |
| 17 | 2026-03-01 09:00:00 | C |

Câu sau chỉ yêu cầu sắp theo thời gian:

```sql
SELECT product_id, created_at
FROM products
ORDER BY created_at DESC
LIMIT 2 OFFSET 0;
```

Nếu nhiều dòng có cùng `created_at`, database **không bị bắt buộc** sắp các dòng đồng hạng theo `product_id`. Khi trang tiếp theo chạy như một truy vấn khác, thứ tự tương đối của các dòng đồng hạng có thể thay đổi và gây trùng/bỏ sót **ngay cả khi dữ liệu không đổi**.

Hãy thêm một **khóa phụ (tie-breaker)** duy nhất:

```sql
SELECT product_id, created_at
FROM products
ORDER BY created_at DESC, product_id DESC
LIMIT 2 OFFSET 0;
```

Thứ tự `(created_at DESC, product_id DESC)` xác định vị trí của mọi dòng khi `product_id` là duy nhất.

**Nguyên tắc:** khi có thể có giá trị trùng ở các cột sắp xếp, hãy bổ sung một hoặc nhiều cột để tạo thành thứ tự **toàn phần (total order)**, thường kết thúc bằng khóa chính duy nhất. Một thứ tự toàn phần chỉ bảo đảm tính xác định cho **cùng một tập dữ liệu và quy tắc so sánh**, chứ chưa thể giữ các trang cố định khi tập dữ liệu thay đổi.

### NULL và collation cũng ảnh hưởng thứ tự

Nếu cột `created_at` cho phép `NULL`, vị trí các dòng `NULL` trong `ORDER BY` phụ thuộc DBMS, hướng sắp xếp và cú pháp như `NULLS FIRST`/`NULLS LAST` nếu được hỗ trợ. Với cột văn bản, **collation** quyết định cách phân biệt chữ hoa, dấu và nhiều trường hợp so sánh khác.

Vì vậy, khi phân trang cần lặp lại được:

- Dùng cùng một `ORDER BY` ở mọi trang.
- Quy định thứ tự của `NULL` nếu dữ liệu có thể thiếu và dialect hỗ trợ.
- Hiểu collation đang dùng, nhất là khi đổi môi trường.
- Thêm cột phân biệt duy nhất ở cuối danh sách sort.
- Giữ nguyên `WHERE`, sort và bộ lọc giữa các lần tải trang.

## 3. Cú pháp phân trang trên các DBMS

Các hệ quản trị có cú pháp khác nhau nhưng cùng ý tưởng: sắp xếp, bỏ qua `offset` dòng, lấy tối đa `pageSize` dòng.

| DBMS | Ví dụ lấy 10 dòng, bỏ qua 20 dòng | Ghi chú |
| --- | --- | --- |
| **PostgreSQL** | `LIMIT 10 OFFSET 20` | Hỗ trợ `LIMIT`/`OFFSET` và cú pháp `OFFSET ... FETCH` |
| **MySQL/MariaDB** | `LIMIT 10 OFFSET 20` | Còn dạng `LIMIT 20, 10`: số đầu là offset, số sau là số dòng |
| **SQLite** | `LIMIT 10 OFFSET 20` | Còn dạng `LIMIT 20, 10` theo quy tắc của SQLite |
| **SQL Server 2012+** | `OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY` | Phải đặt sau `ORDER BY` |
| **Oracle Database 12c+** | `OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY` | Nên dùng cùng `ORDER BY` xác định |

### PostgreSQL, MySQL/MariaDB và SQLite

```sql
SELECT product_id, product_name, created_at
FROM products
ORDER BY created_at DESC, product_id DESC
LIMIT 10 OFFSET 20;
```

MySQL/MariaDB và SQLite còn hỗ trợ dạng ngắn:

```sql
-- MySQL/MariaDB/SQLite: offset đứng trước, row count đứng sau.
SELECT product_id, product_name, created_at
FROM products
ORDER BY created_at DESC, product_id DESC
LIMIT 20, 10;
```

Hai cách viết trên cùng biểu diễn “bỏ qua 20 dòng, lấy tối đa 10 dòng” trong những DBMS hỗ trợ cả hai. Nhưng `LIMIT 20, 10` **không** có nghĩa lấy 20 dòng rồi bỏ qua 10 dòng.

### SQL Server

```sql
-- SQL Server 2012+:
SELECT product_id, product_name, created_at
FROM dbo.products
ORDER BY created_at DESC, product_id DESC
OFFSET 20 ROWS
FETCH NEXT 10 ROWS ONLY;
```

`OFFSET` là một phần của `ORDER BY` trong cú pháp T-SQL này. Không viết `FETCH NEXT` độc lập mà quên `ORDER BY`.

### Oracle Database

```sql
-- Oracle Database 12c+:
SELECT product_id, product_name, created_at
FROM products
ORDER BY created_at DESC, product_id DESC
OFFSET 20 ROWS
FETCH NEXT 10 ROWS ONLY;
```

Oracle có những cách phân trang đời cũ dùng `ROWNUM` hoặc `ROW_NUMBER()`. Với phiên bản hiện đại, row limiting clause `OFFSET ... FETCH` thường dễ đọc hơn. Dù vậy, đừng lấy riêng cú pháp PostgreSQL `LIMIT` và giả định Oracle hỗ trợ y hệt.

### Không trộn cú pháp khi chuyển hệ

Một query trong tài liệu hoặc ứng dụng nhiều DBMS nên ghi rõ dialect. `LIMIT` và `OFFSET ... FETCH` không phải các đoạn văn bản có thể thay chéo từng từ khóa. Một số ORM/query builder sinh SQL theo engine, nhưng người viết vẫn cần kiểm tra **thứ tự sắp xếp và tính nhất quán dữ liệu**; ORM không thể tự ngăn mọi bản ghi trùng/bỏ sót khi có thao tác ghi đồng thời.

## 4. LIMIT và OFFSET luôn áp dụng lên cùng bộ lọc

Phân trang một danh sách đã lọc cần đặt `WHERE` trong **cùng câu truy vấn** với `ORDER BY`, `LIMIT` và `OFFSET`:

```sql
SELECT product_id, product_name, status, created_at
FROM products
WHERE status = 'ACTIVE'
ORDER BY created_at DESC, product_id DESC
LIMIT 10 OFFSET 20;
```

Ở đây `OFFSET 20` bỏ qua 20 **sản phẩm ACTIVE sau khi sắp xếp**, không phải 20 dòng bất kỳ trong bảng rồi mới tìm sản phẩm ACTIVE.

Sai sót thường thấy là một trang dùng `WHERE status = 'ACTIVE'`, trang khác bỏ điều kiện hoặc đổi cách diễn giải bộ lọc. Khi đó hai trang không còn thuộc cùng một tập kết quả, và không thể đánh giá việc trùng/bỏ sót theo một thứ tự thống nhất.

Nếu người dùng đổi bộ lọc (ví dụ từ trạng thái ACTIVE sang SOLD) hoặc đổi sắp xếp (từ mới nhất sang giá tăng dần), ứng dụng thường nên **quay về trang đầu**. Tái sử dụng `OFFSET 100` từ bộ lọc cũ có thể khiến trang mới rỗng hoặc hiển thị một phần danh sách không như mong đợi.

## 5. Hạn chế lớn nhất: INSERT trước vị trí hiện tại gây trùng dòng

Giả sử bảng có 10 bản ghi và được sắp **ID giảm dần**:

```text
Trước khi thêm:
110, 109, 108, 107, 106, 105, 104, 103, 102, 101

Trang 1: LIMIT 3 OFFSET 0
         [110, 109, 108]

Trang 2 nếu dữ liệu không thay đổi:
         [107, 106, 105]
```

Sau khi người dùng tải trang 1, một giao dịch khác thêm bản ghi có ID `111` (đứng **trước** các dòng cũ theo `ORDER BY id DESC`):

```text
Sau khi thêm:
111, 110, 109, 108, 107, 106, 105, 104, 103, 102, 101

Trang 2: LIMIT 3 OFFSET 3
                      ↓
         [108, 107, 106]
```

**ID 108 xuất hiện ở cả trang 1 lẫn trang 2.** Lý do: `OFFSET` luôn đếm từ **đầu danh sách hiện tại**. Một dòng mới chen vào đầu danh sách đẩy các dòng cũ về sau một vị trí.

| Thời điểm | Trang | OFFSET | Kết quả |
| --- | ---: | ---: | --- |
| Trước INSERT | 1 | 0 | 110, 109, 108 |
| Sau INSERT 111 | 2 | 3 | **108**, 107, 106 |
| Nếu không có INSERT | 2 | 3 | 107, 106, 105 |

Trong ứng dụng thực tế, sự kiện tương tự xảy ra khi có đơn hàng mới, bài viết mới, giao dịch mới hoặc kết quả phù hợp với bộ lọc vừa được thêm. `ORDER BY id DESC` đã là một thứ tự duy nhất và ổn định trên **mỗi trạng thái dữ liệu**, nhưng nó **không ngăn được trùng lặp giữa hai trạng thái khác nhau**.

### Những kiểu INSERT khác có thể gây kết quả khác

- Dòng mới đứng **trước ranh giới trang**: có thể đẩy dòng đã xem vào trang sau, gây trùng.
- Dòng mới đứng **sau ranh giới trang**: có thể chỉ ảnh hưởng những trang phía sau.
- Dòng mới không đáp ứng `WHERE`: không ảnh hưởng tập kết quả phân trang hiện tại.
- Dòng mới có giá trị sort bằng dòng cũ: nếu không có tie-breaker duy nhất, thứ tự còn có thể không xác định.

Vấn đề cốt lõi là vị trí của các dòng trong tập kết quả **đang thay đổi**, trong khi offset vẫn là một con số cố định.

## 6. DELETE trước vị trí hiện tại gây bỏ sót dòng

Bắt đầu lại từ dữ liệu ban đầu:

```text
110, 109, 108, 107, 106, 105, 104, 103, 102, 101

Trang 1: [110, 109, 108]
```

Sau khi đã tải trang 1, một giao dịch khác xóa bản ghi `110`. Dữ liệu trở thành:

```text
109, 108, 107, 106, 105, 104, 103, 102, 101

Trang 2: LIMIT 3 OFFSET 3
         [106, 105, 104]
```

**ID 107 bị bỏ qua** khi người dùng đi từ trang 1 sang trang 2. Trước khi xóa, nó nằm ngay sau phần đã xem; sau khi xóa một dòng phía trước, nó dịch lên vị trí số 3, đúng phần mà `OFFSET 3` bỏ qua.

| Thời điểm | Trang | OFFSET | Kết quả |
| --- | ---: | ---: | --- |
| Trước DELETE | 1 | 0 | 110, 109, 108 |
| Sau DELETE 110 | 2 | 3 | **106**, 105, 104 |
| Nếu không có DELETE | 2 | 3 | **107**, 106, 105 |

Người dùng có thể không bao giờ nhìn thấy ID 107 dù bản ghi vẫn tồn tại. Tình trạng tương tự có thể xảy ra khi một dòng **không còn thỏa điều kiện lọc**, ví dụ trạng thái đổi từ `ACTIVE` sang `ARCHIVED`.

### Vì sao không thể sửa chỉ bằng ORDER BY?

`ORDER BY id DESC` giúp xác định dòng nào ở trước/sau tại **mỗi lần truy vấn**. Nhưng sau DELETE, phần tử đứng tại vị trí thứ 4 (khi đếm từ 1) thay đổi. Không có công thức `OFFSET` thuần túy nào biết trước rằng một dòng ở trang đầu đã biến mất giữa hai request.

Vì vậy, kết hợp `ORDER BY` với khóa duy nhất là **cần thiết** nhưng **chưa đủ** nếu cần duyệt một tập dữ liệu bất biến qua nhiều lần truy vấn.

## 7. UPDATE cũng có thể khiến dòng chuyển trang

Không chỉ INSERT và DELETE mới làm thay đổi vị trí. Nếu `ORDER BY` sử dụng trường có thể sửa, một `UPDATE` có thể đưa bản ghi từ phía sau lên đầu danh sách, hoặc đẩy nó xuống sâu hơn.

Ví dụ hệ thống sắp bài viết bằng `updated_at DESC`:

```sql
SELECT article_id, title, updated_at
FROM articles
WHERE status = 'PUBLISHED'
ORDER BY updated_at DESC, article_id DESC
LIMIT 20 OFFSET 20;
```

Giả sử bài viết từng nằm ở trang 3 được cập nhật nội dung; `updated_at` thay đổi và bài viết nhảy lên trang 1. Những dòng khác bị đẩy xuống, nên một lượt duyệt `OFFSET` có thể trùng hoặc bỏ sót, dù **không có bản ghi mới hoặc bị xóa**.

Cũng cần phân biệt hai loại UPDATE:

1. **Sửa cột không thuộc `ORDER BY` hay `WHERE`:** vị trí dòng thường không đổi, nhưng nội dung có thể khác giữa các lần truy vấn.
2. **Sửa cột thuộc `ORDER BY` hoặc `WHERE`:** thứ tự hoặc thành viên tập kết quả thay đổi, kéo theo nguy cơ trùng/bỏ sót.

Trong dữ liệu nhiều biến động, chọn `created_at` làm thứ tự có thể ổn định hơn `updated_at` nếu thời điểm tạo là bất biến. Nhưng INSERT và DELETE vẫn làm dịch vị trí; chỉ thay cột sắp xếp **không loại bỏ** vấn đề offset.

## 8. Thực hành PostgreSQL: nhìn thấy trùng và bỏ sót

Phần này chạy trên **PostgreSQL** trong database thực hành. Bảng `sql_offset_lab` chỉ dùng làm dữ liệu minh họa. Các thay đổi INSERT/DELETE được đặt trong transaction và kết thúc bằng `ROLLBACK` để giữ dữ liệu ban đầu.

### 8.1. Tạo dữ liệu có thứ tự rõ ràng

```sql
CREATE TABLE sql_offset_lab (
    id         INTEGER PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    title      VARCHAR(100) NOT NULL
);

INSERT INTO sql_offset_lab (id, created_at, title)
VALUES
    (101, TIMESTAMP '2026-03-01 09:01:00', 'Mục 101'),
    (102, TIMESTAMP '2026-03-01 09:02:00', 'Mục 102'),
    (103, TIMESTAMP '2026-03-01 09:03:00', 'Mục 103'),
    (104, TIMESTAMP '2026-03-01 09:04:00', 'Mục 104'),
    (105, TIMESTAMP '2026-03-01 09:05:00', 'Mục 105'),
    (106, TIMESTAMP '2026-03-01 09:06:00', 'Mục 106'),
    (107, TIMESTAMP '2026-03-01 09:07:00', 'Mục 107'),
    (108, TIMESTAMP '2026-03-01 09:08:00', 'Mục 108'),
    (109, TIMESTAMP '2026-03-01 09:09:00', 'Mục 109'),
    (110, TIMESTAMP '2026-03-01 09:10:00', 'Mục 110');
```

Thứ tự `created_at DESC, id DESC` ở dữ liệu mẫu trùng với thứ tự ID giảm dần. Hãy lấy hai trang liên tiếp khi chưa có thay đổi:

```sql
-- Trang 1:
SELECT id, created_at, title
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 0;

-- Trang 2:
SELECT id, created_at, title
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;
```

Kết quả mong đợi: trang 1 có ID `110, 109, 108`; trang 2 có ID `107, 106, 105`.

### 8.2. Mô phỏng INSERT giữa hai lần tải trang

```sql
BEGIN;

-- Giả lập người dùng tải trang 1 trước.
SELECT id
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 0;

-- Một bản ghi mới đứng đầu thứ tự.
INSERT INTO sql_offset_lab (id, created_at, title)
VALUES (111, TIMESTAMP '2026-03-01 09:11:00', 'Mục mới');

-- Giả lập người dùng tải trang 2 sau khi dữ liệu thay đổi.
SELECT id
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;

-- Hoàn nguyên dữ liệu thực hành.
ROLLBACK;
```

Hai trang cho `110, 109, 108` và `108, 107, 106`. ID 108 lặp lại.

**Về cách mô phỏng:** ở đây INSERT xảy ra trên **chính kết nối trong cùng transaction** để dễ lặp lại và có thể `ROLLBACK`. Trong ứng dụng thật, sự thay đổi thường do **giao dịch khác đã commit** giữa hai lần người dùng mở trang; dưới mức cô lập `READ COMMITTED` phổ biến của PostgreSQL, các câu `SELECT` khác nhau có thể nhìn thấy các phiên bản dữ liệu đã commit khác nhau. Ví dụ với thao tác tự INSERT chỉ minh họa cơ chế **dịch vị trí**; không được dùng nó để kết luận một transaction `REPEATABLE READ` cũng sẽ nhìn thấy INSERT từ giao dịch khác (mục 10).

### 8.3. Mô phỏng DELETE giữa hai lần tải trang

Sau `ROLLBACK` ở bước trên, bản ghi `111` không còn và bảng trở lại dữ liệu ban đầu:

```sql
BEGIN;

SELECT id
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 0;

DELETE FROM sql_offset_lab
WHERE id = 110;

SELECT id
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;

ROLLBACK;
```

Trang 1 cho `110, 109, 108`, trang 2 sau xóa cho `106, 105, 104`. ID 107 bị bỏ qua trong hành trình từ trang 1 đến trang 2.

Lưu ý: các lệnh `DELETE` ở đây chỉ dùng trên **bảng học tập tự tạo**, và được `ROLLBACK`. Không áp dụng chúng lên dữ liệu nghiệp vụ thật.

### 8.4. Dọn bảng khi kết thúc

```sql
-- Chỉ chạy nếu sql_offset_lab là bảng do chính bạn tạo cho bài học:
DROP TABLE sql_offset_lab;
```

Nếu muốn tiếp tục làm các bài tập ở cuối tài liệu, hãy giữ bảng và chỉ xóa khi không cần nữa.

## 9. Vì sao OFFSET lớn thường làm truy vấn chậm?

Phân trang theo độ lệch có chi phí tăng theo số dòng cần bỏ qua. Câu SQL:

```sql
SELECT id, created_at, title
FROM articles
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 200000;
```

muốn lấy **20 dòng**, nhưng phải xác định thứ tự đủ để vượt qua **200.000 dòng trước đó**. Một B-tree index phù hợp có thể giúp truy cập theo thứ tự mà không cần sort toàn bộ, nhưng engine vẫn thường phải **đi qua nhiều entry** trước khi bỏ qua được offset lớn. Nếu không có index phù hợp, DBMS có thể phải lọc/sắp xếp lượng dữ liệu đáng kể.

Mức chi phí thực tế phụ thuộc execution plan, chỉ mục, bộ lọc, cache, độ rộng dòng, heap lookup và cơ chế tối ưu của DBMS; không có một công thức thời gian chạy tuyệt đối cho mọi trường hợp. Tuy nhiên, **OFFSET tăng sâu thường không “nhảy tức thì” đến dòng thứ N như truy xuất phần tử mảng**.

### LIMIT nhỏ không đồng nghĩa truy vấn rẻ

Ví dụ:

```sql
-- Trang đầu:
SELECT id, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 0;

-- Một trang rất sâu:
SELECT id, created_at
FROM articles
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 500000;
```

Cả hai chỉ **trả về tối đa 20 dòng**, nhưng trang sâu có thể cần đọc/xét nhiều dòng hơn đáng kể. Nếu ứng dụng cho phép nhập `page=1000000` với kích thước trang lớn, request có thể tiêu tốn tài nguyên dù giao diện chỉ hiển thị vài dòng.

### Index cho bộ lọc và thứ tự

Giả sử thường lọc theo `status` và sắp theo `created_at DESC, id DESC` trên PostgreSQL:

```sql
CREATE INDEX ix_articles_status_created_id
ON articles (status, created_at DESC, id DESC);
```

Chỉ mục nhiều cột này có thể giúp truy vấn với `WHERE status = 'PUBLISHED'` và `ORDER BY created_at DESC, id DESC`, tùy phân bố dữ liệu và kế hoạch truy vấn. Nếu truy vấn chỉ lấy những cột có trong index, DBMS còn có thể tận dụng kiểu truy cập ít đọc heap hơn trong điều kiện phù hợp.

Sử dụng `EXPLAIN` hoặc `EXPLAIN ANALYZE` trong môi trường kiểm thử để xem:

- Truy vấn dùng index scan, bitmap scan hay sequential scan?
- Có sort tốn bộ nhớ/đĩa không?
- Số dòng thực sự được quét/loại bỏ trước khi trả page là bao nhiêu?
- Kế hoạch thay đổi thế nào khi `OFFSET` tăng?
- Chi phí của `COUNT(*)` đi kèm ra sao?

Không chạy `EXPLAIN ANALYZE` với truy vấn ghi dữ liệu ngoài môi trường phù hợp, vì công cụ này có thể **thực thi câu lệnh**; ví dụ ở đây chỉ dùng cho `SELECT`.

## 10. Snapshot và isolation: làm sao giữ cùng một tập dữ liệu?

Hai lần tải trang là **hai câu truy vấn**. Nếu hệ thống cho phép giao dịch khác ghi dữ liệu giữa chúng, kết quả có thể phản ánh **hai thời điểm khác nhau**.

### READ COMMITTED

Trong PostgreSQL ở mức cô lập `READ COMMITTED`, mỗi câu lệnh `SELECT` nhìn thấy một snapshot dữ liệu đã commit tương ứng với thời điểm câu lệnh bắt đầu (cùng với thay đổi do chính transaction thực hiện theo quy tắc engine). Vì vậy, dù hai câu `SELECT` nằm trong một transaction `READ COMMITTED`, dữ liệu được giao dịch khác commit giữa chúng **có thể xuất hiện ở truy vấn sau**.

```sql
-- PostgreSQL:
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT id
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 0;

-- Ở một kết nối khác, có thể có INSERT/DELETE được COMMIT tại đây.

SELECT id
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;

COMMIT;
```

Đoạn trên **chỉ mô tả tình huống**, không tự tạo giao dịch đồng thời. Cần hai kết nối nếu muốn thử thực tế thao tác từ giao dịch khác.

### REPEATABLE READ / SNAPSHOT

Trong PostgreSQL, một transaction `REPEATABLE READ` dùng một snapshot nhất quán cho các câu đọc thông thường trong transaction (không kể thay đổi do chính transaction ghi). Vì vậy, nếu hai truy vấn được thực hiện trong **cùng transaction** và dùng cùng `ORDER BY` toàn phần, INSERT/DELETE từ giao dịch khác được commit sau snapshot đó sẽ không làm dịch tập kết quả mà transaction đang đọc.

```sql
-- PostgreSQL, cùng một kết nối; dùng khi cần một ảnh chụp nhất quán:
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT id
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 0;

SELECT id
FROM sql_offset_lab
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;

COMMIT;
```

**Điều kiện then chốt là cùng transaction/snapshot.** Trong giao diện web, trang 1 và trang 2 thường được tải bằng **hai HTTP request**, mỗi request có transaction riêng. Chỉ cấu hình `REPEATABLE READ` cho từng request **không đảm bảo** chúng dùng cùng snapshot.

Giữ một transaction database mở trong nhiều phút chỉ để người dùng bấm “Trang tiếp theo” thường là lựa chọn tốn kém: chiếm kết nối, kéo dài tuổi snapshot, có thể làm chậm dọn phiên bản dữ liệu cũ hoặc ảnh hưởng quản trị tùy engine. Các DBMS có cơ chế snapshot/cursor/export snapshot đặc thù, nhưng không có quy trình “giữ mọi trang bất biến qua mọi HTTP request” chỉ bằng `LIMIT/OFFSET` có thể áp dụng chung.

### Khi cần bản chụp nhất quán cho xuất dữ liệu

Với báo cáo, đối soát hoặc export cần đủ **mỗi dòng đúng một lần** tại cùng một thời điểm, có thể chọn:

- Thực hiện nhiều truy vấn trong **một transaction đọc snapshot nhất quán**, nếu DBMS/mức cô lập phù hợp và khối lượng cho phép.
- Chạy một truy vấn rồi sử dụng **cursor/streaming** của DBMS để đọc dần trong phạm vi phiên/giao dịch hợp lệ.
- Ghi một **tập ID hoặc kết quả đã cố định** vào bảng tạm, bảng công việc hoặc file export với vòng đời rõ ràng, rồi chia trang trên tập đã cố định.
- Dùng một mốc dữ liệu bất biến/snapshot do hệ thống thiết kế riêng, nếu kiến trúc và quy tắc nghiệp vụ hỗ trợ.

**Mốc thời gian `created_at <= :cutoff` không tự tạo snapshot đầy đủ.** Nó có thể loại bớt các INSERT mới có thời gian tạo muộn, nhưng các bản ghi cũ vẫn có thể bị xóa, thay trạng thái hoặc cập nhật trường sort giữa các trang; cả dữ liệu có timestamp nhập lùi cũng có thể phá giả định. Không coi điều kiện thời gian đơn thuần là một biện pháp đảm bảo snapshot tuyệt đối.

## 11. COUNT(*), tổng số trang và dữ liệu thay đổi

Giao diện dạng “Trang 3 / 125” thường cần hai truy vấn:

```sql
-- Truy vấn dữ liệu của trang:
SELECT id, title, created_at
FROM articles
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 40;

-- Truy vấn đếm:
SELECT COUNT(*) AS total_items
FROM articles
WHERE status = 'PUBLISHED';
```

Hai truy vấn phải có **cùng bộ lọc**. Nhưng nếu chúng chạy ở các thời điểm khác nhau, `total_items` có thể không tương ứng chính xác với các dòng đang hiển thị. Ví dụ sau khi lấy trang 3, một số bài viết bị xóa hoặc đổi trạng thái; số dòng đếm được giảm, hoặc ngược lại có bài viết mới làm tăng tổng.

### Tính số trang

Với tổng `totalItems` đã biết và `pageSize > 0`:

\[
\text{totalPages} = \left\lceil
\frac{\text{totalItems}}{\text{pageSize}}
\right\rceil
\]

Ví dụ `totalItems=103` và `pageSize=20` thì `totalPages=6`. Khi `totalItems=0`, tổng số trang dữ liệu thường được biểu diễn là 0; UI có thể có quy tắc hiển thị khác nhưng cần nhất quán.

Nếu dùng số nguyên trong ứng dụng, có thể tính không cần số thực bằng `(totalItems / pageSize) + (totalItems % pageSize == 0 ? 0 : 1)` để tránh nguy cơ tràn từ biểu thức `totalItems + pageSize - 1` khi dữ liệu rất lớn.

### COUNT(*) có thể tốn chi phí riêng

Trên bảng rất lớn, `COUNT(*)` với bộ lọc phức tạp có thể là một truy vấn đáng kể. Trả một trang 20 dòng không đồng nghĩa đếm chính xác hàng triệu dòng là miễn phí. Có thể cân nhắc:

- Chỉ cung cấp `hasNext` thay vì tổng trang, khi UI chỉ có “Xem tiếp”.
- Sử dụng tổng số ước tính hoặc cache có gắn nhãn **ước tính** nếu nghiệp vụ cho phép.
- Trả tổng chính xác theo yêu cầu riêng, hoặc tính ở snapshot cần thiết cho báo cáo.
- Lấy `pageSize + 1` dòng để biết liệu **tại thời điểm truy vấn đó** có dòng tiếp theo; chỉ hiển thị `pageSize` dòng.

Ví dụ với kích thước trang 20, lấy 21 dòng:

```sql
SELECT id, title
FROM articles
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
LIMIT 21 OFFSET 40;
```

Nếu nhận đủ 21 dòng, trang hiện tại có ít nhất một dòng tiếp theo **trong snapshot của câu truy vấn đó**. Chỉ hiển thị tối đa 20 dòng; dòng thứ 21 dùng để xác định `hasNext`. Đừng đổi bước nhảy của trang kế tiếp thành 21: nếu vẫn dùng offset pagination kích thước 20, trang kế tiếp có `OFFSET 60`.

Dù cách này tránh một phép đếm tổng, `hasNext` vẫn có thể thay đổi sau INSERT/DELETE. Nó không biến offset thành cơ chế duyệt snapshot bất biến.

## 12. Dùng OFFSET trong API và tránh lỗi đầu vào

Giả sử API dùng `page` đánh số từ 1 và `size` là số dòng mỗi trang:

```text
GET /api/articles?page=3&size=20
```

Backend nên kiểm tra:

- `page >= 1`.
- `size >= 1` và không vượt quá **giới hạn tối đa** mà API quy định, ví dụ 100.
- Phép tính `(page-1)*size` không tràn kiểu số nguyên.
- `ORDER BY` là quy tắc ổn định, ưu tiên tie-breaker duy nhất.
- Filter/sort phải đến từ các trường được cho phép, không nối trực tiếp tên cột tùy ý do người dùng gửi vào SQL.
- Với trang quá sâu, cần chính sách giới hạn hoặc giải pháp khác nếu chi phí truy vấn không phù hợp.

### Ví dụ Java JDBC với PostgreSQL

Đoạn này giả sử `connection` là `java.sql.Connection` đã mở đến database. API dùng page bắt đầu từ 1:

```java
int page = 3;
int pageSize = 20;

if (page < 1 || pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("page hoặc pageSize không hợp lệ");
}

// Tính bằng long; multiplyExact phát hiện tràn số.
long offset = Math.multiplyExact((long) (page - 1), (long) pageSize);

String sql = """
    SELECT id, created_at, title
    FROM articles
    WHERE status = ?
    ORDER BY created_at DESC, id DESC
    LIMIT ? OFFSET ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "PUBLISHED");
    ps.setInt(2, pageSize);
    ps.setLong(3, offset);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(
                rs.getLong("id") + " | " + rs.getString("title")
            );
        }
    }
}
```

`PreparedStatement` tách các **giá trị** khỏi văn bản câu SQL, tránh ghép trực tiếp input thành biểu thức SQL. Tuy nhiên, tham số `?` thông thường **không thay thế được tên cột hay từ khóa `ORDER BY`**. Nếu API cho chọn trường sắp xếp, nên ánh xạ lựa chọn hợp lệ vào một tập tên cột đã định nghĩa sẵn trước khi dựng SQL.

Với ví dụ trên, `page=3` và `pageSize=20` tạo `offset=40`. Một chính sách ứng dụng có thể từ chối `offset` quá lớn hoặc hướng người dùng sang cơ chế cursor/seek nếu danh sách sâu. Cần kiểm tra giới hạn kiểu số thực tế mà driver/DBMS chấp nhận.

### Giao diện và trạng thái phân trang

Khi người dùng sửa bộ lọc hoặc thứ tự sort, nên reset về trang 1. Với một ứng dụng cập nhật liên tục, cũng cần quyết định có hiển thị thông báo “Danh sách đã thay đổi; tải lại từ đầu” hay không. Nếu trang đang mở đã rỗng sau khi dữ liệu bị xóa, UI có thể làm mới tổng và điều hướng về trang còn dữ liệu thay vì coi đó là lỗi backend.

**Tham số trang không phải cursor:** `page=3` mô tả một vị trí số trong *kết quả hiện tại*. Nó không nhận diện “dòng cuối cùng mà người dùng đã thấy”.

## 13. Giải pháp thay thế: keyset/seek pagination

Nếu mục tiêu là duyệt lần lượt một danh sách liên tục thay đổi, **keyset pagination** (còn gọi là **seek/cursor pagination**) thường phù hợp hơn offset. Thay vì đếm và bỏ qua tất cả các dòng trước đó, truy vấn tiếp dựa trên **giá trị sắp xếp của dòng cuối đã đọc**.

Giả sử đang sắp theo:

```sql
ORDER BY created_at DESC, id DESC
```

Trang đầu:

```sql
-- PostgreSQL:
SELECT id, created_at, title
FROM articles
WHERE status = 'PUBLISHED'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Giả sử dòng cuối trang đầu có `created_at = '2026-03-01 09:08:00'` và `id = 108`. Trang tiếp theo có thể dùng:

```sql
-- PostgreSQL, cursor minh họa lấy từ dòng cuối trang trước:
SELECT id, created_at, title
FROM articles
WHERE status = 'PUBLISHED'
  AND (
      created_at < TIMESTAMP '2026-03-01 09:08:00'
      OR (
          created_at = TIMESTAMP '2026-03-01 09:08:00'
          AND id < 108
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Đây là phép so sánh **theo thứ tự từ điển (lexicographic)** trên cặp sort. Với PostgreSQL và kiểu cột tương thích, có thể viết gọn:

```sql
SELECT id, created_at, title
FROM articles
WHERE status = 'PUBLISHED'
  AND (created_at, id)
      < (TIMESTAMP '2026-03-01 09:08:00', 108)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Cách so sánh cặp trên phù hợp khi **cả hai cột đều sắp DESC**, không `NULL` và quy tắc so sánh phù hợp. Với tổ hợp ASC/DESC hoặc NULL phức tạp, phải xây dựng điều kiện seek theo đúng thứ tự, không thay `<` theo thói quen.

### Vì sao keyset giảm trùng do INSERT ở đầu danh sách?

Nếu sau trang 1 có dòng mới với khóa sắp xếp **lớn hơn** dòng cuối đã xem, dòng đó **không thỏa** điều kiện “khóa nhỏ hơn cursor”. Nó sẽ không đẩy ranh giới của trang kế tiếp như `OFFSET`. Truy vấn tiếp bắt đầu ngay **sau giá trị khóa đã biết**.

Keyset thường có lợi cho “Xem thêm”, feed, log hoặc danh sách nhiều trang sâu, đặc biệt khi có index hỗ trợ thứ tự và điều kiện seek. Tuy nhiên:

- Keyset **không tự tạo snapshot bất biến**. Một dòng chưa đọc có thể bị xóa, đổi filter hoặc đổi khóa sort; kết quả vẫn có thể thay đổi.
- Nếu dòng đã đọc bị cập nhật và di chuyển **xuống dưới cursor**, nó có thể xuất hiện lại; cần khóa sort ổn định và quy tắc sản phẩm phù hợp.
- Một cursor không nên chỉ chứa `created_at` khi nhiều dòng có timestamp trùng; phải chứa đủ bộ khóa sort, gồm ID duy nhất.
- Keyset không thuận tiện cho yêu cầu **nhảy trực tiếp đến trang 500** như offset.
- Cursor trong API nên gắn với bộ lọc/sort, được mã hóa và xác thực khi cần để người dùng không làm sai ngữ nghĩa hoặc lạm dụng truy vấn. Placeholder giá trị phải tiếp tục được bind an toàn.

### So sánh các cách tiếp cận

| Đặc điểm | OFFSET/LIMIT | Keyset/seek | Snapshot cố định |
| --- | --- | --- | --- |
| Nhảy tới trang N bất kỳ | Dễ | Không trực tiếp | Có thể, nếu kết quả đã được cố định và đánh số |
| Tải trang kế tiếp | Dễ | Dễ nếu có cursor | Dễ trong phạm vi snapshot |
| Chi phí khi đi rất sâu | Thường tăng theo offset | Thường ít phụ thuộc vị trí nếu có index phù hợp | Phụ thuộc cách lưu/đọc snapshot |
| INSERT mới ở đầu làm lặp dòng đã xem | Có thể | Thường tránh được với khóa sort ổn định | Không trong cùng snapshot |
| DELETE/UPDATE giữa các request | Có thể gây bỏ sót/trùng | Có thể thay đổi tập duyệt; ít phụ thuộc dịch vị trí | Không ảnh hưởng tập dòng đã cố định tại snapshot |
| Phù hợp | Danh sách nhỏ/vừa, ít thay đổi, cần số trang | Feed, “Xem thêm”, dữ liệu lớn | Export/đối soát cần ảnh chụp nhất quán |

Không có một phương án luôn tốt nhất. Chọn dựa trên **yêu cầu người dùng**, quy mô dữ liệu, mức độ ghi đồng thời, nhu cầu đi đến trang bất kỳ và yêu cầu nhất quán.

## 14. Các tình huống áp dụng trong thực tế

### Danh mục sản phẩm ít thay đổi

Một trang quản trị có vài nghìn sản phẩm, lọc theo danh mục, cần nút chuyển trực tiếp đến trang N và có thao tác ghi không thường xuyên. `LIMIT/OFFSET` với `ORDER BY` duy nhất, index phù hợp và cách làm mới dữ liệu rõ ràng thường đủ dùng.

### Danh sách thông báo liên tục có sự kiện mới

Thông báo mới luôn được thêm ở đầu. Nếu người dùng cuộn từ trang 1 xuống trang 2 bằng offset, việc thêm thông báo giữa hai request dễ làm xuất hiện thông báo đã đọc lần nữa. **Keyset** theo `(created_at DESC, id DESC)` thường phù hợp hơn cho “Xem thêm”.

### Báo cáo đối soát cuối ngày

Mỗi giao dịch tại một thời điểm chốt phải được tính **đúng một lần**. Vừa chạy export vừa cho ghi dữ liệu rồi dùng nhiều câu `LIMIT/OFFSET` độc lập có thể khiến bản export bỏ sót/trùng theo ranh giới trang. Cần một **snapshot hoặc tập kết quả đã cố định** theo quy trình báo cáo; chỉ thay `OFFSET` thành keyset không bảo đảm tính nhất quán tuyệt đối khi dữ liệu còn được cập nhật/xóa.

### Bộ lọc trạng thái đang thay đổi

Người dùng đang duyệt đơn hàng `status = 'PENDING'`, trong lúc nhân viên khác xác nhận đơn và đổi sang `APPROVED`. Dòng vừa được xử lý biến mất khỏi danh sách PENDING, có thể khiến các dòng sau dịch lên một vị trí. Đây là **hiệu ứng thay đổi thành viên tập kết quả**, tương đương DELETE đối với truy vấn đã lọc, dù không có lệnh xóa dòng vật lý.

## 15. Các lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách tiếp cận |
| --- | --- | --- |
| Trang 2 lặp một dòng của trang 1 | Có INSERT mới đứng trước ranh giới trang | Xem yêu cầu snapshot hoặc keyset; không trông đợi offset tự ổn định |
| Một dòng chưa thấy bị bỏ qua | DELETE hoặc UPDATE filter/sort làm dòng dịch về phía trước | Chọn phương án nhất quán phù hợp; theo dõi thay đổi tập kết quả |
| Trùng/bỏ sót dù dữ liệu không đổi | Thiếu `ORDER BY` hoặc sort có giá trị trùng, không có tie-breaker | Thêm thứ tự toàn phần, thường kết thúc bằng khóa chính |
| API `page=1` lại bắt đầu từ dòng 11 | Nhầm trang từ 0 sang trang từ 1 | Chuẩn hóa công thức `(page-1)*size` hoặc `pageIndex*size` |
| Trang N rỗng sau khi xóa dữ liệu | Số dòng giảm, offset vượt cuối tập | Cập nhật trạng thái trang, làm mới tổng/điều hướng phù hợp |
| Sort thay đổi nhưng vẫn giữ offset cũ | Trang đang dựa trên thứ tự trước đó | Reset trang sau khi đổi sort/filter |
| `ORDER BY created_at` không xác định | Nhiều dòng cùng timestamp | Thêm `id` duy nhất làm tie-breaker |
| Truy vấn trang rất sâu chậm | Engine phải đi qua nhiều dòng để bỏ qua offset | Xem index, giới hạn độ sâu, cân nhắc keyset |
| `COUNT(*)` và danh sách không nhất quán | Hai truy vấn nhìn hai thời điểm khác nhau | Chấp nhận tính cập nhật của UI hoặc dùng snapshot khi cần |
| `REPEATABLE READ` nhưng hai trang vẫn khác nhau | Hai HTTP request là hai transaction khác nhau | Xem vòng đời snapshot; dùng tập kết quả cố định nếu phải nhất quán |
| Giá trị `LIMIT/OFFSET` bất thường gây tải nặng | Không kiểm tra input, số trang quá lớn | Đặt max size/max offset và kiểm tra tràn số |
| JOIN làm tăng số dòng trước LIMIT | Quan hệ JOIN không 1-1, một đối tượng được lặp lại | Xác định **đơn vị phân trang**; có thể cần phân trang khóa đối tượng trước rồi JOIN |

### Phân trang sau JOIN: chú ý đơn vị kết quả

Nếu một đơn hàng có nhiều dòng hàng, câu SQL:

```sql
SELECT o.order_id, o.created_at, i.item_id
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20 OFFSET 0;
```

đang phân trang **20 dòng kết quả JOIN**, không phải 20 đơn hàng riêng biệt. Một đơn hàng có 10 item có thể chiếm 10 dòng của trang. Để phân trang **20 đơn hàng**, thường nên xác định 20 ID đơn hàng trong một CTE/subquery có sort và limit rồi lấy chi tiết theo các ID đó bằng truy vấn kế tiếp hoặc JOIN có chủ đích.

Ví dụ PostgreSQL:

```sql
WITH page_orders AS (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC, order_id DESC
    LIMIT 20 OFFSET 0
)
SELECT p.order_id, p.created_at, i.item_id
FROM page_orders AS p
LEFT JOIN order_items AS i ON i.order_id = p.order_id
ORDER BY p.created_at DESC, p.order_id DESC, i.item_id;
```

Kết quả sau JOIN **có thể nhiều hơn 20 dòng**, nhưng chỉ thuộc **tối đa 20 đơn hàng** đã chọn. Vẫn cần cân nhắc dữ liệu thay đổi nếu trang khác được tải ở thời điểm khác.

## 16. Bài tập thực hành

### Bài 1 — Tính OFFSET

Một API đánh số trang từ 1, mỗi trang chứa 15 dòng. Tính `OFFSET` cho trang 1, 2, 5 và 10. Viết một câu `SELECT` dùng PostgreSQL để lấy trang 5 khi sắp theo `id ASC`.

### Bài 2 — ORDER BY ổn định

Bảng `articles` có các cột `id` (duy nhất), `created_at` (có thể trùng), `title`. Vì sao câu `ORDER BY created_at DESC` có thể gây các trang không nhất quán ngay cả khi không có INSERT/DELETE? Viết `ORDER BY` thay thế.

### Bài 3 — Phát hiện trùng do INSERT

Ban đầu các ID theo thứ tự `DESC` là `9, 8, 7, 6, 5, 4, 3, 2, 1`. Người dùng xem trang 1 với `LIMIT 3 OFFSET 0`. Sau đó có ID `10` mới được thêm vào đầu. Hãy xác định trang 2 với `LIMIT 3 OFFSET 3` và dòng nào bị lặp.

### Bài 4 — Phát hiện bỏ sót do DELETE

Bắt đầu lại từ `9, 8, 7, 6, 5, 4, 3, 2, 1`. Sau khi xem trang 1, ID `9` bị xóa. Xác định trang 2 và dòng nào đã bị bỏ sót so với thứ tự ban đầu.

### Bài 5 — COUNT và tổng trang

Một danh sách có 101 dòng, mỗi trang 20 dòng. Tính tổng trang và offset trang cuối. Nếu sau đó có 2 dòng bị xóa trước khi người dùng mở trang cuối, điều gì có thể xảy ra? Có thể khẳng định tổng đếm ở thời điểm trước vẫn đúng không?

### Bài 6 — Chọn phương án phân trang

Hãy chọn và giải thích phương án phù hợp:

1. Danh mục quản trị có 2.000 bản ghi, cần đi thẳng đến trang 8.
2. Feed nhận hàng nghìn tin mới mỗi phút, chủ yếu bấm “Xem thêm”.
3. Export dữ liệu kế toán cần mỗi dòng thuộc một thời điểm chốt xuất hiện đúng một lần.
4. Màn hình theo dõi đơn đang xử lý, trạng thái đơn thay đổi liên tục.

### Bài 7 — Viết truy vấn keyset

Bảng `articles` sắp `created_at DESC, id DESC`. Dòng cuối của trang hiện tại có `created_at='2026-03-01 10:00:00'`, `id=500`. Viết điều kiện `WHERE` để lấy các dòng **đứng sau** cursor, với giả định `created_at` và `id` không `NULL`.

### Gợi ý đáp án

1. Offset lần lượt `0`, `15`, `60`, `135`. Trang 5: `SELECT * FROM articles ORDER BY id ASC LIMIT 15 OFFSET 60;` (giả sử bảng có cột `id`).
2. Các timestamp trùng khiến thứ tự giữa các dòng đồng hạng không được xác định; dùng `ORDER BY created_at DESC, id DESC`.
3. Trang 1 trước INSERT: `9,8,7`. Sau khi thêm 10, trang 2 offset 3: `7,6,5`. ID `7` lặp.
4. Trang 1: `9,8,7`. Xóa 9, danh sách trở thành `8,7,6,5,4,3,2,1`. Trang 2 offset 3: `5,4,3`; ID `6` bị bỏ sót.
5. `CEIL(101/20)=6` trang; trang 6 có `OFFSET 100`. Sau khi xóa 2 dòng, tập dữ liệu chỉ còn 99 dòng và truy vấn trang 6 có thể rỗng, tùy vị trí các dòng bị xóa; tổng cũ không còn phản ánh trạng thái hiện tại.
6. (1) OFFSET với `ORDER BY` duy nhất và index phù hợp. (2) Keyset/cursor theo khóa sort ổn định. (3) Snapshot/tập kết quả cố định, có thể stream hoặc chia trang trên tập đã chốt. (4) Cân nhắc keyset hoặc cơ chế refresh/cập nhật theo phiên, tùy yêu cầu thao tác và chấp nhận thay đổi.
7. Điều kiện: `WHERE created_at < TIMESTAMP '2026-03-01 10:00:00' OR (created_at = TIMESTAMP '2026-03-01 10:00:00' AND id < 500)`, kết hợp với các bộ lọc khác bằng ngoặc và giữ `ORDER BY created_at DESC, id DESC`.

Điều cần ghi nhớ: **OFFSET/LIMIT chọn một lát cắt theo vị trí trong tập kết quả tại thời điểm truy vấn**. `ORDER BY` toàn phần tạo thứ tự xác định, nhưng không cố định các vị trí nếu có ghi mới, xóa hoặc cập nhật. Khi phải duyệt một tập dữ liệu đang đổi mà không muốn bị dịch trang, cân nhắc keyset; khi phải xuất đủ dữ liệu đúng một thời điểm, cần cơ chế snapshot hoặc tập kết quả được chốt rõ ràng.
