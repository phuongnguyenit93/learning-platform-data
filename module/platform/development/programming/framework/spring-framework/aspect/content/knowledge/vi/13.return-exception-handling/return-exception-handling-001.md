# Giữ hợp đồng trả về khi advice bọc phương thức đích trong Spring AOP

## 1. Vấn đề: around advice có thể thay đổi thứ caller nhận được

Trong **Spring AOP**, một Spring-managed bean có thể được bọc bằng JDK dynamic proxy hoặc CGLIB proxy để các advice thực thi khi caller gọi một method qua proxy. Với `@Around`, advice không chỉ được làm việc trước/sau method mà còn **quyết định có chuyển tiếp lời gọi, trả giá trị nào hoặc ném exception nào**.

Điều này đặt ra trách nhiệm rất rõ: **nếu mục tiêu của aspect chỉ là logging, tracing, metrics hay quan sát kết quả, phải giữ nguyên hợp đồng của method đích**. Không được vô ý làm mất giá trị trả về, trả sai kiểu, biến kết quả thành `null`, đổi semantic của `Optional` hoặc nuốt exception.

Quy tắc quan trọng nhất:

~~~java
@Around("execution(* demo.CatalogService.*(..))")
public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
    // Thực hiện hành vi trước khi vào target nếu cần.
    Object result = pjp.proceed();
    // Chỉ quan sát result, không thay đổi reference nếu không được yêu cầu.
    return result;
}
~~~

Đoạn này là **method advice minh họa**: phải đặt trong Spring bean `@Aspect`, có import `org.aspectj.lang.ProceedingJoinPoint` và `org.aspectj.lang.annotation.Around`, cùng bean target và pointcut hợp lệ. Nó không phải một chương trình Java độc lập.

**Vì sao cần trả `Object`?** Theo tài liệu Spring Framework, `@Around` nên khai báo kiểu trả về `Object`; giá trị advice trả về sẽ là giá trị mà **caller của method đích nhìn thấy**. Thông thường, hãy `return pjp.proceed();` ngay cả khi method đích là `void`. Nếu khai báo chính method `@Around` trả `void`, Spring sẽ đưa `null` trở lại interceptor chain, làm mất return value của method đích; với method trả primitive thì `null` còn có thể dẫn đến lỗi invocation.

Nội dung tập trung **Spring Aspect trong Spring Framework**, không chuyển sang lý thuyết AspectJ weaving tổng quát.

## 2. Hợp đồng trả về gồm những gì?

Trong Java, “hợp đồng trả về” không chỉ là một từ khóa `return`. Đối với caller sử dụng một Spring AOP proxy, cần bảo toàn các thuộc tính có ý nghĩa:

| Thành phần hợp đồng | Ví dụ method | Điều advice quan sát thuần túy phải giữ |
| --- | --- | --- |
| **Kiểu khai báo** | `String label(...)` | Caller tiếp tục nhận đối tượng `String` hoặc `null` nếu method contract cho phép |
| **Giá trị** | `int quantity()` | Giữ đúng giá trị số, không vô tình trả `0` hay giá trị khác |
| **Primitive không-null** | `boolean enabled()` | Không trả `null` hoặc wrapper sai kiểu cho primitive |
| **Reference identity** | `Customer findById(...)` | Không thay object khác khi requirement chỉ là quan sát; Spring có một số xử lý đặc biệt khi target trả chính `this` |
| **Nullability** | `String nullable()` | Nếu target trả `null` hợp lệ, advice không tự biến thành chuỗi `"null"` |
| **Container kết quả** | `Optional<String> lookup()` | Giữ `Optional.empty()` là empty, không tự biến thành `null` hoặc một `Optional` khác |
| **Method không có giá trị** | `void ping()` | Target phải được gọi nếu không có requirement short-circuit; không cố ép một giá trị hữu hình cho caller |
| **Exception** | `String fail()` | Nếu target ném lỗi, advice quan sát không được âm thầm trả fallback thành công |
| **Generic contract** | `List<Order> findAll()` | Không trả `List` có element không tương thích dù kiểu raw `List` có vẻ hợp lệ |
| **Lazy/async return** | `CompletableFuture<Result>` hoặc reactive type | Không thay wrapper hoặc ngầm block/subscribe ngoài yêu cầu; completion xảy ra ngoài thời điểm method return |

Ví dụ caller có thể viết:

~~~java
String code = service.label("ada");
int quantity = service.quantity();
Optional<String> maybe = service.search(false);
~~~

Nếu advice bọc các method này nhưng đổi `String` thành `Integer`, trả `null` cho `int`, hoặc biến `Optional.empty()` thành `null`, code phía caller bị phá vỡ dù **business target vẫn chạy bình thường**.

**Giữ hợp đồng** không có nghĩa Spring buộc `@Around` chỉ được quan sát. Spring **cho phép** advice chủ động trả giá trị thay thế; việc đó cần là requirement được thiết kế, document và test, không phải side effect ngoài ý muốn của logging.

## 3. Đi qua chuỗi proxy: ai quyết định return value?

