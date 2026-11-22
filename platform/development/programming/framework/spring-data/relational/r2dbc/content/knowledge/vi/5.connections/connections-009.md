# Kiểm tra cấu hình theo môi trường và xử lý lỗi kết nối ban đầu

## 1. Vì sao cần kiểm tra cấu hình kết nối theo môi trường?

Một ứng dụng Spring Data R2DBC thường chạy ở nhiều môi trường: máy phát triển của lập trình viên, Docker Compose, môi trường kiểm thử, staging và production. Mỗi môi trường có thể dùng một hostname, port, database, tài khoản, mật khẩu hoặc yêu cầu TLS khác nhau. Nếu cấu hình bị gắn cứng vào source code, ứng dụng dễ kết nối nhầm database hoặc hoạt động trên máy này nhưng thất bại trên máy khác.

Mục tiêu của việc quản lý cấu hình là giữ phần logic truy cập dữ liệu ổn định, trong khi thông tin kết nối được cung cấp theo môi trường triển khai. Khi ứng dụng khởi động hoặc thực hiện truy vấn đầu tiên, cần có cách xác nhận:

- Ứng dụng đang dùng đúng Spring profile và đúng nguồn cấu hình.
- R2DBC URL trỏ đến đúng host, port và database.
- Driver R2DBC tương ứng đã có trên classpath.
- Database đang chạy và có thể nhận kết nối từ nơi ứng dụng thực thi.
- Username, password, quyền truy cập và yêu cầu TLS phù hợp.
- Connection pool và timeout được cấu hình trong giới hạn hợp lý.
- Lỗi kết nối được ghi nhận đủ thông tin để chẩn đoán mà không làm lộ secret.

Bài này tập trung vào quá trình kiểm tra và xử lý lỗi kết nối ban đầu của Spring Data R2DBC. Các ví dụ dùng PostgreSQL; khi dùng hệ quản trị khác, cần thay driver, URL scheme và tùy chọn kết nối tương ứng.

## 2. Các lớp cấu hình của Spring Data R2DBC

Trong một ứng dụng Spring Boot, kết nối R2DBC thường được tạo tự động từ cấu hình và driver có trên classpath. Các thuộc tính cơ bản gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| spring.r2dbc.url | URL xác định driver, host, port và database |
| spring.r2dbc.username | Tài khoản kết nối |
| spring.r2dbc.password | Mật khẩu kết nối |
| spring.r2dbc.properties | Các thuộc tính bổ sung dành cho driver |
| spring.r2dbc.pool.* | Cấu hình connection pool khi ứng dụng có thư viện pool tương thích |

Ví dụ cấu hình tối thiểu cho PostgreSQL:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/app
spring.r2dbc.username=app
spring.r2dbc.password=${DB_PASSWORD}
~~~

URL có dạng tổng quát:

~~~text
r2dbc:<driver>://<host>:<port>/<database>
~~~

Trong ví dụ:

- **r2dbc** là scheme của giao thức R2DBC.
- **postgresql** xác định driver PostgreSQL.
- **localhost** là hostname nhìn từ tiến trình Spring Boot.
- **5432** là port PostgreSQL.
- **app** là tên database.

R2DBC URL không phải JDBC URL. Ví dụ, URL JDBC PostgreSQL thường bắt đầu bằng **jdbc:postgresql:**, còn URL R2DBC bắt đầu bằng **r2dbc:postgresql:**. Đưa nhầm JDBC URL vào cấu hình R2DBC có thể khiến driver không nhận diện được URL.

Nên cấu hình username và password bằng thuộc tính riêng thay vì nhúng trực tiếp vào URL. Cách này giúp phân tách endpoint và credential, đồng thời giảm nguy cơ lộ mật khẩu khi log URL hoặc chia sẻ cấu hình.

## 3. Quản lý cấu hình theo Spring profile

### 3.1. Profile giúp tách cấu hình môi trường

Spring profile cho phép kích hoạt một tập cấu hình phù hợp với môi trường đang chạy. Có thể dùng file cấu hình riêng như:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-docker.yml
├── application-test.yml
└── application-prod.yml
~~~

