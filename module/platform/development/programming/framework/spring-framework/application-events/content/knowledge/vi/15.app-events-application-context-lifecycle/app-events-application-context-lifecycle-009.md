# Sự kiện khi đóng ứng dụng trong Spring Framework Application Events

## 1. ContextClosedEvent là gì?

`ContextClosedEvent` là sự kiện vòng đời chuẩn của Spring Framework, được phát khi một `ApplicationContext` đang thực hiện quá trình đóng. Trong ứng dụng thông thường, đây là tín hiệu để những thành phần quan tâm biết rằng context sắp kết thúc vòng đời: ngừng nhận công việc mới, ghi nhận trạng thái vận hành cuối cùng, thông báo cho bộ phận điều phối hoặc phối hợp bước dọn dẹp.

Ví dụ, một hệ thống xử lý đơn hàng có các thành phần:

- Listener theo dõi việc ứng dụng chuẩn bị ngừng, để chuyển trạng thái phục vụ sang "draining".
- Thành phần `SmartLifecycle` dừng việc nhận thêm job và đợi những job đang chạy hoàn tất.
- Bean giữ kết nối hoặc tài nguyên nội bộ, tự giải phóng trong `destroy()` hoặc `@PreDestroy`.
- Ứng dụng web cần hoàn thành những request đang xử lý theo chính sách graceful shutdown.

Các trách nhiệm này liên quan nhau, nhưng **không nên gộp tất cả vào một listener**. `ContextClosedEvent` thông báo **ngữ cảnh chuẩn bị đóng**, còn việc dừng và giải phóng tài nguyên theo vòng đời bean vẫn do các cơ chế lifecycle của Spring quản lý.

Loại sự kiện có quan hệ kế thừa:

```text
java.util.EventObject
    -> org.springframework.context.ApplicationEvent
        -> org.springframework.context.event.ApplicationContextEvent
            -> org.springframework.context.event.ContextClosedEvent
```

Thông tin chính nằm ở `event.getApplicationContext()`: context phát sự kiện. Không cần tự tạo `ContextClosedEvent` để kích hoạt đóng ứng dụng; hãy đóng context bằng API tương ứng để Spring điều phối đúng toàn bộ vòng đời.

## 2. Khi nào Spring phát sự kiện đóng?

Các tình huống điển hình:

1. Mã ứng dụng gọi `close()` trên một `ConfigurableApplicationContext`.
2. Một context đã đăng ký JVM shutdown hook bằng `registerShutdownHook()` và JVM thực hiện shutdown bình thường.
3. Một ứng dụng do Spring Boot điều hành được yêu cầu tắt theo quy trình chuẩn, dẫn tới việc đóng application context.

`ApplicationContext` là giao diện đọc/truy cập context; **không phải mọi biến khai báo kiểu `ApplicationContext` đều có phương thức `close()`**. API đóng thuộc `ConfigurableApplicationContext` và các triển khai như `AnnotationConfigApplicationContext`.

Ví dụ:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfig.class);

// Chương trình làm việc...

context.close(); // Spring phát ContextClosedEvent và đóng context.
```

Vì `AnnotationConfigApplicationContext` hỗ trợ `AutoCloseable`, cũng có thể dùng `try-with-resources` để chắc chắn gọi `close()` khi ra khỏi khối:

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Sử dụng các bean.
} // close() được gọi tại đây.
```

Hai đoạn trên là **mẫu sử dụng API**, chưa phải chương trình độc lập; ví dụ đầy đủ có các bean cụ thể ở mục 5.

### Trường hợp không có bảo đảm nhận được event

`ContextClosedEvent` chỉ được phát nếu context thực sự đi vào quy trình close. Việc JVM bị kill cưỡng bức (ví dụ `SIGKILL`), process crash, mất điện hoặc môi trường runtime chấm dứt tức thời **không bảo đảm** shutdown hook, listener hay destroy callback được chạy.

