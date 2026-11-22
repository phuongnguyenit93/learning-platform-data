# Thiết kế đóng tài nguyên nhiều lần an toàn và có thời hạn trong Spring Boot

## 1. Bài toán: close() bị gọi lần thứ hai không được phá hệ thống

Trong ứng dụng Spring Boot, tài nguyên có vòng đời riêng có thể là `ExecutorService`, HTTP client, connection pool, message consumer, file writer, cache có thread nền, socket, scheduler hoặc một bộ phận kết nối dịch vụ bên ngoài. Một tài nguyên có thể cần được đóng khi:

- Ứng dụng kết thúc bình thường và Spring đóng `ApplicationContext`.
- Bean bị hủy theo lifecycle của container.
- Một tác vụ quản trị chủ động gọi `close()` hoặc `stop()`.
- Việc khởi tạo thất bại giữa chừng và hệ thống phải cleanup các tài nguyên đã cấp phát.
- Có lỗi nghiêm trọng khiến thành phần phải ngừng hoạt động trước khi toàn bộ ứng dụng dừng.
- Nhiều thành phần hoặc nhiều thread gần như đồng thời gửi yêu cầu dừng.

Đừng thiết kế theo giả định “`close()` sẽ được gọi đúng một lần, trên đúng một thread, đúng một thời điểm”. Một API đóng tài nguyên tốt nên có hai thuộc tính:

1. **An toàn khi gọi nhiều lần (idempotent shutdown):** nhiều lời gọi không làm thực hiện các side effect nguy hiểm nhiều lần, không đóng sai tài nguyên của chủ sở hữu khác và không tạo race làm rò rỉ việc đang chạy.
2. **Có thời hạn và kết quả rõ ràng (bounded shutdown):** quy trình có deadline hợp lý; caller biết nó đã hoàn thành sạch, phải force-stop, bị gián đoạn hay chưa thể xác nhận tài nguyên đã dừng.

Quan hệ logic cần nhớ:

```text
Một lời gọi close()       -> yêu cầu dừng
Nhiều lời gọi close()     -> cùng hướng đến một trạng thái kết thúc
Graceful timeout          -> giới hạn chờ, KHÔNG chứng minh đã dừng
Forced shutdown           -> cố yêu cầu dừng, KHÔNG luôn thành công
Completion thực sự        -> có bằng chứng tài nguyên ngừng hoạt động
ApplicationContext.close  -> điều phối vòng đời, KHÔNG hiểu mọi bất biến nghiệp vụ
```

**Mục tiêu của bài:** thiết kế một cách đóng *lặp được, có cạnh tranh cũng an toàn, không chờ vô hạn* và biết cách nối nó với Spring Boot. Đây là bài về tài nguyên ứng dụng, **không phải** lời hứa exactly-once cho các thao tác dữ liệu khi nhiều tiến trình cùng chạy.

## 2. “Idempotent close” không có nghĩa “cứ gọi lại là bỏ qua ngay”

Cách đóng đơn giản thường thấy:

```java
private boolean closed;

public void close() {
    if (!closed) {
        closed = true;
        connection.close();
    }
}
```

Đây là **pseudocode minh họa rủi ro**, không phải chương trình hoàn chỉnh. Nó có ít nhất ba vấn đề:

- `closed` không được đồng bộ: hai thread có thể cùng thấy `false` rồi cùng gọi `connection.close()`.
- Cờ được đặt `true` **trước khi** việc đóng thực sự thành công. Nếu `connection.close()` ném exception hoặc việc đóng là bất đồng bộ, những caller sau có thể bị báo là đã đóng dù resource còn sống.
- Nếu thread A đang đóng trong nhiều giây, thread B thấy `closed=true` và trả về ngay. Nếu hợp đồng của B là “khi `close()` trả về, không còn tác vụ chạy”, điều đó bị vi phạm.

Thực tế cần phân biệt ít nhất:

| Trạng thái | Ý nghĩa |
|---|---|
| `OPEN` | Đang nhận công việc và tài nguyên sẵn sàng |
| `CLOSING` | Không nhận việc mới; cleanup/drain đang diễn ra |
| `CLOSED` | Đã xác nhận cleanup/termination thành công |
| `FAILED_TO_CLOSE` | Đã yêu cầu stop nhưng không thể xác nhận hoàn tất trong điều kiện cho phép |

Một biến `AtomicBoolean closingStarted` có thể giúp chọn **một người thực hiện cleanup**, nhưng **không đủ** để các caller khác biết khi nào đã hoàn tất. Cần thêm một dấu hiệu hoàn tất như `CountDownLatch` hoặc `CompletableFuture`.

### Bất biến cần giữ

Trong mô hình một owner và nhiều caller:

1. Không nhận thêm công việc mới sau khi hệ thống chuyển sang đóng.
2. Không có hai thread độc lập cùng tiến hành cleanup phá hoại lên resource.
3. Những caller đến sau quan sát được **cùng kết quả kết thúc**, không tự tưởng tượng rằng `closingStarted=true` đồng nghĩa `CLOSED`.
4. Không trả về thành công khi chưa có điều kiện xác nhận termination.
5. Không chờ vô hạn; timeout/interrupt có lối thoát và được báo đúng.
6. Không reset trạng thái `CLOSED` về `OPEN` chỉ vì có một lời gọi start mới, trừ khi ứng dụng đã thiết kế **chu kỳ tái khởi động** tường minh.

**Chú ý:** “idempotent” mô tả hiệu ứng của việc lặp lại thao tác. Nó **không** bắt mọi lần `close()` phải không bao giờ ném lỗi. Nếu tài nguyên không dừng được, ném exception có ý nghĩa hơn là trả về giả vờ thành công.

## 3. Sở hữu tài nguyên: ai tạo thì ai chịu trách nhiệm đóng?

Trước khi chọn annotation, cần trả lời **ai sở hữu** tài nguyên.

| Cách có được tài nguyên | Chủ sở hữu thường là | Cách đóng phù hợp |
|---|---|---|
| Bean singleton do `@Bean` tạo, container quản lý đầy đủ | Spring container / bean chịu trách nhiệm resource nội bộ | `@Bean(destroyMethod="close")` hoặc cơ chế destroy rõ ràng |
| `@Component` có resource được tạo trong constructor/init | Chính bean component | `@PreDestroy` / `DisposableBean` hoặc `SmartLifecycle` theo nhu cầu |
| Executor/connection được lấy từ bean dùng chung | Bean hạ tầng cấp resource | Consumer **không** tự gọi shutdown lên tài nguyên dùng chung |
| Tài nguyên tạo trong một scope ngắn và không đưa vào container | Block hoặc object tạo tài nguyên | `try-with-resources` / `finally` |
| Một client wrapper cho tài nguyên được bên ngoài sở hữu | Owner bên ngoài | Wrapper chỉ đóng những phần nó thực sự sở hữu |
| Resource đang được framework quản lý như server hoặc scheduler | Framework lifecycle | Không tự gọi close phá hạ tầng khi chưa đúng thời điểm |

**Nguyên tắc:** *ownership* quan trọng hơn việc một đối tượng có method `close()`. Nếu service A chỉ được tiêm một `ExecutorService` dùng chung từ bean B, A không nên gọi `executor.shutdown()` trong `@PreDestroy` của mình khi những service khác vẫn cần executor đó.

Ví dụ rủi ro:

```java
@Service
class ReportService {

    private final ExecutorService sharedExecutor;

    ReportService(ExecutorService sharedExecutor) {
        this.sharedExecutor = sharedExecutor;
    }

    @PreDestroy
    void cleanup() {
        sharedExecutor.shutdown(); // Sai nếu executor thuộc một bean hạ tầng khác.
    }
}
```

Đoạn này chỉ minh họa lỗi ownership; cần các import Spring/JDK và bean executor thực tế. Đặt lại trách nhiệm đóng cho bean cấp phát executor, rồi để những consumer ngừng gửi việc mới trước khi executor được dừng.

## 4. Các điểm móc đóng tài nguyên của Spring

Spring hỗ trợ nhiều cơ chế hủy bean:

