# Giữ kiểm thử độc lập, che bí mật và dọn tài nguyên sau khi chạy

Kiểm thử Spring Cloud Config thường cần nhiều thành phần cùng lúc: Config Server, Git repository, Config Client, message broker, Vault hoặc một dịch vụ giả lập. Nếu bài kiểm thử dùng chung repository, cổng mạng, credential hay dữ liệu giữa các lần chạy, kết quả có thể phụ thuộc vào thứ tự test hoặc trạng thái máy của người chạy. Test có thể pass trên máy lập trình viên nhưng thất bại trong CI, hoặc để lại tiến trình và dữ liệu làm ảnh hưởng lần chạy sau.

Một bộ kiểm thử đáng tin cậy cần ba nguyên tắc: **cô lập dữ liệu và hạ tầng**, **dùng bí mật giả và che đầu ra**, **dọn mọi tài nguyên do test tạo ra**. Với Spring Cloud Config, điều này đặc biệt quan trọng vì cấu hình được nạp sớm trong startup và có thể chứa credential. Bài học này trình bày cách dựng test fixture riêng cho từng test, cấp port động, quản lý lifecycle của container và mock server, đồng thời tránh để secret xuất hiện trong Git fixture, log hoặc báo cáo kiểm thử.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Thiết kế test độc lập với thứ tự chạy và trạng thái môi trường bên ngoài.
- Tạo Git repository tạm, commit và file cấu hình riêng cho mỗi test hoặc test class.
- Dùng `@TempDir`, random port và `@DynamicPropertySource` để tránh xung đột tài nguyên.
- Khởi chạy Config Server, Config Client, mock server hoặc Testcontainers với lifecycle rõ ràng.
- Phân biệt test unit, slice test và integration test để chọn đúng mức hạ tầng.
- Dùng secret giả, không dùng credential production trong test.
- Tránh rò rỉ bí mật qua log, assertion message, test report, HTTP trace và Actuator.
- Dọn repository, container, file, process, listener và context sau khi test kết thúc.
- Xử lý test song song, timeout và lỗi giữa chừng mà không để lại tài nguyên.

## 2. Ba nguyên tắc của một test độc lập

Một test độc lập phải tự tạo hoặc nhận một fixture có thể tái lập và không dựa vào trạng thái còn sót lại từ test khác.

| Nguyên tắc | Cách áp dụng | Lỗi cần tránh |
| --- | --- | --- |
| Cô lập dữ liệu | Temp directory, repository riêng, namespace riêng, test profile riêng | Hai test cùng ghi một thư mục Git hoặc cùng sửa một znode |
| Cô lập kết nối | Random port, container network riêng, mock endpoint cục bộ | Hard-code cổng `8888`, gọi Config Server staging hoặc Git production |
| Cô lập danh tính | Credential giả và token ngắn hạn của môi trường test | Dùng token Vault, Git PAT hoặc password thật |
| Tái lập | Fixture có nội dung và revision xác định | Phụ thuộc branch `main` đang thay đổi trên remote |
| Dọn dẹp | Lifecycle hook, try-with-resources và temporary directory | Để lại container, tiến trình, file clone hoặc listener |

Một test không độc lập nếu chỉ chạy được sau một test khác đã tạo dữ liệu. Không dùng thứ tự test như một cơ chế setup ngầm.

## 3. Chọn đúng mức kiểm thử

Không phải mọi test đều cần khởi động Config Server và Git backend thật.

| Loại test | Phạm vi | Hạ tầng nên dùng |
| --- | --- | --- |
| Unit test | Logic chọn cấu hình, mapping, validation, fallback | Mock `Environment`, repository interface hoặc collaborator |
| Spring context test | Binding `@ConfigurationProperties`, profile và bean wiring | Spring TestContext với property test riêng |
| Config Server integration test | Git backend, application/profile/label và Environment response | Config Server thật với Git repository tạm |
| Config Client integration test | Config Data import, kết nối server và property binding | Config Server local hoặc mock HTTP server |
| End-to-end test | Server, backend, client và refresh cùng hoạt động | Hạ tầng test cô lập, có thể dùng Testcontainers |

