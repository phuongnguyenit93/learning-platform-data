# Kiểm thử yêu cầu lặp, thao tác cạnh tranh và khởi động lại broker

Một service broker theo Open Service Broker API (OSB API) phải chịu được những tình huống thường gặp trong môi trường phân tán: platform gửi lại cùng một request sau timeout, hai request cùng thay đổi một service instance, worker nhận message nhiều lần hoặc broker khởi động lại giữa lúc provider đang tạo tài nguyên. Nếu chỉ kiểm thử đường đi thành công một lần, broker có thể hoạt động tốt trong môi trường phát triển nhưng tạo tài nguyên trùng, mất operation hoặc ghi sai trạng thái khi chạy production.

Ba nhóm tình huống cần kiểm thử có quan hệ chặt chẽ:

- **Yêu cầu lặp (duplicate/retry):** cùng một thao tác được gửi lại vì client không nhận được response hoặc chủ động retry.
- **Thao tác cạnh tranh (concurrency):** nhiều request hoặc worker cùng tác động lên một instance, binding hoặc operation.
- **Khởi động lại broker (restart/recovery):** process dừng ở bất kỳ thời điểm nào rồi khởi động lại, trong khi request, operation hoặc provider call chưa hoàn tất.

Mục tiêu kiểm thử là chứng minh broker giữ được tính idempotent, bảo vệ state transition, không thất lạc công việc đã chấp nhận và có thể phục hồi trạng thái từ dữ liệu bền vững. Bài học này trình bày chiến lược kiểm thử từ HTTP contract tới database, queue và provider adapter; xây dựng kịch bản lỗi có kiểm soát; đồng thời xác định các invariant cần được giữ sau retry, race condition và restart.

## 1. Vì sao cần kiểm thử các tình huống phân tán?

Một request provision có thể đi qua nhiều thành phần:

1. Platform gửi HTTP request tới broker.
2. Broker xác thực request và kiểm tra service/plan.
3. Broker ghi service instance, operation và outbox event.
4. Broker trả kết quả đồng bộ hoặc HTTP 202.
5. Relay publish job vào queue.
6. Worker gọi provider API.
7. Provider tạo tài nguyên và có thể trả provider operation ID riêng.
8. Worker cập nhật mapping và trạng thái.
9. Platform truy vấn last_operation.

Giữa bất kỳ hai bước nào, mạng có thể timeout, process có thể bị kill hoặc message có thể được giao lại. Một kết quả timeout không chứng minh provider chưa thực hiện request. Một message được giao hai lần không chứng minh queue bị lỗi. Một worker bị dừng không có nghĩa operation đã thất bại.

~~~mermaid
flowchart TD
    A[Platform gửi request] --> B[Broker nhận và xác thực]
    B --> C[Commit instance + operation + outbox]
    C --> D[Trả response]
    C --> E[Relay publish job]
    E --> F[Worker xử lý]
    F --> G[Provider API]
    G --> H[Worker lưu kết quả]
    H --> I[Platform polling last_operation]
    X[Timeout / crash / duplicate] -.-> B
    X -.-> E
    X -.-> F
    X -.-> G
~~~

Kiểm thử cần xác minh không chỉ HTTP response mà cả trạng thái bền vững và tác dụng phụ phía provider. Ví dụ platform gửi provision hai lần có thể nhận hai response 202, nhưng broker vẫn chỉ được tạo một logical operation và một provider resource.

## 2. Xác định invariant trước khi viết test

Invariant là điều kiện phải luôn đúng dù request bị retry, worker chạy đồng thời hoặc process restart.

Một số invariant quan trọng:

| Phạm vi | Invariant cần giữ |
|---|---|
| Service instance | Một OSB instance ID không được đại diện cho hai tài nguyên provider ngoài ý muốn |
| Operation | Retry cùng một request không tạo operation độc lập nếu contract yêu cầu nhận diện là cùng thao tác |
| Provider resource | Một idempotency key không tạo nhiều resource |
| Binding | Một binding ID chỉ ánh xạ tới một binding logic và đúng instance |
| State transition | Không chuyển instance từ DEPROVISIONING về ACTIVE do một worker cũ |
| Queue | Message giao lặp không lặp lại tác dụng phụ |
| Outbox | Event đã commit không bị mất khi relay hoặc broker restart |
| Worker | Một operation không bị nhiều worker thực thi đồng thời ngoài chính sách |
| Last operation | Platform đọc được trạng thái bền vững và nhất quán |
| Tenant | Request của tenant này không thay đổi tài nguyên tenant khác |

Viết invariant thành điều kiện kiểm tra cụ thể. Ví dụ sau hai request provision giống nhau:

- Chỉ có một bản ghi service instance.
- Chỉ có một operation logic đang đại diện cho request đó.
- Provider fake ghi nhận một resource được tạo.
- Hai response phù hợp với semantics idempotency của endpoint.
- last_operation trả cùng trạng thái operation.
- Không có bản ghi binding hoặc resource mapping mồ côi.

Không chỉ assert HTTP 202 hoặc 200. Những status đó không chứng minh broker đã bảo đảm idempotency.

