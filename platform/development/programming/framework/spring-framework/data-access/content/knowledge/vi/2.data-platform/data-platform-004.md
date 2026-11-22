# Kiểu dữ liệu SQL, NULL và logic ba giá trị

Một truy vấn đúng cú pháp vẫn có thể cho kết quả sai nếu chọn kiểu dữ liệu không phù hợp hoặc xử lý `NULL` như một giá trị thông thường. Đây là nền tảng cần hiểu trước khi dùng JDBC, Spring JDBC, JPA hay bất kỳ công cụ truy cập dữ liệu nào: các công cụ Java chuyển đổi dữ liệu, nhưng **quy tắc kiểu dữ liệu và phép so sánh vẫn do hệ quản trị CSDL (DBMS) quyết định**.

Sau bài này, bạn có thể:
- Chọn nhóm kiểu SQL thích hợp cho số, chuỗi, ngày giờ, dữ liệu nhị phân và các kiểu mở rộng; nhận biết khác biệt giữa các DBMS.
- Phân biệt `NULL` với số 0, chuỗi rỗng, `FALSE` và một giá trị mặc định.
- Dự đoán kết quả `TRUE` / `FALSE` / `UNKNOWN` của biểu thức SQL, nhất là khi lọc bằng `WHERE`, `JOIN` và `HAVING`.
- Tránh các lỗi phổ biến của `= NULL`, `NOT IN`, `COUNT`, `CHECK` và phép nối ngoài.
- Ánh xạ giá trị nullable an toàn khi đọc/ghi dữ liệu qua JDBC và Spring `JdbcTemplate`.

> **Phạm vi ví dụ:** Những truy vấn tạo bảng và `WITH ... VALUES` dưới đây sử dụng cú pháp PostgreSQL hiện đại để có thể chạy thử nhất quán. Các nguyên lý về `NULL`, logic ba giá trị và phép tổng hợp là nguyên lý SQL rộng rãi; nơi cú pháp/hành vi khác theo DBMS sẽ được nêu rõ. Khi triển khai với MySQL, SQL Server, Oracle hoặc H2, kiểm tra thêm tài liệu đúng phiên bản đang sử dụng.

## 1. Kiểu dữ liệu SQL mô tả điều gì?

Mỗi cột có **kiểu dữ liệu** quyết định miền giá trị hợp lệ, cách lưu trữ, phép toán, tính chính xác và quy tắc chuyển đổi. Ví dụ, mã hóa đơn `'00125'` là định danh dạng văn bản; nếu lưu bằng số nguyên, số 0 đầu tiên bị mất. Ngược lại, tổng tiền phải là kiểu số để cộng, so sánh và kiểm tra ràng buộc.

Các nhóm thường gặp:

| Nhóm | Kiểu thường gặp | Dùng cho | Điểm cần chú ý |
| --- | --- | --- | --- |
| Số nguyên | `SMALLINT`, `INTEGER`/`INT`, `BIGINT` | Số lượng, khóa số, bộ đếm | Giới hạn miền giá trị; tránh tràn số khi tính toán. |
| Số thập phân chính xác | `DECIMAL(p,s)`, `NUMERIC(p,s)` | Tiền, tỷ lệ cần độ chính xác xác định | `p` là tổng số chữ số; `s` là chữ số sau dấu thập phân. |
| Số xấp xỉ | `REAL`, `FLOAT`, `DOUBLE PRECISION` | Đo lường, tính toán khoa học | Biểu diễn nhị phân xấp xỉ; không phù hợp để kiểm tra tiền bằng so sánh bằng tuyệt đối. |
| Ký tự | `CHAR(n)`, `VARCHAR(n)`, `TEXT` | Tên, mô tả, mã | `CHAR` có thể được đệm khoảng trắng; `TEXT` và giới hạn độ dài khác nhau theo DBMS. |
| Ngày/giờ | `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` | Ngày sinh, thời điểm tạo, lịch hẹn | Phải phân biệt ngày địa phương, thời gian không múi giờ và mốc thời gian thực. |
| Luận lý | `BOOLEAN` | Cờ bật/tắt, trạng thái đúng/sai | Cột nullable còn có khả năng `NULL`; một số DBMS dùng kiểu số thay thế. |
| Nhị phân | `BINARY`, `VARBINARY`, `BLOB`/`BYTEA` | Tệp, byte, checksum | Tên kiểu và giới hạn kích thước phụ thuộc hệ quản trị. |
| Mở rộng | `UUID`, `JSON`/`JSONB`, `ARRAY`, `ENUM` | Định danh UUID, tài liệu JSON, tập giá trị | Không phải kiểu nào cũng thuộc cùng tập cú pháp chuẩn hoặc được hỗ trợ ở mọi DBMS. |

