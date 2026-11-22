# Đối tượng tạo bằng `new` và lời gọi ngoài Spring container

## 1. Vấn đề: có `@Transactional` nhưng vẫn không rollback

Trong Spring Framework, một lớp Java có thể chứa phương thức `@Transactional`, ứng dụng có thể đã cấu hình transaction manager, nhưng khi gọi phương thức ấy thì **không có giao dịch nào được Spring tạo ra**. Một nguyên nhân rất hay gặp là bạn tạo đối tượng bằng `new` rồi gọi trực tiếp, thay vì sử dụng **Spring bean reference đã được transaction proxy xử lý**.

Ví dụ:

```java
@Service
public class PaymentService {
    @Transactional
    public void pay() {
        // Trừ tiền và lưu đơn hàng.
    }
}

// Một nơi khác:
PaymentService payment = new PaymentService();
payment.pay();
```

Đoạn trên chỉ **minh họa nguyên tắc**, không phải chương trình biên dịch độc lập. Nếu `PaymentService` có dependency trong constructor thì lời gọi `new` cần cung cấp dependency đó. Quan trọng hơn, `payment` ở đây là đối tượng thường: Spring không khởi tạo, không inject, không áp dụng lifecycle và **không tạo transaction AOP proxy** cho reference vừa `new`. Annotation trên class không tự chạy transaction interceptor.

Nhưng có một trường hợp phải phân biệt: **caller nằm ngoài Spring container không nhất thiết làm mất transaction**. Một class thường tạo bằng `new` vẫn có thể gọi thành công vào bean `@Transactional`, miễn là nó giữ **đúng reference proxy do Spring cung cấp**:

```java
PaymentService bean = context.getBean(PaymentService.class);
ExternalJob job = new ExternalJob(bean); // Caller được tạo bằng new.
job.execute();                           // Caller gọi qua bean proxy.
```

Đoạn này là **minh họa**, cần `context` và class `ExternalJob` phù hợp. Vì `job` có reference tới `bean` đã được Spring quản lý/proxy, method call vẫn có thể được intercept. Vị trí tạo caller và vị trí tạo **target service** là hai câu hỏi khác nhau.

**Mục tiêu bài học:** nhận diện đúng object/reference nào được Spring xử lý, kiểm tra lời gọi có đi qua proxy không, và thực hành bằng một demo cho thấy dữ liệu khác nhau giữa gọi `new` trực tiếp và gọi bean proxy.

## 2. Spring quản lý bean và proxy như thế nào?

`@Transactional` là **metadata** mô tả chính sách giao dịch. Trong chế độ mặc định `AdviceMode.PROXY`, một transaction được kích hoạt khi:

1. Lớp hoặc phương thức có metadata `@Transactional` phù hợp.
2. Bean được đăng ký/khởi tạo trong Spring `ApplicationContext` có hạ tầng annotation-driven transaction management (ví dụ `@EnableTransactionManagement` hoặc auto-configuration thích hợp).
3. Có `TransactionManager` phù hợp với tài nguyên cần quản lý.
4. Caller thực sự gọi phương thức qua **proxy reference** mà Spring đã tạo, trên phương thức có khả năng được advice.
5. Các thao tác dữ liệu dùng đúng tài nguyên tham gia transaction do manager quản lý.

Spring thường dùng **Spring AOP proxy**: JDK dynamic proxy nếu cần proxy interface, hoặc class-based proxy cho class không có interface phù hợp. Transaction interceptor được gọi **trước** method body để mở/join transaction và **sau** method body để commit/rollback.

```text
                      SPRING APPLICATION CONTEXT
                     +---------------------------+
                     |  Bean definition          |
                     |  @EnableTransactionManagement
                     |  TransactionManager       |
                     |       |                   |
                     |       v                   |
Caller ------------->|  Transaction proxy       |
                     |       |                   |
                     |       v                   |
                     |  PaymentService target    |
                     +---------------------------+
                              |
                              v
                       JDBC/JPA operations

Caller -> new PaymentService() -> target method
         (không đi qua transaction proxy của Spring)
```

Nếu bạn gọi trực tiếp target `new PaymentService(...)`, interceptor không có cơ hội chạy. Điều này **không đồng nghĩa** với chuyện mọi câu JDBC bên trong sẽ thất bại: các câu SQL vẫn có thể chạy bình thường và tự commit riêng lẻ. Lỗi thường chỉ lộ ra khi cần rollback một nhóm thao tác.

