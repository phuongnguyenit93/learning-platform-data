# ContextStartedEvent trong vòng đời Spring ApplicationContext

## 1. ContextStartedEvent là gì?

`ContextStartedEvent` là một **sự kiện vòng đời có sẵn của Spring Framework**, thuộc package `org.springframework.context.event`. Nó được phát khi một `ConfigurableApplicationContext` được **start một cách tường minh** thông qua `start()`.

Ví dụ:

```java
ConfigurableApplicationContext context = ...;
context.start(); // Spring điều khiển Lifecycle beans, sau đó phát ContextStartedEvent.
```

Đoạn mã trên chỉ minh họa API; ví dụ Java chạy độc lập ở phần 5.

Ý nghĩa của từ “started” ở đây rất cụ thể: context chuyển **tín hiệu khởi chạy** đến những bean tham gia hợp đồng `Lifecycle`. Event không đồng nghĩa với “JVM vừa chạy”, “Spring Boot đã sẵn sàng nhận request” hoặc “mọi bean vừa được khởi tạo lần đầu”.

Điểm quan trọng nhất:

> **Chỉ khởi tạo/refresh context không mặc nhiên làm phát `ContextStartedEvent`.** Trong cách dùng thông thường, event này gắn với lời gọi `context.start()`, không phải với một lần `refresh()` hay với việc Spring Boot tự khởi động ứng dụng.

`ContextStartedEvent` thích hợp khi ứng dụng có quy trình **start / stop / start lại** những thành phần được quản lý qua `Lifecycle` và cần một tín hiệu sau bước start để kích hoạt việc phối hợp, quan sát trạng thái hoặc ghi nhận hoạt động.

## 2. Đặt ContextStartedEvent vào bức tranh vòng đời

Spring Framework có các event vòng đời context thường gặp:

| Event | Nguồn phát điển hình | Ý nghĩa |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context được khởi tạo hoặc hoàn tất `refresh()` | Bean factory, singleton và hạ tầng context đã sẵn sàng sau refresh |
| **`ContextStartedEvent`** | Gọi `ConfigurableApplicationContext.start()` | Context đã thực hiện bước start các bean `Lifecycle` liên quan |
| `ContextStoppedEvent` | Gọi `ConfigurableApplicationContext.stop()` | Context đã thực hiện bước stop các bean `Lifecycle` liên quan |
| `ContextClosedEvent` | Gọi `close()` hoặc shutdown hook dẫn tới đóng context | Context đang được đóng; các bean sẽ được hủy theo quy trình đóng |

Một chuỗi thao tác *có chủ ý* có thể là:

```text
new AnnotationConfigApplicationContext(Config.class)
                  |
                  v
              refresh()
                  |
                  v
        ContextRefreshedEvent
                  |
                  | context.start()
                  v
        Lifecycle beans: start()
                  |
                  v
         ContextStartedEvent
                  |
                  | context.stop()
                  v
         Lifecycle beans: stop()
                  |
                  v
         ContextStoppedEvent
                  |
                  | context.start()
                  v
        Lifecycle beans: start()
                  |
                  v
         ContextStartedEvent
                  |
                  | context.close()
                  v
         ContextClosedEvent
                  |
                  v
          đóng/hủy bean context
```

Đây là **sơ đồ những lời gọi tường minh**, không phải trình tự bắt buộc cho mọi ứng dụng Spring. Một ứng dụng chỉ `refresh()` rồi `close()` có thể không bao giờ có `ContextStartedEvent`. Việc `close()` ngừng các thành phần vẫn đang chạy là một phần của quy trình đóng context; nó **không tương đương** với việc chủ động gọi `stop()` để phát một `ContextStoppedEvent` rồi vẫn giữ context hoạt động.

### Phân biệt start, stop và close

- `start()`: truyền tín hiệu start cho các bean `Lifecycle` phù hợp; context vẫn hoạt động và có thể `stop()` sau đó.
- `stop()`: truyền tín hiệu stop, nhưng **không hủy bean singleton** và thông thường có thể `start()` lại.
- `close()`: kết thúc vòng đời context, giải phóng/hủy bean; không dùng `start()` để hồi sinh một context đã đóng.

