# Idempotency khi message chạy lại routing slip

## 1. Bối cảnh: một đường đi động có thể chạy nhiều lần

Trong chương **Routing slip** của module **SPRING_INTEGRATION_PATTERN**, chúng ta thực hành các Enterprise Integration Patterns bằng Spring Integration để xây dựng luồng message ít phụ thuộc, dễ mở rộng. Router, Filter, Transformer, Splitter, Aggregator và Gateway tổ chức những bước nghiệp vụ; retry, error channel, correlation và việc quan sát các nhánh giúp luồng tiếp tục hoạt động khi gặp sự cố.

Một routing slip mô tả **đường đi của một message qua những endpoint tiếp theo**. Thay vì cấu hình cố định nhiều router cho từng nhánh, message mang thông tin để một endpoint biết cần gửi reply tới channel nào sau khi xử lý xong. Mẫu này thuận tiện cho quy trình linh hoạt, nhưng khi **message được chạy lại**, những bước đã thực hiện có thể bị gọi thêm lần nữa.

Ví dụ hệ thống tiếp nhận sự kiện **shipment.requested** rồi thực hiện:

1. **validateShipment**: kiểm tra dữ liệu (không có side effect).
2. **reserveInventory**: ghi giữ hàng trong kho (có side effect).
3. **chargePayment**: yêu cầu thu tiền (có side effect ngoài hệ thống).
4. **notifyCustomer**: gửi thông báo xác nhận (có side effect ngoài hệ thống).

Nếu lỗi mạng xảy ra sau khi chargePayment đã thu tiền nhưng trước khi kết quả được xác nhận, việc gửi lại cùng sự kiện từ đầu có thể **giữ hàng lần hai, thu tiền lần hai hoặc gửi email lần hai**. Routing slip không tự nhận biết tác động nghiệp vụ nào đã xảy ra.

~~~mermaid
flowchart LR
    I["ShipmentRequested evt-301"] --> S["Routing slip"]
    S --> V["validateShipment"]
    V --> R["reserveInventory"]
    R --> C["chargePayment"]
    C --> N["notifyCustomer"]
    C -->|"Mất phản hồi / lỗi"| X["Retry cùng event"]
    X -.-> S
~~~

**Mục tiêu bài học**

- Giải thích chính xác cơ chế routing slip, path và vị trí hiện tại trong Spring Integration.
- Phân biệt **retry một handler**, **replay từ ingress**, **resume từ checkpoint** và **redelivery từ broker**.
- Xây dựng khóa idempotency theo **sự kiện nghiệp vụ + bước có tác động**.
- Thiết kế transaction, checkpoint, outbox và external idempotency cho từng chặng.
- Hiểu vai trò/giới hạn của Idempotent Receiver và MetadataStore.
- Viết kiểm thử tái chạy, lỗi sau side effect, chạy song song, restart và phiên bản flow.

## 2. Routing slip trong Spring Integration thực sự làm gì?

Spring Integration hỗ trợ mẫu Routing Slip từ phiên bản 4.1. Framework dùng metadata **routingSlip** trên message để tìm **channel tiếp theo** ở những endpoint kiểu **AbstractMessageProducingHandler**, khi endpoint tạo reply nhưng **không** đặt outputChannel tường minh.

Khi routing slip đã đi hết, framework quay về cách tìm **replyChannel** thông thường. Routing slip **không tự tạo một workflow engine bền vững** và không bảo đảm mỗi bước chỉ được thực hiện một lần.

### 2.1. Path và routingSlipIndex

Routing slip mô tả một **path** gồm những entry (thường là tên channel). Framework quản lý **routingSlipIndex** để biết entry hiện tại. Trong Spring Integration, path và index thuộc **cấu trúc của header routingSlip do framework quản lý**; không nên coi index là một header tùy ý hoàn toàn độc lập rồi tự tăng bằng tay.

Giả sử path là:

~~~text
validateChannel -> reserveChannel -> chargeChannel -> notifyChannel
~~~

Một mô hình khái niệm:

| Giai đoạn | Entry tiếp theo | Ý nghĩa |
| --- | --- | --- |
| Bắt đầu | validateChannel | Gửi reply từ endpoint tạo slip tới validate |
| Sau validate | reserveChannel | Validate thành công và tạo reply |
| Sau reserve | chargeChannel | Reserve đã tạo reply để chuyển tiếp |
| Sau charge | notifyChannel | Charge đã tạo reply để chuyển tiếp |
| Sau notify | Hết path | Xử lý replyChannel bình thường nếu có reply |

**Chỉ số là vị trí định tuyến, không phải dấu xác nhận đã commit.** Một chặng có thể đã ghi database hoặc gọi HTTP thành công rồi crash trước khi bản cập nhật tiến độ được lưu bền. Ngược lại, một message có vị trí slip ở phía sau không chứng minh mọi side effect trước đó đều thành công.

### 2.2. Điều kiện để routing slip được tham khảo

Thuật toán định tuyến hoạt động khi **handler có reply** và **không cấu hình outputChannel tường minh** cho endpoint đó. Nếu handler trả null, flow có thể kết thúc tại đó; không thể mặc nhiên cho rằng message sẽ tự tiến sang bước tiếp theo.

~~~mermaid
flowchart TD
    H["Handler nhận message"] --> R{"Có reply?"}
    R -->|"Không"| STOP["Không tạo message tiếp theo"]
    R -->|"Có"| E{"Endpoint có outputChannel rõ ràng?"}
    E -->|"Có"| OUT["Chuyển tới outputChannel"]
    E -->|"Không"| SL{"Routing slip còn path?"}
    SL -->|"Có"| NEXT["Chọn channel kế tiếp"]
    SL -->|"Hết"| REPLY["Xét replyChannel bình thường"]
~~~

Nếu outputChannel được chỉ định rõ, đừng kỳ vọng routing slip sẽ ghi đè đích đó. Tương tự, nếu một bước đã trả null trước chặng cuối, các bước sau không tự chạy.

### 2.3. Entry tĩnh và RoutingSlipRouteStrategy

Path có thể chứa:

- Tên bean MessageChannel cố định.
- Tên bean **RoutingSlipRouteStrategy** quyết định channel động.
- Biểu thức SpEL, tùy khả năng xử lý của RoutingSlipHeaderValueMessageProcessor.

Một **RoutingSlipRouteStrategy** có thể được hỏi nhiều lần tại **cùng vị trí path**, cho đến khi nó trả về null hoặc chuỗi rỗng để framework chuyển sang entry kế tiếp. Khi strategy trả về tên channel, index có thể **giữ nguyên** để strategy quyết định lần sau có tiếp tục hay không.

Điểm này quan trọng với idempotency: một channel được strategy chọn **nhiều lần có chủ đích** không nhất thiết là duplicate. Ví dụ một bước xử lý lần lượt nhiều phần tử cần khóa theo **itemId hoặc logical iteration**; nếu chỉ dùng eventId + stepId, các lần xử lý hợp lệ có thể bị bỏ qua nhầm.

### 2.4. Header routingSlip không phải trạng thái hoàn tất nghiệp vụ

| Thành phần | Chịu trách nhiệm |
| --- | --- |
| routingSlip path | Biết cần đến những channel nào hoặc strategy nào |
| routingSlipIndex | Trạng thái định tuyến trong message hiện tại |
| eventId | Nhận diện một sự kiện nghiệp vụ logic qua các lần gửi lại |
| stepId | Nhận diện một tác vụ nghiệp vụ cụ thể |
| step status | PENDING, PROCESSING, COMPLETED, FAILED, UNKNOWN |
| idempotency record | Ngăn lặp một tác động đã hoàn tất theo khóa nghiệp vụ |
| outbox/inbox hoặc broker | Hỗ trợ chuyển giao bền và redelivery nếu được cấu hình |

