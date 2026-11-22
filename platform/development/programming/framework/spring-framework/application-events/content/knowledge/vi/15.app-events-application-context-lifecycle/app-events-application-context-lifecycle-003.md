# ContextStoppedEvent trong vòng đời ApplicationContext của Spring Framework

## 1. ContextStoppedEvent là sự kiện gì?

`ContextStoppedEvent` là sự kiện hệ thống của Spring, thuộc package `org.springframework.context.event`. Nó được phát khi một `ApplicationContext` nhận lệnh **dừng tường minh** thông qua `ConfigurableApplicationContext.stop()`. Đây là tín hiệu về vòng đời của **context**, khác với một event nghiệp vụ như `OrderCreated` hoặc `PaymentSucceeded`.

Lớp này kế thừa `ApplicationContextEvent`, nên một listener có thể gọi `event.getApplicationContext()` để lấy đúng context đã phát sự kiện. Event cũng có timestamp thông qua `ApplicationEvent.getTimestamp()`. Không cần tự xây dựng đối tượng `ContextStoppedEvent` trong đường đi thông thường: Spring tạo và phát sự kiện khi thao tác `stop()` được gọi.

Tại sao sự kiện này hữu ích? Một ứng dụng có thể muốn biết rằng các thành phần `Lifecycle` đã nhận tín hiệu stop, chẳng hạn để ghi log vận hành, cập nhật trạng thái giám sát, hoặc hoàn thiện thông tin của một phiên chạy. Nhưng cần hiểu rõ một giới hạn nền tảng:

**`stop()` không tương đương `close()`.** Context bị stop vẫn còn active và có thể được start lại. Việc stop không có nghĩa toàn bộ singleton bean đã bị hủy hoặc JVM đã thoát.

## 2. ContextStoppedEvent xuất hiện ở đâu trong vòng đời?

Với một `ApplicationContext` được quản lý bằng `AnnotationConfigApplicationContext` hoặc các triển khai `ConfigurableApplicationContext` thông thường, có thể hình dung:

```text
new/refresh()
  |
  +-- khởi tạo bean và cơ chế ApplicationEvent
  +-- auto-start các SmartLifecycle thích hợp
  +-- phát ContextRefreshedEvent
  |
context.start()
  +-- LifecycleProcessor.start(): gửi tín hiệu start cho Lifecycle beans
  +-- phát ContextStartedEvent
  |
context.stop()
  +-- LifecycleProcessor.stop(): gửi tín hiệu stop cho Lifecycle beans
  +-- phát ContextStoppedEvent
  |       \-- @EventListener / ApplicationListener nhận event
  |
context.start()       <-- có thể chạy lại sau stop
  +-- LifecycleProcessor.start()
  +-- phát ContextStartedEvent
  |
context.close()
  +-- phát ContextClosedEvent trong quá trình đóng
  +-- dừng Lifecycle beans còn chạy, hủy singleton beans
  +-- context hết vòng đời
```

Hai sự kiện `ContextStartedEvent` và `ContextStoppedEvent` thường đi cùng các lời gọi `start()`/`stop()` một cách tường minh. `ContextRefreshedEvent` là tín hiệu khởi tạo/refresh. `ContextClosedEvent` gắn với đóng context và hủy tài nguyên.

Một ứng dụng được shutdown bình thường có thể gọi `close()` mà **không hề gọi `stop()` công khai trước đó**. Khi đó không được mặc định cho rằng luôn có `ContextStoppedEvent`. Trong các ứng dụng Spring Boot hoặc server, nhiều luồng shutdown dựa trên `ContextClosedEvent`, `SmartLifecycle` và quy trình đóng context; event stopped không phải tín hiệu chung thay thế cho mọi lần shutdown JVM.

## 3. Quan hệ với Lifecycle, SmartLifecycle và LifecycleProcessor

`ContextStoppedEvent` mô tả *sự kiện sau tín hiệu dừng context*, còn thao tác dừng bean được điều phối bởi `LifecycleProcessor` (mặc định là `DefaultLifecycleProcessor`).

