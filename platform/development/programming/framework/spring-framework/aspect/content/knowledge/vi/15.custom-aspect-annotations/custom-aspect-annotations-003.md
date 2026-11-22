# Ràng buộc giá trị annotation vào advice trong Spring AOP

## 1. Vấn đề cần giải quyết

Trong Spring AOP, một annotation tùy chỉnh có thể vừa đánh dấu phương thức cần được chặn, vừa cung cấp **cấu hình riêng cho từng phương thức**. Ví dụ, với các phương thức trong Spring service, ta muốn một aspect ghi log theo tên nghiệp vụ, độ ưu tiên hoặc quy tắc che thông tin do annotation khai báo:

~~~java
@TrackOperation(action = "order.create", sensitive = false)
public String create(String orderId) {
    return "created: " + orderId;
}
~~~

Một advice nên nhận trực tiếp đối tượng TrackOperation để gọi action() và sensitive(). Nhờ vậy, không cần viết một aspect khác cho từng action hay hard-code tên method trong advice.

**Phạm vi:** Cách Spring diễn giải biểu thức pointcut kiểu @AspectJ, liên kết đối tượng annotation với tham số advice, và các ranh giới khi Spring gọi bean qua AOP proxy. Kiến thức Java annotation/AOP chung chỉ được dùng ở mức cần thiết để triển khai chính xác trong Spring.

## 2. Hai nghĩa của @annotation: chọn phương thức và ràng buộc giá trị

Spring AOP hỗ trợ pointcut designator @annotation để khớp phương thức được gọi qua Spring proxy mà phương thức đó mang annotation chỉ định. Có hai cách thể hiện khác nhau:

**Chỉ lọc bằng tên kiểu annotation:**

~~~java
@Before("@annotation(demo.TrackOperation)")
public void beforeAnyTrackedMethod() {
    // Chạy khi phương thức được advice khớp với TrackOperation.
    // Không nhận đối tượng annotation trong tham số advice.
}
~~~

**Ràng buộc annotation vào tham số advice:**

~~~java
@Before(value = "@annotation(track)", argNames = "track")
public void beforeTrackedMethod(TrackOperation track) {
    System.out.println(track.action());
    System.out.println(track.sensitive());
}
~~~

Trong trường hợp thứ hai:

1. track trong chuỗi "@annotation(track)" là **tên biến binding**, không phải class name.
2. TrackOperation là kiểu Java thực tế của tham số advice. Spring/AspectJ expression xác định kiểu cần khớp và truyền annotation đã match vào tham số ấy.
3. argNames = "track" khai báo rõ tên biến trong biểu thức trùng với tham số advice; điều này giúp hoạt động ổn định khi biên dịch không giữ tên tham số Java.
4. action() và sensitive() lấy giá trị **khai báo tại method được gọi**, không phải giá trị tự đọc từ argument nghiệp vụ của method đó.
5. Các attribute annotation được khai báo bằng giá trị hợp lệ tại thời điểm biên dịch; advice nhận cấu hình metadata đó vào lúc Spring chặn lời gọi tương ứng.

Không dùng biểu thức "@annotation(demo.TrackOperation)" mà kỳ vọng Spring tự truyền TrackOperation vào một tham số không có binding. Muốn nhận object, cần dùng dạng tên biến và một tham số tương ứng.

## 3. Định nghĩa custom annotation phù hợp cho Spring proxy

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackOperation {
    String action();
    boolean sensitive() default false;
}
~~~

Trong ứng dụng, annotation ở trên đặt trên phương thức được Spring AOP proxy chặn:

~~~java
@Service
public class OrderService {
    @TrackOperation(action = "order.create")
    public String create(String id) {
        return "created: " + id;
    }

    @TrackOperation(action = "order.cancel", sensitive = true)
    public void cancel(String id) {
        // Xử lý nghiệp vụ
    }
}
~~~

