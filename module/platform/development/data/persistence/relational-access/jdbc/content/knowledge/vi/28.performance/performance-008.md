# Đánh giá tương tác giữa kiểu tham số và kế hoạch truy vấn trong JDBC

Khi tối ưu truy vấn JDBC, nhiều người tập trung vào index, số hàng trả về hoặc kích thước connection pool, nhưng bỏ qua một chi tiết quan trọng: **kiểu dữ liệu mà `PreparedStatement` truyền cho dấu `?` có thể ảnh hưởng đến cách cơ sở dữ liệu suy luận biểu thức và chọn kế hoạch thực thi**. Hai câu truy vấn có cùng SQL text và cùng giá trị hiển thị có thể được database xử lý khác nhau khi một bên nhận số nguyên, bên kia nhận chuỗi; tương tự, một giá trị chuỗi Unicode có thể được biểu diễn khác với chuỗi `VARCHAR` thông thường.

Không phải mọi khác biệt kiểu tham số đều khiến truy vấn chậm. Một số hệ quản trị tự chuyển đổi kiểu mà vẫn dùng được index; một số khác phải chuyển đổi **giá trị cột**, làm giảm khả năng dùng index seek. Ngoài ra, **độ chọn lọc của giá trị tham số** còn có thể ảnh hưởng đến kế hoạch được biên dịch hoặc tái sử dụng, kể cả khi kiểu SQL đã hoàn toàn chính xác.

Bài thuộc chương **Hiệu năng** của module **JDBC**, với mục tiêu thực hành đánh giá tương tác giữa `DataSource`, `Connection`, `PreparedStatement`, các phương thức `setXxx`, kiểu cột SQL, driver, index và query optimizer. Ta sẽ kết hợp phân tích cơ chế, ví dụ Java có thể áp dụng, phương pháp đọc execution plan và quy trình thử nghiệm có kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt **kiểu Java**, **kiểu JDBC truyền/bind**, **kiểu cột SQL** và **kiểu mà DB thực sự dùng khi tối ưu câu lệnh**.
- Chọn `setLong`, `setString`, `setBigDecimal`, `setObject` và `setNull` phù hợp hợp đồng dữ liệu.
- Phát hiện chuyển đổi kiểu ngầm (*implicit conversion*) có thể ảnh hưởng biểu thức tìm kiếm và index.
- Giải thích vì sao tham số có độ chọn lọc khác nhau có thể dẫn đến kế hoạch truy vấn khác nhau hoặc kế hoạch cache không phù hợp.
- So sánh kế hoạch thực thi và thời gian chạy với **giá trị tham số đại diện**, không suy diễn từ một lần chạy.
- Nhận diện giới hạn riêng của PostgreSQL, SQL Server, Oracle, MySQL và JDBC driver khi phân tích kết quả.

## 1. Đường đi của một tham số từ Java tới query optimizer

Xét truy vấn:

```sql
SELECT account_id, email, credit_limit
FROM customer_account
WHERE account_id = ?;
```

Ứng dụng đặt tham số:

```java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 501L);
    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            // Đọc kết quả.
        }
    }
}
```

Quá trình từ ứng dụng đến kết quả có thể hình dung như sau:

```text
Java long / Long
       |
       v
PreparedStatement.setLong(1, 501L)
       |
       v
JDBC driver: biểu diễn tham số + giao thức truyền dữ liệu
       |
       v
DBMS: kiểu của marker ? trong ngữ cảnh câu SQL
       |
       v
So sánh với account_id BIGINT, quy tắc chuyển kiểu
       |
       v
Optimizer: thống kê, index, selectivity, execution plan
       |
       v
Thực thi, truy xuất hàng, trả ResultSet về Java
```

Một điểm rất quan trọng: **phương thức setter không phải lúc nào cũng ánh xạ 1–1 tới một kiểu wire-level hoặc một kiểu server duy nhất trên mọi driver**. Driver có thể dùng metadata của câu SQL, loại prepared statement phía server, thuộc tính kết nối hoặc cơ chế ép kiểu của DB. Vì thế, gọi `setLong` là cách diễn đạt rõ dự định truyền số nguyên 64 bit, nhưng muốn xác định server **thực sự** thấy kiểu nào phải khảo sát đúng driver và DB.

### Bốn loại thông tin không nên trộn lẫn

| Loại | Ví dụ | Nơi xác định |
| --- | --- | --- |
| Kiểu Java của giá trị | `long`, `String`, `BigDecimal`, `LocalDateTime` | Mã ứng dụng |
| Kiểu JDBC được yêu cầu qua setter | `setLong`, `setObject(..., Types.DECIMAL)` | Mã ứng dụng / JDBC API |
| Kiểu SQL của cột hoặc biểu thức | `BIGINT`, `VARCHAR(254)`, `DECIMAL(15,2)` | Schema và câu SQL |
| Kiểu nội bộ trong lúc so sánh/lập kế hoạch | Có thể là kiểu cột, kiểu tham số hoặc biểu thức sau chuyển đổi | DBMS, optimizer và driver |

Sự khác biệt giữa các tầng có thể làm **thay đổi ngữ nghĩa** (lỗi ép kiểu, làm tròn, timezone) trước khi tác động đến **hiệu năng**. Không nên sửa kiểu truyền chỉ để đạt index seek nếu việc sửa làm câu truy vấn trả kết quả khác.

## 2. Schema minh họa và những truy vấn quan trọng

Giả sử có bảng tài khoản:

```sql
CREATE TABLE customer_account (
    account_id    BIGINT PRIMARY KEY,
    email         VARCHAR(254) NOT NULL UNIQUE,
    account_state SMALLINT NOT NULL,
    credit_limit  DECIMAL(15, 2) NOT NULL,
    created_at    TIMESTAMP NOT NULL
);

CREATE INDEX idx_customer_account_state
    ON customer_account (account_state);

CREATE INDEX idx_customer_account_created_at
    ON customer_account (created_at);
```

Đây là **DDL minh họa gần SQL chuẩn**; cách khai báo index, `TIMESTAMP`, độ dài chuỗi và quy tắc collation có thể khác nhau giữa DBMS. Index trên `account_state` không mặc nhiên hữu ích nếu gần như mọi hàng đều có cùng trạng thái; index trên `created_at` cần được xét theo phạm vi thời gian mà ứng dụng truy vấn.

Các câu SQL cần đánh giá:

```sql
-- Khóa chính số nguyên 64 bit.
SELECT account_id, email FROM customer_account WHERE account_id = ?;

-- Khóa duy nhất chuỗi.
SELECT account_id, email FROM customer_account WHERE email = ?;

-- Cột số nguyên nhỏ có thể có dữ liệu phân bố không đều.
SELECT COUNT(*) FROM customer_account WHERE account_state = ?;

-- Cột thời gian, điều kiện phạm vi có thể dùng index.
SELECT COUNT(*) FROM customer_account
WHERE created_at >= ? AND created_at < ?;

-- Cập nhật chính xác giá trị thập phân.
UPDATE customer_account SET credit_limit = ? WHERE account_id = ?;
```

