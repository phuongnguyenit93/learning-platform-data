# Thiết kế start hoặc stop an toàn khi được gọi lại với SmartLifecycle

## 1. Bài toán thực tế

Trong Spring Boot Application Runtime, một bean triển khai **SmartLifecycle** có thể tự động khởi động khi `ApplicationContext` refresh và được yêu cầu dừng khi context đóng. Tuy nhiên, lifecycle không luôn là chuỗi duy nhất `start() → stop()`:

- Spring tự gọi `start()` trong refresh; code quản trị hoặc test gọi lại `start()`.
- Component đã RUNNING nhưng một thao tác đồng bộ gọi `start()` thêm lần nữa.
- Một lệnh `context.stop()` rồi `context.start()` khiến bean phải dừng và khởi động lại.
- Hai luồng gọi `start()` hoặc `stop()` gần nhau, hoặc stop đến khi start chưa hoàn tất.
- Khi shutdown, `DefaultLifecycleProcessor` gọi `stop(Runnable)`; sau đó callback hủy như `DisposableBean.destroy()` hoặc `@PreDestroy` lại dọn cùng resource.
- Một lời gọi stop mới xuất hiện trong lúc quá trình stop bất đồng bộ còn chạy.
- Startup lỗi sau khi mở một phần tài nguyên, trước lúc đánh dấu RUNNING.

Nếu viết ngây thơ:

~~~java
public void start() {
    executor = Executors.newSingleThreadExecutor();
}
~~~

thì start hai lần có thể tạo hai pool, mất tham chiếu đến pool đầu và làm rò thread. Đoạn trên chỉ minh họa một lỗi thiết kế, chưa phải chương trình độc lập.

Tương tự:

~~~java
public void stop() {
    executor.shutdown();
    executor = null;
}
~~~

có thể ném `NullPointerException` nếu gọi stop trước start hoặc stop lần hai. Tệ hơn, nếu start/stop chạy ở hai luồng, một luồng có thể đóng resource mà luồng kia vừa thay thế.

**Mục tiêu của bài:** một thao tác start hoặc stop khi bị gọi lại phải an toàn, không tạo/đóng resource trùng, trạng thái trung thực, callback hoàn tất được gửi chính xác, và không chặn shutdown quá lâu.

Khái niệm gần nhất là **idempotence (tính lũy đẳng)**. Khi component đã RUNNING, gọi start thêm lần nữa không mở thêm resource. Khi đã STOPPED, gọi stop thêm lần nữa không đóng lại resource. Nhưng điều đó **không cấm** bắt đầu một generation mới sau một lần stop thành công.

## 2. Hợp đồng SmartLifecycle của Spring Framework

`org.springframework.context.SmartLifecycle` mở rộng `Lifecycle` và `Phased`. Các API quan trọng:

| API | Ý nghĩa | Yêu cầu thực hành |
| --- | --- | --- |
| `start()` | Khởi động component | Không mở resource mới nếu đã RUNNING |
| `stop()` | Dừng đồng bộ theo hợp đồng Lifecycle | Không lỗi khi component chưa chạy hoặc đã dừng |
| `stop(Runnable callback)` | Dừng và thông báo hoàn tất cho lifecycle processor | Callback chạy sau khi dừng xong |
| `isRunning()` | Trạng thái hoạt động thực tế | Nhất quán với resource/state |
| `isAutoStartup()` | Tự chạy ở context refresh? | SmartLifecycle mặc định trả true |
| `getPhase()` | Nhóm và thứ tự start/stop | Phase thấp start trước, phase cao stop trước |

Về cơ bản, interface cung cấp các chữ ký:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
~~~

Đây là **minh họa rút gọn**. Đừng định nghĩa lại interface trong dự án, hãy dùng interface chính thức của Spring Framework. Tùy phiên bản, một số method đã có implementation mặc định.

### Vòng đời trong Spring Boot

~~~text
SpringApplication.run(...)
   |
   +-- Chuẩn bị và refresh ApplicationContext
   |     +-- Khởi tạo bean SmartLifecycle
   |     +-- DefaultLifecycleProcessor.onRefresh()
   |           +-- Auto-start SmartLifecycle (theo phase)
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   |
   +-- Ứng dụng hoạt động ...
   |
   +-- context.close() / JVM shutdown hook
         +-- ContextClosedEvent
         +-- LifecycleProcessor.onClose()
         |     +-- SmartLifecycle.stop(Runnable)
         |           +-- Callback sau khi hoàn tất stop
         +-- Hủy singleton
               +-- @PreDestroy / DisposableBean.destroy()
~~~

Các sự kiện startup thuộc Spring Boot, còn `SmartLifecycle` và `DefaultLifecycleProcessor` thuộc Spring Framework. Trong đường khởi động bình thường, auto-start của SmartLifecycle diễn ra trong refresh, **trước** `ApplicationStartedEvent` và trước runners.

Khi context đóng, Spring thường gọi `stop(Runnable)`, **không nhất thiết gọi `stop()` không tham số**. Nếu bạn có cleanup ở `stop()`, cần bảo đảm `stop(Runnable)` thực sự delegate phù hợp. Implementation mặc định của SmartLifecycle có thể delegate rồi gọi callback, nhưng với resource bất đồng bộ bạn phải viết lại chính xác.

