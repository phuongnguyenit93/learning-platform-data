# Dữ liệu có tên hoặc khóa riêng cho từng bộ kiểm thử

## Vì sao mỗi bộ kiểm thử cần một namespace riêng?

Kiểm thử tích hợp Spring thường dùng các dịch vụ có trạng thái: database, Redis, message broker, object storage hoặc một HTTP service dùng chung. Nhiều test có thể chạy cùng lúc trên cùng một container hoặc cùng một môi trường CI. Nếu tất cả cùng ghi vào các tên bảng, key, queue hoặc bucket giống nhau, dữ liệu của test này có thể ảnh hưởng tới test khác.

Một cách cô lập hiệu quả là cấp cho mỗi bộ kiểm thử một **namespace riêng**. Namespace là tiền tố hoặc phạm vi định danh giúp nhận biết dữ liệu thuộc về suite nào. Từ namespace đó, test tạo các tên hoặc khóa riêng cho tài nguyên mà nó sử dụng.

Ví dụ:

~~~text
suite namespace: it_a81f2c9d

database schema: it_a81f2c9d
redis key:       it_a81f2c9d:orders:42
queue:           it_a81f2c9d-order-events
object key:      it_a81f2c9d/reports/42.json
tenant id:       it_a81f2c9d
~~~

Khi một suite khác chạy song song, nó có namespace khác nên có thể tạo dữ liệu cùng loại mà không ghi đè lên dữ liệu của suite đầu tiên.

Namespace không thay thế assertion hoặc cleanup. Nó tạo ranh giới sở hữu dữ liệu; test vẫn cần kiểm tra kết quả của mình và dọn những tài nguyên đã tạo. Cũng cần phân biệt tên container với namespace dữ liệu: một container database có thể được nhiều suite dùng chung, nhưng mỗi suite vẫn nên có schema, tenant hoặc key prefix riêng.

## Phân biệt namespace của suite và khóa của từng test

Có hai cấp định danh thường hữu ích:

- **Suite namespace** tồn tại trong toàn bộ vòng đời của một bộ kiểm thử. Nó dùng cho schema, queue, topic, tenant hoặc prefix chung.
- **Test key** phân biệt dữ liệu do từng test method tạo ra bên trong namespace của suite. Nó dùng cho từng order, user, message hoặc object.

Ví dụ:

~~~text
it_a81f2c9d:orders:test_creates_order
it_a81f2c9d:orders:test_cancels_order
it_a81f2c9d:users:test_registers_user
~~~

Nếu các test trong cùng suite chạy tuần tự và dữ liệu được reset đúng cách, chỉ cần suite namespace có thể đã đủ. Nếu test method chạy song song, hoặc nhiều test trong suite có thể truy cập cùng một resource, hãy thêm test key riêng để tránh xung đột nội bộ.

Không nên tạo một UUID mới mỗi lần getter được gọi. Tất cả thành phần trong cùng suite phải dùng cùng một namespace trong suốt vòng đời suite. Hãy tạo giá trị một lần ở fixture hoặc cấu hình test rồi truyền nó tới các thành phần cần sử dụng.

## Chọn định danh ổn định và duy nhất

Một namespace cần đáp ứng ba đặc tính:

1. **Không trùng giữa các suite đang chạy đồng thời.** Có thể dùng UUID, mã build kết hợp mã job hoặc một run id ngẫu nhiên.
2. **Ổn định trong một suite.** Tạo một lần rồi chia sẻ qua test context và các fixture liên quan.
3. **Phù hợp quy tắc đặt tên của dịch vụ.** Một số backend giới hạn độ dài, ký tự hợp lệ hoặc phân biệt chữ hoa/chữ thường.

Ví dụ tạo một token ngắn từ UUID:

~~~java
import java.util.UUID;

final class TestNamespace {

    private TestNamespace() {
    }

    static String newSuiteId() {
        return "it_" + UUID.randomUUID()
                .toString()
                .replace("-", "")
                .substring(0, 12);
    }
}
~~~

