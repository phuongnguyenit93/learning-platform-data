# Cô lập context, luồng và hook để các lần kiểm thử không ảnh hưởng nhau

Một test Spring Boot có thể **PASS khi chạy riêng** nhưng **FAIL khi chạy toàn bộ suite**, hoặc khiến `gradle test` treo sau khi mọi assertion đã hoàn thành. Nguyên nhân thường nằm ở vòng đời tài nguyên chứ không phải logic nghiệp vụ: `ApplicationContext` được Spring TestContext cache và tái sử dụng; executor/thread vẫn hoạt động; `Runtime.addShutdownHook` để lại callback cho cuối JVM; `ThreadLocal`, static state hoặc system properties tồn tại qua nhiều test; file, port và dữ liệu test bên ngoài JVM vẫn chưa được dọn.

Bài Knowledge thuộc module **Spring Boot Application Runtime**, mục cha **Kiểm thử vòng đời**, đề mục **“Cô lập context, luồng và hook để các lần kiểm thử không ảnh hưởng nhau”**. Ví dụ áp dụng cho **Spring Boot 3.3.x, Spring Framework 6.1, Java 17+ và JUnit 5**. Trọng tâm là **quyền sở hữu tài nguyên, thời điểm dọn và phép kiểm chứng**, không phải vô hiệu hóa context cache toàn bộ hoặc chạy mỗi test trong JVM riêng khi không cần thiết.

Sau bài học, bạn cần:

- Phân biệt **Spring context**, **JVM/process** và **tài nguyên ngoài JVM**; mỗi phạm vi cần cleanup khác nhau.
- Hiểu vì sao `@SpringBootTest` có thể chia sẻ context giữa nhiều test và khi nào cần `@DirtiesContext`.
- Dùng `ApplicationContextRunner` hoặc `try-with-resources` để tạo context được đóng ngay sau mỗi lượt thử.
- Thiết kế bean quản lý worker với destroy method, interrupt và `awaitTermination` hữu hạn.
- Tránh kiểm thử `System.exit` hoặc JVM hook ngay trong tiến trình JUnit; sử dụng subprocess có timeout.
- Khôi phục system properties, static caches và `ThreadLocal`, cô lập port/file/DB/queue.
- Chạy test theo nhiều thứ tự và trên CI để xác nhận không gây nhiễu giữa các lượt.

## 1. Ba phạm vi tài nguyên không đồng nghĩa nhau

| Phạm vi | Ví dụ | Cơ chế dọn chủ yếu |
| --- | --- | --- |
| **Spring ApplicationContext** | Singleton beans, `@PreDestroy`, `SmartLifecycle`, bean-managed scheduler/executor | `context.close()`, `@DirtiesContext`, Spring TestContext hoặc context runner |
| **JVM/process** | `Runtime.addShutdownHook`, `System.setProperty`, static mutable state, unmanaged thread | Hoàn nguyên trong test/`finally` hoặc kết thúc JVM có kiểm soát |
| **Ngoài JVM** | Database, Testcontainers, temp file, port, message broker, mock server | Test fixture, unique namespace, transaction/cleanup và process management |

Không được dùng các phương trình sai sau:

~~~text
context.close()  !=  JVM shutdown
@DirtiesContext  !=  reset mọi static Java field
@PreDestroy      !=  tự đóng mọi ExecutorService bên ngoài Spring
System.exit(0)   !=  chỉ dừng một test method
Thread.interrupt !=  chắc chắn worker đã kết thúc
~~~

**Nguyên tắc:** một đối tượng phải có **owner** rõ. Nếu Spring bean tạo executor, lifecycle bean chịu trách nhiệm đóng nó. Nếu test tự tạo executor, test phải đóng. Nếu test đăng ký JVM hook, test phải gỡ hook trước khi kết thúc hoặc cô lập toàn bộ thử nghiệm trong JVM con.

### Một timeline gây nhiễu thường gặp

~~~text
JUnit worker JVM bắt đầu
  |
  +-- Test A tạo context A
  |      +-- Bean Counter state = 1
  |      +-- Thread pool không shutdown
  |      +-- Hook A đăng ký ở Runtime
  |
  +-- Test A PASS
  |
  +-- Test B dùng lại context A từ cache
  |      +-- Counter vẫn = 1 -> Test B FAIL
  |
  +-- Test C start server trên cổng bị thread cũ giữ -> FAIL
  |
  +-- Cuối suite: JVM shutdown -> Hook A mới chạy
         +-- Hook tham chiếu file/bean đã hết vòng đời -> lỗi hoặc treo
~~~

Có thể chữa từng nguyên nhân bằng việc **chặn trạng thái chia sẻ** chứ không cần thêm timeout hoặc sleep ngẫu nhiên.

## 2. Spring TestContext cache: vì sao hai test có thể dùng cùng context?

Spring Framework TestContext giữ `ApplicationContext` đã được tạo trong một **cache tĩnh trong JVM test worker**. Một test mới với **cùng context configuration key** có thể nhận lại context cũ để tiết kiệm chi phí component scan, auto-configuration và khởi tạo singleton.

Cache key có thể xét các yếu tố như cấu hình classes/locations, context initializers/customizers, profile, property sources, context hierarchy, mock/bean overrides và các tùy biến khác. Vì vậy:

- Không phải mọi test gắn `@SpringBootTest` đều dùng cùng context.
- Không phải mỗi class JUnit là một context mới.
- Các test có cấu hình tương đương có thể nhận **cùng singleton beans**, kể cả khác class.
- Test thường chỉ kết thúc **method**, còn context có thể tiếp tục nằm trong cache.
- Context có thể bị đóng khi đánh dấu dirty, khi cache eviction hoặc khi JVM test suite dừng.

Cache có lợi. Vấn đề là **state bẩn mà test không hoàn nguyên**, ví dụ:

~~~java
@Service
class MutableCounter {
    private int count;

    int increment() {
        return ++count;
    }

    int current() {
        return count;
    }
}
~~~

Đây là class minh họa, cần import `@Service`. Nếu hai test dùng cùng singleton và test trước tăng `count`, test sau không thể chắc chắn giá trị ban đầu bằng `0`. Hướng xử lý có thể là biến state thành immutable, reset trạng thái có kiểm soát hoặc đánh dấu context dirty.

