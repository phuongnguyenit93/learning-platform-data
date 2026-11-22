# Chỉ chuyển tiếp những header được cho phép

Trong kiến trúc microservices, `order-service` có thể gọi `inventory-service` bằng URL logic `http://inventory-service`. Spring Cloud LoadBalancer tìm `ServiceInstance` theo service ID, chọn một bản sao rồi để `RestClient`, `RestTemplate`, `WebClient` hoặc OpenFeign gửi HTTP request tới đích. Bên cạnh URL, method và body, request còn có **HTTP headers**; nếu một dịch vụ vô tình chép nguyên headers nhận từ caller sang downstream, những dữ liệu không nên vượt qua ranh giới tin cậy cũng có thể bị chuyển tiếp.

Ví dụ, `Authorization` dành cho API công khai có thể không phù hợp với `inventory-service`; `Cookie` của trình duyệt không nên đi theo lời gọi nội bộ; `X-Forwarded-Host` hoặc `X-Tenant-Id` do client không tin cậy tự thêm có thể đánh lừa logic routing và phân quyền; các header điều khiển kết nối như `Connection` không được sao chép tùy tiện sang một HTTP hop mới.

**Nguyên tắc của bài:** khi dịch vụ A gọi B, hãy **tạo headers mới từ một allowlist được thiết kế cho đúng operation**, thay vì chép tất cả headers từ request đến rồi loại bỏ một vài tên “có vẻ nguy hiểm”. Header chỉ được chuyển tiếp khi nó thực sự cần thiết, giá trị đã được xác thực/chuẩn hóa, nơi nhận có quyền nhìn thấy và HTTP client được giao trách nhiệm quản lý các trường giao thức.

## 1. Ranh giới tin cậy trong chuỗi lời gọi qua LoadBalancer

Giả sử luồng nghiệp vụ:

```text
Browser / External Client
        |
        v
API Gateway (xác thực, chuẩn hóa request)
        |
        v
order-service
        |  @LoadBalanced RestClient/WebClient/Feign
        v
Spring Cloud LoadBalancer chọn inventory-A hoặc inventory-B
        |
        v
inventory-service
```

Một request đầu vào có thể chứa:

```http
GET /api/orders/42 HTTP/1.1
Host: public.example.test
Authorization: Bearer <external-access-token>
Cookie: session=<browser-session>
X-Forwarded-Host: attacker.example.test
X-Tenant-Id: forged-tenant
Accept-Language: vi
X-Correlation-Id: user-controlled-value
Connection: keep-alive
```

**Không** nên truyền nguyên bản request trên thành:

```http
GET /api/v1/items/42 HTTP/1.1
Host: inventory-service
Authorization: Bearer <external-access-token>
Cookie: session=<browser-session>
X-Forwarded-Host: attacker.example.test
X-Tenant-Id: forged-tenant
...
```

Vì hai lời gọi có **khác audience, quyền truy cập, transport hop, host đích và hợp đồng API**. Việc API Gateway đã xác thực caller không làm mọi header caller gửi trở nên đáng tin. Đặc biệt, một header tên `X-User-Id` không phải chứng cứ về danh tính nếu nó do bên ngoài tự khai.

```mermaid
flowchart TD
    E[External client: headers không tin cậy] --> G[Gateway: xác thực, loại bỏ header giả, tạo context tin cậy]
    G --> A[order-service]
    A --> P[Header projection theo allowlist của operation]
    P --> L[Spring Cloud LoadBalancer: chọn ServiceInstance]
    L --> H[HTTP client dựng request mới]
    H --> B[inventory-service]
    A -.-> X[Không sao chép cả inbound headers]
    P -.-> Y[Không relay Cookie / Authorization / X-Forwarded-* tùy tiện]
```

**LoadBalancer không tự làm nhiệm vụ lọc dữ liệu bảo mật từ inbound request.** Nó chọn đích theo `service ID` và metadata/discovery phù hợp; chính ứng dụng, gateway và HTTP client phải quyết định header nào đi cùng request outbound.

## 2. Vì sao allowlist an toàn hơn copy-all hoặc denylist?

Có ba mô hình thường gặp:

| Mô hình | Cách triển khai | Rủi ro |
|---|---|---|
| **Copy-all** | Chép tất cả inbound headers sang outgoing request | Lộ token, cookie, header giả, hop-by-hop, proxy metadata |
| **Denylist** | Chép tất cả trừ các tên đã cấm | Header mới/khác tên có thể vượt qua; không có ranh giới cần biết |
| **Allowlist** | Outbound request chỉ chứa những tên và giá trị được phép cho operation | Dễ audit; mặc định không truyền dữ liệu lạ |

Ví dụ kiểu code **không nên dùng**:

```java
// SAI: copy hàng loạt dữ liệu từ request ngoài vào downstream.
restClient.get()
        .uri("/api/v1/items/42")
        .headers(out -> out.addAll(incomingHeaders))
        .retrieve()
        .body(ItemDto.class);
```

Không chỉ `Authorization` hoặc `Cookie`: sau này một middleware có thể thêm `X-Internal-Role`, `X-Debug-Token` hay `X-Session-Metadata` vào inbound headers. Với copy-all, chúng sẽ tự động bị chuyển tiếp dù chưa được review về quyền riêng tư hoặc tác động bảo mật.

**Allowlist là hợp đồng ứng dụng**, nên được mô tả bằng các quyết định cụ thể:

1. Header nào có ý nghĩa cho operation? Ví dụ `Accept-Language` cho việc bản địa hóa mô tả mặt hàng.
2. Ai được đặt giá trị? Caller ngoài, API Gateway sau xác thực, hay `order-service` tạo từ security context?
3. Giá trị phải có kiểu, độ dài, định dạng và tập cho phép như thế nào?
4. Đích nhận có quyền sử dụng dữ liệu này không? Có cần hạn chế theo tenant/scope/audience?
5. Header có phải loại HTTP transport, tracing hoặc identity mà framework cần xử lý riêng không?

Không có một allowlist duy nhất áp dụng đúng cho mọi dịch vụ. Với GET tồn kho, `Accept-Language` có thể hợp lý; với POST tạo charge, có thể cần `Idempotency-Key` đã chuẩn hóa, nhưng không có lý do gửi browser cookie hoặc token dành cho website.

## 3. Phân loại các header trước khi chuyển tiếp

