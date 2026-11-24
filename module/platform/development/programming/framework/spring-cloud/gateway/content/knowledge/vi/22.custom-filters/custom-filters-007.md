# Xử lý trước, sau, lỗi và hủy trong một chuỗi Reactor

## 1. Vì sao cần hiểu vòng đời reactive khi viết bộ lọc tùy biến?

Trong **Spring Cloud Gateway**, request đi vào hệ thống sẽ được chọn route bằng các route predicates (như `Path`, `Method`, `Header`), sau đó qua filter chain để xử lý xác thực, giới hạn lưu lượng, biến đổi path/header, chọn instance bằng `lb://`, kết nối HTTP(S), retry, circuit breaker và trả response. Người phát triển có thể bổ sung **GatewayFilter** hoặc **GlobalFilter** để đo thời gian, bổ sung header, kiểm tra quy tắc riêng hoặc ghi nhận sự kiện.

Nhưng Gateway Server WebFlux dựa trên **Reactor**: một phương thức filter trả về `Mono<Void>` thay vì thực hiện toàn bộ request một cách đồng bộ ngay tại thời điểm được gọi. Nếu nhầm việc **tạo Publisher** với việc **Publisher được subscribe và thực thi**, custom filter có thể:

- Ghi log “thành công” khi downstream còn chưa bắt đầu.
- Bỏ sót request bị hủy khi client ngắt kết nối.
- Ghi đè lỗi 401/403 hoặc biến 503 thành 200 sai hợp đồng.
- Thử sửa response sau khi headers đã được gửi.
- Gọi `subscribe()` hoặc `block()` gây mất kiểm soát vòng đời và nghẽn event loop.
- Giữ `DataBuffer` hoặc tài nguyên khác sau khi cancel, dẫn đến memory leak.
- Đo sai latency khi có retry, circuit breaker hoặc streaming.

Bài **“Xử lý trước, sau, lỗi và hủy trong một chuỗi Reactor”**, thuộc chương **Bộ lọc tùy biến**, giúp hiểu cách thiết kế một bộ lọc tuân theo vòng đời bất đồng bộ của **Spring Cloud Gateway Server WebFlux**. Các ví dụ tập trung vào `GlobalFilter`, `GatewayFilter`, `GatewayFilterChain`, `ServerWebExchange` và `Mono<Void>`.

Sau bài học, bạn có thể:

1. Phân biệt phần xử lý **pre** và **post**, kể cả khi nhiều filters có order khác nhau.
2. Giải thích các tín hiệu Reactor **onSubscribe**, **onComplete**, **onError** và **cancel** trong một `Mono<Void>`.
3. Dùng `Mono.defer`, `doOnSubscribe`, `doOnSuccess`, `doOnError`, `doOnCancel` và `doFinally` đúng mục đích.
4. Dùng `onErrorResume` có điều kiện mà không che lỗi bảo mật hoặc trả response sau commit.
5. Đăng ký `ServerHttpResponse.beforeCommit` để chỉnh response headers trước thời điểm commit.
6. Kiểm thử thứ tự, thành công, lỗi và hủy bằng **StepVerifier** hoặc test HTTP tích hợp.
7. Áp dụng nguyên tắc non-blocking, bảo vệ dữ liệu nhạy cảm, context propagation và dọn tài nguyên khi kết thúc.

> **Phạm vi:** Bài áp dụng cho **Spring Cloud Gateway Server WebFlux** (Reactor Netty), không phải biến thể Server Web MVC. API và package có thể khác theo phiên bản Spring Boot/Spring Cloud. Các snippets là ví dụ học tập và cần được tích hợp với dependencies, bảo mật và tests của dự án thực tế.

## 2. Một filter có hai pha logic: trước và sau downstream

Interface cơ bản:

~~~java
public interface GatewayFilter {
    Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain);
}
~~~

Một `GlobalFilter` có cùng ý tưởng nhưng áp dụng cho những Gateway routes đủ điều kiện:

~~~java
public interface GlobalFilter {
    Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain);
}
~~~

Trong một implementation thông thường, `chain.filter(exchange)` trả Publisher đại diện cho công việc của **phần filter chain còn lại**. Filter có thể làm công việc trước khi gọi nó (**pre**), gắn operators để xử lý sau khi nó kết thúc (**post**) hoặc quan sát lỗi/hủy.

~~~mermaid
flowchart TD
    Client["Client HTTP request"] --> Security["WebFlux / Spring Security filters"]
    Security --> Route["Chọn Gateway route"]
    Route --> F1pre["GlobalFilter A: pre"]
    F1pre --> F2pre["GatewayFilter B: pre"]
    F2pre --> F3pre["GlobalFilter C: pre"]
    F3pre --> Routing["Load balancer + HTTP routing"]
    Routing --> F3post["GlobalFilter C: post"]
    F3post --> F2post["GatewayFilter B: post"]
    F2post --> F1post["GlobalFilter A: post"]
    F1post --> Client
~~~

Đây là mô hình **lồng nhau**. Nếu A chạy pre trước B, phần post của A thường được kích hoạt sau phần post của B, giống như mở và đóng các lớp bao.

### Thứ tự được quyết định bởi order

Gateway kết hợp GlobalFilters và GatewayFilters thành một chuỗi có thứ tự. Thành phần có độ ưu tiên cao hơn (giá trị order nhỏ hơn) thường được thực thi **sớm hơn ở pha pre** và **muộn hơn ở pha post**. Tuy nhiên, **các toán tử Reactor cũng quyết định thời điểm nhận tín hiệu**, nên không được suy diễn hoàn toàn từ thứ tự khai báo trong YAML.

| Filter | Order minh họa | Pha pre | Pha post khi downstream complete |
| --- | ---: | ---: | ---: |
| A | -100 | 1 | 3 |
| B | 0 | 2 | 2 |
| C | 100 | 3 | 1 |

Lưu ý: Bảng là **hình dung thứ tự**, không phải mọi callback luôn chạy khi downstream lỗi hoặc bị hủy. `then(... )` chỉ chạy tiếp khi chuỗi trước hoàn tất thành công; `doFinally` nhận cả complete, error và cancel.

### Ví dụ ngắn: pre và post cho trường hợp thành công

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    // Pha chuẩn bị; được thực thi khi filter(...) được gọi.
    long startNanos = System.nanoTime();

    return chain.filter(exchange)
            .then(Mono.fromRunnable(() -> {
                long elapsedNanos = System.nanoTime() - startNanos;
                // Việc không blocking, sau khi downstream hoàn tất thành công.
                recordSuccessDuration(elapsedNanos);
            }));
}
~~~

Đoạn trên chỉ là **phác thảo**, với `recordSuccessDuration` là hàm giả định. `then(Mono.fromRunnable(...))` **không chạy khi downstream phát lỗi hoặc bị cancel**. Ngoài ra, ghi `startNanos` trước khi Publisher được subscribe có thể bao gồm thời gian chờ giữa **lúc tạo chain** và **lúc thực thi**, nếu có. Khi cần dữ liệu riêng cho mỗi subscription, dùng `Mono.defer`.

## 3. Reactor là Publisher có vòng đời, không phải một lời gọi đồng bộ

`Mono<Void>` thể hiện một tiến trình phát tối đa một giá trị, nhưng với generic `Void` thì trong mô hình bình thường **không có payload `onNext`** để sử dụng. Nó có thể:

- Được subscribe rồi **hoàn tất thành công** (`onComplete`).
- Được subscribe rồi **thất bại** (`onError(Throwable)`).
- Bị **cancel** qua `Subscription.cancel()` trước terminal signal.

~~~mermaid
stateDiagram-v2
    [*] --> Created: Tạo Publisher
    Created --> Subscribed: subscribe
    Subscribed --> Completed: onComplete
    Subscribed --> Failed: onError
    Subscribed --> Cancelled: cancel
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

Các trạng thái mô phỏng vòng đời **một subscription**. Cancellation là yêu cầu ngừng gửi tín hiệu từ downstream tới upstream; nó không phải một `onError` mới được gửi đến subscriber, và không đảm bảo mọi I/O/side effect đã bắt đầu đều đảo ngược tức thì.

### Assembly khác subscription

Khi code tạo:

~~~java
Mono<Void> work = chain.filter(exchange)
        .doOnSuccess(ignored -> log.debug("completed"));
~~~

điều chắc chắn là bạn đang **xây một Publisher chain** và trả nó cho WebFlux. Công việc reactive nằm trong Publisher thường chỉ tiến hành **khi có subscription**, nhưng một phương thức Java được gọi để *xây dựng Publisher* vẫn có thể chạy side effect **ngay tại assembly**. Đó là lý do viết `log.info("request complete")` ngay sau `chain.filter(exchange)` là sai:

~~~java
// CHỐNG MẪU: log thành công quá sớm.
Mono<Void> result = chain.filter(exchange);
log.info("Downstream đã hoàn tất"); // Chưa có bảo đảm như vậy.
return result;
~~~

Để trì hoãn cả việc lấy mốc thời gian và tạo Publisher tới lúc subscription, dùng:

~~~java
return Mono.defer(() -> {
    long startNanos = System.nanoTime();
    return chain.filter(exchange)
            .doFinally(signal -> {
                long elapsedNanos = System.nanoTime() - startNanos;
                recordTerminalSignal(signal, elapsedNanos);
            });
});
~~~

Ở ví dụ trên, `recordTerminalSignal` là hàm instrumentation minh họa. **Mỗi subscription** sẽ chạy lại supplier của `Mono.defer`, tạo state cục bộ mới. Nếu muốn thấy mỗi subscription đang gắn với một attempt retry hay một HTTP request, cần biết **operator retry đặt bên ngoài hay bên trong filter**.