Vì vậy, “đã stop” không có nghĩa “đã shutdown toàn bộ Spring container”; còn “đã close” là trạng thái kết thúc vòng đời.

## 3. Spring tạo và phát ContextStartedEvent như thế nào?

`ContextStartedEvent` kế thừa `ApplicationContextEvent`, vốn kế thừa `ApplicationEvent`. Nó chứa nguồn là `ApplicationContext` được start:

```java
import org.springframework.context.event.ContextStartedEvent;

ContextStartedEvent event = ...;
var startedContext = event.getApplicationContext();
long eventTimestamp = event.getTimestamp();
```

Đây là đoạn minh họa về dữ liệu event, không phải chương trình chạy độc lập. `getApplicationContext()` giúp xác định context phát event, đặc biệt hữu ích trong ứng dụng có context cha/con.

Ở các triển khai context tiêu chuẩn dựa trên `AbstractApplicationContext`, cách hiểu luồng đi là:

1. Ứng dụng gọi `ConfigurableApplicationContext.start()`.
2. Context yêu cầu `LifecycleProcessor.start()` điều phối các bean `Lifecycle`.
3. Sau khi bước start hoàn tất bình thường, context công bố `new ContextStartedEvent(this)` qua cơ chế application event.
4. Những `ApplicationListener<ContextStartedEvent>` hoặc phương thức `@EventListener` nhận đúng kiểu event được thông báo.

Các bean `Lifecycle` được quản lý theo quy tắc phase, dependencies và trạng thái `isRunning()` của `LifecycleProcessor` tương ứng. Không nên hiểu “mọi bean Spring” đều có phương thức start được gọi: chỉ những bean tham gia hợp đồng vòng đời mới có ý nghĩa start/stop ở bước này.

Nếu một `Lifecycle.start()` ném lỗi khiến lời gọi start không hoàn tất, **không được mặc định kỳ vọng** `ContextStartedEvent` đã phát. Ngược lại, nếu một listener của `ContextStartedEvent` ném lỗi trong chế độ đồng bộ, `start()` có thể ném exception **sau khi** một số bean đã bắt đầu chạy. Cần giám sát cả hai loại thất bại.

### Event không tự sinh ra chỉ nhờ khai báo listener

Đoạn sau **không** ép Spring phát event khi ứng dụng vừa boot:

```java
@EventListener
public void afterStarted(ContextStartedEvent event) {
    System.out.println("Context explicitly started");
}
```

Phương thức chỉ được gọi nếu context thực sự phát `ContextStartedEvent`. Chỉ đặt annotation không tạo thêm lời gọi `start()`.

## 4. Lifecycle và SmartLifecycle khác nhau ở đâu?

Để hiểu khi nào cần `ContextStartedEvent`, cần phân biệt hai hợp đồng vòng đời bean.

### 4.1. Lifecycle

`org.springframework.context.Lifecycle` khai báo:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Đoạn trên mô tả hợp đồng API. Bean triển khai `Lifecycle` thông thường nhận start/stop khi context được điều khiển tường minh. Khi `start()` được gọi, bean nên đạt trạng thái “running” và báo `isRunning() == true`; khi `stop()` thành công, chuyển về false.

Các phương thức nên **idempotent về hiệu ứng**: nhận lệnh start khi đã chạy hoặc stop khi đã dừng không nên vô tình mở thêm tài nguyên, tạo hai consumer trùng nhau hay ném lỗi chỉ vì trạng thái đã đúng.

### 4.2. SmartLifecycle

`org.springframework.context.SmartLifecycle` mở rộng `Lifecycle`, thêm các đặc tính như:

- `isAutoStartup()`: có tự khởi động trong lần `refresh()` hay không.
- `getPhase()`: giai đoạn/độ ưu tiên tương đối khi start/stop.
- `stop(Runnable callback)`: cơ chế phối hợp ngừng bất đồng bộ; implementation phải gọi callback khi hoàn tất để container không chờ vô ích.