### 4.1. @PreDestroy

Một method được gọi khi **bean do Spring quản lý** bị hủy trong chu kỳ đóng context thích hợp:

```java
@Component
class LocalCache {

    @PreDestroy
    void release() {
        // Đóng tài nguyên mà LocalCache sở hữu.
    }
}
```

`@PreDestroy` của Spring Boot 3.3 dùng annotation `jakarta.annotation.PreDestroy`. Nó thích hợp cho teardown đồng bộ vừa phải. Không có hợp đồng sẵn để Spring đợi một chuỗi bất đồng bộ đã khởi chạy bên trong method này hoàn tất chỉ vì method trả về.

### 4.2. @Bean(destroyMethod = "close")

Khi một tài nguyên được tạo bằng factory method:

```java
@Configuration
class ResourceConfiguration {

    @Bean(destroyMethod = "close")
    ManagedResource managedResource() {
        return new ManagedResource();
    }
}
```

Đây là **snippet tích hợp**: cần class `ManagedResource` có `public void close()` cùng các import. Spring sẽ gọi destroy method khi bean singleton thuộc sở hữu container bị hủy.

Spring Framework cũng có cơ chế **suy luận** destroy method trên bean tạo bằng `@Bean` nếu đối tượng có method `close` hoặc `shutdown` phù hợp. Viết tường minh `destroyMethod="close"` giúp hợp đồng dễ đọc, đặc biệt trong bài học.

### 4.3. AutoCloseable và try-with-resources

`AutoCloseable` là interface của Java:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Một class có thể override `close()` mà không khai báo `throws Exception`. Khi resource do một block Java sở hữu, `try-with-resources` gọi close ở cuối block:

```java
try (SomeResource resource = openResource()) {
    use(resource);
}
```

Đây là mẫu tổng quát, cần implementation `SomeResource`, `openResource()` và `use(...)` thật. Đừng vừa đặt một resource trong `try-with-resources`, vừa giao cùng resource cho Spring quản lý mà không hiểu rõ việc nó có thể bị yêu cầu đóng từ **hai đường**. Một `close()` idempotent giúp hạn chế rủi ro nhưng **không thay thế việc phân công owner rõ ràng**.

### 4.4. DisposableBean

`org.springframework.beans.factory.DisposableBean.destroy()` là callback hủy cấp Spring. Nó phù hợp khi bạn cần hợp đồng trực tiếp với framework; với class nghiệp vụ/library muốn độc lập Spring, `AutoCloseable` hoặc destroy method tường minh thường dễ test hơn.

### 4.5. SmartLifecycle

`SmartLifecycle` được sử dụng khi cần **start/stop có phase** hoặc dừng bất đồng bộ có callback:

```java
void stop(Runnable callback);
```

`DefaultLifecycleProcessor` điều phối dừng theo phase giảm dần, đợi các callback hoặc hết timeout của phase trước khi chuyển tiếp. Nó khác method `@PreDestroy` hoặc `@Bean(destroyMethod=...)`: **callback dành cho việc điều phối giai đoạn dừng**, còn destroy method dành cho hủy bean.

Không ghép tất cả cơ chế vào một bean rồi mặc định “càng nhiều callback càng an toàn”. Nếu có cả `SmartLifecycle.stop(Runnable)`, `@PreDestroy` và `close()`, phải phân chia rõ trách nhiệm, thứ tự và khả năng gọi trùng. Một cách thường gặp: phase stop ngừng nhận việc và drain; destroy cuối chỉ kiểm tra/đóng dự phòng khi state đã dừng.

## 5. Spring Boot shutdown timeout bao phủ những gì?

Trong Spring Boot 3.3:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Thuộc tính này điều chỉnh thời hạn **chờ mỗi nhóm phase của `LifecycleProcessor`**, áp dụng cho việc dừng các bean lifecycle, bao gồm `SmartLifecycle`. Nó **không phải timeout tổng cho mọi câu lệnh Java trong shutdown**.

Không suy luận:

```text
spring.lifecycle.timeout-per-shutdown-phase=20s
=> mọi @PreDestroy và mọi @Bean(destroyMethod="close")
   chắc chắn return trong 20 giây.
```

Suy luận đó **sai**. Một method destroy đồng bộ có thể bị chặn vì I/O hoặc khóa; timeout của phase không tự ngắt method ấy. Nếu cần close có thời hạn, chính resource hoặc cơ chế gọi phải có **deadline cấp tài nguyên**.

Một ứng dụng có thể có:

```text
A. SIGTERM từ orchestrator
         |
B. SpringApplicationContext đóng
         |
C. SmartLifecycle stop (timeout theo phase)
         |
D. Destroy singleton beans (@PreDestroy, close, destroy)
         |
E. JVM kết thúc nếu không còn thread giữ tiến trình
```

Quỹ thời gian ở tầng A có thể ngắn hơn tổng các giai đoạn C+D. Khi bị `SIGKILL` hoặc `kill -9`, JVM không có cơ hội thực hiện cleanup bình thường.

### Graceful Web shutdown không tự đóng mọi worker nghiệp vụ

Với ứng dụng Web Spring Boot 3.3:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Spring Boot cho Web server ngừng nhận request mới và cho request đang xử lý khoảng thời gian hoàn thành theo giới hạn cấu hình. Nhưng **message consumer, custom executor, file writer** vẫn cần thiết kế stop riêng. Đừng cho rằng bật graceful Web server thì mọi client kết nối bên ngoài, mọi queue in-memory và mọi database transaction đều được flush.

## 6. ExecutorService: yêu cầu dừng khác xác nhận đã dừng

Với Java 17, `ExecutorService` cung cấp các API:

| API | Ý nghĩa | Có chờ hoàn tất không? |
|---|---|---|
| `shutdown()` | Ngừng nhận task mới; cho task đã nhận tiếp tục | **Không** |
| `isShutdown()` | Đã có yêu cầu shutdown | Không nói mọi task đã xong |
| `awaitTermination(timeout, unit)` | Chờ executor kết thúc hoặc hết thời hạn / bị interrupt | **Có**, trả boolean |
| `isTerminated()` | Xác nhận executor đã kết thúc sau shutdown | Kiểm tra trạng thái |
| `shutdownNow()` | Cố interrupt task đang chạy và trả task chưa bắt đầu | **Không bảo đảm** đã dừng |
| `Future.get(timeout, unit)` | Chờ **một task** hoàn tất trong một khoảng thời gian | Không thay shutdown của toàn executor |

Đây là điểm bẫy điển hình:

```java
executor.shutdown();
closed = true;
```

Nếu còn task đang chạy, `closed=true` không thể được hiểu là “executor terminated”. Thiết kế nên dùng những tên rõ như `shutdownRequested`, `acceptingNewTasks` và `terminated`.

### Hai giai đoạn graceful → forced

Một quy trình cơ bản:

```text
Tắt intake của ứng dụng
        |
executor.shutdown()
        |
awaitTermination(gracePeriod)
        |
   +----+----+
   |         |
   v         v
terminated   timeout
   |         |
   |         v
   |    executor.shutdownNow()
   |         |
   |    awaitTermination(forcePeriod)
   |         |
   |       +-- terminated?
   |       |   +-- yes: kết thúc cưỡng bức có kiểm soát
   |       |   +-- no: báo UNKNOWN / FAILED_TO_CLOSE
   v
Thành công (có bằng chứng)
```

`shutdownNow()` chỉ là **best-effort**. Nếu task mắc kẹt trong native I/O hoặc bỏ qua interrupt, nó có thể vẫn chạy sau khi `shutdownNow()` trả về. Khi đó **không được tuyên bố close đã thành công** chỉ vì hết thời gian chờ.

Việc gọi `shutdownNow()` cũng có thể loại các task chưa chạy khỏi queue. Nếu chúng chứa nghiệp vụ quan trọng, ứng dụng phải ghi nhận và xử lý mất việc/retry/checkpoint phù hợp, không xem đó là cleanup không có hậu quả.

## 7. Ví dụ chạy được: AutoCloseable có đóng lặp an toàn và chờ tối đa hai giai đoạn

