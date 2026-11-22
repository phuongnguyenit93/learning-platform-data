# Lời gọi qua Spring bean so với đối tượng tự tạo bằng `new`

## 1. Vấn đề cốt lõi: annotation có mặt nhưng advice có chạy không?

Trong Spring Security, một phương thức có `@PreAuthorize` không tự bảo vệ chính nó chỉ nhờ annotation nằm trên mã nguồn. Với cấu hình **Spring AOP proxy** thông dụng, Spring cần quản lý đối tượng và tạo một **proxy** ở ranh giới lời gọi. Lệnh được gọi **qua proxy** mới đi qua các bộ chặn (interceptor/advice) của method security. Tương tự, `@Transactional` thường cần một transaction interceptor để mở, tham gia, commit hoặc rollback giao dịch.

So sánh trực tiếp:

```java
// Có thể nhận proxy do Spring quản lý:
OrderService managed = applicationContext.getBean(OrderService.class);
managed.changeOrder(42L);       // Method security/transaction advice có cơ hội chạy.

// Đối tượng tự tạo độc lập:
OrderService manual = new OrderService();
manual.changeOrder(42L);        // Gọi thẳng method, bỏ qua advice của Spring AOP.
```

Đây là **đoạn minh họa về tham chiếu đối tượng**, không phải chương trình Java độc lập: `OrderService` và cấu hình ứng dụng được giả định đã tồn tại. Trường hợp đầu chỉ được bảo vệ khi **method security thực sự đã bật**, có advisor khớp với method và bean đã được proxy. Không phải mọi Spring bean đều tự động có proxy.

Hậu quả của việc tự tạo service bằng `new` có thể nghiêm trọng:

- Phương thức gắn `@PreAuthorize("hasAuthority('ORDER_WRITE')")` vẫn chạy dù caller không có quyền đó.
- `@Transactional` trên chính phương thức không tự kích hoạt một transaction interceptor.
- Dependency injection, `@PostConstruct`, cấu hình bean scope và một số vòng đời do container quản lý không áp dụng cho đối tượng tự tạo ngoài container.
- Unit test gọi `new Service()` có thể chạy xanh nhưng **không kiểm tra được enforcement** của Spring method security hoặc transaction proxy.

**Điểm cần nhớ:** “Đối tượng có annotation” và “lời gọi thực sự được Spring chặn” là hai điều khác nhau. Bài này tập trung vào sự khác biệt đó trong **Spring Security authorization** và **giao dịch**.

## 2. Spring bean, target và proxy là gì?

**Bean do Spring quản lý** là đối tượng được đăng ký trong `ApplicationContext`; Spring chịu trách nhiệm tạo hoặc nhận đối tượng, inject phụ thuộc, áp dụng BeanPostProcessor và quản lý vòng đời theo scope.

**Target** là đối tượng triển khai logic nghiệp vụ. **Proxy** là đối tượng đại diện đứng giữa caller và target, có thể chạy logic cắt ngang trước/sau lời gọi như phân quyền hoặc giao dịch. Trong proxy mode, chính **tham chiếu mà caller cầm** quyết định liệu lời gọi có đi qua interceptor hay không.

Hai đường đi:

```text
A. Caller nhận Spring bean có proxy
   Controller / service khác
             |
             v
      Spring AOP proxy
             |
      +------+-----------------------------+
      | @PreAuthorize: kiểm tra quyền      |
      | @Transactional: transaction advice|
      | Các advisor liên quan khác        |
      +------+-----------------------------+
             |
             v
         Target method
             |
             v
         Return/exception

B. Caller tự tạo đối tượng ngoài container
   Caller
      |
      v
   new Service(...)
      |
      v
   Target method
   (không qua các Spring AOP interceptor)
```

Không nên hiểu biểu đồ A là **thứ tự cố định** của security và transaction advice: thứ tự tùy advisor và cấu hình. Phần bất biến quan trọng của proxy mode là lời gọi ngoài đi qua proxy mới được kiểm tra bởi các advice tương ứng. Một interceptor có thể từ chối lời gọi trước khi thân phương thức chạy.

### Phân biệt ba điều kiện

| Câu hỏi | Ý nghĩa | Nếu thiếu |
| --- | --- | --- |
| Đối tượng có nằm trong Spring container? | `@Service`, `@Component`, `@Bean` hoặc cách đăng ký khác | Chưa có quản lý bean và proxy tự động |
| Method security/transaction infrastructure đã được bật? | `@EnableMethodSecurity`, transaction management và transaction manager thích hợp | Bean có thể tồn tại nhưng annotation chưa được thực thi |
| Caller có tham chiếu đi qua proxy đúng method? | Controller, service khác, hoặc `ApplicationContext.getBean` nhận bean đã được proxied | `new`, self-invocation hoặc method không thể proxy sẽ bypass advice |

