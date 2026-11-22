# Phân biệt lỗi không tìm thấy driver và lỗi không kết nối được máy chủ

Trong **JDBC (Java Database Connectivity)**, hai sự cố thường xuất hiện ngay khi ứng dụng bắt đầu truy cập cơ sở dữ liệu quan hệ:

1. **Ứng dụng không tìm thấy hoặc không chọn được JDBC driver phù hợp** để xử lý URL kết nối.
2. **Ứng dụng đã có driver nhưng chưa thể thiết lập kết nối đến máy chủ cơ sở dữ liệu**.

Cả hai có thể xảy ra khi gọi `DriverManager.getConnection(...)`, nhưng nguyên nhân và cách khắc phục khác nhau. Trường hợp thứ nhất thường liên quan đến **dependency, classpath/module path, class loader, cơ chế đăng ký driver hoặc cú pháp JDBC URL**. Trường hợp thứ hai thường liên quan đến **hostname, cổng, mạng, firewall, tiến trình DBMS, cấu hình listener hoặc việc thương lượng kết nối**. Sau khi đã liên lạc được với máy chủ, còn có thể phát sinh lỗi **xác thực, quyền truy cập, tên cơ sở dữ liệu hoặc TLS**; không nên tự động gộp tất cả vào nhóm “máy chủ không chạy”.

Bài thuộc chương **Driver và cấu hình** này hướng dẫn nhận diện lỗi theo **giai đoạn phát sinh**, đọc ngoại lệ có ý nghĩa và kiểm tra từng lớp từ ứng dụng Java đến hệ quản trị dữ liệu.

## 1. Một kết nối JDBC đi qua những giai đoạn nào?

Một đoạn mã kết nối điển hình:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

String url = "jdbc:postgresql://db.example.internal:5432/shop";
String username = System.getenv("DB_USER");
String password = System.getenv("DB_PASSWORD");

try (Connection connection =
             DriverManager.getConnection(url, username, password)) {
    System.out.println("Đã mở kết nối JDBC");
} catch (SQLException ex) {
    System.err.println("SQLState: " + ex.getSQLState());
    System.err.println("Vendor code: " + ex.getErrorCode());
    System.err.println("Message: " + ex.getMessage());
}
~~~

URL trên chỉ minh họa cấu trúc PostgreSQL; để chạy cần có **PostgreSQL JDBC driver** tương thích và một máy chủ thật có thể truy cập. Khi đưa mã vào sản phẩm, không in password, URL có chứa credential, token hoặc thông tin nhạy cảm vào log. Đoạn ví dụ dành cho môi trường thực hành.

Trước khi trả về một `Connection`, hệ thống phải vượt qua một số bước:

~~~mermaid
flowchart TD
    A["Ứng dụng gọi getConnection(url)"] --> B{"Có driver được nạp và chấp nhận URL?"}
    B -->|"Không"| C["Nhóm A: thiếu driver / URL sai"]
    B -->|"Có"| D["Driver phân tích host, port, database, tùy chọn"]
    D --> E{"Có thể mở kết nối mạng?"}
    E -->|"Không"| F["Nhóm B: DNS / timeout / refused / network"]
    E -->|"Có"| G{"Handshake, TLS, xác thực và cấu hình DB hợp lệ?"}
    G -->|"Không"| H["Nhóm C: cấu hình, xác thực hoặc protocol"]
    G -->|"Có"| I["Connection sẵn sàng chạy SQL"]
~~~

Điểm cần nhớ: **driver phải được tìm thấy và chấp nhận JDBC URL trước khi có thể thực hiện giao tiếp bình thường với DBMS**. Tuy nhiên, từng driver có thể báo lỗi tại các thời điểm khác nhau; phải dựa trên thông tin ngoại lệ thực tế, không suy luận chỉ từ vị trí dòng mã.

## 2. Nhóm A: Java không tìm thấy lớp JDBC driver

Thông báo điển hình của cách nạp driver thủ công:

~~~text
java.lang.ClassNotFoundException: org.postgresql.Driver
~~~