Không được giả định callback dừng luôn đến trước destruction: trong một số đường abort refresh hoặc destroy ngoài shutdown bình thường, resource có thể bị destroy mà không có stop lifecycle ở trước đó.

## 3. State machine: vì sao hai trạng thái đôi lúc chưa đủ?

### Resource đồng bộ, nhẹ

~~~text
STOPPED --start thành công--> RUNNING
RUNNING --stop hoàn tất-----> STOPPED

RUNNING --start thêm--------> RUNNING  (no-op)
STOPPED --stop thêm---------> STOPPED  (no-op)
~~~

Với tài nguyên in-memory hoặc thao tác mở/đóng rất ngắn, dùng cùng một monitor/lock để serialize start, stop và isRunning thường đủ.

### Resource có I/O hoặc dừng bất đồng bộ

~~~text
             start request
STOPPED -----------------------> STARTING
   ^                               |
   |                               +-- open success --> RUNNING
   |                               +-- open error ----> cleanup / FAILED
   |                                                    |
   |                       stop request                 |
   +----------- STOPPING <------------------------ RUNNING
                   |
                   +-- drain/close hoàn tất --> STOPPED
                   +-- lỗi/timeout ---------> FAILED_STOP / policy
~~~

Khi dùng network, executor, consumer hoặc scheduled task, khoảng thời gian STARTING/STOPPING có ý nghĩa. Không báo RUNNING khi mới *yêu cầu* mở connection; chỉ báo RUNNING khi tài nguyên đã sẵn sàng theo contract.

Không báo STOPPED ngay khi mới gọi một lệnh như `ExecutorService.shutdown()`, vì các task đang chạy có thể chưa hoàn tất.

### Bảng điều khiển khi có lời gọi lặp

| State hiện tại | start() | stop()/stop(callback) |
| --- | --- | --- |
| STOPPED | Mở resource, chuyển STARTING/RUNNING | Không đóng nữa; callback được hoàn tất |
| STARTING | Không mở trùng; đợi, gộp hoặc báo lỗi rõ | Ghi nhận yêu cầu dừng sau khi start kết thúc |
| RUNNING | No-op | Bắt đầu dừng, chuyển STOPPING |
| STOPPING | Không mở generation mới chồng lên resource cũ | Gộp vào lần stop đang chạy, đăng ký thêm callback |
| FAILED | Cleanup/rollback rồi retry có điều kiện | Dọn phần tài nguyên còn sót, không giả vờ đã stop |

Không có một policy đúng cho mọi resource. Người triển khai phải quyết định: start khi STOPPING sẽ **đợi**, **xếp hàng** hay **bị từ chối**. Điều cấm là không xác định policy mà vẫn mở tài nguyên mới khi tài nguyên cũ còn đang đóng.

## 4. Invariants: điều gì phải luôn đúng?

Những quy tắc sau nên trở thành tiêu chí kiểm thử:

1. **Một generation đang chạy có tối đa một resource thật.** Hai lệnh start đồng thời không thể mở hai connection, consumer hoặc worker trùng.
2. **Một generation được đóng đúng một lần.** Stop khi STOPPED không gọi close lần hai gây lỗi.
3. **Có thể restart nếu resource hỗ trợ.** RUNNING → STOPPED → RUNNING tạo generation mới hợp lệ.
4. **isRunning() nhất quán.** Không thấy true trước khi resource sẵn sàng; không thấy false khi lifecycle còn coi resource đang hoạt động, trừ khi có state rõ.
5. **Không overlap nguy hiểm.** Start thế hệ mới không mở lại port/lease đang bị thế hệ trước chiếm.
6. **Callback hoàn tất thực sự.** `stop(Runnable)` không báo done trước khi dừng xong.
7. **Gọi stop thêm không bỏ callback.** Mỗi lời gọi stop(callback) hợp lệ có một completion notification.
8. **Cleanup chịu được gọi lại từ destroy.** `@PreDestroy` / `DisposableBean.destroy()` có thể dùng cùng đường cleanup mà không gây double-close.
9. **Có timeout/failure policy.** Không giữ monitor hay chờ I/O vô thời hạn.
10. **Quan sát được.** Log/metrics phân biệt số lần method được gọi với số lần resource thực sự được mở/đóng.

Đừng chỉ test `assertDoesNotThrow`; hãy kiểm tra open count, close count, generation, trạng thái cuối và thời điểm callback.

## 5. Vì sao volatile hoặc AtomicBoolean đơn lẻ chưa đủ?

Ví dụ này có race:

~~~java
private volatile boolean running;

public void start() {
    if (!running) {
        openConnection();
        running = true;
    }
}
~~~

Đây là pseudocode; `openConnection()` chưa định nghĩa. Hai thread có thể cùng thấy false và cùng cấp phát tài nguyên. `volatile` tạo bảo đảm về visibility, **không gộp check/allocate/publish thành một thao tác atomic**.

Thử dùng CAS:

~~~java
if (running.compareAndSet(false, true)) {
    openConnection();
}
~~~

