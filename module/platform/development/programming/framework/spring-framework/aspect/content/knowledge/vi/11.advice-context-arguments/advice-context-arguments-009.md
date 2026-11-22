# Spring AOP: Giới hạn suy luận khi tham số có generic và xóa kiểu

## 1. Vấn đề trong Spring Aspect: `List<String>` có thật sự được nhận diện?

Một Spring aspect thường cần quan sát hoặc ràng buộc đối số method thông qua `JoinPoint.getArgs()`, `args(...)`, `MethodSignature` hoặc tên tham số của advice. Khi target method khai báo kiểu có generic như `List<String>`, `Collection<Order>`, `Optional<User>` hoặc `Repository<T>`, phải phân biệt:

1. **Kiểu khai báo trong source/class metadata**, chẳng hạn `List<String>`.
2. **Kiểu runtime của object được truyền vào**, chẳng hạn một instance của `List`.
3. **Kiểu runtime của mỗi phần tử**, chẳng hạn từng object `String`.
4. **Khả năng match/bind của Spring AOP pointcut**, vốn không tương đương một bộ kiểm tra đầy đủ mọi type parameter tại runtime.

Java thực hiện **generic type erasure**: đa số type arguments không nằm trong runtime class của object `List`. Spring có thể đọc **generic signature metadata** của một method bằng reflection nếu metadata tồn tại, nhưng điều đó không chứng minh nội dung collection thực sự phù hợp.

Đây là giới hạn thực hành quan trọng khi dùng **Spring Aspect**, không phải bài học tổng quát về generics. Ta tập trung vào những câu hỏi: advice match method nào, bind được giá trị gì, reflection biết được đến đâu, khi nào phải tự kiểm tra phần tử, và tác động của JDK/CGLIB proxies cùng bridge methods.

### Ví dụ phân biệt ba lớp thông tin

```java
public interface MessagePort {
    void deliver(List<String> names);
}
```

Khi consumer gọi `port.deliver(List.of("An", "Bình"))` trên Spring-managed proxy:

- Java compile-time kiểm tra `List<String>` theo method contract.
- `JoinPoint.getArgs()[0]` nhận một **List object**. `getClass()` cho biết implementation class của List, không cho ra `List<String>`.
- Nếu declaration thực sự còn generic signature, reflection có thể đọc rằng **tham số của method** được khai báo `List<String>`.
- Runtime argument vẫn có thể bị tạo qua raw type, unchecked cast, reflection, deserialization hoặc code không an toàn. Method declaration không bảo đảm mọi element đúng là String.
- Spring AOP không tự duyệt tất cả List elements mỗi invocation để suy ra `T`, vì không thể xây quy tắc tổng quát đáng tin cho `null`, collection rỗng, wildcard hoặc mutable list.

**Kết luận mở đầu:** *Generic declaration metadata khác với generic runtime verification; `JoinPoint` và pointcut binding không thay thế Java type-safety của application boundary.*

## 2. Spring AOP quan sát lời gọi ở ranh giới proxy

```text
Consumer
   |
   | port.deliver(List<String>)
   v
JDK proxy (interface) hoặc CGLIB proxy (class)
   |
   | pointcut match method-execution
   v
@Before / @Around advice
   |
   +-- jp.getArgs()[0]             -> List object (runtime value)
   +-- jp.getSignature()           -> method signature
   +-- Method.getGeneric...        -> declared metadata nếu có
   +-- args(values)                -> bind runtime object
   |
   v
Target.deliver(List<String>)
```

Spring AOP dựa trên proxy, chỉ hỗ trợ **method-execution join points** của Spring-managed beans. Không phải mọi method call trong JVM đều tạo `JoinPoint` cho advice.

Khi target tự gọi `this.deliver(...)`, lời gọi nội bộ **bypass proxy**, nên advice không tự thấy invocation đó. Tương tự, object được tạo bằng `new` bên ngoài Spring IoC không tự có AOP proxy.

### Cách gọi method không thay đổi erasure

Chuyển từ JDK proxy sang CGLIB không “khôi phục” generic arguments bên trong runtime List; cả hai vẫn dựa trên Java runtime. Điểm khác là method phản chiếu từ interface hoặc implementation có thể khác nhau, khiến ta phải **resolve concrete method** trước khi đọc generic metadata.