Routing slip giúp **chọn đường đi**, còn trạng thái hoàn tất và cam kết side effect phải do **ứng dụng và hạ tầng phù hợp** quản lý.

## 3. Khi nào cùng một routing slip được chạy lại?

Có nhiều loại chạy lại, và mỗi loại cần cơ chế phục hồi khác nhau.

### 3.1. Replay lại từ điểm vào

Producer, scheduler hoặc operator phát **cùng eventId** vào ingress lần thứ hai. Nếu tại ingress, ứng dụng tạo lại routingSlip path từ đầu, chuỗi có thể chạy lại từ validate. Đường đi hợp lệ nhưng mọi bước có side effect phải chịu được việc được gọi thêm.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Slip ingress
    participant V as Validate
    participant R as Reserve
    participant C as Charge
    P->>S: evt-301 lần 1
    S->>V: validate
    V->>R: reserve
    R->>C: charge
    C--xP: Mất phản hồi
    P->>S: evt-301 lần 2
    S->>V: validate lại
    V->>R: reserve lại
    Note over R: Phải nhận diện effect đã hoàn tất
~~~

### 3.2. Retry ngay tại một handler

Khi một Retry Advice đặt **quanh handler chargePayment**, cùng message có thể được xử lý nhiều lần tại **một bước**, mà chưa quay về ingress. Khi lỗi tạm thời xảy ra **trước** side effect, retry có thể thành công. Nếu lỗi xảy ra **sau** side effect nhưng **trước** phản hồi, retry có thể tạo trùng.

Không được suy ra rằng retry cục bộ luôn an toàn hơn retry toàn flow: nó chỉ **thu hẹp phạm vi công việc chạy lại**. Tại biên HTTP, database hoặc email, vẫn cần idempotency và chính sách lỗi rõ ràng.

### 3.3. Redelivery từ broker hoặc hàng đợi

Nếu một chặng chuyển message sang broker, consumer có thể crash sau khi đã cập nhật hệ thống đích nhưng trước acknowledgement. Broker redeliver message tới consumer. Lần này, routingSlip header được giữ ở mức nào phụ thuộc adapter, serialization, việc lưu/publish header và nơi message được lấy lại.

**Không được mặc định rằng broker luôn giữ nguyên routingSlip hoặc routingSlipIndex.** Một số môi trường phân tán không thể serialize nội dung slip nếu path chứa strategy biểu thức inline. Hãy kiểm thử cách adapter chuyển header và chỉ dựa vào một **checkpoint nghiệp vụ bền** khi cần resume chính xác.

### 3.4. Resume từ snapshot/checkpoint

Một hệ thống có thể lưu trạng thái đã hoàn tất các bước và **quyết định tiếp tục từ bước chưa hoàn tất**. Nếu snapshot chỉ lưu routingSlipIndex mà không lưu trạng thái side effect, vẫn có hai sai lệch:

- **Index lùi:** side effect đã thành công nhưng index chưa lưu → có nguy cơ effect lặp.
- **Index tiến quá xa:** đã lưu tiến độ trước khi effect commit → có nguy cơ bỏ qua effect chưa hoàn tất.

Khi cần resume an toàn, checkpoint, hiệu ứng và bản ghi idempotency phải có quan hệ commit nhất quán hoặc có cơ chế đối soát khi chúng nằm ở các hệ thống khác nhau.

## 4. Định nghĩa idempotency ở mức từng bước

Giả sử evt-301 cần thực hiện ba tác động:

| Step ID | Effect | Có thể được lặp an toàn bằng cách nào? |
| --- | --- | --- |
| validate | Kiểm tra dữ liệu thuần | Có thể chạy lại; không tạo side effect |
| reserve-inventory | Ghi số lượng đã giữ | Unique business operation hoặc DB transaction |
| charge-payment | Yêu cầu thu tiền bên ngoài | Stable idempotency key gửi sang payment API |
| notify-customer | Gửi email/SMS | Provider key, outbox, trạng thái gửi và đối soát |

Một khóa thường có dạng:

~~~text
idempotencyKey = trustedTenantId + ":" + eventId + ":" + logicalStepId
~~~

Ví dụ:

| Tenant | Event | Step | Key |
| --- | --- | --- | --- |
| tenant-A | evt-301 | reserve-inventory | tenant-A:evt-301:reserve-inventory |
| tenant-A | evt-301 | charge-payment | tenant-A:evt-301:charge-payment |
| tenant-A | evt-301 | notify-customer | tenant-A:evt-301:notify-customer |
| tenant-A | evt-302 | charge-payment | tenant-A:evt-302:charge-payment |

**Không dùng cùng một khóa duy nhất cho cả routing slip** rồi coi toàn bộ flow hoàn tất sau khi bước đầu thành công. Mỗi bước có trạng thái và rủi ro riêng; một bước đã xong không được làm bước sau bị loại khi retry.

### 4.1. Không lấy MessageHeaders.ID làm business key

ID của Spring Message phục vụ messaging; khi message được tạo lại qua Transformer, Gateway hoặc adapter, ID kỹ thuật có thể thay đổi. EventId phải nhận diện **một sự kiện logic** qua các lần gửi và retry.

Các trường có mục đích khác nhau:

- **eventId**: một sự kiện logic, ổn định qua retry/redelivery.
- **orderId/shipmentId**: một thực thể nghiệp vụ có thể có nhiều sự kiện.
- **logicalStepId**: một tác động như reserve-inventory hoặc charge-payment.
- **routingSlipIndex**: vị trí điều hướng, không phải business key.
- **attemptId**: một lần thử; thay đổi qua retry, không phù hợp để chặn lặp effect.
- **correlationId**: liên kết một nhóm messages (Splitter/Aggregator), không tự chứng minh đã xử lý.

### 4.2. Nếu cùng step được gọi nhiều lần hợp lệ

Một strategy có thể lặp bước xử lý cho nhiều line item, ví dụ tính phí cho ba kiện hàng. Khi đó key có thể cần:

~~~text
tenantId : eventId : logicalStepId : packageId
~~~

Đừng thêm **attemptId** vào key: làm vậy mỗi retry có key mới và vô hiệu hóa chống trùng. Cũng không nên dùng **routingSlipIndex** thay cho packageId khi strategy có thể lặp tại cùng index.

### 4.3. Flow version và thay đổi đường đi

Khi nâng cấp flow từ:

~~~text
validate -> reserve -> charge -> notify
~~~

sang:

~~~text
validate -> reserve -> fraudCheck -> charge -> notify
~~~

cần quyết định event cũ sẽ dùng **đường đi cũ** hay **chuyển sang đường mới**. Khi resume với version mới, có thể xuất hiện một bước chưa từng chạy. Nếu thêm flowVersion vào mọi idempotency key một cách máy móc, các bước reserve/charge đã hoàn tất ở version cũ có thể được xử lý lại.

**Nguyên tắc:** chọn **logicalStepId ổn định theo tác động nghiệp vụ**. Chỉ tạo effect identity mới khi thực sự muốn nghiệp vụ chạy một tác động mới. Lưu flowVersion riêng để phục vụ migration và audit, không mặc định coi nâng version là lý do cho phép lặp mọi side effect.

## 5. Java DSL: xây dựng routing slip có các bước rõ ràng

Spring Integration Java DSL hỗ trợ thêm routing slip bằng **HeaderEnricherSpec.routingSlip**. Ví dụ sau tạo một routing slip cố định cho một loại shipment. Chúng ta dùng **DirectChannel** để dễ quan sát, còn trạng thái idempotency của các service sẽ được bàn ở phần tiếp theo.

### 5.1. Hợp đồng dữ liệu và các service

~~~java
import java.math.BigDecimal;

record ShipmentRequested(
        String eventId,
        String tenantId,
        String orderId,
        String sku,
        int quantity,
        BigDecimal totalVnd) {}

interface ShipmentValidation {
    void validate(ShipmentRequested event);
}

