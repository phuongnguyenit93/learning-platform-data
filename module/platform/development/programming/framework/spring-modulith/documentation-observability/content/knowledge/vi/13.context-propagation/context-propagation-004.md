# ThreadLocal và giới hạn mặc định

## 1. Bối cảnh: vì sao ThreadLocal không tự đi theo tác vụ?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, một yêu cầu có thể đi qua module **order**, phát sự kiện **OrderPlaced**, rồi được module **notification** xử lý sau khi giao dịch đặt hàng commit. Khi luồng xử lý chuyển từ request thread sang executor, từ imperative code sang Reactor, hoặc sang một tiến trình khác, thông tin như **trace context**, **correlation ID**, **tenant ID** và **security context** không tự động đi theo chỉ vì chúng đang được lưu trong `ThreadLocal`.

Bài thuộc chương **Context propagation** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module học này dùng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác trong ứng dụng Spring Boot thông qua module graph, Actuator, event metrics, tracing và context propagation. Trọng tâm ở đây là **ThreadLocal và giới hạn mặc định**: hiểu dữ liệu gắn với thread ra sao, tại sao mô hình này gặp vấn đề với async/reactive, và cách Spring/Micrometer chuyển ngữ cảnh một cách có kiểm soát.

Sau bài học, bạn có thể:

1. Giải thích vì sao mỗi thread có bản sao `ThreadLocal` riêng và tại sao đổi thread làm mất ngữ cảnh.
2. Nhận diện rủi ro khi dùng thread pool, `InheritableThreadLocal`, Reactor và tác vụ bất đồng bộ.
3. Phân biệt **ThreadLocal**, **Reactor Context**, **Micrometer Context Propagation** và dữ liệu truyền qua message/HTTP.
4. Dùng `ThreadLocalAccessor`, `ContextRegistry`, `ContextSnapshot` và `ContextPropagatingTaskDecorator`.
5. Cấu hình propagation cho `@Async` và Reactor theo phiên bản Spring Boot.
6. Kiểm chứng trace/log correlation qua listener bất đồng bộ của Spring Modulith mà không nhầm context propagation với transaction propagation.

## 2. ThreadLocal lưu dữ liệu theo thread như thế nào?

`ThreadLocal<T>` cung cấp một biến mà **mỗi thread truy cập có một bản sao giá trị độc lập**. Hai thread cùng đọc một đối tượng `ThreadLocal` vẫn có thể nhận hai giá trị khác nhau, vì giá trị được gắn với thread đang thực thi chứ không gắn với request, task, user hay application module.

~~~java
public final class RequestContext {

    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    private RequestContext() {
    }

    public static void set(String requestId) {
        REQUEST_ID.set(requestId);
    }

    public static String get() {
        return REQUEST_ID.get();
    }

    public static void clear() {
        REQUEST_ID.remove();
    }
}
~~~

Nếu thread A gọi `RequestContext.set("req-101")`, chỉ thread A nhìn thấy giá trị đó. Thread B gọi `RequestContext.get()` sẽ nhận giá trị riêng của B, thường là `null` nếu chưa khởi tạo. Khi thread A kết thúc tác vụ, giá trị không tự biến thành dữ liệu của một thread khác.

~~~mermaid
flowchart TD
    TL["ThreadLocal object: REQUEST_ID"]
    TL --> A["Thread A: req-101"]
    TL --> B["Thread B: null"]
    TL --> C["Thread C: req-303"]
    A --> A1["Code trên A đọc req-101"]
    B --> B1["Code trên B đọc null"]
    C --> C1["Code trên C đọc req-303"]
~~~

Đây là lý do `ThreadLocal` tiện cho các API đồng bộ dựa trên thread: code sâu trong call stack có thể đọc thông tin gắn với thread hiện tại mà không phải truyền tham số qua từng phương thức. Một số thư viện dùng cơ chế này cho logging MDC, observation/tracing scope, locale hoặc security context.

### Vòng đời của giá trị

- `get()` đọc giá trị của thread hiện tại; nếu chưa có, `initialValue()` hoặc supplier có thể được gọi theo cách triển khai.
- `set(value)` gán giá trị cho thread hiện tại.
- `remove()` xóa giá trị của thread hiện tại. Lần `get()` tiếp theo có thể khởi tạo lại giá trị mặc định.

Nên dọn dữ liệu trong `finally` hoặc dùng scope có `close()` để khôi phục trạng thái trước đó:

~~~java
RequestContext.set("req-101");
try {
    handleRequest();
}
finally {
    RequestContext.clear();
}
~~~

Nếu chỉ gọi `set()` mà quên `remove()`, giá trị có thể tồn tại lâu hơn request dự kiến, nhất là khi thread được tái sử dụng trong thread pool.

## 3. Những giới hạn mặc định của ThreadLocal

### 3.1. Không tự truyền sang thread khác

