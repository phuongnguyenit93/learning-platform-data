# Tách kiểm thử tác vụ bất đồng bộ khỏi kiểm thử lịch kích hoạt

Một tác vụ chạy nền có thể được kích hoạt theo nhiều cách: người dùng gửi request, một message đến queue hoặc lịch `@Scheduled` đến thời điểm chạy. Phần xử lý công việc và cơ chế quyết định thời điểm kích hoạt là hai trách nhiệm khác nhau. Nếu kiểm thử cả hai trong cùng một test bằng cách chờ đồng hồ chạy đến thời điểm hẹn, test sẽ chậm, phụ thuộc thời gian thực và khó xác định lỗi nằm ở logic công việc hay ở lịch.

Trong Spring, nên tách phần nghiệp vụ thành một service có thể gọi trực tiếp, dùng `@Async` hoặc `TaskExecutor` để kiểm tra cách chạy bất đồng bộ, và giữ phương thức `@Scheduled` thật mỏng để kiểm tra riêng việc đăng ký và kích hoạt. Cách chia này giúp test logic công việc không cần scheduler, còn test scheduler không cần chạy toàn bộ tác vụ nền.

## Phân biệt ba trách nhiệm

Một quy trình nền thường có ba phần:

| Phần | Trách nhiệm | Cơ chế Spring thường dùng |
|---|---|---|
| Business task | Thực hiện công việc thực tế: đọc dữ liệu, tính toán, cập nhật trạng thái | Service thông thường, không phụ thuộc lịch hoặc thread |
| Async execution | Đưa công việc sang thread/executor khác và quản lý kết quả hoàn tất | `@Async`, `TaskExecutor`, `CompletableFuture` |
| Schedule trigger | Xác định khi nào cần yêu cầu công việc chạy | `@Scheduled`, `TaskScheduler`, `Trigger` |

`TaskExecutor` và `TaskScheduler` giải quyết hai vấn đề khác nhau. Executor thực thi một task được gửi đến; scheduler quyết định thời điểm gọi một `Runnable` theo cron, fixed rate, fixed delay hoặc một `Trigger`. Một scheduled method có thể gọi async launcher rồi trả về nhanh để scheduler tiếp tục quản lý các lần kích hoạt sau.

Luồng xử lý được tổ chức như sau:

```text
Cron / fixed delay
        |
        v
Scheduled method (@Scheduled)
        |
        v
Async launcher (@Async)
        |
        v
Business task service
        |
        v
Repository / external system
```

Test business task gọi service trực tiếp. Test async execution gọi launcher qua Spring proxy và chờ `Future` hoàn tất. Test scheduler chỉ xác nhận lịch đã đăng ký và runnable khi được kích hoạt sẽ gọi launcher.

## Tách logic nghiệp vụ khỏi annotation chạy nền

Không nên đặt toàn bộ nghiệp vụ vào một phương thức vừa mang `@Scheduled` vừa chứa nhiều truy vấn và cập nhật dữ liệu. Hãy chuyển phần công việc sang service thông thường:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class ExpiredSessionCleanup {

    private final SessionRepository sessionRepository;

    ExpiredSessionCleanup(SessionRepository sessionRepository) {
        this.sessionRepository = sessionRepository;
    }

    @Transactional
    int removeExpiredSessions() {
        return sessionRepository.deleteExpiredSessions();
    }
}
```

Service này không biết ai gọi nó và gọi vào lúc nào. Nó có thể được gọi từ HTTP handler, message listener, async launcher, scheduler hoặc test đơn vị. Transaction cũng nằm ở ranh giới xử lý nghiệp vụ, nên test có thể xác nhận hành vi repository mà không phải chờ scheduler.

### Kiểm thử business task trực tiếp

Test logic nghiệp vụ bằng JUnit và mock dependency:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ExpiredSessionCleanupTest {

    @Mock
    private SessionRepository sessionRepository;

    @InjectMocks
    private ExpiredSessionCleanup cleanup;

    @Test
    void removesExpiredSessions() {
        when(sessionRepository.deleteExpiredSessions()).thenReturn(3);

        int removed = cleanup.removeExpiredSessions();

        assertThat(removed).isEqualTo(3);
        verify(sessionRepository).deleteExpiredSessions();
    }
}
```

