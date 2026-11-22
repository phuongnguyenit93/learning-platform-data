# Reactor Context và sự khác biệt với ThreadLocal

## 1. Vì sao ứng dụng reactive cần một cơ chế lưu ngữ cảnh?

Trong ứng dụng backend, một request thường mang theo những thông tin được dùng ở nhiều tầng xử lý: mã request, mã trace, người dùng hiện tại, tenant, locale hoặc thông tin bảo mật. Nếu phải truyền tất cả giá trị này qua tham số của từng phương thức, chữ ký hàm sẽ trở nên dài và nhiều tầng chỉ phải chuyển tiếp dữ liệu mà chúng không trực tiếp sử dụng.

Trong ứng dụng imperative truyền thống, **ThreadLocal** thường được dùng để giải quyết vấn đề đó. Một giá trị được gắn với thread hiện tại; các phương thức chạy trên cùng thread có thể đọc giá trị mà không cần nhận nó qua tham số.

Mô hình này không còn phù hợp nếu áp dụng nguyên trạng cho reactive. Một request không nhất thiết được xử lý trên cùng một thread từ đầu đến cuối. Reactor có thể chuyển việc thực thi giữa các thread thông qua những toán tử như **publishOn** và **subscribeOn**. Giá trị nằm trong ThreadLocal của thread ban đầu không tự đi theo request khi pipeline chuyển sang thread khác.

**Reactor Context** giải quyết bài toán bằng cách gắn metadata với subscriber của một pipeline reactive. Context đi theo quá trình subscribe và vẫn có thể được truy cập khi pipeline chuyển thread. Đây là cơ chế ngữ cảnh của Reactor, không phải một ThreadLocal khác.

## 2. ThreadLocal hoạt động theo thread như thế nào?

ThreadLocal cho phép mỗi thread có một bản giá trị riêng cho cùng một biến ThreadLocal. Khi gọi **set()**, giá trị được lưu trong vùng dữ liệu gắn với thread hiện tại. Khi gọi **get()**, Java đọc giá trị của thread đang thực thi lời gọi đó.

Ví dụ:

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

public void handleRequest() {
    REQUEST_ID.set("req-123");
    try {
        process();
    } finally {
        REQUEST_ID.remove();
    }
}

private void process() {
    String requestId = REQUEST_ID.get();
    System.out.println("Request: " + requestId);
}
~~~

Trong ví dụ imperative này, **handleRequest()** và **process()** chạy đồng bộ trên cùng thread. Vì vậy, **process()** đọc được giá trị mà **handleRequest()** đã đặt.

ThreadLocal thường được dùng trong những thư viện có API đồng bộ, chẳng hạn logging MDC, một số cơ chế bảo mật trong servlet stack hoặc mã cần gắn dữ liệu với thread trong thời gian xử lý một tác vụ.

Điểm quan trọng là ThreadLocal gắn với **thread**, không gắn với khái niệm request, transaction hay một chuỗi công việc ở mức ứng dụng. Nếu công việc chuyển sang thread khác, giá trị ở thread ban đầu không tự được chuyển sang.

## 3. Vì sao ThreadLocal gặp vấn đề trong reactive pipeline?

### 3.1. Một request có thể đi qua nhiều thread

Reactor không cam kết một pipeline luôn chạy trên một thread. **publishOn** thay đổi scheduler dùng để thực thi những toán tử ở phía downstream của vị trí đặt nó. **subscribeOn** ảnh hưởng đến thread dùng để thực hiện quá trình subscribe và nguồn upstream.

~~~text
Request A
    |
    v
Thread-1: bắt đầu pipeline
    |
    v
publishOn(...)
    |
    v
Thread-7: xử lý phần downstream
~~~

Nếu request ID được lưu trong ThreadLocal của Thread-1, mã chạy trên Thread-7 sẽ đọc ThreadLocal của Thread-7. Giá trị của Thread-1 không tự xuất hiện ở đó.

Ví dụ minh họa:

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

Mono<String> result =
        Mono.just("start")
            .publishOn(Schedulers.parallel())
            .map(value -> REQUEST_ID.get());
~~~

