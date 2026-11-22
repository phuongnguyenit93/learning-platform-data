# Container chưa sẵn sàng, sai mapped port hoặc mất kết nối

## 1. Tình huống: Testcontainers chạy nhưng Spring Boot không kết nối được

Một bài kiểm thử Spring Boot dùng PostgreSQL hoặc Redis qua Testcontainers có thể thất bại với những dấu hiệu rất khác nhau:

- `ContainerLaunchException` hoặc `Timed out waiting for container port to open` ngay lúc setup.
- Docker báo container đang `running` nhưng ứng dụng trả `Connection refused`.
- Ở máy developer truy cập `localhost:5432` thành công, còn CI không kết nối được.
- `IllegalStateException: Mapped port can only be obtained after the container is started`.
- Spring Boot khởi động thành công ở lớp test A, nhưng lớp test B dùng context đã cache lại nhận `Connection reset` hay `HikariPool ... connection is not available`.
- Cùng một container hoạt động khi chạy riêng một class, nhưng fail khi chạy parallel, chạy cả suite hoặc chuyển sang Docker-in-Docker.
- Log báo container đã tạo thành công nhưng database vẫn đang chạy init scripts, recovery hoặc migrations.

Các hiện tượng trên **không đồng nghĩa**. Muốn sửa đúng, phải tách bốn ranh giới:

1. **Docker availability**: JVM có giao tiếp được với Docker daemon, kéo image và tạo container không?
2. **Container lifecycle**: process trong container đã ở trạng thái running và dịch vụ thực sự ready chưa?
3. **Network addressing**: từ đúng tiến trình client, phải dùng host nào, **mapped port** nào, network alias nào?
4. **Spring context/client lifecycle**: DataSource, Redis client và cached ApplicationContext có còn trỏ đến container đang chạy, với thông tin kết nối cập nhật không?

Bài học này thuộc chủ đề **Chẩn đoán lỗi kiểm thử**; đề bài trực tiếp là **“Container chưa sẵn sàng, sai mapped port hoặc mất kết nối”**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt Docker container `created`, `running`, cổng đang `listening` và ứng dụng đã `ready`.
- Sử dụng Testcontainers `getHost()` và `getMappedPort(containerPort)` đúng **sau khi container khởi động**.
- Phân biệt **container port**, **host mapped port** và **port trên Docker network giữa containers**.
- Chọn `Wait.forListeningPort()`, `Wait.forHttp(...)`, `Wait.forLogMessage(...)` hoặc healthcheck theo tín hiệu sẵn sàng có nghĩa.
- Chẩn đoán `Connection refused`, timeout, DNS failure, TLS/authentication errors, connection reset và Hikari pool exhaustion.
- Dùng Spring Boot 3.5 `@ServiceConnection` với container quản lý bởi Spring để tránh lifecycle lệch với context cache.
- Dùng `@DynamicPropertySource` khi không có ServiceConnection, đồng thời hiểu thời điểm supplier được đánh giá.
- Thu thập Docker/Testcontainers logs đúng mức, không làm lộ passwords hoặc URLs chứa secrets.
- Phân biệt lỗi máy local với CI, Docker-in-Docker, remote daemon, rootless Docker và JVM forks.
- Viết mã Java 17+/Spring Boot 3.5 với PostgreSQL, Redis, JUnit Jupiter và các test kết nối thật.
- Thiết kế checklist triage để sửa **nguyên nhân**, không chỉ tăng timeout hoặc lặp lại test.

**Phiên bản của ví dụ chạy được:** Java 17+, Spring Boot **3.5.16**, Testcontainers **1.21.4** do Boot BOM quản lý, JUnit Jupiter và Gradle Groovy DSL. Các tài liệu Testcontainers trên website hiện hành có thể minh họa API và Maven coordinates cho **Testcontainers 2.x**; project mẫu này cố ý dùng tọa độ module **1.x** như `org.testcontainers:postgresql` và `org.testcontainers:junit-jupiter` theo Spring Boot 3.5.16. Không sao chép coordinates 2.x vào project 1.x mà không kiểm tra tương thích.

## 2. Mô hình hai mạng và hai loại cổng

Giả sử PostgreSQL bên trong container luôn nghe **5432**, Redis nghe **6379**, nhưng Testcontainers xuất các cổng đó ra **cổng ngẫu nhiên trên host**.

```text
       JUnit/Spring Boot test JVM
                 |
                 | JDBC URL / TCP request
                 v
       host = container.getHost()
       port = container.getMappedPort(5432)
                 |
                 v
   Docker host / host-side exposed endpoint
              port 49xxx
                 |
          Docker port mapping
                 |
                 v
       PostgreSQL container :5432
           (inside network)

       Other container on same Docker network
                 |
                 | database:5432
                 v
       Network alias "database"
       (internal port, no host mapping needed)
```

**Quy tắc chính:**

- `5432` là **container port**; dùng làm argument cho `getMappedPort(5432)`.
- Giá trị trả về, ví dụ `49182`, là **host mapped port**, được cấp lúc container start. **49182 chỉ là số minh họa, không phải stdout hay port mặc định.**
- `getHost()` cho biết host mà **JVM đang chạy test** nên kết nối tới; không luôn là `localhost` khi dùng remote Docker hoặc CI.
- `container.getJdbcUrl()` của `PostgreSQLContainer` đã chứa đúng địa chỉ và mapped port; thường nên ưu tiên API này thay vì tự ghép chuỗi JDBC.
- Một **container khác trên cùng Docker network** có thể kết nối tới tên alias và **internal port 5432**, không cần biết mapped host port.
- Nếu **ứng dụng Spring Boot cũng chạy trong container**, phải xét network từ vị trí ứng dụng; không được bê nguyên hostname/port phù hợp cho JVM test chạy ngoài host vào trong một container khác.

### 2.1. Sai lầm phổ biến: hardcode localhost:5432

```java
// SAI khi Testcontainers dùng mapped port ngẫu nhiên.
String jdbcUrl = "jdbc:postgresql://localhost:5432/testdb";
```

Nếu trên máy đang có PostgreSQL local ở 5432, test có thể vô tình kết nối **nhầm database** và vẫn xanh. CI không có database local sẽ báo Connection refused. Còn nếu 5432 được một service khác chiếm, test có thể trả dữ liệu đáng ngờ thay vì lỗi kết nối rõ.

Cách đúng cho PostgreSQLContainer:

```java
postgres.start();
String jdbcUrl = postgres.getJdbcUrl();
String username = postgres.getUsername();
String password = postgres.getPassword();
```

Đây là **snippet**: biến `postgres` phải là một PostgreSQLContainer đã cấu hình. Khi dùng Spring Boot `@ServiceConnection`, bạn thường không cần tự gọi `postgres.start()` hay tự set spring.datasource.url; container bean và JDBC connection details được Boot quản lý.

### 2.2. Sai lầm phổ biến: getMappedPort trước khi start

```java
GenericContainer<?> redis =
    new GenericContainer<>(
            DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379);

// Không gọi khi container chưa start:
int mappedPort = redis.getMappedPort(6379);
```

`getMappedPort` chỉ có ý nghĩa **sau startup**, khi Docker đã gán mapped port. Test có thể fail ngay với IllegalStateException, hoàn toàn **không phải** lỗi network của Redis.

Ở phần mã runnable có một JUnit unit test chuyên kiểm tra failure mode này, không cần Docker daemon.

## 3. Container running khác service ready

Một tiến trình bên trong container có thể đang chạy, nhưng vẫn bận:

- Giải nén hoặc khôi phục dữ liệu.
- Chạy PostgreSQL init scripts, tạo user/database.
- Đợi Kafka broker election/metadata.
- Chạy Redis loading snapshot.
- Áp dụng DB migrations.
- Khởi tạo TLS keys/certificates.
- Đợi một dependency khác hoặc healthcheck chuyển trạng thái healthy.
- Bind socket trước khi các API/query thật đã sẵn sàng.

Vì vậy:

| Trạng thái | Điều khẳng định được | Điều chưa khẳng định |
|---|---|---|
| Image pull thành công | Image khả dụng cho Docker | Container đã start |
| Container `created` | Docker đã tạo cấu hình container | Process đang chạy |
| Container `running` | Entry process còn sống | Service có thể phục vụ requests |
| TCP port `listening` | Có socket nhận kết nối | Authentication/queries/health API đã sẵn sàng |
| HTTP health 200 | Endpoint health báo healthy tại thời điểm đó | Mọi business dependency đều sẵn sàng |
| SQL `SELECT 1` thành công | DB server chấp nhận truy vấn thật | Migration/schema nghiệp vụ đã đúng |
| Test contract query thành công | Đường kiểm thử hiện tại dùng được | Mọi concurrency/failover case đã được kiểm tra |

