# Dọn tài nguyên và ngăn dữ liệu kiểm thử lẫn giữa các lần chạy

Các bài kiểm thử service discovery thường khởi động nhiều tài nguyên bên ngoài tiến trình test: registry, provider giả lập, database, message broker, container, namespace Kubernetes và các kết nối HTTP. Nếu chỉ kiểm tra assertion mà không quản lý vòng đời những tài nguyên này, lần chạy sau có thể đọc registration cũ, dùng lại instance ID, gặp port đã bị chiếm hoặc nhận dữ liệu do test khác tạo ra.

Vấn đề trở nên rõ hơn khi chạy test song song trên máy developer và CI. Hai test có thể cùng đăng ký `inventory-service`, cùng dùng một Consul catalog hoặc cùng xóa một znode. Kết quả là test lúc pass lúc fail, khó tái hiện và để lại dữ liệu rác trong môi trường dùng chung.

Bài này trình bày cách tổ chức setup/teardown, cách cô lập registry và test data, quản lý Testcontainers và Spring ApplicationContext, xử lý registration theo provider, cùng các nguyên tắc để test có thể chạy lặp lại và song song an toàn.

## 1. Tài nguyên nào cần được quản lý?

Một test service discovery có thể tạo ra nhiều loại tài nguyên:

| Tài nguyên | Ví dụ | Rủi ro nếu không dọn |
| --- | --- | --- |
| Registry server/container | Consul, Eureka, ZooKeeper | Container/process tiếp tục chạy, chiếm port và bộ nhớ |
| Service registration | `inventory-service` instance `test-1` | Consumer test sau nhìn thấy instance cũ |
| Discovery cache/watch | Curator `ServiceCache`, Kubernetes informer | Listener/thread giữ tham chiếu hoặc snapshot cũ |
| HTTP client/connection pool | WebClient, Reactor Netty | Socket, event loop và connection còn tồn tại |
| Spring ApplicationContext | Bean, scheduler, listener, client | Context giữ connection tới container đã dừng |
| Database/test data | Row, schema, collection | Test sau đọc dữ liệu của lần chạy trước |
| Message broker | Topic, queue, consumer group | Message cũ được xử lý trong test mới |
| File và thư mục tạm | Log, config, snapshot | Dữ liệu cũ ảnh hưởng assertion hoặc lộ thông tin |
| Kubernetes resource | Namespace, Service, ConfigMap, Secret | Resource tồn tại sau khi test kết thúc |

Mỗi tài nguyên cần có owner, thời điểm tạo, phạm vi sử dụng và cách đóng/xóa. Nếu không xác định được ai sở hữu tài nguyên, rất dễ xóa nhầm tài nguyên của test khác hoặc của môi trường developer.

## 2. Nguyên tắc thiết kế cleanup

Một quy trình test tốt nên tuân theo các nguyên tắc sau:

1. **Tạo tài nguyên trong phạm vi hẹp nhất:** method, class, suite hoặc toàn bộ test run tùy chi phí khởi tạo.
2. **Gán danh tính duy nhất:** service ID, instance ID, namespace, topic và schema phải phân biệt giữa các test/run.
3. **Đăng ký cleanup ngay sau khi tạo:** nếu bước setup tiếp theo thất bại, tài nguyên đã tạo vẫn phải được dọn.
4. **Dọn theo đúng ownership:** chỉ xóa registration/resource do test hiện tại tạo.
5. **Đóng theo thứ tự ngược dependency:** dừng consumer/client trước registry/container mà chúng đang kết nối.
6. **Không phụ thuộc thứ tự test:** mỗi test tự tạo dữ liệu cần thiết và không dựa vào test chạy trước.
7. **Cleanup phải idempotent:** chạy hai lần không làm hỏng trạng thái hoặc xóa nhầm dữ liệu khác.
8. **Không che lỗi test bằng lỗi teardown:** giữ cả lỗi chính và lỗi cleanup để điều tra.

Một quy tắc hữu ích là mỗi test có một `runId`, mỗi test case có một `caseId`; ghép chúng vào mọi tài nguyên có thể đặt tên:

```text
runId  = ci-4821-7f2a
caseId = register-two-instances

serviceId  = inventory-test-ci-4821-7f2a-register-two-instances
instanceId = inventory-ci-4821-7f2a-register-two-instances-01
namespace  = sd-ci-4821-7f2a-register-two-instances
```

Tên ví dụ cần được rút gọn và chuẩn hóa theo giới hạn của provider. Không dùng một ID cố định như `test-service` khi có khả năng chạy đồng thời nhiều test.

## 3. Chọn phạm vi vòng đời: method, class hay suite

Không phải tài nguyên nào cũng cần tạo và hủy cho mỗi test method. Tạo quá nhiều registry container làm suite chậm; dùng một registry chung mà không cô lập dữ liệu lại gây nhiễm chéo.

| Phạm vi | Cách quản lý | Khi phù hợp |
| --- | --- | --- |
| Method | `@BeforeEach` / `@AfterEach`, try-with-resources | Tài nguyên rẻ, dữ liệu cần sạch hoàn toàn cho từng case |
| Class | `@BeforeAll` / `@AfterAll`, static Testcontainer | Nhiều method dùng chung registry/container nhưng registration phải riêng |
| Suite | Singleton container hoặc suite fixture | Container nặng, nhiều class cần cùng registry server |
| Test run/CI job | Hạ tầng ephemeral của job, namespace hoặc project riêng | Kiểm thử tích hợp nhiều service và dữ liệu lớn |

Tài nguyên có thể dùng chung ở tầng server, nhưng dữ liệu bên trong vẫn phải cô lập theo test. Ví dụ một Consul container dùng chung cho class có thể phục vụ nhiều method; mỗi method phải có service ID/instance ID riêng và deregister sau khi chạy.

Không nên chọn phạm vi rộng hơn chỉ để giảm thời gian khởi tạo nếu chưa có cơ chế cô lập và dọn dữ liệu đáng tin cậy.

## 4. Dùng JUnit 5 để đóng tài nguyên chắc chắn

Với tài nguyên triển khai `AutoCloseable`, ưu tiên try-with-resources. Java sẽ gọi `close()` ngay cả khi assertion hoặc thao tác ở giữa ném exception:

```java
@Test
void readsServiceInstances() throws Exception {
    try (TestingServer server = new TestingServer()) {
        // Tạo Curator client, đăng ký service và thực hiện assertion.
    }
}
```

Với tài nguyên sống qua nhiều method, dùng `@BeforeAll`/`@AfterAll` hoặc JUnit extension. Đặt cleanup trong `@AfterEach` để nó chạy sau mỗi test kể cả khi assertion thất bại:

```java
class DiscoveryRegistrationTest {

    private RegistryFixture registry;
    private String serviceId;
    private String instanceId;

    @BeforeEach
    void setUp() {
        registry = RegistryFixture.start();
        serviceId = "inventory-test-" + UUID.randomUUID();
        instanceId = serviceId + "-instance-1";
    }

    @AfterEach
    void tearDown() {
        if (registry != null) {
            registry.deregister(serviceId, instanceId);
            registry.close();
        }
    }
}
```

Ví dụ trên minh họa ý tưởng; `RegistryFixture` là helper do test suite định nghĩa. Nếu `deregister` có thể ném exception, hãy bảo đảm `close()` vẫn được gọi bằng `try/finally` hoặc để fixture tự quản lý cả hai thao tác.

Một mẫu teardown an toàn hơn:

```java
@AfterEach
void tearDown() {
    try {
        if (registry != null) {
            registry.deregister(serviceId, instanceId);
        }
    } finally {
        if (registry != null) {
            registry.close();
        }
    }
}
```

Khi nhiều tài nguyên phụ thuộc nhau, có thể đóng chúng theo thứ tự ngược tạo. Ví dụ: dừng service cache/listener, đóng Curator client, rồi mới dừng ZooKeeper server.

## 5. Testcontainers cho registry thật

Mock giúp test logic consumer nhanh, nhưng một số lỗi chỉ xuất hiện khi giao tiếp với registry thật: protocol, health API, ACL, session, registration lifecycle và network. Testcontainers có thể khởi động registry trong container cô lập.

