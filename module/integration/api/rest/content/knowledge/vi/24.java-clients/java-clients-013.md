# Truyền trace context và khóa chống trùng khi được hợp đồng hỗ trợ

## 1. Hai cơ chế khác nhau khi Java client gọi REST API

Một ứng dụng Java tạo đơn hàng hoặc thanh toán qua HTTP có thể gặp hai câu hỏi:

1. **Request này đã đi qua những dịch vụ nào, chậm hoặc lỗi ở đâu?** Cần *distributed tracing* để liên kết các span giữa Java client, API gateway, dịch vụ và database.
2. **Nếu mất phản hồi rồi gửi lại, server có tạo đơn/thu tiền hai lần không?** Cần *idempotency contract* và khóa chống trùng được xử lý bền vững ở server.

Trong module **INTEGRATION_API_REST**, hai vấn đề liên hệ trực tiếp với URI/resource, POST/PUT/GET, HTTP status, timeout, retry, OpenAPI, xác thực, phân quyền và kiểm thử API với Java/Spring. Có thể truyền cả **trace context** và **Idempotency-Key** trên cùng request, nhưng chúng **không thay thế nhau**:

| Khái niệm | Mục đích | Vòng đời/thay đổi | Ai thực thi? |
|---|---|---|---|
| **traceparent** | Liên kết span trong một trace phân tán | Span ID thường khác ở mỗi lần gọi HTTP/attempt | Tracing SDK/instrumentation và các service |
| **tracestate** | Thông tin riêng của hệ thống tracing đi cùng traceparent | Theo quy tắc W3C và tracing vendor | Tracing propagator |
| **baggage** (nếu sử dụng) | Mang metadata được phép đi qua các service | Có thể lan rất rộng; dễ rò dữ liệu | Tracing/baggage policy |
| **X-Request-ID / correlation ID** | Hỗ trợ đối chiếu log theo quy ước nội bộ | Tùy gateway và hợp đồng vận hành | Gateway/application |
| **Idempotency-Key** | Nhận diện cùng một *ý định nghiệp vụ* qua retry | **Giữ nguyên cho mọi attempt của một ý định** | **Server/provider**, bằng kho lưu bền vững |
| **Authorization** | Chứng minh danh tính/quyền | Token có thời hạn và scope | Security layer |

**Trace ID không phải Idempotency-Key.** Một ý định tạo đơn có thể có nhiều HTTP attempts và spans; chúng phải dùng **cùng khóa chống trùng**, dù mỗi attempt mang span context khác. Tracing không ngăn database ghi hai bản, còn idempotency không tự tạo distributed trace.

> **Nguyên tắc thiết kế:** Chỉ gửi các header theo hợp đồng của **đối tác/endpoint**. Không giả định API nào cũng hiểu Idempotency-Key, chấp nhận W3C Trace Context hoặc có cùng chính sách replay/TTL.

## 2. W3C Trace Context: truyền vị trí hiện tại của trace

### 2.1. traceparent và tracestate

**W3C Trace Context** quy định các HTTP headers phục vụ distributed tracing. Ví dụ minh họa:

~~~http
GET /api/orders/ord-741 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=opaque-state
~~~

Đối với phiên bản traceparent **00**, định dạng là:

~~~text
traceparent: 00-<trace-id>-<parent-id>-<trace-flags>

00          : version (2 chữ số hex)
trace-id    : 32 chữ số hex; không được toàn số 0
parent-id   : 16 chữ số hex; không được toàn số 0
trace-flags : 2 chữ số hex; bit sampling có ý nghĩa được định nghĩa
~~~

- **trace-id** nhóm các span của cùng luồng quan sát phân tán.
- **parent-id** xác định span phía gửi mà service nhận dùng làm remote parent, theo cách instrumentation tổ chức span.
- **trace-flags** có tín hiệu sampling; **không** phải cờ bảo đảm server ghi log hoặc lưu toàn bộ trace.
- **tracestate** là danh sách giá trị có cú pháp riêng, dành cho thông tin tracing của hệ thống/vendor; không nhét business payload, JWT hay PII vào đó.

