# Dừng có callback hoàn tất và giới hạn thời gian trong Spring Framework

## Mục tiêu học tập

Một ứng dụng Spring có thể chứa HTTP server, message consumer, scheduler, executor, kết nối mạng hoặc những tiến trình nền cần thời gian để ngừng nhận công việc và hoàn tất công việc đang chạy. Khi đóng `ApplicationContext`, gọi `close()` trên tài nguyên ngay lập tức đôi khi làm mất việc; ngược lại, đợi một worker vô thời hạn có thể khiến quá trình shutdown bị treo.

Spring Core Container giải quyết phần **điều phối vòng đời context** bằng `Lifecycle`, `SmartLifecycle`, `LifecycleProcessor` và triển khai mặc định `DefaultLifecycleProcessor`. Cụ thể, `SmartLifecycle.stop(Runnable callback)` cho phép một component bắt đầu dừng, hoàn thành bất đồng bộ rồi **báo đã dừng bằng callback**. Container chờ các callback của **mỗi shutdown phase** trong khoảng thời gian cấu hình.

Sau bài học, bạn có thể:

- Hiểu tại sao `stop(Runnable)` có callback và khác `stop()` thường.
- Viết `SmartLifecycle` tự động khởi động, dừng bất đồng bộ và luôn báo hoàn tất đúng thời điểm.
- Sắp thứ tự shutdown theo `getPhase()` và dependency.
- Cấu hình timeout chung hoặc timeout riêng cho từng phase bằng `DefaultLifecycleProcessor`.
- Hiểu chính xác timeout tác động vào việc **chờ** của container, không phải lệnh cưỡng bức dừng thread.
- Phân biệt stop phase với `@PreDestroy`, `DisposableBean.destroy()`, và graceful shutdown HTTP của Spring Boot.
- Kiểm thử đường thành công, lỗi, timeout, race condition và shutdown cưỡng bức.

## 1. Lifecycle stop nằm ở đâu khi đóng ApplicationContext?

Trong một lần đóng context bình thường, có thể khái quát:

~~~text
ApplicationContext.close()
       |
       v
Phát ContextClosedEvent
       |
       v
LifecycleProcessor.onClose()
       |
       +-- Xác định SmartLifecycle/Lifecycle đang chạy
       +-- Gom theo phase và quan hệ phụ thuộc
       +-- Stop các phase từ cao xuống thấp
       +-- Với SmartLifecycle: gọi stop(Runnable callback)
       +-- Chờ callback của các thành phần trong phase đến timeout
       |
       v
Hủy các singleton (destruction callbacks)
       |
       +-- @PreDestroy
       +-- DisposableBean.destroy()
       +-- @Bean(destroyMethod = "...")
       |
       v
Hoàn tất đóng context
~~~

**Đây là quy trình shutdown bình thường.** Ở một số tình huống bất thường, ví dụ context refresh thất bại hoặc bean bị hủy ngoài luồng đóng context, destruction method có thể được gọi mà không có stop signal trước đó. Vì vậy một bean đang giữ tài nguyên phải bảo đảm cleanup đủ an toàn cả khi `stop()` chưa từng chạy.

Các từ “stop” và “destroy” có trách nhiệm khác nhau:

| Hoạt động | Mục đích | Cơ chế thường dùng |
| --- | --- | --- |
| Stop | Ngừng nhận việc; cho việc đang chạy cơ hội kết thúc | `Lifecycle.stop()` / `SmartLifecycle.stop(Runnable)` |
| Chờ hoàn tất | Điều phối các component trước khi tiến sang phase khác | `DefaultLifecycleProcessor` + callback/timeout |
| Destroy | Đóng tài nguyên cuối cùng, giải phóng bean | `@PreDestroy`, `DisposableBean`, `destroyMethod` |
| Tắt tiến trình | Hệ điều hành/runtime kết thúc JVM | SIGTERM, shutdown hook, container orchestration |

Không phải mọi Spring bean đều cần `SmartLifecycle`. Với một object chỉ có method `close()` chạy nhanh, `@PreDestroy` hoặc `@Bean(destroyMethod = "close")` có thể đã đủ. `SmartLifecycle` đặc biệt hữu ích khi cần **ngừng có điều phối**, **phase** và **báo completion của hoạt động bất đồng bộ**.

## 2. Ba interface điều phối vòng đời

### 2.1. Lifecycle: khởi động/dừng đồng bộ cơ bản

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Đây là chữ ký giản lược của `org.springframework.context.Lifecycle` để tham khảo; không phải file cần tạo trong dự án.

- `start()` yêu cầu component bắt đầu hoạt động.
- `stop()` yêu cầu component dừng; theo contract, khi method trở về, implementation nên hoàn tất phần dừng mà nó chịu trách nhiệm.
- `isRunning()` phản ánh trạng thái hoạt động thực của component.

Một `Lifecycle` thông thường không mặc nhiên auto-start khi context refresh. Spring có thể điều khiển nó qua `context.start()/stop()` và lifecycle processor. Khi đóng context, processor xử lý các beans `Lifecycle` đang chạy.

### 2.2. SmartLifecycle: phase, auto-start và callback

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
    // getPhase() đến từ Phased.
}
~~~

