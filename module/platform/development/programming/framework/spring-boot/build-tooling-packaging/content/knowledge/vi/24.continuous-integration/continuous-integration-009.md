# Quản lý timeout, tác vụ đồng thời và dọn tiến trình sau khi kiểm tra

## 1. Mục tiêu và phạm vi

Một pipeline kiểm thử Spring Boot thường khởi chạy nhiều thứ ngoài JVM của Maven/Gradle: ứng dụng web, database, message broker, Docker containers, mock servers, browser drivers, subprocesses và nhiều test workers. Nếu một tác vụ bị treo hoặc không được dọn đúng cách, CI có thể hết thời gian, cổng TCP bị chiếm, database còn dữ liệu cũ, process con tiếp tục chạy hoặc test job sau bị ảnh hưởng.

Ba vấn đề cần giải quyết riêng:

1. **Timeout:** xác định một thao tác được phép chạy bao lâu, deadline của cả test/job là bao lâu, và phải làm gì khi vượt giới hạn.
2. **Concurrency:** chạy các test/tác vụ đồng thời có giới hạn, tránh tranh chấp port/file/database và không tạo quá nhiều process/thread.
3. **Cleanup:** khi test pass, fail, timeout hoặc bị interrupt, dừng ứng dụng/process/container, đóng resource và thu thập log cần thiết.

Một thiết kế đáng tin cậy cần phối hợp **JUnit timeout, Maven/Gradle test workers, Java ExecutorService, ProcessBuilder, Docker cleanup và CI job timeout**. Không có một cờ timeout duy nhất bảo vệ tất cả các tầng.

Sau bài này, bạn có thể:

- Phân biệt timeout của test, HTTP request, subprocess, test JVM và toàn CI job.
- Dùng deadline dựa trên thời gian monotonic để tránh cộng dồn timeout ngoài ý muốn.
- Viết Java 17 code chạy subprocess với ProcessBuilder, timeout, output capture và best-effort kill process tree.
- Chạy Callable đồng thời bằng thread pool có giới hạn, xử lý cancellation/interruption và đợi executor kết thúc.
- Cấu hình JUnit 5, Maven Surefire/Failsafe và Gradle test workers.
- Khởi động test server/container bằng port riêng, chờ readiness có timeout và dọn tài nguyên trong mọi nhánh kết thúc.
- Dùng shell trap/CI timeout để dọn Docker containers khi script fail hoặc bị hủy.
- Nhận diện process leak, deadlock do output pipe, thread không chịu interrupt, port conflict và cleanup che mất lỗi gốc.

**Phiên bản ví dụ:** Java 17, **Spring Boot 3.3.5**, JUnit Jupiter 5.10.2, Maven Surefire/Failsafe 3.2.5, Gradle Java Test task và Docker CLI. Các version này để code minh họa đồng nhất; dùng phiên bản đã được dự án phê duyệt.

## 2. Timeout phải được thiết kế theo nhiều tầng

Một pipeline có thể có nhiều deadline lồng nhau:

~~~text
CI job deadline:             20 phút
  |
  +-- Maven/Gradle test task: 12 phút
        |
        +-- Integration test: 60 giây
              |
              +-- HTTP readiness: 20 giây
              |
              +-- HTTP request: 5 giây
              |
              +-- Child process: 10 giây
~~~

Các con số chỉ minh họa. Hãy phân bổ budget thật dựa trên môi trường CI, thời gian khởi động ứng dụng và mức độ quan trọng của kiểm thử.

| Tầng | Timeout kiểm soát | Khi hết hạn |
| --- | --- | --- |
| HTTP client/request | Một lần gọi API hoặc kết nối | Hủy request/socket và báo lỗi |
| Test method | Một test case | Đánh dấu test fail/aborted theo test framework |
| Subprocess | Một lệnh ngoài JVM | Dừng process và process con trong phạm vi có thể kiểm soát |
| Test suite/task | Cả nhóm tests hoặc Maven/Gradle task | Dừng workers/processes và thu thập logs |
| CI job | Toàn bộ job/step | CI runner hủy job; cleanup hooks có thể được chạy tùy cách runner kết thúc |

**Timeout ngoài phải lớn hơn timeout trong.** Nếu một test có deadline 30 giây nhưng CI job chỉ còn 20 giây, runner có thể bị hủy trước khi test kịp dừng process và lưu log. Hãy chừa một khoảng cleanup margin sau deadline của test/task.

### 2.1. Timeout không đồng nghĩa với cancellation

- **Timeout** là kết luận rằng một deadline đã hết.
- **Cancellation** là yêu cầu dừng công việc đang chạy.
- **Interruption** là tín hiệu Java gửi tới thread để nó tự kết thúc hoặc giải phóng resource.
- **Termination** là process/thread thực sự đã kết thúc.

Một lệnh `Future.cancel(true)` chỉ yêu cầu interrupt thread thực thi. Nó không tự đảm bảo code dừng: task phải gọi blocking APIs có hỗ trợ interrupt hoặc chủ động kiểm tra cờ interrupt. Tương tự, hủy HTTP future không phải lúc nào cũng đóng được một socket do thư viện ngoài quản lý.

**Không dùng `Thread.stop()`** để ép dừng code. Cách đó không an toàn với shared state và không phải cơ chế cancellation hợp lệ.

## 3. Chọn deadline và tránh cộng dồn timeout

