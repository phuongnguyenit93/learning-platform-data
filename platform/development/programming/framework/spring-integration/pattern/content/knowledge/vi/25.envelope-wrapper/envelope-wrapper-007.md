# Truyền envelope qua subflow

## 1. Bối cảnh: thông điệp rẽ nhánh nhưng không được đánh mất ngữ cảnh

Trong chương **Envelope wrapper** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai Enterprise Integration Patterns bằng **Spring Integration** để xây dựng các luồng thông điệp ít phụ thuộc và dễ mở rộng. Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation thường được kết hợp trong một ứng dụng. Khi một message đi từ luồng chính vào **subflow**, câu hỏi không chỉ là “payload có tới handler không?” mà còn là “**ngữ cảnh nào phải còn nguyên khi message trở lại luồng chung?**”

Ví dụ hệ thống tính phí vận chuyển nhận yêu cầu:

~~~json
{
  "metadata": {
    "schemaVersion": 1,
    "tenantId": "tenant-a",
    "eventId": "evt-ship-901",
    "businessCorrelationKey": "shipping:tenant-a:SHIP-901:7",
    "traceId": "trace-901",
    "sourceSystem": "ORDER_SERVICE",
    "receivedAt": "2026-11-21T03:00:00Z"
  },
  "payload": {
    "shipmentId": "SHIP-901",
    "serviceLevel": "EXPRESS",
    "packageCount": 2
  }
}
~~~

Luồng có thể chọn **standardSubflow** hoặc **expressSubflow** để tính giá, rồi hội tụ vào một kênh kết quả. Nếu handler chỉ trả về giá tiền, không còn tenant, eventId, business correlation hay traceId, downstream có thể không biết kết quả thuộc yêu cầu nào. Nếu handler tự sinh các metadata mới mỗi khi retry, những lần giao lại cùng sự kiện có thể bị coi là công việc khác nhau.

~~~mermaid
flowchart LR
    I["Trusted ingress"] --> E["DomainEnvelope: metadata + request"]
    E --> R{"Router: service level"}
    R -->|"STANDARD"| S["standardSubflow"]
    R -->|"EXPRESS"| X["expressSubflow"]
    S --> M["DomainEnvelope: metadata + quote"]
    X --> M
    M --> V["Common validation"]
    V --> O["Business output / persistence"]
    R -.->|"UNKNOWN"| Q["Reject / quarantine"]
~~~

**Ý tưởng trọng tâm:** với một envelope mang ngữ cảnh nghiệp vụ, subflow **thay đổi phần payload theo trách nhiệm của mình** nhưng vẫn giữ những metadata cần thiết để định tuyến, quan sát, đối soát, xử lý lỗi và idempotency. Điều đó không có nghĩa mọi header hoặc mọi trường đều phải copy vô điều kiện.

### Mục tiêu bài học

1. Phân biệt **Envelope Wrapper (EIP)** với **Spring Message** gồm payload và headers, cũng như wire envelope của HTTP/JMS/AMQP.
2. Thiết kế một envelope bất biến, có version và đủ identity/ngữ cảnh nhưng không mang tùy ý đối tượng hạ tầng.
3. Truyền envelope qua Router và các **IntegrationFlow con** mà không mất business correlation và eventId.
4. Hiểu sự khác nhau giữa **biến đổi payload bên trong envelope**, **unwrap/re-wrap**, và **tạo Message mới**.
5. Xử lý ngữ cảnh qua Splitter, publish-subscribe, Scatter-Gather, Gateway và adapter một cách có chủ đích.
6. Bảo vệ metadata qua validation, retry, timeout, redelivery, multi-tenant và các ranh giới trust.
7. Viết Java DSL, unit test và integration test chứng minh các bất biến được giữ xuyên subflow.

## 2. Envelope Wrapper là gì?

Theo Enterprise Integration Patterns, **Envelope Wrapper** bọc một message bằng một cấu trúc bao ngoài để mang các thông tin mà ứng dụng hoặc hệ thống tích hợp cần, trong khi phần nội dung nghiệp vụ nằm bên trong. Bọc/giải bọc có thể được thực hiện khi đi qua một môi trường yêu cầu biểu diễn khác.

~~~text
Envelope
├── metadata
│   ├── schemaVersion
│   ├── tenantId
│   ├── businessCorrelationKey
│   ├── eventId
│   └── trace context
└── payload
    ├── shipmentId
    ├── serviceLevel
    └── packageCount
~~~

Không phải mọi trường trong metadata đều bắt buộc cho mọi hệ thống. Một envelope tốt phải có **hợp đồng rõ ràng**: field nào do ingress cấp, field nào được phép đổi ở subflow, field nào được serialize ra ngoài và field nào chỉ dùng nội bộ.

### 2.1. Ba lớp thường bị gọi nhầm là “envelope”

| Lớp | Ví dụ | Phạm vi | Ai sở hữu? |
| --- | --- | --- | --- |
| **Domain/Application envelope** | DomainEnvelope(metadata, payload) | Qua subflow hoặc qua wire khi đã có schema rõ | Ứng dụng, hợp đồng nghiệp vụ |
| **Spring Message wrapper** | Message payload + MessageHeaders | Trong Spring Integration runtime | Framework và endpoint |
| **Transport envelope** | HTTP headers/body, JMS properties, AMQP properties, TCP frame | Qua network/broker | Protocol adapter và wire contract |

Một Spring Message có thể có **payload là DomainEnvelope**:

~~~text
Spring Message
  headers:
    id: generated framework message id
    replyChannel: runtime channel (nếu có)
    errorChannel: runtime channel (nếu có)
    trace/broker/sequence headers...
  payload:
    DomainEnvelope
      metadata: tenantId, eventId, correlationKey, schemaVersion...
      payload: DeliveryRequest
~~~

Như vậy có **hai lớp wrapper** nhưng không phải lỗi thiết kế. Lớp bên ngoài được framework dùng để thực thi luồng; lớp ứng dụng có thể tồn tại sau khi serialize, lưu bền hoặc được truyền sang service khác.

### 2.2. Không nhầm Envelope Wrapper với Normalizer

| Pattern | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Envelope Wrapper** | Dữ liệu và ngữ cảnh nào phải đi cùng nhau? | Bọc quote request với eventId/tenant/correlation |
| **Normalizer** | Các schema khác nhau quy về một schema nào? | ERP JSON và CSV → CanonicalOrder |
| **Content-Based Router** | Message đi nhánh nào? | STANDARD → standardSubflow |
| **Transformer** | Payload hoặc cấu trúc Message được đổi thế nào? | DeliveryRequest → DeliveryQuote |
| **Aggregator** | Những messages nào phải gom lại? | Nhiều supplier replies → một báo cáo |

Một Normalizer có thể chuyển **payload bên trong** một DomainEnvelope. Một Router có thể đọc thông tin từ payload/envelope để chọn subflow. Một Aggregator có thể nhóm theo businessCorrelationKey được truyền qua envelope. Các pattern hỗ trợ nhau; **Envelope Wrapper không tự thay thế Router/Transformer/Aggregator**.

### 2.3. Vì sao subflow làm rủi ro lộ rõ?

Một IntegrationFlow con có thể:

- Nhận cùng message rồi thay đổi payload bằng Transformer.
- Trả một **Message hoàn chỉnh**, khiến headers không được propagate như trường hợp chỉ trả payload.
- Trả **chỉ payload**, khiến envelope của ứng dụng bị mất.
- Gửi sang Gateway/adapter, nơi không phải header nào cũng đi qua wire.
- Split thành nhiều messages con có sequencing/correlation riêng.
- Xử lý bất đồng bộ với retry, khiến một message được tạo lại từ dữ liệu đã lưu.

Nếu thiết kế “envelope luôn tự được giữ” mà không kiểm chứng những điểm này, lỗi có thể chỉ xuất hiện khi retry, khi đổi channel sang ExecutorChannel hoặc khi thay connector.

## 3. Hợp đồng truyền envelope qua subflow

Trước khi viết Java DSL, định nghĩa những bất biến:

| Dữ liệu | Khi vào một subflow | Khi ra subflow | Lý do |
| --- | --- | --- | --- |
| **tenantId** | Đã được xác minh | **Không đổi** | Cô lập tenant |
| **eventId** | Identity logical event | **Không đổi** nếu cùng logical event | Dedup/redelivery |
| **businessCorrelationKey** | Workflow/group ID | **Không đổi** trong cùng workflow | Correlation |
| **schemaVersion** | Version envelope hiện tại | Giữ nguyên hoặc migrate **có kiểm soát** | Consumer hiểu đúng schema |
| **traceId** | Context quan sát | Giữ liên kết trace; spanId có thể thay | Tracing |
| **sourceSystem** | Nguồn đã xác thực | **Không tự nhận nguồn khác** | Audit |
| **receivedAt** | Thời gian ingress cấp | **Không đổi** | Phân biệt original ingress và processing time |
| **payload** | DeliveryRequest | Thành DeliveryQuote | Trách nhiệm Transformer |
| **attemptId** | Tùy lần retry | **Có thể đổi** mỗi attempt | Quan sát vận hành |
| **replyChannel** | Runtime Spring header | Do framework quản lý | Không phải domain metadata |

Không viết một hàm “copy mọi thứ từ input sang output” nếu trong input có dữ liệu chưa tin cậy. **Bảo toàn có chọn lọc theo hợp đồng** khác với **sao chép mù quáng**.

### 3.1. Contract “same logical event” và “new derived event”

Không phải lúc nào eventId cũng phải giữ nguyên:

- **Transformer nội bộ:** cùng logical event được đổi biểu diễn, thường giữ eventId.
- **Splitter tạo nhiều child events độc lập:** mỗi child cần identity riêng nếu dedup/side effects theo từng child.
- **Một business event mới được phát ra:** có thể cần eventId mới và parentEventId/causationId để liên kết.

Ví dụ:

~~~text
Original eventId: evt-shipment-901

Route đến EXPRESS subflow rồi tính quote:
  eventId: evt-shipment-901      (cùng logical work, đổi representation)

Split 3 parcels để tính độc lập:
  child event IDs:
    evt-shipment-901:parcel:1
    evt-shipment-901:parcel:2
    evt-shipment-901:parcel:3
  parentEventId: evt-shipment-901
  businessCorrelationKey: shipping:tenant-a:SHIP-901:7
~~~

Không dùng chung một eventId cho ba child business effects rồi để inbox xem child thứ hai và thứ ba là duplicate của child thứ nhất.

### 3.2. Bản chất bất biến không có nghĩa object luôn cùng một instance

Khi chuyển từ DomainEnvelope\<DeliveryRequest\> sang DomainEnvelope\<DeliveryQuote\>, subflow sẽ tạo **object envelope mới** với metadata không đổi. Unit test nên so sánh **giá trị metadata**, không cần yêu cầu cả input và output là cùng Java object identity.

Nếu metadata là immutable record, các subflow có thể chia sẻ cùng instance metadata an toàn khi không mutation. Nếu metadata chứa Map/List mutable, phải defensive copy hoặc dùng immutable structures; record chỉ bất biến nông nếu các field tham chiếu còn mutable.

## 4. Thiết kế DomainEnvelope có kiểu và bất biến

Java 17 records giúp định nghĩa một contract gọn và rõ:

~~~java
import java.time.Instant;
import java.util.Objects;

record EnvelopeMetadata(
        int schemaVersion,
        String tenantId,
        String eventId,
        String businessCorrelationKey,
        String traceId,
        String sourceSystem,
        Instant receivedAt) {

    EnvelopeMetadata {
        if (schemaVersion != 1) {
            throw new IllegalArgumentException("UNSUPPORTED_ENVELOPE_VERSION");
        }
        if (tenantId == null
                || !tenantId.matches("[a-z0-9_-]{1,48}")) {
            throw new IllegalArgumentException("INVALID_TENANT_ID");
        }
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_:-]{1,120}")) {
            throw new IllegalArgumentException("INVALID_EVENT_ID");
        }
        if (businessCorrelationKey == null
                || businessCorrelationKey.isBlank()
                || businessCorrelationKey.length() > 200) {
            throw new IllegalArgumentException("INVALID_CORRELATION_KEY");
        }
        if (traceId == null || traceId.isBlank()
                || traceId.length() > 128) {
            throw new IllegalArgumentException("INVALID_TRACE_ID");
        }
        if (sourceSystem == null || sourceSystem.isBlank()
                || sourceSystem.length() > 80) {
            throw new IllegalArgumentException("INVALID_SOURCE");
        }
        Objects.requireNonNull(receivedAt, "receivedAt");
    }
}

record DomainEnvelope<T>(
        EnvelopeMetadata metadata,
        T payload) {

    DomainEnvelope {
        Objects.requireNonNull(metadata, "metadata");
        Objects.requireNonNull(payload, "payload");
    }

    <R> DomainEnvelope<R> mapPayload(R nextPayload) {
        return new DomainEnvelope<>(metadata, nextPayload);
    }
}
~~~

**mapPayload()** là thao tác cốt lõi của bài: tạo envelope mới với **metadata gốc** nhưng payload có kiểu khác. Nó không ghi đè eventId/tenantId, không thay đổi sourceSystem và không phát sinh một businessCorrelationKey mới mỗi lần đi qua subflow.

### 4.1. DomainEnvelope không mặc định là DTO có thể nhận từ client

Kẻ gửi có thể tự dựng JSON với tenantId="tenant-admin" và eventId bất kỳ. Record constructor chỉ kiểm tra cú pháp, **không xác minh quyền**. Tại ingress phải:

1. Parse wire message theo schemaVersion được hỗ trợ và giới hạn kích thước.
2. Xác thực client/producer bằng token, mTLS hoặc broker ACL thích hợp.
3. Tra tenant và business workflow từ nguồn đáng tin.
4. **Tạo EnvelopeMetadata nội bộ** bằng thông tin đã xác minh.
5. Chỉ sau đó đưa DomainEnvelope vào channel dành cho trusted envelopes.

Không cho external adapter nối trực tiếp tới subflow nội bộ vốn giả định metadata đã đáng tin.

### 4.2. Chọn identity source và correlation đúng scope

Nếu hai tenants có shipmentId cùng là SHIP-901, chỉ dùng shipmentId làm businessCorrelationKey sẽ gây trộn nhóm. Nếu cùng shipment trải qua hai phiên xử lý hợp lệ, phải phân biệt **workflow epoch**.

~~~text
tenant-a / SHIP-901 / epoch 7:
  shipping:tenant-a:SHIP-901:7

tenant-b / SHIP-901 / epoch 7:
  shipping:tenant-b:SHIP-901:7

tenant-a / SHIP-901 / epoch 8:
  shipping:tenant-a:SHIP-901:8
~~~

Tính hoặc tra correlation key từ verified tenant + workflow identity **một lần ở điểm vào**, và giữ key đó qua subflows. Đừng chọn epoch mới chỉ vì broker redeliver message cũ.

## 5. Ví dụ nghiệp vụ: cùng một request, hai cách tính phí

Để tách phần routing khỏi giao thức vận chuyển, ta dùng hai service levels: STANDARD và EXPRESS. Mỗi nhánh trả về cùng một kiểu DeliveryQuote, nhưng có logic tính phí khác nhau.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

enum ServiceLevel {
    STANDARD,
    EXPRESS
}

record DeliveryRequest(
        String shipmentId,
        ServiceLevel serviceLevel,
        int packageCount) {

    DeliveryRequest {
        if (shipmentId == null
                || !shipmentId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("INVALID_SHIPMENT_ID");
        }
        Objects.requireNonNull(serviceLevel, "serviceLevel");
        if (packageCount < 1 || packageCount > 1_000) {
            throw new IllegalArgumentException("INVALID_PACKAGE_COUNT");
        }
    }
}

record DeliveryQuote(
        String shipmentId,
        ServiceLevel serviceLevel,
        BigDecimal amountVnd) {

    DeliveryQuote {
        Objects.requireNonNull(shipmentId, "shipmentId");
        Objects.requireNonNull(serviceLevel, "serviceLevel");
        Objects.requireNonNull(amountVnd, "amountVnd");
        if (amountVnd.signum() < 0 || amountVnd.scale() > 0) {
            throw new IllegalArgumentException("INVALID_VND_AMOUNT");
        }
    }
}
~~~

Trong thực tế, phí vận chuyển thường còn phụ thuộc trọng lượng, địa chỉ, phụ phí và biểu phí phiên bản. Ví dụ dùng **30.000 VND/gói STANDARD** và **80.000 VND/gói EXPRESS** để minh họa cơ chế truyền envelope, **không phải bảng giá hay quy tắc tài chính production**.

### 5.1. Các nhánh chỉ biến đổi payload

~~~java
import java.math.BigDecimal;

final class DeliveryQuoteTransformer {

    DomainEnvelope<DeliveryQuote> standardQuote(
            DomainEnvelope<?> input) {
        return calculate(input, ServiceLevel.STANDARD, 30_000L);
    }

    DomainEnvelope<DeliveryQuote> expressQuote(
            DomainEnvelope<?> input) {
        return calculate(input, ServiceLevel.EXPRESS, 80_000L);
    }

    private DomainEnvelope<DeliveryQuote> calculate(
            DomainEnvelope<?> input,
            ServiceLevel expected,
            long unitPriceVnd) {

        if (!(input.payload() instanceof DeliveryRequest request)) {
            throw new IllegalArgumentException("UNEXPECTED_PAYLOAD_TYPE");
        }
        if (request.serviceLevel() != expected) {
            throw new IllegalStateException("WRONG_SUBFLOW");
        }

        BigDecimal total = BigDecimal.valueOf(unitPriceVnd)
                .multiply(BigDecimal.valueOf(request.packageCount()));

        return input.mapPayload(new DeliveryQuote(
                request.shipmentId(),
                expected,
                total));
    }
}
~~~

Ba chi tiết cần chú ý:

1. **input.mapPayload(...)** tạo envelope mới mà không tự tái tạo metadata.
2. Method của từng subflow kiểm tra lại serviceLevel để phát hiện routing sai; không chỉ tin tên channel.
3. Logic dùng giá trị có kiểu (**BigDecimal**, **enum**) và trả một **DeliveryQuote**, không trả String hay Map tùy ý mà downstream phải đoán.

### 5.2. Đầu vào và đầu ra của mỗi nhánh

~~~text
Input:
  DomainEnvelope<DeliveryRequest>
    metadata:
      eventId = evt-ship-901
      tenantId = tenant-a
      businessCorrelationKey = shipping:tenant-a:SHIP-901:7
    payload:
      shipmentId = SHIP-901
      serviceLevel = EXPRESS
      packageCount = 2

expressSubflow:
  verify serviceLevel == EXPRESS
  calculate quote

Output:
  DomainEnvelope<DeliveryQuote>
    metadata:
      eventId = evt-ship-901                 (giữ nguyên)
      tenantId = tenant-a                    (giữ nguyên)
      businessCorrelationKey = shipping:tenant-a:SHIP-901:7
    payload:
      shipmentId = SHIP-901
      serviceLevel = EXPRESS
      amountVnd = 160000
~~~

Đây là **thay đổi biểu diễn của cùng một yêu cầu**. Nếu business quyết định gửi một event mới kiểu QUOTE_CREATED sang broker cho dịch vụ khác, thao tác phát event mới có thể có **eventId mới** cùng parentEventId/causationId; không nên đồng nhất nó với phép transform nội bộ này.

## 6. Java DSL: Router dẫn đến hai subflows và một kênh hội tụ

Cách dễ kiểm thử là định nghĩa các subflow thành **IntegrationFlow beans với input channels rõ ràng**, rồi cho Router chọn channel. Các nhánh con đều gửi kết quả sang **quoteOutput**.

### 6.1. Cấu hình các MessageChannels

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
class DeliveryEnvelopeFlowConfig {

    @Bean
    MessageChannel envelopeInput() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel standardRequests() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel expressRequests() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel quoteOutput() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel rejectedEnvelopeMessages() {
        return new QueueChannel();
    }

    @Bean
    DeliveryQuoteTransformer deliveryQuoteTransformer() {
        return new DeliveryQuoteTransformer();
    }

    // Các IntegrationFlow beans được khai báo bên dưới.
}
~~~

Đây là phần đầu của cùng một lớp cấu hình. Những bean flows ở các đoạn kế tiếp **được đặt trong lớp DeliveryEnvelopeFlowConfig**, không phải khai báo lại một lớp có cùng tên.

### 6.2. Router không bỏ lớp envelope

~~~java
// Phương thức @Bean bên trong DeliveryEnvelopeFlowConfig.
@Bean
IntegrationFlow envelopeRouterFlow() {
    return IntegrationFlow.from("envelopeInput")
            .route(DomainEnvelope.class, envelope -> {
                if (!(envelope.payload()
                        instanceof DeliveryRequest request)) {
                    return "UNSUPPORTED";
                }
                return request.serviceLevel().name();
            }, mapping -> mapping
                    .channelMapping(
                            "STANDARD", "standardRequests")
                    .channelMapping(
                            "EXPRESS", "expressRequests")
                    .defaultOutputChannel("rejectedEnvelopeMessages"))
            .get();
}
~~~

**Điều cần quan sát:** Router chỉ đọc payload bên trong envelope để chọn route. **Message được chuyển vào nhánh vẫn có payload là DomainEnvelope\<DeliveryRequest\>**; Router không tự bóc lớp metadata để chỉ gửi DeliveryRequest.

Nếu request không có loại payload được hỗ trợ, default output channel giữ nguyên message để hệ thống có thể quarantine/audit. Trường hợp validation ném exception hoặc handler lỗi thuộc **error path**, không mặc định đi vào default route.

### 6.3. Subflows xử lý một nghiệp vụ riêng

~~~java
// Hai phương thức @Bean bên trong DeliveryEnvelopeFlowConfig.
@Bean
IntegrationFlow standardDeliverySubflow(
        DeliveryQuoteTransformer mapper) {
    return IntegrationFlow.from("standardRequests")
            .transform(DomainEnvelope.class, mapper::standardQuote)
            .channel("quoteOutput")
            .get();
}

@Bean
IntegrationFlow expressDeliverySubflow(
        DeliveryQuoteTransformer mapper) {
    return IntegrationFlow.from("expressRequests")
            .transform(DomainEnvelope.class, mapper::expressQuote)
            .channel("quoteOutput")
            .get();
}
~~~

Các endpoint Transformer nhận một **DomainEnvelope** và trả một **DomainEnvelope**. Spring Message headers có thể được propagate theo semantics của Transformer; nhưng **metadata ứng dụng quan trọng đã nằm trong payload envelope**, vì thế không phụ thuộc vào việc một client bên ngoài có gửi HTTP/JMS custom header hay không.

**Lưu ý phiên bản:** Java DSL signatures và type inference có thể khác giữa các dòng Spring Integration. Đoạn mẫu mô tả API DSL cho các phiên bản hiện đại; khi ghép mã vào source thực tế cần import đúng các package và kiểm thử bằng dependency của dự án. Phạm vi bước viết nội dung này không bao gồm chạy build/QA học thuật.

### 6.4. Chuyển tiếp tới downstream

Từ quoteOutput, một consumer có thể:

1. Đọc EnvelopeMetadata để xác định tenant/workflow và eventId.
2. Kiểm tra payload đúng **DeliveryQuote** và bất biến amountVnd.
3. Lưu kết quả hoặc gọi một service có **business idempotency key**.
4. Ghi trace/audit và cập nhật workflow state nếu cần.

Đừng bóc envelope ngay trước khi đưa vào một downstream cần correlation; nếu muốn downstream chỉ nhận DeliveryQuote, phải có một **bước chuyển đổi có chủ đích** đã lưu hoặc truyền đủ context bằng cách khác.

## 7. Inline subflowMapping: cùng semantics, ngắn hơn

Spring Integration Java DSL còn cho phép tạo **subflows lồng ngay trong định nghĩa Router**, thay vì chỉ map tới tên channel:

~~~java
// Biến thể minh họa: thay cho envelopeRouterFlow và hai
// subflow beans riêng ở mục 6, KHÔNG đăng ký đồng thời cả hai.
@Bean
IntegrationFlow inlineEnvelopeRouting(
        DeliveryQuoteTransformer mapper) {
    return IntegrationFlow.from("envelopeInput")
            .route(DomainEnvelope.class, envelope -> {
                if (!(envelope.payload()
                        instanceof DeliveryRequest request)) {
                    return "UNSUPPORTED";
                }
                return request.serviceLevel().name();
            }, routes -> routes
                    .subFlowMapping("STANDARD", sub -> sub
                            .transform(
                                    DomainEnvelope.class,
                                    mapper::standardQuote)
                            .channel("quoteOutput"))
                    .subFlowMapping("EXPRESS", sub -> sub
                            .transform(
                                    DomainEnvelope.class,
                                    mapper::expressQuote)
                            .channel("quoteOutput"))
                    .defaultOutputChannel("rejectedEnvelopeMessages"))
            .get();
}
~~~

**Không dùng đồng thời** biến thể ở mục 7 và bộ Router/Subflows ở mục 6 với **cùng envelopeInput**: hai consumer Router trên DirectChannel có thể gây xử lý không mong muốn. Chọn **một** kiểu wiring.

Trong biến thể inline, mỗi lambda subflow là một luồng xử lý tách biệt được Router chọn. Hợp đồng envelope **không đổi**: cùng metadata, chỉ payload được chuyển thành DeliveryQuote.

### 7.1. Khi nào chọn subFlowMapping thay vì named channels?

| Lựa chọn | Phù hợp | Cần lưu ý |
| --- | --- | --- |
| **Named channels + separate IntegrationFlow beans** | Nhánh lớn, cần metrics hoặc test độc lập, ownership theo module | Nhiều bean hơn, nhưng boundaries rõ |
| **subFlowMapping inline** | Nhánh ngắn, routing logic dễ đọc cùng một chỗ | Không để lambda quá dài, tránh trộn nhiều trách nhiệm |
| **Một Transform với switch** | Số trường hợp rất ít, logic thuần và đơn giản | Dễ trở thành khối if/else lớn khi thêm nguồn |

Chọn cách nào cũng phải xác định đường lỗi, timeout, output channel, correlation và idempotency.

### 7.2. Một số Router có semantics reply khác nhau

Một Router chuyển Message tới channel; một subflow có thể kết thúc ở Service Activator không trả reply, hoặc được nối tới một channel khác. Đừng mặc định chỉ vì Router đã chọn nhánh thì một **Gateway caller** luôn nhận được reply: cần có một đường reply hợp lệ (và hợp đồng send/reply timeout) xuyên các endpoint.

Đặc biệt, nếu subflow trả null hoặc có Filter discard, yêu cầu/reply có thể kết thúc mà không có output. Khi Gateway đang chờ, điều đó có thể dẫn đến reply timeout.

## 8. Ba cách transform và điểm dễ mất envelope