interface InventoryReservation {
    void reserveOnce(ShipmentRequested event);
}

interface PaymentCharging {
    void chargeOnce(ShipmentRequested event);
}

interface CustomerNotification {
    void notifyOnce(ShipmentRequested event);
}
~~~

Hậu tố **Once** trong tên phương thức thể hiện **hợp đồng cần có**, không tự chứng minh cài đặt đã idempotent. Phần service phải được xây dựng và kiểm thử theo khóa hợp lệ, đặc biệt với những side effect ở database hoặc hệ thống ngoài.

### 5.2. Khai báo routing slip và các channel

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class ShipmentRoutingSlipConfig {

    @Bean
    MessageChannel shipmentInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel validateChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel reserveChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel chargeChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel notifyChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow startShipmentSlip() {
        return IntegrationFlow.from("shipmentInput")
                .enrichHeaders(headers -> headers.routingSlip(
                        true,  // Ghi đè slip cũ tại ingress đáng tin cậy.
                        "validateChannel",
                        "reserveChannel",
                        "chargeChannel",
                        "notifyChannel"))
                .get();
    }

    @Bean
    IntegrationFlow validateShipment(ShipmentValidation validation) {
        return IntegrationFlow.from("validateChannel")
                .handle(ShipmentRequested.class, (event, headers) -> {
                    validation.validate(event);
                    return event;  // Có reply để tiếp tục routing slip.
                })
                .get();
    }

    @Bean
    IntegrationFlow reserveInventory(InventoryReservation inventory) {
        return IntegrationFlow.from("reserveChannel")
                .handle(ShipmentRequested.class, (event, headers) -> {
                    inventory.reserveOnce(event);
                    return event;
                })
                .get();
    }

    @Bean
    IntegrationFlow chargePayment(PaymentCharging payments) {
        return IntegrationFlow.from("chargeChannel")
                .handle(ShipmentRequested.class, (event, headers) -> {
                    payments.chargeOnce(event);
                    return event;
                })
                .get();
    }

    @Bean
    IntegrationFlow notifyCustomer(CustomerNotification notifications) {
        return IntegrationFlow.from("notifyChannel")
                .handle(ShipmentRequested.class, (event, headers) -> {
                    notifications.notifyOnce(event);
                    return null; // Bước cuối: không phát reply mới.
                })
                .get();
    }
}
~~~

**Lưu ý kỹ thuật:**

1. Header Enricher tạo routing slip gồm các tên channel. Với Java DSL phiên bản hỗ trợ, tham số **true** của routingSlip(true, ...) yêu cầu ghi đè header routing slip đã tồn tại.
2. Các Service Activator ở validate/reserve/charge trả về payload để tạo reply; chúng **không cấu hình outputChannel** tường minh, nhờ đó routing slip được tham khảo.
3. Notify là bước cuối không cần reply trong ví dụ one-way; nếu Gateway cần trả kết quả, phải thiết kế request/reply và xử lý replyChannel khi slip đã hết. Không để bước giữa trả null khi còn các bước bắt buộc phải chạy.
4. Đây là **flow minh họa**: ứng dụng cần bean triển khai bốn interface, validate input, cấu hình transaction và chiến lược phục hồi.
5. Nếu gắn channel tường minh ngay sau một handler, flow có thể đi theo outputChannel đó thay vì đường routing slip. Cần kiểm thử topology thực, không chỉ nhìn vào danh sách tên channel trong header.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant I as Header Enricher
    participant V as Validate
    participant R as Reserve
    participant C as Charge
    participant N as Notify
    P->>I: ShipmentRequested
    I->>V: Slip entry 0
    V-->>R: Reply, entry 1
    R-->>C: Reply, entry 2
    C-->>N: Reply, entry 3
    N-->>P: Không reply, one-way hoàn tất
~~~

### 5.3. Vì sao phải đặt đường đi ở ingress đáng tin?

Routing slip chứa tên channel hoặc strategy, nên nó mang khả năng ảnh hưởng **topology xử lý**. Không chấp nhận path do client HTTP/broker không tin cậy cung cấp mà không xác minh. Một người gửi có thể đưa channel nhạy cảm, vòng lặp hoặc biểu thức ngoài ý định vào path nếu hệ thống sao chép nguyên header bên ngoài.

Ở trust boundary:

- Xác thực producer, tenant và quyền gửi sự kiện.
- Chuẩn hóa/validate payload và gắn eventId ổn định do hệ thống quản lý.
- Tạo routing slip từ **allowlist channel/strategy nội bộ**.
- Giới hạn chiều dài path, số chặng và các lựa chọn động.
- Quản lý replyChannel, errorChannel và correlation của message theo nhu cầu thực tế.

**Ghi đè routingSlip** chỉ xử lý một header; nó không tự loại bỏ mọi header độc hại khác. Khi tạo lại message tại ingress, cân nhắc allowlist các header được giữ.

## 6. Đặt điểm chống trùng ở đúng nơi

Trong một routing slip có nhiều step, đặt dedup ở ingress theo eventId có thể làm mất phần việc còn dang dở. Ví dụ lần đầu đã reserve hàng nhưng charge chưa hoàn tất; nếu ingress thấy eventId từng được tiếp nhận rồi **bỏ toàn bộ lần retry**, charge và notify sẽ không bao giờ có cơ hội tiếp tục.

~~~mermaid
flowchart TD
    E["Replay evt-301"] --> D{"Dedup toàn luồng?"}
    D -->|"Đã thấy evt-301"| LOST["Bỏ luôn: charge chưa xong"]
    E --> STEP{"Dedup theo logical step"}
    STEP --> V["Validate chạy lại an toàn"]
    STEP --> R["Reserve đã completed: skip effect"]
    STEP --> C["Charge chưa completed: thực hiện"]
    STEP --> N["Notify khi charge thành công"]
~~~

Một thiết kế thực tế gồm hai lớp khác nhau:

1. **Tầng truyền và điều phối**: biết message đang ở bước nào, còn chặng nào chưa hoàn tất; có cơ chế retry/replay đúng chỗ.
2. **Tầng tác động nghiệp vụ**: service tại mỗi chặng thực thi theo hợp đồng idempotent, nhận diện tác động đã hoàn tất hoặc chưa rõ kết quả.

Không đánh đồng “message đã từng đi qua bước” với “side effect đã commit”. Một log ghi “đã gọi charge” chỉ chứng minh có attempt, không chứng minh thanh toán đã thành công.

### 6.1. Bảng trạng thái xử lý từng bước

Một mô hình tối thiểu:

| Trạng thái | Ý nghĩa | Cách xử lý khi retry |
| --- | --- | --- |
| **PENDING** | Chưa có attempt, hoặc đã chuẩn bị công việc | Có thể bắt đầu xử lý |
| **PROCESSING** | Đang có attempt được claim | Kiểm tra lease/lock, không chạy song song vô hạn |
| **COMPLETED** | Effect đã commit hoặc có xác nhận hợp lệ | Bỏ qua effect, tạo reply để slip tiếp tục |
| **FAILED_RETRYABLE** | Lỗi tạm thời, chưa hoàn tất | Retry có giới hạn/backoff |
| **FAILED_FINAL** | Không thể xử lý tự động | Quarantine/DLQ và can thiệp |
| **UNKNOWN** | Không biết external effect đã xảy ra chưa | Đối soát hoặc retry với idempotency key |

**COMPLETED** phải mang ý nghĩa nghiệp vụ được định nghĩa rõ. Một HTTP 202 Accepted có thể chỉ là downstream đã nhận việc, không phải đã thu tiền; trạng thái của step phải phản ánh đúng hợp đồng với API bên ngoài.

## 7. Ví dụ SQL: hiệu ứng trong cùng database

