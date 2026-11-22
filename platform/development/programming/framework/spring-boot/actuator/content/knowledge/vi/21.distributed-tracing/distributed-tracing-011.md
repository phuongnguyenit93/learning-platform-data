# Duy trì trace khi chuyển luồng hoặc đi qua chuỗi xử lý reactive

## 1. Trace thuộc lần xử lý, không thuộc tên luồng

Một yêu cầu đặt hàng có thể bắt đầu trên luồng HTTP, giao việc cho executor rồi tiếp tục trong một chuỗi Reactor. Nếu chỉ nhìn tên luồng, ta dễ tưởng ba phần việc này thuộc ba lần xử lý khác nhau.

Điều cần giữ là **ngữ cảnh truy vết (trace context)**:

- **Trace ID** xác định lần xử lý phân tán.
- **Span ID** xác định một thao tác trong lần xử lý đó.
- **Parent span ID** thể hiện thao tác cha khi tạo span con.
- **Scope** là phạm vi mà một observation hoặc span được coi là hiện hành.

Ví dụ thiết kế:

```text
HTTP nhận đơn: trace T, span A
    --> tác vụ kiểm tra kho: trace T, span B, parent A
    --> lời gọi thanh toán: trace T, span C, parent A
```

Đổi luồng không bắt buộc đổi Trace ID. Tạo span con có thể giữ cùng Trace ID nhưng phải có Span ID riêng. Ngược lại, chỉ truyền ngữ cảnh sang một tác vụ không tự tạo span mới để đo tác vụ đó.

