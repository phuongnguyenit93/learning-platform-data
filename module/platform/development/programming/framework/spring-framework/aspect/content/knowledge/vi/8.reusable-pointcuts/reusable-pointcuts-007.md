# Loại trừ bean hạ tầng, aspect và mã ghi nhận dùng chung trong Spring AOP

## 1. Mục tiêu

Một `@Aspect` trong Spring thường xử lý chức năng cắt ngang như audit, ghi log, đo thời gian hoặc theo dõi lời gọi của **Spring service beans**. Nếu pointcut quá rộng, advice không chỉ chạy trên nghiệp vụ mà còn có thể chạy trên **recorder, adapter hạ tầng, logger, metrics collector** – chính những bean mà advice phải gọi đến.

Hãy xét một advice được Spring dùng để ghi nhận mỗi lời gọi:

~~~text
Client -> OrderService proxy
              |
              +-> @Before advice
                       |
                       +-> AuditRecorder.record()
                                    |
                                    +-> Nếu recorder cũng bị advise
                                           |
                                           +-> @Before advice
                                                  |
                                                  +-> AuditRecorder.record()
                                                           |
                                                           +-> ...
~~~

Nếu recorder được gọi **qua Spring AOP proxy** và cũng khớp chính advisor đó, advice có thể tái nhập không kiểm soát và dẫn tới vòng lặp hoặc `StackOverflowError`. Những cấu hình có dependency ngược giữa aspect, recorder và service còn có thể gây lỗi khi khởi tạo container.

Bài học tập trung vào **tổ chức pointcut trong Spring Framework** để loại bỏ đúng các bean kỹ thuật. Sau khi hoàn thành, bạn sẽ:

- Phân biệt chính xác **business bean**, **infrastructure bean**, **aspect bean** và **shared recorder bean**.
- Biết Spring AOP **tự loại class `@Aspect` khỏi auto-proxying với vai trò target**, nhưng **không tự loại mọi collaborator** mà aspect inject vào.
- Xây dựng **allowlist** nghiệp vụ và các biểu thức phủ định bằng `within`, `bean`, `execution`.
- Ghép và chia sẻ `@Pointcut` có tên với `&&`, `||`, `!`.
- Viết ví dụ Spring Framework thuần, **Java 17+**, có output kiểm chứng service được proxy trong khi recorder, inspector và aspect không bị proxy bởi concern này.
- Nhận diện giới hạn của loại trừ theo tên bean, package, class, annotation và những advisor khác.

**Phạm vi:** Chỉ nói về **Spring AOP dựa trên proxy**, không chuyển sang AspectJ weaving hoặc trình bày lại AOP tổng quát.

## 2. Bốn loại bean và trách nhiệm của pointcut

| Loại | Ví dụ | Hành vi mong muốn với business audit |
| --- | --- | --- |
| Spring bean nghiệp vụ | `OrderService`, `InvoiceService` | Được advice khi method thuộc phạm vi audit |
| Bean hạ tầng ứng dụng | `HealthInspector`, `CacheSupport` | Thường được loại, trừ khi cần quan sát hạ tầng |
| Bean `@Aspect` | `LoggingAspect` | Spring AOP không dùng nó làm target để aspect khác advice |
| Bean ghi nhận dùng chung | `AuditRecorder`, `MetricsSink` | Nên loại khỏi chính advisor đang gọi nó |

**Chú ý:** `AuditRecorder` là một Spring bean bình thường. Chỉ vì nó có tên “recorder” hoặc được inject vào `LoggingAspect` **không có nghĩa Spring tự động loại nó khỏi mọi advisor**. Nếu `AuditRecorder.record()` khớp pointcut, recorder có khả năng được bọc proxy.

Ngược lại, theo tài liệu chính thức về **Declaring an Aspect**, class đánh dấu `@Aspect` được Spring AOP nhận diện là một aspect và **loại khỏi auto-proxying với vai trò target**. Điều này không xóa advice của aspect; Spring vẫn lấy advice từ aspect bean để áp dụng lên những business beans phù hợp.

Với bean hạ tầng **do ứng dụng định nghĩa**, đừng dựa vào giả định tất cả bean có annotation `@Component`, `@Configuration` hay tên kết thúc `Manager` đều được framework miễn advice. Một số loại Spring infrastructure nội bộ được tạo/xử lý ở giai đoạn đặc biệt, nhưng chúng không thay thế chính sách loại trừ pointcut của ứng dụng.

## 3. Hai cách tiếp cận: chọn đúng từ đầu hay phủ định sau

### 3.1. Pointcut quá rộng

~~~java
@Before("execution(public * demo..*.*(..))")
public void beforeAnyPublicMethod(JoinPoint jp) {
    recorder.record(jp.getSignature().getName());
}
~~~