Do đó, câu “lấy Spring bean thì chắc chắn có phân quyền” là **quá rộng**. Phải xét cả cấu hình, advisor, annotation, đặc tính method và đường đi lời gọi.

## 3. Vì sao `new` không kích hoạt `@PreAuthorize`?

Với `@EnableMethodSecurity`, Spring Security đăng ký những advisor/interceptor cho `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` theo cấu hình. Một lời gọi `@PreAuthorize` qua proxy sẽ được `AuthorizationManagerBeforeMethodInterceptor` xử lý; manager đánh giá biểu thức SpEL dựa trên `Authentication`, tham số method và các chính sách liên quan.

Ví dụ:

```java
@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOCUMENT_DELETE')")
    public String deleteDocument(long id) {
        return "deleted-" + id;
    }
}
```

Nếu một controller nhận `DocumentService` qua constructor injection, controller thường đang giữ Spring bean (trong cấu hình được proxy). Một tài khoản chỉ có `DOCUMENT_READ` sẽ bị từ chối khi gọi `deleteDocument` qua proxy.

Ngược lại:

```java
DocumentService direct = new DocumentService();
System.out.println(direct.deleteDocument(42L));
```

Stdout của đoạn **Java đơn giản này trong điều kiện không có phụ thuộc khác** là:

```text
deleted-42
```

Với instance `direct`, Spring không nhìn thấy lời gọi, nên **không chạy bộ chặn `@PreAuthorize`**. Dù code có thể đọc `SecurityContextHolder` thủ công, điều đó không làm một lời gọi trực tiếp tự đi qua interceptor.

### `@EnableMethodSecurity` là bước cần thiết

Spring Boot Starter Security **không tự bật method-level authorization** chỉ nhờ thêm dependency. Với ứng dụng Servlet/Bộ điều khiển phương thức thông thường, cần:

```java
@Configuration
@EnableMethodSecurity
class SecurityMethodConfig {
}
```

Hai import:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
```

`@SpringBootApplication` cũng mang đặc điểm của một lớp cấu hình; có thể đặt `@EnableMethodSecurity` trực tiếp trên class ứng dụng. Bật method security không thay thế cấu hình bảo vệ HTTP endpoints, authentication provider, CSRF hay các chính sách ở tầng web.

## 4. `@Transactional` chịu ảnh hưởng tương tự

Trong transaction proxy mode mặc định, `@Transactional` được diễn giải bởi transaction advisor. Khi lời gọi đi qua proxy, nó có thể mở transaction, gắn transaction vào thread và đảm bảo commit/rollback theo quy tắc. Một lời gọi trực tiếp vào instance tạo bởi `new` **không kích hoạt transaction advisor của Spring chỉ vì annotation ở trên method**.

```java
@Service
public class TransferService {

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        debit(fromId, amount);
        credit(toId, amount);
    }
}
```

Đoạn trên là **minh họa nghiệp vụ**; `debit`/`credit` do hệ thống triển khai. Nếu một lời gọi bypass transaction advice mà mỗi cập nhật DB tự commit độc lập, lỗi ở `credit` có thể để lại `debit` đã commit. Đó là nguy cơ mất tính nguyên tử; hành vi thực tế còn phụ thuộc transaction manager, data access, auto-commit và transaction đang có.

Có một ngoại lệ cần hiểu chính xác: nếu `new TransferService()` được gọi **bên trong một transaction đã được mở bởi thành phần khác trên cùng thread**, thao tác DB của nó **có thể vẫn tham gia transaction hiện có**. Lỗi nằm ở chỗ annotation trên instance `new` **không tự tạo hoặc điều chỉnh ranh giới transaction mới**. Vì vậy không được phát biểu tuyệt đối “mọi lệnh gọi `new` luôn nằm ngoài giao dịch”.

Với `@Transactional(propagation = REQUIRES_NEW)`, khác biệt càng rõ: bỏ qua advice đồng nghĩa yêu cầu mở giao dịch mới và tạm dừng giao dịch hiện tại **không được thực hiện** bởi annotation đó.

## 5. Chương trình Spring Boot Java 17 chạy được: cùng một method, ba đường gọi

Demo này thể hiện đồng thời method security và transaction advice, không cần web server. Nó dùng:

- Java 17, Maven và Spring Boot **3.5.15** (Spring Framework 6.2 / Spring Security 6.x).
- `spring-boot-starter-security` để bật method security.
- `spring-boot-starter-jdbc` + H2 để có `PlatformTransactionManager` thực.
- `@EnableMethodSecurity` và `@EnableTransactionManagement` khai báo rõ ràng.
- Một class `GuardedService`, với một method có cả `@PreAuthorize` và `@Transactional`.
- Kiểm tra trạng thái transaction bằng `TransactionSynchronizationManager.isActualTransactionActive()`.

Đây là **demo thực thi được trong dự án Maven đầy đủ**, còn các đoạn khác được ghi rõ là minh họa kiến trúc. Demo không thay thế một hệ thống xác thực thực tế.

### 5.1. Cấu trúc dự án

```text
proxy-vs-new/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── ProxyVsNewApplication.java
                └── GuardedService.java
