# Spring AOP: tự tiêm tham chiếu proxy và các phụ thuộc phát sinh

## 1. Vì sao có khái niệm self-injection?

Spring AOP là **proxy-based AOP**. Spring tạo proxy cho những Spring-managed beans cần được advisor/advice áp dụng. Khi bean khác gọi một method **qua proxy**, advice có cơ hội chạy. Nhưng khi chính target gọi method của nó qua `this`, cuộc gọi này không đi qua proxy — gọi là *self-invocation*.

```java
@Service
public class ReportService {
    public void generate() {
        this.audit(); // Gọi trên target, không qua Spring AOP proxy.
    }

    public void audit() {
        System.out.println("audit");
    }
}
```

Đoạn này minh họa; chưa phải ứng dụng chạy độc lập. Giả sử Spring có aspect `@Before` cho `audit()`: nếu một consumer gọi `reportService.audit()` qua reference proxy Spring inject, advice có thể chạy. Nhưng `generate()` gọi `this.audit()` trực tiếp nên advice cho `audit()` không chạy. Điều này đúng với cả JDK dynamic proxy lẫn CGLIB trong Spring AOP.

**Self-injection** là kỹ thuật để bean nhận lại reference đến **chính Spring bean** của nó (hy vọng là AOP proxy), rồi chủ động gọi method qua reference đó thay cho `this`:

```java
private ReportOperations self;

public void generate() {
    self.audit(); // Chỉ chạy advice nếu self cuối cùng gọi đúng AOP proxy.
}
```

Đoạn này chỉ minh họa ý tưởng, không có cơ chế inject. Giải pháp này có thể vượt qua self-invocation cho **một lời gọi cụ thể**, nhưng kéo theo quan hệ phụ thuộc vào chính bean đang được khởi tạo. Vì vậy, tài liệu Spring xem self-injection là biện pháp dự phòng; giải pháp thiết kế được ưu tiên là **tách operation cần advice sang một Spring bean khác** rồi gọi qua dependency do Spring inject.

Bài học này chỉ tập trung vào Spring AOP, Spring IoC, proxy, bean lifecycle và các phụ thuộc phát sinh; không bàn luận AOP tổng quát hoặc AspectJ weaving ngoài phạm vi Spring AOP proxy.

## 2. Ba reference dễ bị nhầm

Xét một Spring bean `ReportService implements ReportOperations` có method `generate()` và `audit()`:

1. **Target object:** instance thực sự chứa state và code `ReportService`. Trong target, `this` trỏ tới target.
2. **Spring AOP proxy:** reference mà `ApplicationContext.getBean(ReportOperations.class)` hoặc constructor injection của consumer có thể nhận, khi có advisor phù hợp.
3. **Lazy-resolution proxy:** reference trung gian Spring cấp cho một injection point gắn `@Lazy`; khi caller sử dụng, nó mới tìm dependency thật từ container. Dependency cuối cùng có thể là **Spring AOP proxy**.

```text
Consumer
   |
   v
Spring AOP proxy (ReportOperations)
   |
   v
Target ReportService.generate()
   |
   +-- this.audit()
   |       |
   |       v
   |    Target.audit()          -> KHÔNG đi qua advice
   |
   +-- self.audit()
           |
           v
       @Lazy proxy nếu có
           |
           v
       Resolve dependency trong Spring
           |
           v
       Spring AOP proxy
           |
           +-- advice cho audit(), nếu pointcut khớp
           |
           v
       Target.audit()
```

Điểm mấu chốt: **`@Lazy` injection proxy không đồng nghĩa với AOP proxy**. Chỉ thấy object `self` có dạng proxy không đủ để kết luận có advisor hoặc lời gọi đã chạy advice. Cần kiểm tra bean Spring thực sự được resolve và kết quả method invocation.

Hai kiểu proxy cũng không tự động thay thế lệnh `this.audit()`. Chỉ khi code **đổi sang gọi `self.audit()` trên reference đúng** thì mới có cơ hội đi qua Spring AOP proxy.

## 3. Quy tắc self-injection trong Spring DI

### 3.1. `@Autowired` self reference có thứ tự ưu tiên thấp nhất

