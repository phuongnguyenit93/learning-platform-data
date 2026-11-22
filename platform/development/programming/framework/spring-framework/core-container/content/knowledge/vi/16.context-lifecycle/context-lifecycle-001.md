# ConfigurableApplicationContext và các giai đoạn refresh trong Spring Framework

## 1. ApplicationContext là gì, vì sao cần ConfigurableApplicationContext?

Trong Spring Core Container, **`ApplicationContext`** là giao diện đại diện cho container đã biết các bean definition, cung cấp bean, event, resource, message resolution và thông tin môi trường. Mã nghiệp vụ thường chỉ cần giao diện đọc này hoặc inject một dependency cụ thể.

**`ConfigurableApplicationContext`** mở rộng các khả năng quản trị vòng đời: có thể cấu hình context trước khi khởi động, yêu cầu `refresh()`, `start()`, `stop()`, `close()`, đăng ký application listener, shutdown hook và làm việc với `ConfigurableEnvironment`. Khi xây dựng ứng dụng/framework hoặc khởi tạo Spring container bằng tay, ta sử dụng API quản trị này.

Hai ví dụ quen thuộc:
- `AnnotationConfigApplicationContext`: container độc lập dùng `@Configuration`, `@Component` và Java annotation; tạo bằng constructor rỗng, `register(...)` rồi gọi `refresh()`.
- `ClassPathXmlApplicationContext`: context đọc bean definitions từ XML trên classpath, có cách xây dựng context đặc thù. Không cần XML nếu ứng dụng Java hiện đại dùng annotation config.

Ví dụ về sự khác nhau ở mức giao diện:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

void useBeans(ApplicationContext context) {
    Object service = context.getBean("someService"); // Tra bean đang có.
}

void manageContext(ConfigurableApplicationContext context) {
    context.start(); // Tín hiệu Lifecycle, KHÔNG thay refresh().
    context.stop();
    context.close(); // Kết thúc vòng đời context.
}
```

Đây là fragment minh họa API, chưa phải chương trình Java độc lập (các method phải nằm trong một class). Trong ứng dụng do Spring Boot quản lý, không tùy tiện gọi `refresh()` hoặc `close()` từ một HTTP request: framework thường chịu trách nhiệm điều phối vòng đời chung.

### Những trạng thái cần phân biệt

```text
CONSTRUCTED (chưa refresh)
     |
     | register / scan / customize Environment / BeanFactoryPostProcessor
     v
refresh() đang chạy:
     prepare -> bean definitions -> processors -> infrastructure
               -> instantiate regular singletons -> finish refresh
     |
     v
ACTIVE / REFRESHED
     |                  |
     | start()/stop()   | getBean()/publishEvent()/ứng dụng phục vụ công việc
     | điều khiển        |
     | Lifecycle beans  |
     +------------------+
     |
     v
close() / shutdown
     |
     v
CLOSED (tài nguyên được giải phóng theo lifecycle)
```

`isActive()` cho biết context đã được đánh dấu active và chưa đóng; cờ này được bật từ **đầu** `refresh()`, nên không được dùng riêng nó để chứng minh toàn bộ ứng dụng đã ready. Khái niệm “context đã refresh hoàn tất”, “Lifecycle component đã start”, “server đang nhận kết nối” và “external dependency healthy” là những điều khác nhau.

## 2. Vòng đời điển hình của AnnotationConfigApplicationContext

Có hai cách khởi tạo phổ biến:

**Cách 1 — constructor thực hiện refresh ngay:**

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    MyService bean = context.getBean(MyService.class);
}
```

Constructor nhận class cấu hình sẽ đăng ký class và **refresh context** trước khi trả về. `AppConfig` và `MyService` trong fragment cần được định nghĩa trong dự án.

**Cách 2 — chủ động làm rõ giai đoạn cấu hình:**

```java
try (var context = new AnnotationConfigApplicationContext()) {
    context.register(AppConfig.class);
    context.getEnvironment().setActiveProfiles("dev");
    context.refresh();
    MyService bean = context.getBean(MyService.class);
}
```

Mẫu này cho phép thay đổi cấu hình môi trường **trước** `refresh()`. `register(AppConfig.class)` chưa chạy hết bean lifecycle; nó khai báo cấu hình đầu vào. Sau `refresh()` mới có container đã hoàn thành bootstrap. Trong thực tế nên chọn một cơ chế quản lý cấu hình rõ ràng, tránh thay đổi active profile trễ khi bean definitions đã được xử lý.

Với `AnnotationConfigApplicationContext`, cơ chế bean factory là `GenericApplicationContext`: **chỉ refresh một lần** trên cùng instance. Gọi `refresh()` lần thứ hai không phải cách “nạp lại” application từ đầu; nó có thể ném `IllegalStateException`. Một số triển khai khác như `ClassPathXmlApplicationContext`/`AbstractRefreshableApplicationContext` có hỗ trợ làm mới lặp lại khi context còn mở. Vì vậy không suy ra từ tên method rằng mọi `ConfigurableApplicationContext` đều hot-reload được.

