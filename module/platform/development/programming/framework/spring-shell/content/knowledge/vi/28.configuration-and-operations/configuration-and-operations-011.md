# Phát hiện luồng nền khiến tiến trình không thoát

Một command Spring Shell có thể chạy xong, in kết quả và trả quyền điều khiển về runner, nhưng cửa sổ terminal vẫn không kết thúc. Trong script hoặc CI, job có thể tiếp tục ở trạng thái running dù không còn công việc nào mà người dùng nhìn thấy. Một nguyên nhân phổ biến là ứng dụng còn **thread nền không phải daemon** đang sống.

Với ứng dụng Spring Boot, các thread đó có thể đến từ **@Scheduled**, **@Async**, executor tự tạo, timer, message listener, client nền hoặc một thread được khởi chạy thủ công. Cách xử lý đúng là tìm thread còn sống, xác định bean hoặc thư viện tạo ra nó, rồi đóng tài nguyên theo vòng đời ứng dụng.

Bài này hướng dẫn chẩn đoán bằng thread dump, nhận diện các nguồn thread thường gặp trong Spring, cấu hình đóng ApplicationContext sau khi command hoàn tất và bảo đảm executor/thread được dừng có trật tự. Nội dung tập trung vào Spring Shell 4, Spring Boot 4 và Java 21 trở lên.

## 1. Vì sao command xong nhưng JVM vẫn chạy?

Trong một ứng dụng Spring Shell chạy non-interactive, command có thể hoàn tất rất nhanh. Tuy nhiên, JVM chỉ bắt đầu shutdown tự động khi tất cả thread non-daemon đã kết thúc. Một thread đang chờ công việc tiếp theo vẫn là thread đang sống; nó có thể ở trạng thái WAITING hoặc TIMED_WAITING mà không tiêu thụ CPU nhưng vẫn giữ tiến trình hoạt động.

Ví dụ:

~~~java
public class BackgroundThreadExample {

    public static void main(String[] args) {
        System.out.println("Command đã hoàn tất.");

        Thread worker = new Thread(() -> {
            while (true) {
                try {
                    Thread.sleep(60_000);
                }
                catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }
        }, "background-worker");

        worker.start();
    }
}
~~~

Sau khi main method kết thúc, thread **background-worker** vẫn đang chạy. Thread được tạo mặc định kế thừa trạng thái daemon từ thread tạo ra nó; main thường là non-daemon, nên worker trong ví dụ cũng là non-daemon. JVM chưa thể tự kết thúc.

Điều này khác với một command chạy lâu do đang thực hiện nghiệp vụ. Khi command đã in kết quả cuối cùng mà process vẫn còn sống, hãy kiểm tra thread thay vì chỉ nhìn CPU usage hoặc output.

## 2. Daemon và non-daemon thread

Java phân biệt hai loại platform thread:

| Loại | Ảnh hưởng đến JVM shutdown |
|---|---|
| Non-daemon | JVM chờ thread kết thúc trước khi bắt đầu shutdown tự động |
| Daemon | Không giữ JVM sống; có thể bị dừng khi JVM kết thúc |

Main thread thường là non-daemon. Các thread được tạo từ main bằng constructor Thread thường kế thừa thuộc tính daemon của thread tạo ra chúng. Thread pool tạo qua các factory mặc định của Java thường cũng sử dụng worker non-daemon.

Ví dụ tạo platform thread daemon:

~~~java
Thread background = Thread.ofPlatform()
        .name("optional-metrics")
        .daemon(true)
        .start(this::collectMetrics);
~~~

Thread daemon phù hợp với công việc phụ có thể bị bỏ dở khi JVM thoát, chẳng hạn một số tác vụ telemetry hoặc cache refresh không bắt buộc. Không biến mọi worker thành daemon chỉ để process thoát nhanh. Nếu thread đang ghi dữ liệu, gửi giao dịch, xử lý file hoặc hoàn tất một nghiệp vụ quan trọng, việc JVM kết thúc có thể làm công việc bị cắt giữa chừng.