## 3. Phân biệt các loại yêu cầu lặp

Không phải mọi request có cùng instance ID đều là duplicate hợp lệ. Cần kiểm thử ít nhất các trường hợp:

1. Cùng instance ID, cùng operation type, cùng payload và cùng idempotency identity.
2. Cùng instance ID nhưng payload khác.
3. Cùng instance ID, request đầu đang xử lý và request sau đến đồng thời.
4. Request đầu đã hoàn tất, platform gửi lại request cũ.
5. Request mới hợp lệ sau khi operation trước đã kết thúc.
6. Hai request khác tenant nhưng cố dùng cùng ID.
7. Request retry sau khi broker đã commit nhưng response bị mất.

Ví dụ provision retry với cùng service ID và plan ID có thể được nhận diện là cùng yêu cầu. Nhưng nếu request sau đổi plan hoặc parameters, broker phải áp dụng quy tắc conflict/idempotency của OSB và thiết kế nội bộ. Không được chỉ dựa vào instance ID để trả lại response cũ nếu payload mới có ý nghĩa khác.

## 4. Kiểm thử idempotency cho provision

Provision là thao tác dễ tạo duplicate resource nếu broker không xử lý retry đúng.

Một kịch bản cơ bản:

- Gửi PUT provision cho instance-123.
- Provider fake nhận lệnh tạo resource.
- Giả lập response HTTP của broker bị mất hoặc client timeout.
- Gửi lại cùng request với cùng instance ID.
- Xác minh broker trả kết quả phù hợp với operation/resource đã tồn tại.
- Xác minh provider chỉ tạo một resource.

Provider fake nên ghi số lần create và idempotency key đã nhận. Ví dụ:

~~~java
public final class FakeProvider {

    private final Map<String, String> resourcesByKey =
            new ConcurrentHashMap<>();
    private final AtomicInteger createCalls = new AtomicInteger();

    public String create(String idempotencyKey) {
        createCalls.incrementAndGet();
        return resourcesByKey.computeIfAbsent(
                idempotencyKey,
                key -> "resource-" + UUID.randomUUID());
    }

    public int createCalls() {
        return createCalls.get();
    }
}
~~~

Đây là fake đơn giản để kiểm tra contract idempotency. Nếu muốn đo số tác dụng phụ thực tế, cần phân biệt số lần adapter gọi provider với số resource được tạo. Một provider có thể nhận nhiều request retry nhưng chỉ tạo một resource nhờ idempotency key.

Test cần assert cả:

- Số logical resource bằng một.
- Mapping instance tới provider resource ổn định.
- Operation ID được giữ hoặc trả theo đúng semantics.
- Không tạo operation mới không cần thiết.
- Request fingerprint không bị thay đổi.
- Không rò rỉ credentials trong response hoặc log.

## 5. Cùng ID nhưng payload khác

Một request lặp với payload khác cần được kiểm tra riêng. Ví dụ request đầu provision plan small, request sau dùng cùng instance ID nhưng plan production.

Broker có thể lưu request fingerprint hoặc dữ liệu chuẩn hóa để phát hiện xung đột. Test nên chứng minh:

- Broker không âm thầm dùng payload mới để sửa operation cũ.
- Broker không tạo resource thứ hai.
- Broker không trả response thành công giả cho request không tương thích.
- Error response phù hợp với contract OSB và chính sách broker.
- Operation và instance ban đầu vẫn nhất quán.

Fingerprint cần được tính từ dữ liệu canonicalized, loại bỏ field không có ý nghĩa với idempotency và không đưa secret dạng rõ vào bảng fingerprint. Nếu parameters chứa secret, có thể dùng HMAC với key được quản lý riêng hoặc chỉ fingerprint các field nghiệp vụ đã được chọn.

Ví dụ test khái niệm:

~~~java
@Test
void rejectsSameInstanceWithDifferentPlan() {
    provision("instance-123", "small");

    var response = provisionHttp(
            "instance-123",
            "production");

    assertThat(response.statusCode())
            .isEqualTo(409);
    assertThat(instanceRepository.countById("instance-123"))
            .isEqualTo(1);
    assertThat(fakeProvider.createdResources())
            .hasSize(1);
}
~~~

Status trong ví dụ là lựa chọn minh họa; cần xác minh response thực tế theo OSB contract và cách framework xử lý tình huống cụ thể.

## 6. Kiểm thử idempotency cho update và deprovision

Update có thể thay đổi plan, quota hoặc cấu hình provider. Retry update sau timeout có thể gửi lại cùng một thay đổi hoặc áp dụng một thay đổi khác nếu broker không lưu operation identity.

Các trường hợp cần kiểm tra:

- Cùng update request được gửi lại.
- Hai update cùng instance nhưng target plan khác nhau.
- Update retry khi operation đầu đang chạy.
- Update retry sau khi provider đã hoàn tất nhưng broker chưa lưu kết quả.
- Update cũ được giao lại sau khi một update mới đã bắt đầu.

