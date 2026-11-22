# Kiểm thử close, SmartLifecycle và callback giải phóng tài nguyên trong Spring Boot

## 1. Mục tiêu: kiểm thử **đường dừng**, không chỉ đường khởi động

Một Spring Boot application có thể khởi động thành công nhưng khi dừng lại:
- một consumer tiếp tục nhận message dù datasource đang đóng;
- một thread pool không được shutdown, khiến JVM còn chạy;
- một `SmartLifecycle` quên gọi `callback.run()`, khiến quá trình đóng context chờ tới timeout;
- một resource không nhận được `@PreDestroy` vì nó không phải Spring-managed bean;
- hai bean dừng sai thứ tự, dẫn tới worker còn cần một dependency đã bị giải phóng;
- một test chỉ xác nhận `context.close()` trả về mà không kiểm tra tài nguyên thật sự được release.

Bài này hướng dẫn thiết kế **kiểm thử vòng đời có thể chạy bằng JUnit 5**, tập trung vào ba contract:

1. **`ConfigurableApplicationContext.close()`**: đóng Spring context bình thường, phát `ContextClosedEvent`, dừng các lifecycle components và destroy beans.
2. **`SmartLifecycle`**: tự start, dừng theo phase, hỗ trợ `stop(Runnable callback)` để chờ một bước stop bất đồng bộ.
3. **Callback giải phóng tài nguyên**: `@PreDestroy`, `DisposableBean.destroy()`, custom `@Bean(destroyMethod="...")`, `AutoCloseable` và quyền sở hữu tài nguyên.

Bài dùng **Java 17+**, **Spring Boot 3.5.16**, **Spring Framework 6.2.x**, Maven, AssertJ và JUnit Jupiter. Một phần dùng `AnnotationConfigApplicationContext` để kiểm thử Spring contract nhanh và không làm ô nhiễm context cache; một phần dùng `SpringApplication` để quan sát hành vi Boot thật.

**Nguyên tắc:** test phải đo một sự kiện có thể quan sát được và có assertion rõ ràng: bean đã được stop? Callback đã được gọi? Resource đã đóng đúng một lần? Context còn active không? Những câu hỏi này chính xác hơn việc chỉ so khớp vài dòng log.

## 2. Bản đồ vòng đời cần kiểm thử

Một lần đóng `ApplicationContext` thành công trong điều kiện thông thường có đường đi khái quát:

~~~mermaid
flowchart TD
  A["Context active; SmartLifecycle đang running"] --> B["context.close()"]
  B --> C["Publish ContextClosedEvent"]
  C --> D["LifecycleProcessor.onClose()"]
  D --> E["Stop các lifecycle beans theo phase giảm dần"]
  E --> F["SmartLifecycle.stop(callback)"]
  F --> G["Đợi callbacks trong giới hạn thời gian mỗi phase"]
  G --> H["Destroy các singleton beans"]
  H --> I["@PreDestroy / DisposableBean / custom destroy"]
  I --> J["Context inactive, resource đã release"]
~~~

Đây là **mô hình cho đường đóng context bình thường**. Một context tạo lỗi nửa chừng có thể chỉ dọn được những bean đã tạo; `SIGKILL`/JVM crash không chạy chuỗi dọn dẹp; custom callbacks lỗi hoặc timeout có thể khiến một số công việc không hoàn tất. Test không nên viết giả định rằng mọi shutdown path đều giống nhau.

### Các mốc nên quan sát

| Mốc | API hoặc dấu hiệu | Ý nghĩa kiểm thử |
| --- | --- | --- |
| Context đã refresh | `context.isActive() == true` | Context đang hoạt động |
| Lifecycle đã start | `SmartLifecycle.isRunning() == true` | Bean lifecycle được tự khởi động |
| Bắt đầu đóng | `ContextClosedEvent` | Spring đã bắt đầu xử lý close |
| Stop theo phase | `stop(Runnable)`, `getPhase()` | Các component dừng theo thứ tự cần thiết |
| Async stop đã hoàn tất | `callback.run()` | LifecycleProcessor có thể đi tiếp |
| Bean được destroy | `@PreDestroy` | Container gọi callback trước khi xóa bean |
| Custom destroy | `@Bean(destroyMethod="close")` | Đóng resource đã khai báo |
| Context không còn active | `context.isActive() == false` | Không dùng context như một instance còn mở |
| Process thực sự thoát | Exit status của JVM | Vượt ngoài phép test close của một context đơn lẻ |

`context.close()` **không phải** `System.exit(...)`. Một JVM có thể tiếp tục sống nếu còn non-daemon threads được tạo ngoài cơ chế lifecycle của Spring, dù context đã inactive.

## 3. close(), stop() và JVM shutdown hook khác nhau ra sao?

### 3.1. context.close()

`ConfigurableApplicationContext.close()` đóng context. Trên `AbstractApplicationContext` thông thường, nó xử lý các bước như publish close event, lifecycle processor stop, destroy singleton beans và giải phóng bean factory.

Sau khi close, bạn **không nên tiếp tục lấy bean hoặc gửi request** bằng context đó. Nếu cần chạy một môi trường mới trong unit test, tạo **context mới**, không cố refresh lại một `GenericApplicationContext` đã đóng.

### 3.2. context.stop()

`ConfigurableApplicationContext.stop()` gửi thông báo **stop** cho các `Lifecycle` beans, nhưng **không đồng nghĩa destroy toàn bộ beans**. Context có thể vẫn active và có thể được `start()` lại tùy trạng thái/implementation.

~~~java
context.stop();
boolean activeAfterStop = context.isActive();
context.start();
context.close();
~~~

Đây là snippet trong một test có biến `context` đúng kiểu; không phải chương trình Java độc lập. Nó hữu ích để chứng minh “dừng worker” khác “đóng mọi resource”.

### 3.3. JVM shutdown hook

`SpringApplication` mặc định đăng ký shutdown hook để đóng context trên đường JVM shutdown bình thường. Tuy nhiên, **đăng ký hook không có nghĩa tự chạy hook**. Hook không được bảo đảm chạy khi process bị `SIGKILL`, `Runtime.halt(...)` hoặc crash nghiêm trọng.

**Không gọi `System.exit(...)` ngay trong JUnit test process** để kiểm thử close; thao tác đó có thể kết thúc cả Maven Surefire/Test Runner. Muốn kiểm thử signal/PID/exit code, phải tạo **subprocess riêng**, chạy tích hợp trong CI/staging và có watchdog timeout.

## 4. SmartLifecycle: những hợp đồng quan trọng

`org.springframework.context.SmartLifecycle` mở rộng `Lifecycle` và `Phased`. Khi được Spring quản lý, nó giúp component có start/stop riêng (scheduler, consumer, connection listener...) tham gia vào vòng đời context.

