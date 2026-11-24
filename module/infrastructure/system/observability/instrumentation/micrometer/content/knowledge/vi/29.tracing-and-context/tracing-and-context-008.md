# Khôi phục rồi dọn ngữ cảnh để tránh lẫn dữ liệu giữa các yêu cầu

Ứng dụng Java thường dùng `ThreadLocal` để giữ ngữ cảnh hiện tại như observation, trace/span, tenant hoặc correlation ID. Cách này thuận tiện khi một lời gọi đi qua nhiều tầng đồng bộ trên cùng thread. Tuy nhiên, server và executor thường tái sử dụng thread cho nhiều yêu cầu. Nếu ngữ cảnh của yêu cầu trước không được khôi phục hoặc xóa đúng lúc, yêu cầu tiếp theo có thể nhìn thấy trace, tenant hoặc dữ liệu của người dùng khác.

Micrometer Observation quản lý ngữ cảnh hiện tại thông qua `Observation.Scope`. Khi scope đóng, observation trước đó được khôi phục. Với các `ThreadLocal` khác, cần dùng `try/finally` hoặc cơ chế context propagation có scope để khôi phục trạng thái trước đó và dọn giá trị không còn hợp lệ. Trong tác vụ bất đồng bộ, phải truyền ngữ cảnh sang thread đích một cách có chủ đích rồi đóng scope ở thread đó.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, quản lý context đúng giúp trace không bị nối nhầm giữa các request, log không mang sai correlation ID và tag quan sát không rò rỉ dữ liệu giữa các tenant. Quy tắc cốt lõi là mỗi lần gắn context vào thread phải có một điểm hoàn trả trạng thái tương ứng.

## 1. Vì sao thread tái sử dụng dễ gây rò rỉ context?

Servlet container, web server và thread pool thường dùng một số lượng thread hữu hạn. Sau khi xử lý xong một request, thread không bị hủy; nó quay lại pool để xử lý request tiếp theo.

Nếu code đặt dữ liệu vào `ThreadLocal` nhưng không xóa hoặc khôi phục trong mọi nhánh thực thi, giá trị có thể còn lại trên thread:

```java
private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

void handleRequest(String tenantId) {
    TENANT.set(tenantId);
    processRequest();
    // Nếu processRequest ném exception, dòng dọn dữ liệu có thể không chạy.
    TENANT.remove();
}
```

Ở ví dụ này, `remove()` chỉ chạy khi `processRequest()` hoàn tất bình thường. Nếu exception thoát ra, thread có thể giữ `tenantId` cũ. Một request sau được chạy trên cùng thread và đọc nhầm tenant.

Ngay cả khi đặt `remove()` trong `finally`, việc xóa vô điều kiện vẫn có thể phá ngữ cảnh lồng nhau. Nếu một hàm con tạm thời thay tenant context trong khi hàm cha vẫn cần giá trị cũ, khi hàm con kết thúc phải khôi phục giá trị của hàm cha thay vì xóa toàn bộ.

## 2. Phân biệt khôi phục và xóa

Hai thao tác này có mục tiêu khác nhau:

| Thao tác | Khi nào dùng | Kết quả |
| --- | --- | --- |
| Khôi phục (restore) | Có thể đã tồn tại context trước khi vào scope hiện tại | Trả thread về đúng giá trị trước đó |
| Xóa (clear/remove) | Không có context trước đó hoặc giá trị hiện tại không còn hợp lệ | Loại bỏ giá trị để thread không mang sang tác vụ tiếp theo |

Một helper an toàn thường lưu giá trị trước đó, gắn giá trị mới, rồi khôi phục trong `finally`:

```java
private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

void withTenant(String tenantId, Runnable work) {
    String previous = TENANT.get();
    try {
        TENANT.set(tenantId);
        work.run();
    } finally {
        if (previous == null) {
            TENANT.remove();
        } else {
            TENANT.set(previous);
        }
    }
}
```

Nếu trước đó thread chưa có tenant, helper xóa giá trị sau khi chạy. Nếu đang ở trong một tenant scope khác, helper khôi phục tenant trước đó. Cách này hỗ trợ scope lồng nhau và vẫn dọn dữ liệu khi code ném exception.