Giả sử chương trình có:

~~~java
Class.forName("org.postgresql.Driver");
~~~

`ClassNotFoundException` nghĩa là class loader được sử dụng **không tìm thấy định nghĩa lớp với tên đó**. Một số nguyên nhân:

- Chưa thêm thư viện JDBC driver vào dependency của ứng dụng.
- Thư viện chỉ có ở thời điểm **biên dịch** hoặc **kiểm thử**, nhưng không có ở **runtime** nơi ứng dụng chạy.
- Tên lớp truyền vào `Class.forName` sai hoặc thuộc driver của hệ quản trị khác.
- Ứng dụng chạy trong môi trường có **class loader** riêng (application server, plugin, môi trường module) và driver không hiển thị với loader cần thiết.
- Gói đóng ứng dụng không chứa JAR/metadata cần thiết của driver, hoặc cách đóng gói đã làm hỏng phần nạp tự động.

Đây **chưa phải bằng chứng máy chủ cơ sở dữ liệu lỗi**: Java có thể chưa chạy tới bước mở kết nối mạng.

### JDBC 4 trở lên: thường không cần `Class.forName`

Với driver JDBC hiện đại được đóng gói đúng cách, `DriverManager` thường tự phát hiện driver qua cơ chế **service provider** khi driver có mặt trong runtime. Do đó, mã bình thường có thể viết:

~~~java
Connection connection =
        DriverManager.getConnection(url, username, password);
~~~

Không nhất thiết phải gọi `Class.forName("org.postgresql.Driver")` trước. Việc thêm `Class.forName` đôi khi có ích như **phép kiểm tra chẩn đoán tách biệt** để xem JVM có nạp được lớp driver hay không; nó không thay thế việc cấu hình dependency đúng và không chứng minh mạng đã hoạt động.

### Kiểm tra dependency ở đúng môi trường chạy

Ví dụ khai báo dependency trong Gradle:

~~~kotlin
dependencies {
    // Thay <driver-version> bằng phiên bản tương thích đã chọn.
    runtimeOnly("org.postgresql:postgresql:<driver-version>")
}
~~~

Ví dụ dùng Maven:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version>VERSION_DA_CHON</version>
    <scope>runtime</scope>
</dependency>
~~~

Với thư viện driver của DBMS khác, **group/artifact** cũng khác; không thể dùng PostgreSQL driver để kết nối tùy ý tới mọi DBMS. Các chuỗi phiên bản trong ví dụ chỉ là chỗ cần điền phiên bản thật phù hợp với môi trường của dự án.

Khi chẩn đoán, phải kiểm tra **dependency resolution và classpath của chính tiến trình đang chạy**. Một IDE có thể chạy được nhờ dependency riêng, nhưng lệnh đóng gói hoặc chạy ứng dụng ở máy chủ lại thiếu JAR. Cũng có thể bài kiểm thử tìm thấy driver, nhưng bản phát hành chạy ở môi trường khác thì không.

### `NoClassDefFoundError` có giống `ClassNotFoundException` không?

Không hoàn toàn. `ClassNotFoundException` thường xuất hiện khi yêu cầu tải một lớp theo tên nhưng không tìm thấy. `NoClassDefFoundError` có thể xuất hiện khi JVM cố sử dụng một lớp cần thiết lúc runtime nhưng không định nghĩa/khởi tạo được lớp đó; chẳng hạn driver bị thiếu một dependency liên quan hoặc có vấn đề khi khởi tạo.

Trong cả hai tình huống, hãy kiểm tra **đầy đủ các JAR và mối quan hệ class loader**. Đừng sửa hostname hoặc firewall trước khi giải quyết lỗi tải lớp.

## 3. Nhóm A khác: `No suitable driver found`

Một thông báo thường gặp khác:

~~~text
java.sql.SQLException: No suitable driver found for jdbc:postgresql://localhost:5432/shop
~~~

Thông điệp này thường phát sinh từ `DriverManager` khi **không có driver hiện có nào chấp nhận JDBC URL được truyền vào**. Có ít nhất hai khả năng cần kiểm tra riêng:

1. Driver tương ứng không được nạp/đăng ký hoặc không hiển thị với `DriverManager` ở runtime.
2. Driver đã có nhưng **URL sai cú pháp hoặc sai tiền tố**, nên driver không nhận URL đó.

Đây là lý do không nên kết luận rằng “chắc chắn thiếu JAR” chỉ vì thấy `No suitable driver`.

Ví dụ:

~~~text
# Cấu trúc minh họa cho PostgreSQL
jdbc:postgresql://localhost:5432/shop

# Cấu trúc minh họa cho MySQL
jdbc:mysql://localhost:3306/shop

# Có thể không được PostgreSQL driver chấp nhận vì sai tiền tố/cấu trúc
jdbc:postgre://localhost:5432/shop
~~~

Một driver chỉ nhận các URL mà nó hỗ trợ. **Chuỗi bắt đầu bằng `jdbc:` không có nghĩa là mọi driver đều có thể xử lý chuỗi đó**.

### Kiểm tra `acceptsURL` để tách hai nguyên nhân

Với driver PostgreSQL và code chẩn đoán riêng, có thể kiểm tra:

~~~java
import java.sql.Driver;

Driver driver = new org.postgresql.Driver();

boolean accepted = driver.acceptsURL(
        "jdbc:postgresql://localhost:5432/shop");
System.out.println(accepted);
~~~

Ví dụ này cần thư viện driver ở **compile classpath** vì code tham chiếu trực tiếp `org.postgresql.Driver`. Với ứng dụng bình thường chỉ dùng API `java.sql`, không nhất thiết phải phụ thuộc trực tiếp vào lớp driver. Khi `acceptsURL` trả `true`, điều đó chỉ nói URL *có thể* thuộc loại driver xử lý; **nó không chứng minh server đang chạy, credential đúng hay DB tồn tại**.

Để chẩn đoán theo cách không phụ thuộc lớp riêng của driver, `DriverManager.getDrivers()` cho phép liệt kê những driver được đăng ký và hiển thị với mã gọi. Cơ chế class loader có thể ảnh hưởng danh sách:

~~~java
import java.sql.Driver;
import java.sql.DriverManager;
import java.util.Enumeration;

Enumeration<Driver> drivers = DriverManager.getDrivers();
while (drivers.hasMoreElements()) {
    Driver driver = drivers.nextElement();
    System.out.println(driver.getClass().getName());
}
~~~

Nếu driver cần thiết không có trong danh sách, hãy kiểm tra dependency và quá trình nạp. Nếu có, kiểm tra lại JDBC URL, driver đang được dùng và các cấu hình liên quan.

## 4. Nhóm B: driver có mặt nhưng máy chủ không truy cập được

Khi driver đã chấp nhận URL và cố thiết lập kết nối mạng, những thông báo sau có thể xuất hiện (văn bản tùy driver và hệ điều hành):

~~~text
Connection refused
Connection timed out
The connection attempt failed
UnknownHostException: db.example.internal
Communications link failure
~~~

Thông thường các lỗi này được gói trong `SQLException`, với một `cause` bên dưới như `java.net.ConnectException`, `java.net.SocketTimeoutException` hoặc `java.net.UnknownHostException`. Nhưng **tên lớp ngoại lệ hay thông điệp chính xác không giống nhau trên mọi driver**.

| Dấu hiệu | Giải thích có thể xảy ra | Nên kiểm tra trước |
| --- | --- | --- |
| **Connection refused** | Đã tới địa chỉ mạng nhưng kết nối tới cổng bị từ chối; không có listener phù hợp hoặc có thiết bị chủ động từ chối | DBMS có chạy và lắng nghe đúng interface/cổng không? Host/port đúng không? |
| **Connection timed out** | Không hoàn tất được kết nối trong khoảng chờ; có thể bị chặn hoặc đường mạng không tới | Firewall, route, VPN, security group, network policy, timeout |
| **Unknown host / DNS error** | Tên máy không phân giải được thành địa chỉ phù hợp | Hostname, DNS, VPN, cách đặt tên trong Docker/Kubernetes |
| **Connection reset / broken pipe** | Kết nối bị đóng đột ngột trong hoặc sau khi trao đổi dữ liệu | DBMS restart, proxy, network, cấu hình TLS, timeout ở hai đầu |
| **Communications link failure** | Thông điệp tổng quát của một số driver khi giao tiếp thất bại | Xem `cause` và giai đoạn thất bại; đừng suy ra một nguyên nhân duy nhất |

