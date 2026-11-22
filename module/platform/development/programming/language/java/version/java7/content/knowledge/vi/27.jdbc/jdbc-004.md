# JDBC: getObject theo Class và chuyển đổi kiểu mà JDBC driver hỗ trợ

## 1. Mục tiêu: lấy dữ liệu SQL thành đúng kiểu Java mong muốn

Khi đọc một dòng từ **ResultSet**, ứng dụng cần chuyển giá trị của cột SQL thành giá trị Java có kiểu rõ ràng. JDBC cung cấp hai kiểu gọi thường gặp:

~~~java
Object raw = resultSet.getObject("amount");                // Kiểu Java do driver chọn.
BigDecimal amount = resultSet.getObject("amount", BigDecimal.class);
LocalDate date = resultSet.getObject("event_date", LocalDate.class);
~~~

Đây là **đoạn minh họa** bên trong khối mã đã có **ResultSet resultSet** đang trỏ tới một dòng hợp lệ, không phải một chương trình độc lập.

- **getObject(column)** không có đối số Class trả về **Object** theo ánh xạ mặc định của driver/JDBC; muốn dùng một kiểu khác có thể phải kiểm tra kiểu và chuyển đổi.
- **getObject(column, Class<T>)** yêu cầu driver trả giá trị dưới dạng **T** và cố chuyển SQL value sang kiểu Java được yêu cầu **nếu phép chuyển đổi được hỗ trợ**.
- Tham số **Class<T>** giúp kiểu trả về rõ ràng ở thời điểm biên dịch; nó **không bảo đảm** mọi cặp SQL type → Java class đều chạy được trên mọi driver.
- **getObject** chỉ đọc và chuyển dữ liệu. Nó **không sửa dữ liệu**, **không thay đổi SQL type lưu trong bảng**, và không giống việc ép kiểu SQL bằng **CAST/CONVERT** ở máy chủ.

Ví dụ: cột **DECIMAL(12,2)** nên được đọc bằng **BigDecimal.class** để giữ số thập phân chính xác; **DATE** phù hợp **LocalDate.class**; một cột **UUID** có thể được đọc bằng **UUID.class** với driver hỗ trợ kiểu UUID (chẳng hạn H2). Không giả định rằng driver nào cũng tự chuyển chuỗi JSON, UUID hoặc timestamp tùy ý thành mọi Java class.

**Tư duy đúng:** Chọn kiểu Java theo **ngữ nghĩa dữ liệu**, xác nhận **kiểu SQL của cột**, rồi kiểm tra **khả năng chuyển đổi của phiên bản JDBC driver đang dùng**.

## 2. Các overload của JDBC và cách dùng

**ResultSet** định nghĩa hai overload có kiểu:

~~~java
<T> T getObject(int columnIndex, Class<T> type) throws SQLException;
<T> T getObject(String columnLabel, Class<T> type) throws SQLException;
~~~

- **columnIndex** đánh số bắt đầu từ **1** theo vị trí cột trong kết quả truy vấn, không phải số thứ tự cột trong bảng gốc.
- **columnLabel** là tên nhãn của cột trong ResultSet. Với **SELECT price AS amount**, nhãn là **amount**; dùng nhãn riêng, không trùng lặp để tránh đọc nhầm cột khi JOIN.
- **type** là một đối tượng **Class<T>** không được null, ví dụ **Integer.class**, **String.class**, **BigDecimal.class**, **LocalDate.class**, **OffsetDateTime.class**.
- Nếu ô SQL chứa **NULL**, getObject trả về **null**, kể cả với overload có Class; do đó dùng wrapper như **Integer**, **Long**, **Boolean** thay vì unboxing ngay sang primitive.
- Phải gọi **resultSet.next()** thành công trước khi đọc; đọc sai nhãn/chỉ số, ResultSet đã đóng, hoặc conversion không hỗ trợ đều có thể gây **SQLException**.
- Nếu bản thân overload không được driver hỗ trợ, driver ném **SQLFeatureNotSupportedException** (một nhánh của SQLException). Một cặp chuyển đổi SQL → Java không hỗ trợ **cũng có thể ném SQLException thông thường**; không được chỉ bắt SQLFeatureNotSupportedException rồi kết luận mọi phép chuyển đổi còn lại đều hỗ trợ.