### 1.1. Kiểu chính xác và kiểu xấp xỉ

Với `DECIMAL(15,2)`, một giá trị có tối đa 15 chữ số thập phân, trong đó 2 chữ số dành cho phần lẻ; về mặt miền giá trị, tối đa 13 chữ số ở phần nguyên. Quy tắc làm tròn/chuyển đổi và xử lý vượt miền cần kiểm tra theo DBMS.

- **Tiền:** dùng `DECIMAL`/`NUMERIC` và trong Java thường dùng `BigDecimal`.
- **Đo đạc xấp xỉ:** có thể dùng kiểu dấu phẩy động; đừng giả định phép cộng nhị phân cho kết quả chính xác tuyệt đối ở dạng thập phân.
- **Định danh:** `phone`, `postal_code` hay mã sản phẩm có số 0 đầu nên dùng chuỗi, dù chỉ chứa chữ số.

### 1.2. Kiểu thời gian có ngữ nghĩa khác nhau

`DATE` là một ngày theo lịch, không phải thời điểm tuyệt đối; `TIME` là thời gian trong ngày. `TIMESTAMP WITHOUT TIME ZONE` lưu ngày và giờ theo ngữ cảnh địa phương mà không tự mang thông tin múi giờ. Với PostgreSQL, `TIMESTAMP WITH TIME ZONE` (`timestamptz`) biểu diễn một thời điểm và được diễn giải/hiển thị theo múi giờ phiên làm việc; nó **không giữ nguyên chuỗi múi giờ hoặc offset ban đầu**. Một số DBMS có quy tắc khác. Trong Java, thường chọn `LocalDate` cho `DATE`, `LocalDateTime` cho thời gian địa phương và `OffsetDateTime`/`Instant` cho thời điểm thực, theo khả năng JDBC driver và kiểu cột.

## 2. Thiết kế bảng minh họa và ý nghĩa của NULL

Ví dụ PostgreSQL:

```sql
CREATE TABLE invoices (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    invoice_no  VARCHAR(30) NOT NULL UNIQUE,
    amount      DECIMAL(15, 2) NOT NULL CHECK (amount >= 0),
    due_on      DATE,
    paid_at     TIMESTAMP WITH TIME ZONE,
    note        VARCHAR(200),
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO invoices
    (customer_id, invoice_no, amount, due_on, paid_at, note)
VALUES
    (7, 'INV-00125', 125000.50, DATE '2026-11-15', NULL, NULL);
```

Ở đây, `paid_at IS NULL` có nghĩa **chưa có thông tin thời điểm thanh toán**. Không được tự động suy ra hóa đơn đã quá hạn hay chắc chắn chưa thanh toán nếu quy trình nghiệp vụ còn các trạng thái khác. `note IS NULL` nghĩa là trường ghi chú không có giá trị, khác với `note = ''` (chuỗi rỗng) trong PostgreSQL. `amount` bị ràng buộc `NOT NULL` vì hóa đơn phải có số tiền.

**NULL không phải** số 0, `FALSE`, chuỗi `'NULL'`, chuỗi rỗng, ngày `1970-01-01` hoặc một ô chưa được tạo ở giao diện. Nó là **marker cho việc thiếu/không xác định giá trị** trong mô hình SQL. Lý do thiếu có thể là chưa biết, chưa áp dụng hoặc chưa được cung cấp; nếu cần phân biệt các trạng thái này, hãy thiết kế thêm cột trạng thái hay mô hình riêng, thay vì gán một ý nghĩa nghiệp vụ cố định cho mọi `NULL`.

