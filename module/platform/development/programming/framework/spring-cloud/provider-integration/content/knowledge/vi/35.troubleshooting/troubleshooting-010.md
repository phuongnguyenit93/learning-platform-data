# Khoanh vùng bằng request ID và thu thập bằng chứng đã che bí mật

Khi một ứng dụng Spring Boot gặp lỗi với dịch vụ managed trên AWS, Azure hoặc Google Cloud, log thường chỉ cho thấy một exception ở phía ứng dụng. Để tìm nguyên nhân, cần nối được request đi qua những service nào, SDK đã gọi operation nào, provider trả lỗi gì và lần gọi cụ thể đó được ghi nhận ở đâu. Đồng thời, bằng chứng gửi cho đội vận hành hoặc cloud support phải đủ dùng nhưng không làm lộ credential, token, dữ liệu cá nhân hay payload nghiệp vụ.

Một mã định danh duy nhất không thể đại diện cho mọi lớp. **Request ID** định danh một request tới ứng dụng; **correlation ID** nối một nghiệp vụ qua nhiều request hoặc service; **trace ID/span ID** mô tả đường đi và thời gian của các thao tác; **provider request ID** giúp tra cứu một lần gọi API tại nhà cung cấp; **message/event ID** nhận diện thông điệp nghiệp vụ. Ghi đúng loại ID và giữ chúng liên kết với nhau sẽ rút ngắn thời gian điều tra đáng kể.

Bài học này hướng dẫn thiết kế định danh, truyền trace context qua HTTP và messaging, thu thập provider metadata, tạo log có cấu trúc, che bí mật theo allowlist và đóng gói bằng chứng an toàn cho một sự cố production.

Sau bài học, bạn có thể:

- Phân biệt request ID, correlation ID, trace ID, span ID, provider request ID, message ID và idempotency key.
- Tạo và truyền ID an toàn qua Spring Boot, HTTP client và message broker.
- Dùng Micrometer Tracing/OpenTelemetry để liên kết log với distributed trace.
- Ghi lại request ID của AWS, Azure và Google Cloud theo đúng API/SDK.
- Thu thập log, trace, metric, cấu hình runtime và thông tin phiên bản mà không lộ secret.
- Chuẩn bị evidence bundle có timestamp, request ID, operation, lỗi và bước tái hiện để đội vận hành xử lý.

## 1. Các loại ID và vai trò của chúng

| Định danh | Phạm vi | Ai tạo? | Dùng để làm gì? |
|---|---|---|---|
| Request ID | Một request tới một service | Ingress/gateway hoặc service nhận request | Tìm log của request ở một service cụ thể |
| Correlation ID | Một luồng nghiệp vụ có thể qua nhiều service/request | Gateway, service đầu tiên hoặc producer nghiệp vụ | Nối các thao tác cùng một business operation |
| Trace ID | Một distributed trace | Tracing SDK/instrumentation | Tìm toàn bộ trace gồm nhiều span qua service và dependency |
| Span ID | Một thao tác trong trace | Tracing SDK/instrumentation | Xác định service/client operation cụ thể và parent-child relationship |
| Provider request ID | Một request cụ thể tới API của cloud provider | Dịch vụ cloud | Tra cứu request trong log/telemetry của provider hoặc support case |
| Message ID | Một message do broker nhận diện | Producer/broker tùy dịch vụ | Theo dõi một lần gửi/giao message ở tầng broker |
| Event ID | Một sự kiện nghiệp vụ | Producer ứng dụng | Nhận diện sự kiện qua publish, retry, consumer và redelivery |
| Idempotency key | Một ý định thực hiện thao tác có thể bị gửi lại | Client hoặc service nghiệp vụ | Ngăn side effect bị áp dụng nhiều lần khi retry |

Các ID này có quan hệ nhưng không thay thế nhau. Một trace có thể chứa nhiều request tới cùng provider; mỗi lần retry có thể tạo provider request ID khác nhau. Một event có thể được giao nhiều lần với cùng event ID nhưng message delivery metadata khác nhau. Một correlation ID có thể tồn tại qua nhiều trace nếu workflow kéo dài qua thời gian hoặc được chia thành nhiều request độc lập.

```mermaid
flowchart TD
    U[Client request] --> G[API Gateway]
    G --> A[Spring Boot Service A]
    A --> B[Spring Boot Service B]
    B --> SDK[Cloud SDK call]
    A --> Q[Message Broker]
    Q --> C[Spring Boot Consumer C]
    C --> DB[(Managed Database)]
    subgraph IDs[Định danh và telemetry]
      R[Request ID mỗi service]
      K[Correlation ID nghiệp vụ]
      T[Trace ID và các Span ID]
      P[Provider request ID mỗi API attempt]
      E[Event ID / Message ID]
    end
    G -. gắn .-> R
    A -. giữ correlation .-> K
    A -. tạo span .-> T
    SDK -. nhận từ response .-> P
    Q -. mang metadata .-> E
```

