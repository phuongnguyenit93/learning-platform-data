# Kết hợp nhiều nguồn cấu hình trong một Spring ApplicationContext

## 1. Đặt vấn đề

Trong một dự án Spring Framework, không phải tất cả bean đều đến từ cùng một file hoặc cùng một cách khai báo. Một ứng dụng đang phát triển có thể có:

- Những bean do ứng dụng tạo bằng **Java configuration** (`@Configuration` và `@Bean`).
- Những bean còn giữ trong **XML configuration** của hệ thống lâu năm.
- Những service/adapters được phát hiện qua **component scanning** (`@ComponentScan` cùng `@Component`, `@Service`, `@Repository`,...).
- Những bean được đăng ký **bằng chương trình** khi bootstrap (`register`, `registerBean`, `registerBeanDefinition`).
- Các cấu hình nhỏ được ghép qua **`@Import`**, hoặc nguồn XML được kết nối bằng **`@ImportResource`**.

Spring có thể đưa những **bean definitions** này vào **một IoC Container**, rồi giải quyết dependency giữa chúng mà không bắt buộc tất cả class cùng sử dụng một annotation.

Ý nghĩa của chủ đề không chỉ là “nạp nhiều file”: điều cần hiểu là **nguồn cấu hình đóng góp metadata**, còn **một BeanFactory/ApplicationContext** dùng metadata đó để tạo và quản lý object theo quy tắc chung. Kết quả là một bean từ XML có thể được inject vào service được component scan, và một bean từ `@Bean` có thể cùng sử dụng bean đăng ký chương trình.

### Mục tiêu sau bài học

Bạn sẽ biết cách:

1. Phân biệt **nguồn bean definitions** với **nguồn properties** và với **nhiều ApplicationContext riêng biệt**.
2. Ghép Java configuration bằng `@Import` và XML bằng `@ImportResource`.
3. Kết hợp `@ComponentScan` với các bean `@Bean`, XML và đăng ký bằng `registerBean`.
4. Tạo context theo đúng trình tự **đăng ký nguồn → `refresh()` → sử dụng → `close()`**.
5. Giải quyết dependency xuyên các nguồn; xử lý bean cùng tên, nhiều ứng viên cùng kiểu, thứ tự khởi tạo và processor.
6. Chọn chiến lược tích hợp XML cũ với Java configuration mới mà không vô tình tạo context lồng nhau.
7. Chạy một ví dụ Java 17+ với **bốn cách đăng ký bean khác nhau** cùng hoạt động trong **một `AnnotationConfigApplicationContext`**.

## 2. Khái niệm trung tâm: một context, nhiều nguồn metadata

Spring bean là một object được container quản lý theo bean definition/registration. Container cần biết bean class hoặc supplier/factory, tên, scope, phụ thuộc và các thuộc tính quản lý khác. Metadata ấy có thể đến từ nhiều nơi.

```text
Java @Configuration/@Bean ─────┐
                              │
XML <bean> / @ImportResource ──┤
                              │
@ComponentScan ────────────────┼──> BeanDefinitionRegistry
                              │             │
registerBean(...) ────────────┘             v
                                     BeanFactory / Context
                                              │
                                Dependency resolution + lifecycle
                                              │
                                       Bean instances
                                              │
                                  Một ApplicationContext
```

**Một context** nghĩa là những registrations cùng đóng góp vào **một registry/factory và cùng cơ chế giải quyết dependency**. Bean singleton mặc định là singleton **trong container đó**, không phải singleton toàn JVM.

Ví dụ:

- `Formatter` đến từ Java `@Bean`.
- `LegacyPrefixer` đến từ XML `<bean>`.
- `AggregationService` đến từ `@ComponentScan`.
- `AuditSink` đến từ `context.registerBean(...)`.

Khi `AggregationService` có constructor cần cả ba dependency, Spring tìm ứng viên trong cùng context và inject chúng; service **không cần biết** mỗi dependency đã được khai báo bằng hình thức nào.

### Không nhầm “nhiều nguồn” với “nhiều container”

Nếu bạn tạo:

```java
var context1 = new AnnotationConfigApplicationContext(JavaConfig.class);
var context2 = new ClassPathXmlApplicationContext("legacy.xml");
```

đây là **hai ApplicationContext riêng**, không tự chia sẻ registry hoặc singleton cache. Để lấy bean từ context khác, phải thiết lập quan hệ parent-child hoặc kết nối có chủ đích. Điều đó **khác** với việc Java và XML cùng đóng góp bean definitions vào **một** context.

Đoạn trên là snippet minh họa; cần imports và `JavaConfig`, `legacy.xml` thực tế. Đừng dùng nó nếu mục tiêu là ghép bean vào cùng một context.

## 3. Năm cách đóng góp cấu hình thường gặp

| Cách | Ví dụ | Tác dụng | Tình huống phù hợp |
| --- | --- | --- | --- |
| Java factory method | `@Bean Formatter formatter()` | Đăng ký bean từ factory method | Object thư viện, cấu hình rõ ràng, builder |
| Java configuration import | `@Import(PricingConfig.class)` | Nạp thêm configuration/type | Ghép module chức năng |
| XML import | `@ImportResource("classpath:legacy.xml")` | Nạp XML bean definitions vào context Java | Tích hợp XML cũ, XML namespace đặc biệt |
| Component scanning | `@ComponentScan(basePackageClasses=JobService.class)` | Tìm class mang stereotype/filter | Service, adapter và component tự quản lý source |
| Programmatic registration | `context.registerBean("auditSink", AuditSink.class, AuditSink::new)` | Đăng ký bean theo API trước refresh | Bootstrap động, fixture test, plugin/module runtime |

Các cách này **có thể phối hợp**. Tuy nhiên, một bean nên có **registration owner rõ ràng**; không được mặc định rằng khai báo trùng một class theo nhiều nguồn sẽ được Spring tự “gộp” thành một bean.

## 4. Cách 1 — Java @Configuration và @Bean

Java configuration biểu diễn nguồn bean definitions bằng source Java có type checking:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FormattingConfiguration {
    @Bean
    Formatter formatter() {
        return new Formatter("java");
    }
}
```

Đây là cấu hình rút gọn, giả định `Formatter` là class trong dự án có constructor nhận `String`. Trong demo hoàn chỉnh bên dưới, class đó sẽ được khai báo thật.

Khi `FormattingConfiguration` được nạp qua `@Import` hoặc `register`, Spring nhận diện factory method và đăng ký bean tên `formatter`. Khi cần tạo object, Spring gọi method và quản lý kết quả theo scope/lifecycle.

**Đặc điểm:**

- Return type của `@Bean` giúp Spring dự đoán type để giải quyết dependency.
- Factory method có thể nhận bean dependency thông qua tham số: `Formatter formatter(AppSettings settings)`.
- Không cần `@Component` trên class object trả về.
- `proxyBeanMethods=false` không tắt `@Bean`; nó chỉ tắt inter-bean method interception trong configuration class đó. Dùng method parameter injection để ghép bean, tránh gọi chéo factory methods theo cách tạo object phụ.
- Một class có `@Configuration` trong source code vẫn cần được **nạp vào context** bằng đường hợp lệ; annotation tự nó không tạo context.

## 5. Cách 2 — @Import ghép nhiều Java configuration

Giả sử module báo cáo khai báo bean, còn module định dạng cung cấp dependency:

```java
@Configuration(proxyBeanMethods = false)
@Import(FormattingConfiguration.class)
public class ReportsConfiguration {
    @Bean
    ReportService reportService(Formatter formatter) {
        return new ReportService(formatter);
    }
}
```

`ReportService` và `Formatter` là kiểu ví dụ; đoạn này đặt trong class có imports tương ứng. Khi `ReportsConfiguration` được register, Spring xử lý `@Import` rồi đăng ký definitions từ `FormattingConfiguration`.

Cách này có hai lợi ích chính:

1. **Composition rõ ràng:** chỉ nạp cấu hình gốc, các nguồn con được import theo thiết kế.
2. **Dependency tường minh:** method `reportService(Formatter formatter)` nói cần bean `Formatter`; không gọi `new FormattingConfiguration().formatter()`.

`@Import` không tạo context con. Hai bean cùng nằm trong container đang được xây dựng. Một ứng dụng cũng có thể dùng `context.register(ConfigA.class, ConfigB.class)` thay vì cấu hình import tập trung; hai cách là những con đường nạp configuration metadata, không phải hai loại bean khác nhau.

## 6. Cách 3 — XML bean definitions qua @ImportResource

Trong hệ thống đang di chuyển từ XML sang Java configuration, Spring cho phép giữ một số bean trong XML và nạp vào context Java bằng `@ImportResource`.

**Java configuration:**

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-beans.xml")
public class ApplicationConfiguration {
}
```

