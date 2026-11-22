# Spring AOP: đăng ký bean đích và tránh đối tượng tạo bằng `new` ngoài container

## 1. Vấn đề thực tế: cùng một class, vì sao lời gọi có hoặc không chạy advice?

Giả sử ứng dụng có một `ReceiptService` và một aspect ghi log trước phương thức `issue()`. Hai cách sử dụng sau có thể dẫn đến kết quả khác nhau:

```java
// Đối tượng Spring quản lý: có cơ hội nhận AOP proxy khi advisor khớp.
ReceiptService managed = applicationContext.getBean(ReceiptService.class);
managed.issue("INV-01");

// Đối tượng Java được tự tạo: không tự đi qua hạ tầng AOP của Spring.
ReceiptService unmanaged = new ReceiptService();
unmanaged.issue("INV-02");
```

Đoạn code này chỉ minh họa cách lấy đối tượng, không phải chương trình độc lập. Với Spring AOP dựa trên proxy:

- `applicationContext.getBean(...)` trả về **bean do Spring quản lý**, có thể là một **AOP proxy** nếu hạ tầng AOP đã bật và có advisor phù hợp.
- `new ReceiptService()` tạo ra một **đối tượng Java độc lập**, không được Spring tự động đăng ký và xử lý như một bean chỉ vì class của nó được gắn `@Service`.
- Advice chạy khi lời gọi **đi qua proxy**, chứ không phải vì có annotation nào đó hiện diện trên class hoặc vì object được tạo từ cùng một source code.

Điều kiện **cần** để Spring AOP tự động advice một service thông thường là đối tượng đó được Spring quản lý và lời gọi tới nó đi qua proxy phù hợp. Nhưng **đăng ký bean không tự động bảo đảm có advice**: bạn vẫn cần kích hoạt Spring AOP, có aspect/advisor được đăng ký, pointcut khớp và lời gọi qua proxy.

### Đường đi của hai đối tượng

```text
                           ApplicationContext
                                |
                     Bean definition cho service
                                |
                     Tạo + cấu hình target bean
                                |
                   Auto-proxy creator (nếu khớp)
                                |
                  Spring bean reference: proxy
                                |
           Controller / Workflow được DI service
                                |
               proxy -> advice -> target.issue()


             Code bên ngoài Spring gọi:
                   new ReceiptService()
                                |
                      object.issue() trực tiếp
                                |
                     Không có Spring AOP proxy
```

Đây là cơ chế **Spring AOP proxy** trong Spring IoC container. Không suy diễn cho cơ chế AspectJ compile-time/load-time weaving, vốn hoạt động ở mức bytecode và có phạm vi khác.

## 2. Đăng ký target bean đúng cách

### Cách A — Component scanning với `@Component` / `@Service`

Khai báo class nghiệp vụ là Spring component:

```java
package demo.springaop;

import org.springframework.stereotype.Service;

@Service
public class ReceiptService {
    public void issue(String id) {
        System.out.println("[service] issue " + id);
    }
}
```

Bật component scanning cho đúng package:

```java
package demo.springaop;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

Hai tệp này là phần của ví dụ đầy đủ ở mục 5. `@Service` là specialization của `@Component` nên Spring component scanner có thể tìm thấy. `@Repository`, `@Controller`, `@Component` cũng là các stereotype liên quan, nhưng nên chọn stereotype đúng vai trò.

**Phạm vi scan rất quan trọng:** nếu class có `@Service` nhưng package của nó nằm ngoài phạm vi `@ComponentScan`, Spring không tạo bean từ class đó bằng đường scan. Trong Spring Boot, `@SpringBootApplication` bao gồm component scanning bắt đầu từ package chứa application class và các package con mặc định; đặt main class ở package cha phù hợp, hoặc khai báo `scanBasePackages`/`scanBasePackageClasses` khi cấu trúc dự án yêu cầu.

`@Component` hay `@Service` không biến mọi lần gọi `new ReceiptService()` thành bean. Annotation là thông tin cho **container xử lý khi phát hiện class**, không can thiệp vào toán tử `new` của Java.

### Cách B — Đăng ký target với `@Bean`

Khi class không tiện gắn `@Service` (thư viện bên ngoài, code cần dựng qua factory, cấu hình cụ thể), có thể dùng phương thức `@Bean`:

```java
@Configuration
class ReceiptConfig {
    @Bean
    ReceiptService receiptService() {
        return new ReceiptService();
    }
}
```

Đây là **phương án thay thế**: hãy bỏ `@Service` hoặc loại class khỏi component scan nếu đồng thời dùng cách `@Bean` để tránh vô tình đăng ký hai bean cùng kiểu, khiến việc DI theo kiểu bị mơ hồ.

Sự khác biệt nằm ở **ai giữ quyền quản lý instance**:

- Bên trong `@Bean`, việc viết `new ReceiptService()` là hoàn toàn bình thường: Spring gọi phương thức factory, lấy object được trả về, đưa nó vào vòng đời bean và áp dụng các `BeanPostProcessor`/auto-proxy liên quan.
- Nếu business code tự viết `new ReceiptService()` và giữ riêng reference đó, Spring không biết object mới ấy thuộc bean definition nào.
- Một helper do bạn `new` bên trong một bean khác cũng không tự trở thành **bean riêng** chỉ vì bean chứa nó được Spring quản lý.

Nói cách khác, lời khuyên “tránh `new` ngoài container” áp dụng cho **các dependency cần IoC/AOP**, không phải cấm mọi toán tử `new`. Bạn vẫn có thể tạo DTO, record, value object, collection và đối tượng tạm thời thông thường bằng `new`.

### Cách C — Đăng ký programmatically và XML

Spring cũng hỗ trợ đăng ký bean definition bằng API của container hoặc cấu hình XML. Ví dụ XML minh họa:

```xml
<bean id="receiptService" class="demo.springaop.ReceiptService"/>
```

Fragment này chưa phải file XML hoàn chỉnh. Về mặt AOP, cách đăng ký cụ thể không phải trọng tâm: điều quan trọng là container có **bean definition**, quản lý quá trình khởi tạo và có thể xuất bản reference proxy.

### Điều kiện bổ sung: Aspect và hạ tầng AOP cũng phải được đăng ký

Có target bean chưa đủ. Với kiểu khai báo Spring `@AspectJ`:

```java
@Aspect
@Component
public class ReceiptAspect {
    @Before("execution(* demo.springaop.ReceiptService.issue(..))")
    public void beforeIssue() {
        System.out.println("[aop] before issue");
    }
}
```

Đoạn này minh họa aspect; các import đầy đủ có trong mục 5. `@Aspect` **không tự khiến class được component scanner đăng ký**; dùng thêm `@Component` hoặc tạo aspect qua `@Bean`. Hạ tầng auto-proxy cũng phải được bật, ví dụ `@EnableAspectJAutoProxy` khi dùng Spring Framework thuần. Có thể dùng Spring Boot với `spring-boot-starter-aop` để nhận auto-configuration AOP thích hợp.

**Phân biệt:** `@Aspect` mô tả aspect, còn `@Service`/`@Component`/`@Bean` đưa các instance vào container. Target bean và aspect bean là hai vai trò khác nhau trong Spring AOP.

## 3. Vì sao container có thể trả về proxy?

Quy trình thường gặp với một singleton:

1. Spring biết bean definition của target nhờ component scan, `@Bean` hoặc cơ chế đăng ký tương đương.
2. Container tạo instance, resolve dependency, tiêm cấu hình và thực hiện initialization callbacks.
3. Hạ tầng `BeanPostProcessor` của Spring AOP xem xét các advisor; khi pointcut khớp và proxy được yêu cầu, nó có thể bọc target bằng proxy.
4. Bean khác yêu cầu dependency từ Spring sẽ nhận **reference được container công bố**; nếu đã được AOP bọc, reference này là proxy.
5. Lời gọi method qua proxy đi qua interceptor/advice trước hoặc sau khi đến target, tùy loại advice và pointcut.

```text
Spring-managed consumer
        |
        | constructor injection
        v
   service reference
        |
        v
   Spring AOP proxy
        |
        +----> advice
        |
        v
   target method