**Virtual thread** được Java đánh dấu là daemon. Chúng không tự giữ JVM sống. Tuy nhiên, điều đó không thay thế việc quản lý tác vụ: virtual thread có thể bị dừng khi JVM thoát và không bảo đảm một công việc quan trọng đã hoàn tất.

## 3. Phân biệt Spring Shell REPL và command chạy một lần

Spring Shell có hai cách chạy khác nhau:

- **Interactive mode:** ứng dụng mở REPL để người dùng tiếp tục nhập nhiều command. Process cần sống cho đến khi người dùng thoát.
- **Non-interactive mode:** ứng dụng chạy command từ đối số hoặc script rồi kết thúc. Đây là chế độ thường dùng trong Bash, PowerShell, CI và scheduler.

Trong Spring Shell 4, interactive mode được bật mặc định, kể cả khi khởi chạy kèm command-line arguments. Để chạy command từ process arguments, đặt:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Khi đó Spring Shell dùng **NonInteractiveShellRunner**. Command hoàn tất chưa chắc đã làm JVM thoát: các thread non-daemon khác vẫn có thể giữ tiến trình sống.

Nếu mục tiêu là một CLI chạy một lần rồi đóng toàn bộ Spring context, Spring Shell cung cấp thuộc tính **spring.shell.context.close**. Đây là cơ chế cần kiểm tra trước khi tự viết shutdown logic.

## 4. Dùng spring.shell.context.close cho command chạy một lần

Spring Shell có thể yêu cầu đóng **ApplicationContext** sau khi shell hoàn tất phần thực thi. Cấu hình:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
    context:
      close: true
~~~

Thuộc tính **spring.shell.context.close** đăng ký listener cho **ApplicationReadyEvent** và yêu cầu đóng context sau khi shell hoàn tất. Tùy chọn này không bật mặc định.

Khi context đóng, Spring gọi các lifecycle callback của bean được quản lý: executor, scheduler, connection pool, client hoặc component có phương thức destroy. Đây là cách phù hợp cho CLI one-shot có các bean nền được Spring quản lý đúng vòng đời.

Ví dụ cấu hình cho ứng dụng chỉ thực hiện một command:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
    context:
      close: true
~~~

Không bật tùy chọn này nếu ứng dụng cần giữ REPL hoặc tiếp tục phục vụ một tác vụ nền sau khi command đầu tiên kết thúc. Với ứng dụng interactive, context chỉ nên đóng sau khi phiên shell kết thúc theo ý người dùng.

Lưu ý: đóng ApplicationContext không tự động dừng một thread được tạo thủ công rồi bỏ tham chiếu, hoặc một executor không được đăng ký làm Spring bean. Những tài nguyên đó vẫn cần cơ chế stop riêng.

## 5. Tìm thread đang giữ tiến trình bằng jcmd

Đừng đoán tên bean hoặc thêm lệnh đóng thread trước khi biết thread nào còn sống. Lấy thread dump của process đang bị giữ:

~~~bash
jcmd -l
~~~

Lệnh liệt kê các JVM process mà công cụ có thể quan sát. Chọn PID của ứng dụng Spring Shell, rồi in stack trace của tất cả thread:

~~~bash
jcmd 18420 Thread.print
~~~

Muốn có thêm thông tin về lock:

~~~bash
jcmd 18420 Thread.print -l
~~~

Thay **18420** bằng PID thực tế. Trên Windows có thể chạy **jcmd.exe**; trên Linux/macOS thường dùng **jcmd**. Công cụ phải chạy trên cùng máy và thường cần cùng user/group hiệu lực với tiến trình đích.

JDK khuyến nghị dùng **jcmd** để chẩn đoán thay vì dựa vào các công cụ cũ như **jstack**. Thread dump chứa tên thread, trạng thái, stack frame và thông tin lock; đây là dữ liệu đầu tiên cần xem khi process không thoát.

