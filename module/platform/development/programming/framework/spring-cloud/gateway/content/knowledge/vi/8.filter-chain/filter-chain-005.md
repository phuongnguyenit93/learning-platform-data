# Tiếp tục chuỗi bằng chain.filter(exchange)

## 1. Vì sao cần hiểu lời gọi chain.filter(exchange)?

Trong **Spring Cloud Gateway Server WebFlux**, một request thường đi qua nhiều bộ lọc trước khi được chuyển tới microservice: gắn thông tin truy vết, thay đổi đường dẫn/header, xác thực hoặc kiểm tra chính sách, giới hạn lưu lượng, circuit breaker, retry và thu thập thông tin quan sát. Các bộ lọc này phải phối hợp để mỗi request được xử lý đúng thứ tự.

Lời gọi quan trọng nhất trong một bộ lọc tùy chỉnh là:

~~~java
return chain.filter(exchange);
~~~

Nó biểu thị: **tiếp tục chuyển `ServerWebExchange` tới phần còn lại của chuỗi filter và trả về một `Mono<Void>` đại diện cho việc xử lý bất đồng bộ đó**. Nếu một filter không gọi tiếp chuỗi, các filter phía sau và bước định tuyến upstream có thể không chạy; hành vi này có thể đúng khi filter cố ý từ chối request, nhưng là lỗi nếu tác giả chỉ quên trả về `chain.filter(exchange)`.

Trong bài học thuộc chương **Chuỗi bộ lọc**, ta tập trung vào vòng đời lời gọi `chain.filter(exchange)`, cách viết phần xử lý trước/sau, cách truyền exchange đã sửa, và khi nào cần dừng chuỗi. Các ví dụ đặt trong ngữ cảnh xây dựng **API Gateway** với route predicate, filter chain, chuyển đổi header/path, service discovery và các kiểm soát bảo mật/độ tin cậy.

**Sau bài học, bạn có thể:**

1. Mô tả vai trò của `ServerWebExchange`, `GatewayFilterChain` và kiểu trả về `Mono<Void>`.
2. Viết `GlobalFilter` hoặc `GatewayFilter` tiếp tục chuỗi chính xác, không tự `subscribe()` hay `block()`.
3. Phân biệt phần xử lý **pre**, **post**, **error** và **cancel** trong Reactor.
4. Thay đổi request/response đúng thời điểm, biết khi nào response đã được commit.
5. Nhận biết **short-circuit**, thứ tự filter, xử lý lỗi, request body streaming và các lỗi thường gặp.
6. Kiểm tra việc chuỗi thực sự chạy bằng thử nghiệm đơn vị và request qua gateway.

> Bài viết tập trung vào **Spring Cloud Gateway Server WebFlux** và Reactor. Spring Cloud Gateway Server Web MVC có mô hình filter khác; không nên dùng nguyên ví dụ `GatewayFilterChain` của WebFlux cho biến thể MVC.

## 2. Chuỗi filter nằm ở đâu trong quá trình xử lý request?

Khi request tới Gateway, `RoutePredicateHandlerMapping` tìm route phù hợp theo các điều kiện như `Path`, `Host`, `Method` hay `Header`. Sau khi chọn route, `FilteringWebHandler` tạo chuỗi kết hợp các `GlobalFilter` và `GatewayFilter` của route. Chuỗi được sắp xếp theo thứ tự và xử lý request theo mô hình reactive.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[RoutePredicateHandlerMapping]
    B -->|Đã chọn route| C[FilteringWebHandler]
    C --> D[Filter A: pre]
    D --> E[Filter B: pre]
    E --> F[Routing filter / upstream handler]
    F --> G[Filter B: post]
    G --> H[Filter A: post]
    H --> I[HTTP response]
~~~

Sơ đồ diễn tả **thứ tự bao bọc trước/sau** trong trường hợp request được xử lý bình thường. Trên thực tế một filter có thể chỉ chạy pre, chỉ quan sát tín hiệu kết thúc, tự trả response hoặc chuyển việc xử lý cho một cơ chế khác. Không phải mọi filter đều có một đoạn code post.

Ba khái niệm quan trọng:

| Khái niệm | Vai trò | Điều cần nhớ |
| --- | --- | --- |
| `ServerWebExchange` | Ngữ cảnh HTTP request/response của lần xử lý hiện tại | Chứa request, response, attributes và các thông tin liên quan |
| `GatewayFilterChain` | Trừu tượng để gọi phần còn lại của chuỗi | Phương thức chính là `Mono<Void> filter(ServerWebExchange exchange)` |
| `Mono<Void>` | Tín hiệu về việc xử lý bất đồng bộ kết thúc, lỗi hoặc bị hủy | Không mang một phần tử dữ liệu kiểu `Void` để `map` hoặc `doOnNext` xử lý |

Điểm tinh tế: **trả về `Mono<Void>` không đồng nghĩa response không có body**. Body có thể được ghi trong các thành phần downstream bằng `response.writeWith(...)` hoặc codec WebFlux; `Mono<Void>` chỉ biểu thị quá trình xử lý/ghi response đã hoàn tất về mặt reactive.

## 3. Ý nghĩa chính xác của chain.filter(exchange)

Trong chữ ký của `GlobalFilter` và `GatewayFilter`:

~~~java
Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain);
~~~

`chain.filter(exchange)` tạo ra phần tiếp theo của pipeline xử lý cho exchange được truyền vào. Khi pipeline có subscriber do WebFlux quản lý, công việc thực tế được thực thi theo ngữ nghĩa Reactor; kết quả hoàn tất, lỗi hoặc hủy được truyền ngược lên các filter bao ngoài.

~~~mermaid
sequenceDiagram
    participant Framework as WebFlux runtime
    participant A as Filter A
    participant B as Filter B
    participant R as Routing/handler

    Framework->>A: filter(exchange, chain)
    A->>A: pre A
    A->>B: chain.filter(exchange)
    B->>B: pre B
    B->>R: chain.filter(exchange)
    R-->>B: Publisher completes
    B->>B: post B
    B-->>A: Mono<Void> completes
    A->>A: post A
    A-->>Framework: Completion signal
~~~

Cần phân biệt **gọi phương thức để tạo/ghép publisher** và **publisher được subscribe**. Trong nhiều đoạn code Reactor, việc thực hiện I/O hoặc gọi xử lý bất đồng bộ được trì hoãn đến subscription. Tuy nhiên, những lệnh Java đặt **trực tiếp trước** `return chain.filter(exchange)` có thể được thực thi ngay khi phương thức `filter` được gọi. Khi cần dời cả bước tạo tác vụ sang lúc subscribe, có thể dùng `Mono.defer(...)` có chủ đích.

Mẫu cơ bản, đúng và dễ đọc nhất:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    // Pre: kiểm tra/chuẩn bị những gì cần thiết cho request.
    return chain.filter(exchange);
}
~~~

**Không gọi `chain.filter(exchange)` chỉ để lấy tác dụng phụ rồi bỏ kết quả.** Mono không được subscribe một cách đúng đắn thì công việc phía sau có thể không chạy. Framework cần nhận lại publisher để điều phối vòng đời request, lỗi và hủy.

## 4. Viết GlobalFilter có xử lý pre và post

Giả sử ta muốn đo thời gian từ khi filter bắt đầu xử lý tới khi chuỗi kết thúc. Một `GlobalFilter` đơn giản:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class GatewayTimingFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(GatewayTimingFilter.class);

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        long startedAt = System.nanoTime(); // Pre

        return chain.filter(exchange)
                .doOnError(error ->
                        log.warn("Gateway processing failed: {}",
                                error.getClass().getSimpleName()))
                .doFinally(signal -> {
                    long durationMs = TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - startedAt);
                    log.info("Gateway finished: signal={}, durationMs={}",
                            signal, durationMs);
                });
    }
}
~~~

**Đường đi của mã:**

1. `startedAt` ghi nhận thời điểm bắt đầu khi filter được gọi.
2. `chain.filter(exchange)` tiếp tục chuỗi và trả về `Mono<Void>`.
3. `doOnError` nhận tín hiệu lỗi truyền qua publisher nhưng **không tự nuốt lỗi**.
4. `doFinally` chạy khi chuỗi phát tín hiệu kết thúc, lỗi hoặc bị hủy. Nó thích hợp để ghi thời gian hoặc dọn tài nguyên được quản lý riêng.

