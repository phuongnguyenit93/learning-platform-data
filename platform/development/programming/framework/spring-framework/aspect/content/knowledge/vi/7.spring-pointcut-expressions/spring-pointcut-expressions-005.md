# Sử dụng @annotation để chọn phương thức mang annotation trong Spring AOP

## 1. Mục tiêu bài học

Trong ứng dụng Spring Framework, thay vì khớp tên method theo một quy ước cố định, ta có thể chủ động đánh dấu những **phương thức Spring bean** cần áp dụng cross-cutting logic bằng annotation và viết pointcut Spring AOP sử dụng `@annotation`.

Bài này trả lời cụ thể:

1. `@annotation(...)` chọn method execution nào trong Spring AOP và khác gì với `execution(...)` thuần túy?
2. Làm thế nào viết custom annotation `@Retention(RUNTIME)`, `@Target(METHOD)`, rồi dùng `@Before` chỉ chặn method được đánh dấu?
3. Làm thế nào **bind annotation instance vào advice** để đọc thuộc tính `value`/`tag` của annotation?
4. Có thể kết hợp `@annotation` với `execution` để giới hạn đúng package, class, tầng service không?
5. Vì sao cùng method có annotation vẫn không chạy advice khi gọi bằng `this.method()`, `new` object, hoặc method không thể intercept qua Spring proxy?
6. Làm thế nào quan sát và chẩn đoán kết quả bằng Spring AOP proxy và bộ đếm advice?

**Giới hạn phạm vi:** Đây là **Spring AOP trên Spring-managed beans**, sử dụng cú pháp `@AspectJ` nhưng thực thi bằng proxy JDK/CGLIB. Không nhầm với AspectJ bytecode weaving và không biến annotation thành interceptor JVM cho mọi object.

## 2. Hiểu `@annotation` trong ngữ cảnh Spring AOP

Spring AOP hỗ trợ pointcut designator `@annotation` để chọn **method execution mà method tương ứng có annotation được chỉ định**. Đây là một điều kiện khớp join point khi lời gọi **đi qua Spring AOP proxy**.

Ví dụ annotation:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedAction {
    String value();
}
~~~

Với method của Spring bean:

~~~java
@TrackedAction("checkout")
public void checkout() {
    // ...
}

public void preview() {
    // ...
}
~~~

Nếu cả hai lời gọi đều đi qua bean proxy và đủ điều kiện advice, chỉ `checkout()` khớp `@annotation(demo.TrackedAction)`; `preview()` không khớp chỉ vì nằm cùng class.

### Hai dạng sử dụng quan trọng

**Dạng chọn annotation theo tên kiểu:**

~~~java
@Before("@annotation(demo.TrackedAction)")
public void before() {
    System.out.println("Annotated method");
}
~~~

`demo.TrackedAction` là tên đầy đủ của **loại annotation**. Advice này chỉ cần biết phương thức được đánh dấu, không cần đọc thuộc tính của annotation.

**Dạng bind instance annotation vào tham số advice:**

~~~java
@Before(value = "@annotation(trackedAction)", argNames = "trackedAction")
public void before(TrackedAction trackedAction) {
    System.out.println(trackedAction.value());
}
~~~

Trong dạng này, `trackedAction` là **tên binding variable**, không phải tên class annotation. Spring suy ra kiểu `TrackedAction` từ tham số advice, bind đối tượng annotation phù hợp và cho phép đọc `trackedAction.value()`.

Đây là hai snippet minh họa cần đặt vào một `@Aspect` đã đăng ký làm Spring bean, không phải các chương trình Java đầy đủ. Không đặt **cả hai** advice vào cùng ví dụ nếu bạn chỉ muốn một dòng log: khi hai advice cùng khớp, cả hai đều có thể chạy.

Lưu ý cú pháp:

- `@annotation(demo.TrackedAction)`: khớp theo **loại annotation**.
- `@annotation(trackedAction)`: bind annotation theo **tên biến**; tên đó phải tương ứng tham số nhận annotation của advice (hoặc được Spring suy ra đúng).
- Có thể ghi `argNames = "trackedAction"` rõ ràng để tránh phụ thuộc tên tham số sau khi biên dịch. Khi advice có `JoinPoint` ở tham số **đầu**, không cần khai báo tên tham số `JoinPoint` trong `argNames`.
- Với điểm cắt đa điều kiện, dùng `&&` và `||` giống biểu thức pointcut AspectJ, ví dụ `execution(public * demo.AuditService.*(..)) && @annotation(trackedAction)`.

### `@annotation` khác `execution` như thế nào?

| Pointcut | Quy tắc khớp chính | Khi nên dùng |
| --- | --- | --- |
| `execution(* demo.AuditService.ship(..))` | Theo chữ ký/method execution | Áp dụng cho tên method hoặc nhóm method xác định |
| `execution(public * demo..service..*(..))` | Theo visibility, return type, package/type, method | Áp dụng thống nhất cho service layer |
| `@annotation(demo.TrackedAction)` | Theo method có annotation `@TrackedAction` | Chỉ áp dụng cho method được đánh dấu chủ động |
| `execution(* demo.AuditService.*(..)) && @annotation(demo.TrackedAction)` | Phải thỏa cả class/method scope và annotation | Giảm vùng xét/giảm match không mong muốn |
| `@annotation(trackedAction)` | Theo annotation và bind giá trị cho advice | Advice cần đọc annotation attribute để audit/log/tag |

`@annotation` không thay thế việc cần một **Spring AOP join point có thể chặn qua proxy**. Một method có annotation nhưng bị gọi trực tiếp trên target vẫn không tự chạy advice.

## 3. Tạo annotation đúng cách

Hai meta-annotation Java đặc biệt quan trọng:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedAction {
    String value();
}
~~~

- `@Retention(RetentionPolicy.RUNTIME)`: giữ annotation ở runtime để cơ chế AOP dùng metadata tại runtime. Nếu dùng `SOURCE` thì annotation biến mất sau compile; dùng `CLASS` không đảm bảo sẵn qua Java reflection runtime.
- `@Target(ElementType.METHOD)`: cho phép gắn vào **method** (không tự biến thành annotation cấp class/field/parameter).
- `String value()`: attribute bắt buộc. Khi viết `@TrackedAction("fulfillment")`, `"fulfillment"` là giá trị của `value`.
- Có thể thêm default như `String category() default "general";`. Nếu advice cần dùng attribute, bind annotation thay vì parse annotation bằng chuỗi.

**Không cần thêm `@Inherited`** cho bài này. `@Inherited` của Java chủ yếu có ý nghĩa đối với annotation trên **class**, không tự khiến annotation trên method của interface hoặc superclass được xem như annotation trực tiếp của mọi method override. Khi làm việc với interface method, overriding method hoặc composed/meta-annotation của Spring, cần kiểm tra cách Spring/AspectJ resolver thực sự xác định method annotation theo proxy type, không áp dụng giả định kế thừa tùy ý.

Và đừng nhầm `@TrackedAction` với `@Aspect`:

- `@TrackedAction` là annotation đánh dấu **method nghiệp vụ** để pointcut tìm.
- `@Aspect` đánh dấu **class chứa advice**, Spring chỉ tìm nó nếu class đó đã được **đăng ký thành Spring bean**.
- `@EnableAspectJAutoProxy` (hoặc auto-configuration tương ứng) bật hỗ trợ Spring AOP để advice thực thi qua proxy.

## 4. Ví dụ chạy được: hai method có annotation, một method không có

Dự án Maven nhỏ dưới đây sử dụng **Java 17+**, **Spring Framework 6.2.0** và **AspectJ Weaver 1.9.22**. Đây là Spring Framework thuần, không phụ thuộc Spring Boot và không dùng AspectJ compiler/agent.

Cấu trúc đầy đủ:

~~~text
spring-annotation-pointcut/
├── pom.xml
└── src/main/java/demo/
    ├── Demo.java
    ├── TrackedAction.java
    ├── AuditService.java
    └── TraceAspect.java
