# Ranh giới với AOP, giao dịch và các mô-đun web trong Spring Framework

## 1. Vì sao phải phân biệt các lớp trách nhiệm?

Khi học Spring Core Container, rất dễ đi từ `@Component`, `@Bean` và `@Autowired` sang kết luận rằng container sẽ tự động xử lý cả logging, transaction, HTTP endpoint và mọi hành vi gắn annotation. Kết luận đó **không đúng**.

**Spring Core Container** chịu trách nhiệm chính về **quản lý và lắp ráp bean**: đọc metadata cấu hình, tạo object, giải quyết dependency, áp dụng scope, phối hợp lifecycle và cung cấp `BeanFactory`/`ApplicationContext`. Những cơ chế khác có thể *dựa trên* container để gắn thêm hành vi:

- **Spring AOP:** áp dụng lời khuyên (*advice*) như log, đo thời gian hoặc chính sách chung quanh **lời gọi phương thức** đủ điều kiện, thường thông qua proxy.
- **Spring Transaction Management:** cung cấp hạ tầng khai báo/điều phối giao dịch (chẳng hạn `@Transactional`) và transaction manager thích hợp; ở chế độ phổ biến, sử dụng AOP proxy.
- **Spring Web MVC / WebFlux:** tổ chức tiếp nhận HTTP request, ánh xạ handler, binding, xử lý kết quả/response và lỗi; bean controller/service vẫn do Spring container cung cấp.
- **Spring Boot:** hỗ trợ bootstrap, dependency starter và auto-configuration; **không đồng nghĩa với Spring Core Container** và không phải điều kiện bắt buộc để chạy Spring Framework thuần.

Một ứng dụng console có thể sử dụng `ApplicationContext` mà **không có web server, giao dịch database hoặc aspect**. Một ứng dụng web/transactional vẫn cần IoC container nhưng phải có các thành phần hạ tầng tương ứng.

~~~text
          Spring Boot (nếu chọn dùng)
        bootstrap / auto-configuration
                      |
      +---------------v----------------+
      | Spring Core Container          |
      | BeanFactory / ApplicationContext|
      | bean definitions + DI + lifecycle|
      +----------------+---------------+
                       |
       +---------------+----------------+
       |               |                |
    Spring AOP      Spring Tx       Spring Web
   method proxy   tx interceptor   MVC / WebFlux
       |           + tx manager         |
       +----> service / repository <----+
                    beans
~~~

Sơ đồ thể hiện **quan hệ phối hợp chức năng**, không phải sơ đồ phụ thuộc Maven đầy đủ. AOP, transaction và web là các tính năng/tầng trách nhiệm khác nhau, nhưng tất cả có thể dùng chung các bean do container quản lý.

## 2. Những thứ thuộc Core Container

Một `ApplicationContext` như `AnnotationConfigApplicationContext` có thể thực hiện:

1. Đọc cấu hình bean (`@Configuration`, `@Bean`, component scanning nếu bật).
2. Tạo bean, chọn constructor/factory method, và inject các dependency.
3. Quản lý scope, thường là `singleton` theo từng context; quản lý callback khởi tạo/hủy của bean theo quy tắc tương ứng.
4. Cung cấp `Environment`, resource loading, internationalization qua `MessageSource`, event publication và các tiện ích context khác.
5. Thực thi quá trình khởi động `refresh()`, nơi bean definitions và các post-processor có thể được đăng ký, khám phá và kích hoạt.

Ví dụ cấu hình:

~~~java
@Configuration
class CoreConfig {
    @Bean
    Notifier notifier() {
        return new ConsoleNotifier();
    }

    @Bean
    OrderService orderService(Notifier notifier) {
        return new OrderService(notifier);
    }
}
~~~

Đây là **mã minh họa**, chưa runnable độc lập nếu chưa định nghĩa `Notifier`, `ConsoleNotifier` và `OrderService`. Việc nối `notifier` vào constructor của `OrderService` là **DI thuần túy**; nó **không tự** tạo AOP logging, mở database transaction hoặc công bố REST endpoint.