### 3.1. Startup strategy khác wait strategy

Testcontainers phân biệt:

- **Startup check strategy**: container đã đạt trạng thái vòng đời mong muốn chưa (thường process running).
- **Wait strategy**: dịch vụ bên trong đã sẵn sàng cho mục đích test chưa.

Với `GenericContainer` có exposed ports, Testcontainers mặc định thường đợi **cổng đầu tiên được map** lắng nghe, timeout mặc định khoảng **60 giây**. Chỉ “port open” không đủ cho mọi ứng dụng. Đừng giải quyết sai bằng `Thread.sleep(30000)`: nó vừa chậm vừa vẫn flaky khi CI tải nặng.

### 3.2. Wait.forListeningPort

```java
GenericContainer<?> service =
    new GenericContainer<>(
            DockerImageName.parse("redis:7-alpine"))
        .withExposedPorts(6379)
        .waitingFor(Wait.forListeningPort());
```

Đây là **snippet** cần imports; phù hợp khi TCP listener là dấu hiệu readiness đủ cho mục tiêu. Với Redis hoặc một service cụ thể, vẫn nên có **lệnh kiểm tra ứng dụng thật** (ví dụ Redis PING) sau startup để chứng minh protocol phản hồi.

### 3.3. Wait.forHttp

Với một service HTTP có endpoint health thực:

```java
GenericContainer<?> api =
    new GenericContainer<>(
            DockerImageName.parse("example/your-api:1.0"))
        .withExposedPorts(8080)
        .waitingFor(
            Wait.forHttp("/actuator/health/readiness")
                .forPort(8080)
                .forStatusCode(200)
                .withStartupTimeout(
                    Duration.ofMinutes(2)));
```

**Snippet minh họa, không runnable độc lập** vì `example/your-api:1.0` chỉ là placeholder image để giải thích WaitStrategy. Hãy thay bằng image thật của ứng dụng, bảo đảm path tồn tại, actuator readiness endpoint thực sự được bật, security policy cho phép health check, và health 200 phản ánh dependency cần test.

Nếu endpoint cần TLS, có biến thể `usingTls()`. Với endpoint cần xác thực và trả HTTP 401 nhưng TCP đã thông, **đừng định nghĩa mọi 401 là “service unavailable”**; tùy mục tiêu, dùng một health endpoint phù hợp hoặc predicate status có chủ ý. Không tắt security production chỉ để health check pass.

### 3.4. Wait.forLogMessage

Một số image ghi một log line tương đối ổn định khi sẵn sàng:

```java
.waitingFor(Wait.forLogMessage(
    ".*Ready to accept connections.*\\n", 1))
```

Đây là **snippet**, pattern tùy Redis image/version. Log readiness có thể đổi theo phiên bản, bị lặp lại khi recovery hoặc xuất hiện trước khi TCP reachable. Với một DB dùng specialized Testcontainers module, **ưu tiên wait strategy chuyên biệt của module** thay vì tự thay bằng log/port-only wait yếu hơn.

### 3.5. Wait.forHealthcheck

```java
.waitingFor(Wait.forHealthcheck())
```

Chỉ phù hợp nếu image có Docker HEALTHCHECK đúng và status healthy đáng tin. Docker healthcheck của image không tự xác nhận schema/migrations nghiệp vụ.

### 3.6. Timeout phải gắn với nguyên nhân

Tăng startup timeout có cơ sở khi pull image lần đầu hoặc service thật cần startup lâu. Nhưng nếu URL trỏ sai host/port, đợi hai phút thay vì 60 giây không sửa được gì. Phân biệt timeout của:

- Kết nối Docker daemon.
- Image pull.
- Container startup/retry.
- WaitStrategy readiness.
- JDBC driver socket/connect.
- Hikari connection acquisition.
- HTTP client request.
- JUnit method/test runner.
- CI job wall-clock.

Hãy thu logs và metrics cho **giai đoạn nào đang timeout** rồi mới điều chỉnh ngưỡng.

## 4. Bảng phân loại triệu chứng → giả thuyết

| Lỗi trong log/test | Giả thuyết ưu tiên | Bằng chứng cần thu |
|---|---|---|
| `Could not find a valid Docker environment` | Docker daemon không truy cập được | `docker info`, quyền socket, Docker context |
| `ContainerLaunchException` | Image/container entrypoint/startup/wait fail | Docker logs, inspect state, wait strategy |
| `Mapped port can only be obtained after ... started` | Đọc port quá sớm | Thứ tự start/getMappedPort |
| `Connection refused` | Host:port không có listener reachable | host/mappedPort, container logs, Docker mapping |
| `UnknownHostException` | Sai DNS/alias hoặc sai network vantage point | getHost, network aliases, DNS resolver |
| `SocketTimeoutException: connect timed out` | Route/firewall/host không reachable hoặc service treo | CI network policy, Docker daemon host |
| `Read timed out` | Có kết nối nhưng service không trả response kịp | DB load/locks, endpoint readiness |
| `Connection reset by peer` | Service/container restart/close socket | Exit/restart logs, pool stale connections |
| `HikariPool ... Connection is not available` | Pool cạn hoặc database chết/treo | Active/idle pool, DB status, blocked queries |
| `password authentication failed` | Credentials sai nhưng network đã tới DB | getUsername/getPassword, Boot connection details |
| `database "... " does not exist` | DB name/init chưa đúng hoặc nhầm instance | current_database, getDatabaseName, init logs |
| `SSLHandshakeException` | TLS trust/cert/protocol mismatch | Cert chain, JDBC sslmode, hostname |
| `No route to host` | Docker network/host routing | Test process location, bridge/CI topology |
| Tests riêng pass, suite fail | Cache context dùng container đã stop; parallel/fork race | lifecycle, @Container/@ServiceConnection, @DirtiesContext |
| Test chỉ fail trên CI | Docker-in-Docker, remote host, resource limits | Docker info, mapped host, CPU/RAM, runner |
| JDBC ready nhưng migration lỗi | Service ready, schema chưa đúng | Flyway/Liquibase logs, migration state |

**Một lỗi có thể có nhiều nguyên nhân.** Đừng tự gán “network error” cho mọi exception có chữ `connection`. Authentication failure nghĩa là client đã trao đổi được ít nhất một phần protocol với server, còn connection refused thường chưa đạt được tầng SQL authentication.

## 5. Ba cách tích hợp container với Spring Boot

Spring Boot 3.5 cho nhiều cách làm; phải chọn có ý thức về **source của connection details** và **ai quản lý lifecycle**.

### 5.1. Cách A — Spring-managed container bean + @ServiceConnection

Ưu tiên khi nhiều Spring tests có thể reuse cached ApplicationContext:

```java
@TestConfiguration(proxyBeanMethods = false)
class DbTestConfiguration {
    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        return new PostgreSQLContainer<>(
            DockerImageName.parse("postgres:16-alpine"))
            .withDatabaseName("diagnostics");
    }
}
```

Đây là **snippet**; các file runnable đầy đủ ở phần 11. Spring Boot tạo/start container bean **trước những bean phụ thuộc**, tạo JDBC connection details, dừng container **sau khi các bean khác được destroy**. Container gắn với vòng đời cached ApplicationContext thay vì dừng sớm ngay khi JUnit test class kết thúc.

**Lợi ích:** Datasource và container sống cùng context; cache hit từ class khác không tự dùng DataSource trỏ tới một container đã bị JUnit extension stop.

### 5.2. Cách B — @Testcontainers + @Container + @ServiceConnection

```java
@Testcontainers
@SpringBootTest
class RepositoryWithContainerTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>(
            DockerImageName.parse("postgres:16-alpine"));
}
```

**Snippet riêng.** JUnit Testcontainers extension quản lý lifecycle: `static @Container` start một lần cho **test class** và stop sau class; instance `@Container` thường start/stop theo **method**. Nó thuận tiện nhưng Spring's TestContext cache có thể sống **lâu hơn test class**. Lớp B cùng cached context có thể reuse DataSource trỏ tới container của lớp A đã stop; đây là một nguồn flakiness rất thực.

Không kết luận mọi `static @Container` đều sai. Với test class độc lập, cache lifecycle được quản lý rõ, nó có thể phù hợp. Nhưng nếu cần context usable xuyên nhiều test classes, theo Spring Boot docs hãy ưu tiên **Spring-managed container bean** hoặc `@ImportTestcontainers`.

