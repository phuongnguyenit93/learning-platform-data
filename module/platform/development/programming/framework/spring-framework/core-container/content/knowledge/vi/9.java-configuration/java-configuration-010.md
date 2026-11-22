# Tách việc tạo đối tượng khỏi công việc khởi tạo nghiệp vụ trong Spring Java Configuration

## 1. Mục tiêu và ý tưởng cốt lõi

Trong Spring Core Container, `@Configuration` và `@Bean` cho phép bạn nói với IoC container **đối tượng cần được tạo như thế nào** và **phụ thuộc vào những bean nào**. Nhưng một đối tượng tồn tại trong container không đồng nghĩa ứng dụng đã hoàn thành mọi **công việc khởi tạo nghiệp vụ** (business bootstrap), chẳng hạn nạp dữ liệu nền, kiểm tra điều kiện khai trương dịch vụ, lập danh mục tham chiếu, đăng ký với hệ thống ngoài hoặc kích hoạt một quy trình phục vụ vận hành.

Một lỗi thiết kế thường gặp là đưa những thao tác nghiệp vụ này vào ngay body của `@Bean`:

```java
// Phản ví dụ: không phải chương trình độc lập.
@Bean
CustomerService customerService(CustomerRepository repository) {
    CustomerService service = new CustomerService(repository);
    service.importSeedCustomers(); // Thao tác nghiệp vụ xảy ra khi tạo bean.
    return service;
}
```

Factory method giờ vừa **wiring** vừa **chạy một use case có side effect**. Hậu quả có thể là startup phụ thuộc I/O, giao dịch xảy ra quá sớm, test context gây thay đổi dữ liệu, khó retry, khó kiểm soát thứ tự và hành vi bị lặp lại khi bean/context được tạo thêm.

Nên tách ba trách nhiệm:

1. **Object construction / bean wiring:** tạo object, gán dependency, cấu hình immutable values. Đây là việc của constructor và `@Bean` factory methods.
2. **Bean-local initialization:** xác thực cấu hình, chuẩn bị cấu trúc nội bộ, mở tài nguyên thuộc sở hữu chính bean khi thật sự cần. Đây là việc của `@PostConstruct`, `@Bean(initMethod=...)` hoặc các lifecycle callback tương ứng.
3. **Application/business bootstrap:** điều phối hành động nghiệp vụ sau khi các cộng tác viên cần thiết đã sẵn sàng; có chính sách idempotency, transaction, lỗi và quan sát. Đây thường là việc của một **startup coordinator** hoặc một entry point nghiệp vụ rõ ràng, có thể được kích hoạt qua `SmartInitializingSingleton`, `ContextRefreshedEvent`, `SmartLifecycle` hoặc cơ chế runtime tương ứng.

**Nguyên tắc:** `@Bean` khai báo **cách dựng bean**; service nghiệp vụ khai báo **hành vi**; bootstrap coordinator quyết định **khi nào chạy hành vi khởi tạo**. Không biến constructor/factory method thành nơi thực thi workflow nghiệp vụ.

Bài học này thuộc **Cấu hình Java — Spring Framework Core Container**. Các cơ chế `ApplicationRunner`, `CommandLineRunner` và `ApplicationReadyEvent` của Spring Boot chỉ được nêu để so sánh tại ranh giới, không được dùng trong ví dụ Spring Framework thuần.

## 2. Ba giai đoạn khác nhau cần phân biệt

### 2.1. Giai đoạn A — tạo đối tượng và nối dependency

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
```

Đây là **minh họa cần định nghĩa** `OrderRepository`, `InMemoryOrderRepository`, `OrderService`. Vai trò của `@Bean` chỉ là dựng đối tượng và biểu diễn dependency:

- `orderRepository()` cung cấp object triển khai repository.
- `orderService(OrderRepository repository)` yêu cầu Spring phân giải repository rồi truyền vào service.
- Spring quyết định thời điểm tạo bean dựa trên scope, lazy/eager semantics và dependency graph.
- Không cần gọi nghiệp vụ như `service.placeOrder(...)` trong factory method.

Khi viết `@Configuration(proxyBeanMethods=false)`, truyền dependency qua **tham số factory method** còn giúp tránh direct call từ một `@Bean` method sang method khác gây tạo object ngoài bean identity. Đây là một nguyên tắc wiring, tách biệt với việc bootstrap có nên chạy hay không.

### 2.2. Giai đoạn B — bean-local initialization

Một số bean chỉ hoạt động được sau khi kiểm tra thuộc tính hoặc chuẩn bị trạng thái **của chính nó**:

```java
final class RulesIndex {
    private boolean ready;

    void initialize() {
        // Xây chỉ mục từ cấu hình đã có sẵn trong object.
        ready = true;
    }

    boolean isReady() {
        return ready;
    }
}
```

Có thể khai báo:

```java
@Bean(initMethod = "initialize")
RulesIndex rulesIndex() {
    return new RulesIndex();
}
```

Spring sẽ gọi `initialize()` theo lifecycle khi nó tạo và khởi tạo **managed bean**. Đây là phần chuẩn bị cục bộ, không phải chạy một quy trình tạo hóa đơn, phát email hay sửa dữ liệu kinh doanh.

`@PostConstruct` và `InitializingBean.afterPropertiesSet()` cũng phục vụ cùng nhóm vấn đề. Tuy nhiên, **các init callback thường chạy trong giai đoạn tạo singleton, dưới khóa khởi tạo singleton**. Spring khuyến cáo giữ chúng gọn, tập trung validate trạng thái/chuẩn bị cấu trúc cục bộ; không nên thực hiện tác vụ nặng, gọi lung tung sang các bean khác hoặc I/O phức tạp, vì có nguy cơ kéo dài startup hay gặp deadlock trong quá trình khởi tạo.

### 2.3. Giai đoạn C — business/application bootstrap

Ví dụ một ứng dụng cần bảo đảm dữ liệu khách hàng mẫu có mặt trước khi chấp nhận tác vụ. Đây là một **use case**: cần repository, service, chính sách chống tạo trùng, và có thể liên quan transaction/hệ thống ngoài.

Không nên viết:

```java
@Bean
CustomerService customerService(CustomerRepository repository) {
    CustomerService service = new CustomerService(repository);
    service.register("seed-001"); // Lẫn provisioning bean với use case.
    return service;
}
```

Nên có một coordinator riêng:

```java
// Minh họa: một Spring-managed startup bean.
final class SeedCustomers implements SmartInitializingSingleton {
    private final CustomerService customers;

    SeedCustomers(CustomerService customers) {
        this.customers = customers;
    }