**CallableStatement** có overload tương tự cho **OUT parameter** của stored procedure:

~~~java
<T> T getObject(int parameterIndex, Class<T> type) throws SQLException;
<T> T getObject(String parameterName, Class<T> type) throws SQLException;
~~~

Đó là API dùng sau khi đã đăng ký OUT parameter và thực thi lời gọi procedure. Khả năng hỗ trợ kiểu dữ liệu, tên parameter và stored procedure khác nhau theo database/driver. Bài này tập trung vào **ResultSet** để phân tích chuyển đổi kiểu khi đọc hàng truy vấn.

### Generics mang lại điều gì?

~~~java
Integer count = resultSet.getObject("quantity", Integer.class);
~~~

Biến **count** có kiểu **Integer** ngay khi biên dịch. Không cần ép thủ công **(Integer) resultSet.getObject("quantity")**. Tuy nhiên, trình biên dịch chỉ kiểm tra quan hệ generic Java; **driver quyết định tại runtime** nó có chuyển được kiểu SQL hiện tại thành Integer hay không. Một conversion có thể thất bại do kiểu SQL không tương thích, dữ liệu vượt miền số hoặc hỗ trợ driver khác nhau.

Việc truyền **Object.class** hoặc **String.class** cho mọi cột không tự động tạo ra một định dạng chuẩn chung. Hãy chọn kiểu có ý nghĩa, dùng trình chuyển đổi ứng dụng tường minh khi cần, và tránh dựa vào chuyển đổi ngầm khó kiểm soát.

## 3. Ánh xạ SQL → Java thường dùng trong JDBC hiện đại

Bảng dưới đây thể hiện **lựa chọn kiểu hợp lý**, chứ không phải cam kết mọi driver đều hỗ trợ mọi phép chuyển đổi. Các ánh xạ cơ bản nằm trong JDBC; **java.time** được đưa vào JDBC 4.2 và được nhiều driver hiện hành hỗ trợ.

| Kiểu cột SQL | Kiểu Java thường chọn với getObject(..., Class) | Điểm cần chú ý |
| --- | --- | --- |
| INTEGER | **Integer.class** | SQL NULL → null; kiểm tra phạm vi số |
| BIGINT | **Long.class** | Tránh đọc thành Integer nếu có nguy cơ tràn |
| BOOLEAN | **Boolean.class** | Kiểu boolean SQL của từng DB có thể khác nhau |
| DECIMAL / NUMERIC | **BigDecimal.class** | Giữ độ chính xác, scale; tránh Double cho tiền |
| CHAR / VARCHAR | **String.class** | Conversion từ chuỗi thành số/ngày phụ thuộc driver và định dạng |
| DATE | **LocalDate.class** | Ngày lịch, không chứa giờ hoặc múi giờ |
| TIME (không timezone) | **LocalTime.class** | Giờ địa phương, không hàm ý thời điểm tuyệt đối |
| TIMESTAMP (không timezone) | **LocalDateTime.class** | Ngày-giờ không gắn offset hay zone |
| TIME WITH TIME ZONE | **OffsetTime.class** | Chỉ khi database/driver hỗ trợ SQL type và mapping này |
| TIMESTAMP WITH TIME ZONE | **OffsetDateTime.class** | Chính sách lưu offset/timezone của DB cần được hiểu rõ |
| BINARY/VARBINARY | **byte[].class** nếu driver hỗ trợ | Dữ liệu lớn cân nhắc stream và quản lý bộ nhớ |
| UUID của database | **UUID.class** nếu driver hỗ trợ | **Không phải** ánh xạ phổ quát cho mọi JDBC driver |
| JSON/JSONB, ARRAY, GEOMETRY, kiểu riêng | **Theo tài liệu driver** | Có thể trả String, byte[], java.sql.Array hoặc lớp của vendor; không đoán Class |

