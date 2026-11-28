# Tiến trình treo do chờ đầu vào, luồng nền hoặc tài nguyên chưa đóng

Một ứng dụng Spring Shell có thể trông như bị treo trong ba tình huống khác nhau: command đang chờ người dùng nhập dữ liệu, command đã trả kết quả nhưng một luồng nền vẫn giữ JVM sống, hoặc quá trình shutdown đang chờ executor và tài nguyên được đóng. Cả ba đều có thể khiến cửa sổ terminal không trả prompt hoặc lệnh chạy trong CI không kết thúc.

Cách xử lý hiệu quả bắt đầu bằng việc xác định tiến trình đang chờ ở đâu. Nếu thread chính đang đọc terminal, hãy kiểm tra runner và luồng STDIN. Nếu command đã in kết quả nhưng JVM vẫn sống, hãy tìm các non-daemon thread và executor chưa dừng. Nếu ứng dụng đang đóng context, hãy kiểm tra task chưa hoàn thành, timeout I/O và callback đóng tài nguyên.

Bài viết dùng Spring Shell 3.4.x làm ví dụ chính, đồng thời ghi rõ khác biệt runner ở 4.x. Các ví dụ Java áp dụng cho ứng dụng Spring Boot/Spring Shell thông thường; hãy thay tên command, executor và resource bằng thành phần thực tế của dự án.

## Nhận diện đúng triệu chứng

Không phải mọi tiến trình còn chạy đều bị treo. Một REPL tương tác phải tiếp tục sống để chờ command tiếp theo. Một command dài cũng có thể đang làm việc bình thường. Trước khi sửa code, hãy xác định thời điểm tiến trình dừng tiến triển.

| Triệu chứng | Nguyên nhân có thể | Dấu hiệu cần tìm |
| --- | --- | --- |
| Command không trả kết quả, con trỏ đứng ở prompt nhập liệu | Command hoặc UI component đang chờ input | Thread đang đọc terminal, System.in, JLine hoặc vòng lặp UI |
| Command đã in kết quả nhưng tiến trình không thoát | Executor, scheduler hoặc thread nền còn sống | Thread pool, timer, client I/O hoặc consumer thread vẫn hoạt động |
| Tiến trình chỉ chậm khi shutdown | Task không kết thúc hoặc shutdown đang chờ | Thread ở trạng thái WAITING/TIMED_WAITING, Future chưa hoàn tất, callback close bị chặn |
| Chạy tốt trong terminal nhưng treo ở CI/container | Command vẫn hỏi input hoặc STDIN còn mở | Không có TTY, input bị redirect, Docker giữ STDIN mở |
| Chỉ treo khi xử lý dữ liệu lớn | Pool cạn, queue đầy, deadlock hoặc I/O không có timeout | Nhiều worker cùng chờ, lock contention, socket read |
| Ứng dụng chạy xong khi nhấn Ctrl+C | Có luồng nền không được đóng hoặc runner đang chờ input | Shutdown hook mới giải phóng tài nguyên hoặc signal làm luồng dừng |

Hãy ghi lại ba mốc thời gian: lúc gọi command, lúc command in kết quả cuối cùng và lúc JVM thực sự kết thúc. Nếu kết quả đã in nhưng process còn sống, đừng tiếp tục sửa phần thân command trước khi kiểm tra thread nền.

## Bước đầu: xác minh chế độ chạy của Spring Shell

Spring Shell có runner tương tác và runner non-interactive. Chế độ tương tác được thiết kế để giữ shell mở, chờ người dùng nhập command tiếp theo. Đây là hành vi đúng khi chạy REPL, nhưng không phù hợp với một tác vụ batch cần thực thi xong rồi thoát.

Trong Spring Shell 3.4.x, có ba runner:

| Runner | Mục đích |
| --- | --- |
| InteractiveShellRunner | Mở REPL và chờ người dùng nhập nhiều command |
| NonInteractiveShellRunner | Chạy command được truyền qua đối số tiến trình rồi kết thúc |
| ScriptShellRunner | Chạy file script được truyền qua đối số dạng @/path/file |