```

Thời điểm tạo proxy thực tế có thể bị ảnh hưởng bởi scope, circular dependency hoặc các custom post-processor. Bản chất không đổi: **caller phải dùng reference proxy**, không phải một target riêng tự tạo.

### Cùng kiểu class nhưng không nhất thiết cùng object

Hai dòng sau không có nghĩa tương đương:

```java
ReceiptService fromSpring = context.getBean(ReceiptService.class);
ReceiptService fromNew = new ReceiptService();
```

Với một Spring-managed singleton được AOP bọc, `fromSpring` thường là reference proxy. `fromNew` là instance độc lập. Những phép kiểm tra như `fromSpring == fromNew` thường sẽ cho `false`; cũng không nên dựa vào `fromSpring.getClass() == ReceiptService.class` khi Spring đã tạo subclass proxy.

Dùng API Spring để chẩn đoán:

```java
boolean proxied = AopUtils.isAopProxy(fromSpring);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(fromSpring);
boolean cglibProxy = AopUtils.isCglibProxy(fromSpring);
```

Ba lệnh chỉ minh họa API, không phải chương trình độc lập. Trong ví dụ hoàn chỉnh, service không triển khai interface nên Spring AOP thường tạo class-based proxy. Nếu target có interface, kiểu proxy phụ thuộc vào cấu hình, như `proxyTargetClass`; luôn kiểm tra **bean thực tế nhận được**.

## 4. Dependency Injection là cách tiêu chuẩn đưa proxy đến nơi gọi

Thay vì:

```java
public class CheckoutWorkflow {
    private final ReceiptService service = new ReceiptService();

    public void checkout(String id) {
        service.issue(id);
    }
}
```

hãy biến workflow thành Spring bean và khai báo constructor injection:

```java
@Component
public class CheckoutWorkflow {
    private final ReceiptService service;

    public CheckoutWorkflow(ReceiptService service) {
        this.service = service;
    }

    public void checkout(String id) {
        service.issue(id);
    }
}
```

Các đoạn trong mục này minh họa khác biệt, không phải tệp Java độc lập. Khi `CheckoutWorkflow` được Spring tạo, container resolve `ReceiptService` và có thể inject proxy phù hợp. Với một constructor duy nhất, Spring tự động chọn constructor injection mà không cần `@Autowired`.

**Lưu ý khi gọi từ code ngoài Spring:** Controller, scheduled task, message listener, startup runner, test hoặc object do framework khác tạo cần nhận service từ container bằng cơ chế tích hợp thích hợp. Không tự `new` service trong callback rồi kỳ vọng aspect Spring chặn method call. Khi ở ranh giới ứng dụng cần lấy bean, dùng DI là ưu tiên; lấy trực tiếp qua `ApplicationContext.getBean(...)` là lựa chọn hợp lý tại điểm tích hợp, nhưng không nên biến toàn bộ business code thành service locator.

### Hai lỗi khác nhau dễ bị nhầm

- **Target tự tạo bằng `new`:** object không có Spring proxy ngay từ đầu. Dù method được gọi từ bên ngoài object, Spring AOP không có reference proxy để intercept.
- **Self-invocation trên target đã được Spring quản lý:** bean đã có proxy, nhưng `this.otherMethod()` bên trong target vẫn gọi trực tiếp trên target, bỏ qua proxy. Đây là vấn đề đường gọi, không phải thiếu bean registration.

Ví dụ:

```java
@Service
class InvoiceService {
    public void outer() {
        this.inner(); // Không đi qua Spring AOP proxy.
    }

    public void inner() {
        // Advice dành cho inner() sẽ không tự chạy khi gọi từ outer().
    }
}
```

Đây là đoạn minh họa trong một hệ thống có advisor cho `inner()`. Cách xử lý phù hợp là tách phần được advice vào một Spring bean khác rồi inject bean đó, để lời gọi đi qua reference do container cấp.

## 5. Ví dụ Maven + Java 17 chạy được: managed bean và object tự `new`

Ví dụ dùng **Spring Framework 6.2.x**, Java 17 và Maven. Không cần Spring Boot. Có 4 tệp Java trong package `demo.springaop` và một `pom.xml`. Aspect ghi log trước `ReceiptService.issue()`; main so sánh lời gọi trên bean do Spring quản lý và object tự tạo.

Cấu trúc:

```text
spring-aop-managed-target/
├── pom.xml
└── src/main/java/demo/springaop/
    ├── AppConfig.java
    ├── ReceiptService.java
    ├── ReceiptAspect.java
    ├── CheckoutWorkflow.java
    └── DemoMain.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-managed-target</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
