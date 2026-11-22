# Phân biệt `@Aspect` với annotation đăng ký component trong Spring AOP

## 1. Vấn đề cần phân biệt

Trong Spring AOP, một lớp có `@Aspect` **chưa chắc được Spring container quản lý**. Ngược lại, một lớp có `@Component` là ứng viên được Spring component scan đăng ký làm bean nhưng **không tự động trở thành aspect**. Hai annotation giải quyết **hai câu hỏi khác nhau**:

- **`@Aspect`** trả lời: *Lớp này có khai báo các advice/pointcut để Spring AOP nhận diện không?*
- **`@Component`** (hoặc stereotype tương đương) trả lời: *Spring component scanner có nên phát hiện và đăng ký lớp này thành bean không?*

Để advice từ một lớp `@Aspect` được Spring AOP sử dụng, Spring cần thấy lớp đó **dưới dạng bean trong `ApplicationContext`**, đồng thời ứng dụng cần bật hỗ trợ `@AspectJ` auto-proxy. Bean của aspect và bean đích phải được cấu hình để cơ chế AOP áp dụng được.

Bài học chỉ tập trung vào annotation, bean registration và cơ chế phát hiện aspect **trong Spring Framework/Spring Boot**. Những khái niệm Aspect mang tính tổng quát nằm ngoài phạm vi ở đây.

## 2. Hai nhóm annotation có trách nhiệm khác nhau

| Tiêu chí | `@Aspect` | `@Component` / annotation đăng ký component |
| --- | --- | --- |
| Thuộc thư viện | `org.aspectj.lang.annotation.Aspect` (AspectJ) | `org.springframework.stereotype.Component` (Spring) |
| Vai trò chính | Đánh dấu class chứa khai báo aspect để Spring AOP phân tích | Đánh dấu class là ứng viên Spring bean khi component scan |
| Tự làm Spring scan thấy class? | **Không** | **Có**, khi class nằm trong phạm vi scan và đáp ứng điều kiện |
| Tự định nghĩa advice? | Cho Spring biết cần xét các method `@Before`, `@Around`,… bên trong class | **Không** |
| Có đủ để lời gọi target chạy advice? | Không, phải có aspect bean, cơ chế AOP và target proxy phù hợp | Không, phải có advisor/pointcut khớp và lời gọi qua proxy |
| Có thể dùng một mình không? | Có thể khi aspect đã được khai báo bean bằng `@Bean` hoặc cách khác | Có; một component bình thường không nhất thiết là aspect |
| Có thể dùng đồng thời? | **Có** | **Có** |

Hai import cần nhớ:

```java
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;
```

**Lưu ý quan trọng:** Spring Framework documentation nói rõ `@Aspect` **không đủ cho autodetection qua classpath scanning**. Bạn cần thêm `@Component` hoặc một custom stereotype hợp lệ theo quy tắc component scanner, **hoặc** đăng ký instance aspect bằng `@Bean`, XML/bean definition. Đây là quy tắc Spring, không phải khác biệt cú pháp giữa hai annotation.

## 3. Ba trường hợp thường gặp

### Trường hợp A: Chỉ có `@Aspect`

```java
package example.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.service.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("[audit] before submit");
    }
}
```

Nếu cấu hình ứng dụng chỉ dùng `@ComponentScan` và **không có bean definition khác cho lớp này**, thì scanner không đăng ký `AuditAspect`. Kết quả là:

- `AuditAspect` là lớp Java có metadata `@Aspect`.
- **Không có `AuditAspect` bean** trong context do component scan cung cấp.
- Advice trong đó **không được Spring AOP sử dụng** chỉ vì lớp có mặt trên classpath.
- `@EnableAspectJAutoProxy` cũng **không tự biến class ngoài container thành bean**.

Nghĩa là cách viết chỉ có `@Aspect` **không sai**: nó hoạt động nếu bạn **đăng ký lớp thành bean bằng cách khác**, như `@Bean`. Sai lầm là cho rằng annotation ấy tự đăng ký bean.