## 3. Danh sách đầy đủ các pha chính trong refresh()

`AbstractApplicationContext.refresh()` là mẫu thuật toán (template method) chung cho nhiều context implementations. Nó đảm bảo các bước chuẩn bị, cấu hình container, tạo singleton, thông báo sự kiện và dọn dẹp khi thất bại. Đây là **thứ tự khái niệm** của các pha trọng tâm trong Spring Framework 6.x; cách triển khai chi tiết có thể khác giữa các subclass/phiên bản.

```text
refresh()
  |
  +--  1. prepareRefresh()
  |       state, startup time, property sources, required properties
  |
  +--  2. obtainFreshBeanFactory()
  |       nạp/lấy BeanFactory và bean definitions
  |
  +--  3. prepareBeanFactory(beanFactory)
  |       standard resolvers, Aware, ApplicationContext integration
  |
  +--  4. postProcessBeanFactory(beanFactory)
  |       subclass hook (chẳng hạn WebApplicationContext)
  |
  +--  5. invokeBeanFactoryPostProcessors(beanFactory)
  |       cấu hình/biến đổi bean definitions trước khi tạo bean thường
  |
  +--  6. registerBeanPostProcessors(beanFactory)
  |       đăng ký processor cho vòng đời từng bean
  |
  +--  7. initMessageSource()
  |       internationalized message resolution
  |
  +--  8. initApplicationEventMulticaster()
  |       hạ tầng phân phối application events
  |
  +--  9. onRefresh()
  |       subclass hook, ví dụ một số web context dựng web infrastructure
  |
  +-- 10. registerListeners()
  |       application listeners và early application events
  |
  +-- 11. finishBeanFactoryInitialization(beanFactory)
  |       chuẩn bị conversion service, preInstantiateSingletons()
  |       tạo các singleton thông thường, khởi tạo + callback tương ứng
  |
  +-- 12. finishRefresh()
          clear caches / lifecycleProcessor.onRefresh()
          publish ContextRefreshedEvent
  |
  +-- refresh completed successfully
```

Cần phân biệt **mốc đăng ký infrastructure** với **mốc chạy method của bean**. Việc đăng ký `BeanPostProcessor` tại bước 6 không đồng nghĩa tất cả bean người dùng đã được tạo. Bean singleton thường được khởi tạo ở bước 11, lúc các processor đã có cơ hội áp dụng vào lifecycle từng target.

### Bảng tra cứu nhanh

| Pha | Việc chính | Hệ quả quan sát |
| --- | --- | --- |
| `prepareRefresh` | Đánh dấu startup, chuẩn bị property sources, validate required properties | Config thiếu bắt buộc có thể làm refresh fail |
| `obtainFreshBeanFactory` | Lấy hoặc nạp BeanFactory/bean definitions | Class cấu hình và bean definitions được container quản lý |
| `prepareBeanFactory` | Thiết lập hạ tầng mặc định (class loader, expression resolver, resolvable dependencies, v.v.) | Bean có thể nhận một số `Aware` dependencies |
| `postProcessBeanFactory` | Hook cho subclass | Web context có thể thêm hỗ trợ môi trường web |
| `invokeBeanFactoryPostProcessors` | Chạy processors của **bean definition** | `@Configuration`/`@Bean`, component scanning được xử lý đúng cơ chế |
| `registerBeanPostProcessors` | Đăng ký processors của **bean instance** | Hỗ trợ `@Autowired`, `@PostConstruct`, proxy/AOP theo cấu hình |
| `initMessageSource` | MessageSource | `getMessage(...)` khả dụng theo context |
| `initApplicationEventMulticaster` | Hệ thống publish/listen events | Các event có nơi phân phối |
| `onRefresh` | Hook của context implementation | Context đặc thù hoàn thành bước riêng |
| `registerListeners` | Đăng ký listener và phát event sớm phù hợp | Listener nhận sự kiện lifecycle theo khả năng |
| `finishBeanFactoryInitialization` | Tạo eager singleton, chạy initialization callbacks | Singleton mặc định đã khởi tạo |
| `finishRefresh` | Kết thúc bootstrap, khởi động auto-start Lifecycle thích hợp, publish refresh event | `ContextRefreshedEvent` xuất hiện |

Các tên method trên thuộc cơ chế implementation của `AbstractApplicationContext`; chúng không phải “12 method mà ứng dụng luôn tự gọi”. Ứng dụng gọi một lần `refresh()`, Spring tự thực hiện thuật toán. Không tự gọi các method `protected` hoặc tìm cách thay đổi thứ tự chúng từ mã nghiệp vụ.

## 4. Các pha 1–4: chuẩn bị môi trường và BeanFactory