**`src/main/resources/legacy-beans.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="legacyPrefixer" class="demo.legacy.LegacyPrefixer">
        <constructor-arg value="xml"/>
    </bean>
</beans>
```

Class `demo.legacy.LegacyPrefixer` phải tồn tại trên classpath và có constructor nhận `String`. File XML thuộc **classpath resource**, được Gradle đặt vào runtime classpath từ `src/main/resources`.

**Khi nào có lợi?**

- Có nhiều definitions XML cũ chưa muốn chuyển toàn bộ.
- Một thư viện/framework tích hợp bằng XML namespace tiện hơn Java config.
- Muốn triển khai theo kiểu Java-centric: cấu hình mới viết Java, phần legacy chỉ import nơi cần.

`@ImportResource` giúp **XML và Java cùng góp definitions vào một context**; không tạo một `ClassPathXmlApplicationContext` khác ở hậu trường cho từng file import.

### 6.1. Java-centric hay XML-centric?

**Java-centric** dùng `AnnotationConfigApplicationContext` làm điểm khởi động và `@ImportResource` nạp bean definitions XML vào **cùng context**. **XML-centric** có thể dùng `ClassPathXmlApplicationContext`, khai báo Java configuration classes trong XML và bật annotation configuration processing phù hợp (chẳng hạn `<context:annotation-config/>`). Hai cách đều hợp lệ; không tự mở hai context độc lập rồi giả định chúng chia sẻ beans.

### 6.2. Khác biệt với XML `<import/>`

XML `<import resource="feature-beans.xml"/>` nạp thêm XML từ resource hiện tại; `@ImportResource("classpath:...")` nạp XML từ Java configuration; `@Import(SomeConfig.class)` nạp class/selector/registrar qua Java metadata. Trong bài tổng hợp này, cả ba là **nguồn bean definitions cho cùng container**. Cách khai báo đường dẫn, namespace, alias và lộ trình chuyển đổi XML được thực hành riêng ở bài `@ImportResource` tiếp theo.

## 7. Cách 4 — @ComponentScan và stereotype

Một class do ứng dụng quản lý source có thể mang `@Component`:

```java
package demo.scanned;

import org.springframework.stereotype.Component;

@Component
public final class HealthMarker {
    public String label() {
        return "scanned";
    }
}
```

Một configuration class có:

```java
@ComponentScan(basePackageClasses = HealthMarker.class)
```

sẽ scan **package chứa `HealthMarker` và các package con**, không chỉ riêng `HealthMarker`. Scanner mặc định nhận `@Component` và các stereotype/meta-annotations phù hợp.

Nhiều nguồn cấu hình kết hợp hữu ích vì class được scan **có thể inject** bean từ XML, `@Bean` hay registration API. Ví dụ:

```java
@Component
public final class ReportCoordinator {
    private final Formatter formatter;
    private final LegacyPrefixer prefixer;

    public ReportCoordinator(Formatter formatter, LegacyPrefixer prefixer) {
        this.formatter = formatter;
        this.prefixer = prefixer;
    }

    public String format(String value) {
        return prefixer.wrap(formatter.format(value));
    }
}
```

Đây là một class minh họa (cần package/import các kiểu), không phải file độc lập của demo chính. Constructor duy nhất thường được Spring tự chọn để inject mà không cần `@Autowired`. Quan trọng là **hai dependency không nhất thiết được scan**: chúng có thể đến từ Java hoặc XML.

### 7.1. Tại sao nên giới hạn phạm vi scan?

Nếu scan package gốc quá rộng, Spring có thể tìm thêm:

- Nhiều `@Configuration` ngoài ý định, kéo theo `@Bean` definitions khác.
- Một implementation dự kiến chỉ dùng trong test.
- Các component cùng bean name hoặc cùng interface dẫn đến trùng/mơ hồ.
- Component của module không muốn bật.

Vì vậy `basePackageClasses` hoặc `basePackages` nên gắn với ranh giới phù hợp. `@Import` ở composition root giúp thấy rõ modules, `@ComponentScan` giúp module chọn các class do nó sở hữu; cả hai không mâu thuẫn.

## 8. Cách 5 — Đăng ký bằng chương trình trước refresh()

Spring cho phép đăng ký bean bằng Java API:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.registerBean(
        "auditSink",
        AuditSink.class,
        AuditSink::new
);

context.register(AppConfiguration.class);
context.refresh();
```

`AppConfiguration` và `AuditSink` là các kiểu minh họa; cần import `AnnotationConfigApplicationContext`. API `registerBean` nhận tên, bean class và `Supplier`, tạo bean definition để container sử dụng khi khởi tạo.

**Không nhầm hai cách:**

- `context.registerBean("auditSink", AuditSink.class, AuditSink::new)`: đăng ký **bean definition có supplier**; Spring quản lý instance được tạo theo definition.
- `AuditSink sink = new AuditSink()` ở một biến Java bên ngoài: chỉ tạo object Java. Nó không tự trở thành Spring bean và không tự được inject/callback khi chưa đăng ký theo API phù hợp.

### 8.1. Vì sao phải register trước refresh?

`AnnotationConfigApplicationContext` có constructor rỗng để bạn thêm cấu hình bằng `register(...)`, `scan(...)` và `registerBean(...)`, rồi **gọi `refresh()`** cho Spring xử lý metadata/processor và tạo các singleton cần thiết.

Thứ tự bootstrap khuyến nghị:

```text
new AnnotationConfigApplicationContext()
   |
register(AppConfiguration.class)
registerBean("auditSink", AuditSink.class, AuditSink::new)
   |
refresh()
   |
getBean(AggregationService.class)
   |
