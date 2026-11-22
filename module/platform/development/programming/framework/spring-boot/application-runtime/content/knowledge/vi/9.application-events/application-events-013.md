# ContextClosedEvent và phân biệt với các sự kiện khởi động trong Spring Boot

## 1. ContextClosedEvent là gì?

`ContextClosedEvent` là **sự kiện vòng đời của Spring Framework**, thuộc package `org.springframework.context.event`. Spring phát sự kiện khi một `ApplicationContext` đang hoạt động **bắt đầu được đóng**. Trong ứng dụng Spring Boot, quá trình này thường xuất hiện khi ứng dụng thoát bình thường, nhận tín hiệu dừng mà JVM xử lý được, hoặc khi chương trình gọi `ConfigurableApplicationContext.close()` một cách chủ động.

Điều quan trọng là chữ **Closed** trong tên sự kiện **không có nghĩa tất cả bean đã bị hủy trước khi listener được gọi**. Theo chuỗi đóng context của `AbstractApplicationContext`, sự kiện được công bố **trước** việc yêu cầu các `Lifecycle` bean dừng và trước việc hủy các singleton đang được quản lý. Vì vậy, đây là tín hiệu "context đang đóng", trong khi callback `@PreDestroy`, `DisposableBean.destroy()` hay `@Bean(destroyMethod = "...")` phục vụ dọn dẹp tài nguyên của từng bean ở bước sau.

Ví dụ ứng dụng đã phục vụ xong, cần dừng:

~~~text
Đang vận hành
   |
   +-- Có yêu cầu đóng ApplicationContext
   |      context.close() hoặc JVM shutdown hook
   |
   +-- Công bố ContextClosedEvent
   |      Listener quan sát việc context bắt đầu đóng
   |
   +-- Dừng các Lifecycle / SmartLifecycle bean theo cơ chế lifecycle
   |
   +-- Hủy các singleton trong BeanFactory
   |      @PreDestroy / DisposableBean / destroy method ...
   |
   +-- Đóng BeanFactory, hoàn tất các bước dọn dẹp context
   v
Context đã đóng, không còn dùng như một context đang hoạt động
~~~

Đó là thứ tự khái quát của một lần đóng context thông thường, **không phải thứ tự tuyệt đối giữa mọi listener, mọi bean hoặc luồng bất đồng bộ**. Các phiên bản Spring và các triển khai context có thể thêm bước riêng. Khi shutdown gặp lỗi, một số thao tác dọn dẹp có thể không hoàn thành; sự kiện cũng không được bảo đảm xuất hiện khi tiến trình bị kết thúc cưỡng bức.

### Ý nghĩa chính

- **Báo mốc đóng**: thông báo cho thành phần đang lắng nghe rằng context bắt đầu kết thúc vòng đời.
- **Cho phép phản ứng có phạm vi**: ghi log audit, đánh dấu trạng thái ngừng tiếp nhận công việc, phát tín hiệu quan sát hoặc thực hiện một thao tác ngắn trong lúc shutdown.
- **Gắn với một `ApplicationContext`**: `event.getApplicationContext()` cho biết context đã phát sự kiện. Trong hệ thống nhiều context, phải chú ý nguồn event.

Không dùng `ContextClosedEvent` như cách duy nhất giải phóng socket, thread pool, datasource hoặc connection của bean. Với resource do một bean sở hữu, nên ưu tiên cơ chế **lifecycle và destruction callback** của chính bean để tránh phụ thuộc quá mức vào event listener.

## 2. ContextClosedEvent phát ra vào lúc nào?

Theo Spring Framework, `ContextClosedEvent` được phát khi đóng `ConfigurableApplicationContext`, chẳng hạn:

1. **Đóng tường minh** bằng `context.close()`.
2. **JVM shutdown hook** do Spring Boot đăng ký trong ứng dụng thông thường, giúp đóng context khi JVM đi theo đường thoát có thể chạy hook.
3. **Cơ chế điều phối ứng dụng** dẫn đến đóng context (ví dụ logic kết thúc chương trình CLI hoặc quản lý vòng đời trong test), nếu thật sự gọi đóng context.

Ví dụ chủ động đóng một context đang chạy:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

// Sau khi hoàn tất công việc, yêu cầu đóng context.
context.close();
~~~

Đây là **đoạn minh họa trong `main()`**, không phải tệp độc lập; `MyApplication` và các import cần được khai báo trong một dự án Spring Boot. Đối với một web service cần phục vụ lâu dài, không gọi `close()` ngay sau `run()` trừ khi bạn thực sự muốn dừng service.

Spring Boot thông thường tự đăng ký JVM shutdown hook để gọi đóng context khi tiến trình kết thúc theo cách JVM hỗ trợ. Do đó trong ứng dụng web, bạn thường không cần tự thêm một shutdown hook nữa chỉ để đóng Spring context.

