# LIMIT, FETCH FIRST, TOP và cách phân trang

Khi một truy vấn trả về hàng triệu dòng, ứng dụng thường chỉ cần hiển thị một phần: 20 sản phẩm đầu tiên, 50 đơn mới nhất, trang thứ ba của danh sách khách hàng hoặc 10 bản ghi có doanh thu cao nhất. SQL có nhiều cách giới hạn số hàng, nhưng cú pháp khác nhau giữa các hệ quản trị: PostgreSQL/MySQL/SQLite thường dùng `LIMIT`, chuẩn SQL có `FETCH FIRST`, SQL Server có `TOP` và `OFFSET ... FETCH`, Oracle hỗ trợ row limiting clause và `ROW_NUMBER()`.

Bài học thuộc chương **SQL đa hệ quản trị** của module Database SQL. Mục tiêu là hiểu cả cú pháp lẫn ngữ nghĩa để viết truy vấn có kết quả ổn định, phân trang đúng khi dữ liệu thay đổi và tránh truy vấn ngày càng chậm khi người dùng đi tới những trang sâu.

Điểm quan trọng nhất:

> **Giới hạn số hàng không tự xác định hàng nào được lấy.** Muốn kết quả có ý nghĩa, cần xác định thứ tự bằng `ORDER BY` với khóa sắp xếp đủ ổn định. Muốn phân trang dữ liệu lớn, cần chọn chiến lược phù hợp thay vì mặc định dùng OFFSET rất lớn.

## 1. SQL không bảo đảm thứ tự nếu không có ORDER BY

Một bảng quan hệ là tập hợp hàng; database không hứa trả hàng theo thứ tự chèn, thứ tự khóa chính, thứ tự vật lý trên đĩa hay thứ tự của index.

Ví dụ:

```sql
SELECT ticket_id, title
FROM tickets;
```

Truy vấn này không có `ORDER BY`. Database có thể trả các hàng theo một thứ tự ở lần chạy này và thứ tự khác ở lần chạy khác do thay đổi kế hoạch, index, vacuum, parallel execution hoặc dữ liệu.

Ngay cả khi truy vấn hiện tại luôn trả ID tăng dần trên máy phát triển, đó vẫn không phải cam kết SQL.

### 1.1. LIMIT không tự chọn "hàng đầu tiên"

```sql
SELECT ticket_id, title
FROM tickets
LIMIT 10;
```

Câu lệnh giới hạn kết quả còn tối đa 10 hàng, nhưng nếu không có `ORDER BY`, không có định nghĩa nghiệp vụ về 10 hàng ấy là những hàng nào.

Nếu yêu cầu là 10 ticket mới nhất:

```sql
SELECT ticket_id, title, created_at
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 10;
```

`created_at DESC` sắp xếp thời điểm mới trước; `ticket_id DESC` là tie-breaker khi nhiều ticket có cùng thời điểm.

### 1.2. Thứ tự phải đủ duy nhất để phân trang

Giả sử:

| ticket_id | created_at |
| ---: | --- |
| 10 | 2026-10-01 10:00:00 |
| 11 | 2026-10-01 10:00:00 |
| 12 | 2026-10-01 09:00:00 |

Nếu chỉ viết `ORDER BY created_at DESC`, hai hàng 10 và 11 đồng hạng. Database có thể trả chúng theo thứ tự bất kỳ trong cùng nhóm. Khi dùng LIMIT/OFFSET để chia trang, thứ tự không ổn định có thể làm một hàng xuất hiện ở hai trang hoặc bị bỏ sót giữa các lần truy vấn.

Cách rõ ràng hơn:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

Nếu `ticket_id` là duy nhất, thứ tự toàn bộ hàng được xác định duy nhất.

### 1.3. ORDER BY ở đâu mới có tác dụng?

`ORDER BY` ở truy vấn ngoài cùng quyết định thứ tự kết quả trả về cho client. Một `ORDER BY` bên trong subquery không bảo đảm truy vấn ngoài giữ nguyên thứ tự, trừ khi thứ tự được dùng trong một phép toán có ngữ nghĩa rõ ràng và truy vấn ngoài cũng quy định thứ tự cần thiết.

Ví dụ:

```sql
SELECT *
FROM (
    SELECT ticket_id, created_at
    FROM tickets
    ORDER BY created_at DESC
) AS recent_tickets;
```

Không nên dựa vào thứ tự của subquery để hiển thị. Hãy viết:

```sql
SELECT *
FROM (
    SELECT ticket_id, created_at
    FROM tickets
) AS recent_tickets
ORDER BY created_at DESC, ticket_id DESC;
```

## 2. LIMIT và OFFSET trong PostgreSQL, MySQL, SQLite

Cú pháp quen thuộc:

```sql
SELECT columns
FROM table_name
ORDER BY sort_column
LIMIT row_count OFFSET row_to_skip;
```

- `LIMIT row_count`: tối đa bao nhiêu hàng.
- `OFFSET row_to_skip`: bỏ qua bao nhiêu hàng trước khi trả kết quả.
- OFFSET bắt đầu từ 0: `OFFSET 0` nghĩa là không bỏ hàng nào.

### 2.1. Ví dụ LIMIT

```sql
SELECT ticket_id, title, created_at
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 20;
```

Lấy tối đa 20 ticket mới nhất.

### 2.2. Ví dụ OFFSET

```sql
SELECT ticket_id, title, created_at
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 20 OFFSET 40;
```

Bỏ 40 hàng đầu và trả tối đa 20 hàng tiếp theo. Đây là trang thứ ba nếu mỗi trang có 20 hàng và đánh số trang từ 1:

\[
OFFSET=(page-1)\times pageSize
\]

Với `page=3`, `pageSize=20`, OFFSET là 40.

### 2.3. Cú pháp tương thích MySQL

MySQL hỗ trợ dạng:

```sql
SELECT ticket_id, title
FROM tickets
ORDER BY ticket_id
LIMIT 40, 20;
```

Dạng `LIMIT offset, row_count` tương đương `LIMIT row_count OFFSET offset`. Khi viết code đa hệ quản trị, dạng có từ khóa OFFSET thường dễ đọc và ít gây nhầm tham số hơn.

### 2.4. LIMIT ALL và LIMIT 0

Trong PostgreSQL:

```sql
SELECT * FROM tickets LIMIT ALL;
SELECT * FROM tickets LIMIT 0;
```

- `LIMIT ALL` không giới hạn số hàng.
- `LIMIT 0` trả 0 hàng, hữu ích trong một số tình huống kiểm tra cấu trúc/kế hoạch hoặc API.

Không phải mọi DBMS đều hỗ trợ các biến thể này. Nếu cần tương thích rộng, chỉ dùng dạng cơ bản mà hệ quản trị đích hỗ trợ.

### 2.5. LIMIT và OFFSET có thể là tham số

PostgreSQL, MySQL và SQLite thường cho phép truyền giá trị số qua parameter marker trong prepared statement tùy driver:

```sql
SELECT ticket_id, title
FROM tickets
ORDER BY ticket_id
LIMIT ? OFFSET ?;
```

Ví dụ Java:

```java
PreparedStatement ps = conn.prepareStatement(
    "SELECT ticket_id, title " +
    "FROM tickets ORDER BY ticket_id LIMIT ? OFFSET ?"
);
ps.setInt(1, pageSize);
ps.setLong(2, offset);
```

Cần kiểm tra cú pháp bind và kiểu dữ liệu theo driver/DBMS. Không ghép pageSize/offset từ chuỗi input vào SQL; bind tham số giúp tránh injection và lỗi định dạng.

## 3. FETCH FIRST và OFFSET ... FETCH

`FETCH FIRST` là cú pháp row limiting theo chuẩn SQL, được nhiều hệ quản trị hỗ trợ. Cấu trúc phổ biến:

```sql
SELECT columns
FROM table_name
ORDER BY sort_column
OFFSET offset_rows ROWS
FETCH NEXT fetch_rows ROWS ONLY;
```

Một số hệ cho phép `FETCH FIRST n ROWS ONLY` mà không cần OFFSET.

### 3.1. FETCH FIRST

```sql
SELECT ticket_id, title, created_at
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
FETCH FIRST 10 ROWS ONLY;
```

Lấy tối đa 10 hàng đầu sau khi sắp xếp.

`FIRST` và `NEXT` có thể dùng theo ngữ cảnh cú pháp; `ROW` và `ROWS` cũng có biến thể được DBMS chấp nhận. Để dễ đọc, thường dùng `FETCH FIRST n ROWS ONLY` khi không có offset.

### 3.2. OFFSET ... FETCH NEXT

```sql
SELECT ticket_id, title, created_at
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY;
```

Cách này diễn đạt phân trang theo offset, tương tự `LIMIT 20 OFFSET 40`.

### 3.3. FETCH FIRST trong PostgreSQL

PostgreSQL hỗ trợ:

```sql
SELECT ticket_id, title
FROM tickets
ORDER BY ticket_id
FETCH FIRST 5 ROWS ONLY;
```

và dạng có offset:

```sql
SELECT ticket_id, title
FROM tickets
ORDER BY ticket_id
OFFSET 5 ROWS
FETCH NEXT 5 ROWS ONLY;
```

PostgreSQL cũng hỗ trợ `FETCH FIRST ... WITH TIES` trong các phiên bản hiện đại. `WITH TIES` cần ORDER BY và có thể trả nhiều hơn số hàng yêu cầu nếu các hàng tiếp theo bằng khóa sắp xếp của hàng cuối được chọn.

