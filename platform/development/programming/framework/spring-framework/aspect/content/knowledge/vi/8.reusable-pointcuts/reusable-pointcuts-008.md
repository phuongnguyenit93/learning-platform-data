# Kiểm thử ca được khớp và ca không được khớp của pointcut trong Spring AOP

## 1. Mục tiêu: kiểm chứng cả “match” và “không match”

Trong Spring AOP, một biểu thức pointcut cho biết **những method execution trên Spring bean** sẽ được advice quan tâm. Kiểm thử chỉ một method có advice chạy là chưa đủ: một pointcut viết quá rộng có thể vô tình intercept method khác, gây log thừa, chậm ứng dụng hoặc áp dụng chính sách sai nơi.

Mục tiêu của bài thực hành là tổ chức pointcut thành **hai điều kiện có tên**, kết hợp chúng bằng `&&`, rồi dùng **JUnit 5 và Spring ApplicationContext thực** để khẳng định:

1. **Ca dương (match):** method đáp ứng *cả hai* điều kiện, được gọi qua Spring proxy → `@Before` chạy đúng một lần, trước target.
2. **Ca âm 1:** method đúng phạm vi class/chữ ký nhưng **không mang annotation** → không advice.
3. **Ca âm 2:** method có annotation nhưng **không đúng kiểu trả về mà pointcut yêu cầu** → không advice.
4. **Ca âm 3:** method có annotation nhưng thuộc **class khác** → không advice.
5. **Ca âm ranh giới proxy:** gọi annotated method thông qua `this.method()` từ bên trong target → không advice cho lời gọi nội bộ.
6. **Ca âm đối tượng tự tạo:** cùng class/method nhưng dùng `new` ngoài Spring → không có Spring auto-proxy.

Bài học tập trung vào **Spring Framework - Aspect**, cụ thể là cách **kiểm thử pointcut đã tổ chức**; không đi sâu vào lý thuyết AspectJ ngoài Spring. Ký pháp `@Aspect`/`@Pointcut` có nguồn gốc AspectJ nhưng Spring AOP thực thi bằng **JDK/CGLIB proxy** trên Spring-managed beans, không dùng bytecode weaving.

## 2. Hai tầng kiểm thử pointcut

### Tầng 1: thử biểu thức có match một method không

Spring cung cấp `org.springframework.aop.aspectj.AspectJExpressionPointcut` để biểu diễn một pointcut dùng cú pháp AspectJ. Với một `Method` và một target class, có thể kiểm tra `matches(method, targetClass)`. Đây là phép kiểm tra **khả năng match theo phương thức**, hữu ích để phát hiện pattern quá rộng/hẹp.

~~~java
AspectJExpressionPointcut pointcut = new AspectJExpressionPointcut();
pointcut.setExpression(
    "execution(public void demo.PaymentService.*(..))"
    + " && @annotation(demo.Measured)"
);
boolean matches = pointcut.matches(
    PaymentService.class.getMethod("pay"),
    PaymentService.class
);
~~~

Đây là **đoạn minh họa đặt trong method Java** với import `org.springframework.aop.aspectj.AspectJExpressionPointcut`; các class tương ứng được định nghĩa ở project đầy đủ bên dưới. Lúc này chưa chứng minh Spring đã **tạo proxy hoặc thực thi advice**, chỉ kiểm tra expression với chữ ký method và metadata.

### Tầng 2: integration test gọi method qua Spring bean proxy

Một integration test dùng `AnnotationConfigApplicationContext` cần kiểm chứng lần lượt:

- Context bật `@EnableAspectJAutoProxy`; aspect đã được đăng ký làm bean.
- Service lấy từ context thực sự là AOP proxy khi có advisor áp dụng (`AopUtils.isAopProxy`).
- Gọi method **qua reference bean Spring cấp**.
- Quan sát **marker nằm trong advice**, thứ tự marker so với method target, và số lần advice chạy.
- Gọi các phương thức *không* match để assert **không có marker advice**, không chỉ assert target vẫn chạy.