**Ví dụ trên là cố định để học, tuyệt đối không dùng lại cùng trace ID/parent ID cho mọi request thực.** Hãy để tracing SDK sinh span context và HTTP propagator đúng chuẩn. Nếu dịch vụ nhận traceparent không hợp lệ, phải áp policy xử lý theo tracing instrumentation, không dùng nó làm nguồn danh tính đáng tin.

### 2.2. Trace context qua nhiều hop

Trong luồng **Java client → gateway → Orders → Payment**, mỗi service có thể tạo server span và child/client span cho lời gọi tiếp theo. **Không copy cứng traceparent inbound sang mọi outbound call**: propagator lấy Context.current() từ span hiện hành rồi inject context cho từng attempt.

**Một HTTP retry thường là một client attempt mới**, do đó mỗi attempt có thể có span ID khác nhau nhưng vẫn nằm trong trace của một ý định (nếu có context cha). Nếu job được tiếp tục sau nhiều giờ/restart, nó có thể bắt đầu trace mới; **Idempotency-Key vẫn phải giữ nguyên** theo thời hạn hợp đồng.

### 2.3. Baggage, correlation ID và trust boundary

**W3C Baggage** mang key/value qua nhiều service nên dễ lan tới third-party/log. Không truyền JWT, email, số thẻ, tenant secret hoặc payload nhạy cảm trong baggage/tracestate; hạn chế kích thước/cardinality và **allowlist nơi nhận**. **X-Request-ID** là quy ước correlation, không phải header W3C bắt buộc. Tất cả ID này **không phải credential**; chỉ propagate context qua trust boundary khi policy cho phép.

## 3. Idempotency-Key: hợp đồng nghiệp vụ chứ không phải “header thần kỳ”

### 3.1. Khi nào cần?

**GET/HEAD** có ngữ nghĩa *safe* và **PUT/DELETE** có ngữ nghĩa *idempotent* theo HTTP khi triển khai đúng, nhưng vẫn có thể cần xử lý timeout và concurrency. **POST tạo payment, đơn hàng hoặc lệnh có side effect** là trường hợp phổ biến cần khóa chống trùng nếu API/provider **công bố hỗ trợ**.

Ví dụ tạo đơn:

~~~http
POST /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 7b08dc36-3e44-4a6c-9ad8-9c025f13c415
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

{"customerId":"cus-17","items":[{"sku":"BOOK-01","quantity":2}]}
~~~

Khi xử lý thành công, server có thể trả:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/ord-741
Content-Type: application/json
Cache-Control: no-store

{"id":"ord-741","status":"PENDING_PAYMENT"}
~~~

Nếu response 201 bị mất sau commit, Java client có thể retry **cùng method/URI, tenant, payload logic và cùng Idempotency-Key**. Server phải định nghĩa việc trả lại **outcome đã lưu**: status, body và những header quan trọng như Location. Một số API trả chính xác status/body cũ; API khác trả trạng thái tài nguyên/operation hiện tại. **Không tự suy đoán**, phải dựa trên hợp đồng thực tế.

### 3.2. Những điều hợp đồng phải nói rõ

Contract cần quy định **tên/cú pháp/độ dài header**, endpoint/method áp dụng, phạm vi **tenant/account/operation**, cách so **fingerprint payload**, **TTL**, và **replay** status/header/body hay operation state. Nó còn phải định nghĩa khi request trước **đang xử lý** (chờ, 202 hoặc conflict), khi **key trùng payload khác**, và khi downstream timeout/outcome chưa xác định. Key phải được scope theo danh tính đã xác minh để tránh lộ kết quả khác tenant.

**Idempotency-Key không tự có hiệu lực chỉ vì client gửi header.** Nếu server bỏ qua key hoặc chỉ lưu trong một Map ở RAM, retry qua nhiều replica/restart vẫn có thể tạo bản ghi trùng. Một implementation nghiêm túc cần cơ chế claim nguyên tử, dedup, fingerprint và lưu outcome bền vững.