Chỉ dùng test end-to-end cho luồng mà unit/context test không chứng minh được. Khởi động nhiều container cho một phép kiểm tra binding đơn giản làm test chậm và tăng số điểm có thể lỗi.

## 4. Tạo Git repository tạm cho từng test

Git backend của Config Server cần một repository có thể đọc. Trong test, nên tạo repository dưới thư mục tạm thay vì trỏ vào repository thật hoặc remote dùng chung.

JUnit 5 cung cấp `@TempDir`. JUnit tạo thư mục tạm cho test và tự xóa sau khi test hoặc test class hoàn tất theo phạm vi injection.

Ví dụ:

```java
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ConfigRepositoryFixtureTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void createsRepositoryInsideTemporaryDirectory() {
        Path workingTree = temporaryDirectory.resolve("config-work");
        Path bareRepository = temporaryDirectory.resolve("config-repo.git");

        // Tạo working tree và bare repository tại đây.
        // Không ghi vào repository của dự án hoặc thư mục dùng chung.
    }
}
```

### Tạo repository bằng Git CLI

Có thể dùng `ProcessBuilder` để chạy Git CLI nếu CI đã cài Git. Mỗi test nên có working directory riêng, Git identity giả và remote cục bộ.

```java
static void runGit(Path workingDirectory, String... arguments)
        throws IOException, InterruptedException {
    List<String> command = new ArrayList<>();
    command.add("git");
    command.addAll(List.of(arguments));

    Process process = new ProcessBuilder(command)
            .directory(workingDirectory.toFile())
            .redirectErrorStream(true)
            .start();

    String output;
    try (var input = process.getInputStream()) {
        output = new String(input.readAllBytes(), StandardCharsets.UTF_8);
    }

    int exitCode = process.waitFor();
    if (exitCode != 0) {
        throw new IllegalStateException(
                "Git command failed with exit code " + exitCode
                + "; output: " + redact(output));
    }
}
```

Đây là helper minh họa. Trong code thực tế, cần đặt timeout cho process, tránh lệnh có thể chờ vô hạn và xử lý việc đọc output/stderr để không deadlock. Không đưa credential vào command line vì process list hoặc log CI có thể làm lộ giá trị. Fixture nên dùng `file://` hoặc path cục bộ, không cần token.

Ví dụ các bước setup:

```java
Path work = temporaryDirectory.resolve("work");
Path bare = temporaryDirectory.resolve("remote.git");
Files.createDirectories(work);

runGit(work, "init", "-b", "main");
runGit(work, "config", "user.name", "Config Test");
runGit(work, "config", "user.email", "config-test@example.invalid");

Files.writeString(work.resolve("orders.yml"), """
        orders:
          retry-count: 2
          banner: test-fixture
        """);

runGit(work, "add", "orders.yml");
runGit(work, "commit", "-m", "Create test configuration");
runGit(temporaryDirectory, "init", "--bare", bare.toString());
runGit(work, "remote", "add", "origin", bare.toString());
runGit(work, "push", "-u", "origin", "main");
```

Các lệnh trên cần được điều chỉnh theo phiên bản Git và môi trường chạy. Nếu muốn Config Server clone từ bare remote, dùng URI file được tạo từ `bare.toUri()`. Không ghép chuỗi `file://` bằng tay khi đường dẫn có ký tự đặc biệt.

### Vì sao mỗi test cần repository riêng?

Nếu test A push commit mới lên branch `main`, test B có thể đọc commit đó thay vì fixture ban đầu. Khi chạy song song, một test có thể đang checkout branch trong lúc test khác cập nhật ref. Repository riêng loại bỏ cạnh tranh này và giúp mỗi test xác định chính xác commit/tag/branch mà nó muốn kiểm tra.

## 5. Dùng random port thay vì hard-code cổng

Hai test chạy đồng thời không nên cùng bind cổng cố định `8888` hoặc `8080`. Cổng có thể đã bị tiến trình khác sử dụng hoặc bị test khác chiếm.