```

**Tệp `src/main/java/demo/springaop/AppConfig.java`:**

```java
package demo.springaop;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy
public class AppConfig {
}
```

`@ComponentScan(basePackageClasses = AppConfig.class)` tìm các Spring component trong package `demo.springaop`, nơi có target, workflow và aspect. `@EnableAspectJAutoProxy` cho phép Spring tự tạo proxy khi advice khớp.

**Tệp `src/main/java/demo/springaop/ReceiptService.java`:**

```java
package demo.springaop;

import org.springframework.stereotype.Service;

@Service
public class ReceiptService {
    public void issue(String id) {
        System.out.println("[service] issue " + id);
    }
}
```

Service này được Spring phát hiện qua `@Service`. Class và method không `final` nên có thể được bọc bằng class-based proxy trong ví dụ không có interface.

**Tệp `src/main/java/demo/springaop/ReceiptAspect.java`:**

```java
package demo.springaop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class ReceiptAspect {
    @Before("execution(* demo.springaop.ReceiptService.issue(..))")
    public void beforeIssue() {
        System.out.println("[aop] before issue");
    }
}
```

Aspect là một Spring bean nhờ `@Component`, đồng thời có advice `@Before` áp dụng lên phương thức `issue()`.

**Tệp `src/main/java/demo/springaop/CheckoutWorkflow.java`:**

```java
package demo.springaop;

import org.springframework.stereotype.Component;

@Component
public class CheckoutWorkflow {
    private final ReceiptService receiptService;

    public CheckoutWorkflow(ReceiptService receiptService) {
        this.receiptService = receiptService;
    }

