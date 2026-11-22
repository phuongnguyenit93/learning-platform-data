# Header enricher, content enricher và bổ sung metadata

## 1. Vì sao một integration flow cần enrichment?

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot được dùng để nối HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration. Một thông điệp đi vào hệ thống có thể chỉ chứa dữ liệu gốc của đối tác, trong khi các bước định tuyến, kiểm tra hợp đồng, ghi database hoặc gửi sự kiện cần thêm ngữ cảnh như tenant, phiên bản schema, khóa tương quan và thông tin khách hàng.

**Enrichment (bổ sung dữ liệu)** là mẫu thiết kế biến một message còn thiếu thông tin thành message đủ ngữ cảnh để xử lý tiếp, nhưng không nên làm mất ý nghĩa ban đầu của message. Trong chương **Định tuyến và biến đổi**, Spring Integration có hai cơ chế chính:

- **Header enricher**: bổ sung hoặc tính toán **metadata trong MessageHeaders**, trong khi payload vẫn mang dữ liệu nghiệp vụ ban đầu.
- **Content enricher / payload enricher**: bổ sung **trường trong payload** bằng giá trị cố định, biểu thức hoặc kết quả tra cứu từ một flow khác; cũng có thể bổ sung headers từ kết quả tra cứu.

Đây không chỉ là chuyện chọn API. Enrichment có thể ảnh hưởng đến **hợp đồng dữ liệu, độ trễ, transaction, idempotency, bảo mật, luồng lỗi và observability**. Nếu enrichment gọi HTTP hoặc database, một bước “biến đổi” đơn giản trong sơ đồ có thể trở thành nút thắt quan trọng nhất của flow.

Mục tiêu sau bài học:

1. Phân biệt **headers** và **payload**, cùng vai trò của metadata trong định tuyến.
2. Cấu hình **enrichHeaders** bằng Java DSL và giải thích overwrite, expression, function.
3. Cấu hình **content enricher** để tra cứu dữ liệu qua request/reply channel và gán thuộc tính trả về.
4. Chọn đúng giữa enricher, transformer, filter, router và service activator.
5. Thiết kế timeout, fallback, xử lý lỗi và quyền sở hữu dữ liệu khi enrichment gọi hệ thống bên ngoài.
6. Kiểm tra metadata qua các adapter, tránh phát tán thông tin nhạy cảm và bảo vệ khả năng replay.
7. Viết test chứng minh payload, headers, thứ tự xử lý và các trường hợp lỗi.

## 2. Message gồm payload và headers

Spring Messaging biểu diễn thông điệp qua **Message<T>**, gồm:

~~~java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
~~~

Đây là giao diện rút gọn nhằm diễn giải; phần import và API chi tiết nằm trong Spring Messaging.

**Payload** thường là nội dung nghiệp vụ: **OrderCreated**, JSON, byte[], DTO hoặc một lệnh cần xử lý. **Headers** là tập thuộc tính phụ trợ phục vụ vận chuyển, tương quan, định tuyến và kiểm soát flow.

Ví dụ:

~~~text
Message
├── Payload
│   ├── orderId       = "O-172"
│   ├── customerId    = "C-44"
│   ├── tenantId      = "shop-east"
│   ├── amount        = 560000
│   └── customer      = (chưa tra cứu)
└── Headers
    ├── id            = UUID do framework quản lý
    ├── timestamp     = mốc tạo message
    ├── sourceSystem  = "partner-api"
    ├── flowVersion   = "2"
    ├── correlationId = "req-9f1"
    └── contentType   = "application/json"
~~~

**MessageHeaders về cơ bản là immutable**: các thao tác “thay header” thường tạo một message mới hoặc một tập headers mới. Nhưng **đối tượng payload bên trong message có thể mutable**. Nếu content enricher sửa một JavaBean dùng chung ở nhiều nhánh, các nhánh có thể nhìn thấy thay đổi ngoài ý muốn.

### Khi nào một trường nên là header?

| Thông tin | Nơi thường phù hợp | Lý do |
| --- | --- | --- |
| orderId, customerId, lineItems, amount | **Payload** | Thuộc hợp đồng nghiệp vụ và có thể cần lưu trữ |
| sourceSystem, integrationFlow, schemaVersion | **Header** | Metadata cho adapter, định tuyến và xử lý |
| correlationId, trace context | **Header** | Liên kết bước xử lý và phản hồi |
| idempotencyKey | Header hoặc payload/record nghiệp vụ được định nghĩa rõ | Phải ổn định qua retry/replay và qua boundary |
| customerCreditLevel, customerAddress | **Payload** nếu downstream cần dùng nghiệp vụ | Dữ liệu được enrichment từ customer service |
| retryAttempt, deliveryCount | Header/context vận chuyển hoặc metric | Có thể do broker/adapter quản lý, không tự đồng nhất với retry nghiệp vụ |
| accessToken, password, API secret | Không tự động đính kèm vào message | Có rủi ro log, serialize, đưa sang broker hoặc người nhận khác |

**Không xem header là dữ liệu đáng tin chỉ vì nó nằm trong MessageHeaders.** Một header đến từ HTTP request, broker record hoặc đối tác bên ngoài có thể bị giả mạo. Metadata bảo mật như tenant/role cần được xác minh ở ranh giới tin cậy, không dùng giá trị không xác thực để quyết định truy cập dữ liệu.

## 3. Sơ đồ tổng thể: header rồi content enrichment

Giả sử hệ thống nhận một đơn hàng gọn từ đối tác. Flow cần thêm nhãn luồng và tìm hồ sơ khách hàng trước khi quyết định tuyến giao hàng:

~~~mermaid
flowchart TD
    A["HTTP / Kafka / AMQP inbound"] --> B["Deserialize, validate schema & tenant"]
    B --> C["Header enricher"]
    C --> D["Headers: sourceSystem, flowVersion, correlationId"]
    D --> E["Content enricher"]
    E --> F["Request: customerId"]
    F --> G["Customer lookup: DB/cache/HTTP"]
    G --> H["Reply: CustomerProfile"]
    H --> I["Payload: OrderDraft + customer"]
    I --> J{"Router theo customer tier/tenant"}
    J -->|"priority"| K["Priority processing"]
    J -->|"standard"| L["Standard processing"]
    F -.->|"timeout/error"| M["Retry / fallback / error flow"]
