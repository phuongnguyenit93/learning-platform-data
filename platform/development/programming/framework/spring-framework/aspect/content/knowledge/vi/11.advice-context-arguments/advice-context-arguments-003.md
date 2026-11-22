# MethodSignature và việc lấy thông tin phương thức trong Spring AOP

## 1. Mục đích

Khi một advice trong Spring AOP chạy, nó thường cần biết **Spring bean method nào đang được gọi**, kiểu tham số, kiểu trả về, lớp khai báo hoặc annotation gắn trên method để thực hiện audit, tracing và metrics. Thay vì suy từ tên object proxy hoặc phân tích chuỗi log, Spring Aspect có thể đọc metadata một cách có kiểu thông qua `org.aspectj.lang.reflect.MethodSignature`.

Ví dụ đặt **bên trong Spring @Aspect bean**:

~~~java
@Before("execution(* demo..service..*(..))")
public void before(JoinPoint joinPoint) {
    MethodSignature signature =
            (MethodSignature) joinPoint.getSignature();

    String methodName = signature.getName();
    Class<?> returnType = signature.getReturnType();
    Class<?>[] types = signature.getParameterTypes();
    Method method = signature.getMethod();
}
~~~

Đây là snippet minh họa, không phải Java class hoàn chỉnh: cần import `org.aspectj.lang.JoinPoint`, `org.aspectj.lang.annotation.Before`, `org.aspectj.lang.reflect.MethodSignature` và `java.lang.reflect.Method`. Trong Spring AOP, join point được advice là **method execution của Spring-managed bean**, được gọi qua JDK/CGLIB proxy; nó không bao phủ mọi method trên mọi Java object.

**Phạm vi:** chỉ tập trung cách khai thác `MethodSignature` trong Spring Aspect, khác biệt giữa method metadata và runtime arguments, cách tìm đúng method triển khai khi proxy theo interface, lỗi thường gặp và ví dụ Spring Framework chạy được. Không bàn lại lý thuyết AspectJ bytecode weaving.

## 2. Phân biệt những đối tượng trong một Spring AOP advice

| Kiểu | API | Thông tin/công dụng |
| --- | --- | --- |
| `JoinPoint` | `org.aspectj.lang.JoinPoint` | Invocation context, signature, proxy, target và runtime argument values |
| `ProceedingJoinPoint` | `org.aspectj.lang.ProceedingJoinPoint` | Dành cho `@Around`, kế thừa JoinPoint và cho gọi `proceed(...)` |
| `Signature` | `org.aspectj.lang.Signature` | Tên, modifiers, declaring type và các dạng hiển thị chữ ký |
| `MethodSignature` | `org.aspectj.lang.reflect.MethodSignature` | Kiểu signature dành riêng cho method execution: Java Method, parameter types/names, return type, exception types |
| `Method` | `java.lang.reflect.Method` | Java reflection: annotation, declaring class, generic types, modifiers và bridge method |

Sơ đồ:

~~~text
Spring bean caller
       |
       v
   AOP proxy --------> target method
       |
       v
@Aspect advice(JoinPoint point)
       |
       +-- point.getThis()       : proxy reference
       +-- point.getTarget()     : target object
       +-- point.getArgs()       : giá trị runtime
       +-- point.getSignature()  : Signature
                                    |
                                    v
                             MethodSignature
                               |        |
                         getMethod()  getReturnType()
                               |
                               v
                     java.lang.reflect.Method
~~~

**MethodSignature mô tả chữ ký**, còn `JoinPoint.getArgs()` chứa **giá trị của từng đối số tại invocation**. Ví dụ method `greet(String name, int times)` khai báo `String,int`, nhưng một lần caller có thể truyền `"Ada", 2`. Không đánh đồng loại tham số với giá trị tham số.

Một phân biệt nữa: `getThis()` thường đại diện AOP proxy; `getTarget()` đại diện đối tượng đích mà proxy ủy quyền tới. Trong JDK proxy, chúng không cùng class. Điều này tác động lớn đến cách đọc method annotation và declaring type.

## 3. Các MethodSignature API đáng dùng

### 3.1. Tên và declaring type