### Vì sao không dùng subscribe() trong filter?

~~~java
// SAI: tạo một subscription riêng, không thuộc vòng đời Gateway.
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

Code này có thể trả thành công cho tầng trên **trước khi routing hoàn tất**, tách cancellation/error khỏi request gốc, làm request bị gửi hai lần hoặc rò rỉ tài nguyên. Tương tự, `block()` chặn thread (nguy hiểm trên Reactor Netty event loop) và phá lợi thế non-blocking.

**Quy tắc:** Luôn **trả Publisher** cho framework; compose bằng operators thay vì tự subscribe hay block.

## 4. Bảng chọn operator cho pre, post, error và cancel

| Operator | Khi nào chạy? | Có thay đổi tín hiệu không? | Dùng cho |
| --- | --- | --- | --- |
| `Mono.defer(supplier)` | Mỗi lần Publisher được subscribe | Tạo Publisher mới theo subscription | Bắt đầu timing, gắn state cục bộ, thực thi pre lười |
| `doOnSubscribe(consumer)` | Khi subscription được thiết lập | Không chủ động đổi kết quả | Theo dõi start/subscription |
| `doOnSuccess(consumer)` | Khi `Mono` hoàn tất thành công | Không | Ghi nhận success; với `Mono<Void>` nhận `null` |
| `doOnError(consumer)` | Khi có `onError` | Không, nếu callback không tự ném lỗi | Ghi nhận exception an toàn, metrics lỗi |
| `doOnCancel(runnable)` | Khi downstream yêu cầu cancel | Không chuyển thành HTTP error | Theo dõi cancellation |
| `doFinally(consumer)` | Sau complete, error **hoặc cancel** | Không | Kết thúc timing, cleanup nhẹ, telemetry |
| `then(other)` | Sau khi upstream hoàn tất **thành công** | Chuyển sang Publisher khác | Post-success có công việc reactive cần compose |
| `onErrorResume(mapper)` | Khi upstream phát lỗi | **Có**, thay lỗi bằng publisher thay thế | Fallback hẹp và có kiểm soát |
| `onErrorMap(mapper)` | Khi upstream phát lỗi | **Có**, đổi exception | Chuẩn hóa loại lỗi cần thiết |
| `doOnEach(consumer)` | Khi có các tín hiệu mà operator hỗ trợ | Không | Quan sát tín hiệu cùng Reactor Context |
| `contextWrite(function)` | Gắn/sửa Reactor Context theo hướng subscription | Có ảnh hưởng context | Truyền metadata bất biến, không dùng để chứa token thô |

Các điểm hay nhầm:

- `doOnSuccess` của `Mono<Void>` **không nhận HTTP response body**; argument của nó thường là `null`. Không gọi `ignored.toString()`.
- `doOnError` **chỉ quan sát**. Nó không “bắt” lỗi để response trở thành 200. Muốn xử lý lỗi phải dùng cơ chế như `onErrorResume` có chính sách rõ.
- `doFinally` bao gồm **CANCEL**, nhưng logic trong đó chạy **sau khi tín hiệu terminal/cancel được truyền theo chain**; không nên dựa vào nó để sửa response trước commit.
- `then(...)` không được gọi khi lỗi hoặc cancel. `doOnTerminate` cũng không thay thế xử lý cancel.
- `doOnNext` không phù hợp để quan sát thành công của `Mono<Void>` vì bình thường không phát `onNext`.

### So sánh nhanh ba nhánh kết thúc

~~~text
Downstream -> onComplete:
    doOnSuccess -> then(post work) -> downstream complete -> doFinally(ON_COMPLETE)

Downstream -> onError:
    doOnError -> (onErrorResume nếu có) -> error hoặc fallback -> doFinally(...)

Downstream <- cancel:
    doOnCancel -> upstream cancel/cleanup -> doFinally(CANCEL)
    Không có onComplete/onError cho subscription đã bị cancel.
~~~

Thứ tự callback chi tiết **còn phụ thuộc vị trí operator trong chuỗi**. Nếu `doFinally` đặt trước `onErrorResume`, nó có thể thấy một kết thúc lỗi trong nhánh upstream dù Publisher kết quả tổng đã được fallback phục hồi. Nếu đặt ngoài `onErrorResume`, nó có thể thấy `ON_COMPLETE` sau fallback. Cần chọn vị trí dựa trên **thứ bạn muốn đo**.

## 5. Ví dụ GlobalFilter theo dõi đủ bốn nhánh

Một nhu cầu thực tế là đo thời gian xử lý một route và ghi nhận **thành công**, **lỗi** hoặc **hủy** mà không log dữ liệu nhạy cảm. Ví dụ:

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
        .GATEWAY_ROUTE_ATTR;

@Component
public class SafeLifecycleGlobalFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(SafeLifecycleGlobalFilter.class);

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain
    ) {
        return Mono.defer(() -> {
            long startedAt = System.nanoTime();
            Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
            String routeId = route == null ? "unknown" : route.getId();

            return chain.filter(exchange)
                    .doOnSubscribe(subscription ->
                            log.debug("route={} lifecycle=subscribed", routeId))
                    .doOnSuccess(ignored ->
                            log.debug("route={} lifecycle=success", routeId))
                    .doOnError(error ->
                            log.warn("route={} lifecycle=error errorType={}",
                                    routeId, error.getClass().getSimpleName()))
                    .doOnCancel(() ->
                            log.debug("route={} lifecycle=cancel-requested", routeId))
                    .doFinally(signal -> {
                        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt);
                        HttpStatusCode status =
                                exchange.getResponse().getStatusCode();
                        String statusCode = status == null
                                ? "unknown"
                                : Integer.toString(status.value());

                        log.info(
                                "route={} method={} status={} terminal={} elapsedMs={}",
                                routeId,
                                exchange.getRequest().getMethod(),
                                statusCode,
                                signal,
                                elapsedMs
                        );
                    });
        });
    }
}
~~~

**Giải thích từng lớp:**

1. `Mono.defer` tạo mốc thời gian và biến `routeId` **khi subscription diễn ra**. Nếu Publisher được đăng ký lại do retry ở tầng ngoài, mỗi lần có state riêng.
2. `chain.filter(exchange)` đại diện cho công việc downstream. Filter **không tự gọi `subscribe()`**.
3. `doOnSubscribe` quan sát điểm bắt đầu subscription, hữu ích khi đo số attempts.
4. `doOnSuccess` chạy khi `Mono<Void>` hoàn tất thành công; biến `ignored` sẽ là `null`, không phải response body.
5. `doOnError` chỉ ghi **loại exception**, không in message có thể chứa token, query hoặc URL nội bộ. Lỗi vẫn được truyền tiếp.
6. `doOnCancel` theo dõi yêu cầu hủy từ downstream; không tự biến nó thành HTTP 499/503.
7. `doFinally` chạy cho complete, error **hoặc cancel**, giúp ghi một dòng kết thúc cho subscription. `signal` là `SignalType` như `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`.
8. `getStatusCode()` có thể trả `null` khi response chưa có status rõ ràng. Một status 200 trong response **không chứng minh mọi byte đã tới client**.

Đoạn code này ghi event tối giản. Trong production nên dùng Micrometer/tracing và giới hạn số lượng log bằng sampling phù hợp; không ghi mỗi request thành nhiều dòng DEBUG/INFO khi lưu lượng rất lớn. Với các route được tạo động, phải quản lý route ID để không vô tình đưa dữ liệu do client kiểm soát vào log hoặc metric label.

### Có phải doFinally luôn đồng nghĩa request đã thành công?

**Không.** `doFinally` trả lời “subscription này kết thúc theo tín hiệu nào?”. Ví dụ:

- `ON_COMPLETE`: Publisher hoàn tất bình thường, **nhưng backend có thể đã trả HTTP 503 như một response bình thường**.
- `ON_ERROR`: Publisher đã phát exception; response có thể chưa commit hoặc đã gửi một phần.
- `CANCEL`: downstream hủy; có thể do client disconnect, timeout operator, race hoặc nguyên nhân khác. Không thể luôn biết **client disconnect** chỉ từ tín hiệu CANCEL.

Nếu có `Retry` hoặc `CircuitBreaker`, có thể có **nhiều subscriptions cho một operation**, mỗi cái có tín hiệu riêng. Đừng gọi tổng số `doFinally` bằng số HTTP requests của người dùng nếu chưa kiểm tra vị trí filter.

## 6. Pre-phase đúng: khi nào dùng Mono.defer?

Một custom filter có thể thực hiện phép kiểm tra không blocking rồi quyết định:

~~~java
return Mono.defer(() -> {
    if (!featurePolicyAllows(exchange)) {
        exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
        return exchange.getResponse().setComplete();
    }
    return chain.filter(exchange);
});
~~~

Đây là **mẫu khái niệm**: `featurePolicyAllows` là hàm kiểm tra đã được thiết kế trước, và cần import `HttpStatus` tương ứng. Kiểm tra chính sách nào yêu cầu dữ liệu bất đồng bộ phải compose Publisher thay vì truy vấn blocking. Đặc biệt, **đừng tự thay Spring Security bằng một phép kiểm tra header do client tự khai** cho quyền truy cập admin.

### Tại sao Mono.defer hợp lý?

Nó đảm bảo:

- Pre logic được thực thi **theo subscription**, không tại thời điểm chỉ tạo Publisher.
- Per-attempt state được tạo lại nếu publisher bị resubscribe.
- Exception trong supplier được Reactor chuyển thành `onError` thay vì văng ra như exception đồng bộ tại điểm assembly, trong phạm vi Reactor xử lý supplier.
- Không tạo thao tác có side effect trước khi một request thực sự được thực hiện.