Một suite có thể lưu giá trị này trong field static final:

~~~java
static final String SUITE_ID = TestNamespace.newSuiteId();
~~~

Nếu hệ thống CI đã cấp một build id hoặc job id duy nhất, có thể dùng nó thay UUID hoặc kết hợp với UUID. Build id giúp truy vết resource trong log; UUID giúp tránh va chạm khi một build chạy nhiều job hoặc retry cùng lúc.

Không đưa email, tên người dùng, token truy cập hoặc dữ liệu nhạy cảm vào tên resource. Namespace thường xuất hiện trong log, dashboard hoặc tên queue; chỉ dùng mã định danh kỹ thuật không chứa bí mật.

### Chuẩn hóa tên theo backend

Không phải backend nào cũng chấp nhận cùng một định dạng:

| Backend | Điều cần chú ý khi tạo tên |
| --- | --- |
| PostgreSQL schema/table | Dùng quy tắc ký tự SQL hợp lệ; tránh tên quá dài và từ khóa SQL |
| Redis key | Có thể dùng dấu hai chấm để phân cấp logic; thống nhất encoding và prefix |
| RabbitMQ queue/exchange | Kiểm tra giới hạn và quy tắc tên của broker; tránh tên có ý nghĩa vận hành thật |
| Kafka topic | Dùng ký tự được hỗ trợ và giới hạn độ dài theo broker |
| S3-compatible object storage | Có thể dùng prefix trong object key; bucket name có quy tắc riêng |
| Filesystem | Tránh dấu phân cách, ký tự cấm và đường dẫn thoát khỏi thư mục test |

Với tên có giới hạn độ dài, hãy rút gọn token nhưng vẫn giữ đủ entropy hoặc thêm hash. Không cắt tùy tiện một UUID tới mức các job có khả năng tạo tên trùng nhau.

## Truyền namespace vào Spring ApplicationContext

Trong Spring integration test, một nơi phù hợp để công bố namespace là property của test. Các bean có thể nhận property qua constructor hoặc configuration properties và dùng nó để tạo resource name.

Ví dụ dùng DynamicPropertySource:

~~~java
import java.util.UUID;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class OrderIntegrationTest {

    static final String SUITE_ID = "it_" + UUID.randomUUID()
            .toString()
            .replace("-", "")
            .substring(0, 12);

    @DynamicPropertySource
    static void registerTestNamespace(DynamicPropertyRegistry registry) {
        registry.add("app.test.namespace", () -> SUITE_ID);
    }
}
~~~

Giá trị được đăng ký dưới dạng supplier và Spring có thể đọc nó khi tạo Environment. Các bean cấu hình có thể bind property này:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.test")
public record TestNamespaceProperties(String namespace) {
}
~~~

Một factory dùng namespace để tạo key:

~~~java
class TestResourceNames {

    private final TestNamespaceProperties properties;

    TestResourceNames(TestNamespaceProperties properties) {
        this.properties = properties;
    }

    String redisOrderKey(long orderId) {
        return properties.namespace() + ":orders:" + orderId;
    }

    String queueName(String purpose) {
        return properties.namespace() + "-" + purpose;
    }
}
~~~

Trong ứng dụng thật, hãy đăng ký TestNamespaceProperties bằng EnableConfigurationProperties hoặc cơ chế configuration properties scanning đang dùng. Ví dụ chỉ minh họa việc truyền một giá trị từ test vào bean; nó không yêu cầu production luôn bật namespace test.

### Lưu ý về Spring TestContext cache

Spring TestContext Framework có thể cache ApplicationContext và tái sử dụng context giữa các test class có cùng cấu hình. Vì vậy, namespace được bind vào singleton bean cần ổn định trong toàn bộ vòng đời của context đó.

