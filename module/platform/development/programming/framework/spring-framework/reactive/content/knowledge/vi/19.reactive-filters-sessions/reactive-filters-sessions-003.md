# Kết hợp `chain.filter` thay vì tự `subscribe()` trong Spring WebFlux

## 1. Vấn đề: filter phải nằm trong vòng đời của request

`WebFilter` là điểm mở rộng của Spring WebFlux để xử lý logic chung trước và sau phần còn lại của một HTTP request. Ví dụ thường gặp là correlation ID, logging, đo thời gian, CORS, xác thực, session và các chính sách áp dụng cho nhiều endpoint.

Một `WebFilter` nhận `ServerWebExchange` cùng `WebFilterChain` và trả về `Mono<Void>`:

```java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
```

Điểm quan trọng nằm ở giá trị trả về: `Mono<Void>` đại diện cho **toàn bộ quá trình xử lý request tiếp tục qua filter kế tiếp và handler cuối cùng**. Filter cần compose publisher này rồi trả lại cho Spring.

Một lỗi rất phổ biến là gọi:

```java
chain.filter(exchange).subscribe();
return Mono.empty();
```

Cách này tạo subscription tách rời. Filter trả về `Mono.empty()` ngay khi subscription riêng được khởi động, nên framework có thể coi filter đã hoàn tất trong khi handler vẫn chạy ở một luồng tín hiệu khác. Lỗi downstream không còn được truyền đúng qua pipeline ban đầu; cancellation từ client cũng không còn gắn chắc với công việc đã tách ra; response có thể bị commit hoặc kết thúc sớm.

Nguyên tắc cần nhớ:

> **Trong `WebFilter`, gọi `chain.filter(exchange)` đúng một lần, compose các operator cần thiết và return publisher đó. Không tự gọi `subscribe()` hoặc `block()`.**

Bài học đi sâu vào cách filter chain hoạt động, thứ tự trước/sau, xử lý lỗi và cancellation, cách dùng `WebSession` bất đồng bộ, và cách kiểm thử để phát hiện subscription bị tách khỏi request.

## 2. WebFlux filter chain hoạt động như thế nào?

Spring WebFlux xây dựng một chuỗi gồm nhiều `WebFilter` và một `WebHandler` đích. Mỗi filter có thể làm việc trước khi chuyển request tiếp, hoặc gắn operator để quan sát phần xử lý phía sau.

```text
HTTP request
     |
     v
WebFilter A
  before logic
     |
     | chain.filter(exchange)
     v
WebFilter B
  before logic
     |
     | chain.filter(exchange)
     v
WebFilter C
  before logic
     |
     | chain.filter(exchange)
     v
DispatcherHandler / WebHandler
  controller hoặc functional endpoint
     |
     v
HTTP response
     |
     v
WebFilter C after logic
     |
     v
WebFilter B after logic
     |
     v
WebFilter A after logic
     |
     v
Hoàn tất response pipeline
```

Filter được gọi theo thứ tự của chain. Khi filter A gọi `chain.filter`, quyền xử lý được chuyển cho filter B. Khi publisher phía sau hoàn tất, các callback đã được gắn ở A có thể chạy khi tín hiệu quay trở lại theo pipeline.

Đây là mô hình “wrap”:

```java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    // Before: chạy ở filter hiện tại.

    return chain.filter(exchange)
            .doOnSuccess(ignored -> {
                // Sau khi phần downstream complete.
            })
            .doOnError(error -> {
                // Quan sát lỗi từ downstream.
            })
            .doFinally(signal -> {
                // Quan sát complete, error hoặc cancel.
            });
}
```

`chain.filter(exchange)` không phải lời gọi để tự chạy một request độc lập. Nó trả về một publisher đại diện cho phần còn lại của chain. Spring quản lý subscription ở cấp request; việc return publisher cho phép framework điều khiển demand, terminal signal và cancellation.

### Một request, một pipeline được compose

Giả sử có ba filter:

- Filter A thêm request ID.
- Filter B đọc session và tăng số lần truy cập.
- Filter C ghi nhận thời gian xử lý.

Mỗi filter trả publisher của phần downstream đã được bọc thêm hành vi riêng. Kết quả là một pipeline duy nhất cho request, thay vì ba subscription độc lập.

Nếu một filter cần từ chối request, nó có thể không gọi `chain.filter` và tự hoàn tất response. Ví dụ:

```java
if (!allowed) {
    exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
    return exchange.getResponse().setComplete();
}

return chain.filter(exchange);
```