## 6. Đọc thread dump để tìm nguồn gốc

Khi đọc thread dump, tập trung vào các thread do ứng dụng hoặc thư viện tạo:

| Dấu hiệu trong thread dump | Nguồn có thể liên quan | Điều cần kiểm tra |
|---|---|---|
| **pool-1-thread-1**, **pool-2-thread-1** | ExecutorService tạo bằng Executors | Executor có được shutdown không? |
| **task-1**, **task-2** hoặc prefix tự đặt | ThreadPoolTaskExecutor | Bean executor có được Spring quản lý và destroy không? |
| **scheduling-1** | ThreadPoolTaskScheduler | Có @Scheduled hoặc scheduler chạy định kỳ không? |
| **Timer-0** | java.util.Timer | Timer có được cancel không? |
| **Thread-0**, **Thread-1** | Thread tự tạo hoặc thư viện | Stack trace cho biết code nào tạo hoặc đang chạy? |
| **SimpleAsyncTaskExecutor-...** | Spring SimpleAsyncTaskExecutor | Tác vụ có đang chờ, bị chặn hoặc không kết thúc? |
| Tên thread của client/listener | Kafka, AMQP, HTTP client hoặc SDK | Listener/client có stop/close trong lifecycle không? |
| Thread đang ở shutdown hook | Hook do ứng dụng hoặc thư viện đăng ký | Hook có block hoặc chờ vô hạn không? |

Một thread ở trạng thái **WAITING**, **TIMED_WAITING** hoặc **PARKED** không nhất thiết là lỗi. Worker nhàn rỗi trong thread pool thường chờ task mới. Nếu worker đó là non-daemon và executor chưa shutdown, nó vẫn giữ JVM sống.

Ví dụ stack của worker nhàn rỗi có thể đi qua **ThreadPoolExecutor.getTask()** hoặc **LinkedBlockingQueue.take()**. Scheduler chờ tác vụ kế tiếp có thể nằm trong **ScheduledThreadPoolExecutor$DelayedWorkQueue.take()**. Timer có thể nằm trong **TimerThread.mainLoop()**.

Không kết luận chỉ từ tên thread. Đọc stack frame để xác định lớp hoặc thư viện đang sở hữu luồng. Chụp hai thread dump cách nhau vài giây nếu cần phân biệt thread đang tiến triển với thread bị kẹt. Nếu thread ở RUNNABLE, BLOCKED hoặc WAITING trên I/O, xem các frame và lock liên quan trước khi quyết định cách dừng.

## 7. Nhận diện các nguồn thread thường gặp trong Spring

Các tính năng sau có thể tạo hoặc sử dụng thread nền:

| Cơ chế | Tác động |
|---|---|
| **@EnableScheduling** và **@Scheduled** | Đăng ký tác vụ chạy theo lịch và scheduler |
| **@EnableAsync** và **@Async** | Gửi method sang executor |
| **ThreadPoolTaskExecutor** | Duy trì worker thread để xử lý task |
| **ThreadPoolTaskScheduler** | Duy trì scheduler thread cho tác vụ định kỳ |
| **Executors.newSingleThreadExecutor()** | Tạo executor với worker riêng |
| **Executors.newScheduledThreadPool()** | Tạo scheduler worker cho tác vụ hẹn giờ |
| **new Thread(...).start()** | Tạo thread thủ công |
| **new Timer()** | Tạo Timer thread |
| Message listener hoặc client nền | Có thể mở consumer, heartbeat, reconnect hoặc polling thread |
| Shutdown hook | Có thể làm JVM tiếp tục shutdown sequence cho đến khi hook kết thúc |

Trong ứng dụng CLI chạy một lần, kiểm tra xem có thật sự cần bật scheduling, async listener hoặc client nền hay không. Một bean được copy từ ứng dụng server có thể bật các tác vụ định kỳ không cần thiết cho command line.

## 8. @Scheduled có thể giữ Spring Shell process sống

