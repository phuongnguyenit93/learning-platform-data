# Vì sao ThreadLocal không tự đi theo chuỗi bất đồng bộ

Trong ứng dụng Java, thông tin như mã yêu cầu, người dùng hiện tại, ngôn ngữ hoặc dữ liệu phục vụ ghi log thường được lưu trong **ThreadLocal**. Cách làm này thuận tiện khi một request được xử lý tuần tự trên cùng một thread: một bộ lọc đặt giá trị ở đầu request, các tầng gọi phía sau đọc lại giá trị đó, rồi bộ lọc xóa nó khi hoàn tất.

Pipeline reactive có vòng đời khác. Một thao tác có thể bắt đầu trên thread này, tiếp tục trên thread khác sau khi đổi scheduler, rồi xen kẽ với nhiều thao tác khác trên cùng worker. Vì vậy, ThreadLocal gắn với thread thực thi, không gắn với một chuỗi Publisher hay một subscription. Khi luồng xử lý bất đồng bộ đổi thread, giá trị ThreadLocal không tự đi theo nó. Đây là lý do cần một mô hình truyền ngữ cảnh phù hợp với vòng đời của reactive pipeline.

Bài học thuộc chương **Ngữ cảnh** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Ta sẽ tìm hiểu giới hạn của ThreadLocal, cách dùng Reactor Context và khi nào cần cầu nối với các thư viện dựa trên ThreadLocal.

## ThreadLocal lưu dữ liệu theo thread

Mỗi thread có vùng lưu trữ ThreadLocal riêng. Khi gọi set, giá trị được gắn với thread đang thực hiện lời gọi. Khi một thread khác gọi get trên cùng đối tượng ThreadLocal, nó đọc vùng lưu trữ của chính thread đó, không đọc giá trị đã được đặt ở thread trước.

~~~java
private static final ThreadLocal<String> REQUEST_ID =
    new ThreadLocal<>();

void handleRequest() {
    REQUEST_ID.set("req-42");
    try {
        service.process();
    } finally {
        REQUEST_ID.remove();
    }
}
~~~

Trong luồng xử lý đồng bộ trên một thread, các phương thức được gọi trong `service.process()` có thể đọc cùng `REQUEST_ID`. Khối `finally` xóa giá trị để thread có thể được tái sử dụng cho request tiếp theo mà không mang theo dữ liệu cũ.

Mô hình này dựa trên giả định rằng toàn bộ công việc cần ngữ cảnh đều chạy trên cùng thread. Reactive pipeline không bảo đảm giả định đó:

- `subscribeOn` có thể chuyển việc thực thi nguồn sang worker khác.
- `publishOn` chuyển việc xử lý tín hiệu downstream sang scheduler khác.
- `flatMap` có thể cho nhiều Publisher con hoạt động xen kẽ hoặc đồng thời.
- Một scheduler thường tái sử dụng worker cho nhiều subscription khác nhau.

ThreadLocal không biết những thao tác đó thuộc về request nào. Nó chỉ biết thread nào đang đọc hoặc ghi giá trị.

## Vì sao đổi scheduler làm mất ngữ cảnh?

Giả sử mã đặt request ID trong ThreadLocal rồi đọc lại sau một lần `publishOn`:

~~~java
Mono<String> result = Mono.defer(() -> {
        REQUEST_ID.set("req-42");
        return Mono.just("data");
    })
    .publishOn(Schedulers.parallel())
    .map(value -> REQUEST_ID.get());
~~~

Phần nguồn có thể chạy trên thread thực hiện subscription, còn `map` chạy trên worker của `parallel`. Worker đó không có giá trị `req-42` được đặt ở thread nguồn, nên `REQUEST_ID.get()` thường trả về `null` hoặc giá trị riêng của worker nếu nơi khác đã đặt nó.

Ngay cả khi không đổi scheduler, việc dựa vào ThreadLocal vẫn có thể gây lỗi khi nhiều luồng xử lý dùng chung một worker. Một callback có thể đặt giá trị, callback khác chạy trên cùng worker đọc nhầm giá trị nếu việc đặt và xóa không được quản lý đúng. ThreadLocal phân tách dữ liệu theo thread, trong khi ứng dụng cần phân tách dữ liệu theo subscription hoặc request.

Sơ đồ dưới đây minh họa sự khác nhau:

~~~mermaid
flowchart TD
    A["Request A: ThreadLocal = req-A"] --> B["Tạo Publisher A"]
    B --> C["publishOn: worker-1"]
    D["Request B: ThreadLocal = req-B"] --> E["Tạo Publisher B"]
    E --> F["publishOn: worker-1"]
    C --> G["Worker-1 được tái sử dụng"]
    F --> G
    G --> H["ThreadLocal thuộc worker, không thuộc A hoặc B"]
