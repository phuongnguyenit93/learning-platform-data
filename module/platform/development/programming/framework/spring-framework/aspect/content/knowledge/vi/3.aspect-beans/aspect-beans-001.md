# Khai báo lớp @Aspect và đưa vào Spring container

## 1. Kết quả cần đạt

Trong Spring AOP, khai báo một lớp với `@Aspect` mới **mô tả** rằng lớp đó có thể chứa pointcut và advice; để Spring AOP thực sự sử dụng lớp ấy, Spring phải **biết đến instance của aspect như một bean** trong `ApplicationContext` có bật hỗ trợ `@AspectJ`.

Sau bài học, bạn cần làm được ba việc độc lập:

1. Viết một lớp `@Aspect` có advice hợp lệ.
2. Đăng ký lớp đó thành **Spring bean**, thường bằng `@Component` và component scanning, hoặc bằng `@Bean` trong `@Configuration`.
3. Bật hỗ trợ Spring AOP và kiểm tra lời gọi phương thức trên **bean đích** có đi qua proxy để kích hoạt advice.

Đây là bài về **cách Spring phát hiện, tạo và quản lý aspect bean**. Chỉ sử dụng lượng kiến thức pointcut/advice cần để chứng minh việc đăng ký hoạt động; phần lý thuyết Aspect tổng quát không thuộc phạm vi bài này.

## 2. `@Aspect` là gì đối với Spring container?

Hãy phân biệt ba vai trò thường gặp:

| Thành phần | Annotation / cách khai báo | Điều Spring làm |
| --- | --- | --- |
| **Aspect class** | `@Aspect` từ `org.aspectj.lang.annotation.Aspect` | Khi lớp là bean trong context có hỗ trợ `@AspectJ`, Spring đọc các pointcut/advice của nó để tạo các advisor |
| **Aspect bean** | `@Component` + được scan, hoặc khai báo `@Bean`, XML, bean definition | Container tạo/cung cấp instance aspect, thực hiện dependency injection và quản lý lifecycle tương ứng |
| **Target bean** | Ví dụ `@Service`, `@Repository`, `@Bean` | Nếu method khớp advisor và có thể proxy, Spring trả về AOP proxy cho caller để advice có cơ hội chạy |

Điểm quan trọng:

- `@Aspect` **không phải** stereotype của Spring như `@Component`; chỉ đánh dấu `@Aspect` **không đủ** để component scanner đưa lớp vào container.
- `@Component` đưa lớp vào diện được scan (nếu package nằm trong phạm vi scan); bản thân `@Component` **không bật** AOP và không làm Spring hiểu lớp là aspect nếu thiếu `@Aspect`.
- `@EnableAspectJAutoProxy` bật bộ phận Spring AOP nhận diện aspect beans, tạo advisor và auto-proxy những target beans phù hợp. Nó **không tự scan** mọi lớp nằm ngoài bean definitions.
- Với Spring Framework thông thường, `org.aspectj:aspectjweaver` phải có trong classpath cho xử lý biểu thức `@AspectJ`. Tên thư viện không đồng nghĩa với việc ứng dụng đang chạy load-time weaving: cơ chế minh họa ở đây vẫn là **Spring AOP proxy**.

Luồng hoạt động:

```text
Lớp @Aspect
    |
    +-- @Component + component scan --------+
    |                                       |
    +-- @Bean / khai báo bean khác ---------+--> aspect bean trong ApplicationContext
                                                  |
                             @EnableAspectJAutoProxy / Boot AOP auto-configuration
                                                  |
                                             nhận diện advice
                                                  |
                                        tạo advisor và xét target beans
                                                  |
Caller --> target Spring bean proxy --> advice --> target method
```

Nếu thiếu một trong các bước **đăng ký aspect** hoặc **bật hỗ trợ AOP**, việc annotation `@Before` nằm trong mã nguồn không tự khiến lời gọi nghiệp vụ bị chặn.

## 3. Cách 1: `@Aspect` kết hợp `@Component`

