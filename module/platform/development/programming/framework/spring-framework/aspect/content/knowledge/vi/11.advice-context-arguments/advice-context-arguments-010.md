# Bridge method, phương thức interface và phương thức triển khai trong Spring AOP

## 1. Mục tiêu bài học

Một Spring bean có thể được truy cập qua **interface**, triển khai logic trong **implementation class**, và dùng **generic type**. Khi dùng Spring AOP, một lời gọi đơn giản như `processor.process("spring")` đôi khi liên quan tới ba đối tượng `java.lang.reflect.Method` khác nhau:

1. **Method trên interface** mà JDK dynamic proxy công bố.
2. **Method cụ thể trên implementation** thực hiện nghiệp vụ.
3. **Synthetic bridge method** do Java compiler tạo để bảo toàn overriding sau khi generic type erasure.

Chúng có thể cùng tên nhưng có **declaring class**, **parameter type**, **return type**, **annotation** và cờ `isBridge()` khác nhau. Nếu advice chỉ đọc `MethodSignature.getMethod()` rồi giả định đó luôn là method triển khai, logic tìm annotation hoặc chọn metadata dễ sai.

Sau bài này, bạn có thể:

- Phân biệt rõ **interface method**, **implementation method** và **bridge method** trong ngữ cảnh Spring AOP.
- Giải thích vì sao Java compiler tạo bridge cho `Processor<T>` và `TextProcessor implements Processor<String>`.
- Hiểu JDK dynamic proxy khác CGLIB ở cách expose method và điều gì có thể xuất hiện trong `MethodSignature`.
- Dùng **`AopUtils.getMostSpecificMethod(Method, Class<?>)`** để tìm method tương ứng trên target class, và **`BridgeMethodResolver.findBridgedMethod(Method)`** khi cần gỡ bridge.
- Xây một **`@Around` Spring aspect** ghi thông tin method đúng, không giả định chữ ký reflection luôn đến từ implementation.
- Kiểm tra annotation đặt ở interface so với annotation đặt ở implementation mà không khẳng định sai rằng mọi kiểu proxy luôn trả cùng metadata.
- Nhận diện nguy cơ ghi log/advice trùng, pointcut match sai, type erasure, self-invocation và method không nằm trong proxy interface.

**Phạm vi:** Tập trung vào **Spring Framework proxy-based AOP** và cách Spring xử lý method metadata tại một method-execution join point. Không đi sâu vào Java generics hoặc AspectJ weaving độc lập ngoài những gì cần thiết để hiểu Spring Aspect.

## 2. Ba lớp chữ ký thường gặp

Ví dụ Java:

~~~java
public interface Processor<T> {
    T process(T input);
}

public class TextProcessor implements Processor<String> {
    @Override
    public String process(String input) {
        return input.trim();
    }
}
~~~

Đây là **hai top-level types, đặt ở hai file Java khác nhau** nếu muốn biên dịch, và chưa phải toàn bộ ứng dụng Spring AOP của mục 7.

Ở source code, ta thấy:

- Interface: `T process(T input)`.
- Implementation: `String process(String input)`.

Nhưng do **type erasure**, chữ ký runtime của interface generic tương ứng với kiểu erased:

~~~text
Processor.process(Object) : Object
~~~

Trong implementation có method thật:

~~~text
TextProcessor.process(String) : String
~~~

Để một lời gọi qua interface erased vẫn hoạt động đúng với method đã override, compiler có thể sinh thêm bridge tương tự:

~~~java
// Pseudocode biểu diễn bytecode do compiler tạo,
// không chèn đoạn này trực tiếp vào TextProcessor.java.
public Object process(Object input) {
    return process((String) input);
}
~~~

Bridge method là **synthetic method của class file**, không phải method ứng dụng tự viết. Ví dụ có thể được phản chiếu bằng `Method.isBridge() == true` và `Method.isSynthetic() == true`. Method triển khai thật `process(String)` không mang cờ bridge.

Sơ đồ:

~~~text
Processor<String> proxy (JDK interface)
      |
      +-- process(Object) ở interface sau erasure
      |
      v
Spring AOP invocation
      |
      v
TextProcessor target
      |
      +-- bridge process(Object) (do javac tạo)
      |       |
      |       +-- chuyển String argument rồi gọi
      |           process(String)
      |
      +-- process(String) (method nghiệp vụ thực)
~~~

Sơ đồ là **mô hình lý giải chữ ký**, không bắt buộc mọi invocation Spring phải gọi cả hai method qua reflection theo đúng thứ tự. Spring AOP có thể **resolve method cụ thể/bridge** trước khi quyết định advisor và gọi target. Đừng suy ra có hai advice executions chỉ vì có bridge method.

## 3. Tại sao có bridge method?

Java generics phần lớn được triển khai bằng **type erasure**. Trước erasure, `Processor<String>.process(String)` nhìn như một method nhận và trả String. Sau erasure, bytecode của interface phải hỗ trợ `process(Object)`; implementation lại khai báo `process(String)`.