**Khác biệt mấu chốt:** `SmartLifecycle` với `isAutoStartup() == true` có thể được kích hoạt trong **bước refresh**, trước `ContextRefreshedEvent`, thông qua lifecycle processor. Việc tự start này **không biến refresh thành một lời gọi `ConfigurableApplicationContext.start()`**, nên bản thân nó không làm phát `ContextStartedEvent`.

Khi ứng dụng sau đó gọi `context.start()` tường minh, `ContextStartedEvent` có thể vẫn phát; những bean đã running sẽ được bộ điều phối bỏ qua hoặc xử lý theo trạng thái. Event biểu thị **thao tác start của context**, không phải chứng cứ một bean cụ thể vừa đổi từ stopped sang running.

| Trường hợp | Bean có thể chạy? | Có ContextStartedEvent do riêng thao tác đó? |
| --- | --- | --- |
| `refresh()`, bean `Lifecycle` thông thường | Thường chưa start nhờ lifecycle processor | **Không** |
| `refresh()`, `SmartLifecycle.isAutoStartup() == true` | Có, nếu start thành công | **Không** |
| `context.start()` | Các bean `Lifecycle` được yêu cầu start | **Có**, nếu thao tác hoàn tất bình thường |
| `context.stop()` | Các bean `Lifecycle` được yêu cầu stop | **Không**; có `ContextStoppedEvent` |
| `context.close()` | Các tài nguyên context được đóng/hủy | **Không**; có `ContextClosedEvent` |

Khi mục tiêu là chạy một consumer hoặc một adapter ngay trong lúc container khởi tạo, có thể dùng `SmartLifecycle` phù hợp. Khi mục tiêu là **quan sát một thao tác start tường minh**, dùng `ContextStartedEvent`.

## 5. Ví dụ Java 17+ chạy được: refresh, start, stop, start lại

Ví dụ này dùng **Spring Framework 6.2.12**, Maven và Java 17+. Một bean `WorkerService` triển khai `Lifecycle`; một bean khác lắng nghe các event vòng đời. Chương trình chủ động gọi `start()` rồi `stop()` hai lần để thấy rằng event không chỉ xảy ra một lần trong đời ứng dụng.

Cấu trúc dự án:

```text
context-started-demo/
├── pom.xml
└── src/main/java/demo/ContextStartedDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-started-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ContextStartedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ContextStartedDemo.java`:

```java
package demo;

import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

public class ContextStartedDemo {

    public static class WorkerService implements Lifecycle {
        private boolean running;

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("WORKER START");
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("WORKER STOP");
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }
    }

    public static class LifecycleEvents {
        private final WorkerService worker;

        public LifecycleEvents(WorkerService worker) {
            this.worker = worker;
        }

        @EventListener
        public void onRefresh(ContextRefreshedEvent event) {
            System.out.println("EVENT REFRESHED");
        }

        @EventListener
        public void onStart(ContextStartedEvent event) {
            System.out.println("EVENT STARTED running=" + worker.isRunning());
        }

        @EventListener
        public void onStop(ContextStoppedEvent event) {
            System.out.println("EVENT STOPPED running=" + worker.isRunning());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public WorkerService workerService() {
            return new WorkerService();
        }

        @Bean
        public LifecycleEvents lifecycleEvents(WorkerService worker) {
            return new LifecycleEvents(worker);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            context.start();
            context.stop();
            context.start();
            context.stop();
        }
    }
}
```

Từ thư mục có `pom.xml`, chạy:

```bash
mvn -q compile exec:java
```

Kết quả từ các lệnh `System.out.println` của chương trình (không tính log nội bộ tùy môi trường):

```text
EVENT REFRESHED
WORKER START
EVENT STARTED running=true
WORKER STOP
EVENT STOPPED running=false
WORKER START
EVENT STARTED running=true
WORKER STOP
EVENT STOPPED running=false
```

Giải thích từng giai đoạn:

1. Constructor `new AnnotationConfigApplicationContext(Config.class)` đăng ký cấu hình rồi `refresh()`. Các listener `@EventListener` được đăng ký đúng thời điểm để nhận `ContextRefreshedEvent`. `WorkerService` chỉ là `Lifecycle` thông thường, không phải `SmartLifecycle` tự khởi động, nên chưa in `WORKER START`.
2. `context.start()` gọi lifecycle processor. `WorkerService.start()` chuyển `running` sang true và in `WORKER START`. Sau đó `ContextStartedEvent` được phát; listener quan sát `running=true`.
3. `context.stop()` dừng bean, rồi phát `ContextStoppedEvent`. Listener thấy `running=false`. Bean chưa bị hủy.
4. Lặp lại `start()`/`stop()` tạo thêm một cặp event và dòng log; điều này chứng minh event gắn với **thao tác start/stop**, không phải sự kiện chỉ phát đúng một lần suốt đời.
5. `try-with-resources` gọi `close()` khi kết thúc. Vì trong ví dụ bean đã được stop, việc đóng không in thêm `WORKER STOP`. Chương trình không đăng ký listener cho `ContextClosedEvent`.

Kết quả trên giả định multicaster mặc định **đồng bộ** như cấu hình ví dụ. Nếu ứng dụng tự cấu hình executor bất đồng bộ, thứ tự thời điểm listener in log có thể thay đổi.

## 6. Hai cách nghe ContextStartedEvent

### Cách 1: @EventListener

Đây là cách thường dễ đọc nhất trong Spring beans:

```java
@Component
public class ContextStartObserver {
    @EventListener
    public void onContextStarted(ContextStartedEvent event) {
        System.out.println(
                "Started context: " + event.getApplicationContext().getId());
    }
}
```

Đoạn này để đặt trong một dự án Spring có component scan; cần import `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener` và `ContextStartedEvent`.

Ưu điểm: không cần triển khai interface listener; một bean có thể chứa nhiều phương thức `@EventListener` cho những event khác nhau.

### Cách 2: ApplicationListener<ContextStartedEvent>

```java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextStartedEvent;

public final class ContextStartAudit
        implements ApplicationListener<ContextStartedEvent> {

    @Override
    public void onApplicationEvent(ContextStartedEvent event) {
        System.out.println(
                "Started context: " + event.getApplicationContext().getId());
    }
}
```

Đây là class độc lập về mặt cú pháp nhưng cần được **đăng ký làm bean hoặc listener trong ApplicationContext** để Spring gọi. Chẳng hạn khai báo `@Bean` trả về `ContextStartAudit`, hoặc đăng ký một `ApplicationListener` với context thích hợp trước khi event được phát.

| Tiêu chí | `@EventListener` | `ApplicationListener<ContextStartedEvent>` |
| --- | --- | --- |
| Cách khai báo | Annotation lên phương thức của bean | Interface generic của class |
| Kiểu event | Suy ra từ tham số phương thức | Nằm trong generic type |
| Nhiều handler trong một bean | Thuận tiện | Cần cân nhắc nhiều interface/ủy quyền |
| Trường hợp phù hợp | Application services, audit, observers | Listener class thuần, đăng ký programmatic hoặc hạ tầng |

Cả hai cách đều dựa trên **cùng cơ chế Spring Application Events**. Không cần tự gọi `publishEvent(new ContextStartedEvent(...))` để mô phỏng vòng đời thật; việc tự publish event chỉ phát thông báo, **không chạy `LifecycleProcessor.start()`**.

## 7. ContextStartedEvent không phải sự kiện “ứng dụng Spring Boot đã sẵn sàng”

Đây là một trong những nhầm lẫn phổ biến nhất.

Trong Spring Boot có một loại tên gần giống:

`org.springframework.boot.context.event.ApplicationStartedEvent`

Nó do **Spring Boot** phát trong quy trình `SpringApplication.run(...)`, sau khi application context đã refresh nhưng trước khi chạy `ApplicationRunner` và `CommandLineRunner`. Còn `ApplicationReadyEvent` là mốc muộn hơn, sau các runner, nhằm báo hiệu ứng dụng đã sẵn sàng phục vụ theo tiến trình khởi động Boot.

Ba ý nghĩa khác nhau:

| Tín hiệu | Thuộc | Khi nào thường xảy ra | Dùng cho |
| --- | --- | --- | --- |
| `ContextStartedEvent` | Spring Framework | Gọi tường minh `ConfigurableApplicationContext.start()` | Quan sát start/restart các bean Lifecycle |
| `ApplicationStartedEvent` | Spring Boot | Sau refresh, trước các runner | Quan sát giai đoạn khởi động Boot |
| `ApplicationReadyEvent` | Spring Boot | Sau các runner, cuối tiến trình start Boot | Công việc cần ứng dụng đã sẵn sàng |

**Không thể đổi tên một loại thành loại khác.** Chúng là các lớp khác nhau, với điều kiện phát khác nhau.

Ví dụ, nếu muốn ghi log khi ứng dụng Spring Boot đã sẵn sàng:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;

@EventListener
public void ready(ApplicationReadyEvent event) {
    // Thực hiện việc nhẹ, phù hợp với mốc Boot đã ready.
}
```

Đây chỉ là đoạn phương thức để đặt trong một Spring bean của ứng dụng **Spring Boot**, không chạy độc lập với `spring-context` trong ví dụ ở mục 5.

Nếu bạn đăng ký `@EventListener(ContextStartedEvent.class)` trong ứng dụng Boot nhưng không có ai gọi `context.start()`, đừng kỳ vọng listener sẽ chạy khi Boot hoàn tất khởi động.

## 8. Khi nào nên dùng ContextStartedEvent?

### 8.1. Quan sát một vòng start có chủ đích

Một ứng dụng có thể cho phép tạm dừng và tiếp tục nhận dữ liệu bằng cách điều khiển các `Lifecycle` beans. Nếu cần ghi log/metric sau mỗi lần context start, một listener `ContextStartedEvent` là lựa chọn hợp lý.

### 8.2. Phối hợp thành phần sau bước start

Giả sử vài thành phần tham gia `LifecycleProcessor`. Sau khi start hoàn tất, một observer có thể ghi nhận “context đã nhận và hoàn tất lệnh start” để cập nhật trạng thái vận hành hoặc phát tín hiệu giám sát nội bộ.

Tuy nhiên, nếu phải **bảo đảm một bean khác đã thực sự sẵn sàng xử lý request**, event chung chưa đủ. Hãy kiểm tra health/readiness thực tế của bean hoặc mô hình hóa dependencies và các giai đoạn `SmartLifecycle` phù hợp.

### 8.3. Thống kê số lần khởi chạy lại

Vì context có thể được stop rồi start lại, listener có thể đếm số lần nhận `ContextStartedEvent`. Phân biệt việc **gọi start** với việc **một worker thật sự chuyển trạng thái**: một lần start của context không có nghĩa mọi bean đều thay đổi trạng thái.

### 8.4. Khi không nên dùng

Không dùng `ContextStartedEvent` như một thay thế mặc định cho:

- Khởi tạo dữ liệu sau khi bean factory sẵn sàng: xem xét `ContextRefreshedEvent` và cơ chế khởi tạo có phù hợp.
- Tác vụ cần chạy khi Spring Boot ready: xem xét `ApplicationReadyEvent`.
- Khởi động/dừng tài nguyên gắn với bean: ưu tiên triển khai `Lifecycle` / `SmartLifecycle` hoặc callback khởi tạo/hủy phù hợp.
- Bắt buộc thực hiện công việc một lần duy nhất: event có thể xuất hiện nhiều lần khi context được start nhiều lần; cần cơ chế đánh dấu idempotency rõ ràng.
- Điều khiển hệ thống nhiều instance hoặc có restart tiến trình: event chỉ tồn tại trong phạm vi application context của một tiến trình, không phải thông điệp điều phối bền vững.

## 9. Vòng đời context cha/con và lọc event đúng nguồn

Trong ứng dụng có **parent/child ApplicationContext**, một event từ context con có thể được truyền tới listener của context cha. Do đó, một listener ở cha có thể thấy `ContextStartedEvent` với nguồn là **context con**, dù người đọc code tưởng listener chỉ quan tâm context cha.

Dùng `event.getApplicationContext()` để kiểm tra nguồn khi cần:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.EventListener;

public class LocalContextObserver {

    private final ApplicationContext ownContext;

    public LocalContextObserver(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onStarted(ContextStartedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return; // Sự kiện của context khác, ví dụ context con.
        }
        // Chỉ xử lý context mà bean này thuộc về.
    }
}
```