Spring Framework cho phép `@Autowired` xét lại chính bean đang được cấu hình như một ứng viên cho dependency. Tuy nhiên, self-injection là một **fallback mechanism**:

- Các dependency/bean ứng viên bình thường được xét **trước** self reference.
- Self reference có **độ ưu tiên thấp nhất**, không phải ứng viên autowire thông thường và không được ưu tiên bằng `@Primary`.
- Với nhiều bean cùng interface, `@Autowired ReportOperations self` có thể không chọn bean hiện tại nếu ứng viên bình thường khác phù hợp.
- Spring cũng có khả năng resolve theo tên trong các tình huống phù hợp; nhưng một field mang tên `self` không nên bị coi là ràng buộc chắc chắn đến bean hiện tại.

Hệ quả: viết một field tên `self` chưa chứng minh đã lấy đúng proxy của chính service. Khi correctness phụ thuộc điều này, cần kiểm tra runtime, xác định bean name/qualifier và viết integration test. Trong thiết kế lâu dài, phụ thuộc vào một collaborator bean thật sẽ rõ ràng hơn.

### 3.2. Vì sao constructor tự inject thường gây cycle?

Ví dụ không nên dùng làm mặc định:

```java
@Service
class ReportService implements ReportOperations {
    private final ReportOperations self;

    ReportService(ReportOperations self) {
        this.self = self;
    }
}
```

Đây là fragment minh họa thiếu các method của interface. Để dựng `ReportService`, Spring phải resolve constructor parameter `ReportOperations`; nếu nó trỏ lại chính bean đó thì bean chưa thể xây dựng xong, tạo một **constructor dependency cycle**. Vòng constructor thông thường không thể khắc phục bằng cơ chế cấp sớm singleton vốn dành cho một số trường hợp field/setter.

Một `@Lazy` đặt **trên constructor parameter** có thể trì hoãn resolution và thay đổi tình huống kỹ thuật, nhưng không làm quan hệ tự phụ thuộc trở thành thiết kế tốt. Không tự inject cùng một kiểu qua constructor chỉ để sửa self-invocation.

### 3.3. Field/setter tự inject không `@Lazy` cũng rủi ro

```java
@Autowired
private ReportOperations self;
```

Tại lúc populate field, target có thể vẫn đang được Spring khởi tạo. Nếu dependency resolve ngay và trỏ lại bean hiện tại, Spring có thể phải xử lý **early bean reference**. Với singleton và một số cấu hình cho phép circular dependency, hạ tầng AOP có thể tham gia bằng `SmartInstantiationAwareBeanPostProcessor.getEarlyBeanReference(...)` để tạo early proxy.

Nhưng:

- Không phải mọi vòng dependency đều được Spring chấp nhận.
- Early reference không phải một lời hứa chung rằng toàn bộ initialization/advice đã sẵn sàng.
- Circular reference với constructor vẫn có những giới hạn riêng.
- Spring Boot từ 2.6 trở đi mặc định không cho phép circular references, trừ khi được cấu hình khác.
- Có thể gặp `BeanCurrentlyInCreationException`, raw-target reference hoặc mismatch với proxy cuối khi thiết kế vòng phức tạp.

Không nên bật `spring.main.allow-circular-references=true` như giải pháp đầu tiên; hãy loại bỏ quan hệ tự phụ thuộc hoặc trì hoãn một dependency có chủ đích khi thật sự cần.

## 4. `@Autowired @Lazy` tại injection point hoạt động thế nào?

Đặt `@Lazy` ở **điểm inject**:

```java
@Service
public class ReportService implements ReportOperations {
    @Autowired
    @Lazy
    private ReportOperations self;

    @Override
    public void generate() {
        this.audit(); // Bypass AOP proxy.
        self.audit(); // Qua lazy-resolution proxy, rồi đến bean do Spring cấp.
    }

    @Override
    public void audit() {
        System.out.println("audit");
    }
}
```

Đây là fragment; ví dụ đầy đủ ở mục 7. Với `@Autowired @Lazy`, Spring tạo **lazy-resolution proxy** và không cần resolve target dependency ngay khi inject field. Khi `self.audit()` chạy lần đầu sau khi bean đã khởi tạo xong, proxy trung gian mới resolve `ReportOperations` từ Spring. Nếu container công bố bean đó dưới dạng AOP proxy và pointcut chọn `audit()`, advice chạy.

