# Cấu hình order trong XML và khác biệt thứ tự khai báo với @Aspect trong Spring AOP

## 1. Bài toán: nhiều advice cùng áp dụng cho một Spring bean

Khi Spring bean có nhiều XML hoặc annotation advice cùng match, kết quả quan sát phụ thuộc **precedence của advisor chain**. Có ba phạm vi khác nhau: (1) `order` giữa các aspect/advisor, (2) **thứ tự phần tử advice trong cùng XML `<aop:aspect>`**, và (3) quy tắc annotation advice trong cùng class `@Aspect`. Bài này tập trung **so sánh ba phạm vi bằng cùng một lời gọi**, vì vị trí code/bean definition không thể thay cho hợp đồng ordering.

Ví dụ hai around advice lồng nhau: aspect precedence cao vào trước, rồi thoát sau. Nếu đặt audit bên ngoài metrics thì trace là `AUDIT enter → METRICS enter → target → METRICS exit → AUDIT exit`.

## 2. `order`: số nhỏ hơn có precedence cao hơn

`order` số **nhỏ hơn** có precedence **cao hơn**. Ví dụ:

~~~xml
<aop:aspect ref="auditBean" order="1">
    <aop:around method="around" pointcut-ref="payment"/>
</aop:aspect>
<aop:aspect ref="metricsBean" order="2">
    <aop:around method="around" pointcut-ref="payment"/>
</aop:aspect>
~~~

Đây là fragment cần hai bean và pointcut đã khai báo. Nếu cả hai gọi `proceed()`, audit bọc metrics, nên log:

~~~text
AUDIT enter
METRICS enter
PAY
METRICS exit
AUDIT exit
~~~

Số nhỏ hơn không có nghĩa log luôn xuất hiện trước khi đi ra: outer aspect được gọi **sau cùng** trên đường unwind. Nếu hai aspects không được đặt precedence tường minh, đừng dựa vào thứ tự các dòng XML hoặc thứ tự bean được tạo.

## 3. XML: `<aop:aspect order="...">` điều khiển precedence giữa aspect

Spring hỗ trợ namespace `aop`; cấu hình hợp lệ cần namespace/schema và bean chứa logic advice:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="billingService" class="demo.BillingService"/>
    <bean id="auditBean" class="demo.XmlAuditAspect"/>
    <bean id="metricsBean" class="demo.XmlMetricsAspect"/>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="payment"
                      expression="execution(* demo.BillingService.pay(..))"/>

        <aop:aspect id="audit" ref="auditBean" order="1">
            <aop:around method="around" pointcut-ref="payment"/>
        </aop:aspect>

        <aop:aspect id="metrics" ref="metricsBean" order="2">
            <aop:around method="around" pointcut-ref="payment"/>
        </aop:aspect>
    </aop:config>
