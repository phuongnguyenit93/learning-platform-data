# Tách cấu hình phát triển, kiểm thử và production

Ứng dụng Spring Data R2DBC thường chạy ở nhiều môi trường: máy cá nhân của lập trình viên, môi trường kiểm thử tự động, staging và production. Mỗi môi trường có thể dùng database host, credentials, pool size, timeout, logging level và chính sách migration khác nhau. Nếu trộn các giá trị này vào code hoặc dùng một file cấu hình duy nhất với nhiều giá trị cố định, việc triển khai dễ sai môi trường, lộ bí mật hoặc gây tải không phù hợp lên database.

Spring Boot hỗ trợ externalized configuration và profiles để tách cấu hình theo môi trường. Mục tiêu là giữ logic ứng dụng giống nhau, còn những giá trị phụ thuộc môi trường được cung cấp từ file cấu hình, environment variables, command-line arguments, secret manager hoặc nền tảng triển khai. Cần xác định rõ nguồn cấu hình nào có độ ưu tiên cao hơn, profile nào được kích hoạt và ứng dụng phải làm gì khi thiếu cấu hình bắt buộc.

## 1. Những gì nên khác nhau giữa các môi trường?

Một số giá trị thường thay đổi:

| Nhóm cấu hình | Development | Test | Production |
| --- | --- | --- | --- |
| Database endpoint | Local container hoặc máy dev | Database test cô lập | Managed database/cluster |
| Credentials | Tài khoản dev riêng | Tài khoản test tạm thời | Secret được quản lý an toàn |
| Database/schema | Dữ liệu thử nghiệm | Database reset được | Dữ liệu thật, cần bảo vệ |
| Pool size | Nhỏ, tiện debug | Theo số test đồng thời | Theo capacity và connection budget |
| Timeout | Có thể dài hơn khi debug | Có deadline để test không treo | Theo SLO và request deadline |
| Logging | DEBUG khi cần | INFO hoặc log test | INFO/WARN, tránh lộ dữ liệu |
| Migration | Có thể tự chạy lúc khởi động | Tạo schema từ migration | Job/stage được kiểm soát |
| Observability | Console/local metrics | Test reports | Metrics, tracing, alerting |

Không nên tạo một bộ code riêng cho từng môi trường. Các profile chỉ thay đổi cấu hình và một số bean thực sự cần khác biệt; quy tắc nghiệp vụ và mapping entity nên giữ thống nhất.

## 2. Externalized configuration trong Spring Boot

Spring Boot có thể đọc cấu hình từ nhiều nguồn:

- File `application.yml` hoặc `application.properties` trong ứng dụng.
- File theo profile như `application-dev.yml`, `application-test.yml`.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Config tree hoặc secret được mount thành file.
- Các nguồn cấu hình ngoài được tích hợp qua cơ chế Spring Boot phù hợp.

Các nguồn này có thứ tự ưu tiên. Những nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị trong file cấu hình. Vì vậy, một giá trị trong `application.yml` không nhất thiết là giá trị runtime cuối cùng nếu môi trường triển khai truyền biến môi trường hoặc command-line argument khác.

Ví dụ:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop
    username: shop_dev
    password: dev_only_password
~~~

Khi chạy production, biến môi trường có thể ghi đè:

~~~text
SPRING_R2DBC_URL=r2dbc:postgresql://db.internal:5432/shop
SPRING_R2DBC_USERNAME=shop_app
SPRING_R2DBC_PASSWORD=<injected-secret>
~~~

Không lưu password thật vào source control. Giá trị ví dụ trong tài liệu chỉ dành cho local; môi trường thật phải lấy credentials từ secret manager hoặc cơ chế bảo mật của nền tảng.

## 3. Dùng Spring Profiles

Profiles cho phép khai báo cấu hình hoặc bean chỉ hoạt động trong môi trường được chọn.

Cấu trúc file thường gặp:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
└── application-prod.yml
~~~

`application.yml` chứa cấu hình chung; file theo profile chỉ chứa phần khác biệt.

Kích hoạt profile bằng environment variable:

~~~text
SPRING_PROFILES_ACTIVE=dev
~~~

Hoặc command line:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Không nên mặc định kích hoạt profile production trong artifact hoặc code. Môi trường triển khai chịu trách nhiệm chọn profile phù hợp. Với production, nên cấu hình profile rõ ràng và kiểm tra giá trị effective khi ứng dụng khởi động.

## 4. Cấu hình chung trong application.yml

Ví dụ cấu hình chung cho ứng dụng R2DBC:

~~~yaml
spring:
  application:
    name: order-service

  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-idle-time: 10m
      max-life-time: 30m
      max-acquire-time: 2s

  sql:
    init:
      mode: never