Từ Spring Shell 3.3.x, chỉ NonInteractiveShellRunner được bật mặc định. Muốn bật REPL hoặc script runner, cấu hình rõ ràng:

~~~yaml
spring:
  shell:
    interactive:
      enabled: true
    noninteractive:
      enabled: true
    script:
      enabled: true
~~~

Trong Spring Shell 4.x, interactive mode được bật mặc định. Nếu mục tiêu là chạy command từ process arguments rồi thoát, đặt:

~~~yaml
spring:
  shell:
    interactive:
      enabled: false
~~~

Không nên đoán runner dựa vào việc có hay không có prompt. Hãy kiểm tra cấu hình thực tế, version và cách command được truyền khi khởi động.

Trong Spring Shell 3.4.x, ShellContext phân biệt chế độ tương tác với khả năng PTY:

~~~java
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.context.ShellContext;

public boolean isInteractive(ShellContext shellContext) {
    return shellContext.getInteractionMode() == InteractionMode.INTERACTIVE;
}

public boolean hasTerminal(ShellContext shellContext) {
    return shellContext.hasPty();
}
~~~

Hai giá trị trả lời hai câu hỏi khác nhau. InteractionMode cho biết shell đang chạy REPL hay non-interactive command; hasPty cho biết terminal có pseudo-terminal hay không. Một tiến trình có thể chạy command non-interactive trong khi STDOUT được pipe, hoặc có terminal nhưng vẫn chạy một command rồi kết thúc.

## Command đang chờ input

### Nhận diện prompt bị bỏ quên

Một command có thể vô tình yêu cầu input khi chạy trong CI:

- Gọi Scanner.nextLine() hoặc BufferedReader.readLine() trên STDIN.
- Dùng ConfirmationInput, StringInput, selector hoặc ComponentFlow.
- Chạy TerminalUI.run() hoặc một vòng lặp UI có tính blocking.
- Gọi một thư viện tương tác yêu cầu nhập password, xác nhận hoặc chọn profile.
- Chờ Future/CompletableFuture trong khi công việc nền lại chờ input từ chính command.

Spring Shell có các component nhập liệu như ConfirmationInput. Component này có vòng lặp đọc phím và chỉ trả kết quả khi người dùng hoàn thành thao tác. Đây là lựa chọn phù hợp cho REPL có terminal, nhưng không nên gọi vô điều kiện trong command batch.

Ví dụ một command hỏi xác nhận:

~~~java
import org.springframework.shell.component.ConfirmationInput;
import org.springframework.shell.standard.AbstractShellComponent;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class ArtifactCommands extends AbstractShellComponent {

    private final ArtifactService artifactService;

    public ArtifactCommands(ArtifactService artifactService) {
        this.artifactService = artifactService;
    }

    @ShellMethod(key = "artifact delete", value = "Xóa artifact")
    public String delete(String name) {
        ConfirmationInput input =
                new ConfirmationInput(getTerminal(), "Delete " + name + "?", false);
        input.setResourceLoader(getResourceLoader());
        input.setTemplateExecutor(getTemplateExecutor());

        ConfirmationInput.ConfirmationInputContext result =
                input.run(ConfirmationInput.ConfirmationInputContext.empty());

        if (!result.getResultValue()) {
            return "Đã hủy thao tác";
        }

        artifactService.delete(name);
        return "Đã xóa " + name;
    }
}
~~~

Nếu command này được gọi từ script hoặc CI, không có người dùng để trả lời. Hãy thay prompt bằng một option rõ ràng, ví dụ --yes, hoặc từ chối chạy nếu không có chế độ tương tác.

~~~java
@ShellMethod(key = "artifact delete", value = "Xóa artifact")
public String delete(
        String name,
        @ShellOption(defaultValue = "false") boolean yes) {

    if (!yes) {
        throw new IllegalArgumentException(
                "Hãy xác nhận bằng --yes khi chạy command này");
    }

    artifactService.delete(name);
    return "Đã xóa " + name;
}
~~~

Với thao tác phá hủy dữ liệu, không nên tự động coi EOF hoặc thiếu TTY là đồng ý. Yêu cầu người gọi truyền --yes một cách chủ động giúp command batch có thể dự đoán được.