Ví dụ chạy Consul agent ở chế độ development cho integration test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class ConsulDiscoveryIntegrationTest {

    @Container
    static final GenericContainer<?> consul =
            new GenericContainer<>(DockerImageName.parse("hashicorp/consul:1.20"))
                    .withCommand("agent", "-dev", "-client=0.0.0.0")
                    .withExposedPorts(8500);

    @DynamicPropertySource
    static void consulProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cloud.consul.host", consul::getHost);
        registry.add("spring.cloud.consul.port",
                () -> consul.getMappedPort(8500));
    }

    @Test
    void registersAndDiscoversService() {
        // Khởi động application context và kiểm tra registration.
    }
}
```

Đây là ví dụ cấu hình test; image tag cần được pin theo phiên bản đã được dự án kiểm chứng. Không dùng Consul `-dev` cho production hoặc test bảo mật vì nó không mô phỏng đầy đủ cấu hình ACL, TLS và quorum.

`@Container` static giữ container trong phạm vi class. Nếu dùng chung container cho nhiều class, cần một suite-level singleton fixture hoặc cơ chế quản lý tương đương. Không bật reusable container trong CI một cách tùy tiện: container tái sử dụng có thể giữ catalog, token, config và dữ liệu từ lần chạy trước.

### Lưu ý về Spring TestContext cache

Spring TestContext có thể cache `ApplicationContext` giữa các test class. Nếu container bị dừng sau class đầu tiên nhưng context còn được cache và tái sử dụng, bean HTTP client/discovery client có thể tiếp tục trỏ đến container đã dừng.

Có hai hướng:

- Dùng container có vòng đời ít nhất bằng vòng đời của các `ApplicationContext` đang dùng nó.
- Đánh dấu context cần đóng sau class bằng `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)` khi fixture thực sự yêu cầu context riêng.

`@DirtiesContext` đóng context; nó không tự xóa registration, topic, row hoặc resource đã tạo trên hệ thống bên ngoài. Các dữ liệu đó vẫn cần cleanup riêng.

## 6. Dynamic properties và port ngẫu nhiên

Không hard-code port của registry test. Testcontainers ánh xạ port động trên host; `@DynamicPropertySource` giúp truyền địa chỉ thực tế vào Spring context:

```java
@DynamicPropertySource
static void registryProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.cloud.consul.host", consul::getHost);
    registry.add("spring.cloud.consul.port", () -> consul.getMappedPort(8500));
}
```

Với Eureka hoặc service provider giả lập, áp dụng cùng nguyên tắc: server lắng nghe port ngẫu nhiên, test lấy port đang hoạt động và inject vào cấu hình. Điều này tránh xung đột khi nhiều test chạy đồng thời hoặc khi máy developer đã có dịch vụ chiếm port mặc định.

Không ghi endpoint động vào file cấu hình dùng chung của repository. Hãy truyền qua property source trong phạm vi test và đóng context/client khi hoàn tất.

## 7. Cô lập service ID và instance ID

Registry là hệ thống trạng thái bên ngoài ApplicationContext. Hai test cùng đăng ký một service ID có thể nhìn thấy registration của nhau dù mỗi test tạo Spring context riêng.

Tạo danh tính duy nhất cho mỗi test:

```java
class TestIdentity {
    static String newServiceId(String base) {
        return base + "-test-" + UUID.randomUUID();
    }