### 2.1. Phân biệt ba khái niệm

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| Object do ai tạo? | `new` tùy ý trong application code hay được Spring nhận vào bean lifecycle? |
| Reference hiện tại là gì? | Target thường hay **proxy** do BeanFactory trả về? |
| Caller ở đâu? | Trong một Spring bean, trong `main()`, listener, job, servlet, thư viện ngoài? |

**Reference** là điểm mấu chốt ở thời điểm gọi. Một caller ở bất cứ lớp Java nào cũng có thể sử dụng proxy do `ApplicationContext.getBean(...)` trả về hoặc proxy được inject qua constructor. Ngược lại, một Spring-managed bean có thể tự tạo target bằng `new` và gọi trực tiếp, khiến method của target mới vẫn không được Spring AOP xử lý.

## 3. Các trường hợp thực tế cần phân biệt

### 3.1. Tạo annotated service bằng `new` ngay trong method

```java
public class CheckoutCoordinator {
    public void checkout() {
        PaymentService service = new PaymentService();
        service.pay();
    }
}
```

Đây là **minh họa rút gọn**, giả định `PaymentService` có constructor không tham số. Với `service` vừa được `new`, annotation không biến method call thành lời gọi qua proxy. Nếu bên trong `pay()` có hai lệnh ghi trên JDBC connection chạy auto-commit, chúng có thể commit độc lập; lỗi ở bước thứ hai không tự đảo ngược bước thứ nhất.

**Cách xử lý:** đăng ký `PaymentService` làm Spring bean và inject/reference **bean đã xử lý**. Dùng constructor injection khi `CheckoutCoordinator` cũng thuộc Spring:

```java
@Service
public class CheckoutCoordinator {
    private final PaymentService paymentService;

    public CheckoutCoordinator(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout() {
        paymentService.pay(); // Reference do Spring inject.
    }
}
```

Đây là **lớp minh họa**; `PaymentService` là bean đã được context đăng ký, hạ tầng transaction phải được bật, và lời gọi `pay()` phải thỏa điều kiện interception. Ưu tiên constructor injection để dependency xuất hiện rõ ràng.

### 3.2. Một Spring bean tự `new` thêm object khác

```java
@Service
public class CheckoutCoordinator {
    public void checkout() {
        PaymentService local = new PaymentService();
        local.pay();
    }
}
```

Dù `CheckoutCoordinator` được container quản lý, biến `local` vẫn là object thường. **Bean cha không cấp quyền quản lý tự động** cho mọi object mà code trong bean tạo bằng `new`. Nếu cần nhiều instance được quản lý, sử dụng scope phù hợp, factory bean hoặc `ObjectProvider<PaymentService>`. `provider.getObject()` lấy object thông qua Spring và cho phép các BeanPostProcessor/proxy liên quan tham gia.

### 3.3. Phương thức `@Bean` trả về object được tạo bằng `new`

Không được suy diễn rằng **mọi sự xuất hiện của từ khóa `new` đều sai**:

```java
@Configuration
@EnableTransactionManagement
public class AppConfig {

    @Bean
    PaymentService paymentService() {
        return new PaymentService(); // Spring nhận object này làm bean.
    }
}
```

Đây là **cấu hình minh họa**, cần constructor `PaymentService()` và một transaction manager được cấu hình phù hợp. Trong cách này, **Spring gọi factory method `@Bean` và quản lý kết quả**. Khi bean được tạo, BeanPostProcessor vẫn có thể áp dụng transaction proxy trước khi bean được cung cấp cho các caller qua `getBean`/injection. Đối tượng được `new` **bên trong `@Bean`** khác object được `new` ở một method tùy ý rồi giữ làm local reference.

Tuy nhiên, nếu bạn **tự gọi** `new AppConfig().paymentService()` ở ngoài Spring, kết quả ấy không tự được đăng ký vào container. Không gọi trực tiếp factory method cấu hình như cách lấy bean. Hãy lấy dependency qua Spring.

### 3.4. Caller tạo bên ngoài Spring nhưng gọi đúng proxy

Một chương trình console, batch runner, Java listener, legacy servlet hoặc object của thư viện thứ ba có thể không được Spring tạo. Nó vẫn gọi vào transactional service được nếu nhận **reference proxy**:

```java
public final class ExternalRunner {
    private final PaymentService service;

    public ExternalRunner(PaymentService service) {
        this.service = service;
    }

    public void run() {
        service.pay();
    }
}

// Ví dụ sau khi ApplicationContext đã được khởi tạo:
PaymentService proxy = context.getBean(PaymentService.class);
new ExternalRunner(proxy).run();
```