### 3.3. Không dùng khóa mới cho cùng ý định

Một quy tắc quản lý key ở phía client:

- **Sinh khóa ngẫu nhiên** (ví dụ UUID v4) một lần khi tạo logical intent mới.
- **Lưu khóa cùng payload** trong job/checkout bền vững; dùng lại qua mọi retry/restart trong TTL đã công bố; intent mới dùng key mới.
- Không lấy trace ID, request ID, timestamp, customer ID hoặc **hash body** đơn thuần làm key: cùng payload có thể là hai ý định độc lập.

Không cần gắn Idempotency-Key lên mọi GET hoặc mọi request; chỉ truyền khi API contract hỗ trợ/đòi hỏi. Nếu SDK và gateway có header policy, kiểm tra chúng **không xóa hoặc tự đổi** key giữa các lần retry.

## 4. Timeline dễ sai: server đã commit, client chỉ nhìn thấy timeout

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as Orders API
    participant D as Database
    C->>S: POST /orders, Key=K, Trace attempt A
    S->>D: Claim K, lưu order + outcome
    D-->>S: Commit
    S--xC: 201 bị mất trên mạng
    Note over C: Không biết đã commit hay chưa
    C->>S: Retry, Key=K, Trace attempt B
    S->>D: Tra cứu K + fingerprint
    D-->>S: Outcome của order đã tạo
    S-->>C: Replay/operation status theo contract
~~~

**Timeout không có nghĩa giao dịch đã rollback.** Nếu client sinh K2 ở lần gửi lại, server có thể coi đó là intent khác và tạo order mới. Cũng không thể bảo đảm exactly-once chỉ bằng timeout + retry, vì một payment provider khác có thể đã xử lý side effect ngoài DB của server.

Đối với tác vụ lâu, server có thể dùng **202 Accepted + operation resource**. Client tra trạng thái bằng GET thay vì gửi lại POST vô hạn. Khi provider đã trả trạng thái *không xác định*, cần inquiry/reconciliation; việc gửi lại với cùng key chỉ an toàn nếu provider có hợp đồng dedup tương ứng.

**Trace context mỗi attempt giúp điều tra vì sao timeout**, còn Idempotency-Key giúp server xác định hai attempts có cùng ý định. Hai cơ chế phải đi song song nhưng có vòng đời khác nhau.

## 5. Java HttpClient: giữ key theo intent, inject tracing theo attempt

Java **java.net.http.HttpClient** cho phép đặt request headers và timeouts. Truyền trace context thủ công có thể dùng **OpenTelemetry API + W3C propagator**, nhưng nếu JDK HttpClient **đã được auto-instrument**, không viết thêm propagator để tránh trùng traceparent hoặc span.

### 5.1. Sinh khóa một lần, không một lần cho mỗi request

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.UUID;

// Khởi tạo một lần cho ý định tạo đơn "mới".
String intentKey = UUID.randomUUID().toString();
String payload = """
    {"customerId":"cus-17",
     "items":[{"sku":"BOOK-01","quantity":2}]}
    """;

HttpClient http = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .build();

URI endpoint = URI.create("https://orders.example.test/api/orders");

// Ghi intentKey + payload vào durable job/checkout record nếu cần
// retry sau restart; KHÔNG tạo UUID mới trong mỗi attempt.
~~~

UUID v4 thường đáp ứng nhu cầu khóa có entropy tốt trong ví dụ, nhưng **định dạng và độ dài phải khớp contract provider**. Một số API yêu cầu giá trị key theo cú pháp riêng; đừng tự đặt dấu nháy hoặc encoding nếu tài liệu đối tác không yêu cầu.

### 5.2. Truyền W3C context bằng OpenTelemetry API

