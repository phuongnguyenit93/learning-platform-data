# Vị trí NULL và NULLS FIRST hoặc NULLS LAST theo phương ngữ SQL

Khi sắp xếp bằng `ORDER BY`, người học thường quen với hai hướng: `ASC` (tăng dần) và `DESC` (giảm dần). Tuy nhiên, một cột có thể chứa **`NULL`**, nghĩa là giá trị chưa biết hoặc chưa được cung cấp. Lúc ấy câu hỏi “`NULL` đứng trước hay sau những giá trị đã biết?” không có câu trả lời chung cho mọi hệ quản trị cơ sở dữ liệu.

Ví dụ, giao diện quản lý công việc cần hiển thị các nhiệm vụ có **ngày đến hạn gần nhất lên đầu**, còn nhiệm vụ **chưa có ngày đến hạn xuống cuối**. Truy vấn `ORDER BY due_on ASC` trông có vẻ đủ, nhưng trên PostgreSQL và MySQL có thể cho vị trí `NULL` khác nhau. Nếu giao diện có phân trang, thứ tự không nhất quán còn dẫn tới hiện tượng các dòng xuất hiện ở trang không mong muốn.

Bài học này giải thích cách SQL xử lý `NULL` khi sắp xếp, cú pháp `NULLS FIRST`/`NULLS LAST`, khác biệt giữa các phương ngữ và cách viết truy vấn có thể chuyển đổi qua nhiều DBMS. Cuối bài có ví dụ phân trang và lựa chọn chỉ mục để bảo đảm kết quả nhất quán.

> Ví dụ chính dùng PostgreSQL. Bảng so sánh đề cập PostgreSQL, Oracle Database, MySQL/MariaDB, SQL Server và SQLite. **Cú pháp và hành vi cần được kiểm tra với phiên bản DBMS thật sự đang sử dụng**; đừng giả định cùng một câu `ORDER BY` sẽ cho cùng thứ tự `NULL` trên tất cả hệ.

## 1. `NULL` không phải là giá trị nhỏ nhất hay lớn nhất

`NULL` không đại diện cho số `0`, chuỗi rỗng `''` hoặc một giá trị đặc biệt như `-1`. Nó mô tả **không có giá trị xác định** theo ý nghĩa của cột. Vì vậy, không thể suy luận vị trí của nó trong thứ tự số hay ngày theo một phép so sánh thông thường.

Ví dụ:

```sql
-- PostgreSQL: phép so sánh với NULL cho UNKNOWN,
-- thường được hiển thị thành NULL kiểu boolean.
SELECT
    10 < NULL::INTEGER AS less_than_null,
    10 > NULL::INTEGER AS greater_than_null,
    10 = NULL::INTEGER AS equal_to_null;
```

Cả ba biểu thức đều không cho `TRUE` hoặc `FALSE`; chúng có kết quả logic **`UNKNOWN`**. Để phát hiện giá trị thiếu, dùng `IS NULL`:

```sql
SELECT 10 IS NULL AS ten_is_null;
-- FALSE
```

Vậy tại sao `ORDER BY` vẫn có thể xếp các dòng chứa `NULL`? Vì **sắp xếp có quy tắc đặt giá trị thiếu riêng**, không nhất thiết dựa vào kết quả của các phép `<`, `>` hoặc `=` với `NULL`. DBMS quyết định mặc định hoặc cho phép người viết truy vấn chỉ định rõ.

Ba khái niệm phải tách bạch:

- **Hướng sắp xếp**: giá trị khác `NULL` tăng hay giảm theo `ASC`/`DESC`.
- **Vị trí `NULL`**: các dòng chứa `NULL` đứng trước hay sau các giá trị khác `NULL`.
- **Thứ tự giữa các dòng bằng nhau**: nếu nhiều dòng có cùng giá trị, bao gồm nhiều `NULL`, phải có khóa sắp xếp phụ nếu cần thứ tự xác định.

## 2. Bảng dữ liệu mẫu

Giả sử hệ thống quản lý công việc có mức ưu tiên `priority` và ngày hạn `due_on`. Số ưu tiên càng nhỏ thì công việc càng quan trọng; `NULL` nghĩa là chưa có mức ưu tiên. `due_on IS NULL` nghĩa là chưa đặt hạn.

Tạo bảng tạm và chèn dữ liệu trong PostgreSQL:

```sql
CREATE TEMP TABLE demo_tickets (
    ticket_id INTEGER PRIMARY KEY,
    title VARCHAR(80) NOT NULL,
    priority INTEGER,
    due_on DATE
);

INSERT INTO demo_tickets (ticket_id, title, priority, due_on)
VALUES
    (101, 'Fix login',       2, DATE '2026-11-17'),
    (102, 'Review copy',    NULL, NULL),
    (103, 'Patch outage',    1, DATE '2026-11-16'),
    (104, 'Update docs',     2, NULL),
    (105, 'Research idea', NULL, DATE '2026-11-19'),
    (106, 'Clean logs',      3, DATE '2026-11-14'),
    (107, 'Handle alert',    1, NULL),
    (108, 'Refine UI',       3, DATE '2026-11-15');
```

Dữ liệu gốc:

| ticket_id | title | priority | due_on |
|---:|---|---:|---|
| 101 | Fix login | 2 | 2026-11-17 |
| 102 | Review copy | `NULL` | `NULL` |
| 103 | Patch outage | 1 | 2026-11-16 |
| 104 | Update docs | 2 | `NULL` |
| 105 | Research idea | `NULL` | 2026-11-19 |
| 106 | Clean logs | 3 | 2026-11-14 |
| 107 | Handle alert | 1 | `NULL` |
| 108 | Refine UI | 3 | 2026-11-15 |

Có 8 dòng, trong đó `priority` có **hai giá trị `NULL`** (ID 102, 105) và `due_on` có **ba giá trị `NULL`** (ID 102, 104, 107).