### 4.1. prepareRefresh()

Spring đặt thời điểm khởi động, thiết lập active state, khởi tạo property sources qua hook `initPropertySources()` và xác nhận các required properties đã khai báo trong `Environment`. Ngoài ra, context chuẩn bị hạ tầng giữ các event được phát khi listener chưa sẵn sàng.

Chẳng hạn code cấu hình trước refresh:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();
context.getEnvironment().setRequiredProperties("app.region");
context.register(AppConfig.class);
context.refresh(); // Fail nếu app.region chưa có trong Environment.
```

Đây là fragment cần class `AppConfig` và xử lý `close()` phù hợp. `setRequiredProperties` thuộc `ConfigurablePropertyResolver` của `ConfigurableEnvironment`; `refresh()` sẽ validate và có thể ném exception trước khi tạo singleton thông thường. Ví dụ không tạo thêm property `app.region` nên cố ý minh họa nhánh thiếu cấu hình.

**Không nhầm cờ `isActive()` với startup completed**: `prepareRefresh()` có thể đặt active flag trước khi phần lớn các bước còn lại xảy ra.

### 4.2. obtainFreshBeanFactory()

Giai đoạn này lấy một `ConfigurableListableBeanFactory` đại diện cho cấu hình bean. Ở một số context có thể refresh nhiều lần, Spring tạo một bean factory mới và đọc lại cấu hình; ở `GenericApplicationContext`, bean factory đã có từ trước và không được phép khởi tạo lại tùy tiện.

`BeanFactory` lưu bean definitions, scope, dependency graph và tạo instance. `ApplicationContext` là lớp tích hợp thêm event, resources, messages và lifecycle orchestration. Không phải mọi BeanFactory đều tự phát `ContextRefreshedEvent` như ApplicationContext.

### 4.3. prepareBeanFactory() và postProcessBeanFactory()

Spring cấu hình các thành phần hỗ trợ chuẩn như class loader, expression resolution, property editors, integration `ApplicationContextAware`/`EnvironmentAware` và các resolvable dependencies. Với context web, các subclass bổ sung wiring liên quan ServletContext/request/session ở hook phù hợp.

Phần lớn ứng dụng **không cần override** các hook này. Chúng dành cho tác giả infrastructure hoặc custom `ApplicationContext`; ứng dụng thường cấu hình thông qua `@Configuration`, `@Bean` và các extension point công khai.

## 5. Các pha 5–6: xử lý metadata trước, instance sau

Đây là điểm nối giữa **khai báo bean** và **khởi tạo bean**, đồng thời giải thích vì sao Spring không đơn giản quét class rồi lập tức gọi constructor:

| Extension point | Thao tác chính | Thời điểm trong `refresh()` |
| --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Đăng ký/chỉnh `BeanDefinition`, chẳng hạn phát hiện `@Configuration` và `@Bean` qua `ConfigurationClassPostProcessor` | Pha 5, trước factory processors thông thường |
| `BeanFactoryPostProcessor` | Chỉnh metadata, resolve cấu hình và placeholders | Pha 5, trước khi tạo các singleton ứng dụng |
| `BeanPostProcessor` | Inject, thực hiện callback hoặc bọc proxy quanh **instance** | Đăng ký ở pha 6, được gọi khi từng bean được tạo |

Ví dụ, `AutowiredAnnotationBeanPostProcessor` xử lý các injection points thích hợp; `CommonAnnotationBeanPostProcessor` tham gia callback `@PostConstruct`/`@PreDestroy` khi các API annotation tương ứng có sẵn. Với một singleton thông thường, luồng cục bộ gồm **constructor/factory → injection → before-initialization processors (có thể bao gồm `@PostConstruct`) → `afterPropertiesSet`/custom init → after-initialization processors (có thể tạo proxy)**. Mốc `SmartInitializingSingleton.afterSingletonsInstantiated()` đến sau vòng pre-instantiation và trước `ContextRefreshedEvent`.

Nếu processor cố gọi `getBean()` quá sớm, nó có thể tạo service trước khi các processors khác được đăng ký đầy đủ, gây thiếu injection/proxy kỳ vọng. Bài tiếp theo đi sâu vào cách đăng ký, thứ tự và kiểm thử post-processors; ở bài này chỉ cần nhớ **pha 5 xử lý definitions, pha 6 chuẩn bị xử lý instances, pha 11 khởi tạo eager singletons**.

## 6. Các pha 7–10: messages, events và context-specific infrastructure

`initMessageSource()` thiết lập bean có tên `messageSource` nếu tồn tại, hoặc fallback thích hợp để hỗ trợ internationalized messages. Người dùng thường khai báo `MessageSource` qua cấu hình thay vì override pha lifecycle.

`initApplicationEventMulticaster()` tạo hoặc lấy `ApplicationEventMulticaster` theo tên quy ước của Spring. Mặc định event listener thường chạy đồng bộ trong thread publish; nếu cấu hình executor bất đồng bộ, thứ tự và thời điểm hoàn tất thay đổi. **Không** mặc định dựa vào mọi listener đã làm xong mọi tác vụ bên ngoài khi một event được publish.

`onRefresh()` là hook cho subclass, ví dụ infrastructure của web application. Nó chạy **trước** pha khởi tạo tất cả regular singleton. Một bean tạo bởi infrastructure riêng có thể gây side effect sớm; không viết logic dựa vào giả định thứ tự classpath scanning giữa những bean độc lập.

`registerListeners()` đưa các listener đăng ký tĩnh hoặc bean `ApplicationListener` vào event multicaster, và phát các early application events đã được giữ lại. Với `@EventListener`, infrastructure adapter xử lý annotation thành listener tương ứng; không tự giả định mọi listener được khởi tạo trước pha singleton.

### Các event chuẩn của context

| Event | Thời điểm thường gặp | Ý nghĩa |
| --- | --- | --- |
| `ContextRefreshedEvent` | Cuối `refresh()` thành công | Context đã load definitions, processors, eager singletons và hoàn thành quá trình refresh |
| `ContextStartedEvent` | Sau lệnh `start()` | Lifecycle beans được gửi tín hiệu start |
| `ContextStoppedEvent` | Sau lệnh `stop()` | Lifecycle beans được gửi tín hiệu stop |
| `ContextClosedEvent` | Trong `close()`/shutdown hook | Context đang đóng, chuẩn bị hủy singleton và giải phóng tài nguyên |

Một parent/child ApplicationContext hierarchy có thể khiến event từ child được truyền lên parent. Listener cần kiểm tra `event.getApplicationContext()` nếu nghiệp vụ chỉ dành cho đúng context của nó. Event không phải thông điệp distributed: các context ở JVM/pod khác nhau không tự nhận cùng một Spring event.

## 7. Hai pha cuối: singleton pre-instantiation và finishRefresh

Ở `finishBeanFactoryInitialization(beanFactory)`, Spring hoàn thiện conversion service và những thiết lập cần thiết, sau đó gọi `preInstantiateSingletons()` trên BeanFactory tương ứng. Các singleton eager thông thường được tạo, inject, initialize. Spring không đảm bảo mọi singleton độc lập được tạo theo thứ tự class name hoặc file source; dependency và configuration quyết định nhiều phần trình tự.

Ở `finishRefresh()`, `LifecycleProcessor.onRefresh()` được gọi trước khi `ContextRefreshedEvent` được publish. Với các `SmartLifecycle` bean auto-start, Spring có thể khởi động chúng ở đây theo phase/depends-on. **Vì vậy listener `ContextRefreshedEvent` có thể thấy lifecycle components đã nhận auto-start**, nhưng không có nghĩa tất cả external dependency hoặc tác vụ asynchronous mà chúng khởi chạy đã hoạt động healthy.

`SmartLifecycle` khác `SmartInitializingSingleton`:
- `SmartInitializingSingleton`: callback một lần cuối pre-instantiation của regular singleton, thích hợp validate/xây registry.
- `SmartLifecycle`: tham gia start/stop, có phase và autoStartup, thích hợp listener, consumer hoặc component chạy dài.
- `ContextRefreshedEvent`: tín hiệu cấp ApplicationContext sau refresh, có thể có nhiều lần với implementation hỗ trợ refresh lại.
- `ApplicationRunner`/`CommandLineRunner`: extension Spring Boot chạy sau context refresh theo quy trình Boot, không thuộc 12 pha cơ bản của Spring Core `refresh()`.

## 8. Ví dụ Java 17+ chạy đầy đủ: quan sát refresh, start/stop, close

Mẫu sau dùng **Java 17+, Maven 3.9+ và Spring Framework 6.2.19**, không cần Spring Boot, servlet hay database. Ta tạo `AnnotationConfigApplicationContext` ở trạng thái chưa refresh, đăng ký config, gọi `refresh()` và quan sát thứ tự callback, event.

### Cấu trúc dự án

```text
context-refresh-demo/
├── pom.xml
└── src/main/java/edu/example/context/
    ├── AppConfig.java
    ├── DemoBean.java
    ├── ContextEvents.java
    └── Main.java