Đây là **fragment minh họa nguy cơ**, không phải file Java chạy độc lập. Expression có thể bao phủ nhiều public method của các bean trong namespace `demo`: business service, recorder, helper, kiểm tra health và cấu hình ứng dụng. Nếu recorder cũng được Spring tạo proxy do advisor này, lời gọi `record` từ advice có thể kích hoạt chính advice đó.

Không thử expression nguy hiểm này trong production để “xem có vòng lặp không”. Nên đánh giá bằng test tách biệt, hoặc sửa pointcut theo phương án phía dưới.

### 3.2. Allowlist: chỉ chọn nghiệp vụ

~~~java
@Pointcut("execution(public * demo.business..*.*(..))")
public void businessMethods() {
}
~~~

Một allowlist như trên chọn những public method có type pattern thuộc `demo.business` và các package con. Các bean `demo.shared.AuditRecorder` và `demo.infra.HealthInspector` **không thuộc phạm vi chọn ngay từ đầu**.

Ưu điểm:

1. Khi ứng dụng bổ sung recorder mới ngoài `demo.business`, không cần cập nhật mọi danh sách loại trừ.
2. Nhìn biểu thức là hiểu **loại code được giám sát**.
3. Có thể tái sử dụng điều kiện cho logging, metrics, audit nếu các concern cần phạm vi giống nhau.
4. Có thể viết test khẳng định **business methods được advice**, và **technical methods không được advice**.

Nhược điểm: tổ chức package là một phần của hợp đồng kiến trúc. Nếu bean kỹ thuật bị đặt sai trong `demo.business`, nó vẫn có thể bị chọn; nếu service nghiệp vụ chuyển sang package khác, nó có thể bị bỏ qua. Bởi vậy vẫn phải có test.

### 3.3. Denylist: khi module cũ khó tách package

Khi chưa refactor được package, có thể dùng:

~~~java
@Pointcut(
    "execution(public * demo..*.*(..)) && " +
    "!within(demo.infra..*) && " +
    "!within(demo.shared..*) && " +
    "!within(demo.aop..*)"
)
public void applicationExceptTechnical() {
}
~~~

Điều kiện bắt đầu từ phạm vi rộng, rồi loại các type thuộc package kỹ thuật. Nó có ích khi muốn tiến từng bước, nhưng **nguy cơ bỏ sót technical package mới** lớn hơn so với allowlist nghiệp vụ.

## 4. Loại theo type/package: !within(...)

Spring hỗ trợ pointcut designator `within(...)` để hạn chế phạm vi type chứa method execution. Toán tử `!` đảo điều kiện.

Ví dụ:

~~~text
execution(public * demo..*.*(..))
&& !within(demo.shared..*)
&& !within(demo.infra..*)
~~~

Cách hiểu:

- `execution(public * demo..*.*(..))`: lọc public method signatures trong type pattern thuộc `demo` và subpackages.
- `!within(demo.shared..*)`: loại method execution thuộc những type ở `demo.shared` và package con.
- `!within(demo.infra..*)`: loại nhóm ứng dụng hạ tầng.

Có thể loại một class đơn lẻ:

~~~text
!within(demo.shared.AuditRecorder)
~~~

Nhưng nếu sau đó thêm `MetricRecorder` hoặc `TraceWriter`, phải cập nhật chính sách. Lọc theo cả package thường dễ quản lý hơn trong module được tổ chức tốt.

Một số hierarchy phức tạp (method ở interface, implementation ở package khác, inheritance/bridge method) khiến **declaring type** và method mà proxy kiểm tra không hoàn toàn hiển nhiên. Nếu yêu cầu loại đối tượng theo **runtime target type**, có thể cân nhắc `target(demo.shared.SomeType)` dưới dạng điều kiện, rồi kiểm thử trên bean/proxy thực tế.

Không có điều kiện phủ định package nào vượt qua giới hạn cơ bản: Spring AOP chỉ intercept **những lời gọi qua Spring proxy** và chỉ trên các method hợp lệ theo JDK/CGLIB.

## 5. Loại theo bean name: !bean(...)

`bean(...)` là designator **riêng Spring AOP**, match theo tên bean trong Spring container. Nó hỗ trợ tên cụ thể và wildcard `*` trong bean name.

~~~text
!bean(auditRecorder)
!bean(*Recorder)
!bean(healthInspector)
~~~

Có thể ghép:

~~~text
execution(public * demo..*.*(..))
&& !bean(*Recorder)
&& !bean(healthInspector)
~~~

Khác biệt với `within`:

| Điều kiện | Quyết định theo | Điểm mạnh | Rủi ro |
| --- | --- | --- | --- |
| `!within(demo.shared..*)` | Type/package của method execution | Bảo vệ cả nhóm class kỹ thuật | Phụ thuộc cấu trúc package |
| `!within(demo.shared.AuditRecorder)` | Type cụ thể | Chính xác theo class | Quên loại recorder khác |
| `!bean(auditRecorder)` | Tên Spring bean | Chọn/loại một registration cụ thể | Rename bean làm thay đổi match |
| `!bean(*Recorder)` | Convention tên Spring bean | Loại nhiều recorder cùng quy ước | Không loại bean có tên `auditSink` |

`bean` hoạt động ở mức **Spring bean name**, không phải Java method name, và **không phải** một phần của cú pháp `execution`. Native AspectJ weaving không có Spring bean factory để match designator này; tránh mang nguyên expression này sang weaving mode.

Kiểm tra tên bean thực tế khi dùng `@Component("...")`, `@Bean(name = "...")`, alias và cơ chế đặt tên tùy chỉnh. Không được suy ra bean name chỉ từ class name trong mọi cấu hình.

## 6. Loại bằng annotation và contract nghiệp vụ

Một chiến lược khác là **opt-in**: chỉ advice các method có annotation chủ đích.

~~~text
@annotation(demo.audit.AuditedOperation)
~~~

Trong đó `demo.audit.AuditedOperation` là custom annotation do ứng dụng tạo, với retention runtime và target METHOD. Ví dụ định nghĩa:

~~~java
package demo.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AuditedOperation {
}
~~~

Một service đánh dấu:

~~~java
@AuditedOperation
public void submit(String id) {
    // Phương thức nghiệp vụ cần audit
}
~~~

Đoạn submit là **fragment method**, cần class và import thích hợp; chưa phải file Java độc lập. Spring AOP có thể dùng `@annotation` để chọn method được đánh dấu.

Nếu annotation nằm trên interface thay vì implementation, hoặc có proxy/inheritance phức tạp, cần integration test cách Spring resolve annotation metadata. Không suy luận chỉ vì interface có annotation là mọi kiểu proxy sẽ có cùng kết quả.

Lựa chọn `@within` có thể ràng buộc annotation trên type. Cân nhắc kỹ vì nó khác `@annotation` trên method. Với các application infrastructure classes, việc thiếu annotation nghiệp vụ cũng là một dạng allowlist tự nhiên.

## 7. Named @Pointcut: đóng gói các điều kiện thay vì sao chép

Spring hỗ trợ toán tử:

| Toán tử | Ý nghĩa |
| --- | --- |
| `&&` | Giao: mọi điều kiện đúng |
| `||` | Hợp: ít nhất một điều kiện đúng |
| `!` | Phủ định điều kiện |
| `(...)` | Nhóm điều kiện khi cần |

Có thể viết:

~~~java
@Pointcut("execution(public * demo..*.*(..))")
public void publicApplicationMethod() {
}

@Pointcut(
    "!within(demo.shared..*) && !within(demo.infra..*)"
)
public void notTechnicalType() {
}

@Pointcut("!bean(*Recorder)")
public void notRecorderName() {
}

@Pointcut(
    "publicApplicationMethod() && " +
    "notTechnicalType() && notRecorderName()"
)
public void auditableMethod() {
}
~~~

Đây là **fragment các method đặt trong một class pointcut** có import `org.aspectj.lang.annotation.Pointcut`, không phải file độc lập. Các method `@Pointcut` có **return type void và thân rỗng**: Spring đọc metadata, không gọi các method như logic nghiệp vụ.

Có thể đặt pointcut methods vào `CommonPointcuts` rồi tham chiếu đầy đủ từ aspect:

~~~java
@Before("demo.aop.CommonPointcuts.auditableMethod()")
public void beforeBusiness(JoinPoint jp) {
    // ...
}
~~~

Method pointcut được tham chiếu ở class khác phải có Java visibility phù hợp, chẳng hạn public. Tách thành một class chính sách chung giúp nhóm tránh mỗi aspect có một phiên bản denylist riêng.

## 8. Dự án Java 17+ chạy được

Ta dùng **Spring Framework 6.2.12**, **Java 17+**, **Maven 3.9+**, không cần Spring Boot. Dự án có hai service, một recorder, một infrastructure bean và một `@Aspect`. Pointcut đủ rộng để có ý nghĩa loại trừ, nhưng rõ những nhóm không được advise.

### 8.1. Cấu trúc dự án

~~~text
spring-aop-exclusion/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── config/AppConfig.java
    ├── business/OrderService.java
    ├── business/ReportService.java
    ├── shared/AuditRecorder.java
    ├── infra/HealthInspector.java
    ├── aop/CommonPointcuts.java
    └── aop/LoggingAspect.java