Không nên thay đổi một static namespace sau khi context đã được tạo rồi mong các singleton bean tự nhận giá trị mới. Bean có thể đã giữ giá trị cũ. Nếu hai suite cần namespace khác nhau, hãy tạo context có cấu hình khác nhau hoặc thiết kế namespace ở cấp request/test thay vì thay đổi property của một singleton đã cache.

DynamicPropertySource phù hợp khi một nhóm test chia sẻ một cấu hình và một namespace ổn định. Nếu dùng cùng một context cho nhiều class nhưng mỗi class muốn namespace riêng, cần chủ động thiết kế ranh giới context hoặc truyền test key vào từng thao tác. Đừng để context cache vô tình làm hai suite dùng chung namespace mà không biết.

## Database: schema, tenant hoặc khóa dữ liệu riêng

Database thường có nhiều cách cô lập:

- Database riêng cho mỗi suite.
- Schema riêng cho mỗi suite trong cùng database.
- Tenant id hoặc suite id nằm trong mọi row.
- Primary key riêng cho dữ liệu test, kết hợp với query có điều kiện.

Chọn mức phù hợp với chi phí tạo tài nguyên và cách ứng dụng truy vấn dữ liệu. Schema riêng thường hữu ích khi muốn tái sử dụng một PostgreSQL container nhưng tránh trùng tên bảng giữa các suite. Tenant key phù hợp với ứng dụng vốn đã hỗ trợ multi-tenancy.

### Schema riêng trong PostgreSQL

Một suite có thể tạo schema theo namespace rồi cấu hình connection để truy vấn trong schema đó. Tên schema nên được kiểm soát chặt, chỉ chứa ký tự do test sinh ra và không ghép trực tiếp dữ liệu người dùng vào SQL identifier.

Ví dụ khái niệm:

~~~sql
CREATE SCHEMA it_a81f2c9d;
~~~

Sau khi schema được tạo, cấu hình datasource để dùng schema đó, hoặc đặt search_path cho connection theo cách phù hợp với driver và pool. Migration phải chạy vào schema của suite; nếu migration vẫn ghi vào schema mặc định, namespace không cô lập được bảng.

Khi kết thúc suite, có thể xóa schema đã sở hữu:

~~~sql
DROP SCHEMA it_a81f2c9d CASCADE;
~~~

Chỉ thực hiện DROP trên schema được tạo bởi chính suite hiện tại. Không xóa schema mặc định hoặc schema dùng chung của môi trường test.

### Tenant id hoặc suite id trong dữ liệu

Nếu ứng dụng có tenant column, có thể dùng namespace làm tenant id:

~~~java
String tenantId = suiteNamespace;

Order order = new Order(
        tenantId,
        "order-" + testCaseId,
        OrderStatus.NEW
);
orderRepository.save(order);
~~~

Các truy vấn cần luôn giới hạn theo tenant:

~~~java
List<Order> findByTenantIdAndStatus(
        String tenantId,
        OrderStatus status);
~~~

Chỉ thêm tenant id khi schema và logic ứng dụng thực sự hỗ trợ tenant isolation. Nếu repository vẫn truy vấn toàn cục, gắn một tenant id vào dữ liệu không tự cô lập test.

### Dùng key riêng thay vì xóa toàn bộ database

Tránh chạy lệnh xóa toàn bộ bảng hoặc truncate schema dùng chung khi nhiều suite chạy song song. Một suite có thể xóa dữ liệu mà suite khác đang kiểm tra.

Nếu không có schema hoặc tenant riêng, hãy tạo id duy nhất cho record của test và dọn đúng các record do test tạo. Có thể dùng repository method xóa theo id hoặc theo suite id; không dùng điều kiện xóa quá rộng.

## Redis: prefix riêng cho key

Redis thường được chia sẻ giữa nhiều test vì một instance nhẹ và khởi động nhanh. Dùng prefix theo suite giúp tránh va chạm:

~~~java
class RedisTestKeys {

    private final String namespace;

    RedisTestKeys(String namespace) {
        this.namespace = namespace;
    }

    String order(long id) {
        return namespace + ":orders:" + id;
    }

