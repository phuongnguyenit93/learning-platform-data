# Truyền ngữ cảnh bằng Reactor Context qua các ranh giới bất đồng bộ

Trong một ứng dụng reactive, một request có thể đi qua nhiều service, repository, scheduler và callback trước khi hoàn tất. Các thành phần đó thường cần dùng chung một số thông tin xuyên suốt quá trình xử lý, chẳng hạn correlation ID, tenant, locale hoặc thông tin phục vụ tracing. Nếu truyền tất cả các giá trị này qua tham số của mọi phương thức, chữ ký hàm sẽ phình to và các lớp không liên quan phải biết về ngữ cảnh của request.

Reactor cung cấp Context để gắn dữ liệu với subscription thay vì gắn với thread. Context đi theo chuỗi reactive khi các publisher được compose đúng cách, kể cả khi pipeline chuyển thread bằng publishOn hoặc subscribeOn. Đây là điểm quan trọng với RSocket và Spring vì một tương tác có thể được xử lý bất đồng bộ trên nhiều thread.

Tuy nhiên, Reactor Context chỉ tồn tại trong tiến trình và subscription hiện tại. Nó không tự đi qua mạng RSocket, không tự xuất hiện trong một CompletableFuture độc lập và cũng không tự biến thành ThreadLocal. Muốn đi qua các ranh giới đó, ứng dụng phải truyền hoặc khôi phục ngữ cảnh một cách tường minh.

## 1. Vì sao cần Reactor Context?

Giả sử một request tra cứu đơn hàng đi qua RSocket handler, service, repository và audit service. Mỗi thành phần cần correlation ID để ghi log và tenant ID để giới hạn dữ liệu. Nếu không có context, mỗi phương thức phải nhận thêm các tham số này:

~~~java
findOrder(orderId, tenantId, correlationId)
loadItems(orderId, tenantId, correlationId)
writeAudit(orderId, tenantId, correlationId)
~~~

Khi số lượng thông tin xuyên suốt tăng lên, việc truyền tham số lặp lại làm code khó đọc và buộc các lớp trung gian phụ thuộc vào dữ liệu mà chúng không trực tiếp sử dụng.

Reactor Context giải quyết vấn đề này bằng cách gắn các cặp key-value với subscriber:

~~~java
Mono<OrderView> result = orderService.findOrder("ORD-42")
    .contextWrite(context -> context
        .put(ContextKeys.CORRELATION_ID, "req-8f21")
        .put(ContextKeys.TENANT_ID, "tenant-17")
    );
~~~

Các publisher ở phía upstream có thể đọc những giá trị đó khi subscription chạy. Service không cần thêm tham số correlation ID hoặc tenant ID vào mọi chữ ký phương thức.

## 2. Context thuộc về subscription, không thuộc về thread

Context là cấu trúc dữ liệu bất biến gắn với subscriber. Khi một subscriber đăng ký publisher, Reactor cung cấp Context cho các operator trong chuỗi. Một subscription có Context riêng; hai subscription chạy đồng thời có thể mang hai bộ giá trị khác nhau dù chúng dùng cùng một service singleton.

| Đặc điểm | Reactor Context | ThreadLocal |
|---|---|---|
| Phạm vi | Subscriber/subscription | Thread |
| Khi chuyển thread | Được truyền theo reactive chain | Không tự đi theo |
| Cập nhật | Bất biến, tạo Context mới | Thay đổi giá trị gắn với thread |
| Cách đọc | deferContextual, ContextView | ThreadLocal.get() |
| Cô lập request đồng thời | Theo subscription | Dễ nhầm nếu thread được tái sử dụng |

Context không phải một map mutable toàn cục. Mỗi lần gọi contextWrite tạo ra Context mới cho phạm vi subscription tương ứng. Vì vậy không nên lưu Context vào field của controller singleton hoặc giữ một biến currentTenant dùng chung giữa các request.