- RetentionPolicy.RUNTIME là điều kiện quan trọng để annotation hiện diện tại runtime cho Spring AOP và các cơ chế reflection/annotation resolution.
- Target(METHOD) khẳng định bài toán là annotation ở **phương thức**. Nếu annotation đặt lên class, cần cân nhắc designator @within hoặc @target theo mục tiêu thay vì chờ @annotation match class.
- Trường action() bắt buộc tại điểm sử dụng; sensitive() có default nên có thể bỏ qua.
- Spring chỉ áp dụng advice cho các invocation **đi qua bean proxy** được cấu hình. Đánh dấu method không làm cho mọi lời gọi Java trực tiếp hoặc self-invocation tự động được chặn.

## 4. Ví dụ chạy được: binding TrackOperation trong @Around

Ví dụ dưới đây dùng **Java 17, Spring Framework 6.1.15 và Maven**. Nó cho thấy chính giá trị annotation của phương thức create/cancel được truyền vào một advice duy nhất, còn phương thức preview không có annotation sẽ không bị chặn.

Cấu trúc thư mục:

~~~text
spring-annotation-binding/
├── pom.xml
└── src/main/java/demo/
    ├── Application.java
    ├── TrackOperation.java
    ├── OrderService.java
    └── TrackingAspect.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-annotation-binding</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                    <mainClass>demo.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/TrackOperation.java**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackOperation {
    String action();
    boolean sensitive() default false;
}
~~~

**src/main/java/demo/OrderService.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    @TrackOperation(action = "order.create")
    public String create(String orderId) {
        return "created: " + orderId;
    }

    public String preview(String orderId) {
        return "untracked: " + orderId;
    }

    @TrackOperation(action = "order.cancel", sensitive = true)
    public String cancel(String orderId) {
        throw new IllegalStateException("cancelled");
    }
}
~~~

**src/main/java/demo/TrackingAspect.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TrackingAspect {

    @Around(value = "@annotation(track)", argNames = "track")
    public Object around(ProceedingJoinPoint joinPoint, TrackOperation track)
            throws Throwable {
        // Spring bind annotation của đúng method vào track.
        String action = track.action();
        boolean sensitive = track.sensitive();

        System.out.println("trace.enter: " + action
                + ", sensitive=" + sensitive);

        try {
            Object result = joinPoint.proceed();
            System.out.println("trace.success: " + action);
            return result;
        } catch (Throwable error) {
            System.out.println("trace.error: " + action
                    + ", " + error.getClass().getSimpleName());
            throw error;
        }
    }
}
~~~

**src/main/java/demo/Application.java**

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan("demo")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Application {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Application.class)) {
            OrderService service = context.getBean(OrderService.class);

            System.out.println(service.create("O-42"));
            System.out.println(service.preview("O-42"));

            try {
                service.cancel("O-42");
            } catch (IllegalStateException error) {
                System.out.println("caught: " + error.getMessage());
            }
        }
    }
}
~~~

Tại thư mục có pom.xml, chạy:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chương trình tự in theo thứ tự:

~~~text
trace.enter: order.create, sensitive=false
trace.success: order.create
created: O-42
untracked: O-42
trace.enter: order.cancel, sensitive=true
trace.error: order.cancel, IllegalStateException
caught: cancelled
~~~

Lệnh Maven có thể in thêm thông báo do môi trường Maven hoặc Spring Logging; các dòng chương trình nêu trên là kết quả logic dự kiến.

Giải thích:

- @EnableAspectJAutoProxy bật xử lý proxy-based @AspectJ của Spring. aspectjweaver cung cấp các API cần thiết để Spring phân tích AspectJ pointcut expression; ví dụ không dùng compile-time weaving.
- @ComponentScan đăng ký OrderService và TrackingAspect trong Spring context. Lời gọi context.getBean(...) lấy đối tượng có thể đã được Spring proxy.
- create và cancel có cùng loại annotation nhưng **giá trị action và sensitive khác nhau**. Tại mỗi join point, Spring truyền đối tượng TrackOperation tương ứng vào track.
- preview không mang TrackOperation nên không có log trace.
- Advice gọi proceed() **một lần** và trả nguyên kết quả, hoặc ném lại Throwable. Việc log lỗi không biến lỗi ứng dụng thành thành công.
- Tham số ProceedingJoinPoint đứng đầu signature advice được **bỏ qua trong chuỗi argNames** theo quy tắc binding của Spring. Vì thế argNames chỉ ghi "track".
- Compiler được cấu hình giữ parameter names, nhưng ví dụ vẫn dùng argNames tường minh để thể hiện chính xác mối liên hệ với pointcut.