Ví dụ phương thức gửi **một attempt** dưới đây minh họa việc tạo client span, inject context hiện tại và gửi cùng intent key. Nó giả định **OpenTelemetry SDK/propagator đã được cấu hình** ở ứng dụng; OpenTelemetry API đơn thuần không tự tạo trace hữu ích.

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapSetter;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

class TracedOrdersClient {
    private static final TextMapSetter<HttpRequest.Builder> SETTER =
        (carrier, name, value) -> {
            if (carrier != null) carrier.header(name, value);
        };

    private final HttpClient http;
    private final Tracer tracer;

    TracedOrdersClient(HttpClient http) {
        this.http = http;
        this.tracer = GlobalOpenTelemetry.getTracer("orders-client");
    }

    HttpResponse<String> sendAttempt(
            URI uri, String json, String intentKey)
            throws IOException, InterruptedException {

        Span span = tracer.spanBuilder("POST /api/orders")
            .setSpanKind(SpanKind.CLIENT)
            .startSpan();

        try (Scope scope = span.makeCurrent()) {
            HttpRequest.Builder request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(8))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .header("Idempotency-Key", intentKey)
                .POST(HttpRequest.BodyPublishers.ofString(
                    json, StandardCharsets.UTF_8));

            // Inject context của span HIỆN TẠI cho attempt này.
            GlobalOpenTelemetry.getPropagators()
                .getTextMapPropagator()
                .inject(Context.current(), request, SETTER);

            return http.send(
                request.build(), HttpResponse.BodyHandlers.ofString());
        } catch (IOException | InterruptedException ex) {
            span.recordException(ex);
            throw ex;
        } finally {
            span.end();
        }
    }
}
~~~

**Điều kiện để ví dụ hoạt động đúng:**

- Cấu hình một **W3C Trace Context propagator** ở OpenTelemetry SDK, sampler/exporter và context của transaction/operation cha. Nếu chưa cấu hình, GlobalOpenTelemetry có thể hoạt động dạng **no-op** và không inject được traceparent thực.
- **Chỉ chọn một cơ chế instrumentation**. Nếu Java agent/instrumentation đã tạo client span/inject headers, bỏ đoạn manual span/inject này và chỉ truyền Idempotency-Key.
- Một lần gọi **sendAttempt** là một attempt. Nếu retry, gọi lại với **cùng intentKey và json**, nhưng tạo span mới bên dưới cùng parent operation context khi có thể.
- Java HttpClient **send() là blocking**; không gọi trực tiếp trong event-loop của WebFlux. Dùng sendAsync() hoặc WebClient nếu đường xử lý được thiết kế reactive.
- Không đưa Authorization vào log/tracing attributes. Token phải lấy từ cơ chế secrets/token provider an toàn, không hard-code trong mã hoặc ví dụ chia sẻ.

### 5.3. Đọc outcome: đừng chỉ dựa vào một exception

~~~java
TracedOrdersClient api = new TracedOrdersClient(http);
try {
    HttpResponse<String> res =
        api.sendAttempt(endpoint, payload, intentKey);

    if (res.statusCode() == 201) {
        // Parse và kiểm tra Location/body theo schema.
    } else if (res.statusCode() == 409) {
        // Phân tích code; key/payload conflict KHÔNG tự retry.
    } else if (res.statusCode() == 202) {
        // Chuyển sang GET operation status nếu contract cho phép.
    } else {
        // Xử lý 4xx/5xx theo contract và retry policy.
    }
} catch (java.io.IOException unknownOutcome) {
    // Mạng thất bại: server CÓ THỂ đã xử lý.
    // Retry chỉ khi endpoint hỗ trợ idempotency,
    // dùng lại intentKey/payload, giới hạn số lần & deadline.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Hủy / chuyển lại quyền quyết định cho tầng gọi; không retry mù.
}
~~~

Đây là **fragment cách quyết định**, không phải retry engine production. Một client cần giới hạn retry, backoff + jitter, tổng deadline, nhận diện 429/503/Retry-After và cơ chế truy vấn kết quả khi status vẫn không xác định. Không đọc trực tiếp dữ liệu do server trả như lệnh thực thi hoặc URL tùy ý mà không áp policy tin cậy.