    static String newInstanceId(String serviceId) {
        return serviceId + "-" + UUID.randomUUID();
    }
}
```

Nếu provider chỉ cho phép service ID theo định dạng cụ thể, chuẩn hóa chuỗi trước khi gửi:

- Chuyển về chữ thường nếu provider phân biệt chữ hoa/chữ thường.
- Thay ký tự không hợp lệ bằng dấu gạch ngang.
- Giới hạn độ dài theo quy định provider.
- Tránh đưa email, username hoặc dữ liệu cá nhân vào ID.
- Giữ `runId` để truy vết nhưng không dùng ID ngẫu nhiên làm metric label.

Không chỉ làm instance ID duy nhất mà quên service ID. Consumer truy vấn theo service ID; nếu hai test cùng dùng `inventory-service`, mỗi test có thể nhìn thấy instance của test kia.

## 8. Cleanup registration trong Consul

Consul có service catalog và agent API. Khi test tự đăng ký service trực tiếp, cần deregister đúng `serviceId` do test sở hữu. Nếu Spring Cloud Consul tự động đăng ký, hãy xác định lifecycle deregistration của phiên bản đang dùng và vẫn có thể bổ sung cleanup phòng trường hợp test dừng bất thường.

Ví dụ gọi agent API để deregister một service ID đã tạo riêng cho test:

```java
void deregisterConsulService(RestClient client, String serviceId) {
    client.delete()
            .uri("/v1/agent/service/deregister/{id}", serviceId)
            .retrieve()
            .toBodilessEntity();
}
```

`RestClient` cần được cấu hình base URL trỏ đến Consul agent của test. Với ACL bật, client cần token có quyền phù hợp; không ghi token vào log. Chỉ gọi endpoint với ID do test hiện tại tạo.

Một số điểm cần nhớ:

- Deregister ở agent API không giống việc xóa toàn bộ service catalog.
- Không gọi `DELETE /v1/agent/service/deregister/<id>` với ID dùng chung của môi trường developer.
- Nếu dùng Spring Cloud auto-registration, đóng application context đúng lifecycle để registration được deregister theo cơ chế framework.
- Nếu agent/registry container bị dừng ngay, việc deregister có thể không còn ý nghĩa; vẫn phải đóng client và chờ container dừng sạch.
- Với test song song, mỗi method cần ID riêng và cleanup đúng ID của nó.

## 9. Cleanup registration trong Eureka

Eureka client đăng ký instance và thường deregister khi ứng dụng shutdown theo lifecycle của client. Test cần cho Spring context/client đóng trước khi dừng Eureka server.

Nếu test gọi Eureka REST API trực tiếp, chỉ xóa instance cụ thể thuộc test, theo application name và instance ID đã tạo. Không xóa toàn bộ application name nếu test khác đang dùng cùng registry.

Với Eureka server dùng chung trong suite:

1. Sinh application/service ID riêng cho từng test run nếu phù hợp với mục tiêu test.
2. Tạo instance ID duy nhất cho từng instance.
3. Chờ registration xuất hiện trước khi assertion.
4. Đóng client/context hoặc deregister instance cụ thể.
5. Chờ registry phản ánh việc xóa nếu test tiếp theo phụ thuộc vào kết quả đó.

Eureka có cache và propagation delay; không nên giả định instance biến mất tức thì khỏi mọi consumer sau một lời gọi deregister. Dùng Awaitility với timeout hữu hạn để chờ trạng thái hội tụ, thay vì `Thread.sleep()` cố định.

## 10. Cleanup znode và Curator

Với ZooKeeper, mỗi test nên có root path riêng, ví dụ:

```text
/tests/<runId>/<caseId>/services/inventory-service/<instanceId>
```

Khi dùng ephemeral znode, đóng session/client sẽ khiến node ephemeral gắn với session được xóa. Tuy nhiên, persistent parent/root path vẫn có thể tồn tại và cần cleanup nếu test tạo ra chúng.

Ví dụ xóa đúng test root:

```java
void deleteTestRoot(CuratorFramework client, String testRoot) throws Exception {
    if (client.checkExists().forPath(testRoot) != null) {
        client.delete()
                .guaranteed()
                .deletingChildrenIfNeeded()
                .forPath(testRoot);
    }
}
```

Chỉ truyền `testRoot` do test hiện tại sở hữu. Không gọi recursive delete ở `/services`, `/` hoặc parent path dùng chung. Nếu có nhiều test song song, root path riêng ngăn một test xóa znode của test khác.

Đóng theo thứ tự:

1. Đóng `ServiceCache`/`CuratorCache` và listener.
2. Xóa persistent test root nếu cần.
3. Đóng `CuratorFramework` client để session và ephemeral node được giải phóng.
4. Dừng `TestingServer` hoặc container ZooKeeper.

Nếu test đang xác minh session expiration, không xóa ephemeral node trước assertion; hãy để server/session behavior thực hiện rồi mới cleanup persistent root.

## 11. Cleanup tài nguyên Kubernetes

Với Kubernetes integration test, tạo namespace riêng cho mỗi test class hoặc test run:

```text
sd-test-<runId>-<caseId>
```

Đặt Service, Deployment, ConfigMap, Secret và các resource namespaced trong namespace đó. Khi test kết thúc, xóa namespace và chờ trạng thái `Terminating` hoàn tất trước khi tái sử dụng tên.

Nguyên tắc:

- Dùng namespace riêng thay vì xóa Service/Pod theo label chung trong namespace dùng chung.
- Label resource với `test-run-id` và `test-case-id` để truy vết.
- Không tạo ClusterRole, CRD hoặc resource cluster-scoped nếu test không cần; các resource đó không được xóa theo namespace.
- Không xóa namespace của developer hoặc namespace `default`.
- Nếu API server tạm thời lỗi, cleanup nên retry có giới hạn và báo rõ resource còn sót.
- Khi test ServiceAccount/RBAC, chỉ cấp quyền tối thiểu và xóa ServiceAccount/RoleBinding do test tạo.

Nếu dùng namespace chung cho cả suite, phải cô lập tên resource và cleanup theo UID/label của test. Namespace per run thường dễ điều tra và an toàn hơn khi chạy CI song song.

## 12. Dùng Awaitility thay cho sleep cố định

Registry thường cập nhật bất đồng bộ. Sau registration, deregistration hoặc watch reconnect, assertion ngay lập tức có thể chạy trước khi trạng thái hội tụ.

Ví dụ chờ service xuất hiện:

```java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            List<ServiceInstance> instances =
                    discoveryClient.getInstances(serviceId);
            assertThat(instances).hasSize(1);
        });