Với bước reserveInventory mà cả bản ghi chống trùng và việc trừ hàng tồn đều dùng **một database/transaction manager**, có thể commit nguyên tử bằng unique constraint và transaction.

~~~sql
CREATE TABLE routing_step_execution (
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    logical_step_id VARCHAR(80) NOT NULL,
    status VARCHAR(24) NOT NULL,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, event_id, logical_step_id)
);

CREATE TABLE stock_balance (
    tenant_id VARCHAR(80) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    available_quantity INTEGER NOT NULL CHECK (available_quantity >= 0),
    PRIMARY KEY (tenant_id, sku)
);
~~~

Ví dụ cài đặt với Spring JDBC, PostgreSQL:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class JdbcInventoryReservation implements InventoryReservation {
    private final JdbcTemplate jdbc;

    JdbcInventoryReservation(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional
    public void reserveOnce(ShipmentRequested event) {
        String step = "reserve-inventory";

        // PostgreSQL: chỉ một attempt có thể insert khóa mới.
        int claimed = jdbc.update("""
                INSERT INTO routing_step_execution
                    (tenant_id, event_id, logical_step_id, status)
                VALUES (?, ?, ?, 'PROCESSING')
                ON CONFLICT DO NOTHING
                """,
                event.tenantId(), event.eventId(), step);

        if (claimed == 0) {
            // Chỉ được skip an toàn nếu entry tồn tại đã COMPLETED.
            String status = jdbc.queryForObject("""
                    SELECT status FROM routing_step_execution
                    WHERE tenant_id = ? AND event_id = ?
                      AND logical_step_id = ?
                    """,
                    String.class,
                    event.tenantId(), event.eventId(), step);
            if ("COMPLETED".equals(status)) {
                return;
            }
            throw new IllegalStateException(
                    "Step chưa hoàn tất; phải retry có kiểm soát");
        }

        int updated = jdbc.update("""
                UPDATE stock_balance
                   SET available_quantity = available_quantity - ?
                 WHERE tenant_id = ? AND sku = ?
                   AND available_quantity >= ?
                """,
                event.quantity(), event.tenantId(),
                event.sku(), event.quantity());

        if (updated != 1) {
            throw new IllegalStateException("Không đủ hàng hoặc SKU lỗi");
        }

        jdbc.update("""
                UPDATE routing_step_execution
                   SET status = 'COMPLETED',
                       completed_at = CURRENT_TIMESTAMP
                 WHERE tenant_id = ? AND event_id = ?
                   AND logical_step_id = ?
                """,
                event.tenantId(), event.eventId(), step);
    }
}
~~~

**Tiền điều kiện:** event đã được validate (eventId/tenantId/sku không rỗng, quantity dương, tenantId từ nguồn xác thực). Hai bảng và JdbcTemplate phải cùng database, cùng transaction manager; method được gọi qua Spring proxy để **@Transactional** thực sự có tác dụng.

### Tại sao pattern này có ích?

Khi các thao tác ở trên nằm trong một transaction:

1. Attempt đầu **insert key** và cập nhật tồn kho.
2. Nếu lỗi trước commit, **insert key lẫn thay đổi stock đều rollback**.
3. Nếu commit thành công, một lần retry gặp key đã tồn tại, đọc **COMPLETED** và **không trừ kho lần hai**.
4. Hai attempt đồng thời tranh cùng khóa chịu sự điều phối của **primary key và transaction/locking**, không dựa trên thao tác check-then-insert không atomic.

Khi có giao dịch còn đang tiến hành, mức chờ hoặc hành vi của transaction thứ hai phụ thuộc isolation/locking. Một entry tồn tại nhưng chưa COMPLETED phải được xử lý như trạng thái cần điều tra/retry, không coi là đã thành công.

**Ranh giới của bảo đảm:** pattern trên giúp tránh trừ stock trùng **trong một database** khi cùng một eventId/stepId được dùng đúng. Nó không đảm bảo chargePayment hay email đã được gửi chỉ một lần. Các API bên ngoài đòi hỏi chiến lược riêng.

### 7.1. Vì sao không chỉ dùng Set hoặc MetadataStore in-memory?

~~~java
// Phản ví dụ: claim trước khi side effect thực hiện xong.
if (seen.add(event.eventId() + ":charge-payment")) {
    paymentClient.charge(event);
}
~~~

Nếu seen.add thành công rồi paymentClient.charge thất bại, retry có thể bị skip vĩnh viễn. Nếu ứng dụng restart, Set mất dữ liệu và charge có thể lặp. Khi chạy nhiều instance, từng JVM còn có Set riêng.

Một **ConcurrentMetadataStore** hỗ trợ thao tác atomic như putIfAbsent, nhưng nếu việc ghi claim và effect không cùng một transaction, chỉ atomic claim chưa đủ để tạo exactly-once effect. Điều tương tự đúng với cache Redis/DB nếu thiết kế sai trạng thái hoàn tất.

## 8. Chặng gọi HTTP: đã thu tiền nhưng mất phản hồi

Giả sử chargePayment gửi request tới payment provider. Provider **đã thu tiền**, nhưng kết nối bị cắt trước khi ứng dụng nhận HTTP response. Từ phía client, kết quả của chặng là **UNKNOWN**.

~~~mermaid
sequenceDiagram
    participant W as Workflow worker
    participant P as Payment provider
    participant S as Step store
    W->>P: POST charge, key=tenant-A:evt-301:charge-payment
    P->>P: Đã thu tiền
    P--xW: Mất response
    W->>S: Lưu trạng thái UNKNOWN / retryable
    W->>P: Tra cứu theo cùng key hoặc retry idempotent
    P-->>W: Kết quả charge đã có
    W->>S: Đánh dấu COMPLETED
~~~

**Không thể quyết định một request đã thất bại chỉ từ việc timeout.** Nếu gửi lại request với một **idempotency key khác**, provider có thể coi đó là yêu cầu thanh toán mới.

### 8.1. Gửi cùng khóa cho cùng một tác động

~~~java
final class ExternalChargeKey {
    static String forEvent(ShipmentRequested event) {
        return event.tenantId()
                + ":" + event.eventId()
                + ":charge-payment";
    }
}

interface PaymentProviderPort {
    // Ví dụ hợp đồng adapter: provider nhận một idempotency key.
    ChargeResult charge(ShipmentRequested event, String key);

    // Nếu provider có khả năng tra cứu bằng cùng key.
    ChargeResult findByIdempotencyKey(String key);
}

record ChargeResult(boolean succeeded, boolean unknown) {}
~~~

Đây là **interface mô tả hợp đồng**, không phải API có sẵn của Spring Integration. Mỗi provider có chính sách lưu khóa, thời hạn TTL, scope, response caching và retry riêng; cần đọc tài liệu của provider và kiểm thử khi có timeout.

Một chiến lược điều phối:

1. Với key đã **COMPLETED**, bỏ qua charge và tiếp tục slip.
2. Với key **PENDING/FAILED_RETRYABLE**, gọi charge bằng **cùng key**.
3. Với trạng thái **UNKNOWN**, tra cứu kết quả theo key hoặc đối soát; chỉ retry khi provider có semantics idempotent phù hợp.
4. Khi provider xác nhận thành công, lưu COMPLETED trước khi đánh dấu chặng nghiệp vụ có thể được tiếp tục.
5. Khi có lỗi không thể phục hồi, chuyển workflow sang trạng thái cần can thiệp, không tạo vô hạn những request mới.

**Điểm không thể loại trừ hoàn toàn:** nếu provider không hỗ trợ idempotency key hoặc truy vấn kết quả, ứng dụng có thể không phân biệt được “chưa thu tiền” với “đã thu tiền nhưng response mất”. Khi đó cần reconciliation, compensating action nếu phù hợp hoặc chính sách chấp nhận rủi ro rõ ràng.

## 9. Outbox và checkpoint đáng tin khi flow phải sống qua restart

Routing slip mang path/index trong **message hiện tại**; nó không tự lưu bền toàn bộ lịch sử bước vào database. Nếu cần tiến trình tồn tại sau khi ứng dụng restart, có thể xây dựng bảng **workflow_instance**, **routing_step_execution** và **outbox**.

Ví dụ mô hình:

~~~sql
CREATE TABLE workflow_instance (
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    flow_version VARCHAR(32) NOT NULL,
    state VARCHAR(24) NOT NULL,
    next_logical_step VARCHAR(80),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, event_id)
);