Đoạn trên là mẫu minh họa, cần đăng ký `LocalContextObserver` làm bean và cung cấp đúng `ownContext` của context chứa bean. Nếu một context có nhiều observer hoặc tên context dễ trùng, so sánh tham chiếu đối tượng như ví dụ đáng tin hơn chỉ so sánh chuỗi `getId()`.

Việc phát event trong hierarchy không có nghĩa Spring sẽ tự động start/stop context cha khi gọi start/stop context con. Cần quản lý lifecycle từng context theo hệ thống đang dùng.

## 10. Xử lý lỗi và bất đồng bộ khi nhận ContextStartedEvent

### 10.1. Đồng bộ là mặc định thông thường

Với `SimpleApplicationEventMulticaster` mặc định, listener thường chạy đồng bộ trên thread gọi `start()`. Nếu listener ném `RuntimeException` và multicaster không có cơ chế xử lý lỗi để suppress, exception có thể lan ra khỏi `start()`.

Tình huống này nhạy cảm vì bước `LifecycleProcessor.start()` có thể đã khởi chạy các bean trước khi listener thất bại. Không nên coi exception từ listener như bảo đảm container đã tự rollback toàn bộ những gì vừa start.

Hướng xử lý:

1. Chỉ làm việc nhẹ, xác định được thời gian trong listener vòng đời.
2. Với lỗi có thể phục hồi, ghi log/metric có correlation phù hợp.
3. Nếu listener là bước thiết yếu để component chạy an toàn, hãy thiết kế công việc đó trong chính hợp đồng start/dependency hoặc quy trình orchestration rõ ràng.
4. Không suppress lỗi tùy tiện để che trạng thái sẵn sàng không chính xác.

### 10.2. Listener async có khác biệt

Spring có thể dùng executor trong multicaster hoặc `@Async` để xử lý một số listener bất đồng bộ. Khi đó:

- `ContextStartedEvent` vẫn do thao tác start phát ra, nhưng thời điểm **listener hoàn thành** có thể đến sau khi `context.start()` trả về.
- Không được đọc một log “event đã được phát” như bằng chứng mọi tác vụ async bên trong listener đã xong.
- Lỗi trong task async có thể không truyền ngược về caller theo cùng cách như listener đồng bộ.
- Context truyền vào event không làm tự động mang transaction/security/MDC của thread publisher sang thread mới.

Nếu observer cần đồng bộ hóa nghiêm ngặt với việc start, nên đánh giá xem bất đồng bộ có phù hợp không, hoặc xây dựng barrier/phép chờ có timeout theo nhu cầu thực tế.

### 10.3. Không tự gắn transaction semantics

`ContextStartedEvent` không phải `@TransactionalEventListener` tự động sau commit. Nó thuộc vòng đời Spring context; việc nhận event không chứng minh có một transaction vừa commit. Nếu logic listener ghi database, cần quản lý transaction tại nơi làm việc đó.

## 11. SmartLifecycle phù hợp hơn khi cần điều khiển tài nguyên

Khi yêu cầu là mở hoặc đóng một message consumer, scheduler, socket hoặc kết nối dài hạn, hãy dùng `Lifecycle`/`SmartLifecycle` để quản lý **tài nguyên**, còn `ContextStartedEvent` để quan sát **mốc vòng đời context**.

Một mẫu `SmartLifecycle` rút gọn:

```java
import org.springframework.context.SmartLifecycle;

public final class MessageConsumerLifecycle implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        if (!running) {
            // Mở consumer theo cách phù hợp với ứng dụng.
            running = true;
        }
    }

    @Override
    public void stop() {
        running = false;
        // Dừng consumer theo cách phù hợp với ứng dụng.
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run(); // Báo cho lifecycle processor đã hoàn tất.
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 0;
    }
}
```

Đây là **mẫu implementation minh họa**; mã comment chỉ vị trí mở/dừng consumer, chưa tích hợp một broker thật. Khi cần dừng async, chỉ gọi `callback.run()` sau khi tác vụ dừng đã hoàn thành; ví dụ trên giả định stop đồng bộ. Triển khai thật phải bảo vệ state, xử lý timeout, exception và lệnh start/stop đồng thời.

