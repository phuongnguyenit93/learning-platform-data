# Sai URI, TLS, xác thực, routing hoặc tên database

Khi ứng dụng Spring Data Neo4j (SDN) không kết nối được Neo4j, thông báo lỗi thường xuất hiện lúc khởi động, ở query đầu tiên hoặc khi driver cần định tuyến transaction tới một thành viên khác trong cluster. Những nguyên nhân phổ biến gồm URI sai scheme/host/port, TLS không tin cậy chứng chỉ, thông tin xác thực không hợp lệ, routing table chứa địa chỉ không thể truy cập hoặc database được chọn không tồn tại.

Hãy chẩn đoán theo từng lớp: xác nhận cấu hình Spring Boot, kiểm tra network và Bolt endpoint, xác minh TLS, xác thực tài khoản, kiểm tra routing rồi mới kiểm tra database và quyền truy cập. Cách này giúp phân biệt lỗi kết nối với lỗi query hoặc mapping entity. Một đối tượng `Driver` được tạo thành công chưa chứng minh kết nối đã thành công vì Java Driver thiết lập kết nối theo nhu cầu; hãy chủ động gọi `verifyConnectivity()` hoặc chạy probe query trên database đích.

## 1. Xác định cấu hình kết nối SDN

Với Spring Boot starter, các thuộc tính kết nối cơ bản nằm trong namespace `spring.neo4j`. Database mà SDN repository sử dụng có thể được chọn riêng bằng `spring.data.neo4j.database`.

~~~yaml
spring:
  neo4j:
    uri: neo4j+s://graph.example.com:7687
    authentication:
      username: app_user
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: appdb
~~~

Ý nghĩa:

- `spring.neo4j.uri`: URI của Bolt endpoint hoặc routing entry point.
- `spring.neo4j.authentication.username`: user Neo4j.
- `spring.neo4j.authentication.password`: mật khẩu hoặc secret được inject từ môi trường.
- `spring.data.neo4j.database`: database SDN repository/template sẽ sử dụng.

Không nhầm `spring.neo4j.database` với `spring.data.neo4j.database`. Database selection thuộc cấu hình Spring Data Neo4j; URI và authentication thuộc cấu hình Driver. Nếu ứng dụng dùng `DatabaseSelectionProvider` để chọn database động theo tenant, provider có thể thay đổi lựa chọn tĩnh trong cấu hình.

Có thể cấu hình qua environment variables:

~~~text
SPRING_NEO4J_URI=neo4j+s://graph.example.com:7687
SPRING_NEO4J_AUTHENTICATION_USERNAME=app_user
SPRING_NEO4J_AUTHENTICATION_PASSWORD=<secret-from-secret-manager>
SPRING_DATA_NEO4J_DATABASE=appdb
~~~

Không commit mật khẩu thật vào `application.yml`, source control hoặc log. Nếu secret có ký tự đặc biệt, truyền qua environment/secret manager thay vì ghép username và password vào URI.

## 2. Kiểm tra cấu trúc URI, host và port

Java Driver dùng URI có dạng:

~~~text
<scheme>://<host>[:<port>]
~~~

Một URI Bolt không phải HTTP URL. Không thêm path như `/neo4j/`, không dùng cổng HTTP Browser thay cho Bolt port và không nhúng tên database vào path. Tên database được chọn ở session hoặc qua cấu hình SDN.

Các cổng thường gặp:

| Cổng | Mục đích | Dùng cho Java Driver Bolt? |
|---:|---|---|
| `7687` | Bolt mặc định | Có, nếu server đang lắng nghe tại cổng này |
| `7474` | HTTP endpoint/Neo4j Browser trên self-managed setup | Không |
| `7473` | HTTPS endpoint trên self-managed setup | Không |

Ví dụ URI sai và đúng:

| Sai | Đúng hơn |
|---|---|
| `http://localhost:7474` | `bolt://localhost:7687` cho local không TLS |
| `neo4j://localhost:7474` | `neo4j://localhost:7687` nếu dùng routing |
| `neo4j://graph.example.com/neo4j` | `neo4j://graph.example.com:7687` |
| `neo4j://https://graph.example.com` | `neo4j+s://graph.example.com:7687` nếu endpoint yêu cầu TLS và chứng chỉ CA hợp lệ |

