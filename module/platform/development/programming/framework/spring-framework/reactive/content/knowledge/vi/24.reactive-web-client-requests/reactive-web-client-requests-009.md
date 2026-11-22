# Request attributes và truyền dữ liệu qua Reactor Context trong Spring WebFlux WebClient

## 1. Mục tiêu

Khi gọi dịch vụ HTTP bằng `WebClient`, ứng dụng thường cần chuyển thêm metadata đi cùng request: correlation ID để truy vết, mã tenant, tên thao tác, thông tin tracing hoặc dữ liệu phục vụ filter. Một số metadata chỉ cần cho **một request outgoing**; một số khác cần đi theo cả chuỗi reactive, kể cả các request lồng nhau được gọi trong `flatMap` hoặc `concatMap`.

Spring WebFlux cung cấp hai cơ chế khác nhau:

- **Request attributes của WebClient:** lưu metadata trên một `ClientRequest` cụ thể. Filter có thể đọc attribute để quyết định cách xử lý request đó.
- **Reactor Context:** lưu metadata theo subscriber/reactive sequence. Các operator và những request WebClient được compose trong cùng reactive chain có thể đọc cùng Context.

Điểm cần nhớ là attributes và Reactor Context đều là metadata nội bộ của ứng dụng. Chúng **không tự động được gửi qua HTTP**. Nếu dịch vụ đích cần nhận giá trị, filter phải chuyển nó thành header, query parameter, cookie hoặc một phần của request body theo API contract.

Bài học tập trung vào:

- Gắn attribute vào một request bằng `attribute(...)` hoặc `attributes(...)`.
- Đọc attribute trong `ExchangeFilterFunction` qua `ClientRequest.attribute(...)`.
- Dùng `defaultRequest(...)` để thêm metadata mặc định cho mỗi request.
- Ghi dữ liệu vào Reactor Context bằng `contextWrite(...)`.
- Đọc Context trong filter bằng `Mono.deferContextual(...)`.
- Truyền correlation ID hoặc metadata tới các WebClient call lồng nhau.
- Hiểu vị trí của `contextWrite`, tính bất biến và giới hạn propagation.
- Tránh phụ thuộc ThreadLocal hoặc tự `subscribe()` trong reactive flow.
- Kiểm thử cả request attributes và Reactor Context bằng StepVerifier.

Các API chính trong bài có từ các phiên bản Spring Framework 5.x và vẫn dùng được trên Spring Framework 6.2/7.0. Ví dụ dùng Java 17+, Spring Boot 3.x/4.x tương thích và Reactor.

## 2. Phân biệt request attribute, Reactor Context và HTTP header

Ba khái niệm có thể mang cùng một giá trị nhưng có phạm vi và cách truyền khác nhau:

| Cơ chế | Phạm vi | Ai đọc được? | Có tự gửi qua mạng? |
| --- | --- | --- | --- |
| WebClient request attribute | Một ClientRequest outgoing | Filter của request đó và thành phần xử lý ClientRequest | Không |
| Reactor Context | Một subscriber/reactive chain | Reactor operators, WebClient filter và thư viện tích hợp Context | Không |
| HTTP header | Một HTTP request thực tế | Server nhận request và các proxy trung gian | Có |

Ví dụ muốn gửi correlation ID `req-42`:

- Attribute `operation=read-order` có thể chỉ giúp filter ghi header phù hợp cho request hiện tại.
- Reactor Context có thể giữ `correlationId=req-42` xuyên suốt một chuỗi gồm nhiều WebClient request.
- Header `X-Correlation-Id: req-42` là dữ liệu thực sự được gửi tới dịch vụ HTTP bên kia.

Có thể hình dung:

```text
Reactive request chain
        |
        | contextWrite(correlationId = req-42)
        v
  Reactor Context
        |
        +---- WebClient call A
        |         |
        |         +-- request attribute: operation = read-order
        |         |
        |         +-- ExchangeFilterFunction đọc attribute
        |         +-- ExchangeFilterFunction đọc Context
        |         +-- tạo HTTP header
        |
        +---- flatMap(...)
                  |
                  +---- WebClient call B
                            |
                            +-- đọc lại correlationId từ Context
                            +-- tạo HTTP header
```

Request attribute của call A không tự xuất hiện ở call B. Reactor Context có thể được call B đọc nếu call B được compose trong cùng reactive chain.

## 3. Request attributes trong WebClient

### 3.1. Thêm attribute cho một request

WebClient cung cấp `attribute(String name, Object value)` trên request specification:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attribute("operation", "read-order")
        .retrieve()
        .bodyToMono(String.class);
```

Attribute được gắn vào request đang được xây dựng. Giá trị có thể là String, enum, một record nhỏ hoặc object nội bộ khác. Nên ưu tiên metadata nhỏ, bất biến và có kiểu rõ ràng.

Có thể gắn nhiều attribute:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attribute("operation", "read-order")
        .attribute("tenantId", tenantId)
        .attribute("requestTag", "orders-screen")
        .retrieve()
        .bodyToMono(String.class);
```

Hoặc thêm qua một Consumer của map:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attributes(attributes -> {
            attributes.put("operation", "read-order");
            attributes.put("requestTag", "orders-screen");
        })
        .retrieve()
        .bodyToMono(String.class);