Đây là giới hạn cơ bản nhất. `ThreadLocal` không có cơ chế mặc định sao chép giá trị từ thread gọi sang thread thực thi tác vụ. Ví dụ:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

RequestContext.set("req-101");
try {
    executor.submit(() ->
            System.out.println(RequestContext.get()));
}
finally {
    RequestContext.clear();
}
~~~

Task có thể chạy trên worker thread khác, nên kết quả không được đảm bảo là `req-101`; nếu worker chưa có giá trị thì thường là `null`. Không nên dựa vào thời điểm scheduler chạy để hy vọng giá trị vẫn còn trong thread nguồn.

### 3.2. Thread pool tái sử dụng thread

Trong server, thread pool thường tái sử dụng worker cho nhiều request/task. Nếu task trước đặt một giá trị mà không xóa, task sau chạy trên cùng worker có thể đọc nhầm dữ liệu còn sót lại.

~~~mermaid
sequenceDiagram
    participant R1 as Request A
    participant W as Worker thread-1
    participant R2 as Request B
    R1->>W: set tenant=tenant-A
    W-->>R1: xử lý xong nhưng quên remove
    R2->>W: chạy trên worker được tái sử dụng
    W-->>R2: get tenant vẫn có thể là tenant-A
~~~

Rủi ro không chỉ là trace bị sai. Nếu dữ liệu lưu trong ThreadLocal là tenant, user hoặc quyền truy cập, việc rò rỉ giữa hai tác vụ có thể trở thành lỗi phân tách dữ liệu hoặc bảo mật. Vì vậy:

- Dùng `try/finally` để dọn dữ liệu do ứng dụng tự đặt.
- Khi khôi phục context, phải lưu trạng thái trước đó và khôi phục/xóa sau khi scope đóng.
- Không lưu object lớn hoặc tài nguyên có vòng đời dài trong ThreadLocal của worker.
- Viết test dùng lại cùng một worker để phát hiện context rò rỉ.

### 3.3. InheritableThreadLocal không giải quyết thread pool

`InheritableThreadLocal` sao chép giá trị từ thread cha sang thread con **tại thời điểm thread con được tạo**. Điều đó không có nghĩa giá trị được sao chép mỗi lần submit task.

Thread pool thường tạo worker từ trước rồi tái sử dụng. Nếu worker được tạo trước khi request đặt context, nó không nhận giá trị mới; nếu worker đã mang giá trị cũ, tác vụ sau có thể thấy trạng thái không phù hợp. Do đó, `InheritableThreadLocal` không phải giải pháp đáng tin cậy cho context propagation của executor.

### 3.4. Reactive pipeline không gắn với một thread cố định

Trong Reactor, một chuỗi `Mono`/`Flux` có thể chuyển qua nhiều scheduler và thread. Nhiều subscription có thể dùng chung một thread ở các thời điểm khác nhau. Vì vậy, **ThreadLocal không phải kho ngữ cảnh phù hợp cho reactive flow**.

Reactor cung cấp **Reactor Context** gắn với subscriber/sequence. Nó được truyền dọc chuỗi reactive mà không phụ thuộc thread đang chạy operator.

~~~mermaid
flowchart LR
    S["Subscriber A + Reactor Context A"] --> O1["operator 1 / thread-1"]
    O1 --> O2["publishOn / thread-7"]
    O2 --> O3["operator 2 / thread-7"]
    S2["Subscriber B + Reactor Context B"] --> O4["operator / thread-1"]
~~~

Thread-1 có thể lần lượt chạy code của nhiều subscriber. Nếu code chỉ đọc một ThreadLocal theo thread, nó không tự biết giá trị nào thuộc subscriber A hay B.

### 3.5. Không truyền qua tiến trình hoặc mạng

`ThreadLocal` chỉ có ý nghĩa trong JVM và thread hiện tại. Khi gọi HTTP service khác, gửi Kafka/RabbitMQ message hoặc ghi event vào database, giá trị không tự xuất hiện ở tiến trình nhận. Muốn truyền qua boundary đó, phải dùng header/metadata được định nghĩa rõ, chẳng hạn W3C `traceparent`, baggage được cho phép hoặc correlation ID trong message.

### 3.6. Không phải mọi loại context đều có thể sao chép an toàn

Trace context, MDC, tenant context, security context và transaction context có quy tắc riêng. Việc sao chép một giá trị không tự làm cho đối tượng bên trong an toàn khi dùng đồng thời. Đặc biệt:

- Không sao chép `EntityManager`, JDBC connection hoặc transaction resource sang thread khác.
- Không giả định `SecurityContext` được truyền chỉ vì Micrometer observation được truyền.
- Không đưa access token, cookie, thông tin cá nhân hoặc payload nhạy cảm vào baggage/trace attributes.
- Chỉ propagate các giá trị có accessor và vòng đời đã được xác định.

### 3.7. Virtual threads không tự giải quyết propagation

