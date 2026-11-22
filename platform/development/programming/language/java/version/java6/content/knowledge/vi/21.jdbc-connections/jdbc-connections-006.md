# SQLClientInfoException và thuộc tính cấu hình không được chấp nhận trong JDBC (Java 17+)

## 1. Vấn đề thực tế: JDBC driver không chấp nhận client-info property

Khi mở một kết nối cơ sở dữ liệu bằng JDBC, ứng dụng có thể muốn gắn **metadata mô tả client** lên phiên làm việc: tên ứng dụng, người sử dụng đang thực hiện tác vụ, hostname… Một số JDBC drivers có thể chuyển metadata này vào session register, session parameter hoặc vị trí chẩn đoán của database server, giúp DBA quan sát và phân biệt nguồn truy vấn.

JDBC định nghĩa hai overload:

```java
connection.setClientInfo("ApplicationName", "billing-worker");

Properties values = new Properties();
values.setProperty("ApplicationName", "billing-worker");
connection.setClientInfo(values);
```

Đây là **snippet** trong phương thức đã có `java.sql.Connection connection` và import `java.util.Properties`. **Đây không phải cách cấu hình JDBC URL, username/password, timeout, transaction isolation hoặc SQL session security.** `setClientInfo` dành cho metadata/diagnostics; nó không được phép tùy tiện làm thay đổi ngữ nghĩa của connection ngoài việc lưu client information theo hợp đồng JDBC.

**Không phải mọi driver hỗ trợ mọi tên client-info.** Driver có thể từ chối tên không nhận diện, giá trị không hợp lệ hoặc giá trị vượt giới hạn. Khi đặt một hoặc nhiều client-info properties thất bại, JDBC có exception chuyên biệt:

- **`java.sql.SQLClientInfoException`** — subclass của `SQLException`.
- **`SQLClientInfoException.getFailedProperties()`** — trả map tên thuộc tính không đặt được và mã lý do `ClientInfoStatus`.
- **`DatabaseMetaData.getClientInfoProperties()`** — giúp kiểm tra các tên, giới hạn độ dài và mô tả do driver công bố.

Bài tập trung vào cách **hiểu, dự phòng, chẩn đoán, xử lý và kiểm thử** lỗi này trong Java 17+; không giả định một thuộc tính nào được mọi DBMS hỗ trợ.

> Lưu ý thuật ngữ: đề bài dùng “thuộc tính cấu hình không được chấp nhận”. Với JDBC, client-info là **thông tin mô tả kết nối phục vụ kế toán, chẩn đoán và debug**; nếu cần cấu hình hành vi connection, hãy dùng các API như `setAutoCommit`, `setReadOnly`, `setTransactionIsolation`, `setSchema` hoặc cấu hình driver hợp lệ thay vì nhét vào `setClientInfo`.

## 2. JDBC client information dùng để làm gì?

Các tên **chuẩn được JDBC nêu ra** là:

| Tên client-info | Ý nghĩa | Có bắt buộc driver hỗ trợ? |
| --- | --- | --- |
| `ApplicationName` | Tên ứng dụng hiện sử dụng connection. | **Không.** |
| `ClientUser` | Tên user mà ứng dụng đang thực hiện công việc thay mặt; có thể khác user dùng để đăng nhập DB. | **Không.** |
| `ClientHostname` | Hostname nơi ứng dụng đang chạy. | **Không.** |

Khi driver có một thuộc tính khớp với ý nghĩa chuẩn này, đặc tả khuyến khích dùng đúng tên chuẩn. Driver vẫn **không bị buộc** triển khai cả ba tên. Một số driver còn hỗ trợ những tên vendor-specific; phải kiểm tra tài liệu driver và metadata thực tế.

**Tránh nhầm:**
- `ClientUser` không tự đổi danh tính đăng nhập DB hay quyền SQL.
- `ClientHostname` là metadata, không phải biện pháp xác minh nguồn mạng.
- `ApplicationName` có thể được dùng để đặt tên connection hiển thị trong công cụ giám sát, nhưng không tự sửa cơ chế connection pool, log mức SQL hoặc timeouts.
- JDBC driver có thể **trì hoãn** việc đẩy giá trị client-info đến database server cho đến lúc statement được prepare hoặc execute, vì lý do hiệu năng.

### 2.1. Hai overload của Connection.setClientInfo

```java
void setClientInfo(String name, String value)
        throws SQLClientInfoException;

void setClientInfo(Properties properties)
        throws SQLClientInfoException;
```

Đây là **chữ ký API minh họa**, không phải chương trình Java độc lập.

**Overload một property:**
- Thử đặt thuộc tính có tên `name` bằng `value`.
- Nếu `value == null`, yêu cầu **xóa giá trị hiện tại của property đó**.
- Có thể gặp `SQLClientInfoException` nếu driver/server báo lỗi, bao gồm kết nối đã đóng.
- Tên không nhận diện: driver được yêu cầu tạo `SQLWarning`; cách biểu hiện lỗi/truncation cụ thể phải xem driver và JDBC contract.

