# Bật quản lý giao dịch bằng `@EnableTransactionManagement` trong Spring Framework

## 1. Mục tiêu của bài học

Khi viết ứng dụng Spring thuần (không dựa vào transaction auto-configuration của Spring Boot), ta cần **bật cơ chế xử lý `@Transactional`** và cung cấp một **transaction manager** phù hợp. `@EnableTransactionManagement` là annotation cấu hình giúp Spring nhận biết, chặn lời gọi phương thức và áp dụng ranh giới giao dịch khai báo.

Sau bài này, bạn có thể:

- Giải thích vì sao chỉ đặt `@Transactional` trên service chưa đủ.
- Đặt `@EnableTransactionManagement` đúng chỗ trong cấu hình Java.
- Khai báo `DataSource`, `PlatformTransactionManager` và service là Spring bean.
- Chạy một giao dịch thành công và một giao dịch rollback với Java 17+, Spring Framework và H2.
- Nhận diện các lỗi thường gặp: gọi trực tiếp đối tượng, tự gọi trong cùng class, thiếu manager, nhầm `proxyTargetClass`, nhầm Spring Boot với Spring thuần.

**Phạm vi chính:** giao dịch imperative (đồng bộ) qua Spring AOP proxy và JDBC. Ứng dụng reactive có cơ chế quản lý transaction khác; phần cuối chỉ lưu ý để tránh áp dụng nhầm.

## 2. Vì sao `@Transactional` một mình chưa đủ?

Ví dụ, ta viết:

```java
public class PaymentService {
    @Transactional
    public void pay() {
        // Ghi dữ liệu vào cơ sở dữ liệu
    }
}
```

`@Transactional` chỉ là **metadata** mô tả mong muốn quản lý giao dịch. Nó không tự biến mọi đối tượng Java thành đối tượng được Spring quản lý và không tự tạo transaction manager.

Trong cấu hình Spring thuần dùng JavaConfig, cần đủ các mảnh ghép:

| Thành phần | Trách nhiệm |
| --- | --- |
| `@Configuration` + `@EnableTransactionManagement` | Kích hoạt hạ tầng xử lý transaction annotation trong Spring ApplicationContext. |
| `@Transactional` | Đánh dấu phương thức/lớp cần ranh giới giao dịch và cấu hình propagation, rollback, isolation, read-only... |
| `PlatformTransactionManager` | Bắt đầu, commit, rollback transaction vật lý cho công nghệ dữ liệu tương ứng. Ví dụ: `JdbcTransactionManager`, `DataSourceTransactionManager` hoặc `JpaTransactionManager`. |
| `DataSource` / tài nguyên dữ liệu | Cung cấp kết nối thực tế đến cơ sở dữ liệu. |
| Spring-managed bean và lời gọi qua proxy | Cho transaction interceptor cơ hội chặn lời gọi phương thức. |

`@EnableTransactionManagement` **không tự tạo `DataSource` hoặc transaction manager**. Nếu thiếu transaction manager, lỗi có thể xuất hiện khi gọi phương thức `@Transactional` thay vì ở thời điểm chỉ đọc annotation.

### Luồng hoạt động

```text
ApplicationContext khởi tạo
  |
  +-- Đọc @Configuration và @EnableTransactionManagement
  +-- Đăng ký transaction advisor + TransactionInterceptor + AOP auto-proxy
  +-- Tạo các bean, trong đó có DataSource và transactionManager
  '-- Tạo proxy cho bean có phương thức @Transactional phù hợp

Code bên ngoài gọi Spring bean (proxy)
  |
  +-- TransactionInterceptor chọn transaction manager
  +-- Bắt đầu transaction mới hoặc tham gia transaction hiện có
  +-- Gọi phương thức nghiệp vụ
  +-- Trả về bình thường: commit khi proxy sở hữu transaction cần hoàn tất
  '-- Ném lỗi: xét quy tắc rollback/commit rồi truyền exception cho caller
```