Đây là cách thông dụng khi dự án tổ chức các aspect như các lớp thuộc package được Spring quét:

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
        System.out.println("[audit] before submit");
    }
}
```

- `@Aspect`: cho phép Spring nhận diện điểm khai báo advice khi instance đã là bean.
- `@Component`: cho phép component scanner đăng ký `AuditAspect` như một Spring bean.
- `@Before(...)`: phương thức advice chạy trước lời gọi `OrderService.submit(..)` đi qua AOP proxy và khớp pointcut.

`@Aspect` và `@Component` làm hai nhiệm vụ khác nhau. Đừng giả định `@Aspect` tự tìm được lớp, ngay cả khi package được scan.

Ví dụ ở đây dùng `@Component`; một custom stereotype được meta-annotate đúng cách bằng `@Component` cũng có thể làm nhiệm vụ đăng ký.

## 4. Ví dụ chạy được với Spring Framework thuần và Java 17+

Ví dụ này trình bày toàn bộ chuỗi **khai báo aspect → component scan → dependency injection → kích hoạt proxy → lời gọi nhận advice**. Cấu hình sử dụng Spring Framework 6.2.x, và không yêu cầu Spring Boot.

### 4.1. Cấu trúc dự án

```text
spring-aspect-bean-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── AuditSink.java
    ├── AuditAspect.java
    ├── OrderService.java
    └── Main.java
```

### 4.2. `pom.xml`

Dùng cùng phiên bản Spring Framework cho `spring-context` và `spring-aop`; ví dụ chọn 6.2.19. Đối với ứng dụng thực tế, nên để Spring BOM hoặc Spring Boot quản lý phiên bản thay vì ghim tùy tiện từng module.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aspect-bean-demo</artifactId>
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

### 4.3. Spring bean được inject vào aspect

**`AuditSink.java`**

```java
package example;

import org.springframework.stereotype.Component;

@Component
public class AuditSink {
    public void record(String event) {
        System.out.println("[audit] " + event);
    }
}
```

**`AuditAspect.java`**

```java
package example;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(* example.OrderService.submit(..))")
    public void beforeSubmit() {
        sink.record("before submit");
    }
}
```

**`OrderService.java`**

```java
package example;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public void submit(String orderId) {
        System.out.println("order submitted: " + orderId);
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
            AuditAspect aspect = context.getBean(AuditAspect.class);
            OrderService service = context.getBean(OrderService.class);

            System.out.println("aspect bean exists: " + (aspect != null));
            System.out.println("service is proxy: " + AopUtils.isAopProxy(service));
            System.out.println("aspect is proxy: " + AopUtils.isAopProxy(aspect));

            service.submit("A-100");
        }
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
```

Các dòng do chương trình trên in ra:

```text
aspect bean exists: true
service is proxy: true
aspect is proxy: false
[audit] before submit
order submitted: A-100
```

Diễn giải chính xác:

1. `AnnotationConfigApplicationContext` tải `AppConfig`.
2. `@ComponentScan` tìm các lớp có Spring stereotype trong package `example`. Nhờ `@Component`, `AuditAspect` trở thành bean; `AuditSink` và `OrderService` cũng thành bean.
3. Spring inject `AuditSink` vào constructor của `AuditAspect`. Vì aspect là bean nên nó có thể dùng constructor injection như các bean Spring khác.
4. `@EnableAspectJAutoProxy` kích hoạt Spring AOP auto-proxy, nhận diện aspect có `@Aspect` và advice khớp `OrderService.submit(..)`.
5. Spring cung cấp proxy cho `OrderService`. Khi client gọi `service.submit("A-100")`, advice chạy trước rồi mới vào method nghiệp vụ.
6. `aspect is proxy: false` là kết quả **đúng**: Spring AOP loại các `@Aspect` bean khỏi việc auto-proxy bởi aspect khác; aspect bean **không cần phải là AOP proxy** để advice do nó khai báo chạy.

Đối với ứng dụng có log framework, dòng log của framework có thể xuất hiện ngoài những dòng ví dụ; các dòng trên là kết quả từ các `System.out.println` trong mã.

## 5. Cách 2: Khai báo `@Bean` trong `@Configuration`

Không phải lúc nào lớp aspect cũng phù hợp để đánh dấu `@Component`. Khi cần cấu hình tường minh, tạo aspect bằng factory method `@Bean` rất hữu ích.

**Cách chuyển ví dụ mục 4 sang `@Bean`:** bỏ riêng annotation `@Component` khỏi `AuditAspect` (vẫn giữ `@Aspect` và constructor), sau đó thay toàn bộ `AppConfig.java` bằng:

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
    public AuditAspect auditAspect(AuditSink sink) {
        return new AuditAspect(sink);
    }
}
```