### Trường hợp B: `@Aspect` + `@Component`

```java
package example.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* example.service.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("[audit] before submit");
    }
}
```

Đây là mẫu thông dụng:

1. `@Component` cho phép component scanner phát hiện lớp và Spring đăng ký `AuditAspect` thành bean (nếu package được scan).
2. `@Aspect` cho phép Spring AOP phân tích bean ấy để tìm advice, pointcut và advisor.
3. Nếu bật AOP, một bean đích như `OrderService` khớp pointcut có thể nhận proxy; gọi method thông qua proxy khiến advice chạy.

### Trường hợp C: Chỉ có `@Component`, không có `@Aspect`

```java
package example.aop;

import org.springframework.stereotype.Component;

@Component
public class AuditHelper {
    public void log(String event) {
        System.out.println("[helper] " + event);
    }
}
```

`AuditHelper` là Spring bean thông thường, có thể được inject và gọi bình thường. Nó **không được nhận là một `@AspectJ` aspect** chỉ vì class là component. Việc có một method tên `beforeSubmit` cũng không khiến Spring AOP coi nó là advice.

> Quy tắc thực hành: **`@Aspect` mô tả vai trò AOP của class; `@Component` cho phép scanner đăng ký class làm bean.** Spring sử dụng cả hai thông tin ở những bước khác nhau.

## 4. `@Component`, `@Service`, `@Repository` và custom stereotype

Các annotation Spring như `@Service`, `@Repository`, `@Controller` là stereotype có quan hệ meta-annotation với `@Component`; chúng dùng để đánh dấu vai trò bean trong từng tầng ứng dụng. Nếu bạn viết:

```java
@Aspect
@Service
public class AuditAspect {
    // ...
}
```

Thì về **khả năng component scan**, một stereotype được Spring công nhận như `@Service` vẫn có thể khiến lớp được đăng ký thành bean. Tuy nhiên, **`@Component` là lựa chọn diễn đạt rõ hơn** cho một aspect kỹ thuật không phải nghiệp vụ service. Đừng dùng `@Service` chỉ để chữa lỗi Spring không tìm thấy aspect.

Ngược lại, bean đích thường được định nghĩa bằng annotation thể hiện đúng vai trò:

```java
@Service
public class OrderService {
    public void submit() {
        System.out.println("order submitted");
    }
}
```

Sự có mặt của `@Service` không làm `OrderService` thành aspect. Nó là **target bean** có thể được advice can thiệp sau khi Spring AOP tạo proxy phù hợp.

### Custom stereotype

Bạn cũng có thể định nghĩa stereotype riêng được meta-annotate bằng `@Component`:

```java
package example.aop;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.stereotype.Component;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Component
public @interface InfrastructureComponent {
}
```

Và sử dụng:

```java
// Minh họa lớp dùng custom stereotype; các method advice được lược bớt.
@Aspect
@InfrastructureComponent
public class AuditAspect {
}
```

Khi scanner nhận diện `InfrastructureComponent` theo meta-annotation, lớp là ứng viên bean. `@Aspect` vẫn có trách nhiệm riêng. Custom stereotype chỉ nên tạo khi dự án có ngữ nghĩa thực sự cần dùng lại, không cần thiết cho ví dụ nhỏ.

## 5. Ví dụ Java 17+ chạy được: so sánh trực tiếp các trường hợp

Ví dụ Spring Framework thuần sử dụng Maven, Spring 6.2.19 và AspectJ Weaver 1.9.25.1. Mục đích là quan sát chính xác **aspect class nào trở thành bean, service có phải proxy và advice có chạy hay không**.

### 5.1. Cấu trúc project

```text
spring-aspect-component-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── OrderService.java
    ├── AuditAspect.java
    ├── InvisibleAspect.java
    ├── AuditHelper.java
    └── Main.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aspect-component-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`OrderService.java`**

```java
package example;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public void submit() {
        System.out.println("service: submit");
    }
}
```

**`AuditAspect.java`: có cả hai annotation**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* example.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("registered aspect: before");
    }
}
```

