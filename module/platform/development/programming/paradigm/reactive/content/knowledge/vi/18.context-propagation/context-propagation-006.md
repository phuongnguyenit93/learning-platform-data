# Kết nối ngữ cảnh với ghi log, bảo mật và truy vết

Một request reactive có thể đi qua nhiều publisher, đổi thread bằng scheduler, gọi dịch vụ khác và kết hợp kết quả từ nhiều nguồn. Khi điều tra một lỗi hoặc kiểm tra quyền truy cập, ứng dụng cần biết các bước đó thuộc request nào, người dùng nào và trace nào. Trong ứng dụng đồng bộ, thông tin này thường được đặt trong ThreadLocal, chẳng hạn MDC của logging hoặc SecurityContextHolder. Nhưng pipeline reactive không bảo đảm một request luôn chạy trên cùng một thread. Vì vậy, dựa vào ThreadLocal đơn thuần có thể làm mất correlation ID, ghi log sai request hoặc đọc nhầm ngữ cảnh bảo mật.

Reactor cung cấp Reactor Context để mang dữ liệu theo subscription. Context cho phép các toán tử đọc metadata như request ID, tenant ID hoặc thông tin cần thiết cho tích hợp thư viện. Spring Security reactive sử dụng cơ chế này để cung cấp SecurityContext; Micrometer Context Propagation và các tích hợp tracing giúp kết nối ngữ cảnh reactive với thư viện dựa trên ThreadLocal. Hiểu cách các lớp này phối hợp giúp giữ log, bảo mật và truy vết nhất quán trong pipeline Mono/Flux.

## 1. Vì sao ThreadLocal không đủ cho pipeline reactive?

ThreadLocal gắn dữ liệu với thread hiện tại. Cách này hoạt động tốt trong mô hình request-per-thread: một request được xử lý trên một thread, và các hàm gọi tiếp theo có thể đọc dữ liệu từ ThreadLocal đó.

Trong Reactor, một pipeline có thể chuyển thread:

~~~java
Mono<Result> result = service.load()
    .publishOn(Schedulers.parallel())
    .map(this::transform);
~~~

Nguồn có thể phát trên một thread, còn bước map chạy trên scheduler khác. Với flatMap, nhiều publisher con có thể chạy đồng thời. Một request không nhất thiết có một thread duy nhất trong suốt vòng đời. Nếu đặt request ID vào ThreadLocal trước khi subscribe rồi đọc nó trong map, giá trị có thể không tồn tại trên thread đang chạy map. Nếu một thread được tái sử dụng, giá trị cũ còn sót lại cũng có thể bị nhìn thấy bởi tác vụ khác nếu không được khôi phục và xóa đúng cách.

Các rủi ro chính:

- **Mất correlation:** log ở bước bất đồng bộ không có request ID hoặc trace ID.
- **Gắn nhầm ngữ cảnh:** thread pool tái sử dụng thread và giữ giá trị từ tác vụ trước.
- **Rò rỉ danh tính:** mã nghiệp vụ đọc ThreadLocal không đúng request và áp dụng sai quyền.
- **Khó kiểm thử:** kết quả phụ thuộc scheduler và cách thread được lên lịch.

ThreadLocal vẫn có vai trò trong các thư viện logging hoặc tracing cũ, nhưng nó cần được kết nối với mô hình context của reactive một cách có kiểm soát.

## 2. Reactor Context là metadata gắn với subscription

Reactor Context là một cấu trúc key-value bất biến được truyền theo subscription. Nó không phải payload của luồng và không làm thay đổi kiểu dữ liệu mà publisher phát. Context phù hợp để mang metadata xuyên suốt pipeline, ví dụ:

- Request ID hoặc correlation ID.
- Tenant ID sau khi đã xác thực.
- Thông tin principal hoặc SecurityContext do Spring Security quản lý.
- Trace/span context và baggage do thư viện tracing cung cấp.
- Một cờ kỹ thuật hoặc thông tin chẩn đoán cần thiết cho các toán tử.

