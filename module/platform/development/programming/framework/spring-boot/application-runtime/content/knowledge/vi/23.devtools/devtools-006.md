# Quan hệ giữa DevTools restart với shutdown hook và dọn dẹp tài nguyên trong Spring Boot

## 1. Bài toán: sửa code, DevTools restart, nhưng tài nguyên cũ vẫn còn

Khi phát triển một ứng dụng Spring Boot, **spring-boot-devtools** có thể tự động khởi động lại application sau khi các class trong classpath được biên dịch và thay đổi. Việc này giúp chu kỳ sửa mã nhanh hơn chạy lại toàn bộ JVM. Nhưng restart có thể gây các lỗi khó nhận biết:

- Sau nhiều lần sửa code, số background threads tăng dần.
- Port TCP hoặc file handle từ context trước không được giải phóng.
- Một scheduled task cũ và một task mới cùng chạy.
- Connection pool đã được khởi tạo lại nhưng connection cũ vẫn mở.
- ThreadLocal, listener hoặc cache giữ đối tượng do classloader cũ nạp.
- DevTools không restart đúng sau khi code tắt shutdown hook.
- Lần restart đầu tiên chạy tốt, nhưng lần thứ ba báo lỗi port already in use.

Để giải quyết, phải hiểu mối quan hệ giữa **DevTools restart**, **ApplicationContext.close()**, **SpringApplication shutdown hook**, **bean destruction callbacks** và **vòng đời của JVM/classloader**.

~~~text
JVM vẫn chạy
   |
   +-- DevTools base ClassLoader      (thư viện ổn định)
   |
   +-- RestartClassLoader #1         (application classes lần 1)
   |        |
   |        +-- ApplicationContext #1
   |        +-- Bean resources #1
   |        +-- HTTP server / scheduler / listeners
   |
   +-- Classpath thay đổi -> restart được yêu cầu
   |        |
   |        +-- Đóng ApplicationContext #1
   |        |       +-- ContextClosedEvent
   |        |       +-- SmartLifecycle.stop(...)
   |        |       +-- @PreDestroy / destroy callbacks
   |        |
   |        +-- Loại bỏ tham chiếu tới RestartClassLoader #1
   |
   +-- RestartClassLoader #2
            |
            +-- ApplicationContext #2
            +-- Bean resources #2
            +-- Server / scheduler mới
   |
   +-- JVM tiếp tục chạy, PID thường không đổi
~~~

**Định luật vận hành của bài:** DevTools có thể thay ApplicationContext và restart classloader, nhưng **không thể tự động đóng những tài nguyên mà ứng dụng đã tạo bên ngoài lifecycle của Spring**. Nếu một thread, socket, timer hoặc static cache giữ reference tới classloader cũ, JVM vẫn có thể giữ phần lớn đối tượng cũ trong bộ nhớ.

Bài dùng **Java 17+, Spring Boot 3.3.13, Maven và spring-boot-devtools**. Ví dụ đi kèm chạy trong môi trường phát triển, không sử dụng DevTools trong production.

## 2. DevTools restart thực sự là gì?

Theo tài liệu Spring Boot 3.3, cơ chế **automatic restart** sử dụng hai classloader:

1. **Base classloader:** chứa những dependency JAR ổn định, thường là thư viện bên thứ ba. Nó được giữ lại qua các vòng restart.
2. **Restart classloader:** chứa class của dự án đang phát triển, thường được đọc từ những thư mục classpath có thể thay đổi như **target/classes**. Khi restart, DevTools bỏ classloader này và tạo một instance mới.

Việc giữ base classloader làm cho restart thường nhanh hơn cold start: các class thư viện đã được nạp không cần khởi tạo toàn bộ từ đầu.

### 2.1. Restart khác reload

| Khái niệm | Tác động |
| --- | --- |
| **DevTools restart** | Đóng context ứng dụng cũ, dựng lại context và restart classloader |
| **LiveReload** | Thông báo browser refresh khi tài nguyên phù hợp thay đổi; không đồng nghĩa JVM/context restart |
| **IDE hot code replace** | Thay một số bytecode đang chạy nếu debugger/JVM hỗ trợ; không nhất thiết tạo context mới |
| **JVM process restart** | Process cũ kết thúc, process mới được hệ điều hành tạo với PID mới |
| **Kubernetes rollout** | Thay các instance/container; có tác động bên ngoài JVM |
| **ApplicationContext.refresh()** | Hoạt động refresh context theo hợp đồng của loại context; không tự đồng nghĩa DevTools restart |

**Đừng nhầm DevTools restart với “chạy lại main trong một JVM mới”.** DevTools có thể chạy lại quá trình bootstrap ứng dụng trong chính JVM hiện tại, thông qua classloader mới. Một số thành phần và state nằm ở base classloader có thể sống qua nhiều lần restart.

### 2.2. Khi nào DevTools tự restart?

DevTools theo dõi **các tài nguyên trên classpath**. Thay đổi **file .java ở thư mục nguồn** chưa chắc làm restart nếu IDE chưa biên dịch và copy class mới vào output directory.

Các cách thường gặp:

- Eclipse có thể compile khi save.
- IntelliJ IDEA cần **Build Project** hoặc cơ chế auto-build được cấu hình phù hợp.
- Maven **mvn compile** hoặc Gradle build tạo class mới vào output path.
- Một file trigger có thể dùng để kiểm soát thời điểm restart.

Tài nguyên tĩnh và template có thể được DevTools xử lý theo hướng **LiveReload** mà không cần full application restart, tùy cấu hình.

### 2.3. Restart không đồng nghĩa mọi thay đổi đều tạo một vòng mới

Không nên mặc định mỗi lần bấm Save đều đóng context. Một thay đổi không làm classpath output thay đổi, hoặc thuộc các đường dẫn bị loại trừ khỏi restart, có thể chỉ kích hoạt reload hoặc không tạo restart nào.

Muốn kiểm tra đã xảy ra restart thật, quan sát **context instance** và một **resource ID** được tạo khi bean mới xuất hiện; không dựa vào số lần người dùng nhấn Ctrl+S.

## 3. Shutdown hook là gì trong Spring Boot?

Mặc định, **SpringApplication** đăng ký một shutdown hook với JVM để ApplicationContext được đóng khi tiến trình đi qua đường shutdown bình thường.

API liên quan:

~~~java
SpringApplication application =
        new SpringApplication(MyApplication.class);

// Mặc định true. Không tắt khi dựa vào DevTools restart.
application.setRegisterShutdownHook(true);
application.run(args);
~~~

Đây là **snippet**; cần định nghĩa lớp **MyApplication** và imports tương ứng. Tài liệu SpringApplication 3.3 nêu **setRegisterShutdownHook(...) mặc định true**, nhằm hỗ trợ đóng context khi JVM shutdown.

Spring Boot 3.3 DevTools nêu rõ rằng **restart phụ thuộc application context shutdown hook** để đóng context cũ. Nếu dùng:

~~~java
application.setRegisterShutdownHook(false);
~~~

DevTools **không hoạt động đúng** theo tài liệu chính thức. Không được khuyến nghị tắt cơ chế này chỉ để làm output console trông đơn giản hơn hoặc tự quản lý dừng server.

### 3.1. Phân biệt ba hành động dễ nhầm

