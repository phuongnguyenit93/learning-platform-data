# Vòng đời của aspect và vòng đời của bean đích trong Spring AOP

## 1. Câu hỏi trọng tâm

Trong Spring AOP, **aspect** và **bean đích (target bean)** đều có thể do Spring IoC container quản lý, nhưng chúng **không mặc nhiên có cùng scope, cùng số instance hoặc cùng thời điểm được tạo/hủy**.

Một `@Aspect` mặc định thường là **một Spring singleton trong mỗi `ApplicationContext`**, trong khi cùng aspect đó có thể áp dụng advice cho nhiều bean đích: singleton, prototype hoặc bean thuộc scope web được cấu hình phù hợp. Ngược lại, các phương thức vòng đời của target bean không nhất thiết là những lần gọi đi qua AOP proxy, nên advice không tự chạy chỉ vì Spring đang khởi tạo/hủy bean.

Hiểu hai vòng đời độc lập này giúp trả lời các câu hỏi thực tế:

- Spring tạo instance aspect khi nào, và có tạo lại aspect mỗi khi service được gọi không?
- Bean singleton và prototype được proxy như thế nào? Lấy hai lần `getBean()` cho kết quả gì?
- Vì sao `@Before` không chạy khi target tự gọi method trong `@PostConstruct` hoặc `afterPropertiesSet()`?
- Ai gọi `@PreDestroy`/`destroy()` và điều gì xảy ra khi `ApplicationContext` đóng?
- Làm sao tránh lưu trạng thái riêng của từng request hoặc từng lần gọi trong một aspect singleton dùng chung?

Bài tập trung vào **vòng đời của aspect do Spring dùng cho Spring AOP** và quan hệ với **Spring bean đang được proxy**. Các mô hình AspectJ độc lập với Spring chỉ được nhắc khi cần phân biệt rõ cơ chế.

## 2. Phân biệt ba đối tượng trong một lời gọi Spring AOP

Khi Spring áp dụng advice cho một target bean theo cơ chế proxy, ta cần phân biệt:

| Thành phần | Vai trò | Quan hệ với vòng đời |
| --- | --- | --- |
| **Aspect bean** | Đối tượng chứa `@Aspect` và advice như `@Before`, `@Around`. | Thường singleton theo context; có lifecycle callback như các Spring bean khác. |
| **Target bean** | Đối tượng chứa nghiệp vụ, ví dụ `OrderService`. | Scope và lifecycle tùy bean definition: singleton, prototype, request, session... |
| **AOP proxy** | Đối tượng đại diện Spring có thể trao cho caller thay vì trao raw target, nhằm áp dụng advisor/advice khi method khớp. | Thường được tạo trong quy trình hậu xử lý bean; vòng đời/khả năng tái sử dụng phụ thuộc cách cấu hình target và target source. |

Mô hình gọi đơn giản:

```text
Spring ApplicationContext
  |
  +-- TraceAspect bean (thường 1 instance / context)
  |      └── advice / pointcut
  |
  +-- OrderService bean definition (ví dụ singleton)
  |      └── raw target -> Spring AOP proxy -> caller
  |
  +-- InvoiceService bean definition (ví dụ prototype)
         ├── lần getBean #1: target A -> proxy A
         └── lần getBean #2: target B -> proxy B

caller -> proxy phù hợp -> advice của aspect -> target.method()
```

Hình này mô tả **cấu hình proxy thông thường**. Với scoped proxy hoặc custom `TargetSource`, có thể có một proxy dùng chung trỏ tới các target khác nhau theo lần gọi; không được tổng quát hóa rằng mọi proxy luôn giữ một target cố định.

**Cốt lõi:** một aspect singleton vẫn có thể chạy cùng lời advice trên hàng trăm target beans hoặc nhiều lần gọi; **số lần advice thực thi không phải số lần aspect được khởi tạo**.

## 3. Vòng đời thường gặp của aspect `@Aspect`

### 3.1. Spring phải đăng ký aspect thành bean

`@Aspect` cho Spring biết class mang khai báo aspect, nhưng chỉ riêng annotation này không tự tạo một Spring bean. Có hai cách phổ biến:

```java
@Aspect
@Component
public class AuditAspect {
    // Advice...
}
```

Hoặc:

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