```

Hai cách trên có cùng mục đích. Dùng `attribute(...)` khi thêm một giá trị đơn lẻ; dùng `attributes(...)` khi muốn thêm một nhóm giá trị.

### 3.2. Đọc attribute trong ExchangeFilterFunction

Filter có thể đọc attribute từ `ClientRequest.attribute(name)`. Giá trị trả về là `Optional<Object>`:

```java
WebClient client = WebClient.builder()
        .filter((request, next) -> {
            Optional<Object> operation =
                    request.attribute("operation");

            operation.ifPresent(value ->
                    System.out.println("operation=" + value));

            return next.exchange(request);
        })
        .build();
```

Đây là ví dụ minh họa log. Trong production, không log dữ liệu nhạy cảm hoặc giá trị attribute tùy ý.

Nếu filter cần thay đổi HTTP request, tạo một request mới bằng `ClientRequest.from(request)`:

```java
ExchangeFilterFunction operationHeaderFilter =
        (request, next) -> {
            ClientRequest.Builder builder =
                    ClientRequest.from(request);

            request.attribute("operation").ifPresent(value ->
                    builder.headers(headers ->
                            headers.set(
                                    "X-Client-Operation",
                                    value.toString())));

            return next.exchange(builder.build());
        };
```

Trong ví dụ này:

1. Filter đọc attribute `operation` từ request hiện tại.
2. Nếu có giá trị, filter thêm header `X-Client-Operation`.
3. Filter tạo ClientRequest mới và gọi `next.exchange(...)`.
4. Dịch vụ đích chỉ nhìn thấy header HTTP; nó không nhìn thấy map attribute nội bộ.

Không tự sửa một ClientRequest đã được build. ClientRequest là immutable; dùng builder từ `ClientRequest.from(request)` để tạo bản thay thế.

### 3.3. Attribute không phải header

Nếu viết:

```java
webClient.get()
        .uri("/orders/42")
        .attribute("tenantId", "tenant-17")
        .retrieve()
        .bodyToMono(String.class);
```

thì request không tự có header `tenantId: tenant-17`. Attribute chỉ nằm trong metadata nội bộ của ClientRequest.

Muốn gửi giá trị đó qua HTTP, phải map nó sang một thành phần request rõ ràng:

```java
ExchangeFilterFunction tenantHeaderFilter =
        (request, next) -> {
            ClientRequest.Builder builder =
                    ClientRequest.from(request);

            request.attribute("tenantId").ifPresent(value ->
                    builder.headers(headers ->
                            headers.set(
                                    "X-Tenant-Id",
                                    value.toString())));

            return next.exchange(builder.build());
        };
```

Chỉ làm vậy nếu dịch vụ đích có contract nhận header này. Không lấy tenant ID tùy ý từ client rồi chuyển tiếp mà không xác thực quyền truy cập tenant.

### 3.4. Attribute chỉ ảnh hưởng request hiện tại

Giả sử một service thực hiện hai request:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attribute("operation", "read-order")
        .retrieve()
        .bodyToMono(String.class)
        .flatMap(order -> webClient.get()
                .uri("/orders/42/audit")
                .retrieve()
                .bodyToMono(String.class));
```

Request đầu có attribute `operation=read-order`. Request thứ hai là một ClientRequest mới; attribute đó không tự động được sao chép sang request thứ hai.

Nếu cả hai request cần cùng metadata, có thể gắn attribute vào từng request, dùng `defaultRequest(...)` cho metadata mặc định, hoặc dùng Reactor Context nếu dữ liệu cần truyền theo cả reactive chain.

### 3.5. defaultRequest để thêm attribute mặc định

WebClient.Builder có callback `defaultRequest(...)` để tùy chỉnh mỗi request được tạo:

```java
WebClient client = WebClient.builder()
        .defaultRequest(spec ->
                spec.attribute("clientName", "orders-service"))
        .filter((request, next) -> {
            String clientName = request.attribute("clientName")
                    .map(Object::toString)
                    .orElse("unknown");

            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Client-Name", clientName)
                    .build();

            return next.exchange(updated);
        })
        .build();
```

Cách này phù hợp cho metadata tĩnh hoặc mặc định của client, ví dụ tên service, loại client hoặc nhóm API. Nó không thay thế Reactor Context cho dữ liệu thay đổi theo từng subscriber/request chain.

## 4. ExchangeFilterFunction và vòng đời filter

### 4.1. Filter là điểm xử lý xuyên suốt request

`ExchangeFilterFunction` cho phép can thiệp trước và sau khi WebClient gửi request:

```java
ExchangeFilterFunction filter =
        (request, next) -> {
            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Client-Name", "orders-service")
                    .build();

            return next.exchange(updated);
        };
```

Filter phù hợp cho:

- Thêm correlation ID vào request.
- Thêm header client/service metadata.
- Gắn authentication header theo cơ chế phù hợp.
- Ghi log request metadata đã được làm sạch.
- Đo thời gian request.
- Xử lý retry/refresh token theo contract rõ ràng.

Filter được đăng ký bằng `WebClient.Builder.filter(...)`. Nhiều filter tạo thành một chain. Thứ tự đăng ký ảnh hưởng thứ tự request đi qua các filter.

### 4.2. Giữ lại response body khi filter can thiệp

