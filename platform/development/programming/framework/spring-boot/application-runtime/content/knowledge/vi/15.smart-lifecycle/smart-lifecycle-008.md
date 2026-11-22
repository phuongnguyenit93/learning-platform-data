# Dừng bất đồng bộ bằng stop(Runnable) và nghĩa vụ gọi callback trong SmartLifecycle

## 1. Vấn đề cần giải quyết: dừng tài nguyên không phải lúc nào cũng tức thời

Một ứng dụng Spring Boot có thể tạo các thành phần hoạt động lâu dài như message consumer, bộ nhận sự kiện, bộ xử lý nền, bộ đệm ghi, kết nối streaming hoặc worker pool. Khi ứng dụng đóng `ApplicationContext`, nhiều thành phần không thể dừng tức thì; chúng cần:

- Ngừng nhận công việc mới.
- Cho công việc đang xử lý hoàn tất trong một khoảng thời gian hợp lý.
- Flush dữ liệu hoặc xác nhận message cuối cùng.
- Đóng connection, thread hoặc executor.
- Thông báo rằng **giai đoạn dừng đã kết thúc** để Spring có thể tiếp tục shutdown các thành phần phụ thuộc.

Spring Framework cung cấp giao diện `SmartLifecycle` cho các bean cần điều khiển vòng đời và thứ tự start/stop. Phương thức đặc biệt:

```java
void stop(Runnable callback);
```

cho phép triển khai **dừng bất đồng bộ**: yêu cầu dừng bắt đầu ở luồng đóng context, trong khi một luồng khác có thể tiếp tục xử lý cleanup. Khi shutdown hoàn tất, bean **phải gọi `callback.run()`**.

Đây là hợp đồng mấu chốt của bài:

> **Callback là tín hiệu hoàn thành dành cho `LifecycleProcessor`. Không gọi callback thì Spring có thể chờ tới hết timeout của phase; gọi callback quá sớm thì Spring có thể đóng các dependency trong khi bean vẫn còn hoạt động.**

Nó **không** phải callback để thực hiện cleanup hộ bạn. Cleanup là trách nhiệm của bean; callback chỉ xác nhận với bên điều phối rằng bước stop của bean đã kết thúc.

## 2. SmartLifecycle khác Lifecycle ở điểm nào?

Trong Spring Framework 6.1, `SmartLifecycle` mở rộng hai giao diện:

```java
public interface SmartLifecycle extends Lifecycle, Phased {
    // Các phương thức được cung cấp bởi SmartLifecycle và interface cha:
    boolean isAutoStartup();
    int getPhase();
    void stop(Runnable callback);
    // start(), stop(), isRunning() đến từ Lifecycle.
}
```

Đây là **sơ đồ rút gọn các chữ ký quan trọng**, không phải đoạn mã để khai báo lại những interface có sẵn trong thư viện Spring.

| Thành phần | Ý nghĩa thực tế |
|---|---|
| `start()` | Bắt đầu thành phần, ví dụ mở consumer hoặc worker |
| `isRunning()` | Trả về trạng thái đang chạy để lifecycle processor xác định việc start/stop phù hợp |
| `stop()` | Phương thức dừng của `Lifecycle`, không có callback |
| `stop(Runnable callback)` | Phương thức dừng có tín hiệu hoàn thành; được lifecycle processor dùng cho `SmartLifecycle` |
| `isAutoStartup()` | Có tự khởi động khi context refresh hay không; mặc định `true` |
| `getPhase()` | Xác định thứ tự start/stop giữa các thành phần; mặc định của `SmartLifecycle` là `Integer.MAX_VALUE` |

**Điểm dễ sai nhất:** trong quy trình dừng do `DefaultLifecycleProcessor` điều phối, Spring **gọi `stop(Runnable)`**, **không gọi `stop()`** cho một implementation của `SmartLifecycle`. Nếu chỉ viết logic đóng tài nguyên trong `stop()` và override `stop(Runnable)` mà không gọi logic đó, tài nguyên có thể không được dừng.

Ngược lại, nếu **không override `stop(Runnable)`**, implementation mặc định trong `SmartLifecycle` gọi `Lifecycle.stop()` rồi ngay lập tức gọi callback trên luồng hiện tại. Đây là hành vi hữu ích khi dừng **đồng bộ**, nhưng **không phù hợp** nếu `stop()` chỉ gửi lệnh cho một worker bất đồng bộ rồi trả về trước khi worker thật sự dừng.

## 3. Vì sao Spring cần callback?

Trong một context có nhiều `SmartLifecycle` beans, Spring không thể chỉ gọi một phương thức `void` rồi đoán tài nguyên đã dừng. Với dừng bất đồng bộ, `stop(Runnable)` có thể **trả về trước khi công việc cleanup xong**.

Sơ đồ:

```text
Thread đóng ApplicationContext          Thread cleanup của bean
                |                                  |
                | gọi stop(callback)               |
                +--------------------------------->|
                |                                  | ngừng intake
                | stop(...) trả về                 | đợi tác vụ dang dở
                |                                  | flush & close
                | DefaultLifecycleProcessor       |
                | chờ callback trong phase        |
                |                                  |
                |<---------------------------------+
                |       callback.run()
                |
                | xác nhận bean đã dừng
                | tiếp tục các phase thấp hơn
                v
          context đóng
```

`LifecycleProcessor` dùng callback để biết khi nào **một bean đã hoàn tất lệnh dừng**, từ đó phối hợp nhiều bean trong **cùng phase** và quyết định có thể chuyển sang phase tiếp theo hay chưa. Một phase có thể có nhiều bean, nên tổng thời gian dừng của nhóm không nhất thiết bằng tổng thời gian từng bean; các bước bất đồng bộ có thể chồng lấp.

Không nên hiểu callback như Java `Future` hay `CompletionStage`: chữ ký chỉ là `Runnable`. Bean có thể dùng thread, callback của thư viện I/O hoặc `CompletableFuture` nội bộ, nhưng cuối cùng phải gọi **chính `Runnable` do Spring cung cấp**.

### Hai lỗi đối nghịch

**Lỗi A — không bao giờ gọi callback:**

```java
@Override
public void stop(Runnable callback) {
    worker.shutdown();
    // Quên callback.run().
}
```

Đây là snippet **sai cố ý**, giả định có biến `worker`. Dù worker đã dừng, lifecycle processor vẫn có thể chờ đến khi phase timeout. Nó không có cách biết rằng stop đã hoàn tất.