Không nên chỉ gọi `ThreadLocal.set(null)` như một cách dọn dữ liệu. `remove()` xóa entry của thread-local khỏi map nội bộ của thread; `set(null)` vẫn có thể giữ một entry với giá trị null và làm code đọc khó phân biệt giữa chưa thiết lập và đã thiết lập null.

## 3. Observation.Scope tự khôi phục observation trước đó

Micrometer cung cấp `Observation.Scope` để đặt một observation làm current trong một vùng thực thi. Khi đóng scope, observation hiện tại trước đó được khôi phục. Đây là cơ chế quan trọng khi các observation lồng nhau.

```java
Observation parent = Observation.start("orders.process", observationRegistry);
try (Observation.Scope parentScope = parent.openScope()) {
    validateOrder();

    Observation child = Observation.start("inventory.reserve", observationRegistry);
    try (Observation.Scope childScope = child.openScope()) {
        reserveInventory();
    } catch (RuntimeException ex) {
        child.error(ex);
        throw ex;
    } finally {
        child.stop();
    }

    // Sau khi childScope đóng, parent observation được khôi phục thành current.
    saveOrder();
} catch (RuntimeException ex) {
    parent.error(ex);
    throw ex;
} finally {
    parent.stop();
}
```

Khi `childScope.close()` chạy, Micrometer trả current observation về `parent`. Khi `parentScope.close()` chạy, current observation trước khi vào parent scope được khôi phục. Vì vậy, code bên trong không cần tự lưu và gán lại observation ThreadLocal.

`Scope.close()` không dừng observation. `child.stop()` và `parent.stop()` vẫn cần được gọi đúng một lần. Mẫu trên đóng scope trước khi stop, đồng thời báo exception cho observation tương ứng.

Trong code thông thường, `Observation.observe(...)` tự quản lý start, scope, error và stop. Chỉ dùng lifecycle thủ công khi cần điều khiển rõ mốc bắt đầu/kết thúc hoặc lồng nhiều scope.

## 4. Luôn đóng scope bằng try-with-resources

Không giữ scope mở bằng cách gọi `openScope()` rồi hy vọng một dòng `close()` cuối hàm sẽ được chạy. Exception, return sớm hoặc cancellation có thể bỏ qua dòng dọn context.

Mẫu nên dùng:

```java
observation.start();
try {
    try (Observation.Scope scope = observation.openScope()) {
        performWork();
    }
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
```

Try-with-resources đảm bảo `close()` được gọi khi block kết thúc bình thường, return hoặc ném exception. Scope được đóng trước khi `catch` và `finally` bên ngoài chạy. Nhờ đó, context của observation cha được khôi phục trước khi xử lý lỗi hoặc dừng observation con.

Nếu một method chỉ cần thực hiện công việc đồng bộ trong observation, cách ngắn hơn là:

```java
Observation.createNotStarted("orders.process", observationRegistry)
        .observe(() -> performWork());
```

Không mở scope thủ công bên ngoài rồi lại dùng `observe()` cho cùng observation; hãy chọn một cách quản lý lifecycle để tránh đóng hoặc dừng hai lần.

## 5. Khôi phục ThreadLocal tùy biến trong filter hoặc interceptor

Một số ứng dụng có context riêng như tenant, locale hoặc correlation ID. Nếu cần giữ các giá trị này bằng `ThreadLocal`, hãy đóng gói việc gắn và khôi phục vào một helper hoặc scope có thể tự đóng.

Ví dụ với servlet filter:

```java
public final class TenantContextFilter extends OncePerRequestFilter {
    private final TenantResolver tenantResolver;

    public TenantContextFilter(TenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String previous = TenantContext.get();
        try {
            TenantContext.set(tenantResolver.resolve(request));
            filterChain.doFilter(request, response);
        } finally {
            if (previous == null) {
                TenantContext.clear();
            } else {
                TenantContext.set(previous);
            }
        }
    }
}
```