**Không thể bảo đảm event luôn được phát** trong các trường hợp:

- Tiến trình bị `SIGKILL`, `kill -9`, `Runtime.halt(...)`, sập JVM hoặc mất điện: JVM shutdown hook có thể không được thực thi.
- Startup thất bại khi context còn chưa được tạo hoặc chưa ở trạng thái active: có thể không có một context hợp lệ để công bố sự kiện.
- Ứng dụng chạy trong container/orchestrator nhưng bị dừng cưỡng bức trước khi đủ thời gian shutdown.
- Listener lỗi, bị cấu hình không được đăng ký hoặc xử lý bất đồng bộ không hoàn tất trước khi tiến trình dừng.

Vì vậy `ContextClosedEvent` hữu ích để **quan sát lifecycle**, nhưng không phải giao thức giao hàng chắc chắn cho một giao dịch quan trọng. Nếu phải ghi dữ liệu hoặc sự kiện nghiệp vụ có độ bền cao, dùng cơ chế lưu trữ/queue/transaction phù hợp trước khi shutdown xảy ra.

## 3. Phân biệt sự kiện Spring Framework với sự kiện Spring Boot

`ContextClosedEvent` thuộc **Spring Framework** và mô tả vòng đời `ApplicationContext`. Ngược lại, `ApplicationStartingEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent` và `ApplicationFailedEvent` là các sự kiện gắn với một lần chạy `SpringApplication` của **Spring Boot**.

| Sự kiện | Nơi khai báo | Thời điểm chính | Có ý nghĩa gì? |
| --- | --- | --- | --- |
| `ApplicationStartingEvent` | Spring Boot | Bắt đầu `SpringApplication.run`, trước khi có `Environment`/context đầy đủ | Chuỗi bootstrap đã bắt đầu |
| `ApplicationEnvironmentPreparedEvent` | Spring Boot | `Environment` đã được chuẩn bị, trước khi tạo context | Có thể quan sát cấu hình môi trường sớm |
| `ApplicationContextInitializedEvent` | Spring Boot | Context đã tạo và initializers đã được gọi, trước khi nạp bean definitions | Context được khởi tạo sơ bộ |
| `ApplicationPreparedEvent` | Spring Boot | Bean definitions đã nạp, trước refresh | Chuẩn bị refresh context |
| `ContextRefreshedEvent` | Spring Framework | Context được refresh thành công | Container đã hoàn tất refresh |
| `ApplicationStartedEvent` | Spring Boot | Sau refresh, trước `ApplicationRunner`/`CommandLineRunner` | Context đã hoạt động, runner chưa hoàn tất |
| `ApplicationReadyEvent` | Spring Boot | Sau khi các runner chạy thành công | Spring Boot hoàn tất startup theo lifecycle của nó |
| `ApplicationFailedEvent` | Spring Boot | Khi khởi động thất bại | Lần khởi động gặp lỗi |
| **`ContextClosedEvent`** | **Spring Framework** | **Khi context đang hoạt động bắt đầu đóng** | **Bắt đầu giai đoạn shutdown của context** |
| `ContextStoppedEvent` | Spring Framework | Khi gọi `ApplicationContext.stop()` | Các `Lifecycle` bean được yêu cầu dừng; context chưa nhất thiết bị hủy |

Hai điểm dễ nhầm nhất:

- **`ApplicationStartedEvent` không có nghĩa ứng dụng đã shutdown hoặc đã sẵn sàng nhận traffic**. Sự kiện này xảy ra trong startup, trước runners. `ApplicationReadyEvent` mới đánh dấu mốc startup thành công muộn hơn.
- **`ContextStoppedEvent` không đồng nghĩa `ContextClosedEvent`**. `stop()` thuộc cơ chế dừng vòng đời `Lifecycle`; một context đã stop vẫn có thể được `start()` lại trong mô hình hỗ trợ. `close()` là kết thúc vòng đời context; không thể đối xử với instance đã đóng như một context còn có thể refresh/chạy lại bình thường.

### Sơ đồ hai chặng: startup và shutdown

~~~text
JVM gọi main(...)
  |
  v
SpringApplication.run(...)
  |
  +-- ApplicationStartingEvent
  +-- ApplicationEnvironmentPreparedEvent
  +-- ApplicationContextInitializedEvent
  +-- ApplicationPreparedEvent
  |
  +-- ApplicationContext.refresh()
  |     +-- ContextRefreshedEvent
  |
  +-- ApplicationStartedEvent
  +-- Chạy ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
  v
Ứng dụng đang hoạt động
  |
  | Sau đó mới có yêu cầu dừng
  v
ConfigurableApplicationContext.close() / shutdown hook
  |
  +-- ContextClosedEvent
  +-- Dừng Lifecycle beans
  +-- Destruction callbacks của singleton
  +-- Hoàn tất đóng context
  v
