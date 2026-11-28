# Quản lý trạng thái khi nhiều tác vụ dùng chung bean

## 1. Vì sao trạng thái dùng chung dễ gây lỗi?

Trong ứng dụng Spring Shell, command và service thường được đăng ký thành Spring bean. Mặc định, một bean có scope `singleton`: Spring tạo một instance cho mỗi bean definition trong một `ApplicationContext` và tái sử dụng instance đó ở những nơi inject bean.

Điều này phù hợp với service không giữ trạng thái theo từng lần gọi. Ví dụ, `ProjectService` có thể dùng chung repository, cấu hình và client HTTP để xử lý nhiều yêu cầu. Rủi ro xuất hiện khi bean singleton lưu dữ liệu thay đổi theo từng command hoặc từng tác vụ:

- Tác vụ A ghi tên tệp hiện tại vào field; tác vụ B ghi đè field đó trước khi A đọc lại.
- Hai tác vụ cùng tăng một biến đếm và làm mất cập nhật.
- Một danh sách mutable được sửa đồng thời trong lúc command khác đang duyệt.
- Tác vụ nền tiếp tục chạy sau khi command khởi tạo đã trả về, khiến trạng thái thay đổi ngoài thời điểm người dùng dự kiến.

Spring quản lý vòng đời và việc inject bean; điều đó không tự làm cho object thread-safe. Nếu một bean được nhiều command hoặc tác vụ dùng chung, chính thiết kế bean phải xác định dữ liệu nào bất biến, dữ liệu nào thuộc riêng từng tác vụ và dữ liệu nào cần đồng bộ.

## 2. Bean singleton trong ứng dụng Spring Shell

Trong mô hình annotation, lớp command được đăng ký như Spring component. Ví dụ:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ProjectCommands {

    @ShellMethod(key = "project status")
    public String status() {
        return "Project service is ready";
    }
}
~~~

`@ShellComponent` là component được Spring quản lý. Nếu không chỉ định scope khác, bean này dùng scope mặc định `singleton`. Những service được inject vào command cũng thường là singleton.

Không nên kết luận rằng mọi command trong một phiên shell luôn chạy song song. Một phiên REPL có thể xử lý command theo trình tự. Tuy nhiên, các tác vụ nền có thể chồng lấp nếu ứng dụng dùng `TaskExecutor`, `@Async`, scheduler, listener hoặc một luồng xử lý riêng. Khi nhiều tác vụ đang chạy, chúng có thể gọi cùng một service singleton cùng lúc.

Vì vậy, hãy thiết kế bean dùng chung an toàn ngay cả khi các lần gọi xảy ra đồng thời. Không lưu dữ liệu tạm của một lần thực thi vào field của command hoặc service singleton.

## 3. Phân biệt dữ liệu cấu hình, dữ liệu nghiệp vụ và trạng thái tác vụ

Trước khi chọn scope hoặc cơ chế đồng bộ, hãy phân loại dữ liệu:

| Loại dữ liệu | Ví dụ | Cách quản lý phù hợp |
|---|---|---|
| Cấu hình dùng chung | URL API, giới hạn retry, tên môi trường mặc định | Bean singleton bất biến hoặc snapshot chỉ đọc. |
| Logic nghiệp vụ | Tính giá, kiểm tra quyền, đọc repository | Service singleton stateless. |
| Dữ liệu đầu vào một lần gọi | Đường dẫn tệp, project ID, tùy chọn export | Tham số method hoặc request object riêng. |
| Trạng thái của một tác vụ nền | Task ID, tiến độ, trạng thái, lỗi | Task context riêng và registry theo task ID. |
| Trạng thái chia sẻ cần cập nhật đồng thời | Bộ đếm, cache, registry | Atomic type, concurrent collection hoặc lock theo bất biến. |
| Trạng thái cần tồn tại sau khi tiến trình dừng | Lịch sử import, job đang chờ, kết quả xử lý | Database hoặc kho lưu trữ bền vững. |

Một nguyên tắc hữu ích là giữ service singleton không có state thay đổi theo từng lần gọi; truyền dữ liệu của lần gọi qua tham số. Nếu cần theo dõi nhiều tác vụ, lưu từng trạng thái theo ID thay vì giữ một biến `currentTask` duy nhất.