    @Override
    public void afterSingletonsInstantiated() {
        customers.register("seed-001");
    }
}
```

`SmartInitializingSingleton` nằm trong `org.springframework.beans.factory`. Callback `afterSingletonsInstantiated()` được Spring gọi sau khi **hoàn tất pre-instantiation của các singleton thông thường, không lazy** trong bean factory. Nó phù hợp với công việc sau giai đoạn khởi tạo singleton; không nên nhầm là tất cả lazy/prototype beans đã được khởi tạo hoặc toàn bộ hệ thống phân tán đã sẵn sàng.

Ví dụ đầy đủ có thể chạy ở mục 6.

## 3. Vì sao trộn logic nghiệp vụ vào @Bean là vấn đề?

### Factory method bị biến thành lệnh nghiệp vụ

Một factory method lý tưởng chủ yếu có trách nhiệm:

```java
@Bean
InvoiceService invoiceService(InvoiceRepository repository,
                              InvoicePolicy policy) {
    return new InvoiceService(repository, policy);
}
```

Đoạn này chỉ wiring. Nếu thay bằng:

```java
@Bean
InvoiceService invoiceService(InvoiceRepository repository,
                              InvoicePolicy policy) {
    InvoiceService service = new InvoiceService(repository, policy);
    service.generateMonthlyInvoices(); // Side effect nghiệp vụ.
    return service;
}
```

người dùng không cần gọi `generateMonthlyInvoices()` mà công việc đã chạy trong lúc context dựng bean. Những tác hại thường gặp:

- **Startup khó dự đoán:** DB/network chậm có thể kéo dài hoặc làm hỏng context initialization.
- **Dễ chạy lặp:** integration tests, context refresh, nhiều ứng dụng/replica hoặc một scope tạo bean lại có thể khiến nghiệp vụ chạy nhiều lần.
- **Side effect ngoài ý muốn:** chạy test khởi tạo context có thể tự gửi email hoặc thay đổi dữ liệu thật.
- **Transaction không rõ:** gọi method ngay trong factory/constructor không tự bảo đảm nó đi qua proxy `@Transactional` mong muốn.
- **Khó vận hành:** không có điểm riêng cho idempotency, retry, metrics, logging, readiness hoặc rollback.
- **Khó kiểm thử:** chỉ muốn test wiring nhưng lại phải giả lập cả external services và dữ liệu.

Các class `InvoiceRepository`, `InvoicePolicy`, `InvoiceService` ở hai đoạn trên là kiểu giả định; đây là **phản ví dụ minh họa**, không phải project tự biên dịch.

### Constructor cũng không phải entry point nghiệp vụ

```java
final class InvoiceService {
    InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
        generateMonthlyInvoices(); // Thiết kế khó kiểm soát.
    }
}
```

Việc constructor gọi business workflow có cùng vấn đề: gây side effect trước khi object được dựng xong, khó kiểm thử, có thể phụ thuộc bean khác chưa sẵn sàng, và khó xác định retry/transaction.

Constructor nên ghi nhận/kiểm tra dependency và thiết lập invariant nội bộ, không làm các tác vụ tác động ra bên ngoài trừ khi việc mở một resource nội bộ là một phần hợp đồng xây đối tượng được cân nhắc kỹ.

### Đừng "chữa" bằng cách gọi thủ công @Bean method khác

```java
@Configuration(proxyBeanMethods = false)
class BadConfig {
    @Bean
    InvoiceRepository repository() {
        return new JdbcInvoiceRepository();
    }

    @Bean
    InvoiceService invoiceService() {
        InvoiceService service = new InvoiceService(repository());
        service.generateMonthlyInvoices();
        return service;
    }
}
```

Có **hai** rủi ro khác nhau:

1. `repository()` được gọi trực tiếp trong lite mode, có thể tạo repository **ngoài** bean do container quản lý.
2. `generateMonthlyInvoices()` bị chạy trong giai đoạn tạo bean.

Cách sửa: inject `InvoiceRepository` qua **tham số `@Bean`**, đồng thời dời việc chạy use case sang startup coordinator hoặc một lệnh nghiệp vụ được gọi có chủ đích.

## 4. Dùng cơ chế nào cho loại công việc nào?

| Việc cần làm | Vị trí thường phù hợp | Vì sao |
| --- | --- | --- |
| Dựng object, truyền dependency | Constructor, `@Bean` method | Factory/wiring rõ trách nhiệm |
| Kiểm tra tham số cấu hình cục bộ | Constructor hoặc bean init callback | Phát hiện cấu hình sai sớm |
| Chuẩn bị map/cache nhỏ từ dữ liệu đã có sẵn trong bean | `@PostConstruct`/`@Bean(initMethod)` | Bean-local initialization |
| Giải phóng tài nguyên thuộc sở hữu bean | `@PreDestroy`/`@Bean(destroyMethod)`/`close()` | Bean lifecycle cleanup |
| Công việc cần tất cả non-lazy singleton thông thường đã dựng xong | `SmartInitializingSingleton` | Callback sau giai đoạn pre-instantiation singleton |
| Việc phải diễn ra khi context đã refresh | `ApplicationListener<ContextRefreshedEvent>` hoặc `@EventListener` | Sự kiện context lifecycle |
| Thành phần cần start/stop theo phase, hỗ trợ shutdown | `SmartLifecycle` | Managed lifecycle, có start/stop |
| Tác vụ chỉ chạy khi người dùng/job kích hoạt | Service method gọi từ entry point thích hợp | Không ép tác vụ nghiệp vụ chạy khi startup |
| Boot application cần startup command theo thứ tự và tích hợp lifecycle Boot | `ApplicationRunner`/`CommandLineRunner` | **Spring Boot**, ngoài API core |
| Boot cần biết toàn application đã sẵn sàng để phục vụ | `ApplicationReadyEvent` hoặc cơ chế readiness | **Spring Boot**, không thay cho callback core |

Bảng này không nói rằng **mọi ứng dụng phải có bootstrap job**. Nhiều ứng dụng chỉ cần đăng ký bean rồi chờ request hoặc message; trong trường hợp đó **không chạy nghiệp vụ tại startup** là thiết kế đúng nhất.

## 5. Lifecycle của container: các mốc quan trọng

Một ApplicationContext Spring thuần thường đi qua những giai đoạn khái niệm sau:

```text
Đăng ký / đọc các bean definitions
        |
        v
Xử lý bean factory/post-processor
        |
        v
Khởi tạo các singleton non-lazy thông thường
  + gọi factory/constructor
  + dependency injection
  + @PostConstruct / initMethod
  + BeanPostProcessor
        |
        v
SmartInitializingSingleton.afterSingletonsInstantiated()
        |
        v
Hoàn tất refresh, quản lý lifecycle
        |
        v
ContextRefreshedEvent
        |
        v
Ứng dụng thực hiện các tác vụ được yêu cầu
        |
        v