Deprovision cũng cần idempotency. Platform có thể retry DELETE nếu không nhận được response. Broker cần xử lý trường hợp provider resource đã bị xóa trước đó, đồng thời không xóa nhầm resource được tạo lại hoặc resource của tenant khác.

Test deprovision nên xác minh:

- Xóa một resource nhiều lần không gây tác dụng phụ sai.
- Provider NOT_FOUND được diễn giải theo trạng thái hiện tại.
- Mapping được giữ đủ lâu để đối soát khi kết quả không rõ.
- Instance không bị đánh dấu DELETED trước khi điều kiện hoàn tất được xác minh.
- Một worker cũ không thể xóa tài nguyên sau khi instance đã chuyển sang một thế hệ mới.

Có thể gắn operation generation hoặc version với mỗi thao tác để phân biệt request cũ và request mới trên cùng instance.

## 7. Kiểm thử binding và unbind lặp

Binding có ID riêng và thường tạo credentials hoặc attachment ở provider. Retry bind có thể tạo nhiều user database hoặc nhiều volume attachment nếu adapter không idempotent.

Các test quan trọng:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Cùng binding ID, cùng instance, cùng request | Trả lại binding logic đã có |
| Cùng binding ID nhưng instance khác | Từ chối xung đột |
| Hai bind cùng binding ID đồng thời | Chỉ một binding được tạo |
| Hai binding ID khác nhau trên cùng instance | Xử lý như hai consumer riêng nếu plan cho phép |
| Unbind gửi lại | Không thu hồi nhầm binding khác |
| Unbind timeout sau provider revoke | Reconcile trạng thái trước khi gọi lại |
| Deprovision khi binding còn hoạt động | Áp dụng chính sách và contract đã định nghĩa |

Không chỉ kiểm tra số bản ghi service_binding. Cần kiểm tra số credential hoặc attachment thực tế trong provider fake. Nếu provider hỗ trợ nhiều credential cho một binding, test phải chứng minh retry không phát hành thêm credential không được quản lý.

## 8. Kiểm thử đồng thời bằng barrier

Một race condition khó tái hiện nếu gửi request tuần tự. Test concurrency cần điều khiển nhiều thread hoặc request cùng bắt đầu tại một thời điểm.

Có thể dùng CountDownLatch để đồng bộ:

~~~java
@Test
void concurrentProvisionCreatesOneLogicalInstance()
        throws Exception {

    int requestCount = 10;
    var ready = new CountDownLatch(requestCount);
    var start = new CountDownLatch(1);
    var pool = Executors.newFixedThreadPool(requestCount);

    var futures = IntStream.range(0, requestCount)
            .mapToObj(index -> pool.submit(() -> {
                ready.countDown();
                start.await();
                return provision("instance-123", "small");
            }))
            .toList();

    ready.await();
    start.countDown();

    var responses = new ArrayList<Response>();
    for (var future : futures) {
        responses.add(future.get());
    }

    pool.shutdown();

    assertThat(instanceRepository.countById("instance-123"))
            .isEqualTo(1);
    assertThat(fakeProvider.createdResources())
            .hasSize(1);
}
~~~

Đây là ví dụ minh họa. Cần thêm timeout cho latch/future, cleanup executor trong finally và chọn số request phù hợp với test environment. Với test HTTP, mỗi task nên gửi request qua client tới broker thay vì gọi trực tiếp method service, để bao phủ cả web layer.

Barrier giúp tạo cạnh tranh gần như đồng thời, nhưng không bảo đảm mọi lịch thực thi đều giống nhau. Nên chạy test nhiều lần hoặc dùng fault injection để mở rộng các cửa sổ race quan trọng.

## 9. Kiểm soát cạnh tranh ở database

Kiểm tra bằng Java trước khi insert không đủ để ngăn hai request cùng tạo instance:

~~~text
Request A: SELECT instance-123 -> không tồn tại
Request B: SELECT instance-123 -> không tồn tại
Request A: INSERT instance-123
Request B: INSERT instance-123
~~~

Nếu không có unique constraint, hai bản ghi có thể được tạo. Nếu có unique constraint, một transaction sẽ thất bại; application service phải chuyển lỗi duplicate thành kết quả idempotent hoặc conflict phù hợp.

Các cơ chế thường dùng:

- Unique constraint cho service instance ID hoặc khóa nghiệp vụ.
- Unique constraint cho binding ID.
- Optimistic locking bằng version.
- Pessimistic row lock khi cần serialize thao tác.
- Conditional update theo state và version.
- Transaction boundary ngắn để giảm thời gian giữ lock.

Ví dụ constraint:

~~~sql
ALTER TABLE service_instance
    ADD CONSTRAINT uq_service_instance_id
    UNIQUE (service_instance_id);

ALTER TABLE service_binding
    ADD CONSTRAINT uq_binding_id
    UNIQUE (binding_id);
~~~

Không nên chỉ dựa vào distributed lock ở application layer mà bỏ unique constraint. Database constraint là hàng rào cuối cùng cho tính duy nhất của dữ liệu.

## 10. Kiểm thử optimistic locking và state transition