### Cache không phải một JVM độc lập

Nếu build tool chạy mỗi nhóm test trong một JVM khác nhau, cache không chia sẻ qua hai tiến trình. Nhưng **database, file, network port, queue** vẫn có thể bị chia sẻ giữa các JVM. Cô lập TestContext cache chỉ giải quyết **một** phạm vi.

Để điều tra, bật log cache trong cấu hình test:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Mục đích là xem cache hit/miss và hoạt động đóng context; đừng dùng số cache hit như bằng chứng mọi thread hay external state đã được dọn.

## 3. `@DirtiesContext`: đóng context đúng thời điểm

`org.springframework.test.annotation.DirtiesContext` bảo Spring TestContext coi context là đã bị thay đổi, **loại khỏi cache và đóng** ở mốc được chỉ định.

Các chế độ:

| Cách dùng | Thời điểm |
| --- | --- |
| `@DirtiesContext` trên method | Sau method, mặc định `AFTER_METHOD` |
| `methodMode = BEFORE_METHOD` | Trước method |
| `classMode = BEFORE_CLASS` | Trước toàn bộ class |
| `classMode = AFTER_CLASS` | Sau toàn bộ class, mặc định ở class |
| `classMode = BEFORE_EACH_TEST_METHOD` | Trước mỗi method |
| `classMode = AFTER_EACH_TEST_METHOD` | Sau mỗi method |

Ví dụ:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class TestThatMutatesSingletonState {
    // ... @Test methods ...
}
~~~

Đây là fragment, cần import `@SpringBootTest`/`@DirtiesContext` và test methods. Nó bảo vệ việc **không tái sử dụng context bị bẩn sau class**. Nhưng không mặc nhiên đảm bảo context là **mới ngay trước class**, vì context cùng key có thể được cache từ test trước.

Nếu thật sự yêu cầu một context mới lúc bắt đầu:

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_CLASS)
~~~

Để đóng sau một test cụ thể:

~~~java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void mutatingTest() {
    // ...
}
~~~

**Không gắn `@DirtiesContext` bừa bãi** lên toàn suite. Nó khiến những context vốn có thể reuse an toàn phải bị tạo lại, làm test chậm và che được một số lỗi thiết kế shared state thay vì giải quyết.

### Khi nào nên dùng?

- Test thay đổi cấu hình hoặc state singleton mà khó hoàn nguyên an toàn.
- Test cố ý đo vòng đời bắt đầu/dừng của context do TestContext quản lý.
- Test JMX, stateful infrastructure hoặc context configuration bị mutate sau khởi tạo.
- Test yêu cầu cô lập context trước/sau một tình huống cụ thể.

### Khi nào không đủ?

- Test dùng `System.setProperty` rồi quên restore.
- Test tạo `new Thread`/`Executors` bên ngoài bean.
- Test đăng ký `Runtime.addShutdownHook`.
- Test tạo file, database record, broker message, local port ngoài context.
- Test dùng `ThreadLocal` trên executor worker và không clear.

**`@DirtiesContext` chỉ kiểm soát Spring context**, không reset cả JVM.

## 4. `@SpringBootTest`: context do TestContext sở hữu

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class MyIntegrationTest {
    // @Autowired beans ...
}
~~~

Spring test framework quyết định khi nào load, cache và đóng context. **Đừng gọi `context.close()` tùy tiện** lên một `@Autowired ConfigurableApplicationContext` từ `@SpringBootTest`: test tiếp theo có thể nhận reference tới context đã bị đóng nếu cache chưa được cập nhật đúng cách.

Nếu muốn thử đóng context theo ý mình, hãy dùng `ApplicationContextRunner` hoặc tự tạo `AnnotationConfigApplicationContext` trong `try-with-resources`. Nếu muốn báo framework rằng shared context không nên reuse, dùng `@DirtiesContext`.

Với web integration test:

| `webEnvironment` | Embedded web server thật? | Tình huống |
| --- | --- | --- |
| `MOCK` | Không | MVC/mock web test |
| `NONE` | Không | Bean/lifecycle test không cần HTTP |
| `RANDOM_PORT` | Có, cổng động | HTTP end-to-end, giảm port conflict |
| `DEFINED_PORT` | Có, cổng cố định/cấu hình | Chỉ dùng khi cần kiểm cổng cố định |

Khi chạy suite song song, `DEFINED_PORT` dễ đụng cổng của test khác, tiến trình local hoặc service đang chạy. Với test HTTP thật, ưu tiên `RANDOM_PORT` và đọc cổng được cấp thay vì hard-code `8080`.

### Rollback transaction không bảo đảm cô lập qua server thread

Test `@Transactional` có thể rollback transaction của test thread. Nhưng HTTP client và server khi dùng `RANDOM_PORT` chạy trên **những thread khác nhau**, transaction server có thể commit độc lập. Vì vậy, muốn dọn dữ liệu do request HTTP tạo ra cần một test fixture hoặc cleanup phù hợp, không chỉ trông vào rollback của JUnit caller.

## 5. Đóng context có dừng mọi thread không?

Trên đường đóng bình thường của `AbstractApplicationContext`, Spring thường:

~~~text
context.close()
  -> ContextClosedEvent
  -> LifecycleProcessor.onClose()
       -> Lifecycle/SmartLifecycle.stop(...)
  -> destroy singleton beans
       -> @PreDestroy
       -> DisposableBean.destroy()
       -> @Bean(destroyMethod=...)
  -> context inactive
~~~

Những bước này quản lý **beans và lifecycle contracts**. Nếu ứng dụng tạo `ExecutorService` trong một field ngoài Spring hoặc một task chạy trên thread không do bean quản lý, context không tự biết phải gọi shutdown cho resource đó.

Ví dụ bean:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService reportExecutor() {
    return Executors.newSingleThreadExecutor();
}
~~~

Đây là fragment trong class cấu hình, cần import `@Bean`, `ExecutorService` và `Executors`. Spring sẽ gọi `shutdown` khi hủy bean thích hợp, nhưng **`shutdown()` không đồng nghĩa tất cả task đã kết thúc**. Một test cần đảm bảo cleanup trước khi method kế tiếp chạy nên có bounded await và task hợp tác với cancellation.