Với Spring Boot integration test:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ConfigServerHttpTest {

    @LocalServerPort
    int port;

    @Test
    void servesEnvironment() {
        URI uri = URI.create("http://localhost:" + port + "/orders/dev/main");
        // Gửi HTTP request và kiểm tra response.
    }
}
```

`RANDOM_PORT` để Spring Boot chọn cổng khả dụng cho test server. Client test phải dùng giá trị được inject, không giả định cổng mặc định.

Nếu test tự khởi tạo mock server, container hoặc socket, hãy dùng API random port của công cụ đó và đóng server trong lifecycle teardown. Không tự dò một cổng trống bằng cách mở rồi đóng socket trước khi server bind; có thể xảy ra race condition giữa hai thao tác.

## 6. Truyền thuộc tính động bằng `@DynamicPropertySource`

Config Server trong test thường chạy ở random port. `@DynamicPropertySource` cho phép đăng ký thuộc tính động từ fixture hoặc container cho các bean và thành phần đọc thuộc tính trong quá trình tạo Spring context.

Ví dụ khung:

```java
@SpringBootTest(
        classes = OrdersApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrdersConfigClientTest {

    static ConfigServerFixture configServer;

    @BeforeAll
    static void startConfigServer() {
        configServer = ConfigServerFixture.start();
    }

    @DynamicPropertySource
    static void configServerProperties(DynamicPropertyRegistry registry) {
        registry.add("orders.api.base-url", configServer::baseUrl);
    }

    @AfterAll
    static void stopConfigServer() {
        if (configServer != null) {
            configServer.close();
        }
    }
}
```

Đây là cấu trúc minh họa; `ConfigServerFixture` đại diện cho fixture do test tạo. `@DynamicPropertySource` phù hợp với thuộc tính mà bean đọc trong quá trình tạo context. Không mặc định rằng nó có thể cung cấp `spring.config.import` hoặc mọi thuộc tính được Config Data resolver đọc rất sớm; các giá trị đó cần có trước giai đoạn xử lý Config Data.

Nếu cần truyền URL random port vào Config Data import, có thể khởi chạy client sau khi fixture server đã sẵn sàng và truyền import location qua command-line arguments của `SpringApplication`:

```java
try (ConfigServerFixture server = ConfigServerFixture.start()) {
    SpringApplication clientApplication =
            new SpringApplication(OrdersApplication.class);

    try (ConfigurableApplicationContext context = clientApplication.run(
            "--spring.application.name=orders",
            "--spring.profiles.active=test",
            "--spring.config.import=configserver:" + server.baseUrl())) {
        OrdersProperties properties = context.getBean(OrdersProperties.class);
        // Assertion trên cấu hình đã được nạp từ Config Server.
    }
}
```

Command-line arguments được đưa vào Environment trước khi Spring Boot xử lý Config Data. Trong test thực tế, hãy truyền thêm các thuộc tính test cần thiết và bảo đảm `ConfigServerFixture.close()` dừng server sau khi client context đã đóng.

Không thay `spring.config.import` bằng URL production hoặc staging trong test. Nếu URL được đọc quá sớm, cần dùng cơ chế cung cấp property trước khi Config Data loader chạy.

## 7. Cô lập profile và property source

Test phải chỉ rõ application name, active profile, label và mọi override cần thiết. Tránh để môi trường của máy developer quyết định profile ngầm.

Ví dụ test properties:

```java
@SpringBootTest(properties = {
        "spring.application.name=orders",
        "spring.profiles.active=test",
        "spring.cloud.config.label=test-fixture"
})
class OrdersConfigurationTest {
}
```

Khi test Config Client với Config Data import, cần kiểm tra thứ tự property source thực tế. `@SpringBootTest(properties=...)`, `@DynamicPropertySource`, `@TestPropertySource`, system properties và environment variables có thể có độ ưu tiên khác nhau. Đừng chỉ nhìn file YAML để kết luận giá trị cuối cùng.

Các nguyên tắc:

- Dùng profile `test` hoặc profile fixture riêng, không dùng `prod`.
- Không phụ thuộc `SPRING_PROFILES_ACTIVE` đang có trên máy CI.
- Đặt application name tường minh để request đúng context.
- Dùng label/branch/tag được tạo riêng trong fixture.
- Không để test cùng sửa `System.setProperty` mà không khôi phục giá trị cũ.
- Nếu test cần thay `Environment`, tạo context mới hoặc khôi phục property source trong `finally`.

## 8. Dùng Testcontainers cho hạ tầng thật

Khi cần kiểm tra tương tác với ZooKeeper, Vault, RabbitMQ, Kafka hoặc Git service, Testcontainers có thể khởi chạy dịch vụ trong container dùng cho test.

Ví dụ RabbitMQ:

```java
@Testcontainers
class ConfigBusIntegrationTest {

    @Container
    static final RabbitMQContainer rabbit =
            new RabbitMQContainer("rabbitmq:3.13-management");

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }
}
```

Ví dụ cần được điều chỉnh theo phiên bản Testcontainers và module RabbitMQ đang dùng. Nên pin image tag cụ thể đã được kiểm thử, không dùng `latest`, để CI có kết quả tái lập.

Testcontainers quản lý vòng đời container thông qua JUnit integration. Với static `@Container`, container thường được chia sẻ trong phạm vi test class; với instance field, container có thể được khởi tạo/dừng theo từng test. Chọn phạm vi phù hợp với yêu cầu cô lập.

Không bật reusable containers trên CI nếu test yêu cầu trạng thái sạch. Container tái sử dụng có thể giữ volume, queue, topic hoặc secret từ lần chạy trước. Nếu dùng shared container để giảm thời gian, mỗi test vẫn phải tạo namespace, database/schema, queue hoặc dữ liệu có tên duy nhất và xóa sau khi hoàn tất.

## 9. Mock server khi không cần backend thật

Không phải test Config Client nào cũng cần một Config Server thật. Với test logic xử lý response HTTP hoặc lỗi kết nối, có thể dùng WireMock hoặc mock web server.

Các trường hợp phù hợp:

- Kiểm tra client gửi đúng application/profile/label.
- Kiểm tra response Environment có property source như mong đợi.
- Kiểm tra HTTP 401/403, 404, 5xx hoặc timeout.
- Kiểm tra retry/backoff và xử lý lỗi tạm thời.
- Kiểm tra response lỗi hoặc JSON không hợp lệ.

Mock server cần chạy trên random port và được đóng sau test. Stub phải được reset giữa các test để request mapping của test trước không ảnh hưởng test sau.

Không mock mọi thứ trong một bài test rồi kết luận Git backend hoặc Config Data integration hoạt động. Cần có một số integration test nhỏ dùng Config Server và Git thật trong fixture để xác nhận các thành phần kết nối đúng.

## 10. Dùng secret giả trong test

Test không cần credential production để chứng minh cơ chế cấu hình hoạt động. Dùng giá trị giả rõ ràng và không thể dùng để truy cập hệ thống thật.

Ví dụ:

```yaml
payments:
  api-key: TEST_ONLY_NOT_A_REAL_KEY
  username: test-user
  password: test-password-not-valid