Dự án **Java 17 + Spring Boot 3.3.5** sau đây minh họa:

- Một bean `GuardedJobResource` **sở hữu** executor do chính nó tạo.
- Method `submit(...)` và giai đoạn tắt intake dùng **cùng một lock**.
- `AtomicBoolean` chọn **đúng một caller** tiến hành shutdown.
- `CountDownLatch` cho các caller đóng sau biết **lần đóng đầu đã hoàn tất hay chưa**.
- Có hai khoảng chờ cụ thể: tối đa **1 giây graceful** rồi **1 giây sau yêu cầu force-stop**.
- Nếu executor không kết thúc, method báo lỗi; không giả vờ đã đóng sạch.
- `@Bean(destroyMethod="close")` để Spring gọi lại `close()` khi context hủy bean; lần gọi sau không đóng trùng.
- Runner đóng tài nguyên chủ động hai lần, rồi việc đóng context tạo thêm một lần gọi để kiểm chứng idempotency.

Đây là **demo một JVM** với task hợp tác và chạy ngắn. Nó không tự cung cấp durable queue, retry, exactly-once, bảo đảm thread không bao giờ treo hoặc full restart semantics.

### 7.1. Cấu trúc dự án

```text
bounded-resource-close/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/boundedclose/
    ├── BoundedCloseApplication.java
    └── GuardedJobResource.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'bounded-resource-close'
```

**`build.gradle` (Gradle Groovy DSL):**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
}
```

Không cần Web server hay database. Để chạy lệnh `./gradlew`, dự án cần Gradle Wrapper đã được tạo (ví dụ qua Spring Initializr) hoặc một Gradle cài sẵn tương thích; chỉ viết `build.gradle` không tự sinh script Wrapper.

### 7.2. Resource sở hữu executor và tự bảo vệ close

**`src/main/java/com/example/boundedclose/GuardedJobResource.java`:**

```java
package com.example.boundedclose;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class GuardedJobResource implements AutoCloseable {

    private final Object admissionLock = new Object();

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor(task ->
                    new Thread(task, "owned-job-worker"));

    private final AtomicBoolean closeStarted = new AtomicBoolean(false);
    private final CountDownLatch closeFinished = new CountDownLatch(1);

    // Những field này được đọc sau khi latch báo completion.
    private volatile boolean terminated;
    private volatile String closeFailure = "unknown";

    // Mọi truy cập biến này được bảo vệ bởi admissionLock.
    private boolean accepting = true;

    public Future<String> submit(String jobId) {
        Objects.requireNonNull(jobId, "jobId");

        synchronized (admissionLock) {
            if (!accepting) {
                throw new RejectedExecutionException(
                        "Resource is closing; new jobs are rejected");
            }

            return executor.submit(() -> {
                // Mô phỏng I/O hợp tác với interruption.
                Thread.sleep(100);
                return "done:" + jobId;
            });
        }
    }

    @Override
    public void close() {
        if (closeStarted.compareAndSet(false, true)) {
            // Chỉ caller đầu tiên sở hữu đường shutdown.
            try {
                synchronized (admissionLock) {
                    accepting = false;
                    executor.shutdown();
                }
                System.out.println("CLOSE: requested");

                boolean stopped =
                        executor.awaitTermination(1, TimeUnit.SECONDS);

                if (!stopped) {
                    List<Runnable> pending = executor.shutdownNow();
                    System.err.println(
                            "CLOSE: forced; not-started jobs = "
                            + pending.size());

                    stopped = executor.awaitTermination(
                            1, TimeUnit.SECONDS);
                }

                terminated = stopped;

                if (!stopped) {
                    closeFailure =
                            "executor still running after stop deadline";
                    throw new IllegalStateException(closeFailure);
                }

                System.out.println("CLOSE: terminated");
            } catch (InterruptedException ex) {
                // Không quên yêu cầu dừng khi caller bị interrupt.
                executor.shutdownNow();
                closeFailure = "close thread was interrupted";
                Thread.currentThread().interrupt();
                throw new IllegalStateException(closeFailure, ex);
            } finally {
                // Luôn đánh dấu lần thử close đã KẾT THÚC;
                // không đồng nghĩa nó đã thành công.
                closeFinished.countDown();
            }
        } else {
            // Caller tới sau không nhầm CLOSING với CLOSED.
            try {
                if (!closeFinished.await(2, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "another close call is still in progress");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "interrupted while waiting for close", ex);
            }

            if (!terminated) {
                throw new IllegalStateException(
                        "previous close did not terminate: "
                        + closeFailure);
            }

            System.out.println("CLOSE: already terminated");
        }
    }
}
```

**Giải thích theo từng bất biến:**

1. `GuardedJobResource` implement `AutoCloseable`, nên caller không phụ thuộc Spring vẫn có thể quản lý bằng `try-with-resources`.
2. Nó tự tạo `ExecutorService` và là **owner**; do đó nó có quyền gọi `shutdown()` và `shutdownNow()`. Không áp dụng quyền này lên executor dùng chung của toàn ứng dụng.
3. `submit` lấy `admissionLock` để kiểm tra `accepting` và gửi job **trong cùng vùng khóa**. Khi close lấy lock để đặt `accepting=false` và gọi `shutdown()`, không thể có việc mới chen vào **sau khi đã đóng intake**.
4. `compareAndSet(false,true)` chỉ chọn một thread sở hữu công việc close. Nếu không có bước này, hai thread có thể cùng đợi/kích hoạt force stop một cách khó kiểm soát.
5. `closeFinished` phục vụ **các caller đến sau**. Họ không coi việc close đã *bắt đầu* là nó đã *thành công*.
6. `awaitTermination(1, SECONDS)` đợi tối đa một giây cho dừng bình thường. Nếu không xong, `shutdownNow()` gửi yêu cầu dừng mạnh hơn rồi chờ thêm tối đa một giây.
7. Nếu task không kết thúc, `terminated=false` và `close()` ném `IllegalStateException`. **Có thể vẫn còn thread đang chạy**; exception là tín hiệu cần điều tra, không phải bằng chứng đã cleanup xong.
8. `closeFinished.countDown()` chạy trong `finally` ngay cả khi thread đóng bị interrupt hoặc lần thử close thất bại. Latch chỉ báo **lần đóng đầu đã có kết quả**; `terminated` mới là cờ mô tả kết quả được xác nhận.
9. Một caller khác gọi `close()` sau khi lần đầu thành công sẽ chờ latch (lúc này hoàn tất ngay), kiểm tra `terminated` và không gọi `shutdown()` lần nữa.
10. Nếu lần đầu thất bại, các lần sau **không tự coi đó là success**. Ví dụ này không tự động retry việc shutdown sau thất bại vì việc đó cần chính sách recovery/force-close riêng, không thể được giải quyết chỉ bằng một Boolean.

**Giới hạn thời gian cần hiểu cho chính xác:** mã sử dụng **hai phép `awaitTermination` có giới hạn 1 giây**, cộng thêm chi phí lấy lock, JVM scheduling và xử lý lỗi. Đây là ngân sách chờ theo từng bước, **không phải một bảo đảm thời gian tường tuyệt đối rằng method sẽ trả về trước đúng 2.000 ms** trên mọi máy và mọi resource. Nếu cần deadline tổng nghiêm ngặt hơn, tính phần thời gian còn lại bằng `System.nanoTime()` ở từng bước và kiểm soát cả thao tác I/O đồng bộ trong cleanup.

**Giới hạn concurrency của demo:** không gọi `close()` từ bên trong chính job đang chạy trên **executor mà close sẽ chờ**; như vậy có thể tự chờ chính thread của mình (pool starvation/self-join). Thông thường đường quản trị, lifecycle callback hoặc một thread điều phối độc lập thực hiện close.

### 7.3. Lớp Spring Boot đăng ký destroy method và gọi đóng ba lần

**`src/main/java/com/example/boundedclose/BoundedCloseApplication.java`:**

```java
package com.example.boundedclose;

