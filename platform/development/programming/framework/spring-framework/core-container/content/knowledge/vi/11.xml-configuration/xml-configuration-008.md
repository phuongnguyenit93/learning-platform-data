# Bật annotation-config và component-scan trong Spring XML

## 1. Vấn đề cần giải quyết

Spring IoC Container quản lý các bean thông qua **bean definitions**. Khi chuyển dần từ XML sang annotations, hai cấu hình thường được nhắc tới là:

```xml
<context:annotation-config/>
<context:component-scan base-package="com.example"/>
```

Hai phần tử này rất dễ bị nhầm là tương đương, nhưng chúng xử lý **hai nhu cầu khác nhau**:

- **`<context:annotation-config/>`**: thêm các hạ tầng xử lý annotation để Spring nhận biết `@Autowired`, `@Value`, một số Jakarta lifecycle annotations và cấu hình Java **trên những bean mà context đã đăng ký**. Nó **không quét classpath** để tìm mọi class có `@Component`.
- **`<context:component-scan base-package="..."/>`**: tìm những class được đánh dấu `@Component` hoặc stereotypes phù hợp trong package, **đăng ký chúng làm beans**, đồng thời **mặc định kích hoạt chức năng annotation-config**. Vì thế thường không cần viết cả hai phần tử cùng lúc.

Ví dụ: class `OrderService` được XML khai báo qua `<bean class="...OrderService"/>` và có `@Autowired OrderRepository repository`. Nếu container thiếu `AutowiredAnnotationBeanPostProcessor`, field injection đó có thể không diễn ra. Nhưng khi đã bật annotation-config và có bean `OrderRepository` phù hợp, Spring sẽ inject dependency. Ngược lại, một class `@Service` chỉ có mặt trên classpath mà chưa được scan/import/register thì không tự trở thành Spring bean.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Khai báo Spring XML Beans/Context namespaces và schemas hợp lệ.
2. Phân biệt **component discovery**, **bean registration**, **annotation injection** và **bean lifecycle**.
3. Biết `annotation-config` đăng ký những processor nào và **không** làm việc gì.
4. Hiểu `component-scan` chọn những stereotype candidates nào, quét package/subpackages ra sao và đặt bean name như thế nào.
5. Giải thích vì sao `component-scan` mặc định bao hàm `annotation-config`.
6. Phân biệt `annotation-config="false"` với `use-default-filters="false"`.
7. Sử dụng `include-filter`/`exclude-filter` và biết giới hạn của scan.
8. Chạy ví dụ Java 17+, Spring Framework 6.2.9 đối chiếu **bốn XML contexts**.
9. Xử lý xung đột bean definitions, sai package, missing dependency, duplicate components và vấn đề parent-child context.
10. Lựa chọn cấu hình phù hợp khi chuyển dần từ XML-only sang annotation-based configuration.

**Phạm vi:** Spring Framework **Core Container**. Không giả định Spring Boot, HTTP server, transaction proxy, persistence provider hoặc scheduler tự hoạt động chỉ nhờ hai phần tử này.

## 2. Mô hình: bốn giai đoạn khác nhau

```text
A. CÓ JAVA CLASS TRÊN CLASSPATH
       |
       +-- XML <bean> trực tiếp
       |
       +-- <context:component-scan> nhận @Component candidates
       |
       +-- @Configuration / @Import / registration APIs (khi đã bật)
       |
       v
B. BEAN DEFINITIONS TRONG REGISTRY
       |
       | Processor được đăng ký bởi annotation-config
       | hoặc bởi component-scan mặc định
       v
C. BEANFACTORY TẠO INSTANCE VÀ INJECT
       |
       | @Autowired, @Value, các lifecycle callbacks hợp lệ
       v
D. MANAGED BEAN TRONG CONTEXT
```

Một annotation như `@Component` là metadata trên **class**, không tự đăng ký class trong mọi ApplicationContext. Một annotation như `@Autowired` là metadata trên **injection point**, cần BeanPostProcessor phù hợp và ứng viên dependency đã được đăng ký.

### Phân biệt hai câu hỏi

**Bean có được đăng ký không?**

```java
boolean exists = context.containsBean("orderService");
```

Nếu false, kiểm tra XML `<bean>`, `component-scan`, `@Import` hoặc registration APIs.

**Bean đã được inject không?**

```java
OrderService service = context.getBean(OrderService.class);
boolean ready = service.hasRepository();
```

Đoạn này là snippet minh họa; `OrderService` phải có method `hasRepository()` trong dự án. Nếu bean tồn tại mà dependency null, kiểm tra annotation processors và cách bean được tạo, không chỉ package scanning.

## 3. Cú pháp namespace XML chuẩn

`<context:annotation-config/>` và `<context:component-scan/>` thuộc **Spring Context namespace**, không phải Spring Beans namespace mặc định.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean id="orderRepository"
          class="com.example.OrderRepository"/>
    <bean id="orderService"
          class="com.example.OrderService"/>

