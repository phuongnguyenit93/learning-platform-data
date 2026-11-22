# Gateway header mapping từ method argument

## 1. Bài toán: gọi phương thức Java nhưng cần gửi một Message có ngữ cảnh

Trong module **SPRING_INTEGRATION_PATTERN**, chúng ta học cách triển khai Enterprise Integration Patterns bằng **Spring Integration** để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation có thể phối hợp trong một flow, nhưng tầng gọi nghiệp vụ thường muốn một API Java gọn:

~~~java
QuoteReceipt result = quoteGateway.preview(
        command,
        "tenant-a",
        "evt-quote-901",
        "quote:v1:tenant-a:SHIP-901:7");
~~~

Một Service Activator, Router hoặc Aggregator ở phía sau lại cần nhiều thông tin hơn payload của request:

~~~text
Spring Message
├── payload = QuoteCommand(
│       shipmentId="SHIP-901",
│       serviceLevel=EXPRESS,
│       parcelCount=2,
│       workflowEpoch=7)
└── headers:
    trustedTenantId       = "tenant-a"
    businessEventId       = "evt-quote-901"
    businessCorrelationKey= "quote:v1:tenant-a:SHIP-901:7"
    gatewaySource         = "JAVA_APP"
    operationKind         = "PREVIEW"
    id                    = <Spring Message ID>
    replyChannel          = <runtime reply destination>
~~~

**Messaging Gateway** giúp chuyển lời gọi Java thành Message, gửi vào IntegrationFlow và, nếu phương thức có kết quả, chuyển reply thành giá trị trả về Java. Chủ đề của bài này là **mapping method arguments thành Message headers**: một tham số Java nào phải trở thành payload, tham số nào trở thành header, và các header cố định/được tính ra được gắn thế nào.

~~~mermaid
flowchart LR
    A["Java caller"] --> G["Messaging Gateway proxy"]
    G --> P["Mapping method arguments"]
    P --> M["Spring Message: payload + headers"]
    M --> C["Request channel"]
    C --> H["Router / Service Activator"]
    H --> R["Reply"]
    R --> G
    G --> O["Java return value"]
~~~

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Gateway là ranh giới giữa **API Java** và **message-based flow**.
2. Dùng **@Payload** để chọn payload và **@Header** để chọn một argument làm header.
3. Dùng **@Headers** cho Map chứa nhiều headers khi cần.
4. Phân biệt **@GatewayHeader** cố định/SpEL với **@Header** lấy từ argument mỗi lần gọi.
5. Hiểu quy ước mặc định và những trường hợp **Map/multiple arguments mơ hồ**.
6. Thiết kế Gateway request/reply có header contract rõ, timeout hữu hạn và không nhầm business correlation với temporary replyChannel.
7. Kiểm tra header ở Service Activator, Java DSL và các subflows downstream.
8. Viết unit/integration tests, negative tests, và kiểm tra trust boundary, retry, error handling và idempotency.

## 2. Messaging Gateway trong Enterprise Integration Patterns

Enterprise Integration Patterns định nghĩa **Messaging Gateway** như một cách che giấu chi tiết nhắn tin đằng sau một giao diện thân thiện với ứng dụng. Code gọi không cần tự tạo Message, chọn channel hoặc chờ reply bằng tay.

~~~text
Business application
    |
    | Java method
    v
Gateway interface/proxy
    |
    | Spring Message
    v
IntegrationFlow
    |
    +-- Filter / Router / Transformer
    |
    +-- Service Activator / outbound adapter
    |
    +-- reply or error
~~~

Spring Integration cung cấp **@MessagingGateway** trên interface và **@Gateway** để cấu hình từng method. Khi interface được đăng ký đúng vào Spring context, framework tạo proxy thực hiện mapping và gửi Message.

### 2.1. Gateway không đồng nghĩa HTTP Gateway

Một **@MessagingGateway** là giao diện Java của ứng dụng với Spring Integration. Nó có thể gửi message tới DirectChannel, QueueChannel, ExecutorChannel, JMS/AMQP adapter hoặc nhiều endpoints khác.

Một **HTTP inbound/outbound gateway** là adapter tích hợp qua giao thức HTTP. Cả hai dùng từ “gateway”, nhưng API, vòng đời request/reply, mapping metadata và timeout có trách nhiệm khác nhau.

### 2.2. Gateway là điểm vào, không tự xác minh business identity

Nếu code gọi:

~~~java
gateway.preview(command, "tenant-admin", "evt-1", "quote:admin:...");
~~~

annotation **@Header("trustedTenantId")** sẽ map argument thứ hai thành một header có tên `trustedTenantId`. Nó **không tự xác minh** caller có quyền sử dụng tenant-admin.

Quy trình an toàn phải là:

~~~text
Authenticated application caller
    -> verify tenant + shipment + workflowEpoch
    -> calculate trusted event/group identity
    -> call Gateway method
    -> Spring Message with verified headers
~~~

Nếu interface Gateway được mở trực tiếp cho một controller nhận thông số tùy ý từ HTTP, phải có lớp xác thực/authorization trước lời gọi Gateway; tên header có chữ “trusted” không tạo ra lòng tin.

## 3. Chiều mapping: Gateway khác Service Activator

Điểm dễ nhầm nhất là cả Gateway và Service Activator đều có thể dùng **@Header**, nhưng ở **hai chiều khác nhau**:

~~~mermaid
flowchart LR
    C["Gateway method arguments"] -->|"@Payload / @Header"| M["Spring Message"]
    M -->|"@Payload / @Header"| H["Service Activator parameters"]
    H -->|"return value"| R["Reply Message"]
    R --> G["Gateway method return"]
~~~

| Vị trí annotation | Nguồn dữ liệu | Đích | Ví dụ |
| --- | --- | --- | --- |
| **Gateway @Payload** | Argument khi Java gọi Gateway | Message payload | `QuoteCommand` |
| **Gateway @Header** | Một argument khi Java gọi Gateway | Một Message header | `tenantId → trustedTenantId` |
| **Gateway @Headers** | Map argument của Java caller | Nhiều Message headers | `Map.of("traceRef", "...")` |
| **Gateway @GatewayHeader** | Giá trị/SpEL trong cấu hình Gateway | Message header | `operationKind=PREVIEW` |
| **Service Activator @Payload** | Message payload đã nhận | Java handler argument | `QuoteCommand request` |
| **Service Activator @Header** | Message header đã nhận | Java handler argument | `String tenantId` |

Đối với Gateway, `@Header("trustedTenantId") String tenantId` nghĩa là **đưa tenantId từ lời gọi method vào header**. Đối với handler phía sau, annotation cùng tên nghĩa là **lấy header ra khỏi message để đưa vào tham số**.

### 3.1. Không đảo nhầm hai vai trò

~~~java
// Gateway: caller cung cấp một giá trị, Gateway tạo Message.
QuoteReceipt preview(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);

// Service Activator: handler đọc một giá trị từ Message.
QuoteReceipt handle(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);
~~~

Hai signatures nhìn tương tự, nhưng Gateway method có proxy do Spring Integration tạo; Service Activator method là implementation được framework gọi khi message đi đến endpoint.

### 3.2. Spring Message header không phải HTTP request header

Khi Gateway Java gắn `trustedTenantId`, đó là header trong **Spring Messaging**. Nếu flow gửi qua HTTP/JMS/AMQP/TCP, có một bước khác quyết định header đó được serialize/map vào giao thức như thế nào. Không có bảo đảm mọi Spring headers tự đi qua mọi adapter.

## 4. Hợp đồng ví dụ: yêu cầu báo giá vận chuyển

Bài sử dụng Java 17 records để tập trung vào header mapping, không cần kết nối ngân hàng hoặc nhà vận chuyển thật. Một lệnh báo giá có:

- **Payload:** shipmentId, serviceLevel, parcelCount, workflowEpoch.
- **Headers theo invocation:** trustedTenantId, businessEventId, businessCorrelationKey.
- **Header cố định của Gateway:** gatewaySource và operationKind.
- **Reply:** QuoteReceipt, chứa thông tin cần để xác minh đường request/reply.

### 4.1. Các kiểu dữ liệu

~~~java
import java.math.BigDecimal;
import java.util.Objects;

enum ServiceLevel {
    STANDARD,
    EXPRESS
}

record QuoteCommand(
        String shipmentId,
        ServiceLevel serviceLevel,
        int parcelCount,
        int workflowEpoch) {

    QuoteCommand {
        if (shipmentId == null
                || !shipmentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SHIPMENT_ID");
        }
        Objects.requireNonNull(serviceLevel, "serviceLevel");
        if (parcelCount < 1 || parcelCount > 1000) {
            throw new IllegalArgumentException("INVALID_PARCEL_COUNT");
        }
        if (workflowEpoch < 1) {
            throw new IllegalArgumentException("INVALID_WORKFLOW_EPOCH");
        }
    }
}

record QuoteReceipt(
        String shipmentId,
        String tenantId,
        String eventId,
        String businessCorrelationKey,
        String gatewaySource,
        String operationKind,
        ServiceLevel serviceLevel,
        BigDecimal amountVnd) {
}
~~~

Giá trong ví dụ sau chỉ là một phép tính minh họa cho integration tests: STANDARD = 30.000 VND/gói, EXPRESS = 80.000 VND/gói. Đây không phải bảng giá sản phẩm thực tế.

### 4.2. Business correlation key được tạo từ scope đáng tin

~~~java
final class QuoteIdentity {
    private QuoteIdentity() {}

    static String businessKey(
            String tenantId, QuoteCommand command) {
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT");
        }
        return "quote:v1:" + tenantId
                + ":" + command.shipmentId()
                + ":" + command.workflowEpoch();
    }
}
~~~

Sử dụng tenant, shipment và workflowEpoch giúp:

- Hai tenants cùng shipmentId không bị trộn thành một group.
- Hai phiên xử lý khác nhau của cùng shipment không bị nhầm.
- Redelivery của cùng logical operation tạo cùng business key.

**Chưa đủ để cấp quyền:** thuật toán trên chỉ tạo chuỗi xác định. Một application service còn phải xác minh user/producer thực sự có quyền với tenant và shipment.

### 4.3. Những header được phép đưa vào request

| Tên Spring header | Kiểu | Nguồn | Bắt buộc? |
| --- | --- | --- | --- |
| `trustedTenantId` | String | Authenticated application context | Có |
| `businessEventId` | String | Stable event ID được kiểm chứng/persist | Có |
| `businessCorrelationKey` | String | QuoteIdentity/business workflow registry | Có |
| `gatewaySource` | String | @MessagingGateway default header | Có theo cấu hình |
| `operationKind` | String | @Gateway method header | Có theo cấu hình |
| `traceRef` | String | Observability, tùy method | Tùy chọn |
| `replyChannel` | MessageChannel runtime | Gateway framework | Không phải business argument |

Một phần metadata có thể được đặt trong payload envelope thay vì header khi cần bền qua wire/restart. Bài này chủ yếu minh họa **chuyển Java method arguments thành Spring Message headers** trong JVM.

## 5. Gateway interface: @Payload + nhiều @Header

Ví dụ chính:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.GatewayHeader;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(
        defaultRequestChannel = "quoteRequests",
        defaultHeaders = @GatewayHeader(
                name = "gatewaySource", value = "JAVA_APP"))
interface ShippingQuoteGateway {

    @Gateway(
            requestTimeout = 5_000,
            replyTimeout = 5_000,
            headers = @GatewayHeader(
                    name = "operationKind", value = "PREVIEW"))
    QuoteReceipt preview(
            @Payload QuoteCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey);
}
~~~

Khi gọi:

~~~java
QuoteCommand command = new QuoteCommand(
        "SHIP-901", ServiceLevel.EXPRESS, 2, 7);

String groupKey = QuoteIdentity.businessKey("tenant-a", command);

QuoteReceipt reply = gateway.preview(
        command,
        "tenant-a",
        "evt-quote-901",
        groupKey);
~~~

Gateway tạo một Spring Message có:

~~~text
Message.payload:
  QuoteCommand(SHIP-901, EXPRESS, 2, 7)

Message.headers:
  trustedTenantId        = tenant-a       (@Header method argument)
  businessEventId        = evt-quote-901  (@Header method argument)
  businessCorrelationKey = quote:v1:...   (@Header method argument)
  gatewaySource          = JAVA_APP       (@MessagingGateway defaultHeader)
  operationKind          = PREVIEW        (@Gateway method header)
  id/timestamp           = framework-assigned
  replyChannel           = Gateway-managed if reply is expected
~~~