| Header/nhóm | Quyết định điển hình | Giải thích |
|---|---|---|
| `Accept-Language` | **Cho phép có điều kiện** | Hữu ích cho nội dung đa ngôn ngữ, cần validate/sanitize |
| `X-Correlation-Id` | **Chỉ dùng giá trị tin cậy** | Gateway tạo hoặc chuẩn hóa; dùng để liên kết log, không phải credential |
| `traceparent`, `tracestate` | **Để tracing library xử lý** | Context propagation phải theo trust policy, không copy mù |
| `baggage` | **Giới hạn nghiêm ngặt** | Có thể chứa PII, tenant hoặc dữ liệu nhạy cảm; chỉ truyền field đã phê duyệt |
| `Idempotency-Key` | **Chỉ với operation ghi thích hợp** | Cần key ổn định, format/size và scope theo tenant/operation |
| `If-Match` / `If-None-Match` | **Theo hợp đồng API** | Có ý nghĩa với optimistic locking hoặc cache validation |
| `Accept` / `Content-Type` | **Đặt theo request outbound** | Phụ thuộc body/representation đích; không chép cứng từ inbound |
| `Authorization` | **Không relay tùy tiện** | Token phải đúng audience, scopes và chính sách delegation |
| `Cookie`, `Set-Cookie` | **Không copy mặc định** | Dữ liệu session/browsers không nên đi sang service không liên quan |
| `X-User-Id`, `X-Role`, `X-Tenant-Id` | **Không tin header client tự gửi** | Danh tính/quyền/tenant phải xuất phát từ context đã xác thực |
| `Forwarded`, `X-Forwarded-*`, `X-Real-IP` | **Không forward nguyên inbound** | Chỉ proxy tin cậy được dựng/chuẩn hóa, tránh spoofing |
| `Host`, `Content-Length`, `Transfer-Encoding` | **Để HTTP transport dựng đúng** | Liên quan đích kết nối và framing; không copy từ request gốc |
| `Connection`, `Keep-Alive`, `Upgrade` | **Không chuyển qua hop mới** | Thường là hop-by-hop; do proxy/client xử lý theo HTTP semantics |
| `Proxy-Authorization` / `Proxy-Authenticate` | **Không relay cho upstream ứng dụng** | Header dành cho proxy authentication |
| `X-Debug-*` hoặc các header nội bộ lạ | **Từ chối mặc định** | Cần review và cấp phép riêng, không dùng wildcard |

**Ghi chú:** Đây là bảng chính sách mẫu cho request của một microservice gọi microservice khác, không phải danh sách chuẩn HTTP buộc phải chặn tất cả các tên trong mọi kiến trúc. Ví dụ một reverse proxy được cấu hình đúng có thể tạo `Forwarded` hoặc `X-Forwarded-For` tại ranh giới tin cậy. Điểm quan trọng là **không lấy giá trị do client ngoài tự khai rồi tin rằng proxy đã xác nhận**.

### 3.1. Header hop-by-hop và trường do transport quản lý

Theo HTTP semantics, `Connection` có thể chứa **danh sách tên header áp dụng riêng cho kết nối hiện tại**:

```http
Connection: keep-alive, X-Connection-Debug
X-Connection-Debug: internal
```

Một intermediary HTTP đúng chuẩn không được tùy tiện chuyển các trường được liệt kê trong `Connection` sang hop tiếp theo. Danh sách đó **có thể thay đổi theo request** nên chỉ cấm tên `Connection` nhưng vẫn copy mọi header khác không giải quyết được vấn đề. Với outbound RestClient/WebClient/Feign, cách an toàn hơn là tạo headers mới từ allowlist nhỏ và để HTTP stack xử lý những trường giao thức.

`Host` không nên lấy từ request đầu vào: HTTP client phải dựng authority/host theo URI của `ServiceInstance` được chọn. Không tự đặt `Content-Length` nếu thư viện đã quản lý framing và body; gửi số byte không khớp có thể gây lỗi giao thức và trong môi trường proxy phức tạp tạo ra vấn đề bảo mật.

Những header như `Accept-Encoding`, `TE`, `Transfer-Encoding`, `Trailer` và `Upgrade` có ngữ nghĩa giao thức riêng; không đưa chúng vào allowlist nghiệp vụ nếu không thật sự triển khai một proxy HTTP đúng chuẩn.

## 4. Authentication, identity và tenant: không phải cứ có header là đáng tin

Ba ví dụ sai phổ biến:

```text
inbound.Authorization            -> outbound.Authorization       (relay token mù)
inbound.X-Tenant-Id              -> outbound.X-Tenant-Id         (tin tenant do user khai)
inbound.X-Forwarded-For          -> outbound.X-Forwarded-For     (tin IP do user khai)
```

Rủi ro gồm **credential leakage**, vượt ranh giới audience, thực hiện hành động với sai tenant, và bypass những logic phân quyền dựa trên header.

### 4.1. Hai cách xác thực giữa dịch vụ cần phân biệt

**Service-to-service identity:** `order-service` tự nhận diện là một service khi gọi `inventory-service`. Có thể dùng OAuth 2.0 client credentials hoặc cơ chế mTLS/service identity do hạ tầng quản lý. Credential outbound được cấp và quản lý bởi tầng bảo mật, **không sao chép từ inbound user token**.

**On-behalf-of / user delegation:** một số operation cần thực hiện thay mặt user. Khi đó token phải được kiểm tra audience, scopes, expiry và chính sách ủy quyền; hệ thống có thể cần token exchange hoặc cơ chế delegation do authorization server hỗ trợ. Không mặc định access token cấp cho `api.example.test` cũng hợp lệ cho `inventory-service`.

Phân quyền ở service B vẫn cần được thực thi theo resource/tenant. Header nội bộ không tự trở thành nguồn xác thực nếu có thể bị làm giả bởi một kết nối không tin cậy.

### 4.2. Đừng tạo danh tính từ header do caller tự khai

Giả sử caller gửi:

```http
X-User-Id: admin
X-Role: SUPERUSER
X-Tenant-Id: tenant-other
```

Nếu gateway không loại bỏ/ghi đè các header này, một interceptor sao chép nguyên sang downstream có thể khiến `inventory-service` tin vào giá trị giả. Thay vào đó, các identity claims cần được lấy từ **đối tượng principal/claims đã xác thực** và truyền qua phương án delegation tin cậy hoặc một context nội bộ có xác thực/tính toàn vẹn.

Nếu dự án dùng header tenant nội bộ theo một hợp đồng riêng, phải kiểm tra caller của kênh nội bộ thực sự được xác thực, giá trị tenant tương ứng principal và downstream **không chấp nhận** cùng header qua kênh công khai không tin cậy. Chỉ dùng header nội bộ như một chuỗi tùy ý là chưa đủ.

## 5. Tracing và correlation: cho phép quan sát không đồng nghĩa cấp quyền

`traceparent` và `tracestate` thường do OpenTelemetry/Micrometer Tracing hoặc instrumentation tương ứng tạo/quản lý. Chúng hỗ trợ nối các span trong chuỗi A → B → C, nhưng **không chứng minh** ai đã xác thực và không được dùng làm quyền truy cập.

Với request đi từ Internet vào, gateway có thể tiếp nhận một `traceparent` hợp lệ theo chính sách tracing hoặc tạo trace mới; việc tin vào sampling flag, baggage hay metadata ở phía ngoài cần có quy tắc riêng. **Không đặt token, password, số thẻ, email hay quyền người dùng vào `baggage` chỉ để dễ debug.**

`X-Correlation-Id` do ứng dụng định nghĩa có thể hữu ích khi cần kết nối log của nhiều dịch vụ. Cần giới hạn độ dài/ký tự, tránh CR/LF injection, và **không sử dụng correlation ID như một credential hoặc khóa phân quyền**.

Ví dụ ứng dụng cho phép từ bên ngoài một `X-Correlation-Id` nhưng phải chuẩn hóa ở ingress; với header không hợp lệ có thể tạo ID mới. Tuy vậy, nếu threat model yêu cầu không cho client kiểm soát correlation ID, hãy luôn tạo ID mới ở gateway.

Không tự sao chép tất cả headers tracing bằng `incomingHeaders` rồi lại để instrumentation thêm lần nữa: có thể tạo giá trị trùng, sai context hoặc vô tình lan truyền các baggage không được phép.

