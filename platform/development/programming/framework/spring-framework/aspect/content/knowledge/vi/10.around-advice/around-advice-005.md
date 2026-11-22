# proceed(Object[]) và thay đổi đối số theo quy ước Spring AOP

## 1. Mục tiêu bài học

Trong Spring AOP, advice `@Around` nhận một `ProceedingJoinPoint` và có quyền quyết định **khi nào, với đối số nào, bao nhiêu lần** method đích thực sự chạy. Phần này tập trung vào hai cách tiếp tục lời gọi:

- **`pjp.proceed()`:** chuyển tiếp đến chuỗi interceptor/method đích với **các đối số hiện có của lời gọi**. Khi chưa có advice trước đó thay đổi chúng, đó là các đối số mà caller ban đầu truyền vào.
- **`pjp.proceed(Object[] arguments)`:** tiếp tục lời gọi với **mảng đối số thay thế**, mỗi phần tử ứng với **một tham số của method đang được advice**, **cùng vị trí và thứ tự**.

Quy ước thứ hai là điểm cực kỳ quan trọng: **trong Spring AOP, mảng truyền cho `proceed(Object[])` đại diện cho argument list của method đích, không phải danh sách tham số của method advice**. Nếu method đích nhận hai tham số thì mảng mới phải cung cấp hai giá trị, kể cả khi method advice chỉ bind một trong hai tham số đó.

Bài này tập trung vào Spring Framework và Spring Aspect, không trình bày lại đầy đủ AspectJ weaving. Ta sẽ xây dựng project Maven Java 17+ chạy qua Spring bean proxy, quan sát đối số trước và sau khi advice thay đổi, đồng thời chỉ ra những lỗi thường gặp về **arity (số đối số), thứ tự, kiểu, `null`, binding và exception propagation**.

### Hình dung ngắn

~~~text
Caller:
    service.submit(" alice ", 2)
               |
               v
       Spring AOP proxy
               |
               v
    @Around: pjp.getArgs() -> [" alice ", 2]
               |
               | pjp.proceed(new Object[] {"ALICE", 3})
               v
       OrderService.submit("ALICE", 3)
               |
               v
       kết quả "order:ALICE:3"
               |
               v
       Advice trả lại kết quả
               |
               v
             Caller
~~~

Caller vẫn **đã gọi `submit(" alice ", 2)`**, nhưng target nhận `"ALICE", 3`. Chỉ các lời gọi **đi qua Spring AOP proxy** mới được advice này thực hiện; một object cùng class được tạo bằng `new` ngoài container không tự nhận advice.

## 2. Điều kiện để `proceed(Object[])` có tác dụng trong Spring

### 2.1. Around advice phải là Spring-managed aspect

Ví dụ cấu hình:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public RewriteAspect rewriteAspect() {
        return new RewriteAspect();
    }
}
~~~

Đây là **đoạn cấu hình minh họa**, chưa phải file Java hoàn chỉnh. Project đầy đủ nằm ở phần 5. Các yếu tố bắt buộc:

1. Class aspect được đánh dấu `@Aspect` **và** được đăng ký thành Spring bean (bằng `@Bean` hoặc component scanning phù hợp).
2. Target là Spring-managed bean. Spring AOP auto-proxy creator xét advisor, tạo proxy khi method phù hợp và cho caller sử dụng reference proxy.
3. Method execution phải khớp `@Around` pointcut. `proceed(Object[])` chỉ được gọi **bên trong advice đang thực thi**.
4. Method muốn được advice phải phù hợp với cơ chế proxy JDK/CGLIB. Với class proxy, `final`/`private` methods không thể được intercept theo kiểu override; self-invocation vẫn có thể bỏ qua proxy.
5. `ProceedingJoinPoint` phải là **tham số đầu của `@Around` advice**. Chỉ advice loại `@Around` nhận loại join point có `proceed`; `@Before`/`@AfterReturning` không có quyền tự quyết định method đích được gọi ra sao.

### 2.2. Hai overload

~~~java
Object result = pjp.proceed();
~~~

Không truyền mảng mới; method tiếp tục với argument list đang có trong join point. Đây là lựa chọn nên ưu tiên nếu chỉ cần quan sát, ghi log, đo thời gian hoặc làm thứ gì đó không thay đổi đối số.

~~~java
Object result = pjp.proceed(
        new Object[] { "ALICE", Integer.valueOf(3) }
);
~~~

Dùng argument list mới. Trong ví dụ `submit(String customer, int quantity)`, phần tử thứ nhất là `String`, phần tử thứ hai là `Integer` (Java wrapper được unbox thành `int` khi gọi method). **Mảng có đúng hai phần tử**, không thừa/thiếu.

Dùng `Object` cho return type của advice và `return pjp.proceed(...)` là cách thông thường để giữ nguyên hợp đồng trả về. Với method đích `void`, advice vẫn thường khai báo trả `Object` để giữ khả năng hoạt động thống nhất qua interceptor chain.

### 2.3. Khi nào *không* nên dùng overload nhận mảng?

Nếu chỉ muốn ghi log trước lời gọi:

~~~java
@Around("execution(* demo.OrderService.passthrough(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("AROUND: pass unchanged");
    return pjp.proceed();
}
~~~

Không cần sao chép hay tạo array mới. Thậm chí nếu chỉ cần log *trước* method, một `@Before` thường là advice **ít quyền can thiệp hơn**, dễ hiểu hơn `@Around`. Chỉ sử dụng `@Around` vì một yêu cầu thực tế cần bao cả invocation hoặc cần sửa argument/return.

## 3. Quy ước của Spring AOP: mảng đối số theo **method đích**

Giả sử target method:

~~~java
public String submit(String customer, int quantity) {
    return "order:" + customer + ":" + quantity;
}
~~~