| Hành động | Mô tả | Điều quan trọng |
| --- | --- | --- |
| **Đăng ký shutdown hook** | SpringApplication thiết lập cơ chế đóng context khi JVM shutdown | DevTools cần cơ chế này còn khả dụng |
| **Đóng ApplicationContext** | Spring gọi lifecycle stop/destroy trên bean được quản lý | Có thể xảy ra khi DevTools restart, không cần JVM exit |
| **JVM chạy các Runtime shutdown hooks** | JVM bắt đầu quá trình shutdown thực sự | Không được mặc định xảy ra với mỗi DevTools restart |

Một **DevTools restart không phải JVM shutdown**. Khi application context cũ được đóng, các callback Spring như **@PreDestroy** có thể chạy. Nhưng **không nên giả định JVM sẽ thực thi mọi Thread mà ứng dụng tự đăng ký bằng Runtime.addShutdownHook(...) sau mỗi lần reload**.

Đây là ranh giới quan trọng nhất của bài: **Spring bean destruction callbacks** gắn với việc đóng context; **Runtime.addShutdownHook** gắn với trình tự kết thúc JVM.

### 3.2. Vì sao cụm từ “shutdown hook” trong DevTools dễ gây hiểu nhầm?

Tài liệu DevTools nói: restart cần **application context's shutdown hook** để đóng context. Đây là quan hệ tích hợp giữa DevTools và cơ chế đóng context của SpringApplication. Không có nghĩa DevTools mô phỏng một lệnh **System.exit()** hoặc gửi SIGTERM mỗi khi classpath thay đổi.

Nếu bạn đang theo dõi log:

~~~text
CONTEXT_CLOSING ...
RESOURCE_DESTROY ...
NEW_CONTEXT_STARTED ...
~~~

thì đó là bằng chứng context được đóng rồi tạo lại. Nó **không chứng minh toàn JVM đã thực hiện shutdown sequence** hoặc tất cả custom JVM hooks đều chạy.

### 3.3. Khi nào nên gọi context.close() thủ công?

Trong một chương trình CLI hoặc integration test cần kết thúc theo chủ đích, **context.close()** là cách trực tiếp để yêu cầu Spring đóng lifecycle của context hiện tại.

Trong ứng dụng web đang dùng DevTools, **không thêm context.close() ngay sau SpringApplication.run(...)**: ứng dụng sẽ tự đóng server khi main trở về, thay vì chờ DevTools/watchers và request từ developer.

Với ứng dụng phục vụ lâu dài, để SpringApplication/DevTools điều phối context; chỉ đóng chủ động khi đó là một thao tác lifecycle được thiết kế và kiểm soát.

## 4. Điều gì được dọn dẹp khi đóng ApplicationContext?

Spring quản lý lifecycle cho những bean được đăng ký đúng. Khi đóng context bình thường, các cơ chế có thể tham gia gồm:

- **ContextClosedEvent:** event báo context đang đóng.
- **SmartLifecycle.stop(...)** và các pha dừng có thứ tự.
- **@PreDestroy:** callback destruction cho bean managed tương ứng.
- **DisposableBean.destroy():** cơ chế destruction của Spring.
- **@Bean(destroyMethod = "close")** hoặc destroy method khác.
- **AutoCloseable / Closeable** trong các trường hợp bean definition có inference phù hợp.
- **Embedded WebServer stop:** giải phóng cổng và hạ tầng request theo cách server hỗ trợ.
- **Executor/scheduler bean shutdown:** tùy bean, configuration và chính sách chờ công việc.

Đối với nhiều loại bean thông thường, Spring gọi các destruction callbacks khi **ApplicationContext.close()** diễn ra. Nhưng **không có bảo đảm tất cả custom resources bên ngoài context sẽ được đóng**, và các trường hợp crash/hard kill cũng không bảo đảm callback được gọi.

### 4.1. ContextClosedEvent không phải @PreDestroy

| Cơ chế | Vai trò | Hạn chế |
| --- | --- | --- |
| **ContextClosedEvent** | Cho listener biết context đang đóng | Không phải nơi tốt để block vô hạn |
| **SmartLifecycle.stop(callback)** | Dừng component có lifecycle chủ động; có thể dùng pha và callback | Phải gọi callback hoàn tất; tránh deadlock |
| **@PreDestroy** | Thả resource do bean đang sở hữu | Chỉ chạy nếu bean managed và context tiến qua destruction |
| **DisposableBean.destroy** | Hợp đồng destruction cụ thể của Spring | Tăng coupling vào Spring |
| **@Bean destroyMethod** | Khai báo phương thức đóng cho bean third-party | Cần đúng signature và ownership |
| **Runtime.addShutdownHook** | Callback ở shutdown JVM | Không phải callback per DevTools restart |

Trong quá trình đóng context thông thường, **ContextClosedEvent** được phát và lifecycle components được dừng trước general destruction. Đừng viết code phụ thuộc thứ tự tuyệt đối giữa mọi bean tùy chỉnh, đặc biệt nếu sử dụng async listeners, pha khác nhau hoặc xảy ra lỗi bootstrap.

### 4.2. Spring chỉ dọn những tài nguyên mà nó biết

Ví dụ sai:

~~~java
@Component
class WorkerStarter {

    @PostConstruct
    void begin() {
        Thread thread = new Thread(() -> loopForever());
        thread.start();
    }
}
~~~

Đây là **anti-pattern snippet**, giả định có method loopForever(). Spring biết bean **WorkerStarter**, nhưng **không tự biết** cách hủy Thread tự tạo. Nếu không có stop flag, interrupt/join hoặc shutdown policy, thread cũ có thể chạy tiếp sau DevTools restart.

Nếu một thread cũ giữ context classloader hoặc tham chiếu tới application bean, nó có thể giữ các class/objects của restart classloader cũ trong bộ nhớ và gây **classloader leak**.

### 4.3. Đăng ký resource ngoài Spring khiến việc đóng thiếu chủ sở hữu

Các ví dụ cần quản lý rõ:

- **ExecutorService** tạo bằng Executors.newFixedThreadPool hoặc newSingleThreadScheduledExecutor.
- **Timer / TimerTask** tự tạo.
- **ServerSocket / Socket / FileChannel / WatchService**.
- **JDBC Connection** được mở và giữ trực tiếp ngoài pool.
- **HTTP client/connection manager** bên thứ ba có close/shutdown API.
- **MBean đăng ký thủ công** vào platform MBeanServer.
- **Listener/callback** đăng ký trong một registry ngoài Spring.
- **Global static cache**, ThreadLocal, callback trong thư viện singleton giữ application classes.

Nếu tài nguyên được tạo bên trong bean, cần đảm bảo **bean cũng đóng tài nguyên đó** khi bị destroy. Với tài nguyên do thư viện tạo, có thể dùng adapter bean và destroyMethod.

## 5. Vì sao resource leak dễ lộ khi dùng DevTools?

Ở lần khởi chạy JVM mới hoàn toàn, một số leak chưa dễ thấy vì khi tiến trình chết, hệ điều hành thu hồi file descriptors và TCP sockets, JVM memory biến mất.

Nhưng DevTools giữ JVM sống qua nhiều vòng restart:

~~~text
Start #1:
  classloader 1 -> executor 1 -> 2 threads

Restart #1, thiếu cleanup:
  classloader 1 -> executor 1 -> 2 threads VẪN CHẠY
  classloader 2 -> executor 2 -> 2 threads

Restart #2, thiếu cleanup:
  classloader 1 -> executor 1 -> 2 threads
  classloader 2 -> executor 2 -> 2 threads
  classloader 3 -> executor 3 -> 2 threads

