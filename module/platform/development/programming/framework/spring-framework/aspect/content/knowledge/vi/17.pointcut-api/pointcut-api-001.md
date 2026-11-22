# Pointcut, ClassFilter và MethodMatcher trong Spring AOP

## 1. Vấn đề: Spring quyết định advice áp dụng cho lời gọi nào?

Một interceptor Spring AOP không nên được chạy cho mọi phương thức trong ứng dụng. Ta thường chỉ muốn đo thời gian các phương thức nghiệp vụ, kiểm tra một nhóm service hoặc ghi nhận thao tác có điều kiện. **Pointcut** là hợp đồng lựa chọn những *method execution* mà một advice được phép tham gia khi lời gọi đi qua **Spring AOP proxy**.

Spring cung cấp hai con đường quen thuộc:

- Khai báo pointcut bằng biểu thức AspectJ trong `@Aspect`/XML, thường phù hợp với các quy tắc tên method, annotation hay package.
- Sử dụng trực tiếp **Spring Pointcut API** khi cần cấu thành điều kiện bằng Java, tái sử dụng một bộ lọc hoặc quyết định có điều kiện theo đối số thực tế.

Bài này tập trung vào con đường thứ hai: ba giao diện trong Spring và cách nối chúng với một Spring advisor/proxy.

```text
Caller -> Spring proxy -> Advisor
                              |
                              v
                          Pointcut
                           /    \
                 ClassFilter    MethodMatcher
                 lớp phù hợp?    method phù hợp?
                       \          /
                        \        /
                           yes
                            |
                         advice
                            |
                       target method
```

Nếu `ClassFilter` từ chối class hoặc `MethodMatcher` từ chối method, advice tương ứng sẽ không tham gia lời gọi đó. Target method vẫn có thể chạy bình thường qua proxy nếu không có advice khác từ chối.

## 2. Ba giao diện cốt lõi của Spring

### 2.1. `Pointcut`: kết hợp bộ lọc lớp và bộ khớp phương thức

API `org.springframework.aop.Pointcut`:

```java
public interface Pointcut {
    ClassFilter getClassFilter();
    MethodMatcher getMethodMatcher();
}
```

Spring dùng **cả hai** để xác định advisor có áp dụng được cho một method trên một target class hay không. `Pointcut.TRUE` là pointcut luôn khớp, hữu ích trong tình huống cần advice toàn bộ, nhưng có thể quá rộng đối với nghiệp vụ.

Pointcut **chỉ mô tả điều kiện chọn**. Nó không chứa mã thực thi trước/sau target. Trong Spring AOP, `DefaultPointcutAdvisor` ghép một pointcut với một `Advice` để tạo một quy tắc interception.

### 2.2. `ClassFilter`: chọn nhóm target class

API `org.springframework.aop.ClassFilter`:

```java
public interface ClassFilter {
    boolean matches(Class<?> clazz);
}
```

Trong ví dụ service:

```java
ClassFilter orderClasses =
        clazz -> OrderService.class.isAssignableFrom(clazz);
```

Điều kiện này khớp `OrderService` và các lớp con phù hợp. Nếu chỉ dùng `clazz == OrderService.class`, bộ lọc sẽ loại subclass và có thể gây bất ngờ khi mở rộng ứng dụng. Ngược lại, bộ lọc `clazz.getSimpleName().endsWith("Service")` có thể rộng ngoài ý định.

`ClassFilter.TRUE` cho phép mọi class; hãy chọn nó chỉ khi bộ lọc method hoặc pointcut khác thực sự đủ hẹp.

**Chú ý:** đối số `clazz` là thông tin về **target class** mà Spring dùng khi khớp, không phải tên proxy được tạo ra để caller gọi. Một class filter phù hợp không bảo đảm mọi method trong class đều bị chặn: `MethodMatcher` vẫn phải khớp.

### 2.3. `MethodMatcher`: chọn method tĩnh và tùy chọn theo đối số

API `org.springframework.aop.MethodMatcher`:

```java
public interface MethodMatcher {
    boolean matches(Method method, Class<?> targetClass);
    boolean isRuntime();
    boolean matches(Method method, Class<?> targetClass, Object... args);
}
```