Trong Spring Boot, **Micrometer Observation** quản lý vòng đời một thao tác quan sát; handler truy vết chuyển observation thành span. Khi observation được mở scope, span tương ứng trở thành span hiện hành. [Micrometer Tracing 1.3: cấu hình với Observation](https://docs.micrometer.io/tracing/reference/1.3/configuring.html)

Bài tập trung vào các ranh giới trong cùng tiến trình. Khi gọi dịch vụ khác, còn cần bộ tích hợp giao thức để chèn/trích xuất ngữ cảnh trên đường truyền.

## 2. Vì sao đang có trace lại bị mất khi chuyển luồng?

### 2.1. ThreadLocal không phải ngữ cảnh của toàn bộ yêu cầu

Trong mô hình xử lý tuần tự, thư viện thường dùng `ThreadLocal` để tìm ngữ cảnh hiện hành. Mỗi luồng có bản giá trị riêng; đặt giá trị trên luồng A không tự đặt giá trị trên luồng B. [Java 17: ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)

Hãy xét một executor có các luồng được tái sử dụng:

```text
luồng HTTP:
mở scope yêu cầu R1
    --> đưa Runnable vào hàng đợi

luồng trong pool:
lấy Runnable ra chạy
    --> nếu không khôi phục ngữ cảnh, không biết scope của R1
```

Có hai lỗi khác nhau:

1. **Mất ngữ cảnh:** tác vụ không có span hiện hành hoặc tạo nhầm một trace gốc mới.
2. **Rò ngữ cảnh:** tác vụ tiếp theo nhìn thấy dữ liệu còn sót lại của yêu cầu trước.

Vì vậy, một giải pháp đúng phải vừa **khôi phục trước khi chạy**, vừa **trả lại trạng thái trước đó sau khi chạy**, kể cả khi có lỗi.

Không dùng một biến `static Span current` để sửa lỗi: nhiều yêu cầu chạy đồng thời sẽ ghi đè nhau. Cũng không chỉ sao chép chuỗi Trace ID vào MDC; cách đó có thể làm log trông đúng nhưng không tạo ngữ cảnh để tracer xác định quan hệ span.

`InheritableThreadLocal` không thay thế việc truyền ngữ cảnh theo từng lần gửi tác vụ: pool thường đã tạo luồng trước yêu cầu và tiếp tục tái sử dụng chúng. Luồng ảo cũng không làm một executor bất kỳ tự hiểu hợp đồng ngữ cảnh của thư viện truy vết.

### 2.2. Ba thời điểm cần phân biệt

| Thời điểm | Việc xảy ra | Rủi ro khi lấy ngữ cảnh sai lúc |
| --- | --- | --- |
| Tạo đối tượng tác vụ hoặc lắp chuỗi Reactor | Mô tả công việc tương lai | Ngữ cảnh hiện tại chưa chắc thuộc lần chạy sau |
| Gửi tác vụ hoặc đăng ký thực thi (subscribe) | Một lần thực thi được thiết lập | Đây là ranh giới cần chọn đúng ngữ cảnh |
| Thực thi callback/operator | Công việc chạy trên luồng thực tế | Ngữ cảnh phải được mở đúng phạm vi tại đây |

Một snapshot tạo lúc khởi động ứng dụng không thể đại diện cho mọi yêu cầu sau đó. Tương tự, tạo một `Mono` khi còn scope rồi đăng ký thực thi ở nơi khác không có nghĩa scope đã được mang theo.

## 3. Chọn cách truyền theo ranh giới thực thi

| Ranh giới | Cơ chế phù hợp | Điều vẫn cần kiểm chứng |
| --- | --- | --- |
| `ExecutorService` tự quản lý | `ContextSnapshot` bọc tác vụ hoặc executor có hỗ trợ context | Chụp lúc còn đúng ngữ cảnh; đóng scope sau chạy |
| Executor của Spring/`@Async` | `ContextPropagatingTaskDecorator` | Đúng executor được dùng và đúng accessor được đăng ký |
| Chuỗi `Mono`/`Flux` | Reactor Context cùng cơ chế khôi phục ThreadLocal | Đúng subscription, đúng khóa và đúng vị trí `contextWrite` |
| Gọi HTTP sang dịch vụ khác | Client được tích hợp quan sát và truyền giao thức | Đúng ngữ cảnh ngay lúc gửi request |
| Callback từ thư viện ngoài | Bộ nối ngữ cảnh ngay tại ranh giới callback | Không giả định Reactor hook bao phủ callback tùy ý |

Một tác vụ có thể đi qua nhiều ranh giới. Cấu hình đúng executor chưa giải quyết callback ở một thư viện khác; bật Reactor tự động chưa biến `new Thread(...)` thành tác vụ được truyền ngữ cảnh.

## 4. Executor: chụp, khôi phục, chạy, trả lại

Micrometer Context Propagation dùng **ThreadLocalAccessor** để đọc/ghi một loại ngữ cảnh, **ContextRegistry** để quản lý accessor và **ContextSnapshot** để tạo bản chụp (snapshot) các giá trị đã đăng ký. Snapshot có thể mở lại các giá trị trong một scope rồi khôi phục trạng thái cũ khi scope đóng. [Micrometer Context Propagation 1.1: ví dụ](https://docs.micrometer.io/context-propagation/reference/1.1/usage.html)

Luồng thao tác cần giữ:

```text
bên gửi: chụp ngữ cảnh đang có hiệu lực
    --> gửi tác vụ được bọc
bên chạy: khôi phục ngữ cảnh
    --> chạy logic
    --> đóng scope và trả lại ngữ cảnh trước đó
```

Đoạn dưới minh họa một ranh giới executor. Nó giả định `factory` là `ContextSnapshotFactory` đã cấu hình accessor phù hợp, còn `executor` là `ExecutorService`; đây không phải chương trình độc lập:

```java
ContextSnapshot snapshot = factory.captureAll();

Future<Boolean> result = executor.submit(snapshot.wrap(() -> {
    Span current = tracer.currentSpan();
    return current != null;
}));
```

Cần các import `io.micrometer.context.ContextSnapshot`, `io.micrometer.tracing.Span` và `java.util.concurrent.Future`; `tracer` là Micrometer `Tracer` đã được cung cấp. Chương trình đầy đủ ở mục 8 kiểm tra chặt hơn việc chỉ khác `null`.

Chụp snapshot **trước khi rời ngữ cảnh bên gửi**. Chụp ngay bên trong một worker đã mất ngữ cảnh chỉ ghi lại trạng thái rỗng của worker.

### 4.1. Tiếp tục ngữ cảnh và tạo span con là hai thao tác

Sau khi khôi phục observation cha:

- Nếu chỉ cần giữ tương quan cho đoạn xử lý, có thể chạy trong ngữ cảnh đó.
- Nếu cần đo một thao tác riêng, tạo observation con bên trong tác vụ.
- Bên tạo observation/span chịu trách nhiệm kết thúc nó.
- Tác vụ không được kết thúc observation HTTP do framework sở hữu.

Một tác vụ có thể tiếp tục sau khi yêu cầu HTTP kết thúc. Việc giữ liên kết truy vết không đồng nghĩa giữ request, transaction hoặc tài nguyên HTTP còn sống. Với tác vụ nền có vòng đời độc lập, cần xác định quan hệ quan sát phù hợp thay vì kéo dài giả tạo scope của request.

### 4.2. CompletableFuture không tự giải quyết việc này

Các phương thức async không nhận executor thường dùng `ForkJoinPool.commonPool()`; callback không có hậu tố `Async` có thể chạy trên luồng hoàn tất future. Không gắn một chuỗi future với giả định “mọi bước dùng cùng luồng”. [Java 17: CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

Nếu đã có executor được trang bị truyền ngữ cảnh, hãy dùng nó có chủ đích. Với một callback được đăng ký dưới ngữ cảnh A nhưng chỉ được gửi vào executor khi một future hoàn tất dưới ngữ cảnh B, cần quyết định rõ ngữ cảnh nào phải được chụp. Decorator ở thời điểm gửi tác vụ không tự khôi phục A nếu A đã mất từ trước.

## 5. Spring Boot 3.3: cấu hình executor cho @Async

Các lớp dưới đây là **mã tích hợp vào ứng dụng Boot 3.3 hiện có**, không phải dự án khởi động độc lập. Ứng dụng cần Actuator, Micrometer Tracing với một bridge phù hợp và thư viện `io.micrometer:context-propagation`. Khi cần xuất span, cấu hình thêm bộ xuất và nơi nhận tương ứng; chỉ thêm context propagation không tự tạo hệ thống lưu truy vết.

`ContextPropagatingTaskDecorator` có từ Spring Framework 6.1, hỗ trợ khôi phục ngữ cảnh khi tác vụ chạy trên luồng khác và có chi phí bổ sung cho mỗi tác vụ. [Spring Framework 6.1: ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)

### 5.1. Executor có accessor Observation được khai báo tường minh

Lưu thành `TraceAsyncConfiguration.java`:

```java
package example.tracing;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class TraceAsyncConfiguration {
    @Bean("traceExecutor")
    public ThreadPoolTaskExecutor traceExecutor(ObservationRegistry registry) {
        ContextRegistry contexts = new ContextRegistry();
        contexts.registerThreadLocalAccessor(
                new ObservationThreadLocalAccessor(registry));

        ContextSnapshotFactory snapshots = ContextSnapshotFactory.builder()
                .contextRegistry(contexts)
                .clearMissing(true)
                .build();

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("trace-worker-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator(snapshots));
        return executor;
    }
}
```

Spring quản lý khởi tạo và đóng bean executor này. Không cần gọi `initialize()` thủ công trong phương thức bean.

Ví dụ dùng registry cục bộ để nêu rõ: nó truyền **Observation** gắn với `ObservationRegistry` được tiêm vào. `clearMissing(true)` yêu cầu dọn những giá trị accessor bị thiếu trong snapshot trong lúc khôi phục; đây không phải lệnh xóa mọi ThreadLocal của ứng dụng.

Nếu tự tạo span bằng `Tracer` ngoài vòng đời Observation, hoặc tự tạo baggage, phải cấu hình các accessor tương ứng. Micrometer Tracing có `ObservationAwareSpanThreadLocalAccessor` và `ObservationAwareBaggageThreadLocalAccessor` cho các trường hợp này. Đừng đăng ký trùng hoặc thay cấu hình toàn cục trong từng request. [Micrometer Tracing 1.3: Context Propagation](https://docs.micrometer.io/tracing/reference/1.3/configuring.html#_context_propagation_with_micrometer_tracing)

### 5.2. Phương thức bất đồng bộ chạy trên đúng executor

Lưu thành `AsyncStockWorker.java` trong cùng package:

```java
package example.tracing;

import java.util.concurrent.CompletableFuture;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncStockWorker {
    private final ObservationRegistry registry;
    private final Tracer tracer;

    public AsyncStockWorker(ObservationRegistry registry, Tracer tracer) {
        this.registry = registry;
        this.tracer = tracer;
    }

    @Async("traceExecutor")
    public CompletableFuture<String> inspectStock() {
        String traceId = Observation.createNotStarted("stock.inspect", registry)
                .observe(() -> {
                    Span current = tracer.currentSpan();
                    return current == null
                            ? "missing"
                            : current.context().traceId();
                });
        return CompletableFuture.completedFuture(traceId);
    }
}
```

Một bean khác gọi `inspectStock()` trong lúc observation cha đang có hiệu lực. Decorator mang observation cha sang worker; `observe(...)` tạo, mở scope và kết thúc observation của thao tác kiểm tra kho.

Lưu ý khi tích hợp:

- `@Async("traceExecutor")` phải khớp tên bean.
- Với cơ chế proxy thông thường, gọi `this.inspectStock()` ngay trong cùng đối tượng không đi qua proxy async.
- Không mở thêm `CompletableFuture.supplyAsync(...)` không có executor bên trong phương thức này, vì nó tạo một ranh giới khác.
- Nếu đầu vào không có observation cha, observation con có thể bắt đầu một trace mới; đừng xem Trace ID khác rỗng là bằng chứng giữ đúng trace.

Framework 6.1 hỗ trợ truyền ngữ cảnh cho xử lý async nhưng không tự tạo observation đo mọi phương thức `@Async`. [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes)

## 6. Reactive: ngữ cảnh thuộc subscription

### 6.1. Reactor Context khác ThreadLocal

Một chuỗi Reactor có thể đổi luồng nhiều lần. **Reactor Context** mang các cặp khóa–giá trị theo ngữ cảnh subscriber; nó không cần bám vào một luồng cố định. `Context` là bất biến: `put` trả về một Context mới. [Reactor 3.6: Context API](https://projectreactor.io/docs/core/3.6.6/api/reactor/util/context/Context.html)

Ví dụ độc lập về dữ liệu trong Context, giả định đã import `reactor.core.publisher.Mono`:

```java
Mono<String> label = Mono.deferContextual(context ->
        Mono.just(context.<String>get("request.label")))
        .contextWrite(context -> context.put("request.label", "checkout"));
```

Đây là đoạn khai báo có thể đặt trong một phương thức; chưa có terminal subscription nên nó chưa in hay trả kết quả cho người gọi. Chuỗi `request.label` chỉ là dữ liệu minh họa, không phải khóa kích hoạt tracer.

`contextWrite` làm giàu Context cho các operator **phía nguồn** của vị trí đó; `deferContextual` đọc ngữ cảnh khi đăng ký thực thi. Không nghĩ Context di chuyển giống hướng các phần tử dữ liệu. [Reactor 3.6: Mono API](https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Mono.html)

Đặt một khóa tùy ý tên `traceId` vào Context không tự thiết lập span hiện hành. Muốn nối với Micrometer phải dùng accessor và khóa ngữ cảnh mà cơ chế đó hiểu, ví dụ `ObservationThreadLocalAccessor.KEY` đối với Observation.

### 6.2. Bật khôi phục ThreadLocal trong Boot 3.3

```yaml
spring:
  reactor:
    context-propagation: auto
```

Boot 3.3 có thuộc tính này để bật tự động khôi phục các ThreadLocal liên quan trong chuỗi reactive. Mặc định không phải mọi operator đều có các giá trị ấy được khôi phục tự động. [Spring Boot 3.3: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html)

Tự cấu hình Reactor của Boot gọi `Hooks.enableAutomaticContextPropagation()` khi chế độ là `AUTO`. [Mã nguồn ReactorAutoConfiguration của Boot 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/reactor/ReactorAutoConfiguration.java)

Cần phân biệt:

- Context là nơi mang dữ liệu cho lần thực thi.
- Accessor nối dữ liệu đó với ngữ cảnh mà thư viện đọc trên luồng.
- Chế độ tự động giúp khôi phục dữ liệu đúng phạm vi operator.

Chỉ bật cấu hình không tạo ra observation chưa tồn tại, không biến mọi khóa thành tracing context và không sửa callback tùy ý bên ngoài Reactor.

Trong ứng dụng Boot, ưu tiên cấu hình khi khởi động. Không bật/tắt hook toàn cục theo từng request. Chương trình CLI ở mục 8 tự quản lý hook vì nó chạy trong JVM riêng.

### 6.3. contextCapture không có nghĩa là chụp lúc lắp chuỗi

`contextCapture()` lấy những ThreadLocal có accessor tại **thời điểm subscription** và đưa vào Context. Chế độ tự động áp dụng cho các subscription mới; nên bật từ lúc khởi động. Trong chế độ mặc định có giới hạn, hỗ trợ khôi phục tập trung ở các operator như `handle` và `tap`; không suy ra một `map` bất kỳ sẽ có ngữ cảnh ThreadLocal. [Reactor 3.6: Context-Propagation Support](https://projectreactor.io/docs/core/3.6.12/reference/index.html#context.propagation)

Ví dụ về sai thời điểm:

```text
mở scope A
    --> tạo Mono có contextCapture
đóng scope A
    --> chuyển Mono cho nơi khác subscribe
```

Khi subscription thực sự xảy ra, A có thể đã không còn là ngữ cảnh hiện hành. Việc có `contextCapture` trong chuỗi không sửa được nguồn ngữ cảnh đã mất.

Nếu đã có đối tượng Observation đúng cho lần thực thi, có thể đặt nó vào Context bằng khóa chuẩn như ví dụ đầy đủ ở mục 8. Với một publisher dùng lại nhiều lần, không lấy observation của request đầu rồi cố định nó cho tất cả subscription.

`publishOn` và `subscribeOn` thay đổi nơi một phần công việc được lên lịch; chúng không phải lệnh tạo hoặc chọn trace. Hãy kiểm tra ngữ cảnh tại operator thực sự chạy sau ranh giới đổi luồng.

## 7. Vòng đời span trong chuỗi reactive

Đừng dùng scope đồng bộ bao quanh thao tác chỉ **trả về** `Mono` rồi cho rằng scope ấy tồn tại đến lúc chuỗi hoàn tất. Scope sẽ đóng khi phương thức trả về, trong khi công việc có thể chưa bắt đầu.

Đối với một thao tác reactive cần observation riêng, có thể dùng tích hợp `reactor-core-micrometer` thay vì tự giữ scope qua nhiều luồng. Đoạn sau là minh họa tích hợp: `stockLookup` là một `Mono<String>` được cung cấp sẵn, `registry` là ObservationRegistry của ứng dụng.

```java
import reactor.core.observability.micrometer.Micrometer;

Mono<String> observedLookup = stockLookup
        .name("stock.lookup")
        .tap(Micrometer.observation(registry));
```

Import đặt ở đầu tệp; phần khai báo đặt trong phương thức. Dự án Boot cần thêm `io.projectreactor:reactor-core-micrometer` theo hệ quản lý phiên bản của nó. Observation ở đây có thể chuyển thành span khi registry có tracing handler. [Reactor: Observation qua Micrometer](https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/#_observation)

Khi chọn cách tự quản lý vòng đời thay cho tích hợp thư viện, phải xác định rõ:

- Mỗi subscription có observation riêng hay dùng observation do framework sở hữu?
- Khi hoàn tất, có lỗi hoặc bị hủy thì ai kết thúc observation?
- Khi retry tạo lần đăng ký lại, cần một observation cho cả chuỗi hay từng lần thử?
- Dữ liệu trong nhánh `flatMap` thuộc subscription nào?
- Context có bị lưu nhầm trong biến dùng chung, cache hoặc publisher phục vụ nhiều yêu cầu không?

Không kết thúc observation HTTP của framework từ `doFinally` của một chuỗi con. Nếu tự tạo observation, hãy kết thúc chính observation đó. Việc hủy cũng là một đường kết thúc cần được kiểm tra, không chỉ đường thành công.

## 8. Chương trình Java 17 chạy độc lập: kiểm tra trace thật

Chương trình sau dùng Micrometer Tracing với Brave, không dùng Spring Boot và không xuất dữ liệu qua mạng. Nó kiểm tra trực tiếp tracer hiện hành, quan hệ span cha–con và việc dọn ngữ cảnh.

Các phiên bản được ghim cho thí nghiệm tương thích thế hệ Boot 3.3; trong dự án Boot thật, dùng BOM của dự án thay vì chép đè toàn bộ phiên bản này.

### 8.1. Cấu trúc và build.gradle

Tạo một thư mục thử độc lập:

```text
trace-context-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/TraceContextDemo.java
```

Nội dung `settings.gradle`:

```groovy
rootProject.name = 'trace-context-demo'
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'io.micrometer:context-propagation:1.1.1'
    implementation 'io.micrometer:micrometer-observation:1.13.0'
    implementation 'io.micrometer:micrometer-tracing:1.3.0'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave:1.3.0'
    implementation 'io.zipkin.brave:brave:6.0.3'
    implementation 'io.projectreactor:reactor-core:3.6.6'
}

application {
    mainClass = 'TraceContextDemo'
}
```

Cần một bản Gradle chạy được với JVM đang dùng, có JDK 17 để chọn toolchain và có mạng tải phụ thuộc lần đầu. Tên tệp Java phải trùng tên public class.

### 8.2. Toàn bộ TraceContextDemo.java

```java
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.ThreadLocalCurrentTraceContext;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.brave.bridge.BraveBaggageManager;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import reactor.core.publisher.Hooks;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class TraceContextDemo {
    private static String traceId(Tracer tracer) {
        Span current = tracer.currentSpan();
        return current == null ? null : current.context().traceId();
    }

    public static void main(String[] args) throws Exception {
        ObservationRegistry registry = ObservationRegistry.create();
        ContextRegistry contexts = ContextRegistry.getInstance();
        contexts.registerThreadLocalAccessor(
                new ObservationThreadLocalAccessor(registry));
        Hooks.enableAutomaticContextPropagation();

        ExecutorService executor = Executors.newSingleThreadExecutor();
        Scheduler scheduler = Schedulers.newSingle("reactive-demo");

        try (Tracing brave = Tracing.newBuilder()
                .currentTraceContext(
                        ThreadLocalCurrentTraceContext.newBuilder().build())
                .sampler(Sampler.ALWAYS_SAMPLE)
                .addSpanHandler(new SpanHandler() {
                    @Override
                    public boolean end(TraceContext context, MutableSpan span,
                            Cause cause) {
                        return true;
                    }
                })
                .build()) {
            Tracer tracer = new BraveTracer(
                    brave.tracer(),
                    new BraveCurrentTraceContext(brave.currentTraceContext()),
                    new BraveBaggageManager());
            registry.observationConfig().observationHandler(
                    new DefaultTracingObservationHandler(tracer));

            Observation parent = Observation.start("checkout", registry);
            try (Observation.Scope scope = parent.openScope()) {
                String expectedTrace = traceId(tracer);
                String expectedParent = tracer.currentSpan().context().spanId();

                boolean rawMissing = executor.submit(
                        () -> tracer.currentSpan() == null).get();

                ContextSnapshot snapshot = ContextSnapshotFactory.builder()
                        .clearMissing(true)
                        .build()
                        .captureAll();

                boolean executorTrace = executor.submit(snapshot.wrap(
                        () -> expectedTrace.equals(traceId(tracer)))).get();

                boolean childLinked = executor.submit(snapshot.wrap(
                        () -> Observation.createNotStarted("worker.step", registry)
                                .observe(() -> {
                                    Span child = tracer.currentSpan();
                                    return child != null
                                            && expectedTrace.equals(
                                                    child.context().traceId())
                                            && expectedParent.equals(
                                                    child.context().parentId())
                                            && !expectedParent.equals(
                                                    child.context().spanId());
                                }))).get();

                boolean reactorTrace = Boolean.TRUE.equals(
                        Mono.delay(Duration.ofMillis(5), scheduler)
                                .map(value -> expectedTrace.equals(traceId(tracer)))
                                .contextWrite(context -> context.put(
                                        ObservationThreadLocalAccessor.KEY,
                                        parent))
                                .block());

                System.out.println("rawMissing=" + rawMissing);
                System.out.println("executorTrace=" + executorTrace);
                System.out.println("childLinked=" + childLinked);
                System.out.println("reactorTrace=" + reactorTrace);
                System.out.println("callerRestored=" + expectedParent.equals(
                        tracer.currentSpan().context().spanId()));
            } finally {
                parent.stop();
            }

            System.out.println("workerClean=" + executor.submit(
                    () -> tracer.currentSpan() == null).get());
            System.out.println("reactorClean=" + Mono.delay(
                    Duration.ofMillis(5), scheduler)
                    .map(value -> tracer.currentSpan() == null)
                    .block());
            System.out.println("callerClean=" + (tracer.currentSpan() == null));
        } finally {
            executor.shutdownNow();
            scheduler.dispose();
            Hooks.disableAutomaticContextPropagation();
            contexts.removeThreadLocalAccessor(ObservationThreadLocalAccessor.KEY);
        }
    }
}
```

`SpanHandler` trong ví dụ chỉ nhận sự kiện kết thúc mà không gửi ra hệ thống lưu. Vì vậy chương trình không yêu cầu Zipkin hay Collector.

### 8.3. Chạy và đọc kết quả

Tại thư mục thử:

```shell
gradle -q run
```

Stdout của chương trình:

```text
rawMissing=true
executorTrace=true
childLinked=true
reactorTrace=true
callerRestored=true
workerClean=true
reactorClean=true
callerClean=true
```

Các dòng có ý nghĩa khác nhau:

| Kết quả | Điều được kiểm chứng |
| --- | --- |
| `rawMissing=true` | Executor chưa bọc tác vụ không tự thấy span của bên gửi |
| `executorTrace=true` | Snapshot khôi phục đúng Trace ID trên worker |
| `childLinked=true` | Span con cùng Trace ID, khác Span ID và có đúng parent span ID |
| `reactorTrace=true` | Operator chạy trên scheduler khác vẫn thấy đúng trace |
| `callerRestored=true` | Sau tác vụ và chuỗi con, bên gọi vẫn ở span cha |
| `workerClean=true` | Cùng worker pool không còn span sau tác vụ đã bọc |
| `reactorClean=true` | Một subscription mới trên cùng scheduler không mang span cũ |
| `callerClean=true` | Luồng gọi không còn span sau khi scope cha đóng |

Chương trình không in Trace ID cụ thể vì nó thay đổi theo lần chạy. So sánh quan hệ giữa các ID cho kết quả ổn định và có ý nghĩa hơn việc mong một chuỗi ID cố định.

`block()` chỉ giúp chương trình CLI đợi kết quả và thoát có thứ tự. Không đưa cách chờ này vào luồng sự kiện WebFlux để sửa lỗi mất trace. Trong một endpoint reactive, trả publisher cho framework quản lý.

Chương trình đăng ký accessor và hook một lần rồi dọn khi kết thúc JVM thử nghiệm. Không chép phần gỡ accessor/tắt hook vào xử lý từng yêu cầu trong ứng dụng dùng chung.

## 9. Kiểm chứng trong ứng dụng thật

Ví dụ CLI kiểm tra các ranh giới trong JVM; chưa chứng minh đường HTTP, MDC, xử lý hủy hay mọi kiểu tích hợp của ứng dụng. Hãy bổ sung các bài kiểm tra theo tình huống thực tế:

| Tình huống | Điều cần quan sát |
| --- | --- |
| HTTP → @Async | Worker cùng Trace ID với request; span con có đúng parent |
| Reactor đổi scheduler | Trace ID tại operator sau đổi luồng vẫn đúng |
| Hai yêu cầu chạy xen kẽ | Trace của A không xuất hiện trong callback của B |
| Tác vụ ném ngoại lệ | Observation do tác vụ sở hữu kết thúc; worker không giữ ngữ cảnh |
| Subscription bị hủy | Tài nguyên quan sát của subscription được kết thúc đúng |
| Chuỗi retry | Số observation và quan hệ cha–con đúng thiết kế, không đóng sớm |
| Tác vụ không có trace đầu vào | Không kế thừa dữ liệu còn lại của yêu cầu trước |
| Gọi HTTP ra ngoài | Client dùng ngữ cảnh hiện hành tại thời điểm gửi để truyền sang dịch vụ nhận |
| Context có dữ liệu nhưng log thiếu ID | Kiểm tra accessor, scope và cấu hình log, không chỉ nhìn Context |
| Không thấy span tại nơi lưu | Kiểm tra lấy mẫu/bộ xuất riêng với kiểm tra ngữ cảnh trong JVM |

Với HTTP, dùng builder client do Boot cung cấp để giữ cơ chế tự động truyền truy vết. Tự tạo client ngoài cấu hình quan sát có thể làm đứt liên kết dù đoạn xử lý trước đó có span hiện hành. [Spring Boot 3.3: Propagating Traces](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.micrometer-tracing.propagating-traces)

MDC là một bằng chứng hỗ trợ cho log. Cần kiểm tra thêm `tracer.currentSpan()`, Trace ID, parent span ID và các span đã kết thúc. Chỉ thấy cùng một chuỗi trong log chưa chứng minh hệ thống truy vết có quan hệ đúng.

## 10. Lỗi thường gặp và cách khoanh vùng

| Biểu hiện | Nguyên nhân cần kiểm tra | Cách điều chỉnh |
| --- | --- | --- |
| @Async không đổi luồng | Gọi nội bộ cùng bean hoặc chưa qua proxy | Gọi qua bean được Spring quản lý; kiểm tra executor |
| Có Trace ID nhưng là trace mới | Tạo observation khi ngữ cảnh cha đã mất | Sửa ranh giới truyền trước khi tạo observation con |
| Snapshot vẫn rỗng | Chụp trong worker sau khi mất ngữ cảnh, hoặc thiếu accessor | Chụp bên gửi; kiểm tra loại ngữ cảnh đã đăng ký |
| Reactor Context có observation nhưng span hiện hành lúc có lúc không | Khôi phục ThreadLocal chưa áp dụng đúng phạm vi | Kiểm tra chế độ auto, subscription và cấu hình accessor |
| Mất trace ở một map sau đổi luồng | Đang ở chế độ giới hạn hoặc dữ liệu chưa vào Context | Kiểm tra cơ chế khôi phục và vị trí ghi Context |
| Log đúng nhưng span không liên kết | Chỉ sao chép MDC/Trace ID dạng chuỗi | Truyền ngữ cảnh tracer/Observation thực |
| Yêu cầu sau mang trace trước | Scope không đóng hoặc trạng thái dùng chung | Khôi phục theo scope; kiểm tra lại trên cùng worker |
| Trả Mono xong span đã kết thúc | Dùng vòng đời đồng bộ cho công việc deferred | Dùng tích hợp reactive hoặc quản lý theo subscription |
| Mất context tại callback bên ngoài | Callback không đi qua ranh giới đã trang bị | Bọc đúng callback hoặc executor thư viện sử dụng |

Khi điều tra, chọn một ranh giới nhỏ: ghi nhận ngữ cảnh ngay trước khi gửi và ngay trong callback đầu tiên nhận việc. Sau khi ranh giới đó đúng, kiểm tra ranh giới tiếp theo. Cách này giúp phân biệt lỗi mất nguồn ngữ cảnh với lỗi khôi phục hoặc lỗi xuất span.

## 11. Thực hành

1. Bỏ `snapshot.wrap(...)` ở một tác vụ của CLI và quan sát phép so sánh trace thất bại; giữ nguyên các tác vụ khác để đối chiếu.
2. Tắt chế độ tự động trước subscription thử nghiệm rồi kiểm tra operator `map` trên scheduler. Không suy kết quả của chương trình thử sang ứng dụng có cơ chế tích hợp khác mà chưa kiểm chứng.
3. Gửi hai yêu cầu độc lập vào một worker pool nhỏ; kiểm tra Trace ID riêng của từng yêu cầu và tác vụ kế tiếp không có đầu vào.
4. Tạo một trường hợp lỗi và một trường hợp hủy subscription; kiểm tra cả span kết thúc lẫn ngữ cảnh sau xử lý.
5. Nối thêm lời gọi HTTP ở cuối tác vụ rồi kiểm tra dịch vụ nhận. Phân biệt việc giữ ngữ cảnh trong JVM với việc truyền qua giao thức.

Sau bài này, hãy tự giải thích được ba câu: ngữ cảnh được lấy từ đâu, được khôi phục tại ranh giới nào, và ai chịu trách nhiệm đóng phạm vi quan sát. Ba câu đó phải có câu trả lời cụ thể cho từng đường thực thi.