## 3. Khi Spring bind được tham số có kiểu cụ thể

Tài liệu chính thức Spring Framework, mục **Advice Parameters and Generics**, giải thích Spring AOP hỗ trợ các trường hợp generic ở class declaration và method parameter. Ví dụ:

```java
public interface Sample<T> {
    void sampleGenericMethod(T value);
    void sampleGenericCollectionMethod(Collection<T> values);
}
```

Nếu caller truyền một object thuộc class `Invoice` vào `sampleGenericMethod(T)`, advice có thể bind kiểu cụ thể nhờ runtime type của argument, tùy pointcut và giới hạn phương thức:

```java
@Before(
    value = "execution(* demo.generic..*.sampleGenericMethod(..))"
          + " && args(invoice)",
    argNames = "invoice"
)
public void beforeInvoice(Invoice invoice) {
    System.out.println("invoice id=" + invoice.id());
}
```

Đây là **fragment**; `Invoice` phải là type thực có trong dự án, aspect cần Spring quản lý và method cần đi qua proxy. `args(invoice)` giúp bind actual argument và giới hạn kiểu phù hợp. Spring có thể kiểm tra runtime object có phải `Invoice`, khác hẳn câu hỏi “một List đang chứa `Invoice` hay không”.

Với một đối số dạng class có generic `T` nhưng method thực tế nhận subclass cụ thể, Spring/AspectJ pointcut matching có thể dùng **runtime type**, declared method signature và các quy tắc khác. Không suy từ một ví dụ đơn giản rằng mọi trường hợp generic hierarchy, overload, `null`, interface và bridge methods đều được match giống nhau.

## 4. Giới hạn quan trọng: `Collection<Invoice>` trong advice

Điểm Spring nêu rõ: bạn **không thể chỉ dùng** một advice parameter kiểu `Collection<Invoice>` để làm pointcut phân biệt chính xác contents của một generic collection:

```java
// KHÔNG dùng như phương pháp xác minh List/Collection<Invoice> runtime.
@Before(
    value = "execution(* demo.generic..*.sampleGenericCollectionMethod(..))"
          + " && args(values)",
    argNames = "values"
)
public void beforeInvoices(Collection<Invoice> values) {
    // Kiểu khai báo này KHÔNG có nghĩa Spring đã kiểm tra từng element.
}
```

Đây là snippet **phản ví dụ**, không phải code khuyến nghị. Lý do không chỉ nằm ở “Spring không đủ thông minh”: object `Collection` tại runtime thông thường không mã hóa `Invoice` làm type argument, và Spring không duyệt tất cả phần tử để kết luận generic match.

Cách nên dùng khi cần inspect actual contents:

```java
@Before(
    value = "execution(* demo.generic..*.sampleGenericCollectionMethod(..))"
          + " && args(values)",
    argNames = "values"
)
public void inspect(Collection<?> values) {
    boolean allInvoices = values.stream()
            .allMatch(Invoice.class::isInstance);
    System.out.println("all invoices=" + allInvoices);
}
```

Đây là **fragment** giả định `Invoice` có thật. `Collection<?>` nói rõ rằng advice chưa biết element type, rồi ta kiểm tra từng phần tử theo policy cụ thể. Tuy nhiên:

- `allMatch(...)` trên **collection rỗng** trả `true` theo quy tắc toán học (vacuous truth): *không có phần tử sai* không đồng nghĩa *đã chứng minh kiểu Invoice*.
- Nếu collection chứa `null`, `Invoice.class.isInstance(null)` là `false`; bạn cần quyết định chính sách null.
- Nếu collection mutable và bị thay đổi đồng thời, một lần kiểm tra không bảo đảm nó mãi hợp lệ.
- Nếu chỉ muốn logging, không nhất thiết cần duyệt mọi element vì chi phí, độ nhạy cảm dữ liệu và side effects.
- Nếu validation ảnh hưởng bảo mật/nghiệp vụ, chọn boundary đúng, kiểm tra có chủ đích và cân nhắc Spring Bean Validation / contract validation phù hợp; không coi aspect tự bảo đảm toàn bộ hệ thống.