## 2. Quy tắc tạo và sử dụng ID

### 2.1. Request ID

Request ID nên được tạo tại ingress hoặc service đầu tiên tiếp nhận request. Nó giúp tìm log trong phạm vi một service. Khi request đi qua nhiều service, mỗi service có thể tạo request ID riêng, nhưng cần giữ correlation ID và trace context để nối các đoạn với nhau.

Một số gateway đã tạo `X-Request-ID` hoặc header tương tự. Nếu tin cậy gateway, cấu hình gateway xóa header do client tự gửi và ghi đè bằng ID mới trước khi chuyển request vào ứng dụng. Nếu ứng dụng nhận request trực tiếp từ Internet, không nên tin vô điều kiện một ID do client cung cấp; client có thể cố tình dùng ID trùng để làm nhiễu log. Ứng dụng có thể tạo ID nội bộ mới và lưu ID bên ngoài dưới trường riêng đã kiểm tra.

Request ID không phải thông tin xác thực. Không dùng nó để cấp quyền, truy cập dữ liệu, bỏ qua rate limit hoặc xác định danh tính người dùng.

### 2.2. Correlation ID

Correlation ID nối các thao tác thuộc cùng một nghiệp vụ, ví dụ một checkout tạo order, reserve inventory, publish event và gửi notification. ID nên ổn định trong toàn workflow, kể cả khi message được retry hoặc xử lý bất đồng bộ sau vài phút.

Nếu hệ thống đã có `orderId`, `workflowId` hoặc `operationId`, có thể dùng một ID nghiệp vụ phù hợp làm correlation ID, nhưng cần cân nhắc không đưa giá trị nhạy cảm hoặc ID có thể đoán được vào log công khai. Không dùng email, số điện thoại, mã khách hàng có ý nghĩa cá nhân hoặc nội dung business làm correlation ID.

### 2.3. Trace ID và span ID

Distributed tracing mô tả quan hệ cha-con giữa các thao tác. Một trace ID được giữ qua nhiều service; mỗi span có span ID riêng. HTTP client instrumentation có thể tạo span cho lời gọi ra ngoài; SDK cloud cần instrumentation riêng hoặc interceptor nếu muốn có span cho từng operation.

W3C Trace Context định nghĩa các header phổ biến:

- `traceparent`: mang trace ID, parent span ID và trace flags.
- `tracestate`: mang vendor-specific tracing state khi cần.
- `baggage`: mang metadata cần truyền qua trace; chỉ đưa thông tin không nhạy cảm và giới hạn kích thước.

Không tự tạo hoặc sửa `traceparent` bằng cách ghép chuỗi thủ công nếu đã dùng tracing SDK. SDK chịu trách nhiệm validate, tạo span ID và quản lý sampling/context.

### 2.4. Provider request ID

Provider request ID được trả bởi dịch vụ cloud hoặc SDK response metadata. Nó thường là thông tin quan trọng nhất khi mở support case vì provider có thể dùng ID đó để tìm request trong hệ thống nội bộ. Ghi chính xác giá trị, service, operation, region và timestamp UTC.

Provider request ID thường định danh một lần gọi API, không phải toàn bộ nghiệp vụ. Nếu SDK retry ba lần, có thể có ba provider request ID. Ghi từng attempt nếu client/interceptor cho phép; đừng chỉ giữ ID của lần cuối nếu đang điều tra throttling hoặc lỗi ngẫu nhiên.

## 3. Truyền correlation và trace context qua Spring Boot

### 3.1. Tạo request ID tại servlet ingress