### Xử lý EOF thay vì chờ vô hạn

Nếu code tự đọc STDIN, phải xử lý trường hợp không còn dữ liệu. BufferedReader.readLine() trả về null khi luồng đã kết thúc. Không lặp lại readLine() vô hạn khi nhận EOF.

~~~java
String line = reader.readLine();
if (line == null) {
    throw new IllegalStateException(
            "Không có dữ liệu đầu vào; hãy truyền --file hoặc pipe dữ liệu vào STDIN");
}
~~~

Không đóng System.in trong command nếu luồng này do shell quản lý. Đóng nó có thể làm các command tiếp theo trong cùng REPL không đọc được input nữa. Với dữ liệu file do command tự mở, dùng try-with-resources để đóng stream đó.

### Phân biệt STDIN, TTY và interaction mode

Trong Docker, ba cấu hình thường bị nhầm:

| Tùy chọn | Tác dụng |
| --- | --- |
| -i | Giữ STDIN mở cho container |
| -t | Cấp pseudo-terminal |
| -it | Vừa giữ STDIN vừa cấp pseudo-terminal |

Một container chạy REPL thường dùng docker run -it. Một command batch thường không cần -t; chỉ dùng -i nếu command thực sự đọc dữ liệu từ pipe. Nếu dùng -i mà không gửi EOF hoặc không đóng đầu pipe, chương trình có thể tiếp tục chờ dữ liệu.

Ví dụ chạy batch bằng file:

~~~bash
docker run --rm \
  --mount type=bind,src="$PWD/input",dst=/input,readonly \
  spring-shell-cli:1.0 \
  artifact import --file /input/data.csv
~~~

Ví dụ đọc CSV từ STDIN:

~~~bash
cat ./input/data.csv | docker run --rm -i spring-shell-cli:1.0 artifact import --stdin
~~~

Command phải có nhánh xử lý --stdin và kết thúc khi nhận EOF. -i chỉ giữ luồng mở; nó không tự chuyển dữ liệu pipe thành tham số command.

## Command không trả về vì I/O đang chờ

Một command có thể không hỏi terminal nhưng vẫn chờ mạng, database, filesystem hoặc process con.

Các lời gọi dễ chờ lâu nếu không có timeout:

- HTTP connect/read/response.
- JDBC query hoặc lấy connection từ pool.
- Socket read hoặc accept.
- Đọc file từ filesystem mạng.
- ProcessBuilder.waitFor() khi process con không thoát.
- Future.get() hoặc CompletableFuture.join() khi task chưa hoàn thành.
- Lock, semaphore hoặc queue chờ tài nguyên.

Đặt timeout tại đúng lớp thực hiện I/O. Timeout ở command không thể tự giải phóng một socket hoặc query đang bị kẹt nếu thư viện bên dưới không hỗ trợ cancellation.

Ví dụ với Java HttpClient:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(20))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
~~~

Connect timeout giới hạn thời gian thiết lập kết nối; request timeout giới hạn thời gian chờ phản hồi. Với JDBC, cấu hình connection timeout của pool và query timeout của statement theo chính sách hệ thống. Với thư viện khác, tìm thuộc tính connect timeout, read timeout, call timeout hoặc request timeout tương ứng.

Nếu command chờ một Future, đặt thời hạn và xử lý timeout:

~~~java
try {
    ImportResult result = future.get(30, TimeUnit.SECONDS);
    return "Đã nhập " + result.count() + " bản ghi";
}
catch (TimeoutException exception) {
    future.cancel(true);
    throw new IllegalStateException("Tác vụ nhập quá thời hạn 30 giây", exception);
}
catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Command bị ngắt khi đang chờ tác vụ", exception);
}
catch (ExecutionException exception) {
    throw new IllegalStateException("Tác vụ nhập thất bại", exception.getCause());
}
~~~

Với Future do ExecutorService trả về, cancel(true) yêu cầu ngắt task đang chạy; task phải hợp tác với interrupt để dừng. Với CompletableFuture, cancel(true) không bảo đảm interrupt thread đang tính toán. Nếu cần dừng công việc nền, hãy dùng cơ chế cancellation rõ ràng hoặc giữ Future phù hợp với executor. Nếu code nghiệp vụ nuốt InterruptedException hoặc bỏ qua cờ interrupted, lệnh hủy có thể không giải phóng worker.

