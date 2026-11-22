# Tích hợp truyền ngữ cảnh và giới hạn với MDC, thư viện ngoài

**Bối cảnh:** Spring Framework – Reactive, chương **Reactor Context**. Bài này giải thích cách truyền request ID, trace ID, tenant và metadata qua các operator Reactor; cách tích hợp với **SLF4J MDC** và thư viện imperative dựa vào ThreadLocal; cùng giới hạn của tự động truyền ngữ cảnh.

## 1. Bài toán: một request có thể chạy qua nhiều thread

Trong ứng dụng imperative truyền thống, một request thường được xử lý phần lớn trên một thread. Các logging framework như SLF4J MDC lưu thông tin chẩn đoán trong ThreadLocal, ví dụ requestId hoặc traceId. Khi ghi log, formatter đọc MDC của thread hiện tại để thêm các trường tương ứng.

Trong Reactor/WebFlux, một request không gắn cố định với một thread. Các bước có thể chạy trên Netty event-loop, thread khác sau publishOn/subscribeOn, scheduler của Reactor, virtual thread, executor do thư viện ngoài tự tạo hoặc callback bất đồng bộ sau khi thread ban đầu đã xử lý request khác.

Vì vậy, **MDC của thread hiện tại không phải nơi lưu trữ đáng tin cậy cho toàn bộ vòng đời reactive request**. Một giá trị có thể không xuất hiện ở thread mới; tệ hơn, giá trị còn sót của request trước có thể bị đọc nhầm khi thread được tái sử dụng.

Ví dụ lỗi thường thấy:

```java
MDC.put("requestId", requestId);

return service.load()
        .publishOn(Schedulers.parallel())
        .doOnNext(value -> log.info("loaded {}", value));
```

Đây là **đoạn minh họa lỗi**: MDC được đặt trên thread dựng controller, nhưng callback sau publishOn có thể chạy trên thread khác. Nếu không có cơ chế phục hồi context, log không có request ID như mong muốn. Cũng không nên chỉ gọi MDC.clear() ở cuối controller, vì controller có thể return publisher ngay lập tức trong khi các signal đến sau.

Giải pháp là phân biệt hai loại context:

1. **Reactor Context:** nguồn dữ liệu theo subscription, truyền qua pipeline reactive.
2. **ThreadLocal/MDC:** trạng thái tạm thời gắn với thread, chỉ nên được khôi phục trong phạm vi thực thi cần dùng.

Reactor Context là nơi phù hợp để giữ metadata của một luồng reactive. MDC và các ThreadLocal khác là **đích tương thích** khi phải gọi code cũ hoặc ghi log bằng thư viện vốn dựa vào thread hiện tại.

## 2. Reactor Context khác MDC như thế nào?

| Đặc điểm | Reactor Context | SLF4J MDC |
| --- | --- | --- |
| Phạm vi sở hữu | Gắn với subscriber/subscription | Gắn với thread hiện tại |
| Cách truyền | Theo subscription; context được truyền từ downstream về upstream khi subscribe | Không tự chuyển khi pipeline đổi thread |
| Kiểu dữ liệu | Map-like, immutable; thao tác ghi tạo Context mới | Map các chuỗi nằm trong ThreadLocal của logging backend |
| Nhiều request đồng thời | Mỗi subscription có context riêng | An toàn khi set/restore đúng trên từng thread; dễ rò khi quản lý sai |
| Thời điểm đọc | Qua deferContextual, transformDeferredContextual, Signal.getContextView | Qua MDC.get trong scope đã khôi phục |
| Vai trò | Lưu request/trace/tenant metadata trong reactive flow | Tương thích log formatter và code imperative hiện hữu |

Một Reactor Context không phải bản sao toàn bộ MDC. Nó chỉ chứa key/value đã được đưa vào context, chẳng hạn:

```java
.contextWrite(context -> context.put("requestId", "req-42"))
```

Các operator phía **trên** vị trí contextWrite có thể đọc key đó. Context được truyền từ downstream về upstream trong quá trình subscribe, vì vậy vị trí đặt contextWrite có ý nghĩa. Operator phía dưới nó không tự nhìn thấy bản context mới theo cách mà operator phía trên nhìn thấy.

Có thể đọc giá trị mà không cần ThreadLocal:

```java
Mono<String> requestId = Mono.deferContextual(context ->
        Mono.just(context.get("requestId")));
```

Đây là cách ưu tiên khi code của bạn kiểm soát được: truyền context tường minh thay vì gọi MDC.get trong mọi business method.

### 2.1. Context là dữ liệu theo subscription, không phải biến toàn cục

Reactor Context được thiết kế để mỗi subscriber có thể mang một giá trị riêng. Hai request cùng chạy trên một event-loop không vì thế mà dùng chung request ID. Không nên đặt request metadata vào biến static mutable, singleton holder hoặc ThreadLocal toàn cục rồi kỳ vọng Reactor tự phân biệt request.

Các object được lưu trong Context vẫn có thể mutable. Bản thân Context immutable không làm object bên trong tự thread-safe. Ưu tiên value object bất biến, chuỗi hoặc metadata có contract rõ ràng; không lưu map mutable dùng chung rồi cập nhật từ nhiều nhánh song song.

## 3. Metadata nào nên truyền?

Một pipeline có thể mang:

- **Correlation/request ID:** nối các log thuộc cùng request hoặc thao tác xuyên nhiều tầng.
- **Trace/span context:** liên kết span cha/con, trace ID và thông tin tracing theo chuẩn instrumentation.
- **Tenant ID:** định tuyến tới tenant hoặc chọn cấu hình phù hợp, nhưng phải được xác thực ở biên tin cậy.
- **Locale hoặc timezone:** phục vụ format dữ liệu và thông báo.
- **Security context/principal:** danh tính và quyền hạn theo cơ chế bảo mật được hỗ trợ.
- **Thông tin quan sát:** observation hiện tại, baggage hoặc metadata cho metrics/traces.

Không dùng context để mang payload nghiệp vụ lớn, dữ liệu binary, toàn bộ request body, token bí mật, password hoặc object mutable phức tạp. Context không phải cache hay nơi thay thế parameter của hàm. Dữ liệu cần thiết để tính kết quả nên được truyền bằng kiểu đầu vào/đầu ra rõ ràng.

**Giới hạn về cardinality và bảo mật:** request ID/trace ID thường có độ đa dạng cao, phù hợp log hoặc trace nhưng không phù hợp làm metric tag có cardinality không giới hạn. Không ghi access token, session secret hoặc dữ liệu cá nhân nhạy cảm vào MDC/log.

## 4. Tích hợp Reactor Context với MDC bằng doOnEach

Cách minh bạch và có kiểm soát là đọc dữ liệu từ Reactor Context **ngay tại điểm ghi log**, đặt tạm vào MDC, thực hiện log, rồi khôi phục trạng thái ngay sau callback.

SLF4J 2 cung cấp MDC.putCloseable(key, value). Đối tượng trả về dùng được với try-with-resources; khi đóng, giá trị tạm được gỡ khỏi MDC. Điều này tránh để request ID của request A tồn tại trên worker rồi bị request B sử dụng nhầm.

### 4.1. Helper ghi log cho tín hiệu onNext

```java
import java.util.Optional;
import java.util.function.Consumer;

import org.slf4j.MDC;
import reactor.core.publisher.Signal;

public final class ReactorMdc {
    private ReactorMdc() {}

    public static <T> Consumer<Signal<T>> logOnNext(
            Consumer<T> logStatement) {

        return signal -> {
            if (!signal.isOnNext()) {
                return;
            }

            Optional<String> requestId =
                    signal.getContextView().getOrEmpty("requestId");

            if (requestId.isPresent()) {
                try (MDC.MDCCloseable ignored =
                             MDC.putCloseable("requestId", requestId.get())) {
                    logStatement.accept(signal.get());
                }
            } else {
                logStatement.accept(signal.get());
            }
        };
    }
}
```

Cách dùng trong một pipeline:

```java
return service.load()
        .doOnEach(ReactorMdc.logOnNext(value ->
                log.info("loaded {}", value)))
        .contextWrite(context ->
                context.put("requestId", requestId));
```

Đây là **helper và cách dùng minh họa**, cần service, log và requestId do ứng dụng định nghĩa. Điểm cần nhớ:

1. doOnEach nhận một Signal, không chỉ giá trị. Signal chứa ContextView tương ứng với subscription.
2. Chỉ xử lý onNext trong helper này; nếu cần log error, viết helper riêng kiểm tra isOnError và đọc getThrowable.
3. Nếu key có giá trị, helper đặt nó vào MDC đúng trong callback ghi log. Sau đó try-with-resources đóng scope.
4. Nếu key không tồn tại, helper vẫn log bình thường mà không tự tạo request ID giả.
5. contextWrite đặt ở cuối chain để operator doOnEach phía trên đọc được key.

Không viết MDC.put rồi để đó trong callback. Với thread pool dùng chung, mỗi callback phải khôi phục hoặc xóa trạng thái tạm sau khi hoàn tất.

### 4.2. Chương trình Java 17+ chạy độc lập với output xác định

Ví dụ sau dùng scheduler để chứng minh callback có thể chạy ở thread khác, nhưng output không in tên thread nên kết quả không phụ thuộc worker nào được chọn.

Tệp src/main/java/demo/ReactorMdcDemo.java:

```java
package demo;

import java.time.Duration;
import java.util.Optional;
import java.util.function.Consumer;

import org.slf4j.MDC;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Signal;
import reactor.core.scheduler.Schedulers;
import reactor.util.context.Context;

public final class ReactorMdcDemo {

    private static <T> Consumer<Signal<T>> logOnNext(
            Consumer<T> logStatement) {

        return signal -> {
            if (!signal.isOnNext()) {
                return;
            }

            Optional<String> requestId =
                    signal.getContextView().getOrEmpty("requestId");

            if (requestId.isPresent()) {
                try (MDC.MDCCloseable ignored =
                             MDC.putCloseable("requestId", requestId.get())) {
                    logStatement.accept(signal.get());
                }
            } else {
                logStatement.accept(signal.get());
            }
        };
    }

    public static void main(String[] args) {
        Flux.just("created", "updated")
                .publishOn(Schedulers.parallel())
                .doOnEach(logOnNext(value ->
                        System.out.println(
                                "requestId=" + MDC.get("requestId")
                                        + ", event=" + value)))
                .contextWrite(Context.of("requestId", "req-42"))
                .blockLast(Duration.ofSeconds(5));
    }
}
```

