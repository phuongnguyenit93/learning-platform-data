# Aspect như bean hạ tầng và giới hạn áp dụng advice lên chính aspect

## 1. Hiểu đúng hai vai trò của một `@Aspect` trong Spring

Trong Spring AOP, một lớp mang `@Aspect` có thể được đăng ký **như một Spring bean** để Spring tìm, tạo, inject dependency và lấy các khai báo advice/pointcut của nó. Tuy nhiên, khi Spring AOP tự động chọn đối tượng để tạo proxy, **bean được đánh dấu `@Aspect` được loại khỏi danh sách target của auto-proxying**. Vì vậy, một aspect không thể được advice của một aspect khác chặn theo cơ chế **Spring AOP @AspectJ auto-proxy**.

Đây là một khác biệt dễ bỏ sót:

- **Là bean:** aspect có thể được Spring container quản lý vòng đời, cấu hình, inject dependency, và được lấy ra bằng `getBean(...)` như các bean thông thường.
- **Có vai trò hạ tầng AOP:** aspect cung cấp advisor/advice để Spring chèn vào **proxy của các target bean khác**; nó không trở thành đối tượng được Spring AOP auto-proxy chỉ vì pointcut của aspect khác khớp tên method trong aspect.
- **Không đồng nghĩa với annotation `@Infrastructure` hoặc interface `AopInfrastructureBean`:** gọi aspect là “bean hạ tầng” ở đây nhằm mô tả **vai trò**. Một class `@Aspect` không bắt buộc phải implements marker interface nào mới bị loại khỏi auto-proxying.

**Quy tắc cần nhớ:** *Aspect bean được Spring quản lý và cung cấp advice; nhưng Spring AOP không tự áp advice của aspect khác lên chính bean `@Aspect` đó.* Quy tắc này thuộc cơ chế proxy Spring AOP, không phải khẳng định về mọi công nghệ bytecode weaving hoặc mọi proxy được tạo thủ công.

Bài tập trung hoàn toàn vào Spring Framework và Spring AOP; không mở rộng sang lý thuyết Aspect tổng quát.

## 2. `@Aspect` không tự đăng ký thành Spring bean

Mã sau mô tả một aspect có advice:

```java
@Aspect
public class AuditAspect {
    @Before("execution(* com.example.app.service..*.*(..))")
    public void audit() {
        System.out.println("AUDIT");
    }
}
```

Đặt `@Aspect` lên class **chỉ khai báo vai trò aspect**, chưa bảo đảm Spring container tạo instance và sử dụng nó.

Có hai cách phổ biến để đăng ký:

**Cách A — component scanning:**

```java
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("execution(* com.example.app.service..*.*(..))")
    public void audit() {
        System.out.println("AUDIT");
    }
}
```

Với cách này, package của class phải nằm trong vùng Spring component-scan. `@Component` giúp Spring phát hiện bean; `@Aspect` giúp cơ chế @AspectJ nhận ra các khai báo advice.

**Cách B — đăng ký bằng `@Bean`:**

```java
@Configuration
@EnableAspectJAutoProxy
public class AopConfig {
    @Bean
    public AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

Đây là đoạn cấu hình minh họa, giả định class `AuditAspect` đã định nghĩa như ví dụ và các import Spring phù hợp. Trong cấu hình Spring Framework thuần, `@EnableAspectJAutoProxy` bật xử lý aspect bean kiểu `@AspectJ`. Ứng dụng Spring Boot có `spring-boot-starter-aop` thường được Boot tự bật hỗ trợ AOP khi đủ điều kiện classpath; không nhất thiết phải tự thêm `@EnableAspectJAutoProxy`.

**Không đặt `@Aspect` lên method `@Bean` để kỳ vọng nó biến object thành aspect.** Spring nhận diện loại aspect từ class thực tế mang `@Aspect`. Tương tự, `@Aspect` đơn lẻ không thay thế `@Component` khi dùng component scanning.

## 3. Spring xử lý aspect bean khác target bean ở đâu?

Một cách nhìn đơn giản về chu kỳ khởi tạo Spring:

```text
ApplicationContext đăng ký bean definitions
             |
             v