## Tiến trình còn sống sau khi command hoàn tất

### Vì sao JVM chưa thoát?

JVM bắt đầu shutdown khi không còn platform thread non-daemon nào đang chạy, trừ khi có yêu cầu shutdown khác. Vì vậy, command trả về không có nghĩa JVM phải kết thúc ngay. Một executor hoặc thư viện có thể vẫn giữ worker thread sống.

Các nguồn thường gặp:

- Executors.newFixedThreadPool() hoặc newSingleThreadExecutor() được tạo nhưng không shutdown.
- ScheduledExecutorService hoặc Timer còn lịch chạy.
- Thread tự tạo bằng new Thread() không kết thúc.
- Consumer/listener chạy vòng lặp chờ message.
- Client SDK có connection manager hoặc event loop riêng.
- Một task nền đang chờ queue, lock hoặc I/O.
- TerminalUI event loop vẫn đang chạy.

Không chữa bằng cách đổi tất cả thread sang daemon. Daemon thread không giữ JVM sống, nhưng JVM có thể dừng chúng giữa chừng khi process kết thúc; dữ liệu đang ghi, giao dịch hoặc cleanup có thể bị bỏ dở. Hãy quản lý vòng đời thread và tài nguyên đúng cách.

### Dùng executor do Spring quản lý

Ưu tiên ThreadPoolTaskExecutor hoặc TaskScheduler được khai báo thành Spring bean. Spring quản lý lifecycle của executor khi ApplicationContext đóng.

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("shellJobExecutor")
    public ThreadPoolTaskExecutor shellJobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("shell-job-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
~~~

Tên thread có prefix rõ ràng giúp tìm executor trong thread dump. Queue có giới hạn tránh việc command gửi nhanh hơn tốc độ xử lý rồi tích lũy task vô hạn. Cấu hình chờ task khi shutdown cho phép task đang chạy và task trong queue có thời gian hoàn thành; await termination đặt giới hạn thời gian chờ. Nếu task có thể treo vô hạn, shutdown vẫn có thể kéo dài tới timeout đã cấu hình.

Có thể dùng executor này từ service:

~~~java
@Service
public class ImportService {

    @Async("shellJobExecutor")
    public CompletableFuture<ImportResult> importFile(Path file) {
        ImportResult result = doImport(file);
        return CompletableFuture.completedFuture(result);
    }

    private ImportResult doImport(Path file) {
        // Đọc file và nhập dữ liệu; mọi stream phải được đóng.
        return new ImportResult(0);
    }
}
~~~

Lưu ý @Async mặc định hoạt động qua Spring proxy. Gọi một method @Async từ method khác trong cùng instance không đi qua proxy nên có thể chạy đồng bộ trên thread gọi. Nếu command bất ngờ chạy tác vụ dài ngay trên thread shell, hãy kiểm tra lời gọi có đi qua proxy hay không và kiểm tra executor được chọn.

Kiểm tra cả implementation thực tế của TaskExecutor. SyncTaskExecutor luôn chạy task trên thread gọi; CallerRunsPolicy của ThreadPoolExecutor cũng có thể chạy task ngay trên thread gửi khi pool quá tải. Hai cấu hình này khiến command tưởng như đã gửi việc nền nhưng vẫn bị chặn để thực hiện công việc.

Task cần hợp tác với interrupt:

~~~java
public void processRecords(List<Record> records) {
    for (Record record : records) {
        if (Thread.currentThread().isInterrupted()) {
            return;
        }

        process(record);
    }
}
~~~

Nếu một lời gọi có thể ném InterruptedException:

~~~java
try {
    blockingOperation();
}
catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Không bắt InterruptedException rồi bỏ qua. Việc khôi phục interrupt status giúp tầng gọi phía trên biết task đã được yêu cầu dừng.

### Tránh chờ lẫn nhau trong cùng thread pool

Một dạng treo khó nhận ra là task trong pool lại gửi một task con vào cùng pool rồi chờ task con hoàn thành. Nếu toàn bộ worker đều đang chờ task con, không còn worker rảnh để chạy chúng.

Ví dụ cấu hình pool chỉ có hai worker:

~~~java
executor.execute(() -> {
    Future<?> child = executor.submit(this::doChildWork);
    child.get();
});
~~~

Nếu cả hai worker cùng chạy đoạn code này, hai task con có thể nằm trong queue trong khi không còn worker để thực thi. Đây là thread starvation/deadlock do thiết kế.

Cách sửa là không block chờ task con trong chính pool đã cạn worker; dùng composition của CompletableFuture, một executor riêng cho công việc con, hoặc tăng concurrency sau khi hiểu rõ giới hạn tài nguyên bên dưới. Không chỉ tăng pool size mà không kiểm tra tải và số lượng kết nối.

## Tài nguyên chưa đóng

Một tài nguyên chưa đóng có thể giữ thread, socket, file handle hoặc connection. Hãy phân biệt tài nguyên thuộc quyền sở hữu của command với tài nguyên được Spring container chia sẻ.

### Đóng stream và file bằng try-with-resources

~~~java
public long countLines(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.lines().count();
    }
}
~~~

