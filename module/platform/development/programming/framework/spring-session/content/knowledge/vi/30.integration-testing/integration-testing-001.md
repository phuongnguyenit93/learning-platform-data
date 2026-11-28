# Dùng Redis và cơ sở dữ liệu thử nghiệm gần với môi trường triển khai

Spring Session lưu session trong repository bên ngoài tiến trình ứng dụng, thường là Redis hoặc JDBC. Vì vậy, một bài test chỉ dùng `MockHttpSession`, mock repository hoặc H2 in-memory có thể xác nhận logic controller nhưng không chứng minh được serializer, TTL, cookie, schema SQL, index, transaction và hành vi khi nhiều instance cùng truy cập.

Kiểm thử tích hợp đáng tin cậy nên dùng Redis và hệ quản trị cơ sở dữ liệu thật trong môi trường cô lập, thường được khởi chạy bằng Testcontainers. Phiên bản image, cấu hình, schema, encoding và cách kết nối cần gần với production. Mục tiêu là tái hiện các ranh giới thật giữa ứng dụng, Spring Session, cookie và kho dữ liệu; đồng thời giữ dữ liệu test độc lập để test có thể chạy lặp lại.

## 1. Vì sao cần Redis và database thật?

Các tầng test khác nhau phát hiện các loại lỗi khác nhau:

| Cách test | Phát hiện tốt | Không chứng minh đầy đủ |
|---|---|---|
| Unit test với mock repository | Logic nghiệp vụ, nhánh xử lý | Serialization, SQL, TTL và giao tiếp store |
| MockMvc với `MockHttpSession` | Mapping MVC, status, validation, một phần security flow | Cookie resolver và repository Spring Session thật nếu filter/repository không được chạy |
| H2 in-memory | Một số SQL cơ bản và transaction | Dialect, collation, locking, index và hành vi của DB production khác H2 |
| Redis/database bằng Testcontainers | Tích hợp repository, serializer, TTL, schema, query và cookie qua filter | Không tự đại diện toàn bộ network, HA, tải production hoặc failure domain |
| Môi trường staging gần production | Deployment, proxy, topology và tải nhiều node | Không thay thế test nhanh, lặp lại và cô lập trong CI |

Redis thật giúp kiểm tra key, serialization, expiration, namespace và lệnh repository. Database cùng họ với production giúp kiểm tra SQL, kiểu dữ liệu, index, transaction và migration. Testcontainers tạo các service này theo vòng đời test, không cần dùng chung một Redis/database phát triển của nhóm.

## 2. Nguyên tắc chọn môi trường test

Môi trường tích hợp nên tương đồng ở những yếu tố có thể làm thay đổi kết quả:

- Cùng hệ quản trị database và major version với production, ví dụ PostgreSQL 16 nếu production dùng PostgreSQL 16.
- Cùng major/minor Redis phù hợp với production, nhất là khi dựa vào lệnh, module hoặc expiration notification cụ thể.
- Cùng phiên bản Spring Boot, Spring Session, Spring Data Redis, JDBC driver và serializer.
- Cùng schema migration, index, constraint, collation và timezone.
- Cùng kiểu transaction manager, isolation level và connection pool ở mức cấu hình liên quan.
- Cùng Redis namespace, cookie serializer và session timeout với cấu hình ứng dụng.
- Dùng cấu hình TLS/ACL ở môi trường kiểm thử riêng khi cần xác minh bảo mật kết nối.

Không cần sao chép mọi thông số production vào mỗi test. Cần tái hiện chính xác những đặc tính có ảnh hưởng đến hành vi đang kiểm tra, đồng thời ghi rõ những khác biệt còn lại.

## 3. Testcontainers tạo service cô lập

Testcontainers khởi chạy container Redis hoặc database khi test bắt đầu và dừng chúng theo vòng đời đã cấu hình. JUnit 5 tích hợp qua `@Testcontainers` và `@Container`.

Ví dụ Maven dependencies (chọn phiên bản Testcontainers tương thích với BOM và JDK của dự án):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Redis có thể được chạy bằng `GenericContainer` nếu dự án không dùng module Redis chuyên biệt:

```java
@Container
static final GenericContainer<?> redis =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
                .withExposedPorts(6379);
```

Trong CI, pin image version cụ thể; với yêu cầu reproducibility cao, pin cả digest. Không dùng tag `latest`, vì image có thể thay đổi mà test không đổi mã nguồn.

### Ví dụ lớp test dùng Redis và PostgreSQL

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
abstract class SessionStoreIntegrationTestBase {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("session_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port", redis::getFirstMappedPort);
    }
}
```

Đây là lớp nền minh họa để cung cấp endpoint động. Trong dự án thật, các test Redis và JDBC thường nên tách thành context/class riêng, mỗi class chọn đúng `spring.session.store-type`. Không bật đồng thời hai repository implementation trong cùng một application context nếu cấu hình auto-configuration không xác định rõ store nào được dùng.

`@DynamicPropertySource` đăng ký giá trị sau khi container đã khởi động. Test không nên hardcode `localhost:6379` hoặc port database vì Testcontainers thường ánh xạ port ngẫu nhiên.

## 4. Tách test Redis và JDBC

Nếu ứng dụng hỗ trợ cả Redis và JDBC, nên có hai nhóm integration test độc lập:

| Nhóm | Store được chọn | Thành phần cần xác minh |
|---|---|---|
| Redis session tests | `spring.session.store-type=redis` | Redis repository, serializer, namespace, TTL và index |
| JDBC session tests | `spring.session.store-type=jdbc` | JDBC repository, schema, SQL, transaction, index và cleanup |

Ví dụ cấu hình riêng cho Redis test:

```properties
spring.session.store-type=redis
spring.session.redis.namespace=integration-test:sessions
spring.session.timeout=30m
```

Và JDBC test:

```properties
spring.session.store-type=jdbc
spring.session.jdbc.initialize-schema=always
spring.session.timeout=30m
```

`initialize-schema=always` có thể phù hợp cho database container mới tạo trong test. Nếu production dùng Flyway hoặc Liquibase, nên có test chạy đúng migration của ứng dụng và thường tắt schema auto-initialization để tránh hai cơ chế cùng quản lý DDL. Tên property có thể khác theo phiên bản Spring Boot/Spring Session; xác minh metadata cấu hình của phiên bản dự án.

Không dựa vào việc classpath có `spring-session-data-redis` hay `spring-session-jdbc` để kết luận store nào đang được dùng. Kiểm tra auto-configuration report hoặc bean repository trong test nếu có nguy cơ chọn nhầm implementation.

## 5. Kiểm thử JDBC bằng schema gần production

JDBC repository cần các bảng session và attribute theo schema của đúng phiên bản Spring Session. Với database production là PostgreSQL, nên chạy test trên PostgreSQL thay vì chỉ H2.

Những khác biệt có thể làm test H2 pass nhưng production fail:

- Kiểu cột và giới hạn độ dài `SESSION_ID`, `PRINCIPAL_NAME` hoặc attribute name.
- Quy tắc so sánh chuỗi/collation và chữ hoa, chữ thường.
- Khóa chính, unique constraint và foreign key.
- Index và execution plan.
- Cách database khóa hàng và xử lý transaction đồng thời.
- SQL dialect, timestamp precision và timezone.
- Isolation level, deadlock và retry behavior.

### Dùng migration thật

Nếu production dùng Flyway, test nên chạy cùng migration scripts:

```properties
spring.flyway.enabled=true
spring.session.jdbc.initialize-schema=never
```

Migration cần tạo đúng bảng và index Spring Session mà ứng dụng mong đợi. Nếu dùng script schema chính thức của Spring Session để khởi tạo test, bảo đảm script khớp dependency version. Không tự chép schema từ phiên bản khác rồi coi đó là test production-like.

### Kiểm tra index và query

Các truy vấn thường cần index trên session ID và expiry; nếu dùng principal lookup, cần index principal tương ứng. Integration test có thể xác minh migration tạo index và chạy query repository trên database thật. Với performance-sensitive path, xem `EXPLAIN`/execution plan bằng database production-like.

Không thêm index vào production schema chỉ để làm test pass. Xác định query thực tế, execution plan và lợi ích/chi phí ghi trước khi thay migration.

## 6. Kiểm thử Redis repository và serializer

Redis integration test nên xác minh:

- Session được lưu với ID và namespace đúng.
- Attribute có thể serialize và deserialize giữa request.
- Thay đổi attribute được lưu theo `SaveMode`/`FlushMode`.
- Session timeout được phản ánh vào TTL theo repository semantics.
- Logout/invalidate làm session không còn được tải.
- Principal index hoạt động nếu ứng dụng dùng chức năng đó.
- Nhiều application context/node có thể đọc cùng session khi cùng cấu hình.
- Dữ liệu cũ và serializer hiện tại tương thích trong giai đoạn rollout nếu yêu cầu.

Không chỉ kiểm tra key có tồn tại bằng một lệnh Redis. Hãy gửi request qua Spring Session filter, sau đó đọc lại session qua repository hoặc request tiếp theo. Điều đó xác minh cả serialization, cookie resolver và lifecycle.

Nếu production dùng Redis ACL, TLS, Sentinel hoặc Cluster, một container Redis standalone chỉ xác minh repository cơ bản. Cần có test bổ sung cho topology và bảo mật kết nối nếu ứng dụng phụ thuộc các đặc tính đó.

## 7. Kiểm thử round-trip qua HTTP cookie

Một test có giá trị cao là tạo session ở request đầu, nhận cookie, rồi gửi cookie đó trong request thứ hai để đọc attribute. Ví dụ controller test-only hoặc endpoint test profile có thể đặt/đọc một attribute.

```java
@RestController
class SessionProbeController {