**Điểm mấu chốt:** interceptor bao quanh lời gọi qua **proxy**. Với chế độ mặc định `AdviceMode.PROXY`, một lời gọi `this.someMethod()` bên trong chính đối tượng không tự đi qua proxy để áp dụng một cấu hình `@Transactional` mới.

## 3. Cách bật tối thiểu bằng JavaConfig

Trong Spring Framework thuần, cấu hình có hình thức:

```java
@Configuration
@EnableTransactionManagement
public class TransactionConfig {

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Đây là **đoạn cấu hình minh họa**, chưa đủ để chạy độc lập: `DataSource` phải được tạo ở cùng ApplicationContext hoặc import từ cấu hình khác; service cũng phải là Spring bean. Ví dụ đầy đủ bên dưới bổ sung cả hai.

Ý nghĩa của từng dòng:

1. `@Configuration`: báo Spring rằng class chứa bean definitions/cấu hình.
2. `@EnableTransactionManagement`: bật transaction advice dựa trên `@Transactional`. Không cần gắn thêm `@EnableAspectJAutoProxy` chỉ để bật transaction annotation trong ví dụ cơ bản.
3. `@Bean transactionManager(...)`: cung cấp manager để Spring có thể thực sự mở/đóng transaction.
4. `JdbcTransactionManager`: quản lý transaction JDBC cho chính `DataSource` được inject. `JdbcTemplate` dùng trong service cũng phải truy cập cùng tài nguyên ấy để tham gia transaction.

Có thể dùng `DataSourceTransactionManager` thay cho `JdbcTransactionManager` với JDBC; cả hai đều quản lý giao dịch cục bộ trên một `DataSource`. Khi dùng JPA, thường dùng `JpaTransactionManager` đã được cấu hình cho persistence unit, không sao chép nguyên xi cấu hình JDBC sang JPA.

## 4. Demo hoàn chỉnh: bật quản lý và chứng minh rollback

Dự án minh họa dùng **Java 17+, Spring Framework 6.2.19, Maven và H2 in-memory**. Không cần Spring Boot, Docker hoặc database server riêng.

Cấu trúc hai file:

```text
enable-transaction-demo/
├── pom.xml
└── src/main/java/com/example/tx/EnableTxDemo.java
```

### 4.1. Tạo `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>enable-transaction-demo</artifactId>
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
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.4.240</version>
            <scope>runtime</scope>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp container/JavaConfig, `spring-jdbc` cung cấp `JdbcTemplate` và JDBC transaction manager, `spring-tx` chứa transaction annotation/API, H2 là database thử nghiệm. Các phiên bản đã được cố định để việc chạy lại ví dụ không phụ thuộc phiên bản mới nhất ở thời điểm học.

### 4.2. Tạo `EnableTxDemo.java`

```java
package com.example.tx;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class EnableTxDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(TxConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE demo_accounts (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO demo_accounts (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO demo_accounts (id, balance) VALUES (?, ?)", 2, 100);

            MoneyService service = context.getBean(MoneyService.class);
            printBalances("INIT", jdbc);

            service.transfer(1, 2, 30, false);
            printBalances("AFTER_COMMIT", jdbc);

            try {
                service.transfer(1, 2, 20, true);
            } catch (IllegalStateException ex) {
                System.out.println("EXPECTED_ERROR=" + ex.getMessage());
            }
            printBalances("AFTER_ROLLBACK", jdbc);
        }
    }

    private static void printBalances(String prefix, JdbcTemplate jdbc) {
        int a = jdbc.queryForObject(
                "SELECT balance FROM demo_accounts WHERE id = ?", Integer.class, 1);
        int b = jdbc.queryForObject(
                "SELECT balance FROM demo_accounts WHERE id = ?", Integer.class, 2);

        System.out.printf("%s: A=%d, B=%d%n", prefix, a, b);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class TxConfig {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:transaction_lesson;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public MoneyService moneyService(JdbcTemplate jdbcTemplate) {
            return new MoneyService(jdbcTemplate);
        }
    }

    public static class MoneyService {
        private final JdbcTemplate jdbc;

        public MoneyService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transfer(int from, int to, int amount, boolean failAfterDebit) {
            System.out.println("IN_TRANSACTION="
                    + TransactionSynchronizationManager.isActualTransactionActive());

            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            int debited = jdbc.update(
                    "UPDATE demo_accounts SET balance = balance - ? "
                    + "WHERE id = ? AND balance >= ?",
                    amount, from, amount);
            if (debited != 1) {
                throw new IllegalArgumentException("source missing or insufficient funds");
            }

            // Mô phỏng lỗi xảy ra sau khi đã gửi câu SQL trừ tiền.
            if (failAfterDebit) {
                throw new IllegalStateException("simulated failure");
            }

            int credited = jdbc.update(
                    "UPDATE demo_accounts SET balance = balance + ? WHERE id = ?",
                    amount, to);
            if (credited != 1) {
                throw new IllegalArgumentException("destination account missing");
            }
        }
    }
}
```