**Chú ý:** tên method Java `preview` không tự trở thành header có tên `operationKind`. Giá trị PREVIEW ở ví dụ được gắn **tường minh** bằng @GatewayHeader, không phải suy luận tự động.

### 5.1. Vai trò của từng annotation

- **@MessagingGateway:** đánh dấu interface cho Gateway proxy; có thể cấu hình defaultRequestChannel/defaultHeaders.
- **@Gateway:** tùy chỉnh request channel, header và timeout cho một method cụ thể.
- **@Payload:** xác định argument nào trở thành Message payload.
- **@Header("..."):** xác định argument nào trở thành một header có tên tương ứng.
- **@GatewayHeader:** gắn header dựa vào cấu hình method/interface, không cần thêm argument Java.

### 5.2. Tại sao dùng @Payload tường minh?

Với một parameter đơn giản, Gateway có thể suy luận payload. Nhưng khi một method có nhiều arguments, đặc biệt là **Map** và các arguments có annotated headers, việc ghi @Payload giúp contract sáng rõ và tránh phụ thuộc vào những quy ước mơ hồ.

### 5.3. Tại sao không truyền trực tiếp String sourceSystem mỗi lần gọi?

Nếu source luôn là một API Java nội bộ, `gatewaySource=JAVA_APP` không cần do mỗi caller nhập. Một **@GatewayHeader(value=...)** thể hiện nguồn cấu hình cố định, tránh một argument dễ bị gõ sai.

Ngược lại, **tenantId**, **eventId**, **businessCorrelationKey** thay đổi theo từng invocation nên là parameters hoặc do một trusted facade tính toán; không hard-code chúng trong @GatewayHeader.

## 6. @GatewayHeader: header tĩnh, default header và SpEL

**@Header** trên một parameter lấy giá trị **từ argument của invocation**. **@GatewayHeader** khai báo giá trị header **trong cấu hình Gateway**. Nó có các thuộc tính quan trọng:

- `name`: tên header.
- `value`: giá trị tĩnh.
- `expression`: biểu thức SpEL được tính khi tạo Message.

Đây là hai con đường tạo header khác nhau, không phải hai cách viết tương đương trong mọi trường hợp.

### 6.1. Header chung cho mọi method

~~~java
@MessagingGateway(
    defaultRequestChannel = "quoteRequests",
    defaultHeaders = {
        @GatewayHeader(name = "gatewaySource", value = "JAVA_APP"),
        @GatewayHeader(name = "contractVersion", value = "1")
    })
interface MultiOperationQuoteGateway {
    QuoteReceipt preview(@Payload QuoteCommand command);
    QuoteReceipt recalculate(@Payload QuoteCommand command);
}
~~~

Đây là **một biến thể interface riêng** để minh họa default headers; không đăng ký cùng gateway/flow của ví dụ chính nếu không có thiết kế rõ ràng. Hai methods đều nhận `gatewaySource=JAVA_APP` và `contractVersion=1`.

**contractVersion ở đây là chuỗi header**, không tự tương đương version của payload JSON hay version business tariff. Nếu muốn schemaVersion có kiểu Integer, cần cấu hình/convert tương ứng và test.

### 6.2. Header riêng theo từng method

~~~java
@MessagingGateway(defaultRequestChannel = "quoteRequests")
interface QuoteActions {

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "PREVIEW"))
    QuoteReceipt preview(@Payload QuoteCommand command);

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "RECALCULATE"))
    QuoteReceipt recalculate(@Payload QuoteCommand command);
}
~~~

Hai method có thể dùng cùng request channel nhưng downstream Router tách theo `operationKind`. Giá trị này do Gateway cấu hình, không phải client tùy chọn dynamic channel name.

### 6.3. Header từ biểu thức

Tài liệu Spring Integration hỗ trợ SpEL để tạo header; evaluation context có thể cung cấp thông tin về **gateway method** và **method arguments**. Ví dụ:

~~~java
@MessagingGateway(
    defaultRequestChannel = "quoteRequests",
    defaultHeaders = @GatewayHeader(
            name = "gatewayMethodName",
            expression = "method.name"))
interface DiagnosticQuoteGateway {

    QuoteReceipt preview(@Payload QuoteCommand command);
}
~~~

Trong cấu hình tương thích, `method.name` tạo chuỗi tên method. Giá trị String có thể hữu ích cho audit/routing nội bộ; **đừng serialize nguyên đối tượng java.lang.reflect.Method**, vì đối tượng này không phải wire contract portable.

Nếu muốn tạo header dựa trên method arguments, cũng có thể dùng SpEL với `args` theo contract của Gateway expression context. Tuy nhiên, một argument cần mang business identity thường nên được khai báo **@Header tường minh**, thay vì một biểu thức dựa trên vị trí argument dễ bị thay đổi khi refactor method signature.

### 6.4. Thứ tự ưu tiên khi trùng tên

Không nên định nghĩa cùng một header ở nhiều nơi. Theo tài liệu Gateway, một **method-specific header configuration** có thể có ưu tiên cao hơn default header; trong những cấu hình nhất định, header cụ thể của method còn có thể override giá trị từ parameter `@Header`. Trong khi đó, **default header không override @Header của interface method**.

Ví dụ nên tránh:

~~~java
@Gateway(headers = @GatewayHeader(
        name = "trustedTenantId", value = "tenant-admin"))
QuoteReceipt unsafe(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);
~~~

Ở đây tên `trustedTenantId` bị cấp **cả bằng argument và bằng cấu hình cố định**, dễ tạo nhầm quyền. Đừng dựa vào thứ tự ưu tiên để giải quyết **authorization metadata**: tách rõ chủ sở hữu header và viết test xác nhận giá trị thực tế.

### 6.5. Không dùng SpEL để “xác thực” người gửi

Một expression chuyển `args[1]` thành một header `trustedTenantId` vẫn chỉ đang **sao chép dữ liệu**. Authorization phải dựa trên authenticated principal và registry, không dựa vào việc SpEL chạy thành công.

## 7. @Headers Map: một argument tạo nhiều headers

Khi số header có thể thay đổi theo một context đã được xác minh, Gateway hỗ trợ `@Headers` cho **Map**:

~~~java
import java.util.Map;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(
        defaultRequestChannel = "quoteRequests",
        defaultHeaders = @GatewayHeader(
                name = "gatewaySource", value = "JAVA_APP"))
interface QuoteWithContextGateway {

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "PREVIEW"))
    QuoteReceipt previewWithContext(
            @Payload QuoteCommand command,
            @Headers Map<String, Object> contextHeaders);
}
~~~

Caller có thể truyền:

~~~java
Map<String, Object> trustedHeaders = Map.of(
        "trustedTenantId", "tenant-a",
        "businessEventId", "evt-quote-901",
        "businessCorrelationKey",
                "quote:v1:tenant-a:SHIP-901:7",
        "traceRef", "trace-901");

QuoteReceipt reply =
        gateway.previewWithContext(command, trustedHeaders);
~~~

Map này được **mở rộng thành nhiều Message headers**, không phải trở thành payload. @Payload xác định rõ `command` là payload.

### 7.1. Rủi ro của Map động

Nếu Map đến từ body hoặc request headers của một client chưa xác thực, caller có thể cố đặt:

~~~text
trustedTenantId=tenant-admin
businessCorrelationKey=quote:v1:tenant-admin:...
replyChannel=untrustedDestination
errorChannel=untrustedErrorRoute
~~~

**Không truyền raw external Map trực tiếp vào @Headers.** Map phải được tạo bởi application service đã xác minh và chỉ chứa những header được allowlist. Tại ingress, hãy loại các framework control headers như replyChannel, errorChannel và routingSlip nếu chưa được internal trust policy cho phép.

### 7.2. @Headers không thay business DTO

Nếu cần thông tin như giá trị hàng, khối lượng, địa chỉ giao, parcelCount, hãy đặt trong **typed payload** `QuoteCommand`, không dồn vào Map headers. Header phù hợp với routing/correlation/trace và metadata bên ngoài nội dung cốt lõi; dữ liệu nghiệp vụ nên có schema/version rõ.

### 7.3. Khi Map đã được typed và validated

Một lớp facade có thể nhận **VerifiedQuoteContext** rồi tạo Map:

~~~java
record VerifiedQuoteContext(
        String tenantId,
        String eventId,
        String traceRef) {
}

final class QuoteGatewayFacade {
    private final QuoteWithContextGateway gateway;

    QuoteGatewayFacade(QuoteWithContextGateway gateway) {
        this.gateway = gateway;
    }

    QuoteReceipt preview(
            QuoteCommand command,
            VerifiedQuoteContext context) {

        // Context phải được tạo bởi auth/registry, không phải client.
        String groupKey = QuoteIdentity.businessKey(
                context.tenantId(), command);

        Map<String, Object> headers = Map.of(
                "trustedTenantId", context.tenantId(),
                "businessEventId", context.eventId(),
                "businessCorrelationKey", groupKey,
                "traceRef", context.traceRef());

        return gateway.previewWithContext(command, headers);
    }
}
~~~

**Giới hạn ví dụ:** `VerifiedQuoteContext` là record, không phải authentication mechanism. Production phải hạn chế nơi tạo context này hoặc dùng service xác thực và authorization thực tế trước khi gọi facade.

## 8. Convention mặc định và những method signature mơ hồ

Tài liệu Gateway mô tả các quy ước khi **không khai báo rõ @Payload/@Headers**. Một số trường hợp đơn giản có thể được suy ra, nhưng những trường hợp phức tạp có thể **không xác định được payload**.

### 8.1. Một argument không phải Map

~~~java
void send(QuoteCommand command);
~~~

Theo convention, argument này có thể được dùng làm payload. Tuy nhiên, khi một API có nhiều headers, `@Payload QuoteCommand command` sẽ rõ trách nhiệm hơn.

### 8.2. Một object và một Map

~~~java
void send(QuoteCommand command, Map<String, Object> headers);
~~~

Spring Integration có convention ánh xạ argument object đầu tiên thành payload và nội dung Map thứ hai thành headers trong trường hợp không mơ hồ. Nhưng code dễ khó đọc hoặc đổi nghĩa nếu method signature thay đổi. Cách tường minh:

~~~java
void send(
        @Payload QuoteCommand command,
        @Headers Map<String, Object> headers);
~~~

### 8.3. Một Map có thể chính là payload

~~~java
void send(Map<String, Object> body);
~~~

Theo tài liệu, khi method chỉ có một Map, Map có thể là **payload**, không phải một tập headers. Nếu cần gửi JSON-like Map làm payload, ghi rõ:

~~~java
void send(@Payload Map<String, Object> body);
~~~

Nếu định dùng Map làm headers, thêm payload argument hoặc một payload expression hợp lệ theo contract.

### 8.4. Hai Maps không annotation: không đủ thông tin

~~~java
void ambiguous(
        Map<String, Object> first,
        Map<String, Object> second);
~~~

Gateway không có đủ căn cứ để chọn Map nào là payload, Map nào là headers. Đây không phải lỗi do “headerName sai”; bản thân **method-to-message mapping mơ hồ**.

~~~java
void explicit(
        @Payload Map<String, Object> payload,
        @Headers Map<String, Object> headers);
~~~

Trong trường hợp dữ liệu nghiệp vụ lớn hoặc schema ổn định, một DTO thay vì Map payload thường dễ validate hơn.

### 8.5. Các signatures không hợp lệ

~~~java
// Không dùng hai payload parameters độc lập:
void invalidTwoPayloads(
        @Payload String a,
        @Payload String b);

// Không đánh dấu cùng một argument vừa payload vừa header:
void invalidSameArgument(
        @Payload @Header("x") String a);

// Không đánh dấu một Map vừa là payload vừa là tập headers:
void invalidPayloadHeaders(
        @Payload @Headers Map<String, Object> input);
~~~

Gateway chỉ cần **một payload xác định**, còn các arguments khác có thể cung cấp headers hoặc thuộc về một method-level payload expression.

## 9. Khi @Payload dùng biểu thức và method không có payload argument

Spring Integration hỗ trợ cách cung cấp payload thông qua **biểu thức** ở Gateway, có ích khi method gọi chỉ mang các arguments cần tính toán hoặc khi method không có argument.

Ví dụ biểu thức trên method:

~~~java
@MessagingGateway(defaultRequestChannel = "commands")
interface CommandTriggerGateway {

    @Gateway(payloadExpression = "'RUN_HEALTH_CHECK'")
    String runHealthCheck();
}
~~~

Đây là **biến thể riêng** với requestChannel "commands"; để chạy phải có consumer trả một String reply tương ứng. Nó không dùng `@Header` để tạo payload. Không đăng ký một no-argument Gateway rồi mong framework tự suy ra nội dung nghiệp vụ nếu không có payload expression hay PollableChannel receive semantics.