CREATE TABLE workflow_outbox (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    target_step VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL,
    delivered_at TIMESTAMPTZ,
    UNIQUE (tenant_id, event_id, target_step)
);
~~~

Giả sử reserveInventory là thao tác trong cùng database:

~~~mermaid
flowchart LR
    A["Reserve inventory"] --> TX["DB transaction"]
    TX --> E["Trừ tồn kho"]
    TX --> ST["Step COMPLETED"]
    TX --> OB["Outbox: charge-payment"]
    OB --> D["Dispatcher"]
    D --> C["Charge consumer<br/>cùng idempotency key"]
~~~

Khi reserve hoàn tất:

- Trừ tồn kho, đánh dấu reserve completed và ghi **outbox cho bước charge** trong **cùng transaction**.
- Dispatcher lấy outbox rồi gửi message đến chặng charge; nếu gửi lặp, consumer charge dùng **cùng khóa idempotency**.
- Một broker/queue bền có thể hỗ trợ redelivery khi consumer chết; ack phải được đặt tương ứng với ranh giới commit.
- Workflow có thể **tái dựng routing slip hoặc chọn tiếp từ next_logical_step** dựa trên trạng thái đã lưu bền, không dựa duy nhất vào header/index vừa nhận.

**Ví dụ chỉ là một phương án:** Spring Integration không tự cung cấp cho mọi routing slip một outbox/checkpoint transaction. Cần triển khai/cấu hình service, store, adapters, retry và monitoring tương ứng.

### 9.1. Ghi next step quá sớm sẽ bỏ sót side effect

Sai:

~~~text
UPDATE workflow_instance SET next_logical_step='notify-customer'
CALL paymentProvider.charge(...)
~~~

Nếu crash trước khi charge, resume từ notify sẽ **bỏ qua thu tiền**. Đúng hơn, trạng thái tiến độ phải phản ánh **đã xác nhận charge** hay chưa. Với API ngoài, có thể cần trạng thái UNKNOWN và một bước reconcile trước khi chuyển sang notify.

### 9.2. Ghi next step quá muộn có thể lặp effect

Sai theo chiều ngược:

~~~text
CALL paymentProvider.charge(...)  // thành công
PROCESS CRASH
UPDATE workflow_instance SET next_logical_step='notify-customer'
~~~

Sau restart, state vẫn ở charge, nên worker sẽ gọi lại. **Idempotency key ở payment provider** hoặc cơ chế đối soát giúp giữ hiệu ứng chỉ một lần dù attempt lặp.

### 9.3. Khả năng bền của routingSlip header

Tài liệu Spring Integration cảnh báo rằng khi routing slip đi qua **JMS/AMQP, persistent MessageStore hoặc ranh giới JVM**, không nên dùng **biểu thức SpEL inline** làm entry path theo cách khiến framework lưu một **ExpressionEvaluatingRoutingSlipRouteStrategy không Serializable** trong header.

Biện pháp:

- Dùng **tên bean RoutingSlipRouteStrategy đã đăng ký** thay vì inline expression cần giữ trong message phân tán.
- Dùng tên channel ổn định, có mapping/strategy được kiểm soát trong mỗi ứng dụng.
- Kiểm tra serialization, header mapper và tương thích phiên bản qua adapter/broker thực tế.
- Nếu nhiều service không chia sẻ cùng topology/channel names, dùng **workflow state/payload portable** thay vì gửi nguyên cấu trúc nội bộ của routing slip xuyên dịch vụ.

Việc header có thể serialize **không** bảo đảm mọi bước đã hoàn tất, cũng không thay thế idempotency.

## 10. Spring Integration Idempotent Receiver ở từng chặng

Spring Integration cung cấp **IdempotentReceiverInterceptor** và **MetadataStoreSelector** để hỗ trợ mẫu Idempotent Receiver. Đây là cơ chế ở **endpoint**, không phải một tùy chọn mặc định của routing slip.

MetadataStoreSelector có thể dùng một **ConcurrentMetadataStore** để claim key, ví dụ:

~~~java
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.messaging.Message;

// store phải do ứng dụng cung cấp với durability phù hợp.
MetadataStoreSelector selector = new MetadataStoreSelector(
        (Message<?> message) -> {
            ShipmentRequested event =
                    (ShipmentRequested) message.getPayload();
            return event.tenantId()
                    + ":" + event.eventId()
                    + ":reserve-inventory";
        },
        store);

IdempotentReceiverInterceptor advice =
        new IdempotentReceiverInterceptor(selector);

// Gắn advice vào endpoint reserveInventory theo cấu hình dự án.
// Khi cần drop duplicate, phải cấu hình discardChannel
// hoặc rejection policy rõ ràng, thay vì chỉ tạo advice.
~~~

Đây là mảnh cấu hình giải thích cơ chế; store và advice cần được khai báo/gắn vào endpoint bằng API tương ứng với phiên bản Spring Integration đang dùng.

### 10.1. Cơ chế mặc định không nhất thiết chặn duplicate

Theo tài liệu, nếu selector bác bỏ message, **IdempotentReceiverInterceptor** có thể gắn header **duplicateMessage=true** và vẫn chuyển message đến handler, trừ khi cấu hình **discardChannel** hoặc **throwExceptionOnRejection**.

Do đó, chỉ tạo interceptor không đồng nghĩa side effect sẽ tự được bỏ qua. Nếu chặng đang trả reply để routing slip tiếp tục, việc **loại hẳn duplicate trước handler** cũng cần cân nhắc: nó có thể khiến flow **dừng tại chặng đã xử lý**, thay vì bỏ qua side effect rồi **tiếp tục chặng chưa hoàn tất**.

Với routing slip có thể replay từ ingress, một thiết kế hợp lý cho bước đã COMPLETED thường là:

~~~java
ShipmentRequested processReserve(ShipmentRequested event) {
    // reserveOnce nhận biết completed và bỏ qua effect trùng.
    inventoryReservation.reserveOnce(event);

    // Dù đã completed ở lần trước, vẫn trả message
    // để routing slip tiếp tục chặng tiếp theo.
    return event;
}
~~~

**Điểm quan trọng:** tránh trừ kho lần hai **nhưng vẫn phát reply** để chặng charge hoặc notify còn thiếu được đi tiếp. Nếu chỉ dùng discardChannel=nullChannel tại reserve, lần replay từ đầu có thể dừng trước charge.

### 10.2. Claim key trước effect và lỗi sau claim

Nếu MetadataStoreSelector claim key trước khi handler gọi external service, một exception sau claim có thể khiến lần retry bị đánh dấu duplicate. Điều này là rủi ro **mất tác vụ** chứ không chỉ rủi ro trùng.

Giải pháp tùy nguồn side effect:

- **DB cùng transaction:** ghi idempotency record và effect atomically.
- **External API hỗ trợ key:** dùng cùng key trên mọi attempt, tra cứu khi kết quả unknown.
- **Workflow nhiều bước:** lưu step status, chỉ skip effect khi trạng thái xác nhận COMPLETED.
- **Distributed store:** kiểm tra atomicity, TTL, concurrency và cách phục hồi lock/claim.

### 10.3. Không dùng global dedup nếu chưa có trạng thái từng bước