```

### 5.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.15</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>proxy-vs-new</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

H2 trong classpath giúp Spring Boot tự cấu hình data source và transaction manager. Không có bản ghi nào được thay đổi trong demo; transaction được mở chỉ để quan sát advice.

### 5.3. Tệp `src/main/java/demo/GuardedService.java`

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class GuardedService {

    @PreAuthorize("hasAuthority('DOC_WRITE')")
    @Transactional
    public String update() {
        boolean active =
                TransactionSynchronizationManager.isActualTransactionActive();
        return "executed, transaction=" + active;
    }

    public String callUpdateInternally() {
        return this.update();
    }
}
```

Ở đây:

- `update()` là một phương thức `public`, không `final`, phù hợp với class-based proxy.
- `@PreAuthorize` yêu cầu authority `DOC_WRITE`.
- `@Transactional` yêu cầu transaction advice cho lời gọi hợp lệ qua proxy.
- `callUpdateInternally()` cố ý dùng `this.update()` để minh họa **self-invocation**: lời gọi bên trong target không đi qua proxy thêm lần nữa.

Không viết logic bảo mật production theo `callUpdateInternally()`; nó chỉ có ý nghĩa như trường hợp lỗi để học.

### 5.4. Tệp `src/main/java/demo/ProxyVsNewApplication.java`

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableMethodSecurity
@EnableTransactionManagement
public class ProxyVsNewApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ProxyVsNewApplication.class);
        app.setDefaultProperties(Map.of(
                "spring.main.web-application-type", "none",
                "spring.main.banner-mode", "off",
                "logging.level.root", "OFF"
        ));
        try (ConfigurableApplicationContext ignored = app.run(args)) {
            // CommandLineRunner thực hiện các lời gọi trước khi run() trả về.
        }
    }

    @Bean
    CommandLineRunner compareCalls(GuardedService managed) {
        return args -> {
            GuardedService manuallyCreated = new GuardedService();

            System.out.println("Spring bean proxy: "
                    + AopUtils.isAopProxy(managed));
            System.out.println("new instance proxy: "
                    + AopUtils.isAopProxy(manuallyCreated));

            try {
                authenticate("reader", "DOC_READ");

                try {
                    System.out.println("bean + reader: " + managed.update());
                } catch (AccessDeniedException denied) {
                    System.out.println("bean + reader: DENIED");
                }

                System.out.println("new + reader: "
                        + manuallyCreated.update());

                System.out.println("self-call + reader: "
                        + managed.callUpdateInternally());

                authenticate("writer", "DOC_WRITE");
                System.out.println("bean + writer: " + managed.update());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticate(String username, String authority) {
        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                        username,
                        "ignored",
                        List.of(new SimpleGrantedAuthority(authority))
                )
        );
        SecurityContextHolder.setContext(context);
    }
}
```

**Lưu ý:** `authenticate(...)` chỉ tạo `Authentication` thử nghiệm bằng mã Java; không phải endpoint đăng nhập hay phương án xác thực production. Trong HTTP application thật, `SecurityFilterChain` và authentication infrastructure được cấu hình để xác thực caller.

### 5.5. Biên dịch và chạy

Từ thư mục `proxy-vs-new` (cần JDK 17+, Maven và tải được dependencies Maven Central):

```bash
mvn -q clean package
java -jar target/proxy-vs-new-1.0.0.jar
```

Các dòng do chương trình in ra khi chạy với cấu hình trên:

```text
Spring bean proxy: true
new instance proxy: false
bean + reader: DENIED
new + reader: executed, transaction=false
self-call + reader: executed, transaction=false
bean + writer: executed, transaction=true
```

### 5.6. Giải thích từng dòng

| Lời gọi | Authorization | Transaction | Vì sao |
| --- | --- | --- | --- |
| `AopUtils.isAopProxy(managed)` | — | — | Spring trả về bean có proxy vì advisor khớp class/method |
| `AopUtils.isAopProxy(manuallyCreated)` | — | — | Instance `new` độc lập không được container proxy |
| `managed.update()` với `DOC_READ` | Bị từ chối | Method không chạy | `@PreAuthorize` được xử lý qua proxy |
| `manuallyCreated.update()` với `DOC_READ` | Không bị advice kiểm tra | `false` trong demo | Caller gọi thẳng target; annotation inert trên đường gọi này |
| `managed.callUpdateInternally()` với `DOC_READ` | Bỏ qua kiểm tra ở `update()` | `false` trong demo | `this.update()` bypass proxy; method ngoài không mở transaction |
| `managed.update()` với `DOC_WRITE` | Cho phép | `true` | Proxy chạy security và transaction advice của `update()` |

Dòng `self-call + reader` đặc biệt quan trọng: **ngay cả khi đối tượng ban đầu đến từ Spring**, nội bộ cùng instance gọi `this.update()` cũng bỏ qua advice của method được gọi. Đường đi lời gọi mới là yếu tố quyết định.

`TransactionSynchronizationManager.isActualTransactionActive()` trả lời **đang có transaction gắn với thread hay không**, không khẳng định một nghiệp vụ đã commit thành công. Vì demo không có transaction bên ngoài bao quanh `new`/self-call, các trường hợp này in `false`.

## 6. Lỗi phổ biến hơn `new`: self-invocation trong cùng bean

Một service có thể nhận từ Spring đúng cách nhưng vẫn gọi method được annotation sai đường:

```java
@Service
public class OrderWorkflow {