**`InvisibleAspect.java`: chỉ có `@Aspect`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class InvisibleAspect {
    @Before("execution(* example.OrderService.submit(..))")
    public void beforeSubmit() {
        System.out.println("invisible aspect: before");
    }
}
```

**`AuditHelper.java`: chỉ có `@Component`**

```java
package example;

import org.springframework.stereotype.Component;

@Component
public class AuditHelper {
    public String label() {
        return "helper bean";
    }
}
```

**`AppConfig.java`**

```java
package example;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "example")
@EnableAspectJAutoProxy
public class AppConfig {
}
```

**`Main.java`**

```java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println("AuditAspect beans: "
                + context.getBeanNamesForType(AuditAspect.class).length);
            System.out.println("InvisibleAspect beans: "
                + context.getBeanNamesForType(InvisibleAspect.class).length);
            System.out.println("AuditHelper beans: "
                + context.getBeanNamesForType(AuditHelper.class).length);

            OrderService service = context.getBean(OrderService.class);
            System.out.println("service is AOP proxy: " + AopUtils.isAopProxy(service));
            service.submit();
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Các dòng `System.out.println` của ví dụ, theo thứ tự:

```text
AuditAspect beans: 1
InvisibleAspect beans: 0
AuditHelper beans: 1
service is AOP proxy: true
registered aspect: before
service: submit
```

**Giải thích output:**

1. `AuditAspect` vừa có `@Aspect` vừa có `@Component`. Scanner đăng ký một bean, rồi Spring AOP dùng metadata aspect để tạo advice. Khi `submit()` được gọi qua service proxy, dòng `registered aspect: before` xuất hiện.
2. `InvisibleAspect` nằm ngay trong package `example` nhưng không có `@Component` hoặc khai báo `@Bean`. Vì vậy `InvisibleAspect beans: 0`; advice của nó không được đăng ký và dòng `invisible aspect: before` không xuất hiện.
3. `AuditHelper` có `@Component` nên có một bean, nhưng không có `@Aspect` và không tạo advice.
4. `@EnableAspectJAutoProxy` bật tính năng tìm aspect beans và tạo proxy. `service is AOP proxy: true` chứng minh target đang được Spring can thiệp.

Kết quả dựa trên **đúng các file/cấu hình** trong ví dụ. Nếu thêm bean definition cho `InvisibleAspect` hoặc sửa scan/configuration thì output sẽ thay đổi.

## 6. Không dùng `@Component` vẫn đăng ký được aspect bằng `@Bean`

Trong nhiều dự án, không muốn class aspect phụ thuộc vào annotation `@Component`, hoặc cần tạo aspect qua factory để inject các tham số cấu hình. `@Bean` cũng là cách Spring container quản lý aspect.

