# Kiểm thử tích hợp kho dữ liệu và dịch vụ thật bằng Testcontainers khi phù hợp

Trong module **SPRING_CLOUD_SERVICE_BROKER**, broker phải phối hợp nhiều thành phần: HTTP API theo Open Service Broker API (OSB API), database lưu service instance và binding, queue/worker cho operation bất đồng bộ, secret store và provider adapter gọi dịch vụ hạ tầng. Unit test có thể xác minh logic của từng lớp, nhưng không đủ để phát hiện sai khác giữa database thật và database giả lập, lỗi migration, constraint không đúng, transaction race hoặc cách service thực sự khởi động.

**Testcontainers** cho phép test tự khởi động các dependency thật trong container, sử dụng chúng trong lúc chạy test và dọn dẹp sau đó. Ví dụ, broker có thể chạy integration test với PostgreSQL thật thay vì H2, kiểm thử RabbitMQ bằng broker container, hoặc khởi động Redis để xác minh cache/locking. Điều này giúp kiểm tra behavior gần môi trường triển khai hơn mà không phải cài thủ công từng dịch vụ trên máy developer.

Không phải dependency nào cũng nên chạy trong container ở mọi test. Với API cloud bên ngoài, provider có thể tính phí, cần credential hoặc tạo tài nguyên lâu dài; trong trường hợp đó, một HTTP stub có kiểm soát hoặc sandbox integration test riêng có thể phù hợp hơn. Mục tiêu là chọn đúng ranh giới cần kiểm chứng: dùng container cho dịch vụ có thể chạy cục bộ đáng tin cậy, mock/stub cho ranh giới bên ngoài cần tính xác định, và test sandbox có kiểm soát cho hành vi mà emulator không mô phỏng đầy đủ.

## 1. Testcontainers giải quyết vấn đề gì?

Integration test thường cần một hoặc nhiều dependency đang hoạt động. Nếu dùng database cài sẵn trên máy developer, kết quả phụ thuộc phiên bản, cấu hình, dữ liệu cũ và trạng thái môi trường. Nếu dùng database in-memory, test có thể không phản ánh đúng behavior của database production.

Testcontainers giải quyết bằng cách quản lý vòng đời container trong test:

1. Test khai báo image và cấu hình service cần dùng.
2. Test framework khởi động container trước khi test cần dependency chạy.
3. Container mở port hoặc network alias cho test.
4. Ứng dụng nhận endpoint, username, password và các property tương ứng.
5. Test thực hiện request qua application thật.
6. Sau khi test hoàn tất, container được dừng và tài nguyên được dọn dẹp.

Với service broker, cách này hữu ích để kiểm tra:

- Repository lưu instance, binding và operation trên database thật.
- Flyway hoặc Liquibase migration chạy được trên đúng engine.
- Unique constraint và transaction isolation ngăn tạo resource trùng.
- Queue giao message và worker cập nhật operation state.
- Redis lock hoặc cache hoạt động với cấu hình thật.
- Provider adapter gọi một service có thể chạy trong container.
- OSB HTTP request đi qua Spring application và persistence thật.

Testcontainers không thay thế toàn bộ integration environment. Nó cung cấp dependency thật trong phạm vi test, còn việc kiểm tra ingress, TLS production, IAM cloud, quota tài khoản hoặc behavior riêng của managed provider có thể cần test ở môi trường khác.

## 2. Chọn đúng ranh giới cần chạy thật

Trước khi thêm container, hãy xác định test cần chứng minh điều gì. Không nên khởi động tất cả dependency cho mọi test vì sẽ làm suite chậm, khó debug và phụ thuộc Docker không cần thiết.

