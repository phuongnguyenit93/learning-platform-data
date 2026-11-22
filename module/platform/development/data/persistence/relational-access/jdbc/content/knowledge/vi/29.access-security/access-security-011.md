# Kiểm soát JDBC URL và thuộc tính kết nối từ nguồn không tin cậy

Một ứng dụng Java dùng **JDBC** thường nhận cấu hình kết nối qua `DataSource`, JDBC URL, tài khoản và các thuộc tính của driver. Cấu hình này quyết định ứng dụng **kết nối tới đâu, xác thực với ai, dùng phương thức bảo vệ đường truyền nào và bật những khả năng gì của driver**. Nếu lấy nguyên các giá trị đó từ request, biểu mẫu quản trị chưa được kiểm soát, file do khách hàng tải lên hoặc nguồn cấu hình không đáng tin cậy rồi truyền trực tiếp vào `DriverManager.getConnection(...)`, ứng dụng có thể bị dẫn tới máy chủ không được phép hoặc hoạt động ở chế độ bảo mật yếu hơn thiết kế.

Bài thuộc chương **Bảo mật truy cập** của module **JDBC**. Trọng tâm là xác định ranh giới tin cậy của **JDBC URL và connection properties**, thiết kế lựa chọn `DataSource` theo danh sách cho phép, quản lý tài khoản và TLS, tránh truyền thuộc tính driver tùy ý, giám sát kết nối và kiểm thử trường hợp nhập độc hại. Đây là những biện pháp bổ sung cho `PreparedStatement`, phân quyền cơ sở dữ liệu, transaction và các kỹ thuật bảo mật khác.

**Nguyên tắc chính:** dữ liệu không đáng tin cậy có thể được dùng để **chọn một cấu hình kết nối đã được phía server phê duyệt**, nhưng không được mặc nhiên có quyền **định nghĩa hoặc sửa trực tiếp điểm đến, driver, thông tin xác thực và chính sách bảo mật của kết nối**.

## 1. JDBC URL là cấu hình có quyền lực, không phải chuỗi dữ liệu thông thường

JDBC URL có dạng tổng quát bắt đầu bằng `jdbc:`, nhưng phần còn lại do **driver tương ứng** định nghĩa. Ví dụ:

```text
jdbc:postgresql://db.example.internal:5432/orders
jdbc:mysql://db.example.internal:3306/orders
jdbc:sqlserver://db.example.internal:1433;databaseName=orders
```

Các chuỗi trên chỉ minh họa **hình thức URL của từng driver**. Không giả định chúng có cùng cách xử lý dấu `?`, `&`, `;`, tên host, tên database, URL encoding hoặc thuộc tính cấu hình. Một số driver còn hỗ trợ nhiều host, chế độ failover, kết nối tới socket đặc biệt hoặc tài nguyên cục bộ.

Một đoạn mã không nên có ở ranh giới HTTP:

```java
// KHÔNG AN TOÀN: jdbcUrl đến trực tiếp từ request của người dùng.
String jdbcUrl = request.getParameter("jdbcUrl");
Connection connection = DriverManager.getConnection(
        jdbcUrl, applicationUser, applicationPassword);
```

Đây là **mẫu sai để nhận diện**, không phải đoạn mã nên triển khai. Nếu người gọi điều khiển được `jdbcUrl`, họ có thể yêu cầu driver tìm một điểm đến ngoài dự định. Trong trường hợp cấu hình xác thực và giao thức không được bảo vệ đúng, thông tin xác thực có thể được gửi tới máy chủ không tin cậy. Ngay cả khi không lộ mật khẩu, ứng dụng vẫn có thể tạo socket tới mạng nội bộ, tiêu hao tài nguyên, gây lỗi hoặc tương tác với cơ sở dữ liệu khác.

Khác biệt với SQL injection cần được hiểu rõ:

- `PreparedStatement` với placeholder `?` bảo vệ **giá trị tham số trong câu SQL**, trong phạm vi driver/database hỗ trợ.
- Nó **không kiểm soát** JDBC URL, tên driver, địa chỉ server, thuộc tính TLS hoặc tài khoản được dùng để tạo `Connection`.
- Chỉ tham số hóa SQL **không đủ** nếu người dùng đã điều hướng ứng dụng tới một database không được phép.

## 2. Nguồn nào cần được xem là chưa đáng tin cậy?

Một nguồn trông giống “cấu hình” vẫn có thể chưa được phép điều khiển kết nối. Ví dụ:

| Nguồn dữ liệu | Nguy cơ | Chính sách phù hợp |
| --- | --- | --- |
| Tham số HTTP, query string, JSON body | Người gọi có thể gửi URL/host/driver/property bất kỳ | Không chấp nhận JDBC URL thô; nhận **mã cấu hình đã cho phép** |
| Header, cookie, JWT claim chưa kiểm chứng | Dữ liệu có thể bị giả mạo hoặc không có phạm vi quyền phù hợp | Xác thực/ủy quyền; tách tenant identity khỏi dữ liệu tùy ý |
| File CSV/YAML/JSON do khách hàng tải lên | Có thể chứa connection string hoặc thuộc tính driver ngoài dự kiến | Parse như dữ liệu, không tự tạo `DataSource` từ file |
| Bản ghi DB do người dùng có quyền sửa | Có thể bị thay đổi sau khi được hệ thống tin cậy lần đầu | Xem là input chưa đáng tin cậy; kiểm soát thay đổi/approval |
| Remote configuration service, secrets store | Thường có quản trị nhưng vẫn có thể lỗi hoặc bị sửa sai | RBAC, xác thực nguồn, kiểm tra schema và audit thay đổi |
| Biến môi trường, JVM properties | Thường do người vận hành đặt, nhưng có thể bị thay đổi trong CI/deploy | Giới hạn người sửa, kiểm tra ở startup; không tự xem mọi giá trị là an toàn |
| Mẫu cấu hình có sẵn trong code/repository được review | Độ tin cậy cao hơn | Kiểm soát phiên bản, review, tránh lộ secret trong repository |

**Độ tin cậy gắn với quyền kiểm soát**, không phải tên file hoặc nơi lưu trữ. Một chuỗi từ `System.getenv("JDBC_URL")` có thể là cấu hình đáng tin khi chỉ hệ thống triển khai được sửa, nhưng cũng có thể là dữ liệu tùy ý nếu một pipeline cho phép bên ngoài đẩy thẳng giá trị vào biến đó.