Test này kiểm tra phần việc thực sự cần đúng: service gọi repository và trả lại số bản ghi đã xóa. Nó không cần bật `@EnableScheduling`, không cần `@EnableAsync` và không cần chờ một thời điểm trong tương lai. Các nhánh nghiệp vụ như bỏ qua bản ghi chưa hết hạn, xử lý dữ liệu không hợp lệ hoặc rollback khi repository lỗi cũng nên được kiểm tra ở lớp này.

Nếu logic task cần transaction hoặc Spring bean khác, dùng test context thích hợp cho service. Dù vậy, vẫn giữ test độc lập với thời điểm kích hoạt; việc transaction commit hay rollback là trách nhiệm riêng có thể kiểm thử bằng integration test của tầng dữ liệu.

## Đưa tác vụ sang executor bằng @Async

`@Async` đánh dấu phương thức cần được gọi thông qua một executor. Bật chức năng này bằng `@EnableAsync` và khai báo executor có tên rõ ràng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

@Configuration
@EnableAsync
class AsyncExecutionConfig {

    @Bean("cleanupExecutor")
    Executor cleanupExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("cleanup-");
        return executor;
    }
}
```

Launcher chỉ chịu trách nhiệm chuyển yêu cầu thực thi sang executor:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

import java.util.concurrent.CompletableFuture;

@Component
class AsyncCleanupLauncher {

    private final ExpiredSessionCleanup cleanup;

    AsyncCleanupLauncher(ExpiredSessionCleanup cleanup) {
        this.cleanup = cleanup;
    }

    @Async("cleanupExecutor")
    public CompletableFuture<Integer> launch() {
        int removed = cleanup.removeExpiredSessions();
        return CompletableFuture.completedFuture(removed);
    }
}
```

Khi gọi qua Spring proxy, executor thực thi phần thân phương thức trên thread riêng. Với kiểu trả về `CompletableFuture<T>`, caller có thể quan sát kết quả và exception khi công việc hoàn tất. Với phương thức trả `void`, exception không thể được truyền về caller; cần cấu hình `AsyncUncaughtExceptionHandler` nếu muốn xử lý exception phát sinh từ async void method.

`@Async` hoạt động qua proxy. Vì vậy, gọi một phương thức `@Async` từ một phương thức khác trong cùng instance (`this.launch()`) thường không đi qua proxy và không tạo async dispatch. Hãy gọi launcher thông qua Spring bean được inject.

## Kiểm thử async execution riêng

Test async cần xác nhận launcher được gọi qua proxy, công việc được chuyển sang executor và kết quả hoàn tất. Không cần dùng scheduler trong test này.

Ví dụ cấu hình test dùng executor nhỏ, có thread name prefix xác định và một collaborator giả:

```java
import static org.mockito.Mockito.mock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncLauncherTestConfig {

    @Bean("cleanupExecutor")
    ThreadPoolTaskExecutor cleanupExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("cleanup-test-");
        return executor;
    }

    @Bean
    ExpiredSessionCleanup cleanup() {
        return mock(ExpiredSessionCleanup.class);
    }

    @Bean
    AsyncCleanupLauncher launcher(ExpiredSessionCleanup cleanup) {
        return new AsyncCleanupLauncher(cleanup);
    }
}
```

Test lấy launcher từ application context, vì vậy lời gọi đi qua proxy Spring:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(AsyncLauncherTestConfig.class)
class AsyncCleanupLauncherTest {

    @Autowired
    private AsyncCleanupLauncher launcher;

    @Autowired
    private ExpiredSessionCleanup cleanup;