File **application.yml** chứa cấu hình chung và các thuộc tính không phụ thuộc môi trường:

~~~yaml
spring:
  application:
    name: customer-service
  r2dbc:
    username: ${DB_USER:app}
    password: ${DB_PASSWORD}
~~~

File **application-local.yml** dành cho ứng dụng chạy trực tiếp trên máy phát triển:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/app
~~~

File **application-docker.yml** dành cho ứng dụng chạy trong cùng Docker Compose network với service database tên db:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db:5432/app
~~~

Khi chạy trên máy cá nhân, kích hoạt profile local:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
~~~

Khi chạy ứng dụng trong Docker Compose, có thể đặt biến môi trường:

~~~yaml
environment:
  SPRING_PROFILES_ACTIVE: docker
~~~

Tên profile phải khớp với hậu tố file cấu hình. Ví dụ profile docker làm Spring Boot nạp thêm application-docker.yml.

### 3.2. Phân biệt hostname theo vị trí chạy ứng dụng

Hostname được phân giải từ góc nhìn của tiến trình đang mở kết nối:

| Vị trí chạy Spring Boot | Hostname thường dùng | Ví dụ URL |
|---|---|---|
| Chạy trực tiếp trên máy phát triển, database publish port ra host | localhost | r2dbc:postgresql://localhost:5432/app |
| Chạy trong container cùng Compose network với service db | db | r2dbc:postgresql://db:5432/app |
| Chạy trong Kubernetes | Service DNS của database | Phụ thuộc namespace và Service |
| Chạy trên máy chủ khác | DNS hoặc IP có thể truy cập | Theo endpoint môi trường |

**localhost luôn có nghĩa là máy hoặc network namespace hiện tại.** Bên trong container ứng dụng, localhost trỏ về chính container ứng dụng, không trỏ về container PostgreSQL. Trong Compose network, service name là hostname phù hợp để các container giao tiếp.

Nếu ứng dụng chạy trên host nhưng PostgreSQL không publish port, localhost cũng không thể truy cập database chỉ vì container đang chạy. Cần kiểm tra port mapping hoặc dùng một đường mạng được thiết kế rõ ràng.

### 3.3. Không để profile production dùng nhầm cấu hình local

Không nên đặt profile local làm mặc định cho mọi môi trường triển khai. Cần chỉ định profile rõ ràng ở nơi chạy ứng dụng và xác nhận giá trị đó trong log khởi động. Cấu hình production nên được cung cấp bởi hệ thống triển khai hoặc secret manager, với quyền truy cập tối thiểu.

Tránh commit mật khẩu production vào application-prod.yml hoặc file compose. File cấu hình có thể chứa placeholder, còn giá trị thực được truyền qua secret hoặc biến môi trường ở runtime.

## 4. Externalized configuration và biến môi trường

Spring Boot hỗ trợ externalized configuration: cùng một artifact có thể nhận cấu hình từ file, biến môi trường, Java system properties hoặc tham số dòng lệnh. Nhờ đó, không cần build lại ứng dụng chỉ để đổi endpoint database.

Ví dụ application.yml dùng biến môi trường:

~~~yaml
spring:
  r2dbc:
    url: ${R2DBC_URL:r2dbc:postgresql://localhost:5432/app}
    username: ${DB_USER:app}
    password: ${DB_PASSWORD}
~~~

Các biểu thức có ý nghĩa:

- **${R2DBC_URL:...}** dùng R2DBC_URL nếu biến đã được cung cấp; nếu không, dùng URL local mặc định.
- **${DB_USER:app}** dùng DB_USER hoặc fallback là app.
- **${DB_PASSWORD}** yêu cầu DB_PASSWORD được cung cấp; nếu thiếu, việc phân giải placeholder sẽ thất bại khi cấu hình được nạp.

Có thể dùng tên biến môi trường theo dạng relaxed binding của Spring Boot:

| Property | Environment variable |
|---|---|
| spring.r2dbc.url | SPRING_R2DBC_URL |
| spring.r2dbc.username | SPRING_R2DBC_USERNAME |
| spring.r2dbc.password | SPRING_R2DBC_PASSWORD |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |

Ví dụ chạy JAR với biến môi trường trên Linux hoặc macOS:

~~~bash
SPRING_PROFILES_ACTIVE=local \
SPRING_R2DBC_URL=r2dbc:postgresql://localhost:5432/app \
SPRING_R2DBC_USERNAME=app \
SPRING_R2DBC_PASSWORD=local-password \
java -jar app.jar
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SPRING_R2DBC_URL = "r2dbc:postgresql://localhost:5432/app"
$env:SPRING_R2DBC_USERNAME = "app"
$env:SPRING_R2DBC_PASSWORD = "local-password"
java -jar app.jar
~~~

Giá trị từ biến môi trường, system property hoặc command-line argument có thể ghi đè giá trị trong file cấu hình theo thứ tự ưu tiên của Spring Boot. Vì vậy, khi URL trong application.yml trông đúng nhưng ứng dụng vẫn kết nối sai host, cần kiểm tra biến môi trường, tham số chạy IDE, cấu hình của container và profile đang active. Đừng chỉ nhìn một file YAML rồi kết luận đó là giá trị cuối cùng.

### 4.1. File .env của Docker Compose không tự cấu hình tiến trình Java trên host

Docker Compose đọc file **.env** để nội suy giá trị trong compose.yaml. Việc có file này không có nghĩa một tiến trình Java chạy trực tiếp bằng IDE cũng tự nhận các biến đó.

Ví dụ, Compose có thể dùng:

~~~dotenv
DB_NAME=app
DB_USER=app
DB_PASSWORD=local-dev-password
~~~

Và truyền biến vào container:

~~~yaml
services:
  app:
    environment:
      SPRING_R2DBC_URL: r2dbc:postgresql://db:5432/${DB_NAME:-app}
      SPRING_R2DBC_USERNAME: ${DB_USER:-app}
      SPRING_R2DBC_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD}
~~~

Nếu chạy ứng dụng từ IntelliJ IDEA, Eclipse hoặc terminal trên host, cần cấu hình environment variables riêng trong Run Configuration hoặc shell. Đây là nguyên nhân phổ biến khiến ứng dụng trong container kết nối được nhưng ứng dụng chạy từ IDE lại báo thiếu password hoặc dùng sai URL.

### 4.2. Kiểm tra cấu hình đã được nạp

Có thể xác nhận profile active qua log khởi động của Spring Boot. Khi cần, dùng Actuator hoặc cơ chế chẩn đoán nội bộ để kiểm tra property đã resolve, nhưng phải bảo vệ endpoint và không trả password ra ngoài.

Không nên in toàn bộ environment variables, application properties hoặc connection URL có chứa credential vào log. Khi ghi log cấu hình để chẩn đoán, chỉ ghi những trường không nhạy cảm như profile, driver, hostname, port và tên database; che username nếu chính sách yêu cầu và tuyệt đối không ghi password.

## 5. Xác nhận dependency và R2DBC driver

Có URL đúng vẫn chưa đủ. Driver tương ứng phải có trên runtime classpath. Với PostgreSQL, dependency Gradle thường có dạng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

Spring Boot dependency management nên quản lý phiên bản tương thích giữa Spring Data, Spring Framework, Reactor và driver. Tránh tự chọn các phiên bản rời rạc nếu chưa kiểm tra compatibility matrix.

Nếu dùng MySQL, cần thay bằng R2DBC driver MySQL phù hợp và URL scheme tương ứng. Không thể dùng PostgreSQL driver để kết nối MySQL chỉ bằng cách thay hostname.

Một số dấu hiệu thiếu hoặc sai driver:

- Lỗi cho biết không tìm được driver phù hợp với URL.
- ConnectionFactory không được tạo hoặc không có bean ConnectionFactory.
- Ứng dụng báo không có ConnectionFactory khi tạo repository hoặc DatabaseClient.
- URL dùng scheme JDBC trong khi ứng dụng yêu cầu R2DBC.