~~~

### 4.1. Cấu hình Maven

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-annotation-pointcut</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Demo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` tạo `ApplicationContext` và xử lý Java config; `spring-aop` cung cấp proxy/interceptor/`AopUtils`. `aspectjweaver` cung cấp thư viện dùng khi Spring diễn giải biểu thức pointcut/`@AspectJ`; **không có `-javaagent` ở đây**, vì runtime vẫn là Spring AOP dựa trên proxy.

`<parameters>true</parameters>` giúp javac giữ tên tham số để Spring có thể tra cứu khi cần. Ví dụ vẫn khai báo `argNames` rõ ràng để người học thấy chính xác binding variable nào được sử dụng.

### 4.2. File annotation có retention runtime

Tạo `src/main/java/demo/TrackedAction.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedAction {
    String value();
}
~~~

### 4.3. Service với method được/không được đánh dấu

Tạo `src/main/java/demo/AuditService.java`:

~~~java
package demo;

public class AuditService {
    @TrackedAction("fulfillment")
    public void ship(String orderId) {
        System.out.println("SERVICE: ship " + orderId);
    }

    public void ping() {
        System.out.println("SERVICE: ping");
    }

    @TrackedAction("account")
    public void adjust(String customerId) {
        System.out.println("SERVICE: adjust " + customerId);
    }

    public void callShipInside() {
        System.out.println("SERVICE: callShipInside");
        this.ship("A-101");
    }
}
~~~

Với `ship(...)` và `adjust(...)`, annotation ở **method triển khai** sẽ được `@annotation` nhận diện khi caller gọi qua proxy. `ping()` không gắn annotation nên không match. `callShipInside()` cũng không gắn annotation; bên trong nó gọi `this.ship(...)`, cho phép quan sát giới hạn **self-invocation** của Spring AOP proxy.

Các method đều `public` và class không `final`, để CGLIB class proxy có thể intercept chúng. Trong project tối thiểu, không cần `@Service` vì service sẽ được tạo bằng `@Bean` từ `Demo`.

### 4.4. Aspect bind giá trị annotation