Đối với **DATE / TIME / TIMESTAMP**, kiểu **java.time** phản ánh đúng ý nghĩa hơn so với việc ép mọi giá trị thời gian thành **java.util.Date**. Chẳng hạn, không yêu cầu **Instant.class** cho mọi cột TIMESTAMP: **TIMESTAMP WITHOUT TIME ZONE** không mang thông tin zone/offset để xác định duy nhất một instant. Nếu nghiệp vụ cần instant, hãy quy định múi giờ/offset hoặc sử dụng kiểu dữ liệu thời gian có timezone phù hợp, rồi kiểm chứng cách lưu của DB.

**Phân biệt mapping và conversion:**

- **Mapping tự nhiên**: DATE → LocalDate; DECIMAL → BigDecimal; VARCHAR → String; driver hiểu trực tiếp dữ liệu cột.
- **Chuyển đổi thêm**: VARCHAR → Integer, NUMERIC → Boolean, VARCHAR → UUID hoặc TIMESTAMP → OffsetDateTime. Tùy giá trị, database và driver, có phép được hỗ trợ, có phép bị từ chối hoặc thay đổi ngữ nghĩa.
- **Vendor-specific**: Các kiểu UUID, JSONB, enum tùy hệ quản trị có thể cần loại Java riêng hoặc parse thủ công. **getObject("status", MyEnum.class)** không mặc nhiên biến một VARCHAR thành enum ứng dụng.
- **Dữ liệu null**: NULL vẫn là null, không biến thành 0, false, chuỗi rỗng hay một LocalDate mặc định.

Đặc tả JDBC mô tả các phép chuyển đổi tối thiểu bắt buộc và cho phép driver hỗ trợ thêm phép chuyển đổi riêng. Một cặp type chạy tốt ở H2 chưa chắc hoạt động giống hệt trên PostgreSQL, MySQL hoặc SQL Server. Cần thử với driver và phiên bản database thực tế.

## 4. Ví dụ Java 17+ có thể biên dịch và chạy bằng H2

Ví dụ dùng **JDBC chuẩn trong java.sql**, kết nối tới cơ sở dữ liệu H2 trong bộ nhớ. H2 là driver phục vụ thực hành; **UUID.class** là một trường hợp được H2 hỗ trợ, không phải cam kết portable. Các giá trị được cố định để stdout có thể đối chiếu.

Lưu tệp **TypedGetObjectDemo.java**:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Types;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.UUID;

public class TypedGetObjectDemo {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:h2:mem:typed_object_demo;DB_CLOSE_DELAY=-1";

        try (Connection connection = DriverManager.getConnection(url)) {
            try (Statement ddl = connection.createStatement()) {
                ddl.executeUpdate(
                    "CREATE TABLE event (" +
                    "id INTEGER PRIMARY KEY, " +
                    "event_date DATE NOT NULL, " +
                    "starts_at TIMESTAMP NOT NULL, " +
                    "price DECIMAL(12, 2) NOT NULL, " +
                    "external_id UUID NOT NULL, " +
                    "note VARCHAR(100))");
            }

            String insertSql = "INSERT INTO event " +
                    "(id, event_date, starts_at, price, external_id, note) " +
                    "VALUES (?, ?, ?, ?, ?, ?)";

            try (PreparedStatement insert = connection.prepareStatement(insertSql)) {
                insert.setInt(1, 7);
                insert.setObject(2, LocalDate.of(2026, 11, 4));
                insert.setObject(3, LocalDateTime.of(2026, 11, 4, 9, 30));
                insert.setBigDecimal(4, new BigDecimal("125.50"));
                insert.setObject(
                    5, UUID.fromString("123e4567-e89b-12d3-a456-426614174000"));
                insert.setNull(6, Types.VARCHAR);
                insert.executeUpdate();
            }

            String querySql =
                    "SELECT id, event_date AS day_date, starts_at, " +
                    "price, external_id, note FROM event WHERE id = ?";

            try (PreparedStatement query = connection.prepareStatement(querySql)) {
                query.setInt(1, 7);

                try (ResultSet rs = query.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Không tìm thấy event id=7");
                    }

                    Integer id = rs.getObject(1, Integer.class);
                    LocalDate day = rs.getObject("day_date", LocalDate.class);
                    LocalDateTime start = rs.getObject(
                            "starts_at", LocalDateTime.class);
                    BigDecimal price = rs.getObject("price", BigDecimal.class);
                    UUID externalId = rs.getObject("external_id", UUID.class);
                    String note = rs.getObject("note", String.class);

                    System.out.println("id=" + id);
                    System.out.println("day=" + day);
                    System.out.println("start=" + start);
                    System.out.println("price=" + price.toPlainString());
                    System.out.println("uuid=" + externalId);
                    System.out.println("noteIsNull=" + (note == null));
                }
            }
        }
    }
}
~~~

