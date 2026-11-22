# spring.lifecycle.timeout-per-shutdown-phase và giới hạn thời gian dừng trong Spring Boot

**Chủ đề:** Spring Boot Application Runtime → **Dừng ứng dụng**. Bài này giải thích cấu hình `spring.lifecycle.timeout-per-shutdown-phase`, quy tắc Spring dừng các `SmartLifecycle` theo `phase`, ranh giới của thời gian chờ, sự khác nhau giữa graceful shutdown của web server và dừng công việc nền, cùng cách điều phối với deadline ở hệ điều hành và Kubernetes. Có một dự án **Java 17+ / Spring Boot 3.5.x** chạy được để tự đo mốc callback, mô phỏng một phase chậm, một phase nhanh và kiểm chứng phản ứng khi vượt timeout.

**Điểm phải nhớ:** Timeout ở đây là **ngân sách đợi mỗi shutdown phase**, không phải “toàn bộ ứng dụng buộc phải dừng sau N giây”, cũng không phải “Spring tự hủy thread/rollback transaction khi hết N giây”. Muốn shutdown an toàn phải kiểm soát request mới, task đang chạy, callback hoàn thành, timeout của I/O bên ngoài và hạn chót của platform.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Đọc đúng property `spring.lifecycle.timeout-per-shutdown-phase=20s` và giải thích đơn vị thời gian.
2. Biết Spring Boot 3.5 mặc định **30 giây cho mỗi phase**; phân biệt với mặc định **10 giây** của `DefaultLifecycleProcessor` trong Spring Framework 6.2 khi dùng riêng mà không có Boot override.
3. Phân biệt `SmartLifecycle.stop(Runnable)`, `Lifecycle.stop()`, `@PreDestroy`, `DisposableBean.destroy()` và JVM shutdown hook.
4. Nêu quy tắc dừng theo `phase` **cao trước, thấp sau**; các bean cùng phase là một nhóm có chung ngân sách chờ.
5. Biết callback `Runnable` thông báo Spring “thành phần đã xong thủ tục dừng”, và vì sao không được quên/gọi quá sớm.
6. Tự đo việc phase chậm bị timeout nhưng phase sau vẫn được xử lý, **không khẳng định** tác vụ chậm đã bị ngắt.
7. Chứng minh một component đang dừng bất đồng bộ có thể tiếp tục hoạt động sau khi `ApplicationContext.close()` trả về vì hết thời gian chờ.
8. Phân biệt timeout của lifecycle processor với graceful HTTP request drain, executor termination, JDBC/socket timeout và Kubernetes `terminationGracePeriodSeconds`.
9. Chạy ví dụ có HTTP request đang xử lý và giải thích vì sao response có thể thành công, bị reset hoặc trả lỗi tùy server, connection và thời điểm.
10. Thiết kế thứ tự dừng worker → dependency, ngăn nhận việc mới, xử lý retry/idempotency và kiểm tra không rò tài nguyên.
11. Xác định được lỗi startup/shutdown và tiêu chí QA bằng log timestamp, callback và trạng thái tài nguyên.
12. Lựa chọn ngân sách dừng từ phép đo thực tế thay vì tăng property tùy ý.

## 2. Property này thực sự điều khiển cái gì?

Cấu hình chuẩn trong `src/main/resources/application.properties`:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Dạng YAML tương đương:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Cả hai đều đặt thời gian chờ mà Spring Boot chuyển cho cơ chế lifecycle processing khi context đang đóng. Giá trị kiểu `Duration` nên ghi **rõ đơn vị**, ví dụ `500ms`, `5s`, `20s`, `1m`. Không dựa vào việc bỏ đơn vị rồi đoán người đọc sẽ hiểu giây hay mili-giây.

**Đúng phạm vi:** Spring Framework có `DefaultLifecycleProcessor`, làm việc với các `Lifecycle`/`SmartLifecycle` trong `ApplicationContext`. Các `SmartLifecycle` được dừng theo thứ tự phase giảm dần. Ở mỗi nhóm phase, processor yêu cầu component `stop(Runnable callback)` và chờ các callback tối đa khoảng thời gian cho phase đó. Hết thời gian, processor có thể ghi log component còn chưa callback và **chuyển tiếp** sang phase kế tiếp.

**Không nằm trong phạm vi bảo đảm:** Property không tự áp một deadline tổng lên mọi `@PreDestroy`, callback tùy biến, HTTP client, network socket, thread pool tự tạo, transaction đang commit hoặc shutdown hooks ngoài Spring. Một method `stop(Runnable)` triển khai sai, chạy đồng bộ và không trả về có thể làm toàn chuỗi shutdown chậm quá thời gian cấu hình; đó không phải cơ chế preemptive cancellation.

### 2.1. Mặc định của Boot khác mặc định framework thuần

| Đối tượng | Mặc định của phiên bản nêu trong bài | Ý nghĩa |
|---|---|---|
| Spring Boot **3.5** — `spring.lifecycle.timeout-per-shutdown-phase` | **30s** | Boot áp lên lifecycle processor mà nó cấu hình |
| Spring Framework **6.2** — `DefaultLifecycleProcessor` độc lập | **10.000 ms (10s)** | Mặc định của implementation nếu không có Boot/custom override |
| `server.shutdown` trong Spring Boot **3.5** | `graceful` | Graceful shutdown được bật mặc định cho embedded web servers được hỗ trợ |
| `spring.main.register-shutdown-hook` trong Spring Boot **3.5** | `true` | Spring Boot đăng ký shutdown hook JVM thông thường |

Đừng lấy giá trị 10 giây từ Javadoc Spring Framework rồi tuyên bố Spring Boot 3.5 mặc định 10 giây. Cũng đừng dùng mặc định Boot 3.5 để suy luận toàn bộ dòng Boot 2.x/3.x/4.x đều giống nhau. Khi ứng dụng có custom `LifecycleProcessor` hoặc phiên bản khác, phải đọc configuration metadata và runtime thực tế.

### 2.2. Có phải timeout này áp cho từng bean?

**Không.** Tên property ghi rõ `per-shutdown-phase`. Xét ba beans:

- `workerA` phase 200
- `workerB` phase 200
- `databaseAdapter` phase 100

Với timeout mỗi phase là 10s, hai beans ở phase 200 được yêu cầu dừng và processor chờ **chung một ngân sách 10 giây** cho callbacks của phase 200; không mặc định là 10 + 10 giây chỉ vì có hai beans. Sau đó phase 100 có một ngân sách chờ **riêng**. Thời gian tổng có thể vượt 10 giây, đặc biệt nếu còn nhiều phase, bean destruction, hooks hoặc I/O blocking.

Điều quan trọng là **phân nhóm theo giá trị phase, không phân nhóm theo package hoặc loại business**.

## 3. Sơ đồ từ SIGTERM tới kết thúc ứng dụng

~~~text
Kubernetes / systemd / terminal gửi SIGTERM
         |
         v
JVM shutdown hook do Spring Boot đăng ký
         |
         v