</beans>
```

Trong ví dụ cấu trúc này, các class phải có trên runtime classpath và có constructors/wiring hợp lệ. Các namespace URI và schemaLocation giúp XML parser hiểu `<beans>`, `<bean>` và các phần tử `context:`.

### Lỗi XML thường thấy

Nếu báo lỗi prefix `context` chưa được khai báo: thiếu `xmlns:context`. Nếu báo phần tử không được phép trong `<beans>`: kiểm tra schema pair, vị trí/nesting, dependencies và Spring versions. Đừng thay namespaced element thành tên trần `<component-scan>` mà không hiểu XML namespace.

Spring cung cấp cơ chế tìm schema resources phù hợp với các modules trên classpath; các URL schema **không phải** application API endpoints hoặc nơi định nghĩa service nghiệp vụ.

## 4. annotation-config đăng ký hạ tầng gì?

Theo tài liệu Spring 6.2, `<context:annotation-config/>` kích hoạt các post-processors phục vụ annotation-based configuration trong **ApplicationContext hiện tại**. Những thành phần chính được mô tả gồm:

- `ConfigurationClassPostProcessor`: xử lý các class cấu hình đã được biết, bao gồm metadata `@Configuration`, `@Bean`, `@Import`.
- `AutowiredAnnotationBeanPostProcessor`: xử lý `@Autowired`, `@Value` và các annotation tương ứng được hỗ trợ trên injection points.
- `CommonAnnotationBeanPostProcessor`: liên quan `@Resource`, `@PostConstruct`, `@PreDestroy` khi Jakarta annotations APIs phù hợp hiện diện.
- `PersistenceAnnotationBeanPostProcessor` khi có các dependency Jakarta Persistence cần thiết.
- `EventListenerMethodProcessor` cùng các processor hỗ trợ event-listener metadata.

**Điểm tinh tế:** hạ tầng chính xác còn phụ thuộc classpath/Spring version; không nên kết luận rằng mọi processor của mọi framework stack chắc chắn được tạo dù thiếu thư viện hoặc infrastructure chuyên biệt.

### 4.1. Bean XML có @Autowired

```java
package com.example;

import org.springframework.beans.factory.annotation.Autowired;

public class PaymentService {
    @Autowired
    private PaymentRepository repository;

    public boolean isReady() {
        return repository != null;
    }
}
```

Đây là snippet minh họa, cần một `PaymentRepository` bean hợp lệ. Nếu XML khai báo:

```xml
<context:annotation-config/>
<bean id="paymentRepository"
      class="com.example.PaymentRepository"/>
<bean id="paymentService"
      class="com.example.PaymentService"/>
```

thì processor có thể inject `PaymentRepository`. **Không cần `@Component` trên PaymentService** vì XML đã đăng ký class làm bean.

### 4.2. @Value và property placeholders

```java
@Value("${client.timeout:30}")
private int timeout;
```

Đây là snippet minh họa trong một Spring-managed bean. Annotation processor giúp xử lý injection, còn `Environment`/property source infrastructure cung cấp giá trị và conversion. Muốn lấy file property ngoài hệ thống mặc định, có thể dùng `<context:property-placeholder location="classpath:app.properties"/>` hoặc hạ tầng property source thích hợp.

**Không nhầm:** đọc một properties file không tự tạo bean definition; bật `@Value` không tự dựng những external service clients được mô tả bằng properties.

### 4.3. Lifecycle annotations

`@PostConstruct` và `@PreDestroy` thuộc Jakarta annotation APIs trong Spring Framework 6+. Java 17 không tự tích hợp tất cả Jakarta APIs; khi viết chương trình có annotations đó cần khai báo dependency như `jakarta.annotation-api` tương thích.

Nếu class được tạo bằng `new` ngoài container, `@PostConstruct` **không tự chạy** chỉ vì class có annotation. Nó cần Spring quản lý lifecycle với processor phù hợp.

### 4.4. Java @Configuration vẫn cần được đăng ký

`<context:annotation-config/>` có thể hỗ trợ xử lý metadata của class cấu hình Java **đã được đăng ký trong context**, chẳng hạn:

```xml
<context:annotation-config/>
<bean class="com.example.JavaFeatureConfiguration"/>
```

Giả sử `JavaFeatureConfiguration` có `@Configuration`/`@Bean` hợp lệ. Đây là cách dùng kết hợp XML và Java configuration. Nhưng `annotation-config` **không tự tìm mọi `@Configuration` trên classpath**: nguồn class ở đây là `<bean>` XML.

## 5. Những điều annotation-config không làm

Nó **không phải công tắc bật toàn bộ Spring Framework**. Chỉ ghi:

```xml
<context:annotation-config/>
```

không có nghĩa:

- Tất cả class `@Service` trong mọi package được tự động scan.
- `@Repository` luôn được exception translation nếu thiếu hạ tầng thích hợp.
- `@Transactional` chắc chắn có transaction AOP; còn cần transaction manager, proxy infrastructure/`<tx:annotation-driven/>` phù hợp.
- `@Scheduled` tự chạy mà không có scheduling support.
- `@Async` tự chạy không cần async processing/executor.
- `@Controller` tự nhận HTTP requests trong một Core Container chưa có Spring MVC/DispatcherServlet infrastructure.
- Java objects tự `new` bên ngoài container bỗng được inject.
- Processors trong child context tự áp lên beans thuộc parent context.

**Chốt ý:** annotation-config bật **phần xử lý annotations**, không bật **tìm class**.

## 6. component-scan tìm và đăng ký class nào?

```xml
<context:component-scan base-package="com.example.orders"/>
```

Yêu cầu scanner tìm candidate classes trong package `com.example.orders` và các subpackages. Mặc định các stereotype candidates thường gồm:

- `@Component`.
- `@Service`.
- `@Repository`.
- `@Controller`.
- `@Configuration` (meta-annotated bằng `@Component`).
- Custom annotations được meta-annotated bằng `@Component`; trong môi trường có thêm JSR-330/Jakarta annotations, những filters được Spring hỗ trợ còn có thể tác động.

Ví dụ:

```text
com.example
├── orders
│   ├── OrderService.java          <-- thuộc package scan
│   └── persistence
│       └── OrderRepository.java   <-- thuộc subpackage scan
└── billing
    └── BillingService.java        <-- KHÔNG thuộc base-package orders
