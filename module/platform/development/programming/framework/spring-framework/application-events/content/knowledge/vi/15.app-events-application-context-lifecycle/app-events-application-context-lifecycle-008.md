# Sự kiện khi start và stop `ApplicationContext` trong Spring Framework

## 1. Khái niệm: start, stop, refresh và close không phải một thao tác

`ApplicationContext` là IoC container quản lý bean, dependency injection và Application Events. Một context có thể được **khởi tạo (`refresh`)**, nhận **tín hiệu bắt đầu (`start`)**, nhận **tín hiệu dừng (`stop`)** rồi **đóng và hủy bean (`close`)**. Spring phát những sự kiện khác nhau cho các mốc này. Hiểu đúng chúng giúp bạn điều khiển worker, consumer, scheduler, kết nối dài hạn và tài nguyên nền theo vòng đời ứng dụng.

Trong Spring Framework, hai sự kiện trực tiếp của đề bài là:

- **`ContextStartedEvent`**: được phát khi gọi `start()` trên `ConfigurableApplicationContext`. Spring chuyển tín hiệu bắt đầu đến các bean `Lifecycle` phù hợp.
- **`ContextStoppedEvent`**: được phát khi gọi `stop()` trên `ConfigurableApplicationContext`. Spring chuyển tín hiệu dừng đến các bean `Lifecycle` đang chạy.

Hai sự kiện này **không phải** mặc định xuất hiện mỗi khi ứng dụng khởi động hoặc kết thúc. `AnnotationConfigApplicationContext` thường `refresh()` ngay trong constructor được sử dụng ở ví dụ, phát `ContextRefreshedEvent`, **không tự phát `ContextStartedEvent` chỉ vì đã refresh**. Khi gọi `close()`, Spring phát **`ContextClosedEvent`** rồi xử lý dừng/hủy bean; **không được mặc định kỳ vọng sẽ nhận `ContextStoppedEvent` khi chỉ gọi `close()`**.

Một chi tiết quan trọng: `stop()` không hủy bean hoặc đóng context. Sau `stop()`, context vẫn có thể `start()` lại. Ngược lại, context đã `close()` không thể được start/restart như trước; cần tạo context mới.

## 2. Bảng so sánh bốn sự kiện vòng đời

| Event | Tác nhân phổ biến | Ý nghĩa chính | Có thể tiếp tục sử dụng context? |
| --- | --- | --- | --- |
| `ContextRefreshedEvent` | `refresh()` / constructor tự refresh | Bean definitions được xử lý, context hoàn tất khởi tạo hoặc refresh | Có |
| `ContextStartedEvent` | `ConfigurableApplicationContext.start()` | Yêu cầu các bean `Lifecycle` bắt đầu hoặc tiếp tục chạy | Có |
| `ContextStoppedEvent` | `ConfigurableApplicationContext.stop()` | Yêu cầu các bean `Lifecycle` dừng hoạt động | Có; có thể `start()` lại |
| `ContextClosedEvent` | `close()` hoặc shutdown hook phù hợp | Context bước vào quy trình đóng, dừng thành phần và hủy singleton | Không |

Các class nằm trong package `org.springframework.context.event`. Chúng kế thừa `ApplicationContextEvent`, có thể lấy context phát sự kiện bằng `event.getApplicationContext()`.

**Không đánh đồng tên:** `ContextStartedEvent` thuộc **Spring Framework**, còn `ApplicationStartedEvent` thuộc **Spring Boot**. Đây là hai loại event khác nhau, có điều kiện phát và vị trí trong lifecycle khác nhau. Một ứng dụng Boot có thể nhận `ApplicationStartedEvent` mà không hề gọi `applicationContext.start()`.

## 3. Luồng xử lý bên trong Spring

Với `AbstractApplicationContext` và `LifecycleProcessor` mặc định, luồng chính có thể hình dung như sau:

```text
Tạo / refresh context
  ├─ tạo và khởi tạo các bean
  ├─ đăng ký ApplicationListener / phương thức @EventListener
  ├─ LifecycleProcessor.onRefresh()
  │    └─ tự start các SmartLifecycle có isAutoStartup() = true
  └─ publish ContextRefreshedEvent

context.start()
  ├─ LifecycleProcessor.start()
  │    └─ start những Lifecycle bean cần chạy
  └─ publish ContextStartedEvent

context.stop()
  ├─ LifecycleProcessor.stop()
  │    └─ stop những Lifecycle bean đang chạy
  └─ publish ContextStoppedEvent

context.start()        (có thể gọi lại nếu context chưa close)
  ├─ LifecycleProcessor.start()
  └─ publish ContextStartedEvent

context.close()
  ├─ publish ContextClosedEvent
  ├─ LifecycleProcessor.onClose()
  │    └─ dừng Lifecycle bean còn chạy
  └─ hủy singleton / đóng tài nguyên container
```

Đây là mô tả đường đi bình thường của một context đơn lẻ và một số bước chính, không phải toàn bộ implementation. Thứ tự listener có thể chịu ảnh hưởng bởi cấu hình multicaster, listener order, bean dependency và listener bất đồng bộ.

Sự kiện `ContextStartedEvent` được phát **sau khi lệnh start lifecycle hoàn tất theo cơ chế của processor**; tương tự `ContextStoppedEvent` phát sau lời gọi stop trên processor. Nhưng nếu `SmartLifecycle.stop(Runnable callback)` tự dừng bất đồng bộ, bạn cần bảo đảm gọi callback báo hoàn tất đúng cách; một listener không nên tùy tiện suy luận mọi tài nguyên trong toàn bộ hệ thống ngoài đều đã sẵn sàng/ngừng hoàn toàn.

## 4. Ví dụ Java 17+ chạy được: start, stop, restart, close

Ví dụ dùng **Spring Framework 6.2.12**, Java 17+ và Gradle 8+; không yêu cầu Spring Boot hay cơ sở dữ liệu. Một bean `Lifecycle` đơn giản đại diện cho worker chạy nền; bean listener nhận bốn loại event vòng đời.

Cấu trúc:

```text
context-lifecycle-events-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ContextLifecycleDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'context-lifecycle-events-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.ContextLifecycleDemo'
}
```

**`src/main/java/demo/ContextLifecycleDemo.java`**

```java
package demo;

import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;
import org.springframework.context.event.EventListener;

public class ContextLifecycleDemo {

    public static class Worker implements Lifecycle {
        private boolean running;

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("worker: start");
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("worker: stop");
            }
        }

        @Override
        public boolean isRunning() {
            return running;
        }
    }

    public static class ContextEvents {

        @EventListener
        public void onRefreshed(ContextRefreshedEvent event) {
            System.out.println("event: refreshed");
        }

        @EventListener
        public void onStarted(ContextStartedEvent event) {
            System.out.println("event: started");
        }

        @EventListener
        public void onStopped(ContextStoppedEvent event) {
            System.out.println("event: stopped");
        }

        @EventListener
        public void onClosed(ContextClosedEvent event) {
            System.out.println("event: closed");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        Lifecycle worker() {
            return new Worker();
        }

        @Bean
        ContextEvents contextEvents() {
            return new ContextEvents();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Lifecycle worker = context.getBean("worker", Lifecycle.class);

            System.out.println("after refresh: running=" + worker.isRunning());

            context.start();
            System.out.println("after start: running=" + worker.isRunning());

            context.stop();
            System.out.println("after stop: running=" + worker.isRunning());
            System.out.println("after stop: active=" + context.isActive());

            context.start();
            System.out.println("after restart: running=" + worker.isRunning());

        } // try-with-resources gọi context.close().
    }
}
```

Chạy khi đã cài JDK 17+ và Gradle:

```bash
gradle -q run
```

Các dòng do chương trình in ra theo đúng thứ tự:

```text
event: refreshed
after refresh: running=false
worker: start
event: started
after start: running=true
worker: stop
event: stopped
after stop: running=false
after stop: active=true
worker: start
event: started
after restart: running=true
event: closed
worker: stop
```