```

**pom.xml:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>context-refresh-demo</artifactId>
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
                <configuration>
                    <mainClass>edu.example.context.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/context/DemoBean.java:**

```java
package edu.example.context;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.SmartInitializingSingleton;

public final class DemoBean
        implements InitializingBean, SmartInitializingSingleton, DisposableBean {

    public DemoBean() {
        System.out.println("bean: constructor");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("bean: afterPropertiesSet");
    }

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("bean: afterSingletonsInstantiated");
    }

    @Override
    public void destroy() {
        System.out.println("bean: destroy");
    }
}
```

**src/main/java/edu/example/context/ContextEvents.java:**

```java
package edu.example.context;

import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ApplicationContextEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;

public final class ContextEvents
        implements ApplicationListener<ApplicationContextEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextEvent event) {
        if (event instanceof ContextRefreshedEvent) {
            System.out.println("event: refreshed");
        } else if (event instanceof ContextStartedEvent) {
            System.out.println("event: started");
        } else if (event instanceof ContextStoppedEvent) {
            System.out.println("event: stopped");
        } else if (event instanceof ContextClosedEvent) {
            System.out.println("event: closed");
        }
    }
}
```

**src/main/java/edu/example/context/AppConfig.java:**

```java
package edu.example.context;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    public DemoBean demoBean() {
        return new DemoBean();
    }

    @Bean
    public ContextEvents contextEvents() {
        return new ContextEvents();
    }
}
```

**src/main/java/edu/example/context/Main.java:**

```java
package edu.example.context;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        System.out.println("before refresh: active=" + context.isActive());
        context.register(AppConfig.class);

        try {
            context.refresh();
            System.out.println("after refresh: active=" + context.isActive());

            context.start();
            context.stop();
        } finally {
            context.close();
        }

        System.out.println("after close: active=" + context.isActive());
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Các dòng `System.out.println` của chương trình, theo thứ tự:**