ApplicationContext.close()
         |
         +--> ContextClosedEvent
         |
         +--> LifecycleProcessor.onClose()
         |       |
         |       +--> phase cao nhất: ví dụ web-server graceful stop
         |       |       - stop intake / drain requests theo server
         |       |       - chờ callback tối đa timeout cho phase này
         |       |
         |       +--> phase 200: yêu cầu worker stop
         |       |       - stop(Runnable callback)
         |       |       - chờ callback tối đa timeout phase 200
         |       |
         |       +--> phase 100: dừng dependency
         |               - stop(Runnable callback)
         |               - ngân sách timeout phase 100 riêng
         |
         +--> destroyBeans()
         |       - @PreDestroy / DisposableBean / destroy-method
         |
         +--> đóng BeanFactory và công việc context khác
         |
         v
context.close() trả về; JVM còn phải tuân theo shutdown process
~~~

Trong ví dụ, thứ tự là mô hình khái niệm; các infrastructure beans của Spring Boot có phase cụ thể mà ta không tự sắp xếp tùy ý, và quan hệ `depends-on` có thể ảnh hưởng thứ tự so với phase. Một `ContextClosedEvent` được publish khi bắt đầu doClose, **trước** điều phối stop của `LifecycleProcessor` trong `AbstractApplicationContext` tiêu chuẩn.

**Hai giới hạn độc lập:** Spring có thể đã đi hết nhóm phase sau khi chờ timeout nhưng một thread bất đồng bộ vẫn chưa xong. Khi JVM đang shutdown bởi SIGTERM, nó có thể chấm dứt process sau hooks mà **không cần chờ** thread nền đó kết thúc. Đừng nghĩ “Thread còn chạy” đồng nghĩa được hoàn tất nốt trong mọi chế độ đóng process.

### 3.1. Dấu mốc readiness

Khi ứng dụng bắt đầu shutdown hợp lệ, Spring Boot có thể công bố `ReadinessState.REFUSING_TRAFFIC` để hạ tầng ngừng routing. Tín hiệu này **không** lập tức chặn mọi request gửi trực tiếp tới Pod IP nếu HTTP connector vẫn còn hoạt động. Khi web server thực sự đi qua graceful shutdown, nó có chính sách dừng nhận request mới.

Vì vậy cần phân biệt **publish availability state**, **readiness probe**, **thay đổi EndpointSlice/load balancer routing** và **web server ngừng tiếp nhận**. Những hành động đó không được bảo đảm đồng bộ tức thời.

## 4. Quy tắc phase: start thấp trước, stop cao trước

`SmartLifecycle` cho phép bean mô tả phase qua `getPhase()`. Spring Framework dùng phase để xác định thứ tự:

~~~text
Startup (onRefresh):
 phase -100 → phase 0 → phase 100 → phase 200

Shutdown (onClose):
 phase 200 → phase 100 → phase 0 → phase -100
~~~

Điều này giúp bảo đảm khi dừng: **dependent worker** dừng trước **dependency service** mà nó cần cho cleanup. Nếu component A cần database adapter B lúc stop để flush dữ liệu cuối, B không nên bị đóng trước A.

Những chi tiết cần nhớ:

- `SmartLifecycle` có mặc định `getPhase() = Integer.MAX_VALUE` trong Spring Framework 6.2 nếu không override; điều này khác phase 0 của một số `Lifecycle` thông thường.
- `SmartLifecycle.isAutoStartup()` mặc định true; bean thích hợp được auto-start trong refresh và được quản lý lúc close.
- `depends-on` ảnh hưởng thứ tự thực tế: dependent bean stop trước dependency dù một số phase gợi ý khác.
- Các beans cùng phase không có một thứ tự tuần tự nghiệp vụ ổn định để dựa vào. Muốn thứ tự quan trọng, dùng phase khác hoặc dependency rõ ràng.
- Framework quản lý **Lifecycle beans đang running**; bean chưa running không có cùng nghĩa vụ nhận stop.
- Đặt phase cực đại/cực tiểu tùy tiện có thể tương tác ngoài ý muốn với web server, listener container hoặc scheduler của framework. Hãy tìm phase của thành phần thực tế trước khi override.

**Ví dụ bài toán:** HTTP listener nhận lệnh, worker xử lý hàng đợi và adapter gửi kết quả sang broker. Phương án an toàn: chặn intake, cho worker drain/cancel, sau đó mới đóng broker adapter. Có thể phối hợp phase + dependency + readiness + broker acknowledgements, không chỉ đổi hai con số phase.

## 5. Stop callback: nghĩa vụ quyết định việc chờ

### 5.1. Hợp đồng SmartLifecycle.stop(Runnable)

`org.springframework.context.SmartLifecycle` khai báo:

~~~java
void stop(Runnable callback);
~~~

Khi processor yêu cầu dừng một bean `SmartLifecycle`, nó cung cấp callback. **Bean phải gọi `callback.run()` khi thủ tục dừng của mình đã hoàn tất**. Nếu dừng đồng bộ nhanh:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

Đây là **method snippet**, cần đặt trong class implement `SmartLifecycle` với method `stop()` đúng contract. Trong hệ thống có lỗi cleanup, cần log/truyền policy lỗi phù hợp, không chỉ luôn tuyên bố success.

Nếu stop bất đồng bộ:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            stopReceivingNewMessages();
            awaitOrCancelInFlightWork();
            closeOwnedResources();
        } finally {
            callback.run();
        }
    });
}
~~~

Đây là **pseudocode dưới dạng Java method**, vì `executor` và ba hàm cleanup phụ thuộc hệ thống thực tế. Phải cẩn trọng trường hợp `executor.execute(...)` tự bị reject trong lúc shutdown: nếu không tạo được task dừng, cần kế hoạch fallback đồng bộ, ghi lỗi và vẫn hoàn tất lifecycle contract theo policy.

### 5.2. Hai lỗi ngược chiều

- **Quên callback:** Processor chờ đến hết timeout của phase, ghi nhận bean chưa hoàn tất và tiến sang phase sau. Shutdown có thể kéo dài, ứng dụng rơi vào trạng thái hủy phụ thuộc khi worker vẫn chạy.
- **Callback quá sớm:** Bean gọi `callback.run()` khi task mới *được yêu cầu* dừng, nhưng queue còn việc và tài nguyên chưa được đóng. Processor tưởng đã hoàn tất và dừng dependency khác, gây mất event, lỗi transaction hoặc resource use-after-close.

Cả hai đều là lỗi lifecycle. Callback không phải “thông báo đã nhận yêu cầu stop”, mà là “**đã xử lý xong việc stop theo hợp đồng**”, bao gồm timeout/failure policy được thiết kế và kiểm chứng.

### 5.3. Property không hủy một stop() blocking

Nếu code làm:

~~~java
@Override
public void stop(Runnable callback) {
    doBlockingNetworkCallWithNoTimeout();
    callback.run();
}
~~~

thì method `stop(Runnable)` có thể không trả về để processor đi đến lượt chờ trên latch. Tùy implementation, cấu hình “2s” **không biến** network call này thành call bị interrupt đúng sau 2 giây. Cách đúng là có timeout của network client, hoặc khởi động thao tác dừng bất đồng bộ rồi trả về để lifecycle processor chờ callback trong budget.

Đừng đặt `Thread.sleep(60000)` trong `stop(Runnable)` đồng bộ và kết luận Spring không tôn trọng property khi shutdown mất 60 giây. Đó là bài test **blocking method**, không phải bài test timeout chờ callback.

## 6. Ứng dụng thực hành Java 17 và Spring Boot 3.5

