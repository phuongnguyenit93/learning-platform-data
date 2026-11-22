# Quản lý thông tin kết nối và bí mật ngoài mã nguồn

Một ứng dụng Java cần biết **nơi kết nối tới cơ sở dữ liệu**, **danh tính được phép truy cập** và **cách chứng minh danh tính đó**. Việc viết sẵn JDBC URL, username và password trực tiếp trong mã nguồn có vẻ thuận tiện, nhưng biến mỗi bản sao repository, bản build, log lỗi và ảnh chụp cấu hình thành một nơi có nguy cơ làm lộ quyền truy cập dữ liệu. Khi một password cần thay đổi, đội ngũ còn phải sửa code, build và deploy chỉ vì thông tin xác thực đã được gắn cứng vào ứng dụng.

Giải pháp là **tách cấu hình kết nối khỏi mã nguồn, lưu bí mật trong hệ thống hoặc vùng lưu trữ chuyên dụng, cấp quyền tối thiểu và quản lý vòng đời bí mật từ lúc tạo đến lúc thu hồi**. Mục tiêu không chỉ là “không có password trong Git”, mà còn là hạn chế ai được đọc, secret tồn tại ở đâu trong runtime, nó có bị ghi vào log không, làm sao xoay vòng và ứng dụng sẽ xử lý khi nguồn bí mật không khả dụng.

Trong chương **An toàn dữ liệu** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài học này gắn an toàn cấu hình với ranh giới persistence Java, connection pool, giao dịch, vận hành nhiều môi trường và khả năng phục hồi. Ta tập trung vào JDBC/Spring Boot, cơ chế cấp bí mật theo workload, bảo vệ kênh TLS, nguyên tắc đặc quyền tối thiểu và quy trình rotation không gây lỗi hàng loạt.

## 1. Phân loại: cấu hình, bí mật và danh tính

Không phải mọi tham số JDBC đều là bí mật, nhưng **mọi tham số đều có thể tác động đến an toàn**.

| Nhóm | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Cấu hình kết nối** | Host, port, database name, pool size, timeout | Đưa ra cấu hình môi trường; xác thực nguồn cấu hình và kiểm soát thay đổi |
| **Danh tính truy cập** | Database username, tên service account | Cấu hình hoặc danh tính do nền tảng cấp; giới hạn quyền tương ứng |
| **Bí mật xác thực** | Password, access token, private key, client certificate key, secret dùng để ký | Lưu ngoài mã nguồn; cấp theo quyền, tránh log và hỗ trợ rotation |
| **Vật liệu tin cậy TLS** | CA certificate, truststore | Thường không bí mật nếu là public CA, nhưng **tính toàn vẹn rất quan trọng** |
| **Thông tin nhạy cảm trong URL** | Query string chứa password/token, tên hệ thống nội bộ | Không nhúng credential vào URL; hạn chế log nguyên văn URL |
| **Bí mật vận hành** | Tài khoản migration, backup, replication, quản trị DB | Tách khỏi tài khoản ứng dụng; cấp quyền đúng nhiệm vụ, quản lý nghiêm ngặt |

Một cấu hình sai nhưng không chứa password vẫn nguy hiểm. Ví dụ trỏ ứng dụng production tới DB staging có thể làm lộ dữ liệu hoặc ghi nhầm; dùng `sslmode=disable` có thể vô hiệu hóa bảo vệ kết nối; cấu hình pool quá lớn có thể làm cạn session DB. Vì vậy cần **xác minh cả nguồn và giá trị cấu hình**, không chỉ che password.

### Anti-pattern: thông tin kết nối viết thẳng trong Java

```java
// KHÔNG dùng kiểu này trong ứng dụng thật:
String jdbcUrl = "jdbc:postgresql://db.example.internal:5432/orders";
String username = "orders_admin";
String password = "example-hardcoded-password";

Connection connection =
        DriverManager.getConnection(jdbcUrl, username, password);
```

Chuỗi trên chỉ là **giá trị minh họa không phải thông tin xác thực thật**. Vấn đề gồm: password xuất hiện trong Git và bytecode; một nhánh hoặc artifact cũ vẫn giữ nó; cùng credential có thể bị dùng ở nhiều môi trường; tài khoản `orders_admin` còn vi phạm nguyên tắc cấp quyền tối thiểu.

Chỉ chuyển thành:

```java
String password = System.getenv("DB_PASSWORD");
```

là **một cải thiện so với hardcode**, nhưng **chưa phải giải pháp hoàn chỉnh**. Environment variable vẫn có thể bị lộ qua công cụ quan sát process, crash report, child process, cấu hình deployment, CI/CD log hoặc người có quyền phù hợp trên host. Hãy lựa chọn cơ chế cấp secret phù hợp với nền tảng và mô hình đe dọa.

## 2. Mô hình đe dọa: bí mật có thể lộ ở đâu?

Một password đi qua nhiều ranh giới trước khi JDBC driver dùng nó:

```text
Người/quy trình có thẩm quyền tạo secret
                  |
                  v
         Secret manager / vault
                  |
          IAM / workload identity
                  |
                  v
        Runtime ứng dụng Java
                  |
       +----------+-----------+
       |                      |
  Secret mount/file      Bộ nhớ JVM
       |                      |
       +------> Pool/Driver <-+
                    |
                    v
          Kết nối TLS tới DB

Rủi ro dọc đường: Git, CI log, biến môi trường,
file permission, trace, exception, heap dump,
debug endpoint, backup, thông tin truy cập nội bộ.
```

| Bề mặt rò rỉ | Tình huống thường gặp | Biện pháp |
| --- | --- | --- |
| Repository và lịch sử commit | `application-prod.yml` chứa password; file bị xóa ở commit sau nhưng vẫn còn trong history | Không commit ngay từ đầu; secret scanning, pre-commit/CI và quy trình thu hồi khi lộ |
| Artifact và image | Build nhúng credential vào resource/class, Docker `ARG/ENV` hoặc layer | Không bake bí mật vào JAR/image; cấp khi runtime |
| CI/CD | Command in biến, log command, task output, artifact cấu hình | Secret masking chỉ là lớp phụ; tránh echo/print, giảm quyền runner và phân tách deploy role |
| File secret trên máy/container | File có quyền quá rộng, được copy vào log/backup | Mount read-only, hạn chế quyền file/UID, phân quyền host, xác định vòng đời |
| Environment variable | Bị kế thừa vào child process hoặc xuất hiện trong diagnostic | Giới hạn quyền process, không in toàn bộ env; ưu tiên file/secret API khi có thể |
| Log, metric, exception | Ghi nguyên JDBC URL, `Properties`, cấu hình pool, HTTP headers | Chỉ log tên logical database/host an toàn và mã lỗi; redact và hạn chế quyền xem |
| Heap dump, thread/debug endpoint | Secret là `String` tồn tại trong bộ nhớ JVM | Hạn chế dump/debug, bảo vệ nơi lưu và thời hạn retention; dùng cơ chế xóa khi có thể |
| Kết nối mạng | JDBC kết nối không TLS hoặc không kiểm tra hostname | TLS với xác minh chứng chỉ/hostname, trust anchor phù hợp |

**Không có một kỹ thuật duy nhất làm secret “biến mất khỏi bộ nhớ”.** Phần lớn JDBC driver và connection pool cuối cùng cần nhận credential, thường dưới dạng `String` hoặc `Properties`; chuỗi Java là immutable nên không thể đảm bảo xóa nội dung đã lưu trong heap ngay lập tức. Do đó giới hạn quyền truy cập runtime và hạn chế leak qua diagnostic cũng quan trọng như lưu secret ở đâu.

## 3. Ba chiến lược cấp bí mật khi chạy ứng dụng

| Chiến lược | Cách dùng | Điểm mạnh | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| **Biến môi trường** | Nền tảng inject `DB_PASSWORD` vào process | Đơn giản, nhiều framework hỗ trợ | Dễ bị lộ qua công cụ/diagnostic/process environment; thay đổi thường cần khởi động lại |
| **Tệp bí mật được mount** | Runtime cấp file chỉ đọc từ Secret/volume | Không cần đặt trực tiếp password vào app config/environment; có thể thay nội dung theo nền tảng | Vẫn là plaintext trong phạm vi container; phải quản lý quyền, symlink/rotation, định dạng, thời điểm đọc lại |
| **Secret manager qua API** | Ứng dụng dùng workload identity để fetch secret lúc startup/refresh | IAM, audit, versioning, rotation, truy cập theo danh tính workload | Thêm phụ thuộc mạng/API, cần chính sách cache, TTL, retry và quyền truy cập bootstrap |

Một hệ thống tốt thường kết hợp **secret manager làm nguồn sự thật** với **cơ chế cấp secret phù hợp tại runtime**. Chẳng hạn, nền tảng đồng bộ một secret version đã được phê duyệt vào volume container, hoặc ứng dụng gọi secret manager bằng danh tính được nền tảng cấp.

### Giải quyết bài toán “cần secret để lấy secret”

Nếu ứng dụng cần một password hardcode để đăng nhập vào secret manager, ta chỉ **chuyển chỗ của vấn đề**. Ưu tiên danh tính workload có thể xác minh qua hạ tầng:

- Managed identity/instance identity/service account phù hợp nền tảng.
- Token có thời hạn hoặc cơ chế trao đổi danh tính được cấp qua metadata/identity service.
- Chính sách IAM chỉ cho workload cụ thể đọc **đúng secret path/version được cho phép**.
- Audit cho việc truy xuất secret và cảnh báo truy xuất bất thường.

