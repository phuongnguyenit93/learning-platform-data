# Tạo correlation ID ở điểm vào

## 1. Bối cảnh: nhận nhiều message, phải biết message nào thuộc cùng một công việc

Trong chương **Content-based correlation** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai Enterprise Integration Patterns bằng **Spring Integration** để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng. Bên cạnh Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, việc xác lập **correlation ID từ thời điểm message đi vào hệ thống** là điều kiện cơ bản để theo dõi và kết hợp đúng các nhánh xử lý.

Ví dụ hệ thống quản lý đơn hàng nhận ba sự kiện độc lập qua HTTP hoặc broker:

| Sự kiện | Nguồn | Nội dung liên quan |
| --- | --- | --- |
| PAYMENT_CONFIRMED | Payment service | Thanh toán đơn ORD-101 |
| INVENTORY_RESERVED | Warehouse service | Tồn kho đơn ORD-101 |
| ADDRESS_VERIFIED | Delivery service | Địa chỉ giao đơn ORD-101 |

Ba sự kiện có thể tới vào những thời điểm khác nhau, từ những producer khác nhau, thậm chí sau khi một service restart. Một **Aggregator** muốn phát quyết định READY_TO_FULFILLMENT chỉ khi **đủ ba loại kết quả của cùng một đơn và cùng một vòng xử lý**.

~~~mermaid
flowchart LR
    P["Payment event"] --> I["Trusted ingress"]
    W["Inventory event"] --> I
    D["Address event"] --> I
    I --> K["Tạo/khôi phục correlation key"]
    K --> B["Business events / channels"]
    B --> G["Aggregator theo key"]
    G --> R["Order readiness"]
    G -.->|"Lỗi / timeout"| E["Error / recovery"]
~~~

Nếu mỗi sự kiện tạo một UUID mới ở điểm vào:

~~~text
PAYMENT_CONFIRMED   -> correlationId = 6c30...a1
INVENTORY_RESERVED  -> correlationId = f29b...d2
ADDRESS_VERIFIED    -> correlationId = 49ed...c9
~~~

Aggregator nhìn thấy **ba nhóm khác nhau**, mỗi nhóm thiếu hai sự kiện. Nó không thể biết các message cùng thuộc ORD-101.

Nếu chỉ lấy orderId làm correlation ID trong hệ thống đa tenant:

~~~text
Tenant A / ORD-101 -> correlationId = ORD-101
Tenant B / ORD-101 -> correlationId = ORD-101
~~~

Aggregator có thể **trộn dữ liệu của hai khách hàng**. Đó không chỉ là lỗi xử lý nhóm mà có thể là vi phạm ranh giới dữ liệu.

**Mục tiêu bài học**

1. Hiểu correlation ID là **khóa nhóm logic**, không phải message ID, trace ID hay idempotency key.
2. Xác định ranh giới **ingress** là nơi đầu tiên có đủ thông tin đáng tin để tạo hoặc khôi phục khóa.
3. Thiết kế khóa content-based từ tenant, business identity và workflow epoch.
4. So sánh khóa **deterministic** với ID ngẫu nhiên được tạo **một lần cho cả workflow**.
5. Gắn correlation metadata vào Spring Message bằng MessageBuilder, có validation và không tin header điều khiển do client gửi.
6. Cấu hình Aggregator dùng header mặc định hoặc custom CorrelationStrategy để ghép đúng nhóm.
7. Kiểm thử khác tenant, khác epoch, retry cùng logical event, mất/giả mạo header, fan-out và nhóm thiếu thành viên.
8. Phối hợp group timeout, persistent state, idempotency, logging và error channel để vận hành an toàn.

## 2. Content-based correlation là gì?

**Correlation** trả lời câu hỏi: *message này thuộc cùng tiến trình, đơn hàng, batch hoặc giao dịch nào với những message khác?*

**Content-based correlation** xác định câu trả lời bằng thông tin **trong payload hoặc nội dung nghiệp vụ đã được kiểm tra**. Ví dụ các payment event, inventory event và delivery event đều có một business order reference, vì thế ứng dụng có thể lấy ref đó làm thành phần của khóa nhóm.

~~~text
Input content:
  orderRef = ORD-101
  workflowEpoch = 7

Authenticated tenant:
  tenantId = tenant-A

Derived correlation key:
  order-readiness:v1:tenant-A:ORD-101:7
~~~

Với cùng tenant, orderRef và epoch, các sự kiện khác loại sẽ nhận cùng **group key**. Với tenant khác hoặc epoch khác, chúng phải nhận khóa khác.

### 2.1. Correlation ID khác Message ID, trace ID và event ID

| Định danh | Đại diện cho | Có giống nhau giữa ba message cùng workflow? |
| --- | --- | --- |
| **Spring MessageHeaders.ID** | Một Spring Message object cụ thể | Không bảo đảm |
| **eventId** | Một logical event, dùng dedup/redelivery | Không: mỗi loại event thường có eventId khác |
| **correlationId** | Một nhóm message liên quan | **Có**, với cùng workflow/epoch |
| **traceId** | Một trace quan sát/diagnostic | Không nhất thiết, đặc biệt qua broker lâu dài |
| **requestId** | Một HTTP/API request hoặc một lệnh nghiệp vụ | Tùy hợp đồng; không mặc định đồng nghĩa group ID |
| **orderId / batchId** | Thực thể hoặc nhóm nghiệp vụ | Có thể lặp qua nhiều vòng xử lý |
| **workflowEpoch** | Một lần chạy/version của workflow trên cùng thực thể | Phân biệt workflow mới với redelivery cũ |

Ví dụ:

~~~text
logical group = tenant-A / ORD-101 / epoch-7

event-001: PAYMENT_CONFIRMED      correlationId = group-7
event-002: INVENTORY_RESERVED     correlationId = group-7
event-003: ADDRESS_VERIFIED       correlationId = group-7

event-002 delivered again:
  eventId remains event-002
  correlationId remains group-7
  MessageHeaders.ID may change
~~~

**Một nhóm chứa nhiều event IDs.** Không dùng eventId làm correlationId nếu muốn nhiều event khác nhau được gom chung. Ngược lại, không dùng correlationId để suy ra mỗi event chỉ xuất hiện một lần.

### 2.2. Tại sao tạo ở ingress?

Ingress là ranh giới đầu tiên nơi ứng dụng có thể:

- Xác thực producer/actor và biết **tenant đáng tin**.
- Parse, kiểm tra schema và giới hạn kích thước payload.
- Xác định business object mà sự kiện thực sự thuộc về.
- Tìm workflow epoch hiện hành trong registry/state store.
- Tạo hoặc tra lại group key theo chính sách.
- Gắn header nội bộ thống nhất **trước khi message bị Router/Filter/Splitter phân nhánh**.
- Ghi lại event identity, version và quyết định correlation để đối soát.

Đây là **ranh giới trách nhiệm** chứ không bắt buộc phải là HTTP controller. Với Kafka/JMS, ingress là consumer adapter cùng lớp validation/mapping đầu tiên; với API, đó có thể là controller hoặc application service ngay sau xác thực. Mọi đường vào của cùng workflow phải dùng **cùng một hợp đồng sinh/tra cứu key**.

### 2.3. Không nhầm “tạo ID” với “tạo UUID mới cho mọi message”

Có hai tình huống khác nhau:

1. **Khởi tạo một workflow mới:** có thể sinh một opaque random group ID một lần, rồi lưu mapping bền giữa business object và group ID.
2. **Nhận message thứ hai, thứ ba hoặc redelivery của workflow đó:** phải **tra lại cùng group ID**, hoặc tính lại một deterministic key từ cùng dữ liệu đáng tin.

Nếu mỗi lần nhận message đều gọi UUID.randomUUID() mà không tra mapping, các reply/event liên quan sẽ không bao giờ được Aggregator gom đúng.

## 3. Chọn thành phần của correlation key

Một khóa nhóm tốt cần thỏa các điều kiện:

1. **Cùng workflow → cùng khóa**, kể cả đi qua các adapter và được redeliver.
2. **Khác tenant → khác khóa**, nếu dữ liệu có tính đa tenant.
3. **Khác thế hệ workflow → khác khóa**, khi cùng order được xử lý lại hợp lệ.
4. **Ổn định**: không dựa trên thread, thời điểm nhận, message ID kỹ thuật hoặc arrival order.
5. **Canonical**: tất cả producer được normalize bằng một quy tắc công bố.
6. **Không tiết lộ dữ liệu nhạy cảm** ở metric label, URL hoặc log công khai.
7. **Không thể bị khách hàng chỉ định tùy ý** để ghép vào group của người khác.

### 3.1. Bốn cách chọn key

| Cách chọn | Ưu điểm | Rủi ro |
| --- | --- | --- |
| **orderRef** | Đơn giản | Trùng giữa tenant hoặc giữa workflow epochs |
| **tenantId + orderRef** | Cô lập tenant | Có thể trộn các lần xử lý cùng order |
| **tenantId + orderRef + epoch** | Phân biệt khách hàng và lần chạy | Cần workflow epoch đáng tin và ổn định |
| **Opaque group ID có mapping bền** | Không lộ orderRef, hỗ trợ đổi identity | Cần registry và lookup/recovery |

Trong bài này, dùng **tenantId + orderRef + epoch**, với một prefix phiên bản:

~~~text
order-readiness:v1:tenant-A:ORD-101:7
~~~

Trong production, nếu tenant/orderRef có thể chứa dấu phân cách hoặc ký tự Unicode, không nối chuỗi tùy ý. Dùng **mã hóa độ dài**, type-safe composite key, hoặc encode canonical (và lưu khóa dạng hashed/opaque nếu cần). Các ví dụ Java sẽ giới hạn character set để loại ambiguity.

### 3.2. Epoch chỉ tăng khi workflow mới thực sự bắt đầu

Giả sử đơn ORD-101 hoàn tất epoch 7, sau đó vì chính sách nghiệp vụ phải thực hiện lại cả quy trình readiness:

~~~text
ORD-101 / epoch 7 -> group A đã complete
ORD-101 / epoch 8 -> group B mới được tạo
~~~

Nếu message của epoch 7 bị giao lại, nó **phải** giữ epoch 7; không được “nâng epoch theo thời gian nhận” khiến redelivery tạo group B giả. Cần lưu trạng thái trong một workflow registry và tra cứu bằng identity của **logical workflow**, không chỉ nhìn epoch mới nhất một cách thiếu kiểm tra.

### 3.3. Business ID có thể sai hoặc bị giả mạo

Một HTTP client có thể gửi:

~~~json
{
  "eventId": "evt-91",
  "orderRef": "ORD-101",
  "workflowEpoch": 7,
  "correlationId": "tenant-admin:ORD-999:1"
}
~~~

Không dùng trường correlationId từ payload hay HTTP header này để định tuyến nội bộ nếu chưa xác minh quyền và mapping. Hãy lấy **tenant từ authenticated principal**; đối chiếu orderRef và epoch với quyền/registry; sau đó **tạo mới nội bộ** correlation header, ghi đè hoặc loại bỏ giá trị mà producer muốn nhét vào.

Đặc biệt, việc có đúng cú pháp correlation ID **không chứng minh** producer được truy cập group. Authentication, authorization và tenancy validation vẫn là yêu cầu độc lập.

## 4. Chính sách canonicalization

Trước khi tạo key, phải định nghĩa chính xác các phép biến đổi:

- Có bỏ khoảng trắng ở hai đầu hay không?
- Mã đơn hàng có phân biệt hoa/thường không?
- Có chấp nhận Unicode normalization hay chỉ ASCII?
- Mã tenant đến từ principal hay từ input?
- “000123” và “123” có phải cùng một orderRef không?
- Epoch do producer ký hay do hệ thống registry quyết định?

**Không tự biến những business IDs khác nhau thành cùng ID** bằng normalize quá mạnh. Ví dụ, nếu hệ thống cho phép orderRef "ab" và "AB" là hai đơn khác nhau, gọi toUpperCase() là lỗi collision.

Với hợp đồng minh họa trong bài:

~~~text
tenantId: lower-case ASCII [a-z0-9_-]+, lấy từ verified context
orderRef: upper-case ASCII [A-Z0-9_-]+, chuyển từ input theo contract
epoch: integer dương, được xác nhận bởi workflow registry
kind: một trong ba loại event đã cho phép
~~~

**Dùng Locale.ROOT** khi chuyển case để hành vi không phụ thuộc locale của JVM. Nếu sản phẩm không cho phép normalize case, hãy giữ case gốc và validate exact spelling.

### 4.1. Khi nào cần HMAC hoặc opaque ID?

Nếu correlation key chứa thông tin định danh nội bộ hoặc tenant nhạy cảm, cân nhắc:

- Sinh **UUID/ULID cho group** một lần và lưu mapping bền.
- Hoặc tính **HMAC-SHA-256** trên canonical composite identity với key quản lý bởi KMS, định nghĩa version/key rotation rõ.

Hash/HMAC **không thay thế xác thực quyền**. HMAC có thể giảm lộ business IDs trong một hệ thống, nhưng nếu ứng dụng vẫn log raw payload hoặc expose tenant bằng API khác, dữ liệu vẫn có thể bị lộ. Đừng đưa secret dùng để tính HMAC vào code, log hay config public.

## 5. Java 17: mô hình đầu vào và danh tính đã xác thực

Ví dụ tập trung vào ba loại kết quả của cùng một order. Mỗi producer phát một message độc lập; không dùng Splitter để tự tạo các part.

### 5.1. Payload chưa được coi là đáng tin

~~~java
enum PartKind {
    PAYMENT,
    INVENTORY,
    ADDRESS
}

record OrderPartEvent(
        String eventId,
        String orderRef,
        int claimedEpoch,
        PartKind kind,
        boolean approved) {

    OrderPartEvent {
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException("INVALID_EVENT_ID");
        }
        if (orderRef == null || orderRef.isBlank()
                || orderRef.length() > 64) {
            throw new IllegalArgumentException("INVALID_ORDER_REF");
        }
        if (claimedEpoch < 1 || kind == null) {
            throw new IllegalArgumentException("INVALID_WORKFLOW_PART");
        }
    }
}
~~~

Trường **claimedEpoch** là tuyên bố từ nguồn, chưa phải workflow epoch đã được xác thực. Trường **approved** ở đây chỉ dùng minh họa cho một kết quả domain; producer ngoài hệ thống phải được xác thực về quyền phát loại event tương ứng. Đừng chấp nhận client bất kỳ gửi approved=true rồi cho Aggregator ra quyết định.

### 5.2. Verified actor và workflow binding

~~~java
record VerifiedActor(
        String principalId,
        String tenantId) {
    VerifiedActor {
        if (principalId == null || principalId.isBlank()
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("INVALID_VERIFIED_ACTOR");
        }
    }
}

record VerifiedWorkflowBinding(
        String tenantId,
        String orderRef,
        int epoch) {
}

interface WorkflowBindingResolver {
    VerifiedWorkflowBinding resolve(
            VerifiedActor actor,
            OrderPartEvent event);
}
~~~

**WorkflowBindingResolver** là một cổng nghiệp vụ. Implementation thật cần:

1. Xác minh actor/producer được quyền báo cáo **loại PartKind**.
2. Tra order từ kho dữ liệu của **tenant đáng tin**, không chấp nhận tenantId từ payload làm sự thật.
3. Đối chiếu orderRef với identity lưu bền.
4. Đối chiếu claimedEpoch với một workflow instance đã tồn tại, kể cả trường hợp redelivery của epoch cũ.
5. Trả **VerifiedWorkflowBinding** đúng theo bản ghi nghiệp vụ hoặc từ chối.
6. Không tự tăng epoch theo thời gian nhận.

Trong mô hình có nhiều worker/instance, resolver phải dùng dữ liệu trạng thái nhất quán. Không tự phát sinh một workflow epoch mới chỉ vì một instance chưa thấy mapping trong cache.

## 6. Hàm tạo content-based correlation key

Tách logic tạo khóa thành một hàm thuần giúp kiểm thử trước khi khởi động Spring Integration.

~~~java
import java.util.Locale;

final class OrderCorrelationKeys {
    private static final String PREFIX = "ordready:v1:";

    private OrderCorrelationKeys() {
    }

    static String from(VerifiedWorkflowBinding binding) {
        if (binding == null) {
            throw new IllegalArgumentException("MISSING_BINDING");
        }

        String tenant = binding.tenantId();
        if (tenant == null
                || !tenant.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }

        String order = binding.orderRef();
        if (order == null) {
            throw new IllegalArgumentException("MISSING_ORDER_REF");
        }

        String canonicalOrder = order
                .trim()
                .toUpperCase(Locale.ROOT);
        if (!canonicalOrder.matches("[A-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_ORDER_REF");
        }

        if (binding.epoch() < 1) {
            throw new IllegalArgumentException("INVALID_EPOCH");
        }

        return PREFIX
                + tenant + ":"
                + canonicalOrder + ":"
                + binding.epoch();
    }
}
~~~

Hàm trên dùng delimiter ":" an toàn **chỉ vì** từng thành phần đã được giới hạn regex không chứa dấu ":". Nếu mở rộng cho Unicode hoặc dấu phân cách tự do, phải thay chiến lược encoding; nếu không, hai bộ thành phần khác nhau có thể tạo cùng chuỗi khóa.

### 6.1. Ví dụ cùng/khác key

~~~text
from(tenant-a, ORD-101, epoch 7)
  -> ordready:v1:tenant-a:ORD-101:7

from(tenant-a, " ord-101 ", epoch 7)
  -> ordready:v1:tenant-a:ORD-101:7

from(tenant-b, ORD-101, epoch 7)
  -> ordready:v1:tenant-b:ORD-101:7

from(tenant-a, ORD-101, epoch 8)
  -> ordready:v1:tenant-a:ORD-101:8
~~~

Hai chuỗi đầu trùng theo **quy tắc case-insensitive** đã công bố. Hai chuỗi sau khác key, vì khác tenant hoặc epoch.

### 6.2. Version prefix để làm gì?

Nếu quy tắc correlation thay đổi từ v1 sang v2, không được lặng lẽ dùng cùng prefix rồi đổi cách tính:

~~~text
ordready:v1:tenant-a:ORD-101:7
ordready:v2:<opaque-hmac>
~~~

Cần một kế hoạch migration:

- Cấu hình producer/ingress cùng hiểu version của key.
- Giữ khả năng tìm các group v1 còn chờ.
- Mapping v1 → v2 hoặc cách drain trước khi chuyển.
- Không trộn hai dạng key của cùng một workflow trong một Aggregator.
- Khi rotating HMAC key, lưu version của secret và thời hạn tương thích.

Thay thuật toán nhưng không version có thể khiến những event còn lại của một group bị chia sang key khác.

## 7. Ingress làm giàu message và chủ động bỏ header giả mạo

Ở đây ingress nhận **OrderPartEvent** cùng **VerifiedActor** từ lớp xác thực. Nó gọi WorkflowBindingResolver để có binding tin cậy, tính một key, rồi dựng **Spring Message mới**.

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

final class OrderEventIngress {
    static final String GROUP_KEY = "businessCorrelationKey";
    static final String TRUSTED_TENANT = "trustedTenantId";
    static final String BUSINESS_EVENT_ID = "businessEventId";
    static final String WORKFLOW_EPOCH = "workflowEpoch";

    private final WorkflowBindingResolver bindings;
    private final MessageChannel correlatedInput;

    OrderEventIngress(
            WorkflowBindingResolver bindings,
            MessageChannel correlatedInput) {
        this.bindings = bindings;
        this.correlatedInput = correlatedInput;
    }

    void accept(OrderPartEvent event, VerifiedActor actor) {
        VerifiedWorkflowBinding binding =
                bindings.resolve(actor, event);
        String groupKey = OrderCorrelationKeys.from(binding);

        Message<OrderPartEvent> internal =
                MessageBuilder.withPayload(event)
                        .setHeader(GROUP_KEY, groupKey)
                        .setHeader(TRUSTED_TENANT, binding.tenantId())
                        .setHeader(WORKFLOW_EPOCH, binding.epoch())
                        .setHeader(
                                BUSINESS_EVENT_ID,
                                event.eventId())
                        .setHeader(
                                IntegrationMessageHeaderAccessor
                                        .CORRELATION_ID,
                                groupKey)
                        .build();

        if (!correlatedInput.send(internal)) {
            throw new IllegalStateException(
                    "CORRELATED_EVENT_DISPATCH_REJECTED");
        }
    }
}
~~~

Hàm này **không copyHeaders() từ một incoming Message chưa tin cậy**, không đọc client-supplied errorChannel/replyChannel/routingSlip và không lấy tenant từ một HTTP header tự do. Code chỉ gắn các metadata nội bộ cần thiết.

**Trong production** có thể bổ sung trace context đã xác minh, schemaVersion, receivedAt do server cấp và outbox/transaction boundary theo nhu cầu. Mỗi header được thêm cần có quy định nguồn, chủ sở hữu và nơi được phép sử dụng.