### 9.1. Method-level @Payload và expressions

Tài liệu cũng cho phép `@Payload` với expression trong các tình huống tương thích:

~~~java
@MessagingGateway(defaultRequestChannel = "commands")
interface ExpressionGateway {

    @Payload("args[0] + ':' + args[1]")
    String combine(String prefix, String suffix);
}
~~~

Ví dụ cho thấy biểu thức có thể đọc các method arguments; đây là cách **tạo payload**, không phải gắn header. Nếu đồng thời khai báo `@Gateway(payloadExpression=...)`, cần hiểu precedence của framework và test kết quả thay vì kết hợp expression trùng mục đích.

### 9.2. Có nên dùng expression để tạo business correlation?

Có thể viết SpEL lấy tenant và shipment từ arguments, nhưng khi correlation quyết định quyền hoặc idempotency, nên để **trusted facade/domain service** tính và validate key rồi truyền bằng `@Header`. Biểu thức ngắn gọn không thay thế việc kiểm tra tenant/epoch và theo dõi version của thuật toán tạo key.

## 10. Khi conventions không đủ: MethodArgsMessageMapper

Nếu method signature phức tạp đến mức annotations và conventions không thể mô tả mapping, Spring Integration có extension **MethodArgsMessageMapper** để tự chuyển `MethodArgsHolder` thành Message.

Đây là lựa chọn **nâng cao**, không nên dùng chỉ để thay cho vài `@Header` đơn giản. Khi tự mapper:

- Tự xác định argument nào là payload.
- Tự xác định allowed headers và type conversion.
- Tự chịu trách nhiệm khi method signature/overloads thay đổi.
- Cần kiểm tra default/method-level gateway headers và payload expressions có tương thích với custom mapper không.
- Test gateway proxy thật, không chỉ test helper mapper trực tiếp.

Theo tài liệu cấu hình Gateway, custom mapper có những **ràng buộc không được kết hợp** với default-payload-expression và header definitions nhất định. Không chồng mọi cơ chế mapping vào một interface rồi hy vọng framework chọn cách phù hợp một cách tự động.

### 10.1. Quy tắc chọn cách ánh xạ

| Yêu cầu | Cách phù hợp |
| --- | --- |
| Một typed payload | @Payload trên argument |
| Một vài headers biến động theo invocation | @Header trên từng argument |
| Một tập headers động đã được validate | @Headers Map |
| Header cố định cho mọi Gateway methods | @MessagingGateway(defaultHeaders=...) |
| Header cố định cho một method | @Gateway(headers=@GatewayHeader(...)) |
| Header tính từ gateway method metadata | @GatewayHeader(expression=...) |
| Payload tạo từ expressions | @Gateway(payloadExpression=...) hoặc @Payload expression |
| Mapping quá đặc biệt | Custom MethodArgsMessageMapper + contract tests |

**Ưu tiên cách đơn giản có thể đọc và test**. Khi header chứa tenant/correlation/authorization context, sự tường minh đáng giá hơn việc giảm một vài dòng code.

## 11. Flow nhận Message do Gateway tạo

Để quan sát những headers đã được mapping, tạo một **Service Activator thông qua Java DSL**. Nó nhận `QuoteCommand` và Map headers, validate các metadata rồi trả `QuoteReceipt`.

### 11.1. Service đọc headers và tạo reply

~~~java
import java.math.BigDecimal;
import java.util.Map;

final class QuotePreviewService {

    private static String requiredHeader(
            Map<String, Object> headers, String name) {
        Object value = headers.get(name);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_REQUIRED_HEADER_" + name);
        }
        return text;
    }

    QuoteReceipt preview(
            QuoteCommand command,
            Map<String, Object> headers) {

        String tenantId = requiredHeader(
                headers, "trustedTenantId");
        String eventId = requiredHeader(
                headers, "businessEventId");
        String correlationKey = requiredHeader(
                headers, "businessCorrelationKey");
        String source = requiredHeader(
                headers, "gatewaySource");
        String operation = requiredHeader(
                headers, "operationKind");

        String expected = QuoteIdentity.businessKey(
                tenantId, command);
        if (!expected.equals(correlationKey)) {
            throw new SecurityException("CORRELATION_MISMATCH");
        }
        if (!"JAVA_APP".equals(source)
                || !"PREVIEW".equals(operation)) {
            throw new IllegalArgumentException(
                    "UNSUPPORTED_GATEWAY_HEADER_CONTRACT");
        }

        long unitPrice = command.serviceLevel()
                == ServiceLevel.EXPRESS ? 80_000L : 30_000L;
        BigDecimal amountVnd = BigDecimal.valueOf(unitPrice)
                .multiply(BigDecimal.valueOf(command.parcelCount()));

        return new QuoteReceipt(
                command.shipmentId(),
                tenantId,
                eventId,
                correlationKey,
                source,
                operation,
                command.serviceLevel(),
                amountVnd);
    }
}
~~~

Kết quả `QuoteReceipt` **echo những trường header quan trọng** để kiểm thử có thể phát hiện mismatch trong chuỗi Gateway → Message → handler. Khi xử lý thật, không nên trả tất cả metadata nội bộ cho một client không được cấp quyền; đây là ví dụ chỉ để quan sát mapping.

### 11.2. Cấu hình Java DSL và Gateway scanning

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class QuoteFlowConfig {

    @Bean
    MessageChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    QuotePreviewService quotePreviewService() {
        return new QuotePreviewService();
    }

    @Bean
    IntegrationFlow quoteProcessingFlow(
            QuotePreviewService service) {
        return IntegrationFlow.from("quoteRequests")
                .handle(QuoteCommand.class, service::preview)
                .get();
    }
}
~~~

**Cách đặt code:** Đặt `ShippingQuoteGateway` interface ở package mà **@IntegrationComponentScan** quét tới (cùng package hoặc phạm vi được cấu hình rõ). **@EnableIntegration** kích hoạt infrastructure của Spring Integration. Nếu chỉ dùng `@ComponentScan` thông thường, interface gắn @MessagingGateway không mặc định được đăng ký bởi chính cơ chế đó; cần IntegrationComponentScan hoặc đăng ký GatewayProxyFactoryBean tương đương.

### 11.3. Đường reply về Gateway

Khi Gateway method `preview()` có return type `QuoteReceipt`, Gateway thường tạo **temporary anonymous reply channel** cho invocation. Trong ví dụ, handler ở cuối flow trả `QuoteReceipt`, không gửi nó vào một `QueueChannel` cố định khác, để reply có thể quay về đúng caller theo framework semantics.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as ShippingQuoteGateway
    participant F as quoteRequests DirectChannel
    participant H as QuotePreviewService
    C->>G: preview(command, tenant, eventId, groupKey)
    G->>G: Map args to Message payload/headers
    G->>F: Message with temporary replyChannel
    F->>H: handle(command, headers)
    H-->>F: QuoteReceipt
    F-->>G: Reply via Gateway-managed channel
    G-->>C: QuoteReceipt Java return
~~~

Nếu tự đặt `.channel("someQueue")` sau handler rồi không tạo đường reply từ queue về Gateway, caller có thể timeout. Không đánh đồng **outputChannel riêng** với **replyChannel Gateway**.

### 11.4. Method-level @Gateway và defaultRequestChannel

Interface ví dụ dùng `defaultRequestChannel="quoteRequests"`, nên `preview()` không cần lặp lại requestChannel. Nếu một method cần vào Router khác, có thể đặt:

~~~java
@Gateway(requestChannel = "specialQuoteRequests")
QuoteReceipt special(@Payload QuoteCommand command);
~~~

Tuy nhiên phải có MessageChannel/consumer tên `specialQuoteRequests`. Annotation không tự tạo một flow nghiệp vụ hoàn chỉnh và không kiểm tra tenant/mapping của method mới.

## 12. Mapping sang Service Activator có @Header ở đầu nhận

Nếu muốn đọc header bằng annotated parameters thay vì Java DSL Map, có thể thay `QuotePreviewService` bằng một Service Activator:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

final class QuoteReceivingActivator {

    @ServiceActivator(inputChannel = "quoteRequests")
    public QuoteReceipt handle(
            @Payload QuoteCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey,
            @Header("gatewaySource") String source,
            @Header("operationKind") String operation) {

        return new QuotePreviewService().preview(
                command,
                Map.of(
                        "trustedTenantId", tenantId,
                        "businessEventId", eventId,
                        "businessCorrelationKey", groupKey,
                        "gatewaySource", source,
                        "operationKind", operation));
    }
}
~~~

**Đây là phương án thay thế**: nếu dùng bean QuoteReceivingActivator thì bỏ IntegrationFlow bean đang tiêu thụ `quoteRequests`; không cho hai consumers cùng chia sẻ một DirectChannel khi chỉ muốn một business handler.

Điểm cần nhớ:

- **Gateway @Header**: Java argument → Spring header.
- **Service Activator @Header**: Spring header → Java parameter.

Kết hợp hai phía tạo một đường dữ liệu rõ ràng mà domain service không cần đọc HTTP/broker headers.

### 12.1. Required headers ở đầu nhận

Ở Gateway, các arguments có thể được caller truyền bằng null hoặc dữ liệu sai hợp đồng; ở Service Activator, `@Header` thường yêu cầu header hiện diện. Nếu header không có hoặc sai conversion, endpoint có thể lỗi **trước khi vào body method**.

**Nhưng chỉ kiểm tra header hiện diện chưa đủ:** tenantId có thể là `"tenant-admin"` với cú pháp hợp lệ nhưng không được cấp quyền. Authorization phải được kiểm chứng tại application boundary.

### 12.2. Tại sao không dùng Map ở mọi lớp?

Gateway có thể nhận `@Headers Map` linh hoạt, handler có thể nhận `@Headers Map` linh hoạt, nhưng nếu cả domain layer cũng truyền Map, schema trở nên khó quản lý. Cách tốt hơn:

~~~text
VerifiedQuoteContext (typed)
    -> Gateway @Header arguments
    -> Spring Message headers
    -> Receiving adapter / Service Activator
    -> QuoteBusinessContext (typed)
    -> Domain service
~~~

Typed context có thể validation tại construction và tránh nhầm `tenantId` với `traceId`, nhưng **vẫn cần authentication/authorization thực**.

## 13. Header mapping và Router ở phía sau

Một Gateway có thể đặt header `operationKind` để Router chọn nhánh:

~~~mermaid
flowchart LR
    G["Gateway methods"] --> M["Message + operationKind"]
    M --> R{"Header-based Router"}
    R -->|"PREVIEW"| P["previewSubflow"]
    R -->|"RECALCULATE"| C["recalculateSubflow"]
    R -.->|"Unsupported"| E["Reject / error"]
    P --> O["Reply"]
    C --> O
~~~

### 13.1. Tại sao route theo header?

Payload QuoteCommand mô tả lệnh báo giá. `operationKind` mô tả **ý định thực thi** của Gateway method. Khi hai operations có cùng payload type nhưng khác route, một header giúp Router chọn mà không phải thêm field không thuộc domain vào QuoteCommand.

### 13.2. Ví dụ DSL route theo header

~~~java
// Mảnh flow minh họa; sử dụng thay cho quoteProcessingFlow
// ở mục 11 trong một Spring context thử nghiệm riêng.
@Bean
IntegrationFlow quoteRouteFlow() {
    return IntegrationFlow.from("quoteRequests")
            .route(
                    message -> message.getHeaders()
                            .get("operationKind"),
                    mapping -> mapping
                            .channelMapping(
                                    "PREVIEW", "previewRequests")
                            .channelMapping(
                                    "RECALCULATE", "recalcRequests")
                            .defaultOutputChannel("unsupportedQuoteRequests"))
            .get();
}
~~~

Để chạy, phải khai báo các channels và subflows xử lý `previewRequests`, `recalcRequests`, `unsupportedQuoteRequests`. Đây là mảnh riêng, không phải cấu hình hoàn chỉnh thay thế toàn bộ chương trước.

### 13.3. Không route theo arbitrary channel name của client

Đừng lấy method argument `destination` rồi gửi trực tiếp vào MessageChannel có tên do client chỉ định, ví dụ `adminPaymentQueue`. Cho caller lựa chọn **business operation** từ allowlist, sau đó map operation → channel trong cấu hình tin cậy. Header routing không tự là authorization.

### 13.4. Không biến default route thành success

Nếu operationKind mới chưa được hỗ trợ, cần reject/quarantine/unsupported flow với error policy phù hợp. Không mặc định route sang PREVIEW rồi trả QuoteReceipt thành công, vì đó là một quyết định nghiệp vụ không được xác minh.