Một entity có version giúp phát hiện cập nhật đồng thời. Ví dụ:

~~~java
@Entity
public class ServiceInstanceEntity {

    @Id
    private String serviceInstanceId;

    @Version
    private long version;

    private String state;
}
~~~

Hai transaction cùng đọc version 4. Transaction A cập nhật thành version 5. Transaction B cố ghi với version 4 sẽ gặp optimistic locking conflict.

Test nên chứng minh:

1. Hai request cùng đọc một version.
2. Request A thực hiện transition hợp lệ và commit.
3. Request B ghi với version cũ bị phát hiện.
4. Broker đọc lại state mới và quyết định trả conflict, retry nội bộ hoặc nhận diện duplicate.
5. Không có transition bất hợp lệ được commit.

State machine cũng cần kiểm tra điều kiện. Ví dụ instance đang DEPROVISIONING không được chuyển về ACTIVE chỉ vì một worker provision cũ ghi kết quả muộn.

Có thể dùng conditional update:

~~~sql
UPDATE service_instance
SET state = 'ACTIVE',
    version = version + 1
WHERE service_instance_id = :instance_id
  AND state = 'PROVISIONING'
  AND version = :expected_version;
~~~

Nếu số hàng cập nhật bằng 0, worker phải đọc lại trạng thái. Không được mặc định update thất bại là lỗi database; có thể một thao tác khác đã thay đổi state.

## 11. Kiểm thử hai thao tác khác loại trên cùng instance

Không chỉ duplicate cùng operation mới gây race. Các thao tác khác loại có thể xung đột:

- Provision và deprovision cùng instance.
- Update và bind.
- Update và update với hai plan khác nhau.
- Deprovision và unbind.
- Hai worker xử lý operation theo thứ tự ngược.
- Reconcile và request mới cùng sửa mapping.

Xây dựng ma trận cạnh tranh:

| Thao tác A | Thao tác B | Điều cần xác minh |
|---|---|---|
| Provision | Provision | Một instance/resource logic |
| Provision | Deprovision | Deprovision không chạy trước khi provision có trạng thái rõ |
| Update | Update | Serialize hoặc conflict theo policy |
| Update | Bind | Binding dùng cấu hình nhất quán |
| Unbind | Unbind | Thu hồi idempotent |
| Deprovision | Unbind | Không xóa binding/resource ngoài thứ tự |
| Worker cũ | Worker mới | Fencing/version ngăn worker cũ ghi đè |

Một cách thiết kế phổ biến là chỉ cho một lifecycle operation active trên một service instance. Nếu chọn cách này, test cần chứng minh unique active-operation constraint hoặc lock hoạt động giữa nhiều broker replica, không chỉ trong một JVM.

## 12. Kiểm thử nhiều broker replica

Một lock trong memory như synchronized, ReentrantLock hoặc map concurrent chỉ bảo vệ một process. Khi broker chạy nhiều replica, mỗi replica có lock riêng.

Test multi-instance nên khởi chạy hai broker instance cùng kết nối một database và queue test. Gửi cùng request đồng thời tới cả hai instance.

Kết quả cần xác minh:

- Database constraint ngăn duplicate.
- Operation claim chỉ có một owner hợp lệ.
- Outbox relay không làm mất event.
- Worker lease/fencing xử lý process chết.
- Cả hai replica đọc cùng state bền vững.
- Không có dữ liệu phụ thuộc vào local memory của một replica.

Có thể dùng Testcontainers để chạy database và message broker thật trong test integration. Nếu test chỉ dùng H2 hoặc in-memory queue, một số khác biệt về lock, isolation, SQL dialect và delivery semantics có thể không xuất hiện.

## 13. Kiểm thử outbox và message giao lặp

Transactional outbox bảo đảm event được ghi cùng transaction nghiệp vụ, nhưng relay có thể publish event nhiều lần. Consumer cần idempotency.

Các kịch bản:

1. Database commit thành công, relay chưa chạy.
2. Relay publish thành công nhưng crash trước khi đánh dấu published.
3. Queue giao cùng event hai lần.
4. Consumer xử lý xong nhưng crash trước ack.
5. Consumer claim operation rồi crash trước provider call.
6. Consumer gọi provider thành công nhưng crash trước khi lưu kết quả.
7. Lease hết hạn và worker khác tiếp quản.

Với mỗi trường hợp, test cần xác minh event không bị mất và tác dụng phụ không bị lặp.

Một bảng inbox có unique key theo consumer và event ID có thể giúp deduplicate:

~~~sql
CREATE TABLE inbox_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(255) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Test cần gửi lại cùng event ID và xác minh consumer không thực hiện nghiệp vụ lần thứ hai sau khi transaction đầu đã commit. Nếu message được giao lại khi transaction đầu rollback, consumer phải có thể thử xử lý lại.

## 14. Kiểm thử provider idempotency và kết quả UNKNOWN

Một trong những tình huống khó nhất:

1. Worker gửi POST create tới provider.
2. Provider tạo tài nguyên thành công.
3. Response bị mất hoặc worker timeout.
4. Broker không biết resource đã được tạo hay chưa.