Tạo `src/main/java/demo/TraceAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class TraceAspect {
    private final AtomicInteger adviceCount = new AtomicInteger();

    @Before(
        value = "execution(* demo.AuditService.*(..)) && @annotation(trackedAction)",
        argNames = "trackedAction"
    )
    public void before(JoinPoint point, TrackedAction trackedAction) {
        adviceCount.incrementAndGet();
        System.out.println(
            "ADVICE: tag=" + trackedAction.value()
            + " method=" + point.getSignature().getName()
        );
    }

    public int count() {
        return adviceCount.get();
    }
}
~~~

Phân tích chính xác cách advice khớp:

1. `execution(* demo.AuditService.*(..))` giới hạn các method execution trên `AuditService`. Đây là ràng buộc scope bổ sung, tránh annotation trùng tên ở class khác vô tình tham gia.
2. `@annotation(trackedAction)` chỉ chấp nhận method tương ứng có annotation có kiểu bind được vào tham số `TrackedAction trackedAction`.
3. `argNames = "trackedAction"` tường minh tên biến cần bind trong pointcut với tham số của advice. Tham số đầu `JoinPoint point` được Spring xử lý đặc biệt, nên không cần nằm trong `argNames`.
4. `trackedAction.value()` đọc attribute của **annotation gắn trên method đang được Spring AOP xét**. Ví dụ in `fulfillment` hoặc `account` mà không cần logic đọc annotation bằng reflection thủ công.
5. `point.getSignature().getName()` lấy tên method đang được advice ở join point. Trong ví dụ kết quả là `ship` hoặc `adjust`.
6. `adviceCount` chỉ tăng bên trong advice; dùng `AtomicInteger` để phép đo rõ ràng. Chương trình chỉ gọi tuần tự nên không cần giả lập nhiều thread.

Điểm dễ nhầm: `trackedAction` ở biểu thức pointcut **không phải** biến Java bên ngoài method; nó là tên binding dùng bởi Spring/AspectJ để truyền annotation instance vào method advice.

### 4.5. Bật AOP, đăng ký các bean và kiểm tra kết quả

Tạo `src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Demo {
    @Bean
    public AuditService auditService() {
        return new AuditService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Demo.class)) {
            AuditService service = context.getBean(AuditService.class);
            TraceAspect aspect = context.getBean(TraceAspect.class);

            boolean isProxy = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + isProxy);

            service.ship("A-100");
            service.ping();
            service.adjust("C-200");
            service.callShipInside();

            int count = aspect.count();
            System.out.println("ADVICE_COUNT: " + count);

            if (!isProxy || count != 2) {
                throw new IllegalStateException(
                    "Expected @annotation advice exactly twice");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Tại sao `@EnableAspectJAutoProxy(proxyTargetClass = true)` được dùng?

- Nó kích hoạt **Spring AOP auto-proxy**, cho phép Spring tạo subclass proxy cho `AuditService`, dù class không triển khai interface.
- Nó không tự kích hoạt toàn bộ mọi method; proxy/advisor vẫn xem xét method nào khớp pointcut.
- `@Bean auditService()` đăng ký service như một Spring-managed bean. `@Bean traceAspect()` đăng ký aspect; chỉ đặt `@Aspect` trên class mà không đăng ký bean sẽ không đủ.
- `context.getBean(AuditService.class)` trả Spring reference; nếu có advisor phù hợp, đây là proxy chứ không phải object tự `new` bên ngoài container.
- `service.callShipInside()` đi vào target method, rồi `this.ship("A-101")` là lời gọi **nội bộ trực tiếp**. Dù `ship` có annotation, lời gọi nội bộ bypass proxy nên `before` không chạy lần thứ ba.

### 4.6. Chạy Maven và stdout mong đợi

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do mã Java trong ví dụ in ra, theo đúng thứ tự:

~~~text
PROXY: true
ADVICE: tag=fulfillment method=ship
SERVICE: ship A-100
SERVICE: ping
ADVICE: tag=account method=adjust
SERVICE: adjust C-200
SERVICE: callShipInside
SERVICE: ship A-101
ADVICE_COUNT: 2
CHECK: PASS
~~~

Maven hoặc logger trong môi trường chạy có thể có thêm output. Mười dòng trên là các message `System.out.println` của ví dụ.

Diễn giải:

- `PROXY: true`: service bean đã được Spring AOP xử lý thành proxy.
- `ship("A-100")` có annotation `@TrackedAction("fulfillment")` và gọi qua proxy, nên advice in giá trị `fulfillment` trước business code.
- `ping()` không có `@TrackedAction`, do đó không có dòng `ADVICE` tương ứng.
- `adjust("C-200")` có annotation `@TrackedAction("account")`, advice được gọi và bind value `account`.
- `callShipInside()` không annotated. Lời gọi `this.ship("A-101")` vẫn thực thi mã service nhưng **không quay qua proxy**, nên không xuất hiện `ADVICE: tag=fulfillment` cho `A-101`.
- `ADVICE_COUNT: 2` xác minh advice thực sự chạy đúng hai lần trên những lời gọi qua proxy đã được đánh dấu.
- `CHECK: PASS` chỉ xuất hiện sau khi proxy tồn tại và count đúng bằng `2`.

Mục tiêu chính là chứng minh **cả điều kiện annotation và ranh giới Spring proxy**, tránh kết luận sai rằng `@annotation` can thiệp vào mọi lời gọi Java tới annotated method.

## 5. Tách scope và annotation bằng @Pointcut

Trong project thực tế, nhiều advice có thể dùng cùng một ràng buộc. Có thể đặt tên pointcut:

~~~java
@Pointcut("execution(public * demo.AuditService.*(..))")
public void auditServiceOperations() {
}

@Before(
    value = "auditServiceOperations() && @annotation(trackedAction)",
    argNames = "trackedAction"
)
public void before(JoinPoint jp, TrackedAction trackedAction) {
    System.out.println("Tracked: " + trackedAction.value());
}
~~~

Đây là **đoạn code trích để đặt bên trong một `@Aspect`**, không thêm nguyên xi vào `TraceAspect` khi nó đã có `before(...)` trùng nhiệm vụ. Cần import `org.aspectj.lang.annotation.Pointcut` và `Before`, `JoinPoint` cùng annotation `TrackedAction`. Method `auditServiceOperations()` chỉ mô tả pointcut; **nội dung method phải rỗng** và không chứa business logic.

Điểm lợi:

- `auditServiceOperations()` diễn tả **phạm vi của Spring service**; `@annotation(trackedAction)` thêm yêu cầu method có annotation.
- Có thể tái dùng named pointcut cho `@Before` hoặc `@Around` mà vẫn giữ code dễ đọc.
- Khi đổi package/class scope, sửa định nghĩa named pointcut thay vì lặp nhiều chuỗi biểu thức.
- Kết hợp scoping designator làm intent rõ ràng hơn, tránh pointcut `@annotation(...)` quá rộng khắp toàn application.

Nếu muốn áp dụng cho nhiều class service trong cùng package, thay ràng buộc `demo.AuditService.*(..)` bằng một `execution(...)` phù hợp package convention và test lại match trên bean thực tế. Không cố “sửa” annotation match bằng cách nới pointcut tới toàn JVM.

## 6. Phân biệt @annotation với các designator @-khác trong Spring

Spring AOP hỗ trợ một tập designator theo ngữ cảnh; phần tiền tố `@` không có nghĩa tất cả kiểm tra cùng một nơi:

| Designator | Ý nghĩa đối với method execution Spring AOP | Ví dụ mục đích |
| --- | --- | --- |
| `@annotation(X)` | Method ở join point có annotation kiểu `X` | Audit riêng các method được đánh dấu |
| `@within(X)` | Join point nằm trong kiểu class có annotation tương ứng | Chọn các method trong class được đánh dấu |
| `@target(X)` | Runtime target object có kiểu được đánh dấu bằng annotation đó | Chọn theo annotation trên loại đối tượng đích |
| `@args(X)` | Dựa vào annotation trên kiểu runtime của argument đi vào method | Trường hợp chọn theo metadata của object đầu vào |
| `execution(...)` | Chọn method execution theo chữ ký và phạm vi | Chọn service/package/method cần advice |
| `within(...)` | Giới hạn theo kiểu/phạm vi khai báo method | Thu hẹp phạm vi xét advisor |

Ví dụ, một class được đánh dấu:

~~~java
@TrackedService
public class OrderService {
    public void submit() {
    }
}
~~~

Nếu `@TrackedService` là annotation có `@Target(TYPE)` và `@Retention(RUNTIME)`, các biểu thức `@within(demo.TrackedService)` hoặc `@target(demo.TrackedService)` có ý nghĩa **khác** `@annotation(demo.TrackedService)`: một annotation chỉ đánh dấu **class** không tự xuất hiện trên từng method. Đoạn trên là ví dụ minh họa về annotation `@TrackedService` chưa định nghĩa trong project demo; không phải file chạy độc lập.

Tương tự, `@args` không kiểm tra annotation trên tham số khai báo của method; nó dựa trên **kiểu runtime của argument**. Khi chỉ cần đánh dấu một method nghiệp vụ để AOP xử lý, `@annotation` phù hợp và dễ kiểm soát hơn.

## 7. Những giới hạn quan trọng trong Spring AOP

### 7.1. Có annotation chưa đủ nếu không đi qua proxy

Một biểu thức pointcut chính xác vẫn không chạy trong các tình huống sau:

- Đối tượng được tạo bằng `new AuditService()` bên ngoài `ApplicationContext`.
- `@Aspect` class không được đăng ký làm Spring bean, hoặc `@EnableAspectJAutoProxy` chưa được bật trong context đang dùng.
- Caller gọi annotated method bằng `this.ship()` từ một method khác trên chính target (self-invocation).
- Method `private`/`final` không thể bị chặn theo cách class-based subclass proxy; `final` class không thể được CGLIB subclass.
- Pointcut scope `execution(...)` quá hẹp khiến method có annotation nằm ngoài phạm vi đã chỉ định.
- Bean bị khởi tạo ở giai đoạn quá sớm nên chưa được auto-proxy, hoặc lời gọi đi tới raw target thay vì Spring bean reference.

Đặc biệt, **`proxyTargetClass = true` không chữa self-invocation**. CGLIB vẫn là Spring proxy đứng ở ranh giới caller-target. Giải pháp ít phụ thuộc framework là tách method cần advice sang bean khác và gọi qua dependency được Spring inject.

### 7.2. Annotation trên interface và implementation

Trong Java, annotation cấp method không được kế thừa tự động như quan hệ interface/implementation. Với Spring AOP, match thực tế có thể bị ảnh hưởng bởi:

- JDK proxy hay CGLIB proxy;
- annotation đặt ở interface method, implementation method hoặc method override;
- cách Spring phân giải method cụ thể/bridge method của target;
- một số cơ chế meta-annotation/composed annotation đặc thù Spring.

**Khuyến nghị dễ kiểm chứng:** trong demo đơn giản, đặt annotation trực tiếp trên **implementation method** là join point mong muốn, như `AuditService.ship` và `AuditService.adjust`; viết integration test dùng proxy configuration thật nếu project cố ý đặt annotation ở interface hoặc base class. Không mặc định `@Inherited` sẽ tự làm annotation của interface method xuất hiện trên implementation method.

Nếu một thư viện sử dụng annotation chuyên biệt với Spring, đừng tự suy rằng `@annotation(...)` luôn tuân theo quy tắc tìm **merged/meta-annotations** giống tất cả Spring annotation utilities. AspectJ pointcut matching và Spring annotation discovery không hoàn toàn là cùng một API. Khi cần semantic “annotation trực tiếp hoặc meta-annotation”, hãy kiểm tra thực nghiệm và cân nhắc truy xuất metadata cụ thể bằng Spring utilities phù hợp thay vì chỉ đổi chuỗi pointcut.

### 7.3. @annotation không biến mọi annotation thành nghiệp vụ đặc biệt

`@TrackedAction` chỉ là dấu mốc của ứng dụng. Bản thân việc khai báo annotation không tự tạo log, transaction, validation hay security. Cần **aspect/advisor** phù hợp, Spring context quản lý target và proxy có thể chặn method.

Tương tự, nếu ứng dụng đã có `@Transactional` hoặc `@Cacheable`, các annotation đó hoạt động thông qua cơ chế hạ tầng Spring riêng khi đã được bật. Đừng nghĩ mọi annotation tự động được pointcut custom của mình nhận diện hoặc có cùng thứ tự advisor. Khi nhiều advice chạy trên một method, kiểm tra thứ tự bằng `@Order` hoặc cơ chế ordering tương ứng nếu logic cần sự nhất quán.

### 7.4. Có nên dùng @Around thay @Before?

`@Before` phù hợp nếu mục tiêu là audit hoặc ghi nhận metadata trước khi method chạy. Nếu cần đo thời gian thực thi/quan sát return value hay exception quanh lời gọi, có thể chọn `@Around` nhưng **phải gọi `proceed()`** khi muốn business method tiếp tục:

~~~java
@Around(
    value = "execution(* demo.AuditService.*(..)) && @annotation(trackedAction)",
    argNames = "trackedAction"
)
public Object around(
        ProceedingJoinPoint pjp, TrackedAction trackedAction) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long nanos = System.nanoTime() - started;
        System.out.println(trackedAction.value() + ": " + nanos + " ns");
    }
}
~~~