Dự án dưới đây có hai `SmartLifecycle` tự start, nhưng khi close có **hai phase dừng** độc lập: bean phase 200 dừng chậm, bean phase 100 dừng nhanh. Dùng `Thread` riêng làm stop bất đồng bộ để minh họa callback và việc timeout **không tự kill thread**. Có một endpoint HTTP sleep để quan sát graceful web server khi chạy chế độ server.

### 6.1. Tạo Maven project

Vào Spring Initializr tạo:

- Group: `com.example`
- Artifact: `shutdown-phase-lab`
- Package: `com.example.shutdownphase`
- Java: **17**
- Spring Boot: **3.5.x**
- Build: Maven, Packaging: Jar
- Dependency: **Spring Web**

Giữ `pom.xml` và `mvnw`/`mvnw.cmd` do Initializr tạo. Cấu trúc:

~~~text
shutdown-phase-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/shutdownphase/
    ShutdownPhaseLabApplication.java
    TimedLifecycle.java
    LifecycleBeans.java
    SlowController.java
  src/main/resources/application.properties
~~~

Cả bốn Java files dưới đây hoàn chỉnh khi đặt đúng package, với Maven classpath của Spring Boot. Java 17+ là đủ; không dùng API virtual threads trong ví dụ này. Không tạo thêm lớp có cùng public class name.

### 6.2. Main: đóng context có kiểm soát để đo budget

File `ShutdownPhaseLabApplication.java`:

~~~java
package com.example.shutdownphase;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import java.util.concurrent.TimeUnit;

@SpringBootApplication
public class ShutdownPhaseLabApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(
                        ShutdownPhaseLabApplication.class, args);

        boolean autoClose = context.getEnvironment()
                .getProperty("lab.auto-close", Boolean.class, true);

        if (!autoClose) {
            System.out.println("LAB_WEB_MODE_READY");
            return;
        }

        System.out.println("LAB_CLOSE_REQUESTED");
        long begin = System.nanoTime();
        context.close();
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - begin);
        System.out.println(
                "LAB_CLOSE_RETURNED elapsedMs=" + elapsedMs);
    }

    @EventListener(ContextClosedEvent.class)
    public void onContextClosed() {
        System.out.println("LAB_CONTEXT_CLOSED_EVENT");
    }
}
~~~

**Hai chế độ:** Mặc định `lab.auto-close=true` để `main` gọi `context.close()` ngay sau khi Boot hoàn thành startup, giúp đo thời gian close **ngoài JVM shutdown hook**. Khi `lab.auto-close=false`, ứng dụng giữ web server hoạt động cho phép thử HTTP và đợi tín hiệu dừng từ terminal/container.

Vì `ContextClosedEvent` thuộc context close lifecycle, marker `LAB_CONTEXT_CLOSED_EVENT` xảy ra trước các marker stop phase trong ví dụ. `elapsedMs` là **độ dài `context.close()`**, không phải thời gian JVM thực sự thoát, không tính khoảng chờ của shutdown hook bên ngoài hoặc external supervisor. Các stop threads do lab tạo có thể còn tồn tại khi close trả về vì timeout.

### 6.3. TimedLifecycle: mô phỏng cleanup bất đồng bộ

File `TimedLifecycle.java`:

~~~java
package com.example.shutdownphase;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.SmartLifecycle;

public final class TimedLifecycle implements SmartLifecycle {

    private final String name;
    private final int phase;
    private final long stopDelayMs;
    private final AtomicBoolean running = new AtomicBoolean();

    public TimedLifecycle(
            String name, int phase, long stopDelayMs) {
        if (stopDelayMs < 0) {
            throw new IllegalArgumentException(
                    "stopDelayMs must be >= 0");
        }
        this.name = name;
        this.phase = phase;
        this.stopDelayMs = stopDelayMs;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("LAB_START " + name
                    + " phase=" + phase);
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("LAB_STOP_DONE " + name
                    + " phase=" + phase);
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!isRunning()) {
            callback.run();
            return;
        }

        System.out.println("LAB_STOP_BEGIN " + name
                + " phase=" + phase
                + " delayMs=" + stopDelayMs);

        Thread cleanup = new Thread(() -> {
            try {
                Thread.sleep(stopDelayMs);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                System.out.println("LAB_STOP_INTERRUPTED " + name);
            } finally {
                // Khong co external I/O that trong lab.
                stop();
                System.out.println("LAB_STOP_CALLBACK " + name);
                callback.run();
            }
        }, "lab-cleanup-" + name);

        // Chi phuc vu demo: de thay callback den muon
        // sau khi context.close() tra ve vi phase timeout.
        cleanup.setDaemon(false);
        cleanup.start();
    }
}
~~~

**Cơ chế:**

1. `start()` cập nhật `running=true` khi container khởi chạy bean (mặc định auto-start). Trong lab không có external resource nào, nên flag mô phỏng chính xác.
2. `stop(Runnable)` **không block caller**. Nó tạo một thread cleanup rồi trả về. Vì vậy `DefaultLifecycleProcessor` có thể bắt đầu đếm/chờ callback với timeout phase.
3. `Thread.sleep(stopDelayMs)` chỉ mô phỏng delay. Nó **không** thực hiện bất kỳ nghiệp vụ hay network I/O thật.
4. `stop()` dùng compare-and-set để chỉ đánh dấu dừng một lần.
5. `callback.run()` xảy ra **sau khi** `stop()` trong `finally`, kể cả khi sleep bị interrupt. Với demo không có resource thật, interrupt có thể làm kết thúc quá trình dừng ngay.
6. Thread cleanup được đặt **non-daemon** để khi `context.close()` được gọi trực tiếp từ main, ta có cơ hội quan sát callback đến sau timeout. **Không sao chép cách giữ non-daemon thread như vậy vào production**: nó có thể giữ JVM sống, còn khi JVM đang thực thi shutdown hooks theo SIGTERM thì thread non-daemon cũng **không được bảo đảm** chạy xong trước khi JVM kết thúc.
7. Không tạo `new Thread` cho mỗi công việc dừng trong ứng dụng thật nếu đã có lifecycle owner và executor quản lý phù hợp. Ví dụ dùng nó duy nhất để minh họa rõ “processor ngừng chờ” khác “tác vụ thực sự dừng”.

Một component production cần giải phóng chính resource của nó và phối hợp task state. `stop()`/`stop(Runnable)` phải idempotent và chịu được gọi lặp; code mẫu được thiết kế cho **một lượt start/stop trong lab**, không phải state machine đầy đủ cho nhiều vòng restart.

### 6.4. Hai beans với phase cụ thể

File `LifecycleBeans.java`:

~~~java
package com.example.shutdownphase;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LifecycleBeans {

    @Bean("highPhase")
    SmartLifecycle highPhase(
            @Value("${lab.high-stop-ms:1000}") long delayMs) {
        return new TimedLifecycle("high", 200, delayMs);
    }

    @Bean("lowPhase")
    SmartLifecycle lowPhase(
            @Value("${lab.low-stop-ms:0}") long delayMs) {
        return new TimedLifecycle("low", 100, delayMs);
    }
}
~~~