**Cách chạy:** Tải JAR của một phiên bản **H2 Database** còn được duy trì từ Maven Central, đặt cạnh tệp Java và đặt tên tệp JAR là **h2.jar**. Các lệnh sau dùng **JDK 17+**:

~~~bash
javac TypedGetObjectDemo.java
java -cp ".;h2.jar" TypedGetObjectDemo
~~~

Dấu **;** trong classpath áp dụng cho Windows. Trên Linux/macOS thay dòng chạy bằng **java -cp ".:h2.jar" TypedGetObjectDemo**. Việc biên dịch chỉ cần JDK vì mã không import lớp riêng của H2; khi chạy phải có JDBC driver JAR trên classpath để **DriverManager** tìm driver qua service loading.

**Kết quả kỳ vọng với H2 hỗ trợ những mapping trên:**

~~~text
id=7
day=2026-11-04
start=2026-11-04T09:30
price=125.50
uuid=123e4567-e89b-12d3-a456-426614174000
noteIsNull=true
~~~

**Vì sao ví dụ minh họa đúng ý bài học?**

1. **Integer.class** đọc cột INTEGER qua chỉ số 1-based (**1**).
2. **LocalDate.class** đọc DATE bằng nhãn **day_date** đã đổi bằng SQL **AS**.
3. **LocalDateTime.class** nhận TIMESTAMP không timezone, không tự gán timezone.
4. **BigDecimal.class** giữ **125.50** và scale; **toPlainString()** giúp định dạng output dễ đọc.
5. **UUID.class** thành công bởi **H2 hỗ trợ** SQL UUID ↔ java.util.UUID. Với DB khác phải xác minh loại cột và driver.
6. **String.class** trên một cột SQL **NULL** trả **null**, nên biểu thức **note == null** in **true**.
7. **PreparedStatement** và **ResultSet** được đóng bằng try-with-resources. Đây là phần quản lý tài nguyên độc lập với việc chuyển đổi kiểu.

Đây là ví dụ **thực thi H2 cụ thể**, không phải một bài kiểm định khả năng conversion của mọi driver. Trong dự án thật, dùng URL/driver thực tế, tạo dữ liệu bằng migration hoặc fixture phù hợp và kiểm tra mapping trong integration test.

## 5. Đọc NULL đúng cách: tránh unboxing vô ý

Xét cột **discount_percent INTEGER NULL**.

~~~java
// Đoạn này giả định ResultSet rs đang đứng ở một dòng.
Integer discount = rs.getObject("discount_percent", Integer.class);
if (discount == null) {
    System.out.println("Không có chiết khấu");
} else {
    System.out.println("Chiết khấu: " + discount);
}
~~~

Nếu viết **int discount = rs.getObject("discount_percent", Integer.class);** rồi ô SQL là NULL, Java sẽ cố unbox **null** và ném **NullPointerException**. **getObject(..., Integer.class)** không tự thay NULL bằng 0.