Ví dụ ứng dụng bật scheduling:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class TaskCliApplication {
}
~~~

Một bean có tác vụ định kỳ:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class HousekeepingTasks {

    @Scheduled(fixedDelay = 60_000)
    public void cleanup() {
        // Dọn dữ liệu tạm theo lịch.
    }
}
~~~

Scheduler có thể tiếp tục chờ lần chạy tiếp theo sau khi command non-interactive hoàn tất. Nếu ứng dụng không cần tác vụ định kỳ, bỏ **@EnableScheduling** hoặc điều kiện hóa bean để nó chỉ được tạo trong ứng dụng server.

Nếu scheduler là yêu cầu thật của ứng dụng, cần xác định CLI có phải là process dài hạn hay không. Một command chạy một lần và một daemon xử lý tác vụ định kỳ là hai kiểu triển khai khác nhau; không nên giữ một CLI one-shot sống chỉ vì một scheduler vô tình được khởi tạo.

## 9. @Async và executor cần được quản lý

Spring Boot auto-configure một **AsyncTaskExecutor** nếu context chưa có executor phù hợp. Khi virtual thread không được bật, executor mặc định thường là **ThreadPoolTaskExecutor**. Khi bật virtual thread trên Java 21 trở lên, Boot có thể dùng **SimpleAsyncTaskExecutor** với virtual thread.

Ví dụ:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async
    public void generateReport() {
        // Xử lý báo cáo nền.
    }
}
~~~

Để bật xử lý bất đồng bộ bằng annotation, ứng dụng cần bật **@EnableAsync** trên một lớp cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Nếu command gọi **generateReport()** rồi trả về ngay, command đã hoàn tất nhưng task nền có thể vẫn đang chạy. Cần quyết định rõ:

- CLI phải chờ report hoàn tất trước khi thoát.
- CLI chỉ gửi yêu cầu và trả về mã job, còn worker dài hạn xử lý ở process khác.
- CLI cho phép bỏ dở task khi shutdown.

Không để task chạy nền không có hợp đồng về hoàn tất, retry và shutdown. Nếu kết quả cần được command trả về, dùng **Future** hoặc **CompletableFuture** và chờ có giới hạn thời gian thay vì fire-and-forget.

## 10. Cấu hình shutdown cho executor và scheduler của Spring Boot

Spring Boot cung cấp thuộc tính để executor chờ các task đang chạy khi context đóng:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
    context:
      close: true
  task:
    execution:
      shutdown:
        await-termination: true
        await-termination-period: 20s
    scheduling:
      shutdown:
        await-termination: true
        await-termination-period: 20s
~~~

Ý nghĩa:

- **spring.shell.context.close:** yêu cầu đóng Spring context sau khi shell hoàn tất.
- **spring.task.execution.shutdown.await-termination:** yêu cầu executor chờ task đang chạy khi shutdown.
- **spring.task.execution.shutdown.await-termination-period:** thời gian tối đa executor chờ.
- **spring.task.scheduling.shutdown.await-termination:** yêu cầu scheduler chờ task đang chạy khi shutdown.
- **spring.task.scheduling.shutdown.await-termination-period:** thời gian tối đa scheduler chờ.

Các thuộc tính await-termination chỉ có tác dụng sau khi executor/scheduler nhận tín hiệu shutdown. Chúng không tự dừng một thread thủ công hoặc executor không được Spring quản lý. Nếu task không phản hồi interruption hoặc không kết thúc trong giới hạn, shutdown có thể vẫn kéo dài.

Khi **spring.threads.virtual.enabled=true** trên Java 21 trở lên, Spring Boot có thể dùng **SimpleAsyncTaskScheduler** cho scheduled task thay cho thread pool scheduler. Virtual thread là daemon, nhưng tác vụ vẫn cần được thiết kế để hoàn tất hoặc hủy đúng cách khi context đóng.