Hợp đồng tham số dự kiến:

| Cột | Kiểu SQL | Setter Java hợp lý | Điều cần kiểm tra |
| --- | --- | --- | --- |
| `account_id` | `BIGINT` | `setLong` | Tránh truyền ID như chuỗi tùy tiện |
| `email` | `VARCHAR(254)` | `setString`, với cơ chế chuỗi của driver phù hợp | Collation, cách driver truyền Unicode và chuyển kiểu |
| `account_state` | `SMALLINT` | `setShort` | Giá trị hợp lệ và độ chọn lọc của từng trạng thái |
| `credit_limit` | `DECIMAL(15,2)` | `setBigDecimal` | Chính xác thập phân, precision, scale |
| `created_at` | `TIMESTAMP` | `setObject(..., Types.TIMESTAMP)` hoặc `setTimestamp` | Kiểu timestamp, múi giờ và hỗ trợ JDBC 4.2 |

Lựa chọn setter không chỉ để “truy vấn nhanh”: nó phải phản ánh đúng **kiểu dữ liệu và quy tắc nghiệp vụ**. Index, statistics và dữ liệu thực tế mới quyết định optimizer sẽ dùng đường truy cập nào.

## 3. Chọn kiểu tham số nhất quán với cột SQL

### 3.1. `BIGINT`: không đổi ID thành chuỗi nếu không cần

```java
String sql = "SELECT email FROM customer_account WHERE account_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 501L);
    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            System.out.println(result.getString("email"));
        }
    }
}
```

Nếu thay `setLong(1, 501L)` bằng `setString(1, "501")`, một số DB có thể tự ép chuỗi sang số và vẫn dùng index; DB khác có thể cần ép kiểu khác, trả lỗi hoặc chọn kế hoạch không tối ưu. **Không có quy tắc phổ quát rằng truyền chuỗi luôn làm quét bảng**, nhưng việc ép kiểu không cần thiết làm tăng phụ thuộc vào driver và quy tắc chuyển kiểu của DBMS.

Đặc biệt, chuỗi `"00501"` hoặc `"501x"` không có ngữ nghĩa giống một ID số nguyên. Nếu đầu vào đến từ HTTP/JSON, hãy xác thực và chuyển nó sang `long` trước khi bind thay vì để DB quyết định cách chuyển đổi chuỗi không hợp lệ.

### 3.2. `DECIMAL`: dùng `BigDecimal` để bảo toàn giá trị

```java
BigDecimal amount = new BigDecimal("12345.60");
statement.setBigDecimal(1, amount);
```

`BigDecimal` diễn đạt số thập phân chính xác, phù hợp cột `DECIMAL(15,2)`. Ngược lại, `double` là số dấu phẩy động nhị phân; nhiều giá trị thập phân như `0.1` không thể biểu diễn chính xác dưới dạng này. Dùng `setDouble` cho tiền có thể làm xuất hiện sai khác khi chuyển đổi hoặc so sánh, ngoài khả năng khiến optimizer phải xử lý kiểu đầu vào khác với kiểu cột.

Để thực hiện phép gán chính xác đến hai chữ số:

```java
BigDecimal normalized = amount.setScale(
        2, java.math.RoundingMode.UNNECESSARY);
statement.setBigDecimal(1, normalized);
```

`setScale(..., UNNECESSARY)` cho phép bỏ những chữ số `0` dư nhưng từ chối trường hợp cần làm tròn thật sự. Với cột `DECIMAL(15,2)`, cần kiểm tra cả giá trị âm/dương theo nghiệp vụ và precision tổng; **metadata tham số của driver không thay thế ràng buộc schema**.

### 3.3. `SMALLINT`: bind rõ kiểu nhưng nhớ phân bố dữ liệu

```java
short state = 1;
statement.setShort(1, state);
```

Kiểu đúng là bước đầu. Nếu `account_state = 1` xuất hiện ở 95% hàng còn `account_state = 9` chỉ xuất hiện ở 0,1%, cùng một predicate `account_state = ?` có thể tối ưu theo hai cách rất khác nhau. Trường hợp này liên quan **selectivity và parameter-sensitive plans**, không phải lỗi kiểu tham số.

### 3.4. `TIMESTAMP` và kiểu ngày giờ Java

Với JDBC 4.2, một cách bind là:

```java
import java.sql.Types;
import java.time.LocalDateTime;

LocalDateTime from = LocalDateTime.of(2026, 1, 1, 0, 0);
statement.setObject(1, from, Types.TIMESTAMP);
```

Khi dùng `TIMESTAMP WITHOUT TIME ZONE` (hoặc cột có ngữ nghĩa thời gian địa phương tương ứng), `LocalDateTime` có thể là lựa chọn phù hợp. Với các cột lưu thời điểm tuyệt đối và có múi giờ, phải xác định hợp đồng `TIMESTAMP WITH TIME ZONE` / `OffsetDateTime`, UTC và hỗ trợ driver cụ thể. **Không chọn kiểu ngày giờ chỉ vì kế hoạch truy vấn trông đẹp hơn** nếu điều đó đổi ý nghĩa thời điểm.

Nếu driver không hỗ trợ binding `LocalDateTime` theo cách trên, một phương án tương thích truyền thống là `setTimestamp(index, Timestamp.valueOf(from))` khi hợp đồng thời gian phù hợp. Cần kiểm tra các ca ranh giới múi giờ và daylight-saving time với DB thực tế.

### 3.5. Khi cần `setObject` và kiểu SQL đích

`setObject(index, value)` tiện lợi nhưng có thể khiến driver phải suy luận kiểu từ lớp Java và ngữ cảnh SQL. Với các trường hợp mơ hồ, có thể đưa kiểu đích rõ ràng:

```java
statement.setObject(1, 501L, java.sql.Types.BIGINT);
statement.setObject(2, new BigDecimal("120.00"),
                    java.sql.Types.DECIMAL);
```

Đây là API chuẩn, nhưng khả năng chuyển đổi kiểu cụ thể vẫn phụ thuộc JDBC driver và DBMS. Không dùng `setObject` với một kiểu đích tùy tiện chỉ để tránh exception. Khi đã có setter chuyên biệt đơn giản như `setLong` hoặc `setBigDecimal`, nên ưu tiên cách viết dễ hiểu và dễ kiểm chứng.

## 4. Chuyển đổi kiểu ngầm và khả năng dùng index (*sargability*)

**Sargability** mô tả khả năng một điều kiện truy vấn được khai thác hiệu quả bởi cấu trúc truy cập như index. Một predicate đơn giản trên cột đã index thường là điểm bắt đầu tốt:

```sql
SELECT account_id
FROM customer_account
WHERE account_id = ?;
```

So với một phiên bản biến đổi **cột** trong điều kiện:

```sql
SELECT account_id
FROM customer_account
WHERE CAST(account_id AS VARCHAR(30)) = ?;
```

Ở câu thứ hai, DB có thể phải tính biểu thức `CAST(account_id AS VARCHAR(30))` trên nhiều hàng thay vì tìm kiếm trực tiếp trên index `account_id`. Nhưng mức ảnh hưởng vẫn tùy optimizer, index biểu thức, kiểu chuyển đổi và dữ liệu: **không khẳng định mọi hàm trên cột luôn vô hiệu hóa mọi index**.

### Chuyển đổi ở phía cột so với phía tham số

```text
Hướng thường mong muốn:
  Cột BIGINT đã index  =  tham số được bind/suy ra kiểu BIGINT
  DB có cơ hội tìm kiếm trực tiếp theo giá trị khóa

Hướng có thể gây hại:
  CONVERT/Cast(Cột BIGINT)  =  tham số VARCHAR
  DB có thể phải tính lại biểu thức trên nhiều giá trị cột
```

Một số DB tự chuyển đổi **tham số** sang kiểu cột mà không làm hỏng kế hoạch. DB khác có thể chuyển **cột** do thứ tự ưu tiên kiểu hoặc quy tắc so sánh. Vì thế, không đoán chiều chuyển đổi chỉ từ Java code; cần xem **execution plan** của câu truy vấn thực sự.

### Điều kiện thời gian: tránh bọc cột trong phép đổi ngày

Giả sử cần tìm dữ liệu được tạo trong ngày 2026-01-05:

```sql
-- Có thể khiến index created_at khó được khai thác trực tiếp:
SELECT account_id FROM customer_account
WHERE CAST(created_at AS DATE) = ?;

-- Một phạm vi nửa mở rõ ràng hơn:
SELECT account_id FROM customer_account
WHERE created_at >= ? AND created_at < ?;
```

Trong cách thứ hai, bind hai mốc timestamp bắt đầu ngày và bắt đầu **ngày tiếp theo**, theo đúng ngữ nghĩa múi giờ/schema. Với index trên `created_at`, DB có cơ hội thực hiện index range scan; đây vẫn **không phải cam kết** optimizer luôn chọn index nếu phần lớn bảng nằm trong phạm vi đó.

Các phép biến đổi như `LOWER(email)`, `TRIM(email)` hoặc `SUBSTRING(email, ...)` cũng có thể thay đổi khả năng dùng index thông thường. Nếu cần tìm kiếm theo biểu thức, hãy cân nhắc collation phù hợp, cột chuẩn hóa hoặc **index trên biểu thức** khi DB hỗ trợ, thay vì mặc định bỏ xử lý chuỗi cho nhanh.

### Chuyển đổi có thể làm sai kết quả trước khi làm chậm truy vấn

Ví dụ so sánh giá tiền `DECIMAL` với tham số dấu phẩy động, hoặc timestamp không rõ múi giờ, có thể dẫn tới khác biệt ở ranh giới điều kiện `<`, `<=`, `=`. Một kế hoạch chạy nhanh nhưng trả sai tập hàng **không phải tối ưu thành công**. Khi so sánh các cách binding, phải kiểm tra **giá trị và số hàng kết quả** trước khi so thời gian.

## 5. Chuỗi `VARCHAR`, `NVARCHAR` và Unicode: ví dụ nhạy cảm theo DB

Với các DBMS có phân biệt kiểu chuỗi Unicode và non-Unicode, sự khác biệt giữa `VARCHAR` và `NVARCHAR` có thể ảnh hưởng đến kiểu tham số mà server nhận và quy tắc so sánh với cột.

Ví dụ, trong **Microsoft SQL Server**, câu SQL dùng cột `email VARCHAR(254)` có index:

```sql
SELECT account_id
FROM dbo.customer_account
WHERE email = ?;
```

Tùy phiên bản/cấu hình Microsoft JDBC Driver, phương thức `setString` có thể gửi tham số bằng biểu diễn Unicode; `setNString` và thuộc tính driver liên quan tới cách gửi chuỗi cũng có vai trò riêng. Khi DB so sánh `NVARCHAR` với cột `VARCHAR`, **kiểu chuyển đổi, collation và kế hoạch truy cập index** có thể khác so với trường hợp cả hai cùng `VARCHAR`.

Điều cần tránh là kết luận quá đơn giản:

- Không phải “`setString` luôn gửi `VARCHAR`” trên mọi driver.
- Không phải “tham số Unicode luôn gây table scan” trên mọi collation và mọi kế hoạch SQL Server.
- Không phải thay `setNString` bằng `setString` luôn giữ nguyên ngữ nghĩa của dữ liệu đa ngôn ngữ.

Quy trình đúng là kiểm tra **schema thật, collation, phiên bản driver, thuộc tính kết nối và execution plan thực tế**. Khi cần hỗ trợ Unicode, phải chọn thiết kế cột và kiểu tham số bảo toàn dữ liệu; không hy sinh dữ liệu tiếng Việt chỉ để đạt một index seek.

Ở PostgreSQL, MySQL hay Oracle, hệ kiểu chuỗi, character set và quy tắc chọn operator/index khác SQL Server. Đừng áp dụng trực tiếp một mẹo cấu hình Microsoft JDBC Driver sang sản phẩm khác.

## 6. `NULL` và điều kiện tùy chọn cũng ảnh hưởng kế hoạch

Khi một trường lọc là tùy chọn, ứng dụng thường tạo truy vấn dạng:

```sql
SELECT account_id, email
FROM customer_account
WHERE (? IS NULL OR account_state = ?);
```

Nếu tham số đầu tiên là `NULL`, truy vấn bỏ qua điều kiện trạng thái. Nếu không `NULL`, phải gán **hai vị trí tương ứng** bằng các giá trị và kiểu thích hợp. Nhưng dạng `OR` dùng chung cho hai trường hợp có thể khiến optimizer khó chọn một kế hoạch tối ưu cho cả “lọc một trạng thái” và “không lọc”.

Một số DB/driver còn khó suy luận kiểu của marker trong biểu thức `? IS NULL`; ví dụ có thể cần `CAST(? AS SMALLINT)` hoặc khai báo rõ loại tham số khi hỗ trợ. **Đừng mặc định `setNull(1, Types.SMALLINT)` sẽ được mọi DB xử lý giống nhau** trong biểu thức tham số đứng độc lập.

Nếu chỉ có hai trường hợp, dùng hai SQL template cố định có thể rõ ràng hơn:

```java
String allSql = """
        SELECT account_id, email
        FROM customer_account
        ORDER BY account_id
        """;

String filteredSql = """
        SELECT account_id, email
        FROM customer_account
        WHERE account_state = ?
        ORDER BY account_id
        """;

// Không có filter -> tạo statement từ allSql.
// Có filter -> tạo statement từ filteredSql và setShort(1, state).
```

Điều này cho phép DB nhìn thấy hai cấu trúc predicate khác nhau và dễ thử nghiệm kế hoạch hơn. Đổi lại, mỗi SQL template có thể có cache entry riêng. Với tập điều kiện lọc lớn, cần xây SQL một cách có kiểm soát, giữ danh sách kiểu/giá trị tham số tương ứng và tránh ghép **giá trị người dùng** trực tiếp vào câu SQL.

Ngoài ra, nhớ rằng:

```sql
WHERE optional_column = NULL
```

không phải cách kiểm tra SQL `NULL`. Dùng `IS NULL` khi muốn tìm hàng có cột `NULL`; dấu `?` và `setNull` không tự thay đổi ngữ nghĩa ba giá trị của SQL.

## 7. Cùng kiểu, cùng SQL nhưng vẫn có thể khác kế hoạch: độ chọn lọc

Giả sử bảng có một triệu tài khoản:

```text
account_state = 1   -> 950.000 hàng (95%)
account_state = 9   ->   1.000 hàng (0,1%)
Các trạng thái khác  ->  49.000 hàng
```

Với truy vấn:

```sql
SELECT account_id
FROM customer_account
WHERE account_state = ?;
```

Giá trị `9` có độ chọn lọc cao: một đường truy cập bằng index có thể hữu ích. Giá trị `1` trả phần lớn bảng: sequential/table scan có thể rẻ hơn việc đi qua index rồi truy xuất hàng loạt bản ghi. **Việc optimizer không dùng index chưa chắc là lỗi.**

Nhiều DBMS dùng histogram, thống kê phân bố, cardinality estimates và thông tin truy vấn để chọn kế hoạch. Nếu thống kê cũ hoặc không phản ánh dữ liệu thật, optimizer có thể ước lượng sai số hàng. Khi chẩn đoán, hãy so **estimated rows** với **actual rows** nếu công cụ execution plan của DB hỗ trợ.

### Kế hoạch dùng lại có thể không tối ưu cho mọi giá trị

Prepared statement và plan cache giúp tránh lập kế hoạch lặp lại, nhưng một kế hoạch được chọn cho giá trị hiếm chưa chắc tối ưu cho giá trị phổ biến. Ngược lại, kế hoạch scan được chọn cho giá trị phổ biến có thể rất chậm khi giá trị mới chỉ khớp vài hàng.

Những cơ chế cần biết, với tên và hành vi phụ thuộc DBMS:

| Hệ quản trị | Khái niệm cần khảo sát | Không nên suy diễn |
| --- | --- | --- |
| **SQL Server** | *Parameter sniffing*, parameter-sensitive plan optimization, plan cache | Mọi kế hoạch cache đều xấu hoặc mọi DB phiên bản đều dùng chung một kế hoạch |
| **PostgreSQL** | Custom plan so với generic plan cho prepared statement; quyết định tùy cơ chế prepared statement và thống kê | `EXPLAIN` cho một literal luôn phản ánh plan mà pgJDBC dùng lâu dài |
| **Oracle** | Bind variable peeking, adaptive cursor sharing và cơ chế optimizer theo phiên bản | Một bind variable luôn buộc dùng đúng một plan mãi mãi |
| **MySQL** | Optimizer, prepared-statement behavior và cách server/driver xử lý tham số | Mọi đặc tính plan cache của SQL Server/PostgreSQL đều tồn tại giống hệt |

Việc JDBC driver dùng **server-side prepared statement** hay chỉ chuẩn bị theo cách khác cũng có thể ảnh hưởng đường đi của câu SQL. Ví dụ một số driver có ngưỡng hoặc thuộc tính cấu hình để quyết định thời điểm chuẩn bị phía server. **Một lần gọi `Connection.prepareStatement(...)` không tự khẳng định DB đã tạo server prepared statement và đang tái dùng một plan cụ thể.**

Để đánh giá thực tế, cần kiểm tra DBMS, driver, cấu hình prepare, số lần thực thi, các giá trị bind đã dùng và kế hoạch được quan sát **trong bối cảnh thực thi thực tế**, không chỉ qua một câu SQL chạy thủ công trong công cụ quản trị.

## 8. Ví dụ Java hoàn chỉnh: hợp đồng bind tường minh

Repository sau dùng Java 17+ và `DataSource`. Mục đích là giữ **SQL template ổn định, kiểu tham số rõ ràng và vòng đời tài nguyên ngắn**. Đây là baseline tốt để đo hiệu năng trước khi can thiệp vào kế hoạch truy vấn.

Tệp minh họa `AccountQueryRepository.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.time.LocalDateTime;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class AccountQueryRepository {
    private static final String FIND_BY_EMAIL = """
            SELECT account_id, email, credit_limit
            FROM customer_account
            WHERE email = ?
            """;

    private static final String COUNT_BY_STATE = """
            SELECT COUNT(*)
            FROM customer_account
            WHERE account_state = ?
            """;

    private static final String COUNT_CREATED_RANGE = """
            SELECT COUNT(*)
            FROM customer_account
            WHERE created_at >= ? AND created_at < ?
            """;

    private static final String UPDATE_CREDIT = """
            UPDATE customer_account
            SET credit_limit = ?
            WHERE account_id = ?
            """;

    public record Account(
            long id, String email, BigDecimal creditLimit) {
    }

    private final DataSource dataSource;

    public AccountQueryRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public Optional<Account> findByEmail(String email)
            throws SQLException {
        Objects.requireNonNull(email, "email");

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(FIND_BY_EMAIL)) {
            // Cột email khai báo VARCHAR trong schema minh họa.
            statement.setString(1, email);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Account(
                        rs.getLong("account_id"),
                        rs.getString("email"),
                        rs.getBigDecimal("credit_limit")));
            }
        }
    }

    public long countByState(short state) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(COUNT_BY_STATE)) {

            statement.setShort(1, state);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("COUNT query returned no row");
                }
                return rs.getLong(1);
            }
        }
    }

    public long countCreatedBetween(
            LocalDateTime fromInclusive,
            LocalDateTime toExclusive) throws SQLException {

        Objects.requireNonNull(fromInclusive, "fromInclusive");
        Objects.requireNonNull(toExclusive, "toExclusive");
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time interval");
        }

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(COUNT_CREATED_RANGE)) {

            // JDBC 4.2; xác minh hỗ trợ java.time của driver.
            statement.setObject(1, fromInclusive, Types.TIMESTAMP);
            statement.setObject(2, toExclusive, Types.TIMESTAMP);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("COUNT query returned no row");
                }
                return rs.getLong(1);
            }
        }
    }

    public boolean updateCreditLimit(long id, BigDecimal rawAmount)
            throws SQLException {
        Objects.requireNonNull(rawAmount, "rawAmount");
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }

        final BigDecimal amount;
        try {
            amount = rawAmount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException failure) {
            throw new IllegalArgumentException(
                    "Credit limit must fit scale 2 exactly", failure);
        }
        if (amount.signum() < 0 || amount.precision() > 15) {
            throw new IllegalArgumentException(
                    "Credit limit is outside DECIMAL(15,2) range");
        }

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(UPDATE_CREDIT)) {

            statement.setBigDecimal(1, amount);
            statement.setLong(2, id);
            int updated = statement.executeUpdate();
            if (updated > 1) {
                throw new SQLException("Expected at most one account");
            }
            return updated == 1;
        }
    }
}
```