Filter thường trả kết quả của `next.exchange(...)` để WebClient tiếp tục decode response. Nếu filter tự đọc response body để kiểm tra status hoặc retry, phải tiêu thụ body hoặc chuyển tiếp body cho thành phần tiếp theo.

Ví dụ, khi gặp 401 và muốn retry sau khi refresh token, cần giải phóng body của response đầu trước khi gửi lại:

```java
return next.exchange(request)
        .flatMap(response -> {
            if (response.statusCode().value() == 401) {
                return response.releaseBody()
                        .then(refreshToken())
                        .flatMap(token -> {
                            ClientRequest retryRequest =
                                    ClientRequest.from(request)
                                            .headers(headers ->
                                                    headers.setBearerAuth(token))
                                            .build();

                            return next.exchange(retryRequest);
                        });
            }

            return Mono.just(response);
        });
```

Đây là mã khung minh họa; `refreshToken()` phải trả publisher và xử lý token an toàn. Không bỏ response body mà không release/consume, vì có thể giữ tài nguyên kết nối hoặc buffer.

### 4.3. Filter không nên tự subscribe

Sai:

```java
.filter((request, next) -> {
    next.exchange(request).subscribe();
    return Mono.empty();
})
```

Cách trên tạo subscription riêng và làm mất response của request đang được WebClient quản lý. Lỗi, cancellation và body lifecycle có thể không còn gắn với caller.

Đúng:

```java
.filter((request, next) ->
        next.exchange(request))
```

Hoặc compose các thao tác trước/sau exchange bằng `flatMap`, `map` và các operator Reactor khác rồi trả publisher cho WebClient.

## 5. Reactor Context là gì?

Reactor Context là một cấu trúc key-value gắn với **Subscriber** của một reactive sequence. Nó được thiết kế để truyền metadata xuyên suốt chuỗi operator mà không phụ thuộc thread hiện tại.

Các đặc điểm chính:

- Context gắn với subscriber và được truy cập trong quá trình subscribe.
- Context immutable: `put(...)` tạo một Context mới thay vì sửa object hiện tại.
- Dữ liệu Context được truyền từ downstream về upstream qua subscription.
- Reactor-native operators có thể đọc Context bằng `deferContextual(...)` hoặc `transformDeferredContextual(...)`.
- WebClient filter có thể đọc Context để thêm metadata vào request.
- Các WebClient call lồng nhau trong cùng reactive chain có thể nhận cùng Context.
- Context không tự biến thành HTTP header và không tự truyền qua một subscription độc lập.

Ví dụ đơn giản:

```java
private static final String USER_KEY = "currentUser";

Mono<String> greeting = Mono.deferContextual(context ->
        Mono.just("Hello " + context.get(USER_KEY)));

Mono<String> result = greeting.contextWrite(context ->
        context.put(USER_KEY, "An"));
```

Khi subscribe, kết quả là:

```text
Hello An
```

`contextWrite(...)` gắn Context cho subscription. `deferContextual(...)` đọc giá trị khi publisher được subscribe, vì Context chỉ có sẵn trong subscription lifecycle.

### 5.1. Context không phải một Map có thể sửa trực tiếp

Ví dụ:

```java
Context updated = Context.empty()
        .put("correlationId", "req-42");
```

`put(...)` trả về Context mới. Phải dùng Context được trả về:

```java
.contextWrite(context -> context.put("correlationId", "req-42"))
```

Không mong đợi việc gọi `context.put(...)` thay đổi Context cũ. Cũng không nên lưu object mutable rồi sửa nội dung object đó trong lúc nhiều operator cùng đọc; ưu tiên record/value object immutable.

### 5.2. Đọc Context bằng deferContextual

`Mono.deferContextual` tạo publisher dựa trên Context có tại thời điểm subscribe:

```java
Mono<String> correlationId = Mono.deferContextual(context ->
        Mono.just(context.getOrDefault(
                "correlationId", "not-provided")));
```

Nếu key không có, ví dụ trả `not-provided`. Nếu cần phân biệt key thiếu và giá trị mặc định, dùng `hasKey(...)` hoặc `getOrEmpty(...)`.

Trong filter WebClient, cách đọc này giúp filter nhận metadata từ chain gọi WebClient mà không cần truyền tham số qua từng method.

## 6. Ghi dữ liệu vào Context bằng contextWrite

### 6.1. Đặt contextWrite ở cuối reactive chain

Ví dụ:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .retrieve()
        .bodyToMono(String.class)
        .flatMap(order -> webClient.get()
                .uri("/orders/42/audit")
                .retrieve()
                .bodyToMono(String.class)
                .map(audit -> order + " | " + audit))
        .contextWrite(context ->
                context.put("correlationId", "req-42"));
```

Context được gắn ở cuối chain để các operator và WebClient call ở phía upstream có thể đọc được.

Quy tắc dễ nhớ: **subscription và Context đi từ cuối chain về đầu chain**. Vì vậy vị trí của `contextWrite` ảnh hưởng operator nào có thể nhìn thấy giá trị.

### 6.2. Vị trí sai thường gặp

Ví dụ dưới đây ghi Context quá sớm trong chain:

```java
Mono<String> wrong = Mono.just("start")
        .contextWrite(context ->
                context.put("correlationId", "req-42"))
        .flatMap(value ->
                Mono.deferContextual(context ->
                        Mono.just(context.getOrDefault(
                                "correlationId", "missing"))));
