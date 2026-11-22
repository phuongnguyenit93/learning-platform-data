# Phương thức kế thừa, interface mặc định và vị trí đặt annotation trong Spring AOP

## 1. Mục tiêu và phạm vi

Khi làm việc với Spring AOP, một lời gọi phương thức có thể đi qua **JDK dynamic proxy** hoặc **CGLIB class-based proxy**. Phương thức đó có thể được khai báo trực tiếp trên lớp đích, **kế thừa từ superclass**, hoặc được cung cấp dưới dạng **default method của interface**. Đồng thời, annotation dùng để định nghĩa advice hoặc kích hoạt cơ chế Spring có thể nằm trên interface, implementation, superclass hay method.

Bốn câu hỏi cần tách riêng:

1. **Client có gọi qua Spring proxy không?** Không có đường vào proxy thì Spring AOP không tự chặn lời gọi chỉ vì method có annotation.
2. **Phương thức có nằm trong API mà proxy intercept được không?** Với JDK proxy, cần lời gọi public method được công bố trên interface; với CGLIB, cần method mà subclass proxy có thể override.
3. **Pointcut có khớp execution thực tế không?** Kiểm tra kiểu khai báo method, lớp target, chữ ký, annotation và biểu thức Spring AOP.
4. **Framework lấy annotation ở đâu?** Java reflection, Spring merged-annotation utilities, `@annotation` pointcut và các module như transaction đều có những quy tắc tra cứu metadata không hoàn toàn giống nhau.

Bài này chỉ phân tích các tình huống trên trong **Spring Framework/Spring AOP proxy-based interception**. Những lý thuyết Aspect chung hoặc AspectJ compile-time/load-time weaving không phải trọng tâm.

## 2. Nhận diện ba nguồn gốc phương thức

Ví dụ một interface với default method và một lớp triển khai kế thừa method từ superclass:

```java
public interface CustomerApi {
    String inherited(String id);

    default String fromDefault(String id) {
        return "DEFAULT:" + id;
    }

    String explicit(String id);
}

public class BaseCustomerService {
    public String inherited(String id) {
        return "BASE:" + id;
    }
}

public class CustomerService
        extends BaseCustomerService implements CustomerApi {

    @Override
    public String explicit(String id) {
        return "IMPL:" + id;
    }
}
```

Đây là **ba loại method khác nhau trong cùng một đối tượng đích**:

| Method | Nơi cung cấp code | Vì sao gọi được từ client? |
| --- | --- | --- |
| `inherited(String)` | `BaseCustomerService` (superclass) | `CustomerService` kế thừa method public và thỏa `CustomerApi` |
| `fromDefault(String)` | `CustomerApi` (interface default method) | Interface cung cấp implementation mặc định, class chưa override |
| `explicit(String)` | `CustomerService` | Implementation khai báo/override trực tiếp |

**Vị trí khai báo code không quyết định duy nhất việc có advice.** Spring AOP cần chặn được lời gọi **đi qua proxy** và xác định advisor phù hợp với method. Phương thức kế thừa hoặc default method không tự nằm ngoài AOP chỉ vì code không viết trực tiếp trong class cuối cùng.

Trong Java reflection, có thể quan sát nguồn gốc:

```java
Method m1 = CustomerService.class.getMethod("inherited", String.class);
System.out.println(m1.getDeclaringClass().getSimpleName());
// BaseCustomerService

Method m2 = CustomerApi.class.getMethod("fromDefault", String.class);
System.out.println(m2.isDefault());
// true
```

Đây là các **đoạn minh họa**, cần import `java.lang.reflect.Method` và định nghĩa các kiểu như trên. `getDeclaringClass()` phản ánh class/interface khai báo method được tìm thấy; nó **không trả lời** Spring có tạo proxy hay pointcut đã khớp chưa.

## 3. Với phương thức kế thừa, JDK và CGLIB khác nhau như thế nào?

### 3.1. JDK dynamic proxy

JDK proxy không kế thừa `CustomerService`. Nó triển khai những interface Spring công bố, ví dụ `CustomerApi`. Vì `CustomerApi` có method `inherited(String)`, client có thể gọi nó qua proxy:

```text
Client (CustomerApi)
        |
        v
JDK proxy.inherited("A")
        |
        v
Spring AOP advice / interceptor
        |
        v
CustomerService target
        |
        v
BaseCustomerService.inherited("A")
```

Trong trường hợp này, **implementation nằm ở superclass** nhưng lời gọi bên ngoài vẫn có thể được Spring AOP intercept do method **được khai báo trên interface proxy**.

Nếu superclass có method public `onlyInBase()` nhưng `CustomerApi` **không công bố** method đó, client giữ JDK proxy không thể gọi `onlyInBase()` bằng cách ép JDK proxy sang `CustomerService`. Lời gọi không phải một API được JDK proxy expose; đặt advice trên method không tạo thêm method vào proxy interface.

### 3.2. CGLIB class-based proxy

Với `@EnableAspectJAutoProxy(proxyTargetClass = true)`, Spring có thể tạo proxy bằng subclass của `CustomerService`. Subclass proxy có thể intercept các method đủ điều kiện override, gồm method public **được kế thừa từ superclass**, miễn method/visibility và pointcut phù hợp.

```text
Client (CustomerService)
        |
        v
CGLIB proxy extends CustomerService
        |
        v
Spring AOP advice / interceptor
        |
        v
Target CustomerService
        |
        v
BaseCustomerService.inherited("A")
```

Một method kế thừa bị đánh dấu `final` thì CGLIB **không thể override** để đặt interceptor, bất kể method đó có annotation hay pointcut khớp. Tương tự, `private` method không được kế thừa/override; `final class` không thể làm superclass của CGLIB proxy.

**Kết luận cho method kế thừa:** kiểm tra **API proxy và overrideability**, sau đó kiểm tra **pointcut**. Không dùng câu “method không được override ở implementation nên Spring AOP bỏ qua” làm quy tắc tổng quát.

## 4. Default method của interface dưới góc nhìn Spring AOP

Java interface có thể khai báo:

```java
public interface CustomerApi {
    default String fromDefault(String id) {
        return "DEFAULT:" + id;
    }
}
```

Default method là method **có implementation do interface cung cấp**. Nó khác abstract interface method, nhưng vẫn là method public trong contract của interface.

Với Spring AOP:

- **JDK proxy:** default method thuộc interface được proxy công bố. Một lời gọi từ client qua proxy là lời gọi có thể đi vào invocation handler/AOP chain; Spring sau đó tiếp tục thực thi implementation mặc định trên target nếu không bị advice short-circuit.
- **CGLIB proxy:** proxy là subclass của target. Interface default method có thể xuất hiện như một method kế thừa từ interface; khả năng intercept cụ thể vẫn phụ thuộc điều kiện proxy, target, signature và Spring version. Nếu kết quả quan trọng, phải kiểm tra trong một test context với proxy strategy đã chọn.
- **Không phải do `default` mà tự động có advice:** nếu pointcut không match, lời gọi vẫn chạy bình thường, không có business advice được áp dụng.
- **Default method có thể gọi method khác:** lời gọi phát sinh **sau khi đã chuyển execution vào target** không được tự coi là một lời gọi mới qua Spring proxy. Nếu cần interceptor cho lời gọi thứ hai, tách sang một Spring bean khác để client/collaborator gọi qua proxy.

Đặc biệt, **Spring AOP không áp advice lên việc khai báo interface**. Nó hoạt động ở *method execution* có lời gọi đi qua Spring proxy. Vị trí implementation ở interface không biến `@AspectJ` pointcut thành weaving lên bytecode interface.

### Default method được override thì sao?

```java
interface CustomerApi {
    default String fromDefault(String id) {
        return "DEFAULT:" + id;
    }
}

class CustomerService implements CustomerApi {
    @Override
    public String fromDefault(String id) {
        return "OVERRIDE:" + id;
    }
}
```