JUnit Testcontainers extension được tài liệu chính thức mô tả là **chưa được kiểm thử/hỗ trợ đầy đủ cho parallel execution**; không bật parallel vô điều kiện trên các test có @Container.

### 5.3. Cách C — @DynamicPropertySource

Khi công nghệ chưa có `@ServiceConnection` factory hoặc cần custom property mapping, dùng một static method:

```java
@DynamicPropertySource
static void connectionProperties(
        DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

**Snippet**, giả định biến static `postgres` có lifecycle được quản lý. Supplier API bảo đảm values được đọc động khi Spring yêu cầu, **không có nghĩa** nó sẽ tự start container hoặc tự tạo unique context key theo mỗi random port.

Nếu code viết:

```java
registry.add(
    "spring.datasource.url",
    () -> "jdbc:postgresql://localhost:5432/test");
```

thì việc dùng DynamicPropertySource không sửa được sai host/port. Phải lấy URL từ container đã start, hoặc dùng dynamic factory/connection detail phù hợp.

### 5.4. Đừng dùng song song hai nguồn connection settings không hiểu precedence

Spring Boot `@ServiceConnection` tạo `JdbcConnectionDetails`, và **connection details được ưu tiên hơn** các connection-related properties thông thường. Nếu bạn đồng thời đặt `spring.datasource.url=jdbc:postgresql://localhost:5432/...` và @ServiceConnection tới container, Hikari có thể dùng thông tin từ @ServiceConnection dù log Environment vẫn có URL literal. Khi debug, **kiểm tra DataSource thực sự kết nối đi đâu**, không chỉ đọc giá trị Environment.

Đối với `PostgreSQLContainer`, cùng một container có thể tạo nhiều connection details phù hợp, ví dụ JDBC/R2DBC. Nếu ứng dụng chỉ dùng JDBC, cấu hình type/bean phù hợp theo Spring Boot docs khi cần tránh ambiguities.

## 6. Sai mapped port: nhìn từ nơi phát sinh kết nối

### 6.1. JVM test chạy trên máy host

Đúng:

```java
String host = container.getHost();
int port = container.getMappedPort(6379);
String address = host + ":" + port;
```

Sai:

```java
String address = "localhost:6379";
```

**Hai đoạn là snippets.** Đúng khi container đã start và expose `6379`; getMappedPort(6379) khác getMappedPort(hostPort).

### 6.2. Client chạy trong một container khác

Các container cùng một Docker network có thể dùng alias và internal port:

```text
redis container:
  network alias: redis
  listens inside: 6379

application container:
  connects to redis:6379
```

Địa chỉ `redis:6379` trong ví dụ này chỉ có ý nghĩa nếu hai containers cùng network và alias `redis` được gán. Host JVM có thể **không resolve** `redis`. Ngược lại, inside application container, `localhost:6379` trỏ về **chính application container**, không phải Redis.

### 6.3. Container cần gọi service chạy trên host

Đây là chiều **container → host**, khác test JVM → container. Testcontainers có cơ chế expose host ports cho container, dùng host alias chuyên biệt `host.testcontainers.internal` khi cấu hình đúng. Đừng lấy `container.getHost()` từ host JVM rồi mặc định dùng địa chỉ đó từ một container khác. Với kịch bản này xem tài liệu `Testcontainers.exposeHostPorts(...)` và gọi setup **trước khi start container** cần kết nối tới host.

### 6.4. Remote daemon, Docker Desktop, rootless Docker

Khi Docker daemon không nằm cùng network namespace với JVM hoặc Docker Desktop dùng VM, host mapped ports có thể không ở địa chỉ bạn đoán. Vì thế `container.getHost()` là API nên dùng. Nếu vẫn không reachable, xem:

- Docker context/endpoint được JVM sử dụng.
- `DOCKER_HOST` và TLS certificate config nếu dùng remote daemon.
- Firewall, port forwarding, host gateway.
- Rootless socket permission.
- Kubernetes/CI runner networking policy.
- Docker Desktop/Colima/Podman compatibility đối với môi trường đang dùng.

Các env vars như `TESTCONTAINERS_HOST_OVERRIDE` đôi khi là giải pháp cho topology đặc biệt, nhưng **chỉ đặt sau khi xác minh host thật**. Đặt tùy tiện có thể làm Testcontainers tìm nhầm host và khiến chẩn đoán khó hơn.

## 7. Các lỗi điển hình theo thời điểm khởi tạo

### 7.1. Trước container.start()

Nếu code gọi `getMappedPort` trong static field initializer hoặc `@BeforeAll` trước khi extension start, lỗi thường là **thứ tự lifecycle**. Không giải quyết bằng tăng timeout. Chuyển việc đọc port vào sau startup, ví dụ trong method test, hoặc để Spring Boot @ServiceConnection cung cấp details ở đúng lúc.

### 7.2. Sau khi Docker start nhưng trước readiness

Container có thể running nhưng socket chưa mở. Dùng WaitStrategy phù hợp và test protocol thật. Với PostgreSQL, chuyên biệt `PostgreSQLContainer` có startup readiness riêng; **không tự thay bằng GenericContainer port-only** nếu cần database có thể truy vấn.

### 7.3. Sau khi ready nhưng trước app migrations

Postgres chấp nhận `SELECT 1` nhưng Flyway migrations chưa apply schema của ứng dụng, dẫn tới `relation does not exist`. Kiểm tra thứ tự Spring Boot DataSource → Flyway/Liquibase → repository. Health DB không thay thế test schema/version. Trường hợp cần data fixtures nên dùng migrations cùng test setup được kiểm soát.

### 7.4. Sau khi test class A kết thúc

JUnit extension dừng static @Container của A, nhưng Spring cached context của A vẫn giữ JdbcTemplate/DataSource. Lớp B reuse context (khóa cấu hình tương đương) và mở connection mới → `Connection refused`. Điều cần sửa là **lifecycle ownership** hoặc context reuse strategy, không phải hardcode port hoặc thêm sleep.

### 7.5. Giữa nhiều tests song song

Hai tests cùng mutate data/schema, reset container, stop/restart hoặc dùng cùng database name có thể làm nhau fail. Testcontainers JUnit Jupiter extension không được đảm bảo an toàn cho parallel execution. Dùng isolated resources, stable container lifecycle, serial execution cho nhóm dùng chung state, hoặc thiết kế per-test resources đúng mức.

### 7.6. Docker container bị OOM-kill/restart

Dù WaitStrategy đã pass, container có thể chết trong lúc test chạy do thiếu memory/disk/CPU hoặc entrypoint crash. Kiểm tra `docker inspect` state (exit code, OOMKilled), `docker logs`, Docker events và CI resource limits. Đừng chỉ tăng JDBC connection timeout; server chết cần được phát hiện ở tầng container.

## 8. Một cây quyết định để tìm nguyên nhân gốc

```text
TEST FAILS: cannot connect to container service
                  |
                  v
        Docker daemon available?
             /          \
            no          yes
            |            |
   Docker/socket/CI     Can container start?
                         /          \
                       no           yes
                       |             |
                Image/startup       Is service ready?
                logs/exit code       /        \
                                    no        yes
                                    |          |
                            Wait/health/DB     Correct endpoint?
                                              /       \
                                            no        yes
                                            |          |
                                    host/mappedPort   Client/auth/TLS/
                                    network vantage  pool/migrations
                                                      |
                                                      v
                                        Fails only across tests?
                                              /      \
                                            yes       no
                                             |         |
                                    cache + @Container  app-specific
                                    stop/parallel/fork  fault
```

**Áp dụng theo thứ tự:**

1. Chạy `docker info`/`docker version` trong **cùng CI executor/test machine**.
2. Xem container id, startup logs, health status và exposed ports (không in secrets).
3. Xác minh vị trí của client: JVM host, container khác, remote service hay CI job container.
4. Lấy host từ `getHost()` và mapped port từ `getMappedPort(originalPort)` **sau start**.
5. Gửi một protocol-level probe: `PING` với Redis, `SELECT 1` với Postgres.
6. Kiểm tra credentials/TLS/DB name và schema nếu network đã thông.
7. Đối chiếu container lifecycle với Spring context cache/parallel/JVM forks.
8. Chỉ điều chỉnh timeout khi log chứng minh thực sự cần thêm thời gian.

## 9. Lệnh chẩn đoán Docker và Testcontainers

### 9.1. Kiểm tra Docker trước khi chạy JUnit

Linux/macOS hoặc PowerShell:

```bash
docker version
docker info
docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Nếu lệnh chạy trong máy dev nhưng không chạy trong **CI job environment**, bạn chưa chứng minh JVM CI có quyền truy cập Docker. Với Docker-in-Docker, socket TCP/TLS hoặc mount path có thể khác.

**Không** chạy `docker rm -f $(docker ps -aq)` hay xóa toàn bộ volumes để sửa test. Việc này có thể phá containers/volumes của người khác trên host dùng chung.

### 9.2. Xem một container có ID đã biết

```bash
docker logs --tail 100 <CONTAINER_ID>
docker inspect <CONTAINER_ID>
docker port <CONTAINER_ID>
```

Đây là **lệnh mẫu**: thay `<CONTAINER_ID>` bằng ID thực tế từ log/Testcontainers hoặc `docker ps -a`. Các outputs như JDBC URL, connection string và container env có thể chứa mật khẩu. Chỉ chia sẻ phần được redact.

Khi inspect, xem:

- Process `State.Running`/`ExitCode`/`OOMKilled`.
- `Health.Status` nếu image có HEALTHCHECK.
- `NetworkSettings.Ports`: internal containerPort/tcp → mapped host port.
- Network attachments/aliases.
- `RestartCount`, StartedAt, FinishedAt.
- Logs cho readiness/init/termination.

### 9.3. Bật log đúng namespace

Trong Logback test config hoặc logger setup, có thể bật:

```properties
logging.level.org.testcontainers=DEBUG
logging.level.com.github.dockerjava=INFO
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.com.zaxxer.hikari=DEBUG
```

Đây là **cấu hình minh họa**, không nhất thiết mọi logger hoạt động như kỳ vọng nếu hệ logging khởi tạo khác. DEBUG logs có thể rất ồn và có nguy cơ lộ thông tin; chỉ bật khi cần, redact credential-bearing properties/headers/URLs. Đọc root cause đầu tiên, đừng chỉ chọn exception cuối sau nhiều failed-context attempts.

### 9.4. Thu logs trong Java

Testcontainers có:

```java
String logs = container.getLogs();
System.out.println(logs);
```

**Snippet**: chỉ dùng trong debug có kiểm soát; sản phẩm thật không nên in raw logs nếu chứa secrets. Có thể dùng `withLogConsumer(new Slf4jLogConsumer(log))` hoặc custom consumer để thu output có redaction, hạn chế size và time window.

## 10. Demo Java 17+/Spring Boot 3.5.16

Project mẫu có **hai kiểm thử Docker integration** khác nhau:

1. **PostgreSQL** là Spring-managed container bean qua `@ServiceConnection`. Các tests dùng Spring `JdbcTemplate` để xác minh JDBC query, mapping và DataSource kết nối đúng container.
2. **Redis** dùng Testcontainers JUnit extension và `GenericContainer`, có WaitStrategy theo log; các tests dùng Java `Socket` và Redis protocol `PING` để chứng minh đúng host/mapped port.

Ngoài ra, có một **unit test không cần Docker** để kiểm tra điều kiện lỗi khi gọi `getMappedPort` trước startup. Các tests Redis không dùng Spring context và không bị Spring cache giữ client sau class. Trường hợp Postgres dùng Spring container bean để đồng bộ với context cache.

**Tổng cộng: 8 JUnit Jupiter methods**: 4 PostgreSQL, 3 Redis, 1 unit.

### 10.1. Cấu trúc file

```text
container-diagnostics/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/containerdiag/
    │   └── ContainerDiagnosticsApplication.java
    └── test/java/com/example/containerdiag/
        ├── PostgresContainerConfiguration.java
        ├── PostgresServiceConnectionTest.java
        ├── RedisMappedPortTest.java
        └── PortLifecycleUnitTest.java
```

Đây là demo thật cho kết nối khi có Docker daemon/images, **không** giả lập một URL cứng. Không khởi động database ngoài Testcontainers, không gửi request tới production services, không tạo cố định host ports trên máy dev.

### 10.2. Gradle Groovy DSL

**File `settings.gradle`:**

```groovy
rootProject.name = 'container-diagnostics'
```

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'

    // Spring Boot 3.5.16 BOM manages Testcontainers 1.21.4.
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    maxParallelForks = 1
    forkEvery = 0
}
```

**Giải thích dependencies và phiên bản:**

- `spring-boot-starter-jdbc` cung cấp DataSource/JdbcTemplate/Hikari.
- `org.postgresql:postgresql` là JDBC driver thật cho PostgreSQL.
- `spring-boot-starter-test` cung cấp JUnit Jupiter và AssertJ.
- `spring-boot-testcontainers` cung cấp Spring Boot integration và `@ServiceConnection`.
- `org.testcontainers:postgresql` và `org.testcontainers:junit-jupiter` là **module names Testcontainers 1.x**, tương thích Boot 3.5 managed dependencies.
- `maxParallelForks=1` và `forkEvery=0` giúp demo chạy một test worker JVM; chúng **không** đảm bảo mọi CI environment có Docker.
- Để giảm race trong JUnit Testcontainers extension, demo không bật JUnit parallel. Nếu dự án có `junit.jupiter.execution.parallel.enabled=true` từ cấu hình khác, hãy tắt cho nhóm này hoặc cô lập resources đúng cách.
- Gradle Wrapper không nằm trong danh sách file; tạo qua Gradle/IDE nếu project chưa có.

**Vì Spring Boot 3.5 BOM quản lý Testcontainers 1.21.4, đừng thay tọa độ module ở đây bằng các module names từ docs Testcontainers 2.x mà không nâng toàn bộ dependency graph và kiểm tra APIs.**

## 11. Production entrypoint và Spring-managed PostgreSQL

### 11.1. Spring Boot application

**File `src/main/java/com/example/containerdiag/ContainerDiagnosticsApplication.java`:**

```java
package com.example.containerdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContainerDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ContainerDiagnosticsApplication.class, args);
    }
}
```

Application demo chỉ có JDBC starter, không nạp MVC/JPA. Nếu chạy `bootRun` mà **không có** database config riêng, auto-config có thể fail vì không có DataSource; đó không phải lỗi của tests. Trong demo, PostgreSQL container được cung cấp **chỉ trong test ApplicationContext** qua @Import, và `bootRun` độc lập không được coi là một lệnh khởi động app mẫu với DB.

### 11.2. Container bean theo vòng đời Spring

**File `src/test/java/com/example/containerdiag/PostgresContainerConfiguration.java`:**

```java
package com.example.containerdiag;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

@TestConfiguration(proxyBeanMethods = false)
class PostgresContainerConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                DockerImageName.parse("postgres:16-alpine"))
                .withDatabaseName("diagnostics")
                .withUsername("test")
                .withPassword("test");
    }
}
```

**Tại sao không có @Testcontainers/@Container ở class này?**

Vì `PostgreSQLContainer` được đăng ký là Spring `@Bean`; Spring Boot quản lý lifecycle:

1. Tạo/start container bean trước những Spring beans cần kết nối.
2. Tạo `JdbcConnectionDetails` từ `@ServiceConnection`.
3. DataSource lấy JDBC URL/username/password từ connection details, không cần hardcode localhost:5432.
4. Khi Spring TestContext cache giữ ApplicationContext, container tiếp tục sống cùng context.
5. Khi context được đóng, Boot dừng container **sau khi** dependencies được destroy.

Đây là lựa chọn có chủ đích để tránh trường hợp JUnit extension stop container trước khi cached context được dùng xong.

**Bảo mật:** username/password `test` chỉ dành cho container test tạm thời, không phải credentials production. Không in password trong test logs hoặc gửi connection string chứa secrets lên issue công khai.

## 12. JUnit: kiểm tra PostgreSQL service connection thật

**File `src/test/java/com/example/containerdiag/PostgresServiceConnectionTest.java`:**