## 6. Thiết kế một lớp chiếu header theo operation

Thay vì sử dụng `HttpHeaders.addAll(inbound)` trên request outbound, có thể xây một helper **tạo mới** `HttpHeaders` từ những tên được duyệt. Ví dụ bài lab cho **GET đọc item**, chỉ cần:

- `Accept: application/json` do gateway tự đặt, không lấy từ incoming request.
- `Accept-Language` nếu đầu vào là một language tag đơn giản đã được chấp nhận.
- `X-Correlation-Id` do ingress/gateway tạo hoặc xác thực từ một context tin cậy.

Trong ví dụ, **không** forward `Authorization`, `Cookie`, `X-Tenant-Id`, `Forwarded`, `Host`, `Connection` hay các header ngoài danh sách.

```java
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

public final class AllowedHeaderProjector {

    private static final Pattern CORRELATION_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    // Chính sách cố ý hẹp cho lab: vi, en, en-US...
    // Không phải parser đầy đủ của Accept-Language theo HTTP.
    private static final Pattern SIMPLE_LANGUAGE =
            Pattern.compile("[A-Za-z]{2,3}(?:-[A-Za-z]{2})?");

    private AllowedHeaderProjector() {
    }

    public static HttpHeaders forItemRead(
            HttpHeaders incoming, String trustedCorrelationId) {

        Objects.requireNonNull(incoming, "incoming headers");
        Objects.requireNonNull(trustedCorrelationId, "correlation id");

        if (!CORRELATION_ID.matcher(trustedCorrelationId).matches()) {
            throw new IllegalArgumentException(
                    "Invalid trusted correlation identifier");
        }

        HttpHeaders outgoing = new HttpHeaders();
        outgoing.setAccept(List.of(MediaType.APPLICATION_JSON));
        outgoing.set("X-Correlation-Id", trustedCorrelationId);

        List<String> languages =
                incoming.get(HttpHeaders.ACCEPT_LANGUAGE);

        // Chỉ chấp nhận đúng một field-value đơn giản.
        // Nhiều giá trị hoặc chuỗi không hợp lệ sẽ không được relay.
        if (languages != null && languages.size() == 1) {
            String language = languages.get(0);
            if (SIMPLE_LANGUAGE.matcher(language).matches()) {
                outgoing.set(HttpHeaders.ACCEPT_LANGUAGE, language);
            }
        }

        return outgoing;
    }
}
```

Điểm đáng chú ý:

1. `outgoing` là **một đối tượng mới**; không có bất kỳ lệnh copy-all nào.
2. `Accept` được tạo từ **hợp đồng outbound**, không từ header do browser gửi.
3. `Accept-Language` được giới hạn theo **một cú pháp cố ý đơn giản** trong lab. Các header thực tế có thể chứa danh sách và `q` weights; muốn hỗ trợ đầy đủ phải dùng parser phù hợp, giới hạn kích thước và chuẩn hóa giá trị trước khi forward. Đừng tăng quyền forward chỉ bằng cách bỏ regex.
4. `X-Correlation-Id` chỉ đi từ **tham số được gọi là trusted**, do tầng đáng tin tạo/đã xác thực. Helper không kiểm chứng nguồn gốc của tham số: caller của helper phải bảo đảm ranh giới đó.
5. Giá trị bất thường của `Accept-Language` bị bỏ qua thay vì gửi sang downstream; trong hệ thống nghiêm ngặt có thể chọn trả HTTP 400 theo contract.

**Giới hạn scope:** ví dụ chỉ kiểm soát các header **có nguồn từ request ứng dụng**. HTTP transport vẫn có thể tự tạo các trường giao thức hợp lệ như `Host`, `Content-Length`, header kết nối hoặc tracing instrumentation có thể thêm context được cấu hình. Không nên kiểm tra raw wire request và kỳ vọng nó chỉ có đúng ba header ở trên.

### 6.1. Tạo correlation ID tại biên tin cậy

Một controller mẫu của `order-service` có thể tạo ID mới thay vì tin giá trị do caller ngoài tự gửi:

```java
import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ItemProxyController {

    private final InventoryGateway gateway;

    ItemProxyController(InventoryGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/api/proxy/items/{id}")
    ItemDto get(
            @PathVariable String id,
            @RequestHeader HttpHeaders inboundHeaders) {

        // Mỗi inbound request có một correlation ID do ứng dụng tạo.
        // Có thể lấy từ trusted gateway context nếu hạ tầng đã xác thực.
        String trustedCorrelationId = UUID.randomUUID().toString();

        return gateway.getItem(
                id, inboundHeaders, trustedCorrelationId);
    }
}
```

Controller này không relay `inboundHeaders.getFirst("X-Correlation-Id")`, không sử dụng cookie và không nhận `X-Tenant-Id` làm quyền truy cập. Trong hệ thống có tracing tập trung, nên tận dụng trace/span do instrumentation quản lý thay vì tự sinh ID ở từng hop; đoạn ví dụ chỉ nhằm minh họa **nguồn gốc tin cậy của một header ứng dụng**.

## 7. RestClient: gửi danh sách header được phép qua service ID

Ứng dụng Spring Boot dùng Spring Framework 6.1+ và Spring Cloud tương thích có thể tạo `@LoadBalanced RestClient.Builder`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Gateway áp dụng projector tại đúng operation:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record ItemDto(String id, String name, int available) {
}

@Service
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(
            @Qualifier("loadBalancedRestClientBuilder")
            RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    ItemDto getItem(
            String id,
            HttpHeaders incoming,
            String trustedCorrelationId) {

        HttpHeaders allowed = AllowedHeaderProjector.forItemRead(
                incoming, trustedCorrelationId);

        return restClient.get()
                .uri("/api/v1/items/{id}", id)
                .headers(outgoing -> outgoing.addAll(allowed))
                .retrieve()
                .body(ItemDto.class);
    }
}
```

Đoạn `outgoing.addAll(allowed)` **khác hoàn toàn** việc `addAll(incoming)`: `allowed` là kết quả xây dựng mới từ allowlist đã kiểm tra. Nếu code dùng `RestClient.Builder` được đánh dấu `@LoadBalanced` và discovery có `inventory-service`, LoadBalancer chọn một `ServiceInstance` cho mỗi lời gọi theo cấu hình; header filtering không thay thuật toán Round Robin/Random.

Ví dụ `application-lab.yml` với hai instance:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8091
              - uri: http://localhost:8092
```

Điều kiện lab: Spring Cloud BOM tương thích với Spring Boot; client có `spring-cloud-starter-loadbalancer` và starter HTTP tương ứng. `SimpleDiscoveryClient` chỉ cung cấp danh sách tĩnh; nó không xác thực header thay ứng dụng và không tự phát hiện đầy đủ health của từng instance. Khi chạy trong container, `localhost` của client là container client, không phải host hoặc container provider.

### 7.1. RestTemplate cũng cần tạo HttpEntity mới

Với code dùng `@LoadBalanced RestTemplate`:

```java
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

ItemDto findWithRestTemplate(
        RestTemplate loadBalancedRestTemplate,
        String id,
        HttpHeaders incoming,
        String trustedCorrelationId) {

    HttpHeaders allowed = AllowedHeaderProjector.forItemRead(
            incoming, trustedCorrelationId);

    HttpEntity<Void> request = new HttpEntity<>(allowed);

    ResponseEntity<ItemDto> response =
            loadBalancedRestTemplate.exchange(
                    "http://inventory-service/api/v1/items/{id}",
                    HttpMethod.GET,
                    request,
                    ItemDto.class,
                    id);

    return response.getBody();
}
```

Đây là **đoạn phương thức minh họa**, giả định `RestTemplate` được truyền vào đã cấu hình LoadBalancer và timeout phù hợp. Không viết `new HttpEntity<>(incoming)` khi nguồn là request public: như vậy vô tình bỏ qua chính sách allowlist.

## 8. WebClient: không dùng copy-all trong filter reactive

Với Spring WebFlux, `@LoadBalanced WebClient.Builder` cho phép gọi theo service ID:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveHttpConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Gateway chỉ áp dụng headers đã chiếu:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryGateway {

    private final WebClient client;

    ReactiveInventoryGateway(
            @Qualifier("loadBalancedWebClientBuilder")
            WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    Mono<ItemDto> getItem(
            String id,
            HttpHeaders inbound,
            String trustedCorrelationId) {

        HttpHeaders allowed = AllowedHeaderProjector.forItemRead(
                inbound, trustedCorrelationId);

        return client.get()
                .uri("/api/v1/items/{id}", id)
                .headers(headers -> headers.addAll(allowed))
                .retrieve()
                .bodyToMono(ItemDto.class);
    }
}
```

Vì request WebClient thường được thực hiện khi có subscriber, code không nên dựa vào một `ThreadLocal`/`RequestContextHolder` ở thời điểm phát HTTP request để âm thầm lấy headers từ request đầu vào; thread có thể khác và context có thể mất hoặc bị dùng sai. **Truyền các giá trị đã chuẩn hóa một cách tường minh** qua đối tượng context của operation hoặc Reactor Context với quy tắc rõ ràng.

Nếu sử dụng `ExchangeFilterFunction` để thêm header chung, hãy chắc rằng filter chỉ thêm các header được chứng thực/ủy quyền (ví dụ tracing được quản lý), không copy `ServerHttpRequest.getHeaders()` toàn bộ. Cần đặc biệt chú ý không đưa user token vào tất cả outbound requests do dùng chung `WebClient.Builder`.

## 9. OpenFeign: khai báo rõ header nào là tham số của API

Feign có thể nhận các header được phép dưới dạng tham số tường minh, không cần một `RequestInterceptor` đọc toàn bộ `HttpServletRequest`:

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @GetMapping("/api/v1/items/{id}")
    ItemDto getItem(
            @PathVariable("id") String id,
            @RequestHeader("Accept-Language") String language,
            @RequestHeader("X-Correlation-Id") String correlationId);
}
```

Ứng dụng client cần `spring-cloud-starter-openfeign`, `spring-cloud-starter-loadbalancer` và Spring Cloud BOM tương thích với Spring Boot. Bật `@EnableFeignClients` trên ứng dụng Spring Boot hoặc khai báo phạm vi scan Feign client tương ứng; interface trên dùng kiểu `ItemDto` đã định nghĩa ở mục 7.

Lớp service chuẩn hóa input trước khi gọi:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;

@Service
class InventoryFeignGateway {
    private final InventoryFeignClient client;

    InventoryFeignGateway(InventoryFeignClient client) {
        this.client = client;
    }

    ItemDto getItem(
            String id,
            HttpHeaders incoming,
            String trustedCorrelationId) {

        HttpHeaders allowed = AllowedHeaderProjector.forItemRead(
                incoming, trustedCorrelationId);

        // Contract ví dụ yêu cầu một ngôn ngữ; fallback là "vi".
        String language = allowed.getFirst(HttpHeaders.ACCEPT_LANGUAGE);
        if (language == null) {
            language = "vi";
        }
        return client.getItem(
                id, language, allowed.getFirst("X-Correlation-Id"));
    }
}
```

Ưu điểm: khi review interface, người đọc nhìn thấy chính xác **hai header ứng dụng** mà operation nhận. Tầng HTTP của Feign vẫn có thể thêm header giao thức, encoder hoặc tracing instrumentation phù hợp.

Nếu chọn `RequestInterceptor` vì nhiều phương thức cần chung context, cấu hình interceptor **theo từng Feign client** và chỉ đọc dữ liệu từ context đáng tin cậy. Tránh kiểu:

```java
// SAI: relay hàng loạt các giá trị do caller đầu vào kiểm soát.
// Đặc biệt nguy hiểm với Authorization, Cookie, X-User-Id...
template.headers(incomingHeaders);
```

Đoạn trên chỉ minh họa **antipattern**, không phải snippet có đủ import để chạy. Tránh cấu hình interceptor global chứa thông tin xác thực của một downstream khiến token vô tình đi tới các service ID khác.

### OpenFeign có ErrorDecoder không đồng nghĩa đã lọc header

`ErrorDecoder` chuyển HTTP response lỗi thành exception; nó **không xác thực** những outbound headers. Một Feign client có ErrorDecoder đúng vẫn có thể leak browser cookie hoặc token nếu `RequestInterceptor` sao chép toàn bộ inbound headers.

## 10. Operation ghi: Idempotency-Key không phải một header được copy tùy tiện

Với POST tạo đặt chỗ hoặc thanh toán, khả năng retry an toàn thường cần **một mã thao tác logic ổn định**. Có thể dùng header `Idempotency-Key`, nhưng chỉ được chuyển khi API downstream có contract rõ ràng về deduplication, phạm vi tenant và thời hạn giữ kết quả.

Điểm khác biệt:

| GET đọc item | POST tạo reservation |
|---|---|
| Thường không cần idempotency key | Có thể bắt buộc idempotency key |
| `Accept-Language` có thể được phép | `Content-Type: application/json` theo body gửi |
| `X-Correlation-Id` từ context tin cậy | `X-Correlation-Id` từ context tin cậy |
| Không có lý do tự relay browser cookie | Không có lý do tự relay browser cookie |
| Retry GET với giới hạn thường dễ chấp nhận hơn | Retry POST chỉ an toàn nếu server chống lặp side effect |

Trong một lớp header policy riêng cho POST:

```java
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

final class ReservationHeaderProjector {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,80}");

    private ReservationHeaderProjector() {
    }

    static HttpHeaders forCreate(
            String trustedCorrelationId,
            String stableOperationKey) {

        Objects.requireNonNull(trustedCorrelationId);
        Objects.requireNonNull(stableOperationKey);

        if (!SAFE_ID.matcher(trustedCorrelationId).matches()
                || !SAFE_ID.matcher(stableOperationKey).matches()) {
            throw new IllegalArgumentException(
                    "Invalid internal operation metadata");
        }

        HttpHeaders out = new HttpHeaders();
        out.setAccept(List.of(MediaType.APPLICATION_JSON));
        out.setContentType(MediaType.APPLICATION_JSON);
        out.set("X-Correlation-Id", trustedCorrelationId);
        out.set("Idempotency-Key", stableOperationKey);
        return out;
    }
}
```

Đây là **ví dụ giới hạn format**, không thay thế việc xác thực/ủy quyền hoặc độ ngẫu nhiên của key. Giá trị `stableOperationKey` phải được tạo **một lần cho thao tác nghiệp vụ**, lưu/tái sử dụng giữa các lần retry và được downstream ràng buộc với operation, tenant/principal cùng fingerprint payload. Không lấy một `Idempotency-Key` do người dùng chưa xác thực tự đặt làm bằng chứng rằng một giao dịch đã tồn tại hoặc thuộc về họ.

Nếu retry request ghi với key mới ở mỗi lần thử, server có thể coi đó là **hai thao tác khác nhau**. Nếu retry đi từ `reservation-A` sang `reservation-B`, kho idempotency phải được chia sẻ và quản lý concurrency, không chỉ là một `HashMap` riêng trên từng instance.

### Ví dụ RestClient POST có kiểm soát

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record ReservationCommand(String itemId, int quantity) {
}

record ReservationResult(String reservationId) {
}

@Service
class ReservationGateway {

    private final RestClient client;

    ReservationGateway(
            @Qualifier("loadBalancedRestClientBuilder")
            RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://reservation-service")
                .build();
    }

    ReservationResult reserve(
            ReservationCommand command,
            String trustedCorrelationId,
            String stableOperationKey) {

        HttpHeaders allowed = ReservationHeaderProjector.forCreate(
                trustedCorrelationId, stableOperationKey);

        return client.post()
                .uri("/api/v1/reservations")
                .headers(out -> out.addAll(allowed))
                .body(command)
                .retrieve()
                .body(ReservationResult.class);
    }
}
```