**Dependency:** Java 17+, reactor-core, slf4j-api 2.x và một logging backend có hỗ trợ MDC, ví dụ Logback tương thích SLF4J 2. Trong dự án Spring Boot đã có spring-boot-starter-webflux và logging starter phù hợp, thường không cần tự chọn phiên bản các dependency này; hãy để BOM quản lý. Nếu chạy độc lập, cần các JAR tương thích trong classpath.

Lệnh chạy thủ công (đặt JAR cần thiết trong thư mục lib):

```bash
# Linux/macOS
mkdir -p out
javac -cp "lib/*" -d out src/main/java/demo/ReactorMdcDemo.java
java -cp "out:lib/*" demo.ReactorMdcDemo
```

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force out
javac -cp "lib/*" -d out src/main/java/demo/ReactorMdcDemo.java
java -cp "out;lib/*" demo.ReactorMdcDemo
```

**Stdout chính xác:**

```text
requestId=req-42, event=created
requestId=req-42, event=updated
```

Nguồn đồng bộ phát hai phần tử theo thứ tự; publishOn chuyển việc xử lý downstream sang scheduler. doOnEach lấy request ID từ Reactor Context, đặt vào MDC chỉ trong lúc in log. MDC.get trả lại giá trị mong muốn trong callback. Khi callback kết thúc, scope được đóng, không để lại request ID trên worker.

**Phạm vi của ví dụ:** helper trên chỉ phục vụ log trong callback doOnEach. Nó không làm cho mọi lời gọi thư viện bên ngoài tự động nhìn thấy MDC, cũng không tự truyền request ID qua HTTP tới service khác.

### 4.3. Log error cũng cần khôi phục MDC

Nếu muốn log error với cùng request ID, dùng một helper riêng:

```java
public static Consumer<Signal<?>> logOnError(
        Consumer<Throwable> logStatement) {

    return signal -> {
        if (!signal.isOnError()) {
            return;
        }

        Optional<String> requestId =
                signal.getContextView().getOrEmpty("requestId");

        if (requestId.isPresent()) {
            try (MDC.MDCCloseable ignored =
                         MDC.putCloseable("requestId", requestId.get())) {
                logStatement.accept(signal.getThrowable());
            }
        } else {
            logStatement.accept(signal.getThrowable());
        }
    };
}
```

Cách gắn vào pipeline:

```java
return service.load()
        .doOnEach(ReactorMdc.logOnNext(
                value -> log.info("loaded {}", value)))
        .doOnEach(ReactorMdc.logOnError(
                error -> log.error("load failed", error)))
        .contextWrite(context ->
                context.put("requestId", requestId));
```

Đây là **mã minh họa**, không phải class độc lập. Nếu log terminal signal, nhớ rằng doOnEach có thể nhận nhiều loại signal; helper cần kiểm tra đúng loại trước khi đọc giá trị hoặc throwable.

## 5. Ghi và đọc Context đúng cách

### 5.1. Dùng contextWrite khi đã có metadata

Nếu request ID đã được xác định ở controller hoặc tầng nhận request, hãy ghi trực tiếp:

```java
return service.findOrders()
        .map(this::toDto)
        .contextWrite(context -> context
                .put("requestId", requestId)
                .put("tenantId", tenantId));
```

Đây là mã minh họa với service, toDto, requestId và tenantId do ứng dụng định nghĩa. Vì Reactor Context immutable, mỗi lần put tạo một Context mới. Có thể nối nhiều lần contextWrite; thứ tự merge/ghi đè cần được hiểu rõ để tránh ghi nhầm giá trị cùng key.

Dùng key có namespace hoặc hằng số thay vì chuỗi rải rác:

```java
static final String REQUEST_ID = "app.requestId";
static final String TENANT_ID = "app.tenantId";
```

Tránh hai thư viện tự chọn cùng key nhưng hiểu ý nghĩa khác nhau.

### 5.2. Dùng deferContextual để đọc Context

deferContextual tạo publisher dựa trên Context có tại subscription:

```java
Mono<OrderResult> result = Mono.deferContextual(context -> {
    String requestId = context.get("app.requestId");
    String tenantId = context.get("app.tenantId");

    return orderService.find(tenantId)
            .map(order -> new OrderResult(requestId, order));
});
```

Đây là **mã minh họa** với các kiểu nghiệp vụ do ứng dụng định nghĩa. Nếu key có thể không tồn tại, dùng hasKey hoặc getOrDefault thay vì gọi get trực tiếp và nhận exception khi thiếu key.

Không cần chuyển Reactor Context sang MDC chỉ để đọc một giá trị trong business logic. Nếu bạn sở hữu code, đọc trực tiếp từ ContextView hoặc truyền value vào method.

### 5.3. contextWrite và contextCapture khác nhau

| Operator | Mục đích | Nguồn giá trị |
| --- | --- | --- |
| contextWrite | Ghi/merge giá trị vào Reactor Context | Giá trị bạn cung cấp trực tiếp |
| contextCapture | Chụp các ThreadLocal đã đăng ký tại thời điểm subscribe rồi đưa vào Reactor Context | Context Propagation registry và ThreadLocal hiện tại |
| deferContextual | Đọc Reactor Context tại subscription | Reactor Context của subscriber |
| transformDeferredContextual | Biến đổi publisher dựa trên Context | ContextView và publisher hiện tại |

Ví dụ imperative code đã đặt MDC trước khi khởi chạy Reactor:

```java
MDC.put("requestId", "req-42");