**Trọng tâm:** binding `Collection<?>` đủ để advice đọc object một cách an toàn về mặt generic, còn việc xác minh element type là một bước riêng tùy mục tiêu.

## 5. `args(...)` khác với `execution(...)` về cách match

Spring AOP hỗ trợ hai nhóm thông tin thường bị trộn lẫn:

- `execution(...)` xét **method signature/execution** phù hợp với pattern.
- `args(...)` xét **runtime arguments** phù hợp với type/argument binding.

### 5.1. Không viết generic type argument như một runtime type trong pointcut

Không giả định có thể viết:

```text
execution(* demo.generic.CatalogService.store(java.util.List<java.lang.String>))
```

để Spring AOP thực hiện element-type matching cho `List<String>`. Pointcut execution trong proxy-based Spring AOP không phải một ngôn ngữ truy vấn nội dung generics. Việc Spring có thể **đọc** generic signature từ method declaration là khả năng khác với **match tất cả elements**.

Khi mục tiêu chỉ là method có tên `storeNames`, dùng method pattern:

```java
@Before("execution(* demo.generic.CatalogService.storeNames(..))")
public void beforeNames(JoinPoint jp) {
    Object first = jp.getArgs()[0];
    System.out.println(first instanceof List<?>);
}
```

Snippet trên không tự chứng minh `List<String>` hợp lệ; nó chỉ quan sát một argument thuộc List.

### 5.2. `args(value)` và `args(values)`

Với argument scalar, `args(value)` gắn actual value vào typed advice parameter. Với `List<?>`, `args(values)` bind **List object** chứ không bind từng element. Bạn phải viết rõ logic kiểm tra nếu muốn biết element types.

Hãy cân nhắc `null`: một runtime argument null không có concrete class để `getClass()` kiểm tra. Điều kiện static signature và cơ chế type binding có thể ảnh hưởng match; không suy từ `null` rằng generic type argument được biết. Nếu pointcut hoặc advice phải hoạt động cả khi null, kiểm tra bằng integration test cho đúng overload/config.

### 5.3. Overload theo generic element type không hợp lệ trong Java

Bạn không thể khai báo cùng class hai overload chỉ khác type argument:

```java
// PHẢN VÍ DỤ — hai method có cùng erasure, không biên dịch.
public void store(List<String> values) {}
public void store(List<Integer> values) {}
```

Sau erasure, cả hai có dạng `store(List)`. Java không phân biệt method overload bằng `String` hay `Integer` ẩn trong List. Vì thế đừng thiết kế pointcut để phân biệt hai overload vốn không tồn tại ở Java bytecode.

Có thể dùng hai tên method khác nhau như `storeNames(List<String>)` và `storeNumbers(List<Integer>)`, hoặc dùng wrapper types riêng nếu thực sự cần API khác nhau.

## 6. Reflection: `getParameterTypes()` và `getGenericParameterTypes()`

Khi lời gọi Spring AOP đến một method, advice có thể dùng:

```java
MethodSignature signature = (MethodSignature) jp.getSignature();
Method method = signature.getMethod();

Class<?>[] erasedTypes = method.getParameterTypes();
Type[] declaredTypes = method.getGenericParameterTypes();
```

Đây là **fragment** trong advice; imports gồm `org.aspectj.lang.reflect.MethodSignature`, `java.lang.reflect.Method` và `java.lang.reflect.Type`.

Giả sử concrete declaration là:

```java
public void storeNames(List<String> values) { /* ... */ }
```

Các khái niệm:

| API | Có thể thấy gì? | Không kết luận được gì? |
| --- | --- | --- |
| `Method.getParameterTypes()[0]` | `java.util.List.class` — raw Class | Không cho biết element đang là String |
| `Method.getGenericParameterTypes()[0]` | Metadata `java.util.List<java.lang.String>` trong method declaration nếu còn generic signature | Không chứng minh List object thực sự chỉ chứa String |
| `JoinPoint.getArgs()[0].getClass()` | Concrete runtime List class | Không có type argument chuẩn như `List<String>` |
| `MethodSignature.getParameterTypes()[0]` | Erased declared parameter Class | Không đủ để suy `T` ở method generic |
| `JoinPoint.getArgs()` | Actual runtime values | Không cung cấp Java type arguments trên collection |