## 5. Cách Spring ánh xạ tên binding vào tham số advice

Cấu trúc nguyên tắc:

~~~text
Pointcut expression:  @annotation(track)
                                  │
                                  │ bind object của annotation được match
                                  ▼
Advice parameter:     TrackOperation track
                                  │
                                  ├── track.action()
                                  └── track.sensitive()
~~~

Các tên binding thuộc **không gian tên của pointcut/advice**. Có thể chọn bất kỳ tên Java hợp lệ nào, miễn khớp nhất quán. Ví dụ muốn dùng tên policy:

~~~java
@Around(value = "@annotation(policy)", argNames = "policy")
public Object intercept(ProceedingJoinPoint pjp, TrackOperation policy)
        throws Throwable {
    System.out.println(policy.action());
    return pjp.proceed();
}
~~~

Về cách xác định tên tham số, Spring có thể dùng thông tin argNames, tên parameter lưu trong bytecode khi biên dịch với javac -parameters, hoặc cơ chế suy luận tên từ biểu thức pointcut theo tài liệu Spring. Nếu binding phức tạp, nên khai báo argNames rõ ràng để tránh lỗi "ambiguous binding", "argument names not available" hoặc binding vào sai tham số. Khi khai báo argNames và advice nhận JoinPoint/ProceedingJoinPoint ở tham số đầu tiên, thông thường không cần liệt kê tham số join point đó.

**Lỗi thường gặp: sai tên binding**

~~~java
// Sai: biến "track" trong pointcut không khớp argNames="label".
@Before(value = "@annotation(track)", argNames = "label")
public void wrong(TrackOperation label) {
    // Có thể lỗi xác định/bind tham số khi tạo advisor.
}
~~~

Sửa: dùng cùng một tên ở pointcut expression, argNames và signature Java.

### Ràng buộc nhiều đối tượng cùng lúc

Spring cho phép kết hợp annotation binding và method-argument binding. Ví dụ minh họa dưới đây giả định method phù hợp có đối số đầu là String:

~~~java
@Before(
    value = "@annotation(track) && args(orderId,..)",
    argNames = "track,orderId"
)
public void beforeWithArgument(TrackOperation track, String orderId) {
    System.out.println("action=" + track.action()
            + ", orderId=" + orderId);
}
~~~

- @annotation(track): lấy metadata của **phương thức**.
- args(orderId,..): match và bind **giá trị tham số nghiệp vụ đầu tiên** của lời gọi, theo kiểu dữ liệu được khai báo ở advice; .. cho phép thêm các đối số phía sau.
- Nếu method không có đối số đầu kiểu phù hợp thì điểm thực thi không match expression kết hợp.
- Không đọc orderId để thay thế track.action(): đây là hai nguồn dữ liệu khác nhau. Với thông tin nhạy cảm, cân nhắc track.sensitive() trước khi đưa arguments vào log.

Binding cũng có thể kết hợp với target(...) hoặc kiểu returned value/exception trong các advice tương ứng; mỗi biến bổ sung cần có tham số/điều kiện khớp đúng.

## 6. Tách @Pointcut để tái sử dụng annotation binding

Khi nhiều advice cùng dùng một điều kiện, có thể đặt tên pointcut. Đối tượng annotation **vẫn phải được khai báo như tham số của method @Pointcut**, rồi truyền tới advice gọi pointcut đó.

~~~java
@Aspect
@Component
public class ReusableTrackingAspect {