```

Kết quả là:

```text
missing
```

Lý do: `contextWrite` nằm phía trên operator `flatMap` trong chuỗi, nên Context của nó không được truyền xuống subscriber của flatMap để operator này đọc.

Cách đúng:

```java
Mono<String> correct = Mono.just("start")
        .flatMap(value ->
                Mono.deferContextual(context ->
                        Mono.just(context.getOrDefault(
                                "correlationId", "missing"))))
        .contextWrite(context ->
                context.put("correlationId", "req-42"));
```

Kết quả:

```text
req-42
```

Khi đọc Context trong một nested publisher, hãy kiểm tra operator nào tạo subscription và vị trí contextWrite của sequence đó. Đừng chỉ nhìn thứ tự dòng code rồi giả định Context hoạt động như biến local.

### 6.3. Nhiều contextWrite cùng key

Nếu cùng một key được ghi nhiều lần, giá trị mà operator nhìn thấy phụ thuộc vị trí các lần ghi trong chain. Context immutable và mỗi contextWrite tạo một Context mới cho phần upstream.

Ví dụ:

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("message")))
    .contextWrite(context -> context.put("message", "Reactor"))
    .contextWrite(context -> context.put("message", "World"));
```

Operator deferContextual thấy giá trị `Reactor` vì đó là giá trị được ghi gần nó hơn theo chiều propagation. Tránh ghi cùng một key ở nhiều tầng nếu không có lý do rõ ràng; hãy đặt một điểm sở hữu metadata để code dễ hiểu.

## 7. Dùng Reactor Context trong WebClient filter

### 7.1. Đọc Context rồi chuyển thành HTTP header

Một filter có thể đọc correlation ID từ Reactor Context:

```java
private static final Object CORRELATION_ID =
        CorrelationContext.class;

ExchangeFilterFunction correlationFilter =
        (request, next) ->
                Mono.deferContextual(contextView -> {
                    ClientRequest.Builder builder =
                            ClientRequest.from(request);

                    if (contextView.hasKey(CORRELATION_ID)) {
                        String correlationId =
                                contextView.get(CORRELATION_ID);

                        builder.headers(headers ->
                                headers.set(
                                        "X-Correlation-Id",
                                        correlationId));
                    }

                    return next.exchange(builder.build());
                });
```

Trong ví dụ:

- Context key là một object/class key duy nhất, tránh va chạm với tên key của thư viện khác.
- `Mono.deferContextual(...)` chỉ đọc Context khi request thực thi.
- Filter tạo ClientRequest mới và thêm header.
- Giá trị chỉ được gửi qua HTTP sau khi filter map nó vào header.

Tên header phải theo contract giữa các service. Nếu gateway hoặc dịch vụ đích dùng tên khác, thống nhất trước khi triển khai.

### 7.2. Tại sao cần deferContextual?

Nếu filter cố đọc Context trực tiếp lúc khởi tạo WebClient hoặc lúc cấu hình bean, nó không có Context của từng subscription. Context chỉ được gắn khi reactive chain subscribe.

`Mono.deferContextual(...)` trì hoãn việc đọc tới thời điểm đó, vì vậy cùng một WebClient có thể phục vụ nhiều request đồng thời mà mỗi request nhận correlation ID riêng.

Không lưu correlation ID của request trước vào field mutable của singleton WebClient/filter. Một filter có thể phục vụ đồng thời nhiều request; state dùng chung sẽ gây rò metadata giữa các request.

## 8. Attributes và Context trong cùng một WebClient

Hai cơ chế có thể dùng đồng thời. Attribute phù hợp cho một hành động riêng trên request hiện tại; Context phù hợp cho metadata xuyên suốt chain.

Ví dụ filter xử lý cả hai:

```java
private static final String OPERATION = "operation";
private static final Object CORRELATION_ID = RequestContextKeys.class;

ExchangeFilterFunction metadataFilter =
        (request, next) ->
                Mono.deferContextual(contextView -> {
                    ClientRequest.Builder builder =
                            ClientRequest.from(request);

                    request.attribute(OPERATION).ifPresent(value ->
                            builder.headers(headers ->
                                    headers.set(
                                            "X-Client-Operation",
                                            value.toString())));

                    if (contextView.hasKey(CORRELATION_ID)) {
                        String id = contextView.get(CORRELATION_ID);

                        builder.headers(headers ->
                                headers.set("X-Correlation-Id", id));
                    }

                    return next.exchange(builder.build());
                });
```

Khi gọi:

```java
Mono<String> result = webClient.get()
        .uri("/orders/42")
        .attribute(OPERATION, "read-order")
        .retrieve()
        .bodyToMono(String.class)
        .contextWrite(context ->
                context.put(CORRELATION_ID, "req-42"));
```

Filter tạo hai header:

```http
X-Client-Operation: read-order
X-Correlation-Id: req-42
```

Header đầu đến từ request attribute. Header thứ hai đến từ Reactor Context.

Nếu request tiếp theo được tạo trong `flatMap`, nó vẫn đọc được correlation ID từ Context. Attribute operation chỉ có ở request được gắn attribute; request kế tiếp cần tự thêm attribute nếu cũng cần operation header.