Ví dụ gói cả cấu hình, service và hàm `main` vào **một file Java** nhờ các class `static` lồng nhau. `MoneyService` được đăng ký qua `@Bean`, rồi được lấy ra bằng `context.getBean(...)`; đây là điều kiện để lời gọi đi qua Spring proxy. Trong ứng dụng thật, có thể tách `@Configuration` và `@Service` thành các file riêng, dùng `@ComponentScan` hoặc cấu hình Spring Boot.

**Chú ý:** `DriverManagerDataSource` thích hợp cho demo ngắn; ứng dụng production nên dùng connection pool được cấu hình phù hợp. Tài khoản H2 và số dư ở đây là dữ liệu giả để quan sát ranh giới transaction.

### 4.3. Chạy ví dụ và kiểm tra kết quả

Trong thư mục chứa `pom.xml`, chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.tx.EnableTxDemo
```

Các dòng chính do chương trình in (không tính log công cụ/khởi tạo):

```text
INIT: A=100, B=100
IN_TRANSACTION=true
AFTER_COMMIT: A=70, B=130
IN_TRANSACTION=true
EXPECTED_ERROR=simulated failure
AFTER_ROLLBACK: A=70, B=130
```

**Giải thích từng mốc:**

1. `AnnotationConfigApplicationContext(TxConfig.class)` nạp `@EnableTransactionManagement`, các bean và hạ tầng transaction.
2. Lời gọi `service.transfer(..., false)` đi qua proxy. Spring mở transaction trước khi vào thân phương thức, nên `IN_TRANSACTION=true`. Hai câu `UPDATE` thành công; interceptor commit khi phương thức kết thúc bình thường. A giảm 30, B tăng 30.
3. Lời gọi `service.transfer(..., true)` cũng chạy trong transaction. Câu `UPDATE` trừ 20 đã được thực thi trong transaction, sau đó ném `IllegalStateException`. Vì đây là `RuntimeException`, interceptor rollback theo quy tắc mặc định; hai số dư **không đổi**.
4. `printBalances(...)` được gọi từ `main` sau khi lời gọi qua proxy đã hoàn tất; kết quả đọc cuối cùng xác nhận tác dụng của commit/rollback.

`TransactionSynchronizationManager.isActualTransactionActive()` là cách quan sát transaction đang hoạt động ở thread hiện tại; **chỉ một dòng `true` không chứng minh commit đã thành công**. Cần kiểm tra trạng thái dữ liệu sau ranh giới transaction, như ví dụ này.

### 4.4. Thí nghiệm đối chứng: điều gì xảy ra nếu chưa bật?

Chỉ trong dự án thử nghiệm, tạm bỏ `@EnableTransactionManagement` ở `TxConfig` rồi chạy lại. Khi không có thành phần khác kích hoạt transaction advice, `@Transactional` không tạo proxy giao dịch:

- `IN_TRANSACTION` sẽ là `false`.
- Các câu `JdbcTemplate.update(...)` độc lập chạy với JDBC auto-commit của H2.
- Lần chuyển tiền thất bại sau câu trừ tiền sẽ để lại trạng thái **A=50, B=130**: A đã trừ thêm 20 nhưng B chưa nhận tiền.

Thí nghiệm trước–sau cho thấy chức năng thực tế của `@EnableTransactionManagement`. **Không thực hiện kiểu thử này trên dữ liệu thật.** Sau thí nghiệm, thêm lại annotation để khôi phục transaction management.

## 5. Đọc đúng cấu hình: ba điều kiện phải đồng thời đúng

### 5.1. Annotation được xử lý trong đúng `ApplicationContext`

Đặt `@EnableTransactionManagement` lên class cấu hình được **Spring thực sự nạp**. Class có annotation nhưng không được scan/import/đăng ký vào container sẽ không có tác dụng.

Hạ tầng transaction annotation xử lý các bean trong **cùng ApplicationContext**. Với ứng dụng web cổ điển có root context và child `DispatcherServlet` context, cấu hình đặt ở context của controller có thể không áp dụng cho service bean chỉ thuộc root context. Hãy đặt cấu hình ở context sở hữu service hoặc cấu trúc context phù hợp.

### 5.2. Có transaction manager tương thích

Demo đăng ký:

```java
@Bean
public PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

