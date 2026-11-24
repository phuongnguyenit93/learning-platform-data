# Tích hợp hệ thống cũ dùng ThreadLocal theo phạm vi kiểm soát

Nhiều thư viện Java được viết cho mô hình xử lý đồng bộ lưu thông tin theo thread bằng `ThreadLocal`. Ví dụ phổ biến là mã tenant, correlation ID, thông tin người dùng hiện tại hoặc MDC dùng để gắn dữ liệu vào log. Trong ứng dụng reactive, một pipeline có thể chuyển qua nhiều thread khi dùng scheduler hoặc khi chờ I/O. `ThreadLocal` gắn với thread hiện tại nên giá trị được thiết lập ở thread nhận request không tự động đi theo tín hiệu khi pipeline tiếp tục trên thread khác.

Reactor cung cấp `Context` để mang dữ liệu theo subscription, độc lập với thread thực thi. Khi cần gọi thư viện cũ vẫn đọc `ThreadLocal`, có thể tạo một cầu nối có kiểm soát giữa Reactor Context và ThreadLocal bằng Micrometer Context Propagation. Cách tích hợp an toàn là giữ Reactor Context làm nơi truyền dữ liệu trong pipeline, chỉ khôi phục ThreadLocal tại ranh giới gọi thư viện cũ và bảo đảm giá trị trên thread được dọn sạch sau callback.

## 1. Vì sao ThreadLocal không tự đi theo pipeline reactive?

`ThreadLocal<T>` lưu một giá trị riêng cho từng thread. Khi thread A gọi `set`, thread B không nhìn thấy giá trị đó. Trong mô hình reactive, một request có thể bắt đầu trên event-loop thread A, tiếp tục sau I/O trên thread B và chạy callback tiếp theo trên thread C. Vì vậy, không thể giả định ThreadLocal đã thiết lập ở đầu request vẫn tồn tại ở mọi toán tử.

```java
static final ThreadLocal<String> TENANT_ID = new ThreadLocal<>();

Mono<Customer> loadCustomer(String customerId) {
    return Mono.fromCallable(() -> {
        // Có thể chạy trên worker thread khác thread nhận request.
        String tenantId = TENANT_ID.get();
        return legacyCustomerDao.find(tenantId, customerId);
    }).subscribeOn(Schedulers.boundedElastic());
}
```

Nếu `TENANT_ID` được thiết lập trên thread nhận request, worker thread của `boundedElastic` thường không có giá trị đó. Kết quả có thể là `null`, truy vấn sai tenant hoặc lỗi bảo mật khó phát hiện. Việc đổi `subscribeOn` hay `publishOn` không tự sao chép ThreadLocal.

Reactor Context có vòng đời khác:

- `ThreadLocal` thuộc về một thread và được đọc qua thread hiện tại.
- `Context` thuộc về một subscription và được truyền theo chuỗi tín hiệu, dù các callback chạy trên thread nào.
- `Context` là cấu trúc bất biến; muốn thêm hoặc thay giá trị, toán tử tạo một Context mới.

Với code reactive mới, ưu tiên đọc dữ liệu từ Reactor Context bằng `deferContextual`. ThreadLocal chỉ nên được duy trì tại biên tích hợp với thư viện chưa hỗ trợ truyền context tường minh.

## 2. Đăng ký ThreadLocalAccessor

Micrometer Context Propagation cần biết cách đọc, đặt và xóa từng ThreadLocal. Đăng ký một accessor cho mỗi giá trị legacy mà ứng dụng muốn truyền:

```java
private static final ThreadLocal<String> LEGACY_TENANT = new ThreadLocal<>();

static void registerLegacyAccessors() {
    ContextRegistry.getInstance().registerThreadLocalAccessor(
        "legacyTenant",
        LEGACY_TENANT::get,
        LEGACY_TENANT::set,
        LEGACY_TENANT::remove
    );
}
```

Accessor khai báo một khóa (`legacyTenant`) để liên kết giá trị trong Reactor Context với ThreadLocal tương ứng. Các hàm getter, setter và resetter lần lượt đọc giá trị, đặt giá trị và xóa giá trị trên thread hiện tại. Dùng `remove()` làm resetter giúp thread worker không giữ lại dữ liệu của request trước sau khi callback kết thúc.

Đăng ký accessor một lần trong giai đoạn khởi tạo ứng dụng, trước khi các pipeline cần nó được subscribe. Không đăng ký lại cùng accessor ở mỗi request hoặc mỗi lần gọi service. Nếu tích hợp MDC hoặc một thư viện có accessor được cung cấp sẵn, hãy dùng accessor tương ứng và tránh đăng ký hai accessor cùng quản lý một ThreadLocal.