Ứng dụng dừng

Đường khác: startup thất bại -> ApplicationFailedEvent
(có thể chưa có ContextClosedEvent, tùy giai đoạn lỗi).
~~~

Sơ đồ không hàm ý mọi ứng dụng luôn phát đủ các event: startup có thể thất bại, chương trình có thể có nhiều context, và việc bị tắt đột ngột có thể bỏ qua shutdown hook.

## 4. Nhận ContextClosedEvent bằng ApplicationListener hoặc @EventListener

Vì `ContextClosedEvent` được phát **sau khi một context đã được tạo và đang đóng**, listener có thể là một bean Spring bình thường. Điều này khác với `ApplicationStartingEvent` diễn ra quá sớm để một bean do component scan đăng ký nhận được.

### Cách 1 — @EventListener: đơn giản cho code ứng dụng

~~~java
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownObserver {

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("Closing: "
                + event.getApplicationContext().getId());
    }
}
~~~

Đây là một class Java hoàn chỉnh **trong dự án Spring có đủ dependency và phạm vi component scan**, nhưng không có `main()` nên không chạy riêng lẻ. Spring gọi method được đăng ký khi nhận event trong context phù hợp. `getId()` trả về ID của context, không tự chứng minh trạng thái tất cả bean.

Dùng `@EventListener` cho những phản ứng ngắn, không gây chặn shutdown lâu. Đừng giả định mọi singleton vẫn sẵn sàng nếu listener chạy song song hoặc có luồng khác đang shutdown.

### Cách 2 — ApplicationListener<ContextClosedEvent>

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextClosedEvent;

public final class ShutdownListener
        implements ApplicationListener<ContextClosedEvent> {

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        System.out.println("Context closing: "
                + event.getApplicationContext().getId());
    }
}
~~~

Đây là class Java hoàn chỉnh về cú pháp nhưng **phải được đăng ký** mới có tác dụng. Trong ứng dụng Spring Boot, có thể đăng ký như một bean bằng `@Component`, `@Bean` hoặc thêm qua API hỗ trợ của `SpringApplication` nếu cần listener độc lập với bean factory.

So sánh hai kiểu:

| Tiêu chí | `@EventListener` | `ApplicationListener` |
| --- | --- | --- |
| Hình thức | Method trên một bean Spring | Interface với `onApplicationEvent` |
| Phù hợp | Logic ngắn, đọc dễ, có dependency injection | Tích hợp/framework cần listener kiểu đối tượng |
| Thời điểm đăng ký | Khi bean và event listener adapter được xử lý trong refresh | Có thể sớm hơn nếu thêm trực tiếp vào `SpringApplication`; cũng có thể là bean |
| Nhận `ContextClosedEvent` | Có, nếu bean/listener đã được đăng ký | Có, nếu listener đã được đăng ký |
| Nhận `ApplicationStartingEvent` khi chỉ là bean | Không đáng tin: quá sớm | Chỉ khi đăng ký trước `run`, không phải bean tạo muộn |

**Lưu ý về việc dùng `@Async`:** nếu cấu hình listener chạy bất đồng bộ, đừng dựa vào việc tác vụ của listener phải hoàn tất trước khi `destroyBeans()` chạy. Bài này dùng listener đồng bộ mặc định khi giải thích thứ tự sự kiện và callback.

## 5. Ví dụ Java 17+: chứng minh Close event đến trước destroy callback

Ví dụ sau chạy trên **Spring Boot 3.5.16 + Java 17**. Nó tạo một ứng dụng không có web server (`WebApplicationType.NONE`), chạy một runner, công bố các event startup, rồi **chủ động gọi `context.close()`** để cho kết quả có thể quan sát trên mọi môi trường.

### 5.1. Cấu trúc dự án

~~~text
context-closed-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/closedevent/
                └── ClosedEventApplication.java
~~~

**Tệp `pom.xml`:**

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
    <artifactId>context-closed-demo</artifactId>
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

Dự án cần JDK 17+ và Maven 3.6.3+ (hoặc Maven Wrapper tương ứng). Phần code minh họa dùng API Spring Boot thông dụng, không yêu cầu database hay HTTP port.

**Tệp `src/main/java/com/example/closedevent/ClosedEventApplication.java`:**