Ngay cả khi tín hiệu shutdown thông thường được gửi, thời gian chờ của process/container cũng có thể bị giới hạn. Vì vậy không nên dùng `ContextClosedEvent` làm nơi duy nhất lưu thông tin nghiệp vụ quan trọng.

## 3. Trình tự đóng trong AbstractApplicationContext

Trong triển khai phổ biến của Spring Framework `AbstractApplicationContext`, luồng đóng ở mức khái niệm là:

```text
ConfigurableApplicationContext.close()
             |
             v
     Bắt đầu thủ tục doClose()
             |
             v
     Phát ContextClosedEvent
             |
             v
   LifecycleProcessor.onClose()
   (dừng các Lifecycle/SmartLifecycle bean)
             |
             v
   Hủy singleton bean do context quản lý
   (DisposableBean, @PreDestroy, destroy-method)
             |
             v
    Đóng BeanFactory/context
```

**Với multicaster mặc định đồng bộ**, callback `@EventListener(ContextClosedEvent.class)` thường được gọi **trước** khi các singleton bean bị hủy. Trong callback, một số dependency vẫn có thể còn tồn tại; không có nghĩa việc khởi tạo thêm công việc dài hoặc dựa vào toàn bộ hạ tầng vẫn an toàn.

Trình tự trên mô tả `AbstractApplicationContext` theo Spring 6.x và có thể bị ảnh hưởng bởi multicaster tùy chỉnh, listener bất đồng bộ hoặc triển khai context khác. Ở mức API, nên dựa vào **hợp đồng vòng đời thích hợp** thay vì viết logic gắn chặt với thứ tự nội bộ nếu chưa kiểm thử.

| Giai đoạn | Cơ chế Spring | Ý nghĩa |
| --- | --- | --- |
| Thông báo context sắp đóng | `ContextClosedEvent` | Quan sát hoặc bắt đầu phối hợp |
| Dừng thành phần có vòng đời | `LifecycleProcessor`, `SmartLifecycle` | Điều phối dừng có thứ tự/pha và callback hoàn tất |
| Dọn tài nguyên của bean | `DisposableBean.destroy()`, `@PreDestroy`, `@Bean(destroyMethod=...)` | Giải phóng tài nguyên thuộc quyền sở hữu bean |
| Kết thúc context | `close()` hoàn tất | Không tiếp tục lấy bean hoặc phát event vào context đã đóng |

**Không nhầm với `ContextStoppedEvent`:** gọi `context.stop()` dừng các bean có `Lifecycle` và phát `ContextStoppedEvent`, nhưng context có thể được `start()` lại. `context.close()` kết thúc vòng đời context; context đã đóng không được dùng để refresh hay khởi động lại như cũ.

## 4. Đăng ký listener nhận ContextClosedEvent

### 4.1. Dùng `@EventListener`

Cách ngắn gọn khi bean đã được Spring quản lý:

```java
@Component
public class ShutdownObserver {

    @EventListener
    public void onContextClosed(ContextClosedEvent event) {
        System.out.println("Context closing: "
                + event.getApplicationContext().getId());
    }
}
```

Đây là đoạn minh họa tích hợp: cần import `@Component`, `@EventListener` và `ContextClosedEvent`; class phải được đăng ký qua component scan hoặc bean declaration. Tham số của phương thức cho Spring biết chính xác kiểu sự kiện mà nó quan tâm.

Có thể viết rõ kiểu event bằng `@EventListener(ContextClosedEvent.class)`, nhưng nếu phương thức đã có tham số `ContextClosedEvent` thì cách ngắn gọn phía trên đủ rõ.

### 4.2. Dùng `ApplicationListener<ContextClosedEvent>`

```java
@Component
public class ShutdownListener
        implements ApplicationListener<ContextClosedEvent> {

    @Override
    public void onApplicationEvent(ContextClosedEvent event) {
        // Xử lý tín hiệu context chuẩn bị đóng.
    }
}
```