Kiểm tra lại host có thể phân giải DNS từ chính môi trường chạy ứng dụng. `localhost` trong container hoặc pod là container/pod đó, không phải máy Neo4j ở host hay container khác. Trong Docker Compose, ứng dụng thường cần dùng service name trên network chung, ví dụ `neo4j:7687`, thay vì `localhost:7687`.

Trên Windows có thể kiểm tra TCP port:

~~~powershell
Test-NetConnection graph.example.com -Port 7687
~~~

Trên Linux/macOS có thể dùng:

~~~bash
nc -vz graph.example.com 7687
~~~

Nếu TCP connection thất bại, kiểm tra DNS, firewall, security group, network policy, port mapping và Bolt connector trên Neo4j trước khi điều tra password hoặc entity mapping.

## 3. Chọn đúng URI scheme: routing hay kết nối trực tiếp

Scheme quyết định Driver dùng routing hay kết nối trực tiếp, đồng thời quy định TLS:

| Scheme | Routing | TLS và trust | Trường hợp thường dùng |
|---|---|---|---|
| `neo4j://` | Có | Không mã hóa theo mặc định | Local/self-managed không TLS |
| `neo4j+s://` | Có | TLS, xác minh chứng chỉ CA | Aura hoặc endpoint có certificate chain tin cậy |
| `neo4j+ssc://` | Có | TLS, chấp nhận chứng chỉ self-signed | Môi trường kiểm soát dùng self-signed certificate |
| `bolt://` | Không | Không mã hóa theo mặc định | Kết nối trực tiếp một server |
| `bolt+s://` | Không | TLS, xác minh chứng chỉ CA | Kết nối trực tiếp một server có CA certificate |
| `bolt+ssc://` | Không | TLS, chấp nhận self-signed certificate | Kết nối trực tiếp trong môi trường kiểm soát |

`neo4j://` tạo routing driver. Driver lấy routing table và chọn server phù hợp cho read/write transaction. `bolt://` tạo direct driver, gửi session tới đúng địa chỉ trong URI và không dùng routing table để phân phối transaction.

Nếu ứng dụng kết nối cluster, thông thường dùng `neo4j://` hoặc biến thể TLS tương ứng. Dùng `bolt://` tới một member có thể làm ứng dụng phụ thuộc vào member đó; khi member không khả dụng, Driver không tự chuyển sang member khác qua routing.

Không chọn scheme chỉ theo thói quen. Scheme phải khớp cấu hình Bolt/TLS mà DBA hoặc nền tảng cung cấp. Tài liệu Driver liệt kê các scheme và cách routing hoạt động tại [Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/).

## 4. Xác minh kết nối ngay khi khởi tạo Driver

Việc gọi `GraphDatabase.driver(...)` chủ yếu tạo đối tượng cấu hình và connection pool. Kết nối mạng có thể chỉ được thiết lập khi thực thi thao tác đầu tiên. Để phát hiện lỗi sớm, gọi `verifyConnectivity()`:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;

public class Neo4jConnectionCheck {

    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();
            System.out.println("Neo4j connectivity verified");
        }
    }
}
~~~

Ví dụ này kiểm tra Driver có thể kết nối tới DBMS với cấu hình và credentials đã cung cấp. Nó không thay thế việc kiểm tra database cụ thể mà SDN sẽ dùng. Sau khi xác minh kết nối, hãy mở session tới database ứng dụng và chạy query nhẹ.

Trong ứng dụng Spring Boot dùng SDN starter, không tạo một Driver mới cho mỗi request. Driver thread-safe, quản lý connection pool và nên được dùng như một bean dùng chung. Starter tự cấu hình Driver từ `spring.neo4j.*`; chỉ tạo cấu hình Driver riêng khi có yêu cầu rõ ràng.

## 5. Chẩn đoán lỗi TLS và chứng chỉ