Ngược lại, các getter primitive như **rs.getInt("discount_percent")** trả **0** khi cột SQL là NULL, nên phải gọi **rs.wasNull()** ngay sau khi đọc nếu cần phân biệt NULL với số 0. Với overload có kiểu trả về wrapper, kiểm tra **== null** thường trực quan hơn:

~~~java
int raw = rs.getInt("discount_percent");
boolean isSqlNull = rs.wasNull();  // Hỏi trạng thái của lần đọc cột ngay trước.
Integer nullable = isSqlNull ? null : raw;
~~~

Không gán **Optional.class** làm Class yêu cầu cho getObject với kỳ vọng driver tự tạo Optional. Nếu muốn API ứng dụng trả về Optional, hãy chuyển đổi **sau khi** đọc giá trị: **Optional.ofNullable(rs.getObject("discount_percent", Integer.class))**.

## 6. Chuyển đổi kiểu có điều kiện: driver có quyền từ chối

**getObject(..., Class<T>)** là một yêu cầu chuyển kiểu gửi tới JDBC driver. Quá trình phụ thuộc ít nhất bốn yếu tố:

1. **SQL type thực tế** của cột: VARCHAR, DECIMAL, TIMESTAMP WITH TIME ZONE, UUID, JSONB...
2. **Java Class được yêu cầu**: String, Integer, BigDecimal, LocalDate, OffsetDateTime, UUID...
3. **Giá trị cụ thể**: chuỗi "12" có thể parse được thành số, chuỗi "abc" không; DECIMAL lớn có thể vượt miền Integer.
4. **Driver và database**: phiên bản driver, các mapping chuẩn mà nó thực hiện, phần mở rộng riêng và kiểu dữ liệu server hỗ trợ.

Một số ví dụ **không nên mặc định là portable**:

~~~java
// Các dòng sau chỉ minh họa yêu cầu chuyển đổi; có thể ném SQLException.
// rs.getObject("price", Double.class);     // Có thể mất độ chính xác số tiền.
// rs.getObject("text_id", UUID.class);      // VARCHAR -> UUID tùy driver.
// rs.getObject("created_at", java.time.Instant.class); // Không mặc định hỗ trợ.
// rs.getObject("json_payload", MyRecord.class);       // Không tự parse JSON.
~~~

**SQL NULL** là trường hợp riêng: khi conversion được hỗ trợ, ô NULL trả về **null**. Nếu driver không hỗ trợ chính phương thức hoặc cặp type yêu cầu, **ngoại lệ xảy ra ngay cả khi mã biên dịch thành công**.

**Nguyên tắc thiết kế:** Tạo DTO/domain mapping dựa trên SQL type có chủ đích; không thử hàng loạt Java Class như một thuật toán đoán định. Khi cần chuyển kiểu phức tạp (JSON, UUID lưu VARCHAR, enum, thời điểm UTC), hãy chọn một đường chuyển đổi có kiểm tra và test theo driver.

### Vì sao không thể chỉ nhìn metadata là biết mọi conversion?

~~~java
var meta = rs.getMetaData();
int index = rs.findColumn("price");

System.out.println(meta.getColumnType(index));       // Hằng số java.sql.Types.
System.out.println(meta.getColumnTypeName(index));   // Tên SQL của DB.
System.out.println(meta.getColumnClassName(index));  // Kiểu Java mặc định.
~~~

Đây là đoạn minh họa bên trong phạm vi **ResultSet rs** còn mở. **getColumnClassName** cho biết Java class dự kiến của **getObject(column)** không có Class theo ánh xạ mặc định. Nó **không** liệt kê toàn bộ các Class có thể dùng trong **getObject(column, Class<T>)**.

**DatabaseMetaData.supportsConvert(...)** dùng để mô tả khả năng chuyển đổi giữa các **SQL type** được driver báo cáo; không phải một phép kiểm tra đủ để khẳng định **DECIMAL → LocalDate.class** hoặc **JSONB → CustomPojo.class** được ResultSet hỗ trợ. Với type conversion quan trọng, xem tài liệu JDBC driver và chạy integration test trên DB thật.