### 7.1. Vì sao gắn cả CORRELATION_ID và businessCorrelationKey?

Hai trường này có liên quan nhưng không nhất thiết phải giữ cùng giá trị tại mọi điểm:

- **IntegrationMessageHeaderAccessor.CORRELATION_ID**: header kỹ thuật mặc định được Aggregator/Resequencer sử dụng.
- **businessCorrelationKey**: khóa nghiệp vụ ổn định được tạo tại ingress, dùng xuyên topology, log, replay và custom correlation.

Ban đầu cả hai có thể có cùng giá trị. Tuy nhiên, **Splitter** hoặc một thành phần có cơ chế apply-sequence có thể **thiết lập lại correlation/sequence headers kỹ thuật** cho nhóm con. Khi đó businessCorrelationKey vẫn giúp liên kết với **workflow cha** và cho phép custom CorrelationStrategy ở Aggregator nghiệp vụ.

Đừng cố ép mọi nested Splitter/Scatter-Gather dùng đúng một CORRELATION_ID toàn cục. Có thể cần **correlation ID riêng cho group con** và một **parent business key** bền để nối chúng về cùng workflow.

### 7.2. Một Message ID mới ở mỗi lần build là bình thường

MessageBuilder có thể tạo Spring Message với MessageHeaders.ID mới. Đó là đặc điểm của identity kỹ thuật, **không phải lỗi correlation**, miễn là:

- EventId nghiệp vụ không đổi khi redelivery.
- Workflow binding ổn định.
- Group key tạo ra vẫn giống.
- Dedup và downstream side effect xử lý replay đúng chính sách.

### 7.3. Ingress send() không bảo đảm nghiệp vụ đã commit

Với **DirectChannel**, send() thường chạy handler trên cùng thread; exception có thể quay về caller. Với **ExecutorChannel**, send() trả thành công có thể chỉ nghĩa là executor đã nhận task. Với **QueueChannel/broker**, việc enqueue không đồng nghĩa Aggregator đã release hoặc DB đã commit.

Hợp đồng API phải phân biệt **accepted for processing** và **business completed**. Khi API async trả 202 Accepted, việc group hoàn tất sẽ được thông báo bằng một trạng thái hoặc event sau đó, không thể đổi kết quả HTTP đã trả.

## 8. Ingress với HTTP, broker và Gateway

### 8.1. HTTP: kiểm soát tenant ở security boundary

Một HTTP controller có thể:

1. Nhận JSON request, parse vào DTO.
2. Kiểm tra auth token/session và ánh xạ thành VerifiedActor.
3. Chuyển event/actor cho OrderEventIngress.
4. Trả 202 cùng eventId/trackingId nếu chấp nhận xử lý async.

~~~text
HTTP request
  headers: X-Tenant=tenant-b, X-Correlation-ID=anything
  body: orderRef=ORD-101, eventType=PAYMENT

Spring Security principal:
  verified tenantId=tenant-a

BindingResolver:
  kiểm tra quyền đối với ORD-101 thuộc tenant-a
  quyết định groupKey=ordready:v1:tenant-a:ORD-101:7
~~~

Không tin X-Tenant/X-Correlation-ID chỉ vì nó được client gửi. Nếu API cho phép client cung cấp một **clientRequestId** để truy vết, có thể lưu nó như **untrusted request metadata** sau khi validate độ dài/ký tự; không biến nó thành khóa để ghép các tenant.

### 8.2. Broker: giữ ID qua retry và restart

Với Kafka/JMS hoặc broker khác, một message có thể được giao lại khi consumer chưa ack/commit. Ingress phải:

- Xác thực source/ACL của topic/queue.
- Parse và validate schemaVersion.
- Lấy verified tenant và order binding từ nguồn đáng tin.
- Tính lại cùng groupKey từ dữ liệu đã được chuẩn hóa/verified.
- Giữ eventId logic ổn định qua redelivery.
- Không dùng partition offset làm business correlation key (offset khác bản ghi và không đại diện cho workflow).
- Chọn ack/requeue/error handling phù hợp với việc nhóm chưa hoàn tất.

Nếu một process tạo group ID ngẫu nhiên nhưng **không lưu mapping** trước khi ack message, restart có thể tạo group ID khác. Khi nghiệp vụ cần khôi phục, dùng deterministic key hoặc một mapping transaction/outbox bền.

### 8.3. Gateway: request/reply correlation khác group correlation

Spring Integration **Messaging Gateway** thường tự tạo tạm một **replyChannel** để ghép reply về đúng lời gọi Java request/reply. Nó không đồng nghĩa với business correlationId do ứng dụng dùng để gom ba event của cùng đơn.

~~~text
API gateway invocation
  replyChannel = temporary gateway channel
  businessCorrelationKey = ordready:v1:tenant-a:ORD-101:7
~~~

Nếu ứng dụng cần chờ **ba event từ nhiều hệ thống độc lập** trong thời gian dài, không giữ Gateway sync chờ vô hạn. Dùng workflow state bền và API trạng thái hoặc callback/event completion. Với một flow request/reply ngắn, vẫn phải bảo vệ replyChannel do framework tạo, tránh client tự điều khiển channel này.

## 9. Dùng correlation key ở Aggregator

Spring Integration mặc định correlation theo **IntegrationMessageHeaderAccessor.CORRELATION_ID**. Khi message có cùng giá trị header này, chúng được đưa vào cùng một **MessageGroup**. Việc **khi nào group được release** là trách nhiệm riêng của **ReleaseStrategy**, không phải chỉ có correlation key là đủ.

~~~mermaid
flowchart TD
    A["OrderPartEvent"] --> I["Ingress: verify + key"]
    I --> C["businessCorrelationKey"]
    C --> G["Aggregator"]
    G --> K{"CorrelationStrategy"}
    K --> Q["MessageGroup theo key"]
    Q --> S{"ReleaseStrategy đủ 3 kinds?"}
    S -->|"Chưa"| W["Giữ group chờ"]
    S -->|"Đủ"| P["OutputProcessor"]
    P --> O["OrderReadiness"]
~~~

### 9.1. Đặc điểm quan trọng: có đủ ba loại event không?

Ba event đến từ các nguồn khác nhau **không nhất thiết có sequenceNumber/sequenceSize** do Splitter sinh. Nếu chỉ đặt correlationId rồi dùng default SequenceSizeReleaseStrategy, Aggregator có thể không biết khi nào đủ để phát.

Trong ví dụ này, completion criterion là:

~~~text
Group đủ khi có chính xác:
  PAYMENT
  INVENTORY
  ADDRESS

Không được dùng:
  group.size() == 3

Nếu ba message đều là PAYMENT do retry hoặc lỗi producer,
group.size() == 3 vẫn không chứng minh đủ ba nhánh.
~~~

Thiết kế đúng là kiểm tra **identity của từng thành phần**, đồng thời có dedup/inbox trước Aggregator nếu broker có thể redeliver.

### 9.2. Data model kết quả

~~~java
import java.util.List;

record OrderReadiness(
        String groupKey,
        String tenantId,
        String orderRef,
        int epoch,
        String decision,
        List<OrderPartEvent> evidence) {
}
~~~

**OrderReadiness** là kết quả nghiệp vụ ghép từ ba đầu vào. Trong code demo, decision READY chỉ khi cả ba approved=true; nếu bất kỳ thành phần không được phê duyệt, decision là REVIEW_REQUIRED. Logic production cần tuân theo trạng thái nghiệp vụ thực tế, có thể gồm reject/retry/manual approval.

## 10. ReleaseStrategy và MessageGroupProcessor

Hai hàm thuần dưới đây tách **điều kiện đủ thành viên** khỏi **cách tổng hợp kết quả**.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

final class OrderGroupRules {
    private OrderGroupRules() {
    }

    static boolean complete(MessageGroup group) {
        if (group.size() != PartKind.values().length) {
            return false;
        }
        Set<PartKind> found = EnumSet.noneOf(PartKind.class);
        for (Message<?> message : group.getMessages()) {
            if (!(message.getPayload() instanceof OrderPartEvent part)) {
                return false;
            }
            if (!found.add(part.kind())) {
                return false; // Hai phần của cùng loại: không đủ group.
            }
        }
        return found.size() == PartKind.values().length;
    }

    static OrderReadiness summarize(MessageGroup group) {
        if (!complete(group)) {
            throw new IllegalStateException("INCOMPLETE_ORDER_GROUP");
        }

        List<Message<?>> messages =
                new ArrayList<>(group.getMessages());
        Message<?> first = messages.get(0);

        String key = (String) first.getHeaders()
                .get(OrderEventIngress.GROUP_KEY);
        String tenant = (String) first.getHeaders()
                .get(OrderEventIngress.TRUSTED_TENANT);
        Integer epoch = (Integer) first.getHeaders()
                .get(OrderEventIngress.WORKFLOW_EPOCH);

        if (key == null || tenant == null || epoch == null) {
            throw new IllegalStateException("MISSING_TRUSTED_METADATA");
        }

        List<OrderPartEvent> evidence = new ArrayList<>();
        for (Message<?> message : messages) {
            if (!Objects.equals(
                    key, message.getHeaders()
                            .get(OrderEventIngress.GROUP_KEY))
                    || !Objects.equals(
                            tenant, message.getHeaders()
                                    .get(OrderEventIngress.TRUSTED_TENANT))
                    || !Objects.equals(
                            epoch, message.getHeaders()
                                    .get(OrderEventIngress.WORKFLOW_EPOCH))) {
                throw new IllegalStateException(
                        "MIXED_WORKFLOW_METADATA");
            }
            evidence.add((OrderPartEvent) message.getPayload());
        }

        evidence.sort(Comparator.comparing(OrderPartEvent::kind));
        String order = evidence.get(0).orderRef()
                .trim().toUpperCase(java.util.Locale.ROOT);
        if (evidence.stream().anyMatch(
                part -> !part.orderRef()
                        .trim().toUpperCase(java.util.Locale.ROOT)
                        .equals(order))) {
            throw new IllegalStateException("MIXED_ORDER_REFS");
        }

        boolean ready = evidence.stream()
                .allMatch(OrderPartEvent::approved);

        return new OrderReadiness(
                key,
                tenant,
                order,
                epoch,
                ready ? "READY" : "REVIEW_REQUIRED",
                List.copyOf(evidence));
    }
}
~~~