Trong Reactor, tín hiệu `doFinally` có thể là `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. Khi client ngắt kết nối giữa response dài, luồng có thể nhận tín hiệu hủy; **không nên chỉ ghi nhận request hoàn tất thành công**. Thời gian đo ở đây là thời gian publisher hoạt động tại vị trí filter, không nhất thiết bằng thời gian client đã tiêu thụ hết mọi byte sau khi hệ điều hành ghi ra socket.

Nếu đã có Micrometer/Actuator và gateway metrics, hãy ưu tiên hệ thống quan sát có sẵn cho các chỉ số như latency, route ID, status và tracing; ví dụ trên nhằm làm rõ ý nghĩa vòng đời của `chain.filter(exchange)`.

## 5. Phần post không phải câu lệnh đặt ngay sau chain.filter

Đoạn code sau **sai ý định** nếu tác giả muốn ghi log sau khi downstream hoàn thành:

~~~java
Mono<Void> downstream = chain.filter(exchange);
log.info("Downstream finished"); // Có thể chạy trước khi downstream hoàn tất!
return downstream;
~~~

Lệnh `log.info` chạy ngay sau khi lấy publisher, còn quá trình downstream có thể chưa hoàn tất. Thay vào đó, gắn hành động với tín hiệu Reactor:

~~~java
return chain.filter(exchange)
        .doOnSuccess(ignored -> log.info("Completed successfully"))
        .doOnError(error -> log.warn("Processing failed", error))
        .doFinally(signal -> log.debug("Final signal: {}", signal));
~~~

`Mono<Void>` không phát giá trị cho `doOnNext`. Khi thành công, `doOnSuccess` vẫn được gọi nhưng tham số nhận được thường là `null` vì Mono hoàn tất rỗng. Nếu bạn chỉ muốn chạy một công việc reactive **sau khi downstream hoàn thành thành công**, có thể dùng:

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                log.info("Run only after successful downstream completion")));
~~~

Với `then(...)`, publisher downstream hoàn tất thành công thì bước tiếp theo mới được chạy; nếu upstream lỗi thì lỗi truyền qua, nếu bị hủy thì không chạy phần tiếp theo. `doFinally` khác ở chỗ nó quan sát được cả cancellation. **Không đặt công việc blocking lâu trong các callback**, vì chúng có thể thực thi trên event-loop của Reactor Netty.

### Vì sao không dùng switchIfEmpty để viết post?

`Mono<Void>` hoàn tất **không phát phần tử** trong điều kiện thành công, nên:

~~~java
// Ví dụ dễ gây hiểu nhầm:
return chain.filter(exchange)
        .switchIfEmpty(someAlternativeMono);
~~~

`switchIfEmpty` xem hoàn tất bình thường của `Mono<Void>` là kết quả rỗng và có thể thực thi phương án thay thế ở **mọi lần thành công**, không phải chỉ khi “route không khớp”. Đây không phải cách xây fallback HTTP cho Gateway. Hãy dùng ngữ nghĩa lỗi hoặc cơ chế CircuitBreaker/fallback phù hợp.

## 6. Truyền một ServerWebExchange đã được thay đổi

Một filter có thể cần chuẩn hóa request header hoặc thêm thông tin đáng tin cậy trước khi forward. Thay vì cố gắng sửa trực tiếp request hiện tại, dùng cơ chế **mutate/decorator** của Spring WebFlux rồi truyền **exchange mới được bọc** vào chuỗi:

~~~java
import java.util.UUID;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class GatewayRequestIdFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -200;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String requestId = UUID.randomUUID().toString();

        ServerHttpRequest request = exchange.getRequest().mutate()
                .headers(headers -> {
                    headers.remove("X-Gateway-Request-Id");
                    headers.set("X-Gateway-Request-Id", requestId);
                })
                .build();

        ServerWebExchange updated = exchange.mutate()
                .request(request)
                .build();

        return chain.filter(updated);
    }
}
~~~

Đoạn này tạo một ID mới và thay thế header `X-Gateway-Request-Id` do client có thể gửi trước đó. Đây chỉ là ví dụ về **truyền exchange đã thay đổi**, không phải toàn bộ giải pháp distributed tracing. Tracing chuẩn nên sử dụng context propagation/instrumentation có sẵn; cần chính sách rõ ràng cho trace ID, header tin cậy và log.

Điểm cốt lõi là:

~~~java
return chain.filter(updated);
~~~

Nếu bạn tạo `updated` nhưng lại gọi `chain.filter(exchange)`, các filter và handler phía sau sẽ nhận **exchange cũ**, nên không thấy request header mới. Hai đối tượng exchange có thể chia sẻ response/attributes nền tùy cơ chế decorator, nhưng request view đã mutate chỉ được chuyển tới downstream khi truyền đúng biến.

### Thay đổi path thì sao?

Có thể mutate request path nếu thực sự hiểu yêu cầu, nhưng với route thông thường nên dùng các filter có sẵn như `StripPrefix` hoặc `RewritePath`, vì Gateway còn quản lý URL đích trong các **exchange attributes** dùng bởi routing filters. Chỉ sửa path trên `ServerHttpRequest` tùy ý rồi giả định URL proxy cũng được cập nhật có thể dẫn tới sai lệch. Cần kiểm chứng cả path client gửi, path sau filter và URL backend nhận.

## 7. Gắn header response đúng thời điểm

Khi downstream đã ghi response, header có thể **được commit** và không thể sửa an toàn. Vì vậy đoạn code này không đáng tin cậy:

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                exchange.getResponse().getHeaders()
                        .set("X-Gateway-Processed", "true")));
~~~

Khi phần `then` chạy, downstream có thể đã gửi header và body. Nếu mục tiêu là gắn response header **trước khi ghi**, hãy đăng ký callback `beforeCommit` trước khi đi tiếp:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    exchange.getResponse().beforeCommit(() -> {
        exchange.getResponse().getHeaders()
                .set("X-Gateway-Processed", "true");
        return Mono.empty();
    });

    return chain.filter(exchange);
}
~~~

Callback `beforeCommit` được dùng để điều chỉnh response ngay trước lúc commit. Đừng đưa I/O chặn luồng hoặc thao tác tốn thời gian vào callback. Nếu downstream đã commit response ở thời điểm bạn cố đăng ký callback, việc thêm header có thể không còn tác dụng; vì vậy phải đăng ký **trước** khi chuyển tiếp.

Trong cùng ứng dụng, nhiều filter có thể cùng sửa một header. Hãy xác định rõ nguồn sở hữu và thứ tự cập nhật để tránh hai filter ghi đè lẫn nhau. Các header bảo mật như `Strict-Transport-Security`, `Access-Control-Allow-Origin` hoặc header liên quan identity cần cấu hình bởi chính sách phù hợp, không sao chép vô điều kiện từ client.

## 8. Khi nào cố ý không gọi chain.filter(exchange)?

**Short-circuit** là trường hợp filter quyết định kết thúc request ngay, ví dụ request vi phạm chính sách, vượt giới hạn lưu lượng hoặc thiếu điều kiện cần thiết. Khi đó filter có thể ghi response trực tiếp và **không gọi phần còn lại của chuỗi**.

Ví dụ tối giản từ chối HTTP TRACE trong một filter:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    if (HttpMethod.TRACE.equals(exchange.getRequest().getMethod())) {
        exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
        return exchange.getResponse().setComplete();
    }

    return chain.filter(exchange);
}
~~~

Hai nhánh khác nhau:

- Nếu method là `TRACE`, filter trả publisher hoàn tất response `403`, không định tuyến đến upstream.
- Nếu không phải `TRACE`, filter gọi `chain.filter(exchange)` như bình thường.

Đoạn mã giả định các import `HttpMethod` và `HttpStatus` từ Spring HTTP và được đặt trong một filter phù hợp; chỉ minh họa cơ chế short-circuit. Trong ứng dụng thật, các chính sách xác thực/phân quyền nên dựa trên Spring Security, rate limiting nên dùng thành phần chuyên trách khi phù hợp.

~~~mermaid
flowchart TD
    R[Request vào filter] --> Q{Có vi phạm quy tắc?}
    Q -->|Có| S[Thiết lập status / body]
    S --> T[return response.setComplete]
    Q -->|Không| N[return chain.filter(exchange)]
    N --> U[Filter tiếp theo và routing]
~~~

**Dừng chuỗi có nghĩa là không gọi downstream**, không đồng nghĩa toàn bộ các filter đã chạy trước đó “biến mất”. Các filter bao ngoài vẫn nhận tín hiệu thành công/lỗi/hủy của publisher mà filter short-circuit trả về. Vì vậy một metric hoặc `doFinally` ở filter ngoài vẫn có thể ghi nhận request bị từ chối.

Nếu muốn trả JSON thay vì response rỗng, filter phải đặt status/content type và **ghi body** bằng API reactive tương ứng, rồi trả về chính publisher ghi body; không trả `Mono.empty()` ngay sau khi bắt đầu ghi mà chưa nối tác vụ ghi response vào pipeline.

## 9. Những lỗi khiến chuỗi không được tiếp tục đúng cách

| Mẫu code hoặc hành vi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `chain.filter(exchange); return Mono.empty();` | Bỏ publisher downstream, request có thể không được xử lý | `return chain.filter(exchange);` |
| `chain.filter(exchange).subscribe(); return Mono.empty();` | Tạo subscription riêng ngoài vòng đời HTTP, dễ gây race/lỗi bỏ sót | Trả publisher cho framework quản lý |
| `chain.filter(exchange).block();` | Chặn event-loop, có thể gây deadlock hoặc lỗi blocking | Ghép pipeline bằng Reactor operators |
| `chain.filter(exchange)` gọi hai lần | Có thể chạy filter/routing lặp, tạo hai request upstream hoặc sai response | Chỉ gọi một lần mỗi đường xử lý có chủ đích |
| Tạo `updated` nhưng gọi `chain.filter(exchange)` | Downstream không nhận request đã mutate | `chain.filter(updated)` |
| Log “đã xong” ngay sau khi lấy `Mono` | Log trước khi I/O thực sự hoàn tất | Dùng `doOnSuccess`, `doOnError`, `doFinally` |
| Dùng `doOnNext` với `Mono<Void>` | Không quan sát được completion | Dùng `doOnSuccess` hoặc `doFinally` |
| Sửa response header trong post khi response đã commit | Header không được gửi hoặc gây lỗi | Đăng ký `beforeCommit` từ pha pre |
| Bắt lỗi rồi trả `Mono.empty()` không phản hồi rõ | Có thể biến lỗi thành kết thúc không có ngữ nghĩa HTTP mong muốn | Trả lỗi/trạng thái phù hợp theo contract |
| Body filter đọc toàn nội dung chỉ để kiểm tra một header | Tốn bộ nhớ, có thể làm hỏng streaming | Đọc header trực tiếp; tránh tiêu thụ body nếu không cần |

Một lỗi rất khó phát hiện là:

~~~java
return chain.filter(exchange)
        .onErrorResume(error -> Mono.empty());
~~~

Đoạn này **nuốt toàn bộ lỗi** từ downstream và thay bằng completion, trong khi response có thể chưa có status/body đúng. Nếu đã gửi một phần body, việc nuốt lỗi còn khiến khó quan sát lỗi giữa luồng. Chỉ dùng `onErrorResume` khi có chính sách fallback cụ thể, có phản hồi hợp lệ và biết response đã commit hay chưa.

## 10. Error, cancel và sự kiện response đã commit

Các filter có thể quan sát ba kết cục chính của publisher downstream:

| Kết cục | Tín hiệu Reactor | Ý nghĩa thường gặp |
| --- | --- | --- |
| Hoàn tất | `onComplete` | Chuỗi xử lý kết thúc theo đường thành công, có thể gồm short-circuit |
| Lỗi | `onError` | Một bước downstream phát lỗi; cơ chế xử lý lỗi có thể trả status hoặc đóng kết nối |
| Hủy | `cancel` | Subscriber không cần tiếp tục, ví dụ client đóng kết nối |

**Không có bảo đảm mọi lỗi downstream sẽ cho ra response mới tùy ý.** Với HTTP, sau khi header và byte đầu tiên được gửi, response đã commit; Gateway không thể quay ngược thay toàn bộ status thành `500` hoặc `503`. Điều này đặc biệt quan trọng khi proxy SSE, NDJSON, download tệp hoặc upload lớn.

Ví dụ một nhánh lỗi có kiểm tra trạng thái response, chỉ để minh họa:

~~~java
return chain.filter(exchange)
        .onErrorResume(error -> {
            if (exchange.getResponse().isCommitted()) {
                return Mono.error(error);
            }
            exchange.getResponse()
                    .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
            return exchange.getResponse().setComplete();
        });
~~~

**Không sử dụng mẫu này làm bộ xử lý lỗi chung trong production.** Nó đang biến **mọi lỗi** thành 503, bao gồm lỗi lập trình, lỗi xác thực hoặc request không hợp lệ; điều này sai ngữ nghĩa. Một implementation thực tế phải phân loại lỗi, tôn trọng các status cần thiết, ghi metric, tránh lộ thông tin và cân nhắc các filter/cơ chế xử lý lỗi có sẵn của Gateway.

**Retry và CircuitBreaker** cũng hoạt động thông qua việc bao bọc publisher downstream. Cấu hình retry phải chú ý idempotency: retry một POST tạo đơn hàng hoặc thanh toán có thể tạo tác dụng phụ trùng nếu không có cơ chế an toàn. Với response stream đã gửi một phần, chạy lại pipeline không thể đảm bảo client nhận đúng một chuỗi sự kiện không trùng; cần thiết kế resume/idempotency ở cấp ứng dụng.

## 11. Thứ tự filter quyết định pre và post

Spring Cloud Gateway kết hợp `GlobalFilter` và `GatewayFilter` của route thành một chuỗi rồi sắp xếp theo `Ordered` hoặc cơ chế order tương ứng. **Số order nhỏ hơn thường có độ ưu tiên cao hơn khi đi vào**.

Giả sử:

| Filter | Order | Pre | Post |
| --- | ---: | ---: | ---: |
| A | -100 | 1 | 3 |
| B | 0 | 2 | 2 |
| C | 100 | 3 | 1 |

~~~mermaid
flowchart LR
    A1[A pre] --> B1[B pre]
    B1 --> C1[C pre]
    C1 --> R[Routing / response work]
    R --> C2[C post]
    C2 --> B2[B post]
    B2 --> A2[A post]
~~~

Filter A có order nhỏ nhất nên có thể chạy **sớm nhất ở pre** và **cuối cùng ở post** khi post được gắn vào publisher downstream. Vì vậy không nên chọn order chỉ dựa vào mong muốn chạy “sớm” hoặc “muộn” mà bỏ qua cả hai pha.

**Cần phân biệt thứ tự:**

- **Route order** quyết định route nào được xét trước khi nhiều route cùng khớp predicate.
- **Filter order** quyết định vị trí của filter trong chuỗi **sau khi route đã được chọn**.
- Các bộ lọc tích hợp như routing, metrics, write response hoặc load balancing có order riêng. Nếu custom filter phụ thuộc chúng, kiểm tra đúng thứ tự và các attributes mà filter đó cần theo phiên bản Gateway đang chạy.

Một `GlobalFilter` chạy trong pipeline của **các request đã được Gateway route**, không có nghĩa nó tự động áp dụng cho **mọi** request Spring WebFlux của ứng dụng. Nếu cần chính sách cho các WebFlux endpoint cục bộ ngoài Gateway, hãy xem `WebFilter` hoặc Spring Security WebFlux với phạm vi áp dụng thích hợp. Đừng nhầm `GatewayFilterChain` với `WebFilterChain`.

## 12. GatewayFilter theo route cũng phải tiếp tục chain

Không chỉ `GlobalFilter`, một `GatewayFilter` gắn vào route cụ thể cũng nhận cùng kiểu tham số. Ví dụ dùng Java Route DSL:

~~~java
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.server.reactive.ServerHttpRequest;

@Configuration
class RouteConfiguration {

    @Bean
    RouteLocator catalogRoutes(RouteLocatorBuilder builder) {
        return builder.routes()
                .route("catalog", r -> r.path("/api/catalog/**")
                        .filters(f -> f.filter((exchange, chain) -> {
                            ServerHttpRequest request = exchange.getRequest()
                                    .mutate()
                                    .header("X-Gateway-Section", "catalog")
                                    .build();
                            return chain.filter(
                                    exchange.mutate().request(request).build());
                        }))
                        .uri("lb://catalog-service"))
                .build();
    }
}
~~~

Route trên dùng predicate `Path=/api/catalog/**`, một filter thêm request header và URI `lb://catalog-service`. Filter này được dùng **khi route catalog được chọn**, thay vì áp dụng toàn cục cho tất cả route.

`lb://` yêu cầu hạ tầng load balancing/phân giải service phù hợp (ví dụ Spring Cloud LoadBalancer và service discovery được cấu hình). Đối với bài thử nhỏ, có thể dùng `http://localhost:9001` nếu đã khởi chạy backend trên cổng đó. Đoạn mã minh họa cách nối `chain.filter(exchange)`, chưa bao gồm dependency, project và backend hoàn chỉnh.

Nếu chỉ cần thêm hoặc xóa header đơn giản, ưu tiên **GatewayFilterFactory có sẵn** như `AddRequestHeader`, `SetRequestHeader`, `RemoveRequestHeader` thay vì tự viết Java filter. Tự viết filter hữu ích khi cần logic có điều kiện, trạng thái/request context hoặc tích hợp đặc biệt.

### Vì sao không gắn header tùy ý cho thông tin danh tính?

Nếu downstream tin `X-User-Id` hoặc `X-Role`, tuyệt đối không tự chuyển tiếp header do client kiểm soát rồi coi là đã xác thực. Gateway phải lấy danh tính từ nguồn tin cậy, giới hạn quyền được truyền và thiết lập ranh giới mạng bảo vệ. Filter thêm header minh họa ở trên dùng giá trị cố định **catalog** và không nhằm cấp quyền.

## 13. Đừng vô tình tiêu thụ request body trước khi gọi chain

`ServerWebExchange` chứa request body dưới dạng publisher, thường ở mức thấp là `Flux<DataBuffer>`. Với dữ liệu streaming, việc đọc body trong filter có thể làm downstream không còn dữ liệu hoặc phải đệm toàn bộ vào RAM.

Một mẫu **không nên làm** để log body:

~~~java
// Không dùng: tự subscribe có thể tiêu thụ luồng body trước downstream.
exchange.getRequest().getBody()
        .subscribe(buffer -> log.debug("Received body chunk"));
return chain.filter(exchange);
~~~

Đoạn code này tạo subscription riêng, không quản lý ownership của `DataBuffer` và không chuyển đúng tín hiệu lỗi/hủy vào chuỗi Gateway. Nếu một request body chỉ được tiêu thụ một lần, downstream có thể nhận dữ liệu thiếu hoặc lỗi.

Mẫu nguy hiểm khác:

~~~java
// Không dùng cho body lớn/vô hạn chỉ để log.
Mono<DataBuffer> combined =
        DataBufferUtils.join(exchange.getRequest().getBody());
~~~

`DataBufferUtils.join(...)` gom body thành một buffer; muốn dùng phải hiểu hạn mức kích thước và quy tắc retain/release của DataBuffer. Với upload lớn, SSE, NDJSON hoặc body streaming, việc gom toàn bộ phá vỡ ưu điểm xử lý theo luồng. Nếu cần biến đổi nội dung, hãy cân nhắc bộ lọc body có sẵn, codec, decorator và giới hạn kích thước; kiểm thử hành vi end-to-end.

Trong những tình huống chỉ cần kiểm tra header, path, method hoặc attribute, **không đọc body**. Cứ để:

~~~java
return chain.filter(exchange);
~~~

đưa body tới thành phần proxy/handler đã được thiết kế để tiêu thụ và phát dữ liệu bất đồng bộ.

## 14. Kiểm thử chain có được gọi và Mono có hoàn tất không

Một bài kiểm thử đơn vị cho filter nhỏ có thể tạo `MockServerWebExchange`, tự định nghĩa một `GatewayFilterChain` giả và sử dụng Reactor `StepVerifier`. Ví dụ với `GatewayRequestIdFilter` ở phần 6:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayRequestIdFilterTest {

    @Test
    void forwardsMutatedExchangeToNextFilter() {
        GatewayRequestIdFilter filter = new GatewayRequestIdFilter();
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/items")
                        .header("X-Gateway-Request-Id", "untrusted")
                        .build());

        AtomicReference<String> observedId = new AtomicReference<>();

        GatewayFilterChain next = forwardedExchange -> {
            observedId.set(forwardedExchange.getRequest()
                    .getHeaders().getFirst("X-Gateway-Request-Id"));
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, next))
                .verifyComplete();

        assertThat(observedId.get())
                .isNotBlank()
                .isNotEqualTo("untrusted");
    }
}
~~~

Đây là **test minh họa**, cần đặt đúng source set kiểm thử và có dependency `spring-test`, `reactor-test`, JUnit 5, AssertJ tương thích. Nó xác minh filter thật sự truyền request đã mutate cho mắt xích tiếp theo và publisher kết thúc thành công. Nó **chưa chứng minh** HTTP routing, security, timeout hay backend hoạt động.

### Kiểm tra thêm điều kiện short-circuit

Viết hai trường hợp kiểm thử cho filter từ chối `TRACE` ở phần 8:

1. Request `TRACE`: dùng một `AtomicBoolean` đánh dấu khi `next.filter` được gọi; mong đợi cờ **false**, response được kết thúc và status là 403.
2. Request `GET`: mong đợi `next.filter` được gọi **đúng một lần** và publisher hoàn tất.

Đối với filter có phần xử lý post, dùng publisher downstream có thể kiểm soát completion hoặc lỗi để kiểm tra callback được gọi **đúng lúc**; đừng chỉ kiểm tra return object khác null. Nếu cần kiểm thử hành vi thực của Gateway, viết integration test với route thật và backend stub rồi xác minh response, route ID, header/path chuyển tiếp và các trường hợp lỗi.

## 15. Tình huống thực hành: thêm dấu vết rồi chặn request có chủ đích

Giả sử một gateway cho các microservice Catalog và Orders cần hai khả năng: gắn request ID tin cậy cho request đi qua gateway và ghi nhận thời gian xử lý; đồng thời một endpoint quản trị có thể bị từ chối sớm theo chính sách Spring Security.

### Phần A — Xây filter tiếp tục chuỗi

1. Dùng `GatewayRequestIdFilter` ở phần 6; kiểm tra khi client gửi `X-Gateway-Request-Id: untrusted`, upstream nhận một ID mới.
2. Dùng `GatewayTimingFilter` ở phần 4; phát request thành công và request gây lỗi, quan sát `doFinally` và latency.
3. Định nghĩa route tới service với `lb://` hoặc URI HTTP cố định. Bảo đảm route predicate khớp và request được chuyển tiếp.

### Phần B — Quan sát một lần short-circuit

1. Thêm filter thử nghiệm từ chối `TRACE` với status 403, không gọi `chain.filter(exchange)` ở nhánh từ chối.
2. Gửi request thường và xác minh backend được gọi.
3. Gửi request bị chặn và xác minh backend **không nhận request**.
4. Kiểm tra filter timing ở ngoài vẫn nhận tín hiệu kết thúc; phân biệt request bị chặn với request upstream lỗi.

### Phần C — Tìm lỗi do Reactor lifecycle

Thử ở môi trường kiểm thử, sau đó **sửa về cách đúng**:

| Thử nghiệm | Hiện tượng cần quan sát |
| --- | --- |
| Quên `return chain.filter(exchange)` | Downstream không được thực thi như mong đợi |
| Gọi `subscribe()` thủ công | Pipeline thoát khỏi vòng đời HTTP; lỗi/response khó kiểm soát |
| Log ngay sau khi lấy Mono | Thời điểm log khác thời điểm response hoàn tất |
| Sửa header trong post sau khi response commit | Header có thể không xuất hiện trong response |
| Mutate request nhưng truyền exchange cũ | Backend không nhận header được thêm |
| Dùng `doOnNext` để đếm số lần hoàn tất | Không chạy trên `Mono<Void>` hoàn tất rỗng |
| Client hủy response streaming giữa chừng | `doFinally` có thể nhận `CANCEL` |

### Phần D — Tiêu chí đạt

Hãy xác minh bằng log/metrics và backend thử nghiệm rằng:

- Route được chọn đúng; filter thuộc route hoặc toàn cục được áp dụng đúng phạm vi.
- `chain.filter(updatedExchange)` chuyển thay đổi tới downstream.
- Mỗi đường xử lý bình thường chỉ tiếp tục chuỗi **một lần**; đường short-circuit không tiếp tục.
- Phần pre/post/error/cancel được đo đúng thời điểm; không block event-loop.
- Không log token, cookie hoặc toàn bộ body; backend vẫn nhận request body đầy đủ khi cần.
- Response header được gắn trước lúc commit, không tạo lỗi khi response đã bắt đầu truyền.

## 16. Tổng kết

- **`return chain.filter(exchange);`** là thao tác cơ bản để một Gateway filter **chuyển request tới phần còn lại của chuỗi**, đồng thời trả về publisher cho WebFlux điều phối.
- `Mono<Void>` biểu thị **hoàn tất bất đồng bộ** của pipeline; dùng `doOnSuccess`, `doOnError`, `doFinally` hoặc `then` để xây logic post phù hợp. Đừng dùng `doOnNext` hoặc `switchIfEmpty` sai ý nghĩa.
- Khi thay đổi request, phải truyền đúng **exchange đã mutate** vào `chain.filter(updated)`. Muốn sửa response header, chuẩn bị **trước commit**, ví dụ bằng `beforeCommit`.
- **Short-circuit** là chủ ý không gọi downstream mà tự hoàn tất response; phải có chính sách và status/body đúng, tránh dùng nó để che lỗi.
- **Thứ tự filter** quyết định thứ tự xử lý pre và post; GlobalFilter khác WebFilter và khác GatewayFilter gắn riêng vào route.
- Không tự `subscribe()`, `block()`, gọi chain hai lần hoặc tiêu thụ body tùy tiện trong filter. Đây là nền tảng để API Gateway dùng Spring Cloud Gateway giữ được tính đúng đắn, hiệu năng, bảo mật và khả năng quan sát khi phục vụ microservices.
