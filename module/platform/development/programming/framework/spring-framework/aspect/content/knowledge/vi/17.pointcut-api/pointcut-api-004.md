# StaticMethodMatcherPointcut trong Spring AOP và các trường hợp áp dụng

## 1. Tại sao cần pointcut tĩnh?

Khi một Spring bean có nhiều phương thức, ta thường muốn gắn một advice chỉ với **một nhóm phương thức được xác định từ lớp và chữ ký**, chẳng hạn:

- Ghi nhận việc gọi `OrderService.submit(String, int)`, nhưng bỏ qua `status()`.
- Chỉ đo thời gian những phương thức public được đánh dấu bằng annotation nghiệp vụ.
- Áp dụng interceptor cho các method thuộc một nhóm service cụ thể.
- Giữ quy tắc lựa chọn phương thức ở Java code khi không muốn dùng biểu thức AspectJ/`@Aspect`.

Nếu phạm vi chặn có thể xác định **mà không cần nhìn vào giá trị đối số trong mỗi lần gọi**, Spring AOP cung cấp lớp cơ sở `StaticMethodMatcherPointcut`.

Đây là thành phần thuộc **Spring Framework AOP API**, không phải cơ chế chung của ngôn ngữ AspectJ. Nó giúp tạo một `Pointcut` có `MethodMatcher` tĩnh và có thể được gắn với `Advice` thông qua `Advisor` trên Spring proxy.

```text
Caller
  |
  v
Spring proxy
  |
  +--> Advisor
         |
         +--> ClassFilter.matches(targetClass)
         |       false -> bỏ advice của advisor này
         |
         +--> StaticMethodMatcher.matches(method, targetClass)
                 false -> bỏ advice của advisor này
                 true  -> cho phép advice tham gia chuỗi chặn
  |
  v
Target method (nếu advice cho phép tiếp tục)
```

**Điểm mấu chốt:** “static” nói về **điều kiện chọn method**, không có nghĩa advice chỉ chạy một lần. Nếu method khớp và caller gọi nó 1.000 lần qua proxy, advice có thể chạy 1.000 lần. Spring có thể lưu/ tái sử dụng kết quả khớp tĩnh để tránh kiểm tra lại không cần thiết; chính xác số lần gọi hàm `matches` là chi tiết triển khai và không nên trở thành hợp đồng nghiệp vụ.

## 2. Đặt StaticMethodMatcherPointcut vào kiến trúc Spring AOP

Giao diện `org.springframework.aop.Pointcut` gồm hai phần:

```java
public interface Pointcut {
    ClassFilter getClassFilter();
    MethodMatcher getMethodMatcher();
}
```

Trong đó `ClassFilter` xác định **target class** có thuộc phạm vi không:

```java
public interface ClassFilter {
    boolean matches(Class<?> clazz);
}
```

Còn `MethodMatcher` quyết định **method** có khớp hay không:

```java
public interface MethodMatcher {
    boolean matches(Method method, Class<?> targetClass);
    boolean isRuntime();
    boolean matches(Method method, Class<?> targetClass, Object... args);
}
```

Đây là các chữ ký API trích rút để giải thích, không phải các file bạn phải tạo thêm trong dự án.

`StaticMethodMatcherPointcut` là lớp trừu tượng trong package:

```java
org.springframework.aop.support.StaticMethodMatcherPointcut
```

Nó kế thừa `StaticMethodMatcher`, đồng thời triển khai `Pointcut`. Một subclass thông thường chỉ cần override:

```java
@Override
public boolean matches(Method method, Class<?> targetClass) {
    // Phân tích tên, chữ ký, annotation, targetClass...
    return ...;
}
```

Chú ý ba thuộc tính quan trọng:

| Thành phần | Hành vi của StaticMethodMatcherPointcut | Hệ quả |
| --- | --- | --- |
| `getClassFilter()` | Mặc định trả `ClassFilter.TRUE` | Nếu không thay, không giới hạn target class |
| `setClassFilter(ClassFilter)` | Đặt bộ lọc target class | Thu hẹp tập lớp trước khi xét method |
| `getMethodMatcher()` | Trả matcher của chính pointcut | Có thể đưa pointcut vào advisor |
| `isRuntime()` | Luôn `false` | Spring không chạy bước khớp theo `args` trên từng invocation |
| `matches(Method,Class,Object...)` | Không phải điểm mở rộng cho static matcher | Chỉ override `matches(Method,Class)` |

**Không cần tự viết cả ba phương thức `MethodMatcher`.** Đây chính là lý do dùng lớp cơ sở thay vì tự triển khai `Pointcut` và `MethodMatcher` từ đầu.

## 3. Phân biệt khớp tĩnh và khớp động

Giả sử muốn ghi metrics cho method `submit(String sku, int quantity)`.

**Điều kiện tĩnh**: “Đây có phải method tên `submit`, nhận `String` và `int` trên `OrderService`?” — Có thể trả lời bằng `Method` và `targetClass`.

**Điều kiện động**: “Giá trị `quantity` trong lần gọi hiện tại có lớn hơn 10 không?” — Phải nhìn mảng `args` mỗi lần method được gọi.

```text
submit("A", 2)   -> cùng Class và Method -> static matcher: TRUE
submit("A", 20)  -> cùng Class và Method -> static matcher: TRUE

Nếu yêu cầu quantity >= 10:
submit("A", 2)   -> dynamic matcher: FALSE
submit("A", 20)  -> dynamic matcher: TRUE
```

| Tiêu chí | StaticMethodMatcherPointcut | DynamicMethodMatcherPointcut |
| --- | --- | --- |
| Dữ liệu dùng để quyết định | `Method`, `Class<?>` | `Method`, target class và `Object... args` |
| `isRuntime()` | `false` | `true` |
| Phải kiểm tra đối số trên từng lần gọi? | Không | Có, sau khi vượt qua kiểm tra tĩnh |
| Trường hợp thường gặp | tên/chữ ký method, class, annotation | điều kiện dựa vào giá trị tham số của invocation |
| Chi phí khớp | Thường thấp, có thể tối ưu/cache | Có bước đánh giá bổ sung mỗi lần gọi |

**Không sử dụng `StaticMethodMatcherPointcut` để kiểm tra giá trị đầu vào** như `quantity > 0`. Ngay cả khi một static matcher trả `true`, mã của advice hoặc chính service vẫn phải xử lý hợp đồng nghiệp vụ nếu cần từ chối dữ liệu sai. Pointcut quyết định *advice có tham gia*, không phải nơi mặc định thực hiện validation.

## 4. Thiết kế điều kiện tĩnh đúng và đủ chặt

Một implementation cơ bản:

```java
import java.lang.reflect.Method;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public final class SubmitPointcut extends StaticMethodMatcherPointcut {
    public SubmitPointcut() {
        setClassFilter(OrderService.class::isAssignableFrom);
    }

    @Override
    public boolean matches(Method method, Class<?> targetClass) {
        return method.getName().equals("submit")
                && method.getParameterCount() == 2
                && method.getParameterTypes()[0] == String.class
                && method.getParameterTypes()[1] == int.class;
    }
}
```

Đây là một trích đoạn: `OrderService` phải có trong cùng module. Bản chạy độc lập sẽ xuất hiện ở mục 6.

Ý nghĩa của hai bước:

1. `setClassFilter(OrderService.class::isAssignableFrom)` giới hạn những target class là `OrderService` hoặc subtype.
2. `matches(Method,Class)` xác định chính xác overload `submit(String,int)`. Nó không match overload `submit(String)` hay method `status()`.

### Chọn theo tên method có đủ không?

Điều kiện:

```java
return method.getName().equals("submit");
```

có thể vô tình match `submit(String)`, `submit(String,int)`, `submit(Order)`. Nếu interceptor cần đọc đối số ở vị trí cố định hoặc dựa vào kiểu trả về, phải kiểm tra chữ ký phù hợp. Trong một số nhu cầu, tên method là đủ; khi đó ghi rõ rằng **mọi overload** sẽ được chọn.

