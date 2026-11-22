# Sự kiện trong refresh context của Spring ApplicationContext

## 1. Mục tiêu bài học

Khi ứng dụng Spring khởi tạo, `ApplicationContext` không chỉ tạo bean rồi trả về cho caller. Nó còn thực hiện một chuỗi bước cấu hình, khởi tạo singleton, chuẩn bị hệ thống event, kích hoạt các thành phần `Lifecycle`, và **phát sự kiện `ContextRefreshedEvent`** khi quá trình refresh hoàn tất thành công.

Trong bài này, `refresh context` nghĩa là lời gọi `ConfigurableApplicationContext.refresh()` và những thao tác tương ứng mà `AbstractApplicationContext` thực hiện. Cần hiểu được:

- Sự kiện `ContextRefreshedEvent` là gì, được phát vào thời điểm nào và chứa thông tin gì.
- Các bước của `refresh()` liên quan tới đăng ký listener, khởi tạo bean và `SmartLifecycle`.
- Cách nhận sự kiện bằng `ApplicationListener` hoặc `@EventListener`.
- Khác biệt giữa `ContextRefreshedEvent`, `ContextStartedEvent`, `ContextClosedEvent` và các sự kiện khởi động của Spring Boot.
- Cách xử lý hiện tượng nhận sự kiện từ child context, nhận nhiều lần refresh, xử lý bất đồng bộ và lỗi trong listener.
- Ví dụ Java 17+ chạy độc lập với Spring Framework để quan sát đúng thứ tự khởi tạo.

## 2. `ContextRefreshedEvent` là gì?

`org.springframework.context.event.ContextRefreshedEvent` là một `ApplicationContextEvent` có nguồn là `ApplicationContext` vừa được khởi tạo hoặc refresh. Spring phát sự kiện này sau khi đã thực hiện phần chính của quá trình khởi tạo context, và `ApplicationContext` sẵn sàng sử dụng theo vòng đời của framework.

Ví dụ listener:

~~~java
// Đoạn minh họa trong một Spring-managed bean.
@EventListener
public void onRefreshed(ContextRefreshedEvent event) {
    ApplicationContext source = event.getApplicationContext();
    System.out.println("Refreshed: " + source.getId());
}
~~~

Spring sẽ đăng ký phương thức với hệ thống application events. Khi context nguồn phát `ContextRefreshedEvent`, phương thức được gọi theo chế độ dispatch hiện tại (mặc định đồng bộ). Từ `event.getApplicationContext()` có thể biết **context cụ thể đã phát sự kiện**; rất quan trọng nếu ứng dụng có parent/child context.

**Ý nghĩa chính:** đây là tín hiệu về **vòng đời Spring context**, không phải tín hiệu “đã xử lý mọi tác vụ nền”, “mọi external service đang khỏe” hoặc “ứng dụng đã sẵn sàng nhận traffic” trong mọi kiến trúc.

### Những điều đã và chưa được bảo đảm

Khi `ContextRefreshedEvent` được phát ở cuối `refresh()` thông thường:

- Bean definitions, bean factory và các bean post-processor cần thiết đã được thiết lập.
- **Các singleton không lazy** cần khởi tạo trước đã được instantiate và chạy các callback khởi tạo, chẳng hạn `InitializingBean.afterPropertiesSet()`.
- Spring đã hoàn tất `finishBeanFactoryInitialization(...)`.
- Trong `finishRefresh()`, `LifecycleProcessor.onRefresh()` được gọi trước khi phát `ContextRefreshedEvent`; các `SmartLifecycle` có `autoStartup` thích hợp có thể đã được start.
- Các bean `@Lazy`, prototype hoặc công việc asynchronous tự khởi động **không được bảo đảm đều đã hoàn tất**. Các tiến trình bên ngoài như migration/consumer/remote API cũng có thể chưa sẵn sàng, tùy ứng dụng.

Không nhầm khái niệm “context đã refresh” với “mọi tác vụ của ứng dụng đã kết thúc”.

## 3. Vị trí của sự kiện trong quy trình `AbstractApplicationContext.refresh()`

Ở mức khái quát, trình tự refresh trong `AbstractApplicationContext` gồm các bước sau (tên phương thức là các hook của Spring, không phải API mà ứng dụng phải tự gọi từng bước):

