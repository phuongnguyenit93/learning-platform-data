# Chọn đúng độ rộng pointcut để tránh can thiệp bean ngoài ý muốn trong Spring AOP

## 1. Vì sao phải kiểm soát độ rộng pointcut?

Trong **Spring AOP**, một pointcut mô tả **các method execution trên Spring beans** mà advice có thể áp dụng. Một biểu thức hợp lệ về cú pháp vẫn có thể **quá rộng so với ý định nghiệp vụ**. Ví dụ, advice audit được thiết kế chỉ cho thao tác thanh toán nhưng lại match cả dịch vụ gửi báo cáo, dịch vụ đồng bộ hoặc các bean hỗ trợ khác.

Khi một advisor match thêm bean ngoài ý muốn, hậu quả có thể là:

- **Log/metrics sai phạm vi:** số lượt gọi và latency bị ghi nhận cho cả method không thuộc nghiệp vụ cần theo dõi.
- **Tăng chi phí xử lý:** advice không cần thiết chạy trên quá nhiều lời gọi; nếu advice có I/O, chi phí có thể lớn.
- **Sai hành vi:** `@Around` có thể thay đổi kết quả, xử lý exception, retry hoặc short-circuit những method không nên bị tác động.
- **Lộ dữ liệu:** advice ghi đối số/giá trị trả về vô điều kiện có thể đưa thông tin nhạy cảm vào log.
- **Khó debug:** một aspect tưởng chỉ phục vụ module A bất ngờ ảnh hưởng module B, nhất là khi thêm bean mới sau này.
- **Proxy hóa nhiều bean hơn cần thiết:** bean phù hợp với advisor có thể bị Spring AOP auto-proxy, thay đổi runtime type, đường gọi và các giới hạn proxy.

Mục tiêu của bài: học cách chọn phạm vi chính xác theo **package, lớp, phương thức, annotation, kiểu target và tên Spring bean**, đồng thời kiểm thử **những đối tượng không được match**. Đây là hướng dẫn dành riêng cho **Spring Aspect/Spring AOP proxy-based**, không lặp lại lý thuyết Aspect tổng quát.

## 2. Mô hình hai bước: advisor áp dụng cho bean, advice áp dụng cho invocation

Một biểu thức như:

```java
@Before("execution(public * example.service..*Service.*(..))")
```

có thể khiến Spring nhận diện nhiều lớp trong hệ thống có những method public tương ứng. Spring AOP auto-proxy xem một advisor có khả năng áp dụng cho **target class** khi khởi tạo bean, rồi xét các method và điều kiện invocation phù hợp.

```text
Spring @Aspect bean --> @Before / @Around và pointcut expression
                                   |
                            candidate advisor
                                   |
          Spring AOP xét bean theo type, method, bean name...
                                   |
                    target bean có advisor phù hợp?
                         /                         \
                       có                         không
                       |                            |
                 Có thể tạo proxy            Không proxy do advisor đó
                       |
                Caller gọi method
                       |
              Method / runtime match?
                    /       \
                  có        không
                  |           |
             Advice chạy   Bỏ qua advice này
                  |
             Target method
```

**Không đánh đồng các khẳng định sau:**

1. `AopUtils.isAopProxy(bean) == true`: bean là Spring AOP proxy; **không** khẳng định mọi method đều chạy một advice.
2. Advisor *có thể áp dụng cho class*: ít nhất một method/điều kiện có khả năng match; **không** khẳng định mọi lời gọi được can thiệp.
3. Pointcut match một method: advice chỉ chạy khi invocation đi **qua Spring proxy** và mọi điều kiện động đều thỏa.

Ngược lại, nếu pointcut quá rộng, Spring có thể proxy **nhiều target beans** hơn dự kiến, kể cả các bean được thêm vào trong tương lai có tên lớp/method trùng quy tắc.

## 3. Độ rộng pointcut được quyết định bởi những chiều nào?