Virtual thread vẫn là một đối tượng `Thread`, nên mỗi virtual thread có giá trị ThreadLocal riêng. Việc tạo một virtual thread mới không tự sao chép mọi giá trị từ thread đang submit task. Virtual threads giảm nhu cầu giữ một pool platform thread lớn và tránh một số vấn đề do tái sử dụng worker, nhưng **ranh giới giữa hai thread vẫn còn**. Khi cần giữ trace/tenant context qua task boundary, vẫn phải dùng cơ chế propagation phù hợp; đồng thời tránh đặt quá nhiều dữ liệu lớn vào ThreadLocal của số lượng virtual thread rất cao.

## 4. Context Propagation là lớp cầu nối

Thư viện **Micrometer Context Propagation** giúp chuyển dữ liệu giữa các cơ chế context khác nhau, chẳng hạn:

- Imperative code sử dụng `ThreadLocal`.
- Reactive code sử dụng Reactor `Context`.
- Tác vụ bất đồng bộ chạy trên executor/thread pool.
- Các loại context khác có `ContextAccessor` phù hợp.

Khi ứng dụng dùng trực tiếp các API như `ThreadLocalAccessor`, `ContextSnapshot` hoặc cần Reactor bridge, bảo đảm dependency `io.micrometer:context-propagation` có trên classpath. Ví dụ Gradle, với version được quản lý bởi BOM tương thích:

~~~groovy
dependencies {
    implementation 'io.micrometer:context-propagation'
}
~~~

Reactor Core từ 3.5 tích hợp SPI của thư viện này; `ReactorContextAccessor` được phát hiện qua `ServiceLoader` khi các dependency cần thiết có mặt. Không cần tự khởi tạo hoặc gọi accessor nội bộ của Reactor trong code ứng dụng.

Các abstraction chính:

| Thành phần | Vai trò |
| --- | --- |
| **ThreadLocalAccessor** | Đọc, đặt và xóa giá trị của một ThreadLocal cụ thể. |
| **ContextAccessor** | Đọc/ghi dữ liệu từ loại context dạng map hoặc context khác. |
| **ContextRegistry** | Đăng ký các accessor để thư viện biết cách lấy và khôi phục từng loại giá trị. |
| **ContextSnapshot** | Ảnh chụp các giá trị context tại một thời điểm, dùng để khôi phục ở scope khác. |
| **ContextSnapshotFactory** | Tạo snapshot theo registry và các tùy chọn capture. |
| **ContextPropagatingTaskDecorator** | Bọc task của Spring executor để capture và restore context quanh lúc task chạy. |

~~~mermaid
flowchart TD
    TL["ThreadLocal trên request thread"] --> A["ThreadLocalAccessor"]
    RC["Reactor Context"] --> CA["ContextAccessor"]
    A --> REG["ContextRegistry"]
    CA --> REG
    REG --> SNAP["ContextSnapshot"]
    SNAP --> TASK["Task / Executor / Reactive stage"]
    TASK --> RESTORE["Khôi phục giá trị trong scope"]
    RESTORE --> CODE["Code đích đọc context"]
~~~

Context Propagation không thay thế cách lưu context gốc. Imperative code vẫn có thể dùng ThreadLocal; Reactor code vẫn nên dùng Reactor Context. Thư viện giúp **bắc cầu khi đi qua ranh giới** giữa hai cách lưu đó.

## 5. ThreadLocalAccessor: đăng ký giá trị do ứng dụng sở hữu

Các thư viện như Micrometer có accessor cho observation/tracing context của chúng. Nếu ứng dụng tự tạo một ThreadLocal, cần đăng ký accessor để Context Propagation biết cách đọc, đặt và xóa giá trị.

Ví dụ một holder tenant đơn giản:

~~~java
package com.example.shop.context;

public final class TenantContext {

    private static final ThreadLocal<String> TENANT_ID = new ThreadLocal<>();

    private TenantContext() {
    }

    public static String get() {
        return TENANT_ID.get();
    }

    public static void set(String tenantId) {
        TENANT_ID.set(tenantId);
    }

    public static void clear() {
        TENANT_ID.remove();
    }
}
~~~

Accessor kết nối holder với thư viện:

~~~java
package com.example.shop.context;

import io.micrometer.context.ThreadLocalAccessor;

public final class TenantContextAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "shop.tenant";

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

Đăng ký accessor một lần trong quá trình khởi tạo ứng dụng:

~~~java
import io.micrometer.context.ContextRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ContextAccessorConfiguration {

    @Bean
    TenantContextAccessor tenantContextAccessor() {
        TenantContextAccessor accessor = new TenantContextAccessor();
        ContextRegistry.getInstance()
            .registerThreadLocalAccessor(accessor);
        return accessor;
    }
}
~~~