    @Pointcut(value = "@annotation(track)", argNames = "track")
    public void methodsWithTracking(TrackOperation track) {
        // Method này chỉ khai báo pointcut, không chứa nghiệp vụ.
    }

    @Before(value = "methodsWithTracking(track)", argNames = "track")
    public void before(TrackOperation track) {
        System.out.println("start: " + track.action());
    }

    @AfterReturning(
        value = "methodsWithTracking(track)",
        argNames = "track"
    )
    public void afterSuccess(TrackOperation track) {
        System.out.println("returned: " + track.action());
    }
}
~~~

Đoạn trên là **biến thể độc lập để minh họa**, không thêm đồng thời vào ví dụ ở mục 4 nếu không muốn log từ nhiều aspect chồng lên nhau.

Một điểm quan trọng: @AfterReturning chạy khi Java method trả bình thường; nó không tự đảm bảo nghiệp vụ bất đồng bộ chứa trong Future/Publisher đã hoàn tất. Nếu method trả đối tượng xử lý async, cần thêm cách quan sát phù hợp với kiểu trả về. Mục đích ở đây là minh họa việc đối tượng TrackOperation đã ràng buộc được chuyển qua named pointcut tới từng advice.

Có thể kết hợp vùng package/service để hạn chế số join point:

~~~java
@Pointcut(
    value = "within(demo..*) && @annotation(track)",
    argNames = "track"
)
public void trackedInDemo(TrackOperation track) {}
~~~

within(...) giới hạn nơi phương thức được khai báo/chạy theo biểu thức kiểu, còn @annotation(track) vừa lọc method vừa bind annotation. Việc thu hẹp phạm vi hữu ích nếu nhiều module sử dụng trùng annotation hoặc ứng dụng có nhiều bean.

## 7. So sánh các designator liên quan trong Spring

| Designator | Đối tượng được xét | Khi dùng |
| --- | --- | --- |
| @annotation(track) | Annotation gắn với method thực thi mà Spring AOP match | Bind cấu hình cho từng method vào advice |
| @annotation(demo.TrackOperation) | Kiểu annotation trên method, không khai báo biến binding | Chỉ cần lọc method |
| @within(trackType) | Annotation trên kiểu khai báo method được chặn | Áp dụng cấu hình theo class/kiểu |
| @target(trackType) | Annotation trên class runtime của đối tượng target | Áp dụng cấu hình theo target |
| @args(marker) | Annotation trên **kiểu runtime của argument** | Ràng buộc annotation kiểu của đối số, không phải annotation method |
| args(orderId,..) | Giá trị đối số khi gọi method | Bind dữ liệu input nghiệp vụ, có thể kết hợp @annotation |

Mỗi designator có quy tắc match khác nhau. Nếu annotation đặt ở class mà advice chỉ có @annotation(methodTag), không nên kỳ vọng annotation class tự nhiên trở thành methodTag. Tương tự, @args không lấy annotation trực tiếp từ method.

Một nhu cầu phổ biến: cấu hình class là mặc định, còn annotation ở method ưu tiên ghi đè. **Việc kết hợp và quyết định ưu tiên này là logic Spring aspect do ứng dụng tự thiết kế**, không tự xuất hiện chỉ vì đã viết @annotation. Có thể cân nhắc annotation lookup bằng tiện ích Spring (AopUtils, AnnotatedElementUtils) khi thật sự cần kết hợp annotation metadata, sau khi xác định join point và semantics mong muốn.

## 8. Ranh giới annotation metadata với Spring AOP proxy

### 8.1. Bean phải đi qua Spring proxy

~~~java
@Service
public class OrderFacade {
    @Autowired
    private OrderService service;

    public void externalCall() {
        service.create("O-1"); // Qua bean proxy; có thể chạy advice.
    }
}
~~~

Ngược lại, bên trong cùng một bean:

~~~java
@Service
public class InternalService {
    public void outer() {
        inner(); // this.inner(): lời gọi nội bộ bypass proxy.
    }