| Chiều chọn | Cú pháp Spring AOP tiêu biểu | Cần chú ý |
| --- | --- | --- |
| Phạm vi package và lớp | `within(com.acme.payment..*)` | Giới hạn method execution của types trong package tương ứng và package con; không đồng nghĩa chỉ một bean |
| Chữ ký phương thức | `execution(public * com.acme.payment.PaymentService.pay(..))` | Giới hạn public, class, method name, tham số; biểu thức càng rõ càng ít match nhầm |
| Bean name | `bean(paymentService)` | Spring-specific PCD; tên bean phải đúng với cấu hình IoC |
| Annotation trên method | `@annotation(com.acme.audit.Audited)` | Chỉ match method có annotation tương ứng theo ngữ nghĩa Spring AOP |
| Annotation trên type | `@within(com.acme.audit.AuditedType)` | Giới hạn method thuộc type có annotation; cần kiểm tra ngữ nghĩa kế thừa/interface |
| Target type | `target(com.acme.payment.PaymentService)` | Kiểu của target object; khác `this(...)` khi dùng JDK proxy |
| Runtime arguments | `args(java.lang.String)` | Có thể phụ thuộc kiểu argument thực tế tại invocation, không chỉ signature |
| Kết hợp | `execution(...) && within(...) && bean(...)` | Giao các tập match: mọi điều kiện cùng đúng |
| Mở rộng | `execution(...) || @annotation(...)` | Hợp các tập match: thường **rộng hơn**, cần thử trường hợp ngoài phạm vi |
| Loại trừ | `!within(com.acme.internal..*)` | Trừ đi một nhóm; riêng điều kiện loại trừ không đủ tạo allowlist an toàn |

**Phạm vi Spring:** `execution`, `within`, `this`, `target`, `args`, `@annotation`, `@within` và `bean` là các cách giới hạn thường gặp. Spring AOP chỉ hỗ trợ **method execution join points trên Spring-managed beans**. Không sử dụng `call()`, `get()`, `set()` hoặc các PCD chỉ thuộc AspectJ weaving trong một Spring AOP expression vì chúng không được hỗ trợ ở đây.

## 4. Từ pointcut nguy hiểm đến pointcut có chủ đích

Giả sử dự án có hai loại bean:

- `PaymentService`: nghiệp vụ thanh toán, gồm `pay()` và `status()`.
- `ReportService`: tạo báo cáo, gồm `generate()`.

Yêu cầu nghiệp vụ: **chỉ ghi audit trước `PaymentService.pay()` của bean `paymentService`**.

### 4.1. Biểu thức quá rộng

```java
@Before("execution(public * example.service..*Service.*(..))")
```

Điều kiện này chọn **mọi method public** trên các lớp có tên phù hợp mẫu `*Service` trong và dưới package `example.service`. Nếu `PaymentService` và `ReportService` cùng match, advice chạy cả ba method `pay()`, `status()`, `generate()`.

Rủi ro thực tế: một team khác thêm `TaxService`, `EmailService` hay `HealthService` vào package tương tự. **Không cần sửa aspect**, advisor vẫn có thể bắt đầu can thiệp các bean mới nếu pointcut match. Cú pháp đúng nhưng **phạm vi nghiệp vụ không đúng**.

### 4.2. Chỉ giới hạn package

```java
@Before("execution(public * example.service.payment..*.*(..))")
```

Biểu thức này đã loại trừ báo cáo ở package `example.service.report`, nhưng **vẫn match mọi public method** của mọi class trong khu vực thanh toán. Nếu bạn chỉ cần `pay()`, nó vẫn rộng quá mức.

### 4.3. Giới hạn đúng method và bean

```java
@Before(
    "execution(public * example.service.payment.PaymentService.pay(..))" +
    " && bean(paymentService)"
)
```

Điều kiện trên chọn một chữ ký method cụ thể **và** Spring bean đúng tên. Đặc biệt hữu ích khi có nhiều bean cùng class hoặc bạn đang triển khai aspect theo đúng đối tượng/tenant/adapter được quản lý bởi Spring.

Đặt `bean(paymentService)` là Spring-specific pointcut designator: nó có ý nghĩa **trong Spring AOP**, không nên đưa nguyên xi sang AspectJ compiler/weaver với kỳ vọng được hỗ trợ.

Nếu ứng dụng đổi bean name vì refactor, pointcut sẽ phải cập nhật. Khi tên bean không phải hợp đồng ổn định, sử dụng **kiểu lớp, module/package hoặc annotation chuyên dụng** để diễn đạt ý định thay vì buộc nó vào tên.

### 4.4. Đừng dùng nhiều điều kiện chỉ để dài hơn

Không nhất thiết mọi pointcut cần vừa `execution` vừa `within` vừa `bean`. Nếu một chữ ký đã xác định chính xác nghiệp vụ và package, các điều kiện bổ sung có thể là dư thừa hoặc làm cấu hình quá nhạy với thay đổi. Mục tiêu là **phạm vi nhỏ nhất diễn đạt được ý định mà vẫn ổn định**, không phải biểu thức có nhiều toán tử nhất.