Các câu sau class là **đoạn sử dụng minh họa**, không phải file Java độc lập; cần `context` thực tế và bean phù hợp. Dù `ExternalRunner` được tạo bằng `new`, method `service.pay()` đi qua reference proxy, nên transaction advice có thể chạy. Spring AOP **không yêu cầu caller cũng là Spring bean**; nó yêu cầu cuộc gọi đến target cần được chặn phải đi qua proxy.

Một biểu hiện sai khác:

```java
PaymentService raw = new PaymentService();
new ExternalRunner(raw).run(); // Caller bên ngoài giữ raw target.
```

Lần này `ExternalRunner` không sửa được việc thiếu proxy trên `raw`. Vậy hãy kiểm tra **object được truyền vào**, thay vì chỉ hỏi caller có `@Component` hay không.

### 3.5. `@Autowired` trên object tạo bằng `new`

Field injection không tự động chạy cho object tự tạo:

```java
@Service
public class EmailProcessor {
    @Autowired
    private PaymentService paymentService;

    public void process() {
        paymentService.pay();
    }
}

// Sai nếu tự tạo đối tượng và kỳ vọng field được Spring inject:
EmailProcessor processor = new EmailProcessor();
processor.process(); // paymentService có thể là null.
```

Đây là **mã minh họa**, không nên chạy nguyên khối như ứng dụng độc lập. Annotation `@Autowired` cần Spring thực hiện injection. Với object tự `new` thông thường, field không được gắn reference. Constructor injection buộc caller truyền dependency; nếu dependency là Spring proxy, lời gọi qua nó có thể được intercept dù chính caller không được quản lý.

Một số API nâng cao như `AutowireCapableBeanFactory` có thể xử lý dependency/lifecycle của object có sẵn, nhưng **chỉ autowire một object không đảm bảo bạn đang sử dụng transaction proxy được tạo ra**. Nếu thực sự dùng API khởi tạo bean nâng cao, phải phân biệt **target ban đầu** với **reference trả về sau post-processing**. Trong trường hợp thông thường, cách rõ ràng nhất là đăng ký bean với Spring và lấy nó qua container.

## 4. Demo chạy được: cùng `@Transactional` nhưng kết quả rollback khác nhau

Ví dụ sử dụng **Java 17+, Maven, Spring Framework 6.2.8, Spring JDBC và H2 2.3.232**. Đây là project độc lập, không yêu cầu Spring Boot hay máy chủ HTTP. Chúng ta giữ nguyên phương thức `@Transactional` và dùng bốn đường gọi:

1. **Raw target:** tự tạo service bằng `new` → không có proxy → hai lệnh UPDATE auto-commit.
2. **Spring bean:** lấy service qua `context.getBean(...)` → gọi proxy → exception khiến rollback.
3. **External caller:** tự tạo caller bằng `new` nhưng truyền Spring bean proxy → rollback vẫn hoạt động.
4. **Raw target + `TransactionTemplate`:** service vẫn là object thường, song một transaction được **mở bằng mã ở bên ngoài** → rollback hoạt động dù annotation trong raw target không được Spring AOP xử lý.

Bài lab cố ý ném unchecked exception **sau khi đã chạy hai thao tác ghi**. Đọc lại database sau lỗi để biết hai thao tác được rollback hay không.

### 4.1. Cấu trúc project

```text
manual-new-transaction/
  pom.xml
  src/main/java/example/ProxyBoundaryDemo.java
```

### 4.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>manual-new-transaction</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.ProxyBoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp `ApplicationContext`/cấu hình bean; `spring-jdbc` chứa `JdbcTemplate` và `DataSourceTransactionManager`; `spring-tx` chứa annotation và transaction abstraction; H2 là một JDBC database trong bộ nhớ. H2 có mặt ở compile classpath vì code import `org.h2.jdbcx.JdbcDataSource`.