import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BoundedCloseApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BoundedCloseApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println("MAIN: closing context");
        }

        System.out.println("MAIN: closed");
    }

    @Bean(destroyMethod = "close")
    GuardedJobResource guardedJobResource() {
        return new GuardedJobResource();
    }

    @Bean
    ApplicationRunner runDemo(GuardedJobResource resource) {
        return args -> {
            Future<String> job = resource.submit("job-7");

            System.out.println(
                    "RESULT: " + job.get(3, TimeUnit.SECONDS));

            resource.close(); // Lần 1: shutdown thật.
            resource.close(); // Lần 2: no-op an toàn sau thành công.

            try {
                resource.submit("late");
            } catch (RejectedExecutionException ex) {
                System.out.println("SUBMIT: rejected after close");
            }
        };
    }
}
```

Runner chờ một job hợp tác kết thúc trong tối đa ba giây **trước khi** thực hiện close. Sau đó, một lần close nữa diễn ra trong `ApplicationRunner`, và Spring sẽ gọi `close()` qua `destroyMethod` khi `ApplicationContext` đóng. Đó là ba yêu cầu đóng trên **cùng một object**, không tạo ba executor.

Điểm chủ ý của demo:

- Bean `GuardedJobResource` được Spring quản lý vì xuất phát từ `@Bean`.
- `@Bean(destroyMethod="close")` tường minh chỉ ra Spring phải gọi cleanup khi hủy bean singleton.
- `ApplicationRunner` có thể dùng bean sau khi context refresh.
- `WebApplicationType.NONE` giữ ví dụ là chương trình console, không mở Web server.
- `try-with-resources` trên **context** làm Spring thực thi đường đóng theo lifecycle; điều này khác việc tự đóng resource bằng Java thuần.
- Không khai báo thêm `@PreDestroy` trên `GuardedJobResource` vì không cần thêm một đường gọi close chỉ để “chắc ăn”.

### 7.4. Lệnh chạy

Trong project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có Wrapper, tạo project từ Spring Initializr hoặc sử dụng bản Gradle tương thích. Java 17+ là điều kiện của Spring Boot 3.3 và project này chọn Java 17.

### 7.5. Output quan trọng

Các dòng do code demo tự in theo thứ tự logic sau, bỏ qua banner/log Spring Boot/Gradle:

```text
RESULT: done:job-7
CLOSE: requested
CLOSE: terminated
CLOSE: already terminated
SUBMIT: rejected after close
MAIN: closing context
CLOSE: already terminated
MAIN: closed
```

Lý giải:

- Job đầu tiên hoàn tất và trả `done:job-7`.
- Lần close đầu đóng intake, yêu cầu `shutdown()`, xác nhận executor terminated.
- Lần close thứ hai chỉ xác nhận kết quả đã thành công, không shutdown lại.
- `submit("late")` bị từ chối vì `accepting=false`.
- Khi context đóng, Spring gọi lại destroy method; đó là lần close thứ ba và cũng không gây side effect phá hoại.
- `MAIN: closed` chỉ xuất hiện sau khi Spring `close()` hoàn tất.

**Nếu bạn bỏ lệnh `resource.close()` khỏi runner**, Spring vẫn có thể gọi `close()` một lần trong giai đoạn destroy nhờ `@Bean(destroyMethod="close")`. Khi đó các dòng log khác với ví dụ; hãy ghi rõ đã thay đổi kịch bản trước khi đối chiếu stdout.

## 8. Vì sao dùng một lock cho cả submit lẫn shutdown?

Một lỗi điển hình:

```java
if (!closed.get()) {
    executor.submit(job);
}
```

Giữa `get()` và `submit()`, một thread khác có thể chạy `shutdown()`. Kết quả là:

- Caller nghĩ resource còn mở nhưng `submit` ném `RejectedExecutionException`.
- Nếu dùng một queue/sentinel tự xây, job còn có thể được nhận sau dấu kết thúc và trở thành **lost work**.
- Trạng thái log không giải thích được số job đã nhận tại thời điểm đóng.

Với executor chuẩn, `RejectedExecutionException` là một đường lỗi hợp lệ và phải được xử lý; nó không nhất thiết là bug nếu xảy ra đúng lúc shutdown. Tuy nhiên, nếu hợp đồng ứng dụng yêu cầu “mọi job đã được chấp nhận trước close đều phải có cơ hội chạy” thì cần một **ranh giới nhận việc tuyến tính hóa (linearization point)**.

Trong demo, đó là `synchronized(admissionLock)`:

```text
Submit A:
  acquire lock -> kiểm tra accepting -> executor.submit -> release

Close B:
  acquire lock -> accepting=false -> executor.shutdown -> release

Submit C:
  acquire lock -> thấy accepting=false -> reject -> release
```

Do cả hai thao tác đồng bộ trên cùng lock, không thể có trường hợp **Submit A đã vượt kiểm tra nhưng chưa submit** trong khi Close B đã shutdown executor. Kết quả có thể khác tùy thread nào lấy lock trước, nhưng mỗi thứ tự quan sát được đều hợp lệ với hợp đồng.

Đây là thiết kế **thread-safe admission** cho ví dụ. Nó **không** tự giải quyết trạng thái business của task đã chấp nhận (ví dụ commit DB rồi crash trước khi trả Future). Với hệ thống bền vững, còn cần transaction, checkpoint, idempotency hoặc broker acknowledgement thích hợp.

## 9. Lần đóng đầu thất bại: idempotency phải giữ trạng thái thất bại

Điểm hay bị bỏ qua: nếu lần gọi `close()` đầu tiên thất bại, các lần gọi sau phải làm gì?

Có ba chính sách thường gặp:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| **Fail-closed, không tự retry** | Không nhận việc mới; báo rằng termination chưa xác nhận | Đóng lại có thể nguy hiểm, cần operator/owner khác xử lý |
| **Retry có kiểm soát** | Cho một caller mới thực hiện bước cleanup còn thiếu sau trạng thái FAILED | Cleanup có thể lặp an toàn, có deadline, không làm mất dữ liệu |
| **Escalate/force-close** | Dùng API cưỡng bức, ghi nhận unfinished work rồi chuyển xử lý sự cố | Hệ thống có chính sách rõ cho resource không hợp tác |

Demo phần 7 chọn chính sách thứ nhất. Khi timeout/interrupt, `closeFinished` vẫn được báo để caller đến sau **không chờ mãi**, nhưng `terminated=false` làm họ nhận exception. Đừng viết:

```java
if (closeStarted.get()) {
    return; // Sai nếu cần biết close đã thành công hay chưa.
}
```

Nếu dự án thật cần retry, phải mở rộng state machine để chỉ một caller retry tại một thời điểm, giữ nguyên quyền sở hữu tài nguyên, ngăn submit mới, lưu kết quả các nỗ lực và không lặp những bước không idempotent.

### Exactly-once cleanup có cần thiết không?

Nhiều thao tác đóng của Java như `ExecutorService.shutdown()` được thiết kế để lặp lại vô hại; một số API close khác cũng vậy. Nhưng **không phải tất cả bước cleanup nghiệp vụ đều idempotent**. Ví dụ:

- Ghi một bản ghi “job completed” khi đóng lần thứ hai có thể nhân đôi log nghiệp vụ.
- Commit cùng message offset lần thứ hai có thể sai tùy protocol.
- Xóa file hoặc trả tài nguyên về pool nhiều lần có thể gây lỗi.
- Gửi notification “workflow finished” nhiều lần có thể gây side effect bên ngoài.

Vì vậy **chỉ thực hiện phần side effect cần một lần dưới một owner**, còn các caller tới sau có thể quan sát kết quả. Đừng coi việc gọi nhiều lần một phương thức Java là giao dịch phân tán exactly-once.

## 10. Dùng một deadline tổng thay vì các timeout cộng dồn tùy ý

Demo dùng 1 giây graceful + 1 giây forced để dễ học. Với ứng dụng thực, có thể nhận một tổng ngân sách `Duration totalBudget` và chia theo thời gian **còn lại**.

Sơ đồ:

```text
closeStartedAt = System.nanoTime()
deadline = closeStartedAt + totalBudget
           |
           +-- ngừng intake
           +-- gửi graceful close
           +-- đợi tối đa min(graceBudget, remaining)
           +-- nếu chưa xong: force-close/cancel
           +-- đợi tối đa remaining
           +-- xác nhận result hoặc báo incomplete