Bên trong container có cơ chế mở rộng như `BeanPostProcessor`. Các module AOP/transaction có thể đăng ký thêm post-processor và proxy. Do đó ranh giới không phải “Core không liên quan gì tới AOP”, mà là **Core cung cấp nền tảng, còn tính năng chuyên biệt cần hạ tầng và cấu hình riêng**.

### Bảng xác định đúng tầng

| Câu hỏi / hành vi | Trách nhiệm chính |
| --- | --- |
| “Ai tạo `OrderService` và đưa `Repository` vào constructor?” | Core Container (DI / bean factory) |
| “Ai thêm log trước khi gọi một service?” | AOP advice và auto-proxy infrastructure, hoặc mã log thuần |
| “Ai quyết định mở/commit/rollback giao dịch khi gọi service?” | Transaction interceptor + transaction manager + tài nguyên giao dịch |
| “Ai biến `GET /orders/7` thành lời gọi controller?” | Web MVC dispatcher/handler mapping hoặc WebFlux dispatcher |
| “Ai đóng gói mặc định dependency và tự cấu hình server?” | Spring Boot khi được sử dụng |
| “Ai thực thi câu lệnh SQL?” | JDBC/JPA/client database tương ứng, không phải IoC container |
| “Ai thực thi `new` trong `@Bean` factory?” | Mã factory do container gọi, không phải một phép màu loại bỏ `new` |

## 3. Ranh giới với Spring AOP

### 3.1. AOP làm gì?

**Aspect-Oriented Programming (AOP)** nhằm tách những xử lý dùng xuyên nhiều lớp (*cross-cutting concerns*) khỏi luồng nghiệp vụ chính, ví dụ:

- Audit/logging một số method call.
- Đo thời gian, theo dõi metric, trace.
- Áp dụng một chính sách kiểm tra chung quanh method call.
- Thực hiện cơ chế interceptor dùng cho `@Transactional` trong cách cấu hình giao dịch phổ biến.

Các khái niệm nền:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Aspect** | Tập hợp một concern xuyên suốt, ví dụ tracing |
| **Join point** | Vị trí có thể áp dụng hành vi; với Spring AOP dựa trên proxy, chủ yếu là thực thi phương thức của Spring bean |
| **Pointcut** | Điều kiện chọn method/join point |
| **Advice** | Hành vi áp dụng trước/sau/quanh lần gọi |
| **Target** | Đối tượng chứa nghiệp vụ thật |
| **Proxy** | Đối tượng trung gian nhận lời gọi, áp dụng interceptor rồi chuyển tới target |

Spring AOP không có nghĩa tất cả code Java trong ứng dụng đều tự được “weave”. Nó chủ yếu xử lý **method execution của các bean Spring đủ điều kiện** qua proxy. Các điểm nối như field access hay constructor execution không phải phạm vi thông thường của Spring AOP proxy; muốn AOP ở mức bytecode sâu hơn cần công cụ như AspectJ weaving, là cách khác.

### 3.2. Vì sao chỉ thêm `@Aspect` chưa đủ?

Khối sau chỉ là ví dụ cú pháp, **không tự hoạt động chỉ nhờ annotation**:

~~~java
@Aspect
class TraceAspect {
    @Before("execution(* process(..))")
    void beforeProcess() {
        System.out.println("TRACE before");
    }
}
~~~

Cần `org.aspectj.lang.annotation.Aspect`/`Before` và một hạ tầng phát hiện aspect + áp dụng proxy; thường dùng:

- `spring-aop` và thư viện AspectJ phục vụ phân tích pointcut.
- `@EnableAspectJAutoProxy` hoặc cấu hình tự động tương đương.
- Bean chứa aspect được đăng ký vào cùng `ApplicationContext`.
- Target là bean do container quản lý và lời gọi **đi qua proxy**.

`@Aspect` mô tả advice; nó không tự biến một object được `new` bên ngoài container thành bean có interceptor.

### 3.3. Giới hạn quan trọng: self-invocation và proxy

Xét:

~~~java
class PaymentService {
    public void checkout() {
        this.verify();
    }