| Thành phần | Cách kiểm thử phù hợp | Lý do |
|---|---|---|
| PostgreSQL/MySQL broker store | Testcontainers với database thật | Kiểm tra SQL, migration, constraint, transaction |
| Redis cache/lock | Redis container khi semantics Redis quan trọng | Kiểm tra TTL, atomic command và lock |
| RabbitMQ/Kafka | Container tương ứng | Kiểm tra topology, serialization, redelivery |
| HTTP provider API | WireMock hoặc stub server | Kịch bản lỗi có thể tái lập và xác định |
| Provider có emulator đáng tin cậy | Emulator container nếu behavior cần thiết được hỗ trợ | Kiểm tra adapter mà không gọi cloud thật |
| Managed cloud service | Sandbox integration test có kiểm soát | Chỉ môi trường thật mới xác nhận một số semantics |
| Kubernetes API | Kind hoặc cluster test riêng khi cần | Kiểm tra RBAC, CRD, controller và resource lifecycle |
| Secret manager | Fake/stub cho unit/integration cơ bản; sandbox riêng cho contract | Tránh tạo secret thật hoặc yêu cầu quyền rộng trong suite thường |

Một broker có thể dùng PostgreSQL thật trong hầu hết integration tests, nhưng mock provider API để giả lập timeout, conflict và response lỗi. Một số test riêng sẽ chạy trên sandbox cloud để xác nhận API provider thực tế. Đây là sự phân chia hợp lý giữa tốc độ, độ tin cậy và chi phí.

## 3. Phân biệt unit, slice, integration và end-to-end test

Testcontainers thường phù hợp nhất với integration test, nhưng cần đặt nó trong chiến lược kiểm thử tổng thể.

| Loại test | Phạm vi | Ví dụ trong service broker |
|---|---|---|
| Unit test | Một class hoặc domain component | Quota policy, state transition, fingerprint |
| Spring slice test | Một phần Spring context | MVC controller, JSON serialization |
| Integration test | Nhiều lớp cùng dependency thật | OSB endpoint + service + PostgreSQL |
| Component test | Một component chạy như service độc lập | Broker app + PostgreSQL + RabbitMQ |
| Provider contract test | Adapter đối chiếu contract provider | Request/response, retry, error mapping |
| End-to-end test | Platform và nhiều hệ thống liên kết | Cloud Foundry/Kubernetes gọi broker và provider sandbox |

Không cần chạy container cho mọi unit test. Unit test nên nhanh, cô lập và không cần Docker. Integration test dùng Testcontainers để xác minh behavior của các thành phần thật. End-to-end test nên ít hơn, chạy ở pipeline hoặc môi trường phù hợp vì thường tốn thời gian và cần cấu hình nhiều hơn.

## 4. Chuẩn bị dependency và môi trường Docker

Testcontainers cần runtime container tương thích, thường là Docker Engine hoặc Docker Desktop đang hoạt động. Trong CI, runner phải có quyền truy cập Docker daemon hoặc môi trường container runtime được hỗ trợ.

Các bước chuẩn bị:

1. Chọn phiên bản Testcontainers tương thích với JDK, JUnit và Spring Boot của dự án.
2. Dùng dependency quản lý phiên bản thống nhất, chẳng hạn Testcontainers BOM.
3. Thêm module JUnit Jupiter và module cho service cần chạy.
4. Xác nhận Docker daemon sẵn sàng trước khi test.
5. Chọn image version rõ ràng, tránh phụ thuộc tag trôi nổi trong pipeline quan trọng.
6. Thiết lập timeout startup và wait strategy hợp lý.
7. Đảm bảo CI có thể pull image hoặc dùng registry mirror đã cấu hình.

Ví dụ Gradle minh họa:

~~~groovy
dependencies {
    testImplementation platform("org.testcontainers:testcontainers-bom:<version>")
    testImplementation "org.testcontainers:junit-jupiter"
    testImplementation "org.testcontainers:postgresql"
}
~~~

Ví dụ Maven có thể khai báo BOM trong dependencyManagement và các module tương ứng trong test scope. Hãy dùng cùng một phiên bản Testcontainers cho core, JUnit integration và service module để tránh lỗi classpath.