Tuy nhiên, `Mono.defer` **không biến một hàm blocking thành non-blocking**. Nếu `featurePolicyAllows` thực hiện JDBC blocking, gọi REST đồng bộ hoặc `Thread.sleep()`, event loop vẫn có thể bị nghẽn. Cần sử dụng API reactive hoặc cách ly tài nguyên có chủ đích ở lớp phù hợp.

### Pre logic thực hiện I/O bất đồng bộ

Nếu phải lấy dữ liệu từ một nguồn phản ứng bất đồng bộ để xét policy, có thể compose:

~~~java
return policyService.check(exchange)
        .flatMap(allowed -> {
            if (!allowed) {
                exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }
            return chain.filter(exchange);
        });
~~~

Đoạn trên là **mẫu thiết kế**, với `policyService.check(exchange)` là hàm giả định trả `Mono<Boolean>`. Trong hệ thống thực phải có **timeout, cache, error policy và phân quyền rõ** cho dịch vụ policy. Nếu nguồn policy lỗi, không tự mặc định cho phép truy cập vào tài nguyên nhạy cảm; nguyên tắc **fail closed** thường phù hợp.

Không dùng `flatMap` trên `Mono<Void>` để chạy post logic vì nó **không phát giá trị onNext**. Muốn nối một công việc reactive sau khi downstream thành công, dùng `then(...)`.

## 7. Post-phase: sau thành công, trước commit và sau commit

Từ “sau” có thể chỉ **ba thời điểm khác nhau**:

1. Sau khi **downstream Publisher hoàn tất thành công**.
2. **Ngay trước lúc response commit**, trước khi gửi status/headers.
3. Sau khi **response đã commit hoặc đã bắt đầu ghi body**, khi nhiều thay đổi HTTP không còn hợp lệ.

**Không thể thay thế ba thời điểm này cho nhau.**

### 7.1. Post-success với then

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                auditSuccessWithoutSensitiveData(exchange)));
~~~

`auditSuccessWithoutSensitiveData` là hàm giả định, phải nhanh và không blocking. `then` đợi Publisher trước **onComplete** rồi mới subscribe công việc phía sau; nó không chạy khi có `onError` hay cancel.

Lưu ý: ở tầng HTTP, **onComplete không đồng nghĩa HTTP status là 2xx**. Một backend trả 500 có thể tạo response hoàn tất bình thường. Nếu muốn đo “success HTTP”, phải xét status theo policy riêng.

### 7.2. Đăng ký beforeCommit trước khi chạy downstream

Nếu cần thêm response header bằng chính sách Gateway, nên đăng ký callback **trước khi response được ghi**:

~~~java
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class ResponseMarkerFilter implements GlobalFilter, Ordered {
    @Override
    public int getOrder() {
        return -200;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain
    ) {
        return Mono.defer(() -> {
            exchange.getResponse().beforeCommit(() -> {
                exchange.getResponse().getHeaders()
                        .set("X-Gateway-Processed", "true");
                return Mono.empty();
            });

            return chain.filter(exchange);
        });
    }
}
~~~

`beforeCommit` đăng ký `Supplier<Mono<Void>>` được gọi trước khi response commit. Callback phải cung cấp Publisher phù hợp, không tự subscribe và không blocking. Header `X-Gateway-Processed` chỉ minh họa; nếu hệ thống có chính sách header bảo mật như HSTS, CORS hoặc CSP thì nên dùng thành phần chính thức và kiểm tra **nguồn nào sở hữu header**, không tùy tiện ghi đè.

**Giới hạn:** `beforeCommit` chỉ chạy nếu response thực sự đến bước commit và callback đã được đăng ký kịp thời. Nó không bảo đảm chạy khi request bị hủy trước commit. Nếu có filter khác đã commit trước khi bạn đăng ký, quá muộn để thay đổi header.

### 7.3. Vì sao doFinally không phải chỗ để sửa response?

~~~java
// CHỐNG MẪU: có thể quá muộn để thêm header hoặc đổi status.
return chain.filter(exchange)
        .doFinally(signal ->
                exchange.getResponse().getHeaders()
                        .set("X-Finished", "true"));
~~~

Ở thời điểm `doFinally`, status và headers có thể **đã commit**. Dù mutation Java không ném exception, nó cũng không bảo đảm header xuất hiện ở phía client. Dùng `beforeCommit` hoặc filter response chuyên dụng; `doFinally` chỉ nên làm instrumentation/cleanup nhẹ.

### Thứ tự callback khi cùng dùng beforeCommit và then

~~~mermaid
sequenceDiagram
    participant G as Custom GlobalFilter
    participant D as Downstream routing
    participant R as ServerHttpResponse
    participant C as Client
    G->>R: Register beforeCommit callback
    G->>D: chain.filter(exchange)
    D->>R: Write status/headers/body
    R->>R: Invoke beforeCommit callback
    R-->>C: Response data
    D-->>G: Publisher completes
    G->>G: then(post-success) / doFinally
~~~

Sơ đồ đơn giản hóa khả năng ghi response theo nhiều đợt. **Post-success không được đảm bảo là thời điểm cuối cùng tất cả byte đã được mạng bên dưới giao tận tay client.** Để đo I/O sâu hơn, dùng instrumentation của HTTP server/Netty theo phiên bản.

## 8. Phân biệt quan sát lỗi và xử lý lỗi

Reactor cung cấp nhiều operators liên quan đến lỗi, nhưng tác động khác nhau:

~~~java
// Chỉ quan sát; lỗi vẫn đi tiếp.
return chain.filter(exchange)
        .doOnError(error -> recordErrorType(error.getClass()));
~~~

~~~java
// Chuyển lỗi thuộc một loại thành một Publisher khác.
return chain.filter(exchange)
        .onErrorResume(SelectedUpstreamException.class,
                error -> safeFallback(exchange, error));
~~~

Trong ví dụ thứ hai, `SelectedUpstreamException` và `safeFallback` là ký hiệu **phác thảo**. Không được sao chép chúng như các class/API có sẵn. Với một exception có thể xử lý được, `onErrorResume` có thể thay `onError` thành `onComplete` nếu Publisher fallback hoàn tất thành công.

**Đừng dùng `onErrorResume(error -> Mono.empty())` cho tất cả lỗi.** Nó có thể làm phần filter chain kết thúc mà không tạo response/status phù hợp, che lỗi bảo mật và khiến hệ thống quan sát hiểu nhầm request đã thành công.

### 8.1. Ví dụ xử lý hẹp lỗi kết nối khi response chưa commit

Đoạn sau minh họa chỉ chuyển **java.net.ConnectException trực tiếp** thành HTTP 503 với body rỗng; các lỗi khác vẫn tiếp tục được truyền về error handler của framework:

~~~java
import java.net.ConnectException;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class NarrowConnectionFallback {

    private NarrowConnectionFallback() {}

    public static GatewayFilter create() {
        return (exchange, chain) -> chain.filter(exchange)
                .onErrorResume(
                        ConnectException.class,
                        error -> respondUnavailable(exchange, error)
                );
    }

    private static Mono<Void> respondUnavailable(
            ServerWebExchange exchange,
            ConnectException originalError
    ) {
        ServerHttpResponse response = exchange.getResponse();

        // Không ghi lại status nếu header/body đã được gửi.
        if (response.isCommitted()
                || !response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE)) {
            return Mono.error(originalError);
        }

        response.getHeaders().setCacheControl("no-store");
        return response.setComplete();
    }
}
~~~

**Đây là ví dụ kỹ thuật có giới hạn, không phải fallback hoàn chỉnh cho production.** Trong Reactor Netty, lỗi kết nối có thể được wrap hoặc biểu diễn bằng exception khác. Code này chỉ bắt `ConnectException` đúng kiểu, không chắc nhận mọi timeout, TLS handshake failure hoặc `PrematureCloseException`. Hệ thống thật nên có chính sách ngoại lệ rõ, dựa trên contract route và có test fault injection.

Quan trọng hơn:

1. **Lỗi auth 401/403** nên do Spring Security và backend policy xử lý, không biến mọi exception thành 503.
2. Nếu response **đã commit**, không thể tạo HTTP 503 mới trên cùng response. Ví dụ trả lại original error để phía ngoài xử lý/cancel kết nối theo khả năng thực tế.
3. HTTP 500/503 **được backend trả như response bình thường** thường không tạo `onError`; custom filter cần phân biệt status với reactive error.
4. Nếu muốn fallback theo Resilience4j/circuit breaker, có thể dùng **CircuitBreaker GatewayFilter** và handler `forward:` phù hợp thay vì tự viết catch-all.
5. Không ghi toàn bộ exception message ra response; message có thể chứa upstream URL, host, query hoặc credential.

### 8.2. Lỗi trong chính callback của filter

Một callback như:

~~~java
.doOnError(error -> {
    // Nếu recordFailure() ném lỗi, nó có thể làm mất exception ban đầu.
    recordFailure(error);
})
~~~

cần được thiết kế **không ném exception**. Một logger, metric exporter hoặc formatter gặp lỗi không nên thay thế nguyên nhân gốc. Dùng instrumentation đã được kiểm thử, giới hạn cost, và không gọi I/O blocking bên trong các callback `doOn...`.

### 8.3. Operator order thay đổi điều bạn quan sát

So sánh:

~~~java
// A: quan sát lỗi upstream, rồi fallback.
return chain.filter(exchange)
        .doOnError(error -> recordUpstreamFailure())
        .onErrorResume(ConnectException.class,
                error -> respondUnavailable(exchange, error));