### Target class có ảnh hưởng gì?

Một lớp khác cùng có method `submit(String,int)` không nhất thiết thuộc phạm vi. Nếu giữ mặc định `ClassFilter.TRUE` và matcher chỉ kiểm tra tên/chữ ký, advisor có thể chặn cả lớp khác. Nếu mục tiêu là riêng `OrderService`, đặt class filter phù hợp.

Đừng so sánh tên proxy sinh ra như `clazz.getName().contains("CGLIB")`: đó là chi tiết triển khai, không phải đặc điểm nghiệp vụ. Dùng kiểu lớp, interface, annotation hay cấu trúc package có quy tắc rõ.

### Nên kiểm tra annotation như thế nào?

Sự hiện diện của một annotation runtime trên một method là **metadata tĩnh** đối với lời gọi. Tuy nhiên khi dùng JDK proxy, method có thể là phương thức khai báo trên interface; metadata của implementation có thể cần được tìm bằng API Spring:

```java
// Trích đoạn minh họa logic trong matches(...):
Method specific = AopUtils.getMostSpecificMethod(method, targetClass);
return AnnotatedElementUtils.hasAnnotation(specific, Monitored.class);
```

Import:

```java
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;
```

`Monitored` là annotation ứng dụng cần tự khai báo với `@Retention(RUNTIME)` và `@Target(METHOD)`. `AnnotatedElementUtils` hỗ trợ cách Spring xử lý một số trường hợp meta-annotation/merged annotation; nếu dự án có bridge method, generic/interface method hoặc override phức tạp, hãy test đúng kiểu proxy thật. Chỉ dùng `method.getAnnotation(...)` trong mọi hoàn cảnh có thể bỏ sót annotation trên implementation.

## 5. Từ Pointcut sang Advice: bản thân matcher không tạo interception

`StaticMethodMatcherPointcut` chỉ quyết định *có khớp hay không*. Để tác động tới lời gọi, phải kết nối:

```text
StaticMethodMatcherPointcut
         +
MethodInterceptor (Advice)
         |
         v
DefaultPointcutAdvisor
         |
         v
Spring AOP proxy
         |
         v
Service target
```

Trong mã Java, cấu trúc thường là:

```java
MethodInterceptor interceptor = invocation -> {
    System.out.println("before");
    try {
        return invocation.proceed();
    } finally {
        System.out.println("after");
    }
};

var advisor = new DefaultPointcutAdvisor(
        new SubmitPointcut(), interceptor);

var proxyFactory = new ProxyFactory(target);
proxyFactory.addAdvisor(advisor);
Object proxy = proxyFactory.getProxy();
```

Đây là đoạn mô tả wiring: cần khai báo `target` và `SubmitPointcut` trong chương trình. `DefaultPointcutAdvisor` ghép một `Pointcut` với một `Advice`; `ProxyFactory` tạo Spring AOP proxy.

Lệnh `invocation.proceed()` đưa lời gọi qua phần còn lại của interceptor chain đến target (trừ khi interceptor khác chặn tiếp). Nếu quên gọi mà cũng không chủ ý thay thế kết quả, target method sẽ không thực thi. Khối `finally` vẫn chạy khi target ném lỗi; đó là hành vi của **advice**, độc lập với việc static pointcut chọn method.

**Phân biệt `Pointcut` và `@Pointcut`:** `org.springframework.aop.Pointcut` là một đối tượng có `ClassFilter` và `MethodMatcher`; `org.aspectj.lang.annotation.Pointcut` là annotation dùng khai báo pointcut trong `@Aspect`. Hai API có liên hệ khái niệm nhưng cách cấu hình không giống nhau.

## 6. Ví dụ hoàn chỉnh với Java 17 và Spring ProxyFactory

Ví dụ bên dưới không cần `@Aspect` hay AspectJ Weaver. Ta dùng trực tiếp Spring AOP API để minh họa đúng cách `StaticMethodMatcherPointcut` được nối vào advisor.

Mục tiêu kiểm thử:

- Chặn `OrderService.submit(String,int)` ở mọi giá trị `quantity`.
- Không chặn `OrderService.submit(String)` (overload) hoặc `OrderService.status()`.
- Không chặn `OtherService.submit(String,int)`, dù trùng tên/chữ ký.
- Ghi nhận chính xác thứ tự lời gọi `before → target → after` và giữ nguyên giá trị trả về.

Cấu trúc:

```text
spring-static-pointcut/
├── pom.xml
└── src/
    ├── main/java/example/StaticPointcutDemo.java
    └── test/java/example/StaticPointcutDemoTest.java
```

### 6.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-static-pointcut</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.8</version>
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
```

### 6.2. File src/main/java/example/StaticPointcutDemo.java

```java
package example;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public class StaticPointcutDemo {

    public static class OrderService {
        private final List<String> events;

        public OrderService(List<String> events) {
            this.events = events;
        }

        public String submit(String sku, int quantity) {
            events.add("target:submit:" + sku + ":" + quantity);
            return "OK:" + sku + ":" + quantity;
        }

        public String submit(String sku) {
            events.add("target:overload:" + sku);
            return "OVERLOAD:" + sku;
        }

        public String status() {
            events.add("target:status");
            return "READY";
        }
    }

    public static class OtherService {
        private final List<String> events;

        public OtherService(List<String> events) {
            this.events = events;
        }

        public String submit(String sku, int quantity) {
            events.add("other:submit:" + sku + ":" + quantity);
            return "OTHER:" + sku + ":" + quantity;
        }
    }

    public static class SubmitPointcut extends StaticMethodMatcherPointcut {
        public SubmitPointcut() {
            // Chỉ OrderService (hoặc subclass) đủ điều kiện.
            setClassFilter(OrderService.class::isAssignableFrom);
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            return method.getName().equals("submit")
                    && method.getParameterCount() == 2
                    && method.getParameterTypes()[0] == String.class
                    && method.getParameterTypes()[1] == int.class;
        }
    }

    public record Fixture(OrderService service, List<String> events) {}

    public static Fixture createFixture() {
        List<String> events = new ArrayList<>();
        OrderService target = new OrderService(events);

        MethodInterceptor trace = invocation -> {
            events.add("before:" + invocation.getMethod().getName());
            try {
                return invocation.proceed();
            } finally {
                events.add("after:" + invocation.getMethod().getName());
            }
        };

        ProxyFactory factory = new ProxyFactory(target);
        factory.setProxyTargetClass(true);
        factory.addAdvisor(new DefaultPointcutAdvisor(
                new SubmitPointcut(), trace));

        return new Fixture((OrderService) factory.getProxy(), events);
    }

    public static OtherService createOtherProxy(List<String> events) {
        ProxyFactory factory = new ProxyFactory(new OtherService(events));
        factory.setProxyTargetClass(true);

        MethodInterceptor trace = invocation -> {
            events.add("UNEXPECTED");
            return invocation.proceed();
        };

        // Cùng advisor nhưng ClassFilter không chọn OtherService.
        factory.addAdvisor(new DefaultPointcutAdvisor(
                new SubmitPointcut(), trace));

        return (OtherService) factory.getProxy();
    }

    public static void main(String[] args) {
        Fixture fixture = createFixture();
        OrderService order = fixture.service();

        System.out.println(order.submit("A", 2));
        System.out.println(order.submit("B", 12));
        System.out.println(order.submit("A"));
        System.out.println(order.status());

        List<String> otherEvents = new ArrayList<>();
        OtherService other = createOtherProxy(otherEvents);
        System.out.println(other.submit("C", 99));

        System.out.println("orderEvents=" + fixture.events());
        System.out.println("otherEvents=" + otherEvents);
    }
}
```

Giải thích theo từng thành phần:

1. `SubmitPointcut` là subclass của Spring `StaticMethodMatcherPointcut`; class filter loại `OtherService` trước khi xét method.
2. `matches` chỉ xem **tên và chữ ký**. Dù `quantity` là 2, 12 hay 0, kết quả khớp của `submit(String,int)` giống nhau.
3. `ProxyFactory` nhận target và thêm `DefaultPointcutAdvisor`. Phương thức `submit` qua proxy mới chạy interceptor; tạo trực tiếp `new OrderService(events)` rồi gọi sẽ không có advice.
4. `factory.setProxyTargetClass(true)` yêu cầu proxy dựa trên class để có thể ép kiểu kết quả thành `OrderService`/`OtherService`. Trong ứng dụng dùng interface, JDK proxy có thể là lựa chọn phù hợp nhưng phải lấy bean qua interface.
5. Advice sử dụng `try/finally`, do đó `after:submit` cũng xảy ra nếu target có exception. Đây là **điều khoản do advice viết**, không phải do pointcut tự sinh ra.

Chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.StaticPointcutDemo
```