## 14. Những header nào do framework quản lý?

Gateway mapping tạo custom headers, nhưng Spring Integration cũng có **framework headers**:

| Header | Chủ sở hữu | Ý nghĩa |
| --- | --- | --- |
| `id` | Spring Message | Message instance identity |
| `timestamp` | Spring Message | Thời điểm Message được tạo |
| `replyChannel` | Gateway/request-reply runtime | Đích reply của invocation |
| `errorChannel` | Flow/error handling configuration | Đường xử lý lỗi |
| `correlationId` | Splitter/Aggregator hoặc app theo scope | Nhóm messages |
| `sequenceNumber` | Splitter/sequence infrastructure | Thứ tự child |
| `sequenceSize` | Splitter/sequence infrastructure | Số child dự kiến |
| `trustedTenantId` | Application verified boundary | Tenant |
| `businessEventId` | Application | Logical event ID |
| `businessCorrelationKey` | Application/workflow | Group identity nghiệp vụ |

Gateway method arguments **không nên tự cung cấp replyChannel/errorChannel** dưới dạng Map tùy ý, trừ khi đang xây một infrastructure adapter được kiểm soát và hiểu rõ security semantics.

### 14.1. Spring Message ID không phải business eventId

~~~text
Invocation 1:
  Spring MessageHeaders.ID = m-001
  businessEventId          = evt-quote-901

Invocation 2 (retry):
  Spring MessageHeaders.ID = m-002
  businessEventId          = evt-quote-901
~~~

Nếu lần retry là cùng logical operation, **businessEventId giữ nguyên**; việc framework tạo Message ID mới không phải lý do tạo một eventId khác.

### 14.2. Technical correlation và business correlation

Một Splitter có thể dùng `correlationId` để gom child messages; một business workflow có thể dùng `businessCorrelationKey` qua nhiều adapters và epochs. Hai giá trị đôi khi trùng nhau do thiết kế, nhưng **không có yêu cầu phải trùng trong mọi topology**.

Nếu một Gateway method cung cấp `@Header("businessCorrelationKey")`, handler downstream vẫn phải chọn đúng `correlationStrategy` cho Aggregator; không tự động có grouping chỉ vì header tồn tại.

### 14.3. Không serialize runtime replyChannel sang wire

Một temporary replyChannel là object trong Spring runtime. Khi gửi request qua JMS/AMQP/HTTP/TCP, giao thức có cơ chế reply/correlation riêng; không chuyển một live MessageChannel object thành JSON hay broker property rồi mong hệ thống khác sử dụng lại.

## 15. Gateway return type và response lifecycle

Gateway có thể biểu diễn:

- **Request/reply:** method trả một typed result.
- **Send-only:** method trả `void`.
- **Asynchronous/reactive variants:** khi cấu hình phù hợp, method return type/adapter có semantics khác; không mặc định mọi kiểu trả về đều đồng bộ.

### 15.1. Typed result

~~~java
QuoteReceipt preview(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);
~~~

Caller muốn một QuoteReceipt. Gateway phải có đường downstream reply hợp lệ; nếu handler chỉ ghi log rồi trả void/null hoặc Filter discard, không thể mong nhận QuoteReceipt.

### 15.2. Send-only

~~~java
void submit(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId);
~~~

Caller không nhận business result qua method. Spring Integration có thể dùng `nullChannel` cho đường reply của one-way Gateway tùy framework version để discard reply phát sinh, nhưng **send-only không đồng nghĩa remote effect đã commit**.

### 15.3. Gateway timeout và business deadline là hai đồng hồ

`requestTimeout` chi phối thời gian gửi request trong các tình huống channel cần chờ chỗ/đăng ký; `replyTimeout` chi phối đợi reply. Với **DirectChannel**, handler đồng bộ có thể chạy trực tiếp trên thread caller; việc đặt replyTimeout không phải cơ chế ngắt một business handler đang chạy mãi.

~~~text
requestTimeout = 2s:
  gửi Message vào một channel có thể chờ capacity

replyTimeout = 5s:
  chờ Message reply sau khi request đã dispatch

businessDeadline = 2 minutes:
  workflow quote phải có quyết định cuối cùng
~~~

Không dùng một timeout duy nhất để suy ra remote provider đã hoàn tất hay chưa. Khi Gateway timeout, side effect có thể đã xảy ra; phải dùng idempotency key/reconciliation khi retry.

## 16. Tầng ứng dụng nên xác minh dữ liệu trước khi gọi Gateway

Một interface Gateway với nhiều @Header parameters làm API rất rõ, nhưng nó cũng cho phép bất kỳ caller nào có reference đến Gateway proxy truyền các chuỗi tùy ý. Với dữ liệu bảo mật, nên cung cấp **application facade** thực hiện quyền và tạo header.

### 16.1. Verified principal và policy

~~~java
record AuthenticatedActor(
        String principalId,
        String tenantId) {
}

interface ShipmentQuoteAuthorization {
    void assertMayQuote(
            AuthenticatedActor actor,
            QuoteCommand command);
}

interface StableQuoteEventRegistry {
    String findOrCreateEventId(
            String tenantId, QuoteCommand command);
}
~~~

Hai interfaces thể hiện những dependency phải được giải quyết ở production. **AuthenticatedActor** không được dựng bằng tenantId lấy từ một HTTP header tự do; nó phải đến từ hệ thống authentication, kèm authorization policy truy shipment và epoch.

### 16.2. Facade gắn header từ dữ liệu đã xác minh

~~~java
final class SecureQuoteApplicationService {
    private final ShippingQuoteGateway gateway;
    private final ShipmentQuoteAuthorization authorization;
    private final StableQuoteEventRegistry events;

    SecureQuoteApplicationService(
            ShippingQuoteGateway gateway,
            ShipmentQuoteAuthorization authorization,
            StableQuoteEventRegistry events) {
        this.gateway = gateway;
        this.authorization = authorization;
        this.events = events;
    }

    QuoteReceipt preview(
            QuoteCommand command,
            AuthenticatedActor actor) {

        authorization.assertMayQuote(actor, command);
        String tenant = actor.tenantId();
        String eventId =
                events.findOrCreateEventId(tenant, command);
        String groupKey = QuoteIdentity.businessKey(
                tenant, command);

        return gateway.preview(
                command, tenant, eventId, groupKey);
    }
}
~~~

**StableQuoteEventRegistry** là một abstraction: implementation thực cần quyết định identity của một logical operation, lưu bền nếu cần, phân biệt request mới với retry và chống event ID conflict. Không tự tạo một UUID mới mỗi lần caller retry cùng công việc.

### 16.3. Vì sao không để Gateway tự xử lý authentication?

Một Gateway proxy chủ yếu **mapping arguments thành Spring Message và quản lý invocation**, không phải identity provider hay authorization engine. Giữ authorization ở ứng dụng/ingress làm quyền sở hữu metadata rõ và tránh dùng những header đã chưa được xác minh để quyết định security.

### 16.4. Không nhét roles hoặc secrets vào Gateway headers

Nếu một service cần biết client có quyền ADMIN, nên dùng security context được xác minh và một quyết định authorization có scope rõ. Một custom header `role=ADMIN` chưa được bảo vệ là dữ liệu dễ giả mạo. Tương tự, không chuyển Authorization bearer token, session cookies hoặc private keys vào headers chỉ để downstream log chúng.

## 17. Gateway method truyền Map<MessageHeaders> hoặc Message<?>?

Ngoài typed payload + headers annotations, một Gateway có thể nhận **Message<?>** do caller đã dựng để kiểm soát cả payload và headers. Đây là lựa chọn dành cho tầng integration có hiểu biết, không phải API nghiệp vụ mặc định.

~~~java
import org.springframework.messaging.Message;

@MessagingGateway(defaultRequestChannel = "quoteRequests")
interface RawMessageQuoteGateway {
    QuoteReceipt preview(Message<QuoteCommand> message);
}
~~~

Nếu caller truyền Message có custom headers đã xác minh, Gateway có thể chuyển tiếp nội dung đó. Nhưng cách này làm application caller phụ thuộc Spring Messaging và có thể để các framework control headers bị cấu hình sai.

### 17.1. Khi nào dùng Message thay vì nhiều arguments?

| Bối cảnh | Khuyến nghị |
| --- | --- |
| Domain/application service gọi một command đơn giản | Typed @Payload + @Header |
| Một adapter nội bộ đã có Spring Message validated | Message<?> có thể phù hợp |
| Custom middleware cần giữ headers ở trusted hop | MessageBuilder.fromMessage(...) |
| HTTP controller nhận raw request | Parse/authorize → typed facade, không đưa raw Message vào Gateway |
| Lưu event lâu dài hoặc truyền sang remote service | Versioned wire envelope/DTO |

**Không cấu hình đồng thời cả một Message argument và nhiều @Payload parameters** cho cùng mục đích nếu không hiểu custom mapping contract. Một source of truth rõ hơn là nhận Message hoàn chỉnh **hoặc** để Gateway tạo Message từ arguments.

### 17.2. Phân biệt Map parameter và MessageHeaders

Một `@Headers Map<String,Object>` trên Gateway **tạo headers**. Một `MessageHeaders` trong message nhận được là tập metadata **của Message đã tạo**. Cả hai có thể chứa custom values, nhưng chỉ MessageHeaders có thêm framework-generated id/timestamp/replyChannel theo runtime.

Không yêu cầu caller cung cấp id/timestamp để một Gateway method hoạt động; framework sẽ quản lý lifecycle của Message.

## 18. Header propagation qua Transformer và subflow

Header mapping ở Gateway chỉ là **hop đầu tiên**. Message sau đó có thể đi qua Router, Filter, Transformer, Splitter và các subflows khác.

~~~mermaid
flowchart TD
    G["Gateway args -> headers"] --> R["Router"]
    R --> T1["STANDARD Transformer"]
    R --> T2["EXPRESS Transformer"]
    T1 --> C["Common Service Activator"]
    T2 --> C
    C --> O["Reply"]
~~~

### 18.1. Transformer trả payload mới

Spring Integration Transformer có cơ chế propagation cho inbound headers khi trả **payload mới**, theo quy tắc framework. Ví dụ:

~~~java
// Mảnh IntegrationFlow, giả định quoteRequests có owner riêng.
.transform(QuoteCommand.class, mapper::normalizeCommand)
~~~

Nếu mapper trả một DTO khác, các custom headers như businessEventId, tenantId có thể tiếp tục tồn tại ở Message ra trong trường hợp thông thường. Nhưng cần **integration test** để phát hiện những điểm mà headers bị loại bởi HeaderFilter hoặc converter.

### 18.2. Handler trả Message mới

~~~java
Message<?> rebuilt = MessageBuilder
        .withPayload(newPayload)
        .setHeader("businessEventId", originalEventId)
        .build();
~~~

Nếu handler tự dựng Message mới từ đầu, những headers khác như trustedTenantId/businessCorrelationKey/temporary replyChannel có thể thiếu. Kết quả là Service Activator về sau không nhận đủ arguments, hoặc Gateway không nhận được reply.

Đối với **trusted internal Message**, nếu muốn giữ headers hiện có:

~~~java
Message<?> next = MessageBuilder.fromMessage(trustedInput)
        .setHeader("processingStage", "NORMALIZED")
        .build();
~~~

Không dùng `fromMessage` hoặc `copyHeaders` để copy toàn bộ headers **từ external producer chưa xác thực**. Tại trust boundary, tạo Message mới với allowlist và verified identity trước.

### 18.3. Splitter đổi scope technical correlation

Khi Gateway request đi qua Splitter tạo nhiều child messages, framework có thể gắn `correlationId`, `sequenceNumber`, `sequenceSize` để phục vụ Aggregator. Chúng là **sequence/group metadata của topology**, không thay thế `businessCorrelationKey` ổn định từ Gateway method.

Ví dụ:

~~~text
businessCorrelationKey:
  quote:v1:tenant-a:SHIP-901:7

Splitter child 1:
  correlationId = batch-42
  sequenceNumber = 1
  sequenceSize = 2

Splitter child 2:
  correlationId = batch-42
  sequenceNumber = 2
  sequenceSize = 2
~~~

Nếu một method Gateway đang chờ **một QuoteReceipt**, mà một Splitter tạo **hai results** không có Aggregator/transformer tổng hợp, đường reply không tự biết phải trả result nào. Thiết kế Scatter-Gather/Aggregator rõ nếu cần gom nhiều replies.

### 18.4. Router không tự tạo business correlation