close()
```

Trong một số biến thể container có API cho phép đăng ký definition sau khi đã refresh, nhưng **đừng dùng đó làm hành vi mặc định** khi bài toán là bootstrap nhiều nguồn: post-processor, singleton pre-instantiation, event/lifecycle và điều kiện cấu hình có thể đã chạy. Hãy hoàn tất registrations trước `refresh()` nếu muốn một tập bean definitions được xử lý nhất quán từ đầu.

### 8.2. registerBean khác register(Class...) và scan(String...)

- `register(AppConfiguration.class)`: đăng ký một **annotated component/configuration class** để Spring xử lý metadata của class ấy.
- `scan("demo.scanned")`: yêu cầu scanner tìm candidate trong package.
- `registerBean("auditSink", AuditSink.class, AuditSink::new)`: đăng ký một bean definition trực tiếp, không cần class có `@Component` hoặc scan.
- `registerBeanDefinition(...)` trên registry: API cấp thấp, cần cung cấp BeanDefinition phù hợp; thường chỉ cần cho framework/integration code.

Chúng là những cách khác nhau để **góp registrations vào cùng context**.

## 9. Ví dụ chạy được: Java + XML + component scan + programmatic bean

Đây là ví dụ trung tâm. Ta cần bốn bean từ bốn nguồn khác nhau:

| Bean | Class | Nguồn |
| --- | --- | --- |
| `formatter` | `Formatter` | `@Bean` từ Java configuration được `@Import` |
| `legacyPrefixer` | `LegacyPrefixer` | XML `<bean>` được `@ImportResource` |
| `aggregationService` | `AggregationService` | `@Component` được `@ComponentScan` |
| `auditSink` | `AuditSink` | `context.registerBean(...)` tại bootstrap |

`AggregationService` có constructor nhận **cả ba dependency**: `Formatter`, `LegacyPrefixer`, `AuditSink`. Spring phải tìm các bean theo type trong **một context** để khởi tạo được service.

### 9.1. Cấu trúc dự án

```text
multi-source-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── App.java
        │       ├── config/
        │       │   ├── AppConfiguration.java
        │       │   └── FormattingConfiguration.java
        │       ├── javaformat/
        │       │   └── Formatter.java
        │       ├── legacy/
        │       │   └── LegacyPrefixer.java
        │       ├── audit/
        │       │   └── AuditSink.java
        │       └── scanned/
        │           └── AggregationService.java
        └── resources/
            └── legacy-beans.xml
```

Mỗi public top-level class đặt trong file trùng tên với class và package khớp đường dẫn.

### 9.2. Gradle configuration

**`settings.gradle`**

```groovy
rootProject.name = 'multi-source-context-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.App'
}
```

Spring Context đã mang theo những dependency Spring Core/Beans cần thiết để xử lý XML và annotation configuration. Ví dụ chạy bằng Java 17+, không cần Spring Boot, servlet container hay database.

### 9.3. Bean Java: Formatter

**`src/main/java/demo/javaformat/Formatter.java`**

```java
package demo.javaformat;

import java.util.Objects;

public final class Formatter {
    private final String source;

    public Formatter(String source) {
        this.source = Objects.requireNonNull(source);
    }

    public String format(String value) {
        return source + "[" + value + "]";
    }
}
```

Class này **không có `@Component`**. Nó trở thành Spring bean nhờ factory method Java configuration.

**`src/main/java/demo/config/FormattingConfiguration.java`**

```java
package demo.config;

import demo.javaformat.Formatter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FormattingConfiguration {
    @Bean
    Formatter formatter() {
        return new Formatter("java");
    }
}
```

Bean name mặc định là `formatter`; return type là `Formatter`. Spring có thể inject nó cho service nằm ở package khác.

### 9.4. Bean XML: LegacyPrefixer

**`src/main/java/demo/legacy/LegacyPrefixer.java`**

```java
package demo.legacy;

import java.util.Objects;

public final class LegacyPrefixer {
    private final String prefix;

    public LegacyPrefixer(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String wrap(String input) {
        return prefix + "(" + input + ")";
    }
}
```

Không có stereotype hay Spring annotation.

**`src/main/resources/legacy-beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="legacyPrefixer" class="demo.legacy.LegacyPrefixer">
        <constructor-arg value="xml"/>
    </bean>
</beans>
```

Bean XML tên `legacyPrefixer` có constructor nhận chuỗi `xml`. XML là nguồn definition thứ hai, không phải một ApplicationContext độc lập.

### 9.5. Bean programmatic: AuditSink

**`src/main/java/demo/audit/AuditSink.java`**

```java
package demo.audit;

import java.util.concurrent.atomic.AtomicInteger;

public final class AuditSink {
    private final AtomicInteger records = new AtomicInteger();

    public String record(String message) {
        int number = records.incrementAndGet();
        return "AUDIT#" + number + ":" + message;
    }

    public int count() {
        return records.get();
    }
}
```

Class không mang stereotype. Chúng ta **không** viết `@Bean AuditSink` trong Java config và **không** khai báo nó trong XML. Entry point sẽ trực tiếp gọi API `registerBean` trước `refresh()`.

### 9.6. Bean component scan: AggregationService

**`src/main/java/demo/scanned/AggregationService.java`**

```java
package demo.scanned;

import demo.audit.AuditSink;
import demo.javaformat.Formatter;
import demo.legacy.LegacyPrefixer;

import org.springframework.stereotype.Component;

@Component
public final class AggregationService {
    private final Formatter formatter;
    private final LegacyPrefixer prefixer;
    private final AuditSink audit;

    public AggregationService(
            Formatter formatter,
            LegacyPrefixer prefixer,
            AuditSink audit) {
        this.formatter = formatter;
        this.prefixer = prefixer;
        this.audit = audit;
    }

    public String execute(String input) {
        return audit.record(
                prefixer.wrap(
                        formatter.format(input)
                )
        );
    }
}
```

Có **một constructor** cần ba dependency. Spring Framework 6.2 có thể constructor-inject constructor duy nhất dù không đặt `@Autowired`. Container sẽ tìm bean `Formatter`, `LegacyPrefixer` và `AuditSink` sau khi tất cả nguồn metadata đã được nạp.

Class được annotate `@Component` nên sẽ được scanner chọn, **nhưng scanner không tự tạo thêm ba dependency**. Chúng đến từ ba nguồn khác.

### 9.7. Composition root Java: import Java + XML + scan

**`src/main/java/demo/config/AppConfiguration.java`**

```java
package demo.config;

import demo.scanned.AggregationService;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportResource;

@Configuration(proxyBeanMethods = false)
@Import(FormattingConfiguration.class)
@ImportResource("classpath:legacy-beans.xml")
@ComponentScan(basePackageClasses = AggregationService.class)
public class AppConfiguration {
}
```

Ba annotations ghép các nguồn:

1. `@Import(FormattingConfiguration.class)`: nạp `@Bean Formatter` từ module Java.
2. `@ImportResource("classpath:legacy-beans.xml")`: nạp XML legacy bean.
3. `@ComponentScan(basePackageClasses = AggregationService.class)`: quét package `demo.scanned`, nhận `AggregationService`.

`AppConfiguration` **không đăng ký `AuditSink`**, vì nguồn programmatic sẽ đăng ký ở bootstrap. Tách việc đó ra để nhìn rõ tác dụng của API.

### 9.8. Entry point: một ApplicationContext duy nhất

**`src/main/java/demo/App.java`**

```java
package demo;

import demo.audit.AuditSink;
import demo.config.AppConfiguration;
import demo.scanned.AggregationService;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class App {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(AppConfiguration.class);
            context.registerBean(
                    "auditSink",
                    AuditSink.class,
                    AuditSink::new
            );

            context.refresh();

            System.out.println("java-bean="
                    + context.containsBean("formatter"));
            System.out.println("xml-bean="
                    + context.containsBean("legacyPrefixer"));
            System.out.println("scanned-bean="
                    + context.containsBean("aggregationService"));
            System.out.println("programmatic-bean="
                    + context.containsBean("auditSink"));

            AggregationService service =
                    context.getBean(AggregationService.class);
            System.out.println("result=" + service.execute("ok"));

            AuditSink audit = context.getBean(AuditSink.class);
            System.out.println("audit-count=" + audit.count());
            System.out.println("same-audit="
                    + (audit == context.getBean("auditSink", AuditSink.class)));
        }
    }
}
```

Không có lệnh tạo `ClassPathXmlApplicationContext` riêng. Bốn nguồn cùng đi vào `context` có một `refresh()` và một lần `close()`. `try-with-resources` đảm bảo context được đóng sau khi sử dụng; với tài nguyên thật, Spring có thể gọi destruction callbacks phù hợp.

### 9.9. Chạy và kết quả

Từ thư mục `multi-source-context-demo`:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows). Lệnh `javac App.java` đơn lẻ không đủ vì ứng dụng có nhiều source files và cần Spring dependencies trên classpath; Gradle giải quyết cả hai.

**Các dòng do chương trình in ra:**

```text
java-bean=true
xml-bean=true
scanned-bean=true
programmatic-bean=true
result=AUDIT#1:xml(java[ok])
audit-count=1
same-audit=true
```

Log Gradle hoặc logging runtime, nếu có, là thông tin môi trường khác với bảy dòng `System.out.println` kể trên.

### 9.10. Vì sao output chính xác?

**`java-bean=true`:** cấu hình `FormattingConfiguration` được `@Import` nạp, factory method `@Bean` đăng ký tên `formatter`.

**`xml-bean=true`:** `@ImportResource` nạp `legacy-beans.xml` và đăng ký `legacyPrefixer`.

**`scanned-bean=true`:** `@ComponentScan` quét package chứa `AggregationService` và scanner chọn class `@Component`, tên bean thông thường là `aggregationService`.

**`programmatic-bean=true`:** `context.registerBean("auditSink", ...)` đăng ký bean definition với supplier trước refresh.

**`result=AUDIT#1:xml(java[ok])`:** `formatter.format("ok")` trả `java[ok]`; `LegacyPrefixer.wrap(...)` trả `xml(java[ok])`; `audit.record(...)` đánh số lần ghi đầu tiên bằng 1 rồi trả chuỗi như trên.