    @Test
    void runsCleanupOnConfiguredExecutor() throws Exception {
        when(cleanup.removeExpiredSessions())
                .thenAnswer(invocation -> {
                    assertThat(Thread.currentThread().getName())
                            .startsWith("cleanup-test-");
                    return 3;
                });

        int removed = launcher.launch().get(2, TimeUnit.SECONDS);

        assertThat(removed).isEqualTo(3);
        verify(cleanup).removeExpiredSessions();
    }
}
```

`get(timeout, unit)` chờ có giới hạn và trả kết quả khi async task hoàn tất. Nếu task không hoàn tất trong thời gian cho phép, test thất bại thay vì treo vô hạn. Việc kiểm tra thread name xác nhận phương thức được chạy trên executor được chỉ định. Có thể thay bằng một `CountDownLatch` hoặc `CompletableFuture` hoàn tất từ collaborator khi test cần phối hợp nhiều bước.

Không dùng `Thread.sleep()` để đợi task. Sleep chỉ trì hoãn test; nó không chứng minh công việc đã hoàn tất và có thể thất bại ngẫu nhiên khi CI chậm. Dùng future, latch hoặc thư viện chờ có timeout để đồng bộ theo một điều kiện thực tế.

### Kiểm tra exception trong async task

Với phương thức trả `CompletableFuture`, exception có thể được quan sát qua future:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

when(cleanup.removeExpiredSessions())
        .thenThrow(new IllegalStateException("repository unavailable"));

CompletableFuture<Integer> future = launcher.launch();

assertThatThrownBy(() -> future.get(2, TimeUnit.SECONDS))
        .hasCauseInstanceOf(IllegalStateException.class);
```

Khi dùng `join()`, exception thường được bọc trong `CompletionException`; với `get()`, exception được bọc trong `ExecutionException`. Chọn cách assert theo loại wrapper mà API trả về và kiểm tra cause thực tế.

Nếu launcher trả `void`, caller không có future để chờ hoặc nhận exception. Khi đó, dùng latch/test observer hoặc cấu hình `AsyncUncaughtExceptionHandler` để xác nhận lỗi được xử lý theo chính sách của ứng dụng.

## Giữ scheduled method mỏng

Scheduled method chỉ nên quyết định rằng đã đến lúc yêu cầu công việc chạy. Nó không nên chứa toàn bộ logic nghiệp vụ:

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class CleanupSchedule {

    private final AsyncCleanupLauncher launcher;

    CleanupSchedule(AsyncCleanupLauncher launcher) {
        this.launcher = launcher;
    }

    @Scheduled(cron = "${cleanup.cron}")
    public void triggerCleanup() {
        launcher.launch();
    }
}
```

Khai báo lịch trong cấu hình:

```properties
cleanup.cron=0 0/15 * * * *
```

Ví dụ này yêu cầu kích hoạt mỗi 15 phút. `@EnableScheduling` bật xử lý annotation `@Scheduled`. Phương thức scheduled gọi launcher rồi trả về; phần công việc chạy trên `cleanupExecutor` nhờ `@Async`.

Khi công việc có thể kéo dài hơn chu kỳ, cần quyết định rõ có cho phép nhiều lần chạy chồng nhau hay không. Nếu không cho phép, hãy dùng lock, trạng thái job hoặc cơ chế điều phối phù hợp. Không nên dựa vào giả định scheduler sẽ tự chờ một `CompletableFuture` mà scheduled method đã bỏ qua.

Nếu kết quả hoặc lỗi async cần được theo dõi, launcher có thể ghi trạng thái job hoặc gắn callback `whenComplete(...)`. Hãy quy định rõ cách ghi nhận lỗi để một task thất bại không bị mất dấu chỉ vì scheduled method đã kết thúc.

## Kiểm thử scheduler mà không chờ đồng hồ thật

Test scheduler cần xác nhận hai điều: Spring đăng ký task theo cấu hình và khi runnable được kích hoạt, scheduled method gọi launcher. Không cần thực sự đợi 15 phút hoặc khởi động một executor chạy lịch liên tục.

Một cách kiểm soát là thay `TaskScheduler` bằng mock ghi lại runnable được đăng ký. Khi Spring xử lý `@Scheduled(cron = ...)`, nó gọi overload `schedule(Runnable, Trigger)`. Test có thể lưu runnable rồi gọi trực tiếp trong thời điểm do test quyết định.

Ví dụ test configuration:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ScheduledFuture;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.Trigger;
import org.springframework.scheduling.annotation.EnableScheduling;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CapturedScheduledTasks {
    private final List<Runnable> tasks = new CopyOnWriteArrayList<>();

    void add(Runnable task) {
        tasks.add(task);
    }

    List<Runnable> all() {
        return List.copyOf(tasks);
    }
}

@Configuration
@EnableScheduling
class SchedulerTestConfig {

    @Bean
    CapturedScheduledTasks capturedScheduledTasks() {
        return new CapturedScheduledTasks();
    }

    @Bean
    TaskScheduler taskScheduler(CapturedScheduledTasks captured) {
        TaskScheduler scheduler = mock(TaskScheduler.class);
        when(scheduler.schedule(any(Runnable.class), any(Trigger.class)))
                .thenAnswer(invocation -> {
                    captured.add(invocation.getArgument(0));
                    return mock(ScheduledFuture.class);
                });
        return scheduler;
    }

    @Bean
    AsyncCleanupLauncher cleanupLauncher() {
        return mock(AsyncCleanupLauncher.class);
    }

    @Bean
    CleanupSchedule cleanupSchedule(AsyncCleanupLauncher launcher) {
        return new CleanupSchedule(launcher);
    }
}
```