~~~

### 8.2. Maven

**pom.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-exclusion</artifactId>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp ApplicationContext và Spring AOP dependency phù hợp; `aspectjweaver` hỗ trợ phân tích expression/annotation `@AspectJ`. Ví dụ dùng **Spring AOP proxy-based**, không phải AspectJ compile-time hoặc load-time weaving.

### 8.3. Hai business beans

**src/main/java/demo/business/OrderService.java**

~~~java
package demo.business;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    public void place(String orderId) {
        System.out.println("BUSINESS place " + orderId);
    }
}
~~~

**src/main/java/demo/business/ReportService.java**

~~~java
package demo.business;

import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public void generate(String period) {
        System.out.println("BUSINESS generate " + period);
    }
}
~~~

Cả hai là **Spring-managed service beans** do component scanning đăng ký. Hai class không final và public methods không final, nên Spring có thể dùng **class-based CGLIB proxy** khi advisor match. Chúng không triển khai interface; ta lấy trực tiếp bean theo concrete class.

### 8.4. Bean recorder được aspect sử dụng

**src/main/java/demo/shared/AuditRecorder.java**

~~~java
package demo.shared;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class AuditRecorder {

    private final AtomicInteger count = new AtomicInteger();

    public void record(String event) {
        count.incrementAndGet();
        System.out.println("AUDIT " + event);
    }

    public int size() {
        return count.get();
    }
}
~~~

`AuditRecorder` là một Spring `@Component` thông thường, được Spring tạo với scope singleton mặc định. Nó không tự được loại khỏi mọi advisor. Điều kiện loại trừ `demo.shared` và tên bean `*Recorder` sẽ ngăn **chính LoggingAspect** dùng nó làm mục tiêu advice trong ví dụ này.

`AtomicInteger` dùng để đếm an toàn ở mức thao tác tăng đơn lẻ. Đối với hệ thống audit thật, cần chọn storage và xử lý concurrency/lỗi phù hợp; không dùng singleton counter làm kho audit production.

### 8.5. Bean infrastructure bình thường

**src/main/java/demo/infra/HealthInspector.java**

~~~java
package demo.infra;

import org.springframework.stereotype.Component;

@Component
public class HealthInspector {

    public void ping() {
        System.out.println("INFRA ping");
    }
}
~~~

Mục tiêu là chứng minh một `@Component` kỹ thuật vẫn được Spring quản lý nhưng **không có nghĩa sẽ phải bị audit**. `HealthInspector` không mang annotation `@Aspect`; nó bị loại theo policy ứng dụng, không phải cơ chế tự loại aspect.

### 8.6. CommonPointcuts dùng cho nhiều aspect

**src/main/java/demo/aop/CommonPointcuts.java**

~~~java
package demo.aop;

import org.aspectj.lang.annotation.Pointcut;

public class CommonPointcuts {

    @Pointcut("execution(public * demo..*.*(..))")
    public void publicApplicationMethod() {
    }

    @Pointcut(
        "!within(demo.infra..*) && " +
        "!within(demo.shared..*) && " +
        "!within(demo.aop..*) && " +
        "!within(demo.config..*)"
    )
    public void notTechnicalType() {
    }

    @Pointcut("!bean(*Recorder) && !bean(healthInspector)")
    public void notTechnicalBeanName() {
    }

    @Pointcut(
        "publicApplicationMethod() && " +
        "notTechnicalType() && notTechnicalBeanName()"
    )
    public void auditableApplicationMethod() {
    }
}
~~~

**Cách đọc**:

1. `publicApplicationMethod` xác định phạm vi sơ bộ: public method execution của các type trong `demo`.
2. `notTechnicalType` loại bốn package kỹ thuật: infrastructure, recorder/shared, AOP helper và config.
3. `notTechnicalBeanName` loại bean name theo wildcard `*Recorder` và bean chính xác `healthInspector`.
4. `auditableApplicationMethod` kết hợp ba điều kiện bằng **giao logic**.

Điều kiện theo tên bean **có phần trùng** với điều kiện package trong ví dụ đơn giản này. Điều đó có chủ đích để minh họa **hai lớp bảo vệ**; không có quy tắc bắt buộc viết cả hai trong mọi Spring application.

`CommonPointcuts` **không cần** là một Spring bean hay mang `@Aspect`. Đây là class chứa các named `@Pointcut` public để aspect khác có thể tham chiếu bằng tên class đầy đủ. Các method pointcut có thân rỗng, không tự được gọi như business methods.

### 8.7. LoggingAspect inject recorder

**src/main/java/demo/aop/LoggingAspect.java**

