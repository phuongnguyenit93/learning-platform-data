# JDBC kết nối: Client info, setClientInfo và getClientInfo

## Mục tiêu học tập

Trong JDBC, **java.sql.Connection** đại diện cho một phiên làm việc với database thông qua driver. Bên cạnh transaction và những thiết lập kết nối, JDBC có **client information properties**: các cặp tên/giá trị chuỗi dùng cho **accounting, diagnostics và debugging** của kết nối. Chúng có thể giúp quản trị viên CSDL nhận biết ứng dụng hoặc loại công việc đang dùng session, nhưng **không phải cơ chế xác thực hay phân quyền**.

Bài này tập trung trực tiếp vào bốn API:

- **Connection.setClientInfo(String name, String value)**: thay đổi một client-info property.
- **Connection.setClientInfo(Properties properties)**: thay thế tập client-info properties hiện tại.
- **Connection.getClientInfo(String name)**: đọc giá trị một property.
- **Connection.getClientInfo()**: lấy một Properties biểu diễn những client-info properties hiện tại mà driver hỗ trợ.

Sau bài học bạn sẽ:

1. Hiểu client info được lưu ở đâu, giới hạn của nó và khi nào nên/không nên dùng.
2. Phân biệt overload setter **một property** với overload **Properties thay thế toàn tập**.
3. Tìm danh sách tên hỗ trợ và **MAX_LEN** bằng **DatabaseMetaData.getClientInfoProperties()**, thay vì giả định driver nào cũng có ApplicationName.
4. Hiểu **null**, cảnh báo **SQLWarning**, ngoại lệ **SQLClientInfoException** và map **getFailedProperties()**.
5. Xử lý **bulk update có thể không atomic**, tránh suy luận sai về transaction rollback.
6. Đặt client info đúng lifecycle trong ứng dụng dùng **DataSource/connection pool** và không làm lộ dữ liệu nhạy cảm.
7. Biên dịch/chạy một chương trình Java 17+ tự kiểm tra contract bằng **test double** không cần JDBC driver bên ngoài; phân biệt rõ kết quả mô phỏng và kết quả database thực tế.
8. Xây integration tests với driver thật để xác nhận hỗ trợ, độ dài, readback và database-side monitoring.

**Phạm vi:** API chuẩn **java.sql** tiếp tục có mặt trong Java SE hiện đại, ví dụ chạy với **OpenJDK 24.0.2 --release 17**. Chỉ dùng kiến thức còn áp dụng hiện nay.

## 1. Client info dùng để làm gì?

Một hệ thống thường có nhiều service dùng chung một database:

~~~text
orders-api ───────┐
billing-worker ───┼─> JDBC Connection(s) ──> Database server
report-service ───┘            │
                               └── optional client-info metadata
                                   ApplicationName = orders-api
                                   ClientUser      = job-42
                                   ClientHostname  = node-7
~~~

Nếu driver/server hỗ trợ, những thông tin này có thể xuất hiện trong **session parameters, special registers, system tables hoặc metadata/monitoring views**, giúp chẩn đoán kết nối nào đến từ ứng dụng nào.

**JDBC không bắt buộc mọi driver hỗ trợ các tên giống nhau hoặc lưu theo cùng một cơ chế.** Driver có thể trì hoãn việc cập nhật metadata ở phía server đến lần prepare/execute SQL tiếp theo nhằm tránh round trip không cần thiết. Đừng giả định setClientInfo xong là mọi monitoring view sẽ nhìn thấy giá trị ngay lập tức.

### 1.1. Client info không phải authentication

Các giá trị client info do phía ứng dụng cung cấp; ví dụ ghi **ClientUser=admin** không biến session DB thành tài khoản admin. Quyền thực tế vẫn được kiểm soát bởi database authentication, role/grant và application authorization.

Một bảng so sánh:

| API/cơ chế | Mục đích |
| --- | --- |
| **setClientInfo/getClientInfo** | Mô tả client, phục vụ accounting/diagnostics/debug |
| **DataSource.getConnection / DriverManager.getConnection** | Tạo kết nối và truyền cấu hình mở kết nối |
| **setAutoCommit, commit, rollback** | Điều khiển transaction |
| **setSchema, setCatalog** | Chọn namespace/schema của connection |
| **setTransactionIsolation** | Điều chỉnh mức cô lập transaction |
| **setNetworkTimeout** | Điều khiển giới hạn chờ network theo JDBC |
| **Tracing/logging** | Theo dõi request và distributed context |
| **Database roles/grants** | Kiểm soát quyền truy cập dữ liệu |

Đừng dùng client info để thay các API cấu hình JDBC đã có. Theo contract, ngoài việc lưu thông tin cho diagnostics, setClientInfo **không được làm thay đổi cách hoạt động khác của Connection**.

### 1.2. Thuộc tính thuộc scope Connection

Mỗi **Connection** mang một tập client info riêng. Nếu có nhiều kết nối hoạt động đồng thời, đặt property ở connection A không tự đặt trên connection B.

Khi connection pool tái sử dụng session vật lý, một property đã set cho công việc trước có thể còn đó nếu driver/pool/application không reset. Vì vậy client info cần được quản lý theo **quyền sở hữu và vòng đời kết nối**, nhất là các property thay đổi theo request.

## 2. Các phương thức chuẩn của Connection

Chữ ký chính:

~~~java
// Tóm tắt các chữ ký API, không phải một class độc lập.
void setClientInfo(String name, String value)
        throws SQLClientInfoException;

void setClientInfo(Properties properties)
        throws SQLClientInfoException;

String getClientInfo(String name)
        throws SQLException;

Properties getClientInfo()
        throws SQLException;
~~~

| Method | Hành vi |
| --- | --- |
| **setClientInfo(name,value)** | Set một key, value **null** sẽ xóa giá trị của key đó |
| **setClientInfo(Properties)** | Tập truyền vào **thay thế** tập client info đang có |
| **getClientInfo(name)** | Trả giá trị hoặc **null** khi unset/không có default hay không hỗ trợ |
| **getClientInfo()** | Trả danh sách client-info property values dưới dạng Properties |

**getClientInfo(name) trả null không chứng minh key không được hỗ trợ.** Nó có thể là một key được hỗ trợ nhưng chưa có giá trị và không có default. Để xác minh support, phải đọc metadata.

### 2.1. Setter một property

~~~java
// Mảnh code minh họa khi biến connection đã có Connection hợp lệ.
connection.setClientInfo("ApplicationName", "orders-api");
String name = connection.getClientInfo("ApplicationName");

// Dọn một key khi không còn cần.
connection.setClientInfo("ApplicationName", null);
~~~

Không mặc định rằng getter sẽ phản ánh được mọi chi tiết ở database server hoặc driver sẽ luôn hỗ trợ property. Nếu tên không được nhận diện, driver cần sinh **warning**; một số lỗi khác có thể làm phát sinh **SQLClientInfoException**.

### 2.2. Setter với Properties thay thế, không merge

~~~java
// Mảnh code minh họa.
Properties replacement = new Properties();
replacement.setProperty("ClientUser", "job-42");
connection.setClientInfo(replacement);
~~~

Nếu trước đó ApplicationName đã được set nhưng **replacement không chứa ApplicationName**, overload Properties **xóa giá trị cũ** theo contract. Đây không phải thao tác thêm ClientUser mà giữ nguyên các key khác.

**Muốn thay đổi một property**, ưu tiên overload String,String.

**Muốn thay toàn bộ bộ metadata**, dùng overload Properties khi bạn thực sự sở hữu toàn bộ tập và đã xác định cách xử lý lỗi. Không lấy getClientInfo() rồi sửa Properties local mà nghĩ Connection tự cập nhật; phải gọi setter phù hợp.

### 2.3. Properties rỗng và giá trị null

~~~java
connection.setClientInfo(new Properties()); // Xóa tập client info.
connection.setClientInfo("ClientUser", null); // Chỉ xóa ClientUser.
~~~

Hai lệnh có phạm vi khác nhau. Với connection pool, việc xóa **toàn tập** có thể vô tình mất ApplicationName do pool hoặc monitoring agent giữ. Nếu mục tiêu chỉ là bỏ metadata theo request, dọn riêng property của request hoặc khôi phục giá trị trước đó theo pool policy.

**Properties là một class Java dành cho String keys/values**, không nên cố lưu null values vào nó. Dùng overload String,String và null khi muốn xóa riêng key.

## 3. Các tên client info chuẩn nhưng không bắt buộc

JDBC Connection Javadoc nêu những tên chuẩn:

| Tên | Mô tả |
| --- | --- |
| **ApplicationName** | Tên ứng dụng hiện đang dùng connection |
| **ClientUser** | Người dùng/ngữ cảnh mà ứng dụng đang thực hiện công việc thay cho; có thể khác DB username |
| **ClientHostname** | Hostname của máy chạy client application |

**Driver không bắt buộc hỗ trợ đủ ba tên trên.** Nếu driver có một property đúng ngữ nghĩa một trong ba tên chuẩn, nên dùng tên chuẩn ấy. Một số DBMS/driver cung cấp các tên thêm, ví dụ thông tin accounting, nhưng chúng không phải một tập universal names có thể dùng trên mọi CSDL.

Không tự set ClientUser là email, access token hoặc session ID chứa dữ liệu nhạy cảm. Client info thường phục vụ diagnostics/monitoring với access control và retention khác hệ thống ứng dụng.

### 3.1. ClientUser không phải SQL login

~~~text
DB account thực tế: service_account
ClientUser metadata: report-job-42
~~~

Database vẫn kiểm tra quyền bằng **service_account** và quyền thực tế của session. ClientUser chỉ là mô tả có thể bị caller tự đặt sai.

### 3.2. Phân biệt connection properties

**DriverPropertyInfo** và các properties truyền vào **DriverManager.getConnection(...)** liên quan **cấu hình tạo kết nối**. Chúng không giống **Connection client-info properties** có thể đọc/ghi sau khi kết nối được tạo.

Ví dụ một JDBC URL có tùy chọn **applicationName** do driver riêng định nghĩa không tự chứng minh **setClientInfo("ApplicationName",...)** được driver đó hỗ trợ; phải xem tài liệu và metadata của đúng driver/version.

## 4. Khám phá khả năng driver qua DatabaseMetaData

Đừng đoán. **DatabaseMetaData.getClientInfoProperties()** trả **ResultSet** mô tả tập property driver thực sự hỗ trợ:

~~~java
// Mảnh minh họa với Connection connection có thật.
try (ResultSet rs =
        connection.getMetaData().getClientInfoProperties()) {
    while (rs.next()) {
        String name = rs.getString("NAME");
        int maxLength = rs.getInt("MAX_LEN");
        String defaultValue = rs.getString("DEFAULT_VALUE");
        String description = rs.getString("DESCRIPTION");
        System.out.println(name + ": max=" + maxLength);
    }
}
~~~

Các columns chuẩn:

| Column | Kiểu | Ý nghĩa |
| --- | --- | --- |
| **NAME** | String | Tên property được driver hỗ trợ |
| **MAX_LEN** | int | Độ dài tối đa cho value |
| **DEFAULT_VALUE** | String | Giá trị mặc định, có thể null |
| **DESCRIPTION** | String | Mô tả, thường nói nơi property được lưu trên server |

Theo Javadoc, ResultSet được sắp theo **NAME**. Nếu driver không hỗ trợ client info nào, kết quả có thể là tập rỗng.

### 4.1. Quy trình sử dụng metadata

1. Lấy Connection từ DataSource.
2. Dùng **connection.getMetaData().getClientInfoProperties()**.
3. Tìm **NAME** đúng với property dự định dùng.
4. Đọc **MAX_LEN**, mô tả, default.
5. Kiểm tra value của ứng dụng theo quy tắc driver.
6. Set đúng overload, xem warning/exception.
7. Đọc lại bằng getter nếu cần, hoặc xác minh qua monitoring DBMS theo driver docs.

Nếu property vắng khỏi metadata, không mặc định gửi nó đi rồi yêu cầu DBMS phải lưu lại.

### 4.2. Cẩn thận với Unicode và MAX_LEN

MAX_LEN là giới hạn do JDBC metadata trả, nhưng khi áp dụng vào text Unicode, hãy kiểm tra tài liệu driver/DBMS có dùng **UTF-16 code units, Unicode code points, bytes, hay cách tính riêng**. Một chuỗi tiếng Việt hoặc emoji có thể có kích thước khác nhau theo các phép đếm.

**Không assume rằng value.length() luôn bằng giới hạn thực trên server.** Nó là kiểm tra sơ bộ hữu ích trong một số môi trường nhưng không thay thế integration test.

## 5. Driver lưu client info như thế nào?

Theo JDBC spec, driver lưu property tại một nơi thích hợp phía database, ví dụ special register, session parameter hoặc system table column. Để tối ưu hiệu năng, driver **có thể defer** việc đưa giá trị sang server cho đến khi câu SQL được prepare/execute.

Điều này dẫn tới các điểm cần thận trọng:

- Setter có thể trả về trước khi monitoring view của DBMS cập nhật.
- Driver có thể dùng quy tắc khác nhau để kiểm tra/giới hạn value.
- Một database có thể có session metadata riêng cho monitoring nhưng không có API readback đầy đủ qua getter.
- Tên property, giới hạn, cách reset và cách quan sát là **vendor-dependent**.
- Client info được khai báo dành cho diagnostics/accounting, không làm thay đổi SQL permission, transaction isolation hoặc query planner theo contract chuẩn.

Nếu ứng dụng cần correlating request tại DBMS, cần test cả **thời điểm metadata xuất hiện** và **hành vi của pool**, không chỉ gọi setter một lần rồi tin rằng server đã lưu.

### 5.1. Không phải transaction data

**setClientInfo** không được chuẩn hóa thành một thao tác transaction có thể rollback như INSERT/UPDATE. Đừng dùng **connection.rollback()** để nghĩ rằng metadata của request A sẽ tự trở về mặc định. Hãy quản lý cleanup theo lifecycle của Connection.

### 5.2. Không dùng thay tracing

Client info thuộc **một Connection**. Một request có thể chạy qua nhiều database connections, microservices hoặc background jobs. Nó không tự cung cấp distributed tracing context, transaction spans hoặc security audit. Khi cần end-to-end tracing, dùng tracing pipeline phù hợp và chỉ gắn các thuộc tính không nhạy cảm vào JDBC client info nếu driver hỗ trợ.

## 6. SQLWarning, SQLClientInfoException và ClientInfoStatus

### 6.1. Warning khi tên không được nhận diện

JDBC yêu cầu driver sinh warning khi tên client info được set không được nhận diện. Nếu cần, kiểm tra chain:

~~~java
// Mảnh minh họa.
SQLWarning warning = connection.getWarnings();
while (warning != null) {
    System.err.println(
            "JDBC warning: " + warning.getSQLState()
                    + ", code=" + warning.getErrorCode());
    warning = warning.getNextWarning();
}
~~~

**Đừng log secret/value** trong warning diagnostics. Khi đã xử lý theo policy, có thể gọi **connection.clearWarnings()**, nhưng không xóa warning trước khi code quan sát kịp đọc.

### 6.2. Trường hợp quá dài

Khi value dài hơn giới hạn, driver có thể:

- **Truncate và tạo SQLWarning**.
- **Ném SQLClientInfoException**, theo contract setter một property thì value được yêu cầu không set thành công.

Vì vậy một ứng dụng không nên assert rằng **mọi driver nhất thiết phải throw** hoặc **mọi driver nhất thiết phải truncate**. Test hai behavior theo driver dùng trong production.

### 6.3. SQLClientInfoException có thêm failedProperties

**SQLClientInfoException** extends SQLException và cung cấp:

~~~java
// Mảnh minh họa bên trong catch (SQLClientInfoException e).
Map<String, ClientInfoStatus> reasons = e.getFailedProperties();
~~~