Để thử **biến thể** từ ví dụ mục 5, giữ `InvisibleAspect.java` (chỉ có `@Aspect`). Thay `AppConfig.java` bằng:

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "example")
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    public InvisibleAspect invisibleAspect() {
        return new InvisibleAspect();
    }
}
```

Các lớp còn lại giữ nguyên. Chạy lại chương trình mục 5 sẽ cho:

```text
AuditAspect beans: 1
InvisibleAspect beans: 1
AuditHelper beans: 1
service is AOP proxy: true
invisible aspect: before
registered aspect: before
service: submit
```

**Lưu ý về thứ tự advice:** Khi nhiều aspect có cùng loại advice và không cấu hình `@Order`, **thứ tự của hai dòng advice không được bảo đảm**. Hai dòng có thể đảo vị trí, còn ý nghĩa quan trọng là cả hai đều xuất hiện trước dòng `service: submit`. Đừng viết test phụ thuộc thứ tự ngẫu nhiên đó.

Lý do thay đổi: `@Bean` đăng ký instance `InvisibleAspect` thành Spring bean; `@Aspect` trên class vẫn được Spring AOP nhận diện. `new InvisibleAspect()` **trong factory method `@Bean`** khác với việc tùy ý tạo `new InvisibleAspect()` bên ngoài container: chỉ instance được trả về từ `@Bean` mới là bean đã đăng ký.

Nếu bạn chỉ muốn một aspect, hãy bỏ hoặc vô hiệu hóa `AuditAspect` khi chuyển sang `@Bean`. **Không** khai báo trùng cùng một aspect qua cả `@Component` và `@Bean` nếu không có chủ đích; hai instance có thể tạo advice lặp và gây nhập nhằng khi inject.

## 7. Bật Spring AOP là bước riêng

Đăng ký aspect bean và bật hệ thống AOP là hai bước khác nhau.

Trong Spring Framework thuần, bạn thường dùng:

```java
@Configuration
@ComponentScan("example")
@EnableAspectJAutoProxy
public class AppConfig {
}
```

- `@ComponentScan` tìm những class đủ điều kiện đăng ký bean.
- `@EnableAspectJAutoProxy` kích hoạt xử lý Spring AOP dạng `@AspectJ` và tự động tạo proxy cho bean phù hợp.
- AspectJ Weaver cần có trên classpath để Spring xử lý biểu thức pointcut.
- `@EnableAspectJAutoProxy` **không tự đăng ký** class chỉ có `@Aspect` nằm ngoài bean definitions.

Với ứng dụng **Spring Boot**, khi dependency AOP/AspectJ và auto-configuration tương ứng hoạt động, Boot có thể bật hỗ trợ AspectJ auto-proxy mặc định mà không cần bạn thêm `@EnableAspectJAutoProxy`. Tuy nhiên, vẫn cần **đăng ký aspect làm bean**.

Tên starter thường dùng:

```xml
<!-- Spring Boot 3.x, bên trong <dependencies>; version lấy từ Boot BOM. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

```xml
<!-- Spring Boot 4.x, bên trong <dependencies>; version lấy từ Boot BOM. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aspectj</artifactId>
</dependency>
```

Đây là hai **snippet phụ thuộc theo phiên bản Boot**, không phải một POM hoàn chỉnh và không nên thêm đồng thời chỉ để “chắc chắn”. Boot BOM/parent chịu trách nhiệm giữ dependency Spring/AspectJ tương thích.

### Package scan trong Spring Boot

Giả sử main class đặt tại `com.acme.app.Application`, còn aspect đặt tại `com.acme.infrastructure.AuditAspect`. Component scan mặc định khởi đầu từ package chứa main class và các package con; `com.acme.infrastructure` **không thuộc** phạm vi `com.acme.app`. Việc class có cả `@Aspect @Component` vẫn không làm nó thành bean nếu không quét đúng package.

Hai cách giải quyết thường gặp là đặt aspect vào `com.acme.app.aop` (thuộc phạm vi scan), hoặc cấu hình scan rõ ràng qua `@SpringBootApplication(scanBasePackages = {"com.acme.app", "com.acme.infrastructure"})` khi có lý do tổ chức package. Với ứng dụng lớn, cũng có thể dùng `@Import` hoặc `@Bean` để đăng ký aspect một cách tường minh.

## 8. Những annotation khác không thay thế `@Aspect`

Phân biệt tiếp một số annotation có thể gặp:

| Annotation | Có đăng ký bean không? | Có định nghĩa vai trò aspect không? | Lưu ý |
| --- | --- | --- | --- |
| `@Aspect` | Không tự đăng ký qua scan | **Có** | Cần có aspect bean |
| `@Component` | Có, nếu được scan | Không | Dùng cùng `@Aspect` là cách phổ biến |
| `@Service` | Có, nếu được scan | Không | Dùng cho service nghiệp vụ; cũng là một component |
| `@Repository` | Có, nếu được scan | Không | Dùng cho tầng lưu trữ, có cơ chế exception translation liên quan |
| `@Configuration` | Được Spring nhận diện như configuration class khi đăng ký/quét hợp lệ | Không | Dùng để khai báo `@Bean`/cấu hình context |
| `@Bean` | **Có**, đối với giá trị trả về từ method `@Bean` | Không | Có thể tạo bean từ một class vốn có `@Aspect` |
| `@ComponentScan` | Chỉ thị quét package để tìm ứng viên | Không | Không có nghĩa mọi class trên classpath đều được đăng ký |
| `@EnableAspectJAutoProxy` | Kích hoạt cơ chế Spring AOP auto-proxy | Không tự biến class thành aspect bean | Cần aspect bean, pointcut khớp, target proxy |

`@Aspect` **không phải** một annotation `@Component` được meta-annotate: khác nhau ngay ở nguồn thư viện và trách nhiệm. Ngay cả khi một custom annotation được meta-annotate bằng `@Component`, nó chỉ thay phần **component registration**, không thay phần đánh dấu `@Aspect`.

## 9. Aspect bean không đồng nghĩa với target proxy

Một nhầm lẫn khác: sau khi thêm `@Component`, nhiều người kiểm tra xem **aspect bean** có phải AOP proxy hay không. Spring AOP có một quy tắc riêng:

- Lớp có `@Aspect` **không được Spring auto-proxy như target của các aspect khác**.
- Việc `AopUtils.isAopProxy(context.getBean(AuditAspect.class))` thường trả về `false` là **bình thường**.
- Cần kiểm tra **target bean** (ví dụ `OrderService`) để xác minh proxy và quan sát lời gọi advice.

Ví dụ chẩn đoán trong hàm có `ApplicationContext context`:

```java
// Đoạn minh họa dùng các lớp đã được khai báo ở ví dụ mục 5.
Object aspect = context.getBean(AuditAspect.class);
Object service = context.getBean(OrderService.class);

System.out.println(AopUtils.isAopProxy(aspect));  // false: expected
System.out.println(AopUtils.isAopProxy(service)); // true: nếu pointcut khớp
```

Đừng suy ra `@Aspect` “không hoạt động” chỉ vì **chính aspect bean không phải proxy**.

Ngoài ra, nếu một target được tạo bằng `new OrderService()` ở code bình thường, instance đó không tự động được proxy dù một Spring-managed `OrderService` khác đã có proxy. Đây là giới hạn của **Spring AOP proxy-based**, không liên quan tới việc aspect có `@Component` hay không.

## 10. Chẩn đoán khi aspect không được Spring nhận diện

Khi advice không chạy, kiểm tra từng tầng theo thứ tự để tránh sửa nhầm:

1. **Có aspect bean chưa?** Dùng `context.getBeanNamesForType(AuditAspect.class)`; nếu mảng rỗng, kiểm tra `@Component`/`@Bean`, `@ComponentScan`, package, profile, điều kiện tạo bean và đúng `ApplicationContext`.
2. **Có đánh dấu `@Aspect` đúng trên class không?** Import `org.aspectj.lang.annotation.Aspect`; một component chứa method tên `before` không tự được Spring coi là advice.
3. **Đã bật hỗ trợ AOP chưa?** Kiểm tra `@EnableAspectJAutoProxy` trong Spring Framework thuần, hoặc cấu hình auto-configuration/AspectJ dependency của Spring Boot.
4. **Target có phải bean được proxy không?** Lấy target qua Spring và dùng `AopUtils.isAopProxy(target)`; đừng kiểm tra aspect thay target.
5. **Lời gọi có thực sự đi qua proxy không?** Lời gọi nội bộ `this.method()` trong target bỏ qua advice áp dụng riêng cho method được gọi nội bộ.
6. **Pointcut có match đúng không?** Kiểm tra method, package, signature, annotation và điều kiện khả năng proxy phương thức (ví dụ method `final` không thể bị CGLIB subclass override).
7. **Có aspect bean trùng không?** Nếu đăng ký cùng aspect class qua `@Component` và `@Bean`, hoặc có nhiều cấu hình scan chồng nhau, hãy đọc danh sách bean và đếm số lần advice chạy.

