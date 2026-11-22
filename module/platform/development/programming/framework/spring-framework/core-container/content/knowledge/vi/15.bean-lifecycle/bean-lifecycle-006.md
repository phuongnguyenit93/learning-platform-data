# SmartInitializingSingleton sau khi tạo các singleton thông thường trong Spring Framework

## 1. Vấn đề: có những tác vụ cần đợi cả pha khởi tạo singleton

Trong Spring IoC Container, một bean được tạo, inject dependencies, thực thi các callback như `@PostConstruct` và `InitializingBean.afterPropertiesSet()`, rồi mới được xem là đã khởi tạo xong. Các callback đó thuộc về **từng bean riêng lẻ**. Chúng không có nghĩa toàn bộ những singleton khác đều đã được tạo xong.

Một số công việc phải chờ **hết pha pre-instantiation của các singleton thông thường (regular, non-lazy singleton)**, ví dụ:

- Kiểm tra cấu hình liên quan nhiều component, khi các singleton mặc định eager đã được khởi tạo.
- Tổng hợp metadata từ những bean cùng interface sau khi chúng hoàn thành initialization thông thường.
- Xây dựng một chỉ mục các strategy/handler đã đăng ký trong container, tránh vô tình yêu cầu Spring tạo bean khác quá sớm.
- Xác thực ràng buộc chéo, chẳng hạn phải có ít nhất một handler xử lý một loại sự kiện.
- Hoàn thiện một registry nội bộ trước khi ApplicationContext phát sự kiện refresh thành công.

Spring cung cấp callback **`org.springframework.beans.factory.SmartInitializingSingleton`** cho mục đích này. Interface xuất hiện từ Spring Framework 4.1 và còn được sử dụng trong Spring Framework 6.x/7.x.

```java
package org.springframework.beans.factory;

public interface SmartInitializingSingleton {
    void afterSingletonsInstantiated();
}
```

Đây là chữ ký API minh họa từ Spring, **không** phải source bạn tự khai báo lại trong dự án. Một bean singleton có thể `implements SmartInitializingSingleton`; khi `BeanFactory` hoàn thành pha tạo singleton thông thường, Spring gọi `afterSingletonsInstantiated()` trên instance phù hợp.

**Điều bảo đảm:** tại thời điểm callback được gọi, các **regular singleton bean** đã được tạo và khởi tạo xong theo thuật toán tạo singleton thông thường. **Điều không bảo đảm:** mọi bean lazy, prototype, request/session scoped đã có instance; tất cả external service đã ready; hay mọi logic startup cấp ứng dụng đã hoàn thành.

## 2. Vị trí callback trong vòng đời Spring Container

Một đường đi điển hình khi refresh một Spring `ApplicationContext`:

```text
ApplicationContext.refresh()
   |
   +-- đọc/xử lý bean definitions
   +-- đăng ký BeanFactoryPostProcessor / BeanPostProcessor
   +-- chuẩn bị infrastructure (event multicaster, v.v.)
   |
   +-- finishBeanFactoryInitialization(...)
   |     |
   |     +-- preInstantiateSingletons()
   |           |
   |           +-- tạo các singleton thông thường chưa lazy
   |           |     +-- constructor / @Bean factory
   |           |     +-- dependency injection
   |           |     +-- @PostConstruct
   |           |     +-- InitializingBean.afterPropertiesSet()
   |           |     +-- custom init method
   |           |     +-- BeanPostProcessor sau khởi tạo
   |           |
   |           +-- SmartInitializingSingleton.afterSingletonsInstantiated()
   |
   +-- finishRefresh()
         |
         +-- khởi động lifecycle processor / SmartLifecycle theo cấu hình
         +-- publish ContextRefreshedEvent
```

Sơ đồ là tổng quan hữu ích đối với `AbstractApplicationContext`/`DefaultListableBeanFactory` thông thường. Một số cơ chế đặc biệt như background initialization, circular references, factory beans và custom context có thể có chi tiết khác. Không dùng sơ đồ làm cam kết tuyệt đối về thứ tự **giữa các singleton độc lập**.

### Các mốc cần phân biệt