Một quy tắc thực hành hữu ích: chọn **phạm vi module/package** trước, sau đó giới hạn **loại method** cần advice; chỉ dùng `bean` hoặc `@annotation` nếu đó thật sự là một phần hợp đồng.

## 5. Ví dụ Maven/Java 17+ chạy được: rộng và hẹp

Ví dụ này tạo **hai Spring ApplicationContext độc lập** để so sánh hai pointcut trên **cùng các service classes**. Tách context giúp không bị lẫn hai aspect và không phụ thuộc thứ tự advisor.

Sử dụng **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**. Trong dự án thực tế, ưu tiên BOM của Spring Framework hoặc Spring Boot để quản lý phiên bản; ví dụ cố định chúng để tái hiện độc lập.

### 5.1. Cấu trúc thư mục

```text
pointcut-width-demo/
├── pom.xml
└── src/main/java/example/
    ├── Main.java
    ├── service/
    │   ├── payment/PaymentService.java
    │   └── report/ReportService.java
    ├── aop/
    │   ├── BroadAspect.java
    │   └── NarrowAspect.java
    └── config/
        ├── ServicesConfig.java
        ├── BroadConfig.java
        └── NarrowConfig.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>pointcut-width-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. PaymentService

**`src/main/java/example/service/payment/PaymentService.java`**

```java
package example.service.payment;

public class PaymentService {

    public void pay() {
        System.out.println("payment: pay");
    }

    public void status() {
        System.out.println("payment: status");
    }
}
```

### 5.4. ReportService

**`src/main/java/example/service/report/ReportService.java`**

```java
package example.service.report;

public class ReportService {

    public void generate() {
        System.out.println("report: generate");
    }
}
```

### 5.5. Aspect quá rộng

**`src/main/java/example/aop/BroadAspect.java`**

```java
package example.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class BroadAspect {

    @Before("execution(public * example.service..*Service.*(..))")
    public void beforeAnyServiceMethod() {
        System.out.println("broad: before");
    }
}
```

Nó không có `@Component` vì sẽ được đăng ký qua `@Bean` trong `BroadConfig`. Biểu thức cố ý match cả payment/report services. Đây là **mẫu để thấy lỗi về phạm vi**, không phải khuyến nghị áp dụng rộng khắp production.

### 5.6. Aspect giới hạn đúng mục tiêu

**`src/main/java/example/aop/NarrowAspect.java`**

```java
package example.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class NarrowAspect {

    @Before(
        "execution(public * example.service.payment.PaymentService.pay(..))"
        + " && bean(paymentService)"
    )
    public void beforePayment() {
        System.out.println("narrow: before payment pay");
    }
}
```

Pointcut này không nhắm tới `PaymentService.status()`, `ReportService.generate()`, hay một bean khác chỉ tình cờ có method tên `pay()`.

### 5.7. Cấu hình các beans chung

**`src/main/java/example/config/ServicesConfig.java`**

```java
package example.config;

import example.service.payment.PaymentService;
import example.service.report.ReportService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ServicesConfig {

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService();
    }
}
```

Vì tên method `@Bean` là `paymentService`, bean có tên này trong context, đáp ứng `bean(paymentService)`. Nếu đổi tên bean, cần sửa điểm cắt hoặc bỏ ràng buộc theo tên.

### 5.8. Context sử dụng broad pointcut

**`src/main/java/example/config/BroadConfig.java`**

```java
package example.config;