Lớp dùng interface là phương án hợp lệ khi muốn kiểu listener thể hiện trực tiếp ở khai báo class. Đừng tự đăng ký cùng một listener theo nhiều cơ chế rồi vô tình tạo nhiều callback.

### 4.3. Xác định context phát event

`event.getApplicationContext()` trả về context liên quan tới event; với một hệ thống có nhiều context cha/con, thông tin này đặc biệt quan trọng.

```java
@EventListener
public void onContextClosed(ContextClosedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return; // Bỏ qua tín hiệu đóng từ context khác.
    }
    // Xử lý cho đúng context mà bean này theo dõi.
}
```

Đây là mẫu tích hợp, `ownContext` phải là dependency `ApplicationContext` được inject. Spring có thể truyền event từ context con lên context cha; listener đặt trong context cha có thể thấy event phát từ context con. Nếu cần đúng phạm vi, hãy so sánh **context instance**, thay vì mặc nhiên xem tất cả `ContextClosedEvent` đều thuộc chính context của listener.

## 5. Ví dụ hoàn chỉnh chạy với Java 17 + Spring Framework

Ví dụ dưới đây chứng minh ba điểm:

1. Trong `try-with-resources`, context được đóng tự động.
2. `@EventListener` nhận `ContextClosedEvent` khi tài nguyên mẫu vẫn đang mở.
3. `DisposableBean.destroy()` được gọi sau đó để đóng tài nguyên.

Ví dụ dùng `AnnotationConfigApplicationContext` thuần: không cần web server, database hay Spring Boot.

### Cấu trúc dự án

```text
context-closed-event-demo/
├── pom.xml
└── src/main/java/example/ContextClosedEventDemo.java
```

### Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-closed-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <configuration>
                    <mainClass>example.ContextClosedEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### Tệp `src/main/java/example/ContextClosedEventDemo.java`

```java
package example;

import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;

public class ContextClosedEventDemo {

    // Giữ bằng chứng để in sau khi context đã đóng.
    public static final class Trace {
        private final List<String> events = new ArrayList<>();

        public void add(String event) {
            events.add(event);
        }

        public void printAll() {
            events.forEach(System.out::println);
        }
    }

    // Mô phỏng một bean sở hữu tài nguyên cần đóng.
    public static final class TrackedResource implements DisposableBean {
        private final Trace trace;
        private boolean open = true;

        public TrackedResource(Trace trace) {
            this.trace = trace;
        }

        public boolean isOpen() {
            return open;
        }

        @Override
        public void destroy() {
            open = false;
            trace.add("DisposableBean.destroy: resourceOpen=" + open);
        }
    }

    // Chỉ quan sát tín hiệu đóng; resource tự hủy khi Spring
    // gọi DisposableBean.destroy().
    public static final class CloseObserver {
        private final Trace trace;
        private final TrackedResource resource;

        public CloseObserver(Trace trace, TrackedResource resource) {
            this.trace = trace;
            this.resource = resource;
        }

        @EventListener
        public void onContextClosed(ContextClosedEvent event) {
            trace.add("ContextClosedEvent: resourceOpen="
                    + resource.isOpen());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public TrackedResource trackedResource(Trace trace) {
            return new TrackedResource(trace);
        }

        @Bean
        public CloseObserver closeObserver(Trace trace,
                                            TrackedResource resource) {
            return new CloseObserver(trace, resource);
        }
    }

    public static void main(String[] args) {
        Trace trace;
        TrackedResource resource;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            trace = context.getBean(Trace.class);
            resource = context.getBean(TrackedResource.class);
            System.out.println("Trước close: resourceOpen="
                    + resource.isOpen());
        }

        System.out.println("Sau close: resourceOpen="
                + resource.isOpen());
        trace.printAll();
    }
}
```

### Chạy chương trình

Trong thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Các dòng do ứng dụng in ra:**

```text
Trước close: resourceOpen=true
Sau close: resourceOpen=false
ContextClosedEvent: resourceOpen=true
DisposableBean.destroy: resourceOpen=false
```