Context được tạo hoặc cập nhật bằng `contextWrite`, và được đọc bằng `deferContextual` hoặc từ `Signal` trong một số hook. Ví dụ:

~~~java
Mono<String> requestDescription = Mono.deferContextual(context -> {
    String requestId = context.get("requestId");
    return Mono.just("Đang xử lý request " + requestId);
});

Mono<String> result = requestDescription
    .contextWrite(context -> context.put("requestId", "req-42"));
~~~

`deferContextual` trì hoãn việc đọc context đến lúc có subscription. `contextWrite` thêm request ID vào Context của subscription đó. Khi subscribe, giá trị được đọc từ Context và dùng để tạo kết quả.

### Context không phải một map mutable dùng chung

Các thao tác `put`, `delete` và `putAll` tạo Context mới. Một subscription có thể có Context riêng mà không sửa Context của subscription khác. Đây là đặc điểm quan trọng khi nhiều request chạy đồng thời.

~~~java
Flux<String> descriptions = Flux.just("A", "B")
    .flatMap(name ->
        Mono.deferContextual(context ->
            Mono.just(name + " / " + context.get("requestId"))
        )
        .contextWrite(context ->
            context.put("requestId", "req-" + name)
        )
    );
~~~

Mỗi publisher con ghi một request ID riêng trong phạm vi Context của nó. Không cần dùng một biến mutable toàn cục để lưu ID hiện tại. Với pipeline thực tế, Context nên được đặt tại ranh giới request và chỉ ghi đè trong phạm vi có chủ đích.

## 3. Chiều truyền của Context và vị trí contextWrite

Một điểm dễ nhầm là dữ liệu đi từ publisher xuống subscriber, còn Context được cung cấp từ subscriber ngược lên publisher khi subscription được thiết lập. Do đó, `contextWrite` thường đặt ở phía downstream của toán tử cần đọc Context.

~~~java
Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.just(context.get("correlationId"))
    )
    .contextWrite(context ->
        context.put("correlationId", "corr-1001")
    );
~~~

Khi subscription bắt đầu, `contextWrite` cập nhật Context mà phần upstream nhìn thấy. `deferContextual` nằm phía upstream nên đọc được giá trị `corr-1001`.

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    A[Subscriber] -->|Subscription và Context| B[contextWrite]
    B -->|Context đã cập nhật| C[deferContextual]
    C -->|onNext / onError / onComplete| B
    B --> D[Subscriber nhận tín hiệu]
~~~

Context đi ngược chiều subscription; các tín hiệu dữ liệu đi theo chiều ngược lại. Đây là lý do `contextWrite` không giống một phép map dữ liệu. Nó thay đổi metadata mà các toán tử upstream có thể đọc.

### Thứ tự nhiều contextWrite

Khi có nhiều `contextWrite`, thứ tự trong chuỗi toán tử ảnh hưởng giá trị cuối cùng mà upstream quan sát. Một Context gần subscriber hơn được áp dụng trước khi subscription tiếp tục đi upstream; một contextWrite ở phía upstream có thể tiếp tục cập nhật hoặc ghi đè key trước khi toán tử nguồn đọc nó. Nếu cùng một key được đặt ở nhiều nơi, hãy làm rõ nơi nào sở hữu key đó và tránh ghi đè ngầm.

Nên dùng hằng số cho key thay vì rải chuỗi literal:

~~~java
static final String REQUEST_ID = "requestId";
static final String TENANT_ID = "tenantId";
~~~

Nếu cần giá trị có kiểu và tránh xung đột tên, có thể dùng một object key riêng hoặc kiểu wrapper. Không nên dùng key chung chung như `user` hoặc `id` trong thư viện dùng chung nếu có nguy cơ va chạm với context của thành phần khác.

## 4. Đưa correlation ID vào Context ở ranh giới request

Correlation ID thường được lấy từ header đã được kiểm tra hoặc được tạo tại gateway/server. Hãy đưa nó vào Context tại ranh giới xử lý request, để các service và operator phía trong có thể đọc cùng một giá trị.

