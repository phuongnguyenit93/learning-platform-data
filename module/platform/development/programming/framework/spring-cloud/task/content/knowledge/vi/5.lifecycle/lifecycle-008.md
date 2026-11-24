# Tín hiệu dừng, luồng nền và giới hạn hoàn tất khi JVM bị ngắt

## 1. Vì sao “tiến trình đã dừng” không đồng nghĩa “tác vụ đã hoàn tất”?

Trong **Spring Cloud Task**, mỗi lần khởi chạy ứng dụng Spring Boot thường đại diện cho một công việc có thời gian hữu hạn: nhập file, đồng bộ dữ liệu, xuất báo cáo, đối soát giao dịch hoặc chạy một Spring Batch Job. **TaskRepository** lưu metadata như thời điểm bắt đầu/kết thúc, tên task, mã thoát và thông tin liên quan tới một **TaskExecution**. Tuy nhiên, khi JVM bị ngắt, có thể tồn tại ba trạng thái khác nhau:

- **Trạng thái tiến trình:** JVM còn chạy, đã thoát với mã nào, hay bị hệ điều hành/container cưỡng bức kết thúc.
- **Trạng thái metadata:** TaskExecution đã có `END_TIME` và thông tin kết thúc hay vẫn ở trạng thái chưa chốt trong CSDL.
- **Trạng thái nghiệp vụ:** Báo cáo đã ghi đủ, giao dịch đã commit, message đã được xác nhận, các luồng con đã xử lý hết hay chưa.

Ba trạng thái này **không tự đồng bộ tuyệt đối** với nhau. Một tiến trình có thể bị dừng sau khi đã commit toàn bộ dữ liệu nhưng trước khi ghi metadata kết thúc. Ngược lại, một runner có thể trở về bình thường trong khi tác vụ nền vẫn đang chạy, khiến ứng dụng báo hoàn tất sớm nếu không chờ chúng.

Xét ví dụ: task xuất báo cáo gồm 20 phân vùng, mỗi phân vùng mất vài giây. Khi phân vùng thứ 12 đang chạy, Kubernetes yêu cầu dừng Pod vì rollout hoặc xóa Job. Nếu JVM nhận tín hiệu dừng, liệu nó có lưu được phần kết quả đã hoàn thành, ghi trạng thái task, báo lỗi cho hệ điều phối và thoát an toàn? Câu trả lời phụ thuộc **loại tín hiệu**, **cách xử lý luồng**, **thời gian cho phép dừng** và **thiết kế idempotency/checkpoint**.

Mục tiêu học tập của bài này là hiểu chính xác ranh giới của graceful shutdown trong Spring Cloud Task, từ đó thiết kế việc kết thúc và khôi phục an toàn khi tác vụ chạy theo lịch hoặc theo yêu cầu.

## 2. Bức tranh vòng đời: khởi chạy, xử lý, hoàn tất và bị ngắt

~~~mermaid
flowchart TD
    A["CLI / Scheduler / Kubernetes Job"] --> B["JVM khởi chạy Spring Boot"]
    B --> C["Spring Cloud Task ghi nhận lần chạy"]
    C --> D["Runner / service xử lý nghiệp vụ"]
    D --> E{"Có yêu cầu dừng?"}
    E -- "Không" --> F["Chờ công việc con, commit kết quả"]
    F --> G["Task kết thúc bình thường"]
    G --> H["Đóng context / trả mã thoát"]
    E -- "SIGTERM hoặc đóng context" --> I["Bắt đầu shutdown, thời gian hữu hạn"]
    I --> J["Báo dừng, hạn chế nhận việc mới"]
    J --> K{"Hoàn thành an toàn trước deadline?"}
    K -- "Có" --> L["Chốt phần đã xử lý, giải phóng tài nguyên"]
    L --> H
    K -- "Không" --> M["Có thể bị kill / kết thúc giữa chừng"]
    E -- "SIGKILL / crash / OOMKill" --> M
    M --> N["Metadata hoặc kết quả có thể dở dang"]
    H --> O["Bộ điều phối quan sát mã thoát và trạng thái"]
    N --> P["Đối chiếu dấu vết, phục hồi, retry idempotent"]
~~~

Luồng trên là mô hình vận hành, không cam kết thứ tự chính xác giữa callback nội bộ Spring Cloud Task, Spring Boot và JVM trong mọi phiên bản. **Spring Cloud Task không thể chạy mã Java khi JVM đã ngừng thực thi**. Do đó framework không thể bảo đảm sẽ ghi thành công metadata cuối cùng nếu tiến trình chết trước lúc hoàn thành thao tác ghi.

Có hai cấp độ “hoàn tất” cần định nghĩa rõ:

1. **Hoàn tất nghiệp vụ:** tất cả phần việc bắt buộc đã xử lý, dữ liệu đã lưu an toàn, lỗi đã được tổng hợp.
2. **Hoàn tất lần chạy:** framework có cơ hội cập nhật TaskExecution và tiến trình có kết quả để bên điều phối quan sát.