Trong cấu hình thứ hai, class `AuditAspect` vẫn phải có `@Aspect`, và phương thức `@Bean` đăng ký nó với container. Ví dụ chỉ minh họa cách khai báo, không phải tệp Java độc lập.

Ở Spring Framework thuần, thường bật `@EnableAspectJAutoProxy` hoặc XML `<aop:aspectj-autoproxy/>`. Spring Boot có thể tự cấu hình Spring AOP khi starter/điều kiện thích hợp đã có. Nếu aspect không phải bean hoặc hạ tầng proxy chưa bật, việc target và advice cùng tồn tại trong source code không đủ để bảo đảm lời advice chạy.

### 3.2. Singleton aspect có nghĩa gì?

Mặc định, Spring bean có scope `singleton`. Với `@Aspect` thông thường dùng mô hình singleton, có **một instance aspect ứng với bean definition trong cùng context**, không phải một instance trên từng service bean, từng thread hoặc từng request.

Ví dụ `AuditAspect` được tạo một lần và giữ `AtomicInteger` đếm số lời gọi; khi có 1.000 lần gọi qua proxy, counter tăng 1.000 lần nhưng constructor của `AuditAspect` không chạy 1.000 lần.

Cần phân biệt:

- **Singleton theo Spring context**, không phải singleton toàn JVM. Hai `ApplicationContext` độc lập có thể có hai instance aspect tương ứng.
- Nếu đăng ký **hai bean khác nhau** cùng class `@Aspect`, có thể có hai instance aspect và hai tập advisor; đó là hai bean definitions, không phải Spring tự nhân bản aspect trên mỗi lời gọi.
- Scope không tự bảo đảm thread safety: aspect singleton có thể được nhiều thread gọi đồng thời. Các field ghi trạng thái phải được thiết kế như shared state an toàn hoặc loại bỏ.

### 3.3. Lifecycle callback của aspect vẫn là callback Spring bean

Aspect là một Spring bean nên có thể tham gia các cơ chế lifecycle phổ biến:

- Khởi tạo instance và inject dependency.
- Callback khởi tạo như `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, hoặc `initMethod` khi được cấu hình.
- Được Spring dùng để xây dựng advisor áp dụng lên các target phù hợp.
- Callback hủy `@PreDestroy`, `DisposableBean.destroy()` hoặc `destroyMethod` khi scope/context thuộc diện Spring quản lý hủy.

**Không có quy tắc bảo đảm constructor của aspect luôn chạy trước constructor của mọi target bean.** Thứ tự khởi tạo phụ thuộc dependency graph, lazy initialization, proxy/advisor discovery và cách tạo context. Khi thứ tự thật sự quan trọng, xác lập dependency và kiểm thử; đừng dựa vào thứ tự tình cờ quan sát ở log.

### 3.4. Aspect thường không bị proxy bởi chính Spring AOP

Spring Framework loại class mang `@Aspect` khỏi tập target cần auto-proxy bằng chính cơ chế Spring `@AspectJ`. Không thiết kế hệ thống với giả định advice của aspect A sẽ tự chặn method nội bộ trên aspect B thông qua Spring AOP. Trách nhiệm chung cần được gắn vào **bean nghiệp vụ được proxy**, không gắn vào vòng đời callback hoặc class aspect như một target mặc định.

## 4. Vòng đời bean đích và vị trí AOP proxy xuất hiện

Trong luồng Spring container thông thường, sơ đồ khái quát cho một bean singleton được áp dụng Spring AOP là:

```text
Đọc bean definition / đăng ký hạ tầng auto-proxy
            |
            v
Tạo raw target instance
            |
            v
Inject dependencies và gọi callbacks trước khởi tạo
            |
            v
Gọi @PostConstruct / afterPropertiesSet / init method nếu có
            |
            v
BeanPostProcessor hậu khởi tạo
(có thể trả về Spring AOP proxy cho bean phù hợp)
            |
            v
Đưa bean/proxy đã hoàn thiện cho caller
            |
            v
Caller gọi method qua proxy -> advice có thể chạy
            |
            v