    @PostMapping("/test/session")
    String write(HttpSession session,
                 @RequestParam String value) {
        session.setAttribute("probe", value);
        return "stored";
    }

    @GetMapping("/test/session")
    String read(HttpSession session) {
        return (String) session.getAttribute("probe");
    }
}
```

Test dùng MockMvc qua Spring Session filter:

```java
MvcResult created = mockMvc.perform(post("/test/session")
        .with(csrf())
        .param("value", "redis-round-trip"))
    .andExpect(status().isOk())
    .andReturn();

Cookie sessionCookie = created.getResponse().getCookie("APPSESSION");
assertThat(sessionCookie).isNotNull();

mockMvc.perform(get("/test/session").cookie(sessionCookie))
    .andExpect(status().isOk())
    .andExpect(content().string("redis-round-trip"));
```

Ví dụ giả định cookie serializer đã đặt tên `APPSESSION`, endpoint chỉ tồn tại trong profile test và Spring Security CSRF được bật. Nếu test không dùng CSRF, điều chỉnh theo cấu hình thật thay vì tắt bảo vệ chỉ để test chạy.

Điểm quan trọng là request thứ hai gửi cookie do response thứ nhất phát hành. Không truyền cùng `MockHttpSession` object trực tiếp nếu mục tiêu là xác minh cookie và repository thật; cách đó có thể bỏ qua đường serialize/lookup mà production sử dụng.

## 8. Kiểm thử TTL và expiration

Session timeout phải được kiểm tra ở cả API lẫn store. Có thể đặt timeout ngắn trong test, tạo session, xác nhận session còn tồn tại, chờ đến khi hết hạn và xác nhận repository không còn trả session hợp lệ.

Ví dụ kiểm thử khái quát:

```java
session.setMaxInactiveInterval(Duration.ofSeconds(2));
repository.save(session);

assertThat(repository.findById(session.getId())).isNotNull();

await().atMost(Duration.ofSeconds(8))
        .untilAsserted(() ->
                assertThat(repository.findById(session.getId())).isNull());