~~~java
MethodSignature s = (MethodSignature) point.getSignature();

String name = s.getName();
Class<?> declaredIn = s.getDeclaringType();
String qualifiedType = s.getDeclaringTypeName();
int modifiers = s.getModifiers();
boolean isPublic = java.lang.reflect.Modifier.isPublic(modifiers);
~~~

`getName()` trả tên method, chẳng hạn `greet`. `getDeclaringType()` và `getDeclaringTypeName()` cho kiểu xuất phát từ **signature mà proxy đang xử lý**; với JDK dynamic proxy có thể là một interface, không nhất thiết là implementation class. `getModifiers()` là tập cờ Java modifiers, có thể dùng `java.lang.reflect.Modifier` để diễn giải.

`s.toShortString()`, `s.toLongString()` và `s.toString()` thuận tiện cho log chẩn đoán. **Không parse các chuỗi hiển thị đó bằng regex** để xây định danh ổn định: định dạng string có thể phụ thuộc library version; hãy lấy `name`, `declaringType`, `parameterTypes` riêng.

### 3.2. Kiểu trả về và ngoại lệ khai báo

~~~java
Class<?> returnType = s.getReturnType();
Class<?>[] declaredExceptions = s.getExceptionTypes();
~~~

`getReturnType()` mô tả **kiểu trả về đã khai báo**: `String.class` cho `String greet(...)`, `void.class` cho `void send()`, `int.class` cho `int sum(...)`. Nó không phải object kết quả của một invocation. Nếu method khai báo `List<String>`, raw class thông thường là `List.class` chứ không bảo toàn `String` element type.

`getExceptionTypes()` mô tả các exception trong **throws declaration** của method; nó không cho biết method thực sự đã ném lỗi nào. Muốn đọc giá trị trả về thì dùng `@AfterReturning(returning="...")`; muốn đọc exception đã ném thì dùng `@AfterThrowing(throwing="...")` hoặc `@Around` khi yêu cầu điều khiển flow thực sự tồn tại.

### 3.3. Kiểu tham số và tên tham số

~~~java
Class<?>[] parameterTypes = s.getParameterTypes();
String[] parameterNames = s.getParameterNames();
Object[] argumentValues = point.getArgs();
~~~

- `parameterTypes` có các `Class<?>` theo thứ tự khai báo: `String.class` và `int.class` trong ví dụ.
- `parameterNames` có thể chứa tên như `name`/`times`, nhưng **không được bảo đảm luôn tồn tại** với mọi bytecode/proxy.
- `argumentValues` là giá trị runtime, ví dụ `["Ada", 2]`; primitive `int` được boxed thành `Integer` trong `Object[]`.

Bật compiler flag `-parameters` khi kiểm soát project Java 17+. Mặc dù vậy, vẫn viết code có fallback khi `getParameterNames()` trả `null` hoặc metadata không đầy đủ. Tránh tạo logging/audit schema quan trọng chỉ phụ thuộc tên tham số của một third-party dependency.

### 3.4. Java reflection Method

~~~java
Method method = s.getMethod();
String name = method.getName();
Class<?> declaringClass = method.getDeclaringClass();
Class<?>[] formalTypes = method.getParameterTypes();
java.lang.reflect.Type genericType = method.getGenericReturnType();
~~~

`getMethod()` là cầu nối để đọc annotation, modifiers, type/generic metadata, `isBridge()` và `isSynthetic()`. Tuy nhiên, **đừng tự giả định `getMethod()` luôn trả method trên target implementation**: khi dùng JDK proxy, nó có thể là method khai báo trên interface.

Điểm này rất quan trọng nếu annotation audit chỉ đặt trên method triển khai: `method.getAnnotation(AuditTag.class)` có thể `null` khi `method` xuất phát từ interface.

## 4. Vấn đề JDK proxy: tìm method triển khai để lấy annotation

Giả sử interface `GreetingPort` có:

~~~java
public interface GreetingPort {
    String greet(String name, int times);
}
~~~

Implementation có annotation:

~~~java
public class GreetingService implements GreetingPort {
    @AuditTag("greeting")
    @Override
    public String greet(String name, int times) {
        return "Hello " + name + " x" + times;
    }
}
~~~