    String session(String sessionId) {
        return namespace + ":sessions:" + sessionId;
    }
}
~~~

Test ghi và đọc đúng key:

~~~java
String key = keys.order(42L);

redisTemplate.opsForValue().set(key, "created");

assertThat(redisTemplate.opsForValue().get(key))
        .isEqualTo("created");
~~~

Khi cleanup, chỉ xóa các key có prefix của suite. Với Redis, không dùng FLUSHALL hoặc FLUSHDB trên instance dùng chung vì chúng xóa dữ liệu của các suite khác.

Nếu cần tìm toàn bộ key của namespace, ưu tiên lệnh scan có pattern và xóa theo batch thay cho KEYS trên môi trường có nhiều dữ liệu. SCAN tránh chặn Redis lâu như một lệnh liệt kê toàn bộ key; tuy vậy, cleanup vẫn cần giới hạn prefix chính xác và xử lý việc key có thể được tạo trong lúc scan.

## Message broker: queue và topic có tên riêng

Message broker có trạng thái khó rollback bằng transaction test thông thường. Một message đã publish có thể còn trong queue sau khi test kết thúc. Nếu nhiều suite dùng chung queue, consumer của suite này có thể nhận message do suite khác gửi.

Tạo queue hoặc topic theo namespace:

~~~java
String queueName = suiteNamespace + "-order-events";
String topicName = suiteNamespace + "-payment-events";
~~~

Đưa tên resource vào cấu hình consumer và producer của suite. Cả hai phải dùng cùng namespace; nếu producer publish vào queue A còn consumer nghe queue B, test sẽ chờ đến timeout dù message đã được gửi.

Với Kafka, tên topic riêng giúp tránh consumer group và retained record của suite khác. Với RabbitMQ, queue/exchange riêng giúp giới hạn message và binding theo suite. Cần kiểm tra quy tắc đặt tên, giới hạn độ dài và quyền tạo resource của broker.

Cleanup cần xóa queue/topic hoặc purge đúng resource do suite sở hữu. Nếu broker xóa resource bất đồng bộ hoặc consumer còn đang kết nối, hãy chờ thao tác dọn hoàn tất trước khi kết thúc suite hoặc trước khi tái sử dụng tên.

Không dùng cùng một queue name cố định cho nhiều pipeline đồng thời nếu không có cơ chế phân vùng message. Chỉ một consumer có thể nhận message mà test khác đang chờ, làm kết quả không xác định.

## Object storage và filesystem

Với S3-compatible storage, bucket có quy tắc tên riêng và có thể không cho phép tạo bucket tùy ý theo từng test method. Một cách phổ biến là dùng bucket riêng cho suite hoặc dùng object key có prefix:

~~~text
bucket: integration-test-artifacts
object key:
  it_a81f2c9d/reports/42.json
  it_a81f2c9d/uploads/avatar.png
~~~

Khi cleanup, liệt kê và xóa object trong prefix của suite, sau đó xóa bucket nếu suite tự tạo bucket đó. Đảm bảo không xóa object thuộc prefix khác.

Với filesystem, tạo thư mục tạm riêng cho suite hoặc test:

~~~java
Path suiteDirectory = Files.createTempDirectory("it-a81f2c9d-");
Path report = suiteDirectory.resolve("reports/report.json");
~~~

Dùng thư mục tạm giúp tránh đụng tên file giữa các test và cho phép cleanup theo một root cụ thể. Khi test dùng JUnit Jupiter TempDir, framework quản lý vòng đời thư mục tạm theo scope được khai báo; vẫn cần kiểm tra test không lưu file ra ngoài thư mục đó.

## Cleanup theo namespace và theo đúng vòng đời

Namespace giúp xác định dữ liệu thuộc suite nào, từ đó cleanup có thể nhắm đúng phạm vi. Hãy chọn một trong các thời điểm:

- Sau mỗi test method nếu dữ liệu chỉ thuộc method đó.
- Sau mỗi test class nếu các method trong class chia sẻ fixture.
- Sau toàn bộ suite nếu namespace đại diện cho cả một nhóm test hoặc một application context.

Cleanup cần chạy cả khi assertion thất bại. JUnit Jupiter cung cấp AfterEach và AfterAll; tài nguyên có thể quản lý bằng extension hoặc AutoCloseable fixture để đóng đúng lifecycle.

Ví dụ:

~~~java
class NamespacedRedisTests {

    static final String SUITE_ID = TestNamespace.newSuiteId();
    RedisTestKeys keys = new RedisTestKeys(SUITE_ID);

    @AfterAll
    static void cleanSuiteData() {
        redisCleanup.deleteByPrefix(SUITE_ID + ":");
    }
}
~~~

Đây là minh họa về vị trí cleanup; trong test thật, dependency cleanup cần được inject hoặc truy cập qua fixture phù hợp. Không nên dùng static method nếu dependency không có lifecycle tĩnh; khi đó dùng TestInstance(PER_CLASS), extension hoặc một resource manager được đóng ở AfterAll.

Nếu cleanup là bất đồng bộ, đừng kết thúc test ngay sau khi gửi lệnh xóa. Chờ tín hiệu hoàn tất hoặc xác nhận resource đã biến mất với timeout hữu hạn. Nếu suite kế tiếp có thể tái sử dụng tên, cleanup chưa xong sẽ gây xung đột.

### Cleanup thất bại không được che lỗi test

Nếu assertion trong test đã thất bại rồi cleanup cũng ném exception, báo cáo cuối cùng có thể chỉ hiện lỗi cleanup và làm mất nguyên nhân chính. Nên ghi log lỗi cleanup và gắn nó như suppressed exception hoặc dùng lifecycle helper có cách báo lỗi rõ ràng. Không bỏ qua cleanup error một cách im lặng, vì resource còn sót có thể ảnh hưởng lần chạy sau.

## Namespace trong test chạy song song

Suite namespace chỉ cô lập các suite với nhau. Nếu nhiều test method trong cùng suite chạy đồng thời, chúng vẫn có thể đụng key nếu cùng dùng một id cố định.

Có thể tạo key ở cấp test:

~~~java
String testKey = suiteNamespace + ":"
        + testInfo.getTestMethod().orElseThrow().getName()
        + ":"
        + UUID.randomUUID();
~~~

JUnit Jupiter có thể inject TestInfo vào lifecycle method hoặc test method. Kết hợp tên method với UUID giúp log dễ đọc mà vẫn giảm khả năng trùng. Nếu muốn test chạy lại với cùng dữ liệu để debug, dùng test method name cộng một run id ổn định trong lần chạy đó.

Không nên dùng tên method một mình làm khóa duy nhất nếu test parameterized, repeated hoặc chạy đồng thời nhiều invocation. Các invocation có thể cùng method name; thêm index hoặc token cho từng invocation khi cần phân biệt.

Một lựa chọn khác là fixture riêng cho mỗi method, ví dụ tạo một key prefix mới trong BeforeEach rồi xóa trong AfterEach. Hãy bảo đảm code đang kiểm tra nhận đúng prefix đó qua dependency injection hoặc tham số; không dựa vào biến global mutable có thể bị test khác ghi đè.

## Không nhầm namespace dữ liệu với isolation của transaction

Spring test có thể chạy test method trong transaction và rollback sau khi test hoàn tất. Điều này hữu ích với dữ liệu database được ghi trong cùng transaction mà test quản lý. Tuy nhiên, rollback không tự dọn mọi loại tài nguyên:

- Message đã publish ra broker có thể đã được consumer khác nhận.
- Redis command có hiệu lực độc lập với transaction database.
- File hoặc object đã ghi ra storage vẫn tồn tại.
- Một service HTTP bên ngoài có thể đã xử lý request và lưu side effect.
- Tác vụ async có thể tiếp tục sau khi transaction test rollback.