### 2.1. NULL, DEFAULT và ràng buộc

- `NOT NULL` buộc cột phải có giá trị không-null.
- `DEFAULT TRUE` được dùng khi cột được **bỏ qua** trong `INSERT` hoặc khi dùng từ khóa `DEFAULT`; truyền tường minh `NULL` không đồng nghĩa với yêu cầu dùng mặc định. Với cột có `NOT NULL`, truyền `NULL` thường bị từ chối.
- `PRIMARY KEY` xác định duy nhất bản ghi và không cho `NULL`.
- `UNIQUE` và `NULL` có khác biệt giữa DBMS: nhiều hệ quản trị cho phép nhiều hàng có `NULL` trong cột unique, một số quy tắc/kiểu index khác. Không mặc định tính di động của hành vi này.
- Một khóa ngoại nullable có thể không chỉ đến bản ghi cha nào; với khóa ngoại một cột, `NULL` không được xem là một khóa tham chiếu cần tìm hàng cha.
- `CHECK (amount >= 0)` chỉ bác bỏ biểu thức **FALSE**. Nếu `amount` là `NULL`, `amount >= 0` thành **UNKNOWN**, nên riêng `CHECK` này không loại `NULL`. Cần cả `NOT NULL` nếu trường bắt buộc.

## 3. SQL dùng logic **ba giá trị** (three-valued logic)

Trong nhiều ngôn ngữ lập trình, biểu thức điều kiện chủ yếu nhận `true` hoặc `false`. Trong SQL, vì `NULL`, một phép so sánh thông thường có thể cho:

- **TRUE (T):** điều kiện đúng.
- **FALSE (F):** điều kiện sai.
- **UNKNOWN (U):** thiếu giá trị để xác định đúng/sai.

Một số biểu thức minh họa:

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `5 = 5` | T | Hai giá trị xác định bằng nhau. |
| `5 <> 8` | T | Hai giá trị xác định khác nhau. |
| `NULL = 5` | U | Không có giá trị để so sánh. |
| `NULL <> 5` | U | Không được suy ra là “khác 5”. |
| `NULL = NULL` | U | Hai marker NULL không tạo thành phép bằng TRUE. |
| `NOT (NULL = 5)` | U | Phủ định UNKNOWN vẫn UNKNOWN. |
| `NULL IS NULL` | T | `IS NULL` kiểm tra sự hiện diện của NULL. |
| `5 IS NOT NULL` | T | Giá trị 5 có tồn tại. |

Quy tắc cốt lõi: với phép `=`, `<>`, `<`, `>`, `<=`, `>=`, khi một toán hạng là `NULL` thì kết quả thường là `UNKNOWN`; không dùng `= NULL` hoặc `<> NULL` để kiểm tra giá trị thiếu.

### 3.1. Bảng chân trị của NOT, AND, OR

`NOT`:

| P | NOT P |
| --- | --- |
| T | F |
| F | T |
| U | U |

`AND`:

| P \ Q | T | F | U |
| --- | --- | --- | --- |
| T | T | F | U |
| F | F | F | F |
| U | U | F | U |

`OR`:

| P \ Q | T | F | U |
| --- | --- | --- | --- |
| T | T | T | T |
| F | T | F | U |
| U | T | U | U |

Lưu ý những trường hợp dễ nhầm: `FALSE AND UNKNOWN = FALSE`, `TRUE OR UNKNOWN = TRUE`, còn `NOT UNKNOWN = UNKNOWN`. Vì vậy, biểu thức `x = 10 OR x <> 10` **không luôn TRUE**: khi `x IS NULL`, cả hai vế UNKNOWN và kết quả là UNKNOWN. Quy tắc “loại trừ trung gian” quen thuộc của logic hai giá trị không thể áp dụng máy móc cho phép so sánh nullable trong SQL.

