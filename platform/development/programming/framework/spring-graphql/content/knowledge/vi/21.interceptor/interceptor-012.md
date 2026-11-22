# Interceptor blocking và reactive trong Spring for GraphQL

Spring for GraphQL cung cấp `WebGraphQlInterceptor` để chặn và bổ sung xử lý quanh một GraphQL request ở tầng web. API này có chữ ký reactive: method `intercept` nhận `WebGraphQlRequest` và trả về `Mono<WebGraphQlResponse>`. Chữ ký đó được giữ nguyên dù ứng dụng chạy trên Spring MVC hay Spring WebFlux.

Điểm cần quan tâm là công việc mà interceptor thực hiện. Nếu interceptor gọi thư viện blocking như JDBC, JPA hoặc HTTP client đồng bộ, lời gọi đó có thể giữ thread đang thực thi. Trong WebFlux, việc này đặc biệt nguy hiểm nếu chạy trên event-loop thread. Với công việc reactive, hãy nối các publisher bằng `flatMap`, `map` và các toán tử Reactor, không chờ kết quả bằng `.block()`.

## 1. WebGraphQlInterceptor nằm ở đâu?

`WebGraphQlInterceptor` chạy quanh quá trình xử lý một request đi vào GraphQL qua web transport. Nó phù hợp cho các tác vụ áp dụng ở phạm vi request/operation như:

- Đọc và xác minh metadata từ HTTP request.
- Đưa principal, tenant, request ID hoặc locale vào `GraphQLContext`.
- Ghi log, đo thời gian và thêm tracing.
- Kiểm tra điều kiện request trước khi chuyển đến GraphQL engine.
- Quan sát hoặc xử lý response sau khi GraphQL execution hoàn tất.

Luồng khái quát:

~~~mermaid
flowchart TD
    A[HTTP or WebSocket request] --> B[WebGraphQlInterceptor 1]
    B --> C[WebGraphQlInterceptor 2]
    C --> D[WebGraphQlHandler]
    D --> E[GraphQL execution]
    E --> F[DataFetchers and controllers]
    F --> G[WebGraphQlResponse]
    G --> H[Interceptor response chain]
    H --> I[Transport response]
~~~

Interceptor có thể chạy logic trước và sau `chain.next(request)`. Mỗi interceptor nên gọi `chain.next` đúng một lần cho request mà nó chuyển tiếp. Nếu không gọi chain, request không được chuyển đến các interceptor tiếp theo và GraphQL execution.

## 2. Chữ ký interceptor luôn là reactive

Interface có dạng:

~~~java
public interface WebGraphQlInterceptor {

    Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    );

    interface Chain {
        Mono<WebGraphQlResponse> next(WebGraphQlRequest request);
    }
}
~~~

Do đó, `WebGraphQlInterceptor` không có hai interface riêng kiểu blocking và reactive. Cùng một hợp đồng `Mono` được dùng trong tích hợp web của Spring for GraphQL. Khác biệt blocking/reactive nằm ở công việc bên trong interceptor và thread model của transport.

Ví dụ interceptor chỉ ghi log trước và sau GraphQL execution:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class GraphQlLoggingInterceptor implements WebGraphQlInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(GraphQlLoggingInterceptor.class);

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        log.debug("GraphQL request received: {}", request.getId());

        return chain.next(request)
                .doOnNext(response ->
                        log.debug("GraphQL request completed: {}", request.getId())
                );
    }
}
~~~

Các thao tác log ngắn thường có thể chạy trực tiếp. Nếu ghi log đồng bộ đến file, network hoặc hệ thống từ xa với độ trễ đáng kể, hãy dùng appender bất đồng bộ hoặc API reactive phù hợp để tránh biến interceptor thành điểm nghẽn.

## 3. Blocking và reactive phụ thuộc vào transport

Spring GraphQL có thể được tích hợp với Spring MVC hoặc Spring WebFlux. Mỗi stack có mô hình xử lý request khác nhau:

| Môi trường | Thread model | Điều cần lưu ý |
| --- | --- | --- |
| Spring MVC | Thường xử lý request trên servlet thread; có thể dùng async request processing | Lời gọi blocking chiếm servlet thread trong thời gian chờ |
| Spring WebFlux | Dùng event-loop và reactive scheduling | Không chạy lời gọi blocking trên event-loop thread |
| `WebGraphQlInterceptor` | Luôn trả `Mono<WebGraphQlResponse>` | Không có bản blocking riêng; phải compose công việc theo reactive contract |