Test provider adapter nên có fake hỗ trợ các chế độ:

- Tạo resource rồi trả response bình thường.
- Tạo resource rồi đóng kết nối trước response.
- Nhận cùng idempotency key nhiều lần.
- Trả operation ID rồi hoàn tất muộn.
- Trả conflict khi resource đã tồn tại.
- Trả timeout trước khi nhận request.
- Trả timeout sau khi đã nhận và xử lý request.

Broker cần giữ trạng thái UNKNOWN hoặc NEEDS_RECONCILIATION khi chưa xác định kết quả. Worker tiếp theo phải tra cứu theo idempotency key, resource tag hoặc provider operation ID trước khi gửi lệnh create mới.

Không nên kiểm thử bằng cách giả định mọi timeout đều có nghĩa provider chưa làm gì. Đó là một trong những giả định gây duplicate resource trong hệ thống phân tán.

## 15. Kiểm thử khởi động lại sau từng checkpoint

Broker có thể dừng ở nhiều thời điểm. Một kế hoạch fault injection nên xác định điểm dừng và trạng thái mong đợi sau restart.

| Điểm dừng | Dữ liệu có thể đã commit? | Hành vi khi restart |
|---|---|---|
| Trước transaction accept | Chưa | Platform retry request |
| Sau commit instance/operation/outbox | Có | Relay tiếp tục publish |
| Sau publish, trước mark outbox | Có | Event có thể publish lại; consumer deduplicate |
| Sau worker claim | Có | Lease hết hạn hoặc recovery tiếp quản |
| Trước provider call | Có | Worker tiếp tục xử lý |
| Provider đã tạo resource, chưa lưu mapping | Provider có tác dụng phụ | Lookup/idempotency trước khi create lại |
| Đã lưu provider operation ID | Có | Worker tiếp tục polling |
| Đã lưu state SUCCEEDED, chưa ack queue | Có | Redelivery bị bỏ qua an toàn |
| Trong lúc trả HTTP response | Có thể đã commit | Retry request phải nhận diện operation cũ |

Không chỉ restart broker khi idle. Cần kill process có chủ đích tại các checkpoint đã chọn và xác minh state sau khi khởi động lại.

## 16. Thiết kế test hook để fault injection

Không nên thêm endpoint debug công khai để kill worker hoặc tạo lỗi provider. Trong test, có thể dùng hook nội bộ, fake clock, latch hoặc test-only provider.

Ví dụ một checkpoint interface:

~~~java
public interface FailurePoint {
    void reach(String checkpoint);
}
~~~

Trong production implementation, method có thể không làm gì. Trong test, fake có thể chặn hoặc ném exception tại một checkpoint cụ thể:

~~~java
public final class TestFailurePoint implements FailurePoint {

    private final String target;
    private final CountDownLatch reached = new CountDownLatch(1);
    private final CountDownLatch release = new CountDownLatch(1);

    public TestFailurePoint(String target) {
        this.target = target;
    }

    @Override
    public void reach(String checkpoint) {
        if (!target.equals(checkpoint)) {
            return;
        }
        reached.countDown();
        try {
            release.await();
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(error);
        }
    }

    public void awaitReached() throws InterruptedException {
        reached.await();
    }

    public void resume() {
        release.countDown();
    }
}
~~~

Trong test, gọi awaitReached, dừng process hoặc mô phỏng lỗi, sau đó restart và kiểm tra. Hook chỉ được bật trong test profile, không được expose qua HTTP hoặc cấu hình production.

Một cách khác là dùng fake provider có thể trả lỗi theo kịch bản và controllable queue để kiểm soát thời điểm giao/ack.

## 17. Kiểm thử phục hồi operation và last_operation

Sau restart, platform có thể tiếp tục polling endpoint last_operation. Broker cần trả trạng thái từ kho dữ liệu bền vững, không dựa vào Mono hoặc future còn nằm trong memory trước khi process dừng.

Test nên xác minh:

- Operation ID cũ vẫn tra cứu được.
- State ACCEPTED/QUEUED/RUNNING được phục hồi theo policy.
- Worker lease hết hạn được phát hiện.
- Operation không bị đánh dấu FAILED chỉ vì process restart.
- Provider operation ID vẫn được giữ.
- Worker có thể tiếp tục polling provider.
- State cuối cùng SUCCEEDED hoặc FAILED được lưu và trả ổn định.
- Request last_operation lặp không tạo thêm provider call.

Nếu operation bị treo ở RUNNING sau restart, recovery job cần kiểm tra lease và provider state trước khi tiếp quản. Không tự động đặt mọi operation RUNNING về QUEUED rồi chạy lại từ đầu; điều đó có thể tạo duplicate side effect.

## 18. Kiểm thử broker restart và worker restart riêng biệt

Broker HTTP process và worker có thể chạy chung một process hoặc tách thành deployment riêng. Test cần bao phủ đúng kiến trúc triển khai.

Nếu chung process:

- Dừng toàn bộ process khi operation đang chạy.
- Xác minh HTTP server, relay và worker đều được khởi động lại.
- Xác minh các job chưa hoàn tất được phục hồi.