Ví dụ minh họa một handler WebFlux:

~~~java
Mono<ServerResponse> handle(ServerRequest request) {
    String requestId = validatedRequestId(request);

    return orderService.findOrder(request.pathVariable("id"))
        .flatMap(order -> ServerResponse.ok().bodyValue(order))
        .contextWrite(context ->
            context.put(REQUEST_ID, requestId)
        );
}
~~~

`validatedRequestId` đại diện cho logic xác thực hoặc tạo ID ở ranh giới HTTP. Không nên tin mọi giá trị header do client gửi mà không có giới hạn độ dài, ký tự hợp lệ và chính sách chống giả mạo. Correlation ID phục vụ quan sát; nó không phải bằng chứng xác thực người dùng.

Trong Spring WebFlux, có thể đặt Context trong một WebFilter để mọi publisher phía sau nhận metadata chung. Cách triển khai cụ thể phụ thuộc cách ứng dụng tạo response và quản lý filter chain; điều quan trọng là Context phải được gắn vào publisher được trả về từ filter, thay vì ghi vào ThreadLocal rồi hy vọng thread không đổi.

## 5. Đưa Context vào log bằng MDC

MDC của SLF4J thường dựa trên ThreadLocal. Reactor Context không tự động đồng nghĩa MDC luôn có giá trị trên mọi thread. Có hai hướng thường dùng:

1. Đọc Context tại vị trí ghi log và mở MDC scope trong thời gian thực hiện log.
2. Dùng Micrometer Context Propagation để kết nối Reactor Context với ThreadLocal của thư viện logging, theo cấu hình và phiên bản phù hợp.

Với cách thứ nhất, có thể dùng `doOnEach` để đọc Context của signal và đặt MDC tạm thời:

~~~java
Flux<Order> loggedOrders = orderService.findOrders()
    .doOnEach(signal -> {
        if (!signal.isOnNext()) {
            return;
        }

        String requestId = signal.getContextView()
            .getOrDefault(REQUEST_ID, "unknown");

        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("requestId", requestId)) {
            log.info("Đã nhận order {}", signal.get());
        }
    });
~~~

`MDC.putCloseable` giúp khôi phục/xóa giá trị MDC sau khối ghi log, tránh để giá trị rò rỉ sang tác vụ tiếp theo dùng cùng thread. Đặt hook ở vị trí mà signal có Context mong muốn; `contextWrite` phía downstream có thể cung cấp Context cho hook upstream.

Không nên đặt MDC một lần ở đầu request rồi giả định nó tồn tại đến cuối pipeline. Nếu callback chạy trên thread khác, MDC có thể không được mang theo. Cũng không nên ghi log trong một callback dài trong khi MDC vẫn được giữ mở; hãy giới hạn scope đúng vào thao tác log.

## 6. Tự động khôi phục ThreadLocal bằng Micrometer Context Propagation

Nhiều thư viện quan sát và logging cũ vẫn đọc ThreadLocal. Micrometer Context Propagation cung cấp cơ chế capture và restore các giá trị ThreadLocal được đăng ký, để chúng có thể phối hợp với Reactor Context.

Các thành phần thường gặp:

- `ThreadLocalAccessor`: mô tả cách đọc, đặt và xóa một ThreadLocal.
- `ContextRegistry`: đăng ký các accessor để thư viện có thể capture/restore.
- `contextCapture()`: capture các ThreadLocal đã đăng ký tại thời điểm subscribe và đưa giá trị vào Reactor Context.
- `Hooks.enableAutomaticContextPropagation()`: bật chế độ tự động khôi phục context propagation cho các subscription mới trong Reactor, khi ứng dụng đã cấu hình dependency và accessor phù hợp.

Ví dụ đăng ký một ThreadLocal tùy chỉnh:

~~~java
ContextRegistry.getInstance().registerThreadLocalAccessor(
    REQUEST_ID,
    requestIdThreadLocal::get,
    requestIdThreadLocal::set,
    requestIdThreadLocal::remove
);
~~~