**Overload `Properties`:**
- **Thay thế toàn bộ tập client-info properties hiện tại** bằng tập được truyền.
- Property trước đó đã đặt nhưng **không xuất hiện** trong `Properties` mới sẽ bị xóa.
- Truyền **`Properties` rỗng yêu cầu xóa tất cả** client-info properties hiện có.
- Nếu một hay nhiều property không được đặt, ném `SQLClientInfoException`.
- **Không có cam kết mọi property được đặt nguyên tử.** Có database có thể đã áp dụng một số property trước khi lỗi xuất hiện, nên **trạng thái client-info sau exception là không chắc chắn**.

Điểm này quan trọng: đừng coi `setClientInfo(Properties)` là hàm “chỉ merge một vài thay đổi”. Nó có thể làm mất metadata đang dùng ở connection nếu bạn đưa vào danh sách thiếu các trường cũ.

## 3. SQLClientInfoException là gì?

Khai báo lớp:

```java
public class SQLClientInfoException extends SQLException
```

Đây là chữ ký class trong JDK, không phải source tự định nghĩa.

Vì nó là subclass của `SQLException`, các phương thức thông thường của lỗi JDBC vẫn có:
- `getMessage()`: mô tả lỗi.
- `getSQLState()`: SQLState do driver cung cấp, có thể null.
- `getErrorCode()`: vendor-specific code, có thể bằng 0.
- `getCause()`: nguyên nhân nếu có.
- `getNextException()`: các `SQLException` bổ sung theo chain, nếu driver đặt.
- `getFailedProperties()`: **dữ liệu riêng** của `SQLClientInfoException`, cho biết property nào thất bại.

**Cốt lõi:** `getFailedProperties()` trả kiểu:

```java
Map<String, ClientInfoStatus>
```

- **Key:** tên client-info property không đặt được.
- **Value:** lý do thất bại theo enum `java.sql.ClientInfoStatus`.
- Map này **không chứa giá trị của property bị từ chối**. Đừng cố suy ra giá trị từ mã lỗi.
- Một exception khởi tạo bằng constructor rỗng có thể trả `null` cho failed-properties map; do đó code chẩn đoán cần kiểm tra null.

### 3.1. Bốn ClientInfoStatus vẫn áp dụng ở Java 17+

| Mã `ClientInfoStatus` | Ý nghĩa chính thức | Cách phản ứng |
| --- | --- | --- |
| `REASON_UNKNOWN_PROPERTY` | Tên property không được driver nhận diện. | Kiểm tra tên hỗ trợ qua `DatabaseMetaData` và tài liệu driver; bỏ hoặc đổi sang tên hợp lệ. |
| `REASON_VALUE_INVALID` | Giá trị được cung cấp không hợp lệ. | Kiểm tra định dạng/ký tự/ràng buộc của driver; không tự sửa đoán mò. |
| `REASON_VALUE_TRUNCATED` | Giá trị quá lớn theo giới hạn property. | Rà `MAX_LEN`; chọn giá trị ngắn hợp lệ rồi thử lại có kiểm soát. |
| `REASON_UNKNOWN` | Không đặt được vì nguyên nhân chưa rõ. | Kiểm tra `SQLState`, vendor code, exception chain, driver/server logs và tình trạng connection. |

**Đừng nhầm `ClientInfoStatus` với `SQLState`:**
- `ClientInfoStatus` có bốn lý do được enum hóa theo **từng property**.
- `SQLState` là trạng thái lỗi SQL/JDBC ở cấp exception và do driver/server cung cấp.
- Hai cơ chế bổ sung nhau, **không thể thay nhau**.

### 3.2. “REASON_VALUE_TRUNCATED” không có nghĩa giá trị đã được lưu

Với `setClientInfo(String,String)`, nếu giá trị dài quá mức, JDBC cho phép driver **cắt bớt và tạo warning** hoặc **ném SQLClientInfoException**. Nếu driver **ném exception**, giá trị yêu cầu đó **không được set** theo hợp đồng của overload này.

Vì thế:
- Trạng thái `REASON_VALUE_TRUNCATED` trong failed map là tín hiệu **giá trị quá dài**, không phải xác nhận đã lưu một phiên bản ngắn.
- Nếu driver chỉ tạo `SQLWarning` do truncate, lời gọi có thể không ném exception, nhưng giá trị thực có thể bị rút ngắn; cần chính sách kiểm tra warning và readback.
- Không tự động truncate những giá trị quan trọng chỉ để “cho qua”; cân nhắc ý nghĩa, tính nhất quán và metadata hệ thống giám sát.

## 4. Tại sao có thể thất bại từng phần?

Giả sử một ứng dụng cố đặt:

```java
Properties requested = new Properties();
requested.setProperty("ApplicationName", "batch-worker");
requested.setProperty("UnknownTag", "blue");
connection.setClientInfo(requested);
```

Đây là **snippet**, không phải ví dụ có kết quả cố định trên mọi driver. Driver A có thể nhận `ApplicationName` nhưng không biết `UnknownTag`; driver B có thể không hỗ trợ cả hai hoặc từ chối theo cách khác.