Với `SmartLifecycle.stop(Runnable callback)`, callback phải được gọi **khi stop thực sự hoàn tất**. Quên callback có thể khiến lifecycle processor chờ timeout. Không nên đặt một vòng chờ vô hạn trong `@PreDestroy` hoặc stop callback.

## 6. Thread và executor: test cần kiểm dừng thật

Ví dụ sai (chỉ để đọc, **không chạy**):

~~~java
@Test
void badTest() {
    ExecutorService pool = Executors.newSingleThreadExecutor();
    pool.submit(() -> {
        while (true) {
            // Non-daemon worker chạy mãi, không có cancellation.
        }
    });
    // Test PASS nhưng pool còn sống.
}
~~~

Lỗi này có thể làm `gradle test` treo vì JVM còn non-daemon thread.

Mẫu đúng hơn khi test **sở hữu executor**:

~~~java
ExecutorService pool = Executors.newSingleThreadExecutor();
try {
    Future<String> result = pool.submit(() -> "OK");
    assertEquals("OK", result.get(2, TimeUnit.SECONDS));
} finally {
    pool.shutdownNow();
    assertTrue(pool.awaitTermination(2, TimeUnit.SECONDS));
}
~~~

Đây là fragment trong một method có `throws Exception` và import tương ứng. `shutdownNow()` chủ yếu gửi interrupt; **không bắt buộc một task bỏ qua interrupt phải dừng**. Hãy viết worker nhận cancel/interrupt, rồi assert termination.

### `CountDownLatch` tốt hơn `Thread.sleep` khi đồng bộ

Đừng giả định:

~~~java
worker.start();
Thread.sleep(100);
assertTrue(worker.isReady());
~~~

vì 100 ms có thể chưa đủ trên CI đang tải cao. Dùng `CountDownLatch.await(timeout)`, `Future.get(timeout)` hoặc một completion signal rõ. Timeout là hạn chót cho phép test fail, **không phải một mẹo làm thread chạy nhanh hơn**.

## 7. Hook là cấp JVM, không phải cấp context

~~~java
Thread hook = new Thread(
        () -> System.out.println("JVM shutting down"),
        "my-shutdown-hook");
Runtime.getRuntime().addShutdownHook(hook);
~~~

`Runtime.addShutdownHook` đăng ký một thread để JVM chạy khi shutdown bình thường. Những hooks có thể chạy **đồng thời và không bảo đảm thứ tự**. Một test kết thúc, context bị dirty hoặc `@PreDestroy` được gọi **không làm JVM shutdown hook tự chạy**.

Nếu test A đăng ký hook mà quên gỡ, hook có thể nằm im đến tận cuối suite, sau đó chạy và cố truy cập file đã xóa hoặc bean đã hủy.

Nếu một test bắt buộc tạo hook tạm thời:

~~~java
Runtime runtime = Runtime.getRuntime();
Thread hook = new Thread(() -> {
    // Đăng ký tạm để thử API.
}, "temporary-hook");

runtime.addShutdownHook(hook);
try {
    // Test registration; không gọi System.exit ở đây.
} finally {
    boolean removed = runtime.removeShutdownHook(hook);
    if (!removed) {
        throw new IllegalStateException("Hook registration missing");
    }
}
~~~

Đây là fragment. `removeShutdownHook` chỉ hợp lệ **trước khi JVM bắt đầu shutdown**. Gỡ hook không chạy callback. Không test logic callback bằng cách gọi `hook.run()` rồi kết luận shutdown lifecycle đã được thử thật: đó chỉ là lời gọi method trên caller thread.

### `System.exit` và `Runtime.halt`

- `System.exit(code)` yêu cầu **toàn JVM** shutdown và chạy các hooks bình thường.
- `Runtime.getRuntime().halt(code)` dừng JVM cưỡng bức, bỏ qua hook.
- Cả hai đều **không thích hợp gọi trực tiếp trong JUnit worker JVM** chỉ để kiểm thử một hook.

**Chạy subprocess có timeout** là cách cô lập đúng khi kiểm tra process-level shutdown.

## 8. Spring Boot hook và TestContext cache: hai cơ chế khác nhau

`SpringApplication` có `setRegisterShutdownHook(boolean)`, **mặc định `true`**. Ứng dụng Spring Boot chạy độc lập thường dựa vào hook để đóng context khi JVM shutdown bình thường.

Ngược lại, `@SpringBootTest` dùng Spring TestContext Framework để quản lý context test và cache. Context có thể được đóng do `@DirtiesContext`, cache eviction hoặc giai đoạn shutdown của test suite. **Không đồng nhất shutdown hook do SpringApplication đăng ký với vòng đời cache của TestContext**.

Bảng quyết định:

| Trường hợp | Owner | Nên dọn thế nào |
| --- | --- | --- |
| `@SpringBootTest` context | Spring TestContext | `@DirtiesContext` theo nhu cầu; không tự `close()` |
| `ApplicationContextRunner` context | Runner | Đóng sau callback |
| `new AnnotationConfigApplicationContext(...)` | Test caller | `try-with-resources` |
| `SpringApplication.run` trong app độc lập | App/Boot | `close()` rõ hoặc shutdown hook khi JVM thoát |
| `Runtime.addShutdownHook` do test đăng ký | JVM/test code | Gỡ trước khi test xong |
| Test `System.exit`/Boot shutdown hook | Subprocess | Đợi, đọc exit/marker, kill child khi timeout |

Chỉ tắt `SpringApplication.setRegisterShutdownHook(false)` trong một chương trình test tự sở hữu context khi có lý do và **bảo đảm đóng context bằng code khác**. Tắt hook không tự dừng thread đã leak, thậm chí có thể bỏ mất cơ chế cleanup lúc JVM shutdown.

## 9. Chọn mức cô lập phù hợp