Header-based Router có thể dùng `operationKind` chọn nhánh, nhưng nó không tự chứng minh tenant/correlation đúng hoặc tự phát event ID mới. Business identity nên đi qua các nhánh dưới dạng trusted headers/envelope hoặc persist trong workflow store.

## 19. Khi Gateway gọi remote adapter

Một Gateway Java có thể gửi Message tới flow chứa outbound HTTP/JMS/AMQP/TCP gateway. **Hai lớp request/reply** có thể xuất hiện:

1. **Java Messaging Gateway:** ghép invocation Java với Spring reply message.
2. **Transport gateway:** ghép request/response theo giao thức (HTTP response context, JMSCorrelationID/JMSReplyTo, AMQP replyTo/correlationId, TCP connection/request semantics).

### 19.1. Hai correlation IDs có thể khác nhau

~~~text
Business:
  businessCorrelationKey = quote:v1:tenant-a:SHIP-901:7

Java Messaging Gateway:
  replyChannel = temporary Java runtime channel

JMS outbound gateway:
  JMSMessageID / JMSCorrelationID / JMSReplyTo

AMQP outbound gateway:
  replyTo / correlationId
~~~

Không ép các trường trên thành cùng chuỗi chỉ vì chúng đều được gọi là “correlation”. Gateway header `businessCorrelationKey` dùng để định danh **workflow nghiệp vụ**; transport correlation dùng cho **request/reply của một attempt**.

### 19.2. HTTP headers và body

Một custom Spring header không tự trở thành HTTP X-Business-Correlation-Key trừ khi HeaderMapper/converter được cấu hình phù hợp. Với callback bất đồng bộ, đưa business identity vào **versioned wire envelope** hoặc persisted mapping để remote có thể trả về, không dựa vào temporary replyChannel của lời gọi Java ban đầu.

### 19.3. JMS và AMQP

JMS/AMQP hỗ trợ message properties/headers và request/reply correlation riêng, nhưng không phải mọi kiểu Java object trong Spring MessageHeaders có thể serialize thành một broker property. Các header đơn giản (String/number/boolean) có thể được map theo contract; **MessageChannel object** không phải wire value portable.

### 19.4. TCP và file adapters

TCP thường cần framing/serializer rõ để mang payload và selected headers; chỉ một connection ID không đồng nghĩa business operation. File/SFTP adapters có thể tạo message từ nội dung file, nhưng file name/mtime không tự là correlation key được xác minh.

### 19.5. Contract test qua adapter thật

Với cùng Gateway method:

1. Xác minh headers ngay sau Gateway proxy.
2. Serialize qua outbound adapter.
3. Deserialize ở inbound adapter khác.
4. Xác minh versioned business identity còn đủ.
5. Kiểm tra authorization ở source/tenant và reply correlation theo giao thức.
6. Kiểm tra retry, duplicate, timeout và late response.

Test Spring context thuần không chứng minh HTTP/JMS/AMQP/TCP header mapping đã đúng khi vận hành.

## 20. Async flow: header không tự trở thành ThreadLocal

Khi request đi vào ExecutorChannel, worker thread có thể khác thread gọi Gateway:

~~~text
Caller thread:
  authenticated tenant = tenant-a
  gateway.preview(...)

Worker thread:
  ThreadLocal tenant may be absent/stale
  Message.header.trustedTenantId = tenant-a
~~~

Handler phải đọc **trusted Message metadata** hoặc persisted workflow context, không lấy quyền tenant từ một ThreadLocal của thread khác chưa được propagate. Trace context có thể cần instrumentation để nối spans; nó không thay thế business eventId.

### 20.1. Đồng bộ và bất đồng bộ có semantics timeout khác nhau

Với DirectChannel, handler chạy trên caller thread và có thể chặn toàn bộ lời gọi. Với ExecutorChannel, Gateway có thể gửi rồi chờ một reply trên temporary channel, nhưng scheduling, queue capacity, errorChannel và reply timeout đều cần được kiểm thử theo topology.

### 20.2. Không coi Gateway method trả về là durable completion

Nếu method có return type `QuoteReceipt` và handler trả ngay khi command được **accepted**, receipt có thể chỉ là ACK tiếp nhận, không phải business quote cuối cùng. Cần đặt tên/kiểu `AcceptedReceipt` khác `CompletedQuote` nếu nghiệp vụ có vòng đời dài.

### 20.3. Callback đến muộn

Một HTTP/JMS callback sau khi Gateway đã timeout phải được gắn vào workflow state bền bằng eventId/businessCorrelationKey/operationId; không thể gửi reply vào temporary Java channel đã hết hiệu lực.

## 21. Unit test: business logic sau khi headers đã được resolve

Trước khi khởi động Spring context, test `QuotePreviewService` bằng cách truyền **Map headers đã giả định được Gateway tạo**. Các tests này chứng minh validation/business mapping, **không** chứng minh Gateway proxy đã áp dụng @Header thành công.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class QuotePreviewServiceTest {

    private final QuotePreviewService service =
            new QuotePreviewService();

    private QuoteCommand command() {
        return new QuoteCommand(
                "SHIP-901", ServiceLevel.EXPRESS, 2, 7);
    }

    private Map<String, Object> validHeaders() {
        QuoteCommand command = command();
        return Map.of(
                "trustedTenantId", "tenant-a",
                "businessEventId", "evt-quote-901",
                "businessCorrelationKey",
                        QuoteIdentity.businessKey("tenant-a", command),
                "gatewaySource", "JAVA_APP",
                "operationKind", "PREVIEW");
    }

    @Test
    void completeHeaderMapCreatesExpectedReceipt() {
        QuoteReceipt receipt = service.preview(
                command(), validHeaders());

        assertEquals("tenant-a", receipt.tenantId());
        assertEquals("evt-quote-901", receipt.eventId());
        assertEquals(
                "quote:v1:tenant-a:SHIP-901:7",
                receipt.businessCorrelationKey());
        assertEquals("JAVA_APP", receipt.gatewaySource());
        assertEquals("PREVIEW", receipt.operationKind());
        assertEquals(ServiceLevel.EXPRESS, receipt.serviceLevel());
        assertEquals(new BigDecimal("160000"), receipt.amountVnd());
    }

    @Test
    void missingTenantIsNotSilentlyDefaulted() {
        Map<String, Object> incomplete =
                new HashMap<>(validHeaders());
        incomplete.remove("trustedTenantId");

        assertThrows(IllegalArgumentException.class,
                () -> service.preview(command(), incomplete));
    }

    @Test
    void forgedGroupKeyIsRejected() {
        Map<String, Object> forged =
                new HashMap<>(validHeaders());
        forged.put(
                "businessCorrelationKey",
                "quote:v1:tenant-b:SHIP-901:7");

        assertThrows(SecurityException.class,
                () -> service.preview(command(), forged));
    }

    @Test
    void headerOfWrongTypeCannotBecomeTenant() {
        Map<String, Object> wrong =
                new HashMap<>(validHeaders());
        wrong.put("trustedTenantId", 123);

        assertThrows(IllegalArgumentException.class,
                () -> service.preview(command(), wrong));
    }

    @Test
    void unsupportedOperationIsNotAcceptedAsPreview() {
        Map<String, Object> wrong =
                new HashMap<>(validHeaders());
        wrong.put("operationKind", "DELETE_SHIPMENT");

        assertThrows(IllegalArgumentException.class,
                () -> service.preview(command(), wrong));
    }

    @Test
    void businessKeyIsStableForSameWorkflow() {
        String first = QuoteIdentity.businessKey(
                "tenant-a", command());
        String replay = QuoteIdentity.businessKey(
                "tenant-a", command());

        assertEquals(first, replay);
        assertNotEquals(first, QuoteIdentity.businessKey(
                "tenant-b", command()));
    }
}
~~~

**Giới hạn:** Map được tạo bằng code test, không qua Gateway. Do đó unit tests chỉ chứng minh logic `requiredHeader`, correlation, operationKind và giá tiền. Phần quan trọng nhất của bài — **argument mapping thật** — cần integration test.

## 22. Integration test: gọi Gateway proxy để xác nhận argument → header

Trong Spring context có **@EnableIntegration**, **@IntegrationComponentScan** và một consumer `quoteRequests`, gọi `ShippingQuoteGateway.preview` để framework tạo Message thực:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteFlowConfig.class)
class ShippingQuoteGatewayIntegrationTest {

    @Autowired
    ShippingQuoteGateway gateway;

    @Autowired
    QuoteWithContextGateway mapGateway;

    private QuoteCommand command(
            String shipment, ServiceLevel level, int epoch) {
        return new QuoteCommand(
                shipment, level, 2, epoch);
    }

    @Test
    void mapsPayloadAndEachAnnotatedHeader() {
        QuoteCommand command =
                command("SHIP-901", ServiceLevel.EXPRESS, 7);
        String groupKey =
                QuoteIdentity.businessKey("tenant-a", command);

        QuoteReceipt reply = gateway.preview(
                command,
                "tenant-a",
                "evt-quote-901",
                groupKey);

        assertNotNull(reply);
        assertEquals("SHIP-901", reply.shipmentId());
        assertEquals("tenant-a", reply.tenantId());
        assertEquals("evt-quote-901", reply.eventId());
        assertEquals(groupKey, reply.businessCorrelationKey());
        assertEquals("JAVA_APP", reply.gatewaySource());
        assertEquals("PREVIEW", reply.operationKind());
        assertEquals(new BigDecimal("160000"), reply.amountVnd());
    }

    @Test
    void mapArgumentCreatesSeveralHeaders() {
        QuoteCommand command =
                command("SHIP-902", ServiceLevel.STANDARD, 2);
        String key =
                QuoteIdentity.businessKey("tenant-a", command);

        Map<String, Object> trustedHeaders = Map.of(
                "trustedTenantId", "tenant-a",
                "businessEventId", "evt-quote-902",
                "businessCorrelationKey", key,
                "traceRef", "trace-902");

        QuoteReceipt reply = mapGateway.previewWithContext(
                command, trustedHeaders);

        assertEquals("evt-quote-902", reply.eventId());
        assertEquals(key, reply.businessCorrelationKey());
        assertEquals("JAVA_APP", reply.gatewaySource());
        assertEquals("PREVIEW", reply.operationKind());
        assertEquals(new BigDecimal("60000"), reply.amountVnd());
    }

    @Test
    void twoTenantsWithSameShipmentHaveDifferentGroupKeys() {
        QuoteCommand command =
                command("SHIP-903", ServiceLevel.STANDARD, 1);

        QuoteReceipt tenantA = gateway.preview(
                command, "tenant-a", "evt-a-903",
                QuoteIdentity.businessKey("tenant-a", command));

        QuoteReceipt tenantB = gateway.preview(
                command, "tenant-b", "evt-b-903",
                QuoteIdentity.businessKey("tenant-b", command));

        assertEquals("tenant-a", tenantA.tenantId());
        assertEquals("tenant-b", tenantB.tenantId());
        assertNotEquals(
                tenantA.businessCorrelationKey(),
                tenantB.businessCorrelationKey());
    }

    @Test
    void reInvokingSameLogicalRequestDoesNotChangeBusinessKey() {
        QuoteCommand command =
                command("SHIP-904", ServiceLevel.EXPRESS, 3);
        String key =
                QuoteIdentity.businessKey("tenant-a", command);

        QuoteReceipt first = gateway.preview(
                command, "tenant-a", "evt-904", key);
        QuoteReceipt replay = gateway.preview(
                command, "tenant-a", "evt-904", key);

        assertEquals(first, replay);
    }
}
~~~

**Điều kiện khi đưa vào project:** gateway interfaces phải nằm trong package được @IntegrationComponentScan quét, hoặc được đăng ký proxy theo cách tương đương. Các biến thể `MultiOperationQuoteGateway`, `QuoteActions`, `DiagnosticQuoteGateway`, `ExpressionGateway` trong bài chỉ là ví dụ riêng; không nhất thiết đưa tất cả vào cùng package/context test.

### 22.1. Vì sao test này kiểm chứng đúng mapping?

Code test **không tự dựng Spring Message**; nó chỉ gọi `gateway.preview(command, tenant, eventId, groupKey)`. QuotePreviewService nhận được Map headers do framework tạo. Nếu @Header gắn sai tên, hoặc @GatewayHeader default/method không được áp dụng, method service sẽ lỗi và test sẽ không nhận đúng QuoteReceipt.

Với `mapGateway.previewWithContext`, integration test chứng minh Map được Gateway dùng làm **headers** thay vì payload — nếu mapping sai, service sẽ không nhận được QuoteCommand cùng đủ headers.

### 22.2. Giới hạn của test

