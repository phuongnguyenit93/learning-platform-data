# Chọn `@Target` và `@Retention` phù hợp cho annotation dùng với Spring AOP

## 1. Mục đích

Khi xây dựng custom annotation để kích hoạt một advice của **Spring AOP**, hai meta-annotation Java đặc biệt quan trọng:

- `@Target` quy định annotation **được phép khai báo ở vị trí nào** trong source code, chẳng hạn trên method hoặc class.
- `@Retention` quy định annotation **được giữ lại đến giai đoạn nào**. Advice Spring AOP chạy trong JVM, nên marker mà Spring/AOP phải tìm lúc runtime thông thường cần `RetentionPolicy.RUNTIME`.

Lựa chọn này liên quan trực tiếp đến pointcut Spring như `@annotation`, `@within`, `@target`, đến cách Spring đọc metadata bằng reflection/merged-annotation APIs, và đến ranh giới proxy. Đây là hướng dẫn về **Aspect trong Spring**, không phải bài tổng quan độc lập về AspectJ weaving.

## 2. Chọn `@Target` theo vị trí của marker

| Cách thiết kế | Khai báo phù hợp | Cách advice thường được áp dụng |
| --- | --- | --- |
| Đánh dấu một method nghiệp vụ | `@Target(ElementType.METHOD)` | `@annotation(...)` cho method execution được Spring AOP proxy intercept |
| Đánh dấu toàn bộ lớp service | `@Target(ElementType.TYPE)` | `@within(...)` hoặc `@target(...)` với semantics tương ứng, cần kiểm tra kiểu target/proxy |
| Cho phép trên cả method và class | `@Target({ElementType.METHOD, ElementType.TYPE})` | Thiết kế hai nhánh pointcut rõ ràng; không giả định một `@annotation` sẽ bắt class annotation |
| Đánh dấu annotation khác để tạo composed annotation | `@Target(ElementType.ANNOTATION_TYPE)` hoặc thêm vị trí cần thiết | Metadata APIs của Spring có thể hỗ trợ merged annotations; matching pointcut AspectJ có giới hạn riêng cần test |

`ElementType.PARAMETER` đánh dấu tham số khai báo trong method, không khiến `@annotation` tự bắt một method execution. `ElementType.TYPE_USE` hoặc `TYPE_PARAMETER` cũng không biến Spring AOP thành pointcut bắt type-use. Spring AOP tiêu chuẩn tập trung vào **method-execution join points qua proxy**.

### Annotation dùng trên method

~~~java
package demo;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Audited {
    String event() default "operation";
}
~~~

Dùng trên method được Spring quản lý:

~~~java
@Service
class OrderService {
    @Audited(event = "place-order")
    public String place(String orderId) {
        return "accepted:" + orderId;
    }
}
~~~

Nếu `@Target(TYPE)` mà lại đặt lên method, Java compiler báo lỗi ở declaration site. Nếu `@Target(METHOD)` mà đặt lên class, compiler cũng từ chối; đây là lợi ích của metadata contract rõ ràng.

### Annotation dùng trên class

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface MonitoredService {}
~~~

~~~java
@MonitoredService
@Service
class PaymentService {
    public String pay() { return "paid"; }
}
~~~

Một `@annotation(demo.MonitoredService)` chỉ kiểm tra annotation tại method và không phải lựa chọn phù hợp để lọc class marker. Cần chủ động chọn `@within`/`@target` theo loại target, semantics static/runtime của pointcut và hành vi proxy.

## 3. Chọn `@Retention`: SOURCE, CLASS hay RUNTIME?

| Policy | Có trong bytecode? | Có thể tìm bằng reflection ở runtime? | Phù hợp marker Spring AOP runtime? |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Thường bị compiler loại khi tạo class | Không | Không |
| `RetentionPolicy.CLASS` | Có trong class file | Không xuất hiện qua reflection runtime thông thường | Không |
| `RetentionPolicy.RUNTIME` | Có | Có | **Có, khi pointcut/proxy tương ứng match** |

Nếu không khai báo `@Retention`, mặc định của Java là `RetentionPolicy.CLASS`. Vì vậy marker không định nghĩa retention rõ ràng thường dẫn đến hiện tượng “annotation nhìn thấy trong source nhưng advice không chạy”. Để Spring đọc annotation từ `AnnotatedElement` trong JVM, cách chọn thông thường là `RUNTIME`.

`RUNTIME` là **điều kiện cần**, không phải điều kiện đủ. Advice còn phụ thuộc:

1. Có bean `@Aspect` được Spring nhận diện và hạ tầng `@EnableAspectJAutoProxy`/Boot AOP được thiết lập.
2. Pointcut đúng loại annotation và đúng method/class được kiểm tra.
3. Method call đi qua Spring AOP proxy; `this.someMethod()` bên trong target bỏ qua proxy.
4. JDK dynamic proxy và CGLIB class-based proxy có khác biệt trong cấu trúc method/interface và những method intercept được.
5. Chỉ định pointcut phù hợp nếu annotation nằm trên interface hay implementation; kiểm thử proxy strategy thực tế.

