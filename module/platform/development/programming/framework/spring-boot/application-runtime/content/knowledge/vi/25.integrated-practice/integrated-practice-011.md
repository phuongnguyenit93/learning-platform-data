# Kiểm tra rò rỉ tài nguyên qua nhiều lần mở và đóng ApplicationContext trong Spring Boot

## 1. Mục tiêu thực hành

Một ứng dụng Spring Boot có thể chạy đúng khi khởi động lần đầu nhưng vẫn **rò rỉ tài nguyên** khi cùng JVM phải tạo, đóng rồi tạo lại `ApplicationContext` nhiều lần. Tình huống này xuất hiện trong:

- Kiểm thử tích hợp tạo nhiều context.
- Spring Boot DevTools restart trong môi trường phát triển.
- Ứng dụng có context con, plugin/module được bật tắt động.
- Batch/CLI khởi chạy từng phiên xử lý trong một process.
- Ứng dụng thử nghiệm lifecycle, cấu hình và hot-reload.
- Các thư viện đăng ký listener, tạo executor, mở socket/file, nhưng không trả lại tài nguyên khi context đóng.

Một số lỗi chỉ xuất hiện **sau 10, 20 hoặc 100 vòng**. Context đã đóng nhưng vẫn còn thread, file descriptor, connection pool, subscription hoặc static reference giữ bean/classloader cũ.

**Mục tiêu của bài:** xây dựng một bài thực hành Java 17+/Spring Boot 3.3 với hai tài nguyên thực: **executor có thread riêng** và **temporary file đang mở bằng FileChannel**. Chạy lặp nhiều lần tạo/đóng context, kiểm tra số instance mở/đóng, viết JUnit tests cho trường hợp đúng và trường hợp cố ý thiếu destructor, rồi mở rộng sang các tài nguyên thường thấy trong ứng dụng production.

Kết quả mong đợi là **không còn tài nguyên đang active sau mỗi vòng**, số lần tạo bằng số lần dọn dẹp, không cần khởi động lại JVM để che rò rỉ.

### 1.1. Điều kiện đạt

Sau `N` lượt tạo/đóng context trong **cùng JVM**:

1. Mỗi lượt khởi động context thành công hoặc báo lỗi đúng kỳ vọng.
2. Tài nguyên được tạo thuộc đúng context và có chủ sở hữu rõ ràng.
3. `close()` của context được gọi **ngay cả khi code trong context ném exception**.
4. Các bean singleton có destructor được Spring gọi theo lifecycle.
5. Từng executor được yêu cầu shutdown và xác nhận đã terminate trong một deadline hữu hạn.
6. Mỗi file handle được đóng; temporary file đã tạo được dọn nếu chính sách yêu cầu.
7. Bộ đếm `active` trở về baseline sau mỗi lượt, không chỉ ở cuối toàn bộ vòng chạy.
8. Tài nguyên trong trường hợp startup fail cũng được kiểm thử, không chỉ đường thành công.
9. Test không để lại zombie threads hoặc file handles sau khi kết thúc.
10. Không dùng một heap snapshot duy nhất làm “chứng cứ không leak”.

## 2. Trước hết: thế nào là rò rỉ tài nguyên?

**Rò rỉ tài nguyên** nghĩa là một đối tượng hoặc handle vẫn bị giữ **sau khi nó không còn cần thiết**, dẫn tới tiêu hao giới hạn hệ thống hoặc ngăn thu hồi.

| Loại tài nguyên | Ví dụ | Dấu hiệu cần đo |
| --- | --- | --- |
| Java threads | `ExecutorService`, scheduler, worker tự tạo | Thread còn sống, executor chưa terminate |
| File handle | `InputStream`, `FileChannel`, `WatchService` | Channel còn mở, số open file descriptors không giảm |
| Network socket | `ServerSocket`, HTTP client, gRPC channel | Socket chưa đóng, connection/state còn tồn tại |
| Database connection pool | HikariCP, pool tự tạo | Pool không shutdown, connections còn active/idle |
| External subscriptions | Message broker consumer, listener, callback | Subscription/listener vẫn đăng ký |
| Heap objects | Cache, session, bean không còn dùng | Retained references qua GC cycles |
| Classloader | DevTools restart loader hoặc plugin loader | Loader cũ bị static cache/thread giữ tham chiếu |
| Native memory | Direct buffers, thư viện JNI | Native allocation còn giữ ngoài heap |
| Scheduled tasks | Timer, scheduler, repeating jobs | Task còn chạy sau context close |
| Resource bên ngoài | Lease, distributed lock, temporary cloud object | Lock/lease không được release hoặc expire đúng |

**Không phải mọi tăng trưởng đều là leak.** Một JVM có thể mở rộng heap đã commit, làm nóng JIT, lưu metadata hoặc tạo caches hợp lệ. Sau một số vòng, những số đo này có thể ổn định. Cần phân biệt:

- **Live resource count**: tài nguyên thật đang mở.
- **Total created count**: tổng số tài nguyên từng tạo.
- **Total closed count**: tổng số đã đóng thành công.
- **Heap used/committed**: tình trạng bộ nhớ của JVM, không trực tiếp chứng minh handle còn mở.
- **Retained object graph**: đường tham chiếu khiến object/classloader không được thu gom.

Công thức đo hữu ích cho một loại tài nguyên có tracking nhất quán:

```text
active = opened - closed
```

Đây là **invariant logic của bộ đếm mẫu**. Nó không tự thay thế phép đo OS: một bug cập nhật counter sai vẫn có thể báo 0 trong khi file descriptor thực chưa được đóng.

## 3. Vì sao phải lặp trong cùng một JVM?

Nếu chỉ chạy:

```bash
java -jar app.jar
java -jar app.jar
java -jar app.jar
```

thì mỗi lệnh tạo một process mới. Hệ điều hành thường thu hồi nhiều handle khi process kết thúc, nên **không kiểm tra được một static cache hoặc executor bị bỏ quên qua các lượt context close trong cùng JVM**.

Bài test đúng cho mục tiêu này cần:

```text
JVM process: bắt đầu
    |
    +-- context #1 open -> sử dụng -> close
    |
    +-- context #2 open -> sử dụng -> close
    |
    +-- context #3 open -> sử dụng -> close
    |
    ...
    |
    +-- context #N open -> sử dụng -> close
    |
JVM process: kết thúc
```

Đặc biệt, phải **tạo context mới cho mỗi vòng**. Lấy cùng context từ cache của test framework N lần không tương đương N lần khởi động mới.

### 3.1. Đừng nhầm @SpringBootTest với N vòng mở/đóng

Spring TestContext Framework có **context caching** để giảm thời gian chạy test. Một loạt method `@SpringBootTest` dùng cùng cấu hình có thể được phục vụ bởi **một context được tái sử dụng**, không phải một context mới mỗi test.

Do đó nếu mục tiêu là kiểm thử lifecycle lặp:

- Dùng `SpringApplicationBuilder` / `SpringApplication.run` để tạo context mới chủ động trong vòng lặp.
- Hoặc dùng `ApplicationContextRunner` tạo context cho từng lượt callback khi bài test chỉ yêu cầu một cấu hình nhỏ.
- Không mặc định `@DirtiesContext` cho mọi test để ép tạo context nếu có thể viết một harness ngắn, rõ trách nhiệm.
- Khi dùng `@DirtiesContext`, hiểu đó là cơ chế loại context khỏi cache, **không phải bộ đo resource leaks**.

## 4. Spring quản lý gì khi ApplicationContext.close()?

Với context đã refresh thành công, `ConfigurableApplicationContext.close()` thực hiện đường đóng lifecycle và hủy các singleton phù hợp.

Một mô hình khái quát:

```text
context.close()
    |
    +-- ContextClosedEvent
    |
    +-- LifecycleProcessor.onClose()
    |      +-- stop các Lifecycle/SmartLifecycle beans phù hợp
    |      +-- SmartLifecycle.stop(Runnable) với callback
    |
    +-- destroySingletons()
           +-- @PreDestroy
           +-- DisposableBean.destroy()
           +-- custom destroy method / close / shutdown
    |
    +-- release context-specific infrastructure
```

Đây là sơ đồ **mức ý tưởng**; thứ tự chi tiết phụ thuộc loại context và có ngoại lệ khi refresh thất bại.

Các điểm quan trọng:

1. Spring chỉ có thể destroy những instance **thuộc vòng đời nó quản lý**.
2. `@Bean(destroyMethod = "close")` khai báo rõ phương thức dọn tài nguyên.
3. Với `@Bean` methods, Spring Framework còn có cơ chế **tự suy luận** `close()`/`shutdown()` phù hợp; explicit `destroyMethod` dễ đọc và dễ kiểm thử.
4. Bean `prototype` không được Spring tự quản lý toàn bộ destruction như singleton.
5. Một object được `new` rồi lưu trong static field nhưng không đăng ký resource ownership có thể vẫn sống sau context close.
6. Tài nguyên mở trong constructor/factory nhưng **lỗi trước khi bean hoàn tất tạo** phải có cleanup ngay tại điểm cấp phát.
7. `context.stop()` chỉ điều phối lifecycle stop; nó **không tương đương** `context.close()` và không hủy tất cả singleton.
8. Khi context đóng, Spring không tự xóa bất kỳ **temporary file ngoài process** nào nếu resource owner không được viết để dọn nó.