Hãy xét ba kiểu implementation thường gặp.

### 8.1. Đúng: nhận envelope, trả envelope

~~~java
DomainEnvelope<DeliveryQuote> transform(
        DomainEnvelope<DeliveryRequest> incoming) {
    DeliveryRequest request = incoming.payload();
    DeliveryQuote quote = new DeliveryQuote(
            request.shipmentId(),
            request.serviceLevel(),
            java.math.BigDecimal.valueOf(60_000L));
    return incoming.mapPayload(quote);
}
~~~

Ở đây metadata luôn đi cùng output. Đổi payload không yêu cầu clone mọi Spring MessageHeaders hoặc tái tạo các trường tin cậy từ input thô.

### 8.2. Sai nếu downstream vẫn cần envelope: chỉ trả nội dung đã xử lý

~~~java
// Trả payload thuần, làm mất DomainEnvelope application-level.
DeliveryQuote transform(DomainEnvelope<DeliveryRequest> incoming) {
    DeliveryRequest request = incoming.payload();
    return new DeliveryQuote(
            request.shipmentId(),
            request.serviceLevel(),
            java.math.BigDecimal.valueOf(60_000L));
}
~~~

Spring Integration có thể tiếp tục propagate **một số Spring Message headers**, nhưng output payload không còn DomainEnvelope. Nếu downstream tìm **metadata trong payload envelope** để serialize vào broker, nó không tìm thấy nữa.

Điều này chỉ đúng khi bạn **cố ý unwrap** ở một boundary và đã có cách khác để giữ thông tin cần thiết. Không coi việc Spring Message còn các headers là bằng chứng domain envelope vẫn được bảo toàn.

### 8.3. Sai: tự tạo metadata ngẫu nhiên trong từng subflow

~~~java
// Phản ví dụ không nên làm.
EnvelopeMetadata changed = new EnvelopeMetadata(
        1,
        incoming.metadata().tenantId(),
        java.util.UUID.randomUUID().toString(),
        java.util.UUID.randomUUID().toString(),
        "new-trace-every-hop",
        "UNKNOWN",
        java.time.Instant.now());

return new DomainEnvelope<>(changed, newQuote);
~~~

Trường eventId, businessCorrelationKey, traceId, sourceSystem và receivedAt đã bị thay đổi mà không có quyết định nghiệp vụ. Khi cùng event được retry, hành vi có thể tạo nhóm mới hoặc vô hiệu hóa dedup.

**Nguyên tắc:** nếu đây là cùng logical work, giữ immutable metadata. Nếu cần ghi thông tin của hop/subflow, sử dụng **processing context riêng** hoặc thêm một cấu trúc enrichment/versioned metadata rõ chủ sở hữu.

## 9. Trường hợp subflow cần thêm metadata

Đôi khi subflow phải ghi nhận **kết quả xác minh**, **pricing rule version**, hoặc **thời điểm hoàn thành**. Không nên mutate một Map chung trong envelope mà các subflows khác cũng đang giữ.

### 9.1. Tách metadata của event gốc và metadata phát sinh

Một lựa chọn là đặt dữ liệu nghiệp vụ phát sinh vào payload:

~~~java
// Biến thể DTO mở rộng, không khai báo cùng lúc
// với DeliveryQuote tối giản ở mục 5.
record DetailedDeliveryQuote(
        String shipmentId,
        ServiceLevel serviceLevel,
        java.math.BigDecimal amountVnd,
        String tariffVersion,
        java.time.Instant calculatedAt) {
}
~~~

Khi đó event metadata gốc vẫn giữ nguyên, còn payload kết quả có đủ thông tin về quyết định mới. Với ví dụ mục 5 dùng DeliveryQuote tối giản, có thể tạo **kiểu kết quả mở rộng** như trên khi contract yêu cầu.

Một lựa chọn khác là tạo:

~~~java
record ProcessingContext(
        String attemptId,
        String currentStage,
        java.time.Instant processedAt) {
}
~~~

ProcessingContext có thể được đặt ở Spring Message headers **nội bộ** để quan sát một lần xử lý, nhưng không bắt buộc serialize theo mỗi domain event. Nếu cần bền qua retry/restart, persist trạng thái xử lý theo event/operation ID; không chỉ dựa vào headers in-memory.

### 9.2. Enrich envelope với version rõ ràng

Nếu yêu cầu tích hợp buộc phải thêm một field vào **wire envelope**, thay đổi schema có kiểm soát:

~~~text
DomainEnvelope v1:
  schemaVersion, tenantId, eventId, correlationKey, payload

DomainEnvelope v2:
  schemaVersion, tenantId, eventId, correlationKey,
  causationId, payload
~~~

Cần converter v1/v2, backward compatibility, tests, kế hoạch rollout. Không đột ngột thêm field bắt buộc vào JSON của mọi partner chỉ vì một subflow mới cần metadata.

## 10. Spring MessageHeaders khác DomainEnvelope.metadata

Ngay cả khi DomainEnvelope bất biến, Spring Integration vẫn bọc nó trong một Spring Message với **headers** của framework. Cần phân biệt rạch ròi:

| Thuộc tính | Nên đặt ở đâu? | Lý do |
| --- | --- | --- |
| **eventId logic** | DomainEnvelope.metadata | Còn khi serialize/lưu và replay |
| **tenantId đã xác minh** | DomainEnvelope.metadata, có thể mirror header nội bộ | Ranh giới nghiệp vụ và bảo mật |
| **businessCorrelationKey** | DomainEnvelope.metadata, mirror vào correlation header khi cần | Aggregator/recovery |
| **traceId / trace context** | Observability context + envelope khi hợp đồng yêu cầu | Liên kết qua service |
| **replyChannel** | Spring MessageHeaders do framework quản lý | Runtime request/reply |
| **errorChannel** | Spring MessageHeaders theo error handling | Runtime error routing |
| **sequenceNumber / sequenceSize** | Spring headers của Splitter/Resequencer | Group con và vị trí trong sequence |
| **deliveryAttempt / retry count** | Runtime processing header hoặc state | Có thể khác mỗi attempt |
| **HTTP/JMS/AMQP properties** | Transport adapter/header mapper | Phạm vi giao thức |

### 10.1. Tạo Spring Message có header tương thích với envelope

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class EnvelopeMessageFactory {

    static <T> Message<DomainEnvelope<T>> trusted(
            DomainEnvelope<T> envelope) {

        EnvelopeMetadata md = envelope.metadata();
        return MessageBuilder.withPayload(envelope)
                .setHeader("trustedTenantId", md.tenantId())
                .setHeader("businessEventId", md.eventId())
                .setHeader(
                        "businessCorrelationKey",
                        md.businessCorrelationKey())
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        md.businessCorrelationKey())
                .build();
    }
}
~~~

Factory này nhận **DomainEnvelope đã được kiểm chứng tại ingress**. Nó **không** copy toàn bộ HTTP/JMS headers hoặc raw client correlationId để tránh cho một nguồn chưa tin cậy tự điều khiển ReplyChannel/ErrorChannel hoặc tạo false group.

### 10.2. Mirror cần kiểm tra xung đột

Giả sử Message header businessCorrelationKey ghi **order-A**, nhưng payload envelope metadata ghi **order-B**. Không nên lấy một trong hai ngẫu nhiên tùy từng downstream:

~~~text
Spring header:  businessCorrelationKey=shipping:tenant-a:SHIP-901:7
Envelope meta:  businessCorrelationKey=shipping:tenant-b:SHIP-999:1
~~~

Một boundary validator phải so sánh và **fail closed** khi mismatch. Chọn **source of truth** là registry hoặc verified envelope tại ingress, sau đó tạo các Spring headers nội bộ từ nó. Không để downstream Router dùng header A còn Aggregator dùng envelope B.

### 10.3. Transformer trả payload và Transformer trả Message

Spring Integration Transformer có thể nhận Message rồi trả **payload** hoặc trả **Message mới**:

~~~java
// Biến đổi payload; framework có thể giữ các inbound headers
// theo quy tắc của transformer endpoint.
.transform(DomainEnvelope.class, mapper::expressQuote)
~~~

~~~java
// Handler tự dựng Message mới. Phải quyết định những header
// runtime nào cần giữ/thiết lập.
Message<DomainEnvelope<DeliveryQuote>> wrapExplicitly(
        Message<DomainEnvelope<DeliveryRequest>> incoming) {
    DomainEnvelope<DeliveryQuote> payload =
            quoteTransformer.expressQuote(incoming.getPayload());
    return MessageBuilder.withPayload(payload)
            .setHeader("businessCorrelationKey",
                    payload.metadata().businessCorrelationKey())
            .build();
}
~~~

Mẫu thứ hai **không bảo toàn tất cả Spring headers**; tùy topology có thể mất replyChannel, errorChannel, trace hoặc sequence metadata. Khi một handler thực sự cần tạo Message, hãy xác định các header nào cần propagate bằng **API/framework semantics của version đang dùng**, tránh copy tùy tiện mọi header từ nguồn chưa tin cậy.

### 10.4. Không dùng Spring Message ID thay eventId

MessageHeaders.ID là identity của một Spring Message, có thể thay đổi khi tạo Message mới hoặc qua adapter. DomainEnvelope.metadata.eventId đại diện cho **logical event** và thường phải giữ ổn định khi redelivery.

~~~text
attempt 1:
  Spring Message ID = msg-a
  Domain event ID   = evt-ship-901

attempt 2:
  Spring Message ID = msg-b
  Domain event ID   = evt-ship-901
~~~

Nếu dùng Spring MessageHeaders.ID làm dedup key, redelivery có thể vượt qua kiểm tra trùng.

## 11. Nơi unwrap envelope có chủ đích

Một số thư viện business chỉ muốn nhận **DeliveryQuote**, không muốn biết DomainEnvelope. Có thể tạo **adapter ở ranh giới ứng dụng**:

~~~java
final class DeliveryQuoteHandler {
    void process(
            DeliveryQuote quote,
            EnvelopeMetadata metadata) {
        // Dùng metadata để kiểm tra tenant/idempotency/correlation.
        // Domain service có thể nhận quote thuần sau boundary.
    }
}
~~~

~~~text
Before boundary:
  DomainEnvelope<DeliveryQuote>

Adapter:
  validate metadata and payload
  select business idempotency key
  call domain service(quote, verified business context)

After boundary:
  domain service có thể không biết Spring Integration
~~~

**Không unwrap quá sớm:** nếu bỏ metadata trước khi gọi business handler rồi sau đó cần tenant/correlation, handler có thể tự đọc một ThreadLocal/RequestContext đã không còn hiệu lực khi flow chuyển qua ExecutorChannel hoặc broker.

### 11.1. Một ví dụ unwrap có kiểm soát

~~~java
// Mảnh phương thức tại adapter gọi business service.
void handle(DomainEnvelope<?> envelope) {
    if (!(envelope.payload() instanceof DeliveryQuote quote)) {
        throw new IllegalArgumentException("EXPECTED_DELIVERY_QUOTE");
    }
    EnvelopeMetadata context = envelope.metadata();

    // Caller có thể kiểm tra tenant/operation identity tại đây.
    deliveryQuoteService.save(
            context.tenantId(),
            context.eventId(),
            context.businessCorrelationKey(),
            quote);
}
~~~

**deliveryQuoteService** là một service placeholder cho ví dụ kiến trúc; code production phải có transaction, unique constraint và idempotency phù hợp. Việc lấy context từ envelope **không tự chứng minh** tenant đã được xác minh nếu một adapter ngoài đã bypass ingress validation.

### 11.2. Tránh double-wrapping không có mục đích

~~~text
DomainEnvelope<DomainEnvelope<DeliveryRequest>>
~~~

Đôi khi wrapper lồng nhau có lý do (ví dụ wire envelope của transport và domain envelope), nhưng nếu mỗi subflow đều bọc thêm một DomainEnvelope cùng ngữ nghĩa, consumer sẽ khó biết tenant/eventId nằm ở tầng nào. Khi đã có **một canonical envelope**, hãy **mapPayload** và giữ tầng metadata thay vì bọc thêm lớp giống hệt.

## 12. Splitter: envelope của message cha và envelope của message con

Khi một DeliveryRequest có ba packages cần xử lý song song, Splitter có thể tạo ba child messages. **Đây là điểm ranh giới identity mới**, không chỉ là một phép mapPayload của cùng một event.

~~~mermaid
flowchart TB
    P["DomainEnvelope<DeliveryRequest>"] --> S["Splitter"]
    S --> A["Child envelope parcel 1"]
    S --> B["Child envelope parcel 2"]
    S --> C["Child envelope parcel 3"]
    A --> N["Child processing"]
    B --> N
    C --> N
    N --> G["Aggregator: complete parcel set"]
    G --> O["Shipment summary"]
~~~

Nếu cả ba child envelopes giữ **cùng eventId của cha** mà downstream có inbox unique theo tenant+eventId, child 2 và child 3 có thể bị chặn như duplicate. Vì thế:

- **businessCorrelationKey của workflow cha** có thể được giữ.
- **child eventId** phải ổn định và riêng khi từng child là một logical work độc lập.
- **parentEventId/causationId** phải còn để truy nguồn.
- **sequenceNumber/sequenceSize** có thể được Spring Splitter gắn để các child messages vào đúng nhóm con.

### 12.1. DTO và quy tắc tạo child identity

~~~java
record ParcelTask(
        String parentEventId,
        String shipmentId,
        int parcelNumber,
        int totalParcels) {
}

final class ParcelEnvelopes {
    private ParcelEnvelopes() {}

