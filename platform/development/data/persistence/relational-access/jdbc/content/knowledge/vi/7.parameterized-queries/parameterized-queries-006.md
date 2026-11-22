# Xử lý chuyển đổi kiểu ngầm giữa Java, driver và cơ sở dữ liệu

## 1. Vì sao truy vấn tham số có thể gặp vấn đề về kiểu dữ liệu?

**JDBC (Java Database Connectivity)** là API Java để truy cập cơ sở dữ liệu quan hệ. Khi dùng `PreparedStatement`, ứng dụng truyền các **giá trị tham số** bằng `setInt`, `setLong`, `setString`, `setBigDecimal`, `setObject` và nhiều phương thức khác. Tuy nhiên, **kiểu của giá trị Java không tự động trùng với kiểu SQL của cột hoặc biểu thức nhận giá trị đó**.

Ví dụ, cột `customer_id` trong cơ sở dữ liệu có kiểu `BIGINT`, nhưng ứng dụng lại truyền chuỗi `"42"`:

```java
String sql = "SELECT name FROM customers WHERE customer_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "42"); // Chuỗi Java, trong khi cột là BIGINT.
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
```

Tùy driver và hệ quản trị cơ sở dữ liệu (**DBMS**), truy vấn có thể được chấp nhận nhờ **chuyển đổi kiểu ngầm** (*implicit type conversion/coercion*), hoặc bị từ chối do kiểu tham số không tương thích. Nếu được chấp nhận, cách chuyển kiểu cũng có thể ảnh hưởng đến kết quả so sánh, độ chính xác số, cách xử lý ngày giờ hoặc kế hoạch truy vấn.

Với cột `BIGINT`, cách ràng buộc phù hợp hơn thường là:

```java
statement.setLong(1, 42L);
```

Chuyển đổi ngầm đôi khi hữu ích, nhưng không nên dựa vào nó như hợp đồng chung cho mọi JDBC driver và DBMS.

## 2. Ba lớp kiểu dữ liệu tham gia vào một tham số

Một giá trị đi qua nhiều lớp trước khi được cơ sở dữ liệu sử dụng:

```text
Ứng dụng Java                  JDBC driver                    DBMS
────────────────              ───────────                    ─────────────────
Long / String /               Nhận setLong /                 Cột BIGINT,
BigDecimal / LocalDate ────► setString / setObject ────────► DECIMAL, DATE...
       │                            │                             │
       │                            │ chọn kiểu JDBC/             │ kiểm tra tương thích,
       │                            │ mã hóa/định dạng            │ ép kiểu khi được phép,
       │                            │ tham số theo giao thức      │ lưu trữ hoặc so sánh
       └────────────────────────────┴─────────────────────────────┘
```

Có thể phân biệt ba khái niệm:

| Lớp | Ví dụ | Ai quyết định? |
|---|---|---|
| **Kiểu Java** | `long`, `String`, `BigDecimal`, `LocalDate` | Mã ứng dụng và API setter được gọi |
| **Kiểu SQL/JDBC của tham số** | `BIGINT`, `VARCHAR`, `DECIMAL`, `DATE`; các mã `java.sql.Types` | Driver và lời gọi setter, đôi khi chịu ảnh hưởng từ ngữ cảnh SQL |
| **Kiểu trong cơ sở dữ liệu** | Cột `BIGINT`, biểu thức `NUMERIC(12,2)`, hàm nhận `DATE` | Schema, cú pháp SQL và quy tắc ép kiểu của DBMS |

JDBC định nghĩa các kiểu trong `java.sql.Types` để driver và ứng dụng có ngôn ngữ chung khi trao đổi dữ liệu. **`Types.BIGINT` không phải là lớp Java `Long`**; đó là mã biểu diễn kiểu SQL mong muốn. Đồng thời, tên và độ rộng thực tế của một số kiểu SQL có thể khác theo DBMS.

## 3. Cách các setter ảnh hưởng đến suy luận kiểu

Các phương thức setter mang theo ý định của ứng dụng. Một số ánh xạ JDBC thường gặp:

| Dữ liệu Java | Setter nên cân nhắc | Kiểu SQL thường tương ứng | Điều cần chú ý |
|---|---|---|---|
| `int` | `setInt(index, value)` | `INTEGER` | Có thể tràn phạm vi khi cột nhỏ hơn hoặc không tương thích |
| `long` | `setLong(index, value)` | `BIGINT` | Phân biệt số định danh với chuỗi mã có số `0` đầu |
| `BigDecimal` | `setBigDecimal(index, value)` | `DECIMAL` / `NUMERIC` | Cần kiểm soát precision và scale của cột |
| `double` | `setDouble(index, value)` | `DOUBLE` / số dấu phẩy động | Có rủi ro sai số biểu diễn khi dùng cho tiền |
| `String` | `setString(index, value)` | `VARCHAR` / kiểu chuỗi tương đương | Không bảo đảm chuỗi số hoặc ngày sẽ được ép sang kiểu khác |
| `boolean` | `setBoolean(index, value)` | `BOOLEAN` / `BIT` hoặc kiểu do driver ánh xạ | DBMS không thống nhất cách lưu boolean |
| `byte[]` | `setBytes(index, value)` | `VARBINARY` hoặc dạng nhị phân khác | Phân biệt dữ liệu bytes với văn bản mã hóa hex/base64 |
| `LocalDate` | `setObject(index, value)` với JDBC 4.2 | `DATE` | Driver phải hỗ trợ ánh xạ `java.time` tương ứng |
| `LocalDateTime` | `setObject(index, value)` với JDBC 4.2 | `TIMESTAMP` | Không chứa múi giờ hoặc UTC offset |
| `OffsetDateTime` | `setObject(index, value)` với JDBC 4.2 | `TIMESTAMP_WITH_TIMEZONE` | Hỗ trợ và hành vi chuẩn hóa offset khác theo DBMS |

Các ánh xạ trên biểu thị **hợp đồng phổ biến và ý định ràng buộc**, không phải cam kết DBMS sẽ nhận mọi giá trị hay mọi driver sẽ thực thi y hệt. Nếu kiểu cột thực tế khác kiểu tham số, DBMS vẫn có thể cần ép kiểu hoặc báo lỗi.

Vị trí tham số trong `PreparedStatement` **bắt đầu từ 1**, không phải 0. Ví dụ:

```java
String sql = "SELECT id FROM products WHERE category_id = ? AND price <= ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 12L);                  // category_id kiểu BIGINT
    statement.setBigDecimal(2, new BigDecimal("99.90")); // price DECIMAL
    // Sử dụng statement.executeQuery() khi cần đọc dữ liệu.
}
```

Ví dụ giả định đã import `java.math.BigDecimal`, `java.sql.PreparedStatement` và có `Connection` đang mở; kiểu cột mô tả là giả định của bài học.

## 4. Phân biệt chuyển kiểu trong Java, trong driver và trong DBMS

Cùng một câu truy vấn có thể phát sinh chuyển đổi ở các vị trí khác nhau:

1. **Ứng dụng Java chuyển trước khi bind**: `Long.parseLong(rawId)` biến chuỗi thành `long`; lỗi định dạng được phát hiện tại tầng Java.
2. **Driver ánh xạ giá trị khi bind**: `setObject(...)` hoặc `setString(...)` khiến driver chọn kiểu tham số, mã hóa dữ liệu và cách gửi tới DBMS.
3. **DBMS ép kiểu khi thực thi**: một kiểu tham số khác kiểu biểu thức/cột có thể được chuyển đổi theo quy tắc SQL của hệ quản trị.

Các bước này **không tương đương**. Ví dụ, Java `Long.parseLong("42")` bảo đảm giá trị đã là `long` trước khi gửi. Trong khi đó, `setString(1, "42")` đặt một giá trị chuỗi; việc DBMS có chấp nhận so sánh chuỗi với `BIGINT` hay không phụ thuộc ngữ cảnh và triển khai.

```java
String rawId = "42";
long customerId = Long.parseLong(rawId); // Java kiểm tra định dạng/phạm vi.

try (PreparedStatement statement = connection.prepareStatement(
        "SELECT name FROM customers WHERE customer_id = ?")) {
    statement.setLong(1, customerId);    // Bind theo ý định BIGINT.
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString(1));
        }
    }
}
```