Hai giai đoạn khớp có ý nghĩa khác nhau:

1. `matches(Method, Class<?>)` là **kiểm tra tĩnh** dựa trên method và target class; có thể được Spring tối ưu/lưu kết quả theo đặc điểm proxy.
2. Nếu kết quả tĩnh là `true` **và** `isRuntime() == true`, Spring tiếp tục gọi `matches(Method, Class<?>, Object... args)` **cho từng lần gọi**, trước advice, để kiểm tra các đối số cụ thể.

Với `isRuntime() == false`, phép khớp 3 tham số không được dùng để quyết định advice ở runtime. Với `isRuntime() == true`, điều kiện tĩnh vẫn là **cửa đầu tiên**; trả `false` ở giai đoạn này có thể khiến phần kiểm tra đối số không bao giờ chạy.

| Loại điều kiện | Ví dụ | Khớp tại thời điểm nào? | Chi phí |
| --- | --- | --- | --- |
| `ClassFilter` | Chỉ `OrderService` | Khi Spring xác định khả năng áp dụng advisor cho target class | Thường ít lần |
| `MethodMatcher` tĩnh | Tên method là `submit` và có hai tham số | Có thể được kiểm tra/cache trong chuỗi proxy | Thấp hơn động |
| `MethodMatcher` động | `quantity >= 10` tại mỗi lần `submit` | Với từng lời gọi có method đã khớp tĩnh | Cao hơn; phải đọc args mỗi lần |

Một điều kiện như `quantity >= 10` **không thể khớp chỉ bằng `Method` reflection**: `Method` mô tả chữ ký, không chứa giá trị `quantity` của từng lần gọi.

## 3. Thứ tự quyết định advice trong Spring proxy

Xét một advisor chứa một pointcut động:

```text
1. Caller gọi proxy.submit("A-1", 12).
2. Spring xem target class có qua ClassFilter không?
   └─ Không -> advisor không áp dụng.
3. Method submit(String,int) có qua matches(Method,Class) không?
   └─ Không -> advisor không áp dụng.
4. Nếu isRuntime() là true, kiểm tra matches(Method,Class,args)
   └─ False -> bỏ advice cho lần gọi này.
5. Nếu mọi điều kiện đúng, chạy advice.
6. Nếu advice gọi proceed(), chuỗi tiếp tục đến target.
```

**Điểm đặc thù Spring AOP:** cùng một method có thể lúc chạy advice, lúc không, nếu dùng dynamic matcher và các lần gọi có đối số khác nhau. Nhưng Spring AOP vẫn là cơ chế dựa trên **proxy**: self-invocation `this.submit(...)` thường không đi qua proxy, dù các điều kiện match đều đúng. `final`/`private` có giới hạn riêng của proxy; pointcut không tự sửa được giới hạn này.

Một advisor có thể chưa được đưa vào chuỗi proxy nếu Spring đánh giá toàn bộ class/method không phù hợp; vì vậy không nên dựa vào hiệu ứng phụ của `matches` để thực hiện logic nghiệp vụ.

## 4. Chọn lớp hỗ trợ thay vì tự viết lại toàn bộ giao diện

Spring có các lớp tiện ích:

| API | Khi nào nên dùng? | Chi tiết |
| --- | --- | --- |
| `StaticMethodMatcherPointcut` | Điều kiện chỉ phụ thuộc class/method | Override `matches(Method,Class)`; `isRuntime() == false` |
| `DynamicMethodMatcherPointcut` | Phải đọc đối số từng lần gọi | Override phép kiểm tra động, đồng thời thu hẹp kiểm tra tĩnh nếu biết trước |
| `NameMatchMethodPointcut` | Chọn method qua tên/pattern đơn giản | Không cần tự viết matcher |
| `JdkRegexpMethodPointcut` | Chọn method bằng regex | Kiểm tra pattern và phạm vi trước khi áp dụng rộng |
| `AspectJExpressionPointcut` | Muốn dùng cú pháp pointcut AspectJ trong Spring | Thích hợp cho nhiều quy tắc thường gặp |
| `ComposablePointcut` / `Pointcuts` | Cần hợp/ giao các pointcut | Có thể kết hợp bộ lọc mà không tạo lớp mới |