Các tests dùng DirectChannel và handler thuần trong Spring context. Chúng **không kiểm chứng**:

- HTTP/JMS/AMQP/TCP HeaderMapper thực qua wire.
- Authorization với JWT/mTLS/broker ACL.
- Broker redelivery hoặc process restart.
- Distributed transaction và idempotency bền.
- Handler blocking lâu hơn timeout ở một asynchronous channel.
- Một external provider thực sự áp dụng quote hay ghi side effect.

Chúng chỉ chứng minh **Gateway method-to-message mapping** và request/reply nội bộ của cấu hình mẫu.

## 23. Negative integration tests: header mất, sai kiểu hoặc bị giả

Test các lỗi này để tránh việc một lần refactor tên method argument/header làm caller nhận reply thuộc sai tenant hoặc group.

~~~java
// Bổ sung các test sau vào ShippingQuoteGatewayIntegrationTest.
@Test
void wrongCorrelationArgumentCannotJoinAnotherWorkflow() {
    QuoteCommand command =
            command("SHIP-905", ServiceLevel.EXPRESS, 1);

    assertThrows(RuntimeException.class, () ->
            gateway.preview(
                    command,
                    "tenant-a",
                    "evt-905",
                    "quote:v1:tenant-b:SHIP-905:1"));
}

@Test
void wrongHeaderTypeFromMapIsRejected() {
    QuoteCommand command =
            command("SHIP-906", ServiceLevel.STANDARD, 1);
    String key = QuoteIdentity.businessKey("tenant-a", command);

    Map<String, Object> headers = Map.of(
            "trustedTenantId", 42,
            "businessEventId", "evt-906",
            "businessCorrelationKey", key);

    assertThrows(RuntimeException.class, () ->
            mapGateway.previewWithContext(command, headers));
}

@Test
void absentRequiredBusinessHeaderIsRejected() {
    QuoteCommand command =
            command("SHIP-907", ServiceLevel.STANDARD, 1);

    Map<String, Object> missingEventId = Map.of(
            "trustedTenantId", "tenant-a",
            "businessCorrelationKey",
                    QuoteIdentity.businessKey("tenant-a", command));

    assertThrows(RuntimeException.class, () ->
            mapGateway.previewWithContext(
                    command, missingEventId));
}
~~~

Gateway errors có thể được Spring Integration **wrap** bằng MessagingException và cause chain khác nhau theo handler/version. Assert `RuntimeException` trong ví dụ để không phụ thuộc quá chặt vào outer exception class; khi áp dụng vào project hãy assert **nguyên nhân cuối và error code** theo contract thực tế.

### 23.1. Test header precedence bằng hai sources trùng tên

Nếu một method có vừa `@Header("operationKind")` trên parameter vừa `@Gateway(headers=...operationKind...)`, giá trị cuối có thể chịu precedence của method configuration. Viết một **contract test riêng** để xác minh version đang dùng nếu phải hỗ trợ kiểu cấu hình đó. Thực tế tốt hơn là **không cho hai chủ sở hữu cùng đặt một header**.

### 23.2. Test không thể ngụy tạo authorization

Một test có thể truyền `tenant-admin` kèm businessKey tương ứng và service vẫn chấp nhận vì cả hai chuỗi khớp. Đó là **giới hạn chủ ý của ví dụ QuotePreviewService**, không phải bằng chứng tenant-admin có quyền. Test security thật phải gọi `SecureQuoteApplicationService` với actor đã xác thực và policy từ chối shipment không thuộc tenant.

## 24. Test riêng cho @GatewayHeader expression và default headers

Ngoài happy path với header tĩnh, có thể tạo Gateway test riêng cho `@GatewayHeader(expression="method.name")`:

1. Gọi `DiagnosticQuoteGateway.preview(command)`.
2. Dùng endpoint test chỉ đọc Message headers, xác minh `gatewayMethodName` là `"preview"`.
3. Kiểm tra header là String, không phải `java.lang.reflect.Method`.
4. Nếu muốn truyền qua broker, serialize/deserialize qua adapter contract test.

Nếu dùng biểu thức `args[0]`, test cả khi đổi thứ tự parameters: expression có thể **chạy thành công nhưng đọc sai ý nghĩa**. Một annotated argument `@Header("businessEventId")` ít phụ thuộc vị trí hơn khi signature mở rộng.

### 24.1. Test ambiguity của Map

Một method `send(Map first, Map second)` không annotation cần được xem là **cấu hình thiếu contract**, không phải test business runtime thành công. Sửa method signature thành `@Payload Map payload, @Headers Map headers` trước khi tạo Gateway proxy; nếu cần kiểm thử invalid examples, đặt chúng trong một test configuration riêng để không làm hỏng application context chung.

### 24.2. Không chỉ assert Spring context start thành công

Một Gateway bean tồn tại chưa chứng minh payload và headers được map đúng. Hãy gọi method, nhận reply từ một handler đọc các header cụ thể và so sánh với input. Khi có adapter thật, kiểm tra cả outbound wire fields.

## 25. Lỗi phát sinh ở đâu trong Gateway lifecycle?

Lỗi liên quan header mapping và request/reply có thể nằm tại nhiều tầng:

~~~mermaid
flowchart TD
    A["Java method invocation"] --> B{"Method args mapping"}
    B -->|"Ambiguous / invalid"| E1["Gateway mapping error"]
    B -->|"PASS"| C{"Send to request channel"}
    C -->|"No capacity / no subscriber"| E2["Send failure / timeout"]
    C -->|"PASS"| D{"Downstream handler"}
    D -->|"Validation/security"| E3["Business rejection"]
    D -->|"Transient IO error"| E4["Retry / recovery"]
    D -->|"Reply"| R{"Reply path"}
    R -->|"Correct channel"| O["Java return value"]
    R -->|"Missing / late"| E5["Reply timeout / unknown state"]
~~~

### 25.1. Mapping lỗi trước khi Message có thể được gửi

Ví dụ một method có hai Map arguments chưa annotation. Gateway có thể không xác định được payload và headers. Đây là lỗi của **method-to-message mapping**, khác với lỗi business method nhận được Message nhưng phát hiện correlationKey không hợp lệ.

### 25.2. Gửi không thành công

Request channel có thể không có subscriber, đang đầy, hoặc cấu hình sai destination. `requestTimeout` có ý nghĩa trong những trường hợp send có thể block; với DirectChannel đồng bộ, exception của subscriber có thể lan lên cùng thread.

### 25.3. Downstream business handler lỗi

Nếu Service Activator ném exception, Gateway có thể nhận lỗi được wrap với Message/cause tùy chain. Không cho rằng mọi exception đều sẽ đi tới errorChannel trước khi quay lại Java caller; semantics của sync/async và error channel configuration khác nhau.

### 25.4. Reply không tới caller

Một Transformer có thể trả null/làm Filter discard, handler one-way không tạo reply, hoặc Message mới mất replyChannel; khi đó Gateway method có return type `QuoteReceipt` có thể timeout/không nhận kết quả theo contract của Gateway.

**Reply timeout không chứng minh business effect chưa xảy ra.** Một provider đã ghi lệnh nhưng response thất lạc vẫn có thể tạo timeout ở caller.

### 25.5. Error channel không phải mọi thứ đều tự bền

ErrorMessage có thể chứa Throwable, failedMessage và metadata liên quan tùy exception. Một errorChannel trong memory không tự là durable DLQ. Với gateway có error channel cấu hình, lỗi có thể được chuyển tới error flow và phản hồi biến đổi theo thiết kế; cần test return type và exception của Java caller.

### 25.6. Ma trận xử lý lỗi

| Triệu chứng | Nguyên nhân khả dĩ | Nên làm |
| --- | --- | --- |
| Gateway bean không có | Thiếu IntegrationComponentScan/config | Kiểm tra registration/package |
| Ambiguous payload | Hai Maps/multiple payloads không annotation | Thêm @Payload/@Headers |
| Header tenantId thiếu | Caller không truyền, Map sai key | Reject và sửa contract |
| Header là kiểu lạ | Raw map/string conversion sai | Parse/validate tại facade |
| CORRELATION_MISMATCH | Tenant/shipment/epoch khác | Reject, audit trust boundary |
| requestTimeout | Channel không nhận/queue full | Capacity/backpressure/route |
| replyTimeout | Không có reply/late reply | Kiểm tra replyChannel/handler contract |
| Result thuộc sai workflow | Business key trùng/không verified | Tenant/epoch scope, registry |
| Message bị redeliver | Broker ack/retry | Idempotency/recovery |
| Gateway trả null bất ngờ | No reply/error path hoặc timeout contract | Xem framework/version/return type |
| Remote side effect UNKNOWN | Timeout sau gửi request | Reconcile trước retry |

## 26. Retry, redelivery và idempotency: mapping headers phải ổn định

Khi một Gateway method được gọi lại do timeout, nó có thể tạo **MessageHeaders.ID** và temporary replyChannel mới. Nếu đó vẫn là **cùng logical operation**, businessEventId và businessCorrelationKey phải giữ nguyên.

~~~text
Attempt 1:
  Java Gateway invocation #1
  businessEventId = evt-quote-901
  businessCorrelationKey = quote:v1:tenant-a:SHIP-901:7
  Spring Message ID = msg-001
  replyChannel = temporary-A

Attempt 2:
  Java Gateway invocation #2
  businessEventId = evt-quote-901
  businessCorrelationKey = quote:v1:tenant-a:SHIP-901:7
  Spring Message ID = msg-002
  replyChannel = temporary-B
~~~

### 26.1. Một logical event không được sinh UUID mới ở mỗi retry

Nếu facade làm:

~~~java
// Phản ví dụ cho các operations cần idempotency.
String eventId = java.util.UUID.randomUUID().toString();
gateway.preview(command, tenant, eventId, groupKey);
~~~

thì mỗi retry cùng công việc mang eventId mới; một downstream ledger có thể coi đó là công việc khác và tạo side effect trùng. Chọn eventId từ **operation registry/persisted request identity** hoặc contract có định danh ổn định.

### 26.2. Preview thuần khác commit có side effect

QuotePreviewService trong bài là phép tính thuần từ QuoteCommand. Gọi nó hai lần có thể trả cùng giá mà không tạo thay đổi ngoài. Nhưng nếu flow được mở rộng thành **reserve shipment**, **charge fee**, **create order** hoặc **send notification**, retry có thể tạo side effects. Cần idempotency ngay tại handler/provider thực hiện effect.

### 26.3. SQL ledger minh họa

~~~sql
CREATE TABLE quote_operation_inbox (
    tenant_id VARCHAR(48) NOT NULL,
    producer_id VARCHAR(64) NOT NULL,
    event_id VARCHAR(96) NOT NULL,
    group_key VARCHAR(220) NOT NULL,
    shipment_id VARCHAR(64) NOT NULL,
    workflow_epoch INTEGER NOT NULL,
    payload_digest VARCHAR(128) NOT NULL,
    processing_status VARCHAR(32) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, producer_id, event_id)
);

CREATE INDEX quote_operation_pending_idx
    ON quote_operation_inbox (processing_status);
~~~

Key chính dùng tenant + producer + eventId **nếu eventId chỉ duy nhất trong namespace producer**. Nếu identity contract khác, cần thay schema cho phù hợp. Khi cùng identity nhưng `payload_digest` khác, đó là **ID_CONFLICT**, không phải duplicate bình thường.

### 26.4. Khoảng hở crash sau khi đánh dấu dedup

~~~text
1. INSERT inbox event, status=SEEN
2. Commit
3. Crash trước khi gửi Message tới downstream handler
4. Broker redeliver event
5. Dedup thấy SEEN rồi discard
=> Business effect có thể không bao giờ chạy
~~~

Thiết kế production có thể dùng **transactional inbox/outbox**, workflow state machine hoặc recovery worker để phân biệt RECEIVED, DISPATCH_PENDING, EFFECT_COMMITTED. Gateway method mapping tự thân không giải quyết distributed transaction.

### 26.5. Cùng operation nhưng khác transport attempt

Khi flow đi qua JMS/AMQP/HTTP, protocol correlation token có thể thay đổi theo attempt; **businessEventId/operationId** ở app vẫn ổn định. Không buộc JMSCorrelationID bằng business key nếu cấu hình Gateway giao thức cần unique request token riêng.

### 26.6. Late replies và final state

Một reply của attempt 1 có thể đến sau khi attempt 2 đã được gửi. Gateway temporary replyChannel của attempt 1 có thể không còn caller đang chờ. Nếu reply còn có ý nghĩa nghiệp vụ, cần persisted workflow state/reconciliation dựa trên **business key**. Không gửi reply muộn vào một invocation Java mới chỉ vì shipmentId giống nhau.