Đây là short-circuit có chủ đích: request bị chặn nên không đi tới filter/handler phía sau. Trong ứng dụng thực, authentication và authorization nên tích hợp Spring Security; ví dụ trên chỉ minh họa cơ chế dừng chain.

## 3. Vì sao `subscribe()` trong filter là sai?

### 3.1. Hai subscription độc lập

Đoạn code sai:

```java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    chain.filter(exchange).subscribe();

    return Mono.empty();
}
```

Có hai publisher khác nhau:

1. Publisher được subscribe thủ công bên trong filter.
2. `Mono.empty()` mà framework nhận làm kết quả của filter.

Framework chỉ thấy publisher thứ hai. Publisher thứ nhất chạy ngoài vòng đời mà framework đang quản lý.

Hậu quả:

- **Response lifecycle sai**: filter có thể báo hoàn tất trước khi handler ghi response.
- **Lỗi bị tách**: exception từ handler không nhất thiết đi qua pipeline mà framework đang chờ.
- **Cancellation bị mất liên kết**: client ngắt kết nối có thể hủy pipeline được return, nhưng subscription tự tạo vẫn tiếp tục.
- **Tài nguyên bị giữ lâu**: HTTP client, database query, session hoặc stream có thể chạy sau khi request đã kết thúc.
- **Khó kiểm thử**: test thấy filter complete nhưng công việc nền vẫn còn chạy.
- **Khó quản lý context**: Reactor Context và các hook quan sát có thể không còn ở đúng subscription dự kiến.

### 3.2. Cách đúng: compose rồi return

```java
@Override
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    return chain.filter(exchange)
            .doOnError(error ->
                    log.warn("Request failed", error))
            .doFinally(signal ->
                    log.debug("Request finished: {}", signal));
}
```

`doOnError` chỉ quan sát lỗi và không biến lỗi thành thành công. Lỗi tiếp tục truyền downstream theo contract. `doFinally` quan sát tín hiệu kết thúc và không thay thế publisher.

Nếu cần chạy tác vụ bất đồng bộ trước khi vào handler:

```java
return loadPolicy(exchange)
        .flatMap(policy -> {
            exchange.getAttributes().put("policy", policy);
            return chain.filter(exchange);
        });
```

Nếu cần chạy tác vụ bất đồng bộ sau handler:

```java
return chain.filter(exchange)
        .then(writeAuditRecord(exchange));
```

Cả hai trường hợp đều nối publisher bằng `flatMap` hoặc `then`; không tạo subscription phụ.

### 3.3. Không dùng `block()` để chờ chain

Đoạn sau cũng sai:

```java
chain.filter(exchange).block();
return Mono.empty();
```

`block()` chờ đồng bộ trên thread đang thực thi filter. Nếu thread đó là event-loop của Reactor Netty, nó có thể chặn việc xử lý các kết nối khác và phá vỡ mô hình non-blocking. Thay vì chờ bằng Java call stack, hãy biểu diễn thứ tự công việc trong reactive chain.

## 4. Mẫu `before → chain → after`

Một filter thường có ba giai đoạn:

1. Thực hiện logic trước khi chuyển tiếp.
2. Delegate sang phần còn lại bằng `chain.filter(exchange)`.
3. Gắn hành vi xử lý sau khi downstream hoàn tất.

```java
@Component
public class TimingWebFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(TimingWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        long startedAt = System.nanoTime();

        log.debug("before request {}", exchange.getLogPrefix());

        return chain.filter(exchange)
                .doOnSuccess(ignored ->
                        log.debug("downstream completed"))
                .doOnError(error ->
                        log.warn("downstream failed", error))
                .doFinally(signal -> {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt);

                    log.info(
                            "request signal={} durationMs={}",
                            signal, elapsedMs);
                });
    }
}
```

Các import cần thiết:

```java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;
```

Đây là snippet filter có thể biên dịch trong ứng dụng Spring WebFlux đã có dependency tương ứng.

### `doOnSuccess`, `doOnError` và `doFinally`

`chain.filter` trả `Mono<Void>`:

- `doOnSuccess` được gọi khi downstream complete thành công; giá trị callback là `null` vì Mono<Void> không phát giá trị.
- `doOnError` được gọi nếu lỗi đi qua vị trí operator đó.
- `doFinally` nhận `SignalType.ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`.

Cancellation không phải complete. Nếu client ngắt kết nối, filter có thể quan sát `CANCEL`; không được ghi log “request success” chỉ vì một callback cleanup đã chạy.

`doFinally` được gọi sau khi terminal/cancel được truyền qua vị trí operator. Dùng nó cho metrics và logging, không dùng để thay đổi response body/header ở thời điểm có thể response đã commit.