| Kiểu test | Cô lập/lợi ích | Chi phí |
| --- | --- | --- |
| Unit test Java thuần | Không context, chỉ tạo object cần test | Thấp |
| `ApplicationContextRunner` | Context nhỏ, mới theo mỗi `run`, đóng sau callback | Thấp-vừa |
| `AnnotationConfigApplicationContext` tự quản lý | Điều khiển chính xác start/stop Framework context | Thấp-vừa |
| `@SpringBootTest` dùng cache | Gần ứng dụng Boot thật, reuse nhanh | Vừa-cao |
| `@SpringBootTest` + `@DirtiesContext` | Context bị loại khỏi cache/đóng | Cao hơn |
| JVM subprocess | Có JVM hook, `System.exit`, signal và process status thật | Cao nhất |

**Không chạy mọi unit test trong JVM riêng** nếu không có nhu cầu. Nhưng cũng không cố ép một thử nghiệm `System.exit` thành test in-process chỉ để giảm thời gian.

## 10. Dự án chạy được: Spring Boot 3.3 / Java 17 / Gradle

Ta xây dựng một ví dụ có cả ba phạm vi:

- `WorkerConfig` tạo bean `TrackedWorker` với destroy method.
- `TrackedWorker` sử dụng **non-daemon thread** và dừng bằng interrupt/await.
- `WorkerIsolationTest` dùng `ApplicationContextRunner`, xác minh context đóng và worker kết thúc qua từng lượt.
- `BootLifecycleTest` minh họa TestContext cache với before/after dirty mode.
- `HookChild` đăng ký JVM hook và gọi `System.exit(23)`, **nhưng chỉ trong child JVM**.
- `HookProcessTest` dùng `ProcessBuilder` xác minh exit code/marker, timeout và cleanup.

### 10.1. Cấu trúc

~~~text
lifecycle-isolation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/lifecycle/
    │   ├── LifecycleIsolationApplication.java
    │   ├── WorkerConfig.java
    │   ├── TrackedWorker.java
    │   └── HookChild.java
    └── test/java/com/example/lifecycle/
        ├── WorkerIsolationTest.java
        ├── BootLifecycleTest.java
        └── HookProcessTest.java
~~~

### 10.2. `settings.gradle`

~~~groovy
rootProject.name = 'lifecycle-isolation-demo'
~~~

### 10.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    // Dùng Gradle native BOM thay vì bỏ trống phiên bản dependency.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Với Spring Boot 3.3 và Java 17+, cần Gradle tương thích. Starter dependencies không tự có version nếu không dùng cơ chế dependency management; mẫu đã khai báo **BOM** cho cả implementation và testImplementation.

### 10.4. `LifecycleIsolationApplication.java`

~~~java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleIsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(LifecycleIsolationApplication.class, args);
    }
}
~~~

Lớp chính không tự gọi `System.exit`. Nó có thể dùng để chạy Spring Boot standalone; bean worker được scan từ `WorkerConfig` cùng package và sẽ do context quản lý.

### 10.5. `WorkerConfig.java`

~~~java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WorkerConfig {

    @Bean(destroyMethod = "close")
    TrackedWorker trackedWorker() {
        return new TrackedWorker();
    }
}
~~~

`@Bean(destroyMethod = "close")` gắn cleanup của `TrackedWorker` với vòng đời singleton bean. Khi test gọi `ApplicationContextRunner.run(...)` và callback kết thúc, context đóng và gọi `close()`.

### 10.6. `TrackedWorker.java`

~~~java
package com.example.lifecycle;

import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class TrackedWorker implements AutoCloseable {

    private final String id = UUID.randomUUID().toString();
    private final CountDownLatch started = new CountDownLatch(1);
    private final CountDownLatch finished = new CountDownLatch(1);
    private final AtomicBoolean closed = new AtomicBoolean();
    private final ExecutorService executor;

    public TrackedWorker() {
        executor = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "tracked-worker-" + id);
            thread.setDaemon(false);
            return thread;
        });

        executor.execute(() -> {
            started.countDown();
            try {
                while (!Thread.currentThread().isInterrupted()) {
                    Thread.sleep(50);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                finished.countDown();
            }
        });
    }

    public String id() {
        return id;
    }

    // Không ném checked exception; callback của ContextRunner
    // có thể gọi method này mà không cần catch InterruptedException.
    public boolean awaitStarted(long timeout, TimeUnit unit) {
        try {
            return started.await(timeout, unit);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while waiting for worker startup", ex);
        }
    }

    public boolean isClosed() {
        return closed.get();
    }

    public boolean isFinished() {
        return finished.getCount() == 0;
    }

    @Override
    public void close() {
        executor.shutdownNow();
        try {
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker executor did not terminate");
            }
            closed.set(true);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while stopping worker", ex);
        }
    }
}
~~~

**Điểm kiểm soát quan trọng:**

1. Worker là thread **non-daemon** để có thể làm lộ lỗi nếu quên shutdown.
2. `started` báo worker đã thực sự chạy; không dùng sleep đoán thời điểm.
3. `shutdownNow` yêu cầu interrupt; task xử lý `InterruptedException` và thoát.
4. `awaitTermination(2, SECONDS)` đặt deadline thay vì chờ vô hạn.
5. `finished` được count down khi task kết thúc, trong `finally`.
6. `closed` chỉ chuyển sang `true` sau khi executor đã dừng, tránh false positive.
7. `id` giúp xác nhận hai context mới có hai bean khác nhau.

Đây là **demo**, không phải một production worker implementation hoàn chỉnh. Với task thật phải kiểm queue, backpressure, tài nguyên bên ngoài, khả năng task bị tạo quá sớm trong constructor và phương án cleanup khi bean creation thất bại giữa chừng.

### 10.7. `WorkerIsolationTest.java`

