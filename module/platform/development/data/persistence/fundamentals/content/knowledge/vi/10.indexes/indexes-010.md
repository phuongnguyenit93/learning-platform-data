# Ảnh hưởng của biểu thức, kiểu dữ liệu và chuyển đổi ngầm lên chỉ mục

Một chỉ mục tồn tại không có nghĩa là mọi truy vấn lọc theo cột đó đều sử dụng được chỉ mục một cách hiệu quả. **Biểu thức đặt lên cột, kiểu dữ liệu của cột và tham số, cùng các phép chuyển đổi kiểu ngầm** có thể thay đổi cách hệ quản trị cơ sở dữ liệu (DBMS) so sánh giá trị, ước lượng số dòng và chọn kế hoạch truy vấn.

Bài học này thuộc phần **Chỉ mục** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là hiểu nguyên lý lưu trữ và truy vấn dữ liệu bền vững để thiết kế lớp persistence cho ứng dụng Java: chọn kiểu dữ liệu đúng, viết điều kiện có thể tận dụng chỉ mục, truyền tham số đúng kiểu và kiểm chứng hiệu năng bằng kế hoạch thực thi. Các ví dụ SQL chủ yếu dùng **PostgreSQL** và chỉ mục B-tree; khi áp dụng với MySQL, SQL Server hay hệ khác, cần đối chiếu cú pháp và quy tắc tối ưu của chính hệ đó.

## 1. Từ điều kiện lọc đến phép tra cứu chỉ mục

Giả sử bảng giao dịch có cấu trúc:

```sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    status       TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL
);

CREATE INDEX idx_orders_customer_created
    ON orders (customer_id, created_at);

CREATE INDEX idx_orders_created_at
    ON orders (created_at);

CREATE INDEX idx_orders_total_amount
    ON orders (total_amount);
```

Với chỉ mục B-tree trên `created_at`, các giá trị được tổ chức theo thứ tự khóa. Nếu bộ tối ưu có thể xác định **khoảng khóa cần tìm**, nó có cơ hội đi đến vùng phù hợp trong chỉ mục thay vì kiểm tra mọi dòng. Chẳng hạn:

```sql
SELECT id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-02 00:00:00+07'
ORDER BY created_at;
```

Điều kiện `customer_id = 42` kết hợp khoảng thời gian phù hợp với thứ tự khóa của `idx_orders_customer_created`: tra theo `customer_id` rồi quét khoảng `created_at` trong nhóm khách hàng đó. Đây là ví dụ của một điều kiện **có thể dùng để tìm kiếm trên chỉ mục** (thường gọi là *sargable*: search-argument-able).

Tính sargable chỉ nói rằng bộ tối ưu *có khả năng* biến điều kiện thành thao tác tra cứu chỉ mục. Nó **không bảo đảm** DBMS sẽ chọn chỉ mục. Truy vấn trả về phần lớn bảng, bảng quá nhỏ, thống kê sai lệch hoặc chi phí đọc dữ liệu theo chỉ mục quá cao đều có thể khiến quét bảng hợp lý hơn.

## 2. Biểu thức trên cột có thể làm mất khả năng tìm theo khóa gốc

### 2.1. Hàm xử lý cột trong `WHERE`

Xem truy vấn lấy đơn hàng trong một ngày:

```sql
-- Dễ đọc nhưng khó tra theo B-tree thông thường trên created_at.
SELECT id, created_at
FROM orders
WHERE created_at::date = DATE '2026-11-01';
```

Chỉ mục hiện có sắp xếp theo **thời điểm đầy đủ** của `created_at`, còn điều kiện yêu cầu so sánh giá trị **sau khi ép thành ngày**. DBMS thường không thể biến biểu thức này thành một khoảng khóa trên chỉ mục gốc một cách trực tiếp. Một số hệ quản trị hoặc phiên bản có quy tắc viết lại đặc biệt, nhưng không nên giả định chúng luôn áp dụng.

Nếu yêu cầu nghiệp vụ là ngày **01/11/2026 theo múi giờ Việt Nam**, diễn đạt trực tiếp bằng khoảng nửa mở:

```sql
SELECT id, created_at
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-02 00:00:00+07';
```

Khoảng `[đầu ngày, đầu ngày kế tiếp)` vừa dễ tra chỉ mục, vừa không phụ thuộc vào độ chính xác phần giây cuối ngày. Với `TIMESTAMPTZ`, phép `created_at::date` còn phụ thuộc vào múi giờ phiên PostgreSQL; dùng nó mà không xác định múi giờ nghiệp vụ có thể trả về ngày khác dự kiến. Với vùng có giờ mùa hè, hai mốc đầu ngày phải được tính theo *ngày lịch của vùng*, không mặc định cộng đúng 24 giờ.

Tình huống tương tự xảy ra với `LOWER(email)`, `TRIM(code)`, `ROUND(total_amount)`, `SUBSTRING(...)` hoặc biểu thức tính toán. Chỉ mục trên cột gốc lưu khóa của **giá trị gốc**, không mặc nhiên lưu khóa của mọi hàm có thể áp dụng lên giá trị đó.

### 2.2. Phép toán số học trên cột

```sql
-- Khó dùng trực tiếp idx_orders_total_amount để tìm ngưỡng.
SELECT id
FROM orders
WHERE total_amount * 2 >= 1000000;

-- Diễn đạt điều kiện tương đương với NUMERIC trong trường hợp này.
SELECT id
FROM orders
WHERE total_amount >= 500000;
```

Ở câu thứ hai, ngưỡng nằm bên phải phép so sánh và cột chỉ mục xuất hiện nguyên dạng. Tuy nhiên, **không tùy tiện biến đổi mọi biểu thức**: chia, làm tròn, tràn số, số thực dấu phẩy động, giá trị `NULL` và các quy tắc nghiệp vụ có thể khiến hai công thức tưởng tương đương cho kết quả khác nhau. Chỉ viết lại khi chứng minh được tính tương đương cho miền dữ liệu thực tế.

### 2.3. Các trường hợp cần nhận diện

| Điều kiện | Vấn đề tiềm ẩn | Hướng xử lý |
|---|---|---|
| `created_at::date = ...` | Chuyển cột thời gian thành ngày | So sánh bằng khoảng thời gian đúng múi giờ |
| `LOWER(email) = ...` | Chỉ mục thường trên `email` không lưu kết quả `LOWER` | Chuẩn hóa dữ liệu hoặc chỉ mục biểu thức `LOWER(email)` |
| `CAST(customer_id AS TEXT) = ...` | So sánh khóa dạng chuỗi thay vì `BIGINT` | Đưa tham số về `BIGINT`, giữ cột nguyên dạng |
| `total_amount * 2 >= ...` | Khóa trong B-tree là `total_amount`, không phải tích | Chuyển ngưỡng sang phía tham số nếu tương đương |
| `COALESCE(status, 'UNKNOWN') = ...` | Khóa tìm kiếm là kết quả biểu thức | Viết điều kiện trên cột gốc hoặc cân nhắc chỉ mục biểu thức |
| `email LIKE '%example.com'` | Mẫu bắt đầu bằng `%` không xác định tiền tố của B-tree | Chọn phương án tìm kiếm chuỗi phù hợp yêu cầu |

Một biểu thức nằm trong phần `SELECT` thường chỉ ảnh hưởng chi phí tính toán kết quả; vấn đề tra cứu khóa phát sinh rõ nhất khi biểu thức xuất hiện trong `WHERE`, điều kiện `JOIN` hoặc `ORDER BY`. Ví dụ, `SELECT LOWER(email) ... WHERE id = ?` vẫn có thể tra nhanh theo khóa chính `id`.

## 3. Kiểu dữ liệu quyết định ý nghĩa so sánh và đặc tính chỉ mục

Chỉ mục không chỉ lưu các byte. Nó dựa trên **quy tắc so sánh của kiểu dữ liệu, toán tử và collation** để sắp xếp hoặc đối chiếu khóa. Chọn sai kiểu có thể gây lỗi nghiệp vụ ngay cả khi truy vấn chạy nhanh.

### 3.1. Khóa định danh, chuỗi và thứ tự