Tên và overload API cần đối chiếu với phiên bản Micrometer Context Propagation trong dependency management của ứng dụng. Sau khi accessor được đăng ký, `contextCapture()` có thể đưa giá trị ThreadLocal hiện tại vào Reactor Context khi subscribe:

~~~java
Mono<Result> result = service.load()
    .contextCapture();
~~~

Nếu dùng automatic context propagation, cấu hình hook thường được bật một lần lúc khởi động ứng dụng, không bật lặp lại trong từng request:

~~~java
Hooks.enableAutomaticContextPropagation();
~~~

Hãy bật cơ chế này theo hướng dẫn của phiên bản Reactor/Micrometer đang dùng và kiểm thử trên các ranh giới scheduler, callback và thư viện tích hợp. Automatic propagation có thể có chi phí capture/restore; chỉ đăng ký các ThreadLocal thực sự cần thiết. Không coi nó là bảo đảm cho mọi executor hoặc callback tùy chỉnh không tích hợp với cơ chế propagation.

### Khi nào dùng contextCapture?

`contextCapture()` hữu ích khi một thư viện imperative đặt metadata vào ThreadLocal trước khi subscribe publisher, và pipeline cần mang metadata đó vào Reactor Context. Nó capture ở thời điểm subscribe, không phải ở thời điểm khai báo publisher. Nếu giá trị ThreadLocal thay đổi sau khi publisher được subscribe, Context đã capture không tự cập nhật theo thay đổi đó.

Trong ứng dụng mới, ưu tiên truyền metadata qua Reactor Context và chỉ bridge sang ThreadLocal ở ranh giới cần tích hợp. Điều này làm rõ ownership và tránh phụ thuộc vào trạng thái thread.

## 7. Bảo mật: đọc SecurityContext từ reactive context

Spring Security WebFlux lưu SecurityContext trong Reactor Context để danh tính được giữ đúng qua pipeline bất đồng bộ. Trong code reactive, dùng `ReactiveSecurityContextHolder` để lấy thông tin xác thực:

~~~java
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
~~~

Đoạn mã đọc Authentication gắn với subscription hiện tại. Nó không cần giả định request luôn chạy trên thread đã xác thực ban đầu.

Trong ứng dụng Spring Security, filter chain chịu trách nhiệm xác thực và thiết lập SecurityContext. Thông thường, code nghiệp vụ nên đọc context do framework cung cấp thay vì tự tạo hoặc ghi đè authentication. Nếu test hoặc một integration đặc biệt cần thiết lập context thủ công, Spring Security có các helper như `ReactiveSecurityContextHolder.withAuthentication(authentication)` để gắn Authentication vào Context:

~~~java
Mono<String> secured = currentUsername
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );
~~~

Chỉ dùng cách thiết lập thủ công trong ranh giới được kiểm soát, ví dụ test hoặc adapter đã xác minh danh tính. Không lấy username từ header tùy ý rồi đặt thành Authentication. Context là phương tiện truyền dữ liệu; nó không tự xác thực dữ liệu được đưa vào.

### Không chuyển reactive SecurityContext sang ThreadLocal tùy tiện

`SecurityContextHolder` trong mô hình imperative thường dựa trên ThreadLocal. Trong WebFlux, không nên gọi API imperative này để lấy principal ở một callback bất kỳ rồi giả định nó đúng. Dùng `ReactiveSecurityContextHolder` trong pipeline reactive. Nếu phải gọi thư viện imperative cần SecurityContextHolder, dùng cơ chế context propagation được Spring/Micrometer hỗ trợ và giới hạn scope khôi phục. Không lưu Authentication trong biến static hoặc singleton mutable.

## 8. Truy vết phân tán: trace context và span

Tracing phân tán liên kết các thao tác trong nhiều service thành một trace. Một request HTTP có thể tạo server span, gọi database tạo client span, rồi gọi service khác tạo thêm span. Khi pipeline chuyển thread hoặc kết hợp nhiều publisher, trace context cần được truyền đúng để span con thuộc đúng trace và parent.