| API | Contract quan trọng |
| --- | --- |
| `start()` | Khởi động component, chuyển sang running khi đã sẵn sàng |
| `isRunning()` | Cho biết trạng thái lifecycle hiện tại |
| `stop()` | Đường stop của `Lifecycle` thông thường, thường nên hỗ trợ khi gọi trực tiếp |
| `stop(Runnable callback)` | Đường stop có callback do LifecycleProcessor sử dụng cho `SmartLifecycle` |
| `isAutoStartup()` | Mặc định `true` trong Spring Framework 6.2; tự start khi refresh |
| `getPhase()` | Quy định thứ tự start/stop theo các phase |
| `SmartLifecycle.DEFAULT_PHASE` | `Integer.MAX_VALUE` trong Spring Framework 6.2 |
| `Lifecycle` thường không implement SmartLifecycle | Thường được xem có phase `0` cho điều phối |

**Đừng đoán default phase của `SmartLifecycle` là `0`.** Trong Spring Framework 6.2, default phase của `SmartLifecycle` là `Integer.MAX_VALUE`, còn `Lifecycle` thông thường có phase mặc định `0`. Một số infrastructure components (chẳng hạn executor/scheduler) có **phase riêng**, nên hãy xác nhận API/version thực tế khi cần sắp xếp thứ tự.

### 4.1. Quy tắc phase

~~~text
START: phase nhỏ -> phase lớn
STOP:  phase lớn -> phase nhỏ
~~~

Ví dụ:
- component `low` có phase `-100`;
- component `high` có phase `100`.

Thứ tự thường mong đợi:

~~~text
start:low
start:high
... context.close() ...
stop:high
stop:low
~~~

Khi có `depends-on`, dependency graph còn ảnh hưởng thứ tự. Không nên ghi một assertion chỉ dựa vào thứ tự scan components khi không có phase/dependency rõ ràng.

### 4.2. stop(Runnable): không quên callback

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stopWorkers();
    } finally {
        callback.run();
    }
}
~~~

Đây là snippet; `stopWorkers()` phải do ứng dụng định nghĩa. Nó minh họa **stop đồng bộ**: callback được gọi sau khi dừng xong hoặc sau đường xử lý lỗi. Nếu `stopWorkers()` chỉ phát tín hiệu interrupt mà không chờ worker thực sự kết thúc, gọi callback ngay **không chứng minh** work đã drain xong.

Với **stop bất đồng bộ**, callback chỉ nên chạy **khi quá trình stop thực sự đạt trạng thái hoàn tất**:

~~~java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewWork();

    drainExecutor.execute(() -> {
        try {
            awaitInflightWork();
        } finally {
            closeOwnedResources();
            callback.run();
        }
    });
}
~~~

Đây là **snippet minh họa**, không phải file chạy độc lập; `drainExecutor` phải tồn tại và có lifecycle riêng. Nếu chính executor dùng để drain đang bị shutdown trước đó, việc submit có thể bị từ chối. Trong production cần đường fallback và deadline có giới hạn.

### 4.3. Timeout theo phase

Spring Boot có property:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=10s
~~~

Mặc định Spring Boot 3.5 tài liệu hóa giá trị **30s**. Timeout được áp dụng **theo nhóm `SmartLifecycle` có cùng phase**, không phải một deadline tuyệt đối cho toàn JVM.

Khi callback không được gọi, lifecycle processor có thể **chờ đến timeout và tiếp tục đóng các phần khác**. Việc context đóng xong không xác nhận component đã hoàn tất flush/commit nếu callback bị bỏ quên hoặc worker không hợp tác.

### 4.4. Chú ý khi stop trực tiếp

Theo Javadoc `SmartLifecycle`, `DefaultLifecycleProcessor` gọi phiên bản `stop(Runnable)` khi đóng context; nó không bắt buộc gọi `stop()` thường trước đó. Vì vậy implement `stop()` nhưng quên `stop(Runnable)` hoặc không hiểu default delegation có thể khiến behavior không đúng kỳ vọng.

## 5. @PreDestroy, destroyMethod và thứ tự callback

Spring hỗ trợ nhiều hook giải phóng tài nguyên:

| Cơ chế | Sử dụng | Lưu ý |
| --- | --- | --- |
| `@PreDestroy` | Method của Spring-managed bean | Spring Boot 3 dùng `jakarta.annotation.PreDestroy` |
| `DisposableBean.destroy()` | Bean implement Spring interface | Coupling với Spring Framework |
| `@Bean(destroyMethod="close")` | Khai báo đóng một bean từ factory method | Phù hợp resource có method `close` |
| Auto-detect destroy | Với nhiều `@Bean` có `close`/`shutdown` hoặc `AutoCloseable` | Phụ thuộc cấu hình bean definition; nên ghi rõ nếu test behavior cụ thể |
| `@EventListener(ContextClosedEvent.class)` | Nhận event context bắt đầu đóng | Không phải bằng chứng mọi resource đã giải phóng |
| `SmartLifecycle.stop(callback)` | Dừng công việc còn sống trước destroy | Không tự thay thế destroy resource |

Khi **cùng một bean** có đầy đủ nhiều destroy callbacks, Spring Framework mô tả thứ tự:
1. `@PreDestroy`;
2. `DisposableBean.destroy()`;
3. custom destroy method.

Bài sẽ test trên **cùng một resource bean** có `@PreDestroy` và custom `close`, nhờ vậy thứ tự kỳ vọng không phụ thuộc vào thứ tự destroy giữa nhiều bean khác nhau.

Một bean được tạo bằng `new` ngoài container **không tự** nhận `@PreDestroy`. Một bean khai báo `@Lazy` nhưng chưa bao giờ được khởi tạo cũng không nhất thiết có instance để destroy. Với prototype beans, Spring container không tự quản lý toàn bộ vòng đời destruction giống singleton; owner phải có chính sách cleanup riêng.

### Resource ownership

Cần chỉ định rõ:
- ai tạo resource?
- ai có quyền đóng resource?
- có worker nào đang sử dụng resource trong lúc close không?
- một lần close có thể được gọi lặp lại không?
- resource có timeout/cancellation không?
- có cần flush/commit trước khi close không?

Một unit test kiểm tra method `close()` được gọi **không đủ** để xác nhận dữ liệu đã commit thành công ở database hoặc broker. Những hiệu ứng đó cần integration test ở ranh giới external system.

## 6. Kiến trúc bài thực hành Java 17+ / Spring Boot 3.5.16

Để test được **thứ tự** và **đếm số lần** callback, ta dùng một timeline recorder trong bộ nhớ, không dựa vào thứ tự các dòng log của logging framework.

Project:

~~~text
lifecycle-close-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/lifecycle/
    │   ├── LifecycleLabApplication.java
    │   └── LifecycleFixtures.java
    └── test/java/com/example/lifecycle/
        ├── LifecycleCloseTest.java
        └── AsyncStopTest.java
~~~

Lab chạy không cần web server, database hoặc message broker. Điều này giúp assertion ổn định và không làm bài kiểm thử bị ảnh hưởng bởi port, network hoặc client chưa khởi tạo.

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-close-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và Spring TestContext qua dependency management của Boot. Test dưới đây không cần `@SpringBootTest` cho mọi method: ta chủ động tạo/đóng context để kiểm thử đúng vòng đời.