Số `10` nhỏ hơn `2` là sai, nhưng chuỗi `'10'` có thể đứng trước `'2'` theo thứ tự từ điển. Do đó:

- Mã định danh có bản chất **số học** và cần phép so sánh số nên dùng kiểu số phù hợp, ví dụ `BIGINT`.
- Mã nghiệp vụ như `'00042'`, số điện thoại, mã bưu chính hoặc mã bên thứ ba cần giữ số 0 đầu và ký tự đặc biệt thường nên là **chuỗi**; không ép kiểu số chỉ vì nội dung trông giống số.
- `UUID` là định danh có cấu trúc riêng; không chọn kiểu `TEXT` chỉ để tránh ánh xạ UUID trong Java nếu DBMS hỗ trợ kiểu `UUID`.

Kích thước khóa cũng ảnh hưởng số khóa trên một trang chỉ mục, lượng I/O và chi phí ghi. Một trường văn bản dài và collation phức tạp có đặc tính khác khóa số cố định; nhưng không có quy tắc đơn giản rằng "kiểu nhỏ hơn luôn nhanh hơn" trong mọi workload.

### 3.2. Số chính xác và số gần đúng

`NUMERIC(14,2)` phù hợp với số tiền cần độ chính xác theo chữ số thập phân. `REAL`/`DOUBLE PRECISION` chứa giá trị gần đúng theo nhị phân; dùng phép so sánh bằng tuyệt đối với số thực có thể không phản ánh ý nghĩa nghiệp vụ. Một chỉ mục có thể thực hiện so sánh đúng theo **kiểu đã lưu** nhưng vẫn không sửa được lỗi do làm tròn hoặc ràng buộc giá trị sai.

Với Java, tiền thường được biểu diễn bằng `BigDecimal` và truyền qua `PreparedStatement#setBigDecimal`; tránh chuyển qua `double` rồi kỳ vọng phép so sánh thập phân giữ nguyên độ chính xác.

### 3.3. Thời gian và múi giờ

Phân biệt `DATE` (ngày lịch), `TIMESTAMP WITHOUT TIME ZONE` (ngày giờ không gắn múi giờ) và `TIMESTAMPTZ` (thời điểm được chuẩn hóa để so sánh trên trục thời gian). Khi tìm sự kiện trong một ngày theo múi giờ của người dùng, hãy biến ngày lịch thành **hai thời điểm biên** trước khi so sánh cột thời điểm.

Không chuyển cột `created_at` sang chuỗi bằng `TO_CHAR` chỉ để lọc theo ngày. Việc định dạng thuộc phần trình bày; các điều kiện tra cứu nên dùng giá trị thời gian có kiểu đúng. Nếu dữ liệu vốn chỉ có độ chi tiết ngày, một cột `DATE` được mô hình hóa đúng có thể đơn giản hơn.

### 3.4. Collation và khớp chuỗi

Với `TEXT`/`VARCHAR`, collation và lớp toán tử quyết định cách các ký tự được sắp xếp và so khớp. Tùy DBMS/collation:

- `'A'` và `'a'` có thể được xem là khác hoặc tương đương trong một phép so sánh.
- Một chỉ mục B-tree cho so sánh bằng có thể không phục vụ được mọi kiểu tìm kiếm `LIKE` hay `ILIKE`.
- `LIKE 'abc%'` có khả năng khai thác phạm vi tiền tố với cấu hình chỉ mục phù hợp; `LIKE '%abc'` hoặc `LIKE '%abc%'` thường không thể tìm theo tiền tố bằng B-tree thông thường.

Trong PostgreSQL, một số collation yêu cầu lớp toán tử như `text_pattern_ops` để tăng khả năng dùng B-tree cho `LIKE 'prefix%'`. Tìm kiếm chuỗi con có thể cần chỉ mục trigram (`pg_trgm`) hoặc một phương án tìm kiếm chuyên biệt. Cần thống nhất từ đầu yêu cầu phân biệt hoa thường, dấu tiếng Việt, quy tắc chuẩn hóa Unicode và tính duy nhất của dữ liệu: thay collation hoặc cách chuẩn hóa có thể thay đổi cả kết quả lẫn khả năng sử dụng chỉ mục.