**Hai nghĩa của `@Lazy` không giống nhau:**

| Cách đặt | Tác dụng trong Spring |
| --- | --- |
| `@Lazy` trên class `@Service` hoặc method `@Bean` | Yêu cầu trì hoãn **khởi tạo bean** khi có thể |
| `@Lazy` trên field/parameter `@Autowired` | Tạo **lazy-resolution proxy** tại injection point; tìm dependency khi thực sự sử dụng |
| `@Lazy` trên một method business | Không tự bật advice hoặc sửa self-invocation |

Các lưu ý:

- Không gọi `self.audit()` trong constructor, `@PostConstruct` hoặc lúc container chưa có thể cung cấp AOP proxy hoàn chỉnh. Lazy không có nghĩa bean đã initialized.
- Với singleton, lazy proxy thường cache dependency sau lần resolve đầu tiên; với scope khác, cách resolve có thể khác.
- `@Lazy` có thể **trì hoãn cả lỗi cấu hình**: dependency không tồn tại hay không resolve được có thể chỉ lỗi khi lời gọi xảy ra.
- `@Lazy` không bảo đảm aspect được scan, hạ tầng AOP đã bật hoặc pointcut khớp.
- Nếu actual AOP proxy là JDK dynamic proxy, hãy tự inject **interface được proxy thực hiện**; inject concrete class có thể lỗi kiểu hoặc dẫn đến hành vi không mong muốn.
- `@Lazy` không sửa static/private/final method limitations hoặc object do code tự `new`.
- Nếu có nhiều `ReportOperations` bean khác nhau, self-injection fallback có thể chọn một bean khác. Đừng đánh đồng “reference có đúng type” với “reference chính xác của tôi”.

Một lỗi test rất dễ gặp: `AopUtils.isAopProxy(self)` cho kết quả true vì `self` là **injection-point proxy**, không nhất thiết vì underlying bean có Spring AOP advice. Hãy kiểm tra `AopUtils.isAopProxy(context.getBean(ReportOperations.class))` cho bean chính thức và xác nhận các dòng advice in ra từ invocation.

## 5. Những phụ thuộc phát sinh và chi phí thiết kế

### 5.1. Phụ thuộc logic vào lifecycle container

Một method tưởng chỉ gọi business logic nay cần Spring tạo bean, tạo self reference rồi công bố AOP proxy. Gọi sai giai đoạn lifecycle có thể resolve reference khi bean đang được tạo hoặc chưa hoàn tất post-processing.

Ví dụ, không nên gọi self method cần advice từ `@PostConstruct`: callback initialization thường chạy trên target trước khi proxy cuối cùng được công bố. Tốt hơn hãy để operation được gọi từ consumer sau khi context sẵn sàng.

### 5.2. Coupling với Spring DI

Field `@Autowired @Lazy ReportOperations self` là hạ tầng Spring nằm ngay trong class nghiệp vụ. Một unit test đơn giản:

```java
ReportService service = new ReportService();
service.generate();
```

sẽ không nhận field injection của Spring, do đó `self` vẫn null và lời gọi đến nó có thể ném `NullPointerException`. Muốn test phần này phải dùng context hoặc cấu hình dependency thủ công. Đây là chi phí thật so với thiết kế có constructor injection của một collaborator bean độc lập.

### 5.3. Sai dependency khi có nhiều implementation

Giả sử có cả `ReportService implements ReportOperations` và `SpecialReportService implements ReportOperations`. Self-reference không được Spring ưu tiên hơn ứng viên bình thường. Vì thế field tự inject theo interface có thể resolve sang service khác; lời gọi và aspect vẫn chạy, nhưng sai operation hoặc sai state.

Nếu bắt buộc self-inject, phải kiểm tra bean name/type/qualifier trong ứng dụng cụ thể. Tuy nhiên, qualifier và tên bean là thêm một tầng coupling; khi có thể hãy thiết kế hai service có vai trò rõ ràng.

### 5.4. Proxy type ảnh hưởng kiểu của self reference