Cũng chưa đủ nếu không có state machine. Cờ được set true **trước khi** mở connection thành công. Nếu kết nối thất bại, một stop khác có thể hiểu nhầm là đang RUNNING; lần start sau cũng có thể bị bỏ qua.

### Dùng một lock chung khi start/stop ngắn

~~~java
private final Object monitor = new Object();
private boolean running;

public void start() {
    synchronized (monitor) {
        if (running) return;
        openResource();  // Chỉ công bố RUNNING sau khi thành công.
        running = true;
    }
}

public void stop() {
    synchronized (monitor) {
        if (!running) return;
        closeResource();
        running = false;
    }
}

public boolean isRunning() {
    synchronized (monitor) {
        return running;
    }
}
~~~

Đây chỉ là **đoạn minh họa chưa độc lập**: `openResource()` và `closeResource()` là các thao tác giả định. Dùng cùng monitor giúp serialize check/state/resource. Nếu thao tác I/O kéo dài, giữ lock trong toàn bộ `openResource()` hoặc `closeResource()` có thể chặn thread khác; production nên dùng STARTING/STOPPING và hoàn tất I/O bên ngoài lock theo state machine.

### Thứ tự giữa start và stop đồng thời

Giả sử hai thread bắt đầu gần như cùng lúc:

~~~text
A: stop()
B: start()
~~~

Nếu thao tác được serialize, kết quả có thể RUNNING hoặc STOPPED tùy thứ tự thật sự đi vào lock. **Thread-safe không có nghĩa trạng thái cuối luôn giống nhau với hai lệnh mang mục đích ngược nhau.**

Muốn bảo đảm “shutdown thắng mọi start”, cần một trạng thái terminal/closing flag hoặc chính sách điều phối riêng, không chỉ synchronized.

## 6. Ví dụ Spring Boot Java 17+ chạy hoàn chỉnh

Ví dụ sau chạy với **Spring Boot 3.5.16** và **Java 17+**. Resource là một đối tượng in-memory để mọi dòng output đều xác định. Nó không giả vờ mô phỏng độ trễ network: mục tiêu là chứng minh gọi lặp, stop callback và destruction callback.

### 6.1. Cấu trúc dự án

~~~text
repeatable-lifecycle-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/lifecycle/
                └── RepeatableLifecycleApplication.java
~~~

**Tệp pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>repeatable-lifecycle-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.5.16 đã được công bố và có trên Maven Central. Ví dụ không dùng `spring-boot-starter-web` để tránh tạo server; mục tiêu là lifecycle bean thuần.

### 6.2. Tệp Java đầy đủ

**Tệp src/main/java/com/example/lifecycle/RepeatableLifecycleApplication.java:**

~~~java
package com.example.lifecycle;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RepeatableLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                RepeatableLifecycleApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ManagedWorker worker;

        try (ConfigurableApplicationContext context = app.run(args)) {
            worker = context.getBean(ManagedWorker.class);
            System.out.println("MAIN running=" + worker.isRunning());
        }

        System.out.println(
                "AFTER_CLOSE running=" + worker.isRunning());
        System.out.println(
                "AFTER_CLOSE counts="
                        + worker.startCount() + "/"
                        + worker.stopCount());
    }

    @Bean
    ManagedWorker managedWorker() {
        return new ManagedWorker();
    }

    @Bean
    ApplicationRunner demonstrate(ManagedWorker worker) {
        return args -> {
            System.out.println(
                    "RUNNER running=" + worker.isRunning());

            worker.start();
            worker.start();

            worker.stop(() -> System.out.println("CALLBACK first"));
            worker.stop(() -> System.out.println("CALLBACK second"));

            // Restart sau khi đã STOPPED là một generation mới.
            worker.start();
            worker.start();

            System.out.println(
                    "RUNNER counts="
                            + worker.startCount() + "/"
                            + worker.stopCount());
        };
    }

    public static final class ManagedWorker
            implements SmartLifecycle, DisposableBean {

        private final Object monitor = new Object();
        private Object resource;
        private int starts;
        private int stops;

        @Override
        public void start() {
            synchronized (monitor) {
                if (resource != null) {
                    System.out.println("START already-running");
                    return;
                }

                // Resource in-memory được tạo xong ngay lập tức.
                resource = new Object();
                starts++;
                System.out.println("START count=" + starts);
            }
        }

        @Override
        public void stop() {
            synchronized (monitor) {
                if (resource == null) {
                    System.out.println("STOP already-stopped");
                    return;
                }

                // Không có I/O bất đồng bộ trong demo.
                resource = null;
                stops++;
                System.out.println("STOP count=" + stops);
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                callback.run();
            }
        }

        @Override
        public boolean isRunning() {
            synchronized (monitor) {
                return resource != null;
            }
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }

        public int startCount() {
            synchronized (monitor) {
                return starts;
            }
        }

        public int stopCount() {
            synchronized (monitor) {
                return stops;
            }
        }

        @Override
        public void destroy() {
            System.out.println("DESTROY fallback");
            stop();
        }
    }
}
~~~

