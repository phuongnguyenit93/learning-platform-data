# Reactor Context và chiều truyền ngữ cảnh qua chuỗi

Một request reactive thường cần mang theo metadata xuyên suốt nhiều bước xử lý: request ID để ghi log, tenant ID để chọn dữ liệu, thông tin xác thực để gọi dịch vụ khác hoặc trace context để nối các span. Pipeline có thể chuyển qua nhiều scheduler và thread, vì vậy dựa vào `ThreadLocal` như trong code đồng bộ dễ làm metadata biến mất hoặc bị gắn nhầm request. Reactor cung cấp `Context` để gắn dữ liệu với subscription và cho phép các operator đọc ngữ cảnh theo đúng luồng xử lý.

Bài học thuộc chương **Ngữ cảnh** của module `REACTIVE_PROGRAMMING`. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Trọng tâm ở đây là Reactor Context, chiều truyền ngữ cảnh trong chuỗi operator và cách đặt `contextWrite` để dữ liệu xuất hiện đúng nơi cần đọc.

Sau bài học, bạn có thể:

- Giải thích Context thuộc về subscription và không phụ thuộc vào một thread cụ thể.
- Đọc Context bằng `deferContextual` và `transformDeferredContextual`.
- Ghi hoặc biến đổi Context bằng `contextWrite`.
- Dự đoán chiều truyền Context khi có nhiều `contextWrite`.
- Hiểu phạm vi Context trong `flatMap` và các subscription lồng nhau.
- Phân biệt Reactor Context với `ThreadLocal`, dữ liệu nghiệp vụ và payload của luồng.
- Kiểm thử metadata qua `publishOn`, `subscribeOn` và các ranh giới operator.

## 1. Vì sao pipeline cần một Context theo subscription?

Trong ứng dụng đồng bộ, một request thường chạy trên một thread trong phần lớn thời gian. Thư viện logging hoặc security có thể lưu request ID hay thông tin người dùng trong `ThreadLocal`. Khi code chuyển sang reactive, một request có thể bắt đầu trên thread này, tiếp tục trên thread khác sau `publishOn`, rồi lại chuyển sang worker khác. Một thread có thể xử lý nhiều request xen kẽ.

Vì vậy, `ThreadLocal` không phải nơi an toàn để biểu diễn metadata gắn với một subscription. Nó gắn dữ liệu với thread hiện tại, trong khi reactive cần gắn dữ liệu với luồng xử lý của từng subscriber.

Reactor Context giải quyết việc đó:

- Context được liên kết với subscriber/subscription.
- Các operator có thể đọc Context trong quá trình xử lý subscription.
- Context không cần nằm trên cùng một thread để tiếp tục có thể truy cập.
- Mỗi subscription có Context riêng; các subscriber khác nhau không tự động dùng chung Context.

Ví dụ một API cần request ID:

```java
Mono<String> response = Mono.deferContextual(context -> {
    String requestId = context.get("requestId");
    return Mono.just("Đang xử lý request " + requestId);
});

Mono<String> request = response
    .contextWrite(context -> context.put("requestId", "req-42"));
```

Khi subscribe vào `request`, `deferContextual` đọc được giá trị `req-42`. Giá trị này không phải phần tử `onNext` được truyền qua các operator; nó là metadata đi kèm subscription.

## 2. Context là cấu trúc bất biến

Reactor Context có giao diện dạng key-value và được thiết kế để bất biến. Các thao tác như `put`, `delete` hoặc `putAll` trả về một Context mới thay vì sửa object hiện có.

```java
Context base = Context.empty();

Context requestContext = base
    .put("requestId", "req-42")
    .put("tenantId", "tenant-a");

Context updatedContext = requestContext
    .put("requestId", "req-43");
```

`requestContext` vẫn giữ `req-42`; `updatedContext` có `req-43`. Cách thiết kế bất biến giúp các operator không vô tình sửa Context của subscriber khác.

Context phù hợp với metadata nhỏ, ổn định trong vòng đời request, ví dụ:

- `requestId`, `traceId` hoặc correlation ID.
- Tenant hoặc vùng dữ liệu cần định tuyến.
- Principal hoặc thông tin xác thực đã được xác minh.
- Locale hoặc thông tin phục vụ logging/observability.

Không nên dùng Context để truyền payload lớn, danh sách kết quả hoặc trạng thái nghiệp vụ biến đổi liên tục. Dữ liệu nghiệp vụ nên đi qua `onNext` để kiểu dữ liệu và luồng phụ thuộc được thể hiện rõ. Context cũng không phải kho lưu trữ dùng chung toàn ứng dụng; nó thuộc phạm vi subscription.

### Kiểu key và kiểu value

Context thường được truy cập bằng key. Để giảm lỗi chính tả hoặc trùng key, nên gom key vào hằng số hoặc dùng một kiểu key riêng:

```java
final class ContextKeys {
    static final String REQUEST_ID = "requestId";
    static final String TENANT_ID = "tenantId";

    private ContextKeys() {}
}
```

Khi đọc bằng `get`, key phải tồn tại; nếu không, Reactor ném lỗi khi operator thực thi. Có thể dùng `hasKey` hoặc `getOrEmpty` để xử lý metadata tùy chọn:

```java
Mono<String> requestId = Mono.deferContextual(context ->
    Mono.just(context.getOrDefault(ContextKeys.REQUEST_ID, "unknown"))
);
```

Với giá trị bắt buộc, đọc trực tiếp bằng `get` giúp phát hiện thiếu metadata sớm. Với giá trị tùy chọn, dùng API có default hoặc kiểm tra key để biểu diễn rõ hành vi.

## 3. Đọc Context bằng `deferContextual`

`deferContextual` nhận một function được gọi khi có subscription. Function nhận `ContextView`, một giao diện chỉ đọc của Context hiện tại, rồi trả về Publisher.

```java
Mono<String> greeting = Mono.deferContextual(context -> {
    String user = context.get("user");
    String locale = context.getOrDefault("locale", "vi");

    return Mono.just("Xin chào " + user + " (" + locale + ")");
});

Mono<String> result = greeting.contextWrite(context -> context
    .put("user", "An")
    .put("locale", "vi")
);
```

`ContextView` không cung cấp thao tác sửa Context. Điều này phù hợp với vai trò đọc metadata trong một operator. Nếu thiếu key bắt buộc như `user`, `get("user")` sẽ báo lỗi thay vì âm thầm tạo giá trị không hợp lệ.

### Đọc Context ở giữa chuỗi bằng `transformDeferredContextual`

Khi muốn một nhóm operator đọc Context và biến đổi Publisher dựa trên metadata, có thể dùng `transformDeferredContextual`:

```java
Mono<Order> order = orderSource
    .transformDeferredContextual((source, context) -> {
        String tenantId = context.get("tenantId");
        return source.filter(item -> item.tenantId().equals(tenantId));
    });

Mono<Order> tenantOrder = order
    .contextWrite(context -> context.put("tenantId", "tenant-a"));
```

Function được gọi cho từng subscription với Publisher nguồn và ContextView của subscription đó. Ví dụ lọc đơn hàng theo tenant minh họa cách Context ảnh hưởng đến việc tạo chuỗi operator. Trong hệ thống thực, việc phân quyền tenant cần được thực hiện ở tầng truy cập dữ liệu đáng tin cậy; lọc ở pipeline không thay thế kiểm soát bảo mật tại database hoặc service.

## 4. Ghi Context bằng `contextWrite`

`contextWrite` tạo hoặc biến đổi Context mà các operator ở phía upstream có thể đọc. Đây là điểm dễ nhầm nhất: dữ liệu Context truyền theo hướng ngược với thứ tự khai báo operator.

```java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just(context.get("requestId"))
    )
    .map(id -> "request=" + id)
    .contextWrite(context -> context.put("requestId", "req-100"));
```

Khi subscriber subscribe, quá trình subscribe đi từ downstream ngược lên upstream. `contextWrite` nhận Context của subscriber, tạo Context mới rồi truyền Context đó về phía nguồn. Vì `deferContextual` nằm upstream của `contextWrite`, nó đọc được `requestId`.