Phần còn lại trong mục 4 giữ nguyên; chạy lệnh Maven tương tự và nhận các dòng kết quả tương đương.

Giải thích:

- `@Bean` khiến **giá trị trả về từ `auditAspect(...)`** được Spring đăng ký và quản lý.
- Tham số `AuditSink sink` được resolve từ container rồi truyền vào constructor aspect.
- Không cần đặt `@Component` trên `AuditAspect`: Spring nhận diện `@Aspect` trên **class của bean** đã đăng ký.
- Tránh vừa để `@Component` quét `AuditAspect`, vừa tạo thêm `@Bean AuditAspect` mà không chủ ý; điều này có thể tạo **hai aspect beans**, dẫn tới advice chạy trùng và ambiguity khi inject theo kiểu. Nếu có nhiều bean cùng kiểu thì `getBean(AuditAspect.class)` có thể ném `NoUniqueBeanDefinitionException`.

**Cần phân biệt:** `new AuditAspect(sink)` bên trong một `@Bean` factory method là hợp lệ vì **instance trả về được Spring đăng ký**. Ngược lại, tự `new AuditAspect(...)` trong code ứng dụng mà không đưa instance đó vào container **không đăng ký** aspect với Spring AOP.

### 5.1. Khai báo aspect bean bằng XML

Trong ứng dụng Spring XML cũ, một class chỉ có `@Aspect` có thể được khai báo bằng bean definition:

```xml
<!-- Đoạn minh họa nằm trong phần tử <beans> có khai báo namespace aop. -->
<bean id="auditAspect" class="example.AuditAspect">
    <constructor-arg ref="auditSink"/>
</bean>

<aop:aspectj-autoproxy/>
```

Ở cách này, `auditSink` cũng phải được khai báo là bean. `<aop:aspectj-autoproxy/>` là cách bật Spring AOP proxy tương đương với Java configuration; XML snippet trên không phải một file XML độc lập. Phần lớn ứng dụng mới dùng Java configuration hoặc Spring Boot.

## 6. Nếu sử dụng Spring Boot

Với Spring Boot, `@SpringBootApplication` kết hợp component scanning từ package của application class; nếu lớp `@Aspect` nằm trong phạm vi scan và có `@Component`, nó được đăng ký giống một bean bình thường.

Ví dụ đoạn khai báo aspect trong ứng dụng Boot:

```java
package example.app.aop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class RequestAuditAspect {
    @Before("execution(* example.app.service.OrderService.submit(..))")
    public void beforeOrder() {
        System.out.println("[audit] submitting order");
    }
}
```

**Đây là một lớp minh họa để chèn vào ứng dụng Boot hiện có**, giả định có service `example.app.service.OrderService` với phương thức `submit`. Khi chạy thật cần `@SpringBootApplication` nằm trong package cha `example.app` hoặc phải cấu hình `scanBasePackages` thích hợp.

Về dependency:

- **Spring Boot 3.x**: thông thường dùng `org.springframework.boot:spring-boot-starter-aop`.
- **Spring Boot 4.x**: starter này đã được đổi tên thành `org.springframework.boot:spring-boot-starter-aspectj`.
- Dùng starter/BOM phù hợp để đưa `spring-aop` và `aspectjweaver` vào classpath. Không tự chọn hai phiên bản xung đột với Spring Boot BOM.

Khi AspectJ có trên classpath, Spring Boot mặc định có AOP auto-configuration và thường **không cần** tự thêm `@EnableAspectJAutoProxy`. Nếu dự án tắt auto-configuration liên quan hoặc tùy chỉnh `spring.aop.auto=false`, phải rà soát cấu hình trước khi kỳ vọng advice chạy. Mặc định Boot thường chọn **class-based proxies (CGLIB)**; có thể dùng `spring.aop.proxy-target-class=false` để ưu tiên interface-based proxies khi phù hợp.