## 3. Khai báo key cho context

Nên tập trung các key dùng chung trong một lớp để tránh sai chính tả và trùng tên giữa các module. Có thể dùng object làm key thay vì chuỗi chung chung:

~~~java
public final class ContextKeys {

    private ContextKeys() {
    }

    public static final Object CORRELATION_ID = new Object();
    public static final Object TENANT_ID = new Object();
    public static final Object LOCALE = new Object();
}
~~~

Key là object dùng chung, còn value thuộc từng subscription. Nếu dùng String làm key, hãy đặt namespace rõ ràng, ví dụ com.example.orders.correlationId, để tránh va chạm với thư viện hoặc module khác.

Không nên đặt access token, mật khẩu hoặc dữ liệu bí mật vào Context chỉ vì nó tiện truy cập. Context có thể được quan sát bởi operator, hook và code trong cùng pipeline; chỉ đưa vào những giá trị thực sự cần thiết và quản lý chúng như dữ liệu nhạy cảm nếu có.

## 4. Ghi context bằng contextWrite

contextWrite ghi thêm hoặc thay thế giá trị trong Context mà subscriber cung cấp cho các operator ở phía upstream. Ví dụ:

~~~java
Mono<OrderView> result = orderService.findOrder("ORD-42")
    .contextWrite(context -> context
        .put(ContextKeys.CORRELATION_ID, "req-8f21")
        .put(ContextKeys.TENANT_ID, "tenant-17")
    );
~~~

Context được áp dụng khi publisher được subscribe, không phải lúc biến result được tạo. Điều này phù hợp với publisher lazy của Reactor: có thể xây dựng pipeline trước, rồi cung cấp ngữ cảnh tại ranh giới thực thi.

Có thể viết một helper để gắn ngữ cảnh cho một request:

~~~java
public static <T> Mono<T> withRequestContext(
    Mono<T> pipeline,
    String correlationId,
    String tenantId
) {
    return pipeline.contextWrite(context -> context
        .put(ContextKeys.CORRELATION_ID, correlationId)
        .put(ContextKeys.TENANT_ID, tenantId)
    );
}
~~~

Với Flux, cách dùng tương tự:

~~~java
Flux<OrderEvent> events = orderService.watch("ORD-42")
    .contextWrite(context -> context
        .put(ContextKeys.CORRELATION_ID, "stream-91")
        .put(ContextKeys.TENANT_ID, "tenant-17")
    );
~~~

## 5. Đọc context bằng deferContextual

Để đọc Context trong lúc subscription chạy, dùng Mono.deferContextual hoặc Flux.deferContextual. Chúng nhận ContextView, một view chỉ đọc của Context hiện tại:

~~~java
import reactor.core.publisher.Mono;

public Mono<OrderView> findOrder(String orderId) {
    return Mono.deferContextual(context -> {
        String correlationId = context.get(ContextKeys.CORRELATION_ID);
        String tenantId = context.get(ContextKeys.TENANT_ID);

        return orderRepository.findByTenantAndId(tenantId, orderId)
            .map(order -> OrderView.from(order))
            .doOnNext(order ->
                log.debug("Loaded order; correlationId={}", correlationId)
            );
    });
}
~~~

deferContextual trì hoãn việc đọc cho tới khi có subscriber và cung cấp đúng Context của subscriber đó. Đây là cách an toàn để đọc dữ liệu theo request trong service singleton.

Nếu một giá trị là tùy chọn, có thể dùng getOrDefault hoặc getOrEmpty thay vì gọi get và để thiếu key gây lỗi:

~~~java
Mono<String> currentCorrelationId = Mono.deferContextual(context ->
    Mono.just(context.getOrDefault(
        ContextKeys.CORRELATION_ID,
        "no-correlation-id"
    ))
);
~~~