### 4.3. `src/main/java/example/ProxyBoundaryDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class ProxyBoundaryDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            // Đối tượng tự new: cùng class, cùng JdbcTemplate, nhưng không có proxy.
            WalletService raw = new WalletService(jdbc);

            // @Bean trong Config trả về new WalletService(...);
            // Spring quản lý kết quả và có thể tạo proxy.
            WalletService bean = context.getBean(WalletService.class);

            System.out.println(
                "Manual service proxy: " + AopUtils.isAopProxy(raw)
            );
            System.out.println(
                "Spring service proxy: " + AopUtils.isAopProxy(bean)
            );

            runCase(
                "manual new service",
                jdbc,
                () -> raw.transferAndFail(20)
            );

            runCase(
                "Spring-managed service",
                jdbc,
                () -> bean.transferAndFail(20)
            );

            ExternalCaller caller = new ExternalCaller(bean);
            runCase(
                "new caller with Spring proxy",
                jdbc,
                caller::execute
            );

            TransactionTemplate template = new TransactionTemplate(
                context.getBean(PlatformTransactionManager.class)
            );
            runCase(
                "manual service inside TransactionTemplate",
                jdbc,
                () -> template.executeWithoutResult(
                    status -> raw.transferAndFail(20)
                )
            );
        }
    }

    private static void runCase(
        String name,
        JdbcTemplate jdbc,
        Runnable action
    ) {
        reset(jdbc);
        System.out.println("CASE: " + name);

        try {
            action.run();
        } catch (IllegalStateException expected) {
            System.out.println("Caught: " + expected.getMessage());
        }

        Integer a = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = 1",
            Integer.class
        );
        Integer b = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = 2",
            Integer.class
        );
        System.out.println("Balances: A=" + a + ", B=" + b);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.execute("DROP TABLE IF EXISTS wallets");
        jdbc.execute(
            "CREATE TABLE wallets (" +
            "id INT PRIMARY KEY, balance INT NOT NULL)"
        );
        jdbc.update("INSERT INTO wallets(id, balance) VALUES (1, 100)");
        jdbc.update("INSERT INTO wallets(id, balance) VALUES (2, 50)");
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:manual_new_tx;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
            DataSource dataSource
        ) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public WalletService walletService(JdbcTemplate jdbcTemplate) {
            return new WalletService(jdbcTemplate);
        }
    }

    // Class có thể được Spring proxy vì public, không final,
    // method transactional public, không final.
    public static class WalletService {
        private final JdbcTemplate jdbc;

        public WalletService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transferAndFail(int amount) {
            System.out.println(
                "Transaction active: " +
                TransactionSynchronizationManager.isActualTransactionActive()
            );

            if (amount <= 0) {
                throw new IllegalArgumentException("invalid amount");
            }

            int debitCount = jdbc.update(
                "UPDATE wallets " +
                "SET balance = balance - ? " +
                "WHERE id = 1 AND balance >= ?",
                amount, amount
            );
            int creditCount = jdbc.update(
                "UPDATE wallets " +
                "SET balance = balance + ? WHERE id = 2",
                amount
            );
            if (debitCount != 1 || creditCount != 1) {
                throw new IllegalStateException("update count invalid");
            }

            throw new IllegalStateException("simulated failure");
        }
    }

    // Caller không phải bean, nhưng giữ một reference Spring proxy hợp lệ.
    public static class ExternalCaller {
        private final WalletService service;

        public ExternalCaller(WalletService service) {
            this.service = service;
        }

        public void execute() {
            service.transferAndFail(20);
        }
    }
}
```

**Giải thích thiết kế demo:**

- Cả `raw` và `bean` đều có class gốc `WalletService` và sử dụng **cùng bean `JdbcTemplate`**. Khác biệt không nằm ở câu SQL, dependency hay annotation.
- `WalletService` là class `public static` (không `final`), method `transferAndFail()` là `public`. Nó không implements một interface, nên Spring có thể dùng **class-based proxy** để bọc bean trong demo.
- `Config.walletService()` có `new WalletService(jdbcTemplate)`. Vì Spring gọi phương thức `@Bean` để **đăng ký và hoàn thiện** bean, Spring có thể tạo proxy. Còn `new WalletService(jdbc)` trong `main()` tạo raw object ngoài container.
- `@EnableTransactionManagement` bật transaction advice; `transactionManager` quản lý cùng datasource H2. `JdbcTemplate` sử dụng connection gắn với transaction của thread thông qua Spring JDBC.
- `reset()` tạo lại bảng và số dư **trước mỗi case**; vì vậy bốn case có cùng dữ liệu đầu A=100, B=50.
- Method cố ý cập nhật A trừ 20, B cộng 20, kiểm tra số hàng, rồi ném `IllegalStateException`. Exception được catch **ở phía caller sau khi đã đi qua boundary**, để có thể tiếp tục kiểm tra case kế tiếp.

### 4.4. Cách chạy

Đặt hai file đúng vị trí theo cây thư mục. Từ `manual-new-transaction`, sử dụng JDK 17 trở lên, Maven 3.9+ và kết nối repository tải dependency trong lần chạy đầu:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Các dòng **do chương trình in ra** (không tính log Maven/Spring) theo thứ tự:

```text
Manual service proxy: false
Spring service proxy: true
CASE: manual new service
Transaction active: false
Caught: simulated failure
Balances: A=80, B=70
CASE: Spring-managed service
Transaction active: true
Caught: simulated failure
Balances: A=100, B=50
CASE: new caller with Spring proxy
Transaction active: true
Caught: simulated failure
Balances: A=100, B=50
CASE: manual service inside TransactionTemplate
Transaction active: true
Caught: simulated failure
Balances: A=100, B=50
```

### 4.5. Giải thích từng kết quả

**Case 1 — `manual new service`:**

`raw` là đối tượng Java được `new` trong `main()`, không qua transaction proxy. `TransactionSynchronizationManager.isActualTransactionActive()` trả `false` vì caller chưa mở transaction. Hai lệnh `UPDATE` được `JdbcTemplate` thực thi với các JDBC connection không nằm trong một transaction Spring; trong cấu hình H2 `JdbcDataSource` của demo, chúng auto-commit. Exception ném ra **không tự rollback các lệnh đã commit**, nên A=80, B=70. Demo không có mất tổng số dư vì cố ý lỗi sau **cả hai** ghi; trong nghiệp vụ thật, lỗi xảy ra **giữa** hai ghi còn có thể để lại dữ liệu dở dang nguy hiểm hơn.

**Case 2 — `Spring-managed service`:**

`bean` được `ApplicationContext` trả về dưới dạng proxy. Interceptor mở transaction trước khi `transferAndFail` chạy, nên in `Transaction active: true`. Cả hai `UPDATE` tham gia cùng transaction. Exception `IllegalStateException` là `RuntimeException` nên mặc định `@Transactional` yêu cầu rollback; A=100, B=50 sau khi method trả lỗi. Bean có transaction không phải vì lệnh `@Bean` không dùng `new`, mà vì **Spring xử lý object returned by `@Bean`**.

**Case 3 — `new caller with Spring proxy`:**

`ExternalCaller` được `new` thủ công, nhưng giữ **bean proxy**. Lời gọi từ nó tới `service.transferAndFail(20)` vẫn qua proxy nên transaction được mở và rollback. Kết quả A=100, B=50. Điều này chứng minh **một lời gọi xuất phát từ class ngoài container vẫn có thể được intercept**.

**Case 4 — `manual service inside TransactionTemplate`:**

`raw` vẫn không phải Spring proxy, nhưng transaction đã được `TransactionTemplate` mở **trước khi raw method chạy**. Vì `raw` dùng đúng `JdbcTemplate`/datasource đã được transaction manager quản lý, hai lệnh SQL tham gia transaction ấy. Exception từ callback khiến `TransactionTemplate` rollback; A=100, B=50. Trường hợp này nhắc rằng **object raw không thể tự khởi tạo transaction nhờ annotation**, nhưng SQL do nó thực thi **vẫn có thể tham gia một transaction đang hoạt động**, nếu hạ tầng và tài nguyên được sử dụng đúng.

Bốn trường hợp không phụ thuộc vào một Spring web server. `main()` là code Java thông thường, nhưng nó lấy bean proxy từ Spring context và truyền reference tới các caller. Đó là bằng chứng rõ ràng rằng chữ «ngoài container» cần được hiểu theo **target/reference**, không chỉ theo file hoặc nơi method call được viết.

## 5. Checklist xác định vì sao `@Transactional` không chạy

Khi quan sát method có annotation nhưng rollback không như mong đợi, hãy kiểm tra theo trình tự.

### 5.1. Trước tiên: service object đến từ đâu?

```java
WalletService fromContainer = context.getBean(WalletService.class);
WalletService fromNew = new WalletService(jdbc);
```

Đây là **đoạn minh họa**, cần context và jdbc đã tồn tại. Hai reference khác nhau về lifecycle. Bean lấy từ context có cơ hội được Spring xử lý và proxy; object `new` thủ công thì không. Đừng quyết định dựa vào tên class hay việc class có `@Service`. Một instance vẫn là object raw nếu bạn tự `new` nó.

### 5.2. Đúng bean nhưng có thật là proxy không?

Trong code chẩn đoán, khi có dependency `spring-aop`:

```java
Object candidate = context.getBean("walletService");
System.out.println(AopUtils.isAopProxy(candidate));
```

Đoạn này **minh họa**, import `org.springframework.aop.support.AopUtils`. Nếu mong đợi transaction proxy mà nhận `false`, hãy kiểm tra registration, `@EnableTransactionManagement`, context sở hữu bean, class/method không thể proxy và các điều kiện hỗ trợ. Nhưng `true` chỉ chứng minh có **một AOP proxy**, chưa chắc transaction interceptor cụ thể đang hoạt động. Hãy kết hợp với quan sát transaction active và dữ liệu rollback.

### 5.3. Dependency injection đã xảy ra chưa?

- Object có `@Autowired` field được tạo thủ công bằng `new` thường chưa được inject: field có thể là `null`.
- Nếu có constructor injection, caller buộc phải cung cấp dependency. Việc truyền `JdbcTemplate` hoặc repository được container tạo vào raw service **không tự biến raw service thành Spring proxy**.
- Đăng ký object qua `@Bean`, `@Component` + component scanning thích hợp, hoặc lấy nó bằng `ObjectProvider.getObject()` khi cần scope/prototype. Đối tượng được tạo hợp lệ thông qua Spring lifecycle có thể được bọc proxy.
- Không nên giữ bản raw được tạo riêng rồi dùng song song với Spring bean proxy cùng class; dễ làm nhóm nghiệp vụ chạy với transaction semantics khác nhau.

### 5.4. Lời gọi có đi qua proxy không?

Ngay cả khi service là Spring bean, gọi nội bộ bằng `this` vẫn bỏ qua proxy trong chế độ Spring AOP phổ biến:

```java
@Service
public class BillingService {
    public void process() {
        save(); // Tự gọi trên this, không đi qua proxy của save().
    }