**Hai tầng không thay thế cho nhau.** `pointcut.matches(...) == true` không bảo đảm advice sẽ chạy khi gọi qua `this` hoặc object `new`. Ngược lại, thấy proxy tồn tại không khẳng định mọi method trong class đều khớp pointcut.

## 3. Thiết kế ma trận ca kiểm thử trước khi viết aspect

Giả sử pointcut mục tiêu là:

~~~text
execution(public void demo.PaymentService.*(..))
    &&
@annotation(demo.Measured)
~~~

Ý nghĩa:

- Điều kiện A: method `public`, trả về `void`, được khai báo trong `demo.PaymentService`.
- Điều kiện B: method được đánh dấu `@Measured`.
- Toán tử `&&`: cả A **và** B phải thỏa.

Ma trận cho project ở phần 4:

| Method được gọi | Đúng class + public void? (A) | Có @Measured? (B) | Có advice khi qua proxy? |
| --- | --- | --- | --- |
| `PaymentService.pay()` | Có | Có | **Có: 1 lần** |
| `PaymentService.preview()` | Có | Không | **Không** |
| `PaymentService.refund()` (trả `String`) | Không | Có | **Không** |
| `OtherService.pay()` | Không, class khác | Có | **Không** |
| `PaymentService.callPayInside()` | Có | Không | **Không** tại entry method |
| `this.pay()` bên trong `callPayInside()` | Đúng chữ ký và có annotation | Có | **Không**, vì self-invocation không qua proxy |
| `new PaymentService(...).pay()` | Đúng chữ ký và có annotation | Có | **Không**, vì object không do Spring auto-proxy |

Hai hàng cuối phân biệt **không match theo expression** với **không có join point đi qua proxy**: method có thể đúng về annotation/chữ ký nhưng không được AOP intercept trong lời gọi cụ thể.

Nếu chỉ test `pay()` mà không test `preview()`/`refund()`/`OtherService.pay()`, rất khó phát hiện việc bỏ nhầm một trong hai ràng buộc của pointcut.

## 4. Project Maven/Java 17+ chạy được

Ta viết **một project nhỏ** có đầy đủ mã và test. Không cần Spring Boot, web server, database, mock framework hay Spring TestContext vì `AnnotationConfigApplicationContext` đủ cho integration test minh họa.

Cấu trúc thư mục:

~~~text
spring-pointcut-match-test/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── Measured.java
    │   ├── EventLog.java
    │   ├── PaymentService.java
    │   ├── OtherService.java
    │   ├── MatchAspect.java
    │   └── AopConfig.java
    └── test/java/demo/
        └── PointcutMatchTest.java
~~~

Yêu cầu: JDK 17+, Maven 3.9+ và có thể resolve dependency. Các phiên bản cố định dùng cho bài thực hành: **Spring Framework 6.2.0**, **AspectJ Weaver 1.9.22**, **JUnit Jupiter 5.11.0**; không coi đó là phiên bản mới nhất của thư viện.

### 4.1. Tạo `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-pointcut-match-test</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
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
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

- `spring-context` cung cấp container và Java configuration.
- `spring-aop` cung cấp auto-proxy, `AopUtils` và `AspectJExpressionPointcut`.
- `aspectjweaver` cung cấp các kiểu thư viện cần để Spring phân tích cú pháp `@AspectJ`; **không** tự kích hoạt weaving.
- `junit-jupiter` là JUnit 5 để viết `@Test` và assertions; `maven-surefire-plugin` chạy chúng qua lệnh Maven.

### 4.2. Annotation đánh dấu method

Tạo `src/main/java/demo/Measured.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Measured {
}
~~~

`@Retention(RUNTIME)` giữ annotation có thể được dùng khi AOP xét method ở runtime. `@Target(METHOD)` ngăn dùng nhầm annotation trên class/field. Nó chỉ là dấu mốc metadata; bản thân annotation không thực thi advice.

### 4.3. EventLog độc lập để không phụ thuộc logger hay stdout

Tạo `src/main/java/demo/EventLog.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