| Mốc | Khi nào? | Có biết tất cả regular singleton đã tạo xong? |
| --- | --- | --- |
| Constructor | Tạo chính bean đó | Không |
| Field/setter injection | Populate dependencies của bean | Không |
| `@PostConstruct` | Initialization của từng target sau injection | Không |
| `InitializingBean.afterPropertiesSet()` | Kết thúc pha khởi tạo cục bộ của bean | Không |
| `@Bean(initMethod=...)` | Custom initialization method cho bean | Không |
| `BeanPostProcessor.postProcessAfterInitialization` | Sau init của từng bean; có thể tạo proxy | Không |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Cuối pha pre-instantiation của singleton | **Có**, trong phạm vi regular singleton |
| `ContextRefreshedEvent` | ApplicationContext refresh hoàn tất | Context đã refresh; hook ở cấp context |
| `ApplicationRunner`/`CommandLineRunner` (Spring Boot) | Sau quá trình khởi tạo Boot context | Startup logic của Boot, không phải hook từng bean |

Thường `@PostConstruct` của bean A chạy **trước** `afterSingletonsInstantiated()` của bean B. Mọi bean thông thường đã hoàn tất initialization khi callback của B bắt đầu, nhưng callback `afterSingletonsInstantiated()` của **các bean khác** có thể chưa chạy.

Đó là giới hạn quan trọng: **không** coi callback của bean A là bằng chứng callback của bean B đã hoàn tất. Nếu A thực sự phụ thuộc kết quả riêng từ callback B, thiết kế cơ chế phối hợp hoặc tổ chức một bean orchestration duy nhất, thay vì trông chờ thứ tự đăng ký bean.

## 3. Cách Spring gọi interface này

Trong triển khai phổ biến của Spring, `DefaultListableBeanFactory.preInstantiateSingletons()` có hai bước về mặt ý tưởng:

1. Duyệt danh sách bean definition và khởi tạo các singleton cần eagerly instantiated. Các bean có dependency được tạo theo yêu cầu của hệ thống dependency graph.
2. Sau khi kết thúc bước đó, tìm các singleton đã tạo có triển khai `SmartInitializingSingleton` và gọi `afterSingletonsInstantiated()`.

```text
Bean definitions:
   alpha       -> singleton eager
   beta        -> singleton eager
   inspector   -> singleton eager, implements SmartInitializingSingleton
   lazyCache   -> singleton @Lazy
   factory     -> prototype

Trong pre-instantiation:
   alpha, beta, inspector được khởi tạo theo quy tắc Spring
   (thứ tự cụ thể phụ thuộc dependencies/definitions).

Sau khi các regular singleton đã được tạo:
   inspector.afterSingletonsInstantiated()

Nếu về sau mới gọi getBean("lazyCache"):
   lazyCache được tạo theo yêu cầu;
   callback đã qua không được tự gọi lại cho lazyCache.
```

Điểm khác với `InitializingBean`: `afterPropertiesSet()` chạy tại **cuối quá trình tạo một bean cụ thể**, nên nếu nó lấy tất cả bean theo type bằng `getBeansOfType()` thì có nguy cơ khởi tạo những bean chưa tới lượt. `afterSingletonsInstantiated()` dành cho việc này vì regular singleton đã đi hết bước eager initialization.

Tuy nhiên `getBeansOfType(SomeType.class)` vẫn có thể chạm tới **lazy bean** hoặc `FactoryBean` tùy API và cách khai báo. Vì vậy nói “không vô tình khởi tạo singleton thông thường quá sớm” không có nghĩa “mọi lookup đều không tạo thêm object”. Trong môi trường có lazy beans, cân nhắc `getBeanNamesForType(type, includeNonSingletons, allowEagerInit)` để phát hiện tên mà không yêu cầu eager init của FactoryBean; ngay cả khi đã có tên, chỉ `getBean()` khi thực sự muốn instantiate.

## 4. Ví dụ Spring Core đầy đủ chạy được với Java 17+

Ví dụ sử dụng Spring Framework **6.2.18**, Java 17+ và Maven 3.9+; không cần Spring Boot, web server hay database. Chúng ta khai báo hai singleton `Module` và một `ModuleInspector`. Mỗi module đặt cờ `initialized` trong `InitializingBean.afterPropertiesSet()`. Cuối pha tạo singleton, inspector tìm hai module, kiểm tra cả hai đã được initialize, rồi in kết quả. Output không dựa vào thứ tự tạo hai module.

**Cấu trúc dự án:**

```text
smart-singletons/
├── pom.xml
└── src/main/java/edu/example/smart/
    ├── AppConfig.java
    ├── Module.java
    ├── ModuleInspector.java
    └── Main.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>smart-singletons</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
                    <mainClass>edu.example.smart.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/smart/Module.java**

```java
package edu.example.smart;