Kiểm tra dependency runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows nếu dùng Gradle Wrapper:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Tìm driver R2DBC của database đang sử dụng trong kết quả. Nếu dependency chỉ nằm trong test runtime hoặc bị exclude khỏi runtimeClasspath, ứng dụng đóng gói có thể không kết nối được dù test chạy trong IDE.

## 6. Quy trình kiểm tra kết nối theo từng lớp

Khi kết nối thất bại, nên kiểm tra từ lớp ngoài vào trong. Mỗi bước xác nhận một giả thuyết cụ thể và giúp thu hẹp phạm vi lỗi.

~~~text
Cấu hình ứng dụng
       |
       v
Đúng profile và property đã resolve?
       |
       v
Đúng R2DBC driver và URL scheme?
       |
       v
Hostname phân giải được?
       |
       v
Port có thể truy cập?
       |
       v
Database đang chạy và nhận kết nối?
       |
       v
Database / username / password hợp lệ?
       |
       v
TLS, quyền và tùy chọn driver phù hợp?
       |
       v
ConnectionFactory / pool hoạt động?
       |
       v
Truy vấn SELECT 1 thành công
~~~

### 6.1. Kiểm tra ứng dụng đang dùng cấu hình nào

Xác nhận:

- Profile đang active có đúng môi trường không?
- R2DBC URL được lấy từ file nào hoặc biến môi trường nào?
- Có tham số chạy trong IDE ghi đè URL không?
- Container app có nhận được các biến SPRING_R2DBC_* không?
- Tên database, user và port có khớp với database đã tạo không?

Đặc biệt, so sánh hostname với vị trí chạy ứng dụng. localhost và tên service Compose không thể thay thế cho nhau tùy ý.

### 6.2. Kiểm tra DNS và network

Nếu dùng hostname như **db**, kiểm tra ứng dụng có nằm trong cùng network và có phân giải được tên đó hay không. Có thể mở shell trong container app để kiểm tra:

~~~bash
docker compose exec app sh
~~~

Tùy image có cài công cụ hay không, có thể dùng **getent hosts db**, **nslookup db** hoặc **ping db**. Không phải image production nào cũng có sẵn các tiện ích này. Ping thất bại cũng chưa đủ kết luận database không truy cập được vì ICMP có thể bị chặn.

Nếu ứng dụng chạy trên host, kiểm tra cổng được publish. Trên PowerShell:

~~~powershell
Test-NetConnection localhost -Port 5432
~~~

Trên Linux có thể dùng:

~~~bash
nc -vz localhost 5432
~~~

Kết quả kiểm tra port chỉ xác nhận đường TCP có thể mở; nó chưa xác nhận database, tài khoản hay quyền truy cập đúng.

### 6.3. Kiểm tra database bằng client độc lập

Với PostgreSQL chạy trong Compose, thử kết nối ngay bên trong container:

~~~bash
docker compose exec db pg_isready -U app -d app
docker compose exec db psql -U app -d app -c "SELECT 1;"
~~~

Nếu psql trong container cũng không kết nối được, cần xem trạng thái và log database trước khi điều tra Spring. Nếu psql chạy được trong container nhưng ứng dụng trên host không kết nối được, tập trung vào port mapping, firewall và hostname. Nếu psql từ host chạy được nhưng Spring thất bại, tập trung vào URL, driver, credential, TLS và cấu hình runtime.

Khi kiểm tra bằng psql từ host, dùng đúng hostname và port mà ứng dụng dự kiến sử dụng:

~~~bash
psql "host=localhost port=5432 dbname=app user=app" -c "SELECT 1;"
~~~

Lệnh này có thể hỏi password tùy cấu hình. Không nên truyền password trực tiếp trong command line vì nó có thể xuất hiện trong process list hoặc lịch sử shell.

### 6.4. Kiểm tra bằng DatabaseClient