Các ví dụ sẽ thêm `ticket_id ASC` làm tiêu chí cuối cùng. Đây là khóa duy nhất giúp xác định thứ tự khi hai công việc có cùng ưu tiên hoặc cùng trạng thái `NULL`. Nếu bỏ khóa phụ, DBMS **không bảo đảm** ID nào xuất hiện trước trong một nhóm có cùng giá trị sắp xếp.

## 3. `ASC` và `DESC` chưa xác định hết ý nghĩa sắp xếp

`ASC` đặt các giá trị *khác `NULL`* theo hướng tăng dần, chẳng hạn mức ưu tiên `1, 2, 3`. `DESC` đặt chúng theo hướng giảm dần, chẳng hạn `3, 2, 1`.

Xét hai câu lệnh:

```sql
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority ASC, ticket_id ASC;

SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority DESC, ticket_id ASC;
```

Thứ tự tương đối của các nhóm giá trị đã biết thì rõ ràng. Nhưng hai dòng ID 102 và 105 có `priority IS NULL` có thể đứng ở đầu hoặc cuối **tùy DBMS**.

Điều này cũng đúng với `DATE`, `TIMESTAMP`, kiểu văn bản và nhiều kiểu khác có thể chứa `NULL`. Vị trí `NULL` không được quyết định bằng cách coi nó là ngày sớm nhất hay chuỗi rỗng.

### 3.1. Mặc định phổ biến của các phương ngữ

| Hệ quản trị | `ORDER BY col ASC` | `ORDER BY col DESC` | Hỗ trợ viết `NULLS FIRST / NULLS LAST`? |
|---|---|---|---|
| **PostgreSQL** | `NULL` **cuối** | `NULL` **đầu** | Có |
| **Oracle Database** | `NULL` **cuối** | `NULL` **đầu** | Có |
| **MySQL** | `NULL` **đầu** | `NULL` **cuối** | Không dùng trực tiếp cú pháp này trong các phiên bản MySQL thông dụng |
| **MariaDB** | `NULL` **đầu** | `NULL` **cuối** | Thường dùng biểu thức thay thế, không dùng cú pháp PostgreSQL |
| **SQL Server** | `NULL` **đầu** | `NULL` **cuối** | Thường dùng `CASE` để mô phỏng |
| **SQLite** | `NULL` **đầu** | `NULL` **cuối** | Có từ SQLite **3.30.0** |

Với `ASC`, PostgreSQL/Oracle thường xem `NULL` như phần tử nằm sau các giá trị thông thường, còn MySQL/SQL Server/SQLite đặt nó trước. Với `DESC`, vị trí mặc định thường đảo lại.

**Điều quan trọng:** Đây là **hành vi của các hệ quản trị**, không phải quy tắc rằng `NULL` có thể so sánh lớn hơn/nhỏ hơn số hay ngày. Cần kiểm tra đúng phiên bản/edition và tham khảo tài liệu DBMS khi triển khai, nhất là với tính năng hoặc phiên bản mới.

### 3.2. Cùng một dữ liệu, thứ tự mặc định khác nhau

Với truy vấn:

```sql
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority ASC, ticket_id ASC;
```

- **PostgreSQL/Oracle**: `103, 107, 101, 104, 106, 108, 102, 105`. Nhóm `NULL` đứng cuối.
- **MySQL/MariaDB/SQL Server/SQLite**: `102, 105, 103, 107, 101, 104, 106, 108`. Nhóm `NULL` đứng đầu.

Với `priority DESC, ticket_id ASC`:

- **PostgreSQL/Oracle**: `102, 105, 106, 108, 101, 104, 103, 107`.
- **MySQL/MariaDB/SQL Server/SQLite**: `106, 108, 101, 104, 103, 107, 102, 105`.

Phần sau sẽ viết lại các truy vấn này với **vị trí `NULL` tường minh**, giúp thống nhất kết quả.

## 4. Cú pháp `NULLS FIRST` và `NULLS LAST`

Trên các DBMS hỗ trợ, ta đặt `NULLS FIRST` hoặc `NULLS LAST` **ngay sau hướng sắp xếp của biểu thức tương ứng**:

```sql
ORDER BY expression ASC  NULLS FIRST
ORDER BY expression ASC  NULLS LAST
ORDER BY expression DESC NULLS FIRST
ORDER BY expression DESC NULLS LAST
```

- `NULLS FIRST`: các giá trị `NULL` xuất hiện **trước** mọi giá trị khác `NULL` của biểu thức đó.
- `NULLS LAST`: các giá trị `NULL` xuất hiện **sau** mọi giá trị khác `NULL` của biểu thức đó.
- `ASC`/`DESC`: xác định thứ tự **trong nhóm giá trị đã biết**.
- Một danh sách `ORDER BY` có nhiều biểu thức có thể đặt quy tắc `NULL` **riêng cho từng biểu thức**, nếu phương ngữ hỗ trợ.

### 4.1. Tăng dần, `NULL` cuối

Mục tiêu: ưu tiên `1` rồi `2` rồi `3`; các công việc chưa đặt mức ưu tiên ở cuối.

```sql
-- PostgreSQL, Oracle hoặc SQLite >= 3.30.0
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC;
```

Kết quả theo `ticket_id`:

```text
103, 107, 101, 104, 106, 108, 102, 105
```

| Thứ tự | ticket_id | priority |
|---:|---:|---:|
| 1 | 103 | 1 |
| 2 | 107 | 1 |
| 3 | 101 | 2 |
| 4 | 104 | 2 |
| 5 | 106 | 3 |
| 6 | 108 | 3 |
| 7 | 102 | `NULL` |
| 8 | 105 | `NULL` |

`ticket_id ASC` chỉ sắp bên trong các nhóm có `priority` giống nhau. Hai dòng `priority = 1` có thứ tự 103 rồi 107; hai dòng `NULL` có thứ tự 102 rồi 105.

### 4.2. Tăng dần, `NULL` đầu