```

Giá trị giả nên có prefix như `TEST_ONLY`, `DUMMY` hoặc `NOT_A_REAL_SECRET` để dễ nhận biết. Không dùng một chuỗi trông giống token thật được copy từ môi trường thật.

Với test Vault, tạo Vault dev/test instance hoặc mock backend và cấp policy/token dùng riêng cho test. Token cần quyền tối thiểu và vòng đời ngắn. Không dùng root token hoặc token production chỉ vì test cần đọc một secret.

Với test Git authentication, dùng repository cục bộ hoặc credential giả. Không nhúng PAT vào remote URL vì URL có thể xuất hiện trong log, exception hoặc process arguments.

## 11. Che bí mật trong log và báo cáo kiểm thử

Một test có thể vô tình in secret trong nhiều nơi:

- Log ứng dụng khi bind `@ConfigurationProperties` hoặc debug `Environment`.
- HTTP request/response logging.
- Assertion failure message.
- Exception message có URL chứa credential.
- CI test report, screenshot hoặc artifact.
- Actuator `/env`, `/configprops` và endpoint chẩn đoán.
- Trace span attributes hoặc metric tags.

Không log toàn bộ object cấu hình nếu nó có trường password/token. Thay vào đó, log tên application, profile, release ID và kết quả kiểm tra không nhạy cảm.

Ví dụ assertion an toàn:

```java
assertThat(properties.getApiKey()).isNotBlank();
assertThat(properties.getApiKey()).startsWith("TEST_ONLY");
```

Tránh assertion message đưa trực tiếp giá trị secret vào output:

```java
// Không nên: failure message có thể in giá trị nhạy cảm.
assertThat(actualSecret)
        .as("API key was %s", actualSecret)
        .isEqualTo(expectedSecret);