Trong các tình huống này, **thay phiên bản driver một cách ngẫu nhiên thường không phải bước chẩn đoán đầu tiên**. Hãy kiểm tra endpoint, mạng và tiến trình DBMS từ đúng môi trường mà ứng dụng đang chạy.

### `localhost` thường bị hiểu sai

`localhost` nghĩa là **máy/môi trường mạng của chính tiến trình đang kết nối**:

- Ứng dụng Java chạy trên máy cá nhân, DBMS cũng chạy ở máy đó: `localhost` có thể đúng.
- Ứng dụng Java nằm trong **container Docker**, DBMS nằm trên máy host: `localhost` bên trong container **trỏ về container**, không mặc nhiên là host.
- Ứng dụng và DBMS ở **hai container khác nhau**: thường cần tên dịch vụ/địa chỉ trong mạng chung được cấu hình đúng, không dùng `localhost` như thể cả hai cùng một container.
- Ứng dụng chạy trên máy chủ hoặc Kubernetes: `localhost` trỏ về môi trường/pod nơi ứng dụng chạy, tùy cách triển khai.

Vì thế, một URL chạy được từ laptop không nhất thiết chạy được từ container hoặc server. Hãy xác minh hostname và route **ngay nơi JVM đang thực thi**.

### Phân biệt “máy chủ không chạy” và “không đến được máy chủ”

Khi nhận `Connection refused`, DBMS có thể chưa khởi động, đang lắng nghe cổng khác hoặc chỉ bind vào giao diện loopback. Khi nhận timeout, DBMS thậm chí có thể vẫn chạy tốt nhưng đường mạng bị chặn. Một cổng mở ở tầng TCP chỉ chứng minh có thể kết nối đến một điểm lắng nghe; nó **chưa chứng minh** JDBC handshake, TLS, credential hoặc tên database hợp lệ.

## 5. Những lỗi xảy ra sau khi đã tới DBMS

Không phải mọi `SQLException` từ `getConnection` đều thuộc nhóm “không kết nối được server”. Nếu mạng đã thông, server vẫn có thể từ chối phiên JDBC vì:

- **Sai username/password** hoặc phương thức xác thực.
- User không được phép truy cập database hoặc không nằm trong danh sách cho phép.
- **Tên database sai/không tồn tại**, schema hoặc service name sai tùy DBMS.
- **TLS/SSL** không khớp: CA không tin cậy, chứng chỉ không hợp lệ, tên host khác chứng chỉ, hoặc chính sách mã hóa giữa client và server không tương thích.
- Driver và DBMS không tương thích về một số tính năng/giao thức, hoặc một proxy/connection gateway không cho phép kết nối.
- DBMS đã đạt giới hạn kết nối, quá tải hoặc đang từ chối phiên mới.

Ví dụ thông điệp thường gặp:

~~~text
password authentication failed for user ...
Access denied for user ...
database ... does not exist
SSLHandshakeException
too many connections
~~~

Lỗi xác thực hay tên DB không phải lý do để sửa dependency trước tiên. Ngược lại, **đừng vô hiệu hóa kiểm tra TLS/chứng chỉ để “làm cho kết nối chạy”**: cần sửa chứng chỉ, trust store và cấu hình transport đúng với chính sách hệ thống.

## 6. Đọc `SQLException` thay vì chỉ đọc dòng báo lỗi

`SQLException` chứa nhiều tín hiệu giúp phân loại nguyên nhân:

- `getMessage()`: thông điệp do driver/DBMS cung cấp; hữu ích nhưng không được chuẩn hóa hoàn toàn.
- `getSQLState()`: mã SQLState, có thể chỉ nhóm lỗi. Theo quy ước SQLState, **class `08`** liên quan đến connection exception; **class `28`** liên quan đến invalid authorization specification. Cách ánh xạ từng lỗi cụ thể tùy driver.
- `getErrorCode()`: mã lỗi do nhà cung cấp DBMS/driver định nghĩa, không dùng chung giữa các DBMS.
- `getCause()`: ngoại lệ gốc của Java, đôi khi chỉ rõ DNS, socket, TLS hoặc IO.
- `getNextException()`: chuỗi các `SQLException` liên quan, đặc biệt hữu ích khi một thao tác có nhiều chẩn đoán từ JDBC/DBMS.

Ví dụ thu thập thông tin lỗi khi kết nối:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class JdbcConnectionDiagnosis {
    public static void main(String[] args) {
        String url = System.getenv("JDBC_URL");
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        if (url == null || url.isBlank() ||
                user == null || password == null) {
            System.err.println("Thiếu cấu hình môi trường JDBC");
            return;
        }

        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {
            System.out.println("Kết nối thành công");
        } catch (SQLException ex) {
            SQLException current = ex;
            while (current != null) {
                System.err.println("SQLException type: "
                        + current.getClass().getName());
                System.err.println("SQLState: " + current.getSQLState());
                System.err.println("Vendor code: " + current.getErrorCode());
                System.err.println("Message: " + current.getMessage());

                Throwable cause = current.getCause();
                if (cause != null) {
                    System.err.println("Cause type: "
                            + cause.getClass().getName());
                }
                current = current.getNextException();
            }
        }
    }
}
~~~

Đoạn này chạy với Java 11 trở lên vì sử dụng `String.isBlank()`. Đây là **công cụ minh họa cho môi trường phát triển có kiểm soát**: trong sản phẩm, thông điệp từ driver đôi khi chứa hostname, tên người dùng hoặc thông tin nhạy cảm; dùng cơ chế log đã được che/lọc và không gửi nguyên văn chi tiết kết nối tới client.

Một số driver gói ngoại lệ sâu hơn một tầng, nên khi cần chẩn đoán nâng cao hãy xem **chuỗi cause**, không chỉ cause đầu tiên. Với `DataSource` hoặc connection pool, lớp framework có thể thêm ngoại lệ như “failed to obtain connection” hoặc “pool timeout”; cần tìm `SQLException` hoặc `cause` bên trong để phân biệt lỗi DBMS và lỗi cạn pool.

## 7. Quy trình chẩn đoán theo thứ tự

Khi gặp lỗi, kiểm tra lần lượt. Quy trình này giúp tránh đổi cấu hình mạng khi vấn đề thực tế là dependency, hoặc sửa Java source khi DBMS không lắng nghe.

### Bước 1 — Xác định ngoại lệ đầu tiên thực sự phát sinh

Đọc **loại ngoại lệ đầy đủ**, thông điệp, SQLState, vendor code và chuỗi `cause`/`nextException`. Xác định lỗi xảy ra khi nạp lớp, chọn driver, mở socket hay trong handshake/xác thực.

| Ngoại lệ/dấu hiệu | Giả thuyết ưu tiên |
| --- | --- |
| `ClassNotFoundException: ...Driver` | Thiếu class driver hoặc class loader không thấy driver |
| `NoClassDefFoundError` trong quá trình nạp driver | Thiếu class phụ thuộc/khởi tạo lỗi hoặc class loader |
| `No suitable driver found for jdbc:...` | Không có driver phù hợp được đăng ký **hoặc** URL không được chấp nhận |
| `UnknownHostException` | DNS/hostname |
| `ConnectException: Connection refused` | Cổng đích không có listener hoặc chủ động từ chối |
| `SocketTimeoutException`, `connect timed out` | Đường kết nối/port không phản hồi đúng thời gian chờ |
| SQLState bắt đầu `08` | Nhóm lỗi kết nối, cần xem lỗi chi tiết |
| SQLState bắt đầu `28` | Nhóm lỗi ủy quyền/xác thực, tùy DBMS |
| Thông báo lỗi certificate/SSL handshake | Cấu hình TLS, certificate, trust chain hoặc hostname |