Khi server yêu cầu TLS nhưng client dùng URI không mã hóa, handshake có thể thất bại. Ngược lại, dùng `neo4j+s://` với server không hỗ trợ TLS cũng có thể tạo lỗi handshake.

Các dấu hiệu thường gặp:

- `SSLHandshakeException`: TLS handshake không hoàn tất.
- `PKIX path building failed`: JVM không xây dựng được certificate chain tới CA tin cậy.
- `No subject alternative DNS name matching ...`: hostname trong URI không khớp SAN của certificate.
- `UntrustedServerException`: Driver không xác minh được server là Neo4j đáng tin cậy.
- `Connection reset` hoặc handshake failure: có thể do sai port, proxy, firewall hoặc server không nói TLS trên endpoint đó.

Kiểm tra theo thứ tự:

1. Xác nhận server Bolt có bật TLS hay không.
2. Chọn đúng `neo4j+s`, `neo4j+ssc`, `bolt+s` hoặc `bolt+ssc` theo endpoint.
3. Dùng hostname có trong Subject Alternative Name (SAN) của certificate; tránh thay bằng IP nếu certificate chỉ chứa DNS name.
4. Kiểm tra certificate còn hạn và chain có intermediate/root CA cần thiết.
5. Xác nhận JVM trust store có CA phù hợp hoặc cấu hình trust strategy theo hướng dẫn của Driver.
6. Nếu certificate vừa được thay, xác nhận ứng dụng/container đang dùng trust store mới và đã restart khi cần.

`+s` dành cho certificate được CA tin cậy ký và xác minh đầy đủ. `+ssc` cho phép dùng self-signed certificate, phù hợp với môi trường kiểm soát. Không chuyển sang `+ssc` chỉ để che lỗi certificate trong production; hãy cài certificate chain đúng và dùng hostname khớp certificate.

Có thể xem certificate được server trình bày bằng:

~~~bash
openssl s_client -connect graph.example.com:7687 -servername graph.example.com
~~~

Lệnh này hỗ trợ quan sát handshake và certificate chain. Nó không thay thế kiểm tra bằng chính Java Driver, vì JVM có trust store, provider và cấu hình TLS riêng.

Không bật trust-all certificate hoặc tắt hostname verification như một cách sửa lỗi lâu dài. Những cấu hình đó làm yếu khả năng xác minh server và có thể khiến ứng dụng kết nối tới endpoint giả mạo.

## 6. Phân biệt lỗi TLS với lỗi xác thực

TLS xác minh và bảo vệ kênh kết nối. Authentication xác minh danh tính user sau khi kênh đã được thiết lập. Hai lớp này độc lập:

| Tình huống | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Certificate không được tin cậy | `SSLHandshakeException`, `PKIX path building failed` | Sửa CA chain/trust store và URI scheme |
| Hostname certificate không khớp | Lỗi SAN/hostname verification | Dùng hostname đúng hoặc cấp certificate có SAN phù hợp |
| Server yêu cầu TLS nhưng client dùng URI không TLS | Handshake/connection reset | Chọn scheme TLS đúng |
| TLS thành công nhưng username/password sai | `AuthenticationException` | Kiểm tra secret, username, password và auth provider |
| Authentication thành công nhưng thiếu quyền | `SecurityException` hoặc lỗi authorization khi query | Cấp privilege đúng database/graph |

Đừng đổi password để xử lý `PKIX path building failed`; cũng đừng đổi certificate để xử lý `AuthenticationException`. Xác định lớp lỗi trước khi thay đổi cấu hình.

## 7. Xử lý AuthenticationException và credential sai

`AuthenticationException` cho biết Driver không xác thực được với thông tin đăng nhập cung cấp. Nguyên nhân thường gặp:

- Username hoặc password không đúng.
- Secret trong environment khác với secret đã cập nhật trên Neo4j.
- Deployment chưa reload secret mới.
- Ứng dụng trỏ nhầm Neo4j instance hoặc môi trường.
- Tài khoản bị khóa hoặc cơ chế xác thực ngoài như LDAP/SSO gặp lỗi.
- User đang ở trạng thái cần đổi password nhưng ứng dụng không xử lý quy trình đó.