### Dùng `Mono.defer` khi muốn trì hoãn side effect trước chain

Nếu muốn hành động trước request chỉ chạy khi publisher được subscribe:

```java
return Mono.defer(() -> {
    log.debug("filter subscribed");
    return chain.filter(exchange);
});
```

`Mono.defer` gọi supplier khi subscription bắt đầu. Trong một `WebFilter` bình thường, filter method được framework gọi trong quá trình xử lý request; không phải mọi dòng trước `return` đều cần bọc trong `defer`. Dùng `defer` khi bạn cần đảm bảo side effect hoặc việc tạo publisher chỉ diễn ra theo subscription, đặc biệt khi publisher có thể được tái sử dụng.

## 5. Trình tự thực thi khi có nhiều filter

WebFlux tự động phát hiện các bean `WebFilter` trong application context. Có thể quy định thứ tự bằng `@Order` hoặc triển khai `Ordered`.

Giá trị order nhỏ hơn có precedence cao hơn và được gọi sớm hơn. Filter vào trước sẽ bao phần xử lý của filter vào sau; phần callback sau chain thường diễn ra theo chiều ngược lại.

Ví dụ:

```java
@Component
@Order(1)
public class FirstWebFilter implements WebFilter {
    // ...
}

@Component
@Order(2)
public class SecondWebFilter implements WebFilter {
    // ...
}
```

Trình tự khái niệm:

```text
First.before
  Second.before
    Handler
  Second.after
First.after
```

Không nên dựa vào thứ tự bean được phát hiện ngẫu nhiên. Nếu logging, security, CORS, session hoặc tracing phụ thuộc vào nhau, khai báo order rõ ràng và kiểm tra thứ tự thực tế của ứng dụng.

### Tương tác với Spring Security

Spring Security WebFlux cũng tham gia filter chain thông qua `WebFilterChainProxy`. Thứ tự của security chain có ý nghĩa bảo mật. Không đặt custom filter trước hoặc sau security một cách tùy tiện:

- Filter cần thông tin principal đã xác thực nên chạy sau bước security authentication.
- Filter tạo request ID/log metadata có thể chạy sớm hơn, miễn không tự coi header do client gửi là danh tính đáng tin cậy.
- CORS preflight cần được xử lý đúng thứ tự với security.
- Authorization nên dùng Spring Security, không chỉ dựa trên một điều kiện header trong custom filter.

Thứ tự cụ thể phụ thuộc cấu hình Spring Boot/Security của ứng dụng. Hãy xác định rõ filter đang được gắn vào server chain hay security chain.

## 6. Thay đổi request hoặc exchange mà vẫn giữ pipeline

`ServerWebExchange` là abstraction cho request-response hiện tại. Nếu cần thêm header nội bộ hoặc thay đổi request trước khi delegate, hãy tạo bản request/exchange đã mutate rồi truyền bản đó vào `chain.filter`.

```java
ServerHttpRequest mutatedRequest = exchange.getRequest()
        .mutate()
        .header("X-Internal-Request", "true")
        .build();

ServerWebExchange mutatedExchange = exchange.mutate()
        .request(mutatedRequest)
        .build();

return chain.filter(mutatedExchange);
```

Các import chính:

```java
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.server.ServerWebExchange;
```

Đây là ví dụ mutate request tại biên. Không sửa trực tiếp các cấu trúc bất biến như request headers gốc. Không ghi đè header do client gửi mà chưa có chính sách rõ ràng; header nội bộ cần được tạo tại ranh giới tin cậy.

### Dùng request attributes cho dữ liệu nội bộ theo request

Nếu chỉ cần chia sẻ dữ liệu giữa các filter và handler trong cùng một exchange, có thể dùng attributes:

```java
exchange.getAttributes().put("requestId", requestId);

return chain.filter(exchange);
```

Controller hoặc handler có thể đọc:

```java
String requestId = exchange.getAttribute("requestId");
```

Request attributes thuộc một exchange, không phải session và không tồn tại giữa các HTTP request khác nhau. Không dùng static map hoặc singleton map để giữ dữ liệu request vì dễ gây rò rỉ, tranh chấp và giữ object quá lâu.

### Thêm response header trước khi response commit

Header có thể được đặt trước khi delegate:

```java
exchange.getResponse().getHeaders()
        .set("X-Request-Id", requestId);

return chain.filter(exchange);
```

Nếu cần thao tác ngay trước khi response được commit, dùng callback `beforeCommit`:

```java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Processed-By", "webflux");
    return Mono.empty();
});

return chain.filter(exchange);
```