## 9. Ví dụ Spring Boot WebFlux hoàn chỉnh

Ví dụ dùng Java 17+, Spring Boot 3.x hoặc 4.x tương thích và WebFlux. Một service gọi dịch vụ đối tác hai lần: đọc order rồi đọc audit. Correlation ID được truyền qua Reactor Context để cả hai request có cùng ID; operation attribute chỉ được gắn vào request đọc order.

### 9.1. Dependencies

Tệp `build.gradle` cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Dự án cần Spring Boot Gradle plugin và dependency management tương thích. Dùng BOM của Boot để quản lý Spring Framework và Reactor; không override riêng reactor-core hoặc spring-webflux.

### 9.2. Context key

Tệp `src/main/java/demo/RequestContextKeys.java`:

```java
package demo;

public final class RequestContextKeys {

    public static final Object CORRELATION_ID =
            RequestContextKeys.class;

    private RequestContextKeys() {
    }
}
```

Dùng Class object làm key để giảm nguy cơ trùng tên với key của thư viện khác. Key phải được dùng thống nhất ở service và filter.

### 9.3. WebClient configuration

Tệp `src/main/java/demo/PartnerWebClientConfiguration.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class PartnerWebClientConfiguration {

    public static final String OPERATION_ATTRIBUTE = "operation";

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example")
                .filter((request, next) ->
                        Mono.deferContextual(contextView -> {
                            ClientRequest.Builder updated =
                                    ClientRequest.from(request);

                            request.attribute(OPERATION_ATTRIBUTE)
                                    .ifPresent(value ->
                                            updated.headers(headers ->
                                                    headers.set(
                                                            "X-Client-Operation",
                                                            value.toString())));

                            if (contextView.hasKey(
                                    RequestContextKeys.CORRELATION_ID)) {

                                String correlationId =
                                        contextView.get(
                                                RequestContextKeys.CORRELATION_ID);

                                updated.headers(headers ->
                                        headers.set(
                                                "X-Correlation-Id",
                                                correlationId));
                            }

                            return next.exchange(updated.build());
                        }))
                .build();
    }
}
```

Spring Boot cung cấp WebClient.Builder đã được auto-configure khi có starter WebFlux. Nếu dùng Spring Framework thuần, có thể thay tham số builder bằng `WebClient.builder()`.

Filter chỉ thêm header khi có dữ liệu tương ứng. Nó không ghi correlation ID vào field của bean, vì bean WebClient là singleton và được dùng đồng thời.

### 9.4. Service gọi hai request lồng nhau

Tệp `src/main/java/demo/PartnerOrderService.java`:

```java
package demo;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

import static demo.PartnerWebClientConfiguration.OPERATION_ATTRIBUTE;
import static demo.RequestContextKeys.CORRELATION_ID;

@Service
public class PartnerOrderService {

    private final WebClient partnerWebClient;

    public PartnerOrderService(WebClient partnerWebClient) {
        this.partnerWebClient = partnerWebClient;
    }

    public Mono<OrderView> findOrder(
            String orderId,
            String correlationId) {

        return partnerWebClient.get()
                .uri("/orders/{id}", orderId)
                .attribute(OPERATION_ATTRIBUTE, "read-order")
                .retrieve()
                .bodyToMono(PartnerOrder.class)
                .flatMap(order ->
                        partnerWebClient.get()
                                .uri("/orders/{id}/audit", orderId)
                                .retrieve()
                                .bodyToMono(PartnerAudit.class)
                                .map(audit -> new OrderView(
                                        order.id(),
                                        order.status(),
                                        audit.lastAction())))
                .contextWrite(context ->
                        context.put(CORRELATION_ID, correlationId));
    }

    public record PartnerOrder(String id, String status) {
    }

    public record PartnerAudit(String lastAction) {
    }

    public record OrderView(
            String id,
            String status,
            String lastAction) {
    }
}
```

Request đầu có cả operation attribute và correlation Context. Request thứ hai được tạo trong flatMap: nó không có operation attribute của request đầu, nhưng vẫn có correlation ID trong Context vì publisher được compose trong cùng reactive chain.

Nếu muốn request audit cũng có operation metadata, thêm:

```java
.attribute(OPERATION_ATTRIBUTE, "read-order-audit")
```

vào request thứ hai.

### 9.5. Controller nhận correlation ID

Tệp `src/main/java/demo/PartnerOrderController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class PartnerOrderController {

    private final PartnerOrderService service;

    public PartnerOrderController(PartnerOrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<PartnerOrderService.OrderView> find(
            @PathVariable String id,
            @RequestHeader("X-Correlation-Id") String correlationId) {

        return service.findOrder(id, correlationId);
    }
}
```

Đây là ví dụ minh họa đầu vào. Trong production, correlation ID nên được sinh hoặc kiểm tra ở một filter/gateway đáng tin cậy; không dùng correlation ID để xác thực user hoặc cấp quyền.

## 10. Kiểm thử attributes và Context bằng StepVerifier

Có thể kiểm thử filter mà không gọi mạng thật bằng cách cung cấp một `ExchangeFunction` giả. Test ghi lại ClientRequest mà filter chuyển xuống exchange function.