    static DomainEnvelope<ParcelTask> child(
            DomainEnvelope<DeliveryRequest> parent,
            int number) {
        DeliveryRequest request = parent.payload();
        if (number < 1 || number > request.packageCount()) {
            throw new IllegalArgumentException("INVALID_PARCEL_NUMBER");
        }

        EnvelopeMetadata root = parent.metadata();
        String childId = root.eventId() + ":parcel:" + number;

        EnvelopeMetadata childMeta = new EnvelopeMetadata(
                root.schemaVersion(),
                root.tenantId(),
                childId,
                root.businessCorrelationKey(),
                root.traceId(),
                root.sourceSystem(),
                root.receivedAt());

        return new DomainEnvelope<>(
                childMeta,
                new ParcelTask(
                        root.eventId(),
                        request.shipmentId(),
                        number,
                        request.packageCount()));
    }
}
~~~

Child IDs trong ví dụ được tạo theo **parent event ID + parcel number**. Khi retry cùng logical parent và cùng manifest, child ID ổn định. Nếu order of packages thay đổi giữa attempts, index có thể không đại diện cùng một parcel; trong hệ thống thực nên dùng **parcelId ổn định** từ manifest. Ngoài ra, validation ở EnvelopeMetadata giới hạn eventId 120 ký tự; production phải đảm bảo phép ghép childId không vượt giới hạn hoặc dùng mapping/encoding đã định nghĩa.

### 12.2. Technical correlation của Splitter có thể khác business key

Spring Integration Splitter có thể đặt các headers **CORRELATION_ID, SEQUENCE_NUMBER, SEQUENCE_SIZE** theo cách nhóm những message con. Giá trị technical correlation đó không nhất thiết trùng với **businessCorrelationKey** của workflow gốc.

~~~text
DomainEnvelope.metadata.businessCorrelationKey:
    shipping:tenant-a:SHIP-901:7   (workflow cha)

Spring MessageHeaders.CORRELATION_ID:
    splitter-batch-42               (nhóm message con)

Spring MessageHeaders.SEQUENCE_NUMBER:
    1, 2, 3
~~~

**Không ép tất cả nested Splitters sử dụng một CORRELATION_ID toàn cục.** Một Aggregator gom parcel results có thể dùng technical group theo Splitter, còn Aggregator gom business events có thể dùng businessCorrelationKey có scope rộng hơn. Phải xác định scope rõ trước khi chọn correlationStrategy.

### 12.3. Một cách dùng Splitter với Envelope

~~~java
// Ý tưởng về một splitter function độc lập với transport.
static java.util.List<DomainEnvelope<ParcelTask>> split(
        DomainEnvelope<DeliveryRequest> parent) {

    java.util.List<DomainEnvelope<ParcelTask>> result =
            new java.util.ArrayList<>();
    for (int i = 1; i <= parent.payload().packageCount(); i++) {
        result.add(ParcelEnvelopes.child(parent, i));
    }
    return java.util.List.copyOf(result);
}
~~~

Khi gắn vào một Spring Integration Splitter, cần kiểm thử sequence headers được tạo bằng đúng cấu hình và version, rồi kiểm tra Aggregator release sau khi nhận các **logical child results**, không chỉ sau một số attempts có thể chứa duplicates.

## 13. Publish-Subscribe và Recipient List: nhiều subflows đọc cùng envelope

Một publish-subscribe channel có thể nhân bản **tham chiếu đến cùng immutable envelope** để nhiều subscribers xử lý một message. Ví dụ một nhánh ghi audit, một nhánh tạo quote, một nhánh thu thập metrics.

~~~mermaid
flowchart LR
    E["DomainEnvelope<Request>"] --> P["Publish-Subscribe"]
    P --> A["Audit subflow"]
    P --> Q["Quote subflow"]
    P --> M["Metrics subflow"]
    Q --> O["Envelope<Quote>"]
~~~

### 13.1. An toàn khi payload và metadata thật sự bất biến

DomainEnvelope là record bất biến, nhưng cần xem cả **payload**. Nếu payload chứa một List mutable, Map mutable hoặc object có setter, hai subflows vẫn có thể thay đổi dữ liệu mà nhánh khác đang đọc.

Ví dụ sai:

~~~java
record UnsafePayload(java.util.Map<String, Object> fields) {}

// subflow A:
envelope.payload().fields().put("status", "CHANGED");

// subflow B đọc cùng object và thấy dữ liệu đã bị đổi.
~~~

Biện pháp:

- Payload dùng immutable records, enums và immutable collections.
- Constructor thực hiện defensive copy cho Map/List: **Map.copyOf**, **List.copyOf** khi phù hợp.
- Mỗi subflow tạo output mới bằng mapPayload hoặc DTO mới.
- Khi có side effect, dùng idempotency và transaction; **immutable object không giúp DB writes chạy một lần**.

### 13.2. Đừng hiểu publish-subscribe là một request có một reply

Khi một publish-subscribe channel gửi message đến nhiều subscribers, mỗi subscriber có thể hoàn tất hoặc thất bại khác nhau. Nếu yêu cầu đợi kết quả từ cả ba, cần **Scatter-Gather/Aggregator** và chính sách release/timeout; không chỉ gọi publish rồi chờ một arbitrary reply.

Recipient List cũng có thể gửi message tới nhiều destinations. Nếu hai recipient cùng ghi DB, phải phân biệt **operationId của từng recipient** để không nhầm side effects của hai nhánh là một thao tác trùng.

### 13.3. Envelope của các derived results

Nếu một root request tạo ba outcomes:

~~~text
root eventId = evt-ship-901

AUDIT_RECORDED   -> evt-ship-901:audit
PRICE_COMPUTED  -> evt-ship-901:price
CHECK_COMPLETED -> evt-ship-901:check
~~~

Có thể giữ businessCorrelationKey chung nhưng cấp identity riêng cho các **events mới** theo quy tắc deterministic hoặc persisted mapping. Nếu mỗi branch chỉ đọc envelope rồi cập nhật **metrics**, không cần phát một business event mới.

## 14. Scatter-Gather: kết hợp kết quả sau nhiều subflows

Trong Scatter-Gather, một request được phát đến nhiều nhánh và các replies được Aggregator hợp nhất. Envelope giúp mỗi branch reply có business context để xác minh đang thuộc cùng workflow.

~~~text
Request:
  eventId = quote-request-100
  businessCorrelationKey = shipping:tenant-a:SHIP-901:7

Scatter:
  rateProvider A
  rateProvider B
  rateProvider C

Gather:
  Reply A: QuoteResult, correlationKey=...
  Reply B: QuoteResult, correlationKey=...
  Reply C: QuoteResult, correlationKey=...

Aggregate:
  check same tenant, same business key, distinct providers
  release khi đủ terminal outcomes theo manifest
~~~

### 14.1. Correlation và release là hai câu hỏi khác nhau

- **CorrelationStrategy:** kết quả của ba nhà cung cấp có thuộc cùng một logical request không?
- **ReleaseStrategy:** đã nhận đủ những kết quả cần thiết để kết luận chưa?

Không dùng duy nhất **group.size()==3** nếu broker có thể redeliver Provider A ba lần. Cần dedup theo provider operation/eventId, kiểm tra expected providers, timeout và các kết quả terminal như ACCEPTED/REJECTED/UNAVAILABLE.

### 14.2. Không dùng một correlation key cho mọi subgroup

Nếu một batch chứa nhiều shipments, mỗi shipment gửi sang ba providers, dùng chỉ batchId sẽ trộn hết provider replies. Scope có thể là:

~~~text
batchId: B-2026-11

shipment A provider group:
  provider-quote:tenant-a:B-2026-11:SHIP-A:epoch-1

shipment B provider group:
  provider-quote:tenant-a:B-2026-11:SHIP-B:epoch-1
~~~

Chỉ sau khi có per-shipment summaries, một Aggregator cha mới gom các summaries theo batch key. Envelope có thể mang **parentBusinessKey** và **currentGroupKey** tách biệt khi topology yêu cầu.

### 14.3. Không tin reply chỉ vì có đúng correlation key

Một actor bất kỳ biết group key có thể cố đưa “quote rẻ” giả vào Aggregator. Inbound adapter phải xác thực producer, xác minh providerId và quyền đối với tenant/workflow, rồi mới tạo verified envelope nội bộ. **Correlation không phải authorization**.

## 15. Gateway và temporary replyChannel

Spring Integration **Messaging Gateway** cho phép code Java gọi một IntegrationFlow như một phương thức. Khi method đợi reply, framework thường dùng một **temporary replyChannel** để gửi kết quả về đúng invocation.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Messaging Gateway
    participant R as Router
    participant S as Subflow
    C->>G: calculateQuote(envelope)
    G->>R: Message(payload=DomainEnvelope, replyChannel=temporary)
    R->>S: Route message
    S-->>G: DomainEnvelope<DeliveryQuote> qua reply path
    G-->>C: Result payload
~~~

**Business correlationKey trong DomainEnvelope không phải replyChannel của Gateway.** Cùng workflow có thể có nhiều Gateway attempts, nhưng mỗi invocation cần phân biệt reply destination tương ứng.

### 15.1. Interface Gateway minh họa

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
interface DeliveryQuoteGateway {

    @Gateway(
            requestChannel = "gatewayQuoteInput",
            replyTimeout = 5_000)
    DomainEnvelope<DeliveryQuote> calculate(
            DomainEnvelope<DeliveryRequest> request);
}
~~~

Ví dụ này là **hợp đồng Gateway**; để chạy cần một flow nối **gatewayQuoteInput** tới route/subflow có khả năng trả reply vào đường reply tương ứng. **Không** gửi reply vào một QueueChannel output riêng rồi tự mong Gateway biết để nhận, trừ khi có wiring bridge/reply channel tương thích.

### 15.2. Gửi vào subflow nhưng làm mất replyChannel

Nếu một Transformer tự dựng Message mới chỉ có **businessCorrelationKey**, một Gateway đang chờ có thể không nhận reply. Ngược lại, cố nhét **temporary replyChannel object** vào DomainEnvelope để gửi qua broker cũng sai vì đối tượng runtime không portable và không sống mãi.

Giải pháp cần tách hai tầng:

1. **Business context** bền trong envelope.
2. **Gateway request/reply context** do framework/adapter quản lý trong cùng request lifecycle.

### 15.3. Khi request mất nhiều phút

Một Gateway sync với temporary replyChannel không phải workflow store. Nếu remote service trả HTTP 202 Accepted rồi callback một phút sau, lời gọi Gateway ban đầu có thể đã trả hoặc timeout. Callback phải được **correlate qua business key** vào persistent workflow state, không gửi vào temporary channel đã hết lifetime.

Nếu cần đợi nhiều kết quả rồi cập nhật trạng thái, dùng async command + event callbacks + Aggregator/workflow coordinator. API có thể trả trackingId để client truy vấn, thay vì giữ HTTP thread vô thời hạn.

## 16. Qua HTTP, JMS, AMQP và TCP: envelope ứng dụng cần wire contract

Một subflow có thể kết thúc bằng outbound gateway/adapter thay vì một MessageChannel nội bộ. Lúc này **DomainEnvelope được serialize thành bytes**; Spring MessageHeaders sẽ được chuyển theo **HeaderMapper/MessageConverter** của từng transport, không có bảo đảm mọi header runtime đều đi qua network.

### 16.1. Định dạng wire minh họa

~~~json
{
  "schemaVersion": 1,
  "metadata": {
    "tenantId": "tenant-a",
    "eventId": "evt-ship-901",
    "businessCorrelationKey": "shipping:tenant-a:SHIP-901:7",
    "traceId": "trace-901",
    "sourceSystem": "ORDER_SERVICE",
    "receivedAt": "2026-11-21T03:00:00Z"
  },
  "payloadType": "DELIVERY_REQUEST",
  "payload": {
    "shipmentId": "SHIP-901",
    "serviceLevel": "EXPRESS",
    "packageCount": 2
  }
}
~~~

Đây là **application wire contract minh họa**, không phải format JSON mặc định của Spring Integration. Trường payloadType hoặc schemaVersion giúp parser chọn đúng DTO; không nên deserialize tùy ý class names do client gửi, vì có thể tạo rủi ro polymorphic deserialization.

### 16.2. Bảng giới hạn qua transport

| Transport | Giao thức mang gì? | Điều phải cấu hình |
| --- | --- | --- |
| **HTTP** | Body + HTTP headers | JSON serializer, content type, header allowlist, timeout |
| **JMS** | Body + JMS headers/properties | Converter, HeaderMapper, JMSReplyTo/JMSCorrelationID khi RPC |
| **AMQP** | Body + AMQP properties/headers | Converter, replyTo/correlation cho RPC, broker permissions |
| **TCP** | Bytes theo framing/serializer | Framing, MessageMapper, selected headers hoặc DTO envelope |
| **File/SFTP** | Nội dung file + tên/path/metadata ngoài | File schema, identity, idempotency và parsing |

Spring Message header **replyChannel** có thể chứa một MessageChannel object trong cùng JVM; không phải dữ liệu JSON/JMS property portable. Đừng serialize một Spring Message hoàn chỉnh và giả định service khác có thể tái tạo live channel references.

### 16.3. Nếu adapter chỉ gửi payload bên trong

Phản ví dụ:

~~~text
Before outbound adapter:
  Message.payload = DomainEnvelope<DeliveryRequest>

Custom converter:
  encode(message.payload.payload)      // Chỉ lấy DeliveryRequest

After remote inbound:
  Message.payload = DeliveryRequest
  DomainEnvelope metadata đã mất