Với ứng dụng Spring MVC/Servlet, một `OncePerRequestFilter` có thể tạo request ID, lấy correlation ID từ gateway đáng tin cậy đã ghi đè header, đưa vào MDC và trả lại ID cho client:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public class RequestContextFilter extends OncePerRequestFilter {
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain
    ) throws ServletException, IOException {
        String requestId = UUID.randomUUID().toString();
        String incoming = request.getHeader("X-Correlation-ID");

        // Chỉ giữ incoming khi ingress đã được cấu hình xóa/ghi đè header
        // do client gửi và chuyển tiếp một ID đã được kiểm tra.
        String correlationId = incoming != null && SAFE_ID.matcher(incoming).matches()
            ? incoming
            : requestId;

        MDC.put("requestId", requestId);
        MDC.put("correlationId", correlationId);
        response.setHeader("X-Request-ID", requestId);
        response.setHeader("X-Correlation-ID", correlationId);

        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
            MDC.remove("correlationId");
        }
    }
}
```

Đăng ký filter bằng `@Component` hoặc `FilterRegistrationBean` theo kiến trúc ứng dụng. Regex giới hạn ký tự và độ dài để tránh log injection/giá trị quá lớn; việc validate không chứng minh nguồn gửi đáng tin cậy. Nếu không có gateway tin cậy ghi đè header, hãy bỏ qua `X-Correlation-ID` do client gửi và tạo correlation ID nội bộ.

MDC dựa trên thread-local. Với Servlet async, executor tùy chỉnh hoặc Reactor/WebFlux, context có thể đổi thread và MDC không tự truyền trong mọi trường hợp. Dùng Micrometer Context Propagation/Observation hoặc tracing instrumentation tương thích; không tự copy MDC qua thread mà không dọn context trong `finally`, vì thread pool có thể tái sử dụng thread giữa các request.

### 3.2. Dùng Micrometer Tracing/OpenTelemetry

Trong ứng dụng Spring Boot, ưu tiên tracing tích hợp với Micrometer thay vì tự viết parser `traceparent`. Với Spring Boot 3.x, một cấu hình thường dùng là Actuator, bridge OpenTelemetry và OTLP exporter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Hãy dùng dependency management/BOM của Spring Boot để chọn phiên bản tương thích; không tự ghim các phiên bản Micrometer/OpenTelemetry độc lập nếu chưa kiểm tra ma trận tương thích. Cấu hình tracing sampling có thể đặt trong `application.yml`:

```yaml
management:
  tracing:
    sampling:
      probability: 0.1
```

Sampling 0.1 chỉ là ví dụ, nghĩa là lấy mẫu khoảng 10% trace theo chiến lược head sampling tương ứng. Chọn tỷ lệ dựa trên volume, chi phí và yêu cầu điều tra. Với sự cố hiếm, cần cân nhắc tail sampling ở collector hoặc chính sách sampling tăng cường cho lỗi; head sampling có thể bỏ qua một trace trước khi biết nó sẽ thất bại.

### 3.3. Propagation qua HTTP client

Khi dùng Spring Boot auto-configured `RestClient.Builder` hoặc `WebClient.Builder` có observation/tracing instrumentation, Micrometer có thể truyền W3C trace context tự động theo cấu hình. Hãy inject builder được Spring quản lý thay vì tự `WebClient.builder()` hoặc tạo HTTP client hoàn toàn mới mà không gắn observation.

Ví dụ:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class InventoryClient {
    private final WebClient client;

    public InventoryClient(WebClient.Builder builder) {
        this.client = builder
            .baseUrl("https://inventory.internal")
            .build();
    }

    public InventoryResult find(String sku) {
        return client.get()
            .uri("/v1/items/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryResult.class)
            .block();
    }
}
```

Đoạn code chỉ minh họa cách inject builder đã được auto-configure. Trong WebFlux reactive, không gọi `.block()` trên event-loop; trả về `Mono<InventoryResult>` và để pipeline điều phối. Trong ứng dụng MVC, nếu cần gọi đồng bộ, chọn client và execution model phù hợp. Kiểm tra outbound request thực tế có `traceparent` và span được tạo; không giả định mọi third-party SDK đều tự động được instrument.

### 3.4. Propagate correlation ID riêng

Tracing instrumentation thường tự truyền `traceparent`, nhưng correlation ID nghiệp vụ là một trường riêng. Với `RestClient` đồng bộ chạy trên servlet thread, có thể thêm correlation ID từ MDC bằng interceptor:

```java
import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class PartnerRestClientConfiguration {
    @Bean
    RestClient partnerRestClient(RestClient.Builder builder) {
        return builder
            .requestInterceptor((request, body, execution) -> {
                String correlationId = MDC.get("correlationId");
                if (correlationId != null) {
                    request.getHeaders().set("X-Correlation-ID", correlationId);
                }
                return execution.execute(request, body);
            })
            .build();
    }
}
```

Interceptor này phù hợp với luồng đồng bộ có MDC đã được thiết lập. Với async executor hoặc Reactor, lấy correlation ID từ context propagation/command context và truyền tường minh; không đọc MDC thread-local rồi giả định nó luôn đúng. Chỉ gửi correlation ID tới service nội bộ hoặc đối tác đã thống nhất header này. `traceparent` vẫn do Micrometer/OpenTelemetry quản lý, không tự ghi đè trong interceptor.

## 4. Truyền ID qua message broker và công việc bất đồng bộ

HTTP trace kết thúc ở thời điểm request trả response, nhưng nghiệp vụ có thể tiếp tục trong consumer. Khi publish message, truyền event ID, correlation ID và trace context trong message headers/attributes theo cơ chế của broker hoặc binder.