Hai đoạn trên là minh họa riêng; source hoàn chỉnh ở phần 5. Nếu Spring AOP chọn **JDK dynamic proxy**, interface method và implementation method là hai đối tượng Java reflection `Method` khác nhau. Annotation nằm trên implementation method, không tự lan sang interface method.

**Cách đọc không đủ an toàn:**

~~~java
MethodSignature s = (MethodSignature) point.getSignature();
AuditTag tag = s.getMethod().getAnnotation(AuditTag.class);
// Có thể null dù implementation method có @AuditTag.
~~~

**Cách Spring-native:**

~~~java
MethodSignature s = (MethodSignature) point.getSignature();

Method methodOnSignature = s.getMethod();
Class<?> targetClass = point.getTarget().getClass();

Method targetMethod = org.springframework.aop.support.AopUtils
        .getMostSpecificMethod(methodOnSignature, targetClass);

AuditTag tag = targetMethod.getAnnotation(AuditTag.class);
~~~

`AopUtils.getMostSpecificMethod(method, targetClass)` tìm method tương ứng trên target class nếu có; nó còn xử lý vấn đề bridge method theo tài liệu Spring. Với ví dụ `GreetingService`, method đích được tìm thấy sẽ chứa `@AuditTag`.

Điểm cần nhớ:

1. `point.getTarget()` là target trong Spring AOP invocation thông thường; đừng lấy `point.getThis().getClass()` là generated proxy class rồi tìm trực tiếp annotation tại đó.
2. Nếu method trên interface không có implementation method cụ thể hoặc target class không resolve được, helper có thể trả method ban đầu; nên viết fallback thích hợp.
3. `target.getClass()` có thể liên quan custom target source/đối tượng đặc biệt; code library tổng quát nên kiểm tra `getTarget()!=null`.
4. Khi annotation nằm trên interface chứ không phải implementation, cần xác định rõ chính sách đọc annotation trên **cả hai vị trí**, thay vì mặc định annotation ở đâu cũng “inherited”.
5. Helper tìm method **không tự làm advice match**. Pointcut phải match và invocation phải qua Spring proxy trước khi code trong advice có cơ hội chạy.

### Tìm custom meta-annotation theo Spring

~~~java
AuditTag tag =
    org.springframework.core.annotation.AnnotatedElementUtils
        .findMergedAnnotation(targetMethod, AuditTag.class);
~~~

`findMergedAnnotation` có ích khi project dùng Spring composed/meta-annotations hoặc aliasing phù hợp. Khác với `getAnnotation` của Java reflection thuần; **không** có nghĩa nó luôn đọc được mọi annotation trong mọi interface hierarchy hay đúng bằng semantics của `@annotation(...)` pointcut. Nếu yêu cầu interface annotation fallback:

~~~java
AuditTag tag = AnnotatedElementUtils.findMergedAnnotation(
        targetMethod, AuditTag.class);
if (tag == null) {
    tag = AnnotatedElementUtils.findMergedAnnotation(
            methodOnSignature, AuditTag.class);
}
~~~

Đây là hai snippet minh họa dùng các biến/import đã giải thích. Ưu tiên implementation trước, interface sau là **chính sách cụ thể của ví dụ**, không phải một quy tắc phổ quát cho mọi annotation hệ thống. Với Spring Boot/Spring Framework app lớn, viết integration test cho placement annotation thực tế.

## 5. Project Java 17+ Spring Framework 6.2: ví dụ chạy được

Chương trình sẽ dùng **JDK interface proxy**, một custom `@AuditTag` nằm **chỉ trên implementation method**, một `@Before` advice đọc `MethodSignature` và annotation, cùng lời gọi method không match để so sánh.

Cấu trúc:

~~~text
spring-method-signature/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── AuditTag.java
    ├── GreetingPort.java
    ├── GreetingService.java
    └── MetadataAspect.java
~~~