Một chốt kiểm tra ngay trước header enricher kiểu “eventId đã thấy thì drop” có thể chặn hoàn toàn lần replay, trong khi reserve đã xong nhưng charge chưa chạy. Trừ khi toàn bộ tác vụ đã được **bàn giao bền** cho từng recipient/step hoặc có cơ chế resume độc lập, không xem global dedup là lời giải đầy đủ.

## 11. Retry, error channel và kiểm soát thứ tự

### 11.1. Lỗi đồng bộ và bất đồng bộ

| Ngữ cảnh | Hành vi lỗi thường gặp | Việc cần làm |
| --- | --- | --- |
| DirectChannel, handler sync | Exception có thể truyền về caller | Xác định transaction rollback và vị trí retry |
| ExecutorChannel | Handler chạy sau khi executor nhận việc | Error handler/flow riêng và bounded executor |
| QueueChannel + poller | Lỗi phát sinh khi consumer poll/handle | Retry/backoff, trạng thái step, DLQ |
| Broker/JMS/AMQP | Có ack/redelivery theo adapter và broker | Cam kết message đúng lúc effect đã được ghi |
| Request/reply Gateway | ReplyChannel điều hướng phản hồi khi slip hết | Timeout/error reply cần hợp đồng rõ |

Nếu routing slip có bước **reserve** và **charge** cùng DirectChannel đồng bộ, một exception ở charge có thể làm caller nghĩ toàn bộ quy trình thất bại. Điều đó **không chứng minh** reserve đã rollback, nhất là nếu reserve đã commit DB riêng hoặc external effect đã xảy ra.

### 11.2. Retry phải có giới hạn và nhận diện lỗi

| Loại lỗi | Có retry ngay được không? | Hành động ưu tiên |
| --- | --- | --- |
| Input không hợp lệ | Thường không | Từ chối trước side effect |
| Không có channel/bean trong slip | Không, nếu topology chưa sửa | Fail fast, sửa cấu hình |
| Thiếu hàng | Tùy nghiệp vụ | Business rejection hoặc chờ restock có workflow riêng |
| DB deadlock/timeout | Có thể | Retry có backoff với unique key |
| Payment provider timeout | Chỉ an toàn nếu có idempotency/reconcile | Giữ trạng thái UNKNOWN, dùng cùng key |
| Email provider 429 | Có thể | Backoff, rate limit, cùng idempotency key nếu hỗ trợ |
| Strategy lặp path vô hạn | Không nên retry mù | Giới hạn số hop/iteration, cảnh báo |

Không để retry tự do tạo vòng lặp **RoutingSlipRouteStrategy → cùng channel** không giới hạn. Nếu workflow chủ động lặp bước theo từng item, cần định nghĩa điều kiện kết thúc và số lần tối đa.

### 11.3. Correlation không đồng nghĩa idempotency

Khi một routing slip được dùng cùng **Splitter/Aggregator**, correlationId/sequenceSize giúp quản lý nhóm các message con. Chúng không tự ngăn việc một side effect bị chạy lại.

Ví dụ:

~~~text
eventId = evt-301
correlationId = shipment-301
stepId = reserve-inventory
itemId = SKU-9
~~~

Khóa idempotency có thể là tenantId + eventId + stepId + itemId. CorrelationId dùng để **gắn các phần tử của cùng shipment**, không nên thay eventId nếu một shipment phát nhiều event và các tác vụ hợp lệ khác nhau.

Nếu một strategy đọc reply để chọn chặng tiếp theo, hãy kiểm soát kiểu reply. Tài liệu Spring Integration lưu ý reply có thể là Message, builder hoặc object domain tùy handler; không được mặc định strategy luôn đọc được reply.payload và reply.headers trong mọi trường hợp.

## 12. Integration test: replay chạy lại đường đi, không tự idempotent

Để hiểu cơ chế thực tế, một kiểm thử cần xác nhận:

1. Routing slip dẫn message tới đúng các channel theo thứ tự trong một lần gửi đồng bộ.
2. Gửi **cùng sự kiện** vào ingress lần thứ hai khiến những handler có thể chạy lại.
3. Lỗi ở chặng charge có thể dừng lần gửi trước khi tới notify.
4. Lần gửi lại từ ingress sẽ gọi lại các chặng đầu, trừ khi chúng tự kiểm soát idempotency.

Ví dụ sau chạy với **JUnit 5, spring-test và Spring Integration Java DSL**. Các handler chỉ ghi nhận tên bước, không có side effect thực.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(RoutingSlipReplayTest.Config.class)
class RoutingSlipReplayTest {

    static final class Probe {
        final List<String> visits = new CopyOnWriteArrayList<>();
        volatile boolean failCharge;
    }

    @Configuration
    @EnableIntegration
    static class Config {

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        MessageChannel ingress() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel verifyStep() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel inventoryStep() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel paymentStep() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel notificationStep() {
            return new DirectChannel();
        }

        @Bean
        IntegrationFlow slipIngress() {
            return IntegrationFlow.from("ingress")
                    .enrichHeaders(h -> h.routingSlip(true,
                            "verifyStep",
                            "inventoryStep",
                            "paymentStep",
                            "notificationStep"))
                    .get();
        }

        @Bean
        IntegrationFlow verifyFlow(Probe probe) {
            return IntegrationFlow.from("verifyStep")
                    .handle(ShipmentRequested.class, (event, headers) -> {
                        probe.visits.add("verify");
                        return event; // Tạo reply để lấy entry kế tiếp.
                    })
                    .get();
        }

        @Bean
        IntegrationFlow inventoryFlow(Probe probe) {
            return IntegrationFlow.from("inventoryStep")
                    .handle(ShipmentRequested.class, (event, headers) -> {
                        probe.visits.add("inventory");
                        return event;
                    })
                    .get();
        }

        @Bean
        IntegrationFlow paymentFlow(Probe probe) {
            return IntegrationFlow.from("paymentStep")
                    .handle(ShipmentRequested.class, (event, headers) -> {
                        probe.visits.add("payment");
                        if (probe.failCharge) {
                            throw new IllegalStateException("Payment timeout");
                        }
                        return event;
                    })
                    .get();
        }

        @Bean
        IntegrationFlow notificationFlow(Probe probe) {
            return IntegrationFlow.from("notificationStep")
                    .handle(ShipmentRequested.class, (event, headers) -> {
                        probe.visits.add("notification");
                        return null; // Kết thúc flow one-way.
                    })
                    .get();
        }
    }

    @Autowired
    @Qualifier("ingress")
    MessageChannel input;

    @Autowired
    Probe probe;

    @BeforeEach
    void clear() {
        probe.visits.clear();
        probe.failCharge = false;
    }

    private ShipmentRequested event() {
        return new ShipmentRequested(
                "evt-301", "tenant-A", "ORD-301",
                "SKU-9", 2, new BigDecimal("240000"));
    }

    @Test
    void aSingleSendVisitsEachStepInOrder() {
        assertTrue(input.send(
                MessageBuilder.withPayload(event()).build()));

        assertEquals(
                List.of("verify", "inventory", "payment", "notification"),
                probe.visits);
    }

    @Test
    void replayingAtIngressRepeatsHandlersWithoutDedup() {
        assertTrue(input.send(
                MessageBuilder.withPayload(event()).build()));
        assertTrue(input.send(
                MessageBuilder.withPayload(event()).build()));

        assertEquals(List.of(
                "verify", "inventory", "payment", "notification",
                "verify", "inventory", "payment", "notification"),
                probe.visits);
    }

    @Test
    void aFailedStepStopsThisAttemptButReplayStartsAgain() {
        probe.failCharge = true;

        assertThrows(RuntimeException.class,
                () -> input.send(
                        MessageBuilder.withPayload(event()).build()));
        assertEquals(
                List.of("verify", "inventory", "payment"),
                probe.visits);

        probe.failCharge = false;
        assertTrue(input.send(
                MessageBuilder.withPayload(event()).build()));

        assertEquals(List.of(
                "verify", "inventory", "payment",
                "verify", "inventory", "payment", "notification"),
                probe.visits);
    }
}
~~~