Nếu ThreadLocal chỉ được thiết lập ở thread khởi tạo request, lời gọi **get()** phía sau **publishOn** có thể trả về **null** vì toán tử **map** chạy trên thread khác. Kết quả cụ thể phụ thuộc scheduler và cách thiết lập ThreadLocal; điều chắc chắn là Reactor không tự bảo đảm giá trị ThreadLocal được chuyển theo pipeline.

### 3.2. Thread pool tái sử dụng thread

Các scheduler thường sử dụng thread pool để tái sử dụng thread. Một thread sau khi hoàn thành tác vụ có thể được dùng cho tác vụ khác. Nếu mã tự đặt ThreadLocal nhưng không xóa đúng lúc, giá trị cũ có thể còn tồn tại trên thread và ảnh hưởng đến tác vụ tiếp theo.

Điều này đặc biệt nguy hiểm với metadata theo request như user ID hoặc tenant ID. Một lỗi dọn dẹp có thể khiến log hoặc logic xử lý đọc nhầm dữ liệu của tác vụ trước đó.

Trong mô hình imperative, phạm vi **try/finally** thường giúp quản lý vòng đời ThreadLocal tương đối rõ ràng. Với pipeline reactive, một request có thể tạm dừng, tiếp tục trên thread khác và hoàn tất ở thời điểm khác; không thể dựa vào một phạm vi gọi hàm đồng bộ đơn giản để quản lý toàn bộ vòng đời đó.

### 3.3. Một request không đồng nghĩa với một thread

Mô hình reactive cho phép nhiều request cùng được điều phối trên một số lượng thread tương đối nhỏ. Một request có thể được xử lý bởi nhiều thread ở các thời điểm khác nhau, còn một thread có thể lần lượt xử lý các phần công việc của nhiều request.

Vì thế, thread không còn là đơn vị thích hợp để đại diện cho ngữ cảnh của một request. Cần một cơ chế gắn dữ liệu với luồng xử lý logic thay vì gắn với thread đang tình cờ thực thi một bước.

## 4. Reactor Context là gì?

**Reactor Context là một cấu trúc key-value bất biến, gắn với subscriber của một chuỗi reactive.** Nó cho phép các operator đọc metadata được cung cấp trong quá trình subscribe, kể cả khi quá trình xử lý chuyển giữa nhiều thread.

Các đặc điểm quan trọng:

- Context thuộc về subscriber và subscription, không thuộc về một thread cụ thể.
- Context được truyền qua quá trình subscribe trong pipeline Reactor.
- Context có thể được đọc ở nhiều vị trí trong pipeline bằng API của Reactor.
- Context là immutable: thao tác thêm, thay hoặc xóa một key tạo ra Context mới.
- Mỗi subscription có ngữ cảnh riêng, nhờ đó những request độc lập có thể mang các giá trị khác nhau.
- Context chủ yếu dành cho metadata phục vụ điều phối và tích hợp, chẳng hạn trace ID, tenant ID hoặc thông tin bảo mật.

Context có thể chứa bất kỳ object nào làm value. Tuy nhiên, tính bất biến của Context không có nghĩa mọi object bên trong cũng bất biến. Nếu lưu một object mutable rồi nhiều operator cùng thay đổi object đó, ứng dụng vẫn có thể gặp race condition. Nên ưu tiên các giá trị nhỏ, rõ ràng và bất biến.

Reactor cung cấp hai kiểu API thường gặp:

- **Context** là kiểu có thể được tạo hoặc cập nhật bằng các thao tác như **put**, **putAll** và **delete**.
- **ContextView** là góc nhìn chỉ đọc, thường được dùng khi một operator truy cập Context.

## 5. Cách ghi và đọc Reactor Context

### 5.1. Ghi dữ liệu bằng contextWrite

Toán tử **contextWrite** cập nhật Context được cung cấp cho phần upstream của pipeline.

~~~java
Mono<String> greeting =
        Mono.just("hello")
            .map(value -> value.toUpperCase())
            .contextWrite(context -> context.put("userId", "user-42"));
~~~

Ở đây, **contextWrite** tạo một Context có key **userId** với value **user-42**. Context đó được cung cấp cho các operator ở phía upstream trong quá trình subscribe.