Khi kết thúc scope/context: Spring gọi cleanup callback
theo lifecycle scope tương ứng
```

Đây là **trật tự khái quát của quy trình chuẩn**, không phải cam kết mọi extension đều làm giống nhau; proxy cũng có thể được xử lý sớm trong tình huống đặc biệt như circular references. Điều quan trọng cho bài này là:

**Các initialization callbacks được gọi trên raw bean trước khi một proxy AOP thông thường được áp dụng.** Vì thế, nếu target gọi một phương thức được advice từ `@PostConstruct`/`afterPropertiesSet()`, lời gọi nội bộ đó không đi qua proxy của Spring AOP.

Ví dụ minh họa:

```java
public class OrderService implements org.springframework.beans.factory.InitializingBean {
    @Override
    public void afterPropertiesSet() {
        placeOrder(); // Trực tiếp gọi trên raw target (this).
    }

    public void placeOrder() {
        // Nghiệp vụ.
    }
}
```

Nếu pointcut khớp `placeOrder()`, Spring không tự áp dụng advice cho lời gọi trong `afterPropertiesSet()` như cho `context.getBean(OrderService.class).placeOrder()` sau khi proxy đã được cung cấp. Tương tự, `this.placeOrder()` trong một method khác của target là **self-invocation**, không quay lại proxy.

**Phân biệt:** `@Before` và `@After` là advice của một **lần thực thi phương thức qua proxy**, không phải cặp callback vòng đời Spring `@PostConstruct`/`@PreDestroy`.

## 5. Scope bean đích tác động thế nào tới việc tạo proxy?

| Scope target | Tạo target | Điều thường thấy khi lấy bean qua Spring | Hủy do container |
| --- | --- | --- | --- |
| `singleton` (mặc định) | Một target cho bean definition trong một context; thường eager khi context refresh, trừ khi lazy hoặc điều kiện khác. | Các lần `getBean()` cùng tên thường trả về cùng tham chiếu Spring bean (proxy nếu có). | Spring gọi destruction callbacks khi đóng context, trừ các ngoại lệ cấu hình/vòng đời. |
| `prototype` | Tạo một target mới mỗi lần container giải quyết yêu cầu bean tương ứng. | Khi dùng auto-proxy AOP thông thường, mỗi lần lấy prototype bean được xử lý tạo proxy cho target mới. | **Không tự gọi destruction callback** khi context đóng; client phải tự giải phóng resource nếu cần. |
| `request`/`session` trong web app | Tạo trong request/session scope theo cơ chế web-aware context. | Có thể inject scoped proxy để một dependency dài hạn luôn truy cập target hiện hành theo scope. | Cleanup tùy scope và cơ chế kết thúc request/session. |
| Custom scope/`TargetSource` | Theo logic cấu hình cụ thể. | Một proxy có thể chuyển tiếp tới target thay đổi theo lookup/lần gọi. | Phải kiểm tra contract scope/target source cụ thể. |

Quan hệ giữa **scope aspect** và **scope target** được quyết định riêng. Đặc biệt, `@Scope("prototype")` trên target **không khiến một singleton aspect trở thành prototype**.

### 5.1. Prototype target được tạo nhiều lần nhưng vẫn có thể dùng cùng singleton aspect

Ví dụ: target `ReportService` có scope prototype. Hai lần `context.getBean(ReportService.class)` trả về hai bean instances riêng, mỗi instance có thể được Spring bọc bằng proxy; một `@Aspect` singleton dùng chung vẫn đưa advice lên cả hai.

Ngược lại, nếu một singleton bean được inject trực tiếp với một prototype dependency tại thời điểm khởi tạo, nó thường **giữ đúng prototype instance đã nhận**. Nó không tự nhận một prototype mới ở mỗi lần gọi. Muốn lookup target mới nhiều lần, có thể dùng `ObjectProvider`, method injection hoặc scoped proxy được cấu hình đúng.

### 5.2. Scoped proxy khác proxy AOP của advice

Một bean request/session/prototype có thể được gắn scoped proxy để inject vào bean sống lâu hơn. Scoped proxy quyết định **chọn target hiện hành**; AOP proxy/advisor quyết định **lời gọi nào chạy advice**. Hai vai trò có thể phối hợp trong một cấu hình, thậm chí tạo nhiều tầng proxy khi thích hợp.

Vì vậy thấy `AopUtils.isAopProxy(bean) == true` chưa đủ kết luận proxy đó đã chứa advice mình mong muốn. Cần xét advisor và chạy thử method có pointcut khớp.

## 6. Ví dụ hoàn chỉnh: một aspect singleton, hai loại target scope

Ví dụ này dùng **Java 17+, Spring Framework 6.1.14, AspectJ weaver 1.9.22.1, Maven** để giữ dependency rõ ràng. Không cần Spring Boot hoặc web server.

Ta cố ý làm cho `SingletonService.afterPropertiesSet()` gọi `run()` trên raw bean: **đây là lời gọi nghiệp vụ không qua AOP proxy**. Sau khi container khởi động, ứng dụng lấy bean qua context và gọi `run()` từ bên ngoài để so sánh.

### 6.1. Cấu trúc project

```text
spring-aop-lifecycle/
├── pom.xml
└── src/main/java/com/example/lifecycle/
    ├── AppConfig.java
    ├── TraceAspect.java
    ├── SingletonService.java
    ├── PrototypeService.java
    └── DemoApp.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-aop-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp container và kéo các module Spring nền tảng, bao gồm Spring AOP theo cây dependency phù hợp với bản mẫu; `aspectjweaver` cung cấp hỗ trợ cần thiết để Spring xử lý `@Aspect`/pointcut. Đây vẫn là **Spring proxy AOP**.