    @Transactional
    public void save() {
        // Ghi dữ liệu.
    }
}
```

Đây là **lớp minh họa**. Cách sửa rõ ràng thường là đặt `@Transactional` lên public entry method `process()` nếu cả nghiệp vụ cần transaction, hoặc chuyển `save()` sang bean khác rồi gọi qua injected proxy. Lời gọi `this.save()` và object `new` thủ công là hai lỗi khác nhau nhưng có chung nguyên tắc **không đi qua Spring transaction advice**.

### 5.5. Cấu hình transaction management có nằm ở đúng context?

`@EnableTransactionManagement` và `<tx:annotation-driven/>` trong chế độ proxy thông thường áp dụng cho các bean thuộc **ApplicationContext tương ứng**. Nếu service ở root context nhưng cấu hình transaction chỉ nằm trong `DispatcherServlet` child context, service root không tự được child proxy lại. Đồng thời, nếu service nằm trong child context mà advice chỉ được kích hoạt ở root, root cũng không tự post-process child bean.

Đừng đồng nhất việc child **nhìn thấy bean** ở parent với việc child **tạo transaction proxy** cho bean ấy. Với ứng dụng Boot một context chính thường đơn giản hơn, nhưng các cấu hình nhiều context vẫn cần kiểm tra ownership cụ thể.

### 5.6. Class và phương thức có thể được proxy không?

Trong class-based proxy, class `final` và method `final` không thể được CGLIB subclass/override để advice; method `private` không thể được intercept theo cách này. Với JDK interface proxy, caller cần gọi qua interface proxy và method phù hợp với interface. Phương thức `public` trong non-final service bean, được caller khác gọi qua proxy, là lựa chọn ít gây bất ngờ nhất.

`proxyTargetClass=true` có thể chọn class-based proxy trong tình huống phù hợp, nhưng **không tự biến object raw tạo bằng `new` thành bean**. `AdviceMode.ASPECTJ` có semantics khác vì sử dụng weaving và yêu cầu setup riêng; bài này nói về **proxy mode mặc định**, không suy diễn sang các trường hợp weaving.

### 5.7. Có chắc lỗi thỏa rollback rule và đúng tài nguyên?

Ngay cả khi interceptor chạy, mặc định `@Transactional` rollback đối với `RuntimeException` và `Error` chưa bị chặn, còn checked exception như `IOException` thường cần `rollbackFor` hoặc cấu hình rollback mặc định toàn cục phù hợp phiên bản Spring. Nếu method **catch exception rồi trả bình thường**, interceptor có thể commit những thay đổi trước đó nếu transaction chưa bị đánh dấu rollback-only.

Một transaction manager JDBC chỉ kiểm soát connection của datasource tham gia nó. Code raw dùng một JDBC connection **khác** hoặc gọi hệ thống ngoài (email, HTTP, message broker độc lập) sẽ không tự được rollback cùng transaction. Trường hợp dùng JDBC trực tiếp hãy bảo đảm lấy connection qua hạ tầng tham gia transaction (như `JdbcTemplate`/`DataSourceUtils`), không tùy ý gọi `dataSource.getConnection()` rồi tự quản lý khi đang chờ transaction Spring kiểm soát.

## 6. Các tình huống nên xử lý thế nào?

| Tình huống | Cách khắc phục phù hợp |
| --- | --- |
| Service có `@Transactional` nhưng được `new` tùy ý | Đăng ký làm Spring bean; inject hoặc lấy bean proxy qua `ApplicationContext` / `ObjectProvider`. |
| Một job/caller ngoài container cần gọi service | Truyền vào **proxy** lấy từ Spring; caller không nhất thiết là Spring bean. |
| Service được tạo bằng `@Bean` trả về `new` | Cách này hợp lệ vì Spring quản lý **resulting bean**; dùng reference từ context, không gọi trực tiếp factory method tùy ý. |
| Cần giao dịch cho một callback trong code không phải bean | Có thể dùng `TransactionTemplate` với manager phù hợp và các resource cùng tham gia. |
| Method transaction được gọi bằng `this.method()` | Đặt boundary ở entry point hoặc gọi qua bean khác được inject. |
| Service bean ở context cha, advice chỉ ở context con | Bật hạ tầng transaction ở đúng context sở hữu service. |
| Bean đã proxy nhưng không rollback | Kiểm tra exception rule, exception có thoát ra boundary không, manager, connection và propagation. |
| `new` một object chứa field `@Autowired` | Dùng constructor injection/bean lifecycle; đừng mặc định injection đã chạy. |

**Vấn đề quan trọng:** «sửa» bằng cách viết thêm `@Transactional` lên mọi method thường không có ích nếu lời gọi vẫn đi vào object raw. Hãy sửa **đường đi của reference** và **quyền sở hữu lifecycle** trước.

## 7. Sai lầm thường gặp và giới hạn cần nhớ

**Sai lầm 1 — «Class có `@Service` thì `new` cũng được quản lý».** Không. `@Service` là stereotype để Spring có thể phát hiện class khi component scan, không biến mọi instance của class thành bean.

**Sai lầm 2 — «`@Bean` dùng `new` nên annotation transaction trên bean hỏng».** Không. Nếu Spring gọi factory method để tạo bean và các transaction bean post-processors hoạt động, resulting bean có thể được bọc proxy bình thường. Demo trực tiếp xác nhận điều này.

**Sai lầm 3 — «Caller bên ngoài container không thể dùng transaction».** Không. Caller thường có thể gọi proxy từ Spring; lời gọi vào proxy sẽ được interceptor xử lý. Nhiều loại caller thực tế như command-line runner, test harness, scheduler, application plugin đều có thể sử dụng reference proxy được cấp hợp lệ.

**Sai lầm 4 — «Chỉ cần lấy dependency từ Spring rồi `new` service là đủ».** Không. Raw service có thể dùng `JdbcTemplate` được inject thủ công nhưng chính method `@Transactional` của raw service vẫn chưa được proxy. Demo cố ý làm như vậy để cô lập nguyên nhân.

**Sai lầm 5 — «Nếu không có proxy, không có SQL nào chạy».** Không. JDBC vẫn thực thi; trong một số cấu hình connection các câu lệnh auto-commit từng cái, dẫn tới **partial commit** khi gặp lỗi. Gắn annotation mà không có transaction boundary có thể tạo cảm giác an toàn giả.

**Sai lầm 6 — «`TransactionSynchronizationManager.isActualTransactionActive()` là bằng chứng đủ cho toàn bộ thao tác».** Chưa đủ. Nó cho biết transaction Spring hiện được xem là active trên thread; còn phải xác minh **tài nguyên truy cập dữ liệu có tham gia**, rollback rules và trạng thái database sau khi transaction kết thúc. Trường hợp code bất đồng bộ sang thread khác hoặc reactive pipeline có mô hình context riêng.

**Sai lầm 7 — «Mọi method invocation trên bean đã proxy đều được intercept».** Không. Method visibility, method final/private, interface proxy và self-invocation có giới hạn. Việc proxy tồn tại cũng không buộc một method không có transaction metadata mở transaction.

**Sai lầm 8 — «Object raw không bao giờ chạy trong transaction».** Không. Object raw không tự tạo transaction bằng annotation; nhưng các JDBC thao tác của nó vẫn có thể tham gia một transaction đã được caller/template tạo trên cùng thread và datasource. Demo `TransactionTemplate` đã cho thấy điều này.

**Sai lầm 9 — «Mở thread mới vẫn giữ transaction của caller».** Với transaction imperative của Spring, tài nguyên thường gắn với thread hiện tại; `new Thread`, `@Async` hoặc `CompletableFuture` không tự mang transaction sang thread khác. Đối với R2DBC/reactive cần `ReactiveTransactionManager` và Reactor Context; không nhầm hai mô hình.

**Sai lầm 10 — «Test có `@Transactional` pass tức là service tự mở transaction».** Spring Test có thể mở transaction cho **test method** rồi rollback toàn bộ sau test. Code raw chạy trong test transaction sẽ khiến người viết nghĩ annotation trên raw service có tác dụng. Kiểm thử nên gọi service khi không có transaction bao ngoài (hoặc chủ động kiểm soát ranh giới test) và quan sát dữ liệu sau commit/rollback của service.

## 8. Tự kiểm tra và bài tập

Trước khi làm bài thực hành, hãy dự đoán rồi chạy demo:

| Case | Target `WalletService` | Caller | Transaction chủ động được mở ở đâu? | Kỳ vọng sau lỗi |
| --- | --- | --- | --- | --- |
| 1 | `new WalletService(jdbc)` | `main()` | Không | A=80, B=70 |
| 2 | Bean proxy từ `context.getBean` | `main()` | Transaction interceptor | A=100, B=50 |
| 3 | Bean proxy từ `context.getBean` | `new ExternalCaller(bean)` | Transaction interceptor | A=100, B=50 |
| 4 | Raw `new WalletService(jdbc)` | `TransactionTemplate` | Template bên ngoài | A=100, B=50 |

Các thí nghiệm bổ sung:

1. **Thay reference:** sửa `new ExternalCaller(bean)` thành `new ExternalCaller(raw)`, chạy lại. Dự đoán `Transaction active` và số dư; giải thích vì sao nơi tạo caller vẫn y hệt nhưng kết quả đổi.
2. **Bỏ hạ tầng transaction:** bỏ `@EnableTransactionManagement` trong `Config`, lấy lại `WalletService` qua context và dự đoán `AopUtils.isAopProxy(bean)`. Phân biệt `@Transactional` metadata với advisor runtime.
3. **Đổi nơi tạo service:** bỏ `@Bean walletService(...)` và đăng ký `WalletService` bằng `@Component` + `@ComponentScan` đúng phạm vi, với constructor injection. Mục tiêu là Spring vẫn sở hữu bean và tạo proxy, bất kể bean được phát hiện bằng cách nào.
4. **Bắt lỗi trong service:** sửa `transferAndFail` để bắt và nuốt `IllegalStateException` trước khi trả ra proxy; dự đoán liệu mặc định Spring có rollback hay không. Phân biệt rollback policy với việc exception có thật sự đi qua boundary.
5. **Dời transaction boundary:** giữ raw service nhưng bọc lời gọi của nó trong `TransactionTemplate` như case 4. Giải thích vì sao transaction có thật dù `@Transactional` trên raw vẫn không được proxy.
6. **Suy nghĩ về dữ liệu thật:** sửa demo ném lỗi **giữa** trừ tiền và cộng tiền. Với raw service, số dư A sẽ thay đổi còn B chưa tăng; với proxy service, A và B trở về giá trị cũ. Đây là kiểm thử quan trọng hơn so với chỉ quan sát log.

Các câu hỏi tự đánh giá:

- `@Transactional` có tự làm gì khi JVM gọi method trên object vừa `new` không?
- Khi nào `@Bean` được phép trả về `new SomeService(...)` và vẫn được Spring AOP xử lý?
- Caller `new ExternalCaller(proxy)` có bị mất transaction chỉ vì caller không là bean không?
- Vì sao một method raw có thể in transaction active = true khi được gọi từ `TransactionTemplate`?
- Khi log hiển thị AOP proxy nhưng rollback sai, nên kiểm tra điều gì tiếp theo?

## 9. Tài liệu tham khảo chính thức

- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): annotation là metadata; transaction runtime nhờ infrastructure/proxy; self-invocation và transaction boundary.
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): `TransactionInterceptor`, `TransactionManager` và AOP proxy.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): khác biệt giữa gọi target và gọi proxy, JDK/CGLIB, self-invocation.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` mở transaction bằng mã.
- [Spring Framework — `@Bean` Methods](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): object được tạo qua factory method do container quản lý.