import org.springframework.beans.factory.InitializingBean;

public final class Module implements InitializingBean {
    private final String name;
    private boolean initialized;

    public Module(String name) {
        this.name = name;
    }

    @Override
    public void afterPropertiesSet() {
        // Được Spring gọi trong initialization của riêng module này.
        initialized = true;
    }

    public String name() {
        return name;
    }

    public boolean initialized() {
        return initialized;
    }
}
```

**src/main/java/edu/example/smart/ModuleInspector.java**

```java
package edu.example.smart;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.ApplicationContext;

public final class ModuleInspector implements SmartInitializingSingleton {
    private final ApplicationContext context;
    private boolean checked;

    public ModuleInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void afterSingletonsInstantiated() {
        // Đúng thời điểm: các regular singleton khác đã init xong.
        List<Module> modules =
                new ArrayList<>(context.getBeansOfType(Module.class).values());
        modules.sort(Comparator.comparing(Module::name));

        if (modules.size() != 2 ||
                modules.stream().anyMatch(m -> !m.initialized())) {
            throw new IllegalStateException("Modules are not fully initialized");
        }

        String names = String.join(",",
                modules.stream().map(Module::name).toList());
        checked = true;
        System.out.println("callback: " + names + " initialized");
    }

    public boolean checked() {
        return checked;
    }
}
```

**src/main/java/edu/example/smart/AppConfig.java**

```java
package edu.example.smart;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    public Module alpha() {
        return new Module("alpha");
    }

    @Bean
    public Module beta() {
        return new Module("beta");
    }

    @Bean
    public ModuleInspector inspector(ApplicationContext context) {
        return new ModuleInspector(context);
    }
}
```

**src/main/java/edu/example/smart/Main.java**

```java
package edu.example.smart;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            ModuleInspector inspector = context.getBean(ModuleInspector.class);
            System.out.println("main: checked=" + inspector.checked());
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Các dòng do chương trình in ra `System.out` (theo thứ tự):**

```text
callback: alpha,beta initialized
main: checked=true
```

Maven/Spring có thể có log riêng; hai dòng trên là output ứng dụng. `AnnotationConfigApplicationContext(AppConfig.class)` đã gọi `refresh()` trong constructor, nên callback được gọi **trước** khi câu lệnh `context.getBean(ModuleInspector.class)` ở `Main` chạy. Mảng tên module được sort trước khi in nên kết quả độc lập với việc Spring chọn tạo `alpha` hay `beta` trước. Đây là chương trình một context, không có bean lazy hay lifecycle callback khác can thiệp.

**Tại sao ví dụ chứng minh đúng điểm học?** Nếu `afterSingletonsInstantiated()` được gọi, cả `alpha` và `beta` đã có instance và đã hoàn thành `InitializingBean.afterPropertiesSet()`; điều kiện kiểm tra `initialized()` đều đúng. Nếu đổi `ModuleInspector` để làm cùng phép tìm kiếm trong constructor hoặc `@PostConstruct` của inspector, việc lookup có thể kích hoạt tạo những module chưa được tạo trước đó. Đó là side effect mà callback cuối pha singleton giúp tránh đối với regular singleton.

### Phiên bản với interface marker

Cơ chế này không yêu cầu bean phải khai báo annotation đặc biệt. Bất kỳ singleton thích hợp nào cũng có thể implement interface:

```java
@Component
public class StartupRegistry implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Validate hoặc tổng hợp registry từ các regular singleton đã tạo.
    }
}
```

Đoạn này minh họa; khi dùng, import `org.springframework.stereotype.Component` và `org.springframework.beans.factory.SmartInitializingSingleton`, đặt trong component-scan context. Nếu class không được đăng ký thành Spring singleton bean, sẽ không có callback dù nó implements interface.

## 5. Khái niệm “tất cả singleton” có giới hạn chính xác

Phải đọc cụm “all regular singleton beans” theo đúng ngữ cảnh. Nó chỉ những singleton thông thường được xử lý ở pha pre-instantiation, **không** phải “mọi object thuộc mọi scope trên mọi container”.