Nếu compiler không duy trì một đường gọi tương thích với erased interface method, Java polymorphism bị phá vỡ khi caller dùng reference kiểu generic interface. Bridge giải quyết việc đó.

Phân biệt:

| Thuộc tính | Interface method | Implementation method | Bridge method |
| --- | --- | --- | --- |
| Ví dụ | `Processor.process(Object)` | `TextProcessor.process(String)` | `TextProcessor.process(Object)` |
| Nguồn tạo | Định nghĩa interface generic | Developer viết | Compiler tạo |
| `getDeclaringClass()` | `Processor.class` | `TextProcessor.class` | `TextProcessor.class` |
| Parameter runtime | Object | String | Object |
| Return runtime | Object | String | Object |
| `isBridge()` | false | false | **true** |
| `isSynthetic()` | Thường false | Thường false | **true** trong ví dụ javac |
| Annotation ở implementation | Không tự có annotation đó | Có nếu khai báo | Không nên coi annotation bridge là nguồn chân lý |

Không nên chép/match tên method rồi tự suy đoán generic parameter. Với method có overload hoặc hierarchy, chỉ dùng `getName()` sẽ không phân biệt được:

~~~java
String process(String input);
String process(String input, int limit);
~~~

Điểm quan trọng là dùng **type + signature + target class** để resolve đúng method.

## 4. Spring AOP hoạt động qua proxy, không phải weave bytecode

Spring AOP dùng một proxy bao quanh Spring-managed target:

~~~text
Caller
  |
  v
JDK proxy hoặc CGLIB proxy
  |
  +-- Advisor / pointcut
  +-- @Before, @Around, @After... thích hợp
  |
  v
Target method
~~~

Hai kiểu proxy chủ yếu:

### 4.1. JDK dynamic proxy

Khi target có interface và cấu hình chọn JDK proxy, đối tượng nhận bởi caller triển khai các interface đã được proxy. Caller thường viết:

~~~java
Processor<String> processor = /* Spring-injected proxy */;
processor.process("hello");
~~~

Proxy **không phải một instance của `TextProcessor`**. Không ép kiểu proxy JDK về concrete class:

~~~java
// Có thể ClassCastException nếu bean là JDK dynamic proxy.
TextProcessor concrete = (TextProcessor) processor;
~~~

Method thông qua `MethodSignature.getMethod()` trong một invocation JDK proxy **có thể là method trên interface**, không phải method ứng dụng đã annotate trong implementation. Vì vậy metadata của interface có thể khác metadata của target.

### 4.2. Class-based CGLIB proxy

Khi cấu hình `@EnableAspectJAutoProxy(proxyTargetClass = true)` hoặc target không có interface phù hợp, Spring có thể dùng CGLIB class-based proxy.

Proxy là subclass của target và có thể override những method hợp lệ. Nhưng:

- Không proxy được `final` class bằng subclass.
- Không advice được `private`/`final` method bằng override.
- Method không visible để subclass override, ví dụ package-private trong superclass ở package khác, có thể không được advice.
- Self-invocation trên target vẫn bypass Spring proxy.
- Bridge/synthetic methods có thể hiện diện trong target class, nhưng không nên coi bridge là một operation riêng để thực hiện business advice lần thứ hai.

**Bật CGLIB không làm biến mất bridge method mà compiler đã tạo**, cũng không đảm bảo `MethodSignature.getMethod()` lúc nào có đúng annotation bạn cần. Khi đọc metadata, giải pháp bền vững là resolve target method rõ ràng.

### 4.3. Phân biệt JDK proxy và target

Các helper hữu ích:

~~~java
AopUtils.isAopProxy(bean);
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
AopUtils.getTargetClass(bean);
~~~

Trong đó `getTargetClass(bean)` trả class thực của target khi framework xác định được. Nó **không** mang nghĩa unwrap tất cả custom proxies trong mọi hệ thống. `pjp.getTarget()` trong advice chỉ target hiện tại, còn `pjp.getThis()` biểu diễn Spring AOP proxy.

## 5. MethodSignature và những giới hạn phải hiểu

Ở `@Around` advice, có thể lấy metadata:

~~~java
MethodSignature signature =
        (MethodSignature) pjp.getSignature();

Method invokedMethod = signature.getMethod();
~~~

`MethodSignature` là interface thuộc `org.aspectj.lang.reflect`; Spring AOP cung cấp thông tin join point theo contract đó. Trong JDK proxy, `invokedMethod` thường mô tả interface method; với CGLIB hoặc tình huống generic khác, declaring class/bridge status có thể khác.

**Không được mặc định**:

~~~java
// Sai giả định: method từ signature luôn là method khai báo
// trực tiếp trong TextProcessor và luôn mang annotation của implementation.
Method method = ((MethodSignature) pjp.getSignature()).getMethod();
boolean marked = method.isAnnotationPresent(TrackedOperation.class);
~~~