~~~text
Caller: String value = service.label("ada")
                         |
                         v
                 Spring AOP proxy
                         |
                         v
           @Around advice: before logic
                         |
                    pjp.proceed()
                         |
                         v
           Các interceptor phía trong (nếu có)
                         |
                         v
              Target.label("ada")
                         |
                         | return "ADA"
                         v
              interceptor chain
                         |
                         v
           @Around advice nhận Object "ADA"
                         |
                  return result
                         |
                         v
              Caller nhìn thấy "ADA"
~~~

Nếu advice viết:

~~~java
Object result = pjp.proceed();
return result;
~~~

thì nó tiếp tục chain, nhận object result (hoặc `null`), rồi trả lại cho proxy. Với target trả primitive `int`, giá trị trên đường đi của AOP interceptor được biểu diễn dưới dạng wrapper phù hợp, ví dụ `Integer`, trước khi proxy giao lại giá trị cho caller.

Nếu advice viết:

~~~java
pjp.proceed();
return null;
~~~

thì target **có thể vẫn chạy**, nhưng giá trị return từ target **đã bị advice vứt bỏ**. Caller nhìn thấy `null` (nếu return type là reference) hoặc gặp lỗi nếu method khai báo primitive. Đây là một bug rất khác với việc quên `proceed()`: trong trường hợp này side effect của target vẫn xảy ra, chỉ giá trị return bị mất.

Nếu advice viết:

~~~java
return "fixed-result";
~~~

mà **không gọi `proceed()`**, target có thể hoàn toàn không chạy. Điều này hợp lệ về khả năng kỹ thuật của `@Around` (ví dụ cache hit) nhưng làm thay đổi hợp đồng và side effects, nên chỉ đúng khi được thiết kế rõ.

## 4. Phân biệt @Before, @AfterReturning và @Around

Khi chỉ muốn **ghi nhận kết quả trả về** mà không thay đổi kết quả, dùng `@AfterReturning` thường an toàn và ít quyền can thiệp hơn `@Around`.

~~~java
@AfterReturning(
    pointcut = "execution(String demo.CatalogService.label(..))",
    returning = "result",
    argNames = "result"
)
public void observe(String result) {
    System.out.println("OBSERVED: " + result);
}
~~~

Advice này nhận return value khi target method **hoàn thành bình thường**. `@AfterReturning` **không thể trả một object reference hoàn toàn khác để thay return value** của caller. Nó không có `proceed()` và theo thông lệ khai báo `void`.

Có một ngoại lệ khái niệm cần hiểu: nếu object trả về **mutable**, Java code trong `@AfterReturning` vẫn có thể chỉnh sửa nội dung của chính object đó; điều này là một side effect mà caller có thể thấy. **Không thể thay reference** khác với **không thể mutate object**. Nếu yêu cầu chỉ quan sát, không sửa mutable return object.

`@Before` chỉ đủ khi cần xử lý **trước** method, không cần biết result. `@AfterThrowing` giúp quan sát exception mà target ném. `@After` (after-finally) dùng khi cần xử lý lúc hoàn thành kể cả success/error. **Chỉ chọn `@Around`** khi cần state đi xuyên trước/sau trong cùng invocation, đổi arguments/return, short-circuit hoặc kiểm soát chuỗi method execution theo yêu cầu.

Lưu ý: bản thân một advice loại đơn giản vẫn có thể ném exception khiến invocation bị fail; “ít quyền can thiệp” giúp giảm bề mặt lỗi, không thay thế việc thiết kế error policy cho logging/metrics.

## 5. Ví dụ Java 17+: một around advice giữ nguyên nhiều kiểu kết quả

Project Spring Framework thuần này dùng `@Around` chung cho các method của `CatalogService` nhưng **không thay đổi giá trị**. Nó kiểm chứng đầy đủ:

1. `String` trả bình thường;
2. `int` primitive;
3. `boolean` primitive;
4. `Optional<String>` có và không có giá trị;
5. `void` method;
6. Reference `null` hợp lệ;
7. Exception từ target truyền nguyên loại và message tới caller.

Chương trình có assertion tổng hợp và bộ đếm advice, không chỉ in chữ “PASS” theo mặc định.

Cấu trúc file:

~~~text
spring-aop-return-contract/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── App.java
    │   ├── CatalogService.java
    │   └── PreserveResultAspect.java
    └── test/java/demo/
        └── ReturnContractTest.java
~~~

Sử dụng Java 17+, Maven 3.9+, Spring Framework **6.2.0**, AspectJ Weaver **1.9.22** và JUnit Jupiter **5.11.0**. Phiên bản được khóa cho ví dụ, không khẳng định mới nhất. Không dùng Spring Boot hay AspectJ bytecode weaving.

### 5.1. Maven pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-return-contract</artifactId>
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

`spring-context` cung cấp `AnnotationConfigApplicationContext` và Java configuration. `spring-aop` chứa proxy/advisor support. `aspectjweaver` cung cấp các kiểu thư viện giúp Spring hiểu `@AspectJ` pointcut; chỉ thêm dependency này **không kích hoạt weaving**. `junit-jupiter`/Surefire dùng để chạy integration tests đơn giản trong cùng project.