## 4. Ví dụ lỗi: lưu dữ liệu của lần gọi trong field singleton

Đoạn code sau có race condition nếu hai tác vụ cùng dùng bean:

~~~java
@Service
public class ExportService {

    private String currentFile;

    public void export(String fileName) {
        currentFile = fileName;
        prepareFile(currentFile);
        writeFile(currentFile);
    }
}
~~~

Giả sử tác vụ A gọi `export("a.csv")`, sau đó tác vụ B gọi `export("b.csv")` trước khi A thực hiện `writeFile(...)`. Field `currentFile` có thể đã thành `b.csv`, khiến A ghi nhầm tệp.

Sửa bằng cách chuyển dữ liệu tạm thành biến cục bộ:

~~~java
@Service
public class ExportService {

    public void export(String fileName) {
        Path output = prepareFile(fileName);
        writeFile(output);
    }
}
~~~

Mỗi lần gọi có stack frame và biến cục bộ riêng. Bean vẫn được chia sẻ nhưng không chia sẻ dữ liệu tạm giữa các lần gọi. Nếu `prepareFile(...)` hoặc `writeFile(...)` sử dụng một collaborator mutable khác, collaborator đó cũng cần được kiểm tra về thread safety.

## 5. Truyền request object riêng cho từng tác vụ

Khi một command nhận nhiều tham số, gom chúng thành một request object bất biến. Record phù hợp vì các thành phần của record là final:

~~~java
import java.nio.file.Path;
import java.util.Locale;

public record ExportRequest(
        Path source,
        Path destination,
        String format,
        Locale locale) {
}
~~~

Service nhận request qua tham số:

~~~java
@Service
public class ExportService {

    public ExportReceipt export(ExportRequest request) {
        // Chỉ dùng dữ liệu của request này trong lần gọi hiện tại.
        Path source = request.source();
        Path destination = request.destination();
        // Đọc source, chuyển đổi và ghi destination.
        return new ExportReceipt(destination, "COMPLETED");
    }
}
~~~

`ExportReceipt` là kiểu kết quả của ứng dụng. Request không được lưu vào field mutable của service. Nếu hai command gọi `export(...)` cùng lúc với hai request khác nhau, mỗi lần gọi sử dụng đúng dữ liệu được truyền vào.

Không phải object nào cũng tự động an toàn chỉ vì được truyền qua tham số. Nếu request chứa một `List` mutable, caller vẫn có thể sửa list trong lúc service đang đọc. Hãy dùng collection bất biến hoặc sao chép dữ liệu ở ranh giới nhận request khi cần.

## 6. Chọn scope phù hợp cho bean có trạng thái

Spring Framework hỗ trợ các scope chính:

| Scope | Ý nghĩa | Phù hợp với CLI thông thường? |
|---|---|---|
| `singleton` | Một instance cho mỗi bean definition trong một container | Có, cho service stateless và registry dùng chung có đồng bộ. |
| `prototype` | Tạo instance mới mỗi lần container được yêu cầu lấy bean | Có thể dùng để tạo object stateful cho một tác vụ. |
| `request` | Một instance cho mỗi HTTP request | Không có sẵn trong Spring ApplicationContext thông thường của CLI. |
| `session` | Một instance cho mỗi HTTP session | Không có sẵn trong CLI không chạy trong web context. |
| `application`, `websocket` | Gắn với vòng đời web tương ứng | Không phải scope theo command hoặc theo tác vụ CLI. |

Scope `request` và `session` được thiết kế cho web-aware `ApplicationContext`. Không nên gắn `@RequestScope` hoặc `@SessionScope` vào command rồi mong Spring Shell tự tạo một scope theo từng lần nhập lệnh.

### Prototype không tự tạo một instance mới ở mỗi lần gọi method

Một lỗi thường gặp là inject prototype bean trực tiếp vào singleton:

Hai lớp trong ví dụ được đặt ở hai file Java riêng.

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ImportContext {
    private String source;
}

@Service
public class ImportCoordinator {

    private final ImportContext context;

    public ImportCoordinator(ImportContext context) {
        this.context = context;
    }
}
~~~