```

Nếu cần so sánh secret, báo kết quả chung hoặc fingerprint không thể đảo ngược theo chính sách nội bộ. Không dùng hash yếu của secret ngắn làm bằng chứng bảo mật; giá trị entropy thấp có thể bị dò từ điển.

### Không bật log quá chi tiết trong CI

Các logger HTTP, Spring Environment hoặc Vault client ở mức DEBUG/TRACE có thể in header, payload và metadata nhạy cảm. Chỉ bật tạm thời trong môi trường cô lập, có redaction và giới hạn quyền xem log. Tắt sau khi điều tra.

### Actuator trong test

Không expose `/actuator/env` hoặc `/actuator/configprops` rộng rãi chỉ để assertion. Nếu test cần kiểm tra giá trị, inject `Environment` hoặc properties bean trực tiếp trong test và chỉ assert các trường cần thiết. Nếu bắt buộc kiểm tra endpoint, dùng cấu hình security test và kiểm tra response không chứa secret.

## 12. Dọn tài nguyên bằng lifecycle rõ ràng

Mọi tài nguyên do test tạo phải có owner và điểm đóng cụ thể.

| Tài nguyên | Cách tạo | Cách dọn |
| --- | --- | --- |
| Thư mục/file fixture | `@TempDir` hoặc `Files.createTempDirectory` | JUnit tự dọn với `@TempDir`; nếu tự tạo thì xóa trong `finally` |
| Git process | `ProcessBuilder` | Đặt timeout, destroy process nếu cần và chờ process kết thúc |
| Git repository/clone | Thư mục tạm riêng | Xóa thư mục sau khi server/context đã đóng |
| Embedded server | `@SpringBootTest` hoặc test fixture | JUnit/Spring context đóng; custom server gọi `stop()`/`close()` |
| Mock HTTP server | WireMock/MockWebServer | `stop()` sau test và reset stub |
| Container | Testcontainers | JUnit extension dừng container; xóa volume/data nếu được tạo riêng |
| Executor/thread | ExecutorService | `shutdown()`, chờ termination rồi `shutdownNow()` nếu quá hạn |
| Listener/subscription | Event listener hoặc broker consumer | Unregister/close subscription và connection |
| System property | `System.setProperty` | Khôi phục giá trị cũ trong `finally` |

### Dùng try-with-resources

Với object triển khai `AutoCloseable`, ưu tiên try-with-resources:

```java
try (ConfigServerFixture server = ConfigServerFixture.start()) {
    // Chạy test khi fixture còn hoạt động.
}
```

Khi block kết thúc, `close()` được gọi kể cả khi assertion ném exception. Đây là cách tốt hơn việc chỉ gọi cleanup ở cuối test vì cleanup cuối test có thể không chạy khi test thất bại sớm.

### Dùng `@AfterEach` và `@AfterAll`

JUnit lifecycle hook phù hợp với resource không thể biểu diễn bằng try-with-resources:

```java
class ConfigFixtureTest {

    private ConfigServerFixture server;