Các trường hợp:
1. **Không có error:** driver có thể chấp nhận request và lưu metadata theo chính sách riêng.
2. **Warning:** driver không nhận diện một tên hoặc cắt ngắn một giá trị theo behavior JDBC; cần kiểm tra warning chain và kết quả nếu được hỗ trợ.
3. **`SQLClientInfoException`:** một hoặc nhiều properties không đặt được; inspect failed map.
4. **Thất bại một phần khi bulk set:** một số properties đã được lưu trước exception, một số không. Không có bảo đảm **transactional atomicity**.
5. **Connection đã đóng hoặc server lỗi:** có thể nhận `SQLClientInfoException` dù tên/giá trị hợp lệ.

**Kết luận vận hành:** Sau một lần `setClientInfo(Properties)` ném exception, đừng giả định:
- Tất cả giá trị đã rollback.
- Tất cả giá trị đều thất bại.
- Các keys **không xuất hiện** trong `getFailedProperties()` chắc chắn đã được áp dụng và có thể đọc lại ngay.

Phải xem xét metadata/driver docs và nếu có thể, **đọc lại bằng `getClientInfo`**, hiểu rằng giá trị có thể được trì hoãn gửi đến server.

## 5. Kiểm tra thuộc tính được hỗ trợ qua DatabaseMetaData

Một JDBC driver chuẩn có thể công bố client-info properties bằng:

```java
DatabaseMetaData meta = connection.getMetaData();

try (ResultSet rs = meta.getClientInfoProperties()) {
    while (rs.next()) {
        String name = rs.getString("NAME");
        int maximum = rs.getInt("MAX_LEN");
        String defaultValue = rs.getString("DEFAULT_VALUE");
        String description = rs.getString("DESCRIPTION");
    }
}
```

Đây là **snippet** trong method có `Connection connection` và import `java.sql.DatabaseMetaData`, `java.sql.ResultSet`. Các biến được đọc nhưng không được dùng ở snippet vì mục đích minh họa cột metadata; trong production hãy sử dụng chúng để quyết định validation và policy, tránh ghi log giá trị nhạy cảm.

Kết quả `ResultSet` có các cột chuẩn:

| Cột | Kiểu JDBC trả về | Ý nghĩa |
| --- | --- | --- |
| `NAME` | `String` | Tên client-info property được driver hỗ trợ. |
| `MAX_LEN` | `int` | Độ dài giá trị lớn nhất theo metadata driver. |
| `DEFAULT_VALUE` | `String` | Giá trị mặc định nếu có. |
| `DESCRIPTION` | `String` | Diễn giải thuộc tính, thường kèm nơi nó được lưu. |

JDBC quy định result set được sắp theo `NAME`. Nếu không có property được hỗ trợ, driver có thể trả **ResultSet rỗng**. Nếu driver/server không truy xuất metadata được, `getClientInfoProperties()` có thể ném `SQLException`.

**Lưu ý với `rs.getInt("MAX_LEN")`:** dùng `rs.wasNull()` nếu cần phân biệt giá trị SQL NULL với `0`. Đừng tự suy rằng `0` hay null luôn đồng nghĩa “không giới hạn”; phải đọc driver docs. Độ dài theo Java `String.length()` là UTF-16 code units; nếu driver có quy tắc giới hạn theo bytes/Unicode khác, phải tuân theo contract của driver.

**Tên chuẩn là gợi ý, không phải danh sách bắt buộc:** `ApplicationName`, `ClientUser` và `ClientHostname` có thể thiếu trong metadata nếu driver không hỗ trợ. Không hardcode tên và kỳ vọng hoạt động ở PostgreSQL, MySQL, SQL Server, Oracle, H2… giống nhau.

## 6. Ví dụ Java 17+ độc lập: tạo và đọc SQLClientInfoException

Ví dụ đầu tiên **không cần database, không cần JDBC driver ngoài JDK**. Chúng ta mô phỏng hai property bị từ chối bằng constructor chính thức của `SQLClientInfoException`, rồi in các thông tin lỗi và mã trạng thái.

**Quan trọng:** đây là bài tập minh họa **cách đọc exception**, **không phải kết quả của một JDBC driver thật**. Mã `HY000` và vendor code `24` được chọn giả lập; không phải code bắt buộc của mọi DB.

Tạo file **`ClientInfoExceptionDemo.java`**:

```java
import java.sql.ClientInfoStatus;
import java.sql.SQLClientInfoException;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.Map;

public class ClientInfoExceptionDemo {

    public static void main(String[] args) {
        Map<String, ClientInfoStatus> failed = new LinkedHashMap<>();

        failed.put("UnknownTag",
                ClientInfoStatus.REASON_UNKNOWN_PROPERTY);
        failed.put("ApplicationName",
                ClientInfoStatus.REASON_VALUE_TRUNCATED);

        SQLClientInfoException ex = new SQLClientInfoException(
                "Client info rejected",
                "HY000",
                24,
                failed);

        System.out.println("type=" + ex.getClass().getSimpleName());
        System.out.println("sqlState=" + ex.getSQLState());
        System.out.println("vendorCode=" + ex.getErrorCode());
        System.out.println("isSQLException=" + (ex instanceof SQLException));

        ex.getFailedProperties().forEach((name, status) ->
                System.out.println(name + "=" + status));
    }
}
```

### 6.1. Biên dịch và chạy