try {
    return service.load()
            .contextCapture();
} finally {
    MDC.remove("requestId");
}
```

Đây chỉ là **mã minh họa** và chỉ đúng khi requestId được một ThreadLocalAccessor đăng ký với Context Propagation. contextCapture chụp ThreadLocal tại **thời điểm subscription**, không phải lúc assembly. Vì vậy nếu publisher được subscribe sau khi finally đã xóa MDC, context có thể không còn request ID để chụp.

Ở một controller WebFlux, request đã ở trong reactive lifecycle và framework có thể đưa observation/security metadata vào Reactor Context. Với dữ liệu tùy chỉnh, thường rõ ràng hơn khi ghi trực tiếp bằng contextWrite. Không thêm contextCapture theo thói quen nếu bạn chưa xác định giá trị nào đang ở ThreadLocal và subscription xảy ra khi nào.

## 6. Micrometer Context Propagation: cầu nối giữa Context và ThreadLocal

Project Reactor tích hợp với SPI của io.micrometer:context-propagation từ Reactor Core 3.5.0. Thư viện này cung cấp các abstraction:

- **ThreadLocalAccessor:** đọc, đặt và xóa giá trị của một ThreadLocal cụ thể.
- **ContextAccessor:** cho phép đọc/ghi một dạng context map-like.
- **ContextRegistry:** đăng ký các accessor được dùng để kết nối những dạng context khác nhau.
- **ContextSnapshot:** chụp các giá trị ngữ cảnh và khôi phục ThreadLocal trong một scope.
- **ContextSnapshotFactory:** tạo snapshot từ ThreadLocal hiện tại hoặc từ context được cung cấp.

Reactor có thể hiểu Context/ContextView thông qua ReactorContextAccessor được tải bằng ServiceLoader. Khi có cả reactor-core và context-propagation trên classpath, không cần tự viết accessor cho Reactor Context.

Micrometer Context Propagation không thay thế Reactor Context hoặc ThreadLocal. Nó **hỗ trợ đi qua ranh giới** giữa chúng: code imperative có thể tiếp tục dùng ThreadLocal; code Reactor nên dùng Reactor Context; khi cần gọi một thành phần imperative, thư viện có thể khôi phục ThreadLocal trong đúng scope.

### 6.1. Hai chế độ: limited và automatic

| Chế độ | Hành vi | Khi nào cân nhắc |
| --- | --- | --- |
| **Default / limited** | Chỉ những operator được chọn như handle và tap khôi phục ThreadLocal trong phạm vi callback khi có Context Propagation và context snapshot phù hợp | Khi muốn hạn chế overhead và kiểm soát điểm bridge |
| **Automatic** | Các operator Reactor khôi phục ThreadLocal qua ranh giới thread dựa trên Reactor Context và các accessor đã đăng ký | Khi ứng dụng cần tương thích rộng với thư viện imperative và chấp nhận chi phí tương ứng |

Các mốc phiên bản quan trọng:

- **Reactor Core 3.5.0:** tích hợp SPI Context Propagation; có limited mode, contextCapture và các thay đổi hỗ trợ khôi phục ThreadLocal trong một số operator.
- **Reactor Core 3.5.3:** bổ sung Hooks.enableAutomaticContextPropagation để bật automatic mode.
- Tài liệu Micrometer cho ví dụ Reactor 3.5.3+ nêu bộ phiên bản tối thiểu tương ứng gồm Reactor 3.5.3, Context Propagation 1.0.3, Micrometer 1.10.8 và Micrometer Tracing 1.0.7. Đây là **mốc tham chiếu của ví dụ tài liệu**, không phải bộ version bắt buộc cho mọi ứng dụng hiện nay.
- **Spring Boot 3.2+:** có property spring.reactor.context-propagation với các chế độ limited và auto. Mặc định là limited trong các tài liệu Boot 3.2.x; hãy kiểm tra đúng BOM/phiên bản của ứng dụng.

Không trộn version thủ công nếu đang dùng Spring Boot BOM. Kiểm tra dependency runtime để bảo đảm Reactor, Micrometer, Micrometer Tracing và Context Propagation tương thích với nhau.

### 6.2. Bật automatic mode trực tiếp trong Reactor

Nếu không dùng Spring Boot để cấu hình, có thể bật hook lúc khởi động ứng dụng:

```java
import reactor.core.publisher.Hooks;

public final class Application {
    public static void main(String[] args) {
        Hooks.enableAutomaticContextPropagation();

        // Khởi tạo và chạy ứng dụng sau khi bật hook.
    }
}
```

Đây là **mẫu khởi động**, phần chạy ứng dụng được lược bỏ. Hook là cấu hình toàn cục cho shared Reactor runtime và **chỉ áp dụng cho các subscription mới**. Vì vậy phải bật trước khi tạo subscription cần được truyền context; cách an toàn là bật trong giai đoạn khởi động, không bật muộn sau khi request đã chạy.

Hook không tự tạo request ID hoặc trace ID. Nó chỉ khôi phục các ThreadLocal có accessor tương ứng từ giá trị có trong Reactor Context. Nếu Context không có key, không có giá trị để khôi phục.

### 6.3. Bật automatic mode trong Spring Boot

Trong src/main/resources/application.properties:

```properties
spring.reactor.context-propagation=auto
```

Hoặc YAML:

```yaml
spring:
  reactor:
    context-propagation: auto