`TenantContext` ở đây là holder dùng `ThreadLocal`. Filter lưu trạng thái trước đó và khôi phục trong `finally`, do đó xử lý được exception và scope lồng nhau. Nếu filter là điểm ngoài cùng của request và hợp đồng đảm bảo không có context cha, có thể chỉ cần `clear()` trong `finally`; cách lưu/khôi phục tổng quát an toàn hơn khi filter có thể được gọi lồng trong một execution context khác.

Không lấy tenant từ một `ThreadLocal` cũ trước khi xác thực request. Context phải được tạo từ thông tin đã xác thực và chỉ tồn tại trong phạm vi xử lý tương ứng.

## 6. ThreadLocalAccessor khai báo cách đọc, gắn và reset context

Thư viện Micrometer Context Propagation cung cấp `ThreadLocalAccessor` để mô tả một ThreadLocal có thể được chụp và truyền qua ranh giới thực thi. Accessor cần cung cấp:

- Một key duy nhất để nhận diện loại context.
- `getValue()` để đọc giá trị hiện tại trên thread.
- `setValue(value)` để gắn giá trị đã chụp vào thread đích.
- `setValue()` không tham số để reset/remove giá trị khi snapshot không có giá trị tương ứng.

Ví dụ đăng ký accessor cho correlation ID:

```groovy
dependencies {
    implementation 'io.micrometer:context-propagation'
}
```

Với Spring Boot, để BOM quản lý phiên bản tương thích. Nếu đã có dependency này qua starter khác, không cần khai báo lặp lại.

```java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ThreadLocalAccessor;

public final class CorrelationContext {
    private static final ThreadLocal<String> CORRELATION_ID = new ThreadLocal<>();

    private CorrelationContext() {
    }

    public static String get() {
        return CORRELATION_ID.get();
    }

    public static void set(String value) {
        CORRELATION_ID.set(value);
    }

    public static void clear() {
        CORRELATION_ID.remove();
    }

    public static void registerAccessor() {
        ContextRegistry.getInstance().registerThreadLocalAccessor(
                new ThreadLocalAccessor<String>() {
                    @Override
                    public Object key() {
                        return "correlationId";
                    }

                    @Override
                    public String getValue() {
                        return CORRELATION_ID.get();
                    }

                    @Override
                    public void setValue(String value) {
                        CORRELATION_ID.set(value);
                    }

                    @Override
                    public void setValue() {
                        CORRELATION_ID.remove();
                    }
                });
    }
}
```

Đăng ký accessor một lần khi khởi tạo ứng dụng, không đăng ký lại mỗi request. Key phải duy nhất trong `ContextRegistry`; nếu nhiều thư viện cùng đăng ký key trùng, việc truyền context có thể ghi đè sai accessor.

Accessor chỉ khai báo cách truyền một giá trị. Nó không tự động truyền ThreadLocal qua mọi executor. Cần dùng `ContextSnapshot` hoặc integration tương ứng để capture ở thread nguồn, set trên thread đích và reset khi scope đóng.

## 7. Dùng ContextSnapshot để truyền rồi khôi phục context

`ContextSnapshot` chụp các giá trị từ những accessor đã đăng ký, sau đó có thể áp dụng chúng tạm thời trên thread khác. Khi đóng scope của snapshot, giá trị trước đó trên thread đích được khôi phục.

```java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;

ContextSnapshotFactory snapshotFactory = ContextSnapshotFactory.builder()
        .contextRegistry(ContextRegistry.getInstance())
        .clearMissing(true)
        .build();

// Đang ở thread nhận request; các accessor đã có giá trị hiện tại.
ContextSnapshot snapshot = snapshotFactory.captureAll();

executor.execute(() -> {
    try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
        processAsyncWork();
    }
    // Khi scope đóng, ThreadLocal trên worker trở lại trạng thái trước đó.
});
```

`captureAll()` chỉ chụp những context được đăng ký thông qua accessor. Nó không tự động sao chép mọi ThreadLocal tùy ý trong JVM. `clearMissing(true)` yêu cầu snapshot scope reset các accessor không có giá trị trong snapshot, tránh để giá trị cũ của worker tồn tại trong thời gian thực thi tác vụ mới.