```

Công thức minh họa:

```java
long deadline = System.nanoTime() + timeout.toNanos();
long remaining = Math.max(0L, deadline - System.nanoTime());

boolean stopped = executor.awaitTermination(
        remaining, TimeUnit.NANOSECONDS);
```

Đây là **snippet tích hợp**, cần `timeout` thuộc `Duration` hợp lệ và `executor`. Với một bộ đếm thực tế, cần kiểm soát trường hợp `Duration.toNanos()` overflow khi giá trị cực lớn và chọn một budget tối đa hợp lý. `System.nanoTime()` phù hợp để đo **thời gian đã trôi qua**, không dùng `LocalDateTime.now()` cho một deadline dễ bị ảnh hưởng bởi chỉnh đồng hồ hệ thống.

**Giới hạn không thể vượt qua:** timeout trên phương thức chờ không ép một thao tác đồng bộ bên dưới tự trả về. Nếu `driver.close()` tự treo vì I/O mà không hỗ trợ timeout, bạn có thể không thực thi được deadline chỉ bằng một `try/finally` đơn giản. Cần chọn API có timeout/cancellation thực sự, đôi khi phải dùng một thread điều phối riêng; nhưng thread bị treo vẫn là rủi ro cần xử lý.

### Ngân sách shutdown nhiều lớp

Ví dụ một deployment cho process 30 giây grace period:

```text
Orchestrator SIGTERM grace budget: 30s
    Spring phase stop group 1:   tối đa 8s
    Spring phase stop group 2:   tối đa 8s
    Resource close/destroy:      mục tiêu 5s
    Logging, network flush, JVM: dự phòng 4s
    Margin cho scheduling:       còn lại
```

Đây là **ví dụ phân bổ minh họa**, không phải mặc định Spring Boot. Một số bước có thể chạy song song, một số nối tiếp; phải đo thời gian thực. Điều cần học là **các timeout riêng không được vô tình cộng dồn vượt ngân sách process**.

Nếu orchestrator gửi `SIGKILL` sau 30 giây, việc cấu hình một timeout chờ 60 giây trong Java **không** khiến process có quyền sống thêm 30 giây.

## 11. Khi sử dụng SmartLifecycle.stop(Runnable) để dừng có thứ tự

Khi resource là một thành phần hoạt động lâu dài, cần dừng trước các dependency của nó, `SmartLifecycle` có thể thích hợp hơn chỉ dùng destroy method. Nó cung cấp:

- `start()` để bật thành phần theo lifecycle của context.
- `isRunning()` để phản ánh trạng thái.
- `getPhase()` để chọn thứ tự giữa nhiều lifecycle beans.
- `stop(Runnable callback)` để tiến hành shutdown không đồng bộ rồi **phát tín hiệu hoàn tất** cho `LifecycleProcessor`.

**Thứ tự phase:** start phase thấp trước cao; stop phase cao trước thấp. Ví dụ một consumer dùng writer có thể dùng phase 200 cho consumer, phase 100 cho writer để consumer dừng và drain trước writer.

Một khuôn mẫu logic:

```text
DefaultLifecycleProcessor:
  gọi Consumer.stop(callback)
        |
  Consumer ngừng intake
        |
  Consumer đợi/flush theo deadline trong worker shutdown
        |
  Consumer xác nhận đã kết thúc hoặc đã hoàn tất chính sách stop
        |
  callback.run()
        |
  Processor có thể tiếp tục phase writer
```

**Lỗi phổ biến:** gọi `callback.run()` ngay sau `executor.shutdown()`. Executor có thể vẫn đang chạy. Spring sẽ hiểu bước stop đã hoàn tất, dẫn đến writer/db client thuộc phase thấp hơn bắt đầu đóng trong khi consumer còn dùng.

Ngược lại, quên gọi callback khiến `LifecycleProcessor` đợi hết timeout phase. Callback là **nghĩa vụ** của implementation. Trong tình huống cleanup thất bại hoặc hết deadline, phải ghi nhận thất bại và có chính sách force-stop/recovery; callback cho biết bước stop được điều phối đã kết thúc, **không tự chứng nhận mọi dữ liệu được xử lý an toàn**.

### Phân biệt callback và Future

`stop(Runnable)` chỉ nhận một `Runnable`. Nếu thư viện đóng resource cung cấp `CompletionStage`:

```java
CompletionStage<Void> completion = client.stopAsync();

completion.whenComplete((ignored, error) -> {
    try {
        if (error != null) {
            recordFailure(error);
        }
    } finally {
        callback.run();
    }
});
```

Đây là **pseudocode tích hợp**, giả định `client` có `stopAsync()`, `recordFailure` tồn tại và `callback` đến từ `stop(Runnable)`. Khi dùng thật phải định nghĩa rõ “completion” của API bên thứ ba có nghĩa đã ngừng nhận việc, đã đóng socket hay chỉ đã gửi lệnh stop. **Chỉ nối callback vào future có semantics hoàn tất phù hợp**, không nối vào future báo “đã chấp nhận yêu cầu dừng”.

Một `SmartLifecycle` vẫn có thể có destroy callback làm cleanup dự phòng. Tuy nhiên, tránh double-close có side effect: dùng cùng state machine và đặt hợp đồng owner rõ, hoặc tổ chức stop làm phần nghiệp vụ còn destroy chỉ xác minh/đóng phần còn lại nếu cần.

## 12. @PreDestroy có thể bị gọi trong những hoàn cảnh nào?

`@PreDestroy` được gọi khi container hủy bean trong một vòng đời Spring hợp lệ. Tuy nhiên, đừng viết code với giả định:

- JVM luôn có đủ thời gian chạy shutdown hooks.
- Context luôn được refresh thành công trước khi phải cleanup.
- `@PreDestroy` là bước dừng duy nhất có thể xảy ra.
- Chỉ vì Spring gọi method destroy mà tất cả task của resource đã chấm dứt.
- Mọi scope đều được quản lý destroy giống singleton.

**Singleton:** container thường quản lý đầy đủ việc tạo và hủy singleton, nên destroy callbacks được gọi trong shutdown bình thường.

**Prototype:** container tạo prototype khi được yêu cầu nhưng không tự quản lý toàn bộ việc destroy từng instance giống singleton. Chủ sở hữu prototype thường cần tự cleanup.

**Lazy bean:** nếu singleton chưa từng được tạo, có thể không có instance để gọi destroy. Không dùng `@PreDestroy` của một bean chưa từng được tạo như đảm bảo duy nhất rằng một hành động shutdown toàn ứng dụng luôn chạy.

**Context không đóng đúng cách:** nếu process bị kill cưỡng bức hoặc crash, không có nghĩa callback Java được chạy. Các dữ liệu quan trọng cần cơ chế recovery, journaling/checkpoint/transaction phù hợp, không chỉ hy vọng `@PreDestroy` flush.

### Có nên gắn cả @PreDestroy và destroyMethod?

Với một bean duy nhất, việc khai báo nhiều cơ chế destroy có thể tạo nhiều callback. Spring có quy tắc chống trùng ở một số cấu hình, nhưng **không được coi tất cả tổ hợp tùy ý là bảo đảm chỉ gọi close một lần**. Cách đơn giản nhất là chọn một đường chính, như `@Bean(destroyMethod="close")` cho resource factory-created hoặc `@PreDestroy` cho component tự sở hữu tài nguyên.

Nếu thiết kế yêu cầu cả hai, method cleanup phải an toàn khi được gọi lặp và không phụ thuộc một thứ tự chưa kiểm chứng. Đừng thêm nhiều callback như “phòng hờ” mà không có test.

## 13. Thao tác đóng bị lỗi giữa chừng: nên dùng kết quả nào?

Không phải mọi resource có một trạng thái nhị phân “đã đóng/chưa đóng”. Xét một message consumer:

```text
STOP requested
  -> không nhận message mới
  -> chờ in-flight handlers
  -> ghi kết quả và commit transaction
  -> ack/checkpoint
  -> đóng kết nối
  -> xác nhận STOPPED