Nếu có ba bước liên tiếp, mỗi bước được truyền timeout 30 giây, tổng thời gian có thể gần 90 giây. Nếu mục tiêu là toàn bộ workflow chỉ được chạy 30 giây, cần dùng **một deadline chung** rồi tính thời gian còn lại cho từng bước.

Dùng `System.nanoTime()` để đo elapsed time/deadline trong process hiện tại. Không dùng `System.currentTimeMillis()` cho thời lượng vì đồng hồ hệ thống có thể bị điều chỉnh.

~~~java
import java.time.Duration;

public final class Deadline {
    private final long endNanos;

    private Deadline(Duration budget) {
        if (budget.isNegative() || budget.isZero()) {
            throw new IllegalArgumentException("budget must be positive");
        }
        this.endNanos = System.nanoTime() + budget.toNanos();
    }

    public static Deadline after(Duration budget) {
        return new Deadline(budget);
    }

    public Duration remaining() {
        long nanos = endNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0L, nanos));
    }

    public boolean expired() {
        return endNanos - System.nanoTime() <= 0L;
    }
}
~~~

Ví dụ dùng:

~~~java
Deadline deadline = Deadline.after(Duration.ofSeconds(20));

callService(deadline.remaining());

if (deadline.expired()) {
    throw new java.util.concurrent.TimeoutException("workflow deadline exceeded");
}

runDatabaseCheck(deadline.remaining());
~~~

`callService` và `runDatabaseCheck` cần thực sự áp dụng duration nhận được vào HTTP/client/driver API. Chỉ truyền duration nhưng thư viện bỏ qua nó thì không tạo ra timeout thật.

### 3.1. Deadline truyền qua các lớp

Một workflow nên truyền deadline/remaining budget qua các tầng thay vì mỗi tầng tự đặt lại timeout mặc định. Điều này tránh trường hợp retry vô hạn hoặc mỗi HTTP call đều được cấp lại toàn bộ budget.

- Chọn timeout kết nối và timeout đọc riêng nếu HTTP client hỗ trợ.
- Đặt số lần retry và tổng retry budget.
- Không retry lỗi không thể khôi phục như invalid credentials hoặc sai coordinates.
- Khi deadline hết, không bắt đầu tác vụ mới.
- Giữ một khoảng thời gian riêng để đóng resource và lưu logs.

## 4. Timeout cho JUnit 5 tests

JUnit Jupiter hỗ trợ `@Timeout` và assertion timeout. Ví dụ:

~~~java
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class ServiceTimeoutTest {

    @Test
    @Timeout(value = 3, unit = TimeUnit.SECONDS)
    void serviceRespondsWithinBudget() throws Exception {
        // Gọi service test; client cũng cần timeout riêng.
    }
}
~~~

`@Timeout` giới hạn thời gian test method. Nó là hàng rào của test framework, **không thay thế timeout cho HTTP client, JDBC, subprocess hoặc container**. Nếu test đang chờ một API không timeout, thread có thể vẫn mắc kẹt trong tầng ngoài.

### 4.1. assertTimeout và assertTimeoutPreemptively

~~~java
import static org.junit.jupiter.api.Assertions.assertTimeout;
import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class TimeoutAssertionTest {

    @Test
    void checksElapsedTimeAfterWorkCompletes() {
        assertTimeout(Duration.ofSeconds(1), () -> {
            performQuickCheck();
        });
    }

    @Test
    void requestsPreemptiveCancellationWhenBudgetExpires() {
        assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
            performInterruptibleCheck();
        });
    }

    private void performQuickCheck() {
        // Công việc có thời lượng dự kiến ngắn.
    }

    private void performInterruptibleCheck() throws InterruptedException {
        Thread.sleep(100);
    }
}
~~~

Khác biệt:

- `assertTimeout`: thực thi callback rồi mới đánh giá thời gian đã dùng. Nếu callback treo mãi, assertion không thể tự ngắt callback đúng deadline.
- `assertTimeoutPreemptively`: chạy callback trên thread riêng và yêu cầu dừng khi vượt hạn. Nó có thể ảnh hưởng code dựa vào ThreadLocal, transaction context hoặc framework test gắn với thread gốc.
- Preemptive cancellation vẫn phụ thuộc code có phản hồi interruption. Task bỏ qua interrupt có thể tiếp tục chạy sau khi assertion timeout.

Không bọc toàn bộ Spring test suite bằng preemptive timeout một cách máy móc. Ưu tiên timeout ở API/process thật sự cần bảo vệ, dùng `@Timeout` có chủ đích và đảm bảo resource cleanup không phụ thuộc vào thread bị interrupt.

## 5. Maven Surefire và Failsafe: quản lý test JVM

Maven thường dùng:

- **Surefire** để chạy unit tests ở phase `test`.
- **Failsafe** để chạy integration tests qua goals `integration-test` và `verify`.

Khi test chạy trong forked JVM, Maven plugin có thể giới hạn thời gian process fork được phép chạy. Ví dụ cấu hình cho Surefire:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <forkCount>2</forkCount>
        <reuseForks>true</reuseForks>
        <forkedProcessTimeoutInSeconds>180</forkedProcessTimeoutInSeconds>
    </configuration>
</plugin>
~~~

Có thể cấu hình tương tự cho Maven Failsafe nếu integration tests chạy trong forked JVM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <forkCount>1</forkCount>
        <reuseForks>true</reuseForks>
        <forkedProcessTimeoutInSeconds>300</forkedProcessTimeoutInSeconds>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là các fragment cấu hình plugin; hợp nhất vào POM hiện tại thay vì tạo duplicate plugin declarations. `forkedProcessTimeoutInSeconds` kiểm soát thời gian forked JVM, **không phải timeout cho từng HTTP request hay một method riêng**.