## 6. Spring RestClient và WebClient: ưu tiên instrumentation đã tích hợp

Trong **Spring Boot** có cấu hình Micrometer Observation/Tracing và bridge phù hợp, builder do Boot quản lý thường giúp HTTP client tham gia tracing tự động. Cần kiểm tra **Spring Boot version, tracing dependencies, builder configuration và trace propagation format**; chỉ có spring-boot-starter-web/webflux không mặc nhiên bảo đảm traceparent đã được gửi.

### 6.1. RestClient cho luồng blocking

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

record OrderInput(String customerId, java.util.List<Item> items) {
    record Item(String sku, int quantity) {}
}
record OrderView(String id, String status) {}

@Component
class OrdersRestGateway {
    private final RestClient client;

    // Dùng RestClient.Builder được Boot cấu hình, thay vì tự
    // RestClient.create() nếu muốn giữ các observation customizers.
    OrdersRestGateway(RestClient.Builder builder) {
        client = builder.baseUrl("https://orders.example.test").build();
    }

    ResponseEntity<OrderView> create(
            OrderInput input, String intentKey) {
        return client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .header("Idempotency-Key", intentKey)
            .body(input)
            .retrieve()
            .toEntity(OrderView.class);
    }
}
~~~

**RestClient là synchronous**. Dùng ResponseEntity để kiểm tra 201, Location và response body, thay vì chỉ lấy body rồi quên status/header. Với 4xx/5xx, retrieve() thường chuyển thành **RestClientResponseException** hoặc exception từ status handler; cần map đúng theo contract. Việc gửi Authorization cần OAuth2/credential integration phù hợp, không gắn token thật vào source.

Nếu tracing được cấu hình, HTTP client observation có thể **tạo span mới và inject trace headers tự động**. Đừng gắn một traceparent cũ vào defaultHeaders hoặc dùng UUID cho trace ID; nếu không thấy trace qua service, kiểm tra **observation registry, instrumentation, sampling và propagation format** trước khi thêm header thủ công.

### 6.2. WebClient cho luồng reactive

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
class OrdersWebGateway {
    private final WebClient client;

    OrdersWebGateway(WebClient.Builder builder) {
        client = builder.baseUrl("https://orders.example.test").build();
    }

    Mono<ResponseEntity<OrderView>> create(
            OrderInput input, String intentKey) {
        return client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .header("Idempotency-Key", intentKey)
            .bodyValue(input)
            .retrieve()
            .toEntity(OrderView.class);
    }
}
~~~

WebClient thực hiện khi Mono được **subscribe**. Nếu dùng retryWhen, mỗi lần resubscribe có thể tạo HTTP attempt mới; **intentKey là tham số cố định**, không đặt UUID.randomUUID() trong Mono.defer cho mỗi attempt. Tracing cần context propagation thích hợp qua Reactor; auto-instrumentation chỉ hiệu quả nếu cấu hình và scheduler/context không làm mất trace.

~~~java
// Minh họa: KHÔNG tạo key mới khi resubscribe.
String key = loadOrCreateDurableIntentKey();
Mono<ResponseEntity<OrderView>> operation =
    gateway.create(payload, key);

// Chỉ thêm retryWhen khi đã có hợp đồng idempotency,
// classification lỗi và retry budget được xác minh.
~~~

**Không retry mọi WebClientResponseException.** 400/401/403/409 do key-payload conflict không nên retry mù; 429/503/timeout có thể đủ điều kiện *theo hợp đồng* nhưng vẫn phải giới hạn tổng thời gian. WebClient và Reactor có thể phân biệt network failure, HTTP error và decoding error; cần phân loại đúng.

### 6.3. Chọn phương án client

**JDK HttpClient** hợp ứng dụng Java thuần; **RestClient** hợp blocking Spring MVC; **WebClient** hợp reactive. Nếu provider có SDK riêng, kiểm cách SDK quản lý header/retry. Không đổi sang reactive chỉ để có tracing: **W3C propagation không phụ thuộc framework**. Nên gom HTTP client/retry policy vào một tầng dễ kiểm thử.