Quyền truy cập secret manager **không đồng nghĩa** quyền tùy ý vào database. Nên phân tách: một role được phép lấy secret dành cho workload; một database role chỉ có quyền SQL cần thiết. Phía ứng dụng không cần sở hữu quyền quản trị vault hoặc quyền sửa secret.

### Khi không lấy được secret phải làm gì?

Ở **startup**, nếu thiếu secret quan trọng, ứng dụng nên **fail closed**: dừng khởi tạo persistence hoặc đánh dấu chưa sẵn sàng, ghi lỗi *không chứa giá trị secret*, thay vì âm thầm dùng password phát triển hoặc fallback sang DB khác.

Ở **runtime**, nếu secret manager tạm thời lỗi nhưng connection hiện có còn hoạt động, có thể duy trì chúng theo chính sách an toàn, retry lấy phiên bản mới có giới hạn và báo tình trạng sức khỏe. Không nên gọi secret manager cho **mỗi câu SQL**; làm vậy biến secret service thành dependency trên đường nóng, tăng latency và rủi ro gián đoạn. Cần cache/refresh có kiểm soát và tránh giữ connection DB trong lúc chờ mạng tới secret manager.

## 4. Cấu hình Java/JDBC: tách đường dẫn secret khỏi giá trị

Ví dụ dùng PostgreSQL, Java 17+ và một connection pool HikariCP. Ứng dụng nhận ba thông tin **qua cấu hình được cấp khi deploy**:

```text
DB_JDBC_URL=jdbc:postgresql://db.internal.example:5432/orders?sslmode=verify-full
DB_USERNAME=orders_app
DB_PASSWORD_FILE=/var/run/secrets/orders-db/password
```

Đây là các **giá trị minh họa**, không phải lệnh chạy với hệ thống thật. Password **không** xuất hiện trong ba dòng trên: chỉ có đường dẫn tới tệp được mount bằng nền tảng deploy. Tệp secret chứa **đúng một dòng mật khẩu, không có ký tự xuống dòng ở cuối**, theo hợp đồng cấu hình của ví dụ. Nếu secret thực tế có thể chứa newline, phải định nghĩa định dạng khác; không tự gọi `trim()` hoặc `strip()` vì có thể âm thầm đổi password hợp lệ.

### Ví dụ Java/HikariCP đọc mật khẩu từ secret file

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SecureDataSourceFactory {
    private SecureDataSourceFactory() {}

    public static HikariDataSource create() throws IOException {
        String jdbcUrl = requiredEnv("DB_JDBC_URL");
        String username = requiredEnv("DB_USERNAME");
        Path passwordPath = Path.of(requiredEnv("DB_PASSWORD_FILE"));

        // Chỉ chấp nhận file secret có kích thước hợp lý.
        // Chỉ là kiểm tra input, KHÔNG thay thế file permissions.
        long size = Files.size(passwordPath);
        if (size < 1 || size > 4096) {
            throw new IllegalStateException(
                    "Secret file không tồn tại hoặc kích thước không hợp lệ");
        }

        String password = Files.readString(
                passwordPath, StandardCharsets.UTF_8);
        // Contract trong ví dụ: mật khẩu đúng một dòng, không newline.
        if (password.isEmpty() ||
                password.indexOf('\n') >= 0 ||
                password.indexOf('\r') >= 0) {
            throw new IllegalStateException(
                    "Định dạng secret file không hợp lệ");
        }

        HikariConfig config = new HikariConfig();
        config.setPoolName("orders-db-pool");
        config.setJdbcUrl(jdbcUrl);
        config.setUsername(username);
        config.setPassword(password);
        config.setMaximumPoolSize(12);
        config.setConnectionTimeout(5_000);

        // Nền tảng triển khai phải xác thực URL/host/TLS policy.
        // Không log jdbcUrl hoặc password ở mức DEBUG.
        return new HikariDataSource(config);
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            // Chỉ in TÊN biến thiếu, không in nội dung cấu hình.
            throw new IllegalStateException("Thiếu cấu hình: " + key);
        }
        return value;
    }
}
```

Ví dụ sử dụng trong vòng đời do ứng dụng sở hữu:

```java
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