Snippet dùng `@Qualifier` để inject **đúng bean `@LoadBalanced`**, không dựa vào tên tham số khi ứng dụng có nhiều builder. Đây là ví dụ cách gửi header, **chưa tự bật retry** và **chưa cài đặt idempotency ở server**.

## 11. Response headers cũng cần allowlist riêng

Chiều request A→B và response B→A là **hai ranh giới chính sách khác nhau**. Không được suy ra rằng nếu `Accept-Language` được phép gửi đi thì mọi response header từ provider đều an toàn trả cho browser.

| Response header | Chính sách ví dụ khi trả ra public API |
|---|---|
| `Content-Type` | Đặt theo body mà gateway **thực sự trả**, không sao chép khi đã transform dữ liệu |
| `ETag` / `Last-Modified` | Chỉ forward khi còn đúng với representation công khai |
| `Cache-Control` | Do chính sách cache của gateway quyết định, tránh cache nhầm dữ liệu tenant/private |
| `Retry-After` | Có thể dùng khi trả 429/503, sau khi parse và áp giới hạn phù hợp |
| `X-Correlation-Id` | Nếu công bố, dùng ID do hệ thống tin cậy tạo/đã chuẩn hóa |
| `Set-Cookie` | Không forward cookie nội bộ mặc định |
| `WWW-Authenticate` | Không tự phản chiếu challenge nội bộ cho browser khác audience |
| `Server`, `X-Powered-By`, header debug nội bộ | Thường loại hoặc chuẩn hóa để hạn chế lộ chi tiết hạ tầng |
| `Transfer-Encoding`, `Connection` | Để HTTP stack của hop trả lời quản lý |

Ví dụ provider trả `Cache-Control: public` nhưng response chứa dữ liệu tồn kho riêng theo tenant: nếu proxy copy nguyên, shared cache có thể lưu dữ liệu sai phạm vi. Tương tự, nếu proxy chuyển đổi body nhưng vẫn copy `ETag` từ upstream, validator có thể không còn tương ứng với representation trả cho người dùng.

Không sao chép `Set-Cookie` từ `inventory-service` thành cookie của domain công khai nếu đó không phải một phần thiết kế session đã được phê duyệt. Cũng không phản chiếu nguyên error body, trace header nội bộ hay auth challenge của service khác.

### 11.1. Chuyển tiếp status không đồng nghĩa chuyển toàn bộ metadata

Một gateway có thể chọn trả HTTP 404 khi upstream trả `ITEM_NOT_FOUND`, hoặc trả 503 khi downstream tạm không phục vụ. Dù giữ status, **error payload và response headers** vẫn cần được xây lại theo contract công khai, tránh tiết lộ hostname, stack trace, token và internal routing.

## 12. Khi nào không nên dùng allowlist quá chung?

Một header được phép cho operation A có thể nguy hiểm cho operation B:

| Operation | Header nên xem xét | Header không nên “kế thừa” tự động |
|---|---|---|
| GET danh mục | `Accept-Language` | `Idempotency-Key`, user session cookie |
| GET dữ liệu tenant | Auth context đã xác minh, delegation được cấp đúng audience | `X-Tenant-Id` do browser tự khai |
| POST tạo charge | `Idempotency-Key` ổn định, content type, auth đến đúng audience | Cookie của website, Bearer token sai audience |
| Upload file | `Content-Type` thật của body, metadata đã kiểm tra | `Content-Length` do caller tự tuyên bố không khớp body |
| Call qua gateway liên vùng | Trace context, region/zone policy tin cậy | `X-Forwarded-Host` hoặc tenant header do ngoài mạng tự gửi |

Không nên đưa mọi header đã từng được phép ở bất kỳ endpoint nào vào **một allowlist global duy nhất** rồi áp cho tất cả Feign/RestClient/WebClient calls. Chính sách phải có **ngữ cảnh: service đích, operation, mức nhạy cảm của dữ liệu và trust boundary**.

### Header name không phân biệt chữ hoa/chữ thường

HTTP field names là case-insensitive: `authorization` và `Authorization` cùng một tên về mặt ngữ nghĩa. Nếu dùng chính sách so sánh tên bằng `equals` phân biệt chữ hoa/chữ thường, người dùng có thể vượt qua denylist lỗi bằng cách đổi kiểu viết hoa.

Trong ví dụ `AllowedHeaderProjector`, ta **chỉ truy vấn tên được cho phép** qua `HttpHeaders` và tạo lại `HttpHeaders` mới. Cách này tránh việc phải xây denylist phân biệt hàng chục kiểu chữ hoa/thường hoặc wildcard `X-*`.

### Header có thể xuất hiện nhiều lần

Một request có thể chứa nhiều giá trị cho cùng header, hoặc một field-value chứa danh sách phân tách dấu phẩy. Đừng đơn giản lấy `getFirst()` cho header nhạy cảm khi hợp đồng không cho phép nhiều giá trị; có thể có sự khác biệt parsing giữa gateway và provider. Chính sách cần xác định rõ **được phép một hay nhiều giá trị, cách chuẩn hóa và xử lý khi trùng**.

Trong helper ở mục 6, `Accept-Language` có nhiều field-values sẽ bị bỏ qua; đây là một quyết định đơn giản cho lab. Với `Authorization` hoặc identity header, không nên chấp nhận nhiều giá trị nhập nhằng và cũng không relay chúng tự động.

## 13. Bài lab: kiểm tra request tại provider thay vì chỉ nhìn code client

Bài lab sử dụng:

| Thành phần | Port / service ID | Vai trò |
|---|---|---|
| `order-service` | `localhost:8080` | Nhận request không tin cậy, áp allowlist, gọi downstream |
| `inventory-A` | `localhost:8091` | Trả item, ghi nhận tên header đã tới |
| `inventory-B` | `localhost:8092` | Cùng contract, giúp quan sát khi LoadBalancer chọn bản sao khác |
| Service ID logic | `inventory-service` | Được `@LoadBalanced` client sử dụng |