`Long.parseLong(...)` có thể ném `NumberFormatException` nếu chuỗi không hợp lệ hoặc ngoài phạm vi `long`; đó là lỗi **ở Java**, khác với `SQLException` do DBMS/driver báo khi chuyển đổi dữ liệu không thành công.

Không nên chuyển mọi giá trị có vẻ là số sang `long`. Chẳng hạn mã hàng `"00042"`, số điện thoại hoặc mã bưu chính có thể là **định danh dạng chuỗi** và phải giữ số `0` ở đầu. Kiểu Java/SQL phải phản ánh ngữ nghĩa nghiệp vụ, không chỉ hình thức ký tự.

## 5. `setObject()` có thể thuận tiện nhưng không luôn đủ rõ ràng

`PreparedStatement.setObject(index, value)` cho driver ánh xạ kiểu từ đối tượng Java. Khi kiểu đích trong SQL rõ ràng, việc này có thể hoạt động tốt:

```java
statement.setObject(1, Integer.valueOf(42));
```

Tuy nhiên, **dùng `setObject()` với một giá trị không xác định rõ kiểu** có thể khiến ứng dụng phụ thuộc vào quy tắc suy luận của driver hoặc DBMS. Đặc biệt cẩn thận với chuỗi đại diện số, một kiểu Java được driver ánh xạ khác mong muốn, hoặc giá trị `null`.

Khi cần khai báo rõ kiểu SQL mong muốn, JDBC cung cấp biến thể có tham số kiểu:

```java
import java.sql.Types;

statement.setObject(1, Long.valueOf(42L), Types.BIGINT);
statement.setObject(2, new BigDecimal("18.50"), Types.DECIMAL);
```

Có thể dùng phiên bản nhận `SQLType` như `JDBCType.BIGINT` trên môi trường JDBC hiện đại, nếu driver triển khai. Một số biến thể `setObject` còn nhận **scale/length**, nhưng cần kiểm tra hợp đồng và giới hạn của loại dữ liệu cụ thể.

So sánh các cách bind vào cột `customer_id BIGINT`:

| Cách bind | Ý định truyền kiểu | Nhận xét |
|---|---|---|
| `setLong(1, 42L)` | `BIGINT` | Rõ ràng và thường phù hợp nhất |
| `setObject(1, 42L, Types.BIGINT)` | `BIGINT` | Có ích trong mã generic, cần chỉ định kiểu SQL |
| `setObject(1, 42L)` | Suy luận từ `Long` | Thường được ánh xạ phù hợp, vẫn phụ thuộc năng lực driver |
| `setString(1, "42")` | Chuỗi | Có thể cần ép kiểu ngầm; không đảm bảo giống ba trường hợp trên |

Đặc biệt, **placeholder `?` biểu diễn giá trị**, không phải tên bảng, tên cột hoặc schema. Không viết `SELECT * FROM ?` rồi mong JDBC tự biến một chuỗi thành định danh SQL; tên định danh động phải được chọn từ cấu hình hoặc danh sách cho phép và xây dựng câu SQL an toàn.

## 6. `NULL` là nơi suy luận kiểu dễ gặp sự cố

Trong Java, `null` tự nó **không cho biết phải gửi tham số SQL kiểu `INTEGER`, `DATE`, `VARCHAR` hay kiểu nào khác**. Đặc biệt với biểu thức SQL chưa rõ kiểu hoặc lời gọi procedure, driver có thể không đủ ngữ cảnh để xác định.

Không nên mặc định cách sau hoạt động thống nhất trên mọi driver:

```java
statement.setObject(1, null); // Không mô tả rõ kiểu SQL đích.
```

Khi biết kiểu SQL của cột/tham số, sử dụng `setNull()`:

```java
import java.sql.Types;

statement.setNull(1, Types.INTEGER); // Cột quantity kiểu INTEGER.
statement.setNull(2, Types.DATE);    // Cột due_date kiểu DATE.
statement.setNull(3, Types.VARCHAR); // Cột note kiểu VARCHAR.
```

Một lựa chọn khác là dùng `setObject` có chỉ định kiểu:

```java
statement.setObject(1, null, Types.INTEGER);
```

Ví dụ chèn ghi chú có thể `NULL`:

```java
String sql = "INSERT INTO tasks (task_id, note) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 1001L);
    if (note == null) {
        statement.setNull(2, Types.VARCHAR);
    } else {
        statement.setString(2, note);
    }
    statement.executeUpdate();
}
```

Giả định `task_id` có kiểu `BIGINT`, `note` là `VARCHAR` và biến `note` là `String` được truyền vào từ mã ứng dụng. Nếu cột có ràng buộc `NOT NULL`, bind `NULL` vẫn không hợp lệ và DBMS sẽ báo lỗi ràng buộc; chỉ định đúng kiểu tham số **không bỏ qua** quy tắc schema.

## 7. Số nguyên, số thập phân và sai số khó quan sát

Chuyển kiểu số không chỉ làm truy vấn thất bại, mà còn có thể **làm thay đổi giá trị** nếu số bị làm tròn hoặc không thể biểu diễn chính xác.

### 7.1. Giá trị tiền và `BigDecimal`

Với cột SQL `DECIMAL(12,2)` dùng cho số tiền, nên ưu tiên `BigDecimal`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("19.95");
BigDecimal normalized = amount.setScale(2, RoundingMode.UNNECESSARY);
statement.setBigDecimal(1, normalized);
```

`new BigDecimal("19.95")` giữ chính xác giá trị thập phân nhập bằng chuỗi. `setScale(2, RoundingMode.UNNECESSARY)` yêu cầu dữ liệu đã có thể biểu diễn chính xác ở hai chữ số thập phân; nếu phải làm tròn thì phát sinh `ArithmeticException` ngay tại Java. Trong ứng dụng cần làm tròn, hãy chọn **quy tắc nghiệp vụ cụ thể** (ví dụ `HALF_UP` hoặc `HALF_EVEN`) một cách chủ động.

Tránh cách tạo `BigDecimal` trực tiếp từ `double` nhị phân cho các giá trị tiền:

```java
BigDecimal problematic = new BigDecimal(0.1);   // Phản ánh giá trị double gần 0.1.
BigDecimal preferred   = new BigDecimal("0.1"); // Đúng 0.1 ở dạng thập phân.
```

Với `DECIMAL(12,2)`, precision `12` là tổng số chữ số thập phân và scale `2` là số chữ số ở phần lẻ; về mặt lý thuyết cột này lưu được tối đa mười chữ số trước dấu thập phân. **Cách xử lý khi giá trị vượt precision/scale** có thể là lỗi hoặc làm tròn theo quy tắc DBMS, chế độ SQL và driver. Không nên kỳ vọng mọi hệ thống sẽ tự làm tròn giống nhau.

### 7.2. Chuyển kiểu số nguyên và tràn phạm vi

Giả sử cột `quantity` là `INTEGER` nhưng giá trị Java là `long` ngoài phạm vi 32-bit:

```java
long quantity = 5_000_000_000L;
statement.setLong(1, quantity);
```

Driver có thể truyền tham số dưới dạng `BIGINT`, còn DBMS cần gán vào cột `INTEGER`. Kết quả có thể là lỗi ngoài phạm vi hoặc hành vi phụ thuộc hệ quản trị và cấu hình. Một cách phát hiện sớm tại Java là `Math.toIntExact(quantity)`, phương thức sẽ ném `ArithmeticException` nếu không biểu diễn được dưới dạng `int`:

```java
int safeQuantity = Math.toIntExact(quantity);
statement.setInt(1, safeQuantity);
```

Ngược lại, ép `(int) quantity` có thể âm thầm làm mất các bit cao và tạo ra một giá trị khác trước cả khi JDBC nhận dữ liệu.

## 8. Kiểu thời gian: chuyển đổi ngầm dễ làm lệch ngày giờ

Java và SQL có nhiều kiểu thời gian với ý nghĩa khác nhau. Đặc biệt cần phân biệt **ngày lịch**, **thời điểm cục bộ không có múi giờ** và **thời điểm có offset**.

| Java | Kiểu SQL/JDBC thường tương ứng | Ngữ nghĩa cần giữ |
|---|---|---|
| `LocalDate` | `DATE` | Ngày theo lịch, không có giờ hoặc offset |
| `LocalTime` | `TIME` | Giờ trong ngày, không có ngày hoặc offset |
| `LocalDateTime` | `TIMESTAMP` | Ngày giờ cục bộ, tự nó không xác định một thời điểm tuyệt đối trên UTC |
| `OffsetDateTime` | `TIMESTAMP_WITH_TIMEZONE` | Ngày giờ cùng offset so với UTC; hỗ trợ DBMS/driver có thể khác nhau |

Từ JDBC 4.2, API chuẩn hỗ trợ ánh xạ nhiều kiểu `java.time` qua `setObject()` và `getObject()`. Ví dụ cho cột `due_on DATE`:

```java
import java.time.LocalDate;