### Lifecycle

Một bean triển khai `org.springframework.context.Lifecycle` có ba phương thức chính:

```java
void start();
void stop();
boolean isRunning();
```

Khi context nhận lệnh `start()`, lifecycle processor khởi động các bean thuộc diện quản lý. Khi gọi `stop()`, processor yêu cầu các bean đang chạy dừng. `isRunning()` giúp Spring kiểm tra trạng thái hiện tại.

**Bean chỉ triển khai `Lifecycle` thường không tự động được start trong bước refresh**; nó nhận tín hiệu start khi context được start tường minh. Điều này giúp ví dụ ở mục 5 có đầu ra dễ kiểm chứng.

### SmartLifecycle

`SmartLifecycle` mở rộng `Lifecycle` và hỗ trợ điều phối nâng cao:

- `isAutoStartup()`: mặc định trả `true`, cho phép tự start khi context refresh hoàn tất.
- `getPhase()`: số phase điều khiển thứ tự khởi động và dừng. Khi start, phase thấp hơn thường chạy trước; khi stop, phase cao hơn thường dừng trước.
- `stop(Runnable callback)`: hỗ trợ dừng bất đồng bộ; bean phải chạy `callback.run()` sau khi thực sự dừng để lifecycle processor biết đã xong. Nếu không gọi callback, giai đoạn shutdown có thể phải chờ tới timeout.
- Quan hệ dependency giữa các bean có thể được ưu tiên hơn phase, vì một bean phụ thuộc cần dừng trước bean mà nó phụ thuộc vào.

Mặc định ở Spring Framework 6.x, `SmartLifecycle` có phase lớn, nên thường được xử lý stop trước các bean `Lifecycle` ở phase 0. Không suy ra thứ tự từ tên bean hoặc thứ tự khai báo class.

### Khi nào listener nhận ContextStoppedEvent?

Trong đường đi `AbstractApplicationContext.stop()` thông thường, Spring gọi `LifecycleProcessor.stop()` rồi **phát** `ContextStoppedEvent`. Do đó với bộ phát sự kiện đồng bộ mặc định, callback nhận event diễn ra sau khi processor đã hoàn tất lời gọi stop của nó.

Cần phân biệt hai thứ:

1. **Thứ tự stop các bean** được điều khiển bởi lifecycle processor, phase và dependency.
2. **Thứ tự chạy các listener nhận ContextStoppedEvent** được điều khiển bởi event multicaster và có thể áp dụng `@Order`.

Một listener `@Order(-100)` nhận `ContextStoppedEvent` không khiến nó chạy trước `Lifecycle.stop()` của tất cả bean. Nó chỉ được ưu tiên so với listener khác cùng nhận event.

Nếu một bean `SmartLifecycle` thực thi stop bất đồng bộ và không hoàn thành đúng thời hạn, processor có thể xử lý timeout. Vì vậy đừng coi sự kiện này là một bảo đảm tuyệt đối rằng mọi tài nguyên bên ngoài đã giải phóng thành công; cần quan sát tình trạng shutdown thực tế.

## 4. Hai cách lắng nghe ContextStoppedEvent

**Cách dùng @EventListener**: thuận tiện khi đang làm việc với Spring-managed bean.

```java
@Component
class StopAudit {
    @EventListener
    void whenStopped(ContextStoppedEvent event) {
        System.out.println("Stopped context: " +
                event.getApplicationContext().getId());
    }
}
```

Đây là trích đoạn minh họa: cần import `@Component`, `@EventListener`, `ContextStoppedEvent` và đặt bean trong application context. Mã đầy đủ ở mục 5 không cần component scanning.

**Cách dùng ApplicationListener**: phù hợp khi muốn thể hiện rõ kiểu event ở mức interface.