Không chờ `chain.filter` complete rồi mới sửa header trong `doFinally`: response có thể đã được commit và header không còn thay đổi được. `beforeCommit` đăng ký callback để thực hiện trước thời điểm commit.

## 7. Dùng `WebSession` bất đồng bộ bên trong filter

`ServerWebExchange.getSession()` trả về `Mono<WebSession>`. Đây là thao tác reactive, nên phải compose nó vào pipeline trước khi delegate.

### 7.1. Đọc và cập nhật session

```java
@Component
@Order(2)
public class VisitCounterWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        if (!exchange.getRequest().getPath().value().equals("/session")) {
            return chain.filter(exchange);
        }

        return exchange.getSession()
                .flatMap(session -> {
                    Integer current = session.getAttribute("visits");
                    int next = current == null ? 1 : current + 1;

                    session.getAttributes().put("visits", next);

                    return chain.filter(exchange);
                });
    }
}
```

Đây là filter đầy đủ cho ví dụ. Cách hoạt động:

1. Request không phải `/session` đi tiếp ngay.
2. Request `/session` lấy `WebSession` bằng publisher.
3. Khi session sẵn sàng, filter đọc số lần truy cập hiện tại.
4. Filter cập nhật session attribute.
5. Filter delegate sang phần còn lại bằng `chain.filter(exchange)`.

Không viết:

```java
exchange.getSession().subscribe(session -> {
    session.getAttributes().put("visits", 1);
});

return chain.filter(exchange);
```

Trong đoạn sai, chain có thể chạy trước khi session được đọc/cập nhật. Ngoài ra, lỗi lấy session bị tách khỏi pipeline request và cancellation không được liên kết đúng.

### 7.2. Khi nào session thực sự được tạo và lưu?

Cần phân biệt ba việc:

- `exchange.getSession()` cung cấp publisher để lấy session hiện tại hoặc tạo một đối tượng session mới khi cần; chỉ gọi method này **không tự động start session**.
- Gọi `session.getAttributes().put(...)` làm session được start ngầm; gọi `session.start()` cũng có thể start tường minh.
- Spring tự động gọi `WebSession.save()` ngay trước khi response commit. Ứng dụng thông thường không cần tự gọi `save()`.

Vì vậy, trong filter trên, việc thêm attribute được compose trước `chain.filter`; WebFlux xử lý việc lưu session theo vòng đời response. Không cần `session.save().subscribe()` hoặc `.block()`.

`WebSession` mặc định dùng store trong bộ nhớ của ứng dụng. Nếu cần session chia sẻ giữa nhiều instance hoặc tồn tại qua restart, hãy cấu hình một session store phù hợp (ví dụ Spring Session với Redis). Không coi in-memory session là kho dữ liệu bền vững.

### 7.3. Session và request attributes không giống nhau

| Nơi lưu | Phạm vi sống | Ví dụ |
|---|---|---|
| `exchange.getAttributes()` | Một HTTP exchange | request ID, route metadata |
| `WebSession.getAttributes()` | Nhiều request thuộc cùng session | lựa chọn UI, giỏ hàng nhỏ |
| Reactor Context | Một reactive subscription | tracing/security context |
| Database/cache bên ngoài | Theo chính sách lưu trữ | dữ liệu nghiệp vụ lâu dài |

Không lưu dữ liệu nghiệp vụ quan trọng chỉ trong session. Session có thể hết hạn, bị invalidated hoặc không được chia sẻ giữa các node nếu cấu hình store không phù hợp.

### 7.4. Hủy và thay đổi session

Các thao tác như `session.invalidate()` và `session.changeSessionId()` trả về publisher. Phải compose chúng:

```java
return exchange.getSession()
        .flatMap(WebSession::invalidate)
        .then(chain.filter(exchange));
```

Đây là snippet minh họa khi cần invalidate rồi tiếp tục chain. Trong endpoint logout thực tế, thường cần xóa session và trả response logout rõ ràng; nếu filter/handler phía sau lại truy cập session, một session mới có thể được tạo. Hãy thiết kế luồng logout theo đúng security contract.

Sau xác thực thành công, thay session ID để bảo vệ khỏi session fixation có thể được biểu diễn:

```java
return exchange.getSession()
        .flatMap(session -> session.changeSessionId())
        .then(chain.filter(exchange));
```

Đây chỉ là ví dụ API composition. Việc đổi session ID nên được đặt trong luồng xác thực phù hợp hoặc để Spring Security quản lý session fixation protection, không tự thêm filter tùy tiện.

### 7.5. Tránh cập nhật session không an toàn khi có request đồng thời