Trong đoạn minh họa này, implementation thực thi là `CustomerService.fromDefault(...)`. Không được suy rằng annotation hoặc logic ở interface default method vẫn có hiệu lực giống hệt trong mọi Spring feature; cách đọc annotation tùy matcher/metadata source. Kiểm tra implementation thực tế, proxy method và annotation lookup của tính năng đang dùng.

## 5. Ví dụ Java 17+ chạy được: kế thừa, default method và annotation

Thí nghiệm sử dụng **Spring Framework 6.2.19, Java 17+, Maven**. Nó tạo **JDK dynamic proxy** để giữ đường gọi qua interface thật rõ ràng và không phải dựa vào tên lớp proxy được sinh.

Ba method được gọi từ client:

1. `inherited()`: implementation nằm ở superclass, nhưng interface công bố chữ ký.
2. `fromDefault()`: implementation mặc định nằm ở interface.
3. `marked()`: implementation class trực tiếp override và có custom annotation `@TraceCall`.

Aspect dùng pointcut theo **tên method execution** để dễ thấy cả ba lời gọi đều đi qua proxy; phần sau kiểm tra **vị trí annotation bằng Java reflection**. Cách tách này tránh nhầm rằng pointcut bằng tên và pointcut `@annotation` có cùng thuật toán match metadata.

### 5.1. Cấu trúc dự án

```text
spring-aop-method-boundaries/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MethodBoundaryDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-method-boundaries</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
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
                    <mainClass>demo.MethodBoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/MethodBoundaryDemo.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class MethodBoundaryDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface TraceCall {
    }

    public interface CustomerApi {
        String inherited(String id);

        default String fromDefault(String id) {
            System.out.println("TARGET default " + id);
            return "DEFAULT:" + id;
        }

        String marked(String id);
    }

    public static class BaseService {
        public String inherited(String id) {
            System.out.println("TARGET inherited " + id);
            return "BASE:" + id;
        }
    }

    public static class CustomerService
            extends BaseService implements CustomerApi {

        @Override
        @TraceCall
        public String marked(String id) {
            System.out.println("TARGET marked " + id);
            return "MARKED:" + id;
        }
    }

    @Aspect
    public static class TraceAspect {
        @Before(
            "execution(* demo..*.inherited(..)) || " +
            "execution(* demo..*.fromDefault(..)) || " +
            "execution(* demo..*.marked(..))"
        )
        public void trace(JoinPoint joinPoint) {
            System.out.println("ADVICE " + joinPoint.getSignature().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class Config {
        @Bean
        public CustomerApi customerApi() {
            return new CustomerService();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            CustomerApi bean = context.getBean(CustomerApi.class);

            System.out.println("JDK_PROXY="
                    + AopUtils.isJdkDynamicProxy(bean));
            System.out.println("INHERITED_DECLARED_IN="
                    + CustomerService.class
                            .getMethod("inherited", String.class)
                            .getDeclaringClass().getSimpleName());
            System.out.println("INTERFACE_DEFAULT="
                    + CustomerApi.class
                            .getMethod("fromDefault", String.class)
                            .isDefault());
            System.out.println("ANNOTATION_ON_INTERFACE="
                    + CustomerApi.class
                            .getMethod("marked", String.class)
                            .isAnnotationPresent(TraceCall.class));
            System.out.println("ANNOTATION_ON_IMPL="
                    + CustomerService.class
                            .getMethod("marked", String.class)
                            .isAnnotationPresent(TraceCall.class));

            System.out.println("RESULT " + bean.inherited("A"));
            System.out.println("RESULT " + bean.fromDefault("B"));
            System.out.println("RESULT " + bean.marked("C"));
        }
    }
}
```

Chạy trong thư mục dự án:

```bash
mvn -q compile exec:java
```

Các dòng stdout **do chương trình tự in** (thông báo Maven hoặc thư viện logging có thể xuất hiện thêm):

```text
JDK_PROXY=true
INHERITED_DECLARED_IN=BaseService
INTERFACE_DEFAULT=true
ANNOTATION_ON_INTERFACE=false
ANNOTATION_ON_IMPL=true
ADVICE inherited
TARGET inherited A
RESULT BASE:A
ADVICE fromDefault
TARGET default B
RESULT DEFAULT:B
ADVICE marked
TARGET marked C
RESULT MARKED:C
```