    public void execute(long id) {
        approve(id); // Lời gọi ngầm qua this.approve(id).
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    @Transactional
    public void approve(long id) {
        // Thực hiện nghiệp vụ duyệt đơn hàng.
    }
}
```

Đây là **đoạn kiến trúc minh họa**, không phải chương trình độc lập. Nếu caller gọi `workflow.execute(id)` qua proxy, sau khi vào thân `execute`, lời gọi `approve(id)` là một lời gọi trực tiếp trên `this`; `@PreAuthorize` và `@Transactional` đặt ở **approve** không được kích hoạt cho lần gọi nội bộ đó.

Phân biệt:

```text
Controller -> proxy -> approve(id)
             ^ authorization + transaction của approve được áp dụng

Controller -> proxy -> execute(id) -> this.approve(id)
                            ^
                  không đi qua proxy tại lời gọi approve
```

Ngay cả khi `execute` tự có `@Transactional`, điều đó **không làm advice của `approve` chạy lại**. Nhưng nếu transaction của `execute` đã mở, `approve` có thể thực thi **bên trong transaction sẵn có**. Khác biệt chính là các quy tắc riêng của `approve` (như `REQUIRES_NEW`, `readOnly`, timeout hoặc `@PreAuthorize`) sẽ không được áp dụng bởi advice cho lời gọi nội bộ.

### Thiết kế khuyến nghị: tách thành hai Spring bean

```java
@Service
public class OrderWorkflow {
    private final OrderApprovalService approval;

    public OrderWorkflow(OrderApprovalService approval) {
        this.approval = approval;
    }

    public void execute(long id) {
        approval.approve(id); // Gọi qua bean được Spring inject.
    }
}
```

```java
@Service
public class OrderApprovalService {
    private final OrderRepository repository;