Hai request đồng thời dùng chung một session có thể cùng đọc `visits=4`, cùng tính `5`, rồi cùng ghi `5`. Đây là lost update. Map session không biến phép read-modify-write thành thao tác atomic.

Nếu cần bộ đếm chính xác, dùng cơ chế atomic ở store phù hợp hoặc một service lưu trạng thái có đồng bộ. Session phù hợp với lượng trạng thái nhỏ cho người dùng, không phải cơ sở dữ liệu giao dịch.

## 8. Lỗi và cancellation truyền qua filter chain như thế nào?

Vì filter return publisher của downstream, lỗi có thể được quan sát và xử lý theo reactive operator.

### Chỉ ghi log, giữ nguyên lỗi

```java
return chain.filter(exchange)
        .doOnError(error ->
                log.warn("Request pipeline failed", error));
```

`doOnError` không phục hồi lỗi. Downstream subscriber vẫn nhận `onError`.

### Chuyển lỗi thành response tại biên

```java
return chain.filter(exchange)
        .onErrorResume(DomainException.class, error -> {
            exchange.getResponse()
                    .setStatusCode(HttpStatus.CONFLICT);
            return exchange.getResponse().setComplete();
        });
```

Đây là snippet minh họa. Chỉ xử lý loại exception mà filter thực sự sở hữu chính sách ánh xạ. Đừng bắt mọi `Throwable` rồi trả 200 hoặc 400; điều đó che lỗi server và bug.

Nếu response đã commit, filter không thể thay đổi status/body theo cách thông thường. Cần xử lý lỗi trước khi response commit hoặc dùng error handling phù hợp ở framework.

### Cancellation

Nếu client disconnect, timeout hoặc subscriber phía trên hủy request, cancellation được truyền ngược qua publisher đã compose. `doFinally` có thể nhận `SignalType.CANCEL`.

Đây là lợi ích lớn của `return chain.filter(exchange)`: cancellation thuộc cùng pipeline. Nếu filter gọi `.subscribe()` riêng, pipeline request không còn sở hữu công việc đó.

Cancellation vẫn là yêu cầu hủy. Một thư viện blocking hoặc remote server có thể tiếp tục xử lý vật lý nếu nó không hỗ trợ cancellation; filter không thể bảo đảm dừng một tác vụ ngoài contract của client/driver.

### Không gọi chain nhiều lần

Không viết:

```java
return chain.filter(exchange)
        .then(chain.filter(exchange));
```

Điều này có thể gọi downstream hai lần và gây lặp side effect: ghi database, gửi email, tạo đơn hàng hoặc tiêu thụ body nhiều lần. Mỗi request thường cần delegate một lần. Nếu muốn chạy công việc phụ sau downstream, compose công việc phụ bằng `then(...)`, không gọi lại chain.

## 9. Phân biệt `WebFilter`, `HandlerFilterFunction` và filter của WebClient

Tên “filter” xuất hiện ở nhiều lớp khác nhau:

| Loại | Chạy ở đâu? | API chain |
|---|---|---|
| `WebFilter` | Server WebFlux, bao quanh toàn bộ web handler chain | `WebFilterChain.filter(exchange)` |
| `HandlerFilterFunction` | Functional endpoint/WebFlux.fn, bao quanh handler route | `next.handle(request)` |
| `ExchangeFilterFunction` | Outbound `WebClient` request/response | `next.exchange(request)` |
| Spring Security `WebFilter` | Server security chain | Security filter chain |

Các API có hình thức tương tự vì đều dùng composition, nhưng request/response type và phạm vi khác nhau. Không dùng `WebFilterChain` để xử lý outbound `WebClient`; không gọi `next.exchange` trong server `WebFilter`.

### `HandlerFilterFunction`

Với functional endpoint, router có thể gắn filter vào các route:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> logFilter =
        (request, next) -> {
            log.info("path={}", request.path());
            return next.handle(request)
                    .doOnError(error ->
                            log.warn("handler failed", error));
        };
```

`next.handle(request)` trả `Mono<ServerResponse>`. Cũng cần return publisher và không tự subscribe.

### `ExchangeFilterFunction`

Với `WebClient`:

```java
ExchangeFilterFunction clientLogFilter =
        (request, next) -> next.exchange(request)
                .doOnNext(response ->
                        log.debug("status={}", response.statusCode()));