## 27. Security: header arguments không phải quyền truy cập

Một Java method nhìn có vẻ nội bộ:

~~~java
gateway.preview(command, tenantId, eventId, groupKey);
~~~

nhưng các arguments có thể bắt nguồn từ HTTP request, broker event hoặc file import. Một attacker có thể gửi tenantId của người khác nếu không có trust boundary.

### 27.1. Sai: map client header trực tiếp vào @Header của Gateway

~~~java
// Phản ví dụ không nên dùng.
String tenant = request.getHeader("X-Tenant-Id");
String eventId = request.getHeader("X-Event-Id");

return gateway.preview(
        command,
        tenant,
        eventId,
        QuoteIdentity.businessKey(tenant, command));
~~~

Phép tính groupKey khớp tenant input nhưng không chứng minh tenant input được phép. Một client có thể tự khai `tenant-admin` và tạo một business key hợp cú pháp.

### 27.2. Đúng về thứ tự trách nhiệm

~~~text
Authenticated principal
    -> verify tenant and shipment owner
    -> validate payload and workflowEpoch
    -> obtain stable event/operation identity
    -> compute trusted group key
    -> Gateway @Header arguments
    -> Message with allowlisted headers
~~~

### 27.3. @Headers Map có thể mang header điều khiển

Nếu một application truyền một Map do client kiểm soát, nó có thể chứa:

~~~text
trustedTenantId  = tenant-admin
replyChannel     = malicious-or-unintended-route
errorChannel     = arbitrary-route
routingSlip      = unexpected-internal-hop
~~~

Không pass-through Map đó vào Gateway. Dùng allowlist, bỏ các framework control headers và thiết lập reply/error routing bằng cấu hình tin cậy. Trong một số topologies framework có thể override/control một số headers, nhưng **không dựa vào điều này thay kiểm tra bảo mật**.

### 27.4. TraceId không phải authority

TraceRef/traceId do một client gửi có thể dùng cho quan sát sau khi kiểm tra, nhưng không nên làm business correlation, authorization hay idempotency key. Logs/traces có quyền truy cập và retention riêng; không log bearer tokens hoặc private payloads từ MessageHeaders.

### 27.5. Validation cần nhiều tầng

- **Payload:** command type, shipmentId, parcelCount, workflowEpoch.
- **Authenticated actor:** principal và tenant thực.
- **Binding:** shipment thuộc tenant, actor được phép preview.
- **Business group identity:** key tính/tra từ verified metadata.
- **Headers:** tên, type, length và source theo contract.
- **Transport:** source credentials, ACL, signature khi cần.
- **Downstream:** operationId, idempotency và authorization theo quyền của service.

**Không coi annotation @Header, @GatewayHeader hoặc SpEL là các bước xác thực.**

## 28. Quan sát: phát hiện mapping sai trước khi có sự cố nghiệp vụ

Khi một Gateway method trả lỗi, cần biết vấn đề là **argument mapping**, **send**, **downstream**, **reply** hay **business correlation**.

| Metric | Ý nghĩa | Labels phù hợp |
| --- | --- | --- |
| **gateway_invocation_total** | Tổng lời gọi Gateway | method, outcome |
| **gateway_argument_mapping_failed_total** | Không xác định payload/headers | method, reason |
| **gateway_request_send_failed_total** | Gửi Message lỗi | channel, reason |
| **gateway_reply_timeout_total** | Không nhận reply kịp | method |
| **gateway_business_correlation_mismatch_total** | Sai group identity | method |
| **gateway_header_missing_total** | Header bắt buộc thiếu ở receiver | headerName từ allowlist |
| **gateway_header_type_error_total** | Sai kiểu metadata | headerName, typeClass hữu hạn |
| **gateway_downstream_failed_total** | Handler lỗi | component, errorCode |
| **gateway_duplicate_event_total** | Redelivery bị dedup | operationType |
| **gateway_inbox_pending** | Operation chưa commit | state |
| **gateway_integration_latency_seconds** | End-to-end invocation latency | method |
| **gateway_wire_mapping_failure_total** | Lỗi serialize/deserialize qua adapter | protocol |

Không đặt eventId, shipmentId, tenantId, traceId hoặc businessCorrelationKey trực tiếp làm metric label vì cardinality cao và có thể rò rỉ dữ liệu. Dùng structured logs/traces có retention, redaction và quyền truy cập.

### 28.1. Log mẫu trên Gateway ingress

~~~json
{
  "component": "shippingQuoteGateway",
  "method": "preview",
  "payloadType": "QuoteCommand",
  "gatewaySource": "JAVA_APP",
  "operationKind": "PREVIEW",
  "eventRef": "evt-quote-901",
  "outcome": "SENT"
}
~~~

### 28.2. Log mẫu khi mapping gặp lỗi

~~~json
{
  "component": "quotePreviewService",
  "stage": "HEADER_VALIDATION",
  "headerName": "businessCorrelationKey",
  "reason": "CORRELATION_MISMATCH",
  "outcome": "REJECTED"
}
~~~

Đây là các **log do ứng dụng định nghĩa**, không phải log tự sinh chính xác của Spring Integration. Một mapping error có thể xảy ra **trước khi Message được gửi vào channel**, vì vậy instrumentation chỉ đặt trong Service Activator sẽ bỏ sót lỗi Gateway method-to-message.

### 28.3. Phân biệt trace IDs và business IDs

- TraceId liên kết spans/requests để quan sát.
- BusinessEventId định danh logical event phục vụ dedup.
- BusinessCorrelationKey định danh workflow/group có thể trải nhiều events.
- Temporary replyChannel định danh reply destination của một Gateway invocation.
- Transport correlation định danh attempt request/reply qua giao thức.

Không đặt tất cả vào một header tên `correlationId` mà không xác định scope.

## 29. Runbook: Gateway nhận đủ arguments nhưng downstream thiếu header

**Triệu chứng:** Java caller gọi `gateway.preview(command, tenant, eventId, groupKey)`, nhưng Service Activator hoặc Router không thấy `businessEventId` hoặc `trustedTenantId`.

### Bước 1 — Xác minh đúng Gateway proxy

Kiểm tra interface có `@MessagingGateway`, cấu hình `@IntegrationComponentScan` quét đúng package và bean được Spring đăng ký. Không dùng một class tự implement interface rồi gọi nó, vì khi đó annotations không tự tạo Spring Message.

### Bước 2 — Đối chiếu method signature

~~~java
QuoteReceipt preview(
        @Payload QuoteCommand command,
        @Header("trustedTenantId") String tenantId,
        @Header("businessEventId") String eventId,
        @Header("businessCorrelationKey") String groupKey);
~~~

Kiểm tra có đổi annotation/tên header khi refactor không. Nếu có Map, xác định nó là `@Payload Map` hay `@Headers Map`, không để signature mơ hồ.

### Bước 3 — Kiểm tra default/method headers

Nếu header được cấp bằng `@GatewayHeader`, xem lại `name`, `value`, `expression` và precedence. Một method-specific header có thể override default/parameter header trong cấu hình tương ứng. Tránh trùng tên header do hai nơi cùng sở hữu.

### Bước 4 — Xem Message ngay sau Gateway

Dùng một test handler, wire tap hoặc endpoint instrumentation để quan sát **những header có trong Spring Message** trước khi đi qua Transformer/adapter. Chỉ log key names/giá trị đã redact; không log nguyên replyChannel hoặc security tokens.

Nếu Message ngay sau Gateway đã thiếu businessEventId, sửa mapping ở Gateway/facade. Nếu header có ở đó nhưng mất downstream, chuyển sang bước 5.

### Bước 5 — Tìm Transformer hoặc HeaderFilter thay đổi Message

Nếu Transformer chỉ trả payload, framework thường propagate inbound headers theo quy tắc của endpoint. Nếu handler tự dựng Message mới, kiểm tra selected headers được giữ thế nào. Một HeaderFilter có thể chủ động loại field.

### Bước 6 — Kiểm tra adapter boundary

Qua HTTP/JMS/AMQP/TCP, HeaderMapper có thể chỉ chuyển một subset headers hoặc serializer chỉ gửi payload. Kiểm tra outbound wire contract và inbound mapping thay vì mong @Header tự hoạt động qua network.

### Bước 7 — Kiểm tra kiểu và giá trị

~~~text
Required Spring header:
  businessEventId: String "evt-quote-901"

Actual:
  X-Event-Id: List<String> ["evt-quote-901"]
~~~

Đây là **hai tên/kiểu khác nhau**. Normalize tại ingress hoặc adapter, không để domain handler tự parse tùy tiện các dạng headers của từng giao thức.

### Bước 8 — Phân biệt header lỗi và reply lỗi

Nếu Service Activator nhận đúng header nhưng Gateway vẫn timeout, kiểm tra **replyChannel**, handler có trả result không, có Filter discard hay send vào QueueChannel riêng không. Không sửa businessCorrelationKey để chữa một replyChannel sai.

### Bước 9 — Kiểm tra error flow và retry

Missing header thường là lỗi schema/config/authorization; retry nguyên input liên tục không làm header tự xuất hiện. Nếu lỗi transient ở DB/network, retry bounded và giữ cùng logical identity.

### Bước 10 — Xác nhận sau sửa

Một contract test cần assert:

~~~text
@Payload QuoteCommand:
  shipmentId = SHIP-901
  serviceLevel = EXPRESS

Spring headers:
  trustedTenantId = tenant-a
  businessEventId = evt-quote-901
  businessCorrelationKey = quote:v1:tenant-a:SHIP-901:7
  gatewaySource = JAVA_APP
  operationKind = PREVIEW

Java return:
  QuoteReceipt for SHIP-901, 160000 VND
~~~

Sau happy path, chạy negative tests: wrong tenant, group mismatch, missing header, two Maps ambiguous, timeout và adapter mapping qua wire.

## 30. Bài thực hành: Gateway API cho xử lý đơn hàng

Xây dựng `OrderProcessingGateway` có ba tác vụ:

1. **validateOrder:** validate dữ liệu và trả `ValidationReceipt`.
2. **reserveInventory:** gửi lệnh giữ hàng và trả `ReservationReceipt`.
3. **publishAudit:** gửi event audit một chiều.

Các phương thức đều sử dụng cùng mẫu **typed payload + method arguments làm headers**, nhưng có hợp đồng request/reply khác nhau.

### 30.1. Phác thảo interface

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.GatewayHeader;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

@MessagingGateway(
        defaultRequestChannel = "orderCommands",
        defaultHeaders = @GatewayHeader(
                name = "gatewaySource", value = "ORDER_APP"))
interface OrderProcessingGateway {

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "VALIDATE"))
    ValidationReceipt validateOrder(
            @Payload OrderCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId);

    @Gateway(
            headers = @GatewayHeader(
                    name = "operationKind", value = "RESERVE"),
            replyTimeout = 3_000)
    ReservationReceipt reserveInventory(
            @Payload OrderCommand command,
            @Headers java.util.Map<String, Object> verifiedHeaders);

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "AUDIT"))
    void publishAudit(
            @Payload AuditEvent event,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId);
}
~~~

Trong snippet này `OrderCommand`, `AuditEvent`, `ValidationReceipt` và `ReservationReceipt` là **DTO placeholders** để người học tự định nghĩa. Không thể copy nguyên interface vào một project mà chưa tạo DTOs/flows/channels tương ứng.

### 30.2. Hợp đồng metadata

| Header | validateOrder | reserveInventory | publishAudit |
| --- | --- | --- | --- |
| `gatewaySource` | ORDER_APP cố định | ORDER_APP cố định | ORDER_APP cố định |
| `operationKind` | VALIDATE | RESERVE | AUDIT |
| `trustedTenantId` | Argument @Header | Map @Headers đã verified | Argument @Header |
| `businessEventId` | Argument @Header | Map @Headers đã verified | Argument @Header |
| `businessCorrelationKey` | Theo nhu cầu workflow | Bắt buộc trong verified Map | Theo audit contract |
| `replyChannel` | Gateway runtime | Gateway runtime | One-way semantics |

**Cần có facade bảo vệ reserveInventory**: Map không được lấy nguyên từ HTTP request, và inventory reservation cần operation ID ổn định cùng idempotency. Trường hợp inventory service timeout không được tự kết luận hàng chưa được giữ.

### 30.3. Những việc cần làm