```java
package com.example.containerdiag;

import java.sql.Connection;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ContainerDiagnosticsApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@Import(PostgresContainerConfiguration.class)
class PostgresServiceConnectionTest {

    @Autowired
    PostgreSQLContainer<?> postgres;

    @Autowired
    JdbcConnectionDetails connectionDetails;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void containerIsRunningBeforeJdbcConsumersUseIt() {
        assertThat(postgres.isRunning()).isTrue();
        assertThat(postgres.getHost()).isNotBlank();

        int actualHostPort = postgres.getMappedPort(5432);
        assertThat(actualHostPort)
                .isBetween(1, 65535);
        assertThat(postgres.getExposedPorts())
                .contains(5432);
    }

    @Test
    void serviceConnectionPointsAtTheActualContainer() {
        assertThat(connectionDetails.getJdbcUrl())
                .isEqualTo(postgres.getJdbcUrl());
        assertThat(connectionDetails.getUsername())
                .isEqualTo(postgres.getUsername());
        assertThat(connectionDetails.getPassword())
                .isEqualTo(postgres.getPassword());
    }

    @Test
    void jdbcQueryChecksProtocolNotJustContainerState() {
        Integer actual =
                jdbc.queryForObject("SELECT 1", Integer.class);
        assertThat(actual).isEqualTo(1);

        String dbName = jdbc.queryForObject(
                "SELECT current_database()", String.class);
        assertThat(dbName).isEqualTo("diagnostics");
    }

    @Test
    void datasourceProvidesAWorkingJdbcConnection()
            throws Exception {
        try (Connection connection =
                     dataSource.getConnection()) {
            assertThat(connection.isValid(2)).isTrue();
            assertThat(connection.getMetaData()
                    .getURL()).startsWith("jdbc:postgresql:");
        }
    }
}
```

### 12.1. Những asserts này chứng minh gì?

| Assertion | Chứng minh | Không chứng minh |
|---|---|---|
| `postgres.isRunning()` | Container entry process đang chạy | DB protocol đã ready |
| `getMappedPort(5432)` valid | Docker đã cấp mapped port cho internal 5432 | Port có route từ mọi network vantage point |
| `JdbcConnectionDetails.getJdbcUrl()` | Boot chọn đúng container JDBC URL | SQL/query/migrations thành công |
| `SELECT 1` | JDBC connection + PostgreSQL query thực thành công | Schema của app đúng |
| `current_database()` | Đã vào DB mang tên mong đợi | DB có đủ table business |
| `Connection.isValid(2)` | JDBC connection có thể trả lời validity check | Không có future network failure |

Test có **4 JUnit methods** và dựa trên Docker/Postgres image thật. Nếu Docker không available, tests cần fail với lỗi environment có thể xử lý hoặc được quản lý theo chính sách CI, **không phải tự động coi một suite skipped là integration QA PASS**.

### 12.2. Không dùng assert "mappedPort phải khác 5432"

Port mapping thường random, nhưng một host port trùng 5432 không phải bất khả thi. Assert `getMappedPort(5432) != 5432` là test suy đoán môi trường và flaky. Điều đúng cần xác nhận là container đã start, port mapping hợp lệ và **connection protocol thực sự hoạt động**.

### 12.3. JDBC driver và DataSource có thể fail riêng

Container đã ready nhưng Spring bean fail nếu:

- Thiếu `org.postgresql:postgresql` driver.
- Có nhiều Datasources/ConnectionDetails làm auto-configuration ambiguous.
- Các properties hoặc custom DataSource bean override connection details.
- SSL config/driver version không phù hợp.
- Pool size/timeouts bị cấu hình sai.
- Migration chạy vào DB khác với DB mà JDBC test đang dùng.

Đừng gán mọi `BeanCreationException` là container readiness failure; đọc root cause chain và bean dependency đang fail.

## 13. JUnit: xác minh Redis mapped port bằng protocol PING

Trong demo này Redis được JUnit Testcontainers extension quản lý **và không được Spring Data Redis bean dùng lại**; vì vậy không có cached Spring client còn sống sau khi Redis @Container dừng.

**File `src/test/java/com/example/containerdiag/RedisMappedPortTest.java`:**

```java
package com.example.containerdiag;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class RedisMappedPortTest {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7-alpine"))
                    .withExposedPorts(REDIS_PORT)
                    .waitingFor(
                        Wait.forLogMessage(
                            ".*Ready to accept connections.*\\n",
                            1))
                    .withStartupTimeout(
                            Duration.ofMinutes(2));

    @Test
    void containerPortIsExposedAndHostMappingExists() {
        assertThat(redis.isRunning()).isTrue();
        assertThat(redis.getExposedPorts())
                .contains(REDIS_PORT);
        assertThat(redis.getHost()).isNotBlank();
        assertThat(redis.getMappedPort(REDIS_PORT))
                .isBetween(1, 65535);
    }

    @Test
    void redisRepliesToPingOnResolvedMappedEndpoint()
            throws Exception {
        String host = redis.getHost();
        int mappedPort = redis.getMappedPort(REDIS_PORT);

        try (Socket socket = new Socket()) {
            socket.connect(
                    new InetSocketAddress(host, mappedPort),
                    3_000);
            socket.setSoTimeout(3_000);

            byte[] ping =
                    "PING\r\n".getBytes(StandardCharsets.US_ASCII);
            socket.getOutputStream().write(ping);
            socket.getOutputStream().flush();

            BufferedReader reply = new BufferedReader(
                    new InputStreamReader(
                        socket.getInputStream(),
                        StandardCharsets.US_ASCII));

            assertThat(reply.readLine()).isEqualTo("+PONG");
        }
    }

    @Test
    void readinessLogIsPresentAsASeparateSignal() {
        assertThat(redis.getLogs())
                .contains("Ready to accept connections");
    }
}
```

### 13.1. Vì sao dùng Java Socket thay vì thêm Redis client?

Mục tiêu là phân biệt **mapped port** và khả năng TCP/protocol trả lời. Java 17 đã có Socket, nên không cần kéo thêm Spring Data Redis hay Lettuce chỉ để chứng minh Redis PING. Test gửi Redis inline command `PING\r\n`, kỳ vọng RESP simple string `+PONG`. Đây là giao thức Redis ở chế độ không authentication của demo; nếu Redis được bảo vệ bằng ACL/TLS, phải dùng client phù hợp và cấu hình credentials/certificates đúng.

### 13.2. Vì sao vừa log wait vừa PING?

Log message là một readiness signal. PING là kiểm chứng **protocol thực tế đi qua host mapped port**. Nếu log khớp nhưng PING fail, xem network host/mappedPort, Redis process restart, network policy hoặc bảo mật. Nếu log pattern không khớp ở image version mới dù Redis đã ready, đổi wait strategy theo **readiness signal ổn định hơn** thay vì thêm sleep.

### 13.3. Testcontainers version và Redis logs

Image tag `redis:7-alpine` có thể nhận patch versions mới theo thời gian. Log output/pattern có thể thay đổi. Với CI có yêu cầu reproducibility cao, pin digest/image tag đã xác minh trong registry và review updates; điều này đặc biệt quan trọng khi dùng log message as readiness.

## 14. JUnit unit test cho sai thứ tự đọc mapped port

**File `src/test/java/com/example/containerdiag/PortLifecycleUnitTest.java`:**

```java
package com.example.containerdiag;

import org.junit.jupiter.api.Test;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PortLifecycleUnitTest {

    @Test
    void mappedPortCannotBeReadBeforeContainerStartup() {
        GenericContainer<?> neverStarted =
                new GenericContainer<>(
                    DockerImageName.parse("redis:7-alpine"))
                    .withExposedPorts(6379);

        assertThatThrownBy(() ->
                neverStarted.getMappedPort(6379))
                .isInstanceOf(IllegalStateException.class);
    }
}
```

Đây là test thuần Java **không gọi start()** và không cần Docker daemon; nó minh họa một lỗi **order of operations**. Nếu JUnit test đó fail vì API behavior thay đổi ở version khác, kiểm tra docs/Javadoc của Testcontainers version tương ứng thay vì thêm một sleep trước getMappedPort.

### 14.1. Phân loại 8 tests

| Lớp | Số methods | Phạm vi |
|---|---:|---|
| `PostgresServiceConnectionTest` | 4 | Spring Boot container bean + JDBC thực |
| `RedisMappedPortTest` | 3 | JUnit @Container + mapped TCP + Redis PING |
| `PortLifecycleUnitTest` | 1 | Guard đọc mapped port trước startup |
| **Tổng** | **8** | Hai Docker integration paths, một lifecycle unit case |

Test class nào dùng Spring context, class nào không dùng đã được phân tách rõ. Không nên viết test expecting Redis và Postgres cùng một cache entry, vì chúng thuộc lifecycles khác nhau.

## 15. Chạy code và giải thích lỗi quan sát được

### 15.1. Yêu cầu môi trường

- JDK **17+**.
- Gradle phù hợp với Spring Boot 3.5 Gradle plugin, có Gradle Wrapper nếu dùng `./gradlew`.
- Docker daemon accessible từ **JVM chạy tests**, không chỉ từ terminal của host khác.
- Quyền pull images `postgres:16-alpine` và `redis:7-alpine`.
- Đủ CPU/RAM/disk, ports và network routing cho Docker/Testcontainers.
- CI runner cho phép Docker socket/daemon connection; không tự giả định DinD/service container đã cấu hình.
- Không cần database PostgreSQL/Redis chạy sẵn ở host ports cố định.