Tệp `src/test/java/demo/WebClientMetadataTest.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static demo.PartnerWebClientConfiguration.OPERATION_ATTRIBUTE;
import static demo.RequestContextKeys.CORRELATION_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class WebClientMetadataTest {

    @Test
    void requestAttributeAppliesOnlyToTheRequestThatCarriesIt() {
        List<ClientRequest> captured = new ArrayList<>();
        WebClient client = createClient(captured);

        Mono<String> result = client.get()
                .uri("https://example.test/first")
                .attribute(OPERATION_ATTRIBUTE, "read-order")
                .retrieve()
                .bodyToMono(String.class)
                .flatMap(first -> client.get()
                        .uri("https://example.test/second")
                        .retrieve()
                        .bodyToMono(String.class)
                        .map(second -> first + second));

        StepVerifier.create(result)
                .expectNext("/first/second")
                .verifyComplete();

        assertEquals(2, captured.size());
        assertEquals(
                "read-order",
                captured.get(0).headers()
                        .getFirst("X-Client-Operation"));
        assertNull(captured.get(1).headers()
                .getFirst("X-Client-Operation"));
    }

    @Test
    void reactorContextPropagatesToNestedWebClientRequests() {
        List<ClientRequest> captured = new ArrayList<>();
        WebClient client = createClient(captured);

        Mono<String> result = client.get()
                .uri("https://example.test/first")
                .retrieve()
                .bodyToMono(String.class)
                .flatMap(first -> client.get()
                        .uri("https://example.test/second")
                        .retrieve()
                        .bodyToMono(String.class)
                        .map(second -> first + second))
                .contextWrite(context ->
                        context.put(CORRELATION_ID, "req-42"));

        StepVerifier.create(result)
                .expectNext("/first/second")
                .verifyComplete();

        assertEquals(2, captured.size());

        assertEquals(
                "req-42",
                captured.get(0).headers()
                        .getFirst("X-Correlation-Id"));

        assertEquals(
                "req-42",
                captured.get(1).headers()
                        .getFirst("X-Correlation-Id"));
    }

    @Test
    void contextWriteMustBeDownstreamOfTheOperatorThatReadsIt() {
        Mono<String> wrong = Mono.just("start")
                .contextWrite(context ->
                        context.put(CORRELATION_ID, "req-42"))
                .flatMap(value ->
                        Mono.deferContextual(context ->
                                Mono.just(context.getOrDefault(
                                        CORRELATION_ID, "missing"))));

        StepVerifier.create(wrong)
                .expectNext("missing")
                .verifyComplete();

        Mono<String> correct = Mono.just("start")
                .flatMap(value ->
                        Mono.deferContextual(context ->
                                Mono.just(context.getOrDefault(
                                        CORRELATION_ID, "missing"))))
                .contextWrite(context ->
                        context.put(CORRELATION_ID, "req-42"));

        StepVerifier.create(correct)
                .expectNext("req-42")
                .verifyComplete();
    }

    private WebClient createClient(List<ClientRequest> captured) {
        ExchangeFunction exchange = request -> {
            captured.add(request);

            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(
                            HttpHeaders.CONTENT_TYPE,
                            MediaType.TEXT_PLAIN_VALUE)
                    .body(request.url().getPath())
                    .build());
        };

        return WebClient.builder()
                .filter((request, next) ->
                        Mono.deferContextual(contextView -> {
                            ClientRequest.Builder updated =
                                    ClientRequest.from(request);

                            request.attribute(OPERATION_ATTRIBUTE)
                                    .ifPresent(value ->
                                            updated.headers(headers ->
                                                    headers.set(
                                                            "X-Client-Operation",
                                                            value.toString())));

                            if (contextView.hasKey(CORRELATION_ID)) {
                                String id = contextView.get(CORRELATION_ID);

                                updated.headers(headers ->
                                        headers.set("X-Correlation-Id", id));
                            }

                            return next.exchange(updated.build());
                        }))
                .exchangeFunction(exchange)
                .build();
    }
}
```

Các test xác nhận:

- Attribute được chuyển thành header trên request có gắn attribute.
- Request lồng nhau không tự nhận attribute của request trước.
- Reactor Context được nhìn thấy ở cả hai WebClient request trong cùng chain.
- Đặt contextWrite sai vị trí làm operator không đọc được key; đặt ở cuối chain cho kết quả đúng.

Chạy test:

```bash
./gradlew test
```

Test dùng ExchangeFunction giả nên không cần dịch vụ HTTP bên ngoài. Nếu muốn kiểm thử integration qua server thật, có thể dùng WireMock, MockWebServer hoặc một endpoint test riêng và tiếp tục kiểm tra header nhận được.

## 11. Reactor Context, ThreadLocal và MDC

### 11.1. Vì sao ThreadLocal không phù hợp làm nguồn metadata reactive?

Trong mô hình imperative, một request thường được xử lý trên một thread; ThreadLocal có thể giữ request ID trên thread đó. Trong reactive pipeline, một request có thể tiếp tục trên thread khác sau `publishOn`, `subscribeOn` hoặc khi I/O hoàn tất.

Vì vậy, không nên giả định:

```java
ThreadLocal<String> correlationId = new ThreadLocal<>();
```

sẽ giữ đúng request ID xuyên suốt WebFlux pipeline. Nhiều request có thể dùng chung event-loop thread; dữ liệu ThreadLocal có nguy cơ bị thiếu hoặc trộn nếu tự quản lý không đúng.