</beans>
```

Trong `<aop:config>`, khai báo **pointcut trước, advisor sau, aspect cuối** nếu đồng thời có cả ba loại phần tử. `ref` trong `<aop:aspect>` tham chiếu bean Java thông thường: class chứa method `around` **không cần** `@Aspect` vì pointcut/advice đã được mô tả ở XML.

Các điểm cần phân biệt:

- `order` trên `<aop:aspect>` dành cho precedence **giữa các aspect**. Nó không tự sắp lại vị trí các method trong class backing bean.
- Có thể dùng `@Order` hoặc triển khai `org.springframework.core.Ordered` trên bean backing aspect theo quy tắc Spring; nếu đã chọn cấu hình XML minh bạch, đặt `order` ngay trên `<aop:aspect>` thường dễ kiểm tra hơn.
- Cấu hình `proxy-target-class="true"` lựa chọn proxy dựa trên subclass trong ví dụ; nó **không** biến Spring AOP thành AspectJ weaving.
- Nếu dùng `<aop:advisor>` độc lập, chính phần tử advisor cũng có thuộc tính `order` riêng, ví dụ `<aop:advisor advice-ref="guardAdvice" pointcut-ref="payment" order="0"/>`. `guardAdvice` phải là bean advice thích hợp, chẳng hạn implement `org.aopalliance.intercept.MethodInterceptor`. Đây là ví dụ minh họa thuộc tính, chưa phải một advisor chạy độc lập.
- Khi có các advisor khác của Spring như transaction/security, phải xét order của **các advisor đó**. Không thể suy ra toàn bộ thứ tự hệ thống chỉ từ một `<aop:aspect order="...">`.

## 4. Điểm khác biệt cốt lõi: **thứ tự khai báo advice trong cùng XML aspect**

Theo tài liệu Spring AOP schema, khi **hai advice cùng nằm trong một** `<aop:aspect>` và cùng khớp join point, **thứ tự khai báo phần tử advice từ trên xuống dưới thể hiện precedence từ cao đến thấp**.

Ví dụ minh họa, với backing bean có method `around` và `check` phù hợp:

```xml
<aop:aspect id="validationAndAudit" ref="validationAuditBean" order="3">
    <aop:around method="around" pointcut-ref="payment"/>
    <aop:before method="check" pointcut-ref="payment"/>
</aop:aspect>
```

Ở đây `around` được khai báo **trước** `before` nên có precedence cao hơn và bao phía ngoài khi chuỗi advice được thực thi. Đổi thứ tự hai dòng làm thay đổi precedence của chúng trong nhóm XML aspect này.

Cần phân biệt hai kiểu thay đổi:

| Thao tác | Tác động mong đợi |
|---|---|
| Đổi `order="1"` thành `order="5"` của một `<aop:aspect>` | Thay mức ưu tiên của **aspect đó so với các aspect/advisor khác** |
| Đổi vị trí `<aop:around>` với `<aop:before>` **trong cùng** `<aop:aspect>` | Thay precedence **nội bộ** của các advice XML cùng aspect |
| Đổi vị trí hai `<aop:aspect>` khác nhau nhưng giữ `order` là 1 và 2 | Không đảo precedence được xác định bởi hai giá trị `order` |
| Đảo vị trí method `@Before` trong Java class `@Aspect` | Không xác lập thứ tự chạy được bảo đảm |

**Không suy diễn** “XML luôn chạy đúng trật tự mọi phần tử trong cả file”. Quy tắc thứ tự khai báo ở đây áp dụng cho **các advice cùng một `<aop:aspect>`**, còn precedence giữa aspect cần `order`.

Nếu một XML aspect có nhiều advice cùng khớp điểm cắt, nên giữ thứ tự rõ, tránh viết các advice phụ thuộc side effect lẫn nhau. Khi khó diễn đạt thứ tự, tách thành các aspect có `order` hoặc gộp logic cần tuần tự vào một `around` advice có thứ tự gọi minh bạch.

## 5. So với `@Aspect`: `@Order` chỉ cho cấp aspect

Trong cấu hình annotation, các class được Spring quản lý dùng `@Aspect` và `@Order`:

```java
@Aspect
@Order(1)
public class AnnotationAuditAspect {
    @Around("execution(* demo.BillingService.pay(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("AUDIT enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AUDIT exit");
        }
    }
}
```

Và aspect thứ hai:

```java
@Aspect
@Order(2)
public class AnnotationMetricsAspect {
    @Around("execution(* demo.BillingService.pay(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("METRICS enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("METRICS exit");
        }
    }
}
```

Cả hai đoạn chỉ hiển thị thân class (cần các import `@Aspect`, `@Order`, `@Around` và `ProceedingJoinPoint`); phiên bản **tệp đầy đủ** nằm ở ví dụ chạy được bên dưới.

`@Order(1)` và `@Order(2)` tạo chuỗi bao lời gọi **tương tự XML**. Nhưng nếu một class `@Aspect` có nhiều advice:

- Spring áp dụng thứ tự precedence theo **loại advice** trong cùng aspect: `@Around`, `@Before`, `@After`, `@AfterReturning`, `@AfterThrowing` từ cao đến thấp theo quy tắc Spring. Riêng `@After` có hành vi finally nên trên thực tế chạy sau `@AfterReturning` hoặc `@AfterThrowing` tương ứng.
- Khi nhiều advice **cùng loại** (ví dụ hai method đều mang `@Before`) trong cùng class `@Aspect` cùng khớp join point, **thứ tự giữa chúng không được xác định**. Java reflection không bảo đảm giữ thứ tự khai báo method của mã nguồn.
- `@Order` trên **class aspect** không chọn thứ tự của hai method `@Before` **trong cùng class**. Đổi thứ tự viết hai method trong mã nguồn cũng không khắc phục được.
- Nếu thứ tự giữa hai advice cùng loại là yêu cầu nghiệp vụ, hãy gộp chúng thành một advice có thứ tự gọi rõ ràng, hoặc tách thành hai class `@Aspect` và chỉ định `@Order` cho từng class.

Ví dụ **không nên phụ thuộc vào thứ tự khai báo**:

```java
@Aspect
@Order(1)
public class AmbiguousBeforeAspect {
    @Before("execution(* demo.BillingService.pay(..))")
    public void validate() {
        System.out.println("validate");
    }