Tên khóa phải nhất quán giữa accessor và giá trị được đặt trong Reactor Context. Không đặt nhiều dữ liệu khác nhau dưới cùng một khóa, và không dùng một ThreadLocal chung cho tenant, security principal và correlation ID vì chúng có vòng đời và chính sách bảo mật khác nhau.

## 3. Đưa dữ liệu vào Reactor Context tại ranh giới request

Ở đầu pipeline, hãy đưa dữ liệu request vào Reactor Context bằng `contextWrite`:

```java
Mono<Customer> customer = customerService.load(customerId)
    .contextWrite(context -> context.put("legacyTenant", tenantId));
```

Context được gắn với subscription và có thể được các toán tử upstream đọc thông qua `deferContextual`. Cách này không phụ thuộc vào thread nào thực thi pipeline sau đó.

Một service reactive mới có thể đọc trực tiếp Context mà không cần ThreadLocal:

```java
Mono<Customer> load(String customerId) {
    return Mono.deferContextual(context -> {
        String tenantId = context.get("legacyTenant");
        return customerRepository.findByTenantAndId(tenantId, customerId);
    });
}
```

`contextWrite` tác động tới Context mà các toán tử upstream nhìn thấy. Khi đặt nó ở ranh giới request, các service được gọi phía trong pipeline có thể đọc cùng khóa. Nếu một toán tử tạo subscription độc lập bằng `subscribe()` bên trong, subscription mới không tự động thuộc cùng chuỗi Context; hãy compose publisher bằng `flatMap`, `then` hoặc toán tử phù hợp.

## 4. Khôi phục ThreadLocal cho thư viện cũ

Khi thư viện cũ chỉ có API như `legacyDao.findForCurrentTenant(id)` và tự đọc ThreadLocal, cần khôi phục giá trị từ Reactor Context quanh đúng callback gọi thư viện. Micrometer Context Propagation cùng Reactor hỗ trợ hai chế độ chính: chế độ mặc định và chế độ automatic.

### Chế độ mặc định

Ở chế độ mặc định, Reactor khôi phục ThreadLocal từ Context tại một số ranh giới operator được hỗ trợ, tiêu biểu là callback của `handle` và `tap`. Có thể đặt lời gọi legacy trong `handle`:

```java
Mono<Customer> customer = Mono.deferContextual(context ->
    Mono.just(customerId)
        .<Customer>handle((id, sink) -> {
            // Accessor khôi phục LEGACY_TENANT từ Context
            // trong phạm vi callback handle.
            Customer value = legacyCustomerDao.findForCurrentTenant(id);
            sink.next(value);
        })
).contextWrite(context -> context.put("legacyTenant", tenantId));
```

Trong ví dụ, accessor có khóa `legacyTenant` đã được đăng ký. Callback `handle` nhận ThreadLocal đã được khôi phục trong lúc thực thi, nên thư viện cũ có thể đọc tenant hiện tại. Sau callback, giá trị ThreadLocal được khôi phục về trạng thái trước đó hoặc được xóa theo accessor.

Chế độ mặc định không có nghĩa mọi callback đều tự động thấy ThreadLocal. Nếu lời gọi legacy nằm trong `fromCallable`, `map` hoặc callback khác không thuộc ranh giới được hỗ trợ, không nên giả định ThreadLocal sẽ được khôi phục. Hãy dùng operator được hỗ trợ hoặc chuyển sang automatic mode khi cần phạm vi khôi phục rộng hơn.

### Chế độ automatic

Nếu ứng dụng cần khôi phục ThreadLocal trên tất cả operator callback được Reactor quản lý, có thể bật automatic context propagation khi khởi động:

```java
@PostConstruct
void configureContextPropagation() {
    registerLegacyAccessors();
    Hooks.enableAutomaticContextPropagation();
}
```

Trong chế độ này, Reactor khôi phục các ThreadLocal đã đăng ký từ Context quanh callback trên các operator, bao gồm lời gọi được chuyển sang scheduler khác. Cấu hình hook là cấu hình toàn cục của Reactor trong process; hãy bật một lần ở giai đoạn bootstrap, trước khi tạo các subscription cần áp dụng. Hook áp dụng cho các subscription được tạo sau khi bật.

Khi dùng automatic mode, pipeline có thể bọc lời gọi blocking như sau:

```java
Mono<Customer> customer = Mono.fromCallable(
        () -> legacyCustomerDao.findForCurrentTenant(customerId)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .contextWrite(context -> context.put("legacyTenant", tenantId));
```

Khi callable chạy trên worker thread, Reactor khôi phục `LEGACY_TENANT` từ Context để thư viện cũ đọc được. Sau callback, giá trị ThreadLocal được reset để worker thread có thể phục vụ request khác an toàn.

Automatic mode tiện lợi nhưng có chi phí khôi phục ThreadLocal tại nhiều ranh giới callback hơn. Hãy bật khi ứng dụng thực sự cần tương thích rộng với thư viện legacy; nếu chỉ có một vài điểm tích hợp, chế độ mặc định hoặc một cầu nối tường minh tại đúng ranh giới có thể dễ kiểm soát hơn.

## 5. contextCapture dùng khi giá trị hiện có nằm trong ThreadLocal

Đôi khi ứng dụng nhận request từ một framework đồng bộ đã đặt tenant hoặc correlation ID vào ThreadLocal. Nếu subscription được tạo ngay trong phạm vi mà ThreadLocal còn giá trị, `contextCapture()` có thể chụp các ThreadLocal đã đăng ký và đưa chúng vào Reactor Context:

```java
Mono<Response> response = Mono.fromCallable(
        () -> legacyApi.callCurrentContext()
    )
    .subscribeOn(Schedulers.boundedElastic())
    .contextCapture();
```

`contextCapture()` chụp trạng thái ThreadLocal tại thời điểm subscription, không phải tại thời điểm lắp ráp publisher. Do đó, nó chỉ hữu ích nếu ThreadLocal còn được thiết lập ở thread thực hiện subscribe. Nếu publisher được trả về rồi framework subscribe trên một thread khác sau khi ThreadLocal ban đầu đã bị xóa, giá trị cần thiết sẽ không được capture.

Trong ứng dụng reactive end-to-end, cách rõ ràng hơn thường là đọc dữ liệu request tại ranh giới vào và đặt nó vào Context bằng `contextWrite`. Dùng `contextCapture()` như adapter cho một ranh giới đồng bộ cụ thể, không dựa vào nó để truyền trạng thái xuyên suốt một request nếu thời điểm subscribe không được kiểm soát.

Khi automatic mode được bật, Reactor tự capture ThreadLocal đã đăng ký vào Context tại subscription; trong trường hợp đó không cần thêm `contextCapture()` chỉ để lặp lại cùng một bước capture. Tránh thêm nhiều cơ chế capture/restore chồng nhau nếu không có lý do rõ ràng.

## 6. Phạm vi ThreadLocal phải ngắn và có cleanup

ThreadLocal được đặt trên worker thread có thể bị giữ lại khi thread quay về pool. Nếu không xóa hoặc khôi phục giá trị sau callback, request tiếp theo có thể đọc nhầm tenant, user hoặc correlation ID của request trước. Đây là rủi ro rò rỉ dữ liệu giữa các request, không chỉ là lỗi log.

Một accessor phải cung cấp resetter đúng:

```java
ContextRegistry.getInstance().registerThreadLocalAccessor(
    "legacyTenant",
    LEGACY_TENANT::get,
    LEGACY_TENANT::set,
    LEGACY_TENANT::remove
);
```

Context Propagation quản lý việc đặt giá trị trước callback và khôi phục trạng thái sau callback. Nếu tự đặt ThreadLocal thủ công, luôn dùng `try/finally` để khôi phục giá trị trước đó:

```java
String previous = LEGACY_TENANT.get();
try {
    LEGACY_TENANT.set(tenantId);
    return legacyCustomerDao.findForCurrentTenant(customerId);
} finally {
    if (previous == null) {
        LEGACY_TENANT.remove();
    } else {
        LEGACY_TENANT.set(previous);
    }
}
```

Đoạn mã thủ công phù hợp khi một adapter đồng bộ tự kiểm soát trọn callback. Không đặt ThreadLocal ở đầu pipeline rồi hy vọng nó tồn tại qua `publishOn` hoặc `subscribeOn`. Cũng không xóa ThreadLocal của thread caller một cách tùy tiện nếu giá trị đó thuộc về framework hoặc một scope bên ngoài; hãy khôi phục đúng trạng thái trước khi trả quyền điều khiển.

## 7. Đặt ranh giới legacy càng hẹp càng tốt