Một kiểm tra gọn với context của ví dụ:

```java
String[] names = context.getBeanNamesForType(AuditAspect.class);
System.out.println(java.util.Arrays.toString(names));

OrderService target = context.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(target));
```

Nếu `names` rỗng, chưa nên chỉ sửa biểu thức pointcut. Nếu có aspect bean và target proxy nhưng advice không hiện, khi đó mới xem pointcut/đường gọi/thứ tự xử lý.

### Bảng tình huống nhanh

| Khai báo | Component scan tìm được aspect bean? | Advice có thể chạy qua Spring AOP? |
| --- | --- | --- |
| Chỉ `@Aspect`, không `@Bean` | **Không** | Không, vì chưa đăng ký aspect bean |
| `@Aspect @Component`, nằm trong package được scan | **Có** | Có, nếu bật AOP và pointcut/target phù hợp |
| `@Aspect @Component`, nằm ngoài package scan | **Không** nếu không có cách đăng ký khác | Không, trừ khi đăng ký bean theo cách khác |
| `@Aspect` + `@Bean` trả về instance aspect | Không cần component scan | Có, nếu bật AOP và target phù hợp |
| Chỉ `@Component`, không `@Aspect` | Có | Không tạo advice theo `@AspectJ` từ class ấy |
| Có aspect bean nhưng không bật AOP | Có | Không có Spring `@AspectJ` auto-proxy tương ứng |
| Có aspect bean, target tự `new` ở ngoài container | Có | Không can thiệp target đó bằng Spring proxy |

## 11. Tự kiểm tra

**Câu 1.** `@Aspect` có làm Spring component scan tự nhận một lớp không?

**Đáp án:** Không. Nếu không có `@Component`/stereotype tương đương hoặc bean definition khác, Spring sẽ không tự đăng ký lớp như một bean chỉ vì `@Aspect`.

**Câu 2.** Tại sao `@Aspect @Component` vẫn có thể không chạy advice?

**Đáp án:** Có thể lớp nằm ngoài phạm vi scan, thiếu hỗ trợ AOP, thiếu AspectJ trên classpath, pointcut không khớp, target không được proxy hoặc lời gọi không qua proxy. Hai annotation chỉ giải quyết hai bước đầu về metadata aspect và việc đăng ký bean (khi scan thực sự diễn ra).

**Câu 3.** Có thể bỏ `@Component` khỏi aspect nhưng vẫn dùng Spring AOP không?

**Đáp án:** Có. Giữ `@Aspect` và đăng ký aspect bằng `@Bean` (hoặc bean definition hợp lệ); bật Spring AOP.

**Câu 4.** `@Service` thay `@Component` trên lớp aspect có được không?

**Đáp án:** Với component scanner, `@Service` cũng là Spring stereotype và có thể đăng ký bean. Tuy vậy, nên chọn `@Component` cho aspect cơ sở hạ tầng để thể hiện trách nhiệm chính xác.

**Câu 5.** Bean aspect đã được đăng ký nhưng `AopUtils.isAopProxy(aspect)` là `false`. Có phải lỗi không?

**Đáp án:** Không. Spring AOP loại aspect class khỏi auto-proxying như target của aspect khác. Hãy kiểm tra proxy của **service target** và việc advice thực thi.

## 12. Tài liệu chính thức

- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html): giải thích rõ `@Aspect` không đủ để autodetect qua classpath; yêu cầu `@Component` hoặc bean definition tương đương và việc aspect không là target auto-proxy.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): cách bật `@EnableAspectJAutoProxy` và yêu cầu classpath.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): stereotype `@Component`, `@Service`, `@Repository` và custom stereotype.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): Spring Boot auto-configuration hỗ trợ AOP và proxy.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): cơ chế proxy và các giới hạn lời gọi.