## 7. Phía server phải bảo đảm dedup, không chỉ đọc header

Client gửi Idempotency-Key chỉ hữu ích khi **Orders API** thực thi contract. Một cách thiết kế bảng ledger tối thiểu:

~~~sql
CREATE TABLE idempotency_requests (
    tenant_id       VARCHAR(80) NOT NULL,
    operation       VARCHAR(100) NOT NULL,
    idem_key        VARCHAR(128) NOT NULL,
    request_hash    VARCHAR(128) NOT NULL,
    state           VARCHAR(20) NOT NULL,
    response_status INTEGER,
    response_body   TEXT,
    expires_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation, idem_key)
);
~~~

Đây là **schema minh họa**, cần điều chỉnh database, retention, response headers và isolation. Quy trình:

1. **Xác thực/ủy quyền** caller/tenant, validate header, xác định payload fingerprint theo contract.
2. **Claim nguyên tử** tenant + operation + key; chặn hai attempt cùng chạy side effect.
3. Key đã hoàn tất: fingerprint giống → replay; khác → **409**. Request đang xử lý → phản hồi theo in-flight policy.
4. Lưu outcome cùng business state khi có thể. Với provider ngoài DB cần **provider key, outbox/inquiry/reconciliation**.
5. Expire theo TTL; tránh xóa intent còn có retry hợp lệ.

Spring MVC controller có thể đọc header bằng:

~~~java
@PostMapping("/api/orders")
ResponseEntity<OrderView> create(
        @RequestHeader("Idempotency-Key") String key,
        @Valid @RequestBody CreateOrderRequest input,
        Authentication authentication) {
    OrderResult result = service.createOrReplay(
        verifiedCaller(authentication), key, input);
    return ResponseEntity.status(result.httpStatus())
        .location(URI.create("/api/orders/" + result.order().id()))
        .body(result.order());
}
~~~

Đây là **fragment** cần các DTO/use case và xử lý lỗi riêng; nó **không tự triển khai ledger**, cũng không bảo đảm có thể replay mọi header. Spring Security phải kiểm JWT/tenant/scope. Khi replay, status, Location và body phải lấy từ **quy tắc outcome lưu trữ**, không luôn giả định 201 bất kể contract.

### 7.1. Mô tả Idempotency-Key trong OpenAPI

~~~yaml
paths:
  /api/orders:
    post:
      operationId: createOrder
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          description: >
            Stable per logical create intent; scoped by caller/tenant.
            Reuse with identical payload during retries within the
            published retention period.
          schema: {type: string, minLength: 1, maxLength: 128}
      responses:
        '201': {description: Created or replayed saved result}
        '202': {description: Operation accepted, if async mode is supported}
        '400': {description: Invalid key or request}
        '401': {description: Authentication required}
        '403': {description: Forbidden}
        '409': {description: Key reused with different payload}
        '429': {description: Rate limited}
        '503': {description: Temporarily unavailable}
~~~

Đây là **fragment**, không phải tài liệu OpenAPI hoàn chỉnh; cần requestBody, response content, Location, operation status, securitySchemes và schema lỗi riêng. **Traceparent có thể được propagate theo tracing infrastructure**, nhưng không vì thế mà phải công bố nó như required business parameter; chỉ đưa vào contract khi API thực sự yêu cầu.

## 8. Retry policy: cùng key nhưng không retry vô hạn