`StaticMethodMatcherPointcut` đã triển khai `Pointcut` và `MethodMatcher`; mặc định `ClassFilter.TRUE`, có thể thay bằng `setClassFilter(...)`.

`DynamicMethodMatcherPointcut` cũng triển khai `Pointcut` và `MethodMatcher`; lớp này mặc định cho phép mọi class qua `getClassFilter()` nên có thể override để thu hẹp. Khác với static matcher, cơ chế dynamic phải kiểm tra đối số ở thời điểm method thực sự được gọi.

Nên ưu tiên **pointcut tĩnh** nếu điều kiện chọn có thể xác định từ class/method. Dynamic matcher phù hợp khi giá trị đối số quyết định *có chạy advice hay không*, nhưng nó làm phát sinh một phép kiểm tra thêm trên mỗi lời gọi phù hợp.

## 5. Ví dụ hoàn chỉnh Java 17+: static và dynamic matcher trên cùng Spring proxy

Ví dụ minh họa:

- Advisor thứ nhất chỉ áp dụng cho method `OrderService.submit(String, int)`. Nó dùng `StaticMethodMatcherPointcut` và `ClassFilter`.
- Advisor thứ hai chỉ chạy khi cũng là method `submit` **và** `quantity >= 10`. Nó dùng `DynamicMethodMatcherPointcut`.
- `OrderService.status()` không khớp cả hai method matcher nên không sinh log advice.
- `OtherService.submit(...)` có method cùng tên nhưng bị class filter từ chối.

Ta dùng `ProxyFactory` để quan sát trực tiếp Spring AOP API. `ProxyFactory` thuộc Spring Framework, tạo một Spring proxy từ target và advisor; ví dụ không dùng AspectJ weaving hay annotation `@Aspect`.

Cấu trúc:

```text
spring-pointcut-api/
├── pom.xml
└── src/
    ├── main/java/example/PointcutDemo.java
    └── test/java/example/PointcutDemoTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>spring-pointcut-api</artifactId>
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

`src/main/java/example/PointcutDemo.java`:

```java
package example;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.aopalliance.intercept.MethodInterceptor;
import org.springframework.aop.ClassFilter;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.DynamicMethodMatcherPointcut;
import org.springframework.aop.support.StaticMethodMatcherPointcut;

public class PointcutDemo {
    public static class OrderService {
        private final List<String> events;

        public OrderService(List<String> events) {
            this.events = events;
        }

        public String submit(String sku, int quantity) {
            events.add("target:submit:" + quantity);
            return "OK:" + sku + ":" + quantity;
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
            events.add("other:submit");
            return "OTHER:" + sku + ":" + quantity;
        }
    }

    // Chỉ chọn OrderService (và subtype) + submit(String,int).
    public static class SubmitPointcut extends StaticMethodMatcherPointcut {
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

    // Tĩnh: chọn đúng method. Động: chỉ chạy advice khi quantity >= 10.
    public static class BulkPointcut extends DynamicMethodMatcherPointcut {
        @Override
        public ClassFilter getClassFilter() {
            return OrderService.class::isAssignableFrom;
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass) {
            return method.getName().equals("submit")
                    && method.getParameterCount() == 2
                    && method.getParameterTypes()[0] == String.class
                    && method.getParameterTypes()[1] == int.class;
        }

        @Override
        public boolean matches(Method method, Class<?> targetClass,
                               Object... args) {
            return args.length == 2
                    && args[1] instanceof Integer quantity
                    && quantity >= 10;
        }
    }

    public record Fixture(OrderService service, List<String> events) {}

    public static Fixture createFixture() {
        List<String> events = new ArrayList<>();
        ProxyFactory factory = new ProxyFactory(new OrderService(events));
        factory.setProxyTargetClass(true);

        MethodInterceptor trace = invocation -> {
            events.add("static:before");
            Object result = invocation.proceed();
            events.add("static:after");
            return result;
        };

        MethodInterceptor bulk = invocation -> {
            events.add("bulk:before");
            Object result = invocation.proceed();
            events.add("bulk:after");
            return result;
        };

        // Advisor đầu tiên là outer; advisor thứ hai là inner.
        factory.addAdvisor(new DefaultPointcutAdvisor(
                new SubmitPointcut(), trace));
        factory.addAdvisor(new DefaultPointcutAdvisor(
                new BulkPointcut(), bulk));

        OrderService proxy = (OrderService) factory.getProxy();
        return new Fixture(proxy, events);
    }