```

Lỗi có thể xảy ra sau khi đã ngừng intake nhưng trước khi ack. Lúc này tài nguyên có thể **không còn tiếp nhận**, nhưng dữ liệu nghiệp vụ vẫn chưa xác nhận. Nếu bạn trả “CLOSED” chỉ vì socket đã đóng thì thông tin không đủ.

Một mô hình kết quả rõ hơn:

| Kết quả | Ý nghĩa nên ghi nhận |
|---|---|
| `GRACEFUL_TERMINATED` | Tất cả công việc theo hợp đồng đã xong và tài nguyên đã dừng |
| `FORCED_TERMINATED` | Đã dừng nhưng có thể có công việc chưa hoàn tất, cần recovery |
| `TIMED_OUT_UNCONFIRMED` | Hết budget, chưa chứng minh tài nguyên đã ngừng |
| `INTERRUPTED` | Caller bị ngắt trong quá trình chờ; trạng thái resource cần kiểm tra |
| `FAILED` | Một bước cleanup ném lỗi; cần đánh giá phần đã hoàn thành |

Trong Java, `AutoCloseable.close()` trả `void`, nên có thể chọn **ném exception**, lưu kết quả ở object để phục vụ metrics, hoặc có phương thức `closeWithin(Duration)` trả một `CloseOutcome` riêng. Đừng biến những enum minh họa này thành API mặc định của Spring — chúng là **thiết kế ứng dụng**.

Nếu cần API trả kết quả, có thể thiết kế:

```java
public CloseOutcome closeWithin(Duration budget) {
    // Thực hiện stop theo state machine; trả kết quả có cấu trúc.
}
```

Đây là snippet minh họa, `CloseOutcome` là kiểu do project định nghĩa. Không cần ép một `AutoCloseable` Java thuần phải chứa mọi metadata vận hành; quan trọng là caller có đường quan sát kết quả thực tế.

## 14. Concurrency: hai caller cùng đóng có thể tạo race như thế nào?

### 14.1. Race “kiểm tra trước, thực hiện sau”

```java
if (!closed) {
    closeConnection();
    closed = true;
}
```

Hai thread có thể cùng vượt `if`. Với một file handle, socket hoặc pool có semantics close không an toàn khi lặp, việc này có thể gây lỗi. Dùng một state transition atomic hoặc lock để chọn một owner.

### 14.2. Race “đang đóng bị báo đã đóng”

```java
if (closing.compareAndSet(false, true)) {
    slowCleanup();
} else {
    return;
}
```

Đoạn trên có thể phù hợp nếu contract chỉ là “gửi yêu cầu đóng”, **không phù hợp** nếu contract là “khi method trả về, cleanup hoàn thành”. Khi cần completion, caller thứ hai phải chờ `CountDownLatch`/`CompletableFuture` với deadline và kiểm tra trạng thái kết quả.

### 14.3. Race giữa submit và close

Nếu `accepting` chuyển false không đồng bộ với thao tác enqueue, một task có thể được “chấp nhận” sau khi shutdown đã đi qua điểm kết thúc. Giải pháp là tạo **ranh giới atomic** cho quyết định nhận việc và trạng thái stop (như `admissionLock` trong demo), hoặc một queue/state machine được thiết kế sẵn cho semantics đó.

### 14.4. Chặn chính mình khi close

Một task đang chạy trong pool một worker gọi `pool.shutdown()` rồi `awaitTermination(...)` trên **cùng worker đó**. Nó đang chờ executor kết thúc nhưng executor không thể kết thúc cho tới khi chính task này trả về. Đây là **self-deadlock/starvation**. Đường close cần chạy trên thread điều phối bên ngoài hoặc sử dụng cơ chế non-blocking completion phù hợp.

### 14.5. Gọi callback nhiều lần

Nếu sử dụng `SmartLifecycle.stop(Runnable)` và viết:

```java
try {
    closeResource();
    callback.run();
} finally {
    callback.run();
}
```

thì khi cleanup thành công, callback chạy hai lần. Đây là **snippet lỗi cố ý**. Phải bảo đảm mỗi yêu cầu stop nhận tín hiệu completion đúng một lần và tại đúng mốc. Trong nhiều caller, có thể lưu một danh sách callbacks, nhưng cần đồng bộ để callback thêm lúc shutdown vừa kết thúc cũng được xử lý.

## 15. Xử lý interruption, cancellation và shutdownNow()

Java interruption là cơ chế **yêu cầu hợp tác**, không phải công tắc giết thread:

```java
try {
    boolean terminated =
            executor.awaitTermination(2, TimeUnit.SECONDS);

    if (!terminated) {
        executor.shutdownNow();
    }
} catch (InterruptedException ex) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Shutdown interrupted", ex);
}
```

Đây là snippet tích hợp, cần biến `executor` do caller sở hữu và đã gửi `shutdown()`. Việc khôi phục flag interrupt giúp caller cấp trên biết thread bị ngắt.

**Một số điều không nên khẳng định:**

- `shutdownNow()` không bảo đảm task chạy native I/O hoặc task bỏ qua interrupt sẽ dừng.
- `Future.cancel(true)` không rollback giao dịch database đã commit.
- Timeout của `Future.get(...)` chỉ kết thúc **lượt chờ của caller**, không tự dừng task.
- `CompletableFuture.cancel(...)` không nhất thiết ngắt tác vụ nguồn nếu không có tích hợp cancellation thực sự.
- Một thread bị interrupt có thể vẫn cần đóng socket/file để unblock I/O.
- Thread daemon không phải biện pháp thay thế cleanup đúng; JVM có thể thoát trong khi tác vụ chưa hoàn thành.

Nếu dữ liệu quan trọng, khi buộc force-stop phải ghi nhận in-flight tasks chưa xác nhận, checkpoint/offset và chính sách retry sau restart. Không log mọi thứ là “shutdown success” chỉ vì process sắp tắt.

## 16. Tài nguyên có thể đóng nhiều lần nhưng không nên tự động mở lại

Đóng lặp an toàn và **restartable** là hai vấn đề khác nhau.

Với resource dùng một lần:

```text
OPEN -> CLOSING -> CLOSED
              \-> FAILED_TO_CLOSE
```

Sau CLOSED, mọi `submit` đều bị từ chối. Đây là semantics của demo.

Nếu resource hỗ trợ chu kỳ:

```text
NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED
                 ^                        |
                 +------ restart ----------+
```

thì cần **định nghĩa rõ generation**: executor cũ đã terminated, queues và callbacks cũ không còn bị dùng, tài nguyên mới được tạo hoàn toàn, mọi caller biết họ đang gọi vào generation nào. Không chỉ set `closed=false` trên một `ExecutorService` đã shutdown: executor đó **không mở lại** được.

Trong Spring, một số `SmartLifecycle` components hỗ trợ start/stop lại. Nhưng `@Bean(destroyMethod="close")` theo ngữ nghĩa destroy của singleton không phải lời mời để tái sử dụng một object đã hủy. Nếu cần restart độc lập, thiết kế riêng phương thức quản lý vòng đời và state machine có generation counter.

## 17. Tương tác với dependency graph và thứ tự đóng

Một consumer có thể dùng writer, writer dùng database client:

```text
MessageConsumer -> BatchWriter -> DatabaseClient
```

Trong shutdown có trật tự, cần ngừng consumer nhận việc mới, drain in-flight handlers, flush writer rồi đóng database client. Nếu DatabaseClient đóng trước khi consumer flush xong, các tác vụ cuối có thể thất bại.

Có thể thiết kế phase:

```text
Start:
  DatabaseClient -> BatchWriter -> MessageConsumer

Stop:
  MessageConsumer -> BatchWriter -> DatabaseClient