Một `ParameterizedType` có thể mô tả chữ ký method có `List<String>`, nhưng data của `Type` **thuộc declaration**, không thuộc object List đang được truyền. Nếu caller dùng raw types/unchecked casts sai, chữ ký vẫn ghi String.

### 6.1. Spring `ResolvableType` giúp đọc generic declaration

Spring cung cấp `org.springframework.core.ResolvableType` để làm việc với generic type metadata trong reflection:

```java
Method method = ...; // Concrete method đã được xác định đúng.
ResolvableType parameter = ResolvableType.forMethodParameter(method, 0);
Class<?> elementType = parameter.getGeneric(0).resolve();

System.out.println(elementType); // Với List<String>: class java.lang.String.
```

Đây là fragment, không phải file Java hoàn chỉnh. `ResolvableType` thuận tiện hơn việc tự xử lý `ParameterizedType`, `TypeVariable`, `WildcardType`, `GenericArrayType`, nhưng:

- Nó resolve **declared type metadata**, không duyệt runtime collection.
- Với `T` chưa biết, wildcard hoặc parameterized type phức tạp, resolution có thể không thành `String.class`; `resolve()` có thể trả `null` hoặc fallback tùy overload.
- Method được chọn phải đúng declaring/implementation context. Một generic interface `Port<T>` chỉ chứa `T`; muốn biết concrete binding `T = String`, cần xét target implementation class hoặc cung cấp owner context phù hợp.
- Có thể có proxies, bridge methods và hierarchies; đọc nhầm `Method` của interface thay vì implementation sẽ làm metadata kém cụ thể hơn.

Không biến `ResolvableType.resolve() == String.class` thành một “kiểm tra runtime List chỉ chứa String”.

### 6.2. Tên argument không phải generic type

Spring có `argNames`, phản chiếu Java parameter names và pointcut binding. Đây là cơ chế **gắn tên biến advice** với pointcut expression, hoàn toàn khác với việc bảo đảm generic type.

Ví dụ:

```java
@Before(
    value = "execution(* demo.generic.CatalogService.storeNames(..))"
          + " && args(values)",
    argNames = "values"
)
public void before(List<?> values) {
    System.out.println(values.size());
}
```

`argNames="values"` giúp Spring bind tên `values`; nó không khiến `List<?>` biến thành `List<String>`. Các compiler flags như `-parameters` hỗ trợ discovery tên method parameters, chứ không thay cơ chế generic erasure.

## 7. Generic interface, bridge methods và Spring proxy

Ví dụ:

```java
public interface Handler<T> {
    void handle(T value);
}

public class StringHandler implements Handler<String> {
    @Override
    public void handle(String value) {
        System.out.println("handle " + value);
    }
}
```

Khi biên dịch Java, generic `Handler<T>` bị erase (với unbounded T thường thành `Object`). Compiler có thể tạo **synthetic bridge method** để bảo đảm overriding và polymorphism làm việc đúng giữa `handle(Object)` và `handle(String)`.

Với Spring AOP:

- Một JDK proxy có thể nhận method nhìn theo **interface declaration** có tham số erasure là `Object`, trong khi implementation method cụ thể nhận `String`.
- CGLIB proxy có thể liên quan subclass/bridge signatures. Đừng khẳng định mọi invocation cho một generic method luôn có đúng một Java Method object giống nhau ở tất cả proxy types.
- Khi cần tìm annotation hoặc generic metadata cụ thể, nên resolve **most-specific target method** và xử lý bridge nếu cần.

Spring cung cấp công cụ:

```java
MethodSignature sig = (MethodSignature) jp.getSignature();
Method invokedMethod = sig.getMethod();
Object target = jp.getTarget();

if (target != null) {
    Method specific = AopUtils.getMostSpecificMethod(
            invokedMethod, target.getClass());
    System.out.println(specific.toGenericString());
}
```