Test khởi tạo context, kiểm tra task đã được đăng ký, rồi gọi runnable bằng tay:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

@SpringJUnitConfig(SchedulerTestConfig.class)
@TestPropertySource(properties = "cleanup.cron=0 0 * * * *")
class CleanupScheduleTest {

    @Autowired
    private CapturedScheduledTasks captured;

    @Autowired
    private AsyncCleanupLauncher launcher;

    @Test
    void registeredTriggerDelegatesToAsyncLauncher() {
        assertThat(captured.all()).hasSize(1);

        captured.all().get(0).run();

        verify(launcher).launch();
    }
}
```

Test này không chạy business task thật vì launcher là mock. Nó chỉ xác nhận scheduled runnable được đăng ký và khi được kích hoạt sẽ gọi launcher. Đây chính là ranh giới cần kiểm tra ở lớp scheduler.

Trong ví dụ, mock `TaskScheduler` chỉ cần hỗ trợ overload cron `schedule(Runnable, Trigger)`. Nếu ứng dụng dùng `fixedRate`, `fixedDelay` hoặc một overload khác, hãy capture đúng phương thức `TaskScheduler` mà cấu hình đó sử dụng. Cũng cần bảo đảm context test chỉ có một scheduler được chọn để tránh Spring dùng scheduler khác.

## Kiểm tra biểu thức cron riêng

Nếu cần kiểm tra ý nghĩa biểu thức cron, kiểm tra nó như một quy tắc thời gian xác định, không chờ scheduler chạy. Spring cung cấp `CronExpression` để tính lần tiếp theo từ một thời điểm đã biết:

```java
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronExpression;

import static org.assertj.core.api.Assertions.assertThat;

class CleanupCronExpressionTest {