Hai bean không có dependency bắt buộc vào nhau, nên phase là cơ sở kiểm thứ tự. Spring tự start từ phase 100 đến phase 200 và stop **ngược lại**. Đặt `@Bean` return type là `SmartLifecycle` để container nhận diện đúng interface. Vì `@Configuration(proxyBeanMethods=false)` không gọi các factory methods lẫn nhau, không có vòng proxy bean factory cần thiết ở đây.

**Mặc định lab:** high phase 200 dừng sau khoảng 1 giây; low phase 100 dừng gần như ngay lập tức. Có thể thay từng delay độc lập bằng command-line `--lab.high-stop-ms=6000` và `--lab.low-stop-ms=6000`.

### 6.5. Endpoint thử in-flight HTTP request

File `SlowController.java`:

~~~java
package com.example.shutdownphase;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SlowController {

    @GetMapping("/lab/slow")
    public ResponseEntity<String> slow(
            @RequestParam(defaultValue = "7000") long ms) {
        if (ms < 0 || ms > 15_000) {
            return ResponseEntity.badRequest()
                    .body("ms must be between 0 and 15000");
        }

        System.out.println("LAB_REQUEST_BEGIN ms=" + ms);
        try {
            Thread.sleep(ms);
            System.out.println("LAB_REQUEST_DONE ms=" + ms);
            return ResponseEntity.ok("completed");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            System.out.println("LAB_REQUEST_INTERRUPTED");
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("interrupted");
        }
    }
}
~~~

Endpoint này chỉ để mô phỏng một request đang chạy khi web server graceful stop. Dùng `Thread.sleep` trong request thread chỉ chấp nhận được trong **lab**; production nên có logic nghiệp vụ và timeout I/O đúng nghĩa. Không mở API ngủ lâu không có giới hạn ra Internet. HTTP code trả về khi kết nối bị shutdown còn phụ thuộc server và trạng thái connection.

### 6.6. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=shutdown-phase-lab

# Chi lang nghe local cho thi nghiem.
server.address=127.0.0.1
server.port=8080

# Spring Boot 3.5 mac dinh da graceful; khai bao ro.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=2s

# Main tu close sau khi run() theo mac dinh.
lab.auto-close=true

# Hai lifecycle beans cua lab.
lab.high-stop-ms=1000
lab.low-stop-ms=0
~~~

`2s` là giá trị được **chọn có chủ đích cho lab**, không phải giá trị mặc định của Spring Boot 3.5. Boot 3.5 mặc định là **30s** khi không override. Nếu muốn thử default, xóa/dừng override property hoặc truyền đúng giá trị bạn muốn; chú ý command-line argument được ưu tiên hơn cấu hình trong file theo cơ chế property sources của Boot.

Với `lab.auto-close=true`, web server khởi động rồi đóng nhanh; hãy dùng `--lab.auto-close=false` cho phép thử HTTP, nếu không sẽ không có thời gian gọi `/lab/slow`.

## 7. Thí nghiệm A: các phase hoàn tất trước timeout

### 7.1. Build

Từ thư mục project, Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw clean package
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd clean package
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar
~~~

Nếu version trong `pom.xml` khác `0.0.1-SNAPSHOT`, dùng tên JAR thực tế trong `target/`. Java nên là 17 trở lên; Spring Boot 3.5 có thể yêu cầu bản cao hơn nếu bạn tự chọn dependency/version khác.

### 7.2. Dấu mốc cần quan sát

Một đoạn log **minh họa hợp lệ** (bỏ log framework và web server):

~~~text
LAB_START low phase=100
LAB_START high phase=200
LAB_CLOSE_REQUESTED
LAB_CONTEXT_CLOSED_EVENT
LAB_STOP_BEGIN high phase=200 delayMs=1000
LAB_STOP_DONE high phase=200
LAB_STOP_CALLBACK high
LAB_STOP_BEGIN low phase=100 delayMs=0
LAB_STOP_DONE low phase=100
LAB_STOP_CALLBACK low
LAB_CLOSE_RETURNED elapsedMs=...
~~~

Các dòng `elapsedMs` và mức độ log của web server không cố định; điều quan trọng là:

- `LAB_START low` xuất hiện trước `LAB_START high` khi auto-start theo phase.
- `LAB_STOP_BEGIN high` xảy ra trước `LAB_STOP_BEGIN low`.
- Vì high stop mất ~1 giây và ngân sách phase là 2 giây, `LAB_STOP_CALLBACK high` đến **trước** khi bắt đầu stop low.
- `context.close()` trở về sau các callback trong điều kiện không có phase khác bị chặn; HTTP web server infrastructure có thể thêm chút thời gian overhead.
- Các hook/context destruction vẫn có thể in thêm log; không so khớp stdout toàn chương trình từng byte.

Đây là **positive control**: timeout đủ lớn cho component trong phase 200. Chỉ khi nhìn callback mới kết luận component đã hoàn thành hợp đồng stop.

## 8. Thí nghiệm B: phase 200 vượt timeout nhưng phase 100 vẫn chạy

Giữ `spring.lifecycle.timeout-per-shutdown-phase=2s` và thay delay high bằng 6 giây:

~~~bash
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --lab.high-stop-ms=6000
~~~

Ứng dụng sẽ gọi `context.close()` sau startup. Một đoạn marker **kỳ vọng theo quan hệ thời gian**:

~~~text
LAB_CLOSE_REQUESTED
LAB_CONTEXT_CLOSED_EVENT
LAB_STOP_BEGIN high phase=200 delayMs=6000

... processor da cho gan 2000ms ...
... log shutdown phase 200 con bean chua xong, tuy logger ...

LAB_STOP_BEGIN low phase=100 delayMs=0
LAB_STOP_DONE low phase=100
LAB_STOP_CALLBACK low
LAB_CLOSE_RETURNED elapsedMs=...

... sau do high cleanup thread co the van hoat dong ...
LAB_STOP_DONE high phase=200
LAB_STOP_CALLBACK high
~~~

Không dùng những dòng dấu ba chấm làm stdout literal; chúng là **giải thích các mốc**. Trong lab `context.close()` chạy ngoài JVM shutdown hook và high cleanup thread non-daemon, nên có cơ hội thấy `LAB_STOP_DONE high` **sau** `LAB_CLOSE_RETURNED`. Điều đó chứng minh: timeout khiến processor **ngừng chờ callback**, không tự cancel sleep và không tự đảm bảo mọi tài nguyên bên ngoài đã được đóng.

Kỳ vọng `elapsedMs` khoảng 2 giây cộng overhead của web server, phase thấp và destruction, **không phải đúng 2000ms**. Nếu hệ thống quá chậm hoặc infrastructure có phase riêng, số có thể cao hơn đáng kể.

### 8.1. Đọc đúng hiện tượng

| Quan sát | Kết luận được phép | Không được suy ra |
|---|---|---|
| Phase 200 bị timeout | Processor không nhận callback trong ngân sách 2s | Worker chắc chắn đã bị hủy |
| Phase 100 vẫn nhận stop | Processor đã tiến tiếp sau khi timeout | Dependency high đã release mọi resource |
| `LAB_CLOSE_RETURNED` xuất hiện trước callback high | Context đóng xong phần xử lý theo budget trong lab | Toàn bộ process đã thoát |
| Callback high xuất hiện muộn | Thread cleanup demo vẫn hoạt động sau thời điểm chờ | Trong SIGTERM production callback chắc chắn sẽ kịp |
| Bean destroy chạy trong lúc high chưa callback | Có nguy cơ cleanup overlap nếu thiết kế xấu | Spring rollback được external operations |