### Bước 2 — Xác minh driver trong runtime

Xác nhận ba yếu tố khớp nhau: **DBMS đang dùng**, **dependency driver phù hợp**, **tiền tố URL**. Kiểm tra gói ứng dụng phát hành có driver thật sự hay không. Nếu sử dụng Java module/class loader/container đặc thù, xác minh visibility và đăng ký driver ở đúng ngữ cảnh.

Ví dụ lệnh hỗ trợ trong dự án sử dụng công cụ xây dựng phổ biến:

~~~bash
# Dự án Gradle có Wrapper: xem runtime dependencies.
./gradlew dependencies --configuration runtimeClasspath

# Dự án Maven: xem cây dependency.
mvn dependency:tree
~~~

Các lệnh chỉ là cách xem dependency; **kết luận cuối vẫn phải dựa trên môi trường chạy thật**. Một lỗi phổ biến là cấu hình test-runtime có driver nhưng production-runtime lại thiếu.

### Bước 3 — Kiểm tra JDBC URL

Kiểm tra từng thành phần:

~~~text
jdbc:postgresql://db.example.internal:5432/shop
|      |           |                   |    |
|      |           hostname            |    database
|      driver type                     port
JDBC scheme
~~~

URL của hệ quản trị khác có thể có cấu trúc khác. Không tự suy diễn rằng mọi driver chấp nhận chung một dạng `jdbc:vendor://host:port/database`; một số driver hỗ trợ service name, instance name, file path hoặc các thuộc tính đặc thù.

Không đính password hoặc token vào URL trong log hoặc báo lỗi. Nếu URL có query parameters cấu hình, kiểm tra encoding và chính sách bảo mật của driver theo tài liệu nhà cung cấp.

### Bước 4 — Kiểm tra host và cổng từ nơi JVM đang chạy

Trên Windows PowerShell, có thể dùng:

~~~powershell
Test-NetConnection db.example.internal -Port 5432
~~~

Trên môi trường Unix có `nc`:

~~~bash
nc -vz db.example.internal 5432
~~~

Đây là kiểm tra **kết nối TCP cơ bản**; kết quả thành công không đồng nghĩa JDBC đã đăng nhập được. Khi DB nằm trong Docker, Kubernetes, mạng riêng hoặc cloud, phải chạy phép thử từ nơi có đường mạng tương đương JVM; kết quả từ laptop cá nhân có thể không phản ánh điều kiện của ứng dụng trên server.

Nếu thất bại, đối chiếu:

1. DBMS có đang hoạt động?
2. Cổng trong URL có đúng cổng mà DBMS đang nghe?
3. DBMS có lắng nghe địa chỉ mạng phù hợp, hay chỉ `127.0.0.1`?
4. DNS có phân giải đúng hostname từ môi trường ứng dụng?
5. Firewall, cloud security group, network policy, VPN hoặc router có cho phép kết nối?
6. Địa chỉ được dùng có trỏ vào đúng máy chủ/instance, đặc biệt khi có proxy hoặc load balancer?

### Bước 5 — Nếu mạng thông, kiểm tra handshake và quyền truy cập

Xác minh tên database, tài khoản, quyền, phương thức xác thực, chính sách TLS và giới hạn kết nối của server. Nếu dùng pool, xem pool có đang hết kết nối hoặc các connection lâu không được trả về hay không.

Nên thử bằng **một chương trình JDBC tối giản** dùng cùng driver, URL và thông tin xác thực theo cơ chế an toàn. Công cụ CLI của DBMS cũng có thể giúp kiểm tra riêng phía máy chủ, nhưng phải đảm bảo công cụ ấy đi qua cùng đường mạng và không che khuất khác biệt của JDBC driver.

### Bước 6 — Thử lại sau một thay đổi duy nhất