try (HikariDataSource dataSource = SecureDataSourceFactory.create()) {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(
                 "SELECT count(*) FROM orders")) {
        try (ResultSet rows = ps.executeQuery()) {
            if (rows.next()) {
                System.out.println("Số đơn: " + rows.getLong(1));
            }
        }
    }
}
```

Ở ứng dụng web, `HikariDataSource` thường sống suốt vòng đời process và được Spring/container đóng lúc shutdown; **không** tạo/đóng pool sau mỗi request. Mỗi request hoặc transaction chỉ mượn `Connection` từ pool rồi trả đúng lúc. Tên biến môi trường/đường dẫn secret là ví dụ; hệ thống phải kiểm soát quyền và tính toàn vẹn của giá trị được inject. Đoạn code trên không tự bảo đảm URL chỉ trỏ tới host đã phê duyệt.

**Giới hạn của ví dụ:** `Files.size()` rồi `Files.readString()` không phải phép đọc nguyên tử với việc thay thế file; trong môi trường rotation, nền tảng phải cung cấp cập nhật secret nhất quán, và ứng dụng cần chiến lược reload/đổi pool. Mật khẩu vẫn tồn tại dưới dạng `String` vì API JDBC/pool yêu cầu; không nên in `HikariConfig` hay snapshot toàn bộ biến cấu hình. Nếu muốn xác thực file permission, owner, mount path hoặc chống thay thế symlink, thực hiện theo đặc tính OS/orchestrator đang dùng, không giả định `Files.isReadable()` đã đủ bảo mật.

## 5. Spring Boot: externalized configuration và config tree

Spring Boot hỗ trợ cấu hình từ nhiều nguồn bên ngoài mã, gồm property/environment và *config tree* lấy giá trị từ tên tệp. Có thể giữ trong mã nguồn **chỉ các tham chiếu đến secret**, không chứa mật khẩu.

Ví dụ `application.properties`:

```properties
# Thư mục /run/secrets/ có file tên db.password.
# Không dùng optional: ở đây vì startup phải thất bại nếu thiếu file.
spring.config.import=configtree:/run/secrets/

# URL và username không phải password, nhưng vẫn do deployment quản lý.
spring.datasource.url=${DB_JDBC_URL}
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${db.password}

spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.connection-timeout=5000
```

Hợp đồng triển khai: một file được mount tại `/run/secrets/db.password`; Spring import property có tên `db.password` rồi bind vào `spring.datasource.password`. Đặt quyền truy cập file chỉ cho workload phù hợp và mount read-only. Tùy phiên bản/framework, thứ tự nguồn cấu hình và việc refresh giá trị có quy tắc riêng; kiểm tra cách framework thực sự nạp và khi nào cần restart/recreate pool.

**Không để mật khẩu thật trong `application.properties`, `application.yml` hoặc profile `application-prod.yml` được commit.** Giá trị tham chiếu `${db.password}` là cấu hình, không phải bí mật. Tuy nhiên, truy xuất endpoint cấu hình/Actuator có thể làm lộ giá trị đã resolve nếu bảo vệ kém; phải khóa quyền truy cập, áp dụng masking và không công khai `/env`, `/configprops`, diagnostic.

Nếu ứng dụng đã có secret integration chuyên biệt với cloud vault, có thể dùng property source/integration tương ứng; không cần copy bí mật vào tệp thủ công trong startup script. Điều quan trọng là **cơ chế đọc được thiết kế, kiểm soát quyền và kiểm chứng an toàn khi lỗi**.

## 6. Container/Kubernetes: volume secret không có nghĩa là không thể lộ

Một container có thể được cấu hình để mount Secret tại đường dẫn cố định mà không hardcode giá trị vào image:

```yaml
# Trích đoạn cấu hình container minh họa;
# Secret app-db-credentials phải được tạo/provision riêng.
containers:
  - name: orders-api
    image: example/orders-api:stable
    env:
      - name: DB_PASSWORD_FILE
        value: /var/run/secrets/orders-db/password
    volumeMounts:
      - name: db-credentials
        mountPath: /var/run/secrets/orders-db
        readOnly: true
volumes:
  - name: db-credentials
    secret:
      secretName: app-db-credentials
      defaultMode: 0400