    public OrderApprovalService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    @Transactional
    public void approve(long id) {
        repository.markApproved(id);
    }
}
```

Hai class là **đoạn tích hợp vào ứng dụng có `OrderRepository`**, không phải dự án chạy độc lập; `markApproved` là thao tác của repository ứng dụng. Tách bean giúp `OrderWorkflow` giữ **proxy reference** của `OrderApprovalService`. Mỗi lời gọi `approval.approve` đi qua điểm chặn của service đích.

Với một service lớn, có thể tổ chức lớp orchestration và lớp thực thi nghiệp vụ có bảo vệ; tránh tạo bean mới chỉ để có thêm annotation ở mọi method nhỏ. Đặt security/transaction tại **ranh giới nghiệp vụ cần bảo vệ**.

## 7. Không phải mọi cú pháp `new` đều bypass Spring

Điều cần tránh là **đối tượng tạo thủ công rồi dùng trực tiếp bên ngoài container**. Việc một object được tạo bằng từ khóa `new` bên trong **factory method `@Bean`** không tự khiến nó mất cơ chế Spring:

```java
@Configuration
class OrderConfiguration {
    @Bean
    OrderService orderService() {
        return new OrderService();
    }
}
```

Khi `@Configuration` được Spring quản lý, đối tượng trả về từ `@Bean` trở thành bean và được xử lý bởi bean post-processors; nếu có matching advisors, Spring **có thể trả về proxy** của bean ấy. Không đăng ký đồng thời `@Service` và `@Bean` tạo hai bean cùng trách nhiệm nếu không có chủ đích.

So sánh:

| Cách tạo và dùng | Có trở thành Spring bean? | Advice AOP có thể tham gia? |
| --- | --- | --- |
| `new OrderService()` rồi gọi ngay trong code nghiệp vụ | Không | Không theo cơ chế proxy Spring tự động |
| `@Service` + constructor injection vào Controller | Có | Có, nếu infrastructure/advisor/method hợp lệ |
| `@Bean OrderService service() { return new OrderService(); }` rồi inject bean | Có | Có, khi Spring xử lý và proxy bean |
| `ApplicationContext.getBean(OrderService.class)` | Có | Lấy bean được cấu hình, có thể là proxy |
| `this.securedMethod()` bên trong target | Target đã managed nhưng lời gọi nội bộ không qua proxy | Advice của **securedMethod** bị bypass trong proxy mode |
| `new` rồi chủ động wrap bằng proxy factory của framework | Có thể được proxy theo cơ chế explicit | Chỉ những advisor được đưa vào proxy; không mặc định đủ toàn bộ vòng đời Spring bean |

**Phân biệt thêm:** một class không gắn `@Service` vẫn có thể là Spring bean qua `@Bean` hoặc cách đăng ký khác. Ngược lại, chỉ viết `@Service` trên class nhưng class nằm ngoài component-scan, hoặc tự `new` instance của class ấy, **không biến instance đó thành bean đã được proxy**.

## 8. Dependency injection và vòng đời: hệ quả ngoài AOP

Xét:

```java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('INVOICE_WRITE')")
    @Transactional
    public void change(long id) {
        repository.change(id);
    }
}
```

Với constructor injection, `new InvoiceService()` **không biên dịch** vì thiếu tham số. Nếu caller tự cung cấp `InvoiceRepository` rồi dùng `new InvoiceService(repo)`, business method có thể chạy, nhưng object này vẫn **không tự được Spring AOP intercept**. Constructor injection giúp dependency trở nên rõ ràng, không tự thay thế container management.

Với field injection:

```java
@Autowired
private InvoiceRepository repository;
```

Instance được tự `new` bên ngoài Spring thường có field `repository == null` nếu không tự gán, nên có thể ném `NullPointerException`. Dù vậy, cần tách rõ hai lỗi: **thiếu injection** và **thiếu AOP advice**. Sửa một lỗi không tự khắc phục lỗi kia.

Các cơ chế Spring khác cũng phụ thuộc lifecycle/bean management: configuration properties binding, `@PostConstruct`, `@PreDestroy`, bean scopes, sự tham gia vào các proxy của `@Async`, `@Cacheable` và transaction. Mỗi annotation có điều kiện kích hoạt riêng; không suy ra tất cả chúng luôn hoạt động chỉ vì class có `@Component`.

Không nên dựa vào proxy security/transaction ngay trong constructor hoặc `@PostConstruct` của chính bean. Ở giai đoạn khởi tạo, proxy có thể chưa được thiết lập đầy đủ cho lời gọi nội bộ.

## 9. JDK proxy, CGLIB và giới hạn method

Spring AOP có hai cơ chế phổ biến:

- **JDK dynamic proxy**: chủ yếu proxy interface; caller giữ interface type. Những method cần chặn phải thuộc bề mặt method mà proxy thực sự cung cấp.
- **CGLIB/class-based proxy**: proxy là subclass của target; có thể hỗ trợ gọi method concrete trên class, nhưng không override được `final` hoặc `private` methods.

Việc framework chọn JDK hay class-based proxy phụ thuộc cấu hình; Spring Boot có thể mặc định ưu tiên class-based trong một số tình huống, còn Spring Framework proxy settings có mặc định khác. Không đoán kiểu proxy chỉ từ việc class có interface.

| Tình huống | Rủi ro | Cách kiểm tra |
| --- | --- | --- |
| Bean có interface nhưng application mong inject concrete class | JDK proxy không phải instance của implementation class | Inject interface hoặc cấu hình proxy phù hợp |
| `final class` với class-based proxy | Không tạo được subclass proxy | Dùng interface/proxy phù hợp hoặc class không final |
| `final public method` với class-based proxy | Không override để chèn advice | Đặt điều kiện ở public method proxy được |
| `private method` gắn `@PreAuthorize`/`@Transactional` | Không thể được interceptor theo cách gọi qua proxy thông thường | Đưa kiểm soát về public service boundary |
| `this.method()` hoặc gọi ngầm `method()` | Bỏ qua proxy dù bean đã managed | Tách bean hoặc đổi đường đi |
| Gọi method trước khi Spring khởi tạo proxy hoàn chỉnh | Advice chưa thể đảm bảo | Không kích hoạt nghiệp vụ bảo mật trong constructor/`@PostConstruct` |

**Đặc biệt với Kotlin**, class/method là final mặc định; cấu hình plugin mở class cho Spring khi cần phải phù hợp với proxy strategy.

### Một số phép kiểm tra khi debug

```java
Object bean = context.getBean("guardedService");