Stdout logic kỳ vọng (không tính log phụ thuộc Maven/Spring nếu có):

```text
OK:A:2
OK:B:12
OVERLOAD:A
READY
OTHER:C:99
orderEvents=[before:submit, target:submit:A:2, after:submit, before:submit, target:submit:B:12, after:submit, target:overload:A, target:status]
otherEvents=[other:submit:C:99]
```

Bằng chứng từ output:

- Hai lời gọi `submit(String,int)` đều sinh `before`/`after` dù số lượng khác nhau. Đây là bản chất **static**.
- `submit(String)` có cùng tên nhưng khác overload, chỉ ghi `target:overload:A`.
- `status()` không bị advice chặn; `OtherService.submit(...)` cũng không có `UNEXPECTED` nhờ class filter.
- Các method đích vẫn trả về kết quả như bình thường, vì interceptor gọi `proceed()`.

## 7. Kiểm thử đúng hai tầng: hợp đồng matcher và proxy thật

Một test chỉ gọi `pointcut.matches(...)` chưa chứng minh advisor đã được gắn vào proxy. Một test chỉ kiểm tra log khi gọi service có thể bỏ sót việc matcher có `ClassFilter` quá rộng. Kết hợp hai tầng:

`src/test/java/example/StaticPointcutDemoTest.java`:

```java
package example;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;

import static org.junit.jupiter.api.Assertions.*;

class StaticPointcutDemoTest {

    @Test
    void staticMatcherMatchesOnlyExpectedClassAndSignature()
            throws Exception {
        var pointcut = new StaticPointcutDemo.SubmitPointcut();

        Method matched = StaticPointcutDemo.OrderService.class
                .getMethod("submit", String.class, int.class);
        Method overload = StaticPointcutDemo.OrderService.class
                .getMethod("submit", String.class);
        Method status = StaticPointcutDemo.OrderService.class
                .getMethod("status");

        assertTrue(pointcut.getClassFilter()
                .matches(StaticPointcutDemo.OrderService.class));
        assertFalse(pointcut.getClassFilter()
                .matches(StaticPointcutDemo.OtherService.class));

        assertTrue(pointcut.getMethodMatcher()
                .matches(matched, StaticPointcutDemo.OrderService.class));
        assertFalse(pointcut.getMethodMatcher()
                .matches(overload, StaticPointcutDemo.OrderService.class));
        assertFalse(pointcut.getMethodMatcher()
                .matches(status, StaticPointcutDemo.OrderService.class));

        assertFalse(pointcut.getMethodMatcher().isRuntime());
    }

    @Test
    void springProxyAppliesInterceptorToEveryMatchingInvocation() {
        var fixture = StaticPointcutDemo.createFixture();
        var order = fixture.service();

        assertTrue(AopUtils.isAopProxy(order));
        assertEquals("OK:A:2", order.submit("A", 2));
        assertEquals("OK:B:12", order.submit("B", 12));
        assertEquals("OVERLOAD:A", order.submit("A"));
        assertEquals("READY", order.status());

        assertEquals(List.of(
                "before:submit",
                "target:submit:A:2",
                "after:submit",
                "before:submit",
                "target:submit:B:12",
                "after:submit",
                "target:overload:A",
                "target:status"), fixture.events());
    }

    @Test
    void anotherClassWithSameMethodSignatureIsExcluded() {
        List<String> events = new ArrayList<>();
        var other = StaticPointcutDemo.createOtherProxy(events);

        assertEquals("OTHER:C:99", other.submit("C", 99));
        assertEquals(List.of("other:submit:C:99"), events);
    }
}
```