| Tín hiệu Java client quan sát | Quyết định mặc định | Điều kiện để thử lại |
|---|---|---|
| **201/200** theo hợp đồng | Hoàn tất | Không retry |
| **202** và có operation URI | Poll status có giới hạn | Không gửi lại POST vô hạn |
| **400/401/403** | Sửa request/token/quyền | Không retry nguyên request |
| **409 key/payload mismatch** | Dừng, sửa bug quản lý key | Không sinh key mới để “thử may” |
| **409 in-progress** nếu API có quy ước | Hỏi operation/retry sau thời gian quy định | Theo policy rõ của provider |
| **429/503** | Backoff, tôn trọng Retry-After nếu có | API cho phép; retry budget còn |
| **408/502/504, IOException, timeout** | Kết quả có thể chưa xác định | Retry cùng key/payload hoặc hỏi status nếu contract hỗ trợ |
| **Response schema sai** | Báo lỗi tích hợp | Không tự retry giao dịch side effect |

Retry với **exponential backoff + jitter**, giới hạn số attempt và **deadline tổng**, tính cả thời gian chờ. Không tạo *retry storm* khi nhiều service đều retry 3 lần. Retry-After có thể là số giây hoặc HTTP date; chỉ sử dụng giá trị hợp lệ, có giới hạn tối đa theo chính sách. **Circuit breaker** giúp chống tải lan truyền nhưng không thay idempotency.

Khi API **không hỗ trợ** idempotency, sau timeout của POST không thể kết luận retry an toàn: ưu tiên truy vấn kết quả bằng business reference/operation ID, nếu không có thì cần đối soát hoặc hỗ trợ vận hành. Không tạo lại thanh toán chỉ vì user nhấn nút nhiều lần; khóa phải thuộc trạng thái checkout/job.

## 9. Security và observability: hai header đều là dữ liệu không đáng tin

- **TLS/auth:** HTTPS, xác minh certificate và token/scope; traceparent/key không phải danh tính.
- **Header/tenant:** giới hạn length/charset/CRLF; scope key theo caller/tenant đã xác minh.
- **Propagation/logs:** không gửi PII/JWT trong baggage, tracestate hoặc metrics labels; kiểm redirect và destination allowlist.
- **Payload:** lưu snapshot để retry cùng nội dung; nếu server so raw bytes, thay thứ tự JSON field/timestamp có thể bị coi là mismatch.

Một trace sampled bị thiếu trong dashboard **không chứng minh** request chưa tới server. Tương tự, log chỉ có một trace ID **không chứng minh** business effect chỉ chạy một lần. Để điều tra cần ghép trace, ledger, transaction ID, provider receipt và audit log có quyền truy cập.

## 10. Kiểm thử trace propagation và idempotency

### 10.1. Ma trận hợp đồng cần tự động hóa

| Bài test | Kết quả phải xác minh |
|---|---|
| Java client gọi API khi tracing bật | Có traceparent hợp lệ; outbound span liên kết context cha |
| Hai retry của cùng intent | **Cùng Idempotency-Key**, tracing attempt tạo span phù hợp |
| Client restart rồi retry | Khóa/payload được khôi phục; không tạo intent mới |
| Hai POST đồng thời cùng key/payload | Một business effect, outcome nhất quán |
| Một key với hai payload khác | Conflict rõ, không tạo hiệu ứng thứ hai |
| Request thiếu key khi endpoint bắt buộc | Lỗi theo contract, không chạy nghiệp vụ |
| Tenant A và B dùng cùng key | Không xem/ảnh hưởng outcome của nhau |
| Server commit rồi mất HTTP response | Retry cùng key không tạo order/charge trùng |
| 429/503 với Retry-After | Client backoff đúng, không vượt deadline tổng |
| Baggage chứa giá trị nhạy cảm | Filter/scrubber không lan truyền hoặc ghi log |

### 10.2. Test HTTP client với mock upstream

Dùng **OkHttp MockWebServer** hoặc WireMock để xem header gửi thật. Ví dụ fragment JUnit giả định tracing SDK/W3C propagator đã được cấu hình:

~~~java
mockServer.enqueue(new MockResponse()
    .setResponseCode(201)
    .addHeader("Location", "/api/orders/ord-741")
    .addHeader("Content-Type", "application/json")
    .setBody("{\"id\":\"ord-741\",\"status\":\"PENDING_PAYMENT\"}"));