import example.aop.BroadAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import(ServicesConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class BroadConfig {

    @Bean
    public BroadAspect broadAspect() {
        return new BroadAspect();
    }
}
```

### 5.9. Context sử dụng narrow pointcut

**`src/main/java/example/config/NarrowConfig.java`**

```java
package example.config;

import example.aop.NarrowAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import(ServicesConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class NarrowConfig {

    @Bean
    public NarrowAspect narrowAspect() {
        return new NarrowAspect();
    }
}
```

Cả hai context đều dùng `@EnableAspectJAutoProxy` nhưng đăng ký **một aspect khác nhau**. Nhờ `proxyTargetClass=true`, demo có thể lấy service theo concrete class mà không lo vấn đề kiểu của JDK proxy; đây không phải yêu cầu bắt buộc để giới hạn pointcut.

### 5.10. Chạy và so sánh

**`src/main/java/example/Main.java`**

```java
package example;

import example.config.BroadConfig;
import example.config.NarrowConfig;
import example.service.payment.PaymentService;
import example.service.report.ReportService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        System.out.println("-- BROAD --");
        try (var ctx = new AnnotationConfigApplicationContext(BroadConfig.class)) {
            PaymentService payment = ctx.getBean(PaymentService.class);
            ReportService report = ctx.getBean(ReportService.class);

            System.out.println("payment proxy: " + AopUtils.isAopProxy(payment));
            System.out.println("report proxy: " + AopUtils.isAopProxy(report));

            payment.pay();
            payment.status();
            report.generate();
        }

        System.out.println("-- NARROW --");
        try (var ctx = new AnnotationConfigApplicationContext(NarrowConfig.class)) {
            PaymentService payment = ctx.getBean(PaymentService.class);
            ReportService report = ctx.getBean(ReportService.class);

            System.out.println("payment proxy: " + AopUtils.isAopProxy(payment));
            System.out.println("report proxy: " + AopUtils.isAopProxy(report));

            payment.pay();
            payment.status();
            report.generate();
        }
    }
}
```

Trong thư mục dự án:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

**Output của các lệnh `System.out.println` ở đúng các file trên:**

```text
-- BROAD --
payment proxy: true
report proxy: true
broad: before
payment: pay
broad: before
payment: status
broad: before
report: generate
-- NARROW --
payment proxy: true
report proxy: false
narrow: before payment pay
payment: pay
payment: status
report: generate
```

Có thể có log build/runtime khác của Maven hoặc framework; bảng chỉ liệt kê những dòng do chương trình mẫu in ra.

### 5.11. Ý nghĩa kết quả

- **BROAD:** cả PaymentService và ReportService bị pointcut match, nên đều có Spring AOP proxy. Advice chạy trước cả `pay()`, `status()` và `generate()`. Như vậy ba lời gọi bị audit dù nhu cầu ban đầu chỉ có một.
- **NARROW:** chỉ `paymentService.pay()` đủ điều kiện, nên PaymentService có proxy. `payment.status()` được gọi trên cùng proxy nhưng **không chạy narrow advice**, vì method không match. ReportService không cần proxy **do advisor của ví dụ** và `AopUtils.isAopProxy(report)` là `false` trong context này.
- Không thay đổi các target classes, chỉ thay **độ rộng pointcut** đã đổi phạm vi bean và lời gọi thực sự bị can thiệp.
- Không suy từ `isAopProxy(payment) == true` rằng mọi method của PaymentService đều chạy advice. Cấp **bean** và cấp **method** có quyết định khác nhau.

Nếu ứng dụng bổ sung advisor khác (transaction/cache, v.v.), một bean không match narrow advice vẫn có thể là proxy do **advisor khác**. Kết quả `report proxy: false` được dự đoán theo đúng cấu hình demo tối giản.

## 6. Viết pointcut theo module/package thay vì match toàn ứng dụng

Trong codebase có nhiều module, package là một giới hạn tự nhiên. Ví dụ ứng dụng thật có:

```text
com.acme.payment.service
com.acme.payment.repository
com.acme.reporting.service
com.acme.inventory.service
```

Nếu advice chỉ dành cho service thanh toán, chọn:

```java
@Pointcut("within(com.acme.payment.service..*)")
public void inPaymentServiceLayer() {}

@Pointcut("execution(public * *(..))")
public void anyPublicMethod() {}

@Pointcut("inPaymentServiceLayer() && anyPublicMethod()")
public void paymentPublicOperations() {}
```

Đây là **snippet bên trong một class `@Aspect`**, không phải chương trình Java độc lập. Nó dùng **named pointcuts** để đặt tên cho ý định. `within(com.acme.payment.service..*)` giới hạn theo types trong vùng code; `execution(public * *(..))` giới hạn method public; giao nhau diễn đạt “public operations thuộc service layer thanh toán”.

Tránh:

```java
@Before("execution(* com.acme..*(..))")
```

Biểu thức kiểu này có phạm vi rất rộng và khó hiểu/kiểm soát. Nó còn có thể khiến class/method ngoài phạm vi nghiệp vụ được xem xét khi ứng dụng phát triển.

**Lưu ý:** Không phải cứ có package tên `service` là tất cả method trong đó đều cần advice. Giới hạn package là bước đầu, **không thay thế ràng buộc theo chức năng thực sự cần can thiệp**.

## 7. Khi nào nên dùng annotation làm hợp đồng opt-in?

Nếu các method cần advice phân tán ở nhiều package, hoặc chỉ **một số** method nghiệp vụ được lựa chọn, một annotation chuyên dụng có thể diễn đạt ý định bền vững hơn so với tên method hoặc bean.

**`AuditedOperation.java` — đoạn minh họa đầy đủ annotation type:**

```java
package com.acme.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditedOperation {
}
```

Một service có thể đánh dấu **đúng method cần audit**:

```java
// Snippet bên trong một service đã được Spring quản lý.
@AuditedOperation
public void approvePayment() {
    // ...
}