~~~

~~~java
// B: fallback trước; doOnError phía ngoài chỉ thấy lỗi chưa được phục hồi.
return chain.filter(exchange)
        .onErrorResume(ConnectException.class,
                error -> respondUnavailable(exchange, error))
        .doOnError(error -> recordUnrecoveredFailure());
~~~

Trong A, telemetry có thể ghi một upstream failure ngay cả khi fallback trả 503 hợp lệ. Trong B, exception đã được fallback xử lý thành công có thể không tới `doOnError` phía ngoài. Với cả hai cách, vẫn cần **metric riêng cho fallback invocation**; không thể lấy `HTTP status` hoặc `doOnError` làm toàn bộ bức tranh.

## 9. Cancellation: yêu cầu dừng, không phải một exception

Cancellation là một phần bình thường của Reactive Streams. Ví dụ:

- Client đóng tab hoặc rời khỏi trang, kết nối HTTP bị ngắt khi response đang truyền.
- Một operator `timeout` hoặc `takeUntilOther` dừng subscription upstream.
- Một nhánh `flatMap` hoặc publisher kết hợp không còn cần kết quả.
- Server shutdown hoặc một thành phần điều phối hủy công việc đang chạy.

**Không thể suy luận một-một** rằng mọi `CANCEL` đều là “client disconnect”, cũng không thể khẳng định client disconnect luôn biểu hiện đúng một `CANCEL` tại vị trí filter đang đo. Tùy giao thức, mức buffering, tầng Netty và thời điểm sự cố, bạn có thể thấy `onError`, cancel hoặc một kết thúc khác.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as Gateway Reactor chain
    participant Filter as Custom GlobalFilter
    participant Upstream as Backend HTTP client
    Client->>Gateway: GET /api/reports/stream
    Gateway->>Filter: Subscribe
    Filter->>Upstream: Subscribe / start request
    Upstream-->>Client: HTTP response bytes (qua Gateway)
    Client--xGateway: Connection closed / request abandoned
    Gateway->>Filter: cancel (possible outcome)
    Filter->>Upstream: cancel propagates upstream
    Note over Filter,Upstream: Cleanup / socket handling depend on state
~~~

### 9.1. doOnCancel và doFinally(CANCEL) khác gì?

~~~java
return chain.filter(exchange)
        .doOnCancel(() -> recordCancelRequested())
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                recordSubscriptionCancelled();
            }
        });
~~~

Ở đây cần import `reactor.core.publisher.SignalType`; các hàm `record...` là instrumentation minh họa. `doOnCancel` được kích hoạt khi cancellation được yêu cầu. `doFinally` đưa cho bạn **loại tín hiệu kết thúc subscription**, nên phù hợp với một phép đo chung cho cả ba trường hợp `ON_COMPLETE`, `ON_ERROR`, `CANCEL`.

Đừng vừa tăng cùng một counter “cancel” trong cả `doOnCancel` và `doFinally(CANCEL)` nếu không muốn **đếm đôi**. Có thể dùng `doOnCancel` cho log chi tiết, còn `doFinally` cho tổng số kết thúc theo loại.

### 9.2. Vì sao cleanup không nên dùng doOnError duy nhất?

Nếu bạn mở một tài nguyên theo subscription (ví dụ một handle đến hệ thống khác) rồi chỉ dọn khi có lỗi, request hoàn tất thành công hoặc bị cancel có thể làm tài nguyên tồn đọng.

~~~java
// CHỐNG MẪU: bỏ sót success và cancellation.
return chain.filter(exchange)
        .doOnError(error -> releaseResource());
~~~

Với cleanup **đồng bộ, cực nhanh và không blocking**, có thể cân nhắc `doFinally`:

~~~java
return chain.filter(exchange)
        .doFinally(signal -> releaseFastLocalResource());
~~~

Nhưng nếu giải phóng tài nguyên đòi **I/O reactive bất đồng bộ**, không bắt đầu bằng `releaseMono.subscribe()` trong `doFinally`. Hãy quản lý nó bằng toán tử phù hợp, chẳng hạn `Mono.usingWhen` khi lifecycle thực sự sở hữu resource:

~~~java
// Pseudocode về phạm vi ownership; resourceFactory là API tự định nghĩa.
return Mono.usingWhen(
        resourceFactory.acquire(),
        resource -> chain.filter(exchange),
        resource -> resourceFactory.release(resource),
        (resource, error) -> resourceFactory.release(resource),
        resource -> resourceFactory.release(resource)
);
~~~

**Không áp dụng đoạn mã này để tự đóng connection pool, ServerWebExchange hoặc DataBuffer do Gateway/Netty sở hữu.** Nó chỉ minh họa một resource **riêng do custom component tự acquire**, với các phương thức trả Publisher và lifecycle rõ. `usingWhen` cho phép khai báo các nhánh cleanup khi hoàn tất thành công, thất bại và cancel.

### 9.3. Cancellation không đồng nghĩa rollback

Nếu Gateway đã gửi `POST /orders` và Orders đã commit DB trước khi client ngắt, cancel từ Gateway **không đảo ngược** transaction ở service. Không tự retry một thao tác ghi chỉ vì thấy `CANCEL`. Cần **idempotency key, trạng thái giao dịch và chính sách retry** riêng.

Với SSE/WebSocket hoặc NDJSON, cancellation cũng không đảm bảo mọi event chưa được flush; thiết kế reconnect/resume để client xử lý dữ liệu đã nhận một phần, tránh nhân bản sự kiện.

## 10. Đường đi của lỗi khi response đã commit

Trong HTTP, status và headers chỉ có thể thay đổi **trước khi response commit**. Nếu Gateway bắt đầu stream:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

~~~

rồi upstream lỗi, bạn **không thể quay lại gửi**:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"error":"UPSTREAM_UNAVAILABLE"}
~~~

trên cùng HTTP response đã có status 200 và dữ liệu. Một custom `onErrorResume` trả JSON lúc này có thể gây lỗi protocol hoặc ghi nối nội dung không đúng định dạng vào stream.

### Nguyên tắc xử lý an toàn

1. **Trước commit:** Có thể chọn status/body fallback phù hợp nếu exception được phân loại đúng và chưa có response content.
2. **Sau commit:** Không sửa status; để stream lỗi/đóng theo cơ chế HTTP, và định nghĩa reconnect/resume cho client khi nghiệp vụ cần.
3. **Khi cancel:** Tránh cố ghi một response mới cho client đã bỏ; chỉ dọn tài nguyên theo quyền sở hữu.
4. **Khi retry:** Không resubscribe tùy tiện vào một HTTP exchange đã ghi response hoặc request body không replay được.

`exchange.getResponse().isCommitted()` giúp nhận biết trạng thái tại thời điểm kiểm tra, nhưng vẫn có thể xảy ra **race** giữa các thao tác bất đồng bộ. Vì vậy logic commit/status phải dùng API response đúng, không thực hiện mutate trễ từ callback `doFinally`.

## 11. DataBuffer, request/response body và backpressure

Một custom filter đôi khi cần xem hoặc biến đổi request/response body. Trong WebFlux, body thường được biểu diễn bởi `Flux<DataBuffer>`, có thể đến từng phần theo backpressure. Đây là lĩnh vực dễ tạo lỗi nếu chỉ viết code “đọc tất cả rồi ghi lại” như Servlet đồng bộ.

### Vì sao body không giống một String có thể đọc vô hạn lần?

| Hành vi | Rủi ro |
| --- | --- |
| Đọc body trước rồi để downstream đọc lại | Publisher/body có thể đã bị tiêu thụ, downstream nhận body rỗng |
| Cache body không giới hạn | Heap/off-heap memory tăng, có thể OOM |
| Giữ pooled DataBuffer mà không release đúng | Reference-count leak hoặc memory corruption |
| Tự gọi `subscribe()` để log body | Hai luồng đọc tranh chấp, mất backpressure/cancellation |
| Dump body JSON/login trong log | Lộ mật khẩu, access token hoặc dữ liệu cá nhân |
| Thử replay body sau khi response đã commit | HTTP contract sai, side effect trùng |

**Không coi `doFinally` là đủ để giải phóng mọi DataBuffer đã chạm vào.** Với buffer có reference counting, cần biết chính xác ai giữ quyền sở hữu, ai retain, ai release và trường hợp discard/cancel. Sử dụng `DataBufferUtils.release(... )`, `doOnDiscard` và response/request decorator **theo pattern được framework hỗ trợ**; không tự release một buffer mà downstream vẫn cần.

### Kiến trúc đúng khi biến đổi body

~~~mermaid
flowchart LR
    I["Body Flux<DataBuffer>"] --> D["Decorator / supported body filter"]
    D --> T["Transform / validate, bounded"]
    T --> B["Body forwarded with backpressure"]
    B --> U["Upstream HTTP client"]
    T -. "cancel/error" .-> C["Release owned buffers"]
~~~

Nếu chỉ cần thêm header, đo latency hay theo dõi status, **không nên động vào body**. Dùng `AddRequestHeader`, `SetResponseHeader` hoặc callback phù hợp. Nếu cần biến đổi JSON body, ưu tiên những GatewayFilter factories được hỗ trợ như `ModifyRequestBody`/`ModifyResponseBody` trong dòng phiên bản phù hợp, đồng thời đặt giới hạn kích thước và test streaming.

### Response body của Mono<Void> ở đâu?

`Mono<Void>` được GatewayFilter trả về là **tín hiệu hoàn thành công việc**, không phải body content. Dòng JSON/SSE có thể được xử lý qua `ServerHttpResponse.writeWith(Publisher<? extends DataBuffer>)` và các decorator của HTTP response. Do đó:

~~~java
return chain.filter(exchange)
        .doOnSuccess(body -> {
            // body là null trong Mono<Void>, không phải JSON response.
        });
~~~

Không sử dụng cách này để parse response. Việc intercept body yêu cầu API decorator, buffer management và chính sách bảo mật riêng.

## 12. Phân biệt GlobalFilter và GatewayFilterFactory

Không phải mọi yêu cầu đều cần một **GlobalFilter**. Với chính sách chỉ áp dụng cho một số routes, có thể tạo **GatewayFilterFactory** để quản lý config riêng. Lựa chọn ảnh hưởng tới phạm vi thực thi:

| Lựa chọn | Phạm vi điển hình | Khi nào dùng |
| --- | --- | --- |
| `GlobalFilter` | Những request đã được Gateway chọn route và đưa vào Gateway filter chain | Telemetry route chung, chuẩn hóa header chung, chính sách kỹ thuật nhất quán |
| `GatewayFilter` | Một route hoặc nhóm route được cấu hình gắn filter | Policy, response marker hoặc transformation riêng của route |
| `AbstractGatewayFilterFactory<Config>` | Định nghĩa cách tạo `GatewayFilter` có tham số trong YAML/DSL | Tái sử dụng logic có cấu hình/validation |
| `WebFilter` | Lớp WebFlux, có thể bao phủ HTTP requests không đi qua route Gateway | Authentication/authorization hoặc chức năng cần đứng ngoài lifecycle route |

**Điểm cần nhớ:** `GlobalFilter` không đồng nghĩa được chạy cho **mọi request đến cổng HTTP**. Nếu request không khớp route, nó có thể không đi qua `FilteringWebHandler` và không chạy custom GlobalFilter. Các WebFlux controller nội bộ, actuator hoặc handler khác cũng có thể có lifecycle riêng. Với authentication/authorization, ưu tiên cơ chế **Spring Security WebFlux WebFilter** thay vì tự xây bảo mật chỉ bằng GlobalFilter.

### Ví dụ factory cho route cần đo signal theo tên nhóm

~~~java
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class LifecycleTagGatewayFilterFactory
        extends AbstractGatewayFilterFactory<LifecycleTagGatewayFilterFactory.Config> {

    private static final Logger log =
            LoggerFactory.getLogger(LifecycleTagGatewayFilterFactory.class);

    public LifecycleTagGatewayFilterFactory() {
        super(Config.class);
    }

    @Override
    public GatewayFilter apply(Config config) {
        String tag = config.getTag();

        // Chỉ nhận nhãn hữu hạn, do cấu hình đáng tin cung cấp.
        if (tag == null || !tag.matches("[a-z0-9_-]{1,32}")) {
            throw new IllegalArgumentException("Invalid lifecycle tag");
        }

        return (exchange, chain) -> Mono.defer(() -> {
            long startedAt = System.nanoTime();

            return chain.filter(exchange)
                    .doFinally(signal -> {
                        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedAt);
                        log.debug("tag={} signal={} elapsedMs={}",
                                tag, signal, elapsedMs);
                    });
        });
    }

    public static class Config {
        private String tag;

        public String getTag() {
            return tag;
        }

        public void setTag(String tag) {
            this.tag = tag;
        }
    }
}
~~~

Có thể dùng factory đó trong route:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
              filters:
                - name: LifecycleTag
                  args:
                    tag: catalog
~~~

Quy ước đặt tên `LifecycleTagGatewayFilterFactory` cho phép dùng tên filter `LifecycleTag` trong những dòng Gateway hỗ trợ kiểu factory này. Route `lb://catalog-service` cần load balancer và nguồn ServiceInstance; nếu đang thử nghiệm local có thể đổi thành backend URI hợp lệ.

**Lưu ý:** Factory có thể được tạo/cấu hình khi route definitions được nạp, còn `apply` xây filter cho route. Publisher per-request chỉ được tạo trong lambda `(exchange, chain) -> ...`. Không lưu `ServerWebExchange` hoặc request-specific state trong `Config` hay field của singleton factory. Làm vậy dễ rò dữ liệu giữa nhiều người dùng và nhiều request đồng thời.

### Thứ tự riêng của factory

Nếu một route yêu cầu filter nằm trước/sau filter khác, có thể sử dụng cơ chế order của Gateway hoặc `OrderedGatewayFilter` theo API phiên bản, đồng thời test thực tế. **Đừng giả định thứ tự trong danh sách YAML luôn đủ** khi GlobalFilters và factory-generated GatewayFilters được trộn với nhau.

## 13. Reactor Context, ServerWebExchange và dữ liệu theo request

Một request có thể đi qua nhiều asynchronous boundaries. Reactor có **Context** gắn với subscription, còn `ServerWebExchange` giữ dữ liệu HTTP và attributes của request. Hai nơi này phục vụ mục đích khác nhau.

| Nơi lưu | Đặc điểm | Ví dụ phù hợp |
| --- | --- | --- |
| Biến cục bộ bên trong `Mono.defer` | Một state cho mỗi subscription | Mốc thời gian, bộ đếm của một attempt |
| `ServerWebExchange.getAttributes()` | Dữ liệu gắn với HTTP exchange | Route được chọn, URL đích, metadata filter dùng chung |
| Reactor `Context` | Metadata theo subscriber chain | Trace context/technical correlation đã chuẩn hóa |
| `ThreadLocal` / MDC thô | Dữ liệu gắn với thread hiện tại | **Không đáng tin** qua asynchronous scheduling nếu thiếu context propagation |
| Field của singleton `GlobalFilter` | State dùng chung giữa requests | Client/metric registry immutable, **không phải biến per-request** |

Ví dụ đọc Reactor Context trong một Publisher:

~~~java
return Mono.deferContextual(contextView -> {
    String traceGroup = contextView.getOrDefault("trace.group", "unknown");
    return chain.filter(exchange)
            .doFinally(signal ->
                    recordTraceGroup(traceGroup, signal));
});
~~~

`recordTraceGroup` là hàm ví dụ. Đoạn code chỉ đọc khóa đã có trong context; nếu không được tạo bởi instrumentation upstream, giá trị là `unknown`. Với tracing thực tế, nên dùng cơ chế context propagation của **Micrometer Tracing, OpenTelemetry hoặc Spring** phù hợp, thay vì tự phát minh một chuẩn trace header.

### Không copy token vào Reactor Context chỉ để dễ log

Reactor Context có thể truyền qua nhiều operators và thư viện. Việc đưa raw `Authorization`, session cookie, refresh token, request body hoặc URL chứa bí mật vào Context chỉ mở rộng phạm vi dữ liệu có thể bị quan sát. Nếu một filter cần identity để ra quyết định, lấy từ **Spring Security context đã xác thực** hoặc một contract được phê duyệt; không dùng một header `X-User-Id` do client tự khai làm danh tính.

### Vì sao ThreadLocal/MDC có thể sai?

Với WebFlux, nhiều requests có thể dùng chung Reactor Netty event-loop threads và chuyển qua schedulers trong quá trình xử lý. Một `ThreadLocal` đặt ở pre-phase không được bảo đảm còn giá trị đúng khi `doFinally` chạy, trừ khi có context propagation đúng cách. Cũng không giữ `ServerWebExchange` trong một ThreadLocal lâu dài. Điều này có thể gây **lẫn log giữa hai người dùng** hoặc leak dữ liệu.

## 14. Retry, circuit breaker và resubscription làm đổi số callback

Trong Spring Cloud Gateway, route có thể sử dụng `Retry` hoặc `CircuitBreaker`. Một filter đo lifecycle cần hiểu **đang bao bọc HTTP operation tổng hay từng upstream attempt**.

~~~mermaid
flowchart TD
    Req["Một inbound HTTP request"] --> Retry["Retry filter"]
    Retry --> Attempt1["Attempt #1: subscribe downstream"]
    Attempt1 --> Err["onError hoặc status được Retry nhận diện"]
    Err --> Wait["Backoff"]
    Wait --> Attempt2["Attempt #2: resubscribe downstream"]
    Attempt2 --> Done["Success hoặc hết budget"]
    Done --> Resp["Final HTTP response"]
~~~

Nếu `SafeLifecycleGlobalFilter` hoặc một `GatewayFilter` nằm **bên trong** vùng Publisher mà Retry resubscribe, bạn có thể thấy:

~~~text
Attempt 1 -> doFinally(ON_ERROR)
Attempt 2 -> doFinally(ON_COMPLETE)

Một inbound request có thể tạo hai doFinally callbacks.
~~~

Ngược lại, nếu instrumentation bọc **vòng retry tổng**, nó có thể thấy một `ON_COMPLETE` cuối cùng và không ghi riêng từng attempt. **Cả hai phép đo đều hữu ích**, nhưng là hai đơn vị khác nhau:

- **request latency / result**: thời gian và status cuối mà client nhìn thấy.
- **attempt latency / error**: từng lần gọi upstream, kể cả retry hoặc call bị circuit breaker từ chối.

Một `CircuitBreaker` ở trạng thái OPEN có thể ngăn downstream được subscribe. Nếu custom instrumentation nằm ở **sau circuit breaker**, nó sẽ không chạy trên request bị từ chối. Nếu đặt phía ngoài, nó có thể quan sát fallback/short-circuit. Đó là lý do phân tích **filter order** và kiểm thử dưới cả hai trạng thái CLOSED/OPEN.

### Chú ý với Mono.defer và resubscription