~~~java
package demo.aop;

import demo.shared.AuditRecorder;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class LoggingAspect {

    private final AuditRecorder recorder;

    public LoggingAspect(AuditRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("demo.aop.CommonPointcuts.auditableApplicationMethod()")
    public void beforeBusiness(JoinPoint jp) {
        recorder.record("before " + jp.getSignature().getName());
    }
}
~~~

Spring inject một instance `AuditRecorder` vào constructor aspect. Advice dùng instance đó để ghi một sự kiện **trước mỗi business method đã match**. Việc gọi `recorder.record(...)` không bị **chính advisor này** advice vì recorder nằm ngoài phạm vi pointcut.

**Chú ý:** Spring AOP tự tránh auto-proxying aspect bean như một target, nhưng điều kiện `!within(demo.aop..*)` còn có tác dụng với **helper bean khác trong cùng package** nếu các helper không mang `@Aspect`.

### 8.8. ApplicationContext và AOP

**src/main/java/demo/config/AppConfig.java**

~~~java
package demo.config;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

`@ComponentScan` đăng ký hai business beans, recorder, inspector và aspect. `@EnableAspectJAutoProxy` bật hạ tầng tự động phát hiện advice và tạo proxy khi có advisor match. `@Aspect` một mình không tự đăng ký bean; trong ví dụ `LoggingAspect` có thêm `@Component`.

### 8.9. Main kiểm tra cả mục tiêu và loại trừ

**src/main/java/demo/App.java**

~~~java
package demo;

import demo.aop.LoggingAspect;
import demo.business.OrderService;
import demo.business.ReportService;
import demo.config.AppConfig;
import demo.infra.HealthInspector;
import demo.shared.AuditRecorder;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderService orders = context.getBean(OrderService.class);
            ReportService reports = context.getBean(ReportService.class);
            AuditRecorder recorder = context.getBean(AuditRecorder.class);
            HealthInspector inspector = context.getBean(HealthInspector.class);
            LoggingAspect aspect = context.getBean(LoggingAspect.class);

            System.out.println(
                    "SERVICE_PROXY " + AopUtils.isAopProxy(orders));
            System.out.println(
                    "RECORDER_PROXY " + AopUtils.isAopProxy(recorder));
            System.out.println(
                    "INFRA_PROXY " + AopUtils.isAopProxy(inspector));
            System.out.println(
                    "ASPECT_PROXY " + AopUtils.isAopProxy(aspect));

            orders.place("INV-105");
            reports.generate("weekly");

            recorder.record("manual");
            inspector.ping();

            System.out.println("AUDIT_COUNT " + recorder.size());
        }
    }
}
~~~