~~~java
package com.example.lifecycle;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class WorkerIsolationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(WorkerConfig.class);

    @Test
    void contextCloseStopsItsOwnWorker() {
        AtomicReference<TrackedWorker> ref = new AtomicReference<>();

        runner.run(context -> {
            TrackedWorker worker = context.getBean(TrackedWorker.class);
            assertThat(worker.awaitStarted(2, TimeUnit.SECONDS)).isTrue();
            assertThat(worker.isClosed()).isFalse();
            ref.set(worker);
        });

        // ContextRunner đã đóng context sau khi callback kết thúc.
        TrackedWorker worker = ref.get();
        assertThat(worker).isNotNull();
        assertThat(worker.isClosed()).isTrue();
        assertThat(worker.isFinished()).isTrue();
    }

    @Test
    void repeatedRunsDoNotShareBean() {
        AtomicReference<TrackedWorker> first = new AtomicReference<>();
        AtomicReference<TrackedWorker> second = new AtomicReference<>();

        runner.run(context -> {
            TrackedWorker worker = context.getBean(TrackedWorker.class);
            assertThat(worker.awaitStarted(2, TimeUnit.SECONDS)).isTrue();
            first.set(worker);
        });

        runner.run(context -> {
            TrackedWorker worker = context.getBean(TrackedWorker.class);
            assertThat(worker.awaitStarted(2, TimeUnit.SECONDS)).isTrue();
            second.set(worker);
        });

        assertThat(first.get()).isNotNull();
        assertThat(second.get()).isNotNull();
        assertThat(first.get()).isNotSameAs(second.get());
        assertThat(first.get().id()).isNotEqualTo(second.get().id());
        assertThat(first.get().isClosed()).isTrue();
        assertThat(second.get().isClosed()).isTrue();
        assertThat(first.get().isFinished()).isTrue();
        assertThat(second.get().isFinished()).isTrue();
    }
}
~~~

**Vì sao kiểm `isClosed` bên ngoài callback?** Bởi vì bên trong callback, context còn mở. Khi `runner.run(...)` trả về, context đã được đóng và `@Bean(destroyMethod="close")` đã có cơ hội chạy. Đây là phép kiểm lifecycle trực tiếp thay vì dựa vào log `@PreDestroy`.

`ApplicationContextRunner` tạo context mới theo mỗi `run`, không cần `@DirtiesContext` để ép context cache. Các test không giữ lại executor đang chạy sau khi context kết thúc.

### 10.8. `BootLifecycleTest.java`

~~~java
package com.example.lifecycle;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = LifecycleIsolationApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_CLASS)
class BootLifecycleTest {

    @Autowired
    TrackedWorker worker;

    @Test
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void bootContextStartsManagedWorker() {
        assertThat(worker.awaitStarted(2, TimeUnit.SECONDS)).isTrue();
        assertThat(worker.isClosed()).isFalse();
    }
}
~~~

Giải thích:

- `BEFORE_CLASS` loại bỏ một context cùng cấu hình có thể đã được cache từ class trước.
- `AFTER_METHOD` khiến Spring TestContext đánh dấu context dirty và đóng sau method.
- Test **không tự gọi `context.close()`** khi TestContext đang sở hữu nó.
- Muốn khẳng định cleanup sau khi context đã đóng, test `ApplicationContextRunner` ở trên thích hợp hơn vì có callback scope rõ ràng.

Đừng bắt buộc dùng cách dirty before/after cho mọi test bình thường. Mẫu này chuyên để **thử vòng đời**, còn test đọc state nên tận dụng TestContext cache nếu an toàn.

### 10.9. `HookChild.java` — Java child process có thể tự gọi `System.exit`

~~~java
package com.example.lifecycle;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class HookChild {

    private HookChild() {
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected marker path");
        }

        Path marker = Path.of(args[0]);

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> {
                    try {
                        Files.writeString(
                                marker,
                                "HOOK_CALLED\n",
                                StandardCharsets.UTF_8,
                                StandardOpenOption.CREATE,
                                StandardOpenOption.TRUNCATE_EXISTING);
                    } catch (IOException ex) {
                        ex.printStackTrace(System.err);
                    }
                }, "hook-child-writer"));

        System.exit(23);
    }
}
~~~

`HookChild` không phụ thuộc Spring, dùng đúng Java 17 API. Nó có nhiệm vụ **minh họa cách kiểm thử JVM hook thật ở một JVM tách biệt**. File marker chỉ được ghi lúc hook thực thi; không được ghi sẵn nội dung mong đợi trước khi start child.

### 10.10. `HookProcessTest.java` — có timeout và dọn process

~~~java
package com.example.lifecycle;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class HookProcessTest {

    @Test
    void childJvmRunsHookAndParentTestSurvives() throws Exception {
        Path marker = Files.createTempFile("hook-child-", ".txt");
        Process child = null;

        try {
            Files.deleteIfExists(marker);

            boolean windows = System.getProperty("os.name")
                    .toLowerCase().contains("win");

            Path javaBin = Path.of(
                    System.getProperty("java.home"),
                    "bin", windows ? "java.exe" : "java");

            // Gradle Java test tiêu chuẩn: class nằm trong
            // output directory của main source set.
            Path classes = Path.of(
                    HookChild.class.getProtectionDomain()
                            .getCodeSource().getLocation().toURI());

            child = new ProcessBuilder(
                    javaBin.toString(),
                    "-cp", classes.toString(),
                    HookChild.class.getName(),
                    marker.toString())
                    .redirectErrorStream(true)
                    .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                    .start();

            if (!child.waitFor(15, TimeUnit.SECONDS)) {
                child.destroyForcibly();
                child.waitFor(3, TimeUnit.SECONDS);
                fail("Child JVM exceeded 15-second deadline");
            }

            assertEquals(23, child.exitValue());
            assertTrue(Files.exists(marker));
            assertEquals(
                    "HOOK_CALLED\n",
                    Files.readString(marker, StandardCharsets.UTF_8));
        } finally {
            if (child != null && child.isAlive()) {
                child.destroyForcibly();
                child.waitFor(3, TimeUnit.SECONDS);
            }
            Files.deleteIfExists(marker);
        }
    }
}
~~~

Phân tích cơ chế cô lập:

- Child dùng `java` trong `java.home` của test JVM.
- `HookChild` không cần Boot libraries, nên classpath của main output đủ trong build Gradle tiêu chuẩn. Với custom classloader/shaded JAR phải điều chỉnh.
- Mỗi lượt test tạo **một marker path riêng**, tránh xung đột giữa các lượt hoặc parallel test.
- `waitFor(15, SECONDS)` đặt giới hạn. Nếu child treo, parent thử kill để suite tiếp tục thất bại có thông tin rõ.
- `redirectOutput(DISCARD)` tránh child làm đầy stdout pipe không được đọc.
- Assert cả **exit status `23`** và **file nội dung `HOOK_CALLED`**; exit thành công riêng không chứng minh hook chạy.
- `finally` dọn file và child kể cả khi assertion ném exception.

