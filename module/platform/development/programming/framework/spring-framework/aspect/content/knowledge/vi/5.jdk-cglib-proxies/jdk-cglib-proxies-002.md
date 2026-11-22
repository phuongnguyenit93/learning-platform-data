# Proxy CGLIB dựa trên lớp con của lớp đích trong Spring AOP

## 1. CGLIB proxy của Spring AOP là gì?

Trong Spring AOP, một bean được áp dụng advice có thể được trả về cho client dưới dạng **proxy**. Khi Spring chọn **CGLIB (class-based proxy)**, proxy là một lớp **được sinh tại runtime và kế thừa lớp đích (target class)**, thay vì chỉ triển khai các interface như JDK dynamic proxy.

Ví dụ một bean có kiểu `OrderService`:

```java
public class OrderService {
    public String submit(String id) {
        return "OK:" + id;
    }
}
```

Nếu Spring AOP áp dụng advice cho `submit()` và dùng CGLIB, cấu trúc có thể hình dung:

```text
        Spring ApplicationContext
                  |
                  | cấp bean reference
                  v
       OrderService$$SpringCGLIB$$...
             (proxy subclass)
                  |
                  | extends
                  v
             OrderService
              (target type)

Client --> proxy.submit("A01")
              |
              +--> chạy interceptor/advice phù hợp
              |
              +--> delegate tới target OrderService.submit(...)
              |
              +--> trả giá trị / ném exception cho client
```

Tên class proxy thực tế do Spring sinh và **không phải API ổn định**; đừng kiểm tra proxy bằng cách so khớp chuỗi tên class. Dùng `AopUtils.isCglibProxy(bean)` để quan sát.

Điểm cốt lõi: **proxy có quan hệ kế thừa với target type nhưng Spring AOP vẫn tách ý niệm proxy và đối tượng target**. Khi interceptor tiếp tục lời gọi, thông thường nó ủy quyền việc thực thi nghiệp vụ tới đối tượng target được Spring quản lý. Đừng suy rằng mọi lệnh chạy trong phương thức target đều chạy trên chính object proxy chỉ vì kiểu của proxy là subclass.

**Phạm vi:** giải thích Spring AOP class-based proxy, cách Spring sinh và dùng subclass, lúc nào cấu hình CGLIB, method nào được chặn và các giới hạn thực tế. Không mở rộng sang công nghệ weaving hoặc lý thuyết Aspect tổng quát.

## 2. Vì sao Spring cần proxy dựa trên lớp con?

Spring AOP thường dùng một trong hai loại proxy:

| Tiêu chí | JDK dynamic proxy | CGLIB class-based proxy |
| --- | --- | --- |
| Nền tảng | API proxy của JDK | Bộ sinh subclass được Spring dùng qua `spring-core` |
| Quan hệ kiểu | Triển khai các interface được công bố | Kế thừa lớp target (nếu có thể kế thừa) |
| Target không có business interface | Không đủ interface để cung cấp API nghiệp vụ qua JDK proxy | Thường là lựa chọn cần thiết |
| Có thể gọi qua biến kiểu implementation? | Thường không, vì proxy không phải implementation | Có, vì proxy là subtype của implementation |
| Method không khai báo trong interface | Không gọi được qua interface của JDK proxy | Có thể được chặn nếu method đủ điều kiện proxy và pointcut khớp |
| Giới hạn đặc trưng | Caller chỉ sử dụng interface của proxy | Không thể subclass `final class`; không override `final/private method` |

Nếu target **không triển khai interface**, Spring AOP có thể tạo CGLIB proxy để client vẫn inject/gọi bean theo lớp cụ thể. Nếu target có interface, Spring Framework thuần thường ưu tiên JDK proxy khi chưa yêu cầu target-class proxy. Nhưng ứng dụng có thể **ép CGLIB** ngay cả khi có interface.

Không nên xem CGLIB là phương tiện tự động “chặn mọi lời gọi trong class”. Phạm vi của **Spring AOP vẫn là method execution đi qua Spring proxy**.

## 3. Spring tạo subclass và ủy quyền lời gọi ra sao?

Một sơ đồ lớp giúp phân biệt **lớp proxy** với **target instance**:

```text
   OrderService (lớp Java bạn viết)
      ^
      | extends
      |
   OrderService$$SpringCGLIB$$... (lớp sinh runtime)
      ^
      |
   bean reference mà client nhận từ Spring

   Proxy -- intercept public overrideable method -->
        MethodInterceptor / advisor chain
                |
                +-- proceed --> target instance của OrderService
                |
                +-- kết quả / exception --> client
```

CGLIB sinh subclass để override các method mà nó có thể can thiệp. Trong method override sinh ra, Spring tích hợp logic định tuyến tới AOP interceptor chain. Nếu có advisor/pointcut phù hợp cho method execution hiện tại, advice được thực thi ở ranh giới đó; nếu advice tiếp tục, lời gọi được chuyển tới target.

Đây chỉ là **mô hình khái niệm**, không phải mã nguồn subclass thực tế. Spring dùng các thành phần nội bộ, callback và tối ưu riêng để sinh code; client không phải viết subclass hoặc interceptor bằng tay.

Một `@Around` advice minh họa:

```java
@Around("execution(* com.example.app.service..*.save(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    System.out.println("BEFORE " + pjp.getSignature().getName());
    Object result = pjp.proceed();
    System.out.println("AFTER " + pjp.getSignature().getName());
    return result;
}
```

Đây là **method minh họa** cần được đặt trong Spring bean `@Aspect` và có các import cần thiết. `pjp.proceed()` nghĩa là **tiếp tục qua phần còn lại của interceptor chain**, cuối cùng tới target nếu không bị short-circuit. Nó không có nghĩa “gọi thẳng target và bỏ qua mọi advice khác”.

Nếu method ném exception, exception truyền ngược qua chain; các advice ngoài có thể quan sát, ném lại hoặc xử lý theo hợp đồng của chúng. CGLIB không thay đổi ngữ nghĩa cơ bản này so với JDK proxy.

## 4. Khi nào Spring chọn CGLIB proxy?

### 4.1. Target class không có interface

Một Spring bean được khai báo như sau:

```java
@Service
public class InvoiceService {
    public String createInvoice(String id) {
        return "INV:" + id;
    }
}
```

Nếu advisor áp dụng cho `createInvoice()` và Spring AOP cần tạo proxy, **không có business interface**, Spring có thể dùng CGLIB class-based proxy. Đoạn class này là **mã minh họa**, chưa phải chương trình độc lập vì cần import Spring và context chứa bean.

### 4.2. Chủ động ép class-based proxy

