# `this` và `target` trong mô hình proxy của Spring AOP

## 1. Bản chất vấn đề

Trong **Spring AOP**, một lời gọi của client đi vào **proxy** của Spring. Proxy chọn interceptor/advice phù hợp và cuối cùng, nếu chuỗi advice tiếp tục, lời gọi được chuyển đến **target object** đang thực thi nghiệp vụ. Vì proxy và target là hai vai trò khác nhau, pointcut của Spring phân biệt:

- **`this(Type)`:** điều kiện về **đối tượng Spring AOP proxy** nhận lời gọi. Join point khớp khi proxy có thể được coi là một instance của `Type`.
- **`target(Type)`:** điều kiện về **đối tượng đích (target object)** đứng sau proxy. Join point khớp khi target là instance của `Type`.

Đây là ý nghĩa của hai **pointcut designator** trong Spring AOP, không phải lời giải thích chung về từ khóa Java `this`. Trong mô hình weaving AspectJ thuần, hai designator có thể có ngữ nghĩa khác vì không có lớp Spring AOP proxy đứng giữa. Bài chỉ tập trung vào **Spring Framework và Spring AOP**.

Hãy hình dung:

```text
Caller bean
    |
    | Spring injects a bean reference
    v
+-------------------------+
| Spring AOP proxy        | <-- this(Type)
|  - JDK proxy hoặc CGLIB |
|  - advisor chain        |
+-------------------------+
    |
    | proceed() / delegate
    v
+-------------------------+
| Target object           | <-- target(Type)
| PaymentServiceImpl      |
| business method()       |
+-------------------------+
    |
    v
Kết quả / exception về lại proxy và caller
```

Cùng một lời gọi `pay()` có thể thỏa `target(PaymentServiceImpl)` nhưng **không thỏa** `this(PaymentServiceImpl)` nếu proxy là JDK dynamic proxy. Đây là khác biệt quan trọng nhất khi sử dụng `this` và `target` trong Spring pointcut.

## 2. Phân biệt proxy, target, interface và implementation

Xét một interface và implementation:

```java
package demo;

public interface PaymentService {
    String pay(String id);
}

public class PaymentServiceImpl implements PaymentService {
    @Override
    public String pay(String id) {
        return "PAID:" + id;
    }
}
```

Hai khai báo trên là mã minh họa, cần đặt vào các tệp Java tương ứng nếu chạy độc lập. Chúng ta giả sử Spring tạo AOP proxy cho `PaymentServiceImpl` vì có advice phù hợp.

### Trường hợp A: JDK dynamic proxy

JDK proxy triển khai `PaymentService`, nhưng **không phải subclass của `PaymentServiceImpl`**:

```text
JDK-generated proxy  -- implements --> PaymentService
        |
        | dispatch advice + delegate
        v
PaymentServiceImpl target  -- implements --> PaymentService
```

Trong một lời gọi qua JDK AOP proxy:

- `this(PaymentService)`: **khớp**, vì proxy triển khai interface.
- `this(PaymentServiceImpl)`: **không khớp**, vì JDK proxy không extends implementation.
- `target(PaymentService)`: **khớp**, vì target triển khai interface.
- `target(PaymentServiceImpl)`: **khớp**, vì đối tượng thật thuộc lớp implementation.

### Trường hợp B: CGLIB class-based proxy

CGLIB proxy do Spring tạo là **subclass runtime của target class**:

```text
CGLIB-generated subclass  -- extends --> PaymentServiceImpl
        |
        | dispatch advice + delegate
        v
PaymentServiceImpl target -- implements --> PaymentService
```

Với target/proxy hợp lệ như trên:

- `this(PaymentService)`: **khớp**, vì subclass cũng implement interface.
- `this(PaymentServiceImpl)`: **khớp**, vì proxy là subtype của implementation.
- `target(PaymentService)`: **khớp**, vì target implement interface.
- `target(PaymentServiceImpl)`: **khớp**, vì target thuộc implementation.