Lưu ý quan trọng: Với `isAutoStartup() == true`, Spring có thể gọi `start()` ngay khi refresh. Khi đó `MessageConsumerLifecycle` đã chạy nhưng **chưa hề có `ContextStartedEvent`**. Sử dụng `ContextStartedEvent` để tự suy ra consumer có hoạt động hay không sẽ sai trong trường hợp này. Muốn biết, hãy hỏi `isRunning()` hoặc health của consumer.

## 12. Thiết kế listener an toàn và có thể kiểm thử

### 12.1. Không giả định event chỉ phát một lần

Bất kỳ nơi nào gọi `context.start()` đều có thể dẫn đến một event tiếp theo. Nếu listener tạo job, đăng ký resource hoặc gửi thông báo, cần kiểm soát trùng lặp:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.EventListener;

public class OncePerContextObserver {
    private final AtomicBoolean completed = new AtomicBoolean();

    @EventListener
    public void onStarted(ContextStartedEvent event) {
        if (!completed.compareAndSet(false, true)) {
            return;
        }
        // Công việc chỉ muốn thử một lần trong vòng đời bean này.
    }
}
```

Đây là đoạn minh họa cho một **cờ chỉ chạy một lần trong một instance bean**, không phải bảo đảm exactly-once trên nhiều tiến trình. Nếu công việc có thể thất bại cần retry, việc đổi cờ trước khi hoàn thành cũng phải được thiết kế lại. Đặc biệt không dùng cờ này nếu yêu cầu thực tế là thực thi **mỗi lần start lại**.

### 12.2. Một số test case quan trọng

| Kịch bản | Thao tác | Điều cần xác minh |
| --- | --- | --- |
| Chỉ refresh | Tạo `AnnotationConfigApplicationContext(Config.class)` | Nhận `ContextRefreshedEvent` nhưng **chưa** nhận `ContextStartedEvent` |
| Start lần đầu | `context.start()` | `Lifecycle.start()` được gọi và `ContextStartedEvent` được nhận |
| Stop | `context.stop()` | `Lifecycle.stop()` được gọi, nhận `ContextStoppedEvent` |
| Start sau stop | `context.start()` lần nữa | Có một `ContextStartedEvent` mới |
| Close | `context.close()` | Nhận `ContextClosedEvent` nếu đăng ký; context đã kết thúc vòng đời |
| SmartLifecycle auto startup | `refresh()` với bean autoStartup | Bean có thể running mà chưa có `ContextStartedEvent` |
| Listener ném exception | Dùng multicaster đồng bộ mặc định | Xác định exception có lan ra khỏi `start()` không và bean đang running ra sao |
| Context cha/con | Start riêng context con | Listener cha có thể thấy event nguồn con; lọc bằng `getApplicationContext()` |

### 12.3. Kiểm thử bằng ApplicationContext thuần

Trong kiểm thử, nên giữ một recorder có thể đếm số event, thay vì chỉ assert một dòng log. Một recorder cho `ContextStartedEvent` có thể viết như sau:

```java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextStartedEvent;