### 3.4. FETCH FIRST trong Oracle

Oracle Database 12c trở lên hỗ trợ row limiting clause:

```sql
SELECT ticket_id, title, created_at
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
FETCH FIRST 10 ROWS ONLY;
```

Phân trang:

```sql
SELECT ticket_id, title, created_at
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
OFFSET 20 ROWS
FETCH NEXT 10 ROWS ONLY;
```

Oracle cũng hỗ trợ các biến thể như `FETCH FIRST n PERCENT ROWS ONLY` và `WITH TIES` theo cú pháp row limiting clause. Cần kiểm tra phiên bản Oracle và cú pháp chính xác của truy vấn.

### 3.5. FETCH FIRST trong DB2 và các hệ khác

DB2 và một số DBMS khác hỗ trợ `FETCH FIRST n ROWS ONLY`; các phiên bản mới có thể hỗ trợ `OFFSET/FETCH` theo cú pháp cụ thể. Không suy luận mọi sản phẩm có từ khóa FETCH đều hỗ trợ mọi biến thể, đặc biệt WITH TIES, PERCENT, bind parameter và vị trí clause.

### 3.6. FETCH và LIMIT: chọn gì?

| Tiêu chí | LIMIT/OFFSET | FETCH FIRST/OFFSET FETCH |
| --- | --- | --- |
| Tính quen thuộc | Phổ biến ở PostgreSQL/MySQL/SQLite | Gần chuẩn SQL |
| Hệ hỗ trợ | Tùy DBMS | Nhiều hệ doanh nghiệp |
| Dễ đọc | Ngắn gọn | Tường minh |
| Tương thích đa hệ | Không phổ quát | Rộng hơn nhưng vẫn cần kiểm tra dialect |
| WITH TIES | Không có dạng LIMIT cơ bản | Một số DBMS hỗ trợ |
| PERCENT | Không có trong LIMIT cơ bản | Một số DBMS hỗ trợ |

Không có một câu SQL phân trang duy nhất chạy nguyên trạng trên mọi DBMS. Nếu ứng dụng hỗ trợ nhiều dialect, nên dùng abstraction/query builder có dialect rõ ràng hoặc viết adapter riêng.

## 4. TOP trong SQL Server

SQL Server thường dùng `TOP`:

```sql
SELECT TOP (10)
    ticket_id,
    title,
    created_at
FROM dbo.tickets
ORDER BY created_at DESC, ticket_id DESC;
```

`TOP (10)` giới hạn kết quả tối đa 10 hàng.

### 4.1. TOP có thể dùng tham số

SQL Server cho phép biểu thức trong ngoặc, có thể là biến:

```sql
DECLARE @row_count int = 10;

SELECT TOP (@row_count)
    ticket_id, title
FROM dbo.tickets
ORDER BY ticket_id DESC;
```

Với JDBC, có thể dùng parameter marker trong vị trí phù hợp theo driver SQL Server:

```java
PreparedStatement ps = conn.prepareStatement(
    "SELECT TOP (?) ticket_id, title " +
    "FROM dbo.tickets ORDER BY ticket_id DESC"
);
ps.setInt(1, pageSize);
```

Hãy kiểm thử đúng driver/phiên bản SQL Server. Tên bảng, tên cột và hướng sort không thể bind bằng ? như một giá trị; các lựa chọn đó cần allowlist.

### 4.2. TOP PERCENT

SQL Server hỗ trợ:

```sql
SELECT TOP (10) PERCENT
    ticket_id, title
FROM dbo.tickets
ORDER BY created_at DESC, ticket_id DESC;
```

`PERCENT` yêu cầu lấy tỷ lệ phần trăm hàng đầu, số hàng thực tế được làm tròn theo quy tắc SQL Server. Nó không giống LIMIT 10 (10 hàng).

Nếu tổng số hàng thay đổi, số hàng trả về cũng thay đổi. Không nên dùng TOP PERCENT cho phân trang cố định 20 hàng/trang.

### 4.3. TOP WITH TIES

```sql
SELECT TOP (5) WITH TIES
    ticket_id, title, score
FROM dbo.search_results
ORDER BY score DESC;
```

Nếu hàng thứ 5 có score 90 và còn nhiều hàng score 90, tất cả hàng đồng hạng theo biểu thức ORDER BY có thể được trả thêm.

**Kết quả có thể nhiều hơn 5 hàng.** Không thêm một cột tie-breaker duy nhất vào ORDER BY nếu mục tiêu là giữ tất cả hàng cùng score; làm vậy có thể phá ý nghĩa đồng hạng. Nếu mục tiêu là phân trang xác định, hãy dùng khóa duy nhất làm tie-breaker và không dùng WITH TIES.

### 4.4. TOP trong UPDATE và DELETE

SQL Server cho phép TOP trong DML, ví dụ:

```sql
DELETE TOP (100)
FROM dbo.expired_sessions;
```

Nếu không có thứ tự xác định, không thể nói 100 hàng nào được xóa. TOP trong DELETE/UPDATE không cho phép đặt ORDER BY trực tiếp theo cách SELECT làm.

Nếu nghiệp vụ cần xóa 100 session cũ nhất, có thể xác định khóa qua CTE/subquery có thứ tự:

```sql
;WITH oldest AS (
    SELECT TOP (100) session_id
    FROM dbo.expired_sessions
    ORDER BY expires_at, session_id
)
DELETE s
FROM dbo.expired_sessions AS s
JOIN oldest AS o
  ON o.session_id = s.session_id;
```

Đây là mẫu SQL Server; cần xem xét khóa, trigger, FK và concurrency trong workload thật. Không dùng TOP để xóa một tập hàng mà không xác định rõ điều kiện nghiệp vụ.

## 5. Oracle cũ: ROWNUM và ROW_NUMBER

Trước Oracle 12c, row limiting thường được thực hiện qua `ROWNUM` hoặc analytic function `ROW_NUMBER()`.

### 5.1. ROWNUM được gán trước ORDER BY ở cùng query block

Một lỗi quen thuộc:

```sql
SELECT ticket_id, created_at
FROM tickets
WHERE ROWNUM <= 10
ORDER BY created_at DESC;
```

Trong Oracle, ROWNUM được gán khi các hàng được chọn trong query block; điều kiện ROWNUM <= 10 có thể chọn 10 hàng trước rồi mới sắp xếp chúng. Vì thế kết quả không nhất thiết là 10 hàng mới nhất toàn bảng.

### 5.2. Đưa ORDER BY vào inline view

```sql
SELECT ticket_id, created_at
FROM (
    SELECT ticket_id, created_at
    FROM tickets
    ORDER BY created_at DESC, ticket_id DESC
)
WHERE ROWNUM <= 10;
```

Truy vấn con sắp xếp trước; query block ngoài giới hạn các hàng sau khi nhận thứ tự ấy.

### 5.3. Phân trang ROWNUM hai tầng

Để lấy trang từ hàng 21 tới 30:

```sql
SELECT ticket_id, created_at
FROM (
    SELECT ordered_rows.*, ROWNUM AS rn
    FROM (
        SELECT ticket_id, created_at
        FROM tickets
        ORDER BY created_at DESC, ticket_id DESC
    ) ordered_rows
    WHERE ROWNUM <= 30
)
WHERE rn > 20
ORDER BY rn;
```

Lớp trong sắp xếp; lớp giữa giới hạn tới hàng 30 và đánh số; lớp ngoài bỏ 20 hàng đầu. Đây là kỹ thuật lịch sử thường gặp trong ứng dụng Oracle cũ.

### 5.4. ROW_NUMBER tổng quát hơn

```sql
SELECT ticket_id, created_at
FROM (
    SELECT
        ticket_id,
        created_at,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, ticket_id DESC
        ) AS rn
    FROM tickets
)
WHERE rn BETWEEN 21 AND 30
ORDER BY rn;
```

ROW_NUMBER() đánh số hàng theo thứ tự cửa sổ. Cách này còn hữu ích cho top-N-per-group, không chỉ phân trang.

Với Oracle 12c+, thường có thể dùng OFFSET ... FETCH dễ đọc hơn. Nhưng khi bảo trì hệ thống cũ, hiểu ROWNUM và ROW_NUMBER() vẫn rất cần thiết.

## 6. Top-N và Top-N-per-group không giống nhau

Giới hạn tổng số hàng khác với yêu cầu lấy N hàng trong **mỗi nhóm**.

### 6.1. Top 10 sản phẩm toàn hệ thống

```sql
SELECT product_id, product_name, revenue
FROM product_sales
ORDER BY revenue DESC, product_id
FETCH FIRST 10 ROWS ONLY;
```

Kết quả tối đa 10 sản phẩm của toàn bộ bảng.

### 6.2. Top 3 sản phẩm trong mỗi category

```sql
SELECT category_id, product_id, revenue
FROM (
    SELECT
        category_id,
        product_id,
        revenue,
        ROW_NUMBER() OVER (
            PARTITION BY category_id
            ORDER BY revenue DESC, product_id
        ) AS rn
    FROM product_sales
) ranked
WHERE rn <= 3
ORDER BY category_id, rn;
```

PARTITION BY category_id đặt bộ đếm riêng trong mỗi category. Kết quả có tối đa 3 sản phẩm cho mỗi nhóm.