### 6.3. `src/main/java/com/example/lifecycle/TraceAspect.java`

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

@Aspect
public class TraceAspect implements InitializingBean, DisposableBean {
    private static final AtomicInteger initialized = new AtomicInteger();
    private static final AtomicInteger destroyed = new AtomicInteger();

    private final AtomicInteger adviceCalls = new AtomicInteger();

    @Override
    public void afterPropertiesSet() {
        initialized.incrementAndGet();
    }

    @Before("execution(public void com.example.lifecycle.*Service.run())")
    public void beforeRun() {
        adviceCalls.incrementAndGet();
    }

    public int calls() {
        return adviceCalls.get();
    }

    public static int initCount() {
        return initialized.get();
    }

    public static int destroyCount() {
        return destroyed.get();
    }

    @Override
    public void destroy() {
        destroyed.incrementAndGet();
    }
}
```

`TraceAspect` có một counter trên instance để đếm số lần advice chạy, và counter `static` để quan sát callback khởi tạo/hủy. Counter `static` chỉ phục vụ ví dụ một lần chạy trong JVM; code sản xuất không nên dùng static field làm cơ chế xác định lifecycle nghiệp vụ.

`AtomicInteger` cho phép counter được tăng an toàn nếu có nhiều thread; bản thân việc dùng singleton aspect không tự bảo đảm mọi loại mutable field đều thread-safe.

### 6.4. `src/main/java/com/example/lifecycle/SingletonService.java`

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class SingletonService implements InitializingBean, DisposableBean {
    private static final AtomicInteger initialized = new AtomicInteger();
    private static final AtomicInteger destroyed = new AtomicInteger();
    private static final AtomicInteger runs = new AtomicInteger();

    @Override
    public void afterPropertiesSet() {
        initialized.incrementAndGet();
        run(); // Gọi trực tiếp trên raw bean trước khi proxy được công bố.
    }

    public void run() {
        runs.incrementAndGet();
    }

    public static int initCount() {
        return initialized.get();
    }

    public static int destroyCount() {
        return destroyed.get();
    }

    public static int runCount() {
        return runs.get();
    }

    @Override
    public void destroy() {
        destroyed.incrementAndGet();
    }
}
```

`SingletonService` có đúng một lần gọi `run()` **trong initialization callback** và sẽ có thêm lời gọi `run()` từ chương trình chính qua proxy.

### 6.5. `src/main/java/com/example/lifecycle/PrototypeService.java`

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class PrototypeService implements InitializingBean, DisposableBean {
    private static final AtomicInteger initialized = new AtomicInteger();
    private static final AtomicInteger destroyed = new AtomicInteger();
    private static final AtomicInteger runs = new AtomicInteger();

    @Override
    public void afterPropertiesSet() {
        initialized.incrementAndGet();
    }

    public void run() {
        runs.incrementAndGet();
    }

    public static int initCount() {
        return initialized.get();
    }

    public static int destroyCount() {
        return destroyed.get();
    }

    public static int runCount() {
        return runs.get();
    }

    @Override
    public void destroy() {
        destroyed.incrementAndGet();
    }
}
```

Class này có `destroy()` để chứng minh rằng **Spring không tự gọi destruction callback của prototype bean khi đóng context**, dù đã chạy callback khởi tạo mỗi khi tạo một prototype.

### 6.6. `src/main/java/com/example/lifecycle/AppConfig.java`

```java
package com.example.lifecycle;