**Không gọi `HookChild.main(...)` trực tiếp trong test method**. Nó có `System.exit(23)` và sẽ kết thúc chính JVM chạy JUnit.

**Phạm vi:** test này kiểm tra *JDK shutdown hook isolation*, không tuyên bố đã kiểm tra `SpringApplicationShutdownHook` của Boot. Muốn thử Boot hook thật, hãy chạy một executable Spring Boot JAR trong subprocess và quan sát marker từ `@PreDestroy` hoặc `SmartLifecycle.stop`, cùng cơ chế timeout/cleanup tương đương.

### 10.11. Cách chạy

Từ thư mục project nếu có Gradle Wrapper tương thích:

~~~bash
./gradlew clean test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

Nếu đã cài Gradle phù hợp nhưng chưa có wrapper:

~~~bash
gradle clean test
~~~

Kết quả kỳ vọng khi kiểm thử thành công là Gradle báo **BUILD SUCCESSFUL**. Đây là kỳ vọng của build, không phải log stdout chính xác từng dòng vì khác version/daemon/logging. Có **bốn test** trong ba class: hai `WorkerIsolationTest`, một `BootLifecycleTest` và một `HookProcessTest`.

**Các đoạn mã đã được rà soát theo API**, nhưng kết quả thực tế phải kiểm tra trên JDK 17/Gradle và môi trường CI của dự án. Một môi trường hạn chế subprocess hoặc tạo file có thể khiến `HookProcessTest` thất bại và cần điều chỉnh hạ tầng, không nên âm thầm bỏ kiểm tra hook.

## 11. Nếu chỉ dùng Spring Framework core: `AnnotationConfigApplicationContext`

Một cách khác:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(WorkerConfig.class)) {

    TrackedWorker worker = context.getBean(TrackedWorker.class);
    if (!worker.awaitStarted(2, TimeUnit.SECONDS)) {
        throw new AssertionError("Worker did not start");
    }
}
// Khi rời block, context.close() đã được gọi.
~~~

Đây là **fragment** trong một test có import `AnnotationConfigApplicationContext` và `TimeUnit`, cùng các class của project ví dụ. Không cần Spring Boot TestContext cache; test tự sở hữu context.

Mục đích khác nhau:

- `ApplicationContextRunner` thuận tiện cho nhiều biến thể bean/configuration, mỗi `run` có cleanup tự động.
- `AnnotationConfigApplicationContext` cho phép test tự điều khiển trực tiếp lifecycle.
- `@SpringBootTest` thích hợp khi cần **Boot bootstrap/auto-configuration** thật và cache dùng lại có lợi.
- `ProcessBuilder` bắt buộc hơn khi thử **JVM-level hooks/exit**, không chỉ context.

## 12. System properties và static state cần được hoàn nguyên

Một test có lệnh:

~~~java
System.setProperty("feature.mode", "test");
~~~

đã thay đổi trạng thái **cho toàn JVM**. `@DirtiesContext` không reset giá trị này. Test chạy sau có thể đọc sai config.

Mẫu an toàn:

~~~java
String key = "feature.mode";
String oldValue = System.getProperty(key);

try {
    System.setProperty(key, "test");
    // Gọi assertions cần property tạm thời.
} finally {
    if (oldValue == null) {
        System.clearProperty(key);
    } else {
        System.setProperty(key, oldValue);
    }
}
~~~

Nếu JUnit chạy song song, một test khác có thể đọc/ghi property trong lúc test này chưa restore. Khi cần thao tác global, dùng `@ResourceLock` với **cùng tên resource** cho mọi test liên quan, hoặc tốt hơn là **tránh sửa System properties** bằng cách truyền test properties vào context riêng.

Ví dụ fragment:

~~~java
@ResourceLock("GLOBAL_FEATURE_MODE")
@Test
void modifiesGlobalState() {
    // Đọc/ghi System property, kèm try/finally restore.
}
~~~

Cần import `org.junit.jupiter.api.parallel.ResourceLock`. Một test tự dùng lock mà test khác không dùng **không tạo ra mutual exclusion toàn JVM**.

Các state thường bị bỏ sót: `Locale.setDefault`, `TimeZone.setDefault`, static maps/caches, `System.setOut`, system properties, security context, thread-local correlation IDs và mock static instrumentation.

## 13. `ThreadLocal`, MDC và SecurityContext trên worker threads

`ThreadLocal` được lưu ở **thread thực hiện công việc**. Dọn ThreadLocal trên JUnit caller không tự dọn dữ liệu đang giữ trên executor worker.

Ví dụ đúng với task chạy trong worker:

~~~java
private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

// Khi submit:
executor.submit(() -> {
    try {
        TENANT.set("tenant-test");
        doWork();
    } finally {
        TENANT.remove();
    }
}).get(2, TimeUnit.SECONDS);
~~~

Đây là fragment trong class có field `TENANT`, executor và method `doWork`. `finally` chạy trong chính worker thread khi task hoàn thành.

Với Spring Security/MDC, xem cơ chế propagation và clear context tương ứng. Không cho rằng `@Async` tự chuyển transaction context hoặc security context qua mọi ranh giới thread. Nếu task đang chạy sau khi test kết thúc, nó có thể tạo dữ liệu/viết log ảnh hưởng test khác.

## 14. `@Scheduled`, `@Async`, listener và queue consumer

| Thành phần | Nhiễu thường gặp | Phòng vệ |
| --- | --- | --- |
| `@Scheduled` | Tự chạy lúc test khác kiểm DB | Dùng cấu hình test hẹp; kiểm scheduler lifecycle |
| `@Async` | Future chưa xong, state chưa ổn định | Đợi `CompletableFuture`/`Future` với deadline |
| `ApplicationListener` | Callback tạo worker hoặc gửi event muộn | Quản lý resource trong bean và xác minh cleanup |
| Kafka/Rabbit/JMS | Consumer A đọc message của test B | Queue/topic/test IDs riêng và stop container rõ |
| Mock HTTP server | Cổng cố định bị chiếm | Dynamic port, stop server sau test |
| DB/Redis cache | Dữ liệu của run trước còn | Transaction/fixture/namespace và cleanup |
| Testcontainers | Container sống qua nhiều class hoặc static | Xác định ai sở hữu container, cleanup chính xác |