Mục tiêu: đưa các công việc **chưa phân loại ưu tiên** lên đầu để nhân viên bổ sung thông tin, rồi mới hiển thị `1, 2, 3`.

```sql
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY priority ASC NULLS FIRST, ticket_id ASC;
```

Thứ tự: **102, 105, 103, 107, 101, 104, 106, 108**.

`NULLS FIRST` đặc biệt hữu ích trong những màn hình **kiểm tra chất lượng dữ liệu**, nơi bản ghi chưa có giá trị cần được xử lý trước. Lúc này đưa `NULL` lên đầu là yêu cầu nghiệp vụ, không phải lỗi sắp xếp.

### 4.3. Giảm dần, `NULL` cuối

Mục tiêu: hiển thị `3, 2, 1` rồi mới đến nhóm chưa xác định:

```sql
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY priority DESC NULLS LAST, ticket_id ASC;
```

Thứ tự: **106, 108, 101, 104, 103, 107, 102, 105**.

Dù `DESC` đưa các giá trị thông thường từ lớn xuống nhỏ, `NULLS LAST` vẫn giữ nhóm `NULL` ở cuối. **Hướng số và vị trí `NULL` là hai quyết định độc lập**.

### 4.4. Giảm dần, `NULL` đầu

```sql
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY priority DESC NULLS FIRST, ticket_id ASC;
```

Thứ tự: **102, 105, 106, 108, 101, 104, 103, 107**.

Bảng tóm tắt cả bốn trường hợp trên dữ liệu mẫu:

| Cách sắp | Các nhóm theo thứ tự | ID theo thứ tự |
|---|---|---|
| `ASC NULLS FIRST` | `NULL`, 1, 2, 3 | 102, 105, 103, 107, 101, 104, 106, 108 |
| `ASC NULLS LAST` | 1, 2, 3, `NULL` | 103, 107, 101, 104, 106, 108, 102, 105 |
| `DESC NULLS FIRST` | `NULL`, 3, 2, 1 | 102, 105, 106, 108, 101, 104, 103, 107 |
| `DESC NULLS LAST` | 3, 2, 1, `NULL` | 106, 108, 101, 104, 103, 107, 102, 105 |

Nếu bỏ `ASC` và `DESC`, `ASC` thường là mặc định; nhưng khi cần điều khiển `NULL` rõ ràng, nên ghi đủ cả hướng và quy tắc `NULL` để người đọc hiểu nhanh.

## 5. Nhiều cột trong `ORDER BY`: chỉ định `NULL` theo từng khóa

Một truy vấn thực tế thường sắp theo nhiều yếu tố, ví dụ:

1. Ngày đến hạn gần nhất lên trước.
2. Những công việc **chưa có ngày hạn** xuống cuối.
3. Nếu cùng ngày hạn, mức ưu tiên nhỏ hơn được xử lý trước.
4. Nếu cả ngày hạn và ưu tiên đều giống nhau, dùng ID tăng dần.

Có thể viết trong PostgreSQL:

```sql
SELECT ticket_id, title, due_on, priority
FROM demo_tickets
ORDER BY
    due_on ASC NULLS LAST,
    priority ASC NULLS LAST,
    ticket_id ASC;
```

Thứ tự ID theo dữ liệu mẫu: **106, 108, 103, 101, 105, 107, 104, 102**.

Giải thích:

- Các ngày khác `NULL` xuất hiện từ 14/11 đến 19/11: 106, 108, 103, 101, 105.
- Các công việc chưa có ngày hạn (107, 104, 102) xuống cuối.
- Bên trong nhóm `due_on IS NULL`, mức ưu tiên `1` (ID 107) trước `2` (ID 104), sau đó mới `priority IS NULL` (ID 102).
- `ticket_id` là khóa cuối cùng để phân định những dòng bằng nhau trên mọi khóa trước đó.

Cú pháp `NULLS LAST` sau `due_on` **không tự áp dụng** cho `priority`; muốn quy tắc đó trên `priority` cũng phải viết ra. Mỗi thành phần của danh sách `ORDER BY` độc lập về hướng và chính sách vị trí `NULL`.

Một biến thể khác: “công việc chưa có hạn cần xử lý trước, rồi ưu tiên thấp số được chọn trước”:

```sql
SELECT ticket_id, title, due_on, priority
FROM demo_tickets
ORDER BY
    due_on ASC NULLS FIRST,
    priority ASC NULLS LAST,
    ticket_id ASC;
```

Ở đây nhóm `due_on IS NULL` sẽ đứng trước toàn bộ ngày đã xác định; trong nhóm ấy vẫn sắp theo `priority`. **Thứ tự ưu tiên giữa các khóa quan trọng hơn cách riêng từng cột đặt `NULL`.**

### 5.1. `ORDER BY` không có `WHERE` thì không loại `NULL`

`ORDER BY due_on ASC NULLS LAST` giữ toàn bộ công việc và chỉ đổi **vị trí** hiển thị.

Ngược lại:

```sql
SELECT ticket_id, due_on
FROM demo_tickets
WHERE due_on IS NOT NULL
ORDER BY due_on ASC, ticket_id ASC;
```

là truy vấn **loại bỏ các dòng chưa có ngày hạn** khỏi kết quả. Hai quyết định nghiệp vụ khác nhau:

- “Chưa có ngày hạn nằm ở cuối danh sách” → sắp xếp bằng `NULLS LAST`.
- “Chỉ hiển thị công việc đã có hạn” → lọc bằng `WHERE due_on IS NOT NULL`.

Đừng dùng `WHERE` để giải quyết yêu cầu thuần túy về hiển thị vị trí khi các dòng thiếu dữ liệu vẫn cần có mặt.

## 6. Phương ngữ không hỗ trợ `NULLS FIRST/LAST`: dùng `CASE`