Dòng “Sau close” được in **trước các dòng lưu trong `Trace`** bởi vì chương trình chủ động in trạng thái sau khi thoát khối `try`, rồi mới gọi `trace.printAll()`. Thứ tự thực tế của **hai callback** được phản ánh trong hai dòng cuối: listener `ContextClosedEvent` được gọi khi tài nguyên còn mở; sau đó Spring gọi `DisposableBean.destroy()` và đặt `open = false`.

Trong ứng dụng thực, không nên tiếp tục gọi service hoặc dùng resource đã bị đóng. Ở đây biến `resource` và `trace` còn được giữ sau khi context đóng chỉ để đọc trạng thái và in dữ liệu kiểm chứng; cả hai là đối tượng Java in-memory đơn giản. Không có hạ tầng bên ngoài nào bị truy cập sau close.

**Vì sao ví dụ hoạt động?** Khi khởi tạo `AnnotationConfigApplicationContext(Config.class)`, Spring tạo các singleton bean và đăng ký phương thức `@EventListener` của `CloseObserver`. Khi `try-with-resources` gọi `close()`, `AbstractApplicationContext` phát `ContextClosedEvent`, sau đó dừng các lifecycle bean và hủy singleton. `TrackedResource` triển khai `DisposableBean` nên nhận lời gọi `destroy()`.

### Một biến thể để kiểm tra sự kiện chỉ từ context cần quan sát

Nếu code chạy trong hệ thống nhiều context, có thể inject `ApplicationContext` vào `CloseObserver` và chỉ ghi nhận khi `event.getApplicationContext() == localContext`. Ví dụ mục 5 chỉ có một context nên không cần điều kiện đó.

## 6. JVM shutdown hook và đóng chủ động

### 6.1. Đóng chủ động bằng `close()`

Với ứng dụng command-line, integration test hay một container điều khiển vòng đời, `try-with-resources` hoặc `context.close()` cho phép điểm đóng rõ ràng. Đây thường là cách **dễ kiểm thử nhất** để xác nhận `ContextClosedEvent` và callback hủy bean.

### 6.2. Đăng ký shutdown hook

Khi ứng dụng tồn tại cho tới lúc JVM kết thúc, có thể đăng ký hook:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext(Config.class);

context.registerShutdownHook();