Đây là **một chương trình hoàn chỉnh** trong Maven project. Không phải pseudocode. `ManagedWorker` implement cả `SmartLifecycle` và `DisposableBean` để quan sát việc stop và destroy có thể cùng yêu cầu cleanup.

**Phân tích code:**

- `ManagedWorker` được Spring quản lý như singleton bean. Khi context refresh, `DefaultLifecycleProcessor` gọi `start()` vì `isAutoStartup()` trả true.
- Toàn bộ thao tác với `resource` và bộ đếm được bảo vệ bằng cùng `monitor`. Hai thread không thể cùng vượt guard rồi cấp hai resource khi một generation vẫn hoạt động.
- Resource được mô phỏng bằng `new Object()`, khởi tạo xong trước khi ghi trạng thái RUNNING. Với network client thật, cần cấp phát và kiểm tra sẵn sàng trước khi công bố RUNNING.
- `stop()` khi STOPPED chỉ in no-op. `stop(Runnable)` luôn thông báo callback sau khi stop đồng bộ trả về, kể cả lần gọi không có gì để đóng.
- Vì `stop()` trong ví dụ không thực hiện I/O và không có thất bại cleanup, `finally` ở `stop(Runnable)` an toàn cho demo. Trong ứng dụng thật, không được gọi callback “thành công” khi cleanup chưa thật sự hoàn tất.
- `destroy()` là safety net: đường shutdown bình thường đã stop, nhưng destruction callback vẫn có thể gọi lại cùng cleanup mà không gây double-close.
- `getPhase()` là 100. Phase đó không làm runner chạy sớm hơn, không đồng nghĩa với độ ưu tiên của `ApplicationRunner`.

### 6.3. Chạy và kiểm tra stdout

Từ thư mục project:

~~~bash
mvn package
java -jar target/repeatable-lifecycle-demo-0.0.1-SNAPSHOT.jar
~~~

Hoặc:

~~~bash
mvn spring-boot:run
~~~

Những dòng do **chính chương trình in** theo thứ tự sau; banner/log Maven và Spring Boot có thể xen giữa:

~~~text
START count=1
RUNNER running=true
START already-running
START already-running
STOP count=1
CALLBACK first
STOP already-stopped
CALLBACK second
START count=2
START already-running
RUNNER counts=2/1
MAIN running=true
STOP count=2
DESTROY fallback
STOP already-stopped
AFTER_CLOSE running=false
AFTER_CLOSE counts=2/2
~~~

Giải thích:

1. `START count=1`: auto-start trong refresh trước khi runner chạy.
2. `RUNNER running=true`: runner quan sát bean đã start.
3. Hai lời gọi start nữa đều được bỏ qua.
4. Lần stop đầu thực sự đóng generation thứ nhất, rồi phát callback thứ nhất.
5. Lần stop thứ hai không đóng thêm resource nhưng **vẫn phát callback thứ hai**.
6. Start sau stop tạo generation thứ hai, nên `START count=2` là hợp lệ.
7. Lệnh start kế tiếp lại là no-op.
8. `MAIN running=true` xuất hiện sau khi `SpringApplication.run(...)` hoàn tất.
9. Khi `try`-with-resources đóng context, lifecycle processor thực hiện stop lần nữa.
10. Spring gọi `DisposableBean.destroy()` sau đó. Stop thêm chỉ là no-op.
11. Sau close, worker không chạy; hai lượt tạo thật đều đã được dừng.

Lưu ý: đây là kết quả **cho demo đồng bộ với resource giả lập**, không phải một cam kết về thứ tự log trong các hệ thống có nhiều SmartLifecycle, async listeners hoặc I/O.

### 6.4. Ranh giới của ví dụ đồng bộ

Resource chỉ là `Object`, vì vậy không có thread, socket, file hoặc remote connection cần chờ. Bản production có thể khác:

- `start()` phải rollback khi mở resource chỉ thành công một phần.
- `stop()` phải ngừng nhận work và đợi các task đang xử lý theo policy.
- Không nên giữ monitor qua I/O vô hạn, vì sẽ block các lời gọi khác.
- Nếu cleanup có thể fail, cần ghi nhận trạng thái lỗi và báo cho hệ thống, không lặng lẽ đánh dấu STOPPED khi resource còn tồn tại.
- Nếu đóng bất đồng bộ, callback chỉ chạy **sau completion**, không phải sau khi gọi yêu cầu đóng.

## 7. Thiết kế stop(Runnable) không bị mất callback

### 7.1. Callback của SmartLifecycle dùng để làm gì?

Theo Spring Framework, callback được `DefaultLifecycleProcessor` sử dụng để biết component đã hoàn tất stop. Lifecycle processor có thể chờ những callback của các bean cùng phase trước khi chuyển sang phase kế tiếp.

Vì vậy code này sai cho tài nguyên có task đang chạy:

~~~java
@Override
public void stop(Runnable callback) {
    executor.shutdown(); // Chỉ từ chối task mới!
    callback.run();       // Có thể báo dừng quá sớm.
}
~~~