Nếu tách riêng:

- Restart API broker trong khi worker vẫn chạy.
- Restart worker trong khi API broker vẫn nhận request.
- Restart relay trong khi queue còn message.
- Restart queue hoặc database trong môi trường test theo khả năng.
- Xác minh các thành phần phối hợp qua trạng thái bền vững.

Không nên coi việc restart API process đồng nghĩa worker đã restart nếu chúng là hai deployment khác nhau. Kiểm thử cần mô phỏng đúng failure domain.

## 19. Kiểm thử HTTP contract bằng WebTestClient

Các test service unit không đủ để chứng minh OSB endpoint trả response đúng. Dùng WebTestClient hoặc HTTP client phù hợp để gửi request qua server thật trong test context.

Ví dụ cấu trúc:

~~~java
webTestClient.put()
        .uri("/v2/service_instances/{id}?accepts_incomplete=true",
                "instance-123")
        .header("X-Broker-API-Version", supportedApiVersion)
        .headers(headers ->
                headers.setBasicAuth("broker-user", "test-password"))
        .bodyValue(provisionRequest)
        .exchange()
        .expectStatus().isAccepted()
        .expectBody()
        .jsonPath("$.operation").isNotEmpty();
~~~

Đây là ví dụ cần điều chỉnh theo route, version và cấu hình security của broker. Không hardcode giả định response body giống nhau ở mọi framework release; kiểm tra contract đúng phiên bản đang sử dụng.

Sau response, test cần đọc database và provider fake để xác minh operation được lưu và job được enqueue. Sau đó polling last_operation tới trạng thái kết thúc bằng điều kiện có timeout rõ ràng.

## 20. Kiểm thử reactive pipeline bằng StepVerifier

StepVerifier phù hợp để kiểm tra tín hiệu Mono/Flux ở tầng service hoặc adapter:

~~~java
StepVerifier.create(service.provision(command))
        .assertNext(result ->
                assertThat(result.operationId()).isNotBlank())
        .verifyComplete();
~~~

Với lỗi:

~~~java
StepVerifier.create(service.provision(command))
        .expectErrorMatches(error ->
                error instanceof BrokerFailure)
        .verify();
~~~

StepVerifier không kiểm tra transaction commit, HTTP status, queue delivery hoặc process restart. Nó chỉ xác minh publisher phát tín hiệu như mong đợi.

Với retry, có thể dùng fake clock hoặc virtual time để kiểm tra backoff mà không phải chờ thời gian thực dài. Cần bảo đảm scheduler trong code có thể được thay thế hoặc điều khiển trong test.

## 21. Kiểm thử transaction và database isolation

Các race condition thường phụ thuộc isolation level và database engine. Một test dùng in-memory database có thể không tái hiện đúng hành vi production.

Nên dùng Testcontainers với database tương ứng để kiểm tra:

- Unique constraint khi insert cùng instance ID.
- Optimistic locking conflict.
- SELECT FOR UPDATE và SKIP LOCKED nếu ứng dụng dùng.
- Transaction rollback khi outbox insert thất bại.
- Atomicity giữa instance, operation, audit và outbox.
- Lease claim của nhiều worker.
- Deadlock và retry transaction khi có tranh chấp.

Test transaction rollback:

~~~java
@Test
void rollsBackInstanceOperationAndOutboxTogether() {
    outboxRepository.failNextInsert();

    assertThatThrownBy(() ->
            acceptanceService.accept(command))
            .isInstanceOf(RuntimeException.class);

    assertThat(instanceRepository.existsById("instance-123"))
            .isFalse();
    assertThat(operationRepository.countByInstanceId("instance-123"))
            .isZero();
}
~~~

Ví dụ dùng repository fake để mô phỏng lỗi. Với integration test, nên tạo lỗi thực tại database hoặc constraint để xác minh transaction manager và rollback behavior của cấu hình production.

## 22. Kiểm thử worker lease và fencing token

Một worker có thể giữ lease rồi bị treo; lease hết hạn, worker khác tiếp quản. Nếu worker cũ quay lại, nó không được ghi đè kết quả của worker mới.

Ví dụ dữ liệu claim:

| Trường | Ý nghĩa |
|---|---|
| operation_id | Operation được xử lý |
| lease_owner | Worker đang sở hữu |
| lease_until | Thời hạn lease |
| fencing_token | Token tăng theo mỗi lần claim |
| attempt_count | Số lần nhận xử lý |

Kịch bản test:

1. Worker A claim operation với token 10.
2. A bị pause quá lease.
3. Worker B claim lại với token 11.
4. B hoàn tất và ghi state SUCCEEDED.
5. A tiếp tục và cố ghi state FAILED.
6. Database từ chối update của A vì token 10 cũ hơn token hiện tại.
7. Operation vẫn SUCCEEDED.

Chỉ dùng lease timestamp có thể chưa đủ nếu worker cũ tiếp tục chạy sau khi lease hết hạn. Fencing token hoặc version check bảo vệ state khỏi owner cũ.