`Mono` không tự biến một lời gọi đồng bộ thành non-blocking. Nếu gọi blocking service trước khi tạo publisher, công việc đã chạy ngay trên thread hiện tại:

~~~java
// Không nên: blockingCall() chạy ngay khi biểu thức được đánh giá.
return Mono.just(blockingService.loadMetadata());
~~~

Với Spring MVC, lời gọi đó có thể giữ servlet thread. Với WebFlux, nếu thread hiện tại là event loop thì có thể làm chậm nhiều request khác đang dùng chung event loop.

## 4. Viết interceptor reactive khi dependency cũng reactive

Nếu dependency trả về `Mono` hoặc `Flux`, hãy nối publisher vào interceptor chain. Ví dụ xác thực token bằng reactive client:

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveAuthenticationInterceptor implements WebGraphQlInterceptor {

    private final ReactiveTokenService tokenService;

    public ReactiveAuthenticationInterceptor(ReactiveTokenService tokenService) {
        this.tokenService = tokenService;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        String token = request.getHeaders().getFirst("Authorization");

        return tokenService.authenticate(token)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("Authentication is required")
                ))
                .flatMap(principal -> {
                    request.configureExecutionInput((input, builder) ->
                            builder.graphQLContext(context ->
                                    context.put("principal", principal)
                            ).build()
                    );
                    return chain.next(request);
                });
    }
}
~~~

`authenticate` ở đây giả định trả về `Mono<Principal>`. `flatMap` đợi publisher xác thực phát ra principal rồi mới cấu hình execution input và chuyển request đến GraphQL. Không cần tạo thread mới nếu token service đã dùng reactive I/O.

Trong hệ thống thực tế, lỗi xác thực cần được chuyển thành response phù hợp với chính sách bảo mật. Không nên biến mọi lỗi mạng hoặc lỗi hệ thống xác thực thành một kết quả `null` rồi vẫn cho request tiếp tục.

## 5. Gọi blocking dependency trong interceptor

Có trường hợp ứng dụng chưa thể thay JDBC/JPA hoặc HTTP client đồng bộ bằng API reactive. Khi đó, bọc lời gọi blocking bằng `Mono.fromCallable` và chuyển nó sang scheduler phù hợp.

~~~java
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
public class BlockingAuthenticationInterceptor implements WebGraphQlInterceptor {

    private final BlockingTokenService tokenService;

    public BlockingAuthenticationInterceptor(BlockingTokenService tokenService) {
        this.tokenService = tokenService;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain
    ) {
        String token = request.getHeaders().getFirst("Authorization");

        return Mono.fromCallable(() -> tokenService.authenticate(token))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(principal -> {
                    request.configureExecutionInput((input, builder) ->
                            builder.graphQLContext(context ->
                                    context.put("principal", principal)
                            ).build()
                    );
                    return chain.next(request);
                });
    }
}
~~~

`Mono.fromCallable` trì hoãn việc gọi `authenticate` cho đến khi subscribe. `subscribeOn(Schedulers.boundedElastic())` chuyển cả việc gọi blocking sang scheduler được thiết kế cho tác vụ chờ I/O. Khi authentication hoàn tất, `flatMap` tiếp tục interceptor chain.

Đây là cách tích hợp một dependency blocking vào reactive pipeline. Nó không biến dependency thành non-blocking; nó cô lập thời gian chờ trên worker thread để tránh chặn event loop.

`boundedElastic` là scheduler dùng chung và có giới hạn thread/queue. Với một dependency có giới hạn đồng thời riêng, có thể cân nhắc scheduler hoặc executor chuyên biệt để tránh tác vụ blocking của interceptor cạnh tranh không kiểm soát với các tác vụ blocking khác. Không dùng `Schedulers.parallel()` cho I/O blocking vì scheduler này dành cho tác vụ tính toán ngắn.

## 6. Vì sao không dùng Mono.just cho blocking call?

Hai cách viết sau có hành vi khác nhau:

~~~java
// Sai: lời gọi blocking chạy trước khi Mono được tạo.
Mono<Principal> unsafe = Mono.just(tokenService.authenticate(token));

