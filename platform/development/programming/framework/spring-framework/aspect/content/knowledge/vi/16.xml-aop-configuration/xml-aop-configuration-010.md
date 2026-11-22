# Kết hợp XML với Java configuration mà không tạo hành vi trùng lặp trong Spring AOP

## 1. Bài toán và mục tiêu

Trong một ứng dụng Spring Framework có lịch sử cấu hình lâu dài, một phần bean và Spring AOP advice thường được khai báo bằng XML, trong khi các chức năng mới dùng `@Configuration`, `@Bean`, `@Aspect` và `@EnableAspectJAutoProxy`. Hai cách khai báo **có thể cùng tồn tại**, bởi Spring đưa chúng vào cùng cơ chế proxy và advisor. Rủi ro không nằm ở việc một dự án có cả hai loại tệp, mà ở cách đăng ký cùng một aspect, cùng một chức năng hoặc nhiều advisor chồng lấn khiến một method bị audit, logging hay metrics **hai lần**.

Chẳng hạn, một service xử lý `process("A")`. Mục tiêu là có **đúng một bản ghi audit** cho lời gọi ấy. Nếu vừa giữ khai báo `<aop:aspect>` trong XML vừa đăng ký `@Aspect` làm cùng chức năng với cùng pointcut, audit có thể bị ghi hai lần dù nghiệp vụ chỉ chạy một lần. Ngược lại, hai advice độc lập trên cùng join point (ví dụ audit và transaction) là hành vi hợp lệ; không nên coi mọi trường hợp có nhiều advice là lỗi.

Bài tập trung vào **Spring AOP được quản lý bởi Spring ApplicationContext**:

- Cách nạp bean XML từ Java configuration bằng `@ImportResource`.
- Cách khai báo aspect theo XML schema (`<aop:config>`/`<aop:aspect>`) song song với aspect theo `@Aspect`.
- Quy tắc phân công trách nhiệm, tên bean, pointcut và auto-proxy để tránh gọi advice hai lần.
- Cách viết kiểm thử **số lần advice chạy**, không chỉ kiểm tra business result.
- Các ranh giới Spring proxy, context hierarchy, thứ tự advisor và quy trình chuyển dần cấu hình XML sang Java.

Kiến thức AOP tổng quát và AspectJ weaving độc lập không phải phạm vi của bài này.

## 2. Phân biệt ba việc dễ bị nhầm

| Việc được cấu hình | Ví dụ | Hành vi |
| --- | --- | --- |
| **Đăng ký bean** | `<bean id="paymentService" .../>` hoặc `@Bean paymentService()` | Đưa đối tượng nghiệp vụ/advice vào Spring container; chưa tự nói bean nào bị AOP. |
| **Khai báo advisor/aspect** | `<aop:aspect ref="xmlAuditAdvice">` hay `@Aspect` + `@Before` | Quy định method nào sẽ được intercept và logic nào chạy ở đó. |
| **Bật auto-proxying** | `<aop:config>`, `<aop:aspectj-autoproxy/>`, `@EnableAspectJAutoProxy` | Cho Spring tạo proxy và gắn advisor đủ điều kiện lên bean. |

Các cơ chế auto-proxy tiêu chuẩn được Spring tích hợp/thống nhất. Vì vậy, việc trong cùng context có `<aop:config>` và `@EnableAspectJAutoProxy` **không tự chứng minh** mỗi advice được chạy hai lần. Tuy nhiên, chúng có thể cùng lấy được hai **advisor mang cùng hành vi**, và khi đó method bị xử lý trùng.

Một nguồn trùng lặp rõ ràng:

~~~java
@Aspect
public class SharedAuditAspect {
    @Before("execution(* demo.PaymentService.process(..))")
    public void beforeProcess() {
        // ghi một audit event
    }
}
~~~

~~~xml
<bean id="sharedAuditAspect" class="demo.SharedAuditAspect"/>