Đây là **đoạn minh họa không độc lập**. `ExecutorService.shutdown()` không đợi task in-flight hoàn tất. Nếu muốn graceful stop, phải đợi với timeout hoặc gửi callback từ hoàn tất bất đồng bộ.

### 7.2. Callback khi đã STOPPED

Trong implementation chịu được gọi lại, một lời gọi `stop(callback)` khi tài nguyên đã STOPPED vẫn phải hoàn thành contract của caller:

~~~text
Tình trạng hiện tại: STOPPED
stop(callbackA)
  -> Không close resource thêm
  -> callbackA.run() (dừng đã hoàn tất)
~~~

Không được “return ngay vì đã dừng” **mà bỏ callback**. `DefaultLifecycleProcessor` thường kiểm tra `isRunning()` trước khi gọi stop, nhưng caller khác có thể gọi trực tiếp. Bean vẫn nên bảo vệ hợp đồng của API.

### 7.3. Callback khi đang STOPPING

Tình huống cần một state machine:

~~~text
Caller A: stop(callbackA) khi RUNNING
  lock -> state=STOPPING, pendingCallbacks=[A]
  unlock
  bắt đầu shutdown bất đồng bộ một lần

Caller B: stop(callbackB) khi STOPPING
  lock -> thêm B vào pendingCallbacks
  unlock
  KHÔNG khởi động lần shutdown thứ hai

Shutdown thật hoàn tất:
  lock -> state=STOPPED, lấy danh sách callback và xóa queue
  unlock
  callbackA.run()
  callbackB.run()
~~~

Đây là **pseudocode**, không phải Java chạy độc lập. Việc cập nhật state và thêm callback phải atomic theo cùng lock hoặc cơ chế đồng bộ tương đương. Các callback nên được gọi **ngoài lock**, vì callback của framework hoặc tích hợp ngoài có thể gọi sang bean khác và gây deadlock nếu giữ khóa.

Một anti-pattern:

~~~java
if (stopping.compareAndSet(false, true)) {
    shutdownAsync(callback);
}
// Nếu đã STOPPING, callback mới bị rơi mất.
~~~

Đây là đoạn minh họa. CAS chỉ ngăn cleanup chạy hai lần, không tự giữ lại callback đến sau.

### 7.4. Xử lý lỗi và exactly-once notification

Với shutdown bất đồng bộ, cần tính đến:

- Một callback có thể ném exception: không được vì vậy mà bỏ callback kế tiếp; cần cô lập và ghi lỗi.
- Executor dùng để chạy cleanup có thể đã đóng: không gửi mọi callback vào executor không còn nhận task.
- Lời gọi stop mới có thể xảy ra ngay khi completion chuyển STOPPING → STOPPED: phải xử lý được cả hai trường hợp không mất callback.
- Không gọi callback khi đóng tài nguyên chưa xong, cũng không chờ vô hạn nếu tài nguyên kẹt.
- Khi timeout hoặc lỗi không thể cleanup, định nghĩa rõ state FAILED_STOP và cơ chế escalation, không giả định callback tự thay thế việc dọn dẹp.

**Callback đúng một lần** là mục tiêu ở cấp process. Nếu có hệ thống ngoài cần exactly-once side effects qua crash/restart, còn cần idempotency key, transaction, lease hoặc giao thức của hệ thống ngoài; một boolean không bảo vệ được toàn bộ vòng đời phân tán.

## 8. Start an toàn khi gọi lại và khi thất bại nửa chừng

Một start đáng tin cần làm việc theo thứ tự:

~~~text
Kiểm tra state
   |
   +-- RUNNING: no-op
   +-- STARTING: ghép yêu cầu / đợi / từ chối
   +-- STOPPING: đợi stop xong / queue restart / từ chối
   +-- STOPPED: bắt đầu khởi tạo
          |
          +-- mở resource
          +-- cấu hình
          +-- xác minh ready
          +-- thành công --> RUNNING
          +-- lỗi --> rollback resource đã mở
                        --> STOPPED hoặc FAILED
~~~

Đừng viết:

~~~java
running = true;
resource = connectToBroker();
subscribe(resource);
~~~

Đây là **pseudocode**. Nếu kết nối hoặc subscribe lỗi, `running=true` vẫn giữ trạng thái sai và lần start sau có thể bị bỏ qua. Cần chỉ công bố RUNNING khi tất cả bước bắt buộc thành công.

### Rollback khi start lỗi

Nếu đã mở socket nhưng bước tiếp theo thất bại:

1. Lưu resource đang khởi tạo ở một biến có chủ sở hữu rõ ràng.
2. Dọn những resource đã tạo thành công.
3. Không để field trạng thái báo RUNNING.
4. Giữ nguyên exception gốc; nếu cleanup cũng lỗi, có thể đính kèm suppressed exception phù hợp.
5. Chỉ retry nếu resource cho phép và policy cho phép (timeout, backoff, giới hạn số lần).
6. Không vô tình tạo hai subscription trong quá trình retry.

### Ngăn start mới khi context đang đóng