Không bịa một property “disable-all-scheduling” rồi tin nó tắt tất cả `@Scheduled`; cần xác định ứng dụng dùng `@EnableScheduling`, scheduler bean nào và điều kiện cấu hình thật.

Nếu chỉ test bean lifecycle, **không load toàn bộ ứng dụng với scheduler và queue listeners** khi `ApplicationContextRunner`/một `@Import` config nhỏ đã đủ. Điều này giảm nhiễu và chi phí.

## 15. External resources: port, DB, file, container

`@DirtiesContext` không tự xóa dữ liệu đã commit ở DB hoặc broker. Với môi trường test chạy song song:

- Dùng cổng động khi test HTTP server hoặc mock server.
- Dùng `@TempDir`/`Files.createTempFile`, không dùng cùng một file marker tên cố định.
- Tạo ID/namespace/schema riêng cho test records.
- Dọn các bản ghi theo **owner/test-run ID**, không xóa nhầm dữ liệu chung.
- Với Testcontainers, phân biệt per-test/per-class/static shared container.
- Không dùng cùng queue không có correlation filter nếu nhiều test gửi message song song.
- Đặt timeout/rollback/cleanup kể cả khi assertion fail.

Đối với HTTP test trên cổng thật, đừng giả định `@Transactional` rollback mọi side effect của server thread: request thường chạy transaction riêng.

## 16. Cách tìm leak và test bị treo

### Bật log context cache

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Xem cache hit/miss và vòng đời đóng context, nhưng tránh suy ra rằng log context close chứng minh **executor ngoài Spring** đã dừng.

### Thread dump test worker

~~~bash
jcmd <PID> Thread.print
~~~

Thay `<PID>` bằng PID JVM chạy test worker thực, **không nhầm với Gradle daemon**. Tìm thread có tên như `tracked-worker-*`, timer, scheduler, broker listener hoặc thread đang chờ latch vô hạn.

Hỏi lần lượt:

1. Thread do code nào tạo?
2. Có thuộc Spring bean hay test fixture không?
3. Có signal cancel/interruption không?
4. Method cleanup đã chạy chưa?
5. Task có vòng lặp bỏ qua interrupt không?
6. Executor có `awaitTermination` với timeout không?
7. Có TestContext cache còn giữ context và worker không?

### Không lấy `Thread.activeCount()` làm assertion cứng

Tổng số thread active có thể đổi do Gradle, JUnit, GC, logging, timer của thư viện. Một số thread là daemon. Cách chắc chắn hơn là kiểm **executor do test sở hữu đã terminate**, thread cụ thể đã join hoặc worker `finished` latch đã count down.

### Hook marker

Subprocess test nên kiểm **cả marker, exit code và child timeout**. Nếu chỉ thấy process thoát `23` thì không có bằng chứng hook đã thực thi thành công; nếu chỉ thấy marker có thể là file cũ. Hãy tạo tên duy nhất và xóa trước run.

## 17. Ma trận chạy để xác nhận test độc lập

| Kiểu chạy | Mục tiêu |
| --- | --- |
| Một method | Logic cơ bản |
| Toàn class | State giữa các methods |
| Toàn suite | Context cache/static thread/hook giữa classes |
| Đổi thứ tự test | Phát hiện assumption về thứ tự |
| Chạy suite lặp | Resource leak và cleanup |
| Chạy song song khi dự án cho phép | Cạnh tranh global resource, port, DB |
| CI ít CPU/RAM | Phát hiện sleep-based flaky test |
| Test bị timeout/exception | `finally` và child cleanup có chạy không |

Lệnh chạy một class trong Gradle:

~~~bash
./gradlew test --tests 'com.example.lifecycle.WorkerIsolationTest'
~~~

Chạy toàn suite:

~~~bash
./gradlew clean test
~~~

Không chữa flaky test chỉ bằng `Thread.sleep(1000)`, tăng timeout vô hạn hoặc thêm `@DirtiesContext` vào tất cả tests. Hãy tìm tài nguyên rò ở đúng cấp sở hữu.

## 18. Lỗi phổ biến

1. **Tự đóng context injected từ `@SpringBootTest`:** có thể làm hỏng TestContext cache; dùng `@DirtiesContext`.
2. **Cho rằng mỗi method có context mới:** TestContext có cache theo configuration key.
3. **Cho rằng `@DirtiesContext` reset mọi static variables:** sai, state JVM còn.
4. **Gắn dirty lên toàn bộ tests:** suite chậm và che lỗi cleanup.
5. **Tạo executor nhưng không shutdown:** non-daemon worker có thể khiến Gradle test treo.
6. **Gọi `shutdownNow` và nghĩ task đã chết:** cần cooperative interruption + await.
7. **Dùng `Thread.sleep` để đợi sự kiện:** dễ flaky, dùng latch/future.
8. **Tạo JVM shutdown hook trong test và quên remove:** hook chạy bất ngờ ở cuối suite.
9. **Gọi `System.exit` trong JUnit:** giết toàn test worker JVM.
10. **Giả định JVM hooks chạy theo thứ tự đăng ký:** không được bảo đảm.
11. **Dùng `Runtime.halt` để “thử hook”:** halt bỏ qua hooks.
12. **Chạy subprocess không timeout:** child treo kéo suite treo.
13. **Không dọn child process trong `finally`:** child còn sống sau assertion fail.
14. **Dùng một marker file chung:** test song song ghi đè kết quả.
15. **Dùng `DEFINED_PORT` không cần thiết:** test tranh chấp cổng.
16. **Giả định `@Transactional` rollback HTTP server transaction:** client/server khác thread.
17. **Quên restore `System.setProperty`:** test sau đọc config sai.
18. **Chỉ clear `ThreadLocal` ở caller:** worker pool còn state.
19. **Nhầm TestContext cache shutdown với Boot shutdown hook:** cấp sở hữu khác nhau.
20. **Tin một lần test đơn lẻ đã chứng minh isolation:** cần chạy suite/lặp/sắp xếp khác nhau.
21. **Dựa vào `Thread.activeCount()`:** số lượng thread bị nhiễu, không xác minh executor cụ thể.
22. **Không kiểm tra resource của static Testcontainers:** context close chưa chắc dọn container.
23. **Chạy process con để test mọi service method:** quá tốn và không cần thiết.
24. **Không xác định ai sở hữu bean và hook:** cleanup bỏ sót hoặc chạy hai lần.
25. **Bỏ qua cancellation của async jobs:** task còn ghi DB sau khi test khác bắt đầu.
26. **Cho rằng context close luôn chạy mọi callback dưới forced kill:** không được bảo đảm.