import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Scope;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }

    @Bean
    public SingletonService singletonService() {
        return new SingletonService();
    }

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public PrototypeService prototypeService() {
        return new PrototypeService();
    }
}
```

`@Bean` mặc định singleton áp dụng cho `TraceAspect` và `SingletonService`. `PrototypeService` được đánh dấu prototype nên mỗi lần lookup từ container tạo một target mới. `@EnableAspectJAutoProxy(proxyTargetClass = true)` yêu cầu class-based proxy để lấy các service không có interface bằng chính kiểu lớp.

### 6.7. `src/main/java/com/example/lifecycle/DemoApp.java`

```java
package com.example.lifecycle;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class DemoApp {

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class);
        try {
            TraceAspect aspect = context.getBean(TraceAspect.class);

            SingletonService singletonA = context.getBean(SingletonService.class);
            SingletonService singletonB = context.getBean(SingletonService.class);
            PrototypeService prototypeA = context.getBean(PrototypeService.class);
            PrototypeService prototypeB = context.getBean(PrototypeService.class);

            System.out.println("singleton same=" + (singletonA == singletonB));
            System.out.println("prototype same=" + (prototypeA == prototypeB));
            System.out.println("singleton proxy=" + AopUtils.isAopProxy(singletonA));
            System.out.println("prototype proxy=" + AopUtils.isAopProxy(prototypeA));
            System.out.println("initialized: aspect=" + TraceAspect.initCount()
                    + ", singleton=" + SingletonService.initCount()
                    + ", prototype=" + PrototypeService.initCount());
            System.out.println("before external: singletonRuns="
                    + SingletonService.runCount() + ", adviceCalls=" + aspect.calls());

            singletonA.run();
            prototypeA.run();
            prototypeB.run();

            System.out.println("after external: singletonRuns="
                    + SingletonService.runCount()
                    + ", prototypeRuns=" + PrototypeService.runCount()
                    + ", adviceCalls=" + aspect.calls());
        } finally {
            context.close();
        }

        System.out.println("after close: aspectDestroyed=" + TraceAspect.destroyCount()
                + ", singletonDestroyed=" + SingletonService.destroyCount()
                + ", prototypeDestroyed=" + PrototypeService.destroyCount());
    }
}
```

Chạy trong thư mục chứa `pom.xml` với Maven và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.lifecycle.DemoApp
```

Các dòng do **chương trình** in ra, theo đúng thứ tự (không tính log của Maven/Spring nếu môi trường tự bật log):

```text
singleton same=true
prototype same=false
singleton proxy=true
prototype proxy=true
initialized: aspect=1, singleton=1, prototype=2
before external: singletonRuns=1, adviceCalls=0
after external: singletonRuns=2, prototypeRuns=2, adviceCalls=3
after close: aspectDestroyed=1, singletonDestroyed=1, prototypeDestroyed=0
```

**Giải thích đầu ra:**

1. Hai lần lấy `SingletonService` trả cùng tham chiếu bean/proxy, trong khi hai lần lấy `PrototypeService` trả hai tham chiếu khác nhau.
2. Cả singleton target lẫn prototype targets đều khớp pointcut `execution(public void ...*Service.run())` nên được Spring xử lý thành AOP proxies.
3. Có một `TraceAspect` được khởi tạo, một singleton service và hai prototype services. `TraceAspect` **không bị nhân bản** để theo số prototype instances.
4. Trong `SingletonService.afterPropertiesSet()`, `run()` đã chạy một lần trên raw bean nhưng advice vẫn bằng 0. Khi caller bên ngoài dùng proxy gọi ba lần (`singletonA`, `prototypeA`, `prototypeB`), advice tăng đúng 3 lần.
5. Sau `context.close()`, Spring hủy singleton aspect và singleton target. Hai prototype targets đã được tạo và khởi tạo vẫn **không có** lời gọi `destroy()` tự động do container; ví dụ không tự giải phóng chúng để quan sát khác biệt.