Ngay cả khi synchronized giúp serialize, thread quản trị có thể gọi `start()` **sau** khi một `stop()` do context close trả về, khiến resource mở lại lúc context đang destroy. Nếu shutdown phải thắng tuyệt đối, cần cờ terminal `closing` hoặc một state `TERMINATED` được thiết lập khi nhận lệnh đóng cuối cùng. Khi đã đóng vĩnh viễn, từ chối start thay vì cho phép tự động restart.

Ngược lại, trong hệ thống cần hỗ trợ `context.stop() → context.start()`, không được dùng một cờ terminal cho mọi stop. Cần phân biệt **tạm dừng** và **đóng vĩnh viễn**.

## 9. Phase, phụ thuộc và thứ tự shutdown

Spring Framework dùng `getPhase()`:

~~~text
START: phase thấp -> phase cao
STOP : phase cao  -> phase thấp
~~~

Một bảng minh họa:

| Bean | Phase | Start | Stop |
| --- | ---: | --- | --- |
| Kết nối nền tảng | -100 | Sớm | Muộn |
| Thành phần thông thường | 0 | Giữa | Giữa |
| Consumer phụ thuộc kết nối | 100 | Muộn | Sớm |

Như vậy consumer có thể ngừng nhận message trước khi kết nối nền tảng bị đóng. Nếu Spring biết quan hệ depends-on, dependency cũng ảnh hưởng thứ tự cho phù hợp.

`SmartLifecycle` mặc định có phase cao (`Integer.MAX_VALUE` trong Spring Framework 6.2); interface `Lifecycle` thông thường không SmartLifecycle thường được coi là phase 0. Cần chọn phase theo dependency thật, không theo thứ tự các method `@Bean`.

### isAutoStartup và lazy

`isAutoStartup()` mặc định trả true. SmartLifecycle bean có thể được tạo để lifecycle processor thực hiện auto-start ngay cả khi bạn nghĩ `@Lazy` sẽ giữ nó chưa được dùng. Nếu không muốn start tự động lúc refresh, hãy override `isAutoStartup()` thành false, hiểu rằng lệnh `context.start()` sau đó vẫn có thể start bean.

### SmartLifecycle khác ApplicationRunner

`SmartLifecycle.start()` thường chạy trong refresh, trước `ApplicationStartedEvent`, trước `ApplicationRunner` và trước `ApplicationReadyEvent`. Không viết start() chờ một runner hoàn thành theo cách tạo vòng phụ thuộc startup. Nếu cần công việc sau refresh hoặc sau các runner, dùng extension point đúng thời điểm.

## 10. Timeout dừng và graceful shutdown

`DefaultLifecycleProcessor` có timeout chờ callback theo phase; trong Spring Framework 6.2, Javadoc mô tả mặc định 10 giây mỗi phase, trừ khi có cấu hình khác. Spring Boot cho phép cấu hình:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Không dựa vào một giá trị mặc định bất biến cho mọi phiên bản. Cấu hình thời gian chờ của Spring chỉ giới hạn việc **processor đợi phase**, không cưỡng chế socket, task hay remote API tự đóng xong.

Nếu callback không được gọi, Spring có thể phải đợi hết timeout. Nếu callback được gọi quá sớm, Spring tin rằng phase đã dừng trong khi resource còn chạy. Cả hai đều có thể gây lỗi shutdown.

### Quy trình dừng một message consumer

1. Chuyển state sang STOPPING và từ chối tạo task mới.
2. Dừng poll/nhận message mới.
3. Đợi in-flight tasks với timeout.
4. Ack/commit theo hợp đồng broker và điều kiện nghiệp vụ.
5. Đóng connection và release resource.
6. Chuyển state sang STOPPED.
7. Gọi mọi callback đang đợi, ngoài lock.

Nếu có timeout, cần quyết định force-stop, báo lỗi hay để tác vụ retry ở instance khác; không tự công bố đã hoàn tất chỉ vì hết thời gian.

### JVM bị dừng cưỡng bức

`SIGKILL`, crash, mất điện và một số kiểu halt không đảm bảo Spring callback chạy. Resource ngoài process cần có lease/heartbeat/timeout; những yêu cầu “không xử lý trùng” trên toàn cluster cần cơ chế phối hợp phân tán, không chỉ SmartLifecycle local.

## 11. Cleanup dự phòng qua destroy callback

Tài liệu Spring Framework nêu rõ stop notification **không được bảo đảm** đến trước destruction trong mọi trường hợp (ví dụ refresh thất bại). Trong shutdown bình thường, lifecycle bean được stop trước khi Spring gọi destruction callback của singleton.

Những cách dọn tài nguyên phù hợp:

- `@PreDestroy` trên bean được Spring quản lý.
- `DisposableBean.destroy()`.
- `@Bean(destroyMethod = "...")`.
- `AutoCloseable.close()` khi được sở hữu và quản lý đúng contract.

Nếu SmartLifecycle **sở hữu** resource, destroy callback có thể gọi cùng một cleanup method idempotent để che đường lỗi startup. Đây là nguyên nhân demo ở mục 6 implement `DisposableBean`.

Nếu SmartLifecycle chỉ **mượn** resource thuộc bean khác, không tự close nó trừ khi đã thống nhất ownership. Ví dụ consumer dùng pool chung có thể chỉ cần dừng consumer, để chủ sở hữu pool giải phóng trong destruction.