LocalDate dueOn = LocalDate.of(2026, 11, 20);
statement.setObject(1, dueOn);
```

Không nên gửi ngày dưới dạng chuỗi như `"20/11/2026"` và dựa vào việc DB tự nhận biết định dạng. Cách phân tích chuỗi ngày phụ thuộc định dạng, locale hoặc cài đặt phiên; lựa chọn an toàn hơn là phân tích/kiểm tra ở Java thành một kiểu `java.time` đúng rồi bind.

`LocalDateTime` **không mang múi giờ**, vì vậy không thể tự suy ra đó là thời điểm UTC hay giờ địa phương của người dùng. Trong khi đó, `OffsetDateTime` có offset nhưng cách DBMS lưu trữ/hiển thị giá trị có thể chuẩn hóa, thay đổi offset hiển thị hoặc không hỗ trợ đầy đủ kiểu SQL tương ứng. Đừng ngầm chuyển `Instant` sang `TIMESTAMP` trên mọi driver rồi xem đó là hợp đồng JDBC portable; cần xác định rõ cách chuyển đổi cho DBMS sử dụng.

Khi có yêu cầu lưu **thời điểm tuyệt đối**, hãy thống nhất kiểu SQL, driver, cấu hình múi giờ phiên và quy ước API. Khi chỉ cần **ngày đến hạn** hoặc ngày sinh, `LocalDate` + `DATE` thường phản ánh đúng ý nghĩa hơn việc chuyển qua `Timestamp` có thể kéo theo múi giờ.

## 9. Chuỗi ký tự, boolean và các kiểu đặc thù DBMS

Với cột số hoặc boolean, việc truyền chuỗi có thể tạo ra những khác biệt khó đoán:

```java
statement.setString(1, "true"); // Chuỗi, chưa chắc được nhận là BOOLEAN.
statement.setString(2, "0012"); // Chuỗi, chưa chắc nên chuyển sang số 12.
```

Nếu cột thực sự là boolean và driver/DBMS hỗ trợ ánh xạ chuẩn, dùng:

```java
statement.setBoolean(1, true);
```

Đối với cột ký tự, cũng cần xét độ dài, bộ mã Unicode, collation và các quy tắc so sánh. `setString()` không loại bỏ ràng buộc độ dài hoặc bảo đảm mọi DBMS so sánh chữ hoa/chữ thường giống nhau. Dùng `String` là lựa chọn phù hợp cho **mã có số 0 đầu**, điện thoại, mã bưu chính và các định danh mang tính văn bản.

Một số kiểu như JSON, UUID, mảng SQL, enum do DBMS cung cấp, kiểu địa lý hoặc kiểu người dùng định nghĩa **không có cách ánh xạ `setObject()` hoàn toàn giống nhau trên mọi driver**. Có thể phải dùng `SQLType`, `Types.OTHER`, đối tượng do driver cung cấp, `createArrayOf()` hoặc biểu thức ép kiểu SQL đặc thù. Khi phải đổi DBMS, kiểm thử các ánh xạ này riêng.

## 10. Ép kiểu tường minh trong SQL khi ngữ cảnh thiếu thông tin

Trong một số biểu thức hoặc lời gọi hàm, DBMS không có đủ ngữ cảnh để suy ra kiểu của placeholder `?`. Khi driver hỗ trợ cú pháp tương ứng, có thể **ép kiểu tường minh ở phía SQL**.

Ví dụ cú pháp `CAST` theo SQL phổ biến:

```sql
SELECT * FROM customers WHERE customer_id = CAST(? AS BIGINT);
```

Ứng dụng vẫn nên bind đúng kiểu:

```java
statement.setLong(1, 42L);
```

`CAST(? AS BIGINT)` có thể hữu ích khi cần nói rõ kiểu của **tham số hoặc biểu thức**. Nó không phải lý do để mặc định truyền mọi dữ liệu dưới dạng chuỗi rồi để DBMS xử lý. Một chuỗi không hợp lệ vẫn có thể gây lỗi ép kiểu.

Phân biệt hai tình huống:

```sql
-- Ép kiểu tham số (cột giữ nguyên kiểu gốc):
SELECT * FROM customers WHERE customer_id = CAST(? AS BIGINT);