| Cấu hình AOP | Điểm cần lưu ý |
| --- | --- |
| JDK dynamic proxy | Proxy thực hiện interface, không kế thừa implementation class. Self reference nên dùng interface |
| CGLIB class proxy | Có thể inject theo class khi class có thể subclass; `final`/`private` methods vẫn không được CGLIB advice |
| Spring Framework thuần | `@EnableAspectJAutoProxy(proxyTargetClass=false)` ưu tiên JDK proxy nếu target có interface |
| Spring Boot có AOP auto-config | Thường mặc định class proxy; đặt `spring.aop.proxy-target-class=false` nếu chủ đích ưu tiên interface proxy |

Hai loại proxy đều gặp self-invocation. Đổi loại proxy không khiến `this.audit()` tự quay lại interceptor chain.

### 5.5. Scope làm “self” thiếu ổn định

Với singleton mặc định, một Spring bean reference thường ổn định trong một context. Với prototype/request scope hoặc scoped proxies:

- Mỗi lần container resolve bean có thể tạo target khác hoặc phụ thuộc scope hiện hành.
- Lazy reference có thể resolve theo scope khác; khái niệm “gọi chính instance này” cần kiểm chứng, không suy ra từ tên.
- Khi request scope không tồn tại, lời gọi có thể thất bại.
- Self-reference không tự xử lý thread context hoặc truyền transaction/security state giữa threads.

Không áp một ví dụ singleton cho mọi scope.

## 6. Giải pháp ưu tiên: tách method cần advice sang bean khác

Thay vì `ReportService -> self -> ReportService`, tạo một collaborator bean với một trách nhiệm rõ ràng:

```java
public interface AuditOperations {
    void record(String reportId);
}

@Service
public class AuditService implements AuditOperations {
    @Override
    public void record(String reportId) {
        System.out.println("[audit] " + reportId);
    }
}

@Service
public class ReportService {
    private final AuditOperations audit;

    public ReportService(AuditOperations audit) {
        this.audit = audit;
    }

    public void generate(String reportId) {
        System.out.println("[report] " + reportId);
        audit.record(reportId);
    }
}
```

Đoạn trên minh họa thiết kế; mỗi public type cần file riêng, các class `@Service` cần import `org.springframework.stereotype.Service`, và phải cấu hình Spring AOP/aspect chọn `AuditService.record()`. Consumer gọi `ReportService.generate(...)`, còn method cần advice `record(...)` được gọi **qua dependency do Spring cung cấp**, nên có cơ hội qua AOP proxy.

Điểm mạnh:

1. Tránh vòng phụ thuộc chính nó.
2. Sử dụng **constructor injection** thông thường.
3. Phân tách rõ nơi áp dụng policy/aspect.
4. Kiểm thử service với một fake `AuditOperations` mà không cần Spring container.
5. Không phụ thuộc `@Lazy` trên self field, không phụ thuộc `AopContext.currentProxy()`.
6. Khi đổi JDK/CGLIB, consumer vẫn nên phụ thuộc vào hợp đồng interface.

Không nhất thiết tách mọi helper; nếu advice ở public entry point đã bao trùm toàn bộ operation, hãy giữ private helper nội bộ. Tách bean khi method thật sự cần policy/ràng buộc AOP riêng.

## 7. Ví dụ Java 17 và Spring Framework 6.2 chạy được

Ví dụ dùng Maven, Java 17, Spring Framework 6.2.x, không cần Spring Boot. Có một service `ReportService implements ReportOperations` và aspect `@Before` chỉ chọn method `audit()`. Ta dùng `@Autowired @Lazy` để có self reference mà không resolve ngay trong lúc field injection.

Mục tiêu quan sát: `this.audit()` không chạy advice; `self.audit()` chạy advice sau khi lazy proxy resolve Spring AOP bean; gọi `audit()` trực tiếp trên bean Spring cũng chạy advice.

**Cấu trúc:**

```text
spring-aop-self-injection/
├── pom.xml
└── src/main/java/demo/self/
    ├── AppConfig.java
    ├── ReportOperations.java
    ├── ReportService.java
    ├── AuditAspect.java
    └── Main.java
```

### 7.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-self-injection</artifactId>
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

### 7.2. `AppConfig.java`