### 6.2. LifecycleFixtures.java: recorder, lifecycle và resource

File **`src/main/java/com/example/lifecycle/LifecycleFixtures.java`**:

~~~java
package com.example.lifecycle;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;

import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

public final class LifecycleFixtures {
    private LifecycleFixtures() {
    }

    public static final class Timeline {
        private final CopyOnWriteArrayList<String> entries =
                new CopyOnWriteArrayList<>();

        public void add(String event) {
            entries.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(entries);
        }
    }

    public static final class PhaseProbe
            implements SmartLifecycle {

        private final Timeline timeline;
        private final String name;
        private final int phase;
        private final AtomicBoolean running =
                new AtomicBoolean(false);

        public PhaseProbe(
                Timeline timeline, String name, int phase) {
            this.timeline = timeline;
            this.name = name;
            this.phase = phase;
        }

        @Override
        public int getPhase() {
            return phase;
        }

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                timeline.add("start:" + name);
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                timeline.add("stop:" + name);
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
            return running.get();
        }
    }

    public static final class ResourceProbe {
        private final Timeline timeline;
        private final AtomicInteger preDestroyCount =
                new AtomicInteger();
        private final AtomicInteger closeCount =
                new AtomicInteger();

        public ResourceProbe(Timeline timeline) {
            this.timeline = timeline;
        }

        @PreDestroy
        public void beforeDestroy() {
            preDestroyCount.incrementAndGet();
            timeline.add("predestroy:resource");
        }

        public void close() {
            closeCount.incrementAndGet();
            timeline.add("close:resource");
        }

        public int getPreDestroyCount() {
            return preDestroyCount.get();
        }

        public int getCloseCount() {
            return closeCount.get();
        }
    }

    public static final class CloseObserver {
        private final Timeline timeline;

        public CloseObserver(Timeline timeline) {
            this.timeline = timeline;
        }

        @EventListener
        public void handle(ContextClosedEvent event) {
            timeline.add("event:close");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Timeline timeline() {
            return new Timeline();
        }

        @Bean("low")
        PhaseProbe low(Timeline timeline) {
            return new PhaseProbe(timeline, "low", -100);
        }

        @Bean("high")
        PhaseProbe high(Timeline timeline) {
            return new PhaseProbe(timeline, "high", 100);
        }

        @Bean(destroyMethod = "close")
        ResourceProbe resource(Timeline timeline) {
            return new ResourceProbe(timeline);
        }

        @Bean
        CloseObserver closeObserver(Timeline timeline) {
            return new CloseObserver(timeline);
        }
    }
}
~~~

**Giải thích thiết kế:**

- `Timeline` dùng `CopyOnWriteArrayList` để hỗ trợ cả trường hợp stop bất đồng bộ ở phần sau; `snapshot()` trả danh sách không thay đổi.
- Hai `PhaseProbe` có phase `-100` và `100`; default `isAutoStartup()` của Spring Framework 6.2 là `true`, nên sẽ được start khi context refresh.
- `stop(Runnable)` gọi `stop()` trong `try` và chạy callback trong `finally`; đây là stop đồng bộ ngắn, không có I/O.
- `ResourceProbe` có **hai** callback để đo thứ tự chính xác: `@PreDestroy` và `close()`.
- `@Bean(destroyMethod="close")` buộc Spring gọi custom close trên resource bean. Chúng ta không phụ thuộc suy luận destroy method.
- `CloseObserver` nghe `ContextClosedEvent`; nó chỉ thêm một entry, không phụ thuộc logger.
- Các bean có scope mặc định singleton và khởi tạo eager, phù hợp để test destruction.
- Những record trong timeline có tên cố định; không có timestamp ngẫu nhiên nên test có thể assert.

### 6.3. LifecycleLabApplication.java: chạy Boot thật và đóng context

File **`src/main/java/com/example/lifecycle/LifecycleLabApplication.java`**:

~~~java
package com.example.lifecycle;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;

public final class LifecycleLabApplication {
    private LifecycleLabApplication() {
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(
                LifecycleFixtures.Config.class);

        application.setWebApplicationType(
                WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        LifecycleFixtures.Timeline timeline;

        try (ConfigurableApplicationContext context =
                application.run(args)) {

            timeline = context.getBean(
                    LifecycleFixtures.Timeline.class);

            System.out.println("ACTIVE_BEFORE_CLOSE="
                    + context.isActive());

            LifecycleFixtures.PhaseProbe high =
                    context.getBean(
                            "high",
                            LifecycleFixtures.PhaseProbe.class);

            System.out.println("HIGH_RUNNING="
                    + high.isRunning());
        }

        System.out.println("EVENTS=" + timeline.snapshot());
    }
}
~~~

**Vì sao dùng `SpringApplication` với một `@Configuration` rõ ràng?** Đây là cấu hình lab tối giản, không cần `@SpringBootApplication` scan cả project. Spring Boot vẫn bootstraps context và lifecycle như application bình thường; không có web server để giữ process sống sau khi main trả về.

`try-with-resources` gọi `context.close()` khi rời block. Biến `timeline` được giữ tham chiếu bên ngoài để đọc lại các mốc **sau khi context đã đóng**; trong production không nên tiếp tục gọi bean method sau close, nhưng ở đây đó là một object recorder đơn giản, không giữ external resource và chỉ phục vụ test.

### Build và chạy

Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q test
mvn -q -DskipTests package
java -jar target/lifecycle-close-lab-0.0.1-SNAPSHOT.jar
~~~

Các dòng **do chương trình chủ động in** theo thứ tự mong đợi:

~~~text
ACTIVE_BEFORE_CLOSE=true
HIGH_RUNNING=true
EVENTS=[start:low, start:high, event:close, stop:high, stop:low, predestroy:resource, close:resource]
~~~

Tùy logging config, còn có dòng log framework. Đừng so nguyên stdout nếu log level khác nhau. Dòng `EVENTS` là dữ liệu của recorder do code thiết kế; Spring container chỉ thêm điều phối để gọi các lifecycle methods.

### Diễn giải output

1. `start:low` trước `start:high`: start theo phase tăng dần.
2. `event:close`: listener đã nhận `ContextClosedEvent`.
3. `stop:high` trước `stop:low`: stop theo phase giảm dần.
4. `predestroy:resource`: `@PreDestroy` được gọi.
5. `close:resource`: custom destroy method được gọi sau `@PreDestroy` trên cùng bean.
6. Output không cho biết riêng một HTTP request đã drain hoặc dữ liệu database đã commit: lab không sử dụng các tài nguyên ấy.

## 7. JUnit 5: kiểm thử close, phase và gọi callback đúng một lần

File **`src/test/java/com/example/lifecycle/LifecycleCloseTest.java`**:

~~~java
package com.example.lifecycle;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class LifecycleCloseTest {

    @Test
    void closeStopsByDescendingPhaseThenDestroysResource() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LifecycleFixtures.Config.class)) {

            LifecycleFixtures.Timeline timeline =
                    context.getBean(
                            LifecycleFixtures.Timeline.class);

            LifecycleFixtures.ResourceProbe resource =
                    context.getBean(
                            LifecycleFixtures.ResourceProbe.class);

            LifecycleFixtures.PhaseProbe low =
                    context.getBean(
                            "low",
                            LifecycleFixtures.PhaseProbe.class);

            LifecycleFixtures.PhaseProbe high =
                    context.getBean(
                            "high",
                            LifecycleFixtures.PhaseProbe.class);

            assertThat(context.isActive()).isTrue();
            assertThat(low.isRunning()).isTrue();
            assertThat(high.isRunning()).isTrue();

            assertThat(timeline.snapshot())
                    .containsSubsequence(
                            "start:low", "start:high");

            context.close();

            assertThat(context.isActive()).isFalse();
            assertThat(low.isRunning()).isFalse();
            assertThat(high.isRunning()).isFalse();

            List<String> afterClose = timeline.snapshot();

            assertThat(afterClose).containsSubsequence(
                    "event:close",
                    "stop:high",
                    "stop:low",
                    "predestroy:resource",
                    "close:resource");

            assertThat(resource.getPreDestroyCount())
                    .isEqualTo(1);
            assertThat(resource.getCloseCount())
                    .isEqualTo(1);

            // AbstractApplicationContext.close()
            // không chạy lại toàn bộ destroy nhiều lần.
            context.close();

            assertThat(timeline.snapshot())
                    .containsExactlyElementsOf(afterClose);
            assertThat(resource.getPreDestroyCount())
                    .isEqualTo(1);
            assertThat(resource.getCloseCount())
                    .isEqualTo(1);
        }
    }

    @Test
    void stopIsNotTheSameAsClose() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        LifecycleFixtures.Config.class)) {

            LifecycleFixtures.ResourceProbe resource =
                    context.getBean(
                            LifecycleFixtures.ResourceProbe.class);

            LifecycleFixtures.PhaseProbe high =
                    context.getBean(
                            "high",
                            LifecycleFixtures.PhaseProbe.class);

            context.stop();

            // stop() gửi stop signal cho Lifecycle;
            // context vẫn active và chưa destroy bean.
            assertThat(context.isActive()).isTrue();
            assertThat(high.isRunning()).isFalse();
            assertThat(resource.getPreDestroyCount())
                    .isZero();
            assertThat(resource.getCloseCount())
                    .isZero();

            context.start();
            assertThat(high.isRunning()).isTrue();

            // AutoCloseable ở try sẽ close context khi ra scope.
        }
    }
}
~~~