Đây là **đoạn minh họa thay advice** trong một `@Aspect`, cần import `org.aspectj.lang.ProceedingJoinPoint` và `org.aspectj.lang.annotation.Around`. Nó không phải program chạy độc lập và không nên đồng thời giữ cả `@Before` lẫn `@Around` nếu bạn đang kiểm tra một dòng advice duy nhất.

Chú ý `System.nanoTime()` đo elapsed duration tương đối, **không phải** timestamp tuyệt đối. Thời gian chạy và stdout số nanosecond biến thiên theo máy, vì vậy bài thực hành chính dùng `@Before` với output xác định.

## 8. Gỡ lỗi khi method có annotation mà advice không chạy

Một quy trình chẩn đoán thực tế:

1. **Xác nhận annotation có thể thấy ở runtime:** kiểm tra `@Retention(RUNTIME)` và `@Target(METHOD)`, placement chính xác trên method dự kiến. Một annotation cấp class không tự khớp `@annotation` method.
2. **Kiểm tra Spring bean:** method đang được gọi trên bean do `ApplicationContext` xuất ra hay object tự `new`? Aspect đã đăng ký thành bean và AOP đã bật chưa?
3. **Kiểm tra proxy:** dùng `AopUtils.isAopProxy(service)`, `isJdkDynamicProxy(service)` và `isCglibProxy(service)` trên **reference thực sự được caller sử dụng**.
4. **Đọc nguyên biểu thức pointcut:** `execution(...)` có khớp đúng package/class/method không, `@annotation(...)` là kiểu annotation hay tên binding variable?
5. **Kiểm tra advice binding:** khi dùng `@annotation(variable)`, method advice phải khai báo tham số có kiểu annotation phù hợp; nếu không dùng `-parameters` hoặc không thể suy tên tham số, khai báo `argNames` rõ ràng.
6. **Đo số lần và thứ tự chạy:** tăng counter bên trong advice, ghi marker riêng để biết advice chạy trước business method. Không chỉ dựa vào bean có proxy.
7. **Xem self-invocation và visibility:** `this.method()`, `private`, `final`, JDK vs CGLIB, hoặc method không được proxy expose có thể khiến advice không chạy.
8. **Kiểm tra annotation placement qua interface/override:** đặt annotation ở implementation để kiểm tra đối chứng; test lại với proxy strategy thực tế.
9. **Nếu nhiều context/auto-proxy creators:** đảm bảo aspect và target thuộc context đúng; cấu hình AOP thường có phạm vi theo `ApplicationContext`.
10. **Sau khi sửa:** chạy lại kiểm tra trong context hoàn chỉnh và xác nhận marker, counter, kết quả business method.