Trong ví dụ này, Spring tạo một `ImportContext` khi khởi tạo `ImportCoordinator` và inject instance đó vào singleton. Singleton giữ cùng instance đó trong suốt vòng đời của nó. Prototype dependency không được tự resolve lại mỗi khi gọi một method của coordinator.

Nếu cần yêu cầu instance prototype mới tại thời điểm chạy, dùng `ObjectProvider`:

Ví dụ dưới đây cũng gồm hai lớp ở hai file riêng: `ImportContext.java` và `ImportCoordinator.java`.

~~~java
import java.util.UUID;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ImportContext {
    private final UUID taskId = UUID.randomUUID();

    public UUID taskId() {
        return taskId;
    }
}

@Service
public class ImportCoordinator {

    private final ObjectProvider<ImportContext> contextProvider;

    public ImportCoordinator(ObjectProvider<ImportContext> contextProvider) {
        this.contextProvider = contextProvider;
    }

    public ImportContext createContextForTask() {
        return contextProvider.getObject();
    }
}
~~~

Mỗi lần gọi `getObject()` yêu cầu Spring tạo một prototype instance mới. Coordinator nhận context đó rồi truyền nó vào worker tương ứng; không lưu nó vào một field duy nhất dùng chung cho mọi task. Ví dụ chỉ minh họa cách lấy instance; ứng dụng cần bổ sung method khởi chạy task và xử lý context theo nhu cầu.

Spring không quản lý đầy đủ lifecycle sau khi prototype bean đã được giao cho client: destruction callbacks không được tự gọi như với singleton. Nếu prototype giữ file handle, stream hoặc tài nguyên cần đóng, code sở hữu instance phải cleanup rõ ràng. Với dữ liệu thuần như request hoặc task snapshot, một object Java mới tạo trực tiếp bằng constructor thường đơn giản hơn việc khai báo prototype bean.

## 7. Quản lý trạng thái nhiều tác vụ bằng task ID

Nếu CLI chạy nhiều tác vụ nền, mỗi tác vụ cần một định danh riêng. Registry singleton có thể quản lý trạng thái theo ID bằng `ConcurrentHashMap`. Giá trị nên là immutable record để người đọc không quan sát một object đang bị sửa từng field.

~~~java
// Đặt enum này trong TaskStatus.java.
public enum TaskStatus {
    QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED
}
~~~

~~~java
import java.time.Instant;
import java.util.UUID;

// Đặt record này trong TaskSnapshot.java.
public record TaskSnapshot(
        UUID id,
        TaskStatus status,
        int completed,
        int total,
        String message,
        Instant updatedAt) {

    public TaskSnapshot withStatus(TaskStatus next, String nextMessage) {
        return new TaskSnapshot(
                id, next, completed, total, nextMessage, Instant.now());
    }

    public TaskSnapshot withProgress(int nextCompleted, String nextMessage) {
        return new TaskSnapshot(
                id, status, nextCompleted, total, nextMessage, Instant.now());
    }
}
~~~

Registry:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.stereotype.Service;

@Service
public class TaskRegistry {

    private final ConcurrentMap<UUID, TaskSnapshot> tasks =
            new ConcurrentHashMap<>();

    public TaskSnapshot create(UUID id, int total) {
        TaskSnapshot initial = new TaskSnapshot(
                id, TaskStatus.QUEUED, 0, total, "Đang chờ", Instant.now());

        TaskSnapshot previous = tasks.putIfAbsent(id, initial);
        if (previous != null) {
            throw new IllegalStateException("Task ID đã tồn tại: " + id);
        }
        return initial;
    }

    public TaskSnapshot markRunning(UUID id) {
        return tasks.compute(id, (key, current) -> {
            if (current == null || current.status() != TaskStatus.QUEUED) {
                throw new IllegalStateException("Không thể chuyển task sang RUNNING: " + id);
            }
            return current.withStatus(TaskStatus.RUNNING, "Đang xử lý");
        });
    }

    public TaskSnapshot updateProgress(UUID id, int completed, String message) {
        return tasks.compute(id, (key, current) -> {
            if (current == null || current.status() != TaskStatus.RUNNING) {
                throw new IllegalStateException("Task không ở trạng thái RUNNING: " + id);
            }
            int bounded = Math.max(0, Math.min(completed, current.total()));
            int monotonic = Math.max(current.completed(), bounded);
            return current.withProgress(monotonic, message);
        });
    }