Cách gọi:

```java
AccountQueryRepository repository = new AccountQueryRepository(dataSource);

var account = repository.findByEmail("user@example.test");
long activeRows = repository.countByState((short) 1);

long created = repository.countCreatedBetween(
        LocalDateTime.of(2026, 1, 1, 0, 0),
        LocalDateTime.of(2026, 2, 1, 0, 0));

boolean updated = repository.updateCreditLimit(
        501L, new BigDecimal("15000.00"));
```

Điểm đáng chú ý:

| Quyết định trong mã | Lợi ích |
| --- | --- |
| SQL là hằng với placeholder `?` | Ổn định SQL template, tránh ghép dữ liệu không tin cậy vào SQL |
| `setShort` cho `SMALLINT` | Giao tiếp với schema có chủ đích |
| `setBigDecimal` cho `DECIMAL` | Không đưa lỗi số dấu phẩy động nhị phân vào giá trị tiền |
| `setObject(..., Types.TIMESTAMP)` | Nêu kiểu thời gian đích một cách tường minh |
| `created_at >= ? AND created_at < ?` | Tránh ép kiểu toàn bộ cột thời gian trong predicate |
| `try-with-resources` | Đóng `ResultSet`, statement và connection dù xảy ra lỗi |
| Không tự đo `EXPLAIN` ở mỗi request | Tránh overhead chẩn đoán trên đường chạy nghiệp vụ |

Mỗi phương thức thực hiện một câu SQL riêng; ví dụ không yêu cầu transaction nhiều câu lệnh. Nếu nghiệp vụ gồm nhiều `UPDATE` phải nguyên tử, đặt tất cả chúng trên **cùng một `Connection` với `autoCommit = false`**, và quản lý `commit()/rollback()` ở tầng chủ sở hữu transaction. **Kiểu bind đúng và execution plan tốt không thay thế transaction.**

## 9. Xem execution plan với giá trị bind đại diện

Để xác định kiểu tham số có làm đổi đường truy cập hay không, phải kiểm tra **kế hoạch truy vấn thực tế của DB**, không chỉ tốc độ quan sát từ phía Java. Có thể sử dụng:

| DBMS | Công cụ phổ biến | Cần quan sát |
| --- | --- | --- |
| PostgreSQL | `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)` | Seq Scan/Index Scan, ước lượng và số hàng thật, buffers, thời gian |
| SQL Server | Actual execution plan, `SET STATISTICS IO/TIME`, DMV/Query Store | Index Seek/Scan, `CONVERT_IMPLICIT`, estimate vs actual, logical reads |
| MySQL | `EXPLAIN`, `EXPLAIN ANALYZE` ở phiên bản hỗ trợ | Access method, rows examined, estimates và actual timing |
| Oracle | `DBMS_XPLAN`, execution statistics và công cụ theo dõi SQL | Access path, predicate information, bind-related behavior |

**Tên và khả năng của công cụ phụ thuộc phiên bản DBMS.** Không có một phương thức `PreparedStatement.getExecutionPlan()` chuẩn JDBC có thể trả kế hoạch giống nhau trên mọi DB.

### Ví dụ PostgreSQL: dùng `EXPLAIN` qua JDBC

Chỉ dùng ví dụ sau trong **môi trường thử nghiệm** có bảng dữ liệu tương ứng; nó tạo một câu `SELECT` để xem đường truy cập. Đoạn Java:

```java
String explainSql = """
        EXPLAIN (ANALYZE, BUFFERS)
        SELECT account_id, email
        FROM customer_account
        WHERE account_id = ?
        """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(explainSql)) {

    statement.setLong(1, 501L);

    try (ResultSet plan = statement.executeQuery()) {
        while (plan.next()) {
            System.out.println(plan.getString(1));
        }
    }
}
```

`EXPLAIN ANALYZE` trên PostgreSQL **thực sự chạy truy vấn** và thu thập thống kê. Ví dụ chỉ `SELECT` nên không ghi dữ liệu, nhưng bản thân truy vấn vẫn có thể nặng và cạnh tranh tài nguyên. Không chạy vô điều kiện với một câu `UPDATE`/`DELETE` của sản xuất: `EXPLAIN ANALYZE` cho DML có thể **thực thi và gây tác động dữ liệu** nếu không được cô lập/rollback đúng cách.

Các thông tin cần đọc:

- **Access path:** index lookup/scan hay sequential scan, cùng lý do chi phí của optimizer.
- **Estimated rows vs actual rows:** DB đoán bao nhiêu hàng và thật sự trả bao nhiêu.
- **Predicate / filter:** có xuất hiện ép kiểu cột trong điều kiện tìm kiếm hay không.
- **Buffers/IO:** chi phí đọc dữ liệu có giảm thật không.
- **Execution time:** đo nhiều lần, tránh kết luận từ kết quả có thể bị ảnh hưởng bởi buffer cache.

### Quan trọng: `EXPLAIN` thủ công chưa chắc giống plan của ứng dụng

Câu `EXPLAIN` chạy từ một `PreparedStatement` khác có thể được DB chuẩn bị và tối ưu theo ngữ cảnh **khác** với câu lệnh mà ứng dụng đã chạy hàng nghìn lần. Tương tự, một câu SQL có literal cố định trong công cụ quản trị có thể dùng custom plan, trong khi một prepared statement trên ứng dụng về sau dùng generic/cached plan.

Nếu đang điều tra parameter sniffing hoặc generic plan, cần **quan sát plan gắn với câu lệnh thực tế trong connection/session thực tế**, cùng cách chuẩn bị và các loại tham số. Các công cụ như Query Store, thống kê câu lệnh hoặc `EXPLAIN EXECUTE`/cơ chế prepared statement của DB cần được dùng theo sản phẩm, không suy diễn từ một bản chụp kế hoạch đơn lẻ.

## 10. Thiết kế phép thử so sánh kiểu tham số một cách có kiểm soát