public class EventLog {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

Project test chạy từng context riêng và mỗi phép kiểm tra gọi method tuần tự, nên `ArrayList` đủ dùng. Trong ứng dụng concurrent thực tế, cần logger/thread-safe event sink hoặc test synchronization phù hợp. `snapshot()` tạo danh sách không sửa được ở ngoài, để assertions không vô tình thay đổi kết quả.

### 4.4. Service được advice và những ca không match

Tạo `src/main/java/demo/PaymentService.java`:

~~~java
package demo;

public class PaymentService {
    private final EventLog log;

    public PaymentService(EventLog log) {
        this.log = log;
    }

    @Measured
    public void pay() {
        log.add("PAY");
    }

    public void preview() {
        log.add("PREVIEW");
    }

    @Measured
    public String refund() {
        log.add("REFUND");
        return "ok";
    }

    public void callPayInside() {
        log.add("CALL_INSIDE");
        this.pay();
    }
}
~~~

Những chi tiết có chủ ý:

- `pay()`: `public void` và `@Measured` → **match cả A và B**.
- `preview()`: `public void` nhưng không annotation → chỉ thỏa A.
- `refund()`: có `@Measured` nhưng return type `String` → chỉ thỏa B.
- `callPayInside()`: entry method không annotated; `this.pay()` trong target không đi qua Spring proxy → advice không chạy cho internal call. Event `PAY` vẫn được thêm vì business method vẫn thực thi.
- Class và method không `final`, dễ được Spring bọc bằng class-based proxy.

Tạo `src/main/java/demo/OtherService.java`:

~~~java
package demo;

public class OtherService {
    private final EventLog log;

    public OtherService(EventLog log) {
        this.log = log;
    }

    @Measured
    public void pay() {
        log.add("OTHER_PAY");
    }
}
~~~

`OtherService.pay()` có **cùng annotation** và đúng kiểu trả về nhưng không thuộc class `PaymentService`. Đây là ca âm chống việc vô tình chỉ viết `@annotation(demo.Measured)` quá rộng.

### 4.5. Tách điều kiện thành hai named pointcuts

Tạo `src/main/java/demo/MatchAspect.java`:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;

@Aspect
public class MatchAspect {
    private final EventLog log;

    public MatchAspect(EventLog log) {
        this.log = log;
    }

    @Pointcut("execution(public void demo.PaymentService.*(..))")
    public void paymentVoidMethod() {
    }

    @Pointcut("@annotation(demo.Measured)")
    public void measuredMethod() {
    }