Thiết kế tốt cần làm cho hai cấp độ này nhất quán **trong điều kiện vận hành bình thường**, đồng thời chấp nhận và phục hồi được trạng thái không nhất quán khi có sự cố bất ngờ.

## 3. Các kiểu tín hiệu dừng và hành vi của JVM

Trên Linux/Unix, tiến trình Java có thể nhận tín hiệu từ terminal, hệ điều hành hoặc container runtime. Một số tín hiệu hay gặp:

| Sự kiện / tín hiệu | Nguồn thường gặp | JVM có cơ hội cleanup? | Điều cần hiểu |
|---|---|---|---|
| **SIGTERM** (15) | `kill -TERM PID`, `docker stop`, Kubernetes yêu cầu dừng container | **Thường có**, thông qua JVM shutdown sequence/hook nếu môi trường và cấu hình cho phép | Có thời gian để thực hiện dừng có kiểm soát, nhưng không vô hạn |
| **SIGINT** (2) | `Ctrl+C` trong terminal | **Thường có** trên môi trường hỗ trợ | Thường khởi động quy trình shutdown tương tự, không mặc định đồng nghĩa nghiệp vụ hoàn tất |
| **SIGKILL** (9) | `kill -KILL PID`, hết grace period, một số trường hợp OOMKill | **Không** | Không thể bắt/chặn tín hiệu để chạy Java cleanup hoặc shutdown hook |
| Lỗi JVM / crash / mất máy | Crash native, hệ điều hành ngừng, mất điện | **Không thể bảo đảm** | Không có cam kết callback nào được chạy |
| `System.exit(code)` | Mã Java chủ động yêu cầu kết thúc JVM | **Có quy trình shutdown hook**, nếu JVM còn hoạt động bình thường | Không có nghĩa tự đợi mọi nghiệp vụ nền hoàn thành |
| `Runtime.halt(code)` | Kết thúc JVM tức thời theo lời gọi mã Java | **Không** chạy shutdown hook thông thường | Chỉ dùng khi thực sự chấp nhận bỏ qua cleanup |
| Kết thúc tự nhiên | Runner xử lý xong và không còn luồng non-daemon giữ JVM | Có cơ hội đóng tài nguyên nếu code đóng context đúng | Không nên phó mặc metadata cho việc JVM tự rơi khỏi tiến trình |

Trên Linux, một số shell hoặc container hiển thị mã thoát **143** cho SIGTERM (128 + 15), **137** cho SIGKILL (128 + 9), **130** cho SIGINT (128 + 2). Đây là **quy ước hay gặp** của môi trường thực thi, **không phải mã bảo đảm mọi ứng dụng Java sẽ trả về**. Mã cuối cùng có thể do JVM, shell wrapper, container runtime hoặc ứng dụng quyết định. Trên Windows, cơ chế console events và kết thúc tiến trình khác Unix; đừng giả định tất cả ký hiệu SIGTERM/SIGKILL có cùng ý nghĩa trên mọi nền tảng.

### SIGTERM và SIGKILL khác nhau ở điểm cốt yếu nào?

- **SIGTERM** là yêu cầu dừng: JVM *có thể* nhận biết và chạy shutdown hook, Spring *có thể* đóng context, ứng dụng *có thể* chờ và dọn dẹp trong khoảng thời gian cho phép.
- **SIGKILL** là dừng cưỡng bức: JVM không có cơ hội chạy thêm mã Java; các bước chờ, `@PreDestroy`, flush buffer hoặc cập nhật TaskRepository **không được thực hiện sau thời điểm bị kill**.

Bởi vậy, **graceful shutdown là một nỗ lực có giới hạn**, không phải cơ chế bảo đảm mọi công việc sẽ hoàn tất khi có bất kỳ tín hiệu nào.

## 4. JVM shutdown hook và Spring ApplicationContext

Khi JVM bước vào quy trình shutdown bình thường, các **shutdown hook** đã đăng ký có cơ hội được thực thi. Spring Boot thường đăng ký hook để đóng `ApplicationContext` khi JVM kết thúc, trừ khi cơ chế này bị tắt hoặc môi trường thực thi thay đổi hành vi.

Đóng Spring context cho phép Spring thực hiện các bước như:

- Phát `ContextClosedEvent`, để các thành phần quan tâm biết rằng context sắp đóng.
- Dừng các lifecycle component theo cơ chế phù hợp.
- Gọi callback hủy bean như `@PreDestroy`/destroy method và đóng tài nguyên do Spring quản lý.
- Áp dụng quy tắc shutdown của các executor, datasource, listener và thành phần khác nếu chúng được cấu hình.