Phân biệt ba vai trò:

1. **Người dùng ứng dụng:** có thể đề xuất một thao tác nghiệp vụ hoặc chọn hồ sơ dữ liệu được cho phép.
2. **Hệ thống cấu hình được ủy quyền:** quản lý endpoint, driver, TLS, secret và chính sách sử dụng.
3. **Tầng hạ tầng JDBC:** xây dựng `DataSource` và `Connection` từ những lựa chọn đã được duyệt, không sửa theo các tham số tùy ý của request.

## 3. Các rủi ro chính khi cho điều khiển URL và thuộc tính

| Rủi ro | Cách phát sinh | Tác động có thể có |
| --- | --- | --- |
| **Kết nối tới điểm đến ngoài phạm vi** | Người gọi điều khiển host, port, URL hoặc danh sách failover | Ứng dụng truy cập DB khác, mạng nội bộ hoặc endpoint do bên ngoài quản lý |
| **Lộ thông tin xác thực** | Ghép secret của ứng dụng vào URL tùy ý, TLS không xác minh danh tính server | Mật khẩu hoặc thông tin phiên có thể bị gửi đến phía không tin cậy |
| **Hạ cấp bảo vệ đường truyền** | Chấp nhận thuộc tính tắt TLS hoặc bỏ kiểm tra chứng chỉ/danh tính | Truyền thông bị nghe lén hoặc giả mạo server tùy điều kiện mạng |
| **Kích hoạt tính năng driver ngoài ý muốn** | Cho người dùng truyền mọi thuộc tính, kể cả phần mở rộng riêng driver | Truy cập file, thực thi SQL khởi tạo, nạp dữ liệu cục bộ, thay đổi logic xử lý... tùy driver |
| **Lạm dụng tài nguyên** | Tạo pool tới endpoint tùy ý, timeout lớn, nhiều hồ sơ DB khác nhau | Cạn thread, socket, connection, bộ nhớ và giới hạn phiên của server |
| **Vượt ranh giới tenant** | Tin tenant/profile ID từ request mà không kiểm tra quyền | Kết nối đến dữ liệu của tenant khác |
| **Lộ secret qua log/monitoring** | Ghi nguyên URL, `Properties` hoặc exception chứa thông tin nhạy cảm | Secret lọt vào log, tracing, error response, issue tracker |
| **Phụ thuộc parser không chính xác** | Validate chuỗi bằng `startsWith`/regex đơn giản hoặc parser URI không phù hợp | URL hợp lệ theo driver nhưng được giải thích khác với cách kiểm tra |

Những chức năng cụ thể gây rủi ro phụ thuộc **hệ quản trị, driver, phiên bản và cấu hình**. Không suy rằng mọi JDBC driver đều hỗ trợ cùng kiểu URL hoặc cùng thuộc tính nguy hiểm. Khi xem xét security, phải lập danh sách các driver thực sự được đóng gói cùng ứng dụng và tài liệu của chính các phiên bản đó.

### Kết nối ra ngoài là một bề mặt tấn công riêng

Một URL do người dùng chọn có thể khiến ứng dụng mở kết nối **từ mạng của server**, không phải từ máy người dùng. Về mặt mô hình rủi ro, đây là bề mặt tương tự các lỗi *server-side request forgery* (SSRF): người gọi khiến server truy cập địa chỉ mà bản thân họ có thể không truy cập được.

Đối với JDBC, hoạt động này còn có thể dùng **quyền database và secret của ứng dụng**. Vì vậy chỉ kiểm tra câu SQL ở DAO là không đủ; việc **chọn điểm đến** phải được bảo vệ ở lớp cấu hình và mạng.

## 4. Quy tắc an toàn nhất: chỉ cho chọn hồ sơ kết nối đã đăng ký

Thay vì để request gửi:

```json
{
  "jdbcUrl": "jdbc:...",
  "driver": "...",
  "properties": { "..." : "..." }
}
```

hãy cho phép nó gửi **một định danh logic**:

```json
{
  "databaseProfileId": "orders-read"
}
```

Ứng dụng **tự ánh xạ** `orders-read` tới một `DataSource` được khởi tạo từ cấu hình phía server đã được phê duyệt:

```text
Request chưa đáng tin
  databaseProfileId = "orders-read"
                 │
                 ▼
  Xác thực principal / tenant
                 │
                 ▼
  Kiểm tra quyền sử dụng profile
                 │
                 ▼
  Registry profile do server quản lý
    "orders-read" ──► DataSource A
    "orders-write" ─► DataSource B
                 │
                 ▼
  DataSource.getConnection()
                 │
                 ▼
  DB endpoint, TLS, secret, role đã được cấu hình cố định
```

Ưu điểm: người dùng **không thể tạo endpoint mới** chỉ bằng cách đổi chuỗi profile ID. Một profile không có trong registry hoặc principal không có quyền phải bị từ chối.

### Ví dụ Java: router kết nối theo allowlist và quyền truy cập