Chạy:

```bash
mvn -q test
```

Ba phép thử đáp ứng ba câu hỏi:

| Test | Kiểm chứng |
| --- | --- |
| `staticMatcherMatchesOnlyExpectedClassAndSignature` | ClassFilter và MethodMatcher phân biệt đúng class, overload, method khác; `isRuntime()==false` |
| `springProxyAppliesInterceptorToEveryMatchingInvocation` | Advice được gắn lên Spring proxy, chạy ở cả quantity=2 và quantity=12, giữ kết quả target |
| `anotherClassWithSameMethodSignatureIsExcluded` | ClassFilter ngăn chặn advisor của một class khác có cùng tên/chữ ký method |

**Tránh tạo test kiểm tra “`matches` chỉ chạy chính xác một lần”.** Spring có thể kiểm tra khả năng áp dụng advisor lúc tạo proxy, lúc gọi đầu tiên hoặc qua những nhánh xử lý khác. Hợp đồng công khai ở đây là không kiểm tra `args` ở runtime, không phải bộ đếm lời gọi phương thức matcher cố định.

## 8. Các trường hợp thực tế phù hợp

### 8.1. Ghi metrics cho một nhóm method cố định

Chọn các method public trên những service có tên nghiệp vụ phù hợp. Ví dụ bộ lọc như:

```java
@Override
public boolean matches(Method method, Class<?> targetClass) {
    return method.getName().startsWith("find")
            && method.getParameterCount() <= 2;
}
```

Đây là trích đoạn method trong subclass `StaticMethodMatcherPointcut`, không phải class chạy độc lập. Nếu muốn đo latency, advice dùng `System.nanoTime()` bao quanh `proceed()`; phần **chọn method** không phải đo latency. Khi service bất đồng bộ trả `CompletableFuture`, thời gian quanh `proceed()` không nhất thiết là thời gian hoàn thành future.

### 8.2. Áp dụng chính sách theo annotation method

Nếu chính sách được khai báo tĩnh bằng `@Measured` hoặc `@Audited`, matcher có thể xem annotation trên method và dùng `ClassFilter` thu hẹp tới service package/kiểu target. Điều kiện annotation ổn định giữa các lần gọi nên hợp lý với static pointcut. Tuy nhiên chính sách bên trong advice vẫn cần thiết kế, kiểm thử dữ liệu nhạy cảm và hậu quả của lỗi.

### 8.3. Lọc theo chữ ký, overload hoặc interface

Với API có nhiều overload cùng tên, static matcher giúp phân biệt chính xác `submit(String,int)` và `submit(String)`. Nếu dùng JDK dynamic proxy, method phản ánh interface có thể khác method implementation. Hãy test **cả kiểu proxy và vị trí annotation thực tế**. `ClassFilter` chỉ nhìn target class; không mặc định phải là tên proxy.

### 8.4. Một pointcut dùng lại cho nhiều advice

Vì pointcut độc lập với advice, có thể gắn cùng một instance hoặc cùng một class pointcut vào nhiều advisor:

```java
var pointcut = new SubmitPointcut();

factory.addAdvisor(new DefaultPointcutAdvisor(pointcut, metricsAdvice));
factory.addAdvisor(new DefaultPointcutAdvisor(pointcut, auditAdvice));
```

Đây là trích đoạn wiring khi đã có `factory`, `metricsAdvice`, `auditAdvice`. Nếu hai advice cùng khớp, thứ tự advisor ảnh hưởng thứ tự quan sát. Dùng `@Order` ở một nơi khác không tự bảo đảm thứ tự các advisor đã thêm thủ công vào `ProxyFactory`; hãy cấu hình và kiểm thử thứ tự cụ thể.

### 8.5. Khi không nên dùng custom static matcher