| Bước | Công việc | Tác động đến event/listener |
| --- | --- | --- |
| `prepareRefresh()` | Chuẩn bị trạng thái context, kiểm tra thuộc tính, ghi thời điểm khởi động | Thiết lập nền cho chu trình refresh và event sớm |
| `obtainFreshBeanFactory()` | Chuẩn bị hoặc lấy bean factory của lần refresh | Bean definitions phải sẵn sàng theo kiểu context |
| `prepareBeanFactory(...)` | Đăng ký các thành phần nền cho factory | Hỗ trợ dependency, context-aware và infrastructure |
| `postProcessBeanFactory(...)` | Cho subclass điều chỉnh bean factory | Tùy loại context |
| `invokeBeanFactoryPostProcessors(...)` | Chạy `BeanFactoryPostProcessor` và registry post-processors | Các thay đổi cấu hình/definitions hoàn tất trước instantiate |
| `registerBeanPostProcessors(...)` | Cài đặt `BeanPostProcessor` | Chuẩn bị proxy và callback cho bean |
| `initMessageSource()` | Chuẩn bị nguồn thông điệp quốc tế hóa | Dịch vụ context |
| `initApplicationEventMulticaster()` | Khởi tạo multicaster | Sẵn sàng phân phối application events |
| `onRefresh()` | Hook của subclass, ví dụ một số web context khởi tạo hạ tầng | Chưa phải `ContextRefreshedEvent` |
| `registerListeners()` | Đăng ký `ApplicationListener` và phát lại event sớm nếu có | Listener được kết nối với multicaster |
| `finishBeanFactoryInitialization(...)` | Khởi tạo singleton còn lại | Listener annotation và bean `SmartLifecycle` liên quan được chuẩn bị |
| `finishRefresh()` | Thực hiện lifecycle processor và phát sự kiện hoàn tất | **`ContextRefreshedEvent` được publish ở đây** |

Tối giản:

~~~text
refresh()
   |
   +-- chuẩn bị BeanFactory và BeanPostProcessor
   +-- tạo ApplicationEventMulticaster
   +-- đăng ký listener
   +-- khởi tạo singleton không lazy
   |
   +-- finishRefresh()
          |
          +-- lifecycleProcessor.onRefresh()
          |       +-- khởi động SmartLifecycle autoStartup phù hợp
          |
          +-- publishEvent(new ContextRefreshedEvent(this))
   |
   +-- refresh() trả về khi dispatch đồng bộ đã kết thúc
~~~

**Không nhầm `onRefresh()` với `finishRefresh()`:** `onRefresh()` là hook cho subclass tại một bước sớm hơn, trước khi hoàn tất khởi tạo singleton. Sự kiện `ContextRefreshedEvent` được phát tại `finishRefresh()`, sau lời gọi `LifecycleProcessor.onRefresh()`.

### Tại sao listener có thể nhận sự kiện cuối refresh?

- Spring đăng ký các bean thực thi `ApplicationListener` trong giai đoạn `registerListeners()`.
- Các phương thức gắn `@EventListener` được cơ chế xử lý annotation như `EventListenerMethodProcessor` phát hiện/đăng ký trong vòng đời khởi tạo bean.
- Khi `ContextRefreshedEvent` cuối refresh được phát, listener phù hợp đã được đăng ký để nhận sự kiện.

Không lấy thứ tự `@Bean` được khai báo trong một file làm hợp đồng thứ tự callback. Cơ chế quản lý dependency, post-processor và lifecycle mới là yếu tố quyết định.

### Event phát rất sớm trong refresh thì sao?

Một số event được publish khi multicaster/listener chưa đăng ký hoàn toàn có thể được Spring tạm lưu ở cơ chế `earlyApplicationEvents` và phân phối khi `registerListeners()` thực hiện. Điều này là chi tiết lifecycle của `AbstractApplicationContext`; không nên dựa vào nó như một message queue bền vững hoặc giả định mọi kiểu event ở mọi thời điểm đều được lưu/retry.

## 4. Hai cách lắng nghe `ContextRefreshedEvent`

### Cách 1: `ApplicationListener<ContextRefreshedEvent>`

~~~java
// Đoạn minh họa: class cần được đăng ký thành bean.
@Component
public class RefreshListener
        implements ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println(event.getApplicationContext().getId());
    }
}
~~~