```

Spring Boot cấu hình Reactor theo property này khi ứng dụng khởi động. Nếu dùng Boot, ưu tiên một nơi cấu hình rõ ràng và tránh tự gọi hook trùng lặp ở nhiều thư viện hoặc static initializer.

Ở chế độ mặc định limited, các operator handle và tap có hỗ trợ khôi phục ThreadLocal trong callback khi Context Propagation có mặt và Context đã được capture/ghi đúng. Không mặc định rằng doOnNext, map hoặc mọi callback bất kỳ sẽ nhìn thấy MDC trong limited mode. Nếu cần log trong doOnEach, helper thủ công ở mục 4 là một cách minh bạch.

Đối với @Async và executor do Spring Boot tự cấu hình, đó là một đường truyền context khác với Reactor. Boot có property riêng spring.task.execution.propagate-context; executor tự cấu hình cần được gắn ContextPropagatingTaskDecorator. Bật Reactor auto mode không tự cấu hình mọi ExecutorService bên ngoài.

## 7. Đăng ký accessor cho MDC hoặc thư viện ngoài

### 7.1. Dùng Slf4jThreadLocalAccessor cho một số key MDC

Micrometer Context Propagation có Slf4jThreadLocalAccessor để truyền nội dung MDC qua ranh giới thread. Accessor có thể sao chép toàn bộ MDC hoặc chỉ một số key cụ thể. Ví dụ đăng ký một key:

```java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.integration.Slf4jThreadLocalAccessor;

ContextRegistry.getInstance()
        .registerThreadLocalAccessor(
                new Slf4jThreadLocalAccessor("requestId"));
```

Accessor này có từ Context Propagation 1.1.1. Khi dùng các key chọn lọc, Reactor Context chứa giá trị theo key nội bộ của accessor (hằng số Slf4jThreadLocalAccessor.KEY); accessor quản lý map MDC cho các key đã đăng ký. Nếu bạn tự ghi Context trực tiếp, phải tuân theo contract key/value của accessor, không giả định rằng context.put("requestId", ...) tự động trở thành MDC.

**Không đăng ký nhiều accessor cùng thao tác lên cùng một MDC một cách tùy tiện.** Javadoc của Slf4jThreadLocalAccessor khuyến nghị chỉ dùng khi không có accessor khác đồng thời quản lý MDC hoặc những key liên quan, ví dụ instrumentation tracing. Trong ứng dụng Spring Boot/Micrometer Tracing, hãy kiểm tra accessor đã được framework hoặc tracing bridge quản lý trước khi tự thêm accessor khác; nếu hai accessor ghi/xóa cùng key, giá trị có thể bị ghi đè hoặc biến mất ngoài dự kiến.

Nếu chỉ cần log trong một callback, helper doOnEach thủ công thường dễ hiểu và ít ảnh hưởng toàn cục hơn. Dùng automatic MDC accessor khi thật sự cần code imperative cũ đọc MDC ở nhiều điểm qua thread boundary.

### 7.2. Tạo accessor cho ThreadLocal riêng của thư viện legacy

Giả sử thư viện cũ đọc tenant từ một ThreadLocal mà ứng dụng có thể truy cập qua một wrapper:

```java
public final class LegacyTenantContext {
    private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    private LegacyTenantContext() {}

    public static String get() {
        return TENANT.get();
    }

    public static void set(String tenantId) {
        TENANT.set(tenantId);
    }

    public static void clear() {
        TENANT.remove();
    }
}
```

Accessor nối ThreadLocal đó với Reactor Context:

```java
import io.micrometer.context.ThreadLocalAccessor;

public final class TenantIdAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "app.tenantId";

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return LegacyTenantContext.get();
    }

    @Override
    public void setValue(String value) {
        LegacyTenantContext.set(value);
    }

    @Override
    public void setValue() {
        LegacyTenantContext.clear();
    }
}
```

Đăng ký đúng một lần khi ứng dụng khởi động:

```java
ContextRegistry.getInstance()
        .registerThreadLocalAccessor(new TenantIdAccessor());

Hooks.enableAutomaticContextPropagation();
```

Nếu ứng dụng dùng Spring Boot với spring.reactor.context-propagation=auto, để Boot bật automatic mode; không cần tự gọi hook thêm lần nữa. Accessor vẫn phải được đăng ký và key trong Reactor Context phải đúng.

Một service gọi thư viện blocking có thể viết:

```java
public Mono<Customer> findCustomer(String tenantId, String customerId) {
    return Mono.fromCallable(() ->
                    legacyClient.findCustomer(
                            LegacyTenantContext.get(), customerId))
            .subscribeOn(Schedulers.boundedElastic())
            .contextWrite(context ->
                    context.put(TenantIdAccessor.KEY, tenantId));
}
```

Đây là **mẫu service**, giả định legacyClient.findCustomer là lời gọi blocking trả về Customer. Khi subscription chạy trên boundedElastic, automatic propagation khôi phục tenant ThreadLocal trong callback của publisher dựa trên Context của subscription.

Điều kiện để cách này hoạt động:

1. Accessor được đăng ký trong registry dùng bởi Context Propagation.
2. Key trong contextWrite trùng với TenantIdAccessor.KEY.
3. Automatic mode được bật trước khi subscription chạy, hoặc callback nằm trong một operator có hỗ trợ khôi phục ở limited mode.
4. Lời gọi legacy thực sự chạy trong scope đã được khôi phục, không được tự tách sang executor không được instrument.
5. setValue không tham số phải xóa ThreadLocal. Nếu bỏ bước này, giá trị tenant của request trước có thể rò sang tác vụ sau trên cùng worker.

**Không truyền tenant chỉ vì nó đang có trong ThreadLocal ở thread controller.** Hãy đưa tenant đã xác thực vào Reactor Context, rồi để accessor tạo cầu nối có kiểm soát.

## 8. Khi thư viện ngoài tự tạo ExecutorService

Automatic propagation của Reactor chỉ kiểm soát các ranh giới mà Reactor hoặc integration đã instrument. Một thư viện có thể tự tạo ExecutorService, thread pool hoặc callback riêng. Khi code được chạy ở thread đó, Reactor không mặc nhiên biết phải capture/restore Context.

Micrometer Context Propagation có thể wrap executor để khôi phục snapshot cho mỗi task. Ví dụ ở mức khái niệm:

```java
ContextSnapshotFactory snapshotFactory =
        ContextSnapshotFactory.builder().build();