```java
@Component
class StopAuditListener implements ApplicationListener<ContextStoppedEvent> {
    @Override
    public void onApplicationEvent(ContextStoppedEvent event) {
        System.out.println("Context stopped");
    }
}
```

Cả hai cách đều có thể dùng. Trong ví dụ tối thiểu, chọn `@EventListener` cho dễ đọc. Đừng vừa đăng ký cùng một đối tượng bằng nhiều cơ chế nếu điều đó làm logic bị gọi trùng.

Vì event là một `ApplicationContextEvent`, nó mang **context nguồn**. Trong hệ thống có parent/child context, event có thể được chuyển lên parent và khiến listener ở parent nhìn thấy sự kiện phát từ child. Nếu xử lý chỉ dành cho một context nhất định, hãy kiểm tra `event.getApplicationContext()` thay vì ngầm cho rằng mọi event nhận được đều bắt nguồn từ context đang sở hữu listener.

## 5. Ví dụ Maven + Java 17 chạy được

Ví dụ dưới đây cho thấy:

- Sau khi khởi tạo, một bean `Lifecycle` thông thường chưa chạy.
- `context.start()` gọi `worker.start()` và phát `ContextStartedEvent`.
- `context.stop()` gọi `worker.stop()` rồi phát `ContextStoppedEvent`; listener thấy `worker.isRunning() == false`.
- Sau stop, context vẫn active và có thể start lại.
- `close()` ở cuối phát `ContextClosedEvent`, sau đó context kết thúc vòng đời.

Cấu trúc tệp:

```text
spring-context-stopped/
├── pom.xml
└── src/main/java/demo/ContextStoppedDemo.java
```

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-context-stopped</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.ContextStoppedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/ContextStoppedDemo.java`:

```java
package demo;

import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

public class ContextStoppedDemo {