```

Để scanner chọn `OrderService` hoặc `OrderRepository`, class phải phù hợp với stereotype/filter và là candidate component hợp lệ. Package name trong Java source, runtime classpath, scan root và filters đều phải khớp.

### Tên bean của scanned classes

Một class `@Service public class OrderService` được scan thường có bean name `orderService` theo naming convention; có thể chỉ định `@Service("primaryOrderService")`.

Nếu hai classes ở packages khác nhau cùng tên ngắn `OrderService`, bean names tự sinh có thể va chạm. Đừng dựa vào Java package khác nhau để bảo đảm bean name duy nhất khi scan nhiều packages vào **một** context.

### Component scan không nhất thiết tạo instance ngay

Scanner tạo bean definitions; Spring tạo instances sau theo scope/lifecycle. Mặc định non-lazy singleton thường được khởi tạo trong refresh. `@Lazy`, `@Scope` và dependencies có thể thay đổi timing; không suy ra scanner tự gọi constructor ngay khi bắt gặp annotation.

## 7. Vì sao component-scan mặc định bao hàm annotation-config?

Theo Spring Reference, `<context:component-scan>` **implicitly enables** hầu hết chức năng của `<context:annotation-config/>`. Điều này làm hai ví dụ khác nhau:

**Chỉ processing:**

```xml
<context:annotation-config/>
<bean id="manualService" class="demo.ManualService"/>
```

Spring có thể xử lý `@Autowired` trong `manualService` nếu bean dependency hiện diện, **nhưng không tìm** bất kỳ `@Component` class nào ngoài XML.

**Discovery + processing:**

```xml
<context:component-scan base-package="demo.scanned"/>
<bean id="manualService" class="demo.ManualService"/>
```

Scanner tìm beans trong `demo.scanned`; processors được kích hoạt mặc định nên có thể inject `@Autowired` cả vào những scanned components **và** `manualService` đã được XML đăng ký.

| Cấu hình XML | Đăng ký stereotype candidates | Xử lý @Autowired trên XML bean |
| --- | --- | --- |
| Chỉ `<bean>` | Không | Không, nếu không có processor từ nguồn khác |
| `annotation-config` + `<bean>` | Không | Có, khi có dependency hợp lệ |
| `component-scan` + `<bean>` | Có | Có, mặc định |
| `component-scan annotation-config="false"` + `<bean>` | Có | Không do scanner tự thêm processor; có thể vẫn hoạt động nếu processor đã được đăng ký ở nguồn khác |
| Cả scan mặc định và annotation-config | Có | Có; dòng annotation-config thường dư thừa |

### Component scan có chỉ inject scanned beans không?

Không. Processors đã đăng ký hoạt động với những Spring-managed beans tương ứng trong cùng context, bất kể bean được đăng ký từ XML hay scan. **Cơ chế registration khác cơ chế injection**.

## 8. annotation-config="false" nghĩa là gì?

```xml
<context:component-scan
    base-package="demo.scanned"
    annotation-config="false"/>
```

Phần tử này **vẫn scan package** và đăng ký candidate components. Flag chỉ nói rằng **phần tử scanner đó không tự đăng ký những annotation processors mà nó mặc định sẽ thêm**.

Vì vậy, một class được scan có `@Autowired` field có thể vẫn được tạo mà field chưa được inject. Tuy nhiên, nếu có `<context:annotation-config/>` từ XML khác hoặc có `AutowiredAnnotationBeanPostProcessor` được đăng ký bằng một đường khác, injection vẫn có thể chạy.

**Không nên phát biểu tuyệt đối rằng annotation-config="false" sẽ làm mọi annotation ngừng hoạt động**. Điều đúng là nó tắt *auto-registration từ scanner đó*.

### Cảnh báo về tên attribute giống nhau

- `annotation-config="false"`: vẫn chọn stereotype candidates, nhưng không tự thêm annotation processing infrastructure.
- `use-default-filters="false"`: tắt **các candidate filters mặc định** để scanner không tự chọn mọi `@Component`/`@Service`; chỉ những classes match include filters phù hợp mới được đăng ký.

Một flag nói về **post-processors**, flag còn lại nói về **cách tìm bean definitions**.

## 9. Ví dụ hoàn chỉnh Java 17+ so sánh bốn XML configurations

Demo dùng **Spring Framework 6.2.9**, **Java 17+**, **Gradle** và `ClassPathXmlApplicationContext`. Để phân biệt từng tình huống không có nhiễu từ hạ tầng đăng ký chung, ta mở bốn contexts **độc lập và tuần tự**:

1. `plain.xml` — chỉ XML `<bean>`; không scan, không annotation-config.
2. `annotations.xml` — bật annotation-config nhưng không scan.
3. `scanned.xml` — bật component-scan mặc định.
4. `scan-no-annotations.xml` — bật scan nhưng dùng `annotation-config="false"`.

Trong production, nếu các modules cần chia sẻ beans, thường nên nạp các nguồn vào **một context**. Bốn contexts ở đây chỉ là các test fixtures để quan sát rõ từng cơ chế.

### 9.1. Cấu trúc file

```text
xml-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── App.java
        │       ├── Formatter.java
        │       ├── ManualConsumer.java
        │       └── scanned/
        │           └── ScannedConsumer.java
        └── resources/
            ├── plain.xml
            ├── annotations.xml
            ├── scanned.xml
            └── scan-no-annotations.xml