```

Đây là ví dụ dùng Awaitility để polling thay vì `Thread.sleep` cố định. Cần cấu hình repository timeout/TTL phù hợp; `setMaxInactiveInterval` có thể được lưu theo semantics của implementation. Redis key có thể vẫn tồn tại trong thời gian rất ngắn sau TTL do expiration xử lý bất đồng bộ; JDBC row có thể chỉ bị xóa vật lý khi cleanup chạy. Điều cần kiểm tra là repository từ chối session hết hạn theo hợp đồng.

Để kiểm tra Redis TTL, có thể đọc TTL key trong test nếu key layout được coi là chi tiết implementation đã biết. Không viết assertion phụ thuộc tên key nội bộ không ổn định qua version nếu mục tiêu test là hành vi public API.

Với JDBC, kiểm tra cả expiry metadata và cleanup job riêng. Không dùng test timeout vài giây để suy ra chính xác độ trễ production nếu cleanup chạy theo chu kỳ phút.

## 9. Cô lập dữ liệu giữa các test

Container dùng chung cho nhiều test có thể tiết kiệm thời gian, nhưng dữ liệu session phải được cô lập. Nếu test trước tạo session và không xóa, test sau có thể đọc nhầm dữ liệu hoặc fail không ổn định.

Các lựa chọn:

- Dùng Redis namespace riêng cho mỗi test class hoặc suite.
- Dùng database/schema riêng cho mỗi test suite.
- Xóa dữ liệu test trong teardown bằng API repository hoặc SQL cleanup có kiểm soát.
- Tạo principal/session ID ngẫu nhiên riêng cho mỗi test.
- Chạy container mới cho từng test khi isolation quan trọng hơn tốc độ.

Không dùng `FLUSHALL` trên Redis dùng chung với các test khác hoặc môi trường dev. Nếu dùng `FLUSHDB`, chỉ áp dụng cho Redis database/container riêng thuộc test đó.

Với JDBC, cleanup phải xóa bảng attributes trước bảng session nếu không có cascade. Ví dụ SQL dưới đây chỉ minh họa cấu trúc; điều chỉnh tên bảng/cột theo schema thật:

```sql
DELETE FROM SPRING_SESSION_ATTRIBUTES;
DELETE FROM SPRING_SESSION;
```

Nếu test chạy song song, cleanup toàn bảng có thể xóa session của test khác. Dùng schema/database riêng, namespace hoặc session IDs đã biết; tránh global cleanup khi nhiều test cùng chia sẻ store.

## 10. Transaction test và dữ liệu commit

Một số test Spring dùng `@Transactional` và rollback sau mỗi test. Cần cẩn thận: transaction rollback của test có thể không bao phủ thao tác repository session nếu Spring Session dùng transaction boundary/connection khác, hoặc test đang kiểm tra hành vi commit qua request thực.

Đối với test repository JDBC, xác định transaction manager và propagation thực tế. Đối với HTTP integration test, request có thể chạy trên thread/transaction khác với thread test. Không giả định `@Transactional` trên method test sẽ rollback mọi thay đổi session do request tạo.

Nên:

- Dùng database/container riêng cho test suite.
- Dọn dữ liệu bằng repository hoặc SQL trong teardown có kiểm soát.
- Có test xác nhận dữ liệu thực sự commit và đọc được từ connection/request tiếp theo.
- Không bọc test HTTP bằng transaction rollback rồi kết luận repository commit behavior đã được kiểm tra.

## 11. Kiểm thử nhiều node cùng dùng một store

Để xác minh Spring Session hỗ trợ nhiều instance, có thể chạy hai application context hoặc hai server instance cùng trỏ đến một Redis/JDBC container.

Kịch bản:

1. Gửi request login hoặc tạo session đến node A.
2. Lấy cookie session từ response A.
3. Gửi request có cùng cookie đến node B.
4. Xác nhận B đọc được attribute và SecurityContext cần thiết.
5. Cập nhật attribute tại B.
6. Gửi request tiếp theo đến A và xác nhận dữ liệu theo semantics repository.
7. Logout hoặc xóa session tại A.
8. Gửi lại cookie cũ đến B và xác nhận session không còn hợp lệ.

Hai context phải dùng cùng cookie serializer, namespace/schema, serializer và store. Không dùng sticky session như điều kiện để test pass; mục tiêu là chứng minh node bất kỳ có thể đọc dữ liệu đã lưu trong repository chung.

Test hai context trong cùng JVM chưa mô phỏng đầy đủ network/process isolation, nhưng có thể phát hiện nhiều lỗi cấu hình. Với rủi ro deployment cao, chạy hai process/container ứng dụng riêng trong test environment.

## 12. Kiểm thử schema và migration

JDBC test nên bắt đầu từ database trống và chạy toàn bộ migration như production. Điều này phát hiện migration thiếu bảng, sai kiểu dữ liệu, thiếu index hoặc phụ thuộc vào trạng thái database đã có từ trước.

Các kịch bản cần có:

- Tạo schema từ đầu trên database container.
- Nâng cấp từ schema phiên bản trước lên schema mới.
- Xác nhận bảng session và attributes tương thích với repository dependency.
- Kiểm tra index principal/expiry/session ID nếu được yêu cầu.
- Kiểm tra migration có thể chạy lặp theo công cụ migration.
- Kiểm tra ứng dụng không cố tự chạy DDL đồng thời trên mọi node production.

Nếu Spring Session cung cấp schema script theo dialect, dùng script đúng dialect và phiên bản. Nếu schema được quản lý bằng migration riêng, đưa script đó vào test. Không chỉ dựa vào H2 vì nó có thể chấp nhận SQL hoặc kiểu dữ liệu mà database production không chấp nhận.

## 13. Kiểm thử lỗi kết nối và khôi phục

Testcontainers cho phép dừng/restart container hoặc ngắt kết nối trong một số kịch bản. Có thể kiểm tra:

- Redis/database không khả dụng khi request tải session.
- Store mất kết nối khi save ở cuối request.
- Connection pool timeout hoặc database restart.
- Retry có giới hạn và không tạo session trùng.
- Request sau khi store phục hồi có thể tải session còn hợp lệ.
- Lỗi store không bị nuốt rồi trả response thành công giả.

Không nên biến mọi lỗi store thành anonymous session mà không có policy rõ ràng. Với ứng dụng bảo mật, nếu không thể xác minh session, thường phải fail closed hoặc trả lỗi dịch vụ phù hợp thay vì cấp quyền như đã xác thực.

Một test dừng container có thể không mô phỏng chính xác failover Sentinel/Cluster hoặc network partition. Ghi rõ giới hạn và bổ sung test chuyên biệt nếu production phụ thuộc topology đó.

## 14. Test profile và cấu hình không rò rỉ sang production

Thông tin test nên được đặt trong `src/test/resources` hoặc cấu hình Testcontainers. Không commit password thật hoặc endpoint production. Test profile không được tự động bật trong production artifact.

Một số nguyên tắc:

- Không dùng Redis/database dev chung cho CI test.
- Không để test tự xóa dữ liệu ngoài container của nó.
- Không để `initialize-schema=always` ghi DDL vào database production.
- Dùng credential test ngẫu nhiên hoặc chỉ tồn tại trong container.
- Dùng image pin version và có thể tải từ registry nội bộ đã được kiểm soát.
- Giới hạn log SQL/Redis nếu log có thể chứa session ID hoặc serialized data.
- Dọn container sau test và không để process phụ tồn tại sau CI job.

## 15. Chọn mức độ kiểm thử phù hợp

Không cần khởi động cả Redis và PostgreSQL cho mọi test. Tách test theo mục tiêu:

| Mục tiêu | Test phù hợp |
|---|---|
| Logic controller không phụ thuộc store | Unit test hoặc MockMvc với mock |
| Security filter và cookie flow | MockMvc qua filter chain, có Spring Session repository |
| Redis serializer/TTL/namespace | Testcontainers Redis |
| JDBC schema/query/transaction | Testcontainers database production-like |
| Chia sẻ session giữa node | Hai context/process cùng store |
| Failover, latency và pool exhaustion | Integration/performance test chuyên biệt |

Test nhanh vẫn có giá trị, nhưng không thay thế test repository thật. Ngược lại, một bộ Testcontainers lớn không cần chạy cho mọi unit test vì sẽ làm feedback chậm và tăng chi phí CI.

## 16. Ví dụ cấu trúc test suite

Một cấu trúc dễ bảo trì có thể như sau:

```text
src/test/java/
  .../session/
    SessionMvcTest.java
    RedisSessionIntegrationTest.java
    JdbcSessionIntegrationTest.java
    SessionExpirationIntegrationTest.java
    MultiNodeSessionIntegrationTest.java
    SessionStoreFailureIntegrationTest.java