Với Spring AOP, `proceed(Object[])` được hiểu như sau:

| Vị trí | Kiểu tham số của target | Đối số ban đầu | Đối số thay thế |
| --- | --- | --- | --- |
| `0` | `String customer` | `" alice "` | `"ALICE"` |
| `1` | `int quantity` | `2` (được boxed khi đọc qua `Object[]`) | `3` (dưới dạng `Integer` trong `Object[]`) |

~~~java
Object[] original = pjp.getArgs();
Object[] replacement = original.clone();

replacement[0] = ((String) original[0]).trim()
        .toUpperCase(java.util.Locale.ROOT);
replacement[1] = ((Integer) original[1]) + 1;

return pjp.proceed(replacement);
~~~

Đây là snippet **bên trong `@Around` advice**. Nó không dùng `Object[]` làm danh sách *tham số của advice*, mà dùng **đúng hai đối số của `submit(String,int)`**.

Vì sao nên `clone()` trước khi sửa?

- `pjp.getArgs()` dùng để **quan sát danh sách đối số** của join point; không nên dựa vào việc chỉnh trực tiếp mảng nó trả về sẽ luôn có ngữ nghĩa ổn định.
- Bản sao giúp biểu đạt rõ **đối số gốc** và **đối số chuyển xuống target**.
- Clone mảng là **shallow copy**: các object bên trong vẫn là cùng reference. Nếu một phần tử là object mutable, việc sửa thuộc tính của object đó không được giải quyết chỉ bằng `clone()`.
- Caller vẫn giữ reference tới object đầu vào ban đầu. Thay phần tử trong mảng gửi đến `proceed` khác với sửa object đầu vào tại chỗ.

**Số lượng phần tử phải đúng số tham số của method được intercept**, không phải số binding variables ở lời khai báo advice. Spring AOP thực thi method-execution join points; điều này đơn giản và trực tiếp hơn một số ngữ nghĩa của ngôn ngữ AspectJ được biên dịch/weave.

## 4. Khác biệt với quy ước truyền `proceed(Object[])` của AspectJ compiler

Đây là cảnh báo nổi bật trong tài liệu Spring chính thức.

### 4.1. Spring AOP proxy-based

Trong Spring AOP, `proceed(new Object[]{...})` nhận **toàn bộ đối số của method đích** theo thứ tự tham số. Ví dụ:

~~~java
public String inspect(String label, int units)
~~~

thì cần cung cấp **hai** đối số nếu thay đổi trước khi tiếp tục lời gọi:

~~~java
return pjp.proceed(new Object[] { "BOB", 6 });
~~~

### 4.2. AspectJ compiled around advice có quy tắc khác

Với advice được biên dịch theo **ngôn ngữ AspectJ truyền thống**, số lượng giá trị truyền cho `proceed` liên quan đến **số tham số được bind vào around advice**, chứ không mặc nhiên là toàn bộ tham số method đích. Giá trị ở vị trí bound thay thế entity tương ứng tại join point.

Vì thế, **đừng sao chép một ví dụ weaving/AspectJ compiler có bind một argument** rồi suy rằng `proceed(new Object[]{oneArg})` là đủ cho method đích hai tham số trong Spring AOP.

Tài liệu Spring đề xuất cách viết có thể tương thích giữa hai cơ chế: **bind đầy đủ các tham số method đích theo đúng thứ tự trong advice signature**, rồi cung cấp mảng mới có cùng giá trị/số phần tử theo thứ tự ấy. Ví dụ dạng một tham số:

~~~java
@Around(
    value = "execution(* demo.Repository.findByName(..)) && args(name)",
    argNames = "name"
)
public Object normalizeName(
        ProceedingJoinPoint pjp, String name) throws Throwable {
    String normalized = name.trim();
    return pjp.proceed(new Object[] { normalized });
}
~~~

Đây là snippet **minh họa**: `demo.Repository.findByName` không có trong project bên dưới, nhưng giả định nó có đúng **một tham số `String`**. Vì advice bind đúng một tham số của target, `new Object[]{normalized}` phù hợp quy tắc Spring AOP và cũng là hình dạng được tài liệu đề xuất để tránh khác biệt khi di chuyển sang cơ chế AspectJ compiler/weaver.

Đối với method đích **hai tham số**, nếu cần khả năng chuyển đổi tương thích, hãy bind đủ **hai tham số theo thứ tự**. Với Spring AOP thuần, không bắt buộc advice phải bind tất cả nếu bạn lấy đủ mảng bằng `pjp.getArgs()` và truyền đúng mảng khi `proceed`.

### 4.3. Minh họa trường hợp chỉ bind một tham số của method hai tham số

~~~java
@Around(
    value = "execution(* demo.OrderService.inspect(..)) && args(label,..)",
    argNames = "label"
)
public Object inspect(
        ProceedingJoinPoint pjp, String label) throws Throwable {
    Object[] current = pjp.getArgs();   // Method đích có 2 đối số.
    Object[] next = current.clone();
    next[0] = label.trim().toUpperCase(java.util.Locale.ROOT);
    next[1] = ((Integer) current[1]) + 2;

    return pjp.proceed(next);            // PHẢI truyền đủ 2 phần tử.
}
~~~

Ở đây advice signature chỉ có `String label` bên cạnh `ProceedingJoinPoint`, nhưng method được intercept là `inspect(String,int)`. **Mảng `next` có độ dài 2**, bởi `proceed(Object[])` theo quy ước Spring AOP tham chiếu đến method đích. Dạng này nhấn mạnh khác biệt và **không phải mẫu di động nguyên xi sang AspectJ compiler** với ngữ nghĩa binding khác.

Bài thực hành ở phần 5 sử dụng chính tình huống này, vì nó làm lộ lỗi “nhầm số tham số advice với số tham số target” một cách trực tiếp.

