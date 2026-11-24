# Tùy chỉnh ExecutorService và vòng đời tài nguyên

## Vai trò của executor trong tích hợp Resilience4j

Circuit Breaker quyết định một lời gọi có được phép đi đến dịch vụ phụ thuộc hay không và ghi nhận kết quả của lời gọi. Bản thân Circuit Breaker không tạo một thread pool để chạy mọi lời gọi. Trong tích hợp Spring Cloud Circuit Breaker với Resilience4j, executor thường xuất hiện ở hai tình huống: lập lịch tác vụ timeout của `TimeLimiter` và thực thi công việc bất đồng bộ hoặc cô lập bằng thread pool.

Phân biệt các loại tài nguyên giúp tránh dùng nhầm thread pool:

| Tài nguyên | Vai trò | Cách quản lý |
| --- | --- | --- |
| `ScheduledExecutorService` của factory | Lập lịch các tác vụ liên quan đến timeout trong tích hợp Resilience4j. | Cấu hình qua `Resilience4JCircuitBreakerFactory`; quản lý như bean dùng chung của Spring. |
| `ExecutorService` của ứng dụng | Chạy công việc bất đồng bộ do ứng dụng chủ động gửi đi. | Ứng dụng tạo, giới hạn tải và đóng theo vòng đời của ApplicationContext. |
| Thread pool của `ThreadPoolBulkhead` | Cô lập số luồng và hàng đợi dành cho một nhóm lời gọi. | Cấu hình bằng chính sách ThreadPoolBulkhead; không dùng scheduler timeout thay thế. |

Trong nhiều ứng dụng, việc tùy chỉnh quan trọng nhất là scheduler mà `Resilience4JCircuitBreakerFactory` sử dụng cho `TimeLimiter`. Scheduler này cần hoạt động ổn định trong suốt vòng đời ứng dụng. Không nên tạo một executor mới cho từng request hoặc từng lần gọi `create()`.

## Tùy chỉnh ScheduledExecutorService cho CircuitBreakerFactory

Spring Cloud Circuit Breaker cho phép cấu hình executor của factory bằng `configureExecutorService`. Ta có thể khai báo một `ScheduledThreadPoolExecutor` thành bean Spring, sau đó đưa bean đó vào một `Customizer`:

```java
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.scheduling.concurrent.CustomizableThreadFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CircuitBreakerExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService circuitBreakerScheduler() {
        ScheduledThreadPoolExecutor executor = new ScheduledThreadPoolExecutor(
            4,
            new CustomizableThreadFactory("circuit-breaker-timeout-")
        );
        executor.setRemoveOnCancelPolicy(true);
        executor.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        executor.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
        return executor;
    }

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> circuitBreakerExecutorCustomizer(
            @Qualifier("circuitBreakerScheduler")
            ScheduledExecutorService scheduler) {
        return factory -> factory.configureExecutorService(scheduler);
    }
}
```

Trong ví dụ, `circuitBreakerScheduler` là một bean singleton. Factory nhận cùng scheduler này thay vì tự tạo pool riêng cho mỗi breaker. `CustomizableThreadFactory` đặt tiền tố tên luồng để dễ nhận diện khi đọc thread dump hoặc log. `setRemoveOnCancelPolicy(true)` giúp loại bỏ tác vụ đã bị hủy khỏi hàng đợi trì hoãn, tránh giữ lại nhiều tác vụ timeout không còn cần thiết. Hai policy shutdown ngăn các tác vụ trì hoãn hoặc định kỳ tiếp tục chạy sau khi ứng dụng bắt đầu đóng.

Số luồng bằng 4 chỉ là giá trị minh họa. Hãy chọn theo số lượng timeout cần được xử lý đồng thời, mức tải và đặc điểm của tác vụ được lập lịch. Công việc của scheduler thường là xử lý tín hiệu timeout ngắn; không chạy các tác vụ I/O chặn lâu hoặc tính toán nặng trên pool này. Một tác vụ chặn có thể chiếm worker và làm chậm việc phát tín hiệu timeout cho các lời gọi khác.