Khai báo `SimpleDiscoveryClient` như mục 7. Hai provider có cùng endpoint để dễ quan sát headers ở cả A và B:

```java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InventoryDemoController {

    private final String instanceName;

    InventoryDemoController(@Value("${server.port}") int port) {
        this.instanceName = "inventory-" + port;
    }

    @GetMapping("/api/v1/items/{id}")
    ItemDto item(
            @PathVariable String id,
            @RequestHeader HttpHeaders received) {

        // Chỉ log tên và sự hiện diện của header trong lab.
        // Không ghi giá trị token, cookie hoặc danh tính.
        System.out.println(Map.of(
                "instance", instanceName,
                "acceptLanguagePresent",
                    received.containsKey(HttpHeaders.ACCEPT_LANGUAGE),
                "authPresent",
                    received.containsKey(HttpHeaders.AUTHORIZATION),
                "cookiePresent",
                    received.containsKey(HttpHeaders.COOKIE),
                "tenantHeaderPresent",
                    received.containsKey("X-Tenant-Id"),
                "forwardedHostPresent",
                    received.containsKey("X-Forwarded-Host")));

        return new ItemDto(id, instanceName, 12);
    }
}
```

Đây là code cho **môi trường học tập**: logging mỗi request ra stdout không phải chiến lược giám sát production. Các trường `authPresent` và tương tự chỉ ghi **boolean**, không ghi giá trị credential. `ItemDto` phía provider và client phải có cùng cấu trúc `(String id, String name, int available)` để giải mã thành công.

Chạy hai tiến trình provider:

```bash
# Terminal A
java -jar inventory-service.jar --server.port=8091

# Terminal B
java -jar inventory-service.jar --server.port=8092
```

Kiểm tra trực tiếp response:

```bash
curl -i http://localhost:8091/api/v1/items/42
curl -i http://localhost:8092/api/v1/items/42
```

Sau đó khởi động `order-service` chứa `ItemProxyController` và `InventoryGateway` từ mục 6–7. Gửi một request chứa cả header được phép lẫn header cố tình không được phép:

```bash
curl -i 'http://localhost:8080/api/proxy/items/42' \
  -H 'Accept-Language: vi' \
  -H 'Authorization: Bearer example-external-token' \
  -H 'Cookie: session=browser-session-example' \
  -H 'X-Tenant-Id: tenant-forged' \
  -H 'X-Forwarded-Host: attacker.example.test' \
  -H 'X-Internal-Debug: enabled' \
  -H 'X-Correlation-Id: caller-chosen-value'
```

Đây là **dữ liệu giả của lab**, không chứa credential thật. Với helper ở mục 6 và không có cơ chế xác thực/tracing bổ sung tự thêm headers, quan sát tại provider dự kiến:

| Header từ inbound | Xuất hiện ở outbound không? | Lý do |
|---|---|---|
| `Accept-Language: vi` | Có | Hợp lệ theo allowlist GET |
| `Authorization: Bearer example-...` | **Không** | Không relay external token |
| `Cookie: session=...` | **Không** | Không relay browser session |
| `X-Tenant-Id: tenant-forged` | **Không** | Tenant do caller tự khai không đáng tin |
| `X-Forwarded-Host: attacker...` | **Không chuyển giá trị giả** | Không relay thông tin proxy từ untrusted client |
| `X-Internal-Debug: enabled` | **Không** | Không nằm trong allowlist |
| `X-Correlation-Id: caller-chosen-value` | **Không giữ nguyên giá trị** | Controller tạo ID mới |
| `Accept: application/json` | Có | Gateway tự đặt theo contract outbound |
| `Host` | Có thể có | **Do HTTP transport tạo**, không lấy từ incoming host |

Trong các hệ thống có service authentication hoặc proxy/tracing filter, **một số header có thể được thêm hợp lệ sau bước allowlist**. Khi đó phải xác minh nguồn giá trị: `Authorization` do authorized client cấp cho đúng audience là tình huống khác hoàn toàn với `Authorization` bị copy từ browser. Đừng viết test production đơn giản “mọi request outbound phải không bao giờ có Authorization”.

### 13.1. Các phép thử đầu vào không hợp lệ

Thử `Accept-Language` không thuộc cú pháp hỗ trợ:

```bash
curl -i 'http://localhost:8080/api/proxy/items/42' \
  -H 'Accept-Language: vi,en;q=0.8'
```

Trong policy lab, giá trị dạng danh sách bị bỏ qua do helper chỉ hỗ trợ một language tag đơn giản; request vẫn có thể thành công vì `Accept-Language` là tùy chọn. Với API cần hỗ trợ header theo HTTP chuẩn, hãy thay helper bằng cơ chế parse/validate được thiết kế cho danh sách và q-values, không copy thẳng chuỗi chưa xử lý.

Thử gửi header lạ:

```bash
curl -i 'http://localhost:8080/api/proxy/items/42' \
  -H 'X-Superuser: true' \
  -H 'X-Internal-Role: admin'
```

Hai header này phải **không được sao chép** sang `inventory-service`. Nếu sau này chúng được thêm vào hệ thống cho tính năng hợp lệ, phải có review bảo mật và policy mới, không tự xuất hiện chỉ vì client bắt đầu gửi chúng.

### 13.2. Quan sát cả hai bản sao

Gửi nhiều request tuần tự qua `order-service` và kiểm tra log ở `inventory-A` và `inventory-B`. Khi danh sách tĩnh có hai instance khỏe và Round Robin hoạt động, cả hai có thể nhận request theo policy lựa chọn đang được cấu hình. Dù chọn instance nào, **allowlist phải cho cùng kết quả an toàn**.

Đây là lý do không nên để interceptor tạo header dựa trên metadata local của một instance hoặc cache state không rõ nguồn: request đến A và B cần tuân thủ cùng **hợp đồng bảo mật**, không chỉ cùng endpoint nghiệp vụ.

## 14. Unit test cho allowlist và integration test trên HTTP thật

### 14.1. Unit test: tên ngoài danh sách không lọt qua

Đặt lớp test trong module client có `spring-boot-starter-test`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

class AllowedHeaderProjectorTest {

    @Test
    void forwardsOnlyApprovedApplicationHeaders() {
        HttpHeaders inbound = new HttpHeaders();
        inbound.set(HttpHeaders.ACCEPT_LANGUAGE, "vi");
        inbound.set("authorization", "Bearer fake-secret");
        inbound.set(HttpHeaders.COOKIE, "session=abc");
        inbound.set("X-Forwarded-Host", "attacker.example.test");
        inbound.set("X-Tenant-Id", "another-tenant");
        inbound.set("X-Internal-Debug", "true");
        inbound.set("X-Correlation-Id", "caller-controlled");

        HttpHeaders result = AllowedHeaderProjector.forItemRead(
                inbound, "trusted-123");

        assertEquals("vi",
                result.getFirst(HttpHeaders.ACCEPT_LANGUAGE));
        assertEquals("application/json",
                result.getFirst(HttpHeaders.ACCEPT));
        assertEquals("trusted-123",
                result.getFirst("X-Correlation-Id"));

        assertNull(result.getFirst(HttpHeaders.AUTHORIZATION));
        assertNull(result.getFirst(HttpHeaders.COOKIE));
        assertNull(result.getFirst("X-Tenant-Id"));
        assertNull(result.getFirst("X-Forwarded-Host"));
        assertNull(result.getFirst("X-Internal-Debug"));
        assertFalse(result.containsKey(HttpHeaders.HOST));

        // Chỉ ba tên header ứng dụng được projector tạo.
        assertEquals(3, result.size());
    }