Một adapter tốt cô lập API cũ trong một phương thức nhỏ, nhận dữ liệu nghiệp vụ rõ ràng và trả publisher cho caller:

```java
final class LegacyCustomerAdapter {
    Mono<Customer> find(String tenantId, String customerId) {
        return Mono.fromCallable(() -> {
                String previous = LEGACY_TENANT.get();
                try {
                    LEGACY_TENANT.set(tenantId);
                    return legacyCustomerDao.findForCurrentTenant(customerId);
                } finally {
                    if (previous == null) {
                        LEGACY_TENANT.remove();
                    } else {
                        LEGACY_TENANT.set(previous);
                    }
                }
            })
            .subscribeOn(Schedulers.boundedElastic());
    }
}
```

Adapter này dùng scope thủ công vì chính callback sở hữu trọn việc đặt và khôi phục ThreadLocal. Nó không yêu cầu phần còn lại của ứng dụng biết tên ThreadLocal hoặc phụ thuộc vào cách thư viện cũ lấy context. Nếu có nhiều ThreadLocal cần truyền, accessor và Context Propagation giúp tránh lặp lại logic thủ công cho từng trường.

Không để `ThreadLocal` lan ra domain model hoặc repository reactive mới. Các lớp mới nên nhận tenant ID hoặc principal qua tham số, hoặc đọc từ Reactor Context tại ranh giới phù hợp. Chỉ adapter legacy mới cần biết cách chuyển giá trị sang ThreadLocal.

## 8. Trường hợp MDC và thông tin bảo mật

MDC của một số logging framework lưu dữ liệu theo ThreadLocal. Khi log trong callback chạy trên thread khác, MDC có thể rỗng hoặc chứa dữ liệu còn sót lại từ công việc trước. Có thể dùng accessor tương thích MDC để chuyển các key được chọn giữa Reactor Context và MDC. Chỉ đưa các trường cần thiết như trace ID hoặc request ID; tránh sao chép toàn bộ MDC nếu nó chứa dữ liệu nhạy cảm hoặc giá trị không thuộc request hiện tại.

Với thông tin xác thực và principal, ưu tiên cơ chế reactive context của framework bảo mật đang dùng. Ví dụ, trong ứng dụng Spring Security reactive, dùng `ReactiveSecurityContextHolder` và các API bảo mật reactive thay vì tạo một ThreadLocal principal riêng. Cầu nối ThreadLocal chỉ nên phục vụ một thư viện cũ cụ thể không có API nhận principal tường minh.

Không xem việc khôi phục ThreadLocal là cơ chế cấp quyền. Giá trị được truyền phải được xác thực và kiểm tra quyền ở tầng bảo mật. Context propagation chỉ vận chuyển dữ liệu; nó không xác minh dữ liệu đó đúng, còn hạn hay thuộc request hiện tại.

## 9. Lỗi và cancellation ở ranh giới legacy

Khi lời gọi legacy ném exception, `Mono.fromCallable` chuyển exception thành `onError`. Context được khôi phục chỉ trong phạm vi callback; sau khi callback kết thúc, ThreadLocal được reset dù lời gọi thành công hay lỗi. Nếu cần chuyển exception thành lỗi miền nghiệp vụ, dùng `onErrorMap` ở ngoài adapter:

```java
Mono<Customer> customer = legacyAdapter.find(tenantId, customerId)
    .onErrorMap(LegacyStoreException.class,
        error -> new CustomerLookupException(customerId, error));
```

Nếu subscriber cancel trong khi một lời gọi blocking đang chạy, cancellation không đảm bảo thư viện cũ dừng ngay. Worker thread có thể tiếp tục bị giữ cho tới khi lời gọi trả về, trừ khi API hỗ trợ interrupt hoặc timeout riêng. Hãy cấu hình timeout ở chính client/database driver và chỉ dùng bounded elastic để cô lập thời gian chờ.

Không gọi `subscribe()` trong adapter để tự chạy công việc. Trả `Mono` cho caller để lỗi và cancellation thuộc cùng subscription. Nếu adapter tự subscribe, caller không thể compose bước tiếp theo hoặc quản lý vòng đời công việc theo request.

## 10. Kiểm thử việc truyền và khôi phục context

Kiểm thử nên xác minh ba điều: giá trị được đưa vào Context đúng, thư viện legacy nhìn thấy giá trị đó trong callback và ThreadLocal được dọn sau callback. Với automatic mode, có thể viết test tích hợp nhỏ dùng scheduler khác thread:

```java
private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

@Test
void restoresThreadLocalForLegacyCallback() {
    ContextRegistry.getInstance().registerThreadLocalAccessor(
        "tenant", TENANT::get, TENANT::set, TENANT::remove
    );
    Hooks.enableAutomaticContextPropagation();

    Mono<String> result = Mono.fromCallable(TENANT::get)
        .subscribeOn(Schedulers.boundedElastic())
        .contextWrite(context -> context.put("tenant", "tenant-42"));

    StepVerifier.create(result)
        .expectNext("tenant-42")
        .verifyComplete();
}
```

Ví dụ trên minh họa việc Context được khôi phục thành ThreadLocal cho callable chạy trên bounded elastic. Trong test suite thực tế, đăng ký accessor và bật hook toàn cục một lần ở fixture phù hợp; tránh để nhiều test cạnh tranh thay đổi global hook hoặc đăng ký trùng accessor. Có thể dùng một scheduler/test fixture cô lập và dọn cấu hình sau test theo API Reactor tương ứng.

Để kiểm tra cleanup, cho callback ghi lại ThreadLocal sau khi scope kết thúc hoặc thực hiện một callback kế tiếp trên cùng worker thread và xác minh nó không thấy tenant cũ. Không chỉ kiểm tra kết quả publisher; cần xác minh không rò rỉ giá trị qua lần thực thi tiếp theo.

Các trường hợp nên có trong test:

1. Context chứa giá trị: legacy callback đọc đúng giá trị trên thread khác.
2. Context không có khóa: ThreadLocal được reset, không lấy giá trị từ request trước.
3. Callback thành công và callback ném lỗi: cả hai đều dọn ThreadLocal.
4. Subscription bị cancel: xác minh hành vi của nguồn và giới hạn của API blocking.
5. Hai subscription với tenant khác nhau: mỗi callback chỉ thấy tenant của subscription tương ứng.

## 11. Những lỗi tích hợp thường gặp

- Đọc ThreadLocal trong callback sau `publishOn` hoặc `subscribeOn` mà không có cơ chế propagation.
- Đặt ThreadLocal ở thread nhận request rồi giả định nó được sao chép sang worker thread.
- Dùng `contextCapture()` nhưng subscription thực tế xảy ra sau khi ThreadLocal đã bị xóa.
- Cho rằng chế độ mặc định khôi phục ThreadLocal trong mọi operator callback.
- Bật automatic mode sau khi các subscription đã bắt đầu và kỳ vọng chúng tự áp dụng hook mới.
- Đăng ký accessor nhưng dùng khóa khác với khóa trong Reactor Context.
- Không cung cấp resetter hoặc không khôi phục giá trị trước đó, làm rò rỉ tenant/MDC giữa các tác vụ trên thread pool.
- Dùng ThreadLocal để mang security principal trong toàn bộ ứng dụng reactive thay vì API reactive của framework.

Khi điều tra lỗi, hãy xác định thread thực hiện callback, nơi Context được đặt, thời điểm subscription diễn ra, accessor đang dùng và chế độ propagation đã bật. Sau đó kiểm tra resetter và vòng đời của subscription. Những thông tin này thường đủ để phân biệt lỗi thiếu capture, lỗi khôi phục sai phạm vi và lỗi rò rỉ ThreadLocal.

## 12. Quy tắc thiết kế khi cần tương thích với hệ thống cũ

Giữ Reactor Context làm phương tiện truyền dữ liệu trong pipeline. Đưa tenant, trace ID hoặc metadata request vào Context tại ranh giới vào bằng `contextWrite`; đăng ký accessor cho ThreadLocal mà thư viện cũ cần; chọn chế độ mặc định với các điểm `handle`/`tap` được kiểm soát hoặc automatic mode khi cần khôi phục rộng hơn. Nếu giá trị chỉ tồn tại trong ThreadLocal của một framework đồng bộ trước subscription, dùng `contextCapture()` tại ranh giới có thời điểm subscribe được bảo đảm.

Đặt lời gọi legacy trong adapter hẹp, cô lập blocking I/O bằng `fromCallable` và `boundedElastic` khi cần, bảo đảm ThreadLocal được reset sau callback và trả publisher cho caller quản lý lỗi/cancellation. Không để ThreadLocal trở thành state truyền thông chính của ứng dụng reactive. Cầu nối này là lớp tương thích có phạm vi rõ ràng để hệ thống cũ tiếp tục hoạt động trong khi phần mới sử dụng Reactor Context và các API bất đồng bộ một cách nhất quán.