public void previewPayment() {
    // Không có annotation audit.
}
```

Aspect chọn marker trong phạm vi module:

```java
@Aspect
public class PaymentAuditAspect {
    @Before(
        "within(com.acme.payment..*)"
        + " && @annotation(com.acme.audit.AuditedOperation)"
    )
    public void beforeAuditedPayment() {
        // Chỉ method được đánh dấu và nằm trong module payment.
    }
}
```

Đây là **snippet bổ sung**: trong ứng dụng thật class aspect cần đăng ký thành Spring bean, cần AOP được bật và class annotation phải nằm trên classpath. Không cho rằng `@Aspect` tự đăng ký qua component scanning.

**Lợi ích:** team đọc code sẽ nhận ra method nào *opt-in* cho advice. Nếu method bị đổi tên hoặc refactor sang class khác nhưng vẫn giữ annotation trong module cho phép, ý định có thể được giữ lại.

**Hạn chế:** Cần thống nhất vị trí annotation khi proxy interface hoặc implementation, và viết kiểm thử xác nhận pointcut thực sự match trong chiến lược JDK/CGLIB đang chạy. `@annotation` match annotation của **method**, không phải annotation trên mọi class hoặc field.

Một marker annotation không thể bảo vệ dữ liệu nhạy cảm nếu advice vẫn log bừa bãi các tham số; hãy thiết kế nội dung log riêng.

## 8. Điều kiện `bean()`: chính xác nhưng có coupling

Spring cung cấp `bean(idOrNamePattern)`, một pointcut designator **riêng của Spring AOP**. Ví dụ:

```java
@Before("bean(paymentService) && execution(public * *.pay(..))")
```

Khi các bean khác nhau cùng implements interface thanh toán hoặc cùng class, tên bean có thể tách đối tượng cần audit. Dùng `bean()` khi **tên bean là một phần hợp đồng triển khai**, chẳng hạn một adapter được cấu hình có chủ đích.

Lưu ý:

- Pattern bean name có thể sử dụng ký tự `*`, ví dụ `bean(*PaymentService)`. Biểu thức dùng tên bean, **không phải** tên class Java.
- Nếu component name do Spring tự suy luận hoặc bị thay bởi naming strategy, biểu thức có thể không còn match.
- Nếu sử dụng bean alias/FactoryBean hoặc context cha-con, hãy kiểm tra cách tên bean thực tế được resolve.
- Một phép thử thuần `AopUtils.canApply(pointcut, SomeClass.class)` **không thay thế** kiểm thử ở context thật với bean name cụ thể.
- `bean()` là Spring-specific, không thuộc danh sách PCD được AspectJ weaving trực tiếp hỗ trợ.

Trong một số hệ thống, kiểu/type + annotation có thể là hợp đồng ổn định hơn tên bean; đừng biến bean name thành quy tắc mặc định cho mọi aspect.

## 9. Kết hợp `&&`, `||` và `!` mà không mở rộng vô ý

Giả sử:

- `A` = method public trong module thanh toán.
- `B` = method có annotation `@AuditedOperation`.
- `C` = method có tên `pay`.

| Biểu thức | Tập hợp match |
| --- | --- |
| `A && B` | Chỉ method thỏa cả hai; thường **hẹp hơn** A hoặc B |
| `A && C` | Method public trong payment có tên phù hợp |
| `A || B` | Method thuộc A **hoặc** được đánh dấu B ở **bất cứ vùng nào**; có thể rộng bất ngờ |
| `A && !C` | Chọn tất cả method thuộc A trừ C; có thể rất rộng |
| `A && (B || C)` | Vẫn giới hạn trong A, rồi chọn method đánh dấu hoặc tên phù hợp |

Khi dùng dấu phủ định, nhớ rằng `!within(com.acme.internal..*)` chỉ loại bỏ vùng `internal`; nó **vẫn chứa toàn bộ ứng dụng ngoài vùng đó** nếu không kết hợp với một điều kiện allowlist tích cực.

Ví dụ dễ sai:

```java
@Before(
    "within(com.acme.payment..*)"
    + " || @annotation(com.acme.audit.AuditedOperation)"
)
```

Đọc chính xác: **tất cả method của payment module**, cộng **mọi method được đánh dấu annotation ở package khác**. Nếu mong muốn chỉ các method được đánh dấu **bên trong payment module**, phải dùng `&&`:

```java
@Before(
    "within(com.acme.payment..*)"
    + " && @annotation(com.acme.audit.AuditedOperation)"
)
```

Không tự đổi `&&` thành `||` chỉ để “bao phủ nhiều hơn”, đặc biệt với advice có side effects.

## 10. Kiểm thử cả trường hợp match và không match

Một pointcut chính xác phải được kiểm chứng bằng **positive cases** và **negative cases**.

### 10.1. Ma trận kiểm thử phạm vi

Đối với `NarrowAspect` ở mục 5:

| Trường hợp gọi qua Spring bean reference | Mong đợi chạy narrow advice? | Lý do |
| --- | --- | --- |
| `paymentService.pay()` | **Có** | Đúng class, method và bean name |
| `paymentService.status()` | **Không** | Khác method |
| `reportService.generate()` | **Không** | Khác class/package và bean name |
| Một bean `backupPaymentService` cùng class, nếu được đăng ký | **Không** | Không match `bean(paymentService)` |
| `new PaymentService().pay()` ngoài Spring | **Không** | Không có Spring AOP proxy |
| `this.pay()` nội bộ target | **Không** với lời gọi nội bộ đó | Self-invocation bỏ qua Spring proxy |

Không nên chỉ assert “advice đã chạy một lần” cho happy path. Một thay đổi pointcut có thể làm advice tiếp tục chạy ở case đúng **và** chạy thêm ở những case sai, khiến test cũ vẫn xanh.

### 10.2. Kiểm tra qua integration test với Spring

Có thể gắn một counter hoặc test sink vào advice thay cho `System.out.println`, rồi tạo Spring context và gọi các phương thức. Với broad/narrow demo:

1. Assert advice của narrow chạy **đúng một lần** khi gọi `payment.pay()`.
2. Assert counter **không tăng** khi gọi `payment.status()`.
3. Assert counter **không tăng** khi gọi `report.generate()`.
4. Nếu dùng `bean()`, tạo thêm một bean cùng kiểu khác tên và xác nhận không bị advice.
5. Nếu thay đổi phạm vi package, thêm một lớp thử nghiệm tương tự ở package láng giềng để kiểm tra tính cách ly.

Đếm log ở ví dụ là đủ để học cơ chế; dự án production nên viết **JUnit integration tests** và sử dụng dependency/test profile để xác minh không có side-effect ngoài phạm vi.

### 10.3. Kiểm tra pointcut bằng Spring API

Spring AOP có `org.springframework.aop.aspectj.AspectJExpressionPointcut` để phân tích một expression cụ thể:

```java
// Snippet minh họa; không phải chương trình độc lập.
AspectJExpressionPointcut pointcut = new AspectJExpressionPointcut();
pointcut.setExpression(
    "execution(public * example.service.payment.PaymentService.pay(..))"
);