API cấu hình cụ thể cần khớp với phiên bản Spring Cloud Circuit Breaker đang dùng. Starter Resilience4j đã cung cấp factory và auto-configuration; `Customizer` chỉ bổ sung cấu hình cho factory hiện có. Tránh khai báo một factory mới chỉ để thay scheduler, vì điều đó có thể vô tình thay thế cấu hình và các bean mà starter đã tạo.

## Vòng đời của executor trong Spring

Executor là tài nguyên có trạng thái và tạo ra thread. Khi Spring tạo bean, pool bắt đầu phục vụ công việc; khi ApplicationContext đóng, pool cần được shutdown để JVM có thể kết thúc bình thường.

Với bean trong ví dụ, `destroyMethod = "shutdown"` yêu cầu Spring gọi `shutdown()` khi bean bị hủy. Cách này phù hợp khi scheduler dùng chung trong suốt vòng đời ứng dụng. Các bước quản lý thường là:

1. Tạo executor một lần khi ApplicationContext khởi động.
2. Inject executor vào customizer và để factory sử dụng nó.
3. Không gọi `shutdown()` sau từng request, từng circuit breaker hoặc trong fallback.
4. Khi ứng dụng dừng, Spring gọi phương thức hủy bean để ngừng nhận tác vụ mới.
5. Nếu ứng dụng cần chờ các công việc đang chạy hoàn tất trong một thời hạn, bổ sung chính sách graceful shutdown và giới hạn thời gian chờ.

`shutdown()` không buộc các tác vụ đang chạy dừng ngay lập tức. Nó từ chối tác vụ mới và cho các tác vụ đã được chấp nhận cơ hội hoàn tất theo chính sách của executor. `shutdownNow()` cố gắng ngắt các worker đang chạy và trả về các tác vụ chưa bắt đầu; việc ngắt chỉ có hiệu lực nếu tác vụ hợp tác với interrupt. Vì vậy, không dùng `shutdownNow()` như cách thay thế cho timeout của lời gọi mạng.

Nếu cần graceful shutdown có thời hạn, có thể đóng gói executor bằng một bean quản lý riêng:

```java
import java.time.Duration;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public final class ManagedScheduler implements AutoCloseable {
    private final ScheduledExecutorService delegate;
    private final Duration shutdownWait;

    public ManagedScheduler(
            ScheduledExecutorService delegate,
            Duration shutdownWait) {
        this.delegate = delegate;
        this.shutdownWait = shutdownWait;
    }

    public ScheduledExecutorService executor() {
        return delegate;
    }

    @Override
    public void close() {
        delegate.shutdown();
        try {
            if (!delegate.awaitTermination(
                    shutdownWait.toMillis(), TimeUnit.MILLISECONDS)) {
                delegate.shutdownNow();
            }
        } catch (InterruptedException interrupted) {
            delegate.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Đây là lớp quản lý do ứng dụng tự định nghĩa. Nếu dùng nó làm bean, cần bảo đảm chỉ có một nơi sở hữu việc đóng `delegate`; không đồng thời để một bean khác shutdown cùng executor. Thời gian chờ phải hữu hạn để quá trình dừng ứng dụng không bị treo vô thời hạn. Việc khôi phục cờ interrupt sau khi bắt `InterruptedException` giúp giữ lại tín hiệu dừng cho thread hiện tại.

Trong trường hợp đơn giản, bean executor với `destroyMethod = "shutdown"` thường đã đủ. Chỉ thêm lớp quản lý graceful shutdown khi ứng dụng có yêu cầu rõ ràng về thời gian hoàn tất công việc trước khi tiến trình dừng.

## Phân biệt scheduler timeout và executor chạy nghiệp vụ

`configureExecutorService` của factory dành cho executor mà tích hợp Resilience4j dùng để lập lịch. Nó không tự động biến mọi lời gọi đến dịch vụ phụ thuộc thành lời gọi chạy trên pool đó. Nếu ứng dụng cần chạy một tác vụ bất đồng bộ, hãy khai báo một executor riêng theo tải của tác vụ:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.scheduling.concurrent.CustomizableThreadFactory;

@Bean(name = "catalogIoExecutor", destroyMethod = "shutdown")
ExecutorService catalogIoExecutor() {
    return Executors.newFixedThreadPool(
        8,
        new CustomizableThreadFactory("catalog-io-")
    );
}
```