```java
package demo.self;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

Spring scan target bean và aspect trong package `demo.self`. Với target có interface và `proxyTargetClass=false`, ví dụ dùng JDK dynamic proxy.

### 7.3. `ReportOperations.java`

```java
package demo.self;

public interface ReportOperations {
    void generate();
    void audit();
}
```

Cả hai public methods nằm trong interface, nên JDK proxy có thể cung cấp cho caller; chỉ `audit()` được aspect dưới đây advice.

### 7.4. `ReportService.java`

```java
package demo.self;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Service
public class ReportService implements ReportOperations {
    @Autowired
    @Lazy
    private ReportOperations self;

    @Override
    public void generate() {
        System.out.println("[service] generate");
        this.audit(); // Không qua Spring AOP proxy.
        self.audit(); // Resolve lazy dependency, gọi Spring AOP proxy.
    }

    @Override
    public void audit() {
        System.out.println("[service] audit");
    }
}
```

Đây là self-injection **có chủ đích để học**, không phải khuyến nghị thiết kế mặc định. Vì `@Lazy` ở injection point, không cần resolve `ReportOperations` ngay khi field đang được inject. Khi `generate()` được gọi sau khi context hoàn tất, lời gọi `self.audit()` resolve bean do Spring công bố.

### 7.5. `AuditAspect.java`

```java
package demo.self;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* demo.self.ReportService.audit(..))")
    public void beforeAudit() {
        System.out.println("[advice] before audit");
    }
}
```

Aspect có `@Component` để Spring đăng ký thành bean. Pointcut sử dụng target class; Spring có thể match method target ngay cả khi caller giữ interface proxy.

### 7.6. `Main.java`

```java
package demo.self;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            ReportOperations service = context.getBean(ReportOperations.class);

            System.out.println("isAopProxy=" + AopUtils.isAopProxy(service));
            System.out.println("isJdkProxy=" + AopUtils.isJdkDynamicProxy(service));

            service.generate();

            System.out.println("[main] direct proxy call");
            service.audit();
        }
    }
}
```

Lệnh biên dịch/chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.self.Main
```

**Stdout từ các lệnh `System.out` trong ví dụ** (không tính log build nếu môi trường phát thêm):

```text
isAopProxy=true
isJdkProxy=true
[service] generate
[service] audit
[advice] before audit
[service] audit
[main] direct proxy call
[advice] before audit
[service] audit
```

Giải thích:

- Hai dòng đầu xác minh bean chính thức lấy từ Spring là AOP proxy và là JDK dynamic proxy trong cấu hình này.
- `service.generate()` đi qua proxy nhưng `generate()` không khớp pointcut; target in `[service] generate`.
- `this.audit()` in `[service] audit` nhưng **không có advice** trước lần đầu.
- `self.audit()` đi qua lazy-resolution proxy đến bean Spring đã có AOP proxy, nên in `[advice] before audit` rồi `[service] audit` lần hai.
- Gọi `service.audit()` trong `Main` cũng đi qua AOP proxy, nên có advice.
- Không cần `exposeProxy=true` trong ví dụ này; self-injection và `AopContext.currentProxy()` là hai kỹ thuật khác nhau.

## 8. Thử nghiệm và các tình huống cần cảnh giác

### 8.1. Bỏ `@Lazy`

Nếu đổi field thành:

```java
@Autowired
private ReportOperations self;
```

Spring có thể phải resolve self reference trong khi target đang được xây dựng, dẫn đến circular dependency hoặc early reference. Ứng dụng Spring Boot với circular references bị cấm có thể thất bại khi khởi tạo. Không có bảo đảm rằng bỏ `@Lazy` vẫn hoạt động trong mọi cấu hình. Hướng xử lý đúng thường là refactor bean.

### 8.2. Đổi `self.audit()` về `this.audit()`

Cả hai lần gọi từ `generate()` sẽ không qua proxy, mặc dù `service.audit()` trong `Main` vẫn chạy advice. Điều này phân biệt **self-invocation** với lỗi pointcut hoặc lỗi đăng ký aspect.

### 8.3. Có thêm implementation thứ hai

Nếu một bean khác cũng triển khai `ReportOperations`, Spring không có quy tắc mặc định “tên field là self thì luôn inject chính tôi”. Self-injection chỉ là fallback; có thể chọn ứng viên thường trước. Khi bắt buộc cần đúng proxy, xác định bean theo tên/qualifier hoặc cân nhắc refactor. Test integration phải chứng minh method chạy trên **đúng bean**.