Stream được mở trong command nên được đóng trong cùng phạm vi. Không giữ stream mở trong field singleton nếu command không có cơ chế quản lý vòng đời rõ ràng.

### Để Spring quản lý resource dùng chung

Các bean như DataSource, connection pool, executor hoặc client dùng chung nên được cấu hình thành bean và đóng qua lifecycle của container. Không đóng DataSource hoặc executor được inject dùng chung sau mỗi command; command khác có thể đang sử dụng chúng.

Với resource tự tạo trong bean, dùng @PreDestroy hoặc destroyMethod:

~~~java
@Component
public class RemoteClientHolder {

    private final CloseableRemoteClient client;

    public RemoteClientHolder(CloseableRemoteClient client) {
        this.client = client;
    }

    @PreDestroy
    public void close() throws IOException {
        client.close();
    }
}
~~~

Nếu client là bean do thư viện hoặc auto-configuration tạo, hãy kiểm tra bean có destroy method/lifecycle tự động hay không trước khi tự đóng lần nữa.

Ví dụ trên giả định RemoteClientHolder sở hữu vòng đời của client. Nếu client được khai báo thành một bean riêng và được nhiều thành phần dùng chung, hãy để bean tạo client khai báo destroyMethod="close"; không đóng lại cùng resource từ một bean tiêu thụ khác.

### Dừng background service bằng lifecycle

Nếu bean tự khởi động một vòng lặp nền, hãy cung cấp phương thức dừng. Với tiến trình có shutdown bất đồng bộ hoặc cần thứ tự dừng giữa nhiều bean, cân nhắc SmartLifecycle. Spring gửi tín hiệu stop trước các destruction callback trong quá trình đóng context bình thường.

~~~java
@Component
public class QueueWorker implements SmartLifecycle {