    public void checkout(String id) {
        System.out.println("[workflow] checkout " + id);
        receiptService.issue(id);
    }
}
```

Workflow cũng do Spring tạo. Dependency `receiptService` trong constructor là reference được container cấp; nếu Spring đã tạo AOP proxy cho service thì workflow sử dụng proxy đó.

**Tệp `src/main/java/demo/springaop/DemoMain.java`:**

```java
package demo.springaop;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoMain {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            ReceiptService managed = context.getBean(ReceiptService.class);
            System.out.println("managedProxy=" + AopUtils.isAopProxy(managed));

            context.getBean(CheckoutWorkflow.class).checkout("INV-01");

            ReceiptService unmanaged = new ReceiptService();
            System.out.println("manualProxy=" + AopUtils.isAopProxy(unmanaged));
            unmanaged.issue("INV-02");
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.springaop.DemoMain
```

**Stdout từ các câu lệnh `System.out` của chương trình** (Maven/Spring có thể có log khác tùy môi trường):

```text
managedProxy=true
[workflow] checkout INV-01
[aop] before issue
[service] issue INV-01
manualProxy=false
[service] issue INV-02
```

Phân tích từng điểm:

1. `managedProxy=true`: Spring đã nhận diện `ReceiptService` là target, `ReceiptAspect` có pointcut khớp, nên container cung cấp proxy.
2. `CheckoutWorkflow` dùng constructor injection. Khi gọi `receiptService.issue("INV-01")`, invocation qua proxy kích hoạt dòng `[aop] before issue` trước dòng business.
3. `new ReceiptService()` trong `DemoMain` tạo object độc lập, không phải Spring bean; `AopUtils.isAopProxy(unmanaged)` cho `false`.
4. `unmanaged.issue("INV-02")` gọi trực tiếp object tự tạo nên **không có dòng `[aop]`** cho `INV-02`.
5. Không có gì sai với method `issue()` của object unmanaged: Java vẫn gọi method và in ra kết quả. Phần khác biệt là **hạ tầng proxy AOP không tham gia**.

Nếu bỏ `@Component` khỏi `ReceiptAspect` mà không đăng ký aspect bằng `@Bean`, aspect không được phát hiện; target có thể vẫn là Spring bean nhưng không có advice tương ứng. Nếu bỏ `@Service` khỏi `ReceiptService` mà không thay bằng `@Bean`, ứng dụng sẽ không có bean để inject vào `CheckoutWorkflow` và quá trình khởi tạo context sẽ lỗi khi cần dependency.

### Cùng một class, thay đường đăng ký bằng `@Bean`

Để sử dụng factory method thay component scan, **bỏ `@Service` khỏi `ReceiptService`** và thêm phương thức sau vào `AppConfig`:

```java
@Bean
public ReceiptService receiptService() {
    return new ReceiptService();
}
```

Đoạn trên là **fragment đặt bên trong class `@Configuration`**, cần import `org.springframework.context.annotation.Bean`. Dù chứa từ khóa `new`, object trả về chính là bean được container quản lý, nên Spring AOP vẫn có cơ hội bọc nó. Đây là ngoại lệ quan trọng giúp phân biệt “dùng `new` trong bean factory” và “tự `new` một service rồi gọi bên ngoài container”.

## 6. Các trường hợp khó hơn cần nhận diện

### 6.1 Một class có hai instance: một managed, một unmanaged

Ví dụ một constructor của Spring bean vẫn tự tạo dependency:

```java
@Component
class ProcessingHandler {
    private final ReceiptService badService = new ReceiptService();

    void handle() {
        badService.issue("BAD");
    }
}
```

`ProcessingHandler` được Spring quản lý **không đồng nghĩa** với `badService` bên trong nó được container quản lý. Đây chỉ là một field tham chiếu đến object Java mới. Cách sửa là đưa `ReceiptService` vào constructor như ở `CheckoutWorkflow`.

### 6.2 `@Autowired` trên một object tự tạo không tự hoạt động

```java
class OutsideContainer {
    @Autowired
    ReceiptService service;
}

// Tạo bên ngoài container:
OutsideContainer object = new OutsideContainer();
```

Ví dụ này là fragment minh họa. Field `service` sẽ không tự được Spring inject chỉ vì có `@Autowired`. Lý do cùng gốc với AOP: object không đi qua cơ chế tạo/cấu hình bean thông thường của container.

### 6.3 Có hai bean cùng kiểu

Nếu vừa dùng `@Service` vừa dùng `@Bean` để tạo thêm một `ReceiptService`, injection theo kiểu có thể trở nên không xác định. Nên tránh đăng ký trùng không chủ đích. Khi thực sự cần nhiều implementation hoặc nhiều bean cùng kiểu, đặt tên rõ ràng và dùng `@Qualifier` hay `@Primary` thích hợp. Đối với Spring AOP, mỗi bean được container chọn sẽ có thể có proxy riêng; đừng đánh đồng “một class” với “một Spring bean duy nhất”.

### 6.4 Bean scope và object được tạo nhiều lần

`singleton` mặc định có một bean instance cho mỗi Spring container/bean definition theo scope; không có nghĩa toàn bộ JVM chỉ có một object kiểu đó. `prototype` cho phép container tạo instance mới khi bean được yêu cầu và Spring vẫn xử lý initialization/AOP tương ứng. Nhưng mỗi `new ReceiptService()` ngoài container vẫn không được quản lý chỉ vì có một prototype bean definition cùng class.

### 6.5 Hai `ApplicationContext` hoặc ứng dụng có parent/child context

Một target bean được quản lý trong context A chưa chắc có proxy bởi advisor/aspect cấu hình trong context B. `@EnableAspectJAutoProxy` có phạm vi theo context; ứng dụng có nhiều context cần đăng ký cấu hình tại đúng nơi. Vì thế khi debug phải kiểm tra **reference và context thực tế**, không chỉ tên class.

### 6.6 Lấy target thô rồi gọi trực tiếp

Khi Spring đã tạo proxy, không nên cố lấy target nội bộ từ proxy để gọi business methods (ví dụ qua các API debug nội bộ) rồi thắc mắc advice không chạy. Đường gọi bỏ qua proxy sẽ bỏ qua advice. Nguyên tắc tương tự áp dụng cho self-invocation.

### 6.7 Có ngoại lệ công nghệ nào để xử lý object tạo ngoài container không?

Spring có các API tích hợp cấp thấp như `AutowireCapableBeanFactory` để cấu hình đối tượng được tạo sẵn; `initializeBean(...)` có thể trả về object đã qua hậu xử lý, thậm chí được bọc. Tuy nhiên **bạn phải dùng reference được trả về và quản lý vòng đời cẩn thận**: việc autowire một instance bên ngoài không biến mọi reference đã trỏ tới instance đó thành AOP proxy.

Spring cũng có tích hợp AspectJ weaving cho một số trường hợp domain object tạo ngoài container, nhưng đó **không phải** Spring AOP proxy tiêu chuẩn và đòi hỏi cấu hình riêng. Trong bài này, giải pháp mặc định là đăng ký service thành bean và inject đúng reference từ Spring.

## 7. Checklist khi “aspect không chạy”

| Triệu chứng | Kiểm tra cụ thể |
| --- | --- |
| Service có `@Service` nhưng advice không chạy | Service có được component scan đúng package không? Có thực sự được Spring inject/getBean? |
| Business code dùng `new SomeService()` | Có object unmanaged; thay bằng constructor injection của Spring-managed service. |
| `@Bean` chứa `new` nên lo không có AOP | Object **được trả về từ method @Bean** là managed bean; xem advisor/pointcut và reference consumer dùng. |
| Aspect có `@Aspect` nhưng chưa được nhận diện | Thêm `@Component` hoặc một `@Bean` đăng ký aspect, và bật auto-proxy. |
| Target có bean nhưng `AopUtils.isAopProxy` là `false` | Kiểm tra có advisor nào thực sự khớp và auto-proxy có đang hoạt động trong context đó. |
| Proxy tồn tại nhưng một method không được advice | Xem pointcut, loại proxy, method `final`/`private`, và đường gọi qua `this`. |
| Injection theo concrete class lỗi khi AOP bật | JDK dynamic proxy chỉ thực hiện interface; inject theo interface hoặc cân nhắc class-based proxy phù hợp. |
| Vừa `@Service` vừa `@Bean` cùng kiểu | Kiểm tra bean trùng, `@Qualifier`, `@Primary` và phương thức đăng ký mong muốn. |
| Có nhiều `ApplicationContext` | Kiểm tra target, aspect và auto-proxy cùng thuộc context thích hợp. |
| Self-invocation `this.other()` | Gọi thẳng target, bỏ qua proxy; tách method cần intercept sang Spring bean khác. |

Để xác định nguyên nhân theo thứ tự hợp lý:

1. Tìm nơi object được tạo. Nếu là `new` trực tiếp trong business code, xem đó có phải dependency cần AOP hay không.
2. Nếu đã là bean, kiểm tra bean definition, component scan hoặc `@Bean` và cấu hình của context.
3. Kiểm tra aspect cũng được đăng ký là Spring bean, và auto-proxy đã bật.
4. Trên reference được inject hoặc trả về từ context, dùng `AopUtils.isAopProxy(...)`.
5. Nếu đã là proxy, xác nhận phương thức được gọi **qua reference này** và pointcut khớp.
6. Nếu vẫn không có advice, kiểm tra self-invocation, method accessibility/finality, kiểu proxy và những khác biệt giữa contexts.

## 8. Câu hỏi ôn tập

**1. Gắn `@Service` rồi viết `new Service()` có được AOP tự động không?** Không. `@Service` chỉ giúp Spring phát hiện class khi component scanning; object tạo riêng bằng `new` không tự được Spring quản lý.

**2. Dùng `new` trong phương thức `@Bean` có sai không?** Không. Đây là cách hợp lệ để tạo một instance cho Spring quản lý. Container có thể hậu xử lý và proxy object trả về.

**3. Bean đã được đăng ký có chắc chắn chạy advice?** Không. Còn phải có AOP hạ tầng được bật, aspect/advisor phù hợp, pointcut khớp và lời gọi đi qua proxy.

**4. Controller được Spring quản lý thì mọi field do nó tạo bằng `new` có được Spring quản lý không?** Không. Chỉ những dependency được đăng ký và resolve qua container mới có vòng đời bean tương ứng; object tạo trực tiếp vẫn là object Java.

**5. `this.inner()` trong một bean đã proxy khác gì `new Service().inner()`?** Cả hai có thể bỏ qua advice, nhưng lý do khác nhau: `this.inner()` là self-invocation bypass proxy, còn object tạo bằng `new` ban đầu đã không có proxy.

**6. Nên tổ chức code như thế nào để hạn chế lỗi?** Đăng ký target và aspect thành Spring beans, để Spring tạo consumer, dùng constructor injection cho dependency cần AOP, và đặt ranh giới gọi giữa các bean cho những method cần interception.

## Tài liệu Spring chính thức

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — @AspectJ support và đăng ký aspects](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html)
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring Framework — Sử dụng @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework — Integrating AspectJ with Spring Applications](https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html)