~~~

Vấn đề cốt lõi không phải ThreadLocal là API xấu. Nó phù hợp với dữ liệu có vòng đời gắn với một thread. Nhưng request context trong pipeline reactive có vòng đời gắn với subscription và cần một cơ chế truyền riêng.

## Reactor Context gắn ngữ cảnh với subscription

Project Reactor cung cấp **Context** để truyền dữ liệu theo subscription. Context là cấu trúc key-value bất biến: mỗi lần thêm hoặc thay đổi giá trị sẽ tạo ra một Context mới. Context được truyền cùng tín hiệu subscription qua pipeline, nên dữ liệu không phụ thuộc thread hiện tại.

Có thể ghi ngữ cảnh bằng `contextWrite` và đọc bằng `deferContextual`:

~~~java
Mono<String> greeting = Mono.deferContextual(context -> {
    String userId = context.get("userId");
    return Mono.just("Xin chào " + userId);
}).contextWrite(context -> context.put("userId", "user-42"));
~~~

Khi subscribe, Reactor cung cấp Context cho callback của `deferContextual`. Dù các toán tử sau đó chạy trên scheduler khác, giá trị `userId` vẫn thuộc subscription hiện tại.

`ContextView` được cung cấp cho mã đọc ngữ cảnh là giao diện chỉ đọc. Khi cần ghi, dùng `contextWrite` ở phía downstream của đoạn pipeline cần đọc giá trị. Context lan truyền theo hướng ngược với dữ liệu: từ Subscriber đi ngược về phía Publisher khi subscribe.

Ví dụ:

~~~java
Mono<String> user = Mono.deferContextual(context ->
        Mono.just(context.get("userId"))
    )
    .map(id -> "Đang xử lý " + id)
    .contextWrite(context -> context.put("userId", "user-42"));
~~~

`contextWrite` đặt sau các toán tử cần đọc Context sẽ làm giá trị có mặt khi subscription đi ngược qua các toán tử đó. Nếu đặt `contextWrite` ở một nhánh hoặc vị trí không nằm trong phạm vi subscription của đoạn đọc, đoạn đó sẽ không nhìn thấy key đã ghi.

## Context không phải biến toàn cục

Context được tạo và gắn với subscription. Hai subscription có thể dùng cùng một key nhưng có giá trị khác nhau:

~~~java
Mono<String> currentUser = Mono.deferContextual(context ->
    Mono.just(context.get("userId"))
);

Mono<String> alice = currentUser
    .contextWrite(context -> context.put("userId", "alice"));

Mono<String> bob = currentUser
    .contextWrite(context -> context.put("userId", "bob"));
~~~

Subscription của `alice` đọc `alice`; subscription của `bob` đọc `bob`. Hai giá trị không ghi đè lên nhau dù chúng dùng cùng một Publisher được khai báo trước.

Đặc điểm này hữu ích cho:

- Mã tương quan request như `traceId` hoặc `correlationId`.
- Định danh người dùng đã xác thực trong phạm vi request.
- Ngôn ngữ hoặc tenant hiện tại của một thao tác.
- Thông tin phục vụ log, metric hoặc tracing.

Không nên dùng Context như một kho lưu trữ dữ liệu lớn hoặc một đối tượng mutable dùng chung. Context được thiết kế để truyền tham chiếu ngữ cảnh nhỏ theo subscription. Nếu đặt một đối tượng mutable vào Context rồi sửa nó từ nhiều callback, ứng dụng vẫn phải tự giải quyết đồng bộ và chia sẻ trạng thái.

## Đọc Context ở những vị trí khác nhau trong pipeline

`deferContextual` hữu ích khi cần tạo Publisher dựa trên ngữ cảnh lúc subscribe:

~~~java
Mono<Account> account = Mono.deferContextual(context -> {
    String tenantId = context.get("tenantId");
    return accountRepository.findForTenant(tenantId, accountId);
}).contextWrite(context -> context.put("tenantId", "tenant-7"));
~~~

Có thể đọc Context trong các toán tử quan sát tín hiệu bằng `Signal.getContextView()`:

~~~java
Mono<Account> account = accountRepository.findById(accountId)
    .doOnEach(signal -> {
        if (signal.isOnNext()) {
            String traceId = signal.getContextView()
                .getOrDefault("traceId", "unknown");
            logger.info("traceId={} account loaded", traceId);
        }
    })
    .contextWrite(context -> context.put("traceId", "trace-42"));
~~~