**Lỗi B — gọi callback ngay khi vừa gửi yêu cầu dừng:**

```java
@Override
public void stop(Runnable callback) {
    worker.shutdown(); // Yêu cầu ngừng nhận công việc, chưa chắc worker đã kết thúc.
    callback.run();    // Sai nếu vẫn còn công việc đang chạy.
}
```

Nếu `worker` là `ExecutorService`, `shutdown()` **chỉ yêu cầu đóng có trật tự**; nó không đợi những task đã nhận hoàn thành. Gọi callback ngay sau `shutdown()` đánh dấu kết thúc **quá sớm**. Các dependency ở phase thấp hơn có thể bắt đầu bị đóng trong khi task của worker vẫn truy cập chúng.

**Điều đúng:** gọi callback **sau khi việc dừng thực tế hoàn thành**, hoặc sau khi một quy trình kết thúc có kiểm soát (ví dụ timeout nội bộ kèm force-close và xác nhận trạng thái). Nếu không thể dừng sạch, phải log/metric trạng thái thất bại; không gọi callback rồi tuyên bố mọi dữ liệu đã được xử lý an toàn.

## 4. Thứ tự phase: start tăng dần, stop giảm dần

`SmartLifecycle` kế thừa `Phased`. Spring Framework sử dụng `getPhase()` để sắp xếp những thành phần lifecycle được điều phối.

```text
START (phase tăng dần):
  phase -100 -> phase 0 -> phase 100 -> phase 200

STOP (phase giảm dần):
  phase 200 -> phase 100 -> phase 0 -> phase -100
```

Nếu component **Consumer** cần **Writer** hoạt động trước khi nhận message:

- Writer có `getPhase() = 100`.
- Consumer có `getPhase() = 200`.
- Khi start, Writer được khởi động **trước** Consumer.
- Khi stop, Consumer được yêu cầu dừng **trước** Writer.
- Khi Consumer dùng `stop(Runnable)` bất đồng bộ, Spring đợi callback của nhóm phase 200 (hoặc timeout) trước khi đi tới nhóm phase 100 chứa Writer.

Cách sắp xếp này giúp tránh đóng Writer khi Consumer còn cần ghi dữ liệu ở giai đoạn drain.

| Phase | Thành phần | Start | Stop |
|---|---|---|---|
| 100 | Writer | Trước | Sau |
| 200 | Consumer | Sau | Trước |

**Các nuance cần nhớ:**

1. `getPhase()` của `SmartLifecycle` **mặc định là `Integer.MAX_VALUE`**, không phải 0. Vì vậy các bean SmartLifecycle dùng mặc định thường start rất muộn và stop rất sớm so với các `Lifecycle` ở phase 0.
2. Một bean chỉ triển khai `Lifecycle` mà **không** triển khai `SmartLifecycle` được lifecycle processor xử lý như phase **0**.
3. Giữa các bean **cùng một phase**, thứ tự không phải hợp đồng ổn định. Nếu có phụ thuộc thật, đừng chỉ dựa vào cùng phase.
4. Một quan hệ `depends-on` tường minh có thể **ưu tiên hơn phase**: bean phụ thuộc sẽ start sau dependency và stop trước dependency.
5. `@Order` của một bean không đồng nghĩa `getPhase()`; không dùng thứ tự `@Order` làm thay thế cho lifecycle phase.
6. Một phase có **timeout chung cho nhóm**, không phải mỗi bean trong nhóm có một bộ đếm độc lập.

## 5. Khi nào callback phải chạy?

Nguyên tắc đủ chặt để thiết kế một stop bất đồng bộ:

- Nếu bean **đã dừng**, không có gì phải đợi, hãy gọi callback để hoàn thành yêu cầu.
- Nếu bean **đang chạy**, phát lệnh dừng và làm cleanup.
- Nếu cleanup **đã hoàn tất**, cập nhật trạng thái `isRunning()` phù hợp rồi gọi `callback.run()`.
- Nếu có **exception**, xử lý lỗi theo chính sách: cố đóng tài nguyên/force close nếu cần, ghi nhận thất bại, nhưng không bỏ quên việc báo hoàn tất cho lifecycle processor khi quy trình stop thực sự đã kết thúc.
- Nếu không thể khởi chạy tác vụ bất đồng bộ (ví dụ executor từ chối task), phải có **đường fallback**; tuyệt đối không để callback bị quên trong một nhánh code.

Trong một lần gọi `stop(Runnable)`, nên tổ chức logic để **callback được thực thi chính xác một lần** và **sau khi kết thúc stop**. Spring không nên nhận tín hiệu “hoàn tất” hai lần cho cùng yêu cầu dừng.

**Đừng nhầm hai loại hoàn tất:**

- “Đã gửi lệnh hủy”: `shutdown()`, `cancel()`, `closeAsync()` được gọi.
- “Đã dừng”: task đã rời vòng xử lý, tài nguyên đã được đóng hoặc kết thúc theo chính sách timeout/force-close.

Chỉ mốc thứ hai thích hợp để gọi callback nếu mục tiêu là shutdown có trật tự.

## 6. Ví dụ chạy được: hai SmartLifecycle bean và một stop bất đồng bộ

Ví dụ dùng **Java 17+, Spring Boot 3.3.x**, không cần Web server hay database. Có hai bean lifecycle:

- **WriterLifecycle** ở phase 100: dừng đồng bộ.
- **AsyncConsumerLifecycle** ở phase 200: dừng bất đồng bộ trên một thread mới, mô phỏng 300 ms drain.

Chúng không xử lý dữ liệu thật. Mục tiêu là nhìn thấy việc phase 100 **chưa được dừng** cho tới khi phase 200 **gọi callback**.

### 6.1. Cấu trúc project

```text
smart-lifecycle-stop-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/shutdown/
    │   ├── ShutdownDemoApplication.java
    │   ├── WriterLifecycle.java
    │   └── AsyncConsumerLifecycle.java
    └── resources/
        └── application.properties
```

**`settings.gradle`:**

```groovy
rootProject.name = 'smart-lifecycle-stop-demo'
```

**`build.gradle`** (Groovy DSL):

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

**`src/main/resources/application.properties`:**

```properties
spring.application.name=smart-lifecycle-stop-demo

# Giới hạn chờ hoàn thành từng nhóm phase khi shutdown.
spring.lifecycle.timeout-per-shutdown-phase=3s
```

Property timeout ở đây chọn **3 giây** để dài hơn nhiều so với thời gian mô phỏng 300 ms. Không nên chọn timeout nhỏ hơn thời gian cleanup dự kiến rồi coi cảnh báo timeout là lỗi của Spring.