    @Test
    void ignoresUnsupportedLanguageFormat() {
        HttpHeaders inbound = new HttpHeaders();
        inbound.set(HttpHeaders.ACCEPT_LANGUAGE, "vi,en;q=0.8");

        HttpHeaders result = AllowedHeaderProjector.forItemRead(
                inbound, "trusted-456");

        assertNull(result.getFirst(HttpHeaders.ACCEPT_LANGUAGE));
    }

    @Test
    void rejectsInvalidTrustedCorrelationId() {
        HttpHeaders inbound = new HttpHeaders();
        assertThrows(IllegalArgumentException.class,
                () -> AllowedHeaderProjector.forItemRead(
                        inbound, "bad id with spaces"));
    }
}
```

Đây là unit test của **header projection**, không phải phép kiểm chứng toàn bộ HTTP transport. `HttpHeaders` ở đầu ra không có `Host`, nhưng transport vẫn phải tự tạo `Host` khi gửi HTTP/1.1. Nếu một bộ lọc bảo mật thêm token service đúng audience sau đó, test trên projector không cần biết điều đó.

### 14.2. Integration test phải kiểm tra headers thực sự đến provider

Một integration test đủ mạnh nên có:

1. Một HTTP stub server chạy trên port động.
2. `SimpleDiscoveryClient` của context test trả instance là địa chỉ stub đó.
3. `@LoadBalanced RestClient` hoặc WebClient/Feign client **thật** gửi request theo service ID.
4. Stub server lưu headers đã nhận và trả JSON hợp lệ.
5. Assertion chứng minh `Accept-Language`, correlation ID chuẩn hóa đến nơi, còn inbound `Cookie`, token ngoài, tenant giả và debug headers **không bị relay**.

Ví dụ các assertion quan trọng (pseudocode, không phải API mặc định của Spring):

```text
captured.get("Accept-Language") == "vi"
captured.get("X-Correlation-Id") == trustedId

captured.get("Authorization") != inboundBearerToken
captured.has("Cookie") == false
captured.has("X-Tenant-Id") == false
captured.get("X-Forwarded-Host") != "attacker.example.test"
captured.has("X-Internal-Debug") == false

selectedInstance.serviceId == "inventory-service"
providerReceivedRequest == true
```

Nếu hệ thống chủ động bật proxy header generation hoặc OAuth2 token relay, một số assertion cần được diễn đạt là **“không nhận giá trị giả do inbound client cung cấp”** chứ không phải “header luôn vắng mặt”. Quan trọng là xác thực **nguồn và quyền của giá trị**, không đơn giản tên header có xuất hiện trên wire hay không.

Không sử dụng mock thay thế hoàn toàn network layer rồi tuyên bố đã chứng minh service ID routing/LoadBalancer; mock như vậy chỉ kiểm tra logic trong một lớp, không kiểm tra được interceptor, proxy, transport và HTTP server thực sự nhận headers.

## 15. Kiểm soát các filter, proxy và thư viện thêm header tự động

Allowlist trong một gateway **chưa phải toàn bộ chính sách bảo mật**. Headers outbound có thể được thêm tại các lớp khác:

- Filter/interceptor riêng của RestClient, RestTemplate, WebClient hoặc OpenFeign.
- HTTP authentication component (OAuth2 authorized client, service token provider).
- Tracing instrumentation (OpenTelemetry/Micrometer Tracing).
- API Gateway/ingress, service mesh, reverse proxy hoặc egress proxy.
- HTTP transport tự đặt `Host`, `Content-Length`, connection management headers.

Vì vậy cần xác định thứ tự hình thành request và “**ai là chủ sở hữu của từng header**”:

```mermaid
flowchart LR
    A[Incoming request] --> B[Ingress verify/normalize]
    B --> C[Per-operation allowlist]
    C --> D[Authorized token/context injector]
    D --> E[Tracing instrumentation]
    E --> F[HTTP transport]
    F --> G[LoadBalancer-selected destination]
    G --> H[Network proxy / destination]