## 23. Kiểm thử thứ tự và stale event

Queue có thể giao message trễ hoặc worker xử lý event không theo thứ tự mong muốn. Một event ProvisionRequested cũ có thể đến sau event DeprovisionRequested.

Test cần:

- Gắn sequence/version vào event hoặc aggregate.
- Gửi event theo thứ tự đảo ngược.
- Xác minh worker từ chối transition không hợp lệ.
- Xác minh event stale không tạo lại tài nguyên đã deprovision.
- Xác minh operation generation phân biệt thao tác cũ và mới.
- Kiểm tra dead-letter và reconciliation với event không thể áp dụng.

Không chỉ kiểm tra thứ tự queue trong một consumer đơn. Khi scale nhiều consumer, partition và retry có thể làm thứ tự quan sát khác dự kiến.

## 24. Kiểm thử với Testcontainers và provider simulator

Một test environment đáng tin cậy có thể gồm:

- Spring Boot application context.
- Database cùng engine với production.
- Message broker hoặc queue tương đương.
- Provider simulator hoặc WireMock.
- Test clock và fault injection hooks.
- WebTestClient cho OSB HTTP.
- Metrics/log capture để xác minh quan sát.

Provider simulator cần có khả năng:

- Lưu resource theo idempotency key.
- Trả operation ID và trạng thái tiến trình.
- Trả lỗi 429/5xx.
- Delay response.
- Đóng kết nối sau khi đã xử lý request.
- Trả conflict cho duplicate create.
- Cho phép query resource theo tag hoặc operation ID.

Không cần mô phỏng toàn bộ provider SDK trong mọi test. Unit test có thể dùng fake nhanh; integration test cần kiểm tra adapter với HTTP simulator; sandbox test hoặc contract test bổ sung xác minh API provider thực tế.

## 25. Kiểm thử tính nhất quán sau restart

Sau khi restart, không chỉ xác minh process lên lại. Cần kiểm tra các quan hệ dữ liệu:

- Instance state khớp với operation gần nhất.
- Operation có provider operation ID nếu provider đã trả.
- Resource mapping trỏ đúng tài nguyên thực.
- Binding record khớp với provider credential/attachment.
- Outbox pending vẫn được relay.
- Inbox ngăn message đã xử lý bị chạy lại.
- Lease cũ hết hạn được thu hồi.
- Audit history không mất các transition đã commit.
- last_operation trả cùng kết quả qua mọi broker replica.

Có thể tạo một consistency assertion dùng lại:

~~~java
assertThat(instance.state()).isEqualTo("ACTIVE");
assertThat(operation.state()).isEqualTo("SUCCEEDED");
assertThat(instance.providerResourceId())
        .isEqualTo(provider.resourceFor(operation.id()));
assertThat(outboxRepository.pendingFor(operation.id()))
        .isEmpty();
~~~

Các field và method trong ví dụ là minh họa. Assertion cần phản ánh schema thực tế của broker. Với trạng thái UNKNOWN hoặc NEEDS_RECONCILIATION, consistency test phải xác minh tài nguyên không bị tạo thêm và operation được đánh dấu cần xử lý.

## 26. Ma trận kiểm thử đề xuất

Có thể quản lý test suite theo nhóm:

| Nhóm | Kịch bản | Mức kiểm thử |
|---|---|---|
| Duplicate | Provision cùng request hai lần | HTTP integration + DB/provider assertion |
| Duplicate | Cùng ID, payload khác | HTTP contract + state assertion |
| Duplicate | Bind/unbind lặp | Adapter integration |
| Concurrency | Nhiều provision cùng instance | Multi-thread/multi-replica |
| Concurrency | Update cạnh tranh | Database integration |
| Concurrency | Provision và deprovision chồng lấn | State machine integration |
| Queue | Message giao lặp | Consumer integration |
| Outbox | Crash sau publish trước mark | Relay integration |
| Provider | Timeout sau tác dụng phụ | Provider simulator |
| Restart | Crash sau commit trước publish | Process recovery |
| Restart | Crash sau provider success trước DB update | Recovery/reconciliation |
| Restart | Worker lease hết hạn | Worker integration |
| Restart | Broker restart khi operation RUNNING | End-to-end recovery |
| Security | Tenant khác dùng cùng instance ID | Authorization integration |
| Observability | Correlation ID qua worker | Log/trace assertion |

Không cần chạy toàn bộ ma trận trong mọi lần build. Có thể chia:

- Unit tests chạy nhanh ở mỗi thay đổi.
- Integration tests với Testcontainers trong CI.
- Fault-injection và multi-replica tests theo lịch hoặc trước release.
- Sandbox contract tests khi thay đổi provider adapter.
- Recovery drill trong môi trường staging.

## 27. Các lỗi kiểm thử thường gặp