Mono<Result> result = Mono.deferContextual(contextView -> {
    ContextSnapshot snapshot =
            snapshotFactory.captureFrom(contextView);

    Executor contextAwareExecutor =
            snapshot.wrapExecutor(legacyExecutor);

    return Mono.fromFuture(
            CompletableFuture.supplyAsync(
                    legacyClient::call,
                    contextAwareExecutor));
});
```

Đây là **mã minh họa tích hợp**, cần khai báo legacyExecutor, legacyClient và kiểu Result; executor phải được quản lý lifecycle riêng. ContextSnapshotFactory capture giá trị từ Reactor Context, wrapExecutor bọc tác vụ để đặt ThreadLocal trong lúc thực thi rồi khôi phục trạng thái trước đó khi task kết thúc.

Một cách khác là lấy snapshot rồi dùng snapshot.setThreadLocals trong try-with-resources quanh một đoạn imperative đồng bộ:

```java
try (ContextSnapshot.Scope ignored =
             snapshot.setThreadLocals()) {
    legacyLibrary.doWork();
}
```

**Không mở scope trên một thread rồi đóng scope trên thread khác.** Scope cần được đóng ở nơi nó được mở để khôi phục đúng trạng thái ThreadLocal trước đó. Không lưu một snapshot vào biến static rồi dùng chung cho các request; mỗi subscription/task phải mang snapshot của chính nó.

Nếu thư viện ngoài có API callback riêng, hãy kiểm tra nó có hỗ trợ decorator, context carrier hoặc interceptor hay không. Ưu tiên integration chính thức của thư viện; chỉ tự wrap executor khi đã hiểu rõ lifecycle, cancellation, exception và shutdown.

## 9. Context Propagation không tự truyền qua mạng

Reactor Context và ThreadLocal đều thuộc phạm vi trong một JVM. Chúng không tự trở thành HTTP header, message header hay baggage gửi qua service khác.

Ví dụ, contextWrite(Context.of("requestId", "req-42")) không tự khiến request HTTP do WebClient gửi đi có header X-Request-Id. Muốn truyền qua mạng, cần cơ chế rõ ràng:

- Dùng Micrometer Tracing/Observation và propagation format tương thích (thường W3C Trace Context) để chuyển trace/span qua HTTP.
- Nếu nghiệp vụ cần correlation ID riêng, đọc từ Reactor Context rồi thêm header ở WebClient filter hoặc API client adapter.
- Với Kafka/RabbitMQ, đặt metadata vào message header và đọc/khôi phục ở consumer boundary.
- Xác thực/kiểm tra giá trị nhận từ bên ngoài; không coi header request ID hoặc tenant do client gửi là bằng chứng danh tính/quyền hạn.

Một ví dụ WebClient filter minh họa cách đọc Reactor Context để thêm correlation header:

```java
ExchangeFilterFunction requestIdFilter = (request, next) ->
        Mono.deferContextual(context -> {
            String requestId = context.getOrDefault(
                    "app.requestId", "unknown");

            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Request-Id", requestId)
                    .build();

            return next.exchange(updated);
        });