### 6.2. WriterLifecycle: phase 100, dừng đồng bộ

**`src/main/java/com/example/shutdown/WriterLifecycle.java`:**

```java
package com.example.shutdown;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class WriterLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("START writer (phase 100)");
        }
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public void stop(Runnable callback) {
        try {
            if (running.compareAndSet(true, false)) {
                System.out.println("STOP writer (phase 100)");
            }
        } finally {
            // Dừng đồng bộ: cleanup đã hoàn tất ở đây.
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

Đây là một implementation hoàn chỉnh và tự chứa. `@Component` giúp Spring Boot đăng ký nó thành bean trong phạm vi component scan.

Các điểm quan trọng:

- `start()` thiết lập trạng thái running.
- `stop()` và `stop(Runnable)` đều có thể dùng, nhưng **lifecycle processor ưu tiên gọi phiên bản callback**.
- Dừng Writer hoàn thành ngay trong caller thread, nên có thể gọi callback trước khi phương thức trả về.
- `AtomicBoolean` giúp thay đổi trạng thái có visibility phù hợp nếu callback/worker ở thread khác; không phải bằng chứng ứng dụng có toàn bộ cơ chế thread-safety chỉ nhờ một field.
- `getPhase()` trả 100, thấp hơn phase 200 của Consumer.

### 6.3. AsyncConsumerLifecycle: phase 200, dừng bất đồng bộ

**`src/main/java/com/example/shutdown/AsyncConsumerLifecycle.java`:**

```java
package com.example.shutdown;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public final class AsyncConsumerLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("START consumer (phase 200)");
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!running.get()) {
            callback.run();
            return;
        }

        // Đây chỉ là mô phỏng drain; project thật phải đợi resource thật.
        Thread shutdownWorker = new Thread(() -> {
            try {
                System.out.println("STOP consumer: draining...");
                Thread.sleep(300);
                System.out.println("STOP consumer: drained");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                // Demo không có I/O thật; thực tế cần force-close tài nguyên.
                System.err.println("STOP consumer: interrupted");
            } finally {
                running.set(false);
                System.out.println("STOP consumer: callback");
                callback.run();
            }
        }, "consumer-drainer");

        try {
            shutdownWorker.start();
        } catch (RuntimeException | Error ex) {
            // Nếu không thể tạo worker, demo không có resource thật cần đóng.
            running.set(false);
            callback.run();
            throw ex;
        }
    }

    @Override
    public void stop() {
        // Dùng khi có caller gọi Lifecycle.stop() trực tiếp.
        // DefaultLifecycleProcessor dùng stop(Runnable) ở trên.
        CountDownLatch completed = new CountDownLatch(1);
        stop(completed::countDown);

        try {
            if (!completed.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Manual stop did not complete within 2 seconds");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Manual stop interrupted", ex);
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 200;
    }
}
```

Đọc từng phần:

1. `isRunning()` phản ánh trạng thái running ban đầu và sau khi cleanup xong.
2. Nếu `stop(Runnable)` được gọi khi bean đã dừng, callback được gọi ngay để không tạo một yêu cầu chờ không cần thiết.
3. Thread mới thực hiện một tác vụ mô phỏng drain trong 300 ms. `stop(Runnable)` **không đợi 300 ms** mới trả về.
4. `finally` đặt `running=false` và gọi `callback.run()`, nên callback vẫn được thực thi nếu đoạn mô phỏng bị interrupt.
5. Nếu không thể `Thread.start()`, nhánh catch tránh bỏ sót callback. Demo không có I/O thật; trong sản phẩm thực phải có fallback **đóng resource thực tế**, ghi rõ lỗi và bảo đảm trạng thái không bị khai báo sai.
6. `stop()` không có callback được triển khai riêng để hỗ trợ caller trực tiếp, nó đợi tối đa 2 giây cho demo. Đây **không** phải phương thức mà Spring gọi trong lifecycle shutdown của bean SmartLifecycle.
7. `getPhase()=200` khiến Consumer được start sau Writer và được yêu cầu stop trước Writer.

**Giới hạn có chủ đích của ví dụ:** mã này minh họa **một lần đóng context** và không phải một framework xử lý nhiều stop requests đồng thời. Nếu hai thread gọi `stop(Runnable)` cùng lúc khi `running=true`, hai worker có thể được tạo. Ứng dụng production cần cơ chế idempotency, ví dụ một state machine hoặc một shared completion future và đăng ký callbacks của từng caller để tránh chạy cleanup nhiều lần.

**Một nuance về lỗi:** trong ví dụ, `finally` đánh dấu kết thúc sau khi mô phỏng drain; khi có `InterruptedException`, đó chỉ là **kết thúc công việc demo**, không có dữ liệu thật. Trong hệ thống thật, việc bị interrupt **không tự chứng minh đã flush hết dữ liệu**; cần thực hiện force-close hoặc ghi lại tình trạng mất/unfinished work trước khi báo hoàn tất.

### 6.4. Lớp Spring Boot chạy demo và đóng context

**`src/main/java/com/example/shutdown/ShutdownDemoApplication.java`:**

```java
package com.example.shutdown;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ShutdownDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShutdownDemoApplication.class);

        // Không tạo Web server, dễ quan sát việc đóng context.
        application.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            System.out.println("MAIN: closing context");
        }

        System.out.println("MAIN: context closed");
    }

    @Bean
    ApplicationRunner startupReport() {
        return args -> System.out.println("RUNNER: application started");
    }
}
```

`try-with-resources` gọi `context.close()` khi rời khối. Spring thực hiện quy trình đóng context, trong đó `LifecycleProcessor` dừng các lifecycle beans theo phase. Với ứng dụng non-web dùng để học, việc đóng ngay sau `run` là có chủ đích. Với một Web service cần tiếp tục phục vụ HTTP, **không được đóng context ngay sau khi startup** như ví dụ này.

### 6.5. Chạy

Khi project đã có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có Wrapper, có thể tạo skeleton bằng Spring Initializr hoặc tạo Wrapper với Gradle phù hợp. Viết `build.gradle` đơn lẻ không tự sinh ra `gradlew` hoặc `gradlew.bat`.

### 6.6. Kết quả dự kiến

Bỏ qua banner và những log thông thường từ Spring Boot/Gradle, các dòng do **mã Java của demo** in sẽ theo thứ tự logic:

```text
START writer (phase 100)
START consumer (phase 200)
RUNNER: application started
MAIN: closing context
STOP consumer: draining...
STOP consumer: drained
STOP consumer: callback
STOP writer (phase 100)
MAIN: context closed
```

Chú ý:

- Writer start trước Consumer vì phase 100 nhỏ hơn 200.
- Runner chỉ được gọi sau khi context refresh và các `SmartLifecycle` tự start.
- Khi `close()`, Consumer (phase 200) được gọi stop trước Writer (phase 100).
- Lệnh stop của Consumer trả về sớm nhưng Spring **đợi callback** nên Writer chỉ bị dừng sau thông báo `STOP consumer: callback`.
- Sau các phase và xử lý đóng context khác, `try-with-resources` kết thúc rồi mới in `MAIN: context closed`.

**Thời gian 300 ms chỉ là mô phỏng.** JVM scheduling có thể làm thời gian thực dao động; đừng khẳng định runtime chính xác bằng 300 ms. Cũng không dùng thứ tự log của các bean **cùng phase** làm một hợp đồng về thứ tự. Mã ví dụ cố ý dùng phase khác nhau.

## 7. LifecycleProcessor chờ callback trong bao lâu?

Spring Framework dùng `DefaultLifecycleProcessor` làm bộ điều phối lifecycle mặc định. Nó nhóm các bean theo phase, yêu cầu dừng theo thứ tự **phase giảm dần** và chờ kết quả phù hợp của từng nhóm. Với `SmartLifecycle`, callback cho biết bean đã kết thúc stop; nếu callback bị quên, processor có thể phải đợi hết **timeout của phase**.

Trong Spring Boot 3.3, có thể cấu hình:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Đây là **thời gian tối đa cho một nhóm phase**, không phải bảo đảm mọi resource sẽ đóng thành công sau đúng 20 giây. Nếu có ba bean cùng phase 200, chúng chia sẻ khoảng chờ của phase đó; không phải mỗi bean có riêng 20 giây cộng dồn.

Ở Spring Framework 6.1, timeout mặc định của `DefaultLifecycleProcessor` là **30.000 ms (30 giây)** khi không được cấu hình khác. Với bài thực hành, ta dùng 3 giây để thấy rõ ý nghĩa trong môi trường kiểm soát.

**Cảnh báo về thời gian:**

- Timeout 3 giây cho mỗi phase **không có nghĩa** tổng shutdown chỉ 3 giây. Có thể có nhiều phase và các bước destroy bean khác.
- Không có callback thì Spring có thể log cảnh báo timeout, tiếp tục các phase sau; điều đó **không chứng minh bean đã thực sự dừng**.
- Gọi callback sau khi phase đã timeout có thể quá muộn để bảo toàn thứ tự dừng dependency; phải thiết kế cleanup khớp thời hạn.
- Thời gian dành cho shutdown ở môi trường triển khai như Kubernetes `terminationGracePeriodSeconds`, container runtime hoặc process manager phải đủ cho các phase mà ứng dụng cần. Nếu hệ điều hành cưỡng bức kết thúc JVM trước, callback không thể cứu tiến trình.
- Thay giá trị timeout không sửa lỗi quên gọi callback. Đó chỉ là thay đổi thời gian Spring chịu chờ.

### Vì sao cần deadline nội bộ?

Nếu một consumer chờ bên ngoài mãi mãi vì I/O treo, đặt timeout của Spring không tự hủy được lời gọi đó. Hãy có timeout cấp resource hoặc cancellation cho bước drain, và kế hoạch force-close để callback chỉ chạy sau khi đã kết thúc theo chính sách.

Ví dụ timeline:

```text
t=0s: phase 200 bắt đầu stop
t=1s: consumer hoàn thành -> callback -> có thể sang phase 100