Chỉ dùng giá trị mặc định khi nghiệp vụ cho phép. Với tenant hoặc danh tính bảo mật, thiếu context thường phải được xem là lỗi cấu hình hoặc lỗi xác thực, không nên tự gán một tenant mặc định.

## 6. Hiểu chiều lan truyền và vị trí của contextWrite

Một điểm dễ nhầm là contextWrite truyền Context từ phía downstream về phía upstream. Nó cung cấp Context cho publisher đứng trước nó trong chuỗi reactive.

~~~java
Mono<String> source = Mono.deferContextual(context ->
    Mono.just(context.get("region"))
);

Mono<String> result = source
    .map(region -> "Region: " + region)
    .contextWrite(context -> context.put("region", "ap-southeast-1"));
~~~

Khi subscriber đăng ký result, Context đi ngược qua các operator. deferContextual ở phía source nhìn thấy region do contextWrite cung cấp.

Ngược lại, nếu đặt contextWrite bên trong một nhánh upstream rồi mong các operator downstream đọc được giá trị mới đó, kết quả có thể khác mong đợi. Hãy nhớ quy tắc: contextWrite thay đổi Context được nhìn thấy bởi phần pipeline ở phía upstream của chính operator đó.

Context không phải dữ liệu phát qua onNext. Nó không làm thay đổi DTO hoặc payload. Nếu một hàm cần một giá trị để tạo dữ liệu đầu ra, hãy đọc Context bằng deferContextual rồi đưa giá trị đó vào phép biến đổi.

## 7. Context qua flatMap và publisher lồng nhau

Khi compose publisher bằng các toán tử Reactor như flatMap, concatMap, map hoặc then, Context của subscriber được duy trì trong chuỗi. Publisher bên trong được subscribe như một phần của pipeline đó.

~~~java
public Mono<OrderView> loadOrderWithAudit(String orderId) {
    return Mono.deferContextual(context -> {
        String correlationId = context.get(ContextKeys.CORRELATION_ID);
        String tenantId = context.get(ContextKeys.TENANT_ID);

        return orderRepository.findByTenantAndId(tenantId, orderId)
            .flatMap(order ->
                auditService.recordRead(order)
                    .thenReturn(OrderView.from(order))
            );
    });
}
~~~

flatMap nối các bước bất đồng bộ vào cùng pipeline. auditService.recordRead(order) có thể dùng Mono.deferContextual để đọc correlation ID từ Context của subscription đang thực hiện. Nhờ vậy không cần truyền correlation ID qua mọi callback.

Có thể đặt một deferContextual sâu hơn trong publisher lồng nhau:

~~~java
public Mono<Void> recordRead(Order order) {
    return Mono.deferContextual(context -> {
        String correlationId = context.get(ContextKeys.CORRELATION_ID);
        return auditRepository.insert(
            new AuditRecord(order.id(), correlationId)
        );
    });
}
~~~

Điều này hoạt động vì publisher được trả về và compose trong cùng subscription. Nếu tạo một subscription độc lập bằng subscribe() bên trong service, nó không còn tự động thuộc vòng đời và Context của pipeline cha.

## 8. Context qua publishOn và subscribeOn

publishOn chuyển việc xử lý các operator downstream sang scheduler khác. subscribeOn ảnh hưởng tới nơi subscription và nguồn upstream được thực thi. Cả hai đều có thể đổi thread, nhưng Reactor Context vẫn được duy trì qua các operator reactive chuẩn:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get(ContextKeys.CORRELATION_ID))
    )
    .publishOn(Schedulers.parallel())
    .map(id -> "processed-" + id)
    .subscribeOn(Schedulers.boundedElastic())
    .contextWrite(context ->
        context.put(ContextKeys.CORRELATION_ID, "req-8f21")
    );
~~~

Không cần tự chép Context sang một biến ThreadLocal chỉ vì pipeline chuyển scheduler. Các operator Reactor chuẩn truyền subscriber Context theo subscription, không dựa vào thread đang chạy.