Reactor Context gắn với subscriber thay vì thread, nên phù hợp hơn cho metadata request-scoped trong reactive flow.

### 11.2. Kết hợp với Micrometer Context Propagation

Nếu phải tích hợp thư viện cũ sử dụng ThreadLocal hoặc MDC, có thể dùng `io.micrometer:context-propagation` và các accessor tương ứng để bridge giữa Context và ThreadLocal.

Reactor hỗ trợ SPI này từ phiên bản 3.5. Tùy cấu hình, có chế độ propagation mặc định giới hạn hoặc automatic mode thông qua hook. Chỉ bật automatic propagation sau khi hiểu ảnh hưởng tới toàn bộ ứng dụng và các thư viện dùng ThreadLocal.

Không cần thêm Context Propagation chỉ để đọc Reactor Context trong WebClient filter; `deferContextual(...)` đã giải quyết trực tiếp nhu cầu đó.

### 11.3. Spring Security dùng reactive context

Spring Security reactive lưu SecurityContext theo cơ chế reactive context và cung cấp `ReactiveSecurityContextHolder` để truy cập. Khi cần danh tính/authority, ưu tiên API Spring Security thay vì tự đặt user role vào một attribute rồi coi đó là bằng chứng xác thực.

Reactor Context là cơ chế truyền metadata; nó không tự xác thực người dùng, không mã hóa dữ liệu và không thay thế authorization.

## 12. Các giới hạn và nguyên tắc bảo mật

### 12.1. Không để metadata nội bộ bị gửi nhầm ra ngoài

Một attribute có thể chứa object phức tạp, ID nội bộ hoặc thông tin nhạy cảm. Nó chỉ nên được map ra HTTP nếu contract cho phép. Không tạo một filter tự động chuyển tất cả attributes thành headers; cách đó dễ làm lộ metadata nội bộ hoặc gửi các giá trị không hợp lệ.

Chỉ map key được allowlist:

```java
request.attribute("correlationId").ifPresent(value ->
        headers.set("X-Correlation-Id", value.toString()));
```

Không lặp lại nguyên map attributes thành header name/value.

### 12.2. Không dùng tenant ID chưa xác thực

Nếu Context chứa tenant ID, giá trị nên đến từ authentication/authorization layer đáng tin cậy hoặc được xác thực trước khi gọi service. Không tin một tenant ID do browser gửi lên rồi truyền sang service đối tác để quyết định dữ liệu được truy cập.

### 12.3. Không lưu object lớn hoặc mutable trong Context

Context được truyền theo subscription và có thể được đọc từ nhiều operator. Tránh đặt một request body lớn, DataBuffer, entity mutable hoặc object có lifecycle ngắn vào Context. Chỉ lưu metadata nhỏ, immutable và có ý nghĩa xuyên suốt chain.

### 12.4. Tránh log secret

Không đưa access token, refresh token, cookie, session ID hoặc dữ liệu cá nhân vào log chỉ vì filter có thể đọc chúng. Nếu cần debug, ghi correlation ID và mã lỗi đã được làm sạch; không log toàn bộ Context hoặc attributes map.

### 12.5. Không trộn Context giữa request

Không dùng một static mutable map làm nơi lưu request metadata. Mỗi subscriber có Context riêng; giá trị request A không được ghi vào state dùng chung rồi đọc lại trong request B.

Nếu cần chia sẻ cache hoặc cấu hình toàn cục, dùng cơ chế cache/configuration có concurrency policy rõ ràng, không dùng Reactor Context.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ attribute tự thành HTTP header | Dịch vụ đích không nhận được giá trị | Map attribute thành header/query/body trong filter |
| Dùng attribute cho nhiều nested calls | Request sau thiếu metadata | Gắn attribute cho từng request hoặc dùng Reactor Context |
| Đọc Context ngoài reactive subscription | Không có Context của request hiện tại | Dùng deferContextual trong operator/filter |
| Đặt contextWrite quá sớm | Operator downstream không nhìn thấy key | Đặt contextWrite ở cuối chain tương ứng |
| Nghĩ Context là ThreadLocal | Mất hoặc trộn dữ liệu khi đổi thread | Dùng Reactor Context |
| Nghĩ Context là Map mutable | Giá trị ghi không xuất hiện ở nơi khác | Nhớ put trả Context mới; compose contextWrite |
| Tạo nested WebClient call bằng subscribe riêng | Context propagation và error/cancel lifecycle bị tách | Return/compose publisher qua flatMap/concatMap |
| Lưu correlation ID vào field của singleton filter | Request đồng thời có thể dùng nhầm ID | Đọc ID từ Context mỗi subscription |
| Chuyển toàn bộ attributes thành headers | Lộ metadata nội bộ | Allowlist từng attribute được phép truyền |
| Dùng tenant ID từ client làm authorization | Có nguy cơ truy cập chéo tenant | Lấy tenant từ principal đã xác thực |
| Ghi access token vào Context rồi log toàn bộ | Rò credential | Không log Context/attributes chứa secret |
| Filter đọc response nhưng không release body | Giữ buffer/connection hoặc gây leak | Consume, release hoặc chuyển tiếp response downstream |
| Filter tự subscribe | Mất liên kết với caller và HTTP lifecycle | Trả publisher từ filter |
| Dùng ThreadLocal để lưu request metadata trong WebFlux | Giá trị phụ thuộc thread và có thể sai request | Dùng Reactor Context; bridge có chủ đích nếu cần |
| Dùng Context để truyền payload lớn | Tăng memory và khó quản lý lifecycle | Truyền payload qua publisher/body riêng |
| Ghi cùng key Context ở nhiều tầng | Giá trị phụ thuộc vị trí operator | Dùng key duy nhất và một điểm ghi rõ ràng |