| Trường hợp | Có nằm trong bảo đảm cuối pre-instantiation? | Kết luận về callback |
| --- | --- | --- |
| Singleton mặc định eager, được Spring quản lý | Có, trường hợp chuẩn | Nếu implement interface thì callback được gọi |
| Singleton `@Lazy` chưa tạo trong lúc bootstrap | Không | Tạo muộn theo yêu cầu không khiến callback tự được gọi lại |
| Prototype | Không | Không được gọi `afterSingletonsInstantiated()` theo hợp đồng scope |
| HTTP request/session/application scoped target | Không thuộc regular singleton pre-instantiation | Không trông chờ callback này theo mỗi request/session |
| WebSocket scoped target | Không | Dùng cơ chế vòng đời phù hợp với WebSocket session |
| Bean mới đăng ký/tạo sau context refresh | Không được hồi tố | Callback bootstrap không phải listener động cho bean mới |
| Singleton ở **ApplicationContext khác** | Không thuộc cùng BeanFactory | Mỗi container xử lý pha bootstrap của mình |

**Lazy singleton:** Nếu định nghĩa một bean `@Lazy` và chỉ gọi `getBean()` sau khi context refresh, dù nó implements `SmartInitializingSingleton`, callback **không tự chạy** cho singleton tạo theo nhu cầu sau bootstrap. Vì vậy, không đặt tính năng bắt buộc của lazy service vào callback này. Với lazy bean, việc phải làm khi tạo nên nằm ở constructor, `@PostConstruct` hoặc `InitializingBean` của chính bean đó.

Ví dụ anti-pattern (đoạn minh họa):

```java
@Lazy
@Component
class LazyIndexer implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Không kỳ vọng được gọi nếu LazyIndexer mới tạo sau bootstrap.
    }
}
```

Đoạn trên cần import `Lazy`, `Component` và `SmartInitializingSingleton`; nó không phải source chạy độc lập. Nếu bean lazy vô tình bị dependency hoặc lookup khác buộc tạo **trước khi** pha bootstrap kết thúc, hành vi quan sát có thể khác; quy tắc an toàn là **không dựa** vào callback này cho lazy-on-demand singleton.

**Bean từ factory:** `FactoryBean` và `SmartFactoryBean` có quy tắc phát hiện kiểu và eager initialization riêng, khác một object singleton thông thường. Không nên suy từ tên/loại `FactoryBean` rằng mọi sản phẩm của factory đều đã được tạo khi callback chạy; nếu thiết kế yêu cầu, kiểm tra flags và bảo đảm instance cụ thể qua dependency rõ ràng.

**Background bootstrap:** Spring Framework 6.2 giới thiệu tùy chọn `@Bean(bootstrap = Bean.Bootstrap.BACKGROUND)` đối với một số cách cấu hình. Những singleton background thường phải hoàn tất trong giai đoạn hoàn thiện startup thông thường; bean vừa `@Lazy` vừa background có thể được hoàn tất trễ hơn. Khi cần một quan hệ happens-before cụ thể, khai báo dependency explicit thay vì dựa vào giả định thứ tự thread.

## 6. So sánh với @PostConstruct, InitializingBean và ContextRefreshedEvent

### @PostConstruct: initialization của *chính bean*

```java
@Component
class SchemaLoader {
    @PostConstruct
    void loadOwnSchema() {
        // Dependency đã được inject cho bean này.
    }
}
```

Cần import `Component` và `jakarta.annotation.PostConstruct`; đây là fragment minh họa. Callback chạy trong giai đoạn tạo instance, không đợi tất cả unrelated singletons. Phù hợp validate property, tạo parser, chuẩn bị map bất biến. Với Spring 6+/Java 17, dùng `jakarta.annotation.PostConstruct`, không dùng `javax.annotation.PostConstruct` cũ.

### InitializingBean.afterPropertiesSet(): cũng thuộc từng bean

```java
public class LocalIndex implements InitializingBean {
    @Override
    public void afterPropertiesSet() {
        // Sau populate properties của LocalIndex,
        // nhưng có thể trước lúc singleton khác được tạo.
    }
}
```

Đây là fragment cần import `org.springframework.beans.factory.InitializingBean`. `InitializingBean` bị ràng buộc trực tiếp với Spring API, và khác `SmartInitializingSingleton` ở phạm vi thời gian: callback này ngay sau local initialization; callback “smart” sau **toàn bộ pha pre-instantiation**.

### ContextRefreshedEvent: sự kiện cấp context

```java
@Component
class ContextObserver {
    @EventListener(ContextRefreshedEvent.class)
    public void refreshed() {
        // ApplicationContext vừa refresh thành công.
    }
}
```