Sơ đồ hướng truyền:

```text
Thứ tự khai báo Publisher:

source.deferContextual(...)
        |
        v
      map(...)
        |
        v
 contextWrite(...)
        |
        v
     subscriber

Hướng tín hiệu dữ liệu:       source  ------------------> subscriber
Hướng Context khi subscribe:  source  <------------------ subscriber
```

Hãy nhớ hai chiều khác nhau:

- `onNext`, `onComplete`, `onError` đi từ upstream xuống downstream.
- Context được cung cấp từ subscriber về phía upstream trong quá trình subscribe.

Do đó, `contextWrite` thường được đặt ở phía downstream của operator cần đọc Context. Nếu đặt `contextWrite` ở phía upstream của một operator đọc Context, thay đổi đó không tự chảy xuôi để operator phía sau nhìn thấy.

## 5. Nhiều `contextWrite` và quy tắc ưu tiên

Khi có nhiều `contextWrite`, mỗi operator biến đổi Context mà nó nhận từ downstream trước khi chuyển Context về upstream. Vì thế, operator `contextWrite` gần nguồn hơn có thể ghi đè key mà một `contextWrite` ở phía downstream đã đặt.

```java
Mono<String> value = Mono.deferContextual(context ->
        Mono.just(context.get("mode"))
    )
    .contextWrite(context -> context.put("mode", "source-side"))
    .contextWrite(context -> context.put("mode", "subscriber-side"));
```

Kết quả là `source-side`:

1. Subscriber bắt đầu với Context ban đầu.
2. `contextWrite` cuối cùng trong chuỗi (gần downstream hơn) thêm `mode=subscriber-side`.
3. Context mới đi tiếp về upstream.
4. `contextWrite` gần nguồn hơn ghi `mode=source-side`.
5. `deferContextual` đọc Context sau cùng và thấy `source-side`.

Nếu hai `contextWrite` dùng các key khác nhau, các key có thể cùng tồn tại:

```java
Mono<String> metadata = Mono.deferContextual(context ->
        Mono.just(context.get("requestId") + "/" + context.get("tenantId"))
    )
    .contextWrite(context -> context.put("requestId", "req-7"))
    .contextWrite(context -> context.put("tenantId", "tenant-b"));
```

Kết quả là `req-7/tenant-b`. Mỗi bước tạo Context mới và bổ sung key tương ứng.

Để code dễ đọc, nên tránh ghi cùng một key ở nhiều vị trí nếu không có lý do rõ ràng. Nếu key có thể bị ghi đè, hãy xác định rõ nơi nào là nguồn có thẩm quyền và kiểm thử giá trị cuối cùng.

## 6. Phạm vi Context trong `flatMap`

`flatMap` tạo subscription cho Publisher con. Reactor truyền Context của subscription hiện tại sang các Publisher con để chúng có thể đọc metadata như request ID hoặc tenant ID.

```java
Mono<List<Order>> orders = userIdSource
    .flatMap(userId -> Mono.deferContextual(context -> {
        String tenantId = context.get("tenantId");
        return orderRepository.findByUserAndTenant(userId, tenantId).collectList();
    }))
    .contextWrite(context -> context.put("tenantId", "tenant-a"));
```

Publisher con đọc được `tenantId` từ Context của subscription. Điều này giúp metadata theo request đi qua các bước lồng nhau mà không cần thêm tham số vào mọi lambda.

Một `contextWrite` đặt bên trong Publisher con có phạm vi subscription con đó:

```java
Flux<Result> results = ids.flatMap(id ->
    Mono.deferContextual(context ->
        service.load(id, context.get("requestId"))
    )
    .contextWrite(context -> context.put("operation", "load-item"))
);
```

`operation` được thêm cho nhánh con và có thể được đọc bởi operator ở phía upstream bên trong nhánh đó. Thay đổi này không ghi ngược vào Context của subscription cha hoặc sang nhánh `flatMap` khác. Mỗi inner subscription có Context scope riêng.