### 4.1. @Bean destroyMethod suy luận và tắt suy luận

Một bean được tạo bằng:

```java
@Bean
SomeCloseableClient client() {
    return new SomeCloseableClient();
}
```

có thể được Spring tự đăng ký `close()`/`shutdown()` nếu phương thức phù hợp tồn tại. Đây là hợp đồng tiện lợi cho `@Bean`.

Nếu viết:

```java
@Bean(destroyMethod = "")
SomeCloseableClient client() {
    return new SomeCloseableClient();
}
```

thì bạn đã **tắt destroy-method inference** cho bean đó. Nếu đối tượng chỉ dựa vào `close()` được suy luận, context close có thể không gọi nó.

Đây là một **biến thể phản ví dụ**, không nên dùng trên resource đang sở hữu handle trừ khi một owner khác thật sự đóng nó.

Lưu ý: `destroyMethod = ""` **không vô hiệu hóa mọi cơ chế destruction**, chẳng hạn interface `DisposableBean` vẫn có callback riêng. Vì vậy cần biết chính xác bean đã implement những contract nào.

## 5. Thiết kế phép đo: baseline, inside, after-close

Một bài kiểm thử cần đo ở tối thiểu ba thời điểm:

| Thời điểm | Mục tiêu |
| --- | --- |
| Baseline trước vòng lặp | Lấy số resource active trước khi tạo context mới |
| Bên trong context đang dùng | Chứng minh resource thật sự đã được tạo và sử dụng |
| Sau `context.close()` | Xác nhận resource đã trả về baseline |

Ví dụ với **một executor và một file handle mỗi context**:

```text
Trước vòng 1: worker.active=0, file.active=0

Trong context 1:
    worker.active=1
    file.active=1

Sau close context 1:
    worker.active=0
    file.active=0

Trong context 2:
    worker.active=1
    file.active=1

Sau close context 2:
    worker.active=0
    file.active=0

...
```

Cần có **cặp counter opened/closed** để kiểm tra số lần tạo bằng số lần cleanup, không chỉ đếm active ở một thời điểm.

**Không sửa bộ đếm active bằng tay sau mỗi vòng test.** Reset bằng `ACTIVE.set(0)` có thể che mất leak thật. Nếu muốn so baseline từ trước khi test, lưu một số nguyên `beforeActive`, rồi assert `afterActive == beforeActive`; không ép trạng thái toàn cục trở về 0 một cách giả tạo.

## 6. Project runnable Spring Boot 3.3 / Java 17

Ví dụ dùng:

- Một bean `TrackedWorker` sở hữu `ExecutorService`.
- Một bean `TrackedTempFile` sở hữu `FileChannel` và temporary file.
- Một vòng lặp chủ động tạo/đóng **năm application contexts trong cùng một JVM**.
- Hai bean có `@Bean(destroyMethod = "close")`.
- Một bài JUnit kiểm tra nhiều vòng và một bài cố tình tắt destruction.
- Không cần database, web server hoặc dịch vụ ngoài nên dễ chạy trong môi trường học.

### 6.1. Cấu trúc

```text
context-leak-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          contextleak/
            ContextLeakLabApplication.java
            TrackedWorker.java
            TrackedTempFile.java
      resources/
        application.properties
    test/
      java/
        qa/
          contextleak/
            RepeatedContextTests.java
```

Tách package `qa.contextleak` của test ra khỏi `demo.contextleak` để những `@Configuration` chỉ phục vụ test **không bị component-scan của main application**.

### 6.2. settings.gradle

```groovy
rootProject.name = 'context-leak-lab'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.13 được dùng để minh họa API nhánh 3.3; khi lập dự án mới hãy chọn bản còn được hỗ trợ. Cần Gradle/Gradle wrapper tương thích và JDK 17+. Những file này **không tự sinh** `gradlew`: nếu chưa có wrapper, dùng Gradle đã cài đặt chạy `gradle wrapper`.

### 6.4. application.properties

```properties
spring.application.name=context-leak-lab
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=OFF
```

`WebApplicationType.NONE` loại bỏ web server để test không phụ thuộc port. Log level chỉ giảm nhiễu ví dụ; production không nên tắt toàn bộ log vì có thể che lỗi vận hành.

## 7. TrackedWorker.java: tạo, sử dụng và đóng executor

File `src/main/java/demo/contextleak/TrackedWorker.java`:

```java
package demo.contextleak;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class TrackedWorker implements AutoCloseable {

    private static final AtomicInteger OPENED = new AtomicInteger();
    private static final AtomicInteger CLOSED = new AtomicInteger();
    private static final AtomicInteger ACTIVE = new AtomicInteger();
    private static final AtomicInteger THREAD_IDS = new AtomicInteger();

    private final AtomicBoolean closed = new AtomicBoolean(false);
    private final ExecutorService executor;

    public TrackedWorker() {
        ThreadFactory factory = task -> {
            Thread thread = new Thread(
                    task,
                    "context-leak-worker-"
                            + THREAD_IDS.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        };

        this.executor = Executors.newSingleThreadExecutor(factory);

        OPENED.incrementAndGet();
        ACTIVE.incrementAndGet();
    }

    public String executeProbe() throws Exception {
        Future<String> result = executor.submit(
                () -> Thread.currentThread().getName());

        return result.get(5, TimeUnit.SECONDS);
    }

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        executor.shutdown();

        try {
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();

                if (!executor.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Worker did not terminate.");
                }
            }
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while closing worker.", ex);
        }

        CLOSED.incrementAndGet();
        ACTIVE.decrementAndGet();
    }

    public static int opened() {
        return OPENED.get();
    }

    public static int closed() {
        return CLOSED.get();
    }

    public static int active() {
        return ACTIVE.get();
    }
}
```

### 7.1. Những điều cần giải thích

- `Executors.newSingleThreadExecutor(...)` tạo một executor quản lý một worker thread khi có task cần chạy.
- `ThreadFactory` đặt tên để có thể tìm thread trong thread dump.
- `setDaemon(true)` được dùng **chỉ trong lab** nhằm giảm nguy cơ một lỗi test giữ process Java mãi; **daemon không phải cleanup**. Một thread bị leak dù daemon vẫn tiêu thụ tài nguyên cho đến khi JVM kết thúc.
- `executeProbe()` thật sự submit một task, nên không chỉ kiểm tra một object `ExecutorService` chưa từng được sử dụng.
- `Future.get(5, TimeUnit.SECONDS)` có timeout để bài test không treo vô hạn.
- `close()` gọi `shutdown()`, chờ termination có deadline; nếu hết hạn, gửi interrupt bằng `shutdownNow()`.
- `shutdownNow()` là **best-effort interrupt**, không bảo đảm task đang chặn ở mọi I/O sẽ dừng.
- `AtomicBoolean closed` giúp tránh đóng hai lần/ghi counter hai lần.
- `ACTIVE` chỉ giảm khi shutdown được xác nhận hoàn tất.

**Ý nghĩa counters:** `OPENED`/`CLOSED`/`ACTIVE` là hệ đo logic để test lifecycle của ví dụ. Chúng không tự chứng minh thread không leak ở mức JVM nếu code khác tạo thread không đi qua tracker.

### 7.2. Một giới hạn của thiết kế minh họa

Nếu `close()` ném exception vì executor không terminate, `closed` đã chuyển true nhưng `ACTIVE` chưa giảm. Test phát hiện trạng thái bất thường và không giả vờ thành công. Tuy nhiên implementation thực có thể cần state machine `OPEN → CLOSING → CLOSED/FAILED` để xử lý retry hoặc báo lỗi tốt hơn. Đây là bài lab có chủ đích với tác vụ ngắn, không phải thư viện quản lý executor đa năng.

## 8. TrackedTempFile.java: FileChannel và temporary file

File `src/main/java/demo/contextleak/TrackedTempFile.java`:

```java
package demo.contextleak;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class TrackedTempFile implements AutoCloseable {

    private static final AtomicInteger OPENED = new AtomicInteger();
    private static final AtomicInteger CLOSED = new AtomicInteger();
    private static final AtomicInteger ACTIVE = new AtomicInteger();

    private final AtomicBoolean closed = new AtomicBoolean(false);
    private final Path path;
    private final FileChannel channel;

    public TrackedTempFile() throws IOException {
        Path created = Files.createTempFile(
                "context-leak-lab-", ".tmp");

        FileChannel openedChannel;

        try {
            openedChannel = FileChannel.open(
                    created, StandardOpenOption.WRITE);
        } catch (IOException | RuntimeException failure) {
            try {
                Files.deleteIfExists(created);
            } catch (IOException cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }

            throw failure;
        }

        this.path = created;
        this.channel = openedChannel;

        OPENED.incrementAndGet();
        ACTIVE.incrementAndGet();
    }

    public void writeOneByte() throws IOException {
        ByteBuffer buffer = ByteBuffer.wrap(new byte[] { 1 });

        while (buffer.hasRemaining()) {
            channel.write(buffer);
        }
    }

    @Override
    public void close() throws IOException {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        IOException failure = null;

        try {
            channel.close();
        } catch (IOException ex) {
            failure = ex;
        }

        try {
            Files.deleteIfExists(path);
        } catch (IOException ex) {
            if (failure == null) {
                failure = ex;
            } else {
                failure.addSuppressed(ex);
            }
        }

        if (failure != null) {
            throw failure;
        }

        CLOSED.incrementAndGet();
        ACTIVE.decrementAndGet();
    }

    public static int opened() {
        return OPENED.get();
    }

    public static int closed() {
        return CLOSED.get();
    }

    public static int active() {
        return ACTIVE.get();
    }
}
```

### 8.1. Vì sao cần try/catch ngay trong constructor?

Thứ tự cấp phát:

1. `Files.createTempFile(...)` tạo một file trên filesystem.
2. `FileChannel.open(...)` mở channel để ghi.
3. Nếu mở channel thành công, object nhận ownership của path/channel.
4. Nếu mở channel thất bại, constructor tự cố xóa temporary file.

Nếu constructor ném exception ở bước 2, bean chưa được Spring tạo hoàn chỉnh. **Không được dựa vào `@PreDestroy` của bean chưa tồn tại** để dọn temporary file.

`failure.addSuppressed(cleanupFailure)` giữ lỗi mở channel làm nguyên nhân chính, đồng thời không làm mất thông tin lỗi xóa file.

### 8.2. Vì sao cần close channel trước delete?

Một số hệ điều hành, đặc biệt Windows, không cho xóa file khi còn handle đang mở. Đóng channel trước rồi mới xóa file giúp tuân thủ ownership và tăng khả năng cleanup thành công.

Đây là **tài nguyên file thật**, không chỉ đếm object. Tuy vậy file deletion có thể vẫn bị ảnh hưởng bởi permissions, antivirus, filesystem hoặc tiến trình khác. Trong CI phải bảo đảm thư mục temp của JVM có quyền ghi/xóa và coi lỗi OS là tín hiệu cần điều tra, không vội sửa counter để qua test.

### 8.3. Dấu hiệu tài nguyên chưa dọn

- `TrackedTempFile.active() > 0` sau context close.
- `opened() > closed()`.
- Temporary file còn tồn tại sau khi context được đóng thành công.
- Số open file descriptors tăng dần trong quá trình lặp.
- Trên Windows, xóa hoặc di chuyển một file thử nghiệm có thể thất bại do handle chưa đóng; nhưng không dùng khả năng xóa file là phép đo duy nhất trên mọi OS.

## 9. ContextLeakLabApplication.java: mở/đóng context nhiều lần

File `src/main/java/demo/contextleak/ContextLeakLabApplication.java`:

```java
package demo.contextleak;