Khi sửa được một nguyên nhân, chạy lại và ghi nhận lỗi mới nếu có. Ví dụ:

~~~text
Trước: ClassNotFoundException
Sau khi thêm driver đúng runtime: No suitable driver (URL sai)
Sau khi sửa URL: Connection refused (DB chưa lắng nghe cổng)
Sau khi mở đúng endpoint: Authentication failed (credential sai)
Sau khi sửa credential hợp lệ: Connection thành công
~~~

Chuỗi minh họa này cho thấy **nhiều lỗi có thể cùng tồn tại**; xử lý được lỗi đầu tiên có thể khiến chương trình tiến đến giai đoạn tiếp theo và lộ ra lỗi khác. Đừng hiểu đó là bản sửa trước khiến hệ thống hỏng thêm.

## 8. Ba ví dụ phân tích sự cố

### Tình huống A — Ứng dụng chạy trong IDE nhưng bản đóng gói báo thiếu driver

Trong IDE, ứng dụng tìm thấy PostgreSQL driver và chạy `SELECT` bình thường. Khi chạy bản phát hành độc lập, có lỗi `No suitable driver` hoặc `ClassNotFoundException`.

**Phân tích:** driver có thể chỉ xuất hiện trong classpath của IDE/test hoặc bị loại khỏi artifact. Cần kiểm tra dependency ở runtime và cách build/launch bản phát hành. Nếu ứng dụng tạo fat JAR, cần bảo đảm metadata service provider của các driver còn nguyên và không bị ghi đè bởi quá trình đóng gói.

**Hướng xử lý:** cấu hình dependency đúng phạm vi, kiểm tra artifact đầu ra và chạy lại chính bản đóng gói trên môi trường phát hành. Không vội mở cổng firewall: ở giai đoạn này Java chưa chắc tìm thấy driver.

### Tình huống B — Kết nối từ máy host được nhưng từ Docker không được

Ứng dụng chạy trực tiếp trên máy phát triển và dùng `jdbc:postgresql://localhost:5432/shop` thành công; chạy trong container lại báo `Connection refused`.

**Phân tích:** bên trong container, `localhost` là container đó. DBMS chạy trên máy host hoặc container khác có thể không nằm tại địa chỉ này.

**Hướng xử lý:** dùng hostname/dịch vụ/địa chỉ phù hợp với cấu hình mạng container; kiểm tra route, cổng công bố, firewall và listener. Xác nhận lại kết nối **từ container đang chạy JVM**. Không giải quyết bằng cách thêm `Class.forName` khi driver vốn đã mở socket.

### Tình huống C — Lỗi “No suitable driver” với JAR đã có

Thư viện PostgreSQL driver hiện diện ở runtime nhưng URL bị viết nhầm thành `jdbc:postgre://...`.

**Phân tích:** `DriverManager` có thể không tìm được driver chấp nhận tiền tố đó, dù class driver đã tồn tại.

**Hướng xử lý:** đối chiếu URL với cú pháp driver chính thức, sửa thành `jdbc:postgresql://...`. Nếu lỗi chuyển sang `Connection refused` thì đó là dấu hiệu ứng dụng đã đi tới giai đoạn mạng; tiếp tục kiểm tra server và cổng.

## 9. Những cách sửa sai cần tránh