**Không thay thế** `stop(Runnable)` bằng destroy callback: lifecycle processor cần callback để điều phối phase và đợi completion. Destroy đảm nhận tuyến dọn dẹp khác.

## 12. Kiểm thử an toàn khi gọi lại

### 12.1. Thử tuần tự

~~~text
Ban đầu STOPPED:
start()             -> RUNNING, openCount=1
start()             -> RUNNING, openCount=1
stop(callbackA)     -> STOPPED, closeCount=1, callbackA=1
stop(callbackB)     -> STOPPED, closeCount=1, callbackB=1
start()             -> RUNNING, openCount=2
stop(callbackC)     -> STOPPED, closeCount=2, callbackC=1
destroy()           -> STOPPED, closeCount=2
~~~

Những con số này là **kỳ vọng của implementation có thiết kế như demo**, không phải biến đo mà Spring tự tạo.

### 12.2. Hai thread start đồng thời

Dùng `CountDownLatch` để hai thread gọi `start()` cùng thời điểm. Sau khi cả hai kết thúc, với state STOPPED ban đầu:

~~~text
isRunning() == true
openCount == 1
~~~

Cần test nhiều vòng để tăng khả năng phát hiện race. Không chỉ dựa vào kết quả một lần chạy.

### 12.3. Hai thread stop đồng thời

Hai lời gọi:

~~~text
A: stop(callbackA)
B: stop(callbackB)
~~~

Kỳ vọng:
- Một lượt cleanup resource thật.
- callbackA và callbackB được gọi mỗi cái đúng một lần.
- Không callback nào chạy trước khi resource đóng xong.
- Nếu stop async, cả hai cùng chờ một completion mà không gây double-close.

### 12.4. Start chồng lên stop

~~~text
A: stop() đang giải phóng resource
B: start() muốn mở resource mới
~~~

Nếu dùng lock đồng bộ, các thao tác không overlap, nhưng kết quả cuối cùng có thể RUNNING hoặc STOPPED tùy thứ tự lock. Nếu yêu cầu “sau khi shutdown bắt đầu thì mọi start đều bị cấm”, phải có trạng thái CLOSING/TERMINATED.

### 12.5. Kiểm thử lỗi

Hãy tạo tình huống:
- Start tạo connection thành công, subscribe thất bại.
- Stop ném exception ở bước close.
- Callback được đăng ký trong lúc STOPPING.
- Executor thực thi cleanup đã bị shutdown.
- Callback người dùng ném exception.
- Destroy chạy dù chưa từng start thành công.
- Spring stop phase timeout khi task không chịu kết thúc.

Mỗi lần kiểm tra: trạng thái, số resource còn mở, số callback nhận được, không có deadlock và phản ứng tiếp theo có rõ ràng không.

## 13. Những lỗi thường gặp

| Sai lầm | Hậu quả | Sửa bằng |
| --- | --- | --- |
| Start luôn tạo executor/connection | Rò tài nguyên khi gọi lại | Guard state, one resource per generation |
| Stop null resource không kiểm tra | NPE khi chưa start hoặc đã stop | No-op an toàn |
| Chỉ dùng volatile boolean | Hai thread cùng cấp phát | Lock hoặc state machine hoàn chỉnh |
| Set running trước khi connect thành công | State kẹt khi lỗi | Publish RUNNING sau ready, rollback |
| Đánh dấu STOPPED ngay sau shutdown() | Task vẫn còn chạy | Đợi completion/timeout |
| Bỏ callback nếu đã STOPPED | Caller chờ vô ích | Callback ngay vì đã hoàn tất |
| Bỏ callback mới nếu STOPPING | Completion thất lạc | Queue mọi callback |
| Callback trong lock | Có thể deadlock | Chuyển state trong lock, callback ngoài lock |
| I/O vô hạn trong synchronized | Chặn các lời gọi khác | Timeout và async state machine |
| Start khi resource cũ còn STOPPING | Port/lease conflict | Chặn/queue/đợi restart |
| Destroy đóng resource đã đóng | Double-close | Dùng cleanup idempotent |
| Không có rollback khi start lỗi | Rò partial resource | Cleanup trong đường failure |
| Không phân biệt stop và close vĩnh viễn | Mở lại trong shutdown | Terminal closing state |
| Chọn phase ngược phụ thuộc | Consumer dùng client đã đóng | Phase và depends-on đúng |
| Dùng @Lazy để “vô hiệu” auto-start | SmartLifecycle vẫn có thể start | Override isAutoStartup |
| Chỉ test happy path | Race và callback mất | Stress test concurrency/failure |
| Xem callback như idempotency phân tán | Duplicates qua crash/retry | Lease, idempotency key, transaction |

## 14. Câu hỏi ôn tập

**Câu 1:** Vì sao start() phải idempotent?

**Trả lời:** Vì Spring và code ứng dụng có thể gọi lại, hoặc hai thread có thể tranh chấp. Không có guard sẽ tạo resource trùng, rò và sai trạng thái.

**Câu 2:** Một lời gọi stop() khi STOPPED có nên ném exception?