<aop:config>
    <aop:aspect ref="sharedAuditAspect">
        <aop:before method="beforeProcess"
                    pointcut="execution(* demo.PaymentService.process(..))"/>
    </aop:aspect>
</aop:config>
~~~

Nếu `@Aspect` đã được Spring auto-detect và cũng có một khai báo XML `aop:aspect` tham chiếu đúng advice đó, **một phương thức advice được khai báo theo hai đường**. Đây là cấu hình cần tránh. Các fragment này chỉ mô tả một cấu hình sai, **không phải** phần của ví dụ runnable ở dưới.

### Quy tắc phân quyền cấu hình

1. **Một bean chỉ có một chủ sở hữu đăng ký** trong một application context: chọn XML `<bean>` hoặc Java `@Bean`/component scan; không tự tạo hai tên khác nhau cho cùng một logic.
2. **Một trách nhiệm cắt ngang chỉ có một chủ sở hữu advice**: nếu XML đã audit `process`, đừng thêm một Java aspect khác audit chính `process` cùng sự kiện. Nếu đang migration, bỏ khai báo cũ trong cùng bước chuyển sang khai báo mới.
3. **Hai concern độc lập có thể cùng dùng Spring AOP**: một XML aspect audit method `process`, một Java aspect ghi sự kiện vận hành cho method `cancel`; mỗi bên có pointcut rõ và test riêng.
4. **Một điểm bật @AspectJ auto-proxy rõ ràng** cho các aspect viết bằng annotation; không đăng ký lặp bean aspect. Nếu `<aop:config>` cũng hiện diện để khai báo XML advice, cơ chế đó sẽ được Spring phối hợp.

## 3. Sơ đồ kết hợp XML và Java configuration

Ví dụ sẽ tạo đúng **một Spring ApplicationContext**:

~~~text
AnnotationConfigApplicationContext(AppConfig.class)
                   |
                   +--> AppConfig.java
                   |      @Configuration
                   |      @ImportResource("classpath:spring/legacy-aop.xml")
                   |      @EnableAspectJAutoProxy(proxyTargetClass = true)
                   |      @Bean EventRecorder
                   |      @Bean JavaCancelAspect (@Aspect)
                   |
                   +--> legacy-aop.xml
                          <bean id="paymentService" ...>
                          <bean id="xmlAuditAdvice" ...>
                          <aop:config>
                             <aop:pointcut ...process(..)>
                             <aop:aspect ref="xmlAuditAdvice">
                                <aop:before method="beforeProcess" ...>
                             </aop:aspect>
                          </aop:config>
                   |
                   +--> Spring proxy for PaymentService
                          process("A") --> XML audit exactly once
                          cancel("B")  --> Java @Aspect exactly once
~~~

Ở ví dụ này:

- XML sở hữu bean nghiệp vụ `paymentService` và bean advice `xmlAuditAdvice`.
- Java configuration sở hữu `eventRecorder` và `javaCancelAspect`.
- XML audit và Java aspect có **hai trách nhiệm/pointcut riêng**.
- Cả hai được thử qua **cùng Spring proxy** để xác minh không có sự kiện trùng.

Có thể để hai aspect áp dụng lên *cùng* method nếu thực hiện hai concern khác nhau, nhưng cần xác định thứ tự và kiểm thử từng sự kiện. Ví dụ chọn hai method để quan sát rành mạch và tránh ngộ nhận.

## 4. Ví dụ Maven + Spring Framework 6.x + Java 17 chạy được

Ứng dụng mẫu không dùng Spring Boot và không có HTTP server, nhằm quan sát chính xác Spring AOP proxy. Maven, JDK 17+ và dependency truy cập được từ Maven repository là đủ. Với Spring Boot 3.x, cách đăng ký bean, `@ImportResource` và nguyên tắc chống trùng vẫn tương tự; dependency và auto-configuration phải theo BOM của Boot đang dùng.

### 4.1. Cấu trúc