Các điểm cần đối chiếu với output:

- `CustomerService` **không khai báo lại** `inherited()`, nhưng method vẫn được gọi qua `CustomerApi`; advice in trước implementation kế thừa từ `BaseService`.
- `fromDefault()` có code trong interface. JDK proxy tiếp nhận lời gọi và Spring có cơ hội áp advisor trước khi method default chạy trên target.
- `TraceCall` nằm tại `CustomerService.marked()`, **không nằm tại `CustomerApi.marked()`**. Hai dòng kiểm tra annotation phản ánh sự khác nhau giữa method declaration trên interface và implementation.
- Code advice ở ví dụ sử dụng `execution(...)` theo **tên method**, nên dòng `ADVICE marked` **chưa chứng minh** một pointcut `@annotation(TraceCall)` sẽ có kết quả giống nhau cho mọi loại proxy/annotation placement.

### 5.2. Chuyển sang CGLIB để kiểm tra

Trong class `Config`, đổi:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

Sau đó thay điều kiện quan sát proxy bằng:

```java
System.out.println("CGLIB_PROXY="
        + AopUtils.isCglibProxy(bean));
```

Đây là **hai đoạn thay thế nhỏ**, không phải code standalone. Với target class đủ điều kiện kế thừa, Spring có thể tạo CGLIB proxy. Hãy chạy lại ba lời gọi trong cùng context và quan sát trace thay vì mặc định rằng cách đối chiếu interface default method giống hoàn toàn giữa mọi phiên bản proxy.

## 6. Vị trí đặt annotation: Java thực sự nhìn thấy gì?

### 6.1. Annotation ở implementation method

```java
public interface CustomerApi {
    void submit();
}

public class CustomerService implements CustomerApi {
    @TraceCall
    @Override
    public void submit() {
        // xử lý nghiệp vụ
    }
}
```

Đây là phương án rõ ràng nếu bạn muốn khai báo metadata tại nơi chứa **implementation thực sự**. Với JDK proxy, lời gọi client có thể mang Method reflection thuộc interface, trong khi Spring có khả năng tìm **most specific method** trên target class để kiểm tra match.

Dù vậy, đừng giả định mọi custom annotation resolver đều tự tìm từ interface sang implementation. Đặt annotation tại nơi mà **Spring feature đang dùng** chính thức đọc và kiểm tra bằng test.

### 6.2. Annotation chỉ đặt trên interface method

```java
public interface CustomerApi {
    @TraceCall
    void submit();
}

public class CustomerService implements CustomerApi {
    @Override
    public void submit() {
        // xử lý nghiệp vụ
    }
}
```

Java reflection thông thường phân biệt method `CustomerApi.submit()` với method `CustomerService.submit()`. **Method annotation không tự động được “kế thừa” chỉ bởi vì class implements interface**. Do đó, khi framework xử lý annotation trên implementation, nó có thể không thấy annotation ở interface nếu không chủ động tra cứu theo hierarchy/interface.

Điểm này đặc biệt quan trọng nếu pointcut sử dụng `@annotation(...)` hay nếu một framework feature đọc annotation riêng. Không đánh đồng `@TraceCall` và annotation đặc thù được Spring hỗ trợ qua metadata resolver riêng.

### 6.3. Annotation trên method của superclass

```java
public class BaseService {
    @TraceCall
    public void submit() {
        // xử lý gốc
    }
}

public class CustomerService extends BaseService {
    // Không override submit()
}
```

Khi class con **không override**, `CustomerService.class.getMethod("submit")` có thể trả method được khai báo từ superclass và mang annotation đó.

Nếu class con **override** và không gắn lại annotation:

```java
public class CustomerService extends BaseService {
    @Override
    public void submit() {
        // xử lý khác
    }
}
```

thì Method reflection của class con là **method khác** và `isAnnotationPresent(TraceCall.class)` trên Method đó không tự trả `true` chỉ vì method cha có annotation. Spring có thể tìm annotation theo hierarchy với một số tiện ích hoặc tính năng, nhưng cơ chế lookup này phải được kiểm chứng.