Đây cũng là chữ ký khái quát. Spring Framework 6.x có **default methods** đối với một số method trong `SmartLifecycle`: `isAutoStartup()` mặc định trả `true`, `getPhase()` mặc định là `SmartLifecycle.DEFAULT_PHASE` và `stop(Runnable)` có implementation mặc định ủy nhiệm cho `stop()` rồi gọi callback.

Có thể override để điều khiển rõ:

~~~java
@Override
public boolean isAutoStartup() {
    return true;
}

@Override
public int getPhase() {
    return 100;
}
~~~

Khi context refresh xong, Spring tự gọi `start()` cho những `SmartLifecycle` beans có `isAutoStartup() == true` theo thứ tự phase/phụ thuộc. Khi shutdown, processor dùng `stop(Runnable)` để được thông báo component đã ngừng hoạt động.

### 2.3. LifecycleProcessor: người điều phối

`org.springframework.context.LifecycleProcessor` hỗ trợ các hook `onRefresh()` và `onClose()`, cùng với contract `Lifecycle`. Spring thường dùng `DefaultLifecycleProcessor` làm implementation mặc định.

Processor biết tất cả lifecycle beans trong context, sắp thứ tự theo phase và dependency rồi gọi stop phù hợp. Với nhóm beans trong một phase, nó đợi tín hiệu completion cho tới thời hạn phase.

Điều quan trọng: **application không tự gọi callback mà Spring đưa vào từ bên ngoài**. Bean được truyền một `Runnable callback` khi processor gọi `stop(Runnable)`, và bean có trách nhiệm gọi `callback.run()` đúng một lần **sau khi công việc dừng hoàn tất**. Đó là cách processor biết nó có thể tiến tiếp.

## 3. Chính xác SmartLifecycle.stop(Runnable) hoạt động ra sao?

Hợp đồng:

~~~java
@Override
public void stop(Runnable callback) {
    // 1. Ngừng nhận công việc mới.
    // 2. Yêu cầu công việc hiện có kết thúc.
    // 3. Khi quá trình dừng thực sự hoàn tất:
    callback.run();
}
~~~

Đây là **pseudocode Java**, không chạy độc lập. Callback là tín hiệu cho container, không có nhiệm vụ dừng worker thay bạn.

### Dừng đồng bộ

Nếu dừng nhanh:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stopSynchronously();
    } finally {
        callback.run();
    }
}
~~~

Đây là snippet minh họa với method `stopSynchronously()` do ứng dụng định nghĩa; method này phải thực sự đưa component về trạng thái đã dừng. Đừng gọi callback sau khi chỉ phát lệnh “hãy dừng” mà resource vẫn còn đang làm việc nếu hợp đồng yêu cầu đợi hoàn tất.

### Dừng bất đồng bộ

Nếu component cần thời gian drain queue/đợi công việc:

~~~java
@Override
public void stop(Runnable callback) {
    rejectNewWork();
    stopExecutor.execute(() -> {
        try {
            waitForActiveWorkToFinish();
            releaseActivity();
        } finally {
            markStopped();
            callback.run();
        }
    });
}
~~~

Đây là **snippet kiến trúc**, các method `rejectNewWork()`, `waitForActiveWorkToFinish()`, `releaseActivity()`, `markStopped()` và `stopExecutor` chỉ mang tính minh họa. Với hệ thống thực, phải xử lý cả trường hợp executor **từ chối task**, quá trình dừng ném lỗi, callback bị gọi hai lần và deadline được cấp.

**Ý nghĩa của callback:**

1. Không phải callback của người dùng cuối; nó là tín hiệu từ bean trả về `LifecycleProcessor`.
2. Phải gọi **sau khi component thực sự stopped**, không gọi ngay sau khi submit một tác vụ cleanup.
3. Gọi callback quá sớm khiến Spring nghĩ phase đã xong và bắt đầu phá hủy dependency đang còn được worker sử dụng.
4. Quên gọi callback làm processor chờ đến timeout của phase.
5. Sau timeout, processor có thể tiếp tục các bước shutdown; **nó không tự buộc thread của bạn kết thúc**.
6. Lý tưởng là **đúng một lần**, kể cả khi đường dừng thực thi lại hoặc gặp lỗi.
7. `SmartLifecycle.stop()` không có callback vẫn có thể được gọi trực tiếp bởi mã ứng dụng, nhưng processor khi shutdown thông thường sử dụng **overload có callback**. Nếu override cả hai, đừng đặt logic quan trọng chỉ ở một overload rồi quên ủy nhiệm.

### Default implementation không tự tạo async behavior

Trong Spring hiện đại, `SmartLifecycle.stop(Runnable)` có default implementation gọi `stop()`, rồi gọi callback trong thread hiện tại. Hành vi này chỉ phù hợp nếu `stop()` thực sự **dừng đồng bộ**. Một `stop()` chỉ đặt cờ “stopping” rồi trả về không đủ để báo hoàn tất. Nếu shutdown mất thời gian và phải chạy async, override `stop(Runnable)` đúng cách.

## 4. Phase: thứ tự dừng không đơn thuần là thứ tự đăng ký bean

Mỗi component `SmartLifecycle` có số nguyên phase từ `getPhase()`. Quy tắc chung:

- **Startup:** phase thấp khởi động trước; phase cao khởi động sau.
- **Shutdown:** phase cao dừng trước; phase thấp dừng sau.
- Các thành phần cùng phase có thể bắt đầu xử lý stop trong cùng giai đoạn, processor đợi completion trước khi chuyển sang phase tiếp theo.
- Một bean `Lifecycle` thông thường không implement `SmartLifecycle` thuộc phase mặc định **0**.
- `SmartLifecycle` mặc định có `DEFAULT_PHASE` rất cao (`Integer.MAX_VALUE`), nên thường được auto-start muộn và stop sớm, trừ khi cấu hình riêng.
- Quan hệ `depends-on`/dependency có thể **ưu tiên hơn thứ tự phase**: dependent phải dừng trước bean mà nó phụ thuộc.

Ví dụ:

| Bean | Phase | Thứ tự |
| --- | ---: | --- |
| `ClientListener` | 200 | Start sau; stop trước |
| `MessageProcessor` | 100 | Start ở giữa; stop ở giữa |
| `SharedTransport` | 0 | Start trước; stop sau |

Với pipeline nhận message → xử lý → gửi qua transport, thứ tự stop từ cao xuống thấp có thể cho phép listener ngừng nhận việc trước, processor hoàn tất việc đang chạy, rồi mới đóng transport. Tuy vậy, **phase không thay thế thiết kế draining và dependencies**. Nếu listener dừng nhưng còn job đang chạy trong processor, processor vẫn cần đợi job hoàn tất trước callback.

**Phải biểu diễn dependency thực tế:** Nếu A đang dùng B, A phải kết thúc trước khi B bị đóng, bất kể phase dự tính thế nào. Constructor injection và bean dependency graph giúp Spring nắm quan hệ này.

## 5. Timeout cho từng shutdown phase là gì?

`DefaultLifecycleProcessor` đợi callback của các `SmartLifecycle` beans trong mỗi phase. Nếu mọi callback đến trước deadline, phase hoàn tất và shutdown tiến sang phase thấp hơn. Nếu có bean không gọi callback hoặc dừng quá lâu, processor chỉ chờ **đến timeout của phase đó** rồi tiếp tục xử lý shutdown.

~~~text
Phase 200: stop listener ---------------- callback ✅
                                        |
                                        v
Phase 100: stop worker --------- callback ✅ (trong hạn)
                                        |
                                        v
Phase   0: stop transport -------------- callback ✅
                                        |
                                        v
                Chạy bean destruction
~~~

Nếu worker phase 100 quá hạn:

~~~text
Phase 100 bắt đầu: t=0
  worker.stop(callback) → bắt đầu async shutdown
  ...
  t = timeoutPerShutdownPhase: callback chưa được gọi
  → LifecycleProcessor ghi nhận quá hạn / tiếp tục shutdown
  → worker async có thể vẫn đang chạy!
  → bean destruction có thể diễn ra khi worker chưa xong
~~~

**Timeout không phải “kill switch”.** Nó giới hạn khoảng thời gian container **đợi tín hiệu completion** của nhóm cùng phase; Spring không mặc nhiên interrupt, cancel `Future`, đóng socket, ép GC hoặc hủy thread của component sau timeout. Implementation của bean cần hỗ trợ dừng có deadline, cancellation và cleanup idempotent nếu hành vi nghiệp vụ đòi hỏi.

### Timeout là theo phase, không phải mỗi bean

Giả sử phase 100 có ba beans, trong đó một bean cần 4 giây, bean khác cần 5 giây, bean thứ ba cần 6 giây; nếu cả ba dừng đồng thời thì timeout 10 giây là **ngân sách chờ chung của phase**, không phải tổng `4 + 5 + 6` giây, cũng không phải mỗi bean được 10 giây cộng dồn.

Tuy nhiên không nên coi tổng shutdown bằng đúng tổng timeout của các phases: hoạt động đồng bộ trong `stop`, bean destruction callbacks, event listeners và các framework khác có thể mất thêm thời gian. Nếu một `stop(Runnable)` **block trực tiếp** trước khi trả về, nó còn có thể trì hoãn bản thân tiến trình điều phối. Để tận dụng cơ chế callback/time-bound asynchronous stop, phương thức nên trả về sau khi kích hoạt việc dừng, còn completion được báo sau từ luồng thực thi phù hợp.

### Chú ý khác biệt giữa phiên bản

Trong **Spring Framework 6.2**, Javadoc của `DefaultLifecycleProcessor` ghi timeout mặc định **10.000 ms (10 giây) cho mỗi phase**. Một số trang tham chiếu dùng nhánh/phiên bản cũ nói **30 giây**. Vì mặc định và API có thể thay đổi theo phiên bản, hãy đối chiếu version `spring-context` thực chạy; tốt nhất **cấu hình rõ timeout** thay vì dựa trên giá trị ngầm định.

Kể từ Spring 6.2, có thể đặt timeout theo phase bằng `setTimeoutForShutdownPhase(...)` hoặc `setTimeoutsForShutdownPhases(...)`. Các ứng dụng sử dụng Spring Framework 6.1 không có cùng toàn bộ API per-phase như 6.2.

## 6. Cách cấu hình DefaultLifecycleProcessor

### 6.1. Mỗi phase cùng một giới hạn

~~~java
@Bean(name = "lifecycleProcessor")
static DefaultLifecycleProcessor lifecycleProcessor() {
    DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
    processor.setTimeoutPerShutdownPhase(20_000L); // milliseconds
    return processor;
}
~~~