Vì Context là immutable, lời gọi **put** không sửa trực tiếp một Context dùng chung. Nó tạo ra Context mới chứa giá trị được cập nhật. Lambda của **contextWrite** nhận Context hiện tại và trả về Context cần sử dụng.

| API | Ý nghĩa |
|---|---|
| **put(key, value)** | Thêm key hoặc thay value của key hiện có |
| **putAll(otherContext)** | Kết hợp các entry từ Context khác |
| **delete(key)** | Tạo Context mới không còn key đó |
| **hasKey(key)** | Kiểm tra key có tồn tại |
| **get(key)** | Đọc value; phát sinh lỗi nếu key không tồn tại |
| **getOrDefault(key, defaultValue)** | Đọc value hoặc dùng giá trị mặc định |
| **getOrEmpty(key)** | Đọc value dưới dạng Optional |

### 5.2. Đọc dữ liệu bằng deferContextual

Để đọc Context tại thời điểm subscription, Reactor cung cấp **deferContextual**. Lambda nhận một **ContextView**, từ đó có thể lấy giá trị cần thiết.

~~~java
Mono<String> greeting =
        Mono.deferContextual(context -> {
            String userId = context.getOrDefault("userId", "anonymous");
            return Mono.just("Hello " + userId);
        })
        .contextWrite(context -> context.put("userId", "user-42"));
~~~

Khi subscriber đăng ký, **deferContextual** đọc Context hiện tại và tạo publisher dựa trên giá trị **userId**. Kết quả của ví dụ là **Hello user-42**.

Dùng **get()** khi key bắt buộc phải có và muốn phát hiện ngay trường hợp thiếu dữ liệu. Dùng **getOrDefault()** khi có giá trị fallback hợp lý. Tránh âm thầm dùng fallback cho dữ liệu bảo mật hoặc tenant nếu việc thiếu key phải được xem là lỗi cấu hình hay lỗi luồng xử lý.

### 5.3. Ví dụ ghép nhiều thao tác reactive

Một service có thể đọc thông tin đơn hàng, sau đó ghi audit log với tenant ID lấy từ Context:

~~~java
private static final String TENANT_ID = "tenantId";

public Mono<Order> findOrder(String orderId) {
    return orderRepository.findById(orderId)
            .flatMap(order ->
                    Mono.deferContextual(context -> {
                        String tenantId = context.get(TENANT_ID);
                        return auditRepository.recordRead(order.getId(), tenantId)
                                .thenReturn(order);
                    }));
}
~~~

Tầng gọi có thể cung cấp tenant ID cho toàn bộ chuỗi xử lý:

~~~java
return orderService.findOrder("order-100")
        .contextWrite(context -> context.put("tenantId", "tenant-17"));
~~~

Trong ví dụ, **contextWrite** nằm ở phía downstream của toàn bộ chuỗi service. Vì Context được truyền ngược trong quá trình subscribe, các operator upstream, bao gồm phần xử lý bên trong **flatMap**, có thể đọc **tenantId**.

Đây là cách truyền metadata xuyên nhiều tầng mà không cần thêm tham số tenant vào mọi phương thức. Tuy nhiên, Context không tự tạo ra cơ chế phân quyền hoặc cô lập dữ liệu. Truy vấn dữ liệu đa tenant vẫn phải áp dụng điều kiện tenant ở tầng truy cập dữ liệu và kiểm tra quyền phù hợp. Không được xem một giá trị lấy từ Context là bằng chứng xác thực người dùng.

## 6. Hướng lan truyền của Context trong Reactor

Đây là điểm dễ gây nhầm lẫn nhất khi mới học Reactor Context.

Dữ liệu trong pipeline thường được phát từ upstream xuống downstream. Nhưng Context được cung cấp trong **quá trình subscribe theo hướng từ downstream về upstream**. Subscriber cuối cùng là nơi khởi đầu subscription; Context của subscriber được truyền ngược qua các operator.

~~~text
Dòng dữ liệu:
Source  ------------------------------>  Subscriber
        upstream                         downstream

Context khi subscribe:
Source  <------------------------------  Subscriber
        upstream                         downstream
~~~