| Trường | Mục đích | Quy tắc |
|---|---|---|
| `eventId` | Định danh sự kiện nghiệp vụ | Tạo một lần và giữ nguyên khi retry publish |
| `correlationId` | Nối các bước trong cùng workflow | Giữ nguyên qua producer, broker và consumer |
| `traceparent` | Nối trace qua ranh giới messaging | Dùng W3C propagation/instrumentation, không tự ghép chuỗi |
| `tracestate` | Vendor tracing state | Chỉ truyền nếu tracing SDK quản lý và broker hỗ trợ |
| `messageId` | Định danh message ở broker | Lưu broker ID trả về hoặc metadata nhận được |
| `idempotencyKey` | Ngăn side effect trùng | Ổn định theo thao tác nghiệp vụ, có unique constraint hoặc downstream support |

Không đưa token, email, số điện thoại, AccessKey hoặc dữ liệu nhạy cảm vào baggage/message headers. Header có thể được lưu trong broker, hiển thị ở console hoặc chuyển qua nhiều hệ thống ngoài phạm vi ứng dụng.

Với Spring Cloud Stream, các binder thường hỗ trợ message headers; cách mapping và propagation của W3C context phụ thuộc binder/version. Kiểm tra message thực tế ở consumer. Nếu dùng SDK trực tiếp, thêm metadata bằng API message attribute/header tương ứng và trích xuất ở consumer.

## 5. Thu thập provider request ID từ AWS, Azure và Google Cloud

### 5.1. AWS

AWS SDK thường cung cấp response metadata hoặc exception metadata có request ID. Tùy SDK generation và service, response header có thể là `x-amzn-RequestId`, `x-amz-request-id` hoặc header service-specific. Với S3, thường gặp `x-amz-request-id` và `x-amz-id-2`; không nên giả định một header duy nhất cho mọi AWS API.

Khi dùng AWS SDK for Java v2, đọc request ID từ response metadata nếu kiểu response hỗ trợ (ví dụ `response.responseMetadata().requestId()` đối với response AWS tương ứng). Với exception, giữ thông tin request ID/status/error code nếu SDK cung cấp. SDK execution interceptor có thể ghi nhận từng attempt và response metadata; tránh log request headers có Authorization signature hoặc session token.

Thông tin nên lưu: AWS service, operation, region, account/resource alias, SDK request ID, extended request ID nếu có, status/error code, attempt và timestamp UTC. Request ID không thay thế ARN/resource name hoặc trace ID.

### 5.2. Azure

Nhiều Azure service trả các header như `x-ms-request-id` và `x-ms-correlation-request-id`; một số SDK/API hỗ trợ client request ID hoặc request correlation metadata. Azure Service Bus có thể cung cấp TrackingId/diagnostic identifier theo operation. Header và metadata cụ thể khác nhau theo dịch vụ.

Khi dùng Azure SDK for Java, lấy response headers/diagnostic metadata từ response hoặc exception tương ứng. Nếu gửi client request ID, tạo ID an toàn và ghi cả giá trị client lẫn request ID do service trả về; không nhầm chúng. Với HTTP response, có thể ghi các header `x-ms-*` được tài liệu dịch vụ chỉ định, nhưng phải allowlist header và không dump toàn bộ response headers.

Thông tin nên lưu: subscription/tenant alias, resource/namespace, region, operation, `x-ms-request-id`, correlation/TrackingId nếu có, status/substatus, retry-after và SDK version. Không log bearer token hoặc SAS URL đầy đủ.

### 5.3. Google Cloud

Google Cloud không có một response request ID header thống nhất cho mọi API. Metadata phụ thuộc dịch vụ và client library. Một số API cung cấp request/operation identifier trong response hoặc exception; hãy đọc `ApiException`/response metadata và header được tài liệu của đúng dịch vụ công bố. Với Cloud Storage, upload/session và JSON/XML API có metadata riêng; không áp dụng một tên header chung cho mọi sản phẩm.

Với distributed tracing, dùng W3C `traceparent` hoặc cơ chế propagation được thư viện hỗ trợ. Cloud Logging có trường trace resource để liên kết log với trace; định dạng resource trace thường chứa project ID và trace ID. Header `X-Cloud-Trace-Context` xuất hiện trong một số môi trường/tích hợp cũ, nhưng không nên tự tạo song song với W3C context nếu instrumentation đã quản lý propagation.

Thông tin nên lưu: project/resource alias, region, service/method, status/error reason, SDK diagnostic metadata, operation ID nếu API bất đồng bộ, trace ID và timestamp UTC. Nếu không có provider request ID rõ ràng, ghi rõ trường đó là unavailable thay vì tự tạo một giá trị rồi gọi nhầm là ID của Google Cloud.

### 5.4. Bảng tham chiếu nhanh