- Điều kiện chặn đơn giản kiểu tên method: cân nhắc `NameMatchMethodPointcut` để giảm code.
- Điều kiện biểu thức package/annotation/interface thường gặp: `AspectJExpressionPointcut` hoặc `@Pointcut` trong một Spring `@Aspect` có thể dễ đọc hơn.
- Cần xem giá trị đối số mỗi lần gọi: dùng một `DynamicMethodMatcherPointcut` phù hợp hoặc đưa kiểm tra vào advice/service theo trách nhiệm.
- Cần chặn constructor, field access hoặc lời gọi nội bộ không đi qua proxy: Spring AOP proxy không hỗ trợ trực tiếp các join point đó, dù có custom pointcut.

## 9. Tổ hợp nhiều điều kiện tĩnh

Spring hỗ trợ `ComposablePointcut` và tiện ích `Pointcuts` để hợp (union) hoặc giao (intersection) các điều kiện.

- **Giao:** method phải thỏa **cả hai** yêu cầu, ví dụ class service phù hợp *và* method có annotation.
- **Hợp:** method thỏa **ít nhất một nhánh**, ví dụ `submit` *hoặc* `cancel`.

Ví dụ gợi ý dạng minh họa:

```java
// Một pointcut chọn submit(String,int).
var submit = new SubmitPointcut();

// Một pointcut khác chọn cancel(String).
var cancel = new CancelPointcut();

// Tạo pointcut gộp, rồi đưa vào DefaultPointcutAdvisor.
var combined = new ComposablePointcut(submit).union(cancel);
```

Đây là trích đoạn minh họa API: `SubmitPointcut` có trong ví dụ mục 6, còn `CancelPointcut` và method `cancel` cần được tạo trước khi chạy. Import `org.springframework.aop.support.ComposablePointcut`. Khi ghép các pointcut hoàn chỉnh, cần giữ đúng ý nghĩa quan hệ giữa **ClassFilter và MethodMatcher của từng nhánh**; không tự gộp “mọi class của hai nhánh” với “mọi method của hai nhánh” nếu điều đó làm match thừa.

Khi pointcut đã đơn giản, việc tự viết quá nhiều lớp matcher và tổ hợp có thể khó hiểu hơn một biểu thức pointcut rõ nghĩa. Chọn API vì nó làm hợp đồng chặn minh bạch và kiểm thử được, không vì muốn thay toàn bộ `@Aspect`.

## 10. Giới hạn của Spring proxy và những bẫy thiết kế

| Triệu chứng | Nguyên nhân | Cách kiểm chứng/khắc phục |
| --- | --- | --- |
| Test `matches` đúng nhưng advice không chạy | Advisor chưa gắn vào proxy hoặc caller dùng target trực tiếp | Dùng `ProxyFactory`/Spring bean proxy thật và `AopUtils.isAopProxy(...)` |
| Method khác cũng bị chặn | Matcher chỉ nhìn tên, không phân biệt overload/class | Kiểm tra tên, số lượng và kiểu tham số; đặt ClassFilter |
| Method đúng tên nhưng không bị chặn | `ClassFilter` loại target class hoặc chữ ký không trùng | Test riêng ClassFilter và MethodMatcher trên class thực |
| Cần phân biệt quantity=2 và quantity=12 nhưng advice luôn chạy | Static matcher không đọc giá trị `args` | Dùng dynamic matcher hoặc điều kiện trong advice/service |
| Overload interface/implementation khác nhau | Method nhận được có thể là khai báo trên interface | Dùng API tra method cụ thể và test kiểu proxy thực |
| Caller trong bean dùng `this.submit(...)` | Self-invocation bỏ qua proxy | Gọi qua một Spring-managed proxy/boundary thích hợp |
| Target là method `final`/`private` | Proxy-based AOP có giới hạn ghi đè/khả năng chặn | Thiết kế method có thể proxy được; kiểm thử integration |
| Advice không gọi target | Interceptor không gọi `proceed()` | Tiếp tục chuỗi trừ khi có chủ ý thay đổi hợp đồng |
| Matcher truy vấn DB/log I/O khi khớp | Side effect và chi phí ở giai đoạn chọn advisor | Giữ matcher thuần, nhẹ, không phụ thuộc trạng thái mutable |
| Kết quả test phụ thuộc số lần `matches` được gọi | Coi chiến lược cache là hợp đồng | Test kết quả match và hành vi advice, không test internal call count |