Cách này cho phép ghi log với giá trị theo subscription mà không cần tự đặt ThreadLocal trong callback. Với thư viện logging có MDC dựa trên ThreadLocal, cần một cầu nối context propagation nếu muốn MDC được khôi phục trong từng callback.

## Context đi qua các toán tử ghép luồng

Context được truyền theo subscription, vì vậy các toán tử Reactor có thể giữ ngữ cảnh khi chuyển qua các Publisher con. Ví dụ:

~~~java
Mono<String> result = Mono.just("order-42")
    .flatMap(orderId ->
        Mono.deferContextual(context -> {
            String tenant = context.get("tenantId");
            return orderService.load(tenant, orderId);
        })
    )
    .contextWrite(context -> context.put("tenantId", "tenant-7"));
~~~

Publisher con được tạo trong `flatMap` có thể đọc Context của subscription hiện tại. Điều này giúp các service phía dưới nhận được request context mà không cần truyền cùng một tham số xuyên qua mọi chữ ký phương thức.

Tuy nhiên, Context chỉ được truyền trong phạm vi Reactor subscription. Khi chuyển công việc sang một cơ chế thực thi độc lập như tự tạo thread, gửi Runnable vào executor ngoài Reactor hoặc gọi một API callback không tích hợp context propagation, ngữ cảnh không tự động xuất hiện ở đó. Khi vượt qua ranh giới này, cần truyền dữ liệu tường minh hoặc dùng công cụ bridge phù hợp.

## Cầu nối với ThreadLocal và thư viện bên ngoài

Một số thư viện vẫn đọc thông tin từ ThreadLocal. Ví dụ phổ biến là MDC trong logging hoặc các API bảo mật có lưu principal theo thread. Nếu ứng dụng cần tích hợp chúng với Reactor, có thể dùng hệ sinh thái **Micrometer Context Propagation** để đăng ký cách đọc và khôi phục các ThreadLocal đã biết.

Một accessor minh họa cho MDC có thể được đăng ký với `ContextRegistry`:

~~~java
ContextRegistry.getInstance().registerThreadLocalAccessor(
    "requestId",
    () -> MDC.get("requestId"),
    value -> MDC.put("requestId", value),
    () -> MDC.remove("requestId")
);
~~~

Sau khi đăng ký accessor và thêm dependency context-propagation tương thích, có thể chụp các giá trị ThreadLocal hiện tại vào Reactor Context tại thời điểm subscribe bằng `contextCapture()`:

~~~java
Mono<String> result = service.call()
    .contextCapture();
~~~

`contextCapture()` thu thập các giá trị từ ThreadLocal đã đăng ký thông qua accessor và đưa chúng vào Context của subscription. Nó không tự phát hiện mọi ThreadLocal trong ứng dụng; chỉ các accessor đã đăng ký mới tham gia quá trình này.

Reactor cũng có chế độ tự động khôi phục ThreadLocal trong các callback. Có thể bật bằng:

~~~java
Hooks.enableAutomaticContextPropagation();
~~~

Chế độ tự động yêu cầu tích hợp context-propagation phù hợp và cần được bật ở thời điểm khởi tạo ứng dụng trước khi tạo các subscription cần áp dụng. Khả năng và phạm vi khôi phục phụ thuộc phiên bản Reactor cùng thư viện Micrometer Context Propagation. Cần kiểm tra tài liệu phiên bản đang dùng và kiểm thử các ranh giới scheduler thực tế.

Bridge hữu ích khi tích hợp thư viện cũ, nhưng không nên biến ThreadLocal thành nơi lưu trữ ngữ cảnh chính của toàn bộ reactive application. Ưu tiên Reactor Context cho dữ liệu request; dùng bridge ở ranh giới với thư viện cần ThreadLocal.

## Những điều cần lưu ý khi dùng Context

**Context bất biến:** các thao tác `put`, `delete` trả về Context mới. Phải dùng giá trị trả về trong hàm cập nhật:

~~~java
// Đúng: trả về Context mới.
.contextWrite(context -> context.put("traceId", "trace-42"))
~~~

Không sửa Context như một map mutable rồi mong các subscription khác nhìn thấy thay đổi.

**Context có phạm vi subscription:** mỗi lần subscribe có thể cung cấp bộ giá trị riêng. Không nên giả định một Publisher được khai báo một lần chỉ có một Context cố định.

**Thứ tự contextWrite quan trọng:** Context đi ngược upstream khi subscribe. Đặt `contextWrite` ở vị trí downstream của toán tử đọc để toán tử đó thấy key cần thiết.

**Không nhầm Context với dữ liệu phát:** Context không thay thế phần tử `onNext`. Dữ liệu nghiệp vụ mà Subscriber cần xử lý và hiển thị vẫn nên đi qua kiểu dữ liệu của Publisher; Context dành cho thông tin phụ trợ gắn với subscription.