Đoạn này cần các import `Component`, `EventListener` và `ContextRefreshedEvent`. Event có ý nghĩa cấp `ApplicationContext`, nên trong parent/child context hierarchy, listener có thể thấy event của các context khác nhau tùy cách truyền sự kiện và listener được đăng ký. Nếu chỉ cần cuối pha tạo singleton của một BeanFactory, `SmartInitializingSingleton` tránh việc phải phân biệt event nguồn.

Ngoài ra, `SmartInitializingSingleton` thuộc module `spring-beans` và làm việc cả với `ListableBeanFactory` phù hợp, không bắt buộc phải có cả hệ thống event của `ApplicationContext`. Ngược lại, `ContextRefreshedEvent` yêu cầu context có cơ chế event.

### Khi nào dùng ApplicationRunner / CommandLineRunner?

Trong Spring Boot, runner phù hợp với công việc khởi động cấp ứng dụng sau khi container đã được refresh, chẳng hạn đọc tham số CLI hoặc chạy logic bootstrap có điều kiện. Đừng dùng `SmartInitializingSingleton` chỉ vì muốn thực hiện job “một lần toàn cluster”: nếu có 3 replica, mỗi instance/container vẫn có pha bootstrap riêng.

### Khi nào dùng Lifecycle / SmartLifecycle?

Nếu cần **start/stop một kết nối, polling loop, consumer hay scheduled task**, nên dùng `Lifecycle`/`SmartLifecycle` hoặc infrastructure Spring quản lý. Chúng hỗ trợ start/stop và `SmartLifecycle` cung cấp phase cùng khả năng auto-startup. `SmartInitializingSingleton` chỉ có một callback init, không quản lý shutdown, hủy task, readiness hoặc lifecycle restart.

| Yêu cầu | Lựa chọn thường thích hợp |
| --- | --- |
| Khởi tạo một bean từ dependencies của chính nó | Constructor / `@PostConstruct` / `InitializingBean` |
| Tổng hợp nhiều regular singleton sau bootstrap | `SmartInitializingSingleton` |
| Phản ứng khi ApplicationContext refresh | `ContextRefreshedEvent` |
| Startup logic cấp Spring Boot | `ApplicationRunner`/`CommandLineRunner` |
| Quản lý start, stop, phase, cleanup cho task sống lâu | `SmartLifecycle` / `Lifecycle` |
| Chỉ định bean X tạo trước bean Y | Dependency constructor hoặc `@DependsOn` |
| Tác vụ chỉ chạy một lần trên toàn cluster | Coordination/leader election/lock bên ngoài JVM, tùy nghiệp vụ |

## 7. Dùng getBeansOfType và registry đúng cách

Một pattern hợp lý là các strategy singleton đăng ký bằng Spring, cuối pha startup xây một registry:

```java
public interface Exporter {
    String format();
    byte[] export(byte[] input);
}
```

```java
@Component
class ExportRegistry implements SmartInitializingSingleton {
    private final ListableBeanFactory factory;
    private Map<String, Exporter> byFormat = Map.of();

    ExportRegistry(ListableBeanFactory factory) {
        this.factory = factory;
    }

    @Override
    public void afterSingletonsInstantiated() {
        Map<String, Exporter> collected = new HashMap<>();

        for (Exporter exporter : factory.getBeansOfType(Exporter.class).values()) {
            Exporter previous = collected.putIfAbsent(exporter.format(), exporter);
            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate exporter format: " + exporter.format());
            }
        }
        byFormat = Map.copyOf(collected);
    }

    public Exporter require(String format) {
        Exporter exporter = byFormat.get(format);
        if (exporter == null) {
            throw new IllegalArgumentException("Unknown format: " + format);
        }
        return exporter;
    }
}
```

Các snippet registry minh họa một cách áp dụng, không phải project chạy độc lập. Chúng cần import `Component`, `ListableBeanFactory`, `SmartInitializingSingleton`, `Map` và `HashMap`; các implementation cụ thể của `Exporter` phải có trong ứng dụng. Registry dùng `putIfAbsent` để phát hiện trùng key và `Map.copyOf` tạo map bất biến khi xong. Cơ chế này giả định registry được sử dụng **sau** khi callback hoàn tất. Đừng làm bean khác gọi `registry.require(...)` ngay trong `@PostConstruct` của nó, vì lúc ấy callback registry có thể chưa được gọi.

Nếu registry phải được update động lúc runtime, callback bootstrap không đủ. Khi đó cần thêm cơ chế update có synchronization/publication đúng: immutable snapshots qua `AtomicReference<Map<...>>`, application events theo bài toán, hoặc mô hình đăng ký explicit.