Điều này không có nghĩa mọi thư viện bên ngoài đều biết Reactor Context. Một callback gọi ThreadLocal.get() hoặc một API imperative có thể không nhìn thấy dữ liệu trong Context. Khi đi qua ranh giới như vậy, cần chuyển các giá trị cần thiết một cách tường minh hoặc dùng cơ chế context propagation tương thích.

## 9. Qua ranh giới CompletableFuture và Executor

CompletableFuture không phải publisher Reactor. Nếu gọi một thư viện trả về future, đừng giả định callback bên trong future sẽ đọc được Reactor Context. Hãy lấy những giá trị cần thiết trong deferContextual rồi truyền chúng vào API imperative:

~~~java
import java.util.concurrent.CompletableFuture;
import reactor.core.publisher.Mono;

public Mono<LegacyResult> callLegacy(
    String orderId
) {
    return Mono.deferContextual(context -> {
        String correlationId =
            context.get(ContextKeys.CORRELATION_ID);

        CompletableFuture<LegacyResult> future =
            legacyClient.fetchAsync(orderId, correlationId);

        return Mono.fromFuture(future);
    });
}
~~~

Tương tự, khi chạy một lời gọi blocking trên executor, hãy capture giá trị trước khi chuyển scheduler:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<LegacyResult> callBlocking(
    String orderId
) {
    return Mono.deferContextual(context -> {
        String correlationId =
            context.get(ContextKeys.CORRELATION_ID);

        return Mono.fromCallable(() ->
                legacyClient.fetch(orderId, correlationId)
            )
            .subscribeOn(Schedulers.boundedElastic());
    });
}
~~~

Trong hai ví dụ, callback không cần đọc Reactor Context trực tiếp. Giá trị đã được đọc ở ranh giới reactive và truyền như một tham số tường minh sang API bên ngoài. Đây thường là cách đơn giản, dễ kiểm thử và ít phụ thuộc cấu hình nhất.

Nếu cần bridge nhiều giá trị vào ThreadLocal của thư viện cũ, có thể dùng Micrometer Context Propagation với các accessor được đăng ký và cấu hình tương ứng. contextCapture() hoặc chế độ automatic propagation của Reactor có thể hỗ trợ tích hợp này tùy phiên bản và cấu hình. Không nên bật hoặc dựa vào cơ chế tự động mà chưa xác minh dependency, accessor và hành vi khi ứng dụng subscribe.

## 10. Tránh subscribe độc lập bên trong pipeline

Một lỗi phổ biến là gọi subscribe() bên trong service để khởi chạy công việc phụ rồi trả về một publisher khác:

~~~java
// Không nên: subscription audit tách khỏi pipeline của request.
public Mono<Order> findOrder(String orderId) {
    auditService.recordRead(orderId).subscribe();
    return orderRepository.findById(orderId);
}
~~~

Subscription audit độc lập có thể không nhận Context của request cha, không bị hủy cùng request cha và có lỗi không được truyền về caller. Nó cũng có thể tiếp tục chạy sau khi client đã hủy tương tác RSocket.

Hãy compose công việc phụ bằng then, flatMap hoặc when:

~~~java
public Mono<Order> findOrder(String orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            auditService.recordRead(order)
                .thenReturn(order)
        );
}
~~~

Khi auditService.recordRead đọc Context qua deferContextual, nó nhìn thấy Context của cùng request. Lỗi và cancellation cũng được quản lý trong cùng pipeline.

## 11. Reactor Context không tự truyền qua mạng RSocket

Context chỉ gắn với subscription trong một tiến trình. Khi client gửi frame RSocket tới server, Reactor Context không tự được serialize thành metadata hoặc payload. Nếu correlation ID, tenant hoặc trace context cần đi qua mạng, ứng dụng phải đưa thông tin đó vào giao thức truyền tải.

Một cách đơn giản là đưa correlation ID vào request envelope:

~~~java
public record OrderLookupRequest(
    String orderId,
    String correlationId
) {
}
~~~

Client đọc Context rồi tạo payload RSocket:

~~~java
public Mono<OrderView> lookupRemotely(String orderId) {
    return Mono.deferContextual(context -> {
        String correlationId =
            context.get(ContextKeys.CORRELATION_ID);

        return requester.route("orders.lookup")
            .data(new OrderLookupRequest(orderId, correlationId))
            .retrieveMono(OrderView.class);
    });
}
~~~

Ở server, handler lấy giá trị từ envelope rồi tạo Context cho pipeline xử lý cục bộ:

~~~java
@MessageMapping("orders.lookup")
public Mono<OrderView> lookup(OrderLookupRequest request) {
    return orderService.findOrder(request.orderId())
        .contextWrite(context -> context.put(
            ContextKeys.CORRELATION_ID,
            request.correlationId()
        ));
}
~~~

Nếu dùng metadata RSocket thay cho request envelope, hãy serialize correlation ID hoặc tracing fields thành metadata entry với MIME type phù hợp, rồi đọc chúng tại adapter phía nhận. Route metadata, authentication metadata và custom tracing metadata có thể cùng nằm trong composite metadata nhưng phải có MIME type và quy tắc xử lý rõ ràng.

Không đưa bearer token vào correlation field hoặc log. Danh tính bảo mật cần dùng cơ chế authentication metadata và Spring Security tương ứng; correlation ID chỉ dùng để liên kết log và trace.

## 12. Kết hợp với Spring Security

Trong ứng dụng reactive, Spring Security lưu SecurityContext trong Reactor Context. Vì vậy, không nên lấy danh tính người dùng từ một ThreadLocal tùy chỉnh trong service reactive. Có thể đọc Authentication qua ReactiveSecurityContextHolder:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<AccountView> currentAccount() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
            accountService.findForSubject(authentication.getName())
        );
}
~~~

Spring Security cung cấp cơ chế thiết lập và truyền security context theo reactive chain. Khi handler được gọi qua RSocket Security, interceptor xác thực thông tin bảo mật của tương tác và đặt Authentication vào ngữ cảnh reactive phù hợp. Ứng dụng nên dùng ReactiveSecurityContextHolder hoặc cơ chế tích hợp của Spring thay vì tự sao chép principal vào một field dùng chung.

Nếu một request cần cả correlation ID và security context, chúng có thể cùng tồn tại trong Reactor Context nhưng có mục đích riêng. Không dùng correlation ID để xác định quyền, và không dùng giá trị tenant do client tự gửi làm tenant đã được xác thực.

## 13. Kiểm thử context bằng StepVerifier

Có thể kiểm tra việc ghi và đọc Context mà không cần mở kết nối:

~~~java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class RequestContextTest {

    @Test
    void shouldReadCorrelationIdFromContext() {
        Mono<String> pipeline = Mono.deferContextual(context ->
            Mono.just(context.get(ContextKeys.CORRELATION_ID))
        );

        StepVerifier.create(
                pipeline.contextWrite(context ->
                    context.put(ContextKeys.CORRELATION_ID, "test-123")
                )
            )
            .expectNext("test-123")
            .verifyComplete();
    }
}
~~~

Nên kiểm thử thêm rằng hai subscription đồng thời không chia sẻ tenant:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> tenant = Mono.deferContextual(context ->
    Mono.just(context.get(ContextKeys.TENANT_ID))
);

StepVerifier.create(Mono.zip(
        tenant.contextWrite(context ->
            context.put(ContextKeys.TENANT_ID, "tenant-A")
        ),
        tenant.contextWrite(context ->
            context.put(ContextKeys.TENANT_ID, "tenant-B")
        )
    ))
    .expectNextMatches(pair ->
        "tenant-A".equals(pair.getT1())
            && "tenant-B".equals(pair.getT2())
    )
    .verifyComplete();
~~~