Kết quả:
  nhiều tác vụ cùng chạy, heap giữ classloaders cũ,
  tài nguyên và log bị nhân lên.
~~~

Nếu bean shutdown đúng, executor cũ dừng và classloader cũ không còn bị tham chiếu bởi các hoạt động đó. Việc GC thu hồi classloader là **điều kiện có thể xảy ra khi không còn strong references**, không phải điều được bảo đảm tức thời sau mỗi DevTools restart.

### 5.1. Restart classloader và base classloader làm leak phức tạp

DevTools thường đặt application classes ở **restart classloader** và thư viện JAR ở **base classloader**. Một singleton hoặc static cache trong thư viện ở base classloader có thể giữ reference tới object từ restart classloader.

Ví dụ một thư viện đăng ký callback và không unregister:

~~~text
BaseClassLoader
   |
   +-- GlobalRegistry static Map
           |
           +-- callback from RestartClassLoader #1
           +-- callback from RestartClassLoader #2
           +-- callback from RestartClassLoader #3
~~~

Do base classloader vẫn sống, map đó có thể giữ nhiều application classloaders cũ. Trong trường hợp này, chỉ tạo bean Spring mới không xóa được callback của context trước nếu không có unregister.

**Giải pháp:** khi @PostConstruct đăng ký vào registry, @PreDestroy phải gọi phương thức unregister đúng instance/token; hoặc dùng resource wrapper AutoCloseable.

### 5.2. Thread context classloader cũng có thể giữ reference

Một thread được tạo từ application code có thể kế thừa **Thread.contextClassLoader** của thread hiện tại. Nếu thread vẫn sống sau restart, nó có thể giữ reference tới restart classloader cũ ngay cả khi không còn trực tiếp gọi application method.

**Đừng cố giải quyết leak bằng cách chỉ đặt thread.setContextClassLoader(null).** Nó có thể giảm một dạng reference nhưng không đóng socket, không dừng công việc và không xóa các callback đã đăng ký. Cần dừng tài nguyên đúng lifecycle.

### 5.3. Static field không nhất thiết “sống mãi” sau DevTools restart

Static state của một class **được nạp ở restart classloader** nằm trong phạm vi classloader đó, nên khi tạo classloader mới có thể có một bản static mới.

Ngược lại, static state của class **nằm ở base classloader** có thể tồn tại qua nhiều lần restart.

Vì vậy không nên kết luận mọi static counter sẽ tiếp tục tăng qua restart, hoặc mọi static cache sẽ được reset. Hành vi phụ thuộc **class nào được loader nào nạp và reference nào còn tồn tại**.

## 6. Ví dụ Spring Boot 3.3 chạy được: quan sát OPEN / CLOSE / OPEN

Dự án Java 17+ dưới đây tạo:

1. Một web app Spring MVC/Tomcat để developer giữ process đang chạy.
2. Một bean **ManagedPollingResource** tạo scheduled executor cục bộ.
3. **@PostConstruct** mở tài nguyên.
4. **@EventListener(ContextClosedEvent.class)** ghi thời điểm context đóng.
5. **@PreDestroy** đóng executor, chờ có giới hạn và xử lý interruption.
6. **ApplicationRunner** in resource ID, PID và classloader.
7. Endpoint phát triển **GET /debug/resource** để quan sát context instance hiện tại.

Khi sửa class và build, DevTools restart context. Một **resource ID mới** xuất hiện; resource cũ in CLOSE trong quá trình đóng. **PID** thường giữ nguyên vì JVM chưa bị restart.

### 6.1. Cấu trúc Maven

~~~text
devtools-lifecycle-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/devtools/DevtoolsLifecycleDemo.java
  src/test/java/com/example/devtools/ManagedResourceTest.java
~~~

**Điều kiện:** JDK 17+, Maven và IDE hoặc terminal có thể compile classpath khi app đang chạy.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>devtools-lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
            <scope>runtime</scope>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

**Chú ý DevTools là development-time dependency.** Maven đánh dấu optional để không đưa transitively sang module tiêu thụ. Spring Boot Maven plugin mặc định loại DevTools khỏi repackaged executable archive. Không tự bật DevTools cho production bằng cách sửa packaging exclusions.

### 6.3. application.properties

~~~properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s

spring.devtools.restart.enabled=true
spring.devtools.restart.log-condition-evaluation-delta=false
~~~

Ý nghĩa:

- **spring.devtools.restart.enabled=true:** cho phép chức năng restart khi DevTools hoạt động trong môi trường phát triển thích hợp.
- **server.shutdown=graceful:** khi context đóng, Tomcat cho HTTP request đang xử lý một khoảng grace và từ chối request mới theo cơ chế Boot 3.3.
- **spring.lifecycle.timeout-per-shutdown-phase=10s:** giới hạn chờ trên mỗi pha SmartLifecycle.
- **log-condition-evaluation-delta=false:** giảm log diff conditions khi restart; không thay đổi logic cleanup.

Graceful web shutdown chỉ xử lý embedded web server; **background executor trong ví dụ vẫn cần chính sách shutdown riêng**.

### 6.4. Java application hoàn chỉnh

Tạo **src/main/java/com/example/devtools/DevtoolsLifecycleDemo.java**:

~~~java
package com.example.devtools;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DevtoolsLifecycleDemo {

    public static void main(String[] args) {
        // Giữ shutdown hook mặc định: KHÔNG gọi
        // application.setRegisterShutdownHook(false).
        SpringApplication.run(DevtoolsLifecycleDemo.class, args);
    }

    @Bean
    ApplicationRunner startupLog(ManagedPollingResource resource) {
        return args -> System.out.println(
                "RUNNER id=" + resource.id()
                + " pid=" + ProcessHandle.current().pid()
                + " loader="
                + DevtoolsLifecycleDemo.class.getClassLoader()
                        .getClass().getName());
    }
}

@Component
class ManagedPollingResource {

    private final String id =
            UUID.randomUUID().toString().substring(0, 8);

    private final AtomicBoolean closed = new AtomicBoolean();
    private ScheduledExecutorService executor;

    @PostConstruct
    void start() {
        executor = Executors.newSingleThreadScheduledExecutor(task -> {
            Thread thread = new Thread(
                    task, "demo-poll-" + id);
            thread.setDaemon(true);
            return thread;
        });

        System.out.println("OPEN id=" + id);

        executor.scheduleWithFixedDelay(
                () -> System.out.println("TICK id=" + id),
                0, 3, TimeUnit.SECONDS);
    }

    @EventListener(ContextClosedEvent.class)
    void onClosing() {
        System.out.println("CONTEXT_CLOSING id=" + id);
    }