Namespace riêng là lớp cô lập hữu ích cho các tài nguyên này. Transaction rollback và namespace giải quyết hai vấn đề khác nhau: rollback hoàn tác thay đổi trong transaction; namespace phân vùng dữ liệu và resource ở các hệ thống có lifecycle riêng.

Nếu ứng dụng dùng transactional outbox, test có thể kiểm tra row outbox trong transaction và một test khác kiểm tra publisher/consumer. Khi test end-to-end publish message thật, hãy dùng topic/queue riêng và cleanup message/resource theo namespace.

## Những lỗi thường gặp

### Dùng một tên cố định cho mọi suite

Hai pipeline cùng tạo queue hoặc key giống nhau có thể ghi đè, tiêu thụ hoặc xóa dữ liệu của nhau. Sinh namespace duy nhất cho mỗi suite hoặc build.

### Sinh namespace mới ở mỗi lần đọc

Producer, consumer và cleanup có thể nhận ba namespace khác nhau. Tạo token một lần rồi chia sẻ qua fixture và Spring properties.

### Chỉ dùng suite id khi method chạy song song

Các method trong cùng suite vẫn có thể ghi vào cùng key. Thêm test key hoặc fixture riêng cho từng invocation.

### Dùng UUID cho mọi business id mà không cần thiết

Dữ liệu test khó đọc và khó tái hiện. Giữ business id dễ hiểu trong namespace riêng, ví dụ suite:orders:42; chỉ token namespace cần duy nhất.

### Cleanup bằng lệnh xóa toàn cục

FLUSHDB, truncate schema chung hoặc purge queue chung có thể phá dữ liệu của suite khác. Xóa theo prefix, schema, tenant hoặc resource mà suite sở hữu.

### Nghĩ rollback database dọn được broker hoặc storage

Transaction database không bao trùm message broker, Redis, filesystem hoặc object storage. Các tài nguyên này cần namespace và cleanup riêng.

### Thay namespace sau khi Spring context đã cache

Singleton bean có thể tiếp tục dùng property cũ. Cố định namespace theo context lifecycle hoặc tạo context mới khi cần một namespace khác.

### Đặt tên không tuân theo quy tắc dịch vụ

Tên quá dài hoặc chứa ký tự không hợp lệ có thể khiến resource creation thất bại. Chuẩn hóa tên và kiểm tra giới hạn của backend trước khi sử dụng.

## Quy trình thiết kế dữ liệu riêng cho mỗi suite

1. Liệt kê các hệ thống có trạng thái mà suite sử dụng: database, cache, broker, storage và HTTP service.
2. Chọn phạm vi cô lập cho từng hệ thống: database/schema/tenant, key prefix, queue/topic, bucket/object prefix hoặc thư mục.
3. Sinh một suite namespace duy nhất và giữ ổn định trong vòng đời của suite.
4. Tạo test key riêng nếu method hoặc invocation trong suite có thể chạy song song.
5. Truyền namespace qua fixture hoặc Spring configuration; không đọc hoặc sinh lại token ở từng bean.
6. Tạo resource và dữ liệu theo namespace trước khi test gửi request hoặc truy vấn.
7. Assert dữ liệu trong đúng namespace, tránh truy vấn toàn cục có thể nhìn thấy dữ liệu suite khác.
8. Cleanup theo namespace ở đúng lifecycle và chờ cleanup bất đồng bộ hoàn tất.
9. Khi chạy song song, không chia sẻ một resource mutable nếu reset hoặc cleanup của test này có thể tác động tới test khác.

Dữ liệu có tên hoặc khóa riêng giúp nhiều bộ kiểm thử dùng chung hạ tầng mà vẫn có ranh giới sở hữu rõ ràng. Một suite namespace ổn định, test key khi cần, cùng cleanup theo đúng phạm vi sẽ giảm va chạm dữ liệu, giúp chạy song song an toàn hơn và làm cho lỗi trong CI dễ truy vết.