## 4. WHERE, HAVING và JOIN xử lý UNKNOWN ra sao?

`WHERE` và `HAVING` chỉ giữ những hàng/nhóm mà điều kiện đánh giá là **TRUE**. Cả FALSE lẫn UNKNOWN đều không được chọn.

Dữ liệu thử độc lập, chạy được trong PostgreSQL:

```sql
WITH samples(id, score) AS (
    VALUES (1, 5), (2, 10), (3, NULL)
)
SELECT id, score
FROM samples
WHERE score <> 5
ORDER BY id;
```

**Kết quả:** chỉ hàng `id = 2, score = 10`. Hàng `id = 3` bị loại vì `NULL <> 5` là UNKNOWN, không phải TRUE. Thay `WHERE score <> 5` bằng `WHERE NOT (score = 5)` vẫn chỉ trả `id = 2`.

Muốn chọn cả các giá trị khác 5 **hoặc chưa biết**, viết rõ:

```sql
WHERE score <> 5 OR score IS NULL
```

Nếu DBMS hỗ trợ, `score IS DISTINCT FROM 5` là phép so sánh “khác nhau có xét NULL”: với dữ liệu trên, nó là TRUE cho `score = 10` **và** `score IS NULL`. Ngược lại, `IS NOT DISTINCT FROM` là phép so sánh bằng có xét NULL; hai giá trị NULL được coi là không khác nhau. PostgreSQL hỗ trợ cả hai, trong khi MySQL có toán tử null-safe `<=>` với ngữ nghĩa tương đương `IS NOT DISTINCT FROM`. Kiểm tra hỗ trợ của DBMS trước khi dùng.

### 4.1. JOIN: ON và WHERE không hoán đổi tùy ý

Đối với `INNER JOIN`, một cặp hàng chỉ khớp khi điều kiện `ON` là TRUE; UNKNOWN không tạo ra kết quả khớp. Với `LEFT JOIN`, hàng bên trái không có cặp khớp vẫn được giữ và các cột bên phải được bổ sung NULL. Vì thế vị trí điều kiện rất quan trọng.

```sql
-- Giữ mọi khách hàng; chỉ nối hóa đơn đang có active = TRUE.
SELECT c.id, i.invoice_no
FROM customers AS c
LEFT JOIN invoices AS i
    ON i.customer_id = c.id AND i.active = TRUE;
```

Trong truy vấn trên, khách hàng chưa có hóa đơn active vẫn xuất hiện với `i.invoice_no` là NULL. Nhưng nếu chuyển `i.active = TRUE` xuống `WHERE`:

```sql
SELECT c.id, i.invoice_no
FROM customers AS c
LEFT JOIN invoices AS i
    ON i.customer_id = c.id
WHERE i.active = TRUE;
```

Các hàng được bổ sung NULL sẽ bị `WHERE` loại; kết quả không còn giữ mọi khách hàng. Hai ví dụ giả định bảng `customers` có khóa `id` và bảng `invoices` được tạo như ở mục 2.

## 5. Các bẫy phổ biến với IN và NOT IN

`IN` về mặt logic tương đương một chuỗi điều kiện bằng kết hợp `OR`. Nếu danh sách chứa NULL:

- `5 IN (5, NULL)` → TRUE vì đã có phần tử khớp.
- `8 IN (5, NULL)` → UNKNOWN vì `8 = 5` là FALSE, `8 = NULL` là UNKNOWN.
- `8 NOT IN (5, NULL)` → UNKNOWN vì đó là phủ định của UNKNOWN.
- `NULL IN (5, NULL)` → UNKNOWN; NULL không “khớp chính nó” qua dấu `=`.

Vì `WHERE` loại UNKNOWN, `NOT IN` dễ trả về **rỗng ngoài ý muốn** nếu truy vấn con có ít nhất một NULL:

```sql
-- Dễ sai nếu invoices.customer_id có thể chứa NULL:
SELECT c.id
FROM customers AS c
WHERE c.id NOT IN (
    SELECT i.customer_id FROM invoices AS i
);
```