Ví dụ sau nhận các `DataSource` và danh sách cấp quyền từ **cấu hình phía server đã xác minh**. `authenticatedTenantId` phải đến từ security context đã xác thực, không lấy trực tiếp từ query parameter hoặc header chưa xác minh.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class AuthorizedDataSourceRouter {
    private final Map<String, DataSource> profiles;
    private final Map<String, Set<String>> permittedByTenant;

    public AuthorizedDataSourceRouter(
            Map<String, DataSource> trustedProfiles,
            Map<String, Set<String>> trustedPermissions) {

        Objects.requireNonNull(trustedProfiles, "profiles");
        Objects.requireNonNull(trustedPermissions, "permissions");

        // Sao chép để request không thay đổi registry bằng tham chiếu.
        this.profiles = Collections.unmodifiableMap(
                new HashMap<>(trustedProfiles));

        Map<String, Set<String>> permissionsCopy = new HashMap<>();
        for (Map.Entry<String, Set<String>> entry
                : trustedPermissions.entrySet()) {
            permissionsCopy.put(
                    entry.getKey(),
                    Collections.unmodifiableSet(
                            new HashSet<>(entry.getValue())));
        }
        this.permittedByTenant =
                Collections.unmodifiableMap(permissionsCopy);
    }

    public Connection openFor(
            String authenticatedTenantId,
            String requestedProfileId) throws SQLException {

        Objects.requireNonNull(
                authenticatedTenantId, "authenticatedTenantId");

        // requestedProfileId là giá trị do người dùng chọn.
        // Không parse nó như URL hay tên host.
        Set<String> allowed =
                permittedByTenant.get(authenticatedTenantId);

        if (requestedProfileId == null
                || allowed == null
                || !allowed.contains(requestedProfileId)) {
            // Không tiết lộ profile có tồn tại cho tenant khác hay không.
            throw new SecurityException(
                    "Database profile is not permitted");
        }

        DataSource selected = profiles.get(requestedProfileId);
        if (selected == null) {
            // Lỗi cấu hình server, không fallback sang JDBC URL người dùng.
            throw new IllegalStateException(
                    "Authorized database profile is not configured");
        }

        return selected.getConnection();
    }
}
```

Cách dùng trong DAO:

```java
// authenticatedTenantId đã được lấy từ hệ thống xác thực,
// KHÔNG phải từ một giá trị tenant ID tùy ý trong request.
try (Connection connection = router.openFor(
        authenticatedTenantId, requestedProfileId);
     PreparedStatement statement = connection.prepareStatement(
        "SELECT id, total FROM orders WHERE id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet result = statement.executeQuery()) {
        if (result.next()) {
            long id = result.getLong("id");
            // Ánh xạ kết quả theo hợp đồng nghiệp vụ.
        }
    }
}
```

Các import của đoạn DAO gồm `java.sql.Connection`, `PreparedStatement` và `ResultSet`. `router` phải được khởi tạo từ các profile hợp lệ và danh sách quyền đã được phía server kiểm soát.

**Hợp đồng bảo mật của router:**

- `requestedProfileId` **chỉ dùng tra cứu map**, không được ghép thành JDBC URL, tên class driver, database name hoặc câu SQL.
- Kiểm tra **ủy quyền tenant → profile**, không chỉ kiểm tra profile có tồn tại.
- `authenticatedTenantId` phải đến từ **principal đáng tin cậy** do cơ chế xác thực gán, không do người gọi tự chọn.
- Registry và bản đồ quyền được sao chép tại khởi tạo để tránh thay đổi từ bên ngoài. Nếu cần cập nhật động, phải có giao thức cập nhật có phân quyền, audit và đồng bộ.
- Đối tượng `DataSource` trong registry **được tin cậy là đã cấu hình đúng**. Router không thể tự sửa TLS, quyền DB hoặc endpoint sai của một profile được đăng ký nhầm.
- Không fallback sang một host mặc định ngoài dự kiến, cũng không thử một URL từ request nếu profile không được tìm thấy.

Ví dụ còn yêu cầu **phân quyền trong database** và query-level authorization. Kết nối đúng profile không tự chứng minh rằng principal được đọc mọi dòng trong bảng `orders`; có thể cần điều kiện tenant, row-level security hoặc kiểm soát truy cập ở tầng nghiệp vụ.

## 5. Chuẩn hóa cấu hình: tách điểm đến, secret và các thuộc tính cố định

Một cấu hình an toàn có thể phân thành:

```text
Trusted connection profile
  ├─ Profile ID: orders-read
  ├─ Driver/dialect: PostgreSQL (đã chọn lúc build/deploy)
  ├─ Host/port/database: do server quản lý
  ├─ TLS: yêu cầu xác minh chứng chỉ và danh tính server
  ├─ Username/password: lấy từ secret manager
  ├─ Pool limit/timeouts: theo chính sách vận hành
  └─ DB role: chỉ các quyền truy cập tối thiểu cần thiết
```

Nếu ứng dụng không cần chọn database động, hãy **cố định một `DataSource`** và truyền nó cho repository. Đó thường là phương án đơn giản và ít rủi ro nhất.

### Ví dụ dùng `DriverManager` với URL và thuộc tính được kiểm soát

Ví dụ dưới đây minh họa **một cấu hình PostgreSQL cụ thể**; không phải bộ mã đa driver. Cấu hình điểm đến và chính sách TLS do server kiểm soát, còn username/password được truyền từ hệ thống quản lý secret của ứng dụng.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Properties;

public final class TrustedPostgresConnection {
    // Được cấu hình/review phía server, không lấy từ request.
    private static final String TRUSTED_JDBC_URL =
            "jdbc:postgresql://db.example.internal:5432/orders";

    private TrustedPostgresConnection() {
    }

    public static Connection open(
            String secretManagedUser,
            String secretManagedPassword) throws SQLException {

        Objects.requireNonNull(secretManagedUser, "username");
        Objects.requireNonNull(secretManagedPassword, "password");

        Properties options = new Properties();
        options.setProperty("user", secretManagedUser);
        options.setProperty("password", secretManagedPassword);

        // Tên thuộc tính và giá trị theo PostgreSQL JDBC driver.
        // Yêu cầu cấu hình CA/trust và chứng chỉ tên host hợp lệ.
        options.setProperty("sslmode", "verify-full");

        return DriverManager.getConnection(
                TRUSTED_JDBC_URL, options);
    }
}
```

Trong môi trường ứng dụng có traffic thường xuyên, nên tạo **pooled `DataSource` tại startup** thay vì mở kết nối vật lý qua `DriverManager` trong mỗi request. Ví dụ dùng `DriverManager` để nêu rõ ranh giới tin cậy của URL và `Properties`.

**Tại sao ví dụ không nhận tham số `jdbcUrl` từ caller?** Vì chỉ server mới quyết định endpoint và chính sách driver. Mật khẩu có thể thay đổi qua secret manager, nhưng không được dùng để kết nối tới host tùy ý.

**Tại sao không thêm mọi `Properties` từ request vào `options`?** Vì nhiều driver có thuộc tính ảnh hưởng TLS, xác thực, socket, tìm host dự phòng, đọc file hoặc SQL khởi tạo. Những thuộc tính này là **cấu hình có quyền**, không phải tuỳ chọn hiển thị.

