# Vai trò của Micrometer Context Propagation với ThreadLocal và Reactor Context

## Mục tiêu

Trong ứng dụng Java, thông tin của một request thường cần đi qua nhiều lớp xử lý: controller, service, executor, callback bất đồng bộ hoặc chuỗi reactive. Thông tin đó có thể gồm tenant hiện tại, correlation ID, Observation đang hoạt động hoặc dữ liệu tracing.

ThreadLocal gắn dữ liệu với thread đang chạy. Reactor Context gắn dữ liệu với subscriber và subscription của chuỗi reactive. Hai cơ chế có vòng đời khác nhau. Khi tác vụ chuyển sang thread khác, ThreadLocal không tự đi theo; khi Reactor đổi thread qua publishOn hoặc subscribeOn, Reactor Context vẫn đi theo chuỗi nhưng ThreadLocal không tự được cập nhật ở mọi operator.

Micrometer Context Propagation cung cấp cầu nối giữa các cơ chế context. Thư viện dùng ThreadLocalAccessor để đọc/ghi ThreadLocal, ContextAccessor để làm việc với context dạng map, ContextRegistry để quản lý accessor và ContextSnapshot để chụp/khôi phục giá trị.

Sau bài này, bạn có thể:

- Phân biệt ThreadLocal với Reactor Context.
- Đăng ký ThreadLocalAccessor cho dữ liệu ứng dụng.
- Dùng ContextSnapshot để capture và restore giá trị theo scope.
- Bọc ExecutorService để truyền context khi submit tác vụ.
- Dùng Reactor Context, contextCapture và contextWrite đúng vị trí.
- Phân biệt chế độ mặc định với automatic context propagation của Reactor.
- Tránh rò rỉ context giữa các request khi thread được tái sử dụng.

## Hai mô hình lưu context khác nhau

### ThreadLocal gắn với thread

ThreadLocal lưu một giá trị riêng cho từng thread. Khi cùng một thread gọi nhiều hàm đồng bộ, các hàm đó có thể đọc cùng giá trị mà không phải truyền tham số qua mọi tầng.

Ví dụ:

~~~java
public final class TenantContext {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static String get() {
        return CURRENT.get();
    }

    public static void set(String tenant) {
        CURRENT.set(tenant);
    }

    public static void clear() {
        CURRENT.remove();
    }
}
~~~

ThreadLocal thuận tiện trong code imperative, nhưng nó không đại diện cho request hoặc task. Nó chỉ gắn với thread. Nếu request A kết thúc mà giá trị không được xóa, thread pool có thể dùng lại thread đó cho request B và làm B nhìn thấy dữ liệu của A.

### Reactor Context gắn với subscriber

Reactor Context là một cấu trúc key-value bất biến, gắn với subscription. Các operator có thể đọc Context thông qua deferContextual hoặc transformDeferredContextual. Dữ liệu vẫn theo chuỗi reactive ngay cả khi các operator chạy trên nhiều thread.

Ví dụ:

~~~java
Mono<String> tenantName = Mono.deferContextual(context ->
        Mono.just(context.get("app.tenant"))
).contextWrite(context -> context.put("app.tenant", "tenant-a"));
~~~

Reactor Context không phụ thuộc thread hiện tại. Nó phù hợp để lưu dữ liệu theo subscription như tenant, security context, request metadata hoặc Observation.

### So sánh

| Đặc điểm | ThreadLocal | Reactor Context |
|---|---|---|
| Gắn với | Thread | Subscriber/subscription |
| Cách đọc | ThreadLocal.get() | deferContextual hoặc ContextView |
| Qua thread switch | Không tự truyền | Đi theo reactive chain |
| Phù hợp | Code imperative và thư viện dựa trên ThreadLocal | Code reactive |
| Rủi ro chính | Giá trị cũ còn trên thread pool | Ghi sai vị trí trong chain hoặc làm mất Context khi tích hợp publisher ngoài |
| Cleanup | Xóa hoặc khôi phục khi scope kết thúc | Theo vòng đời subscription |

Không nên thay Reactor Context bằng ThreadLocal trong ứng dụng reactive. Context Propagation tồn tại để kết nối hai mô hình khi một thư viện imperative cần ThreadLocal hoặc một luồng imperative gọi sang Reactor.

## Micrometer Context Propagation cung cấp những gì?