**ClientInfoStatus** có bốn enum values:

| Value | Ý nghĩa |
| --- | --- |
| **REASON_UNKNOWN** | Không rõ nguyên nhân từ chối |
| **REASON_UNKNOWN_PROPERTY** | Tên property không được driver nhận diện |
| **REASON_VALUE_INVALID** | Value không hợp lệ |
| **REASON_VALUE_TRUNCATED** | Value quá dài |

Trong diagnostics, có thể đọc **getFailedProperties()**, SQLState, vendor error code và error chain. Không dựa vào exception message duy nhất; không tự suy đoán status khi driver không cung cấp reason cụ thể.

### 6.4. Bulk update có thể không atomic

**setClientInfo(Properties)** thay thế toàn tập. Nếu có lỗi khi set một trong nhiều property, JDBC cho phép một số DBMS **đã áp dụng một số property trước khi ném exception**. Vì vậy sau lỗi:

- Đừng giả định tất cả giá trị vẫn ở trạng thái trước đó.
- Đừng giả định không có giá trị nào được ghi.
- Đọc **getFailedProperties()** để biết những key bị từ chối.
- Nếu cần, đọc lại state và thực hiện restore trong phạm vi mà ứng dụng sở hữu.
- Nếu session pool có nguy cơ rò metadata và không thể khôi phục, loại physical connection khỏi pool bằng cơ chế được pool hỗ trợ.
- Không dùng rollback để trông chờ undo metadata.

Một bulk client-info update **không phải** một atomic SQL transaction theo contract JDBC.

## 7. Ví dụ Java 17+ chạy độc lập: test double của Connection

Để code chạy được không cần DB server, URL hoặc password, ví dụ dùng **java.lang.reflect.Proxy** tạo test double tối thiểu cho **Connection**, **DatabaseMetaData** và **ResultSet**. Nó mô phỏng một số behavior mà JDBC spec cho phép.

**Phân biệt rõ:** Đây **không phải JDBC driver thật**. Các giá trị, warning, MAX_LEN và thứ tự áp dụng bulk được **chủ động mô phỏng** để dễ quan sát và kiểm thử. Bạn vẫn phải chạy integration test trên JDBC driver thật trước khi tin behavior trong production.

Chương trình minh họa:

1. Metadata công bố ApplicationName và ClientUser, mỗi value tối đa 16 ký tự.
2. Getter ban đầu trả null.
3. Setter một property đặt ApplicationName.
4. Bulk setter với chỉ ClientUser xóa ApplicationName.
5. Setter một key với null xóa ClientUser.
6. Property lạ được mô phỏng tạo SQLWarning.
7. Value quá dài ném SQLClientInfoException kèm REASON_VALUE_TRUNCATED.
8. Bulk update lỗi sau khi áp dụng một property, cho thấy tại sao không được mặc định atomicity.

### 7.1. File ClientInfoContractDemo.java

~~~java
import java.lang.reflect.Proxy;
import java.sql.ClientInfoStatus;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLClientInfoException;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLWarning;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.TreeSet;

public final class ClientInfoContractDemo {
    // SELF-CONTAINED TEST DOUBLE, NOT A REAL JDBC DRIVER/DATABASE.
    private static final Map<String, Integer> LIMITS =
            Map.of("ApplicationName", 16, "ClientUser", 16);

    public static void main(String[] args) throws SQLException {
        try (Connection connection = fakeConnection()) {
            try (ResultSet rs =
                    connection.getMetaData().getClientInfoProperties()) {
                List<String> properties = new ArrayList<>();
                while (rs.next()) {
                    properties.add(rs.getString("NAME") + ":"
                            + rs.getInt("MAX_LEN"));
                }
                System.out.println("supported=" + String.join(",", properties));
            }

            System.out.println("before=" +
                    connection.getClientInfo("ApplicationName"));
            connection.setClientInfo("ApplicationName", "orders-api");
            System.out.println("single=" +
                    connection.getClientInfo("ApplicationName"));

            Properties replacement = new Properties();
            replacement.setProperty("ClientUser", "batch-7");
            connection.setClientInfo(replacement);
            System.out.println("afterBulkApp=" +
                    connection.getClientInfo("ApplicationName"));
            System.out.println("afterBulkUser=" +
                    connection.getClientInfo("ClientUser"));
            System.out.println("allKeys=" +
                    new TreeSet<>(connection.getClientInfo().stringPropertyNames()));

            connection.setClientInfo("ClientUser", null);
            System.out.println("cleared=" + connection.getClientInfo("ClientUser"));

            connection.setClientInfo("UnknownKey", "value");
            System.out.println("unknownRead=" +
                    connection.getClientInfo("UnknownKey"));
            System.out.println("warning=" +
                    connection.getWarnings().getMessage());

            try {
                connection.setClientInfo(
                        "ApplicationName", "this-value-is-too-long");
                throw new AssertionError("Expected SQLClientInfoException");
            } catch (SQLClientInfoException e) {
                System.out.println("invalidReason="
                    + e.getFailedProperties().get("ApplicationName"));
            }

            Properties partial = new Properties();
            partial.setProperty("ApplicationName", "partial-ok");
            partial.setProperty("ClientUser", "value-too-long-for-our-demo");
            try {
                connection.setClientInfo(partial);
                throw new AssertionError("Expected bulk failure");
            } catch (SQLClientInfoException e) {
                System.out.println("bulkFailure="
                    + e.getFailedProperties().get("ClientUser"));
                System.out.println("partialApp="
                    + connection.getClientInfo("ApplicationName"));
            }
        }
    }