Đây là ví dụ accessor cho dữ liệu tenant **do ứng dụng quản lý**. Khi dùng trong hệ thống nhiều tenant, cần xác định nguồn tenant đã được xác thực và cách kiểm soát giá trị trước khi đặt vào context; không tin tenant ID tùy ý từ header mà chưa qua xác thực.

Phương thức `setValue()` không tham số có nhiệm vụ **xóa** ThreadLocal khi key không có trong snapshot hoặc scope kết thúc. Bỏ qua thao tác dọn dẹp này có thể làm giá trị của tác vụ trước rò sang tác vụ tiếp theo trên worker thread.

## 6. ContextSnapshot: chụp và khôi phục trong một scope

Khi có accessor, `ContextSnapshot` có thể capture giá trị hiện tại rồi khôi phục trên thread khác. Scope phải được đóng để trạng thái trước đó được phục hồi:

~~~java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;

ContextRegistry registry = ContextRegistry.getInstance();

TenantContext.set("tenant-A");
ContextSnapshot snapshot = ContextSnapshotFactory.builder()
    .contextRegistry(registry)
    .build()
    .captureAll();

TenantContext.set("tenant-B");
try (var scope = snapshot.setThreadLocals()) {
    // Trong scope này, TenantContext.get() trả tenant-A.
    performWork();
}
// Khi scope đóng, giá trị trước đó tenant-B được khôi phục.
TenantContext.clear();
~~~

Snapshot là ảnh chụp **tại thời điểm capture**, không phải tham chiếu luôn cập nhật đến ThreadLocal nguồn. Nếu đổi giá trị nguồn sau khi capture, snapshot không tự thay đổi. Cần capture đúng thời điểm và giới hạn phạm vi scope.

Trong code ứng dụng, không nên tự viết logic capture/restore rải rác nếu Spring đã cung cấp decorator hoặc Reactor integration cho boundary tương ứng. Ví dụ trên hữu ích để hiểu cơ chế nền và kiểm thử accessor tùy chỉnh.

## 7. Truyền context sang executor và @Async

Với imperative async, một cách tiếp cận phổ biến là dùng **ContextPropagatingTaskDecorator** trên executor. Decorator capture context khi task được submit và restore nó khi task chạy, sau đó khôi phục trạng thái worker trước đó.