Thư viện có bốn abstraction chính:

| Thành phần | Trách nhiệm |
|---|---|
| ThreadLocalAccessor | Đọc, đặt và xóa một giá trị ThreadLocal |
| ContextAccessor | Đọc/ghi một context dạng map như Reactor Context |
| ContextRegistry | Đăng ký và tìm các accessor theo key |
| ContextSnapshot | Chụp các giá trị context và khôi phục chúng trong một scope hoặc tác vụ |

ContextSnapshotFactory tạo snapshot và khôi phục ThreadLocal từ các context đã đăng ký. ContextSnapshot.Scope đảm bảo giá trị trước đó được khôi phục hoặc giá trị mới được xóa khi scope đóng.

Thư viện không tự tạo Observation, Span hay trace. Nó chỉ chuyển các giá trị context giữa những cơ chế lưu trữ. Muốn truyền trace qua HTTP hoặc message broker, ứng dụng vẫn cần Micrometer Tracing và các propagation handler để inject/extract trace headers.

## Cài đặt

Khi dự án dùng Spring Boot hoặc Micrometer BOM, thêm dependency Context Propagation mà không tự ghim version riêng:

~~~kotlin
dependencies {
    implementation("io.micrometer:context-propagation")
}
~~~

Reactor Core tích hợp SPI của Micrometer Context Propagation từ Reactor 3.5.0. Để Reactor tự hiểu Reactor Context, cần có cả reactor-core và micrometer context-propagation trên classpath. ReactorContextAccessor được nạp qua ServiceLoader; thông thường không cần tự tạo hoặc đăng ký accessor này.

Hãy để Spring Boot BOM hoặc Micrometer BOM quản lý version tương thích. Khi kiểm tra một API cụ thể, đối chiếu version context-propagation và Reactor thực tế trong dependency tree của ứng dụng.

## Đăng ký ThreadLocalAccessor

Mỗi ThreadLocal cần được mô tả bằng một accessor. Accessor cung cấp key ổn định để ContextRegistry và ContextSnapshot biết giá trị nào đang được truyền.

Ví dụ accessor cho TenantContext:

~~~java
import io.micrometer.context.ThreadLocalAccessor;

public final class TenantThreadLocalAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "app.tenant";

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return TenantContext.get();
    }

    @Override
    public void setValue(String value) {
        TenantContext.set(value);
    }

    @Override
    public void setValue() {
        TenantContext.clear();
    }
}
~~~

Phương thức setValue() không tham số có nhiệm vụ xóa ThreadLocal khi cơ chế propagation yêu cầu clear key bị thiếu. Đây là chi tiết quan trọng để thread worker không giữ lại giá trị của task trước.

Đăng ký accessor một lần khi ứng dụng khởi động:

~~~java
ContextRegistry.getInstance()
        .registerThreadLocalAccessor(new TenantThreadLocalAccessor());
~~~

ContextRegistry.getInstance() là registry toàn cục. Chỉ đăng ký một accessor cho mỗi key. Trong test hoặc module cần cô lập, có thể tạo ContextRegistry riêng và truyền registry đó vào ContextSnapshotFactory.

Không đăng ký một accessor mới cho từng request. Accessor mô tả cách đọc/ghi một loại context, không phải dữ liệu của một request cụ thể.

## Capture và restore bằng ContextSnapshot

ContextSnapshot chụp các giá trị từ ThreadLocal đã đăng ký. Khi gọi setThreadLocals(), snapshot đặt các giá trị đó lên thread hiện tại và trả về Scope. Khi đóng Scope, giá trị trước khi mở scope được khôi phục.

Ví dụ:

~~~java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;

ContextRegistry registry = new ContextRegistry();
registry.registerThreadLocalAccessor(new TenantThreadLocalAccessor());

ContextSnapshotFactory snapshotFactory = ContextSnapshotFactory.builder()
        .contextRegistry(registry)
        .clearMissing(true)
        .build();

TenantContext.set("tenant-a");
ContextSnapshot snapshot = snapshotFactory.captureAll();

TenantContext.set("tenant-b");
try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
    // Trong scope này, TenantContext.get() trả về tenant-a.
    processCurrentTenant();
}

// Sau khi scope đóng, giá trị tenant-b trước đó được khôi phục.
TenantContext.clear();
~~~