## 4. Chuyển đổi kiểu ngầm: không phải phép ép kiểu nào cũng giống nhau

Khi hai toán hạng khác kiểu, DBMS có thể **suy ra kiểu của literal hoặc tham số**, ép kiểu một toán hạng, hoặc từ chối biểu thức. Điều quan trọng là: phép chuyển đổi diễn ra ở **phía giá trị tìm kiếm** hay **phía cột đã lập chỉ mục**, và sau chuyển đổi còn giữ được ý nghĩa so sánh ban đầu hay không.

### 4.1. Chuyển tham số về kiểu cột

Với `customer_id BIGINT`, cách viết có chủ đích là:

```sql
-- Truy vấn minh họa kiểu tham số trong SQL.
SELECT id
FROM orders
WHERE customer_id = CAST('42' AS BIGINT);
```

Cột `customer_id` giữ nguyên kiểu và giá trị tra cứu là `BIGINT`; bộ tối ưu có thể tra theo chỉ mục có cột đầu `customer_id`. Trong PostgreSQL, literal chuỗi chưa xác định kiểu như `'42'` thường được suy kiểu theo ngữ cảnh, nên `customer_id = '42'` **không nhất thiết làm mất chỉ mục**. Không được kết luận rằng hễ thấy dấu nháy quanh literal thì có quét bảng.

Trong SQL được gửi từ Java, có thể truyền tham số số ngay từ đầu (`setLong`) thay vì dựa vào khả năng ép kiểu của DBMS. Nếu cần `CAST`, đặt nó ở phía **tham số** với kiểu đích chính xác, sau khi kiểm soát dữ liệu đầu vào.

### 4.2. Chuyển cột về kiểu tham số

```sql
-- Phép CAST trên cột có thể ngăn phép tìm theo khóa BIGINT thông thường.
SELECT id
FROM orders
WHERE CAST(customer_id AS TEXT) = '42';
```

Ở đây, điều kiện so sánh kết quả hàm `CAST` thay vì khóa số được lưu trong B-tree. Cũng cần chú ý: biểu thức `'42'`, `'042'` và khoảng trắng có thể có quy tắc so sánh chuỗi khác phép so sánh số, nên việc thay đổi kiểu không chỉ là tối ưu hiệu năng.

Một ví dụ khác trong **MySQL**: nếu `external_code` là `VARCHAR`, truy vấn `external_code = 123` có thể dẫn đến so sánh sau khi chuyển chuỗi thành số. Điều này có nguy cơ vừa làm giảm khả năng tra chỉ mục, vừa khiến các chuỗi khác nhau bị coi là tương đương theo quy tắc chuyển đổi số. Đúng hơn là so sánh với tham số chuỗi, chẳng hạn `external_code = '123'`, nếu mã nghiệp vụ được định nghĩa là chuỗi. PostgreSQL có thể từ chối một số cặp kiểu không có toán tử tương thích, thay vì tự chuyển đổi như MySQL.

### 4.3. Ép kiểu không phải lúc nào cũng làm mất chỉ mục

Không có quy tắc phổ quát "có `CAST` là không dùng index". DBMS có thể giản lược một phép chuyển đổi không đổi giá trị, lựa chọn toán tử phù hợp hoặc sử dụng một chỉ mục biểu thức. Ngược lại, một so sánh viết rất gọn vẫn có thể bị ép kiểu ngầm ở phía cột. Vì vậy phải xem **kiểu thực tế** của cột, kiểu của bind parameter, toán tử được chọn và kế hoạch thực thi trên hệ quản trị đang dùng.

Các khác biệt thường khó nhận ra giữa môi trường phát triển và production khi dữ liệu tăng mạnh, thay đổi driver JDBC hoặc nâng phiên bản DBMS. Kiểm thử chức năng chỉ xác nhận kết quả trả về đúng; không cho biết bộ tối ưu đã phải duyệt bao nhiêu dữ liệu để tìm kết quả đó.

## 5. Chỉ mục biểu thức: khi biến đổi cột là yêu cầu thật sự