**Thứ tự và thời gian không được mặc định hiểu là “mọi nghiệp vụ đang chạy sẽ xong”.** Một callback chỉ có cơ hội chạy nếu JVM còn ở trạng thái có thể thực thi hook. Callback có thể gặp lỗi, bị timeout ở tầng điều phối hoặc không còn phụ thuộc mà nó cần vì các bean khác cũng đang bị đóng.

Mẫu dùng hook của Spring để nhận biết context đang đóng:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownState {

    private final AtomicBoolean stopRequested = new AtomicBoolean();

    @EventListener(ContextClosedEvent.class)
    public void onContextClosed(ContextClosedEvent event) {
        stopRequested.set(true);
    }

    public boolean isStopRequested() {
        return stopRequested.get();
    }
}
~~~

`ShutdownState` chỉ báo một **yêu cầu dừng**. Nó không tự hủy các truy vấn CSDL, không chờ worker, không thay thế timeout và không bảo đảm chạy khi bị SIGKILL. Khi `ContextClosedEvent` được phát trên luồng shutdown, luồng nghiệp vụ khác cần **chủ động kiểm tra cờ dừng** tại các điểm an toàn.

### Có nên tự thêm Runtime.addShutdownHook?

Chỉ khi có nhu cầu cụ thể mà hạ tầng lifecycle của Spring không đáp ứng được. Nếu tự cài nhiều hook song song với Spring Boot, **đừng dựa vào thứ tự hook để truy cập bean hoặc datasource**: thứ tự thực thi các hook JVM không được bảo đảm, và các hook có thể chạy đồng thời. Không đặt nghiệp vụ chính, transaction dài hoặc lời gọi mạng không giới hạn thời gian vào shutdown hook.

Đối với ứng dụng Spring Cloud Task, ưu tiên định nghĩa rõ **điểm hoàn tất trong runner**, thực hiện công việc trong service, và dùng lifecycle callback chỉ để hỗ trợ **dừng nhận việc mới, phát tín hiệu hủy, giải phóng tài nguyên**.

## 5. Luồng daemon, non-daemon và nguy cơ “runner xong nhưng task chưa xong”

Trong Java, luồng có thể là **daemon** hoặc **non-daemon**. Khác biệt này ảnh hưởng cách JVM chấm dứt tự nhiên:

- **Non-daemon thread:** khi còn chạy, nó có thể giữ tiến trình JVM sống kể cả sau khi `main` và runner đã trả về.
- **Daemon thread:** không giữ JVM sống một mình; khi JVM kết thúc, công việc trên daemon thread có thể bị bỏ dở.

Ví dụ sau minh họa một lỗi thiết kế:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;

@Bean
ApplicationRunner startInBackground(ReportService reportService) {
    return args -> {
        Thread worker = new Thread(
            reportService::generateReport,
            "report-worker"
        );
        worker.start();

        // Runner kết thúc ngay; không có bảo đảm generateReport() xong.
    };
}
~~~

Ở đây:

1. Runner đã trả về nhưng `generateReport()` vẫn có thể đang chạy.
2. Nếu worker là non-daemon, JVM có thể tiếp tục sống nếu context chưa đóng; vòng đời TaskExecution có thể bị chốt trước khi công việc con hoàn thành, tùy cấu hình và callback.
3. Nếu worker là daemon, công việc có thể biến mất khi không còn non-daemon thread.
4. Nếu context đóng, datasource hoặc executor có thể bị đóng trong lúc worker vẫn cần dùng chúng.
5. Nếu nhận SIGTERM, việc JVM đang có non-daemon thread **không buộc shutdown phải chờ thread đó vô hạn**. Sau khi các shutdown hook hoàn tất, JVM có thể kết thúc dù nghiệp vụ vẫn dở dang.

Không nên giải quyết bằng việc chuyển mọi thread sang non-daemon hoặc chèn `Thread.sleep(...)` sau khi gửi việc. Cần một cơ chế **theo dõi completion rõ ràng**.

### Các nguồn công việc nền dễ bị bỏ sót

| Cơ chế | Vì sao dễ kết thúc sớm? | Cách kiểm soát |
|---|---|---|
| `new Thread(...).start()` | Không lưu/đợi tham chiếu luồng | Quản lý vòng đời, `join` có timeout và kiểm tra kết quả |
| `@Async` | Phương thức được chuyển sang executor | Trả `CompletableFuture`/`Future`, đợi và xử lý exception |
| `TaskExecutor.execute(...)` | Giao `Runnable` không có nghĩa đã hoàn tất | Dùng future, latch hoặc giao diện phù hợp để theo dõi |
| `CompletableFuture.runAsync(...)` | Có thể dùng common pool hoặc executor riêng | Chỉ định executor có quản lý và đợi future |
| `@Scheduled` | Có thể tiếp tục tạo công việc khi ứng dụng còn sống | Dừng nhận việc mới; không dùng scheduler thường trực để giữ task hữu hạn |
| Spring Batch asynchronous job | Runner có thể nhận kết quả khởi chạy trước khi job xong | Kiểm tra `JobExecution`, đợi terminal status nếu cần đồng bộ |