Chạy trong thư mục có `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

**Stdout logic kỳ vọng**, không tính các dòng Maven hay framework logging:

~~~text
SERVICE_PROXY true
RECORDER_PROXY false
INFRA_PROXY false
ASPECT_PROXY false
AUDIT before place
BUSINESS place INV-105
AUDIT before generate
BUSINESS generate weekly
AUDIT manual
INFRA ping
AUDIT_COUNT 3
~~~

**Giải thích kết quả**:

- `SERVICE_PROXY true`: `OrderService` có method nằm trong pointcut và được Spring bọc AOP proxy.
- `RECORDER_PROXY false` và `INFRA_PROXY false`: không có advisor nào trong context demo áp dụng cho các bean kỹ thuật ấy.
- `ASPECT_PROXY false`: đúng với cơ chế Spring AOP không auto-proxy class `@Aspect` như một target.
- `AUDIT before place` và `AUDIT before generate`: chính LoggingAspect được Spring gọi trước hai service methods.
- `AUDIT manual`: App tự gọi recorder; không có `AUDIT before record` vì recorder không khớp advisor audit.
- `INFRA ping`: inspector không có advice audit.
- `AUDIT_COUNT 3`: hai sự kiện từ aspect và một sự kiện manual; không có recursion phát sinh từ recorder.

Kết quả `RECORDER_PROXY false` **không phải** quy tắc chung cho mọi context. Nếu ứng dụng thực còn có advisor bảo mật hoặc transaction khác áp dụng cho recorder, `AopUtils.isAopProxy(recorder)` có thể true, dù pointcut của LoggingAspect đã loại recorder đúng cách. Phải kiểm tra **hành vi của chính advisor cần test** chứ không suy luận mọi proxy đều không tồn tại.

## 9. Vì sao package riêng giúp tránh advice tái nhập?

Thiết kế dễ gây lỗi:

~~~text
demo.service.OrderService
demo.service.ReportService
demo.service.AuditRecorder
demo.service.MetricWriter
~~~

Pointcut:

~~~text
execution(public * demo.service..*.*(..))
~~~

có thể chọn cả recorder và writer vì tất cả ở cùng package service. Khi aspect gọi recorder qua Spring proxy, nó có thể gặp advisor của chính mình.

Thiết kế rõ ràng hơn:

~~~text
demo.business.OrderService
demo.business.ReportService
demo.observability.AuditRecorder
demo.observability.MetricWriter
demo.infra.HealthInspector
demo.aop.LoggingAspect
~~~

Có thể chỉ cần:

~~~text
execution(public * demo.business..*.*(..))
~~~

để tạo một **positive allowlist**. Lúc đó technical beans mới thêm vào `demo.observability` không tự bị chọn.

Nếu hệ thống di sản chưa cho phép refactor package, dùng `!within` và `!bean` tạm thời cùng integration tests, rồi lên kế hoạch thu hẹp expression theo business layer.

## 10. Không nhầm loại trừ @Aspect với loại trừ phụ thuộc của aspect

Spring hiểu `@Aspect` và không dùng bean đó làm target để những Spring aspects khác proxy nó. **Nhưng recorder không tự được miễn**, ngay cả khi chỉ được tạo để phục vụ aspect.

Một aspect thường inject:

- `AuditRecorder`: ghi các sự kiện.
- `EventPublisher`: phát thông báo.
- `Clock`: lấy thời điểm.
- `LogFormatter`: format sự kiện.
- `MetricRegistry`: ghi metrics.

Nếu pointcut đủ rộng và những dependency này được Spring quản lý, Spring có thể xem chúng là target advisor. Phải phân tích **cả dependency graph của advice**, không chỉ tên class aspect.

Bản thân việc `LoggingAspect` không bị proxy **không** ngăn `AuditRecorder` bị proxy và lặp lại advice. Đây là lý do loại trừ shared observability code là một phần quan trọng của **pointcut policy**.

## 11. Một advisor khác vẫn có thể proxy technical bean

Pointcut quyết định phạm vi **của một advisor**, không phải một lệnh cấm mọi cơ chế proxy. Ví dụ:

- Audit aspect của bạn loại `AuditRecorder`.
- Một transaction/security advisor khác lại áp dụng cho method `record`.
- `AuditRecorder` vẫn có thể là Spring AOP proxy.
- Nhưng nếu advice của audit aspect không match recorder, riêng concern audit sẽ không tự tái nhập vì method đó.

Vì vậy không đặt mục tiêu “mọi bean recorder phải luôn `AopUtils.isAopProxy == false`” trong một ứng dụng có nhiều advisor. Mục tiêu đúng là:

1. Service cần audit được advisor audit thực thi.
2. Method recorder không bị **cùng advisor audit** chọn.
3. Số lượng sự kiện tương ứng số business operations mong muốn.
4. Không có vòng gọi từ advice vào chính nó thông qua các dependencies.

Cần phân biệt **tính hiện diện của proxy** với **tính phù hợp của pointcut cụ thể**.

## 12. Kiểm thử tích hợp positive và negative

Để xác thực policy, không chỉ đọc expression. Với cùng context của ví dụ, có thể viết một đoạn test trong một phương thức Java:

~~~java
if (!AopUtils.isAopProxy(orders)) {
    throw new AssertionError("OrderService must be proxied");
}
if (AopUtils.isAopProxy(recorder)) {
    throw new AssertionError("Recorder should not be proxied here");
}
if (AopUtils.isAopProxy(inspector)) {
    throw new AssertionError("Inspector should not be proxied here");
}
if (AopUtils.isAopProxy(aspect)) {
    throw new AssertionError("Aspect should not be proxied");
}

int before = recorder.size();
orders.place("T-1");
int after = recorder.size();

if (after != before + 1) {
    throw new AssertionError("Expected one audit event");
}
~~~

Đây là **fragment kiểm thử**, cần các biến `orders`, `recorder`, `inspector`, `aspect` đã lấy từ context và import `AopUtils` trong một class Java hợp lệ. Không chạy fragment trực tiếp từ command line như một chương trình độc lập.

Với ứng dụng thật có nhiều advisor, việc assert recorder không phải proxy có thể quá mạnh. Khi ấy nên ghi nhận chính xác hiệu ứng của **LoggingAspect** (ví dụ bộ đếm riêng cho advice) để xác nhận recorder không kích hoạt thêm invocation của aspect đó.

### Những trường hợp cần test

| Trường hợp | Mong muốn |
| --- | --- |
| Gọi business method qua Spring bean | Advice chạy đúng số lần |
| Gọi `AuditRecorder.record()` trực tiếp | Không kích hoạt LoggingAspect |
| Gọi `HealthInspector.ping()` | Không kích hoạt LoggingAspect |
| Gọi method của helper ngoài business package | Không kích hoạt audit business policy |
| Gọi `this.method()` nội bộ ở target | Không suy ra advice chạy; kiểm tra proxy boundary |
| Thêm bean có tên `sharedAuditSink` | Kiểm tra package/type policy, vì `*Recorder` không match tên ấy |
| Đổi `@Component` bean name | Chạy lại test vì `bean(...)` có thể thay đổi |
| Chuyển service sang package mới | Chạy lại test allowlist để không bỏ sót nghiệp vụ |

## 13. @Order và @Around không phải công cụ loại bean

`@Order` có thể quyết định **ưu tiên advisor/aspect** khi nhiều advice match cùng invocation. Nó không làm thay đổi việc method recorder có match pointcut hay không.

Tương tự:

- Đổi `@Before` thành `@Around` không tự chặn vòng nếu advice vẫn gọi recorder bị advisor cùng concern can thiệp.
- `ProceedingJoinPoint.proceed()` tiếp tục invocation hiện tại, không phải phép “bỏ qua mọi advice khác”.
- Tăng thread-safety của recorder với `AtomicInteger` không giải quyết vòng gọi qua proxy.
- Bật `proxyTargetClass = true` chuyển sang CGLIB nhưng không phải cách loại recorder khỏi pointcut.
- Tắt `@EnableAspectJAutoProxy` để tránh advice recorder sẽ đồng thời tắt hạ tầng Spring AOP trong context đó, ảnh hưởng cả service cần audit.

Cách sửa chính xác là **thu hẹp phạm vi pointcut**, đồng thời xem lại dependency graph và đường đi lời gọi.

## 14. Khi nào nên dùng !within, !bean hoặc @annotation?

| Bối cảnh | Ưu tiên |
| --- | --- |
| Có package business rõ | `execution(public * demo.business..*.*(..))` |
| Module cũ chứa cả business và technical types | Allowlist nếu có thể, nếu chưa thì phủ định `!within` chính xác |
| Cùng class nhưng nhiều Spring bean registrations có vai trò khác nhau | `bean(...)` để chọn hoặc loại bean name cụ thể |
| Audit chỉ những operation được developer đánh dấu | `@annotation` với annotation nghiệp vụ |
| Nhiều aspect dùng chung cùng business layer | `CommonPointcuts` public named methods |
| Recorder bị advice bởi chính aspect gọi nó | Bắt đầu bằng loại recorder khỏi pointcut đó, rồi kiểm tra graph |
| Chỉ muốn “aspect không bị advice bởi aspect khác” | Spring AOP đã có auto-exclusion cho `@Aspect`; không coi đây là chính sách loại recorder |

Đừng chọn một strategy duy nhất cho mọi dự án. Hệ thống có nhiều module và naming conventions khác nhau có thể cần kết hợp type package và bean-name filters; điều quan trọng là **viết ý định rõ ràng và kiểm thử trên context thật**.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Lặp log liên tục hoặc `StackOverflowError` | Advice gọi recorder; recorder match cùng advisor | Thu hẹp business allowlist hoặc loại recorder rõ ràng |
| Startup lỗi dependency giữa aspect và service | Dependency vòng qua collaborator | Vẽ dependency graph, tách recorder độc lập khỏi service đang được advice |
| Aspect không phải proxy | Spring AOP auto-exclusion với bean `@Aspect` | Hành vi bình thường, không phải lỗi |
| Recorder vẫn là proxy sau khi loại khỏi audit | Có advisor khác chọn recorder | Kiểm tra advisor cụ thể; không dựa vào proxy Boolean tổng quát |
| `!bean(*Recorder)` không loại bean ghi audit | Bean tên khác convention `*Recorder` | Kiểm tra tên bean thực tế, dùng type/package hoặc đổi convention |
| `!within(demo.shared..*)` không loại implementation nằm nơi khác | Type/package matching khác target runtime type | Test hierarchy/proxy, cân nhắc target/type restriction |
| Service mới không có audit | Allowlist theo package hoặc annotation chưa bao phủ | Cập nhật policy/test khi thêm hoặc chuyển service |
| Mọi infrastructure bean đều bị proxy | Pointcut quá rộng, thiếu boundary | Tách package và lọc theo business operations |
| Đổi `@Order` vẫn lặp advice | Ordering không đổi phạm vi match | Sửa pointcut |
| `@Aspect` class có nhưng advice không chạy | Aspect chưa được đăng ký như bean hoặc thiếu hạ tầng | `@Component`/ `@Bean`, `@EnableAspectJAutoProxy` |
| Method khớp chữ ký nhưng advice không chạy | Self-invocation hoặc caller dùng instance `new` | Kiểm tra đường gọi qua Spring proxy |
| Copy `bean(...)` sang weaving mode | Spring bean designator không có trong native AspectJ | Chỉ dùng trong Spring AOP pointcut |

## 16. Checklist thiết kế pointcut để tránh ghi nhận chính mã ghi nhận

1. Xác định **mọi dependency mà advice gọi**, không chỉ business target.
2. Vẽ sơ bộ call graph: Service proxy → Aspect → Recorder/Publisher → các dependencies tiếp theo.
3. Bắt đầu bằng **positive business allowlist** nếu kiến trúc cho phép.
4. Với phạm vi rộng, thêm `!within` cho technical packages/types và `!bean` cho registrations phù hợp.
5. Không trông đợi framework tự miễn các `@Component` helper chỉ vì chúng phục vụ aspect.
6. Đừng thêm mọi exclusion tràn lan nếu service cần thiết bị loại; dùng named pointcuts dễ đọc.
7. Xác minh `@Aspect` được đăng ký Spring bean và AOP được bật.
8. Kiểm tra **cả trường hợp nên match và không nên match** trong integration test.
9. Không coi `AopUtils.isAopProxy` là bằng chứng một advisor cụ thể đang hoặc không đang chạy.
10. Khi thay đổi package, bean name, annotation hay aspect dependency, chạy lại test để kiểm soát policy.
11. Tránh việc recorder tự gọi vào service được advise nếu không có chủ đích vì đó cũng có thể gây tái nhập thông qua một đường nghiệp vụ khác.
12. Nếu có nhiều concerns, thiết kế phạm vi pointcut riêng của từng concern thay vì dùng một pointcut cực rộng cho tất cả.

## 17. Câu hỏi tự đánh giá

**1. Vì sao Spring không tự loại `AuditRecorder` khỏi mọi Spring aspect?**

Vì `AuditRecorder` là Spring bean thông thường. Spring không biết theo tên class rằng advisor nào được phép can thiệp vào recorder nào; ứng dụng phải định nghĩa pointcut policy.

**2. Spring AOP có loại bean mang `@Aspect` khỏi auto-proxying như target không?**

Có. Nhưng bean đó vẫn cung cấp advice cho các bean nghiệp vụ và dependency của aspect không được miễn tương tự.

**3. `!within(demo.shared..*)` khác `!bean(*Recorder)` thế nào?**

Một điều kiện loại theo package/type method execution, điều kiện kia loại theo Spring bean name và convention.

**4. Tại sao allowlist `demo.business` thường dễ bảo trì hơn phủ định hàng chục package?**

Nó chỉ mở phạm vi tới business types rõ ràng, giúp technical beans mới ở ngoài package không bị match ngoài ý muốn.

**5. Có phải `AopUtils.isAopProxy(recorder)` luôn phải false sau khi bạn loại nó khỏi audit aspect?**

Không. Các advisor khác vẫn có thể proxy recorder. Điều cần kiểm tra là advisor audit có chạy khi recorder được gọi hay không.

**6. Dùng `@Order` có ngăn advice tự gọi recorder không?**

Không. `@Order` chỉ điều chỉnh thứ tự, không thay đổi tập join points mà pointcut match.

**7. Có thể gom nhiều điều kiện vào một class CommonPointcuts không?**

Có. Dùng các named `@Pointcut` public và để các aspect tham chiếu bằng tên đầy đủ.

**8. Có nên đánh dấu mọi bean hạ tầng là `@Aspect` để Spring bỏ qua chúng?**

Không. `@Aspect` thể hiện một vai trò AOP thực sự; lạm dụng nó để bỏ qua auto-proxy là sai mô hình. Hãy sửa policy bằng `execution`, `within`, `bean` hoặc annotation phù hợp.

## 18. Tài liệu Spring Framework

- Spring Framework 6.2 — **Declaring a Pointcut** (execution, within, bean, toán tử logic, named pointcuts): https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html
- Spring Framework 6.2 — **Declaring an Aspect** (aspect bean được loại khỏi auto-proxying với vai trò target): https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/at-aspectj.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — **Declaring Advice**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html

**Kết luận:** Spring AOP tự nhận diện `@Aspect` và không biến aspect bean thành target proxy của aspect khác. Nhưng **recorder, helper và infrastructure `@Component` vẫn là beans có thể được advisor xem xét**. Muốn tránh advice bao trùm mã ghi nhận của chính nó, hãy bắt đầu bằng **allowlist business methods**, tổ chức `CommonPointcuts`, bổ sung `!within`/`!bean` khi cần và kiểm thử cả đối tượng được chọn lẫn đối tượng phải loại.