### 6.1. Vì sao contextWrite thường đặt ở cuối chuỗi?

Xét ví dụ:

~~~java
Mono<String> result =
        Mono.deferContextual(context ->
                    Mono.just(context.get("requestId")))
            .map(requestId -> "Request: " + requestId)
            .contextWrite(context -> context.put("requestId", "req-123"));
~~~

Subscriber đăng ký vào publisher cuối cùng. **contextWrite** được thực thi trong quá trình subscribe và tạo Context mà phần upstream có thể nhìn thấy. Vì vậy, **deferContextual** đọc được **requestId**.

Có thể đọc quy tắc này như sau: **contextWrite ảnh hưởng đến phần nằm phía trước nó trong cách viết chuỗi operator**, tức phần upstream mà nó bao bọc trong quá trình subscribe.

### 6.2. contextWrite không phải biến toàn cục

Mỗi **contextWrite** chỉ tạo phạm vi Context cho phần upstream tương ứng. Nó không cập nhật một Context toàn cục và không tự làm cho các operator downstream đọc được giá trị vừa ghi.

Ví dụ dưới đây đặt **contextWrite** trước **flatMap**:

~~~java
Mono<String> result =
        Mono.just("order-100")
            .contextWrite(context -> context.put("tenantId", "tenant-17"))
            .flatMap(orderId ->
                    Mono.deferContextual(context ->
                            Mono.just(context.getOrDefault("tenantId", "missing"))));
~~~

**contextWrite** nằm trong nhánh upstream của **flatMap**. Nó cung cấp Context cho phần upstream của chính nó. Publisher được tạo bên trong **flatMap** không thể mặc định nhìn thấy giá trị được ghi ở vị trí đó. Với mục tiêu để **flatMap** và publisher con đọc được key, hãy đặt **contextWrite** ở phía downstream:

~~~java
Mono<String> result =
        Mono.just("order-100")
            .flatMap(orderId ->
                    Mono.deferContextual(context ->
                            Mono.just(context.get("tenantId"))))
            .contextWrite(context -> context.put("tenantId", "tenant-17"));
~~~

Việc hiểu đúng vị trí **contextWrite** giúp tránh lỗi thiếu key dù code đã có lời gọi **put**.

### 6.3. Đọc Context trong operator biến đổi

Ngoài **deferContextual**, Reactor còn có **transformDeferredContextual** để tạo một phép biến đổi publisher dựa trên Context của subscriber. API này hữu ích khi muốn đóng gói một logic dùng Context thành một operator tái sử dụng.

~~~java
Mono<String> result =
        Mono.just("order-100")
            .transformDeferredContextual((source, context) ->
                    source.map(orderId ->
                            orderId + " / tenant=" + context.get("tenantId")))
            .contextWrite(context -> context.put("tenantId", "tenant-17"));
~~~

Tên gọi **deferred** nhấn mạnh rằng phép biến đổi được áp dụng theo từng subscription, khi Context tương ứng đã sẵn sàng. Đây là điểm khác với việc đọc metadata ngay tại thời điểm lắp ráp pipeline.

## 7. Reactor Context không phụ thuộc vào thread

Một ưu điểm quan trọng của Reactor Context là nó đi theo subscriber, do đó không cần gắn với thread đang thực thi operator.

~~~java
Mono<String> result =
        Mono.just("start")
            .publishOn(Schedulers.parallel())
            .flatMap(value ->
                    Mono.deferContextual(context ->
                            Mono.just(value + " / " + context.get("requestId"))))
            .contextWrite(context -> context.put("requestId", "req-123"));
~~~

Dù **publishOn** chuyển phần xử lý downstream sang scheduler khác, **deferContextual** vẫn đọc được **requestId**. Context được truyền qua subscription chain, không phải bằng cách sao chép ThreadLocal từ thread này sang thread khác.

Cần phân biệt hai khái niệm:

- **Scheduler** quyết định nơi và thời điểm các tác vụ được thực thi.
- **Reactor Context** cung cấp metadata gắn với subscriber để operator có thể truy cập trong quá trình thực thi.

Context không tạo thread, không điều phối thread và không làm cho một thao tác blocking trở thành non-blocking. Nó chỉ cung cấp ngữ cảnh ổn định cho pipeline reactive.