**`audit-count=1`:** chỉ có một lần `record`. `AuditSink` được đăng ký như singleton mặc định và service sử dụng đúng instance được container tạo.

**`same-audit=true`:** lookup theo type và lookup theo name trong cùng context trả **cùng bean singleton** `auditSink`.

Bài thực hành chứng minh tính độc lập giữa **cách khai báo bean** và **cách consumer nhận dependency**: constructor `AggregationService` không biết bean của mình đến từ XML, Java config hay API registration.

## 10. Lý giải trình tự container refresh khi dùng nhiều nguồn

Trong demo:

```text
1. new AnnotationConfigApplicationContext()
   |
2. register(AppConfiguration.class)
   |
3. registerBean("auditSink", AuditSink.class, AuditSink::new)
   |
4. refresh()
   |
   +--> ConfigurationClassPostProcessor:
   |      @Import FormattingConfiguration
   |      @ImportResource legacy-beans.xml
   |      @ComponentScan demo.scanned
   |
   +--> các bean definitions trở nên khả dụng trong registry
   +--> BeanFactoryPostProcessor / BeanPostProcessor tương ứng
   +--> tạo non-lazy singletons & resolve dependencies
   |
5. getBean(AggregationService.class)
   |
6. close()
```

Đây là **mô hình logic**, không phải cam kết về thứ tự nội bộ từng bước được phát biểu chính xác cho mọi extension point. Một số configuration processing đăng ký definitions trong pha BFPP, và container có thể có các processor đặc biệt hoạt động sớm. Phần thiết yếu là **các nguồn cần được nạp/đăng ký đúng lúc, trước khi consumer bean được tạo**, để BeanFactory nhìn thấy dependency candidates.

### 10.1. Đăng ký bean definitions không đồng nghĩa lập tức tạo instance

Gọi `registerBean` thường đăng ký metadata và supplier; gọi `register` nạp class metadata. Với context chưa `refresh()`, nhiều bean application chưa được tạo. Khi refresh chạy, Spring chuẩn bị processors, resolve dependencies và thường pre-instantiate non-lazy singleton beans.

Điều đó giải thích vì sao không cần sắp xếp các lệnh đăng ký theo thứ tự “formatter trước, prefixer sau, service cuối” trong mã bootstrap. Dependencies khai báo đúng sẽ được giải quyết bằng bean factory; tránh dùng side effect của thứ tự registration làm hợp đồng nghiệp vụ.

### 10.2. Vì sao tên bean/kiểu trả về quan trọng?

Bean definition có thông tin tên/type/factory method. Khi `AggregationService` yêu cầu `Formatter`, Spring cần tìm được candidate type phù hợp. Với `@Bean`, return type nên được khai báo đủ cụ thể cho những injection point cần dùng.

Nếu `@Bean Object formatter() { return new Formatter("java"); }`, trước khi instance tồn tại Spring có thể chỉ dự đoán bean type là `Object` và việc injection theo `Formatter` có thể không được resolve ở giai đoạn cần thiết. Nên trả kiểu `Formatter` hoặc interface thích hợp mà consumer thực sự inject.

## 11. Phân biệt nhiều bean definitions với nhiều nguồn properties

Có hai kiểu “nguồn cấu hình” thường bị gọi cùng tên:

**A. Nguồn bean definitions:** XML `<bean>`, Java `@Bean`, component scanning, programmatic registration. Chúng quyết định **bean nào tồn tại** và cách tạo bean.

**B. Nguồn giá trị properties:** `application.properties`, environment variables, system properties, `@PropertySource`, `Environment`, secret stores, Spring Boot config data, v.v. Chúng chủ yếu cung cấp **giá trị cấu hình** cho bean.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:client.properties")
class ClientConfiguration {
    @Bean
    ClientOptions clientOptions(Environment environment) {
        return new ClientOptions(
                environment.getRequiredProperty("client.endpoint")
        );
    }
}
```

`ClientOptions` là class demo giả định, cần import `@PropertySource`, `@Bean`, `@Configuration`, `Environment`, và file `client.properties`. `@PropertySource` thêm resource vào `Environment`/property sources; nó **không tự tạo một bean `ClientOptions`**. Factory method `@Bean` mới là nguồn bean definition, còn property là dữ liệu để tạo object.

### 11.1. Một resource XML có thể cấu hình bean lẫn properties

XML có thể dùng `<context:property-placeholder location="..."/>` và `<bean>`. Đó là hai cơ chế phối hợp: property resolver giúp điền giá trị, còn bean element định nghĩa object. Trong migration, cần kiểm tra **thứ tự đăng ký post-processors** và những file properties thực sự được tìm trên classpath.

### 11.2. Spring Boot application.properties không đồng nghĩa @ImportResource

Spring Boot thường tự quản lý các nguồn cấu hình giá trị (`application.properties`/YAML, environment, command-line arguments, profiles...) theo quy tắc riêng. Điều đó không có nghĩa Boot tự đọc mọi file `legacy-beans.xml` và đăng ký toàn bộ bean trong đó. Muốn import legacy XML, vẫn cần `@ImportResource` hoặc cơ chế nạp XML tương ứng.

**Ghi nhớ:** “đã đọc file properties” khác “đã đăng ký một bean từ file XML”.

## 12. Dùng @ImportResource hay XmlBeanDefinitionReader?

### 12.1. @ImportResource: đơn giản khi Java config làm gốc

Với hầu hết ứng dụng Java-centric, chọn:

```java
@Configuration
@ImportResource({
    "classpath:legacy-beans.xml",
    "classpath:integration-beans.xml"
})
class AppConfiguration {}
```

Đây là cách declarative: khi configuration được xử lý, Spring nạp các XML resources đã liệt kê. Thích hợp khi tập XML cố định theo module/deployment.

### 12.2. XmlBeanDefinitionReader: linh hoạt khi bootstrap động

Khi muốn điều khiển trực tiếp nguồn XML, Spring cũng cung cấp `XmlBeanDefinitionReader`, ví dụ ý tưởng dùng cùng `GenericApplicationContext`:

```java
GenericApplicationContext context = new GenericApplicationContext();