    @TrackOperation(action = "internal.inner")
    public void inner() {}
}
~~~

Nếu chỉ gọi outer() từ bên ngoài, inner() được gọi trực tiếp trên this nên advice target inner() thường không chạy trong Spring proxy mode. Hãy đặt ranh giới can thiệp ở lời gọi qua Spring-managed bean thích hợp hoặc cấu trúc lại service. Bản thân annotation không khắc phục self-invocation.

### 8.2. Vị trí annotation ở interface và implementation

Spring có thể tạo **JDK dynamic proxy** cho bean có interface hoặc **class-based proxy**. Kiểu proxy và phương thức thực tế được resolve có thể ảnh hưởng việc annotation có được nhìn thấy/match khi cấu hình đặt annotation ở interface, implementation, hoặc method được override.

Quy ước dễ kiểm tra là đặt annotation **trực tiếp trên method thực thi của Spring service**, như OrderService trong ví dụ, và viết integration test gọi qua đúng bean proxy mà production sử dụng. Nếu project cần annotation trên interface, hãy kiểm tra cụ thể hành vi khi đổi proxyTargetClass, inheritance và bridge methods; đừng giả định method annotation được Java kế thừa tự động. @Inherited của Java chỉ dành cho kế thừa annotation ở type, không giải quyết chung method annotation trên interface/override.

### 8.3. Phạm vi method có thể được advice

Spring AOP proxy hỗ trợ method execution join point thông qua bean proxy; nó không tự chặn constructor, field access, lời gọi đến đối tượng được new thủ công, hoặc bất kỳ gọi nào không qua proxy. Final class/final method có hạn chế đáng kể đối với class-based proxy. Các visibility và cấu hình proxy cụ thể cũng quyết định khả năng advice; không dựa vào method private như một join point thường gặp.

Với method overloaded cùng tên, metadata annotation của **đúng method** cần được match; không tự lấy annotation của method chỉ dựa trên tên method.

### 8.4. Retention và composed annotation

Thiếu @Retention(RUNTIME) có thể khiến advice không thấy annotation tại runtime. Với custom composed/meta-annotation (annotation A gắn trên annotation B), Spring có hệ thống merged annotation riêng phục vụ nhiều feature như @Transactional. Tuy nhiên, không mặc định suy rằng mọi tổ hợp meta-annotation sẽ bind bằng @annotation(track) giống annotation gắn trực tiếp trong mọi cấu hình/version. Khi cần semantics composed annotation, xác định rõ cơ chế matching và kiểm thử; nếu chỉ cần binding trực tiếp, khai báo annotation ngay trên method là đơn giản nhất.

## 9. Khi nào nên dùng @Before, @Around, @AfterReturning, @AfterThrowing?

Chỉ cần **đọc cấu hình từ annotation rồi log/kiểm tra điều kiện trước khi chạy**: @Before có parameter binding thường là đủ.

Cần đo thời gian đồng bộ, tự điều khiển proceed(), ghi nhận kết quả, hoặc chặn lời gọi theo chính sách được annotation mô tả: dùng @Around, nhưng phải xác định rõ liệu short-circuit, đổi arguments, đổi return value có nằm trong hợp đồng dịch vụ không. Advice @Around là thành phần mạnh, dễ gây thay đổi nghiệp vụ nếu quên gọi proceed() hoặc gọi nhiều lần.

Cần nhận annotation cùng giá trị trả về khi **method trả bình thường**:

~~~java
@AfterReturning(
    value = "@annotation(track)",
    returning = "result",
    argNames = "track,result"
)
public void afterReturn(TrackOperation track, Object result) {
    System.out.println(track.action() + ": " + result);
}
~~~

returning="result" bind **giá trị trả về của method**, khác với @annotation(track) bind **metadata annotation**. Nếu dùng tham số returning kiểu cụ thể (ví dụ String thay Object), Spring có thể giới hạn những method join point có giá trị trả về phù hợp với kiểu ấy.