```

Java types là public top-level classes; từng file ở đúng package.

### 9.2. Gradle setup

**`settings.gradle`**

```groovy
rootProject.name = 'xml-context-demo'
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
    implementation 'org.springframework:spring-context:6.2.9'
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

Dependency này mang `spring-beans`/`spring-core` và hạ tầng annotations cần cho `@Autowired`/`@Component`. Không cần Spring Boot hay Jakarta annotation APIs bổ sung vì chương trình không dùng `@PostConstruct`.

### 9.3. Formatter.java — bean chỉ được đăng ký qua XML

**`src/main/java/demo/Formatter.java`**

```java
package demo;

import java.util.Objects;

public final class Formatter {
    private final String prefix;

    public Formatter(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String format(String value) {
        return prefix + ":" + value;
    }
}
```

Class không có `@Component`. XML `<bean id="formatter">` bên dưới là nguồn bean definition duy nhất.

### 9.4. ManualConsumer.java — XML bean có field @Autowired

**`src/main/java/demo/ManualConsumer.java`**

```java
package demo;

import org.springframework.beans.factory.annotation.Autowired;

public final class ManualConsumer {
    @Autowired
    private Formatter formatter;

    public boolean wired() {
        return formatter != null;
    }

    public String describe() {
        return formatter.format("manual");
    }
}
```

`ManualConsumer` không có `@Component`, nhưng cả bốn XML files đều đăng ký `<bean id="manualConsumer" class="demo.ManualConsumer"/>`. Nếu context không có processor hỗ trợ field `@Autowired`, field này giữ `null`.

**Chỉ gọi `describe()` trong những contexts đã xác nhận `wired()==true`** để không tự tạo `NullPointerException`.

### 9.5. ScannedConsumer.java — chỉ được tìm bởi component scan

**`src/main/java/demo/scanned/ScannedConsumer.java`**

```java
package demo.scanned;

import demo.Formatter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component("scannedConsumer")
public final class ScannedConsumer {
    @Autowired
    private Formatter formatter;

    public boolean wired() {
        return formatter != null;
    }

    public String describe() {
        return formatter.format("scan");
    }
}
```

Class có stereotype và bean name explicit. Trong `annotations.xml` không có scanner hoặc XML `<bean>` cho class này nên nó không phải bean. Trong `scanned.xml` và `scan-no-annotations.xml`, scanner tìm thấy class.

### 9.6. plain.xml — không annotation-config/scan

**`src/main/resources/plain.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="formatter" class="demo.Formatter">
        <constructor-arg value="xml"/>
    </bean>
    <bean id="manualConsumer" class="demo.ManualConsumer"/>
</beans>
```

Ở đây không có annotation processors từ XML này, cũng không có scan package. `ManualConsumer` được tạo nhưng không field-autowired, `ScannedConsumer` vắng mặt.

### 9.7. annotations.xml — có annotation-config, không scan

**`src/main/resources/annotations.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:annotation-config/>

    <bean id="formatter" class="demo.Formatter">
        <constructor-arg value="xml"/>
    </bean>
    <bean id="manualConsumer" class="demo.ManualConsumer"/>
</beans>
```

`AutowiredAnnotationBeanPostProcessor` xử lý field của `ManualConsumer` đã khai báo XML. `ScannedConsumer` vẫn chưa được register.

### 9.8. scanned.xml — scan ngầm bật annotation processing

**`src/main/resources/scanned.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="demo.scanned"/>

    <bean id="formatter" class="demo.Formatter">
        <constructor-arg value="xml"/>
    </bean>
    <bean id="manualConsumer" class="demo.ManualConsumer"/>
</beans>
```

Vừa có XML beans vừa có scanned bean. Processors được scanner tự đăng ký, nên cả hai consumer fields `@Autowired` đều được inject từ cùng bean `Formatter` singleton.

### 9.9. scan-no-annotations.xml — scan nhưng không tự thêm processors

**`src/main/resources/scan-no-annotations.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan
        base-package="demo.scanned"
        annotation-config="false"/>

    <bean id="formatter" class="demo.Formatter">
        <constructor-arg value="xml"/>
    </bean>
    <bean id="manualConsumer" class="demo.ManualConsumer"/>
</beans>
```

`ScannedConsumer` vẫn được scanner đăng ký thành bean. Nhưng vì fixture này không có một nguồn khác đăng ký `AutowiredAnnotationBeanPostProcessor`, cả hai fields `@Autowired` không được xử lý.

### 9.10. App.java

**`src/main/java/demo/App.java`**