Nhánh lỗi:
t=0s: phase 200 bắt đầu stop
t=3s: callback chưa tới -> phase timeout, processor có thể tiếp tục
t=4s: consumer mới thực sự hoàn tất -> callback đến MUỘN
```

Ở nhánh lỗi, Writer phase 100 có thể đã bị dừng trước khi Consumer xong, làm hỏng ý đồ phân tầng. Vấn đề ở **deadline của quá trình dừng**, không phải Spring “không chờ”.

## 8. Mô hình trạng thái cho stop bất đồng bộ đáng tin cậy

Một bean có worker nền nên xác định rõ state, thay vì chỉ dùng một Boolean trong mọi tình huống:

```text
NEW
 |
 v
STARTING -> RUNNING
               |
           stop requested
               v
           STOPPING
               |
           stop completed
               v
           STOPPED
```

Có thể thêm `FAILED` cho tình huống lỗi trong runtime hoặc cleanup không hoàn thành theo tiêu chí ứng dụng. Khi chuyển sang `STOPPING`, cần từ chối công việc mới và cho công việc còn dở hoàn tất (hoặc cancel có kiểm soát).

**Các quy tắc triển khai:**

1. `start()` không được khởi chạy resource hai lần khi bean đã running; đồng thời phải nhận biết stop đang diễn ra.
2. `stop(Runnable callback)` phải an toàn khi bean đã stopped; không có gì cần đợi thì callback ngay.
3. Với nhiều lời gọi stop gần nhau, chỉ **một** đường cleanup được khởi chạy; mỗi callback được đăng ký để chạy **sau cùng một kết quả stop**.
4. Nếu callback được gọi qua `CompletableFuture.whenComplete(...)`, hãy đảm bảo future hoàn thành **sau khi cleanup** chứ không phải ngay khi gửi lệnh shutdown.
5. Callback không được gọi khi vẫn còn task có quyền ghi vào dependency mà phase thấp hơn đang chuẩn bị đóng.
6. Nếu quá thời hạn nội bộ, phải quyết định và ghi nhận rõ “force-stop”, “unfinished tasks”, số message chưa ack hoặc dữ liệu chưa flush.
7. Resource/worker nên được đóng theo chiều ngược với thứ tự tạo/phụ thuộc của chúng, có deadline từng bước.
8. Bảo đảm không ném exception rồi bỏ qua callback trong một nhánh lỗi; log lỗi và để close tiến tới trạng thái kết thúc phù hợp.

### Một khuôn mẫu production với CompletionStage

Khi thư viện cung cấp API dừng bất đồng bộ, ví dụ một phương thức `CompletionStage<Void> stopAsync()`, có thể kết nối completion stage với callback:

```java
@Override
public void stop(Runnable callback) {
    CompletionStage<Void> stage;

    try {
        stage = resource.stopAsync();
    } catch (RuntimeException ex) {
        // Phải force-close hoặc xác nhận resource đã kết thúc trước.
        safeForceClose(resource);
        recordShutdownFailure(ex);
        callback.run();
        return;
    }

    stage.whenComplete((ignored, error) -> {
        try {
            if (error != null) {
                recordShutdownFailure(error);
                safeForceClose(resource);
            }
            running.set(false);
        } finally {
            callback.run();
        }
    });
}
```

Đây là **pseudocode Java tích hợp có cấu trúc hợp lý**, **không phải chương trình runnable độc lập**: `resource`, `safeForceClose`, `recordShutdownFailure` và `running` là thành phần do ứng dụng tự định nghĩa. `safeForceClose` phải có semantics đúng; chỉ nên phát callback sau khi tài nguyên đã thật sự ngừng hoặc đã qua quy trình force-close được xác nhận. Nếu `safeForceClose` có thể ném lỗi và bỏ lại resource đang chạy, cần bổ sung xử lý riêng và ghi nhận trạng thái không hoàn tất. Khuôn mẫu cũng phải xử lý idempotency nếu `stop(Runnable)` có thể bị gọi đồng thời.

### Vì sao không được làm như sau?

```java
@Override
public void stop(Runnable callback) {
    resource.stopAsync();
    callback.run();
}
```

Đây là **sai cố ý**: việc nhận một `CompletionStage`/`Future` không có nghĩa operation đã hoàn tất. Cần gắn callback **vào completion** hoặc đợi bằng một cách có deadline phù hợp.

## 9. Các tình huống lỗi và nghĩa vụ gọi callback

### 9.1. Cleanup phát sinh exception

Một phương thức có thể ném `IOException`, `TimeoutException` hoặc lỗi thư viện khi flush/close. Không viết:

```java
@Override
public void stop(Runnable callback) {
    flushDatabase();  // Nếu ném exception thì dòng sau không chạy.
    callback.run();
}
```

Đây là snippet **sai cố ý**, không phải code chạy độc lập. Nếu cần thông báo lỗi ra logs/metrics, xử lý bằng `try/catch/finally` và một chiến lược fallback phù hợp. `finally` bảo vệ callback trước exception, nhưng phải nhớ **ngữ nghĩa đã dừng**: chỉ dùng finally để báo kết thúc sau khi cleanup hoặc forced shutdown thực sự đã hoàn thành, không che một resource còn hoạt động.

### 9.2. Dừng từ thread khác bị interrupt

Trong Java, một `InterruptedException` không tự đóng socket, executor hoặc hoàn tất offset commit. Code nên:

- Khôi phục cờ interrupt khi phù hợp bằng `Thread.currentThread().interrupt()`.
- Kích hoạt cancellation/force-close.
- Ghi nhận các công việc chưa hoàn tất.
- Chỉ gọi callback sau khi đã đạt trạng thái stop kết thúc theo chính sách.

Trong demo, không có I/O thật nên xử lý interrupt như kết thúc mô phỏng. Không sao chép hành vi này thành một cam kết về data durability ở production.

### 9.3. Không thể gửi tác vụ vào executor

Với `ExecutorService`, gọi `execute(...)` có thể ném `RejectedExecutionException` nếu executor đã đóng hoặc đầy. Nếu chỉ viết:

```java
executor.execute(() -> {
    cleanup();
    callback.run();
});
```

thì khi việc gửi task **bị từ chối**, callback sẽ không được gọi. Phải có nhánh catch, thực hiện cleanup thay thế (có thể đồng bộ hoặc bằng cơ chế khác) và báo hoàn tất khi điều kiện dừng đã đạt.

**Không dùng cùng một executor để điều phối cleanup nếu chính executor đó đã bị shutdown trước khi scheduling cleanup.** Có thể cần một executor riêng còn sống trong giai đoạn shutdown, hoặc thực hiện cleanup có deadline trên thread gọi stop.

### 9.4. Callback bị gọi hai lần

Trong một số code lỗi:

```java
try {
    cleanup();
    callback.run();
} finally {
    callback.run(); // Lặp hai lần nếu cleanup thành công.
}
```

Đây là **sai cố ý**. Bố trí **một điểm gọi callback** trong luồng kết thúc, hoặc dùng guard phù hợp. Callback của `LifecycleProcessor` thường đếm tín hiệu hoàn thành; gọi nhiều lần không phải một “retry” hợp lệ.

### 9.5. Đánh dấu isRunning false quá sớm

Nếu `isRunning()` trả false ngay lúc nhận lệnh dừng, nhưng worker vẫn xử lý dữ liệu, trạng thái điều phối và trạng thái thực tế không khớp. Trong một quy trình shutdown dễ hiểu, chuyển sang STOPPING nội bộ khi ngừng nhận công việc, và chỉ phản ánh STOPPED khi resource được đóng. Có thể định nghĩa `isRunning()` tùy hợp đồng của resource, nhưng không dùng nó để che một cleanup chưa xong rồi gọi callback sớm.

### 9.6. Không được shutdown hook kích hoạt

`SmartLifecycle.stop(Runnable)` được gọi khi context đi qua đường dừng lifecycle hợp lệ. Nếu tiến trình bị `kill -9` hoặc JVM crash, không có bảo đảm callback hay `@PreDestroy` được gọi. Kiểm tra đường đóng có kiểm soát riêng và xây dựng cơ chế khôi phục dữ liệu cho tình huống tắt cưỡng bức.

### 9.7. Bean chưa running

`DefaultLifecycleProcessor` thông thường chỉ gọi stop trên các lifecycle beans đang running. Nếu `isRunning()` không bao giờ trả true do `start()` triển khai sai, không nên mong chờ callback dừng được gọi để cleanup tài nguyên đã cấp phát ở một pha khác. Tài nguyên cần được quản lý đúng vòng đời; `@PreDestroy` có thể là đường đóng bổ sung khi thích hợp, nhưng không thay thế hợp đồng stop có phase.

## 10. Dừng ExecutorService đúng hơn shutdown() + callback ngay

Một ví dụ sát thực tế hơn: consumer sử dụng một `ExecutorService` để xử lý message. Khi stop:

1. Từ chối công việc mới.
2. Gọi `executor.shutdown()`.
3. Đợi `executor.awaitTermination(timeout, unit)` trên **luồng khác** (nếu muốn stop bất đồng bộ).
4. Nếu quá thời gian, gọi `shutdownNow()` và thử đợi một khoảng ngắn; ghi lại task còn lại.
5. Chỉ xác nhận shutdown hoàn thành khi executor thật sự terminated hoặc resource đã bị force-close theo chính sách.

Đoạn mô tả pseudo-code:

```java
@Override
public void stop(Runnable callback) {
    acceptingNewWork.set(false);
    executor.shutdown();

    Thread monitor = new Thread(() -> {
        try {
            boolean done = executor.awaitTermination(4, TimeUnit.SECONDS);

            if (!done) {
                executor.shutdownNow();
                done = executor.awaitTermination(1, TimeUnit.SECONDS);
            }

            if (!done) {
                // Một task có thể đã bỏ qua interrupt; không tuyên bố graceful.
                recordUnfinishedTasks();
            }

            // Chỉ đánh dấu complete nếu đã có chính sách xử lý kết quả
            // của cả nhánh done=false; xem giải thích bên dưới.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            executor.shutdownNow();
            recordShutdownInterrupted();
        } finally {
            // Không vô điều kiện khẳng định worker đã dừng nếu chưa có
            // xác nhận termination. Cần thiết kế forced stop thực tế.
            onTerminationPolicyResolved(callback);
        }
    }, "executor-termination-monitor");

    monitor.start();
}
```

**Đây là skeleton minh họa, không phải code runnable độc lập**: `acceptingNewWork`, `executor`, `recordUnfinishedTasks`, `recordShutdownInterrupted` và `onTerminationPolicyResolved` là thành phần do dự án tự xây dựng. Ý chính là **không nhầm `shutdown()` với `isTerminated()`** và không phát callback từ khi bắt đầu drain.

Một việc bắt buộc: nếu task treo **không phản ứng với interrupt**, `shutdownNow()` chỉ là yêu cầu dừng; không thể tự đảm bảo executor đã terminated. Tùy nghiệp vụ, cần close socket/resource trực tiếp, thực hiện recovery sau restart, hoặc báo rõ shutdown không sạch. Bộ timeout của Spring chỉ giúp tránh treo vô thời hạn; không giải quyết dữ liệu chưa flush.

## 11. Quan hệ với @PreDestroy, DisposableBean và việc đóng ApplicationContext

Spring có nhiều cơ chế teardown; chúng không cùng nhiệm vụ:

| Cơ chế | Giai đoạn/ý nghĩa | Khả năng chờ bất đồng bộ |
|---|---|---|
| `SmartLifecycle.stop(Runnable)` | Dừng lifecycle theo phase trước bước destroy beans | Có callback để `LifecycleProcessor` biết khi nào stop xong |
| `Lifecycle.stop()` | API dừng trực tiếp; với SmartLifecycle shutdown, processor chọn overload callback | Tự thiết kế việc đợi nếu caller dùng bản không callback |
| `@PreDestroy` | Callback destroy khi bean bị hủy trong quá trình đóng context | Không cung cấp cùng hợp đồng callback theo phase |
| `DisposableBean.destroy()` | Callback hủy bean | Không trực tiếp thay thế phase callback |
| `ConfigurableApplicationContext.close()` | Khởi động toàn bộ quy trình đóng context | Có thể đợi nhiều phase và các callback destroy |
| JVM shutdown hook | Đường kích hoạt close context khi tiến trình kết thúc bình thường | Không bảo đảm thực hiện khi kill cưỡng bức |

Đối với `ApplicationContext` chuẩn, shutdown thường đi theo ý nghĩa:

```text
context.close()
       |
       v