## 8. So sánh Reactor Context và ThreadLocal

| Tiêu chí | Reactor Context | ThreadLocal |
|---|---|---|
| Gắn với | Subscriber / subscription | Thread hiện tại |
| Phạm vi | Một luồng xử lý reactive theo subscription | Một thread trong thời gian value được giữ |
| Khi chuyển thread | Context tiếp tục đi theo pipeline | Không tự chuyển sang thread mới |
| Cách đọc | API như deferContextual, transformDeferredContextual | ThreadLocal.get() |
| Cách ghi | contextWrite, tạo Context mới | ThreadLocal.set() trên thread hiện tại |
| Tính chất cấu trúc | Context immutable; value bên trong có thể mutable | Giá trị riêng cho từng thread và có thể thay đổi |
| Cách ly giữa request | Theo subscriber, nếu mỗi request có subscription riêng | Theo thread; thread pool có thể tái sử dụng thread |
| Phù hợp với | Metadata trong reactive pipeline | Mã imperative gắn với một thread |
| Vấn đề thường gặp | Đặt sai vị trí contextWrite, thiếu key, hiểu nhầm phạm vi Context | Mất giá trị khi đổi thread, quên remove, đọc nhầm giá trị còn sót |

Hai cơ chế phục vụ những mô hình thực thi khác nhau. ThreadLocal vẫn hữu ích trong mã đồng bộ và các thư viện imperative. Reactor Context phù hợp hơn khi cần gắn metadata với một pipeline reactive có thể chạy trên nhiều thread.

## 9. Dùng Context cho những loại dữ liệu nào?

Context nên chứa dữ liệu mô tả môi trường hoặc danh tính của luồng xử lý, không nên trở thành nơi chứa toàn bộ trạng thái nghiệp vụ.

| Loại metadata | Ví dụ key | Mục đích |
|---|---|---|
| Correlation / trace ID | traceId | Liên kết log và trace qua nhiều service |
| Request ID | requestId | Tìm các log thuộc cùng request |
| Tenant ID | tenantId | Cung cấp thông tin tenant cho những bước cần dùng |
| User identity | userId | Gắn định danh người dùng với pipeline |
| Security context | SecurityContext | Cung cấp thông tin xác thực và quyền trong reactive security |
| Locale | locale | Chọn ngôn ngữ hoặc định dạng phù hợp |
| Transaction resources | Do Spring quản lý | Liên kết các thao tác trong cùng reactive transaction |

Không nên lưu các tập dữ liệu lớn, entity graph, buffer hoặc object mutable được nhiều bước cùng cập nhật. Những dữ liệu đó nên được truyền bằng publisher, tham số nghiệp vụ hoặc cơ chế lưu trữ phù hợp.

Tên key cần nhất quán để tránh xung đột giữa các thư viện và module. Có thể khai báo hằng số **static final** thay vì rải chuỗi literal trong nhiều lớp. Với thư viện dùng chung, nên chọn namespace rõ ràng cho key. Khi đọc key bắt buộc, nên xử lý trường hợp thiếu một cách tường minh.

## 10. Tích hợp với logging, security và tracing

### 10.1. Logging MDC

Nhiều logging framework cung cấp MDC (Mapped Diagnostic Context) để gắn request ID hoặc trace ID vào log. MDC phổ biến dựa trên ThreadLocal. Vì vậy, gọi **MDC.put()** ở đầu một reactive request không bảo đảm giá trị sẽ hiện diện trên mọi thread xử lý pipeline.

Có hai cách tiếp cận:

1. Giữ metadata trong Reactor Context và chỉ đưa giá trị sang MDC trong phạm vi callback thực sự ghi log.
2. Dùng thư viện Context Propagation để kết nối Reactor Context với ThreadLocal mà thư viện logging đang sử dụng.

Ví dụ đọc trace ID từ Reactor Context và tạm thời đưa vào MDC khi xử lý một signal:

~~~java
.doOnEach(signal -> {
    if (signal.isOnNext()) {
        String traceId = signal.getContextView()
                .getOrDefault("traceId", "unknown");

        try (MDC.MDCCloseable ignored = MDC.putCloseable("traceId", traceId)) {
            log.info("Processed value: {}", signal.get());
        }
    }
})
~~~