~~~java
package com.example.closedevent;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class ClosedEventApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ClosedEventApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);

        System.out.println("05_MAIN_BEFORE_CLOSE");
        context.close(); // Yêu cầu đóng tường minh.
        System.out.println("08_MAIN_AFTER_CLOSE");
    }

    @Bean(destroyMethod = "release")
    TrackedResource trackedResource() {
        return new TrackedResource();
    }

    @Bean
    ApplicationRunner demoRunner(TrackedResource resource) {
        return args -> System.out.println(
                "03_RUNNER_VALUE=" + resource.value());
    }

    @Bean
    EventObserver eventObserver() {
        return new EventObserver();
    }

    static final class EventObserver {

        @EventListener
        public void onStarted(ApplicationStartedEvent event) {
            System.out.println("02_APPLICATION_STARTED");
        }

        @EventListener
        public void onReady(ApplicationReadyEvent event) {
            System.out.println("04_APPLICATION_READY");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            System.out.println("06_CONTEXT_CLOSED_EVENT");
        }
    }

    static final class TrackedResource {

        TrackedResource() {
            System.out.println("01_RESOURCE_CREATED");
        }

        String value() {
            return "ready";
        }

        public void release() {
            System.out.println("07_RESOURCE_DESTROY_METHOD");
        }
    }
}
~~~

Ví dụ chứa `main()` và các class phụ trong cùng một tệp Java; không cần tạo thêm file `EventObserver.java` hay `TrackedResource.java`. Spring quản lý `TrackedResource` như bean singleton thông thường nhờ phương thức `@Bean`. `EventObserver` cũng là bean, nên các method `@EventListener` được Spring đăng ký trong quá trình khởi tạo context.

`@Bean(destroyMethod = "release")` yêu cầu Spring gọi `TrackedResource.release()` khi hủy bean. Tên method tương ứng chính xác, có thể kiểm chứng trong code. Ví dụ này không dùng `@PreDestroy` để tránh in nhiều callback làm rối mục tiêu chính.

### 5.2. Chạy và đọc output

Tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Hoặc đóng gói thành executable JAR:

~~~bash
mvn package
java -jar target/context-closed-demo-0.0.1-SNAPSHOT.jar
~~~

Trong output (bỏ qua banner, log Spring Boot/Maven hoặc log thư viện xen kẽ), **những dòng do code ví dụ in ra** có thứ tự như sau:

~~~text
01_RESOURCE_CREATED
02_APPLICATION_STARTED
03_RUNNER_VALUE=ready
04_APPLICATION_READY
05_MAIN_BEFORE_CLOSE
06_CONTEXT_CLOSED_EVENT
07_RESOURCE_DESTROY_METHOD
08_MAIN_AFTER_CLOSE
~~~

Giải thích:

1. **`01_RESOURCE_CREATED`**: bean singleton được tạo trong giai đoạn refresh context.
2. **`02_APPLICATION_STARTED`**: context đã được refresh thành công, nhưng runner chưa được gọi.
3. **`03_RUNNER_VALUE=ready`**: `ApplicationRunner` chạy sau mốc started.
4. **`04_APPLICATION_READY`**: Boot phát ready event khi các runner thành công.
5. **`05_MAIN_BEFORE_CLOSE`**: `SpringApplication.run()` trả về context; phương thức `main()` chủ động chuẩn bị đóng.
6. **`06_CONTEXT_CLOSED_EVENT`**: sự kiện đóng context được phát và listener quan sát.
7. **`07_RESOURCE_DESTROY_METHOD`**: Spring gọi destroy method của singleton sau giai đoạn công bố close event.
8. **`08_MAIN_AFTER_CLOSE`**: `context.close()` trả về; code trong `main()` thực thi tiếp.

Đây là thứ tự **đối với chương trình minh họa và listener đồng bộ**, không phải bảo đảm mọi sản phẩm dùng Spring đều có cùng tám dòng hay cùng tên log. Trong ứng dụng production có web server, shutdown còn liên quan đến ngừng nhận request, drain kết nối, lifecycle bean và signal từ môi trường triển khai.

### 5.3. Thử nghiệm thêm

**Thử 1 — chuyển sang shutdown hook:** Bỏ hai dòng `context.close()` và `08_MAIN_AFTER_CLOSE`, đổi sang ứng dụng web có web server, sau đó kết thúc tiến trình bằng Ctrl+C. Nếu JVM cho shutdown hook chạy, Spring Boot sẽ đóng context và event listener có thể nhận `ContextClosedEvent`. Đây là bài thử cần chuẩn bị web starter/cấu hình và **không có output cố định giống ví dụ CLI**.

**Thử 2 — kiểm tra @PreDestroy:** Thay `@Bean(destroyMethod = "release")` bằng `@Bean`, rồi gắn `@PreDestroy` lên method `release()` (import `jakarta.annotation.PreDestroy`, dependency annotation có mặt trong cấu hình Boot 3.x phù hợp). Quan sát cleanup vẫn xảy ra khi Spring hủy bean. Đây là đoạn hướng dẫn sửa mã ví dụ, không phải một tệp độc lập.

**Thử 3 — phân biệt stop và close:** Trên `ConfigurableApplicationContext` còn sống, thử gọi `context.stop()`, rồi `context.start()` và cuối cùng `context.close()`. Theo dõi các event `ContextStoppedEvent`/`ContextStartedEvent` nếu có listener thích hợp, rồi so sánh với `ContextClosedEvent`. Không giả định `stop()` đã thực thi tất cả destruction callback.

