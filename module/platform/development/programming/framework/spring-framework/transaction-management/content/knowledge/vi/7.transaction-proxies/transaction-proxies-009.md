# Thời điểm khởi tạo bean và giới hạn trong `@PostConstruct` với Spring transactional proxy

## Mục tiêu

Bài này giải thích vì sao `@Transactional` không đảm bảo mở transaction khi một Spring bean đang được khởi tạo, đặc biệt trong `@PostConstruct`. Sau khi học, bạn có thể xác định thứ tự callback và thời điểm proxy có hiệu lực, phân biệt lỗi lifecycle với self-invocation, quan sát transaction bằng Java 17 + Spring JDBC, và lựa chọn thời điểm thích hợp để chạy nghiệp vụ có transaction sau khi application context sẵn sàng.

**Ý chính:** trong chế độ mặc định **Spring AOP proxy**, chỉ những lời gọi phương thức phù hợp **đi từ bên ngoài qua proxy đã sẵn sàng** mới được transaction interceptor chặn. `@PostConstruct` do container gọi trong giai đoạn khởi tạo target bean, khi không thể dựa vào transactional proxy của chính bean đó.

## 1. `@Transactional` phụ thuộc vào đường gọi qua proxy

Với cấu hình `@EnableTransactionManagement` (hoặc Boot auto-configuration tương ứng), Spring dùng AOP proxy cho các bean đủ điều kiện. Khi bean khác gọi một public method có `@Transactional` qua tham chiếu proxy, Spring chạy `TransactionInterceptor`, chọn `PlatformTransactionManager` cho JDBC/JPA, rồi bắt đầu/tham gia transaction, gọi target và commit hoặc rollback tùy kết quả. Phạm vi của bài là transaction **imperative**, nhưng nguyên tắc thời điểm tạo proxy cũng quan trọng khi áp dụng transaction reactive.

```text
Caller
  |
  v
Spring AOP proxy -- TransactionInterceptor
  |                        |
  |                        +--> TransactionManager:
  |                             begin/join, commit/rollback
  v
TargetBean.transactionalMethod()
```

Chữ `@Transactional` là metadata, không tự biến một lời gọi Java thông thường thành transaction. Để advice chạy, tối thiểu cần: transaction management được bật, transaction manager phù hợp, method đủ điều kiện được proxy chặn, và caller thực sự đi qua proxy.

Hai lỗi riêng biệt dễ bị nhầm:

1. **Chưa đúng thời điểm:** callback chạy khi target đang được khởi tạo, proxy chưa được công bố/hoàn tất.
2. **Không đúng đường đi:** `this.otherMethod()` gọi nội bộ trên target; mặc dù bean đã khởi tạo xong, vẫn bỏ qua proxy.

Sửa lỗi thứ nhất không tự sửa lỗi thứ hai.

## 2. Lifecycle của bean: `@PostConstruct` xảy ra trước bước tạo proxy thông thường

Với singleton thông thường, một sơ đồ hợp lý là:

```text
1. Constructor: tạo target bean
       |
2. Dependency injection: gán field/constructor/property
       |
3. BeanPostProcessor.postProcessBeforeInitialization
       |  CommonAnnotationBeanPostProcessor gọi @PostConstruct
       |
4. InitializingBean.afterPropertiesSet() (nếu có)
       |
5. Custom init-method (nếu có)
       |
6. BeanPostProcessor.postProcessAfterInitialization
       |  AOP auto-proxy creator thường tạo/trả về proxy
       |
7. Bean được công bố dưới tham chiếu hoàn chỉnh
       |
8. Bean khác gọi method qua proxy
       |  TransactionInterceptor có thể áp dụng @Transactional
```

Đây là thứ tự khái quát cho trường hợp chuẩn, không phải mọi trường hợp đặc biệt của bean scope, bean post-processor tùy biến hay circular dependency đều giống hoàn toàn. Tuy nhiên Spring ghi rõ initialization callbacks chạy trên **raw bean reference** trước khi AOP interceptors được áp dụng; proxy cần hoàn tất để giao dịch hoạt động như mong đợi.