### Vì sao có thứ tự đó?

1. `new AnnotationConfigApplicationContext(AppConfig.class)` tự đăng ký cấu hình và thực hiện `refresh()`; Spring tạo `Worker`, đăng ký các phương thức `@EventListener`, sau đó phát `ContextRefreshedEvent`. Bean chỉ implement `Lifecycle` thông thường **không tự start tại refresh**, nên `running=false`.
2. `context.start()` yêu cầu `LifecycleProcessor.start()` gọi `worker.start()` trước, rồi phát `ContextStartedEvent`. Do đó thấy `worker: start` trước `event: started`.
3. `context.stop()` gọi `worker.stop()` trước, rồi phát `ContextStoppedEvent`. `isActive()` vẫn `true`: context chưa đóng, vẫn giữ bean và có thể hoạt động lại.
4. Gọi `context.start()` lần nữa sẽ start worker đã dừng và phát thêm một `ContextStartedEvent`.
5. Khi thoát `try`, `close()` được gọi. Spring phát `ContextClosedEvent` rồi gọi lifecycle processor đóng/dừng bean còn chạy, nên `event: closed` đứng trước `worker: stop`. **Không có dòng `event: stopped` mới do riêng thao tác close.**

Mẫu log này đáng tin với **multicaster mặc định đồng bộ** và đúng một context như trong ví dụ. Khi thêm executor cho event multicaster, thread và thứ tự hoàn thành handler có thể thay đổi; không nên biến thứ tự dòng log thành hợp đồng chung của một hệ thống bất đồng bộ.

`@EventListener` dựa trên **bean được Spring quản lý**. Nếu tự `new ContextEvents()`, đối tượng mới không được đăng ký làm listener của context. `@EventListener` không tự kết nối những đối tượng nằm ngoài Spring container.

## 5. `Lifecycle` và `SmartLifecycle`: vì sao có bean chạy ngay khi refresh?

### 5.1. `Lifecycle` thường

Interface `org.springframework.context.Lifecycle` gồm:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Bean implement interface này nhận tín hiệu `start()` và `stop()` từ lifecycle processor. **`Lifecycle` thông thường không mặc định tự start sau refresh.** Đây là lý do `Worker` trong ví dụ đang dừng ngay sau khi tạo context, và chỉ chạy khi gọi `context.start()`.

Phương thức `start()`/`stop()` nên có hành vi có thể gọi lại an toàn theo trạng thái. Tín hiệu dừng thường cần trả về khi thành phần đã ngừng; nếu thao tác dừng thực sự bất đồng bộ, xem `SmartLifecycle.stop(Runnable)`.

### 5.2. `SmartLifecycle` hỗ trợ auto-start và thứ tự pha

`SmartLifecycle` mở rộng `Lifecycle` và `Phased`:

- `isAutoStartup()` cho phép tự start trong `LifecycleProcessor.onRefresh()`; **mặc định của `SmartLifecycle` là `true`**.
- `getPhase()` chọn thứ tự khởi động/dừng theo phase; phase **nhỏ start trước**, phase **lớn stop trước**. `Lifecycle` thường được xem như phase 0.
- `stop(Runnable callback)` hỗ trợ shutdown bất đồng bộ theo từng phase. **Phải gọi `callback.run()` khi đã dừng**; nếu quên, lifecycle processor có thể phải chờ đến timeout.
- Một `SmartLifecycle` có thể đã chạy từ lúc `ContextRefreshedEvent` được phát, **dù `ContextStartedEvent` chưa từng xuất hiện**.

Đoạn minh họa `SmartLifecycle` (không phải chương trình độc lập, giả định đặt trong Spring-managed bean):