    @Before("execution(* demo.BillingService.pay(..))")
    public void audit() {
        System.out.println("audit");
    }
}
```

Đoạn này chỉ minh họa bẫy về thứ tự; không thuộc hai file aspect trong ví dụ chạy bên dưới. **Không kết luận chắc chắn** stdout phải là `validate` rồi `audit`. Đây là khác biệt quan trọng so với thứ tự phần tử advice trong **cùng** `<aop:aspect>` của XML.

## 6. Ví dụ chạy được: hai cấu hình, cùng một thứ tự ưu tiên

Ví dụ **Java 17+, Spring Framework 6.2.x, Gradle** dưới đây có hai chế độ chạy độc lập:

- `xml`: đăng ký hai aspect qua `<aop:config>` và `<aop:aspect order>`.
- `annotation`: đăng ký hai class `@Aspect` bằng `@EnableAspectJAutoProxy` và `@Order`.

Chúng sử dụng **cùng** `BillingService` nhưng tạo **hai ApplicationContext khác nhau** để so sánh công bằng, tránh đăng ký cùng advice hai lần. Spring AOP vẫn thực thi qua proxy trong cả hai chế độ.

Cấu trúc dự án:

```text
spring-aop-order-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── Main.java
    │   ├── BillingService.java
    │   ├── XmlAuditAspect.java
    │   ├── XmlMetricsAspect.java
    │   ├── AnnotationAuditAspect.java
    │   ├── AnnotationMetricsAspect.java
    │   └── AnnotationConfig.java
    └── resources/aop.xml
```

### 6.1. Gradle và service

**`settings.gradle`**

```groovy
rootProject.name = 'spring-aop-order-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.13'
    implementation 'org.springframework:spring-aop:6.2.13'
    implementation 'org.aspectj:aspectjweaver:1.9.24'
}

application {
    mainClass = 'demo.Main'
}
```

`spring-context` cung cấp container, `spring-aop` cung cấp proxy AOP, còn `aspectjweaver` cung cấp phần cần thiết để Spring phân tích AspectJ pointcut/annotation aspect. Việc có `aspectjweaver` trên classpath **không có nghĩa** ví dụ này kích hoạt load-time weaving: cả hai chế độ đều cấu hình **Spring AOP proxy**.

**`src/main/java/demo/BillingService.java`**

```java
package demo;

public class BillingService {
    public void pay() {
        System.out.println("PAY");
    }
}
```

### 6.2. Backing bean cho XML aspect

**`src/main/java/demo/XmlAuditAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;

public class XmlAuditAspect {
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("AUDIT enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AUDIT exit");
        }
    }
}
```

**`src/main/java/demo/XmlMetricsAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;