`CommonAnnotationBeanPostProcessor` nhận biết `jakarta.annotation.PostConstruct`; các Spring Framework 6+ sử dụng namespace `jakarta.annotation`, không phải `javax.annotation` phổ biến ở mã Spring 5 cũ. `@PostConstruct` thường là phương thức không tham số, trả `void`, do container gọi một lần trong mỗi vòng đời tạo bean (bean có thể bị tạo lại theo scope/context).

Trong khi khởi tạo singleton, Spring có cơ chế khóa/phối hợp nội bộ. Tài liệu Spring khuyến nghị dùng `@PostConstruct` để xác nhận cấu hình và chuẩn bị dữ liệu cục bộ; việc gọi bean khác, tác vụ DB tốn thời gian, asynchronous preparation hoặc tương tác ngoại hệ thống có thể gây chậm khởi động hay deadlock.

| Vị trí thực thi | Đang gọi trên target/proxy? | Có thể tin `@Transactional` trên chính callback? |
|---|---|---|
| Constructor | Target đang xây dựng | Không |
| `@PostConstruct` | Lifecycle processor gọi target | **Không** |
| `InitializingBean.afterPropertiesSet()` | Initialization callback trên target | **Không** |
| Custom `init-method` | Initialization callback trên target | **Không** |
| Lời gọi ngoài bean sau context refresh | Tham chiếu proxy Spring | Có, nếu manager và method hợp lệ |
| `this.save()` trong cùng bean | Gọi trực tiếp target | Không, trong proxy mode |
| Runner/event listener gọi service **khác** đã proxied | Service được gọi qua proxy | Có, nếu cấu hình đúng |

Một bean khác đã tạo xong có thể có proxy ngay cả khi bean hiện tại vẫn đang init, nhưng không nên biến trình tự tạo các dependency thành cơ chế transaction ngầm cho callback. Ranh giới transaction nên được thiết kế rõ ràng.

## 3. Vì sao hai kiểu `@PostConstruct` sau đây sai?

### 3.1. Đặt `@Transactional` ngay trên `@PostConstruct`

```java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class UnsafeStartup {
    @PostConstruct
    @Transactional
    public void initialize() {
        // Không được giả định code này chạy trong Spring transaction.
    }
}
```

Đoạn code là **minh họa lỗi**, chưa là chương trình Java độc lập. Lifecycle processor gọi `initialize()` trong quá trình khởi tạo raw target. Dù annotation có mặt, Spring không bảo đảm interception tại thời điểm này. Với JDBC, nếu connection đang auto-commit, các thao tác ghi có thể commit riêng lẻ; một exception ở giữa không hoàn tác các lệnh ghi trước đó chỉ vì method có `@Transactional`.

### 3.2. Gọi method transaction của chính mình từ `@PostConstruct`

```java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AlsoUnsafe {
    @PostConstruct
    public void init() {
        this.seedData();
    }

    @Transactional
    public void seedData() {
        // Lệnh this.seedData() không đi qua Spring AOP proxy.
    }
}
```

Đây là **self-invocation**. `this.seedData()` là lời gọi trên cùng instance target, bỏ qua transaction interceptor. Lỗi vẫn tồn tại sau khi startup xong, ví dụ method `process()` trong cùng bean gọi `this.seedData()`. Không được xem đây chỉ là “lỗi do `@PostConstruct` chạy quá sớm”.

## 4. Thực nghiệm Java 17: cùng method, kết quả khác nhau giữa proxy và self-invocation

Ví dụ hoàn chỉnh sau dùng Spring Framework 6.2, H2 in-memory và Spring JDBC. Nó cố ý đưa một lệnh INSERT vào method luôn ném `IllegalStateException` để đối chiếu rollback:

- Lời gọi bên ngoài qua proxy có transaction: INSERT bị rollback, đếm bản ghi bằng 0.
- Lời gọi nội bộ qua `this` không có transaction: H2/JDBC auto-commit lệnh INSERT, đếm bản ghi bằng 1.
- Trong `@PostConstruct`, dù method có `@Transactional`, trạng thái actual transaction vẫn là `false`.

### 4.1. Cấu trúc dự án

```text
spring-tx-initialization/
├── pom.xml
└── src/main/java/com/example/txinit/Main.java
```

### 4.2. Tệp `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-tx-initialization</artifactId>
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
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp application context và AOP infrastructure liên quan; `spring-jdbc` cung cấp `JdbcTemplate` và `JdbcTransactionManager`. H2 dùng làm database mẫu và `jakarta.annotation-api` cho `@PostConstruct` trên JDK 17. Phiên bản dependency được pin để tái hiện ví dụ; dự án thật nên sử dụng BOM/quy trình cập nhật phiên bản.