import java.io.IOException;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class ContextLeakLabApplication {

    @Bean(destroyMethod = "close")
    TrackedWorker trackedWorker() {
        return new TrackedWorker();
    }

    @Bean(destroyMethod = "close")
    TrackedTempFile trackedTempFile() throws IOException {
        return new TrackedTempFile();
    }

    public static ConfigurableApplicationContext openContext() {
        return new SpringApplicationBuilder(
                ContextLeakLabApplication.class)
                .web(WebApplicationType.NONE)
                .run();
    }

    public static void main(String[] args) throws Exception {
        final int rounds = 5;

        for (int round = 1; round <= rounds; round++) {
            try (ConfigurableApplicationContext context =
                    openContext()) {

                TrackedWorker worker =
                        context.getBean(TrackedWorker.class);
                TrackedTempFile file =
                        context.getBean(TrackedTempFile.class);

                worker.executeProbe();
                file.writeOneByte();

                require(TrackedWorker.active() == 1,
                        "Worker count inside context is wrong.");
                require(TrackedTempFile.active() == 1,
                        "File count inside context is wrong.");

                System.out.printf(
                        "round=%d inside worker=%d file=%d%n",
                        round,
                        TrackedWorker.active(),
                        TrackedTempFile.active());
            }

            require(TrackedWorker.active() == 0,
                    "Worker leak after context close.");
            require(TrackedTempFile.active() == 0,
                    "File leak after context close.");

            System.out.printf(
                    "round=%d after worker=%d file=%d%n",
                    round,
                    TrackedWorker.active(),
                    TrackedTempFile.active());
        }

        require(TrackedWorker.opened() == rounds,
                "Unexpected worker allocation count.");
        require(TrackedWorker.closed() == rounds,
                "Not all workers were closed.");
        require(TrackedTempFile.opened() == rounds,
                "Unexpected file allocation count.");
        require(TrackedTempFile.closed() == rounds,
                "Not all temp files were closed.");

        System.out.printf(
                "PASS openedWorkers=%d closedWorkers=%d "
                + "openedFiles=%d closedFiles=%d%n",
                TrackedWorker.opened(),
                TrackedWorker.closed(),
                TrackedTempFile.opened(),
                TrackedTempFile.closed());
    }

    private static void require(
            boolean condition, String explanation) {

        if (!condition) {
            throw new IllegalStateException(explanation);
        }
    }
}
```

### 9.1. Vì sao dùng SpringApplicationBuilder thay vì một context đơn giản?

`SpringApplicationBuilder` thực sự chạy cơ chế khởi động Spring Boot và tạo application context mới với môi trường Boot. Cách này gần với runtime hơn một `AnnotationConfigApplicationContext` thuần.

`WebApplicationType.NONE` giúp tránh tạo web server trong demo, nên chỉ có các tài nguyên đã khai báo cần được đo. Khi phát triển một service web thật, cần bổ sung đo thread/connection của embedded server, không suy luận chỉ từ bài non-web.

### 9.2. Vì sao dùng try-with-resources?

`ConfigurableApplicationContext` có API `close()` và tương thích `AutoCloseable`, nên:

```java
try (ConfigurableApplicationContext context = openContext()) {
    // Sử dụng bean.
}
```

bảo đảm Java gọi `close()` khi rời block, kể cả khi code bên trong ném exception. Đây là điểm cốt lõi của test leak: **không để test tự gây leak do quên đóng context**.

**Tránh:**

```java
ConfigurableApplicationContext context = openContext();
doSomethingThatCanFail(context);
context.close();
```

Đây là **pseudo-code**; `doSomethingThatCanFail` chưa định nghĩa. Nếu lời gọi giữa chừng ném exception, `close()` có thể không chạy. Dùng `try-with-resources` hoặc `finally` đúng nơi.

### 9.3. Vì sao kiểm tra sau từng vòng?

Nếu chỉ kiểm tra sau vòng thứ năm, một bean mở muộn hoặc một lỗi chỉ xảy ra ở một lượt cụ thể có thể khó khoanh vùng. Kiểm tra sau **mỗi lần đóng context** cho biết vòng nào bắt đầu mất cân bằng, giảm đáng kể công debug.

### 9.4. Output đáng tin của demo

Giả sử chạy ứng dụng độc lập, các bean khởi tạo/đóng thành công và không có tài nguyên khác can thiệp vào static counters, những dòng **do chính ứng dụng in ra**:

```text
round=1 inside worker=1 file=1
round=1 after worker=0 file=0
round=2 inside worker=1 file=1
round=2 after worker=0 file=0
round=3 inside worker=1 file=1
round=3 after worker=0 file=0
round=4 inside worker=1 file=1
round=4 after worker=0 file=0
round=5 inside worker=1 file=1
round=5 after worker=0 file=0
PASS openedWorkers=5 closedWorkers=5 openedFiles=5 closedFiles=5
```

Có thể có thêm output từ Gradle/JVM nếu chạy qua build tool; các dòng trên là các marker do code in ra, không tuyên bố toàn bộ stdout chỉ có đúng 11 dòng.

Điểm cần đọc kỹ:

- Trong context: mỗi loại tài nguyên có đúng **một instance active**.
- Sau `close()`: cả hai loại về 0.
- Mỗi loại được tạo và đóng đúng năm lần.
- Không cần `System.gc()` để bộ đếm đúng.
- Không dùng process restart giữa các vòng: cùng một `main` thực hiện hết năm lần.

## 10. Biên dịch, chạy và đọc kết quả

Sau khi có Gradle wrapper:

```bash
./gradlew clean test
./gradlew bootRun
```

Hoặc build và chạy JAR:

```bash
./gradlew bootJar
java -jar build/libs/context-leak-lab-1.0.0.jar
```

Tên JAR lấy từ `settings.gradle` và version trong `build.gradle` minh họa; nếu có cấu hình custom archive, dùng tên file được build thực tế.

**Nếu hệ thống không có quyền ghi temporary file**, `TrackedTempFile` có thể ném lỗi khởi động. Test này cố tình dùng file thật nên quyền truy cập OS là một điều kiện môi trường. Chạy trong thư mục temp hợp lệ, không “sửa” bài test bằng cách bỏ kiểm tra cleanup.

### 10.1. Tăng số vòng

Có thể sửa:

```java
final int rounds = 5;
```

thành:

```java
final int rounds = 50;
```

Đây là **biến thể**, không thêm một declaration `rounds` thứ hai. Chạy 5 vòng để xác nhận logic; tăng lên 50–100 vòng khi đo xu hướng lâu dài. Tăng số vòng không tự chứng minh kết quả chính xác nếu chỉ lấy một snapshot ở cuối.

### 10.2. Chạy trong cùng JVM mới có ý nghĩa

Lệnh `./gradlew bootRun` có thể launch một Java process. Bên trong **process đó**, `main` tạo 5 hoặc 50 application contexts. Đó mới là phép thử leak qua nhiều context.

Nếu bạn chạy `./gradlew bootRun` 50 lần, mỗi lần một process mới, kết quả không tương đương.

## 11. JUnit test cho vòng mở/đóng lặp

File `src/test/java/qa/contextleak/RepeatedContextTests.java`:

```java
package qa.contextleak;