    public static class Worker implements Lifecycle {
        private boolean running;

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("worker.start");
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("worker.stop");
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }
    }

    public static class Observers {
        private final Worker worker;

        public Observers(Worker worker) {
            this.worker = worker;
        }

        @EventListener
        public void onStarted(ContextStartedEvent event) {
            System.out.println("event.started; workerRunning=" + worker.isRunning());
        }

        @EventListener
        public void onStopped(ContextStoppedEvent event) {
            System.out.println("event.stopped; workerRunning=" + worker.isRunning());
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            System.out.println("event.closed");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Worker worker() {
            return new Worker();
        }

        @Bean
        Observers observers(Worker worker) {
            return new Observers(worker);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Worker worker = context.getBean(Worker.class);

            System.out.println("after refresh: running=" + worker.isRunning());

            context.start();
            context.stop();

            System.out.println("after stop: active=" + context.isActive()
                    + ", running=" + worker.isRunning());

            context.start();
            context.stop();
        }

        System.out.println("after try: context closed");
    }
}
```

Chạy trong thư mục `spring-context-stopped` khi đã có JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Đầu ra từ các lệnh `System.out.println` của chương trình (không tính log bên ngoài):

```text
after refresh: running=false
worker.start
event.started; workerRunning=true
worker.stop
event.stopped; workerRunning=false
after stop: active=true, running=false
worker.start
event.started; workerRunning=true
worker.stop
event.stopped; workerRunning=false
event.closed
after try: context closed
```

Giải thích:

1. `Worker` triển khai `Lifecycle` thông thường, không phải `SmartLifecycle` tự start, nên sau refresh vẫn `running=false`.
2. `context.start()` kích hoạt lifecycle processor: nó gọi `Worker.start()`, rồi Spring phát `ContextStartedEvent`. Listener nhận event in trạng thái `true`.
3. `context.stop()` gọi `Worker.stop()`, rồi phát `ContextStoppedEvent`. Listener in trạng thái `false`. Mã phía sau vẫn truy cập bean vì context chưa đóng.
4. `context.isActive()` vẫn là `true` sau stop, và hai lần `start()`/`stop()` đều hoạt động.
5. `try-with-resources` gọi `close()` khi ra khỏi khối. `ContextClosedEvent` được listener nhận trước khi context bị giải phóng hoàn toàn; đó là event khác với `ContextStoppedEvent`. Không có thêm một lời gọi stop tường minh trong ví dụ.

Nếu thay `Worker` bằng `SmartLifecycle` có `isAutoStartup() == true`, trạng thái ngay sau refresh và các dòng output sẽ khác vì worker có thể đã được start tự động. Đó là lý do ví dụ cố ý dùng `Lifecycle`.

## 6. So sánh ContextStoppedEvent với các event vòng đời khác

| Event | Cơ chế thường kích hoạt | Ý nghĩa | Context sau thao tác |
| --- | --- | --- | --- |
| `ContextRefreshedEvent` | `refresh()` hoặc khởi tạo context thành công | Bean factory và cơ chế context đã sẵn sàng | Active |
| `ContextStartedEvent` | `start()` | Các bean `Lifecycle` đã nhận tín hiệu start | Active, có thể chạy |
| `ContextStoppedEvent` | `stop()` | Các bean `Lifecycle` đã nhận tín hiệu stop | **Vẫn active, có thể start lại** |
| `ContextClosedEvent` | `close()`, shutdown hook | Context đang đóng, singleton bị hủy trong shutdown | Không thể dùng lại sau khi đóng |

Không dùng `ContextStoppedEvent` như một tên khác của `ContextClosedEvent`: hai sự kiện không có cùng trigger hay bảo đảm vòng đời.

Những phương thức cũng cần phân biệt:

- `context.isActive()`: phản ánh context đã refresh và chưa close, nên có thể **true sau stop**.
- `context.isRunning()`: phản ánh trạng thái lifecycle processor và các thành phần thuộc diện quản lý. Đây không phải phép kiểm tra "bean factory còn sử dụng được hay không".
- `worker.isRunning()`: trạng thái riêng của bean, do implementer quản lý.
- `context.close()`: kết thúc vòng đời và hủy bean; không dùng `start()` để hồi sinh cùng context sau close.

## 7. Những tình huống cần lưu ý trong sản xuất

### 7.1. Event listener có thể chạy đồng bộ, khiến stop bị chậm

Với `SimpleApplicationEventMulticaster` mặc định, các `@EventListener` thường được gọi ngay trong thread thực hiện `context.stop()`. Một listener `ContextStoppedEvent` thực hiện I/O chậm có thể kéo dài thời gian stop. `@Order` có thể định thứ tự các listener nhận event nhưng không thay đổi thứ tự dừng bean của `LifecycleProcessor`.

Nếu multicaster được cấu hình dùng executor bất đồng bộ hoặc phương thức dùng `@Async`, callback có thể chạy ở thread khác và không còn bảo đảm người gọi `stop()` chờ listener hoàn tất. Không dùng event async này như một hàng rào đồng bộ cho shutdown.

### 7.2. ContextStoppedEvent không thay thế việc implement stop()

Nếu một thành phần sở hữu thread, scheduler, consumer hoặc connection, phần dừng thật phải được đặt trong `Lifecycle.stop()` hoặc `SmartLifecycle.stop(Runnable)` (hay một cơ chế shutdown tương ứng). Listener nhận `ContextStoppedEvent` phù hợp với quan sát hoặc việc bổ sung không bắt buộc.

Đặt việc dừng tài nguyên cốt lõi duy nhất trong listener có thể dẫn tới tình huống hệ thống đóng context qua `close()` mà listener stopped không chạy, hoặc stop listener chạy sau các bean khác đã dừng, khi tài nguyên không còn sẵn sàng.

### 7.3. stop() và shutdown hook

`context.registerShutdownHook()` đăng ký đóng context khi JVM shutdown, theo cơ chế close. `@PreDestroy`, `DisposableBean.destroy()` và destruction callback xử lý hủy tài nguyên khi close. Một `ContextStoppedEvent` chỉ được gắn với đường đi stop phù hợp; đừng mặc định shutdown hook phát cả started/stopped events.

### 7.4. Lặp lại stop(), nhiều context và quan sát event

Mã ứng dụng nên tự bảo vệ trước các lệnh stop có thể xuất hiện hơn một lần. `Lifecycle.stop()` nên idempotent, và listener cũng không nên mặc định event luôn tương ứng với một lần dừng công việc mới. Nếu có parent/child context, kiểm tra `event.getApplicationContext()` để phân biệt context thực sự đã stop.

Một listener có thể dùng:

```java
@EventListener
public void onStopped(ContextStoppedEvent event) {
    String contextId = event.getApplicationContext().getId();
    // Ghi nhận contextId trong log hoặc metrics.
}
```

Đây là trích đoạn minh họa, có thể đặt trong Spring-managed bean; code chạy đầy đủ nằm ở mục 5.

### 7.5. Event không bảo đảm tài nguyên ngoài process đã dừng

Nhận `ContextStoppedEvent` nghĩa là context đang đi qua thao tác stop, nhưng không xác nhận tác vụ bên ngoài đã được xử lý hết, queue đã được drain, hoặc mọi callback async đã được xác nhận. Với `SmartLifecycle`, viết đúng `stop(Runnable callback)`, cấu hình timeout dừng hợp lý và giám sát thực tế các tài nguyên.

Nếu listener `ContextStoppedEvent` ném ngoại lệ trong chế độ đồng bộ mặc định, lỗi có thể tác động ngược đến lời gọi stop và những listener khác. Cần thiết kế chính sách lỗi phù hợp cho log/metrics và tránh làm listener vòng đời phụ thuộc hệ thống bên ngoài dễ lỗi.

## 8. Khi nào nên sử dụng?

Sử dụng `ContextStoppedEvent` khi cần **quan sát và phản ứng bổ sung** với một lần stop tường minh của `ApplicationContext`: ghi thời điểm dừng, cập nhật health/metric, hoặc ngăn phát sinh công việc mới trong một thành phần chỉ quan tâm đến dấu mốc vòng đời.

Nếu muốn dừng một bộ xử lý công việc có trạng thái, ưu tiên `Lifecycle`/`SmartLifecycle`. Nếu muốn dọn tài nguyên lúc ứng dụng thực sự kết thúc, ưu tiên destruction callback và xử lý `ContextClosedEvent`. Nếu muốn phản ứng với nghiệp vụ đặt hàng/thanh toán, tạo application event riêng.

Câu hỏi tự kiểm tra:

1. **`ContextStoppedEvent` xuất hiện khi nào?** Khi context nhận thao tác `stop()` theo cơ chế Spring.
2. **Sau stop có gọi lại `start()` được không?** Có, nếu context chưa bị close và triển khai hỗ trợ vòng đời thông thường.
3. **`ContextStoppedEvent` có tự hủy singleton bean không?** Không; việc hủy thuộc đường đi close.
4. **`@Order(-10)` trên listener stopped có khiến một `SmartLifecycle` dừng sớm hơn?** Không; ordering listener khác lifecycle phase.
5. **Shutdown hook chỉ gọi close thì có thể dựa vào ContextStoppedEvent không?** Không nên; lắng nghe `ContextClosedEvent` hoặc dùng lifecycle/destruction callback phù hợp.
6. **Làm sao biết context nào đã stop trong ứng dụng nhiều context?** Dùng `event.getApplicationContext()`.
7. **Tại sao listener stopped không nên làm tác vụ I/O nặng?** Có thể giữ thread đang gọi stop và làm đường shutdown chậm hoặc gặp lỗi ngoài ý muốn.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Standard Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [ContextStoppedEvent API (Spring 6.2.8)](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/ContextStoppedEvent.html)
- [AbstractApplicationContext API (Spring 6.2.8)](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [SmartLifecycle API (Spring 6.2.8)](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [DefaultLifecycleProcessor API (Spring 6.2.8)](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html)