XmlBeanDefinitionReader xml = new XmlBeanDefinitionReader(context);
xml.loadBeanDefinitions("classpath:legacy-beans.xml");

context.registerBean("auditSink", AuditSink.class, AuditSink::new);
context.refresh();
```

Snippet cần import `GenericApplicationContext`, `XmlBeanDefinitionReader`, `AuditSink`. Trong trường hợp này bạn tự điều phối XML/programmatic registration, nhưng nếu muốn dùng `@Configuration` và `@ComponentScan` trên cùng `GenericApplicationContext` còn cần **đăng ký annotation configuration infrastructure** thích hợp (ví dụ dùng `AnnotationConfigApplicationContext` hoặc `AnnotatedBeanDefinitionReader` và `ClassPathBeanDefinitionScanner`). Do đó không nên suy luận rằng cứ tạo một `GenericApplicationContext` là nó tự xử lý mọi annotation `@Configuration`.

### 12.3. Tiêu chí lựa chọn

| Nhu cầu | Cách ưu tiên |
| --- | --- |
| Ứng dụng chủ yếu dùng Java configuration, chỉ một ít XML | `@ImportResource` |
| Muốn quản lý rõ class cấu hình/module | `@Import` |
| Dự án legacy chủ yếu XML | `ClassPathXmlApplicationContext` hoặc XML-centric + annotation processors |
| Bootstrap chọn XML resources theo runtime | `XmlBeanDefinitionReader` với context/registry phù hợp |
| Chỉ cần test fixture thêm một object | `registerBean` hoặc test configuration `@Bean` |
| Nhiều service có stereotype trong package rõ ràng | `@ComponentScan` |

Đừng chọn cách phức tạp chỉ vì có nhiều nguồn; một composition root với `@Import`/`@ImportResource` và vài `@Bean` thường đủ.

## 13. Tránh tạo context khác chỉ để lấy dependency

Một anti-pattern:

```java
public ReportService reportService() {
    ClassPathXmlApplicationContext legacy =
            new ClassPathXmlApplicationContext("legacy-beans.xml");
    LegacyPrefixer prefixer = legacy.getBean(LegacyPrefixer.class);
    return new ReportService(prefixer);
}
```

Đoạn này là ví dụ phản diện, với `ReportService` giả định và cần imports. Nó dựng một XML context khác trong lúc tạo service:

- Bean singleton của XML context **không** dùng chung cache với context Java.
- Phải quản lý/đóng cả hai context đúng cách.
- Dependency resolution xuyên context không mặc nhiên có.
- Dễ rò rỉ tài nguyên, trùng pool, trùng lifecycle và khó test.
- Có thể vô tình tạo nhiều instance cùng type mà người viết tưởng chỉ có một.

Giải pháp đúng khi cần **một context**:

```java
@Configuration
@ImportResource("classpath:legacy-beans.xml")
class RootConfiguration {
    @Bean
    ReportService reportService(LegacyPrefixer prefixer) {
        return new ReportService(prefixer);
    }
}
```

`ReportService` vẫn là kiểu giả định. Bean XML được nạp cùng context và cung cấp qua parameter injection. Không cần tự tạo XML context.

## 14. Một context vẫn có thể xuất hiện nhiều bean cùng type

Việc ghép nhiều nguồn làm tăng khả năng định nghĩa trùng. Hai vấn đề phải phân biệt:

### 14.1. Trùng tên bean

Ví dụ XML đã có:

```xml
<bean id="formatter" class="demo.javaformat.Formatter">
    <constructor-arg value="xml"/>