### 15.2. Lệnh trên Linux/macOS

```bash
docker version
docker info

./gradlew clean test \
  --tests "com.example.containerdiag.PortLifecycleUnitTest" \
  --tests "com.example.containerdiag.RedisMappedPortTest" \
  --tests "com.example.containerdiag.PostgresServiceConnectionTest"
```

### 15.3. Lệnh trên Windows PowerShell

```powershell
docker version
docker info

.\gradlew.bat clean test --tests "com.example.containerdiag.*"
```

Khi chạy toàn project, dùng `./gradlew test` hoặc `.\gradlew.bat test`. Đừng chạy `bootRun` như cách kiểm tra container test ở ví dụ này, vì test container configuration ở `src/test` chỉ được import khi test load Spring context.

### 15.4. Không bịa stdout hay test score

**Kết quả kỳ vọng theo thiết kế** là 8 JUnit methods pass trong môi trường có Docker/Testcontainers/PostgreSQL/Redis tương thích. Bài này **chưa thực thi Gradle, Docker hoặc JUnit** trong phiên soạn; không thể nói đã quan sát `BUILD SUCCESSFUL`, mapped port số cụ thể hoặc thời gian startup thật.

Sau khi chạy, xem:

- `build/test-results/test` (XML JUnit).
- `build/reports/tests/test` (HTML Gradle).
- Testcontainers logs cho container ID và actual mapped port.
- Docker logs/inspect cho readiness/error state.
- Pass/fail/skipped count thực tế, không chỉ build task status `UP-TO-DATE`.

**Nếu Docker không có trong CI**, đừng cấu hình auto-skip rồi báo “8/8 pass”. Phân biệt unit test chạy được với integration tests cần Docker, đặt job/tag rõ và kiểm tra job integration có thực thi.

## 16. @ServiceConnection, @DynamicPropertySource và context cache

### 16.1. Ưu tiên lifecycle nhất quán

Spring TestContext cache giữ ApplicationContext sau class A nếu cache key chưa dirty/evict. Một Spring DataSource bean đã được khởi tạo và giữ connection pool tới container. Nếu @Container của A được JUnit extension stop sau class, class B có thể reuse context **đã giữ client** nhưng backing DB không còn.

**Spring-managed container bean** hoặc Boot `@ImportTestcontainers` là hướng khuyến nghị cho context được share. Cả container và dependent beans có lifecycle cùng context. Khi context shutdown, Spring dọn dependent beans rồi container.

### 16.2. Khi dùng @DynamicPropertySource

Spring Framework đưa `@DynamicPropertySource` method vào **context customizers/cache key**, nhưng không bảo đảm dynamic values (ví dụ randomized ports) được so sánh từng lần để tạo key khác nhau. Nếu nhiều subclasses chia cùng dynamic method nhưng container URL/port thực thay đổi, cache reuse có thể giữ DataSource trỏ endpoint cũ.

Giải pháp có căn cứ:

- Dùng shared container ổn định với lifecycle dài đúng phạm vi.
- Chọn Spring-managed container/imported declaration khi phù hợp.
- Tách context configuration khi resources thật sự khác nhau.
- Nếu không thể reuse safely, dùng `@DirtiesContext` đúng class/context scope, không tràn lan.
- Không cố force một unique random inline property cho mọi test để “né” cache khi điều đó làm CI rất chậm và không giải quyết external DB cleanup.

### 16.3. @DirtiesContext có tác dụng và giới hạn

`@DirtiesContext` loại/đóng cached ApplicationContext; lần lookup sau cùng key phải load mới. Nó **không** xóa Docker volumes ngoài context, không rollback Kafka messages và không bảo vệ một test thread khác đang dùng context khi chạy parallel. Việc dirty context giữa các tests có thể gây `ApplicationContext is no longer active` nếu thread khác còn sử dụng nó.

Đừng thêm `@DirtiesContext` vào mọi class để chữa một lỗi sai hostname hoặc thiếu wait strategy; sửa đúng network/lifecycle trước.

### 16.4. Reusable containers không phải câu trả lời mặc định

Testcontainers hỗ trợ reusable container mode trong một số phiên bản và cấu hình, nhưng lifecycle, isolation và cleanup khác với ephemeral containers thông thường. **Không bật reuse ở CI shared runner chỉ để giảm startup** khi chưa có quy trình quản lý resource/schema/data. Reuse có thể mang state từ test run trước, che hoặc sinh lỗi.

## 17. Lỗi phụ thuộc database/schema dù container đã ready

### 17.1. PostgreSQL ready nhưng JDBC auth fail

Bất kỳ thứ gì sau đây có thể sai:

- Username/password không khớp với container.
- Spring Boot dùng connection details khác do custom DataSource.
- DB name không tồn tại hoặc init script tạo schema trong DB khác.
- JDBC driver chọn SSL mode không phù hợp.
- Application/CI có environment variables `SPRING_DATASOURCE_URL` hoặc test config ảnh hưởng routing khi không dùng @ServiceConnection.

**Quan sát cần thiết:** kết nối thực trả lỗi nào và DataSource thực gửi JDBC URL nào. Khi log URL, **redact credentials**; tốt hơn assert equality với container.getJdbcUrl trong test thay vì dump password.

### 17.2. PostgreSQL ready nhưng Flyway/Liquibase fail

Chạy `SELECT 1` không bảo đảm migrations đúng. Tách thành tests:

1. DB protocol readiness.
2. Migration execution thành công.
3. Schema/table/constraint đúng.
4. Query/transaction nghiệp vụ hoạt động.
5. Dữ liệu test cleanup không làm ô nhiễm classes khác.

Nếu cần migration test, thêm migration dependencies và scripts thực trong một integration suite riêng; **mã demo không khai báo Flyway/Liquibase**, nên không được gọi 8 tests kia là kiểm tra migrations.

### 17.3. Hikari pool hết connection

Thông báo `HikariPool ... Connection is not available, request timed out` có thể do:

- Tạo nhiều connections mà không close.
- Một query/transaction giữ lock quá lâu.
- Postgres đạt giới hạn max_connections.
- Container bị stop/restart nên pool liên tục validate fail.
- Pool size/timeouts thiếu phù hợp với concurrency.

Đừng chỉ tăng `spring.datasource.hikari.connection-timeout`. Kiểm tra active/idle/pending metrics, thread dumps, DB locks và container state.

### 17.4. Connection reset sau readiness

Nếu PostgreSQL/Redis restart sau một thời gian, WaitStrategy lúc startup có thể từng pass nhưng kết nối hiện tại bị reset. Đọc restart/OOM logs, kiểm tra retry policy của client nếu ứng dụng thực có yêu cầu resilience, và xác định test đang kiểm tra startup hay recovery. **WaitStrategy chỉ đồng bộ startup**, không tạo bảo đảm service sống mãi.

## 18. Vì sao CI và máy local khác nhau?

### 18.1. Docker daemon và quyền

Testcontainers cần Docker-compatible runtime. Trên máy local Docker Desktop có daemon/socket phù hợp, nhưng CI executor có thể:

- Không mount Docker socket.
- Chạy rootless với socket path khác.
- Dùng Docker-in-Docker service chưa sẵn sàng.
- Yêu cầu Docker TLS certificate hoặc network alias của service.
- Cấm privileged containers hoặc image pulls.
- Có Docker API version mismatch.

Spring Boot 3.5 có tài liệu giải thích một số Docker Desktop API version changes và cách Boot cung cấp `docker-java.properties` phù hợp. **Không tùy tiện đặt Docker API version** vì một lỗi connect refused không nhất thiết liên quan API version.

### 18.2. Resource starvation

CI runner thiếu RAM/disk làm Postgres khởi động chậm, OOM, disk-full hoặc container image pull timeout. Xem Docker disk utilization, container exit code/OOMKilled, CPU quota và concurrency. Chạy serial/giảm parallel khi tài nguyên không đủ, nhưng không xem đó là fix cho misconfiguration.

### 18.3. Remote Docker và mapped host

Nếu Docker daemon chạy remote, mapped host ports tồn tại ở Docker host, không chắc ở `localhost` của JVM test. Dùng `getHost()` và `getMappedPort()`; nếu host address không route được qua firewall hoặc CI network, phải sửa topology/port forwarding thay vì tự đổi host về localhost.