### 8.2. Tại sao callback đến muộn rất nguy hiểm?

Giả sử worker high phase 200 cần adapter low phase 100 để commit kết quả. Khi high mất 6 giây, ngân sách chỉ 2 giây, processor bắt đầu dừng adapter low trong khi worker high còn dùng nó. Có thể xảy ra exception do connection đóng, mất ack, message redelivery hoặc dữ liệu chưa bền vững.

Không có một con số timeout nào tự sửa được thiết kế phụ thuộc. Cần:

- Dừng **intake** trước khi worker drain.
- Worker có deadline và cách cancel hợp tác.
- Dừng dependency **sau khi worker hoàn tất**, không chỉ sau khi processor hết kiên nhẫn.
- Phối hợp `depends-on` và phase theo nhu cầu thật.
- Lưu kết quả/offset/transaction đúng thời điểm và có idempotency khi retry.

## 9. Thí nghiệm C: hai phase cùng chậm

Gọi:

~~~bash
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --lab.high-stop-ms=6000 --lab.low-stop-ms=6000
~~~

Với ngân sách **2s cho mỗi phase**, processor có thể chờ xấp xỉ 2s ở phase 200 và **thêm** xấp xỉ 2s ở phase 100, rồi `close()` trả về sau khoảng **4s cộng overhead** (tại điều kiện không có phase chậm khác). Đây là minh họa rõ nhất rằng property **không** là deadline tổng 2s.

Nếu có 10 phases cùng timeout 20s, không thể khẳng định shutdown toàn process luôn dưới 20s. Tổng thời gian chờ lifecycle riêng có thể cao hơn, còn `@PreDestroy` và cleanup khác không tự nằm dưới cùng một ngân sách đó.

Trong ứng dụng thật, các phase có thể dừng nhanh hơn timeout nhiều lần; không nên tính tổng như tất cả đều chờ hết hạn. Dùng **observed p95/p99 + worst-case budget** để đặt policy.

## 10. Thí nghiệm D: graceful shutdown của HTTP request đang xử lý

Để ứng dụng chạy lâu và nhận request, bắt đầu trong terminal riêng:

~~~bash
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --lab.auto-close=false --spring.lifecycle.timeout-per-shutdown-phase=10s
~~~

Khi thấy `LAB_WEB_MODE_READY`, dùng terminal khác:

~~~bash
curl -i "http://127.0.0.1:8080/lab/slow?ms=7000"
~~~

Đợi console server có `LAB_REQUEST_BEGIN ms=7000`, rồi gửi Ctrl+C vào terminal chạy ứng dụng hoặc dùng SIGTERM hợp lệ để đóng process. Không dùng `kill -9` hoặc chức năng IDE terminate có thể giết ngay.

**Khi timeout phase đủ lớn**, embedded Tomcat graceful shutdown có cơ hội cho request đang xử lý kết thúc, nên curl có thể nhận HTTP 200, body `completed`. Điều kiện thực tế còn phụ thuộc vào server, cách tín hiệu đến process, trạng thái kết nối, timing và có phần khác đang đóng trước request hay không. Không khẳng định một lệnh thử trên mọi OS sẽ luôn nhận 200.

Thử lại bằng một process mới, dùng `--spring.lifecycle.timeout-per-shutdown-phase=2s` và cùng request 7 giây. Khi web server stop phase đạt ngân sách ngắn hơn request, kết nối có thể bị cắt hoặc client nhận lỗi/trạng thái tùy embedded server và network. Với **Tomcat, Jetty hoặc Reactor Netty**, new connections có thể bị chặn ở network layer; với **Undertow của Boot 3.5**, đường chặn request mới có thể trả HTTP **503**. Không ép phải thấy 503 trên curl của một request in-flight hoặc dùng status code đó làm phép thử duy nhất.

### 10.1. Phân biệt ba thời gian

- `spring.lifecycle.timeout-per-shutdown-phase`: budget chờ lifecycle beans theo **nhóm phase**, bao gồm giai đoạn web server graceful stop trong cơ chế Boot hỗ trợ.
- `server.tomcat.connection-timeout` (nếu có): chờ về mặt protocol/kết nối, **không** thay budget dừng toàn context.
- Timeout xử lý nghiệp vụ/HTTP client: giới hạn các thao tác bên trong controller, không được Spring lifecycle tự tính thành deadline theo request.

Nếu application có custom executor xử lý request, async servlet requests, streaming hoặc gRPC, phải kiểm tra cơ chế drain tương ứng; đừng dựa hoàn toàn vào ví dụ `Thread.sleep` của controller đồng bộ.

## 11. Timeout per phase không thay các timeout khác

| Timeout/hạn chót | Chủ thể áp dụng | Hành vi khi hết | Có cùng nghĩa với shutdown phase? |
|---|---|---|---|
| `spring.lifecycle.timeout-per-shutdown-phase` | Spring `LifecycleProcessor` | Ngừng chờ callbacks của phase, xử lý tiếp theo | Chính nó |
| `spring.task.execution.shutdown.await-termination-period` | Executor do Boot quản lý phù hợp | Thời gian chờ task executor | Không |
| `spring.task.scheduling.shutdown.await-termination-period` | Scheduler do Boot quản lý phù hợp | Thời gian chờ scheduled tasks | Không |
| `ExecutorService.awaitTermination(...)` | Java executor do code sở hữu | Trả false khi timeout; không tự interrupt | Không |
| JDBC connection/query timeout | JDBC driver/pool/database | Acquire/query có thể fail hoặc cancel theo contract | Không |
| HTTP request/read timeout | HTTP client/library | Request fail/cancel theo policy | Không |
| Kafka/RabbitMQ/JMS consumer shutdown | Listener container/broker client | Stop polling/ack/close theo timeout riêng | Không |
| `terminationGracePeriodSeconds` | Kubernetes kubelet/container runtime | Có thể gửi SIGKILL sau grace | Không |
| systemd `TimeoutStopSec` | systemd | Có thể kill service nếu stop quá lâu | Không |
| CI/deploy rollout timeout | CD controller/platform | Báo thất bại/rollback theo công cụ | Không |
| Business operation deadline | Nghiệp vụ | Retry/cancel/compensate theo hợp đồng | Không |

Một ứng dụng có thể đặt shutdown phase 20s, HTTP client call timeout 60s, và Kubernetes grace chỉ 15s. Khi đó những cấu hình “đúng cú pháp” vẫn **mâu thuẫn về ngân sách**. Platform có thể kill process trước khi Spring chờ hết 20s; ngược lại, tăng Kubernetes grace quá cao có thể giữ Pod terminating lâu hơn cần thiết.

## 12. Kubernetes: tính deadline từ ngoài vào trong

Kubernetes quy định thời hạn Pod terminate qua `terminationGracePeriodSeconds`. Mặc định của Pod thường là **30 giây**, nhưng Deployment/Pod hoặc thao tác delete có thể override. Grace period tính cả `preStop` hook (nếu có), thời gian signal được gửi, shutdown trong JVM và việc container thật sự thoát.