~~~

Đây không phải lỗi Router ở subflow; nó là quyết định của **wire converter**. Cần test round-trip của encoder/decoder với metadata, không chỉ test local IntegrationFlow.

## 17. Bảo vệ trust boundary khi envelope quay về từ bên ngoài

Một external producer có thể tự gửi JSON chứa tenantId, eventId và businessCorrelationKey. **Đúng schema không có nghĩa đã được cấp quyền**. Tại inbound adapter, dùng identity của kết nối/producer để xác định tenant và source thật.

### 17.1. Raw wire record khác Verified DomainEnvelope

~~~java
record DeliveryWireRequest(
        int schemaVersion,
        String claimedTenantId,
        String eventId,
        String claimedCorrelationKey,
        String traceId,
        String claimedSourceSystem,
        String receivedAtIso,
        String shipmentId,
        String serviceLevel,
        int packageCount,
        int workflowEpoch) {
}

record VerifiedProducer(
        String principalId,
        String tenantId,
        String sourceSystem) {
}

interface ShipmentWorkflowRegistry {
    boolean maySubmit(
            VerifiedProducer producer,
            String shipmentId,
            int epoch);
}
~~~

Ở ví dụ này, claimedTenantId và claimedCorrelationKey là **untrusted claims**. Registry phải đối chiếu shipment thuộc verified tenant và producer được phép gửi loại request đó. Không chỉ so sánh string tenantId rồi coi là authentication.

### 17.2. Verifier dựng lại envelope có nguồn gốc tin cậy

~~~java
import java.time.Instant;

final class DeliveryEnvelopeIngress {
    private final ShipmentWorkflowRegistry registry;

    DeliveryEnvelopeIngress(ShipmentWorkflowRegistry registry) {
        this.registry = registry;
    }

    DomainEnvelope<DeliveryRequest> verify(
            DeliveryWireRequest wire,
            VerifiedProducer producer) {

        if (wire == null || producer == null
                || wire.schemaVersion() != 1) {
            throw new IllegalArgumentException("INVALID_WIRE_VERSION");
        }

        DeliveryRequest request = new DeliveryRequest(
                wire.shipmentId(),
                ServiceLevel.valueOf(wire.serviceLevel()),
                wire.packageCount());

        if (!registry.maySubmit(
                producer, request.shipmentId(), wire.workflowEpoch())) {
            throw new SecurityException("SHIPMENT_ACCESS_DENIED");
        }

        String expectedKey = "shipping:"
                + producer.tenantId()
                + ":" + request.shipmentId()
                + ":" + wire.workflowEpoch();

        if (!producer.tenantId().equals(wire.claimedTenantId())
                || !producer.sourceSystem()
                        .equals(wire.claimedSourceSystem())
                || !expectedKey.equals(wire.claimedCorrelationKey())) {
            throw new SecurityException("ENVELOPE_IDENTITY_MISMATCH");
        }

        EnvelopeMetadata trusted = new EnvelopeMetadata(
                1,
                producer.tenantId(),
                wire.eventId(),
                expectedKey,
                wire.traceId(),
                producer.sourceSystem(),
                Instant.parse(wire.receivedAtIso()));

        return new DomainEnvelope<>(trusted, request);
    }
}
~~~

**Giới hạn ví dụ:** production còn cần giới hạn kích thước/charset, schema parsing được bảo vệ, xác minh eventId có quyền/đúng phạm vi, cân nhắc traceId do remote khai báo, kiểm tra timestamp skew, chống replay và mapping source-system. **Instant.parse** có thể ném DateTimeParseException khi sai format; hãy map thành error code/HTTP response hoặc DLQ/quarantine theo hợp đồng. **ServiceLevel.valueOf** cũng phải được bắt và phân loại unknown enum thay vì trả nguyên exception nội bộ ra client.

Trong các hệ thống dùng opaque workflow IDs, lấy expectedKey từ registry thay vì ghép chuỗi. Không sử dụng chính claimedCorrelationKey để tra quyền nếu việc đó có thể tạo truy cập chéo tenant.

### 17.3. Header mapping không phải authorization

Một HeaderMapper HTTP/JMS/AMQP có thể map chuỗi X-Correlation-ID thành Spring header correlationId. Điều đó chỉ là **chuyển dữ liệu**, không xác minh giá trị. Phải xác minh source và workflow trước khi dùng header làm khóa Router/Aggregator hoặc route tới destination nhạy cảm.

Nếu một adapter được xem là trusted, phải có ranh giới rõ: adapter đó đã xác thực nguồn hay chỉ parse bytes? Đừng đặt tên bean là trusted rồi bỏ qua kiểm tra.

## 18. Async subflow: envelope không dựa vào ThreadLocal

Nếu thay DirectChannel bằng ExecutorChannel, subflow có thể chạy trên thread khác; nếu qua broker hoặc restart, còn vượt khỏi JVM. Thông tin chỉ lưu trong **ThreadLocal**, MDC hoặc request-scoped bean có thể không xuất hiện khi handler chạy.

~~~text
HTTP thread:
  tenantContext = tenant-a
  send message to ExecutorChannel

Worker thread:
  tenantContext = null / stale

Correct:
  DomainEnvelope.metadata.tenantId = tenant-a
  verified business context được đọc từ envelope
~~~

Trace instrumentation có thể chủ động propagate trace context qua executor hoặc broker, nhưng **business identity** vẫn cần biểu diễn rõ trong payload/envelope hoặc persisted workflow state. MDC giúp logging; nó không phải cơ chế authorization và không phải nguồn business correlation đáng tin.

### 18.1. Không giả định output order giống input order

~~~text
Arrivals:
  Envelope #1 STANDARD
  Envelope #2 EXPRESS
  Envelope #3 STANDARD

Async completion:
  #2, #3, #1
~~~

Subflows có thể hoàn tất không đúng thứ tự arrival. Nếu downstream cần thứ tự nghiệp vụ, dùng sequence numbers/version và Resequencer hoặc coordinator theo stream key. Đừng xếp theo **Instant receivedAt** đơn lẻ khi nhiều producers có đồng hồ khác nhau.

### 18.2. Backpressure

Một Envelope có payload lớn mà được publish tới nhiều subflows có thể tăng memory đáng kể. Với traffic cao:

- Giới hạn payload size và số concurrent messages.
- Dùng bounded executors, queue capacity và rejection policy.
- Đặt quota theo tenant/source; giám sát queue age, retries và DLQ.
- Với payload rất lớn, cân nhắc lưu object bền và truyền **storage reference có quyền truy cập**, nhưng không đưa arbitrary URL do client cung cấp vào tải file server-side.
- Nếu nhiều subflows chia sẻ mutable bytes/collections, cần immutable copy hoặc controlled ownership.

QueueChannel không giới hạn trong ví dụ để test dễ; không dùng unbounded queue làm “giải pháp” backpressure trong production.

## 19. Envelope qua retry và redelivery

Retry thường tạo một **delivery attempt mới**, không phải một business event mới. Cần giữ:

~~~text
logical eventId: evt-ship-901
business key: shipping:tenant-a:SHIP-901:7

attempt 1:
  transportAttemptId: attempt-a
  DomainEnvelope.metadata.eventId: evt-ship-901

attempt 2:
  transportAttemptId: attempt-b
  DomainEnvelope.metadata.eventId: evt-ship-901
~~~

Nếu mỗi retry sinh eventId mới trong envelope, một inbox dedup theo eventId sẽ xem bản gửi lại là một event khác. Ngược lại, nếu thao tác tạo một **business event derived** khác, cần eventId/causationId riêng, không bắt buộc giữ eventId nguồn cho mọi kết quả.

### 19.1. Idempotency tại downstream, không phải chỉ ở Router

Một Router có thể đưa cả hai bản redelivery vào đúng subflow; điều đó không có nghĩa business effect chỉ chạy một lần. Nếu quote handler ghi database, phải dùng stable operation identity và trạng thái bền:

~~~sql
CREATE TABLE delivery_quote_effect (
    tenant_id VARCHAR(48) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    operation_name VARCHAR(80) NOT NULL,
    state VARCHAR(24) NOT NULL,
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, event_id, operation_name)
);
~~~

Giả sử eventId ổn định và duy nhất theo tenant, bảng có thể bảo vệ effect **persist-delivery-quote** bằng unique constraint. Nếu eventId chỉ duy nhất theo producer, cần thêm sourceSystem/producerId vào primary key theo hợp đồng.

### 19.2. Khoảng hở transaction

Phản ví dụ:

~~~text
mark eventId as SEEN in DB
crash before sending envelope to next subflow
broker redelivers eventId
dedup sees SEEN and discards
=> downstream never receives it
~~~

Một thiết kế bền có thể dùng inbox/outbox transaction, hoặc trạng thái RECEIVED → DISPATCH_PENDING → EFFECT_COMMITTED cùng recovery scanner. Đừng bỏ mọi duplicate nếu trạng thái gốc chưa hoàn tất.

### 19.3. Retry không đổi metadata gốc nhưng có thể đổi processing context

Original receivedAt là thời điểm ingress lần đầu. Một lần retry có thể có **attemptStartedAt**, **attemptId** và **retryCount** mới. Đặt chúng trong tracing/runtime metadata hoặc một record processing state phù hợp; không overwrite original receivedAt rồi cho đó là thời điểm message được tạo.

### 19.4. External side effects và UNKNOWN

Nếu subflow gọi payment/shipping provider và timeout, provider có thể đã thực hiện effect dù chưa trả response. Không coi timeout là bằng chứng “chưa xử lý” rồi retry một lệnh không idempotent vô hạn. Dùng provider idempotency key, tra trạng thái hoặc reconciliation.

Envelope giúp truyền identity cho hành động này, nhưng **không tự cung cấp exactly-once effects xuyên các dịch vụ**.

## 20. Unit test: mapPayload giữ metadata nhưng đổi payload đúng

Unit test tốt nhất cho Envelope Wrapper không chỉ kiểm tra output tồn tại mà phải kiểm tra **toàn bộ bất biến metadata** và **kiểu payload mới**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class DeliveryEnvelopeUnitTest {

    private EnvelopeMetadata metadata() {
        return new EnvelopeMetadata(
                1,
                "tenant-a",
                "evt-ship-901",
                "shipping:tenant-a:SHIP-901:7",
                "trace-901",
                "ORDER_SERVICE",
                Instant.parse("2026-11-21T03:00:00Z"));
    }

    private DomainEnvelope<DeliveryRequest> request(
            ServiceLevel level) {
        return new DomainEnvelope<>(
                metadata(),
                new DeliveryRequest("SHIP-901", level, 2));
    }

    @Test
    void standardSubflowPreservesTheEntireEnvelopeMetadata() {
        DomainEnvelope<DeliveryRequest> input =
                request(ServiceLevel.STANDARD);

        DomainEnvelope<DeliveryQuote> output =
                new DeliveryQuoteTransformer().standardQuote(input);

        assertEquals(input.metadata(), output.metadata());
        assertEquals("tenant-a", output.metadata().tenantId());
        assertEquals(
                "evt-ship-901", output.metadata().eventId());
        assertEquals(
                "shipping:tenant-a:SHIP-901:7",
                output.metadata().businessCorrelationKey());
        assertEquals("trace-901", output.metadata().traceId());

        assertEquals(
                ServiceLevel.STANDARD,
                output.payload().serviceLevel());
        assertEquals(
                new BigDecimal("60000"),
                output.payload().amountVnd());
    }

    @Test
    void expressSubflowPreservesMetadataAndComputesPrice() {
        DomainEnvelope<DeliveryRequest> input =
                request(ServiceLevel.EXPRESS);

        DomainEnvelope<DeliveryQuote> output =
                new DeliveryQuoteTransformer().expressQuote(input);

        assertEquals(input.metadata(), output.metadata());
        assertEquals(
                new BigDecimal("160000"),
                output.payload().amountVnd());
        assertEquals("SHIP-901", output.payload().shipmentId());
    }

    @Test
    void theWrongSubflowCannotSilentlyRepriceTheRequest() {
        DomainEnvelope<DeliveryRequest> input =
                request(ServiceLevel.EXPRESS);

        assertThrows(IllegalStateException.class,
                () -> new DeliveryQuoteTransformer()
                        .standardQuote(input));
    }

    @Test
    void inputEnvelopeIsNotMutatedByTransformation() {
        DomainEnvelope<DeliveryRequest> input =
                request(ServiceLevel.STANDARD);
        DeliveryRequest originalPayload = input.payload();
        EnvelopeMetadata originalMetadata = input.metadata();

        new DeliveryQuoteTransformer().standardQuote(input);

        assertSame(originalPayload, input.payload());
        assertSame(originalMetadata, input.metadata());
    }
}
~~~

Trong ví dụ record immutable, **assertSame** với input metadata có thể đúng vì mapPayload giữ tham chiếu record; tuy nhiên **hợp đồng quan trọng là assertEquals** về giá trị. Nếu một version của mapper tạo immutable metadata copy mới có nội dung giống hệt, đó không phải lỗi nghiệp vụ.

### 20.1. Test giữ eventId khi redelivery

~~~java
// Mảnh test bổ sung.
@Test
void repeatedTransformationKeepsLogicalEventIdentity() {
    DomainEnvelope<DeliveryRequest> input =
            request(ServiceLevel.EXPRESS);

    DeliveryQuoteTransformer transformer = new DeliveryQuoteTransformer();
    DomainEnvelope<DeliveryQuote> first =
            transformer.expressQuote(input);
    DomainEnvelope<DeliveryQuote> replay =
            transformer.expressQuote(input);

    assertEquals(
            first.metadata().eventId(),
            replay.metadata().eventId());
    assertEquals(
            first.metadata().businessCorrelationKey(),
            replay.metadata().businessCorrelationKey());
    assertEquals(first.payload(), replay.payload());
}
~~~