### 18.4. Network/proxy constraints

Một CI environment có egress restrictions, corporate proxy hoặc mirror registry có thể không kéo được image. Image pull failure khác test service connection. Dùng registry mirror hợp lệ, credentials được quản lý an toàn và explicit image tags/digests. Không chép Docker registry passwords/token vào logs hoặc test source.

### 18.5. Test worker forks và cache scope

Spring TestContext cache là static **trong một JVM test worker**. Gradle `maxParallelForks>1` tạo nhiều processes, mỗi process có cache riêng và có thể start thêm containers. JUnit ResourceLock không bảo vệ tài nguyên xuyên JVM. Nếu tests dùng chung một database/schema/broker bên ngoài, phải có unique resources hoặc coordination ngoài JVM.

## 19. Phương pháp đọc logs không bị đánh lạc hướng

Khi test fail, thu thông tin **theo thứ tự thời gian**:

1. Test method/class đang chạy, JVM worker và container ID.
2. Docker discovery: daemon endpoint/permission/image pull.
3. Container created/start logs.
4. Wait strategy được chọn và timeout thực tế.
5. Container exit/health state nếu có.
6. Host + mapped port **do container API trả sau startup**.
7. Spring Boot connection details hoặc effective DataSource endpoint.
8. Exception root cause của driver/protocol.
9. Context cache hit/miss, @DirtiesContext, JUnit extension stop hooks.
10. Relevant CI resources/parallel/fork settings.

**Không** chỉ grep từ khóa `Connection refused` rồi kết luận “thêm Thread.sleep”. Cùng một exception có thể phát sinh từ host mapping sai, container chết, service chưa ready hoặc cached DataSource trỏ container bị stop.

### 19.1. Một thông điệp chẩn đoán tốt

Một bug report hữu ích gồm:

```text
Environment:
  JDK: 17
  Spring Boot: 3.5.x
  Testcontainers: 1.21.x
  Test runner: Gradle test worker, one/multiple forks
  Docker: local/remote/DinD (no secrets)

Observed:
  Failure phase: container startup / Spring context /
                 JDBC connect / later test method
  Exception type + sanitized root cause
  Container state: running/exited/oom/health
  Container internal port: 5432
  Resolved getHost(): sanitized hostname
  Resolved getMappedPort(5432): actual host port
  Wait strategy + timeout:
  Container logs: limited, redacted excerpt

Reproduction:
  One class vs entire suite vs parallel execution
  Source of JDBC details: @ServiceConnection /
                          @DynamicPropertySource / manual
  Lifecycle owner: Spring / JUnit Testcontainers extension
```

Đây là **mẫu báo lỗi**, không phải output một lần chạy thật. Không gửi đầy đủ Docker inspect environment, password, auth token, full JDBC URL chứa secret hoặc dữ liệu khách hàng.

## 20. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Thay bằng |
|---|---|---|
| Hardcode localhost:5432 hoặc redis:6379 từ host JVM | Kết nối nhầm DB/port hoặc CI refused | getJdbcUrl, getHost + getMappedPort |
| Gọi getMappedPort trong static initializer trước start | IllegalStateException | Đọc sau start hoặc ServiceConnection |
| Thấy Docker running là coi DB ready | Startup race | WaitStrategy + real protocol query |
| Thread.sleep(30000) mỗi test | Chậm, flaky | Wait for health/protocol readiness |
| Thay specialized PostgreSQL wait bằng port-only | False positive ready | Giữ module startup readiness |
| Bật fixed host ports cho mọi test | Collisions khi parallel | Random mapped ports |
| Dùng Docker alias như redis:6379 từ host JVM | DNS không resolve | Host mapped endpoint |
| Dùng localhost trong application container để tới DB container | Trỏ về chính app container | Same-network alias/internal port |
| Dùng @Container static theo class nhưng cache Spring context xuyên classes | Cached DataSource trỏ DB đã stop | Spring-managed container/@ImportTestcontainers |
| Dùng @DynamicPropertySource nhưng URL hardcoded | Không giải quyết mapping | Container supplier/getJdbcUrl |
| @ServiceConnection + manual JDBC props rồi debug Environment đơn thuần | Không thấy effective connection details | Inspect actual connection details/DataSource |
| Tăng timeout khi credentials sai | Chỉ đợi lâu hơn | Kiểm tra auth/database settings |
| @DirtiesContext mọi class | Repeated Docker startup, slow CI | Lifecycle ownership/cache-safe design |
| Bật JUnit parallel trên @Container shared state | Race/unstable lifetime | Serial/isolation có kiểm soát |
| getLogs in toàn bộ ra public CI | Lộ tokens/password | Sanitized excerpts |
| Test pass khi Docker integration job skipped | False green | CI test count/gates rõ |
| Bỏ kiểm tra migrations vì SELECT 1 pass | Schema regressions lọt | Migration/schema integration tests |
| Bật reusable containers trên shared CI | State leak từ runs trước | Ephemeral hoặc policy cleanup nghiêm |
| Sử dụng port một lần rồi cache static qua restarts | Stale mapped port | Re-resolve after actual start |
| Chạy docker prune/rm tất cả để “fix” | Phá hạ tầng khác | Chỉ xử lý container của test được xác định |
| Chẩn đoán chỉ bằng một exception cuối | Bỏ lỡ root startup failure | Timeline + first root cause |
| Nghĩ @Transactional trên RANDOM_PORT rollback server writes | DB leakage | Cleanup/test isolation riêng |
| Xem Hikari timeout là chứng minh network không thông | Có thể pool/locks | Pool metrics, DB locks, container status |
| Nâng module Testcontainers 2.x riêng lẻ trong Boot 3.5 project 1.x | Classpath/API mismatch | BOM-aligned dependency set |

## 21. Bài tập thực hành với lời giải

### A. Container running nhưng SELECT 1 fail

**Câu hỏi:** Docker báo PostgreSQL running, nhưng JDBC connection refused ngay sau start. Có thể kết luận DB image lỗi không?

**Đáp:** Chưa. Có thể Postgres chưa lắng nghe, test dùng sai host/mapped port, container đã restart hoặc network route bị chặn. Dùng PostgreSQLContainer specialized wait, getJdbcUrl và SELECT 1 để chứng minh readiness/protocol thật.

### B. Port trước start

**Câu hỏi:** Code constructor tạo GenericContainer rồi gọi getMappedPort(6379). JUnit fail trước khi Docker image được pull. Nên tăng timeout ở đâu?

**Đáp:** Không cần tăng timeout. Port mapping chưa được cấp; phải start container trước, rồi mới gọi getMappedPort.

### C. Lỗi localhost trong CI

**Câu hỏi:** Local dùng localhost:5432 thành công nhưng CI Docker daemon remote báo Connection refused. Vì sao?

**Đáp:** Host mapped port nằm trên Docker host, không chắc trên localhost của test JVM. Dùng getHost/getMappedPort hoặc PostgreSQLContainer.getJdbcUrl, sửa network routing/firewall nếu cần.

### D. Container-to-container

**Câu hỏi:** Ứng dụng Spring Boot cũng chạy trong một container chung network với Redis. Có nên dùng mappedPort=49xxx trong ứng dụng?

**Đáp:** Thường không; dùng Docker network alias và internal port 6379 khi cùng network. Host mapped port phục vụ client ở phía host, không phải bắt buộc cho container nội bộ.

### E. Redis log ready nhưng PING fail

**Câu hỏi:** Wait.forLogMessage đã pass, nhưng Socket PING tới mapped endpoint fail.

**Đáp:** Kiểm tra mapped host/port, Redis restart, network route, ACL/TLS và log pattern có xuất hiện trước readiness thực không. Log line không bảo đảm mọi client vantage point tới được dịch vụ.

### F. Một test class pass, lớp kế tiếp fail

**Câu hỏi:** Static @Container PostgreSQL có @ServiceConnection, JUnit extension stop sau lớp A, Spring context còn cached. Lớp B dùng lại context và fail.

**Đáp:** Xem lifecycle mismatch. Dùng Spring-managed container bean hoặc @ImportTestcontainers khi cần context sống xuyên các classes, hoặc cố tình tách cache/contexts phù hợp. Đừng chỉ đổi timeout.

### G. Database login failed

**Câu hỏi:** JDBC báo password authentication failed. Có phải container chưa start?

**Đáp:** Thường client đã tới được PostgreSQL authentication layer. Kiểm tra credentials/source của JdbcConnectionDetails/DataSource và database/user initialization, không mặc định network failure.

### H. SQL relation does not exist