```java
package demo;

import demo.scanned.ScannedConsumer;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class App {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext plain =
                     new ClassPathXmlApplicationContext("plain.xml")) {

            ManualConsumer consumer = plain.getBean(ManualConsumer.class);
            System.out.println("plain.manual-wired=" + consumer.wired());
            System.out.println("plain.scanned-count="
                    + plain.getBeanNamesForType(ScannedConsumer.class).length);
        }

        try (ClassPathXmlApplicationContext annotations =
                     new ClassPathXmlApplicationContext("annotations.xml")) {

            ManualConsumer consumer =
                    annotations.getBean(ManualConsumer.class);
            System.out.println("annotation.manual-wired=" + consumer.wired());
            System.out.println("annotation.manual-message="
                    + consumer.describe());
            System.out.println("annotation.scanned-count="
                    + annotations.getBeanNamesForType(
                            ScannedConsumer.class).length);
        }

        try (ClassPathXmlApplicationContext scanned =
                     new ClassPathXmlApplicationContext("scanned.xml")) {

            ManualConsumer manual = scanned.getBean(ManualConsumer.class);
            ScannedConsumer component =
                    scanned.getBean(ScannedConsumer.class);

            System.out.println("scan.manual-wired=" + manual.wired());
            System.out.println("scan.scanned-count="
                    + scanned.getBeanNamesForType(
                            ScannedConsumer.class).length);
            System.out.println("scan.scanned-wired=" + component.wired());
            System.out.println("scan.scanned-message="
                    + component.describe());
        }

        try (ClassPathXmlApplicationContext scanOff =
                     new ClassPathXmlApplicationContext(
                             "scan-no-annotations.xml")) {

            ManualConsumer manual = scanOff.getBean(ManualConsumer.class);
            ScannedConsumer component =
                    scanOff.getBean(ScannedConsumer.class);

            System.out.println("scan-off.manual-wired=" + manual.wired());
            System.out.println("scan-off.scanned-count="
                    + scanOff.getBeanNamesForType(
                            ScannedConsumer.class).length);
            System.out.println("scan-off.scanned-wired="
                    + component.wired());
        }
    }
}
```

### 9.11. Lệnh chạy

Trong thư mục `xml-context-demo`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper:

```bash
./gradlew run --quiet
```

Trên Windows:

```bat
gradlew.bat run --quiet
```

Dùng `javac App.java` độc lập không đủ vì cần compile các files khác và cung cấp Spring JAR dependencies. Gradle thiết lập classpath, compile và copy resources.

### 9.12. Stdout dự kiến chính xác từ chương trình

```text
plain.manual-wired=false
plain.scanned-count=0
annotation.manual-wired=true
annotation.manual-message=xml:manual
annotation.scanned-count=0
scan.manual-wired=true
scan.scanned-count=1
scan.scanned-wired=true
scan.scanned-message=xml:scan
scan-off.manual-wired=false
scan-off.scanned-count=1
scan-off.scanned-wired=false
```

Đây là **12 dòng được chủ động in từ Java**. Build/runtime có thể xuất hiện thêm log từ framework; chúng không phải một phần của các println này.

### 9.13. Giải thích kết quả

**plain**: XML đăng ký `Formatter`/`ManualConsumer` nhưng không có processor/scanner, nên `manual-wired=false` và `scanned-count=0`.

**annotations**: `annotation-config` bật processor; `ManualConsumer` được inject và trả `xml:manual`. Nhưng không có scan, nên `ScannedConsumer` không thành bean.

**scanned**: `component-scan` vừa đăng ký `ScannedConsumer` vừa mặc định bật processor; các consumer có `@Autowired` đều được inject `Formatter` từ XML.

**scan-no-annotations**: scanner vẫn đăng ký `ScannedConsumer` (count 1), nhưng không tự thêm processors; cả `ManualConsumer` và `ScannedConsumer` đều có field null trong fixture này. Main chỉ kiểm tra `wired()`, không gọi `describe()` trong context này.

**Đừng nhầm bốn contexts của demo là bốn contexts trong một ứng dụng.** Chúng là phép thử độc lập để tách ảnh hưởng từng XML element.

## 10. include-filter, exclude-filter và use-default-filters

Scanner mặc định dùng những stereotype filters. Khi cần kiểm soát candidates, có thể thêm filters.

### 10.1. Exclude một nhóm classes

```xml
<context:component-scan base-package="com.example.orders">
    <context:exclude-filter type="regex"
        expression="com\.example\.orders\.testsupport\..*"/>
</context:component-scan>
```

Đây là snippet cấu trúc: điều kiện chỉ có tác dụng nếu package và class names match pattern thật. Ký tự `\` trong XML attribute là một phần của regex, không phải Java string escape.

### 10.2. Chỉ tìm custom annotation

```xml
<context:component-scan base-package="com.example.jobs"
                        use-default-filters="false">
    <context:include-filter type="annotation"
        expression="com.example.jobs.WorkerTask"/>
</context:component-scan>
```

Với đoạn này, scanner không mặc định chọn mọi `@Component`, mà tìm classes có annotation `WorkerTask` theo điều kiện include. `WorkerTask` phải là một annotation type có thật. `use-default-filters="false"` không tự tắt annotation processors của scanner: đó là flag khác.

### 10.3. Các filter types phổ biến

| `type` | `expression` | Ý nghĩa |
| --- | --- | --- |
| `annotation` | Fully qualified annotation class | Chọn/loại annotations |
| `assignable` | Fully qualified base class/interface | Chọn class có quan hệ type phù hợp |
| `regex` | Regular expression cho class name | Quy tắc theo tên class |
| `aspectj` | AspectJ type pattern | Lọc theo pattern type |
| `custom` | TypeFilter implementation class | Custom predicate |

Một policy có thể kết hợp include/exclude filters. Nhưng filter không thay cho module packaging hay dependency governance; scanner vẫn dựa trên tập classes có trên classpath.

### 10.4. Ví dụ phân biệt hai flags

**Chỉ tắt processors:**

```xml
<context:component-scan
    base-package="com.example"
    annotation-config="false"/>