public final class StartRecorder
        implements ApplicationListener<ContextStartedEvent> {

    private final AtomicInteger count = new AtomicInteger();

    @Override
    public void onApplicationEvent(ContextStartedEvent event) {
        count.incrementAndGet();
    }

    public int count() {
        return count.get();
    }
}
```

Đoạn này là class hỗ trợ test; cần được đăng ký làm listener/bean trước khi start context. Với multicaster đồng bộ, một phép kiểm tra phù hợp là:

```java
// Giả định recorder đã được đăng ký trong context từ trước.
context.start();
assertEquals(1, recorder.count()); // JUnit assertion minh họa.
context.stop();
context.start();
assertEquals(2, recorder.count());
```

Hai dòng `assertEquals` chỉ minh họa test JUnit, không thuộc chương trình chạy độc lập ở phần 5. Nếu multicaster được cấu hình async, dùng cơ chế chờ có thời hạn thay vì giả định sự kiện đã được listener xử lý ngay khi `start()` trả về.

## 13. Những lỗi hay gặp

1. **Nghe ContextStartedEvent để biết Spring Boot đã khởi động xong.** Boot có lifecycle event riêng; listener loại này thường không chạy nếu không gọi `context.start()`.
2. **Nhầm refresh với start.** `ContextRefreshedEvent` có thể xảy ra khi tạo context; `ContextStartedEvent` cần thao tác start tường minh.
3. **Thấy SmartLifecycle chạy nhưng không thấy ContextStartedEvent rồi nghĩ Spring lỗi.** SmartLifecycle auto startup ở refresh là luồng khác.
4. **Dùng ContextStartedEvent để start chính component cốt lõi.** Thường nên đưa start/stop vào `Lifecycle`/`SmartLifecycle`, để lifecycle processor điều phối đúng thứ tự.
5. **Không bảo vệ trước event lặp.** Stop rồi start có thể dẫn đến thêm event; listener phải quyết định có chạy mỗi lần hay chỉ một lần.
6. **Nhầm stop với close.** `stop()` cho phép start lại; `close()` hủy context và kết thúc vòng đời.
7. **Không phân biệt context cha/con.** Listener cha có thể thấy event từ con; nếu cần xử lý theo một context cụ thể, dùng nguồn của event.
8. **Giả định ContextStartedEvent bảo đảm tất cả service bên ngoài healthy.** Lifecycle bean có thể đặt running=true trước khi downstream thật sự sẵn sàng; cần kiểm tra readiness riêng.
9. **Nuốt lỗi listener trong thao tác start.** Có thể tạo trạng thái không nhất quán giữa việc thực thi các bean và phần quan sát/phụ trợ.
10. **Cho rằng event nội bộ có retry và lưu bền vững.** Spring Application Events không phải message broker; restart JVM làm mất state trong bộ nhớ.
11. **Tạo event ContextStartedEvent bằng tay để “khởi động context”.** Tự publish chỉ gửi thông báo, không gọi các bean `Lifecycle.start()`.
12. **Cho rằng callback onStart luôn chạy trong thread publisher.** Điều này đúng theo multicaster đồng bộ mặc định, nhưng cần kiểm tra khi cấu hình executor hoặc `@Async`.

## 14. Checklist chọn đúng công cụ vòng đời

Trước khi dùng `ContextStartedEvent`, hãy trả lời:

- Điều tôi muốn biết có thật sự là **context vừa được gọi `start()`** không?
- Hay tôi muốn biết bean factory vừa refresh, hoặc Spring Boot đã sẵn sàng?
- Component cần được điều khiển start/stop có nên tự triển khai `Lifecycle` hoặc `SmartLifecycle` không?
- Listener sẽ chạy ở mỗi lần start lại, hay chỉ một lần cho mỗi instance?
- Hệ thống có context cha/con cần lọc theo `event.getApplicationContext()` không?
- Listener có công việc nặng cần tránh chặn `start()` không? Nếu async, có cần chờ kết quả?
- Sự kiện chỉ dùng để quan sát, hay đang bị dùng như một cơ chế đảm bảo business transaction?
- Đã kiểm thử `refresh → start → stop → start → close` và trường hợp listener lỗi chưa?

**Kết luận thực hành:** `ContextStartedEvent` là tín hiệu **sau lời gọi start tường minh của Spring ApplicationContext**. Dùng nó để theo dõi hoặc phối hợp với thao tác start/stop có chủ đích. Khi nhu cầu là auto-start một bean, điều khiển tài nguyên hoặc xác nhận ứng dụng Boot sẵn sàng, hãy chọn đúng hợp đồng `SmartLifecycle`, `ContextRefreshedEvent` hoặc event Boot tương ứng.

## Tài liệu tham khảo

- [Spring Framework Reference — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Customizing the Nature of a Bean (Lifecycle and SmartLifecycle)](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [ContextStartedEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/context/event/ContextStartedEvent.html)
- [AbstractApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Spring Boot ApplicationStartedEvent Javadoc](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/context/event/ApplicationStartedEvent.html)