Cách thường an toàn hơn để tìm khách hàng **không có** hóa đơn là anti-join bằng `NOT EXISTS`:

```sql
SELECT c.id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM invoices AS i
    WHERE i.customer_id = c.id
);
```

`EXISTS` chỉ hỏi truy vấn con có ít nhất một hàng hay không; nó không phụ thuộc vào giá trị của cột trong `SELECT 1`. Điều kiện tương quan `i.customer_id = c.id` không khớp với `i.customer_id IS NULL`, nên NULL trong bảng con không làm “độc” toàn bộ kết quả như `NOT IN`. Trong schema minh họa, `invoices.customer_id` đã có `NOT NULL`; ví dụ bẫy `NOT IN` đặc biệt quan trọng với schema khác hoặc truy vấn con có thể sinh NULL từ phép nối/biểu thức.

## 6. NULL với hàm tổng hợp, DISTINCT, GROUP BY

Các hàm tổng hợp không đối xử với NULL giống nhau:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `COUNT(*)` | Đếm **tất cả hàng**, bất kể cột nào là NULL. |
| `COUNT(col)` | Đếm số hàng có `col IS NOT NULL`. |
| `COUNT(DISTINCT col)` | Đếm các giá trị phân biệt **không NULL**. |
| `SUM(col)`, `AVG(col)` | Bỏ qua NULL; `AVG` chia cho số giá trị không NULL. |
| `MIN(col)`, `MAX(col)` | Bỏ qua NULL. |

Kiểm tra bằng một truy vấn độc lập:

```sql
WITH samples(id, score) AS (
    VALUES (1, 5), (2, 10), (3, NULL)
)
SELECT COUNT(*) AS all_rows,
       COUNT(score) AS known_scores,
       SUM(score) AS total_score,
       AVG(score) AS average_score
FROM samples;
```

Kết quả về mặt giá trị: `all_rows = 3`, `known_scores = 2`, `total_score = 15`, `average_score = 7.5`. Cách DBMS định dạng phần thập phân có thể khác. Nếu không có hàng đầu vào (hoặc toàn bộ đối số của `SUM` đều NULL), `SUM` trả NULL, trong khi `COUNT` trả 0. Muốn hiển thị tổng bằng 0 trong trường hợp không có số để cộng, có thể dùng `COALESCE(SUM(score), 0)`.

Khi `GROUP BY col`, các hàng có `col IS NULL` được gom vào **một nhóm NULL**. `SELECT DISTINCT col` cũng chỉ trả một bản thể NULL trong kết quả phân biệt. Điều này **không** có nghĩa `NULL = NULL` trở thành TRUE trong phép so sánh bình thường; đó là quy tắc riêng của nhóm/khử trùng lặp.

Thứ tự sắp xếp NULL không thống nhất giữa DBMS. PostgreSQL cho phép chỉ rõ `ORDER BY col NULLS FIRST` hoặc `NULLS LAST`; cú pháp này không có ở mọi hệ quản trị. Đừng viết logic nghiệp vụ dựa vào vị trí NULL mặc định.

## 7. Viết biểu thức xử lý NULL đúng ý nghĩa

### 7.1. IS NULL / IS NOT NULL

```sql
SELECT invoice_no
FROM invoices
WHERE paid_at IS NULL;
```

Đây là cách chuẩn để tìm hóa đơn thiếu thông tin thời điểm thanh toán. `WHERE paid_at = NULL` không chọn được các hàng này.

### 7.2. COALESCE: chọn giá trị đầu tiên không NULL

`COALESCE(a, b, ...)` trả đối số đầu tiên không NULL; nếu tất cả NULL thì trả NULL. Các đối số phải có kiểu có thể chuyển đổi tương thích theo quy tắc DBMS.

```sql
SELECT invoice_no,
       COALESCE(note, '(không có ghi chú)') AS display_note
FROM invoices;
```