```

`SmartLifecycle.getPhase()` hỗ trợ thứ tự start tăng dần, stop giảm dần. `@DependsOn` cũng có thể tác động thứ tự lifecycle/bean destruction. Nhưng chỉ đặt phase không tự bảo đảm **mỗi task được drain**; consumer vẫn phải kết nối callback vào completion thực, và mọi resource cần timeout tương ứng.

### Tránh đóng shared dependency từ consumer

Nếu `BatchWriter` và `MessageConsumer` đều dùng chung `DatabaseClient`, mỗi component không nên tự `databaseClient.close()` khi stop. Hãy để bean sở hữu database client đóng nó ở phase/destroy đúng thời điểm, sau khi các consumer đã dừng.

**Quy tắc reviewer:** không cho một service hủy dependency dùng chung chỉ vì nó được constructor-inject dependency đó. Tiêm dependency không chuyển quyền sở hữu tài nguyên.

## 18. Kiểm thử idempotency và deadline đúng cách

### 18.1. Test gọi close lặp

Với `GuardedJobResource`:

```java
GuardedJobResource resource = new GuardedJobResource();

resource.close();
resource.close();

try {
    resource.submit("not-allowed");
    throw new AssertionError("submit should reject after close");
} catch (RejectedExecutionException expected) {
    // Đúng: không nhận task mới.
}
```

Đây là snippet Java tích hợp ngoài Spring, cần import `RejectedExecutionException` và class `GuardedJobResource` từ ví dụ. Kiểm tra **không có exception ngoài dự kiến** ở lần close thứ hai và không nhận việc mới.

### 18.2. Test hai caller đóng đồng thời

Để có race rõ ràng, dùng `CountDownLatch` làm barrier chứ không dựa vào `Thread.sleep(5)`:

```java
GuardedJobResource resource = new GuardedJobResource();
CountDownLatch start = new CountDownLatch(1);
CountDownLatch completed = new CountDownLatch(2);

Runnable closeTask = () -> {
    try {
        start.await();
        resource.close();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new RuntimeException(ex);
    } finally {
        completed.countDown();
    }
};

new Thread(closeTask, "closer-a").start();
new Thread(closeTask, "closer-b").start();

start.countDown();