Sau đó truyền executor này trực tiếp vào API bất đồng bộ của ứng dụng, ví dụ `CompletableFuture.supplyAsync(task, catalogIoExecutor)`. Đặt giới hạn đồng thời phù hợp với khả năng của dịch vụ phụ thuộc và giới hạn tài nguyên của tiến trình. Nếu công việc có thể chặn lâu, cần timeout ở HTTP client hoặc `TimeLimiter` tương ứng; không giả định rằng dùng thread pool là đã có timeout.

Không dùng chung một pool cho mọi loại công việc nếu tải của chúng có thể ảnh hưởng lẫn nhau. Một đợt I/O chậm có thể chiếm hết worker và làm chậm các tác vụ khác. Tách scheduler timeout khỏi executor chạy I/O giúp tác vụ timeout vẫn có cơ hội được thực thi đúng hạn.

## ThreadPoolBulkhead sở hữu một pool khác

Resilience4j `ThreadPoolBulkhead` tạo cơ chế cô lập với core thread, giới hạn thread tối đa và hàng đợi riêng. Nó phù hợp khi cần giới hạn số công việc đồng thời dành cho một dịch vụ phụ thuộc. Đây là tài nguyên khác với scheduler được cấu hình cho `TimeLimiter`.

Ví dụ cấu hình bằng `application.yml`:

```yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      catalog:
        maxThreadPoolSize: 8
        coreThreadPoolSize: 4
        queueCapacity: 20
        keepAliveDuration: 20ms
```

`coreThreadPoolSize` là số worker cơ sở, `maxThreadPoolSize` là giới hạn worker, `queueCapacity` giới hạn số tác vụ chờ và `keepAliveDuration` điều khiển thời gian worker dư được giữ lại theo chính sách pool. Khi hàng đợi đầy và pool không thể nhận thêm công việc, lời gọi có thể bị từ chối. Ứng dụng cần xử lý tình huống này như một tín hiệu quá tải, có thể ghi metrics và trả phản hồi phù hợp.

Không tăng `queueCapacity` vô hạn để che tình trạng thiếu năng lực xử lý. Hàng đợi lớn làm tăng thời gian chờ, giữ nhiều tác vụ và có thể khiến request hết hạn trước khi bắt đầu chạy. Chọn giới hạn đồng thời và hàng đợi dựa trên latency mục tiêu, thời gian xử lý và khả năng chịu tải của dịch vụ đích.

Khi sử dụng registry hoặc provider của Resilience4j, để thành phần quản lý bulkhead quản lý vòng đời pool của nó theo phiên bản thư viện. Không lấy scheduler của factory rồi truyền vào ThreadPoolBulkhead hoặc tự shutdown pool nội bộ trong khi registry vẫn đang sử dụng. Nếu tự tạo ThreadPoolBulkhead hoặc registry, cần xác định rõ thành phần nào sở hữu tài nguyên và gọi cơ chế đóng tương ứng khi ApplicationContext dừng.

## Context propagation và quan sát thread

Một task chạy trên thread khác không mặc nhiên mang theo mọi `ThreadLocal` của thread gọi ban đầu. Điều này có thể ảnh hưởng đến MDC logging, tracing hoặc ngữ cảnh bảo mật. Nếu ứng dụng cần truyền ngữ cảnh qua scheduler hay executor, hãy sử dụng cơ chế context propagation tương thích với phiên bản Spring và thư viện đang dùng, hoặc bọc task bằng decorator phù hợp.