Kiểm tra:

1. Xác nhận `spring.neo4j.uri` trỏ tới đúng DBMS.
2. Xác nhận username chính xác, không có khoảng trắng thừa.
3. Kiểm tra secret manager/environment variable tại runtime, không chỉ giá trị trong file local.
4. Thử đăng nhập bằng `cypher-shell` tới cùng endpoint và cùng user.
5. Nếu password đã rotate, cập nhật secret và khởi động lại hoặc refresh cấu hình theo cơ chế triển khai.
6. Kiểm tra trạng thái user bằng tài khoản quản trị nếu nghi ngờ user bị khóa hoặc cần đổi password.

Ví dụ kiểm tra bằng Cypher Shell; lệnh sẽ hỏi password:

~~~bash
cypher-shell -a neo4j+s://graph.example.com:7687 -u app_user -d appdb
~~~

Không truyền password trực tiếp trong command line hoặc ghi nó vào script/log. Command line có thể được lưu trong shell history hoặc hiển thị trong process list.

`AuthorizationExpiredException` hoặc `TokenExpiredException` khác với password sai ban đầu: thông tin xác thực đang dùng có thể đã hết hạn hoặc bị thu hồi. Nếu ứng dụng dùng token manager, kiểm tra luồng cấp mới token và hành vi refresh; không chỉ retry liên tục cùng một token hết hạn.

## 8. Phân biệt authentication với authorization

Authentication trả lời “bạn là ai?”. Authorization trả lời “bạn được phép làm gì?”.

Một user có thể đăng nhập thành công nhưng vẫn không truy cập được database hoặc không có quyền chạy query:

- Không có `ACCESS` trên database đích.
- Thiếu quyền `MATCH`/`READ` cho node hoặc relationship.
- Thiếu quyền `CREATE`, `SET PROPERTY` hoặc `DELETE` khi ghi.
- Role được cấp trên graph/database khác với database SDN đang dùng.

Các lỗi quyền thường xuất hiện khi query hoặc mở session vào database đích. Kiểm tra role và privilege bằng tài khoản quản trị; không cấp quyền quản trị toàn DBMS cho runtime user để làm cho lỗi biến mất.

## 9. Chẩn đoán lỗi routing trong cluster

Với `neo4j://`, Driver kết nối tới một routing entry point, nhận routing table rồi dùng các địa chỉ trong bảng để gửi read/write transaction tới các thành viên phù hợp. Vì vậy, việc chỉ ping được địa chỉ ban đầu chưa chứng minh toàn bộ cluster có thể được truy cập từ ứng dụng.

Các nguyên nhân thường gặp:

- Hostname trong routing table không phân giải được từ application container/pod.
- Firewall chỉ mở cổng tới entry point, không mở tới các địa chỉ member được quảng bá.
- Neo4j advertised addresses dùng hostname nội bộ mà client không thể truy cập.
- DNS trả địa chỉ khác nhau giữa laptop, container và production network.
- Cluster đang thay đổi topology hoặc database chưa online.
- Dùng `bolt://` direct URI trong khi cần routing/failover.

`DiscoveryException` cho biết Driver gặp vấn đề khi lấy routing table; lỗi này có thể tạm thời khi cluster đang thay đổi cấu trúc. Nếu không lấy được routing table hợp lệ từ các routing server, Driver có thể kết thúc bằng `ServiceUnavailableException`. `FatalDiscoveryException` có thể xuất hiện khi không thể lấy routing table cho database được yêu cầu, chẳng hạn database không tồn tại.

Kiểm tra:

1. Dùng `neo4j://` hoặc `neo4j+s://` nếu ứng dụng cần routing.
2. Xác nhận seed host và Bolt port có thể truy cập.
3. Từ chính môi trường ứng dụng, phân giải DNS và mở TCP tới các địa chỉ member được quảng bá.
4. Kiểm tra `server.bolt.advertised_address` và cấu hình routing/advertised address trên Neo4j theo topology.
5. Kiểm tra firewall/security group/network policy cho tất cả member cần thiết.
6. Xác nhận database đích đang online và có trong DBMS.