```

Đây là outbound client filter. Nó quan sát HTTP response từ dịch vụ mà ứng dụng gọi; không phải filter của request đang đi vào server.

## 10. Dự án Java 17+ chạy được: filter chain, request ID và session counter

Ví dụ dùng Spring Boot 3.3.5, Java 17 và Maven. Ứng dụng có:

- `RequestIdWebFilter`: tạo ID cho request, đặt response header và exchange attribute.
- `VisitCounterWebFilter`: cập nhật `WebSession` qua `flatMap` rồi mới gọi chain.
- `DemoController`: trả request ID hoặc số lượt truy cập session.
- `WebTestClient` tests: kiểm tra filter được compose, cookie session được duy trì qua hai request.
- Một test `StepVerifier`: xác nhận cancellation đi qua publisher của filter.

### 10.1. Cấu trúc dự án

```text
webflux-filter-chain/
├── pom.xml
└── src/
    ├── main/java/edu/demo/filter/
    │   ├── FilterApplication.java
    │   ├── RequestIdWebFilter.java
    │   ├── VisitCounterWebFilter.java
    │   └── DemoController.java
    └── test/java/edu/demo/filter/
        └── FilterChainTest.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-filter-chain</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 10.3. `FilterApplication.java`

```java
package edu.demo.filter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterApplication.class, args);
    }
}
```

### 10.4. `RequestIdWebFilter.java`

```java
package edu.demo.filter;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(1)
public class RequestIdWebFilter implements WebFilter {

    public static final String REQUEST_ID_ATTRIBUTE =
            RequestIdWebFilter.class.getName() + ".requestId";

    private static final Logger log =
            LoggerFactory.getLogger(RequestIdWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(
                REQUEST_ID_ATTRIBUTE, requestId);

        exchange.getResponse().getHeaders().set(
                "X-Request-Id", requestId);

        long startedAt = System.nanoTime();

        return chain.filter(exchange)
                .doOnError(error ->
                        log.warn(
                                "requestId={} failed",
                                requestId,
                                error))
                .doFinally(signal -> {
                    long elapsedMs =
                            (System.nanoTime() - startedAt) / 1_000_000;

                    log.info(
                            "requestId={} signal={} durationMs={}",
                            requestId,
                            signal,
                            elapsedMs);
                });
    }
}
```

Filter tạo correlation ID ở phía server, lưu vào attributes của exchange và response header. Ví dụ không tin một ID bất kỳ từ client để làm identity. Trong production, có thể tiếp nhận một correlation ID đã được gateway xác thực hoặc tạo ID mới theo logging policy.

### 10.5. `VisitCounterWebFilter.java`

```java
package edu.demo.filter;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(2)
public class VisitCounterWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        if (!exchange.getRequest().getPath().value().equals("/session")) {
            return chain.filter(exchange);
        }

        return exchange.getSession()
                .flatMap(session -> {
                    Integer current = session.getAttribute("visits");
                    int next = current == null ? 1 : current + 1;

                    session.getAttributes().put("visits", next);

                    return chain.filter(exchange);
                });
    }
}
```

Filter chỉ đọc session cho endpoint `/session`. `flatMap` bảo đảm phần còn lại của chain chạy sau khi session được lấy và cập nhật.

### 10.6. `DemoController.java`

```java
package edu.demo.filter;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/chain")
    public Mono<Map<String, String>> chain(ServerWebExchange exchange) {
        String requestId = exchange.getAttribute(
                RequestIdWebFilter.REQUEST_ID_ATTRIBUTE);

        return Mono.just(Map.of("requestId", requestId));
    }

    @GetMapping("/session")
    public Mono<Map<String, Integer>> session(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> {
                    Integer visits = session.getAttribute("visits");
                    return Map.of("visits", visits == null ? 0 : visits);
                });
    }
}
```

Controller đọc cùng exchange và cùng WebSession đã được filter xử lý. Không cần tạo subscription thủ công trong controller.

### 10.7. `FilterChainTest.java`

```java
package edu.demo.filter;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.web.server.MockServerHttpRequest;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.http.ResponseCookie;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import org.springframework.web.server.WebFilter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FilterChainTest {

    @Autowired
    WebTestClient client;

    @Test
    void filterComposesWithEndpointAndAddsRequestId() {
        client.get()
                .uri("/chain")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("X-Request-Id")
                .expectBody()
                .jsonPath("$.requestId").exists();
    }

    @Test
    void sessionIsSharedAcrossRequestsWithSameCookie() {
        EntityExchangeResult<byte[]> first = client.get()
                .uri("/session")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.visits").isEqualTo(1)
                .returnResult();

        ResponseCookie sessionCookie =
                first.getResponseCookies().getFirst("SESSION");

        assertNotNull(sessionCookie);

        client.get()
                .uri("/session")
                .cookie("SESSION", sessionCookie.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.visits").isEqualTo(2);
    }

    @Test
    void cancellationFlowsThroughFilterPublisher() {
        AtomicReference<SignalType> finalSignal =
                new AtomicReference<>();

        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get("/never").build());

        WebFilter filter = (currentExchange, chain) ->
                chain.filter(currentExchange)
                        .doFinally(finalSignal::set);

        StepVerifier.create(
                        filter.filter(exchange, currentExchange ->
                                Mono.never()))
                .expectSubscription()
                .thenCancel()
                .verify();

        assertEquals(SignalType.CANCEL, finalSignal.get());
    }
}
```