-- Ép kiểu cột cho mỗi phép so sánh:
SELECT * FROM customers WHERE CAST(customer_id AS VARCHAR(30)) = ?;
```

Trong nhiều DBMS, **ép kiểu hoặc áp dụng hàm lên cột được đánh index** có thể làm thay đổi kế hoạch truy vấn và hạn chế sử dụng chỉ mục thông thường; còn so sánh cùng kiểu với cột thường dễ tối ưu hơn. Kế hoạch cụ thể vẫn phụ thuộc DBMS, chỉ mục, thống kê và bộ tối ưu. Dùng `EXPLAIN` hoặc công cụ kế hoạch truy vấn của hệ quản trị để xác minh, không suy luận hiệu năng chỉ từ cú pháp.

Trong ví dụ trên, tên `VARCHAR(30)` và cú pháp `CAST` chỉ mang tính minh họa; khả năng ép giữa kiểu dữ liệu và cách biểu diễn văn bản khác nhau theo DBMS.

## 11. Ví dụ đầy đủ: ghi dữ liệu với kiểu tham số khớp schema

Giả sử ứng dụng có bảng SQL sau (cú pháp định nghĩa bảng minh họa, có thể phải chỉnh cho DBMS cụ thể):

```sql
CREATE TABLE invoices (
    invoice_id BIGINT PRIMARY KEY,
    amount DECIMAL(12,2) NOT NULL,
    due_on DATE NOT NULL,
    note VARCHAR(200)
);
```

Đoạn repository sau ràng buộc **đúng kiểu Java/JDBC theo ý nghĩa cột**, kiểm soát scale của tiền và phân biệt giá trị `NULL`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.time.LocalDate;
import javax.sql.DataSource;

public final class InvoiceRepository {
    private final DataSource dataSource;

    public InvoiceRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int insert(long invoiceId, BigDecimal amount,
                      LocalDate dueOn, String note) throws SQLException {
        if (amount == null || dueOn == null) {
            throw new IllegalArgumentException("amount và dueOn không được null");
        }

        BigDecimal exactAmount = amount.setScale(2, RoundingMode.UNNECESSARY);
        String sql = "INSERT INTO invoices " +
                     "(invoice_id, amount, due_on, note) VALUES (?, ?, ?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, invoiceId);          // BIGINT
            statement.setBigDecimal(2, exactAmount);  // DECIMAL(12,2)
            statement.setObject(3, dueOn);            // DATE (JDBC 4.2)

            if (note == null) {
                statement.setNull(4, Types.VARCHAR);
            } else {
                statement.setString(4, note);
            }

            return statement.executeUpdate();
        }
    }
}
```

Đầu vào `amount = new BigDecimal("25.50")` và `dueOn = LocalDate.of(2026, 11, 30)` giữ nguyên ý nghĩa thập phân và ngày lịch. Nếu `amount` có hơn hai chữ số thập phân **không thể biểu diễn chính xác ở scale 2**, mã phát hiện sớm trước khi gửi xuống database. Nếu giá trị vượt tổng precision cho phép hoặc vi phạm ràng buộc khác, DBMS vẫn có thể báo `SQLException`.