**Vì sao check metadata lần nữa?** CorrelationStrategy nhóm theo key đã tính, nhưng khi output được tạo, kiểm tra tenant/epoch/orderRef giúp phát hiện lỗi mapping hoặc producer/integration endpoint vô tình gắn sai header. Một check bổ sung không thay thế việc xác minh quyền tại ingress, nhưng giúp **fail closed** khi nhóm có dữ liệu không nhất quán.

### 10.1. Duplicate trước khi đủ nhóm

Nếu một PAYMENT event bị gửi hai lần trước khi INVENTORY/ADDRESS tới:

~~~text
Group:
  PAYMENT(evt-1)
  PAYMENT(evt-1)   <-- duplicate
  INVENTORY(evt-2)
  ADDRESS(evt-3)
~~~

Hàm complete() sẽ trả false vì group có 4 messages. **Điều đó không giải quyết duplicate**, mà cố ý chặn một kết quả không đáng tin. Nếu có thể gặp redelivery, cần dedup **trước khi thêm vào group** hoặc một cơ chế group processor/release policy chuyên biệt có rule cho duplicate và sửa state. Nếu không, group có thể nằm chờ tới timeout.

**Tại ingress**, một inbox bền với key phù hợp có thể xác định eventId đã chấp nhận trước đó. Nếu cùng eventId nhưng payload khác, nên báo **ID_CONFLICT** thay vì coi message là bản lặp bình thường. Xem phần idempotency.

### 10.2. Không bắt buộc tất cả outcomes đều thành công

Nếu PAYMENT có approved=false nhưng event hợp lệ, nó vẫn **là một thành viên terminal của group**. Aggregator nhận đủ ba loại, rồi trả REVIEW_REQUIRED. Không Filter bỏ message thất bại và vẫn chờ ba thành viên, vì làm vậy sẽ khiến group không đủ.

Đối với lỗi hạ tầng chưa có outcome terminal, cần trạng thái PENDING/RETRYING hoặc error/recovery riêng; không tự tạo APPROVED=false nếu không biết kết quả thực tế.

## 11. IntegrationFlow dùng custom CorrelationStrategy

Trong Java DSL Spring Integration, Aggregator có thể đọc một header riêng làm correlation key. Cách này hữu ích khi giữa ingress và aggregator có Splitter, Scatter-Gather hoặc integration endpoint thay đổi các sequence headers kỹ thuật.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderCorrelationFlowConfig {

    @Bean
    MessageChannel correlatedOrderInput() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel orderReadinessResults() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel lateCorrelatedEvents() {
        return new QueueChannel();
    }

    @Bean
    OrderEventIngress orderEventIngress(
            WorkflowBindingResolver resolver,
            @org.springframework.beans.factory.annotation.Qualifier(
                    "correlatedOrderInput")
            MessageChannel input) {
        return new OrderEventIngress(resolver, input);
    }

    @Bean
    IntegrationFlow orderCorrelationFlow() {
        return IntegrationFlow.from("correlatedOrderInput")
                .aggregate(a -> a
                        .correlationStrategy(message -> {
                            Object key = message.getHeaders()
                                    .get(OrderEventIngress.GROUP_KEY);
                            if (!(key instanceof String text)
                                    || text.isBlank()) {
                                throw new IllegalArgumentException(
                                        "MISSING_BUSINESS_CORRELATION_KEY");
                            }
                            return text;
                        })
                        .releaseStrategy(OrderGroupRules::complete)
                        .outputProcessor(OrderGroupRules::summarize)
                        .groupTimeout(30_000)
                        .sendPartialResultOnExpiry(false)
                        .discardChannel("lateCorrelatedEvents"))
                .channel("orderReadinessResults")
                .get();
    }
}
~~~

**Cách chạy:** cung cấp một bean WorkflowBindingResolver được triển khai thật; các event được xác minh rồi gọi OrderEventIngress.accept(). Một group có đủ PAYMENT, INVENTORY, ADDRESS sẽ trả OrderReadiness vào QueueChannel. Channel này dùng cho ví dụ/test; khi triển khai thật phải có consumer và chiến lược lưu/ack thích hợp.

**Quan trọng:** groupTimeout(30_000) ở đây là giới hạn minh họa cho group chờ quá lâu; vì sendPartialResultOnExpiry=false, không tự tạo kết quả READY khi thiếu thành viên. Với timeout thực tế, cần đánh dấu group INCOMPLETE/EXPIRED trong state store và có chính sách late arrival. Cấu hình discardChannel chỉ xử lý message mà Aggregator thực sự discard theo cơ chế của nó; không tự tạo một workflow trạng thái thất bại bền.

### 11.1. Cách cấu hình dựa vào header mặc định

Khi không có component đổi correlationId kỹ thuật, có thể dùng mặc định:

~~~java
.aggregate(a -> a
        .releaseStrategy(OrderGroupRules::complete)
        .outputProcessor(OrderGroupRules::summarize))
~~~

Vì OrderEventIngress đã gắn CORRELATION_ID, Aggregator mặc định sẽ nhóm theo header đó. Tuy nhiên, với topology có **nested splitter/recipient-list** và nhiều correlation scope, custom correlationStrategy theo businessCorrelationKey giúp diễn đạt rõ rằng Aggregator đang ghép **workflow cha**, không phải một nhóm sequence con.

### 11.2. Dựa trực tiếp vào payload khi nào phù hợp?

Có thể dùng:

~~~java
.aggregate(a -> a
        .correlationStrategy(message -> {
            OrderPartEvent event =
                    (OrderPartEvent) message.getPayload();
            // Giả định đã có verified binding nội bộ.
            // Không lấy tenant từ event chưa được xác thực.
            return event.orderRef();
        }))
~~~

**Đây là phản ví dụ nếu dùng nguyên orderRef**, vì thiếu tenant và epoch. Dùng payload trực tiếp chỉ hợp lệ khi payload đã được **chuẩn hóa, gắn danh tính tenant được xác minh và epoch ổn định**, hoặc correlationStrategy gọi một service đáng tin và không tự diễn giải trường input ngoài quyền. Ở ingress, việc tính trước key thường dễ audit và test hơn việc mỗi Aggregator tự tạo các biến thể khác nhau.

### 11.3. Custom key phải bất biến với cùng group

CorrelationStrategy được gọi khi message đến. Nếu nó phụ thuộc vào:

- Current time (LocalDateTime.now()).
- Ngẫu nhiên UUID mới cho mỗi message.
- Thread name, instance ID hoặc Kafka offset.
- Workflow registry “latest epoch” thay vì **epoch của message**.
- Config thay đổi giữa những lần nhận event.

thì cùng workflow có thể bị chia thành nhiều group. Hãy giữ key/version/binding cố định trong message hoặc sử dụng lookup có khả năng khôi phục identity cũ.

## 12. Unit test hàm tạo key

Vì hàm tạo khóa là một phép biến đổi thuần, có thể kiểm thử mà không cần Spring context.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class OrderCorrelationKeysTest {

    @Test
    void sameVerifiedIdentityProducesSameKey() {
        String first = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", "ORD-101", 7));
        String second = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", " ord-101 ", 7));

        assertEquals(first, second);
        assertEquals(
                "ordready:v1:tenant-a:ORD-101:7",
                first);
    }

    @Test
    void differentTenantsNeverShareAGroupKey() {
        String tenantA = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", "ORD-101", 7));
        String tenantB = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-b", "ORD-101", 7));

        assertNotEquals(tenantA, tenantB);
    }

    @Test
    void aNewWorkflowEpochGetsANewGroup() {
        String epoch7 = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", "ORD-101", 7));
        String epoch8 = OrderCorrelationKeys.from(
                new VerifiedWorkflowBinding(
                        "tenant-a", "ORD-101", 8));

        assertNotEquals(epoch7, epoch8);
    }

    @Test
    void rejectsInvalidTenantAndDelimiter() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderCorrelationKeys.from(
                        new VerifiedWorkflowBinding(
                                "tenant:admin", "ORD-101", 7)));

        assertThrows(IllegalArgumentException.class,
                () -> OrderCorrelationKeys.from(
                        new VerifiedWorkflowBinding(
                                "tenant-a", "ORD:101", 7)));
    }

    @Test
    void rejectsMissingOrInvalidWorkflowEpoch() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderCorrelationKeys.from(
                        new VerifiedWorkflowBinding(
                                "tenant-a", "ORD-101", 0)));
    }
}
~~~

**Các test này chứng minh:** quy tắc tạo key ổn định, cách normalize đã được công bố, tenant và epoch tách biệt, input có ký tự phân cách bị từ chối. Chúng **chưa chứng minh** WorkflowBindingResolver xác thực quyền đúng hoặc các adapter/broker giữ metadata qua mọi lần retry.

## 13. Unit test: ingress gắn header từ binding đã xác minh

Để kiểm tra ranh giới tạo message, dùng một MessageChannel chỉ ghi lại message được gửi; không khởi động IntegrationFlow.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

class OrderEventIngressTest {

    static class RecordingChannel implements MessageChannel {
        Message<?> last;

        @Override
        public boolean send(Message<?> message) {
            last = message;
            return true;
        }

        @Override
        public boolean send(Message<?> message, long timeout) {
            return send(message);
        }
    }

    @Test
    void derivesTrustedCorrelationAtIngress() {
        RecordingChannel channel = new RecordingChannel();

        WorkflowBindingResolver resolver = (actor, event) -> {
            assertEquals("tenant-a", actor.tenantId());
            assertEquals("ORD-500", event.orderRef());
            return new VerifiedWorkflowBinding(
                    actor.tenantId(), event.orderRef(), 4);
        };

        OrderEventIngress ingress =
                new OrderEventIngress(resolver, channel);
        OrderPartEvent input = new OrderPartEvent(
                "evt-payment-500", "ORD-500", 4,
                PartKind.PAYMENT, true);

        ingress.accept(
                input, new VerifiedActor("user-1", "tenant-a"));

        assertNotNull(channel.last);
        assertEquals(input, channel.last.getPayload());
        assertEquals(
                "ordready:v1:tenant-a:ORD-500:4",
                channel.last.getHeaders()
                        .get(OrderEventIngress.GROUP_KEY));
        assertEquals(
                channel.last.getHeaders()
                        .get(OrderEventIngress.GROUP_KEY),
                channel.last.getHeaders()
                        .get(IntegrationMessageHeaderAccessor
                                .CORRELATION_ID));
        assertEquals(
                "tenant-a",
                channel.last.getHeaders()
                        .get(OrderEventIngress.TRUSTED_TENANT));
    }