```

Class `@Component` vẫn có thể được đăng ký.

**Chỉ tắt mặc định chọn stereotypes:**

```xml
<context:component-scan
    base-package="com.example"
    use-default-filters="false">
    <context:include-filter type="annotation"
        expression="com.example.SpecialComponent"/>
</context:component-scan>
```

Annotation processors vẫn được scanner tự đăng ký theo mặc định, nhưng chỉ candidates match filter mới được tìm theo policy đã nêu.

## 11. Kết hợp XML bean với scanned bean trong cùng context

Trong thực tế, có thể dùng XML cho thư viện vendor/client cần cấu hình constructor, còn business services dùng annotation:

```xml
<context:component-scan base-package="com.example.checkout"/>

<bean id="paymentGateway"
      class="com.example.vendor.ExternalGateway">
    <constructor-arg value="https://gateway.example.test"/>
</bean>
```

Một `@Service` trong package scan có thể constructor-inject `PaymentGateway` nếu type/qualifier phù hợp. Ngược lại, XML `<bean>` có thể `<constructor-arg ref="scannedService"/>` để tham chiếu bean được quét và đăng ký.

**Quy tắc:** injection diễn ra dựa trên tập bean definitions của context, không cần cả hai bên phải có cùng nguồn khai báo. Nếu scanner không quét vendor class mà XML đã đăng ký vendor bean, đó vẫn là candidate hợp lệ.

### Tránh đăng ký cùng class hai lần

Giả sử `EmailService` có `@Service` nằm trong package đang scan, nhưng XML lại khai báo:

```xml
<bean id="emailService" class="com.example.EmailService"/>
```

Có nguy cơ trùng name/definition hoặc hai candidates, tùy cơ chế registration/overriding. Nếu XML cần override configuration chủ động, thiết kế theo chính sách rõ; đừng để duplicate chỉ vì quên xóa definition cũ lúc migration.

### Multiple beans cùng type

Nếu hai beans cùng implement `NotificationSender`, injection theo type có thể không tìm được ứng viên duy nhất. Dùng `@Qualifier`, `@Primary` hoặc chỉ đăng ký implementation cần thiết.

## 12. Các giới hạn của annotation processing

### 12.1. Object phải được Spring quản lý

Một `new ManualConsumer()` do Java code tự tạo **không tự được inject** chỉ vì XML có `annotation-config`. BeanPostProcessors được Spring gọi theo lifecycle quản lý của BeanFactory; không chạy như Java annotation interpreter cho mọi object.

### 12.2. Thư viện Jakarta cần tồn tại

Trong Java 17/Spring 6+, nếu dùng `jakarta.annotation.PostConstruct` hoặc `jakarta.inject.Inject`, khai báo đúng Jakarta dependencies. Có `@Autowired` không đồng nghĩa mọi package Jakarta đều có sẵn.

### 12.3. Transaction, cache, async, scheduling cần infrastructure riêng

- `@Transactional`: cần transaction manager/transaction advice infrastructure.
- `@Cacheable`: cần cache infrastructure.
- `@Async`: cần async-enabled annotation processors/executor phù hợp.
- `@Scheduled`: cần scheduling support.
- `@RequestMapping`: cần Spring MVC/web request mapping infrastructure.

Cả annotation-config lẫn component-scan trong Core Container **không bảo đảm** các chức năng trên tự vận hành.

### 12.4. @Repository exception translation không tự động trong mọi project

`@Repository` đánh dấu vai trò persistence/DAO. Exception translation có thể cần `PersistenceExceptionTranslationPostProcessor` và các adapters/infrastructure thích hợp. Không nên suy luận cứ scan `@Repository` là mọi exception từ JDBC/JPA đều được đổi sang một dạng cụ thể.

## 13. Parent-child ApplicationContexts

Một ứng dụng web truyền thống có thể có root context và child servlet context. `<context:annotation-config/>` chỉ đăng ký processors **vào context chứa nó**.

```text
Root ApplicationContext
  ├── dataSource
  ├── orderRepository
  └── orderService

Child WebApplicationContext
  ├── orderController
  └── viewResolver