Trong hệ sinh thái Spring hiện đại, Micrometer Observation và Micrometer Tracing có thể tích hợp với Reactor và WebFlux. Spring Boot thường cấu hình các thành phần observation/tracing dựa trên dependency và cấu hình ứng dụng. Hãy ưu tiên cơ chế instrumentation chính thức của stack thay vì tự tạo trace ID hoặc tự gắn span bằng ThreadLocal.

Các khái niệm cần phân biệt:

| Khái niệm | Mục đích |
| --- | --- |
| Trace ID | Định danh toàn bộ hành trình của một request qua nhiều service |
| Span ID | Định danh một thao tác cụ thể trong trace |
| Parent span | Liên kết thao tác hiện tại với thao tác gọi nó |
| Baggage | Metadata được truyền cùng trace theo chính sách propagation |
| Correlation ID | Mã ứng dụng dùng để tìm log hoặc liên kết sự kiện; có thể khác trace ID |

Không nên dùng correlation ID thay thế trace ID nếu hệ thống tracing đã có định danh riêng. Cũng không nên đưa dữ liệu cá nhân, token hoặc thông tin nhạy cảm vào baggage vì nó có thể được truyền qua nhiều service và xuất hiện trong telemetry.

### Không tự tạo span thủ công nếu instrumentation đã làm việc đó

Nếu WebClient, database driver hoặc framework đã được instrument, mỗi request có thể đã tạo span phù hợp. Tạo thêm span thủ công cho cùng một thao tác có thể làm trace bị lặp hoặc sai cấu trúc. Chỉ tạo span/Observation thủ công khi có một thao tác nghiệp vụ đáng được đo riêng và chưa được instrumentation tự động bao phủ.

Nếu một callback bên ngoài Reactor cần trace context, hãy kiểm tra adapter có tích hợp Micrometer Context Propagation hay không. Nếu không, cần bridge context ở ranh giới callback bằng API phù hợp; không truyền một ThreadLocal global dùng chung giữa các request.

## 9. Context qua publishOn, subscribeOn và flatMap

Reactor Context gắn với subscription, không gắn cố định với một thread. Vì vậy, các toán tử scheduler như `publishOn` và `subscribeOn` không làm mất Reactor Context trong pipeline Reactor:

~~~java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get(REQUEST_ID))
    )
    .publishOn(Schedulers.parallel())
    .map(requestId -> "processed " + requestId)
    .contextWrite(context ->
        context.put(REQUEST_ID, "req-900")
    );
~~~

Context vẫn có thể được đọc trong các operator Reactor sau khi đổi scheduler. Điều này khác với ThreadLocal: ThreadLocal cần được restore trên thread đang thực thi nếu thư viện imperative muốn đọc nó.

Với `flatMap`, mỗi publisher con kế thừa subscriber context theo semantics của Reactor. Nếu cần thêm metadata riêng cho một nhánh, có thể dùng `contextWrite` trên publisher con:

~~~java
Flux<Result> results = ids.flatMap(id ->
    service.load(id)
        .contextWrite(context ->
            context.put("operationId", "load-" + id)
        )
);
~~~

Context riêng cho nhánh giúp ghi nhận operation ID mà không sửa Context của nhánh khác. Tránh lưu một object mutable dùng chung trong Context rồi sửa nó ở nhiều nhánh đồng thời; Context bất biến không làm cho object bên trong tự trở nên bất biến.

## 10. Thiết kế key và dữ liệu Context an toàn

Context được truyền theo subscription nên mọi dữ liệu đặt vào đó có thể được các toán tử upstream đọc. Chỉ lưu những gì cần cho xử lý và quan sát.

Khuyến nghị:

- Dùng key có tên rõ ràng hoặc object key riêng, tránh va chạm.
- Dùng kiểu dữ liệu bất biến, nhỏ và có vòng đời phù hợp với request.
- Phân biệt metadata đã xác thực với dữ liệu do client gửi.
- Không lưu password, access token, refresh token hoặc secret trong Context.
- Không dùng Context thay database, cache hoặc state store.
- Không lưu collection lớn hoặc object graph giữ nhiều tài nguyên.
- Không dùng một key tenant/user để tự cấp quyền; authorization vẫn phải được kiểm tra tại service/repository.
- Quy định rõ nơi đặt và nơi được phép ghi đè từng key.

Context có thể mang tenant ID đã được xác thực để repository thêm điều kiện lọc. Tuy nhiên, repository vẫn phải kiểm tra tenant scope tại ranh giới truy cập dữ liệu; không tin một tenant ID tùy ý nếu nó không đến từ danh tính đã xác thực.

## 11. Ví dụ kết hợp correlation logging và security context

Một service có thể cần đọc username từ Spring Security và request ID từ Reactor Context để ghi log:

~~~java
Mono<Order> loadOrder(String orderId) {
    return Mono.zip(
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName),
            Mono.deferContextual(context ->
                Mono.just(context.getOrDefault(REQUEST_ID, "unknown"))
            )
        )
        .doOnNext(tuple -> {
            try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("requestId", tuple.getT2())) {
                log.info("User {} đang tải order {}",
                    tuple.getT1(), orderId);
            }
        })
        .then(orderRepository.findById(orderId));
}
~~~

Đây là ví dụ về cách đọc hai loại ngữ cảnh trong một pipeline. Trong ứng dụng thực tế, nên tránh gọi subscribe() bên trong service; trả publisher cho caller để framework quản lý subscription và cancellation. Nếu cần bảo đảm authorization, phải kiểm tra quyền truy cập order theo principal trước khi trả dữ liệu. Ghi username vào log không thay thế kiểm tra quyền.

Một thiết kế thường tốt hơn là dùng một service authorization riêng, rồi mới truy vấn dữ liệu:

~~~java
Mono<Order> loadAuthorizedOrder(String orderId) {
    return authorizationService.currentUserCanRead(orderId)
        .filter(Boolean::booleanValue)
        .switchIfEmpty(Mono.error(new AccessDeniedException("Không có quyền")))
        .then(orderRepository.findById(orderId));
}
~~~

Context giúp truyền principal và request metadata; logic nghiệp vụ vẫn cần xác minh quyền ở nơi phù hợp.

## 12. Kiểm thử Reactor Context

StepVerifier hỗ trợ tạo subscription với Context ban đầu thông qua StepVerifierOptions. Cách này giúp kiểm tra publisher đọc đúng metadata mà không cần ThreadLocal:

~~~java
Mono<String> requestId = Mono.deferContextual(context ->
    Mono.just(context.get(REQUEST_ID))
);

StepVerifier.create(
        requestId,
        StepVerifierOptions.create()
            .withInitialContext(Context.of(REQUEST_ID, "test-42"))
    )
    .expectNext("test-42")
    .verifyComplete();
~~~

Có thể kiểm tra Context riêng cho từng publisher con:

~~~java
Flux<String> values = Flux.just("A", "B")
    .flatMap(value ->
        Mono.deferContextual(context ->
            Mono.just(value + ":" + context.get("branch"))
        )
        .contextWrite(context ->
            context.put("branch", value)
        )
    );

StepVerifier.create(values)
    .expectNextCount(2)
    .verifyComplete();
~~~

Nếu cần xác minh thứ tự output, dùng expectNext với giá trị cụ thể hoặc expectNextMatches. Với flatMap, thứ tự kết quả có thể không ổn định nếu publisher con bất đồng bộ; test nên chỉ khẳng định thứ tự khi pipeline có bảo đảm như concatMap hoặc nguồn đồng bộ.

### Kiểm thử ThreadLocal bridge

Khi dùng Micrometer Context Propagation, cần test riêng:

1. Giá trị ThreadLocal được capture ở thời điểm subscribe như mong đợi.
2. Giá trị được restore khi callback chạy trên scheduler khác.
3. ThreadLocal được reset sau callback để không rò rỉ sang tác vụ tiếp theo.
4. Hai subscription đồng thời không nhìn thấy giá trị của nhau.
5. Cancellation và error vẫn khôi phục trạng thái thread đúng cách.

Các test này cần chạy với scheduler và thư viện thực tế của ứng dụng. Một test chỉ chạy Mono.just đồng bộ không đủ để chứng minh context bridge đúng khi có publishOn, flatMap hoặc callback từ thư viện ngoài.

## 13. Những lỗi thường gặp

- **Dùng ThreadLocal như context chính trong reactive code:** thread có thể thay đổi; dùng Reactor Context cho metadata theo subscription.
- **Đặt contextWrite trước sai vị trí:** toán tử cần đọc Context có thể nằm downstream của nơi ghi; nhớ Context đi ngược chiều subscription.
- **Nghĩ Context là payload:** Context mang metadata của subscription, không thay thế giá trị phát qua onNext.
- **Lưu object mutable trong Context:** các nhánh đồng thời có thể cùng sửa object; ưu tiên giá trị bất biến.
- **Đặt MDC mà không khôi phục:** thread pool tái sử dụng có thể làm log request sau nhận nhầm request ID.
- **Cho rằng publishOn tự chuyển ThreadLocal:** scheduler chuyển thread; ThreadLocal cần bridge riêng.
- **Tự đặt Authentication từ header không tin cậy:** Context không xác thực danh tính; để Spring Security xác thực và thiết lập SecurityContext.
- **Dùng SecurityContextHolder imperative trong WebFlux:** dùng ReactiveSecurityContextHolder hoặc cơ chế bridge được hỗ trợ.
- **Tự tạo trace ID khi tracing đã quản lý:** có thể phá liên kết parent/child hoặc tạo trace trùng.
- **Đưa secret vào baggage hoặc Context:** metadata có thể được truyền rộng và xuất hiện trong log/telemetry.
- **Dùng Context thay authorization:** phải kiểm tra quyền ở tầng nghiệp vụ và truy cập dữ liệu.
- **Giả định callback bên ngoài tự nhận Reactor Context:** tích hợp ngoài Reactor cần adapter hoặc context propagation bridge.

## 14. Quy trình thiết kế context cho một request

Trước khi thêm metadata vào pipeline, hãy xác định:

1. Thông tin đó là payload nghiệp vụ hay metadata của subscription?
2. Nguồn nào tạo và xác thực giá trị?
3. Key nào được dùng và thành phần nào sở hữu key?
4. Các operator nào cần đọc giá trị?
5. Có thư viện ThreadLocal nào cần bridge không?
6. Logging cần request ID, trace ID hay cả hai?
7. Spring Security đã thiết lập SecurityContext trong reactive context chưa?
8. Tracing đã được instrumentation tự động quản lý chưa?
9. Có dữ liệu nhạy cảm hoặc object mutable cần loại khỏi Context không?
10. Test có bao phủ scheduler switch, flatMap, concurrency, error và cancellation không?

Reactor Context cung cấp nền tảng để mang metadata theo subscription qua pipeline bất đồng bộ. contextWrite đặt dữ liệu, deferContextual đọc dữ liệu và các hook như doOnEach có thể dùng Context của signal để ghi log. Spring Security reactive dựa vào Context để giữ SecurityContext; Micrometer Context Propagation kết nối Reactor với ThreadLocal khi thư viện cũ cần MDC hoặc trạng thái imperative; Micrometer Tracing/Observation giúp duy trì trace và span qua các ranh giới bất đồng bộ. Hãy giữ Context nhỏ, bất biến, có nguồn đáng tin cậy và kiểm thử việc bridge giữa các thread. Khi metadata, bảo mật và truy vết được gắn với đúng subscription, các pipeline Mono/Flux có thể đổi scheduler và chạy đồng thời mà vẫn giữ được ngữ cảnh của request.