| Cách làm vội | Vì sao có vấn đề | Cách đúng hơn |
| --- | --- | --- |
| Thấy `No suitable driver` rồi chỉ thêm `Class.forName` | Có thể driver đã có nhưng URL sai, hoặc runtime thiếu thư viện thật | Kiểm tra cả dependency, đăng ký driver và URL |
| Thấy `Connection refused` rồi đổi driver ngay | Phần lớn trường hợp phản ánh endpoint/listener/network | Kiểm tra host, port, DBMS và đường mạng |
| Dùng `localhost` trong mọi môi trường | `localhost` thay đổi theo nơi JVM chạy | Cấu hình hostname theo môi trường triển khai |
| Tăng timeout rất lớn khi connection refused | Không sửa được cổng bị từ chối hay DBMS ngừng chạy | Tìm nguyên nhân kết nối bị từ chối |
| Vô hiệu hóa kiểm tra TLS để hết lỗi handshake | Làm yếu bảo mật và che giấu cấu hình sai | Sửa trust store/certificate và chính sách TLS |
| Hardcode password vào source/JDBC URL rồi log đầy đủ | Có thể làm lộ credential | Lấy secret từ cơ chế cấu hình an toàn, che thông tin nhạy cảm |
| Đọc duy nhất `getMessage()` | Bỏ lỡ SQLState, mã DB và nguyên nhân mạng bên trong | Xem `SQLState`, `errorCode`, `cause` và `nextException` |
| Chỉ thử port bằng công cụ mạng và kết luận “DB hoàn toàn ổn” | TCP thông chưa chứng minh auth, database, TLS | Thử JDBC tối giản với đúng driver và cấu hình |

## 10. Bài thực hành: tái hiện và phân loại hai lỗi

Chuẩn bị một DBMS dùng cho học tập, driver JDBC tương ứng và một bảng đơn giản (nếu cần). Dùng một chương trình mở kết nối như ở phần đầu, rồi lần lượt thay đổi một yếu tố trong môi trường thử nghiệm.

| Lần thử | Thay đổi có chủ đích | Kết quả dự kiến | Giải thích |
| --- | --- | --- | --- |
| 1 | Chạy mà không có driver trên runtime classpath | `No suitable driver` hoặc lỗi tải class nếu `Class.forName` được gọi | JVM không có driver phù hợp |
| 2 | Có driver, nhưng sửa tiền tố `jdbc:postgresql:` thành tiền tố sai | Có thể xuất hiện `No suitable driver` | URL không được driver chấp nhận |
| 3 | Driver và URL đúng loại, nhưng trỏ tới cổng không lắng nghe | Thường là `Connection refused` | Đã thử tạo kết nối mạng nhưng endpoint không nhận |
| 4 | Dùng hostname không tồn tại/không phân giải được | Lỗi DNS, thường lộ `UnknownHostException` trong cause | Không tìm được địa chỉ máy chủ |
| 5 | Server đúng, dùng mật khẩu sai | Lỗi xác thực từ server | Không phải lỗi thiếu driver |
| 6 | Khôi phục endpoint và credential hợp lệ | `getConnection` trả `Connection` | Các giai đoạn chính đã thành công |

Các lỗi dự kiến **không phải hợp đồng chính xác giữa mọi DBMS và driver**. Khi làm bài, hãy ghi lại: ngoại lệ thực tế, SQLState, vendor code, cause và hành động đã sửa. Không cần cố tình thay đổi firewall hay tắt bảo mật của hệ thống dùng chung; có thể thực hành trên DB thử nghiệm cục bộ có quyền quản lý.

### Câu hỏi tự kiểm tra

1. `ClassNotFoundException` khi gọi `Class.forName("org.postgresql.Driver")` cho biết điều gì? Nó có chứng minh DBMS đang tắt hay không?
2. Vì sao `No suitable driver` có thể xảy ra dù file JAR của driver đã có?
3. Lỗi `Connection refused` khác gì lỗi `Connection timed out` và `UnknownHostException`?
4. Vì sao địa chỉ `localhost` có thể đúng trên máy phát triển nhưng sai trong Docker?
5. Sau khi kiểm tra cổng TCP thành công, còn những bước nào có thể khiến JDBC không mở được `Connection`?
6. `SQLException.getSQLState()`, `getErrorCode()` và `getCause()` giúp khoanh vùng lỗi như thế nào?

**Quy tắc chẩn đoán:** trước hết xác định **JVM có thấy driver và driver có nhận URL hay không**; tiếp theo xác định **mạng có tới được endpoint DBMS hay không**; cuối cùng kiểm tra **handshake, TLS, credential, database và quyền truy cập**. Phân biệt các giai đoạn này giúp sửa đúng nguyên nhân và tránh thay đổi cấu hình JDBC không liên quan.