### 6.3. ROW_NUMBER, RANK và DENSE_RANK

| Hàm | Hành vi khi đồng hạng | Ví dụ score 100, 90, 90, 80 |
| --- | --- | --- |
| ROW_NUMBER | Luôn đánh số riêng từng hàng | 1, 2, 3, 4 |
| RANK | Cùng hạng, bỏ qua số kế tiếp | 1, 2, 2, 4 |
| DENSE_RANK | Cùng hạng, không bỏ số kế tiếp | 1, 2, 2, 3 |

Dùng ROW_NUMBER() nếu cần tối đa N hàng mỗi nhóm và muốn xác định từng hàng bằng tie-breaker duy nhất.

Dùng RANK()/DENSE_RANK() nếu yêu cầu nghiệp vụ là lấy mọi hàng có thứ hạng nằm trong top N. Khi đó số hàng thực tế có thể lớn hơn N.

### 6.4. Lấy mọi hàng đồng điểm trong top 3

```sql
SELECT category_id, product_id, revenue
FROM (
    SELECT
        category_id,
        product_id,
        revenue,
        RANK() OVER (
            PARTITION BY category_id
            ORDER BY revenue DESC
        ) AS revenue_rank
    FROM product_sales
) ranked
WHERE revenue_rank <= 3
ORDER BY category_id, revenue_rank, product_id;
```

Không đưa product_id vào ORDER BY bên trong RANK nếu muốn các sản phẩm cùng revenue có cùng hạng; nếu thêm khóa duy nhất vào đó, mỗi hàng sẽ có thứ tự riêng và mất đồng hạng theo doanh thu.

### 6.5. Vì sao TOP/LIMIT không giải quyết top-N-per-group?

LIMIT 3 hay TOP (3) chỉ giới hạn **toàn kết quả**. Để lấy N hàng mỗi nhóm, cần window function, lateral/apply hoặc kỹ thuật tương ứng DBMS.

## 7. WITH TIES và ý nghĩa của đồng hạng

Một số DBMS hỗ trợ lấy thêm các hàng đồng hạng với hàng cuối cùng:

```sql
SELECT ticket_id, score
FROM search_results
ORDER BY score DESC
FETCH FIRST 5 ROWS WITH TIES;
```

Nếu score của hàng thứ năm là 80 và có thêm 4 hàng cùng score 80, kết quả có thể gồm 9 hàng.

### 7.1. ORDER BY xác định ties theo toàn bộ danh sách biểu thức

Nếu viết:

```sql
ORDER BY score DESC, ticket_id
FETCH FIRST 5 ROWS WITH TIES;
```

Hai hàng chỉ được coi là ties khi bằng nhau theo cả score và ticket_id. Nếu ticket_id là duy nhất, thường sẽ không có ties.

Do đó:

- Xếp hạng theo score và giữ mọi hàng cùng điểm: ORDER BY score DESC với WITH TIES.
- Lấy đúng một tập hàng có thứ tự xác định: thêm khóa duy nhất và dùng ONLY/LIMIT/TOP thường.

### 7.2. WITH TIES không phải phân trang ổn định

WITH TIES phù hợp với bảng xếp hạng, top điểm hoặc báo cáo cần giữ trọn nhóm đồng hạng. Nó không tự giải quyết việc chia trang: số hàng một trang có thể vượt giới hạn, và cần quy tắc xác định ranh giới trang cho nhóm ties.

## 8. OFFSET pagination: cách tính trang

Với số hàng mỗi trang là pageSize và trang đánh số từ 1:

\[
offset=(page-1)\times pageSize
\]

Ví dụ:

| page | pageSize | offset | Hàng được yêu cầu |
| ---: | ---: | ---: | --- |
| 1 | 20 | 0 | 1–20 |
| 2 | 20 | 20 | 21–40 |
| 3 | 20 | 40 | 41–60 |
| 10 | 20 | 180 | 181–200 |

### 8.1. Công thức trong Java

```java
long offset = Math.multiplyExact(
    (long) page - 1L,
    (long) pageSize
);
```

Math.multiplyExact giúp phát hiện tràn số thay vì âm thầm tạo offset sai. Trước đó cần kiểm tra page >= 1, pageSize nằm trong giới hạn hợp lý và dữ liệu đầu vào không phải số âm.

### 8.2. Luôn giới hạn pageSize ở server

Không tin client gửi pageSize=10 là luôn an toàn. Người dùng có thể gửi 1.000.000 hoặc giá trị cực lớn gây tải database, truyền dữ liệu và chiếm bộ nhớ.

Ví dụ:

```java
int normalizedPageSize = Math.min(
    Math.max(requestedPageSize, 1),
    100
);
```

Giá trị 100 là chính sách ví dụ; hệ thống thật cần chọn dựa trên payload, SLA và workload.

### 8.3. Trang ngoài phạm vi

Nếu tổng cộng 47 hàng và pageSize=20, trang 4 có offset 60, kết quả rỗng. API cần quyết định trả danh sách rỗng, lỗi page out of range hoặc tự điều chỉnh về trang cuối.

Không để UI giả định database sẽ tự chuyển trang 4 thành trang 3.

### 8.4. COUNT(*) để biết tổng trang

```sql
SELECT COUNT(*)
FROM tickets
WHERE status = 'open';
```

Số trang:

\[
totalPages=\left\lceil\frac{totalRows}{pageSize}\right\rceil
\]

Nếu totalRows=47 và pageSize=20, totalPages=3.

COUNT(*) có thể tốn chi phí đáng kể trên tập dữ liệu lớn và có thể không cùng snapshot với truy vấn lấy trang nếu chạy trong các transaction/snapshot khác nhau. Với giao diện infinite scroll, có thể không cần tổng số trang chính xác; chỉ cần biết còn hàng tiếp theo hay không.

## 9. OFFSET pagination có chi phí tăng ở trang sâu

Ví dụ:

```sql
SELECT ticket_id, title
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 20 OFFSET 500000;
```

Database vẫn phải xác định/bỏ qua một lượng lớn hàng trước khi trả 20 hàng tiếp theo. Một index phù hợp có thể giúp tìm thứ tự nhanh hơn, nhưng offset lớn vẫn thường yêu cầu đi qua các entry trước đó.

Với OFFSET 0, chi phí thường nhỏ hơn. Càng đi sâu, số hàng phải bỏ qua có thể càng lớn.

### 9.1. OFFSET có ưu điểm gì?

- Cú pháp đơn giản.
- Dễ nhảy trực tiếp tới trang N.
- Phù hợp bảng nhỏ hoặc số trang không sâu.
- Dễ kết hợp UI có số trang và tổng số trang.
- Dễ triển khai cho báo cáo/snapshot ít thay đổi.

### 9.2. Nhược điểm

- Trang sâu có thể chậm vì phải bỏ qua nhiều hàng.
- Chèn/xóa hàng giữa các request có thể làm dịch vị trí.
- Mỗi trang phụ thuộc vào thứ tự và trạng thái dữ liệu ở thời điểm query.
- COUNT tổng có thể tốn kém.
- Thứ tự không unique khiến trùng/mất hàng ngay cả khi dữ liệu không đổi.

### 9.3. Dữ liệu thay đổi giữa hai request gây lặp hoặc bỏ sót

Giả sử trang 1 trả hàng 1–20 theo thứ tự mới nhất. Trước khi tải trang 2, một hàng mới được chèn vào đầu danh sách. Khi query OFFSET 20, hàng thứ 20 trước đó có thể bị đẩy xuống vị trí 21, khiến nó xuất hiện lần nữa ở trang 2.

Ngược lại, nếu hàng trước vị trí offset bị xóa, một hàng có thể bị nhảy qua.

Đây là hệ quả của phân trang theo **vị trí**, trong khi tập dữ liệu thay đổi giữa các request.

### 9.4. Isolation không tự giải quyết mọi pagination qua nhiều HTTP request

Nếu hai trang được đọc trong cùng một transaction/snapshot phù hợp, có thể giữ góc nhìn dữ liệu nhất quán. Nhưng thông thường mỗi request HTTP mở transaction mới; không thể giả định trang 1 và trang 2 có cùng snapshot.

Giữ một transaction/snapshot mở suốt thời gian người dùng duyệt nhiều trang có thể tốn connection, giữ snapshot lâu và cản trở bảo trì MVCC. Cần cân nhắc snapshot token, version hoặc keyset pagination thay vì giữ transaction sống rất lâu.

## 10. Keyset pagination (seek pagination)

Keyset pagination không bỏ qua một số hàng theo vị trí. Nó dùng giá trị của hàng cuối trang trước làm **mốc tiếp tục**.

Giả sử thứ tự mới nhất trước:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

Trang đầu:

```sql
SELECT ticket_id, title, created_at
FROM tickets
ORDER BY created_at DESC, ticket_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Giả sử hàng cuối trang đầu có:

```text
created_at = 2026-10-01 09:30:00+07
ticket_id = 501
```

Trang kế tiếp lấy các hàng đứng **sau mốc đó** theo cùng thứ tự:

```sql
SELECT ticket_id, title, created_at
FROM tickets
WHERE (created_at, ticket_id) < (
    TIMESTAMPTZ '2026-10-01 09:30:00+07',
    501
)
ORDER BY created_at DESC, ticket_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Vì cả hai khóa sắp xếp đều DESC, toán tử < lấy các cặp nhỏ hơn mốc cuối trang. Cú pháp so sánh tuple được PostgreSQL hỗ trợ; với DBMS khác có thể cần viết điều kiện tương đương tường minh.