public class XmlMetricsAspect {
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("METRICS enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("METRICS exit");
        }
    }
}
```

Các class này không có `@Aspect`. XML cung cấp pointcut, phương thức advice và order.

**`src/main/resources/aop.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="billingService" class="demo.BillingService"/>
    <bean id="auditBean" class="demo.XmlAuditAspect"/>
    <bean id="metricsBean" class="demo.XmlMetricsAspect"/>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="payment"
                      expression="execution(* demo.BillingService.pay(..))"/>

        <aop:aspect id="audit" ref="auditBean" order="1">
            <aop:around method="around" pointcut-ref="payment"/>
        </aop:aspect>

        <aop:aspect id="metrics" ref="metricsBean" order="2">
            <aop:around method="around" pointcut-ref="payment"/>
        </aop:aspect>
    </aop:config>
</beans>
```

### 6.3. Hai annotation aspect tương đương

**`src/main/java/demo/AnnotationAuditAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(1)
public class AnnotationAuditAspect {
    @Around("execution(* demo.BillingService.pay(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("AUDIT enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AUDIT exit");
        }
    }
}
```

**`src/main/java/demo/AnnotationMetricsAspect.java`**

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(2)
public class AnnotationMetricsAspect {
    @Around("execution(* demo.BillingService.pay(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("METRICS enter");
        try {
            return pjp.proceed();
        } finally {
            System.out.println("METRICS exit");
        }
    }
}
```