Kết quả của phép zip phải giữ tenant-A ở subscription thứ nhất và tenant-B ở subscription thứ hai. Đây là kiểm thử quan trọng với service singleton được nhiều request RSocket gọi đồng thời.

Với ranh giới CompletableFuture hoặc Executor, hãy kiểm thử cả giá trị đã được capture và truyền sang callback. Với RSocket client/server, integration test nên xác nhận correlation ID được serialize qua metadata hoặc payload và được dựng lại vào Context ở phía nhận; kiểm thử Context nội bộ không chứng minh dữ liệu đã tự đi qua mạng.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| deferContextual báo thiếu key | Chưa có contextWrite ở downstream phù hợp hoặc key sai | Kiểm tra vị trí ghi Context và thống nhất key |
| Context có ở service nhưng mất trong callback thư viện cũ | Callback không chạy trong reactive subscription | Capture giá trị rồi truyền tường minh hoặc dùng context propagation đã cấu hình |
| Context mất sau khi tự gọi subscribe() | Tạo subscription độc lập | Compose publisher vào pipeline cha |
| Dữ liệu tenant bị lẫn giữa request | Lưu tenant trong field mutable dùng chung | Đưa tenant vào Context theo subscription và xác thực nguồn giá trị |
| Mong Context tự đi qua RSocket nhưng server không thấy | Context không được serialize qua mạng | Gửi tracing/custom metadata hoặc envelope và dựng Context ở server |
| ThreadLocal trả về giá trị rỗng sau publishOn | Thread đã thay đổi và không có bridge | Dùng Reactor Context; chỉ bridge ThreadLocal khi thư viện thực sự yêu cầu |
| Context có giá trị cũ | contextWrite đặt sai vị trí hoặc key bị ghi đè | Kiểm tra chiều downstream-to-upstream và thứ tự ghi |

## 15. Quy tắc thiết kế

Khi thiết kế một luồng dữ liệu reactive, hãy xác định rõ:

1. Giá trị nào thuộc request/subscription, chẳng hạn correlation ID hoặc tenant đã xác thực?
2. Thành phần nào tạo giá trị và tại ranh giới nào cần gọi contextWrite?
3. Thành phần nào cần đọc giá trị và có thể dùng deferContextual hay ReactiveSecurityContextHolder?
4. Pipeline có đi qua publisher lồng nhau, scheduler, Future hoặc API imperative không?
5. Nếu qua mạng RSocket, giá trị nào phải được serialize thành metadata hoặc payload?
6. Giá trị nào là dữ liệu bảo mật và cần được xử lý bằng cơ chế security thay vì custom context?

Giữ Context nhỏ, dùng key có namespace, không lưu trạng thái mutable theo người dùng trong singleton và compose publisher thay vì tự subscribe. Những nguyên tắc này giúp ngữ cảnh đi đúng request ngay cả khi nhiều tương tác chạy đồng thời trên cùng kết nối RSocket.

## 16. Kết luận

Reactor Context là nơi lưu ngữ cảnh gắn với subscription trong một pipeline reactive. contextWrite cung cấp giá trị cho phần upstream, còn deferContextual đọc giá trị trong lúc subscription chạy. Context được duy trì qua các operator Reactor và scheduler switch, nhưng không tự đi vào ThreadLocal, subscription độc lập, CompletableFuture hoặc frame RSocket.

Khi qua API imperative, hãy capture và truyền các giá trị cần thiết một cách tường minh hoặc dùng Micrometer Context Propagation đã cấu hình. Khi qua mạng RSocket, hãy gửi tracing/custom metadata hoặc request envelope rồi dựng Context ở phía nhận. Với danh tính bảo mật, dùng Spring Security reactive context. Nhờ phân biệt đúng các ranh giới này, ứng dụng có thể giữ correlation, tenant và principal đúng với từng request mà không làm rò rỉ dữ liệu giữa các tương tác đồng thời.