src/test/resources/
  application-redis-test.properties
  application-jdbc-test.properties
  db/migration/
```

Tên file chỉ là gợi ý. Quan trọng là test phân biệt rõ mục tiêu, store và mức độ tích hợp. Các test có thể dùng chung abstract Testcontainers fixture nếu điều đó không làm Spring context cache hoặc dữ liệu test bị trộn lẫn.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test pass với H2 nhưng fail ở production DB | Dialect, collation, type hoặc locking khác nhau | Dùng Testcontainers cùng họ/version DB |
| Test không tìm thấy session sau request đầu | Không đi qua SessionRepositoryFilter hoặc không gửi cookie | Kiểm tra filter registration và `Set-Cookie` |
| Test phụ thuộc port cố định | Container port được ánh xạ động | Dùng `getMappedPort` qua `@DynamicPropertySource` |
| Test Redis đọc dữ liệu cũ | Namespace/database dùng chung và cleanup thiếu | Dùng namespace riêng hoặc container riêng |
| Test JDBC lỗi duplicate key ngẫu nhiên | Dữ liệu test dùng chung hoặc cleanup race | Cô lập schema/ID và tránh cleanup toàn bảng song song |
| TTL test chập chờn | Dùng sleep cố định và giả định thời điểm xóa vật lý | Polling có timeout; kiểm tra repository semantics |
| Migration test pass nhưng production lỗi | Test dùng schema auto-init khác migration thật | Chạy chính migration production trên container |
| Test transaction rollback nhưng session vẫn tồn tại | Request/repository dùng transaction khác | Dọn store rõ ràng và test commit qua request kế tiếp |
| Test nhiều node pass nhờ sticky session | Client luôn quay lại cùng instance | Cố định request A/B luân phiên và dùng store chung |
| CI không khởi chạy container | Docker runtime hoặc quyền truy cập Docker chưa sẵn sàng | Kiểm tra môi trường runner và Testcontainers logs |

## 18. Checklist trước khi merge

- Pin phiên bản Redis và database image gần production.
- Dùng Testcontainers thay cho service dev dùng chung.
- Chọn đúng `spring.session.store-type` trong từng test context.
- Chạy schema migration production trên database container.
- Kiểm thử Redis serializer, namespace và TTL.
- Kiểm thử JDBC SQL, index, transaction và cleanup.
- Gửi lại cookie session thật giữa các request để xác minh round-trip.
- Xác nhận request đi qua `SessionRepositoryFilter`.
- Kiểm thử invalidate/logout và session hết hạn.
- Kiểm thử hai node/context cùng dùng store chung nếu ứng dụng chạy nhiều instance.
- Cô lập dữ liệu test và tránh `FLUSHALL`/cleanup toàn bảng trên store dùng chung.
- Có test lỗi kết nối và khôi phục nếu yêu cầu vận hành cần.
- Không để credential hoặc endpoint production trong test config.
- Ghi rõ những khác biệt giữa container test và production topology.

Redis và database thử nghiệm gần với môi trường triển khai giúp kiểm tra các phần mà mock không thể chứng minh: serializer, TTL, cookie, SQL dialect, schema, index, transaction và chia sẻ session giữa node. Testcontainers cung cấp service cô lập, còn cấu hình và migration cần bám theo phiên bản production. Kết hợp test round-trip qua cookie, test store-specific, test nhiều node và kiểm thử lỗi kết nối sẽ tạo bằng chứng đáng tin cậy hơn cho Spring Session trước khi triển khai.