### 10.1. Điều kiện tương đương không dùng tuple comparison

```sql
SELECT ticket_id, title, created_at
FROM tickets
WHERE created_at < TIMESTAMPTZ '2026-10-01 09:30:00+07'
   OR (
        created_at = TIMESTAMPTZ '2026-10-01 09:30:00+07'
        AND ticket_id < 501
   )
ORDER BY created_at DESC, ticket_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Đây là dạng logic rõ ràng và có thể dễ chuyển sang những DBMS không hỗ trợ row-value comparison theo cách cần thiết.

### 10.2. Vì sao keyset thường nhanh hơn ở trang sâu?

Database có thể tìm vị trí tiếp tục dựa trên giá trị khóa và index phù hợp, rồi đọc tiếp 20 hàng. Nó không cần bỏ qua 500.000 hàng chỉ để tới trang sâu.

Keyset pagination thường hiệu quả khi:

- Có thứ tự sắp xếp rõ và ổn định.
- Có khóa tiếp tục duy nhất hoặc tổ hợp khóa đủ duy nhất.
- Có index hỗ trợ filter + order.
- Người dùng duyệt tiếp/previous thay vì nhảy tùy ý tới trang 500.

### 10.3. Keyset không tự tạo snapshot bất biến

Nếu có hàng mới được chèn **trước** mốc tiếp tục, trang tiếp theo thường không bị dịch vị trí như OFFSET; hàng mới đó không xuất hiện trong chuỗi đang duyệt về phía cũ hơn.

Tuy nhiên, nếu các giá trị sắp xếp của hàng đã đọc bị sửa, hoặc hàng mới được chèn có khóa nằm sau mốc, kết quả vẫn có thể thay đổi. Nếu nghiệp vụ yêu cầu một tập kết quả đóng băng tuyệt đối, cần snapshot/version hoặc một chiến lược lưu tập ID tại thời điểm bắt đầu.

### 10.4. Khóa sắp xếp phải có tie-breaker

Nếu chỉ dùng:

```sql
WHERE created_at < :last_created_at
ORDER BY created_at DESC
```

thì các hàng có cùng timestamp với hàng cuối trang có thể bị bỏ qua, vì điều kiện < không lấy phần còn lại có timestamp bằng nhau.

Dùng khóa kết hợp:

```sql
WHERE created_at < :last_created_at
   OR (created_at = :last_created_at AND ticket_id < :last_ticket_id)
ORDER BY created_at DESC, ticket_id DESC
```

Khóa cuối cùng nên duy nhất để mỗi hàng có vị trí tiếp tục rõ ràng.

## 11. Keyset với nhiều cột và hướng sort khác nhau

Keyset pagination phải biểu diễn đúng thứ tự mà `ORDER BY` tạo ra. Với một cột `DESC` và cột tie-breaker `DESC`, dùng cặp nhỏ hơn như ví dụ trước. Nếu hướng sort khác nhau, điều kiện so sánh cũng phải thay đổi theo từng cột.

### 11.1. Một cột ASC, một cột DESC

Giả sử:

```sql
ORDER BY priority ASC, created_at DESC, ticket_id DESC
```

Trang tiếp theo sau mốc `(last_priority, last_created_at, last_ticket_id)` phải chọn:

- Priority lớn hơn mốc, vì priority tăng ASC.
- Hoặc priority bằng mốc và created_at nhỏ hơn, vì created_at giảm DESC.
- Hoặc cả hai bằng mốc và ticket_id nhỏ hơn.

```sql
SELECT ticket_id, priority, created_at
FROM tickets
WHERE priority > :last_priority
   OR (
        priority = :last_priority
        AND created_at < :last_created_at
   )
   OR (
        priority = :last_priority
        AND created_at = :last_created_at
        AND ticket_id < :last_ticket_id
   )
ORDER BY priority ASC, created_at DESC, ticket_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Không thể dùng một tuple `<` đơn giản cho mọi trường hợp sort direction hỗn hợp mà không chuyển đổi khóa phù hợp.

### 11.2. NULL trong khóa sort

NULL tạo thêm vấn đề vì so sánh `NULL = value` hoặc `NULL < value` không trả TRUE/FALSE như giá trị thông thường; kết quả là UNKNOWN. DBMS còn có quy tắc mặc định khác nhau về NULLS FIRST/LAST.

PostgreSQL cho phép chỉ rõ:

```sql
ORDER BY due_at ASC NULLS LAST, ticket_id ASC
```

Nếu dùng due_at làm một phần cursor, phải mã hóa rõ trạng thái NULL và tạo điều kiện seek xử lý hai nhóm riêng. Ví dụ khi NULLS LAST:

```sql
-- Trang tiếp theo khi last_due_at khác NULL:
WHERE due_at > :last_due_at
   OR (due_at = :last_due_at AND ticket_id > :last_id)
   OR due_at IS NULL
```

Khi mốc đã nằm trong nhóm NULL:

```sql
-- Trang tiếp theo khi last_due_at IS NULL:
WHERE due_at IS NULL
  AND ticket_id > :last_id
```

Đây là mẫu cho `due_at ASC NULLS LAST, ticket_id ASC`. Các DBMS có thể dùng quy tắc NULL mặc định khác nhau; nếu muốn đa hệ, nên định nghĩa cách sắp xếp NULL tường minh và kiểm thử dialect.

### 11.3. Tránh khóa cursor có thể thay đổi

Nếu sort theo một cột thường xuyên được cập nhật, ví dụ priority hoặc status, một hàng có thể di chuyển từ phía sau cursor lên trước hoặc ngược lại giữa các request. Điều này có thể gây bỏ sót/lặp trong quá trình duyệt.

Nếu cần duyệt theo dòng sự kiện ổn định, ưu tiên các khóa bất biến như created_at không cập nhật và ID duy nhất, hoặc dùng snapshot/version phù hợp.

## 12. Trang tiếp theo và trang trước với keyset

Keyset thường thuận tiện nhất cho thao tác “Next”. Có thể lấy “Previous” bằng cách đảo hướng sort, lấy N hàng gần cursor, sau đó đảo thứ tự hiển thị.

Giả sử thứ tự chính là:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

### 12.1. Trang tiếp theo

Dùng điều kiện `<` như phần 10 để lấy các hàng cũ hơn mốc cuối trang.

### 12.2. Trang trước

Giả sử mốc đầu trang hiện tại là `(first_created_at, first_ticket_id)`. Muốn lấy các hàng mới hơn mốc này, truy vấn theo hướng ngược:

```sql
SELECT ticket_id, title, created_at
FROM tickets
WHERE (created_at, ticket_id) > (
    :first_created_at,
    :first_ticket_id
)
ORDER BY created_at ASC, ticket_id ASC
FETCH FIRST 20 ROWS ONLY;
```

Kết quả query ở trên là 20 hàng gần mốc nhất theo chiều ngược. Ứng dụng cần đảo thứ tự danh sách trước khi hiển thị theo thứ tự DESC ban đầu.

Nếu DBMS không hỗ trợ tuple comparison, viết điều kiện OR tương đương như phần 10.1.

### 12.3. Keyset không hỗ trợ nhảy tùy ý tới trang 500 dễ dàng

OFFSET có thể nhảy trực tiếp tới một vị trí nếu chấp nhận chi phí. Keyset cần biết cursor của trang trước. Để nhảy tới trang tùy ý, hệ thống phải có cursor checkpoint đã lưu, hoặc dùng một chiến lược khác.

Điều này không phải lỗi của keyset: nó được thiết kế để duyệt tuần tự ổn định và hiệu quả, không phải truy cập vị trí thứ N tùy ý.

## 13. Cursor token trong API phân trang

Một API keyset thường không yêu cầu client tự gửi từng cột sort. Server có thể trả `nextCursor` mã hóa từ khóa cuối trang.

Ví dụ response:

```json
{
  "items": [
    {
      "ticketId": 501,
      "title": "Không nhận email",
      "createdAt": "2026-10-01T09:30:00+07:00"
    }
  ],
  "nextCursor": "eyJjcmVhdGVkQXQiOiIyMDI2LTEwLTAxVDA5OjMwOjAwKzA3OjAwIiwidGlja2V0SWQiOjUwMX0",
  "hasMore": true
}
```

Cursor có thể chứa:

- Giá trị các cột sort của hàng cuối.
- Bộ lọc hoặc fingerprint của bộ lọc.
- Phiên bản cursor/API.
- Thời điểm snapshot hoặc watermark nếu thiết kế cần.
- Thông tin hết hạn.

### 13.1. Base64 không phải bảo mật

Base64 chỉ mã hóa biểu diễn, không giữ bí mật và không chống sửa đổi. Nếu client có thể thay ticket_id trong cursor để đọc tùy ý, server cần xác thực cursor.

Có thể dùng HMAC/signature để phát hiện cursor bị chỉnh sửa, hoặc mã hóa authenticated encryption nếu cursor chứa dữ liệu cần giữ kín. Dù cursor được ký, server vẫn phải xác thực quyền truy cập và áp dụng filter theo user/tenant ở mọi request.

### 13.2. Gắn cursor với bộ lọc và sort