Nên dùng `COALESCE` ở **ranh giới trình bày** khi một giá trị thay thế thực sự phù hợp. `COALESCE(score, 0)` biến “chưa biết điểm” thành “điểm 0”; điều này có thể thay đổi kết quả thống kê và ý nghĩa dữ liệu. Ví dụ, `AVG(score)` bỏ qua NULL, còn `AVG(COALESCE(score, 0))` đưa những giá trị thiếu thành 0 và làm thay đổi mẫu số.

### 7.3. NULLIF, CASE và chuyển kiểu

- `NULLIF(a, b)` trả NULL nếu `a = b` là TRUE; ngược lại trả `a`. Có thể dùng `NULLIF(quantity, 0)` để biến mẫu số bằng 0 thành NULL trước phép chia, nhưng kết quả biểu thức cũng trở thành NULL thay vì báo lỗi chia cho 0.
- `CASE WHEN condition THEN x ELSE y END` chọn nhánh `WHEN` chỉ khi điều kiện TRUE; FALSE và UNKNOWN đi tiếp đến nhánh sau/`ELSE`.
- `CAST(value AS type)` chuyển kiểu tường minh. Chuyển từ chuỗi sang số/ngày có thể lỗi nếu dữ liệu không hợp lệ; khả năng chuyển đổi “thử rồi trả NULL” có tên/cú pháp riêng theo DBMS, không phải SQL portable.

```sql
SELECT invoice_no,
       CASE
           WHEN paid_at IS NOT NULL THEN 'Đã có thời điểm thanh toán'
           WHEN due_on IS NULL THEN 'Chưa có hạn thanh toán'
           ELSE 'Chưa có thời điểm thanh toán'
       END AS payment_information
FROM invoices;
```

Biểu thức này phân loại **mức độ thông tin có trong cột** theo thứ tự nhánh, chưa kết luận đầy đủ trạng thái nghiệp vụ “đã thanh toán” hoặc “quá hạn”. Phân biệt dữ liệu quan sát được với chính sách kinh doanh.

## 8. Tương tác với JDBC và Spring Data Access

SQL `NULL` ánh xạ thường gặp thành Java `null` với kiểu tham chiếu. Nhưng không phải mọi cách đọc đều giữ được thông tin thiếu. JDBC truyền SQL type qua driver; kiểu Java tương ứng phải chọn theo dữ liệu và tính nullable:

| SQL | Java thường dùng | Lưu ý |
| --- | --- | --- |
| `INTEGER` nullable | `Integer` | Không dùng `int` nếu cần phân biệt NULL với 0. |
| `BIGINT` | `Long`/`long` | Chỉ dùng `long` nguyên thủy khi cột được bảo đảm `NOT NULL`. |
| `DECIMAL`/`NUMERIC` | `BigDecimal` | Giữ độ chính xác, không tự đổi sang `double` cho dữ liệu tiền. |
| `VARCHAR` | `String` | Java `null` và `""` có thể mang hai ý nghĩa khác nhau. |
| `DATE` | `LocalDate` | Nên dùng JDBC 4.2/driver hỗ trợ kiểu `java.time`. |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime`/`Instant` tùy driver | Kiểm tra driver, cách chuẩn hóa và múi giờ kết nối. |
| `BOOLEAN` nullable | `Boolean` | Ba trạng thái Java: `true`, `false`, `null`. |

Các phương thức `ResultSet.getInt(...)`, `getLong(...)` hay `getBoolean(...)` trả kiểu primitive, nên khi cột SQL là NULL, chúng trả giá trị mặc định `0`/`false`. Muốn biết có thực sự là NULL, **gọi `rs.wasNull()` ngay sau lần đọc đó**, trước khi đọc cột khác. Khi JDBC driver hỗ trợ, `rs.getObject("score", Integer.class)` là cách đọc thành đối tượng nullable. `rs.getBigDecimal(...)` trả `BigDecimal` hoặc `null`.

Đây là **một lớp minh họa dùng Spring JDBC**, cần có thư viện Spring JDBC, `JdbcTemplate` được cấu hình và bảng `invoices` trong DB; không phải chương trình chạy độc lập bằng `java`:

```java
import java.math.BigDecimal;
import java.sql.Types;
import java.time.LocalDate;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