Không nên đặt trạng thái mutable dùng chung trong Context rồi sửa nó từ nhiều nhánh `flatMap`. Dù Context bất biến, object được lưu làm value vẫn có thể mutable. Nếu nhiều nhánh cùng giữ một tham chiếu mutable, race condition vẫn có thể xảy ra. Ưu tiên value bất biến hoặc trạng thái có cơ chế đồng bộ riêng.

## 7. Context không phụ thuộc scheduler

Context thuộc subscription, không thuộc thread. Vì vậy, operator đọc Context vẫn có thể lấy metadata sau `publishOn` hoặc `subscribeOn`:

```java
Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.just("requestId=" + context.get("requestId"))
    )
    .publishOn(Schedulers.parallel())
    .map(value -> value + ", stage=parallel")
    .publishOn(Schedulers.single())
    .flatMap(value -> Mono.deferContextual(context ->
        Mono.just(value + ", tenant=" + context.get("tenantId"))
    ))
    .contextWrite(context -> context
        .put("requestId", "req-42")
        .put("tenantId", "tenant-a")
    );
```

Hai điểm đọc Context nằm ở các vùng thực thi khác nhau, nhưng đều đọc metadata của cùng subscription. `publishOn` thay đổi thread xử lý tín hiệu; nó không làm mất Context của subscription.

Đây là khác biệt quan trọng so với `ThreadLocal`. Nếu code downstream trực tiếp gọi `ThreadLocal.get()` sau khi chuyển scheduler, giá trị có thể không tồn tại trên thread mới hoặc có thể thuộc một tác vụ khác đã dùng thread đó. Context cung cấp metadata theo subscription một cách rõ ràng.

## 8. Reactor Context và ThreadLocal

Context và ThreadLocal có mô hình sở hữu khác nhau:

| Đặc điểm | Reactor Context | `ThreadLocal` |
|---|---|---|
| Gắn với | Subscriber/subscription | Thread hiện tại |
| Qua scheduler boundary | Có thể truy cập tiếp theo subscription | Không tự động chuyển sang thread khác |
| Cập nhật | Bất biến, thao tác trả Context mới | Thường sửa giá trị gắn với thread |
| Phạm vi | Một pipeline/subscription | Mọi code chạy trên thread đó có thể truy cập |
| Mục đích phù hợp | Metadata reactive như request ID, tenant, tracing | Thư viện đồng bộ hoặc API cũ phụ thuộc thread |

Không nên dùng Context và ThreadLocal thay thế lẫn nhau một cách tùy tiện. Nếu một thư viện cũ yêu cầu ThreadLocal, có thể cần bridge để capture/restore metadata tại ranh giới phù hợp.

### Tích hợp với Micrometer Context Propagation

Trong hệ sinh thái Reactor hiện đại, thư viện Micrometer Context Propagation có thể giúp kết nối Reactor Context với các context dựa trên ThreadLocal. Các `ThreadLocalAccessor` đã đăng ký mô tả cách đọc và ghi từng ThreadLocal. Reactor cung cấp các cơ chế như `contextCapture()` và chế độ automatic context propagation để hỗ trợ capture/restore trong phạm vi được cấu hình.

Ví dụ khái quát khi ứng dụng đã đăng ký accessor phù hợp:

```java
Hooks.enableAutomaticContextPropagation();

Mono<String> result = legacyService.call()
    .contextCapture()
    .publishOn(Schedulers.parallel())
    .map(this::format);
```

Đây là minh họa tích hợp, không phải cấu hình đầy đủ cho mọi ứng dụng. Cần có dependency Micrometer Context Propagation tương thích, đăng ký accessor cho từng ThreadLocal và chọn chế độ propagation phù hợp với phiên bản Reactor đang dùng. Automatic mode nên được bật lúc khởi động ứng dụng, trước khi tạo các pipeline cần áp dụng. Không giả định mọi ThreadLocal được tự động capture nếu chưa đăng ký accessor hoặc chưa cấu hình propagation.

