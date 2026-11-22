# Kiểm chứng tương thích bằng cùng loại hạ tầng với môi trường chạy

Một ứng dụng Spring có thể hoạt động đúng với mock hoặc dịch vụ nhúng trong test nhưng vẫn lỗi khi chạy ở môi trường thật. Nguyên nhân thường nằm ở khác biệt giữa hạ tầng test và hạ tầng production: H2 thay cho PostgreSQL, một broker giả thay cho Kafka, cache in-memory thay cho Redis, hoặc filesystem local thay cho object storage. Các hệ thống này có thể cung cấp API tương tự nhưng khác về SQL dialect, transaction isolation, serialization, retry, expiry, locking, collation, protocol và cách xử lý lỗi.

Muốn kiểm chứng khả năng tương thích, hãy chạy integration test với cùng loại dịch vụ mà ứng dụng sử dụng khi triển khai. Có thể dùng Testcontainers để khởi động database, message broker, cache hoặc dịch vụ phụ trợ trong container dùng riêng cho test. Mục tiêu là tái tạo những đặc tính hạ tầng có ảnh hưởng đến hành vi ứng dụng, đồng thời giữ dữ liệu, tài khoản và vòng đời tài nguyên được cô lập.

## “Cùng loại hạ tầng” nghĩa là gì?

Không nhất thiết phải dựng một bản sao production hoàn chỉnh. Cần dùng đúng loại công nghệ và những đặc tính có thể làm thay đổi hành vi mà test muốn xác nhận.

Ví dụ, nếu production dùng PostgreSQL thì test tương thích SQL nên chạy trên PostgreSQL, thay vì chỉ dựa vào H2 ở chế độ tương thích. Nếu production dùng Kafka thì test luồng publish/consume quan trọng nên dùng Kafka thật hoặc một môi trường Kafka tương thích, thay vì chỉ mock `KafkaTemplate`. Nếu production lưu file trên S3, test cần xác nhận giao thức và hành vi storage với dịch vụ S3 hoặc implementation tương thích.

| Hạ tầng production | Hạ tầng test đại diện | Những khác biệt cần quan tâm |
|---|---|---|
| PostgreSQL | PostgreSQL container cùng major/minor version phù hợp | SQL dialect, JSONB, sequence, constraint, collation, isolation, extension |
| MySQL | MySQL container cùng version và cấu hình liên quan | SQL mode, collation, timezone, index, transaction engine |
| Kafka | Kafka container hoặc broker test tương thích | Partition, offset, consumer group, ordering, acknowledgement, retry |
| RabbitMQ | RabbitMQ container | Exchange, routing key, queue durability, acknowledgement, dead-letter |
| Redis | Redis container | TTL, eviction, serialization, atomic operation, Lua script |
| Elasticsearch/OpenSearch | Engine cùng họ và version tương thích | Mapping, analyzer, query DSL, index lifecycle, refresh behavior |
| S3-compatible storage | S3 hoặc dịch vụ tương thích như MinIO | Bucket policy, metadata, multipart upload, path-style/virtual-host addressing |
| Filesystem | Filesystem của hệ điều hành/container tương ứng | Case sensitivity, permission, atomic rename, path separator |

“Cùng loại” nên được hiểu theo rủi ro tương thích. Một test chỉ kiểm tra service gọi repository có thể dùng mock. Nhưng test xác nhận query native, migration, locking hoặc transaction cần database engine thật. Tương tự, test xác nhận logic mapping event có thể dùng unit test, còn test xác nhận consumer group, acknowledgement và retry cần broker thật.

## Chọn mức tương đồng cần thiết

Không phải mọi test đều cần tái tạo mọi chi tiết production. Hãy xác định đặc tính hạ tầng có ảnh hưởng đến kết quả:

1. **Loại dịch vụ:** database, broker, cache, search engine, object storage hoặc filesystem.
2. **Engine và version:** dùng cùng engine và version tương thích với môi trường chạy; tránh dùng tag `latest` vì test có thể đổi hành vi ngoài ý muốn.
3. **Cấu hình quan trọng:** encoding, collation, timezone, SQL mode, extensions, transaction isolation, retention, TTL, partition hoặc policy.
4. **Driver và protocol:** dùng driver/client cùng loại và cấu hình gần với ứng dụng production.
5. **Security:** nếu production phụ thuộc TLS, authentication, authorization hoặc credential rotation, cần có test kiểm tra những phần đó ở một tầng phù hợp.
6. **Lifecycle và failure mode:** xác nhận ứng dụng xử lý được timeout, unavailable service, retry, reconnect và shutdown theo yêu cầu.

Một container có cùng engine nhưng cấu hình khác production vẫn có thể bỏ sót lỗi. Ví dụ PostgreSQL test không bật extension mà production sử dụng sẽ không chứng minh migration hoặc query phụ thuộc extension hoạt động. Ngược lại, không cần sao chép dung lượng dữ liệu production nếu mục tiêu chỉ là xác nhận cú pháp query và ràng buộc schema.

## Vì sao H2 hoặc mock có thể không đủ?

H2 rất hữu ích cho test nhanh và một số repository test đơn giản. Tuy nhiên, H2 không phải PostgreSQL hoặc MySQL. Dù H2 có compatibility mode, nó không thể bảo đảm mọi khác biệt về parser, kiểu dữ liệu, hàm SQL, constraint, index, locking và transaction semantics đều được mô phỏng chính xác.

Ví dụ, query sau dùng cú pháp đặc thù PostgreSQL:

```sql
select payload ->> 'customerId'
from event_log
where payload @> '{"status":"READY"}'::jsonb
```

Query này dùng toán tử JSONB và cast của PostgreSQL. Test chỉ chạy trên H2 có thể không thực thi được query hoặc phải thay query bằng một implementation khác, khiến test không còn kiểm tra SQL production đang dùng.

Mock repository còn có giới hạn lớn hơn: mock chỉ trả về kết quả được lập trình sẵn. Nó không kiểm tra SQL, constraint, transaction, isolation, migration, index hay mapping thật. Mock phù hợp với unit test service, nơi mục tiêu là kiểm tra quy tắc nghiệp vụ và cách phối hợp dependency. Nó không thay thế integration test cần xác nhận khả năng tương thích với database.

Một chiến lược thực tế có thể dùng cả ba mức:

| Loại test | Hạ tầng | Điều được xác nhận |
|---|---|---|
| Unit test | Mock dependency | Logic nghiệp vụ và nhánh xử lý |
| Integration test nhanh | Embedded hoặc dịch vụ nhẹ | Mapping/cấu hình cơ bản, nếu semantics tương thích đủ cho mục tiêu |
| Compatibility integration test | Cùng engine/protocol với production | SQL, transaction, migration, serialization và hành vi dịch vụ thật |

Không cần loại bỏ H2 khỏi mọi test. Chỉ cần không dùng kết quả từ H2 để kết luận rằng ứng dụng đã tương thích với PostgreSQL nếu production thực sự chạy PostgreSQL.

## Dùng Testcontainers để khởi động hạ tầng thật

Testcontainers cung cấp API Java để chạy container phục vụ test và tự quản lý vòng đời container. Test có thể khởi động database hoặc broker khi bắt đầu, lấy endpoint động, chạy ứng dụng với endpoint đó rồi dừng container khi test hoàn tất.

Với Maven, ví dụ dependency PostgreSQL:

```xml
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
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

Hãy dùng BOM hoặc dependency management của dự án để quản lý version Testcontainers và driver. Ví dụ này giả định ứng dụng đã có Spring Boot Test và Spring Data/JDBC/JPA dependency tương ứng.

### PostgreSQL cùng loại với production

Ví dụ sau chạy PostgreSQL container, rồi đưa URL, username và password động vào Spring context bằng `@DynamicPropertySource`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class OrderRepositoryCompatibilityTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4-alpine")
                    .withDatabaseName("store_test")
                    .withUsername("test_user")
                    .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void persistsAndReadsOrderUsingPostgres() {
        Order saved = orderRepository.save(new Order("PO-349"));

        Order loaded = orderRepository.findById(saved.getId()).orElseThrow();

        assertThat(loaded.getReference()).isEqualTo("PO-349");
    }
}
```

`@Testcontainers` tích hợp Testcontainers với JUnit Jupiter. `@Container` trên field `static` tạo container dùng chung trong phạm vi test class; container được khởi động trước các test của class và dừng sau class. `@DynamicPropertySource` đăng ký các giá trị chỉ có sau khi container khởi động. Spring đọc các supplier này khi tạo context.

Tag image nên được pin theo version mà production dùng hoặc version được quy định trong ma trận tương thích. Nếu production đang dùng PostgreSQL 16.x, không nên để test tự đổi sang major version khác chỉ vì `latest` được cập nhật.

### Không để Spring Boot thay database test bằng embedded database