## 19. Checklist trước khi đưa vào CI

| Điểm kiểm | Tiêu chí đạt |
| --- | --- |
| Context cache | Hiểu cache key, biết test nào reuse |
| Dirty mode | Đặt đúng before/after khi context thực sự bẩn |
| Context owner | TestContext, runner hoặc test caller rõ ràng |
| Bean cleanup | Có destroy method/`@PreDestroy`/`SmartLifecycle` phù hợp |
| Worker | Dừng bằng interrupt/cancel và chờ với deadline |
| Async | Không còn task nền tác động test khác |
| Hook | Không bỏ lại hook trong parent JVM |
| Subprocess | Timeout, exit, marker, cleanup đầy đủ |
| Global state | Restore properties/Locale/TimeZone/static changes |
| ThreadLocal | Remove trên thread thực thi |
| Network | Dùng port động khi có thể |
| Data | Fixture và namespace/ID độc lập, cleanup có kiểm soát |
| Parallelism | Khóa hoặc không sử dụng global mutable state |
| Java/build | Java17+, Spring Boot 3.3 BOM, JUnit 5 |
| Verification | Chạy một method, class, full suite, CI và lặp |
| Failure evidence | Log rõ process/context/thread nào chưa được dọn |

## 20. Câu hỏi tự kiểm tra

1. **Vì sao hai `@SpringBootTest` có thể chia sẻ singleton?** Vì TestContext cache context cùng cấu hình trong JVM.
2. **`@DirtiesContext` làm gì?** Đánh dấu context bẩn, loại khỏi cache và đóng theo mode.
3. **`AFTER_CLASS` có bắt buộc context mới trước class không?** Không; nếu cần fresh trước dùng mode BEFORE.
4. **`@DirtiesContext` có reset static map, JVM hooks không?** Không.
5. **Khi nào không cần `@DirtiesContext`?** Test không làm bẩn context và reuse an toàn.
6. **Ai đóng context của `ApplicationContextRunner`?** Runner sau callback.
7. **Vì sao kiểm bean `isClosed` ngoài callback?** Bên trong callback context vẫn đang mở.
8. **`context.close()` tự tắt mọi `new Thread` không?** Không.
9. **Vì sao non-daemon worker có thể khiến Gradle test treo?** Thread chưa kết thúc giữ JVM sống.
10. **Có thể tin `shutdownNow` mà không await không?** Không, task phải hợp tác với interrupt.
11. **Vì sao latch/future tốt hơn `sleep`?** Đợi điều kiện thật với deadline.
12. **Runtime hook thuộc Spring context không?** Không, thuộc toàn JVM.
13. **Có nên gọi `System.exit(23)` trong JUnit method không?** Không.
14. **Hook có thứ tự chạy được bảo đảm không?** Không, có thể chạy đồng thời.
15. **Hook tạm thời gỡ bằng gì?** `Runtime.removeShutdownHook` trước JVM shutdown.
16. **Subprocess test cần kiểm gì?** Exit code, marker, timeout và cleanup.
17. **Tại sao dùng file marker riêng?** Tránh ghi đè và kết quả cũ.
18. **`@Transactional` test có rollback HTTP server-side không?** Không tự động.
19. **Có nên sửa System property mà không restore?** Không.
20. **`ThreadLocal` ở executor worker cần clear ở đâu?** Trong worker thread.
21. **Vì sao `Thread.activeCount()` không phải bằng chứng chắc chắn?** Nhiều threads ngoài test và con số biến động.
22. **Lúc nào nên dùng subprocess thay vì context mới?** Kiểm JVM-level hook, `System.exit`/signal/process exit.
23. **Nếu test chỉ fail trong full suite nên kiểm gì?** Context cache, static state, threads, hooks, ports và external fixtures.
24. **Nên tối ưu test isolation bằng cách nào?** Unit test trước, context nhỏ khi đủ, dirty chọn lọc, subprocess khi cần JVM boundary.

**Kết luận:** Test vòng đời tin cậy không chỉ là “context đã đóng”. Hãy phân biệt **Spring TestContext cache**, **thread/executor**, **JVM shutdown hooks**, **global state** và **external fixtures**. Context do TestContext quản lý dùng dirty mode đúng lúc; context tự tạo đóng ngay bằng `ApplicationContextRunner` hoặc `try-with-resources`; worker phải có cancellation và bounded await; hook thật và `System.exit` chạy trong JVM con; còn properties, file, port, DB và ThreadLocal cần cleanup đúng owner. Khi mọi thử nghiệm có ranh giới rõ và chạy lặp độc lập, suite mới thực sự kiểm tra được start/stop mà không làm hỏng kết quả của các test khác.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — **Testing Spring Boot Applications**, `@SpringBootTest` và webEnvironment: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot — **ApplicationContextRunner** trong tài liệu tạo auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Framework 6.1 — **`@DirtiesContext` API**: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/annotation/DirtiesContext.html
- Spring Framework — **Context Caching**: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — **Bean Lifecycle và `SmartLifecycle`**: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3.13 — **`SpringApplication.setRegisterShutdownHook`**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Oracle Java 17 — **Runtime shutdown hooks**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html
- Oracle Java 17 — **ProcessBuilder**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- Spring Boot 3.3 — **Gradle Managing Dependencies**: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