    @Test
    void rejectedWorkflowNeverPublishesAMessage() {
        RecordingChannel channel = new RecordingChannel();
        WorkflowBindingResolver resolver = (actor, event) -> {
            throw new SecurityException("ORDER_ACCESS_DENIED");
        };

        OrderEventIngress ingress =
                new OrderEventIngress(resolver, channel);

        assertThrows(SecurityException.class,
                () -> ingress.accept(
                        new OrderPartEvent(
                                "evt-denied", "ORD-999", 1,
                                PartKind.PAYMENT, true),
                        new VerifiedActor("user-2", "tenant-a")));
        assertNull(channel.last);
    }
}
~~~

Trong adapter HTTP thực tế, nếu request mang sẵn header "correlationId", controller không chuyển header ấy vào OrderEventIngress: lớp ingress chỉ nhận **payload** và **verified actor**. Test nên bổ sung một request với header giả mạo để xác minh adapter không copy nhầm header trước khi gọi ingress.

**Lưu ý về lỗi xác thực:** production cần trả response phù hợp và logging có kiểm soát, không để nguyên thông tin nội bộ trong exception lộ ra HTTP response.

## 14. Integration test: ba events tới sai thứ tự vẫn chung group

Ví dụ JUnit 5 sau khởi động Spring context dùng OrderCorrelationFlowConfig. Resolver trong test là một **stub**, chỉ dùng để kiểm thử cơ chế grouping; nó không thay thế authorization/registry implementation của production.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderCorrelationFlowTest.TestConfig.class)
class OrderCorrelationFlowTest {

    @Configuration
    @Import(OrderCorrelationFlowConfig.class)
    static class TestConfig {
        @Bean
        WorkflowBindingResolver testBindings() {
            // Test double. Trong production phải verify tenant/order/epoch.
            return (actor, event) ->
                    new VerifiedWorkflowBinding(
                            actor.tenantId(),
                            event.orderRef(),
                            event.claimedEpoch());
        }
    }

    @Autowired
    OrderEventIngress ingress;

    @Autowired
    @Qualifier("orderReadinessResults")
    QueueChannel reports;

    private static final VerifiedActor TENANT_A =
            new VerifiedActor("test-user-a", "tenant-a");
    private static final VerifiedActor TENANT_B =
            new VerifiedActor("test-user-b", "tenant-b");

    @BeforeEach
    void clearOutput() {
        while (reports.receive(0) != null) {
            // Dọn queue output giữa các test.
        }
    }

    private void send(
            String eventId, String order, int epoch,
            PartKind kind, boolean approved,
            VerifiedActor actor) {
        ingress.accept(new OrderPartEvent(
                eventId, order, epoch, kind, approved), actor);
    }

    @Test
    void threeIndependentEventsJoinSameWorkflow() {
        send("evt-a-101", "ORD-101", 10,
                PartKind.ADDRESS, true, TENANT_A);
        send("evt-p-101", "ord-101", 10,
                PartKind.PAYMENT, true, TENANT_A);

        assertNull(reports.receive(0));

        send("evt-i-101", "ORD-101", 10,
                PartKind.INVENTORY, true, TENANT_A);

        Message<?> result = reports.receive(0);
        assertNotNull(result);
        OrderReadiness readiness =
                (OrderReadiness) result.getPayload();

        assertEquals(
                "ordready:v1:tenant-a:ORD-101:10",
                readiness.groupKey());
        assertEquals("tenant-a", readiness.tenantId());
        assertEquals(3, readiness.evidence().size());
        assertEquals("READY", readiness.decision());
        assertNull(reports.receive(0));
    }

    @Test
    void twoTenantsWithSameOrderRefAreNotMixed() {
        send("evt-a-payment", "ORD-202", 3,
                PartKind.PAYMENT, true, TENANT_A);
        send("evt-a-inventory", "ORD-202", 3,
                PartKind.INVENTORY, true, TENANT_A);

        send("evt-b-address", "ORD-202", 3,
                PartKind.ADDRESS, true, TENANT_B);
        assertNull(reports.receive(0));

        send("evt-a-address", "ORD-202", 3,
                PartKind.ADDRESS, true, TENANT_A);

        OrderReadiness result = (OrderReadiness)
                reports.receive(0).getPayload();
        assertEquals("tenant-a", result.tenantId());
        assertEquals(3, result.evidence().size());
        assertNull(reports.receive(0));
    }

    @Test
    void newEpochIsSeparateFromOldEpoch() {
        send("evt-e4-payment", "ORD-303", 4,
                PartKind.PAYMENT, true, TENANT_A);
        send("evt-e4-inventory", "ORD-303", 4,
                PartKind.INVENTORY, true, TENANT_A);
        send("evt-e5-address", "ORD-303", 5,
                PartKind.ADDRESS, true, TENANT_A);

        assertNull(reports.receive(0));

        send("evt-e4-address", "ORD-303", 4,
                PartKind.ADDRESS, true, TENANT_A);

        OrderReadiness result = (OrderReadiness)
                reports.receive(0).getPayload();
        assertEquals(4, result.epoch());
        assertNull(reports.receive(0));
    }

    @Test
    void negativeDomainOutcomeStillCompletesTheGroup() {
        send("evt-p-404", "ORD-404", 1,
                PartKind.PAYMENT, false, TENANT_A);
        send("evt-i-404", "ORD-404", 1,
                PartKind.INVENTORY, true, TENANT_A);
        send("evt-a-404", "ORD-404", 1,
                PartKind.ADDRESS, true, TENANT_A);

        OrderReadiness result = (OrderReadiness)
                reports.receive(0).getPayload();
        assertEquals("REVIEW_REQUIRED", result.decision());
        assertEquals(3, result.evidence().size());
    }
}
~~~

### 14.1. Những gì integration test chứng minh

- Các sự kiện độc lập **không cần đến theo một thứ tự cố định** để được ghép.
- Correlation ID tạo ở ingress giống nhau khi verified tenant/orderRef/epoch giống nhau.
- Hai tenant có cùng orderRef không bị gộp.
- Hai epoch của một order không bị gộp.
- Một terminal event có approved=false vẫn **đóng góp vào group**, không bị nhầm với message bị Filter loại.

### 14.2. Những gì integration test chưa chứng minh

- WorkflowBindingResolver thực tế chống giả mạo quyền truy cập.
- Event duplicate/redelivery được ngăn ở tầng inbox bền.
- MessageGroupStore có thể phục hồi sau restart.
- Cả ba producer kết nối broker cùng một chính sách identity.
- Transaction/các side effect downstream được thực hiện đúng một lần.
- Group timeout/late arrival được quan sát đúng SLA.

Đối với production, cần test bổ sung theo các failure modes này; không chỉ dựa vào một happy-path Spring context.

## 15. Khi message đi qua Router, Filter, Transformer, Splitter và Gateway

Tạo correlation ID tại ingress chỉ có ích khi các bước tiếp theo **giữ hoặc tái lập đúng hợp đồng correlation**.

| Thành phần | Ảnh hưởng thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| **Transformer** | Thay payload hoặc tạo Message mới | Business key vẫn đi qua; dữ liệu đã verified không bị thay |
| **Filter** | Có thể discard một message | Group cần terminal outcome/timeout nếu member bắt buộc bị loại |
| **Content-Based Router** | Chọn channel theo nội dung | Các nhánh vẫn giữ identity group cha |
| **Recipient List** | Nhân request đến nhiều recipient | Dùng group con/sequence riêng nếu chờ mọi recipient trả lời |
| **Splitter** | Sinh nhiều child messages và sequencing headers | Không nhầm group child với workflow business cha |
| **Aggregator** | Gom messages theo key và release policy | Chọn đúng CorrelationStrategy và kiểm tra completeness |
| **Resequencer** | Sắp sequence trong một group | Epoch và sequence metadata rõ ràng |
| **Gateway** | Request/reply và replyChannel tạm | Không gộp replyChannel với business correlation key |
| **Error Channel** | Mang thông tin lỗi trong flow phù hợp | failedMessage/originalMessage có thể thiếu; không tự thành member của group |

### 15.1. Splitter có thể đổi correlation scope

Một Splitter thường gắn **CORRELATION_ID, SEQUENCE_NUMBER, SEQUENCE_SIZE** cho các child messages. Trong nhiều topology, giá trị correlation kỹ thuật ở child dùng để ghép **những phần tử con của cùng một parent Message**, không nhất thiết là cùng business group được tạo từ nhiều external events.

~~~mermaid
flowchart TD
    I["Ingress: businessCorrelationKey=Order-101"] --> S["Splitter"]
    S --> A["Child 1, technical correlation=split-X"]
    S --> B["Child 2, technical correlation=split-X"]
    A --> C["Child Aggregator"]
    B --> C
    C --> P["Business result: Order-101"]
~~~

Giải pháp:

- Giữ **businessCorrelationKey** ở một header riêng để truy vết group cha.
- Dùng technical correlationId của Splitter để Aggregator con ghép đúng sequence.
- Nếu một Aggregator ở tầng business cần gom các sự kiện từ nhiều producer, dùng custom CorrelationStrategy dựa trên **businessCorrelationKey** đã verified.
- Kiểm thử metadata thực tế của reply sau Transformer/Handler thay vì mặc định mọi component giữ nguyên tất cả headers.

**Không ép hai scopes correlation thành một nếu chúng có ý nghĩa khác nhau.** Một order có thể có nhiều packages, mỗi package có sequence riêng, trong khi toàn bộ packages thuộc cùng order workflow.

### 15.2. Filter bỏ một member có thể làm group không bao giờ release

Giả sử ADDRESS_VERIFIED bị Filter loại, nhưng Aggregator cần đủ PAYMENT/INVENTORY/ADDRESS. Group sẽ chờ thiếu ADDRESS.

Nếu ADDRESS không hợp lệ, business có thể tạo **terminal rejection outcome** để Aggregator đưa ra REVIEW_REQUIRED, thay vì discard im lặng. Nếu đó là một lỗi hạ tầng chưa có quyết định cuối, cần retry/timeout/incomplete policy.

**Đừng tùy tiện giảm số lượng expected members để che một member đã mất**. Với ba nguồn khác nhau, cần biết chính xác loại nào đã đáp ứng, loại nào còn thiếu và vì sao.

### 15.3. ErrorMessage không tự tham gia Aggregator

Nếu một handler bị lỗi bất đồng bộ, Spring Integration có thể gửi ErrorMessage sang errorChannel. ErrorMessage có payload là Throwable, không phải OrderPartEvent đã được domain xác nhận.

Một recovery flow muốn tạo terminal failure outcome phải:

1. Xác định event/tenant/workflow group một cách đáng tin.
2. Phân loại lỗi: validation, timeout, transient, unexpected hoặc unknown.
3. Retry đúng phần tử/nhánh nếu có khả năng phục hồi.
4. Nếu nghiệp vụ cho phép kết luận terminal, tạo outcome có type và identity đúng.
5. Đảm bảo không phát **hai terminal outcomes** khi worker thành công muộn và recovery cũng đã tạo failure.

Không ép mọi Throwable thành approved=false, vì một lỗi DB tạm thời **không chứng minh** thanh toán hay inventory bị từ chối.

## 16. Duplicate, replay và idempotency là việc riêng của correlation

Giả sử Kafka giao lại PAYMENT(evt-1) trong lúc Aggregator đang đợi INVENTORY và ADDRESS. Correlation ID đúng sẽ đưa cả hai bản của PAYMENT vào **cùng group**, nhưng như vậy chưa có dedup.

~~~text
input:
  PAYMENT(evt-1)   -> group G
  INVENTORY(evt-2) -> group G
  PAYMENT(evt-1)   -> group G (duplicate)
  ADDRESS(evt-3)   -> group G

Nếu chỉ đếm message:
  group size = 4
  unique kinds = 3
~~~

Vì vậy **tạo group key** và **deduplicate logical events** là hai trách nhiệm khác nhau.

### 16.1. Chọn dedup identity đúng

Ví dụ sự kiện có eventId duy nhất trong một tenant:

~~~text
dedupKey = trustedTenantId + ":" + eventId
~~~

Nếu eventId chỉ duy nhất trong một producer:

~~~text
dedupKey = trustedTenantId + ":" + producerId + ":" + eventId
~~~

Nếu một workflow cho phép **phiên bản mới của cùng loại event**, cần một revision hoặc operationId rõ:

~~~text
logicalPartKey =
    tenantId + ":" + orderRef + ":" + epoch
    + ":" + partKind + ":" + partRevision
~~~

Không coi mọi PAYMENT mới của một order là duplicate vĩnh viễn: hệ thống có thể có correction/reversal legitimate. Ngược lại, không để producer tạo eventId mới cho cùng một redelivery rồi vượt qua dedup.

### 16.2. Inbox/ledger bền

Ví dụ schema PostgreSQL:

~~~sql
CREATE TABLE order_part_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    group_key VARCHAR(240) NOT NULL,
    part_kind VARCHAR(20) NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    status VARCHAR(24) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, producer_id, event_id)
);

CREATE INDEX idx_order_part_inbox_group
    ON order_part_inbox (group_key);
~~~

Một inbox transaction có thể:

1. Tìm/claim identity theo tenant, producer và eventId bằng unique constraint.
2. Khi event đã tồn tại, kiểm tra **payload_digest và group_key**: trùng hoàn toàn có thể là redelivery, khác nội dung phải coi là **ID_CONFLICT**.
3. Chỉ dispatch đến Aggregator nếu event thuộc trạng thái/attempt có thể tiếp tục.
4. Ghi nhận tiến độ và trạng thái terminal hoặc retry phù hợp.

**Cẩn thận điểm cắt transaction:** nếu lưu "đã nhận" rồi crash **trước khi gửi event đến Aggregator**, lần redelivery không được bị bỏ qua một cách làm mất message. Một transaction outbox, ack sau commit hoặc một state machine inbox có trạng thái **RECEIVED → DISPATCHED → COMPLETED** và recovery job là những lựa chọn thường dùng.

~~~text
Phản ví dụ thiếu recovery:
  if notSeen(eventId):
      markSeenInDatabase()
      sendToAggregator()    // crash tại đây làm mất event
~~~

### 16.3. Correlation đúng không đồng nghĩa exactly-once

Ngay cả khi Aggregator tạo đúng một OrderReadiness trong một lần chạy, handler phía sau có thể bị retry và gửi email/đặt hàng nhiều lần nếu reply hoặc ack bị mất.

Áp dụng **idempotency tại nơi phát sinh side effect**, ví dụ:

~~~text
effectKey =
    tenantId + ":" + orderRef + ":" + epoch
    + ":reserve-fulfillment"
~~~

Business operation ID phải phù hợp hành động cần bảo vệ, không chỉ message ID kỹ thuật. Với external API, dùng idempotency key mà provider hỗ trợ hoặc trạng thái UNKNOWN/đối soát khi response bị mất.

### 16.4. Event mới thuộc epoch cũ sau khi group hoàn tất

Một event đến rất muộn cho epoch 7 khi group epoch 7 đã complete. Nếu completed-group metadata còn, Aggregator có thể nhận diện và discard theo policy. Nếu metadata đã bị dọn hoặc process restart với in-memory store, group có thể bị tạo lại.

Cần **business ledger và event identity** còn hiệu lực dài hơn retention của MessageGroupStore nếu contract yêu cầu chống lặp qua thời gian dài.

## 17. Timeout, incomplete group và late arrival

Một group có PAYMENT và INVENTORY nhưng không bao giờ nhận ADDRESS phải có trạng thái vận hành rõ ràng.

~~~text
Expected kinds: PAYMENT, INVENTORY, ADDRESS
Arrived:        PAYMENT, INVENTORY
Missing:        ADDRESS
State:          IN_PROGRESS -> INCOMPLETE after deadline
~~~

Không được:

- Báo READY chỉ vì đã nhận hai event.
- Tự suy ra ADDRESS=false nếu nguồn chưa trả kết quả.
- Xóa group rồi cho rằng lỗi đã được xử lý.
- Gửi reply rỗng tới Gateway và coi là thành công.

### 17.1. Các timeout dễ nhầm

| Timeout | Vị trí | Mục đích |
| --- | --- | --- |
| **Source adapter timeout** | HTTP/Kafka/JMS hoặc client gọi ngoài | Quản lý lần fetch/send |
| **Aggregator groupTimeout** | MessageGroup lifecycle | Giới hạn chờ group có đủ members |
| **Gateway replyTimeout** | Request/reply caller | Giới hạn chờ một reply |
| **Business deadline** | Workflow state | Quy định còn chấp nhận event để hoàn tất không |
| **Retention/MessageGroupStoreReaper** | Storage cleanup | Dọn metadata cũ sau thời gian phù hợp |

Các thời gian trên không tự đồng bộ. Nếu business deadline là 30 phút, một Gateway HTTP đợi 10 giây không thể tự biến cả workflow thành FAILED. Nếu groupTimeout đến trước deadline nghiệp vụ, cần cách khởi tạo lại hoặc dùng persistent workflow state, không chỉ dựa vào in-memory aggregator.

### 17.2. Báo cáo trạng thái INCOMPLETE

Nếu business cần biết **member nào thiếu**, lưu một manifest:

~~~json
{
  "groupKey": "ordready:v1:tenant-a:ORD-101:7",
  "expectedKinds": ["PAYMENT", "INVENTORY", "ADDRESS"],
  "receivedKinds": ["PAYMENT", "INVENTORY"],
  "missingKinds": ["ADDRESS"],
  "status": "INCOMPLETE"
}
~~~

Đây là **mô hình trạng thái nghiệp vụ minh họa**, không phải payload mặc định mà Aggregator tự tạo. Nếu group timeout khi chỉ có hai messages, MessageGroupStore/timeout handler có thể biết hai message đã tới, nhưng muốn giữ lịch sử lâu dài vẫn cần store/ledger phù hợp.

### 17.3. Late event sau khi group đã complete/expired

Nếu event ADDRESS tới sau khi report INCOMPLETE đã được công bố, có các lựa chọn:

- **Freeze:** giữ report cũ, lưu late event để audit.
- **Reconciliation:** tạo một report revision mới với thông tin bổ sung, báo cho downstream.
- **Reopen workflow:** chỉ khi business cho phép, với state transition được quản lý.

Không tự đặt epoch mới cho late event rồi trộn vào một group đang xử lý những events thuộc workflow hoàn toàn khác. Late arrival phải được giải quyết theo **business identity + epoch + eventId**, không chỉ dựa vào timestamp.

### 17.4. Persistent store và multi-instance

Khi các event về các instance khác nhau:

- Dùng broker partition/routing theo group key để một instance sở hữu một group; hoặc
- Dùng shared MessageGroupStore với LockRegistry/transaction thích hợp; hoặc
- Dùng workflow coordinator bền lưu trạng thái từng part theo groupKey.

Một **shared store** không thay thế locking khi hai instance đồng thời release cùng group. Phải test failover, duplicate arrivals, timeout race và khả năng phục hồi sau restart.

## 18. Chống correlation collision và rò rỉ dữ liệu

Một correlation key không đúng có thể dẫn đến hai dạng lỗi đối nghịch:

1. **False split:** các event thật sự cùng workflow tạo khóa khác nhau, làm group không bao giờ đủ.
2. **False join:** các event không cùng workflow tạo cùng khóa, gây trộn dữ liệu hoặc quyết định sai.

### 18.1. Một số dạng collision

| Tình huống | Ví dụ | Cách phòng |
| --- | --- | --- |
| Thiếu tenant namespace | Hai tenant đều có ORD-101 | Include trusted tenant hoặc opaque group ID mapping đúng quyền |
| Thiếu epoch | Một order có nhiều đợt xử lý | Include workflow epoch/operation instance |
| Delimiter ambiguity | a:b + c và a + b:c | Regex giới hạn, escaping hoặc length-prefix encoding |
| Case canonicalization sai | order ab và AB là hai thực thể | Chỉ normalize nếu domain đã công bố case-insensitive |
| Dùng timestamp làm thành phần khóa | Cùng workflow nhận qua hai giờ khác | Dùng epoch ổn định, không dùng now() |
| Dùng UUID mới mỗi event | Ba event độc lập tạo ba khóa | Sinh một lần và lưu mapping hoặc tính deterministic |
| Lookup theo epoch hiện tại | Redelivery epoch cũ bị gắn epoch mới | Tra epoch theo persisted workflow instance |
| Cắt chuỗi ID theo độ dài | Hai ID khác nhau cùng prefix | Reject ID quá dài, không truncate im lặng |
| HMAC rotation thiếu version | Cùng workflow cho ra hai digest | Versioned HMAC key, migration/drain |

### 18.2. Không coi correlation ID như token quyền truy cập

Một ID đủ khó đoán không thay cho authorization. Nếu user biết groupKey của tenant khác, API kiểm tra trạng thái group vẫn phải xác minh principal sở hữu order/tenant tương ứng trước khi trả thông tin.

Không để sự tồn tại của một group trong MessageGroupStore trở thành bằng chứng actor được phép gửi event vào group đó. Phải xác minh message **trước khi thêm vào group**, vì sau khi group đã chứa message giả mạo, việc chỉ lọc output là quá muộn.