Snippet này thuộc một lớp `@Configuration`; import `org.springframework.context.annotation.Bean` và `org.springframework.context.support.DefaultLifecycleProcessor`.

Tên bean **`lifecycleProcessor`** là tên Spring context tìm khi khởi tạo lifecycle processor. Với cấu hình Java, method `static` là một cách rõ ràng để tạo bean hạ tầng sớm; Spring cần component này ở bước hoàn tất `refresh()`.

Lệnh `setTimeoutPerShutdownPhase(20_000L)` áp dụng thời gian chờ chung **20 giây cho mỗi phase**, không phải deadline tổng cho toàn bộ JVM shutdown.

### 6.2. Đặt timeout riêng cho một phase (Spring 6.2+)

~~~java
@Bean(name = "lifecycleProcessor")
static DefaultLifecycleProcessor lifecycleProcessor() {
    DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
    processor.setTimeoutPerShutdownPhase(10_000L);
    processor.setTimeoutForShutdownPhase(100, 25_000L);
    processor.setTimeoutForShutdownPhase(200, 5_000L);
    return processor;
}
~~~

Ý nghĩa:

- Mặc định 10 giây cho mỗi phase không được override.
- Phase 100 có 25 giây để hoàn tất callback.
- Phase 200 có 5 giây.
- Khi phase 100 quá hạn, processor tiến sang phase kế tiếp dù component chưa chắc đã dừng.

Có thể truyền `Map<Integer, Long>` vào `setTimeoutsForShutdownPhases(...)` khi có nhiều phase. **Không trộn nhầm timeout khởi động với timeout shutdown**: `setConcurrentStartupForPhase(...)` (ở một số phiên bản 6.2 mới) cấu hình hoạt động startup, không phải phương thức dùng cho bài toán dừng.

### 6.3. Spring Boot property

Với Spring Boot có auto-configuration lifecycle processor, cấu hình phổ biến:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Hoặc YAML:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Đây là **timeout mỗi shutdown phase**. Nếu bạn tự định nghĩa bean `lifecycleProcessor`, cần kiểm tra cấu hình Spring Boot của phiên bản đang dùng vì bean tùy biến có thể ảnh hưởng đến cách Boot tự áp dụng property; tránh giả định property luôn override mọi processor tự tạo.

Cấu hình này đặc biệt quan trọng với **graceful shutdown** của Spring Boot web server. Trong các Spring Boot version hiện đại, graceful shutdown của embedded web server được kích hoạt trong lifecycle shutdown; ứng dụng còn xử lý request cũ trong một grace period và ngừng nhận request mới theo hành vi từng server. Điều này liên quan nhưng **không thay thế** thời gian dừng cho các worker, queue consumer và custom `SmartLifecycle` beans.

## 7. Ví dụ Java 17 có thể chạy: stop bất đồng bộ và callback hoàn tất

Ví dụ dưới đây cố ý đơn giản hóa công việc nền thành thao tác dừng mô phỏng ngắn bằng `Thread.sleep(80)`, để thấy rõ **lệnh stop được gửi trước và callback hoàn tất được báo sau**. Đây không phải implementation sản xuất cho việc drain queue thực sự.

### 7.1. Cấu trúc

~~~text
graceful-stop-demo/
├── pom.xml
└── src/main/java/demo/
    └── SmartStopDemo.java
~~~

### 7.2. pom.xml

Sử dụng JDK 17 và Spring Framework 6.2.19:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>graceful-stop-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. src/main/java/demo/SmartStopDemo.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.DefaultLifecycleProcessor;

public class SmartStopDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("context active");
        }

        System.out.println("context closed");
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean(name = "lifecycleProcessor")
        static DefaultLifecycleProcessor lifecycleProcessor() {
            DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
            processor.setTimeoutPerShutdownPhase(2_000L);
            return processor;
        }

        @Bean(destroyMethod = "release")
        public AsyncWorker asyncWorker() {
            return new AsyncWorker();
        }
    }

    public static class AsyncWorker implements SmartLifecycle {
        private final AtomicBoolean running = new AtomicBoolean();

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("worker started");
            }
        }

        @Override
        public void stop(Runnable callback) {
            if (!running.get()) {
                callback.run();
                return;
            }

            System.out.println("stop requested");

            Thread stoppingThread = new Thread(() -> {
                try {
                    Thread.sleep(80L); // Mô phỏng công việc đang hoàn tất.
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    running.set(false);
                    System.out.println("worker stopped");
                    callback.run();
                }
            }, "worker-stop");

            stoppingThread.start();
        }

        @Override
        public void stop() {
            running.set(false);
        }

        @Override
        public boolean isRunning() {
            return running.get();
        }

        @Override
        public int getPhase() {
            return 100;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        public void release() {
            System.out.println("resource released");
        }
    }
}
~~~

### 7.4. Lệnh chạy và stdout

Tại thư mục `graceful-stop-demo`:

~~~bash
java -version
mvn -version
mvn -q compile exec:java -Dexec.mainClass=demo.SmartStopDemo
~~~

Output dự kiến của chương trình (bỏ qua các log riêng của Maven/Spring nếu môi trường bật log):

~~~text
worker started
context active
stop requested
worker stopped
resource released
context closed
~~~

Giải thích:

1. Trong `refresh()`, `DefaultLifecycleProcessor` nhận bean `AsyncWorker` và gọi `start()` nhờ `isAutoStartup() == true`. In `worker started`.
2. Sau khi context được tạo xong, main in `context active`.
3. Khi ra khỏi `try-with-resources`, `context.close()` được gọi. Spring thấy `AsyncWorker` đang running ở phase 100 và gọi `stop(Runnable)`, in `stop requested`.
4. Phương thức `stop(Runnable)` tạo thread thực hiện phần stop, rồi trả về sớm. `DefaultLifecycleProcessor` chờ callback trong khoảng timeout **2 giây của phase 100**.
5. Thread mô phỏng 80 ms, đặt `running=false`, in `worker stopped`, sau đó gọi `callback.run()`. Processor nhận tín hiệu và có thể kết thúc phase.
6. Khi chuyển sang destruction, Spring gọi `release()` vì `@Bean(destroyMethod = "release")`. In `resource released`.
7. Hoàn tất context close, main in `context closed`.

**Tại sao output có thứ tự ổn định trong ví dụ này?** Main chỉ in `context closed` sau khi `close()` trả về, processor đợi callback; thời gian mô phỏng dừng nhỏ hơn timeout đã cấu hình trong điều kiện chạy thông thường. Nếu CPU bị treo hoặc scheduling chậm vượt quá deadline 2 giây, tình huống timeout có thể làm quan sát khác; khi đó cần xem log timeout và không suy đoán thread đã được dừng.

### 7.5. Những chi tiết cố ý giữ đơn giản

- `Thread.sleep(80)` không đại diện cho một hoạt động drain thật; trong production cần dừng input mới, đợi công việc hiện hành, kiểm soát timeout và handle cancellation.
- `stop()` không tham gia async path mà processor dùng. Trong ứng dụng production, nên có chung cơ chế dừng để `stop()` và `stop(Runnable)` không tạo hai semantics mâu thuẫn.
- Ví dụ không bảo vệ hoàn toàn trước nhiều lời gọi `stop(Runnable)` đồng thời; production cần trạng thái STOPPING/STOPPED, lưu danh sách callbacks hoặc tín hiệu completion dùng chung để không tạo nhiều stop threads và không gọi callback lặp.
- `release()` trong bản mẫu chỉ in một dòng. Resource thật nên bảo đảm không bị destroy trong khi worker còn sử dụng và cleanup an toàn nếu có timeout.
- Thread mới trong ví dụ không bị pooled. Nếu dùng executor để shutdown, hãy xử lý `RejectedExecutionException`: không được bỏ mất completion callback mà không có cơ chế cuối cùng đưa component về trạng thái dừng.

## 8. Trường hợp timeout: vì sao “đã hết hạn chờ” không có nghĩa “đã ngừng”?

Giả sử bean trong ví dụ đợi 5 giây nhưng `timeoutPerShutdownPhase = 2_000L`. Sau hai giây, processor có thể ghi warning timeout và tiếp tục sang các phase tiếp theo/destruction callbacks trong khi stopping thread vẫn còn chạy.

Hệ quả tiềm ẩn:

- `release()` có thể đóng resource mà worker chưa ngừng sử dụng.
- Bean ở phase thấp bị stop sớm hơn mong muốn vì phase cao chờ quá hạn.
- Context.close() có thể kết thúc nhưng thread ngoài container vẫn sống.
- Nếu stopping thread là **non-daemon** và không kết thúc, JVM có thể vẫn không thoát dù Spring đã hết thời gian chờ.
- Một callback được gửi **sau khi phase đã timeout** không “quay ngược thời gian” để phục hồi thứ tự dừng đã bị bỏ qua.

Vì vậy **timeout của lifecycle processor là rào chắn chờ**, không phải deadline hard-kill cho toàn bộ process. Một component tốt còn cần chiến lược riêng:

1. Khi nhận stop, **từ chối công việc mới** ngay.
2. Cho in-flight work một grace period rõ ràng, có deadline thực.
3. Nếu grace period hết, chủ động cancel/interrupt/close I/O theo khả năng an toàn của thư viện.
4. Xác định lúc nào resource thực sự không còn người dùng.
5. Cập nhật trạng thái `isRunning()` nhất quán.
6. Chỉ gọi callback khi component đạt trạng thái stopped theo contract.
7. Log/metrics khi timeout; không giả mạo completion để chỉ “làm Spring ngừng đợi”.

Với các resource không thể đảm bảo stop dưới deadline, ứng dụng cần thiết kế idempotency, retry, durable queue hoặc recovery khi restart. Không nên xử lý mất dữ liệu chỉ bằng cách kéo timeout thật dài.

## 9. Tránh race condition khi triển khai stop(Runnable)

Một component production thường có các trạng thái:

~~~text
NEW → RUNNING → STOPPING → STOPPED

                STOPPING ──(worker hoàn tất)──> STOPPED
                     |
                     └──(grace period hết)──> force/cancel path
                                               └──> STOPPED hoặc FAILED
~~~

Các tình huống cần xử lý:

| Tình huống | Quy tắc cần đáp ứng |
| --- | --- |
| `stop(callback)` gọi khi chưa running | Callback được gọi để processor không chờ vô ích |
| Hai lời gọi `stop(callback)` đến sát nhau | Không tạo hai đường dừng cạnh tranh; callbacks nhận tín hiệu hoàn tất hợp lệ |
| Worker dừng đúng lúc stop bắt đầu | Đọc/trạng thái phải có visibility (`AtomicBoolean`/lock) |
| Executor từ chối shutdown task | Có đường fallback hoặc báo lỗi rõ ràng, tránh bỏ quên callback |
| Worker throw exception | Cleanup phù hợp và không bỏ trạng thái ở STOPPING mãi |
| Callback tự throw exception | Log/contain theo trách nhiệm; không để exception phá hỏng resource cleanup |
| Stop hoàn thành sau processor timeout | Không giả định dependent beans còn sống |
| Start lại sau stop | Chỉ hỗ trợ nếu lifecycle contract/nguồn lực của component cho phép; reset state an toàn |
| Context bị destroy khi stop chưa nhận signal | Cleanup chịu được cả đường bất thường |

Một anti-pattern:

~~~java
@Override
public void stop(Runnable callback) {
    executor.shutdown();
    callback.run(); // Sai nếu executor vẫn có tasks đang chạy.
}
~~~

`ExecutorService.shutdown()` chỉ ngừng nhận task mới và bắt đầu orderly shutdown; nó **không đợi** tất cả task hoàn tất trước khi trả về. Nếu callback được gọi ngay, Spring có thể đóng dependencies trong lúc các tasks vẫn dùng chúng.

Pattern cần thiết sẽ đợi `awaitTermination(...)` hoặc completion signal, có timeout/interrupt policy và chỉ gọi callback sau khi worker thực sự đã stopped. Không chặn đồng bộ vô thời hạn trong thread đang gọi stop.

## 10. Ví dụ tích hợp một ExecutorService thật (snippet giải thích)

Trong một component quản lý executor, đoạn ý tưởng dừng có thể như sau:

~~~java
public void stop(Runnable callback) {
    accepting.set(false);
    workerExecutor.shutdown();

    shutdownCoordinator.execute(() -> {
        try {
            boolean completed =
                    workerExecutor.awaitTermination(15, TimeUnit.SECONDS);
            if (!completed) {
                workerExecutor.shutdownNow();
                // Tùy chính sách: tiếp tục đợi có giới hạn nếu phải xác nhận
                // worker thật sự đã kết thúc trước khi báo completion.
            }
        } catch (InterruptedException ex) {
            workerExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        } finally {
            // Chỉ gọi callback khi đã xác nhận trạng thái dừng cần thiết.
            // Logic này phụ thuộc vào hợp đồng thật của ứng dụng.
        }
    });
}
~~~

Đây là **snippet tích hợp**, cần `AtomicBoolean accepting`, `ExecutorService workerExecutor`, `Executor shutdownCoordinator` và imports `TimeUnit`, `InterruptedException` thích hợp. Nó cố ý **không gọi callback** trong code vì chỉ `shutdownNow()` chưa đảm bảo các running tasks đã kết thúc; bạn phải bổ sung trạng thái completion/await policy đúng. Ví dụ chạy hoàn chỉnh của mục 7 trình bày một stop path hữu hạn, còn mục này chỉ ra điểm thiết kế khó với executor thật.

Nếu không thể chờ resource ngừng hoàn toàn, đừng báo completion giả để “làm đẹp” log. Hãy quyết định rõ timeout nào thuộc coordinator, timeout nào thuộc worker và dữ liệu in-flight sẽ được recover ra sao.

## 11. Phân biệt Spring Boot graceful HTTP shutdown và SmartLifecycle callback

Spring Boot web apps thường cần dừng nhận HTTP requests mới, cho requests đang chạy thời gian hoàn tất, rồi giải phóng server. Với embedded servers và các phiên bản Boot hiện đại, graceful shutdown được tích hợp vào các lifecycle phases.

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Với Spring Boot có graceful shutdown mặc định, dòng `server.shutdown=graceful` có thể không cần thiết nhưng thể hiện ý đồ; kiểm tra phiên bản Boot cụ thể. Property `spring.lifecycle.timeout-per-shutdown-phase` điều khiển giới hạn chờ theo phase của lifecycle processor, được Spring Boot sử dụng cho graceful shutdown.

**Hai điều độc lập cần chú ý:**

- Dừng HTTP listener không đồng nghĩa background message consumer hoặc scheduled jobs cũng đã dừng. Chúng cần lifecycle riêng nếu phải phối hợp shutdown.
- Graceful shutdown timeout của Spring không phải timeout tổng của Kubernetes/OS/runtime. Nếu container orchestrator cho ứng dụng quá ít thời gian trước khi gửi SIGKILL, Spring có thể không được hưởng đầy đủ grace period.

Ví dụ phân bổ ngân sách:

~~~text
Runtime termination grace period
   ├─ thời gian thực thi preStop hook (nếu có)
   ├─ phase HTTP listener nhận stop
   ├─ phase consumers/workers hoàn tất
   ├─ bean destruction/flush
   └─ thời gian an toàn dự phòng
~~~

Đây là **sơ đồ ngân sách**, không phải công thức bắt buộc. Tổng thời gian thực tế phụ thuộc phase ordering và các callbacks; thiết kế nên dùng deadline cấp hệ thống lớn hơn thời gian cần để Spring cleanup.

Một số môi trường IDE gửi tín hiệu “terminate” theo cách khiến shutdown xảy ra nhanh hoặc cưỡng bức; phải kiểm tra quy trình deploy/runtime thật chứ không chỉ quan sát nút Stop của IDE.