    @Test
    void calculatesNextQuarterHour() {
        CronExpression cron = CronExpression.parse("0 0/15 * * * *");
        ZonedDateTime after = ZonedDateTime.parse("2030-01-01T10:07:00Z");

        assertThat(cron.next(after))
                .isEqualTo(ZonedDateTime.parse("2030-01-01T10:15:00Z"));
    }
}
```

Test này kiểm tra phép tính của biểu thức cron với mốc thời gian cố định. Nếu annotation `@Scheduled` có thuộc tính `zone`, hãy dùng `ZonedDateTime` trong đúng timezone đó để xác nhận hành vi quanh ranh giới ngày, tháng hoặc giờ mùa hè. Cron expression và việc đăng ký runnable là hai thứ khác nhau; có thể kiểm tra chúng riêng.

## Phân biệt fixedRate, fixedDelay và cron

Các chế độ scheduling không mang cùng ý nghĩa:

| Cấu hình | Cách tính lần kích hoạt tiếp theo | Dùng khi |
|---|---|---|
| `fixedRate` | Theo khoảng cách giữa thời điểm bắt đầu các lần chạy | Muốn nhịp kích hoạt đều |
| `fixedDelay` | Tính khoảng chờ sau khi lần chạy trước kết thúc | Muốn chờ một khoảng sau khi hoàn tất |
| `cron` | Theo biểu thức lịch ngày/giờ | Muốn chạy theo mốc thời gian cụ thể |

Với `@Async` launcher, scheduled method có thể kết thúc ngay sau khi gửi task sang executor. Khi đó `fixedDelay` trên scheduled method đo khoảng thời gian sau khi phương thức trigger kết thúc, không phải sau khi async business task hoàn tất. Nếu yêu cầu là chờ công việc thực tế xong rồi mới tính delay, phải điều phối future hoặc trạng thái job một cách rõ ràng.

## Không gộp async và scheduler vào một test thời gian thực

Một test tích hợp có thể bật cả `@EnableAsync` và `@EnableScheduling`, nhưng không nên để phần lớn test suite phụ thuộc vào lịch thực. Một bài test chờ cron kích hoạt rồi xác nhận repository được cập nhật có thể thất bại vì:

- Test bắt đầu ngay sau thời điểm cron đã trôi qua và phải chờ chu kỳ tiếp theo.
- CI chậm hoặc thread pool bận khiến task không hoàn tất trước timeout.
- Task được kích hoạt nhiều lần và test không xác định lần nào tạo side effect.
- Test context được cache hoặc giữ scheduler sống lâu hơn vòng đời test method.
- Một lỗi trong business task bị nhầm với lỗi lịch không kích hoạt, hoặc ngược lại.

Nếu cần một smoke test end-to-end cho toàn bộ luồng, hãy dùng lịch test ngắn nhưng vẫn kiểm soát executor, có timeout hữu hạn, chờ một tín hiệu hoàn tất cụ thể và dọn context sau test. Đây nên là một số ít integration test bổ sung; phần lớn logic nên được kiểm tra ở các test độc lập phía trên.

## Tránh các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@Async` chạy đồng bộ | Chưa bật `@EnableAsync`, gọi qua self-invocation hoặc gọi object tự tạo thay vì Spring bean | Bật async support và gọi qua proxy được inject |
| Test kết thúc trước khi async task xong | Không chờ future/latch | Dùng `Future#get(timeout)` hoặc `CountDownLatch#await(timeout, ...)` |
| Test lúc pass lúc fail | Dùng `Thread.sleep()` hoặc dựa vào lịch thật | Điều khiển executor/scheduler và chờ tín hiệu có timeout |
| Scheduled method chạy nhưng business task chưa xong | Method chỉ gửi việc sang executor rồi trả về | Chờ future trong test async riêng; theo dõi completion trong production nếu cần |
| Scheduled task không được capture | Test mock sai overload `TaskScheduler` | Capture overload phù hợp với cron, fixed rate hoặc fixed delay |
| Nhiều lần chạy chồng nhau | Thời gian task dài hơn chu kỳ kích hoạt | Dùng lock, trạng thái job hoặc chính sách chống chạy trùng |
| Exception async bị mất | Phương thức trả `void` hoặc future bị bỏ qua | Trả `CompletableFuture`, quan sát completion hoặc cấu hình async exception handler |
| Executor thread còn chạy sau test | Executor không được đóng khi context kết thúc | Dùng bean Spring có lifecycle shutdown và cấu hình await termination phù hợp |
| `fixedDelay` không đợi async job hoàn tất | Scheduled method trả về ngay sau khi gửi task | Điều phối future hoặc dùng một mô hình chạy đồng bộ nếu delay phải tính sau business completion |

## Ma trận test nên có

| Test | Đối tượng kiểm tra | Điều không cần chạy |
|---|---|---|
| Business service test | Quy tắc nghiệp vụ, repository calls, transaction behavior | Async executor và scheduler |
| Async launcher test | Proxy `@Async`, executor, kết quả và exception | Cron hoặc thời gian kích hoạt |
| Scheduler registration test | `@Scheduled` được đăng ký và runnable gọi launcher | Repository và business task thật |
| Cron expression test | Lần kích hoạt tiếp theo từ mốc thời gian cố định | Thread pool và đồng hồ thực |
| Một smoke integration test (nếu cần) | Kết nối các thành phần trong context thật | Không nên thay thế các test độc lập ở trên |

Khi business task, async execution và schedule trigger có ranh giới rõ, mỗi test có thể điều khiển đúng điều kiện cần thiết. Business test chạy nhanh và xác định; async test chờ completion bằng future hoặc latch; scheduler test kích hoạt runnable theo ý muốn mà không phải chờ thời gian thực. Điều đó giúp lỗi được định vị đúng lớp và giảm sự phụ thuộc của test suite vào đồng hồ, thread pool và tốc độ của môi trường CI.