```

Đây là **đoạn fragment**, không phải Deployment manifest hoàn chỉnh; container thực tế còn cần các biến cấu hình khác và security context phù hợp. `defaultMode: 0400` chỉ có ích khi file owner/user chạy process được thiết lập tương thích; không nên dựa vào nó thay cho RBAC, container isolation hoặc encryption.

Một **Kubernetes Secret object** chứa giá trị được biểu diễn dưới dạng Base64 trong manifest/API, **Base64 không phải mã hóa bảo mật**. Không commit YAML chứa giá trị secret được Base64 hóa rồi cho rằng đã an toàn. Đối với cluster thật, cần kiểm soát quyền đọc Secret bằng RBAC, cấu hình mã hóa at rest theo hạ tầng, quyền truy cập etcd, audit và cơ chế provision/rotation từ nguồn được phê duyệt.

Tệp mount có thể được nền tảng cập nhật bằng cách thay đổi symlink/volume contents; việc ứng dụng đọc file **mỗi lần mở connection** cũng không phải chiến lược tốt nếu tạo thêm I/O và race. Thường cần một tiến trình hoặc ứng dụng quan sát secret version, xác minh rồi thay cấu hình pool bằng quy trình có kiểm soát. Với mount dạng `subPath` hoặc các cơ chế copy-on-start, cách cập nhật có thể khác; phải kiểm tra phiên bản/orchestrator đang dùng.

## 7. Chứng thực kết nối DB: bảo vệ cả kênh truyền

Giấu password trong secret manager nhưng gửi nó qua kết nối không được xác thực vẫn chưa đủ. Với PostgreSQL JDBC driver, một JDBC URL mẫu yêu cầu **TLS và xác minh hostname**:

```text
jdbc:postgresql://db.internal.example:5432/orders?sslmode=verify-full
```

Chế độ `verify-full` trong PostgreSQL JDBC thường yêu cầu chứng chỉ server được tin cậy và hostname khớp; phải cấu hình trust anchor/CA thích hợp theo môi trường. Không hạ xuống `require`/chế độ bỏ xác minh tên máy **chỉ để sửa một lỗi certificate** mà không hiểu rủi ro. Nếu dùng DB proxy/managed service, phải biết endpoint nào được TLS bảo vệ và điểm kết thúc TLS nằm ở đâu.

Một vài nguyên tắc:

- **Không đặt password trong JDBC URL**, kể cả query string `?password=...`; URL thường được log trong lỗi kết nối/metric.
- **Chứng chỉ CA công khai** không nhất thiết là secret, nhưng không được tự động tin một CA giả mạo. Quản lý phiên bản truststore và quy trình thay CA.
- **Client private key**, nếu dùng mTLS, là secret phải được cấp, giới hạn quyền và rotate như credential.
- **Database identity** cần gắn với host/instance thực: TLS mã hóa lưu lượng nhưng chỉ an toàn trước giả mạo máy chủ khi có xác minh danh tính phù hợp.
- **Không dùng `trustAll`, `sslmode=disable` hoặc cờ bỏ qua hostname check trong production** để chữa lỗi cấu hình.

Connection pool cần tái tạo kết nối sau sự cố; một connection cũ đã thiết lập trước khi thay secret có thể còn hoạt động một thời gian. Điều đó không chứng minh rotation hoàn tất hoặc các kết nối mới đã được xác thực bằng thông tin mới.

## 8. Quyền tối thiểu: secret đúng nhưng role quá mạnh vẫn nguy hiểm

Nếu ứng dụng bị chiếm quyền thực thi SQL, một mật khẩu của tài khoản có quyền `SUPERUSER` hoặc `DROP TABLE` sẽ làm mức độ thiệt hại lớn hơn rất nhiều. Tài khoản DB dành cho runtime nên chỉ được quyền cần cho nghiệp vụ.

Ví dụ mô tả chính sách cho PostgreSQL (DBA thực hiện trong môi trường đã cấu hình; cú pháp và đối tượng quyền cần đối chiếu với schema thực tế):

```sql
-- Ví dụ: role ứng dụng đã được DBA tạo và cấp thông tin
-- xác thực bằng quy trình secret provisioning riêng.
GRANT CONNECT ON DATABASE orders_db TO orders_app;
GRANT USAGE ON SCHEMA public TO orders_app;
GRANT SELECT, INSERT, UPDATE ON TABLE public.orders TO orders_app;