Với `@DataJpaTest`, Spring Boot có thể tự thay datasource bằng embedded database nếu tìm thấy dependency phù hợp. Khi mục tiêu là kiểm tra PostgreSQL container, hãy ngăn hành vi thay thế đó:

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class OrderRepositorySliceTest {
    // PostgreSQLContainer và DynamicPropertySource như ví dụ trên.
}
```

`replace = NONE` giữ datasource được cấu hình từ container. Nếu test vô tình chạy với H2, test có thể pass nhưng không còn chứng minh SQL đang chạy trên engine production.

## Dùng @ServiceConnection trong Spring Boot

Với Spring Boot 3.1 trở lên, `@ServiceConnection` có thể tự tạo connection details cho một số loại Testcontainers được Boot hỗ trợ. Cách này giảm việc đăng ký thủ công các datasource properties:

```java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderDatabaseTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16.4-alpine");
}
```

Để dùng annotation này, dự án cần module Spring Boot Testcontainers phù hợp (`spring-boot-testcontainers`) cùng module Testcontainers PostgreSQL. `@ServiceConnection` chỉ tự động cấu hình các loại service mà Spring Boot có connection details factory tương ứng; với dịch vụ hoặc cấu hình riêng, `@DynamicPropertySource` vẫn là lựa chọn linh hoạt.

Không trộn nhiều cách cấu hình cho cùng một endpoint nếu không cần thiết. Hãy xác định rõ nguồn properties cuối cùng để tránh URL từ container bị ghi đè bởi `application-test.yml` hoặc biến môi trường.

## Chạy migration thật trên database test

Compatibility test nên tạo schema bằng cùng migration mà ứng dụng sử dụng khi triển khai. Nếu production dùng Flyway hoặc Liquibase, để test context chạy migration trên database container:

```properties
spring.flyway.enabled=true
spring.jpa.hibernate.ddl-auto=validate
```

Với cách này, Flyway tạo schema từ migration scripts, còn Hibernate kiểm tra mapping entity có tương thích với schema đã tạo hay không. Trong môi trường test, tránh để Hibernate tự tạo schema thay cho migration nếu mục tiêu là xác nhận migration production hoạt động.

Một test có thể xác nhận dữ liệu được lưu sau khi migration chạy:

```java
@Test
void migrationCreatesExpectedColumnAndConstraint() {
    Integer count = jdbcTemplate.queryForObject(
            "select count(*) from information_schema.columns " +
            "where table_name = 'orders' and column_name = 'reference'",
            Integer.class);

    assertThat(count).isEqualTo(1);
}
```

Query metadata có thể khác nhau giữa engine; ví dụ trên phù hợp PostgreSQL với schema/search path tương ứng. Hãy viết assertion theo catalog của database production, đặc biệt khi kiểm tra index, constraint, extension hoặc migration history.

Migration test nên bắt đầu từ database rỗng hoặc schema được tạo mới, để xác nhận toàn bộ chuỗi migration chạy theo đúng thứ tự. Một database đã có schema từ lần chạy trước có thể che khuất migration thiếu hoặc migration không idempotent.

## Kiểm chứng broker và message semantics

Mock `KafkaTemplate` có thể xác nhận service gọi `send()` với topic và payload mong muốn, nhưng không kiểm tra broker nhận message, serializer hoạt động, partition được chọn, consumer group commit offset hoặc retry. Khi các hành vi đó quan trọng, chạy broker cùng loại trong integration test.

Một bài test broker nên kiểm tra theo luồng:

1. Khởi động broker và tạo topic/queue cần thiết.
2. Cấu hình Spring producer/consumer dùng endpoint container.
3. Gửi message bằng producer thật.
4. Chờ consumer xử lý bằng một tín hiệu có timeout, chẳng hạn latch hoặc trạng thái được ghi vào database.
5. Xác nhận payload, header, key, routing hoặc side effect đã xảy ra.
6. Dọn topic/queue hoặc dùng topic/consumer group riêng cho test.

Không dùng `Thread.sleep()` để đoán lúc consumer đã nhận message. Dùng Awaitility, `CountDownLatch`, `CompletableFuture` hoặc polling có timeout theo điều kiện thực tế. Test broker nên có timeout hữu hạn và log thông tin topic, partition, offset hoặc correlation ID khi thất bại.

Đối với Kafka, các đặc tính quan trọng có thể gồm partition count, key-based ordering, consumer group, offset commit, acknowledgement, retry và dead-letter topic. Đối với RabbitMQ, hãy kiểm tra exchange, binding, routing key, durable queue, acknowledgement, redelivery và dead-letter exchange. Mock có thể kiểm tra mapping message; broker thật kiểm tra semantics của hệ thống messaging.

## Kiểm chứng cache, search và object storage

Cache in-memory như `ConcurrentHashMap` không tự động tương đương Redis. Nó có thể khác về TTL, eviction, serialization, atomic operations, distributed lock và hành vi khi node khởi động lại. Nếu ứng dụng dùng Redis, test tương thích nên chạy Redis container cho các tính năng phụ thuộc vào những semantics đó.

Search engine cũng có sự khác biệt giữa implementation. Nếu ứng dụng production dùng Elasticsearch hoặc OpenSearch, cần kiểm tra engine/version, mapping, analyzer, query DSL, refresh và bulk operation. Một mock HTTP server có thể kiểm tra request JSON gửi đi, nhưng không chứng minh engine hiểu mapping hoặc query đó như production.

Với object storage, dùng S3 hoặc dịch vụ tương thích có thể chạy trong container/test environment. Kiểm tra upload/download, metadata, content type, multipart upload, bucket policy, path-style addressing và xử lý object không tồn tại. Một fake lưu byte array trong bộ nhớ chỉ phù hợp để kiểm tra logic gọi interface storage.

| Tính năng | Unit test bằng mock | Compatibility test với hạ tầng cùng loại |
|---|---|---|
| Redis cache key | Xác nhận service tạo key đúng | Xác nhận serialization, TTL và atomic operation |
| Kafka event | Xác nhận producer gọi đúng topic/key | Xác nhận broker nhận, partition và consumer xử lý |
| Search query | Xác nhận request/query object được tạo | Xác nhận mapping/analyzer/query chạy trên engine |
| S3 upload | Xác nhận service gọi storage port | Xác nhận endpoint nhận object, metadata và policy |

Không cần chạy tất cả các test này cho mọi thay đổi. Tập trung vào những adapter và hành vi có nguy cơ lệch giữa môi trường phát triển và production.

## Cấu hình môi trường test một cách rõ ràng

Test nên dùng profile riêng, nhưng profile không nên thay đổi loại hạ tầng mà test đang muốn xác minh. Ví dụ `application-test.yml` có thể chứa logging, timeout và feature flags phù hợp với test, trong khi datasource URL được cung cấp từ Testcontainers:

```yaml
spring:
  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
  datasource:
    hikari:
      maximum-pool-size: 4
      connection-timeout: 5000