Trong Spring Framework thuần, bật @AspectJ auto-proxy và yêu cầu target-class proxy:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
}
```

Trong XML:

```xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
```

Trong Spring Boot khi phần AOP auto-configuration hoạt động, property thường dùng:

```properties
spring.aop.proxy-target-class=true
```

Boot 3.x dùng class-based proxy làm lựa chọn mặc định cho Spring AOP auto-configuration; có thể chọn `false` để trở về chiến lược dựa trên interface khi bean có interface. **Chỉ riêng `false` không cấm CGLIB** cho bean không có interface.

Spring có thể hợp nhất nhiều cấu hình auto-proxy creator. Một cấu hình `proxyTargetClass=true` ở nơi khác có thể chi phối toàn context; đừng kết luận loại proxy chỉ từ một annotation/property rời rạc.

### 4.3. Không phải mọi bean đều nhận proxy

CGLIB chỉ được dùng trong **ngữ cảnh thực sự tạo proxy**. Một bean không có advisor phù hợp có thể tiếp tục là object thông thường. Sự tồn tại của dependency `spring-aop` hoặc `@EnableAspectJAutoProxy` **không tự chứng minh** mọi bean đều là proxy.

Cũng cần tách biệt **Spring AOP CGLIB proxy** với cơ chế tăng cường class cấu hình `@Configuration(proxyBeanMethods=true)`. Cả hai có thể liên quan đến sinh subclass, nhưng mục đích khác nhau: một bên chặn method execution theo advisor, bên kia điều phối lời gọi giữa các `@Bean` methods. Đừng đánh đồng chúng khi dùng `AopUtils.isAopProxy(...)`.

## 5. Thí nghiệm chạy được: CGLIB subclass, advice và self-invocation

Ví dụ sử dụng **Java 17+, Maven, Spring Framework 6.2.19**. Có một service **không khai báo interface**, hai method nghiệp vụ thường và một method `final`. Một aspect advice cả `quote()` và `finalStatus()`, nhưng CGLIB chỉ có thể chặn lời gọi tới method có thể override.

Kết quả cho thấy:

1. Bean do Spring cấp đúng là Spring AOP CGLIB proxy.
2. Client có thể giữ bean bằng **kiểu lớp cụ thể** `PricingService`.
3. Lời gọi client → proxy → `quote()` chạy advice trước target.
4. `process()` ở target gọi `this.quote("INNER")`; lời gọi **không quay lại proxy**, nên không chạy advice `quote()` lần hai.
5. `finalStatus()` không được subclass override, nên không có advice dù pointcut ghi rõ tên method đó. Đây không phải lời hứa chung cho các proxy công nghệ khác.

Cấu trúc project:

```text
spring-cglib-proxy/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CglibProxyDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cglib-proxy</artifactId>
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
                    <mainClass>demo.CglibProxyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/java/demo/CglibProxyDemo.java`:**

```java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class CglibProxyDemo {
    public static class PricingService {
        public String quote(String code) {
            System.out.println("TARGET quote " + code);
            return "PRICE:" + code;
        }

        public void process() {
            System.out.println("TARGET process");
            this.quote("INNER");
        }

        public final void finalStatus() {
            System.out.println("FINAL status");
        }
    }

    @Aspect
    public static class TraceAspect {
        @Before(
            "execution(* demo..*.quote(..)) || " +
            "execution(* demo..*.finalStatus(..))"
        )
        public void beforeCall(JoinPoint joinPoint) {
            System.out.println("ADVICE " + joinPoint.getSignature().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class Config {
        @Bean
        public PricingService pricingService() {
            return new PricingService();
        }

        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            PricingService service = context.getBean(PricingService.class);

            System.out.println("AOP_PROXY=" + AopUtils.isAopProxy(service));
            System.out.println("CGLIB_PROXY=" + AopUtils.isCglibProxy(service));
            System.out.println("IS_PRICING_SERVICE="
                    + (service instanceof PricingService));

            System.out.println("=== OUTSIDE CALL ===");
            System.out.println("RESULT=" + service.quote("OUTER"));

            System.out.println("=== SELF INVOCATION ===");
            service.process();

            System.out.println("=== FINAL METHOD ===");
            service.finalStatus();
        }
    }
}
```

Chạy ở thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Các dòng stdout do chính chương trình in theo thứ tự** (Maven/Spring có thể phát sinh logging riêng):

```text
AOP_PROXY=true
CGLIB_PROXY=true
IS_PRICING_SERVICE=true
=== OUTSIDE CALL ===
ADVICE quote
TARGET quote OUTER
RESULT=PRICE:OUTER
=== SELF INVOCATION ===
TARGET process
TARGET quote INNER
=== FINAL METHOD ===
FINAL status
```

Giải thích các dấu vết:

- `@EnableAspectJAutoProxy(proxyTargetClass=true)` yêu cầu target-class proxy cho bean được advice.
- `@Bean TraceAspect` khiến aspect thực sự là Spring bean; `@Aspect` đơn lẻ không đủ để container tự đăng ký class.
- Proxy của `PricingService` là subclass, do đó đối tượng được trả qua `getBean(PricingService.class)` là instance của `PricingService`.
- Khi client gọi `quote("OUTER")` trên proxy, `@Before` chạy trước target method, rồi kết quả target trả về được in tại client.
- Khi target thực thi `process()` và gọi `this.quote("INNER")`, lời gọi trực tiếp trên target **bỏ qua proxy**, nên không có dòng `ADVICE quote` cho `INNER`.
- Method `finalStatus()` được khai báo `final`, không thể bị CGLIB subclass override; nó chạy trực tiếp và **không** xuất hiện `ADVICE finalStatus`. Method này cố tình **không dùng instance fields** để tránh một vấn đề quan trọng của final method trên proxy được nêu ở phần sau.

Cơ chế giới hạn CGLIB ở đây là một thuộc tính của **Spring AOP proxy-based interception**, không phải của cú pháp pointcut. Dù pointcut có khớp lời khai báo method, không có interceptor hook ở một method không thể override.

## 6. Những method nào CGLIB proxy có thể chặn?

| Thành phần trong target class | Có thể được Spring AOP CGLIB advice? | Lý do |
| --- | --- | --- |
| `public` method không `final` | Có, nếu lời gọi qua proxy và pointcut khớp | Proxy subclass có thể override |
| `protected` method không `final` | Có thể, tùy điểm gọi và pointcut | Proxy có khả năng override method visible |
| Package-private method | Có thể nếu method visible đối với subclass và phù hợp với framework | Visibility có thể giới hạn override |
| `final` instance method | **Không** | Subclass không thể override |
| `private` method | **Không** | Method private không được kế thừa/override |
| Method trong `final class` | **Không thể dựng CGLIB subclass** | Class `final` không thể bị kế thừa |
| `static` method | Không phải method execution được chặn theo kiểu instance proxy | Static call không dispatch qua instance override |
| Constructor | Không | Spring AOP không advice constructor execution bằng proxy |
| Method target tự gọi bằng `this` | **Không có lần intercept mới** | Lời gọi không đi vào proxy |
| Method gọi trên đối tượng tạo bằng `new` ở ngoài container | Không tự được Spring AOP advice | Không có Spring proxy tham gia |

Với method không public, phải kiểm tra **visibility thực tế, biểu thức pointcut, kiểu proxy và phiên bản Spring**. Spring có khả năng xử lý một số lời gọi protected/package-visible qua CGLIB, nhưng thiết kế service thông thường nên đặt điểm cắt bên ngoài ở các phương thức public rõ ràng.

### 6.1. Vì sao `final class` là vấn đề?

Ví dụ:

```java
public final class FinalReportService {
    public void generate() {
        System.out.println("generated");
    }
}
```

Java không cho class khác `extends FinalReportService`, nên Spring **không thể tạo CGLIB subclass** cho bean đó. Nếu bean bắt buộc phải được proxy bằng class-based proxy, việc tạo proxy có thể thất bại ngay trong quá trình khởi tạo context. Chỉ bỏ `final` khỏi class, thay cách thiết kế bean, hoặc dùng một chiến lược interface-based phù hợp mới giải quyết được nguyên nhân trực tiếp.

**Không suy rằng class có interface sẽ tự được JDK proxy nếu cấu hình đang ép CGLIB.** Cần xem chế độ proxy thực sự có hiệu lực.

### 6.2. Vì sao `final method` đặc biệt nguy hiểm với trạng thái instance?

Một CGLIB AOP proxy thường giữ một **target object riêng**. Với method override được, proxy chuyển execution qua interceptor về target. Với method `final`, subclass không override được, nên client gọi method đó **trên proxy instance trực tiếp**.

Điều này có thể tạo khác biệt về **instance fields** nếu mã final method truy cập trạng thái khởi tạo trong constructor của target: đừng mặc định final method trên proxy sẽ thấy cùng state như method đã delegate vào target. Mô hình dễ gặp:

```java
class StatefulService {
    private String token;

    StatefulService() {
        token = "READY";
    }

    public final String token() {
        return token;
    }
}
```

Đây là **mã phân tích rủi ro, không phải chương trình standalone**. Spring thường tạo proxy instance qua **Objenesis** để không phải chạy constructor của target lần thứ hai. Vì vậy, dữ liệu instance field trên proxy ở method `final` có thể không phải dữ liệu của target. Không dùng việc gọi final method trên CGLIB proxy làm hợp đồng tin cậy.

Cách an toàn hơn là để method cần Spring AOP chặn có thể override, tránh class `final` trong target cần proxy, hoặc định vị hành vi cần chặn ở interface/service khác với chiến lược proxy phù hợp.

### 6.3. `private` và `static` method

`private` method thuộc phạm vi trực tiếp của class, không được override; Spring AOP CGLIB không có cách thay nó bằng method override của proxy. `static` method liên kết với class thay vì dispatch qua instance; đặt annotation lên static method cũng không làm nó trở thành join point Spring AOP mà proxy chặn.

Muốn có advice tại ranh giới nghiệp vụ, đặt hành vi cần can thiệp trên method phù hợp của Spring-managed bean và gọi method đó qua proxy.

## 7. Proxy subclass vẫn có self-invocation

Đây là điểm dễ gây nhầm khi nghe rằng CGLIB “kế thừa target class”.

```text
Client ------------------> CGLIB proxy
                              |
                           intercept
                              |
                              v
                         target.outer()
                              |
                              | this.inner()
                              v
                         target.inner()
                     (không quay về proxy)
```

Khi target đã thực thi `outer()`, tham chiếu `this` trong target trỏ tới target; lời gọi `this.inner()` đi thẳng qua dispatch bình thường của object đó, không trở lại entry point của proxy.

Đặt `proxyTargetClass=true` **không tự giải quyết** self-invocation, kể cả `inner()` là public và có pointcut phù hợp. Điều này ảnh hưởng trực tiếp các cơ chế dùng Spring AOP như `@Transactional`, `@Cacheable` và các application advice.

### Cách thiết kế để lời gọi đi qua proxy

Thông thường nên tách method cần advice sang một Spring bean chuyên trách, rồi inject bean đó:

```java
@Service
public class PriceCalculator {
    @Transactional
    public void calculateAndSave() {
        // xử lý được áp transaction khi gọi qua proxy
    }
}

@Service
public class OrderProcessor {
    private final PriceCalculator calculator;

    public OrderProcessor(PriceCalculator calculator) {
        this.calculator = calculator;
    }

    public void processOrder() {
        calculator.calculateAndSave(); // gọi qua bean reference do Spring inject
    }
}
```

Đây là **mẫu thiết kế minh họa**, cần import, context có transaction management và database/transaction manager phù hợp để áp dụng thật. Mấu chốt là `OrderProcessor` sử dụng bean reference do Spring cấp, nên lời gọi có thể đi qua proxy `PriceCalculator`.

Kỹ thuật self-injection hoặc `AopContext.currentProxy()` với `exposeProxy=true` tồn tại nhưng làm code phụ thuộc chi tiết Spring AOP; thường chỉ nên dùng khi không thể refactor ranh giới bean.

## 8. Constructor: CGLIB proxy có gọi constructor hai lần không?

Spring Framework hiện đại thường dùng **Objenesis** để tạo proxy object mà không cần gọi constructor của target thêm lần nữa. Do đó, trường hợp bình thường **không có hai lần chạy constructor của target** chỉ vì có CGLIB AOP proxy.

Ví dụ quan sát sai thường thấy:

```java
public class DocumentService {
    public DocumentService() {
        System.out.println("CONSTRUCTOR");
    }

    public void generate() {
        System.out.println("GENERATE");
    }
}
```

Không nên mặc định đầu ra luôn có hai dòng `CONSTRUCTOR` khi Spring tạo CGLIB proxy. Trong một số môi trường JVM hạn chế constructor bypass, Spring có thể fallback và sinh thêm constructor call cùng debug log; đây là trường hợp ngoại lệ được tài liệu Spring nêu.

**Hệ quả thực tế:** constructor nên làm công việc khởi tạo thuần túy, tránh phụ thuộc vào sự tồn tại của proxy hoặc advice tại thời điểm constructor chạy. Spring AOP không dùng proxy để advice các method được gọi trong constructor trước khi bean proxy sẵn sàng.

## 9. Module system và khả năng kế thừa class

CGLIB cần sinh subclass và truy cập các method/class của target. Vì vậy, với Java Platform Module System (JPMS), Java access rules có thể ngăn proxy một số class hoặc package.

Ví dụ thường được Spring nêu: tạo class-based proxy cho class trong package `java.lang` khi triển khai theo module path có hạn chế mạnh; việc mở package bằng tham số như:

```text
--add-opens=java.base/java.lang=ALL-UNNAMED
```

chỉ có ý nghĩa trong những cấu hình JVM phù hợp, và không thể tùy tiện dùng để mở package cho một named module theo cách tương tự. Đừng thêm JVM flag đại trà khi chưa có lỗi cụ thể và chưa xác định target package, module boundary, kiểu deployment.

Đối với service class của ứng dụng, kiểm tra class có `final` hay không, các method có thể override hay không, phạm vi truy cập package/module và kiểu classloader nếu Spring báo lỗi tạo CGLIB subclass.

## 10. CGLIB proxy và kiểu của bean khi inject

Một lợi thế dễ quan sát của class-based proxy là bean có thể được inject theo **concrete class**:

```java
@Service
public class CustomerService {
    public String find(String id) {
        return "CUSTOMER:" + id;
    }
}

@RestController
public class CustomerController {
    private final CustomerService customerService;

    public CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }
}
```

Đây là **mã minh họa cần Spring Boot Web imports và method handler phù hợp**. Nếu Spring AOP tạo CGLIB proxy cho `CustomerService`, proxy là subclass của `CustomerService`, nên về mặt kiểu có thể được cấp cho field/constructor parameter `CustomerService`.

Khi đổi sang JDK dynamic proxy, bean thường chỉ công bố interface, và nơi inject implementation class có thể thất bại. Để giảm phụ thuộc loại proxy, thiết kế interface nghiệp vụ rõ ràng khi phù hợp; nhưng nếu ứng dụng thực sự cần dùng class-based proxy, hãy bảo đảm class được kế thừa hợp lệ.

Lưu ý: **khả năng inject theo concrete class không phải bằng chứng bean chắc chắn đã được advice**. Bean thông thường cũng có kiểu concrete; xác minh bằng `AopUtils.isCglibProxy(bean)`.

## 11. Cách kiểm tra loại proxy thật khi chạy

Nếu đã có `ApplicationContext` và class service phù hợp:

```java
Object bean = context.getBean(PricingService.class);

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(bean instanceof PricingService);
```

Đây là **đoạn bổ sung** cho ví dụ runnable ở mục 5. Với cấu hình CGLIB và target bean được advice như ví dụ, các dòng là:

```text
true
true
false
true
```

Không dùng `bean.getClass() == PricingService.class` để kiểm tra target type: lớp proxy là subclass sinh động, nên so sánh class chính xác có thể cho `false`. Khi cần class đích, Spring cung cấp các tiện ích như `AopUtils.getTargetClass(bean)`. Tuy vậy, việc lấy target thật từ proxy hoặc can thiệp trực tiếp thường không cần trong code nghiệp vụ.

Trong ứng dụng có nhiều auto-proxy creator hoặc proxy đặc biệt, **kết quả runtime là bằng chứng chính**. Đừng suy loại proxy từ tên starter hoặc chỉ một property khi không biết config có hiệu lực.

## 12. Những nhận định sai thường gặp

| Nhận định | Thực tế trong Spring AOP |
| --- | --- |
| “CGLIB tạo một object giống target, không có quan hệ kiểu.” | Proxy là subclass của target class (khi tạo subclass hợp lệ). |
| “CGLIB có thể chặn mọi method trong class.” | Không: `final`, `private`, `static` và những method không đủ điều kiện đều có giới hạn. |
| “Đổi từ JDK sang CGLIB thì `this.inner()` được advice.” | Không: self-invocation vẫn bỏ qua proxy. |
| “Dùng CGLIB thì constructor target sẽ chạy hai lần.” | Spring thường dùng Objenesis để tránh constructor thứ hai; trường hợp fallback là ngoại lệ. |
| “CGLIB proxy không khác target instance.” | Cần phân biệt proxy object và target object; trạng thái method final có thể đặc biệt nguy hiểm. |
| “Class `final` vẫn ổn nếu pointcut chỉ match method public.” | Không thể subclass `final class` bằng CGLIB. |
| “Có dependency Spring AOP thì mọi service đều là CGLIB proxy.” | Chỉ những bean cần proxy và đủ điều kiện mới được auto-proxy. |
| “Kiểm tra tên lớp chứa `CGLIB` là phương pháp đáng tin.” | Dùng `AopUtils.isCglibProxy(bean)`; tên lớp runtime không phải contract. |
| “CGLIB bắt buộc thêm dependency riêng.” | CGLIB đã được Spring repackaged trong `spring-core` cho cơ chế proxy này. |
| “Mọi loại subclass do Spring tạo đều là Spring AOP CGLIB proxy.” | Subclass cho `@Configuration` và class-based AOP proxy phục vụ mục đích khác nhau. |

## 13. Checklist xử lý sự cố

1. **Bean có thực sự do Spring quản lý?** Đảm bảo caller dùng bean được inject/lấy từ context thay vì `new` đối tượng trực tiếp.
2. **Có advisor phù hợp không?** Nếu không có advisor, một bean thông thường không nhất thiết bị proxy.
3. **Cấu hình target-class proxy đã hiệu lực chưa?** Kiểm tra `@EnableAspectJAutoProxy(proxyTargetClass=true)`, `spring.aop.proxy-target-class` và cấu hình AOP/transaction khác.
4. **Class có `final` không?** Nếu có, Spring không tạo được CGLIB subclass cho class đó.
5. **Method có `final/private/static` không?** Nếu có, không kỳ vọng Spring AOP advice method bằng cơ chế override.
6. **Có self-invocation không?** Kiểm tra lời gọi `this.method()` bên trong target; đó không phải một lần gọi mới đi qua proxy.
7. **Java visibility và module permissions hợp lệ không?** Xem package access, inherited package-private method, module path và exception khi tạo subclass.
8. **Có truy cập instance state trong final method không?** Nếu có, kiểm tra rủi ro object proxy khác target state; ưu tiên thiết kế lại ranh giới.
9. **Loại proxy lúc chạy là gì?** Dùng `AopUtils.isAopProxy` / `isCglibProxy` / `isJdkDynamicProxy` và kiểm tra điểm gọi thực tế.
10. **Aspect đã đăng ký chưa?** Class `@Aspect` phải là Spring bean, và cơ chế @AspectJ auto-proxy cần được bật phù hợp.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Target `InventoryService` không implements interface, có một method public `reserve()` và một Spring AOP advisor khớp method đó. Proxy dự kiến là loại nào?  
**Đáp án:** CGLIB class-based proxy vì không có interface nghiệp vụ phù hợp cho JDK proxy.

**Câu 2.** Target implements interface, nhưng đặt `proxyTargetClass=true`. Proxy dự kiến là gì?  
**Đáp án:** CGLIB, miễn target class đủ điều kiện tạo subclass và không có cấu hình/ngoại lệ khác làm thay đổi kết quả.

**Câu 3.** Vì sao gọi `this.reserve()` bên trong `InventoryService` không chạy advice trên `reserve()`, dù Spring đang dùng CGLIB?  
**Đáp án:** Lời gọi nội bộ thực hiện trên target, không quay lại proxy. CGLIB không tự chèn advice vào bytecode target.

**Câu 4.** Tại sao `final void status()` không được advice bởi CGLIB?  
**Đáp án:** Subclass sinh runtime không thể override một method `final`.

**Câu 5.** Có thể dùng `AopUtils.isCglibProxy(bean)` để kiểm chứng bean được Spring AOP proxy bằng CGLIB không?  
**Đáp án:** Có. Nhưng còn phải kiểm tra method cụ thể và đường đi lời gọi để biết advice có chạy hay không.

**Câu 6.** Constructor in một dòng và bean được CGLIB proxy. Có luôn in hai dòng không?  
**Đáp án:** Không. Spring hiện đại thường dùng Objenesis, nên target constructor không bị gọi hai lần trong điều kiện thông thường.

**Câu 7.** Một method `final` đọc instance field gán từ constructor; có nên tin rằng nó luôn đọc cùng dữ liệu target trên CGLIB AOP proxy?  
**Đáp án:** Không. Final method không được delegate theo interceptor như method override được; proxy và target có thể có state instance khác nhau.

## 15. Tài liệu Spring Framework

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): lựa chọn JDK/CGLIB, final/private, Objenesis, module system và self-invocation.
- [Spring Framework — Introduction to Spring AOP](https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html): quan hệ proxy với target và giới hạn method execution.
- [Spring Framework — Using ProxyFactoryBean](https://docs.spring.io/spring-framework/reference/core/aop-api/pfb.html): tạo proxy cho class và nguyên lý subclass delegate.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): method matching khi dùng CGLIB trong Spring AOP.