Ví dụ giả định `DataSource` đã cấu hình phù hợp và driver hỗ trợ bind `LocalDate` theo JDBC 4.2. Trên môi trường cũ, có thể cần dùng `java.sql.Date.valueOf(dueOn)` với `setDate(...)` hoặc cơ chế tương đương được driver hỗ trợ.

## 12. Quan sát và chẩn đoán lỗi chuyển kiểu

Khi truy vấn gặp lỗi, cần xác định *giá trị mang kiểu gì tại mỗi lớp*, thay vì chỉ nhìn chuỗi message:

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Chuỗi `"abc"` được bind vào cột số | Không thể chuyển từ ký tự sang số | Kiểm tra kiểu đầu vào, setter và schema; chuyển kiểu/validate tại Java |
| Số ngoài phạm vi của cột | Overflow/tràn miền giá trị | Kiểm tra `INTEGER`/`BIGINT` và precision, dùng kiểm tra miền hợp lệ |
| Giá tiền bị thay đổi vài chữ số lẻ | Chuyển qua `double`, làm tròn scale hoặc quy tắc DBMS | Dùng `BigDecimal`, định nghĩa quy tắc scale/rounding nhất quán |
| Ngày giờ bị lệch | Ép chuỗi ngày, múi giờ hoặc mapping `TIMESTAMP` khác ý định | Xác định kiểu `java.time`, kiểu SQL, offset và timezone phiên |
| Câu SQL chạy trên DB này nhưng lỗi trên DB khác | Khác quy tắc implicit cast hoặc driver | Xác định DBMS/driver; bind đúng kiểu và ép kiểu tường minh khi cần |
| Truy vấn chậm sau khi thay kiểu tham số | DBMS thay kế hoạch, có thể phát sinh cast ở cột | Kiểm tra SQL thực tế, metadata và kế hoạch thực thi (`EXPLAIN`) |

Một `SQLException` có thể cung cấp `getMessage()`, `getSQLState()` và `getErrorCode()`. Lớp SQLState **`22`** thường liên quan đến lỗi dữ liệu (data exception), trong đó có các vấn đề chuyển đổi hoặc giá trị vượt phạm vi. Tuy nhiên, **mã SQLState chi tiết và cách driver phân loại lỗi không thống nhất tuyệt đối**; phải kết hợp với thông tin cột, kiểu tham số và tài liệu của DBMS.

Mẫu ghi nhận thông tin an toàn:

```java
try {
    statement.executeUpdate();
} catch (SQLException failure) {
    System.err.println("SQLState: " + failure.getSQLState());
    System.err.println("Vendor code: " + failure.getErrorCode());
    System.err.println("Bị lỗi khi bind amount kiểu DECIMAL, due_on kiểu DATE");
    throw failure;
}
```

Trong ví dụ này `statement` là `PreparedStatement` đang mở và đã bind tham số. Khi ghi log thực tế, không in mật khẩu, token, dữ liệu cá nhân hoặc toàn bộ câu SQL đã ghép giá trị nhạy cảm. Cần giữ stack trace và thông tin driver/schema đủ để chẩn đoán, tránh để người dùng cuối thấy thông báo lỗi SQL thô.

Có thể dùng `ResultSetMetaData` để đọc kiểu SQL của các cột trả về (`getColumnType`, `getColumnTypeName`) và thử `ParameterMetaData.getParameterType(index)` để tìm kiểu tham số. **Tuy nhiên `ParameterMetaData` không được mọi driver hỗ trợ đầy đủ**, đặc biệt với SQL phức tạp; không nên coi nó là cách thay thế cho schema và khai báo kiểu của ứng dụng.

## 13. Kiểm thử chuyển đổi kiểu trong hệ thống thật

Các thử nghiệm có giá trị thường gồm:

1. **Giá trị đúng kiểu**: `BIGINT` với `setLong`, `DECIMAL(12,2)` với `setBigDecimal`, `DATE` với `LocalDate`.
2. **Giá trị biên**: số cực đại/cực tiểu của `INTEGER`, `BIGINT`; số thập phân vừa và vượt precision/scale cho phép.
3. **`NULL`**: cột có/không có `NOT NULL`, thử `setNull(index, Types.X)` theo kiểu thực tế.
4. **Chuỗi không hợp lệ**: ký tự không phải số, định dạng ngày không hợp lệ, chuỗi có dấu phân tách theo locale.
5. **Ngày giờ**: thời điểm qua ranh giới ngày/múi giờ, đổi timezone phiên, dùng `LocalDate` so với `LocalDateTime` hoặc `OffsetDateTime` phù hợp.
6. **Hiệu năng**: so sánh truy vấn bind đúng kiểu với truy vấn gây ép kiểu; đo qua kế hoạch thực thi và dữ liệu đủ lớn.
7. **Khả năng tương thích**: chạy trên đúng phiên bản DBMS và JDBC driver đang triển khai, vì không thể suy ra toàn bộ hành vi từ đặc tả Java.

Nên kiểm tra cả **giá trị lưu và giá trị đọc lại**. Một câu lệnh `INSERT` thành công không bảo đảm giá trị được biểu diễn chính xác như ý định, đặc biệt khi DBMS cho phép làm tròn hoặc chuẩn hóa kiểu dữ liệu.

## 14. Những nhận định dễ nhầm

| Nhận định | Giải thích đúng |
|---|---|
| “Có dấu `?` thì JDBC tự chọn kiểu đúng với cột.” | Placeholder bảo vệ vị trí giá trị; kiểu bind và khả năng suy luận vẫn quan trọng. |
| “`setString("42")` giống `setLong(42)`.” | Một bên là chuỗi, một bên là số; implicit cast tùy driver/DBMS. |
| “`setObject()` luôn an toàn và portable cho mọi kiểu Java.” | Một số kiểu cần khai báo `Types`/`SQLType` hoặc cách ánh xạ riêng của driver. |
| “`null` không cần thông tin kiểu.” | Khi bind SQL `NULL`, nhiều trường hợp nên dùng `setNull(index, Types.X)`. |
| “`double` lưu chính xác mọi khoản tiền.” | Số dấu phẩy động nhị phân không biểu diễn chính xác mọi số thập phân. |
| “`LocalDateTime` đồng nghĩa với thời điểm UTC.” | `LocalDateTime` không chứa offset/múi giờ. |
| “DB tự ép kiểu thành công thì truy vấn luôn tối ưu.” | Biểu thức có cast có thể thay đổi kế hoạch thực thi và khả năng dùng index. |
| “Lỗi chuyển kiểu luôn đến từ JDBC driver.” | Có thể xảy ra tại Java trước khi bind hoặc do DBMS trong lúc thực thi. |

## 15. Tình huống tổng hợp

Một ứng dụng nhận dữ liệu đầu vào:

```text
customerId = "00042"
amount     = "199.95"
dueDate    = "2026-11-30"
```

Giả sử schema khai báo `customer_id BIGINT`, `amount DECIMAL(12,2)`, `due_on DATE`. Cách xử lý có thể là:

```java
long customerId = Long.parseLong("00042");
BigDecimal amount = new BigDecimal("199.95");
LocalDate dueOn = LocalDate.parse("2026-11-30");

statement.setLong(1, customerId);
statement.setBigDecimal(2, amount);
statement.setObject(3, dueOn);
```

Ở đây `Long.parseLong("00042")` tạo số `42`, phù hợp **nếu `customer_id` thực sự là số nguyên trong mô hình dữ liệu**. Nếu `"00042"` là mã khách hàng cần giữ nguyên ký tự số `0` đầu, schema nên dùng kiểu ký tự phù hợp và ứng dụng không nên chuyển sang `long`.

**Ghi nhớ:** Trong truy vấn tham số JDBC, cần xác định rõ kiểu ở **ba lớp Java → driver → cơ sở dữ liệu**. Ưu tiên setter thể hiện đúng kiểu SQL và ý nghĩa nghiệp vụ, dùng `BigDecimal` cho giá trị thập phân chính xác, `java.time` cho ngày giờ, và `setNull` có kiểu khi truyền `NULL`. Chỉ dựa vào ép kiểu ngầm khi đã hiểu và kiểm thử quy tắc của driver/DBMS đang dùng; điều này giúp tránh lỗi dữ liệu, sai số và kế hoạch truy vấn ngoài dự kiến.