-- Nếu chỉ cần endpoint báo cáo:
GRANT CONNECT ON DATABASE orders_db TO orders_reader;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON TABLE public.orders TO orders_reader;
```

Đây là **ví dụ cấp quyền bổ sung**, không phải chính sách hoàn chỉnh: quyền hiện có qua `PUBLIC`, role membership, default privileges, sequence, schema khác và row-level security phải được kiểm tra riêng. `GRANT` không tự thu hồi quyền rộng đã có; cần chủ động audit/revoke theo nhu cầu.

| Danh tính | Quyền nên cân nhắc | Quyền thường không cần |
| --- | --- | --- |
| Service runtime ghi đơn | SELECT/INSERT/UPDATE theo bảng và thao tác | DDL toàn schema, quản lý role, backup toàn DB |
| Read-only report | SELECT hoặc view phù hợp; hạn chế cột nhạy cảm | INSERT/UPDATE/DELETE, ALTER/DROP |
| Migration runner | DDL giới hạn schema và thời gian chạy qua CI/CD được phê duyệt | Truy cập runtime thường xuyên bằng credential DDL |
| Backup/restore operator | Quyền và cơ chế được DB hỗ trợ cho sao lưu/phục hồi | Dùng chung credential với service xử lý HTTP |

Một **role database** chỉ là một lớp bảo vệ. Đối với hệ thống nhiều tenant, cần bảo vệ tenant ID ở tầng ứng dụng hoặc row-level security đúng cách, dùng prepared statement để chống SQL injection và hạn chế dữ liệu nhạy cảm trong log. Lưu secret ngoài mã không tự giải quyết phân quyền nghiệp vụ hay kiểm soát truy vấn.

## 9. Rotation: thay credential mà không làm sập connection pool

Rotation có nghĩa là **phát hành credential mới, chuyển tất cả consumer hợp lệ sang credential mới và thu hồi credential cũ**. Không thể coi rotation hoàn tất chỉ vì secret manager đã lưu version mới: JVM có thể vẫn đang giữ password cũ, pool có các connection cũ và một vài instance chưa restart.

```text
T0: Secret version A -> App replicas dùng A -> DB chấp nhận A
T1: Tạo B, chuẩn bị DB chấp nhận B
T2: Secret manager/volume cấp B
T3: App replicas chuyển sang B; mở connection mới kiểm tra
T4: Quan sát mọi instance/pool đã chuyển xong, không còn A cần thiết
T5: Thu hồi A; giám sát lỗi xác thực và kế hoạch rollback
```

**Lưu ý PostgreSQL:** một role thông thường không hỗ trợ **hai password độc lập cùng có hiệu lực** chỉ bằng một lệnh đổi password đơn giản. Nếu thay password của **cùng một role**, các kết nối mới với password cũ có thể thất bại ngay từ lúc cập nhật; connection đang tồn tại có thể vẫn hoạt động. Nếu cần giai đoạn chồng lấn A/B, cân nhắc **hai database role được cấp quyền tương đương theo kiểm soát** hoặc một cơ chế danh tính/token được hệ quản trị hỗ trợ. Không giả định mô hình “DB nhận cả A và B” nếu DB thực tế không hỗ trợ.

Quy trình rotation an toàn gồm:

1. **Kiểm kê consumer:** API, worker, batch, job migration, dashboard, read replica và công cụ vận hành; không bỏ sót consumer dùng chung credential.
2. **Phát hành version mới:** tạo secret từ hệ thống quản lý được phê duyệt; không gửi qua chat, issue, email hoặc command line có lưu lịch sử.
3. **Chuẩn bị giai đoạn chồng lấn hoặc cutover:** theo khả năng DB; nếu cần hai role, cấp quyền tối thiểu tương đương và hạn chế truy cập.
4. **Chuyển các ứng dụng có điều phối:** refresh secret và **recreate/drain pool** hoặc rolling restart theo thiết kế; không giả định HikariDataSource tự đọc lại secret file.
5. **Xác minh:** kết nối mới có thành công, request/transaction tiếp tục hoạt động, số lỗi authentication/pool timeout có tăng không?
6. **Thu hồi:** vô hiệu hóa credential/role cũ khi xác nhận không consumer hợp lệ nào còn cần; làm sạch bản sao secret không còn hợp lệ theo retention policy.
7. **Audit và diễn tập:** ghi thời điểm, phạm vi, hệ thống chịu ảnh hưởng và kết quả test. Có kịch bản nếu một nhóm instance không chuyển được sang secret mới.

Với workload identity hoặc token ngắn hạn, JDBC driver/pool vẫn cần được cấu hình để **mỗi kết nối mới** có thể nhận credential còn hạn. Token hết hạn có thể làm việc tạo connection mới thất bại nếu pool chỉ giữ token của lúc khởi động. Thư viện tích hợp cloud/proxy có thể hỗ trợ refresh; phải kiểm tra theo provider thực tế.

### Thu hồi một secret đã lộ

Nếu password từng xuất hiện trong Git, CI log hoặc artifact công khai:

- **Thu hồi/đổi ngay credential** theo kênh kiểm soát sự cố; chỉ xóa dòng khỏi commit mới là không đủ vì lịch sử và bản sao khác còn tồn tại.
- Xác định phạm vi truy cập: log xác thực, audit DB, truy cập bất thường, khung thời gian bí mật có thể đã bị khai thác.
- Hạn chế quyền/cách ly hệ thống theo kế hoạch ứng phó sự cố; cập nhật secret cho các consumer hợp lệ.
- Làm sạch repository history, cache, artifact, CI logs và bản sao nơi được phép/khả thi **sau khi** đã thu hồi; việc “rewrite history” không thể bảo đảm mọi bản clone biến mất.
- Xem lại nguyên nhân gốc: pre-commit secret scanning, quyền người dùng, quy trình rotation và bảo vệ diagnostic.

## 10. Không để thông tin nhạy cảm đi vào log, lỗi và quan sát vận hành

Một lỗi kết nối có thể xuất hiện khi secret manager quá hạn quyền, certificate không hợp lệ, DB từ chối login hoặc pool đạt timeout. Log cần đủ thông tin để điều tra nhưng **không được ghi secret**.

Ví dụ nội dung log nên hướng tới:

```text
WARN persistence_connection_failed
  service=orders-api
  pool=orders-db-pool
  stage=connect
  sqlstate_class=28
  attempt=2
  credential_version=opaque-version-id
  password=[REDACTED]