## 12. Stop callback khác @PreDestroy như thế nào?

~~~java
@Component
public class ListenerLifecycle implements SmartLifecycle {

    @Override
    public void stop(Runnable callback) {
        // Ngừng nhận việc + chờ công việc cũ hoàn tất;
        // báo completion bằng callback.run().
    }

    @PreDestroy
    public void releaseResources() {
        // Đóng tài nguyên còn lại.
    }
}
~~~

Đây là **snippet cấu trúc**, chưa implement đầy đủ các method của `SmartLifecycle` và cần `jakarta.annotation.PreDestroy` cùng các imports khác. Không phải code chạy độc lập.

Trong context shutdown bình thường:

1. Spring gọi `stop(Runnable)` của running lifecycle beans theo phase.
2. Processor chờ completion callback tới timeout mỗi phase.
3. Spring chạy destruction callbacks như `@PreDestroy`, `DisposableBean.destroy()` hoặc custom destroy method.

Nhưng nếu `refresh()` thất bại trong khi context tạo bean hoặc một số đường destruction bất thường xảy ra, `@PreDestroy` có thể chạy mà `stop(Runnable)` chưa được gọi. Vì vậy destructor cần chịu được trạng thái “đang chạy”, “đang dừng”, “chưa từng start” và “đã dừng”.

Không nên gọi `callback.run()` trong `@PreDestroy` nếu callback thuộc một lần stop khác đã hết hạn hoặc không tồn tại; completion callback phải gắn đúng stop invocation và trạng thái completion thực tế.

## 13. Kiểm thử và chẩn đoán

### Kiểm thử tối thiểu

1. **Auto-start:** context refresh xong thì `isAutoStartup() == true` khiến `start()` được gọi.
2. **Stop bình thường:** `context.close()` gọi `stop(Runnable)`, callback chỉ chạy sau công việc dừng.
3. **Chờ callback:** Trong cùng phase, component A dừng async, processor chưa chuyển phase thấp hơn trước khi callback A được phát.
4. **Không gọi callback:** Processor chỉ chờ đến timeout của phase, log cảnh báo, tiếp tục xử lý. Đảm bảo không treo test vô thời hạn.
5. **Callback quá sớm:** Mô phỏng component còn đang dùng dependency; test phát hiện resource bị đóng trước khi worker xong.
6. **Multi-component cùng phase:** Xác minh timeout là deadline chung của nhóm, không cộng cho mỗi bean.
7. **Order:** Phase cao stop trước phase thấp; dependency override nếu cần.
8. **Sự cố dừng:** Executor shutdown task reject, worker throw exception, timeout/cancellation.
9. **Idempotent stop:** Gọi stop lặp hoặc stop khi not running, không để callback bị bỏ quên hay resource bị đóng hai lần.
10. **Startup failure:** Destruction vẫn an toàn nếu chưa có stop.
11. **Servlet graceful shutdown:** Kiểm thử HTTP requests in-flight và việc từ chối request mới trên embedded server đang dùng.
12. **Runtime signals:** Kiểm tra SIGTERM và termination grace period trong môi trường triển khai thực.

### Quan sát thực tế

Log nên ghi: component, phase, thời điểm stop requested, số lượng in-flight tasks, thời điểm completion callback, thời gian shutdown, việc timeout và lỗi cleanup. Metrics có thể gồm histogram `shutdown_duration_seconds`, gauge `inflight_tasks`, counter `shutdown_timeouts_total`. Tên metrics chỉ là gợi ý thiết kế; Spring Core không tự tạo các metric này chỉ vì một bean implements `SmartLifecycle`.

**Phân biệt các câu log:**

- “stop requested”: lệnh dừng đã gửi.
- “running=false”: trạng thái component cho biết đã dừng theo contract.
- “callback invoked”: container đã nhận tín hiệu completion.
- “phase timed out”: container ngừng chờ; component có thể vẫn chạy.
- “context closed”: quá trình đóng context đã đi hết các bước nhưng không chứng minh mọi task ngoài phạm vi quản lý đã kết thúc hoàn toàn.

### Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Shutdown phải chờ đến timeout dù worker đã dừng | Quên `callback.run()` | Gọi callback đúng một lần sau khi xác nhận dừng, kể cả đường no-op |
| Container đóng dependency khi task còn chạy | Callback gọi quá sớm, ví dụ ngay sau `executor.shutdown()` | Đợi in-flight tasks hoàn tất trước callback |
| Bean `stop()` có code nhưng không chạy lúc close | `SmartLifecycle` processor dùng `stop(Runnable)` overload | Override/ủy nhiệm giữa hai overload đúng cách |
| Phase cao chờ lâu, phase thấp chưa nhận stop | Chưa nhận callback hoặc deadline lớn | Kiểm tra asynchronous stop và timeout per phase |
| Bean timeout nhưng process vẫn không thoát | Thread ngoài scope còn sống, timeout không interrupt | Cancel/đóng resource chủ động và quản lý executor |
| Quá hạn rồi `@PreDestroy` đóng resource khi worker đang dùng | Stop callback không đến kịp, cleanup chưa phối hợp | Thiết kế deadline, cancellation, safe cleanup và recovery |
| Component không auto-start | `isAutoStartup() == false` hoặc bean chưa được đăng ký trong context | Cấu hình auto-start/explicit start chính xác |
| Thứ tự stop khác phase mong đợi | Quan hệ `depends-on` được ưu tiên | Kiểm tra dependency graph, không chỉ phase numbers |
| Boot property không có hiệu lực như nghĩ | Đang dùng custom lifecycle processor hoặc version khác | Kiểm tra bean `lifecycleProcessor` và cấu hình Boot thực chạy |
| Log thấy 30 giây nhưng Javadoc ghi 10 giây | Đọc tài liệu phiên bản khác | Chốt framework version và cấu hình timeout tường minh |
| Test shutdown pass nhưng production bị SIGKILL | Runtime grace period quá ngắn | Cấp đủ thời gian ở nền tảng triển khai và có recovery |
| Bean bị destroy mà chưa stop | Lỗi startup/hot refresh/đường hủy bất thường | Destructor phải an toàn khi chưa nhận stop signal |