Cần nhận annotation và lỗi được ném tại method invocation:

~~~java
@AfterThrowing(
    value = "@annotation(track)",
    throwing = "error",
    argNames = "track,error"
)
public void afterError(TrackOperation track, Throwable error) {
    System.out.println(track.action() + ": " + error.getClass().getSimpleName());
}
~~~

throwing="error" bind exception tương ứng, không thay cho annotation binding. Nếu method trả Mono/Future bình thường nhưng đối tượng async phát lỗi về sau, advice @AfterThrowing này không tự quan sát tín hiệu async. Cách xử lý phụ thuộc kiểu API thực tế, không coi annotation binding là cơ chế quan sát mọi vòng đời.

**Không đặt nhiều advice có side effect trùng nhau** chỉ để nhận cùng annotation nếu không cần. Nếu có nhiều aspects liên quan (ví dụ security/metrics/transaction), thứ tự advisor có thể làm thay đổi ngữ nghĩa trước/sau; dùng @Order và kiểm thử khi thứ tự thực sự quan trọng.

## 10. Thiết kế giá trị annotation: metadata của chính sách, không phải state toàn cục

Annotation phù hợp để lưu metadata tĩnh tại method, ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AuditPolicy {
    String event();
    Level level() default Level.INFO;
    boolean includeResult() default false;

    enum Level { INFO, WARN }
}
~~~

Đoạn khai báo này độc lập với ví dụ TrackOperation ở trên. Spring advice có thể bind AuditPolicy để chọn mức log hoặc loại sự kiện:

~~~java
@Before(value = "@annotation(policy)", argNames = "policy")
public void onAuditPolicy(AuditPolicy policy) {
    System.out.println(policy.event() + " at " + policy.level());
}
~~~

Các giá trị action/event/level là cấu hình tại method được match. Chúng không thay đổi riêng theo từng invocation dựa vào request. Khi cần dữ liệu runtime (userId, orderId, tenant, correlation id), cần lấy từ đối số method, security context hoặc ngữ cảnh xử lý tương ứng; có thể kết hợp với annotation metadata, nhưng không nhét dữ liệu request vào một field mutable trong singleton @Aspect.

Ví dụ về chia sẻ trạng thái dễ sai:

~~~java
@Aspect
@Component
class WrongAspect {
    private String currentAction; // Sai: field mutable dùng chung giữa requests.

    @Before(value = "@annotation(track)", argNames = "track")
    public void before(TrackOperation track) {
        currentAction = track.action();
    }
}
~~~

Với nhiều thread xử lý song song, currentAction bị ghi đè dẫn đến log/correlation sai. Thay bằng biến cục bộ trong mỗi advice invocation; nếu cần shared counters, dùng cơ chế concurrency-safe phù hợp. Đối tượng annotation được bind là metadata của method; lưu nó vào field currentAction để "ghi nhớ" request hiện tại là không cần thiết.

Nếu advice thực thi chính sách thực tế (ủy quyền, kiểm soát dữ liệu), không coi annotation là bằng chứng rằng người dùng được cấp quyền; kiểm tra danh tính/quyền qua thành phần Spring Security hay policy service đã được cấu hình. Annotation chỉ mô tả quy tắc cần áp dụng.