Cách này giới hạn thời gian MDC được đặt trong callback và tự đóng giá trị sau khi ghi log. Trong ứng dụng thực tế, cần chọn đúng hook hoặc thư viện tích hợp logging để bảo đảm cả log ở các điểm khác cũng có context phù hợp.

### 10.2. Spring Security trong WebFlux

Spring Security ở servlet stack truyền thống thường dùng **SecurityContextHolder**, vốn gắn SecurityContext với thread thông qua ThreadLocal. Trong reactive stack, request có thể đổi thread nên Spring Security WebFlux sử dụng Reactor Context để giữ security context theo reactive chain.

API **ReactiveSecurityContextHolder.getContext()** trả về một **Mono<SecurityContext>** để lấy thông tin bảo mật trong pipeline:

~~~java
Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .map(securityContext ->
                        securityContext.getAuthentication().getName());
~~~

Khi phát triển ứng dụng WebFlux, nên dùng các API reactive của Spring Security. Không nên giả định **SecurityContextHolder.getContext()** luôn trả về người dùng hiện tại trên mọi thread trong reactive request.

### 10.3. Tracing và observability

Trace ID và span context cần được truyền qua nhiều bước xử lý, có thể bao gồm WebFlux, Spring Data R2DBC và lời gọi HTTP đến service khác. Reactor Context là một phần quan trọng trong cơ chế truyền metadata này.

Các thư viện observability hiện đại thường tích hợp với Reactor hoặc Micrometer Context Propagation để giữ trace context và khôi phục thông tin cần thiết tại ranh giới thực thi. Khi dùng framework tích hợp sẵn, nên tuân theo cơ chế cấu hình của phiên bản đó thay vì tự tạo một ThreadLocal độc lập cho trace ID.

## 11. Kết nối Reactor Context với ThreadLocal

Một số thư viện cũ chỉ cung cấp API dựa trên ThreadLocal. Khi đưa những thư viện này vào ứng dụng reactive, có thể cần cầu nối giữa Reactor Context và ThreadLocal.

Hệ sinh thái Micrometer cung cấp thư viện **Context Propagation** để hỗ trợ việc này. Ý tưởng chung là:

- Đăng ký một **ThreadLocalAccessor** mô tả cách đọc, ghi và xóa một ThreadLocal cụ thể.
- Dùng cơ chế capture để đưa giá trị ThreadLocal hiện có vào Reactor Context tại thời điểm subscription.
- Khi thực thi callback ở thread phù hợp, khôi phục giá trị từ Context vào ThreadLocal và dọn dẹp sau callback.
- Chỉ đăng ký những ThreadLocal thực sự cần tích hợp.

Ví dụ khái niệm khi capture context:

~~~java
Mono<String> task =
        Mono.deferContextual(context ->
                Mono.just(context.getOrDefault("requestId", "unknown")))
            .contextCapture();
~~~

**contextCapture()** sử dụng Context Propagation để capture các giá trị ThreadLocal đã đăng ký vào Reactor Context tại thời điểm subscribe. Vì vậy, giá trị cần capture phải có mặt trên thread thực hiện subscription và accessor tương ứng phải được đăng ký.

Reactor cũng cung cấp chế độ automatic context propagation thông qua hook **Hooks.enableAutomaticContextPropagation()** ở những phiên bản có hỗ trợ. Chế độ này giúp tự động khôi phục các ThreadLocal đã đăng ký từ Reactor Context quanh quá trình thực thi operator. Hook cần được bật sớm, trước khi các subscription cần áp dụng cơ chế này được tạo.

Một số lưu ý khi dùng cầu nối:

- Context Propagation không làm cho mọi ThreadLocal tự động được truyền đi. Chỉ những ThreadLocal có accessor được đăng ký mới được tích hợp.
- **contextCapture()** capture giá trị tại thời điểm subscribe; nó không đọc lại ThreadLocal ở mọi bước trong pipeline.
- Automatic mode thay đổi cách khôi phục ThreadLocal cho các operator được hỗ trợ. Cần đọc tài liệu đúng phiên bản Reactor và Micrometer đang sử dụng.
- Nếu có thể dùng API reactive thuần, nên ưu tiên giữ dữ liệu trong Reactor Context. Cầu nối ThreadLocal chủ yếu dành cho thư viện imperative cần tương thích.
- Việc khôi phục ThreadLocal phải có phạm vi và cleanup rõ ràng để tránh rò rỉ dữ liệu giữa các tác vụ.

Không nên tự viết một cơ chế copy ThreadLocal bằng cách lấy giá trị ở đầu request rồi set trên một thread bất kỳ. Cách đó khó xử lý thread reuse, nested callback, lỗi, cancellation và nhiều scheduler. Hãy dùng cơ chế tích hợp được thư viện hỗ trợ.

## 12. Context và reactive transaction

Spring Data R2DBC sử dụng reactive transaction manager. Transaction context được gắn với reactive execution context để các thao tác trong cùng một pipeline có thể dùng chung transaction và connection phù hợp.

Ví dụ, một service cập nhật hai dữ liệu trong cùng một transaction:

~~~java
@Transactional
public Mono<Void> updateOrderAndInventory(Order order) {
    return orderRepository.save(order)
            .then(inventoryRepository.decrease(order.getProductId(), order.getQuantity()))
            .then();
}
~~~

Publisher được trả về cho Spring quản lý transaction. Các thao tác cần tham gia transaction phải nằm trong cùng reactive chain và được thực thi trong transaction context mà Spring cung cấp.

Đây là một ví dụ khác cho thấy vì sao ngữ cảnh trong reactive không thể dựa đơn thuần vào ThreadLocal. Transaction có thể đi qua nhiều bước và nhiều thread, trong khi transaction manager cần liên kết đúng tài nguyên với subscription. Không nên tự gọi **subscribe()** bên trong phương thức transactional vì nó tạo một subscription độc lập có vòng đời khác với publisher mà Spring quản lý.

## 13. Những lỗi thường gặp khi sử dụng Reactor Context

### 13.1. Đặt contextWrite sai vị trí

Nếu **contextWrite** nằm upstream của operator cần đọc Context, operator đó có thể không thấy giá trị. Hãy nhớ Context được truyền từ downstream về upstream khi subscribe. Đặt **contextWrite** ở phía downstream của toàn bộ phần cần sử dụng giá trị thường là cách dễ hiểu nhất.

### 13.2. Đọc Context quá sớm khi lắp ráp pipeline

Không thể đọc Context như một biến có sẵn ngay lúc khai báo publisher. Context được cung cấp theo subscription. Dùng **deferContextual** hoặc **transformDeferredContextual** khi cần truy cập nó.

### 13.3. Giả định Context tự truyền sang mọi tác vụ bất đồng bộ

Context được Reactor quản lý trong reactive chain. Nếu tự tạo thread, gửi một callback sang executor ngoài Reactor hoặc khởi tạo subscription độc lập, không nên giả định Context sẽ tự đi theo. Cần dùng API tích hợp Context Propagation phù hợp hoặc truyền dữ liệu tường minh qua ranh giới đó.

### 13.4. Tạo subscription lồng nhau bằng subscribe()

Gọi **subscribe()** tùy tiện bên trong operator thường làm tách một phần công việc khỏi pipeline ban đầu. Việc xử lý lỗi, cancellation, Context và transaction có thể không còn được quản lý cùng một vòng đời. Hãy trả về publisher và dùng các toán tử như **flatMap**, **then**, **zip** để kết hợp công việc.

### 13.5. Dùng Context làm nơi lưu trạng thái mutable

Context immutable chỉ bảo đảm cấu trúc key-value không bị thay đổi tại chỗ. Một value như **HashMap** hoặc một object mutable vẫn có thể bị thay đổi bởi nhiều bước. Hãy lưu metadata đơn giản và bất biến, tránh dùng Context để chia sẻ một vùng trạng thái có thể bị cập nhật đồng thời.

### 13.6. Dựa vào Context để thay thế kiểm tra bảo mật