`Mono.defer` sẽ thực thi lại supplier khi có subscription mới. Nếu pre-phase thực hiện **ghi DB, phát email, trừ tiền hoặc tạo order**, một retry ở tầng ngoài có thể **lặp side effect**. Không đặt tác vụ nghiệp vụ có side effect trong custom GatewayFilter chỉ vì nó “chạy trước routing”.

Nếu cần retry logic, ưu tiên **Retry GatewayFilter Factory** với chính sách method/status/exception, backoff, deadline và idempotency rõ. Không tự `repeat()` hoặc `retryWhen()` quanh `chain.filter(exchange)` khi chưa kiểm chứng body replay, response commit, cancellation và contract nghiệp vụ.

## 15. Bảo mật khi xử lý lỗi và hủy

Các sự kiện lỗi/hủy thường khiến đội vận hành bật nhiều debug hơn. Đây là lúc token và dữ liệu người dùng dễ lọt vào log/tracing.

**Không nên:**

~~~java
return chain.filter(exchange)
        .doOnError(error -> {
            log.error("Failed exchange={} exception={}", exchange, error);
        });
~~~

Ngoài việc log toàn exception stack, biểu diễn của `exchange` hoặc message có thể chứa raw URL/query, token hoặc địa chỉ nội bộ tùy phiên bản/logger. Một response fallback cũng không được echo `Authorization` hoặc stack trace về client.

**Nên** log metadata được kiểm soát:

~~~text
route=catalog-api method=GET status=503
terminal=ON_ERROR errorType=ConnectException
elapsedMs=148
~~~

Với `CANCEL`, không ghi “client maliciously disconnected” chỉ từ tín hiệu cancel; nên ghi `terminal=CANCEL` và kết hợp server/network instrumentation nếu cần phân biệt nguyên nhân.

### Những ranh giới không được một GlobalFilter bảo vệ thay

1. **Spring Security WebFilter** phải xử lý authentication/authorization ở lớp phù hợp; GlobalFilter không thể thay thế chính sách cho mọi HTTP endpoint.
2. **TLS/mTLS** quyết định tính tin cậy và bảo mật của kết nối upstream, không đến từ `doOnSuccess`.
3. **Service discovery** có thể đổi đích `lb://service-id`; không log hoặc forward token đến instance không được phép.
4. **Rate limiting/circuit breaker/retry** có thể short-circuit chuỗi; telemetry phải biết nhánh nào đã chạy thật.
5. **Gateway fallback** với `forward:` không được công khai endpoint nội bộ hoặc bỏ qua backend authorization.

Nếu cần audit bảo mật bắt buộc trước khi cho phép hành động, **đừng giao việc audit quan trọng cho một callback doFinally best-effort** mà không có cơ chế đảm bảo kết quả. Dùng một transaction/outbox hoặc một service audit đáng tin có chính sách thất bại rõ ràng theo nghiệp vụ.

## 16. Kiểm thử pre và post bằng StepVerifier

Các callback Reactor thường chạy bất đồng bộ, nên chỉ đọc log bằng mắt khó chứng minh thứ tự. **reactor-test** cung cấp `StepVerifier` để subscribe Publisher và xác nhận `onComplete`, `onError` hoặc cancellation.

### 16.1. Xác minh pre → downstream → post

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class PrePostGatewayFilterTest {

    @Test
    void preRunsBeforeDownstreamAndPostRunsAfterSuccess() {
        List<String> events = new ArrayList<>();

        GatewayFilter filter = (exchange, chain) ->
                Mono.defer(() -> {
                    events.add("pre");
                    return chain.filter(exchange)
                            .then(Mono.fromRunnable(() -> events.add("post")));
                });

        GatewayFilterChain downstream = exchange ->
                Mono.fromRunnable(() -> events.add("downstream"));

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42").build());

        StepVerifier.create(filter.filter(exchange, downstream))
                .verifyComplete();

        assertThat(events)
                .containsExactly("pre", "downstream", "post");
    }
}
~~~

**Vì sao test có giá trị?**

1. Khi dựng filter, `Mono.defer` chưa chạy `events.add("pre")`.
2. `StepVerifier` tạo subscription, kích hoạt pre logic.
3. `Mono.fromRunnable` ở downstream thêm `downstream`.
4. Vì downstream hoàn tất thành công, `then` mới thêm `post`.
5. Assertion xác nhận thứ tự. Nếu downstream lỗi, `post` sẽ không được thêm; trường hợp đó được test riêng.

Ở test nhỏ này, `ArrayList` đủ vì code không chuyển scheduler. Nếu test chuyển sang nhiều threads, hãy dùng cấu trúc an toàn cho concurrency hoặc cách đồng bộ rõ ràng.

### 16.2. Xác minh lỗi không bị doOnError nuốt mất

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ErrorSignalGatewayFilterTest {

    @Test
    void doOnErrorObservesButDoesNotRecoverTheError() {
        AtomicInteger errorsSeen = new AtomicInteger();

        GatewayFilter filter = (exchange, chain) ->
                chain.filter(exchange)
                        .doOnError(error -> errorsSeen.incrementAndGet());

        GatewayFilterChain failingDownstream = exchange ->
                Mono.error(new IllegalStateException("test-only"));

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42").build());

        StepVerifier.create(filter.filter(exchange, failingDownstream))
                .expectError(IllegalStateException.class)
                .verify();

        assertThat(errorsSeen.get()).isEqualTo(1);
    }
}
~~~

Test chứng minh `doOnError` có quan sát lỗi, nhưng subscriber cuối vẫn nhận `onError`. Nếu thay bằng `onErrorResume` trả Publisher hoàn tất thành công, kỳ vọng của `StepVerifier` phải thay đổi tương ứng.

### 16.3. Xác minh cancellation có SignalType.CANCEL

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CancelSignalGatewayFilterTest {

    @Test
    void finallyObservesCancelWithoutTurningItIntoError() throws Exception {
        AtomicReference<SignalType> finalSignal = new AtomicReference<>();
        CountDownLatch finished = new CountDownLatch(1);

        GatewayFilter filter = (exchange, chain) ->
                chain.filter(exchange)
                        .doFinally(signal -> {
                            finalSignal.set(signal);
                            finished.countDown();
                        });

        GatewayFilterChain neverCompletes = exchange -> Mono.never();

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/stream").build());

        StepVerifier.create(filter.filter(exchange, neverCompletes))
                .thenCancel()
                .verify();

        assertThat(finished.await(1, TimeUnit.SECONDS)).isTrue();
        assertThat(finalSignal.get()).isEqualTo(SignalType.CANCEL);
    }
}
~~~

`Mono.never()` không tự complete hoặc error, nên `StepVerifier.thenCancel()` kích hoạt nhánh cancel. `CountDownLatch` trong **test thread** giúp tránh một assertion chạy trước `doFinally`; **không dùng blocking await này trong Reactor Netty event loop ở production**.

Đây là test tín hiệu Reactor, **không phải mô phỏng đầy đủ một client TCP disconnect**. Muốn xác minh lifecycle thực khi client ngắt SSE/WebSocket, cần integration test với Gateway và backend/proxy thật hoặc stub có kiểm soát.

## 17. Kiểm thử beforeCommit và response đã commit

Một yêu cầu thường gặp: “Thêm header kiểm toán vào mọi response được Gateway proxy.” Cần kiểm tra rằng header xuất hiện **trước response commit**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class BeforeCommitGatewayFilterTest {

    @Test
    void headerIsAddedBeforeResponseCompletes() {
        GatewayFilter filter = (exchange, chain) -> {
            exchange.getResponse().beforeCommit(() -> {
                exchange.getResponse().getHeaders()
                        .set("X-Gateway-Processed", "true");
                return Mono.empty();
            });
            return chain.filter(exchange);
        };

        GatewayFilterChain downstream = exchange ->
                exchange.getResponse().setComplete();

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/catalog/items/42").build());

        StepVerifier.create(filter.filter(exchange, downstream))
                .verifyComplete();

        assertThat(
                exchange.getResponse().getHeaders()
                        .getFirst("X-Gateway-Processed")
        ).isEqualTo("true");
    }
}
~~~

Test này sử dụng `MockServerWebExchange` và test response; không chứng minh mọi reverse proxy hoặc CDN đều giữ header đó khi trả ra Internet. Hãy có integration test HTTP để kiểm tra sau khi request đi qua ingress, response filters và backend.

**Không dùng test này để kết luận doFinally sửa header là hợp lệ**: downstream `setComplete()` chính là điểm commit. Khi đã commit, callback post hoặc finally có thể không còn cơ hội thay đổi status/headers.

## 18. Ma trận kiểm thử vòng đời đầy đủ

| Kịch bản | Downstream Publisher | Callback cần xuất hiện | Callback không nên kỳ vọng |
| --- | --- | --- | --- |
| Thành công bình thường | `Mono.empty()` | `doOnSuccess`, `doFinally(ON_COMPLETE)` | `doOnError`, `doOnCancel` |
| Lỗi trong route/filter | `Mono.error(ex)` | `doOnError`, `doFinally(ON_ERROR)` | `doOnSuccess` |
| Cancel chủ động | `Mono.never()` rồi cancel | `doOnCancel`, `doFinally(CANCEL)` | `doOnError`, `doOnSuccess` |
| Lỗi được fallback | `onErrorResume` trả `Mono.empty()` | Observer trước fallback thấy lỗi; observer sau fallback có thể thấy complete | Mọi observer đều thấy cùng một terminal signal |
| Backend trả HTTP 503 bình thường | Response HTTP 503 + Publisher complete | `doOnSuccess`, `doFinally(ON_COMPLETE)` có thể chạy | `doOnError` tự động chỉ vì status 503 |
| Lỗi sau commit | HTTP 200 đã gửi một phần + Publisher error | `doOnError`, `doFinally(ON_ERROR)` tùy vị trí | Có thể đổi status 200 thành 503 |
| Retry có 2 attempts | Publisher downstream có thể resubscribe | Hai lần pre/finally nếu filter nằm trong phạm vi retry | Một callback cho mỗi user operation |
| Circuit breaker OPEN | Không subscribe downstream trong nhánh bị chặn | Observer bên ngoài thấy kết quả fallback/short-circuit | Filter bên trong downstream luôn được chạy |
| Không khớp Gateway route | Không có Gateway FilteringWebHandler cho route đó | WebFlux/WebFilter thích hợp, nếu có | Custom GlobalFilter chắc chắn chạy |
| Client ngắt HTTP stream | Tùy Netty/transport và thời điểm | Có thể có cancel hoặc error trong chain | Mỗi disconnect nhất thiết là đúng một CANCEL |