Trong task chạy hữu hạn, hãy xác định rõ **việc nào bắt buộc phải hoàn tất trước khi runner trả về**. Metadata của Spring Cloud Task mô tả vòng đời ứng dụng; nó không tự theo dõi từng future và không thể tự biết service đã đẩy bao nhiêu việc sang thread pool.

## 6. Thiết kế runner chỉ trả về khi mọi việc bắt buộc đã hoàn tất

Ví dụ dưới đây dùng Spring-managed `ThreadPoolTaskExecutor` và `CompletableFuture` để xuất các phân vùng báo cáo song song. Runner đợi tất cả phân vùng kết thúc trước khi trả về.

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class ExportTaskConfiguration {

    @Bean("exportExecutor")
    ThreadPoolTaskExecutor exportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("export-");

        // Hỗ trợ quá trình đóng context, không thay thế chờ future.
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }

    @Bean
    ApplicationRunner exportRunner(
            ExportService exportService,
            @Qualifier("exportExecutor") TaskExecutor executor) {
        return args -> {
            List<Integer> partitions = List.of(1, 2, 3, 4, 5, 6, 7, 8);

            List<CompletableFuture<Void>> futures = partitions.stream()
                .map(part -> CompletableFuture.runAsync(
                    () -> exportService.exportPartition(part), executor))
                .toList();

            CompletableFuture<Void> all = CompletableFuture.allOf(
                futures.toArray(new CompletableFuture<?>[0])
            );

            // Chỉ kết thúc khi tất cả đã hoàn tất; lỗi sẽ lan lên runner.
            all.join();
        };
    }
}
~~~

`ExportService` là service nghiệp vụ cần được dự án cung cấp. `exportPartition(part)` phải có chiến lược transaction và idempotency, ví dụ mỗi phân vùng ghi một kết quả được định danh duy nhất theo `date` và `partitionId`.

**Ý nghĩa của đoạn mã:**

- Pool có giới hạn luồng và hàng đợi, tránh tạo quá nhiều thread không kiểm soát.
- `CompletableFuture.allOf(...).join()` chỉ hoàn tất bình thường sau khi **mọi future đều hoàn tất thành công**; nếu có future thất bại, `join()` ném exception (thường được bọc trong `CompletionException`).
- `setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(30)` là hỗ trợ shutdown của executor. Chúng **không đảm bảo** JVM được hệ điều phối cho đủ 30 giây, không tự roll back transaction, và không thay thế `join()`.
- Đặt timeout chờ shutdown khác với timeout nghiệp vụ. Một phần việc bị treo I/O quá lâu vẫn cần deadline, timeout và chính sách hủy riêng.

Với một task cần hủy có kiểm soát trong lúc đang chạy, thêm cơ chế cancellation vào service: nhận yêu cầu dừng, **không nhận thêm phân vùng mới**, để phân vùng đang chạy hoàn tất đến điểm commit an toàn, lưu checkpoint rồi dừng. Điều này khó đạt được nếu đã nộp hàng nghìn công việc vào queue và chỉ đến shutdown mới cố xử lý chúng.

## 7. Dừng hợp tác: interruption, cờ dừng và điểm commit an toàn

**Thread interruption** là một cơ chế yêu cầu dừng mang tính hợp tác trong Java. Nó không cưỡng bức kết thúc mọi phép tính và không bảo đảm hủy được I/O hay transaction đang chạy.

Một phần việc có thể nhận yêu cầu dừng từ:

- Cờ dừng ứng dụng (ví dụ `ShutdownState.isStopRequested()` sau `ContextClosedEvent`).
- Trạng thái interrupted của luồng khi executor hoặc logic hủy gọi `interrupt()`/`Future.cancel(true)`.
- Timeout hoặc hạn mức nghiệp vụ do hệ điều phối thiết lập.

Mẫu service xử lý dữ liệu theo từng phân vùng, tránh dừng ở giữa transaction:

~~~java
import java.util.List;
import java.util.concurrent.CancellationException;

import org.springframework.stereotype.Service;

@Service
public class PartitionCoordinator {

    private final ShutdownState shutdownState;
    private final PartitionService partitionService;

    public PartitionCoordinator(
            ShutdownState shutdownState,
            PartitionService partitionService) {
        this.shutdownState = shutdownState;
        this.partitionService = partitionService;
    }

    public void process(List<String> partitionIds) {
        for (String id : partitionIds) {
            // Kiểm tra trước khi bắt đầu một đơn vị công việc mới.
            if (shutdownState.isStopRequested()
                    || Thread.currentThread().isInterrupted()) {
                throw new CancellationException(
                    "Task bi yeu cau dung truoc partition " + id);
            }

            // Mỗi partition là một đơn vị commit/idempotency độc lập.
            partitionService.processAndCommit(id);
        }
    }
}
~~~