Đoạn manifest **thuộc phần `spec.template.spec` của một Deployment**, không phải full Deployment YAML:

~~~yaml
terminationGracePeriodSeconds: 45
containers:
  - name: app
    image: example/app:1.0
    ports:
      - containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
~~~

Ví dụ này chỉ minh họa **termination budget + readiness probe**; muốn chạy cần image thật, Actuator dependency và cấu hình probes tương ứng. Dùng `example/app:1.0` như ký hiệu hình dung kiến trúc, không phải image đã xác minh tồn tại.

### 12.1. Ngân sách nhiều tầng

Một cách lập ngân sách gần đúng (để thiết kế, **không** phải công thức runtime bắt buộc):

~~~text
T_grace_platform
    >= T_preStop
     + T_drain_or_propagation_margin
     + T_lifecycle_phases_expected
     + T_destroy_other
     + T_termination_overhead
~~~

Một số bước chạy song song hoặc overlap; không cộng trùng thời gian nếu instrumentation chứng minh overlap. Nhưng khi sizing cần bảo đảm hệ thống có khoảng trống cho các tình huống xấu có thể xảy ra.

Ví dụ: preStop cần 5s, web drain dự kiến tối đa 15s, worker stop 10s, bean destruction 3s và margin 5s → khoảng **38s** trong kịch bản phải chờ tuần tự. Đặt `terminationGracePeriodSeconds=45` cho một ngân sách minh họa; đo lại p95/p99 và worst case trước khi dùng thật. **Đây là bài toán giả định**, không phải khuyến nghị mặc định cho mọi dịch vụ.

### 12.2. PreStop và signal timing

Theo Kubernetes pod termination flow, khi Pod bị đánh dấu terminating, kubelet có thể chạy `preStop` hook rồi gửi TERM tới process. Grace period đã bắt đầu chạy; preStop kéo dài làm **giảm** thời gian thực tế còn lại cho Spring shutdown. Nếu process là Java chạy sau shell wrapper không forward SIGTERM đúng, Java có thể không nhận graceful signal và bị kill khi hết grace.

Vì vậy:

- Ưu tiên container entrypoint có signal forwarding đúng; ví dụ `exec java ...` trong script nếu script cần thiết.
- Không dùng một `preStop sleep` dài vô hạn chỉ để “chờ load balancer”.
- Đo thời gian EndpointSlice/readiness propagation và in-flight requests thật.
- Cần budget hợp lý cho consumer ack, flush, checkpoint, resource release.
- Khi grace hết, kubelet có thể buộc dừng; `finally`/`@PreDestroy`/callback **không được bảo đảm** chạy khi bị kill cưỡng bức.

### 12.3. Timeout processor không phải công tắc “Pod luôn thoát đúng giờ”

Nếu worker stop đồng bộ bị kẹt, JDBC không timeout hoặc scheduler giữ non-daemon threads, process có thể kéo dài. Dù Spring đã hết timeout của một phase, OS/container vẫn có thể còn các phần tử chưa đóng. Với `SIGTERM`, JVM chạy hooks nhưng cũng có thể kết thúc khi hooks hoàn tất mà các asynchronous cleanup threads chưa xong. Đó là lý do **mọi task dừng phải có deadline và cơ chế cancellation hợp tác**, không chỉ property ở cấp framework.

## 13. Quản lý tác vụ nền khi shutdown

### 13.1. Ngừng nhận việc trước khi drain

Một background consumer/service có thể thực hiện:

~~~text
RUNNING
   |
   +-- nhận tín hiệu stopping
   v
QUIESCING: từ chối job mới, tạm ngừng poll/message intake
   |
   v
DRAINING: đợi hoặc hủy in-flight work theo deadline
   |
   v
FLUSHING: ghi checkpoint/offset/result đã commit hợp lệ
   |
   v
CLOSED: đóng clients/executors và hoàn thành callback
~~~

Đừng chỉ set `isRunning=false` rồi gọi callback nếu thread và sockets vẫn đang hoạt động. Nếu in-flight task có thể gửi external side effect mà process bị kill giữa chừng, phải có idempotency key, queue redelivery/ack semantics hoặc durable job store để xử lý lại an toàn.

### 13.2. Ví dụ ExecutorService shutdown có deadline

Đoạn Java minh họa bên trong một bean sở hữu `ExecutorService`:

~~~java
private void terminateExecutor(ExecutorService executor) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(3, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                System.err.println(
                        "Executor did not terminate within budget");
            }
        }
    } catch (InterruptedException ex) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

Đây là **method snippet**; cần imports `ExecutorService`/`TimeUnit` và được gọi bởi owner có lifecycle phù hợp. `shutdownNow()` chỉ là nỗ lực ngắt tác vụ, không cưỡng ép I/O không hợp tác phải dừng. Nếu muốn Spring chờ asynchronous stop callback, đặt lời gọi terminate trong worker dừng riêng, hoàn tất hoặc áp chính sách fail rồi mới gọi callback.

**Không dùng một `ExecutorService` vừa để chạy các job thường vừa để thực hiện callback dừng cuối cùng** nếu lúc shutdown executor đó đã từ chối task. Stop method cần có đường fallback an toàn, nếu không callback có thể bị bỏ qua.

### 13.3. Khi @PreDestroy vẫn chạy lâu hơn property

`@PreDestroy`/`DisposableBean.destroy()` là pha destruction của Spring beans, chạy **sau** lifecycle stop bình thường. Property `timeout-per-shutdown-phase` không tự áp deadline cưỡng bức cho một method `@PreDestroy` đang block. Vì thế đoạn mã:

~~~java
@PreDestroy
public void destroy() throws InterruptedException {
    Thread.sleep(60_000);
}
~~~

là **snippet phản ví dụ**: đặt trong Spring bean và có import `jakarta.annotation.PreDestroy`. Dù đặt shutdown phase timeout 2s, đoạn này có thể vẫn trì hoãn việc đóng context thêm khoảng 60s (nếu không bị process kill). Không đưa `sleep` này vào ứng dụng thật; dùng deadline thực của client và cleanup idempotent.

### 13.4. Phân biệt worker được framework quản lý với thread tự tạo

Spring có thể quản lý task executor, task scheduler, messaging listener container qua lifecycle callbacks. Nhưng một `new Thread(...).start()` hoặc `Executors.newCachedThreadPool()` được giữ trong field mà không có `@PreDestroy`/`SmartLifecycle` sẽ **không tự động được dừng chỉ vì tên property này**.

Muốn shutdown đáng tin, chỉ định rõ owner đóng tài nguyên, đường dừng và tính bền vững của trạng thái. Nếu tài nguyên đã được framework quản lý, đừng tự double-close; đọc hợp đồng của thư viện và cấu hình timeout tương ứng.