## 7. Xử lý ngoại lệ và phương án chuyển đổi phù hợp

Một cách xử lý **khi conversion không được hỗ trợ** là không giả định lỗi bằng 0 hoặc thay bằng giá trị mặc định. Log đủ ngữ cảnh cột và kiểu mong muốn, rồi chọn phương án chuyển đổi đã được định nghĩa trong hợp đồng ứng dụng.

~~~java
// Đoạn minh họa trong một phương thức nhận ResultSet rs.
try {
    LocalDate date = rs.getObject("event_date", LocalDate.class);
    // Dùng date; date có thể null nếu SQL là NULL.
} catch (java.sql.SQLFeatureNotSupportedException unsupportedMethod) {
    // Driver không hỗ trợ API/capability được gọi.
    throw new SQLException(
            "Driver không hỗ trợ đọc event_date thành LocalDate",
            unsupportedMethod);
} catch (SQLException conversionOrReadError) {
    // Cả conversion không hỗ trợ lẫn lỗi SQL khác có thể đến nhánh này.
    // Xem SQLState, message, cause và tài liệu driver trước khi quyết định.
    throw conversionOrReadError;
}
~~~

Một số driver cũ hoặc môi trường đặc thù không hỗ trợ **LocalDate.class** nhưng vẫn cung cấp **ResultSet.getDate()**. Trong trường hợp được xác minh như vậy, có thể dùng đường tương thích tường minh **java.sql.Date sqlDate = rs.getDate("event_date"); LocalDate date = sqlDate == null ? null : sqlDate.toLocalDate();**. Đây là **phương án tương thích khi cần**, không phải lựa chọn ưu tiên cho JDBC 4.2 được hỗ trợ tốt. Đừng âm thầm thử fallback trên mọi SQLException: lỗi có thể do connection, quyền truy cập hoặc dữ liệu sai; fallback khi đó sẽ che lỗi thực tế.

**Nên theo dõi và kiểm thử:**

- **SQLState** và message để biết lỗi không hỗ trợ type, lỗi truy vấn, dữ liệu không hợp lệ hay lỗi kết nối; cách mã hóa cụ thể phụ thuộc driver.
- **getCause()** khi chuyển đổi lỗi có nguyên nhân sâu hơn.
- **Integration test** với driver/DB thật: **giá trị thường**, **SQL NULL**, **biên số**, **độ chính xác decimal**, **date/time**, **offset/timezone**, dữ liệu không hợp lệ, và kiểu vendor.
- **Thay đổi phiên bản JDBC driver**: kiểm tra release notes và chạy lại test conversion trước khi coi một kiểu mới là được hỗ trợ.

Không nên dùng **catch (Exception)** để chuyển mọi lỗi thành chuỗi rỗng hoặc null. Khi conversion không được hỗ trợ, ứng dụng cần quyết định rõ: đổi kiểu SQL, dùng getter chuyên biệt đang được hỗ trợ, chuyển đổi trong Java có kiểm soát, hoặc bỏ tính năng phụ thuộc mapping đó.

## 8. Dùng đúng kiểu thời gian, số và dữ liệu riêng

### LocalDate, LocalDateTime và OffsetDateTime

- **DATE → LocalDate**: giá trị lịch, không chứa thời gian.
- **TIMESTAMP WITHOUT TIME ZONE → LocalDateTime**: có ngày-giờ nhưng **không tự xác định instant trên trục UTC**. Đừng gắn múi giờ hệ thống rồi coi đó là hành vi JDBC.
- **TIMESTAMP WITH TIME ZONE → OffsetDateTime**: là mapping có trong JDBC 4.2, nhưng một số DB chuẩn hóa offset hoặc không giữ nguyên tên timezone. Phải xác minh ý nghĩa chính xác với DB/driver cụ thể.
- **Instant** cần thời điểm tuyệt đối; nếu đang có **OffsetDateTime**, ứng dụng có thể gọi **toInstant()** tường minh sau khi đã xác nhận cách DB lưu timestamp.