```

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderInfrastructureTest {
}
```

Đặt URL, user và password động từ container; không commit credentials production vào test resources. Nếu production bắt buộc TLS hoặc authentication, hãy có test cấu hình riêng để xác nhận client có thể kết nối đúng với các cơ chế đó. Một container không bật TLS không thể chứng minh cấu hình TLS production hoạt động.

Khi test cần xác nhận cấu hình pool hoặc connection lifecycle, hãy giữ connection pool thật của ứng dụng (ví dụ HikariCP) và thay endpoint bằng container. Không thay toàn bộ datasource bằng mock vì như vậy sẽ bỏ qua pool, driver, connection validation và transaction manager.

## Đồng bộ version và cấu hình với production

Nên lưu version hạ tầng test ở một nơi có thể xem xét và nâng cấp có chủ đích:

```properties
# test-infrastructure.properties
test.postgres.image=postgres:16.4-alpine
```

Có thể dùng property này để cấu hình container hoặc đặt trực tiếp tag đã pin trong test source. Điều quan trọng là không để CI tự lấy image mới nhất mà không có thay đổi được review.

Ma trận tương thích có thể ghi rõ:

| Thành phần | Production | Test | Mức tương đồng cần giữ |
|---|---|---|---|
| PostgreSQL | 16.x | 16.4 | Cùng major; pin patch version trong CI |
| JDBC driver | PostgreSQL JDBC 42.x | Cùng dòng driver | Cùng driver và cấu hình pool |
| Kafka | 3.x | Cùng broker version hoặc version được chứng nhận | Protocol và semantics consumer/producer |
| Redis | 7.x | 7.x | Cùng version, persistence/eviction nếu có liên quan |
| S3 | Managed S3 | S3 test service | API và các tính năng được ứng dụng sử dụng |

Nếu production có managed service với extension hoặc policy riêng, container cơ bản chỉ xác nhận được engine/API nền. Cần bổ sung contract test hoặc staging test để xác nhận tính năng đặc thù của nhà cung cấp.

## Data isolation và cleanup

Dùng cùng loại hạ tầng không có nghĩa dùng chung dữ liệu production. Mỗi test cần dữ liệu xác định và không ảnh hưởng test khác.

Các chiến lược thường dùng:

- Một container riêng cho test class hoặc test suite.
- Một database/schema riêng cho mỗi test class hoặc mỗi worker chạy song song.
- Tên topic, queue, bucket hoặc key có namespace riêng theo test.
- Dữ liệu seed bằng fixture rõ ràng và dọn sau test.
- Dùng transaction rollback khi toàn bộ thao tác nằm trong cùng transaction/thread; không giả định rollback bao phủ HTTP server thread, async executor hoặc message consumer.

Với database, có thể dùng `@Transactional` để rollback test-managed transaction trong các test repository chạy trực tiếp. Tuy nhiên, nếu request được gửi qua `RANDOM_PORT`, server xử lý trên thread khác và có transaction riêng. Dữ liệu đã commit từ server không tự động rollback cùng transaction của test. Hãy xóa dữ liệu bằng cleanup transaction, tạo schema/database riêng hoặc reset container.

Với broker, dùng topic hoặc queue riêng theo test để message cũ không làm test sau pass giả. Với Redis, thêm prefix cho key và đặt TTL phù hợp. Với object storage, dùng bucket/prefix riêng và xóa object sau test. Khi chạy song song, namespace nên chứa ID test hoặc worker để tránh collision.