Đây là thí nghiệm về Spring container lifecycle và Spring AOP proxy. Không nên diễn giải kết quả thành “mọi method trong constructor hoặc `@PostConstruct` luôn bị bỏ qua vì pointcut không khớp”: vấn đề thực sự là **không đi qua proxy** ở thời điểm đó.

## 7. `@PostConstruct` và `@PreDestroy` có phải advice không?

**Không.** Hai annotation lifecycle callback quản lý **chu trình sống của bean**, còn Spring AOP advice quản lý **lần thực thi method qua proxy**.

| Tình huống | Ai kích hoạt? | Có mặc nhiên chạy `@Before`/ `@Around`? |
| --- | --- | --- |
| `@PostConstruct` trên target bean | Spring trong lúc khởi tạo raw bean | Không; callback chạy trước khi proxy thông thường được áp dụng. |
| `InitializingBean.afterPropertiesSet()` | Spring trong init phase | Không; tương tự. |
| Caller dùng bean đã inject từ context và gọi method khớp pointcut | Caller đi qua AOP proxy | Có, nếu proxy/advisor và điểm gọi hợp lệ. |
| `this.someMethod()` từ một method của target | Raw target tự gọi nội bộ | Không đi qua proxy, thường không kích hoạt advice của lời gọi nội bộ. |
| `@PreDestroy`/`DisposableBean.destroy()` | Container trong cleanup của bean được quản lý hủy | Không được xem là lời gọi có advice theo mặc định; không dùng advice để thay callback hủy. |
| Method trên đối tượng tự `new` ngoài Spring | Code ứng dụng | Không có AOP proxy Spring để áp dụng. |

Một callback `@PostConstruct` muốn thực hiện nghiệp vụ sau khi proxy đã sẵn sàng thường là tín hiệu cần thiết kế lại điểm kích hoạt: có thể đẩy công việc sang bean khác, dùng `ApplicationRunner` trong Spring Boot hoặc callback/event sau khi context refresh phù hợp. Không nên giả định gọi method được advice từ trong constructor/initialization callback sẽ kích hoạt advice.

**Quan trọng với `@Transactional`:** Spring transaction interceptor cũng thường dựa trên proxy. Nếu gọi method `@Transactional` từ chính target trong `@PostConstruct`, transaction proxy không có cơ hội chặn lời gọi. Đây là một lỗi lifecycle/proxy thường gặp, không phải lỗi syntax của annotation.

## 8. Các mô hình khởi tạo aspect nâng cao trong Spring

### 8.1. Singleton là mặc định, nhưng không phải mô hình duy nhất

Tài liệu Spring Framework về `@AspectJ` nêu các **aspect instantiation models** như:

- **Singleton:** một aspect instance mặc định trong application context.
- **`perthis(...)`:** conceptually một aspect instance gắn với mỗi đối tượng proxy `this` phù hợp tại join point được chọn.
- **`pertarget(...)`:** aspect instance gắn với mỗi đối tượng target phù hợp.
- **`pertypewithin(...)`:** được tài liệu các phiên bản Spring mới liệt kê, nhưng cần kiểm tra hỗ trợ thực tế theo dòng Framework ứng dụng đang dùng.
- **`percflow` và `percflowbelow`:** không được Spring proxy AOP hỗ trợ theo tài liệu hiện hành.

Các mô hình không-singleton này là **quy tắc tạo aspect instances**, khác với `@Scope("prototype")` của **target bean**. Chúng không được bật chỉ vì target là prototype, và không được suy luận đơn giản từ số lần `getBean()` của target.

Ví dụ khai báo mang tính minh họa:

```java
@Aspect("perthis(execution(* com.example..service.*.*(..)))")
public class PerProxyUsageAspect {
    private int callsForAssociatedProxy;

    @Before("execution(* com.example..service.*.*(..))")
    public void record() {
        callsForAssociatedProxy++;
    }
}
```

Đây là **một class fragment minh họa**, cần thêm imports, đăng ký bean và cấu hình scope tương thích với kiểu khởi tạo aspect (thường dùng prototype-scoped aspect bean cho mô hình per-clause phù hợp), không phải một chương trình độc lập. Tránh dùng `perthis` hoặc `pertarget` chỉ để đếm metric chung: tính phức tạp và lifecycle sẽ khó kiểm soát hơn singleton stateless.