Thay đổi từ `setLong` sang `setString` rồi thấy truy vấn nhanh/chậm hơn **không đủ chứng minh** kiểu tham số là nguyên nhân. Thời gian có thể thay đổi vì caches đã nóng, số hàng kết quả khác, connection khác, query plan được chuẩn bị lại hoặc DB đang chạy workload khác.

Một quy trình đáng tin cậy:

1. **Giữ nguyên schema, index và statistics** trong lúc so sánh hai biến thể; ghi nhận bản DDL và kiểu cột thật.
2. **Chọn dữ liệu đại diện:** giá trị phổ biến, giá trị hiếm, giá trị không tồn tại; với phạm vi thời gian, dùng cả khoảng hẹp và khoảng rộng.
3. **Giữ ngữ nghĩa kết quả giống nhau:** hai cách bind phải trả cùng tập hàng và cùng giá trị, nếu không thì phép so sánh hiệu năng không hợp lệ.
4. **Ghi nhận SQL template, setter và loại Java:** `setLong`, `setString`, `setObject(..., Types.X)`, `setNull` và vị trí tham số.
5. **Ghi nhận DBMS, JDBC driver, phiên bản, collation và cấu hình prepared statement** (có/không server-side preparation, pooling/caching).
6. **Warm-up có kiểm soát**, rồi đo nhiều lượt và phân bố độ trễ; tách biến động do khởi động, tạo connection và chuẩn bị statement.
7. **Thu kế hoạch và statistics:** estimated/actual rows, index access, filter, IO, server CPU nếu có.
8. **So sánh toàn bộ vòng đời truy vấn:** chuẩn bị, thực thi, truyền `ResultSet`, ánh xạ dữ liệu và đóng tài nguyên.
9. **Lặp lại dưới tải đồng thời** gần thực tế; kiểm tra plan cache và giới hạn connection pool.
10. Chỉ áp dụng thay đổi nếu **đúng kết quả, cải thiện ổn định và không tạo rủi ro dữ liệu**.

Một bảng ghi thử nghiệm:

| Biến thể | Loại bind | Giá trị chọn mẫu | Kết quả đúng? | Plan / IO / thời gian |
| --- | --- | --- | --- | --- |
| A | `setLong(1, 501L)` cho `BIGINT` | ID tồn tại | Cần xác minh | Đo trên DB thật |
| B | `setString(1, "501")` cho `BIGINT` | Cùng ID | Cần xác minh | Đo trên DB thật; có thể bị chuyển kiểu |
| C | `setShort(1, (short) 1)` | Trạng thái phổ biến | Cần xác minh | Đo selectivity cao/thấp |
| D | `setShort(1, (short) 9)` | Trạng thái hiếm | Cần xác minh | So với kế hoạch được tái sử dụng |
| E | `setBigDecimal(1, price)` | Giá `DECIMAL` chuẩn | Cần xác minh | Kiểm tra chính xác và plan |
| F | `setObject(..., Types.TIMESTAMP)` | Phạm vi ngày | Cần xác minh | So với ép kiểu trên cột |

Không có con số hiệu năng bịa sẵn trong bảng. Kết quả phải đến từ benchmark/`EXPLAIN` trên đúng DB. Nếu không thấy chênh lệch đáng kể, **giữ cách bind đúng kiểu và mã đơn giản** thay vì thêm logic tối ưu đặc thù.

### Đo từ phía Java chưa cho biết chi phí nằm ở đâu

```java
long startNanos = System.nanoTime();

try (PreparedStatement statement = connection.prepareStatement(SQL)) {
    statement.setLong(1, id);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            // Tiêu thụ kết quả theo cùng một cách ở mọi lần đo.
        }
    }
}

long elapsedNanos = System.nanoTime() - startNanos;
```

Đoạn này đo tổng thời gian Java gồm chuẩn bị, bind, server execution, network, fetch, mapping và đóng statement. Đây là số đo hữu ích cho người dùng, nhưng **không chỉ ra riêng query optimizer đã tốn bao nhiêu**. Để kết luận nguyên nhân, đối chiếu với metrics và actual execution plan ở DB.

Đừng đo một biến thể chỉ bằng `executeQuery()` không đọc `ResultSet`, còn biến thể kia lại duyệt hết hàng: cách đó so hai lượng công việc khác nhau, đặc biệt khi driver fetch dữ liệu theo đợt.

## 11. Ảnh hưởng của plan cache, connection pool và thống kê

Kiểu tham số còn tương tác với vòng đời của prepared statement:

```text
DataSource / pool
    |
    +-- Physical Connection A -> prepared statement / plan context A
    |
    +-- Physical Connection B -> prepared statement / plan context B
    |
    +-- Physical Connection C -> prepared statement / plan context C

Cùng SQL template nhưng:
 - có thể khác thời điểm prepare,
 - khác tham số đầu tiên hoặc độ chọn lọc,
 - khác session options và cache state,
 - khác kế hoạch DB đã chọn hoặc đang dùng lại.
```

Không phải mọi database đều giữ plan riêng trên từng connection, và cũng không phải mọi driver đều cache cùng một cách. Nhưng **đo một connection duy nhất** chưa chắc mô tả tải nhiều connection đang dùng pool.

Những câu hỏi khi quan sát:

- SQL đã được server-side prepare hay driver chỉ chuẩn bị theo cách ở client?
- Driver có đặt ngưỡng trước khi chuyển sang server-side prepared statement không?
- DB đang dùng generic/cached plan hay lập kế hoạch theo giá trị bind hiện tại?
- Thống kê phân bố dữ liệu đã được cập nhật gần đây và đủ chi tiết chưa?
- Có nhiều kiểu bind khác nhau cho cùng một SQL template từ các code path khác không?
- Có những session options, collation hoặc schema khác nhau khiến plan bị phân mảnh không?
- Một giá trị rất phổ biến có gây regress cho những giá trị rất hiếm khi plan được dùng chung không?

**Prepared-statement cache là một vấn đề khác với query plan cache**. Driver/pool có thể cache metadata hoặc statement handle mà optimizer vẫn phải lập kế hoạch lại; DB cũng có thể chia sẻ plan cho câu SQL không xuất phát từ `PreparedStatement` theo cách riêng. Vì vậy, không lấy “cache hit ở pool” làm bằng chứng một execution plan đã được dùng lại.

### Khi cùng SQL có performance không ổn định

Nếu độ trễ thay đổi mạnh giữa các giá trị tham số, phân loại theo từng nhóm:

| Triệu chứng | Giả thuyết cần thử | Kiểm tra |
| --- | --- | --- |
| ID số nguyên đôi khi quét bảng | Có implicit conversion hoặc index không phù hợp | Plan predicate, schema, kiểu bind thực tế |
| Trạng thái phổ biến chậm, trạng thái hiếm nhanh | Khác selectivity là hợp lý | Actual rows, IO, thống kê, plan theo từng giá trị |
| Giá trị hiếm đột ngột chậm sau warm-up | Plan cache/generic plan không phù hợp | Kế hoạch trước/sau nhiều lượt execute, cơ chế DB |
| Cột email `VARCHAR` chạy khác theo cấu hình driver | Unicode/collation/type conversion | Loại tham số server thấy, index predicate, cấu hình driver |
| Truy vấn mốc thời gian bỏ qua index | Ép kiểu cột hoặc phạm vi quá rộng | So SQL dạng phạm vi với CAST cột, actual rows |
| Mọi giá trị cùng chậm ở peak load | Pool/lock/IO/CPU thay vì kiểu tham số | Wait stats, pool metrics, latency server |

Đừng chỉ sửa câu SQL bằng `CAST` để ép optimizer dùng index mà bỏ qua nguyên nhân thống kê, cardinality hoặc thiết kế index. **Không phải scan nào cũng là vấn đề cần sửa**.

## 12. Kiểu `NULL`, metadata và giới hạn kiểm chứng từ JDBC

Khi giá trị có thể `NULL`, truyền kiểu rõ ràng giúp giảm mơ hồ:

```java
if (email == null) {
    statement.setNull(1, java.sql.Types.VARCHAR);
} else {
    statement.setString(1, email);
}
```

Đoạn mã chỉ có ý nghĩa với **tham số trong một câu SQL cho phép `NULL`**. Trong schema minh họa, `email` là `NOT NULL`; nếu ghi `NULL` vào cột đó, DB phải từ chối. Nếu predicate là `email = ?`, bind `NULL` **không** tìm những hàng có email `NULL`; dùng `IS NULL` theo ngữ nghĩa SQL.

Có thể khảo sát `ParameterMetaData`:

```java
var parameterMeta = statement.getParameterMetaData();
int count = parameterMeta.getParameterCount();
int sqlType = parameterMeta.getParameterType(1);
```

Nhưng **`ParameterMetaData` có thể không được driver hỗ trợ đầy đủ** hoặc trả kiểu không xác định khi marker nằm trong biểu thức. Không dùng `getParameterType(1)` làm nguồn sự thật duy nhất để chọn setter hay suy luận plan. Để xác nhận hiệu năng, cần biết cả:

- Kiểu cột từ DDL/`DatabaseMetaData`.
- Giá trị và setter ứng dụng đã dùng.
- Kiểu tham số mà DB thực sự suy ra/nhận được, nếu công cụ DB công bố.
- Biểu thức conversion và access path trong actual plan.

Một driver có thể ném `SQLFeatureNotSupportedException` ở một getter metadata dù `PreparedStatement` vẫn thực thi bình thường. Hãy tách lỗi introspection tùy chọn khỏi lỗi SQL thực sự; không bắt mọi `SQLException` từ `executeQuery()` rồi coi đó chỉ là metadata không hỗ trợ.

## 13. Những lỗi hiệu năng và tính đúng đắn thường gặp

| Cách làm | Rủi ro | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Truyền mọi tham số bằng `setString` | Ép kiểu không cần thiết, lỗi giá trị, plan phụ thuộc DB | Dùng setter theo kiểu SQL và nghiệp vụ |
| Dùng `setDouble` cho tiền `DECIMAL` | Sai khác biểu diễn thập phân và kiểu bind không mong muốn | Dùng `BigDecimal`/`setBigDecimal` |
| Đánh đồng `setString` với wire type `VARCHAR` | Cấu hình Unicode của driver có thể khác | Xác minh server thấy kiểu gì trên DB đích |
| Bọc cột index trong `CAST` không cần thiết | Có thể làm predicate kém sargable | Giữ cột ở kiểu gốc và bind kiểu phù hợp |
| Dùng `CAST(created_at AS DATE)` cho lọc ngày | Có thể làm khó index range seek | Dùng khoảng timestamp nửa mở khi đúng ngữ nghĩa |
| Dùng `(? IS NULL OR col = ?)` cho mọi bộ lọc | Plan chung có thể không tốt cho từng chế độ | Cân nhắc các SQL template ổn định theo trường hợp |
| Coi index scan/seq scan luôn tệ | Với kết quả rất lớn, scan có thể rẻ hơn index lookup | So estimated/actual rows, IO, tổng thời gian |
| Chỉ thử một giá trị tham số | Bỏ sót data skew và parameter-sensitive plan | Thử giá trị phổ biến, hiếm, không tồn tại |
| Dùng `EXPLAIN` literal để khẳng định plan của server-side prepare | Kế hoạch có thể khác bối cảnh JDBC thật | Kiểm tra session, bind, prepare và plan thực tế |
| Chỉ đo lần chạy đầu tiên | Bị ảnh hưởng bởi warm-up/caches/connection | Đo nhiều lượt và ghi lại điều kiện |
| So sánh hai binding nhưng trả số hàng khác nhau | Benchmark không cùng công việc và có thể sai dữ liệu | Xác minh kết quả trước khi so hiệu năng |
| Tối ưu kiểu bind bằng cách đổi timezone | Có thể trả sai mốc thời gian | Chọn đúng kiểu và ngữ nghĩa thời gian trước |
| Tin rằng `ParameterMetaData` luôn chính xác | Getter có thể trả `UNKNOWN` hoặc không hỗ trợ | Đối chiếu DDL và công cụ DB |
| Dùng SQL ghép chuỗi để “tránh prepare” | SQL injection, SQL template phân mảnh | Tiếp tục dùng `PreparedStatement` tham số hóa |
| Cache statement lớn mà không đo | Tăng memory/handle và giữ plan không phù hợp | Đo cả hiệu năng và ngân sách tài nguyên |
| Nuốt `SQLException` khi đổi setter | Che giấu lỗi kiểu/constraint/SQL | Giữ lỗi và sửa hợp đồng dữ liệu |

## 14. Kiểm thử tích hợp và tình huống thực hành

Kiểm thử phải thực hiện trên **DBMS, JDBC driver, version, collation, schema và tập dữ liệu** thực tế. Mock `PreparedStatement` giúp xác minh thứ tự setter, nhưng **không thể chứng minh** optimizer sẽ dùng index hay một implicit conversion cụ thể.