boolean proxied = AopUtils.isAopProxy(bean);
boolean jdk = AopUtils.isJdkDynamicProxy(bean);
boolean cglib = AopUtils.isCglibProxy(bean);
```

Ba phép kiểm tra cần import `org.springframework.aop.support.AopUtils`. Đây là đoạn tích hợp có biến `context` là Spring `ApplicationContext`. Giá trị `isAopProxy == true` chỉ xác nhận object được proxy, **không chứng minh từng method cụ thể có advice bảo mật/transaction khớp**. Cần test hành vi bằng caller được phép/bị cấm và quan sát transaction thật.

## 10. Cách sửa an toàn trong ứng dụng thực

### Cách 1: inject Spring bean qua constructor (mặc định nên dùng)

```java
@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final DocumentCommandService service;

    public DocumentController(DocumentCommandService service) {
        this.service = service;
    }

    @PostMapping("/{id}/archive")
    public void archive(@PathVariable long id) {
        service.archive(id);
    }
}
```

Đây là đoạn tích hợp: `DocumentCommandService` là bean nghiệp vụ của ứng dụng và có các import Spring MVC thích hợp. Controller **không tự `new` service**. Method security của `archive` vẫn cần được bật và policy phải nằm ở boundary đúng.

### Cách 2: tách phương thức được bảo vệ sang bean khác

Nếu đang có `this.archive(id)`, chuyển `archive` sang service được inject như ví dụ `OrderApprovalService`. Đây thường là cách đơn giản nhất để tránh self-invocation mà không buộc mã nghiệp vụ hiểu AOP.

### Cách 3: dùng self proxy hoặc `AopContext.currentProxy()` có cân nhắc

Có thể inject proxy của chính mình hoặc dùng `AopContext.currentProxy()` khi cấu hình expose proxy. Tuy nhiên:

- Self injection có thể gây phụ thuộc vòng, khó đọc và khó test.
- `AopContext.currentProxy()` khiến business class phụ thuộc trực tiếp vào Spring AOP và cần cấu hình expose proxy đúng.
- Không thay đổi kiểu proxy chỉ để chữa một design có thể tách bean rõ ràng.

Vì thế, coi đây là phương án có điều kiện, không mặc định dùng trong mọi service.

### Cách 4: AspectJ weaving hoặc proxy thủ công

Spring hỗ trợ AspectJ mode cho những trường hợp cần advice hoạt động ở self-invocation vì bytecode được weave, nhưng chi phí build/runtime, cấu hình weaving và phạm vi annotation cần được kiểm chứng riêng. Đây là cơ chế khác proxy AOP, không mặc định bật cùng `@EnableMethodSecurity`.

Spring Security còn có `AuthorizationProxyFactory` cho **proxy thủ công** đối tượng khi cần method security trên một object không trực tiếp được Spring tạo. Điều này không đồng nghĩa object sẽ tự nhận đầy đủ `@Autowired`, mọi BeanPostProcessor hoặc transaction advice; phải xem proxy factory áp dụng advisor nào. Với service ứng dụng thông thường, constructor injection vào bean vẫn rõ ràng hơn.

## 11. Transaction và authorization: các tình huống dễ hiểu nhầm

### 11.1. `@Transactional` không thay thế authorization

Nếu một method đi qua transaction proxy nhưng bỏ qua method security, nó **vẫn có thể ghi dữ liệu trái quyền** trong một transaction hợp lệ. Ngược lại, method có authorization nhưng không có transaction phù hợp có thể ghi nhiều lần rồi hỏng giữa chừng. Cần cả hai khi nghiệp vụ yêu cầu.

### 11.2. Quyền ở controller không thay thế quyền ở service

Một lời gọi service có thể bắt nguồn từ HTTP, scheduler, message consumer, integration test hoặc một service khác. Đặt chính sách ở boundary service quan trọng nếu dữ liệu phải được bảo vệ nhất quán qua nhiều entry point. Bật authorization HTTP không tự làm `new Service()` chạy `@PreAuthorize`.

### 11.3. Lỗi xảy ra ở đâu quyết định rollback

Trong proxy mode, exception qua transaction advice chịu quy tắc rollback. Mặc định Spring rollback với `RuntimeException` hoặc `Error`, còn checked exception cần cấu hình `rollbackFor`/quy tắc tương ứng nếu muốn rollback. Không bắt lỗi rồi trả kết quả thành công khi nghiệp vụ cần rollback toàn bộ.

Không nên kết luận “`new` gây commit từng câu SQL” một cách tuyệt đối: nếu caller đã mở transaction và các thao tác tham gia cùng resource/thread, chúng có thể vẫn rollback theo transaction đó. Lỗi thực sự là **annotation của phương thức bypass không được tôn trọng như ranh giới giao dịch riêng**.

### 11.4. SecurityContext không phải bằng chứng có interceptor

Một method được gọi trên object tự tạo vẫn có thể đọc `SecurityContextHolder.getContext().getAuthentication()` khi caller đã đặt context cho thread. Nhưng như thế **không kích hoạt `@PreAuthorize`**. Tương tự, một method có thể thấy transaction active do caller khác mở, nhưng điều đó không chứng minh `@Transactional` trên method hiện tại đã được thực thi.

## 12. Kiểm thử thực tế để không bỏ lọt bypass

### Unit test thuần Java dùng `new`

Phù hợp để kiểm tra thuật toán, validate input, xử lý dữ liệu, gọi dependency mock. Nó **không phải integration test** chứng minh annotation-based method security hay transaction intercept.

### Integration test dùng Spring proxy

Ví dụ dự án có `spring-boot-starter-test` và `spring-security-test`:

```java
@SpringBootTest
class GuardedServiceSecurityTest {