Không dùng dữ liệu production trực tiếp. Nếu cần dữ liệu có hình dạng thực tế, tạo fixture tổng hợp hoặc dùng dữ liệu đã được khử nhận dạng và phê duyệt theo quy trình của tổ chức.

## Vòng đời container và Spring context cache

`@Container` static với JUnit Jupiter thường sống trong phạm vi một test class. Spring TestContext lại có thể cache `ApplicationContext` và tái sử dụng giữa nhiều class. Nếu context đã cache vẫn giữ `DataSource` trỏ đến container vừa bị dừng sau class trước, test class tiếp theo có thể gặp connection refused dù cấu hình của nó giống hệt.

Có một số cách tổ chức:

1. Dùng container theo class và cấu hình context để mỗi lifecycle phù hợp với container; tránh để context cache sống lâu hơn tài nguyên mà nó phụ thuộc.
2. Dùng một container singleton cấp suite, khởi động một lần và giữ sống trong toàn bộ thời gian các context sử dụng nó. Khi dùng cách này, không gắn `@Container` để JUnit tự dừng sau từng class; cần quản lý startup/shutdown rõ ràng.
3. Dùng `@DirtiesContext` khi test thực sự cần đóng context trước khi container dừng, nhưng không lạm dụng vì làm tăng thời gian suite.

Nếu chia sẻ container cấp suite, vẫn phải cô lập database/schema, topic, queue và key giữa test. Chia sẻ tiến trình dịch vụ không có nghĩa chia sẻ state nghiệp vụ.

## Kiểm tra readiness thay vì chờ cố định

Container đã chạy không đồng nghĩa dịch vụ bên trong đã sẵn sàng nhận request. Testcontainers có wait strategy cho port, log message, HTTP response hoặc health check. Chọn điều kiện readiness phù hợp với dịch vụ và phiên bản image.

```java
GenericContainer<?> service = new GenericContainer<>(
        DockerImageName.parse("example/service:1.2.3"))
        .withExposedPorts(8080)
        .waitingFor(Wait.forHttp("/health")
                .forStatusCode(200)
                .withStartupTimeout(Duration.ofMinutes(2)));
```

Ví dụ này minh họa HTTP wait strategy cho một service có endpoint health. Với database hoặc broker, ưu tiên wait strategy tương ứng hoặc health check của image. Tránh `Thread.sleep(5000)` sau khi start container: máy nhanh có thể lãng phí thời gian, máy chậm vẫn có thể chưa sẵn sàng.

Nếu ứng dụng có startup logic cần retry khi dependency chưa sẵn sàng, test nên xác nhận hành vi đó bằng điều kiện quan sát được và timeout hữu hạn. Readiness của container và retry policy của ứng dụng là hai hành vi khác nhau.

## Chạy cùng chiến lược trên máy phát triển và CI

Test tương thích chỉ hữu ích khi có thể chạy lặp lại. Máy phát triển và CI nên dùng cùng image version, cùng migration, cùng cấu hình quan trọng và cùng cách lấy endpoint. CI cần runtime container như Docker hoặc một môi trường Testcontainers được cấu hình tương thích.

Một pipeline thường thực hiện:

1. Chuẩn bị Docker/container runtime.
2. Chạy test suite; Testcontainers khởi động các dịch vụ cần thiết.
3. Đợi readiness, tạo schema/topic/bucket và nạp fixture.
4. Chạy integration test và thu thập log khi thất bại.
5. Dừng container và dọn tài nguyên test.

Khi CI không cho phép Docker-in-Docker hoặc không hỗ trợ Testcontainers, có thể dùng service container do CI cung cấp hoặc môi trường ephemeral riêng. Hãy giữ cùng engine/version và cấu hình liên quan; chỉ đổi cách cung cấp endpoint, không âm thầm đổi sang database hoặc broker khác.

## Những trường hợp cần thêm test trên môi trường gần production