Trong terminal dùng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ClientInfoExceptionDemo.java
java ClientInfoExceptionDemo
```

**Stdout chính xác** đã biên dịch/chạy kiểm chứng trên JDK:

```text
type=SQLClientInfoException
sqlState=HY000
vendorCode=24
isSQLException=true
UnknownTag=REASON_UNKNOWN_PROPERTY
ApplicationName=REASON_VALUE_TRUNCATED
```

**Giải thích:**
1. `LinkedHashMap` bảo toàn thứ tự chèn nên hai dòng properties xuất hiện ổn định.
2. `SQLClientInfoException` kế thừa `SQLException` nên `isSQLException=true`.
3. `getSQLState()` trả mã `HY000` do constructor **chúng ta truyền**, không phải JDK tự đoán.
4. `getErrorCode()` trả `24`, cũng do constructor truyền.
5. `getFailedProperties()` chứa **tên thuộc tính và enum status**. Không có actual property values; nên dùng map như nguồn chẩn đoán, không log dữ liệu nhạy cảm.

Vì tự tạo exception nên test này luôn chạy được chỉ với JDK. Nó không kiểm thử khả năng hỗ trợ `ApplicationName` của một DB cụ thể; phần sau là chương trình kết nối thật.

## 7. Ví dụ tích hợp với driver JDBC thực: metadata → set → catch → readback

Chương trình sau **biên dịch bằng Java 17+ mà không cần thư viện ngoài JDK**, vì chỉ import `java.sql`. Để thực sự kết nối, runtime **phải có JDBC driver tương thích** và một database hoạt động. Nó đọc JDBC URL từ argument và user/password từ môi trường (nếu cần), rồi:

1. Lấy `DatabaseMetaData.getClientInfoProperties()`.
2. In **tên** thuộc tính và maximum length do driver công bố.
3. **Chỉ thử `ApplicationName` nếu driver quảng bá tên này**.
4. Bắt `SQLClientInfoException` và in mã lý do của từng failed property.
5. Đọc `getClientInfo("ApplicationName")` để kiểm tra giá trị đang được driver báo cáo.

Không gắn nhãn “thành công” chỉ vì `setClientInfo` trả bình thường; nên quan sát warning/readback theo policy của driver.

### 7.1. File JdbcClientInfoInspector.java

```java
import java.sql.ClientInfoStatus;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLClientInfoException;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

public class JdbcClientInfoInspector {

    public static void main(String[] args) throws SQLException {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java JdbcClientInfoInspector <jdbc-url>");
            return;
        }

        Properties login = new Properties();

        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        if (user != null) {
            login.setProperty("user", user);
        }
        if (password != null) {
            login.setProperty("password", password);
        }