### Bằng chứng từ integration test

Cho backend stub có khả năng trả 200/503, delay, reset connection hoặc stream một phần:

1. Gửi request qua route gắn custom filter.
2. Xác minh **route ID** và số lần backend nhận request.
3. Xác minh callback success/error/cancel theo điều kiện đã tạo.
4. Kiểm tra status, header, body ở **client**, không chỉ ở exchange mock.
5. Với retry hoặc breaker, đo số subscriptions/attempts riêng biệt.
6. Với cancel, xác minh tài nguyên do filter sở hữu đã được cleanup; không mặc định TCP socket đóng ngay cùng một mili giây.
7. Đảm bảo callback không ghi token, cookies, query nhạy cảm hoặc toàn body vào telemetry.

**Kiểm thử bằng fault injection có giới hạn trong môi trường thử nghiệm.** Không cần gây outage trên production để chứng minh operator `doFinally` hoạt động.

## 19. Chẩn đoán những lỗi custom filter phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log “request complete” xuất hiện trước khi backend phản hồi | Log ở assembly, ngay sau `chain.filter` | Dùng `then`, `doOnSuccess` hoặc `doFinally` đúng tín hiệu |
| `doOnNext` không chạy dù request có body JSON | Filter trả `Mono<Void>` không phát onNext | Quan sát completion/status; body phải dùng decorator đúng |
| `doOnSuccess` gây NullPointerException | Callback cố đọc giá trị từ `Mono<Void>` | Không dùng argument như response body; nó là `null` |
| Có lỗi nhưng post-success không chạy | `then` chỉ thực hiện khi upstream complete | Dùng `doFinally` nếu cần theo dõi mọi kiểu kết thúc |
| Client disconnect nhưng không thấy doOnError | Cancellation không phải onError | Theo dõi `doOnCancel`/`doFinally(CANCEL)`; test transport thực |
| Filter tính latency hai lần cho một request | Retry resubscribe downstream hoặc log cả success và finally | Phân biệt operation/attempt; chọn counter riêng |
| Response header được set nhưng client không thấy | Set ở `doFinally` sau commit hoặc bị filter khác ghi đè | Dùng `beforeCommit`; kiểm tra order và response filters |
| Fallback 503 không được gửi | Response đã commit hoặc exception không đúng loại | Kiểm tra `isCommitted()`, exception chain và HTTP contract |
| HTTP 500 không kích hoạt doOnError | Backend trả response bình thường với status 500 | Quan sát status riêng; chọn CircuitBreaker `statusCodes` khi phù hợp |
| Spring Security 401/403 không xuất hiện trong GlobalFilter telemetry | Security WebFilter xử lý trước route Gateway | Instrument WebFlux/Spring Security hoặc HTTP server ở lớp tương ứng |
| Filter không chạy với `/unknown` | Không có Gateway route match | Kiểm tra route predicate hoặc dùng WebFilter nếu cần toàn bộ HTTP |
| `NullPointerException` ở `getStatusCode().value()` | Response status chưa có | Kiểm tra `null` trước |
| Dữ liệu request A xuất hiện trong log request B | State per-request lưu trong singleton field/ThreadLocal sai | Dùng `Mono.defer`, exchange/context và propagation phù hợp |
| Memory tăng khi body lớn hoặc cancel | Cache/join DataBuffer không giới hạn, retain/release sai | Giới hạn body, dùng factory/decorator chuẩn, kiểm tra leak |
| Gateway treo dưới tải dù backend nhanh | Có `block()`, JDBC, sleep hoặc I/O trong callback | Dùng reactive APIs hoặc cách ly blocking theo thiết kế |
| Error counter cao nhưng HTTP client success rate tốt | Observer nằm trước `onErrorResume` hoặc fallback trả 200 | Tách raw upstream errors, fallback count và final status |
| Circuit OPEN nhưng custom metric không tăng | Custom filter nằm trong nhánh downstream không được subscribe | Điều chỉnh điểm đo/order, đo breaker rejected calls riêng |
| Một request bị proxy hai lần | Tự `subscribe()` hoặc gọi `chain.filter` lại không có policy | Trả một Publisher composed, không tự điều khiển subscription |

### Quy trình điều tra theo từng lớp

1. **Route selection:** `RoutePredicateHandlerMapping` đã chọn route nào? Nếu không có route, GatewayFilter không chạy.
2. **Filter order:** custom filter đứng trước/sau `Retry`, `CircuitBreaker`, `RouteToRequestUrlFilter`, `ReactiveLoadBalancerClientFilter` và routing filter nào?
3. **Assembly vs subscription:** pre logic nằm ngoài hay trong `Mono.defer`? Có retry làm resubscribe không?
4. **Reactive signal:** publisher hoàn tất, lỗi hay bị cancel? Lỗi có bị `onErrorResume` ở operator khác xử lý không?
5. **HTTP response state:** đã commit chưa? Status cuối thực sự là gì? Response đã gửi một phần chưa?
6. **Transport:** Backend trả response bình thường, mất TCP, timeout, TLS error hay client tự đóng?
7. **Ownership:** Ai sở hữu DataBuffer, connection, session và resource của filter? Có leak/cancellation không?
8. **Instrumentation:** Metric đang đếm HTTP requests, upstream attempts hay subscriptions? Có lọt thông tin nhạy cảm vào log không?

Đi theo thứ tự này giúp tránh phản ứng sai như **thêm retry** khi thực ra lỗi do filter đang subscribe hai lần hoặc **tăng timeout** khi event loop bị blocking.

## 20. Hiệu năng và độ tin cậy của callback trong production

Custom filter nằm trên request hot path, vì vậy một callback tưởng nhỏ cũng có thể tạo áp lực lớn khi Gateway xử lý hàng nghìn requests/giây.

### Không blocking trong callback

Các đoạn sau **không phù hợp** chạy trực tiếp trên Reactor Netty event loop:

~~~java
// CHỐNG MẪU:
return chain.filter(exchange)
        .doFinally(signal -> {
            Thread.sleep(100);             // Ví dụ; còn không biên dịch vì checked exception.
            jdbcRepository.save(...);       // I/O blocking.
        });
~~~

Đây là **pseudocode minh họa phản mẫu**, cố tình không phải đoạn biên dịch. Thực tế, bất cứ lệnh ngủ, JDBC blocking, network client đồng bộ hoặc fsync nào trong callback đều có thể chặn event loop, làm chậm nhiều request khác. Không chạy audit/billing/DB update quan trọng bằng `doFinally` tùy tiện.

Nếu phải kết hợp một hoạt động reactive sau khi downstream complete:

~~~java
return chain.filter(exchange)
        .then(nonBlockingAuditPublisher(exchange));
~~~

`nonBlockingAuditPublisher(exchange)` là hàm được ứng dụng định nghĩa, phải trả Publisher và **không ghi bí mật**. Hãy cân nhắc rằng lúc này HTTP response có thể đã commit; nếu audit lỗi, behavior của toàn filter có thể thành `onError` mặc dù response thành công đã được gửi. Với audit bắt buộc, cần đặt quyết định/bảo đảm **trước** khi cho phép hành động hoặc dùng outbox/transaction thích hợp; với telemetry best-effort, dùng instrumentation được thiết kế để không làm hỏng request.

### Không tạo quá nhiều log và nhãn metrics

| Tín hiệu | Nên làm | Tránh |
| --- | --- | --- |
| Route ID | Dùng ID từ route được quản lý | Route ID tùy ý từ input client |
| Outcome | `ON_COMPLETE`, `ON_ERROR`, `CANCEL` | Dán toàn exception message vào label |
| HTTP status | Số status nếu có | Gắn raw body vào metric |
| Latency | Histogram/timer được cấu hình phù hợp | Log full payload mỗi request |
| Errors | Exception type đã chuẩn hóa | Token, JWT payload, query hoặc headers |
| Trace | Trace ID hợp lệ, hạn chế retention | Session ID hoặc Authorization làm correlation ID |

Khi dữ liệu nhạy cảm đã lọt vào log/exporter, việc xóa `Authorization` khỏi HTTP request outbound **không loại bỏ bản sao đã ghi**. Áp dụng chính sách log allowlist ngay tại nơi thu thập, đồng thời bảo vệ logs, traces và APM.

### Không dùng SignalType làm HTTP status

`ON_COMPLETE` không đồng nghĩa HTTP 200, `ON_ERROR` không bắt buộc HTTP 500 và `CANCEL` không phải mã HTTP chuẩn 499 trong mọi tầng. Các server/proxy đôi khi có mã log nội bộ cho client disconnect, nhưng **không tự đặt `response.setStatusCode(499)` từ doFinally**.