### Vì sao matcher nên là hàm thuần?

Method matcher nhận thông tin tĩnh về phương thức/lớp. Nếu nó phụ thuộc “thời điểm hiện tại”, biến toàn cục có thể thay đổi, trạng thái của request hoặc I/O ngoại vi, kết quả có thể không nhất quán với cách framework lưu kết quả match tĩnh. Đừng đưa logic nghiệp vụ có trạng thái vào `matches`. Hãy dùng điều kiện tĩnh thật sự, hoặc chuyển logic phụ thuộc invocation vào thành phần phù hợp.

### Self-invocation và kiểm thử trên bean thật

Giả sử `OrderService.status()` gọi `this.submit("A",2)`. Ở chế độ Spring proxy thường gặp, lần gọi nội bộ không qua proxy, nên advice cho `submit` có thể không xuất hiện. Điều này **không chứng minh matcher sai**. Khi kiểm thử hành vi AOP, luôn bắt đầu từ caller lấy được **proxy** chứ không dùng chính target object để xác nhận interception.

### Làm rõ tài nguyên và lỗi

Static pointcut có thể chọn đúng method nhưng vẫn chưa giải quyết vấn đề chạy advice khi exception, transaction, bất đồng bộ hoặc reactive. Những nội dung đó được xác định bởi **Advice/Advisor và chuỗi proxy**, không bởi tên `StaticMethodMatcherPointcut`. Ví dụ metrics có `finally` sẽ chạy ghi thời gian dù exception; còn `@AfterReturning` chỉ áp dụng khi lời gọi trả về bình thường.

## 11. Bài tập thực hành và tiêu chí hoàn thành

Từ chương trình `StaticPointcutDemo`:

1. Thêm method `submit(String,int,boolean)`. Giữ matcher hiện tại và kiểm tra overload mới **không bị chặn**.
2. Thay `ClassFilter` bằng `ClassFilter.TRUE`, tạo một `OtherService` proxy với cùng advisor và kiểm tra nó bắt đầu sinh log `UNEXPECTED`. Trả filter cũ về để sửa.
3. Thay matcher thành điều kiện chọn cả `submit` và `status`; dự đoán rồi xác nhận thứ tự các event.
4. Thêm annotation `@Measured` trên `submit` và sửa matcher chỉ chọn method có annotation. Kiểm thử một implementation có interface nếu ứng dụng dùng JDK proxy.
5. Muốn chỉ đo các lần có `quantity >= 10`: giải thích vì sao static matcher không đủ; chuyển sang dynamic matcher hoặc điều kiện có chủ đích trong interceptor rồi test ranh giới 9/10.
6. Đặt một counter vào chính advice và một counter chẩn đoán vào matcher. Chạy nhiều invocation, quan sát sự khác biệt, nhưng **không biến số lần Spring gọi matcher thành điều kiện pass/fail**, vì cơ chế tối ưu có thể khác nhau.

Một bài triển khai đạt yêu cầu khi bạn chứng minh được: đúng target class, đúng method/overload, advice chạy **mỗi lần method đã chọn được gọi qua proxy**, dữ liệu kết quả/exception của method được giữ đúng, method và class ngoài phạm vi không bị chặn, và không nhầm điều kiện tĩnh với kiểm tra đối số động.

### Tài liệu chính thức của Spring

- Pointcut API và static/dynamic matcher: https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html
- `StaticMethodMatcherPointcut` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aop/support/StaticMethodMatcherPointcut.html
- `StaticMethodMatcher` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aop/support/StaticMethodMatcher.html
- Advisor API: https://docs.spring.io/spring-framework/reference/core/aop-api/advisor.html
- Spring proxy và self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