```

Sơ đồ trình bày **mô hình khái niệm**; thứ tự filter và LoadBalancer trong HTTP client có thể khác nhau tùy integration. Cần kiểm tra thực tế của stack được dùng, không dựa vào sơ đồ để khẳng định thứ tự thực thi tuyệt đối.

**Quy tắc quan trọng:** nếu một `WebClient` dùng chung được cấu hình interceptor đặt Bearer token cho `billing-service` thì không nên tái sử dụng chính instance đó để gọi `inventory-service` khi hai dịch vụ yêu cầu audience/scopes khác nhau. Token provider nên được chọn theo đích, không theo “token có sẵn từ inbound request”.

### 15.1. Một số kiểm tra phòng thủ bổ sung

| Điểm kiểm soát | Kiểm tra nên thực hiện |
|---|---|
| API Gateway | Loại bỏ/ghi đè các header identity/proxy do Internet tự khai |
| Ingress → service | Xác thực kết nối, phân biệt mạng tin cậy và không tin cậy |
| Service code | Chỉ tạo header theo allowlist **cho từng operation** |
| Auth injector | Token đúng audience/scope, không relay session/browser cookie |
| Tracing | Chỉ truyền context cho phép; giới hạn baggage và không chứa PII |
| HTTP transport | Không can thiệp framing/Host thủ công; timeout và TLS hợp lệ |
| Egress proxy | Kiểm tra routing, header rewrite và hạn chế gửi secrets tới đích ngoài |
| Downstream | Xác thực lại caller, kiểm tra authz/tenant/resource chứ không tin header tên “internal” |

Spring Cloud LoadBalancer được dùng để chọn `ServiceInstance` trong tập discovery; điều đó **không tự đảm bảo đích đáng tin hoặc có TLS hợp lệ**. Khi dùng HTTPS/mTLS, client phải kiểm tra chứng chỉ và policy tương ứng với đích. Metadata của discovery và cấu hình zone/instance không thay thế authentication và authorization.

## 16. Quan sát lỗi header mà không ghi lộ dữ liệu nhạy cảm

Một chính sách allowlist cần được đo và cảnh báo, nhưng **không nên log toàn bộ giá trị header đã bị chặn** vì chính đó có thể là token hoặc cookie nhạy cảm.

Các metric/log gợi ý:

| Tín hiệu | Mục đích |
|---|---|
| `serviceId` / `operation` | Biết policy nào đang được dùng |
| `headerPolicyVersion` | Đối chiếu thay đổi sau deploy |
| `allowedHeaderNames` (giới hạn) | Debug danh sách tên header được phép |
| `droppedHeaderCount` | Phát hiện request có nhiều metadata bị loại |
| `invalidHeaderCategory` | Ví dụ language format sai, correlation ID sai, header identity do ngoài gửi |
| `selectedInstance` | Xác minh lời gọi vẫn qua đúng LoadBalancer |
| `authAudience` / scope category | Xem token outbound có hướng tới đúng service không (không log token) |
| `traceId`, `spanId` | Liên kết lời gọi và sự cố giữa các hop |
| `httpStatus` / `exceptionClass` | Xác định lỗi bị từ chối vì policy hay lỗi ở provider/transport |

Đây là **tên gợi ý cho instrumentation**, không phải tất cả là metric có sẵn của Spring Cloud. Khi đẩy dữ liệu vào hệ thống metric, không dùng full header values, correlation ID, user ID, request URI chứa ID hoặc token làm label có cardinality cao. Nếu cần trace chi tiết, lưu trong hệ thống có retention và quyền truy cập thích hợp.

### Khi phát hiện header không mong muốn ở provider

1. Xác định **header name và nguồn tạo**: inbound user, gateway, app filter, auth component, tracing hay proxy. **Không ghi lại giá trị secret** trong báo cáo vận hành.
2. Kiểm tra request có đi qua **đúng bean `@LoadBalanced`** hay dùng một client khác bỏ qua projector.
3. Kiểm tra có **global interceptor** đang copy `HttpServletRequest`, `ServerHttpRequest` hoặc `RequestContextHolder` không.
4. Xác nhận policy theo **service ID và operation**: có thể một Feign client khác được cấu hình interceptor toàn cục.
5. Đối chiếu raw request tại provider với request đã xuất khỏi HTTP client nếu có hạ tầng proxy ở giữa.
6. Nếu là `Authorization`, xác minh **nguồn token và audience**, không chỉ kiểm tra có/không.
7. Nếu là header proxy, xem proxy tin cậy đã loại/ghi đè giá trị bên ngoài trước khi forward hay chưa.
8. Viết regression test cho header vừa phát hiện để ngăn leak lặp lại.

### Phân biệt lỗi policy với lỗi LoadBalancer

Một request thiếu auth hợp lệ có thể nhận 401/403 từ downstream dù LoadBalancer đã chọn instance chính xác. Ngược lại, sai service ID có thể khiến LoadBalancer không chọn được instance dù allowlist đúng. **Đừng sửa bằng cách forward tất cả headers** khi thấy lỗi 401 hoặc 503: cần xác định tầng tạo lỗi và hợp đồng xác thực của đích.

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| `outgoing.addAll(incoming)` | Rò rỉ mọi header mới/chưa review | Chỉ tạo `HttpHeaders` mới từ allowlist |
| Dùng denylist thiếu `Cookie`/`Authorization` | Lộ session hoặc access token | Allowlist theo operation |
| Sao chép `Host` từ public request | Sai đích logic, lỗi routing/authority | Để HTTP client đặt Host theo URI đích |
| Tin `X-Forwarded-Host`, `X-Real-IP` do Internet gửi | Header spoofing, sai quyết định bảo mật | Gateway tin cậy loại/ghi đè/chuẩn hóa |
| Tin `X-Tenant-Id` để chọn dữ liệu | Cross-tenant access | Xác minh tenant từ principal/security context |
| Chuyển nguyên Bearer token sang mọi service | Audience/scope mismatch, credential exposure | Service token hoặc delegation phù hợp |
| Tự gắn `Content-Length` từ inbound request | Framing sai, HTTP parsing inconsistency | Để HTTP transport tạo |
| Chỉ chặn `Connection`, vẫn copy header do nó liệt kê | Lọt metadata dành cho hop cũ | Không copy-all; tuân thủ HTTP semantics |
| Forward `baggage` có PII | Lan truyền dữ liệu nhạy cảm vào trace | Giới hạn baggage theo schema được duyệt |
| Retry POST với idempotency key mới mỗi lần | Tạo side effect trùng | Key ổn định theo logical operation |
| Copy response `Set-Cookie` của service nội bộ | Lộ cookie, tạo session sai domain | Response allowlist riêng |
| Copy `Cache-Control: public` cho dữ liệu tenant | Cache sai phạm vi | Policy cache tại API boundary |
| Test chỉ kiểm tra projector, không kiểm tra wire | Bỏ sót interceptor/proxy thêm header | Integration test tới server thật |
| Bật filter global copy `RequestContextHolder` | Lẫn context hoặc leak sang service khác | Per-client policy và context tin cậy tường minh |

## 18. Checklist trước khi triển khai

- [ ] Xác định trust boundary từ client ngoài → gateway → service A → service B.
- [ ] Có **allowlist riêng theo service/operation**, không copy inbound headers toàn bộ.
- [ ] Mỗi tên được phép có lý do nghiệp vụ, format, độ dài, cardinality và policy nguồn gốc.
- [ ] Không relay `Authorization`/`Cookie` từ public client nếu không có delegation được thiết kế rõ.
- [ ] Identity/tenant/role chỉ được tạo từ context **đã xác thực**, downstream vẫn enforce authz.
- [ ] HTTP transport quản lý `Host`, framing và connection headers; không chép từ inbound.
- [ ] Các giá trị `Forwarded`/`X-Forwarded-*` chỉ được tin sau proxy được cấu hình đúng.
- [ ] Tracing propagation được instrumentation quản lý; baggage không chứa dữ liệu nhạy cảm.
- [ ] `Idempotency-Key` chỉ được gửi với operation phù hợp, ổn định giữa retries và gắn với tenant/operation ở server.
- [ ] Request headers và response headers có **hai chính sách allowlist riêng**.
- [ ] Kiểm tra interceptor/filter global và token provider không ghi đè chính sách.
- [ ] Có unit test header projection và integration test trên HTTP request thực tới provider.
- [ ] Test với tên header khác hoa/thường, duplicate values, giá trị quá dài hoặc sai định dạng.
- [ ] Khi chạy qua LoadBalancer nhiều instance, mọi bản sao nhận đúng contract headers đã được duyệt.
- [ ] Metric/log không chứa token, cookie, PII hoặc raw baggage; có đủ trace để phân biệt lỗi auth, selection và transport.

## 19. Tổng kết

**Chỉ chuyển tiếp những header được cho phép** nghĩa là **chủ động dựng một outbound request mới**, dựa trên hợp đồng của dịch vụ đích, chứ không mang nguyên trạng request đầu vào qua nhiều microservice. `Accept-Language` có thể được forward sau chuẩn hóa, `X-Correlation-Id` có thể được tạo ở trust boundary, và `Idempotency-Key` có thể cần cho một operation ghi; nhưng token, cookie, tenant tự khai, proxy headers và các header điều khiển kết nối phải có chính sách riêng hoặc không được relay.

Trong Spring Cloud LoadBalancer, **chọn `ServiceInstance` và bảo mật header là hai trách nhiệm độc lập**. Dù LoadBalancer chọn instance A hay B, outbound policy phải cho kết quả nhất quán. Khi kết hợp allowlist theo operation, token đúng audience, tracing an toàn, kiểm thử raw request tại provider và quan sát nguồn header, hệ thống sẽ giảm nguy cơ rò rỉ thông tin và tránh để dữ liệu không tin cậy ảnh hưởng đến quyền truy cập hoặc routing nội bộ.

### Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): định nghĩa các trường HTTP, `Connection` và xử lý field ở intermediary.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): framing, `Host` và các yêu cầu về xử lý HTTP/1.1.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): `RestClient`, `RestTemplate` và `WebClient`.
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service IDs, `ServiceInstance` và tích hợp HTTP client.
- [Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): `@FeignClient`, request interceptors và cấu hình client.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context và baggage.