Container cùng loại giúp kiểm tra phần lớn hành vi engine và protocol, nhưng vẫn có những khác biệt không thể tái tạo đầy đủ:

- Managed database có extension, parameter group, proxy hoặc failover riêng.
- Kafka/RabbitMQ cluster nhiều node với replication, partition rebalance hoặc quorum behavior.
- IAM, KMS, secret manager, certificate rotation và network policy của cloud.
- Load balancer, reverse proxy, DNS, TLS termination và network latency.
- Storage policy, lifecycle rule, versioning và quota của nhà cung cấp.

Với các rủi ro này, dùng compatibility integration test trong container để kiểm tra phần nền tảng, sau đó bổ sung một số contract/staging test trên môi trường gần production. Không cần biến mọi unit test thành test staging; chỉ đưa các phụ thuộc đặc thù nhà cung cấp vào đúng tầng xác minh.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test pass trên H2 nhưng lỗi trên PostgreSQL | SQL dialect hoặc semantics khác nhau | Chạy test query/migration trên PostgreSQL cùng loại production |
| Spring vẫn kết nối H2 | Boot thay datasource hoặc property container bị ghi đè | Dùng `replace = NONE` với slice phù hợp và kiểm tra datasource URL thực tế |
| Container chạy nhưng connection thất bại | Dịch vụ chưa readiness hoặc port mapping sai | Dùng wait strategy và lấy endpoint qua API Testcontainers |
| Test class sau gặp connection refused | Spring context cache tham chiếu container đã dừng | Điều chỉnh lifecycle container/context hoặc dùng container cấp suite |
| Message test nhận event cũ | Topic/queue dùng chung và không được reset | Namespace hoặc tạo topic/queue riêng cho test |
| Cache test phụ thuộc thứ tự | Key dùng chung hoặc TTL chưa hết | Dùng prefix riêng, dọn key và kiểm tra TTL rõ ràng |
| Test chậm hoặc không ổn định trên CI | Dùng `sleep`, readiness không rõ hoặc image không pin version | Wait strategy có timeout, pin image và thu thập log |
| Transaction test không rollback dữ liệu từ HTTP request | Request chạy trên server thread và transaction riêng | Cleanup dữ liệu hoặc cô lập schema/database |
| Container tương thích API nhưng thiếu tính năng production | Managed service có extension/policy riêng | Bổ sung test trên môi trường staging/contract test phù hợp |

## Ma trận chọn hạ tầng cho từng mục tiêu

| Mục tiêu kiểm thử | Hạ tầng nên dùng | Vì sao |
|---|---|---|
| Logic service và nhánh nghiệp vụ | Mock repository/client | Tập trung vào quyết định của service |
| Query native, migration, locking | Cùng database engine với production | Xác nhận SQL và transaction semantics thực tế |
| Serialization và consumer behavior | Cùng broker hoặc broker tương thích | Xác nhận protocol, routing, acknowledgement và retry |
| TTL, atomic operation, distributed lock | Cùng cache engine | Xác nhận semantics mà cache in-memory không mô phỏng đủ |
| Search mapping/analyzer | Cùng search engine/version | Xác nhận query và index behavior |
| Upload/download object | S3 hoặc implementation tương thích | Xác nhận API, metadata, multipart và policy |
| IAM, failover, managed extension | Staging hoặc môi trường gần production | Những đặc tính này không có đầy đủ trong container cơ bản |

Kiểm chứng tương thích bằng cùng loại hạ tầng giúp phát hiện lỗi do khác biệt engine, version, protocol và cấu hình trước khi triển khai. Hãy dùng mock cho logic đơn vị, container cho integration test cần dịch vụ thật, và staging test cho đặc tính chỉ tồn tại ở môi trường managed. Khi version, cấu hình, readiness, dữ liệu và lifecycle được kiểm soát, kết quả test sẽ phản ánh đáng tin cậy hơn cách ứng dụng hoạt động khi chạy thực tế.