Nếu annotation chỉ xuất hiện trên `TextProcessor.process(String)`, phép kiểm tra trên `Processor.process(Object)` có thể trả false.

Hai đối tượng khác nhau:

- **Invoked method**: method mà AOP invocation/signature công bố tại vị trí proxy.
- **Most-specific target method**: method triển khai tương ứng trên target class, phù hợp để tìm metadata của implementation.

Đừng kết luận rằng chỉ cần `getMethod().getDeclaringClass()` là bạn đã tìm được concrete implementation type.

## 6. Hai API Spring quan trọng

### 6.1. AopUtils.getMostSpecificMethod

~~~java
Method resolved = AopUtils.getMostSpecificMethod(
        invokedMethod,
        targetClass
);
~~~

API thuộc `org.springframework.aop.support.AopUtils`. Nó tìm method trên target class tương ứng với method được cung cấp, ví dụ từ `Processor.process(Object)` về `TextProcessor.process(String)` trong trường hợp generic bridge được giải quyết.

Nó đặc biệt hữu ích khi phải truy tìm:

- Custom annotation đặt trên implementation method.
- Method signature đúng của target cho audit/metrics.
- Method cụ thể có generic return/parameter đã được bind.
- Chỗ thực sự định nghĩa nghiệp vụ trong class hierarchy.

Trong Spring Framework 6.2.x, helper này có khả năng xử lý **bridge resolution**; vì vậy không cần giả định nó sẽ trả bridge. Nếu cần làm rõ cho người đọc, vẫn có thể dùng `BridgeMethodResolver.findBridgedMethod(...)` an toàn trên kết quả.

### 6.2. BridgeMethodResolver.findBridgedMethod

~~~java
Method bridged =
        BridgeMethodResolver.findBridgedMethod(candidate);
~~~

API thuộc `org.springframework.core.BridgeMethodResolver`. Nếu `candidate` là bridge method, Spring cố tìm **method gốc tương ứng**. Nếu không phải bridge, API có thể trả lại method đầu vào; không bắt buộc gọi `isBridge()` trước.

**Hạn chế:** `findBridgedMethod` chỉ resolve theo class chứa candidate; nó **không thể tự suy ra toàn bộ implementation** chỉ từ một method của interface nếu không có target class. Vì vậy thường cần:

~~~java
Method declared =
        ((MethodSignature) pjp.getSignature()).getMethod();

Class<?> targetClass = pjp.getTarget().getClass();

Method specific =
        AopUtils.getMostSpecificMethod(declared, targetClass);

Method original =
        BridgeMethodResolver.findBridgedMethod(specific);
~~~

Cách làm này xử lý tốt tình huống method trên proxy là interface/generic bridge và bạn cần xem annotation trên implementation. Nó không tự giải quyết mọi bài toán **annotation inheritance, interface annotation composition hoặc meta-annotation**; với những trường hợp đó cần thêm chiến lược Spring merged annotation phù hợp.

### 6.3. Tại sao không dùng getDeclaredMethod trực tiếp?

Đoạn sau dễ sai:

~~~java
targetClass.getDeclaredMethod(
    invokedMethod.getName(),
    invokedMethod.getParameterTypes()
);
~~~

Nếu `invokedMethod` là `Processor.process(Object)` nhưng implementation method nghiệp vụ khai báo `process(String)`, lời gọi ở trên có thể trả bridge `process(Object)` hoặc thất bại, tùy class/compiler/hierarchy. Khi annotation nằm trên `process(String)`, đọc trực tiếp bridge không phải mục tiêu.

`AopUtils.getMostSpecificMethod` và `BridgeMethodResolver` được Spring thiết kế chính cho những trường hợp này.

## 7. Ví dụ chạy được: generic Processor, Spring @Around và bridge resolution

Dự án sử dụng **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.12**, **AspectJ Weaver 1.9.24**. Không cần Spring Boot hay database.

### 7.1. Cấu trúc

~~~text
spring-aop-bridge-method/
├── pom.xml
└── src/main/java/demo/
    ├── Processor.java
    ├── TrackedOperation.java
    ├── TextProcessor.java
    ├── TraceAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-bridge-method</artifactId>
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

`spring-context` đưa vào các module container và AOP cần thiết; `aspectjweaver` cho Spring đọc `@AspectJ` annotation/pointcut expression. Đây vẫn là **Spring proxy-based AOP**, không phải bytecode weaving.

### 7.3. Processor.java

~~~java
package demo;

public interface Processor<T> {
    T process(T input);
}
~~~

Ở runtime, `Processor<T>.process(T)` bị erasure thành method nhận và trả Object. Generic type parameter của source không buộc Java reflection method mang parameter String.

### 7.4. TrackedOperation.java

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface TrackedOperation {
}
~~~

Marker annotation được khai báo với runtime retention và method target. Nó chỉ gắn ở **method implementation** trong ví dụ; cố ý không gắn vào interface, để phân biệt metadata từ hai nơi.

### 7.5. TextProcessor.java