**Không nhầm hai điều kiện:** Spring Boot tự bật cơ chế AOP không đồng nghĩa nó tự đăng ký mọi class chỉ có `@Aspect`; lớp đó vẫn cần vào container qua `@Component`, `@Bean` hoặc cách đăng ký bean hợp lệ.

## 7. Quản lý aspect bean: phạm vi và đặc điểm

### 7.1. Aspect là bean, nhưng có vai trò đặc biệt

Spring có thể inject dependency vào aspect, áp dụng các callback/lifecycle tương ứng với bean definition và quản lý singleton như bean thông thường. Tuy nhiên, đối với Spring AOP:

- Aspect bean là **nguồn khai báo advisor**, còn proxy thông thường được tạo cho **target bean** phù hợp.
- Spring loại chính các lớp `@Aspect` khỏi việc trở thành target auto-proxy của các aspect khác. Do đó lời gọi lên instance aspect không nên được kỳ vọng kích hoạt advice do aspect khác khai báo.
- Theo mặc định, Spring dùng mô hình **một aspect instance trong một ApplicationContext** (singleton aspect). Các mô hình instantiation đặc biệt như `perthis` và `pertarget` thuộc chủ đề nâng cao, không cần cho bước khai báo cơ bản.

### 7.2. Giữ state an toàn trong aspect

Một singleton aspect thường phục vụ nhiều lời gọi đồng thời từ nhiều bean/threads. Vì vậy:

- Ưu tiên aspect **không giữ mutable state theo từng request** trong field.
- Với thông tin theo từng lời gọi, sử dụng biến cục bộ trong advice, tham số được Spring/AspectJ bind vào advice hoặc abstraction chuyên dụng phù hợp với ngữ cảnh.
- Nếu cần ghi log/sự kiện, inject một bean có trách nhiệm rõ ràng như `AuditSink`, thay vì tích lũy dữ liệu request trong field mutable không đồng bộ.

Ví dụ **không nên** trong singleton aspect:

```java
// Minh họa sai về thiết kế khi chạy đa luồng; không phải chương trình độc lập.
private String currentOrderId; // các request có thể ghi đè lẫn nhau
```

### 7.3. Nhiều ApplicationContext

Một aspect được đăng ký trong một context không có nghĩa nó sẽ advice mọi object trong mọi context của ứng dụng. Cơ chế auto-proxy và phạm vi bean phụ thuộc context nơi nó được cấu hình. Với ứng dụng có context cha/con hoặc nhiều context riêng, hãy xác định **aspect bean** và **target bean** thuộc context nào, proxy creator nào đang vận hành và tham chiếu client nhận được đến từ đâu.

## 8. Những lỗi thường gặp khi khai báo `@Aspect`

| Hiện tượng | Nguyên nhân phổ biến | Cách kiểm tra / sửa |
| --- | --- | --- |
| Lớp có `@Aspect` nhưng advice không chạy | Không có `@Component`/`@Bean`, nên lớp chưa vào context | Tìm bean type `AuditAspect` bằng `context.getBeanNamesForType(...)`; đăng ký rõ ràng |
| Đã có `@Component` nhưng Spring không tìm thấy aspect | Lớp nằm ngoài `@ComponentScan` | Kiểm tra package gốc của `@SpringBootApplication` hoặc `@ComponentScan` |
| Aspect bean tồn tại nhưng target method không nhận advice | Chưa bật Spring AOP hoặc thiếu thư viện, pointcut không khớp, lời gọi bỏ qua proxy | Kiểm tra `@EnableAspectJAutoProxy`/Boot auto-config, `aspectjweaver`, `AopUtils.isAopProxy(target)` |
| Advice chạy hai lần bất ngờ | Hai aspect beans giống nhau cùng được đăng ký bằng `@Component` và `@Bean`, hoặc hai aspect độc lập cùng match | In danh sách bean theo type; kiểm tra cấu hình đăng ký trùng |
| `NoSuchBeanDefinitionException` với aspect | Bean chưa được đăng ký hoặc nằm ở context khác | Kiểm tra điều kiện tạo bean, package scan, profile, context thực tế |
| `NoUniqueBeanDefinitionException` khi inject aspect | Có nhiều aspect beans cùng type | Loại bỏ khai báo trùng hoặc chỉ định bean mong muốn bằng `@Qualifier` |
| `AopUtils.isAopProxy(aspect)` trả về `false` | **Hành vi bình thường**: class `@Aspect` không phải target auto-proxy | Kiểm tra `AopUtils.isAopProxy(targetService)` và kết quả chạy advice |
| Aspect có dependency `null` hoặc thiếu dependency | Tạo object aspect ngoài Spring, không được DI; hoặc bean wiring có lỗi | Để container tạo/inject aspect thông qua `@Component` hoặc `@Bean` |
| Advice không chạy khi service tự gọi `this.inner()` | Self-invocation không đi qua proxy | Gọi qua bean/proxy hoặc tách xử lý sang bean khác |