Cursor tạo cho `status=open` không nên được dùng lại với `status=done` nếu điều kiện seek được tính theo tập khác. Tương tự, cursor của sort `created_at DESC` không hợp lệ cho sort `priority ASC`.

Server có thể lưu fingerprint của filter/sort trong cursor, hoặc tạo cursor có cấu trúc riêng theo từng query. Nếu chữ ký không khớp, trả lỗi cursor invalid/expired và yêu cầu bắt đầu lại.

### 13.3. Không đưa quyền truy cập vào cursor như bằng chứng duy nhất

Cursor không thay thế authorization. Client có thể đổi tenant/filter hoặc gửi cursor từ user khác. Server vẫn phải lấy tenant/user từ danh tính đã xác thực và áp dụng điều kiện truy cập độc lập.

## 14. Index hỗ trợ LIMIT, OFFSET và keyset

Giới hạn hàng không tự làm truy vấn nhanh. Một index phù hợp có thể giúp database tìm đúng thứ tự và dừng sau khi lấy đủ số hàng.

Giả sử truy vấn:

```sql
SELECT ticket_id, title, created_at
FROM tickets
WHERE status = 'open'
ORDER BY created_at DESC, ticket_id DESC
LIMIT 20;
```

Một index PostgreSQL có thể là:

```sql
CREATE INDEX idx_tickets_status_created_id
ON tickets (status, created_at DESC, ticket_id DESC);
```

Index bắt đầu bằng cột lọc equality `status`, sau đó theo các cột sort. DBMS có thể dùng index để tìm hàng open theo thứ tự cần thiết và dừng sớm khi đủ 20 hàng.

### 14.1. Thứ tự cột index quan trọng

Nếu filter theo `status` và sort theo `created_at`, index `(status, created_at)` có thể phù hợp hơn `(created_at, status)` cho một số workload. Nhưng không có quy tắc duy nhất: cardinality, điều kiện lọc, thứ tự sort, phân bố và các query khác đều ảnh hưởng.

### 14.2. Index có thể hỗ trợ cả ASC và DESC

B-tree có thể được quét theo chiều thuận hoặc ngược trong nhiều DBMS. Một index `(created_at ASC, ticket_id ASC)` có thể hỗ trợ truy vấn sort DESC bằng scan ngược khi cả hai cột đổi hướng cùng nhau. Với hướng sort hỗn hợp, index direction và khả năng scan của DBMS cần xem xét kỹ.

### 14.3. Keyset cần index khớp điều kiện seek

Truy vấn:

```sql
WHERE created_at < :last_created_at
   OR (
        created_at = :last_created_at
        AND ticket_id < :last_ticket_id
   )
ORDER BY created_at DESC, ticket_id DESC
FETCH FIRST 20 ROWS ONLY
```

thường được hỗ trợ bởi index trên `(created_at, ticket_id)` theo thứ tự tương ứng. Nếu còn filter equality như `status='open'`, cân nhắc `(status, created_at, ticket_id)`.

### 14.4. Partial index

PostgreSQL có thể dùng partial index khi truy vấn thường lọc một tập con:

```sql
CREATE INDEX idx_open_tickets_created
ON tickets (created_at DESC, ticket_id DESC)
WHERE status = 'open';
```

Index chỉ lưu hàng status open, có thể nhỏ hơn index toàn bảng. Điều kiện truy vấn phải tương thích với predicate để planner có thể sử dụng index.

### 14.5. SELECT chỉ những cột cần thiết

Không lấy `SELECT *` khi trang chỉ hiển thị vài trường. Hàng rộng làm tăng I/O, memory và dữ liệu truyền qua mạng. Nếu cần hiển thị title và ngày, chỉ chọn các cột ấy; index-only scan có thể có lợi trong một số trường hợp nhưng còn phụ thuộc visibility map, DBMS và index coverage.

### 14.6. Xem execution plan

PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ticket_id, title, created_at
FROM tickets
WHERE status = 'open'
ORDER BY created_at DESC, ticket_id DESC
LIMIT 20;
```

SQL Server có Actual Execution Plan; MySQL có EXPLAIN/EXPLAIN ANALYZE theo phiên bản; Oracle có execution plan và runtime statistics. Xem liệu có sort lớn, scan nhiều hàng, rows removed hoặc offset sâu gây tốn chi phí không.

`EXPLAIN ANALYZE` thực thi truy vấn. Dùng cẩn trọng với truy vấn đắt hoặc DML trên môi trường production.

## 15. COUNT và trang dữ liệu: hai truy vấn có thể nhìn thấy trạng thái khác nhau

Một giao diện số trang thường chạy hai câu:

```sql
SELECT COUNT(*)
FROM tickets
WHERE status = 'open';
```

và:

```sql
SELECT ticket_id, title
FROM tickets
WHERE status = 'open'
ORDER BY created_at DESC, ticket_id DESC
LIMIT 20 OFFSET 40;
```

Nếu có insert/delete giữa hai câu hoặc hai request, total count và page data có thể không mô tả cùng một trạng thái.

### 15.1. Có cần COUNT chính xác không?

Với admin table có nút “trang cuối”, tổng trang chính xác có thể quan trọng. Với feed/infinite scroll, chỉ cần `hasMore` có thể đủ.

Một kỹ thuật là lấy `pageSize + 1` hàng:

```sql
SELECT ticket_id, title, created_at
FROM tickets
WHERE status = 'open'
ORDER BY created_at DESC, ticket_id DESC
LIMIT 21;
```

Nếu lấy được 21 hàng, hiển thị 20 hàng đầu và đặt `hasMore=true`; nếu chỉ có tối đa 20 hàng, không còn trang sau theo snapshot của truy vấn đó.

Cách này tránh COUNT toàn tập cho mỗi request, nhưng không cung cấp `totalRows`/`totalPages` chính xác.

### 15.2. COUNT(*) OVER()

Một số DBMS hỗ trợ window count:

```sql
SELECT
    ticket_id,
    title,
    COUNT(*) OVER () AS total_rows
FROM tickets
WHERE status = 'open'
ORDER BY created_at DESC, ticket_id DESC
OFFSET 40 ROWS
FETCH NEXT 20 ROWS ONLY;
```

Mỗi hàng trả về mang theo tổng số hàng của tập đã lọc. Tuy nhiên, truy vấn có thể phải xử lý/tính tổng toàn tập, và nếu trang rỗng thì không có hàng nào để mang `total_rows`. Không mặc định cách này rẻ hơn một COUNT riêng.

### 15.3. Approximate count

Với dashboard dữ liệu rất lớn, có thể chấp nhận count ước lượng hoặc cập nhật theo cache/materialized summary. Phải công bố rõ đó là số xấp xỉ hoặc có độ trễ, không đặt nhãn “chính xác” nếu không đảm bảo.

## 16. Filter, DISTINCT, GROUP BY và LIMIT

LIMIT áp dụng lên kết quả của query block sau các phép toán logic có liên quan; vị trí đặt LIMIT trong subquery có thể làm thay đổi kết quả.

### 16.1. Lọc trước rồi giới hạn

```sql
SELECT ticket_id, title
FROM tickets
WHERE status = 'open'
ORDER BY created_at DESC, ticket_id DESC
LIMIT 20;
```

Đây là 20 ticket open mới nhất.

### 16.2. Giới hạn trước rồi lọc ngoài: kết quả khác

```sql
SELECT *
FROM (
    SELECT ticket_id, title, status, created_at
    FROM tickets
    ORDER BY created_at DESC, ticket_id DESC
    LIMIT 20
) AS newest
WHERE status = 'open';
```

Truy vấn này lấy 20 ticket mới nhất toàn bộ trước, rồi mới lọc open. Kết quả có thể ít hơn 20 và không giống truy vấn ở phần 16.1.

### 16.3. DISTINCT và LIMIT

```sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY customer_id
LIMIT 10;
```

Lấy tối đa 10 customer ID phân biệt. Nếu giới hạn hàng trước trong subquery rồi mới DISTINCT, có thể chỉ có ít giá trị distinct hơn và kết quả khác.

### 16.4. GROUP BY và LIMIT

```sql
SELECT customer_id, SUM(total_amount) AS revenue
FROM orders
GROUP BY customer_id
ORDER BY revenue DESC, customer_id
FETCH FIRST 10 ROWS ONLY;
```

Ở đây LIMIT/FETCH giới hạn **nhóm khách hàng sau khi aggregate**, không phải 10 order nguồn.

### 16.5. UNION và thứ tự cuối

Để lấy 10 hàng đầu từ hợp của hai tập:

```sql
SELECT id, label
FROM (
    SELECT id, label FROM source_a
    UNION ALL
    SELECT id, label FROM source_b
) AS combined
ORDER BY id
FETCH FIRST 10 ROWS ONLY;
```

`ORDER BY` cuối cùng định nghĩa thứ tự toàn bộ kết quả. LIMIT ở từng nhánh có thể thay đổi ngữ nghĩa, trừ khi đã chứng minh việc đẩy giới hạn xuống là tương đương theo yêu cầu.


## 17. Cùng một ứng dụng, nhiều SQL dialect

Nếu ứng dụng phải chạy trên PostgreSQL, MySQL, SQL Server và Oracle, không nên rải các đoạn nối chuỗi SQL khắp nơi rồi hy vọng mọi dialect hiểu giống nhau.

Một lớp truy vấn nên biết rõ dialect và tạo câu SQL theo DBMS đã cấu hình. Dữ liệu như page size/offset vẫn được bind qua PreparedStatement; tên cột sort cần chọn từ allowlist.

### 17.1. Bảng cú pháp thực dụng

| DBMS | Lấy N hàng đầu | Trang theo offset |
| --- | --- | --- |
| PostgreSQL | `LIMIT ?` hoặc `FETCH FIRST ? ROWS ONLY` | `LIMIT ? OFFSET ?` hoặc `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` |
| MySQL | `LIMIT ?` | `LIMIT ? OFFSET ?` |
| SQLite | `LIMIT ?` | `LIMIT ? OFFSET ?` |
| SQL Server 2012+ | `TOP (?)` hoặc OFFSET/FETCH từ đầu | `ORDER BY ... OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` |
| Oracle 12c+ | `FETCH FIRST ? ROWS ONLY` | `OFFSET ? ROWS FETCH NEXT ? ROWS ONLY` |
| Oracle cũ | Inline view + `ROWNUM`/`ROW_NUMBER()` | `ROW_NUMBER()` hoặc hai tầng ROWNUM |
| DB2 | `FETCH FIRST ? ROWS ONLY` theo phiên bản | Cú pháp OFFSET/FETCH theo phiên bản |

Đây là bảng định hướng. Cần kiểm tra phiên bản DBMS và JDBC driver về parameter marker trong row limiting clause, kiểu số và giới hạn giá trị.

### 17.2. Không bind tên cột bằng dấu hỏi

Đây là sai:

```sql
SELECT ticket_id, title
FROM tickets
ORDER BY ?;
```

Dấu hỏi bind một **giá trị**, không biến nó thành tên cột hoặc từ khóa ASC/DESC. Database có thể hiểu đó là một biểu thức hằng, không phải cột sort mà client muốn chọn.

Dùng allowlist:

```java
String sortColumn;