## 4. Ví dụ Spring chạy được, Java 17 + Maven

Cấu trúc project:

~~~text
spring-aop-marker-meta/
  pom.xml
  src/main/java/demo/Audited.java
  src/main/java/demo/OrderService.java
  src/main/java/demo/AuditAspect.java
  src/main/java/demo/Application.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-aop-marker-meta</artifactId>
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
      <version>1.9.25</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Audited.java**

~~~java
package demo;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Audited {
    String event() default "operation";
}
~~~

`@Documented` cho phép JavaDoc đưa marker vào tài liệu API; nó không làm Spring AOP match mạnh hơn.

**OrderService.java**

~~~java
package demo;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    @Audited(event = "placed")
    public String place(String id) {
        return "accepted:" + id;
    }

    public String status() {
        return "ready";
    }
}
~~~

**AuditAspect.java**

~~~java
package demo;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("@annotation(audited)")
    public void audit(Audited audited) {
        System.out.println("audit:" + audited.event());
    }
}
~~~

Aspect dùng `@annotation(audited)` để bind marker thực tế vào tham số `audited`. Có thể dùng `argNames` khi compilation không giữ thông tin tên tham số như mong muốn; trong ví dụ một annotation-typed argument này Spring AOP/AspectJ thường suy ra binding, nhưng đối với project nhiều tham số nên khai báo rõ.

**Application.java**