## 5. Dự án Spring Framework Java 17+ hoàn chỉnh

Ta chạy bốn case tách biệt, dùng bốn method khác tên để tránh chồng các `@Around` advice:

1. `passthrough(String)`: dùng `proceed()` và giữ nguyên đối số.
2. `submit(String,int)`: sửa **hai đối số** bằng `proceed(Object[])`.
3. `inspect(String,int)`: advice **chỉ bind một argument** (`label`) nhưng vẫn truyền **đủ hai giá trị**.
4. `fail(String)`: sửa argument trước khi target ném exception, sau đó **giữ nguyên exception propagation**.

### 5.1. Thư mục

~~~text
spring-aop-proceed-args/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── OrderService.java
    └── RewriteAspect.java
~~~

Yêu cầu Java 17+, Maven 3.9+, Spring Framework 6.2.0 và AspectJ Weaver 1.9.22. Các phiên bản được khóa để tái lập ví dụ, không tuyên bố là phiên bản mới nhất.

### 5.2. File `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-proceed-args</artifactId>
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

`spring-context` cung cấp `ApplicationContext`/Java configuration, `spring-aop` chứa hạ tầng proxy và `AopUtils`; `aspectjweaver` là thư viện hỗ trợ parsing các `@AspectJ` pointcut expressions của Spring AOP. Không có `-javaagent` hoặc weaving trong project này.

### 5.3. File `src/main/java/demo/OrderService.java`

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class OrderService {
    private final AtomicInteger targetCalls = new AtomicInteger();

    public String passthrough(String input) {
        targetCalls.incrementAndGet();
        System.out.println("TARGET_PASS: [" + input + "]");
        return "pass:" + input;
    }

    public String submit(String customer, int quantity) {
        targetCalls.incrementAndGet();
        System.out.println(
                "TARGET_SUBMIT: " + customer + " x" + quantity);
        return "order:" + customer + ":" + quantity;
    }

    public String inspect(String label, int units) {
        targetCalls.incrementAndGet();
        System.out.println(
                "TARGET_INSPECT: " + label + " x" + units);
        return "inspect:" + label + ":" + units;
    }

    public String fail(String customer) {
        targetCalls.incrementAndGet();
        System.out.println("TARGET_FAIL: " + customer);
        throw new IllegalStateException("declined:" + customer);
    }

    public int getTargetCalls() {
        return targetCalls.get();
    }
}
~~~

Các method này là `public`, class không `final` và không tự gọi lẫn nhau, nhằm giữ ví dụ tập trung vào việc **thay đổi argument list trong Spring AOP**. `targetCalls` ghi nhận số lần **thực sự vào target**; ngay cả method `fail` cũng tăng counter trước khi ném exception.

Mỗi method trả `String` (hoặc ném exception trước khi trả), giúp `@Around` xử lý kết quả kiểu `Object` mà vẫn trả về một `String` hợp lệ cho caller.

### 5.4. File `src/main/java/demo/RewriteAspect.java`

~~~java
package demo;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class RewriteAspect {
    private final AtomicInteger adviceCalls = new AtomicInteger();

    @Around("execution(String demo.OrderService.passthrough(..))")
    public Object aroundPass(ProceedingJoinPoint pjp) throws Throwable {
        adviceCalls.incrementAndGet();
        System.out.println("AROUND_PASS: original arguments");
        return pjp.proceed();
    }

    @Around("execution(String demo.OrderService.submit(..))")
    public Object aroundSubmit(ProceedingJoinPoint pjp) throws Throwable {
        adviceCalls.incrementAndGet();

        Object[] original = pjp.getArgs();
        Object[] changed = original.clone();

        String customer = (String) original[0];
        int quantity = (Integer) original[1];

        changed[0] = customer.trim().toUpperCase(Locale.ROOT);
        changed[1] = quantity + 1;

        System.out.println("AROUND_SUBMIT: modified 2 args");
        return pjp.proceed(changed);
    }

    @Around(
        value = "execution(String demo.OrderService.inspect(..))"
              + " && args(label,..)",
        argNames = "label"
    )
    public Object aroundInspect(
            ProceedingJoinPoint pjp, String label) throws Throwable {
        adviceCalls.incrementAndGet();

        Object[] changed = pjp.getArgs().clone();

        changed[0] = label.trim().toUpperCase(Locale.ROOT);
        changed[1] = ((Integer) changed[1]) + 2;

        System.out.println("AROUND_INSPECT: 1 binding, 2 args");
        return pjp.proceed(changed);
    }

    @Around("execution(String demo.OrderService.fail(..))")
    public Object aroundFail(ProceedingJoinPoint pjp) throws Throwable {
        adviceCalls.incrementAndGet();

        String customer = (String) pjp.getArgs()[0];
        Object[] changed = {
            customer.trim().toUpperCase(Locale.ROOT)
        };

        System.out.println("AROUND_FAIL: modified customer");
        return pjp.proceed(changed);
    }

    public int getAdviceCalls() {
        return adviceCalls.get();
    }
}
~~~

Giải thích từng advice:

- `aroundPass`: chỉ chuyển tiếp, không thay đầu vào. Nó dùng `proceed()` vì không cần mảng đối số mới.
- `aroundSubmit`: `getArgs()` cho hai phần tử, copy mảng, xử lý `String` (trim + uppercase) và tăng `int` từ `2` lên `3`. `proceed(changed)` truyền đủ hai đối số xuống target.
- `aroundInspect`: expression có `args(label,..)` chỉ **bind phần tử đầu** vào advice parameter `String label`. `argNames="label"` chỉ giúp Spring nhận diện tên binding trong advice signature. Method đích vẫn có `(String,int)`, nên `proceed(changed)` phải chứa **hai** phần tử. `argNames` **không** đổi quy ước độ dài mảng của Spring.
- `aroundFail`: thay input rồi gọi target. Exception từ target **đi xuyên qua advice** tới caller, vì advice không bắt/nuốt/đổi exception. Đây là cách giữ hợp đồng lỗi của business method.
- Mọi advice trả `Object` và `return pjp.proceed(...)` để giữ kết quả; không tạo `null` ngoài dự kiến.
- Các pointcut được giới hạn theo **tên method cụ thể** và không trùng nhau, giúp mỗi invocation tương ứng đúng một advice trong ví dụ.