Với code mới, ưu tiên đọc Context trực tiếp bằng `deferContextual` hoặc truyền dữ liệu qua tham số. Bridge ThreadLocal chủ yếu hữu ích khi tích hợp thư viện cũ hoặc API không thể thay đổi.

## 9. Ví dụ thực tế: request ID xuyên qua nhiều service

Giả sử một request gọi service hồ sơ, sau đó truy vấn đơn hàng. Mỗi bước cần ghi log với cùng request ID:

```java
Mono<CustomerSummary> loadSummary(String customerId) {
    return customerService.find(customerId)
        .flatMap(customer -> orderService.findRecent(customer.id())
            .collectList()
            .map(orders -> new CustomerSummary(customer, orders)))
        .doOnEach(signal -> {
            if (signal.isOnNext()) {
                String requestId = signal.getContextView()
                    .getOrDefault("requestId", "unknown");
                log.info("requestId={} summary ready", requestId);
            }
        });
}

Mono<CustomerSummary> request = loadSummary("customer-9")
    .contextWrite(context -> context.put("requestId", "req-2026-42"));
```

`doOnEach` nhận `Signal` và có thể đọc `ContextView` gắn với tín hiệu. Nhờ Context được truyền từ subscriber về upstream, các operator trong `loadSummary` có thể truy cập cùng metadata. Khi dùng `doOnEach`, cần kiểm tra loại tín hiệu trước khi đọc dữ liệu hoặc ghi log để tránh xử lý terminal signal như một phần tử.

Một cách khác là đọc Context ngay tại service boundary bằng `deferContextual`:

```java
Mono<Customer> findCustomer(String customerId) {
    return Mono.deferContextual(context -> {
        String requestId = context.get("requestId");
        return customerRepository.findById(customerId)
            .doOnNext(customer -> log.info(
                "requestId={} customer={}", requestId, customer.id()
            ));
    });
}
```

Cách này làm rõ metadata được đọc tại ranh giới service. Hãy tránh đọc Context quá sâu trong mọi hàm nếu chỉ một số tầng cần metadata; truyền tham số tường minh có thể dễ hiểu hơn khi dữ liệu là đầu vào nghiệp vụ thực sự.

## 10. Kiểm thử Context và chiều truyền bằng StepVerifier

`StepVerifier` hỗ trợ cung cấp Context cho subscriber qua `StepVerifierOptions`. Đây là cách kiểm thử một Publisher yêu cầu metadata mà không cần đặt `contextWrite` bên trong chính Publisher.

### Subscriber cung cấp Context

```java
Mono<String> requestId = Mono.deferContextual(context ->
    Mono.just(context.get("requestId"))
);

StepVerifier.create(
        requestId,
        StepVerifierOptions.create()
            .withInitialContext(Context.of("requestId", "test-42"))
    )
    .expectNext("test-42")
    .verifyComplete();
```

Kiểm thử xác nhận nguồn đọc được Context ban đầu do subscriber cung cấp.

### Kiểm thử `contextWrite` ở phía downstream

```java
StepVerifier.create(
        Mono.deferContextual(context -> Mono.just(context.get("tenant")))
            .map(String::toUpperCase)
            .contextWrite(context -> context.put("tenant", "tenant-a"))
    )
    .expectNext("TENANT-A")
    .verifyComplete();
```

### Kiểm thử thứ tự ghi đè

```java
StepVerifier.create(
        Mono.deferContextual(context -> Mono.just(context.get("mode")))
            .contextWrite(context -> context.put("mode", "near-source"))
            .contextWrite(context -> context.put("mode", "near-subscriber"))
    )
    .expectNext("near-source")
    .verifyComplete();
```

Kiểm thử xác nhận `contextWrite` gần nguồn hơn được áp dụng sau trong quá trình Context đi ngược về upstream và vì vậy ghi đè giá trị cùng key.

### Kiểm thử qua scheduler boundary