## 11. Chẩn đoán lỗi binding trong ứng dụng Spring

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và sửa |
| --- | --- | --- |
| Advice không chạy dù method có annotation | Bean không qua proxy, self-invocation, @EnableAspectJAutoProxy chưa hoạt động, annotation đặt ở vị trí khác | Lấy bean từ ApplicationContext, kiểm tra loại proxy và method thực thi |
| Spring báo lỗi không xác định được tham số binding | Tên trong pointcut/argNames/signature khác nhau, thiếu -parameters khi cần | Thêm argNames tường minh, kiểm tra tham số nhận đúng loại annotation |
| Annotation trong advice là null hoặc không match | Annotation không có RUNTIME, method/class/interface annotation resolution khác giả định | Dùng @Retention(RUNTIME), đặt trực tiếp trên method thử nghiệm, kiểm thử proxy thật |
| Dùng @annotation(demo.TrackOperation) nhưng muốn đọc action() | Biểu thức chỉ lọc type, không có biến binding | Dùng @annotation(track) với tham số TrackOperation track |
| @Around chạy nhưng nghiệp vụ không chạy | Quên gọi proceed() | Gọi proceed() đúng một lần trừ khi cố ý short-circuit theo hợp đồng |
| Method thực thi nhưng kiểu trả về sai | Advice trả object khác kiểu mong đợi hoặc không trả kết quả proceed() | Giữ return contract, không tự biến String thành Mono hay ngược lại |
| Advice ghi sai orderId trong nhiều request | Dùng field mutable trong singleton aspect | Dùng local variables và cơ chế context/counter an toàn |
| Không chặn method override hoặc interface method | Khác biệt method annotation lookup/proxy strategy | Test với JDK/class proxy thực tế; xác định nơi annotation cần đặt |
| Method lỗi nhưng @AfterReturning vẫn chạy | Method trả một Future/Publisher, lỗi xảy ra sau lần trả đồng bộ | Phân biệt return của Java method với kết quả bất đồng bộ |
| Chỉ muốn filter nhưng vô tình bind sai type | Dùng tên biến, advice nhận sai annotation class | Kiểm tra type, expression và signature thống nhất |

### Kiểm thử tối thiểu

Dùng Spring integration test (khởi tạo ApplicationContext hoặc @SpringJUnitConfig / @SpringBootTest tùy ứng dụng) và **lấy service từ context**, không tự new service. Kiểm thử:

1. Hai methods dùng cùng TrackOperation nhưng có action/sensitive khác nhau: advice nhận **đúng từng giá trị**, không dùng nhầm giá trị method khác.
2. Method không gắn annotation: không bị advice này chặn.
3. Advice @Around trả nguyên String và giữ nguyên exception từ target.
4. Gọi qua self-invocation: xác nhận giới hạn của Spring proxy, hoặc thiết kế service boundary khác.
5. Chạy song song nhiều method annotated: giá trị bind không bị chéo giữa các invocation.
6. Nếu sử dụng interface, overload, composed annotation hoặc nhiều advisors, kiểm thử đúng cấu hình proxy và thứ tự advisor sẽ chạy ở production.

Các test có thể thu nhận invocation bằng spy/collector an toàn thread thay vì so sánh println khi concurrency không bảo đảm thứ tự.

## 12. Quy trình áp dụng nhanh

1. Xác định custom annotation mang metadata nào và đặt retention RUNTIME; chọn METHOD khi cấu hình cho từng method.
2. Gắn annotation lên đúng method trong Spring bean; xác minh người gọi thực sự qua proxy.
3. Viết pointcut "@annotation(variable)" với advice parameter có type là annotation tương ứng.
4. Khai báo argNames trùng variable (bỏ tham số JoinPoint đầu tiên khỏi argNames nếu áp dụng).
5. Đọc attribute của annotation trong advice; lưu dữ liệu mỗi invocation bằng local, không gán vào shared mutable fields.
6. Chọn loại advice và bảo toàn proceed()/return/exception theo hợp đồng.
7. Kiểm thử annotation value theo nhiều methods, method không annotate, lỗi, proxy strategy và concurrency.

Điểm mấu chốt trong Spring: **@annotation(variable) vừa nhận diện method được Spring AOP proxy chặn, vừa ràng buộc đúng instance annotation vào tham số có tên tương ứng của advice**. Một aspect có thể xử lý nhiều methods với cấu hình khác nhau được khai báo ngay tại các annotation, trong khi Spring giữ nguyên cơ chế proxy và thời điểm method execution.

Tài liệu tham khảo chính thức:
- Spring Framework, Declaring a Pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework, Declaring Advice (Passing Parameters to Advice / Explicit Argument Names): https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework, @AspectJ support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