### Kiểm tra trực tiếp trong context

Đoạn Java sau minh họa cách kiểm tra trong một phương thức có sẵn `ApplicationContext context`:

```java
// Đoạn minh họa, yêu cầu các bean/type tương ứng đã khai báo.
String[] names = context.getBeanNamesForType(AuditAspect.class);
System.out.println(java.util.Arrays.toString(names));

OrderService target = context.getBean(OrderService.class);
System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(target));
```

Với ví dụ mục 4, danh sách thường chứa bean tên `auditAspect`; target có proxy vì pointcut khớp. Kiểm tra `context.containsBean("auditAspect")` chỉ cho biết một tên bean có được đăng ký hay không, không thay cho việc xác minh advice chạy.

## 9. Các tình huống đối chiếu

| Tình huống | `@Aspect` trở thành nguồn advice cho Spring AOP? | Vì sao |
| --- | --- | --- |
| `@Aspect @Component`, package được scan, hỗ trợ AOP đã bật | **Có** | Được đăng ký thành Spring bean và Spring nhận diện metadata aspect |
| Chỉ có `@Aspect`, dù package được scan, không có khai báo bean nào khác | **Không** | `@Aspect` tự nó không phải dấu hiệu component |
| Class `@Aspect` không có `@Component`, nhưng được `@Bean` trả về | **Có** | Instance đã được đăng ký qua factory method |
| `@Component` có method `@Before` nhưng không có `@Aspect` | **Không theo mô hình `@AspectJ` này** | Spring không nhận lớp là `@AspectJ` aspect |
| `@Aspect @Component` nhưng AOP auto-proxy không được bật | **Không tự động có Spring AOP advice** | Có bean nhưng thiếu bước xử lý aspect/proxy |
| Tạo `new MyAspect()` ở ngoài Spring | **Không** | Instance không thuộc tập aspect beans mà proxy creator đọc |
| Aspect bean hợp lệ, target là object tự `new` ngoài container | Aspect **đã đăng ký**, nhưng **target đó không được advice bằng Spring proxy** | Spring AOP chỉ can thiệp lời gọi qua proxy của managed bean |

**Tự kiểm tra:** Nếu đổi `AuditAspect` ở ví dụ chạy được thành chỉ có `@Aspect` và không khai báo `@Bean`, điều gì xảy ra? Spring sẽ không đăng ký `AuditAspect` qua component scan, nên `context.getBean(AuditAspect.class)` không tìm được bean; đoạn chương trình sẽ lỗi tại bước lấy bean và không đến bước gọi `submit`. Nếu bỏ dòng lấy aspect rồi vẫn gọi service, `OrderService` sẽ không nhận advice của lớp aspect chưa đăng ký.

## 10. Nguồn tham khảo Spring chính thức

- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html): `@Aspect`, đăng ký bằng `@Bean` hoặc component scan, lưu ý không auto-proxy aspect bean.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): `@EnableAspectJAutoProxy`, thư viện AspectJ trên classpath và quá trình tạo proxy.
- [Spring Framework — Aspect Instantiation Models](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html): mặc định singleton, các mô hình nâng cao.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): lý do advice cần lời gọi qua proxy và giới hạn self-invocation.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): auto-configuration Spring AOP và lựa chọn proxy.