Ví dụ mapping tường minh trong mã nghiệp vụ:

~~~java
OffsetDateTime stored = rs.getObject(
        "created_with_offset", OffsetDateTime.class);
java.time.Instant instant =
        stored == null ? null : stored.toInstant();
~~~

Đoạn trên giả định cột có SQL type và JDBC driver tương thích; không phải chương trình độc lập.

### Decimal và chuyển đổi số

**BigDecimal** thích hợp cho tiền/số cần độ chính xác; **Double/Float** dùng số dấu phẩy động nhị phân nên có thể mất phần thập phân. Khi cần số nguyên, chọn **Integer** hoặc **Long** đúng miền giá trị. Đừng yêu cầu **Integer.class** trên DECIMAL lớn với kỳ vọng driver tự làm tròn theo quy tắc nghiệp vụ; nên kiểm tra range, scale và chuyển đổi bằng Java rõ ràng nếu yêu cầu.

### UUID, JSON và enum

- Nếu DB có kiểu **UUID** và driver trả **UUID**, có thể dùng **getObject("id", UUID.class)**. Với UUID lưu **VARCHAR**, có thể đọc String rồi gọi **UUID.fromString(string)** sau khi kiểm tra dữ liệu; phép chuyển từ VARCHAR sang UUID trực tiếp là tùy driver.
- Với **JSON/JSONB**, driver có thể trả String, byte[], đối tượng vendor hoặc dạng khác. Chọn API được driver công bố và thư viện JSON phù hợp; không kỳ vọng **getObject("payload", MyDto.class)** tự deserialize tùy ý.
- Với **enum** lưu VARCHAR, đọc **String.class**, sau đó ánh xạ/validate qua danh sách giá trị được hỗ trợ. Không ép **getObject("status", OrderStatus.class)** nếu chưa có mapper được kiểm chứng.

Những chuyển đổi này thuộc **hợp đồng dữ liệu ứng dụng**. Việc driver hỗ trợ thêm convenience conversion không thay thế kiểm tra tính đúng đắn của domain.

## 9. Những lỗi thường gặp

| Tình huống | Vấn đề | Cách xử lý |
| --- | --- | --- |
| **(Integer) rs.getObject("n")** | Phụ thuộc Java class mặc định mà driver trả; có thể ClassCastException | Dùng **getObject("n", Integer.class)** với SQL type phù hợp |
| **getObject("n", Integer.class)** trên cột VARCHAR bất kỳ | Có thể unsupported hoặc dữ liệu không parse được | Chọn SQL numeric hoặc chuyển đổi String tường minh |
| **int n = rs.getObject("n", Integer.class)** | SQL NULL gây unboxing NullPointerException | Dùng Integer và kiểm tra null |
| **getObject("paid", Double.class)** | Tiền có thể mất độ chính xác | Dùng BigDecimal và scale phù hợp |
| **getObject("created_at", Instant.class)** vô điều kiện | TIMESTAMP có thể không chứa offset; driver có thể không hỗ trợ | Thiết kế SQL type/múi giờ và mapping rõ ràng |
| **getObject("uuid_text", UUID.class)** trên mọi DB | VARCHAR → UUID không portable | Dùng native UUID có driver support hoặc parse String |
| **getObject("json", Dto.class)** | JDBC driver không phải JSON mapper chung | Dùng mapping vendor + JSON serializer/deserializer |
| Truyền **null** làm Class | Không có kiểu đích hợp lệ | Chọn Class cụ thể, xử lý NULL bằng giá trị trả về |
| Gọi getObject khi chưa next hoặc ResultSet đã close | Cursor/ResultSet ở trạng thái sai | Kiểm tra next(), giữ ResultSet sống trong try-with-resources |
| Nhầm tên bảng với columnLabel/AS | Không tìm thấy cột hoặc đọc nhầm JOIN | Dùng nhãn SELECT rõ ràng, duy nhất |
| Bắt mọi SQLException rồi trả null | Che mất lỗi kết nối, lỗi query và conversion | Phân loại lỗi, log SQLState, không swallow |
| Coi metadata class name là danh sách conversion | Metadata chỉ mô tả mapping mặc định | Đọc docs driver và kiểm chứng bằng test |
| Chạy trên H2 rồi khẳng định mọi DB đều giống nhau | Driver/database khác nhau về kiểu riêng và chuyển đổi | Test trên DB và driver sẽ dùng ở production |