```

Đây là mẫu mô tả **không phải format bắt buộc**. Nếu version ID tự chứa thông tin nhạy cảm hoặc giúp suy ra đường dẫn secret, hãy thay bằng định danh giám sát không bí mật. Trong môi trường thật, có thể **bỏ hoàn toàn field `password`** thay vì ghi dấu `[REDACTED]`. Cần kiểm tra exception message của driver và thư viện: không giả định framework tự xóa mọi URL/header/parameter trước khi log.

Không viết:

```java
// KHÔNG NÊN:
System.out.println(System.getenv());
logger.info("database properties: {}", connectionProperties);
logger.error("DB auth failed; password={}", password);
```

Cũng phải bảo vệ error page, Spring Actuator endpoint, metrics label, tracing baggage, debugger snapshot, profiling/heap dump, support bundle và crash upload. Secret có thể đi vào hệ thống tập trung của tổ chức, nơi nhiều người có quyền đọc hơn máy chủ ứng dụng.

### Bảo vệ cả URL, không chỉ password

Một URL tưởng không có mật khẩu vẫn có thể làm lộ topology nội bộ, tên database hoặc thông số TLS. Khi URL chứa credential dưới dạng query parameter, log nguyên văn URL là leak trực tiếp. Thay vì log toàn chuỗi, chỉ log **một tên logical data source** hoặc host đã được chính sách cho phép hiển thị.

Đảm bảo pipeline observability không thu full JDBC bind values trong production nếu có PII, thẻ thanh toán, token hoặc bí mật. Nếu cần debug truy vấn, ưu tiên query fingerprint, thời lượng, số hàng và mã lỗi đã chuẩn hóa.

## 11. Môi trường phát triển, test và production phải tách biệt

Một hệ thống có thể giữ mã Java dùng chung nhưng cần **tách danh tính và dữ liệu**:

| Môi trường | Nguồn cấu hình | Mức quyền/đặc điểm |
| --- | --- | --- |
| Local development | File bí mật không theo Git, công cụ dev vault hoặc DB container với credential giả | Chỉ DB local/test, không reuse password production |
| CI/test | Secret ngắn hạn hoặc DB disposable được provision cho job | Giới hạn thời gian sống; không in biến môi trường; không chạm DB production |
| Staging | Secret path và DB riêng; dữ liệu giả/đã xử lý phù hợp quyền riêng tư | Có thể gần production về cấu hình nhưng không dùng chung tài khoản |
| Production | Secret manager/identity được quản trị; quyền DB theo workload | Audit, rotation, network isolation, backup và cảnh báo |

Một tệp `.env` hoặc cấu hình local **không được commit** vẫn có thể bị leak nếu được đồng bộ lên cloud drive hoặc chia sẻ theo đường không an toàn; sử dụng quyền file và vòng đời phù hợp. Thêm file vào `.gitignore` có ích nhưng **không bảo vệ tệp đã từng commit**. Tránh cung cấp credential production cho developer để “kiểm thử nhanh” một lỗi JDBC; dùng dữ liệu và role thử nghiệm.

Khởi động ứng dụng với secret rỗng hoặc mặc định như `password=postgres` khi thiếu cấu hình production là **fail open** nguy hiểm. Kiểm soát startup validation để lỗi rõ ràng ngay tại bootstrap, nhưng không tiết lộ giá trị bị thiếu.

## 12. Kiểm thử và giám sát hệ thống quản lý secret

Không nhất thiết chạy penetration test phức tạp để phát hiện lỗi cơ bản. Nên có kiểm thử ở từng lớp:

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Thiếu secret ở startup | Ứng dụng không kết nối bằng fallback; không in giá trị nào ra log |
| Secret file sai quyền hoặc không đọc được | Startup báo lỗi cấu hình an toàn, không xuất file contents |
| Password sai/role bị revoke | Kết nối mới thất bại có kiểm soát; health/readiness phản ánh đúng |
| DB certificate/hostname sai | Handshake không được chấp nhận khi cấu hình xác minh TLS |
| Rotate secret đang phục vụ traffic | Pool chuyển qua credential mới có điều phối, không tạo gián đoạn ngoài ngân sách |
| Secret manager tạm thời mất kết nối | Retry/backoff/cached policy đúng thiết kế, không giữ connection DB vô ích |
| Log/trace/exception khi lỗi kết nối | Không xuất password/token/private key, JDBC URL nhạy cảm hoặc file secret |
| Scan repository/image/CI output | Không phát hiện bí mật xác thực thật đã được commit/bake vào artifact |
| Quyền app runtime | Role ứng dụng không có DDL/admin không cần thiết; role read-only không thể ghi |

Các metric/alert hữu ích: tỷ lệ lỗi DB authentication, số lần không lấy được secret, tuổi/phiên bản secret đang dùng, thời gian refresh, lỗi TLS handshake, số connection creation failure, active/pending connection pool và số instance chưa chuyển sau rotation. Không đưa **giá trị secret** vào metric label hoặc trace attribute.

Nếu cần kiểm thử rotation, nên dùng một môi trường có DB và secret path riêng, đồng thời mô phỏng các phiên bản app cũ/mới còn sống. Kiểm tra đặc biệt tình huống một pod giữ connection cũ và pod khác tạo connection mới: thành công nhất thời trên connection cũ không chứng minh credential mới đã hoạt động.

## 13. Bài tập thực hành

### Bài tập 1: xác định đâu là secret

Một service có `DB_HOST`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD` và `DB_CA_CERTIFICATE`. Trường nào chắc chắn là bí mật? Trường nào tuy không bí mật nhưng cần bảo vệ tính toàn vẹn?