Driver có custom address resolver để ánh xạ địa chỉ cluster khi DNS hoặc advertised address không phù hợp với mạng client. Chỉ dùng resolver sau khi đã hiểu topology và các địa chỉ thật sự cần truy cập; resolver không thể sửa một cluster member đang offline hoặc một firewall chặn kết nối.

## 10. Kiểm tra database name và database state

Từ Neo4j 4, một DBMS có thể chứa nhiều database. URI kết nối tới DBMS; database được chọn riêng cho session. SDN hỗ trợ cấu hình database tĩnh:

~~~yaml
spring:
  data:
    neo4j:
      database: appdb
~~~

Hoặc chọn động bằng `DatabaseSelectionProvider` trong ứng dụng imperative và `ReactiveDatabaseSelectionProvider` trong ứng dụng reactive. Nếu không cấu hình database selection, session sẽ dùng database mặc định theo user/DBMS.

Các lỗi có thể gặp:

- Database name gõ sai chữ hoặc khác tên thật.
- Database chưa được tạo.
- Database đang `offline`, `quarantined` hoặc chưa sẵn sàng.
- User không có quyền `ACCESS` trên database.
- Database selection provider trả tên tenant không hợp lệ.
- Ứng dụng chạy nhầm profile nên dùng database của môi trường khác.

SDN không tự tạo database mới. Tạo database bằng công cụ quản trị hoặc migration/infra script trước khi ứng dụng sử dụng nó.

Tài khoản quản trị có thể kiểm tra:

~~~cypher
SHOW DATABASES;
~~~

Kiểm tra trực tiếp database ứng dụng bằng Cypher Shell:

~~~bash
cypher-shell -a neo4j+s://graph.example.com:7687 -u app_user -d appdb
~~~

Nếu session mặc định thành công nhưng session `appdb` thất bại, hãy kiểm tra tên database, trạng thái và quyền `ACCESS` của user trên `appdb`.

## 11. Kiểm tra database selection động

Trong ứng dụng multi-tenant, provider có thể chọn database theo tenant hoặc security context. Lỗi thường phát sinh khi tenant key không khớp database thật, request không có tenant context hoặc provider trả về giá trị khác dự kiến.

Ví dụ imperative provider tĩnh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

@Configuration
public class Neo4jDatabaseConfiguration {

    @Bean
    DatabaseSelectionProvider databaseSelectionProvider() {
        return DatabaseSelectionProvider
            .createStaticDatabaseSelectionProvider("appdb");
    }
}
~~~

Với provider động, ghi log database selection đã chọn ở mức phù hợp, không ghi dữ liệu nhạy cảm của tenant. Xác nhận lựa chọn được thực hiện đúng ở đầu mỗi transaction và không thay đổi giữa các thao tác cần cùng database. Không lấy database name trực tiếp từ request mà không kiểm tra allowlist hoặc ánh xạ tenant đã được kiểm soát.

## 12. Dùng query probe để tách lỗi kết nối và lỗi database

Sau khi `verifyConnectivity()` thành công, hãy mở session tới database mà SDN sử dụng và chạy một query nhẹ:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public class Neo4jDatabaseProbe {

    private final Driver driver;

    public Neo4jDatabaseProbe(Driver driver) {
        this.driver = driver;
    }

    public void verifyDatabase(String database) {
        try (var session = driver.session(
                SessionConfig.builder()
                    .withDatabase(database)
                    .build())) {
            session.run("RETURN 1 AS probe").single();
        }
    }
}
~~~

`verifyConnectivity()` kiểm tra khả năng kết nối tới DBMS; probe có `withDatabase(database)` kiểm tra thêm việc mở session và chạy query trên database được chỉ định. `RETURN 1` không xác nhận mọi quyền đọc/ghi graph của repository. Nếu cần kiểm tra privilege nghiệp vụ, chạy query đại diện read-only với cùng user.