LifecycleProcessor.onClose()
  -> SmartLifecycle stop theo phase
  -> đợi callback/timeout theo từng phase
       |
       v
destroy singleton beans
  -> @PreDestroy / DisposableBean / destroy-method ...
       |
       v
giải phóng context
```

Nếu bean dùng cả `SmartLifecycle` và `@PreDestroy`, hãy làm các phương thức **idempotent** và chia trách nhiệm rõ. Ví dụ `stop(Runnable)` ngừng nhận message và drain; `@PreDestroy` chỉ kiểm tra/đóng dự phòng tài nguyên đã ở trạng thái dừng. Không để cả hai cùng gửi cùng một commit hoặc ghi trùng dữ liệu.

**Không nên** chỉ dùng `@PreDestroy` để làm async drain rồi hy vọng Spring biết đợi theo `getPhase()`: callback trong `stop(Runnable)` mới có vai trò phối hợp phase.

## 12. Liên hệ với graceful shutdown của Spring Boot

Spring Boot 3.3 hỗ trợ graceful shutdown cho Web server tích hợp khi bật:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Với cấu hình tương ứng, graceful Web server shutdown hoạt động như một phần của việc đóng context và được xử lý trong nhóm phase dừng rất sớm của các `SmartLifecycle` liên quan. Tại đây Web server ngừng nhận request mới theo cơ chế phù hợp, cho những request đang xử lý thời gian hoàn tất.

**Phân biệt hai việc:**

- **Graceful shutdown Web server:** ngừng nhận request mới, để request đang chạy hoàn thành (tùy server và cấu hình).
- **Stop một `SmartLifecycle` nghiệp vụ:** ngừng consumer/producer/job/worker của ứng dụng, drain hoặc đóng resource theo phase của **bean do bạn viết**.

Bật `server.shutdown=graceful` **không tự động** buộc mọi message consumer tùy biến thực hiện drain đúng; bạn vẫn phải triển khai `stop(Runnable)` của bean. Ngược lại, triển khai callback của consumer không có nghĩa Web server đã graceful.

**Đừng giả định chỉ đổi `spring.lifecycle.timeout-per-shutdown-phase` là đủ:** có thể còn timeout của message broker, JDBC, HTTP client, executor, Kubernetes/containers và shutdown hook. Thiết kế thời hạn phải phù hợp với tổng quỹ thời gian của tiến trình.

**Lưu ý phiên bản:** trong Spring Boot 3.3, graceful shutdown Web server được bật bằng `server.shutdown=graceful`; không sao chép mặc định ở phiên bản mới hơn sang ứng dụng 3.3 mà không kiểm tra.

## 13. Cách kiểm thử callback và phase một cách định lượng

### 13.1. Quan sát thời gian đóng context

Trong demo, có thể đo quanh `close()` bằng `System.nanoTime()`:

```java
long start = System.nanoTime();