MySQL/MariaDB và SQL Server trong những phiên bản thông dụng **không chấp nhận trực tiếp** câu `ORDER BY priority ASC NULLS LAST` như PostgreSQL/Oracle/SQLite mới. Một cách diễn đạt rộng rãi giữa các DBMS là tạo **khóa sắp xếp phụ** bằng `CASE` để phân loại “có giá trị” và “`NULL`”.

### 6.1. `NULL` cuối, giá trị tăng dần

```sql
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END ASC,
    priority ASC,
    ticket_id ASC;
```

Giải thích thứ tự:

1. Biểu thức `CASE` trả `0` cho giá trị đã biết và `1` cho `NULL`.
2. `ORDER BY ... ASC` với `CASE` đặt nhóm `0` trước nhóm `1`, nên **mọi `NULL` xuống cuối**.
3. Trong nhóm đã biết (`0`), sắp `priority ASC`.
4. Trong từng nhóm có cùng `priority`, sắp `ticket_id ASC`.

Thứ tự ID là **103, 107, 101, 104, 106, 108, 102, 105**, cùng ý định với `ASC NULLS LAST`.

Đây là một mẫu dễ chuyển qua nhiều DBMS vì dùng `CASE WHEN` và `IS NULL` theo SQL thông dụng.

### 6.2. `NULL` đầu, giá trị tăng dần

Đảo vai trò `0` và `1`:

```sql
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY
    CASE WHEN priority IS NULL THEN 0 ELSE 1 END ASC,
    priority ASC,
    ticket_id ASC;
```

Thứ tự: **102, 105, 103, 107, 101, 104, 106, 108**.

Có thể giữ biểu thức `CASE WHEN ... THEN 1 ELSE 0 END` và sắp `DESC` thay vì đảo giá trị, nhưng nhất quán một cách viết giúp dễ đọc hơn.

### 6.3. `NULL` cuối, giá trị giảm dần

```sql
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END ASC,
    priority DESC,
    ticket_id ASC;
```

Thứ tự: **106, 108, 101, 104, 103, 107, 102, 105**.

Chú ý **không đổi `CASE` thành `DESC` chỉ vì chuyển `priority ASC` sang `DESC`**. `CASE` vẫn kiểm soát `NULL` cuối; hướng của `priority` kiểm soát thứ tự các số.

### 6.4. `NULL` đầu, giá trị giảm dần

```sql
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY
    CASE WHEN priority IS NULL THEN 0 ELSE 1 END ASC,
    priority DESC,
    ticket_id ASC;
```

Thứ tự: **102, 105, 106, 108, 101, 104, 103, 107**.

Các biến thể `CASE` đều kiểm soát **vị trí `NULL` độc lập với hướng sắp dữ liệu**. Dù thiếu cú pháp `NULLS FIRST/LAST`, ứng dụng vẫn có thể thể hiện ý định rõ ràng.

### 6.5. Thay thế cho nhiều cột

Đối với yêu cầu ngày đến hạn tăng dần, `NULL` cuối; ưu tiên tăng dần, `NULL` cuối; ID tăng dần:

```sql
SELECT ticket_id, title, due_on, priority
FROM demo_tickets
ORDER BY
    CASE WHEN due_on IS NULL THEN 1 ELSE 0 END,
    due_on ASC,
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END,
    priority ASC,
    ticket_id ASC;
```

Truy vấn này mang cùng ý nghĩa với ví dụ `ORDER BY due_on ASC NULLS LAST, priority ASC NULLS LAST, ticket_id ASC` ở DBMS hỗ trợ.

Chú ý vị trí của hai biểu thức `CASE`: `CASE` cho `due_on` nằm **trước** ngày hạn, còn `CASE` cho `priority` nằm **sau** ngày hạn và **trước** mức ưu tiên. Nếu đặt mọi `CASE` ở đầu, ví dụ ưu tiên mọi hàng có `priority` khác `NULL` trước khi xét ngày hạn, bạn đã thay đổi thứ tự ưu tiên giữa các cột và có thể nhận kết quả khác.

## 7. Cú pháp ngắn theo từng hệ quản trị

### 7.1. PostgreSQL

PostgreSQL hỗ trợ tường minh `NULLS FIRST`/`NULLS LAST` trong `ORDER BY`:

```sql
-- Ưu tiên tăng dần, chưa biết ở cuối.
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC;

-- Ưu tiên giảm dần, chưa biết ở cuối.
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority DESC NULLS LAST, ticket_id ASC;
```

Mặc định PostgreSQL đặt `NULL` cuối khi `ASC`, đầu khi `DESC`. Viết rõ quy tắc vẫn hữu ích để truy vấn tự thể hiện ý định và dễ chuyển sang hệ khác.

Có thể dùng biểu thức boolean để phân nhóm:

```sql
-- PostgreSQL hỗ trợ sắp xếp boolean: FALSE đứng trước TRUE khi ASC.
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY (priority IS NULL) ASC, priority ASC, ticket_id ASC;
```

Cách này có kết quả `NULL` cuối, nhưng không phải cú pháp portable tối ưu cho mọi DBMS; `CASE` dễ dùng liên hệ hơn khi cần SQL Server/Oracle cũ.

### 7.2. Oracle Database

Oracle hỗ trợ `NULLS FIRST` và `NULLS LAST`, với mặc định tương tự PostgreSQL:

```sql
-- Trong Oracle, giả sử đã có bảng tickets cùng cấu trúc cột.
SELECT ticket_id, priority
FROM tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC;
```

Không mặc định lấy DDL `CREATE TEMP TABLE` của PostgreSQL áp dụng trực tiếp cho Oracle; ví dụ trên chỉ minh họa cú pháp `ORDER BY`.

### 7.3. MySQL và MariaDB

Ở MySQL/MariaDB, `NULL` thường đứng đầu với `ASC` và cuối với `DESC`. Để đưa `NULL` cuối **khi tăng dần**, có thể dùng biểu thức kiểm tra `IS NULL`:

```sql
-- MySQL / MariaDB; tickets là bảng cùng cột.
SELECT ticket_id, priority
FROM tickets
ORDER BY (priority IS NULL) ASC, priority ASC, ticket_id ASC;
```

Trong ngữ cảnh này, biểu thức `priority IS NULL` cho giá trị logic được dùng như 0/1 khi sắp xếp: giá trị đã biết ở nhóm 0, giá trị `NULL` ở nhóm 1.

Muốn `NULL` đầu khi giảm dần:

```sql
SELECT ticket_id, priority
FROM tickets
ORDER BY (priority IS NULL) DESC, priority DESC, ticket_id ASC;
```

Cũng có thể dùng dạng `CASE WHEN priority IS NULL THEN ... ELSE ... END` để diễn đạt cùng ý định. Không sao chép trực tiếp `NULLS LAST` của PostgreSQL vào MySQL nếu phiên bản bạn dùng không hỗ trợ.

### 7.4. SQL Server

SQL Server thường đặt `NULL` trước các giá trị khác khi `ASC` và sau khi `DESC`. Dùng `CASE` để đổi hành vi theo yêu cầu:

```sql
-- T-SQL; giả sử bảng dbo.tickets đã có sẵn.
SELECT ticket_id, priority
FROM dbo.tickets
ORDER BY
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END,
    priority ASC,
    ticket_id ASC;
```

Khi phân trang bằng cú pháp T-SQL, ví dụ:

```sql
SELECT ticket_id, priority
FROM dbo.tickets
ORDER BY
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END,
    priority ASC,
    ticket_id ASC
OFFSET 0 ROWS FETCH NEXT 3 ROWS ONLY;
```

`OFFSET ... FETCH` đòi hỏi `ORDER BY` trong các trường hợp dùng phân trang theo cú pháp này. Cú pháp `LIMIT 3 OFFSET 0` của PostgreSQL/MySQL/SQLite không được dùng nguyên xi trong SQL Server.

### 7.5. SQLite

SQLite đặt `NULL` đầu khi sắp `ASC` và cuối khi `DESC` theo mặc định; từ **3.30.0**, SQLite hỗ trợ cú pháp `NULLS FIRST`/`NULLS LAST`:

```sql
-- SQLite 3.30.0 trở lên.
SELECT ticket_id, priority
FROM tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC;
```

Ở phiên bản cũ hơn, dùng `CASE WHEN priority IS NULL THEN 1 ELSE 0 END` hoặc biểu thức sắp xếp phù hợp. Nếu ứng dụng tích hợp SQLite, hãy kiểm tra phiên bản **thực tế được đóng gói trong ứng dụng/driver**, không chỉ phiên bản CLI cài trên máy phát triển.

## 8. Vì sao `COALESCE` và giá trị giả có thể gây sai thứ tự?

Có người muốn đẩy `NULL` xuống cuối bằng cách đổi nó thành một giá trị “rất lớn”:

```sql
-- Ví dụ có vẻ tiện, nhưng chỉ đúng khi 9999999 không thể là
-- một giá trị priority hợp lệ.
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY COALESCE(priority, 9999999) ASC, ticket_id ASC;
```

Cách này có một số rủi ro:

- **Giá trị giả có thể đụng miền giá trị thật**. Nếu `priority` có thể lên tới hoặc vượt 9.999.999, dòng `NULL` không còn chắc chắn đứng cuối.
- **Đổi chiều `ASC` sang `DESC`** khiến vị trí giá trị giả đảo theo, dù yêu cầu có thể vẫn muốn `NULL` cuối.
- Với `DATE`, chọn ngày giả như `9999-12-31` có thể vượt miền hỗ trợ của một DBMS/driver hoặc tạo hiểu nhầm “có hạn thật”.
- `NULL` mang nghĩa thiếu thông tin, còn giá trị giả có nghĩa “một giá trị đã biết”. Khi dùng `COALESCE` trong báo cáo hoặc ứng dụng, người đọc có thể hiểu nhầm dữ liệu.
- Dùng hàm trên cột có thể ảnh hưởng đến kế hoạch truy vấn/chỉ mục, tùy DBMS.

Ưu tiên cách thể hiện rõ **quy tắc về vị trí**:

```sql
-- Hệ hỗ trợ cú pháp bản địa.
ORDER BY priority ASC NULLS LAST, ticket_id ASC

-- Hướng dễ chuyển DBMS.
ORDER BY CASE WHEN priority IS NULL THEN 1 ELSE 0 END,
         priority ASC,
         ticket_id ASC
```

`COALESCE` vẫn hợp lý khi yêu cầu nghiệp vụ **thực sự coi giá trị thiếu là một giá trị mặc định**, nhưng khi đó nó không còn là thao tác chỉ thay vị trí `NULL` đơn thuần.

## 9. Phân trang: vì sao vị trí `NULL` ảnh hưởng đến tính ổn định?

Khi có hàng nghìn công việc, giao diện thường hiển thị từng trang. Để phân trang dự đoán được, cần một **thứ tự toàn phần**, nghĩa là trong các hàng có cùng giá trị sắp chính phải có một tiêu chí đủ phân biệt, thường là khóa chính.

Xét câu lệnh:

```sql
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority ASC NULLS LAST
LIMIT 3 OFFSET 0;
```

Nếu nhiều dòng có cùng `priority`, SQL không bắt buộc DBMS trả chúng theo thứ tự `ticket_id`. Lần chạy sau hoặc kế hoạch thực thi khác có thể cho thứ tự giữa các dòng đồng hạng khác đi, làm việc chia trang không ổn định. Nên bổ sung khóa sắp xếp duy nhất:

```sql
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC
LIMIT 3 OFFSET 0;
```

Trên PostgreSQL (hoặc SQLite hỗ trợ), các trang kích thước 3 của dữ liệu mẫu sẽ là:

| Trang | `LIMIT` / `OFFSET` | ticket_id |
|---:|---|---|
| 1 | `LIMIT 3 OFFSET 0` | 103, 107, 101 |
| 2 | `LIMIT 3 OFFSET 3` | 104, 106, 108 |
| 3 | `LIMIT 3 OFFSET 6` | 102, 105 |

**Nếu chạy trên MySQL/SQL Server**, phải dùng dạng `CASE` tương ứng để bảo đảm cùng vị trí `NULL`; cú pháp phân trang cũng phải theo phương ngữ. Việc ghi rõ `NULLS LAST` bằng cú pháp bản địa hoặc mô phỏng làm cho ranh giới giữa trang 2 và 3 không bị đảo ngoài ý muốn.

### 9.1. Đổi chiều sort không nhất thiết phải đảo vị trí `NULL`

Một giao diện có nút đổi `ASC`/`DESC` thường muốn đổi hướng sắp các giá trị đã biết, trong khi vẫn **giữ dữ liệu thiếu ở cuối**. Vì vậy nên có hai quy tắc rõ:

```sql
-- Số ưu tiên nhỏ trước, NULL luôn cuối.
ORDER BY priority ASC NULLS LAST, ticket_id ASC

-- Số ưu tiên lớn trước, NULL vẫn luôn cuối.
ORDER BY priority DESC NULLS LAST, ticket_id ASC
```

Nếu chỉ đổi `ASC` thành `DESC` mà bỏ phần `NULLS LAST`, PostgreSQL sẽ đẩy `NULL` lên đầu còn MySQL mặc định có thể đẩy xuống cuối. UI dễ tạo ra thứ tự bất ngờ khi người dùng đổi chiều.

Lưu ý: `ticket_id ASC` trong ví dụ giữ thứ tự ID tăng dần ở các nhóm có `priority` bằng nhau ở **cả hai chiều**. Nếu muốn đảo *toàn bộ* danh sách khi người dùng đổi chiều, có thể phải đảo cả các khóa phụ theo chính sách UI. Đó là một quyết định khác với vị trí `NULL`.

### 9.2. Phân trang bằng cursor/keyset với `NULLS LAST`

`OFFSET` dễ dùng nhưng khi dữ liệu được chèn/xóa giữa hai lần tải trang, các dòng có thể dịch vị trí và gây lặp/bỏ sót. Với danh sách lớn và thứ tự ổn định, có thể dùng phân trang theo **khóa cuối cùng của trang trước** (*keyset/cursor pagination*).

Giả sử sắp theo:

```sql
ORDER BY priority ASC NULLS LAST, ticket_id ASC
```

Khi hàng cuối trang trước có `priority` **khác `NULL`**, ví dụ cursor `(priority = 2, ticket_id = 104)`, các hàng theo sau phải là:

1. Hàng có `priority > 2`;
2. Hoặc có cùng `priority = 2` nhưng `ticket_id > 104`;
3. Hoặc có `priority IS NULL`, vì toàn bộ `NULL` nằm cuối.

PostgreSQL:

```sql
-- Các tham số :last_priority và :last_id do ứng dụng cung cấp.
-- Trường hợp last_priority KHÁC NULL.
SELECT ticket_id, priority
FROM demo_tickets
WHERE priority > :last_priority
   OR (priority = :last_priority AND ticket_id > :last_id)
   OR priority IS NULL
ORDER BY priority ASC NULLS LAST, ticket_id ASC
LIMIT 3;
```

Với cursor `(2, 104)`, các dòng tiếp theo theo thứ tự là ID **106, 108, 102, 105**; `LIMIT 3` trả **106, 108, 102**.

Nhưng khi cursor nằm trong nhóm `NULL`, ví dụ `(priority = NULL, ticket_id = 102)`, **không thể viết** `priority > NULL` hoặc `priority = NULL` để tìm hàng tiếp theo. Khi đó dùng nhánh riêng:

```sql
-- Trường hợp last_priority LÀ NULL.
SELECT ticket_id, priority
FROM demo_tickets
WHERE priority IS NULL
  AND ticket_id > :last_id
ORDER BY priority ASC NULLS LAST, ticket_id ASC
LIMIT 3;
```

Với `last_id = 102`, chỉ còn ID **105** trong bảng mẫu.

Những điểm cần nhớ khi viết cursor:

- **Điều kiện cursor phải mô phỏng chính xác `ORDER BY`**, bao gồm hướng sort, vị trí `NULL` và khóa phân định bằng nhau.
- Nếu đổi `ASC` sang `DESC` hoặc đổi `NULLS LAST` sang `NULLS FIRST` thì điều kiện cursor phải đổi theo.
- Nếu còn bộ lọc `WHERE` khác (theo người dùng, trạng thái, tenant, khoảng ngày...), mọi trang phải áp dụng **cùng bộ lọc** và cursor cần gắn với quy tắc sắp xếp đó.
- Keyset giúp tránh một số vấn đề của `OFFSET` và thường tốt ở trang sâu, nhưng **không tự đảm bảo ảnh chụp bất biến** khi giá trị sort của hàng có thể cập nhật giữa các lượt tải. Khi yêu cầu nhất quán tuyệt đối qua nhiều trang, cần thêm chiến lược snapshot/giao dịch hoặc cơ chế phiên bản dữ liệu.

### 9.3. Nhiều khóa sắp có `NULL`: cursor phức tạp hơn

Nếu sắp theo:

```sql
ORDER BY
    due_on ASC NULLS LAST,
    priority ASC NULLS LAST,
    ticket_id ASC
```

thì cursor phải chứa đủ các khóa liên quan: `due_on`, `priority` và `ticket_id`. Vì có thể có `NULL` ở **cả hai** khóa, việc chỉ dùng phép so sánh tuple dạng `(due_on, priority, ticket_id) > (...)` sẽ không tự xử lý mọi trường hợp `NULL` theo thứ tự `NULLS LAST`. SQL so sánh tuple chứa `NULL` có logic riêng và có thể cho `UNKNOWN`.