### Lỗi phổ biến với binding annotation

**Lỗi 1 — tưởng `@annotation(trackedAction)` là tên class**

~~~java
@Before("@annotation(trackedAction)")
public void before() {
    // Không có tham số annotation để bind như dự định
}
~~~

Trong trường hợp này, bạn dùng **tên binding** nhưng advice không khai báo biến `trackedAction` tương ứng. Hãy đổi thành `@annotation(demo.TrackedAction)` nếu chỉ cần match type, hoặc thêm tham số `TrackedAction trackedAction` như ví dụ đúng.

**Lỗi 2 — viết annotation không có `RUNTIME` retention**

~~~java
@Retention(RetentionPolicy.CLASS)
@Target(ElementType.METHOD)
public @interface TrackedAction {
    String value();
}
~~~

Đây là **ví dụ sai retention dành cho nhu cầu runtime matching**: `CLASS` không giữ annotation sẵn ở runtime theo cách yêu cầu. Đừng đưa đoạn này vào project hoạt động đồng thời với `TrackedAction` chuẩn.

**Lỗi 3 — method được đánh dấu nhưng nằm ngoài scope**

~~~java
@Before("execution(* demo.AuditService.ship(..)) && @annotation(demo.TrackedAction)")
public void before() {
}
~~~

Nếu bạn gắn `@TrackedAction` cho `adjust`, biểu thức này vẫn **không match `adjust`** vì nó chỉ chọn `ship`. Annotation matching và method-signature matching là quan hệ **AND** ở đây.