Snippet cần imports `org.aspectj.lang.reflect.MethodSignature`, `java.lang.reflect.Method`, `org.springframework.aop.support.AopUtils`. Spring cung cấp `BridgeMethodResolver` khi cần làm việc với bridge methods cụ thể:

```java
Method userMethod = BridgeMethodResolver.findBridgedMethod(specific);
```

`BridgeMethodResolver` nằm ở `org.springframework.core`. Lời gọi trên chỉ minh họa khi biến `specific` có sẵn. Không tự cast result sang implementation method rồi giả định `getGenericParameterTypes()` lúc nào cũng là `List<String>`, nhất là khi metadata được khai báo ở generic superclass/interface.

### 7.1. Generic type erasure không phải lỗi riêng của Spring

Khi ứng dụng dùng reflection, dynamic proxy và method interception, erasure là đặc tính của Java compilation/runtime. Spring cung cấp utilities giúp **giải metadata**, nhưng không thể suy luận thứ Java runtime không lưu ở object hoặc method context.

Vì vậy, việc thay `@EnableAspectJAutoProxy(proxyTargetClass=true)` không thể tự sửa một advice đang mong `List<String>` tự match contents.

## 8. Dự án chạy được: phân biệt metadata generic và runtime arguments

Ví dụ dùng **Java 17**, **Maven** và **Spring Framework 6.2.x** không cần Spring Boot. Ta chủ động tạo một Spring-managed service có interface và một aspect với ba before advices cho ba method khác nhau. Mỗi method dùng pointcut riêng để stdout có thứ tự kiểm chứng được, không phụ thuộc precedence của nhiều advisors trên cùng invocation.

Mục tiêu:

1. Bind tham số `String` scalar với `args(text)`.
2. Đọc declared generic parameter type của `List<String>` và `List<Integer>`.
3. Chứng minh runtime list là `List`, nhưng nếu muốn biết element class thì phải kiểm tra contents.
4. Không log concrete implementation class của `List.of(...)` vì tên internal của JDK không là API ổn định.
5. Dùng Spring-managed JDK proxy để minh họa đúng ranh giới AOP.

### 8.1. Cấu trúc thư mục

```text
spring-aop-generic-args/
├── pom.xml
└── src/main/java/demo/generic/
    ├── AppConfig.java
    ├── PayloadPort.java
    ├── PayloadService.java
    ├── InspectAspect.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-generic-args</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
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
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. `AppConfig.java`

```java
package demo.generic;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@EnableAspectJAutoProxy(proxyTargetClass=false)` trong Spring Framework thuần ưu tiên **JDK interface proxy** vì target bên dưới triển khai `PayloadPort`.

### 8.4. `PayloadPort.java`

```java
package demo.generic;

import java.util.List;

public interface PayloadPort {
    void submit(String text);
    void storeNames(List<String> names);
    void storeNumbers(List<Integer> numbers);
}
```

Đây là ba method **khác tên**, vì Java không cho overload chỉ khác `List<String>` và `List<Integer>` sau erasure.

### 8.5. `PayloadService.java`

```java
package demo.generic;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PayloadService implements PayloadPort {
    @Override
    public void submit(String text) {
        System.out.println("[target] submit " + text);
    }

    @Override
    public void storeNames(List<String> names) {
        System.out.println("[target] names count=" + names.size());
    }

    @Override
    public void storeNumbers(List<Integer> numbers) {
        System.out.println("[target] numbers count=" + numbers.size());
    }
}
```

Target chỉ in số phần tử, không cast element, để tập trung vào điều kiện match/generic observation của advice.

### 8.6. `InspectAspect.java`

```java
package demo.generic;