### 4.3. Tệp `src/main/java/com/example/txinit/Main.java`

```java
package com.example.txinit;

import jakarta.annotation.PostConstruct;
import javax.sql.DataSource;

import org.springframework.aop.support.AopUtils;
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

public class Main {

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:txinit;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public LedgerService ledgerService(JdbcTemplate jdbc) {
            return new LedgerService(jdbc);
        }
    }

    public static class LedgerService {
        private final JdbcTemplate jdbc;

        public LedgerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @PostConstruct
        @Transactional
        public void initialize() {
            System.out.println("init transaction=" + txActive());
            this.printTx("init self-call");
        }

        @Transactional
        public void printTx(String source) {
            System.out.println(source + " transaction=" + txActive());
        }

        @Transactional
        public void insertThenFail(String label) {
            System.out.println(label + " insert transaction=" + txActive());
            jdbc.update("INSERT INTO tx_log(label) VALUES (?)", label);
            throw new IllegalStateException("planned failure");
        }

        public void selfInvoke() {
            try {
                this.insertThenFail("self");
            } catch (IllegalStateException ex) {
                System.out.println("self error=" + ex.getMessage());
            }
        }

        private static boolean txActive() {
            return TransactionSynchronizationManager.isActualTransactionActive();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE tx_log (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
                "label VARCHAR(40) NOT NULL)"
            );

            LedgerService service = context.getBean(LedgerService.class);
            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            service.printTx("external");

            try {
                service.insertThenFail("external");
            } catch (IllegalStateException ex) {
                System.out.println("external error=" + ex.getMessage());
            }

            System.out.println("rows after external=" +
                jdbc.queryForObject("SELECT COUNT(*) FROM tx_log", Integer.class));

            service.selfInvoke();

            System.out.println("rows after self=" +
                jdbc.queryForObject("SELECT COUNT(*) FROM tx_log", Integer.class));
        }
    }
}
```

**Cơ chế trong ví dụ:**

1. `@EnableTransactionManagement(proxyTargetClass = true)` chọn proxy theo class để không cần interface; thuộc tính này **không làm lời gọi `this` trở thành giao dịch**.
2. `JdbcTemplate` và `JdbcTransactionManager` dùng cùng `DataSource`; `transactionManager` là tên bean mặc định Spring nhận biết.
3. `@PostConstruct initialize()` được gọi trước khi proxy thông thường chặn được lời gọi, nên cả `initialize()` và `this.printTx(...)` thấy `false`.
4. Sau khi context hoàn tất, `getBean(LedgerService.class)` nhận proxy; `printTx("external")` và `insertThenFail("external")` được interceptor mở transaction nên thấy `true`.
5. Lỗi unchecked từ `insertThenFail("external")` đi ra interceptor, gây rollback. Đếm là 0.
6. `selfInvoke()` không transactional; nó gọi `this.insertThenFail("self")` trên target. Không có transaction và JDBC auto-commit, nên INSERT vẫn tồn tại dù exception được bắt. Đếm là 1.

### 4.4. Chạy và đối chiếu output

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.txinit.Main
```

Những dòng do chính chương trình in ra trong ví dụ (log Maven/driver nếu có không được liệt kê):

```text
init transaction=false
init self-call transaction=false
proxy=true
external transaction=true
external insert transaction=true
external error=planned failure
rows after external=0
self insert transaction=false
self error=planned failure
rows after self=1
```

Đây là thí nghiệm **cố ý gây ghi dữ liệu ngoài transaction** nhằm chứng minh nguy cơ. Không chuyển `selfInvoke()` vào nghiệp vụ thực tế. Với JPA, việc ghi không có transaction có thể thất bại hoặc có semantics khác so với JDBC auto-commit; không suy diễn kết quả H2/JDBC sang mọi provider.

## 5. Cách triển khai đúng khi cần khởi tạo dữ liệu có transaction

**Nguyên tắc:** chỉ định một bean làm điểm kích hoạt *sau startup* và một bean khác chứa method `@Transactional`. Spring inject tham chiếu proxy của bean service vào bean kích hoạt, nhờ vậy lời gọi từ bên ngoài được chặn đúng.

### 5.1. Spring Boot: `ApplicationRunner` hoặc `CommandLineRunner`

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class SeedService {
    @Transactional
    public void seed() {
        // Các bước JDBC/JPA cần commit/rollback cùng nhau.
    }
}

@Component
class SeedRunner implements ApplicationRunner {
    private final SeedService seedService;

    SeedRunner(SeedService seedService) {
        this.seedService = seedService;
    }

    @Override
    public void run(ApplicationArguments args) {
        seedService.seed();
    }
}
```