```text
before refresh: active=false
bean: constructor
bean: afterPropertiesSet
bean: afterSingletonsInstantiated
event: refreshed
after refresh: active=true
event: started
event: stopped
event: closed
bean: destroy
after close: active=false
```

Spring/Maven có thể tạo log riêng, nhưng các dòng `System.out` là kết quả xác định của chương trình tối giản này khi refresh thành công. Lưu ý `context.start()` và `context.stop()` **vẫn phát event** dù mẫu không có custom `Lifecycle` bean nào cần start hoặc stop. `close()` phát `ContextClosedEvent` trước khi các singleton được destroy, vì vậy event đóng được in **trước** `bean: destroy`.

Mẫu cố ý không gọi `refresh()` lần thứ hai: `AnnotationConfigApplicationContext` không hỗ trợ refresh lại cùng instance. Trong production, dùng context do framework quản lý và đóng theo vòng đời ứng dụng, tránh gọi `close()` giữa request còn chạy.

## 9. Cấu hình context trước refresh và trách nhiệm quản lý

`ConfigurableApplicationContext` cho phép cấu hình thêm trước khi bootstrap. Một số API thường gặp:

| API | Tác dụng | Thời điểm nên gọi |
| --- | --- | --- |
| `setEnvironment(...)` | Cung cấp `ConfigurableEnvironment` riêng | Trước refresh |
| `getEnvironment().setActiveProfiles(...)` | Chọn profile | Trước xử lý bean definitions/refresh |
| `addBeanFactoryPostProcessor(...)` | Thêm processor cấp BeanFactory | Trước refresh |
| `addApplicationListener(...)` | Đăng ký listener tĩnh | Trước refresh hoặc sau khi event system active, theo API |
| `setParent(...)` | Đặt parent context | Trước refresh |
| `refresh()` | Bootstrap container | Theo quy tắc implementation, thường một lần |
| `getBeanFactory()` | Truy cập nội bộ ConfigurableListableBeanFactory | Dùng cẩn trọng, thường cho framework/infrastructure |
| `registerShutdownHook()` | JVM hook tự đóng context khi shutdown | Khi app tự quản lý context mà chưa có shutdown manager khác |
| `start()/stop()` | Gửi tín hiệu Lifecycle | Sau refresh, không thay thế refresh/close |
| `close()` | Đóng context, hủy singleton | Khi kết thúc ứng dụng/container |

Đừng tự gắn `registerShutdownHook()` rồi cũng chủ động gọi `close()` mà lo bean chắc chắn bị destroy hai lần: Spring có cơ chế tránh close trùng trên cùng context, nhưng thiết kế shutdown vẫn nên có **một nơi chịu trách nhiệm chính**. `try-with-resources` thuận tiện cho CLI/test tự tạo context vì `ConfigurableApplicationContext` hỗ trợ `close()`.

### BeanFactoryPostProcessor nên được đăng ký ở đâu?

Ví dụ fragment:

```java
AnnotationConfigApplicationContext ctx =
        new AnnotationConfigApplicationContext();
ctx.addBeanFactoryPostProcessor(factory -> {
    // Chỉnh metadata trước khi bean thông thường được instantiate.
});
ctx.register(AppConfig.class);
ctx.refresh();
```

Đây chỉ là đoạn minh họa, chưa có `AppConfig` và cleanup. Callback nhận `ConfigurableListableBeanFactory` cho phép truy cập bean definitions; tránh gọi `factory.getBean(...)` tùy tiện bên trong để không tạo instance quá sớm.