~~~text
mixed-spring-aop/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── AppConfig.java
    │   │   ├── EventRecorder.java
    │   │   ├── PaymentService.java
    │   │   ├── XmlAuditAdvice.java
    │   │   ├── JavaCancelAspect.java
    │   │   └── Main.java
    │   └── resources/spring/legacy-aop.xml
    └── test/java/demo/MixedAopConfigurationTest.java
~~~

### 4.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>mixed-spring-aop</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cho phép dùng Java configuration và load XML; `spring-aop` cung cấp API proxy/AOP; `aspectjweaver` phục vụ cách biểu diễn pointcut và các annotation AspectJ mà Spring AOP phân tích. Đây là **Spring AOP proxy**, không phải chương trình dùng AspectJ load-time weaving. Các phiên bản chỉ là bộ dependency minh họa cố định, không phải khuyến nghị phiên bản mới nhất cho mọi dự án.

### 4.3. `src/main/java/demo/PaymentService.java`

~~~java
package demo;

public class PaymentService {
    public String process(String orderId) {
        return "processed:" + orderId;
    }

    public String cancel(String orderId) {
        return "cancelled:" + orderId;
    }
}
~~~

Class không `final`, method public và không `final` để Spring có thể dùng class-based proxy. Cả hai method đều không có code audit; đây là concern nằm ngoài service.

### 4.4. `src/main/java/demo/EventRecorder.java`

~~~java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class EventRecorder {
    private final List<String> events = new CopyOnWriteArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

Recorder là bean dùng chung để test quan sát **số lần advice chạy**. `CopyOnWriteArrayList` giúp an toàn với các lời gọi đồng thời trong ví dụ nhỏ; hệ thống production thường dùng logging, meter registry hoặc audit sink thực tế. Không dựa vào chuỗi log của framework để đếm vì logging có thể được cấu hình khác nhau.

### 4.5. `src/main/java/demo/XmlAuditAdvice.java`

~~~java
package demo;

import org.aspectj.lang.JoinPoint;

public class XmlAuditAdvice {
    private final EventRecorder recorder;

    public XmlAuditAdvice(EventRecorder recorder) {
        this.recorder = recorder;
    }

    public void beforeProcess(JoinPoint joinPoint) {
        recorder.add("xml:process:" + joinPoint.getArgs()[0]);
    }
}
~~~

`XmlAuditAdvice` là class Java bình thường **không gắn `@Aspect` hay `@Before`**. Spring sẽ biết đây là advice vì khai báo `<aop:before>` trong XML. Chỉ có một bean `xmlAuditAdvice` được đăng ký.

### 4.6. `src/main/java/demo/JavaCancelAspect.java`

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class JavaCancelAspect {
    private final EventRecorder recorder;

    public JavaCancelAspect(EventRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("execution(public * demo.PaymentService.cancel(..))")
    public void beforeCancel(JoinPoint joinPoint) {
        recorder.add("java:cancel:" + joinPoint.getArgs()[0]);
    }
}
~~~

Đây là **annotation-style aspect**. Trong ví dụ này không đánh dấu class bằng `@Component`, vì `@Bean` ở `AppConfig` sẽ đăng ký nó chính xác một lần. Pointcut chỉ áp dụng cho `cancel` nên không chồng lấn nghiệp vụ audit XML của `process`.

### 4.7. `src/main/resources/spring/legacy-aop.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="paymentService" class="demo.PaymentService"/>

    <bean id="xmlAuditAdvice" class="demo.XmlAuditAdvice">
        <constructor-arg ref="eventRecorder"/>
    </bean>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="processOperation"
                      expression="execution(public * demo.PaymentService.process(..))"/>

        <aop:aspect id="xmlAuditAspect" ref="xmlAuditAdvice">
            <aop:before method="beforeProcess"
                        pointcut-ref="processOperation"/>
        </aop:aspect>
    </aop:config>
</beans>
~~~

`eventRecorder` chưa khai báo trong XML vì do Java `@Bean` quản lý trong **cùng context**. Spring giải quyết tham chiếu `ref="eventRecorder"` khi khởi tạo bean advice. `proxy-target-class="true"` buộc chọn class-based proxy cho target, nhất quán với Java config.

Lưu ý: **không có** `<aop:aspectj-autoproxy/>` ở file này. Java configuration ở dưới sẽ bật @AspectJ auto-proxying; `<aop:config>` vẫn cung cấp advisor schema-style. Việc bỏ declaration lặp ở đây nhằm cấu hình rõ trách nhiệm, chứ không vì có hai tag bật auto-proxy chắc chắn tạo hai lần advice.

### 4.8. `src/main/java/demo/AppConfig.java`

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.ImportResource;

@Configuration
@ImportResource("classpath:spring/legacy-aop.xml")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    public EventRecorder eventRecorder() {
        return new EventRecorder();
    }

    @Bean
    public JavaCancelAspect javaCancelAspect(EventRecorder recorder) {
        return new JavaCancelAspect(recorder);
    }
}
~~~

Cơ chế liên kết:

- `@ImportResource` nạp định nghĩa bean và advisor trong file XML vào context đang khởi tạo từ `AppConfig`.
- `@Bean` tạo một `EventRecorder` cho cả hai advice.
- `@Bean` đăng ký đúng một instance `JavaCancelAspect`, có metadata `@Aspect` được Spring hỗ trợ khi `@EnableAspectJAutoProxy` đang bật.
- XML `<aop:config>` định nghĩa advisor cho `process`; Java `@Aspect` định nghĩa advisor cho `cancel`. Mỗi đường khai báo chạy một chức năng riêng.
- Hai nơi cùng chỉ định class-based proxy. Trong một Spring application context, hạ tầng auto-proxy tiêu chuẩn được thống nhất và cấu hình proxy mạnh hơn có thể ảnh hưởng mọi advice cùng dùng hạ tầng đó.

### 4.9. `src/main/java/demo/Main.java`

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventRecorder events = context.getBean(EventRecorder.class);

            System.out.println("proxy:" + AopUtils.isAopProxy(service));
            System.out.println(service.process("A"));
            System.out.println(service.cancel("B"));
            System.out.println("events:" + events.snapshot());
        }
    }
}
~~~