**Lưu ý:** `sslmode=verify-full` là **thuộc tính đặc thù PostgreSQL JDBC driver**. Nó chỉ có tác dụng khi đường dẫn chứng chỉ/CA và danh tính endpoint được cấu hình đúng, và không nên copy nguyên sang MySQL, Oracle hoặc SQL Server. Với mỗi driver khác cần chính sách TLS tương đương theo tài liệu phiên bản hiện tại.

## 6. Tại sao không được ghép URL bằng chuỗi do người dùng cung cấp?

Một cách xây dựng URL dễ sai:

```java
// MẪU SAI: host và extraOptions do người dùng điều khiển.
String jdbcUrl =
        "jdbc:postgresql://" + userHost + ":5432/orders?"
        + extraOptions;

Connection connection = DriverManager.getConnection(
        jdbcUrl, user, password);
```

Rủi ro không chỉ là ký tự lạ trong tên host. Các driver có thể có:

- Phân tách host và port khác nhau, hỗ trợ **nhiều host/failover**.
- Tham số URL dùng dấu `?`, `&`, `;`, dấu phân cách hoặc escape riêng.
- Giá trị đặc biệt của tên database/path, socket hoặc server name.
- Thuộc tính TLS, auth, endpoint fallback, tự khởi tạo SQL hay tiện ích riêng.
- Quy tắc ưu tiên khác nhau khi cùng thuộc tính xuất hiện **cả URL lẫn `Properties`**.

Không có một parser JDBC URL chuẩn cho tất cả driver. `java.net.URI` **không phải trình phân tích cú pháp phổ quát của JDBC URL**. Một biểu thức như:

```java
if (jdbcUrl.startsWith(
        "jdbc:postgresql://db.example.internal")) {
    // KHÔNG ĐỦ để chứng minh endpoint duy nhất là host được cho phép.
}
```

có thể bỏ sót ranh giới tên host, phần mở rộng URL hoặc cách driver diễn giải endpoint. Tương tự, tìm chuỗi `"ssl=true"` trong URL không chứng minh driver đang xác minh chứng chỉ và hostname.

**Cách phòng tránh tốt nhất:** không chấp nhận URL thô. Cho người dùng chọn **mã profile**; phía server tự xây dựng và duy trì `DataSource` hoặc JDBC URL cố định.

### Nếu thực sự cần nhiều endpoint khác nhau

Một hệ thống quản trị nhiều cơ sở dữ liệu hoặc dịch vụ kết nối đối tác có thể có nhu cầu bổ sung endpoint mới. Khi đó không nên chuyển yêu cầu đó thành quyền “mọi request được mở JDBC URL bất kỳ”. Thay vào đó:

1. Tạo một **quy trình đăng ký endpoint riêng** có xác thực mạnh, quyền quản trị và audit.
2. Chỉ hỗ trợ **danh sách driver/dialect đã duyệt**, không cho tải class driver tùy ý.
3. Thu thập những trường có kiểu cụ thể như logical ID, host, port, database, TLS profile; **không nhận nguyên URL và danh sách thuộc tính mở**.
4. Kiểm tra endpoint bằng chính sách mạng/DNS, giải quyết hostname và đối chiếu tất cả địa chỉ đích được phép; chú ý IPv4/IPv6, CNAME, multi-host, failover và DNS có thể thay đổi.
5. Thiết lập **egress network controls** để tầng ứng dụng chỉ mở được kết nối tới những mạng/endpoint được cho phép. Kiểm tra chuỗi ở Java không thay thế firewall/network policy.
6. Yêu cầu TLS và xác minh **danh tính server**, không chỉ “có mã hóa”.
7. Cấp secret và DB role **riêng cho endpoint/tenant** theo quyền tối thiểu; không tái sử dụng credential có quyền rộng trên những endpoint chưa được duyệt.
8. Giới hạn số profile, số pool, kích thước pool, timeout và ngân sách tài nguyên; định kỳ kiểm tra lại endpoint trước khi sử dụng.
9. Chỉ sau khi duyệt mới tạo `DataSource` và thêm nó vào registry phục vụ nghiệp vụ.

**Đặc biệt:** một hostname được duyệt tại thời điểm đăng ký vẫn có thể đổi địa chỉ DNS. Cần kiểm soát cả đường kết nối ở runtime. Chỉ kiểm tra “địa chỉ IP có thuộc dải nội bộ hay không” bằng một lần DNS lookup rồi yên tâm vĩnh viễn là chưa đủ.

## 7. Quy tắc allowlist cho thuộc tính kết nối

Các thuộc tính JDBC thường được truyền qua `Properties` hoặc API cấu hình của `DataSource`. **Không có một danh sách tên thuộc tính chung và đầy đủ cho mọi driver**. Ví dụ `sslmode` của PostgreSQL khác tên và giá trị cấu hình TLS của sản phẩm khác.

Một chính sách hữu ích là:

| Nhóm thuộc tính | Ai được điều khiển? | Lý do |
| --- | --- | --- |
| Driver và giao thức | Cấu hình đã phê duyệt tại build/deploy | Tránh mở rộng khả năng kết nối ngoài chủ đích |
| Host, port, database | Registry endpoint phía server | Không cho điều hướng tới DB hoặc mạng khác |
| Username/password/token | Secret manager hoặc hệ thống xác thực được ủy quyền | Tránh lộ credential, thực thi least privilege |
| TLS, trust store, hostname verification | Security/ops policy đáng tin cậy | Không cho request hạ cấp bảo vệ đường truyền |
| Kích thước pool, connect/socket/network timeout | Chính sách vận hành có giới hạn | Không cho người dùng giữ tài nguyên vô hạn |
| SQL session initialization, session role | Tầng hạ tầng/transaction manager | Tránh đổi quyền hoặc ngữ cảnh phiên tùy ý |
| Tuỳ chọn driver liên quan file, URL phụ, local data import, plugin | Mặc định không mở cho input người dùng | Có thể có tác động vượt ra ngoài việc gửi SQL thông thường |
| Ngôn ngữ/định dạng hiển thị dữ liệu | Chỉ qua tập giá trị đã xác minh, nếu thực sự cần | Không để thuộc tính driver trở thành kênh sửa security policy |

### Không merge mọi key từ JSON hay `Properties` vào driver

Một cách sai thường gặp:

```java
// MẪU SAI: truyền toàn bộ key/value của người dùng vào driver.
Properties properties = new Properties();

for (Map.Entry<String, String> entry
        : requestProperties.entrySet()) {
    properties.setProperty(entry.getKey(), entry.getValue());
}

DriverManager.getConnection(requestJdbcUrl, properties);
```

Ngay cả khi caller không kiểm soát JDBC URL, một thuộc tính driver có thể làm thay đổi endpoint fallback, TLS hoặc hành vi session. Vì vậy **không nên xem map tuỳ ý là vô hại**.

Nếu nghiệp vụ cần cho người dùng chọn một vài hành vi không nhạy cảm, hãy chuyển chúng qua **một mô hình đầu vào nhỏ có kiểu và miền giá trị rõ**. Ví dụ người dùng có thể chọn một mức timeout cho *truy vấn* từ tập giới hạn do service cho phép; tầng DAO áp dụng qua `Statement.setQueryTimeout()` sau khi xác minh ngân sách request, thay vì nhận một property tên tuỳ ý để đặt ở connection level.

**Default-deny:** key không biết hoặc giá trị không nằm trong miền cho phép phải bị từ chối, thay vì âm thầm chuyển qua driver.

## 8. Đừng dựa vào thứ tự ưu tiên URL-vs-Properties để ép an toàn

Một thiết kế tưởng như an toàn:

```java
Properties trusted = new Properties();
trusted.setProperty("sslmode", "verify-full");

// jdbcUrl vẫn có thể đến từ nguồn chưa tin cậy:
DriverManager.getConnection(jdbcUrl, trusted);
```

**Không nên mặc định `trusted` sẽ thắng mọi thuộc tính bị nhúng trong `jdbcUrl`.** Quy tắc xử lý URL, property trùng tên và mức ưu tiên là đặc thù của driver/phiên bản. Thậm chí có những thiết lập mà JDBC URL được phân tích thành đường kết nối khác trước khi driver áp các thuộc tính còn lại.

Hướng đúng là:

1. Chỉ dùng **URL đã được phê duyệt**, không chấp nhận raw URL từ request.
2. Thiết lập thuộc tính bảo mật bằng **API và cách cấu hình đã được tài liệu driver xác nhận**.
3. Không để cùng một property xuất hiện mâu thuẫn ở URL, nguồn config và object `Properties`.
4. Trong startup/integration test, **kiểm chứng kết nối thực sự đang dùng TLS và xác minh danh tính server** theo cách DB/driver hỗ trợ, không chỉ kiểm tra chuỗi cấu hình.
5. Nếu cấu hình sai hoặc không thể xác minh, **không khởi tạo pool và báo lỗi cấu hình**, thay vì tự hạ cấp xuống chế độ không an toàn.

## 9. Mật khẩu, token và URL: tránh rò rỉ thông tin

Mật khẩu hoặc token không nên nằm trong query parameter của URL được dùng để log, xuất metric hay hiển thị ở màn hình lỗi. Một URL có thể đi qua nhiều nơi:

```text
Application config
      │
      ├─ Startup logs
      ├─ Exception messages
      ├─ Distributed tracing attributes
      ├─ Monitoring dashboard
      ├─ Error report / support ticket
      └─ Connection pool diagnostics
```

Chỉ cần một nơi ghi nguyên chuỗi là secret có thể bị lưu trong thời gian dài.

### Nguyên tắc quản lý secret

- Lấy credential từ **secret manager** hoặc kênh cấu hình hạn chế quyền truy cập, không hardcode trong code và không commit vào repository.
- Dùng **tài khoản database riêng** theo ứng dụng/môi trường hoặc nhóm quyền, áp dụng *least privilege* và cấp quyền `SELECT`/`INSERT`/`UPDATE`/`DELETE` thật sự cần.
- Không dùng tài khoản DDL hoặc superuser để phục vụ request CRUD thông thường.
- Không gửi cùng credential tới những endpoint thuộc tenant/đối tác khác nhau nếu không có thiết kế và phê duyệt cụ thể.
- Giới hạn quyền xem secret trong CI/CD, log, dump và dashboard; có kế hoạch xoay vòng secret.
- Tránh in `Properties`, raw JDBC URL hay toàn bộ `DataSource.toString()` vì implementation có thể chứa thông tin nhạy cảm.
- Khi buộc phải ghi chẩn đoán, log **profile ID**, DB product/driver, stage và trace ID; tránh raw host khi không cần thiết và tuyệt đối không ghi username/password/token.

Trong Java, JDBC thường cần credential ở dạng `String` tại ranh giới driver nên không thể hứa “xóa toàn bộ bản sao mật khẩu khỏi bộ nhớ” chỉ bằng `char[]`. Giảm vòng đời và quyền truy cập tới secret vẫn hữu ích, nhưng phải hiểu giới hạn API và driver.

### Phân biệt lỗi kết nối với thông điệp công khai

Không trả nguyên `SQLException.getMessage()` về HTTP response. Driver có thể báo cả URL, host, database name hoặc chi tiết xác thực. Nên chuyển lỗi ở DAO/hạ tầng thành loại lỗi ổn định như `DATABASE_UNAVAILABLE` hoặc `DATABASE_ACCESS_DENIED`, còn chẩn đoán chi tiết nằm trong kênh log nội bộ được kiểm soát.

## 10. TLS: mã hóa đường truyền chưa đủ nếu không xác minh server

Một cấu hình “đã bật SSL/TLS” chưa chắc xác minh **máy chủ nào** đang ở đầu kia của kết nối. Hai yêu cầu cần phân biệt:

1. **Mã hóa và bảo vệ tính toàn vẹn đường truyền:** giảm nguy cơ nghe lén/chỉnh sửa lưu lượng.
2. **Xác minh chứng chỉ và danh tính endpoint:** ngăn kẻ không được phép giả mạo một database server bằng chứng chỉ hoặc tên không hợp lệ.

Ví dụ dùng PostgreSQL JDBC driver với `sslmode=verify-full` ở phần 5 minh họa chính sách xác minh danh tính; driver cần trust root/CA phù hợp và hostname thực tế khớp chứng chỉ. Nếu môi trường DB dùng chứng chỉ nội bộ, cần quản lý CA/trust store đúng cách, **không bỏ qua kiểm tra hostname để “kết nối cho được”**.