~~~java
package demo;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class TextProcessor implements Processor<String> {

    @TrackedOperation
    @Override
    public String process(String input) {
        System.out.println("TARGET process(String)");
        return input.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Hai điểm:

1. `@Service` làm implementation trở thành Spring bean qua component scanning.
2. `@TrackedOperation` nằm trên `process(String)`, không nằm trên interface generic `process(Object)`.

Với javac, Java compiler tạo bridge để implementation tuân theo interface erased contract. Việc đó không cần tự viết bridge trong source.

### 7.6. TraceAspect.java

~~~java
package demo;

import java.lang.reflect.Method;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.core.BridgeMethodResolver;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {

    @Around("execution(* demo.Processor+.process(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        MethodSignature signature =
                (MethodSignature) pjp.getSignature();

        Method interfaceOrProxyMethod = signature.getMethod();

        Method specific = AopUtils.getMostSpecificMethod(
                interfaceOrProxyMethod,
                pjp.getTarget().getClass()
        );

        Method original = BridgeMethodResolver.findBridgedMethod(specific);

        boolean annotationOnImplementation =
                original.isAnnotationPresent(TrackedOperation.class);

        System.out.println(
                "ADVICE process annotationOnImpl=" +
                annotationOnImplementation);

        return pjp.proceed();
    }
}
~~~

Cách đọc:

- `@Aspect` khai báo advice; `@Component` đăng ký aspect bean.
- Pointcut `execution(* demo.Processor+.process(..))` chọn những method executions phù hợp thuộc type `Processor` hoặc subtype/implementation của nó, trong giới hạn Spring AOP.
- `signature.getMethod()` cho method được AOP invocation công bố. **Không ép kết luận nó luôn là implementation method.**
- `AopUtils.getMostSpecificMethod` dựa trên **target class** để tìm method cụ thể.
- `BridgeMethodResolver.findBridgedMethod` bảo đảm nếu candidate là bridge, ta dùng method gốc.
- `original.isAnnotationPresent` kiểm tra annotation **đặt trực tiếp** trên original method. Với custom composed/meta-annotations hoặc annotations trên interface, phải dùng cách lookup tương ứng với yêu cầu.
- `pjp.proceed()` đúng một lần, trả nguyên kết quả và để target thực thi. Advice **không tự gọi lại** `TextProcessor.process` trực tiếp nên không phá chuỗi interceptor.

`@Around` là một trong các loại advice quan sát signature thuận tiện; với `@Before`, có thể dùng `JoinPoint` và cast signature tương tự, nhưng không có `proceed()`.

### 7.7. AppConfig.java

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
~~~

Cấu hình bật component scan để đăng ký `TextProcessor` và `TraceAspect`, sau đó tạo hạ tầng Spring AOP. `proxyTargetClass = false` thể hiện ý định **không ép class-based proxy**; với implementation có interface trong ví dụ, Spring Framework thuần dùng JDK dynamic proxy khi phù hợp.

Nếu một phần cấu hình khác dùng chung auto-proxy creator và ép CGLIB, loại proxy thực có thể đổi. Vì vậy chương trình sẽ in cả `AopUtils.isJdkDynamicProxy` để kiểm tra thay vì chỉ suy đoán.

### 7.8. App.java: quan sát interface, bridge và target method

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.BridgeMethodResolver;

public class App {

    private static String describe(Method method) {
        return method.getDeclaringClass().getSimpleName()
                + "." + method.getName()
                + "("
                + Arrays.stream(method.getParameterTypes())
                        .map(Class::getSimpleName)
                        .reduce((a, b) -> a + "," + b)
                        .orElse("")
                + ")";
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            @SuppressWarnings("unchecked")
            Processor<String> processor =
                    (Processor<String>) context.getBean(Processor.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(processor));
            System.out.println(
                    "IS_JDK_PROXY " +
                    AopUtils.isJdkDynamicProxy(processor));

            Method interfaceMethod =
                    Processor.class.getMethod("process", Object.class);

            Method bridge = Arrays.stream(
                        TextProcessor.class.getDeclaredMethods())
                    .filter(Method::isBridge)
                    .filter(m -> m.getName().equals("process"))
                    .findFirst()
                    .orElseThrow();

            Method specific = AopUtils.getMostSpecificMethod(
                    interfaceMethod,
                    TextProcessor.class
            );

            Method bridged = BridgeMethodResolver.findBridgedMethod(bridge);

            System.out.println(
                    "INTERFACE_METHOD " + describe(interfaceMethod));
            System.out.println("BRIDGE_PRESENT " + bridge.isBridge());
            System.out.println("SPECIFIC_METHOD " + describe(specific));
            System.out.println(
                    "BRIDGED_METHOD " + describe(bridged));

            System.out.println(
                    "ANNOTATION_ON_INTERFACE " +
                    interfaceMethod.isAnnotationPresent(
                            TrackedOperation.class));
            System.out.println(
                    "ANNOTATION_ON_IMPL " +
                    bridged.isAnnotationPresent(
                            TrackedOperation.class));

            String result = processor.process("  spring  ");
            System.out.println("RESULT " + result);
        }
    }
}
~~~

Ở đây:

- `Processor.class.getMethod("process", Object.class)` lấy method đã bị erasure trên generic interface.
- `TextProcessor.class.getDeclaredMethods()` tìm bridge do compiler tạo; **lọc theo `isBridge()` thay vì tin vào thứ tự reflection**.
- `AopUtils.getMostSpecificMethod` nhận interface method và concrete target class; trong tình huống này nó tìm về `TextProcessor.process(String)`.
- `BridgeMethodResolver.findBridgedMethod(bridge)` truy về method gốc mà bridge hỗ trợ.
- `describe` in chữ ký ngắn, không in tên các proxy classes ngẫu nhiên, giúp output ổn định.
- Caller dùng `Processor<String>` interface bean, **không cast JDK proxy về TextProcessor**.

Chạy trong thư mục có `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 7.9. Stdout logic dự kiến

~~~text
IS_PROXY true
IS_JDK_PROXY true
INTERFACE_METHOD Processor.process(Object)
BRIDGE_PRESENT true
SPECIFIC_METHOD TextProcessor.process(String)
BRIDGED_METHOD TextProcessor.process(String)
ANNOTATION_ON_INTERFACE false
ANNOTATION_ON_IMPL true
ADVICE process annotationOnImpl=true
TARGET process(String)
RESULT SPRING
~~~

Đây là **stdout logic kỳ vọng** cho project Java 17+ và Spring Framework thuần cấu hình như trên, không tính logging Maven/Spring. Phần reflection của javac cho thấy một bridge method; Spring AOP chỉ ghi **một** dòng `ADVICE` cho lời gọi business proxy `process`.

Nếu dự án thực chạy với compiler, Java language level hoặc AOP config khác, cần kiểm chứng thực tế các dòng phản ánh loại proxy và method metadata. Không coi kiểu proxy hay số bridge methods của mọi class Java là bất biến trong mọi môi trường.

**Điểm cần nhìn:** `INTERFACE_METHOD` và `BRIDGED_METHOD` không trùng chữ ký, nhưng cùng mô tả một logical service operation. `ANNOTATION_ON_INTERFACE false` và `ANNOTATION_ON_IMPL true` chứng minh không được đọc annotation implementation bằng cách chỉ xem method ở interface.

## 8. Thử thay đổi proxyTargetClass sang CGLIB

Trong `AppConfig.java`, thay:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = false)
~~~

bằng:

~~~java
@EnableAspectJAutoProxy(proxyTargetClass = true)
~~~

Đây là **thí nghiệm sửa một dòng cấu hình**, không tạo thêm `AppConfig` thứ hai.

Khi khởi động context mới:

- Spring có thể dùng **CGLIB class-based proxy** cho `TextProcessor`.
- `AopUtils.isAopProxy(processor)` vẫn dự kiến `true`.
- `AopUtils.isJdkDynamicProxy(processor)` dự kiến `false`.
- `AopUtils.isCglibProxy(processor)` sẽ là `true` nếu CGLIB thực sự được dùng.
- Class-based proxy vẫn có thể expose interface `Processor` để caller gọi qua interface.
- Bridge method trong class file vẫn tồn tại; đổi proxy không làm Java generics mất type erasure.
- Method mà `MethodSignature.getMethod()` biểu diễn có thể khác trong chi tiết declaring class so với JDK proxy; **logic resolve most-specific method vẫn cần thiết**.

Tránh mô tả rằng `proxyTargetClass = true` sẽ khiến Spring advise cả private, final hoặc self-invoked methods. Các giới hạn proxy vẫn còn.

## 9. Annotation trên interface và implementation: quyết định ở đâu?

Với `Processor<T>` và `TextProcessor implements Processor<String>`, một marker đặt trên interface method có thể **không có mặt trực tiếp** trên implementation method; chiều ngược lại cũng vậy. `@Inherited` của Java không làm annotation trên method được kế thừa qua override. Nếu dùng raw reflection, phải biết đang cầm `Method` của interface, implementation hay bridge.

Điều này tác động đến pointcut `@annotation(...)`: Spring có thể resolve method trong lúc match, còn gọi `isAnnotationPresent(...)` trên `MethodSignature.getMethod()` không tự tái hiện toàn bộ semantics của framework. Khi một annotation liên quan generic interface, hãy kiểm tra cả proxy JDK/CGLIB và nhất là **method được resolve sau bridge**. Đừng coi một bytecode bridge là method nghiệp vụ độc lập chỉ vì reflection nhìn thấy nó.

## 10. Khi cần annotation metadata hợp nhất

Đường đọc metadata đúng thứ tự là: lấy method từ `MethodSignature`, tìm **most-specific target method** bằng `AopUtils.getMostSpecificMethod`, resolve bridge khi cần bằng `BridgeMethodResolver.findBridgedMethod`, rồi chọn chính sách **raw annotation** hoặc **merged/meta-annotation** bằng các API Spring phù hợp. Bước tìm method và bước tìm annotation có mục đích khác nhau; điểm cắt `@annotation(...)` cũng phải được kiểm tra bằng advice invocation thực tế.

Bài **Đọc annotation trên đúng phương thức khi đối tượng là proxy** trình bày đầy đủ lookup ở interface, implementation, superclass và composed annotations. Phần trọng tâm tại đây là compiler bridge và cách xác định **một logical method** cho mỗi lời gọi proxy.

## 11. Bridge method không đồng nghĩa overload nghiệp vụ

Java source có thể cho developer viết overload:

~~~java
String process(String input);
String process(String input, int limit);
~~~

Nhưng bridge method thường là thứ compiler tạo để hỗ trợ overriding/generics hoặc covariant return, không phải overload mà team chủ động thêm.

| Khái niệm | Được tạo bởi | Vì sao có? | Có nên xem là business operation riêng? |
| --- | --- | --- | --- |
| Overload `process(String,int)` | Developer | Nhiều biến thể API khác danh sách tham số | Có, nếu nghiệp vụ phân biệt |
| Override `process(String)` | Developer | Cài đặt contract của generic interface | Có, là logic target |
| Bridge `process(Object)` | Compiler | Bảo toàn overriding sau type erasure | Thường **không** |
| JDK proxy method `Processor.process(Object)` | Interface/proxy contract | Cung cấp điểm gọi của proxy | Cùng logical operation của target |

Đừng ghi audit hai lần chỉ vì reflection trả về cả `process(String)` và `process(Object)`. Khi quét methods để tự xây metadata, nên lọc bridge/synthetic theo mục đích hoặc resolve về bridged method rồi deduplicate theo logical signature. Cần tránh việc lọc tất cả synthetic methods một cách mù quáng nếu framework có những method đặc biệt cần thiết khác.

Trong **Spring AOP**, một lời gọi `processor.process("x")` qua proxy về nguyên tắc là một logical proxy invocation; việc compiler sinh bridge không tự làm xuất hiện hai lời gọi advice cùng pointcut. Nếu quan sát hai log, trước hết kiểm tra **nhiều advisors cùng match**, double invocation thực tế hoặc nhiều proxy layers.

## 12. Generic, erasure và pointcut expression

Một expression như:

~~~text
execution(* demo.Processor+.process(..))
~~~

phù hợp để chọn một family method theo tên/type mà không phụ thuộc chi tiết generic erased parameter.

Nếu viết expression ràng buộc parameter cụ thể, cần hiểu:

- `Processor<T>` bị erasure; interface method có runtime parameter Object.
- Implementation `TextProcessor.process(String)` có signature riêng.
- Spring AspectJ pointcut matcher có thể resolve target/bridged method.
- Một expression quan sát interface/generic hierarchy không nên được đánh giá bằng cách chỉ đối chiếu chuỗi `Method.toString()`.

Nếu bạn cần lựa chọn “mọi implementation của `Processor<String>` nhưng không phải `Processor<Integer>`”, Java erasure khiến việc match **generic type argument** theo tên method đơn giản không đáng tin cậy. Cân nhắc explicit bean types, custom annotation, một contract riêng hoặc kiểm tra metadata type phù hợp với Spring `ResolvableType`; viết integration test chứng minh match behavior.

**Không dùng `args(java.lang.String)` như thể nó là một phép chọn overload trên declared parameter type**: `args` xét argument runtime type, trong khi `execution` xét method execution signature. Một target có method khai báo `process(Object)` vẫn có thể nhận String instance tại runtime.

## 13. Truyền tham số JoinPoint và đọc MethodSignature an toàn

Bên trong advice, ngoài `getMethod()` bạn có thể quan sát:

~~~java
Object[] arguments = pjp.getArgs();
Object proxy = pjp.getThis();
Object target = pjp.getTarget();

MethodSignature signature =
        (MethodSignature) pjp.getSignature();

String methodName = signature.getName();
Class<?> declaringType = signature.getDeclaringType();
~~~

Đây là **fragment ở bên trong `@Around`**, chưa có imports và context đầy đủ. Phải hiểu:

- `getArgs()` mô tả arguments của invocation; runtime argument type có thể khác declared signature do inheritance.
- `getThis()` là proxy đang cung cấp AOP invocation.
- `getTarget()` là target object.
- `getDeclaringType()` không mặc nhiên là `target.getClass()` với JDK proxy.
- `getName()` chỉ là tên, không phân biệt overload hoặc generic bridge.
- `MethodSignature.getMethod()` là entry để resolve đúng target method, không phải bằng chứng annotation tồn tại trên implementation.
- Nếu aspect match những join point types khác trong môi trường AspectJ weaving, không được cast mọi signature sang `MethodSignature` một cách vô điều kiện; riêng Spring AOP chỉ xử lý method execution join points.

Khi thay đổi arguments qua `pjp.proceed(Object[])`, cần đúng số lượng và kiểu; không dùng generic erasure làm lý do chuyền sai runtime type. Một bridge có thể cast Object thành String, nên truyền sai type có thể dẫn đến `ClassCastException` trong đường thực thi.

## 14. Pointcut match interface nhưng method chỉ có trong implementation

Ví dụ một service:

~~~java
public interface OrderApi {
    void place();
}

public class OrderService implements OrderApi {
    @Override
    public void place() {
    }

    public void internalReport() {
    }
}
~~~

Hai type trên phải ở **hai file Java riêng** nếu đều public. Đây là fragment mô tả ranh giới, không phải project runnable chính.

Nếu bean được proxy bằng **JDK dynamic proxy** của `OrderApi`, caller không thể gọi `internalReport()` qua `OrderApi` vì method không nằm trong contract proxy. Expression:

~~~text
execution(* demo.OrderService.internalReport(..))
~~~

không thể khiến method đó tự xuất hiện trên JDK proxy interface. Nếu thật sự cần advice method ấy:

- Cân nhắc đưa method vào một interface public phù hợp.
- Hoặc dùng **CGLIB class-based proxy** nếu class/method có thể override.
- Hoặc refactor sang một Spring bean khác với API rõ ràng.

Bridge resolution là vấn đề **method metadata**; nó không thể vượt qua hạn chế method exposure của proxy.

## 15. Self-invocation vẫn bypass Spring AOP

Nếu `TextProcessor.process(String)` gọi một method khác trong cùng target qua `this.helper()`, lời gọi nội bộ đó không tự quay qua proxy nên advice của `helper()` không được áp dụng theo đường đi ấy.

~~~java
public String process(String input) {
    return this.normalize(input);
}

public String normalize(String input) {
    return input.trim();
}
~~~

Đây là **fragment minh họa**, không phải cách thay file `TextProcessor.java` của ví dụ vì còn thiếu annotations/imports. Dù `normalize` có chữ ký rõ ràng và Spring có thể resolve method, lời gọi `this.normalize` trong target không tạo thêm invocation đi qua proxy.

Đừng nhầm hai câu hỏi:

1. **Spring có resolve được method đúng không?** Liên quan bridge, interface, target method và pointcut.
2. **Lời gọi có đi qua proxy không?** Liên quan self-invocation, JDK/CGLIB và bean lifecycle.

Có phương thức được resolve đúng **không bảo đảm advice sẽ chạy** nếu caller bypass proxy.

## 16. Các lỗi phổ biến và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `getMethod().getAnnotation(...)` trả null | `getMethod()` đang là interface method | Resolve target method với `AopUtils.getMostSpecificMethod` |
| Chọn được `process(Object)` thay vì `process(String)` | Method từ generic interface hoặc compiler bridge | Dùng `BridgeMethodResolver` và target class |
| Reflection quét thấy hai method cùng tên | Có method implementation và bridge do compiler sinh | Kiểm tra `isBridge()`, `isSynthetic()` và parameter types |
| Advice log hai lần | Nhiều advisors/lần gọi/proxy layers, không nhất thiết do bridge | Đếm proxy invocations, kiểm tra advisor chain |
| Cast Spring proxy sang concrete implementation thất bại | Proxy là JDK dynamic proxy | Inject/use interface; cân nhắc CGLIB khi cần |
| `@annotation` không match ở một cấu hình proxy | Annotation placement hoặc method resolution khác | Test interface/implementation metadata trong context thật |
| Method trên interface không có annotation nhưng implementation có | Raw reflection nhìn nhầm nơi đặt annotation | Resolve most-specific target method |
| Generic type String nhưng reflection trả Object | Type erasure ở generic interface | Xem `getGenericParameterTypes()` và `ResolvableType` khi cần |
| Spring không advice implementation-only method | JDK proxy không expose method ấy | Thêm API vào interface hoặc thay kiến trúc/proxy |
| Spring không advice private/final method | Class-based proxy không override được | Thay entrypoint/interceptable design |
| Advice không chạy khi target tự gọi method | Self-invocation bypass proxy | Tách bean/gọi qua Spring-managed dependency |
| `getDeclaredMethod` thất bại | Dùng erased interface parameter types trên implementation | `AopUtils.getMostSpecificMethod` |
| `ClassCastException` khi gọi generic bridge | Runtime argument không tương thích String | Bảo đảm typed caller/proceed arguments đúng |
| Scan annotation bỏ sót meta-annotation | Raw reflection không dò composed annotation | Cân nhắc `AnnotatedElementUtils` / merged metadata |
| Spring context không tạo AOP proxy | Aspect không là bean, AOP chưa bật hoặc không có advisor phù hợp | Kiểm tra `@Component`, `@Aspect`, `@EnableAspectJAutoProxy` |

## 17. Checklist triển khai Spring Aspect trên interface generic

1. Xác định method được advice nằm trên **interface**, implementation hay cả hai?
2. Bean đã được đăng ký trong Spring ApplicationContext chưa?
3. Aspect đã là Spring bean và AOP infrastructure đã bật chưa?
4. Proxy thực tế là JDK hay CGLIB? Dùng `AopUtils.isJdkDynamicProxy`/`isCglibProxy`.
5. Method được `MethodSignature.getMethod()` khai báo ở class nào?
6. Có bridge method không? Dùng `Method.isBridge()` để biết.
7. Nếu cần annotation implementation, đã resolve `AopUtils.getMostSpecificMethod` theo target class chưa?
8. Nếu candidate là bridge, đã tìm bridged method chưa?
9. Có yêu cầu meta-annotation/hierarchy không? Nếu có, dùng Spring annotation utilities đúng policy.
10. Pointcut có match **một logical business operation** như mong muốn không?
11. Có advisor khác, overload, interface default method hoặc inherited method làm số advice thay đổi không?
12. Method có được công bố trên JDK proxy interface hoặc interceptable bởi CGLIB không?
13. Caller có đi qua proxy thay vì `new`/`this.method()` không?
14. Có integration test kiểm tra cả JDK proxy, CGLIB (nếu được hỗ trợ) và annotation placement quan trọng không?
15. Đã đối chiếu output trên runtime/compiler mà ứng dụng triển khai, thay vì suy đoán reflection order chưa?

## 18. Câu hỏi tự đánh giá

**1. Vì sao `Processor<String>.process(String)` có thể xuất hiện `process(Object)` trên bytecode?**

Vì type erasure biến generic interface method thành erased signature, và compiler có thể sinh bridge để duy trì overriding.

**2. `Method.isBridge()` nói lên điều gì?**

Nó cho biết method được đánh dấu compiler-generated bridge; không có nghĩa đó là một operation nghiệp vụ tách biệt.

**3. Với JDK proxy, `MethodSignature.getMethod()` có luôn là method implementation không?**

Không. Nó có thể là method khai báo trong interface. Cần resolve target method khi muốn metadata implementation.

**4. API Spring nào thường dùng để tìm implementation method từ interface Method?**

`AopUtils.getMostSpecificMethod(method, targetClass)`.

**5. API nào dùng để tìm method gốc khi đang có bridge?**

`BridgeMethodResolver.findBridgedMethod(bridgeMethod)`.

**6. Có cần kiểm tra `isBridge()` trước khi gọi `findBridgedMethod` không?**

Không bắt buộc; API Spring cho phép truyền non-bridge method và có thể trả method ấy.

**7. Annotation chỉ nằm trên implementation thì raw reflection của interface method có thấy không?**

Không. Phải xem concrete method hoặc sử dụng cách tìm annotation theo quy ước Spring phù hợp.

**8. Tại sao đổi JDK proxy sang CGLIB không làm bridge method biến mất?**

Bridge là sản phẩm của Java compiler trên class file, không phải đối tượng chỉ tồn tại do JDK proxy tạo.

**9. Có bridge method thì Spring AOP phải chạy @Around hai lần không?**

Không. Bridge không tự là hai client proxy invocations. Nếu advice chạy hai lần, cần điều tra call path và advisors.

**10. Nếu method chỉ có trên implementation, client JDK proxy gọi nó trực tiếp được không?**

Không, nếu method không thuộc interface mà JDK proxy expose.

**11. Có phải `@annotation` giống hệt `MethodSignature.getMethod().isAnnotationPresent` trong mọi trường hợp?**

Không. Spring method matching và annotation resolution có thể xét target/bridge hierarchy, còn raw reflection chỉ đọc annotation theo chính Method đó.

**12. Resolve đúng bridge có sửa được self-invocation bypass proxy không?**

Không. Method metadata resolution và proxy invocation boundary là hai vấn đề độc lập.

## 19. Tài liệu Spring Framework chính thức

- **Spring Framework — AOP Proxying Mechanisms:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- **Spring Framework — @AspectJ Pointcuts:** https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html
- **Spring Framework 6.2.x — AopUtils Javadoc:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/support/AopUtils.html
- **Spring Framework 6.2.x — BridgeMethodResolver Javadoc:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/BridgeMethodResolver.html
- **Spring Framework — AnnotatedElementUtils Javadoc:** https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/annotation/AnnotatedElementUtils.html
- **Spring Framework — AspectJ-style AOP Support:** https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html

**Kết luận:** Với generic interfaces trong Spring AOP, **interface method, concrete implementation method và compiler bridge method** có thể đại diện cho cùng một logical operation nhưng chứa metadata khác nhau. Khi advice cần xem annotation hoặc chữ ký method triển khai, hãy xuất phát từ `MethodSignature`, xác định **target class**, dùng **`AopUtils.getMostSpecificMethod`** và **`BridgeMethodResolver.findBridgedMethod`** khi phù hợp. Đồng thời luôn nhớ: Spring AOP là **proxy-based**; dù đã resolve đúng method, advice vẫn chỉ chạy khi invocation thực sự đi qua proxy và advisor match.