    private static Connection fakeConnection() {
        Map<String, String> values = new HashMap<>();
        SQLWarning[] warning = new SQLWarning[1];
        boolean[] closed = new boolean[1];
        return (Connection) Proxy.newProxyInstance(
                ClientInfoContractDemo.class.getClassLoader(),
                new Class<?>[] {Connection.class},
                (proxy, method, args) -> {
                    String name = method.getName();
                    if (name.equals("close")) {
                        closed[0] = true; return null;
                    }
                    if (name.equals("isClosed")) {
                        return closed[0];
                    }
                    if (name.equals("toString")) {
                        return "ClientInfoFakeConnection";
                    }
                    if (closed[0]) {
                        throw new SQLException("Connection closed");
                    }
                    if (name.equals("getMetaData")) {
                        return fakeMetaData();
                    }
                    if (name.equals("getClientInfo")) {
                        if (args == null || args.length == 0) {
                            Properties result = new Properties();
                            values.forEach(result::setProperty);
                            return result;
                        }
                        return values.get((String) args[0]);
                    }
                    if (name.equals("setClientInfo")) {
                        if (args.length == 2) {
                            setOne(values, warning,
                                    (String) args[0], (String) args[1]);
                        } else {
                            values.clear();
                            Properties props = (Properties) args[0];
                            for (String key : new TreeSet<>(
                                    props.stringPropertyNames())) {
                                setOne(values, warning, key,
                                        props.getProperty(key));
                            }
                        }
                        return null;
                    }
                    if (name.equals("getWarnings")) {
                        return warning[0];
                    }
                    if (name.equals("clearWarnings")) {
                        warning[0] = null; return null;
                    }
                    throw new SQLFeatureNotSupportedException(
                            "Fake does not implement " + name);
                });
    }

    private static void setOne(Map<String, String> values,
                               SQLWarning[] warning,
                               String key, String value)
            throws SQLClientInfoException {
        Integer maximum = LIMITS.get(key);
        if (maximum == null) {
            warning[0] = new SQLWarning("unknown property");
            return;
        }
        if (value != null && value.length() > maximum) {
            throw new SQLClientInfoException(
                    "Too long", Map.of(key,
                        ClientInfoStatus.REASON_VALUE_TRUNCATED));
        }
        if (value == null) {
            values.remove(key);
        } else {
            values.put(key, value);
        }
    }

    private static DatabaseMetaData fakeMetaData() {
        return (DatabaseMetaData) Proxy.newProxyInstance(
                ClientInfoContractDemo.class.getClassLoader(),
                new Class<?>[] {DatabaseMetaData.class},
                (proxy, method, args) -> {
                    if (method.getName().equals("getClientInfoProperties")) {
                        return fakePropertyRows();
                    }
                    throw new SQLFeatureNotSupportedException();
                });
    }

    private static ResultSet fakePropertyRows() {
        String[] names = {"ApplicationName", "ClientUser"};
        int[] pos = {-1};
        return (ResultSet) Proxy.newProxyInstance(
                ClientInfoContractDemo.class.getClassLoader(),
                new Class<?>[] {ResultSet.class},
                (proxy, method, args) -> {
                    switch (method.getName()) {
                        case "next":
                            return ++pos[0] < names.length;
                        case "getString":
                            String col = (String) args[0];
                            if ("NAME".equals(col)) return names[pos[0]];
                            if ("DEFAULT_VALUE".equals(col)) return null;
                            if ("DESCRIPTION".equals(col)) return "demo";
                            throw new SQLException("Unexpected column " + col);
                        case "getInt":
                            if ("MAX_LEN".equals((String) args[0])) return 16;
                            throw new SQLException("Unexpected int column");
                        case "close":
                            return null;
                        default:
                            throw new SQLFeatureNotSupportedException();
                    }
                });
    }
}
~~~

### 7.2. Lệnh biên dịch và chạy

Chạy trong thư mục chứa file ở trên, với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 --release 17 ClientInfoContractDemo.java
java ClientInfoContractDemo
~~~

Các lệnh này cũng hợp lệ trong Windows PowerShell. Chương trình không cần network, CSDL, thư viện driver, URL hoặc credentials.

### 7.3. Stdout chính xác

~~~text
supported=ApplicationName:16,ClientUser:16
before=null
single=orders-api
afterBulkApp=null
afterBulkUser=batch-7
allKeys=[ClientUser]
cleared=null
unknownRead=null
warning=unknown property
invalidReason=REASON_VALUE_TRUNCATED
bulkFailure=REASON_VALUE_TRUNCATED
partialApp=partial-ok
~~~

**Đã kiểm chứng 12 dòng stdout** khi compile bằng **javac 24.0.2 --release 17** và chạy trên OpenJDK 24.0.2. Đây là output **của fake**, không phải output cam kết từ driver thực.

### 7.4. Cách đọc kết quả test