Đôi khi ứng dụng **cần** truy vấn theo một biểu thức, ví dụ tìm email không phân biệt chữ hoa/chữ thường. Khi đó có thể lưu kết quả biểu thức trong một chỉ mục chuyên dụng.

```sql
CREATE TABLE customers (
    id            BIGINT PRIMARY KEY,
    email         TEXT NOT NULL,
    external_code TEXT NOT NULL
);

CREATE INDEX idx_customers_email ON customers (email);
CREATE INDEX idx_customers_external_code ON customers (external_code);

-- Chỉ mục của biểu thức, hỗ trợ tra cứu theo LOWER(email).
CREATE INDEX idx_customers_email_lower ON customers (LOWER(email));

SELECT id, email
FROM customers
WHERE LOWER(email) = LOWER('Lan.Nguyen@example.com');
```

`idx_customers_email` lưu khóa email gốc; `idx_customers_email_lower` lưu khóa đã qua `LOWER`. Với truy vấn cuối, bộ tối ưu có thể dùng chỉ mục biểu thức khi điều kiện, toán tử và ngữ cảnh so khớp tương thích với định nghĩa chỉ mục. Cách xử lý chữ hoa/chữ thường còn phụ thuộc collation và yêu cầu chuẩn hóa email cụ thể.

Có ba chiến lược phổ biến:

| Chiến lược | Khi phù hợp | Đánh đổi |
|---|---|---|
| So sánh trên cột gốc với tham số đúng kiểu | Có thể diễn đạt điều kiện thành `=`, `<`, `>=`, khoảng giá trị | Đơn giản, tái sử dụng chỉ mục; cần đảm bảo tương đương ngữ nghĩa |
| Chỉ mục biểu thức như `LOWER(email)` | Truy vấn lặp lại trên một biến đổi ổn định, được DBMS hỗ trợ | Tốn dung lượng và chi phí cập nhật; truy vấn phải có biểu thức tương thích |
| Cột chuẩn hóa hoặc cột sinh (*generated column*) rồi lập chỉ mục | Nhiều truy vấn hoặc hệ thống cần dùng chung giá trị đã chuẩn hóa | Phải định nghĩa và duy trì quy tắc chuẩn hóa, ràng buộc và migration |

Trong PostgreSQL có thể tạo chỉ mục duy nhất trên `LOWER(email)` nếu nghiệp vụ yêu cầu tính duy nhất không phân biệt hoa thường, nhưng phải kiểm tra dữ liệu trùng sẵn có trước khi tạo. Không phải biểu thức nào cũng hợp lệ để lập chỉ mục: PostgreSQL yêu cầu các hàm tham gia biểu thức chỉ mục có tính **IMMUTABLE** theo quy tắc của nó. Những phép xử lý phụ thuộc múi giờ phiên, cấu hình hoặc trạng thái bên ngoài cần được đánh giá kỹ.

Chỉ mục biểu thức không phải giải pháp mặc định cho mọi điều kiện thiếu sargability. Nó bổ sung chi phí ghi khi `INSERT`/`UPDATE`, chiếm bộ nhớ đệm và dung lượng, đồng thời không thay thế việc chọn kiểu dữ liệu đúng. Nếu có thể viết điều kiện khoảng trực tiếp trên `created_at` như phần 2, đó thường là điểm xuất phát đơn giản hơn việc lập thêm chỉ mục ngày.

## 6. Liên kết với Java: kiểu tham số JDBC là một phần của thiết kế truy vấn

Trong lớp persistence, truy vấn SQL và kiểu bind parameter cần được thiết kế cùng nhau. Một bảng ánh xạ thực dụng:

| Kiểu cột PostgreSQL | Kiểu dữ liệu Java thường dùng | Cách bind JDBC phù hợp |
|---|---|---|
| `BIGINT` | `long`/`Long` | `setLong` hoặc `setObject` với kiểu phù hợp |
| `NUMERIC(p,s)` | `BigDecimal` | `setBigDecimal` |
| `TEXT`, `VARCHAR` | `String` | `setString` |
| `DATE` | `LocalDate` | `setObject` (driver hỗ trợ JDBC 4.2) |
| `TIMESTAMPTZ` | `OffsetDateTime` | `setObject` (với PostgreSQL JDBC hỗ trợ) |
| `UUID` | `UUID` | `setObject` với driver hỗ trợ UUID |