```java
public final class MessageConsumer implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public boolean isAutoStartup() {
        return true; // tự start khi context refresh
    }

    @Override
    public int getPhase() {
        return 100; // start sau phase 0; stop trước phase 0
    }

    @Override
    public void start() {
        if (!running) {
            // Khởi động consumer; ví dụ này chỉ minh họa trạng thái.
            running = true;
        }
    }

    @Override
    public void stop() {
        running = false;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run(); // báo cho lifecycle processor rằng stop đã xong
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

Cần import `org.springframework.context.SmartLifecycle`. Đây là code minh họa tối giản; trong ứng dụng thật, chỉ gọi `callback.run()` khi consumer đã **thực sự dừng**, sau khi đóng kết nối, hủy subscription hoặc chờ xử lý xong các message in-flight theo chính sách. Nếu shutdown bất đồng bộ, chuyển callback vào nhánh được kích hoạt sau khi tài nguyên đã giải phóng.

**Lưu ý:** Không được dùng event `ContextStartedEvent` để suy luận rằng mọi `SmartLifecycle` vừa mới được start; nhiều bean đã auto-start ngay khi context refresh. Khi stop một component bằng `component.stop()` trực tiếp, việc đó cũng **không tự động khiến context phát `ContextStoppedEvent`**.

## 6. Chọn `@EventListener` hay `ApplicationListener`?

Hai cách phổ biến để xử lý lifecycle events là method annotation và interface.

### Cách 1: `@EventListener`

```java
@Component
public class ContextStatusObserver {

    @EventListener
    public void onStarted(ContextStartedEvent event) {
        // Sau lời gọi context.start().
    }

    @EventListener
    public void onStopped(ContextStoppedEvent event) {
        // Sau lời gọi context.stop().
    }
}
```

Đây là đoạn minh họa cần import `Component`, `EventListener`, `ContextStartedEvent`, `ContextStoppedEvent`. Bean phải thuộc context đã đăng ký listener; annotation được Spring xử lý khi cấu hình container.

### Cách 2: `ApplicationListener<T>`

```java
@Component
public class StartedObserver
        implements ApplicationListener<ContextStartedEvent> {

    @Override
    public void onApplicationEvent(ContextStartedEvent event) {
        // Nhận event typed từ Spring context.
    }
}
```

Đây cũng là mã minh họa; import `org.springframework.context.ApplicationListener`, `org.springframework.context.event.ContextStartedEvent`, `org.springframework.stereotype.Component`.

Với ví dụ chính, `@EventListener` tiện cho việc đặt nhiều handler cho các event cụ thể trong cùng một bean. `ApplicationListener<T>` thích hợp khi muốn kiểu listener tường minh, dễ đăng ký theo API hoặc trong những phần hạ tầng. Cả hai đều tham gia cơ chế event multicaster của context.

Không nhầm **`ApplicationEventPublisher.publishEvent(...)`** với `start()/stop()`: bạn có thể tự phát một custom event bằng publisher, nhưng `ContextStartedEvent`/`ContextStoppedEvent` chuẩn phản ánh thao tác do context thực hiện. **Không nên tự `publishEvent(new ContextStartedEvent(context))` để giả vờ đã start**; việc đó không gọi `LifecycleProcessor.start()` và có thể khiến listener tưởng sai trạng thái.

## 7. `close()` không phải `stop()`: khác biệt về tài nguyên và tái sử dụng

| Phương diện | `context.stop()` | `context.close()` |
| --- | --- | --- |
| Event chuẩn | `ContextStoppedEvent` | `ContextClosedEvent` |
| `Lifecycle` bean | Nhận stop nếu đang chạy theo lifecycle processor | Được dừng khi shutdown theo lifecycle processor, nếu áp dụng |
| Singleton | Thường vẫn tồn tại trong container | Bị hủy trong quá trình đóng context |
| `context.isActive()` | Thông thường vẫn `true` | `false` sau đóng |
| Có thể `start()` lại? | Có, nếu context vẫn active | Không |
| Dùng khi nào? | Tạm dừng/restart thành phần nền | Kết thúc vòng đời container/application |

Khi `close()`, thứ tự thông thường của `AbstractApplicationContext` là phát `ContextClosedEvent`, gọi `LifecycleProcessor.onClose()` để dừng các lifecycle beans, sau đó hủy singleton. Do đó listener xử lý `ContextClosedEvent` **không nên mặc định tin rằng mọi worker đã hoàn toàn dừng** tại thời điểm nhận event.

Ví dụ cleanup rõ ràng:

```java
@Component
public class ShutdownObserver {