**Đừng bỏ qua `throws Throwable`** khi gọi `ProceedingJoinPoint.proceed(...)`. Nó được khai báo trên API và đảm bảo các exception có thể được propagate qua advice. Trong ứng dụng thật, không nuốt exception chỉ vì method advice là tầng cross-cutting.

### 5.5. File `src/main/java/demo/App.java`

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public OrderService orderService() {
        return new OrderService();
    }

    @Bean
    public RewriteAspect rewriteAspect() {
        return new RewriteAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            OrderService service = context.getBean(OrderService.class);
            RewriteAspect aspect = context.getBean(RewriteAspect.class);

            boolean proxied = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxied);

            String pass = service.passthrough("keep");
            System.out.println("RESULT_PASS: " + pass);

            String submit = service.submit(" alice ", 2);
            System.out.println("RESULT_SUBMIT: " + submit);

            String inspect = service.inspect(" bob ", 4);
            System.out.println("RESULT_INSPECT: " + inspect);

            boolean failed = false;
            try {
                service.fail(" bad ");
            } catch (IllegalStateException ex) {
                failed = "declined:BAD".equals(ex.getMessage());
                System.out.println("CAUGHT: " + ex.getMessage());
            }

            int advice = aspect.getAdviceCalls();
            int target = service.getTargetCalls();
            System.out.println(
                    "COUNTS: advice=" + advice + ",target=" + target);

            if (!proxied
                    || !"pass:keep".equals(pass)
                    || !"order:ALICE:3".equals(submit)
                    || !"inspect:BOB:6".equals(inspect)
                    || !failed || advice != 4 || target != 4) {
                throw new IllegalStateException(
                    "Spring AOP proceed arguments verification failed");
            }

            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Tại sao ví dụ hoạt động theo đúng thiết kế Spring?

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật Spring AOP và tạo class-based proxy khi `OrderService` có advisor phù hợp. `OrderService` không implement interface nên cách lấy bằng `getBean(OrderService.class)` thuận tiện.
2. `@Bean rewriteAspect()` biến `RewriteAspect` thành Spring bean, để Spring nhận diện bốn `@Around` advisors.
3. Caller chỉ sử dụng **reference lấy từ ApplicationContext**, do đó method được gọi qua proxy, nơi advice có thể thay argument list.
4. `service.getTargetCalls()` là method không khớp bốn pointcut, nhưng vẫn có thể được gọi qua proxy; nó trả giá trị bộ đếm target mà không làm tăng advice counter.
5. Lời gọi `fail(" bad ")` vẫn truyền exception sau khi sửa argument thành `"BAD"`. `failed` xác nhận cả **loại lỗi** và message đúng nội dung.
6. Assertion tổng hợp buộc kết quả match và **chính xác bốn lần vào target**. Nếu `proceed` bị bỏ quên trong một advice hoặc giá trị mảng sai, chương trình không in `CHECK: PASS`.

### 5.6. Chạy Maven và stdout

Tại thư mục `spring-aop-proceed-args`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do mã ví dụ chủ động in ra, theo thứ tự:

~~~text
PROXY: true
AROUND_PASS: original arguments
TARGET_PASS: [keep]
RESULT_PASS: pass:keep
AROUND_SUBMIT: modified 2 args
TARGET_SUBMIT: ALICE x3
RESULT_SUBMIT: order:ALICE:3
AROUND_INSPECT: 1 binding, 2 args
TARGET_INSPECT: BOB x6
RESULT_INSPECT: inspect:BOB:6
AROUND_FAIL: modified customer
TARGET_FAIL: BAD
CAUGHT: declined:BAD
COUNTS: advice=4,target=4
CHECK: PASS
~~~

Maven hoặc logger framework có thể phát thêm thông báo tùy cấu hình môi trường; đoạn trên chỉ liệt kê `System.out.println` từ ứng dụng.

Bốn phép đối chứng:

- `passthrough("keep")`: **`proceed()`**, target thấy `"keep"` không đổi.
- `submit(" alice ", 2)`: **`proceed(Object[])`**, target nhận `("ALICE", 3)` chứ không phải `(" alice ", 2)`.
- `inspect(" bob ", 4)`: advice **chỉ bind label** nhưng vẫn cần mảng target đầy đủ `("BOB", 6)`; target trả `inspect:BOB:6`.
- `fail(" bad ")`: target nhận `"BAD"` trước khi ném exception, caller vẫn bắt đúng `declined:BAD`.

Kết quả `CHECK: PASS` chỉ xuất hiện khi proxy tồn tại, các kết quả và exception hợp lệ, và số lượt advice/target đều bằng bốn. Nếu dùng `proceed()` trong `aroundSubmit` thay vì `proceed(changed)`, target sẽ nhận các đối số không sửa và assertion thất bại.

## 6. Những lỗi thường gặp với `proceed(Object[])`

### 6.1. Mảng ít hoặc nhiều phần tử hơn số argument của method đích

Với method `submit(String customer, int quantity)`:

~~~java
return pjp.proceed(new Object[] { "ALICE" });
~~~

**Sai** trong Spring AOP: mảng chỉ có một phần tử nhưng method đích nhận hai tham số.

~~~java
return pjp.proceed(new Object[] { "ALICE", 3, "extra" });
~~~