```

Ví dụ chờ instance biến mất sau deregistration:

```java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() ->
                assertThat(discoveryClient.getInstances(serviceId)).isEmpty());
```

Awaitility cần timeout hữu hạn và thông báo lỗi hữu ích. Không đặt thời gian chờ quá dài để che lỗi registration; khi timeout, in service ID, instance ID, provider và trạng thái registry đã quan sát.

`Thread.sleep()` có thể dùng trong test chuyên kiểm tra thời gian/lease với lý do cụ thể, nhưng không nên dùng để đoán lúc registry đã cập nhật.

## 13. Dọn HTTP client, scheduler và listener

Test có thể tạo `WebClient`, Reactor Netty `ConnectionProvider`, scheduler, executor, watch listener hoặc event listener. Các resource này cần được đóng theo ownership.

- Dùng Spring-managed bean nếu client thuộc ApplicationContext.
- Dùng `@PreDestroy`, `DisposableBean` hoặc `destroyMethod` cho resource bean có `close`/`dispose`.
- Đóng `ServiceCache`/`CuratorCache` trước Curator client.
- Dispose `ConnectionProvider` do test tự tạo; không dispose global shared Reactor Netty resources nếu test không sở hữu chúng.
- Dừng scheduler/executor tự tạo và chờ task kết thúc có giới hạn.
- Hủy subscription/listener trước khi dừng registry.

Ví dụ quản lý resource Reactor Netty tự tạo:

```java
@Test
void usesDedicatedConnectionPool() {
    ConnectionProvider provider = ConnectionProvider.create("test-pool", 10);
    try {
        HttpClient client = HttpClient.create(provider);
        // Tạo request và assertion.
    } finally {
        provider.dispose();
    }
}
```

Không gọi `dispose()` trên resource dùng chung do framework quản lý. Trước khi đóng, xác định rõ ai đã tạo và ai sở hữu lifecycle của resource đó.

## 14. Cô lập database, message broker và filesystem

Service discovery test thường kéo theo test data ở các dependency nghiệp vụ. Dọn registry thôi chưa đủ nếu test sau đọc database row hoặc message do test trước tạo.

### Database

- Dùng database/schema riêng theo test run nếu có thể.
- Với test method, transaction rollback phù hợp cho thao tác đồng bộ trên cùng transaction.
- Transaction rollback không tự hoàn tác side effect đã commit ở thread khác, message broker hoặc service bên ngoài.
- Với integration test chạy async, dùng fixture ID riêng và cleanup theo fixture ID.
- Không `TRUNCATE` bảng dùng chung khi test khác đang chạy.

### Message broker

- Dùng topic/queue/consumer group có tên duy nhất.
- Drain hoặc xóa message chỉ trong topic/queue do test sở hữu.
- Dừng consumer và chờ worker kết thúc trước khi xóa resource.
- Không dùng cùng consumer group cho test song song nếu mục tiêu test yêu cầu mỗi test nhận cùng message độc lập.

### Filesystem

- Dùng `@TempDir` của JUnit cho file tạm.
- Không ghi test artifact vào thư mục làm việc chung của developer.
- Không dùng tên file cố định nếu test chạy song song.
- Đảm bảo stream/file handle đóng trước khi thư mục bị xóa.

Ví dụ JUnit:

```java
@Test
void writesDiscoverySnapshot(@TempDir Path tempDir) throws IOException {
    Path snapshot = tempDir.resolve("registry-snapshot.json");
    Files.writeString(snapshot, "{}", StandardCharsets.UTF_8);
    assertThat(Files.exists(snapshot)).isTrue();
}
```

JUnit tự dọn thư mục tạm sau test. Không tự tạo một thư mục cố định trong `target/test-data` rồi để dữ liệu qua nhiều lần chạy nếu không có cơ chế reset.

## 15. Ngăn dữ liệu lẫn khi chạy song song

Test parallel-safe phải độc lập cả ở dữ liệu và resource. Chỉ dùng `UUID` cho service ID nhưng vẫn dùng chung znode root hoặc Consul token mutable thì chưa đủ.

Checklist cho parallel test:

- Mỗi test có run ID/case ID riêng.
- Service ID và instance ID không trùng.
- Namespace, znode root, topic, queue, schema và temp directory riêng.
- Không sửa cùng một cấu hình registry dùng chung trong lúc test khác đang chạy.
- Không xóa resource bằng selector rộng như `app=inventory-service` nếu test khác cũng có label đó.
- Không dùng biến static mutable để chứa registration state giữa các test.
- Không phụ thuộc thứ tự test hoặc thứ tự cleanup.
- Dùng lock chỉ khi thật sự cần chia sẻ tài nguyên không thể cô lập; lock phải có timeout và phạm vi rõ.

Nếu test không thể chạy song song an toàn, đánh dấu rõ và cấu hình JUnit/Surefire giới hạn concurrency cho nhóm đó. Đây là giải pháp có chủ đích; không nên tắt parallel execution cho toàn bộ suite chỉ vì một fixture dùng chung chưa được thiết kế đúng.

## 16. Context cache và `@DirtiesContext`

Spring TestContext cache ApplicationContext dựa trên cấu hình test. Điều này giúp giảm thời gian khởi tạo nhưng có thể khiến state trong singleton bean còn tồn tại giữa các method/class.

Ví dụ bean giữ danh sách đăng ký hoặc mock state có thể làm test sau nhìn thấy dữ liệu test trước dù registry container vẫn đang chạy.

Hãy:

- Reset state của bean/spy/mock ở mỗi test khi cần.
- Không giữ danh sách instance trong static field.
- Tạo service ID riêng cho từng test.
- Dùng `@DirtiesContext` khi test làm thay đổi cấu hình singleton hoặc resource không thể reset an toàn.
- Không dùng `@DirtiesContext` như cách xóa mọi external data; nó chỉ quản lý Spring context.
- Đảm bảo container/registry sống lâu hơn context cache đang tham chiếu tới nó.

`@DirtiesContext` làm giảm khả năng tái sử dụng context và có thể khiến suite chậm. Chỉ dùng khi test thực sự làm bẩn ApplicationContext hoặc cần đóng context để kích hoạt lifecycle cleanup.

## 17. Dọn dẹp khi setup thất bại giữa chừng

Setup nhiều bước có thể thất bại ở bước 4 sau khi đã tạo registry, đăng ký service và mở client. Nếu chỉ đặt cleanup ở cuối test body, code có thể không chạy đến đó.

Đăng ký cleanup ngay sau khi tạo resource:

```java
List<AutoCloseable> resources = new ArrayList<>();