    @EventListener
    public void onClosing(ContextClosedEvent event) {
        // Ngừng nhận yêu cầu mới / ghi log / chuyển trạng thái shutdown.
        // Không mặc định rằng mọi Lifecycle bean đã stop xong.
    }

    @PreDestroy
    public void onDestroy() {
        // Dọn tài nguyên do chính bean sở hữu trước khi bean bị hủy.
    }
}
```

Đây là mã minh họa, cần import `ContextClosedEvent`, `EventListener`, `Component` và `jakarta.annotation.PreDestroy` (trên Java 17 có thể cần dependency `jakarta.annotation-api` nếu dự án chưa có). `@PreDestroy` là bean destruction callback, không tương đương context stop; nó chạy khi bean bị destroy. Đừng phụ thuộc một cách mù quáng vào event listener để thay thế toàn bộ quản lý tài nguyên.

Khi phải giữ an toàn cho một tài nguyên nền, đặt logic start/stop ở bean sở hữu tài nguyên, thông qua `Lifecycle` hoặc `SmartLifecycle`; dùng event listener cho **phản ứng phụ trợ** như logging, telemetry hoặc chuyển trạng thái.

## 8. Spring Boot: tránh nhầm `ApplicationStartedEvent`

Spring Boot sử dụng `SpringApplication` để chạy ứng dụng và phát các **SpringApplication events** ngoài các event chuẩn của Spring Framework. Một số event có ý nghĩa:

- **`ApplicationStartedEvent` (Spring Boot):** phát sau khi `ApplicationContext` đã refresh, trước khi gọi các `ApplicationRunner`/`CommandLineRunner`.
- **`ApplicationReadyEvent` (Spring Boot):** phát khi ứng dụng đã hoàn tất các runner và sẵn sàng tiếp nhận công việc theo vòng đời Boot.
- **`ContextRefreshedEvent` (Spring Framework):** thuộc quá trình refresh của context.
- **`ContextStartedEvent` (Spring Framework):** phản ánh lời gọi `ConfigurableApplicationContext.start()` rõ ràng; **không phải** cách để mặc định biết Spring Boot vừa khởi động xong.
- **`ContextStoppedEvent` (Spring Framework):** phản ánh lời gọi `stop()` rõ ràng; **không phải** event shutdown chuẩn thay cho `ContextClosedEvent`.

Để làm tác vụ khi Boot đã sẵn sàng, thường cân nhắc `ApplicationReadyEvent` hoặc `ApplicationRunner` theo yêu cầu cụ thể. Để quản lý start/stop của một consumer hoặc worker, ưu tiên `SmartLifecycle`. Để biết context đang đóng, dùng `ContextClosedEvent` hoặc lifecycle shutdown callback tương ứng.

Đừng nhầm chữ “started” trong Spring Boot và chữ “started” của Spring Framework. Cùng một từ nhưng khác lifecycle, kiểu event và thời điểm.

## 9. Đồng bộ, bất đồng bộ và thứ tự xử lý

Mặc định, `SimpleApplicationEventMulticaster` xử lý listener **đồng bộ**, trên thread phát event. Vì thế ví dụ ở mục 4 có thứ tự log dễ quan sát.

Nếu bạn gắn `@Async` cho phương thức listener, hoặc cấu hình executor ở multicaster, handler có thể chạy ở thread khác. Khi đó:

- `context.start()` đã gửi tín hiệu bắt đầu cho lifecycle processor, nhưng **listener async** nhận `ContextStartedEvent` có thể chưa hoàn tất.
- Một listener nhận `ContextStoppedEvent` bất đồng bộ có thể chạy sau một thao tác khác hoặc trong khi ứng dụng đang chuẩn bị đóng.
- Không nên dựa vào thứ tự `@EventListener` giữa nhiều thread để quyết định worker nào phải start/stop trước.
- Cấu hình `@Async` cần bật `@EnableAsync`, proxy và executor thích hợp. Sự kiện multicaster được cấu hình executor và `@Async` trên phương thức listener là hai cơ chế khác nhau.
- Exception ở listener đồng bộ có thể lan tới bên phát event tùy multicaster/error handler; listener async cần cơ chế theo dõi lỗi riêng.

Đối với start/stop **phụ thuộc tài nguyên**, dùng lifecycle processor, `SmartLifecycle.getPhase()`, `depends-on` và callback stop — không dùng một tập các event listener bất đồng bộ thay thế cơ chế điều phối đó.

Ví dụ một listener ghi log có điều kiện:

```java
@EventListener
public void onStarted(ContextStartedEvent event) {
    System.out.println("started context id="
            + event.getApplicationContext().getId());
}
```

Đây là đoạn minh họa; `getApplicationContext()` trả về context nguồn của sự kiện. Trong hệ thống có parent/child contexts, event của child có thể được propagate lên parent; listener ở parent có thể thấy nhiều event. Nếu chỉ muốn phản ứng với một context, kiểm tra **context nguồn hoặc ID** cẩn thận thay vì giả định chỉ có một container trong tiến trình.

## 10. Kiểm thử ứng dụng và xử lý sự cố

### 10.1. Trường hợp cần test

1. **Refresh:** tạo context mới; xác nhận `ContextRefreshedEvent` được nhận, `Lifecycle` thường chưa auto-start và `SmartLifecycle` với `isAutoStartup=true` có thể đã chạy.
2. **Start:** gọi `start()`; xác nhận `Lifecycle.start()` được gọi và `ContextStartedEvent` được phát.
3. **Stop:** gọi `stop()`; xác nhận `Lifecycle.stop()` được gọi và `ContextStoppedEvent` được phát; context chưa bị hủy.
4. **Restart:** gọi `start()` sau `stop()`; xác nhận các bean restart được mà không giữ trạng thái/tài nguyên cũ bất hợp lệ.
5. **Close:** gọi `close()`; xác nhận `ContextClosedEvent`, bean destruction và tài nguyên shutdown; không mặc định đếm thêm `ContextStoppedEvent`.
6. **Auto-start:** thay `Lifecycle` bằng `SmartLifecycle`, đặt `isAutoStartup=true/false`; xác minh khác nhau ngay sau refresh.
7. **Nhiều bean/phase:** kiểm tra bean phụ thuộc được start/stop đúng trình tự; có timeout/callback cho shutdown bất đồng bộ.
8. **Async listeners:** chờ `CountDownLatch`/future/Awaitility thay vì dựa vào sleep ngẫu nhiên, vì thứ tự hoàn tất không cố định.
9. **Parent/child context:** kiểm tra listener không vô tình xử lý cùng một event nhiều lần do propagation.

Có thể kiểm thử event bằng một bean listener lưu counters, ví dụ:

```java
@EventListener
public void onStarted(ContextStartedEvent event) {
    startedCount.incrementAndGet();
}