Nếu cần tùy biến definitions thông qua Java config, ưu tiên các annotation/spring extension đã hỗ trợ, chỉ dùng processor cấp thấp khi thật sự cần thay đổi metadata.

## 10. Refresh thất bại: exception, rollback và cleanup

Khi refresh gặp exception, Spring chủ động dọn các singleton đã tạo trong BeanFactory theo cơ chế lifecycle, hủy context bootstrap và báo lỗi ra caller. `ConfigurableApplicationContext.refresh()` có contract tránh để lại các singleton đã tạo dở trong một lần startup thất bại. Tuy nhiên điều đó **không bảo đảm hoàn tác mọi side effect** của mã ứng dụng: nếu `@PostConstruct` tự gửi email, ghi DB, mở socket ngoài kiểm soát hoặc start thread, Spring không thể “undo” các thao tác ấy một cách tự động.

```text
refresh()
  |
  +-- prepare, process bean definitions, instantiate beans
  |
  +-- @PostConstruct / factory method / processor ném exception
  |
  +-- destroy already-created singletons (best effort)
  +-- cancelRefresh() / reset status
  +-- propagate failure tới caller
```

Các điểm cần lưu ý:
- Cấu hình không hợp lệ, thiếu dependency và vòng phụ thuộc không hỗ trợ thường phát sinh `BeansException` hoặc `BeanCreationException` với nguyên nhân chi tiết.
- Bean lazy có thể không được tạo tại startup; lỗi trong bean đó có thể chỉ xuất hiện tại lần gọi đầu tiên, **không** nhất thiết trong refresh.
- Một context chỉ cho refresh một lần có thể không được retry refresh sau lỗi; tạo instance context mới và sửa nguyên nhân thay vì gọi lại bừa bãi.
- Cleanup phụ thuộc việc singleton đã được Spring quản lý đầy đủ hay chưa. Nếu tạo resource rồi ném exception giữa constructor/init, nên tự đảm bảo cleanup cục bộ.
- Nhiều context ở parent-child hierarchy có vòng đời độc lập; close child không tự đóng parent, và không coi refresh child là refresh toàn bộ hierarchy.

Mẫu fail-fast phù hợp: dùng `@ConfigurationProperties` validation, constructor preconditions hoặc `@PostConstruct` kiểm tra điều kiện bắt buộc; nếu resource ngoài có thể tạm không sẵn sàng, cần readiness/retry/timeout rõ ràng thay vì treo vô hạn ở refresh.

## 11. start(), stop(), close() và các sự kiện không thay thế nhau

`refresh()` **tạo và chuẩn bị** container. `start()` và `stop()` thuộc `Lifecycle` control; chúng gửi tín hiệu đến các `Lifecycle` bean được quản lý và publish context events tương ứng. `close()` **kết thúc** context: publish closing event, dừng lifecycle components qua processor phù hợp và destroy singleton.

```text
          refresh
 NEW  ----------------->  CONTEXT REFRESHED
                                  |
                                  | start()
                                  v
                           Lifecycle STARTED
                                  |
                                  | stop()
                                  v
                           Lifecycle STOPPED
                                  |
                                  | start()
                                  v
                           Lifecycle STARTED
                                  |
                                  | close()
                                  v
                            CONTEXT CLOSED
```