### 10.8. Chạy ứng dụng và kiểm thử

Trong thư mục có `pom.xml`:

```bash
mvn test
```

Khi dependency tải được và assertion đúng, dự án có **3 test**:

1. Filter tạo request ID, handler nhận được exchange attribute và response có header tương ứng.
2. Session counter tăng từ 1 lên 2 khi client gửi lại cùng cookie `SESSION`.
3. Cancellation được quan sát là `SignalType.CANCEL` qua publisher được return từ filter.

Khởi động ứng dụng:

```bash
mvn spring-boot:run
```

Gọi endpoint có request ID:

```bash
curl -i http://localhost:8080/chain
```

Response có header tương tự:

```http
HTTP/1.1 200 OK
X-Request-Id: 4c6d...
Content-Type: application/json

{"requestId":"4c6d..."}
```

Giá trị UUID thực tế thay đổi theo request.

Gọi session endpoint lần đầu:

```bash
curl -i -c cookies.txt http://localhost:8080/session
```

Response body:

```json
{"visits":1}
```

Gọi lại bằng cookie đã lưu:

```bash
curl -i -b cookies.txt -c cookies.txt http://localhost:8080/session
```

Response body:

```json
{"visits":2}
```

Ví dụ dùng default in-memory WebSession store, nên dữ liệu session chỉ tồn tại theo vòng đời ứng dụng/store đó. Không dùng bộ đếm session làm dữ liệu giao dịch cần chính xác khi có request đồng thời.

Các test và lệnh trên là hướng dẫn chạy độc lập. Chỉ xác nhận test PASS sau khi thực thi `mvn test` trong môi trường thật; nội dung bài không tuyên bố đã chạy Maven.

## 11. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| `chain.filter(exchange).subscribe()` | Subscription tách khỏi request | Return publisher đã compose |
| Gọi `.block()` trong filter | Chặn event-loop, phá non-blocking | Dùng `flatMap`, `then`, `onErrorResume` |
| Gọi `chain.filter` hai lần | Handler chạy lặp, side effect lặp | Delegate đúng một lần |
| `exchange.getSession().subscribe(...)` | Chain chạy trước khi session sẵn sàng | `getSession().flatMap(session -> chain.filter(...))` |
| Tạo `Mono` phụ nhưng không nối vào return | Tác vụ không được framework quản lý | Ghép bằng `then`/`flatMap` |
| Ghi header trong `doFinally` | Response có thể đã commit | Ghi trước chain hoặc dùng `beforeCommit` |
| Coi cancel là complete | Log sai trạng thái request | Phân biệt `ON_COMPLETE`, `ON_ERROR`, `CANCEL` |
| Dùng request attributes cho dữ liệu qua nhiều request | Dữ liệu biến mất ở request tiếp theo | Dùng `WebSession` hoặc store phù hợp |
| Dùng session làm database | Lost update, mất dữ liệu khi expire/restart | Dùng repository/store giao dịch |
| Không đặt thứ tự filter | Hành vi phụ thuộc thứ tự không rõ | Dùng `@Order`/`Ordered` và kiểm thử |
| Custom filter tự xác thực bằng header | Dễ giả mạo danh tính | Dùng Spring Security/WebFlux Security |
| Nuốt lỗi bằng `onErrorResume` quá rộng | Che lỗi server và bug | Chỉ xử lý exception có chính sách rõ |

## 12. Checklist khi viết `WebFilter`

Trước khi đưa filter vào ứng dụng:

1. Filter có trả `Mono<Void>` của `chain.filter(exchange)` không?
2. Có gọi `chain.filter` đúng một lần cho request được delegate không?
3. Có `subscribe()` hoặc `block()` ẩn trong filter/helper không?
4. Tác vụ bất đồng bộ trước chain đã được nối bằng `flatMap`/`then` chưa?
5. Tác vụ sau chain đã được nối bằng `then`/operator phù hợp chưa?
6. Lỗi có tiếp tục truyền qua pipeline hay được xử lý có chủ đích?
7. Cancellation có thể truyền về upstream không?
8. Response header có được thiết lập trước commit không?
9. Session có được lấy/cập nhật trong cùng chain không?
10. Filter order có được khai báo rõ và tương thích Spring Security không?
11. Request attributes có bị dùng nhầm cho trạng thái giữa nhiều request không?
12. Có kiểm thử complete, error, cancel, session cookie và short-circuit không?
13. Filter có giữ dữ liệu nhạy cảm hoặc object request trong static/singleton state không?
14. Log có tránh ghi body/header/token nhạy cảm không?