### 5.2. Target với các kiểu return khác nhau

Tạo `src/main/java/demo/CatalogService.java`:

~~~java
package demo;

import java.util.Locale;
import java.util.Optional;

public class CatalogService {
    public String label(String input) {
        System.out.println("TARGET: label " + input);
        return input.toUpperCase(Locale.ROOT);
    }

    public int quantity() {
        System.out.println("TARGET: quantity");
        return 7;
    }

    public boolean enabled() {
        System.out.println("TARGET: enabled");
        return true;
    }

    public Optional<String> search(boolean exists) {
        System.out.println("TARGET: search " + exists);
        return exists ? Optional.of("found") : Optional.empty();
    }

    public void ping() {
        System.out.println("TARGET: ping");
    }

    public String nullable() {
        System.out.println("TARGET: nullable");
        return null;
    }

    public String fail() {
        System.out.println("TARGET: fail");
        throw new IllegalStateException("boom");
    }
}
~~~

Class này không `final`; các method đều `public` và không `final`, giúp CGLIB tạo class-based proxy và intercept. `search(true)` trả `Optional.of("found")`; `search(false)` trả `Optional.empty()`; đây là hai kết quả hợp lệ **khác `null`**. `nullable()` được phép trả `null` theo thiết kế minh họa; `quantity()` và `enabled()` là primitives nên **không thể có giá trị Java `null`**.

### 5.3. Aspect giữ giá trị và không nuốt exception

Tạo `src/main/java/demo/PreserveResultAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;

@Aspect
public class PreserveResultAspect {
    private final AtomicInteger calls = new AtomicInteger();

    @Around("execution(* demo.CatalogService.*(..))")
    public Object preserve(ProceedingJoinPoint point) throws Throwable {
        String method =
                ((MethodSignature) point.getSignature()).getName();

        System.out.println("AROUND: enter " + method);
        try {
            Object result = point.proceed();
            System.out.println("AROUND: return " + method);
            return result;
        } catch (Throwable error) {
            System.out.println(
                    "AROUND: throw " + method
                    + " " + error.getClass().getSimpleName());
            throw error;
        } finally {
            calls.incrementAndGet();
        }
    }

    public int calls() {
        return calls.get();
    }
}
~~~

Điểm thiết kế:

- `@Aspect` chỉ nhận diện class chứa advice; Spring vẫn cần đăng ký nó làm **bean**.
- `@Around` có **kiểu trả về `Object`** và `throws Throwable` như API `ProceedingJoinPoint.proceed()`.
- `Object result = point.proceed(); return result;` giữ nguyên reference/kết quả mà inner interceptor chain trả về, không ép kiểu thủ công sang `String` hay wrapper cụ thể.
- Với `int` và `boolean`, Spring AOP xử lý boxing/unboxing ở ranh giới interceptor/proxy; advice chỉ cần trả đúng object nhận được. **Không** tự trả `null` hay chuỗi `"7"` thay `Integer`.
- Với `void`, return từ `proceed()` có thể là `null` ở tầng interceptor; `return result;` vẫn là cách giữ semantics của void method. Không biến method advice thành `void`.
- Với `Optional.empty()` hoặc `null` từ target, reference/result được chuyển tiếp như đang có, không “chuẩn hóa” ngoài yêu cầu.
- Khối `catch(Throwable error)` ở đây chỉ **in marker và `throw error` ngay**; nó không làm mất loại exception gốc. Nếu không cần log loại lỗi, có thể bỏ catch và giữ `try/finally`.
- `finally` tăng `calls` kể cả khi target ném exception. Counter này đo **số lần advice được gọi**, không phải số success.
- Pointcut chọn các method trên `CatalogService`, ví dụ cố tình gọi mỗi method qua Spring bean proxy. Không thử bắt constructors, field access hay object `new` bên ngoài container.

Nếu logger có thể ném exception (ví dụ lỗi serialize/log sink), production cần error policy để logging không vô tình đổi business outcome; code in `System.out` chỉ phù hợp ví dụ tối thiểu.

### 5.4. Spring configuration và main method

Tạo `src/main/java/demo/App.java`:

~~~java
package demo;

import java.util.Optional;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    @Bean
    public PreserveResultAspect preserveResultAspect() {
        return new PreserveResultAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            CatalogService service = context.getBean(CatalogService.class);
            PreserveResultAspect aspect =
                    context.getBean(PreserveResultAspect.class);

            boolean proxy = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxy);

            String label = service.label("ada");
            System.out.println("CALLER_LABEL: " + label);

            int quantity = service.quantity();
            System.out.println("CALLER_QUANTITY: " + quantity);

            boolean enabled = service.enabled();
            System.out.println("CALLER_ENABLED: " + enabled);

            Optional<String> present = service.search(true);
            System.out.println("CALLER_PRESENT: " + present);

            Optional<String> absent = service.search(false);
            System.out.println("CALLER_ABSENT: " + absent);

            service.ping();
            System.out.println("CALLER_PING: complete");

            String nullable = service.nullable();
            System.out.println("CALLER_NULL: " + (nullable == null));

            boolean caught = false;
            try {
                service.fail();
            } catch (IllegalStateException error) {
                caught = "boom".equals(error.getMessage());
                System.out.println("CALLER_EXCEPTION: " + error.getMessage());
            }

            int count = aspect.calls();
            System.out.println("ADVICE_COUNT: " + count);

            if (!proxy
                    || !"ADA".equals(label)
                    || quantity != 7
                    || !enabled
                    || !Optional.of("found").equals(present)
                    || !Optional.empty().equals(absent)
                    || nullable != null
                    || !caught
                    || count != 8) {
                throw new IllegalStateException(
                        "Return contract was not preserved");
            }

            System.out.println("CHECK: PASS");
        }
    }
}
~~~

Tại sao đây là phép thử thực sự của Spring AOP?

1. `@EnableAspectJAutoProxy(proxyTargetClass = true)` bật auto-proxy creator và class-based proxy cho bean phù hợp. `CatalogService` không cần interface trong ví dụ.
2. `@Bean catalogService()` trả instance cho Spring quản lý; caller sử dụng bean từ `ApplicationContext` thay vì gọi `new CatalogService()` ở ngoài.
3. `@Bean preserveResultAspect()` đăng ký aspect trong cùng context, để Spring nhận advisor `@Around`.
4. `AopUtils.isAopProxy(service)` xác nhận bean reference thực sự là AOP proxy, không chỉ là target được gọi trực tiếp.
5. Tám lần gọi qua proxy: `label`, `quantity`, `enabled`, `search(true)`, `search(false)`, `ping`, `nullable`, `fail`. Do đó `ADVICE_COUNT` dự kiến bằng **8**, kể cả lần `fail` kết thúc bằng exception.
6. Caller nhận **các kiểu và giá trị đúng**: `String`, `int`, `boolean`, `Optional` có/không có giá trị, `void`, `null` reference và `IllegalStateException`.
7. Condition cuối kiểm tra cả proxy, các giá trị, kiểu quan sát qua Java assignment và exception, rồi mới in `CHECK: PASS`. Nếu `@Around` lỡ trả `null` từ `quantity`, chương trình sẽ không vượt qua được lệnh Java assignment vào `int`.

### 5.5. Chạy Maven và đối chiếu stdout

Chạy trong thư mục có `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng `System.out.println` của ứng dụng, theo thứ tự:

~~~text
PROXY: true
AROUND: enter label
TARGET: label ada
AROUND: return label
CALLER_LABEL: ADA
AROUND: enter quantity
TARGET: quantity
AROUND: return quantity
CALLER_QUANTITY: 7
AROUND: enter enabled
TARGET: enabled
AROUND: return enabled
CALLER_ENABLED: true
AROUND: enter search
TARGET: search true
AROUND: return search
CALLER_PRESENT: Optional[found]
AROUND: enter search
TARGET: search false
AROUND: return search
CALLER_ABSENT: Optional.empty
AROUND: enter ping
TARGET: ping
AROUND: return ping
CALLER_PING: complete
AROUND: enter nullable
TARGET: nullable
AROUND: return nullable
CALLER_NULL: true
AROUND: enter fail
TARGET: fail
AROUND: throw fail IllegalStateException
CALLER_EXCEPTION: boom
ADVICE_COUNT: 8
CHECK: PASS
~~~

Đây là **stdout mong đợi theo source**, không phải claim đã thực thi Maven trên máy của người học. Maven/SLF4J có thể sinh dòng khác. `CHECK: PASS` chỉ xảy ra khi mọi điều kiện trong code được thỏa mãn.

### 5.6. Integration tests bằng JUnit Jupiter

Tạo `src/test/java/demo/ReturnContractTest.java`:

~~~java
package demo;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReturnContractTest {
    @Test
    void preservesReferencePrimitivesVoidOptionalNullAndException() {
        try (var context =
                new AnnotationConfigApplicationContext(App.class)) {
            CatalogService service = context.getBean(CatalogService.class);
            PreserveResultAspect aspect =
                    context.getBean(PreserveResultAspect.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals("ADA", service.label("ada"));
            assertEquals(7, service.quantity());
            assertTrue(service.enabled());
            assertEquals(Optional.of("found"), service.search(true));
            assertEquals(Optional.empty(), service.search(false));

            service.ping();
            assertNull(service.nullable());

            IllegalStateException error = assertThrows(
                    IllegalStateException.class, service::fail);
            assertEquals("boom", error.getMessage());

            assertEquals(8, aspect.calls());
        }
    }

    @Test
    void plainObjectOutsideSpringIsNotAutoProxied() {
        CatalogService raw = new CatalogService();
        assertFalse(AopUtils.isAopProxy(raw));
        assertEquals("ADA", raw.label("ada"));
    }
}
~~~

Lệnh chạy:

~~~bash
mvn clean test
~~~

Kết quả mong đợi trong báo cáo Surefire nếu chạy thành công:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
~~~

JUnit kiểm tra trực tiếp **contract quan sát bởi caller**. Chỉ thấy bean là proxy hoặc advice có log chưa đủ: một advice có thể chạy nhưng vô tình trả giá trị sai. Mỗi assert tương ứng một nhóm return behavior, gồm cả thrown exit.

## 6. Lỗi nghiêm trọng: @Around khai báo void làm mất return value

Ví dụ **sai** cho một method `String`:

~~~java
@Around("execution(String demo.CatalogService.label(..))")
public void wrong(ProceedingJoinPoint point) throws Throwable {
    point.proceed();
}
~~~

Method advice trả `void` khiến Spring dùng `null` làm result của advice; caller của `String label(...)` có thể nhận `null` dù target đã trả `"ADA"`. Nếu pointcut dùng để bọc method primitive `int quantity()`, `null` không thể trả như một `int`: Spring AOP có thể ném `AopInvocationException` do null không tương thích primitive return type.

**Sửa đúng:**

~~~java
@Around("execution(String demo.CatalogService.label(..))")
public Object correct(ProceedingJoinPoint point) throws Throwable {
    return point.proceed();
}
~~~

Hai đoạn này là những **phương án minh họa riêng**, không nên thêm vào project chạy ở phần 5 vốn đã có một `@Around` trên `CatalogService`. Tránh để advice sai hoạt động cùng advice đúng khi muốn kiểm tra output chuẩn.

Theo Spring docs, `@Around` nên khai báo **`Object`** làm return type kể cả khi target method `void`. Với `void` target, `return point.proceed()` vẫn là idiom giữ nguyên chain; không cần đặc biệt viết `return null` nếu không có yêu cầu thay behavior.

## 7. Lỗi khi bỏ return, thay sai reference hoặc sai kiểu

### 7.1. Target chạy nhưng result bị vứt đi

~~~java
@Around("execution(* demo.CatalogService.label(..))")
public Object broken(ProceedingJoinPoint point) throws Throwable {
    point.proceed();  // Target vẫn có thể đã chạy.
    return null;      // Nhưng kết quả từ target đã bị bỏ.
}
~~~

Đối với method trả `String`, caller có thể nhận `null` mà không thấy exception tại advice. Với primitive, proxy không thể đưa `null` trở lại như `int` hoặc `boolean`. Cách sửa: **`return point.proceed();`**.

### 7.2. Thay reference khác dù không được yêu cầu

~~~java
@Around("execution(* demo.CatalogService.label(..))")
public Object replaces(ProceedingJoinPoint point) throws Throwable {
    point.proceed();
    return "FORCED";
}
~~~

Dù kiểu `String` hợp lệ, giá trị `"FORCED"` không còn là kết quả của target. Nếu nghiệp vụ không yêu cầu transform, đây là bug semantics. Nếu ứng dụng chủ động cần cache/fallback/masking ở boundary, thay return value có thể hợp lệ, nhưng phải document và kiểm thử tương thích hợp đồng.

### 7.3. Sai kiểu object

~~~java
@Around("execution(* demo.CatalogService.label(..))")
public Object wrongType(ProceedingJoinPoint point) throws Throwable {
    point.proceed();
    return Integer.valueOf(42);
}
~~~

Target khai báo `String label(...)` mà advice trả `Integer`. `@Around` trả `Object` không làm method interface/concrete class của caller được phép trả bất kỳ kiểu nào. Ở ranh giới proxy/caller, có thể xuất hiện `ClassCastException` hoặc lỗi chuyển kiểu/invocation tương ứng. Đừng dựa vào exact exception message giữa JDK/CGLIB/configurations; **hành vi trả sai type là không hợp lệ**.

### 7.4. Trả null cho primitive

~~~java
@Around("execution(int demo.CatalogService.quantity())")
public Object nullPrimitive(ProceedingJoinPoint point) throws Throwable {
    point.proceed();
    return null;
}
~~~

Không có giá trị Java `null` của primitive `int`. Với Spring AOP, null result không tương thích primitive có thể được framework báo bằng `AopInvocationException`; tùy proxy/chain còn có thể có exception wrapper. Đừng dùng kiểu này như một cách “trả default”. Nếu requirement cho fallback 0, nó phải là chính sách được quyết định rõ, không tự phát từ logging.

### 7.5. Optional: không biến empty thành null

~~~java
@Around("execution(* demo.CatalogService.search(..))")
public Object badOptional(ProceedingJoinPoint point) throws Throwable {
    Object result = point.proceed();
    return result == null ? null : Optional.empty();
}
~~~

Sai với `search(true)`: dù target trả `Optional.of("found")`, advice thay thành empty. Sai với `search(false)` nếu downstream cần phân biệt một Optional container hợp lệ với việc method trả null. Nếu contract khai báo `Optional<T>` và quy ước không-null, **giữ nguyên `Optional` object** khi chỉ quan sát. Chỉ transform khi có requirement rõ.

Mọi đoạn trong phần 7 là **các mẫu sai độc lập**, không phải code để thêm vào project chuẩn. Trong code review, nên đặc biệt tìm pattern `proceed(); return null;` hoặc catch rồi return default không được mô tả bằng API contract.

## 8. Exception cũng là một phần của hợp đồng quan sát bởi caller

### 8.1. Truyền nguyên ngoại lệ khi chỉ cần log

~~~java
@Around("execution(* demo.CatalogService.fail(..))")
public Object traceFailure(ProceedingJoinPoint point)
        throws Throwable {
    try {
        return point.proceed();
    } catch (Throwable error) {
        System.out.println("Error: " + error.getClass().getSimpleName());
        throw error;
    }
}
~~~

Advice phải **rethrow đúng object `error`** nếu không có chủ đích translate exceptions. Khi target ném `IllegalStateException("boom")`, caller vẫn quan sát exception đó. Thêm `throws Throwable` cho advice method phù hợp với `ProceedingJoinPoint.proceed()`.

### 8.2. Nuốt exception làm đổi thrown exit thành normal return

~~~java
@Around("execution(* demo.CatalogService.fail(..))")
public Object hidesFailure(ProceedingJoinPoint point)
        throws Throwable {
    try {
        return point.proceed();
    } catch (Throwable error) {
        return null;
    }
}
~~~

Đây là một **thay đổi hợp đồng rất lớn**: thay vì để caller xử lý thất bại, advice trả `null` như một normal return. Với method trả `String`, code phía caller có thể không biết target đã thất bại. Với primitive return, null lại không hợp kiểu.

Nếu mục tiêu business thật sự là fallback/recovery, hãy định nghĩa exception classes được xử lý, fallback có kiểu hợp lệ, tác động với transaction/cache và logging/audit, rồi viết integration tests. Trong nhiều trường hợp, error handling thuộc **service boundary** hoặc circuit breaker/retry integration chuyên dụng hơn là một around advice tùy tiện.

### 8.3. Finally để cleanup mà không thay kết quả

~~~java
@Around("execution(* demo..service..*.*(..))")
public Object measure(ProceedingJoinPoint point)
        throws Throwable {
    long start = System.nanoTime();
    try {
        return point.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - start;
        // Ghi metric; không ném exception khác từ cleanup.
    }
}
~~~

Mẫu này duy trì normal return hoặc exception từ `proceed()` vì có `return` ở `try` và `finally` không thay kết quả. `System.nanoTime()` chỉ đo elapsed duration, không phải wall-clock timestamp. Trong production, cần bảo vệ việc ghi metric khỏi failure nếu metric failure không được phép ảnh hưởng business.

Một câu `return` trong `finally` hoặc exception ném ra trong `finally` có thể **ghi đè outcome** của `try`. Tránh pattern đó với các around advices chỉ quan sát.

## 9. Primitive, reference, void, generic và async: checklist type safety

### Primitive và boxing

Trong Java, `int quantity()` và `boolean enabled()` không thể trả `null`. Tại interceptor boundary, result có thể được đóng gói thành `Integer`/`Boolean`. Trả `String "7"` thay cho `Integer.valueOf(7)` không phải một phép đổi type được proxy tự động bảo đảm. Nếu không chủ đích transform, **return nguyên object** từ `proceed()`.

### Reference có thể null

Method `String nullable()` được thiết kế cho phép `null` thì `@Around` quan sát nên giữ `null`. Không coi “không có giá trị” là lỗi AOP tự thân. Nếu API contract cấm `null`, sửa tại service/validation layer hoặc định nghĩa policy explicit; logging aspect không nên tự đặt default.

### Method void

Method `void ping()` không cho caller nhận value. Trong Spring AOP, around advice `Object preserve(...)` vẫn trả kết quả của `proceed()` để giữ chain nhất quán. Không khai báo advice `void` chỉ vì nó có thể match `void` method; cùng aspect có thể match các methods trả giá trị khác.

### Optional

`Optional.empty()` là một object hợp lệ, **không đồng nghĩa `null`**. Giữ `Optional<T>` result khi chỉ quan sát. Trả `Optional.empty()` tùy ý thay `Optional.of(...)` có thể làm caller nghĩ dữ liệu không tồn tại.

### Generics

Giả sử một Spring service khai báo `List<Order> findAll()`. Runtime type erasure có thể khiến proxy chỉ kiểm tra raw `List`; trả một `List<String>` từ `@Around` có thể không báo lỗi ngay, nhưng code caller khi đọc phần tử như `Order` sẽ lỗi. Kiểm thử cả **element contract**, không chỉ `result instanceof List`.

### Async / Future / reactive

Với `CompletableFuture<Result> fetchAsync()`, “return contract” gồm cả **wrapper** và hành vi complete/exceptionally complete trong tương lai. Một advice trả `Result` trực tiếp thay vì `CompletableFuture<Result>` là sai kiểu; chặn `join()`/`get()` không có requirement có thể làm block thread và thay exception/timing. Với Reactor `Mono<T>`/`Flux<T>`, subscription và signals nằm ngoài thời điểm method return; nếu cần quan sát **outcome bất đồng bộ** phải chọn integration/callback phù hợp, không giả định log sau `proceed()` nghĩa là pipeline đã kết thúc.

## 10. Khi nhiều aspects cùng tham gia interceptor chain

Một `@Around` có thể bao ngoài các advice khác như transaction/cache/security; khi gọi `pjp.proceed()`, nó chuyển xuống **phần còn lại của interceptor chain**, không nhất thiết gọi target trực tiếp ngay lập tức.

~~~text
Caller
  |
  v
Outer audit @Around
  | proceed()
  v
Inner transaction/cache advisor
  | proceed() hoặc short-circuit theo semantics của nó
  v
Target method (khi được gọi)
  |
  v
Inner advisor trả result / ném exception
  |
  v
Outer @Around nhận result / exception
  |
  v
Caller
~~~

Vì vậy, **giữ hợp đồng** nghĩa là bảo toàn result/exception do inner chain thực sự trả, không chỉ giả định value đến trực tiếp từ target.

Một cache advisor có thể chủ động trả cache hit mà không chạy target. Nếu outer audit aspect trả nguyên `pjp.proceed()` result, nó không phá cache behavior. Nếu outer aspect ép result thành một type không hợp lệ, hoặc tự gọi target reflection để bypass interceptor chain, nó có thể phá cache, transaction và security policies.

Nếu dùng `@Order` để quyết định outer/inner precedence, giá trị **nhỏ hơn** thường có precedence cao hơn: advice ngoài đi vào trước và hoàn thành sau khi inner chain trả. Đừng dựa vào vị trí khai báo code để suy ordering giữa các aspects. Test trên đúng Spring context khi outcome phụ thuộc thứ tự.

## 11. Cách thiết kế một around advice an toàn

Một skeleton có mục đích rõ ràng:

~~~java
@Aspect
public class TimingAspect {
    @Around("execution(* demo..service..*.*(..))")
    public Object measure(ProceedingJoinPoint point) throws Throwable {
        long started = System.nanoTime();
        try {
            return point.proceed();
        } finally {
            long elapsedNanos = System.nanoTime() - started;
            // Metrics sink phải có failure policy rõ ràng.
        }
    }
}
~~~

Đây là **snippet minh họa**; cần import `@Aspect`, `@Around`, `ProceedingJoinPoint`, đăng ký aspect Spring bean và dùng package pointcut thực tế. Nếu code chỉ muốn log **trước** method, `@Before` đơn giản hơn. Nếu chỉ muốn log **result thành công**, `@AfterReturning` thường đúng quyền can thiệp hơn. Dùng `@Around` khi phải giữ local state trước/sau invocation hoặc can thiệp luồng thực thi với mục tiêu rõ ràng.

Một code review tốt nên hỏi:

1. Advice có thật sự cần `@Around` hay `@Before`/`@AfterReturning` đáp ứng đủ?
2. Mỗi nhánh success có `return` đúng giá trị `proceed()` trả không?
3. Mỗi nhánh failure có giữ nguyên exception theo contract không?
4. Có `return null`/default vô tình nào không? Nếu có, target return type là reference hay primitive?
5. Method có `Optional`, generic collections, async wrapper hoặc nullable contract không?
6. `proceed()` có đúng số lần cần thiết? Retry có thể gây side effects?
7. Có self-invocation, target raw, method `final` hoặc pointcut không match làm advice không chạy?
8. Log/metrics code có thể ném lỗi khiến outcome thay đổi không?
9. Nếu muốn transform có chủ ý, có test caller-facing result và exception tương ứng không?
10. Nếu nhiều advisors cùng match, đã xác minh thứ tự và transaction/cache semantics thực tế chưa?

## 12. Bài tập kiểm tra các tình huống sai

### Bài 1: quên return

Mẫu:

~~~java
Object result = point.proceed();
return null;
~~~

Với `String label()`, caller có thể nhận null. Sửa thành `return result;`. Với `int quantity()`, null không tương thích primitive; không dùng ví dụ sai đó trong production.

### Bài 2: ép mọi kết quả về String

Mẫu:

~~~java
Object result = point.proceed();
return String.valueOf(result);
~~~

Nếu aspect match `int`, `boolean` hoặc `Optional`, method công bố return type không khớp với `String`. Nếu aspect chỉ cần log, hãy log `String.valueOf(result)` vào logger rồi **`return result;`**.

### Bài 3: fallback “im lặng”

Mẫu:

~~~java
try {
    return point.proceed();
} catch (Throwable error) {
    return "";
}
~~~

Với method ném lỗi và contract yêu cầu caller được thấy exception, đây là bug. Với method primitive/Optional, chuỗi `""` còn sai type. Nếu fallback có mục đích, phải match method cụ thể, xác định loại exception được handle và đúng return type, document behavior và test.

### Bài 4: method void

Method `void ping()` không đòi hỏi caller nhận giá trị. Trong một `@Around Object` chung cho nhiều methods, vẫn dùng:

~~~java
return point.proceed();
~~~

Không đổi advice thành `void` chỉ vì một method mục tiêu trả `void`. Spring docs khuyến nghị `Object` return type để không vứt bỏ return value của các method trả value.

### Bài 5: Optional

Nếu `search(false)` trả `Optional.empty()`, lời gọi advice nên giữ object result đó. Khi thấy `Optional.empty()` không có nghĩa target trả `null`. Trả `null` từ aspect có thể khiến caller `search(false).isPresent()` ném `NullPointerException`.

### Bài 6: exception

Trong `@Around` chỉ logging:

~~~java
try {
    return point.proceed();
} catch (Throwable error) {
    logException(error);
    throw error;
}
~~~

`logException` là helper **giả định** có error policy riêng, không phải method đã được định nghĩa trong project chạy phần 5. Không để helper ném một exception khác nếu yêu cầu là giữ nguyên exception gốc.

## 13. Gỡ lỗi khi caller nhận sai kết quả dù target đúng

1. **Đo proxy**: dùng `AopUtils.isAopProxy(service)` trên reference thực sự đang được gọi. Nếu false, không nên quy kết ngay cho around advice.
2. **Xem pointcut**: method trả kết quả sai có thực sự match `@Around` này không? Có aspect khác nằm trong chain không?
3. **Kiểm tra advice signature**: `@Around` có khai báo return `Object`, tham số `ProceedingJoinPoint` đầu tiên và `throws Throwable` không?
4. **Kiểm tra đường success**: có gọi `proceed()` đúng một lần và `return` chính result không, hay chỉ gọi rồi bỏ?
5. **Kiểm tra đường failure**: có catch và return default/`null` vô tình không? Có `finally` ném lỗi khác không?
6. **So return type**: dùng `MethodSignature.getReturnType()` để xác định method khai báo `String`, `int`, `void`...; đối chiếu object result hoặc fallback.
7. **Đặc biệt với primitive**: `null` không thể giao cho `int`/`boolean`, kiểm tra lỗi `AopInvocationException`/wrapper tương ứng.
8. **Với generics**: kiểm tra cả element types và behavior caller sử dụng, không chỉ raw class.
9. **Với Optional/async**: phân biệt `Optional.empty()`/`null` và object wrapper/result hoàn tất sau này.
10. **Xác minh nhiều advisors**: transaction/cache/security có thể thay đổi cách tạo result/exception; đọc precedence/order thực tế.
11. **Không thay target bằng reflection trực tiếp**: gọi `method.invoke(target, ...)` không tương đương `ProceedingJoinPoint.proceed()` và có thể bypass inner AOP advisors.
12. **Viết integration tests**: assert caller-facing results của các method representative, exception propagation và số lần advice chạy, không chỉ xem Spring bean có AOP proxy.

### Mẫu đo return type bên trong advice

~~~java
MethodSignature signature =
        (MethodSignature) point.getSignature();
Class<?> declaredReturn = signature.getReturnType();
System.out.println("Declared: " + declaredReturn.getTypeName());

Object result = point.proceed();
System.out.println("Is null: " + (result == null));
return result;
~~~

Đây là snippet trong `@Around` đã có biến `point` và import `MethodSignature`; không phải file chạy độc lập. Tránh log nội dung result nếu nó có dữ liệu nhạy cảm hoặc có `toString()` gây side effects. Chỉ đọc metadata khi cần và không parse chuỗi class name của generated proxy.

## 14. Checklist trước khi merge một Spring @Around advice

- [ ] Business requirement nêu rõ đây là **quan sát** hay **chủ động transform/short-circuit**.
- [ ] Nếu chỉ cần xử lý trước, dùng `@Before`; nếu chỉ đọc successful result, cân nhắc `@AfterReturning`.
- [ ] `@Around` khai báo `Object` và tham số đầu `ProceedingJoinPoint`.
- [ ] Mọi nhánh success bình thường trả **đúng result** của `proceed()` khi không có policy thay thế.
- [ ] `proceed()` được gọi đúng số lần; không skip/retry trái yêu cầu.
- [ ] Thrown exit propagate exception gốc nếu chỉ logging/tracing.
- [ ] Không có `return` trong `finally` và logging/metrics không vô ý làm đổi outcome.
- [ ] Đã test reference type, primitive, void, nullable, Optional và exception đại diện.
- [ ] Fallback nếu có phải đúng declared return type/nullability, được document và kiểm thử.
- [ ] Aspect và target là Spring-managed beans; caller dùng proxy, tránh self-invocation.
- [ ] Có integration test caller-facing, không chỉ đếm số lần advice.
- [ ] Nếu chain có transaction/cache/security, ordering và tương tác return/exception đã được xem xét.
- [ ] Không đưa dữ liệu nhạy cảm vào log chỉ vì advice được phép đọc `getArgs()` hoặc result.

## 15. Tài liệu Spring Framework chính thức

- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `Object` return type, `proceed()`, ý nghĩa return value nhìn từ caller, lưu ý `@Around void` và `@AfterReturning` không thay reference.
- [Spring Framework 6.2 — Advice API](https://docs.spring.io/spring-framework/reference/6.2/core/aop-api/advice.html): `MethodInterceptor.invoke` trả giá trị của invocation, `AfterReturningAdvice` chỉ quan sát value và exception từ advice.
- [Spring Framework 6.2 — AOP Concepts](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html): `@Around` là loại advice mạnh, nên chọn advice ít quyền nhất đáp ứng yêu cầu.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): proxy boundary, JDK/CGLIB, self-invocation.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): đăng ký @Aspect Spring bean và kích hoạt auto-proxying.