switch (requestedSort) {
    case "created":
        sortColumn = "created_at";
        break;
    case "priority":
        sortColumn = "priority";
        break;
    default:
        sortColumn = "ticket_id";
}
```

Direction cũng phải giới hạn bằng lựa chọn hợp lệ:

```java
String direction = requestedDescending ? "DESC" : "ASC";
```

Chỉ những fragment đã được ứng dụng chọn từ allowlist mới được nối vào SQL. Page size, offset và giá trị filter vẫn dùng bind parameters.

### 17.3. Ví dụ Java tạo SQL theo dialect

Mẫu minh họa:

```java
enum DatabaseDialect {
    POSTGRESQL,
    MYSQL,
    SQLITE,
    SQL_SERVER,
    ORACLE_12C
}

static String pageSql(DatabaseDialect dialect, String sortColumn) {
    // sortColumn phải đến từ allowlist, không phải input tùy ý.
    String order = " ORDER BY " + sortColumn + " DESC, ticket_id DESC";

    switch (dialect) {
        case POSTGRESQL:
        case MYSQL:
        case SQLITE:
            return "SELECT ticket_id, title, created_at " +
                   "FROM tickets" + order + " LIMIT ? OFFSET ?";

        case SQL_SERVER:
        case ORACLE_12C:
            return "SELECT ticket_id, title, created_at " +
                   "FROM tickets" + order +
                   " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY";

        default:
            throw new IllegalArgumentException("Unsupported dialect");
    }
}
```

Cách bind khác nhau theo dialect:

```java
try (PreparedStatement ps = conn.prepareStatement(sql)) {
    if (dialect == DatabaseDialect.POSTGRESQL
            || dialect == DatabaseDialect.MYSQL
            || dialect == DatabaseDialect.SQLITE) {
        ps.setInt(1, pageSize);
        ps.setLong(2, offset);
    } else {
        ps.setLong(1, offset);
        ps.setInt(2, pageSize);
    }

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Map một hàng kết quả.
        }
    }
}
```

Đây là khung đơn giản. Một abstraction production còn cần kiểm soát quoting identifier, schema, collation, NULL ordering, kiểu dữ liệu và cú pháp từng phiên bản. Không để dialect được chọn trực tiếp từ query parameter không tin cậy.

### 17.4. Oracle cũ cần một adapter riêng

Không thể thay `LIMIT ? OFFSET ?` bằng một từ khóa duy nhất trong Oracle phiên bản cũ. Có thể tạo query dùng `ROW_NUMBER()` và bind hai mốc:

```sql
SELECT ticket_id, title, created_at
FROM (
    SELECT
        ticket_id,
        title,
        created_at,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, ticket_id DESC
        ) AS rn
    FROM tickets
)
WHERE rn > ?
  AND rn <= ?