## 13. Bảng đối chiếu lỗi và nguyên nhân

| Lỗi/dấu hiệu | Lớp có khả năng gặp vấn đề | Kiểm tra đầu tiên |
|---|---|---|
| `UnknownHostException` | DNS/host | Hostname, DNS trong container/pod |
| `ConnectException: Connection refused` | TCP/port/listener | Bolt port, service, firewall, port mapping |
| Connect timeout | Network/routing | Route, firewall, advertised addresses |
| `SSLHandshakeException` | TLS | URI scheme, certificate, TLS config |
| `PKIX path building failed` | Certificate trust | CA chain và JVM trust store |
| Hostname/SAN mismatch | Certificate identity | Hostname trong URI so với SAN |
| `AuthenticationException` | Authentication | Username, password, secret rotation |
| `AuthorizationExpiredException`/`TokenExpiredException` | Token lifecycle | Token expiry và refresh |
| `SecurityException` khi query | Authorization/security | ACCESS và graph privileges |
| `DiscoveryException` | Routing table | Seed host, routing addresses, cluster topology |
| `ServiceUnavailableException` | Connectivity/cluster | Member availability, network, routing table |
| `FatalDiscoveryException` | Routing/database selection | Database name và routing table cho database |
| Database not found | Database selection | `spring.data.neo4j.database`, `SHOW DATABASES` |
| Repository chạy được nhưng health DOWN | Health indicator chọn database khác | Default database của user và database SDN |

Đọc exception gốc nằm bên trong Spring `DataAccessException` hoặc exception wrapper nếu SDN chuyển đổi lỗi. Giữ lại Neo4j error code, exception type và root cause khi ghi log; không ghi credential hoặc token.

## 14. Bật logging và quan sát đúng mức

Trong môi trường development/staging, có thể tăng log Driver để quan sát kết nối và routing:

~~~yaml
logging:
  level:
    org.neo4j.driver: DEBUG
~~~

Tên logger và mức log hữu ích có thể thay đổi theo phiên bản Driver. Chỉ bật trong thời gian điều tra, giới hạn output và kiểm tra log trước khi chia sẻ. Không để password, auth token, certificate private key hoặc thông tin nhạy cảm trong log.

Ngoài log ứng dụng, đối chiếu:

- Neo4j Bolt connector có đang listen đúng host/port không.
- Neo4j server log có lỗi TLS, authentication hoặc database state không.
- DNS và TCP từ môi trường ứng dụng tới seed host/member.
- Trạng thái database bằng `SHOW DATABASES`.
- Thời điểm secret/certificate được rotate so với lúc lỗi bắt đầu.

Một lần lỗi routing ngắn trong lúc cluster thay đổi topology có thể tự phục hồi. Nếu lỗi lặp lại, hãy kiểm tra advertised addresses, network và member health thay vì chỉ tăng retry hoặc timeout.

## 15. Quy trình chẩn đoán theo thứ tự

1. Xác nhận Spring profile và giá trị `spring.neo4j.uri` tại runtime.
2. Xác nhận URI dùng đúng scheme, hostname và Bolt port.
3. Kiểm tra DNS và TCP port 7687 từ chính container/pod/host chạy ứng dụng.
4. Kiểm tra TLS scheme, certificate chain, hostname SAN và JVM trust store.
5. Xác minh username/password hoặc token; kiểm tra secret rotation.
6. Gọi `Driver.verifyConnectivity()` để tách lỗi kết nối DBMS.
7. Nếu dùng cluster, xác nhận routing scheme và mọi advertised address đều truy cập được.
8. Xác nhận database được cấu hình tồn tại, online và đúng tên.
9. Mở session tới database đích và chạy `RETURN 1`.
10. Kiểm tra `ACCESS` và graph privileges nếu query nghiệp vụ vẫn bị từ chối.
11. Đối chiếu root cause, Neo4j error code và server log; chỉ thay đổi một lớp cấu hình mỗi lần.

## 16. Những lỗi xử lý thường gặp