**Trả lời:** Không. Hợp đồng Lifecycle kỳ vọng dừng an toàn khi component không chạy; nên no-op.

**Câu 3:** stop(Runnable) khi STOPPED có nên gọi callback?

**Trả lời:** Có. Không cần đóng resource nữa, nhưng phải báo hoàn tất lời gọi.

**Câu 4:** ExecutorService.shutdown() có nghĩa mọi task đã kết thúc?

**Trả lời:** Không. Nó ngăn nhận task mới; cần theo dõi termination hoặc completion của task.

**Câu 5:** Tại sao volatile không đủ bảo vệ start?

**Trả lời:** Check và cấp phát không atomic. Hai thread có thể đọc false rồi cùng tạo resource.

**Câu 6:** Phase cao start trước hay sau phase thấp?

**Trả lời:** Start sau và stop trước, trừ các điều kiện dependency bổ sung.

**Câu 7:** isAutoStartup=false có cấm context.start() start bean không?

**Trả lời:** Không. Nó chỉ điều khiển auto-start khi refresh; context.start() là yêu cầu lifecycle riêng.

**Câu 8:** Một start sau một stop hoàn tất có phải vi phạm idempotence?

**Trả lời:** Không. Nếu component hỗ trợ restart, đó là generation mới hợp lệ.

**Câu 9:** Tại sao callback stop không được gọi dưới monitor?

**Trả lời:** Callback có thể gọi lại API hoặc chạm lock khác, dẫn đến deadlock hoặc block không mong muốn.

**Câu 10:** Spring có đảm bảo stop lifecycle luôn chạy trước destroy không?

**Trả lời:** Không trong mọi đường đi; cần cleanup fallback cho resource thuộc bean.

**Câu 11:** Timeout shutdown phase có tự cưỡng chế tài nguyên đã đóng không?

**Trả lời:** Không. Nó giới hạn thời gian Spring chờ callback; tài nguyên cần logic timeout/cancel riêng.

**Câu 12:** Làm sao đảm bảo start không chồng lên stop?

**Trả lời:** Với thao tác ngắn, serialize bằng lock; với thao tác bất đồng bộ, dùng STARTING/STOPPING state và chính sách queue/đợi/từ chối rõ.

## 15. Bài tập thực hành

**Bài tập A:** Chạy demo mục 6. Đếm lời gọi start/stop và số lượt resource thật sự được mở/đóng. Giải thích vì sao startCount=2 và stopCount=2 dù số method call nhiều hơn.

**Bài tập B:** Thêm `worker.stop(() -> System.out.println("CALLBACK third"))` ngay sau lần stop thứ hai. Callback thứ ba phải xuất hiện nhưng stopCount không tăng.

**Bài tập C:** Đổi `isAutoStartup()` thành false. Quan sát runner ban đầu thấy STOPPED; sau đó start chủ động và kiểm chứng behavior.

**Bài tập D:** Dùng `CountDownLatch` và hai thread gọi start đồng thời từ STOPPED. Kỳ vọng openCount=1. Lặp lại với hai stop callback để kiểm tra completion chính xác.

**Bài tập E:** Tạo một ResourceFactory đôi khi ném exception sau bước cấp phát đầu tiên. Viết rollback tránh leak và không báo RUNNING khi chưa ready.

**Bài tập F:** Thay Object bằng worker thread, triển khai STOPPING + callback queue. Đảm bảo dừng task thật sự trước callback; dùng timeout và test cả hai lời gọi stop đến cùng lúc.

**Bài tập G:** Thêm bean nền tảng phase -100 và consumer phase +100. Quan sát thứ tự start/stop. Kiểm tra điều gì xảy ra nếu consumer stop trước khi hết in-flight work.

## 16. Tài liệu chính thức và ghi nhớ

Nguồn nên đối chiếu theo version phụ thuộc thực tế:

- [Spring Framework 6.2 — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/SmartLifecycle.html): callback, phase, auto-start.
- [Spring Framework 6.2 — Lifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/Lifecycle.html): hợp đồng start/stop/isRunning.
- [Spring Framework 6.2 — DefaultLifecycleProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): thứ tự và shutdown timeout.
- [Spring Framework — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): stop, phase và destruction callback.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): cấu hình timeout trong shutdown.

**Ghi nhớ:**

1. RUNNING + start() → no-op; STOPPED + stop() → no-op.
2. STOPPED + start() → generation mới nếu resource hỗ trợ restart.
3. Guard phải bảo vệ cả trạng thái và resource; volatile/CAS đơn giản không tự đủ.
4. isRunning() phải trung thực với resource và phase chuyển tiếp.
5. stop(Runnable) phải thông báo callback sau khi dừng thật, kể cả khi gọi lại.
6. Async STOPPING cần giữ mọi callback và chỉ một tiến trình cleanup.
7. SmartLifecycle start theo phase tăng và stop theo phase giảm.
8. Cleanup từ destroy phải idempotent và không thay thế stop callback.
9. Không giữ lock qua I/O vô hạn hoặc báo STOPPED khi task chưa dừng.
10. Cần test concurrency, failure, restart và forced shutdown, không chỉ happy path.