**Thử 4 — startup failure:** Cố ý ném `IllegalStateException` từ `ApplicationRunner`, sau đó quan sát `ApplicationFailedEvent`. Nếu `run()` ném exception, chương trình sẽ không chạy đến dòng `05_MAIN_BEFORE_CLOSE` trong ví dụ này. Không suy ra `ContextClosedEvent` chắc chắn cũng phải được phát trong mọi trường hợp lỗi.

## 6. ContextClosedEvent so với @PreDestroy, DisposableBean và SmartLifecycle

Khi thiết kế shutdown, hãy chọn **đúng cơ chế theo trách nhiệm**:

| Cơ chế | Được gọi ở đâu? | Trách nhiệm phù hợp |
| --- | --- | --- |
| `@EventListener(ContextClosedEvent.class)` | Listener của một sự kiện context-level | Quan sát và phản ứng ngắn khi context bắt đầu đóng |
| `ApplicationListener<ContextClosedEvent>` | Listener đối tượng của sự kiện context-level | Tích hợp hạ tầng/framework |
| `@PreDestroy` | Callback trên bean đang bị hủy | Giải phóng resource do bean sở hữu |
| `DisposableBean.destroy()` | Callback hủy bean theo interface Spring | Logic dọn dẹp một bean cần hợp đồng Spring |
| `@Bean(destroyMethod = "...")` | Destroy method được khai báo trong cấu hình bean | Dọn dẹp bean bằng method riêng không cần interface Spring |
| `SmartLifecycle.stop(Runnable callback)` | Trong quá trình lifecycle processor dừng bean | Dừng consumer, worker, luồng xử lý có phối hợp thời gian |
| `ContextStoppedEvent` | Khi `stop()` được gọi với context hỗ trợ | Báo trạng thái stop của lifecycle, không thay cho close |

Sự khác biệt quan trọng nhất là **close event được công bố trước khi bean singleton bị hủy**, còn `@PreDestroy`/destroy method thuộc chính quá trình hủy bean đó. Vì vậy nếu một service sở hữu thread pool hoặc connection pool, chính service nên đóng resource trong callback hủy hoặc lifecycle thích hợp; listener chỉ nên phát tín hiệu phối hợp ngắn khi context sắp kết thúc.

### Ví dụ dọn resource phù hợp

~~~java
@Component
public class CacheWorker {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    @PreDestroy
    public void shutdown() {
        executor.shutdown();
    }
}
~~~

Đây là **đoạn minh họa trong ứng dụng**, chưa độc lập: cần import `org.springframework.stereotype.Component`, `jakarta.annotation.PreDestroy`, `java.util.concurrent.ExecutorService` và `java.util.concurrent.Executors`. Trong production, nếu cần đợi task hoàn thành, dùng chính sách `awaitTermination`, timeout, xử lý interruption và fallback phù hợp; một lệnh `shutdown()` đơn lẻ chỉ ngừng nhận nhiệm vụ mới.

Đừng gọi trực tiếp `ApplicationContext.close()` từ `@PreDestroy` hoặc `ContextClosedEvent` của chính context chỉ vì muốn "chắc chắn đã dừng": context đang đi qua luồng close, việc đệ quy đóng hoặc khởi tạo bean mới trong lúc teardown thường không có lợi.

## 7. Các giới hạn thực tế của ContextClosedEvent

### 7.1. Không đồng nghĩa với đã shutdown xong

Vì listener chạy khi event được phát, các resource khác có thể vẫn chưa được hủy. Do đó không viết log như "all resources destroyed" ngay tại `ContextClosedEvent`. Nếu cần xác minh một resource đã đóng, kiểm tra callback hủy của chính resource hoặc một điều kiện bên ngoài hệ thống.

Không nên tạo bean mới từ `ApplicationContext.getBean()` trong listener đóng. Trong giai đoạn shutdown, bean factory có thể đang ngừng cho phép tạo singleton mới, và các thành phần được yêu cầu dừng. Hãy sử dụng dependency đã được inject từ trước nếu thật cần, tránh sinh work mới.

### 7.2. Không đồng nghĩa với sự kiện đầu tiên của startup

Trong Spring Boot, `ApplicationStartingEvent` xuất hiện trước khi tạo `Environment` và `ApplicationContext`; để bắt nó phải đăng ký listener trước `run()`. `ContextClosedEvent` thì ngược lại: một bean `@EventListener` thông thường có thể nhận được vì context đã từng được khởi tạo.

Điều đó cũng giải thích vì sao cùng một lớp `@Component` có thể nhận `ApplicationReadyEvent` và `ContextClosedEvent` nhưng bỏ lỡ `ApplicationStartingEvent`. Đừng nhầm "không thấy event" với "event không được phát"; đôi khi listener được đăng ký quá muộn.