| Provider | Metadata thường hữu ích | Nơi lấy |
|---|---|---|
| AWS | SDK `requestId`; `x-amzn-RequestId` hoặc `x-amz-request-id`; S3 có thể có `x-amz-id-2` | AWS SDK response/exception metadata hoặc response headers theo service |
| Azure | `x-ms-request-id`, `x-ms-correlation-request-id`, client request ID hoặc Service Bus TrackingId tùy dịch vụ | Azure SDK response/exception diagnostics hoặc allowlisted response headers |
| Google Cloud | API-specific request/operation metadata; trace resource/trace ID; diagnostics của client library | Google Cloud client response/exception metadata và Cloud Logging/Trace |

Không gộp tất cả vào một trường `requestId` rồi làm mất nguồn gốc. Dùng các trường riêng như `providerRequestId`, `providerOperationId`, `traceId` và `requestId`; thêm `provider`/`service` để biết ID thuộc hệ thống nào.

## 6. Log có cấu trúc để điều tra

Log text tự do thường khó truy vấn khi có hàng nghìn request đồng thời. Structured logging giúp tìm theo trường mà không cần parse câu văn.

Ví dụ một log event đã loại bỏ dữ liệu nhạy cảm:

```json
{
  "timestamp": "2026-11-24T04:15:32.481Z",
  "level": "ERROR",
  "service": "order-service",
  "environment": "production",
  "region": "ap-southeast-1",
  "requestId": "b6f8d2a0-7d5d-4d34-8f3d-7c3a3a7f9c10",
  "correlationId": "checkout-7f29d6a1",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "provider": "aws",
  "providerService": "dynamodb",
  "operation": "UpdateItem",
  "providerRequestId": "sample-provider-request-id",
  "resource": "orders-table-prod",
  "statusCode": 400,
  "errorCode": "ProvisionedThroughputExceededException",
  "attempt": 2,
  "durationMs": 184,
  "retryAfterMs": 250,
  "outcome": "throttled"
}
```

Các ID và request ID trong ví dụ là dữ liệu minh họa, không phải ID thật. Trường `resource` dùng alias thay vì ARN đầy đủ nếu ARN có account identifier hoặc tên nhạy cảm. Với hệ thống thực, schema log nên thống nhất giữa các service và được kiểm tra bởi logging pipeline.

### 6.1. Ghi log một provider attempt

Một lần gọi SDK nên có các trường tối thiểu:

- Provider, service, operation và region.
- Trace ID/span ID hiện tại.
- Correlation ID nghiệp vụ.
- Provider request ID trả về hoặc `null` nếu chưa nhận được response.
- Attempt number và tổng attempt nếu biết.
- Status/error code, latency và retry delay.
- Resource alias và payload size, không phải payload.

Nếu request timeout trước khi nhận response, provider request ID có thể không có. Ghi `providerRequestId: null`, `failurePhase: connect|read|unknown` nếu xác định được, và giữ client exception. Không tự điền request ID của ứng dụng vào trường provider request ID.

### 6.2. Gắn trace/span vào log

Với Micrometer Tracing, log correlation pattern có thể đưa `traceId` và `spanId` vào mỗi log line. Cách cấu hình pattern phụ thuộc Spring Boot version và logging backend. Nếu tự dùng MDC, bảo đảm context được dọn sau request và truyền đúng qua async boundary. Trong Reactor/WebFlux, ưu tiên context propagation thay vì dựa hoàn toàn vào thread-local MDC.

Không cần đưa toàn bộ header vào log để có correlation. Chỉ ghi các header allowlist như request ID, trace context và provider request ID; loại bỏ Authorization, Cookie, Set-Cookie, proxy auth và header chứa token.

## 7. Che bí mật và dữ liệu nhạy cảm

Evidence bundle cần đủ thông tin để điều tra nhưng phải tuân theo nguyên tắc **allowlist trước, redact sau**. Chỉ thu thập trường đã xác định cần thiết; không dump toàn bộ request/response, environment variables, HTTP headers, JVM properties hoặc cấu hình Spring rồi cố gắng xóa secret bằng regex sau đó.

### 7.1. Không đưa các dữ liệu sau vào log/ticket

- `Authorization`, `Proxy-Authorization`, bearer token, OAuth refresh/access token và cookie/session ID.
- AWS AccessKey/SecretKey/session token, Azure client secret/SAS token, Google service account private key hoặc access token.
- Private key, keystore password, truststore password, certificate material có chứa private key.
- URL ký sẵn (presigned URL/SAS URL) đầy đủ vì query string có thể mang quyền truy cập.
- Database URL chứa username/password, Redis connection string có credential, connection string của broker.
- Payload nghiệp vụ, file, email, số điện thoại, địa chỉ, dữ liệu định danh hoặc thông tin thanh toán nếu không thật sự cần thiết.
- Nội dung `baggage`, message header hoặc exception có thể chứa token/PII.

### 7.2. Các trường nên thu thập theo allowlist