Spring AOP chỉ chặn **method executions trên Spring beans qua proxy**. Ngay cả khi dùng `perthis`/`pertarget`, nó không biến thành AspectJ compile-time weaving, và không tự sửa giới hạn self-invocation hoặc đối tượng ngoài container.

### 8.2. Đừng nhầm `@Scope("prototype")` của aspect với `perthis`/`pertarget`

`@Scope` là metadata cho Spring bean definition; `perthis`/`pertarget` là các quy tắc instantiation của `@Aspect`. Với nhu cầu cơ bản, **giữ aspect singleton và không mang mutable state theo từng request** là lựa chọn dễ kiểm soát hơn. Nếu cần aspect per-object, phải chọn model được hỗ trợ theo phiên bản Spring và bảo đảm bean definition tương thích.

Ngoài ra, Spring schema-based AOP qua XML `<aop:aspect>` chỉ hỗ trợ **singleton instantiation model** theo tài liệu, nên không được chuyển cơ học một aspect `perthis` thành cấu hình schema và mong có cùng vòng đời.

## 9. Thiết kế trạng thái trong singleton aspect: tránh lỗi chia sẻ dữ liệu

Một aspect singleton có thể bị gọi đồng thời từ nhiều request/threads. Ví dụ dễ lỗi:

```java
@Aspect
public class UnsafeDurationAspect {
    private long startedAtNanos;

    @Before("execution(* com.example..service.*.*(..))")
    public void before() {
        startedAtNanos = System.nanoTime();
    }

    @After("execution(* com.example..service.*.*(..))")
    public void after() {
        System.out.println(System.nanoTime() - startedAtNanos);
    }
}
```

Đây là **ví dụ phản diện**, chưa phải class chạy độc lập. Nếu thread A và thread B gọi cùng lúc, field `startedAtNanos` bị ghi chồng khiến kết quả đo sai. Kể cả thêm `volatile` chỉ giải quyết tính nhìn thấy của giá trị, không biến state đó thành riêng cho từng lời gọi.

Hướng phù hợp hơn là dùng biến cục bộ trong một advice `@Around`:

```java
@Around("execution(* com.example..service.*.*(..))")
public Object measure(org.aspectj.lang.ProceedingJoinPoint pjp) throws Throwable {
    long startedAtNanos = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - startedAtNanos;
        // Gửi elapsedNanos sang metric recorder thread-safe.
    }
}
```

Đây cũng là **method fragment** trong một aspect có import `org.aspectj.lang.annotation.Around`. `finally` đo cả trường hợp method ném exception; `proceed()` chuyển tiếp lời gọi đến target. Biến `startedAtNanos` cục bộ trên invocation nên không chia sẻ giữa threads.

Đối với counter tổng hợp, `AtomicInteger`/`LongAdder` hoặc metric registry phù hợp có thể dùng; đối với state gắn với request, dùng request-scoped context hay tracing context theo kiến trúc ứng dụng, không giữ trong instance field mutable của singleton aspect.

## 10. Quan sát vòng đời đúng cách khi kiểm thử Spring AOP

Một test phục vụ bài học nên xác minh cả **quan hệ instance** lẫn **hành vi advice**, thay vì chỉ in log constructor:

1. **Context và scope:** kiểm tra `getBean()` hai lần với singleton/prototype; nếu web scope, tạo request/session test context tương ứng.
2. **Proxy:** kiểm tra `AopUtils.isAopProxy(bean)` và advisor/pointcut áp dụng, không kết luận chỉ dựa vào class name chứa `$$SpringCGLIB$$`.
3. **Lifecycle callback:** đếm `afterPropertiesSet()`, `@PostConstruct`, `destroy()` tùy scope và thời điểm close.
4. **Đường gọi:** gọi method từ bên ngoài qua proxy, rồi so với lời gọi nội bộ từ target/initialization phase.
5. **Aspect instances:** đo số bean aspect trong context và số lần advice chạy; hai con số độc lập.
6. **Phạm vi context:** thử parent/child context nếu có để tránh nhầm singleton theo context với singleton theo toàn JVM.
7. **Thread safety:** nếu advice lưu state, kiểm thử dưới tải đồng thời và lỗi/exception, không chỉ một lần gọi tuần tự.