**Không chứa bí mật tùy tiện:** Context có thể được đọc bởi các toán tử và thư viện trong pipeline. Chỉ đưa thông tin cần thiết vào đó, tránh ghi log toàn bộ Context hoặc đưa mật khẩu, token thô và dữ liệu nhạy cảm vào giá trị dễ bị quan sát.

## Kiểm thử Context bằng StepVerifier

Có thể kiểm thử rằng một Publisher đọc đúng Context:

~~~java
Mono<String> userId = Mono.deferContextual(context ->
    Mono.just(context.get("userId"))
);

StepVerifier.create(
        userId.contextWrite(context ->
            context.put("userId", "user-42"))
    )
    .expectNext("user-42")
    .verifyComplete();
~~~

Có thể xác nhận hai subscription không chia sẻ nhầm giá trị:

~~~java
StepVerifier.create(
        userId.contextWrite(context -> context.put("userId", "alice"))
    )
    .expectNext("alice")
    .verifyComplete();

StepVerifier.create(
        userId.contextWrite(context -> context.put("userId", "bob"))
    )
    .expectNext("bob")
    .verifyComplete();
~~~

Để kiểm tra Context có mặt trong subscription, `StepVerifier` cung cấp `expectAccessibleContext()`:

~~~java
Mono<String> source = Mono.deferContextual(context ->
    Mono.just(context.get("traceId"))
);

StepVerifier.create(
        source.contextWrite(context -> context.put("traceId", "trace-42"))
    )
    .expectAccessibleContext()
    .contains("traceId", "trace-42")
    .then()
    .expectNext("trace-42")
    .verifyComplete();
~~~

Khi kiểm thử context propagation sang ThreadLocal, cần chạy test trong cấu hình có accessor và chế độ propagation tương ứng. Kiểm tra giá trị ở callback sau một lần đổi scheduler, đồng thời xác nhận giá trị ThreadLocal được dọn hoặc khôi phục sau callback để không rò rỉ sang công việc khác dùng chung worker.

## Những nhầm lẫn thường gặp

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
|---|---|---|
| ThreadLocal đi theo Publisher | Giá trị có thể mất sau khi đổi thread | ThreadLocal gắn với thread; Context gắn với subscription |
| Dùng `publishOn` để truyền ngữ cảnh | Chỉ đổi scheduler xử lý tín hiệu | Dùng Reactor Context hoặc bridge phù hợp |
| Context là map mutable dùng chung | Các subscription có thể ảnh hưởng trạng thái lẫn nhau nếu chứa object mutable | Context bất biến, cập nhật bằng giá trị Context mới |
| `contextCapture()` chụp mọi ThreadLocal | Giá trị không có accessor sẽ không được thu thập | Đăng ký accessor cho từng loại ThreadLocal cần bridge |
| Cancellation hoặc executor ngoài Reactor tự giữ Context | Ngữ cảnh có thể mất ở ranh giới thực thi độc lập | Truyền tường minh hoặc tích hợp context propagation |
| Context thay thế dữ liệu nghiệp vụ | Subscriber không nhận được dữ liệu qua `onNext` | Dùng Context cho metadata; dùng Publisher element cho dữ liệu |

## Nguyên tắc thiết kế

Khi cần truyền request context qua pipeline reactive, hãy xác định:

1. Thông tin nào thuộc về request hoặc subscription thay vì thread?
2. Các toán tử nào cần đọc thông tin đó và có thể dùng `deferContextual` hay `ContextView`?
3. `contextWrite` đã được đặt ở vị trí downstream phù hợp với các toán tử đọc chưa?
4. Công việc có vượt khỏi Reactor subscription sang executor hoặc callback bên ngoài không?
5. Thư viện tích hợp có yêu cầu ThreadLocal hay có API nhận context tường minh?
6. Nếu cần bridge, accessor nào được đăng ký và khi nào giá trị được capture/restore?
7. Kiểm thử có bao gồm đổi scheduler, nhiều subscription và việc dọn ThreadLocal sau callback không?

ThreadLocal không tự đi theo chuỗi bất đồng bộ vì nó lưu dữ liệu theo thread, trong khi reactive pipeline cần ngữ cảnh theo subscription. Reactor Context giải quyết phần truyền ngữ cảnh trong pipeline; Micrometer Context Propagation có thể làm cầu nối với thư viện còn phụ thuộc ThreadLocal. Phân định rõ hai cơ chế này giúp request context nhất quán qua các scheduler mà không vô tình chia sẻ dữ liệu giữa những công việc dùng chung thread.