Context đóng: stop/destroy callbacks thích hợp
```

Đây là **sơ đồ khái niệm**, không phải toàn bộ trình tự nội bộ của mọi ApplicationContext hay framework extension. Sự kiện refresh có thể được phát lại khi context được refresh lần nữa, và cấu trúc parent-child có thể tạo nhiều sự kiện từ các context khác nhau.

### @PostConstruct có phải "sau toàn bộ application startup"?

**Không.** `@PostConstruct` chạy trong vòng đời khởi tạo của **một bean cụ thể**. Nó không bảo đảm tất cả bean khác đã được khởi tạo; một số còn lazy, prototype hoặc phụ thuộc config/condition khác.

Ví dụ:

```java
// Đoạn minh họa, cần Jakarta Annotations trong classpath.
@PostConstruct
void init() {
    validateLocalSettings();
}
```

Một tác vụ có nhiều external calls, dài hạn, cần transaction hoặc phối hợp toàn hệ thống thường không phù hợp ở đây. Spring còn cảnh báo init callbacks dưới singleton creation lock có thể gây rủi ro deadlock nếu thao tác nặng/tra cứu bean ngoài luồng.

### SmartInitializingSingleton có phải "ứng dụng đã sẵn sàng phục vụ"?

**Không hoàn toàn.** Nó báo rằng BeanFactory đã hoàn thành **pre-instantiation của các singleton non-lazy thông thường**, nhưng một số hoạt động hoàn tất refresh/lifecycle có thể diễn ra sau đó. Nếu công việc thật sự phụ thuộc vào context refresh hoàn tất, hãy chọn `ContextRefreshedEvent`; nếu phụ thuộc web server readiness trong Spring Boot, cân nhắc cơ chế Boot tương ứng.

### ContextRefreshedEvent có thể lặp

Sự kiện `ContextRefreshedEvent` phát khi một `ApplicationContext` được khởi tạo/refresh. Nó không phải giao kèo "chạy nghiệp vụ đúng một lần duy nhất trong vòng đời công ty". Trong hệ thống parent-child contexts, một listener có thể cần kiểm tra sự kiện từ context nào; khi refresh lại, sự kiện có thể phát tiếp.

**Giả định một callback == exactly-once nghiệp vụ là sai.** Nếu tác vụ tạo dữ liệu hoặc tác động ra hệ thống ngoài, cần idempotency/điều phối phù hợp.

## 6. Ví dụ chạy được: factory thuần, init cục bộ và business bootstrap riêng

Ví dụ dùng **Java 17 + Spring Framework 6.2** thuần với `AnnotationConfigApplicationContext`. Không có Spring Boot, database hoặc mạng ngoài.

Ta xây:

- `CustomerRepository`: lưu định danh khách hàng trong bộ nhớ; có phép thêm nếu chưa tồn tại.
- `Rules`: một bean có initialization callback nhỏ để đánh dấu sẵn sàng, và destroy callback khi context đóng.
- `CustomerService`: chứa nghiệp vụ đăng ký khách hàng, không tự chạy gì khi được dựng.
- `SeedCustomers`: coordinator implement `SmartInitializingSingleton`, thực hiện một thao tác seed sau khi các singleton thông thường đã được khởi tạo.
- `AppConfig`: các phương thức `@Bean` **chỉ tạo/wire bean**, không gọi `customers.register(...)` trong method factory.

### 6.1. Cấu trúc thư mục

```text
spring-init-separation/
├── pom.xml
└── src/main/java/demo/InitSeparationDemo.java
```

### 6.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-init-separation</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. File src/main/java/demo/InitSeparationDemo.java

```java
package demo;