String key = "intent-test-741";
client.sendAttempt(mockServer.url("/api/orders").uri(),
    payload, key);

RecordedRequest observed = mockServer.takeRequest();
assertEquals("POST", observed.getMethod());
assertEquals(key, observed.getHeader("Idempotency-Key"));
assertNotNull(observed.getHeader("traceparent"));
~~~

**Fragment không độc lập chạy:** cần mockServer, client, payload, imports, OpenTelemetry SDK và W3C propagator thực. Nếu tracing là no-op, assertion traceparent phải thất bại; **không hard-code header giả để test xanh**. Kiểm định dạng/quan hệ context thay vì assert trace ID cố định. Để kiểm retry, mock hai attempts và assert **cùng key**, số lần gọi phù hợp với policy.

**Server-side integration tests** cần DB thật/Testcontainers để chứng minh unique claim nguyên tử khi concurrent requests; mock repository không chứng minh dedup. Với payment provider, dùng sandbox hoặc fault injection mất response **sau commit**, rồi đối chiếu receipt và số charge. Không kết luận exactly-once chỉ vì HTTP test thấy response giống nhau.

## 11. Bài tập và đáp án gợi ý

**Bài 1 — Nhầm khóa.** Mỗi lần retry, Java client dùng trace ID mới làm Idempotency-Key. **Đáp án:** Sai: retry có thể bị xem là intent mới. Tạo khóa một lần cho logical intent; trace context để SDK quản lý theo từng span.

**Bài 2 — Lỗi sau commit.** POST thanh toán timeout nhưng provider có thể đã thu tiền. Có nên gửi lại với UUID mới? **Đáp án:** Không. Giữ provider idempotency key khi hợp đồng hỗ trợ; nếu chưa rõ outcome, tra operation status/inquiry và đối soát.

**Bài 3 — Reactor retry.** Đặt UUID.randomUUID() trong Mono.defer và thêm retryWhen. **Đáp án:** Mỗi resubscription có thể tạo key mới. Lấy/lưu key bên ngoài publisher, truyền cùng tham số qua mọi attempts.

**Bài 4 — Trace context.** Dịch vụ A copy nguyên traceparent inbound sang mọi outbound call. **Đáp án:** Instrumentation cần tạo child/client spans và inject context hiện hành; trace header không phải authentication.

**Bài 5 — Bảo mật.** Gửi baggage chứa email/raw JWT tới payment provider, dùng key toàn cục tra kết quả. **Đáp án:** Rò dữ liệu và nguy cơ chéo tenant; giới hạn propagation theo allowlist, loại PII/secret và scope key theo caller đã xác minh.

## 12. Checklist trước khi đưa Java client vào production

- [ ] Endpoint/provider **công bố** tracing và Idempotency-Key theo contract?
- [ ] Khóa gắn với **một logical intent**, lưu bền vững qua retry/restart và không đổi theo trace?
- [ ] Scope, fingerprint, TTL, replay và in-flight behavior được hiểu rõ?
- [ ] Trace context do SDK sinh/inject, không copy span cũ hoặc chèn trùng?
- [ ] HTTPS, token, baggage/tracestate, redirects và trust boundary được bảo vệ?
- [ ] Retry có error classification, backoff/jitter, deadline và Retry-After?
- [ ] 409 mismatch, 202 operation status và unknown outcome có nhánh xử lý riêng?
- [ ] Server/provider có dedup bền vững và tenant authorization, không chỉ đọc header?
- [ ] Tests bao phủ headers, concurrency, timeout sau commit và provider receipts?

**Kết luận:** **Trace context** giúp theo dõi đường đi của request, còn **Idempotency-Key** giữ một ý định nghiệp vụ không bị nhân đôi khi retry. Java HttpClient, Spring RestClient và WebClient đều có thể truyền hai cơ chế, nhưng cần để instrumentation quản lý trace, giữ khóa theo intent và **chỉ retry khi hợp đồng server/provider công bố và kiểm thử được sự an toàn**.