### 7.1. Executor do ứng dụng tự cấu hình

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncExecutorConfiguration {

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("shop-async-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Khi dùng `@Async`, chỉ định executor mà ứng dụng thực sự cấu hình:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @Async("applicationTaskExecutor")
    public void generateReport() {
        // Observation/trace context đã đăng ký có thể được khôi phục
        // trong phạm vi task nếu accessor và decorator được cấu hình.
        generate();
    }

    private void generate() {
        // Công việc nền.
    }
}
~~~

`@EnableAsync` cần được bật ở cấu hình ứng dụng nếu chưa được cấu hình ở nơi khác. Việc có một bean decorator trong context **không tự chứng minh mọi executor đều dùng nó**; cần xác nhận executor bean thực sự được `@Async` chọn và có gắn decorator.

### 7.2. Khác biệt cấu hình theo Spring Boot

Tài liệu Spring Boot thay đổi cách opt-in theo phiên bản. Không nên sao chép một property từ phiên bản mới vào ứng dụng cũ mà chưa kiểm tra metadata cấu hình:

| Phiên bản tham chiếu | Executor auto-configured | Executor do ứng dụng tự tạo |
| --- | --- | --- |
| **Spring Boot 3.5** | Tài liệu observability hướng dẫn cung cấp `ContextPropagatingTaskDecorator` bean; kiểm tra executor auto-configured thực tế nhận decorator. | Gắn `new ContextPropagatingTaskDecorator()` qua `setTaskDecorator(...)`. |
| **Spring Boot 4.2** | Có thể opt-in bằng `spring.task.execution.propagate-context=true` cho `AsyncTaskExecutor` auto-configured. | Gắn `ContextPropagatingTaskDecorator` vào executor do ứng dụng quản lý. |

Ví dụ property cho Spring Boot 4.2:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Nếu ứng dụng định nghĩa nhiều executor, chỉ cấu hình property cho executor auto-configured không bảo đảm các executor tùy chỉnh đều được bao phủ. Hãy rà soát từng bean và tên executor được dùng.

## 8. Reactor Context và chế độ propagation mặc định

Trong Reactor, dữ liệu theo subscriber được lưu trong **Reactor Context**, không phải ThreadLocal. Các operator có thể chạy trên thread khác mà vẫn truy cập được cùng context của subscriber thông qua API Reactor.

~~~java
Mono.deferContextual(contextView ->
        Mono.just("tenant=" + contextView.get("shop.tenant")))
    .contextWrite(context -> context.put("shop.tenant", "tenant-A"));
~~~

`contextWrite` thêm giá trị vào context của subscriber; `deferContextual` đọc giá trị đó khi subscription chạy. Context không tự động biến thành ThreadLocal ở mọi operator.

### 8.1. Hai chế độ Reactor Context Propagation

Kể từ Reactor Core 3.5, tích hợp Micrometer Context Propagation hỗ trợ hai chế độ:

- **Default/limited mode:** chỉ khôi phục ThreadLocal trong một số operator nhất định, đáng chú ý là `handle` và `tap`, khi context đã được capture và accessor tương ứng đã đăng ký.
- **Automatic mode:** khôi phục ThreadLocal từ Reactor Context xuyên các ranh giới thread trong reactive chain. Chế độ này mở rộng phạm vi tự động nhưng có chi phí và yêu cầu dọn trạng thái chính xác.

Trong Spring Boot, property điều khiển chế độ là `spring.reactor.context-propagation`. Ví dụ bật automatic mode:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Trong chế độ mặc định **limited**, đoạn code nằm trong một `map` hoặc `doOnNext` bất kỳ không nên giả định ThreadLocal đã được khôi phục. Nếu cần truy cập dữ liệu reactive, ưu tiên đọc trực tiếp từ Reactor Context; nếu cần gọi code imperative dựa vào ThreadLocal, dùng cơ chế capture/restore phù hợp.

### 8.2. Ví dụ phân biệt Context và ThreadLocal

~~~java
static final ThreadLocal<String> TENANT = new ThreadLocal<>();
static final String TENANT_KEY = "shop.tenant";

Mono<String> pipeline = Mono.deferContextual(context ->
        Mono.delay(Duration.ofMillis(10))
            .map(ignored -> "context=" +
                context.getOrDefault(TENANT_KEY, "missing") +
                ", threadLocal=" + TENANT.get()))
    .contextWrite(context -> context.put(TENANT_KEY, "tenant-A"));
~~~

Trong default/limited mode, giá trị `tenant-A` có trong **Reactor Context** nhưng không mặc nhiên có trong `TENANT.get()` tại operator `map`. Trong automatic mode, ThreadLocal có thể được khôi phục từ Context nếu đã đăng ký accessor phù hợp. Kết quả cụ thể còn phụ thuộc thời điểm subscription, scheduler, operator và cấu hình.

### 8.3. Default mode cần context capture khi nào?

Nếu muốn capture ThreadLocal hiện tại tại thời điểm subscription để đưa vào Reactor Context, có thể dùng `contextCapture()`:

~~~java
TENANT.set("tenant-A");
try {
    Mono<String> result = Mono.deferContextual(context ->
            Mono.just(context.getOrDefault(TENANT_KEY, "missing")))
        .contextCapture();

    String tenant = result.block();
}
finally {
    TENANT.remove();
}
~~~

`contextCapture()` sử dụng Context Propagation để capture các ThreadLocal có accessor đã đăng ký và đưa giá trị vào Reactor Context. Nó không thể capture một ThreadLocal không có accessor. Trong automatic mode, một số blocking operator có thể thực hiện context capture tự động; không nên thêm thủ công mọi nơi mà không hiểu lifecycle.

### 8.4. Automatic mode có giới hạn gì?

Automatic mode giúp ThreadLocal có thể hiện diện xuyên các operator, nhưng phải khôi phục và xóa giá trị đúng theo Context của subscriber. Reactor Context là nguồn sự thật; nếu key không có trong Context, accessor tương ứng phải cho phép xóa ThreadLocal để không rò dữ liệu từ subscription trước.

Automatic mode cũng có thể ảnh hưởng hiệu năng do capture/restore quanh nhiều ranh giới. Chỉ bật sau khi đo tải đại diện và kiểm tra các thư viện dựa vào ThreadLocal. Với code reactive thuần, dùng Reactor Context trực tiếp thường rõ ràng hơn việc dựa vào ThreadLocal.

## 9. Những thứ Context Propagation không làm

Context Propagation giúp truyền **các giá trị đã được đăng ký** qua một boundary. Nó không biến mọi trạng thái JVM thành dữ liệu có thể sao chép và không thay thế các cơ chế quản lý riêng.

| Loại dữ liệu | ThreadLocal/Context Propagation có thể làm gì? | Điều không được giả định |
| --- | --- | --- |
| **Observation/trace context** | Khôi phục context đã đăng ký để tạo liên hệ observation/span và log correlation. | Mọi exporter đều thành công hoặc trace không bao giờ bị tách. |
| **MDC/correlation ID** | Có thể truyền qua accessor tương ứng, giữ log có ngữ cảnh. | MDC tự đồng bộ với trace context nếu không cấu hình. |
| **Tenant ID** | Có thể truyền nếu đăng ký accessor và xác thực nguồn dữ liệu. | Giá trị tenant đã được kiểm tra quyền truy cập. |
| **SecurityContext** | Có cơ chế riêng của Spring Security; có thể dùng executor/delegating wrapper phù hợp. | `ContextPropagatingTaskDecorator` tự truyền mọi security state. |
| **Transaction/JDBC resources** | Không nên copy transaction-bound resources sang thread khác. | Giao dịch của publisher tiếp tục tồn tại trong worker. |
| **Message metadata** | Có thể serialize một phần context đã cho phép vào header/message. | ThreadLocal tự đi qua Kafka, RabbitMQ hoặc HTTP. |
| **Object nghiệp vụ** | Có thể truyền object như tham số hoặc payload nếu thiết kế cho phép. | Snapshot là bản sao sâu, bất biến của mọi object trong context. |

### Transaction context là một ranh giới riêng

Một request có thể có transaction JDBC gắn với thread. Nếu gửi tác vụ sang executor, transaction đó không được Context Propagation chuyển sang thread worker. Với Spring Modulith, `@ApplicationModuleListener` thường chạy sau commit trong transaction riêng của listener. Đây là chủ đích để listener không phụ thuộc transaction đang mở của publisher.

Nếu worker cần đọc dữ liệu, nên dùng transaction mới và tải lại dữ liệu bằng khóa nghiệp vụ; không mang `EntityManager`, connection hoặc persistence context qua thread.

### Security context cần chính sách riêng

Spring Security mặc định thường lưu `SecurityContext` trong `SecurityContextHolder` với chiến lược ThreadLocal. Khi dùng async, cần xem xét cơ chế như `DelegatingSecurityContextExecutor`/wrapper hoặc tích hợp phù hợp của Spring Security. Chỉ đăng ký accessor tùy chỉnh khi hiểu rõ vòng đời, quyền hạn và cách xóa context sau task. Không truyền nguyên security context sang tác vụ nền dài hạn nếu nghiệp vụ không cần danh tính người gọi.

## 10. Áp dụng vào Spring Modulith event listener

Giả sử module **order** phát `OrderPlaced` sau khi lưu đơn, còn module **notification** dùng `@ApplicationModuleListener` để tạo yêu cầu gửi email. Listener xử lý bất đồng bộ sau commit:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.order.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    @ApplicationModuleListener
    public void on(OrderPlaced event) {
        // Ghi yêu cầu thông báo bằng eventId để hỗ trợ idempotency.
        createNotificationRequest(event.eventId(), event.orderId());
    }

    private void createNotificationRequest(String eventId, String orderId) {
        // Phần triển khai nghiệp vụ được lược bỏ.
    }
}
~~~