### 7.3. Không đồng nghĩa với ApplicationFailedEvent

`ApplicationFailedEvent` của Spring Boot liên quan đến **thất bại khi khởi động**. Nếu một lỗi xảy ra rất sớm, có thể chưa có `ApplicationContext` để đóng. Nếu lỗi xảy ra sau khi context đã tạo một số bean, framework có thể dọn dẹp các bean tạo được, nhưng không thể kết luận `ContextClosedEvent` luôn được phát như trong đường close bình thường.

Do đó không thiết kế logic "startup fail thì chắc chắn ContextClosedEvent sẽ xử lý" mà không có kiểm chứng lifecycle cụ thể. Chọn cơ chế xử lý lỗi startup/cleanup có bảo đảm rõ ràng.

### 7.4. Context hierarchy và sự kiện từ context con

Một ứng dụng phức tạp có thể có **parent context và child context**. Sự kiện phát trong context con có thể được truyền lên các context tổ tiên. Khi đó listener ở context cha có thể nhận `ContextClosedEvent` của context con; đừng mặc định mọi event nhận được đều nói rằng **chính context đang giữ listener** đã đóng.

Nếu muốn lọc đúng context, so sánh reference:

~~~java
@EventListener
public void onClosed(ContextClosedEvent event) {
    if (event.getApplicationContext() != this.applicationContext) {
        return;
    }
    // Phản ứng chỉ với context mà bean này thuộc về.
}
~~~

Đây là **đoạn minh họa, không độc lập**: `applicationContext` phải là dependency được inject hoặc lấy qua `ApplicationContextAware` trước khi shutdown. Không làm thay đổi context trong callback chỉ để lọc sự kiện.

### 7.5. Listener mặc định đồng bộ, nhưng không nên block lâu

Theo mặc định event listener của Spring thực thi đồng bộ qua multicaster mặc định. Một listener chậm có thể kéo dài tiến trình đóng. Một listener ném exception cũng có thể được framework xử lý/log theo cơ chế đóng context, nhưng không được dựa vào exception từ event như một cách ngăn toàn bộ shutdown.

Tránh:
- Gọi HTTP hoặc database vô hạn timeout.
- Flush toàn bộ dữ liệu lớn ở phút cuối mà không có checkpoint trước đó.
- Bắt đầu thêm tác vụ nền mới khi hệ thống đang shutdown.
- Dựa vào một thread async để ghi dấu "đã đóng" rồi giả định nó kịp chạy.
- Chặn shutdown hook lâu hơn giới hạn termination grace period của hạ tầng.

Tốt hơn là dùng callback hủy resource có timeout rõ, hệ thống queue có ack, hoặc logic drain của service phù hợp.

## 8. Web server, graceful shutdown và readiness

Trong web service, sự kiện đóng context chỉ là **một phần** của quy trình shutdown. Hệ thống còn có:

1. Load balancer/orchestrator quyết định ngừng định tuyến request mới.
2. Máy chủ web ngừng nhận kết nối mới hoặc phối hợp graceful shutdown.
3. Các request đang xử lý được cho thời gian hoàn thành theo chính sách.
4. Bean lifecycle và resource được đóng.
5. Tiến trình JVM thoát.

Spring Boot hỗ trợ graceful shutdown cho một số web server tích hợp. Với Spring Boot 3.5, cấu hình mẫu:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Đây là **cấu hình tham khảo**, cần đánh giá web server đang dùng, phiên bản Spring Boot và giới hạn của nền tảng triển khai. Nó không thay cho readiness probe của Kubernetes hay cơ chế drain ở load balancer. Nếu container bị `SIGKILL` ngay lập tức thì không có cấu hình Spring nào bảo đảm toàn bộ công việc dọn dẹp sẽ hoàn tất.

Trong Kubernetes, readiness và liveness probe mang ý nghĩa vận hành khác với event:
- **Readiness**: cho biết instance có nên nhận traffic mới hay không.
- **Liveness**: cho biết tiến trình có đủ khỏe để tiếp tục chạy hay nên restart.
- **`ContextClosedEvent`**: thông báo vòng đời đóng của context bên trong ứng dụng.

Có thể có khoảng thời gian hệ thống đã ngừng định tuyến request mới trước khi context thực sự đóng. Không dùng `ContextClosedEvent` như nguồn sự thật duy nhất cho readiness. Chọn tín hiệu phù hợp với cơ chế điều phối và điều kiện nghiệp vụ.

### ContextClosedEvent có phát nếu không có web server?

**Có, trong trường hợp context đang hoạt động được đóng đúng cách**. Ví dụ đầy đủ ở mục 5 đặt `WebApplicationType.NONE` và vẫn nhận `ContextClosedEvent`. Event thuộc Spring `ApplicationContext`, không thuộc một servlet container cụ thể.