### 8.4. Bỏ aspect

Nếu bỏ `@Component` trên `AuditAspect` mà không thay bằng `@Bean`, hoặc đổi pointcut không khớp, `self.audit()` vẫn có thể gọi bean Spring nhưng sẽ **không có advice**. Đây không phải lỗi của `@Lazy` mà là không có advisor áp dụng.

### 8.5. Chuyển sang class-based proxy

Trong `AppConfig` thay bằng:

```java
@EnableAspectJAutoProxy(proxyTargetClass = true)
```

Với class không `final`, Spring tạo CGLIB proxy. `isJdkProxy` trong stdout sẽ là `false`, còn việc `this.audit()` bypass và `self.audit()` gọi qua proxy vẫn đúng. Bật CGLIB không xóa ranh giới proxy.

### 8.6. Gọi trong lifecycle callback

Không dùng `self.audit()` trong constructor hay `@PostConstruct` để “tự bật” transaction hoặc audit. Thời điểm đó target có thể chưa trải qua bước auto-proxy cuối cùng; lazy resolution có thể gặp `BeanCurrentlyInCreationException` hoặc reference khác mong đợi. Hãy gọi operation từ Spring-managed consumer sau khi context sẵn sàng.

### 8.7. Dùng `ObjectProvider` thay `@Lazy`

Một phương án resolve theo nhu cầu:

```java
@Service
public class ReportService implements ReportOperations {
    private final ObjectProvider<ReportOperations> provider;

    public ReportService(ObjectProvider<ReportOperations> provider) {
        this.provider = provider;
    }

    @Override
    public void generate() {
        provider.getObject().audit();
    }

    @Override
    public void audit() {
        System.out.println("audit");
    }
}
```

Đây là fragment cần import `org.springframework.beans.factory.ObjectProvider`, `@Service` và type interface đầy đủ. Inject provider không nhất thiết resolve bean ngay, nhưng `getObject()` **không tự bảo đảm** chọn chính bean này khi có nhiều candidates; self-injection vẫn liên quan quy tắc lựa chọn. `ObjectProvider` cũng tăng coupling với DI container. Đây không phải giải pháp được ưu tiên trước refactor.

## 9. So sánh các lựa chọn

| Cách | Khi hữu ích | Giới hạn / rủi ro |
| --- | --- | --- |
| **Tách method sang Spring bean khác và constructor-inject** | Thiết kế chuẩn khi operation cần advice độc lập | Cần phân chia trách nhiệm hợp lý |
| `@Autowired @Lazy` self-reference | Giải pháp tình thế để đi qua proxy nội bộ khi không refactor được | Fallback autowire, lazy proxy ≠ AOP proxy, khó test, lifecycle coupling |
| `@Autowired` self field không lazy | Có thể hoạt động trong vài cấu hình legacy hỗ trợ early singleton reference | Dễ circular dependency, raw bean vs proxy, lỗi lúc khởi tạo |
| Constructor self-injection | Tránh dùng trực tiếp | Constructor dependency cycle; `@Lazy` chỉ trì hoãn chứ không sửa thiết kế |
| `AopContext.currentProxy()` | Giải pháp cuối khi invocation đã qua proxy và có expose | Cần `exposeProxy=true`, Spring-specific, phụ thuộc thread/invocation |
| `ObjectProvider<T>` hoặc `ApplicationContext.getBean(...)` | Khi chủ động cần lookup bean theo thời điểm | Service locator coupling, chọn nhầm bean/ambiguity nếu type không duy nhất |

### `AopContext.currentProxy()` có thay thế self-injection không?

Spring cho phép:

```java
((ReportOperations) AopContext.currentProxy()).audit();
```

nhưng cần đang thực thi trong **invocation qua AOP proxy có `exposeProxy=true`**, ví dụ cấu hình `@EnableAspectJAutoProxy(exposeProxy = true)`. Nếu không có current proxy phù hợp, `AopContext.currentProxy()` ném `IllegalStateException`. Với JDK proxy, phải cast sang interface proxy triển khai, không phải tùy tiện cast sang implementation class.