Không cần thêm Testcontainers vào runtime scope của ứng dụng broker. Đây là dependency phục vụ test.

## 5. Chạy PostgreSQL thật cho broker repository

Nếu production dùng PostgreSQL, integration test nên chạy PostgreSQL container thay vì giả định H2 tương đương. Hai database có thể khác nhau về kiểu dữ liệu, JSON operators, sequence, locking, constraint, collation và cú pháp SQL.

Ví dụ JUnit 5:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class BrokerPostgresIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("broker_test")
            .withUsername("broker")
            .withPassword("broker-test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void applicationStartsAgainstRealPostgres() {
        // Thực hiện assertion qua repository hoặc HTTP endpoint.
    }
}
~~~

Ví dụ này minh họa cách wiring datasource. Hãy dùng image version được dự án chấp thuận; pipeline ổn định có thể pin version cụ thể hoặc digest để tránh image tag thay đổi ngoài ý muốn.

Test phải xác nhận ứng dụng thực sự kết nối container. Không để test vô tình dùng datasource local hoặc profile developer. Một cách là kiểm tra JDBC metadata trong test hoặc thực hiện một thao tác chỉ có trong engine production.

### 5.1. Dùng DynamicPropertySource hoặc ServiceConnection

Có hai cách thường gặp để đưa connection information vào Spring:

- **DynamicPropertySource:** đăng ký JDBC URL, username và password lấy từ container.
- **ServiceConnection:** nếu phiên bản Spring Boot và Testcontainers tích hợp hỗ trợ, annotation có thể tự tạo connection details cho dependency tương ứng.

DynamicPropertySource có tính tường minh và phù hợp khi cấu hình tùy chỉnh. ServiceConnection giúp giảm boilerplate nhưng phụ thuộc phiên bản Spring Boot và module integration. Không giả định annotation này tồn tại trong mọi phiên bản dự án.

### 5.2. Không dùng password production trong test

Credentials container phải là test-only, không dùng lại secret môi trường thật. Testcontainers có thể sinh password ngẫu nhiên nếu test cần; nếu cấu hình cố định, chỉ dùng giá trị giả trong test. Không ghi secret provider hoặc vault thật vào log.

## 6. Kiểm tra database migration bằng engine thật

Broker thường dùng Flyway hoặc Liquibase để tạo bảng service instance, binding, operation, outbox và quota. Migration có thể chạy trên H2 nhưng thất bại trên PostgreSQL do type, index, constraint hoặc SQL dialect.

Integration test nên khởi động container rỗng và để ứng dụng chạy migration như startup bình thường.

Các assertion hữu ích:

- Tất cả migration hiện hành được áp dụng.
- Schema history table có version mong đợi.
- Primary key và unique constraint tồn tại.
- Foreign key và index được tạo đúng.
- JSON/JSONB, UUID, timestamp và numeric mapping hoạt động.
- Migration từ schema version cũ sang mới giữ dữ liệu.
- Migration lỗi khiến startup thất bại rõ ràng, không để schema ở trạng thái nửa chừng.

Không chỉ kiểm tra ứng dụng khởi động. Một test migration tốt cần tạo bản ghi đại diện, đọc lại và xác minh constraint bằng thao tác thật.

## 7. Kiểm tra transaction và idempotency trên database thật

Idempotency của OSB phụ thuộc vào unique constraints và transaction. Test với database in-memory có thể không tái hiện đúng race condition hoặc isolation semantics production.

Ví dụ, service broker dùng composite key cho instance:

~~~sql
CREATE TABLE service_instance (
    platform_instance_id VARCHAR(128) NOT NULL,
    instance_id VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    lifecycle_state VARCHAR(32) NOT NULL,
    PRIMARY KEY (platform_instance_id, instance_id)
);
~~~

Integration test nên xác minh:

- Hai request cùng platformInstanceId và instanceId không tạo hai record.
- Cùng ID nhưng fingerprint khác tạo conflict.
- Binding key gồm platformInstanceId, instanceId và bindingId.
- Worker retry không tăng quota hoặc reference count hai lần.
- Optimistic locking phát hiện update trên version cũ.
- Transaction rollback không để lại reservation một phần.
- Outbox event được ghi cùng transaction với operation.

Test concurrency nên thực sự gửi hai request hoặc chạy hai transaction đồng thời. Không chỉ gọi cùng method tuần tự hai lần.

## 8. Kiểm thử cạnh tranh bằng hai request đồng thời

Ví dụ dưới đây minh họa cách đồng bộ hai thread trước khi gọi cùng một use case. Cách cụ thể có thể dùng ExecutorService, CountDownLatch hoặc test client gửi request song song.

~~~java
@Test
void concurrentProvisionCreatesOneInstance() throws Exception {
    var ready = new CountDownLatch(2);
    var start = new CountDownLatch(1);

    Callable<ProvisionResult> request = () -> {
        ready.countDown();
        start.await();
        return provisionService.provision(commandFor("instance-42"));
    };

    var first = executor.submit(request);
    var second = executor.submit(request);

    ready.await();
    start.countDown();

    var resultA = first.get();
    var resultB = second.get();

    assertThat(instanceRepository.countByInstanceId("instance-42"))
        .isEqualTo(1);
}
~~~

Đây là pseudocode cần bổ sung quản lý executor và cleanup trong test thực tế. Kết quả mong đợi là một resource reservation duy nhất; request thứ hai được phân loại thành retry cùng intent hoặc conflict theo fingerprint.

Để test thực sự có giá trị, hãy xác minh cả provider call count hoặc outbox event count, không chỉ số hàng database. Nếu database chỉ có một row nhưng provider adapter bị gọi hai lần, side effect vẫn có thể bị lặp.

## 9. Chạy RabbitMQ hoặc Kafka container cho asynchronous operations

Nếu broker dùng queue để xử lý provision/update/deprovision, cần kiểm tra message topology, serialization, redelivery và worker behavior với broker thật.

Ví dụ RabbitMQ container:

~~~java
@Testcontainers
@SpringBootTest
class BrokerMessagingIntegrationTest {

    @Container
    static final RabbitMQContainer rabbit =
        new RabbitMQContainer("rabbitmq:3-management-alpine");

    @DynamicPropertySource
    static void messagingProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add("spring.rabbitmq.port", rabbit::getAmqpPort);
        registry.add("spring.rabbitmq.username", rabbit::getAdminUsername);
        registry.add("spring.rabbitmq.password", rabbit::getAdminPassword);
    }
}
~~~

Tên property cần khớp cấu hình Spring Boot của ứng dụng. Với Kafka, dùng module Kafka tương ứng và cấu hình bootstrap servers từ container.

Các test nên xác minh:

- Queue/exchange/topic được khai báo đúng.
- Message chứa operation ID và resource namespace.
- Worker nhận và deserialize event.
- Message redelivery không tạo provider side effect lặp.
- Ack chỉ diễn ra sau khi state đã commit.
- Lỗi tạm thời được retry theo policy.
- Poison message được đưa vào dead-letter path nếu thiết kế có hỗ trợ.
- Restart worker không làm operation biến mất.

Không dùng queue giả lập nếu mục tiêu test là xác minh routing, ack hoặc redelivery behavior của broker thật.

## 10. Kiểm tra Redis, lock và cache khi có ý nghĩa

Nếu broker dùng Redis cho distributed lock, cache hoặc idempotency token, container Redis có thể giúp kiểm tra semantics thực tế.

Một số trường hợp:

- Lock có TTL và tự hết hạn khi worker chết.
- Hai worker không cùng claim một operation.
- Cache key có platformInstanceId và tenant scope.
- Invalidation diễn ra sau update/deprovision.
- Atomic command hoặc Lua script thực thi đúng.
- Retry không tăng counter hoặc reference count hai lần.

Không nên test lock chỉ bằng cách gọi method tuần tự. Cần hai client/worker cùng tranh chấp key và xác minh chỉ một bên nhận quyền xử lý.

Nếu production dùng Redis cluster, sentinel hoặc managed Redis với cấu hình TLS/ACL đặc biệt, một Redis standalone container chỉ kiểm tra được phần semantics tương ứng. Những khác biệt về topology và authentication cần test riêng trong môi trường gần production.

## 11. Kiểm thử provider adapter: container, stub hay sandbox?

Provider adapter là ranh giới giữa broker và hạ tầng. Chọn phương án theo loại provider:

### 11.1. Provider có thể chạy trong container

Nếu service thực tế là PostgreSQL, Redis hoặc RabbitMQ, broker có thể tạo resource riêng trong container rồi kiểm tra create, bind, revoke và delete thực sự.

Ví dụ với PostgreSQL provider test, adapter có thể tạo database và role trên cùng container. Test xác minh user có thể kết nối, quyền đọc/ghi đúng và revoke khiến kết nối mới bị từ chối.

### 11.2. Provider là HTTP API bên ngoài

Dùng WireMock hoặc HTTP stub để kiểm tra request method, path, headers, payload, timeout và mapping lỗi. Stub cho phép mô phỏng provider trả 429, 409, 500, timeout hoặc response malformed một cách xác định.

Ví dụ stub HTTP không thay thế provider thật. Nó chỉ xác minh broker gửi đúng contract và xử lý response đúng. Khi cần xác nhận semantics thực tế, dùng sandbox provider có quota và cleanup rõ ràng.

### 11.3. Provider emulator

Một emulator như LocalStack có thể hữu ích cho một số API AWS, nhưng không đảm bảo mô phỏng mọi behavior, IAM edge case, quota, consistency hoặc billing của cloud thật. Chỉ dùng emulator cho các chức năng đã được kiểm chứng là được hỗ trợ; bổ sung sandbox test cho behavior quan trọng mà emulator không bảo đảm.

Không gọi cloud production trong integration test mặc định. Test có thể tạo tài nguyên tính phí hoặc để lại resource nếu cleanup thất bại.

## 12. Kiểm thử OSB HTTP lifecycle end-to-end trong application

Một integration test có thể chạy Spring application thật, PostgreSQL container và provider adapter stub/containerized. Test gửi HTTP request theo OSB API qua server port thực tế hoặc MockMvc/WebTestClient theo cách test setup.

Các luồng cần kiểm tra:

| OSB endpoint | Hành vi cần xác minh |
|---|---|
| GET catalog | Catalog và capability phản ánh implementation |
| PUT service_instances | Reservation, provider create và state |
| GET last_operation | Polling chỉ đọc operation state |
| PATCH service_instances | Update parameters/plan theo policy |
| PUT service_bindings | Tạo principal và trả credentials |
| GET service_bindings | Retrieval nếu capability được công bố |
| DELETE service_bindings | Revoke đúng principal |
| DELETE service_instances | Deprovision đúng provider resource |

Ví dụ HTTP request provision:

~~~http
PUT /v2/service_instances/instance-42?accepts_incomplete=true
X-Broker-API-Version: 2.17
Content-Type: application/json
Authorization: Basic <test-credential>
~~~

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "parameters": {
    "storage_gb": 100
  }
}
~~~

Test nên xác minh status code, response body, database row, operation record, outbox event và provider call. Chỉ assert HTTP 202 là chưa đủ nếu operation không được lưu hoặc worker không thể tiếp tục.

Nếu dùng Spring Cloud Open Service Broker, hãy dùng model/extension point đúng phiên bản dependency. Ví dụ HTTP ở trên mô tả contract OSB; không phải cam kết rằng mọi version thư viện có cùng method signature hoặc test utility.