Capture tạo bản chụp tại thời điểm captureAll() được gọi. Nếu ThreadLocal thay đổi sau đó, snapshot không tự thay đổi theo. Scope chỉ có hiệu lực trong đoạn code nằm giữa lúc mở và đóng; không giữ ThreadLocal đã khôi phục sau khi scope kết thúc.

Mặc định clearMissing là false. Khi snapshot hoặc context nguồn không có một key, factory sẽ không chủ động xóa ThreadLocal tương ứng. Với executor thread pool, nếu muốn key vắng mặt được xóa trong scope, hãy cấu hình clearMissing(true). Khi Scope đóng, giá trị trước đó của worker vẫn được khôi phục.

Luôn dùng try-with-resources cho ContextSnapshot.Scope. Nếu bỏ qua close(), worker thread có thể tiếp tục mang giá trị context cũ.

## Truyền context qua ExecutorService

### Bọc tác vụ riêng lẻ

Nếu chỉ cần truyền context cho một task, capture snapshot trước khi submit rồi bọc Runnable hoặc Callable:

~~~java
TenantContext.set("tenant-a");
ContextSnapshot snapshot = snapshotFactory.captureAll();

executor.submit(snapshot.wrap(() -> {
    // Thread worker nhìn thấy tenant-a.
    processCurrentTenant();
}));
~~~

snapshot.wrap(...) tạo task mới. Khi task chạy, snapshot khôi phục ThreadLocal; khi task kết thúc, scope được đóng để khôi phục trạng thái của worker.

### Bọc toàn bộ ExecutorService

Nếu nhiều task cần truyền context, dùng ContextExecutorService:

~~~java
import io.micrometer.context.ContextExecutorService;
import io.micrometer.context.ContextSnapshotFactory;

ExecutorService delegate = Executors.newFixedThreadPool(4);
ExecutorService contextAwareExecutor =
        ContextExecutorService.wrap(delegate, snapshotFactory);

TenantContext.set("tenant-a");
try {
    Future<String> result = contextAwareExecutor.submit(TenantContext::get);
    String tenant = result.get();
    // tenant là tenant-a
} finally {
    TenantContext.clear();
    contextAwareExecutor.shutdown();
}
~~~

ContextExecutorService capture context khi task được submit và restore khi task chạy. Tạo wrapper một lần rồi dùng lại, thay vì tạo một executor mới cho từng request.

Đối với ScheduledExecutorService, có ContextScheduledExecutorService để áp dụng cùng nguyên tắc cho tác vụ được schedule. Hãy kiểm tra đúng overload và version API đang sử dụng.

### Vì sao phải capture ở thời điểm submit?

Giả sử request A đặt TenantContext thành tenant-a rồi submit task. Request B có thể đặt tenant-b trên một thread khác. Snapshot của A phải được capture khi A submit; task của A sẽ thấy tenant-a dù worker chạy muộn hơn.

Nếu capture sau khi task đã được đưa vào queue, thread submit có thể đã xử lý request khác hoặc đã xóa context. Snapshot khi đó không còn đại diện cho request ban đầu.

## Reactor Context và Context Propagation

### Ghi và đọc Reactor Context trực tiếp

Đối với code reactive, cách rõ ràng nhất là dùng Reactor Context trực tiếp:

~~~java
Mono<String> result = Mono.deferContextual(context ->
        Mono.just("tenant=" + context.get("app.tenant"))
).contextWrite(context -> context.put("app.tenant", "tenant-a"));
~~~

contextWrite ghi dữ liệu vào Context cho các operator ở phía upstream. deferContextual đọc Context của subscription hiện tại. Dữ liệu không cần chuyển qua ThreadLocal nếu toàn bộ code có thể dùng Reactor API.

Reactor Context là immutable. Các thao tác put/remove tạo Context mới thay vì thay đổi object cũ. Hãy đặt contextWrite ở đúng vị trí trong chain; vị trí của operator quyết định những operator nào nhìn thấy giá trị.

### contextCapture: đưa ThreadLocal vào Reactor Context

Khi code imperative tạo hoặc subscribe một reactive chain, có thể cần chụp ThreadLocal hiện tại vào Reactor Context:

~~~java
TenantContext.set("tenant-a");
try {
    String result = Mono.just("payload")
            .publishOn(Schedulers.boundedElastic())
            .handle((value, sink) ->
                    sink.next(TenantContext.get() + ":" + value))
            .contextCapture()
            .block();
} finally {
    TenantContext.clear();
}
~~~