## 14. Checklist thiết kế production

- Đặt ý nghĩa “đã dừng” thật rõ: không nhận việc mới, không còn in-flight task sử dụng resource sẽ bị hủy.
- Mô hình hóa RUNNING/STOPPING/STOPPED bằng state thread-safe.
- Đảm bảo `stop(Runnable)` trả về đủ nhanh sau khi kích hoạt async stop; callback chỉ phát khi thật sự complete.
- Đừng quên callback trong đường không running, error, cancellation hoặc rejected scheduling.
- Chọn `getPhase()` phản ánh thứ tự phụ thuộc hợp lý; kiểm tra `depends-on`.
- Cấu hình `DefaultLifecycleProcessor` theo version; trong Spring 6.2 có timeout mặc định 10 giây/phase và API riêng từng phase.
- Đừng coi processor timeout là hủy thread; thành phần tự quản lý deadline/interrupt/force-cancel.
- Phối hợp `@PreDestroy` để giải phóng resources sau stop và xử lý đường stop không xảy ra.
- Với Spring Boot web, kiểm tra graceful shutdown và `spring.lifecycle.timeout-per-shutdown-phase`.
- Bảo đảm thời gian cho phép của orchestrator lớn hơn nhu cầu đóng ứng dụng thực tế.
- Log completed/timeout/aborted theo component và phase; test trên runtime thật.

## 15. Tự kiểm tra

**1. Callback của `SmartLifecycle.stop(Runnable)` có tác dụng gì?**  
Để `LifecycleProcessor` biết component đã thực sự dừng và có thể kết thúc việc chờ nhóm cùng phase. Nó không tự ngừng component.

**2. Nếu worker gọi callback ngay sau `ExecutorService.shutdown()`, có đúng không?**  
Không nhất thiết. `shutdown()` chỉ ngừng nhận tasks mới và không chờ tasks đang chạy. Nếu tasks vẫn sử dụng dependency, callback đã được gọi quá sớm.

**3. Timeout 10 giây/phase có nghĩa mỗi bean được tối đa 10 giây riêng không?**  
Không. Processor áp dụng giới hạn chờ chung cho mỗi phase. Tổng thời gian shutdown còn phụ thuộc các hoạt động khác.

**4. Khi timeout phase xảy ra, Spring có ép interrupt mọi worker không?**  
Không. Timeout là giới hạn đợi completion, không phải cơ chế cưỡng bức cancel task.

**5. Phase nào dừng trước, phase 200 hay phase 100?**  
Thông thường phase 200 dừng trước phase 100. Dependency relationships có thể ưu tiên hơn phase.

**6. Vì sao `SmartLifecycle.stop()` có thể không được gọi trên shutdown dù đã override?**  
Vì lifecycle processor thông thường gọi `stop(Runnable callback)`. Implementation cần override đúng overload hoặc ủy nhiệm nhất quán.

**7. Dừng worker và `@PreDestroy` khác nhau như thế nào?**  
Stop điều phối cho worker ngừng nhận việc/đợi tác vụ, còn destruction callbacks đóng resources cuối cùng. Không thể luôn dựa vào stop xảy ra trước destruction khi startup thất bại.

**8. `spring.lifecycle.timeout-per-shutdown-phase=20s` có bảo đảm JVM luôn dừng dưới 20 giây?**  
Không. Nó giới hạn thời gian chờ cho **mỗi phase**, không bao gồm mọi hoạt động shutdown hoặc thread ngoài quản lý. Runtime có deadline riêng.

**9. Vì sao nên chọn timeout riêng cho phase quan trọng?**  
Vì listener có thể chỉ cần vài giây để ngừng nhận công việc, nhưng processor cần thêm thời gian drain các tasks trước khi transport/DB resource bị đóng. Spring Framework 6.2 hỗ trợ `setTimeoutForShutdownPhase(...)`.

**10. Nếu component dừng xong sau khi phase đã timeout, callback có phục hồi thứ tự shutdown không?**  
Không. Spring có thể đã chuyển phase hoặc phá hủy dependencies; callback muộn không đảo ngược các bước.

## Tài liệu chính thức

- Spring Framework Reference: [Customizing the Nature of a Bean — Startup and Shutdown Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html).
- Spring Framework Javadoc: [SmartLifecycle (Spring 6.2.7)](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/context/SmartLifecycle.html).
- Spring Framework Javadoc: [DefaultLifecycleProcessor (Spring 6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html).
- Spring Boot Reference: [Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html).
- Java SE API: [ExecutorService.shutdown() and awaitTermination()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