## 13. Testcontainers và Spring Boot context lifecycle

Spring TestContext có thể cache application context giữa các test class. Nếu container dừng sau khi một class hoàn tất nhưng context vẫn được cache, class tiếp theo có thể dùng connection trỏ tới container đã dừng.

Cần chọn một chiến lược lifecycle rõ ràng:

- Container static trong một test class khi context chỉ dùng trong class đó.
- Singleton container dùng chung trong test suite khi Spring context được cache giữa nhiều class.
- Dùng @DirtiesContext nếu cần đóng context cùng container theo ranh giới test.
- Chia test suite theo dependency/lifecycle để không tái sử dụng context với endpoint đã hết hiệu lực.

Không trộn các chiến lược tùy tiện. Nếu dùng singleton container, phải bảo đảm shutdown được quản lý ở cuối suite và không có test chạy song song vô tình xóa dữ liệu của test khác.

Với Spring Boot hỗ trợ ServiceConnection, connection details có thể được gắn vào context; nhưng vòng đời container vẫn phải tương thích với vòng đời context.

## 14. Cô lập dữ liệu giữa test

Một database container có thể được dùng cho nhiều test, nhưng mỗi test phải có dữ liệu độc lập.

Các cách thường dùng:

- Tạo database hoặc schema riêng cho test class.
- Dùng tenant ID, instance ID và binding ID duy nhất theo test.
- Xóa record theo khóa nghiệp vụ sau mỗi test.
- Dùng truncate theo thứ tự foreign key khi phù hợp.
- Tạo container mới cho nhóm test cần isolation tuyệt đối.
- Reset queue, cache và provider resource giữa test.

Không dựa vào @Transactional rollback để dọn mọi test HTTP. Khi test gửi request tới Spring server chạy trên thread khác, transaction của test không tự động bao phủ transaction của request handler. Hãy cleanup rõ ràng bằng repository/service hoặc dùng database/schema mới.

Test parallel cần tránh chia sẻ cùng instance ID, binding ID, queue name và cache key. Nếu dùng resource ID cố định, hai test có thể tạo conflict không liên quan tới behavior đang kiểm tra.

## 15. Chờ service sẵn sàng bằng health/readiness strategy

Container process đã chạy không đồng nghĩa service đã sẵn sàng nhận request. PostgreSQL có thể còn recovery, RabbitMQ đang khởi tạo plugin hoặc HTTP provider test server chưa mở port.

Testcontainers có wait strategies để chờ log message, port hoặc health check. Hãy chọn điều kiện phản ánh readiness thực tế.

Nguyên tắc:

- Ưu tiên health check hoặc port readiness được service hỗ trợ.
- Chọn timeout phù hợp, tránh chờ vô hạn.
- Không dùng sleep cố định để giả định service đã sẵn sàng.
- Nếu service cần initialization script, chờ script hoàn tất.
- Log container output khi startup thất bại để debug.
- Với service có readiness nhiều giai đoạn, kiểm tra endpoint health thực tế.

Đối với asynchronous operation trong broker, dùng polling có timeout hoặc thư viện như Awaitility để chờ state condition. Tránh Thread.sleep dài vì test chậm và vẫn có thể flaky.

Ví dụ:

~~~java
await()
    .atMost(Duration.ofSeconds(20))
    .pollInterval(Duration.ofMillis(200))
    .untilAsserted(() ->
        assertThat(operationRepository.findState(operationId))
            .contains("SUCCEEDED")
    );
~~~

Cấu hình Awaitility cần phù hợp test runtime. Polling phải đọc state store hoặc API last operation, không kích hoạt side effect mới.

## 16. Test cleanup và dữ liệu provider

Cleanup là một phần của correctness. Test tạo database, role, queue hoặc bucket phải xóa chúng ngay cả khi assertion thất bại.