    @Autowired
    GuardedService service;

    @Test
    @WithMockUser(authorities = "DOC_READ")
    void readerCannotCallSecuredMethodThroughBean() {
        assertThrows(AccessDeniedException.class, service::update);
    }

    @Test
    @WithMockUser(authorities = "DOC_WRITE")
    void writerRunsWithTransaction() {
        assertEquals("executed, transaction=true", service.update());
    }
}
```

Đây là **đoạn test tích hợp** (cần import các annotation/API JUnit 5, Spring test, Spring Security test). Test phải nhận bean từ application context, không tự tạo `new GuardedService()`, để kiểm tra được advice thật.

Khi kiểm thử giao dịch cơ sở dữ liệu, cần thêm test làm thay đổi dữ liệu rồi chủ động gây lỗi, xác minh trạng thái sau rollback. Kiểm tra `isActualTransactionActive()` là dấu hiệu hữu ích của việc advice tạo transaction, **chưa đủ** để chứng minh consistency của toàn bộ nghiệp vụ.

Ma trận test gợi ý:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Bean + caller thiếu authority | `AccessDeniedException`; thân method không chạy |
| Bean + caller đủ authority | Method chạy; transaction active khi infrastructure được cấu hình |
| Instance tạo thủ công bằng `new` | Annotation-based advice không tự chạy; không dùng làm chứng minh bảo mật |
| Proxy -> method A -> `this.methodB()` | Advice riêng của B bị bypass trong proxy mode |
| Proxy -> bean A -> bean B đã được inject | Advice của method B được áp dụng nếu khớp |
| `@Bean` trả đối tượng tạo bằng `new` | Bean vẫn được post-process/proxy khi cấu hình đúng |
| Có interface và JDK proxy | Caller sử dụng type interface và method nằm trong bề mặt proxy |
| Class/method `final` với CGLIB | Xác định được giới hạn proxy; test từ chối/cho phép thật |
| Caller có transaction sẵn | Không nhầm transaction inherited với transaction advice của method mới |
| Thêm `@Transactional(propagation = REQUIRES_NEW)` | Test thực sự mở transaction mới qua bean, không gọi nội bộ trực tiếp |

### Quan sát lỗi từ production

Nếu đang điều tra việc annotation “bị bỏ qua”:

1. Tìm nơi service được tạo: có `new SomeService(...)` hoặc factory tự giữ instance không?
2. Xác minh class đăng ký bean và nhận đúng Spring-managed reference từ DI.
3. Kiểm tra `@EnableMethodSecurity` và transaction manager / transaction proxy configuration.
4. Kiểm tra call stack: caller -> proxy -> target hay target -> `this.method`?
5. Kiểm tra proxy type, method visibility/`final`, advisor khớp annotation.
6. Viết một test thông qua Spring bean: thiếu quyền phải bị chặn và một transaction test phải có hiệu lực.
7. Chỉ sau đó kiểm tra biểu thức SpEL, authority mapping, rollback rules và config khác.

Không log access token, mật khẩu hoặc toàn bộ principal khi debug. Đủ để log method, vai trò/authority phù hợp, resource ID đã được kiểm soát và kết quả authorization theo quy định bảo mật.

## 13. Những câu hỏi thường gặp

**Có `@Service` trên class thì `new Service()` có được Spring bảo vệ không?** Không. `@Service` giúp component scan nhận diện class để đăng ký **một bean**; nó không khiến mọi instance của class được tạo ở nơi khác tự đi qua proxy.

**Có thể `@Autowired` một class rồi tự `new` một instance khác?** Có về mặt Java, nhưng hai object khác nhau. Method security/transaction advice áp dụng cho bean đã proxy; object tạo thủ công không tự có các interceptor đó.

**`@Bean` dùng `return new Foo()` có sai không?** Không. Đối tượng trả về được container đăng ký và có thể post-process/proxy. Phải phân biệt **cách tạo object** và **đường lấy object để gọi**.

**Tôi thấy `AopUtils.isAopProxy(bean) == true`, vậy mọi method có được bảo vệ?** Không. Proxy có thể được tạo cho transaction hoặc advisor khác; chỉ method được advisor khớp mới chịu advice tương ứng. Cần kiểm tra hành vi method cụ thể.

**Vì sao `this.securedMethod()` không bị kiểm tra nhưng `otherBean.securedMethod()` lại bị?** Lời gọi nội bộ `this` nhảy thẳng vào target; tham chiếu `otherBean` thường là proxy Spring trả về qua DI.

**Nếu một method không gắn `@PreAuthorize` gọi method có `@PreAuthorize` trong cùng class?** Trong proxy mode, lời gọi nội bộ có thể bypass `@PreAuthorize` của method thứ hai. Đừng dựa vào annotation của method thứ hai để bảo vệ một đường đi gọi nội bộ.

**Nếu tôi chỉ dùng JDK proxy thì method concrete có được chặn?** Chỉ những lời gọi có thể đi qua bề mặt proxy interface mới được interceptor ứng xử phù hợp; cần cân nhắc cấu hình proxy và cách đặt annotation. Spring Boot có thể cấu hình class-based proxy trong một số thiết lập.

**Nếu service gọi `new` được tạo bên trong một method có transaction?** Instance mới không được Spring AOP tự proxy. Nhưng thao tác DB của nó có thể dùng transaction đã tồn tại của caller trên cùng thread; không nhầm hiện tượng đó với việc `@Transactional` trên instance mới có hiệu lực.

**Nếu cần lập trình thủ công proxy một object?** Có cơ chế proxy factory/AspectJ chuyên dụng, nhưng phải chủ động cấu hình advisor và hiểu phạm vi. Đa số service ứng dụng nên đăng ký bean và inject rõ ràng.

## 14. Checklist trước khi đưa service vào production

- [ ] Business service có quyền truy cập nhạy cảm được đăng ký và lấy qua Spring container.
- [ ] Controller, listener, scheduler và service khác sử dụng constructor injection, không tự tạo service cần method advice.
- [ ] `@EnableMethodSecurity` đã bật nếu dựa vào `@PreAuthorize`/`@PostAuthorize`.
- [ ] Transaction manager và transaction management đã cấu hình nếu dùng `@Transactional`.
- [ ] Các method cần bảo vệ có thể được proxy; không dựa vào `private`, `final` hoặc self-invocation cho advice.
- [ ] Method được bảo vệ được gọi qua **proxy reference**, kể cả trong orchestration nội bộ.
- [ ] Không nhầm `@Bean { return new ...; }` với đối tượng `new` bên ngoài container.
- [ ] Có test **deny** cho caller thiếu quyền, **allow** cho caller đúng quyền và transaction rollback khi nghiệp vụ cần.
- [ ] Các trường hợp AOP proxy type (JDK/CGLIB), `REQUIRES_NEW`, nested calls và caller transaction được hiểu rõ.
- [ ] Không dùng unit test khởi tạo `new` làm bằng chứng method security đã được thực thi.

**Kết luận kỹ thuật:** Trong proxy mode của Spring, điều quyết định không phải việc class có `@Service`, `@PreAuthorize` hay `@Transactional` trong mã nguồn. Điều quyết định là **lời gọi có đi qua Spring AOP proxy với advisor phù hợp hay không**. Lấy bean từ container, bật đúng infrastructure và thiết kế lời gọi qua ranh giới bean giúp thực thi authorization/transaction nhất quán.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Framework 6.2 — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework — Transactional annotation và giới hạn proxy mode](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Security — Method security testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