Khi listener chạy trên thread khác, ThreadLocal chứa trace context của request không tự hiện diện. Nếu executor dùng để chạy listener được cấu hình Context Propagation đúng cách, observation context đã đăng ký có thể được khôi phục cho phạm vi task. Cần kiểm tra **executor thực sự được Spring Modulith dùng**; một decorator trên executor không liên quan không có tác dụng.

~~~mermaid
sequenceDiagram
    autonumber
    participant HTTP as HTTP request thread
    participant O as Order module
    participant DB as Database
    participant E as Event dispatcher
    participant N as Notification worker
    HTTP->>O: placeOrder()
    O->>DB: save order
    O->>E: publish OrderPlaced
    O->>DB: commit transaction
    O-->>HTTP: response
    E-->>N: schedule listener
    Note over E,N: Context phải được capture/restore nếu cần giữ trace correlation
    N->>DB: transaction riêng của listener
    N-->>E: listener complete
~~~

Ba điều không nên nhầm:

1. **Sự kiện được công bố** không có nghĩa listener đã chạy.
2. **Context propagation thành công** không có nghĩa transaction của publisher được chuyển sang worker.
3. **Trace ID được giữ** không có nghĩa event được giao đúng một lần hoặc notification đã tới người nhận.

Nên ghi **eventId** trong log publisher và listener. Nếu retry xảy ra sau khi ứng dụng restart hoặc sự kiện được gửi qua broker, eventId vẫn là khóa tương quan nghiệp vụ ngay cả khi trace cũ không còn trong ThreadLocal.

## 11. Kiểm chứng propagation bằng log và test

### 11.1. Kiểm tra bằng log

Ghi nhận thread name, traceId và correlation/eventId ở cả hai phía:

~~~text
INFO thread=http-nio-8080-exec-3
  module=order action=event-published
  eventId=e-102 traceId=4bf92f...

INFO thread=shop-async-2
  module=notification action=listener-started
  eventId=e-102 traceId=4bf92f...
~~~

Hai dòng trên chỉ là ví dụ khi context đã được truyền. Nếu traceId ở listener vắng mặt hoặc khác, kiểm tra decorator/executor, accessor, sampling và cơ chế retry. Nếu eventId vẫn khớp, hai log vẫn có thể được đối chiếu ở tầng nghiệp vụ.

### 11.2. Test không truyền context