        try (Connection connection =
                     DriverManager.getConnection(args[0], login)) {

            Map<String, Integer> available = new LinkedHashMap<>();

            try (ResultSet rs = connection.getMetaData()
                    .getClientInfoProperties()) {

                while (rs.next()) {
                    String name = rs.getString("NAME");
                    int maxLen = rs.getInt("MAX_LEN");

                    available.put(name, maxLen);
                    System.out.println(
                            "supported=" + name + ",maxLen=" + maxLen);
                }
            }

            if (!available.containsKey("ApplicationName")) {
                System.out.println(
                        "ApplicationName not advertised; skipping");
                return;
            }

            String requested = "JdbcClientInfoInspector";

            try {
                connection.setClientInfo("ApplicationName", requested);
                System.out.println("setClientInfo returned normally");
            } catch (SQLClientInfoException e) {
                System.out.println(
                        "setClientInfo failed; state=" + e.getSQLState());

                Map<String, ClientInfoStatus> failures =
                        e.getFailedProperties();

                if (failures == null || failures.isEmpty()) {
                    System.out.println(
                            "No per-property failure details");
                } else {
                    failures.forEach((key, status) ->
                            System.out.println(
                                    "failedProperty=" + key
                                    + ",reason=" + status));
                }
            }

            String stored =
                    connection.getClientInfo("ApplicationName");

            System.out.println(
                    "readbackMatches=" + requested.equals(stored));
        }
    }
}
```

### 7.2. Biên dịch và chạy với driver của bạn

Biên dịch chỉ bằng JDK:

```bash
javac -encoding UTF-8 JdbcClientInfoInspector.java
```

Ở runtime, cần cài JDBC driver tương ứng trên classpath. Dùng một JDBC URL **không chứa mật khẩu**, cấp credentials từ nguồn được quản lý theo môi trường thử nghiệm. Ví dụ command cho Linux/macOS khi đã cấu hình `JDBC_URL`:

```bash
java -cp ".:driver.jar" JdbcClientInfoInspector "$JDBC_URL"
```

Với PowerShell, cú pháp classpath và biến môi trường là:

```powershell
java -cp '.;driver.jar' JdbcClientInfoInspector $env:JDBC_URL
```

`driver.jar` ở đây là **tên tập tin giả định cho JAR driver thực của dự án**; phải sử dụng đúng tên và đúng JDBC URL theo vendor. Nếu đang dùng Maven/Gradle, driver dependency có thể đã nằm trong runtime classpath, nên chạy qua application launcher của dự án.

**Không công bố stdout cố định cho chương trình tích hợp.** Kết quả metadata, danh sách supported properties, số `MAX_LEN`, việc `ApplicationName` có tồn tại hay không, cách driver xử lý warning và readback đều thay đổi theo JDBC driver, DBMS, phiên bản và cấu hình server.

**Lưu ý bảo mật:** ví dụ đọc `DB_USER`/`DB_PASSWORD` từ environment chỉ để đơn giản hóa chạy thử. Environment variables không phải kho secret tuyệt đối; trong production ưu tiên secret manager/credential provider và cấu hình datasource theo chính sách tổ chức. Tránh đặt password vào URL, process arguments, logs hoặc source code.

### 7.3. Tại sao program không tự động thử tên property không có trong metadata?

Nếu driver không công bố `ApplicationName`, tự ý thử đặt có thể tạo warning/exception hoặc behavior không như mong đợi. Ví dụ chọn **skip an toàn**. Nếu vendor docs có xác nhận capability mà metadata không đầy đủ, đó là trường hợp tích hợp cần test riêng, không được gộp thành “mọi driver hỗ trợ”.

**Tại sao `readbackMatches=false` không đủ kết luận?** Driver có thể có readback semantics riêng, ghi deferred, hoặc không trả ngay cùng dạng đã yêu cầu. Kết quả `getClientInfo("ApplicationName")` trả `null` còn có thể là property unsupported hoặc chưa có giá trị. Nên đối chiếu vendor docs và server-side diagnostics khi sản phẩm thực sự dựa vào thông tin này.

## 8. Cách bắt exception an toàn trong ứng dụng production

Mẫu được khuyến nghị cho một lần đặt property không thiết yếu:

```java
try {
    connection.setClientInfo("ApplicationName", "order-service");

} catch (SQLClientInfoException e) {
    Map<String, ClientInfoStatus> failed =
            e.getFailedProperties();

    if (failed == null || failed.isEmpty()) {
        logger.warn("JDBC client info not accepted; SQLState={}",
                e.getSQLState());
    } else {
        failed.forEach((name, reason) ->
                logger.warn(
                        "JDBC client info rejected; name={}, reason={}",
                        name, reason));
    }
}
```

Đây là **snippet**, không phải chương trình standalone: `logger` là logger của framework ứng dụng và `connection` đã được mở; cần import `java.sql.SQLClientInfoException`, `java.sql.ClientInfoStatus`, `java.util.Map`. Chỉ log **name/status**, không log value. Trong môi trường production có thể thêm vendor code và exception cause **sau khi rà nội dung an toàn**, vì exception message hoặc vendor chain đôi khi chứa thông tin kết nối.

Nếu ứng dụng cần **bảo đảm** metadata hiện diện (ví dụ monitoring bắt buộc), việc coi đây là warning và tiếp tục không phải lúc nào cũng hợp lệ: có thể fail setup hoặc chuyển sang cơ chế tagging/observability khác được hỗ trợ. Chính sách quyết định mức nghiêm trọng phụ thuộc nghiệp vụ, nhưng tuyệt đối không bỏ qua exception mà không có log/metric phù hợp.

### 8.1. Đặt catch theo thứ tự đúng

`SQLClientInfoException` **là một `SQLException`**. Nếu cùng khối try còn chứa các thao tác JDBC khác và cần xử lý chuyên biệt, đặt catch subclass trước:

```java
try {
    connection.setClientInfo("ApplicationName", "batch-worker");
    connection.getMetaData();
} catch (SQLClientInfoException e) {
    // Lỗi client info: kiểm tra getFailedProperties().
} catch (SQLException e) {
    // Lỗi JDBC khác: kết nối/metadata/driver...
}
```

Đây là snippet. Nếu đặt `catch (SQLException e)` trước, nhánh bắt `SQLClientInfoException` sau sẽ không thể tới và Java báo lỗi compile do catch không thể đạt.

### 8.2. Không bao giờ assume failed map không null

Một số constructors của `SQLClientInfoException` cho phép không truyền failed map; ví dụ `new SQLClientInfoException()`. Khi cần code diagnostic tổng quát, hãy xử lý:
- `failed == null`: không có map chi tiết.
- `failed.isEmpty()`: không có phần tử chi tiết.
- Map có entries: lần lượt đọc `Map.Entry<String,ClientInfoStatus>`.

**Đừng coi map null hoặc rỗng là bằng chứng mọi property đã được lưu.** Có exception, nên cần xem thêm SQLState, vendor code và driver behavior.

## 9. SQLWarning khi driver không ném exception

`Connection.setClientInfo` có những trường hợp API cho phép hoặc yêu cầu driver tạo **SQLWarning**:
- Tên property không được nhận diện.
- Giá trị vượt giới hạn nhưng driver lựa chọn **cắt ngắn** và cảnh báo thay vì ném `SQLClientInfoException`.

Mẫu đọc warning chain:

```java
SQLWarning warning = connection.getWarnings();