Các test dùng DirectChannel đồng bộ, nên có thể quan sát thứ tự ngay sau send(). Nếu chuyển sang ExecutorChannel, QueueChannel hoặc adapter broker, không được dùng kết quả của test đồng bộ để suy ra thứ tự hoàn tất; cần CountDownLatch, timeout hoặc công cụ kiểm thử tích hợp thích hợp.

**Chú ý:** test cuối chứng minh chặng trước bị gọi lại; nó **không** cố ý gắn idempotency cho các handler. Trong hệ thống thực, inventory.reserveOnce sẽ bỏ qua side effect đã COMPLETED nhưng vẫn **trả reply** để slip tiếp tục tới charge và notify.

## 13. Kiểm thử idempotency khi có crash

Một lớp kiểm thử độc lập cần bảo vệ các effect. Không chỉ assert rằng service được gọi một lần trong happy path.

### 13.1. Ma trận lỗi cần có

| Thời điểm lỗi | Trạng thái có thể quan sát | Kết quả retry cần đạt |
| --- | --- | --- |
| Trước validate | Chưa có effect | Chạy lại bình thường |
| Sau validate, trước reserve | Chưa có effect | Validate lại, reserve một lần |
| Reserve DB lỗi trước commit | Transaction rollback | Có thể reserve lại thành công |
| Reserve DB commit, trước khi chuyển sang charge | Reserve COMPLETED | Skip effect reserve, vẫn tiếp tục charge |
| Payment chưa nhận request | Chưa charge | Retry cùng idempotency key |
| Payment đã thu nhưng response mất | UNKNOWN | Tra cứu hoặc retry idempotent, không thu lần hai |
| Đã notify, trước khi ack | Email có thể đã gửi | Provider idempotency/đối soát |
| Retry từ snapshot có index cũ | Các chặng cũ có thể được gọi | Effect completed không chạy lặp |
| Retry từ snapshot có index mới quá sớm | Có thể bỏ sót effect | Xác minh step state, không tin index một mình |
| Hai worker cùng claim một step | Race condition | Một effect được commit, attempt khác không ghi trùng |
| Restart ứng dụng | Metadata in-memory mất | Store bền phục hồi đúng trạng thái |
| Flow version thay đổi | Path và step mapping khác | Migration/replay policy rõ, không tự lặp effect |

### 13.2. Một unit test về khóa của từng bước

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class StepKeyTest {
    static String key(ShipmentRequested e, String step) {
        return e.tenantId() + ":" + e.eventId() + ":" + step;
    }

    @Test
    void aRetryKeepsTheSameKeyButStepsHaveDifferentKeys() {
        ShipmentRequested original = new ShipmentRequested(
                "evt-301", "tenant-A", "ORD-301",
                "SKU-9", 2, new BigDecimal("240000"));
        ShipmentRequested replayed = new ShipmentRequested(
                "evt-301", "tenant-A", "ORD-301",
                "SKU-9", 2, new BigDecimal("240000"));

        assertEquals(
                key(original, "charge-payment"),
                key(replayed, "charge-payment"));
        assertNotEquals(
                key(original, "reserve-inventory"),
                key(replayed, "charge-payment"));
    }
}
~~~

Test này chỉ kiểm tra **hợp đồng identity**. Để kiểm thử dedup thực, cần dùng database có unique constraint hoặc MetadataStore thực và chạy các ca concurrent + rollback.

### 13.3. Kiểm thử transaction DB

Một bài test integration với PostgreSQL/Testcontainers hoặc DB test phù hợp nên làm:

1. Khởi tạo stock của tenant-A, SKU-9 là 10.
2. Gửi evt-301 tới reserveInventory; đợi commit.
3. Gửi lại evt-301 với cùng tenant/event/step; stock phải vẫn là 8, không thành 6.
4. Gây exception **sau khi ghi step claim nhưng trước khi trừ stock**, xác minh transaction rollback.
5. Retry sau rollback phải có thể reserve thành công.
6. Cho hai worker xử lý cùng khóa đồng thời; kiểm tra chỉ có một transaction commit effect.

Đồng thời xác minh chính sách dữ liệu không hợp lệ: quantity âm hoặc 0 phải bị từ chối **trước** khi ghi claim; không cho client chọn tenantId khác bằng cách tự sửa header/payload.

### 13.4. Kiểm thử thanh toán bị mất response

Fake PaymentProviderPort nên mô phỏng: **ghi nhận charge thành công, sau đó ném lỗi mạng cho caller**. Retry cùng idempotency key phải trả về kết quả charge cũ, không tạo charge thứ hai. Nếu provider không hỗ trợ key, test phải biểu diễn trạng thái UNKNOWN và tuyến đối soát thay vì tự tuyên bố charge thất bại.

### 13.5. Kiểm thử replay từ checkpoint

Tạo một workflow có trạng thái:

~~~text
evt-301:
  validate = COMPLETED
  reserve-inventory = COMPLETED
  charge-payment = UNKNOWN
  notify-customer = PENDING
~~~

Khi khôi phục:

- Không giảm stock thêm lần nữa.
- Không cho notify chạy trước khi charge được xác nhận thành công.
- Đối soát charge theo cùng idempotency key.
- Khi charge thành công, mới đánh dấu charge COMPLETED và tiếp tục notify.

Nếu message được tạo lại với routing slip path từ đầu, service ở validate/reserve phải **đủ an toàn để chạy lại**. Nếu hệ thống resume trực tiếp ở charge, điều phối phải chứng minh các điều kiện tiên quyết đã được đáp ứng qua trạng thái bền.

## 14. Quan sát từng chặng và phát hiện duplicate

Trong hệ thống nhiều step, việc log một lần gửi message thành công không đủ. Nên quan sát cả **routing** lẫn **effect status**:

| Metric/log | Ý nghĩa |
| --- | --- |
| workflow_started_total | Số lần logical workflow bắt đầu |
| workflow_replay_attempts_total | Số lần event được phát lại |
| step_attempts_total{step} | Số lần chặng được gọi |
| step_completed_total{step} | Số effect được xác nhận hoàn tất |
| step_idempotent_skips_total{step} | Số attempt skip effect đã hoàn tất |
| step_unknown_total{step} | Số effect chưa xác định kết quả |
| step_retry_total{step} | Số lần retry |
| workflow_outbox_pending_total | Số tác vụ cần được chuyển đi |
| workflow_dead_letter_total | Số tác vụ phải can thiệp thủ công |
| workflow_replay_age_seconds | Thời gian event chờ phục hồi |

Không sử dụng eventId, orderId hoặc tenantId có nhiều giá trị làm **metric label** vì cardinality sẽ tăng không giới hạn. Dùng log/tracing có kiểm soát truy cập, ẩn dữ liệu nhạy cảm để tra cứu theo eventId. Các header như traceId, businessCorrelationId và routingSlip giúp lần theo đường đi nhưng không tự đảm bảo xử lý đúng một lần.

### Ba câu hỏi cần trả lời khi điều tra