- **supported=...**: fake metadata cung cấp hai tên và giới hạn 16.
- **before=null**: ApplicationName chưa có giá trị.
- **single=orders-api**: setter một key cập nhật thành công.
- **afterBulkApp=null**: setClientInfo(Properties) thay toàn tập và xóa key vắng mặt.
- **afterBulkUser=batch-7**: key có trong Properties được set.
- **allKeys=[ClientUser]**: fake snapshot hiện có một key được set.
- **cleared=null**: null qua overload String,String xóa value.
- **unknownRead=null**: fake không lưu key lạ.
- **warning=unknown property**: fake chủ động tạo SQLWarning.
- **invalidReason=REASON_VALUE_TRUNCATED**: fake mô phỏng driver chọn exception khi value quá dài.
- **bulkFailure=...**: key ClientUser bị từ chối trong một bulk update.
- **partialApp=partial-ok**: fake áp dụng key đầu trước khi lỗi ở key sau; đây là minh họa **partial failure** chứ không phải yêu cầu mọi driver áp dụng theo cùng thứ tự.

### 7.5. Vì sao dùng dynamic Proxy?

**Connection** có nhiều method không liên quan tới bài client info. Nếu tự implements toàn bộ Connection chỉ để test hai setter/getter, code bị loãng. **java.lang.reflect.Proxy** là cơ chế JDK hiện hành để dựng test double tập trung vào một số method cần kiểm tra.

Handler cố ý ném **SQLFeatureNotSupportedException** cho những phương thức khác. **Không dùng proxy giả này làm JDBC driver production**, không dùng để chứng minh network/transaction/server monitoring và không đưa dữ liệu thật vào nó.

## 8. Khi dùng Connection thật

Trong ứng dụng, Connection thường đến từ **DataSource** hoặc pool. Với một Connection đã được mượn, có thể kiểm tra hỗ trợ và đặt ApplicationName theo pattern sau:

~~~java
// Mảnh minh họa: dataSource do ứng dụng cấu hình sẵn.
try (Connection connection = dataSource.getConnection()) {
    boolean supportsApplicationName = false;
    try (ResultSet metadata =
            connection.getMetaData().getClientInfoProperties()) {
        while (metadata.next()) {
            if ("ApplicationName".equals(metadata.getString("NAME"))) {
                supportsApplicationName = true;
                break;
            }
        }
    }

    if (supportsApplicationName) {
        String prior = connection.getClientInfo("ApplicationName");
        try {
            connection.setClientInfo("ApplicationName", "orders-api");
            // Thực hiện công việc JDBC ở đúng connection này.
        } finally {
            connection.setClientInfo("ApplicationName", prior);
        }
    }
}
~~~

**Đây là mảnh minh họa, không phải chương trình độc lập**, vì dataSource và thao tác nghiệp vụ là do ứng dụng cung cấp. Code production còn phải xử lý: length MAX_LEN, warnings, SQLClientInfoException, reset failure, original failure bị che bởi exception từ finally, và cách pool invalidate connection khi không thể dọn state.

Nếu property không được hỗ trợ, nghiệp vụ thường vẫn phải chạy nhưng không có metadata bổ sung đó. Tách lớp gắn metadata tùy chọn khỏi lớp thực thi SQL thay vì vô tình bỏ qua nghiệp vụ khi support=false.

### 8.1. Dùng DataSource thay vì hard-code URL/password

Không đưa user/password vào source hay command line của ví dụ chỉ để minh họa API. Trong ứng dụng thực tế, **DataSource** nên được cấu hình với secret management, network security và pool settings theo chuẩn triển khai. Client info không mang credentials và không bảo đảm bí mật.

### 8.2. Kiểm tra warning/exception sau set

Ngoài **getClientInfo()**, nên kiểm tra **getWarnings()** nếu cần biết driver có cảnh báo unsupported/truncation. Với exception, đọc map failedProperties và bảo toàn error chain. Nếu setup metadata là tùy chọn, chính sách cần quyết định liệu lỗi đó là warning vận hành hay phải làm request fail; tránh mặc định bỏ qua mọi SQLException.

### 8.3. Driver có thể defer update

Có trường hợp client-info value chưa hiện ngay trên server view cho đến khi Connection prepare/execute statement. Việc test getClientInfo trả đúng không phải bằng chứng mọi hệ thống monitoring phía DB đã nhìn thấy giá trị tại cùng thời điểm. Kiểm tra timing với chính driver/server trong integration environment.

## 9. Connection pooling và trách nhiệm cleanup

Ví dụ hai request liên tiếp:

~~~text
Pool giữ physical session P1
    │
    ├─ Request A: setClientInfo("ClientUser", "request-A")
    │             thực hiện SQL
    │             trả Connection handle
    │
    └─ Request B: mượn lại session P1
                  có thể thấy metadata cũ nếu chưa reset
~~~

**Connection.close() trong pool thường trả handle về pool**, không nhất thiết đóng session vật lý ngay. Không có bảo đảm phổ quát rằng pool tự reset mọi client-info property; phải xem contract của pool/driver.

Để tránh rò attribution:

1. Chọn rõ key nào là **application-level** (ít thay đổi) và key nào là **request-level**.
2. Khi mượn Connection, thiết lập request metadata nếu được hỗ trợ.
3. Khi công việc kết thúc, restore/clear key mà request sở hữu.
4. Đưa cleanup vào **finally**, kể cả khi SQL lỗi.
5. Nếu restore thất bại, ghi lỗi phù hợp và **evict/invalidate** connection theo pool API khi có nguy cơ session state không sạch.
6. Kiểm thử hai lần borrow liên tiếp, không chỉ một request thành công.
7. Không giả định **rollback** hay gọi **close()** đều reset client-info metadata.
8. Tránh **setClientInfo(new Properties())** nếu việc đó xóa những key do pool hoặc monitoring component quản lý.