    public static void main(String[] args) {
        Fixture fixture = createFixture();
        OrderService service = fixture.service();

        System.out.println(service.submit("A-1", 2));
        System.out.println(service.submit("B-2", 12));
        System.out.println(service.status());
        System.out.println(fixture.events());

        // Cùng tên method nhưng khác target class -> bị ClassFilter loại.
        List<String> otherEvents = new ArrayList<>();
        ProxyFactory otherFactory =
                new ProxyFactory(new OtherService(otherEvents));
        otherFactory.setProxyTargetClass(true);
        otherFactory.addAdvisor(new DefaultPointcutAdvisor(
                new SubmitPointcut(),
                (MethodInterceptor) invocation -> {
                    otherEvents.add("SHOULD_NOT_RUN");
                    return invocation.proceed();
                }));
        OtherService other = (OtherService) otherFactory.getProxy();
        System.out.println(other.submit("C-3", 99));
        System.out.println(otherEvents);
    }
}
```

Giải thích code:

1. `SubmitPointcut` chọn đúng class `OrderService` và method `submit(String,int)`. Spring không cần đọc args để quyết định advisor này.
2. `BulkPointcut` dùng cùng điều kiện tĩnh, sau đó chỉ kích hoạt advice nếu tham số thứ hai là `Integer` có giá trị ít nhất `10`. Java boxing biến đối số primitive `int` thành `Integer` trong mảng `Object... args`.
3. `ProxyFactory.addAdvisor(...)` ghép điều kiện khớp với `MethodInterceptor`. Với advisor thứ nhất ở ngoài, sự kiện trace bọc quanh bulk khi cả hai phù hợp.
4. `invocation.proceed()` chuyển sang interceptor kế tiếp/target; nếu bỏ nó, target method có thể không chạy. `ClassFilter` không có nhiệm vụ thay thế `proceed()`.
5. Các event được lưu vào `List` chỉ để làm minh chứng. Ví dụ chạy tuần tự; nếu dùng đa luồng, cần cấu trúc thread-safe và chính sách đồng bộ thích hợp.

Chạy bằng Java 17 và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.PointcutDemo
```

Output logic mong đợi (không tính log Maven/Spring phụ thuộc môi trường):

```text
OK:A-1:2
OK:B-2:12
READY
[static:before, target:submit:2, static:after, static:before, bulk:before, target:submit:12, bulk:after, static:after, target:status]
OTHER:C-3:99
[other:submit]
```

Quan sát quan trọng:

- `submit(...,2)` khớp static matcher nhưng dynamic matcher trả `false`, do đó chỉ có `static:*`.
- `submit(...,12)` khớp cả hai advisor, thấy `static:before` → `bulk:before` → target → `bulk:after` → `static:after`.
- `status()` chỉ thêm `target:status`.
- `OtherService.submit` không có `SHOULD_NOT_RUN` vì `ClassFilter` loại target class đó. Việc tạo proxy bằng `ProxyFactory` cho target không bảo đảm một advisor nào cũng được chạy.

## 6. Kiểm thử riêng ClassFilter, MethodMatcher và đường đi proxy

Trong hệ thống thực, test tốt nên chứng minh cả **điều kiện thuần** lẫn **hành vi qua Spring proxy**. Test chỉ gọi `matches(...)` có thể bỏ qua lỗi wiring advisor; ngược lại, test chỉ nhìn log có thể bỏ sót trường hợp động không được kiểm tra.

`src/test/java/example/PointcutDemoTest.java`:

```java
package example;

import java.lang.reflect.Method;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.support.AopUtils;

import static org.junit.jupiter.api.Assertions.*;

class PointcutDemoTest {
    @Test
    void classAndMethodMatcherHaveExpectedContract() throws Exception {
        var staticPc = new PointcutDemo.SubmitPointcut();
        var dynamicPc = new PointcutDemo.BulkPointcut();

        Method submit = PointcutDemo.OrderService.class
                .getMethod("submit", String.class, int.class);
        Method status = PointcutDemo.OrderService.class
                .getMethod("status");

        assertTrue(staticPc.getClassFilter()
                .matches(PointcutDemo.OrderService.class));
        assertFalse(staticPc.getClassFilter()
                .matches(PointcutDemo.OtherService.class));
        assertTrue(staticPc.getMethodMatcher()
                .matches(submit, PointcutDemo.OrderService.class));
        assertFalse(staticPc.getMethodMatcher()
                .matches(status, PointcutDemo.OrderService.class));
        assertFalse(staticPc.getMethodMatcher().isRuntime());

        assertTrue(dynamicPc.getMethodMatcher().isRuntime());
        assertTrue(dynamicPc.getMethodMatcher()
                .matches(submit, PointcutDemo.OrderService.class));
        assertTrue(dynamicPc.getMethodMatcher()
                .matches(submit, PointcutDemo.OrderService.class, "A", 10));
        assertFalse(dynamicPc.getMethodMatcher()
                .matches(submit, PointcutDemo.OrderService.class, "A", 2));
    }

    @Test
    void proxyOnlyAppliesAdvisorsWhenFiltersMatch() {
        var fixture = PointcutDemo.createFixture();
        var service = fixture.service();

        assertTrue(AopUtils.isAopProxy(service));
        assertTrue(service instanceof Advised);
        assertEquals("OK:A:2", service.submit("A", 2));
        assertEquals("OK:B:12", service.submit("B", 12));
        assertEquals("READY", service.status());

        assertEquals(List.of(
                "static:before",
                "target:submit:2",
                "static:after",
                "static:before",
                "bulk:before",
                "target:submit:12",
                "bulk:after",
                "static:after",
                "target:status"), fixture.events());
    }
}
```

Chạy:

```bash
mvn -q test
```

Hai test xác minh những hợp đồng khác nhau. Test thứ nhất trực tiếp kiểm tra `ClassFilter`, chữ ký method và `isRuntime()`, kể cả cùng method nhưng args khác nhau. Test thứ hai tạo Spring proxy và kiểm tra sự kiện thực tế; việc method `status` không sinh advice bảo vệ khỏi match quá rộng. Khi đổi tên method hay thay class, một test tương tự sẽ giúp bắt lỗi phạm vi.

**Lưu ý về thiết kế test:** `Advised` giúp kiểm tra proxy có hỗ trợ tra cứu advisor; test không nên ràng buộc vào chi tiết tên class sinh ra (ví dụ chuỗi `$$SpringCGLIB$$`) vì không phải API ổn định.

## 7. Có bắt buộc tự triển khai `Pointcut` không?

Không. Nếu có sẵn `ClassFilter` và `MethodMatcher`, có thể ghép bằng `ComposablePointcut`:

```java
// Đoạn minh họa áp dụng trong chương trình có hai điều kiện phù hợp.
ClassFilter filter = OrderService.class::isAssignableFrom;
MethodMatcher matcher = new SubmitPointcut().getMethodMatcher();

Pointcut result = new ComposablePointcut(filter, matcher);
```

Các import liên quan:

```java
import org.springframework.aop.ClassFilter;
import org.springframework.aop.MethodMatcher;
import org.springframework.aop.Pointcut;
import org.springframework.aop.support.ComposablePointcut;
```

Lưu ý `SubmitPointcut` là lớp ví dụ mục 5, nên khi dùng đoạn minh họa trong package khác cần gọi đúng tên `PointcutDemo.SubmitPointcut` hoặc import lớp lồng thích hợp.

`ComposablePointcut` cung cấp `intersection(...)` và `union(...)` để kết hợp các điều kiện. Có khác biệt quan trọng:

- **Giao (intersection):** advice áp dụng khi các điều kiện đều đúng. Chẳng hạn service class phù hợp **và** method có annotation nhất định.
- **Hợp (union):** advice áp dụng khi ít nhất một nhánh pointcut đúng. Chẳng hạn thao tác `submit` **hoặc** `cancel` cần cùng một audit advice.

Khi tổ hợp **hai Pointcut hoàn chỉnh** bằng union, Spring giữ liên hệ giữa từng nhánh `ClassFilter` và `MethodMatcher` của nhánh đó; không tùy ý ghép class filter của nhánh này với method matcher của nhánh kia. Điều này giúp tránh match thừa mà một phép union ngây thơ có thể gây ra.

Có thể tái sử dụng các lớp `ClassFilters`, `MethodMatchers` và `Pointcuts` thuộc `org.springframework.aop.support` để gộp điều kiện. Tuy nhiên với các điều kiện tên method, annotation và package phổ biến, `AspectJExpressionPointcut` hoặc `@Pointcut` thường đọc ngắn hơn; đừng tạo một hệ thống matcher phức tạp nếu không có nhu cầu rõ ràng.

## 8. Kết nối Pointcut với Advisor và Spring Bean

Sơ đồ liên hệ:

```text
Pointcut                          Advice
(ClassFilter + MethodMatcher)     (MethodInterceptor ...)
        |                                  |
        +-------------+--------------------+
                      |
             DefaultPointcutAdvisor
                      |
               Spring AOP proxy
                      |
                    Target
```

Trong ví dụ ở mục 5, `ProxyFactory` xây một proxy **bằng API** và gắn các advisor trực tiếp. Trong một ứng dụng Spring sử dụng IoC, advisor có thể được đăng ký thành bean và được một auto-proxy creator phù hợp phát hiện, hoặc cấu hình qua `@Aspect`/XML. Đừng nhầm việc đăng ký riêng một bean kiểu `Pointcut` với việc advisor đã hoạt động: **Pointcut chưa gắn với Advice và cơ chế proxy sẽ không tự chạy**.

Nếu chỉ muốn áp dụng cho một bean khi tạo bằng Java code, `ProxyFactory` trực tiếp là ví dụ đơn giản nhất. Nếu nhiều bean cần chính sách nhất quán, dùng cấu hình advisor/auto-proxy phù hợp hoặc pointcut expression trong `@Aspect`.

### Phân biệt `Pointcut` API và `@Pointcut` annotation

| API | Bản chất | Kết nối thông thường |
| --- | --- | --- |
| `org.springframework.aop.Pointcut` | Đối tượng Java cung cấp `ClassFilter` và `MethodMatcher` | `DefaultPointcutAdvisor` hoặc `ProxyFactory` |
| `org.aspectj.lang.annotation.Pointcut` (viết `@Pointcut`) | Annotation đánh dấu phương thức khai báo biểu thức trong `@Aspect` | Advice `@Before`, `@Around`,... |
| `aop:pointcut` trong XML | Phần tử schema khai báo biểu thức pointcut có tên | `pointcut-ref` trên advisor/aspect advice |

Cả ba có liên hệ với việc **chọn** join point, nhưng không hoán đổi trực tiếp mã Java annotation cho một instance `org.springframework.aop.Pointcut`. Điểm chung là chúng chỉ có hiệu lực trên đường đi chặn được của Spring AOP.

## 9. Khi nào chọn static hay dynamic matcher?

**Nên dùng static matcher** khi:

- Chọn bằng method name/signature, class, package, annotation mà giá trị không phụ thuộc lần gọi.
- Cần chi phí runtime thấp và hành vi dễ đoán.
- Muốn bảo vệ phạm vi interceptor chặt chẽ và ít logic có trạng thái.

**Chỉ dùng dynamic matcher khi thực sự cần** xem args hoặc trạng thái chỉ có tại thời điểm gọi, chẳng hạn ghi metrics cho các đơn hàng có số lượng từ 10 trở lên. Mỗi invocation phải kiểm tra điều kiện động, vì vậy đừng đặt logic I/O, query DB hoặc xử lý nặng trong `matches(...,args)`.

Dynamic matcher quyết định **advice có tham gia** chứ không biến pointcut thành cơ chế validation đủ tin cậy. Trong ví dụ, đơn hàng số lượng 2 vẫn được gửi đến target bình thường; chỉ có bulk advice bị bỏ qua. Nếu quy tắc là “số lượng phải dương”, validation phải nằm tại tầng nghiệp vụ hoặc một interceptor được thiết kế rõ trách nhiệm và có xử lý lỗi tương ứng.

**Không cache kết quả dynamic theo Method** vì cùng một Method có thể gọi với các args khác nhau; ví dụ `submit("A", 2)` và `submit("A", 12)` cần kết quả advice khác nhau.

## 10. Giới hạn và bẫy thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Advice không chạy dù matcher trực tiếp trả true | Lời gọi bỏ qua Spring proxy, chưa gắn advisor | Lấy bean/proxy thật, kiểm tra `AopUtils.isAopProxy`, gọi qua nó |
| Method cùng tên bị chặn ở class khác | Dùng `ClassFilter.TRUE` và matcher theo tên quá rộng | Thu hẹp `ClassFilter`; test lớp khác nhưng method cùng tên |
| Advice động luôn chạy hoặc không chạy | Quên giai đoạn tĩnh, sai `isRuntime`, kiểm tra args sai vị trí | Test trực tiếp cả overload `matches` và event khi gọi proxy |
| `matches(Method,Class)` trả false nhưng hy vọng dynamic cứu | Spring lọc tĩnh trước khi xét args | Đảm bảo kết quả static true cho method cần xét |
| Method vẫn chạy khi dynamic condition false | Pointcut chỉ lọc advice, không bắt buộc chặn target | Đặt validation ở nơi đúng hợp đồng |
| Lỗi khi `proceed()` không được gọi | Around interceptor đã chặn chuỗi | Đảm bảo gọi `invocation.proceed()` trừ khi cố ý thay thế kết quả |
| `ClassFilter` dựa trên tên proxy | Proxy name thay đổi theo runtime/framework | So khớp target class/interface/annotation phù hợp |
| Hiệu năng giảm khi quá nhiều lần gọi | Matcher động đọc args cho mỗi invocation | Ưu tiên static; benchmark đường nóng |
| `final`, `private`, self-invocation không bị chặn | Giới hạn proxy Spring AOP | Thiết kế điểm vào bean, không dựa vào nội bộ |
| Kết hợp union làm match thừa | Tổ hợp điều kiện sai cấp độ | Dùng `ComposablePointcut`, test từng nhánh và phần giao |

**Kiểm chứng trước khi đưa vào production:** một test match đúng, một test không match theo method, một test không match theo class, một test thay args để dynamic đổi kết quả, một test call qua Spring proxy. Nếu advisor kiểm tra bảo mật hoặc giao dịch, còn phải test trường hợp bị từ chối và thứ tự với các advisor khác.

## 11. Bài thực hành nâng cao

Từ chương trình ở mục 5:

1. Đổi `SubmitPointcut` để chọn cả `submit` và `status`; dự đoán danh sách sự kiện khi gọi `status`. Sau đó đổi lại và chạy test.
2. Thêm `OrderService.cancel(String sku)` và một matcher riêng; dùng `ComposablePointcut.union(...)` để gắn cùng trace interceptor cho cả `submit` và `cancel`. Đảm bảo `OtherService.submit` vẫn không bị chặn.
3. Đổi điều kiện bulk thành `quantity >= 20` và test các giá trị 19/20, bao gồm ranh giới. Kiểm tra `isRuntime() == true`.
4. Tạo một điểm chặn chỉ chọn method gắn annotation tùy chỉnh. So sánh triển khai Java matcher dựa trên reflection với `AspectJExpressionPointcut` trong Spring, đồng thời kiểm thử annotation trên interface/implementation.
5. Đo thời gian gọi nhiều lần ở môi trường kiểm thử riêng khi có hoặc không có matcher động, tránh logging I/O bên trong phép đo. Kết luận dựa trên số đo thật thay vì suy đoán.

Bạn cần giải thích được vì sao **`Pointcut = ClassFilter + MethodMatcher`**, vì sao dynamic matcher chỉ chạy sau bước static, cách Spring nối Pointcut vào Advisor, và giới hạn khi lời gọi không đi qua proxy.

### Nguồn tham khảo Spring

- Spring Framework – Pointcut API: https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html
- Spring Framework 6.2 – `Pointcut` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/Pointcut.html
- `StaticMethodMatcherPointcut`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/support/StaticMethodMatcherPointcut.html
- `DynamicMethodMatcherPointcut`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/support/DynamicMethodMatcherPointcut.html
- `ComposablePointcut`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/aop/support/ComposablePointcut.html
- Spring proxy & self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