import java.util.concurrent.atomic.AtomicReference;

import demo.contextleak.ContextLeakLabApplication;
import demo.contextleak.TrackedTempFile;
import demo.contextleak.TrackedWorker;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class RepeatedContextTests {

    @Test
    void closesEveryContextAndReturnsToBaseline() throws Exception {
        int workerActiveBefore = TrackedWorker.active();
        int fileActiveBefore = TrackedTempFile.active();

        int workerOpenedBefore = TrackedWorker.opened();
        int workerClosedBefore = TrackedWorker.closed();
        int fileOpenedBefore = TrackedTempFile.opened();
        int fileClosedBefore = TrackedTempFile.closed();

        final int rounds = 3;

        for (int i = 0; i < rounds; i++) {
            try (ConfigurableApplicationContext context =
                    ContextLeakLabApplication.openContext()) {

                context.getBean(TrackedWorker.class).executeProbe();
                context.getBean(TrackedTempFile.class).writeOneByte();

                assertThat(TrackedWorker.active())
                        .isEqualTo(workerActiveBefore + 1);
                assertThat(TrackedTempFile.active())
                        .isEqualTo(fileActiveBefore + 1);
            }

            assertThat(TrackedWorker.active())
                    .isEqualTo(workerActiveBefore);
            assertThat(TrackedTempFile.active())
                    .isEqualTo(fileActiveBefore);
        }

        assertThat(TrackedWorker.opened() - workerOpenedBefore)
                .isEqualTo(rounds);
        assertThat(TrackedWorker.closed() - workerClosedBefore)
                .isEqualTo(rounds);
        assertThat(TrackedTempFile.opened() - fileOpenedBefore)
                .isEqualTo(rounds);
        assertThat(TrackedTempFile.closed() - fileClosedBefore)
                .isEqualTo(rounds);
    }

    @Test
    void detectsMissingDestroyMethodThenCleansTestResource() {
        int activeBefore = TrackedWorker.active();
        AtomicReference<TrackedWorker> created =
                new AtomicReference<>();

        try {
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            MissingDestroyConfiguration.class)
                    .run(context -> {
                        assertThat(context).hasNotFailed();
                        created.set(
                                context.getBean(TrackedWorker.class));

                        try {
                            created.get().executeProbe();
                        } catch (Exception ex) {
                            throw new IllegalStateException(ex);
                        }
                    });

            // ApplicationContextRunner đã đóng context,
            // nhưng destroyMethod="" đã tắt suy luận close().
            assertThat(TrackedWorker.active())
                    .isEqualTo(activeBefore + 1);
        } finally {
            TrackedWorker worker = created.get();

            if (worker != null) {
                worker.close();
            }
        }

        assertThat(TrackedWorker.active())
                .isEqualTo(activeBefore);
    }

    @Test
    void cleansCreatedSingletonWhenLaterBeanFails() {
        int activeBefore = TrackedWorker.active();
        int closedBefore = TrackedWorker.closed();

        new ApplicationContextRunner()
                .withUserConfiguration(FailingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    IllegalStateException.class);
                });

        assertThat(TrackedWorker.active())
                .isEqualTo(activeBefore);
        assertThat(TrackedWorker.closed())
                .isEqualTo(closedBefore + 1);
    }

    @Configuration(proxyBeanMethods = false)
    static class MissingDestroyConfiguration {

        @Bean(destroyMethod = "")
        TrackedWorker unmanagedWorker() {
            return new TrackedWorker();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FailingConfiguration {

        @Bean(destroyMethod = "close")
        TrackedWorker resource() {
            return new TrackedWorker();
        }

        @Bean
        String failingBean(TrackedWorker resource) {
            throw new IllegalStateException(
                    "simulated-refresh-failure");
        }
    }
}
```

Các test trên được biên dịch trong project `spring-boot-starter-test`, với JUnit Jupiter và AssertJ.

### 11.1. Test 1 chứng minh điều gì?

- Cùng một JVM test mở **ba contexts mới**.
- Bên trong mỗi context, worker và file được thực sự sử dụng.
- Sau mỗi `close()`, số active trở lại baseline.
- Tổng số opened/closed tăng đúng ba.
- Test không cần `@SpringBootTest` và không phụ thuộc context cache.

Giá trị baseline được đo **trước khi test chạy**, nên không giả định các test khác trong JVM chưa từng tạo resource. Tuy nhiên các tests dùng static counters vẫn nên chạy **không song song** hoặc có tài nguyên đồng bộ hóa phù hợp; test này không được thiết kế cho concurrent context creation cùng lúc.

### 11.2. Test 2 là negative control có cleanup an toàn

`MissingDestroyConfiguration` khai báo:

```java
@Bean(destroyMethod = "")
TrackedWorker unmanagedWorker() {
    return new TrackedWorker();
}
```

Spring không tự gọi `close()` theo destroy-method inference cho bean này. `ApplicationContextRunner` đóng context sau callback nhưng resource vẫn active theo tracker.

Điểm quan trọng là test dùng `finally` để **tự đóng worker**, không để một demo “leak có chủ đích” gây leak thật cho những test chạy sau.

Mục đích của **negative control** là chứng minh bộ đếm phát hiện tình huống thiếu destructor, chứ không chỉ luôn báo thành công.

### 11.3. Test 3 kiểm tra đường refresh thất bại

`FailingConfiguration` khai báo resource trước, rồi `failingBean(TrackedWorker resource)` phụ thuộc vào nó và ném lỗi. Vì resource đã được tạo thành singleton và có destructor đăng ký, Spring Framework cố hủy nó khi refresh thất bại.

Test kiểm tra:

- Context báo failed.
- Root cause là lỗi cố tình ném.
- Số active trở về baseline.
- Số close tăng một.

**Giới hạn:** nếu chính constructor của `TrackedWorker` ném exception **trước khi return bean**, Spring có thể chưa có instance được đăng ký destructor. Resource mở dở phải được dọn ngay trong constructor/factory.

### 11.4. Vì sao đưa test configuration sang package khác?

Main application ở `demo.contextleak`, trong khi test ở `qa.contextleak`. Nếu các test-only `@Configuration` nằm bên trong package được main component scanning quét, chúng có thể vô tình được tạo trong vòng lặp main test, làm số bean/tài nguyên vượt dự kiến.

Giữ test config ngoài base package của application là một cách tránh hiện tượng **test configuration ảnh hưởng startup của chương trình được kiểm tra**.

## 12. Test thất bại trong @Bean factory: ownership trước khi return

Xem ví dụ phản diện:

```java
@Bean(destroyMethod = "close")
RemoteSession remoteSession() throws Exception {
    RemoteSession session = new RemoteSession();
    session.open();
    throw new IllegalStateException("after-open failure");
}
```

Đây là **snippet**, không có class `RemoteSession` được định nghĩa trong project demo.

Tài nguyên `session` đã mở nhưng bean factory không `return`. Container có thể **không biết instance nào cần đóng**, vì chưa có bean được đăng ký hoàn chỉnh. Đừng dựa vào `@PreDestroy`/destroyMethod của bean chưa hoàn tất.

Một cách an toàn hơn:

```java
@Bean(destroyMethod = "close")
RemoteSession remoteSession() throws Exception {
    RemoteSession session = new RemoteSession();

    try {
        session.open();
        return session;
    } catch (Exception | Error failure) {
        try {
            session.close();
        } catch (Exception cleanupFailure) {
            failure.addSuppressed(cleanupFailure);
        }

        throw failure;
    }
}
```

Đây cũng là **snippet**, yêu cầu type `RemoteSession` triển khai `open/close`. Nguyên tắc: **trước khi return bean, factory vẫn sở hữu resource và phải rollback khi lỗi**; sau khi return thành công, Spring có cơ chế destroy resource.

### 12.1. Test tình huống lỗi cấp phát một phần

Một test tốt nên thử:

- Mở file 1 thành công.
- Mở file 2 thất bại.
- Xác nhận file 1 được đóng dù bean không tạo xong.
- Giữ root cause của file 2.
- Ghi cleanup errors là suppressed nếu có.
- Không tin rằng bean post-processor/destructor chắc chắn chạy cho một bean chưa hoàn tất tạo.

Nếu resource không thể đóng an toàn sau lỗi constructor, cần sửa thiết kế resource hoặc dùng factory có rollback, không chỉ thêm annotation lifecycle.

## 13. Test có thật sự phát hiện thread leak không?

Counter có thể nói worker `active=0`, nhưng để chẩn đoán thực tế có thể kiểm tra thêm **thread sống theo prefix**, thread dump hoặc Java Flight Recorder.

### 13.1. Thread name

Trong `TrackedWorker`, thread được đặt tên:

```text
context-leak-worker-1
context-leak-worker-2
...
```

Nhờ vậy có thể tìm thread tương ứng trong JVM thread dump. Tuy nhiên **thread name có thể lặp hoặc bị đổi** trong thư viện thật; không dùng duy nhất tên thread làm định danh nghiệp vụ.

### 13.2. java.lang.management.ThreadMXBean

Một JVM có thể dùng:

```java
ThreadMXBean bean =
        ManagementFactory.getThreadMXBean();

int total = bean.getThreadCount();
System.out.println("jvm.threadCount=" + total);
```

Đây là snippet với imports `java.lang.management.ManagementFactory` và `ThreadMXBean`.

Chỉ số này cho biết số **live platform threads** theo scope API/VM, nhưng có thể biến động do GC, JIT, timers, agent và các thành phần Spring. Không assert `getThreadCount()` phải đúng bằng một con số cố định sau mỗi vòng; nhiều thứ không liên quan test có thể tạo hoặc dừng thread trong cùng JVM.

**Với virtual threads Java 21+, cần công cụ riêng phù hợp**; một số thread enumeration APIs không đại diện đầy đủ cho mọi virtual thread, nên không lấy một ThreadMXBean snapshot để kết luận không có virtual-thread leak.

### 13.3. Theo dõi riêng thread prefix bằng instrumentation

Ở một test JVM đơn giản dùng platform thread, có thể xem:

```java
long count = Thread.getAllStackTraces()
        .keySet()
        .stream()
        .filter(Thread::isAlive)
        .filter(thread -> thread.getName()
                .startsWith("context-leak-worker-"))
        .count();

System.out.println("matchingThreads=" + count);
```

Đây là snippet đặt trong method Java 17+ với imports chuẩn; nó đo threads còn thấy được tại thời điểm quan sát. Thread kết thúc có thể chưa biến mất trong đúng một snapshot, vì vậy nên có bounded polling cho một test thread-liveness nếu thật sự cần. Không dùng `Thread.sleep` tùy ý làm điều kiện duy nhất cho test pass.

Test chính vẫn nên dùng `ExecutorService.awaitTermination` và tracker vì chúng gắn trực tiếp với contract resource owner.

## 14. File descriptors: đo trực tiếp ở cấp OS

Trên Linux có thể quan sát một process:

```bash
ls /proc/<PID>/fd | wc -l
```

`<PID>` ở đây là **ký hiệu thay thế** bằng PID thật, không phải một lệnh copy-run nguyên văn. Đường `/proc` tùy OS/container và permissions.

Với shell có PID của Java process:

```bash
ls "/proc/$PID/fd" | wc -l
```

Số file descriptors có thể bao gồm socket, pipe, regular file và các handle khác, không chỉ temporary files của bài lab. Vì vậy phải xem **xu hướng có baseline ổn định** và kiểm tra resource cụ thể thay vì assert số FD toàn JVM luôn đúng từng đơn vị.

Trên Windows có thể dùng Resource Monitor, Process Explorer hoặc công cụ tương đương để theo dõi handles/threads trong process.

### 14.1. UnixOperatingSystemMXBean

Một số JVM trên nền Unix có MBean mở rộng với `getOpenFileDescriptorCount()`:

```java
OperatingSystemMXBean os =
        ManagementFactory.getOperatingSystemMXBean();

if (os instanceof UnixOperatingSystemMXBean unix) {
    System.out.println("openFd="
            + unix.getOpenFileDescriptorCount());
}
```

Đây là snippet cho các runtime có interface `com.sun.management.UnixOperatingSystemMXBean` và `java.lang.management.ManagementFactory`; **không chạy tương đương trên mọi OS/JVM**. Tính khả dụng phải kiểm tra ở runtime, không dùng interface này như API portable bắt buộc.

Nếu số FD sau mỗi vòng tăng đều, đó là **tín hiệu điều tra**. Nếu chỉ tăng vài lần đầu rồi ổn định, có thể là warm-up/cache hợp lệ. Tìm handles cụ thể bằng tools của OS trước khi khẳng định leak.

## 15. Heap và GC: đo đúng để không báo động giả

Nhiều người thử:

```java
long before = Runtime.getRuntime().totalMemory()
        - Runtime.getRuntime().freeMemory();
```

sau đó mở/đóng context và assert số memory **phải trở lại chính xác before**. Đây là một phép thử **không vững**.

Lý do:

- JVM mở rộng heap đã commit rồi có thể giữ lại.
- GC không có nghĩa xảy ra đúng thời điểm bạn đọc `freeMemory()`.
- JIT, reflection, class metadata và caches có thể warm up dần.
- Logging, metrics và driver có caches hợp lệ.
- Heap object có thể còn tồn tại nhưng không liên quan resource leak.
- Native memory, file handles và DB connections không được phản ánh đầy đủ trong heap used.

### 15.1. System.gc() không phải điều kiện chứng minh

`System.gc()` là đề nghị JVM thực hiện GC, không phải hợp đồng buộc JVM thu gom mọi object ngay lập tức. Gọi nó nhiều lần trong test có thể làm thời gian chạy chậm, phụ thuộc GC options và gây false negative/positive.

Không viết acceptance test theo quy tắc:

```text
System.gc()
assert(heapUsed == exactBaseline)
```

Thay vào đó:

1. Đo counters/lifecycle contracts trực tiếp.
2. Chạy nhiều vòng để tìm xu hướng.
3. Dùng JFR/heap dump khi có dấu hiệu tăng trưởng kéo dài.
4. Tìm **retaining path** của objects/classloaders không cần tồn tại.
5. Đánh giá memory plateau theo workload và môi trường thật, không yêu cầu một số byte tuyệt đối.

### 15.2. WeakReference không phải assertion tuyệt đối

Một phép đo nâng cao là giữ `WeakReference<ApplicationContext>` sau khi context đóng và bỏ strong references. Nhưng `weakRef.get() != null` ngay sau `close()` không chứng minh leak: GC có thể chưa chạy. Ngược lại, một lần `weakRef.get()==null` không chứng minh mọi native resource đều đã đóng.

Nếu dùng weak references để chẩn đoán:

- Không lưu context trong static collection của test.
- Không để lambda/ThreadLocal giữ context vô tình.
- Dùng thời gian chờ hữu hạn và nhiều quan sát.
- Coi kết quả là tín hiệu điều tra, không phải bằng chứng duy nhất.

## 16. HikariCP, JDBC và kết nối database

Trong project thật, resource dễ leak nhất có thể là database connection pool.

Khi Spring Boot tạo một `HikariDataSource` và bean được quản lý đúng cách, destroy callback sẽ đóng pool theo lifecycle tương ứng. Nhưng bạn vẫn có thể tạo một pool ngoài Spring:

```java
HikariDataSource ds = new HikariDataSource();
ds.setJdbcUrl("jdbc:example:...");
ds.setMaximumPoolSize(10);
// Quên ds.close() sau khi không còn dùng.
```

Đây là **snippet minh họa**, không phải cấu hình JDBC chạy được: URL cố ý là placeholder logic để tránh kết nối thật, cần dependency HikariCP và credentials/driver hợp lệ.

Khi test lặp context với DB thực hoặc Testcontainers:

- Phân biệt **DataSource bean của từng context** với một DataSource external/static.
- Kiểm tra `HikariPoolMXBean.getActiveConnections()` và `getIdleConnections()` nếu dùng Hikari.
- Đóng cả connection/statement/result set theo từng lời gọi và **đóng pool** khi context bị hủy.
- Theo dõi số physical connections từ phía database.
- Test cleanup trong đường startup failure nếu connection pool đã tạo rồi bean sau đó lỗi.
- Không kết luận `activeConnections == 0` là pool đã đóng; pool có thể vẫn giữ **idle connections** và worker housekeeping.
- Không chỉ kiểm tra DB process: server-side session có timeout; client-side leak vẫn cần kiểm tra.

### 16.1. Vì sao không thêm DB thật vào demo cơ sở?

Một DB thật tạo thêm nguyên nhân fail: network, credentials, container availability, migrations, transaction timeouts và driver behavior. Bài lab dùng worker/file trước để chứng minh cơ chế close của Spring một cách lặp lại được; sau đó mới gắn database metrics khi cần.

## 17. @Async, scheduler và task còn chạy sau context close

Các tác vụ chạy nền có thể làm test leak sai nếu chỉ đóng bean mà không chờ tasks hoàn tất.

Ví dụ:

```java
@Component
class PollingService {

    private final ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();

    @PostConstruct
    void start() {
        scheduler.scheduleAtFixedRate(
                this::poll, 0, 1, TimeUnit.SECONDS);
    }

    @PreDestroy
    void stop() {
        scheduler.shutdownNow();
    }

    void poll() {
        // Công việc nghiệp vụ.
    }
}
```

Đây là **snippet minh họa**, cần imports `Component`, `PostConstruct`, `PreDestroy`, `ScheduledExecutorService`, `Executors` và `TimeUnit`.

Vấn đề ở đây:

- `shutdownNow()` gửi yêu cầu dừng nhưng **không chắc task đã kết thúc**.
- `poll()` có thể gọi I/O không có timeout và không phản ứng interrupt.
- Nếu context đóng xong trong lúc task vẫn giữ DB/client, có thể có rò rỉ tạm thời hoặc lỗi sau shutdown.
- Nếu bean có `@Lazy` và không từng được tạo, `@PostConstruct`/`@PreDestroy` không được gọi vì không có instance.
- Nếu tác vụ được tạo **ngoài bean lifecycle**, callback có thể không có quyền kiểm soát nó.

Tốt hơn là quản lý scheduler dưới một owner rõ ràng, dừng nhận việc, dùng `awaitTermination` và deadline. Với thành phần cần phối hợp stop phase, `SmartLifecycle` phù hợp hơn một destructor gọi shutdown không chờ.

### 17.1. SmartLifecycle.stop(Runnable) có ý nghĩa riêng

Một `SmartLifecycle` component có thể triển khai `stop(Runnable callback)` để thông báo cho lifecycle processor **khi stop thực sự hoàn tất**. Đừng gọi callback ngay sau khi chỉ mới gửi yêu cầu dừng async.

Thứ tự phase có ích khi:

```text
Start:
    database/client service (phase thấp)
             ↓
    message consumer (phase cao)

Stop:
    message consumer (phase cao)
             ↓
    database/client service (phase thấp)
```

Nếu consumer cần DB để checkpoint lúc dừng, stop consumer trước rồi mới đóng DB là hợp lý. **Một test đếm threads thôi không chứng minh dependency order đúng.**

## 18. Event listeners, subscriptions và static registry

Một leak tinh vi là bean đăng ký listener vào một registry sống lâu hơn context nhưng không unregister:

```java
@Component
class Watcher {

    private final GlobalEventBus bus;
    private final EventListener listener;

    Watcher(GlobalEventBus bus) {
        this.bus = bus;
        this.listener = event -> handle(event);
        bus.register(listener);
    }

    @PreDestroy
    void close() {
        bus.unregister(listener);
    }

    private void handle(Event event) {
        // Xử lý event.
    }
}
```

Đây là **snippet khái niệm**: cần định nghĩa `GlobalEventBus`, `EventListener` và `Event` của thư viện cụ thể cùng imports phù hợp. Không nên coi nó là một file Java độc lập đã đủ dependencies.

Nếu `GlobalEventBus` là singleton/static nằm ngoài context, nó có thể giữ `Watcher` của context cũ qua nhiều vòng. Việc context đã đóng **không tự xóa registration trong một registry ngoài Spring**.

### 18.1. Cách test registry leak

Trước vòng: `bus.listenerCount() == baseline`.

Trong context: listener count tăng theo số registration.

Sau close: listener count phải trở lại baseline.

Chạy nhiều vòng và kiểm tra đúng listener đã unregister. Tránh test chỉ đo memory sau `System.gc()`, vì registry count trực tiếp phản ánh hợp đồng registration rõ ràng hơn.

### 18.2. ThreadLocal và MDC

Một `ThreadLocal` gắn vào thread pool sống lâu có thể giữ reference tới object từ context đã đóng. Với logging MDC, library thường cung cấp `clear()` hoặc phạm vi scoped context thích hợp.

Khi dùng custom executor:

- Dọn ThreadLocal trong `finally` của task.
- Đừng lưu `ApplicationContext` hoặc bean có vòng đời ngắn trong static ThreadLocal.
- Stop/close executor thuộc context.
- Không xem việc đổi context là tự reset dữ liệu của thread được tái sử dụng ở pool bên ngoài.

## 19. DevTools restart và classloader leak

Spring Boot DevTools thường dùng **base classloader** cho thư viện JAR và **restart classloader** cho application classes có thể thay đổi.

Khi có restart:

```text
Base loader còn sống
        |
        +-- Restart loader R1 → app context R1
        |                         |
        |                         +-- context close
        |
        +-- Restart loader R2 → app context R2
        |
        +-- R1 chỉ được GC khi hết strong references
```

Nếu một static cache trong base loader giữ `Class<?>` hoặc instance từ R1, hoặc một thread cũ giữ thread context classloader R1, **R1 có thể không được thu gom** dù context đã đóng.

Đây là tình huống khác với leak một file handle:

- File handle cần `close()`.
- Restart classloader cần **xóa các strong references tới classloader và class/object thuộc nó**.
- Một static reference từ base tới class/application object cũ có thể làm metaspace tăng qua nhiều lượt.
- Không thể sửa leak classloader chỉ bằng tăng heap hoặc gọi `System.gc()`.

### 19.1. Test context lặp có giống DevTools restart không?

**Không hoàn toàn.**

Khi loop `SpringApplicationBuilder` trong **cùng classloader**, bạn test lifecycle của nhiều contexts cùng JVM nhưng **không thay restart classloader** như DevTools.

Để test leak đặc trưng DevTools:

- Chạy app ở development mode với DevTools restart active.
- Thực hiện nhiều classpath changes hợp lệ.
- Quan sát retained `RestartClassLoader` instances bằng heap dump/JFR/profiler.
- Kiểm tra thread TCCL, static caches và registrations từ base loader.
- Đảm bảo các tài nguyên thuộc context được close trước mỗi restart.
- Nếu lỗi chỉ xuất hiện với DevTools, chạy đối chứng khi restart bị tắt hoàn toàn để thu hẹp nguyên nhân.

**Đừng quy mọi memory growth qua loop context cho “DevTools classloader leak”** nếu test của bạn chưa từng tạo restart classloader.

## 20. Đếm resource nhưng không làm test tự tạo leak

Một số anti-pattern trong test:

### 20.1. Giữ context trong static list

```java
static final List<ApplicationContext> CONTEXTS =
        new ArrayList<>();

// Mỗi vòng:
CONTEXTS.add(context);
```

Đây là snippet cần imports và biến `context`; nó cố tình minh họa một **anti-pattern**.

Ngay cả khi `context.close()` được gọi, static list vẫn giữ reference đến context/bean metadata. Nó có thể làm kết quả GC test sai. Nếu cần thống kê, lưu metrics đơn giản (số/count/chuỗi nhỏ) hoặc weak references để quan sát, không giữ toàn bộ context.

### 20.2. Một @SpringBootTest context cache chung

Chạy 50 test methods nhưng chỉ có một context load không chứng minh resource được close 50 lần. Cần kiểm soát vòng đời đúng mục tiêu.

### 20.3. Không bao giờ gọi getBean

Nếu một bean đánh dấu `@Lazy` và bạn không bao giờ yêu cầu nó, constructor có thể không chạy, nên `opened=closed=0`. Kết quả đó **không chứng minh cleanup của bean đúng**.

Trong demo, code cố ý gọi `getBean` rồi `executeProbe()` / `writeOneByte()` để resource thật sự được tạo và sử dụng.

### 20.4. Test resource active bị reset bằng tay

```java
TrackedWorker.ACTIVE.set(0);
```

Đây là **phản ví dụ**, không biên dịch với field private của demo. Việc reset counter chỉ che sai lệch, không đóng executor. Không bao giờ dùng cách này để biến failure thành PASS.

### 20.5. Kiểm tra quá sớm

Một executor shutdown bất đồng bộ có thể cần thời gian. Đừng assert thread count ngay ở nanos sau khi gửi `shutdown()` rồi báo leak, nếu component có hợp đồng stop async chưa hoàn tất.

Hãy dùng `awaitTermination` hoặc callback completion **có deadline**. Ngược lại, cũng đừng đợi vô hạn đến khi test “tự pass” mà không có giới hạn.

## 21. Mở rộng cho Spring Boot ApplicationContextRunner

`ApplicationContextRunner` của Spring Boot giúp test một context nhỏ:

```java
new ApplicationContextRunner()
        .withUserConfiguration(SmallConfig.class)
        .run(context -> {
            assertThat(context).hasNotFailed();
            // Kiểm tra các bean trong context.
        });
```

Đây là **snippet** yêu cầu `SmallConfig` và AssertJ imports. Callback của `run` có thể thao tác trên context, sau đó runner đóng context theo vòng đời thích hợp.

Lợi ích:

- Không cần khởi chạy toàn bộ autoconfiguration.
- Tạo context mới cho mỗi lần `run`.
- Có thể assert context failed mà vẫn đọc startup failure.
- Dễ kiểm tra một `@Bean`/conditional bean và destructor.
- Tránh mở web server hoặc network port khi không cần.

Nhưng giới hạn:

- Không tự gọi `ApplicationRunner` / `CommandLineRunner` như `SpringApplication.run`.
- Không tự kiểm thử full Boot startup events hay mọi resource ngoài context.
- Không chứng minh JAR production đóng resource theo cùng cấu hình nếu runner chỉ đăng ký một tập bean khác.
- Không nên dùng nó để thay thế mọi integration test của service thật.

### 21.1. Khi nào chọn harness nào?

| Mục tiêu | Nên ưu tiên |
| --- | --- |
| Test một resource bean và destroy method | `ApplicationContextRunner` |
| Test nhiều vòng Boot startup thật (non-web) | `SpringApplicationBuilder` |
| Test graceful shutdown web server | Process-level/service integration có HTTP |
| Test database connection pool | Integration với DB/Testcontainers và pool metrics |
| Test DevTools classloader leak | DevTools restart repeated, heap analysis |
| Test port/socket cleanup | Chạy server/socket thật, đo bound ports |
| Test logic xử lý tài nguyên thuần Java | Unit test `AutoCloseable` không cần Spring |
| Test shutdown dưới tải nhiều request | Load/integration test với in-flight operations |

## 22. Quy trình kiểm tra rò rỉ thực tế theo bốn tầng

### Tầng A — Invariant logic

Theo dõi:

```text
Resource OPENED
Resource CLOSED
Resource ACTIVE
```

Kiểm tra after-close == baseline và opened delta == closed delta.

### Tầng B — Lifecycle hooks

Ghi marker có kiểm soát cho:

```text
context.refresh.complete
resource.constructed
resource.used
context.closed.event
resource.stop
resource.destroy
context.close.return
```

Đây là **tên marker minh họa**, không phải tên sự kiện chuẩn buộc Spring Boot in ra.

Phân biệt `ContextClosedEvent` với hủy bean: event được phát khi bắt đầu đường đóng context; không khẳng định mọi destructor đã chạy ngay tại mốc event.

### Tầng C — JVM và OS metrics

Quan sát:

- Live platform threads phù hợp.
- Executor termination.
- Open file descriptors/handles.
- Pool connections và socket states.
- Heap used sau ổn định, GC pattern, metaspace.
- Active scheduled tasks/subscriptions.
- Retained references khi heap dump.

### Tầng D — Soak/repeated-run

Lặp 20, 50, 100 vòng trong cùng JVM. Đánh giá:

- Có vòng nào không trở lại baseline?
- Số active có tăng 1 mỗi vòng không?
- Resource đóng chậm có tích tụ backlog không?
- Có tăng trưởng liên tục **sau warm-up** không?
- Có đường lỗi nào để lại resource?
- Phép đo có nhiễu vì các test chạy song song không?

**Không bắt buộc mọi chỉ số hệ thống trở về đúng một con số byte hoặc thread tuyệt đối sau mỗi vòng**; điều bắt buộc là lifecycle contract của tài nguyên do bài test sở hữu.

## 23. Tình huống trước–sau

### 23.1. Sai: resource ở singleton ngoài Spring

```java
public final class UnsafeResourceHolder {

    private static final ExecutorService EXECUTOR =
            Executors.newSingleThreadExecutor();

    public static void submit(Runnable task) {
        EXECUTOR.execute(task);
    }
}
```

Đây là class snippet cần imports `ExecutorService` và `Executors`. `EXECUTOR` là static, sống theo classloader, không theo mỗi `ApplicationContext`. Đóng context **không tự shutdown** một executor chưa đăng ký lifecycle callback.

Nếu nhiều contexts lần lượt tạo task từ static executor, resource có thể tiếp tục tồn tại giữa các context. Với một static singleton executor, số thread có thể **không tăng theo từng vòng**, nhưng đó vẫn là một **sai khác về ownership/lifecycle** nếu lẽ ra executor phải đóng khi context đóng.

### 23.2. Đúng: Spring sở hữu bean resource

```java
@Bean(destroyMethod = "close")
TrackedWorker trackedWorker() {
    return new TrackedWorker();
}
```

Khi bean singleton được tạo thành công, Spring có destructor rõ để gọi lúc context đóng. Đây chính là mô hình của demo.

### 23.3. Đúng: local resource có try-with-resources

```java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
```

Đây là snippet, cần `path`, `process` và imports `InputStream`/`Files`; nó biểu diễn resource thuộc một method, **không thuộc Spring context**. Java bảo đảm gọi `close()` khi rời scope nếu resource được khởi tạo thành công.

### 23.4. Sai: destructor chỉ ghi log

```java
@PreDestroy
void onDestroy() {
    log.info("Closing resource");
    // Không thực sự đóng executor, socket hoặc file.
}
```

Đây là snippet phản ví dụ. Việc log “Closing” không chứng minh resource đã được release. Test cần đo trạng thái resource thật.

### 23.5. Sai: gọi System.exit giữa vòng kiểm thử

Nếu `System.exit(...)` kết thúc JVM, cả vòng lặp sẽ dừng và OS có thể thu hồi nhiều tài nguyên. Điều đó **không kiểm tra Spring đã destroy chúng đúng hay chưa**. Đừng gọi exit trong test kiểm tra nhiều context; chỉ dùng process-level test riêng để kiểm tra mã thoát.

## 24. Chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng | Kiểm tra/hướng xử lý |
| --- | --- | --- |
| Worker active tăng thêm 1 sau mỗi close | Executor không có destructor hoặc close thất bại | Kiểm tra `@Bean(destroyMethod)`, shutdown/awaitTermination |
| Test pass khi không có bean được tạo | Bean lazy chưa được truy cập | Yêu cầu bean và sử dụng resource trong context |
| File handle tăng nhưng opened/closed bằng nhau | Tracker bỏ sót file khác hoặc close giả | Đo OS FDs, tìm các file channels/streams khác |
| Opened tăng, closed không tăng | Missing destroy callback | Kiểm tra ownership, scope và callback |
| Thread vẫn sống ngay sau close | Stop async hoặc task không phản ứng interrupt | Bounded wait, task cancellation, thread dump |
| Heap tăng vài vòng đầu rồi ổn định | Warm-up/cache/JIT | So sau plateau, không assert exact heap |
| Metaspace tăng ở mỗi DevTools restart | R1 classloaders có thể bị giữ | Heap dump, static caches, TCCL |
| Test gián đoạn do port in use | Web server đang bind port | Dùng non-web context hoặc dynamic port trong integration |
| Hikari active=0 nhưng connections vẫn mở | Pool chưa đóng, còn idle connections | Theo dõi pool lifecycle và server sessions |
| Resource close 2 lần | Hai owner cùng đóng hoặc callback trùng | Idempotent close, xác định owner duy nhất |
| `@PreDestroy` không chạy khi startup fail rất sớm | Bean chưa được tạo hoàn chỉnh | Cleanup ngay nơi allocation |
| `close()` ném exception nhưng context trả về | Framework có thể log cleanup error | Assert resource counters và error metrics |
| Test chạy solo pass, cả suite fail | Shared static state/parallel tests/context cache | Cô lập metrics, điều phối test execution |
| Context đã đóng nhưng listener vẫn nhận event | Registry nằm ngoài context | Unregister trong destroy callback |
| JVM không thoát | Non-daemon thread ngoài lifecycle | Thread dump, truy tìm executor owner |
| JVM thoát nhưng resource vẫn leak lúc chạy | OS thu hồi khi process exit | Test nhiều context trong cùng process |
| `System.gc()` không làm heap giảm | JVM/GC semantics, strong references | Heap dump retaining paths |
| File temp vẫn tồn tại | Không delete, lỗi OS hoặc policy retention | Đóng channel, xóa file, xử lý suppressed errors |
| Tăng số vòng không tái hiện leak | Leak chỉ xảy ra ở error path hoặc dưới tải | Thêm failure/async/soak scenarios |

### Quy trình debug ưu tiên

1. Xác định resource type, owner và trạng thái sau close.
2. Thử 3 vòng trước, in counters sau mỗi vòng.
3. Kiểm tra bean có được tạo/sử dụng thật không.
4. Kiểm tra `@Bean`, `@PreDestroy`, `DisposableBean` hoặc `SmartLifecycle`.
5. Xác định destructor đã **hoàn tất dọn** hay chỉ ghi log/gửi tín hiệu.
6. Chạy negative control có cleanup `finally` để chứng minh test phát hiện leak.
7. Thêm failure-path test trước khi tin vào production safety.
8. Nếu counters pass nhưng OS resource tăng, kiểm tra resource không được tracker theo dõi.
9. Nếu heap/metaspace tăng, dùng JFR/heap dump để tìm retaining paths.
10. Chạy lại nhiều vòng trong cùng JVM với cấu hình gần môi trường thật.
11. Ghi nguyên nhân và sửa tại **chủ sở hữu tài nguyên**, không reset bộ đếm.
12. Giữ test tự dọn được tài nguyên ngay cả khi assertion fail.

## 25. Test đo lường không được gây hại cho môi trường

Một bài leak test có thể tiêu tốn file handles, ports hoặc threads khi cố tình tạo lỗi. Vì thế:

- Chạy trên môi trường development/CI cô lập, không trên process phục vụ người dùng.
- Bắt đầu với số vòng nhỏ.
- Đặt thời gian chờ hữu hạn.
- Không dùng một leak cố ý không cleanup để “quan sát lâu hơn”.
- Với negative control, giữ resource reference và đóng trong `finally`.
- Dùng temporary file và xóa khi xong; không mở file dữ liệu thật.
- Không log token, password, JDBC URL có credentials hoặc dữ liệu nhạy cảm.
- Không đo quyền truy cập OS bằng thao tác destructive ngoài thư mục test.
- Với child processes, dùng timeout và dọn process tree.
- Với cloud resources, dùng naming/TTL và policy cleanup riêng.

Trong demo, worker threads là daemon để giảm nguy cơ JVM test bị giữ không thoát, nhưng test vẫn **bắt buộc xác nhận shutdown**. Không đổi “daemon thread” thành cách hợp thức hóa leak.

## 26. Bài tập mở rộng

### Bài 1: tạo leak bằng destroyMethod rỗng

Dựa trên test `MissingDestroyConfiguration`. Tại sao `@Bean(destroyMethod = "")` dẫn tới `activeBefore+1` sau context close?

**Đáp án:** cơ chế suy luận custom destroy method `close` bị tắt, nên bean kiểu `TrackedWorker` không có callback tự đóng theo đường đó. Test dùng `finally` gọi close để không gây leak thật.

### Bài 2: số lượt mở/đóng

Đổi `rounds` thành 20. Dự đoán dòng kết thúc.

**Đáp án** (nếu chạy một process mới không có can thiệp):

```text
PASS openedWorkers=20 closedWorkers=20 openedFiles=20 closedFiles=20
```

Lưu ý nếu `main` được gọi nhiều lần trong **cùng JVM** mà static counters giữ số của lần trước, assertion tổng bằng `rounds` cần chuyển sang kiểm tra **delta từ baseline**, như JUnit test đã làm.

### Bài 3: tăng số bean trong context

Thêm một bean `TrackedWorker` thứ hai với tên khác, rồi xem điều gì xảy ra với assertion `worker.active==1`.

**Đáp án:** nếu cả hai được tạo, số active có thể là 2. Test phải cập nhật acceptance criteria theo số resource thực tế, **không ép counter về 1** trong khi thiết kế đã có hai resource.

### Bài 4: resource lazy

Đánh dấu `@Bean @Lazy` cho temporary file, không gọi `context.getBean(TrackedTempFile.class)`. Tại sao counter file có thể bằng 0 dù context active?

**Đáp án:** bean chưa được tạo vì lazy; phép đo cleanup thiếu ý nghĩa cho resource không tồn tại. Hãy có test riêng buộc tạo rồi close nếu cần kiểm tra destructor.

### Bài 5: startup failure sau resource

Dùng `FailingConfiguration` test. Nếu `failingBean` bỏ tham số `TrackedWorker resource`, điều gì có thể thay đổi?

**Đáp án:** nếu bean khác không ép resource được tạo trước, việc tạo resource có thể vẫn xảy ra theo pre-instantiation order nhưng **không nên dựa vào thứ tự ấy**. Tham số dependency giúp xác định resource được tạo trước khi failure diễn ra.

### Bài 6: file close bị lỗi

Giả lập `TrackedTempFile.close()` gặp IOException. Test nên assert gì?

**Đáp án:** không được báo cleanup thành công. Cần giữ lỗi dọn dẹp, kiểm tra file handle/path thực tế và có cơ chế retry/recovery thích hợp. Counter không nên giảm chỉ để làm test pass.

### Bài 7: System.gc và heap

Sau 50 vòng, `totalMemory()` cao hơn ban đầu nhưng `active=0` cho mọi resource. Đó có chắc là leak?

**Đáp án:** không. Cần xem retained objects, heap used sau GC phù hợp, plateau, OS handles và classloader references.

### Bài 8: HikariCP

Thay temporary file bean bằng `HikariDataSource` trên DB thử nghiệm. Viết test so sánh active/idle/pending connections và số pool thực sự đã đóng. **Không chỉ kiểm tra active connections = 0**.

### Bài 9: DevTools và static registry

Tạo một listener ở restart loader, đăng ký vào registry static trong base loader và quên unregister. Sau nhiều lần DevTools restart, bằng cách nào xác định R1 vẫn bị giữ?

**Đáp án:** dùng heap dump/retaining path và kiểm tra static registry/thread TCCL; `context.close()` một mình không gỡ một static reference ngoài context.

### Bài 10: test ngừng task bất đồng bộ

Tạo một scheduled task chờ latch. Khi context close, stop callback phải đợi task dừng hoặc timeout. Viết test bằng `CountDownLatch`/`awaitTermination` có deadline; không dùng `Thread.sleep` không kiểm soát.

## 27. Checklist trước khi kết luận “không leak”

- [ ] Tạo context mới ở **mỗi vòng trong cùng JVM**.
- [ ] `ConfigurableApplicationContext.close()` được gọi trong `try-with-resources`/`finally`.
- [ ] Mỗi resource có owner rõ ràng.
- [ ] Mọi bean resource singleton có destructor phù hợp.
- [ ] Không vô tình đặt `destroyMethod = ""` cho bean chỉ dựa vào `close`.
- [ ] Bean cần test đã thực sự được tạo và sử dụng.
- [ ] Counters đo active/opened/closed tại baseline/inside/after-close.
- [ ] Sau mỗi vòng active trở lại baseline.
- [ ] Tổng opened delta bằng closed delta.
- [ ] Executor có bounded shutdown và báo lỗi khi chưa terminate.
- [ ] FileChannel/stream/socket được đóng thật, không chỉ log.
- [ ] Temporary files của test được xóa theo policy.
- [ ] Có negative control để chứng minh test có khả năng phát hiện thiếu cleanup.
- [ ] Negative control tự dọn trong `finally`.
- [ ] Có test refresh failure sau khi resource đã được tạo.
- [ ] Không trông chờ destructor của bean bị lỗi trước khi tạo xong.
- [ ] Các test dùng static state không chạy song song thiếu kiểm soát.
- [ ] Không nhầm context cache của `@SpringBootTest` với nhiều context mới.
- [ ] Không dùng `System.gc()` hoặc exact heap bytes làm assertion duy nhất.
- [ ] Nếu có DB, kiểm tra cả pool shutdown/idle connections.
- [ ] Nếu có threads, kiểm tra termination thay vì chỉ đếm thread names.
- [ ] Nếu có external listeners, kiểm tra unregister sau close.
- [ ] Nếu dùng DevTools, có test restart classloader riêng.
- [ ] Có giới hạn thời gian và tài nguyên cho soak test.
- [ ] Không để lại resource thật bị leak khi kết thúc test.
- [ ] Có chẩn đoán riêng cho những chỉ số OS/JVM tăng sau warm-up.
- [ ] Có test tại đường lỗi, không chỉ startup/close thành công.

## 28. Tóm tắt

- **Đóng context không đồng nghĩa mọi tài nguyên trong JVM tự được dọn.** Spring quản lý các bean/instance thuộc lifecycle của nó; resource ngoài container, trong static caches, prototype hoặc cấp phát lỗi trước khi bean return cần ownership/cleanup riêng.
- **Muốn kiểm tra leak qua nhiều context, phải mở/đóng lặp trong cùng JVM.** Chạy lại process mới không kiểm tra được những reference/tài nguyên còn sống qua các lần context close.
- **Đo có hệ thống:** baseline → bên trong context → sau `close()`. Kiểm tra active trở về baseline và opened/closed cân bằng.
- **Thực hành với `TrackedWorker` và `TrackedTempFile`** giúp kiểm tra cả một executor có thread riêng và một file handle. Các bean đăng ký `@Bean(destroyMethod="close")` và được thử bằng vòng lặp cùng JUnit.
- **Negative control quan trọng:** cố tình tắt destroy-method inference trong một test cô lập, xác nhận phát hiện leak, rồi tự cleanup trong `finally`.
- **Kiểm tra cả startup failure:** singleton đã hoàn tất tạo có cơ chế destruction; resource mở dở trong constructor/factory cần rollback tại chính nơi cấp phát.
- **Phân biệt leak thật với JVM warm-up:** counters, OS metrics và retaining paths có giá trị hơn một heap snapshot hay `System.gc()`.
- **Mở rộng sang production:** HikariCP, HTTP clients, schedulers, listeners, TCCL, static caches, DevTools restart và shutdown timeouts cần những phép đo riêng.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, context caching và testing infrastructure.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): `ApplicationContextRunner` và thử context.
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): startup, shutdown và lifecycle.
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean` và destroy-method inference.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): `@Bean(destroyMethod)`, `close`/`shutdown`.
- [Spring Framework 6.1 — ConfigurableApplicationContext API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): `close()`, `stop()`.
- [Java 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown và awaitTermination.
- [Java 17 — AutoCloseable API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): resource cleanup contract.
- [Java 17 — FileChannel API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): file channel lifecycle.
- [Java 17 — ManagementFactory / ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html): thread/OS metrics.