```

Đây là **đoạn cấu hình minh họa**, cần đặt trong cấu hình WebClient phù hợp. Trong hệ thống có Micrometer Tracing, ưu tiên propagation instrumentation đã có để tránh tự thêm header trace sai chuẩn hoặc tạo trace ID không liên kết với span.

## 10. MDC, Observation và Tracing không phải một thứ

Ba khái niệm liên quan nhưng khác nhau:

- **MDC:** các trường key/value phục vụ logging, thường lấy từ ThreadLocal.
- **Micrometer Observation:** mô tả một thao tác có thể tạo metrics và traces thông qua registry/handler.
- **Micrometer Tracing:** quản lý trace/span và truyền trace context giữa các process.

Một trace ID trong log có thể đến từ observation/tracing integration. Không nên tự tạo một traceId tùy ý trong MDC rồi nghĩ rằng đã tạo một distributed trace hợp lệ. Distributed tracing còn có parent/child span, trace ID, sampling, baggage, propagation header và lifecycle.

Spring Boot Actuator/Observability sử dụng Micrometer Observation và Context Propagation để chuyển observation qua thread/reactive pipeline. Khi có instrumentation tương thích, log formatter có thể hiển thị trace/span ID mà không cần viết thủ công một MDC bridge cho từng log. Tuy vậy, **request ID tùy chỉnh hoặc metadata ứng dụng** vẫn cần được đưa vào Context và được bridge rõ ràng nếu thư viện yêu cầu ThreadLocal.

Tránh ghi đè các key do tracing framework quản lý. Nếu muốn thêm tenantId hoặc requestId, dùng key riêng và bảo đảm nó không xung đột với các accessor hiện có.

## 11. Giới hạn và chi phí khi bật automatic propagation

Automatic mode rất tiện, nhưng không phải lựa chọn miễn phí:

1. **Overhead:** việc capture/restore ThreadLocal có chi phí mỗi khi qua các ranh giới xử lý được instrument. Với pipeline có nhiều operator và lượng event lớn, cần benchmark.
2. **Accessor coverage:** chỉ các ThreadLocal đã đăng ký accessor mới được biết cách đọc/đặt/xóa. Một thư viện giữ state riêng nhưng không có accessor thì không tự được truyền.
3. **Executor ngoài Reactor:** thread pool riêng của thư viện cần được wrap/instrument riêng hoặc có integration chính thức.
4. **Context không có key:** automatic mode cần xử lý việc xóa/khôi phục state khi key không có trong Context để tránh leak; accessor phải định nghĩa reset đúng.
5. **Nhiều accessor cùng một ThreadLocal:** có thể ghi đè hoặc xóa state của nhau, đặc biệt khi MDC được quản lý đồng thời bởi tracing và accessor tùy chỉnh.
6. **Side effect và context mutable:** tự động truyền một object mutable không làm object thread-safe. Tránh chia sẻ một map mutable giữa các nhánh song song.
7. **Network boundary:** automatic mode không tự truyền dữ liệu sang process khác.
8. **Test isolation:** hook là global state và áp dụng cho subscription mới; test cần khởi tạo/cleanup có kiểm soát, không bật/tắt ngẫu nhiên giữa các test chạy song song.

Dùng limited mode hoặc bridge thủ công khi chỉ cần một vài điểm log. Chọn automatic mode khi phần lớn ứng dụng hoặc thư viện cần truy cập ThreadLocal qua nhiều operator và đã có accessor phù hợp. Đo overhead trên workload đại diện trước khi bật toàn cục cho một hệ thống có thông lượng cao.

## 12. Kiểm thử Context và MDC

### 12.1. Kiểm tra Reactor Context bằng StepVerifier

Bài test sau kiểm tra giá trị được ghi ở cuối chain có thể được đọc từ operator phía trên:

Tệp src/test/java/demo/ReactorContextTest.java:

```java
package demo;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactorContextTest {

    @Test
    void contextWriteIsVisibleUpstream() {
        Mono<String> requestId = Mono.deferContextual(context ->
                Mono.just(context.get("app.requestId")))
                .contextWrite(context ->
                        context.put("app.requestId", "req-42"));

        StepVerifier.create(requestId)
                .expectNext("req-42")
                .verifyComplete();
    }
}
```

Cần JUnit Jupiter và reactor-test trên test classpath; chạy bằng ./gradlew test hoặc mvn test tùy dự án. Test không dùng Thread.sleep và không phụ thuộc thread scheduler.

### 12.2. Kiểm tra MDC không rò giữa hai subscription

Ngoài kiểm tra Context, nên test callback MDC theo cách sau:

- Subscription A có requestId=A; log callback phải đọc được A.
- Subscription B có requestId=B; log callback phải đọc được B dù cùng worker được tái sử dụng.
- Subscription không có key; callback không được đọc nhầm A hoặc B còn sót.
- Khi callback ném exception, scope MDC vẫn phải được đóng nhờ try-with-resources.
- Khi có publishOn hoặc subscribeOn, kiểm tra callback ở đúng ranh giới thread.
- Khi chạy test song song, không dùng một static MDC value làm nguồn context chung.

Có thể dùng một List<String> đồng bộ hoặc test appender của Logback để ghi nhận các log. Không kiểm tra thứ tự thread name cố định vì scheduler có thể chọn worker khác. Kiểm tra **giá trị context và sự cô lập** mới là mục tiêu.

### 12.3. Kiểm tra accessor cho thư viện legacy

Với custom ThreadLocal accessor, kiểm tra đủ ba thao tác:

1. getValue đọc đúng giá trị của thread hiện tại.
2. setValue(value) đặt giá trị từ snapshot.
3. setValue không tham số xóa ThreadLocal khi Context không có key hoặc scope kết thúc.

Test trường hợp request A rồi request B trên cùng executor worker; sau A, trạng thái phải được restore/remove trước khi B chạy. Nếu chỉ test trên hai thread mới hoàn toàn, có thể bỏ sót lỗi leak.

Với thư viện có executor riêng, test tích hợp cần chứng minh task thực sự chạy qua executor đã wrap. Một unit test của Reactor Context không chứng minh thread pool bên thứ ba tự nhận context.

## 13. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| MDC mất sau publishOn | MDC gắn với thread, không tự theo subscriber | Đọc Reactor Context và bridge tại điểm log, hoặc bật propagation phù hợp |
| MDC có request ID của request trước | ThreadLocal không được clear/restore | Dùng try-with-resources, accessor reset và test worker reuse |
| contextWrite đã có nhưng MDC.get vẫn null | Context không tự ghi sang MDC | Dùng helper doOnEach hoặc Context Propagation accessor |
| contextCapture không chụp được ID | ThreadLocal đã bị xóa trước thời điểm subscribe, hoặc chưa đăng ký accessor | Kiểm tra subscription timing và registry |
| Automatic mode không tác dụng | Hook bật quá muộn, Reactor/Context Propagation không tương thích, thiếu accessor hoặc Context không có key | Bật lúc startup, kiểm dependency, key và accessor |
| doOnNext không thấy MDC trong limited mode | Limited mode chỉ khôi phục ở operator chọn lọc như handle/tap | Dùng tap/handle hoặc explicit MDC helper; cân nhắc auto mode |
| Thư viện ngoài vẫn không thấy tenant | Thư viện dùng ThreadLocal khác hoặc executor riêng | Viết accessor phù hợp và wrap executor/callback |
| Context đúng trong service nhưng HTTP downstream không nhận header | Context nội bộ không tự truyền qua network | Dùng WebClient filter, HTTP propagation hoặc message header |
| Bật accessor MDC khiến trace ID biến mất | Hai accessor cùng quản lý MDC hoặc ghi đè cùng key | Kiểm tra tracing integration, chỉ chọn key phù hợp, tránh đăng ký trùng |
| Log có trace ID nhưng metrics tăng cardinality mạnh | Đưa ID duy nhất vào metric tag | Giữ trace/request ID trong log/trace, dùng tag cardinality thấp cho metrics |
| Security context bị mất sau thread switch | Chưa dùng cơ chế propagation của Spring Security hoặc context boundary không được hỗ trợ | Dùng integration chính thức và test principal ở đúng callback |
| Unit test pass nhưng production vẫn leak | Chưa test thread pool reuse, executor ngoài, cancellation hoặc concurrent requests | Viết integration/load test với nhiều request và worker được tái sử dụng |

## 14. Checklist triển khai

1. **Xác định dữ liệu cần truyền:** request ID, trace/span, tenant, locale hay security principal; không gom mọi state vào một ThreadLocal.
2. **Ưu tiên Reactor Context:** dùng contextWrite để ghi và deferContextual để đọc.
3. **Chọn điểm cần MDC:** log trong doOnEach có thể bridge thủ công bằng MDC.putCloseable; không cần khôi phục MDC cho mọi business operator.
4. **Kiểm tra version:** Reactor 3.5.0 có Context Propagation SPI; 3.5.3 có automatic hook; Spring Boot 3.2+ có spring.reactor.context-propagation.
5. **Chọn limited hay auto:** hiểu callback nào được khôi phục và chi phí trước khi bật toàn cục.
6. **Đăng ký accessor đúng một lần:** chọn key cụ thể, không đụng accessor của tracing hoặc security.
7. **Đặt cleanup:** MDC.MDCCloseable, Scope.close và ThreadLocal.remove phải chạy cả khi exception.
8. **Wrap executor ngoài:** không giả định mọi thread pool được Reactor quản lý.
9. **Phân biệt process boundary:** dùng HTTP/message propagation cho dữ liệu qua mạng.
10. **Bảo vệ dữ liệu:** không đưa token/PII vào MDC; không dùng ID có cardinality cao làm metric tag.
11. **Test concurrency và worker reuse:** nhiều request đồng thời, request thiếu key, error, cancellation, external executor.
12. **Đo hiệu năng:** so sánh limited/auto/manual bridge với workload thực và theo dõi p95/p99, allocation, log volume.

## 15. Tài liệu tham khảo

- [Project Reactor Reference – Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html): Context, contextWrite, contextCapture, limited và automatic mode.
- [Project Reactor Reference – Contextual Logging (MDC)](https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/#faq.mdc): mẫu doOnEach, Signal.getContextView và MDC.MDCCloseable.
- [Spring Boot – Observability / Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html): property spring.reactor.context-propagation và ContextPropagatingTaskDecorator.
- [Micrometer Context Propagation – Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html): ThreadLocalAccessor, ContextSnapshot, ContextRegistry và các ranh giới imperative/reactive.
- [Micrometer Context Propagation – Usage Examples](https://docs.micrometer.io/micrometer/reference/1.12/contextpropagation/usage.html): đăng ký accessor và khôi phục ThreadLocal bằng scope.
- [Slf4jThreadLocalAccessor Javadoc](https://javadoc.io/doc/io.micrometer/context-propagation/latest/io/micrometer/context/integration/Slf4jThreadLocalAccessor.html): bridge cho MDC, chọn key và lưu ý khi nhiều accessor cùng quản lý MDC.
- [SLF4J MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html): các thao tác MDC và MDCCloseable.

## 16. Ghi nhớ

**Reactor Context là nguồn context theo subscription; MDC và ThreadLocal là trạng thái tạm thời theo thread.** Không giả định chúng tự đồng bộ khi pipeline đổi thread.

Với code reactive do mình kiểm soát, hãy lưu metadata bằng contextWrite và đọc bằng deferContextual. Khi cần ghi log, lấy Context từ Signal, đặt MDC trong scope ngắn bằng MDC.putCloseable rồi đóng scope. Khi phải gọi thư viện imperative dựa vào ThreadLocal, dùng Micrometer Context Propagation và accessor phù hợp; với executor riêng, wrap task/executor để capture và restore context.

Automatic propagation thuận tiện nhưng chỉ hoạt động với key/accessor được đăng ký và subscription được tạo sau khi cấu hình bật. Nó không truyền dữ liệu qua network, không thay thế security/tracing integration và không loại bỏ nhu cầu cleanup. Thiết kế đúng ranh giới giúp log có đúng request ID, thư viện legacy nhận đúng metadata và thread pool không mang context của request trước sang request sau.