Yêu cầu JDK 17+, Maven 3.9+, Spring Framework **6.2.0**, AspectJ Weaver **1.9.22**. Các version cố định để học; không khẳng định đây là bản mới nhất. Không cần AspectJ weaving/javaagent.

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-method-signature</artifactId>
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
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` chứa IoC/Java config; `spring-aop` có `AopUtils` và auto-proxy framework; `aspectjweaver` hỗ trợ Spring phân tích kiểu `@AspectJ` pointcut, **không tự kích hoạt weaving**. `<parameters>true</parameters>` cung cấp tên tham số compile-time nhưng không phải yếu tố quyết định stdout bên dưới.

### 5.2. Annotation đánh dấu implementation method

Tạo `src/main/java/demo/AuditTag.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AuditTag {
    String value();
}
~~~

`RUNTIME` retention để có thể đọc khi advice inspect `Method`. `METHOD` target để annotation chỉ đánh dấu method. `value` mang tag dùng cho audit.

### 5.3. Interface và implementation

`src/main/java/demo/GreetingPort.java`:

~~~java
package demo;

public interface GreetingPort {
    String greet(String name, int times);
    String echo(String message);
}
~~~

`src/main/java/demo/GreetingService.java`:

~~~java
package demo;

public class GreetingService implements GreetingPort {
    @AuditTag("greeting")
    @Override
    public String greet(String name, int times) {
        System.out.println("TARGET: greet " + name + " x" + times);
        return "Hello " + name + " x" + times;
    }

    @Override
    public String echo(String message) {
        System.out.println("TARGET: echo " + message);
        return message;
    }
}
~~~

Annotation **chỉ có ở implementation** `GreetingService.greet`. Cả `greet` và `echo` thuộc cùng interface, nhưng pointcut phía dưới chỉ chọn `greet`. Method `echo` giúp xác nhận mọi lời gọi qua Spring proxy không tự trở thành một advice event.

### 5.4. Aspect sử dụng MethodSignature

`src/main/java/demo/MetadataAspect.java`:

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;

@Aspect
public class MetadataAspect {
    private final AtomicInteger adviceCount = new AtomicInteger();

    @Before("execution(* demo.GreetingPort.greet(..))")
    public void inspect(JoinPoint point) {
        if (!(point.getSignature() instanceof MethodSignature sig)) {
            throw new IllegalStateException("Not a method join point");
        }

        Method method = sig.getMethod();
        Class<?> targetClass = point.getTarget().getClass();

        Method actual = AopUtils.getMostSpecificMethod(
                method, targetClass);

        AuditTag tag = AnnotatedElementUtils.findMergedAnnotation(
                actual, AuditTag.class);
        if (tag == null) {
            throw new IllegalStateException("Missing annotation");
        }

        String formalTypes = Arrays.stream(actual.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));

        String methodInfo =
                actual.getDeclaringClass().getSimpleName()
                + "." + actual.getName()
                + "(" + formalTypes + ")->"
                + actual.getReturnType().getSimpleName();

        adviceCount.incrementAndGet();
        System.out.println("METHOD: " + methodInfo);
        System.out.println("TAG: " + tag.value());
        System.out.println("ARGS: " + Arrays.toString(point.getArgs()));
    }

    public int count() {
        return adviceCount.get();
    }
}
~~~

Những ý quan trọng trong code:

1. `@Aspect` chỉ đánh dấu class; class này sẽ được đăng ký thành Spring bean qua `@Bean`.
2. `@Before` được chọn vì chỉ đọc/in trước target; không cần quyền can thiệp `proceed()` của `@Around`.
3. `point.getSignature()` được cast với `instanceof MethodSignature` để kiểm tra loại join point trong code.
4. `sig.getMethod()` có thể đến từ `GreetingPort`; helper `getMostSpecificMethod` xác định implementation method nếu có.
5. `actual.getParameterTypes()` và `actual.getReturnType()` trả kiểu khai báo; ghép thành `GreetingService.greet(String,int)->String` mà không phụ thuộc tên tham số.
6. `findMergedAnnotation(actual,AuditTag.class)` đọc tag `greeting` trực tiếp trên implementation method.
7. `point.getArgs()` trả giá trị runtime và có thể in `[Ada, 2]` (khác với `[String,int]`).
8. `AtomicInteger` chỉ tăng trong advice. Nếu `echo` không match, bộ đếm không tăng.
9. Không sử dụng `getParameterNames()` trong stdout vì giá trị có thể phụ thuộc metadata compiler/interface đã nạp.