contextCapture() chụp ThreadLocal tại thời điểm subscribe và ghi các giá trị có accessor vào Reactor Context. Trong default mode, handle là một trong các operator hỗ trợ khôi phục ThreadLocal trong callback của operator.

Không nhầm thời điểm assembly với subscription. Reactor thường lazy: tạo Mono chưa thực thi chain. contextCapture() đọc ThreadLocal khi subscription xảy ra, không phải lúc biến Mono được khai báo.

Nếu code đã nằm trong một reactive chain, chẳng hạn controller WebFlux trả về Mono, hãy ưu tiên ghi dữ liệu trực tiếp vào Reactor Context bằng contextWrite hoặc dùng context do framework cung cấp. contextCapture() chủ yếu hữu ích ở ranh giới imperative gọi sang Reactor khi ThreadLocal đã được thiết lập tại thời điểm subscribe.

### Khôi phục ThreadLocal trong một operator cụ thể

Nếu không bật automatic mode, có thể chủ động khôi phục ThreadLocal từ Reactor Context bằng ContextSnapshotFactory:

~~~java
ContextSnapshotFactory snapshotFactory = ContextSnapshotFactory.builder()
        .clearMissing(true)
        .build();

Mono<String> result = Mono.just("payload")
        .publishOn(Schedulers.boundedElastic())
        .transformDeferredContextual((source, contextView) ->
                source.map(value -> {
                    try (ContextSnapshot.Scope scope =
                                 snapshotFactory.setThreadLocalsFrom(contextView)) {
                        return TenantContext.get() + ":" + value;
                    }
                })
        )
        .contextWrite(context -> context.put(
                TenantThreadLocalAccessor.KEY, "tenant-a"));
~~~

Scope khôi phục ThreadLocal từ ContextView trước khi gọi code imperative và phục hồi trạng thái worker sau khi callback kết thúc. Đây là cách kiểm soát rõ phạm vi mà ThreadLocal được sử dụng.

## Hai chế độ của Reactor

Reactor tích hợp Context Propagation theo hai chế độ.

### Default mode

Từ Reactor 3.5.0, nếu context-propagation có trên classpath, Reactor hỗ trợ khôi phục ThreadLocal ở một số operator được chọn, chủ yếu là handle() và tap().

Trong default mode:

- Reactor Context vẫn có thể được đọc ở bất kỳ vị trí phù hợp bằng deferContextual.
- contextCapture() có thể capture ThreadLocal tại subscription.
- handle() và tap() khôi phục ThreadLocal cho callback của operator khi Context phù hợp.
- Các operator khác không tự động khôi phục ThreadLocal.
- Key không có trong Context có thể không được thay đổi trên thread hiện tại; cần chú ý trạng thái ThreadLocal đã tồn tại trước đó.

Ví dụ:

~~~java
Mono<String> result = Mono.just("payload")
        .publishOn(Schedulers.boundedElastic())
        .handle((value, sink) ->
                sink.next(TenantContext.get() + ":" + value))
        .contextWrite(context -> context.put(
                TenantThreadLocalAccessor.KEY, "tenant-a"));
~~~

Callback trong handle() có thể đọc tenant-a khi accessor đã đăng ký. Nếu thay handle() bằng doOnNext() trong default mode, không nên giả định TenantContext.get() đã được khôi phục.

### Automatic mode

Từ Reactor 3.5.3, có thể bật automatic context propagation:

~~~java
import reactor.core.publisher.Hooks;

public static void main(String[] args) {
    Hooks.enableAutomaticContextPropagation();
    SpringApplication.run(Application.class, args);
}
~~~

Automatic mode khôi phục ThreadLocal trên các operator trong reactive chain theo Reactor Context. Hook chỉ áp dụng cho subscription mới, vì vậy nên bật lúc ứng dụng khởi động, trước khi tạo tải.

Ví dụ:

~~~java
Hooks.enableAutomaticContextPropagation();

Mono<String> result = Mono.just("payload")
        .publishOn(Schedulers.boundedElastic())
        .map(value -> TenantContext.get() + ":" + value)
        .contextWrite(context -> context.put(
                TenantThreadLocalAccessor.KEY, "tenant-a"));