Có thể xây điều kiện theo nhiều nhánh `IS NULL` hoặc dùng các khóa sắp trung gian có thứ tự rõ ràng được thiết kế riêng. Trước khi triển khai, cần xác định quy tắc cursor cho các tổ hợp “ngày có/không, ưu tiên có/không” và dữ liệu đồng hạng. Với hệ thống lớn, việc đóng gói quy tắc cursor vào một lớp truy vấn thống nhất giúp tránh khác biệt giữa API và SQL.

## 10. Chỉ mục và chi phí của cách sắp `NULL`

`ORDER BY` có thể yêu cầu DBMS sắp xếp nhiều dòng, tiêu tốn CPU/bộ nhớ hoặc dùng cấu trúc chỉ mục nếu thứ tự chỉ mục phù hợp.

### 10.1. Chỉ mục tương ứng trong PostgreSQL

Với truy vấn thường gặp:

```sql
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC
LIMIT 20;
```

có thể cân nhắc chỉ mục:

```sql
CREATE INDEX idx_demo_tickets_priority_id
ON demo_tickets (priority ASC NULLS LAST, ticket_id ASC);
```

PostgreSQL hỗ trợ ghi hướng sắp và vị trí `NULL` trong định nghĩa chỉ mục B-tree. Trên dữ liệu lớn, chỉ mục này có thể hữu ích cho `ORDER BY` cùng thứ tự, đặc biệt khi lấy một số dòng đầu. Tuy nhiên, DBMS có thể chọn quét bảng rồi sort nếu dữ liệu nhỏ hoặc chi phí kế hoạch đó thấp hơn; **chỉ mục không bảo đảm luôn được dùng**.

Với chỉ mục ghép có nhiều hướng, vị trí `NULL` của từng cột và hướng quét chỉ mục đều quan trọng. Quét ngược một chỉ mục có thể đảo nhiều thành phần thứ tự, nhưng không tự động giải quyết mọi tổ hợp hỗn hợp `ASC`/`DESC` hoặc `NULLS FIRST`/`NULLS LAST`. Kiểm tra `EXPLAIN` trên truy vấn và dữ liệu thực tế.

### 10.2. Chi phí của biểu thức `CASE`

Cách viết portable:

```sql
ORDER BY
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END,
    priority ASC,
    ticket_id ASC
```

có thể khiến một chỉ mục chỉ trên `priority` không khớp hoàn toàn với **danh sách khóa sắp xếp** vì truy vấn còn sắp theo biểu thức `CASE`. Tùy DBMS, có thể sử dụng chỉ mục biểu thức, cột tính toán có chỉ mục, cột sinh (*generated column*) hoặc chỉ mục đặc thù để tối ưu.

Nhưng đừng tạo thêm cấu trúc chỉ mục chỉ vì thấy `CASE`: cần xác định tần suất truy vấn, kích thước bảng, độ chọn lọc và chi phí ghi. Một câu truy vấn nhỏ hoặc truy vấn ít chạy có thể hoạt động tốt mà không cần tối ưu thêm.

### 10.3. Thứ tự giữa các giá trị văn bản khác `NULL`

Khi sắp `name` hoặc `category`, vị trí `NULL` chỉ là một phần của vấn đề. **Collation** của cột/biểu thức quyết định cách so sánh chữ hoa/thường, dấu tiếng Việt và thứ tự các chuỗi khác `NULL`. Hai DBMS có cùng `NULLS LAST` vẫn có thể sắp danh sách tên khác nhau nếu collation không giống nhau.

Ngoài ra, chuỗi rỗng `''` là một giá trị xác định trong nhiều DBMS, nhưng Oracle Database truyền thống xem chuỗi ký tự độ dài zero như `NULL` với một số kiểu chuỗi. Vì vậy nếu nghiệp vụ phân biệt “trống” và “chưa biết”, phải kiểm tra cụ thể cách DBMS lưu và sắp dữ liệu văn bản.

## 11. Những hiểu lầm và lỗi thường gặp

| Hiểu lầm hoặc sai sót | Hệ quả | Cách làm phù hợp |
|---|---|---|
| “`NULL` là giá trị nhỏ nhất.” | Kết luận sai về thứ tự và phép so sánh | Xem `NULL` là giá trị thiếu; dùng quy tắc sắp xếp riêng |
| “`ORDER BY col ASC` luôn đặt `NULL` cuối.” | Đúng trong PostgreSQL/Oracle thông dụng, sai ở MySQL/SQL Server/SQLite theo mặc định | Viết `NULLS LAST` hoặc dùng `CASE` |
| “`DESC` sẽ đảo cả danh sách theo ý UI.” | `NULL` có thể chuyển từ đầu sang cuối ngoài ý định | Chỉ định lại vị trí `NULL` cho mỗi hướng sort |
| “`NULLS LAST` là cú pháp SQL chạy trên mọi DBMS.” | Lỗi cú pháp ở phương ngữ không hỗ trợ | Dùng `CASE WHEN col IS NULL ...` nếu cần chuyển DBMS |
| “`NULLS LAST` ở cột đầu sẽ áp dụng cho mọi cột sau.” | Các cột khác có `NULL` vẫn theo mặc định riêng | Chỉ định trên từng biểu thức cần kiểm soát |
| Dùng `WHERE col IS NOT NULL` chỉ để `NULL` đứng cuối | Làm mất bản ghi cần hiển thị | Sắp bằng `ORDER BY` nếu muốn giữ dòng |
| Dùng `COALESCE(col, 9999999)` tùy tiện | Giá trị giả trùng/ngoài miền, đảo chiều sort sai | Dùng `NULLS LAST` hoặc khóa sắp `CASE` |
| Phân trang mà không có khóa phụ duy nhất | Dòng cùng khóa sắp có thể đổi thứ tự, phân trang bất ổn | Bổ sung ID duy nhất vào `ORDER BY` |
| Cursor so sánh `col > NULL` | Điều kiện không thành `TRUE`, bỏ sót dòng sau nhóm `NULL` | Xử lý `IS NULL` và các nhánh cursor tương ứng |
| Dùng cùng chuỗi SQL trên mọi DBMS | Khác vị trí `NULL` hoặc lỗi cú pháp | Khai báo quy tắc sắp theo từng dialect |
| Nghĩ tạo chỉ mục sắp theo `NULL` luôn nhanh hơn | Chi phí ghi/chỉ mục có thể tăng, DBMS có thể không sử dụng | Đo bằng `EXPLAIN` và dữ liệu đại diện |