## 14. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần xét | Bằng chứng/biện pháp |
|---|---|---|
| Đặt `2s` nhưng tổng shutdown 8s | Nhiều phase hoặc destroy/hook khác | Log đầu/cuối từng phase và `context.close()` |
| Phase timeout nhưng worker vẫn ghi log | Callback chưa đến, thread chưa bị kill | So `LAB_CLOSE_RETURNED` với `LAB_STOP_CALLBACK` |
| Cấu hình 20s nhưng request 30s vẫn bị cắt | Web server graceful phase thiếu budget; platform grace ngắn | So HTTP start/end, Tomcat logs và SIGTERM timing |
| Không thấy callback stop | Quên `callback.run()` hoặc bean chưa running | Kiểm `stop(Runnable)`, `isRunning()` và phase |
| Callback đến trước khi worker thật sự dừng | Gọi callback quá sớm | Thêm metric in-flight, resource close marker |
| Dừng bean phase thấp trước worker phase cao | Phase/dependency thiết kế sai hoặc gọi stop trực tiếp | Kiểm `getPhase()`, `depends-on`, lifecycle processor |
| Không có graceful behavior trong IDE | IDE dùng lệnh terminate không gửi signal phù hợp | Thử console JAR và SIGTERM |
| Có `ContextClosedEvent` nhưng shutdown treo | Event không chứng minh stop/destroy đã hoàn tất | Xem callback, thread dump, external timeouts |
| Spring Boot 3.5 “default 10s” trong tài liệu nhóm | Nhầm Javadoc Framework với Boot config | Boot common properties: default **30s** |
| ThreadPoolTaskExecutor dừng sớm làm mất jobs | Queue RAM và policy executor không chờ | Durable source, retry/ack/idempotency |
| Toàn Pod bị kill trước callback | Kubernetes grace hết hoặc entrypoint không forward signal | Kiểm Pod events, preStop, TERM/SIGKILL |
| Connection DB không về pool | I/O/transaction chưa xong hoặc leak | Hikari active/pending, connection close markers |
| Web server đã dừng nhưng broker consumer còn nhận | Không có bước quiesce hoặc phase/order sai | Stop intake, consumer lifecycle, broker offsets |
| Shutdown timeout set quá cao | Giữ deployment/rollout lâu và làm quá hạn platform | Đo p99 drain và đặt trần hợp lý |
| Shutdown timeout set quá thấp | Phụ thuộc bị đóng khi worker chưa flush | Tăng deadline phù hợp, cải thiện cleanup không block |
| App nhận traffic sau readiness refusing | Probe/route propagation delay hoặc direct access | Kiểm service route vs Pod IP, app admission |
| Không thấy `LAB_STOP_DONE` sau Ctrl+C | JVM shutdown hook có thể hoàn tất rồi JVM exit | Dùng chế độ `context.close()` trực tiếp của lab |
| Log phase không có đúng thời gian kỳ vọng | Scheduling, infrastructure beans, I/O, logging | Đo wall-clock/monotonic time và nhiều lần |
| Thay property nhưng không có tác dụng | Custom LifecycleProcessor hoặc config bị override | Kiểm environment/config metadata của app đang chạy |

### 14.1. Bốn kiểu bằng chứng không tương đương

- **`ContextClosedEvent`:** bắt đầu close, chưa phải mọi task đã dừng.
- **`LAB_STOP_BEGIN`:** bean đã nhận yêu cầu dừng, chưa có cleanup.
- **`LAB_STOP_CALLBACK`:** bean đã báo hoàn tất thủ tục dừng theo contract mà nó tự cài đặt.
- **`LAB_CLOSE_RETURNED`:** API close trả về; không chắc JVM đã thoát hay mọi external side effect đã hoàn tất.

Một log “Shutting down...” hoặc việc container biến mất khỏi network chưa đủ chứng minh không mất job. Cần thêm business-state check/ack logs và resource metrics.

## 15. Tính ngân sách shutdown theo tình huống thật

### 15.1. Công việc ngắn, restart thường xuyên

Web request p99 3s, worker có thể drain 4s, broker close 1s, destruction 1s. Nếu các phần cần đi tuần tự, một ngân sách ví dụ có margin như 15–20s có thể hợp lý; nhưng phải đối chiếu web server phase, worker phase, platform budget và kiểm thử dưới tải. Không đặt `timeout-per-shutdown-phase=1m` chỉ vì “càng lớn càng an toàn”.

### 15.2. Công việc dài 5 phút

Nếu job có thể chạy 5 phút nhưng Kubernetes chỉ cho terminate 30s, tăng lifecycle timeout lên 5m **không làm 5 phút của job được bảo đảm**. Cần chuyển job sang durable queue với ack/redelivery, checkpoint hoặc lease để resume/retry; shutdown chỉ cần đủ thời gian ngừng nhận mới, commit phần đã hoàn thành và bàn giao/đánh dấu phần chưa xong.

### 15.3. Nhiều replicas cùng giảm lưu lượng

Nếu tất cả replica cùng vào rolling termination, Service có thể thiếu capacity. Readiness/drain policy phải phối hợp với rollout strategy (`maxUnavailable`, `maxSurge` tương ứng), autoscaling và external system quotas. Tăng deadline chỉ là một phần; không thay thế kế hoạch còn bao nhiêu replica đang phục vụ.

### 15.4. I/O không hợp tác

Một external HTTP call không có timeout có thể giữ shutdown dở dang vô hạn. Thiết kế tối thiểu cần connect/read/request timeout, cancellation và finally cleanup. Nếu client API không hỗ trợ interrupt, đánh dấu phần dừng không chắc chắn và dựa vào platform deadline + idempotency/reconciliation để bảo vệ nghiệp vụ; không giấu lỗi bằng callback thành công giả.

## 16. Thử nghiệm bổ sung: cấu hình khác nhau và đảm bảo QA

### 16.1. Thử 2s, 5s và 10s

Dùng cùng project, `lab.high-stop-ms=6000`, `lab.low-stop-ms=0`. Chạy riêng từng tiến trình:

~~~bash
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --spring.lifecycle.timeout-per-shutdown-phase=2s --lab.high-stop-ms=6000
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --spring.lifecycle.timeout-per-shutdown-phase=5s --lab.high-stop-ms=6000
java -jar target/shutdown-phase-lab-0.0.1-SNAPSHOT.jar --spring.lifecycle.timeout-per-shutdown-phase=10s --lab.high-stop-ms=6000
~~~

**Không chạy đồng thời** ba lệnh khi cùng muốn mở cổng 8080; thực hiện tuần tự hoặc thêm `--server.port=0` để chọn cổng ngẫu nhiên cho chế độ tự đóng. Với 2s và 5s, phase 200 có thể hết ngân sách trước khi callback high đến; với 10s, callback high 6s thường đến trước timeout. Dựa vào marker và elapsed thực tế, không dùng giá trị được giả định thay cho đo đạc.

### 16.2. Đo duration không dùng sleep giả làm kết quả thật

Một log duration từ `System.nanoTime()` như trong main hữu ích để đo elapsed trong **cùng JVM**; không dùng `System.currentTimeMillis()` tính duration nếu đồng hồ hệ thống có thể nhảy do NTP. Trong production, thêm Micrometer timers/histograms, trace span cho quiesce/drain/cleanup, và log phase/bean IDs một cách có kiểm soát.

### 16.3. Checklist QA cho một lần deploy