~~~

Trong automatic mode, callback map() cũng có thể nhìn thấy tenant-a sau khi chuyển thread. Khi Context không có key tương ứng, Reactor cần xóa ThreadLocal đã đăng ký để tránh giá trị của tác vụ trước rò sang tác vụ mới. Vì vậy, ThreadLocalAccessor phải triển khai đúng phương thức setValue() không tham số để xóa trạng thái.

### Chọn chế độ nào?

| Tiêu chí | Default mode | Automatic mode |
|---|---|---|
| Phạm vi khôi phục ThreadLocal | Callback của handle/tap và các điểm hỗ trợ | Các operator trong reactive chain |
| Mức độ tường minh | Cao hơn, dễ thấy nơi ThreadLocal được dùng | Thuận tiện hơn cho thư viện imperative |
| Cleanup khi key vắng mặt | Cần chú ý trạng thái hiện có | Tự xử lý việc xóa key đã đăng ký theo Context |
| Chi phí | Thường ít điểm khôi phục hơn | Có thể thêm overhead ở nhiều operator |
| Phù hợp | Chỉ một vài callback cần ThreadLocal | Ứng dụng phụ thuộc nhiều thư viện dùng ThreadLocal |

Automatic mode không luôn nhanh hơn hoặc chậm hơn. Chi phí phụ thuộc số operator, số accessor, scheduler và cách ứng dụng dùng context. Hãy đo dưới tải gần với production trước khi chọn.

## Truyền Observation và tracing context

Micrometer Observation có thể được lưu trong ThreadLocal khi Observation được mở scope. Để context đó đi qua executor hoặc Reactor, cần accessor tương ứng và registry được cấu hình đúng.

Trong Micrometer, ObservationThreadLocalAccessor cung cấp cầu nối cho current Observation. Với một số cách tích hợp thủ công, cần gắn ObservationRegistry vào accessor:

~~~java
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;

ObservationThreadLocalAccessor.getInstance()
        .setObservationRegistry(observationRegistry);
~~~

Kiểm tra phiên bản Micrometer và cấu hình Spring Boot trước khi gọi thủ công. Một số integration có thể đã cấu hình accessor này.

ObservationThreadLocalAccessor được cung cấp qua ServiceLoader trong Micrometer Observation. Tài liệu Micrometer nêu rõ việc đặt registry trên singleton accessor từ Micrometer 1.10.8 cho kịch bản dùng Hook thủ công. Với Spring Boot, hãy kiểm tra auto-configuration trước để tránh đăng ký hoặc cấu hình trùng.

Khi truyền Observation qua executor, ContextExecutorService có thể capture current Observation và khôi phục nó trong task. Từ đó, Observation con được tạo trong task có thể nhận đúng parent.

Khi dùng Reactor, Observation có thể được lưu trong Reactor Context. Automatic mode có thể khôi phục current Observation vào ThreadLocal cho các thư viện cần đọc nó. Tuy nhiên, code reactive nên ưu tiên Reactor Context hoặc Observation API thay vì tự đọc ThreadLocal ở mọi operator.

Context Propagation chỉ chuyển context trong tiến trình. Khi gọi HTTP hoặc gửi message sang tiến trình khác, trace context phải được inject vào carrier như HTTP headers hoặc message headers bởi Micrometer Tracing propagation handler; service nhận phải extract các header đó để tiếp tục trace.

## Cleanup và tránh rò rỉ context

Thread pool tái sử dụng thread giữa nhiều task. Nếu ThreadLocal không được khôi phục hoặc xóa, task tiếp theo có thể nhìn thấy dữ liệu của task trước.

Các nguyên tắc cần giữ:

1. Mọi ThreadLocalAccessor phải có cách xóa giá trị.
2. Dùng ContextSnapshot.Scope trong try-with-resources.
3. Capture tại ranh giới submit hoặc subscribe, không capture sau khi context đã thay đổi.
4. Không giữ ContextSnapshot lâu hơn vòng đời tác vụ nếu không cần.
5. Không lưu context của request vào field static hoặc singleton mutable.
6. Không tự set ThreadLocal trong một operator mà không khôi phục trạng thái sau callback.
7. Với automatic mode, coi Reactor Context là nguồn dữ liệu chuẩn; key vắng mặt phải được phép xóa ThreadLocal tương ứng.