if (!completed.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("close callers did not finish in time");
}
```

Đây là một **snippet kiểm thử tích hợp**, cần imports `CountDownLatch` và `TimeUnit` và phương thức test có `throws Exception`. Nó cho phép hai thread tranh nhau quyền đóng. **Giới hạn:** exception trong worker thread không tự được ném lại trong test thread. Trong JUnit production nên thu exception vào một cấu trúc thread-safe hoặc dùng `Future.get`/`CompletableFuture.allOf` để assert đúng từng caller. Không chỉ kiểm tra latch rồi suy luận các worker chắc chắn đều thành công.

### 18.3. Test deadline

Tạo một task hợp tác ngủ 500 ms, đóng với budget 2 giây: kết quả bình thường phải terminated. Sau đó thử task phản ứng chậm hơn grace period nhưng chấp nhận interruption: có thể thấy đường force-stop, song phải kiểm tra nó thật sự kết thúc.

Không dùng một task cố tình vòng lặp vô hạn và bỏ qua interruption trong cùng JVM phát triển rồi chờ chương trình tự thoát. Một worker non-daemon như vậy có thể giữ JVM sống. Nếu cần stress test kiểu này, dùng process test riêng và thời gian giám sát bên ngoài, có cơ chế kill an toàn.

### 18.4. Test lỗi sau khi một phần cleanup đã chạy

Giả định đóng resource gồm ba bước: flush, close socket, release lock. Cố ý làm bước 2 ném exception và xác định:

- Bước 1 có hoàn tất chưa?
- Bước 3 có được chạy trong cleanup dự phòng không?
- State là CLOSED hay FAILED_TO_CLOSE?
- Caller thứ hai có nhận cùng kết quả không?
- Có tạo lại socket/worker ngoài ý muốn không?
- Có log/metric cho tài nguyên còn lại không?

Đây là phần quan trọng hơn việc chỉ kiểm tra `close()` không ném khi mọi thứ tốt đẹp.

### 18.5. Integration test với Spring context

Trong integration test, tạo context chứa bean `@Bean(destroyMethod="close")`, để runner (hoặc test code) gọi `close()` một lần rồi đóng context. Đo số lần cleanup thực tế bằng một `AtomicInteger` được tăng tại **điểm side effect thật**, không chỉ đếm số lần method close được gọi. Hợp đồng là “cleanup thực tế một lần”, còn method có thể được gọi nhiều lần.

## 19. Monitoring và điều hành sự cố shutdown

Khi ứng dụng chỉ log `Closing resources...` mà không log kết quả, rất khó phân biệt đóng sạch với timeout. Nên quan sát:

- Số lần yêu cầu close và số lần cleanup thật sự thực hiện.
- Thời gian dừng nhận việc mới.
- Thời gian drain in-flight tasks và số task còn lại khi hết budget.
- Tình trạng graceful/forced/timed-out/interrupted.
- Số connection hoặc threads còn chạy sau close.
- Các exception phát sinh ở destroy method/`SmartLifecycle`.
- Thời gian từng phase so với shutdown grace period của process.
- Tác động của restart: job chưa ack được redeliver không, có xử lý lặp không.

Trong Spring Boot có Micrometer/Actuator nếu dự án đã cấu hình. Nhưng không tự giả định rằng mọi tài nguyên tùy biến đã có metrics; application cần chủ động định nghĩa counter/timer phù hợp. Tránh log secret, payload nhạy cảm hay toàn bộ nội dung task trong shutdown trace.

### Tiêu chí thành công có ý nghĩa vận hành

Một thông báo “shutdown complete” nên dựa trên **tiêu chí đo được** như:

```text
acceptingNewWork = false
inFlightCount = 0
executor.isTerminated() = true
writerFlushCompleted = true
connectionClosed = true
callbackSignalled = true (nếu dùng SmartLifecycle)
```

Đây là **ví dụ trạng thái cần kiểm tra**, không phải các field mặc định của Java/Spring. Trong hệ thống đã chọn forced shutdown, tiêu chí có thể khác: phải báo rõ unfinished tasks và cơ chế recovery, thay vì ghi cùng một nhãn “graceful success”.

## 20. Những lỗi điển hình

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai thread cùng gọi close gây lỗi | Check-then-act trên `boolean closed` | Chọn owner bằng lock/CAS, chia sẻ completion |
| Lần close thứ hai trả về trước lần đầu | Chỉ kiểm tra cờ “đã bắt đầu” | Dùng latch/future cho completion, có deadline |
| `shutdown()` xong nhưng thread vẫn chạy | `shutdown` không chờ task hoàn tất | `awaitTermination` và kiểm tra `isTerminated` |
| `shutdownNow()` xong nhưng worker vẫn sống | Task bỏ qua interrupt hoặc kẹt I/O | Resource timeout, force-close thật, báo unconfirmed |
| Đóng context bị treo lâu | Destroy callback chờ I/O/lock vô hạn | Deadline cấp tài nguyên và monitoring |
| Đặt `spring.lifecycle.timeout-per-shutdown-phase` mà `@PreDestroy` vẫn treo | Timeout chỉ dành cho lifecycle phases | Thêm thời hạn trong cleanup của destroy callback |
| Vừa đóng tài nguyên ở runner vừa để Spring destroy | Hai đường close trên cùng bean | Ưu tiên một owner; API close phải idempotent nếu thực sự lặp |
| Đóng executor dùng chung từ service consumer | Nhầm injection với ownership | Để bean cấp phát executor quản lý shutdown |
| Lỗi hủy bean nhưng cờ CLOSED=true | Set cờ thành công quá sớm | Tách CLOSING/CLOSED/FAILED |
| Context đóng mà vẫn nhận job mới | Không đồng bộ submit với stop | Admission gate/cơ chế trạng thái atomic |
| Callback `stop(Runnable)` gọi sớm | Gọi sau khi gửi yêu cầu thay vì sau drain | Nối callback với completion có semantics phù hợp |
| Callback không bao giờ được gọi | Bỏ nhánh lỗi hoặc quá thời hạn không có kết thúc | Bảo đảm đường kết thúc/callback, báo failure |
| Worker tự close chính pool và chờ | Self-deadlock | Dùng coordinator thread khác |
| `@PreDestroy` trên prototype không chạy | Spring không quản lý đầy đủ destroy prototype | Owner prototype tự cleanup |
| `kill -9` làm mất dữ liệu | Không có đường shutdown có trật tự | Durability, transaction, checkpoint, restart recovery |
| Thêm timeout thật lớn để “an toàn” | Tổng budget vượt orchestration grace | Phân bổ deadline đo được cho từng tầng |
| Đóng lặp tạo trùng audit/message | Cleanup có side effect không idempotent | Dedupe/owner một lần, lưu kết quả |
| Executor đã shutdown nhưng code cố restart | `ExecutorService` không có reopen API | Tạo generation/resource mới rõ ràng |

### Checklist review

- [ ] Xác định đúng resource owner; dependency dùng chung không bị đóng từ consumer.
- [ ] Có định nghĩa OPEN, CLOSING, CLOSED, FAILED_TO_CLOSE.
- [ ] Có điểm chặn việc mới trước khi bắt đầu drain.
- [ ] Có đồng bộ giữa admission và shutdown.
- [ ] Chỉ một caller thực hiện cleanup; caller khác biết kết quả.
- [ ] Close lặp khi thành công không gây side effect trùng.
- [ ] Close sau thất bại không giả vờ thành công.
- [ ] Có timeout/graceful/forced rõ ràng theo từng tài nguyên.
- [ ] Không nhầm `shutdown()`, `shutdownNow()`, `isShutdown()` với `isTerminated()`.
- [ ] Xử lý `InterruptedException`, phục hồi cờ interrupt khi thích hợp.
- [ ] Không chờ termination của pool từ chính worker trong pool ấy.
- [ ] Nếu dùng SmartLifecycle, callback sau stop và phase phù hợp.
- [ ] Không trông chờ timeout của Spring để chặn mọi destroy method.
- [ ] Có test close hai lần, close đồng thời, timeout và lỗi cleanup.
- [ ] Có monitoring cho forced/timeout/unfinished work.
- [ ] Shutdown budget của JVM nhỏ hơn grace period của hạ tầng, có dự phòng.

## 21. Bài thực hành

Dùng project phần 7, mỗi lần chỉ thay đổi một điều rồi khôi phục trước khi thử tiếp.

**Bài A — đóng một lần, nhiều lần:** chạy nguyên bản. Đếm ba lời gọi `close()` (hai từ runner, một từ Spring destroy), nhưng chỉ một lần xuất hiện `CLOSE: requested` và `CLOSE: terminated`.

**Bài B — thử nhận việc sau đóng:** xác nhận `submit("late")` bị từ chối. Vì method `submit` và `close` dùng chung `admissionLock`, không có job mới được chấp nhận sau khi intake bị đóng.

**Bài C — đóng đồng thời:** sử dụng hai thread và latch như phần 18. Đặt một job hợp tác đang chạy để caller thứ hai có cơ hội vào lúc `CLOSING`; kiểm tra nó đợi kết quả thay vì trả thành công tức thì.

**Bài D — hết grace period:** đổi thời gian `Thread.sleep(100)` thành khoảng dài hơn 1 giây trong một bản thử. Xem nhánh `shutdownNow()` và yêu cầu interrupt; giải thích sự khác biệt giữa “force request” và “termination confirmed”.

**Bài E — task không tuân thủ interrupt:** chỉ mô phỏng trong process test cô lập có watchdog. Quan sát `awaitTermination` có thể trả false ngay cả sau `shutdownNow()`. Giải thích vì sao không thể hứa cleanup thành công chỉ bằng timeout.

**Bài F — bỏ đồng bộ admission:** cố ý chuyển kiểm tra `accepting` và `executor.submit` ra khỏi lock rồi dùng barrier/latch tạo race với close. Quan sát đường `RejectedExecutionException` và xác định điều kiện cần bảo vệ.

**Bài G — trạng thái đóng thất bại:** trong bản test, giả lập một close không được xác nhận terminated. Yêu cầu thứ hai phải biết thất bại, không được trả về như thể CLOSED.

**Bài H — so sánh destroy hook:** đưa resource vào một bean `@Component` tự sở hữu và dùng `@PreDestroy`, sau đó so với cách `@Bean(destroyMethod="close")`. Chọn **một đường chính** cho mỗi phiên bản demo để không vô tình thêm callback trùng.

**Bài I — thêm SmartLifecycle:** tạo một consumer phase 200 phụ thuộc writer phase 100. Ngừng intake, drain theo deadline và chỉ gọi callback sau khi consumer kết thúc; xác nhận writer stop sau callback hoặc sau timeout nếu đã cố tình bỏ callback.

**Bài J — thiết kế production:** với một message consumer, hãy ghi hợp đồng: ai sở hữu broker client, executor và DB pool; message nào đang in-flight; ack lúc nào; cách dừng nhận việc; graceful/forced deadline; số message chưa ack; chính sách retry sau restart và metrics cảnh báo.

### Câu hỏi tự đánh giá

1. Vì sao một `AtomicBoolean` đánh dấu `closeStarted=true` chưa đủ chứng minh resource đã CLOSED?
2. `shutdown()` có đợi task đã submit hoàn tất không?
3. `shutdownNow()` có bảo đảm giết được task bỏ qua interruption không?
4. Tại sao caller thứ hai nên biết completion của caller đầu nếu contract là close đồng bộ?
5. Nếu tài nguyên thuộc bean hạ tầng dùng chung, một service được inject nó có quyền gọi `shutdown` không?
6. Vì sao `spring.lifecycle.timeout-per-shutdown-phase` không ràng buộc mọi `@PreDestroy`?
7. Điểm tuyến tính hóa giữa `submit` và `close` trong demo nằm ở đâu?
8. Nếu lần close đầu hết deadline, lần close thứ hai nên trả “đã xong” hay báo trạng thái không xác nhận?
9. Khi nào nên chọn `SmartLifecycle.stop(Runnable)` thay vì chỉ `@Bean(destroyMethod="close")`?
10. Vì sao đóng resource sạch ở một JVM không tự bảo đảm không mất/trùng message khi process crash?

## 22. Kết luận

Thiết kế đóng tài nguyên nhiều lần an toàn bắt đầu bằng **ownership đúng, state machine rõ và kết quả completion được chia sẻ**. Một caller giành quyền đóng; những caller khác không chạy cleanup trùng và không coi `CLOSING` là `CLOSED`. Ranh giới nhận task phải được đồng bộ với shutdown. Thời hạn đóng phải có ngân sách cụ thể, có đường graceful rồi forced, và báo lỗi khi không thể xác nhận resource thực sự đã dừng.

Trong Spring Boot, sử dụng `@Bean(destroyMethod="close")`, `@PreDestroy` hoặc `SmartLifecycle` **theo trách nhiệm và mức điều phối cần thiết**, không cộng dồn annotation như cách sửa race. `spring.lifecycle.timeout-per-shutdown-phase` hữu ích cho lifecycle phases, nhưng **không giới hạn tự động mọi destroy callback**. Và khi tắt JVM cưỡng bức, chỉ có durability/recovery đúng mới bảo vệ được công việc còn dở.

**Một nguyên tắc để nhớ:** **đóng lặp an toàn không đồng nghĩa đóng không lỗi; đóng có timeout không đồng nghĩa đã dừng; đã dừng resource không đồng nghĩa mọi giao dịch nghiệp vụ đã được xác nhận.**

### Tài liệu chính thức

- Spring Boot 3.3 — Graceful Shutdown và `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Framework 6.1 — Bean lifecycle/destroy và suy luận `close`/`shutdown` cho bean: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Framework 6.1 — `@Bean` Javadoc, `destroyMethod`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html
- Spring Framework 6.1 — `SmartLifecycle` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Java SE 17 — `ExecutorService` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `ThreadPoolExecutor`, `shutdown`/`shutdownNow`/`awaitTermination`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html