| Nhóm | Trường phù hợp |
|---|---|
| Thời gian | Timestamp UTC, thời gian bắt đầu/kết thúc, duration, clock offset nếu biết |
| Định danh | Request ID, correlation ID, trace ID, span ID, provider request ID, event/message ID đã được phê duyệt |
| Ứng dụng | Service name, environment, release/build version, pod/instance alias, JDK và SDK version |
| Cloud | Provider, region, service/API, resource alias, operation |
| Kết quả | HTTP/status code, provider error code, exception class, retry attempt, retry-after, outcome |
| Kết nối | Hostname đã loại query/userinfo, port, proxy alias, TLS version, certificate issuer/expiry nếu cần |
| Hiệu năng | Latency, payload size, pool active/idle/pending, queue depth, CPU/memory summary |
| Bằng chứng | Sanitized stack trace, trace link, dashboard link đã kiểm tra quyền truy cập |

### 7.3. Che URL và header

Khi ghi URL, chỉ giữ scheme, hostname, port và path template đã loại dữ liệu nhạy cảm. Bỏ userinfo và query string mặc định. Ví dụ:

```text
Trước: https://user:secret@storage.example/bucket/file?sig=abc123&token=xyz
Sau:   https://storage.example/bucket/{object}
```

Không ghi `Authorization` rồi thay một phần token bằng `***`; tốt nhất không ghi header này từ đầu. Với header cần lưu, dùng allowlist rõ ràng:

```text
ALLOW:
  traceparent
  tracestate (nếu đã kiểm tra nội dung)
  x-request-id
  x-correlation-id
  x-amzn-requestid / x-amz-request-id
  x-ms-request-id

DENY BY DEFAULT:
  authorization
  proxy-authorization
  cookie
  set-cookie
  x-api-key
  x-amz-security-token
  all unknown headers
```

Tên header provider cụ thể cần được allowlist theo service. Không dùng danh sách trên làm bộ lọc đầy đủ cho mọi cloud SDK; mặc định an toàn là không log header chưa được duyệt.

### 7.4. Exception và stack trace

Stack trace hữu ích nhưng exception message có thể chứa URL đầy đủ, SQL, payload, credential hoặc tên tài nguyên nhạy cảm. Trước khi log, phân loại exception và chỉ ghi message đã làm sạch. Giữ cause chain ở hệ thống log có kiểm soát khi cần, nhưng áp dụng redaction tại appender/collector và giới hạn quyền truy cập.

Không trả stack trace hoặc provider request ID cùng thông tin nội bộ cho end user. API response nên có mã lỗi công khai và request ID do ứng dụng tạo; chi tiết kỹ thuật ở log/trace nội bộ.

## 8. Thu thập evidence bundle cho một sự cố

Một evidence bundle tốt cho phép người khác tái dựng timeline mà không cần quyền truy cập trực tiếp vào production data.

### 8.1. Nội dung đề xuất

| Artifact | Nội dung | Lưu ý bảo mật |
|---|---|---|
| Incident summary | Mô tả triệu chứng, ảnh hưởng, thời gian bắt đầu/kết thúc và phạm vi | Không chứa dữ liệu người dùng không cần thiết |
| Request timeline | Request ID, correlation ID, trace ID, span ID, provider request ID và timestamp UTC | Phân biệt ID nội bộ với ID provider |
| Sanitized logs | Log JSON liên quan, exception class/error code và stack trace đã rà soát | Loại secret, PII, payload và URL ký sẵn |
| Trace export/link | Span tree, dependency latency, retry và error span | Kiểm tra quyền truy cập và retention của tracing backend |
| Metrics snapshot | Error rate, latency, throttling, pool, queue/backlog, resource utilization | Dùng time range và timezone thống nhất |
| Runtime context | Service version, JDK, SDK/client version, region, instance alias | Không dump env hoặc system properties đầy đủ |
| Sanitized config | Timeout, retry, pool size, endpoint hostname/port và feature flags liên quan | Che password, token, private endpoint nếu chính sách yêu cầu |
| Network/TLS evidence | DNS result, TCP test, certificate issuer/SAN/expiry, proxy alias | Không đính kèm private key hoặc full proxy credentials |
| Reproduction | Bước tái hiện, request mẫu đã thay dữ liệu, expected/actual result | Dùng synthetic data và endpoint test nếu có |

### 8.2. Chuẩn hóa timeline UTC

Các service có thể chạy ở nhiều region/timezone. Dùng timestamp ISO 8601 UTC, ví dụ `2026-11-24T04:15:32.481Z`. Đảm bảo host/container đồng bộ thời gian qua NTP hoặc cơ chế của nền tảng. Nếu clock skew lớn, thứ tự log có thể sai dù trace context đúng.

Khi điều tra, chọn một khoảng thời gian hẹp quanh provider request ID trước, sau đó mở rộng để thấy retry và downstream effect. Ghi rõ time range inclusive/exclusive, timezone và độ chính xác timestamp. Không so sánh timestamp từ client và provider mà bỏ qua clock skew.