**Cẩn thận với exception trong finally:** nếu SQL nghiệp vụ đã ném SQLException và phần cleanup lại ném SQLClientInfoException, exception cleanup có thể che lỗi gốc nếu code không chủ động giữ/suppress đúng. Với hệ thống quan trọng, dùng một scope helper hoặc pool hook có chính sách bảo toàn primary failure.

### 9.1. Đừng gắn thông tin user nhạy cảm vào client info

ClientUser là metadata tự khai, có thể xuất hiện ở DB administration views. Không gắn email, số điện thoại, JWT, password, session token, PII hoặc nội dung query vào properties. Một mã tác vụ/tracing identifier đã được đánh giá có thể phù hợp hơn, nhưng cần xem retention/access controls.

### 9.2. Không dùng metadata để ra quyết định an ninh

Một session có ClientUser=alice không chứng minh Alice đã được xác thực ở ứng dụng. Quyền database vẫn gắn với DB account/roles; authorization nghiệp vụ do hệ thống thực hiện. Không dùng một chuỗi có thể set từ client để cấp quyền hoặc tính phí nếu chưa có nguồn xác thực độc lập.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| getClientInfo(ApplicationName) trả null | Property unset, không default hoặc không hỗ trợ | Tra metadata, không dựa vào null để suy support |
| setClientInfo không ném lỗi nhưng server chưa thấy | Driver defer hoặc driver-specific behavior | Test monitoring timing, warnings và docs |
| Bulk setter làm mất key đang có | Overload Properties thay toàn tập | Dùng setter String,String khi chỉ đổi một key |
| Bulk failure để lại trạng thái khác | Một phần update đã được áp dụng | Readback và restore/evict tùy pool |
| Unknown property không throw | Driver tạo SQLWarning | Đọc getWarnings, kiểm tra NAME support |
| Value quá dài bị cắt | Driver chọn truncate+warning | Kiểm tra MAX_LEN, warning và readback |
| SQLClientInfoException | Property bị từ chối hoặc connection/DB error | Xem getFailedProperties, SQLState, vendor code |
| ClientUser được set nhưng quyền SQL không đổi | Client info không phải authorization | Dùng authentication/roles/grants |
| Metadata vẫn ở session sau rollback | Client info không phải transaction state | Reset riêng trong lifecycle |
| Request B thấy ClientUser của A | Pool tái sử dụng session chưa reset | Cleanup trong finally, kiểm thử borrow/return |
| Không thấy ApplicationName trên vendor B | Tập properties là vendor-dependent | Discovery qua DatabaseMetaData |
| Unicode bị truncate bất ngờ | Giới hạn được driver đo khác với Java length | Test theo docs và encoding vendor |
| Logs DB có token/user identifier | Dữ liệu nhạy cảm bị gửi thành metadata | Không truyền secret/PII qua client info |
| getClientInfo(Properties) không phản ánh mọi tên supported | Values unset/default hoặc cách biểu diễn Properties | Dùng DatabaseMetaData cho names, getter cho current values |
| Sau close không thể set | Connection đã đóng | Quản lý đúng scope; không dùng handle sau close |

### 10.1. Quy trình debug

1. Ghi metadata môi trường không nhạy cảm: **driver version, DBMS version, pool version**.
2. Dùng **getClientInfoProperties()** để liệt kê NAME/MAX_LEN/DEFAULT_VALUE/DESCRIPTION.
3. Xem spelling/case tên property, giới hạn và validation rules.
4. Đặt key qua overload đúng; nếu chỉ thay một key không dùng bulk Properties.
5. Đọc getter và SQLWarning chain.
6. Nếu exception, đọc failedProperties, SQLState, vendor code.
7. Nếu bulk failure, không coi trạng thái đã rollback.
8. Nếu server monitoring khác, test prepare/execute timing.
9. Nếu dùng pool, test borrowed connection trước và sau cleanup.
10. Đối chiếu tài liệu JDBC driver cụ thể; không suy từ test double rằng vendor có cùng behavior.

## 11. Integration test với database thật

**Test double không thay thế integration testing**. Một ma trận tối thiểu:

| Tình huống | Cần xác minh |
| --- | --- |
| Đọc metadata | Driver hỗ trợ keys nào, MAX_LEN/default/description ra sao |
| ApplicationName | Set/get có thành công, trường hợp null/empty |
| Unsupported key | Warning và behavior khi tên không được nhận diện |
| Value vượt giới hạn | Truncate+warning hoặc SQLClientInfoException |
| Unicode value | Cách driver tính giới hạn và encoding |
| Bulk replacement | Keys vắng mặt có bị xóa đúng contract không |
| Bulk partial failure | Readback và phương án khôi phục |
| Server monitoring | Session view nào chứa metadata; xuất hiện sau hoạt động nào |
| Commit/rollback | Không tự giả định metadata được undo |
| Pool reuse | Request A không làm metadata của request B bị sai |
| Closed connection | Error của setter/getter theo contract |
| Reconnect/failover | Driver/pool có tái đặt metadata không |
| Logging/privacy | Không có credential/PII trong DB monitoring/logs |