| Lỗi thiết kế | Hướng xử lý |
| --- | --- |
| Tắt TLS trong môi trường lẽ ra phải mã hóa | Fail closed, sửa cấu hình và chứng chỉ thay vì hạ cấp |
| Chỉ bật mã hóa mà không kiểm tra danh tính server | Bật hostname verification và trust chain theo driver |
| Cho request đổi thuộc tính TLS | Không chấp nhận; TLS policy do server/security quản lý |
| Dùng một trust store tuỳ ý do request chỉ định | Chỉ dùng trust material đã được phê duyệt |
| Không kiểm tra failover/replica | Mỗi endpoint thực tế phải đáp ứng chính sách định danh |
| Dùng môi trường test bỏ TLS rồi sao chép config sang production | Kiểm thử riêng cấu hình production và bảo vệ startup |

Không có một property TLS thống nhất cho tất cả JDBC driver. Trong tài liệu triển khai nên ghi rõ **driver, phiên bản, property, trust configuration và cách xác minh trong integration test**.

## 11. Tài khoản đúng không thay thế kiểm soát phạm vi dữ liệu

Giả sử nhiều tenant dùng chung một database. Dù router ở phần 4 chỉ cấp đúng `DataSource`, DAO vẫn có thể truy vấn sai phạm vi nếu không kiểm tra quyền dữ liệu:

```java
// Không đủ khi bảng chứa nhiều tenant:
String sql = "SELECT id, total FROM orders WHERE id = ?";
```

Nếu chính sách ứng dụng dựa trên cột tenant, câu SQL cần dùng **tenant ID đã xác thực** (hoặc database row-level security được thiết kế và kiểm thử):

```java
String sql =
        "SELECT id, total FROM orders " +
        "WHERE id = ? AND tenant_id = ?";

try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

    statement.setLong(1, orderId);
    statement.setLong(2, authenticatedTenantId);

    try (ResultSet result = statement.executeQuery()) {
        // Chỉ xử lý hàng thuộc tenant đã được xác thực.
    }
}
```

Trong ví dụ thứ hai, `authenticatedTenantId` là `long` do security context cung cấp, **không phải tham số do client tự khai**. Nếu hệ thống dùng chuỗi UUID hoặc đối tượng khác, dùng setter phù hợp.

**Chọn kết nối đúng và chọn dữ liệu đúng là hai kiểm tra riêng.** Tương tự, tài khoản `read-only` phải được DB thực sự hạn chế quyền ghi; `Connection.setReadOnly(true)` là API/hint cho kết nối, **không thay thế phân quyền `GRANT`/`REVOKE`** của database.

### Role/schema/session state

Một số ứng dụng dùng role hoặc schema theo tenant. Điều này thêm rủi ro nếu một kết nối được pool tái sử dụng mà session state chưa được reset. Hãy thiết kế transaction và cleanup rõ ràng, tránh để một request thay đổi schema/role bằng input tùy ý rồi trả kết nối về pool với trạng thái không xác định. Đối với isolation theo tenant, **connection pool configuration và role của DB cũng phải hỗ trợ đúng mô hình**.

## 12. Kích thước pool và timeout là một phần của chính sách bảo mật

Một input có thể không thay host nhưng vẫn gây sự cố nếu được phép quyết định:

- `maximumPoolSize` rất lớn, mở hàng trăm phiên DB ngoài ngân sách.
- Connect/borrow/socket timeout quá dài, giữ request và thread chờ vô thời hạn.
- Validation/keepalive không phù hợp, gây liên tục mở lại kết nối.
- Số lượng `DataSource` mới không bị giới hạn theo tenant hoặc request.
- Cấu hình khởi tạo SQL hoặc session role chạy với quyền vượt nhu cầu.

Hệ thống nên giới hạn **số profile, số pool, tổng connection và tốc độ tạo kết nối**, đặt timeout hợp lý và bảo đảm cleanup bằng `try-with-resources`. Không tạo pool mới cho mỗi request chỉ vì user đổi `databaseProfileId`.

Các chỉ số vận hành hữu ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Pool active/idle/pending | Phát hiện giữ kết nối lâu hoặc đang cạn pool |
| Acquisition timeout count | Chỉ ra request chờ mượn quá lâu |
| Physical connection creation failures | Phát hiện endpoint/credential/TLS/DB không hoạt động |
| Login/TLS handshake failure | Cảnh báo lỗi chứng chỉ, hostname, xác thực |
| Connection attempts by approved profile | So sánh hành vi với registry đã phê duyệt |
| Unexpected destination / denied egress | Dấu hiệu cấu hình hoặc request cố vượt allowlist |
| Authorization denials by profile | Phát hiện chọn profile sai quyền, không gắn nhãn chứa secret |

Metric nên dùng **profile ID có cardinality được kiểm soát**, không dùng raw URL hoặc host từ người dùng làm nhãn. Một attacker có thể tạo vô số chuỗi làm metric quá tải và vô tình đưa thông tin nhạy cảm vào hệ thống quan sát.

## 13. Khi nào cần kiểm tra URL thực sự?

Trong kiến trúc ưu tiên **registry profile phía server**, ứng dụng có thể không cần parse URL từ request. Nhưng ở tầng cấu hình hạ tầng, việc kiểm tra **tính đúng** của JDBC URL vẫn quan trọng.

Tại startup hoặc thời điểm phê duyệt profile:

1. Xác nhận **driver/dialect được phép** và URL đúng cú pháp do driver đó hỗ trợ.
2. Kiểm tra tập endpoint được phê duyệt, bao gồm multi-host, failover, redirect hoặc cơ chế phân giải host nếu driver có hỗ trợ.
3. Kiểm tra host/port/database, schema, authentication mode, TLS và file tham chiếu thực tế.
4. Kiểm tra những thuộc tính có thể làm thay đổi endpoint hoặc chế độ bảo mật; từ chối key không được phê duyệt.
5. Đảm bảo DB role đúng quyền; chạy thử `SELECT`/`UPDATE` trong phạm vi thử nghiệm an toàn nếu cần để xác minh grant.
6. Kiểm thử tình huống chứng chỉ sai/hostname không khớp và đảm bảo kết nối **thất bại**, không tự fallback.
7. Đối chiếu network egress policy tại runtime, không chỉ chuỗi URL.
8. Lưu một bản ghi audit về thay đổi profile và phiên bản cấu hình, **không lưu secret nguyên văn**.