1. **Một event đi đâu?** Xác định flowVersion, path và chặng hiện tại từ telemetry, đừng chỉ tin một header cũ.
2. **Chặng nào đã thật sự hoàn tất?** Đối chiếu step status, transaction commit, provider idempotency response.
3. **Có thể retry từ đâu?** Chọn resume checkpoint hoặc replay từ ingress, dựa trên idempotency của các step.

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Coi routingSlipIndex là bằng chứng step đã commit | Bỏ sót hoặc lặp effect khi crash | Lưu step status bền, xác nhận effect |
| Dùng MessageHeaders.ID làm dedup key | Retry qua adapter có thể nhận ID mới | Dùng eventId logic ổn định |
| Dedup toàn flow ở ingress rồi drop replay | Không thể khôi phục nhánh chưa hoàn tất | Dedup theo step, resume có state |
| Dùng eventId + stepId cho strategy cố ý chạy nhiều item | Bỏ nhầm các lần xử lý hợp lệ | Thêm itemId/iteration identity đúng nghĩa |
| Ghi claim trước effect nhưng không rollback khi effect lỗi | Retry bị chặn dù effect chưa thành công | Transaction hoặc status/lease/recovery |
| Tưởng routing slip tự tạo checkpoint bền | Crash có thể làm mất tiến độ | DB state, outbox/broker và replay policy |
| Cho handler giữa đường trả null | Routing slip có thể dừng trước chặng sau | Trả reply nếu cần tiếp tục |
| Cấu hình explicit outputChannel rồi đợi slip quyết định | Message không đi theo path mong muốn | Thiết kế endpoint và kiểm thử wiring |
| Retry charge bằng idempotency key mới | Có thể bị thu tiền lần hai | Giữ key cho cùng logical effect |
| Retry cả slip khi notification lỗi | Reserve/charge bị gọi lại | Retry nhánh lỗi, service idempotent |
| Dùng SpEL inline slip qua broker phân tán | Có thể lỗi serialization | Strategy bean name, portable state |
| Để client cung cấp trực tiếp routingSlip header | Có thể route vào channel không cho phép | Tạo path ở trust boundary, allowlist |
| Tự động đưa flowVersion vào mọi effect key | Deploy phiên bản mới có thể lặp effect cũ | Giữ logicalStepId ổn định, migration rõ |
| Chỉ kiểm thử happy path một lần | Không phát hiện duplicate và crash window | Test replay, concurrent, restart, unknown |

## 16. Bài thực hành: xây dựng routing slip có thể chạy lại

Một hệ thống bán hàng xử lý **OrderAccepted(eventId, tenantId, orderId, totalVnd)** bằng đường đi:

~~~mermaid
flowchart LR
    I["Ingress"] --> V["Validate"]
    V --> S["Reserve stock"]
    S --> P["Capture payment"]
    P --> A["Create shipment"]
    A --> N["Notify customer"]
~~~

**Yêu cầu**

1. Sự kiện có eventId ổn định qua redelivery và tenantId từ nguồn xác thực.
2. Validate có thể chạy lại mà không tạo side effect.
3. Reserve stock không làm giảm tồn kho lần thứ hai khi cùng event chạy lại.
4. Payment provider nhận một idempotency key ổn định; timeout có thể dẫn đến trạng thái UNKNOWN và yêu cầu đối soát.
5. Create shipment có unique business operation hoặc idempotency ở dịch vụ đích.
6. Notify chỉ chạy sau khi các chặng bắt buộc đã thành công; bản replay không tự gửi thông báo lặp.
7. Workflow có thể restart và tiếp tục dựa trên trạng thái bền.

**Các bước thực hiện**

1. Định nghĩa record OrderAccepted và các port nghiệp vụ; validate trường bắt buộc.
2. Tạo routing slip bằng HeaderEnricherSpec.routingSlip với tên channel trong allowlist.
3. Đảm bảo handler giữa đường **trả reply** và không khai báo outputChannel làm bỏ qua slip.
4. Tạo bảng step_execution có unique key tenantId + eventId + logicalStepId.
5. Với reserve stock, dùng transaction gắn việc ghi trạng thái với cập nhật tồn kho.
6. Với capture payment, mô phỏng mất response sau khi provider đã xử lý; retry bằng cùng key.
7. Ghi trạng thái chặng và quyết định replay từ ingress hoặc resume từ checkpoint.
8. Viết test một lần gửi, gửi lặp, exception giữa đường, restart và hai worker đồng thời.
9. Thêm metrics step_attempts, step_idempotent_skips, step_unknown và workflow_replay_attempts.
10. Đề xuất cách đưa flow qua broker mà không serialize những RoutingSlipRouteStrategy inline phụ thuộc BeanFactory.

### Câu hỏi tự kiểm tra

1. Routing slip được tham khảo trong trường hợp endpoint có reply và outputChannel như thế nào?
2. routingSlipIndex có chứng minh charge-payment đã thành công hay không?
3. Vì sao một lỗi sau reserve có thể làm replay từ ingress trừ kho lần hai?
4. Tại sao chỉ lọc eventId toàn flow có thể gây mất chặng charge chưa hoàn tất?
5. Một strategy trả cùng channel nhiều lần có luôn là duplicate không?
6. Khóa idempotency nên đổi hay giữ nguyên qua retry?
7. Lỗi payment timeout có nghĩa provider chưa thu tiền không?
8. Khi nào có thể ghi idempotency record và effect trong cùng transaction?
9. Vì sao MetadataStoreSelector đơn lẻ có thể làm mất cơ hội retry sau lỗi?
10. Cần làm gì nếu cần replay một event sau khi nâng phiên bản routing slip?
11. Vì sao inline SpEL strategy có rủi ro khi message đi qua broker?
12. Nếu một duplicate bị discard trước bước reserve, chặng charge sẽ được thực hiện ra sao?

## 17. Checklist trước khi vận hành

- Đường đi routing slip đã được định nghĩa bằng **channel/strategy được phép**, không lấy trực tiếp từ dữ liệu chưa tin cậy.
- Endpoint trung gian có reply, và chỉ dùng outputChannel tường minh khi chủ động bỏ qua cơ chế slip.
- eventId và tenantId có nguồn gốc xác thực, giữ ổn định qua retry/redelivery.
- Mỗi chặng có logicalStepId và idempotency key đúng phạm vi tác động.
- Chặng lặp hợp lệ theo item/iteration có khóa riêng, không bị dedup nhầm.
- Không dùng chỉ số slip hoặc MessageHeaders.ID làm dấu commit nghiệp vụ.
- Với DB effect, unique constraint và transaction đảm bảo claim cùng effect được commit/rollback nhất quán.
- Với external effect, có idempotency key, reconciliation hoặc trạng thái UNKNOWN hợp lệ.
- Service đã hoàn tất vẫn **trả reply** khi replay cần tiếp tục bước kế tiếp.
- Có checkpoint/outbox/inbox hoặc cơ chế chuyển giao bền nếu workflow phải sống qua restart.
- Retry có giới hạn, backoff, error channel/DLQ và quyết định xử lý lỗi không thể phục hồi.
- Flow version được quản lý, không tự đổi effect identity khi nâng cấp đường đi.
- Header routingSlip qua broker được kiểm tra serialization và tương thích môi trường.
- Test bao phủ replay từ ingress, resume, partial failure, concurrency, timeout sau effect và restart.

**Kết luận:** Routing slip cho biết **đường đi kế tiếp**, còn idempotency cho biết **một tác động nghiệp vụ đã được thực hiện và có được phép lặp hay không**. Khi message chạy lại routing slip, mỗi chặng phải có identity, trạng thái hoàn tất và chính sách phục hồi độc lập. Chỉ kết hợp routing slip với transaction, idempotent consumer, outbox hoặc reconciliation theo đúng ranh giới hệ thống mới tránh được lỗi lặp side effect mà vẫn không bỏ sót các bước chưa hoàn tất.

## Tài liệu tham khảo

- [Spring Integration Reference — Routing Slip](https://docs.spring.io/spring-integration/reference/router/routing-slip.html): cơ chế path/index, AbstractMessageProducingHandler, strategy và replyChannel.
- [Spring Integration API — HeaderEnricherSpec](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/dsl/HeaderEnricherSpec.html): routingSlip path và tùy chọn overwrite header.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): IdempotentReceiverInterceptor và hành vi duplicate.
- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): ConcurrentMetadataStore, store in-memory và lưu bền.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): IntegrationFlow, Header Enricher, Service Activator.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): đồng bộ/bất đồng bộ, QueueChannel và xử lý errors.