Ví dụ Java lọc đơn hàng theo **ngày lịch ở Việt Nam** và mã khách hàng số:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;

public void listOrdersForDay(Connection connection, long customerId, LocalDate day)
        throws SQLException {
    ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
    OffsetDateTime from = day.atStartOfDay(businessZone).toOffsetDateTime();
    OffsetDateTime until = day.plusDays(1)
            .atStartOfDay(businessZone).toOffsetDateTime();

    String sql = """
            SELECT id, created_at, total_amount
            FROM orders
            WHERE customer_id = ?
              AND created_at >= ?
              AND created_at < ?
            ORDER BY created_at
            """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, customerId); // Khớp BIGINT.
        statement.setObject(2, from);     // Khớp TIMESTAMPTZ.
        statement.setObject(3, until);

        try (ResultSet rows = statement.executeQuery()) {
            while (rows.next()) {
                // Ánh xạ kết quả sang đối tượng miền hoặc DTO phù hợp.
            }
        }
    }
}
```

`OffsetDateTime` được tính từ **đầu hai ngày liên tiếp theo múi giờ nghiệp vụ**, nên cả ngày có chuyển giờ mùa hè cũng được xác định đúng độ dài. Driver và hệ quản trị khác có thể yêu cầu kiểu temporal hoặc cách bind khác; ví dụ trên dành cho PostgreSQL JDBC hiện đại. Sử dụng `PreparedStatement` cũng giúp tách dữ liệu khỏi câu SQL, tránh ghép trực tiếp đầu vào vào truy vấn.

Một lỗi thiết kế là nhận `customerId` dưới dạng `String`, rồi viết `CAST(customer_id AS TEXT) = ?` để truy vấn chạy được với `setString`. Cách đúng là **xác thực và chuyển đổi ở ranh giới ứng dụng** rồi bind `BIGINT`; nếu đầu vào không hợp lệ, báo lỗi đầu vào thay vì sửa kiểu truy vấn bằng cách ép toàn bộ dữ liệu cột.

Nguyên tắc này cũng áp dụng cho ORM như JPA/Hibernate: xem SQL sinh ra và kiểu bind thực tế khi gặp truy vấn chậm. Kiểu khai báo trong entity, mapping `AttributeConverter`, hàm trong JPQL/Criteria, hoặc biểu thức SQL do ORM tạo ra đều có thể tác động đến khả năng tra chỉ mục. Không suy ra hiệu năng chỉ từ tên phương thức repository.

## 7. Đo kế hoạch thực thi thay vì đoán theo cú pháp

Trên PostgreSQL, sử dụng `EXPLAIN` để quan sát kế hoạch ước lượng; khi được phép thực thi truy vấn, dùng `EXPLAIN (ANALYZE, BUFFERS)` để xem số dòng thực tế và lượng đọc bộ đệm:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-02 00:00:00+07';
```

Khi đọc kế hoạch, hãy kiểm tra:

1. **Node truy cập:** `Index Scan`, `Index Only Scan`, `Bitmap Index Scan` hay `Seq Scan`? Một `Seq Scan` không mặc nhiên là lỗi nếu lọc phần lớn bảng.
2. **`Index Cond` và `Filter`:** điều kiện nào được dùng để xác định khóa trong chỉ mục, điều kiện nào chỉ được kiểm tra sau khi đọc dòng? Trong một số kế hoạch, việc đánh giá biểu thức được đẩy sang vị trí khác, nên cần đọc toàn cây thay vì chỉ một dòng.
3. **Ước lượng và thực tế:** chênh lệch lớn giữa `rows` ước lượng và `actual rows` có thể báo hiệu thống kê cũ, phân bố dữ liệu lệch hoặc điều kiện khó ước lượng.
4. **Chi phí thực tế:** số dòng đọc rồi loại, số trang `shared hit/read`, thời gian và mức độ đọc heap. `Index Only Scan` cũng có thể cần truy cập heap tùy visibility map của PostgreSQL.