~~~

Trình tự có ý nghĩa:

1. **Validate và xác thực tenant** trước khi enrichment, tránh lookup dữ liệu của tenant khác.
2. **Enrich headers** trước để nhánh lookup và trace có metadata đã chuẩn hóa.
3. **Enrich payload** bằng một phản hồi có hợp đồng rõ, không nhét toàn bộ object nhạy cảm vào headers.
4. **Route** dựa trên trường đã được bổ sung hoặc metadata hợp lệ.
5. **Gắn xử lý lỗi ở đúng ranh giới** để không nhầm “không tìm thấy khách hàng” với “HTTP timeout”.

## 4. Header enricher trong Spring Integration

**HeaderEnricher** phù hợp khi muốn đặt nhiều headers mà không phải tự viết transformer chỉ để sửa MessageHeaders. Trong Java DSL, phương thức thông dụng là **enrichHeaders(...)**.

### 4.1. Dependency và cấu hình tối thiểu

Với dự án dùng Spring Boot parent hoặc BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

Một IntegrationFlow minh họa:

~~~java
@Configuration
public class OrderHeaderFlowConfiguration {

    @Bean
    IntegrationFlow orderHeaderFlow() {
        return IntegrationFlow.from("validatedOrders")
                .enrichHeaders(h -> h
                        .header("flowVersion", "2")
                        .header("sourceSystem", "order-connector")
                        .headerFunction("businessKey", message -> {
                            OrderDraft order = (OrderDraft) message.getPayload();
                            return order.getOrderId();
                        }))
                .channel("headerEnrichedOrders")
                .get();
    }
}
~~~

Các import Spring và lớp **OrderDraft** được lược bỏ; lớp này được định nghĩa ở phần sau. **validatedOrders** là channel đầu vào đã qua kiểm tra hợp đồng, còn **headerEnrichedOrders** là channel đầu ra. Các giá trị **flowVersion/sourceSystem** chỉ có thể tin cậy khi được gắn ở ranh giới do ứng dụng kiểm soát.

**header(name, value)** đặt giá trị tĩnh; **headerFunction(name, fn)** tính header từ message; cũng có thể dùng **headerExpression(name, spel)** nếu một biểu thức ngắn, dễ kiểm thử, là phù hợp:

~~~java
.enrichHeaders(h -> h
        .header("flowVersion", "2")
        .headerExpression("businessKey", "payload.orderId"))
~~~

Ở ví dụ expression, **payload** là đối tượng của message nguồn và **orderId** phải được truy cập được theo SpEL (getter/property). Biểu thức không biên dịch như Java lambda, vì vậy đổi tên thuộc tính có thể chỉ được phát hiện lúc chạy hoặc trong integration test.

### 4.2. Giữ hay ghi đè header đã tồn tại?

Spring Integration cho phép cấu hình **overwrite** của header enricher. Không nên mặc định rằng mọi header đều có thể bị ghi đè an toàn.

| Header | Chính sách đề xuất | Lý do |
| --- | --- | --- |
| **flowVersion** do service tạo | Có thể gắn/chuẩn hóa tường minh | Kiểm soát hợp đồng nội bộ |
| **sourceSystem** đã được xác thực | Chỉ set tại ingress tin cậy, tránh sửa giữa flow | Phục vụ audit và attribution |
| **correlationId** hợp lệ | Thường giữ xuyên các bước | Nếu overwrite có thể đứt trace và reply matching |
| **replyChannel / errorChannel** | Không sửa tùy tiện | Có thể làm request/reply hoặc error routing sai |
| **id / timestamp** của Spring Message | Để framework quản lý | Mang semantics của message mới, không phải business event ID |
| **contentType** | Chỉ đặt khi thực sự khớp body được gửi | Nếu nói JSON nhưng payload chưa được serialize sẽ gây lỗi adapter |