**Lỗi 4 — dùng proxy nhưng self-call**

~~~java
public void outer() {
    this.ship("A-101");
}
~~~

Khi `outer` được gọi trên Spring bean proxy, code bên trong target gọi `this.ship` sẽ đi thẳng tới target; đừng quy lỗi cho `@annotation`. Đây là một giới hạn của Spring proxy-based AOP.

## 9. Bài tập mở rộng thực hành

### Bài 1: Chọn ba method bằng một annotation

Thêm một method vào `AuditService`:

~~~java
@TrackedAction("refund")
public void refund(String orderId) {
    System.out.println("SERVICE: refund " + orderId);
}
~~~

Gọi `service.refund("R-300")` từ `Demo.main()` sau khi lấy bean proxy. Khi đó có thêm:

~~~text
ADVICE: tag=refund method=refund
SERVICE: refund R-300
~~~

Nếu vẫn gọi hai method annotated ban đầu đúng một lần và chỉ thêm một lời gọi `refund` qua proxy, `ADVICE_COUNT` phải là `3`. Nhớ sửa assertion `count != 2` thành `count != 3`; nếu không, check sẽ báo lỗi vì kỳ vọng cũ, không phải vì advice hỏng.

### Bài 2: Chỉ match annotation trong một service cụ thể