ORDER BY rn;
```

Bind offset vào tham số thứ nhất và offset + pageSize vào tham số thứ hai. Phải kiểm tra phép cộng không tràn số ở Java.

## 18. JDBC: triển khai truy vấn phân trang

### 18.1. OFFSET pagination bằng PreparedStatement

Ví dụ PostgreSQL/MySQL/SQLite:

```java
public List<Ticket> findPage(
        Connection conn,
        int page,
        int pageSize
) throws SQLException {

    if (page < 1) {
        throw new IllegalArgumentException("page must be >= 1");
    }
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize out of range");
    }

    long offset = Math.multiplyExact(
        (long) page - 1L,
        (long) pageSize
    );

    String sql =
        "SELECT ticket_id, title, created_at " +
        "FROM demo_batch_393.tickets " +
        "ORDER BY created_at DESC, ticket_id DESC " +
        "LIMIT ? OFFSET ?";

    List<Ticket> result = new ArrayList<>();

    try (PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setInt(1, pageSize);
        ps.setLong(2, offset);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                result.add(mapTicket(rs));
            }
        }
    }

    return result;
}
```

`Ticket` và `mapTicket` là model/mapper của ứng dụng. Ví dụ tập trung vào cách bind page size và offset; không yêu cầu tạo đúng class đó để hiểu cú pháp.

### 18.2. Keyset pagination bằng PreparedStatement

Với PostgreSQL, truy vấn dùng hai mốc:

```java
String sql =
    "SELECT ticket_id, title, created_at " +
    "FROM demo_batch_393.tickets " +
    "WHERE (created_at, ticket_id) < (?, ?) " +
    "ORDER BY created_at DESC, ticket_id DESC " +
    "LIMIT ?";

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setObject(1, lastCreatedAt);
    ps.setLong(2, lastTicketId);
    ps.setInt(3, pageSize + 1);

    try (ResultSet rs = ps.executeQuery()) {
        // Đọc tối đa pageSize + 1 hàng để suy ra hasMore.
    }
}
```

Dùng đúng kiểu Java/JDBC cho timestamp theo schema, ví dụ OffsetDateTime hoặc Timestamp tùy driver. `setObject()` hỗ trợ kiểu Java hiện đại tùy JDBC driver; nếu không tương thích, dùng phương thức setTimestamp/setObject tương ứng.

### 18.3. Không nhận sort expression tùy ý từ client

Client chỉ nên gửi một mã lựa chọn như `created` hoặc `priority`. Server ánh xạ mã đó sang fragment đã kiểm soát. Không nhận nguyên chuỗi `ORDER BY` từ request rồi nối vào SQL.

### 18.4. Page size + 1 để xác định hasMore

Nếu page size là 20, query lấy 21 hàng:

- Có 21 hàng: trả 20 hàng đầu, `hasMore=true`.
- Có 20 hàng hoặc ít hơn: trả tất cả, `hasMore=false`.
- Nếu có 0 hàng: trang hiện tại không có dữ liệu.

Không hiển thị hàng thứ 21 trong trang hiện tại; nó chỉ là dấu hiệu có trang tiếp theo.

## 19. Các vấn đề dữ liệu và API cần quyết định trước

### 19.1. Null ordering

PostgreSQL cho phép `NULLS FIRST`/`NULLS LAST`; các DBMS khác có quy tắc mặc định khác. Nếu một API hỗ trợ nhiều DBMS, phải định nghĩa rõ null ordering và chuyển sang cú pháp tương ứng.

### 19.2. Collation và thứ tự chữ

Sắp xếp chuỗi có thể khác nhau theo collation, locale, accent/case sensitivity và phiên bản ICU/database. Phân trang bằng tên sản phẩm có thể thay đổi khi collation hoặc dữ liệu thay đổi.

Nếu cần cursor ổn định, ưu tiên khóa sort đã chuẩn hóa hoặc khóa kỹ thuật có thứ tự xác định, đồng thời định nghĩa collation rõ.

### 19.3. Timezone và độ chính xác timestamp

Cursor có timestamp phải giữ đủ độ chính xác của database. Nếu database lưu microseconds nhưng API serialize chỉ milliseconds, mốc cursor có thể làm bỏ sót hoặc lặp hàng có timestamp sát nhau.

Dùng kiểu thời gian nhất quán, giữ timezone/offset rõ ràng và không làm tròn cursor khi serialize.

### 19.4. Filter phải giống nhau giữa các trang

Nếu trang đầu lọc `status='open'` nhưng trang sau quên filter hoặc cursor được dùng cho bộ lọc khác, tập kết quả thay đổi. Mọi request tiếp theo phải áp dụng cùng điều kiện nghiệp vụ và authorization.

### 19.5. Xử lý xóa và cập nhật trong khi duyệt

Keyset giảm dịch chuyển do insert trước cursor, nhưng không đảm bảo snapshot bất biến. Nếu hàng bị xóa trước khi client tới trang, hàng đó đơn giản không còn xuất hiện. Nếu cột sort bị sửa, hàng có thể chuyển vị trí.

Với báo cáo kiểm toán cần một tập cố định, có thể dùng snapshot, version/watermark, bảng kết quả được materialize hoặc lưu danh sách ID của lần chạy.

### 19.6. Previous và next cursor phải khác nhau

API có thể trả:

```json
{
  "items": [],
  "nextCursor": "...",
  "previousCursor": "...",
  "hasMore": true
}
```

Cursor next thường được xây từ hàng cuối trang; cursor previous được xây từ hàng đầu trang. Server phải giải mã, kiểm tra chữ ký và chọn hướng query đúng, sau đó đảo thứ tự khi cần.

### 19.7. Bảo vệ cursor và filter khỏi lạm dụng

- Ký cursor nếu client có thể sửa nội dung.
- Có hạn dùng nếu cursor không nên tồn tại lâu.
- Không nhúng dữ liệu bí mật ở dạng Base64 thuần.
- Kiểm tra quyền user/tenant mỗi lần gọi API.
- Giới hạn page size, timeout và số request.
- Không cho client tự chọn biểu thức SQL, cột hay hướng sort tùy ý.

## 20. Chọn chiến lược giới hạn hàng theo yêu cầu

Không có một phương pháp tốt nhất cho mọi màn hình. Hãy chọn theo cách người dùng duyệt và tính chất dữ liệu.

| Nhu cầu | Chiến lược phù hợp | Lý do |
| --- | --- | --- |
| Lấy 10 hàng đầu trong báo cáo nhỏ | LIMIT/FETCH/TOP với ORDER BY | Đơn giản, dễ hiểu |
| Giao diện có nút trang 1, 2, 3 và nhảy tới trang cuối | OFFSET pagination | Truy cập trang tùy ý trực tiếp |
| Bảng nhỏ, dữ liệu ít thay đổi | OFFSET pagination | Chi phí offset sâu không đáng kể |
| Feed liên tục, nút Load more | Keyset pagination | Không phải bỏ qua số lượng lớn hàng |
| Duyệt hàng triệu sự kiện theo thời gian | Keyset + index | Seek theo timestamp/ID |
| Bảng xếp hạng cần giữ mọi hàng đồng điểm | WITH TIES hoặc RANK | Không cắt ngang nhóm đồng hạng |
| Top 3 sản phẩm mỗi danh mục | ROW_NUMBER/RANK với PARTITION BY | Giới hạn theo từng nhóm |
| Báo cáo cần một snapshot cố định | Snapshot/version/materialized result | Các trang cùng phản ánh một tập dữ liệu |
| Hệ hỗ trợ nhiều DBMS | Query adapter theo dialect | Cú pháp giới hạn hàng khác nhau |

### 20.1. Câu hỏi quyết định

Trước khi viết SQL, xác định:

1. Người dùng cần trang có số thứ tự hay chỉ cần tải tiếp?
2. Có cần nhảy trực tiếp tới trang bất kỳ không?
3. Dữ liệu thay đổi thường xuyên không?
4. Có cần total count chính xác không?
5. Sort key có duy nhất và ổn định không?
6. Có NULL hoặc nhiều cột sort với hướng khác nhau không?
7. Có index hỗ trợ filter và order không?
8. Ứng dụng chạy trên DBMS/phiên bản nào?
9. Cursor có thể bị client sửa hoặc dùng sai filter không?
10. Có yêu cầu giữ snapshot bất biến qua nhiều request không?

### 20.2. Một số lựa chọn thực tế

- Admin dashboard nhỏ, cần trang 1–20 và nút “trang cuối”: OFFSET thường dễ dùng.
- Feed hoạt động mới nhất, người dùng cuộn liên tục: keyset thường phù hợp.
- Bảng top điểm cần lấy trọn đồng hạng: dùng WITH TIES/RANK, chấp nhận số hàng vượt giới hạn.
- Báo cáo pháp lý cần tập dữ liệu cố định: xác định snapshot hoặc materialize tập kết quả; chỉ dùng cursor không đủ bảo đảm bất biến.
- Ứng dụng đa DBMS: tách phần tạo cú pháp theo dialect, giữ filter/authorization và mô hình dữ liệu thống nhất.

## 21. Bài tập thực hành có đáp án

Các bài dùng cú pháp SQL và ví dụ trong tài liệu. Khi một câu hỏi nêu DBMS cụ thể, áp dụng đúng dialect của DBMS đó.

### Bài 1 — Không có ORDER BY

`SELECT * FROM tickets LIMIT 10` có bảo đảm trả về 10 ticket mới nhất không?

**Đáp án:** Không. LIMIT chỉ giới hạn số hàng; phải có ORDER BY xác định thứ tự, ví dụ created_at DESC, ticket_id DESC.

### Bài 2 — OFFSET bắt đầu từ đâu?

`LIMIT 20 OFFSET 0` bỏ qua bao nhiêu hàng?

**Đáp án:** Không bỏ hàng nào; OFFSET bắt đầu từ 0.

### Bài 3 — Trang thứ tư

Page size là 25, page đánh số từ 1. OFFSET bằng bao nhiêu?

**Đáp án:** (4 - 1) × 25 = 75.

### Bài 4 — MySQL LIMIT dạng hai tham số

`LIMIT 40, 20` có nghĩa gì?

**Đáp án:** Bỏ 40 hàng và trả tối đa 20 hàng; tương đương LIMIT 20 OFFSET 40.

### Bài 5 — FETCH FIRST

Viết truy vấn lấy 5 ticket theo ID tăng dần bằng FETCH.

**Đáp án:**

```sql
SELECT ticket_id, title
FROM tickets
ORDER BY ticket_id
FETCH FIRST 5 ROWS ONLY;
```

### Bài 6 — SQL Server TOP

Viết truy vấn lấy 10 đơn mới nhất.

**Đáp án:**

```sql
SELECT TOP (10) order_id, created_at
FROM dbo.orders
ORDER BY created_at DESC, order_id DESC;
```

### Bài 7 — TOP không có ORDER BY

`SELECT TOP (10) * FROM dbo.orders` có đảm bảo lấy 10 đơn gần nhất không?

**Đáp án:** Không. Cần ORDER BY với khóa sort xác định.

### Bài 8 — Oracle ROWNUM

Vì sao `WHERE ROWNUM <= 10 ORDER BY created_at DESC` trong cùng query block không phải cách tin cậy để lấy 10 hàng mới nhất?

**Đáp án:** ROWNUM được gán khi các hàng được chọn trong query block, nên có thể chọn 10 hàng trước rồi mới sort. Đưa ORDER BY vào inline view rồi giới hạn ở query ngoài.

### Bài 9 — ROW_NUMBER

Muốn lấy hàng 21 đến 30 theo created_at mới nhất trong Oracle cũ, dùng gì?

**Đáp án:** Tính ROW_NUMBER() OVER (ORDER BY created_at DESC, ticket_id DESC) trong subquery, rồi lọc rn BETWEEN 21 AND 30.

### Bài 10 — TOP-N-per-group

Muốn lấy 3 sản phẩm doanh thu cao nhất trong từng category, dùng LIMIT 3 toàn bảng được không?

**Đáp án:** Không. Dùng ROW_NUMBER() OVER (PARTITION BY category_id ORDER BY revenue DESC, product_id) rồi lọc rn <= 3.

### Bài 11 — ROW_NUMBER và RANK

Score là 100, 90, 90, 80. RANK cho kết quả nào?

**Đáp án:** 1, 2, 2, 4. DENSE_RANK cho 1, 2, 2, 3; ROW_NUMBER gán số riêng từng hàng.

### Bài 12 — WITH TIES

`FETCH FIRST 5 ROWS WITH TIES` có thể trả 7 hàng không?

**Đáp án:** Có, nếu các hàng thứ 6 và 7 đồng hạng với hàng thứ 5 theo toàn bộ biểu thức ORDER BY.

### Bài 13 — Tie-breaker

Vì sao phân trang theo created_at nên thêm ticket_id?

**Đáp án:** Nhiều hàng có thể cùng timestamp. Khóa duy nhất tạo thứ tự toàn phần ổn định và tránh trùng/bỏ hàng giữa trang.

### Bài 14 — OFFSET sâu

Vì sao OFFSET 500000 có thể chậm hơn OFFSET 0?

**Đáp án:** Database thường phải xác định và bỏ qua nhiều hàng/index entries trước khi trả page size; chi phí có thể tăng theo offset.

### Bài 15 — Chèn hàng giữa hai trang

Trang 1 lấy 20 hàng, sau đó một hàng mới được chèn lên đầu. OFFSET 20 có thể gây vấn đề gì?

**Đáp án:** Hàng ở cuối trang 1 cũ có thể dịch xuống vị trí 21 và xuất hiện lần nữa ở trang 2. OFFSET phân trang theo vị trí nên nhạy với thay đổi tập dữ liệu.

### Bài 16 — Keyset cursor

Sort created_at DESC, ticket_id DESC. Cursor cuối trang là (T, 100). Điều kiện trang sau?

**Đáp án:**

```sql
WHERE (created_at, ticket_id) < (:T, 100)
ORDER BY created_at DESC, ticket_id DESC
```

Trong DBMS không hỗ trợ tuple comparison, viết điều kiện OR tương đương.

### Bài 17 — Sort direction hỗn hợp

ORDER BY priority ASC, created_at DESC. Với cùng priority, hàng tiếp theo cần created_at lớn hơn hay nhỏ hơn mốc?

**Đáp án:** Nhỏ hơn mốc vì created_at được sắp DESC; priority lớn hơn mốc cũng đứng sau do priority ASC.

### Bài 18 — NULL trong keyset

Tại sao không thể chỉ viết due_at = :last_due_at nếu due_at có thể NULL?

**Đáp án:** So sánh với NULL trả UNKNOWN. Cần xử lý nhánh IS NULL riêng và định nghĩa NULLS FIRST/LAST rõ ràng.

### Bài 19 — Base64 cursor

Base64 có ngăn client sửa ticket_id trong cursor không?

**Đáp án:** Không. Base64 không phải chữ ký/bảo mật; dùng HMAC/signature hoặc authenticated encryption khi phù hợp và vẫn kiểm tra authorization server-side.

### Bài 20 — Index cho truy vấn

Query lọc status='open' rồi sort created_at DESC, ticket_id DESC. Index nào có thể hữu ích?

**Đáp án:** Một lựa chọn PostgreSQL là (status, created_at DESC, ticket_id DESC); cần kiểm tra execution plan và workload thực tế.

### Bài 21 — COUNT hay pageSize + 1

Một feed infinite scroll chỉ cần biết còn dữ liệu không. Có nhất thiết COUNT(*) mỗi request không?

**Đáp án:** Không. Lấy pageSize + 1 hàng; nếu có hàng thừa thì hasMore=true. Cách này không trả totalPages chính xác.

### Bài 22 — COUNT(*) OVER()

Trang cuối rỗng, truy vấn COUNT(*) OVER() gắn tổng số hàng vào từng dòng sẽ trả tổng count qua dòng nào?

**Đáp án:** Không có dòng nào để mang total_rows. Có thể cần COUNT riêng hoặc cách lưu metadata khác.

### Bài 23 — Filter trước hay LIMIT trước?

Muốn 20 ticket open mới nhất, truy vấn nào đúng: lọc status trước LIMIT hay lấy 20 hàng mới nhất rồi lọc ngoài?

**Đáp án:** Lọc status trước rồi ORDER BY/LIMIT. Giới hạn trước rồi lọc ngoài có thể trả ít hơn 20 hàng và là tập khác.

### Bài 24 — GROUP BY

`GROUP BY customer_id ORDER BY SUM(total) DESC FETCH FIRST 10` giới hạn 10 hàng nguồn hay 10 nhóm?

**Đáp án:** 10 nhóm khách hàng sau aggregate.

### Bài 25 — JDBC parameter

Có thể dùng `ORDER BY ?` để bind tên cột sort từ request không?

**Đáp án:** Không. Parameter marker bind giá trị, không thay tên cột. Dùng allowlist cho fragment sort và bind các giá trị dữ liệu.

### Bài 26 — Page size không hợp lệ

Client gửi pageSize = 1.000.000. Server nên làm gì?

**Đáp án:** Kiểm tra và giới hạn page size theo chính sách; không để client tùy ý tạo truy vấn trả quá nhiều hàng.

### Bài 27 — Timestamp cursor

Database lưu timestamp microseconds, nhưng API làm tròn cursor về milliseconds. Rủi ro?

**Đáp án:** Các hàng có timestamp gần nhau có thể bị bỏ sót hoặc lặp do mốc cursor không còn chính xác. Giữ đủ precision và timezone.

### Bài 28 — Cursor và authorization

Client gửi cursor thuộc tenant khác. Chỉ xác minh chữ ký cursor có đủ không?

**Đáp án:** Không. Server vẫn phải xác thực user/tenant hiện tại và áp dụng điều kiện truy cập độc lập ở mọi request.

### Bài 29 — Snapshot qua nhiều trang

Keyset có bảo đảm mọi trang phản ánh một snapshot bất biến khi dữ liệu bị cập nhật không?

**Đáp án:** Không. Keyset giảm dịch chuyển do insert trước cursor nhưng không đóng băng tập kết quả. Cần snapshot/version/materialized result nếu nghiệp vụ yêu cầu bất biến.

### Bài 30 — Chọn phương pháp

Một feed có hàng triệu sự kiện, sort theo thời điểm tạo và ID duy nhất, người dùng chỉ tải tiếp. Chọn gì?

**Đáp án:** Keyset pagination với index phù hợp trên khóa sort, cursor giữ đủ timestamp/ID và pageSize + 1 để biết hasMore.

### Bài 31 — Chọn OFFSET

Một màn hình admin có 500 hàng, người dùng thường nhảy trực tiếp tới trang 3. Chọn gì?

**Đáp án:** OFFSET pagination thường đơn giản và đủ hiệu quả ở quy mô này, với ORDER BY ổn định.

### Bài 32 — Giữ đồng hạng

Bảng xếp hạng cần giữ tất cả người cùng điểm với người ở vị trí thứ 10. Chọn gì?

**Đáp án:** FETCH ... WITH TIES hoặc RANK phù hợp, không thêm khóa duy nhất vào biểu thức xác định ties nếu muốn giữ cùng điểm.

### Bài 33 — Oracle cũ và mới

Ứng dụng Oracle 11g có thể dùng FETCH FIRST giống Oracle 19c không?

**Đáp án:** Không. Oracle 11g thường dùng ROWNUM/ROW_NUMBER; row limiting clause FETCH/OFFSET có từ Oracle 12c.

### Bài 34 — Đa hệ quản trị

Một câu LIMIT chạy trên PostgreSQL, MySQL và SQL Server nguyên trạng không?

**Đáp án:** Không. SQL Server thường dùng TOP hoặc OFFSET/FETCH; cần adapter/dialect riêng.

### Bài 35 — Dữ liệu thay đổi

Ứng dụng cần báo cáo pháp lý có danh sách cố định dù dữ liệu live thay đổi. Chỉ dùng keyset có đủ không?

**Đáp án:** Không. Cần snapshot/version hoặc materialize tập kết quả, vì keyset không tự bảo đảm một snapshot bất biến qua nhiều request.

## 22. Checklist thiết kế phân trang

1. Có ORDER BY ở query ngoài cùng không?
2. Thứ tự có đủ duy nhất bằng tie-breaker không?
3. LIMIT/FETCH/TOP có đúng dialect và phiên bản DBMS không?
4. OFFSET có được tính từ page đánh số 1 đúng công thức không?
5. Page size có được kiểm tra và giới hạn ở server không?
6. Sort column/direction có được chọn từ allowlist không?
7. Keyset có điều kiện seek tương ứng từng hướng ASC/DESC không?
8. NULLS FIRST/LAST có được xác định rõ không?
9. Timestamp cursor có giữ precision và timezone không?
10. Filter và authorization có nhất quán giữa các request không?
11. Cursor có gắn với filter/sort và được ký khi cần không?
12. Có kiểm tra quyền user/tenant mỗi lần gọi API không?
13. Query có index hỗ trợ filter và order không?
14. Có đo OFFSET ở trang sâu không?
15. Có cần total count chính xác hay chỉ hasMore?
16. COUNT và page data có yêu cầu cùng snapshot không?
17. Có xử lý trang ngoài phạm vi và kết quả rỗng không?
18. Có dùng WITH TIES đúng khi cần giữ đồng hạng không?
19. Có phân biệt Top-N toàn bảng với Top-N-per-group không?
20. Có kiểm thử dữ liệu được insert/update/delete giữa các lần tải trang không?
21. Có kiểm thử collation và NULL trên từng DBMS không?
22. Có xem execution plan bằng dữ liệu đại diện không?
23. Có kiểm thử parameter binding bằng đúng JDBC driver không?
24. Có tránh SELECT * và giới hạn payload trả về không?
25. Nếu cần snapshot bất biến, có snapshot/version/materialized result không?

## 23. Tổng kết

`LIMIT`, `FETCH FIRST`, `TOP`, `ROWNUM` và `ROW_NUMBER()` đều có thể giúp giới hạn số hàng, nhưng chúng thuộc những dialect và ngữ nghĩa khác nhau. PostgreSQL/MySQL/SQLite thường dùng LIMIT; SQL Server có TOP và OFFSET/FETCH; Oracle 12c+ có row limiting clause, còn Oracle cũ thường dùng ROWNUM hoặc ROW_NUMBER.

**ORDER BY là điều kiện cốt lõi của kết quả có ý nghĩa.** Khi chia trang, thứ tự cần đủ duy nhất để các hàng không bị trùng hoặc bỏ sót chỉ vì đồng hạng. OFFSET dễ triển khai và hỗ trợ nhảy tới trang tùy ý, nhưng trang sâu có thể tốn kém và nhạy với insert/delete giữa các request. Keyset dùng khóa cuối trang trước làm mốc, thường hiệu quả hơn khi duyệt tuần tự dữ liệu lớn, nhưng cần cursor đúng, index phù hợp và không tự tạo snapshot bất biến.

Một ứng dụng đa hệ quản trị nên tách cú pháp theo dialect, bind page size/offset/cursor bằng PreparedStatement, dùng allowlist cho cột sort, giới hạn page size và kiểm tra quyền truy cập ở server. Chọn pagination dựa trên cách người dùng duyệt, mức thay đổi dữ liệu, yêu cầu count/snapshot và kế hoạch thực thi thực tế.