Sau khi các lớp network và xác thực đã được xác nhận, có thể thực hiện truy vấn đơn giản qua chính Spring Data R2DBC để kiểm tra đường kết nối của ứng dụng.

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DatabaseConnectionProbe {

    private final DatabaseClient databaseClient;

    public DatabaseConnectionProbe(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Integer> checkConnection() {
        return databaseClient.sql("SELECT 1 AS value")
                .map((row, metadata) -> row.get("value", Integer.class))
                .one();
    }
}
~~~

Phương thức trả về **Mono<Integer>**. Truy vấn chỉ thực thi khi publisher được subscribe. Có thể dùng nó trong một bài kiểm thử tích hợp để xác nhận ứng dụng kết nối được bằng đúng cấu hình đang nạp.

~~~java
@SpringBootTest
class DatabaseConnectionTest {

    @Autowired
    DatabaseConnectionProbe probe;

    @Test
    void shouldConnectToDatabase() {
        StepVerifier.create(probe.checkConnection())
                .expectNext(1)
                .verifyComplete();
    }
}
~~~

Test cần database thực tế hoặc Testcontainers và cấu hình test phù hợp. Không nên biến truy vấn kiểm tra thành một tác vụ tự subscribe rời rạc trong service nghiệp vụ. Để kiểm tra ở môi trường vận hành, ưu tiên health indicator đã được framework tích hợp hoặc một cơ chế readiness có kiểm soát.

## 7. Những lỗi kết nối ban đầu thường gặp

| Dấu hiệu / thông báo | Nguyên nhân thường gặp | Hướng kiểm tra và xử lý |
|---|---|---|
| Không tìm thấy driver hoặc không tạo được ConnectionFactory | Thiếu R2DBC driver, URL dùng sai scheme hoặc dependency không có ở runtime | Kiểm tra runtimeClasspath, URL phải dùng scheme R2DBC và driver đúng database |
| Connection refused | Database chưa chạy, sai port, port chưa publish hoặc tiến trình chỉ bind ở địa chỉ khác | Kiểm tra container, healthcheck, port mapping và thử kết nối TCP |
| UnknownHostException hoặc host không phân giải được | Sai hostname, app và database không cùng network hoặc DNS chưa sẵn sàng | Dùng service name trong cùng Compose network; kiểm tra DNS và network |
| Connection timed out | Firewall, route mạng, endpoint sai, database không phản hồi hoặc pool đang chờ lâu | Kiểm tra network, security group, database load và thời gian chờ lấy connection |
| password authentication failed | Sai user/password hoặc volume được khởi tạo với credential cũ | Xác nhận credential runtime; đổi password trong database nếu cần giữ dữ liệu |
| database does not exist | Tên database sai hoặc database chưa được tạo | Kiểm tra tên database và quá trình bootstrap |
| SSL / TLS handshake failed | Client và server không thống nhất chế độ TLS, certificate hoặc trust chain | Kiểm tra tùy chọn SSL của driver, CA và chứng thư của môi trường |
| too many connections | Tổng kết nối từ app và các client vượt giới hạn database | Kiểm tra pool max-size, số instance và giới hạn kết nối server |
| Connection validation failed | Connection trong pool đã stale hoặc server đóng connection | Kiểm tra max-idle-time, max-life-time, validation và timeout |
| Ứng dụng khởi động được nhưng truy vấn đầu tiên thất bại | Kết nối được tạo lười hoặc chưa có truy vấn nào buộc mở connection | Thực hiện readiness check hoặc integration test có truy vấn thực tế |

Thông báo lỗi cụ thể thay đổi theo driver và phiên bản. Nên đọc cả exception gốc (root cause) và chuỗi exception lồng nhau thay vì chỉ nhìn dòng log đầu tiên từ Spring.

## 8. Xử lý một số nhóm lỗi cụ thể

### 8.1. Connection refused

Lỗi này thường xảy ra khi TCP client không mở được kết nối tới địa chỉ và port đã cấu hình. Các nguyên nhân điển hình:

- PostgreSQL container chưa chạy hoặc đang khởi tạo.
- Ứng dụng dùng sai port host.
- Database chỉ được expose trong Compose network nhưng app chạy trên host.
- App chạy trong container nhưng dùng localhost.
- Database chưa bind hoặc chưa lắng nghe trên interface cần thiết.

Kiểm tra lần lượt:

~~~bash
docker compose ps
docker compose logs --tail=100 db
docker compose port db 5432
~~~

Nếu app chạy trong Compose network, thử dùng service hostname và port nội bộ. Nếu app chạy trên host, dùng port đã publish. Với startup ordering, healthcheck và depends_on condition: service_healthy có thể giúp tránh kết nối quá sớm, nhưng ứng dụng vẫn cần xử lý database restart sau khi khởi động.

### 8.2. UnknownHostException

Lỗi phân giải hostname thường là dấu hiệu dùng sai DNS name hoặc môi trường network.

Ví dụ, URL **r2dbc:postgresql://db:5432/app** chỉ hợp lý khi tiến trình app có thể phân giải service name db trong Compose network. Nếu chạy từ IDE trên host, hệ điều hành thường không biết hostname db. Hãy dùng hostname được publish ra host, thường là localhost.

Ngược lại, URL localhost trong container app trỏ đến chính container app. Đổi URL theo profile hoặc biến môi trường phù hợp với nơi chạy.

### 8.3. Sai username hoặc password

Kiểm tra giá trị mà Spring thực sự nhận được, không chỉ giá trị trong file cấu hình. Biến môi trường trong IDE, secret của container hoặc tham số command line có thể ghi đè property trong YAML.

Với PostgreSQL image chính thức, POSTGRES_USER và POSTGRES_PASSWORD được dùng khi khởi tạo data directory ban đầu. Nếu named volume đã có dữ liệu, thay đổi các biến này không tự thay password của user đã tồn tại. Có thể cập nhật password bằng SQL khi đăng nhập bằng tài khoản đủ quyền:

~~~sql
ALTER USER app WITH PASSWORD 'new-local-password';
~~~

Sau đó cập nhật secret mà ứng dụng dùng. Không đưa password thật vào migration, source code hoặc log.

### 8.4. Database không tồn tại

Xác nhận tên database trong URL. Có thể liệt kê database bằng psql:

~~~sql
\l
~~~

Trong Docker Compose, biến POSTGRES_DB của image PostgreSQL chỉ tạo database mặc định khi khởi tạo data directory mới. Nếu volume đã tồn tại, đổi POSTGRES_DB không tự tạo database mới. Có thể tạo database bằng tài khoản có quyền phù hợp hoặc chạy quy trình bootstrap có kiểm soát.

### 8.5. TLS và chứng thư

Môi trường staging hoặc production có thể yêu cầu kết nối TLS. Không nên tắt xác thực chứng thư chỉ để làm cho kết nối chạy được. Cần kiểm tra:

- Server có yêu cầu TLS không?
- Driver đang dùng chế độ SSL nào?
- Client có trust CA của server không?
- Hostname có khớp với thông tin trong certificate không?
- Certificate còn hạn và chuỗi chứng thư có đầy đủ không?

Các thuộc tính SSL và cú pháp URL phụ thuộc driver. Hãy tham khảo tài liệu driver đúng phiên bản thay vì sao chép tùy chọn của JDBC driver sang R2DBC.

## 9. Kiểm tra connection pool và timeout

Non-blocking I/O không có nghĩa ứng dụng có thể tạo vô hạn kết nối. Database vẫn có giới hạn connection và tài nguyên. Nếu ứng dụng sử dụng R2DBC pool, cần cân đối kích thước pool với số instance, workload và giới hạn của database.

Các thông số thường cần quan tâm:

| Thông số | Ý nghĩa |
|---|---|
| initial size | Số connection ban đầu được tạo trong pool |
| max size | Số connection tối đa trong pool |
| max idle time | Thời gian connection có thể nhàn rỗi trước khi bị loại bỏ |
| max life time | Tuổi thọ tối đa của connection |
| max acquire time | Thời gian tối đa chờ lấy connection từ pool |
| validation | Cơ chế kiểm tra connection còn dùng được hay không |

Tên property và khả năng hỗ trợ có thể thay đổi theo phiên bản Spring Boot và r2dbc-pool. Chỉ cấu hình những thuộc tính có trong phiên bản đang dùng và khi thư viện pool đã có trên runtime classpath.

Ví dụ cấu hình pool mang tính minh họa:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
~~~

Cấu hình này không phải giá trị khuyến nghị cho mọi ứng dụng. Pool max-size cần tính đến số replica ứng dụng. Ví dụ, nếu có 4 instance và mỗi instance có thể mở tối đa 10 connection, tổng số connection tiềm năng từ ứng dụng là 40, chưa tính migration job, admin tool và các client khác.

Nếu log cho thấy request chờ lấy connection lâu, cần phân biệt:

- Database chậm xử lý truy vấn.
- Pool đã dùng hết connection.
- Connection cũ cần được thay thế.
- Có transaction hoặc publisher giữ connection lâu hơn dự kiến.

Không nên chỉ tăng max-size khi gặp timeout. Nếu database đã gần giới hạn, tăng pool có thể làm tình hình xấu hơn. Cần quan sát số connection đang dùng, thời gian acquire, thời gian query và tải của server.

## 10. Phân biệt lỗi kết nối với lỗi trong reactive pipeline

Một ứng dụng có thể cấu hình kết nối đúng nhưng vẫn không thực hiện truy vấn vì publisher chưa được subscribe. Reactor dùng mô hình lazy: tạo **Mono** hoặc **Flux** thường chỉ mô tả công việc, chưa nhất thiết thực hiện I/O.

Ví dụ:

~~~java
Mono<Customer> customer = customerRepository.findById(42L);
~~~

Đoạn mã trên tạo publisher. Nếu không có thành phần nào subscribe hoặc framework không tiêu thụ publisher đó, truy vấn có thể chưa chạy. Trong WebFlux, framework subscribe vào publisher controller trả về. Trong test, StepVerifier subscribe khi bắt đầu xác minh.

Không nên gọi **block()** hoặc **subscribe()** tùy tiện chỉ để ép truy vấn chạy. Hãy trả publisher về tầng gọi hoặc dùng cơ chế kiểm tra phù hợp. Gọi block trên event-loop thread có thể làm nghẽn pipeline reactive.

Một dấu hiệu cần lưu ý là ứng dụng khởi động thành công nhưng truy vấn đầu tiên báo lỗi. Điều này có thể xảy ra vì connection được mở lười khi có thao tác dữ liệu đầu tiên. Khởi động thành công chỉ xác nhận application context được tạo, không nhất thiết chứng minh database đã được truy cập thành công.

## 11. Readiness, retry và khả năng phục hồi

### 11.1. Readiness khác với trạng thái process đang chạy

Process Java đang chạy không đồng nghĩa ứng dụng đã sẵn sàng phục vụ nghiệp vụ. Nếu API cần database để xử lý request, readiness nên phản ánh khả năng truy cập dependency cần thiết.

Spring Boot Actuator có thể cung cấp health indicator cho R2DBC khi dependency và auto-configuration phù hợp được bật. Có thể sử dụng health endpoint trong hệ thống triển khai, nhưng cần bảo vệ endpoint và tránh công khai chi tiết connection hoặc thông tin nội bộ.

Liveness và readiness phục vụ mục đích khác nhau:

- **Liveness** trả lời process có còn hoạt động hay cần được khởi động lại.
- **Readiness** trả lời instance có đủ điều kiện nhận request hay chưa.

Database tạm thời mất kết nối không phải lúc nào cũng có nghĩa process cần restart. Cách phản ứng phụ thuộc kiến trúc, khả năng reconnect và chính sách vận hành.

### 11.2. Retry cần giới hạn và phân loại lỗi

Có thể retry một số lỗi tạm thời như network interruption hoặc database đang restart. Tuy nhiên, retry không sửa được lỗi cấu hình cố định như sai password, sai hostname hoặc thiếu driver.

Khi thiết kế retry:

- Giới hạn số lần và tổng thời gian retry.
- Dùng backoff để tránh tạo một đợt kết nối dồn dập.
- Chỉ retry những lỗi được phân loại là tạm thời.
- Bảo đảm thao tác được retry là an toàn hoặc có tính idempotent.
- Theo dõi số lần retry và nguyên nhân thất bại.

Ví dụ minh họa một thao tác đọc có retry:

~~~java
return customerRepository.findById(customerId)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .filter(this::isTransientDatabaseError));
~~~