### 8.3. Ví dụ evidence summary

```text
Incident: INC-2026-1124-017
Service: order-service
Environment: production
Region: ap-southeast-1
Window (UTC): 2026-11-24T04:15:00Z .. 2026-11-24T04:20:00Z
Symptom: DynamoDB UpdateItem intermittently throttled
Request ID: b6f8d2a0-7d5d-4d34-8f3d-7c3a3a7f9c10
Correlation ID: checkout-7f29d6a1
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
Provider request ID: sample-provider-request-id (attempt 2)
Provider error: ProvisionedThroughputExceededException
Observed retry-after/backoff: 250 ms
Impact: 1.8% checkout requests exceeded 2 s latency
Evidence: sanitized log excerpt, trace link, throttling metrics, SDK version
Secrets/payload: omitted
```

Các ID và giá trị trên chỉ minh họa cách trình bày. Không đưa account ID, table key thật hoặc payload đơn hàng vào ticket nếu không cần thiết.

## 9. Quy trình khoanh vùng từ request ID

Khi nhận được một request ID từ người dùng hoặc gateway:

1. Xác định ID thuộc service nào và loại ID nào. Một `X-Request-ID` không tự động là provider request ID.
2. Tìm log ingress của service trong time range UTC; lấy correlation ID và trace ID.
3. Mở distributed trace, tìm span có lỗi hoặc latency cao; xác định service/client operation.
4. Tìm log SDK theo trace/span/correlation ID; lấy provider, service, operation, region và provider request ID.
5. Nếu có retry, liệt kê từng attempt theo thứ tự thời gian và request ID riêng.
6. Tra provider request ID trong công cụ/telemetry/provider support flow phù hợp; gửi thêm timestamp, region, operation và resource alias.
7. Đối chiếu metric cùng time window để xác định lỗi đơn lẻ, throttling, quota, pool saturation hay incident rộng.
8. Thu thập evidence bundle đã redaction, kiểm tra quyền truy cập rồi mới chia sẻ.

### 9.1. Nếu không tìm thấy request ID

Không tìm thấy ID có thể có nhiều nguyên nhân:

- Request chưa tới application (DNS, TLS, load balancer, ingress hoặc gateway từ chối trước đó).
- Gateway tạo ID nhưng không forward hoặc đổi tên header.
- Log bị sampling/filter/retention hoặc service ghi log sang backend khác.
- ID được tìm sai service, sai environment, sai region hoặc sai time range.
- ID bị truncate, normalize hoặc thay đổi khi qua proxy.
- Request timeout trước khi provider trả response nên không có provider request ID.

Mở rộng tìm kiếm bằng correlation ID, trace ID, timestamp, route, service version và status code. Kiểm tra access log ở ingress/gateway và metrics của load balancer. Không kết luận request chưa xảy ra chỉ vì không có log trong một service.

### 9.2. Nếu có nhiều provider request ID

Một trace có thể gọi nhiều provider API; một SDK call có thể retry nhiều lần. Tạo bảng timeline theo từng attempt:

| Thời điểm UTC | Span/operation | Attempt | Provider request ID | Kết quả | Duration |
|---|---|---:|---|---|---:|
| 04:15:32.100Z | DynamoDB UpdateItem | 1 | `req-a` | Throttled | 82 ms |
| 04:15:32.350Z | DynamoDB UpdateItem | 2 | `req-b` | Throttled | 184 ms |
| 04:15:32.800Z | DynamoDB UpdateItem | 3 | `req-c` | Success | 96 ms |

Ví dụ này cho thấy request ID khác nhau theo attempt nhưng correlation/trace vẫn nối chúng vào cùng thao tác nghiệp vụ. Khi mở support case, gửi tất cả request ID liên quan và đánh dấu attempt nào thành công/thất bại.

## 10. Công cụ và cách truy vấn log

Tên công cụ phụ thuộc nền tảng, nhưng cách tìm nên nhất quán:

- Bắt đầu bằng `requestId` hoặc `correlationId` chính xác.
- Mở trace theo `traceId` rồi tìm span có `status=ERROR`, `exception` hoặc latency bất thường.
- Lọc log SDK theo `providerService`, `operation`, `providerRequestId` và time range.
- So sánh error rate/latency/pool/backlog trong cùng khoảng thời gian.
- Kiểm tra release/config/secret rotation/deployment event ngay trước thời điểm lỗi.

Ví dụ truy vấn dạng khái niệm (cú pháp thực tế tùy log backend):

```text
service = "order-service"
AND correlationId = "checkout-7f29d6a1"
AND timestamp BETWEEN "2026-11-24T04:15:00Z" AND "2026-11-24T04:16:00Z"
```