```

Nếu chỉ bật annotation-config ở child, nó không tự trở thành BeanPostProcessor của root context. Root beans cần processor ở root khi dùng annotation injection. Bean visibility giữa parent/child cũng không giống một registry duy nhất: child thường lookup bean từ parent, parent không nhìn thấy bean chỉ có ở child.

Đây là một lỗi khó chẩn đoán khi thấy XML child có `annotation-config` nhưng service root vẫn không được xử lý injection như mong đợi.

## 14. Những lỗi phổ biến

### Lỗi 1: Bật annotation-config nhưng quên component-scan

`@Component` không tự được tìm từ classpath. Nếu type chưa được XML khai báo hoặc import/register, ứng dụng có thể báo thiếu bean.

### Lỗi 2: Quét sai base-package

`com.example.order` khác `com.example.orders`. Phải khớp Java package declaration và runtime classpath.

### Lỗi 3: Scan quá rộng

Quét root package lớn có thể kéo những test components, optional configuration, adapters hoặc services chưa muốn bật vào context.

### Lỗi 4: Khai báo cả annotation-config và component-scan mặc định rồi nghĩ sẽ scan nhiều hơn

Hai phần tử không cộng thêm phạm vi scan. `component-scan` mặc định đã bật processors; annotation-config tường minh thường dư.

### Lỗi 5: Hiểu sai annotation-config="false"

Scanner vẫn tìm/register classes. Flag chỉ ngăn scanner tự thêm annotation processors. Nếu processor đến từ nguồn khác, injection vẫn có thể hoạt động.

### Lỗi 6: Nhầm với use-default-filters="false"

Flag này thay cách chọn candidates, không tương đương disable annotation processors.

### Lỗi 7: Bean được XML đăng ký nhưng @Autowired vẫn null

Kiểm tra object có do Spring tạo không, annotation processor có mặt không và có dependency bean phù hợp trong context không.

### Lỗi 8: Hai beans cùng type gây NoUniqueBeanDefinitionException

Đăng ký nhiều implementations có thể hợp lệ, nhưng injection point cần qualifier/primary hoặc chọn một bean duy nhất.

### Lỗi 9: Hai classes cùng bean name

Name collision có thể xảy ra dù hai classes ở packages khác nhau. Dùng scoped scan boundaries và explicit names/qualifiers khi cần.

### Lỗi 10: Dùng @PostConstruct thiếu Jakarta APIs

Java 17 không tự có mọi Jakarta annotation API. Thêm dependency đúng version và processor tương ứng.

### Lỗi 11: Cho rằng scan tạo bean instance ngay

Scan chủ yếu đăng ký definitions; BeanFactory tạo instances theo scope, lazy/depends-on/dependencies.

### Lỗi 12: Bật @Transactional chỉ bằng annotation-config

Transaction support là stack riêng. Cần transaction manager/advice configuration phù hợp.

### Lỗi 13: Có @Controller bean là tự có HTTP endpoint

Controller bean không đồng nghĩa đã có Spring MVC DispatcherServlet và mapping infrastructure.

### Lỗi 14: Mơ hồ context ownership

Bean trong root context không tự được xử lý bởi processors chỉ có ở child context.

### Lỗi 15: Test bằng new object rồi kết luận processor không hoạt động

Object không thuộc Spring lifecycle sẽ không tự được inject. Dùng integration test thật với ApplicationContext.

### Lỗi 16: Bỏ annotation-config trên component-scan nhưng quên filters

`use-default-filters="false"` cần include filters phù hợp; nếu không scanner có thể không tìm bean mong muốn.

### Lỗi 17: Component nằm trong JAR nhưng scanner không nhìn thấy

Kiểm tra dependency được đóng gói trên runtime classpath, directory/module entries và classpath scanning resources.

### Lỗi 18: Dùng @Value nhưng không có property source đúng

Annotation injection hỗ trợ `@Value`, nhưng giá trị vẫn cần nguồn property/placeholder resolution hợp lệ.

## 15. Quy trình debug theo từng bước

Khi `@Autowired` không hoạt động, hãy hỏi theo thứ tự:

1. **Bean tồn tại chưa?** Kiểm tra `getBeanNamesForType` và `containsBean`.
2. **Bean được đăng ký bằng cách nào?** XML `<bean>`, scan, `@Bean` hay programmatic registration?
3. **Object có do Spring tạo không?** Không dùng object tự `new` để kết luận DI.
4. **Processor có tồn tại trong đúng context không?** `annotation-config` hoặc `component-scan` mặc định, trừ khi bị tắt.
5. **Dependency candidate có tồn tại không?** Nếu không, scan/package/registration source nào thiếu?
6. **Có nhiều candidates cùng type không?** Xem `@Qualifier` hoặc `@Primary`.
7. **Có filter hoặc profile/condition làm bean vắng mặt không?**
8. **Có root/child contexts khác nhau không?**
9. **Có sai namespace/JAR/annotation package không?**
10. **Có hiểu nhầm một stack chuyên biệt là Core annotation-config không?**

### Đo trực tiếp processors (khi cần)

Trong một context đang hoạt động:

```java
String[] names = context.getBeanNamesForType(
        org.springframework.beans.factory.annotation
            .AutowiredAnnotationBeanPostProcessor.class);