Cách này ghép business code với Spring AOP; tài liệu Spring khuyên hạn chế và ưu tiên refactor/bean dependency. Nó không làm `private`/`static` methods trở thành interceptable, không sửa lời gọi `this.method()` đã có và không hoạt động trong code được tạo ngoài context.

## 10. Checklist chẩn đoán sự cố

| Triệu chứng | Nguyên nhân/hướng kiểm tra |
| --- | --- |
| `this.inner()` không chạy advice | Đường gọi trên target, bypass Spring proxy; xem có nên tách bean |
| `self.inner()` không chạy advice | Kiểm tra actual bean được lazy resolve, aspect/pointcut, loại AOP proxy |
| `AopUtils.isAopProxy(self)` true nhưng advice không chạy | `self` có thể chỉ là lazy-resolution proxy; kiểm tra bean chính lấy từ context |
| `BeanCurrentlyInCreationException` | Eager self resolution hoặc circular dependency; không dựa vào startup partial bean |
| `NoUniqueBeanDefinitionException`/injection sai bean | Có nhiều implementation, self-injection fallback; kiểm tra name/qualifier |
| `ClassCastException` hay không inject được concrete class | Actual AOP proxy có thể là JDK interface proxy |
| Test bằng `new ReportService()` lỗi NPE | `@Autowired @Lazy` không được inject ngoài Spring container |
| Chạy trong `@PostConstruct` thất bại | Proxy cuối chưa sẵn sàng, tránh gọi self trong init |
| Spring Boot từ chối circular reference | Loại bỏ cycle, đừng bật circular references chỉ để né thiết kế |
| Method `final`/`private`/`static` vẫn không có advice | Giới hạn proxy method; self-injection không vượt khả năng override |
| Có AOP proxy nhưng `audit()` không chạy advice | Kiểm tra pointcut match và method invocation thực sự qua proxy |
| Aspect chỉ có `@Aspect` mà không phải bean | Đăng ký qua `@Component` hoặc `@Bean`, bật Spring AOP |

Thứ tự debug: kiểm tra target/aspect là Spring beans → xác nhận actual Spring AOP proxy (không chỉ lazy proxy) → kiểm tra chọn đúng bean và kiểu interface → xác nhận thời điểm gọi sau initialization → kiểm tra `this` hay `self` → đối chiếu pointcut → refactor nếu có self-cycle không cần thiết.

## 11. Câu hỏi ôn tập

**1. Tại sao `this.audit()` bỏ qua advice?** Vì Spring AOP proxy chỉ chặn lời gọi đi qua reference proxy; `this` ở trong target gọi trực tiếp target.

**2. `@Autowired ReportOperations self` có chắc chọn chính bean đó không?** Không; self-injection chỉ là cơ chế fallback trong Spring, các candidate bình thường được xét trước.

**3. `@Lazy` trên self field có tự kích hoạt Spring AOP không?** Không. Nó tạo một proxy để lazy-resolve dependency, còn AOP proxy cần advisor/pointcut thực sự áp dụng.

**4. Vì sao constructor inject chính service dễ lỗi?** Nó có thể tạo constructor cycle khi bean muốn dựng chính nó trước khi construction kết thúc.

**5. Vì sao không nên gọi `self.audit()` trong `@PostConstruct`?** Khi ấy target có thể chưa được auto-proxy hoàn toàn; lazy resolve có thể gặp bean đang được tạo.

**6. Có cần `exposeProxy=true` để dùng `@Autowired @Lazy` không?** Không. Cấu hình này dùng cho `AopContext.currentProxy()`; lazy self injection làm việc qua dependency resolution.

**7. Lựa chọn được ưu tiên lâu dài?** Tách operation cần advice vào một bean độc lập và gọi qua dependency Spring inject, trừ khi có lý do rất rõ để giữ self-reference.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Proxying Mechanisms và Self-Invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — Using @Autowired: Self Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring Framework 6.2 — @Lazy API: Injection Point](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/Lazy.html)
- [Spring Framework 6.2 — ContextAnnotationAutowireCandidateResolver API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/annotation/ContextAnnotationAutowireCandidateResolver.html)
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — @AspectJ support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html)