// Đúng hơn: lời gọi được thực thi khi subscribe.
Mono<Principal> deferred = Mono.fromCallable(
        () -> tokenService.authenticate(token)
).subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.defer` cũng trì hoãn việc tạo publisher, nhưng bản thân nó không chuyển công việc sang thread khác:

~~~java
// Chỉ defer; blocking call vẫn chạy trên thread subscribe.
Mono<Principal> stillBlocking = Mono.defer(() ->
        Mono.just(tokenService.authenticate(token))
);
~~~

Nếu dùng `defer`, cần kết hợp scheduler phù hợp:

~~~java
Mono<Principal> scheduled = Mono.fromCallable(
        () -> tokenService.authenticate(token)
).subscribeOn(Schedulers.boundedElastic());
~~~

## 7. subscribeOn và publishOn

Hai toán tử thường bị nhầm lẫn:

| Toán tử | Tác dụng chính | Dùng trong trường hợp |
| --- | --- | --- |
| `subscribeOn(scheduler)` | Chọn scheduler cho quá trình subscribe và source phát dữ liệu | Chuyển lời gọi blocking trong `fromCallable` sang worker thread |
| `publishOn(scheduler)` | Chuyển các toán tử phía sau nó sang scheduler chỉ định | Chuyển một bước xử lý tiếp theo sang scheduler khác |

Với blocking source, `subscribeOn` thường là lựa chọn trực tiếp:

~~~java
Mono.fromCallable(() -> repository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`publishOn` đặt sau source không thể ngăn lời gọi blocking ban đầu đã chạy trên thread subscribe. Ví dụ sau vẫn có thể block trước khi chuyển scheduler:

~~~java
// Không phù hợp để offload repository.load(...).
Mono.fromCallable(() -> repository.load(id))
        .publishOn(Schedulers.boundedElastic());
~~~

## 8. Không gọi block, blockFirst hoặc blockLast trong interceptor

Không chờ reactive publisher bằng các lệnh blocking bên trong interceptor:

~~~java
// Không làm như vậy trong WebGraphQlInterceptor.
Principal principal = tokenService.authenticate(token).block();
return chain.next(request);
~~~

`block()` biến luồng reactive thành chờ đồng bộ. Trong WebFlux, nếu gọi trên event loop, thread đó bị giữ cho đến khi publisher hoàn tất. Ngay cả trong Spring MVC, việc block vẫn chiếm servlet thread và làm giảm khả năng xử lý request đồng thời.

Hãy nối publisher bằng `flatMap`:

~~~java
return tokenService.authenticate(token)
        .flatMap(principal -> {
            putPrincipalInContext(request, principal);
            return chain.next(request);
        });
~~~

Không dùng `.toFuture().get()`, `.join()`, `CountDownLatch.await()` hoặc `Thread.sleep()` để chờ kết quả trong reactive interceptor.

## 9. Kết hợp xử lý trước và sau GraphQL execution

Interceptor có thể thêm context trước khi gọi chain và quan sát response khi chain hoàn tất:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain
) {
    request.configureExecutionInput((input, builder) ->
            builder.graphQLContext(context ->
                    context.put("requestId", request.getId())
            ).build()
    );

    long startedAt = System.nanoTime();

    return chain.next(request)
            .doOnNext(response -> {
                long elapsedNanos = System.nanoTime() - startedAt;
                recordGraphQlDuration(elapsedNanos, response.getErrors().size());
            });
}
~~~

`doOnNext` dùng cho side effect đồng bộ, ngắn như cập nhật metric. Nếu bước hậu xử lý cần gọi một dịch vụ reactive khác và phải chờ kết quả, dùng `flatMap` thay vì `doOnNext`:

~~~java
return chain.next(request)
        .flatMap(response -> auditService.record(response)
                .thenReturn(response));
~~~

Đoạn code trên giả định `auditService.record` trả `Mono<Void>`. Nếu audit không phải điều kiện để trả response, có thể thiết kế luồng ghi nhận bất đồng bộ riêng; cần bảo đảm lỗi audit không vô tình làm hỏng GraphQL response nếu chính sách ứng dụng cho phép bỏ qua.

## 10. Xử lý lỗi trong reactive interceptor

Lỗi có thể phát sinh từ nhiều nguồn:

- Dependency xác thực hoặc authorization.
- Dịch vụ lấy tenant hoặc metadata.
- Logic cấu hình context.
- GraphQL execution bên trong `chain.next`.

Lỗi GraphQL execution thường được biểu diễn trong `WebGraphQlResponse` dưới dạng danh sách GraphQL errors. Lỗi xảy ra trong pipeline interceptor trước hoặc sau execution có thể kết thúc publisher bằng error signal.

Không nên dùng `onErrorResume(error -> Mono.empty())` để nuốt mọi lỗi. Cách đó có thể khiến caller nhận một luồng hoàn tất mà không có response hợp lệ. Hãy phân loại lỗi và giữ nguyên ngữ nghĩa:

~~~java
return tokenService.authenticate(token)
        .flatMap(principal -> {
            putPrincipalInContext(request, principal);
            return chain.next(request);
        })
        .doOnError(error -> log.warn(
                "GraphQL request failed before or during execution: {}",
                request.getId(), error
        ));
~~~

Nếu cần chuyển lỗi xác thực thành HTTP status cụ thể, hãy cân nhắc xử lý ở Spring Security hoặc tầng transport phù hợp. Không để interceptor tự biến lỗi thành một response thành công giả.

## 11. Thứ tự nhiều interceptor

Ứng dụng có thể đăng ký nhiều `WebGraphQlInterceptor`, ví dụ:

1. Correlation/request ID.
2. Authentication và xác định principal.
3. Tenant resolution.
4. Metrics/tracing.
5. GraphQL execution.

Thứ tự có ý nghĩa khi interceptor sau cần dữ liệu do interceptor trước đưa vào context. Có thể dùng `@Order` trên bean hoặc cấu hình thứ tự interceptor tại `WebGraphQlHandler` tùy cách ứng dụng đăng ký.

~~~java
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdInterceptor implements WebGraphQlInterceptor {
    // Add requestId to GraphQLContext before the next interceptor.
}
~~~

Không dựa vào thứ tự scan component không được bảo đảm. Hãy khai báo thứ tự rõ ràng khi các interceptor có phụ thuộc dữ liệu. Cũng cần tránh đăng ký cùng một interceptor vừa bằng component scan vừa bằng cấu hình thủ công.

## 12. Phân biệt WebGraphQlInterceptor với Servlet Filter và HandlerInterceptor

Tên gọi interceptor có thể gây nhầm lẫn vì Spring MVC cũng có `HandlerInterceptor`, còn servlet có `Filter` và WebFlux có `WebFilter`.

| Cơ chế | Phạm vi | Dùng khi |
| --- | --- | --- |
| `WebGraphQlInterceptor` | Vòng đời GraphQL web request và execution | Thêm GraphQLContext, xử lý request/response GraphQL, áp dụng logic chung cho GraphQL transport |
| Servlet `Filter` | HTTP servlet request/response | CORS, security filter chain, xử lý HTTP trước khi vào Spring MVC |
| Spring MVC `HandlerInterceptor` | Handler của Spring MVC | Logic gắn với MVC handler và servlet request |
| WebFlux `WebFilter` | Reactive web exchange | Logic web cấp thấp trước/sau WebFlux handler |

`Filter`, `HandlerInterceptor` và `WebFilter` không tự động cung cấp GraphQL-specific context. Nếu cần đưa metadata vào `GraphQLContext`, có thể bridge ở tầng web hoặc dùng `WebGraphQlInterceptor` trực tiếp. Với logic chỉ áp dụng cho GraphQL, `WebGraphQlInterceptor` thường thể hiện đúng phạm vi hơn.

## 13. Kiểm thử interceptor reactive

Có thể kiểm thử bằng Reactor `StepVerifier` ở mức unit hoặc `WebGraphQlTester` ở mức tích hợp. Ví dụ kiểm tra request ID được thêm vào context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.test.tester.WebGraphQlTester;

class RequestIdInterceptorTests {

    private final WebGraphQlHandler handler = createTestHandler();

    @Test
    void putsRequestIdIntoGraphQlContext() {
        WebGraphQlTester tester = WebGraphQlTester.builder(handler)
                .headers(headers -> headers.set("X-Request-Id", "req-123"))
                .build();

        tester.document("{ requestId }")
                .execute()
                .path("requestId")
                .entity(String.class)
                .isEqualTo("req-123");
    }
}
~~~

`createTestHandler()` đại diện cho cấu hình test có `GraphQlSource`, controller và interceptor cần thiết. Trong integration test của ứng dụng, có thể inject `WebGraphQlHandler` từ application context thay vì tự tạo.

Để kiểm tra blocking call đã được offload, dùng một service giả ghi lại `Thread.currentThread()` khi được gọi. Test xác nhận lời gọi chạy trên scheduler worker thay vì event-loop thread. Không nên assert tên thread cụ thể của `boundedElastic` nếu test phụ thuộc vào chi tiết nội bộ; có thể dùng `ThreadFactory` hoặc scheduler riêng có tên được kiểm soát.

Các trường hợp nên có:

1. Reactive dependency hoàn tất và GraphQL execution chỉ bắt đầu sau khi xác thực thành công.
2. Blocking dependency được gọi bên trong `fromCallable` trên scheduler phù hợp.
3. Lỗi từ dependency không bị nuốt và được xử lý theo chính sách đã chọn.
4. Interceptor response hook chạy sau khi `chain.next` hoàn tất.
5. Nhiều interceptor được gọi theo thứ tự cấu hình.
6. Request bị cancel không để lại tác vụ nền hoặc tài nguyên không được giải phóng.

Lưu ý: hủy subscription không bảo đảm mọi lời gọi blocking đang chạy sẽ dừng ngay lập tức. Cần đặt timeout ở client/database, giải phóng tài nguyên đúng cách và kiểm tra khả năng interrupt của dependency.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| WebFlux bị treo hoặc giảm thông lượng | Gọi blocking dependency trên event-loop thread | Dùng reactive client hoặc `Mono.fromCallable(...).subscribeOn(boundedElastic())` |
| `Mono` trả về nhưng request vẫn block | Blocking call được thực thi trước khi tạo `Mono` | Không dùng `Mono.just(blockingCall())`; dùng `fromCallable` |
| Interceptor gọi chain nhưng không chờ kết quả | Dùng `doOnNext` để gọi publisher downstream | Dùng `flatMap` và trả publisher được nối |
| Request đi vào GraphQL hai lần | Gọi `chain.next(request)` nhiều lần | Gọi chain đúng một lần cho mỗi request |
| Metadata không có trong resolver | Cấu hình context sau khi đã gọi chain hoặc dùng sai key | Ghi context trước `chain.next` và thống nhất key |
| Lỗi bị mất | Dùng `onErrorResume` trả `Mono.empty()` | Giữ error signal hoặc chuyển thành response lỗi có chủ đích |
| MVC servlet thread bị chiếm quá lâu | Thực hiện I/O blocking lâu ngay trong interceptor | Dùng async/reactive dependency hoặc offload blocking work |
| ThreadLocal không có dữ liệu trong resolver | Execution chuyển thread hoặc chạy bất đồng bộ | Truyền metadata qua GraphQLContext hoặc context propagation phù hợp |
| Audit làm hỏng response | Hậu xử lý reactive được nối như một bước bắt buộc nhưng service audit lỗi | Xác định audit có phải điều kiện trả response; xử lý lỗi theo chính sách rõ ràng |

## 15. Quy trình chọn cách viết interceptor

Khi triển khai interceptor trong Spring for GraphQL:

1. Xác định logic thuộc GraphQL request hay thuộc HTTP transport chung.
2. Nếu logic cần GraphQLContext hoặc response GraphQL, dùng `WebGraphQlInterceptor`.
3. Nếu dependency trả `Mono`/`Flux`, nối trực tiếp bằng `flatMap`, `map` và các toán tử reactive.
4. Nếu dependency blocking, ưu tiên thay bằng client reactive; nếu chưa thể, bọc bằng `Mono.fromCallable` và offload qua `Schedulers.boundedElastic()` hoặc executor phù hợp.
5. Không gọi `.block()`, `.join()` hoặc chờ đồng bộ trên reactive pipeline.
6. Đưa metadata vào `GraphQLContext` trước khi gọi `chain.next(request)`.
7. Dùng `flatMap` cho hậu xử lý bất đồng bộ; dùng `doOnNext` cho side effect ngắn.
8. Xác định thứ tự interceptor và gọi chain đúng một lần.
9. Kiểm thử reactive completion, blocking offload, lỗi, cancellation và context propagation.

`WebGraphQlInterceptor` có reactive contract trong cả Spring MVC và WebFlux. Ứng dụng cần lựa chọn cách thực thi phù hợp với dependency và thread model của transport: giữ reactive end-to-end khi có thể, hoặc cô lập blocking work trên scheduler chuyên dụng khi phải dùng thư viện đồng bộ.

## Tài liệu tham khảo

- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — WebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlInterceptor.html)
- [Spring for GraphQL — WebGraphQlHandler API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/server/WebGraphQlHandler.html)
- [Project Reactor — Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html)
- [Project Reactor — Blocking call and boundedElastic](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking)