Đây là test **tính deterministic của mapping**. Nó không chứng minh database side effect đã được thực hiện một lần, và không thay thế integration test với broker redelivery.

## 21. Integration test: Router → subflow → output giữ envelope

JUnit 5 + spring-test có thể dựng Spring context với **DeliveryEnvelopeFlowConfig** từ mục 6. Để tránh hai tests trộn trạng thái, mỗi test gửi event vào DirectChannel rồi đọc kết quả từ QueueChannel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DeliveryEnvelopeFlowConfig.class)
class DeliveryEnvelopeFlowTest {

    @Autowired
    @Qualifier("envelopeInput")
    MessageChannel input;

    @Autowired
    @Qualifier("quoteOutput")
    QueueChannel results;

    @Autowired
    @Qualifier("rejectedEnvelopeMessages")
    QueueChannel rejected;

    @BeforeEach
    void drainQueues() {
        while (results.receive(0) != null) {
            // Output của test trước.
        }
        while (rejected.receive(0) != null) {
            // Unknown type của test trước.
        }
    }

    private DomainEnvelope<DeliveryRequest> envelope(
            String tenant, String shipment,
            String eventId, ServiceLevel level) {
        EnvelopeMetadata md = new EnvelopeMetadata(
                1,
                tenant,
                eventId,
                "shipping:" + tenant + ":" + shipment + ":7",
                "trace-" + eventId,
                "ORDER_SERVICE",
                Instant.parse("2026-11-21T03:00:00Z"));

        return new DomainEnvelope<>(
                md,
                new DeliveryRequest(shipment, level, 2));
    }

    private void send(DomainEnvelope<?> envelope) {
        assertTrue(input.send(
                EnvelopeMessageFactory.trusted(envelope)));
    }

    private DomainEnvelope<?> nextEnvelope() {
        Message<?> result = results.receive(0);
        assertNotNull(result);
        assertInstanceOf(
                DomainEnvelope.class, result.getPayload());
        return (DomainEnvelope<?>) result.getPayload();
    }

    @Test
    void standardGoesThroughSubflowWithoutLosingMetadata() {
        DomainEnvelope<DeliveryRequest> original =
                envelope(
                        "tenant-a", "SHIP-101",
                        "evt-standard-101", ServiceLevel.STANDARD);

        send(original);
        DomainEnvelope<?> output = nextEnvelope();

        assertEquals(original.metadata(), output.metadata());
        assertInstanceOf(DeliveryQuote.class, output.payload());
        DeliveryQuote quote = (DeliveryQuote) output.payload();
        assertEquals(ServiceLevel.STANDARD, quote.serviceLevel());
        assertEquals(new BigDecimal("60000"), quote.amountVnd());
        assertNull(results.receive(0));
    }

    @Test
    void expressGoesThroughItsOwnSubflow() {
        DomainEnvelope<DeliveryRequest> original =
                envelope(
                        "tenant-a", "SHIP-102",
                        "evt-express-102", ServiceLevel.EXPRESS);

        send(original);
        DomainEnvelope<?> output = nextEnvelope();

        assertEquals(original.metadata(), output.metadata());
        assertEquals(
                new BigDecimal("160000"),
                ((DeliveryQuote) output.payload()).amountVnd());
        assertNull(results.receive(0));
    }

    @Test
    void differentTenantsKeepSeparateBusinessIdentity() {
        DomainEnvelope<DeliveryRequest> tenantA =
                envelope("tenant-a", "SHIP-901",
                        "evt-a", ServiceLevel.STANDARD);
        DomainEnvelope<DeliveryRequest> tenantB =
                envelope("tenant-b", "SHIP-901",
                        "evt-b", ServiceLevel.STANDARD);

        send(tenantA);
        send(tenantB);
        DomainEnvelope<?> first = nextEnvelope();
        DomainEnvelope<?> second = nextEnvelope();

        assertNotEquals(
                first.metadata().businessCorrelationKey(),
                second.metadata().businessCorrelationKey());
        assertEquals("tenant-a", first.metadata().tenantId());
        assertEquals("tenant-b", second.metadata().tenantId());
    }

    @Test
    void unsupportedEnvelopePayloadUsesDefaultRoute() {
        EnvelopeMetadata md = new EnvelopeMetadata(
                1, "tenant-a", "evt-unknown",
                "shipping:tenant-a:SHIP-999:7",
                "trace-unknown", "ORDER_SERVICE",
                Instant.parse("2026-11-21T03:00:00Z"));

        DomainEnvelope<String> unsupported =
                new DomainEnvelope<>(md, "unknown-payload-type");

        send(unsupported);

        Message<?> quarantine = rejected.receive(0);
        assertNotNull(quarantine);
        assertEquals(unsupported, quarantine.getPayload());
        assertNull(results.receive(0));
    }
}
~~~

### 21.1. Test này chứng minh gì?

1. Router chọn đúng nhánh STANDARD/EXPRESS.
2. Subflow trả **DomainEnvelope** thay vì chỉ DeliveryQuote.
3. **Metadata bất biến** xuyên route/transform/hội tụ.
4. **Tenant, eventId, businessCorrelationKey** không bị nhầm giữa hai yêu cầu.
5. Unknown payload đi vào route mặc định và không tạo quote giả.

### 21.2. Test này chưa chứng minh gì?

- HTTP/JMS/AMQP/TCP HeaderMapper serialize metadata đúng.
- Trust boundary thực tế xác minh client/producer.
- Flow có thể phục hồi sau process restart.
- Retry/ack đúng khi broker redelivery.
- Downstream ghi database exactly once.
- Hành vi khi hai nhánh publish/subscribe chạy song song.
- Exception trong Transformer được đưa tới durable quarantine/DLQ.

Do DirectChannel và QueueChannel hoạt động in-memory trong ví dụ, test này **không phải** bằng chứng một distributed workflow có semantics exactly-once hoặc fault-tolerant.

## 22. Test khi Spring headers và envelope metadata không khớp

Nếu một legacy endpoint tự sửa Spring header businessCorrelationKey mà không thay metadata envelope, downstream sẽ có hai nguồn thông tin mâu thuẫn. Một boundary validator có thể phát hiện tình huống này:

~~~java
import org.springframework.messaging.Message;

final class EnvelopeHeaderConsistency {

    static void requireMatch(Message<DomainEnvelope<?>> message) {
        DomainEnvelope<?> envelope = message.getPayload();
        String expected =
                envelope.metadata().businessCorrelationKey();

        Object header = message.getHeaders()
                .get("businessCorrelationKey");

        if (!(header instanceof String actual)
                || !expected.equals(actual)) {
            throw new SecurityException(
                    "BUSINESS_CORRELATION_MISMATCH");
        }

        Object tenant = message.getHeaders()
                .get("trustedTenantId");
        if (!envelope.metadata().tenantId().equals(tenant)) {
            throw new SecurityException(
                    "TRUSTED_TENANT_MISMATCH");
        }
    }
}
~~~

Ví dụ kiểm thử:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class EnvelopeHeaderConsistencyTest {

    @Test
    void mismatchedHeadersAreRejected() {
        EnvelopeMetadata md = new EnvelopeMetadata(
                1, "tenant-a", "evt-901",
                "shipping:tenant-a:SHIP-901:7",
                "trace-901", "ORDER_SERVICE",
                java.time.Instant.parse("2026-11-21T03:00:00Z"));

        DomainEnvelope<DeliveryRequest> envelope =
                new DomainEnvelope<>(
                        md,
                        new DeliveryRequest(
                                "SHIP-901", ServiceLevel.STANDARD, 2));

        Message<DomainEnvelope<?>> forged =
                MessageBuilder.<DomainEnvelope<?>>withPayload(envelope)
                        .setHeader("trustedTenantId", "tenant-b")
                        .setHeader(
                                "businessCorrelationKey",
                                "shipping:tenant-b:SHIP-901:7")
                        .build();

        assertThrows(SecurityException.class,
                () -> EnvelopeHeaderConsistency.requireMatch(forged));
    }
}
~~~

Trong code production, đặt **header consistency check** ở đúng boundary nơi cả hai trường đều được kỳ vọng tồn tại. Không yêu cầu mọi message trên toàn hệ thống có header này, vì có những endpoint/giao thức cố ý chỉ truyền payload envelope; ở inbound hãy dựng lại mirror headers từ verified metadata.

## 23. Lỗi ở subflow: không phải message nào cũng đến default route

Một hệ thống tích hợp cần phân biệt:

| Trường hợp | Ví dụ | Vị trí phát hiện | Hành vi đúng |
| --- | --- | --- | --- |
| **Unknown payload type** | Envelope payload là String | Router | Route sang reject/quarantine |
| **Validation error** | packageCount=0 | Constructor/ingress | Reject sớm, có error code |
| **Wrong route** | EXPRESS vào STANDARD subflow | Transformer | Fail; không tính sai giá |
| **Header/envelope mismatch** | Tenant khác nhau | Boundary validator | Security rejection/audit |
| **Serialization error** | Wire schema version không hỗ trợ | Adapter/converter | Quarantine/unsupported version |
| **Timeout** | Remote provider không trả reply | Gateway/adapter | Theo retry/UNKNOWN/reconcile policy |
| **Duplicate event** | Broker giao lại eventId cũ | Inbox/side-effect layer | Idempotent skip hoặc recovery |
| **Application bug** | NullPointerException do code | Handler | Error flow, alert, fix |

Nhánh **defaultOutputChannel** của Router chỉ dành cho **routing key không có mapping** trong ví dụ. Nếu **DeliveryQuoteTransformer** ném exception, message không tự đi vào rejectedEnvelopeMessages. Đây là **error path**, cần xử lý theo semantics của channel/endpoint.

### 23.1. DirectChannel và ExecutorChannel

- **DirectChannel:** invocation thường trên thread gửi; exception có thể propagate ngược về sender. Nếu dùng inbound HTTP gateway, cần map lỗi thành response đúng contract.
- **ExecutorChannel:** handler có thể chạy trên thread khác; exception có thể phát thành **ErrorMessage** trên errorChannel tùy endpoint/framework configuration.
- **Poller/broker adapter:** việc ack/requeue, retry và DLQ tùy inbound adapter và transaction boundary; không có một hành vi mặc định đúng cho mọi broker.

### 23.2. ErrorMessage không phải Envelope

Một **ErrorMessage** mang Throwable, và trong một số loại exception có thể tham chiếu failedMessage. Không mặc định:

~~~text
errorMessage.getPayload() instanceof DomainEnvelope
~~~

là true. Error flow phải tìm metadata đáng tin ở failedMessage hoặc persistent workflow store nếu có; nếu không xác định được source, tenant hoặc eventId, quarantine **không đoán** businessCorrelationKey từ stack trace.

### 23.3. Dùng reject outcome có kiểu khi cần business terminal result

Nếu một subflow không thể tính quote vì một quy tắc nghiệp vụ, có thể tạo outcome có kiểu:

~~~java
sealed interface QuoteOutcome permits QuoteAccepted, QuoteRejected {}

record QuoteAccepted(DeliveryQuote quote)
        implements QuoteOutcome {
}

record QuoteRejected(
        String shipmentId,
        String reasonCode) implements QuoteOutcome {
}
~~~

Tất cả outcomes vẫn có thể được bọc trong **DomainEnvelope\<QuoteOutcome\>** với metadata phù hợp. Trái lại, một timeout DB chưa biết kết quả **không tự tương đương** QuoteRejected; cần retry/UNKNOWN theo contract.

### 23.4. Không nuốt lỗi bằng một envelope hợp lệ giả

Phản ví dụ:

~~~java
// Không làm thế này cho lỗi không xác định:
catch (Exception ex) {
    return input.mapPayload(
            new DeliveryQuote(
                    input.payload().shipmentId(),
                    ServiceLevel.STANDARD,
                    java.math.BigDecimal.ZERO));
}
~~~

Điều này biến lỗi hạ tầng hoặc bug thành một báo giá 0 VND có vẻ hợp lệ, đồng thời có thể chọn sai serviceLevel. Nếu muốn default quotation, phải có policy nghiệp vụ riêng, lý do, phiên bản và audit.

## 24. Version hóa envelope khi nhiều subflows được triển khai độc lập

Một hệ thống lớn có thể deploy router và từng subflow theo nhịp khác nhau. Nếu subflow A kỳ vọng metadata schema v1 nhưng subflow B yêu cầu v2, việc chỉ đổi record ở nơi tạo envelope có thể gây lỗi tương thích.

### 24.1. Ba loại version khác nhau

| Version | Điều kiểm soát | Ví dụ |
| --- | --- | --- |
| **Envelope schema version** | Cấu trúc metadata + payload envelope | metadata có causationId ở v2 |
| **Payload schema version** | Kiểu và field của DeliveryRequest/Quote | request thêm dimension/weight |
| **Business rule version** | Cách tính price hoặc tax | tariff-2026-11 |

Chúng **không bắt buộc tăng cùng lúc**. Một thay đổi business tariff không cần đổi envelope schema nếu output payload có chỗ chứa tariffVersion hoặc rule được quản lý trong state.

### 24.2. Bảo đảm backward compatibility

Giả sử subflow mới chấp nhận v2 và tạm thời cần xử lý các message v1 còn trong broker:

1. Decode v1/v2 theo schemaVersion được công bố.
2. Chuyển v1 → v2 ở một **upcaster** với default có ngữ nghĩa hợp lệ.
3. Validate các trường mới; nếu không thể suy ra thì reject/quarantine thay vì bịa giá trị.
4. Chỉ gửi **verified canonical envelope** vào các subflows nội bộ.
5. Đảm bảo replay event cũ dùng mapping version phù hợp; không âm thầm tạo business effect khác.

Không dùng Java serialization mặc định qua nhiều phiên bản JVM/service như một wire contract dài hạn.

### 24.3. Canary deployment và mixed versions

Trong rollout, hai instances có thể nhận cùng event nhưng dùng hai bộ subflow mapping khác nhau. Nếu kết quả cần deterministic theo business rule version, envelope hoặc workflow state phải xác định **tariffVersion**; nếu không, cùng eventId có thể cho ra amount khác nhau sau retry, gây conflict trong idempotency ledger.

**Immutable metadata không bảo đảm business rules bất biến**. Cần quản lý version/rule snapshot nếu retry phải tái tạo đúng kết quả.

## 25. Security: envelope không phải giấy phép truy cập

Một payload có đúng metadata syntax không có nghĩa được phép vào bất kỳ subflow nào. Ranh giới bảo mật tối thiểu:

1. **Authenticate:** biết producer là ai.
2. **Authorize:** producer có quyền với tenant, shipment, event type, workflow epoch không?
3. **Validate:** schema, types, size, enum, timestamps và origin.
4. **Bind:** tạo DomainEnvelope từ registry/verified identity, không chỉ nhận client claims.
5. **Route:** chọn subflow từ dữ liệu đã xác minh; không cho client chỉ định tên MessageChannel tùy ý.
6. **Persist/dedup:** chống replay và event collision.
7. **Audit:** log vừa đủ, có quyền truy cập và retention.

### 25.1. Không route bằng tên channel do client tự khai

~~~json
{
  "destination": "internalPaymentAdminChannel",
  "payload": {"shipmentId": "SHIP-901"}
}
~~~

Nếu endpoint chuyển nguyên destination thành header/channel name, client có thể truy cập những flow không được phép. Dùng **allowlisted business route key** như enum STANDARD/EXPRESS đã validate, rồi map sang bean channels nội bộ ở Router.

### 25.2. Không copy header điều khiển của Spring từ bên ngoài

Những header như replyChannel, errorChannel, routingSlip hoặc custom control fields có thể ảnh hưởng đường xử lý. Ở trust boundary, tạo Message mới với **explicit allowlist** thay vì copyHeaders(rawHeaders) từ HTTP/JMS/TCP chưa xác thực.

### 25.3. TraceId không phải secret và cũng không phải authority

TraceId giúp liên kết log, nhưng client có thể tự khai trace headers. Xác thực trace context và bảo vệ quyền truy cập log; không dùng traceId làm business idempotency key hoặc proof tenant ownership.

### 25.4. Tránh rò rỉ payload qua error logs

Nếu Envelope chứa thông tin địa chỉ, thanh toán hoặc PII:

- Không log toàn bộ envelope mặc định ở DEBUG/ERROR.
- Mask/sanitize error details và chỉ log eventRef, source, stage, reason.
- Quarantine payload trong storage bảo vệ, có retention và audit access.
- Khi dựng alert/metrics, tránh dùng raw businessCorrelationKey/eventId làm high-cardinality labels.

## 26. Quan sát subflow có mất metadata hay không

Một request có thể đi qua Router và đến handler thành công, nhưng về sau xuất hiện lỗi “Không xác định tenant”. Nếu chỉ đếm inbound/outbound tổng thể, rất khó biết metadata rơi ở hop nào.

| Metric | Mục đích |
| --- | --- |
| **envelope_ingress_accepted_total{source}** | Số envelope được xác minh |
| **envelope_routed_total{branch}** | Số message vào STANDARD/EXPRESS |
| **envelope_route_rejected_total{reason}** | Unknown type, unsupported business route |
| **envelope_transform_success_total{branch}** | Số subflow xử lý thành công |
| **envelope_transform_failure_total{branch,reason}** | Lỗi validate/transform |
| **envelope_metadata_mismatch_total{reason}** | Header vs envelope khác key/tenant |
| **envelope_wire_roundtrip_failure_total{protocol}** | Sai schema hoặc mất field khi serialize |
| **envelope_retry_total{branch}** | Số lần thử lại |
| **envelope_duplicate_skipped_total{branch}** | Dedup theo logical event |
| **envelope_output_duration_seconds{branch}** | Latency cho mỗi nhánh |
| **envelope_quarantine_total{reason}** | Event cần điều tra |
| **envelope_active_operations** | Công việc chờ/pending |

Metric labels nên thuộc **tập giá trị hữu hạn**. Không dùng eventId, tenantId, shipmentId, traceId hoặc businessCorrelationKey tùy ý làm label. Dùng structured logs/tracing để tìm một event cụ thể.

### 26.1. Log mẫu ở ingress

~~~json
{
  "stage": "verified-ingress",
  "eventRef": "evt-ship-901",
  "envelopeVersion": 1,
  "routeCandidate": "EXPRESS",
  "source": "ORDER_SERVICE",
  "outcome": "ACCEPTED"
}
~~~

### 26.2. Log mẫu ở subflow

~~~json
{
  "stage": "express-quote-subflow",
  "eventRef": "evt-ship-901",
  "traceRef": "trace-901",
  "envelopeVersion": 1,
  "outputType": "DeliveryQuote",
  "outcome": "SUCCESS"
}
~~~

### 26.3. Log mẫu khi phát hiện mismatch

~~~json
{
  "stage": "envelope-consistency",
  "eventRef": "evt-ship-901",
  "reason": "BUSINESS_CORRELATION_MISMATCH",
  "outcome": "REJECTED"
}
~~~

Đây là các **mẫu log ứng dụng**; Spring Integration không tự sinh đúng những field này. Nếu cần đo tại MessageChannel/endpoint, có thể dùng interceptors, Micrometer và tracing instrumentation theo phiên bản đang triển khai.

### 26.4. Tín hiệu đáng cảnh báo

- STANDARD có output nhiều hơn ingress do redelivery mà không có dedup.
- EXPRESS input tăng nhưng quoteOutput không tăng.
- Metadata mismatch sau khi thêm một Transformer trả Message hoàn chỉnh.
- Unknown payload types tăng sau lần nâng schema từ partner.
- Số pending groups tăng vì một Splitter/Filter bỏ child mà Aggregator vẫn chờ đủ.
- Queue age/processing latency tăng sau chuyển từ DirectChannel sang async channel.
- HTTP callbacks đến đủ nhưng Gateway vẫn timeout vì replyChannel không được nối đúng.
- Replays sau restart làm phát sinh effects trùng.

## 27. Runbook: message đi qua subflow nhưng mất correlation

**Tình huống:** Router log “EXPRESS route selected”, Transformer log “quote generated”, nhưng downstream báo thiếu businessCorrelationKey hoặc xử lý nhầm tenant.

### Bước 1 — Xác định envelope ở ngay ingress

Kiểm tra request đã được xác thực chưa, tenant/shipments/epoch có từ registry đáng tin không, eventId có ổn định không. Đừng bắt đầu bằng cách tự tạo một correlationId mới ở bước downstream.

### Bước 2 — Xem output của Router

Message đã vào đúng branch channel hay chưa? Route key được lấy từ **payload đã validate** hay từ một header client tự gửi? Nếu route key không hỗ trợ, message cần đi reject/quarantine.

### Bước 3 — Xem đầu vào/đầu ra của Transformer

So sánh:

~~~text
Before:
  Message.payload = DomainEnvelope<DeliveryRequest>

After:
  Message.payload = ?
~~~

Nếu output là **DeliveryQuote** thuần, subflow đã unwrap application envelope. Nếu output là DomainEnvelope nhưng metadata thay đổi, kiểm tra mapper có sinh UUID/Instant.now()/source mới không.

### Bước 4 — Xem Spring Message headers

Nếu metadata trong DomainEnvelope còn nhưng header businessCorrelationKey mất, cân nhắc boundary mapper tái dựng mirror headers **từ trusted envelope**. Nếu metadata và header mâu thuẫn, reject thay vì chọn một giá trị tùy ý.

Kiểm tra handler có trả **Message mới** làm mất replyChannel/sequence headers cần thiết không.

### Bước 5 — Xem transport boundary

Nếu message được gửi qua HTTP/JMS/AMQP/TCP, kiểm tra converter có chỉ serialize payload trong hay không, HeaderMapper có map những trường được chọn hay không, và inbound có tái tạo envelope từ verified wire contract không.

### Bước 6 — Kiểm tra Splitter/Gateway scope

Nếu flow có Splitter, phân biệt **technical CORRELATION_ID** của group con với business key cha. Nếu flow có Gateway, phân biệt **temporary replyChannel** của invocation với group key bền.

### Bước 7 — Kiểm tra timeout/retry và duplicate

Một reply cũ đến sau Gateway timeout có thể vẫn hợp lệ về nghiệp vụ; không gửi nó tới temporary channel đã đóng. Một event redelivery giữ cùng eventId phải được nhận diện bởi inbox/ledger, không được thực hiện effect hai lần.

### Bước 8 — Khôi phục

- **Missing metadata do bug mapper:** sửa mapper/contract, replay có kiểm soát với stable eventId.
- **Header spoofing hoặc tenant mismatch:** quarantine/security alert, không cố gắn vào group “đúng” bằng tay.
- **Unknown envelope schema:** thêm converter versioned hoặc từ chối có audit.
- **Partial workflow:** kiểm tra manifest, các child outcomes, group timeout và persistent state.
- **External effect UNKNOWN:** đối soát trước khi retry.

### Bước 9 — Xác minh sau sửa

Theo dõi một event từ ingress đến quoteOutput: cùng tenant, eventId, business key, trace context; payload chuyển đúng; Spring headers không mâu thuẫn; downstream chỉ commit theo idempotency policy.

## 28. Ma trận test cho Envelope qua subflow

| Test case | Input hoặc tình huống | Assertion chính |
| --- | --- | --- |
| Standard path | STANDARD, hai packages | Quote 60.000 VND, metadata giữ nguyên |
| Express path | EXPRESS, hai packages | Quote 160.000 VND, metadata giữ nguyên |
| Two tenants | Cùng shipmentId khác tenant | Hai business keys khác nhau |
| Same logical retry | Cùng input/eventId, lần gửi thứ hai | Metadata eventId/correlation không đổi |
| Unsupported payload | DomainEnvelope payload type lạ | Default reject channel, không quote |
| Wrong subflow | EXPRESS gửi vào StandardTransformer | Fail rõ ràng |
| Header mismatch | Header tenant-b, envelope tenant-a | Reject tại consistency boundary |
| Unwrap regression | Transformer trả DeliveryQuote thuần | Test downstream phát hiện thiếu envelope |
| Double wrapping | Envelope<Envelope<Request>> ngoài hợp đồng | Reject/type validation |
| Child identity | Split thành 3 parcels | 3 child IDs ổn định, parent link còn |
| Duplicate child | Một parcel bị giao lại | Không tính thành child thứ tư |
| Splitter sequencing | Nhiều child messages | CORRELATION_ID/SEQUENCE_SIZE đúng group con |
| Scatter-Gather | Ba providers độc lập | Đủ unique outcomes rồi release |
| Gateway reply | Caller chờ trả một quote | Đúng replyChannel invocation |
| Late reply | Caller timeout, callback đến sau | Business workflow policy quyết định |
| Wire roundtrip | Serialize/deserialize qua transport | Metadata hợp đồng không mất |
| Forged tenant | Client tự khai tenant-admin | Ingress không tin metadata |
| Schema mismatch | Envelope version 99 | Reject/quarantine, không đoán format |
| Async handoff | ExecutorChannel thay DirectChannel | Không cần ThreadLocal để tìm tenant |
| Restart | In-flight operation trong persistent store | Recovery đúng identity |
| Redelivery after commit | Broker gửi event cũ | Không tạo side effect lần hai |

### 28.1. Wire contract test

Một test HTTP/JMS/AMQP/TCP thực cần:

1. Dựng **verified envelope** trong application.
2. Serialize theo wire format version hỗ trợ.
3. Gửi qua adapter với header mapper/converter đang cấu hình thực tế.
4. Nhận ở boundary phía bên kia, parse và verify nguồn.
5. Khẳng định **tenant/eventId/businessKey/schemaVersion** khớp sau roundtrip.
6. Khẳng định không serialize/khôi phục live replyChannel/errorChannel object.

Không chỉ gọi ObjectMapper trực tiếp mà gọi đó là “test JMS HeaderMapper”; cần kiểm tra **transport boundary** nếu mục tiêu là xác nhận behavior của adapter.

### 28.2. Test concurrency

Cho nhiều events thuộc cùng tenant và nhiều tenants khác chạy song song, gồm STANDARD và EXPRESS. Assert output theo eventId/businessKey thay vì đòi đúng thứ tự arrival. Nếu có Aggregator, test với shared store/locking hoặc partition ownership, đặc biệt khi có nhiều instances.

### 28.3. Test lỗi không được đánh đồng

Một unknown payload được Router gửi reject channel, còn Transformer bị lỗi mapping có thể ném exception/errorChannel. Hai trường hợp này phải có **hai assertions khác nhau**, tránh giả định mọi lỗi đều rơi vào defaultOutputChannel của Router.