| Pointcut trên method `pay()` | JDK Spring AOP proxy | CGLIB Spring AOP proxy |
| --- | --- | --- |
| `this(demo.PaymentService)` | Khớp | Khớp |
| `this(demo.PaymentServiceImpl)` | Không khớp | Khớp |
| `target(demo.PaymentService)` | Khớp | Khớp |
| `target(demo.PaymentServiceImpl)` | Khớp | Khớp |

Bảng giả định đúng một `PaymentServiceImpl` target và method public có thể intercept, advisor phù hợp, caller **gọi qua Spring proxy**. Với target khác, proxy bổ sung các interface khác, proxy lồng nhau hoặc cơ chế đặc biệt, phải xác minh bằng runtime.

## 3. `this` trong Spring pointcut KHÁC từ khóa Java `this`

Hai dòng sau không mang cùng một ý nghĩa:

```java
// Java: tham chiếu tới instance đang thực thi method này
this.otherMethod();

// Pointcut: chọn method execution mà AOP proxy là instance của PaymentService
@Before("execution(* demo..*.pay(..)) && this(demo.PaymentService)")
public void before() {
    System.out.println("advice");
}
```

Khối trên là **minh họa**, kết hợp cú pháp từ hai vị trí khác nhau; method `@Before` phải nằm trong một Spring-managed `@Aspect` bean với các import phù hợp.

- **Java `this` trong method target:** là instance target đang chạy business method. Một lời gọi `this.otherMethod()` từ đây **thường không quay lại proxy**, nên không kích hoạt advice trên `otherMethod()` thông qua Spring AOP.
- **Designator `this(Type)` của Spring AOP:** ràng buộc/kiểm tra **đối tượng proxy** tại method execution join point mà Spring đang can thiệp.
- **`JoinPoint.getThis()`:** cung cấp proxy object tương ứng với ý nghĩa Spring AOP của `this` trong pointcut.
- **`JoinPoint.getTarget()`:** cung cấp target object tương ứng với ý nghĩa `target`.

Trong một lời gọi qua proxy thông thường, `joinPoint.getThis() == joinPoint.getTarget()` trả `false`. Mô hình Spring AOP tách đối tượng proxy và target dù CGLIB proxy extends target class.

Với Spring AOP, **self-invocation** vẫn bỏ qua proxy, kể cả khi dùng CGLIB; chuyển `proxyTargetClass=true` không tự làm `this.otherMethod()` bên trong target trở thành một lời gọi proxy mới.

## 4. `this(Type)` / `target(Type)` được áp dụng ở bước nào?

Một pointcut như:

```java
@Around("execution(* demo..*.pay(..)) && target(demo.PaymentServiceImpl)")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

được Spring sử dụng để xác định những **method execution join points** phù hợp trong các lời gọi **đi qua proxy**. `execution(...)` kiểm tra signature và phạm vi method; `target(...)` ràng buộc loại target object. Chúng hoạt động như hai điều kiện logic được kết hợp bằng `&&`.

Một biểu thức tương ứng dùng `this`:

```java
@Around("execution(* demo..*.pay(..)) && this(demo.PaymentServiceImpl)")
public Object aroundImplProxy(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
```

Khi bean AOP proxy bằng JDK, điều kiện `this(demo.PaymentServiceImpl)` không thỏa, dù target `PaymentServiceImpl` có method `pay()` và method đó được client gọi qua interface. Khi cùng bean sử dụng CGLIB proxy, điều kiện có thể thỏa vì proxy subclass của `PaymentServiceImpl`.

**Quan trọng:** một pointcut chỉ khớp kiểu nhưng không có lời gọi qua proxy sẽ không khiến Spring “can thiệp từ xa” vào object tự `new` hoặc vào lệnh `this.foo()` bên trong target. Hai designator là **điều kiện cho join point vốn Spring AOP có thể intercept**, không phải cơ chế thay thế proxy.

### Không dùng `target(...)` như `execution(...)`

`target(Type)` chỉ nói target instance thỏa kiểu; nó không nêu method nào bạn muốn advice. Nên kết hợp với điều kiện method cụ thể và giới hạn package:

```java
@Before("execution(public * demo.service..*.*(..)) && target(demo.service.PaymentService)")
public void auditPaymentCall() {
    // ghi nhận các lời gọi dịch vụ phù hợp
}
```

Đây là **snippet** cần lớp trong package `demo.service`, bean `@Aspect` và Spring context tương ứng. Pointcut được giới hạn rõ hơn so với việc áp `target(...)` lên mọi method thuộc target.

## 5. Ví dụ chạy được: cùng target, JDK proxy so với CGLIB

Ví dụ sử dụng **Java 17+, Maven, Spring Framework 6.2.6**. Một service triển khai interface. Hai context riêng dùng cùng các bean definitions, khác nhau ở `@EnableAspectJAutoProxy(proxyTargetClass=...)`.

Aspect sử dụng **một `@Around` advice** khớp `perform()`, rồi quan sát trực tiếp `ProceedingJoinPoint.getThis()` và `getTarget()`. Vì chỉ có một advice và một method execution mục tiêu, stdout có thứ tự rõ ràng.

### 5.1. Cấu trúc tệp

```text
spring-aop-this-target/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ThisTargetDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-this-target</artifactId>
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
            <version>1.9.22.1</version>
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
                    <mainClass>demo.ThisTargetDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/ThisTargetDemo.java`:

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class ThisTargetDemo {

    public interface TaskApi {
        String perform(String input);
    }

    public static class TaskService implements TaskApi {
        @Override
        public String perform(String input) {
            System.out.println("TARGET perform " + input);
            return "DONE:" + input;
        }
    }

    @Aspect
    public static class TraceAspect {
        @Around("execution(* demo..*.perform(..))")
        public Object trace(ProceedingJoinPoint pjp) throws Throwable {
            Object proxy = pjp.getThis();
            Object target = pjp.getTarget();

            System.out.println("THIS_IS_API=" + (proxy instanceof TaskApi));
            System.out.println("THIS_IS_IMPL=" + (proxy instanceof TaskService));
            System.out.println("TARGET_IS_API=" + (target instanceof TaskApi));
            System.out.println("TARGET_IS_IMPL=" + (target instanceof TaskService));
            System.out.println("SAME_OBJECT=" + (proxy == target));

            return pjp.proceed();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SharedBeans {
        @Bean
        public TaskApi taskApi() {
            return new TaskService();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    @Import(SharedBeans.class)
    public static class JdkConfig {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    @Import(SharedBeans.class)
    public static class CglibConfig {
    }

    private static void inspect(String label, TaskApi bean) {
        System.out.println(label + "_AOP=" + AopUtils.isAopProxy(bean));
        System.out.println(label + "_JDK=" + AopUtils.isJdkDynamicProxy(bean));
        System.out.println(label + "_CGLIB=" + AopUtils.isCglibProxy(bean));
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(JdkConfig.class)) {
            TaskApi bean = context.getBean(TaskApi.class);
            System.out.println("=== JDK ===");
            inspect("JDK", bean);
            System.out.println("RESULT=" + bean.perform("A"));
        }

        try (var context =
                new AnnotationConfigApplicationContext(CglibConfig.class)) {
            TaskApi bean = context.getBean(TaskApi.class);
            System.out.println("=== CGLIB ===");
            inspect("CGLIB", bean);
            System.out.println("RESULT=" + bean.perform("B"));
        }
    }
}
```

Chạy từ thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

Stdout **các dòng do chương trình in** (Maven/Spring có thể ghi thêm logging riêng):

```text
=== JDK ===
JDK_AOP=true
JDK_JDK=true
JDK_CGLIB=false
THIS_IS_API=true
THIS_IS_IMPL=false
TARGET_IS_API=true
TARGET_IS_IMPL=true
SAME_OBJECT=false
TARGET perform A
RESULT=DONE:A
=== CGLIB ===
CGLIB_AOP=true
CGLIB_JDK=false
CGLIB_CGLIB=true
THIS_IS_API=true
THIS_IS_IMPL=true
TARGET_IS_API=true
TARGET_IS_IMPL=true
SAME_OBJECT=false
TARGET perform B
RESULT=DONE:B
```

Trong cả hai context, `SharedBeans.taskApi()` vẫn trả `TaskApi` và tạo `new TaskService()`. Chỉ thay đổi chiến lược tạo proxy:

- Ở context JDK, `pjp.getThis()` là JDK proxy nên `THIS_IS_IMPL=false`.
- Ở context CGLIB, `pjp.getThis()` là subclass proxy nên `THIS_IS_IMPL=true`.
- Trong cả hai context, `pjp.getTarget()` là `TaskService`, nên `TARGET_IS_IMPL=true`.
- `SAME_OBJECT=false` minh họa proxy và target là hai object khác nhau theo cấu hình Spring AOP chuẩn trong ví dụ.

Dù hai kiểu proxy khác nhau, lời gọi qua proxy vẫn được `@Around` advice intercept và `pjp.proceed()` đưa lời gọi đi tiếp tới method target. Chương trình không cần biết tên lớp proxy do runtime sinh.

## 6. Dùng `this(...)` và `target(...)` trực tiếp trong pointcut

Dưới đây là những **đoạn minh họa độc lập về pointcut**, không ghép đồng thời vào một aspect nếu muốn giữ stdout phần 5 nguyên vẹn.

### 6.1. Lọc theo interface mà proxy công bố

```java
@Before("execution(* demo..*.perform(..)) && this(demo.TaskApi)")
public void onlyApiProxyCalls() {
    System.out.println("THIS(TaskApi)");
}
```

Trong một ứng dụng có top-level interface `demo.TaskApi`, đoạn này khớp ở cả JDK và CGLIB nếu proxy expose `TaskApi`. Nếu sử dụng interface lồng bên trong class như ví dụ phần 5, cú pháp tên nested type trong biểu thức AspectJ cần được điều chỉnh theo tên Java/AspectJ hợp lệ; không copy đoạn top-level này nguyên xi và giả định kiểu đó đã tồn tại.

### 6.2. Lọc theo class implementation của target

```java
@Before("execution(* demo..*.perform(..)) && target(demo.TaskService)")
public void onlyTaskTargetCalls() {
    System.out.println("TARGET(TaskService)");
}
```

Điều kiện này khớp ở cả hai proxy strategy nếu target thực sự là `demo.TaskService`. Tên class ở đây là **kiểu top-level minh họa**; project runnable phần 5 định nghĩa nested type `ThisTargetDemo.TaskService`.

### 6.3. Điều kiện khiến JDK và CGLIB có kết quả khác nhau

```java
@Before("execution(* demo..*.perform(..)) && this(demo.TaskService)")
public void onlyImplSubtypeProxyCalls() {
    System.out.println("THIS(TaskService)");
}
```

Với target `TaskService implements TaskApi` và proxy strategy như đã mô tả, advice chỉ thỏa khi **proxy là subtype của `TaskService`**, tức trường hợp CGLIB. Trong JDK dynamic proxy mode, client gọi được `perform()` qua interface nhưng pointcut `this(TaskService)` không khớp.

**Không suy rộng một cách máy móc:** nếu Spring proxy công bố interface khác, target là subclass khác, dùng scoped proxy hoặc nhiều lớp proxy chồng nhau, kiểm tra runtime và target type thực tế trước khi kết luận.

## 7. Ràng buộc proxy và target vào tham số advice

Spring hỗ trợ **binding form** của hai designator bằng tên tham số, giúp advice nhận object đang match:

```java
@Aspect
@Component
public class BindingAspect {

    @Before(
        value = "execution(* demo..*.perform(..)) && this(proxy)",
        argNames = "proxy"
    )
    public void beforeProxy(TaskApi proxy) {
        // proxy là tham chiếu Spring AOP proxy được bind.
    }

    @Before(
        value = "execution(* demo..*.perform(..)) && target(service)",
        argNames = "service"
    )
    public void beforeTarget(TaskService service) {
        // service là target object được bind.
    }
}
```

Đây là **mẫu minh họa cần các top-level type và imports/scan phù hợp**, không phải class độc lập runnable. Ý nghĩa:

- `this(proxy)` kết hợp với tham số `TaskApi proxy` ràng buộc proxy phù hợp `TaskApi`.
- `target(service)` kết hợp với `TaskService service` ràng buộc target phù hợp `TaskService`.
- Tên trong biểu thức phải được Spring nhận diện đúng với tên tham số; `argNames` giúp tránh phụ thuộc vào việc trình biên dịch có lưu parameter names.
- Tham số nhận được ở advice là **đối tượng thực tế** do Spring AOP cung cấp; nó không phải bản sao trạng thái của target.

Nếu chỉ cần đọc thông tin kiểu hoặc tham số ngay tại join point, có thể sử dụng `ProceedingJoinPoint.getThis()` và `getTarget()` như phần 5. Nếu cần thể hiện điều kiện rõ tại pointcut level, sử dụng `this(Type)` và `target(Type)`.

### Chú ý đối với JDK proxy và injection type

Nếu một advice sử dụng `this(proxy)` nhưng khai báo tham số kiểu concrete implementation, JDK proxy **không** phải instance implementation và điều kiện không khớp. Ngược lại, `target(service)` với tham số kiểu implementation có thể khớp vì target object có đúng kiểu đó.

Đừng ép kiểu `pjp.getThis()` sang implementation class khi chương trình cho phép JDK dynamic proxy. Nên dùng interface cho caller và những tham số binding cần tương thích cả hai chiến lược.

## 8. Phân biệt `this`/`target` với các designator khác

Trong Spring AOP, những biểu thức dưới đây có ý nghĩa khác nhau:

| Designator | Căn cứ match | Ví dụ dùng |
| --- | --- | --- |
| `this(Type)` | **Kiểu của proxy object** | Advice chỉ khi proxy là instance của một interface |
| `target(Type)` | **Kiểu của target object** | Advice cho bean có target thuộc một implementation/base type |
| `execution(...)` | **Method execution signature** | Chỉ advice các method `pay(..)` ở package service |
| `within(TypePattern)` | **Kiểu khai báo nằm trong phạm vi pattern** | Hạn chế method execution theo package/lớp |
| `args(Type)` | **Kiểu runtime của tham số truyền vào** | Chọn invocation có tham số thuộc một kiểu |
| `@annotation(Annotation)` | **Annotation trên method execution phù hợp** | Chọn method được gắn một annotation xác định |
| `@target(Annotation)` | **Annotation trên class của target theo matcher** | Chọn target có class mang annotation |
| `@within(Annotation)` | **Annotation trên kiểu khai báo method execution phù hợp** | Chọn execution trong phạm vi kiểu có annotation |

Hai cặp dễ nhầm:

- **`target(Type)` và `@target(Annotation)`:** cái trước kiểm tra quan hệ kiểu Java của target object; cái sau dựa annotation.
- **`this(Type)` và `within(TypePattern)`:** cái trước xét proxy instance; cái sau giới hạn vị trí khai báo kiểu được pointcut matcher sử dụng.

Các biểu thức `call(...)`, `get(...)`, `set(...)` thuộc nhóm AspectJ pointcuts rộng hơn nhưng **không được Spring AOP proxy hỗ trợ để intercept method call site, field read/write**. Spring AOP tập trung vào *method execution join points* được gọi qua proxy.

Một biểu thức practical kết hợp đúng trách nhiệm của từng designator:

```java
@Around(
    "execution(public * demo..service..*Service.*(..)) " +
    "&& target(demo.service.PaymentService)"
)
public Object profile(ProceedingJoinPoint pjp) throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        System.out.println("elapsedNs=" + (System.nanoTime() - start));
    }
}
```

Đây là **method mẫu**, không phải chương trình chạy độc lập. Nó dùng `execution` để giới hạn method và `target` để giới hạn target type; return/exception từ `proceed()` tiếp tục ra caller. Giá trị thời gian phụ thuộc môi trường nên không có stdout cố định.

## 9. Self-invocation và hai khái niệm `this` khác nhau

Giả sử Spring đã tạo proxy cho bean:

```java
public class PaymentServiceImpl implements PaymentService {

    @Override
    public String pay(String id) {
        return save(id);
    }

    public String save(String id) {
        System.out.println("TARGET save " + id);
        return "OK:" + id;
    }
}
```

Đây là minh họa một method gọi method khác **trên cùng target object**. Nếu client gọi `proxy.pay("A")`, advice cho `pay()` có thể chạy. Nhưng khi target `pay()` chạy, lời gọi `save(id)` tương đương `this.save(id)` là lời gọi Java trong target, không quay lại Spring AOP proxy. Advice chỉ match `save()` không được chạy trong đường gọi nội bộ này.

```text
Client --> proxy.pay()
              |
              v
          advice(pay)
              |
              v
          target.pay()
              |
              | Java this.save()
              v
          target.save()
       (không qua proxy lần hai)
```

Ở đây:

- **Pointcut `this(Type)`** được đánh giá khi Spring AOP đang xử lý join point đi qua proxy.
- **Java `this`** trong `target.pay()` là target instance thực thi phương thức.
- Dù target có subtype/kiểu trùng với proxy class-related types, đường gọi `this.save()` vẫn không tự thêm một proxy boundary.

Nếu cần interceptor cho `save()` khi gọi từ `pay()`, cách dễ hiểu là **tách `save()` sang Spring bean khác rồi inject bean đó**; caller gọi sang một Spring proxy riêng. Có các kỹ thuật gọi lại proxy từ self-reference hoặc `AopContext.currentProxy()` với `exposeProxy=true`, nhưng chúng tạo ràng buộc với Spring AOP và cần cân nhắc thiết kế.

## 10. Khi nào nên chọn `this`, khi nào chọn `target`?

**Chọn `this(Type)` khi điều kiện thật sự phụ thuộc loại object mà Spring đã cấp cho client.** Ví dụ muốn giới hạn advice cho một proxy implement interface `ExternalApi`. Trường hợp này phù hợp với việc suy nghĩ theo **contract của proxy**. Lưu ý nếu thay cấu hình JDK → CGLIB, một pointcut ràng buộc implementation class qua `this(Implementation)` có thể thay kết quả match.

**Chọn `target(Type)` khi điều kiện nên đi theo lớp/kiểu của đối tượng nghiệp vụ.** Ví dụ chỉ advice những Spring beans có target implement `PaymentService` hoặc thuộc lớp `PaymentServiceImpl`, bất kể proxy strategy. Dù vậy, advice vẫn chỉ chạy ở những method execution mà proxy có thể intercept.

**Không dùng chúng chỉ vì trông giống nhau trên CGLIB.** Trên một CGLIB proxy, nhiều điều kiện `this(Type)` và `target(Type)` cùng trả true, nhưng khi cấu hình đổi về JDK proxy, sự khác biệt có thể xuất hiện và khiến advice không chạy.

Đối với một service layer, pointcut thường dễ bảo trì khi kết hợp **method execution scope** với **target type hoặc interface contract** phù hợp. Nếu ý định chỉ là “method trên một nhóm package”, `execution(...)` hoặc `within(...)` có thể diễn đạt trực tiếp hơn việc lạm dụng `this(...)`.

## 11. Các trường hợp đặc biệt và giới hạn

### 11.1. Bean không được proxy

Không phải mọi Spring bean đều có AOP proxy. Chỉ khai báo `@Aspect` hoặc `@EnableAspectJAutoProxy` chưa đủ để biến **mọi bean** thành proxy. Spring phải nhận diện advisor phù hợp và proxy được tạo. Nếu client nắm target trực tiếp mà không qua AOP, không có Spring AOP interception ở đường gọi đó.

### 11.2. CGLIB không thể intercept mọi method

CGLIB sinh subclass nên không thể override `final` hoặc `private` method, và không thể tạo subclass cho `final class`. Không nên suy rằng `this(Implementation)` khớp thì mọi method của implementation đều advice được.

### 11.3. JDK proxy không công bố method riêng ngoài interface

JDK proxy implement các interface được cấu hình/công bố. Một public method chỉ có trên implementation nhưng không nằm trên interface proxy thường không thể được client gọi qua kiểu implementation của JDK proxy. `target(Implementation)` khớp về đối tượng thật **không mở rộng API JDK proxy**.

### 11.4. Scoped proxy, proxy lồng nhau và dynamic TargetSource

Ví dụ bài học dùng một singleton target đơn giản được auto-proxy một lần. Spring cũng có thể dùng scoped proxies, proxy lồng nhau hoặc dynamic target source; lúc đó **target object có thể khác theo invocation**, các proxy layer có thể khác nhau và cần xác minh rõ bạn đang kiểm tra proxy nào.

Các helper như `AopUtils.getTargetClass(bean)` hỗ trợ nhận diện target class của Spring AOP proxy trong những tình huống thông thường, nhưng không nên dùng `bean.getClass()` đơn lẻ làm cơ sở suy mọi quan hệ proxy/target trong cấu hình phức tạp.

### 11.5. `@Aspect` bean và tự advice chính nó

Một Spring `@Aspect` bean được container quản lý để cung cấp pointcut/advice, nhưng Spring AOP auto-proxy thông thường loại aspect bean khỏi target auto-proxy. Vì vậy không nên kỳ vọng `this(AspectClass)` hoặc `target(AspectClass)` tự khiến một aspect khác chặn method trên chính `@Aspect` bean đó.

### 11.6. Type name trong pointcut có thể khác Java nested-type syntax

Trong project mẫu, `TaskApi` và `TaskService` được khai báo là các nested types của `ThisTargetDemo`. Khi viết biểu thức pointcut sử dụng **qualified type name**, cần tuân thủ cú pháp type pattern AspectJ cho nested type. Các snippet `demo.TaskApi` / `demo.TaskService` ở phần 6–7 cố ý mô tả trường hợp hai type **top-level** để tránh gắn một tên không tồn tại vào project runnable. Nếu muốn thử trực tiếp với project phần 5, chuyển type thành top-level files hoặc sử dụng tên type chính xác và test pointcut parser.

## 12. Quy trình debug `this` / `target` pointcut không chạy

1. **Lấy bean từ Spring context**, không tự `new` object để so kết quả.
2. **Xác nhận là AOP proxy** bằng `AopUtils.isAopProxy(bean)`.
3. **Phân biệt loại proxy** bằng `AopUtils.isJdkDynamicProxy(bean)` và `isCglibProxy(bean)`.
4. **Kiểm tra object runtime** bằng `bean instanceof Api`, `bean instanceof Impl`, hoặc `type.isInstance(bean)`.
5. **Tìm target class** bằng `AopUtils.getTargetClass(bean)`. Kết quả proxy class và target class có thể khác.
6. **Kiểm tra pointcut** có `execution(...)` khớp method/visibility/package không, trước khi xét điều kiện `this/target`.
7. **Kiểm tra điều kiện `this(Type)`**: Type có thực sự là interface/subtype của **proxy** không?
8. **Kiểm tra điều kiện `target(Type)`**: target object phía sau proxy có thực sự là instance của Type không?
9. **Kiểm tra đường gọi**: self-invocation, object ngoài Spring và method không intercept được không được cứu bằng cách đổi designator.
10. **Kiểm tra context/proxy strategy hiệu lực**: Spring Framework mặc định và Spring Boot auto-configuration có thể dùng strategy khác nhau; dựa vào runtime, không chỉ dựa một property.

Một log hữu ích trong một `@Around` advice:

```java
Object proxy = pjp.getThis();
Object target = pjp.getTarget();

System.out.println("proxyClass=" + proxy.getClass().getName());
System.out.println("targetClass=" + target.getClass().getName());
System.out.println("sameReference=" + (proxy == target));
```

Đây là **snippet bổ sung**, cần `pjp` của advice. Tên class sẽ tùy runtime; trong chương trình tự động, nên assert dựa trên `instanceof` và `AopUtils` thay vì hardcode tên generated proxy.

## 13. Tự kiểm tra

**Câu 1.** Target `InvoiceServiceImpl implements InvoiceService`, Spring AOP dùng JDK proxy. `this(InvoiceServiceImpl)` có khớp một method public đã được proxy intercept không?  
**Đáp án:** Không, vì object proxy không phải implementation subtype. `target(InvoiceServiceImpl)` thì khớp khi target đúng kiểu đó.

**Câu 2.** Cùng bean chuyển sang CGLIB proxy. `this(InvoiceServiceImpl)` có thể khớp không?  
**Đáp án:** Có, vì CGLIB proxy subclass của implementation class, nếu method và pointcut đủ điều kiện.

**Câu 3.** `pjp.getThis()` và `pjp.getTarget()` là cùng một object trong ví dụ Spring AOP chuẩn không?  
**Đáp án:** Không. `getThis()` là AOP proxy; `getTarget()` là object target đứng sau proxy.

**Câu 4.** Có thể sửa self-invocation bằng cách viết pointcut `target(Implementation)` thay cho `this(Implementation)` không?  
**Đáp án:** Không. Self-invocation không đi vào Spring proxy để pointcut được đánh giá cho lời gọi nội bộ.

**Câu 5.** Target implement interface `PaymentApi` và proxy JDK implement `PaymentApi`. Hai điều kiện `this(PaymentApi)` và `target(PaymentApi)` khác nhau về ý nghĩa chứ?  
**Đáp án:** Có. Dù cả hai có thể khớp, `this` xét proxy, `target` xét target.

**Câu 6.** `@target(Audited)` có giống `target(Audited)` không?  
**Đáp án:** Không. `@target` xét annotation trên target class; `target` xét quan hệ kiểu Java.

**Câu 7.** Một Spring bean không có AOP proxy, gọi method trực tiếp nhưng target class phù hợp `target(MyType)`. Spring AOP tự chạy advice không?  
**Đáp án:** Không. Phải có lời gọi mà Spring AOP thực sự intercept thông qua proxy phù hợp.

**Câu 8.** Một class `final` có business interface và được proxy bằng JDK, `target(FinalImplementation)` có thể khớp không?  
**Đáp án:** Có thể, vì target vẫn thuộc class đó, còn proxy là object JDK implement interface. Không suy rằng target class final làm JDK proxy hoàn toàn bất khả thi.

## 14. Tài liệu Spring chính thức

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `this`, `target`, `args`, `@target` và quy tắc match trong Spring AOP.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `JoinPoint.getThis()`, `getTarget()`, `@Around` và `proceed()`.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): cơ chế JDK/CGLIB, proxy/target và self-invocation.
- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/pointcuts.html): Spring pointcut matching và method interception.