try {
    TestingServer server = new TestingServer();
    resources.add(server);

    CuratorFramework client = createClient(server.getConnectString());
    client.start();
    resources.add(client);

    ServiceCache cache = createServiceCache(client);
    cache.start();
    resources.add(cache);

    // Thực hiện assertion.
} finally {
    for (int i = resources.size() - 1; i >= 0; i--) {
        try {
            resources.get(i).close();
        } catch (Exception cleanupError) {
            // Ghi nhận cleanup failure; không bỏ qua âm thầm.
        }
    }
}
```

Trong code thực tế, nên dùng helper/fixture có thể giữ và báo cáo các cleanup exception. Ví dụ rút gọn trên minh họa việc lưu resource ngay sau khi tạo và đóng theo thứ tự ngược. Không để `catch` rỗng trong test suite production; cần gắn cleanup error vào kết quả test hoặc log rõ ràng.

Nếu setup thất bại trước khi đăng ký cleanup, tài nguyên có thể rò rỉ. Vì vậy, factory/fixture nên tạo resource và đăng ký close action trong cùng một bước.

## 18. Dọn dẹp phải idempotent và có thể quan sát

Cleanup đôi khi chạy sau khi resource đã tự hết hạn hoặc đã bị container dừng. Một thao tác xóa không còn resource nên được xử lý an toàn theo semantics provider.

Ví dụ:

- Deregister instance đã biến mất: coi là trạng thái đã dọn nếu provider trả not found theo semantics dự kiến.
- Xóa test root không tồn tại: hoàn tất bình thường.
- Đóng client đã đóng: không làm hỏng test teardown.
- Xóa namespace đang terminating: chờ trạng thái cuối với timeout; nếu timeout, báo resource còn lại.

Ghi nhận cleanup failure cùng `runId`, `caseId`, resource type và resource ID. Không ghi secret/token. Một test pass nhưng để lại registration cũ vẫn là test có vấn đề.

## 19. Ví dụ fixture tổng hợp cho registry test

Fixture có thể gom danh tính test, registration và cleanup vào một nơi:

```java
public final class DiscoveryTestFixture implements AutoCloseable {