**Sai** vì dư phần tử. Trong triển khai Spring AOP, việc chuyển tiếp với độ dài argument list không tương ứng có thể dẫn đến `IllegalArgumentException`/lỗi xử lý invocation từ framework. Đừng phụ thuộc exact exception class/message cho mọi biến thể, nhưng **không thử chạy target với mảng sai arity** trong logic production.

Đúng:

~~~java
return pjp.proceed(new Object[] { "ALICE", 3 });
~~~

Các snippet trong phần này là **những biểu thức minh họa bên trong `@Around` advice**, không thêm chúng đồng thời vào project chính.

### 6.2. Mảng đúng độ dài nhưng đảo thứ tự hoặc kiểu

~~~java
return pjp.proceed(new Object[] { 3, "ALICE" });
~~~

Mảng có hai phần tử nhưng method đích yêu cầu `(String,int)`. Cách này sai về **vị trí/kiểu** và có thể gây lỗi khi framework gọi target bằng reflection/proxy, ví dụ lỗi argument type mismatch.

Lưu ý Java primitive khi dùng `Object[]`:

- `int` được biểu diễn qua wrapper `Integer`.
- `long` thường dùng `Long`, `boolean` dùng `Boolean`.
- Không kỳ vọng chuyển đổi mọi wrapper số tùy ý tự động thành primitive mong muốn; tốt nhất dùng đúng wrapper tương ứng.
- `null` không phải giá trị hợp lệ cho tham số primitive như `int`; nhưng `null` có thể dùng cho tham số reference nếu business contract cho phép.
- Cần kiểm tra downstream validators/contracts: một String được trim/uppercase vẫn có thể làm thay đổi ý nghĩa dữ liệu, định danh, chữ ký bảo mật hoặc quy tắc nghiệp vụ.

Nếu advice không biết chính xác chữ ký method mà chỉ áp dụng wildcard rộng, đừng tự suy rằng phần tử thứ hai của mọi invocation đều là `Integer`. Giới hạn pointcut hoặc kiểm tra method signature/arguments trước khi biến đổi.

### 6.3. Nhầm `pjp.getArgs()` với `Object[]` truyền cho proceed

~~~java
Object[] args = pjp.getArgs();
args[0] = "CHANGED";

return pjp.proceed();
~~~

Đây **không phải** cách an toàn/di động để bảo đảm target nhận `"CHANGED"`. `proceed()` tiếp tục với argument list hiện có trong join point; hành vi khi sửa trực tiếp array trả về từ `getArgs()` không nên là hợp đồng bạn dựa vào giữa các adapter/version. Nếu muốn thể hiện một phép thay đổi rõ ràng theo API Spring AOP, **tạo mảng thay thế và gọi `proceed(newArgs)`**.

Dạng rõ ý định:

~~~java
Object[] original = pjp.getArgs();
Object[] changed = original.clone();
changed[0] = "CHANGED";
return pjp.proceed(changed);
~~~

Nếu Spring/AspectJ ở một phiên bản có hành vi khác khi sửa `getArgs()` array tại chỗ, dạng clone + `proceed(changed)` vẫn là cách biểu đạt trực tiếp việc thay argument list, có thể code review và kiểm thử.

### 6.4. Bỏ quên `proceed`

~~~java
@Around("execution(* demo.OrderService.submit(..))")
public Object broken(ProceedingJoinPoint pjp) {
    return "fake-result";
}
~~~

Đoạn này **hợp lệ về mặt khả năng của `@Around`**, nhưng nếu yêu cầu là chuyển tiếp rồi sửa input thì đây là lỗi logic: target không chạy. `@Around` có quyền short-circuit, do đó chỉ được bỏ `proceed` nếu đó là chính sách được thiết kế rõ ràng (ví dụ cache hit, authorization failure có fallback hợp lệ).

### 6.5. Gọi `proceed` hai lần không kiểm soát

~~~java
Object first = pjp.proceed(args1);
Object second = pjp.proceed(args2);
return second;
~~~

Một `@Around` có thể gọi target nhiều lần, nhưng các thao tác ghi dữ liệu, thanh toán, gửi email có thể bị lặp. Không dùng `proceed(Object[])` để tạo retry tùy tiện. Nếu có yêu cầu retry, phải kiểm soát idempotency, số lần tối đa, exception, transaction và argument list cho từng lần thử. Nhiều hệ thống nên dùng integration chuyên biệt cho retry thay vì một aspect tùy biến.

### 6.6. Nuốt exception hoặc trả sai result type

~~~java
try {
    return pjp.proceed(changed);
} catch (Throwable error) {
    return null;
}
~~~

Đoạn này có thể làm mất exception gốc và thay nó bằng giá trị `null`, phá contract của method đích. Nếu chỉ sửa arguments, để exception propagate tự nhiên bằng `return pjp.proceed(changed);`. Nếu buộc phải xử lý exception/fallback, cần định nghĩa đó là requirement độc lập, bảo đảm kiểu return tương thích và kiểm thử.

`@Around` nên khai báo return type `Object`. Nếu advice khai báo `void`, Spring không có result value để trả lại giống method có return value; đây là nguyên nhân thường gặp của lỗi kết quả bất ngờ khi copy-paste advice.

## 7. Các khía cạnh khác khi truyền `Object[]` trong Spring AOP

### 7.1. Varargs method

Với một method Java:

~~~java
public String send(String topic, String... tags) {
    return topic + ":" + java.util.Arrays.toString(tags);
}
~~~

Varargs được biểu diễn bằng **một tham số mảng** (`String[]`) ở bytecode. Khi Spring advice một method như vậy, danh sách method parameters về mặt reflection là `(String, String[])`, không phải một tham số mới cho mỗi tag.

Trong quy ước method signature, mảng thay thế nên có hai phần tử:

~~~java
return pjp.proceed(
        new Object[] { "NEWS", new String[] { "java", "spring" } }
);
~~~

Đây là code minh họa bên trong advice; class `send` không có trong project runnable. Không trải phẳng `String... tags` thành ba hay bốn phần tử `Object[]` tùy số tag; điều đó không đúng số tham số method đích ở JVM.

### 7.2. Overloaded methods

Nếu class có:

~~~java
public void notify(String value) {
}

public void notify(String value, int retries) {
}
~~~

một pointcut quá rộng như `execution(* *.notify(..))` có thể chọn **cả hai overloads**. Advice giả định `args.length == 2` sẽ lỗi với overload một tham số. Cần:

- Giới hạn pointcut theo signature cụ thể khi có thể;
- Hoặc kiểm tra `pjp.getArgs().length` và `pjp.getSignature()` trước khi tạo mảng;
- Hoặc để nguyên lời gọi bằng `proceed()` nếu invocation không nằm trong phạm vi biến đổi được thiết kế.

Điều này quan trọng vì `proceed(Object[])` không tự suy kiểu tham số từ số phần tử mong muốn; **method đích đã được chọn** trước khi mảng thay thế đi vào.

### 7.3. Generic/bridge method và interface proxy

Ở Spring AOP, caller có thể đi qua JDK dynamic proxy hoặc class-based CGLIB proxy. Method signature mà framework xử lý có thể liên quan tới interface, implementation, generic bridge hoặc target method. Với method có nhiều overload hoặc generic erasure, test thực sự trên proxy configuration ứng dụng, không chỉ tính toán dựa trên source code một class.

Nếu business method chỉ được expose qua interface, đảm bảo lời gọi tới method đó thực sự đi qua Spring AOP proxy. Đừng tin rằng `proceed(Object[])` có thể sửa arguments cho object được gọi trực tiếp bằng `new`, self-invocation `this.method()`, `final`/`private` method không được class proxy intercept.

### 7.4. Null, immutable và mutable objects

`proceed(Object[])` **thay giá trị reference được chuyển xuống target**; nó không tự deep-copy các object. Ví dụ:

~~~java
Object[] before = pjp.getArgs();
Object[] next = before.clone();

next[0] = java.util.List.copyOf(
        (java.util.List<?>) before[0]
);

return pjp.proceed(next);
~~~

Nếu tham số đầu target là `List`, đoạn minh họa trên thay reference thành immutable copy (và `List.copyOf` không chấp nhận `null` element). Điều này có thể làm thay đổi hành vi target nếu target định sửa list; vì thế transformation phải có lý do rõ ràng. Dùng `Object[]` không có nghĩa mọi element đều tự động được serialize/clone.

Chọn cách copy và validate dựa trên hợp đồng business: một DTO chứa mutable nested object có thể cần defensive copy sâu hoặc tuyệt đối không được thay đổi.

### 7.5. Side effects và transaction/security context

Nếu Spring AOP proxy còn có advisor cho `@Transactional`, cache hoặc security, các advice nằm trong **interceptor chain** với thứ tự phụ thuộc precedence. Việc thay arguments bằng `proceed(Object[])` có thể ảnh hưởng logic được gọi phía sau (và có thể ảnh hưởng key/policy của một advisor ở trong chain), nhưng không nên tuyên bố mọi advisor luôn nhìn thấy cùng một argument list nếu không kiểm tra ordering.

Đặc biệt:

- Không tự thay đối số mang nghĩa identity/authentication chỉ để “chuẩn hóa” nếu hợp đồng bảo mật không cho phép.
- Cẩn thận với caching: thay arguments ở một vị trí trong chain có thể khiến cache key được xây từ đối số trước hoặc sau phép thay tùy ordering.
- Không gọi `proceed` nhiều lần trong transaction mà chưa kiểm soát semantics và idempotency.
- Nếu logic chỉ cần validation và ném exception trước khi target chạy, `@Before` có thể đủ; chỉ dùng `@Around` để thay arguments nếu thật sự cần.

## 8. Kiểm thử `proceed(Object[])` trong dự án thật

Không nên dừng ở test kiểm tra advice có chạy. Cần kiểm chứng **giá trị target đã nhận** và caller đã thấy gì.

Ma trận tối thiểu:

| Ca | Đối số caller truyền | Đối số target cần nhận | Kỳ vọng |
| --- | --- | --- | --- |
| Giữ nguyên | `passthrough("keep")` | `"keep"` | Không đổi vì `proceed()` |
| Thay `String` + primitive | `submit(" alice ",2)` | `("ALICE",3)` | Đúng cả hai vị trí |
| Chỉ bind một argument trong advice | `inspect(" bob ",4)` | `("BOB",6)` | Spring dùng đủ hai method arguments |
| Exception propagation | `fail(" bad ")` | `"BAD"` rồi throw | Caller nhận exception gốc |
| Sai arity | `submit("A",1)` nhưng advice truyền mảng độ dài 1 | Không có invocation hợp lệ | Test cần xác nhận reject, không chạy business target |
| Sai vị trí/kiểu | `submit("A",1)`, mảng `[1,"A"]` | Không tương thích `(String,int)` | Không được xem là behavior hợp lệ |
| Primitive nhận `null` | `submit("A",1)`, mảng `["A",null]` | `int` không nhận `null` | Phải validate trước khi proceed |
| Caller dùng `new OrderService()` | Bất kỳ | Tự gọi target, không proxy | Không tự chạy around advice |
| Self-invocation | `this.submit(...)` bên trong target | Lời gọi Java nội bộ | Không qua Spring proxy, dù có pointcut |

Để test âm mà không khiến code production có hành vi nguy hiểm, tạo một **test-only aspect** hoặc unit test chấp nhận exception theo kiểu đủ rộng và kiểm tra target counter không tăng. Cần nhìn root cause của phiên bản Spring đang dùng thay vì đóng đinh exact exception message.