**Gợi ý:** password là secret. Host/port/username là cấu hình có thể nhạy cảm tùy tổ chức và cần kiểm soát thay đổi. CA certificate công khai thường không phải secret, nhưng tính toàn vẹn của nó rất quan trọng. Nếu có client private key, khóa riêng đó là secret.

### Bài tập 2: biến môi trường đã đủ chưa?

Developer chuyển mật khẩu từ Java literal sang `DB_PASSWORD`, sau đó bật logging mọi environment variable để debug. Họ có còn lộ secret không?

**Đáp án:** có. Secret có thể nằm trong log dù không còn trong Git. Cần giới hạn quyền đọc env, không log toàn bộ cấu hình, áp dụng masking và cân nhắc tệp mount/secret manager phù hợp.

### Bài tập 3: cùng role khi rotation

DB PostgreSQL chỉ có role `orders_app` với password A. Đội vận hành đổi role ngay sang password B rồi mới cập nhật secret cho 20 instance Java. Điều gì có thể xảy ra?

**Đáp án:** những instance vẫn dùng A có thể không tạo được connection mới dù một số connection cũ còn sống. Cần cutover có điều phối, hoặc mô hình hai role/grace period nếu cho phép; kiểm tra pool và trạng thái kết nối mới trước khi thu hồi đường cũ.

### Bài tập 4: lỗi TLS bị “chữa” sai

Ứng dụng báo hostname certificate mismatch, developer đổi URL từ `sslmode=verify-full` sang `sslmode=disable` cho hết lỗi. Cách làm có an toàn không?

**Đáp án:** không. Lỗi gợi ý tên host, CA hoặc cấu hình certificate chưa khớp. Cần sửa chứng chỉ, truststore và endpoint hợp lệ; bỏ xác minh chỉ làm giảm bảo vệ thông tin xác thực và dữ liệu truyền.

### Bài tập 5: phân quyền tài khoản runtime

API chỉ đọc đơn và cập nhật trạng thái nhưng lại dùng credential có quyền tạo role, sửa schema và xóa mọi bảng. Nếu password bị lộ, mức độ thiệt hại thay đổi thế nào?

**Đáp án:** attacker có thể làm nhiều hơn use case bình thường. Cần database role giới hạn bảng và thao tác, tách role migration/backup/report, thu hồi quyền không cần thiết và audit quyền kế thừa.

### Bài tập 6: xác minh secret rotation

Secret manager đã ghi version B, nhưng 10% instance vẫn báo login thất bại khi pool mở connection mới; các truy vấn đang chạy khác vẫn thành công. Có thể tuyên bố rotation hoàn tất không?

**Đáp án:** chưa. Phải xác minh **tất cả** instance đọc version mới và tạo connection mới thành công, điều tra quyền/cấu hình của nhóm còn lỗi, theo dõi timeout/pool và chỉ thu hồi A theo quy trình đã phê duyệt.

### Checklist trước khi đưa persistence vào production

- JDBC URL, username, password và private key có được **cấp từ cấu hình/secret source ngoài mã nguồn và image** không?
- Bí mật có bị đưa vào Git, lịch sử commit, tài liệu, ticket, CI log, environment dump hoặc endpoint diagnostic không?
- Workload có identity được xác thực, quyền secret manager tối thiểu, audit và vùng lưu an toàn không?
- Có xác thực TLS server/hostname; không nhúng password vào URL, log hoặc metrics không?
- Database role có quyền SQL tối thiểu; tài khoản migration/backup/reader đã được tách theo nhiệm vụ chưa?
- Secret thiếu/sai sẽ **fail closed**; không dùng default password hoặc tự đổi sang môi trường khác không?
- Có quy trình rotation, tái tạo/refresh pool, kiểm tra connection mới và thu hồi credential cũ không?
- Có kiểm thử mất secret manager, certificate lỗi, quyền file, rò rỉ qua logs và khởi động lại sau rotation không?
- Có kế hoạch ứng phó credential lộ, revoke/audit, rà soát artifact và dữ liệu backup không?

**Kết luận:** Giữ mật khẩu ngoài mã nguồn là **điểm bắt đầu**, không phải đích đến. Một hệ thống Java persistence an toàn cần nguồn cấu hình được kiểm soát, danh tính workload, secret manager/file mount với quyền phù hợp, kênh JDBC có xác minh TLS, database role tối thiểu và quy trình xoay vòng/thu hồi có thể kiểm thử. Bảo vệ secret phải bao trùm toàn bộ hành trình từ build, deploy, runtime, log cho tới backup và ứng phó sự cố; đồng thời giữ ranh giới giao dịch và connection pool hoạt động ổn định.