## 29. Bài thực hành: envelope qua ba subflows

Mở rộng ví dụ tính giá để có ba nhánh:

- **STANDARD**: tính giá cơ bản.
- **EXPRESS**: thêm phí giao nhanh.
- **INTERNATIONAL**: phải tra vùng địa lý, trọng lượng và chính sách hải quan trước khi định giá.

Đầu vào thống nhất:

~~~json
{
  "metadata": {
    "schemaVersion": 1,
    "tenantId": "tenant-a",
    "eventId": "evt-delivery-400",
    "businessCorrelationKey": "delivery:tenant-a:SHIP-400:2",
    "traceId": "trace-delivery-400",
    "sourceSystem": "ORDER_SERVICE",
    "receivedAt": "2026-11-21T03:00:00Z"
  },
  "payload": {
    "shipmentId": "SHIP-400",
    "serviceLevel": "INTERNATIONAL",
    "packageCount": 3,
    "weightGrams": 1500
  }
}
~~~

### 29.1. Yêu cầu kỹ thuật

1. Định nghĩa EnvelopeMetadata bất biến, typed payloads và schemaVersion.
2. Xác minh tenant + shipment + workflow epoch trước khi gửi vào trusted envelopeInput.
3. Tạo RouteKey bằng enum có allowlist, không bằng arbitrary channel name từ HTTP client.
4. Dùng Router chọn ba subflows; mỗi subflow **trả một DomainEnvelope mới**.
5. Giữ eventId, businessKey và source/receivedAt khi chỉ đổi representation.
6. Với INTERNATIONAL, nếu một handler cần gọi dịch vụ ngoài, dùng timeout/retry/UNKNOWN policy rõ.
7. Nếu kết quả được dùng để phát event QUOTE_CREATED mới, tạo identity derived/causation riêng, không chỉ copy eventId một cách ngầm.
8. Tạo một commonQuoteOutput channel và common invariant validator.
9. Thêm error/quarantine paths riêng cho route unknown, invalid amount và infrastructure failure.
10. Thêm idempotent business persistence sau khi unwrap ở một boundary có kiểm soát.

### 29.2. Yêu cầu kiểm thử

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| STANDARD hợp lệ | Payload quote đúng, metadata gốc đầy đủ |
| EXPRESS hợp lệ | Payload quote đúng, metadata gốc đầy đủ |
| INTERNATIONAL hợp lệ | Quote có tariffVersion, amount/currency đúng |
| Tên serviceLevel giả | Reject/unsupported, không route tới channel nội bộ khác |
| eventId redelivery | Không tạo effect trùng |
| tenantId giả mạo | Không tạo trusted envelope |
| Transformer trả payload thuần | Contract test phát hiện mất envelope |
| Message headers khác metadata | Boundary validator reject |
| Remote pricing timeout | Không biến UNKNOWN thành giá 0 |
| Multiple async requests | Correlation không phụ thuộc thread hoặc arrival order |
| Subflow emits a derived event | Có parentEventId/causationId |
| Wire version không hỗ trợ | Quarantine, không deserialize tùy ý |

### 29.3. Bonus: fan-out ra ba nhà vận chuyển

Sau khi tạo INTERNATIONAL request, gửi song song tới ba shipping providers rồi Gather responses:

~~~mermaid
flowchart LR
    E["Envelope<InternationalRequest>"] --> S["Scatter"]
    S --> A["Provider A"]
    S --> B["Provider B"]
    S --> C["Provider C"]
    A --> G["Gather unique provider outcomes"]
    B --> G
    C --> G
    G --> R["Envelope<ShippingDecision>"]
~~~

Yêu cầu **derived event identity riêng từng provider**, businessCorrelationKey đúng shipment/epoch, dedup per provider operation, timeout không làm một UNKNOWN result bị coi là APPROVED. Nếu Aggregator cần đủ ba outcomes, kiểm tra **unique provider IDs**, không chỉ group.size()==3.

### 29.4. Tiêu chí đạt

Một người đọc code downstream có thể xử lý **DomainEnvelope\<DeliveryQuote\>** mà không cần biết:

- Request trước đó đi STANDARD hay EXPRESS subflow như thế nào.
- Router dùng named channel hay inline subFlowMapping.
- HTTP/JMS/AMQP adapter nào đã mang request tới ingress.
- Subflow có chạy cùng thread hay không.

Downstream vẫn **biết tenant, logical eventId, business correlation, payload type và schemaVersion** từ một hợp đồng thống nhất. Chỉ khi nghiệp vụ cần chính sách riêng theo service level thì nó mới đọc serviceLevel trong payload; không phải lần tìm header tùy ý của từng connector.

## 30. Câu hỏi tự kiểm tra

1. Envelope Wrapper theo EIP giải quyết bài toán gì khi message đi qua nhiều subflows?
2. DomainEnvelope và Spring Message có phải là cùng một lớp wrapper không?
3. Vì sao không đặt replyChannel object vào application wire envelope?
4. mapPayload() giữ những metadata gì và đổi phần nào?
5. Một Transformer trả DeliveryQuote thuần có ảnh hưởng gì nếu downstream cần DomainEnvelope?
6. Subflow có được tự tạo eventId mới mỗi khi retry không? Khi nào tạo eventId mới là đúng?
7. Vì sao businessCorrelationKey cần scope tenant và workflow epoch?
8. SourceSystem trong envelope có tự chứng minh producer đáng tin không?
9. Tại sao metadata là Java record chưa chắc toàn bộ envelope bất biến sâu?
10. Router subFlowMapping và named channels khác nhau về tổ chức code như thế nào?
11. Default route của Router có tự nhận exception từ Transformer không?
12. Gateway temporary replyChannel khác businessCorrelationKey ở đâu?
13. Vì sao callback HTTP đến sau Gateway timeout không thể tự gửi reply về Java invocation cũ?
14. Khi Splitter tạo ba parcel tasks, có nên dùng cùng eventId của parent cho cả ba không?
15. Vì sao technical CORRELATION_ID của Splitter có thể khác businessCorrelationKey?
16. Publish-Subscribe có tự đợi mọi subscriber hoàn tất để trả một result không?
17. Một Message có Spring header tenant-a nhưng DomainEnvelope metadata tenant-b cần được xử lý thế nào?
18. Điều gì xảy ra nếu converter của outbound adapter chỉ serialize envelope.payload?
19. HTTP HeaderMapper có phải là authorization mechanism không?
20. Vì sao ThreadLocal/MDC không thể là nguồn business identity trong async subflow?
21. Một redelivery có nên giữ receivedAt và eventId ban đầu không?
22. Vì sao Kafka/JMS ack thành công không chứng minh business effect đã commit?
23. Khi nào cần inbox/outbox thay vì chỉ dùng một Set nhớ eventId trong JVM?
24. Với Scatter-Gather, correlation và releaseStrategy khác trách nhiệm thế nào?
25. Nếu một provider callback đến muộn sau final decision, có được tự đổi kết quả cũ không?
26. Vì sao không dùng UUID mới cho mỗi retry nếu muốn idempotency?
27. Nếu schema v1 được replay khi subflow dùng v2, cần upcast ra sao?
28. Những metric nào giúp tìm một subflow làm mất metadata mà không tạo labels có cardinality lớn?
29. Có thể dùng bản sao bất biến của một metadata record qua các subflows concurrent không? Điều kiện nào về payload?
30. Vì sao việc code chạy đúng trong DirectChannel test chưa chứng minh xử lý an toàn khi qua broker/multi-instance?

## 31. Checklist trước khi triển khai

- Đã xác định **DomainEnvelope** khác Spring Message và transport envelope.
- Metadata có schemaVersion, tenant/event/correlation identity và nguồn gốc rõ ràng.
- Envelope và payload được thiết kế bất biến hoặc có defensive copies.
- Đã quy định metadata nào được giữ khi transform và khi nào tạo derived event identity.
- Tenant và workflow được xác minh tại ingress trước khi có trusted envelope.
- businessCorrelationKey bao gồm đúng scope tenant, entity và workflow epoch.
- Router chọn branch bằng enum/allowlist, không dùng channel name từ client.
- Các subflows STANDARD/EXPRESS đều trả **DomainEnvelope** với payload có kiểu chung.
- Downstream không cần đoán schema dựa trên header riêng của từng connector.
- Một Transformer trả Message mới có chiến lược propagation các runtime headers cần thiết.
- Nếu Spring headers mirror domain metadata, có validator phát hiện mismatch.
- Không copy raw replyChannel/errorChannel/routingSlip từ external messages.
- Không serialize live MessageChannel hoặc arbitrary Java object làm wire contract.
- HeaderMapper/MessageConverter từng HTTP/JMS/AMQP/TCP adapter đã được kiểm thử.
- Unwrap envelope chỉ diễn ra ở boundary có kiểm soát, đủ tenant/correlation/idempotency context.
- Splitter tạo child identities ổn định nếu children là logical events riêng.
- Technical correlation của child groups và business parent key không bị trộn.
- Publish-subscribe không dùng mutable objects chia sẻ giữa concurrent subscribers.
- Scatter-Gather có unique-member release policy và timeout phù hợp.
- Gateway sync chỉ dùng replyChannel cho request lifecycle đang chờ.
- Callback async sử dụng persistent business identity, không dựa vào expired temporary channel.
- Retry giữ stable event ID/business key; attempt IDs có thể khác.
- Downstream side effects có idempotency/transaction/reconciliation.
- Inbox/outbox/recovery bảo vệ khoảng hở crash giữa nhận và dispatch.
- Async channels có bounded pools/queues và không dựa business identity vào ThreadLocal.
- Có chính sách giữ/reap group metadata và late-arrival handling nếu dùng Aggregator.
- Envelope schema evolution có versioning, upcaster, compatibility tests và rollout plan.
- Unknown payload types được reject/quarantine; lỗi Transformer có error path riêng.
- Logs/metrics không rò rỉ dữ liệu nhạy cảm và tránh high-cardinality labels.
- Test bao phủ standard/express, tenant/epoch, metadata, header mismatch, unknown type, derived child IDs, retry, wire round-trip và restart.
- Runbook xác định điểm mất envelope từ ingress → Router → Transformer → adapter → downstream.

## 32. Kết luận

**Truyền envelope qua subflow** không chỉ là chuyển payload từ channel A sang channel B. Ta cần giữ một **hợp đồng ngữ cảnh** để các nhánh có thể xử lý độc lập nhưng vẫn trả kết quả thuộc đúng tenant, event và workflow. Một thiết kế rõ ràng thường có:

~~~text
Verified ingress
  -> DomainEnvelope<DeliveryRequest>
  -> Router
      -> standardSubflow -> mapPayload(DeliveryQuote)
      -> expressSubflow  -> mapPayload(DeliveryQuote)
  -> DomainEnvelope<DeliveryQuote>
  -> common validation / idempotent downstream
~~~

Với một **phép transform của cùng logical event**, giữ metadata bằng **mapPayload** giúp tránh tái tạo eventId, correlationId hoặc traceId tùy ý. Với **fan-out/Splitter tạo events mới**, phải tạo child identities/causation có chủ đích. Với **Gateway**, giữ replyChannel ở tầng runtime; với **adapter**, chọn wire envelope/header mapping có version và xác thực; với **retry**, giữ business identity để chống duplicate effects.

Thiết kế như vậy giúp Spring Integration kết hợp Router, Transformer, Splitter, Aggregator, Gateway, retry và error channel mà vẫn bảo toàn **ngữ nghĩa của message** ở mọi subflow, không chỉ giữ được kiểu dữ liệu Java.

## Tài liệu tham khảo

- [Enterprise Integration Patterns — Envelope Wrapper](https://www.enterpriseintegrationpatterns.com/patterns/messaging/EnvelopeWrapper.html): nguyên lý bọc thông điệp trong một cấu trúc chứa ngữ cảnh và chuyển qua boundary tích hợp.
- [Enterprise Integration Patterns — Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html): transform cấu trúc hoặc biểu diễn message.
- [Enterprise Integration Patterns — Correlation Identifier](https://www.enterpriseintegrationpatterns.com/patterns/messaging/CorrelationIdentifier.html): liên kết messages và replies thuộc cùng một công việc.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): xây dựng IntegrationFlow, routing, subflows và channels.
- [Spring Integration Reference — Routers](https://docs.spring.io/spring-integration/reference/router.html): route theo thông tin message, default output channel và routing semantics.
- [Spring Integration Reference — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): POJO transformers, input/output Messages và header propagation.
- [Spring Integration Reference — Message](https://docs.spring.io/spring-integration/reference/message.html): Spring Message và MessageHeaders.
- [Spring Integration Reference — Splitter](https://docs.spring.io/spring-integration/reference/splitter.html): child messages và sequence/correlation metadata.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation groups, release strategy, timeout và late arrivals.
- [Spring Integration Reference — Publish-Subscribe Channels](https://docs.spring.io/spring-integration/reference/channel/implementations.html): channel semantics và subscriber delivery.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): temporary replyChannel và request/reply lifecycle.
- [Spring Integration Reference — HTTP Support](https://docs.spring.io/spring-integration/reference/http.html): HTTP inbound/outbound adapters và gateways.
- [Spring Integration Reference — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS adapters, protocol correlation và header mapping.
- [Spring Integration Reference — TCP Message Correlation](https://docs.spring.io/spring-integration/reference/ip/correlation.html): TCP gateway, cooperating adapters, connection IDs và chuyển metadata.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): errorChannel, ErrorMessage và lỗi đồng bộ/bất đồng bộ.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): chống lặp message và lưu ý side effects.