Trong project phần 5, bộ đếm `adviceCalls` và `targetCalls`, giá trị trả về và message của exception cung cấp bốn bằng chứng riêng biệt. Bài thực hành không phụ thuộc log framework hay kết quả timing khó dự đoán.

### Một JUnit test tối giản bổ sung cho project phần 5

Nếu muốn biến kiểm tra đã có trong `App.main()` thành integration test tự động, thêm `junit-jupiter` test dependency cùng `maven-surefire-plugin` phiên bản hỗ trợ JUnit 5, rồi tạo:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProceedArgumentsTest {
    @Test
    void replacementArgumentsReachTargetThroughSpringProxy() {
        try (var context =
                new AnnotationConfigApplicationContext(App.class)) {
            OrderService service = context.getBean(OrderService.class);
            RewriteAspect aspect = context.getBean(RewriteAspect.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals(
                "order:ALICE:3",
                service.submit(" alice ", 2));
            assertEquals(
                "inspect:BOB:6",
                service.inspect(" bob ", 4));
            assertEquals(2, aspect.getAdviceCalls());
            assertEquals(2, service.getTargetCalls());
        }
    }
}
~~~

Đây là **file `src/test/java/demo/ProceedArgumentsTest.java` hoàn chỉnh**, nhưng cần các dependency JUnit/Surefire bổ sung như đã nêu, nên **chưa chạy được chỉ với `pom.xml` tối thiểu** của phần 5. Các giá trị assertion xác minh hai cách sửa arguments khác nhau trong cùng một Spring ApplicationContext.

Cần bảo đảm test thực hiện lời gọi qua `context.getBean(...)`, không phải tự `new OrderService()`, vì bài cần kiểm chứng semantics **Spring AOP**, không chỉ test một Java helper xử lý `Object[]`.

## 9. Tổ chức việc bind tham số cho advice có khả năng di chuyển

Trong Spring AOP, đoạn này hợp lệ cho `inspect(String,int)`:

~~~java
@Around(
    value = "execution(* demo.OrderService.inspect(..)) && args(label,..)",
    argNames = "label"
)
public Object around(ProceedingJoinPoint pjp, String label)
        throws Throwable {
    Object[] all = pjp.getArgs().clone();
    all[0] = label.trim();
    return pjp.proceed(all);
}
~~~

Nhưng vì advice chỉ bind **một** tham số của target, nó không phải lựa chọn mạnh nhất nếu muốn dùng cùng source `@AspectJ` aspect qua **cả Spring AOP và AspectJ compiler/weaver**.

Nếu mục tiêu là một pattern tương thích hơn, bind đầy đủ theo method:

~~~java
@Around(
    value = "execution(* demo.OrderService.inspect(String,int))"
          + " && args(label,units)",
    argNames = "label,units"
)
public Object around(
        ProceedingJoinPoint pjp, String label, int units)
        throws Throwable {
    return pjp.proceed(new Object[] {
        label.trim(),
        units + 2
    });
}
~~~

Ở dạng này, advice có hai binding variables cùng thứ tự tương ứng với hai tham số method. Việc `argNames` kê tên đầy đủ giúp Spring phân giải binding chính xác; Java `-parameters` compile flag có thể hỗ trợ khám phá tên nhưng không nên là giả định ngầm khi chia sẻ thư viện.

Đây là **hai cách lựa chọn để viết lại `aroundInspect`** trong class aspect; không đặt cả hai cùng lúc. Pattern thứ hai theo sát khuyến nghị của tài liệu Spring cho việc giảm khác biệt `proceed(Object[])` giữa Spring proxy AOP và AspectJ compiler/weaver. Bài này vẫn chỉ thực thi bằng **Spring AOP**; lưu ý tương thích nhằm tránh lỗi khi tái sử dụng advice.

## 10. Chẩn đoán lỗi tại runtime

Khi thấy target nhận đối số sai, exception lạ hoặc advice không chạy:

1. **Xác nhận pointcut:** expression `execution(...)` match method thực sự trong Spring bean không? Nếu không match, mọi logic `proceed` đều không được chạy.
2. **Xác nhận Spring proxy:** `AopUtils.isAopProxy(service)` trên reference thực sự caller dùng. Object tạo ngoài container và self-invocation không tự được advice.
3. **In số lượng đối số:** kiểm tra `pjp.getArgs().length` và đối chiếu **số tham số của method target**, không đếm số argument được bind vào advice.
4. **Xem từng vị trí và kiểu:** nếu method nhận `(String,int)`, mảng phải có `String` ở index `0` và `Integer` ở index `1`.
5. **Sao chép mảng trước khi sửa:** tránh phụ thuộc side effect từ việc chỉnh `getArgs()` trực tiếp.
6. **Không thay argument mà không cần:** nếu chỉ logging/metrics, giữ `proceed()` hoặc cân nhắc advice hẹp hơn `@Before`.
7. **Kiểm tra return value:** quanh method trả `String`, advice nên trả đúng kết quả `Object` mà `proceed` tạo ra, hoặc fallback có kiểu phù hợp nếu requirement cho phép.
8. **Kiểm tra exception propagation:** advice có catch rồi nuốt lỗi không? Nếu có, đây là thay đổi business contract cần phê duyệt, không phải tác động mặc định của `proceed(Object[])`.
9. **Kiểm tra overload, varargs, generic bridge:** method được chọn có đúng chữ ký mong đợi không? `String...` là `String[]` tại ranh giới JVM.
10. **Xem ordering:** nếu nhiều `@Around`/advisors cùng khớp, lời gọi `proceed` chuyển tiếp vào phần **còn lại của interceptor chain**, không nhất thiết vào target ngay. Test với đúng Spring context và thứ tự advisors khi arguments liên quan cache/transaction/security.
11. **Xác nhận raw vs transformed:** ghi marker trong target hoặc dùng spy/test counter. Chỉ ghi marker trước `proceed` không chứng minh target nhận được mảng mới.
12. **Đọc root cause thay vì đoán exception message:** độ dài/kiểu sai gây invocation failure, nhưng wrapper và nội dung lỗi có thể thay đổi theo phiên bản/framework integration.

Đo nhanh tại call site với một Spring context đã có `OrderService` bean:

~~~java
OrderService service = context.getBean(OrderService.class);
System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(service)
);
~~~