**Thận trọng khi tìm theo type:**
- `getBeansOfType(Exporter.class)` trả bean theo type mà container có thể xác định. Trong cấu hình đa dạng, proxy, generics hoặc `FactoryBean` có thể ảnh hưởng type detection.
- Lookup có thể tạo lazy singleton mà trước đó chưa được tạo. Chỉ scan “tất cả” khi chấp nhận tác động đó, hoặc dùng API liệt kê tên không eager và lọc theo scope/bean definition.
- Nếu cần loại bỏ prototype khỏi registry, phải xét scope thực tế. Lookup theo type không đồng nghĩa danh sách chỉ singleton.
- Nếu exporter phụ thuộc ngược vào registry và registry lại gọi exporter trong callback, phải tránh cycle/logic gọi quá sớm.
- Khi nhiều exporter cung cấp cùng format, quy định conflict policy rõ. Không được mặc định chiến thắng thuộc bean “tạo trước” vì thứ tự không phải hợp đồng ứng dụng.
- Một số bean hạ tầng có thể tạo proxy ở bước post-processing; callback cuối pha pre-instantiation giúp truy cập những bean thông thường đã qua initialization, nhưng vẫn phải dùng public API và không giả định target type là implementation cụ thể.

## 8. Thứ tự callback giữa các SmartInitializingSingleton

Giả sử hai bean độc lập cùng implement `SmartInitializingSingleton`:

```java
@Component
class RegistryA implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Điền dữ liệu A.
    }
}

@Component
class RegistryB implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Dùng dữ liệu A?
    }
}
```

Các class trên cần import `Component` và `SmartInitializingSingleton`. Không nên giả định callback của A chắc chắn chạy trước callback B dựa vào thứ tự tên, cách scan classpath, hay chỉ vì đánh dấu `@Order`. Interface này không có contract về sequencing các callback có quan hệ phụ thuộc. Chúng có thể được gọi theo thứ tự đăng ký singleton trong triển khai cụ thể, nhưng thứ tự đó có thể thay đổi khi cấu hình thay đổi.

Để đáp ứng invariant “B cần kết quả hoàn tất của A”, có thể:
1. Gom việc dựng A và B trong **một** orchestration bean; gọi `prepareA()` rồi `prepareB()` trong cùng callback.
2. Đặt dữ liệu A ở state đã chuẩn bị trong local init (`@PostConstruct`) của A, để callback B đọc dữ liệu đó sau pre-instantiation.
3. Nếu đây là việc quản lý process chạy lâu hoặc có nhiều phase, dùng `SmartLifecycle` với phase/depends-on phù hợp.
4. Thiết kế một API tường minh trả về dữ liệu hoàn chỉnh, tránh phụ thuộc timing của hai callback.

`@DependsOn("registryA")` bảo đảm dependency được **khởi tạo** trước bean phụ thuộc, nhưng không đồng nghĩa callback `afterSingletonsInstantiated()` của registry A đã chạy trước callback của B: cả hai callback đều thuộc pha sau cùng. Đây là khác biệt dễ bỏ sót giữa thứ tự bean initialization và thứ tự callback smart.

## 9. Nếu callback ném exception

`afterSingletonsInstantiated()` chạy trong quá trình Spring hoàn tất bootstrap. Nếu method ném unchecked exception, context refresh có thể thất bại; ứng dụng thường báo startup error kèm nguyên nhân. Với registry cần đảm bảo nhất quán, đây có thể là cơ chế **fail fast** phù hợp:

```java
@Override
public void afterSingletonsInstantiated() {
    if (requiredStrategies.isEmpty()) {
        throw new IllegalStateException(
                "No strategy bean registered for this application");
    }
}
```

Đây là fragment thuộc một class đã implement interface, cần field `requiredStrategies` có kiểu phù hợp; không phải source chạy độc lập. Nếu callback tạo tài nguyên rồi thất bại, đừng trông chờ mọi cleanup hook sẽ chạy trong mọi tình huống, đặc biệt khi process crash hoặc context chưa refresh xong. Quản lý cleanup cục bộ và chỉ publish trạng thái hoàn chỉnh khi validate xong.

Phân biệt:
- **Vi phạm cấu hình bắt buộc**: nên ném exception rõ, dừng startup.
- **Service ngoài tạm thời chưa sẵn sàng**: tránh loop vô hạn hoặc chặn khởi động không có timeout; cân nhắc readiness/retry sau startup.
- **Tác vụ bất đồng bộ dài**: dùng lifecycle component/runner phù hợp, không khởi thread tự phát từ callback rồi bỏ mặc shutdown.