### Các assertion thật sự kiểm tra điều gì?

- `containsSubsequence` kiểm tra **thứ tự tương đối** giữa các mốc cần quan tâm, không buộc mọi framework log phải giống nhau.
- `context.isActive()` trước/sau close xác nhận trạng thái context.
- `isRunning()` chứng minh cả hai lifecycle probes đã stop.
- Counter chứng minh callback giải phóng **một lần** trong đường đóng bình thường.
- Gọi `close()` hai lần xác nhận tính **idempotent của `AbstractApplicationContext.close()` trong lab**, không có nghĩa mọi resource API đều tự idempotent trong mọi tình huống.
- Test `stopIsNotTheSameAsClose` xác nhận resource chưa bị destroy khi chỉ gọi `context.stop()` và component có thể start lại.

**Đừng viết assertion “mọi bean destroy theo thứ tự đăng ký bean”**: thứ tự destroy giữa nhiều beans phụ thuộc dependency relationships và container implementation. Bài kiểm tra thứ tự rõ ràng của **một bean** và giữa **những phase đã chỉ định**.

## 8. JUnit 5: kiểm thử SmartLifecycle.stop(Runnable) bất đồng bộ

Một lỗi thực tế là `stop(Runnable callback)` phát tín hiệu ngừng rồi **quên callback**, khiến LifecycleProcessor phải đợi tới timeout. Để chứng minh callback có ý nghĩa, ta tạo component chỉ hoàn tất shutdown khi test cho phép; sau đó gọi `context.close()` ở một thread khác.

File **`src/test/java/com/example/lifecycle/AsyncStopTest.java`**:

~~~java
package com.example.lifecycle;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AsyncStopTest {

    static final class AsyncStopProbe implements SmartLifecycle {
        private final LifecycleFixtures.Timeline timeline;
        private final CountDownLatch stopEntered =
                new CountDownLatch(1);
        private final CountDownLatch allowStopToComplete =
                new CountDownLatch(1);
        private final AtomicBoolean running =
                new AtomicBoolean(false);

        AsyncStopProbe(LifecycleFixtures.Timeline timeline) {
            this.timeline = timeline;
        }

        @Override
        public void start() {
            running.set(true);
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
        public void stop() {
            running.set(false);
        }

        @Override
        public void stop(Runnable callback) {
            timeline.add("stop:requested");
            stopEntered.countDown();

            Thread thread = new Thread(() -> {
                try {
                    allowStopToComplete.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    running.set(false);
                    timeline.add("stop:completed");
                    callback.run();
                }
            }, "async-stop-lab");

            thread.setDaemon(true);
            thread.start();
        }

        boolean awaitStopStart(long timeout, TimeUnit unit)
                throws InterruptedException {
            return stopEntered.await(timeout, unit);
        }

        void releaseStop() {
            allowStopToComplete.countDown();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AsyncConfig {

        @Bean
        LifecycleFixtures.Timeline timeline() {
            return new LifecycleFixtures.Timeline();
        }

        @Bean
        AsyncStopProbe asyncStopProbe(
                LifecycleFixtures.Timeline timeline) {
            return new AsyncStopProbe(timeline);
        }

        @Bean(destroyMethod = "close")
        LifecycleFixtures.ResourceProbe resource(
                LifecycleFixtures.Timeline timeline) {
            return new LifecycleFixtures.ResourceProbe(timeline);
        }
    }

    @Test
    void closeWaitsForAsyncStopCallbackBeforeDestroy()
            throws Exception {

        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        AsyncConfig.class);

        AsyncStopProbe probe =
                context.getBean(AsyncStopProbe.class);

        LifecycleFixtures.Timeline timeline =
                context.getBean(LifecycleFixtures.Timeline.class);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        Future<?> closing = executor.submit(context::close);

        try {
            assertThat(probe.awaitStopStart(
                    5, TimeUnit.SECONDS)).isTrue();

            // Stop đã bắt đầu nhưng test chưa cho phép hoàn tất.
            assertThat(closing.isDone()).isFalse();

            probe.releaseStop();
            closing.get(10, TimeUnit.SECONDS);

            List<String> events = timeline.snapshot();

            assertThat(events).containsSubsequence(
                    "stop:requested",
                    "stop:completed",
                    "predestroy:resource",
                    "close:resource");

            assertThat(context.isActive()).isFalse();
        } finally {
            // Tránh worker dừng mãi khi assertion thất bại.
            probe.releaseStop();
            executor.shutdownNow();
        }
    }
}
~~~

### Vì sao test này ít phụ thuộc timing?

- `CountDownLatch stopEntered` đồng bộ để test không đoán xem close thread đã tới `stop(Runnable)` hay chưa.
- `allowStopToComplete` giúp giữ đường stop chưa hoàn tất khi kiểm tra `closing.isDone() == false`.
- `callback.run()` chỉ được gọi trong `finally` sau khi worker đã ghi `stop:completed`.
- `closing.get(10, SECONDS)` bảo đảm test có thời gian chờ **hữu hạn**.
- `Timeline` thread-safe nên có thể đọc events từ test thread.
- `releaseStop()` trong `finally` để tránh worker giữ trạng thái chờ vô hạn nếu assertion fail.

### Các giới hạn cần nêu rõ

- `Future.get(10, ...)` là deadline của **test**; `DefaultLifecycleProcessor` cũng có timeout **per-phase** riêng. Nếu cố tình không gọi callback, có thể thấy test failure/phase timeout thay vì treo vĩnh viễn.
- Component minh họa tạo raw thread daemon vì chỉ phục vụ test. Production nên quản lý worker/drain threads có timeout, interruption, metrics và executor lifecycle riêng.
- Nếu worker đã hết deadline và vẫn giữ external resources, việc gọi callback trong `finally` nghĩa là **đã hoàn thành chính sách dừng hoặc hủy**, không chứng minh mọi nghiệp vụ đã commit.
- Nếu test dùng context có thêm lifecycle beans khác, callback và phase phải được xét theo toàn bộ dependency/phase graph.
- Test cần không có external I/O dài; với CI cực chậm, 5 và 10 giây cần được điều chỉnh theo chính sách test nhưng vẫn giữ timeout hữu hạn.

## 9. Khi nào kiểm thử bằng AnnotationConfigApplicationContext, khi nào dùng SpringApplication?

| Cách kiểm thử | Nên dùng khi | Không bao phủ tự động |
| --- | --- | --- |
| `new AnnotationConfigApplicationContext(Config.class)` | Kiểm tra contract của lifecycle beans và destroy callbacks nhanh, cô lập | Spring Boot auto-configuration, web server, external brokers |
| `new SpringApplication(Config.class).run(...)` | Cần xác nhận Boot context khởi chạy/dừng thật | OS signal, container PID 1, toàn bộ web traffic |
| `@SpringBootTest` | Kiểm thử integration với Boot wiring/properties | Callback destroy đúng trong cùng test method nếu context vẫn cached |
| `@DirtiesContext` | Cần yêu cầu TestContext bỏ cache và close sau test/class | Không phải công cụ assertion trực tiếp ngay sau khi đóng nếu callback chạy sau method |
| Subprocess Java với TERM | Cần xác nhận JVM hook, exit code, OS signal, container behavior | Không thay thế unit tests của cleanup method |

### Tại sao không tự close context được inject từ @SpringBootTest?

Spring TestContext **cache ApplicationContext** giữa các test có cùng cấu hình. Nếu một test gọi:

~~~java
@Autowired
ConfigurableApplicationContext context;

@Test
void stopIt() {
    context.close();
}
~~~

thì đây là **anti-pattern snippet** trong một bộ test dùng `@SpringBootTest` nếu test khác còn kỳ vọng context cached ấy hoạt động: test có thể khiến những method/test class khác dùng lại một context đã đóng, gây lỗi phụ và kết quả phụ thuộc thứ tự chạy.

Thay vì thế:
- Với **test cần quan sát close ngay trong method**, tự tạo `AnnotationConfigApplicationContext`/`SpringApplication` riêng như project này.
- Với **test integration muốn framework tự bỏ context khỏi cache**, dùng `@DirtiesContext` phù hợp với lifecycle mong muốn.
- Không đánh dấu mọi test là `@DirtiesContext` một cách máy móc: reload context rất tốn thời gian và có thể che các vấn đề state leakage.

Ví dụ sử dụng `@DirtiesContext` ở mức class:

~~~java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class IntegrationLifecycleTest {
    @Test
    void contextStarts() {
        // Test code có thể assert @Autowired beans đang chạy.
        // Context sẽ được TestContext đóng sau class.
    }
}
~~~

Đây là **snippet**, cần import `SpringBootTest`, `DirtiesContext` và `Test`, đồng thời project phải có một Spring Boot main configuration phù hợp. Nó minh họa chính sách test context, **không** là một file runnable độc lập trong lab tối giản ở phần 6 nếu không bổ sung cấu hình test Boot. Không dựa vào việc `@PreDestroy` đã chạy ngay trong body của `contextStarts()`.

## 10. Phân tích chính xác “stop callback” trong test

Một `SmartLifecycle` đúng phải trả lời được:

1. **Start khi nào?** `isAutoStartup() == true` thì Spring tự start khi context refresh, nếu bean được quản lý và auto startup phù hợp.
2. **Stop khi nào?** `context.stop()` hoặc `context.close()` kích hoạt lifecycle processor, khi component đang running.
3. **Đường callback nào?** `stop(Runnable callback)` do lifecycle processor dùng; không chỉ method `stop()` thông thường.
4. **Báo hoàn tất ra sao?** Gọi callback đúng sau khi dừng/cleanup đạt trạng thái đã cam kết.
5. **Gọi một hay nhiều lần?** Trong đường đóng context bình thường, nên tránh dừng/đóng resource lặp nếu chưa thiết kế idempotence.
6. **Nếu lỗi/timeout thì sao?** Lỗi phải được ghi nhận, deadline được áp dụng, resource owner quyết định retry/hủy/compensate.

### Tại sao callback nên có finally?

~~~java
@Override
public void stop(Runnable callback) {
    try {
        performStop();
    } finally {
        callback.run();
    }
}
~~~

Đây là pattern đồng bộ cơ bản. Nó tránh bỏ quên callback nếu `performStop()` ném exception, nhưng **không tự khiến exception biến mất** hoặc công việc hoàn tất. Cần log/propagate failure phù hợp. Nếu cleanup thất bại nặng, có thể phải báo trạng thái degraded/failure ra monitoring ngay cả khi callback vẫn được gọi để lifecycle processor đi tiếp.

### Khi nào callback không nên được gọi ngay?

Nếu `stop()` mới chỉ gửi `interrupt()` cho worker mà không đợi worker thoát, `callback.run()` ngay lúc đó khiến container tin rằng component đã dừng. Ví dụ:

~~~java
@Override
public void stop(Runnable callback) {
    worker.interrupt();
    callback.run(); // Có thể quá sớm nếu worker chưa kết thúc.
}
~~~

Snippet này có rủi ro nếu worker còn dùng DB/client mà Spring sắp destroy. Nên dùng `join(timeout)`, `Future.get(timeout)` hoặc await-termination có giới hạn trong một cơ chế stop phù hợp.

### Không gọi callback quá sớm hoặc hai lần

Nếu callback được gọi trước khi tài nguyên release, thứ tự dừng có thể sai. Nếu gọi nhiều lần, implementation của lifecycle processor có thể có logic xử lý callback khác nhau; không nên dựa vào việc framework bỏ qua callback trùng. Dùng `AtomicBoolean` hoặc quản lý trạng thái nếu có nhiều nhánh async completion/cancellation.

## 11. Kiểm thử tài nguyên thật: executor, file, socket, database

### 11.1. ExecutorService

Một `ExecutorService` tự tạo có thể giữ **non-daemon threads** còn sống sau context close nếu không shutdown. Test tối thiểu nên xác nhận:

- không nhận task mới sau khi bắt đầu close;
- các task đang chạy được chờ hoặc hủy theo deadline;
- `executor.isShutdown()` hoặc `executor.isTerminated()` đạt trạng thái đúng;
- không còn worker thread thuộc resource owner sau thời hạn;
- `@PreDestroy` không đóng connection khi worker vẫn đang dùng nếu ứng dụng yêu cầu drain trước.

Snippet quản lý executor:

~~~java
@PreDestroy
public void destroy() throws InterruptedException {
    executor.shutdown();

    if (!executor.awaitTermination(
            5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
}
~~~

Đây là **snippet**, cần biến `executor` kiểu `ExecutorService`, import `TimeUnit` và đúng cơ chế xử lý interruption. `shutdownNow()` **chỉ cố gửi interrupt**; nó không bảo đảm mọi task dừng ngay nếu ignore interrupt hoặc block I/O không timeout.

Trong Spring Boot có thể dùng auto-configured executors với chính sách chờ termination, nhưng không nhầm chúng với mọi raw thread pool:
 
~~~properties
spring.task.execution.shutdown.await-termination=true
spring.task.execution.shutdown.await-termination-period=10s
~~~

Các property này chỉ tác động tới executor infrastructure phù hợp mà Boot quản lý. Nếu ứng dụng tự gọi `Executors.newFixedThreadPool(...)` bên ngoài container, phải quản lý lifecycle của chính pool ấy.

### 11.2. File resource

Với file stream, test có thể:
- tạo temp file qua `@TempDir`;
- bean mở resource;
- close context;
- assert stream không còn cho phép write/read;
- assert dữ liệu cần flush đã tồn tại theo contract.

Không xem việc file đã bị đóng là bằng chứng toàn bộ dữ liệu durable đã `fsync` trên storage; đó là mức cam kết khác.

### 11.3. Socket / HTTP client

Test close của HTTP client nên xác minh:
- connection pool/resource manager đã đóng;
- request mới bị từ chối sau close;
- in-flight request được xử lý theo policy;
- không để network I/O dài vô hạn trong `@PreDestroy`.

Không test bằng một endpoint Internet không ổn định. Ưu tiên local test server hoặc mock transport và timeout ngắn.

### 11.4. Database transaction

Đối với database:
- dừng consumer/worker đang dùng datasource trước khi datasource destroy;
- kiểm tra rollback/commit và connection release;
- nếu cần dùng Testcontainers, ghi rõ môi trường Docker, wait strategy và cleanup;
- đừng suy DB commit chỉ từ việc `close()` của connection pool được gọi.

### 11.5. Message broker

Một consumer thường cần:
1. ngừng nhận message mới;
2. cho in-flight handlers hoàn tất hoặc đánh dấu retry;
3. commit/ack đúng ngữ nghĩa broker;
4. đóng consumer và client;
5. xác minh không mất/nhân đôi tác vụ ngoài chính sách at-least-once.

Đây là test integration của messaging, **không phải** một assertion `@PreDestroy` đơn lẻ.

## 12. Kiểm thử shutdown khác startup failure

Không phải mọi lỗi khởi tạo đều đi qua `ContextClosedEvent` và `SmartLifecycle.stop(Runnable)` bình thường. Nếu một bean ném exception trong `@PostConstruct` khi context chưa refresh thành công, Spring có thể hủy những singleton beans đã tạo, nhưng không được giả định toàn bộ lifecycle components đều đã start hoặc một `ContextClosedEvent` thường lệ luôn phát ra.

Vì vậy nên tách ba nhóm test:

| Nhóm | Hành động | Assertions |
| --- | --- | --- |
| Normal close | Refresh thành công rồi `close()` | event, stop phase, destroy callbacks |
| Partial startup failure | Một bean cố tình ném exception khi init | resources đã khởi tạo được cleanup theo contract, không hứa mọi stop callback |
| Forced process termination | Subprocess bị `SIGKILL`/OOMKill | recovery/idempotence, không kỳ vọng JVM hooks |

### Test startup failure có thể dùng assertThatThrownBy

~~~java
assertThatThrownBy(() -> {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(
                    BrokenStartupConfig.class)) {
        // Không tới đây nếu refresh thất bại.
    }
}).hasRootCauseInstanceOf(IllegalArgumentException.class);
~~~

Đây là **snippet**, cần `BrokenStartupConfig` được định nghĩa để ném một `IllegalArgumentException` ở bean init và static import `assertThatThrownBy`. Nó là một pattern cho test lỗi startup, **không phải** test close context bình thường. Khi kiểm tra resource cleanup của partial startup, cần quan sát các resource đã tạo trước lỗi bằng recorder riêng nằm ngoài context thất bại.

### Shutdown hook không chạy vì SIGKILL

Không viết một test JUnit trong cùng JVM gọi `Runtime.getRuntime().halt(...)` chỉ để “kiểm chứng” callback: nó sẽ giết test process và bỏ qua cleanup. Nếu cần test behavior với `SIGTERM`/`SIGKILL`, chạy app như subprocess và theo dõi process từ một harness khác. Dùng deadline, cleanup và environment cách ly, không thực hiện trên production.

## 13. Debug khi một phép test lifecycle thất bại

### Test không thấy ContextClosedEvent

Kiểm tra:
- listener có được Spring đăng ký và bean đã tạo không;
- test có gọi `close()` trên **đúng context instance** không;
- test đang dùng `@SpringBootTest` cached context và chưa được đóng không;
- lỗi startup có xảy ra trước khi event listener sẵn sàng không;
- log có bị lọc không, hay recorder bị reset/GC?

Không vội kết luận `@EventListener` lỗi nếu test chưa hề đóng context.

### Test thấy stop() nhưng không thấy stop(Runnable)

Kiểm tra thành phần có implement `SmartLifecycle` thật không, nó có `isRunning() == true` lúc stop không, và test có gọi `probe.stop()` **trực tiếp** thay vì `context.close()`/`context.stop()` hay không.

Khi ứng dụng trực tiếp gọi `probe.stop()`, đó không phải đường đi qua LifecycleProcessor; có thể khác với contract đóng context.

### Test stop() rồi resource đã destroy

Nếu test dùng `context.close()` thay vì `context.stop()` thì destroy là đúng. `context.stop()` tự nó không đồng nghĩa context destroy. Kiểm tra chính xác API được gọi.

### Callback không được gọi: test chờ đến timeout

Nhìn method `stop(Runnable)` và xác minh mọi nhánh success/error/cancel đều gọi callback. Kiểm tra executor drain có còn nhận task khi shutdown không, có deadlock do worker chờ resource đã đóng không, và deadline theo phase có quá ngắn không.

### Test pass tại máy dev nhưng flake trong CI

Những nguồn flakiness điển hình:
- `Thread.sleep(100)` dùng thay điều kiện đồng bộ;
- assertions chạy trước khi worker có cơ hội thực thi;
- JUnit methods chạy song song nhưng chia sẻ static recorder;
- port hoặc database container chưa ready;
- test dựa vào thời gian tuyệt đối 10 ms;
- Spring context cache bị một test khác đóng;
- shutdown hook chạy sau khi Surefire đã báo test xong.

Hãy dùng `CountDownLatch`, `Future.get(timeout)`, `awaitTermination` và mỗi test tự tạo context. Khi dùng Awaitility, chỉ dùng cho điều kiện eventual có nguyên nhân thật, không thay thế toàn bộ thiết kế đồng bộ.

### Test dừng sai thứ tự

Kiểm tra:
1. `getPhase()` của từng component;
2. quan hệ bean dependency và `depends-on`;
3. phần nào đang sử dụng executor/datasource;
4. một stop có gọi callback **trước** khi worker thực sự dừng không;
5. có nhiều component cùng phase chạy/stop tương đối đồng thời không.

Với components cùng phase, tránh assert thứ tự tuyệt đối nếu không có dependency rõ ràng; lifecycle processor có thể cho phép stop bất đồng bộ và callbacks hoàn tất khác thứ tự bắt đầu.

## 14. Dữ liệu từ test và phạm vi đảm bảo

Các mốc trong timeline rất hữu ích nhưng có giới hạn:

| Quan sát | Điều khẳng định được | Điều chưa chứng minh |
| --- | --- | --- |
| `event:close` | Listener được gọi khi context bắt đầu đóng | Tất cả resources đã đóng |
| `stop:high` trước `stop:low` | Test phase order cho hai probe này | Tất cả beans khác có thứ tự tương tự |
| `stop:completed` trước `predestroy:resource` | LifecycleProcessor đợi callback trong test | Mọi transaction đã commit |
| `predestroy:resource` | `@PreDestroy` được gọi trên managed bean | Nội dung bên ngoài được flush thành công |
| `close:resource` | Custom destroy method được gọi | Resource implementation không có bug nội bộ |
| `context.isActive() == false` | Context đã inactive | JVM không còn non-daemon thread |
| Process exit code `0` | OS thấy process kết thúc thành công theo code | Không có dữ liệu cần retry |
| Không có Java exception | Test path chạy không throw trong quan sát | Hệ thống đúng dưới mọi mức tải |

Để bảo vệ dữ liệu production, phải thêm test I/O integration, retry/idempotency, timeout và kiểm soát failure. Không nên viết test giả “close đã giải phóng mọi thứ” chỉ vì một method void được gọi.

## 15. Một số anti-pattern dễ gây false confidence

**Anti-pattern 1 — Chỉ assert context.close không ném lỗi.**  
Mục đích của bài là kiểm tra callbacks/worker state/resource counters. Một close trả về sau phase timeout vẫn có thể bỏ lại tác vụ chưa dừng.

**Anti-pattern 2 — Ngủ cố định để đợi async stop.**  
`Thread.sleep(1000)` dễ flaky; thay bằng latch và future có timeout.

**Anti-pattern 3 — Quên callback.run().**  
Container có thể chờ tới timeout phase, che lỗi dừng tài nguyên và làm deploy shutdown chậm.

**Anti-pattern 4 — Gọi callback trước khi task drain xong.**  
Container tiến tới destroy dependencies quá sớm, gây lỗi “connection closed” trong worker còn chạy.

**Anti-pattern 5 — Test bằng @SpringBootTest rồi tự đóng context cached.**  
Test khác có thể sử dụng context đã đóng; dùng context riêng hoặc `@DirtiesContext` phù hợp.

**Anti-pattern 6 — Gắn @PreDestroy vào object tự new nhưng không đăng ký với Spring.**  
Không có container-managed destruction cho object đó.

**Anti-pattern 7 — Không phân biệt ContextClosedEvent với @PreDestroy.**  
Event báo **bắt đầu** đóng, @PreDestroy diễn ra trong pha destroy; logging event không đủ làm bằng chứng cleanup.

**Anti-pattern 8 — Kiểm thử SIGKILL trong cùng JVM JUnit.**  
Nó kill runner, không kiểm thử được assertion. Dùng subprocess với watchdog ở môi trường an toàn.

**Anti-pattern 9 — Ép mọi bean phase về MAX_VALUE.**  
Thứ tự phải căn cứ dependencies và việc dừng intake trước khi release resources; phase không phải thứ tự tổng quát cho mọi mã.

**Anti-pattern 10 — Đóng executor quá sớm.**  
Worker có thể đang cần executor để thực hiện cleanup, khiến submit bị reject hoặc completion callback không chạy.

**Anti-pattern 11 — Giả định executor.shutdownNow() cưỡng bức kết thúc task.**  
Nó thường chỉ cố interrupt; task không hợp tác có thể còn chạy.

**Anti-pattern 12 — Assert toàn bộ log stdout bằng chuỗi cứng.**  
Framework startup logs phụ thuộc version và environment. Dùng recorder riêng, đối chiếu các mốc cần thiết.

## 16. Mở rộng cho web application và Kubernetes

Khi ứng dụng là HTTP service, thêm một lớp kiểm thử:

- chạy `@SpringBootTest(webEnvironment=RANDOM_PORT)` hoặc subprocess với cổng ngẫu nhiên;
- gửi request có barrier/latch để xác nhận request thực sự bắt đầu;
- kích hoạt context.close hoặc gửi `SIGTERM` từ harness ngoài process;
- đo request đang chạy có cơ hội hoàn tất theo `server.shutdown=graceful` hay không;
- kiểm tra new traffic bị từ chối trong giai đoạn drain;
- đảm bảo background consumers/task executors stop đúng và resource callbacks thực thi;
- so tổng thời gian TERM→process exit với `terminationGracePeriodSeconds`.

Trong Spring Boot 3.5, graceful shutdown được bật mặc định cho Tomcat, Jetty, Reactor Netty và Undertow, với behavior từ chối request mới tùy server. Nó thực hiện trong **early phase** của `SmartLifecycle`; có thể đặt:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

**Không nhầm** HTTP graceful shutdown với việc mọi message consumer/worker tùy biến được drain. Test HTTP in-flight và test `SmartLifecycle` nên độc lập trước, sau đó có integration test gộp để xác nhận stop order cùng dependencies.

### Kubernetes termination

Kubernetes có `terminationGracePeriodSeconds` riêng. Nếu Java cần 20 giây drain nhưng Pod bị kill sau 10 giây, callback không được bảo đảm kết thúc. `preStop` cũng tiêu tốn một phần ngân sách termination. Bài test unit cho `@PreDestroy` không thay thế kịch bản cluster rollout với TERM, endpoint draining và SIGKILL.

### Nguyên tắc đối với process lifecycle

`ApplicationContext.close()` là một API trong **process hiện tại**. Nếu code tự giữ non-daemon thread sống sau close, `main` có thể return nhưng process vẫn tồn tại. Muốn kiểm chứng JVM thật sự thoát, dùng harness chạy child process với timeout và quan sát exit code/PID; không suy từ `context.isActive()`.

## 17. Checklist cho người viết test

- [ ] Xác định test **stop**, **close**, **startup failure** hay **process termination**.
- [ ] Dùng context riêng cho test cần chủ động close.
- [ ] Đăng ký một recorder thread-safe và giữ reference sau close khi cần assert.
- [ ] Có bean lifecycle running trước khi test stop.
- [ ] Chỉ định phase rõ ràng cho những component cần so thứ tự.
- [ ] Assert start theo phase tăng và stop theo phase giảm.
- [ ] Assert `ContextClosedEvent` xảy ra trước destroy trong normal close.
- [ ] Assert `SmartLifecycle.stop(Runnable)` đã gọi completion callback khi dừng xong.
- [ ] Với stop async, dùng latch/future và timeout hữu hạn, không dựa vào sleep.
- [ ] Assert `@PreDestroy` và custom destroy callback đúng một lần.
- [ ] Chỉ assert thứ tự callback **trong cùng một bean** hoặc khi dependency/phase bảo đảm.
- [ ] Assert `context.stop()` không đồng nghĩa resource destruction.
- [ ] Assert `context.isActive()` chuyển sang false sau close.
- [ ] Nếu test lặp close, xác định rõ contract idempotence của context/resource.
- [ ] Không tự đóng cached `@SpringBootTest` context một cách tùy tiện.
- [ ] Không gọi `System.exit`/`Runtime.halt` ngay trong JUnit runner.
- [ ] Test resource thật (executor, file, DB, broker) ở mức integration thích hợp.
- [ ] Giữ deadline đóng rõ ràng, tránh test treo vô hạn.
- [ ] Kiểm tra logging/exception paths và partial startup failure riêng.
- [ ] Khi thử Docker/Kubernetes, kiểm tra PID 1, SIGTERM và termination grace.
- [ ] Không dùng kết quả mock resource để khẳng định transaction commit.

## 18. Câu hỏi tự kiểm tra

**1. `context.stop()` khác `context.close()` như thế nào?**  
Stop thông báo các `Lifecycle` beans dừng, context thường vẫn active và chưa destroy singleton beans; close bắt đầu chuỗi shutdown/destroy.

**2. Khi context đóng bình thường, event nào báo bắt đầu đóng?**  
`ContextClosedEvent`.

**3. `SmartLifecycle.isAutoStartup()` mặc định ở Spring Framework 6.2 là gì?**  
`true`.

**4. Default phase của `SmartLifecycle` có phải `0` không?**  
Không; `SmartLifecycle.DEFAULT_PHASE` là `Integer.MAX_VALUE` trong Spring Framework 6.2. `Lifecycle` thông thường thường được xem có phase `0`.

**5. Hai phase `-100` và `100` start/stop theo thứ tự nào?**  
Start: -100 rồi 100; stop: 100 rồi -100, nếu không có dependency đặc biệt làm thay đổi.

**6. Ai gọi `stop(Runnable)` trong shutdown?**  
Spring `LifecycleProcessor` khi quản lý `SmartLifecycle` và điều phối dừng.

**7. Khi nào gọi callback.run()?**  
Khi component đã hoàn tất bước dừng theo contract và có thể cho lifecycle processor tiếp tục.

**8. Quên callback gây điều gì?**  
Phase có thể chờ tới timeout, làm shutdown chậm và che trạng thái worker còn sống.

**9. Vì sao dùng CountDownLatch trong async test?**  
Để đồng bộ test với stop callback theo điều kiện thật, tránh flakiness do sleep/timing.

**10. `@PreDestroy` áp dụng cho object tạo bằng new ngoài Spring không?**  
Không tự động; object phải được container quản lý hoặc có owner tự gọi cleanup.

**11. Khi cùng một bean có @PreDestroy và custom destroyMethod, thứ tự nào?**  
`@PreDestroy` trước custom destroy method, theo Spring bean destruction contract.

**12. Vì sao không nên tự close context autowired từ @SpringBootTest?**  
Nó có thể được cache và tái sử dụng giữa các tests, khiến test khác thấy context đã đóng.

**13. `@DirtiesContext` dùng làm gì?**  
Yêu cầu TestContext loại context khỏi cache và tái tạo cho các test sau, theo mode được chỉ định.

**14. Context inactive có đảm bảo JVM process đã thoát không?**  
Không. Một thread non-daemon ngoài context có thể tiếp tục chạy.

**15. SIGKILL có bảo đảm gọi @PreDestroy không?**  
Không; cần thiết kế recovery ngoài shutdown callbacks.

**16. Nếu stop async hoàn tất rồi callback nhưng DB chưa commit, test đã đủ chưa?**  
Chưa. Cần kiểm thử transaction/ack ở tầng integration nghiệp vụ.

**17. Việc gọi close() hai lần trong lab chứng minh gì?**  
Đường close của context không gọi lặp callbacks đã quan sát; không tự khẳng định mọi resource API trong hệ thống đều an toàn khi gọi hai lần.

**18. Khi startup chưa refresh thành công, có thể khẳng định mọi SmartLifecycle đã stop không?**  
Không. Chỉ những components đã tạo/start mới có thể tham gia stop; đường lỗi init không nhất thiết giống normal close.

## 19. Tài liệu chính thức

- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): lifecycle, destroy callbacks, stop phases, `@PreDestroy` và `SmartLifecycle`.
- [Spring Framework 6.2 — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/SmartLifecycle.html): `isAutoStartup`, `getPhase`, `stop(Runnable)` và default phase.
- [Spring Framework 6.2 — AnnotationConfigApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/annotation/AnnotationConfigApplicationContext.html): context test tự tạo.
- [Spring Framework — TestContext caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache lifecycle, eviction và `@DirtiesContext`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, webEnvironment và context reuse.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): JVM shutdown hook và đóng context.
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): web-server phase và timeout.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.lifecycle.timeout-per-shutdown-phase`.
- [Oracle Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `awaitTermination` và interruption.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle và assertions.
- [AssertJ Assertions](https://assertj.github.io/doc/): `containsSubsequence`, `containsExactlyElementsOf` và scalar assertions.

**Kết luận:** kiểm thử shutdown tốt phải chứng minh **context được đóng, lifecycle components được stop đúng thứ tự, callback async hoàn tất có giới hạn và resource được giải phóng đúng một lần**. Dùng context chủ động tạo trong JUnit để quan sát đường close mà không phá cache; sử dụng `CountDownLatch`/`Future` để đồng bộ async; giữ tách biệt stop, close, startup failure và process kill. Một test chỉ thấy `@PreDestroy` chạy chưa đủ để bảo đảm tài nguyên nghiệp vụ hoặc dữ liệu đã được xử lý an toàn.