**`src/main/java/demo/AnnotationConfig.java`**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AnnotationConfig {
    @Bean
    public BillingService billingService() {
        return new BillingService();
    }

    @Bean
    public AnnotationAuditAspect annotationAuditAspect() {
        return new AnnotationAuditAspect();
    }

    @Bean
    public AnnotationMetricsAspect annotationMetricsAspect() {
        return new AnnotationMetricsAspect();
    }
}
```

`@EnableAspectJAutoProxy` bật Spring AOP cho context annotation này; `@Bean` giúp aspect trở thành Spring-managed bean. Chỉ khai báo `@Aspect` trên class tự nó không đăng ký bean với container.

### 6.4. Chọn chế độ chạy

**`src/main/java/demo/Main.java`**

```java
package demo;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Main {
    public static void main(String[] args) {
        String mode = args.length == 0 ? "xml" : args[0];
        if (!mode.equals("xml") && !mode.equals("annotation")) {
            throw new IllegalArgumentException(
                    "mode must be xml or annotation");
        }

        ConfigurableApplicationContext context =
                mode.equals("xml")
                        ? new ClassPathXmlApplicationContext("aop.xml")
                        : new AnnotationConfigApplicationContext(
                                AnnotationConfig.class);

        try (context) {
            context.getBean(BillingService.class).pay();
        }
    }
}
```

Chạy bằng Gradle Wrapper hiện có trong dự án:

```bash
./gradlew run --args=xml
./gradlew run --args=annotation
```

Trên Windows, thay `./gradlew` bằng `.\gradlew.bat`. Nếu khởi tạo thư mục mới chưa có wrapper, cần tạo `gradlew`/`gradlew.bat` bằng bản Gradle tương thích hoặc dùng lệnh `gradle run --args=xml` và `gradle run --args=annotation` khi Gradle đã được cài.

**Cả hai chế độ in cùng những dòng ứng dụng sau, đúng thứ tự:**

```text
AUDIT enter
METRICS enter
PAY
METRICS exit
AUDIT exit
```

Gradle có thể in thêm thông tin task/build bên ngoài phần stdout trên. Đổi `order` giữa XML `audit`/`metrics` từ 1/2 thành 2/1 (hoặc đổi `@Order` tương ứng trong chế độ annotation), sẽ đổi aspect bên ngoài; expected stdout khi đó là:

```text
METRICS enter
AUDIT enter
PAY
AUDIT exit
METRICS exit
```

Đây là phép kiểm chứng hữu ích: **order quyết định lớp bao ngoài**, trong khi thứ tự log trên đường về đảo lại theo tính chất của `around` advice.

## 7. Quy tắc thực tế khi phối hợp XML, annotation và advisor

Khi pha trộn XML với `@Aspect`, transaction hoặc advisor do framework tạo, xác định **đủ các advisor đang áp dụng** trước khi lý giải thứ tự. Cùng giá trị order không tạo contract ổn định; `@Order` của một aspect không sắp xếp hai advice cùng loại bên trong chính class đó. Đổi thứ tự tạo bean hoặc vị trí các element `<aop:aspect>` khác nhau cũng không thay giá trị precedence đã khai báo.

Nếu retry, transaction và audit có thứ tự khác nhau, ranh giới commit, số lần target chạy và event audit có thể khác; dùng integration test trên Spring proxy thật. Trong giai đoạn migration, giữ nguyên tập advisors dự kiến và kiểm tra event trace trước/sau; bài **“Kết hợp XML với Java configuration mà không tạo hành vi trùng lặp”** phân tích nguồn duplicated registrations.

## 8. Checklist kiểm tra thứ tự advice trong ứng dụng Spring

1. Advice cần so sánh có thực sự cùng khớp một method execution đi qua Spring proxy không?
2. Chúng thuộc **hai aspect khác nhau** hay **cùng một XML `<aop:aspect>`** hay **cùng class `@Aspect`**?
3. Nếu khác aspect, đã đặt giá trị `order`/`@Order`/`Ordered` **khác nhau, tường minh** chưa?
4. Nếu cùng XML aspect, đã kiểm tra **thứ tự khai báo phần tử advice** và loại advice chưa?
5. Nếu cùng class `@Aspect`, có đang vô tình dựa vào thứ tự source code của hai advice cùng loại không?
6. Nếu có `@Around`, đang xét log vào hay log ra? `proceed()` và `finally` có làm chiều quan sát đảo lại không?
7. Có `<aop:advisor>`, transaction advisor hoặc security advisor cùng áp dụng mà chưa xem order riêng không?
8. Có đăng ký trùng aspect qua XML, `@Bean` hoặc component scan không?
9. Đã kiểm thử thứ tự bằng stdout hoặc test tích hợp gọi **qua proxy** thay vì gọi trực tiếp một đối tượng `new` chưa?

## 9. Ghi nhớ và tài liệu Spring

| Cấp cấu hình | Cách kiểm soát precedence | Có dựa được vào thứ tự dòng khai báo? |
|---|---|---|
| Hai `<aop:aspect>` XML | Thuộc tính `order` trên từng aspect (hoặc cơ chế ordering của backing bean) | Không dùng dòng XML thay cho `order` |
| Hai advice **trong cùng** `<aop:aspect>` | Thứ tự phần tử advice từ trên xuống dưới và semantics từng loại advice | **Có**, đây là quy tắc riêng của Spring XML schema AOP |
| Hai class `@Aspect` | `@Order` trên aspect hoặc `Ordered` | Không dựa vào vị trí class hoặc method trong source |
| Nhiều method advice **trong cùng** `@Aspect` | Quy tắc loại advice; cùng loại có thể không xác định | **Không**; đổi vị trí hai method cùng loại không tạo contract |
| `<aop:advisor>` | Thuộc tính `order` của advisor | Không dựa vào vị trí dòng XML khi không xác định precedence |

Tài liệu tham khảo của Spring Framework:

- [Schema-based AOP Support – Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/schema.html#advice-ordering)
- [Declaring Advice – Advice Ordering for @Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html#advice-ordering)

**Kết luận về cấu hình Spring Aspect:** dùng `order`/`@Order` để quy định precedence **giữa các aspect**. Trong **cùng XML `<aop:aspect>`**, thứ tự phần tử advice có ý nghĩa; trong **cùng Java `@Aspect`**, không dùng thứ tự viết method để ép hai advice cùng loại chạy theo ý muốn.