| Tình huống kiểm thử | Điều cần xác minh |
| --- | --- |
| `BIGINT` bind bằng `setLong` | Giá trị đúng, cùng kiểu cột kỳ vọng, plan hợp lý với index khóa chính |
| Truyền chuỗi cho cùng ID trong môi trường test | Kết quả tương đương hoặc bị từ chối đúng; có conversion nào xuất hiện? |
| Email `VARCHAR` trên SQL Server | Driver/collation thực tế có làm predicate conversion không? |
| `DECIMAL(15,2)` với `BigDecimal` | Giá trị chính xác, không làm tròn ngoài chính sách |
| Khoảng `created_at` hẹp và rộng | Số hàng và index/range scan được chọn có phù hợp statistics không? |
| Trạng thái hiếm vs phổ biến | Actual rows khác nhau; optimizer dùng plan gì sau warm-up? |
| Bind `NULL` cho điều kiện cho phép NULL | Ngữ nghĩa SQL đúng, kiểu tham số có được suy luận không? |
| Mở nhiều physical connections trong pool | Có khác biệt prepare/plan/độ trễ theo connection không? |
| Nâng cấp JDBC driver | Kết quả, kiểu parameter wire-level và plan có thay đổi không? |
| Cập nhật statistics/index trong môi trường test | So sánh estimate, plan và IO trước/sau có bằng chứng |
| Tải đồng thời cao | Phân biệt bottleneck CPU/IO/lock/pool với chi phí chuyển kiểu |

### Bài 1 — Hai kiểu cho một khóa chính

Một cột `account_id BIGINT` có index khóa chính. Hai phương thức gọi `setLong(1, 501L)` và `setString(1, "501")`. Có thể khẳng định phương thức thứ hai luôn tạo table scan không?

**Đáp án:** Không. Hành vi chuyển kiểu và plan phụ thuộc DBMS/driver. Nhưng `setLong` diễn đạt đúng hợp đồng số nguyên, tránh ép kiểu thừa. Cần xem plan và kiểm tra kết quả trên DB thật để xác định tác động.

### Bài 2 — Tìm lý do index không được chọn

Truy vấn `WHERE account_state = ?` có index, nhưng với tham số `1` thì DB chọn scan, với tham số `9` thì chọn index. Điều này chắc chắn là lỗi optimizer?

**Đáp án:** Không. Nếu `1` khớp gần cả bảng còn `9` khớp rất ít hàng, hai cách truy cập có thể hợp lý. So actual rows, chi phí IO và statistics; chỉ coi là vấn đề khi plan được chứng minh không phù hợp workload.

### Bài 3 — Biểu thức ngày giờ

Vì sao `CAST(created_at AS DATE) = ?` có thể kém hiệu quả hơn `created_at >= ? AND created_at < ?` trên một cột có index? Cần lưu ý điều gì để hai cách trả cùng kết quả?

**Gợi ý:** Phép CAST trên cột có thể giảm khả năng index range seek. Cần xác định mốc đầu/cuối ngày theo đúng timezone, precision và ngữ nghĩa của kiểu timestamp, rồi so kết quả.

### Bài 4 — Độ chính xác tài chính

Ứng dụng lưu hạn mức vào `DECIMAL(15,2)` nhưng dùng `setDouble` cho giá trị `0.1`. Vấn đề có thể phát sinh là gì ngoài thời gian truy vấn?

**Đáp án:** `double` có sai khác biểu diễn thập phân nhị phân. Dùng `BigDecimal` và quy tắc precision/scale rõ ràng; không đổi tính đúng đắn lấy tốc độ.

### Bài 5 — SQL Server và Unicode

Một query trên cột `VARCHAR` đổi kế hoạch khi thay cấu hình gửi tham số chuỗi của JDBC driver. Có thể khẳng định nguyên nhân là “Unicode luôn vô hiệu hóa index” không?

**Đáp án:** Không. Cần kiểm tra kiểu tham số thực tế, conversion direction, collation, index predicate và actual plan. Ảnh hưởng của Unicode không đồng nhất trên mọi cấu hình SQL Server.

### Bài 6 — Plan cache và tham số không đều

Một prepared statement chạy nhanh với trạng thái phổ biến nhưng rất chậm với trạng thái hiếm sau nhiều lần thực thi. Ngoài kiểu bind, cần khảo sát yếu tố gì?

**Gợi ý:** Plan cache, parameter sniffing/generic vs custom plan theo DB, dữ liệu phân bố lệch, statistics và số hàng ước lượng so với thực tế. Kiểm tra plan trong bối cảnh server-side prepare mà ứng dụng thật dùng.

### Bài 7 — `EXPLAIN` và DML

Tại sao không nên chạy `EXPLAIN ANALYZE UPDATE customer_account ...` trực tiếp trên dữ liệu sản xuất chỉ để đo kế hoạch?

**Đáp án:** Trên những DB như PostgreSQL, `EXPLAIN ANALYZE` có thể **thực thi câu lệnh DML**, gây tác động thật. Thử trong môi trường kiểm soát, dùng transaction/rollback theo hợp đồng DB và tránh đưa dữ liệu sản xuất vào rủi ro.

### Bài 8 — Kết luận từ một lần đo

Một lần gọi `setString` mất 3 ms, `setLong` mất 5 ms. Có thể kết luận `setString` nhanh hơn cho `BIGINT`?

**Đáp án:** Không. Cần so các lần chạy với kết quả tương đương, workload và cache ổn định, nhiều mẫu dữ liệu, plan, IO và phân bố độ trễ. Một số đo đơn lẻ không xác định nguyên nhân.

### Bài 9 — Điều kiện tùy chọn

Một API tìm kiếm có trạng thái lọc tùy chọn, và truy vấn hiện tại luôn dùng `(? IS NULL OR account_state = ?)`. Đề xuất cách làm khác để DB có thể tối ưu riêng hai chế độ.

**Gợi ý:** Dùng hai SQL template tham số hóa: không có `WHERE account_state` khi lọc bị bỏ qua, và `WHERE account_state = ?` với `setShort` khi có lọc. Kiểm tra hiệu năng/caching và tránh nối giá trị người dùng trực tiếp vào SQL.

## Tổng kết

Để **đánh giá tương tác giữa kiểu tham số và kế hoạch truy vấn** trong JDBC, hãy bắt đầu từ hợp đồng dữ liệu: cột `BIGINT` dùng kiểu số nguyên phù hợp, `DECIMAL` dùng `BigDecimal`, chuỗi và timestamp tuân theo kiểu SQL cũng như ngữ nghĩa Unicode/múi giờ của DB. Tiếp đó kiểm tra cách driver thực sự bind giá trị, liệu DB phải chuyển kiểu cột hay tham số, và predicate có còn phù hợp với index hay không. **Một kiểu bind đúng chưa đủ bảo đảm một plan luôn nhanh**: selectivity, statistics, generic/cached plan, dữ liệu phân bố lệch và cấu hình driver có thể thay đổi quyết định optimizer. Dùng `EXPLAIN`/actual execution plan, thử giá trị tham số đại diện, xác nhận kết quả tương đương và đo đạc nhiều lượt dưới tải phù hợp. Cuối cùng, giữ `PreparedStatement` tham số hóa, đóng `ResultSet`/statement/connection đúng cách và chỉ áp dụng tối ưu đặc thù DB khi có bằng chứng thực nghiệm.