**Câu hỏi:** SELECT 1 pass nhưng repository query fail với relation does not exist.

**Đáp:** Database protocol ready, nhưng schema/migrations chưa hoàn chỉnh hoặc query tới sai DB/schema. Kiểm tra Flyway/Liquibase/DDL và actual current_database/current_schema.

### I. Hikari timeout

**Câu hỏi:** Hikari chờ connection 30s rồi fail, Docker container vẫn running.

**Đáp:** Pool có thể cạn do leaked connections, long-running transactions, locks hoặc database không trả lời. Xem pool metrics/threads/DB logs, không coi running là proof of healthy database.

### J. Testcontainers @Container chạy parallel

**Câu hỏi:** Hai methods cùng static Redis container được JUnit chạy song song, một method restart container.

**Đáp:** Không an toàn; extension không được docs đảm bảo parallel support, mapped port và clients có thể thành stale. Chạy serial hoặc thiết kế isolated resources, không restart shared container khi test khác sử dụng.

### K. Docker không có trên CI

**Câu hỏi:** Runner chỉ chạy PortLifecycleUnitTest và skip Redis/Postgres, task xanh. Có đủ bằng chứng integration không?

**Đáp:** Không. Unit case chỉ chứng minh API guard; cần CI Docker-enabled job chạy đủ integration tests, kiểm tra executed/skipped counts.

### L. @DynamicPropertySource với port cũ

**Câu hỏi:** Supplier giữ một static mappedPort từ lần start trước, container restart và mapped port đổi.

**Đáp:** Supplier trả stale value. Lấy URL/port từ container hiện tại sau startup; thống nhất lifecycle/context cache để tránh reuse stale DataSource.

### M. Tăng timeout lên 5 phút

**Câu hỏi:** Nếu bị UnknownHostException hoặc localhost sai, tăng wait timeout có hiệu quả không?

**Đáp:** Không. Cần sửa DNS/host/network endpoint. Timeout chỉ giúp service thực sự cần thêm thời gian và có bằng chứng readiness chưa đạt.

### N. @DirtiesContext và database test data

**Câu hỏi:** Dirty context có tự xóa row trong một external PostgreSQL được dùng chung không?

**Đáp:** Không nhất thiết. Context eviction không tương đương database truncate/rollback; quản lý schema/test fixtures/transactions riêng.

### O. Testcontainers 2.x docs và Boot 3.5 BOM

**Câu hỏi:** Documentation mới đề xuất `org.testcontainers:testcontainers-postgresql`, nhưng project Boot 3.5.16 quản lý Testcontainers 1.21.4.

**Đáp:** Đây là thay đổi coordinates giữa major versions. Với Boot 3.5.16 hãy dùng BOM-managed 1.x modules như `org.testcontainers:postgresql`; nếu nâng lên 2.x, nâng đồng bộ dependency graph và xác minh Java APIs.

## 22. Checklist QA cho test dùng container

- [ ] JVM test truy cập Docker daemon thực trong local và CI.
- [ ] Docker image tag/digest hợp lệ và pull được.
- [ ] Testcontainers module versions khớp Spring Boot BOM.
- [ ] Có driver/client dependency cần thiết (PostgreSQL JDBC, Redis client...).
- [ ] Container port được expose đúng bằng withExposedPorts khi dùng GenericContainer.
- [ ] getMappedPort chỉ gọi sau container startup.
- [ ] Không hardcode host mapped port ngẫu nhiên.
- [ ] Host lấy từ getHost hoặc typed container URL theo test vantage point.
- [ ] Khi container→container, dùng đúng network/alias/internal port.
- [ ] Startup strategy và wait strategy không bị nhầm.
- [ ] Wait condition phản ánh readiness thực, không chỉ running.
- [ ] Protocol-level probe phù hợp: PING/SELECT 1/health endpoint.
- [ ] Không thay specialized module wait bằng port-only kém hơn.
- [ ] Không dùng Thread.sleep để che startup race.
- [ ] Auth/TLS/DB/schema errors được tách khỏi network failures.
- [ ] Mapped host/port đọc sau start và sau mỗi restart.
- [ ] @ServiceConnection và DynamicPropertySource không cạnh tranh một cách mù mờ.
- [ ] Effective JdbcConnectionDetails/DataSource được kiểm tra khi debugging.
- [ ] Container lifecycle owner được xác định: JUnit extension hay Spring bean.
- [ ] Cached Spring context không dùng container đã stop.
- [ ] @DirtiesContext chỉ dùng khi cần, không đại trà.
- [ ] Không bật parallel trên shared @Container khi chưa cô lập.
- [ ] External DB/Kafka/test data có cleanup độc lập với context cache.
- [ ] Test job CI đủ CPU/RAM/disk cho images.
- [ ] Remote Docker/DinD/rootless networking được mô tả rõ.
- [ ] Logs có container ID, state, mapped port và wait strategy, đã redact.
- [ ] Không in secrets trong stdout/Docker inspect artifacts.
- [ ] Có JUnit execution counts phân biệt pass/fail/skipped.
- [ ] Không coi skipped Docker test là integration QA PASS.
- [ ] CI không dùng docker prune hoặc rm tất cả resources trên shared host.
- [ ] Có regression test cho failure mode từng xảy ra.
- [ ] Có full app integration test riêng nếu migrations/security/transactions quan trọng.
- [ ] Boot 3.5/Testcontainers 1.x imports/coordinates đã được review.
- [ ] Không tuyên bố runtime pass khi chưa chạy trong Docker-enabled environment.

## 23. Kết luận

**Container running, dịch vụ ready và ứng dụng kết nối được là ba điều khác nhau.** Việc sửa đúng bắt đầu bằng xác định lỗi ở lớp nào: Docker daemon, container process, readiness, host/network/mapped port, protocol/authentication, Spring configuration hay lifecycle/cache/parallel tests.

Những nguyên tắc quan trọng nhất:

1. **Từ JVM host, dùng `getHost()` và `getMappedPort(containerPort)` sau startup; với JDBC container, ưu tiên `getJdbcUrl()` hoặc Spring Boot @ServiceConnection.**
2. **Dùng WaitStrategy phù hợp và probe protocol thật** thay vì chỉ nhìn Docker state hoặc sleep.
3. **Không hardcode localhost/host port**, nhất là trong CI và remote Docker.
4. **Đồng bộ container lifecycle với Spring TestContext cache**; khi muốn context dùng lại an toàn, ưu tiên Spring-managed container bean hoặc @ImportTestcontainers.
5. **Phân biệt connection refused, timeout, auth failure, schema failure và pool exhaustion** trước khi quyết định sửa.
6. **Giữ integration tests chạy thật** trên Docker-enabled CI và xem số tests executed, không chấp nhận false-green do skip.

Ví dụ Java 17+/Spring Boot 3.5.16/Testcontainers 1.21.4 gồm **8 JUnit methods**: Spring-managed PostgreSQL/JDBC integration (4), Redis mapped-port và PING (3), và lỗi lấy mapped port trước startup (1). Kết quả kỳ vọng là các tests chạy xanh **khi Docker, dependencies và network phù hợp**; bài viết này không tự nhận đã chạy Gradle/Docker/JUnit trong phiên biên soạn.

## 24. Tài liệu tham khảo chính thức

- [Testcontainers — Networking and communicating with containers](https://java.testcontainers.org/features/networking/): withExposedPorts, getMappedPort, getHost, host/container network.
- [Testcontainers — Waiting for containers to start or be ready](https://java.testcontainers.org/features/startup_and_waits/): running vs ready, HTTP/log/healthcheck wait, timeout.
- [Testcontainers — Accessing container logs](https://java.testcontainers.org/features/container_logs/): getLogs, following output, wait for log frames.
- [Testcontainers — JUnit Jupiter integration](https://java.testcontainers.org/test_framework_integration/junit_5/): @Testcontainers, @Container static/instance lifecycle, parallel caveats.
- [Testcontainers — Manual lifecycle control](https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/): start/stop, singleton lifecycle patterns.
- [Testcontainers — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQLContainer, database connection details.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): Spring-managed container beans, @ServiceConnection, @ImportTestcontainers, @DynamicPropertySource and lifecycle.
- [Spring Boot 3.5 — Managed dependency versions](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): Testcontainers 1.21.4 module names, JDBC driver, JUnit.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): Docker API version considerations and test setup.
- [Spring Framework 6.2 — Context caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): shared TestContext cache, dirtiness, LRU and lifecycle.
- [Docker — Container networking](https://docs.docker.com/engine/network/): container networks, published ports, aliases and host reachability.