Chạy tại thư mục `mixed-spring-aop`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Main
~~~

**Các dòng do mã Java chủ động in ra**:

~~~text
proxy:true
processed:A
cancelled:B
events:[xml:process:A, java:cancel:B]
~~~

Các log thư viện/Maven (nếu có) phụ thuộc cấu hình riêng của môi trường và không nằm trong stdout minh họa. Quan trọng nhất là mảng events chứa **chính xác hai sự kiện theo hai concern**, không phải bốn sự kiện do advice vô tình được đăng ký hai lần.

## 5. Kiểm thử: xác nhận mỗi advice được thực thi đúng một lần

Tạo `src/test/java/demo/MixedAopConfigurationTest.java`:

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MixedAopConfigurationTest {

    @Test
    void xmlAndJavaAspectsCoexistWithoutDuplicateAdvice() {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventRecorder recorder = context.getBean(EventRecorder.class);

            // Test có gọi qua Spring AOP proxy thật.
            assertTrue(AopUtils.isAopProxy(service));
            assertTrue(AopUtils.isCglibProxy(service));

            assertEquals("processed:A", service.process("A"));
            assertEquals("cancelled:B", service.cancel("B"));

            // Đếm sự kiện, không chỉ assert business result.
            assertEquals(List.of("xml:process:A", "java:cancel:B"),
                         recorder.snapshot());

            // Gọi lặp để chắc chắn tỷ lệ 1 lời gọi : 1 advice.
            assertEquals("processed:C", service.process("C"));
            assertEquals("cancelled:D", service.cancel("D"));
            assertEquals(
                    List.of("xml:process:A", "java:cancel:B",
                            "xml:process:C", "java:cancel:D"),
                    recorder.snapshot());
        }
    }

    @Test
    void everyAspectBeanIsRegisteredExactlyOnce() {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            assertArrayEquals(new String[] {"javaCancelAspect"},
                    context.getBeanNamesForType(JavaCancelAspect.class));
            assertArrayEquals(new String[] {"xmlAuditAdvice"},
                    context.getBeanNamesForType(XmlAuditAdvice.class));
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q test
~~~

Kỳ vọng **2 bài test pass** khi cấu hình được nạp và Spring AOP được áp dụng đúng. Assertion kiểm tra số lần thực thi advice và số lượng bean sẽ phát hiện nhiều lỗi khác nhau:

- Một concern có hai advisor → event bị lặp mặc dù service chỉ chạy một lần.
- Aspect Java bị đăng ký qua `@Bean` và `@Component` ở hai đường → tên/số lượng bean hoặc event có thể khác kỳ vọng.
- XML chưa được nạp hoặc pointcut sai → thiếu sự kiện `xml:process:A`.
- `@EnableAspectJAutoProxy` thiếu hoặc Java aspect chưa được đăng ký → thiếu `java:cancel:B`.
- Caller lấy target trực tiếp, không qua proxy → `AopUtils.isAopProxy` thất bại và không có advice event.

Đây là **test tích hợp nhỏ cho configuration + proxy**, không chỉ unit test của class recorder. Nếu chuyển từ Spring XML sang Java, giữ các assertion này trong quá trình migration để biết ngay khi xóa thiếu hoặc giữ thừa một khai báo.

## 6. Những cấu hình hay gây trùng lặp

### 6.1. Một chức năng được định nghĩa đồng thời trong XML và `@Aspect`

Ví dụ XML cũ vẫn khai báo:

~~~xml
<aop:aspect ref="xmlAuditAdvice">
    <aop:before method="beforeProcess"
                pointcut="execution(* demo.PaymentService.process(..))"/>
</aop:aspect>
~~~

Sau đó có người thêm Java aspect mới cũng audit `process`:

~~~java
@Aspect
class JavaAuditAspect {
    @Before("execution(* demo.PaymentService.process(..))")
    public void beforeProcess() {
        // Ghi cùng một loại audit event với XML advice.
    }
}
~~~

Nếu bean `JavaAuditAspect` được đăng ký và auto-proxy tìm thấy, **hai advice cùng chức năng** sẽ chạy cho một lời gọi, trừ khi cấu hình khác chặn một đường. Cách sửa: xác định **một owner của audit**; xóa definition XML cũ khi Java aspect đã thay thế hoàn toàn, hoặc chỉ dùng XML đến lúc migration xong. Nếu thực sự là hai concern độc lập, đặt tên event, scope và test riêng để làm rõ hành vi mong muốn.

### 6.2. Một `@Aspect` được đăng ký thành nhiều Spring bean

~~~java
@Aspect
@Component
class DuplicateCandidateAspect {
    // advice ...
}
~~~

~~~java
@Configuration
@ComponentScan("demo")
class Config {
    @Bean
    DuplicateCandidateAspect duplicateCandidateAspect() {
        return new DuplicateCandidateAspect();
    }
}
~~~

Đây là **ví dụ sai**, không thuộc demo runnable. Nếu component scanning nhận `@Component`, còn method `@Bean` đăng ký một bean **khác tên**, Spring có thể có nhiều aspect instance của cùng class. Khi advisor được tạo cho cả hai, một join point có thể được advice hai lần. Nếu trùng **cùng tên bean**, hành vi có thể là lỗi cấu hình/bean overriding tùy chế độ container chứ không nên mặc định coi Spring đã âm thầm bỏ bản trùng.

Chọn đúng một trong hai: `@Component` + scan **hoặc** `@Bean` tường minh. Đừng cố sửa duplication bằng `@Primary`; annotation đó giúp chọn candidate khi inject một bean, không mặc nhiên xóa các advisor sinh ra từ aspect khác.

### 6.3. Đăng ký aspect bằng Java và tham chiếu lại như schema-style XML aspect

Nếu một bean đã mang `@Aspect` và các `@Before`/`@Around`, rồi XML tiếp tục có `<aop:aspect ref="sameBean">` khai báo chính method ấy, ứng dụng có **hai nguồn advice metadata** cho cùng logic. Khi đó nên chọn một style làm chủ concern. Để chuyển tiếp an toàn, có thể giữ bean Java chứa logic chung dưới dạng collaborator, và chỉ có **một** XML advice **hoặc** một `@Aspect` wrapper làm owner; không khai báo hai wrapper cùng pointcut khi chưa có chủ đích rõ ràng.

### 6.4. Khai báo auto-proxy nhiều lần

Các tag `<aop:config>`, `<aop:aspectj-autoproxy/>`, `<tx:annotation-driven/>` và các annotation tương ứng như `@EnableAspectJAutoProxy`/`@EnableTransactionManagement` tham gia cấu hình proxy của Spring. Theo tài liệu Spring, các thiết lập tiêu chuẩn được thống nhất; nếu một cấu hình yêu cầu `proxy-target-class="true"` thì lựa chọn class-based proxy có thể có hiệu lực rộng hơn bạn nghĩ.

Vì vậy:

- **Không suy rằng có 2 tag bật proxy ⇒ advice chạy 2 lần.** Điều cần đếm là advisor và event thực tế.
- Không thêm các auto-proxy creator độc lập như `BeanNameAutoProxyCreator`/`DefaultAdvisorAutoProxyCreator` vào context đã có `<aop:config>` nếu không có thiết kế rõ. Tài liệu Spring cảnh báo việc trộn creator trực tiếp với schema AOP có thể khiến advice bị bỏ qua hoặc cấu hình proxy không như dự kiến.
- Với ứng dụng lớn, thống nhất chính sách JDK proxy so với CGLIB và kiểm thử cả method trong interface lẫn implementation.

### 6.5. Trùng do nạp file XML hoặc quét class ở nhiều đường

Ví dụ `@ImportResource("classpath:spring/legacy-aop.xml")` đã load tệp, nhưng một `<import resource="legacy-aop.xml"/>` khác cũng load cùng cấu hình, hoặc module bootstrapping tạo hai context rồi cả hai cùng được dùng xử lý. Kết quả tùy cách bean definition được đặt tên, override, bean factory và mối quan hệ context.

Không nên đoán kết quả từ việc “hai lần import”. Hãy kiểm tra **danh sách bean và advisor ở context thật**, các nguồn load, tên bean/alias và việc target nhận bao nhiêu proxy/advice; dùng test đếm event để nhận diện hậu quả thực tế.

## 7. Khi XML và Java cần áp dụng trên cùng một method

Hai advice khác trách nhiệm trên cùng method là một cấu hình hợp lệ, ví dụ:

~~~text
process()
  -> Java security advice: kiểm tra quyền
  -> XML audit advice: ghi sự kiện
  -> target PaymentService.process()
~~~

Đây là **hai hành vi khác nhau**, không phải “audit hai lần”. Vấn đề phải giải quyết là thứ tự và kết quả:

- Thứ tự advice khi vào/ra phụ thuộc precedence của advisor/aspect, ví dụ `@Order` trên Java aspect hoặc `order` của `<aop:aspect>`. Một advice ưu tiên cao chạy **trước** trên đường vào và **sau** trên đường ra nếu bao quanh invocation.
- Nếu security chặn ngay từ đầu, audit nằm bên trong có thể không chạy. Hãy xác định audit nghiệp vụ cần ghi cả request bị từ chối hay chỉ method được chấp thuận rồi sắp xếp order tương ứng.
- Khi Java transaction advice và XML audit advice cùng áp dụng, cần xác định audit nên nằm ngoài hay trong transaction, được gọi khi rollback hay không.
- Viết test theo hành vi: với một `process("A")`, assert có đúng một `security:checked:A` và đúng một `audit:process:A`; nếu cần thứ tự thì assert danh sách event có thứ tự, thay vì chỉ kiểm tra số lượng.

Ví dụ khai báo order minh họa:

~~~xml
<aop:aspect id="auditAspect" ref="xmlAuditAdvice" order="20">
    <aop:before method="beforeProcess"
                pointcut="execution(* demo.PaymentService.process(..))"/>
</aop:aspect>
~~~

~~~java
@Aspect
@Order(10)
class SecurityAspect {
    @Before("execution(* demo.PaymentService.process(..))")
    public void checkAccess() {
        // kiểm tra quyền của caller
    }
}
~~~

Hai đoạn **chưa phải class/file chạy độc lập**. Với `@Order(10)` và XML `order="20"`, Java advice có ưu tiên cao hơn. Nếu muốn phụ thuộc thứ tự chính xác giữa nhiều advisor trong hệ thống đang dùng transaction/security, kiểm thử context hoàn chỉnh thay vì tin vào thứ tự khai báo file.

## 8. Kiểm chứng khi chuyển từ XML sang Java

Để chuyển **một concern** từ XML sang Java, trước tiên ghi lại các advisor XML, pointcut, bean IDs, `order` và tập method phải match/không match. Viết integration test đếm chính advice đó, gồm success và exception path; chuẩn bị class `@Aspect` mới nhưng chưa đăng ký trùng vào production context.

Khi chuyển, **bỏ cùng một lần** XML `<aop:aspect>`/`aop:advisor` cũ của concern ấy và đăng ký đúng một bean `@Aspect` mới. Giữ `@ImportResource` và các XML bean definitions khác nếu chưa chuyển. Test lại số event mỗi invocation và thứ tự advisor; nếu không còn khai báo schema-based AOP thì mới xem xét bỏ `<aop:config>`.

Bài **“Chuyển đổi cấu hình XML sang annotation và kiểm tra tương đương”** giữ vai trò hướng dẫn migration chi tiết: bảng ánh xạ XML → annotations, chương trình hai context độc lập và đối chiếu proxy/return/exception/events. Bài hiện tại tập trung vào **cách cùng tồn tại an toàn trong một context** trước và trong lúc migration.

## 9. Cách chẩn đoán số lần advice chạy sai

### Kiểm tra bean và proxy

Trong test, cần kiểm tra đúng context/bean:

~~~java
PaymentService service = context.getBean(PaymentService.class);
boolean proxied = AopUtils.isAopProxy(service);
String[] javaAspectNames = context.getBeanNamesForType(JavaCancelAspect.class);
String[] xmlAdviceNames = context.getBeanNamesForType(XmlAuditAdvice.class);
~~~

Đây là fragment chạy **bên trong test có biến `context`**. Với code ở mục 5, cả hai danh sách phải có đúng một phần tử tên theo cấu hình. Nếu aspect được tạo ở parent và child context, hãy kiểm tra từng context riêng và xem service thực sự là bean của context nào.

Có thể inspect advisor của proxy:

~~~java
if (service instanceof org.springframework.aop.framework.Advised advised) {
    for (org.springframework.aop.Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor);
    }
}
~~~