Để đo độ tin cậy, theo dõi **hai chiều**:

- **Reactive lifecycle:** terminal signal, resubscription, cleanup.
- **HTTP outcome:** status gửi được, bytes/stream, upstream/fallback, connection/cancel.

Kết hợp chúng mới giúp giải thích vì sao một route nhận HTTP 200 nhưng user vẫn báo download không hoàn thành, hoặc HTTP 503 được trả đúng nhưng Reactor chain không phát exception.

## 21. Bài thực hành: tự xây bộ lọc quan sát vòng đời

**Bối cảnh:** Bạn đang phát triển Gateway cho Catalog và Reports. Catalog trả JSON nhanh, còn Reports có SSE endpoint kéo dài. Yêu cầu: theo dõi đúng pre/post/error/cancel mà không gây blocking, không lộ token và không thay đổi HTTP status sau commit.

### Phần A — Dựng filter

1. Dùng **Gateway Server WebFlux** với dependency đúng BOM, có một route `/api/catalog/**` tới backend stub.
2. Thêm `SafeLifecycleGlobalFilter` từ phần 5; đặt order có chủ đích.
3. Với một route cụ thể, thử `LifecycleTagGatewayFilterFactory` từ phần 12 để so sánh phạm vi.
4. Tạo metadata log gồm route ID, method, status, `SignalType` và elapsed time; **không log Authorization, Cookie hay raw query**.
5. Đăng ký response marker bằng `beforeCommit` và xác minh header bằng HTTP client.

### Phần B — Kiểm tra tín hiệu

| Tình huống | Backend stub hoặc test publisher | Điều cần chứng minh |
| --- | --- | --- |
| Trả JSON 200 | `Mono.empty()` hoặc HTTP 200 | pre trước downstream; post-success và finally complete |
| Ném exception | `Mono.error(...)` | doOnError được gọi; không tự swallow lỗi |
| HTTP 503 có body | Backend trả response HTTP 503 | doOnError không bắt buộc chạy; status đo riêng |
| Cancel giữa chừng | `Mono.never()` với `StepVerifier.thenCancel()` | doFinally(CANCEL), không phải onError |
| SSE client disconnect | Stub stream chậm, client đóng kết nối | Quan sát cancel/error thực theo Netty |
| Lỗi sau response commit | Stub gửi một phần body rồi reset | Không cố sửa status thành 503 hoặc ghi JSON fallback |
| beforeCommit | Downstream `setComplete()` | Header được đặt trước commit |
| Retry hai attempts | Stub lỗi lần đầu, thành công lần sau | Callback được đếm theo vị trí filter/request/attempt |
| Circuit breaker OPEN | Breaker chặn upstream | Filter nằm trong nhánh không được subscribe sẽ không chạy |

### Phần C — Kiểm tra source code và lifecycle

1. Xác nhận không có `.subscribe()`, `.block()`, `Thread.sleep()` hay JDBC blocking trong filter.
2. Không dùng `doOnNext` để đọc `Mono<Void>` và không dereference giá trị `null` của `doOnSuccess`.
3. Đối với resource tự acquire, test đủ success/error/cancel; không dispose tài nguyên thuộc Gateway framework.
4. Nếu có body decorator, kiểm tra backpressure, giới hạn kích thước và reference-count lifecycle bằng tooling phù hợp.
5. Không lưu `ServerWebExchange` trong field singleton hoặc mutable global map không có lifecycle cleanup.
6. Dùng StepVerifier và HTTP integration tests riêng để tránh nhầm một reactive terminal signal với HTTP response thực tế.

### Phần D — Thử một phản mẫu rồi sửa trong lab

Trong môi trường thử nghiệm **không chứa dữ liệu thật**:

1. Đặt một log “success” ngay sau `chain.filter(exchange)`, so với log thực khi subscription complete.
2. Chuyển nó vào `doOnSuccess` hoặc `then` và so sánh timing.
3. Đổi downstream thành `Mono.error(...)` để thấy `then` không chạy, trong khi `doFinally(ON_ERROR)` có.
4. Dùng `Mono.never()` và `StepVerifier.thenCancel()` để thấy cancellation không thành `onError`.
5. Thử thêm header trong `doFinally` sau khi downstream commit, xác minh nó không đáng tin; chuyển sang `beforeCommit`.
6. Nếu bật Retry trong lab, xem callbacks có được gọi nhiều lần theo số subscriptions và chọn cách đo đúng theo mục tiêu.

### Tiêu chí đạt

Bạn có thể giải thích và chứng minh:

- **Pre** thực hiện đúng thời điểm subscription, không nhầm với assembly.
- **Post-success** chỉ chạy sau downstream hoàn tất bình thường, còn **doFinally** nhận complete/error/cancel.
- **doOnError** quan sát và truyền tiếp lỗi; **onErrorResume** thay kết quả khi được phép, không che 401/403 và không sửa response đã commit.
- **Cancel** là tín hiệu yêu cầu hủy, không đồng nghĩa exception hoặc rollback side effect.
- **beforeCommit** sửa response header đúng thời điểm; body được xử lý riêng với buffer lifecycle an toàn.
- Metrics/logs phân biệt **HTTP request, retry attempt và Reactor subscription**, không lộ dữ liệu nhạy cảm và không blocking event loop.

## 22. Những hiểu lầm thường gặp

| Nhận định sai | Điều đúng |
| --- | --- |
| “Gọi `chain.filter(exchange)` nghĩa là backend đã trả xong.” | Nó trả Publisher; phải quan sát khi Publisher được subscribe và hoàn tất. |
| “Viết log ngay sau chain.filter là post-phase.” | Đó thường là assembly-time Java code, chưa chắc downstream xong. |
| “`Mono<Void>` có body để doOnNext đọc.” | `Mono<Void>` bình thường không phát giá trị; body nằm trong HTTP response publisher khác. |
| “`doOnError` xử lý và nuốt lỗi.” | Nó chỉ quan sát; muốn fallback phải compose onErrorResume có kiểm soát. |
| “Client hủy request sẽ phát onError.” | Cancel khác onError; dùng doOnCancel/doFinally và test transport thực. |
| “Có doFinally thì luôn được sửa status/header.” | Khi callback chạy, response có thể đã commit; dùng beforeCommit nếu cần. |
| “doFinally(ON_COMPLETE) đồng nghĩa client nhận HTTP 200.” | Response 4xx/5xx cũng có thể hoàn tất bình thường; delivery qua mạng còn tách biệt. |
| “GlobalFilter chạy trên mọi HTTP request.” | Nó thuộc Gateway FilteringWebHandler cho route phù hợp, không thay WebFilter toàn ứng dụng. |
| “Thứ tự YAML quyết định mọi callback.” | Filter order và thứ tự operators/resubscription đều ảnh hưởng. |
| “Một lần doFinally là một user request.” | Retry có thể tạo nhiều subscriptions và nhiều callbacks. |
| “Có onErrorResume thì retry/fallback mọi lỗi đều an toàn.” | Cần phân loại lỗi, response commit, auth, idempotency và budget. |
| “Chỉ cần cleanup khi onError.” | Success và cancel cũng cần cleanup theo ownership. |
| “Mono.defer sẽ tự làm code blocking an toàn.” | Nó chỉ trì hoãn execution; không đổi blocking thành non-blocking. |
| “Thêm token vào MDC/Reactor Context để tiện debug là vô hại.” | Nó mở rộng phạm vi bí mật bị truyền/log; dùng metadata an toàn và Security context. |

## 23. Tổng kết

- Trong **Spring Cloud Gateway Server WebFlux**, custom `GlobalFilter` và `GatewayFilter` trả về **`Mono<Void>`**, thể hiện lifecycle của xử lý bất đồng bộ chứ không phải response body.
- **Pre** chạy trước downstream; **post** thường diễn ra theo thứ tự ngược khi các filters lồng nhau. Dùng `Mono.defer` để gắn state/mốc thời gian cho từng subscription thay vì thực thi quá sớm ở assembly.
- `doOnSuccess` quan sát hoàn tất thành công; `doOnError` quan sát lỗi; `doOnCancel` quan sát yêu cầu hủy; **`doFinally` bao phủ cả complete, error, cancel**.
- **onErrorResume thay tín hiệu lỗi bằng Publisher khác**, vì vậy phải áp dụng hẹp, kiểm tra response commit và giữ đúng HTTP contract. Backend trả HTTP 503 bình thường không tự trở thành Reactor onError.
- **Response headers/status phải được xử lý trước commit**; `beforeCommit` phù hợp cho header, còn `doFinally` thích hợp với instrumentation/cleanup nhẹ, không phải sửa response.
- **Cancellation không chứng minh backend đã rollback**; không tự retry request đã có side effect hoặc stream đã phát một phần.
- Chăm sóc `DataBuffer`, backpressure, memory, non-blocking I/O, Reactor Context và resource lifecycle khi viết filter liên quan body hoặc asynchronous cleanup.
- Với `Retry` và `CircuitBreaker`, số lần subscribe và nhánh downstream được thực thi thay đổi; đo riêng request/attempt, xác nhận filter order và bảo vệ telemetry khỏi token/PII.
- Dùng **StepVerifier**, mock exchange và backend stub để chứng minh pre/post/error/cancel, response commit và số attempts; không chỉ dựa vào log hay HTTP 200 cuối.

Một custom filter tốt không chỉ “chạy đúng khi request thành công”, mà phải **giữ nguyên tính đúng đắn của toàn chuỗi Reactor trong cả trường hợp lỗi, hủy, retry và response đã commit**, đồng thời không chặn event loop hoặc làm lộ dữ liệu nhạy cảm.