**Không dùng một hàm `startsWith("jdbc:...")` làm validator bảo mật.** Nếu bắt buộc phải parse một URL nhập từ kênh quản trị, phải sử dụng **quy tắc parser/validator gắn với driver cụ thể**, sau đó đối chiếu endpoint thực sự được kết nối. Đặc biệt tránh tự suy từ ký tự sau `//` bằng `java.net.URI` khi driver có quy tắc không theo URI tiêu chuẩn.

Kiểm soát URL vẫn chỉ là **một lớp phòng vệ**. Nếu máy ứng dụng có quyền mở socket tới bất kỳ nơi nào và credential quá rộng, tác động của cấu hình sai sẽ lớn hơn rất nhiều. Phòng thủ mạng và quyền DB tối thiểu là lớp bảo vệ quan trọng.

## 14. Những mẫu mã dễ sai và cách thay thế

### Sai 1: lấy JDBC URL từ request để truy cập dữ liệu được chỉ định

```java
// Sai: request cung cấp quyền định nghĩa endpoint.
Connection connection =
        DriverManager.getConnection(requestUrl, user, password);
```

**Thay:** `router.openFor(authenticatedTenantId, requestedProfileId)` với registry và phân quyền đã phê duyệt.

### Sai 2: cho người dùng gửi mọi connection property

```java
// Sai: requestProps có thể chứa thuộc tính bảo mật của driver.
Properties options = new Properties();
options.putAll(requestProps);
```

**Thay:** tạo bộ properties ở tầng hạ tầng từ danh sách key và giá trị **đã được kiểm chứng**. Nếu cần expose một sở thích nghiệp vụ, dùng trường đầu vào có kiểu và giá trị giới hạn; không map trực tiếp thành key/value của driver.

### Sai 3: chỉ kiểm tra prefix JDBC URL

```java
// Sai: prefix không bảo đảm host, port, failover hay security mode.
if (requestUrl.startsWith("jdbc:postgresql://db.example.internal")) {
    DriverManager.getConnection(requestUrl);
}
```

**Thay:** dùng **endpoint do server định nghĩa cố định** hoặc một registry endpoint có quy trình approval và kiểm soát mạng.

### Sai 4: log nguyên cấu hình để debug

```java
// Sai: có thể lộ username/password/token hoặc endpoint nội bộ.
logger.info("JDBC config: " + jdbcUrl + " " + properties);
```

**Thay:** log mã profile đã phê duyệt, tên driver, stage và mã lỗi được phân loại, không log raw URL và object chứa secret.

### Sai 5: tin rằng TLS “đang bật” là đủ

Không dùng kiểm tra “có property chứa từ `ssl`” làm bằng chứng bảo vệ. Phải xác minh chứng chỉ, danh tính endpoint và chính sách không fallback trong thử nghiệm tích hợp.

### Sai 6: bỏ qua quyền tenant vì JDBC profile hợp lệ

`databaseProfileId` hợp lệ không có nghĩa mọi principal đều được dùng. Router phải kiểm tra cấp quyền, và DAO/DB vẫn phải đảm bảo ranh giới dữ liệu bên trong.

## 15. Kiểm thử cấu hình JDBC như một bề mặt bảo mật

Kiểm thử ở **hai lớp**: kiểm tra logic phân quyền/registry bằng unit test, và kiểm tra driver/TLS/điểm đến bằng integration test trong môi trường được kiểm soát. Không thử các endpoint không thuộc quyền quản lý của hệ thống.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Profile hợp lệ và tenant có quyền | Router dùng đúng `DataSource` đã đăng ký |
| Profile hợp lệ nhưng tenant không có quyền | Từ chối **trước khi gọi `getConnection()`** |
| Profile ID lạ hoặc `null` | Từ chối, không fallback sang URL khác |
| Tenant ID từ request không có chứng thực | Không dùng như identity; chỉ chấp nhận principal đã xác thực |
| Người dùng gửi thêm trường `jdbcUrl` hoặc `properties` | API không có chức năng truyền thẳng chúng vào driver |
| URL/driver config có tham số ngoài allowlist | Startup/approval fail closed |
| TLS certificate hết hạn hoặc hostname không khớp | Kết nối thất bại; không hạ cấp TLS |
| Endpoint bị đổi DNS sang địa chỉ ngoài phạm vi | Chính sách mạng/runtime từ chối kết nối |
| Database profile chỉ đọc nhận lệnh ghi | DB role/permission chặn thao tác; không chỉ dựa vào `setReadOnly(true)` |
| Tạo nhiều profile/pool bất thường | Rate limit/quota hạn chế số connection và tài nguyên |
| SQLException chứa URL hoặc thông tin server | API response và metric không làm lộ raw URL/secret |
| Connection dùng lại sau thay schema/role | Session state được khôi phục/loại bỏ an toàn theo pool |

### Ví dụ unit test cho router, không cần database thật

Với `AuthorizedDataSourceRouter`, có thể dùng mock `DataSource` để ghi nhận một lần gọi. Các ca kiểm tra quan trọng:

```java
// Pseudocode kiểm thử: source chỉ được gọi sau khi kiểm tra quyền.
Map<String, DataSource> profiles = new HashMap<>();
profiles.put("orders-read", mockedReadSource);

Map<String, Set<String>> permissions = new HashMap<>();
permissions.put(
        "tenant-a",
        Collections.singleton("orders-read"));

AuthorizedDataSourceRouter router =
        new AuthorizedDataSourceRouter(profiles, permissions);

// Được phép:
Connection allowed = router.openFor("tenant-a", "orders-read");
allowed.close();

// Phải từ chối, tuyệt đối không gọi đến DataSource:
try {
    router.openFor("tenant-b", "orders-read");
    throw new AssertionError("Unauthorized request was accepted");
} catch (SecurityException expected) {
    // Test pass.
}
```

Đoạn này dùng một `DataSource` giả (`mockedReadSource`), nên chưa thể copy chạy độc lập nếu chưa khởi tạo mock và import lớp Java cần thiết. Unit test xác nhận **authorization trước khi checkout connection**; integration test mới xác nhận TLS, DB role, driver parsing và cách pool xử lý trạng thái phiên.