server:
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Đây là ví dụ khung; property được hỗ trợ và cách bind phụ thuộc phiên bản Spring Boot, Spring Data Relational và R2DBC Pool. Nếu cấu hình pool bằng URL hoặc custom `ConnectionFactory` bean, cần bảo đảm các thuộc tính trên thực sự được áp dụng cho factory đang được sử dụng.

Không đưa endpoint, credentials hoặc pool size production vào cấu hình chung nếu các môi trường cần giá trị khác nhau. Cấu hình chung nên chứa defaults an toàn và các thiết lập không phụ thuộc môi trường.

## 5. Profile development

File `application-dev.yml` có thể dùng database local:

~~~yaml
spring:
  config:
    activate:
      on-profile: dev

  r2dbc:
    url: r2dbc:postgresql://localhost:5432/shop_dev
    username: shop_dev
    password: dev_only_password
    pool:
      initial-size: 1
      max-size: 5
      max-acquire-time: 5s

  flyway:
    enabled: true
    url: jdbc:postgresql://localhost:5432/shop_dev
    user: shop_dev
    password: dev_only_password
    locations: classpath:db/migration

logging:
  level:
    root: INFO
    org.springframework.data.r2dbc: DEBUG
    io.r2dbc.postgresql.QUERY: DEBUG
~~~

Development có thể ưu tiên dễ khởi động và quan sát:

- Dùng database local hoặc container riêng.
- Dùng tài khoản không có quyền production.
- Pool nhỏ để dễ nhận biết giới hạn và không chiếm nhiều connection.
- Bật log SQL khi cần điều tra.
- Có thể chạy migration tự động để developer luôn có schema mới.

Không bật log bind parameter có thể chứa password, token, email hoặc dữ liệu cá nhân. Nếu cần xem SQL, hãy cấu hình logging an toàn và chỉ dùng dữ liệu giả.

## 6. Profile test

Test cần môi trường có thể tạo, làm sạch và tái lập. Một cấu hình profile đơn giản:

~~~yaml
spring:
  config:
    activate:
      on-profile: test

  r2dbc:
    url: r2dbc:postgresql://localhost:5433/shop_test
    username: shop_test
    password: test_only_password
    pool:
      initial-size: 1
      max-size: 4
      max-acquire-time: 3s

  flyway:
    enabled: true
    url: jdbc:postgresql://localhost:5433/shop_test
    user: shop_test
    password: test_only_password

logging:
  level:
    root: WARN
~~~

Test profile nên:

- Dùng database riêng, không bao giờ trỏ vào production.
- Chạy migration để tạo schema như môi trường thật.
- Dùng dữ liệu fixture có thể tái lập.
- Có timeout để test treo thất bại nhanh.
- Pool đủ cho concurrency của test nhưng không quá lớn.
- Không phụ thuộc vào dữ liệu còn lại từ lần chạy trước.

Với integration test, Testcontainers thường phù hợp hơn một database embedded khác engine vì có thể chạy đúng database mà production sử dụng.

## 7. Profile production

File `application-prod.yml` chỉ nên chứa defaults và cấu hình không bí mật. Endpoint và secret thường được inject từ nền tảng:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod

  r2dbc:
    pool:
      enabled: true
      initial-size: 10
      max-size: 30
      max-acquire-time: 1s
      max-idle-time: 10m
      max-life-time: 30m

  flyway:
    enabled: false

server:
  shutdown: graceful

logging:
  level:
    root: INFO
    org.springframework.data.r2dbc: INFO

management:
  endpoint:
    health:
      show-details: never
~~~

Các con số pool và timeout chỉ là ví dụ, không phải giá trị production mặc định. Cần tính theo số application instances, giới hạn connection của database, query concurrency, transaction duration và SLO.

Migration production có thể chạy trong deployment job riêng rồi mới rollout ứng dụng. Nếu tổ chức chọn chạy migration khi ứng dụng khởi động, phải có lock/coordination và tài khoản migration phù hợp; không để mọi instance tùy tiện dùng tài khoản DDL rộng.

## 8. Phân biệt R2DBC URL và JDBC URL

Spring Data R2DBC dùng R2DBC driver để thực hiện truy vấn nghiệp vụ. Flyway/Liquibase trong cấu hình phổ biến dùng JDBC để thực thi schema migration.

Ví dụ:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/shop
    username: shop_app
    password: ${DB_APP_PASSWORD}

  flyway:
    url: jdbc:postgresql://db.internal:5432/shop
    user: shop_migrator
    password: ${DB_MIGRATION_PASSWORD}
~~~