@EventListener
public void onStopped(ContextStoppedEvent event) {
    stoppedCount.incrementAndGet();
}
```

Đây là đoạn code minh họa, cần biến `AtomicInteger startedCount`, `AtomicInteger stoppedCount` và Spring-managed bean. Test đọc counters sau mỗi lời gọi `context.start()/stop()` với multicaster mặc định đồng bộ, không cần chờ thread khác.

### 10.2. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy `ContextStartedEvent` khi ứng dụng chạy | Chỉ tạo/refresh context; chưa gọi `start()` | Dùng `ContextRefreshedEvent` hoặc Boot `ApplicationReadyEvent` đúng nhu cầu; gọi `start()` chỉ khi cần lifecycle signal |
| Không thấy `ContextStoppedEvent` lúc đóng ứng dụng | Chỉ gọi `close()`; đó là lifecycle event khác | Dùng `ContextClosedEvent` hoặc callback dừng của `LifecycleProcessor` |
| Worker đã chạy trước event started | Bean implement `SmartLifecycle` auto-start khi refresh | Kiểm tra `isAutoStartup`, `getPhase` và luồng refresh |
| `@EventListener` không được gọi | Handler không thuộc bean Spring, sai event type hoặc đăng ký quá muộn | Đăng ký Spring-managed listener trước refresh/start/stop |
| Nghe `ApplicationStartedEvent` nhưng không nhận | Nhầm Boot event với Framework event, hoặc chạy context thuần | Kiểm tra import/package và vòng đời Spring Boot |
| `stop()` xong không thể khôi phục worker | Bean không hỗ trợ restart hoặc tài nguyên đã bị hủy ngoài ý muốn | Viết `start()/stop()` có thể gọi lại; dành hủy tài nguyên vĩnh viễn cho `close()`/destroy |
| Listener nhận event hai lần | Parent/child contexts, nhiều listener hoặc nhiều lần start/stop | Kiểm tra context nguồn, registrations và số lần gọi |
| Shutdown bị kéo dài | `SmartLifecycle.stop(Runnable)` quên callback hoặc task không dừng | Hoàn tất callback sau stop, đặt timeout và theo dõi tài nguyên |
| Log event đến muộn/khác thứ tự | Listener dùng executor / `@Async` | Kiểm thử qua tín hiệu đồng bộ hóa, không giả định ordering giữa worker threads |
| Tự publish `ContextStartedEvent` nhưng worker vẫn dừng | Publish event không kích hoạt `LifecycleProcessor.start()` | Gọi `context.start()` hoặc API lifecycle thích hợp |

## 11. Nguyên tắc thiết kế trong dự án thực tế

- **`ContextStartedEvent` và `ContextStoppedEvent` là sự kiện của thao tác start/stop rõ ràng**, không phải tên chung cho startup/shutdown.
- Nếu cần quản lý một dịch vụ nền có thể khởi động lại, viết `Lifecycle` hoặc `SmartLifecycle`; đặt việc mở/đóng tài nguyên ở `start()`, `stop()`, `stop(Runnable)` tùy yêu cầu.
- Dùng `ContextRefreshedEvent` cho tình huống cần biết container đã refresh, nhưng tránh làm tác vụ nặng ảnh hưởng thời gian khởi động; trong Boot, sự kiện “ứng dụng sẵn sàng” có mục đích khác.
- Dùng `ContextClosedEvent` để phản ứng với container đang đóng; đừng mặc định mọi bean đã stop tại thời điểm nhận event.
- Nếu nhiều thành phần có phụ thuộc khi start/stop, khai báo phase/dependencies theo lifecycle processor, không tự tổ chức thứ tự bằng các event listener không đồng bộ.
- Mặc định listener đồng bộ; nếu bật async, cần chính sách lỗi, timeout và shutdown rõ ràng.
- Với context cha/con, luôn nghĩ tới **event source** và khả năng event được forward lên parent.
- Nếu cần dừng tạm thời: `stop()` rồi `start()` lại. Nếu kết thúc vòng đời: `close()` và tạo context mới khi cần.

**Tóm lại:** `ContextStartedEvent` được phát bởi `context.start()`, `ContextStoppedEvent` bởi `context.stop()`. `refresh()` và `close()` có event riêng. `LifecycleProcessor` điều phối các bean có vòng đời, còn event listener phản ứng với mốc đã xảy ra. Phân biệt rõ hai vai trò này là chìa khóa để tránh lỗi startup/shutdown trong Spring Framework.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — ApplicationContext Events: built-in events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — Startup and Shutdown Callbacks / `Lifecycle`, `SmartLifecycle`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html)
- [Spring Framework — `ConfigurableApplicationContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework — `ContextStartedEvent` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ContextStartedEvent.html)
- [Spring Framework — `ContextStoppedEvent` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ContextStoppedEvent.html)
- [Spring Framework — `SmartLifecycle` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/SmartLifecycle.html)