### 6.4. `@Inherited` không áp dụng cho method annotation

Trong Java, `java.lang.annotation.Inherited` có tác dụng khi truy vấn annotation **trên class**, và chỉ trong quan hệ superclass/subclass thích hợp. Nó không làm **method annotations** tự thừa kế qua override, cũng không biến interface annotations thành class annotations được kế thừa theo mặc định.

Vì vậy đoạn sau không giải quyết bài toán annotation trên interface method:

```java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ServiceMarker {
}
```

Đây là **minh họa annotation trên TYPE**, không phải `@TraceCall` dành cho METHOD. Từ khóa `@Inherited` không thay thế chức năng tìm annotation trên method/interface mà Spring có thể cần thực hiện.

## 7. `execution` và `@annotation` trong Spring AOP không giống nhau

Hai pointcut hay bị nhầm:

```java
@Before("execution(* demo..*.submit(..))")
public void bySignature() {
    // chạy cho method execution phù hợp chữ ký
}

@Before("@annotation(demo.TraceCall)")
public void byAnnotation() {
    // chạy cho method execution khớp annotation theo Spring AOP matcher
}
```

Đây là **hai advice minh họa**, không phải chương trình biên dịch độc lập. Nếu đặt trong một `@Aspect` bean, chúng dùng cơ chế match khác nhau:

| Pointcut | Trọng tâm | Điều cần kiểm tra |
| --- | --- | --- |
| `execution(...)` | Chữ ký method execution, modifiers, return type, tên/args/declaring type pattern | Kiểu và method được Spring AOP nhận diện, lời gọi có qua proxy |
| `@annotation(...)` | Annotation trên method execution theo matcher | Annotation xuất hiện ở đâu, target-specific method và lookup semantics |
| `@within(...)` | Kiểu có annotation, giới hạn các execution trong kiểu | Annotation đặt ở class/interface nào; method inherited có nằm trong phạm vi match không |
| `@target(...)` | Class của target object mang annotation được xét | Target class và annotation semantics |
| `this(Type)` / `target(Type)` | Kiểu của proxy / target | JDK proxy không phải subclass của implementation |

**Đừng sửa lỗi `@annotation` không khớp bằng cách ngẫu nhiên chuyển annotation giữa interface và implementation.** Trước hết cần biết Spring lấy Method nào và feature đang dùng (AOP pointcut hay annotation-specific interceptor).

Một cách chẩn đoán là lấy method thuộc interface rồi giải quyết implementation:

```java
Method interfaceMethod =
        CustomerApi.class.getMethod("submit");

Method targetMethod =
        AopUtils.getMostSpecificMethod(
                interfaceMethod, CustomerService.class);
```

Đây là **đoạn API minh họa** (cần import `java.lang.reflect.Method`, `AopUtils`). `getMostSpecificMethod(...)` giúp tìm method trên target class nếu có. Nó **không** có nghĩa Spring luôn sử dụng đúng duy nhất Method đó cho mọi loại annotation hay mọi trường hợp.

## 8. Annotation của Spring framework cần đánh giá theo chính tính năng đó

Không phải mọi annotation gây ra advice đều được xử lý chỉ bằng AspectJ `@annotation` pointcut. Ví dụ:

- **`@Transactional`** được transaction metadata infrastructure giải quyết qua `TransactionAttributeSource`, rồi Spring dùng interceptor/proxy cho transaction. Spring khuyến nghị đặt annotation trên concrete class/method khi có thể để tránh khác biệt khi đổi proxy/processing mode. Các phiên bản Spring hiện đại có thể hỗ trợ một số cách đặt ở interface trong proxy mode; điều đó **không tạo quy luật chung cho custom annotation**.
- **`@Cacheable`** được caching infrastructure xử lý và có cơ chế tìm metadata, điều kiện cache key, proxy riêng. Việc `@Cacheable` ở interface hoặc implementation có hoạt động như mong đợi không cần được xác minh với cấu hình/version của tính năng.
- **`@Async`** cũng có xử lý annotation và proxy/executor riêng. Đừng dùng kết quả `@Async` ở một vị trí annotation để kết luận một `@Aspect` với `@annotation(...)` xử lý metadata y hệt.