```java
StepVerifier.create(
        Mono.deferContextual(context -> Mono.just(context.get("requestId")))
            .publishOn(Schedulers.parallel())
            .map(id -> "seen=" + id)
            .publishOn(Schedulers.single())
            .flatMap(value -> Mono.deferContextual(context ->
                Mono.just(value + ", tenant=" + context.get("tenantId"))
            ))
            .contextWrite(context -> context
                .put("requestId", "req-8")
                .put("tenantId", "tenant-c")
            )
    )
    .expectNext("seen=req-8, tenant=tenant-c")
    .verifyComplete();
```

Kiểm thử xác nhận metadata vẫn truy cập được qua nhiều scheduler boundary. Không nên assert tên thread cụ thể vì scheduler có thể chọn worker khác nhau giữa các lần chạy.

## 11. Những lỗi thường gặp

| Cách làm sai | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ Context truyền từ upstream xuống downstream | Operator phía sau `contextWrite` không tự thấy thay đổi được ghi ở phía trước nó. | Nhớ Context đi từ subscriber về upstream khi subscribe. |
| Đặt `contextWrite` trước nguồn nhưng mong operator phía sau đọc được | Thay đổi chỉ có hiệu lực cho vùng upstream của nó. | Đặt `contextWrite` ở downstream của operator cần đọc Context. |
| Dùng nhiều `contextWrite` cùng key mà không xét thứ tự | Giá trị cuối cùng có thể bị ghi đè ngoài dự kiến. | Xác định nơi có thẩm quyền và kiểm thử thứ tự. |
| Dùng Context để chứa payload lớn hoặc trạng thái mutable dùng chung | Tăng chi phí và có thể tạo race condition. | Truyền payload bằng `onNext`; dùng value bất biến cho metadata. |
| Cho rằng Context tự động biến thành ThreadLocal | Code thư viện cũ có thể không đọc được metadata sau scheduler boundary. | Dùng Context trực tiếp hoặc cấu hình Micrometer Context Propagation. |
| Giả định `flatMap` chia sẻ mọi thay đổi Context ngược ra ngoài | Context write trong inner publisher có phạm vi riêng. | Xem Context của mỗi inner subscription là scope độc lập. |
| Gọi `get` với key tùy chọn có thể vắng mặt | Pipeline lỗi khi key không tồn tại. | Dùng `hasKey`, `getOrEmpty` hoặc `getOrDefault`. |
| Dùng Context thay cho tham số nghiệp vụ rõ ràng | Dependency bị ẩn và khó đọc khi bảo trì. | Chỉ đưa metadata xuyên suốt vào Context; dữ liệu nghiệp vụ quan trọng nên truyền tường minh. |

## 12. Checklist thiết kế Context

Trước khi đưa metadata vào Context, hãy xác nhận:

- Giá trị này có phải metadata theo request/subscription hay là payload nghiệp vụ?
- Key có được chuẩn hóa bằng hằng số hoặc kiểu riêng không?
- Giá trị là bắt buộc hay tùy chọn; cách xử lý khi thiếu key đã rõ chưa?
- `contextWrite` được đặt downstream của operator cần đọc Context chưa?
- Có nhiều `contextWrite` ghi cùng key và thứ tự ghi đè có chủ đích không?
- Context có tiếp tục được đọc đúng trong Publisher con của `flatMap` không?
- Scheduler boundary có làm lộ ra giả định sai về ThreadLocal không?
- Nếu tích hợp thư viện cũ, accessor và cơ chế context propagation đã được cấu hình tương thích chưa?
- Kiểm thử đã bao gồm Context ban đầu, ghi đè, inner publisher và nhiều scheduler chưa?

Reactor Context giúp metadata đi cùng subscription thay vì phụ thuộc vào thread. Khi nắm được chiều truyền ngược của Context, vị trí đặt `contextWrite` và phạm vi của các Publisher lồng nhau, bạn có thể truyền request ID, tenant hoặc tracing metadata qua pipeline `Mono`/`Flux` một cách rõ ràng, kể cả khi luồng chuyển scheduler. Hãy giữ Context cho metadata nhỏ, dùng dữ liệu bất biến và kiểm thử các ranh giới nơi ngữ cảnh được ghi hoặc đọc.