`EXPLAIN ANALYZE` **thực sự chạy câu lệnh**; với thao tác ghi phải đặc biệt cẩn trọng. Khi so sánh hai cách viết, hãy dùng cùng dữ liệu, thống kê đủ mới, cùng kiểu tham số và workload đại diện. Kế hoạch cho literal cụ thể có thể khác kế hoạch của prepared statement do cách hệ quản trị ước lượng tham số và lựa chọn kế hoạch tổng quát.

Đừng chỉ tối ưu để một chỉ mục xuất hiện trong output. Đích cuối cùng là giảm tổng chi phí truy vấn dưới tải thật mà không làm hại các thao tác ghi, migration hoặc các truy vấn quan trọng khác.

## 8. Tình huống tổng hợp: tra đơn hàng chậm sau khi bổ sung bộ lọc

Một API Java tra đơn hàng theo khách hàng và ngày phát sinh. Bảng đã có `idx_orders_customer_created`, nhưng lập trình viên viết:

```sql
SELECT id, created_at, total_amount
FROM orders
WHERE CAST(customer_id AS TEXT) = :customerId
  AND created_at::date = :day;
```

Hai cột khóa đều bị biến đổi trước khi so sánh. `customerId` truyền dạng chuỗi, còn `day` thiếu định nghĩa múi giờ; ứng dụng có thể vừa tăng số dòng phải kiểm tra, vừa lấy sai đơn hàng quanh nửa đêm.

Hướng sửa tại lớp persistence:

1. Xác thực `customerId` là khóa số hợp lệ và bind bằng `BIGINT`.
2. Xác định múi giờ của yêu cầu (ví dụ `Asia/Ho_Chi_Minh`), tính hai mốc đầu ngày liên tiếp bằng `ZonedDateTime`/`OffsetDateTime`.
3. Viết `customer_id = ? AND created_at >= ? AND created_at < ?`; tận dụng thứ tự `(customer_id, created_at)` của chỉ mục hiện có.
4. Đối chiếu kết quả chức năng ở các thời điểm sát biên ngày, sau đó so sánh kế hoạch và thời gian trên dữ liệu đại diện.

Nếu API còn cần tìm kiếm email không phân biệt chữ hoa, đó là **một yêu cầu lọc khác**: cân nhắc chỉ mục `LOWER(email)` hoặc cột chuẩn hóa cho bảng khách hàng. Không tạo thêm chỉ mục chỉ vì thấy truy vấn có hàm; hãy đo tần suất truy vấn, độ chọn lọc, chi phí ghi và tính đúng đắn của quy tắc chuẩn hóa.

## 9. Nguyên tắc áp dụng khi thiết kế persistence

- **Giữ cột khóa ở dạng nguyên bản trong điều kiện tra cứu** nếu có thể, nhất là ở `WHERE` và `JOIN`; chuyển đổi literal hoặc bind parameter về đúng kiểu của cột.
- **Mô hình hóa đúng dữ liệu ngay từ schema**: mã số, mã chuỗi, tiền, ngày và thời điểm có quy tắc so sánh khác nhau. Tạo chỉ mục không cứu được một mô hình dữ liệu sai.
- **Xác định rõ ngữ nghĩa trước khi tối ưu**: múi giờ, collation, chuẩn hóa chữ, độ chính xác và hành vi `NULL` đều quyết định kết quả đúng.
- **Dùng chỉ mục biểu thức có chủ đích** khi truy vấn thực sự cần biểu thức và DBMS hỗ trợ; cân nhắc chi phí dung lượng và ghi.
- **Xác minh bằng kế hoạch truy vấn cùng dữ liệu thực tế**; không kết luận từ cú pháp `CAST`, từ tên index, hay từ một lần đo trên bảng nhỏ.

Khả năng dùng chỉ mục là kết quả của sự phối hợp giữa **schema, toán tử so sánh, kiểu tham số, biểu thức SQL và bộ tối ưu**. Trong hệ thống Java, ranh giới persistence cần chịu trách nhiệm giữ sự phối hợp đó ổn định khi API, dữ liệu và schema tiến hóa.