Điểm thống nhất ở chế độ **Spring proxy** là lời gọi từ client phải đi vào proxy được cấu hình đúng và method phải đủ điều kiện được chặn.

### Vị trí class annotation và method inherited

Ngay cả với Spring `@Transactional`, tài liệu chỉ ra rằng class-level annotation không mặc nhiên áp cho mọi method **được khai báo ở ancestor class** trong mọi tình huống. Cần xét cách Spring quyết định metadata cho inherited method và phương thức override tại class con. Nếu muốn một hợp đồng rõ ràng, viết test bao phủ method được kế thừa/override thay vì chỉ nhìn annotation trên class con.

## 9. Self-invocation: phương thức kế thừa/default không phải ngoại lệ

Dù code method nằm ở superclass hoặc interface, một lời gọi **bên trong target** vẫn không tự động quay lại Spring proxy.

Ví dụ:

```java
public class CustomerService extends BaseService implements CustomerApi {
    public void outer() {
        this.inherited("A");
    }
}
```

Nếu caller gọi `proxy.outer()` và có advice cho `outer()`, advice ngoài có thể chạy. Nhưng sau khi Spring chuyển tới target, `this.inherited("A")` chạy trực tiếp trên target; advice chỉ khớp `inherited()` **không được chạy thêm** qua đường này.

Tương tự, nếu một default method chạy trên target và gọi một method khác, không được giả định lời gọi nội bộ đó là lời gọi client mới vào proxy. Khi hành vi cần interceptor riêng, nên tách sang Spring bean khác và inject bean reference do container cấp.

Đổi `proxyTargetClass=true` **không tự sửa self-invocation**. Nó chỉ đổi chiến lược tạo proxy.

## 10. Giới hạn theo visibility và vị trí code

| Tình huống | JDK proxy | CGLIB proxy | Cách hiểu |
| --- | --- | --- | --- |
| Public method kế thừa từ superclass và khai báo trên interface | Có thể intercept | Có thể intercept nếu method overrideable | Code nằm ở superclass không phải lý do bỏ qua |
| Public method kế thừa nhưng không công bố trên interface | Không gọi được qua API của JDK proxy | Có thể intercept nếu đủ điều kiện | Phân biệt target API và proxy API |
| Public interface default method | Có thể đi qua proxy | Có thể, cần xác minh override/matching cụ thể | `default` không tự tạo advice |
| `protected` method | Không nằm trong public interface API | Có thể tùy Spring version/visibility | Ưu tiên public boundary rõ ràng |
| `private` method | Không | Không | Không thể override/intercept bằng cơ chế proxy |
| `final` method của target | JDK proxy có thể intercept lời gọi qua interface trong trường hợp tương ứng | Không thể override method đó | Cần xét proxy strategy, không đánh đồng |
| `final class` | Có thể JDK proxy nếu có interface phù hợp | Không thể subclass | Cấu hình ép CGLIB có thể gây lỗi |
| Constructor và field access | Không | Không | Ngoài method-execution boundary của Spring AOP |
| `this.method()` bên trong target | Không vào lại proxy | Không vào lại proxy | Self-invocation bypass advice |

Dòng về `final method` cần đọc cẩn thận: `final` không ngăn **interface method call** đi vào một **JDK proxy**, nhưng ngăn **subclass proxy override method target**. Một JDK proxy và một CGLIB proxy có thể cho kết quả advice khác nhau ở tình huống này.

## 11. Checklist kiểm tra khi advice không chạy