import java.util.HashSet;
import java.util.Set;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class InitSeparationDemo {

    interface CustomerRepository {
        boolean saveIfAbsent(String id);
        boolean contains(String id);
    }

    static final class MemoryCustomerRepository implements CustomerRepository {
        private final Set<String> ids = new HashSet<>();

        @Override
        public boolean saveIfAbsent(String id) {
            return ids.add(id);
        }

        @Override
        public boolean contains(String id) {
            return ids.contains(id);
        }
    }

    static final class Rules {
        private boolean ready;

        void initialize() {
            ready = true;
            System.out.println("rules.initialize");
        }

        boolean isReady() {
            return ready;
        }

        void close() {
            System.out.println("rules.close");
        }
    }

    static final class CustomerService {
        private final CustomerRepository repository;
        private final Rules rules;

        CustomerService(CustomerRepository repository, Rules rules) {
            this.repository = repository;
            this.rules = rules;
        }

        String register(String id) {
            if (!rules.isReady()) {
                throw new IllegalStateException("Rules not initialized");
            }
            return repository.saveIfAbsent(id)
                    ? "created:" + id
                    : "existing:" + id;
        }

        boolean exists(String id) {
            return repository.contains(id);
        }
    }

    static final class SeedCustomers implements SmartInitializingSingleton {
        private final CustomerService customers;

        SeedCustomers(CustomerService customers) {
            this.customers = customers;
        }

        @Override
        public void afterSingletonsInstantiated() {
            // Công việc khởi tạo nghiệp vụ có entry point riêng.
            System.out.println("bootstrap=" +
                    customers.register("seed-001"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        CustomerRepository customerRepository() {
            return new MemoryCustomerRepository();
        }

        @Bean(initMethod = "initialize", destroyMethod = "close")
        Rules rules() {
            return new Rules();
        }

        @Bean
        CustomerService customerService(
                CustomerRepository repository, Rules rules) {
            return new CustomerService(repository, rules);
        }

        @Bean
        SeedCustomers seedCustomers(CustomerService customers) {
            return new SeedCustomers(customers);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            CustomerService customers =
                    context.getBean(CustomerService.class);

            System.out.println("main.seedFound=" +
                    customers.exists("seed-001"));
            System.out.println("main.new=" +
                    customers.register("c-100"));
            System.out.println("main.repeat=" +
                    customers.register("seed-001"));
        }
    }
}
```

### 6.4. Cách chạy

Trong thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.InitSeparationDemo
```

Các dòng **do chương trình in ra** (không bao gồm thông điệp log mà Maven/Spring có thể ghi tùy môi trường):

```text
rules.initialize
bootstrap=created:seed-001
main.seedFound=true
main.new=created:c-100
main.repeat=existing:seed-001
rules.close
```

### 6.5. Diễn giải output và trách nhiệm của từng nơi

1. Spring nạp `AppConfig` và bốn `@Bean` definitions. Những factory methods chỉ trả instance hoặc truyền dependency. Không method nào gọi `CustomerService.register` để thực hiện business bootstrap.
2. Khi container tạo managed bean `Rules`, nó gọi `Rules.initialize()` vì `@Bean(initMethod = "initialize")`. Dòng `rules.initialize` xuất hiện ở giai đoạn bean-local initialization. Không cần toàn bộ ứng dụng đã refresh để set flag này.
3. Sau khi hoàn thành khởi tạo các singleton non-lazy thông thường, Spring gọi `SeedCustomers.afterSingletonsInstantiated()`. Coordinator gọi một use case `CustomerService.register("seed-001")` và in `bootstrap=created:seed-001`.
4. Khi constructor `AnnotationConfigApplicationContext(AppConfig.class)` trả về, chương trình `main` lấy `CustomerService`. Seed đã chạy, nên `main.seedFound=true`.
5. Gọi đăng ký ID mới `c-100` trả `created:c-100`; gọi lại ID seed trả `existing:seed-001` do repository dùng `Set.add(...)` để chống trùng ở **mức bộ nhớ trong cùng context**.
6. Khi thoát `try-with-resources`, Spring đóng context và gọi callback `Rules.close()` trên singleton `Rules`, nên xuất hiện `rules.close`.

**Lưu ý về tính idempotent:** `Set.add` trong ví dụ là demo in-memory đơn luồng. Nó không thay thế database uniqueness/transaction, phân tán lock hay idempotency keys trong môi trường có nhiều process/replica. Trong sản phẩm thực, seed phải có chính sách chống chạy trùng ở cấp dữ liệu/hệ thống, không chỉ một biến static hoặc boolean trong instance.

### 6.6. Lợi ích của việc tách như ví dụ

- `AppConfig` dễ đọc: chỉ có "tạo repository", "tạo rules", "tạo service", "tạo bootstrap coordinator".
- `Rules.initialize()` mô tả trạng thái sẵn sàng cục bộ của một bean và không gọi ra use case.
- `CustomerService.register` chứa nghiệp vụ, có thể test riêng bằng fake repository/rules.
- `SeedCustomers` có entry point rõ cho việc **kích hoạt** một tác vụ lúc startup; có thể đổi chính sách kích hoạt mà không sửa constructor/factory.
- Consumer runtime không cần biết startup callback nào đã tạo dữ liệu seed.
- Nếu muốn bỏ hoàn toàn seed khỏi một môi trường, có thể **không đăng ký** `SeedCustomers` trong cấu hình môi trường đó (ví dụ chia `@Configuration` hoặc dùng `@Profile` phù hợp), thay vì phải đặt `if` vào constructor service.

## 7. @PostConstruct, @Bean(initMethod) và InitializingBean: dùng đúng phạm vi

Spring hỗ trợ nhiều cách khai báo callback **khởi tạo bean**:

### 7.1. @PostConstruct

```java
import jakarta.annotation.PostConstruct;

final class TokenFormat {
    private String prefix;

    @PostConstruct
    void validate() {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalStateException("Missing token prefix");
        }
    }
}
```

Đây là **đoạn minh họa**, `prefix` phải được cấu hình/đưa vào object trong mã thực. Annotation `@PostConstruct` từ `jakarta.annotation` yêu cầu API Jakarta Annotations có trên classpath và post-processor của Spring phù hợp. Với Spring Framework 6.x, dùng Jakarta namespace, không dùng `javax.annotation.PostConstruct` của thế hệ cũ.

Phù hợp: kiểm tra/truyền đạt invariant hoặc chuẩn bị trạng thái nội bộ. Không phù hợp: quét dữ liệu lớn, gọi API nhiều hệ thống, thực hiện vòng lặp nghiệp vụ kéo dài trong init callback.

### 7.2. @Bean(initMethod = "...")

```java
@Bean(initMethod = "initialize")
TokenParser tokenParser() {
    return new TokenParser();
}
```

Đây là đoạn minh họa cần `TokenParser.initialize()` thực sự tồn tại. Phù hợp khi bạn cấu hình object của thư viện không muốn sửa để thêm `@PostConstruct`. Method init được Spring gọi sau bước tạo/thiết lập bean theo lifecycle, không cần phải gọi `tokenParser.initialize()` ngay trong factory method.

Với bean dùng `@Bean`, bạn có thể đặt `destroyMethod` để cleanup tài nguyên; nếu object cung cấp `close` hoặc `shutdown` phù hợp, Spring cũng có cơ chế suy luận destroy method. Nên hiểu rõ bean có thật sự **sở hữu** tài nguyên đó không trước khi để container tự đóng.

### 7.3. InitializingBean.afterPropertiesSet()

```java
final class LocalIndex implements org.springframework.beans.factory.InitializingBean {
    @Override
    public void afterPropertiesSet() {
        // Chỉ kiểm tra và chuẩn bị state của chính bean.
    }
}
```

Cách này trực tiếp phụ thuộc Spring API. Nó vẫn là một **bean-local lifecycle callback**, không tự trở thành ứng dụng-level startup hook.

### 7.4. Không gọi callback init bằng tay rồi lại khai báo với Spring

Nếu:

```java
@Bean(initMethod = "initialize")
Rules rules() {
    Rules rules = new Rules();
    rules.initialize();
    return rules;
}
```

thì `initialize()` có thể chạy **hai lần**: một lần do body factory tự gọi, một lần do lifecycle callback của BeanFactory. Nếu init không idempotent, có thể tạo lỗi hoặc mở resource hai lần.

Hãy chọn **một cơ chế sở hữu việc init**, không vừa tự gọi vừa bảo Spring gọi lặp. Nếu constructor đã bảo đảm object hợp lệ và không cần init callback, đừng thêm callback chỉ để "có đủ lifecycle annotations".

### 7.5. @PostConstruct có gọi được @Transactional method không?

Đừng giả định init callback là entry point hợp lệ cho transaction AOP. Bean có thể chưa qua các proxy/post-processors cần thiết, và self-invocation tới method cùng instance thường không đi qua proxy trong proxy-based AOP.

Khi bootstrap cần transaction, để một **managed coordinator** gọi một **service khác** qua proxy phù hợp sau khi application infrastructure đã sẵn sàng, với `@Transactional` được bật/cấu hình đúng. Cũng cần xác định chính xác thời điểm transaction có thể được mở, rollback và retry; không lấy sự tồn tại của annotation làm bằng chứng chắc chắn transaction hoạt động.

## 8. SmartInitializingSingleton: sau khởi tạo singleton nhưng trước khi coi hệ thống sẵn sàng

`SmartInitializingSingleton` là interface Spring Core có method:

```java
void afterSingletonsInstantiated();
```

Nó được gọi ở cuối giai đoạn pre-instantiation singleton của `BeanFactory`. Lợi ích so với `@PostConstruct`:

- Bean coordinator đã có các dependency được inject.
- Các singleton thông thường, không lazy, đã qua khởi tạo, giảm nguy cơ đụng vào bean khác khi nó còn ở giữa vòng đời khởi tạo.
- Callback được kích hoạt qua cơ chế BeanFactory, không cần viết lệnh gọi nghiệp vụ trong `@Bean` factory method.
- Phù hợp với setup hậu khởi tạo cần nhiều singleton nhưng chưa đòi event context refresh hoàn tất.

Giới hạn quan trọng:

- Không có bảo đảm mọi **lazy singleton**, prototype hoặc external resource đã sẵn sàng.
- Callback chạy đồng bộ trong đường khởi tạo/refresh thông thường; tác vụ nặng có thể kéo dài startup.
- Không mặc định có retry, timeout, transaction hay cơ chế phân tán.
- Nhiều callbacks cùng tồn tại không nên dựa vào thứ tự tình cờ nếu có dependency thứ tự nghiệp vụ giữa chúng; hãy điều phối tường minh.
- Callback không phải sự kiện exactly-once across replicas.
- Nếu bean coordinator cũng bị đánh `@Lazy` và không được khởi tạo trong giai đoạn pre-instantiation, không nên mặc định callback chắc chắn đã chạy.

### Khi cần thứ tự giữa nhiều tác vụ

Giả sử ứng dụng phải **tạo schema hợp lệ**, sau đó **nạp danh mục tham chiếu**, rồi mới **bật một adapter phục vụ traffic**. Đừng tạo ba bean `SmartInitializingSingleton` rồi mặc định Spring sẽ gọi chúng theo một thứ tự kinh doanh cụ thể dựa vào thứ tự viết `@Bean` methods.

Nên có một **coordinator** sở hữu chuỗi bước:

```java
// Đoạn minh họa; từng action là interface/bean ứng dụng.
final class StartupCoordinator implements SmartInitializingSingleton {
    private final ValidateSchema validateSchema;
    private final SeedReferenceData seedReferenceData;

    StartupCoordinator(ValidateSchema validateSchema,
                       SeedReferenceData seedReferenceData) {
        this.validateSchema = validateSchema;
        this.seedReferenceData = seedReferenceData;
    }

    @Override
    public void afterSingletonsInstantiated() {
        validateSchema.run();
        seedReferenceData.run();
    }
}
```

Đây không phải file độc lập. `ValidateSchema` và `SeedReferenceData` phải được định nghĩa trong ứng dụng; coordinator thể hiện rõ trình tự và tạo một nơi để quản lý idempotency/logging/failure policy.

## 9. ContextRefreshedEvent: khi cần ngữ cảnh đã refresh

Spring phát `ContextRefreshedEvent` khi `ApplicationContext` đã được khởi tạo hoặc refresh. Có thể lắng nghe qua:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@Component
final class StartupListener {
    private final ReferenceDataService referenceData;

    StartupListener(ReferenceDataService referenceData) {
        this.referenceData = referenceData;
    }

    @EventListener(ContextRefreshedEvent.class)
    void onRefresh() {
        referenceData.ensureSeeded();
    }
}
```

Đây là **đoạn minh họa**, cần import `@Component`, định nghĩa `ReferenceDataService` và đảm bảo scanner tìm thấy listener. Method được Spring gọi khi event phù hợp được dispatch; không nên coi event listener là phương tiện duy nhất để giải quyết mọi startup task.

Điểm cần cẩn trọng:

- Context có thể **refresh nhiều lần** nếu kiểu context/luồng vận hành hỗ trợ, nên listener có thể chạy lại.
- Nếu có **parent-child context**, một listener có thể thấy sự kiện ở các context khác nhau tùy cấu trúc sự kiện; khi cần, lọc `event.getApplicationContext()`.
- Event multicaster thường dispatch đồng bộ theo mặc định, nhưng có thể được cấu hình bất đồng bộ; không kết luận event handling là barrier readiness nếu kiến trúc đã đổi cách dispatch.
- Nếu callback thất bại, tác động lên startup còn phụ thuộc cơ chế dispatch, exception handling và context lifecycle; cần test đường lỗi thực tế.
- `ContextRefreshedEvent` nói về **Spring context**, không mặc nhiên đảm bảo external database, broker và dịch vụ từ xa đều sẵn sàng.

### @EventListener và ApplicationListener

Hai dạng tương đương về ý định lắng nghe event, không bắt buộc viết cả hai:

```java
// Minh họa dạng interface:
final class Listener implements
        org.springframework.context.ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        // Xử lý một lần phát sự kiện context refresh.
    }
}
```

Dạng class này cũng phải được đăng ký làm bean/listener trong context. Dùng `@EventListener` khi muốn method-based listener; dùng interface khi phù hợp với infrastructure contract. Dù chọn dạng nào, chính sách idempotency vẫn nằm ở nghiệp vụ.

## 10. SmartLifecycle: khi bootstrap là một thành phần có start/stop

Một thành phần chạy nền như polling consumer, listener adapter hoặc scheduler có vòng đời **bắt đầu — hoạt động — dừng**. Việc xây object và khởi tạo bean chỉ là một phần; chạy nền nên được điều khiển theo lifecycle.

`SmartLifecycle` của Spring hỗ trợ:

- `start()`: bắt đầu hoạt động.
- `stop()` hoặc `stop(Runnable callback)`: dừng theo cơ chế đồng bộ/bất đồng bộ phù hợp.
- `isRunning()`: báo trạng thái.
- `getPhase()`: định nghĩa phase ordering giữa những lifecycle components.
- `isAutoStartup()`: xác định có tự start khi context refresh hay không.

Sơ đồ ý tưởng:

```text
@Bean factory: new MessageConsumer(...)
            |
            v
Bean đã được Spring quản lý
            |
            v
Lifecycle processor gọi start()
            |
            v
Consumer lắng nghe message theo phase
            |
            v
Context stop/close -> stop(callback)
            |
            v
Destroy callbacks và tài nguyên được cleanup
```

Không nên mở thread dài hạn hoặc chạy vòng lặp vô hạn trong constructor, `@Bean` factory, hay `@PostConstruct`. Điều đó có thể chặn context initialization, làm trạng thái runtime khó dừng đúng thứ tự hoặc gây rò rỉ tài nguyên.

Một implementation `SmartLifecycle` phải xử lý concurrency, shutdown timeout và callback hoàn tất đúng hợp đồng; chỉ nên dùng khi bạn thật sự có **một thành phần có vòng đời hoạt động**, không phải cho thao tác seed dữ liệu đơn giản chạy một lần.

## 11. Phân biệt Spring Framework Core và Spring Boot

Trong ứng dụng **Spring Framework thuần**, bạn thường chọn:

- `SmartInitializingSingleton` khi cần hành động sau pre-instantiation singleton.
- `ContextRefreshedEvent` khi cần một hook sau refresh.
- `SmartLifecycle` khi có component khởi động/dừng theo phase.
- Entry point ứng dụng gọi service trực tiếp khi công việc không thuộc startup.

Trong **Spring Boot**, ngoài các lựa chọn của Spring Framework còn có:

- `ApplicationRunner` và `CommandLineRunner`: hooks thực hiện khi Boot application đã bắt đầu theo lifecycle runner của Boot; có thể dùng `@Order`/`Ordered` theo chính sách Boot.
- `ApplicationReadyEvent`: tín hiệu Boot đã hoàn thành quá trình startup và chuẩn bị phục vụ request, phát sau các runners theo lifecycle thông thường.
- Readiness/liveness và các cấu hình vận hành khác của Boot.

Cần phân biệt: **`ApplicationReadyEvent` không thuộc Spring Core Container**, và dù nó biểu diễn readiness ở cấp ứng dụng Boot, cũng không hứa các hệ thống ngoài hay một cluster phân tán đã sẵn sàng. Không copy `CommandLineRunner` vào một ví dụ chỉ khai báo dependency `spring-context` rồi mong code biên dịch.

### Khi nào không nên bootstrap tự động?

Nếu một tác vụ có thể chạy theo lịch, được kích hoạt bởi admin, phải chờ approval hoặc cần quota/lock phân tán, đừng buộc nó chạy mỗi lần một instance ứng dụng khởi động. Hãy để entry point tương ứng gọi một service, có trạng thái/tín hiệu riêng. Tách factory khỏi nghiệp vụ giúp bạn đổi **trigger** mà không phải viết lại object wiring.

## 12. Tính idempotent và giao dịch của bootstrap nghiệp vụ

Một tác vụ business bootstrap có thể xảy ra nhiều lần:

- Khởi động lại ứng dụng sau lỗi.
- Nhiều replica cùng khởi động.
- Tạo nhiều Spring contexts trong integration tests.
- Context được refresh hoặc listener nhận nhiều sự kiện.
- Retry do cơ chế quản trị/triển khai.
- Chạy lệnh seed thủ công song song với bootstrapping.

Vì thế **đúng một lần trong một JVM** thường chưa đủ. Với dữ liệu quan trọng, cần invariant có thể kiểm tra trong data store.

### Tạo nếu chưa có, không phải tạo lại vô điều kiện

Thay vì:

```java
// Phản ví dụ:
void seedRoles() {
    roleRepository.insert("ADMIN"); // Chạy lại có thể lỗi/trùng.
}
```

hãy thiết kế thao tác idempotent:

```java
// Đoạn minh họa cấp ứng dụng:
void ensureDefaultRole() {
    roleRepository.insertIfAbsent("ADMIN");
}
```

Method `insertIfAbsent` là API ứng dụng giả định. Ở database thật, cần unique constraint/UPSERT hoặc transaction phù hợp để tránh race condition giữa nhiều instance. Một thao tác kiểu "query trước rồi insert" tách biệt không tự an toàn trong cạnh tranh nếu thiếu ràng buộc dữ liệu.

### Transaction phải nằm ở ranh giới thích hợp

Khi cần transaction, coordinator có thể gọi một service Spring-managed khác:

```java
// Đoạn minh họa: hàm transaction thuộc bean được proxy hợp lệ.
final class SeedCoordinator {
    private final RoleBootstrapService roleService;

    SeedCoordinator(RoleBootstrapService roleService) {
        this.roleService = roleService;
    }

    void execute() {
        roleService.ensureDefaultRoles();
    }
}
```

`RoleBootstrapService` có thể định nghĩa transaction boundary với `@Transactional` khi hạ tầng transaction đã bật. Không giả định gọi method `@Transactional` từ constructor hoặc `@PostConstruct` của **chính bean đó** sẽ đi qua transaction proxy. Tương tự, không nên tự gọi một method transaction khác trong cùng class rồi nghĩ proxy-based advice luôn được áp dụng.

### Chính sách khi bootstrap thất bại

Phải xác định rõ:

| Loại tác vụ | Khi thất bại nên làm gì? |
| --- | --- |
| Bắt buộc để hoạt động an toàn | Startup thất bại hoặc không công bố readiness, cần báo rõ nguyên nhân |
| Dữ liệu nền có thể nạp lại | Retry có kiểm soát, không tạo trùng, có metrics |
| Bổ trợ như warm-up cache | Cho phép degraded mode nếu nghiệp vụ chịu được; ghi log và giám sát |
| Lệnh nghiệp vụ kích hoạt thủ công | Trả kết quả/lỗi cho caller, không giấu trong lifecycle hook |
| External resource không có sẵn | Có timeout, circuit breaker/retry hoặc ràng buộc readiness theo yêu cầu |

Đừng bắt `Exception` rồi âm thầm bỏ qua một bước seed bắt buộc để container vẫn báo healthy. Ngược lại, một cache warm-up không bắt buộc có thể không đáng làm cả ứng dụng fail startup — nhưng đó phải là **quyết định nghiệp vụ**, không phải side effect ngẫu nhiên của `@Bean`.

## 13. Quan sát, testability và side-effect budget

Việc tách trách nhiệm giúp kiểm thử theo ba tầng.

### Test construction riêng

Kiểm tra `CustomerService` bằng repository fake:

```java
// Đoạn minh họa trong test unit; cần fake repository và Rules hợp lệ.
CustomerService service = new CustomerService(fakeRepository, preparedRules);
String result = service.register("customer-1");
```

Không cần dựng Spring context chỉ để kiểm tra business method; đây là lợi thế của constructor injection rõ ràng.

### Test bean initialization riêng

Một test Spring nhỏ xác minh `Rules.initialize()` được gọi khi bean được tạo qua BeanFactory và trạng thái `isReady()` là `true`. Không tự gọi `new AppConfig().rules()` rồi cho rằng đã kiểm thử Spring-managed init callbacks.

### Test bootstrap riêng

Tạo `SeedCustomers` với fake `CustomerService` hoặc dùng ApplicationContext tích hợp rồi kiểm tra dữ liệu seed đã được tạo trước khi context constructor trả về. Với ví dụ đầy đủ, có thể thêm assert sau bên trong `main`:

```java
CustomerService customers =
        context.getBean(CustomerService.class);

if (!customers.exists("seed-001")) {
    throw new AssertionError("Startup seed was not created");
}
```

Đoạn bổ sung này không in thêm stdout khi đúng. Nó kiểm tra hiệu quả thật của coordinator, không chỉ kiểm tra callback được khai báo trong source.

### Integration test kiểm tra context không kích hoạt nghiệp vụ ngoài ý muốn

Nếu một test chỉ cần repository/service bean để kiểm tra wiring, tốt nhất có một cấu hình test **không đăng ký bootstrap coordinator**, hoặc thay thế external gateway bằng fake. Khi factory thuần construction, việc mở ApplicationContext không tự chạy những use case không liên quan trừ khi bạn cố ý đăng ký startup components.

### Observability cho startup job

Trong hệ thống thật, ghi nhận:

- Tên bước và thời điểm bắt đầu/kết thúc.
- Thành công/thất bại và nguyên nhân gốc.
- Số lượng bản ghi đã tạo/cập nhật/bỏ qua.
- Trạng thái idempotency/retry/lock.
- Tổng thời gian và timeout.
- Version/schema/data migration tương ứng.
- Readiness hoặc degraded mode nếu có.

Đừng log secrets/token hoặc nội dung dữ liệu nhạy cảm chỉ để thấy bootstrap chạy. Metric/log cũng không thay thế tính đúng của unique constraints/transaction.

## 14. Những anti-pattern quan trọng

### Anti-pattern A: gửi email ngay trong factory

```java
@Bean
EmailService emailService(EmailGateway gateway) {
    EmailService service = new EmailService(gateway);
    service.sendWelcomeEmails(); // Side effect lặp khi context dựng.
    return service;
}
```

**Sửa:** factory chỉ tạo `EmailService`; một job/command được kích hoạt đúng thời điểm gọi `sendWelcomeEmails()` với idempotency và quan sát riêng. Nếu gửi email phải được người dùng kích hoạt, hoàn toàn không chạy ở startup.

### Anti-pattern B: nạp dữ liệu lớn trong @PostConstruct

```java
@PostConstruct
void init() {
    externalApi.downloadEverythingAndWriteDatabase();
}
```

**Sửa:** bean-local init chỉ validate/precompute nhỏ. Đưa tác vụ nặng vào coordinator sau giai đoạn singleton creation hoặc job bất đồng bộ có policy riêng; nếu cần readiness gating, thiết kế rõ ràng.

### Anti-pattern C: tạo thread trong constructor

```java
public PollingConsumer() {
    new Thread(this::pollForever).start();
}
```

**Sửa:** constructor chỉ lưu config/dependencies; sử dụng `SmartLifecycle` hoặc một scheduler/managed executor phù hợp để start/stop; xử lý shutdown và exception đúng hợp đồng.

### Anti-pattern D: dùng @DependsOn để điều phối tất cả công việc nghiệp vụ

```java
@Bean
@DependsOn("seedData")
ReportService reportService() {
    return new ReportService();
}
```

`@DependsOn` thể hiện **ràng buộc trình tự khởi tạo/hủy bean**, không biến `seedData` thành hệ thống orchestration nghiệp vụ có retry, transaction và idempotency. Nếu cần A→B→C business steps, hãy mô tả các bước trong coordinator/test rõ ràng.

### Anti-pattern E: chạy tác vụ trong @Configuration constructor

```java
@Configuration
class StartupConfig {
    StartupConfig(ReportingService reporting) {
        reporting.generateMonthlyReport();
    }
}
```

**Sửa:** class config làm wiring, không chạy workflow; tránh ép container làm việc ngoài nhiệm vụ khi chính class config còn đang khởi tạo. Đặc biệt nguy hiểm nếu constructor cần những bean mà factory definitions của class cấu hình này đang cung cấp, dễ tạo vòng phụ thuộc.

### Anti-pattern F: hiểu @Bean(initMethod) như "application ready"

```java
@Bean(initMethod = "startAllJobs")
JobCoordinator jobCoordinator() {
    return new JobCoordinator();
}
```

Init callback là **bean lifecycle**, không tự bảo đảm mọi application-level dependency/external service đã sẵn sàng. Nếu `startAllJobs` cần nhiều bean, DB, transaction hoặc dữ liệu nghiệp vụ, cần xem lại trigger và lifecycle orchestration.

## 15. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Mỗi lần test context mở đều gửi email/tạo dữ liệu | Logic nghiệp vụ nằm trong constructor, `@Bean` hoặc init callback | Tách use case khỏi wiring; đăng ký startup coordinator có chủ đích |
| Context không khởi động khi DB chậm | Factory/init callback gọi I/O bên ngoài quá sớm | Dời tác vụ sang lifecycle phù hợp; timeout/retry/readiness |
| Bean khác chưa sẵn mà @PostConstruct đã gọi | Init callback chạy trong khởi tạo bean, không đợi toàn bộ singleton | Chuẩn bị state nội bộ ở init; chuyển orchestration sang callback muộn hơn |
| Deadlock hoặc refresh bị treo | Callback init giữ singleton creation lock và tra cứu/call ngoài luồng | Giảm init work; dùng `SmartInitializingSingleton`/refresh event phù hợp |
| Method @Transactional không có transaction | Self-invocation hoặc gọi trong init trước proxy hoàn chỉnh | Gọi qua service/proxy phù hợp ở ranh giới muộn hơn |
| Dữ liệu seed trùng sau scale-out | Chỉ dùng cờ boolean trong một JVM/context | Dùng unique constraint/UPSERT và idempotency đa instance |
| Resource bị mở hai lần | Vừa gọi init trong factory vừa khai báo `initMethod`; hoặc direct @Bean call trong lite config | Chọn một callback, inject managed bean qua tham số |
| Một task chạy nhiều lần sau refresh | Listener nhận nhiều `ContextRefreshedEvent` | Lọc context đúng và thiết kế idempotency |
| Startup callback không chạy ở bean lazy | Bean callback không thuộc non-lazy singleton pre-instantiation | Đăng ký coordinator non-lazy nếu thật sự cần startup hook |
| Tưởng SmartInitializingSingleton đồng nghĩa mọi external service sẵn | Callback chỉ báo giai đoạn trong BeanFactory | Dùng explicit health/readiness/dependency checks |
| Test unit bắt buộc dựng database | Constructor/factory tự thực thi nghiệp vụ | Constructor injection, fake dependencies, tách bootstrap |
| Shutdown rò rỉ thread/pool | Mở tài nguyên hoặc thread mà không quản lý lifecycle | `destroyMethod`, `SmartLifecycle`, managed executor |
| Không có log nguyên nhân bootstrap fail | Lỗi bị catch rồi bỏ qua ở init | Exception/metrics/logging theo chính sách vận hành |

### Quy trình debug từng bước

1. Xác định code thực hiện side effect nằm ở **constructor**, **@Bean**, **init callback** hay **startup coordinator**.
2. Kiểm tra class `@Configuration` có đang dùng lite mode; nếu gọi `@Bean` method trực tiếp, object có thể nằm ngoài BeanFactory.
3. Kiểm tra dependency bắt buộc có được inject qua constructor/factory parameters hay không.
4. Xác định callback chạy trước/sau pre-instantiation singleton, context refresh hoặc Boot readiness.
5. Xác định mỗi lần khởi động/context refresh/replica có thể kích hoạt tác vụ bao nhiêu lần.
6. Xem tác vụ có idempotent và transaction boundary đúng không.
7. Đọc exception gốc và kiểm tra resource/connection/shutdown policy.
8. Viết integration test tái hiện một lần startup và một lần startup lặp.

## 16. Bài tập thực hành và đáp án

### Bài 1 — Phân loại công việc

Trong một `@Bean DataClient dataClient()`, có các thao tác: (a) xây builder với URL; (b) kiểm tra URL không rỗng; (c) ghi 1.000 hóa đơn vào DB; (d) truyền dependency sang service khác. Thao tác nào thuộc wiring/local setup?

**Đáp án:** (a), (b) và (d) có thể thuộc construction/configuration khi không thực hiện I/O nghiệp vụ. (c) là workflow có side effect và cần entry point/policy riêng; không nên chạy trong factory.

### Bài 2 — @PostConstruct có phải sau tất cả bean?

Một `@PostConstruct` của `CustomerService` gọi mọi handler trong hệ thống. Có bảo đảm tất cả singleton/lazy beans đã khởi tạo không?

**Đáp án:** Không. Init callback thuộc vòng đời bean hiện tại, không phải barrier sau toàn bộ container; nó còn có thể chạy dưới singleton creation lock. Nên điều phối hậu khởi tạo đúng cơ chế và tránh khối lượng công việc nặng ở đây.

### Bài 3 — SmartInitializingSingleton có thay @Bean không?

Nếu `SeedCustomers` implements `SmartInitializingSingleton`, có cần đăng ký nó thành bean không?

**Đáp án:** Có. Spring chỉ có thể gọi callback cho bean mà BeanFactory quản lý. Trong ví dụ đầy đủ, method `@Bean SeedCustomers seedCustomers(CustomerService customers)` đăng ký coordinator.

### Bài 4 — Dự đoán stdout

Trong chương trình `InitSeparationDemo` ở mục 6, tại sao `rules.initialize` chạy trước `bootstrap=created:seed-001`?

**Đáp án:** `Rules` là dependency của `CustomerService`; Spring hoàn thành init callback của managed `Rules` trong giai đoạn tạo singleton. Sau khi các singleton non-lazy đã pre-instantiate, nó gọi `SeedCustomers.afterSingletonsInstantiated()`, khi ấy use case mới chạy.

### Bài 5 — Chạy nhiều instance

Hai replica cùng seed role `ADMIN` bằng lệnh "nếu không tồn tại thì insert" mà không có unique constraint. Có an toàn không?

**Đáp án:** Không. Hai replica có thể cùng đọc "chưa tồn tại" rồi cùng insert. Cần unique constraint/UPSERT/transaction hoặc phối hợp phân tán thích hợp, tùy yêu cầu.

### Bài 6 — @DependsOn có thay coordinator không?

Bạn cần nạp danh mục A rồi tạo chỉ mục B rồi bật listener C. Chỉ đặt `@DependsOn` trên ba beans đã đủ mô tả retry/idempotency/readiness chưa?

**Đáp án:** Chưa. `@DependsOn` nói về dependency của lifecycle bean, không định nghĩa policy orchestration nghiệp vụ. Dùng coordinator/startup lifecycle phù hợp, test thứ tự và các tình huống lỗi.

### Bài 7 — Khi nào dùng SmartLifecycle?

Một message consumer cần tự start ở giai đoạn phù hợp và tự stop trước khi giải phóng pool. Đặt vòng lặp `while(true)` trong `@PostConstruct` hay dùng `SmartLifecycle`?

**Đáp án:** `SmartLifecycle` hoặc một abstraction managed listener/scheduler phù hợp giúp mô tả start/stop và phase; không khởi chạy vòng lặp vô hạn trong init callback.

### Bài 8 — ContextRefreshedEvent có thể chạy hai lần?

Một listener seed dữ liệu dựa trên `ContextRefreshedEvent`; app có parent-child contexts. Có nên giả định listener chỉ thấy đúng một event rồi không cần idempotency?

**Đáp án:** Không. Event có thể phát theo từng context và khi refresh; listener cần lọc context nếu yêu cầu, đồng thời use case seed phải an toàn khi chạy lặp.

### Bài 9 — Transaction nằm ở đâu?

Một bean tự gọi method `@Transactional` từ constructor. Vì sao không nên dùng cách đó?

**Đáp án:** Constructor chạy trước khi object/proxy hoàn chỉnh; self-invocation trong proxy-based Spring AOP thường bỏ qua proxy. Hãy dùng managed service/proxy làm transaction boundary, gọi từ coordinator ở giai đoạn thích hợp.

### Bài 10 — Thiết kế lại @Bean

Refactor đoạn sau:

```java
@Bean
InventoryService inventoryService(InventoryRepository repository) {
    InventoryService service = new InventoryService(repository);
    service.importCatalog();
    return service;
}
```

**Đáp án định hướng:**

```java
@Bean
InventoryService inventoryService(InventoryRepository repository) {
    return new InventoryService(repository);
}

@Bean
CatalogBootstrap catalogBootstrap(InventoryService inventoryService) {
    return new CatalogBootstrap(inventoryService);
}
```

`CatalogBootstrap` là class coordinator ứng dụng: nó có thể implement `SmartInitializingSingleton` hoặc nhận trigger từ entry point phù hợp, tùy thời điểm nghiệp vụ. Đoạn này là ví dụ cấu trúc, cần định nghĩa `InventoryRepository`, `InventoryService` và `CatalogBootstrap` tương ứng. Điểm quan trọng là factory **không gọi `importCatalog()`**.

## 17. Checklist áp dụng vào dự án

- [ ] Mỗi `@Bean` factory method chủ yếu **tạo/wire instance**, không thực thi workflow nghiệp vụ.
- [ ] Constructor của service không tự gửi email, migrate dữ liệu hay gọi external API không cần thiết.
- [ ] Bean-local validation/preparation được đặt trong constructor hoặc lifecycle callback nhỏ, có hợp đồng rõ.
- [ ] Tác vụ nhiều bean hoặc I/O nặng không bị ép vào `@PostConstruct`.
- [ ] Với startup hook, chọn mốc `SmartInitializingSingleton`, `ContextRefreshedEvent`, `SmartLifecycle` hay Boot runner đúng nhu cầu.
- [ ] Nếu không cần tự động startup task, **không đăng ký** một callback chạy nghiệp vụ không cần thiết.
- [ ] Thứ tự giữa các bước nghiệp vụ được điều phối **tường minh**, không dựa vào thứ tự bean definitions tình cờ.
- [ ] Startup task có chính sách idempotency, transaction, retry/timeout và failure/readiness đúng với business requirements.
- [ ] Với nhiều replica hoặc refresh, đã xử lý trường hợp tác vụ chạy lặp.
- [ ] Các dependency vào `@Bean` dùng method parameters thay vì direct bean-method calls khi dùng lite mode.
- [ ] Test đơn vị có thể gọi business service mà không cần mở Spring context, nếu không phụ thuộc infrastructure.
- [ ] Integration test kiểm tra lifecycle/seed/identity và phát hiện side effects không mong muốn.
- [ ] Tài nguyên hoặc background task có cleanup/stop callbacks tương ứng.
- [ ] Logging/metrics đủ quan sát mà không lộ dữ liệu nhạy cảm.

## Ghi nhớ cuối bài

**Tạo bean, khởi tạo bean và khởi tạo nghiệp vụ là ba trách nhiệm khác nhau.** Spring có nhiều lifecycle extension points vì những giai đoạn này không tương đương:

- `@Bean` và constructor: **tạo object + nối dependency**.
- `@PostConstruct` hoặc `@Bean(initMethod)`: **xác thực/chuẩn bị trạng thái cục bộ của bean**.
- `SmartInitializingSingleton` hoặc `ContextRefreshedEvent`: **giai đoạn hậu khởi tạo để điều phối nếu ứng dụng thực sự cần**.
- `SmartLifecycle`: **start/stop của thành phần chạy theo lifecycle**.
- Use case/service method: **nghiệp vụ thực sự**, được gọi từ trigger có chủ đích.

Không cố "làm hết mọi thứ" trong `@Configuration`. Một Java configuration tốt giúp người đọc biết **bean nào tồn tại và nối với nhau ra sao**, còn một bootstrap coordinator tốt giúp người đọc biết **tác vụ nghiệp vụ nào được chạy, lúc nào, với chính sách lỗi và lặp lại thế nào**.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): lifecycle callbacks, lưu ý singleton creation lock, `SmartInitializingSingleton`/context refresh event và `SmartLifecycle`.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory method parameters và `initMethod`/`destroyMethod`.
- [Spring Framework 6.2 — SmartInitializingSingleton Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): ý nghĩa callback sau pre-instantiation singleton.
- [Spring Framework 6.2 — ContextRefreshedEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html): sự kiện ApplicationContext được initialized/refreshed.
- [Spring Framework 6.2 — SmartLifecycle Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/SmartLifecycle.html): start/stop, auto-startup và lifecycle phases.
- [Spring Framework 6.2 — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html): ranh giới factory configuration.