context.close();

long elapsedMs =
        TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);

System.out.println("Close duration (ms): " + elapsedMs);
```

Đoạn này là **snippet tích hợp**, không phải file chạy riêng; cần import `java.util.concurrent.TimeUnit` và biến `context`. Vì demo đã dùng try-with-resources để gọi `close()` tự động, khi thực hành đo thủ công hãy **thay phần đóng tự động** bằng lệnh đóng ở vị trí xác định, tránh gọi close hai lần rồi suy ra số đo sai.

Kỳ vọng tổng thời gian đóng có chứa khoảng chờ drain 300 ms trong điều kiện bình thường, nhưng số đo phụ thuộc runtime; **không viết assertion phải đúng chính xác 300 ms**.

### 13.2. Kiểm tra callback sau completion

Trong unit test triển khai của bạn, có thể truyền `Runnable` tự tạo vào `stop(Runnable)` để biết khi nào callback chạy:

```java
CountDownLatch completed = new CountDownLatch(1);

consumer.stop(completed::countDown);

boolean finished = completed.await(2, TimeUnit.SECONDS);

if (!finished) {
    throw new AssertionError("Stop callback was not invoked");
}

if (consumer.isRunning()) {
    throw new AssertionError("Consumer is still running after callback");
}
```

Đây là **snippet kiểm thử tích hợp**, cần `consumer` là instance đang chạy, import `CountDownLatch`/`TimeUnit`. Với ứng dụng thực, còn phải xác minh các task đã ngừng, tài nguyên đã được đóng và không còn message mới được nhận sau callback. `isRunning()==false` đơn độc có thể được đặt sai trong code.

### 13.3. Kiểm tra callback đúng một lần

```java
AtomicInteger callbacks = new AtomicInteger();
CountDownLatch completed = new CountDownLatch(1);