Context là cơ chế truyền dữ liệu, không phải ranh giới tin cậy. Ví dụ, tenant ID trong Context có thể giúp truyền thông tin qua các tầng, nhưng truy vấn vẫn cần điều kiện tenant và quyền truy cập phải được xác minh. Không tin một key chỉ vì nó tồn tại trong Context.

### 13.7. Dùng dữ liệu theo request trong pipeline cache dùng chung

Các operator như **cache()** có thể chia sẻ kết quả upstream giữa nhiều subscriber. Nếu phần upstream phụ thuộc vào user ID hoặc tenant ID trong Context, việc chia sẻ kết quả có thể khiến dữ liệu theo request bị dùng chung ngoài ý muốn. Cần thiết kế cache key và vị trí cache có tính đến phạm vi dữ liệu; không cache một kết quả cá nhân hóa như thể nó là kết quả dùng chung.

## 14. Kiểm thử Reactor Context

Có thể kiểm tra hành vi Context bằng cách cung cấp Context khi tạo publisher và xác nhận kết quả.

~~~java
Mono<String> currentRequestId =
        Mono.deferContextual(context ->
                Mono.just(context.get("requestId")));

StepVerifier.create(
            currentRequestId.contextWrite(
                    context -> context.put("requestId", "req-test-1")))
        .expectNext("req-test-1")
        .verifyComplete();
~~~

Nên kiểm thử ít nhất các trường hợp:

- Key có mặt và operator đọc được đúng value.
- Key không có mặt, bảo đảm ứng dụng xử lý đúng lỗi hoặc fallback.
- Hai subscription độc lập có thể nhận hai Context khác nhau.
- Context vẫn đọc được sau khi pipeline chuyển scheduler.
- Các publisher con trong **flatMap** đọc được Context khi **contextWrite** đặt đúng vị trí.
- Những thao tác có cache hoặc subscription lồng nhau không vô tình chia sẻ dữ liệu theo request.

Kiểm thử này tập trung vào hành vi của pipeline và subscription, không phụ thuộc vào một thread cụ thể.

## 15. Cách chọn giữa Reactor Context và ThreadLocal

Hãy dùng **Reactor Context** khi dữ liệu cần đi theo một reactive pipeline, có thể qua nhiều operator, scheduler hoặc tầng service. Những ví dụ điển hình là trace ID, request ID, security context, tenant metadata và transaction context.

Hãy dùng **ThreadLocal** khi đang xử lý một đoạn mã imperative thực sự gắn với một thread và vòng đời của giá trị được quản lý rõ ràng. ThreadLocal vẫn có chỗ đứng trong các thư viện đồng bộ và có thể được kết nối với Reactor thông qua Context Propagation khi cần.

Trong một ứng dụng reactive, nên chọn Reactor Context làm nguồn ngữ cảnh chính. Nếu một thư viện cần ThreadLocal, hãy dùng cầu nối đã được hỗ trợ để chuyển đổi tại ranh giới phù hợp. Cách này giúp ngữ cảnh theo request đi cùng subscriber, trong khi những API imperative vẫn nhận được dữ liệu theo cách chúng mong đợi.

## 16. Kết luận

Reactor Context và ThreadLocal đều giúp truy cập metadata mà không phải truyền tham số qua mọi phương thức, nhưng chúng gắn dữ liệu với hai đơn vị khác nhau. ThreadLocal gắn value với thread đang chạy. Reactor Context gắn metadata với subscriber và subscription của reactive pipeline.

Khi pipeline chuyển thread, ThreadLocal không tự chuyển theo; Reactor Context vẫn được truyền trong quá trình subscribe. Muốn sử dụng Context đúng cách, cần hiểu hướng lan truyền từ downstream về upstream, đặt **contextWrite** đúng vị trí và đọc dữ liệu bằng **deferContextual** hoặc API tương ứng.

Với Spring Data R2DBC và Spring WebFlux, Reactor Context là nền tảng quan trọng để truyền transaction, security và tracing metadata xuyên suốt luồng non-blocking. ThreadLocal vẫn có thể xuất hiện ở ranh giới tích hợp với thư viện imperative, nhưng việc chuyển đổi cần được quản lý bằng cơ chế Context Propagation phù hợp.