Đây là **đoạn chẩn đoán**, không phải stdout cố định; tên/lớp advisor có thể khác theo phiên bản Spring và các starter đang bật. Đừng assert số lượng advisor bằng một hằng số tùy tiện: infrastructure có thể bổ sung các interceptor mà bạn không tự khai báo. Thay vào đó, assert số lượng **event nghiệp vụ** và từng loại event.

### Ma trận lỗi và cách xử lý

| Hiện tượng | Điều kiểm tra đầu tiên | Hướng khắc phục |
| --- | --- | --- |
| Một lần `process` ghi hai audit event | Có hai advisor match cùng pointcut và cùng audit logic? | Chọn một owner, bỏ khai báo audit trùng. |
| Aspect Java chạy hai lần | `@Component` và `@Bean` cùng tạo aspect bean? | Đăng ký duy nhất một instance. |
| XML advice không chạy | `@ImportResource` đúng path, `<aop:config>`/`pointcut-ref` đúng, bean được gọi qua proxy? | Đọc danh sách advisor và kiểm tra pointcut. |
| Java `@Aspect` không chạy | Có bật `@EnableAspectJAutoProxy` và aspect bean được đăng ký? | Bổ sung activation/bean đúng nơi. |
| Bean class-cast lỗi | Proxy là JDK interface-based hay class-based? | Inject theo interface hoặc cấu hình proxy hợp lệ. |
| Bản ghi audit nhiều nhưng advice chỉ chạy một lần | Recorder/logger có nhiều appender, target cũng tự ghi audit? | Tách event tại advice với side effect bên ngoài. |
| Một test xanh dù advice không chạy | Test chỉ assert kết quả của service? | Assert cả proxy và event counter. |
| Advice order không như kỳ vọng | `@Order` và XML `order` có nhất quán? | Thêm kiểm thử event trước/sau. |
| Method nội bộ không bị intercept | Self-invocation gọi `this.otherMethod()` | Gọi qua bean/proxy đúng thiết kế Spring. |