Phương thức **isTransientDatabaseError** cần được triển khai dựa trên loại exception thực tế của driver và chính sách của ứng dụng. Không retry mọi exception một cách mù quáng; lỗi validation, SQL sai hoặc authentication thường không tự biến mất sau vài lần thử.

## 12. Logging và quan sát lỗi mà không lộ thông tin nhạy cảm

Khi điều tra kết nối, log cần giúp xác định môi trường, endpoint và loại lỗi. Có thể ghi nhận:

- Profile đang active.
- Driver và phiên bản driver.
- Hostname, port và tên database nếu chính sách cho phép.
- Thời điểm xảy ra lỗi, request hoặc trace ID.
- Loại exception, SQL state nếu driver cung cấp.
- Thời gian chờ connection và thời gian thực thi query.

Không ghi password, token, connection URL có credential hoặc toàn bộ biến môi trường. Cũng không nên bật log bind parameter trên production nếu tham số có thể chứa dữ liệu cá nhân hoặc secret.

Có thể phân biệt lỗi khởi tạo ConnectionFactory, lỗi lấy connection từ pool, lỗi xác thực và lỗi thực thi SQL bằng cách đọc chuỗi cause của exception. Log message ở lớp ngoài thường chỉ nói rằng thao tác repository thất bại; root cause sâu hơn mới chứa thông tin về socket, DNS, authentication hoặc driver.