import java.lang.reflect.Method;
import java.util.List;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class InspectAspect {
    @Before(
        value = "execution(* demo.generic.PayloadService.submit(..))"
              + " && args(text)",
        argNames = "text"
    )
    public void beforeText(String text) {
        System.out.println("[advice] text=" + text);
    }

    @Before("execution(* demo.generic.PayloadService.storeNames(..))")
    public void beforeNames(JoinPoint jp) {
        Method method = concreteMethod(jp);
        List<?> values = (List<?>) jp.getArgs()[0];

        System.out.println("[advice] declared="
                + method.getGenericParameterTypes()[0].getTypeName());
        System.out.println("[advice] runtimeIsList=" + (values instanceof List));
        System.out.println("[advice] allStrings="
                + values.stream().allMatch(String.class::isInstance));
    }

    @Before("execution(* demo.generic.PayloadService.storeNumbers(..))")
    public void beforeNumbers(JoinPoint jp) {
        Method method = concreteMethod(jp);
        List<?> values = (List<?>) jp.getArgs()[0];

        System.out.println("[advice] declared="
                + method.getGenericParameterTypes()[0].getTypeName());
        System.out.println("[advice] runtimeIsList=" + (values instanceof List));
        System.out.println("[advice] allIntegers="
                + values.stream().allMatch(Integer.class::isInstance));
    }

    private Method concreteMethod(JoinPoint jp) {
        MethodSignature sig = (MethodSignature) jp.getSignature();
        return AopUtils.getMostSpecificMethod(
                sig.getMethod(), jp.getTarget().getClass());
    }
}
```

Trong `InspectAspect`:

- `@Before ... args(text)` bind scalar `String` cụ thể.
- Hai method còn lại dùng `JoinPoint` để xem object List, resolve **concrete declaration** bằng Spring `AopUtils.getMostSpecificMethod(...)`, rồi đọc generic signature metadata.
- `method.getGenericParameterTypes()[0]` mô tả declared `List<String>` hoặc `List<Integer>`.
- `values instanceof List` chỉ kiểm tra **raw runtime class/interface**.
- `allMatch(...)` kiểm tra từng phần tử hiện có. Đây là **policy minh họa**; nó không tự là hợp đồng tổng quát cho List rỗng/null/mutable.
- Ba pointcuts không chồng lên nhau, vì vậy kết quả log dễ dự đoán.

### 8.7. `Main.java`

```java
package demo.generic;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            PayloadPort port = context.getBean(PayloadPort.class);
            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(port));

            port.submit("A1");
            port.storeNames(List.of("An", "Binh"));
            port.storeNumbers(List.of(10, 20));
        }
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.generic.Main
```

**Stdout do các lệnh `System.out` của ví dụ phát ra** (không tính log của Maven/Spring nếu môi trường in thêm):

```text
jdkProxy=true
[advice] text=A1
[target] submit A1
[advice] declared=java.util.List<java.lang.String>
[advice] runtimeIsList=true
[advice] allStrings=true
[target] names count=2
[advice] declared=java.util.List<java.lang.Integer>
[advice] runtimeIsList=true
[advice] allIntegers=true
[target] numbers count=2
```

### 8.8. Đọc kết quả chính xác

1. Spring quản lý `PayloadService`, aspect `InspectAspect` được scan và pointcuts match; interface proxy tạo ra nên `jdkProxy=true`.
2. `port.submit("A1")` đi qua proxy. `args(text)` bind String runtime và advice in `text=A1` trước target.
3. `port.storeNames(List.of("An","Binh"))` vào advice. Reflection trên concrete method cho declared `java.util.List<java.lang.String>`, không phải giá trị “type argument của runtime List object”.
4. `values instanceof List` là true. Kiểm tra từng phần tử String trong **mảng dữ liệu thực tế của lời gọi này** trả true; đó là kết quả do sample contents, không do pointcut tự suy generic.
5. `port.storeNumbers(List.of(10,20))` có cùng raw List surface, nhưng declared generic type trong **method khác** là `List<Integer>` và từng element trong ví dụ là Integer.
6. Không có đoạn nào chứng minh mọi List runtime đều có type parameter cố định; output chỉ phản ánh hai method declarations và những sample arguments cụ thể.

## 9. Thử nghiệm suy luận sai thường gặp

### 9.1. Empty collection làm `allMatch` trả true

```java
List<?> empty = List.of();
boolean strings = empty.stream().allMatch(String.class::isInstance);
boolean integers = empty.stream().allMatch(Integer.class::isInstance);
System.out.println(strings + " " + integers); // true true
```

Đây là snippet Java độc lập (trong method) minh họa semantics Stream. Empty list không có phần tử để phản chứng cả hai kiểm tra. Nếu business policy đòi **có ít nhất một phần tử và tất cả là String**:

```java
boolean nonEmptyStrings = !empty.isEmpty()
        && empty.stream().allMatch(String.class::isInstance);