So sánh:

~~~java
@Before("@annotation(demo.TrackedAction)")
public void logAnnotated() {
}
~~~

và:

~~~java
@Before("execution(* demo.AuditService.*(..)) && @annotation(demo.TrackedAction)")
public void logServiceAnnotated() {
}
~~~

Hai đoạn là **hai lựa chọn minh họa**, không nên thêm đồng thời vào aspect demo với advice cũ nếu bạn muốn đếm từng join point một lần. Dạng đầu rộng hơn: chọn annotated method thuộc các Spring beans bất kỳ nếu interceptable; dạng sau chỉ chọn scope `AuditService`.

### Bài 3: Tách self-invocation sang bean khác

Đặt method annotated `ship` vào `ShippingService` là Spring bean, rồi để `AuditService` nhận `ShippingService` qua constructor injection; khi `AuditService` gọi `shippingService.ship("A-101")`, lời gọi qua dependency proxy có thể được advice. Trước khi kết luận, xác nhận Spring tạo bean và advisor match. Không sửa bằng cách gọi `new ShippingService()` bên trong target.

## 10. Checklist ghi nhớ

- [ ] Custom annotation dùng `@Retention(RUNTIME)` và `@Target(METHOD)`.
- [ ] Class có `@Aspect` đã được đăng ký như một **Spring bean**.
- [ ] Context đã bật Spring AOP bằng `@EnableAspectJAutoProxy` (hoặc auto-configuration tương đương).
- [ ] Target service cũng là Spring bean; caller gọi method qua proxy.
- [ ] `@annotation(demo.TrackedAction)` là **chọn loại**; `@annotation(trackedAction)` là **bind instance**.
- [ ] Khi binding, tham số advice có kiểu `TrackedAction` phù hợp và tên binding được xác định bằng `argNames` hoặc thông tin tham số compile-time.
- [ ] Pointcut scope `execution(...)` không vô tình loại method annotated mong muốn.
- [ ] Method không phải `private`/`final` không interceptable theo proxy đang dùng; không có self-invocation bỏ qua proxy.
- [ ] Đã xác minh cả proxy status và số lần advice chạy, không chỉ dựa vào sự tồn tại annotation.

## 11. Tài liệu Spring Framework

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `@annotation` trong các pointcut designators mà Spring AOP hỗ trợ.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): binding annotation instance, `argNames`, `@Before` và `@Around`.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy` và cách Spring đăng ký aspect.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): lời gọi đi qua proxy, self-invocation và giới hạn JDK/CGLIB.
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring dùng kiểu khai báo `@AspectJ` nhưng vẫn là Spring proxy-based AOP.