Không nên tự sao chép toàn bộ `ThreadLocal` một cách tùy tiện. Chỉ truyền những ngữ cảnh cần thiết, làm sạch sau khi task hoàn tất và kiểm tra rằng dữ liệu của request trước không rò rỉ sang request sau trên cùng worker. Khi thay executor mặc định có hỗ trợ context-aware bằng executor thuần, cần xác nhận lại hành vi tracing và logging.

Nên quan sát các chỉ số sau:

- Số worker đang hoạt động và số tác vụ đang chờ.
- Số tác vụ timeout, bị hủy hoặc bị từ chối.
- Thời gian chờ trong hàng đợi và thời gian thực thi.
- Số thread còn sống sau khi ApplicationContext bắt đầu đóng.
- Tên thread trong thread dump để phân biệt scheduler timeout, I/O executor và bulkhead.

Tên thread rõ ràng như `circuit-breaker-timeout-`, `catalog-io-` giúp xác định pool nào bị nghẽn. Kết hợp metrics của executor với metrics Circuit Breaker để biết lỗi đến từ dịch vụ phụ thuộc, timeout, hay thiếu worker xử lý.

## Các lỗi quản lý tài nguyên thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Tạo executor mới trong mỗi lần gọi factory hoặc mỗi request. | Tăng số thread, khó giới hạn tài nguyên và có thể rò rỉ thread. | Khai báo executor singleton hoặc pool theo workload có chủ đích. |
| Không đóng executor khi Spring dừng. | Thread còn sống khiến tiến trình khó kết thúc. | Dùng bean lifecycle với `destroyMethod` hoặc cơ chế graceful shutdown có giới hạn. |
| Gọi `shutdown()` trong fallback. | Một lỗi dịch vụ có thể làm pool ngừng phục vụ các request tiếp theo. | Chỉ đóng tài nguyên tại nơi sở hữu vòng đời của nó. |
| Dùng scheduler timeout để chạy I/O chặn. | Tác vụ timeout khác bị trễ vì worker scheduler bị chiếm. | Tách scheduler và executor nghiệp vụ. |
| Dùng hàng đợi bulkhead không giới hạn. | Tăng bộ nhớ và latency, request chờ quá hạn. | Đặt `queueCapacity` hữu hạn và xử lý từ chối. |
| Thay executor mặc định mà không kiểm tra context propagation. | Thiếu trace ID hoặc MDC trong log của thread phụ. | Bổ sung cơ chế truyền ngữ cảnh và kiểm tra việc dọn context. |

## Quy trình kiểm tra trước khi đưa vào vận hành

1. Xác định executor nào phục vụ `TimeLimiter`, executor nào chạy nghiệp vụ và pool nào thuộc `ThreadPoolBulkhead`.
2. Khai báo từng pool ở đúng phạm vi sở hữu, đặt tên thread dễ nhận biết và giới hạn kích thước.
3. Tiêm scheduler vào `Resilience4JCircuitBreakerFactory` qua `Customizer`.
4. Xác nhận timeout thực thi đúng, các lời gọi không bị block trên scheduler và fallback không đóng tài nguyên dùng chung.
5. Dừng ApplicationContext trong môi trường kiểm thử, quan sát thread và xác nhận executor được shutdown.
6. Kiểm tra lại metrics, tracing và log sau khi thay executor mặc định.

Khi tùy chỉnh `ExecutorService`, mục tiêu là kiểm soát rõ ai tạo, ai sử dụng và ai đóng từng pool. Việc quản lý vòng đời đúng giúp tích hợp Resilience4j ổn định khi tải tăng, khi timeout xảy ra và khi ứng dụng khởi động hoặc dừng trong hệ thống Spring Cloud.