    @PreDestroy
    void cleanup() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }

        System.out.println("CLOSE id=" + id);

        ScheduledExecutorService current = executor;
        if (current == null) {
            return;
        }

        current.shutdown();

        try {
            if (!current.awaitTermination(2, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    String id() {
        return id;
    }

    boolean isClosed() {
        return closed.get();
    }
}

@RestController
class ResourceDebugController {

    private final ManagedPollingResource resource;

    ResourceDebugController(ManagedPollingResource resource) {
        this.resource = resource;
    }

    @GetMapping("/debug/resource")
    Map<String, String> info() {
        return Map.of(
                "resourceId", resource.id(),
                "pid", Long.toString(ProcessHandle.current().pid()),
                "closed", Boolean.toString(resource.isClosed()),
                "classLoader",
                DevtoolsLifecycleDemo.class.getClassLoader()
                        .getClass().getName());
    }
}
~~~

**Tại sao mã hợp lệ?**

- **DevtoolsLifecycleDemo** là public top-level class, trùng tên file; các class còn lại package-private cùng package.
- **@SpringBootApplication** và component scan nhận diện **@Component** và **@RestController**.
- **@PostConstruct/@PreDestroy** dùng **jakarta.annotation** phù hợp với Spring Boot 3.x.
- **ManagedPollingResource** giữ executor như một tài nguyên của bean, nên khi bean bị destroy có thể đóng nó.
- **AtomicBoolean** giúp cleanup có tính **idempotent** nếu code vô tình gọi nhiều lần trong một tình huống thử nghiệm.
- **shutdown()** ngừng nhận task mới; **awaitTermination(2s)** chờ có giới hạn; **shutdownNow()** yêu cầu hủy/interruption nếu hết thời gian.
- Worker thread được đặt daemon trong demo, không phải cách khắc phục resource leak; thread vẫn phải bị dừng khi context đóng.
- **ApplicationRunner** chạy sau refresh; PID in bằng ProcessHandle.current().pid() giúp đối chiếu giữa lần restart.
- Endpoint **/debug/resource** là công cụ học tập, **không nên expose thông tin runtime hoặc classloader ra production**.

### 6.5. Những điều không nên suy diễn từ demo

Không bảo đảm dòng **TICK** xuất hiện sau mọi dòng RUNNER, vì scheduler chạy trên thread riêng và có thể ghi log xen kẽ. Không bảo đảm object ID trùng hoặc khác theo một quy luật số học; nó được tạo ngẫu nhiên mỗi lần bean mới xuất hiện.

Sau DevTools restart thành công, quan sát thường có:

~~~text
OPEN id=<old-id>
RUNNER id=<old-id> pid=<same-pid> loader=<restart-loader>
TICK id=<old-id>

... classpath changes ...

CONTEXT_CLOSING id=<old-id>
CLOSE id=<old-id>
OPEN id=<new-id>
RUNNER id=<new-id> pid=<same-pid> loader=<restart-loader>
TICK id=<new-id>
~~~

**Đây là log dạng minh họa, không phải stdout literal bất biến.** Giá trị ID, PID, tên classloader và thời điểm TICK phụ thuộc môi trường. Thông tin quan trọng là **ID cũ được CLOSE trước/đúng quá trình thay bằng ID mới** và **không còn TICK từ resource cũ sau khi cleanup kết thúc**.

### 6.6. Build và chạy trong development mode

Từ thư mục dự án:

~~~bash
java -version
mvn spring-boot:run
~~~

Lệnh **mvn spring-boot:run** chạy trên classpath phát triển, nơi DevTools có thể quan sát class trong thư mục output. Khi sử dụng Maven/Gradle build plugin, cần giữ cơ chế **forking** để DevTools có isolated application classloader theo tài liệu Boot 3.3.

Tại terminal khác:

~~~bash
curl http://localhost:8080/debug/resource
~~~

Ví dụ response minh họa:

~~~json
{
  "resourceId": "7d5e28f0",
  "pid": "12345",
  "closed": "false",
  "classLoader": "org.springframework.boot.devtools.restart.classloader.RestartClassLoader"
}
~~~

**Không assert nguyên văn** resourceId, PID hoặc classloader name. Kiểm tra đúng ứng dụng của bạn: nếu classLoader không tương tự restart loader, có thể DevTools không active trong cách chạy hiện tại.

### 6.7. Kích hoạt một DevTools restart thật

Trong IDE, sửa một dòng Java không làm sai code, lưu và **Build Project** nếu IDE chưa tự compile classpath output. Nếu dùng terminal, sau khi sửa source có thể chạy trong terminal riêng:

~~~bash
mvn compile
~~~

DevTools theo dõi classpath directory. Sau khi compiler cập nhật .class trong **target/classes**, DevTools có thể phát hiện và restart. Không phải mọi lần Save nếu code chưa compile đều kích hoạt restart.

Gọi lại:

~~~bash
curl http://localhost:8080/debug/resource
~~~

Kiểm tra:

- **resourceId** mới khác giá trị trước (UUID, gần như chắc chắn).
- **pid** thường giữ nguyên trong DevTools restart.
- Console có log **CONTEXT_CLOSING/CLOSE** cho ID trước và **OPEN/RUNNER** cho ID mới.
- Chỉ có một chuỗi TICK từ ID hiện tại sau khi restart hoàn tất.
- Nếu sửa class nhưng IDE thực sự kill/relaunch process, PID có thể đổi: đó là đường **process restart**, không phải DevTools restart nội bộ.

**Không dùng lệnh java -jar target/...jar để kiểm tra DevTools restart mặc định.** Spring Boot 3.3 thường tự disable DevTools khi chạy một fully packaged application; DevTools cũng được loại khỏi repackaged JAR theo cấu hình mặc định.

### 6.8. Khi dừng ứng dụng trong IDE hoặc bằng Ctrl+C

Khi process thật sự kết thúc qua đường shutdown bình thường, Spring có cơ hội đóng context và chạy **@PreDestroy** cho bean. Nếu IDE dùng hard terminate hoặc JVM bị kill cưỡng bức, cleanup callbacks không được bảo đảm.

Một DevTools restart trong khi JVM còn hoạt động **không phải** cùng hành động với Ctrl+C/ SIGTERM kết thúc toàn process. Kiểm tra đúng loại thao tác trong log và PID trước khi kết luận.

## 7. JUnit 5: kiểm tra bean destruction, không giả vờ giả lập DevTools

Có thể kiểm tra rằng context close gọi **@PreDestroy** bằng một Spring context nhỏ, không cần bật DevTools hoặc mở server thật.

Tạo **src/test/java/com/example/devtools/ManagedResourceTest.java**:

~~~java
package com.example.devtools;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ManagedResourceTest {

    @Test
    void closingContextCleansUpManagedExecutor() {
        ManagedPollingResource resource;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(ManagedPollingResource.class);
            context.refresh();

            resource = context.getBean(ManagedPollingResource.class);
            assertFalse(resource.isClosed());
        }

        // try-with-resources đã gọi context.close().
        assertTrue(resource.isClosed());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test xác minh rằng **bean đã được Spring quản lý**, đã khởi tạo và context close dẫn tới destruction callback đổi trạng thái **closed=true**.

**Phạm vi test:** nó không tạo DevTools restart classloader hay mô phỏng thay classpath. Test thuần về Spring lifecycle giúp bảo đảm hợp đồng cleanup của resource **độc lập** với cách DevTools điều phối restart.

### 7.1. Test nào chứng minh DevTools thực sự đóng resource cũ?

Một integration/smoke test ở môi trường dev nên:

1. Chạy app bằng **mvn spring-boot:run** với DevTools active.
2. Quan sát một resource ID ban đầu và PID.
3. Thay đổi, compile một application class để kích hoạt restart.
4. Quan sát **CONTEXT_CLOSING** và **CLOSE** cho resource ID cũ.
5. Quan sát **OPEN** và **RUNNER** cho resource ID mới.
6. Chờ qua hai hoặc ba chu kỳ của poller để phát hiện các TICK từ ID cũ nếu có leak.
7. Kiểm tra số lượng threads/ports/handles không tăng theo số vòng restart.
8. Thử lặp lại một số vòng để thấy lỗi tích lũy thay vì chỉ một vòng.

Không dựa chỉ vào **@SpringBootTest contextLoads**: nó không tự dùng cơ chế DevTools restart của IDE và có thể chạy tốt trong khi production/dev lifecycle khác nhau.

### 7.2. Đừng viết test dựa vào stdout timing tuyệt đối

Vì poller chạy bất đồng bộ, một dòng TICK có thể xuất hiện trước hoặc sau RUNNER. Test nên xác nhận **tài nguyên cũ đã dừng sau close**, không phải bắt thứ tự tuyệt đối của mọi log đa luồng.

Nếu muốn test termination, nên dùng **CountDownLatch** hoặc điều kiện trạng thái executor với deadline ngắn, không chỉ **Thread.sleep(1000)** và hy vọng mọi tác vụ tự dừng.

## 8. Vòng đời đúng cho từng loại tài nguyên

### 8.1. ExecutorService tạo thủ công

Nếu bean sở hữu ExecutorService, cần explicit shutdown khi destroy:

~~~java
@Component
class WorkerOwner {

    private final ExecutorService workers =
            Executors.newFixedThreadPool(2);

    @PreDestroy
    void stop() {
        workers.shutdown();

        try {
            if (!workers.awaitTermination(3, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        } catch (InterruptedException ex) {
            workers.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Đây là snippet cần các imports và phần task submission. **shutdownNow() chỉ yêu cầu interrupt**, không bảo đảm mọi task luôn tuân thủ interruption hoặc đã dừng. Cần đảm bảo task có timeout và logic kết thúc phù hợp.

Tốt hơn khi có thể: dùng executor/scheduler do Spring quản lý, cấu hình bean có destroy/lifecycle policy, để framework phối hợp shutdown.

### 8.2. @Scheduled và TaskScheduler do Spring quản lý

Với **@EnableScheduling** và một TaskScheduler bean thuộc context, Spring có cơ chế lifecycle cho scheduler. Khi context đóng, scheduler thường được dừng theo chính sách bean tương ứng.

Nhưng **một @Scheduled job đang chạy không tự được hoàn tất vô thời hạn** chỉ vì DevTools restart. Nếu job viết database, gửi message hoặc gọi API ngoài, cần xác định:

- Job có được phép bị interrupt không?
- Có cần đợi job commit xong trước khi tạo instance mới không?
- Có thể chạy trùng ở thời điểm hai contexts chuyển giao không?
- Có idempotency và transaction boundary phù hợp không?
- Có timeout và retry sau restart nếu quan trọng không?

Không được coi DevTools restart như durable job scheduler hoặc bảo đảm exactly-once execution.

### 8.3. TCP socket và file handles

Một tài nguyên như **ServerSocket** hoặc **FileChannel** có thể đóng bằng **close()**. Nếu tạo là bean và Spring sở hữu nó, có thể khai báo destruction:

~~~java
@Configuration(proxyBeanMethods = false)
class SocketConfiguration {

    @Bean(destroyMethod = "close")
    ServerSocket localSocket() throws IOException {
        return new ServerSocket(0);
    }
}
~~~

Đây là snippet cần imports và phải nằm trong configuration hợp lệ; port 0 yêu cầu OS cấp ephemeral port. Trường hợp này chỉ minh họa bean ownership, không có accept loop hoặc protocol server hoàn chỉnh.

Khi context đóng, Spring gọi close trên bean socket. Nếu cùng một socket được tạo **bằng new bên trong static initializer** và không quản lý lifecycle, Spring không tự biết cần đóng nó.

### 8.4. Database connection pool

Spring Boot auto-configured **DataSource/HikariCP** được đăng ký làm bean với lifecycle đóng pool tương ứng. Khi DevTools restart context cũ, pool managed đúng được đóng rồi pool mới được tạo.

Nếu ứng dụng tự tạo thêm một HikariDataSource bên ngoài bean container và không gọi close, có thể leak connection/worker thread qua restart. Không dùng DevTools hoặc Hibernate làm lý do bỏ qua ownership.

Cần phân biệt:

- **Một DataSource bean managed**: Spring quản lý destruction.
- **Connection lấy từ pool**: code cần đóng connection handle đúng sau mỗi operation/transaction.
- **Custom connection pool tạo thủ công**: owner phải cung cấp close trong lifecycle.

### 8.5. Messaging consumers và observers

Kafka/RabbitMQ/JMS consumers có thể tạo threads, listeners và connections. Nếu chúng thuộc Spring-managed listener containers, framework có lifecycle stop/close. Nếu tự đăng ký listener vào một external/global registry, bean phải **unregister** khi close.

Không để context mới bắt đầu consume đồng thời với context cũ không dừng hết nếu nghiệp vụ không cho phép overlapping. Khi test, dùng event ID và client instance ID để phát hiện duplicate processing.

### 8.6. File WatchService, Timer, thread-local và callbacks

Các đối tượng sau đặc biệt dễ bị quên:

- **WatchService** có close API.
- **Timer** có cancel API.
- **ThreadLocal** trên threads dùng lại cần remove đúng.
- **MBean** tự đăng ký cần unregister.
- **Global event bus callback** cần remove listener.
- **Static cache** giữ các class application cần invalidate/unregister.
- **Third-party scheduler** cần shutdown/dispose theo hợp đồng thư viện.

**Khái niệm ownership:** thành phần nào tạo/đăng ký một resource thì phải biết chính xác khi nào và bằng API nào để giải phóng nó.

## 9. Vì sao Runtime.addShutdownHook không thay cho @PreDestroy?

Một anti-pattern phổ biến:

~~~java
@PostConstruct
void registerJvmHook() {
    Runtime.getRuntime().addShutdownHook(
            new Thread(() -> cleanupExternalResource()));
}
~~~

Đây là snippet minh họa, giả định method cleanupExternalResource(). Vấn đề:

- Hook gắn với **JVM shutdown**, không phải chắc chắn DevTools restart.
- Mỗi lần bean mới được tạo sau restart có thể đăng ký thêm một hook.
- Runtime giữ reference tới Thread/callback, từ đó có thể giữ application classloader cũ.
- Nhiều hook có thể cùng cố đóng một tài nguyên, chạy sai thứ tự hoặc gây lỗi.
- Nếu JVM bị SIGKILL, các hook cũng không được chạy.

**Nên dùng @PreDestroy hoặc bean destroyMethod** cho resource theo vòng đời context. Nếu thư viện bắt buộc đăng ký một JVM hook, phải nắm đầy đủ cơ chế unregister hoặc quản lý hook ở một layer sống cùng JVM, và hiểu giới hạn của Runtime.removeShutdownHook khi JVM đã bắt đầu shutdown.

### 9.1. Spring shutdown hook vẫn phải được đăng ký

Đừng hiểu phần trên thành “tắt tất cả shutdown hook”. **SpringApplication shutdown hook mặc định phải được giữ** để DevTools restart hoạt động đúng theo tài liệu Boot 3.3.

Tách hai ý:

- **Giữ** shutdown hook do SpringApplication quản lý (không gọi setRegisterShutdownHook(false)).
- **Không lạm dụng** Runtime.addShutdownHook cho resource thuộc một ApplicationContext có thể được DevTools restart.

### 9.2. Nếu thư viện tự tạo JVM hook thì sao?

Một số thư viện đăng ký hook toàn cục để đóng tài nguyên. Nếu thư viện được nạp bởi base classloader và hook/registry tồn tại qua restart, cần xem nó có API shutdown/reset hoặc có thể tích hợp với Spring-managed bean không.

Nếu không có cơ chế cleanup phù hợp, có thể cân nhắc tắt DevTools restart riêng cho môi trường phát triển có thư viện đó, hoặc cấu hình classloader rules, nhưng **không tự giả định đổi classloader là sửa được một resource leak**.

## 10. SmartLifecycle khi cần dừng đúng thứ tự

Một bean sở hữu một background consumer có thể dùng **SmartLifecycle** thay vì chỉ @PreDestroy khi cần:

- Tự khởi động sau context refresh.
- Dừng theo pha trước hoặc sau component khác.
- Nhận callback completion cho asynchronous stop.
- Điều phối phụ thuộc với HTTP server, executor hoặc connection pools.

Mẫu khái niệm:

~~~java
@Component
class MyConsumerLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // start consumer
    }

    @Override
    public void stop(Runnable callback) {
        try {
            running = false;
            // stop accepting new work; drain bounded tasks
        } finally {
            callback.run();
        }
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
~~~

Đây là **snippet chưa cài đặt consumer thật**, cần import SmartLifecycle và Component. Trọng tâm là **stop(Runnable callback)** phải gọi callback.run() sau khi stop hoàn tất, kể cả khi lỗi, để lifecycle processor biết phase có thể tiếp tục.

Một implementation production cần state machine thread-safe, timeout, idempotent stop và xử lý failure. **Không được block vô hạn trong stop(...) hoặc chờ chính thread đang chạy stop**, vì có thể làm DevTools restart treo.

### 10.1. Phase có ý nghĩa gì?

Theo Spring Framework, các SmartLifecycle bean có **phase** để xác định thứ tự stop/start. Nói khái quát:

- Phase cao thường **start muộn hơn và stop sớm hơn** phase thấp.
- Phase thấp thường **start sớm hơn và stop muộn hơn**.
- Dependencies có thể điều chỉnh thứ tự thực tế.

Với Boot web server, graceful shutdown diễn ra ở pha sớm của stop lifecycle. Nếu một HTTP request đang cần một background executor hoặc datasource, đừng thiết kế component đó stop quá sớm khiến request không thể hoàn tất.

### 10.2. @PreDestroy vẫn hữu ích sau SmartLifecycle.stop

Nếu SmartLifecycle.stop chịu trách nhiệm **ngừng nhận việc và drain**, @PreDestroy có thể là lớp **đóng tài nguyên cuối cùng**. Hai callback nên idempotent, không ném exception không kiểm soát và không giả định stop luôn chạy trước destroy trong mọi trường hợp bất thường.

Spring Framework ghi nhận một số failure paths có thể chỉ gọi destroy, không có stop trước đó. Do vậy destruction cần tự đủ an toàn.

## 11. Graceful shutdown và DevTools restart

Với ứng dụng web, có thể bật:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=10s
~~~

Khi context đóng theo đường lifecycle bình thường, Boot cho embedded server cơ hội chờ in-flight requests và ngăn requests mới trong giới hạn. Điều đó có thể áp dụng cho context đang bị DevTools thay thế, nếu server được đóng qua đúng đường lifecycle.

Tuy nhiên:

- DevTools restart **không phải** một rolling deployment.
- Request trong IDE có thể bị cắt khi restart; đây không phải cam kết zero-downtime.
- Một WebSocket/SSE stream hoặc request dài có thể vượt timeout.
- Executor/background tasks có shutdown policy riêng.
- Khi IDE dùng hard terminate, graceful shutdown hook có thể không chạy.

Trong Boot 3.3, **server.shutdown=graceful** cần bật tường minh nếu muốn cơ chế đó (mặc định Boot 3.3 là immediate). Không nhầm với các phiên bản Spring Boot mới hơn có default khác.

### 11.1. Vì sao background executor nên đóng có giới hạn?

Nếu @PreDestroy gọi executor.awaitTermination vô thời hạn, mỗi lần DevTools restart có thể treo. Cần deadline và cơ chế hủy hợp lý. Nếu task đang giữ lock và callback destruction chờ lock đó, deadlock có thể xảy ra.

Với DevTools, lỗi này dễ tái hiện vì người phát triển restart liên tục. Một resource owner nên dừng nhận công việc, chờ bounded time rồi request cancellation, đồng thời ghi log khi không thể dừng đúng.

### 11.2. Nếu cần hoàn tất job dài trước khi restart?

DevTools là công cụ development; nếu tác vụ không được phép mất, cần hệ thống job bền vững hoặc cơ chế checkpoint. Không nên nâng grace period lên nhiều phút rồi dựa vào nó để bảo đảm data integrity.

Có thể tắt restart tạm thời khi debug tác vụ dài hoặc dùng trigger file để chỉ restart lúc đã sẵn sàng, nhưng **đó không thay thế retry/idempotency** trong production.

## 12. Tắt restart đúng cách để khoanh vùng lỗi

Nếu nghi ngờ lỗi do classloader hoặc cleanup, hãy kiểm tra một run **không có DevTools restart** rồi so sánh.

Tắt từ config:

~~~properties
spring.devtools.restart.enabled=false
~~~

Theo tài liệu Boot 3.3, cách này thường **ngăn việc theo dõi file thay đổi**, nhưng một phần restart infrastructure/classloader vẫn có thể được khởi tạo.

Để **vô hiệu hóa restart support hoàn toàn**, đặt **system property trước khi gọi SpringApplication.run(...)**:

~~~java
public static void main(String[] args) {
    System.setProperty(
            "spring.devtools.restart.enabled", "false");
    SpringApplication.run(MyApplication.class, args);
}
~~~

Đây là snippet cần class MyApplication phù hợp. Hoặc cấu hình JVM lúc launch:

~~~bash
java -Dspring.devtools.restart.enabled=false -cp ... com.example.MyApplication
~~~

Dòng này minh họa cờ JVM; phần classpath **...** phải được thay theo môi trường phát triển thực tế, không phải lệnh chạy nguyên văn. Với Maven plugin, dùng cấu hình JVM arguments tương ứng thay vì giả định flags sau run goal là JVM options.

**Không tắt SpringApplication shutdown hook để “tắt DevTools”.** Đó là hai cơ chế khác nhau; tắt hook có thể làm restart xử lý context sai.

### 12.1. Trigger file giúp restart ít bất ngờ hơn

Nếu IDE compile liên tục, có thể dùng:

~~~properties
spring.devtools.restart.trigger-file=.reloadtrigger
~~~

Tạo file **src/main/resources/.reloadtrigger** rồi cập nhật file này sau khi class thay đổi để kích hoạt lần kiểm tra restart.

Trigger file hữu ích khi muốn sửa nhiều lớp rồi mới restart. Nhưng nó **không sửa được tài nguyên không được cleanup**. Dù restart thủ công một lần, context cũ vẫn cần đóng toàn bộ resources.

### 12.2. Exclude tài nguyên không cần restart

DevTools mặc định không full restart với một số static resources/templates. Có thể cấu hình **spring.devtools.restart.additional-exclude** để thêm patterns vào danh sách loại trừ mà vẫn giữ mặc định.

Không cấu hình exclude một thư mục application classes quan trọng chỉ để tránh lỗi cleanup; đó là che lỗi, không phải xử lý vòng đời.

## 13. Classloader issues và cách chẩn đoán

Một số lỗi chỉ xuất hiện khi restart loader thay đổi:

- **ClassCastException** khi class cùng tên được nạp bởi hai loaders khác nhau.
- Deserialize object bằng ObjectInputStream không dùng context classloader phù hợp.
- Reflection caches giữ Class<?> từ restart loader cũ.
- ThreadContextClassLoader dẫn tới service loader chọn class sai.
- Multi-module project phân chia loader không phù hợp.
- Static registries trong library JAR giữ callbacks từ application loader.

Khi DevTools restart lỗi nhưng full JVM launch bình thường, có thể thử tắt restart để xác nhận sự khác biệt. Nếu nguyên nhân là classloader split, Spring Boot hỗ trợ **META-INF/spring-devtools.properties** với **restart.include** và **restart.exclude** để điều chỉnh classpath segments nằm ở loader nào.

Ví dụ minh họa một file cấu hình:

~~~properties
restart.include.project-shared=/project-shared-[^/]+[.]jar
restart.exclude.legacy-module=/legacy-module-[^/]+/
~~~

**Các regex là ví dụ**, phải điều chỉnh theo classpath thực tế. Nó không phải Java application property thông thường đặt trong application.properties. Các key trong META-INF/spring-devtools.properties phải duy nhất, và matching dựa trên classpath entries.

**Tách hai loại lỗi**:

1. **Classloader partition issue**: cần sửa include/exclude hoặc library handling.
2. **Resource lifecycle leak**: cần đóng resource/unregister callbacks; thay loader không tự giải phóng một socket/thread.

### 13.1. Standard ObjectInputStream có thể gây lỗi

Spring Boot docs lưu ý việc deserialize object qua standard ObjectInputStream đôi khi hoạt động không tốt với restart classloader. Nếu thật sự dùng serialization, có thể cần **ConfigurableObjectInputStream** cùng context classloader thích hợp.

Đừng cấu hình serializer/deserializer theo tên class một cách tùy tiện; ưu tiên data formats không phụ thuộc Java classloader và kiểm thử lại khi restart.

### 13.2. Vì sao một class name có thể “giống hệt” nhưng cast thất bại?

Trong JVM, identity của class bao gồm **fully qualified name và defining ClassLoader**. Hai class cùng tên nhưng do loader khác nhau tạo không phải cùng một runtime class. Leak hoặc registry trộn objects của context cũ và mới có thể gây **ClassCastException** rất khó đọc.

Cần log classLoader identity của những object thực sự liên quan, không chỉ tên class. Không công khai classloader details trên HTTP endpoint production.

## 14. Debug tài nguyên bị giữ sau nhiều lần restart

### 14.1. Quan sát log từng vòng context

Nên in các marker tối thiểu:

~~~text
OPEN resource-id=...
CONTEXT_CLOSING resource-id=...
CLOSE resource-id=...
OPEN resource-id=...
~~~

So sánh theo resource ID thay vì chỉ timestamp. Nếu có OPEN mới mà không có CLOSE cũ, cần kiểm tra bean ownership/lifecycle và liệu DevTools có thực sự close context cũ không.

Không suy ra leak chỉ từ việc có log CLOSE: một method có thể in CLOSE nhưng thực tế không ngừng thread hoặc không đóng socket. Hãy kiểm tra trạng thái resource thật.

### 14.2. Quan sát threads

Trong JVM dev đang chạy, có thể lấy thread dump bằng JDK tooling:

~~~bash
jcmd <pid> Thread.print
~~~

**<pid> là placeholder**, thay bằng process ID thật. Tìm những thread tên **demo-poll-...**; sau khi DevTools restart hoàn tất và cleanup chạy đúng, thread của instance cũ không nên tồn tại nữa.

Có thể dùng **jstack** ở các JDK hỗ trợ hoặc JDK Flight Recorder/JFR để phân tích thread churn, allocations và retained references.

### 14.3. Quan sát port và file handles

Triệu chứng:

- Restart đầu tiên thành công, sau đó **BindException: Address already in use**.
- File không thể rename/delete ở Windows.
- Watcher cũ tiếp tục nhận events.
- Pool connections vẫn còn mở dù app đã chạy context mới.

Kiểm tra chủ resource/port và log close. Đừng tự kill một process khác để “giải phóng cổng”; trước hết xác minh đúng process/PID và tài nguyên.

### 14.4. Heap/classloader diagnostics

Với một ứng dụng phát triển bị tăng heap qua nhiều restart, có thể:

1. Lấy heap dump trong môi trường cho phép, tránh dữ liệu nhạy cảm.
2. So sánh số **RestartClassLoader** còn referenced.
3. Theo GC roots tìm Thread, static Map, listener registry hoặc shutdown hooks.
4. Xác định object ở base classloader nào đang giữ application objects cũ.
5. Sửa owner và unregister/close, rồi test lại qua nhiều vòng.

**Không phải cứ còn một RestartClassLoader sau GC snapshot là leak chắc chắn**: có thể nó vẫn còn references hợp lệ trong thời gian chuyển giao. Cần xác định retained path và xem object cũ không còn được dùng sau restart.

## 15. Lỗi thiết kế thường gặp

### 15.1. Tắt hook của SpringApplication

**Sai:** gọi **setRegisterShutdownHook(false)** trong ứng dụng có DevTools restart. Spring Boot docs cảnh báo restart không hoạt động đúng. Hãy giữ default true.

### 15.2. Dùng Runtime.addShutdownHook để đóng resource theo context

Không đúng scope. JVM hook không chạy mỗi lần DevTools restart. Dùng @PreDestroy/SmartLifecycle/destroyMethod.

### 15.3. Tạo Thread mới trong @PostConstruct mà không dừng

Mỗi lần restart có thể tạo thêm worker; thread cũ giữ classloader cũ. Có executor owner và stop policy rõ.

### 15.4. Để global registry giữ listener của context cũ

Unregister ở destruction. Đừng chỉ xóa field reference của bean khi registry vẫn giữ callback.

### 15.5. Chờ task vô hạn trong destruction

Có thể treo DevTools restart. Dùng bounded wait, interruption và retry/checkpoint khi cần.

### 15.6. Cho rằng JVM shutdown hook được gọi ở mọi restart

Sai. Restart không đồng nghĩa JVM exit; Spring context close và Runtime hook là các lifecycle khác nhau.

### 15.7. Cho rằng static cache luôn reset

Không. Class trong base loader có static state giữ lại; class trong restart loader có thể có bản static mới. Xem loader thật.

### 15.8. Tưởng daemon thread không thể leak

Daemon chỉ ảnh hưởng JVM liveness, không tự đóng tài nguyên hoặc xóa reference. Nó vẫn có thể sống qua nhiều context restarts.

### 15.9. Tắt DevTools trong application.properties rồi coi classloader chắc chắn biến mất

Property ở application.properties thường chỉ tắt file watching/restart behavior; muốn disable hoàn toàn, dùng system property trước run hoặc bỏ dependency.

### 15.10. Test bằng executable JAR rồi nói DevTools không hoạt động

DevTools thường tự disable ở fully packaged application và bị loại khỏi repackaged JAR theo mặc định. Hãy dùng dev classpath hoặc Maven/Gradle boot run.

### 15.11. Dựa vào @PreDestroy khi SIGKILL

SIGKILL/crash không bảo đảm Java cleanup. Với công việc quan trọng cần persistence/recovery độc lập.

### 15.12. Coi graceful HTTP shutdown đồng nghĩa mọi async job đã xong

Không. WebServer và TaskExecutor/consumer có chính sách shutdown riêng; cần điều phối nếu chúng phụ thuộc nhau.

### 15.13. Nhầm file save với classpath change

DevTools theo dõi output classpath, không phải bất kỳ thao tác Save source nào. Kiểm tra IDE compile/build.

### 15.14. Không test nhiều vòng restart

Một lần restart có thể chưa lộ leak. Lặp lại vài lần, theo dõi threads/heap/socket và callback count.

### 15.15. Đăng ký hai cách cleanup mà không xét idempotency

Nếu một resource có cả @PreDestroy và external shutdown callback, nó có thể bị đóng nhiều lần hoặc race. Thiết kế close idempotent và xác định rõ owner.

## 16. Checklist trước khi dùng DevTools restart

- [ ] DevTools chỉ có trong development classpath; không bật remote DevTools trong production.
- [ ] Giữ SpringApplication shutdown hook mặc định, không gọi setRegisterShutdownHook(false).
- [ ] Hiểu DevTools restart **không kết thúc toàn JVM**.
- [ ] Phân biệt Spring context destruction với Runtime shutdown hooks.
- [ ] Tài nguyên mở tại @PostConstruct có cleanup ở @PreDestroy hoặc destroyMethod.
- [ ] Executor tạo thủ công có shutdown, bounded await, interruption policy.
- [ ] Task @Scheduled/consumer có stop strategy và tránh overlap nếu cần.
- [ ] Static/global registry unregister callback của context cũ.
- [ ] ThreadLocal và thread context classloader không giữ references cũ không cần thiết.
- [ ] Sockets/file channels/watch services có owner đóng đúng.
- [ ] Connection pool do Spring quản lý hoặc custom pool được close.
- [ ] SmartLifecycle.stop(callback) luôn callback sau khi hoàn tất.
- [ ] Cleanup không block vô hạn và có chính sách khi timeout.
- [ ] Các startup failure paths cũng cleanup tài nguyên cấp phát một phần.
- [ ] Có log OPEN, CONTEXT_CLOSING, CLOSE với resource ID.
- [ ] Test context.close bằng JUnit riêng.
- [ ] Test DevTools thật trong IDE/Maven với classpath được compile.
- [ ] Test lặp restart nhiều lần và kiểm tra thread/port/heap không tăng bất thường.
- [ ] Nếu classloader issue, thử disable restart có kiểm soát, rồi xem include/exclude.
- [ ] Không dựa vào SIGKILL/IDE hard-stop để đánh giá @PreDestroy.
- [ ] Không dùng DevTools làm một cơ chế deploy hoặc bảo đảm zero-downtime.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** DevTools restart có tạo JVM process mới không?

**Đáp án:** Thông thường không. DevTools thay restart classloader và context trong JVM hiện tại; không phải full process restart.

**Câu 2.** Base classloader giữ những gì?

**Đáp án:** Thường là dependency JAR không thay đổi. Nó có thể tồn tại qua nhiều lần restart và giữ static caches/registries lâu hơn context ứng dụng.

**Câu 3.** Vì sao setRegisterShutdownHook(false) gây vấn đề?

**Đáp án:** Spring Boot docs nêu DevTools cần application context shutdown hook để đóng context khi restart; tắt nó khiến restart không hoạt động đúng.

**Câu 4.** Mỗi DevTools restart có gọi mọi Runtime.addShutdownHook callback không?

**Đáp án:** Không nên giả định. Runtime hooks thuộc JVM shutdown; DevTools restart là đóng/thay application context, không phải JVM exit.

**Câu 5.** @PreDestroy được gọi khi nào?

**Đáp án:** Khi Spring destroy một managed bean trong quá trình đóng context bình thường, bao gồm context cũ khi DevTools restart được thực hiện đúng.

**Câu 6.** Một Thread daemon cũ còn sống sau restart có leak được không?

**Đáp án:** Có. Daemon không giữ JVM sống nhưng vẫn có thể giữ classloader/reference, socket hoặc tài nguyên khác.

**Câu 7.** Vì sao static map trong library JAR có thể giữ classloader cũ?

**Đáp án:** Library thường nằm ở base classloader sống qua restart; map có thể giữ callback/object được nạp bởi restart classloader cũ.

**Câu 8.** Làm sao biết một restart đã xảy ra thay vì chỉ LiveReload?

**Đáp án:** Quan sát context/resource ID, các lifecycle logs và restart classloader, không chỉ browser reload hoặc file Save.

**Câu 9.** Có nên đóng context ngay sau SpringApplication.run trong web app?

**Đáp án:** Không, vì sẽ đóng server sau startup. Chỉ đóng chủ động khi ứng dụng/CLI/test có chủ ý kết thúc.

**Câu 10.** Một @SpringBootTest contextLoads có chứng minh DevTools classloader restart không leak?

**Đáp án:** Không. Test đó không tự chạy DevTools restart. Cần smoke test bằng IDE/Maven dev classpath và nhiều vòng restart.

**Câu 11.** Đặt server.shutdown=graceful có tự chờ mọi background task không?

**Đáp án:** Không. Nó tập trung vào web server; executor/scheduler cần shutdown policy riêng.

**Câu 12.** Nếu bean tạo resource rồi @PostConstruct thất bại giữa chừng, có chắc @PreDestroy chạy không?

**Đáp án:** Không nên dựa vào điều đó cho resource chưa hoàn tất đăng ký lifecycle. Dùng try/catch và close cấp phát một phần khi init thất bại.

**Câu 13.** Có nên vô hiệu DevTools bằng cách tắt Spring shutdown hook?

**Đáp án:** Không. Dùng spring.devtools.restart.enabled=false đúng scope hoặc bỏ dependency; giữ hook SpringApplication cho context lifecycle.

**Câu 14.** Khi thấy hai nhóm TICK từ hai resource ID sau restart, nên tìm gì trước?

**Đáp án:** Xem @PreDestroy đã chạy cho ID cũ chưa, executor đã shutdown chưa, và có thread/global registry nào giữ reference cũ.

## 18. Tổng kết

**DevTools restart là thay ApplicationContext và restart classloader trong cùng JVM, không phải JVM shutdown đầy đủ.** Spring Boot 3.3 DevTools phụ thuộc application context shutdown hook: tắt cơ chế đó qua **SpringApplication.setRegisterShutdownHook(false)** có thể làm restart hoạt động sai.

Để dọn dẹp tài nguyên, hãy **gắn ownership của resources vào Spring-managed beans** và sử dụng **@PreDestroy**, **destroyMethod**, hoặc **SmartLifecycle** khi cần thứ tự dừng. Các **Runtime.addShutdownHook** tự tạo không thay cho destruction callbacks khi context bị DevTools restart.

Một DevTools restart đúng nên thấy **context cũ CLOSE, context mới OPEN**, không còn background thread/socket/listener của context cũ tiếp tục hoạt động. Đừng dựa vào GC tự động giải phóng mọi tài nguyên hoặc daemon flags; kiểm tra bằng logs, thread dumps, port/handle counts và vài vòng restart thực tế.

## 19. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Developer Tools, Automatic Restart, Shutdown Hook, Restart vs Reload, Classloader: https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html
- Spring Boot 3.3 — SpringApplication, Application Exit và Shutdown Hooks: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — SpringApplication.setRegisterShutdownHook API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework — Bean Lifecycle, @PreDestroy, DisposableBean, SmartLifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html