    @BeforeEach
    void setUp() {
        server = ConfigServerFixture.start();
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.close();
            server = null;
        }
    }
}
```

Nếu nhiều resource phụ thuộc nhau, dọn theo thứ tự ngược với lúc tạo: dừng client trước, đóng server, đóng broker/container, rồi xóa thư mục repository. Không xóa repository trong khi Config Server vẫn có thể đọc nó.

## 13. Quản lý Spring ApplicationContext và `@DirtiesContext`

Spring TestContext cache application context để tăng tốc. Việc này có thể khiến bean singleton hoặc static state tồn tại giữa nhiều test method.

Nếu test thay đổi singleton state, system property hoặc context theo cách không thể khôi phục, có thể dùng `@DirtiesContext` để đánh dấu context cần đóng và tạo lại. Tuy nhiên, annotation này làm test chậm và không phải giải pháp mặc định cho mọi test.

Ưu tiên:

- Không mutate singleton bean state trong test nếu có thể.
- Dùng fixture riêng và reset state sau mỗi test.
- Tạo context mới khi test thực sự cần một cấu hình startup khác.
- Dùng `@DirtiesContext` có phạm vi hẹp khi test làm bẩn context và không thể khôi phục.
- Không dùng static mutable field để chia sẻ cấu hình giữa test class.

`@DynamicPropertySource` thường được xử lý khi context được tạo. Nếu một static property source thay đổi giữa các test nhưng context được cache, context có thể tiếp tục dùng giá trị cũ. Khi cần giá trị startup khác nhau, hãy dùng context configuration khác, context lifecycle riêng hoặc cơ chế reset phù hợp.

## 14. Test song song không được tranh chấp tài nguyên

JUnit có thể chạy test song song; Maven/Gradle cũng có thể chạy nhiều fork. Cần thiết kế tên tài nguyên riêng cho mỗi test.

Ví dụ:

- Mỗi test có temp directory riêng.
- Mỗi test tạo Git repository và branch riêng.
- Dùng random port thay vì `8888` cố định.
- Tạo queue/topic/database schema với suffix duy nhất.
- Không dùng một znode path chung có thể bị test khác xóa.
- Không thay đổi cùng một `System` property ở nhiều test song song.
- Không dùng một Vault path chung cho test chạy đồng thời.

Nếu cần dùng một container chung để tiết kiệm thời gian, dữ liệu bên trong phải có namespace riêng theo test ID và được xóa sau khi hoàn tất. Nếu không thể bảo đảm cô lập, tắt parallel execution cho nhóm test đó và ghi rõ lý do.

Không dùng `Thread.sleep()` để chờ Config Server hoặc Bus. Dùng Awaitility hoặc polling có timeout để đợi điều kiện cụ thể, ví dụ endpoint readiness, property revision mới hoặc event ACK. Polling phải có deadline để test không treo vô hạn.

## 15. Kiểm tra cleanup ngay cả khi test thất bại

Cleanup phải chạy khi:

- Assertion thất bại.
- Startup Config Server ném exception.
- Git clone thất bại.
- Container không ready.
- Test timeout hoặc bị interrupt.
- Một test bị skip sau khi fixture đã được tạo một phần.

Thiết kế fixture nên có trạng thái khởi tạo từng phần và `close()` an toàn khi một số thành phần chưa được tạo.

Ví dụ:

```java
final class ConfigServerFixture implements AutoCloseable {

    private Process process;
    private Path repositoryDirectory;