```

Cần dựa vào validation contract riêng, không đổ lỗi cho Spring AOP vì collection rỗng.

### 9.2. Phần tử null và wildcard

```java
List<?> mixed = java.util.Arrays.asList("An", null);
boolean allStrings = mixed.stream().allMatch(String.class::isInstance);
System.out.println(allStrings); // false
```

Nếu `null` được cho phép theo business contract, phải viết rõ điều kiện, ví dụ `value == null || value instanceof String`. Trong Spring AOP, `args(values)` bind **whole list**; nó không biết policy null của từng element.

### 9.3. Raw types/unchecked casts có thể phá lời hứa của declaration

```java
@SuppressWarnings({"rawtypes", "unchecked"})
static List<String> unsafe() {
    List raw = List.of(123);
    return raw; // Biên dịch với unchecked conversion, không kiểm tra elements.
}
```

Đây là **phản ví dụ** cho type safety, không phải pattern nên dùng. Runtime list chứa `Integer` dù caller về mặt source cầm `List<String>`. `Method.getGenericParameterTypes()` vẫn mô tả declaration `List<String>` nếu method contract là như vậy; nó không chứng minh object chứa String.

Khi validation là yêu cầu thực, kiểm tra nội dung tại boundary phù hợp hoặc dùng DTO/domain types không gây nhầm lẫn type parameter.

### 9.4. `getClass().getTypeParameters()` không phải câu trả lời

```java
List<String> names = List.of("An");
System.out.println(names.getClass().getTypeParameters().length);
```

Một concrete runtime class của List có thể không khai báo bất kỳ formal type variable nào cần cho suy luận; dù có generic type variables, chúng **không phải** actual `String` argument ở call site. Không dùng `getTypeParameters()` của runtime instance như cách “phục hồi List<String>”.

### 9.5. Return value generics có giới hạn tương tự

Nếu một service trả `List<User>`, `@AfterReturning(returning="result")` có thể bind reference được return; advice không tự xác minh mỗi User bên trong list. Nếu chỉ cần quan sát, dùng `List<?>`/`Object` thích hợp và tránh ép generic không được kiểm chứng. Đối với `@Around`, `proceed()` trả `Object`; advice phải trả lại value tương thích **declared return type** và không thay container object bằng một type khác.

## 10. Cạm bẫy khi đọc generic metadata trong Spring

| Vấn đề | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `jp.getArgs()[0].getClass()` không có `String` | Runtime List class bị generic erasure | Dùng declaration metadata nếu muốn biết chữ ký; inspect elements nếu cần validate |
| Advice `Collection<Invoice>` không lọc đúng contents | Spring không match generic collection elements | Bind `Collection<?>` rồi kiểm tra elements theo policy |
| Empty list passes allMatch String/Integer | Không có phần tử để phản chứng | Kết hợp `!isEmpty()` khi policy cần nonempty |
| `null` làm `getClass()` lỗi | Null không có runtime class | Kiểm tra null trước |
| Reflection thấy type variable `T` thay vì String | Đang đọc generic interface/base method, chưa resolve implementation binding | Dùng concrete target class context, `ResolvableType`, Spring method resolution |
| `MethodSignature.getMethod()` chỉ về interface | JDK proxy hoạt động trên interface methods | Dùng `AopUtils.getMostSpecificMethod(...)` |
| Có synthetic bridge method | Java compiler sinh bridge do erasure/overriding | Sử dụng `BridgeMethodResolver` nếu cần user method |
| `argNames` không hoạt động | Parameter name binding không đủ metadata hoặc sai tên | Khai báo đúng `argNames`, cấu hình `-parameters` nếu cần |
| Overload `m(List<String>)` và `m(List<Integer>)` không biên dịch | Hai method có cùng erased signature | Đặt method names khác hoặc dùng domain wrapper types |
| `@Around` trả raw List chứa sai element type | Advice chỉ giữ raw type, không bảo toàn generic contract | Giữ nguyên value/collection, test domain contract |
| Proxy không advice method cần inspect | Target không là Spring bean, aspect thiếu đăng ký hoặc self-invocation | Kiểm tra context/proxy/pointcut |
| Đổi CGLIB mà không sửa được generic mismatch | Proxy mode không tái tạo erased element type | Sửa validation/API thiết kế |
| Log toàn bộ generic payload | Dữ liệu có thể nhạy cảm, tốn chi phí, `toString()` side effects | Redaction, chỉ log metadata an toàn |
| Async Future/Reactive Publisher generic T không suy từ payload tức thời | Container wrapper đã return trước khi payload sẵn | Xử lý trong async/reactive context, giữ đúng wrapper contract |

### Quy trình kiểm tra để tránh suy luận quá mức

1. Xác nhận method thực sự được gọi qua **Spring AOP proxy** và pointcut đúng.
2. Xác định bạn muốn biết **declared generic signature** hay **runtime contents**.
3. Dùng `getArgs()` để lấy actual value, kiểm tra `null` và raw runtime interface.
4. Dùng `MethodSignature`/most-specific method/`ResolvableType` để đọc declared metadata, nếu cần.
5. Nếu muốn biết element types, định nghĩa explicit policy cho collection rỗng, null elements, mixed contents và mutable data.
6. Không dùng `Collection<T>` typed advice như công cụ tự động kiểm tra tất cả element types.
7. Xét bridge/interface method khi target là generic implementation.
8. Test Spring AOP integration trên đúng proxy mode, empty/null/mixed/boundary data; không chỉ dựa vào một sample hợp lệ.

## 11. Câu hỏi tự kiểm tra

**1. Spring `JoinPoint.getArgs()` có trả `List<String>` reified object không?** Không. Nó trả actual argument object; Java List runtime thông thường không lưu generic type argument String.

**2. `Method.getGenericParameterTypes()[0]` trả `List<String>` thì có chứng minh nội dung List gồm Strings không?** Không. Nó mô tả method declaration metadata, không kiểm tra runtime elements.

**3. Vì sao `Collection<Invoice>` trong signature advice không đủ để lọc runtime collection?** Vì erasure và Spring không tự duyệt từng phần tử hoặc quyết định null/empty policy.

**4. Nếu muốn kiểm tra thật những phần tử trong list, dùng gì?** Bind `Collection<?>`/`List<?>` rồi inspect phần tử bằng `instanceof`/`Class.isInstance` theo business policy.

**5. `allMatch(String.class::isInstance)` trên list rỗng trả gì?** True; đó không phải bằng chứng list có generic String.

**6. Vì sao một JDK proxy đôi khi chỉ cung cấp Method của interface trong signature?** Proxy thực hiện interface. Khi cần concrete metadata, resolve most-specific target method.

**7. Bridge method là gì trong bối cảnh Spring AOP generic target?** Method compiler có thể sinh để giữ polymorphism sau erasure; việc đọc signature/annotation cần quan tâm bridge resolution.

**8. `-parameters` có khôi phục `List<String>` runtime contents không?** Không. Nó giúp lưu Java parameter names; khác với generic metadata/element type checking.

**9. Việc đổi `proxyTargetClass=true` có giúp `args(...)` match List<String> elements tự động không?** Không. CGLIB không thay đổi generic erasure.

**10. Điểm nào nên chịu trách nhiệm validation dữ liệu?** Boundary/service/domain validation có contract rõ ràng; advice có thể quan sát hoặc áp cross-cutting policy nhưng không tự suy luận hơn khả năng runtime.

## Tài liệu Spring chính thức

- [Spring Framework — Declaring Advice: Advice Parameters and Generics](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Declaring Advice: binding args, advice parameter types](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — Declaring Pointcuts: args và execution](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 API — ResolvableType](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/ResolvableType.html)
- [Spring Framework 6.2 API — BridgeMethodResolver](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/BridgeMethodResolver.html)
- [Spring Framework — Proxying Mechanisms, JDK/CGLIB và self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework 6.2 API — AopUtils.getMostSpecificMethod](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/support/AopUtils.html)