Không dùng một ThreadLocal chung để lưu nhiều loại dữ liệu không liên quan. Tách key và accessor theo trách nhiệm để tránh ghi đè hoặc xóa nhầm context của thành phần khác.

## Kiểm thử context propagation

### Kiểm thử capture và restore

~~~java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ContextSnapshotTest {

    @Test
    void restoresCapturedValueAndThenRestoresPreviousThreadLocal() {
        ContextRegistry registry = new ContextRegistry();
        registry.registerThreadLocalAccessor(new TenantThreadLocalAccessor());
        ContextSnapshotFactory factory = ContextSnapshotFactory.builder()
                .contextRegistry(registry)
                .clearMissing(true)
                .build();

        TenantContext.set("tenant-a");
        ContextSnapshot snapshot = factory.captureAll();
        TenantContext.set("worker-before");

        try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
            assertThat(TenantContext.get()).isEqualTo("tenant-a");
        }

        assertThat(TenantContext.get()).isEqualTo("worker-before");
        TenantContext.clear();
    }
}
~~~

Test xác minh snapshot khôi phục giá trị đã capture và Scope trả thread về trạng thái trước đó.

### Kiểm thử ExecutorService

Tạo một executor một thread để tái sử dụng cùng worker:

~~~java
import io.micrometer.context.ContextExecutorService;
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import org.junit.jupiter.api.Test;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class ExecutorContextPropagationTest {

    @Test
    void propagatesContextWhenTaskIsSubmitted() throws Exception {
        ContextRegistry registry = new ContextRegistry();
        registry.registerThreadLocalAccessor(new TenantThreadLocalAccessor());
        ContextSnapshotFactory factory = ContextSnapshotFactory.builder()
                .contextRegistry(registry)
                .clearMissing(true)
                .build();

        ExecutorService delegate = Executors.newSingleThreadExecutor();
        ExecutorService executor = ContextExecutorService.wrap(delegate, factory);
        try {
            TenantContext.set("tenant-a");
            Future<String> first = executor.submit(TenantContext::get);
            assertThat(first.get()).isEqualTo("tenant-a");

            delegate.submit(() -> TenantContext.set("stale-tenant")).get();
            TenantContext.clear();
            Future<String> second = executor.submit(TenantContext::get);
            assertThat(second.get()).isNull();
        } finally {
            TenantContext.clear();
            executor.shutdown();
            assertThat(executor.awaitTermination(5, TimeUnit.SECONDS)).isTrue();
        }
    }
}
~~~

Ngoài kết quả trả về, integration test nên submit nhiều task với tenant khác nhau trên cùng worker để xác minh task sau không nhận giá trị của task trước.

Trong test trên, một task gửi trực tiếp qua delegate cố ý đặt giá trị cũ để xác minh clearMissing(true) xóa giá trị đó trong scope của task được bọc. Trong production, hãy gửi toàn bộ công việc cần propagation qua wrapper; task đi thẳng qua delegate không được bảo vệ.

### Kiểm thử Reactor Context

Với code reactive, trước hết kiểm tra giá trị trong Reactor Context trực tiếp:

~~~java
StepVerifier.create(
        Mono.deferContextual(context ->
                Mono.just(context.get(TenantThreadLocalAccessor.KEY)))
            .contextWrite(context -> context.put(
                    TenantThreadLocalAccessor.KEY, "tenant-a"))
)
.expectNext("tenant-a")
.verifyComplete();
~~~

Sau đó, nếu ứng dụng cần ThreadLocal trong callback, kiểm thử riêng default mode với handle/tap hoặc automatic mode với Hooks.enableAutomaticContextPropagation(). Test cần có publishOn để xác minh context qua thread switch, đồng thời xác minh ThreadLocal được dọn sau khi callback kết thúc.

## Những lỗi thường gặp

**Cho rằng ThreadLocal tự đi theo task.** ThreadLocal thuộc thread, không thuộc request. Dùng snapshot hoặc executor wrapper khi task chuyển thread.

**Dùng ThreadLocal làm nguồn context chính trong Reactor.** ThreadLocal không theo subscription. Dùng Reactor Context để lưu request-specific state.

**Nhầm ContextSnapshot với Observation.** Snapshot chỉ capture/restore giá trị; nó không tạo Observation hoặc Span.