System.out.println(names.length);
```

Đây là đoạn chẩn đoán minh họa; số lượng chính xác phụ thuộc infrastructure của context/version. Nó không thay thế test thực tế rằng service đã được inject đúng dependency.

### Unit test vs integration test

Unit test tạo trực tiếp một service với constructor-injected dependency để kiểm tra business logic. Integration test nên dựng đúng XML context để kiểm tra scanning, bean registration, annotation processing và lifecycle. Đừng dùng `new` rồi mong field `@Autowired` sẽ được Spring tự điền.

## 16. Lộ trình chuyển XML legacy sang annotations

Một chiến lược có kiểm soát:

1. Ban đầu XML đăng ký hầu hết service/repository/adapters qua `<bean>`.
2. Bật `<context:annotation-config/>` để sử dụng annotation injection trên **beans đã biết** trong khi vẫn giữ XML registrations.
3. Chọn một feature package rõ ràng và bật `<context:component-scan>` cho các components mới.
4. Vì scan đã bật processors theo mặc định, có thể bỏ annotation-config tường minh nếu không có lý do đặc biệt cần giữ.
5. Khi class chuyển hoàn toàn sang `@Component` và được scan, xóa XML `<bean>` trùng tương ứng để tránh xung đột.
6. Test bean names/types, qualifiers, scopes và lifecycle trước/sau migration.
7. Chỉ mở rộng base-package khi có kiểm thử xác nhận không cuốn unwanted components/configurations.
8. Giữ XML cho một số vendor beans cần constructor/factory logic nếu điều đó hữu ích; Spring không bắt buộc chuyển toàn bộ sang annotations.

**Lưu ý:** chuyển nguồn bean definitions không nên làm thay đổi tài nguyên do ai sở hữu. Đặc biệt, đừng tạo hai HTTP clients, DataSources hoặc pools chỉ vì cả XML và scan đang cùng đăng ký một implementation.

## 17. Checklist thiết kế XML cấu hình

- XML có đủ `beans` và `context` namespaces/schema locations.
- Biết rõ những classes do XML đăng ký và classes do scanner tìm.
- `annotation-config` được bật khi cần annotation processing nhưng chưa có scanner/infrastructure khác.
- Nếu đã dùng `component-scan` mặc định thì không thêm processors trùng không cần thiết.
- `base-package` bao phủ đúng feature và subpackages.
- `annotation-config="false"` không bị nhầm là tắt scanning.
- `use-default-filters="false"` đi kèm include filters khi yêu cầu.
- XML `<bean>` và scanned components không tạo duplicates ngoài ý định.
- Injection candidates có type/name/qualifier rõ ràng.
- Parent/child context boundaries được kiểm tra nếu có.
- Các annotations chuyên biệt có hạ tầng tương ứng, không tự suy ra từ Core Container.
- Code có integration tests khởi tạo ApplicationContext và test injection thực tế.
- Không dùng tên bean từ scan như hợp đồng bất biến nếu không có naming policy.
- Startup logs được đọc kèm with bean-definition/injection evidence, không chỉ nhìn thấy “scan succeeded”.

## 18. Câu hỏi ôn tập

**Câu 1.** `annotation-config` có tự scan package để tìm `@Service` không?

**Đáp:** Không. Nó đăng ký annotation processors phục vụ beans đã được context đăng ký.

**Câu 2.** `component-scan` có mặc định bật annotation-config functionality không?

**Đáp:** Có. Đó là behavior được Spring Reference mô tả, nên thường không cần viết cả hai.

**Câu 3.** XML bean có field `@Autowired`, cần bản thân class có `@Component` không?

**Đáp:** Không, nếu bean đã đăng ký từ XML và context có processor thích hợp.

**Câu 4.** Class mang `@Component` nhưng chưa scan/import/register, có tự xuất hiện trong context không?

**Đáp:** Không.

**Câu 5.** `annotation-config="false"` trên scanner làm scanner ngừng tìm classes không?

**Đáp:** Không. Nó ngăn scanner tự thêm annotation processors; candidate detection vẫn có thể diễn ra.

**Câu 6.** `use-default-filters="false"` làm gì?

**Đáp:** Tắt default stereotype candidate filters; cần include filters để chủ động chọn classes.

**Câu 7.** Trong demo, tại sao `annotation.scanned-count=0`?

**Đáp:** `annotations.xml` không có component scan hoặc registration source cho `ScannedConsumer`.

**Câu 8.** Trong demo, tại sao `scan-off.scanned-count=1` nhưng `scan-off.scanned-wired=false`?

**Đáp:** Scanner đăng ký bean nhưng không tự thêm processor; context đó không có nguồn processor khác.

**Câu 9.** Scanner chỉ inject `@Autowired` cho scanned beans đúng không?

**Đáp:** Sai. Processor trong context xử lý injection của các Spring-managed beans được tạo trong context, kể cả beans đăng ký từ XML.

**Câu 10.** Có hai implementations của một interface trong context, `@Autowired` phải xử lý thế nào?

**Đáp:** Cần candidate selection phù hợp như `@Qualifier`, `@Primary` hoặc kiến trúc chỉ đăng ký một implementation khi yêu cầu.

**Câu 11.** Cứ bật annotation-config là `@Transactional` có transaction behavior?

**Đáp:** Không. Cần infrastructure transaction management phù hợp.

**Câu 12.** Bật annotation-config ở child context có tự xử lý fields trên bean root context không?

**Đáp:** Không. Processor có phạm vi context nơi nó được đăng ký.

**Câu 13.** Vì sao test bằng `new Service()` thường không phản ánh field injection?

**Đáp:** Vì không có Spring BeanFactory lifecycle và BeanPostProcessor tác động lên object tự tạo.

**Câu 14.** Khi XML dùng vendor bean còn scanned service cần nó, dependency có inject được không?

**Đáp:** Có, nếu cả hai definitions nằm trong context liên quan và candidate type/qualifier phù hợp.

## 19. Tài liệu chính thức

- [Spring Framework 6.2 — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html): `<context:annotation-config/>` và processors.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): component scan, implicit annotation-config, filters và flags.
- [Spring Framework 6.2 — @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html): constructor/field/method injection.
- [Spring Framework 6.2 — XML-based Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): XML bean definitions và container.
- [Spring Framework 6.2 — BeanFactory Post-processors](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-extension.html): registry/instance post-processing.
- [Spring Framework 6.2 Javadoc — AutowiredAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html).
- [Spring Framework 6.2 Javadoc — ClassPathXmlApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/ClassPathXmlApplicationContext.html).

**Ghi nhớ cuối cùng:** Trong XML Spring, `<context:annotation-config/>` bật **annotation processing trên các bean đã có**; `<context:component-scan/>` **tìm/register components** và mặc định bật annotation processing. Hai thuộc tính `annotation-config="false"` và `use-default-filters="false"` điều khiển **hai tầng khác nhau**: processors và scanner candidate selection. Phân biệt đúng **đăng ký bean** với **inject dependency** là chìa khóa để sử dụng chúng an toàn.