boolean paymentClassCanMatch =
    AopUtils.canApply(pointcut, PaymentService.class);

boolean reportClassCanMatch =
    AopUtils.canApply(pointcut, ReportService.class);
```

Với chữ ký expression được chỉ ra, dự kiến kết quả lần lượt là `true` và `false`. Cần import `AspectJExpressionPointcut` và `AopUtils` cùng các model classes.

**Giới hạn:** `canApply` ở đây trả lời câu hỏi class có thể có method match hay không. Nó không xác nhận một proxy cụ thể đã cài advisor, không kiểm tra bean name nếu thiếu ngữ cảnh và không thay thế kiểm thử invocation runtime. Với pointcut dùng `bean()`, cần đánh giá trong Spring bean factory/context và các advisor thực sự đã được auto-proxy creator chọn.

## 11. Pointcut rộng còn gây thay đổi proxy type và tương tác framework

Một aspect rộng có thể tạo proxy cho những bean trước đây vốn là object gốc. Điều này có thể làm:

- Caller từng inject theo **concrete implementation type** gặp lỗi khi AOP chuyển sang JDK dynamic proxy.
- Những bean cấu hình `final` method không được can thiệp theo class-based proxy dù bean bị proxy.
- Các method gọi nội bộ qua `this` vẫn bỏ qua Spring AOP, khiến phạm vi tác động thực tế không đồng đều.
- Transaction/cache/security advisors cùng tham gia một proxy, làm thứ tự interceptor khó theo dõi hơn.
- `equals()`, `toString()`, introspection hoặc công cụ quan sát class runtime trở nên khác so với plain Java object.
- Một `@Around` advice có lỗi trong `proceed()`/return/exception flow ảnh hưởng những method hoàn toàn không thuộc nghiệp vụ ban đầu.

**Quan trọng:** Proxy được tạo không có nghĩa *tất cả* những hậu quả trên chắc chắn xuất hiện. Đó là các rủi ro cần kiểm chứng khi **mở rộng phạm vi AOP**. Cách phòng ngừa hiệu quả nhất là làm pointcut khớp đúng lớp/method/bean có mục đích rõ ràng.

## 12. Spring Boot: tự bật AOP không đồng nghĩa nên dùng pointcut rộng

Trong Spring Boot, khi AOP/AspectJ starter và auto-configuration được bật, hệ thống có thể tự bật hỗ trợ `@AspectJ` proxies mà không cần bạn viết `@EnableAspectJAutoProxy`. Nhưng cách Spring chọn các bean/method chịu advice **vẫn phụ thuộc pointcut**.

- **Spring Boot 3.x:** thông thường dùng `spring-boot-starter-aop`.
- **Spring Boot 4.x:** starter tương ứng được đổi tên thành `spring-boot-starter-aspectj`.
- Một lớp `@Aspect` phải được đăng ký làm Spring bean (thường `@Component` hoặc `@Bean`).
- `spring.aop.proxy-target-class` ảnh hưởng chiến lược JDK/CGLIB, **không tự thu hẹp pointcut**.
- Một aspect dùng `execution(* *(..))` có thể match nhiều method khi chúng thỏa quy tắc Spring AOP, kể cả nếu trước đó project chưa có AOP proxy cho những bean ấy.

Đặc biệt không sao chép pointcut demo quá rộng từ dự án Spring Framework nhỏ sang toàn bộ Spring Boot application có nhiều service/infrastructure beans.

## 13. Phòng tránh lỗi khi nâng cấp hoặc mở rộng ứng dụng

### 13.1. Thêm class/method mới

Pattern dựa trên tên như `*Service` hoặc `save*` có thể tự động bao phủ những class/method mới dù team viết chúng không biết đến aspect. Review các biểu thức pointcut như review **public API boundary**; mỗi lần thêm module/package mới nên xem lại các pointcut shared.

### 13.2. Đổi package hoặc tên bean

Pointcut quá cụ thể về tên class/bean có thể mất hiệu lực sau refactor. Để cân bằng an toàn và khả năng bảo trì:

- Dùng named pointcuts gắn với **ngữ nghĩa module** thay vì lặp chuỗi rất dài.
- Dùng annotation opt-in khi method cần advice không có mô hình tên/package ổn định.
- Nếu dùng bean name, đặt tên tường minh và bảo vệ bằng integration test.
- Không chuyển ngay sang `execution(* *(..))` chỉ để test “đỡ thất bại” sau refactor.

### 13.3. Advice có side effects

Các advice audit, retry, transaction hoặc security cần chú ý hơn vì việc match nhầm có thể ảnh hưởng đúng/sai nghiệp vụ. Có thể dùng cả hai lớp bảo vệ:

1. Pointcut **giới hạn cứng** vào module/type/method.
2. Logic advice **không log secrets** và thực hiện hành vi an toàn khi gặp đối số ngoài dự kiến.

Nhưng guard điều kiện nằm bên trong advice **không thay thế** pointcut hẹp: proxy/advisor vẫn có thể can thiệp những bean/method không cần thiết.

### 13.4. Runtime arguments và performance

Pointcut dựa trên `args(...)` hoặc điều kiện phụ thuộc runtime có thể cần đánh giá theo từng invocation. Chọn biểu thức theo ngữ nghĩa chứ không chỉ tối ưu hiệu năng. Spring hỗ trợ `ClassFilter`, `MethodMatcher` và kiểm tra static/dynamic; **narrow scoping** có thể giúp giảm số ứng viên cần kiểm tra. Đừng đoán chi phí từ độ dài biểu thức, hãy đo hiệu năng ở ứng dụng thật nếu advice nằm trên hot path.

## 14. Checklist thiết kế pointcut

Trước khi merge một Spring Aspect, hãy trả lời:

1. **Ý định cụ thể:** advice nhằm tác động vào thao tác nghiệp vụ nào?
2. **Allowlist:** package, type, method hoặc annotation nào định nghĩa đúng phạm vi?
3. **Không được tác động:** bean/package/method nào tuyệt đối không nên bị match?
4. **Thay đổi tương lai:** thêm lớp `*Service` hoặc chuyển package có gây match bất ngờ không?
5. **Proxy boundary:** caller có gọi qua Spring proxy không, method có proxy được không?
6. **Bean name:** tên có ổn định nếu pointcut dùng `bean(...)` không?
7. **Hành vi advice:** có log bí mật, retry, đổi return value, suppress exception hoặc transaction side effects không?
8. **Test:** có positive **và** negative integration tests không?
9. **Framework:** transaction/cache/async advisors có thể khiến bean vẫn là proxy khi custom aspect không match không?
10. **Bảo trì:** named pointcut, chú thích ý định và test có giúp người khác hiểu biểu thức không?

Chỉ khi danh sách trên rõ ràng mới nên tăng phạm vi. “Chạy được” khác với “chỉ chạy ở đúng nơi”.

## 15. Bài tập

**Tình huống A.** Yêu cầu audit chỉ cho `PaymentService.pay()`. Aspect dùng `execution(public * example.service..*Service.*(..))`. Một `ReportService.generate()` mới được tạo ở package `example.service.report`. Advice có thể chạy không?

**Đáp án:** Có. Type name `ReportService` và public method `generate()` đáp ứng pattern rộng, mặc dù không thuộc thanh toán. Thu hẹp class/method hoặc kết hợp scope khác.

**Tình huống B.** Pointcut `within(example.service.payment..*)` có chắc chắn chỉ match `pay()` không?

**Đáp án:** Không. Nó chọn method executions trong các types thuộc package đó, bao gồm các method khác. Cần thêm điều kiện theo method hoặc annotation.

**Tình huống C.** Có expression `A || B`, trong đó A chọn service thanh toán và B chọn mọi method có annotation audit trên toàn ứng dụng. Nó có thể chọn method ngoài payment không?

**Đáp án:** Có. Một method ở package khác vẫn có thể thỏa B. Để buộc cùng phạm vi payment, dùng `A && B` nếu đúng ý định.

**Tình huống D.** Narrow pointcut được cấu hình đúng. `paymentService` là AOP proxy nhưng gọi `status()` không in log audit. Có mâu thuẫn không?

**Đáp án:** Không. Proxy tồn tại ở cấp bean vì ít nhất một method có advisor; advice dành cho `pay()` không match `status()`.

**Tình huống E.** Pointcut chỉ dùng `bean(paymentService)` để ghi log mọi method. Có vấn đề gì?

**Đáp án:** Nó hạn chế theo bean, nhưng **không** hạn chế method. Nếu chỉ cần `pay()` thì còn quá rộng; thêm `execution(...)` hoặc annotation hợp lệ.

**Tình huống F.** Sau refactor đổi tên bean `paymentService` thành `primaryPaymentService`, advice không chạy. Có nên sửa thành match tất cả service beans không?

**Đáp án:** Không. Cập nhật đúng hợp đồng bean name hoặc chuyển sang annotation/type rõ ràng và bổ sung test. Mở rộng không kiểm soát sẽ tạo rủi ro can thiệp bean ngoài ý muốn.

## 16. Nguồn tham khảo Spring chính thức

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): các PCD Spring AOP hỗ trợ, `bean()`, cách kết hợp named pointcuts và khuyến nghị viết pointcut hẹp.
- [Spring Framework — Spring Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `ClassFilter`, `MethodMatcher`, static/dynamic matching.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy boundaries, JDK/CGLIB, self-invocation.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): bật Spring AOP và yêu cầu aspect bean.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): advice kết hợp pointcut và cách khai báo `@Before`, `@Around`.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): auto-configuration AOP và proxy strategy trong Spring Boot.