// Chương trình tiếp tục vận hành. Khi JVM shutdown bình thường,
// hook sẽ yêu cầu đóng context.
```

Đoạn này minh họa API và dùng class `Config` của ví dụ trước; không phải ứng dụng chạy lâu độc lập. Khi context đã được đóng chủ động, Spring xử lý hook đã đăng ký để không cần đóng lại một cách dư thừa.

**Giới hạn:** JVM shutdown hook không chạy bảo đảm trong tất cả kịch bản. Lệnh dừng cưỡng bức như `kill -9`, một số sự cố hệ điều hành hoặc container bị kết thúc sau khi hết grace period có thể khiến callback không hoàn tất. Hãy coi shutdown hook là hỗ trợ **graceful shutdown**, không phải cơ chế lưu trữ bền vững.

### 6.3. Khi dùng Spring Boot

Trong ứng dụng Spring Boot thông thường, framework quản lý context và đăng ký quy trình shutdown với JVM. Khi ứng dụng được đóng qua quy trình chuẩn, `ContextClosedEvent` vẫn là sự kiện vòng đời của Spring context.

Với web server, cần phân biệt **đóng context** và **graceful shutdown** của server: graceful shutdown tập trung vào việc ngừng nhận request mới và cho các request đang chạy cơ hội hoàn tất trong giới hạn cấu hình. Tác vụ dài, queue nội bộ và xử lý sự kiện vẫn cần chính sách dừng phù hợp.

Không suy ra rằng listener `ContextClosedEvent` đã hoàn tất nghĩa là mọi request, job và lần gửi thông báo đều đã hoàn tất.

## 7. Chọn cơ chế shutdown phù hợp với trách nhiệm

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Log/metrics một tín hiệu context sắp đóng | `@EventListener(ContextClosedEvent.class)` | Quan sát một event toàn context |
| Đóng connection/file/socket do một bean sở hữu | `@PreDestroy`, `DisposableBean` hoặc `destroyMethod` | Cleanup nằm cùng owner của tài nguyên |
| Dừng thành phần nhận việc, chờ hoàn tất theo phase | `SmartLifecycle` | Hỗ trợ phase, `stop(Runnable)` và điều phối bởi `LifecycleProcessor` |
| Đóng context trong ứng dụng/test | `ConfigurableApplicationContext.close()` hoặc try-with-resources | Chủ động kích hoạt đúng quy trình Spring |
| Đóng khi JVM kết thúc bình thường | `registerShutdownHook()` nếu cần | Gắn việc close vào JVM shutdown |
| Không được mất sự kiện/công việc khi process chết | Database/outbox/broker, lưu checkpoint bền vững | Shutdown listener không bảo đảm chạy khi crash |

**Với cleanup của bean**, nên ưu tiên callback destroy tương ứng thay vì một listener toàn context phải biết tất cả tài nguyên. Ví dụ, datasource pool thường đã có cơ chế đóng riêng; gọi `close()` lần hai từ `ContextClosedEvent` có thể gây race hoặc lỗi khó tìm.

**Với thành phần cần dừng có thứ tự**, `SmartLifecycle` hỗ trợ thứ tự các phase và callback `stop(Runnable)`. Callback này cần được gọi khi việc dừng bất đồng bộ hoàn thành; nếu quên gọi callback, shutdown có thể chờ tới timeout. Khi ứng dụng có queue/job đang chạy, đây thường là lựa chọn rõ ràng hơn một listener sự kiện bắt đầu tác vụ async rồi trả về ngay.

## 8. Những giới hạn quan trọng của ContextClosedEvent

### 8.1. Không dùng làm kho lưu sự kiện nghiệp vụ cuối cùng

Giả sử listener đóng context cố gắng gửi email hoặc flush số liệu đến một HTTP API:

```java
@EventListener
public void onClosing(ContextClosedEvent event) {
    remoteReporter.sendFinalMetrics();
}
```

Đây là đoạn minh họa cần bean `remoteReporter` được inject. Một cuộc gọi mạng đồng bộ có thể kéo dài thời gian shutdown; gọi async có thể bị từ chối vì executor cũng đang đóng. Nếu việc gửi là quan trọng, cần persist dữ liệu **trong khi ứng dụng còn hoạt động**, rồi retry bằng worker/broker hoặc xử lý có checkpoint bền vững. Listener đóng chỉ nên hoàn tất phần phối hợp ngắn gọn, có timeout hợp lý.

### 8.2. Cẩn trọng với `@Async` trên listener đóng

`@Async @EventListener` làm callback chạy sau trên executor được chỉ định. Trong lúc context đang đóng, executor, dependency và bean liên quan cũng có thể bị hủy. Vì vậy việc **gửi** một async task thành công không chứng minh task đã hoàn tất trước khi shutdown kết thúc.

Nếu một bước dừng bắt buộc phải hoàn tất trước khi giải phóng tài nguyên, dùng `SmartLifecycle` hoặc cơ chế đồng bộ/callback có timeout rõ ràng; đừng dựa vào một fire-and-forget task.

### 8.3. Không nhầm với listener transaction

`ContextClosedEvent` là sự kiện vòng đời context, thông thường **không gắn với transaction nghiệp vụ**. Đặt `@TransactionalEventListener` vào một phương thức chỉ nghe close có thể khiến listener không chạy, vì mặc định `fallbackExecution = false` nếu không có transaction. Dùng `@EventListener` để quan sát sự kiện đóng context.

### 8.4. Listener ném exception khi đóng

Trong triển khai `AbstractApplicationContext`, đường đóng có xử lý lỗi khi phát `ContextClosedEvent` để tiếp tục các bước đóng tiếp theo. Tuy vậy, exception từ một listener có thể ảnh hưởng quá trình multicaster gọi những listener khác, và lỗi cần được ghi nhận. Đừng dùng exception từ listener để điều khiển việc hủy các bean khác.

Nếu cleanup có thể lỗi, hãy bắt ngoại lệ ở đúng ranh giới, log/metric hợp lý, và bảo đảm các nguồn lực quan trọng vẫn được chủ sở hữu bean đóng theo lifecycle chính thức.

### 8.5. Context cha/con và nhiều application context

Một process có thể có nhiều context. Event được publish trong context con có thể được chuyển lên context cha. Listener của context cha vì thế có thể nhận `ContextClosedEvent` liên quan tới context con. Kiểm tra `event.getApplicationContext()` nếu thao tác chỉ được thực hiện cho một context cụ thể.

Không tự kết luận một event đóng context con đồng nghĩa **toàn bộ JVM** đang dừng hoặc mọi context khác đã đóng.

### 8.6. Thứ tự callback và idempotency

Một context thông thường chỉ đi qua quy trình close một lần, nhưng hệ thống thực tế có thể tạo nhiều context qua test, reload hoặc nhiều phiên khởi chạy. Khi callback chạm tới cùng tài nguyên bên ngoài, hãy thiết kế thao tác dừng có thể chạy lặp mà không gây hại. Ví dụ đóng một client nên kiểm tra hoặc dựa vào hợp đồng close idempotent thay vì tự gây lỗi khi được gọi lại.

Điều này không có nghĩa Spring tự động bảo đảm exactly-once cho tác dụng phụ bên ngoài.

## 9. Kiểm thử sự kiện đóng ứng dụng

Một bài kiểm thử nên xác minh **sự kiện được phát**, **đúng context**, và **thứ tự tương đối với cleanup**. Từ ví dụ mục 5:

| Giai đoạn | Trạng thái tài nguyên | Điều mong đợi |
| --- | --- | --- |
| Context đã khởi tạo | `open = true` | Có thể sử dụng tài nguyên |
| Listener nhận `ContextClosedEvent` | `open = true` | Listener biết context sắp đóng |
| `DisposableBean.destroy()` | Chuyển `open` sang `false` | Tài nguyên được giải phóng |
| Sau khi `close()` hoàn tất | `open = false` | Không dùng lại bean/resource |

**Các test bổ sung có giá trị:**

1. **Đúng loại event:** đăng ký listener chỉ nhận `ContextClosedEvent`, xác nhận không xử lý nhầm `ContextRefreshedEvent` hay `ContextStoppedEvent`.
2. **Đóng bằng API:** gọi `close()` hoặc dùng try-with-resources trên context thực; đừng chỉ gọi trực tiếp phương thức `onContextClosed` rồi xem như kiểm tra tích hợp.
3. **Đúng thứ tự:** ghi dấu bằng một trace đơn giản, kiểm tra listener close chạy trước callback destroy trong cấu hình đồng bộ đang dùng.
4. **Context cha/con:** kiểm tra listener của context cha có cần bỏ qua event xuất phát từ context con không.
5. **Lỗi của listener:** gây lỗi có kiểm soát, xác minh log và trạng thái tài nguyên sau shutdown theo triển khai thực tế.
6. **Shutdown trong môi trường thật:** chạy qua tín hiệu dừng bình thường và giới hạn thời gian, sau đó kiểm tra những job được lưu/đánh dấu trạng thái. Bài kiểm thử này phải riêng với unit test in-memory.
7. **Nhiều lần chạy:** tạo và đóng nhiều context độc lập, tránh lưu trạng thái của lần trước làm sai kết quả.

Test shutdown hook riêng có thể kết thúc JVM thử nghiệm; tránh chạy `System.exit(...)` trong JVM chứa bộ test chính. Để kiểm tra hook thực, nên dùng **process con** và xác minh kết quả từ process đó.

## 10. Các lỗi thường gặp

1. **Nhầm `ContextStoppedEvent` với `ContextClosedEvent`.** `stop()` không đồng nghĩa với `close()`; context stopped có thể start lại.
2. **Gọi `close()` trên một biến chỉ có kiểu `ApplicationContext`.** Dùng `ConfigurableApplicationContext` hoặc kiểu triển khai hỗ trợ close.
3. **Giả định event luôn chạy khi process chết.** Shutdown không được bảo đảm khi JVM bị kill cưỡng bức hoặc crash.
4. **Dồn mọi cleanup vào một `@EventListener`.** Việc giải phóng resource nên thuộc bean sở hữu bằng destroy callback; việc dừng nhiều service có phase nên dùng `SmartLifecycle`.
5. **Thực hiện công việc I/O quá lâu trong callback đóng.** Có thể làm kéo dài thời gian shutdown và chạm giới hạn container.
6. **Khởi tạo tác vụ `@Async` khi executor đang đóng.** Task có thể bị từ chối hoặc không chạy xong; xử lý dừng phải có cơ chế chờ phù hợp.
7. **Tạo event đóng thủ công để thay `close()`.** Gọi `publisher.publishEvent(new ContextClosedEvent(...))` chỉ phát một object event, không tự thực hiện đầy đủ quy trình hủy bean của `close()`.
8. **Không kiểm tra context phát sự kiện.** Trong cấu trúc cha/con có thể nhận tín hiệu đóng của context khác.
9. **Giả định bean vẫn sử dụng được sau `close()`.** Các singleton đã bị hủy; không tiếp tục giao việc dựa trên bean hoặc connection đã đóng.
10. **Cho rằng listener close có transaction sẵn có.** Không dùng `@TransactionalEventListener` khi mục tiêu chỉ là nhận sự kiện context đóng.
11. **Bỏ qua lỗi khi đóng.** Cần log đủ thông tin và phối hợp cleanup, nhưng không coi listener là nơi “chặn” ứng dụng ngừng.
12. **Phụ thuộc thứ tự của nhiều listener bằng mặc định.** Nếu thật sự cần thứ tự, định nghĩa orchestration rõ ràng hoặc cấu hình `SmartLifecycle` có phase phù hợp; với async, thứ tự hoàn tất càng không được bảo đảm.

## 11. Checklist áp dụng

- Ứng dụng có điểm đóng context rõ ràng: `close()`, try-with-resources hoặc hook do framework quản lý.
- Listener nhận đúng `ContextClosedEvent` và đã được đăng ký thành Spring bean.
- Với nhiều context, đã xác định đúng `event.getApplicationContext()`.
- Callback close chỉ làm việc ngắn, phù hợp giới hạn thời gian shutdown.
- Cleanup thuộc về bean sử dụng `DisposableBean`, `@PreDestroy` hoặc destroy method.
- Tác vụ cần dừng có thứ tự dùng `SmartLifecycle`, kiểm thử callback hoàn tất/timeout.
- Không phụ thuộc shutdown event để lưu dữ liệu nghiệp vụ không được phép mất.
- Đã kiểm thử thứ tự event → destroy và kiểm tra trạng thái sau `close()`.
- Đã xem xét graceful shutdown, retry/checkpoint cho những task đang chạy trong production.

**Ghi nhớ:** `ContextClosedEvent` thông báo rằng **Spring ApplicationContext đang đóng**. Trong `AbstractApplicationContext` với multicaster đồng bộ thông thường, event đến listener trước khi các singleton bean bị hủy. Hãy dùng listener để quan sát/phối hợp; dùng lifecycle/destroy callback để dừng và đóng tài nguyên đúng cách; và không coi shutdown event là cơ chế bảo đảm phát sự kiện bền vững.

## Tài liệu chính thức

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Javadoc — ContextClosedEvent (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/ContextClosedEvent.html)
- [Javadoc — AbstractApplicationContext (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Javadoc — ConfigurableApplicationContext (Spring 6.2)](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