## 13. Bài tập tự kiểm tra

**Bài 1.** Vì sao đoạn code sau không đúng?

```java
chain.filter(exchange).subscribe();
return Mono.empty();
```

**Đáp án:** Nó tạo subscription tách rời khỏi publisher mà framework đang quản lý. Filter complete sớm, lỗi/cancel không đi đúng pipeline và response lifecycle có thể sai.

**Bài 2.** Muốn chạy `loadPolicy()` trước handler thì compose thế nào?

**Đáp án:**

```java
return loadPolicy()
        .flatMap(policy -> {
            exchange.getAttributes().put("policy", policy);
            return chain.filter(exchange);
        });
```

**Bài 3.** `doFinally` nhận `CANCEL` nghĩa là gì?

**Đáp án:** Subscriber yêu cầu hủy subscription. Đây không phải `onComplete`; công việc vật lý ngoài ứng dụng có thể cần driver hỗ trợ cancellation mới dừng ngay.

**Bài 4.** `exchange.getSession()` có tự start session không?

**Đáp án:** Không. Nó cung cấp publisher cho session hiện tại hoặc session mới. Session được start khi gọi `start()` hoặc thêm attribute; Spring tự gọi save trước response commit.

**Bài 5.** Muốn tăng session counter rồi chạy handler, operator nào phù hợp?

**Đáp án:** `exchange.getSession().flatMap(session -> { update; return chain.filter(exchange); })`.

**Bài 6.** Vì sao không sửa response header trong `doFinally`?

**Đáp án:** Response có thể đã commit. Đặt header trước khi delegate hoặc đăng ký `beforeCommit`.

**Bài 7.** Có nên gọi `chain.filter(exchange)` hai lần để chạy lại handler sau audit không?

**Đáp án:** Không. Nó có thể chạy nghiệp vụ và side effect hai lần. Nối audit publisher bằng `then(audit)` hoặc thiết kế audit trước/sau trong cùng pipeline.

**Bài 8.** Request attribute và session attribute khác nhau thế nào?

**Đáp án:** Request attribute chỉ sống trong một exchange; session attribute có thể tồn tại qua nhiều request cùng session, theo store và thời gian hết hạn.

## 14. Ghi nhớ

- `WebFilter.filter` trả `Mono<Void>` biểu diễn phần còn lại của HTTP processing chain.
- `chain.filter(exchange)` phải được **compose và return**, không gọi `subscribe()` hoặc `block()`.
- Operator `doOn...`, `doFinally`, `then`, `flatMap`, `onErrorResume` cho phép thêm hành vi trước/sau mà vẫn giữ một subscription.
- Filter vào trước bao phần còn lại; `@Order`/`Ordered` xác định thứ tự.
- `ServerWebExchange` có request attributes theo exchange; `WebSession` giữ attributes qua nhiều request.
- `getSession()` là reactive; dùng `flatMap` để cập nhật session rồi delegate. Spring tự save session trước response commit.
- Error và cancellation được giữ trong pipeline khi không tách subscription.
- Security, CORS và session fixation cần phối hợp đúng thứ tự với Spring Security.
- Một filter nên có một trách nhiệm cross-cutting rõ ràng; không biến nó thành nơi xử lý nghiệp vụ.

Khi đọc một filter, hãy kiểm tra ba điều: **publisher nào được return, chain được gọi bao nhiêu lần, và tác vụ nào đang bị tách khỏi subscription**. Nếu mọi công việc đều được compose vào publisher trả về, WebFlux mới có thể quản lý đúng lifecycle của request.

## Tài liệu chính thức

- Spring Framework 6.2, **Reactive Core – WebHandler API and Filters**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2, **`WebFilter` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/server/WebFilter.html
- Spring Framework 6.2, **`WebFilterChain` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/server/WebFilterChain.html
- Spring Framework 6.2, **`ServerWebExchange` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.2, **`WebSession` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Boot, **Reactive Web Applications – Web Filters and ordering**: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Project Reactor, **Blocking can be wasteful – subscribe and composition**: https://projectreactor.io/docs/core/3.6.6/reference/coreFeatures/reactiveProgramming.html
- Spring Framework, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html