## 13. Checklist xử lý khi ứng dụng không kết nối được

Khi một môi trường mới không kết nối được database, có thể đi theo thứ tự sau:

1. **Profile:** xác nhận SPRING_PROFILES_ACTIVE và file cấu hình tương ứng.
2. **Property:** kiểm tra R2DBC URL, username và password đã resolve đúng; xem xét biến môi trường và tham số chạy có ghi đè file hay không.
3. **Driver:** xác nhận R2DBC driver của database có trong runtimeClasspath và URL dùng đúng scheme.
4. **Hostname:** dùng localhost từ host hoặc service DNS từ cùng container network.
5. **Port:** xác nhận database đang listen và port mapping/firewall cho phép kết nối.
6. **Database:** xác nhận database tồn tại và server đã sẵn sàng.
7. **Credential:** thử bằng client database độc lập với cùng host, port, database và user.
8. **TLS:** xác nhận chế độ SSL và trust chain theo yêu cầu môi trường.
9. **Pool:** kiểm tra pool dependency, giới hạn kết nối, acquire timeout và connection stale.
10. **Reactive execution:** bảo đảm publisher được tiêu thụ bởi framework hoặc subscriber hợp lệ.
11. **Readiness:** chạy một truy vấn kiểm tra qua chính ứng dụng hoặc health indicator.
12. **Observability:** đọc root cause và log có correlation ID; che toàn bộ secret trước khi chia sẻ.

Khi thay đổi một giá trị cấu hình, chỉ thay đổi một nhóm yếu tố mỗi lần và kiểm tra lại. Cách này giúp xác định nguyên nhân thực tế thay vì thay nhiều tham số cùng lúc rồi không biết yếu tố nào đã giải quyết vấn đề.

## 14. Kết luận

Kiểm tra cấu hình R2DBC theo môi trường là quá trình xác nhận đúng profile, property đã resolve, driver, URL, hostname, port, database, credential, TLS và connection pool. Các môi trường khác nhau thường cần endpoint khác nhau; đặc biệt, localhost trên host và localhost trong container có ý nghĩa khác nhau.

Khi gặp lỗi kết nối ban đầu, hãy chẩn đoán theo từng lớp từ cấu hình đến network, database, xác thực và truy vấn thực tế. Kiểm tra bằng client database độc lập giúp tách lỗi hạ tầng khỏi lỗi Spring; truy vấn đơn giản qua DatabaseClient hoặc health indicator xác nhận đường kết nối mà ứng dụng thực sự sử dụng. Kết hợp cấu hình externalized, secret được quản lý đúng cách, readiness và retry có giới hạn sẽ giúp ứng dụng Spring Data R2DBC dễ triển khai và vận hành hơn.