    private volatile boolean running;
    private Thread worker;

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        running = true;
        worker = new Thread(this::runLoop, "queue-worker");
        worker.start();
    }

    private void runLoop() {
        while (running && !Thread.currentThread().isInterrupted()) {
            // Poll với timeout hữu hạn, xử lý message hoặc quay lại kiểm tra cờ dừng.
        }
    }

    @Override
    public synchronized void stop() {
        running = false;
        if (worker != null) {
            worker.interrupt();
            try {
                worker.join(5000);
                if (worker.isAlive()) {
                    throw new IllegalStateException(
                            "Queue worker không dừng trong 5 giây");
                }
            }
            catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Bị ngắt khi đang dừng queue worker", exception);
            }
        }
    }

    @Override
    public void stop(Runnable callback) {
        stop();
        callback.run();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

Ví dụ minh họa một worker đơn giản. Trong ứng dụng thực tế, ưu tiên executor được Spring quản lý thay vì tự tạo Thread. Nếu dùng thread riêng, phải bảo đảm vòng lặp có thể thoát khi bị interrupt và stop callback chỉ được gọi sau khi worker thực sự dừng.

## Shutdown đang chờ task

Khi Spring ApplicationContext đóng, các bean có lifecycle được dừng và các destruction callback được gọi. Nếu một task vẫn đang chạy, quá trình đóng có thể chờ executor hoàn thành task theo chính sách đã cấu hình.

Các điểm cần kiểm tra:

- Task có thời hạn tối đa hay có thể chờ mạng vô hạn?
- Executor có chấp nhận task mới trong giai đoạn context đang đóng không?
- Queue có quá nhiều task cần xử lý hết trước khi shutdown không?
- Task có phản hồi interrupt không?
- Callback @PreDestroy có thực hiện I/O đồng bộ không?
- Bean phụ thuộc đã bị đóng trước khi task cuối cùng sử dụng xong chưa?

Chỉ đặt waitForTasksToCompleteOnShutdown=true không đảm bảo shutdown nhanh. Cấu hình này có thể khiến executor tiếp tục chạy toàn bộ queue. Hãy đặt queue capacity hữu hạn, thời hạn task và await termination phù hợp với thời gian shutdown mà hệ thống chấp nhận.

Không dùng System.exit(0) để che một executor hoặc resource chưa được đóng. Lệnh này khởi động quá trình shutdown của JVM nhưng không giải quyết nguyên nhân khiến thread bị kẹt; các worker đang chạy có thể bị dừng trước khi hoàn tất công việc. Hãy để runner kết thúc đúng chế độ, đóng ApplicationContext và trả exit code phù hợp.

## Lấy thread dump để tìm vị trí đang chờ

Thread dump là ảnh chụp stack của các thread tại một thời điểm. Nó giúp xác định thread nào đang đọc input, chờ Future, bị block bởi lock hoặc chờ socket.

### Dùng jcmd

Liệt kê JVM đang chạy:

~~~bash
jcmd -l
~~~

Lấy thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Để có thông tin lock:

~~~bash
jcmd <pid> Thread.print -l
~~~

Chạy lệnh này trên cùng máy với JVM và bằng user có quyền truy cập process. Trên Windows, jcmd có trong JDK; trong container, cần image có JDK hoặc cơ chế chẩn đoán tương đương để attach vào JVM.

Nếu không có jcmd, có thể dùng jstack <pid> hoặc gửi SIGQUIT/kill -3 trên hệ điều hành hỗ trợ. Thread dump thường được ghi vào STDERR của tiến trình hoặc log của JVM.

### Đọc trạng thái thread

| Trạng thái | Ý nghĩa thường gặp | Cách điều tra |
| --- | --- | --- |
| RUNNABLE | Đang chạy hoặc đang ở native I/O | Kiểm tra CPU, stack và lời gọi socket/file |
| BLOCKED | Đang chờ monitor lock | Tìm thread đang giữ lock và chuỗi gọi liên quan |
| WAITING | Chờ vô thời hạn một điều kiện | Tìm join, Future.get, queue take hoặc condition wait |
| TIMED_WAITING | Chờ có thời hạn | Kiểm tra sleep, poll, await hoặc timeout |
| TERMINATED | Thread đã kết thúc | Không phải nguyên nhân giữ JVM sống |

RUNNABLE không đồng nghĩa với CPU đang bận; thread có thể đang nằm trong lời gọi native chờ I/O. Hãy đọc stack trace và tên thread, không kết luận chỉ từ trạng thái.

Tên thread giúp khoanh vùng:

| Tên thường gặp | Thành phần có thể liên quan |
| --- | --- |
| main | Khởi động ứng dụng, command runner hoặc code đang chờ đồng bộ |
| shell / JLine | Đọc terminal hoặc vòng lặp REPL |
| shell-job-* | Executor được cấu hình với thread name prefix |
| scheduling-* | Scheduler hoặc task định kỳ |
| pool-* | Executor được tạo bởi thư viện hoặc ứng dụng |
| http-* / client-* | HTTP client, event loop hoặc SDK bên ngoài |
| queue-worker | Worker xử lý message do ứng dụng tạo |

Hãy lấy hai hoặc ba thread dump cách nhau vài giây. Nếu stack của một thread không đổi, nó có thể đang chờ vô thời hạn hoặc bị kẹt ở cùng một lời gọi. Nếu stack thay đổi và tiến trình vẫn tiêu thụ CPU/I/O, tác vụ có thể đang tiến triển chậm thay vì deadlock.

### Ví dụ dấu hiệu trong stack

- Thread ở BufferedReader.readLine, Scanner.nextLine hoặc JLine input: đang chờ dữ liệu terminal.
- Thread ở FutureTask.get, CompletableFuture.join hoặc CountDownLatch.await: đang chờ tác vụ/điều kiện khác.
- Thread ở SocketDispatcher.read, SocketInputStream.socketRead0 hoặc HTTP client read: đang chờ I/O mạng.
- Thread ở AbstractQueuedSynchronizer hoặc ReentrantLock: đang chờ lock/semaphore.
- Worker ở LinkedBlockingQueue.take: đang chờ task mới; bản thân điều này thường bình thường nếu executor còn được quản lý.
- Nhiều worker cùng chờ Future của task con trong cùng pool: nghi ngờ thread starvation.

Nếu có deadlock, thread dump có thể chỉ ra chuỗi lock và thread liên quan. Hãy lưu toàn bộ dump, không chỉ copy vài dòng đầu.

## Quy trình chẩn đoán theo từng bước

1. Xác định ứng dụng đang chạy REPL hay batch. Kiểm tra Spring Shell version, runner property và command arguments.
2. Xác định command đã kết thúc chưa. Tìm log kết quả cuối, thời gian trả về và exit code.
3. Nếu command chưa trả về, lấy thread dump. Tìm main/shell thread và stack đang chờ input, I/O, Future hay lock.
4. Nếu command đã trả kết quả nhưng JVM còn sống, liệt kê các thread non-daemon và xác định executor, scheduler, Timer hoặc client sở hữu chúng.
5. Nếu đang shutdown, kiểm tra executor queue, task đang chạy, await termination và @PreDestroy/SmartLifecycle callback.
6. Đặt timeout ở I/O và Future. Bảo đảm cancellation được task thực thi.
7. Đóng resource do command sở hữu bằng try-with-resources; resource dùng chung để Spring quản lý lifecycle.
8. Chạy lại trong terminal có TTY, non-interactive mode và CI/container để so sánh.
9. Kiểm tra tiến trình kết thúc tự nhiên và trả exit code đúng; không dùng System.exit để che lỗi cleanup.

## Ma trận kiểm thử để tránh tái phát

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| REPL có TTY | Chạy shell và nhập nhiều command | Shell tiếp tục mở cho đến khi người dùng quit/exit |
| Batch không có TTY | Truyền command qua process arguments | Command chạy xong, process kết thúc |
| Command cần xác nhận | Chạy với và không có --yes | Thiếu xác nhận thì fail rõ ràng, không chờ input |
| STDIN đã EOF | Pipe file hoặc input rỗng | Command nhận EOF và kết thúc hoặc báo lỗi |
| Network chậm | Mô phỏng server không phản hồi | Timeout xảy ra trong thời hạn đã cấu hình |
| Task nền đang chạy | Gửi yêu cầu shutdown | Task hoàn tất hoặc bị hủy trong giới hạn thời gian |
| Executor queue đầy | Gửi nhiều job hơn khả năng xử lý | Từ chối hoặc backpressure theo chính sách, không tăng vô hạn |
| Resource mở | Chạy nhiều lần và đóng context | File/socket/connection được giải phóng |
| Worker bị interrupt | Gửi stop trong khi worker đang poll | Worker nhận interrupt và dừng |
| CI/container | Chạy không có TTY và kiểm tra exit code | Không chờ prompt; stdout/stderr và exit code có thể xử lý tự động |

Với Spring Shell, có thể dùng ShellTestClient để kiểm thử command ở interactive hoặc non-interactive mode. Ngoài test command, nên có một integration test chạy executable JAR như process con, chờ trong một thời hạn và xác minh process exit code. Test gọi trực tiếp method command không thể phát hiện một thread non-daemon còn sống sau khi command trả về.

## Những lỗi thường gặp

| Cách xử lý sai | Vì sao không hiệu quả | Cách sửa |
| --- | --- | --- |
| Luôn bật interactive runner cho job CI | Shell có thể chờ command tiếp theo hoặc prompt | Chọn non-interactive mode theo phiên bản |
| Dùng ConfirmationInput trong batch | Không có người dùng để trả lời | Yêu cầu option --yes hoặc từ chối chạy |
| Dùng Scanner.nextLine mà không xử lý EOF | Có thể chờ hoặc xử lý sai input rỗng | Kiểm tra EOF và đưa ra lỗi có hướng dẫn |
| Giữ Docker STDIN mở không cần thiết | Process có thể tiếp tục chờ input | Bỏ -i nếu không đọc STDIN |
| Gọi join/get vô hạn | Command không có thời hạn chờ | Dùng timeout, cancel và xử lý interrupt |
| Tạo executor bằng Executors nhưng quên shutdown | Worker non-daemon giữ JVM sống | Dùng executor Spring-managed hoặc shutdown trong finally |
| Tạo Timer/thread trong command | Thread sống lâu hơn command | Đưa lifecycle vào bean hoặc kết thúc thread đúng cách |
| Đổi thread sang daemon để JVM thoát | Task có thể bị dừng giữa chừng | Đóng executor và resource có kiểm soát |
| Nuốt InterruptedException | Task không phản hồi shutdown | Khôi phục interrupt status và thoát |
| Chờ task con trong cùng pool đã cạn | Worker chờ lẫn nhau, task con không có worker | Dùng composition hoặc pool riêng |
| Đóng DataSource dùng chung trong command | Command sau không còn kết nối | Để container quản lý resource dùng chung |
| Đặt timeout chỉ ở command | Lời gọi I/O bên dưới có thể vẫn giữ thread | Đặt timeout ở HTTP/JDBC/socket client |
| Dùng System.exit để kết thúc | Che lỗi lifecycle và làm khó kiểm thử | Đóng context, dừng executor và trả exit code đúng |

## Checklist khi một command có vẻ bị treo

- [ ] Đã xác định process đang ở interactive hay non-interactive mode.
- [ ] Đã kiểm tra TTY và STDIN có được giữ mở không.
- [ ] Không có prompt/ConfirmationInput/TerminalUI chờ trong batch path.
- [ ] Đã kiểm tra EOF cho luồng input.
- [ ] Các lời gọi HTTP, JDBC, socket và process con đều có timeout.
- [ ] Future.get/join có giới hạn thời gian.
- [ ] Executor và scheduler được Spring quản lý hoặc có shutdown rõ ràng.
- [ ] Task xử lý đúng InterruptedException.
- [ ] Resource do command mở được đóng bằng try-with-resources.
- [ ] Resource dùng chung có lifecycle callback phù hợp.
- [ ] Đã lấy thread dump khi lỗi còn xảy ra.
- [ ] Process batch kết thúc tự nhiên và trả exit code đúng.

Một tiến trình Spring Shell chỉ nên tiếp tục sống khi còn công việc hoặc phiên tương tác cần phục vụ. Khi command batch đã hoàn tất, mọi task nền và tài nguyên phải có đường kết thúc rõ ràng. Phân biệt chờ input, chờ I/O, worker còn sống và shutdown đang chờ sẽ giúp tìm đúng nguyên nhân thay vì chỉ thay đổi runner hoặc ép JVM thoát.

## Tài liệu tham khảo

- [Execution – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/execution.html)
- [Shell Context – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/shellcontext.html)
- [Confirmation component – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/components/ui/confirmation.html)
- [Execution – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/execution.html)
- [TerminalUI – Spring Shell 4.0.2](https://docs.spring.io/spring-shell/reference/tui/intro/terminalui.html)
- [Task Execution and Scheduling – Spring Framework](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Customizing the Nature of a Bean – Spring Framework](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [ExecutorConfigurationSupport API – Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html)
- [Thread API – Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Runtime API – Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html)
- [JDK Diagnostic Tools and jcmd – Java SE 21](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)