**Không đăng ký ThreadLocalAccessor.** Snapshot không thể capture một ThreadLocal mà registry không biết cách đọc.

**Không triển khai thao tác clear.** Worker thread có thể giữ giá trị cũ khi Context không chứa key.

**Capture quá muộn.** Context của request gốc có thể đã bị xóa hoặc thay đổi trước lúc task thực sự chạy.

**Quên đóng Scope.** ThreadLocal không được khôi phục sau callback, gây rò rỉ giữa task.

**Cho rằng contextWrite tự đặt ThreadLocal trong mọi operator.** contextWrite ghi Reactor Context; chỉ cơ chế propagation mới khôi phục ThreadLocal.

**Bật automatic mode sau khi ứng dụng đã có subscription.** Hook chỉ áp dụng cho subscription mới. Hãy bật khi khởi động.

**Bật automatic mode mà không đo hiệu năng.** Mỗi điểm khôi phục có chi phí. Đo dưới tải thực tế và chỉ truyền các key cần thiết.

**Nhầm context propagation nội bộ với distributed tracing propagation.** Chuyển context giữa thread không tự inject trace headers sang HTTP hoặc message.

## Checklist triển khai

1. Xác định dữ liệu nào gắn với thread và dữ liệu nào gắn với reactive subscription.
2. Ưu tiên Reactor Context trong code reactive.
3. Tạo ThreadLocalAccessor cho từng ThreadLocal cần truyền.
4. Đăng ký accessor một lần vào ContextRegistry.
5. Dùng ContextSnapshotFactory để capture/restore.
6. Dùng ContextSnapshot.Scope trong try-with-resources.
7. Bọc ExecutorService khi nhiều task cần propagation.
8. Dùng contextWrite để ghi và deferContextual để đọc Reactor Context.
9. Dùng contextCapture khi cần capture ThreadLocal tại subscription.
10. Chọn default hoặc automatic mode theo phạm vi callback cần khôi phục.
11. Bật automatic mode trước các subscription đầu tiên nếu chọn chế độ này.
12. Xác minh cleanup trên thread pool và cardinality của context keys.
13. Kiểm thử qua thread switch và nhiều task trên cùng worker.
14. Cấu hình distributed tracing propagation riêng cho HTTP/message carrier.

## Kết luận

ThreadLocal lưu dữ liệu theo thread, còn Reactor Context lưu dữ liệu theo subscriber. Micrometer Context Propagation kết nối hai mô hình bằng ThreadLocalAccessor, ContextAccessor, ContextRegistry và ContextSnapshot. Trong code imperative, dùng snapshot hoặc ContextExecutorService để truyền giá trị sang worker; trong Reactor, ưu tiên Context trực tiếp và chỉ khôi phục ThreadLocal tại những điểm cần thiết. Default mode chỉ khôi phục ở các operator được chọn, còn automatic mode mở rộng khôi phục trên reactive chain và chỉ áp dụng cho subscription mới. Dù chọn cách nào, cleanup phải được thực hiện đúng để thread pool không mang context của request cũ sang tác vụ mới.

## Tài liệu tham khảo

- [Micrometer Context Propagation - Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html): các abstraction và tình huống chuyển context giữa ThreadLocal, Reactor Context và executor.
- [Micrometer Context Propagation - Examples](https://docs.micrometer.io/context-propagation/reference/usage.html): ThreadLocalAccessor, ContextRegistry, ContextSnapshot và Scope.
- [Micrometer Context Propagation - ContextSnapshot API](https://www.javadoc.io/doc/io.micrometer/context-propagation/1.2.1/io/micrometer/context/ContextSnapshot.html): wrap Runnable, Callable, Consumer và Executor.
- [Micrometer Context Propagation - ContextSnapshotFactory.Builder](https://www.javadoc.io/doc/io.micrometer/context-propagation/1.2.1/io/micrometer/context/ContextSnapshotFactory.Builder.html): clearMissing, ContextRegistry và bộ lọc key được capture.
- [Micrometer Context Propagation - ContextExecutorService](https://www.javadoc.io/doc/io.micrometer/context-propagation/1.2.1/io/micrometer/context/ContextExecutorService.html): bọc ExecutorService và capture context khi submit task.
- [Micrometer - Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html): propagation qua Executor, Reactor Context và Observation.
- [Project Reactor - Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): contextWrite, contextCapture, default mode và automatic mode.