    public void verify() {
        // logic kiểm tra
    }
}
~~~

Nếu Spring AOP gắn advice cho `verify()` theo proxy, thì `checkout()` gọi `this.verify()` **trực tiếp trên target**, bỏ qua proxy; advice áp dụng cho lời gọi `verify` từ bên ngoài proxy sẽ **không** chạy ở lời gọi nội bộ đó.

Các hệ quả thường gặp:

- JDK dynamic proxy triển khai interface; code nên gọi qua kiểu interface phù hợp. Class-based proxy (CGLIB) tạo subclass khi điều kiện cho phép.
- Với class-based proxy, `final` class không thể được subclass và `final` method không thể bị override để advise; private method cũng không thể được proxy interception theo cách này.
- Lấy bean bằng `getBean(Interface.class)` có thể nhận **proxy**, không phải reference trực tiếp tới target.
- Một lời gọi **qua proxy** và một lời gọi nội bộ qua `this` có thể cho kết quả khác nhau về advice dù business method chạy cùng mã.

Giải pháp thiết kế thường là tách hành vi phải được intercept sang bean riêng và gọi qua dependency được inject. Không nên lạm dụng `AopContext.currentProxy()` vì sẽ buộc domain/service biết hạ tầng AOP.

## 4. Ranh giới với quản lý giao dịch

### 4.1. `@Transactional` không phải một giao dịch tự động từ Core Container

Annotation:

~~~java
@Transactional
public void transferMoney() {
    debitSource();
    creditDestination();
}
~~~

là **mã minh họa**, chưa có các hàm `debitSource`/`creditDestination`. Quan trọng hơn: **chỉ có `@Transactional` không bảo đảm mở, commit hay rollback một transaction**.

Để giao dịch khai báo hoạt động trong cấu hình proxy thông thường, thường cần:

1. Dependency cho transaction abstraction, chẳng hạn module `spring-tx`; với JDBC còn có `spring-jdbc` và driver database.
2. Bật transaction interception, thường bằng `@EnableTransactionManagement` (hoặc auto-configuration phù hợp).
3. Một bean `TransactionManager` phù hợp với tài nguyên: ví dụ `JdbcTransactionManager`/`DataSourceTransactionManager` cho một JDBC `DataSource`, `JpaTransactionManager` cho JPA hoặc giải pháp tương ứng với môi trường.
4. Service là Spring bean; lời gọi cần áp dụng annotation phải đi **qua proxy** ở chế độ proxy.
5. Tài nguyên đọc/ghi **thực sự tham gia cùng transaction**; dùng một connection riêng không được quản lý có thể làm ý định rollback không đúng.

Ví dụ cấu hình **minh họa, không runnable độc lập** vì `DataSource`, JDBC driver, repository và các bean kết nối database phải được cung cấp:

~~~java
@Configuration
@EnableTransactionManagement
class TransactionConfig {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

Những tên cần import ở đoạn này:

- `@Configuration`: `org.springframework.context.annotation.Configuration`
- `@EnableTransactionManagement`: `org.springframework.transaction.annotation.EnableTransactionManagement`
- `PlatformTransactionManager`: `org.springframework.transaction.PlatformTransactionManager`
- `DataSource`: `javax.sql.DataSource` (API JDBC trong JDK)
- `JdbcTransactionManager`: `org.springframework.jdbc.support.JdbcTransactionManager`

Với `@Transactional`, mặc định trong Spring 6.x là propagation `REQUIRED`, isolation `DEFAULT` và rollback khi có `RuntimeException`/`Error`; checked exception **không tự gây rollback theo mặc định** trừ khi có quy tắc bổ sung. Spring 6.2 có tùy chọn cấu hình default rollback khác, vì thế khi áp dụng cần kiểm tra policy thực tế.

### 4.2. Proxy giao dịch và database là hai tầng khác nhau

~~~text
Caller
  |
  v
Transactional proxy  [spring-tx + AOP infrastructure]
  |-- mở/tham gia transaction thông qua TransactionManager
  |-- gọi business method
  |-- commit / rollback theo policy
  v
OrderService (business logic)
  |
  v
Repository / JDBC / JPA
  |
  v
Database resource
~~~

`spring-tx` định nghĩa API và interceptor; nó không tự thay database, connection pool, JDBC driver hoặc mapper. `@Transactional` cũng **không biến nhiều hệ thống độc lập thành một distributed transaction** nếu không có giao thức/quản lý phù hợp.

Một lỗi kinh điển:

~~~java
class OrderService {
    public void place() {
        this.save();        // self-invocation trong cùng target
    }