Với production logging, tránh in mọi `getArgs()` một cách vô điều kiện: một trong các phần tử có thể chứa password, access token, số thẻ, dữ liệu cá nhân hoặc `toString()` có side effect. Demo chỉ có tên và một số nguyên không nhạy cảm.

### 5.5. Configuration và main method

`src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class App {
    @Bean
    public GreetingPort greetingPort() {
        return new GreetingService();
    }

    @Bean
    public MetadataAspect metadataAspect() {
        return new MetadataAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            GreetingPort service = context.getBean(GreetingPort.class);
            MetadataAspect aspect = context.getBean(MetadataAspect.class);

            boolean jdk = AopUtils.isJdkDynamicProxy(service);
            System.out.println("JDK_PROXY: " + jdk);

            String greeted = service.greet("Ada", 2);
            System.out.println("RESULT: " + greeted);

            String echoed = service.echo("ping");
            System.out.println("ECHO: " + echoed);

            int count = aspect.count();
            System.out.println("ADVICE_COUNT: " + count);

            if (!jdk || !"Hello Ada x2".equals(greeted)
                    || !"ping".equals(echoed) || count != 1) {
                throw new IllegalStateException(
                        "MethodSignature verification failed");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

`@EnableAspectJAutoProxy(proxyTargetClass = false)` cho phép JDK interface proxy khi bean có interface; không phải một mệnh lệnh buộc mọi bean đều dùng JDK proxy. Với project này, aspect có advisor match `greet` và `GreetingService implements GreetingPort`, nên JDK proxy là kết quả mong đợi. Chương trình kiểm tra thực tế bằng `AopUtils.isJdkDynamicProxy` và ném lỗi nếu điều kiện không đúng.

`new GreetingService()` được gọi **trong `@Bean` factory**; giá trị trả về được Spring quản lý và có thể được auto-proxy. Caller lấy reference thông qua `ApplicationContext`, không giữ một raw target reference khác để bỏ qua advice.

### 5.6. Lệnh chạy và stdout dự kiến

Chạy tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do code `System.out.println` tạo ra:

~~~text
JDK_PROXY: true
METHOD: GreetingService.greet(String,int)->String
TAG: greeting
ARGS: [Ada, 2]
TARGET: greet Ada x2
RESULT: Hello Ada x2
TARGET: echo ping
ECHO: ping
ADVICE_COUNT: 1
CHECK: PASS
~~~

Maven/SLF4J có thể in thêm dòng ngoài đoạn trên. Bản này mô tả **application stdout mong đợi khi project được chạy**; chưa phải biên bản thực thi Maven trên máy của người đọc.

Kết quả chứng minh:

- Service reference Spring trả về là JDK proxy.
- Method metadata resolution tìm đúng **implementation** thay vì mắc kẹt ở interface.
- `@AuditTag("greeting")` trên implementation được tìm thấy.
- `String,int` là **parameter types**, `[Ada, 2]` là **argument values**.
- Dòng advice xuất hiện trước business method; `echo` không có advice tương ứng.
- `ADVICE_COUNT: 1` xác nhận aspect chạy đúng một lần.
- `CHECK: PASS` chỉ xuất hiện khi kết quả kinh doanh, proxy type và advice count đáp ứng kỳ vọng.

## 6. Tái sử dụng MethodSignature theo loại advice

### 6.1. @Before: metadata trước invocation

~~~java
@Before("execution(* demo..service..*(..))")
public void before(JoinPoint jp) {
    MethodSignature signature =
            (MethodSignature) jp.getSignature();
    System.out.println(signature.getName());
}
~~~

Đây là method advice minh họa; package thực phải khớp expression. Khi chỉ cần đọc tên method và arguments trước business call, `@Before` là lựa chọn đơn giản hơn `@Around`.

### 6.2. @AfterReturning: metadata và kết quả thực

~~~java
@AfterReturning(
    pointcut = "execution(* demo..service..*(..))",
    returning = "value",
    argNames = "value"
)
public void afterReturning(JoinPoint jp, Object value) {
    MethodSignature s = (MethodSignature) jp.getSignature();
    System.out.println("Declared: " + s.getReturnType().getSimpleName());
    System.out.println("Actual: " + value);
}
~~~

`getReturnType()` là **declared return type**, còn `value` là actual return value trên nhánh method **trả về bình thường**. Nếu target ném exception, `@AfterReturning` không được gọi.

### 6.3. @AfterThrowing: metadata và exception thực

~~~java
@AfterThrowing(
    pointcut = "execution(* demo..service..*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterThrowing(JoinPoint jp, Throwable error) {
    MethodSignature s = (MethodSignature) jp.getSignature();
    System.out.println(s.getName() + " threw "
            + error.getClass().getSimpleName());
}
~~~

`error` là exception thực tế; `s.getExceptionTypes()` là các loại **khai báo trong method throws**. `@AfterThrowing` quan sát failure, không tự biến thrown exception thành successful result.

### 6.4. @Around: metadata và chuyển tiếp

~~~java
@Around("execution(* demo..service..*(..))")
public Object around(ProceedingJoinPoint jp) throws Throwable {
    MethodSignature s = (MethodSignature) jp.getSignature();
    System.out.println(s.getName());
    return jp.proceed();
}
~~~

`ProceedingJoinPoint` kế thừa `JoinPoint` nên có cùng API `getSignature()`. Khác với `@Before`, `@Around` có quyền bỏ qua `proceed()`, thay arguments/return hoặc ném lại exception. Đừng dùng quyền này chỉ để in tên method khi `@Before` đáp ứng đủ.

Nếu thực sự dùng `proceed(Object[])` để thay arguments, số phần tử của mảng mới trong **Spring AOP** phải tương ứng method target; `getParameterTypes()` giúp xác định signature, `getArgs()` giúp đọc current values. Đây là một bài toán khác với đơn thuần **lấy metadata**.

Các snippets trong mục 6 là **những lựa chọn độc lập**, không nên thêm tất cả vào `MetadataAspect` của project chính khi muốn output đúng như phần 5.

## 7. Overload, generic, bridge method và annotation placement

### 7.1. Method overload

Hai method này có cùng tên:

~~~java
public void dispatch(String code) {
}

public void dispatch(String code, int retries) {
}
~~~

`MethodSignature.getName()` trả `dispatch` trong cả hai. Nếu tạo metrics key chỉ từ tên, hai overload bị gộp sai. Dùng thêm parameter types:

~~~java
String types = java.util.Arrays
        .stream(s.getParameterTypes())
        .map(Class::getTypeName)
        .collect(java.util.stream.Collectors.joining(","));

String key = s.getDeclaringTypeName()
        + "#" + s.getName() + "(" + types + ")";
~~~

Đây là snippet trong advice đã có biến `MethodSignature s`. Cần quyết định key theo signature proxy hay implementation method; nếu muốn class target cụ thể, dùng method đã resolve.

### 7.2. Generic bridge

~~~java
interface Converter<T> {
    T convert(T value);
}

class StringConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.trim();
    }
}
~~~

Đây là snippet Java minh họa riêng. Java generics erasure có thể tạo **bridge method** ở implementation để duy trì polymorphism. `Method.isBridge()`/`isSynthetic()` cho biết một số đặc điểm reflection; `AopUtils.getMostSpecificMethod` xử lý bridge resolution cho metadata lookup theo tài liệu Spring. Nếu bạn tự dùng reflection `getDeclaredMethod` chỉ theo tên/arity, dễ gặp sai method hoặc thiếu annotation trên user-declared method.

### 7.3. Annotation trên interface vs implementation

Method annotation của Java không tự động kế thừa từ interface method xuống implementation method theo `@Inherited`; cơ chế `@Inherited` chủ yếu liên quan class annotations. Cần quy ước rõ:

- Đặt annotation trên implementation method: resolve target method rồi tìm annotation.
- Đặt annotation trên interface method: cần tìm tại interface method khi target method không có tag.
- Cần meta-annotation hoặc aliasing: cân nhắc `AnnotatedElementUtils.findMergedAnnotation`.
- Aspect dùng pointcut `@annotation(...)` để **chọn join point**: semantics matching không nhất thiết đồng nhất một cách máy móc với Spring merged annotation lookup trong method advice.

### 7.4. Method name, return type và runtime arguments có ý nghĩa khác nhau

| Thứ cần biết | Cách đọc | Ví dụ |
| --- | --- | --- |
| Tên method | `signature.getName()` | `greet` |
| Kiểu tham số | `signature.getParameterTypes()` | `String,int` |
| Tên tham số | `signature.getParameterNames()` | `name,times` (nếu metadata có) |
| Giá trị thực tế | `joinPoint.getArgs()` | `"Ada",2` |
| Kiểu trả về khai báo | `signature.getReturnType()` | `String` |
| Giá trị trả về thực tế | `@AfterReturning(returning=...)` | `Hello Ada x2` |
| Exceptions khai báo | `signature.getExceptionTypes()` | Kiểu trong `throws` |
| Exception thực tế | `@AfterThrowing(throwing=...)` | `IllegalStateException` nếu thực sự thoát ra |
| Java reflection Method | `signature.getMethod()` | Có thể là interface method |
| Method implementation | `AopUtils.getMostSpecificMethod(...)` | `GreetingService.greet` |
| Proxy vs target | `joinPoint.getThis()` / `getTarget()` | JDK proxy / GreetingService |

Bảng này giúp tránh nhầm **static metadata** với **dynamic invocation state**.

## 8. Lỗi thường gặp và hướng gỡ

**1. `ClassCastException` hoặc method metadata không phải implementation:** nếu dùng JDK proxy, reference và `Method` có thể gắn với interface. Không cast proxy xuống implementation class; dùng interface API cho caller và `AopUtils.getMostSpecificMethod` cho metadata.

**2. Annotation trả `null`:** kiểm tra nó nằm trên interface hay implementation. `signature.getMethod().getAnnotation(...)` có thể nhìn nhầm method; resolve target method rồi đọc. Nếu vẫn null, xem retention `RUNTIME`, annotation target `METHOD` và cấu hình meta-annotation.

**3. Parameter names bị thiếu:** bảo đảm `-parameters` được bật ở module chứa method; xem tên trên interface và implementation có đồng bộ không. Dù bật flag, luôn có fallback khi xử lý library bên thứ ba.

**4. Return type không giống loại object được trả:** declared type `List`/`Number` có thể khác runtime type `ArrayList`/`Integer`. `getReturnType()` không phải giá trị mà target đã trả; cần `@AfterReturning`/`@Around` cho outcome.

**5. Advice không chạy, nên không thấy metadata:** có thể do pointcut không khớp, aspect chưa đăng ký làm bean, object tự tạo ngoài Spring, bean chưa được auto-proxy hoặc self-invocation. Xác minh `AopUtils.isAopProxy` trên reference caller thực sự dùng. Không chuyển `@Before` thành `@Around` chỉ để mong method được intercept.

**6. `getDeclaringType()` không phải tên bean:** declaring type là lớp/interface khai báo chữ ký; một Spring class có thể có nhiều bean instances hoặc nhiều bean names. `MethodSignature` không tự mang bean name, request ID hay user identity.

**7. Log method signature bằng `toLongString()` rồi parse bằng regex:** cách này giòn, phụ thuộc format/version. Lấy accessor có kiểu và tự format stable key nếu cần.

**8. Nhật ký vô tình lộ dữ liệu:** `Arrays.toString(jp.getArgs())` trong ví dụ chỉ dùng dữ liệu học tập. Với production Spring AOP, chỉ log field đã được cho phép, áp dụng redaction và tránh gọi `toString` trên object nhạy cảm.

**9. Dùng `getExceptionTypes()` để đo failures:** đây là declared exceptions, không phải actual exceptions. Dùng `@AfterThrowing` với typed binding nếu cần metrics failure.

**10. Dùng reflection `Method.invoke` ngay trong advice để “gọi method thật”:** như vậy có thể làm thay đổi/đi vòng khỏi interceptor chain, dẫn tới double invocation hoặc mất transaction/cache/security. Trong `@Around` cần `ProceedingJoinPoint.proceed()` để tiếp tục chain theo đúng cơ chế Spring AOP; method reflection ở đây chỉ để **đọc metadata**.

## 9. Kiểm thử qua ApplicationContext

Khi cần kiểm thử `MethodSignature` trong Spring AOP, test phải gọi đúng **Spring bean proxy**. Việc tự tạo `new GreetingService()` chỉ kiểm tra logic Java, không tạo join point advice.

Có thể viết JUnit 5 integration test sau, sau khi bổ sung `junit-jupiter` và `maven-surefire-plugin` trong `pom.xml`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MethodSignatureTest {
    @Test
    void implementationAnnotationIsVisibleThroughJdkProxy() {
        try (var context =
                new AnnotationConfigApplicationContext(App.class)) {
            GreetingPort service = context.getBean(GreetingPort.class);
            MetadataAspect aspect = context.getBean(MetadataAspect.class);

            assertTrue(AopUtils.isJdkDynamicProxy(service));
            assertEquals("Hello Ada x2", service.greet("Ada", 2));
            assertEquals("ping", service.echo("ping"));
            assertEquals(1, aspect.count());
        }
    }
}
~~~

Đây là **file test Java hoàn chỉnh** nhưng không thể chạy chỉ bằng `pom.xml` tối thiểu ở phần 5 nếu chưa khai báo JUnit dependency và Surefire plugin. Trong test, `MetadataAspect` sẽ ném exception nếu không tìm được implementation annotation; vì thế test vừa kiểm tra advice thực thi, vừa kiểm tra metadata resolution đủ để không gặp lỗi.

Sau khi bổ sung test dependencies, chạy:

~~~bash
mvn clean test
~~~

Nếu muốn test riêng các method metadata, có thể dùng thêm `MethodSignature.getParameterTypes()` và `AopUtils.getMostSpecificMethod(...)` trực tiếp ở các integration test. Tuy nhiên, đọc method reflection ngoài context **không thay thế** việc thử Spring AOP advice thực tế đi qua JDK proxy.

## 10. Checklist khi viết Spring Aspect cần metadata method

- [ ] `@Aspect` class đã đăng ký như Spring bean; target là Spring bean đúng context.
- [ ] Caller gọi qua Spring proxy, không dùng raw object hoặc self-invocation để kiểm thử advice.
- [ ] Lấy `MethodSignature` từ `JoinPoint.getSignature()`; dùng `instanceof` khi helper cần an toàn.
- [ ] Đọc method name, return type, parameter types qua accessor; không parse string representation.
- [ ] Dùng `joinPoint.getArgs()` cho runtime values, không nhầm với parameter types/names.
- [ ] `getParameterNames()` được xử lý với fallback; `-parameters` bật khi phù hợp.
- [ ] Với JDK proxy, `getMethod()` có thể là method interface; không mặc định annotation ở đó.
- [ ] Resolve `AopUtils.getMostSpecificMethod(...)` trước khi tra annotation trên implementation.
- [ ] Phân biệt declared return type và actual return value; declared throws và actual thrown exception.
- [ ] Khi có overload/bridge/generic methods, test theo đúng proxy configuration của Spring.
- [ ] Hạn chế reflection và string construction trong hot-path advice; cache metadata theo `Method` nếu có nhu cầu và chính sách hợp lệ.
- [ ] Không log toàn bộ arguments nhạy cảm; xác định rõ mục tiêu observability.

## 11. Tài liệu chính thức

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `JoinPoint`/`ProceedingJoinPoint` và metadata trong Spring advice.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK proxy, CGLIB và self-invocation.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring AOP method execution trên managed beans.
- [AopUtils Javadoc — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/support/AopUtils.html): `getMostSpecificMethod` và bridge methods.
- [AnnotatedElementUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/annotation/AnnotatedElementUtils.html): annotation lookup hỗ trợ merged/composed metadata.
- [MethodSignature — AspectJ API](https://www.javadoc.io/doc/org.aspectj/aspectjrt/1.9.22/org/aspectj/lang/reflect/MethodSignature.html): các accessor `getMethod`, `getParameterTypes`, `getParameterNames`, `getReturnType` và `getExceptionTypes`.