</bean>
```

trong khi Java configuration cũng khai báo `@Bean Formatter formatter()`. Hai registrations dùng **cùng tên** `formatter`. Hành vi phụ thuộc quy tắc overriding và thứ tự đăng ký:

- Có môi trường từ chối override bean definition và ném lỗi.
- Có môi trường cho phép ghi đè definition theo các quy tắc cụ thể.
- Spring Boot thường chặt hơn với duplicate definitions theo mặc định so với một số trường hợp Spring Framework thuần.

**Không nên dùng “ai đăng ký sau sẽ thắng” như hợp đồng nghiệp vụ.** Chọn một owner cho mỗi bean name hoặc thiết kế tên khác nhau có chủ ý.

### 14.2. Nhiều bean cùng kiểu

XML khai báo `legacyFormatter` và Java `@Bean` khai báo `formatter`, cả hai return/bean class đều thuộc kiểu `Formatter`. Bây giờ injection point nhận một `Formatter` có thể gặp nhiều ứng viên.

Có các cách hợp lệ:

- `@Qualifier("formatter")` ở injection point nếu muốn bean Java.
- `@Primary` trên bean mặc định khi thực sự có một lựa chọn ưu tiên.
- Tên/qualifier chuyên biệt theo chức năng (ví dụ `publicJsonMapper` và `internalJsonMapper`).
- Inject `List<Formatter>` hoặc `Map<String, Formatter>` khi nghiệp vụ chủ động cần nhiều implementations.
- Chỉ nạp đúng module/bean set cần thiết vào context.

Không đổi mọi bean thành `@Primary` hoặc mở bean overriding tùy tiện để lờ đi xung đột.

## 15. Component scan có thể vô tình nạp lại Java configuration

`@Configuration` cũng mang semantics stereotype của `@Component`. Do đó nếu `@ComponentScan` quét package chứa những configurations khác, Spring có thể tự phát hiện và xử lý chúng. Khi đã `@Import` một configuration và cùng class cũng bị scan, Spring thường có cơ chế quản lý metadata cùng configuration class; nhưng việc quét rộng **vẫn có thể nạp những cấu hình/module không dự định bật**.

Trong demo, `@ComponentScan(basePackageClasses=AggregationService.class)` chỉ scan `demo.scanned` thay vì toàn bộ `demo`; nhờ vậy tránh cuốn `demo.config` vào vùng quét không cần thiết.

Một cấu trúc tốt:

```text
demo.config   -> Java configurations / composition root
demo.scanned  -> application components của module này
demo.legacy   -> XML-managed classes
demo.audit    -> programmatically registered classes
```

Package separation ở đây làm rõ intent, nhưng **không tự tạo isolation**: khi bean definitions được nạp, chúng vẫn thuộc cùng context.

## 16. Annotation processing có còn hoạt động với bean XML/programmatic?

**Có, nếu context đăng ký hạ tầng annotation tương ứng.** Ví dụ `AnnotationConfigApplicationContext` đã chuẩn bị các annotation configuration processors cốt lõi, để Spring có thể xử lý `@Autowired`, các callback/hạ tầng thích hợp trên managed beans dù definition đến từ XML hay `registerBean`.

Một class XML có field `@Autowired` vẫn có thể được inject khi instance do Spring tạo và `AutowiredAnnotationBeanPostProcessor` phù hợp đang hoạt động. **Component scanning không phải điều kiện duy nhất của annotation processing**.

### Cần phân biệt với XML-centric context

Nếu dùng `ClassPathXmlApplicationContext` với XML thuần và muốn xử lý `@Autowired`, thường dùng `<context:annotation-config/>`, hoặc `<context:component-scan/>` vốn bao hàm annotation processors thông dụng. Chỉ đọc `<bean>` definitions từ XML **không đồng nghĩa** mọi annotation đã tự được bật trong tất cả BeanFactory variants.

### Và không phải annotation nào cũng tự hoạt động

`@Transactional` cần transaction management; `@Scheduled` cần scheduling infrastructure; `@RequestMapping` cần web mapping. Chỉ vì bean được kết hợp vào context không có nghĩa mỗi annotation của mọi stack tự có behavior.

## 17. Tên bean, scope, lifecycle và dependency xuyên nguồn

### 17.1. Cùng một singleton mặc định trong cùng context

Nếu bean `AuditSink` được đăng ký programmatically một lần với singleton mặc định, XML-managed bean và Java-managed bean khác khi inject `AuditSink` cùng sẽ nhận bean được container resolve. Trong demo, `same-audit=true` minh họa identity trong cùng context.

Nếu tạo **hai** ApplicationContext khác nhau, mỗi context có thể có singleton của riêng nó; không trông chờ identity qua biên giới contexts.

### 17.2. Scope luôn quan trọng

Bean từ XML có thể khai báo `scope="prototype"`; bean `@Bean` có thể dùng `@Scope("prototype")`; programmatic registration có thể dùng BeanDefinitionCustomizer để cấu hình scope. Khi một singleton consumer inject prototype trực tiếp, Spring thường cấp instance prototype tại thời điểm tạo singleton; không tự lấy prototype mới trên mỗi method call. Cần `ObjectProvider<T>`/`Provider<T>` khi muốn deferred lookup có chủ đích.

### 17.3. Vòng đời và resources

Nếu XML bean/Java bean trả HTTP client hoặc connection pool, phải xác định:

- Ai sở hữu client/pool?
- Init callback có được container gọi không?
- Shutdown cần `destroy-method`, `@Bean(destroyMethod=...)`, `@PreDestroy` hay API đóng khác?
- Có vô tình tạo hai pools vì cùng nguồn được nạp hai lần hoặc trực tiếp gọi factory method không?

Tập trung resources vào bean definitions được quản lý và đóng **context sở hữu chúng** đúng thời điểm. Với resource externally owned, không để Spring đóng nhầm tài nguyên không thuộc quyền sở hữu.

### 17.4. Phụ thuộc vòng xuyên cấu hình

Một XML bean có constructor ref tới bean Java, trong khi bean Java lại constructor-inject XML bean có thể tạo vòng phụ thuộc. Việc đến từ hai nguồn khác nhau **không thay đổi quy tắc xử lý vòng** của Spring: constructor cycles thường không giải quyết được và cần thiết kế lại dependency direction.

## 18. Thêm PropertySource mà không tạo bean trùng

Một hệ thống đa nguồn thường có nhiều properties files. Ví dụ:

**`src/main/resources/service.properties`**

```properties
service.prefix=production
```

**Java config:**

```java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:service.properties")
class ServiceSettingsConfiguration {
    @Bean
    String servicePrefix(Environment environment) {
        return environment.getRequiredProperty("service.prefix");
    }
}
```

Đây là snippet Java cấu trúc, cần imports tương ứng. `@PropertySource` thêm một nguồn **giá trị** vào `Environment`; `@Bean String servicePrefix(...)` mới tạo bean tên `servicePrefix`.

Trong ứng dụng thật, không nhất thiết tạo mọi chuỗi cấu hình thành bean `String` (có thể gây mơ hồ injection); thường gói properties thành settings object rõ kiểu hoặc dùng configuration binding nếu framework hỗ trợ.

### 18.1. Thứ tự ưu tiên properties không đồng nghĩa thứ tự override bean

Giả sử system environment và property file đều có key `service.prefix`. `Environment` có thứ tự ưu tiên giữa các `PropertySource`; điều đó **khác** việc có hai bean definitions cùng tên `servicePrefix`. Một bên chọn **giá trị cấu hình**, một bên quyết định **bean registration**, phải debug tách biệt.

### 18.2. @Value placeholders cần resolver tương ứng

Trong `AnnotationConfigApplicationContext`, cơ chế environment/property resolution được tích hợp, nhưng với một số container low-level hoặc cú pháp placeholder tùy chỉnh, phải có processor/resolver thích hợp. Không trông chờ `@PropertySource` tạo bean đúng chỉ vì file properties đã đọc thành công.

## 19. Những lỗi tích hợp thường gặp

### Lỗi 1 — Tạo hai ApplicationContext độc lập rồi tưởng chúng chung singleton cache

Hai context không tự chia sẻ bean definitions. Nếu muốn một context, dùng `@ImportResource`/`@Import` hoặc reader trên cùng registry. Nếu muốn parent-child hierarchy, cấu hình parent rõ ràng và hiểu dependency visibility.

### Lỗi 2 — Quên @ImportResource, XML resource không được nạp

Java context không tự phát hiện XML file chỉ vì nó có trong `src/main/resources`. Nạp nó qua `@ImportResource` hoặc `XmlBeanDefinitionReader` trong đúng bootstrap path.

### Lỗi 3 — Sai đường dẫn classpath

`@ImportResource("classpath:legacy-beans.xml")` yêu cầu resource ở classpath root của runtime. Nếu file đặt `src/main/resources/config/legacy-beans.xml` thì đường dẫn cần là `classpath:config/legacy-beans.xml`. Build/test runtime classpath phải có resource.

### Lỗi 4 — Component scan quá rộng

`@ComponentScan("demo")` có thể tìm cả modules/configurations không dự kiến. Sử dụng package marker nằm trong package mục tiêu, hoặc `@Import` explicit thay vì scan toàn bộ project.

### Lỗi 5 — Đăng ký programmatic bean sau khi refresh rồi chờ toàn bộ lifecycle khởi động lại

Nhiều bước refresh và post-processing đã chạy. Với bootstrap, đăng ký trước refresh; nếu cần dynamic registration thực sự, phải hiểu API/lifecycle và test riêng trường hợp đó.

### Lỗi 6 — Trùng bean name từ XML và @Bean

Một XML bean id `formatter` đụng method `@Bean formatter()`. Kết quả tùy chính sách overriding và thời điểm xử lý, có thể lỗi hoặc thay bean definition. Dùng owner duy nhất hoặc đổi tên có chủ đích.

### Lỗi 7 — Nhiều ứng viên cùng type gây injection ambiguity

Hai beans `Formatter` từ XML và Java nhưng constructor nhận một `Formatter`. Cần `@Qualifier`, `@Primary`, tập hợp hoặc tổ chức lại module. Đừng suy luận nguồn Java luôn được ưu tiên hơn XML.

### Lỗi 8 — Bean do XML khai báo có @Autowired nhưng processor chưa được bật

Ở XML-centric context không có `<context:annotation-config/>` hoặc infrastructure tương đương, field/method annotation có thể không hoạt động. Kiểm tra loại ApplicationContext và processors đã đăng ký, không thay thế bằng mở rộng component scan vô tội vạ.

### Lỗi 9 — Nạp XML cần namespace nhưng thiếu dependency

Một XML file có namespace cho transaction, AOP, JMS hoặc Spring Security có thể cần module/schema/namespace handler tương ứng trên classpath. XML trong demo chỉ dùng Spring beans namespace nên không cần những modules đó.

### Lỗi 10 — Trộn cấu hình XML và Java nhưng gọi new trên configuration

Tự `new ConfigurationClass()` hoặc gọi `@Bean` method từ object không managed có thể tạo object ngoài container. Đưa dependency qua constructor/factory method parameters; để BeanFactory quản lý source-derived instance.

### Lỗi 11 — Giấu type phía sau @Bean Object

Spring không luôn đoán được concrete type trước khi factory method chạy. Điều này có thể gây thiếu candidate hoặc khiến processor hạ tầng không được phát hiện sớm. Return type nên đủ rõ, đặc biệt `BeanFactoryPostProcessor`/`BeanPostProcessor`.

### Lỗi 12 — Biên dịch được Java nhưng XML constructor không khớp

Ví dụ XML `<constructor-arg value="abc"/>` trong khi class vendor không có constructor hợp lệ. Lỗi chỉ xuất hiện lúc đọc/tạo bean. Khi tích hợp XML, kiểm tra constructor signature, tên package và type conversion.

### Lỗi 13 — Nhầm @Import với @ImportResource

`@Import` nhận class/type config/selector/registrar. `@ImportResource` nhận địa chỉ tài nguyên XML (hoặc nguồn được reader phù hợp hỗ trợ). Đừng đặt `"classpath:legacy-beans.xml"` vào `@Import` hoặc truyền class configuration vào `@ImportResource`.

### Lỗi 14 — Suy ra thứ tự khởi tạo từ thứ tự import

Đừng mặc định XML đọc trước sẽ tạo singleton trước Java bean và ngược lại. Dependency graph, scope, lazy-init, BFPP/BPP và early bean creation ảnh hưởng thời điểm. Nếu thật sự cần ràng buộc thứ tự initialization, có thể dùng `@DependsOn` hoặc bean-definition depends-on nhưng tốt nhất là biểu diễn dependency thật.

### Lỗi 15 — Bean đã ở context nhưng stack chuyên biệt chưa hoạt động

Có controller bean không đồng nghĩa HTTP server/mapping đã khởi chạy; có repository bean không đồng nghĩa transaction được bật. Việc kết hợp bean definitions chỉ giải quyết **registry/DI/lifecycle cơ bản**, không tự dựng mọi infrastructure framework khác.

## 20. Kiểm tra một context đã ghép đủ nguồn

### 20.1. Kiểm tra theo bean name

```java
context.containsBean("formatter");
context.containsBean("legacyPrefixer");
context.containsBean("aggregationService");
context.containsBean("auditSink");
```

Đặt trong `main` sau `refresh()` như demo. Những lookup này giúp kiểm chứng **bean name hiện diện**. Không chứng minh dependency đã được inject đúng nếu không chạy hành vi thực tế.

### 20.2. Kiểm tra theo bean type

```java
Formatter formatter = context.getBean(Formatter.class);
LegacyPrefixer legacy = context.getBean(LegacyPrefixer.class);
AuditSink audit = context.getBean(AuditSink.class);
AggregationService service = context.getBean(AggregationService.class);
```

Đoạn này dùng các class và context của demo. Nếu một type có nhiều candidates, `getBean(Type.class)` có thể lỗi; khi đó dùng name + type hoặc qualifier tại injection point.

### 20.3. Xem bean definition và nguồn khai báo

```java
var factory = context.getBeanFactory();