### Kiểm thử tích hợp bắt buộc cho cấu hình bảo mật

Nếu dùng PostgreSQL với TLS hostname verification hoặc một driver khác có chế độ tương đương, nên có các bài thử:

1. Kết nối tới endpoint hợp lệ với cert/CA đúng → thành công.
2. Cert không khớp hostname hoặc trust root không hợp lệ → thất bại; không fallback sang kết nối thiếu kiểm chứng.
3. Thử kết nối qua profile tới endpoint bị network policy cấm → kết nối bị chặn.
4. Thử đăng nhập với role `read-only` và chạy thao tác ghi trong DB thử nghiệm → DB từ chối.
5. Thay đổi cấu hình profile và secret trong một quy trình deployment thử → audit và rotation hoạt động, không lộ secret trong log.
6. Cố gửi các tên property không được phép qua cấu hình nhập từ người dùng → bị từ chối trước khi tạo `DataSource`.

Không nên coi **metadata từ driver** hoặc flag `supports...()` là bằng chứng tuyệt đối về bảo mật. Phải quan sát kết quả kết nối thật và các chính sách phía database.

## 16. Checklist thiết kế an toàn

- **Không nhận JDBC URL, tên driver hoặc `Properties` thô từ request** để tạo kết nối có credential của ứng dụng.
- **Cho chọn profile ID**, tra trong registry server-side và kiểm tra quyền theo principal/tenant đã xác thực.
- **Cố định hoặc phê duyệt endpoint**, gồm cả cơ chế multi-host/failover, DNS và egress network policy.
- **Áp dụng TLS có xác minh danh tính server**, không cho request thay đổi hoặc tắt bảo vệ.
- **Lấy secret qua kênh được bảo vệ** và dùng tài khoản DB tối thiểu quyền; không hardcode hoặc log secret.
- **Không merge property tùy ý** vào cấu hình driver; dùng allowlist key/value và fail closed.
- **Không dùng parser chuỗi đơn giản** để chứng minh URL an toàn; kiểm thử theo driver thực tế.
- **Giới hạn pool và timeout**, không tạo `DataSource` không giới hạn từ dữ liệu người dùng.
- **Phân quyền dữ liệu ở DAO/DB**, không chỉ phân quyền lựa chọn kết nối.
- **Đóng tài nguyên bằng `try-with-resources`** và xử lý transaction/connection state khi tái sử dụng pool.
- **Kiểm thử deny cases, TLS, role và log redaction** cùng với kiểm thử thành công thông thường.
- **Lưu lịch sử thay đổi profile** và giám sát destination/connection failures theo profile ID, không theo URL thô.

### Bài thực hành

1. Xây dựng một registry gồm hai profile `orders-read` và `orders-write`, mỗi profile ánh xạ tới một `DataSource` được cấu hình từ nguồn tin cậy.
2. Thêm kiểm tra `tenant → profile` ở `AuthorizedDataSourceRouter`. Viết unit test chứng minh một tenant không được phép không thể gọi `getConnection()` của profile khác.
3. Thay endpoint nhập trực tiếp trong API bằng `databaseProfileId`. Thử truyền thêm `jdbcUrl` và `properties` trong JSON; xác nhận chúng bị bỏ qua theo schema hoặc request bị từ chối, **không được chuyển vào driver**.
4. Cấu hình TLS xác minh danh tính trên DB thử nghiệm. Thử chứng chỉ/hostname sai và xác nhận driver không fallback.
5. Dùng một tài khoản DB read-only thật, không chỉ `Connection.setReadOnly(true)`; thử `INSERT` và quan sát lỗi phân quyền.
6. Thử tải đồng thời nhiều request cùng chọn một profile; kiểm tra pool không được tạo mới theo từng request và không vượt quota.
7. Kiểm tra log, tracing và error response khi driver ném `SQLException`: không có mật khẩu, token, URL thô hoặc thông tin schema nhạy cảm.
8. Viết một báo cáo ngắn xác định rõ **nguồn tin cậy**, **tập thuộc tính được phép**, **cơ chế TLS**, **quy tắc cấp quyền**, **network policy** và **các kiểm thử đã chạy**.

## 17. Tổng kết

1. **JDBC URL và connection properties là cấu hình nhạy cảm về bảo mật**, không phải dữ liệu vô hại. Một giá trị chưa đáng tin cậy có thể đổi điểm đến, xác thực, TLS hoặc hành vi của driver.
2. **Ranh giới an toàn nhất là registry profile phía server.** Client chỉ chọn định danh logic đã cấp quyền, còn endpoint, driver, secret và property do hệ thống quản trị.
3. **Chỉ dùng `PreparedStatement` không đủ:** nó bảo vệ giá trị SQL, không bảo vệ bước tạo `Connection` hay lựa chọn database.
4. **Không cho phép property pass-through hoặc URL string validation hời hợt.** Quy tắc URL và tên thuộc tính có thể khác giữa driver; phải dùng allowlist và kiểm thử trên phiên bản triển khai.
5. **TLS cần xác minh danh tính server; secret cần least privilege.** Hai lớp này bổ sung cho allowlist điểm đến và giới hạn egress mạng.
6. **Bảo vệ cả tính sẵn sàng và phân quyền dữ liệu:** giới hạn số pool/connection, timeout, quyền tenant/profile và quyền đọc/ghi của DB role.
7. **Kiểm thử đường bị từ chối quan trọng như đường thành công.** Nếu endpoint sai, profile không có quyền hoặc TLS không hợp lệ, kết nối phải thất bại có kiểm soát, không fallback sang chế độ yếu hơn.

**Kết luận:** trong một ứng dụng JDBC an toàn, nguồn không tin cậy có thể yêu cầu **thao tác nghiệp vụ** và lựa chọn **profile đã được phê duyệt**, nhưng không được điều khiển trực tiếp JDBC URL, driver, credential và connection properties. Đặt ranh giới này ở tầng cấu hình/`DataSource`, kết hợp kiểm tra quyền, mạng, TLS và phân quyền database, giúp giảm nguy cơ kết nối sai nơi, lộ secret, hạ cấp bảo vệ và lạm dụng tài nguyên.