Đây là đoạn chèn vào phương thức có biến `context`, không phải file Java độc lập. Nếu trả `false`, hãy kiểm tra bean/aspect/pointcut trước khi phân tích array replacement.

## 11. Câu hỏi tự kiểm tra

**1. Với method `transfer(String from, String to, int amount)` và advice chỉ bind `amount`, mảng `proceed(Object[])` của Spring AOP cần mấy phần tử?**  
**Ba** phần tử, tương ứng `from`, `to`, `amount`. Không dùng mảng một phần tử chỉ vì advice có một bound parameter.

**2. Khi nào nên gọi `proceed()` thay vì `proceed(Object[])`?**  
Khi không cần thay arguments và chỉ muốn method chạy với danh sách đối số hiện có.

**3. Nếu lời gọi `submit(" alice ",2)` đổi thành `proceed(new Object[]{"ALICE",3})`, caller có tự thấy biến String đầu vào chuyển thành `"ALICE"`?**  
Không. Advice chuyển danh sách giá trị/reference mới cho invocation xuống target; nó không tự đổi các biến local của caller.

**4. Có thể truyền `new Object[]{"ALICE",null}` tới method `submit(String,int)` không?**  
Không hợp lệ cho primitive `int`. Phải truyền wrapper số tương thích và theo đúng contract.

**5. Vì sao dùng `args(label,..)` chỉ bind một tham số mà advice vẫn có thể sửa cả hai đối số method?**  
Vì `pjp.getArgs()` cho danh sách arguments của method join point; `proceed(Object[])` nhận danh sách method arguments đầy đủ theo quy ước Spring AOP.

**6. Có nên sửa trực tiếp `pjp.getArgs()[0]` rồi gọi `proceed()`?**  
Không nên dựa vào side effect của array trả về; thể hiện rõ thay đổi bằng `clone()` và `proceed(changed)`.

**7. `@Around` có được bỏ `proceed`?**  
Được về mặt khả năng, nhưng target sẽ không chạy nếu advice short-circuit. Chỉ làm khi requirement thật sự yêu cầu và return/exception policy được xác định.

**8. Dùng `proceed(Object[])` có tự khiến method `final` trên target được intercept không?**  
Không. Nó chỉ hoạt động **bên trong around advice đã được gọi qua proxy**, không vượt giới hạn method interception của Spring.

**9. Varargs `send(String topic, String... tags)` yêu cầu số phần tử thế nào?**  
Theo signature JVM là **hai** tham số: `String` và `String[]`, không trải số tag thành các phần tử riêng của `Object[]`.

**10. Khác biệt lớn nhất giữa Spring AOP và advice được AspectJ compiler biên dịch là gì?**  
Spring `proceed(Object[])` dùng **arguments của underlying method** theo thứ tự; AspectJ compiler traditional around advice định vị arguments theo **các binding của advice**. Muốn code tương thích, bind đầy đủ method arguments theo thứ tự và tạo mảng đúng cấu trúc.

## 12. Checklist thực hành

- [ ] Spring bean được lấy từ `ApplicationContext` và proxy đã có advisor match.
- [ ] `@Around` nhận `ProceedingJoinPoint` ở tham số đầu, method advice khai báo `throws Throwable` nếu chuyển tiếp exception.
- [ ] Nếu không đổi arguments, ưu tiên `proceed()`; nếu chỉ log trước, cân nhắc `@Before`.
- [ ] Nếu đổi arguments, dùng `proceed(Object[])` và truyền **đủ số lượng/thứ tự của method target**.
- [ ] Các giá trị trong mảng có kiểu phù hợp, kể cả primitive wrappers và `null`.
- [ ] Nếu bind một phần qua `args(...)`, không nhầm số binding của advice với số arguments method.
- [ ] Không phụ thuộc mutation trực tiếp vào `pjp.getArgs()`; tạo mảng thay thế tường minh.
- [ ] Trả kết quả của `proceed` khi không chủ đích transform; không nuốt exception ngoài yêu cầu.
- [ ] Không gọi `proceed` nhiều lần khi side effects chưa được kiểm soát.
- [ ] Đã test return value, target-observed arguments, exception và proxy boundary.
- [ ] Khi tái sử dụng code qua Spring AOP và AspectJ weaving, áp dụng quy ước bind đầy đủ arguments theo thứ tự theo khuyến nghị Spring.

## 13. Tài liệu chính thức Spring Framework

- [Spring Framework 6.2 — Declaring Advice, Around Advice và Proceeding with Arguments](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): giải thích trực tiếp `proceed()`, `proceed(Object[])`, sự khác biệt với AspectJ compiler và pattern bind arguments để tương thích.
- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `execution(...)`, `args(...)`, Spring AOP method-execution semantics.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxy và giới hạn self-invocation.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): đăng ký aspect và auto-proxying trong Spring context.
- [ProceedingJoinPoint JavaDoc (AspectJ)](https://www.javadoc.io/doc/org.aspectj/aspectjrt/1.9.22/org/aspectj/lang/ProceedingJoinPoint.html): API `proceed()`/`proceed(Object[])` mà Spring sử dụng qua `@Around`.