1. **Bean có được Spring quản lý?** Tạo bằng `@Component`/`@Bean` hay ứng dụng đang gọi object `new` trực tiếp?
2. **Có proxy thực sự không?** Dùng `AopUtils.isAopProxy(bean)`, `isJdkDynamicProxy(bean)`, `isCglibProxy(bean)`.
3. **Caller dùng kiểu nào?** Interface hay implementation? JDK proxy chỉ công bố interface được proxy triển khai.
4. **Method thật khai báo ở đâu?** Implementation, superclass, interface default hay method override?
5. **Method có thể bị proxy chặn không?** Public interface method cho JDK; method có thể override và phù hợp visibility cho CGLIB.
6. **Pointcut khớp gì?** `execution` dựa signature, `@annotation` dựa annotation trên method được matcher xét.
7. **Annotation nằm ở đâu?** Method/interface/class/superclass? Có override bỏ annotation không? `@Inherited` có bị hiểu nhầm là method inheritance không?
8. **Đang dùng module Spring nào?** `@Transactional`/`@Cacheable`/`@Async` có metadata resolver và cấu hình riêng; không đồng nhất với custom `@annotation` pointcut.
9. **Có self-invocation không?** `this.method()` và các lời gọi nội bộ trên target không vào lại proxy.
10. **Có nhiều proxy/advisor không?** Cấu hình proxy-target-class, thứ tự advice và pointcut động có thể làm kết quả khác dự đoán.

Một kiểm thử tốt dùng **ApplicationContext thật**, lấy đúng Spring bean reference, xác minh loại proxy, rồi gọi **từ client bên ngoài target**. Kết hợp test cho hai proxy mode nếu ứng dụng hỗ trợ cả JDK và CGLIB.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `CustomerService` kế thừa method public `run()` từ `BaseService` và `CustomerApi` khai báo `run()`. JDK proxy có thể chạy Spring AOP advice khi client gọi `run()` qua interface không?  
**Đáp án:** Có, nếu advisor/pointcut khớp và bean thực sự nhận AOP proxy. Vị trí implementation ở superclass không ngăn interceptor.

**Câu 2.** Cũng method `run()` đó, nhưng interface không khai báo nó. Client giữ JDK proxy có thể ép proxy sang implementation để gọi `run()` không?  
**Đáp án:** Không thể giả định; JDK proxy không phải subclass của implementation. Nếu cần method này qua proxy, cân nhắc API interface hoặc CGLIB khi phù hợp.

**Câu 3.** Default method có implementation sẵn trong interface. Điều đó khiến nó không thể được Spring AOP intercept?  
**Đáp án:** Không. Lời gọi từ client qua proxy vẫn có thể được chặn, tùy advisor matching và phương thức mà proxy hỗ trợ.

**Câu 4.** Một method implementation được gắn `@TraceCall` nhưng interface method không có annotation. Java reflection trên interface method có tự trả true không?  
**Đáp án:** Không. Hai Method declaration khác nhau, annotation đặt ở implementation không tự xuất hiện trên interface method.

**Câu 5.** Method cha có annotation, con override method không khai báo lại annotation. Java method reflection của con có tự kế thừa method annotation nhờ `@Inherited` không?  
**Đáp án:** Không. `@Inherited` dành cho annotation trên class theo quan hệ superclass, không tự áp dụng cho method override.

**Câu 6.** Spring `@Transactional` ở interface hoạt động trong một cấu hình proxy. Có đủ cơ sở kết luận custom pointcut `@annotation(MyMarker)` luôn hoạt động y hệt không?  
**Đáp án:** Không. Spring transaction metadata lookup và AspectJ `@annotation` pointcut không mặc nhiên đồng nhất.

**Câu 7.** `outer()` gọi `this.inherited()` và method kế thừa có advice. Advice đó chạy cho lời gọi nội bộ không?  
**Đáp án:** Không có một lần intercept mới qua proxy. Cần thay đổi đường gọi để đi qua proxy nếu muốn advice được kích hoạt.

## Tài liệu Spring Framework

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): giới hạn JDK/CGLIB, self-invocation và final/private.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `execution`, `@annotation`, `@within`, `@target` và phạm vi method execution.
- [Spring Framework — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): đăng ký aspect bean và bật Spring AOP.
- [Spring Framework 6.2 — Using @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): annotation placement, interface/implementation, method visibility và self-invocation trong transaction proxy mode.