Mỗi lần nâng JDBC driver hoặc DBMS nên chạy lại các integration tests này, bởi tập tên/độ dài/thời điểm server nhận metadata có thể thay đổi.

### 11.1. Kiểm thử pool reuse

Mượn Connection A, gắn metadata test và chạy một câu SQL không gây thay đổi dữ liệu; trả vào pool. Mượn tiếp Connection B dưới điều kiện tái sử dụng session có kiểm soát; xác minh metadata không bị rò từ A sang B. Lặp lại khi SQL ném lỗi và khi reset metadata thất bại.

Không chạy bài test với secret/user thật hoặc trên production database khi không được phép.

### 11.2. Quản lý observability

Nếu cần dùng client info để chẩn đoán, ghi các sự kiện như:

- Property nào được set/reset.
- Driver có hỗ trợ property đó không.
- Warning/error code, không chứa value nhạy cảm.
- Mối liên hệ với Connection/borrow scope đã được thiết kế.
- Phiên bản driver/DBMS và timestamp nếu phù hợp.

Không biến client info thành hệ thống lưu event logs hoặc audit trail đáng tin. Nó chỉ là metadata theo session, có thể bị thay đổi và không có cùng security guarantees.

## 12. Bài tập

1. Thay ApplicationName trong chương trình test bằng value dài hơn 16 ký tự; dự đoán status của SQLClientInfoException.
2. Sau khi set ApplicationName, dùng **setClientInfo("ClientUser", "job-42")** thay cho bulk setter; kiểm tra ApplicationName có còn không.
3. Dùng **setClientInfo(new Properties())** rồi đọc getClientInfo() và getClientInfo("ApplicationName") trong test double.
4. Thêm **ClientHostname** vào LIMITS và fake metadata, kiểm tra ResultSet sắp theo NAME.
5. Thay implementation fake để **truncate+SQLWarning** thay vì exception khi value dài, so sánh behavior hợp lệ.
6. Mô phỏng REASON_VALUE_INVALID cho một value bị từ chối và thiết kế cách report key/reason không ghi nội dung bí mật.
7. Dựng một test bulk failure trong đó một key được ghi trước khi lỗi xảy ra; viết logic restore phù hợp.
8. Viết helper đọc metadata và trả một Map immutable gồm property name/max length; kiểm tra ResultSet được đóng.
9. Trong test DB với driver thực, xác minh khi setClientInfo không có warning thì database monitoring có phản ánh metadata ngay hay sau SQL prepare/execute.
10. Thiết kế test connection pool borrow/return, bảo đảm request B không thấy ClientUser của A.
11. Giải thích vì sao ClientUser=admin không làm thay đổi DB privileges.
12. Tạo logging policy: chỉ tên property, status, SQLState và reason; không log value hoặc token.

## 13. Checklist trước production

- [ ] Client info chỉ dùng cho **accounting/diagnostics/debug**, không cho authorization.
- [ ] Driver hỗ trợ key qua **DatabaseMetaData.getClientInfoProperties**.
- [ ] Đọc **NAME/MAX_LEN/DEFAULT_VALUE/DESCRIPTION** và validation theo driver.
- [ ] Không giả định ApplicationName/ClientUser/ClientHostname luôn có.
- [ ] Không gửi secret, token, user PII hoặc thông tin nhạy cảm.
- [ ] Khi đổi một key, dùng đúng setter String,String.
- [ ] Khi dùng Properties, hiểu rõ đây là **thay toàn tập**, không merge.
- [ ] Null xóa một key; Properties rỗng xóa tập metadata.
- [ ] Kiểm tra warning chain và lỗi SQLClientInfoException.getFailedProperties().
- [ ] Không giả định bulk update atomic hoặc rollback khôi phục client info.
- [ ] Xét defer-to-next-statement behavior của driver/server.
- [ ] Quản lý lifecycle/pool, reset hoặc restore metadata đã dùng.
- [ ] Khi reset thất bại, không trả session nghi ngờ sạch lại vào pool.
- [ ] Mỗi ResultSet/Connection được đóng đúng scope qua try-with-resources.
- [ ] Đã chạy integration tests trên driver/DBMS/pool thực tế.
- [ ] Có quy tắc versioning và diagnostics nếu behavior driver thay đổi.

## Kết luận

**Connection.setClientInfo/getClientInfo** là API chuẩn để đặt và đọc **client metadata** trên một JDBC Connection. Tập properties được hỗ trợ không giống nhau ở mọi driver; cần hỏi **DatabaseMetaData.getClientInfoProperties()**. Setter **String,String** thay một key và nhận null để xóa, còn setter **Properties** **thay toàn bộ tập** và có thể thất bại một phần.

Đọc **SQLWarning** và **SQLClientInfoException.getFailedProperties()** khi cần, quản lý cleanup cho connection pool và đừng coi client info như authentication, transaction state hay distributed tracing. Mô phỏng giúp hiểu API, nhưng chỉ **integration test trên driver/server thật** mới xác định một property được hỗ trợ, được lưu và quan sát thế nào.

**Tài liệu JDK chính thức hiện hành:**

- [Connection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html)
- [DatabaseMetaData — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DatabaseMetaData.html)
- [SQLClientInfoException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLClientInfoException.html)
- [ClientInfoStatus — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ClientInfoStatus.html)
- [SQLWarning — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLWarning.html)
- [Connection — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html)