### 18.3. Tránh lộ business IDs qua metrics

Metric có nhãn correlationId của từng đơn có thể tạo **cardinality rất lớn**, tốn tài nguyên và làm lộ mã đơn. Nên:

- Dùng labels hữu hạn như component, ingress adapter, event type, result status, reason code.
- Dùng correlation key ở log/tracing có quyền truy cập, masking và retention phù hợp.
- Không đưa raw correlation key vào URL public hoặc error text trả cho client nếu nó chứa business identity.
- Nếu cần một public tracking ID, cấp opaque ID riêng có mapping/authorization rõ ràng.

### 18.4. Bảo vệ trước key quá lớn hoặc group flooding

Nếu một client có thể tạo vô hạn group IDs:

~~~text
request 1 -> random correlation A
request 2 -> random correlation B
...
request 1,000,000 -> random correlation ...
~~~

Aggregator có thể giữ hàng triệu MessageGroup chưa hoàn tất. Bên cạnh authorization, cần:

- Rate limit và quota theo tenant/producer.
- Giới hạn kích thước và số lượng workflow active.
- Validate độ dài và cấu trúc key.
- Group timeout/expiry và MessageGroupStore capacity.
- Backpressure ở ingress và monitoring tuổi group.
- Xóa/expire theo chính sách, không tăng retention vô hạn để che mất member.

## 19. Observability: xem được vì sao message không join đúng

Trong môi trường có nhiều Router và Integrations, một lỗi correlation thường xuất hiện dưới dạng **Aggregator không ra output**. Chỉ đếm exception là chưa đủ, vì không có exception nào bắt buộc phải xảy ra khi group chỉ có 1/3 thành viên.

| Metric | Điều nên quan sát |
| --- | --- |
| **correlation_ingress_accepted_total{source}** | Số event được chấp nhận vào pipeline |
| **correlation_binding_rejected_total{reason}** | Event không được phép gắn với order/workflow |
| **correlation_key_created_total{version}** | Số lần gắn key theo version |
| **correlation_key_validation_failed_total{reason}** | Key không hợp lệ |
| **correlation_group_active** | Số nhóm đang chờ |
| **correlation_group_size{stage}** | Số members mỗi nhóm, báo cáo bằng histogram |
| **correlation_group_age_seconds** | Tuổi nhóm chưa complete |
| **correlation_group_completed_total{decision}** | Số group hoàn tất theo quyết định |
| **correlation_group_timeout_total** | Group hết hạn trước khi đủ thành viên |
| **correlation_missing_part_total{kind}** | Thành viên bắt buộc thiếu tại timeout |
| **correlation_duplicate_event_total{source}** | Redelivery/dedup xảy ra |
| **correlation_identity_conflict_total** | EventId trùng nhưng payload/group khác |
| **correlation_late_event_total{reason}** | Message đến sau khi workflow đã đóng |
| **correlation_recovery_failed_total** | Error flow không thể phục hồi |

Không gắn tenantId, orderRef, eventId hoặc groupKey có cardinality tùy ý vào metrics. Dùng log/tracing có kiểm soát để truy cứu một group cụ thể.

### 19.1. Log ingress có cấu trúc

~~~json
{
  "stage": "verified-ingress",
  "eventId": "evt-payment-101",
  "eventType": "PAYMENT",
  "correlationSchema": "ordready:v1",
  "groupKeyRef": "opaque-or-redacted-reference",
  "bindingVerified": true,
  "outcome": "ACCEPTED"
}
~~~

Đây là **log minh họa**, không phải output mặc định của Spring Integration. Không ghi raw token, user password, thông tin thanh toán hoặc toàn bộ payload trong exception/log.

### 19.2. Log khi group thiếu member

~~~json
{
  "stage": "order-readiness-aggregation",
  "correlationSchema": "ordready:v1",
  "groupStatus": "INCOMPLETE",
  "expectedKinds": ["PAYMENT", "INVENTORY", "ADDRESS"],
  "receivedKinds": ["PAYMENT", "INVENTORY"],
  "missingKinds": ["ADDRESS"],
  "timeoutReason": "BUSINESS_DEADLINE_EXPIRED"
}
~~~

Một log như vậy giúp phân biệt thiếu ADDRESS với lỗi parser, wrong tenant, duplicate PAYMENT hoặc mất routing header.

### 19.3. Những cảnh báo nên có

1. Active groups tăng liên tục trong khi completed groups không tăng.
2. Một partKind bị thiếu trên phần lớn các group sau một lần deploy.
3. Correlation key version v1 và v2 cùng xuất hiện với cùng workflow chưa drain.
4. EventId trùng nhưng có payload digest khác.
5. Tỷ lệ unauthorized/missing binding tăng bất thường.
6. Completed group nhận late event với eventId chưa thấy trước.
7. Shared MessageGroupStore lỗi hoặc lock timeout.
8. Một workflow đã READY nhưng downstream effect bị tạo lặp sau replay.
9. Một tenant tạo quá nhiều group chưa hoàn tất trong thời gian ngắn.
10. Group giữa các instance bị phân mảnh do routing/partition key không nhất quán.

## 20. Runbook: một order có ba events nhưng Aggregator không tạo kết quả

**Tình huống:** operator thấy Payment, Inventory và Address đều được ghi log, nhưng không có OrderReadiness.

### Bước 1 — Truy tìm ba event IDs

Kiểm tra ba event logic thuộc **cùng order và cùng workflow epoch hay không**. Không chỉ so sánh orderRef bằng mắt vì hai tenant có thể dùng cùng mã.

### Bước 2 — So sánh group key ở ingress

Những giá trị cần đối chiếu:

~~~text
eventId             tenant       orderRef    epoch   groupKey
evt-p-1             tenant-a     ORD-101     7       ...:ORD-101:7
evt-i-1             tenant-a     ORD-101     7       ...:ORD-101:7
evt-a-1             tenant-a     ORD-101     8       ...:ORD-101:8
~~~

Ở đây Address đang ở epoch 8, nên Aggregator không nên ghép nó vào group epoch 7. Cần điều tra **binding resolver/epoch lookup**, không đổi correlation ID thủ công để “cho đủ”.

### Bước 3 — Kiểm tra metadata qua các endpoint

Kiểm tra Transformer/Router/Splitter có xóa **businessCorrelationKey** hoặc thay **CORRELATION_ID** kỹ thuật không. Xác nhận Aggregator đang dùng **đúng chiến lược** mà kiến trúc mong muốn (header mặc định hay custom header).

### Bước 4 — Kiểm tra release strategy

Nếu group có ba messages nhưng toàn PAYMENT, **không đủ ba kinds**. Tìm duplicate event, nhầm eventType mapping hoặc nguồn INVENTORY/ADDRESS đã lỗi. Không đổi release policy thành group.size() >= 3 để che mất thành viên.

### Bước 5 — Kiểm tra timeout và state

Group còn ACTIVE, đã EXPIRED hay đã COMPLETED? Metadata còn trong store không? Có reaper/timeout trước khi đủ member, hoặc late arrival sau khi group đóng không?

### Bước 6 — Kiểm tra inbox và ack

Một event được đánh dấu SEEN trong inbox nhưng chưa DISPATCHED vì crash sẽ không tự tới Aggregator. Xác định transaction/outbox và recovery job, không chỉ đếm số lần producer gửi.

### Bước 7 — Chọn hành động có kiểm soát

- Replay **đúng logical eventId** nếu chưa xử lý và còn hợp đồng retry.
- Đối soát khi trạng thái external effect UNKNOWN.
- Quarantine event không hợp lệ/không có quyền.
- Tạo correction/new workflow epoch khi nghiệp vụ cho phép.
- Không sửa tay database group key nếu chưa kiểm tra các effect đã xảy ra.

### Bước 8 — Xác minh sau phục hồi

Kiểm tra nhóm có đúng PAYMENT/INVENTORY/ADDRESS, release một lần theo policy, OrderReadiness đúng tenant và epoch, downstream không tạo side effect trùng.

## 21. Nếu payload không có khóa nghiệp vụ tự nhiên thì làm sao?

Không phải workflow nào cũng có một orderRef xuất hiện trong mọi message. Một quy trình gửi biểu mẫu qua ba nhà cung cấp có thể chỉ có **requestId nội bộ** được tạo khi yêu cầu mới bắt đầu.

Khi đó dùng **opaque correlation ID được sinh một lần**:

~~~mermaid
flowchart LR
    N["Client yêu cầu workflow mới"] --> A["Ingress xác thực"]
    A --> C["Create workflow"]
    C --> P["Persist workflowId + mapping"]
    P --> F["Phát 3 branch commands"]
    F --> R["Branches giữ workflowId"]
    R --> G["Gather theo workflowId"]
~~~

### 21.1. Quy trình khởi tạo

1. Nhận lệnh create workflow có business idempotency key ổn định.
2. Xác thực tenant/actor và quyền tạo workflow.
3. Tra registry theo **clientOperationId** hoặc logical request identity để kiểm tra đã tạo workflow trước đó chưa.
4. Nếu chưa, sinh một UUID/ULID **một lần**, lưu mapping và trạng thái với unique constraint.
5. Commit state/outbox trước khi phát nhiệm vụ tới các branch.
6. Mọi branch command/reply nhận cùng **workflowId** từ nguồn nội bộ đã xác minh.
7. Nếu lệnh create bị retry, trả về **workflowId cũ** thay vì sinh thêm một group mới.

~~~text
create(requestKey=tenant-a:signup-815)
  -> persisted workflowId=019f...a12

retry create(requestKey=tenant-a:signup-815)
  -> same workflowId=019f...a12
~~~

Lúc này correlation không còn được tính trực tiếp bằng cách nối orderRef, mà bằng cách **tra mapping tin cậy** từ business content tới một ID đã được cấp phát bền.

### 21.2. Dùng key nội bộ khác với external tracking token

Một public tracking token chỉ giúp client truy vấn trạng thái sau khi authorization; nó không nên được xem là chứng cứ quyền truy cập. Có thể dùng cùng opaque identifier nếu hợp đồng bảo mật cho phép, nhưng vẫn phải xác thực quyền. Với workflow nhạy cảm, tách public tracking token khỏi correlation key nội bộ có thể giảm lộ topology.

### 21.3. Quyết định khi nào sinh mới và khi nào dùng lại

| Đầu vào | Hành động |
| --- | --- |
| Tạo workflow lần đầu, chưa có state | Sinh ID một lần, persist mapping |
| Retry cùng logical create request | Trả ID cũ |
| Message tiếp theo của workflow | Tra mapping/đính kèm ID cũ |
| Cố ý khởi động workflow mới | Tạo generation/epoch mới theo nghiệp vụ |
| Một late message từ generation cũ | Giữ generation cũ, phân loại late |
| Mapping không tìm thấy nhưng event đã cũ | Quarantine/đối soát, không tự đoán ID mới |