| Hiện tượng | Vì sao test bỏ sót | Cải thiện |
|---|---|---|
| Test duplicate pass nhưng production tạo hai resource | Chỉ assert database row, không assert provider side effect | Kiểm tra cả provider fake/simulator |
| Test concurrency không tái hiện race | Gửi request tuần tự | Dùng barrier và nhiều replica |
| Restart test vẫn pass nhưng job bị mất | Restart khi broker idle | Kill process tại checkpoint cụ thể |
| H2 test pass nhưng PostgreSQL fail | Khác biệt lock/isolation/SQL | Dùng Testcontainers cùng engine |
| Worker xử lý duplicate sau restart | Inbox chỉ nằm trong memory | Persist inbox và test redelivery |
| Provider timeout bị coi là failure chắc chắn | Fake chỉ timeout trước khi xử lý | Thêm trường hợp timeout sau side effect |
| Worker cũ ghi đè state | Không test lease expiry và stale owner | Fencing token/version |
| last_operation sai sau restart | Test chỉ gọi service method | Gọi HTTP endpoint sau restart |
| Test quá phụ thuộc sleep | Dùng Thread.sleep để chờ trạng thái | Dùng latch, polling condition và fake clock |
| Test pass ngẫu nhiên | Không cleanup executor/container hoặc shared data | Isolate test, deterministic IDs và finally cleanup |

## 28. Quy trình xây dựng test suite

Một quy trình thực hiện có thể gồm:

1. Viết invariant cho instance, operation, binding và provider resource.
2. Xác định idempotency identity và request fingerprint.
3. Xác định các state transition hợp lệ và transition bị cấm.
4. Tạo fake provider có thể ghi nhận tác dụng phụ và mô phỏng timeout.
5. Viết test duplicate request qua HTTP.
6. Viết test cùng ID nhưng payload khác.
7. Viết test concurrent request với barrier.
8. Kiểm tra unique constraint, optimistic locking và lease trên database thật.
9. Kiểm thử outbox/inbox và queue redelivery.
10. Thêm failure checkpoint sau mỗi transaction/provider boundary quan trọng.
11. Restart broker/worker rồi xác minh recovery và last_operation.
12. Chạy multi-replica test cho các thao tác có shared state.
13. Kiểm tra audit, log và correlation ID không bị mất hoặc chứa secret.
14. Chia suite thành nhóm phù hợp với tốc độ CI và release gate.

Test nên có assertion về trạng thái cuối và tác dụng phụ, không chỉ assertion về response ban đầu. Dùng ID cố định theo test hoặc namespace dữ liệu riêng để tránh test chạy song song tác động lẫn nhau.

## 29. Checklist trước khi phát hành

**Idempotency**

- [ ] Retry cùng provision request không tạo service instance hoặc provider resource trùng.
- [ ] Cùng ID nhưng payload khác được xử lý theo quy tắc rõ ràng.
- [ ] Update và deprovision retry an toàn.
- [ ] Bind/unbind retry không tạo hoặc thu hồi nhầm credential.
- [ ] Provider idempotency key được giữ ổn định qua retry.
- [ ] Timeout sau side effect được xử lý bằng lookup/reconciliation.

**Concurrency**

- [ ] Nhiều request đồng thời được kiểm thử qua HTTP.
- [ ] Unique constraint bảo vệ instance ID và binding ID.
- [ ] Optimistic/pessimistic locking hoạt động trên database production-like.
- [ ] Hai operation xung đột trên cùng instance không cùng commit transition bất hợp lệ.
- [ ] Multi-replica test chứng minh lock không phụ thuộc JVM.
- [ ] Lease/fencing ngăn worker cũ ghi đè kết quả.

**Restart và recovery**

- [ ] Operation và outbox được commit bền vững trước khi trả 202.
- [ ] Relay tiếp tục publish event pending sau restart.
- [ ] Consumer xử lý message duplicate qua inbox/idempotency.
- [ ] Worker restart không tạo lại provider resource.
- [ ] Provider operation ID và resource mapping được phục hồi.
- [ ] Operation RUNNING có lease/deadline và recovery policy.
- [ ] last_operation trả trạng thái đúng sau restart.
- [ ] Audit history và correlation ID còn đầy đủ.

**Test quality**

- [ ] Có unit test, HTTP contract test và integration test.
- [ ] Có database/queue test gần với production.
- [ ] Provider simulator mô phỏng timeout trước và sau side effect.
- [ ] Fault injection bao phủ các transaction/provider boundary quan trọng.
- [ ] Test dùng latch/condition thay vì sleep tùy tiện.
- [ ] Test song song không chia sẻ dữ liệu ngoài ý muốn.
- [ ] Có log/metric assertion cho lỗi và recovery quan trọng.

Kiểm thử yêu cầu lặp, thao tác cạnh tranh và khởi động lại broker phải chứng minh rằng trạng thái bền vững và tác dụng phụ bên ngoài vẫn nhất quán khi hệ thống gặp timeout, duplicate delivery hoặc process crash. Idempotency bảo vệ retry; database constraint, version và lease bảo vệ concurrency; operation journal, outbox/inbox và reconciliation giúp phục hồi sau restart. Khi test bao phủ cả HTTP response, database, queue và provider simulator, service broker có cơ sở vững chắc để vận hành an toàn trong môi trường nhiều replica và lỗi phân tán.