var javaDefinition = factory.getBeanDefinition("formatter");
var xmlDefinition = factory.getBeanDefinition("legacyPrefixer");
var scanDefinition = factory.getBeanDefinition("aggregationService");
var apiDefinition = factory.getBeanDefinition("auditSink");

System.out.println(javaDefinition.getFactoryMethodName());
System.out.println(xmlDefinition.getBeanClassName());
System.out.println(scanDefinition.getBeanClassName());
System.out.println(apiDefinition.getBeanClassName());
```

Đây là một snippet để quan sát, không đặt stdout cứng cho mọi môi trường. Bean definition có thể mô tả factory method hoặc class name; một số field có thể `null` tùy cơ chế đăng ký. Trong ví dụ này, `formatter` đến từ `@Bean` (factory method), XML bean chỉ định class, scanner biết class, programmatic registration biết class/supplier. `BeanDefinition.getResourceDescription()` có thể cung cấp nguồn tài nguyên để hỗ trợ điều tra.

### 20.4. Điều tra missing bean đúng hướng

Khi `UnsatisfiedDependencyException` xảy ra, kiểm tra:

1. Class/bean definition có thực sự được nạp từ **nguồn dự kiến**?
2. Resource XML tìm thấy chưa, format/schema có hợp lệ không?
3. Component scan có bao phủ đúng package? Có bị exclude không?
4. Programmatic registration có diễn ra trước refresh không?
5. Bean candidates có bị `@Profile`/`@Conditional` làm loại không?
6. Có nhiều candidate cùng kiểu hoặc trùng bean name không?
7. Bean construction có lỗi thực tế vì dependency khác, không phải vì scanner thiếu không?

Cách tiếp cận này nhanh hơn việc thêm tràn lan `@ComponentScan` hoặc `@Autowired` vào các class bất kỳ.

## 21. Kiến trúc kết hợp nhiều nguồn trong dự án thực tế

### 21.1. Giai đoạn migrate XML → Java

Một lộ trình an toàn:

1. Chọn **một context làm composition root** và xác định ai sở hữu bootstrap.
2. Giữ XML legacy trong một hoặc vài `@ImportResource` references.
3. Đưa các bean mới vào Java configuration, dùng `@Import` để chia nhóm.
4. Dùng component scan có phạm vi giới hạn cho code mới mang stereotype.
5. Tránh tạo context riêng cho một tài nguyên chỉ nhằm lấy bean.
6. Dùng integration tests để xác nhận tên bean, type, qualifier và behavior xuyên nguồn.
7. Migrate từng nhóm bean XML sang `@Bean` khi có lợi, nhưng không cần di chuyển tất cả cùng lúc.
8. Sau mỗi nhóm migrate, xóa definition cũ để tránh duplicate registrations.
9. Kiểm tra lifecycle và shutdown behavior của các tài nguyên dài hạn.

Đây là cách “strangler migration” ở cấp cấu hình: chuyển dần ownership bean mà vẫn duy trì khả năng chạy ứng dụng.

### 21.2. Chia theo module và vẫn chung context

```text
bootstrap/
    AppConfiguration.java
    App.java

pricing/
    PricingConfiguration.java
    DiscountService.java

legacy/
    legacy-beans.xml

integration/
    HttpClientConfiguration.java

scanned/
    EventHandler.java