while (warning != null) {
    System.out.println("warningState=" + warning.getSQLState());
    warning = warning.getNextWarning();
}
```

Đây là snippet trong method có `connection`, import `java.sql.SQLWarning`, và phần output không cố định. `getWarnings()` có thể trả null. Trong hệ thống cần diagnosics, chỉ log metadata an toàn; thông điệp warning có thể chứa dữ liệu nhạy cảm và cần kiểm duyệt.

**Lưu ý:** warning chains trên connection có thể chứa cảnh báo từ những thao tác trước đó. Đừng quy mọi warning bạn đọc được cho lần `setClientInfo` mới nhất nếu không kiểm soát thời điểm phát sinh. Chỉ gọi `clearWarnings()` khi chính sách ứng dụng cho phép, không tự dọn mất thông tin cần được component khác xử lý.

## 10. Bulk set: không atomic và không giống merge

Một khác biệt thường bị bỏ sót:

```java
Properties requested = new Properties();
requested.setProperty("ApplicationName", "import-job");
requested.setProperty("ClientUser", "service-account");
connection.setClientInfo(requested);
```

**Không có bảo đảm transactional/atomic.** Nếu `ClientUser` không được hỗ trợ, có driver đã đặt `ApplicationName` trước khi ném exception. Theo contract, trạng thái toàn bộ client info có thể không xác định sau khi exception.

**Không phải partial patch.** Khi gọi `setClientInfo(Properties)`, tập properties truyền vào **thay thế tập hiện có**. Nếu connection trước đó có `ClientHostname` mà bạn không truyền, property đó có thể bị xóa. Điều này quan trọng khi nhiều library cùng chia sẻ một connection.

Muốn thay một property mà không đụng các property khác, dùng overload:

```java
connection.setClientInfo("ApplicationName", "import-job");
```

Đây chỉ là hướng chọn API; ngay cả overload một property vẫn có thể bị driver từ chối.

**Về transaction rollback:** không tự giả định `rollback()` sẽ trả client-info metadata về nguyên trạng. Client info là thông tin connection/session dành cho diagnostics; không phải dữ liệu bảng được bảo đảm transactional theo cách set hàng loạt. Phải theo contract của driver/server nếu ứng dụng cần rollback semantics.

## 11. Connection pooling: cẩn thận metadata bị “rò” giữa các request

Trong một dịch vụ đa tenant, nhiều request có thể **mượn cùng physical connection** từ connection pool theo thời gian. Nếu request A đặt `ApplicationName`/`ClientUser` rồi trả connection về pool mà không reset, request B có thể nhìn thấy metadata cũ hoặc server-side session tags không đúng, tùy behavior pool/driver.

Thiết kế cần:
1. Xác định client-info là **connection-scoped** hay có cơ chế reset khi pool recycle.
2. Với metadata chung ổn định như service name, gắn trong bước connection initialization do pool/datasource quản lý.
3. Với metadata riêng request/tenant, làm theo quy trình set/reset rõ ràng và **không cho dữ liệu nhạy cảm** vào client info.
4. Khi cần reset một property, overload `setClientInfo(name, null)` cho phép yêu cầu xóa giá trị, nhưng vẫn phải xử lý exception khi reset bị từ chối.
5. Không dùng `setClientInfo(new Properties())` một cách tùy tiện vì nó xóa **tất cả** client info hiện có, có thể làm mất metadata do pool/framework khác quản lý.
6. Kiểm tra tài liệu pool và driver: không giả định pool tự reset client-info nếu không có cam kết cụ thể.
7. Test với việc borrow-return-borrow để xác minh trạng thái không tồn dư.

**Client-info không phải user authentication/authorization.** Gắn `ClientUser="alice"` không khiến database tự chạy với quyền Alice. Không dùng thuộc tính này thay role-based access control, session authorization hay auditing thực sự.

## 12. Khi nào nên tiếp tục, khi nào phải dừng?

Tùy loại ứng dụng:

| Tình huống | Hướng xử lý |
| --- | --- |
| `ApplicationName` chỉ giúp DBA thấy service | Có thể tiếp tục query và cảnh báo/metric nếu property bị từ chối, miễn monitoring policy cho phép. |
| Client-info là yêu cầu audit bắt buộc | Fail connection initialization hoặc dùng cơ chế tagging được DB bảo đảm; không âm thầm tiếp tục. |
| Bulk set fail một phần | Xem `getFailedProperties`, metadata, rồi readback/kiểm tra server nếu cần; không giả định toàn bộ đã rollback. |
| Unknown name | Bỏ/đổi tên theo metadata/driver docs, không retry vô hạn cùng tên. |
| Value invalid | Validate đầu vào theo contract, tránh tự sửa làm mất ý nghĩa. |
| Value too long | Xác định `MAX_LEN`/vendor constraints; chọn giá trị ngắn có chủ đích rồi retry có giới hạn. |
| Driver/server I/O error hoặc closed connection | Đánh giá connection health, pool lifecycle; không coi là chỉ sai tên property. |
| Property không hiện trong metadata | Cẩn thận skip, fallback observability, hoặc test vendor-specific có kiểm soát. |

**Không retry mọi `SQLClientInfoException` vô điều kiện.** Với tên unknown hay giá trị invalid, retry y nguyên không giải quyết được; có thể tạo log noise và tải không cần thiết. Với lỗi connection/server tạm thời, logic retry phải theo chiến lược quản lý connection và idempotency của ứng dụng.

## 13. Những nhầm lẫn kỹ thuật thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “ApplicationName luôn được JDBC driver hỗ trợ.” | Đây là standard name có khuyến nghị, **không bắt buộc**. |
| “setClientInfo là cách thay JDBC login user.” | Chỉ là metadata, không xác thực/ủy quyền thay user. |
| “Bulk setter cộng thêm hai key.” | Bulk setter **thay thế toàn bộ tập**; keys không gửi bị clear. |
| “Thấy SQLClientInfoException nghĩa là mọi property đều thất bại.” | Có thể đã set một phần do DB không atomic. |
| “Failed map không có tên X thì X chắc chắn thành công.” | Không đủ cơ sở; trạng thái tổng thể sau bulk error có thể bất định. |
| “REASON_VALUE_TRUNCATED nghĩa là đã lưu giá trị ngắn.” | Với exception, đó là lý do giá trị quá lớn và không đặt được theo overload tương ứng. |
| “SQLState và ClientInfoStatus là một.” | SQLState thuộc exception; ClientInfoStatus thuộc từng failed property. |
| “getClientInfo(name)==null luôn nghĩa là key sai.” | Có thể unsupported, chưa set, hoặc không có default. |
| “Không cần check warning nếu không có exception.” | Driver có thể cảnh báo unknown name/truncation. |
| “getClientInfoProperties() là bảng property toàn JDBC URL.” | Nó mô tả **client-info properties**, không phải mọi driver configuration property. |
| “setClientInfo(Properties) dùng như transaction update.” | Không được bảo đảm atomic; rollback không chắc phục hồi client info. |
| “ClientInfo luôn được truyền ngay lên server.” | Driver có thể defer đến prepare/execute statement. |
| “ClientUser quyết định quyền database.” | Không, quyền SQL do authentication/authorization riêng. |
| “Reset pool tự xóa mọi client info.” | Phụ thuộc pool và driver; phải kiểm tra contract. |
| “getFailedProperties() không bao giờ null.” | Constructor không truyền map có thể tạo exception với map null. |
| “Khai báo catch SQLException trước rồi catch SQLClientInfoException.” | Subclass catch sau superclass catch là unreachable trong Java. |

## 14. Checklist kiểm thử thực tế

**Test 1 — Metadata discovery:** Trên mỗi loại driver/DBMS hỗ trợ, gọi `getClientInfoProperties()` và ghi nhận các names/limits. Không lấy kết quả của một driver áp cho tất cả DBMS.

**Test 2 — Unknown property:** Nếu môi trường thử nghiệm cho phép, thử một tên không tồn tại. Quan sát exception và/hoặc `SQLWarning`; không khẳng định vendor nhất định sẽ throw.

**Test 3 — Invalid/overlong value:** Với property có documented `MAX_LEN`, thử giá trị quá giới hạn. Test xem driver ném exception hay warning/truncate; không thực hiện với thông tin nhạy cảm.

**Test 4 — Bulk partial failure:** Đặt hai properties trong một `Properties` rồi tạo điều kiện khiến một property bị từ chối. Sau lỗi, đọc lại hoặc xác minh server state nếu có thể; không mong mặc định all-or-nothing.

**Test 5 — Bulk replacement:** Đặt các keys A/B, sau đó gọi bulk với chỉ A; xác nhận B bị clear theo contract nếu driver hỗ trợ. Kiểm thử riêng để không ảnh hưởng pool khác.

**Test 6 — Single null clear:** Gọi `setClientInfo("ApplicationName", null)` trên connection test và kiểm tra cách driver phản hồi; không dùng môi trường production shared pool bừa bãi.

**Test 7 — Pool reuse:** Mượn connection, set metadata, trả pool, mượn lại; xác nhận chính sách reset và độ cách ly của request/tenant.

**Test 8 — No support:** Với driver không hỗ trợ client-info, application có hành vi fallback phù hợp và không crash chỉ vì diagnostics metadata bị từ chối.

**Test 9 — Error diagnostics:** Kiểm tra `getFailedProperties` null, empty và map có nhiều entries; log name/status nhưng không log property values.

**Test 10 — Version upgrades:** Kiểm thử lại sau khi nâng JDBC driver, database server hoặc JDK, bởi danh sách properties/limits/behavior có thể đổi dù API `java.sql` vẫn tương thích.

## 15. Bài tập thực hành

1. **Đọc metadata:** Trong một DB thử nghiệm có JDBC driver hợp lệ, gọi `getClientInfoProperties` và chỉ in các tên `NAME`/`MAX_LEN`; giải thích vì sao `ApplicationName` có thể không có.
2. **Thử set một property:** Chọn một key có trong metadata và set giá trị ngắn. So sánh trạng thái qua `getClientInfo(key)` nếu driver hỗ trợ.
3. **Phân loại failure:** Viết hàm chuyển mỗi `ClientInfoStatus` thành hành động `skip / validate / shorten / investigate`. Không tự động retry khi không có lý do.
4. **Bulk vs single:** Chứng minh sự khác nhau giữa `setClientInfo(Properties)` và `setClientInfo(name, value)` trên database/driver hỗ trợ.
5. **Xử lý warning:** Lấy `connection.getWarnings()` đúng thời điểm sau khi set để nhận biết property unsupported hoặc truncation warning.
6. **Pool:** Viết integration test qua datasource/pool để chứng minh metadata của request A không tồn tại sai ở request B.

## 16. Câu hỏi ôn tập

**Câu 1.** `SQLClientInfoException` xuất hiện trong tình huống gì?

**Đáp án:** Khi một hoặc nhiều client-info properties không thể được đặt trên `Connection` qua `setClientInfo`. Nó kế thừa `SQLException` và có failed-properties map khi driver cung cấp.

**Câu 2.** `REASON_UNKNOWN_PROPERTY` và `REASON_VALUE_INVALID` khác gì?

**Đáp án:** Cái đầu báo tên property không được nhận diện; cái sau báo giá trị không hợp lệ cho một tên property.

**Câu 3.** `REASON_VALUE_TRUNCATED` có chứng minh driver lưu phiên bản đã cắt bớt không?

**Đáp án:** Không. Trong failed-properties map, nó chỉ ra giá trị quá lớn nên lần đặt property đó không thành công; driver có thể chọn behavior warning/truncate trong tình huống khác.

**Câu 4.** `getFailedProperties()` khác `getSQLState()` như thế nào?

**Đáp án:** `getFailedProperties` trả danh sách tên property và lý do từng property; `getSQLState` là trạng thái lỗi chung theo định dạng SQLState của `SQLException`.

**Câu 5.** `setClientInfo(Properties)` có thêm keys vào tập hiện tại không?

**Đáp án:** Không. Nó thay thế tập hiện tại. Keys cũ không có trong `Properties` mới sẽ được clear, và bulk set không được bảo đảm atomic.

**Câu 6.** Muốn biết tên client-info nào được driver hỗ trợ thì dùng API gì?

**Đáp án:** `connection.getMetaData().getClientInfoProperties()`, đọc `NAME`, `MAX_LEN`, `DEFAULT_VALUE` và `DESCRIPTION`.

**Câu 7.** Gọi `getClientInfo("ApplicationName")` trả `null` có chứng minh tên không hỗ trợ không?

**Đáp án:** Không. Null có thể là unsupported hoặc chưa set và không có default value; cần metadata/driver docs.

**Câu 8.** Gắn `ClientUser="alice"` có làm database thực thi dưới quyền Alice không?

**Đáp án:** Không. Client info chỉ phục vụ accounting/diagnostics/debugging, không phải login/authorization.

**Câu 9.** Nếu `setClientInfo` không ném exception thì có nên bỏ qua `SQLWarning` không?

**Đáp án:** Không nên nếu yêu cầu observability nghiêm ngặt. Driver có thể cảnh báo tên không nhận diện hoặc giá trị quá dài bị cắt.

**Câu 10.** Tại sao connection pool cần quan tâm `setClientInfo`?

**Đáp án:** Metadata có thể tồn tại trên physical connection sau khi trả về pool, làm thông tin chẩn đoán sai giữa các request nếu không reset đúng cách.

## 17. Checklist áp dụng trong sản phẩm

- **Tìm hiểu driver thực**: đọc `DatabaseMetaData.getClientInfoProperties` trước khi chọn name/value.
- **Dùng đúng API**: `setClientInfo` chỉ cho client metadata, không dùng như cấu hình login/transaction.
- **Phân biệt single và bulk**: bulk **thay toàn bộ tập**, omitted keys bị clear; có thể fail một phần.
- **Bắt `SQLClientInfoException`** và đọc `getFailedProperties` an toàn với null/empty.
- **Phân loại bốn `ClientInfoStatus`**; không nhầm với `SQLState`.
- **Kiểm tra `SQLWarning` khi có yêu cầu**; absence of exception không bảo đảm mọi điều bạn kỳ vọng đã xảy ra.
- **Đọc lại `getClientInfo` nếu driver cho phép** và hiểu giới hạn deferred updates.
- **Không log property values chứa dữ liệu nhạy cảm**; tránh đưa credentials hoặc PII vào client info.
- **Quản lý pool/reset** khi một physical connection phục vụ nhiều request/tenant.
- **Kiểm thử nhiều drivers/JDKs**, không giả định `ApplicationName` là bắt buộc.
- **Giữ diagnostics non-critical theo chính sách** hoặc fail setup có chủ đích nếu thông tin bắt buộc cho auditing.
- **Sử dụng JDBC 17+** và các API đang hỗ trợ, không cần thư viện legacy cho `SQLClientInfoException`.

## 18. Tài liệu chính thức

- [Oracle Java SE 17 — SQLClientInfoException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLClientInfoException.html): exception cho client info properties không được set, failed map và vấn đề partial success.
- [Oracle Java SE 17 — ClientInfoStatus](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ClientInfoStatus.html): bốn lý do `REASON_*`.
- [Oracle Java SE 17 — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): hai `setClientInfo` overloads, `getClientInfo`, warning và semantics.
- [Oracle Java SE 17 — DatabaseMetaData](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html): `getClientInfoProperties` và cột metadata chuẩn.
- [Oracle Java SE 17 — SQLWarning](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLWarning.html): warning chain cho non-fatal database issues.
- [Oracle Java SE 25 — SQLClientInfoException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLClientInfoException.html): API vẫn hiện hành trên JDK hiện đại.