## 9. Quan sát và chẩn đoán shutdown

| Hiện tượng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Listener đóng không in log | Listener chưa đăng ký, context không đóng qua cơ chế bình thường, tiến trình bị kill cưỡng bức | Kiểm tra `@Component`/`@Bean`, đường shutdown, SIGTERM/SIGKILL, log thực tế |
| Có `ApplicationReadyEvent` nhưng không thấy close event | Ứng dụng vẫn chạy hoặc kết thúc ngoài đường đóng bình thường | Xem JVM shutdown hook, đoạn code đóng, dấu hiệu process crash |
| Thấy `ContextClosedEvent` trước log destroy | Hành vi chuẩn của `AbstractApplicationContext.doClose()` | Xác minh chuỗi close → lifecycle onClose → destroy singleton |
| `@PreDestroy` không chạy | Bean không do Spring quản lý, scope/lifecycle khác, hoặc shutdown cưỡng bức | Kiểm tra bean definition, scope, cách tạo instance và đường kết thúc |
| Listener chạy nhiều lần | Có nhiều context, context hierarchy hoặc nhiều lần tạo/đóng app | In context ID, so sánh `getApplicationContext()` |
| `ApplicationFailedEvent` xuất hiện nhưng không có `ContextClosedEvent` | Lỗi khởi động xảy ra trước khi có context active | Xác định mốc startup thất bại, kiểm tra stacktrace |
| Đóng context chậm | `SmartLifecycle`, destroy method hoặc listener đang chờ I/O/threads | Ghi log có thời lượng, timeout và dữ liệu đo cụ thể |
| Pod bị kill trước khi cleanup xong | Shutdown grace period hoặc signal handling không phù hợp | Kiểm tra terminationGracePeriodSeconds, shutdown hook, thời gian drain |
| Gọi `context.stop()` nhưng không có close event | Stop và close là hai API khác nhau | Dùng `context.close()` khi cần đóng vĩnh viễn |
| Code sau `context.close()` tiếp tục chạy | `close()` trả về người gọi; JVM chưa chắc đã thoát ngay | Xem logic `main()` và các thread còn hoạt động |

### Các bước xác minh hợp lý

1. Xác định **đường dừng**: đóng tường minh, Ctrl+C, SIGTERM, shutdown hook, test teardown hay crash.
2. Kiểm tra đúng **context ID và loại event**. Không suy diễn từ tên “Started/Stopped/Closed” giống nhau.
3. Nếu có listener, kiểm tra nó đã được đăng ký lúc context hoạt động chưa, và có thể bị loại khỏi component scan không.
4. Quan sát riêng thời gian nhận `ContextClosedEvent`, thời gian stop `SmartLifecycle`, và thời gian chạy destroy callback của resource quan trọng.
5. Với hệ thống web, tách vấn đề drain request và readiness khỏi việc hủy bean; xem log của load balancer hoặc container khi cần.
6. Nếu shutdown bị cưỡng bức, dùng cơ chế phục hồi có khả năng đối phó việc mất callback; đừng chỉ bổ sung một listener nữa.

## 10. Những lỗi hiểu sai thường gặp

**Sai lầm 1: “ContextClosedEvent nghĩa là bean đã được hủy sạch”.** Không. Sự kiện thường được công bố trước khi destruction callback thực thi.

**Sai lầm 2: “ContextStoppedEvent và ContextClosedEvent giống nhau”.** Không. `stop()` dành cho vòng đời start/stop; `close()` kết thúc context và hủy các singleton.

**Sai lầm 3: “ApplicationStoppedEvent là event shutdown chuẩn của Boot”.** Đừng tự giả định có một tên event như vậy. Hãy dùng các type sự kiện công khai thật sự, ví dụ `ContextClosedEvent` của Spring Framework.

**Sai lầm 4: “ApplicationStartedEvent đã có nghĩa tất cả runner chạy xong”.** Không. Runner chạy sau `ApplicationStartedEvent`; `ApplicationReadyEvent` xuất hiện muộn hơn.

**Sai lầm 5: “Tôi có thể nhận ApplicationStartingEvent bằng @EventListener trên một bean”.** Không phải cách đáng tin cho sự kiện phát trước context; listener cho startup cực sớm phải đăng ký trước `run()`.

**Sai lầm 6: “Nếu startup lỗi, ContextClosedEvent chắc chắn xuất hiện”.** Không. Lỗi quá sớm có thể chưa có context active; `ApplicationFailedEvent` là sự kiện Boot cho đường thất bại startup.

**Sai lầm 7: “Shutdown hook luôn chạy”.** Không, ví dụ `SIGKILL` hoặc JVM crash có thể bỏ qua mọi hook.

**Sai lầm 8: “Dùng ContextClosedEvent để đóng mọi resource”.** Dễ dẫn đến phụ thuộc chéo, khó kiểm soát thứ tự và timeout. Bean nào sở hữu tài nguyên thì nên tự chịu trách nhiệm lifecycle.