    @Before("paymentVoidMethod() && measuredMethod()")
    public void beforeMeasuredPayment() {
        log.add("ADVICE_PAY");
    }
}
~~~

Điều cần nhớ về việc **tổ chức pointcut** trong Spring AOP:

1. `paymentVoidMethod()` là **pointcut signature** (tên để tham chiếu); biểu thức `execution(...)` mới quyết định loại method execution được xét. Method định nghĩa `@Pointcut` phải có kiểu trả về `void`, thân rỗng.
2. `measuredMethod()` đại diện cho điều kiện method có annotation `@Measured`.
3. `@Before("paymentVoidMethod() && measuredMethod()")` tái sử dụng hai named pointcuts; nếu muốn thu hẹp thêm package/bean name, có thể ghép điều kiện mới mà vẫn giữ tên rõ nghĩa.
4. `ADVICE_PAY` chỉ được thêm trong method advice, nên một event này là bằng chứng advice thực sự thực thi.
5. Một bean khác có `@Measured` nhưng không nằm trong `PaymentService` không được advice, vì phép `&&` đòi hỏi **cả hai** điều kiện.
6. `@Aspect` mới chỉ đánh dấu class aspect; nó phải được đăng ký làm Spring bean ở phần cấu hình dưới đây.

### 4.6. Đăng ký Spring-managed beans và bật AOP

Tạo `src/main/java/demo/AopConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
    @Bean
    public EventLog eventLog() {
        return new EventLog();
    }

    @Bean
    public PaymentService paymentService(EventLog log) {
        return new PaymentService(log);
    }

    @Bean
    public OtherService otherService(EventLog log) {
        return new OtherService(log);
    }

    @Bean
    public MatchAspect matchAspect(EventLog log) {
        return new MatchAspect(log);
    }
}
~~~

`@EnableAspectJAutoProxy(proxyTargetClass = true)` bật Spring AOP và yêu cầu class-based proxy cho bean cần proxy. Vì `PaymentService` không implement interface, class proxy là cách phù hợp để lấy bean bằng `PaymentService.class`. Tùy hạ tầng/kiểu bean, Spring có thể chọn class-based proxy ngay cả khi `proxyTargetClass` không được đặt; cờ `true` làm lựa chọn rõ ràng trong demo.

**Không phải mọi bean trong context đều bị proxy.** Spring auto-proxy creator sẽ xét advisor. `OtherService` không có method khớp điều kiện `paymentVoidMethod() && measuredMethod()`; do đó bài không dựa vào việc `OtherService` có proxy hay không, chỉ khẳng định **không có advice từ `MatchAspect`** cho nó.

`EventLog` được inject vào service và aspect, là cùng một singleton bean trong một context. Mỗi test sẽ tạo **context mới** để không rò rỉ sự kiện giữa các test.

## 5. Tập integration tests với JUnit Jupiter

Tạo `src/test/java/demo/PointcutMatchTest.java`:

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.AspectJExpressionPointcut;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class PointcutMatchTest {

    @Test
    void positiveCaseAnnotatedPublicVoidPaymentMatches() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventLog log = context.getBean(EventLog.class);

            assertTrue(AopUtils.isAopProxy(service));

            service.pay();

            assertEquals(List.of("ADVICE_PAY", "PAY"), log.snapshot());
        }
    }

    @Test
    void negativeCaseMissingAnnotationDoesNotMatch() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventLog log = context.getBean(EventLog.class);

            service.preview();

            assertEquals(List.of("PREVIEW"), log.snapshot());
        }
    }

    @Test
    void negativeCaseWrongReturnTypeDoesNotMatch() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventLog log = context.getBean(EventLog.class);

            assertEquals("ok", service.refund());

            assertEquals(List.of("REFUND"), log.snapshot());
        }
    }

    @Test
    void negativeCaseAnnotationOnDifferentClassDoesNotMatch() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            OtherService other = context.getBean(OtherService.class);
            EventLog log = context.getBean(EventLog.class);

            other.pay();

            assertEquals(List.of("OTHER_PAY"), log.snapshot());
        }
    }

    @Test
    void negativeCaseSelfInvocationSkipsAdvice() {
        try (var context =
                new AnnotationConfigApplicationContext(AopConfig.class)) {
            PaymentService service = context.getBean(PaymentService.class);
            EventLog log = context.getBean(EventLog.class);

            assertTrue(AopUtils.isAopProxy(service));

            service.callPayInside();

            assertEquals(
                    List.of("CALL_INSIDE", "PAY"),
                    log.snapshot());
        }
    }

    @Test
    void negativeCasePlainJavaObjectHasNoAutoProxy() {
        EventLog log = new EventLog();
        PaymentService plain = new PaymentService(log);

        assertFalse(AopUtils.isAopProxy(plain));

        plain.pay();

        assertEquals(List.of("PAY"), log.snapshot());
    }

    @Test
    void staticPointcutMethodMatchesAreCorrect() throws Exception {
        var pointcut = new AspectJExpressionPointcut();
        pointcut.setExpression(
                "execution(public void demo.PaymentService.*(..))"
                + " && @annotation(demo.Measured)");

        assertTrue(pointcut.matches(
                PaymentService.class.getMethod("pay"),
                PaymentService.class));

        assertFalse(pointcut.matches(
                PaymentService.class.getMethod("preview"),
                PaymentService.class));

        assertFalse(pointcut.matches(
                PaymentService.class.getMethod("refund"),
                PaymentService.class));

        assertFalse(pointcut.matches(
                OtherService.class.getMethod("pay"),
                OtherService.class));
    }
}
~~~

Đây là **bảy test methods hoàn chỉnh**. Mỗi test chỉ kiểm tra một ý, tránh test quá nhiều thao tác rồi kết luận không biết advice nào đã gây thay đổi.

### Phân tích các assertion

**Test dương:**

~~~java
service.pay();
assertEquals(List.of("ADVICE_PAY", "PAY"), log.snapshot());
~~~

Khẳng định **cả có advice và đúng thứ tự**: `@Before` thêm `ADVICE_PAY` trước khi business method thêm `PAY`. Nếu pointcut không match hoặc gọi không qua proxy, danh sách chỉ có `PAY` và test fail.

**Test âm thiếu annotation:**

~~~java
service.preview();
assertEquals(List.of("PREVIEW"), log.snapshot());
~~~

Nếu vô tình xóa điều kiện `measuredMethod()` hoặc thay bằng biểu thức rộng, `ADVICE_PAY` sẽ xuất hiện trước `PREVIEW` và assertion sẽ fail.

**Test âm sai kiểu trả về:**

~~~java
service.refund();
assertEquals(List.of("REFUND"), log.snapshot());
~~~

`refund` vẫn mang `@Measured`, nhưng biểu thức `execution(public void ...)` loại nó do trả `String`. Nếu viết pointcut chỉ có `@annotation(demo.Measured)`, test này sẽ fail.

**Test âm sai class:**

~~~java
other.pay();
assertEquals(List.of("OTHER_PAY"), log.snapshot());
~~~

Nếu bỏ giới hạn `demo.PaymentService` khỏi named pointcut, advice có thể lan sang class khác mang annotation tương tự.

**Test âm self-invocation:** `callPayInside()` vào target rồi `this.pay()`, method `pay` vẫn ghi `PAY` nhưng internal call không đi qua proxy. Test giúp phân biệt **mismatch pointcut** với **đường gọi không qua Spring proxy**.

**Test âm object thường:** `new PaymentService(log)` không phải Spring bean, dù method thỏa cú pháp pointcut. `@EnableAspectJAutoProxy` không tự lắp interception cho raw Java object.

**Test kiểm tra trực tiếp pointcut:** `AspectJExpressionPointcut.matches(...)` kiểm tra “hình dạng” method theo biểu thức. Kết hợp với integration tests phía trên để chứng minh vừa **match chính xác**, vừa **Spring AOP thực thi advice ở runtime**.

Điều cần chú ý: test `staticPointcutMethodMatchesAreCorrect` không tạo container, nên nó chỉ kiểm tra biểu thức, không thay thế sáu test kiểm tra hành vi. Nếu static check báo true, không tự suy rằng lời gọi qua `this` hay `new` sẽ được advice.

## 6. Chạy test và đọc kết quả thật

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn clean test
~~~

Nếu sử dụng Maven đã tải đủ dependency và mọi test pass, kết quả cần tìm trong báo cáo Surefire tương tự:

~~~text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
~~~

Tên file báo cáo thường là:

~~~text
target/surefire-reports/demo.PointcutMatchTest.txt
~~~

Không cố định toàn bộ stdout của Maven vì phiên bản Maven/JDK, terminal và logger có thể chèn các dòng khác. **Lệnh phải kết thúc với exit code `0`** và báo cáo `7` tests pass; khi `mvn clean test` trả nonzero hãy xem assertion failure hoặc root cause trước khi tuyên bố hoàn tất.

Để chỉ chạy một test cụ thể:

~~~bash
mvn -Dtest=PointcutMatchTest#positiveCaseAnnotatedPublicVoidPaymentMatches test
~~~

Có thể chọn một test âm để xác nhận một giới hạn riêng:

~~~bash
mvn -Dtest=PointcutMatchTest#negativeCaseWrongReturnTypeDoesNotMatch test
~~~

Chạy riêng một test thuận tiện khi debug nhưng **không đủ** để tuyên bố toàn bộ pointcut đúng: cần chạy lại đủ các test dương/âm.

Nếu IDE không nhận JUnit 5, kiểm tra đúng `src/test/java`, dependency `junit-jupiter` có `scope=test`, và plugin `maven-surefire-plugin`. Nếu Spring không tạo AOP proxy, kiểm tra `@EnableAspectJAutoProxy`, bean `MatchAspect`, dependency `aspectjweaver` và pointcut.

## 7. Kiểm thử kiểu “mutation”: cố tình làm pointcut sai

Một cách hay để đánh giá bộ test là **sửa sai có chủ đích**, chạy test để thấy assertion phát hiện được, rồi **khôi phục đúng cấu hình**.

Các thay đổi dưới đây chỉ dùng **một lần một thay đổi** trên `MatchAspect.java`:

### Mutation A: bỏ điều kiện annotation

Thay:

~~~java
@Before("paymentVoidMethod() && measuredMethod()")
~~~

bằng:

~~~java
@Before("paymentVoidMethod()")
~~~

Khi đó các method `public void` trong `PaymentService` có thể được advice dù không có `@Measured`. Test `negativeCaseMissingAnnotationDoesNotMatch` sẽ thất bại (nhận `ADVICE_PAY` rồi `PREVIEW` thay vì chỉ `PREVIEW`). Test `negativeCaseSelfInvocationSkipsAdvice` có thể cũng thất bại vì entry method `callPayInside()` nay bị advice ngay khi caller vào proxy; điều này không chứng minh self-invocation được sửa.

### Mutation B: bỏ điều kiện class và return type

Thay:

~~~java
@Before("paymentVoidMethod() && measuredMethod()")
~~~

bằng:

~~~java
@Before("measuredMethod()")
~~~

Khi đó `PaymentService.refund()` và `OtherService.pay()` (cùng annotated) cũng có thể kích hoạt advice. Hai negative tests tương ứng phát hiện việc mở rộng phạm vi.

### Mutation C: vô hiệu hóa auto-proxy

Bỏ `@EnableAspectJAutoProxy(proxyTargetClass = true)` khỏi `AopConfig` (với giả định project tối thiểu không có cấu hình AOP khác). `positiveCaseAnnotatedPublicVoidPaymentMatches` thất bại vì `AopUtils.isAopProxy(service)` không còn true và danh sách sự kiện không có `ADVICE_PAY`.

Mutation này kiểm tra **hạ tầng Spring AOP**, không phải chỉ tính đúng đắn cú pháp pointcut. Sau từng mutation hãy khôi phục file chuẩn rồi chạy lại toàn bộ `mvn clean test`.

### Mutation D: đổi `&&` thành `||`

Thay hai điều kiện AND bằng OR:

~~~java
@Before("paymentVoidMethod() || measuredMethod()")
~~~

Bây giờ các method chỉ thỏa A **hoặc** B cũng được advice; các negative tests về annotation/class/return type sẽ phát hiện được. Đây là ví dụ điển hình tại sao test chỉ một positive match **không bảo vệ được phạm vi** của pointcut.

Trong project team, có thể dùng mutation testing framework để tự động hóa nhưng không cần thêm tool cho bài này: tự sửa, chạy Maven và hoàn nguyên là đủ để thấy giá trị của ma trận test.

## 8. Tổ chức pointcut để dễ kiểm thử và tái sử dụng

Khi project lớn, một class `@Aspect` có thể sử dụng các named pointcut riêng:

~~~java
@Pointcut("within(demo..service..*)")
public void serviceLayer() {
}

@Pointcut("@annotation(demo.Measured)")
public void annotatedOperation() {
}

@Before("serviceLayer() && annotatedOperation()")
public void before() {
    // ...
}
~~~

Đây là **snippet minh họa đặt trong một `@Aspect`**, không phải thay thế chạy độc lập cho project test trên. Package `demo..service..*` cần sửa cho đúng package thực tế. Named pointcuts có phương thức `void` với thân rỗng; chúng là cách đặt tên và **kết hợp biểu thức**, không phải callback Java được caller gọi trực tiếp.

Nếu nhiều aspects cùng dùng pointcut, có thể chuyển các khai báo `@Pointcut` sang một class `public @Aspect` kiểu `CommonPointcuts`, rồi tham chiếu bằng tên đầy đủ:

~~~java
@Before("demo.CommonPointcuts.serviceLayer()"
      + " && demo.CommonPointcuts.annotatedOperation()")
public void before() {
    // ...
}
~~~

Đây là đoạn định hướng tổ chức code, **`demo.CommonPointcuts` không thuộc project ví dụ đã khai báo** nên chưa thể biên dịch riêng. Trong ứng dụng thật phải định nghĩa `CommonPointcuts`, đặt visibility phù hợp và bảo đảm biểu thức tham chiếu đúng FQCN.

Dù tái sử dụng pointcut, cần có **test âm của từng điều kiện**: một ràng buộc theo package, một ràng buộc theo annotation, một ràng buộc theo visibility/return type, v.v. Các test âm ngăn thay đổi không chủ ý làm pointcut quá rộng và giúp review code dễ dàng hơn.

## 9. Các nguồn gây false positive/false negative trong test Spring AOP

### 9.1. Chỉ nhìn `isAopProxy()`

`AopUtils.isAopProxy(service)` cho biết bean là một AOP proxy. **Nó không cho biết advice cụ thể của bạn đã khớp method nào**. Một bean có thể được proxy vì transaction, cache hoặc advisor khác. Hãy assert marker nằm **trong advice cần kiểm thử** và logic business target đúng thứ tự.

### 9.2. Dùng object `new` thay vì Spring bean

Nếu tạo:

~~~java
PaymentService service = new PaymentService(new EventLog());
service.pay();
~~~

đây là Java object thường, không chạy qua `AnnotationConfigApplicationContext` nên không được Spring auto-proxy. Khi test runtime aspect, phải lấy `context.getBean(PaymentService.class)` hoặc inject bean. Dùng `new` vẫn hữu ích làm **ca âm** nhưng không thể là phép thử dương cho advice Spring AOP.

### 9.3. Self-invocation

Từ một method đã vào target, lời gọi `this.pay()` bỏ qua proxy nên advice trên `pay()` không chạy. Điều này **không có nghĩa `pay()` không match pointcut**; nó chỉ cho thấy đường gọi Java nội bộ không đi qua interceptor. Muốn kiểm thử match, phải gọi trực tiếp `service.pay()` trên Spring bean proxy.

### 9.4. Lỗi đặt annotation trên interface/override

Java annotation trên method không tự “kế thừa” giống một method override. Khi project dùng interface-based JDK proxy, annotation có thể được đặt ở interface method hoặc implementation method. Cơ chế resolution của Spring/AspectJ có các chi tiết liên quan đến method cụ thể/bridge methods. Để test đáng tin, xác minh annotation **được Spring AOP nhận diện trong cấu hình proxy thật**; trong demo đặt `@Measured` trực tiếp trên implementation method để không tạo biến số.

### 9.5. Method không thể được chặn qua proxy

- Với JDK proxy, method cần được expose qua interface để caller thông thường gọi bằng interface type.
- Với CGLIB, class `final` không thể subclass; method `final` hoặc `private` không thể override để intercept theo cơ chế proxy lớp.
- Static method, constructor và field access không phải các method execution join point mà Spring AOP tự chặn tương tự method instance trên proxy.

Một static pointcut matcher có thể xem method metadata, nhưng nếu runtime không có đường gọi qua proxy thì không có advice. Đừng viết assertion chỉ dựa vào annotation mà bỏ qua điều kiện proxy.

### 9.6. Thứ tự advice khi nhiều aspects cùng match

Ví dụ chỉ có một `@Before` advice nên `["ADVICE_PAY", "PAY"]` là thứ tự dễ kiểm chứng. Trong hệ thống có nhiều advice/transaction advisors, cần cấu hình hoặc kiểm tra thứ tự bằng `@Order`/`Ordered` khi order là yêu cầu nghiệp vụ. Không assert thứ tự ngẫu nhiên của nhiều advisors nếu application chưa định nghĩa ordering.

### 9.7. Test rò rỉ trạng thái

Nếu dùng static counter trong aspect, test chạy chung JVM có thể ảnh hưởng nhau; nếu dùng singleton context được cache cho nhiều test, event list có thể còn dữ liệu từ test trước. Demo giải quyết bằng **mỗi test tạo một context riêng**. Với integration tests lớn, cân nhắc reset spy/recorder và quản lý context lifecycle rõ ràng; không dựa vào thứ tự chạy method của JUnit.

## 10. Mở rộng phạm vi test theo dự án thật

Khi dùng các pointcut tổ chức theo package/annotation/bean name, hãy lập ma trận gồm ba trục:

- **Vùng áp dụng:** service class đúng package, service class ngoài package, interface vs implementation, bean được quản lý vs raw object.
- **Dấu hiệu chọn:** annotation có/không có, tên method, visibility, kiểu trả về, argument type, bean name có/không khớp.
- **Đường gọi:** external caller qua proxy, self-invocation, method final/private, các advisor khác cùng áp dụng.

Đừng tạo test cho mọi tổ hợp vô nghĩa. Nên có ít nhất một ca dương cho mỗi nhánh dự kiến và **một ca âm riêng cho từng ràng buộc** dễ bị bỏ sót. Nếu pointcut chứa `A && B && C`, tối thiểu cân nhắc kiểm thử: `A∧B∧C` (match), `¬A∧B∧C`, `A∧¬B∧C`, `A∧B∧¬C` (không match), cùng một số ranh giới proxy quan trọng.

Ví dụ test cho biểu thức:

~~~text
execution(public * demo..service..*.*(..))
    &&
@annotation(demo.Measured)
    &&
bean(*Service)
~~~

Một matrix tốt sẽ có: đúng package + annotation + bean name; ngoài package; không có annotation; bean name khác; self-invocation; object tự new. Mỗi ca phải nêu **mong đợi trước khi chạy test**, không điều chỉnh expected để phù hợp ngẫu nhiên với kết quả.

Có thể dùng `@SpringJUnitConfig`/Spring TestContext để giảm công tạo context ở một ứng dụng nhiều bean, nhưng khi dùng context cache cần chú ý reset recorder. Trong bài tối thiểu này, `AnnotationConfigApplicationContext` là đủ và không đòi hỏi thêm dependency `spring-test`.

## 11. Checklist rà soát một bộ test pointcut

- [ ] Pointcut có tên, scope đủ rõ; các điều kiện được ghép đúng `&&`/`||`/`!`.
- [ ] Mỗi điều kiện độc lập có **ca không match**; có ít nhất một ca match toàn bộ.
- [ ] Test chạy trên **Spring-managed bean proxy** thay vì tự `new` object khi kiểm tra advice dương.
- [ ] `@Aspect` và target đều là bean của đúng `ApplicationContext`, AOP đã được bật.
- [ ] Test dương xác nhận marker advice thực sự xuất hiện, đúng **trước/sau** target theo loại advice, không chỉ `isAopProxy`.
- [ ] Test âm xác nhận **không có marker advice** nhưng business method vẫn chạy nếu cần.
- [ ] Đã kiểm tra trường hợp annotation/method đúng nhưng class/return type sai.
- [ ] Có đối chứng self-invocation và raw Java object khi chúng là rủi ro của ứng dụng.
- [ ] Test độc lập về state, không phụ thuộc thứ tự chạy hay log ngẫu nhiên.
- [ ] Kết quả Maven/Surefire ghi nhận tất cả tests pass; khi fail, tìm assertion hoặc exception gốc.
- [ ] Không đồng nhất static method matcher với advice runtime trên proxy.

## 12. Tài liệu Spring và JUnit để tham khảo

- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): named pointcut, expression composition và method execution join points.
- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `@Before` và cách tham chiếu pointcut trong advice.
- [Spring Framework 6.2 — Pointcut API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pointcuts.html): `AspectJExpressionPointcut` và static/dynamic matching.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxy và self-invocation.
- [Spring Framework 6.2 — Unit Testing](https://docs.spring.io/spring-framework/reference/6.2/testing/unit.html): phân biệt unit tests độc lập với Spring context và kiểm thử tích hợp.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/5.11.0/user-guide/): JUnit Jupiter `@Test` và assertion APIs.