Mức overwrite mặc định **khác nhau theo thành phần** và overload API. Hãy kiểm tra **HeaderEnricherSpec**/**ContentEnricher** của version Spring Integration đang dùng; khi có yêu cầu không được overwrite, cấu hình tường minh bằng API tương ứng và kiểm thử với message đã có header.

Nếu business key từ input đã được validate, có thể chuẩn hóa một tên header nhưng vẫn lưu **business id** trong payload. Khi qua broker hoặc chuyển đổi Message, một message **id** mới có thể được tạo; đừng coi header id kỹ thuật là nguồn đảm bảo idempotency.

### 4.3. Khi nào dùng HeaderEnricher thay vì MessageBuilder?

**MessageBuilder** hợp lý nếu đang ở code Java tạo message ban đầu:

~~~java
Message<OrderDraft> message = MessageBuilder
        .withPayload(order)
        .setHeader("sourceSystem", "order-connector")
        .setHeader("flowVersion", "2")
        .build();
~~~

**HeaderEnricher** thuận tiện ở giữa một **IntegrationFlow**, nơi cần khai báo metadata như một bước riêng có thể test, quan sát và tái sử dụng. Đối với logic có nhiều điều kiện, validation phức tạp hoặc gọi dịch vụ bên ngoài để tạo header, cân nhắc service/transformer tách riêng để tránh lambda dài khó vận hành.

## 5. Metadata kỹ thuật và các header đặc biệt

Spring Integration dùng nhiều header để điều phối luồng:

| Header | Thường dùng cho | Rủi ro khi tự thay |
| --- | --- | --- |
| **MessageHeaders.ID** | Định danh một message trong framework | Không ổn định như business event ID |
| **MessageHeaders.TIMESTAMP** | Thời điểm message được tạo | Không thay thế thời điểm sự kiện gốc |
| **IntegrationMessageHeaderAccessor.CORRELATION_ID** | Liên hệ các phần của một nhóm hoặc message request/reply | Có thể gom nhầm nhóm nếu sai correlation |
| **SEQUENCE_NUMBER / SEQUENCE_SIZE** | Splitter/aggregator, thành viên trong nhóm | Sai thứ tự/số phần gây chờ hoặc kết hợp sai |
| **MessageHeaders.REPLY_CHANNEL** | Kênh nhận phản hồi từ gateway | Đổi nhầm khiến caller chờ timeout |
| **MessageHeaders.ERROR_CHANNEL** | Đích xử lý ErrorMessage | Đổi nhầm làm lỗi không đi về nơi dự kiến |
| **routingSlip** | Định tuyến theo danh sách bước kế tiếp | Metadata phải đáng tin, tránh route tới channel sai |
| **priority** | Mức ưu tiên nếu channel/adapter hỗ trợ | Không mặc định mọi broker đều dùng hoặc giữ nguyên |

Không nên dùng chung một tên header tự đặt với tên framework, ví dụ **id**, **replyChannel**, **errorChannel**, **correlationId**, nếu không thực sự muốn can thiệp semantics của Spring Integration.

Để quản lý trace/correlation nên có quy ước namespace:

~~~text
businessEventId  = ID nghiệp vụ do nguồn phát, ổn định khi replay
sourceSystem     = adapter tin cậy thiết lập
flowVersion      = phiên bản contract nội bộ
correlationId    = theo dõi quan hệ request/batch theo quy ước
retryAttempt     = trạng thái một lần giao/attempt có định nghĩa riêng
tenantId         = đã xác thực và được đưa qua boundary có bảo vệ
~~~

### Header channel registry khi message được lưu hoặc truyền qua broker

Header **replyChannel** và **errorChannel** có thể chứa tham chiếu **MessageChannel** trong bộ nhớ, không thể tự serializable vào JSON/JMS/Kafka message. Spring Integration có cơ chế **header channels to string / HeaderChannelRegistry** giúp ánh xạ channel tham chiếu sang tên/token có thời gian sống để dùng qua một số ranh giới bất đồng bộ.

Chỉ sử dụng khi thực sự cần duy trì reply/error path qua persistent channel hoặc adapter. Phải đặt TTL đủ cho round-trip, tránh registry hết hạn trước khi reply về. **Không coi token registry là một địa chỉ reply có thể chia sẻ vô hạn giữa các application hoặc deployments**; cần thiết kế hợp đồng tương quan và routing cho hệ phân tán.

## 6. Content enricher bổ sung payload như thế nào?

**ContentEnricher** (còn gọi **payload enricher**) bổ sung thuộc tính vào payload gốc. Khi cần dữ liệu bên ngoài, nó gửi một request tới **requestChannel** và **đợi reply** rồi dùng các expression trên reply để đặt giá trị vào payload hoặc header mục tiêu.

~~~mermaid
sequenceDiagram
    participant O as Order Flow
    participant E as ContentEnricher
    participant L as Customer Lookup Handler
    participant C as Customer DB / Cache / HTTP
    O->>E: OrderDraft(customerId=C-44)
    E->>L: request payload = C-44
    L->>C: lookup customer C-44
    C-->>L: CustomerProfile(gold)
    L-->>E: reply CustomerProfile
    E->>E: setCustomer(profile)
    E-->>O: OrderDraft đã bổ sung customer
~~~

Điểm quan trọng:

1. Request gửi tới lookup channel có thể chỉ mang **một phần payload gốc** (chẳng hạn customerId) bằng **requestPayloadExpression**.
2. Reply có thể là một message mới; content enricher dùng **reply message làm root** để đánh giá **propertyExpression**.
3. **Payload gốc** là đối tượng được bổ sung; nó không tự biến thành reply payload. Nếu muốn trả một DTO hoàn toàn khác, **transformer** có thể phù hợp hơn.
4. Không nhất thiết có request channel: có thể bổ sung giá trị tĩnh hoặc expression ngay trong nội bộ flow.

### 6.1. Mô hình dữ liệu minh họa

Ví dụ dùng JavaBean có setter để Spring Integration có thể gán thuộc tính:

~~~java
public class OrderDraft {
    private String orderId;
    private String customerId;
    private String tenantId;
    private long amount;
    private CustomerProfile customer;

    public OrderDraft() {}

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }

    public long getAmount() { return amount; }
    public void setAmount(long amount) { this.amount = amount; }

    public CustomerProfile getCustomer() { return customer; }
    public void setCustomer(CustomerProfile customer) {
        this.customer = customer;
    }
}

public record CustomerProfile(
        String customerId, String tier, boolean active) {
}
~~~

Trường **customer** là dữ liệu enrichment dùng trong nghiệp vụ; **sourceSystem/flowVersion** là metadata nên để headers. Đối với dữ liệu nhạy cảm, chỉ trả những trường mà flow thực sự cần; không đưa toàn bộ profile chứa địa chỉ, số định danh hoặc thông tin thanh toán vào message nếu không cần.

### 6.2. Java DSL: tra cứu qua request/reply channel

~~~java
@Configuration
public class OrderEnrichmentFlowConfiguration {

    @Bean
    IntegrationFlow enrichOrderFlow() {
        return IntegrationFlow.from("validatedOrders")
                .enrichHeaders(h -> h
                        .header("flowVersion", "2")
                        .header("sourceSystem", "order-connector")
                        .headerExpression("businessKey", "payload.orderId"))
                .enrich(e -> e
                        .requestChannel("customerLookupChannel")
                        .requestPayloadExpression("payload.customerId")
                        .propertyExpression("customer", "payload")
                        .replyTimeout(2_500L))
                .channel("enrichedOrders")
                .get();
    }
}
~~~

**Diễn giải từng dòng:**

- **IntegrationFlow.from("validatedOrders")** đọc message đã qua validation.
- **enrichHeaders(...)** đặt metadata cho những bước downstream.
- **requestChannel("customerLookupChannel")** gửi một request và chờ reply bằng cơ chế gateway nội bộ của ContentEnricher.
- **requestPayloadExpression("payload.customerId")** chỉ gửi customerId để lookup, tránh truyền cả DTO không cần thiết. Các headers liên quan vẫn có thể được mang theo request theo cơ chế gateway.
- **propertyExpression("customer", "payload")** lấy **payload của reply message**, ở đây là CustomerProfile, và gán vào thuộc tính **customer** của OrderDraft gốc.
- **replyTimeout(2_500L)** là thời gian chờ reply của enricher, tính bằng mili giây; nó **không thay thế** timeout mạng của WebClient, JDBC, cache hoặc một deadline tổng thể cho message.
- **channel("enrichedOrders")** đưa message tiếp theo sang channel downstream. Channel này phải có consumer/endpoint nhận; nếu là DirectChannel mà không có subscriber, việc gửi có thể thất bại.

Consumer của lookup channel có thể được khai báo bằng Service Activator:

~~~java
@Component
public class CustomerLookupHandler {
    private final CustomerDirectory directory;

    public CustomerLookupHandler(CustomerDirectory directory) {
        this.directory = directory;
    }

    @ServiceActivator(inputChannel = "customerLookupChannel")
    public CustomerProfile lookup(String customerId) {
        return directory.requireCustomer(customerId);
    }
}
~~~

**CustomerDirectory** là service của ứng dụng, có thể truy cập database, cache hoặc HTTP client. Phương thức **requireCustomer** cần trả CustomerProfile hoặc ném exception có nghĩa rõ ràng nếu không tìm thấy. Không nên trả null tùy tiện khiến flow mất reply, timeout hoặc gán dữ liệu thiếu mà không có log phù hợp.

Đoạn cấu hình trên là ví dụ wiring **synchronous request/reply**; nếu lookup dùng DirectChannel, service method blocking có thể chạy ngay trên thread gửi. Khi cần xử lý async hoặc giới hạn tải, phải thiết kế executor/channel/transaction/timeout phù hợp; không chỉ đặt replyTimeout rồi nghĩ mọi lệnh I/O đều được hủy đúng hạn.

## 7. Content enricher không nhất thiết gọi hệ thống khác

Với những trường có thể suy ra từ payload, dùng enrichment tĩnh hoặc biểu thức sẽ nhẹ hơn một round-trip HTTP/DB:

~~~java
IntegrationFlow staticEnrichmentFlow() {
    return IntegrationFlow.from("ordersWithoutState")
            .enrich(e -> e
                    .property("processingState", "VALIDATED")
                    .propertyExpression("sourceAmount", "payload.amount"))
            .channel("ordersWithState")
            .get();
}
~~~

Ví dụ này yêu cầu target JavaBean có **setProcessingState(...)** và **setSourceAmount(...)** phù hợp; các thuộc tính không tồn tại hoặc không có setter/converter phù hợp sẽ gây lỗi mapping khi chạy.

Nhiều trường hợp chỉ cần tạo **DTO kết quả mới** mà không thay payload gốc. Khi đó **transformer** thường rõ ý nghĩa hơn:

~~~java
public record EnrichedOrder(
        String orderId,
        String customerId,
        CustomerProfile customer,
        long amount) {
}

public EnrichedOrder combine(
        OrderDraft order, CustomerProfile profile) {
    return new EnrichedOrder(
            order.getOrderId(),
            order.getCustomerId(),
            profile,
            order.getAmount());
}
~~~

**ContentEnricher** là công cụ phù hợp cho “bổ sung thuộc tính lên target”. **Transformer** thường phù hợp hơn khi cần thay đổi cấu trúc payload, tạo record bất biến, đổi định dạng JSON/XML/Avro hoặc version hợp đồng. Không ép một immutable record vào content enricher rồi dựa vào reflection để sửa những trường vốn không thể thay đổi.

## 8. Chọn đúng điểm enrichment trong flow

Các thành phần **HeaderEnricher**, **ContentEnricher**, **Transformer**, **Router**, **Filter** và **ServiceActivator** đều có vai trò riêng:

| Thành phần | Công việc chính | Ví dụ |
| --- | --- | --- |
| Header enricher | Bổ sung thông tin điều khiển/metadata | sourceSystem, flowVersion, tenant scope đã xác thực |
| Content enricher | Bổ sung thuộc tính trên payload gốc | Tra customer tier, risk category, warehouse metadata |
| Transformer | Tạo payload/Message biểu diễn mới | JSON thành OrderCreatedV2 hoặc OrderDraft thành EnrichedOrder |
| Filter | Cho đi tiếp hoặc loại message theo điều kiện | Chỉ nhận order amount hợp lệ |
| Router | Chọn channel tiếp theo | Priority lane theo customer tier |
| Service activator | Thực hiện logic, gọi downstream, trả reply tùy hợp đồng | Customer lookup, persistence, outbound publish |

Một quy tắc:

~~~text
Validate input & trust boundary
    → Header enrich: metadata tin cậy
    → Content enrich: dữ liệu bổ sung
    → Business validation: điều kiện sau enrichment
    → Route: dựa vào dữ liệu đã hoàn thiện
    → Handler/adapter: side effect nghiệp vụ
~~~

**Không nhất thiết mọi flow phải theo đúng thứ tự này.** Nếu upstream đã có đủ dữ liệu hoặc kết quả lookup chỉ dùng ở một nhánh, hãy **route sớm rồi chỉ enrich nhánh cần thiết** để tránh tăng độ trễ và số request. Nhưng nếu router dựa vào trường cần lookup, enrich phải xảy ra trước router đó.

## 9. Overwrite, null, đối tượng mutable và tính nhất quán

Một content enricher thực hiện property assignment lên target. Điều này kéo theo các quyết định quan trọng:

### 9.1. Trường đã có giá trị

Nếu **OrderDraft.customer** đã có CustomerProfile mà enricher lại tra customer mới, giá trị hiện tại có thể bị thay theo cấu hình property mapping. Tự hỏi:

- Dữ liệu hiện có đến từ nguồn tin cậy nào?
- Giá trị trong customer service có còn mới hơn không?
- Có được phép overwrite thông tin mà upstream đã cung cấp không?
- Nếu hai nguồn mâu thuẫn, nên ưu tiên nguồn nào và ghi audit gì?

Với header, **overwrite** là tùy chọn riêng; với content enricher, property enrichment thiên về **gán giá trị mới**. Hãy kiểm thử trường hợp header/property đã tồn tại, đừng mặc định hai component có cùng chính sách mặc định.

### 9.2. Reply trả null hoặc thiếu trường

Nếu customer lookup không tìm thấy ID:

- Có thể báo **CustomerNotFoundException** để chặn nghiệp vụ.
- Có thể đi **error flow** để ghi sự kiện chưa xử lý hoặc DLQ theo hợp đồng.
- Nếu hợp đồng cho phép guest order, có thể dùng profile mặc định **được quy định rõ**, kèm lý do và metric fallback.

Content enricher có các cơ chế **null result expression** cho một số property/header mapping, nhưng không nên dùng mặc định giả như một “customer premium” khi lookup lỗi. **Không tìm thấy dữ liệu**, **timeout** và **lỗi cấu hình** là ba tình trạng khác nhau.

### 9.3. Payload mutable và chia sẻ reference

Trong cùng JVM, một message có thể được publish tới nhiều subscriber hoặc đi qua publish-subscribe channel. Header enrichment thường tạo MessageHeaders mới; nhưng payload JavaBean có thể vẫn là **cùng reference**.

~~~java
OrderDraft draft = new OrderDraft();
Message<OrderDraft> initial =
        MessageBuilder.withPayload(draft).build();

// Tạo Message mới không có nghĩa draft được deep-copy.
Message<OrderDraft> withHeader =
        MessageBuilder.fromMessage(initial)
                .setHeader("flowVersion", "2")
                .build();

assertSame(initial.getPayload(), withHeader.getPayload());
~~~

ContentEnricher có tùy chọn **shouldClonePayload** đối với payload triển khai **Cloneable**, nhưng không thay thế một chính sách immutable/deep copy tổng quát. Nếu clone chỉ shallow copy, các object con vẫn có thể dùng chung. Với nhiều nhánh chạy song song, ưu tiên **immutable DTO + transformer tạo object mới** hoặc copy có kiểm soát để tránh race condition.

## 10. Metadata từ HTTP, database và message broker

Thực tế metadata đi qua nhiều boundary:

~~~mermaid
flowchart LR
    A["HTTP request headers"] --> B["HTTP inbound gateway"]
    B --> C["Internal MessageHeaders"]
    C --> D["Content enricher / DB/HTTP lookup"]
    D --> E["Kafka/AMQP/JMS outbound adapter"]
    E --> F["Broker headers + payload"]
    F --> G["Consumer service"]
~~~

**Không phải mọi header nội bộ tự động đi xuyên các adapter.** Header mapper, converter và serialization policy quyết định tên và kiểu dữ liệu được truyền.

| Ranh giới | Cần kiểm tra |
| --- | --- |
| HTTP inbound | Header nào được phép map vào Message? Giá trị tenant, auth, correlation đã xác thực chưa? |
| Database | Metadata quan trọng để replay có được lưu như cột nghiệp vụ/outbox không? |
| Kafka | Header là byte[]/serialization; consumer có thống nhất tên, encoding và version? |
| AMQP/RabbitMQ | Header mapper, content type, correlation ID, reply-to và field types |
| JMS | Header chuẩn JMS, properties với kiểu được provider hỗ trợ; tránh tên không portable |
| Spring Integration persistent channel | Message serialization, header channel registry, khả năng phục hồi sau restart |
| Cache | Key có đủ tenant/business scope và TTL hợp lý? Lookup error có bị che thành cache miss? |

Một số header framework không phù hợp để phát tán bên ngoài process như **replyChannel/errorChannel** chứa object. Bên kia boundary cần hợp đồng **reply destination + correlation key** tường minh hoặc cơ chế request-reply phù hợp với broker.

### Metadata nào phải được lưu như dữ liệu bền vững?

Nếu hệ thống có yêu cầu **replay** sau crash hoặc **deduplicate** event:

- **businessEventId** nên có mặt trong payload hoặc record outbox/inbox bền vững.
- **schemaVersion** nên được truyền theo hợp đồng có kiểm soát để consumer biết cách decode.
- **sourceOccurredAt** là thời điểm sự kiện tại nguồn, khác với **MessageHeaders.TIMESTAMP**.
- **tenantId** cần kiểm tra lại quyền truy cập khi đi qua boundary tin cậy khác.
- **processingStatus/retryCount** có thể được lưu ở bảng trạng thái, không nên chỉ dựa vào header in-memory.

**MetadataStore** của Spring Integration là nơi giữ key–value trạng thái, **không giống MessageHeaders** của từng message. Gắn header “processed=true” không có nghĩa broker, database hoặc consumer khác đã ghi trạng thái xử lý thành công.

## 11. Request/reply timeout của content enricher

Khi **ContentEnricher** dùng request channel, nó hoạt động như một gateway cần reply. Có hai timeout chính ở cơ chế gateway:

| Thiết lập | Ý nghĩa | Không nên hiểu là |
| --- | --- | --- |
| **requestTimeout** | Giới hạn khi **gửi request** tới MessageChannel có thể chặn (ví dụ QueueChannel đầy) | Connect/read timeout của HTTP client |
| **replyTimeout** | Giới hạn chờ reply từ nhánh lookup khi có chờ bất đồng bộ | Deadline tuyệt đối ngắt được mọi blocking handler |
| **HTTP/WebClient timeout** | Connect/read/response time và operator timeout của client | Timeout giao tiếp qua MessageChannel |
| **JDBC query timeout** | Thời gian truy vấn/lock theo driver/DB | Thời gian tổng của content enrichment |
| **Business deadline** | Tổng ngân sách của toàn request hoặc message workflow | Một property mặc định cho mọi component |

Ví dụ:

~~~java
.enrich(e -> e
        .requestChannel("customerLookupChannel")
        .requestPayloadExpression("payload.customerId")
        .propertyExpression("customer", "payload")
        .requestTimeout(300L)
        .replyTimeout(2_500L))
~~~

**Quan trọng:** nếu requestChannel là **DirectChannel** và lookup blocking ngay trên thread gửi, một call HTTP/JDBC có thể giữ thread trong lúc handler chạy; việc đặt **requestTimeout** không ngắt nó. **replyTimeout** cũng không nên được coi là “kill switch” cho mọi phương thức đồng bộ. Muốn ngăn chờ vô hạn, cấu hình timeout ngay tại HTTP/JDBC client, sử dụng async boundary phù hợp và đo deadline đầu cuối.

### 11.1. Timeout mà side effect đã xảy ra

Nếu enrichment chỉ **GET customer** thì retry thường ít rủi ro hơn một lệnh ghi. Nhưng nếu nhánh lookup thực tế cập nhật cache, gọi dịch vụ ghi dữ liệu hoặc phát event, timeout có thể xảy ra **sau khi side effect đã commit**, trước khi reply về.

Không retry vô hạn chỉ vì enricher nói “reply timeout”. Khi cần lặp lại request có tác dụng phụ, phải có **idempotency key** được xác định ở nghiệp vụ và phương án đối soát kết quả.

### 11.2. Reply đến muộn

Khi request chạy qua ExecutorChannel, queue hoặc broker, reply có thể đến **sau khi gateway đã timeout**. Cần hiểu chiến lược **temporary reply channel**, correlation ID và xử lý late reply của framework/adapter. Không dùng một shared reply queue mà không có correlation và không coi mọi reply muộn là một message nghiệp vụ mới.

Nếu lookup có độ trễ khó dự đoán, cân nhắc **async enrichment architecture**:

~~~text
OrderCreated → store pending enrichment
  → request customer lookup (event/command)
  → CustomerProfile reply with correlation
  → join by durable key
  → enriched order → routing
~~~

Kiến trúc này phức tạp hơn nhưng không giữ một thread/request chờ lâu; nó cần persistent state, TTL, timeout, duplicate detection và recovery rõ ràng.

## 12. Error handling, fallback và DLQ

Những lỗi điển hình của enrichment:

| Lỗi | Ví dụ | Cách xử lý nên cân nhắc |
| --- | --- | --- |
| Input schema/tenant sai | Thiếu customerId, tenant không có quyền | Reject trước enrichment, không gọi lookup |
| Không tìm thấy dữ liệu | Customer ID không tồn tại | Business rejection hoặc fallback có hợp đồng |
| Timeout tạm thời | Customer DB/HTTP chậm | Retry có giới hạn, backoff, deadline |
| Downstream trả 429/503 | Rate limit hoặc unavailable | Backoff theo Retry-After/quota, không tạo retry storm |
| Reply không đúng schema | Lookup service trả object bất hợp lệ | Báo lỗi contract, quan sát và sửa mapping |
| Không map được property | JavaBean thiếu setter hoặc sai type | Sửa cấu hình/code, không retry vô hạn |
| Header conflict | correlationId/tenantId bị ghi đè ngoài ý muốn | Kiểm tra trust boundary, overwrite policy |
| Dead-letter publish thất bại | Handler kết thúc lỗi nhưng adapter không gửi được DLQ | Không ACK mù; cần recovery/đối soát |

Một cách xử lý có chủ đích:

1. Validate **trước** khi enrichment; lỗi không thể retry được phân loại sớm.
2. Cho exception của nhánh lookup đi về **error channel** hoặc container error handler phù hợp với loại adapter.
3. Chỉ fallback khi business đã chấp nhận “dữ liệu chưa đầy đủ” và có cách theo dõi/backfill.
4. Nếu message broker nhận lại qua at-least-once, **tất cả side effect** phía sau enrichment cần chống trùng.
5. Tránh bắt Exception rồi gắn header **enrichmentSucceeded=true** hoặc trả default profile giả khiến downstream ra quyết định sai.

ContentEnricher có thể cấu hình **errorChannel** cho những lỗi từ nhánh request để trả đối tượng fallback theo cơ chế framework; tuy nhiên, một ErrorMessage đến error channel chưa có nghĩa lỗi đã được “giải quyết”. Phải có consumer/error flow thực sự trả kết quả hợp lệ hoặc chuyển lỗi cuối sang chính sách DLQ theo contract.

## 13. Hiệu năng, cache, batch và concurrency

Một content enrichment đơn lẻ nhìn nhẹ nhàng nhưng có thể tạo **N+1 network calls**: mỗi order lại gọi customer service, trong khi nhiều order thuộc cùng khách hàng.

Ví dụ tải:

~~~text
2.000 order/giây
× 1 customer lookup/order
= 2.000 request lookup/giây
~~~

Nếu mỗi lookup mất p95 = 120 ms, độ trễ flow tăng ít nhất tương ứng trên các request đồng bộ; ở nhiều instance, tổng concurrency và pool phải được thiết kế theo tải thực tế. Không chọn concurrency dựa vào CPU của service enrichment khi nút thắt là downstream.

Các giải pháp:

- **Cache theo customerId + tenant**, TTL phù hợp biến động hồ sơ và chính sách nhất quán.
- **Batch lookup** nếu hợp đồng upstream cho phép; có thể gom message theo tenant hoặc bucket, nhưng phải xử lý partial failures và thứ tự.
- **Enrich có điều kiện**: chỉ gọi customer service khi router/handler thực sự cần trường customer.
- **Pre-enrich tại nguồn** khi sự kiện có thể mang một snapshot hợp lệ theo đúng hợp đồng và chính sách dữ liệu.
- **Giới hạn concurrent requests**, connection pool, rate limiter và retry budget.
- **Không cho phép unlimited queue** chứa hàng trăm nghìn request enrichment khi downstream hỏng.

### Cache làm dữ liệu enrichment cũ đi

Nếu customer tier thay đổi giữa lúc order được tạo và lúc được xử lý, quyết định ưu tiên có thể khác nhau. Cần định nghĩa:

1. Dùng **tier tại thời điểm đặt hàng** hay tier mới nhất lúc xử lý?
2. Cache entry được version hóa hay invalidation ra sao?
3. Nếu consumer replay event cũ, có được phép enrich lại với dữ liệu hiện tại không?
4. Hệ thống có cần snapshot hóa kết quả enrichment trong outbox/event không?

Một sự kiện có thể được xử lý lại với metadata/customer profile khác nếu luôn tra cứu trạng thái hiện tại. Để có **deterministic replay**, lưu snapshot dữ liệu cần thiết hoặc version của dữ liệu tra cứu theo hợp đồng.

## 14. Truy vết và đo chất lượng của enrichment

Đo lường cần phân biệt **số message**, **số lần lookup**, **cache hit/miss** và **số lần retry**:

| Metric gợi ý | Đơn vị / điểm đo |
| --- | --- |
| **app.integration.enrichment.received** | Delivery vào bước enrichment |
| **app.integration.enrichment.lookup.started** | Lần gọi lookup thực tế |
| **app.integration.enrichment.lookup.duration** | Timer cho lookup DB/HTTP/cache |
| **app.integration.enrichment.lookup.outcome** | success / not_found / timeout / failure |
| **app.integration.enrichment.fallback** | Số lần đi nhánh fallback theo lý do |
| **app.integration.enrichment.completed** | Message bổ sung xong và được gửi tiếp |
| **app.integration.enrichment.failed** | Message thất bại cuối cùng trước downstream |
| **app.integration.enrichment.cache.hit** | Cache hit/miss nếu có cache |
| **app.integration.enrichment.retry.started** | Attempt retry đã bắt đầu, không phải lần mới lên lịch |

Đây là **quy ước metric ứng dụng đề xuất**, không phải toàn bộ metric mặc định Spring Integration. Spring Boot Actuator, Micrometer và Spring Integration Observation cung cấp instrumentation cho HTTP client/handler/channel; các outcome nghiệp vụ cần bổ sung có chủ đích.

Không dùng **orderId**, **customerId**, **requestId**, **raw tenantId** có cardinality cao hoặc error message làm tag meter. Chọn tag hữu hạn như **flow**, **lookup_source**, **outcome**, **error_kind**. Có thể để business ID trong log/trace được bảo vệ quyền truy cập nếu chính sách cho phép.

Trace điển hình:

~~~text
HTTP inbound order
  → validateOrder
  → enrichHeaders(flowVersion=2)
  → contentEnricher
      → customerLookup
          → cache miss
          → GET customer API (120 ms)
      ← CustomerProfile
  → route(priority)
  → outbound publisher
~~~

Điều quan trọng là phân biệt **lỗi ở lookup** với **lỗi ở routing hoặc outbound**. Nếu ghép mọi lỗi thành **enrichment.failed**, dashboard sẽ không chỉ ra hệ thống nào cần khắc phục.

## 15. Kiểm thử header và content enricher

### 15.1. Test đơn vị cho header expression

Có thể tách hàm tính header thành code Java thuần để kiểm thử:

~~~java
public final class OrderMetadata {
    public static String businessKey(OrderDraft order) {
        if (order.getOrderId() == null ||
                order.getOrderId().isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
        return order.getOrderId();
    }
}
~~~

Test với message payload hợp lệ và invalid:

~~~java
@Test
void businessKeyDoesNotDependOnTransportMessageId() {
    OrderDraft order = new OrderDraft();
    order.setOrderId("O-172");

    assertEquals("O-172", OrderMetadata.businessKey(order));
}
~~~

Tuy nhiên test hàm đơn vị **chưa chứng minh** header enricher được gắn đúng channel hay truyền header qua gateway; test flow cần đọc message thực.

### 15.2. Test flow với reply lookup giả

Tạo test context có hai integration flow:

~~~java
@TestConfiguration
class EnrichmentTestConfiguration {

    @Bean
    IntegrationFlow customerLookupTestFlow() {
        return IntegrationFlow.from("customerLookupChannel")
                .handle(String.class, (customerId, headers) ->
                        new CustomerProfile(customerId, "GOLD", true))
                .get();
    }

    @Bean
    IntegrationFlow enrichOrderUnderTest() {
        return IntegrationFlow.from("testOrdersIn")
                .enrichHeaders(h -> h.header("flowVersion", "2"))
                .enrich(e -> e
                        .requestChannel("customerLookupChannel")
                        .requestPayloadExpression("payload.customerId")
                        .propertyExpression("customer", "payload")
                        .replyTimeout(1_000L))
                .channel("testOrdersOut")
                .get();
    }

    @Bean("testOrdersOut")
    QueueChannel testOrdersOut() {
        return new QueueChannel();
    }
}
~~~

Test có thể gửi message bằng input channel và poll output:

~~~java
@Autowired
@Qualifier("testOrdersIn")
MessageChannel input;

@Autowired
@Qualifier("testOrdersOut")
PollableChannel output;

@Test
void contentEnricherAddsCustomerAndPreservesMetadata() {
    OrderDraft draft = new OrderDraft();
    draft.setOrderId("O-172");
    draft.setCustomerId("C-44");

    Message<OrderDraft> source =
            MessageBuilder.withPayload(draft)
                    .setHeader("correlationId", "req-9f1")
                    .build();

    assertTrue(input.send(source));

    Message<?> reply = output.receive(2_000);
    assertNotNull(reply);
    assertEquals("2", reply.getHeaders().get("flowVersion"));
    assertEquals("req-9f1", reply.getHeaders().get("correlationId"));

    OrderDraft enriched = (OrderDraft) reply.getPayload();
    assertEquals("C-44", enriched.getCustomer().customerId());
    assertEquals("GOLD", enriched.getCustomer().tier());
}
~~~

Ví dụ lược bỏ import JUnit 5, Spring Integration DSL, Spring Messaging và annotations. Các bean chạy trong **Spring test context**; tên channel **testOrdersIn** được IntegrationFlow đăng ký từ tên input. Vì test giả lookup xử lý trực tiếp qua **DirectChannel**, kết quả đến nhanh; cần test riêng với ExecutorChannel/HTTP thật để kiểm chứng timeout bất đồng bộ.

### 15.3. Các tình huống cần kiểm tra thêm

| Test case | Điều cần chứng minh |
| --- | --- |
| Input không có orderId/customerId | Validation chặn lookup; không phát event sai |
| Header đã tồn tại | Overwrite policy đúng, không mất correlationId |
| Lookup trả GOLD / STANDARD | Content mapping chính xác; router quyết định đúng |
| Lookup không tìm thấy | Phân loại business not found, không trả profile giả im lặng |
| Lookup ném HTTP timeout | Error channel/retry đúng, không coi là customer không tồn tại |
| Lookup reply đến muộn | Không gán nhầm vào order kế tiếp hoặc tạo side effect trùng |
| Payload là immutable record | Transformer tạo object mới thay vì setter thất bại |
| Hai nhánh cùng tham chiếu JavaBean | Không có mutation ngoài ý muốn/race |
| Adapter gửi qua Kafka/JMS/AMQP | Chỉ header đã cho phép và đúng encoding được map |
| Replay event cũ | Kết quả enrichment nhất quán theo version/snapshot |
| Enrichment retry nhiều lần | Metric attempt khác delivery, không nhân đôi side effect |
| Metadata nhạy cảm | Không lọt vào header broker, log hoặc trace không cần thiết |

Đối với flow tích hợp HTTP/broker, test thực tế cần **MockWebServer/WireMock** hoặc Testcontainers của broker thích hợp; mock một method service đơn thuần không kiểm chứng timeout, mapping header và serialization tại boundary.

## 16. Những nhầm lẫn thường gặp

**“Header enricher và content enricher chỉ khác tên.”** Không đúng. Header enricher chủ yếu cập nhật **MessageHeaders**; content enricher chủ yếu bổ sung **payload** và có thể gọi request/reply flow để tìm dữ liệu.

**“Đặt customer profile vào header cũng giống đặt trong payload.”** Có thể làm lộ dữ liệu qua broker/log, gây vấn đề serialization và lẫn trách nhiệm metadata với hợp đồng nghiệp vụ. Thông tin customer phục vụ xử lý nên ở payload/DTO tương ứng.

**“ContentEnricher lúc nào cũng cần HTTP request.”** Không. Có thể enrich từ literal/expression ngay trong flow; request channel là tùy chọn.

**“requestPayloadExpression chỉ gửi một trường nên các header khác tự mất.”** Thông thường request message vẫn có các headers được mang theo cơ chế gateway. Muốn hạn chế truyền header qua boundary, phải cấu hình header mapper/filter riêng.

**“replyTimeout là timeout cho mọi thao tác HTTP/JDBC bên dưới.”** Sai. Nó giới hạn chờ reply của gateway trong những điều kiện phù hợp; phải đặt timeout ở client/driver và deadline ở service.

**“Header id của Spring là eventId nghiệp vụ.”** Không. Message id có thể đổi khi message được tạo lại; eventId nên do nguồn nghiệp vụ định nghĩa.

**“Thêm correlationId là tự có idempotency.”** Correlation giúp liên kết luồng; idempotency đòi hỏi trạng thái và quy tắc chặn side effect trùng riêng.

**“MessageHeaders immutable nên content enricher không thể gây race.”** Headers và payload là hai phần khác nhau; payload mutable vẫn có thể bị sửa khi nhiều nhánh dùng chung reference.

**“Bật retry sau timeout luôn an toàn.”** Với lookup thuần đọc có thể hợp lý, nhưng nếu lookup có side effect hoặc retry toàn bộ flow sau khi downstream đã commit, phải bảo vệ idempotency.

**“Flow có errorChannel thì mọi message lỗi đều tự vào DLQ.”** Error channel là đường xử lý lỗi trong ứng dụng; muốn vào DLQ cần adapter/publisher hoặc broker policy đúng.

**“Tất cả Spring Integration headers đều truyền qua Kafka/JMS/HTTP.”** Từng adapter có header mapper và quy tắc chuyển đổi riêng, đặc biệt với channel reference, contentType và giá trị không serializable.

## 17. Checklist triển khai thực tế

1. Liệt kê trường nào là **business payload**, trường nào là **metadata**.
2. Validate tenant/contract ở ingress trước khi dùng giá trị header để phân quyền hoặc lookup.
3. Dùng **enrichHeaders** cho thông tin điều khiển nhẹ; dùng **content enricher** cho thuộc tính thiếu trong payload.
4. Khi cần thay đổi cấu trúc DTO hoặc hỗ trợ immutable record, ưu tiên transformer rõ ràng.
5. Định nghĩa overwrite/null/fallback; không cho lỗi lookup bị hiểu thành giá trị hợp lệ.
6. Đặt tên header có namespace rõ, tránh can thiệp replyChannel/errorChannel/id/timestamp ngoài ý muốn.
7. Cấu hình request/reply timeout và client I/O timeout riêng, xác định deadline tổng.
8. Nếu dùng cache, xác định consistency, TTL, tenant scope và tính deterministic khi replay.
9. Với broker/HTTP boundary, kiểm tra header mapper, serialization, correlation và không lộ credential.
10. Có idempotency key và durable state ở ranh giới side effect; metadata in-memory không đủ bảo đảm exactly-once.
11. Giới hạn concurrency, queue depth và retry để enrichment không làm sập customer service/downstream.
12. Đo số lookup, cache hit, latency p95/p99, timeout, error_kind, fallback và kết quả cuối.
13. Test payload/headers, pre-existing values, reply chậm, lỗi mapping và adapter thực tế.

**Kết luận:** **HeaderEnricher** làm phong phú ngữ cảnh vận chuyển/điều phối; **ContentEnricher** làm phong phú dữ liệu nghiệp vụ, thường qua request/reply. Sử dụng đúng ranh giới metadata, giữ dữ liệu có thể replay và kiểm soát lỗi/timeout sẽ giúp các flow Spring Boot tích hợp an toàn, có thể kiểm thử và dễ quan sát.

## Tài liệu tham khảo

- [Spring Integration Reference — Content Enricher](https://docs.spring.io/spring-integration/reference/content-enrichment.html): header enricher, payload enricher, request/reply, property/header expression và Java DSL.
- [Spring Integration API — EnricherSpec (6.4)](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/dsl/EnricherSpec.html): requestChannel, requestPayloadExpression, propertyExpression, requestTimeout và replyTimeout.
- [Spring Integration API — ContentEnricher](https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/ContentEnricher.html): cách bổ sung properties/headers, gateway và clone payload.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): cấu trúc Message, immutable headers và metadata framework.
- [Spring Integration Reference — Header Channel Registry](https://docs.spring.io/spring-integration/reference/message-routing.html): cân nhắc replyChannel/errorChannel qua persistent/asynchronous boundary.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): định nghĩa IntegrationFlow và các thành phần endpoint.
- [Spring Framework — Integration with Spring Messaging](https://docs.spring.io/spring-framework/reference/integration.html): mô hình Spring Messaging và ứng dụng tích hợp.