Khi `snapshot.setThreadLocals()` được gọi, Micrometer lưu trạng thái hiện tại của thread đích, áp dụng các giá trị trong snapshot và trả về một scope. Đóng scope khôi phục trạng thái đã lưu. Vì vậy, nếu worker vốn có context của một tác vụ lồng nhau, nó được phục hồi thay vì bị xóa vô điều kiện.

Không capture snapshot ở thread worker sau khi đã bắt đầu task; lúc đó có thể chụp nhầm context của worker. Hãy capture tại thread nguồn trước khi submit task và truyền snapshot bất biến vào task.

## 8. Dùng ContextPropagatingTaskDecorator với Spring executor

Spring Framework cung cấp `ContextPropagatingTaskDecorator` để tích hợp context propagation cho task được thực thi bởi một executor. Khi dùng `ThreadPoolTaskExecutor`, gắn decorator vào executor cụ thể:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncExecutorConfiguration {
    @Bean
    TaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor(TaskDecorator decorator) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(decorator);
        executor.initialize();
        return executor;
    }
}
```

Decorator chụp context khi task được bọc và khôi phục context trong lúc task chạy. Khi task kết thúc, scope được đóng để dọn hoặc khôi phục ThreadLocal trên worker. Việc truyền context chỉ áp dụng cho executor được gắn decorator; một executor tự tạo khác không tự động nhận cấu hình này.

Context Propagation chỉ truyền những giá trị có accessor được đăng ký. Với Observation/Tracing, hãy dùng phiên bản Spring Boot và Micrometer tương thích để các accessor tương ứng được cấu hình. Với ThreadLocal tùy biến, đăng ký `ThreadLocalAccessor` như phần trước.

## 9. Reactor Context khác ThreadLocal

Reactor dùng `Context` gắn với subscription để truyền dữ liệu qua các operator. Dữ liệu này không phụ thuộc một thread cố định, vì pipeline có thể chạy trên nhiều scheduler. Vì vậy, không nên giả định một `ThreadLocal` được set ở đầu pipeline sẽ luôn tồn tại ở mọi operator.

Với Spring Boot hỗ trợ Reactor context propagation, có thể bật chế độ tự động:

```yaml
spring:
  reactor:
    context-propagation: auto