Đây là **hai class mẫu trong một ứng dụng Spring Boot**, không phải chương trình Java độc lập. Chúng cần Boot, datasource, transaction manager, logic nghiệp vụ thực và registration qua component scanning. `ApplicationRunner` chạy sau context refresh, trước khi `SpringApplication.run(...)` hoàn tất. `CommandLineRunner` tương tự nhưng nhận chuỗi tham số. Spring Boot khuyến nghị chạy startup tasks qua runner thay vì `@PostConstruct`.

Với startup job quan trọng, hãy quyết định nếu lỗi có nên khiến startup thất bại hay không, cách idempotency khi restart và giới hạn thời gian thực thi. Nếu task chạy trước readiness, service chưa nên nhận traffic phụ thuộc vào dữ liệu seed; đừng mặc định công việc được gọi “một lần mãi mãi”, vì deploy/restart sẽ chạy lại.

### 5.2. Spring Framework thuần: `ContextRefreshedEvent`

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class StartupService {
    @Transactional
    public void prepareDatabaseState() {
        // Logic cần transaction.
    }
}

@Component
class ContextReadyHandler {
    private final StartupService service;

    ContextReadyHandler(StartupService service) {
        this.service = service;
    }

    @EventListener(ContextRefreshedEvent.class)
    public void onRefresh() {
        service.prepareDatabaseState();
    }
}
```

Các class minh họa này cần context có component scanning và transaction management. `ContextRefreshedEvent` xảy ra sau giai đoạn tạo regular singleton, nên gọi qua proxy của `StartupService` là phương án rõ ràng.

Cần dự phòng event có thể xảy ra nhiều lần khi refresh context, hoặc trong hệ thống có parent/child contexts. Nếu cần đúng một lần theo DB, dùng unique constraint/migration table/lock hoặc kiểm tra idempotency, thay vì chỉ lưu biến cờ trong bean.

### 5.3. Khi nào dùng phương án khác?

- `SmartInitializingSingleton.afterSingletonsInstantiated()` chạy sau khi các **regular singleton** hoàn tất khởi tạo, hữu ích khi cần quan sát đủ các bean; nó không bảo đảm lazy bean đã được tạo và không nên gắn `@Transactional` trực tiếp lên callback để mong proxy chặn.
- `ApplicationReadyEvent` trong Boot phát **sau các runner**. Đây là lifecycle event muộn hơn, phù hợp với những công việc thực sự cần chờ ứng dụng sẵn sàng; tránh dùng làm điểm migration phải hoàn tất trước khi nhận request.
- Với schema migration và dữ liệu seed theo phiên bản, ưu tiên Flyway/Liquibase hoặc cơ chế migration tương đương thay vì viết nhiều DDL trong `@PostConstruct`.
- `TransactionTemplate` có thể mở transaction trực tiếp mà không cần proxy, nhưng lạm dụng nó ngay trong `@PostConstruct` vẫn gặp rủi ro bean creation lock, vòng phụ thuộc, thứ tự hạ tầng. Chỉ dùng khi đã kiểm soát rõ lifecycle và thật sự cần chương trình hóa transaction.

## 6. Các thay đổi thường bị hiểu nhầm là cách sửa

| Thay đổi | Vì sao chưa giải quyết vấn đề |
|---|---|
| Gắn `@Transactional` lên `@PostConstruct` | Callback vẫn chạy trước khi AOP proxy thông thường chặn method |
| Dùng `public` cho callback | Visibility có thể cần cho AOP, nhưng không đổi thời điểm callback |
| Bật `@EnableTransactionManagement(proxyTargetClass = true)` | Chỉ thay loại proxy, không sửa lifecycle timing hoặc self-invocation |
| Thêm `@DependsOn("transactionManager")` | Chỉ thay thứ tự tạo dependency; manager tồn tại không đồng nghĩa interceptor bao quanh callback |
| Bật `@Lazy` | Dời thời điểm tạo bean, nhưng `@PostConstruct` của nó vẫn chạy trong lifecycle target |
| Tiêm proxy của chính mình trở lại bean | Dễ phát sinh circular dependency và phụ thuộc init order; tách bean rõ ràng an toàn hơn |
| Dùng `this.save()` sau khi startup | Bypass proxy vẫn xảy ra dù bean đã hoàn chỉnh |
| Đánh dấu method `private`/`final` thành transactional | Proxy không intercept private method; class-based proxy không thể override final method |
| Chuyển sang `mode=ASPECTJ` ngay lập tức | Weaving có thể xử lý self-invocation nhưng cần cấu hình/dependency và semantics khác; không phải cách mặc định để chạy I/O trong initialization callback |

Đối với Spring Framework 6+, class-based proxies có thể hỗ trợ protected/package-visible transactional method theo cấu hình mặc định; JDK interface-based proxy cần public interface method. Dù vậy, ví dụ tốt nhất vẫn dùng public method trên service, gọi từ bean khác sau startup.

## 7. Debug, test, và nhận diện lỗi

**Xác nhận có proxy:** khi context đã sẵn sàng, kiểm tra `AopUtils.isAopProxy(bean)`. Kết quả `true` không chứng minh lời gọi nội bộ của chính bean đã đi qua advice.

**Xác nhận có actual transaction:** trong phần imperative JDBC của ví dụ, dùng `TransactionSynchronizationManager.isActualTransactionActive()` bên trong method. Đừng nhầm nó với `isSynchronizationActive()`: synchronization có thể active khi actual transaction không active. Cơ chế này dựa trên thread, không dùng để kết luận trực tiếp về transaction reactive có context riêng.

**Kiểm thử rollback thực:** dùng integration test ghi một bản ghi rồi ném `RuntimeException`; sau khi gọi, đọc DB lại bằng thao tác/transaction khác. So sánh lời gọi qua proxy với tự gọi `this.method()`. Khi test service trong transaction do test framework mở sẵn, `isActualTransactionActive() = true` có thể chỉ phản ánh transaction bên ngoài, vì vậy nên thiết kế test độc lập để kiểm tra method thật sự mở/tham gia transaction đúng như ý định.

**Kiểm tra cấu hình:** `@EnableTransactionManagement` hoặc `<tx:annotation-driven/>` đã bật chưa; transaction manager có quản lý cùng datasource mà repository sử dụng không; method có được gọi qua Spring-managed bean không; bean/method có final/private cản proxy không; exception có bị catch và nuốt bên trong method không.

**Logging:** tùy phiên bản có thể bật DEBUG/TRACE cho `org.springframework.transaction.interceptor` và transaction manager tương ứng để quan sát begin/commit/rollback. Không coi log là bằng chứng duy nhất; trạng thái database sau rollback là phép kiểm tra đáng tin hơn.

### Câu hỏi tự kiểm tra

1. `@Transactional` trên `@PostConstruct` có đủ để rollback những câu SQL trong callback không? **Không**, vì callback chạy trên raw target trong lúc initialization.
2. Vì sao `this.save()` trong cùng bean không mở transaction trong proxy mode? **Vì không đi qua proxy**.
3. `@DependsOn("transactionManager")` có xử lý được không? **Không**, nó chỉ quy định dependency order.
4. Vì sao bean `ApplicationRunner` gọi `seedService.seed()` hiệu quả hơn? **Vì runner chạy sau refresh và gọi qua proxy của một bean service khác**.
5. Cách kiểm chứng rõ nhất là gì? **Cho method ghi rồi ném lỗi, xác nhận actual transaction và kiểm tra dữ liệu sau rollback bằng thao tác DB độc lập**.

## Tài liệu chính thức

- Spring Framework — Using `@Transactional`, proxy và giới hạn `@PostConstruct`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Customizing the Nature of a Bean, lifecycle callbacks và bean initialization lock: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Using `@PostConstruct` and `@PreDestroy`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework — Understanding Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Boot — SpringApplication lifecycle, runner và readiness: https://docs.spring.io/spring-boot/reference/features/spring-application.html