Có thể dùng `context.getBeanNamesForType(MyAspect.class)` để quan sát aspect beans, `AopUtils.isAopProxy(target)` để nhận diện proxy, và `Advised.getAdvisors()` khi cần kiểm tra advisor chain. Đây là các phép kiểm tra bổ trợ: **bean bị proxy** không đồng nghĩa **mỗi method đều được advice**, và **một aspect bean** không có nghĩa advice chỉ chạy một lần.

## 11. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra/sửa |
| --- | --- | --- |
| Advice không chạy từ `@PostConstruct` | Target đang chạy init trước khi proxy hoàn thiện, hoặc gọi nội bộ trên `this`. | Đưa lời gọi cần interception qua bean/proxy từ ngoài sau khởi tạo; không cố vá bằng cách bật lại AOP. |
| Advice chạy nhiều lần dù aspect chỉ khởi tạo một lần | Singleton aspect được chia sẻ và advice chạy cho mỗi lời gọi phù hợp — hành vi bình thường. | Phân biệt instance count với invocation count; chỉ báo lỗi nếu vượt số lần dự kiến. |
| Có hai instance của cùng class aspect | Đăng ký aspect qua `@Component`, `@Bean`, XML trùng hoặc nhiều context. | Đếm bean name/contexts và thống nhất nơi đăng ký. |
| `prototype` target bị giữ lâu trong singleton client | Prototype được inject một lần khi singleton client khởi tạo. | Sử dụng `ObjectProvider`, method injection hoặc scoped proxy phù hợp. |
| Prototype có `destroy()` nhưng không thấy chạy khi đóng context | Container không tự quản lý destruction của prototype sau khi giao cho client. | Client quản lý cleanup/resource; nếu cần, gọi thủ tục giải phóng tương ứng. |
| Scope request/session không hoạt động ngoài web context | Scope web chưa được đăng ký/không có request đang hoạt động. | Dùng web-aware context, test request/session setup và scoped proxy đúng cách. |
| Aspect singleton có kết quả đo thời gian lẫn lộn | Shared mutable field giữa các lời gọi đồng thời. | Dùng local variable trong `@Around`, metric collector thread-safe. |
| Aspect được tạo sớm hơn dự kiến | Spring cần khởi tạo advisor/aspect, có dependency hoặc eager bean creation. | Kiểm tra `@Lazy`, bean graph và hạ tầng AOP; không giả định callback thứ tự chỉ bằng source order. |
| Không thấy `@PreDestroy` trên bean ngoài Spring | Đối tượng không thuộc quản lý container hoặc không thuộc scope được quản lý hủy. | Phân biệt `new` với `context.getBean()` và bảo đảm close context khi cần. |
| Thấy `@Aspect` nhưng không có advice | Aspect chưa là bean, auto-proxy chưa bật, pointcut không khớp hoặc caller không qua proxy. | Kiểm tra lần lượt đăng ký bean, enablement, proxy, pointcut và đường gọi. |

## 12. Kết luận thiết kế trong Spring AOP

Đối với đa số Spring services, cách thiết kế dễ bảo trì nhất là:

- **Aspect ít trạng thái, mặc định singleton**, chỉ chứa chính sách kỹ thuật dùng chung.
- **Target bean chọn scope theo trách nhiệm nghiệp vụ** (singleton cho đa số stateless services; prototype hoặc web scope khi có nhu cầu rõ ràng).
- **Advice bắt các lời gọi thông qua Spring proxy** sau khi bean được đưa vào sử dụng, không dùng advice thay cho init/destroy callbacks.
- **Dọn resource theo lifecycle của target scope**, đặc biệt không mong container tự hủy prototype.
- **Khi cần thay đổi aspect instantiation model**, đối chiếu đúng phiên bản Spring, mô hình `@AspectJ` và loại bean definition.

### Tài liệu chính thức để đối chiếu

- Spring Framework — Aspect Instantiation Models: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/instantiation-models.html
- Spring Framework — Declaring an Aspect: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/at-aspectj.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework — Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html

**Một singleton aspect có thể đồng hành với nhiều target beans và nhiều lời gọi; điều quyết định advice có chạy là lời gọi có đi qua Spring proxy phù hợp hay không.** Vòng đời Spring bean và vòng đời lời gọi AOP có liên hệ, nhưng phải được quan sát và kiểm thử như hai cơ chế riêng biệt.