1. Định nghĩa DTO/enum có validation rõ cho OrderCommand và AuditEvent.
2. Tạo authenticated application context, authorize tenant/order.
3. Định nghĩa stable businessEventId/operationId và businessCorrelationKey theo workflow.
4. Dựng Gateway interface với `@MessagingGateway`, `@Gateway`, `@Payload`, `@Header` và `@Headers`.
5. Tạo Router theo `operationKind`, map đúng ba subflows.
6. Subflow VALIDATE nhận headers và trả ValidationReceipt.
7. Subflow RESERVE nhận headers, lưu ledger/idempotency rồi trả ReservationReceipt.
8. Subflow AUDIT gửi one-way với error policy, không chờ reservation result.
9. Thêm negative route cho operationKind không hỗ trợ.
10. Đặt Gateway request/reply timeout hữu hạn; phân biệt timeout với business deadline.
11. Test header names, types, precedence, Map validation và reply lifecycle.
12. Thêm test cùng orderId khác tenant; cùng eventId replay và eventId conflict.
13. Thử một Transformer trả Message mới làm mất header; sửa bằng trusted header strategy.
14. Nếu có adapter ngoài, kiểm tra wire header mapping và callback correlation.
15. Thêm tracing, monitoring, DLQ/recovery khi có broker/async processing.

### 30.4. Ma trận kiểm thử

| Case | Tình huống | Kỳ vọng |
| --- | --- | --- |
| A | VALIDATE có đủ arguments | Message đúng payload và headers |
| B | RESERVE dùng verified Map | Tất cả keys được map đúng |
| C | AUDIT void method | Không chờ Java business result |
| D | Thiếu trustedTenantId | Reject, không xử lý lệnh |
| E | eventId rỗng hoặc null | Reject/quarantine |
| F | Correlation không khớp tenant/order | Reject theo policy |
| G | GatewayHeader và Header cùng tên | Phát hiện precedence; sửa thiết kế |
| H | Hai Map không annotation | Mapping mơ hồ, không chấp nhận |
| I | OrderId trùng giữa hai tenants | Hai group identities độc lập |
| J | Retry RESERVE cùng operationId | Không tạo hai reservations |
| K | Reply RESERVE mất sau commit | Reconcile, không reserve lại vô điều kiện |
| L | DirectChannel handler chậm | Không hiểu replyTimeout là hard execution deadline |
| M | ExecutorChannel đổi thread | Context không phụ thuộc ThreadLocal |
| N | Transformer làm mất replyChannel | Test bắt lỗi reply path |
| O | Callback sau Gateway timeout | Workflow xử lý late event theo policy |
| P | JMS/AMQP header mapping khác tên | Adapter contract test phát hiện |

### 30.5. Tiêu chí đạt

Người đọc interface Gateway biết ngay:

- Payload chính của từng operation nằm ở đâu.
- Header nào được truyền qua một argument @Header.
- Header nào là cấu hình tĩnh bằng @GatewayHeader.
- Header nào được đưa qua @Headers Map và ai kiểm tra nó.
- Method nào chờ typed reply, method nào one-way.
- Correlation/event identity được tạo và xác minh tại đâu.
- Cơ chế retry/idempotency xử lý lệnh có side effect thế nào.

Nếu phải đọc toàn bộ implementation để biết argument thứ hai là tenant hay payload phụ, method signature chưa đủ tường minh.

## 31. Câu hỏi tự kiểm tra

1. Gateway method arguments được biến thành Spring Message như thế nào?
2. @MessagingGateway và @Gateway khác vai trò ở đâu?
3. Trong Gateway, `@Header("trustedTenantId") String tenantId` mapping theo chiều nào?
4. Trong Service Activator, `@Header("trustedTenantId") String tenantId` mapping theo chiều nào?
5. Khi có nhiều arguments, vì sao nên dùng @Payload tường minh?
6. Một method có một Map argument không annotation sẽ được hiểu thế nào?
7. Nếu method có hai Map arguments không annotation thì vấn đề gì xảy ra?
8. @Headers Map khác @Payload Map như thế nào?
9. Có thể gắn @Payload và @Header lên cùng một argument không?
10. Một Gateway method có thể có hai @Payload arguments độc lập không?
11. @GatewayHeader(name=..., value=...) khác @Header trên parameter như thế nào?
12. defaultHeaders của @MessagingGateway và headers của @Gateway khác scope ra sao?
13. Nếu default header và parameter @Header cùng tên, giá trị nào có thể được ưu tiên?
14. Nếu method-specific header và parameter @Header trùng tên, cần làm gì để tránh bất ngờ?
15. Header expression `method.name` có thể dùng cho mục đích gì?
16. Vì sao không serialize nguyên đối tượng java.lang.reflect.Method vào broker property?
17. Khi nào cần MethodArgsMessageMapper thay vì annotations?
18. Vì sao không đưa raw HTTP headers Map trực tiếp qua Gateway @Headers?
19. Một client truyền `tenant-admin` qua @Header có tự được authorization không?
20. businessCorrelationKey và temporary replyChannel của Gateway khác nhau ở điểm nào?
21. requestTimeout và replyTimeout có tự ngắt một DirectChannel handler đang xử lý lâu không?
22. Nếu Service Activator gửi reply vào một QueueChannel không nối Gateway, caller sẽ thấy gì?
23. Gateway method trả void có tự chứng minh external effect hoàn tất không?
24. Tại sao Spring MessageHeaders.ID không phù hợp làm businessEventId qua retries?
25. Một Transformer tạo Message mới có thể làm mất header nào?
26. Khi nào nên dùng MessageBuilder.fromMessage thay vì dựng từ raw external message?
27. Vì sao Aggregator không tự nhóm theo businessCorrelationKey chỉ vì Gateway đã gắn header đó?
28. Technical correlationId của Splitter có bắt buộc giống business correlation key không?
29. Khi Gateway gọi JMS/AMQP outbound gateway, cần phân biệt những correlation identities nào?
30. Vì sao test gọi Gateway proxy tốt hơn unit test gọi handler trực tiếp cho yêu cầu mapping?
31. Những negative tests nào cần có để chặn tenant/group spoofing?
32. Khi một event bị redeliver, những identity nào cần giữ nguyên và identity nào có thể đổi?
33. Khi reply timeout sau khi provider đã tạo reservation, có được retry mù quáng không?
34. Nếu một Gateway expression dựa vào `args[2]`, thay đổi thứ tự method signature có thể gây lỗi gì?
35. Header nào nên là application metadata, header nào chỉ nên tồn tại ở framework runtime?
36. Những bước nào giúp điều tra khi Gateway mapping đúng nhưng HTTP/JMS adapter làm mất header?

## 32. Checklist trước khi triển khai Gateway header mapping

- Gateway interface có @MessagingGateway và được @IntegrationComponentScan hoặc cấu hình proxy tương đương đăng ký.
- Mỗi method có requestChannel/defaultRequestChannel đúng owner và consumer.
- Payload argument được xác định tường minh bằng @Payload khi signature phức tạp.
- Những headers theo invocation sử dụng @Header với tên rõ và nhất quán.
- Những tập headers động chỉ dùng @Headers Map khi đã validate/allowlist.
- Một Map duy nhất được đánh dấu @Payload khi nó thực sự là body.
- Không có hai payload arguments hoặc một argument vừa @Payload vừa @Header/@Headers.
- Header cố định theo interface dùng defaultHeaders; header cố định theo method dùng @Gateway(headers=...).
- SpEL header expression được kiểm tra và không bị phụ thuộc vào argument positions mơ hồ.
- Không trùng tên header giữa default/method/parameter nếu không có contract ưu tiên rõ và tests.
- Không sử dụng tên header của một giao thức (ví dụ X-Tenant-Id) làm Spring trusted header mà chưa map và xác minh.
- Business identity được tạo từ authenticated principal, tenant, entity và workflow epoch.
- eventId/operationId ổn định giữa các attempts của cùng logical work.
- businessCorrelationKey có namespace/version rõ ràng và nhất quán trong toàn flow.
- Không dùng MessageHeaders.ID, traceId hoặc replyChannel làm business idempotency key.
- Không truyền arbitrary control headers như replyChannel/errorChannel/routingSlip qua external Map.
- Gateway method có return type phù hợp: typed reply hoặc void one-way.
- Request/reply flow có đường reply tới Gateway-managed temporary channel.
- requestTimeout/replyTimeout được đặt phù hợp channel semantics, không bị nhầm với business deadline.
- Router downstream dùng operationKind allowlist, không chuyển raw destination name do client gửi.
- Transformer/handler có chiến lược giữ những trusted headers cần thiết.
- Nếu flow có Splitter/Aggregator, technical sequence/correlation khác business key được xử lý đúng scope.
- HeaderMapper và MessageConverter từng HTTP/JMS/AMQP/TCP adapter có contract tests.
- External callback có persisted correlation, không phụ thuộc temporary replyChannel hết hiệu lực.
- DirectChannel/ExecutorChannel/QueueChannel semantics được kiểm tra và có backpressure bounded.
- Missing/invalid header được reject trước khi gây side effect.
- Error channel/DLQ/quarantine có semantics đúng với sync/async, retry và retention.
- Retry phân biệt schema/auth lỗi vĩnh viễn với transient infrastructure errors.
- Side effects dùng ledger/transaction/idempotency key và có recovery sau crash.
- Unit tests kiểm tra business handler với Map header values giả lập.
- Spring context integration tests thực sự gọi Gateway proxy và assert reply đọc được header values.
- Negative tests bao gồm wrong correlation, missing header, wrong type, ambiguous Map, header precedence và tenant spoofing.
- Test nhiều tenants cùng shipmentId và retry cùng eventId để tránh false joins/duplicate effects.
- Logs/metrics phân biệt mapping, send, handler, reply và adapter errors, không lộ secrets/PII.
- Runbook cho phép tìm điểm mất header từ caller → proxy → Message → subflow → adapter → reply.

## 33. Tổng kết

**Gateway header mapping từ method argument** là khả năng chuyển API Java thông thường thành Spring Message có **payload và headers tường minh**:

~~~java
@MessagingGateway(defaultRequestChannel = "quoteRequests")
interface QuoteGateway {

    @Gateway(headers = @GatewayHeader(
            name = "operationKind", value = "PREVIEW"))
    QuoteReceipt preview(
            @Payload QuoteCommand command,
            @Header("trustedTenantId") String tenantId,
            @Header("businessEventId") String eventId,
            @Header("businessCorrelationKey") String groupKey);
}
~~~

~~~text
Java call arguments
  | @Payload -> Message.payload
  | @Header  -> individual Message.headers
  | @Headers -> multiple Message.headers from Map
  | @GatewayHeader -> static/SpEL-defined headers
  v
Request channel
  -> Router / Transformer / Service Activator
  -> reply / error
  -> Java method return
~~~

Giá trị của thiết kế nằm ở **hợp đồng rõ ràng giữa caller và flow**: ứng dụng không cần trực tiếp dựng Message cho từng lời gọi, còn downstream đọc cùng những header nhất quán. Tuy nhiên, annotation chỉ ánh xạ **dữ liệu**, không xác minh **quyền**, không tự tạo **correlation strategy**, không bảo đảm **reply path** hay **exactly-once side effects**.

Với các luồng Spring Integration có Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry và error channel, hãy kết hợp **verified facade + typed @Payload/@Header + Gateway/Service Activator contract tests + persistent idempotency**. Nhờ vậy thông tin tenant, eventId và business correlation được truyền đúng qua nhiều nhánh mà không rò rỉ control headers hoặc làm sai workflow khi timeout, retry hay giao lại message.

## Tài liệu tham khảo

- [Enterprise Integration Patterns — Messaging Gateway](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingGateway.html): pattern che giấu Messaging API khỏi business application.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): GatewayProxyFactoryBean, @MessagingGateway, @Gateway, mapping method arguments, header expressions, reply channels, timeouts và error handling.
- [Spring Integration API — @Gateway](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/Gateway.html): method-level request/reply settings, header configuration và payload expression.
- [Spring Integration API — @GatewayHeader](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/GatewayHeader.html): name, value và expression cho header tĩnh/động.
- [Spring Integration Reference — Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html): @EnableIntegration, endpoint annotations và IntegrationComponentScan.
- [Spring Framework API — @Header](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html): đặt tên header cho method argument.
- [Spring Framework API — @Headers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html): mapping Map headers.
- [Spring Framework API — @Payload](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Payload.html): lựa chọn payload và SpEL.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): IntegrationFlow, handler lambdas và channel wiring.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): mapping từ Message vào Java handler method và reply.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): Header Value Router, routing theo metadata và default route.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): transformation và header propagation.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): technical correlation và sequence headers.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation strategy, release strategy và group timeout.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, ExecutorChannel, QueueChannel và dispatch semantics.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage/errorChannel và sync/async errors.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): dedup và giới hạn của idempotency advice.