### 5.1. forkCount và concurrency

`forkCount` là số JVM test fork có thể chạy đồng thời. Ví dụ `forkCount=2` có thể chạy hai test JVM cùng lúc. `reuseForks=true` cho phép tái sử dụng các fork giữa test classes theo cơ chế Surefire.

Không đặt `forkCount` thật lớn chỉ vì CI runner báo nhiều CPU:

- Mỗi JVM dùng heap, metaspace, threads và file descriptors.
- Nhiều test đồng thời có thể cùng chiếm port hoặc database connections.
- CPU/memory contention có thể khiến test chậm hơn và timeout giả.
- Một test fail do race condition có thể chỉ xuất hiện khi chạy parallel.

Maven reactor cũng có thể chạy module song song với `-T`. Khi vừa bật Maven parallel modules vừa tăng Surefire forks, tổng số JVM có thể tăng theo cấp số nhân. Tính tổng concurrency của cả reactor và test plugins.

### 5.2. Lệnh Maven chẩn đoán

~~~bash
./mvnw -B -ntp test
./mvnw -B -ntp verify
./mvnw -B -ntp -T 2 test
~~~

- `test` chạy unit-test lifecycle.
- `verify` chạy tiếp integration tests/verification nếu POM đã cấu hình.
- `-T 2` cho phép tối đa hai Maven threads theo reactor scheduling; đây là một nguồn concurrency riêng với Surefire `forkCount`.

Khi điều tra flaky tests, chạy một lượt tuần tự để phân biệt lỗi logic với tranh chấp tài nguyên. Sau đó bật concurrency có giới hạn và ghi lại cấu hình runner.

## 6. Gradle Test workers và concurrency

Gradle `Test` task chạy test trong worker JVM. Có thể giới hạn số fork:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
    maxParallelForks = 2
}
~~~

`maxParallelForks` giới hạn số test worker JVM đồng thời cho task đó. Nếu có nhiều test tasks hoặc nhiều Gradle builds cùng chạy, tổng concurrency vẫn có thể lớn hơn con số này.

### 6.1. Khi nào nên tăng worker?

Tăng worker khi:

- Test classes độc lập và không dùng shared mutable state.
- Database/service test có namespace hoặc schema riêng.
- Port được cấp động hoặc test server có cơ chế port 0.
- Runner có đủ CPU/memory và giới hạn kết nối.
- Test output/logging không phụ thuộc thứ tự thực thi.

Giữ worker thấp khi:

- Tests dùng cùng tài khoản hoặc cùng record database.
- Test sửa global system properties/environment.
- Test phụ thuộc thứ tự hoặc shared filesystem path.
- Docker daemon/registry có giới hạn tài nguyên.
- Runner có ít memory.

### 6.2. Không dùng parallelism để che race condition

Nếu một test pass tuần tự nhưng fail khi chạy đồng thời, hãy xác định shared resource:

- File path cố định như `target/test-output.json`.
- Port hard-code `8080`.
- Database table dùng chung row ID.
- Static singleton/global cache.
- Shared queue/topic hoặc consumer group.
- Container name cố định.
- Test cùng thay đổi một system property.

Tạo resource riêng theo test/run ID, hoặc dùng lock khi resource thực sự phải dùng chung. Không chỉ tăng timeout để che tranh chấp.

## 7. ExecutorService: chạy tác vụ đồng thời có giới hạn

Dùng thread pool hữu hạn để tránh tạo thread không kiểm soát. `Executors.newFixedThreadPool(2)` tạo một pool tối đa hai worker thread; các task vượt số worker sẽ xếp hàng trong queue.

Ví dụ Java 17:

~~~java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedTasksDemo {

    private static String work(String name, long millis)
            throws InterruptedException {
        try {
            Thread.sleep(millis);
            return name + ": completed";
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw ex;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        List<Callable<String>> tasks = List.of(
                () -> work("fast", 100),
                () -> work("slow", 5000)
        );

        try {
            List<Future<String>> results =
                    pool.invokeAll(tasks, 1, TimeUnit.SECONDS);

            for (int i = 0; i < results.size(); i++) {
                Future<String> result = results.get(i);

                if (result.isCancelled()) {
                    System.out.println("task " + (i + 1) + ": timed out");
                } else {
                    System.out.println(result.get());
                }
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw ex;
        } finally {
            pool.shutdownNow();

            try {
                if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                    System.err.println("executor did not terminate");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 BoundedTasksDemo.java
java BoundedTasksDemo
~~~

Với hai task độc lập như ví dụ, output dự kiến theo thứ tự danh sách futures:

~~~text
fast: completed
task 2: timed out
~~~

`invokeAll(..., timeout, unit)` đợi tối đa thời lượng chỉ định rồi hủy những task chưa hoàn tất. `Future.isCancelled()` giúp nhận diện task bị hủy. `shutdownNow()` yêu cầu các worker dừng bằng interrupt; `awaitTermination()` cho ứng dụng một khoảng thời gian để chúng kết thúc.

### 7.1. Vì sao cần shutdown và awaitTermination?

- `shutdown()` ngừng nhận task mới nhưng cho task đã submit chạy hết.
- `shutdownNow()` yêu cầu dừng các task đang chạy và trả về các task đang chờ trong queue.
- `awaitTermination()` đợi pool thực sự kết thúc trong thời gian giới hạn.
- `Future.cancel(true)` yêu cầu interrupt task tương ứng; không đảm bảo task dừng nếu nó không hợp tác.

Trong ví dụ, task `slow` dùng `Thread.sleep`, một API interruptible. Nếu task gọi native method, thư viện không hỗ trợ interruption hoặc vòng lặp CPU không kiểm tra interrupt, nó có thể tiếp tục chạy. Phải thiết kế task để hỗ trợ cancellation.

### 7.2. Không tạo thread pool vô hạn cho mỗi test

Tránh tạo `newCachedThreadPool()` hoặc thread pool mới cho từng request/test mà không quản lý lifecycle. Nếu có nhiều test chạy song song, mỗi test lại tạo pool riêng, số thread có thể tăng rất nhanh.

- Dùng pool có giới hạn theo CPU/I/O workload.
- Đặt queue/backpressure phù hợp.
- Đóng pool trong owner component hoặc `finally`.
- Không chia sẻ executor đã shutdown cho test tiếp theo.
- Không để task background chạy qua ranh giới giữa hai tests.

## 8. ProcessBuilder: timeout và dọn process con

Khi test cần chạy command ngoài JVM, dùng ProcessBuilder với danh sách arguments. Không ghép input chưa tin cậy thành shell command.

**Không làm như sau:**

~~~java
Runtime.getRuntime().exec("sh -c " + userInput);
~~~

Chuỗi shell có thể bị phân tích cú pháp ngoài ý muốn, khó quản lý quoting và khó dừng toàn bộ process tree.

Dùng:

~~~java
new ProcessBuilder("git", "status", "--short");
~~~

Mỗi phần tử là một argument độc lập. `ProcessBuilder` không tự gọi shell khi truyền executable cùng arguments theo dạng list.

### 8.1. Java 17 runnable example

Tạo file `ProcessTimeoutDemo.java`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ProcessTimeoutDemo {

    static void runWithTimeout(List<String> command, Duration timeout)
            throws Exception {
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }

        Path output = Files.createTempFile("process-output-", ".log");
        Process process = null;

        try {
            ProcessBuilder builder = new ProcessBuilder(command)
                    .redirectErrorStream(true)
                    .redirectOutput(output.toFile());

            process = builder.start();

            long timeoutMillis = Math.max(1L, timeout.toMillis());
            if (!process.waitFor(timeoutMillis, TimeUnit.MILLISECONDS)) {
                terminateTree(process);
                throw new TimeoutException(
                        "command exceeded " + timeoutMillis + " ms"
                );
            }

            String captured = Files.readString(output);
            if (process.exitValue() != 0) {
                throw new IOException(
                        "command exited with " + process.exitValue()
                                + System.lineSeparator() + captured
                );
            }

            if (!captured.isBlank()) {
                System.out.print(captured);
            }
        } finally {
            if (process != null && process.isAlive()) {
                terminateTree(process);
            }
            Files.deleteIfExists(output);
        }
    }

    private static void terminateTree(Process process)
            throws InterruptedException {
        List<ProcessHandle> descendants =
                process.toHandle().descendants().toList();

        // Yêu cầu các process con kết thúc trước process gốc.
        for (int i = descendants.size() - 1; i >= 0; i--) {
            descendants.get(i).destroy();
        }

        process.destroy();

        // Cho phép graceful termination trong một khoảng ngắn.
        process.waitFor(1, TimeUnit.SECONDS);

        // Ép dừng các process còn sống nếu graceful termination không đủ.
        for (ProcessHandle child : descendants) {
            if (child.isAlive()) {
                child.destroyForcibly();
            }
        }

        if (process.isAlive()) {
            process.destroyForcibly();
        }

        process.waitFor(2, TimeUnit.SECONDS);
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("child")) {
            System.out.println("child started");
            System.out.flush();
            Thread.sleep(30_000);
            return;
        }

        String executable = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name").toLowerCase().contains("win")
                        ? "java.exe" : "java"
        ).toString();

        String classPath = System.getProperty("java.class.path");

        try {
            runWithTimeout(
                    List.of(
                            executable,
                            "-cp",
                            classPath,
                            ProcessTimeoutDemo.class.getName(),
                            "child"
                    ),
                    Duration.ofSeconds(1)
            );
            System.out.println("child completed");
        } catch (TimeoutException ex) {
            System.out.println("TIMEOUT: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 ProcessTimeoutDemo.java
java ProcessTimeoutDemo
~~~

Output chính xác của process cha:

~~~text
TIMEOUT: command exceeded 1000 ms
~~~

Child process in `child started` vào file log tạm, nhưng parent timeout trước khi đọc output; file được xóa trong `finally`. Ví dụ chủ ý không in log child để giữ stdout xác định.

### 8.2. Tại sao redirect output ra file?

Nếu dùng:

~~~java
process.getInputStream().readAllBytes();
process.waitFor(timeout, TimeUnit.SECONDS);
~~~

thì lệnh đọc stream có thể chặn vô hạn **trước khi code tới waitFor timeout**. Ngoài ra, nếu process ghi nhiều stdout/stderr mà parent không đọc, pipe buffer có thể đầy và child bị block.

Có ba cách thường dùng:

- Redirect stdout/stderr ra file tạm, đợi process rồi đọc file như ví dụ.
- Đọc stream song song bằng một reader task có lifecycle/timeout riêng.
- Redirect output về DISCARD nếu không cần log, hoặc file log do CI thu thập.

Không để output pipe bị bỏ mặc khi process có thể ghi nhiều dữ liệu.

### 8.3. ProcessHandle descendants chỉ là best effort

`ProcessHandle.descendants()` lấy snapshot các process con mà JVM quan sát được tại thời điểm gọi. Process có thể spawn thêm child đồng thời với cleanup; quyền OS, platform và cách process daemonize có thể ảnh hưởng khả năng dừng.

Nếu test command tạo process tree phức tạp, hãy chạy nó trong **container, cgroup, process group hoặc job object** có ranh giới sở hữu rõ ràng. Không dùng lệnh global như `killall java` hoặc `taskkill /IM java.exe` vì có thể giết build/test process của job khác.

### 8.4. Không bỏ qua exit code

Một process kết thúc trong timeout không có nghĩa command thành công. Kiểm tra:

- `waitFor` trả true hay false.
- `exitValue()` bằng 0 hay khác 0.
- stdout/stderr có lỗi cần lưu không.
- process descendants còn sống không.
- cleanup có hoàn tất trong budget không.

Phân biệt ba trạng thái: **completed successfully**, **completed with non-zero exit**, **timed out/cancelled**. Không chuyển tất cả thành một boolean “done”.

## 9. Đợi service readiness thay vì sleep cố định

Một integration test thường start Spring Boot app rồi gửi request. Cách yếu:

~~~java
startApplication();
Thread.sleep(5000);
callEndpoint();
~~~

Năm giây có thể quá dài trên máy nhanh và quá ngắn trên CI runner chậm. Dùng readiness polling có deadline:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class ReadinessCheck {

    public static void waitUntilReady(URI healthUri, Duration budget)
            throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        long deadline = System.nanoTime() + budget.toNanos();
        Exception lastFailure = null;

        while (System.nanoTime() < deadline) {
            HttpRequest request = HttpRequest.newBuilder(healthUri)
                    .timeout(Duration.ofSeconds(2))
                    .GET()
                    .build();

            try {
                HttpResponse<Void> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding()
                );

                if (response.statusCode() == 200) {
                    return;
                }
            } catch (Exception ex) {
                lastFailure = ex;
            }

            Thread.sleep(200);
        }

        throw new java.util.concurrent.TimeoutException(
                "service did not become ready within " + budget
                        + (lastFailure == null ? "" :
                        "; last failure: " + lastFailure)
        );
    }
}
~~~

Code dùng Java 11+ APIs, chạy được trên Java 17. `connectTimeout` giới hạn thời gian thiết lập kết nối, `HttpRequest.timeout` giới hạn request, còn vòng polling có deadline tổng. Chỉ chấp nhận HTTP 200 ở ví dụ; service thực tế có thể dùng readiness status khác.

**Không kiểm tra liveness thay cho readiness.** Process có thể còn sống nhưng application context chưa hoàn tất, database migration chưa xong hoặc endpoint phụ thuộc service khác chưa sẵn sàng.

## 10. Dọn Spring Boot app, HTTP server và test fixtures

Nếu test tự tạo tài nguyên, owner của tài nguyên phải có trách nhiệm đóng nó.

### 10.1. Dùng try/finally cho resource không implement AutoCloseable

~~~java
var server = com.sun.net.httpserver.HttpServer.create(
        new java.net.InetSocketAddress("127.0.0.1", 0), 0
);

try {
    server.start();
    // Gửi HTTP request và assert response.
} finally {
    server.stop(0);
}
~~~

Port 0 yêu cầu OS cấp một port trống. Dùng `server.getAddress().getPort()` để đọc port thực tế. Đừng hard-code 8080 cho nhiều tests chạy song song.

### 10.2. Spring Boot test server với random port

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApplicationHttpTest {

    @LocalServerPort
    int port;

    // Gọi endpoint qua port được cấp động.
}
~~~

Spring test framework quản lý application context theo cache/lifecycle của test. Nếu tự tạo thêm process/server/container bên ngoài context, bạn vẫn phải dọn resource đó.

### 10.3. Cleanup theo vòng đời JUnit

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ExternalProcessTest {

    private Process process;

    @BeforeEach
    void startFixture() throws Exception {
        // Start process fixture và lưu handle.
    }

    @AfterEach
    void stopFixture() throws Exception {
        if (process != null && process.isAlive()) {
            process.destroy();
            if (!process.waitFor(1, java.util.concurrent.TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor(2, java.util.concurrent.TimeUnit.SECONDS);
            }
        }
    }

    @Test
    void checksFixture() {
        // Test.
    }
}
~~~

Đây là pattern rút gọn; trong project thật nên dùng helper quản lý process tree và lưu logs trước khi xóa temp files. `@AfterEach` chạy sau từng test trong luồng JUnit thông thường, kể cả assertion fail. Nếu toàn bộ JVM bị kill -9 hoặc runner bị mất đột ngột, không thể trông cậy vào callback này.

### 10.4. Cleanup phải idempotent

Một cleanup tốt có thể được gọi nhiều lần mà không làm hỏng trạng thái:

- Kiểm tra handle/resource có tồn tại trước khi đóng.
- Đóng socket/server/executor/container theo thứ tự phụ thuộc.
- Ghi logs trước khi xóa container/temp directory.
- Không để lỗi cleanup che mất exception gốc của test.
- Giới hạn thời gian chờ shutdown.
- Xóa thư mục tạm chỉ sau khi process không còn ghi vào đó.

Trong Java, `try-with-resources` phù hợp với `AutoCloseable`; `finally` phù hợp khi phải quản lý nhiều tài nguyên hoặc shutdown process.

## 11. Docker container trong integration tests

Khi test dùng Docker, đặt container name duy nhất cho từng job/test run. Tránh tên cố định như `spring-test` nếu CI có nhiều jobs song song.

Ví dụ chạy detached:

~~~bash
docker run -d \
  --name "$CONTAINER_NAME" \
  -p 127.0.0.1::8080 \
  "$IMAGE"
~~~

Docker tự cấp host port ngẫu nhiên cho container port 8080. Lấy port:

~~~bash
BINDING="$(docker port "$CONTAINER_NAME" 8080/tcp)"
HOST_PORT="${BINDING##*:}"
HEALTH_URL="http://127.0.0.1:$HOST_PORT/actuator/health"
~~~

Nếu Actuator health endpoint không có trong image, thay bằng endpoint readiness của ứng dụng. Không giả định endpoint `/actuator/health` luôn được bật hoặc public.

### 11.1. Chờ readiness với deadline

~~~bash
READY=0
DEADLINE=$((SECONDS + 30))

while (( SECONDS < DEADLINE )); do
  if curl --fail --silent "$HEALTH_URL" >/dev/null; then
    READY=1
    break
  fi
  sleep 1
done

if (( READY == 0 )); then
  echo "container did not become ready" >&2
  docker logs "$CONTAINER_NAME" >&2 || true
  exit 1
fi
~~~

Bash `SECONDS` là counter tăng theo thời gian của shell. Loop có deadline và không chờ vô hạn. Nếu image startup chậm hơn, điều chỉnh budget theo môi trường và quan sát logs thay vì bỏ timeout.

## 12. Shell trap: cleanup khi script pass hoặc fail

Với Bash trên Linux CI, `trap` giúp chạy cleanup khi script thoát bình thường hoặc có lỗi:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

CONTAINER_NAME="spring-it-$CI_JOB_ID-$$"
IMAGE="example/spring-service:test"

cleanup() {
  STATUS=$?
  trap - EXIT INT TERM

  docker logs "$CONTAINER_NAME" >&2 || true
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

  exit "$STATUS"
}

trap cleanup EXIT

docker run -d \
  --name "$CONTAINER_NAME" \
  -p 127.0.0.1::8080 \
  "$IMAGE"

BINDING="$(docker port "$CONTAINER_NAME" 8080/tcp)"
HOST_PORT="${BINDING##*:}"
HEALTH_URL="http://127.0.0.1:$HOST_PORT/actuator/health"

READY=0
DEADLINE=$((SECONDS + 30))
while (( SECONDS < DEADLINE )); do
  if curl --fail --silent "$HEALTH_URL" >/dev/null; then
    READY=1
    break
  fi
  sleep 1
done

if (( READY == 0 )); then
  echo "readiness timeout" >&2
  exit 1
fi

curl --fail --show-error "$HEALTH_URL"
~~~

`cleanup` lưu exit status ban đầu, tắt trap để tránh gọi lặp, ghi container logs rồi force-remove container. `|| true` chỉ áp dụng cho cleanup phụ, tránh một lỗi `docker logs` che mất lỗi chính.

**Giới hạn:** trap không đảm bảo chạy nếu máy/runner mất điện, process bị kill -9 hoặc host bị thu hồi đột ngột. CI runner ephemeral và container labels/TTL/orphan cleanup ở cấp runner vẫn hữu ích.

Không chạy cùng một `CONTAINER_NAME` cố định ở nhiều job song song. Dùng CI job/run ID cộng process ID để tránh collision; với CI provider khác, dùng ID tương ứng.

## 13. CI job timeout và cancellation

CI timeout là hàng rào ngoài cùng. Ví dụ GitHub Actions:

~~~yaml
jobs:
  integration-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - name: Verify
        run: ./mvnw -B -ntp verify
~~~

`timeout-minutes` giới hạn toàn job. Nó không thay thế test-level/process-level cleanup. Khi job bị cancel hoặc timeout, CI runner gửi tín hiệu dừng; cleanup behavior phụ thuộc runner, shell và thời gian grace period còn lại.

Một CI pipeline nên:

1. Đặt job timeout lớn hơn tổng test budgets và cleanup margin.
2. Dùng timeout cho từng network call/subprocess thay vì chờ tới job deadline.
3. Bật fail-fast cho lỗi không thể phục hồi; không retry mãi.
4. Ghi logs/artifacts trước cleanup nếu chúng cần phục vụ điều tra.
5. Dùng unique IDs cho container, temp dirs, schema, queue và ports.
6. Dọn resource bằng trap/finally/AfterEach.
7. Đặt orphan cleanup có scope giới hạn theo label/job ID nếu runner có thể bị hủy đột ngột.
8. Không kill mọi Java process trên shared runner; chỉ dừng process thuộc job/test đang sở hữu.

### 13.1. Timeout và retry phải có budget

Ví dụ HTTP request timeout 5 giây, tối đa hai lần retry. Tổng thời gian không nên vượt deadline của integration test. Nếu mỗi retry lại đợi 5 giây rồi thêm backoff 5 giây, tổng có thể tăng nhanh.

Dùng exponential backoff có giới hạn và jitter cho lỗi tạm thời; không retry lỗi xác thực, invalid configuration, assertion failure hoặc 4xx không retryable. Khi deadline gần hết, dừng retry và bắt đầu cleanup.

## 14. Concurrency và tài nguyên dùng chung

Chạy song song có lợi khi tests độc lập, nhưng các tài nguyên sau thường gây xung đột:

| Tài nguyên | Lỗi khi chạy đồng thời | Cách cô lập |
| --- | --- | --- |
| TCP port | Address already in use | Port 0/random host port, lấy port thực tế |
| Temp directory/file | Test ghi đè hoặc đọc file của test khác | Thư mục riêng theo test/run ID |
| Database | Cùng record/schema, test xóa dữ liệu của nhau | Schema/database riêng, transaction hoặc unique IDs |
| Docker container | Tên/container volume collision | Tên duy nhất và labels theo job |
| Message broker | Consumer cùng đọc message, queue còn dữ liệu | Topic/queue/consumer group riêng |
| External API quota | Rate limit và test flakiness | Bounded concurrency, mock/stub hoặc quota test riêng |
| JVM system properties | Test thay đổi global config của nhau | Tránh mutate global; serialize tests cần thiết |
| Filesystem lock | Một test giữ lock, test khác timeout | Lock scope nhỏ, cleanup trong finally |

### 14.1. Tính concurrency tổng

Ví dụ:

- CI chạy 3 matrix jobs.
- Mỗi job Maven chạy 2 module song song.
- Mỗi module Surefire tạo 3 fork.

Tối đa lý thuyết có thể lên tới 18 test JVM, chưa kể application processes và Docker containers. Nếu mỗi JVM dùng 512 MB heap, riêng heap có thể cần khoảng 9 GB trước overhead.

Đừng cấu hình từng tầng độc lập mà quên tổng số worker. Cần cân bằng CPU, RAM, file descriptors, database connections, registry pulls và API quotas.

### 14.2. Bounded queue và backpressure

Fixed thread pool có queue không giới hạn theo implementation của `Executors.newFixedThreadPool`. Với lượng task lớn, số task chờ có thể tăng và giữ nhiều objects trong memory. Khi cần tải có kiểm soát, tạo `ThreadPoolExecutor` với queue hữu hạn và rejection policy rõ ràng:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor executor = new ThreadPoolExecutor(
        4,
        4,
        0L,
        TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(20),
        new ThreadPoolExecutor.AbortPolicy()
);
~~~

Tối đa bốn worker và hai mươi task chờ. Khi queue đầy, `AbortPolicy` ném `RejectedExecutionException`; caller phải xử lý backpressure/rejection. Không âm thầm bỏ task nếu kết quả test cần đầy đủ.

## 15. Interruption: task phải hợp tác với việc dừng

Code chạy lâu nên kiểm tra interrupt hoặc dùng blocking API hỗ trợ interrupt:

~~~java
void pollUntilDone() throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        checkStatus();
        Thread.sleep(200);
    }
}
~~~

Khi bắt `InterruptedException`:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw ex;
}
~~~

Khôi phục interrupt flag nếu không tiếp tục propagate exception, hoặc ném exception lên caller. Không bắt rồi bỏ qua interruption:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ignored) {
    // Không được âm thầm bỏ qua nếu caller cần dừng task.
}
~~~

`Future.cancel(true)` và `ExecutorService.shutdownNow()` gửi interrupt request, không phải force-kill thread. Nếu một thư viện không hỗ trợ interruption, cần API timeout/cancel riêng hoặc cách ly nó trong subprocess/container để có ranh giới dừng mạnh hơn.

## 16. Cleanup order và giữ lại bằng chứng lỗi

Khi integration test fail, cleanup đúng thứ tự giúp log còn hữu ích:

~~~text
Test assertion / request fails
          |
          v
Capture application + container logs
          |
          v
Stop HTTP clients / scheduled tasks
          |
          v
Stop application process / child processes
          |
          v
Stop containers and close connections
          |
          v
Delete temp files / schemas / queues
          |
          v
Return original test failure to CI
~~~

Một số nguyên tắc:

- **Lưu log trước khi remove container/process.** Nếu xóa trước, bạn mất bằng chứng.
- Đóng client/connection trước khi xóa server/database fixture.
- Dừng scheduled executors trước khi xóa temp directories mà chúng còn ghi.
- Dùng `finally`, `@AfterEach`, `@AfterAll`, `AutoCloseable` hoặc CI trap theo owner.
- Cleanup phải có timeout; không để shutdown chờ vô hạn.
- Giữ exception gốc. Nếu cleanup cũng lỗi, log cleanup exception như suppressed/secondary thay vì che lỗi test chính.
- Dọn theo ID/label của job, không xóa container hoặc file của jobs khác.
- Với test retry, đảm bảo lần trước đã cleanup trước khi lần sau khởi động.

### 16.1. Cleanup không được phụ thuộc chỉ vào shutdown hook

JVM shutdown hook hữu ích cho shutdown bình thường, nhưng không đảm bảo chạy khi process bị kill -9, runner bị mất hoặc host dừng đột ngột. Dùng hook như lớp bảo vệ phụ; vẫn cần finally/test lifecycle/CI resource ownership.

### 16.2. Cleanup sau test fail và timeout

- Nếu assertion fail, `@AfterEach` vẫn là nơi phù hợp để đóng resource.
- Nếu `@Timeout` interrupt test thread, cleanup code cần xử lý interruption hợp lý.
- Nếu subprocess timeout, parent phải dừng process và descendants trước khi xóa log/temp directory.
- Nếu CI cancel, trap có thể chạy trong grace period; nếu không, runner-level orphan cleanup xử lý resource còn sót.
- Nếu container crash, lấy logs và exit code trước khi remove.

## 17. Anti-patterns và lỗi thường gặp

| Anti-pattern / triệu chứng | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| `Thread.sleep(5000)` để chờ service | Chậm hoặc flaky tùy runner | Poll readiness với deadline |
| HTTP client không timeout | Thread/socket có thể treo đến CI timeout | Connect/request/read timeout phù hợp |
| `assertTimeout` dùng cho code có thể treo | Nó chờ callback hoàn thành trước khi đánh giá | Dùng preemptive timeout có cân nhắc hoặc timeout tại API |
| Nghĩ `Future.cancel(true)` giết task ngay | Interrupt chỉ là yêu cầu hợp tác | Task kiểm tra interrupt; dùng process/container isolation khi cần |
| Đọc process output trước `waitFor(timeout)` | Có thể block vô hạn hoặc deadlock pipe | Redirect file hoặc đọc stream song song |
| Chỉ gọi `process.destroy()` | Process có thể bỏ qua graceful termination; child còn sống | Graceful wait rồi force-kill process tree trong scope |
| Dùng `killall java` | Có thể kill Maven/Gradle hoặc job khác | Chỉ dừng handle/container do test sở hữu |
| Thread pool không shutdown | JVM không thoát, task leak qua tests | `shutdownNow` và `awaitTermination` |
| Fixed pool quá lớn | Memory/CPU contention làm test chậm hơn | Bounded concurrency theo tổng runner capacity |
| Port 8080 hard-code | Parallel test tranh port | Port 0 hoặc host port random |
| Container name cố định | Job đồng thời đụng nhau | Unique name + job ID |
| Cleanup xóa logs trước khi lưu | Mất nguyên nhân test fail | Capture logs trước remove |
| Cleanup exception che assertion failure | CI hiển thị sai nguyên nhân chính | Giữ original exception, log/suppress cleanup error |
| Timeout ngoài nhỏ hơn timeout trong | CI hủy runner trước cleanup | Phân tầng deadline và chừa margin |
| Retry vô hạn | Kéo dài job và tăng tải dependency | Retry hữu hạn, deadline chung, backoff |
| Dùng SNAPSHOT/test data dùng chung | Test không tái lập | Version bất biến, unique test data |
| Chỉ dùng CI job timeout | Không biết bước nào treo, cleanup khó | Timeout từng test/request/process và job |
| Cho rằng shutdown hook luôn chạy | Không chạy khi force kill/host loss | Owner cleanup + ephemeral runner/orphan policy |

## 18. Bài thực hành và tiêu chí hoàn thành

Thực hành trong branch thử nghiệm của project Spring Boot:

1. Thêm JUnit `@Timeout` cho một test có thể treo; phân biệt test timeout với HTTP client timeout.
2. Viết readiness polling helper dùng `System.nanoTime()` và deadline tổng; không dùng sleep cố định.
3. Chạy `BoundedTasksDemo.java` với hai task, xác nhận task nhanh hoàn thành và task chậm bị cancel sau một giây.
4. Đảm bảo executor gọi `shutdownNow()` và `awaitTermination()` trong `finally`.
5. Chạy `ProcessTimeoutDemo.java` bằng Java 17; xác nhận parent nhận `TimeoutException` sau 1000 ms và process con được yêu cầu dừng.
6. Kiểm tra output được redirect để tránh pipe deadlock; giữ exit code riêng biệt với timeout.
7. Cấu hình Surefire/Failsafe forked process timeout và concurrency có giới hạn.
8. Cấu hình Gradle `maxParallelForks` theo tài nguyên CI, rồi chạy test tuần tự và song song để phát hiện race.
9. Khởi động Spring Boot integration test server trên random port và chờ readiness qua HTTP.
10. Chạy Docker container detached với tên duy nhất, host port random và health polling có deadline.
11. Thêm Bash `trap` để lưu logs rồi remove container khi script exit/fail.
12. Thử cố ý làm health endpoint không sẵn sàng; xác nhận script fail trong timeout và container được dọn.
13. Thử hủy CI job; kiểm tra logs, process/container còn sót và cleanup behavior của runner.
14. Chạy nhiều job song song; xác minh temp directories, database schemas, queue names, ports và container names không collision.
15. Đo tổng concurrency của CI matrix × Maven reactor × Surefire forks/Gradle workers.
16. Ghi timeout budget, resource owner, cleanup order và bằng chứng logs vào CI documentation.

**Tiêu chí đạt:** không có test/process/container chờ vô hạn; timeout dẫn tới cancellation có kiểm soát; tác vụ đồng thời bị giới hạn; process con/resource được dọn trong các đường pass/fail/timeout; CI giữ được log và trả đúng exit status của lỗi gốc.

## Tài liệu tham khảo chính thức

- [Java 17 – Process API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html)
- [Java 17 – ProcessHandle API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html)
- [Java 17 – ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Java 17 – Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [JUnit 5.10 – Timeout for Tests](https://junit.org/junit5/docs/5.10.2/user-guide/#writing-tests-timeouts)
- [Maven Surefire – Fork Options and Timeouts](https://maven.apache.org/surefire/maven-surefire-plugin/examples/fork-options-and-timeouts.html)
- [Maven Failsafe Plugin – Usage](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Gradle – Java Testing](https://docs.gradle.org/current/userguide/java_testing.html)
- [Docker – Run Containers](https://docs.docker.com/engine/containers/run/)
- [Docker – Stop Containers](https://docs.docker.com/reference/cli/docker/container/stop/)
- [GitHub Actions – Workflow Syntax: timeout-minutes](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions#jobsjob_idtimeout-minutes)