Không đặt timeout quá dài chỉ để che một task bị treo. Chọn giới hạn phù hợp với nghiệp vụ, ghi log khi task chưa hoàn tất và có chính sách hủy hoặc phục hồi.

## 11. Quản lý ThreadPoolTaskExecutor do ứng dụng tạo

Nếu cần executor riêng, khai báo nó thành Spring bean để container gọi lifecycle callback khi đóng context:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BackgroundExecutionConfiguration {

    @Bean
    ThreadPoolTaskExecutor backgroundExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("cli-background-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

**ThreadPoolTaskExecutor** tích hợp với Spring lifecycle và được container khởi tạo, shutdown khi bean bị hủy. Không tạo executor trong method command rồi bỏ tham chiếu; nếu làm vậy, Spring không thể quản lý vòng đời của executor đó.

Nếu executor chỉ phục vụ một command, cân nhắc dùng task đồng bộ thay vì mở pool. Nếu executor phục vụ nhiều command trong REPL, giữ nó ở cấp bean và đóng khi shell/application context kết thúc.

## 12. Quản lý ScheduledExecutorService thuần

Nếu cần API **ScheduledExecutorService** trực tiếp, đăng ký executor thành bean và chỉ rõ phương thức shutdown:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NativeSchedulerConfiguration {

    @Bean(destroyMethod = "shutdown")
    ScheduledExecutorService maintenanceScheduler() {
        return Executors.newSingleThreadScheduledExecutor();
    }
}
~~~

Spring gọi **shutdown()** khi hủy bean. Với executor tạo thủ công ngoài Spring context, code sở hữu nó phải gọi **shutdown()**, chờ có giới hạn bằng **awaitTermination()**, rồi mới gọi **shutdownNow()** nếu cần hủy task còn lại.

Ví dụ quy trình đóng:

~~~java
import java.util.concurrent.TimeUnit;

executor.shutdown();
try {
    if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
}
catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

Không gọi shutdown từ từng command nếu executor là singleton được dùng chung. Việc đóng executor phải thuộc thành phần sở hữu vòng đời của nó.

## 13. Dừng thread tự tạo bằng lifecycle callback

Nếu thật sự cần một platform thread thủ công, lưu tham chiếu và cung cấp cách yêu cầu dừng. Không viết vòng lặp vô hạn mà không có cờ dừng hoặc cơ chế interruption.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class PollingWorker {

    private final AtomicBoolean running = new AtomicBoolean();
    private volatile Thread worker;

    @PostConstruct
    public void start() {
        running.set(true);
        worker = Thread.ofPlatform()
                .name("polling-worker")
                .start(() -> {
                    while (running.get()) {
                        try {
                            pollOnce();
                            Thread.sleep(1_000);
                        }
                        catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            break;
                        }
                    }
                });
    }

    private void pollOnce() {
        // Đọc một lượng dữ liệu hữu hạn hoặc kiểm tra một trạng thái.
    }

    @PreDestroy
    public void stop() {
        running.set(false);
        Thread current = worker;
        if (current != null) {
            current.interrupt();
            try {
                current.join(5_000);
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

Khi context đóng, **@PreDestroy** yêu cầu worker dừng, gửi interrupt và chờ tối đa năm giây. Vòng lặp phải kiểm tra cờ hoặc phản hồi interrupt để kết thúc.

Nếu **pollOnce()** bị block trong một API không hỗ trợ interruption, thread có thể vẫn sống sau khi join timeout. Khi đó cần timeout ở API I/O, đóng socket/stream đang block hoặc dùng một cơ chế hủy phù hợp với tài nguyên. Không thể bảo đảm dừng một thread Java tùy ý bằng cách gọi một phương thức cưỡng bức an toàn.

## 14. Không nuốt InterruptedException

Khi shutdown executor, Spring hoặc Java có thể gửi interruption để yêu cầu task kết thúc. Nếu code bắt **InterruptedException** rồi bỏ qua, thread có thể tiếp tục chạy và khiến process không thoát.

Mẫu sai:

~~~java
try {
    Thread.sleep(1_000);
}
catch (InterruptedException ex) {
    // Bỏ qua interruption.
}
~~~

Mẫu đúng khi không thể ném exception lên caller:

~~~java
try {
    Thread.sleep(1_000);
}
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Nếu task có vòng lặp dài, kiểm tra **Thread.currentThread().isInterrupted()** giữa các đơn vị công việc. Với I/O, đặt timeout và đóng resource để việc chờ có thể kết thúc. Không dùng vòng lặp bận để chờ cờ dừng vì cách đó tiêu thụ CPU và không giải quyết được I/O đang block.

## 15. Shutdown hook cũng có thể làm JVM không kết thúc

Khi JVM bắt đầu shutdown, các shutdown hook đã đăng ký được chạy đồng thời. JVM chờ tất cả hook kết thúc trước khi hoàn tất shutdown sequence. Một hook bị treo, chờ vô hạn hoặc deadlock có thể làm process tiếp tục tồn tại.

Ví dụ hook không nên dùng:

~~~java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    while (true) {
        // Không có điều kiện kết thúc.
    }
}));
~~~

Nếu cần cleanup tùy chỉnh, ưu tiên lifecycle của Spring bean như **@PreDestroy**, **DisposableBean** hoặc **SmartLifecycle**. Nếu phải dùng shutdown hook cho một tài nguyên ngoài Spring, hook cần hoàn tất trong thời gian hữu hạn và không phụ thuộc vào một bean đã bị hủy trước đó.

Không gọi **Runtime.halt()** để ép process dừng. Halt bỏ qua shutdown hook, finally block và cleanup resource. **System.exit()** khởi động shutdown sequence nhưng cũng không sửa được một hook đang treo; nó không thay thế thiết kế lifecycle đúng.

## 16. Phân biệt thread còn sống với JVM shutdown hook

Có hai giai đoạn khác nhau:

1. **Trước shutdown:** JVM chưa bắt đầu shutdown vì còn non-daemon thread đang sống.
2. **Trong shutdown:** JVM đã bắt đầu chạy shutdown hook nhưng một hook chưa kết thúc.

Thread dump giúp phân biệt hai trường hợp. Nếu thread worker hoặc scheduler vẫn đang chạy và JVM chưa vào shutdown sequence, hãy kiểm tra executor/thread owner. Nếu stack cho thấy shutdown hook đang block trong destroy method, kiểm tra bean cleanup, network close, executor await termination hoặc hook tùy chỉnh.

Không nhầm thread nội bộ của JVM với thread ứng dụng. Thread dump có nhiều thread daemon phục vụ GC, compiler, reference processing và runtime; sự hiện diện của chúng không tự chứng minh nguyên nhân process bị giữ.

## 17. Quy trình chẩn đoán từng bước

Khi một command non-interactive đã in kết quả nhưng process vẫn sống, thực hiện theo trình tự:

1. **Xác nhận chế độ chạy:** kiểm tra **spring.shell.interactive.enabled=false** nếu đây là command chạy một lần.
2. **Chờ có giới hạn:** xác định command đã hoàn tất hay còn task được thiết kế chạy nền.
3. **Lấy PID:** dùng **jcmd -l** hoặc công cụ quản lý process của hệ điều hành.
4. **Lấy thread dump:** chạy **jcmd PID Thread.print -l**.
5. **Tìm thread ứng dụng non-daemon:** lọc tên thread, trạng thái và stack frame của executor, scheduler, timer, client hoặc thread tự tạo.
6. **Đối chiếu bean:** tìm **@EnableScheduling**, **@Scheduled**, **@EnableAsync**, **@Async**, ExecutorService, Timer, new Thread và client listener trong cấu hình ứng dụng.
7. **Xác định owner:** thread thuộc bean Spring, thư viện bên thứ ba hay code tự tạo?
8. **Kiểm tra lifecycle:** bean có destroy callback không? Context có thực sự đóng sau command không?
9. **Sửa nơi tạo thread:** bỏ tác vụ không cần thiết hoặc quản lý executor/thread bằng Spring lifecycle.
10. **Kiểm thử process thật:** chạy JAR non-interactive trong tiến trình riêng và xác nhận nó kết thúc trong timeout.

Nếu thread dump không rõ, chụp thêm một dump sau vài giây và so sánh stack. Thread đang chờ queue có thể chỉ là worker idle; thread mắc ở I/O hoặc lock có thể cần kiểm tra dependency bên ngoài hoặc deadlock.

## 18. Kiểm thử rằng CLI thực sự thoát

Unit test cho command không chứng minh JVM sẽ thoát. Cần một integration test khởi chạy artifact hoặc ứng dụng trong process riêng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.fail;

import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

class CliProcessLifecycleTests {

    @Test
    void oneShotCommandTerminatesAfterCompletion() throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase()
                .contains("win");
        Path java = Path.of(
                System.getProperty("java.home"),
                "bin",
                windows ? "java.exe" : "java"
        );
        Path jar = Path.of(System.getProperty("app.jar"))
                .toAbsolutePath();

        Process process = new ProcessBuilder(
                java.toString(),
                "-Dspring.shell.interactive.enabled=false",
                "-Dspring.shell.context.close=true",
                "-jar",
                jar.toString(),
                "task",
                "list"
        )
                .redirectErrorStream(true)
                .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                .start();

        if (!process.waitFor(20, TimeUnit.SECONDS)) {
            process.destroy();
            if (!process.waitFor(2, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor();
            }
            fail("CLI không thoát sau khi command hoàn tất.");
        }

        assertThat(process.exitValue()).isZero();
    }
}
~~~

Test giả định JAR đã được build và system property **app.jar** trỏ đến đúng artifact. Dùng một process riêng để kiểm tra thời gian kết thúc và exit code. Redirect output để test không bị pipe buffer đầy khi chỉ quan tâm đến lifecycle.

Nên có thêm các ca:

| Ca kiểm thử | Kết quả cần xác nhận |
|---|---|
| Command đồng bộ không có task nền | Process thoát sau khi command hoàn tất |
| Có executor Spring-managed | Executor nhận shutdown khi context đóng |
| Có @Scheduled không cần thiết | Không còn scheduler thread sau khi command kết thúc |
| Có task @Async đang chạy | Task hoàn tất trong timeout hoặc được hủy theo chính sách |
| Có raw ExecutorService bean | destroy method gọi shutdown |
| Có thread thủ công | @PreDestroy dừng và join worker |
| Task bị interrupt | Task phản hồi interruption và kết thúc |
| Shutdown hook | Hook hoàn tất trong giới hạn |
| Task bị block I/O | Timeout hoặc close resource giải phóng task |
| Interactive REPL | Process vẫn sống cho đến khi người dùng thoát |

Không chỉ assert rằng command đã in "Done". Điều kiện acceptance là process đã kết thúc, không còn thread giữ JVM và mã thoát phù hợp.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Command xong nhưng process không thoát | Còn non-daemon thread | Lấy thread dump và tìm owner |
| Có thread **scheduling-1** | @Scheduled hoặc scheduler bean vẫn hoạt động | Bỏ scheduling không cần hoặc đóng context |
| Có thread **pool-1-thread-1** | ExecutorService chưa shutdown | Đăng ký executor làm bean và cấu hình destroy |
| Có thread **Thread-0** | Thread thủ công không có điều kiện dừng | Giữ tham chiếu, gửi interrupt và join |
| Context đã đóng nhưng process còn sống | Thread không thuộc lifecycle Spring | Quản lý trực tiếp hoặc sửa thư viện tạo thread |
| Task không dừng sau shutdown | Nuốt InterruptedException hoặc I/O không timeout | Phản hồi interrupt và đóng resource |
| Shutdown chờ quá lâu | await-termination quá dài hoặc task không kết thúc | Đặt timeout hợp lý và ghi log task còn lại |
| Tắt hết background thread làm mất dữ liệu | Chuyển worker quan trọng thành daemon | Dùng graceful shutdown và chờ có giới hạn |
| Có thread dump nhưng không biết thread nào quan trọng | Chỉ nhìn tên hoặc trạng thái | Đọc stack frame và kiểm tra daemon/non-daemon |
| Process ở shutdown sequence mãi | Shutdown hook hoặc bean destroy bị block | Kiểm tra hook và callback cleanup |
| Interactive shell bị đóng sau command đầu tiên | Bật spring.shell.context.close trong REPL | Chỉ bật cho one-shot CLI |
| Process test bị treo | Test không đặt timeout hoặc JAR vẫn chạy interactive | Tắt interactive và dùng waitFor(timeout) |

## 20. Checklist vận hành

- [ ] Đã xác định ứng dụng là interactive REPL hay one-shot command.
- [ ] One-shot command đã tắt interactive mode.
- [ ] Đã cân nhắc **spring.shell.context.close=true** nếu context cần đóng sau shell.
- [ ] Không bật **@EnableScheduling** hoặc **@EnableAsync** nếu command không cần.
- [ ] Executor và scheduler được đăng ký làm Spring bean.
- [ ] Executor thuần có destroy method gọi shutdown.
- [ ] Thread thủ công có cờ dừng, interruption và giới hạn thời gian join.
- [ ] Task không nuốt **InterruptedException**.
- [ ] I/O nền có timeout hoặc cách đóng resource để dừng.
- [ ] Shutdown hook kết thúc trong thời gian hữu hạn.
- [ ] Không dùng daemon flag để che giấu worker bị rò rỉ.
- [ ] Đã lấy thread dump bằng **jcmd** khi process không thoát.
- [ ] Đã kiểm tra cả thread non-daemon và shutdown hook.
- [ ] Đã kiểm thử process thật với timeout và exit code.
- [ ] Đã kiểm tra task quan trọng hoàn tất hoặc được hủy theo chính sách.

Trong Spring Shell, việc command hoàn tất và việc JVM kết thúc là hai sự kiện riêng. Khi CLI chạy một lần, hãy để shell hoàn thành, đóng ApplicationContext, shutdown executor và dừng thread tự tạo theo lifecycle. Khi process vẫn sống, dùng thread dump để tìm đúng owner trước khi sửa. Một shutdown có trật tự vừa giải phóng tài nguyên, vừa bảo đảm công việc quan trọng không bị cắt bỏ chỉ để làm terminal đóng nhanh hơn.

## Tài liệu tham khảo

- [Spring Shell — Context Close](https://docs.spring.io/spring-shell/reference/customization/contextclose.html) — thuộc tính spring.shell.context.close và lý do thread nền có thể giữ process sống sau khi shell hoàn tất.
- [Spring Shell 4 — Execution](https://docs.spring.io/spring-shell/reference/execution.html) — interactive/non-interactive mode và ShellRunner.
- [Spring Boot 4 — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html) — auto-configuration cho executor, scheduler, @Async và @Scheduled.
- [Spring Boot 4 — Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html) — thuộc tính shutdown cho task execution và task scheduling.
- [Spring Framework 7 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — TaskExecutor, TaskScheduler, ThreadPoolTaskExecutor, ThreadPoolTaskScheduler và lifecycle.
- [Spring Framework 7 API — ExecutorConfigurationSupport](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html) — shutdown, waitForTasksToCompleteOnShutdown và awaitTermination.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html) — daemon/non-daemon thread, virtual thread và quy tắc JVM shutdown.
- [Java SE 21 — Runtime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html) — shutdown sequence và shutdown hook.
- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html) — shutdown, shutdownNow, awaitTermination và lifecycle executor.
- [Java SE 21 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html) — jcmd, Thread.print và thread dump.