    @Override
    public void close() {
        if (process != null && process.isAlive()) {
            process.destroy();
            try {
                if (!process.waitFor(5, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor(5, TimeUnit.SECONDS);
                }
            } catch (InterruptedException ex) {
                process.destroyForcibly();
                Thread.currentThread().interrupt();
            }
        }

        // Chỉ xóa repository sau khi process/server đã dừng.
        // @TempDir có thể tự quản lý thư mục nếu fixture được tạo bên trong nó.
    }
}
```

Đây là khung minh họa; code thật cần quản lý timeout và lỗi cleanup sao cho không che mất exception gốc của test. Nếu cleanup thất bại, hãy ghi rõ resource nào chưa đóng, nhưng không in credential hoặc secret.

## 16. Dọn dữ liệu backend và trạng thái ngoài JVM

Một số trạng thái không nằm trong thư mục test:

- RabbitMQ queue/exchange.
- Kafka topic/consumer group.
- ZooKeeper znode.
- Vault KV path hoặc token.
- Database row/schema.
- Git branch/tag trong remote test.
- Service registry registration.

Các resource này phải có namespace hoặc prefix riêng, ví dụ `test-${randomId}`. Sau test, xóa đúng namespace do test tạo. Không dùng lệnh xóa wildcard trên một mount, topic hoặc namespace dùng chung.

Với ZooKeeper, tạo znode dưới test root riêng và chỉ xóa root đó sau khi client session đã đóng. Với Vault, dùng mount/namespace test hoặc path có prefix riêng; thu hồi token sau khi test. Với database, dùng transaction rollback khi phù hợp hoặc schema/database tạm.

Nếu backend test chạy trong container dùng một lần, ưu tiên xóa cả container và volume thay vì cố tái sử dụng trạng thái đã biết là bẩn.

## 17. Tránh phụ thuộc mạng và môi trường thật

Test chạy mặc định không nên gọi:

- Git remote production hoặc public repository không được kiểm soát.
- Config Server staging/production.
- Vault thật chứa secret vận hành.
- ZooKeeper ensemble dùng chung.
- Message broker dùng chung với workload thật.
- DNS hoặc API bên ngoài không ổn định.

Nếu cần kiểm tra tích hợp với dịch vụ bên ngoài, tạo một nhóm smoke test riêng, có credential test và được chạy theo pipeline có chủ đích. Đừng để unit/integration test thông thường phụ thuộc VPN, tài khoản người dùng hoặc trạng thái dịch vụ của team khác.

Khi dùng Testcontainers, CI runner phải có Docker hoặc runtime tương thích. Nếu không có, cấu hình test profile riêng để bỏ qua nhóm container integration test có điều kiện, nhưng không được âm thầm đánh dấu test đã chạy thành công. Báo rõ nhóm test nào bị skip.

## 18. Ma trận kiểm thử độc lập cho Spring Cloud Config

| Tình huống | Fixture | Điều cần xác minh | Cleanup |
| --- | --- | --- | --- |
| Git label selection | Git bare repository tạm với branch/tag/commit riêng | Config Server trả đúng revision theo label | Xóa temp repository sau khi server dừng |
| Profile precedence | Các file application/profile trong repo tạm | Giá trị cụ thể ghi đè giá trị chung đúng thứ tự | Xóa fixture directory |
| Config Client startup | Config Server local với random port | `spring.config.import` nạp đúng property | Đóng context/server |
| Config Server unavailable | Mock server hoặc port test không có listener | Required import fail; optional import theo fallback | Dừng mock server, đóng context |
| Refresh | Repo tạm có commit mới hoặc mock response mới | Client nhận revision mới và bean xử lý đúng | Đóng Bus/mock server, xóa repo |
| Bus propagation | RabbitMQ/Kafka container riêng | Event đến đúng client instance | Dừng consumer, container và xóa queue/topic |
| Vault backend | Vault test container/dev server | ACL giới hạn đúng path và secret giả được đọc | Thu hồi token, xóa test path/container |
| ZooKeeper backend | ZooKeeper test container | Client đọc đúng context và ACL | Đóng session, xóa test root/container |
| Secret masking | Secret giả trong fixture | Log/report không chứa giá trị | Xóa file/log artifact theo chính sách |

## 19. Quy trình xây dựng một test fixture có thể tái sử dụng

1. **Xác định phạm vi:** chọn unit, context, integration hay end-to-end test.
2. **Liệt kê dependency:** Git, Config Server, broker, Vault, ZooKeeper hoặc database nào thực sự cần.
3. **Chọn fixture riêng:** temp directory, random port, container hoặc mock server.
4. **Tạo dữ liệu giả:** application name, profile, label, secret và revision test-only.
5. **Cấu hình động:** truyền URL/port/credential test qua `@DynamicPropertySource` hoặc cơ chế phù hợp.
6. **Đợi readiness:** chỉ chạy assertion khi server/backend thực sự sẵn sàng.
7. **Thực hiện assertion:** kiểm tra response, binding, refresh và hành vi cần thiết.
8. **Che đầu ra:** lọc secret khỏi log, exception, report và trace.
9. **Đóng tài nguyên:** dùng try-with-resources, JUnit lifecycle hoặc Testcontainers extension.
10. **Xác minh dọn dẹp:** bảo đảm process, container, port, file và backend namespace đã được giải phóng.
11. **Chạy lặp và song song:** chạy test độc lập nhiều lần để phát hiện phụ thuộc thứ tự.

## 20. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Test pass riêng nhưng fail khi chạy cả suite | Chia sẻ file, port, system property hoặc singleton state | Tạo fixture riêng và reset state sau mỗi test |
| Test fail ngẫu nhiên trên CI | Cổng cố định, timing hoặc dependency mạng | Dùng random port, readiness polling và mock/local backend |
| Config Server trả commit không mong đợi | Git repository/branch dùng chung bị test khác sửa | Tạo bare repo riêng trong `@TempDir` |
| Test chạy lần hai thất bại | Container, znode, queue hoặc file còn sót | Bổ sung cleanup idempotent và namespace riêng |
| Test report chứa password/token | Assertion hoặc log in giá trị cấu hình | Dùng secret giả, redact output và chỉ assert presence/format |
| Config Client không dùng URL random port | Import location được cung cấp sau Config Data bootstrap hoặc context cache giữ giá trị cũ | Cung cấp import location trước Config Data processing và quản lý context lifecycle |
| Test song song xóa dữ liệu của nhau | Dùng chung path/schema/topic | Thêm test ID vào tên tài nguyên và cleanup đúng namespace |
| Test treo khi server không khởi động | Không có startup timeout hoặc process không được đóng | Đặt deadline và cleanup process/container khi setup lỗi |
| `@DirtiesContext` làm suite quá chậm | Dùng annotation ở phạm vi rộng | Giảm phạm vi, reset fixture hoặc tách test context |
| Cleanup che mất lỗi assertion ban đầu | `close()` ném exception ghi đè lỗi gốc | Thu thập cleanup error riêng và giữ exception gốc làm nguyên nhân chính |

## 21. Checklist trước khi đưa test vào CI

- [ ] Test không phụ thuộc thứ tự chạy hoặc dữ liệu từ test khác.
- [ ] Git repository, branch, tag và commit fixture được tạo riêng.
- [ ] Config Server/mock server dùng random port.
- [ ] URL và port được truyền động trước khi Config Client load Config Data.
- [ ] Profile, application name và label được khai báo tường minh.
- [ ] Không gọi Git, Vault, ZooKeeper, broker hoặc Config Server production/staging.
- [ ] Credential trong test đều là giá trị giả hoặc credential test-only.
- [ ] Log, assertion, exception, trace và report không chứa secret.
- [ ] Actuator endpoint nhạy cảm không được expose ngoài phạm vi test.
- [ ] Container image được pin version cụ thể.
- [ ] Container, process, executor, listener và context có lifecycle rõ ràng.
- [ ] Temporary directory và backend namespace được dọn cả khi test fail.
- [ ] Test parallel không tranh chấp port, branch, path, queue hoặc token.
- [ ] Có timeout cho startup, HTTP request, process và asynchronous assertion.
- [ ] Không dùng `Thread.sleep()` thay cho chờ điều kiện có deadline.
- [ ] Đã chạy test lặp lại và kiểm tra không còn resource sau suite.
- [ ] Nhóm test bị skip do thiếu Docker/hạ tầng được báo rõ, không giả thành pass.

## 22. Tài liệu tham khảo

- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers for Java](https://java.testcontainers.org/)
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