Tên `transactionManager` giúp cấu hình dễ hiểu, đặc biệt khi bắt đầu học. Nếu có **nhiều transaction manager**, cần chỉ định rõ manager mà phương thức dùng, ví dụ:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder() {
    // Giao dịch trên tài nguyên do ordersTransactionManager quản lý.
}
```

Đây chỉ là **minh họa chọn manager**, không phải phương thức độc lập có thể chạy ngay. Cũng có thể chọn manager mặc định bằng `TransactionManagementConfigurer` khi cấu hình yêu cầu. Đừng cho rằng `@EnableTransactionManagement` tự đoán đúng manager giữa nhiều DataSource hoặc tự tạo giao dịch phân tán cho nhiều cơ sở dữ liệu.

### 5.3. Lời gọi phải qua Spring proxy

Hai cách dùng trông tương tự nhưng có ngữ nghĩa khác nhau:

```java
MoneyService managed = context.getBean(MoneyService.class);
managed.transfer(1, 2, 10, false); // Đi qua bean/proxy của Spring

MoneyService unmanaged = new MoneyService(jdbc);
unmanaged.transfer(1, 2, 10, false); // Đối tượng tự tạo, không có proxy giao dịch
```

Đây là **mã minh họa**, không nằm trong luồng chạy ở mục 4; không thực thi cả hai dòng này trên cùng dữ liệu rồi lấy kết quả thay cho demo. Một cách gọi thông qua `new` không được container áp transaction advice. Tương tự, với proxy mode, gọi `this.inner()` trong cùng object sẽ không đi qua proxy: annotation transaction riêng của `inner()` không được xử lý ở lần gọi đó. Nếu outer đã ở trong transaction, thao tác của inner vẫn có thể **tham gia transaction outer**; điều bị bỏ qua là ranh giới/advice riêng của inner.

## 6. `@EnableTransactionManagement` có những tùy chọn nào?

| Tùy chọn | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `mode` | `AdviceMode.PROXY` | Dùng AOP proxy; chỉ chặn lời gọi đi qua proxy. |
| `proxyTargetClass` | `false` | Ưu tiên proxy dựa trên interface khi có interface phù hợp; nếu không có interface thì vẫn có thể dùng proxy lớp. |
| `order` | `Ordered.LOWEST_PRECEDENCE` | Độ ưu tiên của transaction advice so với các advice khác. |

Ví dụ yêu cầu proxy dựa trên lớp:

```java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TxConfig {
    // @Bean DataSource, PlatformTransactionManager, service...
}
```

Đây là **mã minh họa tùy chọn**, không thay thế toàn bộ `TxConfig` trong demo. `proxyTargetClass=true` hữu ích khi cần class-based proxy, nhưng **không chữa được self-invocation**; phương thức/class `final` cũng không thể được lớp proxy override để áp advice. Với thiết kế phổ biến, nên đặt `@Transactional` trên phương thức public của concrete service class.

`AdviceMode.ASPECTJ` là lựa chọn nâng cao dùng weaving và module `spring-aspects`, cần cấu hình compile-time/load-time weaving thực sự; chỉ đổi `mode` mà không có weaving **không đủ**. Trong bài giao dịch đầu tiên, proxy mode mặc định là lựa chọn phù hợp.

## 7. Spring Boot có cần tự thêm `@EnableTransactionManagement` không?

**Phân biệt hai cách khởi tạo dự án:**

- **Spring Framework thuần:** nếu dùng transaction annotation, thường chủ động khai báo `@EnableTransactionManagement` và bean `PlatformTransactionManager` như demo này.
- **Spring Boot:** với starter JDBC/JPA và điều kiện auto-configuration phù hợp, Boot thường tự cấu hình transaction manager và kích hoạt xử lý transaction annotation. Vì vậy phần lớn dự án Boot **không cần viết thêm `@EnableTransactionManagement`** chỉ để dùng `@Transactional`.

Nếu một ứng dụng Boot đã cấu hình sẵn transaction management, thêm annotation một cách máy móc không giải quyết được lỗi thiếu `DataSource`, chọn sai manager hoặc gọi lệch proxy. Khi có nhiều datasource, manager hoặc tùy chỉnh transaction advice, kiểm tra cấu hình thực tế thay vì suy luận từ việc annotation hiện diện.

## 8. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `@Transactional` có nhưng lỗi giữa hai câu SQL vẫn làm dữ liệu dở dang | Chưa bật transaction advice hoặc gọi object bằng `new`/không qua proxy. | Xác nhận JavaConfig đã nạp, lấy service từ container và kiểm thử rollback. |
| Không tìm thấy transaction manager khi thực thi | Chưa đăng ký bean manager phù hợp; có nhiều manager nhưng không chọn rõ. | Tạo `PlatformTransactionManager`; chọn đúng bằng qualifier/`transactionManager` nếu cần. |
| Service trong một context, `@EnableTransactionManagement` ở context khác | Hạ tầng chỉ quét transaction annotations trên bean thuộc context chứa cấu hình. | Đặt cấu hình đúng ApplicationContext sở hữu service. |
| Annotation ở `private`/`final` method hoặc gọi `this.inner()` | Proxy không chặn được lời gọi/method theo cách mong muốn. | Đặt ranh giới transaction ở public service method, gọi qua bean khác/proxy; không dựa vào tự gọi. |
| Đặt `@Transactional` ở interface và đổi loại proxy | Khả năng nhận diện annotation phụ thuộc kiểu proxy/weaving và cấu hình. | Ưu tiên annotate phương thức của concrete class. |
| Dùng `JdbcTransactionManager` với `DataSource` khác `JdbcTemplate` | Connection của thao tác SQL có thể không tham gia transaction mà manager đang điều khiển. | Đảm bảo cùng tài nguyên `DataSource`, dùng Spring JDBC/DataSourceUtils đúng cách. |
| Mong mọi exception đều rollback | Quy tắc mặc định rollback với `RuntimeException` và `Error`; checked exception thường không tự rollback. | Dùng `@Transactional(rollbackFor = SomeCheckedException.class)` khi nghiệp vụ yêu cầu. |
| Khởi tạo bean bằng `@PostConstruct` rồi gọi phương thức transaction | Proxy có thể chưa sẵn sàng để áp dụng advice trong giai đoạn khởi tạo. | Chạy logic nghiệp vụ sau khi container khởi tạo, qua service bean/proxy. |
| Thấy `IN_TRANSACTION=true` nhưng vẫn có dữ liệu khác chưa commit | Transaction còn mở hoặc phương thức chỉ tham gia transaction ngoài; kết quả hiển thị chưa phản ánh commit cuối cùng. | Xác định ranh giới transaction ngoài và quan sát dữ liệu sau khi nó hoàn tất. |

### Hai lưu ý để tránh kết luận sai

**Một:** Spring mặc định dùng `Propagation.REQUIRED`. Nếu đã có transaction ngoài, lời gọi `@Transactional` bên trong thường tham gia transaction đó; phương thức con kết thúc **không có nghĩa** transaction vật lý đã commit.

**Hai:** Transaction JDBC thông thường được gắn với thread thực thi. Không suy ra rằng tạo thread mới, `@Async` hoặc chuyển sang xử lý reactive thì transaction context tự đi theo. Với reactive transaction, Spring sử dụng `ReactiveTransactionManager` và Reactor context, không áp dụng nguyên sơ đồ JDBC thread-bound của demo.

## 9. Checklist trước khi coi là đã bật transaction thành công

1. Class `@Configuration` có `@EnableTransactionManagement` đã được đăng ký trong ApplicationContext chứa service.
2. Có `PlatformTransactionManager` đúng công nghệ và đúng datasource; khi có nhiều manager, chọn manager rõ ràng.
3. Service là Spring bean, được gọi từ bên ngoài qua proxy; phương thức transaction là điểm vào nghiệp vụ phù hợp.
4. Chạy thử case commit và case ném `RuntimeException` **sau ít nhất một câu SQL**, quan sát DB cuối cùng để thấy rollback.
5. Không lấy kết quả `save()`, log trước `return` hoặc `isActualTransactionActive()` làm bằng chứng duy nhất cho **commit thành công**.
6. Với Spring Boot, xác định auto-configuration đã bật sẵn hay cần cấu hình tùy chỉnh trước khi thêm annotation.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Chỉ dùng `@Transactional` trên một class được tạo bằng `new`, không có Spring context. Có transaction do Spring quản lý không?

**Đáp án:** Không. Annotation chỉ là metadata; object không phải Spring-managed bean/proxy.

**Câu 2.** Thêm `@EnableTransactionManagement` nhưng không tạo bất kỳ transaction manager nào. Có thể dùng JDBC `@Transactional` đúng nghĩa ngay không?

**Đáp án:** Không. Cần manager phù hợp để mở/commit/rollback transaction. Lỗi có thể chỉ xuất hiện khi lời gọi `@Transactional` được thực thi.

**Câu 3.** Demo gọi `transfer(...)` qua bean, ném `IllegalStateException` sau câu trừ tiền. Vì sao A không bị trừ 20?

**Đáp án:** `IllegalStateException` là unchecked exception; Spring transaction interceptor rollback cùng transaction JDBC đã chứa câu `UPDATE`.

**Câu 4.** Tại sao một dự án Spring Boot dùng `@Transactional` dù không thấy `@EnableTransactionManagement` trong source?

**Đáp án:** Boot có thể đã bật và cấu hình transaction infrastructure thông qua auto-configuration của starter/tài nguyên phù hợp. Cần kiểm tra setup thực tế.

## Ghi nhớ

**`@EnableTransactionManagement` bật xử lý transaction annotation; `@Transactional` mô tả ranh giới nghiệp vụ; `PlatformTransactionManager` thực hiện giao dịch; Spring proxy là đường đi để interceptor áp dụng transaction.** Hãy kiểm chứng bằng một ca rollback thật, không chỉ bằng việc code biên dịch hoặc có annotation.

## Tài liệu tham khảo chính thức

- Spring Framework 6.2 — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- Spring Framework — [Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- Spring Framework — [Spring AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- Spring Framework — [`@EnableTransactionManagement` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html)