Trong ví dụ, `PartitionService.processAndCommit(id)` được cài đặt ở bean khác để có thể áp dụng transaction đúng qua Spring proxy nếu dùng `@Transactional`. Một lần commit thành công phải đủ thông tin để nhận diện khi retry. Cờ dừng chỉ được kiểm tra **trước khi bắt đầu phân vùng mới** nhằm tránh hủy tùy tiện giữa giao dịch. Với phân vùng rất lâu, có thể bổ sung các điểm kiểm tra bên trong khi an toàn và dùng timeout cho lời gọi mạng/CSDL.

**Hai giới hạn cần ghi nhớ:**

1. `interrupt()` chỉ đánh dấu trạng thái ngắt và đánh thức một số thao tác chờ có hỗ trợ interruption. Một vòng lặp không kiểm tra interrupt hoặc một driver I/O không hỗ trợ hủy có thể tiếp tục chạy.
2. Nếu context đang đóng song song, bean cần thiết như datasource cũng có thể đang bị hủy. Vì vậy cờ dừng và `@PreDestroy` **không đủ để bảo đảm** giao dịch sẽ commit kịp. Muốn chờ có giới hạn, phải phối hợp thứ tự đóng tài nguyên với worker và kiểm thử cơ chế shutdown thực tế.

### Khi bắt được InterruptedException

Nếu một phương thức không thể ném tiếp `InterruptedException` và phải bắt nó để cleanup, nên **khôi phục cờ interrupt** để tầng trên nhận biết yêu cầu dừng:

~~~java
try {
    workerDone.await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
        "Dang cho worker thi nhan interrupt", ex);
}
~~~

Không âm thầm nuốt `InterruptedException` rồi xử lý tiếp như thành công. Ngược lại, đừng coi việc ném `CancellationException` khi JVM đang shutdown là bằng chứng TaskRepository chắc chắn ghi được mã thất bại; tại thời điểm đó callback hoặc kết nối CSDL có thể không còn hoạt động.

## 8. Giới hạn của graceful shutdown và chính sách thời gian

Graceful shutdown hoạt động trong một **ngân sách thời gian** do môi trường chạy áp đặt. Với Kubernetes, khi Pod được yêu cầu chấm dứt, hệ thống thường cho container cơ hội nhận SIGTERM và dừng trước khi cưỡng bức bằng SIGKILL nếu hết thời gian grace. Giá trị cấu hình `terminationGracePeriodSeconds` là một phần của quy trình đó. Các hoạt động như `preStop` cũng tiêu thụ khoảng thời gian cho phép; không nên tính toàn bộ grace period là thời gian có sẵn cho xử lý nghiệp vụ.

Ví dụ Job tối giản:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: daily-revenue-export
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 45
      containers:
        - name: revenue-export
          image: example/revenue-task:1.0
          args:
            - "--date=2026-11-23"
~~~

Ví dụ giả định image đã khai báo entrypoint thực thi ứng dụng Java; giá trị image chỉ mang tính minh họa. Trong thực tế, cần bổ sung cấu hình truy cập CSDL, secret, tài nguyên, bảo vệ tránh trùng và chính sách quan sát phù hợp.

**Không có công thức bảo đảm:** “45 giây grace + executor await 30 giây = chắc chắn đủ 30 giây”. Tín hiệu phải đến đúng tiến trình Java, hook phải chạy, các thành phần phải đóng đúng thứ tự, còn JVM vẫn phụ thuộc deadline bên ngoài. Nếu dùng shell wrapper, hãy dùng dạng `exec java -jar ...` hoặc cách chuyển tiếp tín hiệu đúng để JVM nhận được yêu cầu dừng; nếu không, tiến trình Java có thể chỉ thấy việc parent bị kill.

Các timeout cần xem xét riêng:

| Timeout / giới hạn | Vai trò | Nếu không thỏa mãn |
|---|---|---|
| Grace period của Pod/container | Tổng thời gian môi trường cho phép để dừng | Có thể bị SIGKILL |
| Timeout xử lý từng partition | Giới hạn một đơn vị nghiệp vụ | Cần hủy, rollback, retry hoặc đánh dấu lỗi |
| Timeout I/O/CSDL | Tránh worker kẹt vô hạn | I/O lâu có thể kéo dài quá grace period |
| Executor await termination | Chờ thread pool sau lệnh shutdown | Hết hạn **không** chứng minh mọi việc đã hoàn thành |
| Deadline toàn bộ task | Giới hạn lần thực thi cho bộ điều phối | Có thể bị ngắt kể cả runner đang xử lý |
| Retry/backoff | Cách khởi chạy lại sau lỗi | Có thể thực hiện lặp nghiệp vụ nếu không idempotent |