## 12. Bài tập tự luyện có đáp án

### Bài 1. Dự đoán thứ tự trên hai hệ quản trị

Với bảng `demo_tickets`, dự đoán các ID khi chạy:

```sql
SELECT ticket_id
FROM demo_tickets
ORDER BY priority ASC, ticket_id ASC;
```

**Đáp án:**

- Trên PostgreSQL: **103, 107, 101, 104, 106, 108, 102, 105**.
- Trên MySQL: **102, 105, 103, 107, 101, 104, 106, 108**.

Khác biệt nằm ở vị trí mặc định của `NULL`; thứ tự các nhóm có `priority` khác `NULL` đều là `1, 2, 3`.

### Bài 2. Viết truy vấn ưu tiên tăng, `NULL` cuối

**Yêu cầu:** dùng PostgreSQL lấy các công việc theo `priority` tăng dần, các công việc chưa có ưu tiên đứng cuối; mọi giá trị bằng nhau theo ID tăng.

**Đáp án:**

```sql
SELECT ticket_id, title, priority
FROM demo_tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC;
```

### Bài 3. Chuyển sang SQL Server

**Yêu cầu:** giữ đúng kết quả bài 2 với bảng `dbo.tickets` trong SQL Server.

**Đáp án:**

```sql
SELECT ticket_id, title, priority
FROM dbo.tickets
ORDER BY
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END,
    priority ASC,
    ticket_id ASC;
```

`CASE` xếp nhóm có giá trị trước rồi mới đến nhóm `NULL`.

### Bài 4. Đổi chiều sort nhưng giữ `NULL` cuối

**Yêu cầu:** sửa bài 2 thành ưu tiên **giảm dần**, nhưng vẫn đặt công việc chưa có ưu tiên xuống cuối.

**Đáp án PostgreSQL:**

```sql
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority DESC NULLS LAST, ticket_id ASC;
```

Thứ tự ID: **106, 108, 101, 104, 103, 107, 102, 105**. Chỉ đổi hướng `priority`; quy tắc `NULLS LAST` vẫn giữ nguyên.

### Bài 5. Ngày đến hạn có `NULL`

**Yêu cầu:** hiển thị nhiệm vụ theo ngày hạn gần nhất, các dòng chưa có ngày hạn ở cuối và ID tăng khi cùng hạn.

**Đáp án PostgreSQL:**

```sql
SELECT ticket_id, due_on
FROM demo_tickets
ORDER BY due_on ASC NULLS LAST, ticket_id ASC;
```

Thứ tự: **106, 108, 103, 101, 105, 102, 104, 107**. Các dòng chưa có hạn được phân định bằng ID: 102, 104, 107.

### Bài 6. Nhận diện lỗi khi phân trang

Một ứng dụng có `priority` với nhiều dòng bằng nhau và sử dụng:

```sql
SELECT ticket_id, priority
FROM demo_tickets
ORDER BY priority ASC NULLS LAST
LIMIT 3 OFFSET 3;
```

**Hỏi:** vì sao kết quả có thể không ổn định qua những lần tải trang ngay cả khi không đổi hướng sắp?

**Đáp án:** `priority` không duy nhất; thứ tự giữa các hàng có cùng ưu tiên hoặc cùng `NULL` không được quy định. Thêm `ticket_id ASC` (khóa duy nhất) làm tiêu chí cuối. Nếu dữ liệu thay đổi giữa các lần tải, `OFFSET` vẫn có thể bị dịch trang; cân nhắc keyset/cursor và chiến lược nhất quán tương ứng.

### Bài 7. Viết cú pháp chung cho cả MySQL và SQL Server

**Yêu cầu:** sắp `due_on` giảm dần, `NULL` **đầu**, sau đó ID tăng.

**Đáp án:**

```sql
SELECT ticket_id, due_on
FROM tickets
ORDER BY
    CASE WHEN due_on IS NULL THEN 0 ELSE 1 END,
    due_on DESC,
    ticket_id ASC;
```

Đây là mẫu `CASE` portable về ý nghĩa. Trên SQL Server, tên bảng có thể là `dbo.tickets`; tên bảng và cú pháp tạo dữ liệu mẫu vẫn tùy từng DBMS.

## Kết luận

Trong `ORDER BY`, **hướng tăng/giảm của giá trị đã biết** và **vị trí của `NULL`** là hai quyết định khác nhau. PostgreSQL/Oracle thường mặc định `NULL` cuối với `ASC`, đầu với `DESC`; MySQL/MariaDB/SQL Server/SQLite thường mặc định ngược lại. PostgreSQL, Oracle và SQLite từ phiên bản phù hợp hỗ trợ cú pháp `NULLS FIRST`/`NULLS LAST`; các phương ngữ không hỗ trợ có thể sử dụng `CASE WHEN ... IS NULL ... END` để biểu diễn cùng ý định.

Khi hiển thị dữ liệu hoặc phân trang, hãy **chỉ định rõ vị trí `NULL`**, xử lý riêng cho từng khóa `ORDER BY` và thêm **khóa phụ duy nhất** để phân định các hàng đồng hạng. Nếu dùng cursor, điều kiện tìm trang kế tiếp phải phản ánh đúng chính sách `NULL` và hướng sắp xếp. Những quyết định nhỏ này giúp kết quả SQL nhất quán, giao diện dễ hiểu và việc di chuyển giữa các hệ quản trị ít bất ngờ hơn.