Một test với executor đơn giản có thể minh họa giới hạn ThreadLocal:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    RequestContext.set("req-101");

    Future<String> result = executor.submit(RequestContext::get);

    // Worker thread có ThreadLocal riêng, không tự nhận req-101.
    assertNull(result.get());
}
finally {
    RequestContext.clear();
    executor.shutdown();
}
~~~

Test này chứng minh một ThreadLocal tùy chỉnh không tự truyền sang worker. Nó không kiểm tra Micrometer Context Propagation, vì `RequestContext` chưa có accessor/decorator.

### 11.3. Test khôi phục bằng scope

Khi dùng ContextSnapshot, test có thể kiểm tra giá trị được khôi phục trong scope và trạng thái trước đó được trả lại sau khi scope đóng:

~~~java
TenantContext.set("tenant-A");
ContextSnapshot snapshot = ContextSnapshotFactory.builder()
    .build()
    .captureAll();

TenantContext.set("tenant-B");
try (var scope = snapshot.setThreadLocals()) {
    assertEquals("tenant-A", TenantContext.get());
}
assertEquals("tenant-B", TenantContext.get());
TenantContext.clear();
~~~

Để test trên có ý nghĩa, `TenantContextAccessor` phải được đăng ký vào ContextRegistry dùng bởi factory. Trong kiểm thử production wiring, dùng cùng registry/bean mà ứng dụng thật sử dụng, không tạo registry độc lập rồi suy ra executor đã được cấu hình.

### 11.4. Ma trận kiểm chứng cho ứng dụng

| Kịch bản | Điều kiện | Bằng chứng đạt |
| --- | --- | --- |
| Đồng bộ cùng thread | Observation được mở trong request scope. | Log/trace đọc được context hiện tại. |
| Async qua executor có decorator | Accessor đã đăng ký, task chạy qua đúng executor. | Worker đọc được snapshot; trạng thái worker được khôi phục sau task. |
| Async qua executor không decorator | ThreadLocal tự tạo không được propagate. | Test cho thấy worker không nhận giá trị thread nguồn. |
| Reactor default/limited | Có Context Propagation và capture; code ở `handle`/`tap`. | ThreadLocal được restore trong vùng hỗ trợ. |
| Reactor automatic | `spring.reactor.context-propagation=auto`. | Context có thể được restore qua operator boundaries; kiểm tra cleanup và hiệu năng. |
| Hai subscription liên tiếp | Subscriber có context khác nhau dùng chung scheduler. | Không đọc nhầm tenant/trace từ subscription trước. |
| Listener sau commit | Listener được schedule trên executor thực tế. | Correlation theo trace/eventId theo chính sách; transaction riêng. |
| Retry sau restart | Event được phục hồi sau khi thread/trace cũ không còn. | eventId vẫn đối chiếu được; listener idempotent. |

## 12. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| TraceId có ở controller nhưng mất trong `@Async` | Task chạy trên thread khác, executor không propagate. | Kiểm tra đúng AsyncTaskExecutor và ContextPropagatingTaskDecorator/property. |
| Reactor `map` đọc ThreadLocal là null | Default/limited mode không restore ở operator đó. | Đọc Reactor Context trực tiếp hoặc cân nhắc automatic mode sau khi đo. |
| Reactor flow có tenant cũ | ThreadLocal không được clear/restore hoặc accessor xử lý thiếu key. | Kiểm tra `setValue()` không tham số, scope cleanup và subscription isolation. |
| Task thứ hai thấy context của task đầu | Thread pool tái sử dụng worker, ThreadLocal không được dọn. | Dùng decorator/scope, `remove()` trong finally, test cùng worker. |
| `InheritableThreadLocal` vẫn không có giá trị | Worker thread được tạo trước lúc set hoặc được tái sử dụng. | Không dùng cơ chế inheritance cho task pool; dùng snapshot/decorator. |
| Security principal mất trong async | SecurityContext có cơ chế riêng, chưa được propagate. | Dùng wrapper/executor phù hợp của Spring Security và kiểm tra quyền. |
| Transaction không còn ở worker | Transaction là thread-bound; propagation không copy JDBC resource. | Mở transaction mới trong worker, tải lại dữ liệu. |
| Listener có log nhưng không thấy trace | Tracer/sampler/exporter hoặc context propagation lỗi. | Tách kiểm tra listener execution khỏi telemetry pipeline. |
| Bật automatic Reactor làm chậm | Restore ThreadLocal ở nhiều operator tạo overhead. | Đo tải; chỉ propagate giá trị cần thiết hoặc dùng Context trực tiếp. |
| Dữ liệu context rò giữa tenant | Accessor không clear khi context thiếu key hoặc nguồn tenant không được xác thực. | Sửa accessor/lifecycle, kiểm soát đầu vào và thêm negative tests. |

## 13. Hiệu năng và bảo mật

**Mỗi lần capture/restore có chi phí.** Một snapshot có thể chứa nhiều accessor; càng nhiều context và boundary, công việc capture/restore càng tăng. Chỉ đăng ký những giá trị cần thiết và đo trên tải đại diện, đặc biệt với Reactor automatic mode.