Một lần chạy hữu hạn nên có deadline rõ ràng và các điểm **chấp nhận dừng giữa hai đơn vị commit**, thay vì cố “hoàn tất mọi thứ bằng mọi giá” trước thời điểm kill.

## 9. Điều gì xảy ra với TaskRepository khi JVM bị ngắt?

**TaskRepository** của Spring Cloud Task lưu metadata của TaskExecution trong CSDL khi cấu hình phù hợp, thường bao gồm các thông tin như `TASK_EXECUTION_ID`, `TASK_NAME`, `START_TIME`, `END_TIME`, `EXIT_CODE` và thông điệp thoát. Việc metadata thực sự có mặt phụ thuộc repository có được khởi tạo và kết nối CSDL thành công hay không.

Xem ba trường hợp:

| Thời điểm sự cố | Metadata có thể thấy | Kết luận đúng |
|---|---|---|
| Sau khi khởi tạo task, trước khi hoàn tất nghiệp vụ | Có `START_TIME` nhưng chưa có `END_TIME` hoặc kết quả cuối | Task **có thể** đang chạy, treo hoặc đã chết; cần đối chiếu tiến trình và bộ điều phối |
| Sau khi commit dữ liệu, trước khi cập nhật lần chạy | Dữ liệu nghiệp vụ có thể đủ, TaskExecution chưa chốt | Không tự chạy lại mù quáng; cần kiểm tra tính idempotent/đầu ra |
| Trước khi repository ghi được bản ghi bắt đầu | Có thể không có bản ghi TaskExecution tương ứng | Không thể suy ra “chưa từng được khởi chạy” chỉ từ bảng metadata |

Spring Cloud Task **không thể ghi metadata sau SIGKILL**; trạng thái chưa chốt không tự biến thành “FAILED” nhờ framework. Hơn nữa, một bản ghi thiếu `END_TIME` chưa đủ chứng minh job chết, vì có thể job vẫn đang chạy hợp lệ.

Ví dụ truy vấn minh họa tìm lần chạy chưa có thời điểm kết thúc (cú pháp tham số tùy driver):

~~~sql
SELECT TASK_EXECUTION_ID, TASK_NAME, START_TIME, END_TIME, EXIT_CODE
FROM TASK_EXECUTION
WHERE END_TIME IS NULL
  AND START_TIME < :cutoff_time
ORDER BY START_TIME;
~~~

Khi xử lý danh sách này, cần đối chiếu trạng thái Pod/Job/process, log, heartbeat hoặc bằng chứng nguồn ngoài. Chỉ khi xác nhận lần chạy đã dừng, hệ thống mới nên đưa ra quyết định xử lý bản ghi bất thường theo quy trình vận hành đã thống nhất. Không tự động sửa `EXIT_CODE` hay `END_TIME` bằng một script tùy tiện: dễ ghi đè kết quả của lần chạy còn sống hoặc làm mất dấu vết điều tra.

**TaskExecution không đồng nghĩa với kết quả nghiệp vụ.** Muốn biết 12/20 phân vùng đã được commit, ứng dụng cần bảng tiến độ, checkpoint, transaction log hoặc kết quả lưu trữ riêng.

## 10. Kịch bản mất tiến trình và chiến lược phục hồi

Xét nhiệm vụ xuất doanh thu theo ngày, gồm các phân vùng từ 1 đến 20. Mỗi phân vùng có khóa định danh duy nhất theo `business_date` và `partition_id`.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant T as Spring Cloud Task
    participant D as Business DB
    participant R as TaskRepository
    O->>T: Khởi chạy date=2026-11-23
    T->>R: Ghi lần chạy
    loop Mỗi phân vùng
        T->>D: Xử lý + commit theo khóa nghiệp vụ
    end
    O-->>T: SIGTERM
    T->>T: Nếu còn thời gian: không nhận việc mới
    T->>D: Commit phần đang xử lý nếu an toàn
    alt Đủ thời gian dừng
        T->>R: Có thể ghi trạng thái cuối
        T-->>O: Kết thúc tiến trình
    else Hết thời gian / SIGKILL
        T--xO: Tiến trình bị cắt
        Note over D,R: Dữ liệu và metadata có thể lệch nhau
    end
    O->>D: Kiểm tra phân vùng đã commit
    O->>T: Retry với cùng business_date
    T->>D: Bỏ qua hoặc xác minh phần đã hoàn thành
~~~

Để chạy lại an toàn:

1. **Định nghĩa idempotency key** theo yêu cầu nghiệp vụ, ví dụ `businessDate + partitionId`. Có thể dùng unique constraint/upsert hoặc trạng thái xử lý trong bảng riêng.
2. **Commit theo đơn vị hợp lý:** mỗi phân vùng hoàn chỉnh được ghi như một giao dịch độc lập; không giữ transaction quá lâu chỉ để gom toàn bộ báo cáo.
3. **Đừng tách “ghi kết quả” và “đánh dấu đã xong” một cách thiếu nhất quán:** khi có thể, cập nhật đầu ra và checkpoint trong cùng transaction hoặc dùng outbox/biện pháp đối soát.
4. **Retry kiểm tra dữ liệu thật:** TaskExecution cũ có thể chưa chốt nhưng kết quả phân vùng đã được lưu. Quyết định bỏ qua, cập nhật lại hay chạy bù dựa vào trạng thái nghiệp vụ.
5. **Giới hạn chạy trùng đồng thời:** nếu một task cũ vẫn đang xử lý mà task mới được khởi chạy lại, cần cơ chế khóa/điều phối phù hợp và xác định quyền sở hữu công việc.
6. **Cảnh báo và giám sát:** theo dõi số lần khởi chạy, trạng thái Pod/Job, mã thoát, thời gian chạy và những TaskExecution thiếu `END_TIME` quá ngưỡng hợp lý.

Không nên gọi cơ chế này là “exactly once” chỉ vì có `TaskRepository` hoặc unique key. Khi tương tác với dịch vụ ngoài, gửi email, ghi object storage hoặc phát message, cần thiết kế thêm cơ chế đối soát và idempotency đầu nhận; transaction CSDL nội bộ không bao trùm mọi side effect bên ngoài.

## 11. Spring Cloud Task và Spring Batch khi bị ngắt giữa chừng

Spring Cloud Task và Spring Batch xử lý **hai cấp độ trạng thái**:

| Thành phần | Theo dõi gì? | Khi tiến trình bị kill |
|---|---|---|
| Spring Cloud Task / `TaskRepository` | Vòng đời **lần chạy ứng dụng** (`TaskExecution`) | Có thể thiếu thời điểm kết thúc hoặc mã thoát cuối |
| Spring Batch / `JobRepository` | `JobExecution`, `StepExecution`, checkpoint, trạng thái batch | Có thể còn trạng thái đang chạy hoặc không xác định, cần điều tra/phục hồi |
| CSDL nghiệp vụ | Kết quả đã ghi và khóa nghiệp vụ | Chỉ phần được commit bền vững còn hiệu lực; side effects ngoài transaction cần đối soát |

Nếu sử dụng chunk-oriented processing, Spring Batch có khả năng lưu checkpoint và hỗ trợ **restart** theo thiết kế job/step. Điều đó không có nghĩa việc restart luôn tự diễn ra, cũng không có nghĩa mọi step đều có thể restart an toàn. Reader, processor, writer và side effects phải được thiết kế phù hợp.

Với shutdown hợp tác, có thể cân nhắc yêu cầu job dừng ở ranh giới xử lý phù hợp để checkpoint được lưu, nhưng khi gặp SIGKILL, không thể đảm bảo callback cuối của Spring Batch sẽ chạy. Tương tự Spring Cloud Task, cần kiểm tra repository và dữ liệu nghiệp vụ trước khi restart.

Đối với yêu cầu “ứng dụng xử lý hữu hạn, có TaskExecution, đồng thời cần checkpoint chi tiết từng chunk”, kết hợp Spring Cloud Task và Spring Batch là phương án thường phù hợp. Nếu chỉ có runner đơn giản tự lặp, muốn khôi phục sau khi kill thì phải tự xây cơ chế checkpoint nghiệp vụ hoặc áp dụng framework xử lý batch thích hợp.

## 12. Những ngộ nhận nguy hiểm trong vận hành

### “Nhận SIGTERM là chắc chắn TaskExecution được đánh dấu thất bại”

**Không chắc.** SIGTERM có thể kích hoạt shutdown, nhưng hook có thể bị cắt bởi deadline, repository có thể không còn kết nối, hoặc cơ chế ghi metadata đã xảy ra trước khi service thực sự hoàn tất. Phải kiểm tra bản ghi, log và trạng thái tiến trình.

### “@PreDestroy sẽ luôn chạy”

**Sai.** Callback chỉ có cơ hội chạy khi context được đóng có kiểm soát. SIGKILL, crash hoặc mất máy có thể bỏ qua hoàn toàn callback. Không đặt nghĩa vụ ghi kết quả nghiệp vụ duy nhất vào `@PreDestroy`.

### “Luồng non-daemon giúp bảo đảm không bị mất việc”

**Sai.** Non-daemon có thể giữ JVM sống trong quá trình tự kết thúc, nhưng không ngăn SIGKILL và không bắt JVM chờ vô hạn trong shutdown sequence. Luồng đó cũng có thể đang dùng tài nguyên đã bị đóng.

### “Executor awaitTermination hoàn tất là nghiệp vụ thành công”

**Sai.** Khi hết timeout, worker vẫn có thể đang chạy; khi mọi thread dừng, một số công việc có thể bị từ chối, bị hủy hoặc ném exception. Cần kiểm tra kết quả future, output và tiêu chí thành công trước khi trả mã 0.