### Lưu ý Spring Boot

Spring Boot có thể auto-configure AOP và chọn class-based proxy theo property/phiên bản. Nếu dự án Boot đồng thời dùng `spring-boot-starter-aop`, `@EnableAspectJAutoProxy` và XML `<aop:config>`, hãy xác minh bean/advisor thực tế thay vì suy rằng cứ có nhiều activation là có nhiều proxy. Với `@ImportResource`, cân nhắc bean definition overriding: hai bean cùng tên có thể bị chặn bởi cấu hình Boot hoặc có hành vi ghi đè nếu cho phép; **không dùng overriding để giải quyết ambiguity**.

Spring AOP vẫn chỉ intercept các execution đi qua Spring proxy. Tạo mới target bằng `new` hoặc self-invocation không đi qua proxy có thể làm event thiếu; đây không phải dấu hiệu có hai hay một cấu hình.

## 10. Checklist đưa vào dự án

- [ ] Chỉ một `ApplicationContext` sở hữu những bean/advisor cần kết hợp; quan hệ parent/child được xác định rõ.
- [ ] Mỗi bean AOP có một đường đăng ký (`<bean>` hoặc `@Bean`/component scan); tên/alias rõ ràng.
- [ ] Với mỗi concern, xác định một nguồn khai báo pointcut/advice chính (XML schema hoặc `@Aspect`).
- [ ] `@ImportResource` nạp đúng file XML; XML có namespace `aop` đúng và không import lặp ngoài chủ đích.
- [ ] `@EnableAspectJAutoProxy` (hoặc một cách activation tương đương) sẵn sàng khi có `@Aspect`; `<aop:config>` sử dụng đúng khi còn XML advice.
- [ ] Chọn thống nhất chiến lược proxy và kiểm tra giới hạn interface/final/self-invocation.
- [ ] Nếu nhiều concern cùng khớp một method, ghi rõ trách nhiệm và order, có test tương ứng.
- [ ] Test có cả `AopUtils.isAopProxy`, đếm bean aspect, đếm **advice invocation** theo từng method, positive/negative path.
- [ ] Khi migration một concern, xóa khai báo advice cũ **cùng lúc** đăng ký advice mới và chạy lại test.

**Tiêu chí hoàn thành:** XML bean và Java configuration nạp trong cùng Spring context; đúng proxy được tạo; mỗi lời gọi `process` sinh **một XML audit event**, mỗi lời gọi `cancel` sinh **một Java advice event**; không có bean/aspect/advisor cùng trách nhiệm được đăng ký ngoài chủ đích.

## Tài liệu tham khảo chính thức

- Spring Framework — Mixing Aspect Types: https://docs.spring.io/spring-framework/reference/core/aop/mixing-styles.html
- Spring Framework — Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — ImportResource: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/annotation/ImportResource.html