Một số nguyên tắc:

- Dùng external name có prefix dành riêng cho test run.
- Lưu danh sách provider resource đã tạo.
- Cleanup trong finally hoặc lifecycle hook.
- Xóa binding/principal trước khi xóa instance nếu provider yêu cầu.
- Xác minh resource đã absent sau cleanup.
- Giữ log resource ID để điều tra cleanup failure.
- Không cleanup resource ngoài namespace của test.
- Dùng TTL hoặc janitor job cho sandbox resources bị bỏ sót.

Nếu test chỉ dùng container ephemeral, dừng container thường dọn phần lớn dữ liệu. Nhưng nếu container kết nối tới cloud sandbox hoặc provider thật, việc dừng container không tự xóa tài nguyên cloud đã tạo.

## 17. Test dữ liệu nhạy cảm và bảo mật

Service broker xử lý credentials trong binding và provider authentication. Integration test cần xác minh secret được lưu, trả và log đúng cách.

Các kiểm tra:

- Password không xuất hiện trong application log.
- Error response không trả stack trace hoặc provider secret.
- Secret store chỉ cho broker test identity truy cập.
- Binding response trả đúng credential của binding.
- Tenant A không retrieve được binding của tenant B.
- Unbind làm credential mất hiệu lực theo policy.
- Provider API token không được serialize vào outbox message.
- Container log không chứa secret production.
- Test fixture dùng credential giả và được reset.

Không dùng snapshot database production hoặc secret thật làm fixture. Nếu cần test migration dữ liệu legacy, tạo fixture đã scrub PII và thay secret bằng giá trị test.

## 18. CI và hiệu năng test suite

Testcontainers có startup cost và phụ thuộc image pull. Để CI ổn định:

- Pin image version hoặc digest cho suite quan trọng.
- Cache image layer hoặc dùng registry mirror.
- Giới hạn số container chạy đồng thời.
- Chia unit test nhanh và integration test cần Docker thành task riêng.
- Chạy integration suite trên runner có Docker daemon được hỗ trợ.
- Lưu container logs khi test thất bại.
- Đặt timeout cho startup và toàn test.
- Không bật container reuse trong CI nếu lifecycle chưa được kiểm soát.
- Theo dõi thời gian startup, thời gian test và flakiness.
- Chạy một tập smoke integration test trên mỗi pull request và suite rộng hơn theo lịch nếu chi phí cao.

Local developer có thể bật container reuse theo cấu hình Testcontainers phù hợp để tăng tốc, nhưng phải hiểu dữ liệu cũ có thể còn lại giữa lần chạy. CI nên ưu tiên môi trường sạch và tái lập được.

## 19. Các lỗi thường gặp khi dùng Testcontainers

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng H2 thay PostgreSQL production | Không phát hiện SQL/transaction khác biệt | Test với PostgreSQL container |
| Dùng image tag trôi nổi | Kết quả thay đổi theo thời điểm pull | Pin version hoặc digest |
| Container chạy nhưng chưa ready | Test fail ngẫu nhiên | Wait strategy và health check |
| Spring context cache nhưng container đã dừng | Connection refused ở test class sau | Đồng bộ container/context lifecycle |
| Dùng @Transactional để rollback request HTTP | Dữ liệu test vẫn tồn tại | Cleanup rõ hoặc schema/database riêng |
| Chạy test song song với ID cố định | Test va chạm dữ liệu | Unique test namespace |
| Mock mọi provider behavior | Không phát hiện lỗi protocol hoặc service thật | Container/sandbox cho behavior quan trọng |
| Coi emulator là cloud thật | Bỏ sót IAM/quota/consistency | Sandbox test có kiểm soát |
| Không cleanup cloud resource | Tốn phí và để lại tài nguyên | Resource registry và janitor |
| Chỉ assert HTTP response | Không phát hiện side effect trùng | Kiểm tra database, queue và provider |
| Thread.sleep để chờ worker | Test chậm và flaky | Awaitility/polling có timeout |
| Dùng secret production trong test | Rò rỉ credential | Test-only secrets và redaction |