    public TaskSnapshot finish(UUID id) {
        return tasks.compute(id, (key, current) -> {
            if (current == null || current.status() != TaskStatus.RUNNING) {
                throw new IllegalStateException("Không thể hoàn tất task: " + id);
            }
            return current.withProgress(current.total(), "Hoàn tất")
                    .withStatus(TaskStatus.SUCCEEDED, "Hoàn tất");
        });
    }

    public TaskSnapshot fail(UUID id, String safeMessage) {
        return tasks.compute(id, (key, current) -> {
            if (current == null) {
                throw new IllegalArgumentException("Không tìm thấy task: " + id);
            }
            return current.withStatus(TaskStatus.FAILED, safeMessage);
        });
    }

    public Optional<TaskSnapshot> find(UUID id) {
        return Optional.ofNullable(tasks.get(id));
    }

    public List<TaskSnapshot> findAll() {
        return List.copyOf(tasks.values());
    }
}
~~~

`ConcurrentHashMap.compute(...)` thực hiện cập nhật nguyên tử cho một key. `TaskSnapshot` là immutable, nên command đọc snapshot cũ hoặc mới hoàn chỉnh thay vì đọc object đang bị sửa dở. Cơ chế này bảo vệ thao tác trên từng task ID; nó không tạo transaction nguyên tử cho nhiều task ID cùng lúc.

Hàm được truyền vào `compute(...)` nên ngắn và chỉ tính snapshot mới. Không gọi database, API mạng hoặc chờ tác vụ khác bên trong hàm này vì thao tác đó có thể giữ cơ chế đồng bộ của map lâu hơn cần thiết.

Ví dụ trên là registry trong bộ nhớ của một tiến trình. Dữ liệu sẽ mất khi CLI kết thúc và không được chia sẻ giữa nhiều instance ứng dụng. Nếu cần lịch sử, resume sau restart hoặc nhiều worker trên nhiều tiến trình, hãy lưu task state trong database hoặc một kho lưu trữ dùng chung.

## 8. Chạy tác vụ nền bằng TaskExecutor