**Giữ context nhỏ.** Không dùng ThreadLocal làm kho chứa request object, entity graph, stream, JDBC connection hoặc object lớn. Chỉ giữ ID hoặc giá trị ngắn có vòng đời rõ ràng.

**Không lạm dụng baggage.** Trace baggage có thể được truyền qua nhiều service và HTTP headers; không chứa access token, mật khẩu, email hoặc dữ liệu nhạy cảm. Chỉ cho phép các key cần thiết, giới hạn kích thước và cấu hình quyền truy cập backend.

**Không dùng ThreadLocal làm ranh giới bảo mật.** Giá trị tenant/user phải được xác thực ở tầng thích hợp; propagation chỉ mang giá trị đã có, không xác minh tính hợp lệ hay quyền của nó.

**Dọn context ở mọi nhánh.** Thành công, exception, cancellation và timeout đều cần giải phóng scope. Với Reactor, đảm bảo hook/context cleanup đúng khi subscription kết thúc hoặc bị hủy.

## 14. Checklist triển khai trong Spring Modulith

- [ ] Xác định dữ liệu nào thực sự cần đi qua boundary: observation/trace, MDC, tenant hoặc correlation ID.
- [ ] Dùng Reactor Context cho dữ liệu của reactive subscriber; tránh đọc ThreadLocal tùy tiện trong operator.
- [ ] Với ThreadLocal tự tạo, đăng ký `ThreadLocalAccessor` và kiểm tra thao tác clear.
- [ ] Với `@Async`, xác nhận đúng executor và cấu hình decorator/property theo Spring Boot version.
- [ ] Với `@ApplicationModuleListener`, xác nhận executor thật sự dùng để dispatch và transaction riêng của listener.
- [ ] Kiểm tra context không rò sang tác vụ tiếp theo trên worker thread được tái sử dụng.
- [ ] Ghi eventId trong log publisher/consumer để đối chiếu khi trace bị tách hoặc retry.
- [ ] Không cố truyền JDBC transaction, EntityManager hoặc security state nếu không có cơ chế chuyên biệt và nhu cầu rõ ràng.
- [ ] Đo overhead trước khi bật Reactor automatic mode trên production.
- [ ] Kiểm tra traces/logs/metrics riêng biệt; context propagation không thay thế exporter hoặc backend.

## 15. Tài liệu tham khảo chính thức

- **Java SE — ThreadLocal:** https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ThreadLocal.html — giá trị riêng theo thread, `get`, `set` và `remove`.
- **Micrometer Context Propagation — Purpose:** https://docs.micrometer.io/context-propagation/reference/purpose.html — ThreadLocalAccessor, ContextAccessor, ContextRegistry, ContextSnapshot và use cases.
- **Micrometer Context Propagation — Examples:** https://docs.micrometer.io/context-propagation/reference/usage.html — cách đăng ký accessor và capture/restore ThreadLocal.
- **Reactor — Context-Propagation Support:** https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html — limited/automatic mode, `contextCapture`, `handle`, `tap` và cleanup.
- **Reactor — Adding a Context to a Reactive Sequence:** https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html — Context gắn với subscriber và vấn đề thread switching.
- **Spring Boot 3.5 — Observability:** https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html — context propagation cho reactive operators và executor.
- **Spring Boot 4.2 — Observability:** https://docs.spring.io/spring-boot/reference/actuator/observability.html — `spring.task.execution.propagate-context`, Reactor mode và `ContextPropagatingTaskDecorator`.
- **Spring Framework 7 — Observability Support:** https://docs.spring.io/spring-framework/reference/integration/observability.html — Observation, tracing và tích hợp observability.

## 16. Tổng kết

`ThreadLocal` gắn một giá trị với **thread hiện tại**, không gắn với request hoặc tác vụ. Vì vậy, khi Spring Boot chuyển việc sang executor, khi Reactor đổi thread, hoặc khi Spring Modulith chạy listener sau commit, context không tự động xuất hiện ở nơi thực thi mới. Thread pool còn có thể tái sử dụng worker, khiến giá trị cũ tồn tại nếu không được xóa/khôi phục đúng cách.

Micrometer Context Propagation cung cấp **accessor, registry và snapshot** để chuyển giá trị giữa ThreadLocal, Reactor Context và các boundary async. Trong Spring Boot, dùng `ContextPropagatingTaskDecorator` hoặc property phù hợp cho executor; với Reactor, hiểu rõ khác biệt giữa **limited** và **automatic** mode. Luôn phân biệt trace context với transaction/security context, kiểm tra cleanup và dùng eventId để tương quan nghiệp vụ khi listener được retry hoặc trace bị tách. Đó là nền tảng để observability giữa các application module đáng tin cậy khi ứng dụng vận hành.