Bật auto-proxy @AspectJ (ví dụ @EnableAspectJAutoProxy)
             |
             v
Tìm các bean class có @Aspect để tạo danh sách advisors
             |
             +-------------------------------+
             |                               |
             v                               v
       Aspect bean                      Target bean khác
       (@Aspect)                        (ví dụ OrderService)
             |                               |
             |                               v
             |                        Có advice áp dụng?
             |                               |
             v                         Có ---+--- Không
   Spring AOP loại khỏi                     |         |
   @AspectJ auto-proxying                   v         v
             |                            Proxy   Bean bình thường
             v                              |
   Instance aspect thông thường             v
   trong Spring context                Client gọi proxy
                                              |
                                              v
                                    advice -> target method
```

Về mặt kỹ thuật, Spring Framework có auto-proxy creator, chẳng hạn `AnnotationAwareAspectJAutoProxyCreator`, làm công việc tìm advisor, đánh giá target bean và tạo AOP proxy khi cần. Trong việc xử lý aspect, Spring nhận diện class mang `@Aspect` là nguồn khai báo advice và **bỏ qua việc auto-proxy chính aspect đó**. Cơ chế này ngăn việc một aspect bị lời khuyên của aspect khác tác động như business target.

**Điều gì không đổi?** Spring vẫn inject constructor dependencies cho aspect, vẫn có thể gọi các method public thường của aspect qua reference tới bean, và vẫn sử dụng advice của nó khi method execution trên target bean phù hợp pointcut.

**Điều gì không được kỳ vọng?** Nếu `LoggingAspect` có pointcut khớp method `AuditAspect.maintenance()`, Spring AOP auto-proxy thông thường sẽ không biến `AuditAspect` thành target proxy để chạy advice của `LoggingAspect`.

### Ba khái niệm cần phân biệt

| Đối tượng | Vai trò | Auto-proxy Spring AOP thường làm gì? |
| --- | --- | --- |
| `@Aspect` bean | Nguồn cung cấp pointcut/advice | Được nhận diện để tạo advisor; **không trở thành target cho advice của aspect khác** |
| Service/repository/controller bean bình thường | Target tiềm năng của advice | Có thể được proxy nếu advisor phù hợp và bean đủ điều kiện |
| Hạ tầng đặc biệt như `BeanPostProcessor` hoặc `AopInfrastructureBean` | Hỗ trợ vận hành container/AOP | Có các quy tắc không eligible cho auto-proxy riêng; không được đánh đồng hoàn toàn với mọi aspect bean |

Chữ “hạ tầng” mô tả vai trò vận hành. Đừng suy rằng mọi bean do infrastructure sử dụng đều có cùng cơ chế hoặc cùng nguyên nhân bị loại khỏi proxy.

## 4. Ví dụ runnable: advice chạy trên service nhưng không chạy trên method của aspect

Ví dụ Java 17+ chạy bằng Maven, Spring Framework 6.2.6. Chương trình đăng ký **hai aspect bean**:

- `AuditAspect` có advice chạy trước method `doWork()` của `WorkService`; đồng thời có method bình thường `healthCheck()`.
- `ObserveAspect` có advice nhắm vào mọi method `healthCheck()` phù hợp pointcut.
- Khi client gọi `WorkService.doWork()` qua context, `AuditAspect` advice chạy.
- Khi client gọi `AuditAspect.healthCheck()` qua context, advice của `ObserveAspect` **không chạy**, dù biểu thức pointcut phù hợp tên method. Lý do là bản thân `AuditAspect` không được Spring AOP auto-proxy.

Cấu trúc project:

```text
aspect-bean-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── AspectBeanDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>aspect-bean-demo</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.6</version>
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
                    <mainClass>demo.AspectBeanDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/java/demo/AspectBeanDemo.java`:**

```java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class AspectBeanDemo {

    public static class WorkService {
        public void doWork() {
            System.out.println("SERVICE doWork");
        }
    }

    @Aspect
    public static class AuditAspect {
        @Before("execution(* demo..*.doWork(..))")
        public void beforeWork() {
            System.out.println("AUDIT before doWork");
        }

        public void healthCheck() {
            System.out.println("ASPECT healthCheck");
        }
    }

    @Aspect
    public static class ObserveAspect {
        @Before("execution(* demo..*.healthCheck(..))")
        public void beforeAspectMethod() {
            System.out.println("OBSERVE before healthCheck");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    public static class Config {
        @Bean
        public WorkService workService() {
            return new WorkService();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }

        @Bean
        public ObserveAspect observeAspect() {
            return new ObserveAspect();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            WorkService service = context.getBean(WorkService.class);
            AuditAspect aspect = context.getBean(AuditAspect.class);

            System.out.println("SERVICE_PROXY="
                    + AopUtils.isAopProxy(service));
            System.out.println("ASPECT_PROXY="
                    + AopUtils.isAopProxy(aspect));

            service.doWork();
            aspect.healthCheck();
        }
    }
}
```

Chạy tại thư mục `aspect-bean-demo`:

```bash
mvn -q compile exec:java
```

Các dòng do chương trình in, theo thứ tự:

```text
SERVICE_PROXY=true
ASPECT_PROXY=false
AUDIT before doWork
SERVICE doWork
ASPECT healthCheck
```

Nhận xét:

1. `SERVICE_PROXY=true` cho biết `WorkService` đã nhận Spring AOP proxy vì advice trong `AuditAspect` khớp `doWork()`.
2. `ASPECT_PROXY=false` cho biết bean `AuditAspect` không được @AspectJ auto-proxy, dù `ObserveAspect` có pointcut khớp tên `healthCheck()`.
3. Lệnh `service.doWork()` đi qua proxy nên in `AUDIT before doWork` trước khi target in `SERVICE doWork`.
4. Lệnh `aspect.healthCheck()` là lời gọi method thông thường trên aspect bean; chỉ in `ASPECT healthCheck`. **Không xuất hiện** dòng `OBSERVE before healthCheck`.
5. Cả hai aspect đều hiện diện trong container qua `@Bean`. Việc advice không chạy trên aspect **không phải** do quên đăng ký `ObserveAspect`.

Trong Maven hoặc Spring runtime có thể còn thông báo từ tool/logging ngoài các dòng do ví dụ tự in; chúng không làm thay đổi ý nghĩa các dòng nêu trên.

**Thử mở rộng:** tạo một Spring bean bình thường tên `HealthService` có method `healthCheck()` public, đăng ký `@Bean`, lấy từ context và gọi method này. Nếu pointcut `ObserveAspect` khớp method, lời gọi sẽ được advice, bởi bean đó là target bình thường. Đây là cách kiểm tra độc lập rằng pointcut hợp lệ và aspect đã đăng ký.

## 5. Vì sao gọi aspect là “bean hạ tầng” mà vẫn cần inject dependency?

Aspect nhiều khi cần một cộng tác viên như `AuditSink`, `Clock` hoặc `MetricsRecorder`. Spring vẫn có thể tạo bean và inject dependency qua constructor:

```java
public interface AuditSink {
    void record(String event);
}

@Aspect
@Component
public class AuditAspect {
    private final AuditSink sink;

    public AuditAspect(AuditSink sink) {
        this.sink = sink;
    }

    @Before("execution(* com.example.app.service..*.*(..))")
    public void beforeServiceCall() {
        sink.record("service-called");
    }
}
```

Đoạn này **minh họa một thành phần trong ứng dụng**, không phải file chạy độc lập: cần implementation của `AuditSink`, các import, và cấu hình scan phù hợp.

Spring quản lý `AuditAspect` tương tự nhiều bean khác ở khâu tạo và cấp dependency. Nhưng khi `sink.record(...)` được gọi, lời gọi tới `sink` **có thể** đi qua Spring AOP proxy của bean `AuditSink` nếu bean ấy được advice và được inject qua proxy. Điều đó **khác** với việc đưa chính `AuditAspect` vào proxy để advice chặn method của nó.

### Nên đặt trách nhiệm nào ở aspect?

Trong Spring AOP, aspect nên chủ yếu điều phối hành vi cắt ngang ở ranh giới lời gọi: xác định join point, đọc tham số cần thiết, gọi cộng tác viên, tiếp tục gọi target khi dùng around advice. Nếu phải làm xử lý nghiệp vụ hoặc IO dài, nên cân nhắc tách logic sang Spring bean chuyên trách và inject vào aspect.

Một lợi ích của cách tách này là bạn có thể kiểm thử, thay thế, hoặc áp các interceptor phù hợp cho **bean chuyên trách**, thay vì cố gắng dùng một aspect khác để chặn method trên `@Aspect` bean.

### Vấn đề recursion và pointcut quá rộng

Nếu một advice gọi `auditSink.record()`, trong khi pointcut của chính advice lại bao trùm cả `AuditSink.record()`, ứng dụng có thể phát sinh chuỗi gọi lặp không mong muốn. Với các bean cộng tác, chọn pointcut đủ hẹp, tách package theo trách nhiệm hoặc dùng điều kiện `!within(...)` / `!bean(...)` phù hợp trong Spring AOP.

Đây là vấn đề thiết kế **đường đi lời gọi đến bean được proxy**, khác với quy tắc Spring bỏ qua chính `@Aspect` bean khi auto-proxy.

## 6. Lưu ý về trạng thái và vòng đời của aspect bean

Spring thường đăng ký `@Aspect` bean dưới singleton scope, trừ khi ứng dụng cấu hình khác. Vì singleton được nhiều lời gọi cùng sử dụng, lưu trạng thái thay đổi theo request trong field của aspect có thể dẫn tới race condition hoặc lẫn dữ liệu giữa các thread:

```java
@Aspect
@Component
public class RequestTraceAspect {
    private String currentUser; // DỄ SAI nếu nhiều request chạy đồng thời
}
```

Field `currentUser` ở đây thuộc instance aspect chung, không tự động là dữ liệu riêng cho mỗi request. Lấy dữ liệu từ method arguments, Spring request context/security context khi phù hợp, hoặc dùng cộng tác viên có scope và cách truyền context đúng yêu cầu. Với async/virtual thread, không mặc định rằng thread-local context được tự động truyền qua mọi boundary.

Điều này không thay đổi khi aspect không được auto-proxy: nó vẫn là đối tượng có state và lifecycle do container quản lý.

Lưu ý riêng về `@Aspect` và `@Component`: nếu class mang cả hai, `@Component` phục vụ việc scan; `@Aspect` phục vụ nhận diện advisor và áp dụng quy tắc không auto-proxy aspect. Không dùng `@Repository` hoặc `@Service` thay đổi bản chất một `@Aspect` để mong advice của aspect khác chạy trên nó.

## 7. Các nhầm lẫn thường gặp về lời gọi trên aspect

### 7.1. “Aspect là bean thì advice khác chắc chắn phải áp được”

Sai trong Spring AOP @AspectJ auto-proxy. Điều kiện **bean được quản lý** chỉ là một phần của quá trình tạo proxy. Aspect được nhận diện là nguồn advice và chủ động bị loại khỏi tập target khi auto-proxy.

### 7.2. “Cứ viết pointcut đúng tên method của aspect là đủ”

Sai. Pointcut khớp method là cần thiết khi target eligible, nhưng không đảo ngược được quyết định Spring bỏ qua auto-proxy của aspect.

### 7.3. “Đặt `@Order(1)` lên aspect thì aspect sẽ được advice của aspect khác”

Sai. `@Order` điều khiển thứ tự ưu tiên của các aspect/advice cùng tham gia chuỗi interceptor trên **target bean đủ điều kiện**. Nó không biến aspect thành target cho các advice khác.

### 7.4. “Bật `exposeProxy=true` hoặc đổi sang CGLIB sẽ giải quyết”

Sai về bản chất. `exposeProxy` có liên quan đến truy xuất proxy hiện hành trong một invocation đang đi qua proxy; `proxyTargetClass=true` điều khiển lựa chọn proxy JDK/CGLIB. Không lựa chọn nào khiến aspect bean thoát khỏi quy tắc loại trừ @AspectJ auto-proxy.

### 7.5. “Chỉ có `@Before` mới bị giới hạn”

Sai. Vấn đề nằm ở **target bean không được auto-proxy**. Cho dù khai báo `@Around`, `@After`, `@AfterReturning` hay `@AfterThrowing` trong aspect khác, chúng cũng không tự chặn method của `@Aspect` bean khi không có proxy intercept call.

### 7.6. “Aspect không thể dùng một service được advice”

Sai. Aspect có thể inject và gọi Spring service bean. Nếu service nhận được Spring AOP proxy và pointcut khớp, interceptor của service có thể chạy bình thường. **Bean service** được advice, không phải **aspect**.

### 7.7. “Đã mang `@Aspect` thì không thể nào có proxy dưới bất kỳ hình thức nào”

Không nên kết luận rộng như vậy. Tài liệu Spring đang nói đến tính **không eligible cho @AspectJ auto-proxying của Spring AOP**. Proxy được tạo thủ công, cơ chế khác hoặc AspectJ weaving có phạm vi/hành vi riêng; chúng nằm ngoài quyết định auto-proxy đang xét. Trong ví dụ của bài, kết quả `AopUtils.isAopProxy(aspect) == false` phản ánh đúng đường thiết lập đã sử dụng.

## 8. Thiết kế và kiểm thử: đặt logic đúng bean

Giả sử bạn muốn đo thời gian ghi audit do `AuditAspect` khởi tạo. Cách cố viết một aspect thứ hai chặn `AuditAspect.writeAudit()` sẽ không đạt mục tiêu với Spring AOP auto-proxy. Hãy chuyển thao tác cần đo sang một collaborator bình thường:

```text
Client -> proxy(BusinessService) -> AuditAspect advice
                                      |
                                      v
                              proxy(AuditWriter)
                                      |
                                      v
                         TimingAspect advice -> AuditWriter.write()
```

Ví dụ khung API:

```java
public interface AuditWriter {
    void write(String message);
}

@Service
public class DatabaseAuditWriter implements AuditWriter {
    @Override
    public void write(String message) {
        // Ghi dữ liệu audit, ví dụ theo cơ chế được ứng dụng lựa chọn.
    }
}

@Aspect
@Component
public class AuditAspect {
    private final AuditWriter writer;

    public AuditAspect(AuditWriter writer) {
        this.writer = writer;
    }

    @Before("execution(* com.example.app.service..*.*(..))")
    public void auditCall() {
        writer.write("Business method invoked");
    }
}

@Aspect
@Component
public class TimingAspect {
    @Around("execution(* com.example.app.audit.DatabaseAuditWriter.write(..))")
    public Object timeAudit(ProceedingJoinPoint pjp) throws Throwable {
        long start = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            System.out.println("AUDIT_WRITE_NS=" +
                    (System.nanoTime() - start));
        }
    }
}
```

Đây là **mẫu kiến trúc, không phải chương trình standalone**: còn cần package declarations, imports và context Spring thích hợp. Điểm cần nắm là `DatabaseAuditWriter` là một Spring bean **không mang `@Aspect`**, nên Spring có thể tạo proxy cho bean này để `TimingAspect` advice `write(...)`. Nếu thay `AuditWriter` bằng method `writeAudit()` đặt trực tiếp trong `AuditAspect`, advice của `TimingAspect` không tự chặn method đó theo Spring AOP @AspectJ auto-proxy.

**Chú ý:** class `DatabaseAuditWriter` sử dụng annotation `@Service`, vì vậy phải nằm trong vùng component scan hoặc được đăng ký tương đương. Với kiểu proxy JDK, collaborator thường được inject theo interface `AuditWriter` như minh họa. Ví dụ `timeAudit` dành cho method `void` vẫn dùng `Object` theo chữ ký around advice; Spring xử lý return value phù hợp khi tiếp tục invocation. Giá trị thời gian phụ thuộc máy và workload, nên đoạn này không có stdout cố định.

Một cách khác khi chỉ muốn quan sát nội bộ `AuditAspect` là gọi trực tiếp một timer/helper trong code của chính aspect, hoặc đo trong test. Việc đo đó không cần phải được thực hiện bằng advice của aspect khác.

## 9. Checklist khi thấy aspect khác không chặn được method của aspect

1. **Đúng bean và đúng annotation?** Class đang gọi mang `@Aspect` hay chỉ là Spring service bình thường? Nếu mang `@Aspect`, kiểm tra quy tắc loại trừ khỏi Spring AOP auto-proxy trước khi kiểm pointcut.
2. **Đã đăng ký aspect?** Có `@Bean`, `@Component` kèm component-scan, hoặc khai báo tương đương chưa? Chỉ có `@Aspect` chưa đủ để đăng ký.
3. **Đã bật @AspectJ support?** Với Spring thuần, cấu hình `@EnableAspectJAutoProxy` và dependency liên quan; với Boot, xác định starter/auto-configuration hiệu lực.
4. **Có đang kiểm tra bean thật từ context?** Dùng `AopUtils.isAopProxy(context.getBean(...))` để biết có Spring AOP proxy trên reference thực tế.
5. **Pointcut có chặn target bean khác không?** Thử một service bình thường khớp cùng loại biểu thức. Nếu advice chạy trên service nhưng không chạy trên aspect, nguyên nhân có thể là quy tắc loại trừ aspect.
6. **Logic được đặt đúng chỗ chưa?** Nếu muốn advice trên hành vi do aspect khởi xướng, chuyển logic có thể tái sử dụng sang Spring collaborator bean và để aspect inject qua proxy.
7. **Có tạo vòng gọi vô hạn?** Nếu aspect gọi collaborator đã được aspect khác advice, kiểm tra lại pointcut của tất cả advisor liên quan.
8. **Có nhầm Spring AOP với cơ chế weaving khác không?** Kết luận về proxy của bài chỉ áp dụng cho Spring AOP; nếu project dùng AspectJ weaving thực sự, hãy đánh giá theo runtime/cấu hình riêng.

## 10. Câu hỏi tự kiểm tra

**1.** Một class có `@Aspect` nhưng không có `@Component` và không được khai báo bằng `@Bean`. Spring sẽ tự dùng advice chỉ nhờ `@Aspect` không?  
**Đáp án:** Không. Spring phải đăng ký aspect thành bean phù hợp để @AspectJ auto-proxy hỗ trợ phát hiện.

**2.** Hai aspect `A` và `B` đều là Spring bean. `B` khai báo `@Before` khớp method `A.ping()`. Spring AOP có tự proxy `A` để chạy `B` không?  
**Đáp án:** Không. Bean `@Aspect` bị loại khỏi auto-proxying của Spring AOP.

**3.** Nếu `A` gọi một Spring service `S` mà `B` có pointcut áp dụng, `B` có thể chạy không?  
**Đáp án:** Có, khi `S` là bean đủ điều kiện, nhận proxy, và lời gọi của `A` đi qua proxy đó.

**4.** Tại sao `@Order` không sửa được trường hợp `B` không advice `A`?  
**Đáp án:** `@Order` sắp xếp advice trên target đã có chuỗi interceptor; nó không biến aspect thành target eligible.

**5.** `AopUtils.isAopProxy(auditAspect)` trả `false` nhưng `AuditAspect` vẫn log được lời gọi `PaymentService.pay()`. Có mâu thuẫn không?  
**Đáp án:** Không. `AuditAspect` là nguồn advice; Spring AOP proxy nằm trên `PaymentService`, không cần nằm trên `AuditAspect`.

**6.** Cách thiết kế nào phù hợp khi muốn timing một thao tác IO do aspect gọi?  
**Đáp án:** Tách thao tác IO vào Spring collaborator bean được inject và có thể được proxy; hoặc đo trực tiếp ở code của aspect tùy yêu cầu, tránh kỳ vọng advice khác chặn method nội bộ của aspect.

## Tài liệu chính thức

- [Spring Framework — Declaring an Aspect](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html): aspect bean được khai báo như bean thường, `@Aspect` không đủ cho component-scan và ghi chú chính thức rằng aspect không được advice bởi aspect khác qua Spring AOP.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): bật xử lý @AspectJ auto-proxy bằng Java configuration hoặc XML.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy/target, giới hạn method interception và self-invocation.
- [Spring Framework — Using the Auto-Proxy Facility](https://docs.spring.io/spring-framework/reference/core/aop-api/autoproxy.html): vai trò auto-proxy creator và hạ tầng bean post-processing.