## 14. Checklist triển khai

Trước khi thêm request metadata cho WebClient, hãy kiểm tra:

1. Metadata chỉ dành cho một request hay cần truyền qua nhiều nested calls?
2. Nếu chỉ dành cho một request, đã dùng `attribute(...)` hoặc `attributes(...)` đúng request chưa?
3. Nếu cần truyền xuyên reactive chain, đã dùng Reactor Context chưa?
4. Filter có đọc attribute qua `ClientRequest.attribute(...)` và Context qua `Mono.deferContextual(...)` đúng lifecycle không?
5. `contextWrite(...)` có nằm ở vị trí để các operator cần đọc nhìn thấy giá trị không?
6. Nếu dịch vụ đích cần giá trị, filter đã map rõ sang HTTP header/query/body theo contract chưa?
7. Nested WebClient call có được compose bằng flatMap/concatMap và return publisher không?
8. Có call nào tự subscribe hoặc block làm đứt Context propagation không?
9. Có dùng ThreadLocal/MDC không? Nếu có, đã chọn cơ chế bridge phù hợp chưa?
10. Context key có duy nhất và value có immutable/nhỏ gọn không?
11. Có metadata nhạy cảm nào bị log hoặc gửi nhầm ra ngoài không?
12. Test có xác nhận request attribute chỉ áp dụng cho request hiện tại và Context truyền tới nested calls không?
13. Filter có luôn consume/release hoặc chuyển tiếp response body đúng cách không?
14. Có kiểm tra authorization trước khi truyền tenant/user metadata sang dịch vụ khác không?

## 15. Tóm tắt lựa chọn API

| Nhu cầu | Cơ chế |
| --- | --- |
| Thêm metadata cho một request WebClient | `RequestHeadersSpec.attribute(name, value)` |
| Thêm nhiều metadata cho một request | `RequestHeadersSpec.attributes(Consumer<Map<String,Object>>)` |
| Thêm metadata mặc định cho mọi request | `WebClient.Builder.defaultRequest(...)` |
| Đọc metadata trong filter | `ClientRequest.attribute(name)` hoặc `ClientRequest.attributes()` |
| Tạo request mới trong filter | `ClientRequest.from(request)` |
| Thêm metadata vào reactive chain | `contextWrite(...)` |
| Đọc metadata trong operator/filter | `Mono.deferContextual(...)` |
| Đọc Context ở giữa chain | `transformDeferredContextual(...)` |
| Kiểm tra key có tồn tại | `ContextView.hasKey(...)` |
| Đọc giá trị có fallback | `ContextView.getOrDefault(...)` |
| Đọc giá trị dạng Optional | `ContextView.getOrEmpty(...)` |
| Kiểm thử publisher và Context | `StepVerifier` |
| Bridge ThreadLocal khi thực sự cần | `io.micrometer:context-propagation` |

## 16. Tài liệu tham khảo chính thức

- [Spring Framework – WebClient Attributes](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-attributes.html): thêm attribute vào request, đọc trong filter và dùng defaultRequest.
- [Spring Framework – WebClient Context](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-context.html): lý do dùng Reactor Context cho các request lồng nhau và cách đọc bằng deferContextual.
- [Spring Framework – WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): ExchangeFilterFunction, sửa ClientRequest và quản lý response body khi filter can thiệp.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): WebClient.Builder, filter, defaultRequest và lifecycle immutable của WebClient.
- [Reactor Reference – Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Context immutable, subscriber-scoped, contextWrite và deferContextual.
- [Reactor Reference – Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): tích hợp Reactor Context với ThreadLocal thông qua Micrometer Context Propagation.
- [Spring Security – Reactive Security Context](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): truy cập SecurityContext trong reactive stack.

## 17. Ghi nhớ

**Request attributes dành cho metadata của một ClientRequest; Reactor Context dành cho metadata theo subscriber/reactive chain.** Attribute hữu ích khi một filter cần biết request hiện tại đang thực hiện thao tác gì. Context hữu ích khi một chuỗi có nhiều WebClient call lồng nhau cần dùng chung correlation ID, tenant metadata hoặc thông tin tracing.

Cả hai đều là dữ liệu nội bộ. Muốn gửi giá trị sang dịch vụ HTTP, hãy map tường minh sang header, query parameter hoặc body trong filter. Đọc attributes từ ClientRequest và đọc Context bằng `Mono.deferContextual(...)`. Ghi Context bằng `contextWrite(...)` ở cuối chain để các operator phía upstream nhìn thấy dữ liệu. Giữ publisher trong cùng reactive chain để Context propagation hoạt động; tránh ThreadLocal, state mutable dùng chung, block và subscribe thủ công. Kiểm thử cả phạm vi của attribute lẫn propagation của Context để tránh metadata bị thiếu hoặc rò giữa các request.