public final class InvoiceReader {
    private final JdbcTemplate jdbc;

    public InvoiceReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record InvoiceView(long id, BigDecimal amount, LocalDate dueOn) {}

    public List<InvoiceView> withoutPaymentTimestamp() {
        RowMapper<InvoiceView> mapper = (rs, rowNum) -> new InvoiceView(
            rs.getLong("id"),                       // PK NOT NULL
            rs.getBigDecimal("amount"),              // DECIMAL
            rs.getObject("due_on", LocalDate.class)  // nullable
        );

        return jdbc.query(
            "SELECT id, amount, due_on FROM invoices WHERE paid_at IS NULL",
            mapper
        );
    }

    public int clearNote(long invoiceId) {
        return jdbc.update(
            "UPDATE invoices SET note = ? WHERE id = ?",
            ps -> {
                ps.setNull(1, Types.VARCHAR); // SQL NULL có kiểu rõ ràng
                ps.setLong(2, invoiceId);
            }
        );
    }
}
```

Điểm cần quan sát:
1. `InvoiceView.dueOn` dùng `LocalDate` (kiểu tham chiếu), vì cột `due_on` có thể NULL.
2. `id` và `amount` theo DDL `NOT NULL`; `rs.getLong("id")` hợp lý cho khóa chính. `getBigDecimal` vẫn là phương thức trả đối tượng.
3. `PreparedStatement.setNull(position, Types.VARCHAR)` ghi **SQL NULL**, không ghi chuỗi `"null"`; chọn mã `Types` phù hợp với cột/driver.
4. Giá trị động được bind bằng tham số `?`, tránh nối chuỗi SQL từ dữ liệu người dùng.
5. Không dùng `WHERE note = ?` rồi bind null với kỳ vọng tìm các hàng note NULL; dấu `=` vẫn cho UNKNOWN. Dùng `IS NULL` hoặc phép so sánh null-safe được DBMS hỗ trợ.

Với Spring Data JPA, kiểu Java nullable và cách query vẫn phải phản ánh SQL `NULL`; việc trả `Optional<T>` ở ranh giới repository giúp mô tả “có/không có bản ghi”, nhưng **không tự động giải quyết** mọi thuộc tính nullable hay mọi trường hợp UNKNOWN trong `WHERE`. Nên kiểm tra SQL thực tế khi viết derived query hoặc JPQL có điều kiện nullable.

## 9. Những lỗi thường gặp và cách sửa

| Dễ viết sai | Hậu quả | Cách đúng tùy mục tiêu |
| --- | --- | --- |
| `WHERE x = NULL` | Kết quả UNKNOWN, không bắt hàng thiếu. | `WHERE x IS NULL`. |
| `WHERE x <> NULL` | Không chọn hàng xác định như mong đợi. | `WHERE x IS NOT NULL` nếu mục tiêu là “có giá trị”. |
| `WHERE x <> 5` và tưởng đã gồm NULL | Hàng NULL bị loại. | `x <> 5 OR x IS NULL`, hoặc `x IS DISTINCT FROM 5` nếu hỗ trợ. |
| `NOT IN (subquery)` khi subquery có NULL | Có thể không trả hàng nào. | `NOT EXISTS` với điều kiện tương quan đúng khóa. |
| Đưa điều kiện phía phải `LEFT JOIN` xuống `WHERE` | Mất các hàng trái không có kết quả ghép. | Đặt điều kiện lọc hàng phải trong `ON` khi cần bảo toàn hàng trái. |
| `AVG(COALESCE(x, 0))` để “bỏ qua NULL” | Vô tình tính thiếu dữ liệu thành số 0. | `AVG(x)` nếu muốn bỏ qua giá trị thiếu. |
| `CHECK(x > 0)` rồi tưởng x không NULL | UNKNOWN vẫn có thể vượt CHECK. | Kết hợp `x NOT NULL` và `CHECK(x > 0)`. |
| Đọc nullable SQL `INTEGER` bằng `getInt` mà không `wasNull` | Không phân biệt NULL với 0. | `getObject(..., Integer.class)` hoặc `getInt` + `wasNull`. |
| Dùng `DOUBLE` cho tiền | Sai số dấu phẩy động ảnh hưởng tính toán. | `DECIMAL` trong SQL, `BigDecimal` trong Java. |

Một lỗi thiết kế khác là thay mọi `NULL` bằng sentinel như `-1`, `'N/A'` hoặc ngày giả. Sentinel trở thành **giá trị thực** đối với bộ máy SQL: nó có thể được tính trung bình, so sánh, làm khóa ngoại sai hoặc lọt vào thống kê. Chỉ dùng sentinel nếu đó thật sự là một giá trị có nghĩa trong miền dữ liệu và đã có quy tắc nhất quán.

## 10. Tự kiểm tra hiểu bài

Cho tập bản ghi thử:

| id | score |
| --- | --- |
| 1 | 5 |
| 2 | 10 |
| 3 | NULL |

**Câu 1.** `WHERE score = 5 OR score <> 5` trả những id nào? **Đáp án:** 1 và 2. Hàng 3 có UNKNOWN ở cả hai phép so sánh, nên UNKNOWN OR UNKNOWN = UNKNOWN.

**Câu 2.** `WHERE NOT (score = 5)` và `WHERE score IS DISTINCT FROM 5` có cùng kết quả không? **Đáp án:** Không. Biểu thức đầu trả id 2; biểu thức thứ hai (trong DBMS hỗ trợ) trả id 2 và 3.

**Câu 3.** `COUNT(*)`, `COUNT(score)` và `AVG(score)` lần lượt bằng bao nhiêu? **Đáp án:** 3, 2 và 7.5. `AVG` bỏ qua hàng NULL.

**Câu 4.** Cột `quantity INTEGER CHECK (quantity > 0)` có thể nhận NULL không? **Đáp án:** Có, nếu không có `NOT NULL` hoặc ràng buộc khác cấm nó: `NULL > 0` là UNKNOWN, và `CHECK` chỉ từ chối FALSE.

**Câu 5.** Vì sao `NOT EXISTS` thường đáng tin hơn `NOT IN` khi truy vấn con có thể trả NULL? **Đáp án:** `NOT EXISTS` quyết định dựa trên sự tồn tại của hàng thỏa điều kiện tương quan, trong khi một NULL trong tập giá trị của `NOT IN` có thể khiến phép so sánh thành UNKNOWN và bị `WHERE` loại.

### Checklist khi viết truy vấn thực tế

- Kiểu SQL có biểu diễn **đúng ý nghĩa nghiệp vụ** và đúng độ chính xác hay không?
- Cột cho phép NULL không; NULL đại diện cho loại thiếu thông tin nào?
- Mọi phép so sánh nullable trong `WHERE`/`HAVING`/`JOIN ON` đã xét khả năng UNKNOWN chưa?
- Với `LEFT JOIN`, điều kiện đặt trong `ON` hay `WHERE` có bảo toàn tập hàng mong muốn không?
- `COUNT`/`AVG`/`SUM` đang bỏ qua NULL đúng ý định hay phải báo riêng số giá trị thiếu?
- Query chống tồn tại có nguy cơ `NOT IN` bị NULL làm sai không?
- Java/JDBC có giữ được phân biệt `NULL` với `0`, `false`, chuỗi rỗng và giá trị mặc định không?
- Cú pháp đặc thù (`IDENTITY`, `UUID`, `JSONB`, `IS DISTINCT FROM`, kiểu ngày giờ, NULL sorting) đã được kiểm tra trên DBMS đích chưa?

**Điều cần nhớ:** Kiểu dữ liệu quyết định giá trị hợp lệ; `NULL` biểu diễn giá trị thiếu; và biểu thức SQL có thể nhận **UNKNOWN**. Chỉ điều kiện **TRUE** mới vượt qua `WHERE` và `HAVING`. Hiểu ba điểm này giúp dự đoán đúng kết quả truy vấn trước khi đưa dữ liệu vào Spring.