consumer.stop(() -> {
    callbacks.incrementAndGet();
    completed.countDown();
});

if (!completed.await(2, TimeUnit.SECONDS)) {
    throw new AssertionError("Callback missing");
}

if (callbacks.get() != 1) {
    throw new AssertionError("Expected exactly one callback");
}
```

Đây là snippet kiểm thử, cần import `AtomicInteger`, `CountDownLatch` và `TimeUnit`, cùng một consumer thật. Việc kiểm tra ngay sau latch xác nhận ít nhất một callback đã chạy và số lần đến thời điểm đó, nhưng **không đủ** để chứng minh tuyệt đối sẽ không có lần gọi muộn hơn trong một race condition. Nếu cần kiểm chứng concurrency, dùng test có kiểm soát nhiều thread, state machine hoặc assertion trên completion future và mọi đường dừng.

### 13.4. Kiểm tra nhiều phase

Với project ở phần 6, ghi lại các dòng:

```text
START writer
START consumer
STOP consumer: callback
STOP writer
```

Khi cố ý bỏ `callback.run()` ở Consumer trong một bản thử nghiệm riêng, Spring có thể phải chờ hết timeout phase 200 trước khi dừng Writer. **Không giữ đoạn lỗi đó trong sản phẩm**; sau thực nghiệm phải khôi phục callback.

### 13.5. Mô phỏng timeout có kiểm soát

Đổi `Thread.sleep(300)` trong Consumer thành `Thread.sleep(5000)` khi property timeout phase vẫn là `3s`. Kỳ vọng lifecycle processor có thể hết thời hạn chờ phase 200 trước khi Consumer hoàn tất, làm mất bảo đảm thứ tự dừng bạn mong muốn. Đừng đưa kiểu test này vào pipeline chung nếu các thread/resource không được dọn dẹp. Luôn trả về giá trị đúng sau thử nghiệm.

## 14. Những lỗi điển hình và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Đóng context bị chờ gần đúng thời hạn phase | `stop(Runnable)` quên gọi callback | Đặt completion signal ở đường kết thúc stop, kiểm tra bằng latch |
| Context đóng nhanh nhưng worker còn chạy | Callback gọi ngay sau `shutdown()` | Chờ termination/flush thực sự trước khi callback |
| Logic dừng có trong `stop()` nhưng không chạy | Override `stop(Runnable)` mà không delegate logic | Triển khai cùng một stop routine cho hai đường hoặc delegate phù hợp |
| Bean không được stop khi context đóng | `isRunning()` trả false, bean không được đăng ký hoặc context không đi qua đường close bình thường | Kiểm tra `start`/`isRunning`, đăng ký bean và tín hiệu shutdown |
| Writer bị đóng khi Consumer còn cần ghi | Phase sai, callback sớm hoặc phase timeout | Đặt Consumer phase cao hơn Writer; hoàn tất drain trước callback |
| Các bean cùng phase stop theo thứ tự bất định | Không có ràng buộc phase/dependency | Dùng phase khác nhau hoặc quan hệ dependency phù hợp |
| Chỉ gọi `executor.shutdown()` | `shutdown` không đợi task đã nhận | Dùng `awaitTermination`/completion callback và fallback force-close |
| Executor từ chối cleanup task | Executor đã bị shutdown hoặc queue quá tải | Xử lý `RejectedExecutionException`, có fallback không bỏ callback |
| Lúc lỗi không có callback | Exception thoát khỏi worker trước dòng `callback.run()` | Dùng kiểm soát lỗi và một điểm completion trong `finally` sau cleanup |
| Callback chạy hai lần | Gọi ở `try` rồi `finally` hoặc nhiều nhánh success/error | Thiết kế một điểm gọi callback, dùng guard khi có concurrency |
| Đã timeout nhưng resource vẫn đang chạy | Không có timeout/force-close ở cấp tài nguyên | Thêm deadline, cancellation, kiểm tra termination và báo tình trạng thất bại |
| Dùng `@PreDestroy` thay cho lifecycle callback | `@PreDestroy` không tham gia phase completion như `stop(Runnable)` | Đặt drain trong lifecycle stop, destroy chỉ để cleanup bổ sung |
| Chạy `kill -9` rồi không thấy callback | JVM không có cơ hội shutdown có trật tự | Test bằng close/SIGTERM và có cơ chế recovery cho forced termination |
| `@Lazy` làm SmartLifecycle bean không được khởi tạo | Nhầm chính sách lazy với nhu cầu auto-start | SmartLifecycle auto-start thông thường kéo bean vào startup; kiểm tra bean discovery |
| Nhiều bean cùng phase làm thời gian shutdown khó đo | Chờ nhóm callback, không phải mỗi bean một timeout nối tiếp | Đo từng phase, ghi duration, và cân đối shutdown budget |

### Checklist cho code review

- [ ] Bean thực sự là `SmartLifecycle` được Spring quản lý.
- [ ] `start()` và `isRunning()` phản ánh trạng thái thật của worker.
- [ ] `getPhase()` cho thứ tự phụ thuộc hợp lý.
- [ ] `stop(Runnable)` không gọi callback trước khi cleanup hoàn tất.
- [ ] Mọi đường kết thúc stop đều phát callback đúng một lần, kể cả khi có lỗi hợp lệ.
- [ ] Nếu bean đã stopped, callback không bị bỏ quên.
- [ ] Có xử lý trường hợp không thể submit/start tác vụ cleanup.
- [ ] Có timeout/cancellation cấp resource, không chỉ timeout Spring.
- [ ] Không đóng dependency cần thiết trước consumer còn đang drain.
- [ ] `stop()` trực tiếp và `stop(Runnable)` không có logic mâu thuẫn.
- [ ] Có kiểm thử missing/double callback và phase ordering.
- [ ] Có metrics/log cho forced shutdown và unfinished work.
- [ ] Thời gian shutdown phù hợp với giới hạn ở orchestrator.

## 15. Các bài thực hành

Dùng project phần 6, mỗi lần chỉ thay đổi một điểm rồi khôi phục trước khi thử tiếp.

**Bài 1 — xác định hợp đồng callback:** chạy demo nguyên bản. Giải thích vì sao dòng `STOP writer` chỉ xuất hiện sau `STOP consumer: callback`, dù `stop(Runnable)` đã trả về trước khi drain hoàn tất.

**Bài 2 — bỏ callback có chủ đích:** trong một bản test, tạm bỏ lệnh `callback.run()` ở Consumer. Cấu hình phase timeout `3s` và đo thời gian `context.close()`; kiểm tra dấu hiệu phase chờ timeout, sau đó khôi phục callback ngay.

**Bài 3 — callback quá sớm:** chuyển `callback.run()` lên ngay sau `shutdownWorker.start()` trong một nhánh thử nghiệm, chỉ dùng ở môi trường học. Quan sát Writer có thể bị stop trước khi Consumer in `drained`. Giải thích rủi ro khi Consumer cần Writer để flush dữ liệu.

**Bài 4 — đổi phase:** cho Writer phase 300 và Consumer phase 200, chạy lại. Giải thích vì sao thứ tự mới không còn phù hợp với đường phụ thuộc “Consumer dùng Writer khi drain”.

**Bài 5 — đổi timeout:** tăng `Thread.sleep` từ 300 ms lên 5 giây, vẫn giữ timeout phase 3 giây. Quan sát tác động tới tổng shutdown và thứ tự stop; không dùng đây là phép thử benchmark hiệu năng.

**Bài 6 — thử lỗi interrupt:** trong một unit test, can thiệp interrupt tới thread cleanup rồi kiểm tra callback có được gọi không. Giải thích vì sao **callback được gọi** không đồng nghĩa dữ liệu đã được flush đủ.

**Bài 7 — executor thật:** thay mô phỏng bằng `ExecutorService` có một task chạy ngắn; dùng `shutdown()`, `awaitTermination` và sau cùng là callback. Thử một task không đáp ứng interrupt trong môi trường cô lập để xem giới hạn của `shutdownNow()`.

**Bài 8 — stop gọi nhiều lần:** gọi `stop(Runnable)` đồng thời từ hai thread trong một unit test và quan sát code demo có thể tạo hai shutdown workers. Thiết kế lại bằng một completion future chung trước khi đưa vào sản phẩm; mỗi callback cần nhận một tín hiệu completion đúng lần gọi của nó.

**Bài 9 — xem quan hệ với destroy:** thêm `@PreDestroy` chỉ in một dấu mốc ở Writer. Kiểm tra lifecycle stop xảy ra trước callback destroy khi context đóng bình thường, nhưng không làm resource đóng trùng hai lần.

**Bài 10 — Web server graceful:** trong một ứng dụng Web thử nghiệm dùng Spring Boot 3.3, bật `server.shutdown=graceful` và viết một SmartLifecycle consumer. Xác định hai công việc dừng khác nhau, thứ tự phase của chúng, tổng shutdown budget và lý do phải có readiness/termination chính xác.

### Câu hỏi tự đánh giá

1. Tại sao không được gọi `callback.run()` ngay sau `ExecutorService.shutdown()`?
2. Nếu `stop(Runnable)` không bao giờ gọi callback thì `DefaultLifecycleProcessor` thường phản ứng thế nào?
3. Với bean phase 100 và 200, thứ tự start/stop là gì?
4. `LifecycleProcessor` gọi `stop()` hay `stop(Runnable)` của một `SmartLifecycle`?
5. `SmartLifecycle` có phase mặc định là bao nhiêu? `Lifecycle` thuần được coi như phase nào?
6. Nếu worker hoàn tất sau timeout phase, gọi callback muộn còn đảm bảo Writer chưa dừng không?
7. Vì sao `@PreDestroy` không phải phương thức thay thế trực tiếp cho callback theo phase?
8. Khi `Thread.start()` hoặc `executor.execute()` thất bại, vì sao cần xử lý đường gọi callback?
9. Làm sao đảm bảo callback đúng một lần nếu có hai yêu cầu stop đồng thời?
10. Khi dùng `server.shutdown=graceful`, message consumer của ứng dụng có tự được dừng graceful không?

## 16. Kết luận

`SmartLifecycle.stop(Runnable callback)` là một **hợp đồng phối hợp shutdown** giữa bean của bạn và Spring `LifecycleProcessor`. Bạn được phép trả về ngay rồi dừng resource bất đồng bộ, nhưng **phải gọi `callback.run()` sau khi việc dừng hoàn thành**. Nếu quên callback, Spring có thể chờ hết timeout của phase; nếu gọi callback quá sớm, Spring có thể đi tới dừng những dependency mà worker vẫn cần.

Trong một hệ thống có phụ thuộc, hãy kết hợp **`getPhase()` đúng**, **quy trình drain có deadline**, **trạng thái chạy trung thực**, **error handling**, **callback đúng một lần** và **kiểm thử completion**. `spring.lifecycle.timeout-per-shutdown-phase` là giới hạn chờ của Spring, không phải phép màu để đóng resource đang treo.

### Tài liệu chính thức

- Spring Framework 6.1 — `SmartLifecycle` Javadoc, nghĩa vụ callback và phase: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` Javadoc, thời hạn theo phase và start/stop order: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — Customizing the Nature of a Bean / `SmartLifecycle`: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Boot 3.3 — Graceful Shutdown, `server.shutdown=graceful` và `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html