### “TaskRepository ghi là COMPLETED nên side effects bên ngoài chắc chắn thành công”

**Không đủ căn cứ.** Metadata cho biết cách framework quan sát lần chạy. Nó không xác nhận độc lập rằng hệ thống nhận message, dịch vụ thứ ba hoặc object storage đã xử lý hoàn toàn tác vụ. Phải có xác nhận/đối soát ở tầng nghiệp vụ.

### “Đã cấu hình graceful shutdown 60 giây thì có đúng 60 giây để xử lý tiếp”

**Không bảo đảm.** Thời gian thực nhận phụ thuộc cả runtime, hook, `preStop`, việc chuyển tiếp tín hiệu và giới hạn của bộ điều phối. Shutdown nên được xem là cơ hội **dừng an toàn tại điểm hợp lý**, không phải một khoảng thời gian miễn phí để chạy thêm khối lượng bất kỳ.

## 13. Checklist triển khai Spring Cloud Task có khả năng dừng an toàn

| Câu hỏi kiểm tra | Hành động nếu chưa đạt |
|---|---|
| Runner chỉ trả về sau khi mọi công việc bắt buộc hoàn tất? | Đợi các `Future`/`CompletableFuture`, tổng hợp lỗi, tránh fire-and-forget |
| Công việc có thể dừng ở ranh giới commit rõ ràng? | Chia thành phân vùng/chunk, kiểm tra cờ dừng trước đơn vị mới |
| Có timeout cho I/O, database, từng phần việc? | Đặt timeout có kiểm soát, tránh thread treo quá grace period |
| Signal được chuyển tới JVM/container đúng cách? | Kiểm tra entrypoint dạng exec và quy trình SIGTERM trong môi trường thật |
| Có time budget cho shutdown? | Cấu hình grace period, timeout worker, deadline, kiểm thử tình huống vượt hạn |
| Có kho kết quả và checkpoint bền vững ngoài TaskRepository? | Lưu business state với khóa idempotency, transaction phù hợp |
| Biết phân biệt tiến trình chết với metadata chưa chốt? | Đối chiếu Pod/Job/process, log, heartbeat và TaskExecution |
| Retry có thể ghi trùng hoặc gửi trùng? | Thêm unique key, upsert, idempotency, outbox hoặc đối soát |
| Có thể phân biệt lỗi nghiệp vụ và lỗi hạ tầng? | Trả mã thoát hợp lý, log ngữ cảnh, không nuốt exception |
| Đã diễn tập SIGTERM, SIGKILL và timeout? | Chạy test vận hành trong staging; kiểm tra kết quả nghiệp vụ và trạng thái repository sau restart |

Một kịch bản diễn tập đáng thực hiện:

1. Khởi chạy task có 20 phân vùng, bảo đảm mỗi phân vùng ghi tiến độ sau commit.
2. Trong khi đang xử lý, gửi **SIGTERM** và quan sát thời điểm runner dừng, executor chờ, context đóng và tiến trình trả mã gì.
3. Lặp lại với **SIGKILL** để thấy khác biệt: không trông chờ shutdown callback hoặc metadata được chốt.
4. Đối chiếu `TaskExecution` với dữ liệu nghiệp vụ; ghi nhận phân vùng nào đã commit.
5. Chạy lại cùng tham số; xác nhận kết quả cuối chính xác và không nhân đôi.
6. Kiểm tra trường hợp công việc bị treo quá deadline; bảo đảm hệ thống cảnh báo và có quy trình phục hồi.

Nên kiểm thử cả khi tiến trình vừa khởi động, đang chạy giữa transaction và đã xử lý xong nhưng chưa thoát, bởi **cửa sổ xảy ra sự cố** quyết định dấu vết còn lại.

## 14. Kết luận

Trong **Spring Cloud Task**, dấu hiệu hoàn tất đáng tin cậy bắt đầu từ **nghiệp vụ đã hoàn thành và kết quả đã được lưu**, sau đó mới là TaskExecution và mã thoát của tiến trình. `SIGTERM` thường mang lại cơ hội đóng Spring context, phát yêu cầu dừng và lưu trạng thái; `SIGKILL` hoặc crash có thể cắt bỏ mọi bước đó. Luồng nền, `@Async` và executor chỉ an toàn khi ứng dụng thực sự theo dõi completion, có timeout và biết cách dừng ở ranh giới commit.

Để vận hành ứng dụng có thời gian chạy hữu hạn theo lịch hoặc yêu cầu, hãy kết hợp **graceful shutdown có thời hạn**, **TaskRepository để quan sát vòng đời**, **lưu trạng thái nghiệp vụ bền vững** và **retry idempotent**. Khi JVM bị ngắt giữa chừng, mục tiêu thực tế là có thể **xác định phần việc đã hoàn thành, phục hồi phần còn lại và tránh tạo kết quả sai hoặc trùng**, thay vì kỳ vọng mọi callback luôn kịp chạy.