    @Transactional
    public void save() {
        // thao tác với DB
    }
}
~~~

Trong cơ chế proxy mặc định, lời gọi `this.save()` không đi qua transactional proxy; **không thể trông chờ một giao dịch mới được tạo chỉ bởi annotation của `save`**. Nếu `place()` đã chạy trong một giao dịch khác thì nó có thể tiếp tục sử dụng giao dịch hiện hữu; kết luận chính xác là **advice cho `save` không được kích hoạt ở lời gọi nội bộ**.

Để tránh nhầm: hãy gọi method transactional qua Spring-managed dependency/proxy, hoặc cấu trúc lại ranh giới service rõ ràng; kiểm thử tình huống commit/rollback bằng database test thực, không chỉ quan sát log.

### 4.3. Transaction không đồng nghĩa AOP nào cũng là transaction

Spring AOP có thể dùng cho tracing mà **không có database hoặc transaction manager**. Ngược lại, transaction management có thể áp dụng trong một ứng dụng batch/CLI **không có HTTP server**. Các module liên quan, nhưng là các khái niệm và hạ tầng tách biệt.

Với xử lý reactive, cần lựa chọn `ReactiveTransactionManager` và ngữ cảnh reactive phù hợp; không thể suy diễn rằng transaction dựa trên thread-local cho mã JDBC blocking luôn áp dụng nguyên xi cho pipeline reactive.

## 5. Ranh giới với các mô-đun web

### 5.1. IoC container không phải HTTP server

Một `AnnotationConfigApplicationContext` có thể tạo bean cho ứng dụng Java console, CLI, batch hoặc test. Nó **không tự tạo HTTP endpoint** chỉ vì có bean service.

Ví dụ:

~~~java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
~~~

Đoạn này là minh họa cần khai báo các kiểu liên quan. Bean `OrderService` tồn tại trong context nhưng không có `GET /orders` hoặc cổng 8080 nào tự xuất hiện.

### 5.2. Spring Web MVC: Servlet stack

Mô-đun chính `spring-webmvc` dựa trên Servlet API. Thành phần trung tâm là **`DispatcherServlet`**, một front controller: nhận HTTP request, tìm handler thích hợp, binding tham số, gọi controller, xử lý return value và phản hồi/lỗi.

Một controller minh họa:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {
    private final OrderLookup lookup;

    OrderController(OrderLookup lookup) {
        this.lookup = lookup;
    }

    @GetMapping("/{id}")
    String find(@PathVariable String id) {
        return lookup.find(id);
    }
}
~~~

Khối này **không runnable độc lập**: còn thiếu định nghĩa `OrderLookup`, import web, component registration, cấu hình dispatcher và runtime web.

Để client thực sự gọi `GET /orders/7`, cần có cấu hình Spring MVC, môi trường servlet/web server tương thích, handler mapping/adapter, HTTP serialization hoặc view resolution và vòng đời web app. Với Spring Boot, những phần thường được auto-configure bằng starter web; với Spring Framework thuần, phải bootstrap web infrastructure tương ứng.

### 5.3. Spring WebFlux: reactive stack

`spring-webflux` là framework web reactive, có front controller **`DispatcherHandler`** và các pipeline dựa trên Reactor/Reactive Streams theo cấu hình phù hợp. Nó có thể chạy trên runtime như Netty hoặc adapter Servlet hỗ trợ.

`WebFlux` không đồng nghĩa đơn giản với “MVC nhưng mọi method async”. Nên hiểu:

- Cách biểu diễn kết quả như `Mono`/`Flux` và luồng xử lý non-blocking/backpressure khi stack và các dependency phù hợp.
- WebFlux có handler mapping, adapter, result handler riêng; không dùng `DispatcherServlet` của Spring MVC làm bộ điều phối mặc định.
- Dùng WebFlux **không tự làm JDBC blocking trở thành non-blocking**. Khi thiết kế hệ thống reactive cần cân nhắc driver, transaction và luồng công việc.
- Core DI vẫn có thể inject service/repository vào web handler như ứng dụng MVC.

### 5.4. Có thể dùng Core, AOP và Tx mà không có Web

Sơ đồ luồng hai kiểu ứng dụng:

~~~text
CLI / Scheduler -----------> Service bean
                                |
Web Client -> Dispatcher -> Controller bean -> Service bean
                                |
                   [AOP / transaction proxy nếu bật]
                                |
                           Repository bean -> DB
~~~

**HTTP dispatcher là một tầng biên**; nó không quyết định bean được tạo như thế nào. **Transaction thường nằm ở service/use-case boundary**, không phụ thuộc việc lời gọi xuất phát từ CLI, HTTP hay job scheduler.

Nếu chỉ cần học cách bean được tạo/inject, hãy chạy ví dụ `AnnotationConfigApplicationContext` không web. Nếu cần test HTTP mapping, mới khởi động hạ tầng MVC/WebFlux. Nếu cần test transaction, phải chuẩn bị transaction manager/tài nguyên để chứng minh commit/rollback.

## 6. Bảng module và phụ thuộc cần nhớ

| Module / sản phẩm | Trách nhiệm điển hình | Không nên suy diễn |
| --- | --- | --- |
| `spring-core`, `spring-beans` | Utility nền, bean factory, dependency wiring | Không phải HTTP router hoặc transaction manager |
| `spring-context` | `ApplicationContext`, config, events, message source | Không tự chạy web server |
| `spring-aop` | Proxy và interceptor cho AOP | Không tự khởi động aspect nếu thiếu registration/config |
| `spring-tx` | Transaction abstraction, advice và annotation | Không tự cung cấp JDBC connection/database |
| `spring-jdbc` | JDBC helper và transaction manager JDBC | Không thay thế database/driver |
| `spring-orm` | Integration cho ORM/JPA | Không phải Core DI; còn cần JPA provider/config |
| `spring-webmvc` | HTTP trên Servlet stack | Không phải một `ApplicationContext` console |
| `spring-webflux` | HTTP reactive stack | Không làm blocking code tự chuyển sang reactive |
| **Spring Boot** (dự án riêng) | Starter, auto-configuration, application bootstrap | Không phải tên khác của Spring Core Container |
| **Spring Security** (dự án riêng) | Authentication/authorization, security filter/method security | Không tự xuất hiện vì có `@Service` |

**Lưu ý về Maven:** danh sách trên mô tả trách nhiệm; dependency transitively đi kèm nhau tùy phiên bản. Có thể thấy `spring-aop` xuất hiện trên classpath do module khác kéo vào, nhưng **có JAR trên classpath không đồng nghĩa advice đã được bật hoặc đang chạy**. Ngược lại, ứng dụng không cần tất cả module để dùng DI thuần.

## 7. Ví dụ Java 17 chạy được: IoC thuần và AOP là hai bước khác nhau

Ví dụ này chạy **không cần Spring Boot, web server, database hay transaction manager**. Nó mở hai `ApplicationContext`:

1. Context đầu chỉ cung cấp `ProcessingService` qua `@Bean`, nên gọi method mà **không có advice**.
2. Context thứ hai cũng tạo service nhưng bật `@EnableAspectJAutoProxy` và đăng ký aspect. Lúc này đối tượng tra cứu qua interface là AOP proxy và có thêm dòng log **trước** business method.

Ta cố tình dùng cùng một business service để quan sát **thay đổi ở hạ tầng**, chứ không phải thay đổi nội dung method.

### 7.1. Dự án Maven

Yêu cầu JDK 17+, Maven và khả năng tải dependency lần đầu. Dùng Spring Framework **6.2.0** (một bản Spring 6 tương thích Java 17). Cấu trúc:

~~~text
spring-boundaries/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BoundaryDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-boundaries</artifactId>
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
                    <mainClass>demo.BoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao ghi `spring-aop` và `aspectjweaver` rõ ràng?** Để mục đích AOP của demo không dựa vào giả định dependency tình cờ. Đây là ví dụ `@AspectJ`-style qua Spring AOP **proxy-based**, không yêu cầu agent bytecode weaving.

### 7.2. Tệp Java hoàn chỉnh

Tạo `src/main/java/demo/BoundaryDemo.java`:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class BoundaryDemo {
    public interface ProcessingService {
        void process(String id);
    }

    public static class DefaultProcessingService implements ProcessingService {
        @Override
        public void process(String id) {
            System.out.println("BUSINESS " + id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CoreConfig {
        @Bean
        public ProcessingService processingService() {
            return new DefaultProcessingService();
        }
    }

    @Aspect
    public static class TraceAspect {
        @Before("execution(* process(..))")
        public void beforeProcess() {
            System.out.println("TRACE before");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy
    @Import(CoreConfig.class)
    public static class AopConfig {
        @Bean
        public TraceAspect traceAspect() {
            return new TraceAspect();
        }
    }

    public static void main(String[] args) {
        // 1. Chỉ IoC: bean và constructor/factory method, KHÔNG có aspect.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            ProcessingService service =
                    context.getBean(ProcessingService.class);
            System.out.println("CORE proxy=" + AopUtils.isAopProxy(service));
            service.process("A01");
        }

        // 2. IoC + AOP: bật auto-proxy và đăng ký aspect trong context khác.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AopConfig.class)) {
            ProcessingService service =
                    context.getBean(ProcessingService.class);
            System.out.println("AOP proxy=" + AopUtils.isAopProxy(service));
            service.process("B02");
        }
    }
}
~~~

Tại thư mục `spring-boundaries`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Các dòng do `BoundaryDemo` chủ động in ra stdout theo thứ tự:**

~~~text
CORE proxy=false
BUSINESS A01
AOP proxy=true
TRACE before
BUSINESS B02
~~~

`mvn -version` còn in thông tin Maven/JDK; Maven hoặc thư viện có thể in thêm log tùy cấu hình và môi trường. Khối trên liệt kê **output của code demo**, không bảo đảm đó là toàn bộ text của terminal. Không cần gửi HTTP request hay kết nối database.

### 7.3. Phân tích vì sao output khác

1. Cả hai context đều đọc bean definition `processingService()` và tạo `DefaultProcessingService` qua `@Bean`: đó là **năng lực IoC**.
2. Ở context đầu, không có proxying infrastructure cho aspect nên `AopUtils.isAopProxy` trả `false` và `process("A01")` chỉ in nghiệp vụ.
3. Ở context thứ hai, `@EnableAspectJAutoProxy` cấu hình việc áp dụng advice, `TraceAspect` là Spring bean và pointcut chọn method `process(..)`. Spring trả proxy của service: `AopUtils.isAopProxy` trả `true`.
4. Lời gọi từ `main` đi **qua proxy**, kích hoạt `@Before` in `TRACE before` rồi target chạy và in `BUSINESS B02`.
5. Ví dụ không đăng ký `PlatformTransactionManager`, không thêm `@Transactional`, không dùng web module. **AOP hoạt động không có nghĩa transaction hoặc HTTP đang hoạt động**.

**Lưu ý:** Pointcut `execution(* process(..))` được cố tình chọn đơn giản trong demo để không phụ thuộc package của service. Trong ứng dụng lớn, hãy giới hạn pointcut theo package/interface/annotation thích hợp để tránh áp dụng advice cho các method trùng tên không mong muốn.

## 8. Thêm giao dịch hoặc web: việc gì thay đổi?

### 8.1. Khi thêm transaction

Một use case ghi dữ liệu vào DB sẽ cần repository và driver/data source thật. Ví dụ luồng:

~~~text
Client (CLI/Web/Job)
    -> Spring-managed Service proxy (@Transactional nếu cấu hình)
    -> Repository (JDBC/JPA)
    -> Database
~~~

Bạn phải thêm transaction manager phù hợp, bật cơ chế transaction, cấu hình data source/JPA và kiểm thử hành vi rollback. **Không thể sửa demo `BoundaryDemo` bằng cách thêm `@Transactional` vào một method rồi tuyên bố có transaction database** khi thiếu tài nguyên.

**Một test chứng minh transaction thật** nên:

- Chuẩn bị dữ liệu trước khi gọi service.
- Trong service, ghi một số dòng rồi cố ý ném một unchecked exception.
- Gọi qua Spring-managed proxy.
- Đọc lại database sau lỗi: dữ liệu đã ghi phải rollback theo policy dự kiến.
- Kiểm tra cả trường hợp lỗi được catch/nuốt và checked exception, vì policy rollback không mặc định giống nhau.

### 8.2. Khi thêm HTTP

Để service được gọi qua HTTP, cần controller và web framework:

~~~text
HTTP GET /orders/7
  -> DispatcherServlet (Spring MVC)
  -> OrderController bean
  -> OrderService bean
  -> repository/data source (nếu có)
  -> HTTP response
~~~

Với WebFlux, thay bộ điều phối bằng `DispatcherHandler` cùng reactive infrastructure. Dịch vụ và repository vẫn có thể là bean, nhưng cách xử lý request/response và semantics của reactive cần kiểm tra riêng.

Đừng đưa logic SQL, HTTP binding hay code tạo bean vào cùng một lớp chỉ vì nó được Spring quản lý. Các tầng có thể tương tác qua interface và constructor injection với trách nhiệm rõ ràng.

## 9. Nhận diện lỗi thường gặp

| Triệu chứng hoặc hiểu nhầm | Giải thích và hướng xử lý |
| --- | --- |
| Có `@Component` nhưng tưởng tự có HTTP endpoint | Cần controller mapping và MVC/WebFlux dispatcher/server |
| Gắn `@Aspect` vào class nhưng advice không chạy | Kiểm tra bean registration, auto-proxy infrastructure, pointcut và lời gọi đi qua proxy |
| Tạo service bằng `new` bên ngoài container rồi chờ advice | Đối tượng đó không tự được Spring proxy |
| Advice chạy khi gọi từ controller nhưng không chạy khi gọi nội bộ | Self-invocation qua `this` bỏ qua proxy |
| Dùng `final` class/method rồi mong class-based proxy advise | Proxy subclass có giới hạn với `final` |
| Gắn `@Transactional` rồi kết luận chắc chắn rollback | Cần transaction interceptor, manager, tài nguyên tham gia và policy đúng |
| Bắt `RuntimeException` bên trong method transactional rồi trả bình thường | Nếu không đánh dấu rollback-only và không ném lỗi ra boundary, có thể commit |
| Dùng transaction JDBC nhưng kết nối riêng không tham gia transaction | Kiểm tra cách lấy connection/binding và manager |
| Coi mỗi HTTP request mặc định là một DB transaction | HTTP dispatcher không tự định nghĩa transaction nghiệp vụ |
| Cho rằng `spring-context` nghĩa là đã có web server | Core `ApplicationContext` chạy được trong CLI, không cần HTTP |
| Dùng WebFlux để kỳ vọng JDBC blocking không làm block | Phải đánh giá blocking dependency, scheduler và reactive driver |
| Dùng Spring Boot rồi nghĩ mọi module Spring tự được thêm | Starter/auto-config chọn thành phần theo dependency và condition, không phải “bật hết” |

## 10. Tình huống luyện tập có đáp án

**Tình huống A.** `@Service class InventoryService` được scan thành bean nhưng không có `@Transactional`, không bật web. Có thể inject vào bean khác không? Có tự rollback khi method ghi DB lỗi không?

**Trả lời:** Nếu scan thành công và dependency không mơ hồ, có thể inject. Nhưng không có đủ căn cứ để kết luận có transaction tự động hoặc rollback. Việc truy cập DB phụ thuộc code và hạ tầng cụ thể.

**Tình huống B.** Có `@EnableAspectJAutoProxy` và `@Aspect`, nhưng service gọi `this.doWork()`. Advice nhắm vào `doWork` có nhất thiết chạy không?

**Trả lời:** Không. Với Spring AOP proxy-based, lời gọi nội bộ trực tiếp không đi qua proxy. Nên tách method cần advice vào collaborator phù hợp hoặc thay cách định ranh giới.

**Tình huống C.** Ứng dụng CLI chỉ cần `@Configuration`, `@Bean` và constructor injection, không HTTP hay DB. Có bắt buộc dùng Spring Boot/web/transaction không?

**Trả lời:** Không. `AnnotationConfigApplicationContext` của Spring Framework có thể khởi tạo và nối bean trong ứng dụng Java không web.

**Tình huống D.** Một controller có `@GetMapping("/ping")` được Spring tạo thành bean trong một `AnnotationConfigApplicationContext` thông thường. Có thể mở trình duyệt truy cập ngay không?

**Trả lời:** Chưa. Cần web dispatcher và runtime HTTP thích hợp. Bean management và HTTP routing là hai khả năng khác nhau.

**Tình huống E.** Nhóm thêm `spring-tx` vào Maven; bây giờ mọi method service đều transactional chưa?

**Trả lời:** Chưa. Thư viện trên classpath không đủ; còn phải kích hoạt cơ chế transaction, có manager và lời gọi phù hợp. Annotation và bean registration là một phần của cấu hình, không phải toàn bộ điều kiện.

## 11. Checklist khi thiết kế ứng dụng Spring

1. **Chia trách nhiệm:** ai sở hữu business logic, ai tạo bean, ai áp dụng advice, ai quản lý transaction, ai tiếp nhận HTTP.
2. **Bắt đầu từ IoC:** định nghĩa các collaborator quan trọng qua bean và constructor injection, tránh service tự tra cứu `ApplicationContext` tràn lan.
3. **AOP có chủ đích:** xác định pointcut/advice cụ thể, gọi qua Spring proxy, kiểm thử cả self-invocation và proxy type.
4. **Transaction rõ ràng:** chọn `TransactionManager` khớp resource, đặt boundary trên use case đúng, test rollback/commit thật.
5. **HTTP ở lớp biên:** controller làm mapping, validation và chuyển dữ liệu; logic nghiệp vụ nên ở service riêng.
6. **Chọn MVC/WebFlux theo nhu cầu:** không dùng WebFlux chỉ vì “nó mới hơn”, cũng không mặc định MVC cần reactive stack.
7. **Hiểu module/dependency:** đưa đúng thư viện cần thiết vào build, không đánh đồng classpath với việc đã bật feature.
8. **Giữ test nhanh:** unit test logic với Java thuần/fake; Spring context test để xác nhận wiring/aspect/tx; web test khi cần kiểm tra mapping và HTTP behavior.
9. **Không tin annotation đơn lẻ:** luôn hỏi “ai đọc metadata này, lúc nào, trên object nào, và lời gọi đi qua hạ tầng nào?”.
10. **Đánh giá lỗi và vòng đời:** singleton mutable có cần đồng bộ? database transaction có rollback? server/context được khởi động/đóng ở đâu?

**Kết luận:** **Core Container giải quyết tạo và nối bean**. **AOP mở rộng lời gọi phương thức bằng proxy/advice**, **transaction management điều phối ranh giới commit/rollback với tài nguyên thật**, còn **Spring MVC/WebFlux xử lý giao thức HTTP**. Chúng bổ trợ lẫn nhau nhưng không thay thế nhau. Hiểu rõ ranh giới giúp tránh lỗi kiểu “có annotation là chạy”, đặt trách nhiệm đúng lớp và xây dựng ứng dụng Spring có thể kiểm thử, bảo trì và mở rộng.

### Tài liệu Spring Framework chính thức để đối chiếu

- [IoC Container và BeanFactory/ApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/introduction.html)
- [Spring AOP proxying và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Declarative transactions và @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)