## 20. Một bộ integration test tham khảo cho service broker

Có thể tổ chức suite theo mục tiêu:

| Test suite | Dependencies | Điều cần chứng minh |
|---|---|---|
| RepositoryIT | PostgreSQL | Mapping, constraint, transaction, migration |
| LifecycleHttpIT | PostgreSQL + provider stub | OSB HTTP request, validation và response |
| BindingProviderIT | PostgreSQL + PostgreSQL/RabbitMQ container | Tạo user/role, credentials, revoke |
| AsyncOperationIT | PostgreSQL + RabbitMQ | Outbox, worker, retry, last_operation |
| CacheLockIT | PostgreSQL + Redis | Lock, TTL, cache isolation |
| ProviderContractIT | WireMock hoặc sandbox | Provider request/response và error mapping |
| KubernetesAdapterIT | Kind/test cluster khi cần | RBAC, namespace, resource adoption |
| SmokeIT | Dependency tối thiểu | Application startup và một lifecycle path |

Không nhất thiết tất cả suite phải chạy trong cùng một pipeline stage. Chọn dependency theo test objective để suite nhanh và dễ chẩn đoán.

Một kịch bản integration đầy đủ có thể là:

1. Khởi động PostgreSQL container và chạy schema migration.
2. Khởi động provider container hoặc HTTP stub.
3. Gửi GET catalog và xác minh offering/plan.
4. Gửi PUT provision cho một instance.
5. Xác minh reservation, provider resource mapping và operation state.
6. Poll last operation đến terminal state.
7. Gửi PUT binding và xác minh credential/permission.
8. Gửi lại cùng request để xác minh idempotency.
9. Gửi DELETE binding và xác minh credential bị revoke.
10. Gửi DELETE instance và xác minh provider resource đã được giải phóng.
11. Xác minh quota, outbox và audit không có record trùng.
12. Dọn dữ liệu và dừng dependency containers.

## 21. Checklist quyết định dùng Testcontainers

Trước khi thêm container vào một test, hãy tự hỏi:

- [ ] Test cần xác minh behavior nào mà mock không thể chứng minh?
- [ ] Dependency có thể chạy cục bộ bằng container một cách đáng tin cậy không?
- [ ] Image và phiên bản có tương thích với production không?
- [ ] Test có cần database engine thật để xác minh SQL/transaction không?
- [ ] Có thể dùng stub cho provider HTTP để kiểm soát lỗi và timeout không?
- [ ] Nếu dùng emulator, behavior cần kiểm tra có được hỗ trợ không?
- [ ] Nếu cần cloud thật, có sandbox, quota, credential và cleanup policy không?
- [ ] Container readiness và lifecycle có đồng bộ với Spring context không?
- [ ] Dữ liệu test có được cô lập khi chạy song song không?
- [ ] Resource được tạo có cleanup ngay cả khi test fail không?
- [ ] CI runner có Docker/runtime và image cache phù hợp không?
- [ ] Logs và fixtures không chứa secret hoặc dữ liệu production?

Testcontainers phát huy giá trị khi nó kiểm chứng một dependency thật ở đúng ranh giới cần kiểm tra: PostgreSQL cho repository và transaction, RabbitMQ cho message delivery, Redis cho lock/cache hoặc service container cho provider adapter. Với API cloud không thể mô phỏng đầy đủ, hãy kết hợp stub xác định và sandbox test có kiểm soát. Khi integration tests xác minh cả HTTP contract, database state, queue/worker behavior, provider side effect và cleanup, Spring Cloud Service Broker có bằng chứng đáng tin cậy hơn rằng các luồng OSB hoạt động cùng nhau trong môi trường gần thực tế.