| Kiểm thử | Input/điều kiện | Kết quả phải kiểm chứng |
|---|---|---|
| Normal stop | High delay 1s, phase timeout 2s | High callback trước stop low; close bình thường |
| Timeout một phase | High delay 6s, timeout 2s | Low nhận stop sau khi high hết budget, callback high có thể muộn |
| Hai phase đều timeout | High/low 6s, timeout 2s | Tổng chờ có thể khoảng 4s; không phải hard 2s |
| Request in-flight | HTTP sleep 7s, graceful 10s | Có cơ hội hoàn tất; đo response và logs |
| HTTP grace không đủ | HTTP sleep 7s, graceful 2s | Có thể bị cut; phân biệt network failure/status |
| SIGTERM thực | Console/JAR mode web | Có đóng context và callbacks trước platform kill không? |
| Hard kill | Container SIGKILL | Không bảo đảm cleanup; durable redelivery phải xử lý |
| Repeated startup/stop | Restart nhiều lần | Không leak thread, FD, connection, consumer |
| Bad stop() | Stop đồng bộ block lâu | Timeout phase có thể không preempt method |
| Callback missing | Cố tình không callback trong bản copy | Processor chờ đến timeout và log còn bean |
| Worker dependency | Worker cần broker khi stop | Order worker stop trước broker close |
| K8s termination | Grace chứa preStop + drain + stop | Pod không bị kill trước deadline đã thiết kế |

**Ghi chú:** Những tình huống cố tình làm lỗi callback, leak hoặc hard kill chỉ chạy trong lab cô lập với dữ liệu giả. Không tạo outage thực để kiểm tra quy trình shutdown.

## 17. Câu hỏi kiểm tra kiến thức

**1. `timeout-per-shutdown-phase=20s` có nghĩa app nhất định dừng trong 20 giây không?** Không. Đây là budget **mỗi nhóm phase** của lifecycle processor; còn nhiều phase và cleanup khác.

**2. Tại sao một bean `SmartLifecycle` phải gọi `callback.run()`?** Để báo phase processor biết nó đã hoàn tất thủ tục stop; nếu không, processor có thể đợi đến timeout.

**3. Spring có interrupt một thread bất đồng bộ ngay khi hết timeout không?** Không có bảo đảm đó từ property. Timeout chờ callback không phải executor cancellation.

**4. Nếu stop method đồng bộ chạy I/O không timeout trong 30s nhưng property là 2s thì sao?** Có thể vẫn block vì processor chưa lấy lại control để áp budget chờ callback.

**5. Hai bean cùng phase, mỗi bean dừng 8 giây, timeout phase 10 giây: mất 16 giây?** Nếu cả hai triển khai asynchronous stop và được yêu cầu dừng trong cùng phase, chúng chia sẻ một budget chờ. Nhưng nếu implementation block đồng bộ hoặc dependency buộc tuần tự, thời gian thực tế có thể khác; không suy luận máy móc 8 hay 16 giây chỉ từ con số.

**6. Tại sao nên dừng worker trước database adapter?** Worker có thể còn cần adapter để flush/commit/ack trong shutdown; đóng adapter quá sớm gây lỗi và mất dữ liệu.

**7. Boot 3.5 mặc định property là 10s hay 30s?** **30s**. Javadoc `DefaultLifecycleProcessor` framework riêng dùng 10s.

**8. Có thể thấy `ContextClosedEvent` rồi cho rằng đã an toàn release tài nguyên không?** Không. Event này nằm trước lifecycle stop/destroy.

**9. Graceful web server shutdown và `@PreDestroy` của một bean có cùng timeout không?** Không. Chúng thuộc các giai đoạn và hợp đồng khác nhau.

**10. Kubernetes preStop 10s, grace 30s có còn 30s cho Spring không?** Không, preStop tiêu thụ thời hạn grace; còn lại phải trừ thời gian đã dùng và overhead.

**11. Khi SIGKILL, callback `SmartLifecycle` có chắc chạy không?** Không. Cần thiết kế durability/rollback/redelivery đúng contract.

**12. Khi nhiệm vụ chạy lâu hơn termination budget, giải pháp là gì?** Durable queue, idempotency, checkpoint/lease, drain/cancel có deadline; không chỉ kéo dài property.

## 18. Checklist trước khi đưa vào production

- [ ] Xác nhận Spring Boot/Spring Framework phiên bản đang dùng và default property thực tế.
- [ ] Ghi rõ `spring.lifecycle.timeout-per-shutdown-phase` với đơn vị `ms/s/m`.
- [ ] Liệt kê những `SmartLifecycle` đang chạy, `getPhase()` và dependency graph.
- [ ] Xác nhận stop order theo phase giảm và `depends-on` đúng nghiệp vụ.
- [ ] Mỗi `stop(Runnable)` gọi callback **sau** khi cleanup được hoàn tất theo policy.
- [ ] Không block vô hạn bên trong method stop hoặc destroy; mọi I/O có timeout riêng.
- [ ] Dừng nhận request/job/message trước khi drain queue và đóng downstream dependencies.
- [ ] Phân biệt HTTP graceful phase với task-executor shutdown và bean destruction.
- [ ] Kiểm tra in-flight HTTP request dài hơn và ngắn hơn grace dưới tải thật.
- [ ] Ghi log và metric shutdown duration theo context/phase/bean, có marker completion.
- [ ] Xác nhận tác vụ dài có idempotency/durable recovery nếu Pod bị kill.
- [ ] Tính `terminationGracePeriodSeconds` gồm preStop, routing margin, drain, callbacks và overhead.
- [ ] Đảm bảo JVM process nhận SIGTERM thực, không bị shell wrapper nuốt tín hiệu.
- [ ] Quan sát cảnh báo phase timeout và cleanup chưa xong; không bỏ qua log warning/info.
- [ ] Thử lỗi callback, dependency outage và interrupt trong lab an toàn.
- [ ] Không coi thời gian `context.close()` bằng thời gian JVM/container thật sự hoàn tất.
- [ ] Test rolling deployment không rút toàn bộ capacity cùng lúc.

## 19. Tài liệu chính thức

1. Spring Boot 3.5 — **Graceful Shutdown**, diễn giải web server stop phase và `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
2. Spring Boot 3.5 — **Common Application Properties**, default `spring.lifecycle.timeout-per-shutdown-phase=30s` và `server.shutdown=graceful`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
3. Spring Framework 6.2 — **DefaultLifecycleProcessor Javadoc**, phase grouping, timeout và `setTimeoutForShutdownPhase(...)`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
4. Spring Framework 6.2 — **SmartLifecycle Javadoc**, `stop(Runnable callback)` và phase: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/SmartLifecycle.html
5. Spring Framework 6.2 — **Bean Lifecycle and Destruction**: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
6. Spring Boot 3.5 — **Task Execution and Scheduling**, executor/scheduler shutdown configs: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
7. Kubernetes — **Pod Lifecycle, Termination Flow, preStop và terminationGracePeriodSeconds**: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
8. Java SE 17 — **ExecutorService**, `shutdownNow`, `awaitTermination` và interruption: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html

**Tổng kết:** `spring.lifecycle.timeout-per-shutdown-phase` đặt một **giới hạn thời gian chờ callback cho từng shutdown phase**, giúp lifecycle processor không phải đợi vô hạn một bean SmartLifecycle dừng bất đồng bộ. Nó **không tự ngắt I/O, không bảo đảm toàn JVM dừng trong N giây, và không thay thế platform termination budget**. Một hệ thống dừng an toàn là hệ thống biết ngừng intake, drain/cancel có deadline, dừng worker trước dependency, gọi callback đúng thời điểm, đo duration và có idempotency/durability khi shutdown không hoàn tất.