`ApplicationListener` cung cấp API type-safe, hữu ích khi listener được đăng ký sớm hoặc logic cần tái sử dụng. Không cần thiết phải gọi `publishEvent` thủ công để tạo sự kiện refresh; chính context phát nó.

### Cách 2: `@EventListener`

~~~java
// Đoạn minh họa: class cần được đăng ký thành bean.
@Component
public class RefreshHandler {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println(event.getApplicationContext().getDisplayName());
    }
}
~~~

Spring suy ra kiểu event từ tham số phương thức. Có thể khai báo `@EventListener(ContextRefreshedEvent.class)` tường minh. Chọn cách phù hợp với dự án; hai cách cùng sử dụng cơ chế event của Spring và không cần đăng ký cả hai cho cùng một hành động.

**Đặc biệt với parent/child context:** khi child context publish event, Spring có thể chuyển tiếp sự kiện lên parent context. Listener ở parent vì vậy có thể nhận cả event của parent lẫn child. Để chỉ xử lý refresh của **context mà bean đang thuộc về**, inject context sở hữu bean và so sánh identity:

~~~java
// Đoạn minh họa trong Spring-managed bean.
private final ApplicationContext ownContext;

public RefreshHandler(ApplicationContext ownContext) {
    this.ownContext = ownContext;
}

@EventListener
public void onRefresh(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return; // sự kiện đến từ một context khác, ví dụ child
    }
    initializeForThisContext();
}
~~~

Hai method/class minh họa ở trên không phải chương trình độc lập; hãy áp dụng vào đúng class Spring bean. Nếu cần xử lý **mọi context** trong hierarchy thì không lọc, nhưng phải định nghĩa rõ tác vụ được phép chạy bao nhiêu lần.

## 5. Ví dụ Java 17+ chạy được: quan sát startup và refresh event

Chương trình sau chỉ sử dụng Spring Framework (không cần Spring Boot). Mục tiêu là kiểm chứng:

1. Trước `refresh()`, context chưa active.
2. `InitializingBean.afterPropertiesSet()` chạy khi singleton được khởi tạo.
3. `SmartLifecycle.start()` chạy trong phần lifecycle của refresh.
4. `@EventListener(ContextRefreshedEvent)` quan sát được bean đã khởi tạo và `SmartLifecycle` đã start.
5. Sau `refresh()`, caller thấy một refresh event; sau `close()`, context không còn active.

Sử dụng `AtomicInteger` đếm event và cờ trạng thái cho ví dụ. Không dựa vào `Thread.sleep` hoặc log của framework để kết luận.

Cấu trúc:

~~~text
context-refresh-event/
├── pom.xml
└── src/main/java/demo/ContextRefreshDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-refresh-event</artifactId>
    <version>1.0.0</version>

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
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. `src/main/java/demo/ContextRefreshDemo.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

public class ContextRefreshDemo {

    public static final class State {
        volatile boolean beanInitialized;
        volatile boolean lifecycleStarted;
        final AtomicInteger refreshEvents = new AtomicInteger();
    }

    // Được khởi tạo như singleton trước khi refresh kết thúc.
    public static final class ResourceBean implements InitializingBean {
        private final State state;

        public ResourceBean(State state) {
            this.state = state;
        }

        @Override
        public void afterPropertiesSet() {
            state.beanInitialized = true;
        }
    }

    // SmartLifecycle auto-start trong LifecycleProcessor.onRefresh().
    public static final class Worker implements SmartLifecycle {
        private final State state;
        private final ResourceBean dependency;
        private volatile boolean running;

        public Worker(State state, ResourceBean dependency) {
            this.state = state;
            this.dependency = dependency;
        }

        @Override
        public void start() {
            if (!state.beanInitialized || dependency == null) {
                throw new IllegalStateException("ResourceBean not ready");
            }
            running = true;
            state.lifecycleStarted = true;
        }

        @Override
        public void stop() {
            running = false;
        }

        @Override
        public void stop(Runnable callback) {
            stop();
            callback.run();
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

    public static final class RefreshObserver {
        private final State state;
        private final ApplicationContext ownContext;

        public RefreshObserver(State state, ApplicationContext ownContext) {
            this.state = state;
            this.ownContext = ownContext;
        }

        @EventListener
        public void onContextRefreshed(ContextRefreshedEvent event) {
            // Chỉ xử lý context sở hữu listener, tránh child event.
            if (event.getApplicationContext() != ownContext) {
                return;
            }
            if (!state.beanInitialized || !state.lifecycleStarted) {
                throw new AssertionError("Refresh event arrived too early");
            }
            state.refreshEvents.incrementAndGet();
        }
    }

    @Configuration
    public static class Config {
        @Bean
        public State state() {
            return new State();
        }

        @Bean
        public ResourceBean resourceBean(State state) {
            return new ResourceBean(state);
        }

        @Bean
        public Worker worker(State state, ResourceBean resourceBean) {
            return new Worker(state, resourceBean);
        }

        @Bean
        public RefreshObserver refreshObserver(
                State state, ApplicationContext context) {
            return new RefreshObserver(state, context);
        }
    }

    public static void main(String[] args) {
        var context = new AnnotationConfigApplicationContext();

        try (context) {
            context.register(Config.class);
            System.out.println("before-refresh active=" + context.isActive());

            context.refresh();

            State state = context.getBean(State.class);
            Worker worker = context.getBean(Worker.class);

            System.out.println("bean-initialized=" + state.beanInitialized);
            System.out.println("lifecycle-running=" + worker.isRunning());
            System.out.println("refresh-events=" + state.refreshEvents.get());
            System.out.println("after-refresh active=" + context.isActive());
        }

        System.out.println("after-close active=" + context.isActive());
    }
}
~~~

Chạy tại thư mục chứa `pom.xml`, với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextRefreshDemo
~~~

Các dòng do chương trình in ra theo thứ tự:

~~~text
before-refresh active=false
bean-initialized=true
lifecycle-running=true
refresh-events=1
after-refresh active=true
after-close active=false
~~~

### 5.3. Vì sao kết quả có thể dự đoán?

- Lệnh `new AnnotationConfigApplicationContext()` tạo context chưa refresh; `isActive()` là `false`.
- `register(Config.class)` đăng ký cấu hình, nhưng chưa tự hoàn thành chu trình refresh.
- `refresh()` khởi tạo các singleton theo dependency. `ResourceBean` gọi `afterPropertiesSet()`, đặt `beanInitialized=true`.
- Trong `finishRefresh()`, `LifecycleProcessor.onRefresh()` start `Worker` vì đây là `SmartLifecycle` tự khởi động. `Worker` kiểm tra bean phụ thuộc đã khởi tạo rồi đặt `lifecycleStarted=true`.
- Sau đó context publish `ContextRefreshedEvent`. `RefreshObserver` được đăng ký nhờ `@EventListener` và tăng bộ đếm lên 1 sau khi kiểm tra các điều kiện.
- Với multicaster mặc định đồng bộ và không có parent context, `refresh()` hoàn tất sau lần dispatch đó. Vì thế main đọc thấy `refreshEvents=1`.
- Cuối block `try (context)`, `close()` chạy; `LifecycleProcessor` dừng bean thích hợp và `isActive()` trở thành `false`.

Ví dụ dùng một lần `refresh()`. Không gọi `refresh()` lần hai trên `AnnotationConfigApplicationContext` vì lớp này dựa trên `GenericApplicationContext`, không hỗ trợ refresh lại cùng một instance. Muốn mô phỏng khởi động mới, tạo một context mới. Một số implementation khác của Spring có thể hỗ trợ nhiều lần refresh; không áp dụng quy luật “mỗi JVM chỉ có một ContextRefreshedEvent” cho toàn bộ hệ thống.

## 6. Quan hệ với những sự kiện vòng đời khác

| Event | Nguồn/phát sinh | Nên hiểu là |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context vừa khởi tạo hoặc refresh | Kết thúc thành công chu trình refresh context |
| `ContextStartedEvent` | Gọi `ConfigurableApplicationContext.start()` | Tín hiệu start rõ ràng cho `Lifecycle` bean, khác với refresh |
| `ContextStoppedEvent` | Gọi `ConfigurableApplicationContext.stop()` | Context đã nhận tín hiệu stop |
| `ContextClosedEvent` | Context được `close()` hoặc shutdown | Vòng đời context kết thúc và bean sẽ bị hủy theo quy trình |
| `ApplicationStartedEvent` (Spring Boot) | Boot đã refresh context, trước `ApplicationRunner`/`CommandLineRunner` | Ứng dụng Boot đã khởi động đến giai đoạn trước runner |
| `ApplicationReadyEvent` (Spring Boot) | Sau khi Boot chạy các application/command-line runner | Thời điểm muộn hơn, dùng khi logic cần biết quá trình startup Boot đã hoàn tất |

**Spring Framework thuần** không có nghĩa vụ phát `ApplicationReadyEvent` — đó là sự kiện của **Spring Boot**. Trong một ứng dụng Boot điển hình, `ContextRefreshedEvent` xảy ra trước `ApplicationStartedEvent`, rồi đến `ApplicationReadyEvent` sau các runner. Không viết listener `ContextRefreshedEvent` với giả định các runner đã chạy xong.

Cũng cần tránh nhầm lẫn `onRefresh()` method của `AbstractApplicationContext` với event `ContextRefreshedEvent`, hoặc lẫn `ContextStartedEvent` khi gọi `start()` với sự kiện phát tự động cuối `refresh()`.

## 7. Trường hợp event xảy ra nhiều lần

### 7.1. Parent/child context

Spring cho phép context con có context cha. Event do child publish có thể được chuyển lên parent, nên listener nằm ở parent có thể nhận `ContextRefreshedEvent` của cả hai. Nếu callback thực hiện tác vụ có tác dụng phụ như import dữ liệu, việc nhận nhiều event có thể tạo duplicate.

Phân biệt chính xác bằng:

~~~java
@EventListener
public void onRefresh(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    warmUpCacheForThisContext();
}
~~~

Đây là đoạn mã minh họa cần bean chứa `ownContext` và phương thức `warmUpCacheForThisContext`. So sánh tham chiếu context giúp xử lý **đúng context**, nhưng nếu context đó có thể refresh nhiều lần, vẫn có thể gọi callback nhiều lần theo thiết kế.

### 7.2. Nhiều context độc lập hoặc khởi động lại

Trong test suite, nhiều `ApplicationContext` khác nhau có thể được tạo và đóng. Mỗi lần context hoàn tất refresh có event của riêng nó. Không dùng một biến static `initialized` trong toàn JVM để giả định event chỉ xuất hiện một lần; điều này dễ sai trong integration tests và ứng dụng chứa nhiều context.

Nếu startup action phải **idempotent**, lưu trạng thái theo đúng phạm vi (context, resource, deployment hoặc khóa nghiệp vụ), thiết kế kiểm tra trước/sau và khả năng chạy lặp an toàn. Đừng cố giải quyết bằng một cờ static mà không biết vòng đời thực tế.

## 8. Chọn việc phù hợp cho `ContextRefreshedEvent`

Các ví dụ có giá trị:

- Nạp cấu hình runtime hoặc làm nóng một cache nhỏ sau khi các singleton cần thiết đã khởi tạo.
- Đăng ký một tác vụ theo vòng đời của chính context, có cơ chế dọn khi `ContextClosedEvent`.
- Kiểm tra và ghi metrics cho giai đoạn startup theo phạm vi context.
- Điều phối một bước bootstrap **nhanh**, rõ ràng và có thể chạy lại khi có refresh (nếu loại context hỗ trợ).

Không nên:

- Chạy tác vụ network rất lâu ngay trong listener đồng bộ nếu điều đó sẽ kéo dài `refresh()` và trì hoãn startup.
- Giả định database migration, scheduler, HTTP listener, message consumer và external services đều sẵn sàng chỉ vì một `ContextRefreshedEvent` xuất hiện.
- Gửi email thanh toán, tạo tác vụ không thể hoàn tác hoặc thực hiện migration không idempotent mỗi lần event được phát.
- Dùng nó làm thay thế hoàn toàn cho health/readiness hoặc cơ chế phục hồi sau crash.

**Nếu cần khởi động một tiến trình nền:** cân nhắc `SmartLifecycle` khi yêu cầu thuộc lifecycle start/stop; nếu dùng event để schedule tác vụ bất đồng bộ, ghi rõ executor, timeout, failure handler và cờ sẵn sàng riêng. Sự kiện có thể đã xử lý xong **trước khi công việc async hoàn tất**.

**Nếu cần chạy sau startup Boot:** cân nhắc `ApplicationRunner`, `CommandLineRunner` hoặc `ApplicationReadyEvent` tùy hành vi mong muốn. Runner được Boot gọi sau refresh và trước `ApplicationReadyEvent`; nếu muốn giám sát readiness, kết hợp cơ chế availability/health thích hợp.

## 9. Thứ tự dispatch, xử lý lỗi và `@Async`

### 9.1. Listener đồng bộ và `@Order`

Với event multicaster mặc định đồng bộ, Spring gọi listener trên luồng publish event. Có thể dùng `@Order` hoặc `Ordered` để điều khiển ưu tiên gọi listener phù hợp **trong cùng một dispatch**.

~~~java
// Minh họa trong Spring bean.
@EventListener
@Order(10)
public void afterRefresh(ContextRefreshedEvent event) {
    // Bước được gọi theo độ ưu tiên so với listener cùng event.
}
~~~

`@Order` không phải cơ chế bảo đảm khởi động toàn bộ ứng dụng, thứ tự giữa các lần refresh thuộc nhiều context, hay thứ tự **hoàn thành** nếu các listener chuyển việc sang thread khác.

### 9.2. `@Async`

Khi đặt `@Async` lên listener và bật `@EnableAsync` với executor hợp lệ, thân phương thức listener có thể chạy ở thread khác. Khi ấy:

- `refresh()` không đợi phần thân async hoàn tất chỉ vì event đã được dispatch.
- Không được giả định `ApplicationReadyEvent` hoặc request đầu tiên chỉ đến sau khi task async đó xong.
- Nếu tác vụ async thất bại, cần log/metrics/retry và `AsyncUncaughtExceptionHandler` khi phù hợp.
- Nếu tác vụ cần đúng thread/request/transaction context, việc chuyển thread không tự sao chép `ThreadLocal`, security context hay transaction.

Đối với tác vụ phải hoàn tất **trước khi ứng dụng được coi là ready**, hãy dùng cơ chế phối hợp cụ thể hoặc startup runner phù hợp và kiểm soát lỗi rõ ràng; fire-and-forget sẽ không tạo ra bảo đảm đó.

### 9.3. Exception

Exception trong listener đồng bộ mặc định có thể lan tới luồng phát event (tùy cấu hình multicaster và error handler), gây thất bại trong giai đoạn `finishRefresh()`. Vì vậy không đặt xử lý dễ lỗi, không liên quan đến việc khởi tạo bean, vào callback này mà không có chính sách xử lý failure. Nếu bắt exception, không được âm thầm bỏ lỗi nghiêm trọng khiến ứng dụng tự cho rằng đã sẵn sàng.

Ngược lại, listener chạy async có thể lỗi **sau khi refresh trả về**, nên cần theo dõi độc lập.

## 10. Checklist tự kiểm tra

1. `ContextRefreshedEvent` được phát sau `finishBeanFactoryInitialization` và `LifecycleProcessor.onRefresh()` chưa?
2. Listener thuộc context nào, và có thể nhận event từ child không?
3. Công việc trong listener có idempotent nếu event xuất hiện nhiều lần không?
4. Có đang dựa vào `ContextRefreshedEvent` như một tín hiệu readiness của Spring Boot dù runner chưa chạy xong không?
5. Có tác vụ I/O dài, `@Async`, exception hoặc timeout khiến startup kéo dài hoặc sẵn sàng quá sớm không?
6. Context hiện tại có thực sự hỗ trợ refresh nhiều lần hay cần tạo instance mới?
7. Có cần tài nguyên được start/stop theo lifecycle không? Nếu có, hãy cân nhắc `SmartLifecycle`.
8. Có kiểm thử cả mở/đóng context, hierarchy và startup thất bại không?

**Ghi nhớ:** `ContextRefreshedEvent` đánh dấu Spring context đã hoàn tất một chu kỳ refresh. Nó được publish ở cuối `AbstractApplicationContext.finishRefresh()`, sau khi các singleton không lazy đã được chuẩn bị và lifecycle processor được gọi. Chọn listener để phản ứng với trạng thái **context đã refresh**, đồng thời thiết kế riêng những yêu cầu về readiness, xử lý bất đồng bộ, độ bền và xử lý nhiều context.

## Tài liệu chính thức

- Spring Framework — ApplicationContext events, built-in event types và `ContextRefreshedEvent`: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2 — `AbstractApplicationContext.refresh()` và `finishRefresh()`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework 6.2 — `LifecycleProcessor` và `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/LifecycleProcessor.html
- Spring Framework 6.2 — `ContextRefreshedEvent` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html
- Spring Boot — SpringApplication events, Started/Ready và parent-child contexts: https://docs.spring.io/spring-boot/reference/features/spring-application.html