```

Chế độ này kết nối Reactor Context với các accessor ThreadLocal trong những đoạn thực thi phù hợp. Khi dùng `contextWrite`, hãy ghi dữ liệu vào Reactor Context; khi cần truy cập ThreadLocal trong callback, cơ chế propagation sẽ khôi phục giá trị trong phạm vi callback và dọn khi rời phạm vi đó.

Với Reactor thuần, Context Propagation cung cấp integration qua `Hooks.enableAutomaticContextPropagation()` trên các phiên bản hỗ trợ. Cần bật hook một lần khi khởi tạo ứng dụng và hiểu rõ chi phí của việc khôi phục ThreadLocal ở mỗi operator. Không trộn lẫn việc tự set ThreadLocal thủ công với automatic propagation nếu không có quy tắc sở hữu rõ ràng.

## 10. Tại sao cần clearMissing khi chuyển snapshot?

Giả sử worker thread xử lý request A và có `tenant=A`. Sau khi task A kết thúc, một task B được submit nhưng snapshot của B không chứa tenant. Nếu cơ chế propagation chỉ ghi các giá trị có trong snapshot mà không reset giá trị vắng mặt, worker có thể vẫn giữ `tenant=A` trong lúc chạy B.

Với `clearMissing(true)`, accessor không có giá trị trong snapshot được reset khi snapshot được áp dụng. Khi scope đóng, giá trị cũ trước khi áp dụng snapshot được khôi phục. Trên worker thread trống context, giá trị cũ thường là không có; do đó sau task, worker trở lại trạng thái sạch.

| Trạng thái worker trước task | Snapshot task mới | Khi task chạy | Khi scope đóng |
| --- | --- | --- | --- |
| `tenant=A` | `tenant=B` | `tenant=B` | Khôi phục `tenant=A` |
| `tenant=A` | Không có tenant, `clearMissing=true` | Tenant được reset/không có | Khôi phục trạng thái trước scope (`tenant=A`) |
| Không có tenant | `tenant=B` | `tenant=B` | Xóa tenant khỏi worker |
| Không có tenant | Không có tenant | Không có tenant | Vẫn không có tenant |

Trong thread pool, điều quan trọng là task mới không nhìn thấy context cũ của worker. `clearMissing` bảo đảm điều đó trong phạm vi snapshot scope. Tuy nhiên, scope vẫn khôi phục trạng thái nền trước khi áp dụng snapshot. Nếu worker đã bị để lại `tenant=A` do task trước cleanup sai, khi scope của task B đóng, giá trị A sẽ được khôi phục như bảng trên. Vì vậy, `clearMissing` là lớp bảo vệ khi áp dụng snapshot; nó không thay thế việc sửa task trước để task đó luôn đóng scope và dọn context đúng cách. Không để code ngoài các scope được quản lý đọc ThreadLocal nền bị rò rỉ.

## 11. Tránh context rò rỉ khi xử lý exception và cancellation

Mọi đường thoát khỏi scope phải thực hiện cleanup:

- Kết thúc bình thường.
- Ném checked hoặc unchecked exception.
- Return sớm.
- Task bị hủy hoặc ngắt nếu code có thể phản ứng với interruption.
- Callback async kết thúc exceptional.

Với `Observation`, dùng `observe()` hoặc try-with-resources cho scope và `finally` cho `stop()`. Với ThreadLocal tùy biến, lưu trạng thái cũ và khôi phục trong `finally`. Với `ContextSnapshot`, đặt `setThreadLocals()` trong try-with-resources.

Không dựa vào `ThreadPoolExecutor.afterExecute()` để xóa mọi ThreadLocal toàn cục. Executor có thể được chia sẻ bởi nhiều thư viện; xóa indiscriminately có thể phá context mà một tầng khác vẫn đang sử dụng. Hãy để từng accessor/scope chịu trách nhiệm cho giá trị mà nó sở hữu.

Nếu task bị hủy trước khi bắt đầu, wrapper cần bảo đảm snapshot không bị áp dụng dở dang. Nếu task đã bắt đầu và bị interrupt, `finally` trong task vẫn phải đóng scope. Tránh bắt `Throwable` chỉ để nuốt lỗi; cleanup phải chạy nhưng exception/error vẫn cần được truyền theo hợp đồng của executor.

## 12. Kiểm thử việc khôi phục và dọn context

Test cần chứng minh không chỉ giá trị trong task hiện tại mà cả trạng thái sau khi scope đóng. Ví dụ kiểm tra scope lồng nhau của ThreadLocal:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class TenantContextTest {
    @Test
    void nestedScopeRestoresPreviousTenant() {
        TenantContext.set("tenant-parent");
        try {
            withTenant("tenant-child", () ->
                    assertThat(TenantContext.get()).isEqualTo("tenant-child"));

            assertThat(TenantContext.get()).isEqualTo("tenant-parent");
        } finally {
            TenantContext.clear();
        }

        assertThat(TenantContext.get()).isNull();
    }
}
```

Test trên chứng minh child scope khôi phục parent và test tự dọn trạng thái ban đầu để không ảnh hưởng test khác.

Kiểm thử Observation scope lồng nhau:

```java
@Test
void closingChildScopeRestoresParentObservation() {
    ObservationRegistry registry = ObservationRegistry.create();
    Observation parent = Observation.start("parent", registry);
    Observation child = Observation.createNotStarted("child", registry);

    try (Observation.Scope parentScope = parent.openScope()) {
        assertThat(Observation.currentObservation()).isSameAs(parent);

        child.start();
        try (Observation.Scope childScope = child.openScope()) {
            assertThat(Observation.currentObservation()).isSameAs(child);
        }

        assertThat(Observation.currentObservation()).isSameAs(parent);
    } finally {
        child.stop();
        parent.stop();
    }

    assertThat(Observation.currentObservation()).isNull();
}
```

Kiểm thử propagation với executor nên dùng một thread pool có một worker để dễ tái sử dụng cùng thread:

1. Submit task A với `tenant=A`; xác nhận task thấy A.
2. Hoàn tất task A và đóng snapshot scope.
3. Submit task B không có tenant; xác nhận task B không thấy A.
4. Submit task C với `tenant=C`; xác nhận task thấy C.
5. Sau mỗi task, kiểm tra worker đã trở về context trước đó.