## 10. Checklist khi áp dụng trong dự án

1. **Thiết kế SQL schema trước:** cột dùng INTEGER/DECIMAL/DATE/TIMESTAMP/UUID theo ý nghĩa và tính portable cần thiết.
2. **Chọn Class có chủ đích:** Integer, Long, BigDecimal, LocalDate, LocalDateTime, OffsetDateTime, String; chỉ dùng UUID và kiểu vendor nếu đã kiểm chứng.
3. **Kiểm tra NULL:** dùng reference type và branch rõ ràng; không unbox trước khi xác nhận.
4. **Đọc bằng nhãn SELECT ổn định:** bí danh duy nhất cho cột JOIN; dùng chỉ số 1-based khi phù hợp.
5. **Quản lý JDBC resource:** try-with-resources cho ResultSet/Statement/Connection; không giữ tài nguyên sau khi đóng.
6. **Bảo vệ độ chính xác:** scale BigDecimal, phạm vi số, địa phương/múi giờ phải có chính sách rõ.
7. **Kiểm tra driver:** bản phát hành, tài liệu mapping, SQLState, cơ chế fallback hợp lệ.
8. **Integration test:** ít nhất một bản ghi bình thường, một NULL, biên/invalid value và các trường hợp thời gian/UUID nếu dùng.

### Câu hỏi tự kiểm tra

1. **getObject("price")** và **getObject("price", BigDecimal.class)** khác gì? → Cách đầu trả Object theo default mapping; cách sau yêu cầu BigDecimal nếu driver hỗ trợ.
2. **getObject("birthday", LocalDate.class)** khi cột DATE là SQL NULL trả gì? → null, không phải ngày mặc định.
3. **getObject("created", Instant.class)** có luôn phù hợp TIMESTAMP không timezone không? → Không. Cần chính sách timezone và driver mapping được xác minh.
4. **getColumnClassName()** có xác nhận LocalDate.class được hỗ trợ không? → Không; đó là mapping Java mặc định.
5. **H2 hỗ trợ getObject("uuid", UUID.class)** có bảo đảm SQL Server hoặc MySQL hỗ trợ cùng cách không? → Không; UUID là trường hợp cần kiểm tra driver/database.
6. **Unsupported conversion gây lỗi gì?** → SQLException; nếu overload/capability không được hỗ trợ có thể là SQLFeatureNotSupportedException.

**Điểm cần nhớ:** **getObject(column, Class<T>)** cung cấp kết quả có kiểu Java rõ ràng, nhưng chính **JDBC driver** thực hiện và giới hạn chuyển đổi. Hãy chọn Java class theo SQL type và ngữ nghĩa dữ liệu, kiểm tra SQL NULL, ưu tiên **java.time** / **BigDecimal** khi phù hợp, và xác nhận mọi mapping phụ thuộc driver bằng integration test.

**Tài liệu tra cứu hiện hành:**

- [Java SE 17 — ResultSet.getObject(int/String, Class<T>)](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html)
- [Java SE 26 — CallableStatement.getObject(int/String, Class<T>)](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/CallableStatement.html)
- [H2 — JDBC ResultSet implementation](https://h2database.github.io/javadoc/org/h2/jdbc/JdbcResultSet.html)
- [H2 — Data Types](https://h2database.com/html/datatypes.html)