Một bean được tạo trong startup callback có thể kéo theo side effect mới và làm “regular singleton đã tạo xong” trở nên khó quan sát hơn; hãy giữ callback hướng vào **validation, registry synthesis, chuẩn bị state** dựa trên các dependency đã có.

## 10. Concurrency, các container và phạm vi ứng dụng

`SmartInitializingSingleton` thường chạy đồng bộ trong quá trình `preInstantiateSingletons()` của một BeanFactory thông thường. Nhưng callback **không** cấp một lock cho mọi singleton hay làm mọi object trở nên thread-safe. Nếu callback publish registry mutable cho nhiều request sau đó, bạn vẫn cần bảo đảm người đọc chỉ nhìn trạng thái hoàn chỉnh và mọi update runtime được đồng bộ đúng.

Với ứng dụng không expose bean ra thread khác trước khi khởi tạo xong, lưu snapshot immutable trong callback có thể đủ cho nhiều luồng cùng đọc sau startup. Tuy nhiên nếu bean tự escape vào thread khác trong constructor/init hoặc cập nhật state sau khi publish, không được dựa vào bootstrap callback để thay synchronization.

### Parent/child contexts

Một ứng dụng có thể có root ApplicationContext và một hoặc nhiều child contexts (ví dụ các thành phần web được cấu hình riêng). Mỗi BeanFactory bootstrap singleton của **chính nó**. Callback trong child không làm root/child thành một phạm vi singleton toàn JVM. Nếu cần phối hợp contexts, làm rõ nơi sở hữu bean và lifetime, không mặc định callback “một lần cho mọi ApplicationContext”.

### Nhiều process/pod

Nhiều replica triển khai cùng ứng dụng đều có BeanFactory riêng và chạy callback bootstrap của chúng. Không dùng `afterSingletonsInstantiated()` để thực hiện migration, gửi email, reset data hoặc chạy job chỉ được phép xảy ra **chính xác một lần toàn hệ thống**. Đối với việc đó, dùng migration tooling, DB constraint, distributed leader/lock hoặc job service có semantics phù hợp.

### Khi dùng Spring Boot

Trong Spring Boot, `ApplicationContext` được refresh trước khi các runner được thực thi; `SmartInitializingSingleton` thuộc quá trình bean factory bootstrap, không phải callback “server đã bắt đầu nghe port”. Nếu cần đảm bảo hệ thống sẵn sàng phục vụ traffic, dùng cơ chế lifecycle và readiness của Boot phù hợp, xác minh từng external dependency theo yêu cầu, thay vì đồng nhất callback này với trạng thái Ready.

## 11. Những lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Method `afterSingletonsInstantiated()` không được gọi | Object tạo bằng `new` hoặc không đăng ký thành Spring-managed singleton | Đăng ký `@Component`/`@Bean` phù hợp, để BeanFactory tạo instance |
| Lazy singleton được tạo sau startup nhưng callback không chạy | Callback chỉ có ở cuối pha pre-instantiation | Dùng `@PostConstruct`/`InitializingBean` cho initialization của bean lazy |
| Prototype implements interface nhưng không có callback | Interface không phải lifecycle per prototype | Dùng local initialization phù hợp |
| Bean A trong `@PostConstruct` lấy toàn bộ beans theo type | Lookup có thể khiến bean khác bị eager initialized sớm | Chuyển registry toàn bộ regular singleton sang callback smart |
| Gọi `getBeansOfType()` và bất ngờ thấy bean lazy tạo mới | Method có thể instantiate bean được liệt kê | Dùng type/name discovery có kiểm soát, lọc scope và tránh gọi `getBean` không cần |
| Registry bị đọc trước callback | Bean khác gọi registry trong local init | Tránh lookup lúc local init, thiết kế readiness hoặc tạo sau bootstrap |
| Chỉ định `@Order`/`@DependsOn` và kỳ vọng callback smart có thứ tự | Khởi tạo bean trước không bảo đảm callback smart chạy trước | Gom orchestration hoặc chọn lifecycle có phase |
| Khởi động background consumer trực tiếp từ callback | Interface không hỗ trợ stop/phase/readiness | Dùng `SmartLifecycle`, listener container, executor do Spring quản lý |
| Test gọi `getBean` mà không thấy smart callback | Test dùng BeanFactory chưa gọi `preInstantiateSingletons()` hoặc object không đi qua container | Dùng `AnnotationConfigApplicationContext.refresh()` hoặc gọi bootstrap trên BeanFactory phù hợp |
| Callback bị chạy ở nhiều pod | Mỗi context có lifecycle riêng | Thiết kế phối hợp distributed khi cần exactly-once |
| Callback chạy trước `ContextRefreshedEvent` | Đây là thứ tự chuẩn trong context refresh | Chọn `ContextRefreshedEvent` nếu cần sự kiện cấp context |
| Callback báo lỗi làm startup fail | Vi phạm invariant hoặc unchecked exception | Validate có chủ đích, nêu lý do rõ và xử lý cleanup |
| Xây registry mutable rồi cập nhật về sau không đồng bộ | Callback bootstrap không đồng nghĩa synchronization runtime | Dùng immutable snapshot/atomic publication hoặc lock đúng invariant |