~~~java
package demo;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan("demo")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Application {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Application.class)) {
            OrderService service = context.getBean(OrderService.class);
            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println(service.place("o-7"));
            System.out.println(service.status());
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Application
~~~

Kết quả mong đợi từ `System.out` của ứng dụng:

~~~text
proxy=true
audit:placed
accepted:o-7
ready
~~~

`status()` không được đánh dấu `@Audited` nên advice này không áp dụng. `place()` đi qua Spring proxy, marker runtime có thể match và giá trị annotation được bind. Đây là **expected output kiểm tra tĩnh**, không phải lời khẳng định đã thực thi Maven tại máy hiện tại.

## 5. Nếu marker khai báo trên interface thì sao?

Xem hai khai báo:

~~~java
public interface ReportApi {
    @Audited(event = "generate")
    String generate();
}
~~~

~~~java
@Service
class ReportService implements ReportApi {
    public String generate() { return "done"; }
}
~~~

Java annotation trên interface method **không tự động trở thành annotation của implementation method**. Java `@Inherited` chỉ có hiệu lực giới hạn trên class-level inheritance, không kế thừa method annotation hay interface annotation theo cách Java reflection thông thường mong đợi.

Trong Spring AOP, framework và matcher có thể chọn method phản ánh trên interface/proxy hoặc method implementation tùy advisor/pointcut. Không giả định annotation chỉ khai trên interface sẽ match giống class-based proxy. Với policy quan trọng, thường đặt annotation nhất quán ở implementation method, hoặc xây một advisor/custom matcher sử dụng Spring metadata APIs có kiểm thử cho JDK/CGLIB.

Kiểm thử nên bao gồm:

- Interface method có marker, implementation không có.
- Implementation có marker, interface không có.
- Annotation trên class và trên method, với pointcuts riêng.
- JDK dynamic proxy so với CGLIB class proxy.
- Invocation qua Spring bean proxy so với gọi `this.generate()` nội bộ.

## 6. Meta-annotation trong Spring và giới hạn khớp pointcut

Spring cung cấp `AnnotatedElementUtils`, `MergedAnnotations`, `AnnotationUtils` cùng `@AliasFor` để đọc các annotation tổng hợp trong nhiều ngữ cảnh của framework. Nhưng sự tồn tại của annotation tổng hợp không đồng nghĩa `@annotation(SomeMarker)` của AspectJ-style pointcut tự mở rộng sang mọi annotation được meta-annotated.

Ví dụ:

~~~java
@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Audited(event = "trace")
public @interface Traced {}
~~~

Mẫu trên chỉ hợp lệ khi `@Audited` cho phép `ANNOTATION_TYPE` trong `@Target`. Nếu bản `Audited` ở demo chỉ cho `METHOD`, compiler từ chối `@Audited` trên declaration `@Traced`. Điều này cho thấy cần thiết kế `@Target` theo kế hoạch sử dụng ngay từ đầu.

Một annotation tổng hợp `@Traced` có thể được Spring metadata inspection nhìn thấy qua merged lookup, trong khi AspectJ `@annotation(demo.Audited)` vẫn cần được kiểm chứng bằng integration tests. Với meta-annotation conventions phức tạp, cân nhắc advisor `StaticMethodMatcherPointcut` riêng dùng Spring `MergedAnnotations` và test matching tường minh.

## 7. Scope proxy quan trọng hơn annotation declaration

Spring AOP không weave trực tiếp vào mọi method call của JVM. Marker đúng `RUNTIME` mà không thấy advice vẫn có thể là một trong các lý do:

~~~java
@Service
class CheckoutService {
    public void outer() {
        inner(); // self-invocation: không gọi lại qua Spring AOP proxy
    }

    @Audited
    public void inner() {
        // ...
    }
}
~~~

Một lời gọi từ bên ngoài vào `outer()` (không có marker) rồi tự gọi `inner()` sẽ không kích hoạt `@Before("@annotation(...")` cho lần inner call đó. Giải quyết bằng cấu trúc service phù hợp, tách bean và gọi qua dependency Spring proxy hoặc đưa concern lên entry point phù hợp, thay vì thay đổi retention.

Ngoài ra:

- Class-based proxy thông thường không advice được `final`/private method.
- JDK proxy chỉ exposes interface contract ở reference của caller.
- Target tạo bằng `new` không qua container sẽ không tự được Spring advice.
- Khi dùng `@Async` hoặc `@Transactional`, nhiều advisors có thứ tự và ranh giới khác nhau; kiểm tra method execution qua đúng proxy.
- Nếu annotation được dùng làm phân quyền hoặc chính sách bắt buộc, không coi marker + pointcut là lớp bảo vệ duy nhất: self-invocation và non-proxied calls có thể bỏ qua advice.

## 8. Kiểm thử `@Target` và `@Retention` bằng Java reflection

Bài test nhỏ này hoạt động cho `Audited` trong project demo:

~~~java
package demo;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class MetadataCheck {
    public static void main(String[] args) throws Exception {
        Class<Audited> type = Audited.class;
        Target target = type.getAnnotation(Target.class);
        Retention retention = type.getAnnotation(Retention.class);
        System.out.println("targetMethod=" +
            Arrays.asList(target.value()).contains(ElementType.METHOD));
        System.out.println("runtime=" +
            (retention.value() == RetentionPolicy.RUNTIME));
        System.out.println("markerPresent=" +
            OrderService.class.getMethod("place", String.class).isAnnotationPresent(Audited.class));
    }
}
~~~

Chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MetadataCheck
~~~

Output dự kiến:

~~~text
targetMethod=true
runtime=true
markerPresent=true
~~~

Khác với kiểm tra pointcut, reflection test này chỉ chứng minh marker tồn tại trên method cụ thể và giữ được đến runtime. Nó **không thay** integration test xác nhận advice thật sự match proxy.

## 9. Các lỗi thường gặp

**Có `@Target(METHOD)` nhưng annotation đặt ở class.** Java compiler báo annotation không áp dụng được tại vị trí này. Sửa declaration target cho đúng dự định, sau đó chỉnh lại pointcut tương ứng, tránh thêm vị trí vô tội vạ.

**Không khai báo `@Retention`, nên `@annotation` không chạy.** Mặc định retention là CLASS. Đối với Spring runtime advice, thường dùng `RUNTIME`.

**Khai báo `@Retention(RUNTIME)` nhưng advice không chạy.** Kiểm tra Spring AOP activation, bean managed, pointcut, interface/implementation annotations, final/private methods và self-invocation.

**Thêm `@Inherited` mong method marker lan sang implementation.** Java `@Inherited` không giải quyết method/interface metadata theo cách đó; kiểm thử target thật của Spring proxy.

**Composed annotation hiện trong `AnnotatedElementUtils` nhưng không match `@annotation`.** Spring merged metadata lookup và AspectJ pointcut matching không cùng thuật toán; cần integration test và có thể custom matcher.

**Đặt marker trên field, constructor hoặc parameter và mong Spring AOP advice bắt tại đó.** Spring AOP là proxy-based method execution. Cần thiết kế method-level annotation hoặc công cụ chuyên biệt nếu yêu cầu thật sự khác.

## 10. Checklist sử dụng tại dự án Spring

1. Viết rõ marker dành cho **method**, **type**, hay cả hai và dùng `@Target` hẹp, có chủ ý.
2. Chọn `@Retention(RUNTIME)` cho metadata mà advice runtime cần đọc.
3. Với composed annotation, thêm `ANNOTATION_TYPE` nếu declaration cần làm meta-annotation; kiểm thử Spring metadata API và AspectJ pointcut riêng.
4. Chạy integration test với Spring proxy trên đúng kiểu bean, kiểm tra interface/implementation, JDK/CGLIB và self-invocation.
5. Tránh trộn business policy phức tạp vào annotation; annotation chỉ nên mang metadata cấu hình rõ nghĩa cho concern Spring AOP.
6. Lưu `@Documented` nếu cần API docs, không coi nó là điều kiện matching.
7. Rà soát các advisor khác (`@Transactional`, `@Cacheable`, `@Async`) và kiểm tra thứ tự áp dụng phù hợp.

## Tài liệu đối chiếu

- Spring Framework Reference — Declaring a pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework Reference — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Advice with annotation-style aspects: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Java SE 17 API: `java.lang.annotation.Target`, `Retention`, `RetentionPolicy`, `ElementType`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/package-summary.html

**Kết luận:** Đối với custom annotation phục vụ Spring AOP ở runtime, thường dùng `@Retention(RUNTIME)` và `@Target(METHOD)` nếu đánh dấu từng method, hoặc `TYPE` nếu đánh dấu cả class. Hãy kiểm tra Spring proxy, method metadata và pointcut cùng nhau; chỉ có meta-annotation đúng không bảo đảm advice sẽ chạy.