Không đưa ID có thể truy cập dữ liệu nhạy cảm vào URL dashboard công khai. Link trace/log có thể cấp quyền xem payload hoặc metadata; chỉ chia sẻ cho người có quyền và dùng link có thời hạn nếu nền tảng hỗ trợ.

## 11. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
|---|---|---|
| Dùng một `requestId` cho mọi service và mọi lần retry | Mất khả năng phân biệt request/attempt | Giữ request ID theo service, trace ID xuyên hệ thống và provider request ID theo attempt |
| Gọi correlation ID là provider request ID | Support không tìm được request tại cloud provider | Lưu riêng trường và nguồn tạo ID |
| Tin header do client gửi mà không kiểm tra | Log spoofing, CRLF injection hoặc làm nhiễu điều tra | Gateway ghi đè header; validate charset/length; không dùng làm auth |
| Log toàn bộ request/response headers | Lộ token, cookie, SAS/presigned URL | Allowlist header cần thiết, deny-by-default |
| Gửi cả `.env`, environment dump hoặc `application-prod.yml` cho support | Lộ secret và topology nội bộ | Tạo sanitized config chỉ gồm property liên quan |
| Chỉ lưu request ID của lần retry cuối | Bỏ mất bằng chứng các lần throttling trước | Log từng attempt và request ID riêng |
| Dùng `orderId`/email làm metric label | Cardinality cao và rò rỉ dữ liệu | Dùng ID trong log/trace, metric tag dùng giá trị ổn định |
| Cho rằng không có trace nghĩa là không có request | Sampling hoặc propagation có thể làm trace không xuất hiện | Kiểm tra log, gateway, metric và trace sampling policy |
| Chia sẻ link dashboard không kiểm tra quyền | Người nhận có thể xem dữ liệu ngoài phạm vi | Dùng quyền tối thiểu, link giới hạn và evidence đã redaction |

## 12. Checklist bảo mật trước khi gửi bằng chứng

- [ ] Xác định người nhận và mục đích chia sẻ; chỉ gửi đúng phạm vi cần thiết.
- [ ] Dùng timestamp UTC, request ID, correlation ID, trace ID và provider request ID đúng trường.
- [ ] Ghi service, environment, region, operation, error code, duration và attempt.
- [ ] Giữ lại provider request ID chính xác; không thay bằng ID nội bộ.
- [ ] Đã loại Authorization, cookies, API key, access token, secret, private key và password.
- [ ] Đã loại presigned URL/SAS query, payload, PII và dữ liệu thanh toán.
- [ ] URL chỉ còn host/path template; query/userinfo đã bỏ.
- [ ] Exception/stack trace đã rà soát nội dung nhạy cảm.
- [ ] Không đính kèm `.env`, environment dump, heap dump hoặc full config chưa kiểm tra.
- [ ] Dashboard/trace link có quyền truy cập giới hạn và thời hạn phù hợp.
- [ ] File evidence được lưu ở vị trí có kiểm soát, retention và audit phù hợp.
- [ ] Đã có người rà soát redaction trước khi gửi ra ngoài tổ chức.

## 13. Kết luận

Khoanh vùng sự cố bằng request ID hiệu quả khi mỗi định danh có vai trò rõ ràng và được nối xuyên qua log, trace, SDK và broker. Request ID giúp tìm request ở một service; correlation ID nối nghiệp vụ; trace/span cho thấy đường đi; provider request ID hỗ trợ tra cứu phía cloud; event/message ID giúp theo dõi xử lý bất đồng bộ. Evidence bundle cần giữ timestamp, operation, attempt, mã lỗi, provider metadata và metric liên quan, đồng thời chỉ thu thập trường đã được duyệt. Áp dụng allowlist, loại secret tại nguồn và kiểm soát quyền chia sẻ sẽ giúp đội kỹ thuật điều tra nhanh mà không tạo thêm rủi ro dữ liệu.

## Tài liệu tham khảo

- [W3C Trace Context](https://www.w3.org/TR/trace-context/): chuẩn `traceparent` và `tracestate`.
- [W3C Baggage](https://www.w3.org/TR/baggage/): truyền metadata trong distributed trace và các giới hạn bảo mật.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, propagation và sampling.
- [Micrometer Tracing](https://micrometer.io/docs/tracing): trace/span, bridge và context propagation.
- [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/): truyền trace context qua process boundary.
- [AWS SDK for Java 2.x — Logging and metrics](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/logging-slf4j.html): logging và diagnostics SDK.
- [Azure SDK for Java — Logging](https://learn.microsoft.com/azure/developer/java/sdk/logging-overview): logging, diagnostics và request metadata.
- [Google Cloud — Structured logging](https://cloud.google.com/logging/docs/structured-logging): structured log fields và trace correlation.
- [Google Cloud — Correlate logs with traces](https://cloud.google.com/trace/docs/trace-log-integration): liên kết log với trace trong Cloud Logging.