## 12. Bài tập tự kiểm tra

1. `@PostConstruct` khác `SmartInitializingSingleton.afterSingletonsInstantiated()` ở khía cạnh nào?
2. Trong context có 5 singleton eager, một inspector implements interface, tại thời điểm callback inspector bắt đầu thì những regular singleton đó đã hoàn thành initialization thông thường chưa?
3. Một bean `@Lazy` chưa tạo lúc startup nhưng mới được tạo bằng `getBean` sau context refresh. Callback smart của bean đó có tự chạy không?
4. Một bean prototype implements `SmartInitializingSingleton`, cứ tạo prototype mới là callback smart được gọi chứ?
5. Nếu từ `@PostConstruct` của bean A gọi `getBeansOfType(Handler.class)`, điều gì có thể xảy ra với các bean chưa đến lượt tạo?
6. Vì sao `afterSingletonsInstantiated()` thích hợp để build registry của các strategy eager singleton?
7. `@DependsOn("A")` cho bean B có bảo đảm callback smart của A chạy trước callback smart của B không?
8. Chọn hook nào để quản lý start/stop một consumer chạy lâu dài?
9. Một Spring Boot service có 4 pod. Callback smart của một bean singleton được gọi mấy lần tổng cộng nếu mỗi pod có một container tương ứng và callback đủ điều kiện?
10. Nếu cần đọc tất cả singleton mà không tạo `FactoryBean` sớm, bạn cần cân nhắc tham số nào của `getBeanNamesForType`?
11. Có nên dùng callback smart để xác định HTTP server đang sẵn sàng nhận traffic không?
12. Trong ví dụ runnable, tại sao `callback: alpha,beta initialized` được in trước `main: checked=true`?

**Đáp án gợi ý:**

1. `@PostConstruct` chạy theo vòng đời **mỗi bean**; callback smart chạy sau pha tạo regular singleton.
2. Có, trong phạm vi bảo đảm của pre-instantiation.
3. Không; bean lazy-on-demand sau bootstrap không được gọi lại callback đó.
4. Không; prototype không thuộc callback smart của singleton bootstrap.
5. Lookup có thể khởi tạo các handler còn chưa được tạo, làm phát sinh side effect trong local initialization của A.
6. Các regular singleton đã tạo và local init xong, tránh tạo chúng quá sớm chỉ vì quét registry.
7. Không; phụ thuộc khởi tạo không xác lập thứ tự giữa hai callback smart.
8. `Lifecycle`/`SmartLifecycle` hoặc container quản lý listener/consumer.
9. Có thể bốn lần, mỗi container một lần; không phải một lần toàn cluster.
10. Tham số `allowEagerInit` và quy tắc lọc singleton/FactoryBean; không lấy kết quả lookup làm bảo đảm không side effect nếu sau đó gọi `getBean()`.
11. Không; đây là mốc BeanFactory bootstrap, không phải health/readiness.
12. Constructor `AnnotationConfigApplicationContext(AppConfig.class)` gọi refresh trước khi trả về, nên callback bootstrap hoàn tất trước khi main lấy bean.

## Tài liệu chính thức

- Spring Framework 6.2.18 — `SmartInitializingSingleton` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html
- Spring Framework — Bean Lifecycle / Customizing Bean Nature: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Java-based Container Configuration, singleton startup, lazy and depends-on: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Framework — `ConfigurableListableBeanFactory.preInstantiateSingletons()`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/config/ConfigurableListableBeanFactory.html
- Spring Framework — `ListableBeanFactory` và `getBeansOfType`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html
- Spring Framework — `SmartLifecycle`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/SmartLifecycle.html