Spring cung cấp `TaskExecutor` để gửi công việc sang executor do container quản lý. Cấu hình một thread pool có giới hạn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class TaskExecutionConfiguration {

    @Bean(name = "cliTaskExecutor")
    public ThreadPoolTaskExecutor cliTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("cli-task-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

Queue có giới hạn giúp ứng dụng không nhận vô hạn công việc khi worker đang bận. Cần xác định cách xử lý khi queue đầy: từ chối task, báo người dùng thử lại hoặc ghi trạng thái thất bại. Không nên âm thầm bỏ task.

Coordinator tạo ID và trạng thái trước khi gửi tác vụ:

~~~java
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ImportTaskLauncher {

    private final TaskExecutor executor;
    private final TaskRegistry registry;
    private final ImportWorker worker;

    public ImportTaskLauncher(
            @Qualifier("cliTaskExecutor") TaskExecutor executor,
            TaskRegistry registry,
            ImportWorker worker) {
        this.executor = executor;
        this.registry = registry;
        this.worker = worker;
    }

    public UUID start(Path source, int totalRows) {
        UUID id = UUID.randomUUID();
        registry.create(id, totalRows);

        try {
            executor.execute(() -> run(id, source));
        }
        catch (TaskRejectedException ex) {
            registry.fail(id, "Hàng đợi tác vụ đang đầy; hãy thử lại sau");
        }

        return id;
    }

    private void run(UUID id, Path source) {
        try {
            registry.markRunning(id);
            worker.importFile(source,
                    (completed, message) -> registry.updateProgress(id, completed, message));
            registry.finish(id);
        }
        catch (Exception ex) {
            // Ghi stack trace vào log; chỉ đưa thông báo an toàn vào trạng thái hiển thị.
            log.error("Import task {} failed", id, ex);
            registry.fail(id, "Import thất bại. Kiểm tra log theo task ID để biết chi tiết.");
        }
    }
}
~~~

`ImportWorker`, logger `log` và callback tiến độ là các thành phần ứng dụng cần khai báo. `ImportTaskLauncher` là singleton nhưng không lưu task ID hiện tại trong field; mỗi task ID được truyền rõ ràng vào `run(...)`. Nếu queue từ chối task, registry chuyển task đó sang `FAILED` thay vì để nó ở trạng thái `QUEUED` mãi mãi.

## 9. Gắn transaction vào đúng luồng thực thi

Nếu worker ghi dữ liệu database, đặt ranh giới transaction trong service được gọi từ worker:

~~~java
import java.nio.file.Path;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@FunctionalInterface
interface ProgressReporter {
    void report(int completed, String message);
}

@Service
public class ImportWorker {

    @Transactional
    public void importFile(Path source, ProgressReporter progress) {
        // Đọc dữ liệu, validate và ghi database.
        // Gọi progress.report(...) khi cần cập nhật tiến độ.
    }
}
~~~

Lời gọi `worker.importFile(...)` từ task executor diễn ra trên worker thread. Khi lời gọi đi qua Spring proxy, transaction của phương thức bắt đầu trên thread đó. Không mở transaction trong command thread rồi mong worker thread tự kế thừa transaction; transaction context thông thường được gắn với thread thực thi.

Với tác vụ rất dài, một transaction bao trùm toàn bộ tệp có thể giữ connection và lock quá lâu. Khi đó, cân nhắc xử lý theo batch, mỗi batch có transaction riêng, lưu checkpoint và thiết kế khả năng chạy lại an toàn. `TaskRegistry` trong bộ nhớ chỉ theo dõi tiến độ hiển thị; trạng thái commit thực tế phải được xác định từ dữ liệu bền vững.

## 10. Hiển thị trạng thái task từ Spring Shell command

Command chỉ nhận request, gọi launcher và đọc snapshot từ registry:

~~~java
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ImportCommands {

    private final ImportTaskLauncher launcher;
    private final TaskRegistry registry;

    public ImportCommands(ImportTaskLauncher launcher, TaskRegistry registry) {
        this.launcher = launcher;
        this.registry = registry;
    }

    @ShellMethod(key = "import start", value = "Bắt đầu import ở chế độ nền")
    public String start(@ShellOption("--file") String file) {
        UUID id = launcher.start(Path.of(file), 1000);
        return "Đã gửi tác vụ import. Task ID: " + id;
    }

    @ShellMethod(key = "task status", value = "Xem trạng thái một tác vụ")
    public String status(@ShellOption("--id") UUID id) {
        return registry.find(id)
                .map(task -> task.status() + " - " + task.completed()
                        + "/" + task.total() + " - " + task.message())
                .orElse("Không tìm thấy task " + id);
    }
}
~~~

Số dòng `1000` trong ví dụ chỉ là dữ liệu minh họa; ứng dụng thực tế nên xác định tổng số bản ghi khi kiểm tra tệp hoặc dùng tiến độ theo giai đoạn. Command không giữ biến `currentTask` dùng chung. Người dùng có thể theo dõi nhiều tác vụ bằng ID riêng.

## 11. Khi nào dùng synchronized, atomic và concurrent collection?

Chọn công cụ theo loại bất biến cần bảo vệ:

| Công cụ | Dùng khi | Giới hạn |
|---|---|---|
| `AtomicInteger`, `AtomicLong` | Một giá trị số cần cập nhật nguyên tử | Không bảo vệ một nhóm nhiều field như một đơn vị. |
| `AtomicReference<T>` | Thay thế một snapshot immutable | Phải tạo snapshot mới; không làm object mutable bên trong tự thread-safe. |
| `ConcurrentHashMap` | Nhiều thread thêm, đọc hoặc cập nhật map | Các thao tác nhiều key không tự thành một transaction. |
| `synchronized` | Một đoạn code ngắn cần bảo vệ nhiều thao tác trên cùng monitor | Có thể gây chờ; chỉ phối hợp các caller dùng cùng monitor. |
| `Lock` | Cần chính sách khóa rõ hơn, timeout hoặc điều kiện chờ | Cần unlock trong `finally`. |

Ví dụ dùng `AtomicLong` cho bộ đếm toàn cục:

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class ImportMetrics {

    private final AtomicLong completedFiles = new AtomicLong();

    public long recordCompletedFile() {
        return completedFiles.incrementAndGet();
    }

    public long completedFiles() {
        return completedFiles.get();
    }
}
~~~

Nếu cần thay đổi hai giá trị phải luôn nhất quán với nhau, một atomic riêng cho từng field không đủ. Hãy gom chúng vào một immutable record và cập nhật qua `AtomicReference.updateAndGet(...)`, hoặc bảo vệ đoạn cập nhật bằng lock.

Không giữ lock trong lúc chờ người dùng nhập liệu, gọi API từ xa hoặc đọc một tệp lớn. Hãy thực hiện phần I/O ngoài vùng khóa và chỉ khóa đoạn cập nhật trạng thái nhỏ nhất có thể.

## 12. @Async và những lưu ý về proxy

Ngoài việc gọi `TaskExecutor` trực tiếp, Spring hỗ trợ `@Async`. Bật hỗ trợ async bằng `@EnableAsync`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Sau đó đánh dấu method cần chạy bất đồng bộ:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("cliTaskExecutor")
    public CompletableFuture<ReportReceipt> generate(ReportRequest request) {
        ReportReceipt receipt = generateSynchronously(request);
        return CompletableFuture.completedFuture(receipt);
    }
}
~~~

Lời gọi trả về `CompletableFuture`, cho phép caller tiếp tục làm việc và lấy kết quả sau. Nếu có lỗi, lỗi được quan sát qua future khi caller chờ hoặc kết hợp future. Với method `void`, exception không được trả về caller; cần cấu hình `AsyncUncaughtExceptionHandler` nếu cần xử lý tập trung.

Mặc định, `@Async` dùng proxy mode. Lời gọi phải đi qua proxy Spring; gọi một method `@Async` từ method khác trong cùng object (self-invocation) không kích hoạt async advice. Một service riêng được inject vào command hoặc coordinator thường giúp ranh giới này rõ ràng.

## 13. Không dùng ThreadLocal làm nơi lưu task context mặc định

`ThreadLocal` gắn dữ liệu với thread hiện tại, không gắn với một tác vụ logic. Khi dùng thread pool:

- Tác vụ có thể chạy trên thread khác với thread nhận command.
- Một thread được tái sử dụng cho nhiều tác vụ.
- Callback hoặc continuation có thể chạy trên thread khác.
- Giá trị cũ có thể còn lại nếu code không gọi `remove()` trong `finally`.

Vì vậy, không nên đặt task ID, project hiện tại, người dùng hiện tại hoặc request nghiệp vụ vào `ThreadLocal` rồi mong chúng tự theo tác vụ qua executor. Truyền context tường minh qua tham số là cách dễ kiểm tra nhất.

`TaskDecorator` của Spring có thể bọc một `Runnable` trước khi executor thực thi. Nó hữu ích để truyền ngữ cảnh kỹ thuật như MDC correlation ID hoặc trace context khi đã có chính sách capture/restore/clear rõ ràng. Decorator không biến ThreadLocal thành scope theo task và không nên thay thế request object.

Spring có `SimpleThreadScope`, nhưng scope này không được đăng ký mặc định. Javadoc cũng lưu ý nó không tự cleanup object gắn với thread. Thread scope còn gắn với thread pool worker thay vì vòng đời logic của task, nên thường không phải lựa chọn tốt để cô lập trạng thái từng tác vụ trong CLI.

## 14. Dữ liệu trong bộ nhớ và dữ liệu bền vững

Một `ConcurrentHashMap` an toàn với truy cập đồng thời trong một JVM nhưng không bảo đảm dữ liệu sống qua lần chạy tiếp theo. Khi CLI đóng, trạng thái task trong map mất đi. Nếu ứng dụng cần:

- Tiếp tục tác vụ sau khi tiến trình khởi động lại.
- Cho phép nhiều instance CLI hoặc worker cùng xem trạng thái.
- Lưu lịch sử, audit và kết quả lỗi.
- Ngăn hai tiến trình cùng xử lý một job.

thì cần lưu trạng thái vào database hoặc kho lưu trữ dùng chung. Có thể dùng bảng job với ID, trạng thái, tiến độ, thời điểm cập nhật và version. Dùng optimistic locking hoặc câu lệnh cập nhật có điều kiện để tránh hai worker cùng chuyển trạng thái không hợp lệ.

Đừng nhầm transaction database với khóa Java. `synchronized` chỉ bảo vệ các thread trong cùng một JVM và cùng monitor; nó không ngăn một tiến trình khác hoặc một máy khác ghi cùng bản ghi. Ràng buộc database, transaction và cơ chế claim job mới bảo vệ được bất biến ở phạm vi lưu trữ dùng chung.

## 15. Kiểm thử khi nhiều tác vụ dùng chung bean

Kiểm thử tuần tự thường không phát hiện race condition. Hãy tạo tình huống có chồng lấp thực sự bằng `CountDownLatch`, `CyclicBarrier` hoặc executor trong test.

Các trường hợp nên có:

1. Hai lần gọi cùng một singleton service với hai request khác nhau không làm lẫn dữ liệu.
2. Nhiều task ID được tạo và cập nhật đồng thời; không mất hoặc ghi đè trạng thái của task khác.
3. Các cập nhật tiến độ cho cùng một task tuân thủ quy tắc trạng thái và không giảm ngoài dự kiến.
4. Queue đầy được báo rõ và không để task mắc ở `QUEUED`.
5. Exception trong worker chuyển đúng task sang `FAILED` và được ghi log.
6. Command `task status` đọc snapshot trong khi worker đang cập nhật mà không gặp lỗi truy cập collection.
7. Prototype context lấy qua `ObjectProvider` tạo instance mới cho mỗi lần yêu cầu.
8. Transaction bắt đầu trong worker thread và rollback khi worker thất bại.
9. Shutdown chờ hoặc hủy tác vụ theo chính sách executor đã cấu hình.
10. Nếu trạng thái phải bền vững, khởi động lại ứng dụng không làm mất dữ liệu job đã lưu.

Để phát hiện lỗi field dùng chung, có thể cố ý chặn hai task tại một điểm bằng latch để buộc chúng xen kẽ. Kiểm tra kết quả cuối cùng theo từng ID, không chỉ kiểm tra tổng số task đã chạy.

## 16. Quy trình chọn cách quản lý state

1. Xác định bean nào được nhiều command hoặc tác vụ dùng chung.
2. Xóa dữ liệu tạm theo lần gọi khỏi field của singleton; chuyển thành biến cục bộ hoặc request object.
3. Dùng immutable object cho cấu hình và snapshot trạng thái.
4. Nếu cần object stateful riêng cho từng task, tạo context riêng và truyền theo task; chỉ dùng prototype khi thật sự cần Spring tạo object.
5. Dùng `ObjectProvider` nếu singleton cần yêu cầu prototype instance mới ở thời điểm chạy.
6. Dùng atomic hoặc concurrent collection cho thao tác chia sẻ phù hợp; khóa các bất biến nhiều bước.
7. Đặt transaction ở service được gọi trong worker thread.
8. Dùng database nếu trạng thái cần bền vững hoặc chia sẻ giữa nhiều tiến trình.
9. Kiểm thử với các tác vụ chạy chồng lấp và xác nhận không có state leakage.

## Kết luận

Trong Spring Shell, command và service thường là singleton bean, vì vậy nhiều tác vụ có thể dùng chung một instance. Bean singleton an toàn khi giữ cấu hình và logic stateless; dữ liệu riêng của một lần thực thi nên nằm trong biến cục bộ hoặc request/task context được truyền tường minh. Khi cần theo dõi nhiều tác vụ nền, dùng ID riêng và registry thread-safe với snapshot immutable. `prototype` chỉ tạo instance mới khi container được yêu cầu; inject trực tiếp prototype vào singleton không làm nó tự đổi instance ở mỗi lần gọi. Với trạng thái chia sẻ, chọn atomic, concurrent collection hoặc lock theo bất biến; với dữ liệu cần tồn tại sau restart hoặc chia sẻ giữa nhiều tiến trình, dùng kho lưu trữ bền vững.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Command Registration](https://docs.spring.io/spring-shell/reference/3.4/commands/registration.html)
- [Spring Framework 6.2 – Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html)
- [Spring Framework 6.2 – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 – SimpleThreadScope Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/support/SimpleThreadScope.html)
- [Java – ConcurrentHashMap API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Java – AtomicReference API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