Đây là trường hợp quan trọng để hiểu rằng **tạo correlation ID ở điểm vào** có thể có nghĩa **tạo một lần cho workflow** rồi **khôi phục ở những ingress event tiếp theo**, chứ không có nghĩa sinh mỗi message một ID.

## 22. Bài thực hành: nhập hồ sơ đăng ký khách hàng

Thiết kế một workflow đăng ký mới với ba nguồn đánh giá:

~~~text
ApplicationSubmitted
  -> IdentityCheckResult
  -> CreditCheckResult
  -> RiskCheckResult
  -> OnboardingDecision
~~~

Tài liệu yêu cầu các kết quả Identity, Credit và Risk có thể đến không theo thứ tự, qua những dịch vụ độc lập. Hai tenant có thể cùng dùng externalApplicationRef="APP-100". Một yêu cầu bị retry qua broker; một đợt đánh giá lại cùng hồ sơ có epoch mới.

### 22.1. Thiết kế identity

Hãy xác định và phân biệt:

- trustedTenantId từ principal/ACL.
- externalApplicationRef từ nội dung đã xác minh.
- assessmentEpoch từ workflow registry.
- eventId của mỗi event từ từng producer.
- producerId để làm rõ phạm vi duy nhất của eventId.
- correlation key cho một logical assessment.
- clientRequestId chỉ dùng tracing/idempotency của lệnh create khi phù hợp.

Ví dụ khóa:

~~~text
assessment:v1:tenant-a:APP-100:epoch-2
~~~

**Yêu cầu**: tenant-a/APP-100/epoch-2 không được chung group với tenant-b/APP-100/epoch-2, hoặc tenant-a/APP-100/epoch-3.

### 22.2. Triển khai ingress

1. Xây dựng VerifiedActor hoặc VerifiedProducerContext từ security layer.
2. Viết AssessmentBindingResolver xác nhận application thuộc tenant và epoch hợp lệ.
3. Viết AssessmentCorrelationKeys sinh key deterministic theo contract.
4. Tạo Spring Message mới với verified tenant, eventId, workflowEpoch, businessCorrelationKey.
5. Không copy errorChannel, replyChannel, role hoặc correlationId client-supplied.
6. Nếu là create workflow không có natural key, sinh opaque ID một lần, persist mapping rồi tái sử dụng khi retry.
7. Viết unit test so sánh cùng/khác key và reject unknown application.

### 22.3. Triển khai Aggregate

1. Dùng Aggregator với CorrelationStrategy theo businessCorrelationKey.
2. Viết ReleaseStrategy cần đủ IDENTITY, CREDIT, RISK.
3. Kiểm tra mỗi kind có đúng một terminal outcome.
4. Tạo AssessmentDecision không phụ thuộc arrival order.
5. Nếu một kind REJECTED, hoàn tất group với quyết định MANUAL_REVIEW/REJECTED theo domain policy.
6. Nếu một kind mất vì outage, giữ IN_PROGRESS rồi báo INCOMPLETE khi hết business deadline.
7. Lưu state bền, có per-event dedup và late-arrival policy.

### 22.4. Bộ dữ liệu kiểm thử

| Case | Tenant | Application | Epoch | Event kinds | Mong đợi |
| --- | --- | --- | --- | --- | --- |
| A | tenant-a | APP-100 | 2 | CREDIT, IDENTITY, RISK | Một decision đúng group |
| B | tenant-b | APP-100 | 2 | IDENTITY | Không join với A |
| C | tenant-a | APP-100 | 3 | CREDIT | Không join với epoch 2 |
| D | tenant-a | APP-100 | 2 | CREDIT trùng eventId | Dedup hoặc conflict, không đếm 2 thành viên |
| E | tenant-a | APP-100 | 2 | RISK thiếu sau deadline | INCOMPLETE, không SUCCESS |
| F | tenant-a | APP-100 | 2 | Header correlationId giả mạo | Bị bỏ qua/thay thế tại ingress |
| G | tenant-a | APP-100 | 2 | Một event denied | Không đưa vào group trước authorization |
| H | tenant-a | APP-100 | 2 | Late event sau completed | Audit/discard/correction theo policy |

### 22.5. Tiêu chí đạt

| Tiêu chí | Bằng chứng |
| --- | --- |
| Ingress trust boundary | Event sai quyền không vào channel |
| Khóa deterministic hoặc mapping bền | Retry cùng workflow cho cùng key |
| Namespace tenant/epoch | Hai tenant/epoch khác nhau không bị trộn |
| Header ownership | Chỉ metadata tin cậy đi vào Aggregator |
| Custom CorrelationStrategy | Đọc đúng key đã verified |
| ReleaseStrategy | Kiểm tra đúng các loại outcome |
| Duplicate protection | Bản lặp không thay completeness |
| Error handling | Timeout/unknown không biến thành business rejection |
| Idempotency | Replay không sinh effect trùng |
| Observability | Tìm được vì sao group còn pending |

## 23. Câu hỏi tự kiểm tra

1. Content-based correlation khác message ID hoặc trace ID ở đâu?
2. Vì sao sinh UUID mới cho mỗi event lại làm Aggregator không thể ghép nhóm?
3. Khi nào cần sinh một opaque workflow ID một lần và lưu mapping?
4. Vì sao chỉ dùng orderRef có thể gây trộn dữ liệu trong hệ thống đa tenant?
5. Workflow epoch giải quyết vấn đề gì?
6. Vì sao redelivery cũ không được tự gắn epoch hiện tại?
7. Khi ingress nhận correlationId client-supplied, phải xử lý thế nào?
8. Tại sao String.toUpperCase() không mặc định là an toàn cho mọi business ID?
9. Hàm tạo key deterministic cần những tính chất nào?
10. CorrelationStrategy của Spring Integration trả về gì và có được null không?
11. CorrelationStrategy và ReleaseStrategy có hai trách nhiệm khác nhau như thế nào?
12. Nếu ba messages đều là PAYMENT, group.size() == 3 có cho phép release không?
13. Tại sao cần một businessCorrelationKey bên cạnh CORRELATION_ID kỹ thuật khi có Splitter?
14. Gateway replyChannel có phải là khóa nhóm ba external events không?
15. Filter loại một event bắt buộc có hậu quả gì đối với Aggregator?
16. Nếu MessageGroupStore là in-memory, restart có ảnh hưởng thế nào?
17. Vì sao correlation đúng không bảo đảm exactly-once side effects?
18. Làm thế nào phát hiện một eventId được dùng lại với payload khác?
19. Một event đã được ghi vào inbox nhưng chưa dispatch có thể bị mất ở đâu?
20. Vì sao không dùng correlation key làm token authorization?

## 24. Checklist trước khi đưa correlation ở ingress vào production

- Đã định nghĩa **logical workflow/group boundary** rõ ràng.
- Đã tách eventId, messageId, traceId, requestId, correlationId và business entity ID.
- Tenant và quyền đối với business object được xác minh **trước khi tạo group key**.
- Epoch/workflow generation được lưu bền và ổn định qua redelivery.
- Có quy tắc canonicalization, delimiter escaping hoặc cấu trúc khóa không nhập nhằng.
- Khóa có version và chiến lược migration khi thuật toán thay đổi.
- Với opaque ID, mapping được tạo **một lần** và có tính idempotent.
- Không tin correlationId/replyChannel/errorChannel do client tự gắn.
- MessageBuilder dựng lại headers nội bộ theo allowlist.
- Business correlation key được duy trì qua Router/Transformer/Splitter theo đúng scope.
- Aggregator dùng correlationStrategy phù hợp với group cần ghép.
- ReleaseStrategy kiểm tra **đúng tập thành viên**, không chỉ đếm số messages.
- Có per-event dedup/inbox trước khi Aggregator nếu có thể redeliver.
- Idempotency record và dispatch có transaction/outbox/recovery chống mất event.
- Các outcomes failure/denied được biểu diễn rõ, không bị Filter loại im lặng.
- Timeout, late arrival, partial result và group cleanup có hợp đồng nghiệp vụ.
- MessageGroupStore, LockRegistry và partition routing phù hợp triển khai nhiều instance.
- Downstream side effects có idempotency độc lập với group metadata.
- Không đưa group key hoặc business ID có cardinality cao vào metric labels.
- Test bao phủ cùng group, khác tenant, khác epoch, duplicate, spoofed header, timeout và restart.
- Có dashboard/runbook để điều tra pending groups, false split và false join.

**Kết luận:** Tạo correlation ID ở điểm vào là việc thiết lập **identity đáng tin cho một workflow**, không phải thêm một chuỗi ngẫu nhiên vào mỗi message. Khi ingress đã xác minh tenant, business object và workflow epoch, cùng một logic content-based sẽ gắn **cùng group key** cho các sự kiện liên quan, kể cả khi chúng tới từ nhiều adapter và bị giao lại. Spring Integration Aggregator có thể dùng header mặc định hoặc CorrelationStrategy riêng để nhóm message, còn ReleaseStrategy quyết định khi nào đủ thành viên. Kết hợp trust boundary, canonical key, dedup, persistent state, timeout và idempotency giúp tránh cả **mất kết quả vì nhóm bị tách** lẫn **trộn dữ liệu vì nhóm bị nhập nhầm**.

## Tài liệu tham khảo

- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): mặc định correlation theo CORRELATION_ID, CorrelationStrategy, ReleaseStrategy, MessageGroupStore và timeout.
- [Spring Integration API — CorrelationHandlerSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html): cấu hình correlationStrategy, releaseStrategy và groupTimeout bằng Java DSL.
- [Spring Integration API — AggregatorSpec](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/dsl/AggregatorSpec.html): outputProcessor và cấu hình Aggregator.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): sequence/correlation headers khi tách message và nested grouping.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): replyChannel/request-reply khác với business group correlation.
- [Spring Integration Reference — TCP Message Correlation](https://docs.spring.io/spring-integration/reference/ip/correlation.html): ví dụ liên kết reply với request bằng dữ liệu nghiệp vụ khi đi qua adapter.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage/errorChannel và lỗi đồng bộ/bất đồng bộ.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel và ranh giới dispatch.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): dedup ở tầng endpoint và các giới hạn trước side effect.
- [Enterprise Integration Patterns — Correlation Identifier](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html): ý nghĩa khóa liên kết các messages trong một workflow.