```

Composition root quyết định **cấu hình nào cần nạp**, từng module sở hữu bean definitions của mình. Dù cấu hình đến từ source files khác nhau, chúng có thể góp vào **một** context khi deployment yêu cầu.

### 21.3. Có nên dùng nhiều ApplicationContext?

**Có**, khi bạn thật sự cần parent-child hierarchy, child web context, isolation hoặc lifecycle khác nhau. Nhưng đây là quyết định kiến trúc riêng, không phải điều kiện để sử dụng XML và Java đồng thời.

Trong hierarchy điển hình, **child** có thể tìm bean ở **parent**, còn parent không nhìn thấy bean chỉ tồn tại trong child. Bean name trùng ở child có thể che bean cùng tên trong parent theo lookup rules. Scope/lifecycle cũng không được tự gộp thành một bean factory thống nhất. Do đó, nếu yêu cầu là “nhiều nguồn trong **một** context”, hãy ưu tiên ghép vào một registry thay vì mở thêm containers.

## 22. Bài tập thực hành

### Bài 1 — Chuyển bean XML sang Java @Bean

Trong demo, thử chuyển `LegacyPrefixer` từ XML sang:

```java
@Bean
LegacyPrefixer legacyPrefixer() {
    return new LegacyPrefixer("java-config");
}
```

Đưa method vào Java configuration và **xóa `@ImportResource` hoặc definition XML cũ** trước khi chạy để tránh hai nguồn cùng khai báo bean name `legacyPrefixer`. Dự đoán output sau thay đổi: phần ở giữa chuỗi sẽ là `java-config(java[ok])` thay vì `xml(java[ok])`. Không cần thay constructor `AggregationService`.

### Bài 2 — Thêm XML bean cùng kiểu Formatter

Thêm một bean XML `Formatter` tên `legacyFormatter`. Sau đó, dự đoán kết quả autowire constructor `AggregationService(Formatter ...)`.

Đáp án: có thể xuất hiện **nhiều candidates** `Formatter`; để giữ ý định rõ ràng, dùng `@Qualifier("formatter")` hoặc phân biệt chúng bằng marker/primary theo use case. Không mặc định Java bean có ưu tiên chỉ vì nó không đến từ XML.

### Bài 3 — Đổi programmatic bean thành @Bean

Chuyển `AuditSink` sang Java config:

```java
@Bean
AuditSink auditSink() {
    return new AuditSink();
}
```

Sau khi bỏ dòng `context.registerBean("auditSink", ...)` ở bootstrap, chương trình vẫn có thể in những giá trị giống trước nếu các dependencies khác giữ nguyên. Điều đó chứng minh consumer không cần biết registration source.

### Bài 4 — Bỏ component scan, dùng registerBean(Class)

Thay cơ chế scan cho `AggregationService` bằng:

```java
context.registerBean(AggregationService.class);
```

Đây là lời gọi để đặt **trước `refresh()`**, sau khi bỏ `@ComponentScan` tương ứng. Với class có một public constructor và đủ dependency beans, Spring có thể tạo service bằng constructor injection. Tên bean được generator tạo có thể khác nếu dùng API/metadata khác; test nên tìm theo type, hoặc truyền tên explicit `"aggregationService"`.

### Bài 5 — Phân biệt property source và bean source

Tạo `settings.properties` có `app.prefix=config-value`, rồi dùng `@PropertySource` để cung cấp giá trị cho một factory method `@Bean`. Kiểm tra rằng:

- Property được đọc qua `Environment`.
- Property không tự tạo bean của class bạn mong muốn.
- Bean mới chỉ xuất hiện khi đã có registration source (`@Bean`, XML, scan hoặc API).

## 23. Câu hỏi ôn tập và đáp án

**Câu 1.** Một `AnnotationConfigApplicationContext` có thể chứa đồng thời bean từ XML, Java `@Bean` và component scan không?

**Đáp:** Có. Có thể dùng `@ImportResource` để import XML, `@Import`/`register` cho Java configuration và `@ComponentScan` để tìm components, tất cả trong một context.

**Câu 2.** `@ImportResource` có tạo thêm một `ClassPathXmlApplicationContext` độc lập không?

**Đáp:** Không. Nó nhập bean definitions từ XML vào context Java đang được cấu hình.

**Câu 3.** `@ComponentScan` có bắt buộc để một bean XML được inject vào scanned component không?

**Đáp:** Scan cần thiết nếu bạn chọn cách tìm consumer component qua scanner; bean XML vẫn được đăng ký độc lập. Khi consumer đã ở context, injection theo type hoạt động trên tập bean candidates chung.

**Câu 4.** Vì sao phải hoàn tất `registerBean` trước `refresh()` trong bootstrap?

**Đáp:** Để processor và các bean cần khởi tạo trong refresh nhìn thấy registration ngay từ đầu, tránh thêm bean sau khi startup lifecycle đã chạy.

**Câu 5.** Có hai bean cùng type `Formatter` nhưng tên khác nhau. Điều gì có thể xảy ra khi inject một `Formatter`?

**Đáp:** Nếu không có cách xác định ứng viên duy nhất (qualifier/primary/tên phù hợp), Spring có thể báo `NoUniqueBeanDefinitionException`.

**Câu 6.** File `application.properties` tự khai báo một Spring bean `Formatter` không?

**Đáp:** Không. Nó thường cung cấp giá trị cấu hình, không phải bean definition; cần factory/configuration/registration tương ứng để có object bean.

**Câu 7.** Tạo hai ApplicationContext cùng nạp một XML file có dùng chung singleton của file đó không?

**Đáp:** Không tự động. Mỗi context có bean factory và singleton registry riêng.

**Câu 8.** Trong demo, bốn bean đến từ nguồn nào?

**Đáp:** `Formatter` từ Java `@Bean`, `LegacyPrefixer` từ XML, `AggregationService` từ component scan, `AuditSink` từ programmatic registration.

**Câu 9.** Spring phân biệt constructor injection dựa trên nguồn bean definition hay dựa trên candidates phù hợp?

**Đáp:** Dựa trên dependency metadata, type, qualifier, scope và các quy tắc resolution; consumer thường không cần biết bean nguồn đến từ XML hay Java.

**Câu 10.** Khi chuyển bean XML sang Java, điều quan trọng trước tiên là gì?

**Đáp:** Bảo đảm có **một registration owner rõ ràng**, tránh cùng tên/type bị đăng ký trùng không chủ ý, kiểm tra behavior, scope và lifecycle sau migration.

## 24. Checklist triển khai

Trước khi kết hợp nhiều nguồn cấu hình, xác nhận:

1. **Chỉ có một ApplicationContext nếu mục tiêu là dùng chung registry.**
2. Mọi nguồn được nạp/đăng ký đúng cách: `@Import`, `@ImportResource`, `@ComponentScan`, `registerBean`/`register`.
3. XML resources tồn tại đúng classpath và namespaces được thư viện hỗ trợ.
4. Component scanning giới hạn package/filter và không kéo vào modules ngoài dự kiến.
5. Java `@Bean` methods trả kiểu rõ ràng; dependency thể hiện bằng factory method parameters khi phù hợp.
6. Programmatic registrations hoàn tất trước `refresh()` trong bootstrap.
7. Bean names không va chạm ngoài ý muốn; injection types có lựa chọn ứng viên duy nhất hoặc qualifier rõ ràng.
8. Scope, lazy-init, callbacks và resource ownership được kiểm tra ở container chung.
9. Annotation processors/stack-specific infrastructure được bật khi cần, không suy luận từ việc có bean.
10. Test cùng context: đủ bean theo name/type, hành vi xuyên nguồn chạy thật, resources được đóng đúng.
11. Nếu dùng parent-child contexts, lập sơ đồ visibility/lifecycle riêng; không coi đó là một context.
12. Nguồn properties và nguồn bean definitions được phân biệt trong tài liệu và log chẩn đoán.

## 25. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import`, bean dependency xuyên configuration và `@ImportResource`.
- [Spring Framework 6.2 — Instantiating the Spring Container with AnnotationConfigApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/instantiating-container.html): `register`, `scan`, `refresh`.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): stereotype, base packages, filter.
- [Spring Framework 6.2 — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html): annotation processors khi trộn với XML.
- [Spring Framework 6.2 — Bean Definitions and XML Imports](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): XML `<bean>`, `<import/>` và bean metadata.
- [Spring Framework 6.2 — GenericApplicationContext Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/GenericApplicationContext.html): các overload `registerBean`.
- [Spring Framework 6.2 — ImportResource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ImportResource.html): import bean definitions từ resources.
- [Spring Framework 6.2 — PropertySource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/PropertySource.html): phân biệt property metadata và bean registration.

**Ghi nhớ:** Java configuration, XML, component scan và programmatic API đều có thể đóng góp bean definitions vào **một Spring ApplicationContext**. Container giải quyết dependency giữa chúng bằng cùng cơ chế IoC, scope và lifecycle. **Một context có nhiều nguồn không giống nhiều contexts**, còn nguồn giá trị `@PropertySource` không phải nguồn bean definitions. Nắm rõ registration ownership và kiểm tra trùng tên/type là chìa khóa để kết hợp an toàn.