**Sai lầm 9: “Có event đóng thì mọi HTTP request đã kết thúc”.** Không thể kết luận thế chỉ từ event. Cần cơ chế graceful shutdown, drain kết nối và chính sách timeout tương ứng.

**Sai lầm 10: “Một ContextClosedEvent luôn thuộc về context của listener”.** Với context hierarchy, listener cha có thể thấy event của context con. Hãy kiểm tra `event.getApplicationContext()`.

## 11. Câu hỏi ôn tập

**Câu hỏi 1:** `ContextClosedEvent` được phát trước hay sau `@PreDestroy` của singleton thông thường?

**Trả lời:** Trong đường đóng context chuẩn của `AbstractApplicationContext`, event được công bố trước `destroyBeans()`, nên callback hủy của singleton thường đến sau.

**Câu hỏi 2:** Listener `@EventListener(ContextClosedEvent.class)` có thể là Spring bean thông thường không?

**Trả lời:** Có. Context đã tồn tại và listener đã được đăng ký khi nó bắt đầu đóng, khác với sự kiện startup cực sớm như `ApplicationStartingEvent`.

**Câu hỏi 3:** `ApplicationReadyEvent` có phải shutdown event không?

**Trả lời:** Không. Nó cho biết Spring Boot đã hoàn tất giai đoạn startup và các runners; shutdown là một chặng lifecycle khác.

**Câu hỏi 4:** Khi chạy chương trình CLI với `WebApplicationType.NONE`, đóng context có phát `ContextClosedEvent` không?

**Trả lời:** Có, nếu context đang hoạt động được đóng theo đường bình thường. Event không yêu cầu HTTP server.

**Câu hỏi 5:** `context.stop()` có thay thế được `context.close()` không?

**Trả lời:** Không. Stop chỉ điều khiển lifecycle, còn close kết thúc context và hủy các bean singleton.

**Câu hỏi 6:** Tại sao không nên dùng `ContextClosedEvent` để chắc chắn ghi đơn hàng cuối cùng vào database?

**Trả lời:** Listener có thể không chạy hoặc không hoàn tất khi tiến trình bị kill, timeout hoặc sập bất thường. Ghi dữ liệu quan trọng phải theo cơ chế có bảo đảm/khả năng phục hồi ở luồng nghiệp vụ.

**Bài tập:** Chạy mã mục 5 và ghi lại tám mốc. Thử đổi việc đóng tường minh thành đóng bằng shutdown hook trong một tiến trình giữ JVM chạy; sau đó thêm `@PreDestroy` cho resource và giải thích thứ tự. Phân biệt thêm `ContextStoppedEvent` bằng một listener phù hợp và thao tác `context.stop()`. Cuối cùng, cố ý gây lỗi runner và so sánh đường đi của `ApplicationFailedEvent` với close bình thường.

## 12. Tài liệu chính thức

- [Spring Framework — ApplicationContext events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): ngữ nghĩa `ContextClosedEvent`, `ContextStoppedEvent`, `@EventListener` và cơ chế sự kiện.
- [Spring Framework — AbstractApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `doClose()`, `destroyBeans()`, `registerShutdownHook()`.
- [Spring Framework — ContextClosedEvent Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ContextClosedEvent.html): kiểu event và context source.
- [Spring Boot 3.5 — SpringApplication: events, listeners và exit](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): thứ tự các sự kiện Boot và shutdown hook.
- [Spring Boot 3.5 — Graceful shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html): cách phối hợp web server khi dừng.

## 13. Ghi nhớ

- `ContextClosedEvent` thuộc **Spring Framework**, báo **bắt đầu đóng `ApplicationContext` đang hoạt động**; nó không phải sự kiện `ApplicationStartedEvent` hoặc `ApplicationReadyEvent` của Spring Boot.
- Đường đóng bình thường: **công bố ContextClosedEvent → dừng lifecycle beans → hủy singleton beans → hoàn tất đóng context**.
- `@EventListener` hoặc `ApplicationListener<ContextClosedEvent>` phù hợp để quan sát; resource nên tự dọn bằng `@PreDestroy`, `DisposableBean`, destroy method hoặc `SmartLifecycle` thích hợp.
- `ContextStoppedEvent` là stop, có thể start lại trong mô hình hỗ trợ; `ContextClosedEvent` là close, context kết thúc vòng đời.
- `ApplicationStartingEvent` là đầu startup; `ApplicationStartedEvent` sau refresh; `ApplicationReadyEvent` sau runners; `ApplicationFailedEvent` khi startup thất bại.
- Event shutdown **không được bảo đảm** khi JVM bị kill cưỡng bức; kết hợp graceful shutdown, timeout và cơ chế phục hồi để bảo vệ dữ liệu và tài nguyên.