Để test không phụ thuộc lịch chạy ngẫu nhiên, dùng executor một thread, `Future.get()` để đợi từng task và accessor có thể quan sát giá trị. Bổ sung trường hợp task ném exception để xác nhận cleanup vẫn xảy ra.

## 13. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi `ThreadLocal.set()` mà không có `finally` | Request sau có thể đọc giá trị cũ | Khôi phục hoặc remove trong `finally` |
| Luôn `remove()` khi scope lồng nhau | Làm mất context của caller | Lưu và khôi phục giá trị trước đó |
| Dùng `set(null)` để cleanup | Entry ThreadLocal vẫn có thể tồn tại và khó phân biệt trạng thái | Dùng `remove()` khi không có giá trị trước đó |
| Quên đóng `Observation.Scope` | Current observation/trace context có thể rò sang code tiếp theo | Dùng try-with-resources |
| Nghĩ `Scope.close()` dừng observation | Timer/span không được hoàn tất | Gọi `stop()` riêng hoặc dùng `observe()` |
| Chỉ truyền context sang worker mà không reset missing keys | Worker có thể nhìn thấy giá trị cũ của task trước | Dùng accessor reset và `clearMissing(true)` |
| Capture snapshot trên worker thay vì thread nguồn | Có thể chụp context của task trước | Capture trước khi submit task |
| Tưởng mọi ThreadLocal đều được tự động truyền | Context tùy biến bị mất hoặc không được dọn | Đăng ký `ThreadLocalAccessor` và dùng propagation integration |
| Chỉ gắn decorator cho một executor nhưng submit vào executor khác | Context không được truyền | Cấu hình decorator trên đúng executor thực thi task |
| Dùng ThreadLocal trực tiếp trong Reactor pipeline | Context mất khi đổi scheduler hoặc operator | Dùng Reactor Context và context propagation |
| Cleanup toàn bộ ThreadLocal trong `afterExecute` | Có thể phá context của thư viện khác | Mỗi scope/accessor chỉ dọn context mà nó sở hữu |

## 14. Quy trình quản lý context an toàn

Khi thêm một loại context vào ứng dụng, hãy thực hiện theo trình tự:

1. Xác định context thuộc request, observation, trace, tenant hay tác vụ async.
2. Ưu tiên dùng `Observation.Scope`, Reactor Context hoặc abstraction context có sẵn thay vì tạo ThreadLocal mới.
3. Nếu cần ThreadLocal tùy biến, định nghĩa accessor có key duy nhất và phương thức reset rõ ràng.
4. Khi vào scope, lưu trạng thái trước đó; khi ra scope, khôi phục trạng thái đó hoặc remove nếu trước đó không có.
5. Dùng try-with-resources cho `Observation.Scope` và `ContextSnapshot.Scope`.
6. Khi submit task, capture snapshot ở thread nguồn và áp dụng trên thread đích.
7. Bật clear missing values để task không nhận context cũ của worker.
8. Cấu hình context propagation cho executor và Reactor pipeline thực tế đang dùng.
9. Kiểm thử nested scope, exception, cancellation và tái sử dụng thread.
10. Xác nhận trace ID, tenant và correlation ID không xuất hiện ở request tiếp theo nếu request đó không mang các giá trị ấy.

Context an toàn cần cả hai bước: đưa đúng dữ liệu vào execution context và hoàn trả thread về trạng thái trước đó khi phạm vi kết thúc. `Observation.Scope` tự khôi phục observation cha; `ThreadLocalAccessor` cùng `ContextSnapshot` truyền và reset các giá trị tùy biến; `try/finally` bảo đảm cleanup khi có exception. Khi những quy tắc này được áp dụng nhất quán, thread pool có thể tái sử dụng mà không làm lẫn trace, tenant hoặc correlation data giữa các yêu cầu.

## Tài liệu tham khảo

- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Micrometer Context Propagation: Usage](https://docs.micrometer.io/context-propagation/reference/usage.html)
- [Micrometer Observation: Scope and Context](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Spring Framework: ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