| Cách xử lý sai | Vì sao không hiệu quả | Cách xử lý đúng |
|---|---|---|
| Dùng cổng `7474` cho Java Driver | Đây thường là HTTP endpoint, không phải Bolt | Dùng Bolt port đang cấu hình, thường là `7687` |
| Dùng `bolt://` cho cluster rồi mong driver routing | Direct driver không lấy routing table | Dùng `neo4j://` hoặc `neo4j+s://` |
| Dùng `neo4j+s://` cho certificate không được CA tin cậy | Certificate verification thất bại | Cài CA chain đúng; chỉ dùng self-signed scheme trong môi trường kiểm soát |
| Dùng `+ssc` để bỏ qua lỗi certificate ở production | Làm yếu xác minh danh tính server | Cấp certificate hợp lệ và hostname đúng |
| Đổi password khi lỗi PKIX | PKIX là lỗi trust chain, không phải credential | Sửa CA/trust store và URI scheme |
| Tạo Driver mỗi request | Tạo connection pool lặp lại, tốn tài nguyên | Dùng Driver singleton do Spring quản lý |
| Chỉ kiểm tra seed host trong cluster | Member trong routing table vẫn có thể không truy cập được | Kiểm tra DNS/firewall tới các advertised address |
| Nghĩ `spring.data.neo4j.database` tự tạo database | SDN chỉ chọn database đã tồn tại | Tạo database bằng công cụ quản trị/migration |
| Cấp quyền admin để sửa lỗi ACCESS | Runtime user có đặc quyền vượt nhu cầu | Cấp `ACCESS` và graph privilege tối thiểu |
| Retry vô hạn với password/token sai | Lỗi cấu hình không tự hết | Sửa credentials hoặc refresh token |
| Chỉ gọi `verifyConnectivity()` rồi kết luận repository sẽ chạy | Chưa xác nhận database selection và graph privileges | Probe database đích và query read-only đại diện |

## 17. Tự kiểm tra

1. Vì sao tạo `Driver` thành công chưa chứng minh Neo4j đã kết nối được?
2. Khác biệt giữa `neo4j://` và `bolt://` là gì?
3. `neo4j+s://` và `neo4j+ssc://` khác nhau ở yêu cầu trust certificate nào?
4. Vì sao không nên dùng `+ssc` như cách sửa nhanh lỗi TLS production?
5. `AuthenticationException` khác lỗi authorization như thế nào?
6. Vì sao routing driver cần truy cập được các advertised address của cluster?
7. `DiscoveryException` và `ServiceUnavailableException` gợi ý điều gì khi chẩn đoán?
8. Database được chọn bằng `spring.data.neo4j.database` có tự được tạo bởi SDN không?
9. `verifyConnectivity()` khác query probe với `SessionConfig.withDatabase(...)` như thế nào?
10. Vì sao không nên retry vô hạn khi credentials sai hoặc database name không tồn tại?

Khi SDN không kết nối được Neo4j, hãy xác định lỗi thuộc URI/network, TLS, authentication, routing hay database selection. Dùng đúng Bolt URI scheme, xác minh certificate và credentials, kiểm tra mọi routing address trong cluster, rồi probe database đích bằng một session tường minh. Giữ Driver dùng chung, không log secret và không dùng quyền quản trị hoặc trust-all làm cách né lỗi cấu hình.

Tài liệu tham khảo:

- [Spring Data Neo4j – Getting started and connection configuration](https://docs.spring.io/spring-data/neo4j/reference/getting-started.html)
- [Spring Data Neo4j FAQ – Multiple databases and database selection](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j Java Driver – Connection](https://neo4j.com/docs/java-manual/current/connect/)
- [Neo4j Java Driver – Advanced connection information](https://neo4j.com/docs/java-manual/current/connect-advanced/)
- [Neo4j Java Driver API – Exceptions](https://neo4j.com/docs/api/java-driver/current/org.neo4j.driver/org/neo4j/driver/exceptions/package-summary.html)
- [Neo4j Operations Manual – SSL framework](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/)