    private final RegistryAdmin registry;
    private final String serviceId;
    private final String instanceId;
    private boolean registered;

    public DiscoveryTestFixture(RegistryAdmin registry, String baseName) {
        this.registry = registry;
        String suffix = UUID.randomUUID().toString().replace("-", "");
        this.serviceId = baseName + "-test-" + suffix;
        this.instanceId = serviceId + "-instance-1";
    }

    public void register(ServiceInstanceData instance) {
        registry.register(serviceId, instanceId, instance);
        registered = true;
    }

    public String serviceId() {
        return serviceId;
    }

    public String instanceId() {
        return instanceId;
    }

    @Override
    public void close() {
        if (registered) {
            registry.deregister(serviceId, instanceId);
            registered = false;
        }
    }
}
```

`RegistryAdmin` và `ServiceInstanceData` là abstraction do test suite định nghĩa; chúng không phải class Spring Cloud có sẵn. Fixture chỉ xóa đúng service/instance do nó đăng ký. Khi provider có eventual consistency, test vẫn cần chờ discovery view cập nhật sau `close()`.

Có thể dùng fixture với try-with-resources:

```java
try (DiscoveryTestFixture fixture =
             new DiscoveryTestFixture(registryAdmin, "inventory")) {
    fixture.register(instanceData);
    await().untilAsserted(() ->
            assertThat(discoveryClient.getInstances(fixture.serviceId()))
                    .hasSize(1));
}
```

## 20. Quy trình test lặp lại được trong CI

Một job CI có thể thực hiện theo trình tự:

1. Tạo `runId` duy nhất từ job/build ID.
2. Khởi động registry/database/broker bằng Testcontainers hoặc hạ tầng ephemeral của job.
3. Chờ health endpoint của container sẵn sàng.
4. Inject endpoint/port vào Spring context bằng `@DynamicPropertySource`.
5. Mỗi test tạo service ID, instance ID và test data riêng.
6. Chờ registration/discovery hội tụ bằng polling có timeout.
7. Chạy assertion và thu thập log/metrics khi thất bại.
8. Deregister đúng registration, xóa dữ liệu test và đóng client/listener.
9. Đóng Spring context nếu fixture yêu cầu, rồi dừng container theo đúng thứ tự.
10. Kiểm tra resource còn sót theo run ID và báo lỗi nếu có.

Nếu test fail, CI nên lưu log registry/container trước khi dừng chúng để hỗ trợ điều tra. Có thể giữ artifact log, nhưng không giữ registration hoặc secret từ lần chạy cũ.

## 21. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Test sau thấy instance của test trước | Không deregister hoặc service ID dùng chung | ID riêng và cleanup theo ownership |
| Test pass riêng nhưng fail khi chạy song song | Namespace/znode/topic/ID bị dùng chung | Cô lập mọi external resource theo run/case |
| `Connection refused` ở test class sau | Container dừng nhưng Spring context vẫn được cache | Điều chỉnh container scope hoặc `@DirtiesContext` |
| Port already in use | Hard-code port hoặc process cũ chưa dừng | Port mapping ngẫu nhiên và cleanup process/container |
| Test chập chờn sau registration | Assertion chạy trước khi registry hội tụ | Awaitility với timeout hữu hạn |
| Znode tồn tại sau test | Persistent parent/root chưa được xóa | Dùng test root riêng và recursive delete đúng root |
| Consul catalog có service rác | Không deregister hoặc chỉ dừng test client mà agent còn state | Deregister service ID riêng và xác minh catalog |
| Kubernetes namespace còn `Terminating` | Finalizer hoặc resource chưa xóa xong | Chờ có timeout, kiểm tra finalizer và báo resource tồn dư |
| Database test đọc row cũ | Rollback không bao phủ external/async commit | Schema/fixture ID riêng và cleanup rõ ràng |
| Reactor thread còn chạy sau test | ConnectionProvider/scheduler/listener không dispose | Đóng resource do test sở hữu theo đúng thứ tự |
| Cleanup xóa dữ liệu test khác | Dùng selector hoặc parent path quá rộng | Xóa theo resource ID/root riêng của test |
| Test CI phụ thuộc lần chạy trước | Reusable container hoặc volume giữ state | Dùng container ephemeral và reset dữ liệu |

## 22. Checklist trước khi hoàn tất test

- [ ] Mọi container, server, client, listener và executor đều có owner.
- [ ] Tài nguyên được tạo trong phạm vi method/class/suite phù hợp.
- [ ] Container sống đủ lâu cho Spring ApplicationContext đang tham chiếu.
- [ ] Mỗi test/run có service ID và instance ID riêng.
- [ ] Registry registration được deregister đúng instance do test tạo.
- [ ] ZooKeeper persistent test root hoặc Kubernetes namespace được dọn.
- [ ] Database, broker và filesystem test data được cô lập.
- [ ] Cleanup chạy cả khi assertion hoặc setup thất bại.
- [ ] Resource được đóng theo thứ tự ngược dependency.
- [ ] Cleanup idempotent và báo lỗi khi resource còn sót.
- [ ] Awaitility dùng timeout hữu hạn cho trạng thái bất đồng bộ.
- [ ] Parallel tests không dùng chung mutable state hoặc resource name.
- [ ] `@DirtiesContext` chỉ dùng khi cần đóng/reset ApplicationContext.
- [ ] CI dùng registry/container ephemeral hoặc có chiến lược reset được kiểm chứng.
- [ ] Log lỗi giữ `runId`/`caseId` nhưng không chứa token hoặc secret.

Kiểm thử service discovery chỉ đáng tin cậy khi mỗi lần chạy có thể bắt đầu từ trạng thái đã biết và kết thúc bằng việc giải phóng mọi tài nguyên do nó tạo. Hãy cô lập service ID, instance ID và external test data; quản lý vòng đời container, Spring context, client và listener theo dependency; chờ registry hội tụ bằng polling có timeout; cuối cùng xác minh cleanup đã hoàn tất. Những quy tắc này giúp test chạy lặp lại, hỗ trợ chạy song song và không để dữ liệu của lần chạy trước làm sai kết quả lần chạy sau.