Đây là mô hình khái niệm; trong Spring, một số `SmartLifecycle` bean có thể **auto-start ngay trong finishRefresh()` mà không cần ứng dụng gọi `start()`. Khi `stop()` được gọi, context vẫn còn tồn tại và thường vẫn có thể `getBean()`; chỉ các components quản lý `Lifecycle` nhận tín hiệu dừng. `stop()` không destroy mọi singleton, không xóa toàn bộ definitions và không khởi tạo lại chúng khi `start()`.

Sau `close()`, context kết thúc vòng đời; không gọi `refresh()`/`start()` như cách tái sử dụng một context đã đóng. Với các implementation hỗ trợ nhiều refresh khi **chưa đóng**, đó là ngoại lệ có quy tắc riêng, không biến context đã close thành reusable container.

### SmartLifecycle có phase

`SmartLifecycle` cung cấp `isAutoStartup()`, `getPhase()` và callback `stop(Runnable)` (cùng các method của `Lifecycle`). Tùy version, Spring xử lý startup theo phase tăng dần, shutdown theo phase giảm dần, kết hợp dependency ordering. Nếu cần consumer đợi repository hoặc connection infrastructure, khai báo dependency và phase rõ ràng; không dựa vào listener `ContextRefreshedEvent` để giải quyết toàn bộ thứ tự startup.

## 12. Các bẫy thường gặp với refresh trong Spring Boot, Web và test

### 12.1. Gọi refresh() lại để “reload configuration”

Trong `AnnotationConfigApplicationContext` và nhiều context quản lý bởi Spring Boot, gọi lại `refresh()` không phải cơ chế reload cấu hình runtime hợp lệ. Nó có thể thất bại vì implementation không hỗ trợ multiple refresh. Nếu cần thay đổi cấu hình lúc runtime, thiết kế dynamic config có lifecycle rõ, publish immutable snapshot, hoặc xây lại context mới theo nhu cầu kiểm soát.

### 12.2. Thay Environment sau refresh và mong bean thay đổi

`@Value`, `@ConfigurationProperties`, `@Profile` và `@Conditional` được xử lý ở các giai đoạn khác nhau. Việc gọi `environment.setActiveProfiles("prod")` sau refresh không có nghĩa Spring sẽ tự hủy/tạo lại bean theo profile mới. Bean definitions đã được xử lý, singleton đã tạo. Đặt các profile/property sources trước refresh, hoặc dùng cơ chế refresh cấu hình đặc thù có kiểm soát khi ứng dụng cung cấp.

### 12.3. Khởi chạy job lâu trong @PostConstruct

`@PostConstruct` chạy trong initialization của bean, thường trước `finishRefresh()`. Job mạng kéo dài có thể làm context startup chậm, timeout hoặc fail; lời gọi self-invocation đến method `@Transactional`/`@Async` cũng có thể bỏ qua proxy. Dùng lifecycle hook phù hợp sau refresh hoặc `SmartLifecycle` cho component dài hạn. Trong Spring Boot có thể dùng runner nếu công việc cần thực thi cấp ứng dụng.

### 12.4. Hiểu sai ContextRefreshedEvent là server đã healthy

Event xác nhận context refresh hoàn thành, không chứng minh database, Kafka, Redis, DNS, external API hay readiness của server đã sẵn sàng tuyệt đối. Trong Spring Boot, actuator health/readiness có semantics riêng và cần cấu hình theo hệ thống. Nếu listener `ContextRefreshedEvent` gọi external service trực tiếp, cần timeout/retry/failure policy rõ.

### 12.5. Tạo bean thủ công ngoài container

`new MyService()` không đi qua Spring BeanFactory, vì thế nó không nhận tự động injection, BeanPostProcessor, init callbacks hay destruction management. Đối với dependencies cần container quản lý, hãy khai báo `@Bean`, `@Component`/scan hoặc factory infrastructure phù hợp. Đừng dùng `getBean()` ở khắp code nghiệp vụ nếu constructor injection đã giải quyết được.

### 12.6. ApplicationListener được gọi nhiều lần khi có child context

Một context hierarchy có thể truyền `ApplicationEvent` từ child lên parent. Listener nên kiểm tra `event.getApplicationContext() == myContext` khi nó chỉ muốn xử lý refresh của chính context; ngoài ra một implementation hỗ trợ hot refresh có thể phát event nhiều lần. Không coi `ContextRefreshedEvent` là global exactly-once job.

### 12.7. Đăng ký listener quá muộn

`addApplicationListener(...)` sau khi `ContextRefreshedEvent` đã được phát không tự phát lại sự kiện quá khứ. Nếu bạn cần quan sát lần refresh đầu tiên, đăng ký listener **trước** `refresh()` (hoặc khai báo listener bean sẵn). Cơ chế event thông thường không cung cấp replay lịch sử cho mọi subscriber đến muộn.

### 12.8. Quên close() khi tạo context trong integration test / CLI

Context có thể giữ thread pool, connection, singleton resource. Với `AnnotationConfigApplicationContext` tự tạo, dùng `try-with-resources` hoặc `finally { context.close(); }`. `close()` kích hoạt lifecycle shutdown và các destruction callbacks của singleton; prototype được container tạo thường không tự có đầy đủ destruction management như singleton. Framework test Spring có context cache và quản lý vòng đời riêng, không tùy ý đóng cached context trong từng test.

## 13. Debug khi context không startup hoặc startup sai thứ tự

Một checklist thực hành:

1. **Xác nhận context implementation**: `AnnotationConfigApplicationContext`, `ClassPathXmlApplicationContext`, `WebApplicationContext` hay Spring Boot context? Khả năng refresh lại khác nhau.
2. **Kiểm tra cấu hình trước refresh**: active profiles, property sources, required properties, class scanning, `@Import` và `@Bean` definitions.
3. **Xem root cause của exception**: `NoSuchBeanDefinitionException`, `BeanCreationException`, circular dependencies, constructor exceptions hoặc BeanPostProcessor failures.
4. **Phân biệt giai đoạn**: nếu chưa vào `finishBeanFactoryInitialization()`, lỗi có thể thuộc parsing/processor/infrastructure; nếu lỗi trong `@PostConstruct`, bean đã qua constructor và phần lớn injection.
5. **Quan sát events**: log `ContextRefreshedEvent` và `ContextClosedEvent`, kiểm tra đúng application context khi có parent-child.
6. **Chẩn đoán init order**: thiếu dependency relationship? Ghi rõ `@DependsOn` hoặc constructor dependency; `@Order` không phải công cụ chung điều phối mọi lần tạo singleton.
7. **Kiểm tra lazy beans**: một bean lazy hỏng có thể không gây lỗi ngay lúc refresh, nhưng fail ở request đầu tiên.
8. **Theo dõi bean post-processors**: dependency của processor có bị tạo trước khi infrastructure hoàn tất không? Đây là nguồn lỗi proxy/injection khó thấy.
9. **Tránh blocking vô hạn**: timeout, retry policy và quản lý background work ở đúng lifecycle.
10. **Xem xét shutdown**: context đóng chưa? `@PreDestroy`/`DisposableBean`/custom destroy method được đăng ký và scope có được Spring quản lý hủy không?

### Theo dõi thời gian startup

Spring cung cấp API `ApplicationStartup` để ghi nhận các startup steps. `BufferingApplicationStartup` có thể thu các bước vào buffer phục vụ phân tích; `FlightRecorderApplicationStartup` tích hợp Java Flight Recorder cho profiling chi tiết hơn. Đây là instrumentation giúp biết đoạn nào chậm, không thay đổi thứ tự/hợp đồng vòng đời. Với Spring Boot, các tính năng startup endpoint/observability liên quan cần cấu hình phù hợp nếu muốn expose dữ liệu đo.

## 14. Tự kiểm tra

1. `ApplicationContext` khác `ConfigurableApplicationContext` ở mục đích sử dụng nào?
2. `new AnnotationConfigApplicationContext(AppConfig.class)` đã gọi `refresh()` hay chưa?
3. Khi dùng constructor rỗng của `AnnotationConfigApplicationContext`, cần thao tác nào sau `register(...)` để tạo eager singleton?
4. `BeanFactoryPostProcessor` và `BeanPostProcessor` khác nhau ở thời điểm và đối tượng bị xử lý như thế nào?
5. `@PostConstruct` của bean A có bảo đảm bean B không có dependency với A đã được tạo không?
6. Khi nào `SmartInitializingSingleton.afterSingletonsInstantiated()` chạy so với `ContextRefreshedEvent`?
7. Vì sao `isActive() == true` chưa đủ chứng minh refresh đã hoàn thành và server ready?
8. Gọi `start()` có tạo lại singleton hay chạy lại `@PostConstruct` không?
9. Lệnh `stop()` có giống `close()` không? Vì sao?
10. `ContextClosedEvent` xuất hiện trước hay sau khi Spring destroy singleton thông thường?
11. Có thể gọi `refresh()` lần thứ hai với một `AnnotationConfigApplicationContext` không?
12. Khi `@Bean` factory tạo resource rồi init ném exception, Spring có rollback mọi side effect ngoài container không?
13. Nếu code thêm listener sau khi context đã refresh, listener có tự nhận `ContextRefreshedEvent` trước đó không?
14. Nếu context có parent và child, close child có đóng parent không?
15. Một ứng dụng có ba pod, mỗi pod một context. `ContextRefreshedEvent` có phải chỉ phát đúng một lần trên toàn cluster không?

**Đáp án gợi ý:**

1. `ApplicationContext` là API sử dụng bean/services; `ConfigurableApplicationContext` thêm quản trị startup, environment và shutdown.
2. Có, constructor đó đăng ký cấu hình và refresh.
3. Gọi `refresh()` đúng một lần.
4. Factory processor biến đổi metadata trước instantiate; bean processor tham gia lifecycle instance.
5. Không; hook chỉ của bean A.
6. Smart callback cuối pre-instantiation; refresh event phát sau `finishRefresh()`.
7. Active được bật ở đầu refresh, không phải health signal.
8. Không; chỉ tín hiệu cho `Lifecycle` beans và phát event started.
9. Không; stop không destroy context, close chấm dứt lifecycle và hủy singleton.
10. Trước, trong quy trình đóng thông thường.
11. Không; generic bean factory không hỗ trợ nhiều lần refresh.
12. Không; phải chủ động kiểm soát side effects bên ngoài.
13. Không; events không tự được replay.
14. Không; mỗi context có vòng đời riêng.
15. Không; mỗi context/pod có refresh event của nó.

## Tài liệu chính thức

- Spring Framework — Additional Capabilities of the ApplicationContext (lifecycle events): https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework — `ConfigurableApplicationContext` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework — `AbstractApplicationContext` Javadoc (`refresh()` và các template hooks): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework — `AbstractRefreshableApplicationContext` Javadoc (refreshable context): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractRefreshableApplicationContext.html
- Spring Framework — `AnnotationConfigApplicationContext` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/AnnotationConfigApplicationContext.html
- Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework — `SmartInitializingSingleton` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