Hai URL có protocol khác nhau và có thể dùng hai tài khoản khác nhau:

- `r2dbc:` cho repository, `R2dbcEntityTemplate` và `DatabaseClient`.
- `jdbc:` cho công cụ migration JDBC.

Runtime cần dependency driver tương ứng cho mỗi protocol nếu cả hai được dùng trong cùng artifact. Việc dùng JDBC ở migration stage không biến truy vấn nghiệp vụ thành blocking JDBC.

## 9. Tách tài khoản runtime và tài khoản migration

Không nên dùng cùng một database user có quyền DDL rộng cho cả ứng dụng và migration.

Một mô hình phân quyền:

| Tài khoản | Quyền thường cần |
| --- | --- |
| Application user | SELECT/INSERT/UPDATE/DELETE trên bảng cần thiết |
| Migration user | CREATE/ALTER và cập nhật migration history |
| Test user | Quyền phù hợp trên database test có thể reset |
| Read-only user | SELECT trên bảng/schema được phép nếu dùng replica |

Tách quyền giúp giảm tác động nếu ứng dụng runtime có lỗi hoặc bị khai thác. Application user không nên là database owner/superuser chỉ để tiện chạy migration.

Credentials production nên được quản lý bởi secret manager, Kubernetes Secret hoặc cơ chế tương đương; giới hạn ai được đọc và luân chuyển khi cần. Không commit file chứa secret thật.

## 10. Environment variables và placeholder

Spring Boot hỗ trợ placeholder để lấy giá trị từ property source:

~~~yaml
spring:
  r2dbc:
    url: ${DB_R2DBC_URL}
    username: ${DB_R2DBC_USERNAME}
    password: ${DB_R2DBC_PASSWORD}
~~~

Có thể khai báo default cho local:

~~~yaml
spring:
  r2dbc:
    url: ${DB_R2DBC_URL:r2dbc:postgresql://localhost:5432/shop_dev}
    username: ${DB_R2DBC_USERNAME:shop_dev}
    password: ${DB_R2DBC_PASSWORD:}
~~~

Default rỗng cho password có thể khiến ứng dụng khởi động nhưng kết nối thất bại sau đó. Với production, nên yêu cầu biến bắt buộc và fail fast nếu thiếu. Không dùng giá trị mặc định là password thật hoặc tài khoản có quyền cao.

Environment variable thường dùng tên uppercase với dấu gạch dưới, ví dụ `SPRING_R2DBC_URL` hoặc `DB_R2DBC_URL`. Hãy thống nhất một quy ước để tránh hai property cùng biểu diễn một cấu hình nhưng có nguồn ghi đè khó hiểu.

## 11. Fail fast khi thiếu cấu hình bắt buộc

Nếu database URL hoặc credentials production không có, ứng dụng nên báo lỗi cấu hình ngay lúc khởi động thay vì dùng một endpoint mặc định không đúng.

Có thể dùng constructor binding với `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.database")
@Validated
public record DatabaseSettings(
        @NotBlank String role,
        @NotBlank String environment
) {}
~~~

Khai báo enable properties:

~~~java
@Configuration
@EnableConfigurationProperties(DatabaseSettings.class)
public class AppConfiguration {
}
~~~

Với R2DBC connection settings, Spring Boot có cấu hình riêng. Không tạo một class custom trùng prefix `spring.r2dbc` nếu không cần. Dùng custom properties cho các giá trị ứng dụng sở hữu, ví dụ routing policy hoặc consistency mode.

Validation giúp phát hiện property thiếu/sai ngay khi bind. Với secret, tránh đưa giá trị secret vào exception message hoặc log cấu hình.

## 12. Tránh phụ thuộc nhầm profile

Có thể kích hoạt nhiều profile cùng lúc:

~~~text
SPRING_PROFILES_ACTIVE=prod,metrics
~~~

Spring Boot áp dụng cấu hình của các profile đã kích hoạt theo thứ tự và property precedence. Profile nhóm như `metrics` có thể bật observability; profile môi trường như `prod` cung cấp endpoint/timeout.

Không nên tạo quá nhiều profile chồng chéo như `prod-eu`, `prod-us`, `prod-large-pool`, `prod-debug` nếu phần lớn chỉ khác vài property. Dùng environment variables cho giá trị triển khai và profile cho các nhóm cấu hình có ý nghĩa rõ ràng.

Không kích hoạt đồng thời `dev` và `prod` trừ khi đã xác định chính xác quy tắc override. Nếu profile xung đột, một giá trị có thể ghi đè ngoài dự kiến.

## 13. Profile-specific beans với @Profile

Ngoài YAML, `@Profile` có thể giới hạn bean:

~~~java
@Configuration
public class DatabaseDiagnosticsConfiguration {

    @Bean
    @Profile({"dev", "test"})
    DatabaseDiagnostics databaseDiagnostics() {
        return new VerboseDatabaseDiagnostics();
    }

    @Bean
    @Profile("prod")
    DatabaseDiagnostics productionDiagnostics() {
        return new SafeDatabaseDiagnostics();
    }
}
~~~

Chỉ dùng profile-specific bean khi hành vi hoặc implementation thực sự khác. Không tạo hai repository implementation chỉ vì URL database khác; để cấu hình connection factory xử lý endpoint.

Nếu không có profile nào được chọn, ứng dụng cần hành vi mặc định an toàn. Có thể dùng profile mặc định `default` hoặc validation yêu cầu profile cụ thể tùy cách triển khai. Tránh để môi trường production vô tình chạy bean dev.

## 14. Kiểm tra profile đang hoạt động

Có thể xem active profiles qua Actuator `env` nếu endpoint được expose và bảo vệ, hoặc ghi log một thông tin không nhạy cảm lúc startup:

~~~java
@Component
public class ActiveProfileLogger implements ApplicationRunner {

    private final Environment environment;

    public ActiveProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info(
                "Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles())
        );
    }
}
~~~

Không log toàn bộ Environment hoặc tất cả property values; chúng có thể chứa password, token và connection string nhạy cảm. Chỉ ghi tên profile và các thông tin không bí mật cần thiết.

## 15. Connection pool khác nhau theo môi trường

Pool size cần được chọn theo capacity database và số instance, không theo một con số chung:

- Development: pool nhỏ để tránh chiếm connection và dễ debug.
- Test: pool đủ cho test concurrency; mỗi test suite có thể cần database/container riêng.
- Production: pool dựa trên throughput, connection hold time, số instance, replica topology và database connection limit.

Ví dụ cấu hình theo profile:

~~~yaml
# application-dev.yml
spring:
  r2dbc:
    pool:
      initial-size: 1
      max-size: 5
      max-acquire-time: 5s
~~~

~~~yaml
# application-prod.yml
spring:
  r2dbc:
    pool:
      initial-size: 10
      max-size: 30
      max-acquire-time: 1s
~~~

Đừng sao chép các giá trị minh họa này mà không đo. Tổng số connection có thể được ước tính:

~~~text
possible connections =
    application instances * pool max size
    + worker pools
    + migration/admin/monitoring clients
    + other services
~~~

Nếu có writer và reader pool, cộng cả hai. Tính theo số replica tối đa khi autoscaling hoặc rolling deployment có thể làm số instance tăng tạm thời.

## 16. Timeout theo môi trường và latency budget

Timeout cần phù hợp với deadline của request:

- Pool acquire timeout: giới hạn thời gian chờ connection.
- Query/statement timeout: giới hạn thời gian database thực thi.
- HTTP client timeout: giới hạn thời gian chờ dependency ngoài.
- Request timeout: deadline tổng của use case/HTTP.

Ví dụ local có thể dùng timeout dài hơn để debug query, nhưng production phải có deadline hữu hạn để tránh giữ request và resource quá lâu.

Không đặt query timeout lớn hơn request deadline một cách vô nghĩa; khi request đã timeout và bị cancel, câu SQL có thể vẫn chạy tùy driver/database. Cần phối hợp timeout ở Reactor, driver và database.

Test nên có timeout đủ ngắn để phát hiện deadlock hoặc publisher không kết thúc, nhưng không quá ngắn đến mức tạo flaky test trên CI chậm.

## 17. Migration trong development, test và production

Schema cần được quản lý bằng migration như Flyway hoặc Liquibase. Chính sách có thể khác theo môi trường:

| Môi trường | Chính sách thường dùng |
| --- | --- |
| Development | Auto-migrate lúc app khởi động để cập nhật schema local |
| Test | Chạy migration trước integration test hoặc khi test context tạo database |
| Staging | Chạy migration theo deployment job và kiểm tra trước rollout |
| Production | Job/stage có kiểm soát, backup và phê duyệt theo quy trình |

Nếu ứng dụng dùng R2DBC nhưng Flyway/Liquibase chạy bằng JDBC, cần cấu hình JDBC URL và driver riêng. Không nhầm `spring.r2dbc.url` với `spring.flyway.url` hoặc `spring.liquibase.url`.

Không để mọi pod production tự ý chạy migration bằng application user có quyền DDL. Nếu chạy migration trong startup, phải hiểu lock behavior, startup ordering và quyền của tài khoản.

## 18. Testcontainers thay vì dùng database production

Integration test nên dùng database cô lập:

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16")
                    .withDatabaseName("shop_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://" + postgres.getHost()
                        + ":" + postgres.getMappedPort(5432)
                        + "/" + postgres.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }
}
~~~

Ví dụ minh họa cấu hình R2DBC properties từ Testcontainers. Nếu dùng Flyway, cũng cần cấu hình JDBC URL/credentials tương ứng cho cùng container. Tên image, version và dependency Testcontainers nên được pin phù hợp với database production.

Testcontainers giúp kiểm tra SQL dialect, mapping, constraint và transaction trên engine thật. Nó không thay thế unit test và cũng không nên kết nối nhầm vào database thật.

## 19. Cấu hình migration cho Testcontainers

Nếu Flyway chạy trong test context, thêm JDBC driver và cấu hình JDBC URL:

~~~java
@DynamicPropertySource
static void configureProperties(DynamicPropertyRegistry registry) {
    String host = postgres.getHost();
    int port = postgres.getMappedPort(5432);
    String database = postgres.getDatabaseName();

    registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://" + host + ":" + port + "/" + database
    );
    registry.add("spring.r2dbc.username", postgres::getUsername);
    registry.add("spring.r2dbc.password", postgres::getPassword);

    registry.add("spring.flyway.url", () ->
            "jdbc:postgresql://" + host + ":" + port + "/" + database
    );
    registry.add("spring.flyway.user", postgres::getUsername);
    registry.add("spring.flyway.password", postgres::getPassword);
}
~~~

Đây là ví dụ cho Flyway. Với Liquibase, dùng các property tương ứng. Cấu hình test không nên dùng lại credentials hoặc host từ profile production.

Nếu migration chạy ở test setup riêng, có thể tắt auto-migration trong Spring context để tránh chạy hai lần, nhưng cần bảo đảm migration đã chạy trước khi repository test thực thi.

## 20. Test profile và dữ liệu fixture

Không nên phụ thuộc vào dữ liệu do developer nhập thủ công trong local database. Test cần dữ liệu có thể tái tạo:

- Tạo fixture bằng SQL hoặc builder trong test.
- Dùng ID xác định nếu test cần tham chiếu.
- Dọn dữ liệu hoặc tạo database/container mới theo suite.
- Không dùng dữ liệu production thật nếu không có quy trình ẩn danh và phê duyệt.
- Kiểm tra thứ tự test không ảnh hưởng lẫn nhau.

Nếu test chạy song song, tránh dùng chung một database/schema với dữ liệu mutable mà không có isolation. Có thể tạo schema/database riêng hoặc namespace dữ liệu theo test.

## 21. Docker Compose cho development

Một môi trường local có thể dùng Docker Compose:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: shop_dev
      POSTGRES_USER: shop_dev
      POSTGRES_PASSWORD: dev_only_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U shop_dev -d shop_dev"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  postgres_data:
~~~

Password trong Compose này chỉ là ví dụ local. Không tái sử dụng cho staging hoặc production. Nếu dữ liệu local cần reset, có thể xóa volume có chủ đích; thao tác đó sẽ xóa database local.

Ứng dụng chạy trên host dùng localhost. Nếu ứng dụng cũng chạy trong Compose network, hostname thường là tên service `postgres`, không phải localhost.

## 22. Docker/Kubernetes và cấu hình production

Trong container, cấu hình thường được inject qua environment variables hoặc mounted secrets:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: prod
  - name: SPRING_R2DBC_URL
    valueFrom:
      configMapKeyRef:
        name: order-service-config
        key: r2dbc-url
  - name: SPRING_R2DBC_USERNAME
    valueFrom:
      secretKeyRef:
        name: order-service-db
        key: username
  - name: SPRING_R2DBC_PASSWORD
    valueFrom:
      secretKeyRef:
        name: order-service-db
        key: password
~~~

Ví dụ Kubernetes manifest này chỉ minh họa cách tham chiếu ConfigMap/Secret; không đặt secret value trực tiếp vào YAML được commit. Trong hệ thống thật, áp dụng RBAC, encryption at rest, secret rotation và quyền đọc tối thiểu.

ConfigMap phù hợp cho giá trị không bí mật như endpoint nội bộ hoặc feature setting. Secret phù hợp cho password/token, nhưng cần cấu hình bảo vệ của cluster; tên object là Secret không tự đảm bảo an toàn nếu quyền truy cập và encryption chưa được thiết lập.

## 23. Graceful shutdown và pool lifecycle

Production cần dừng ứng dụng có kiểm soát:

- Ngừng nhận request mới.
- Cho request đang xử lý hoàn tất trong thời gian grace period.
- Đóng publisher/consumer nền theo lifecycle.
- Đóng connection pool sau khi không còn thao tác đang chạy.
- Không ngắt database transaction giữa chừng nếu có thể tránh.

Spring Boot hỗ trợ graceful shutdown ở web server; cần cấu hình thời gian chờ phù hợp với nền tảng orchestrator. Worker nền và custom connection pool cần có lifecycle bean rõ ràng để được đóng đúng cách.

Không tự tạo một pool trong mỗi request hoặc mỗi lần gọi service. Pool là tài nguyên ứng dụng có vòng đời dài, thường được Spring quản lý dưới dạng bean.

## 24. Logging theo môi trường

Development có thể cần log SQL để hiểu mapping/query. Production cần log đủ để vận hành nhưng tránh lộ thông tin nhạy cảm.

Ví dụ:

~~~yaml
# application-dev.yml
logging:
  level:
    root: INFO
    org.springframework.data.r2dbc: DEBUG
~~~

~~~yaml
# application-prod.yml
logging:
  level:
    root: INFO
    org.springframework.data.r2dbc: INFO
~~~

Không bật log parameter nhạy cảm trong production. Khi điều tra query chậm, ưu tiên tracing, query metrics và slow query log đã kiểm soát. Log level quá chi tiết có thể làm tăng I/O, dung lượng log và rủi ro dữ liệu.

## 25. Observability theo môi trường

Development:

- Health check và log console.
- Metrics local khi cần điều tra.
- Có thể bật debug endpoint nhưng chỉ trong môi trường tin cậy.

Test:

- Thu test report, log lỗi và thời gian query.
- Có thể bật metric để phát hiện pool leak hoặc test treo.
- Không expose endpoint quản trị ra network ngoài.

Production:

- Health/readiness/liveness được cấu hình phù hợp.
- Metrics cho HTTP, JVM, R2DBC pool và database.
- Distributed tracing với sampling policy.
- Alert cho pool pending, acquire timeout, query latency và database errors.
- Endpoint quản trị được bảo vệ và chỉ expose những gì cần.

Không expose `env`, `configprops`, heap dump hoặc thread dump công khai. Các endpoint này có thể tiết lộ cấu hình, secret hoặc dữ liệu runtime.

## 26. Readiness khi database chưa sẵn sàng

Ứng dụng có thể khởi động trước khi database sẵn sàng hoặc mất kết nối sau đó. Cần phân biệt:

- Liveness: tiến trình có còn hoạt động không?
- Readiness: instance có thể nhận traffic không?
- Startup probe: ứng dụng đã hoàn tất khởi động chưa?

Nếu readiness kiểm tra database, một sự cố database có thể khiến instance ngừng nhận traffic; điều này có thể phù hợp hoặc không tùy kiến trúc. Không cấu hình liveness phụ thuộc trực tiếp vào database một cách tùy tiện, vì database lỗi có thể khiến orchestrator liên tục restart tất cả instance và làm sự cố nặng hơn.

Health indicator R2DBC và chi tiết response nên được bảo vệ. Kiểm tra connection ở health endpoint cũng tạo tải database, nên đặt tần suất và timeout hợp lý.

## 27. Cấu hình profile không thay thế feature flags

Profiles thích hợp cho khác biệt cấu hình theo môi trường hoặc lựa chọn bean lúc khởi động. Feature flags phù hợp hơn khi cần bật/tắt tính năng theo tenant, người dùng hoặc rollout dần trong cùng một môi trường.

Không tạo profile mới cho mọi lần rollout một tính năng. Ví dụ `prod-new-checkout` và `prod-old-checkout` có thể làm cấu hình phức tạp; feature flag có thể quản lý trạng thái tính năng rõ hơn.

Nếu feature flag ảnh hưởng đến schema, vẫn phải bảo đảm schema tương thích với cả code path bật và tắt trong giai đoạn rollout.

## 28. Không dùng profile để che giấu cấu hình nguy hiểm

Không nên có:

~~~yaml
spring:
  r2dbc:
    url: ${SPRING_R2DBC_URL:r2dbc:postgresql://production-db:5432/shop}
    username: ${SPRING_R2DBC_USERNAME:admin}
    password: ${SPRING_R2DBC_PASSWORD:admin}
~~~

Nếu biến môi trường thiếu, ứng dụng có thể âm thầm kết nối production bằng credentials mặc định. Đây là cấu hình nguy hiểm.

Thay vào đó, production nên yêu cầu các biến bắt buộc, không có default nhạy cảm; local có thể cung cấp default trong profile dev riêng. Hãy xác minh active profile và connection endpoint không phải production trước khi chạy test hoặc script phá hủy dữ liệu.

## 29. Kiểm thử cấu hình profile

Nên có test xác nhận cấu hình được bind đúng:

- Profile dev dùng database local/test endpoint.
- Profile test không bao giờ dùng production host.
- Profile prod yêu cầu secret/URL bắt buộc.
- Pool max size và acquire timeout đúng theo property source.
- Migration được bật/tắt đúng chính sách.
- Logging và Actuator exposure không vượt yêu cầu.

Có thể dùng `ApplicationContextRunner` hoặc `@SpringBootTest` với profile/property override để kiểm tra bean và configuration binding. Không chỉ kiểm tra file YAML bằng mắt; property precedence có thể làm runtime nhận giá trị khác.

Với custom `@ConfigurationProperties`, kiểm tra validation và trường hợp thiếu property. Với R2DBC, integration test nên xác nhận kết nối thực sự đến đúng database.

## 30. Kiểm tra effective configuration an toàn

Khi có nhiều nguồn cấu hình, cần biết giá trị cuối cùng đến từ đâu. Có thể:

- Ghi log active profiles.
- Dùng Actuator `env`/`configprops` trong môi trường dev có bảo vệ.
- Dùng startup validation để xác nhận endpoint và pool bounds.
- Kiểm tra environment variables trong deployment manifest.
- Không in password, token hoặc full secret.

Một startup validator có thể kiểm tra hostname hoặc database name nằm trong allowlist cho môi trường:

~~~java
@Component
public class DatabaseTargetValidator implements ApplicationRunner {

    private final Environment environment;

    public DatabaseTargetValidator(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] profiles = environment.getActiveProfiles();
        String url = environment.getProperty("spring.r2dbc.url", "");

        if (Arrays.asList(profiles).contains("test")
                && url.contains("production-db")) {
            throw new IllegalStateException(
                    "Test profile must not connect to production database"
            );
        }
    }
}
~~~

Đây là ví dụ minh họa; allowlist thực tế nên parse host/database theo URL thay vì kiểm tra chuỗi con. Không log URL nếu nó chứa credentials hoặc query parameter nhạy cảm.

## 31. Cấu hình theo môi trường và nhiều database

Một ứng dụng có thể có primary/replica hoặc database cho nhiều bounded context. Khi đó không nên chỉ đổi một property `spring.r2dbc.url` nếu cần nhiều connection factory.

Có thể định nghĩa custom properties:

~~~yaml
app:
  database:
    writer:
      url: ${DB_WRITER_URL}
      username: ${DB_WRITER_USERNAME}
      password: ${DB_WRITER_PASSWORD}
    reader:
      url: ${DB_READER_URL}
      username: ${DB_READER_USERNAME}
      password: ${DB_READER_PASSWORD}
~~~

Mỗi môi trường cung cấp giá trị tương ứng. Các bean ConnectionFactory cần được cấu hình tường minh bằng qualifiers và pool riêng. Nếu chỉ có một database, không tạo cấu hình phức tạp này khi chưa cần.

## 32. Quản lý secrets và rotation

Secret có thể được cung cấp qua:

- Kubernetes Secret hoặc secret store tích hợp.
- Cloud secret manager.
- Vault hoặc nền tảng quản lý bí mật.
- Mounted file với quyền filesystem hạn chế.
- Environment variables do runtime inject, nếu phù hợp chính sách.

Các nguyên tắc:

- Không commit secret vào Git.
- Không đưa secret vào image/container layer.
- Giới hạn người và service được đọc.
- Không log property source hoặc exception chứa credential.
- Luân chuyển credentials theo quy trình.
- Có kế hoạch cập nhật pool/connection khi password thay đổi.

Nếu rotation làm connection mới dùng password mới nhưng connection cũ vẫn tồn tại, cần hiểu cách pool tái tạo connection và thời điểm restart/reload cần thiết. Không giả định mọi driver/pool tự động nhận secret mới sau khi file hoặc environment thay đổi.

## 33. Thay đổi cấu hình và rolling deployment

Khi đổi database endpoint, password hoặc pool size, cần xem xét các instance cũ và mới chạy đồng thời:

1. Secret/endpoint mới được cung cấp.
2. Instance mới khởi động và tạo pool mới.
3. Readiness xác nhận kết nối hoạt động.
4. Traffic chuyển dần sang instance mới.
5. Instance cũ dừng graceful và đóng pool.
6. Credentials cũ chỉ bị thu hồi sau khi không còn connection cần dùng.

Nếu thu hồi password cũ trước khi instance cũ shutdown, request đang chạy có thể gặp lỗi khi pool cần tạo connection mới. Kế hoạch rotation phải tính tới thời gian rollout và connection lifetime.

## 34. Cấu hình test không được làm thay đổi production

Các lệnh test, cleanup hoặc migration có thể phá hủy dữ liệu. Hãy bảo đảm:

- Test profile chỉ dùng database riêng.
- Testcontainers tạo database cô lập.
- Không lấy production URL từ environment chung khi chạy local test.
- Script reset/clean yêu cầu xác nhận hoặc chỉ cho phép trên hostname/schema test.
- CI dùng credentials có quyền hạn chế.
- Không dùng dữ liệu production thật trừ khi đã ẩn danh và được phê duyệt.

Một lỗi phổ biến là developer có `DB_URL` production trong shell profile, rồi chạy integration test với profile mặc định. Test có thể vô tình ghi/xóa dữ liệu thật nếu cấu hình không được kiểm soát.

## 35. Các lỗi thường gặp

1. **Để endpoint và password production trong application.yml.** Dễ lộ secret và kết nối nhầm môi trường.
2. **Không khai báo active profile khi triển khai.** Ứng dụng có thể dùng default configuration.
3. **Kích hoạt đồng thời dev và prod không có chủ đích.** Property override khó dự đoán.
4. **Dùng cùng database user cho runtime và migration.** Application được cấp quyền DDL không cần thiết.
5. **Nhầm R2DBC URL với JDBC URL.** Migration tool JDBC không dùng protocol R2DBC.
6. **Cấu hình pool quá lớn trên mọi instance.** Tổng connection có thể vượt database limit khi scale-out.
7. **Dùng pool production trong test song song.** Test có thể tranh connection hoặc kết nối nhầm endpoint.
8. **Chỉ sửa YAML nhưng không kiểm tra effective property.** Environment variable/command line có thể ghi đè.
9. **Dùng default credential khi thiếu secret.** Ứng dụng có thể khởi động với cấu hình không an toàn.
10. **Bật SQL DEBUG ở production.** Log có thể chứa dữ liệu nhạy cảm và tăng I/O.
11. **Để Actuator env/configprops mở công khai.** Có thể tiết lộ cấu hình nội bộ.
12. **Cho mọi pod chạy migration bằng tài khoản runtime.** Khó kiểm soát quyền và thứ tự.
13. **Không tính rolling deployment khi tính connection budget.** Số instance tạm thời có thể tăng gấp đôi.
14. **Không kiểm tra profile test trỏ đúng database.** Có nguy cơ ghi dữ liệu production.
15. **Tự tạo ConnectionPool trong mỗi request.** Pool không được tái sử dụng và gây cạn tài nguyên.
16. **Giả định secret rotation tự cập nhật connection đang mở.** Pool có thể tiếp tục dùng connection cũ.

## Quy trình lựa chọn nhanh

- Đặt cấu hình chung trong `application.yml`; chỉ đưa phần khác biệt vào file profile.
- Kích hoạt profile từ môi trường triển khai, không hardcode production.
- Dùng environment variables hoặc secret manager cho endpoint và credentials.
- Dùng database riêng cho development và test; ưu tiên Testcontainers cho integration test.
- Tách runtime user khỏi migration user và read-only user khi cần.
- Cấu hình pool/timeout theo workload và ngân sách tổng connection, không sao chép một giá trị cho mọi môi trường.
- Dùng Flyway/Liquibase với JDBC URL riêng nếu migration chạy bằng JDBC trong ứng dụng R2DBC.
- Chạy migration production trong stage/job có kiểm soát và rollout code tương thích với schema.
- Bảo vệ Actuator, không log secret và không bật SQL parameter logging nhạy cảm ở production.
- Kiểm tra effective configuration và active profiles lúc khởi động.
- Thiết kế graceful shutdown, readiness và secret rotation cho rolling deployment.
- Viết test xác nhận profile test không thể kết nối production.

Tách cấu hình development, kiểm thử và production giúp cùng một ứng dụng Spring Data R2DBC chạy nhất quán ở nhiều môi trường mà vẫn dùng đúng database, credentials, pool và chính sách vận hành. Dùng Spring Profiles cho nhóm cấu hình có ý nghĩa, externalized properties cho giá trị triển khai và secret manager cho thông tin nhạy cảm. Tính connection budget theo toàn bộ instance, tách tài khoản runtime khỏi migration, kiểm thử bằng database cô lập và xác minh cấu hình runtime thay vì chỉ đọc YAML. Khi migration, readiness, graceful shutdown và secret rotation được đưa vào quy trình triển khai, nguy cơ kết nối nhầm môi trường và lỗi vận hành giảm đáng kể.
