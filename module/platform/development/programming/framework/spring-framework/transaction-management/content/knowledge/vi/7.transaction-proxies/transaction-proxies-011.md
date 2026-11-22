# Thứ tự transaction advice với các advice khác trong Spring Framework

## 1. Bài toán: nhiều advice cùng bao quanh một phương thức

Một phương thức `@Transactional` có thể đồng thời chịu các advice về logging, profiling, retry, caching, validation, security hoặc các aspect tự viết. Khi nhiều advice **cùng áp dụng tại một join point** của Spring AOP, thứ tự của chúng quyết định:

- Advice nào chạy trước khi transaction bắt đầu, advice nào chạy trong transaction.
- Advice nào chạy sau khi transaction interceptor commit/rollback, và advice nào chỉ biết thân phương thức đã trả về.
- Retry có tạo transaction mới cho từng attempt hay lặp trong transaction đang mở.
- Exception đã được dịch/chặn hay còn được truyền đến transaction interceptor để áp rollback rule.
- Profiling đo cả chi phí commit/rollback hay chỉ đo phần nghiệp vụ.
- Caching hay thông báo có chạy trước khi dữ liệu được commit thành công hay không.

**Phạm vi:** cơ chế Spring AOP **proxy mode** và giao dịch imperative đồng bộ (JDBC/JPA). Giá trị `order` sắp xếp **advisor chain trên một lời gọi**, không quyết định thứ tự chạy SQL hay thứ tự commit giữa các request đồng thời.

Giả sử có ba lớp:

```text
Caller
  |
  v
Logging advice @Order(10)           [ngoài]
  |
  v
Transaction advisor order=20        [bắt đầu/tham gia transaction]
  |
  v
Metrics advice @Order(30)           [trong]
  |
  v
Target service method
```

Khi đi vào, thứ tự là `10 → 20 → 30 → target`. Trên đường thoát, thứ tự **đảo ngược**: `target → 30 → 20 → 10`. Advice order 10 bao cả transaction interceptor; advice order 30 nằm ở trong nó.

## 2. Quy tắc precedence và thứ tự ra/vào

Spring AOP tuân theo quy tắc precedence kiểu AspectJ:

1. **Order càng nhỏ thì precedence càng cao.** `@Order(10)` đứng trước `@Order(30)` trên đường vào.
2. **Precedence cao nhất chạy trước trên đường vào và cuối cùng trên đường ra.** Với `@Around`, đoạn trước `proceed()` chạy khi vào; đoạn sau `proceed()` chạy khi unwinding về caller.
3. `@Order` trên **class `@Aspect`** (hoặc aspect implement `Ordered`) xác định precedence giữa các aspects. Transaction advisor có order riêng, cấu hình ở transaction infrastructure.
4. Nếu hai advisor có precedence không được xác định rõ hoặc bằng nhau, không dựa vào thứ tự ngẫu nhiên đang thấy trong log. Một số framework còn áp quy tắc nội bộ riêng; hãy kiểm tra những advisor thực sự match lời gọi.
5. Nếu advice `@Around` **không gọi `proceed()`**, phần chain bên trong có thể không chạy. Nếu advice gọi `proceed()` nhiều lần, target và transaction interceptor phía trong cũng có thể được đi qua nhiều lần.

Ví dụ thứ tự rõ ràng:

| Layer | Precedence | Khi đi vào | Khi đi ra |
| --- | ---: | --- | --- |
| `OuterTrace` | 10 | Trước transaction interceptor | Sau transaction interceptor |
| Transaction advice | 20 | Mở hoặc tham gia transaction | Commit/rollback hoặc kết thúc scope của interceptor |
| `InnerTrace` | 30 | Sau khi interceptor bắt đầu xử lý | Trước khi interceptor hoàn tất |
| `target.transfer()` | Không phải advisor | Chạy cuối trên đường vào | Trả về hoặc ném exception đầu tiên |

**Quan trọng:** nếu method `REQUIRED` chỉ tham gia transaction đã mở ở caller, transaction interceptor của method con kết thúc **chưa phải commit vật lý cuối cùng**. Khi ấy advice ngoài method con cũng không thể tuyên bố commit ngoài đã hoàn tất.

## 3. Cấu hình order của transaction advisor

Với Spring annotation-driven transaction management, cách cấu hình chính là:

```java
@Configuration
@EnableTransactionManagement(order = 20)
class TransactionConfig {
    // Các bean DataSource, PlatformTransactionManager, service...
}
```

Đây là cấu hình minh họa chưa chạy độc lập. `order=20` là **precedence của transaction advice**, không phải thời gian chờ 20 ms, không phải ưu tiên của thread và không phải tên transaction manager.

**Mặc định** của `@EnableTransactionManagement` là `Ordered.LOWEST_PRECEDENCE` (giá trị order rất lớn, precedence thấp). Một aspect `@Order(100)` thường bao ngoài transaction advice mặc định; nhưng khi có nhiều framework advisor cũng dùng order thấp nhất, bạn không nên giả định một thứ tự ổn định trong mọi cấu hình.

Các nơi điều chỉnh:

| Thành phần | Nơi cấu hình |
| --- | --- |
| Transaction annotation advisor | `@EnableTransactionManagement(order = 20)` |
| Aspect dựa trên `@AspectJ` | `@Order(10)` trên class aspect hoặc implement `Ordered` |
| Programmatic advisor | `Ordered` hoặc API `setOrder(...)` của advisor tương ứng |
| XML transaction annotation | `<tx:annotation-driven order="20"/>` |
| XML `<aop:advisor>` | Thuộc tính `order` trên advisor |

Không dùng `@Order` trên **service class hoặc một method `@Transactional`** với ý định thay `@EnableTransactionManagement(order=...)`; hai mục đích khác nhau.

## 4. Ví dụ hoàn chỉnh: quan sát chính xác transaction ở giữa hai aspect

Ví dụ chạy bằng **Java 17+, Spring Framework 6.2.5, Spring AOP, H2 2.2.224 và Maven**. Mục tiêu là quan sát thứ tự và hiệu quả commit/rollback trên hai tài khoản giả. Không cần Spring Boot hay một Jakarta application server.

Cấu trúc file:

```text
tx-order-demo/
  pom.xml
  src/main/java/demo/App.java
  src/main/java/demo/LedgerService.java
  src/main/java/demo/OuterTrace.java
  src/main/java/demo/InnerTrace.java
```

### 4.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>tx-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp container, `spring-aop` cung cấp AOP proxy, `aspectjweaver` cần cho cơ chế parsing pointcut của `@AspectJ`, `spring-jdbc` cung cấp JdbcTemplate và kéo theo Spring transaction support. CSDL H2 `mem` được tạo mới mỗi lần chạy tiến trình.

### 4.2. `src/main/java/demo/App.java`

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

public class App {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)");
            jdbc.update(
                "INSERT INTO account (id, balance) VALUES (1, 100), (2, 100)");

            LedgerService service = context.getBean(LedgerService.class);

            service.transfer(10, false);
            printBalances("after_success", jdbc);

            try {
                service.transfer(20, true);
            } catch (IllegalStateException ex) {
                System.out.println("caller.caught=" + ex.getMessage());
            }
            printBalances("after_failure", jdbc);
        }
    }

    private static void printBalances(String prefix, JdbcTemplate jdbc) {
        int a = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = 1", Integer.class);
        int b = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = 2", Integer.class);
        System.out.printf("%s A=%d B=%d%n", prefix, a, b);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    @EnableTransactionManagement(order = 20)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            var ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_advice_order;DB_CLOSE_DELAY=-1");
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
        public LedgerService ledgerService(JdbcTemplate jdbc) {
            return new LedgerService(jdbc);
        }

        @Bean
        public OuterTrace outerTrace() {
            return new OuterTrace();
        }

        @Bean
        public InnerTrace innerTrace() {
            return new InnerTrace();
        }
    }
}
```

Hai cấu hình cần được hiểu khác nhau: `@EnableAspectJAutoProxy` bật xử lý các class `@Aspect`; `@EnableTransactionManagement` bật transaction advisor. `proxyTargetClass = true` giúp service proxy theo lớp, có thể lấy bằng `context.getBean(LedgerService.class)`. Trong demo không có transaction đã mở sẵn ở caller.

### 4.3. `src/main/java/demo/LedgerService.java`

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class LedgerService {
    private final JdbcTemplate jdbc;

    public LedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int amount, boolean failAfterDebit) {
        System.out.println("target.tx=" +
                TransactionSynchronizationManager.isActualTransactionActive());

        jdbc.update(
            "UPDATE account SET balance = balance - ? WHERE id = 1", amount);

        if (failAfterDebit) {
            throw new IllegalStateException("simulated");
        }

        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = 2", amount);
    }
}
```

Lần gọi thứ nhất chuyển 10 từ tài khoản A sang B và commit thành công. Lần thứ hai ném `IllegalStateException` **sau câu trừ 20**, nên transaction interceptor rollback theo mặc định (runtime exception). Hai lệnh JDBC thuộc cùng transaction vì `JdbcTemplate` và transaction manager sử dụng cùng `DataSource`.

### 4.4. `src/main/java/demo/OuterTrace.java`

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Aspect
@Order(10)
public class OuterTrace {
    @Around("execution(* demo.LedgerService.transfer(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        System.out.println("outer.enter tx=" + active());
        try {
            Object result = point.proceed();
            System.out.println("outer.exit tx=" + active());
            return result;
        } catch (Throwable ex) {
            System.out.println("outer.error tx=" + active());
            throw ex;
        }
    }

    private boolean active() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }
}
```

`OuterTrace` có order **10**, nhỏ hơn **20** của transaction advisor. Khi đi vào, nó log trước khi transaction mới bắt đầu. Khi `point.proceed()` trả về, transaction interceptor bên trong đã xử lý commit hoặc ném exception sau rollback.

### 4.5. `src/main/java/demo/InnerTrace.java`

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Aspect
@Order(30)
public class InnerTrace {
    @Around("execution(* demo.LedgerService.transfer(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        System.out.println("inner.enter tx=" + active());
        try {
            Object result = point.proceed();
            System.out.println("inner.exit tx=" + active());
            return result;
        } catch (Throwable ex) {
            System.out.println("inner.error tx=" + active());
            throw ex;
        }
    }

    private boolean active() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }
}
```

`InnerTrace` có order **30**, lớn hơn **20**. Vì vậy `inner.enter` chạy sau khi transaction interceptor mở transaction và `inner.exit`/`inner.error` chạy trước khi interceptor commit/rollback.

### 4.6. Lệnh chạy và kết quả mong đợi

Ở thư mục `tx-order-demo`, thực hiện:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.App
```

Các dòng chính được in bởi chương trình (bỏ qua log Maven/Spring):

```text
outer.enter tx=false
inner.enter tx=true
target.tx=true
inner.exit tx=true
outer.exit tx=false
after_success A=90 B=110
outer.enter tx=false
inner.enter tx=true
target.tx=true
inner.error tx=true
outer.error tx=false
caller.caught=simulated
after_failure A=90 B=110
```

Giải thích từng giai đoạn:

1. `outer.enter tx=false` chạy **trước** transaction interceptor; trong demo chưa có transaction ngoài.
2. Interceptor mở transaction; `inner.enter tx=true` và `target.tx=true` chạy trong transaction.
3. **Thành công:** target trả về; `inner.exit tx=true` in khi transaction vẫn mở; interceptor commit, giải phóng thread-bound transaction; cuối cùng `outer.exit tx=false` in.
4. **Thất bại:** target ném exception; `inner.error tx=true` in trước rollback; transaction interceptor rollback rồi cleanup; `outer.error tx=false` in sau đó, caller nhận exception.
5. Sau lần thất bại, A vẫn 90 và B vẫn 110; câu trừ 20 đã được rollback.

`TransactionSynchronizationManager.isActualTransactionActive()` chỉ báo transaction đang hoạt động trên thread, **không tự chứng minh commit thành công**. Trong trường hợp có outer transaction, advice ở phía ngoài transaction interceptor của service con có thể thấy `tx=true` vì transaction ngoài vẫn đang hoạt động.

## 5. Tại sao thứ tự ra ngược với thứ tự vào?

Các `@Around` được bao lồng như các khối `try/finally`:

```text
OuterTrace(10):
  before
  TransactionInterceptor(20):
    begin or join transaction
    InnerTrace(30):
      before
      target.transfer()
      after / error
    commit / rollback as appropriate
  after / error
```

Đây là **pseudocode để hình dung thứ tự**, không phải source code nội bộ Spring: engine thật có cơ chế rollback-only, synchronization callbacks, `beforeCommit`, `afterCommit`, cleanup và logic riêng khi tham gia transaction ngoài.

Có thể nhớ bằng sơ đồ:

```text
Caller
  -> Outer(10) BEFORE
    -> TX(20) OPEN/JOIN
      -> Inner(30) BEFORE
        -> Target
      <- Inner(30) AFTER
    <- TX(20) COMPLETE
  <- Outer(10) AFTER
Caller
```

Nếu `OuterTrace` dùng `@Around` mà **trả kết quả ngay, không gọi `proceed()`**, transaction advisor không chạy cho lời gọi đó. Đây là hành vi có chủ ý của một số cache advice; nếu viết aspect thủ công, phải hiểu hệ quả.

Nếu một advice retry ngoài transaction gọi `proceed()` nhiều lần, mỗi lần có thể đi qua transaction advisor và tạo transaction độc lập. Nếu retry advice ở trong transaction, nhiều attempt có thể cùng nằm trong transaction đã bị đánh dấu rollback-only. Nên chọn thứ tự theo hành vi mong muốn, không theo con số đẹp.

## 6. `@Before`, `@AfterReturning`, `@AfterThrowing` và `@After`

Các loại advice này cũng chịu precedence theo advisor chain:

| Advice | Ở **ngoài** transaction advice | Ở **trong** transaction advice |
| --- | --- | --- |
| `@Before` | Chạy trước khi interceptor bắt đầu transaction của lời gọi | Chạy sau khi transaction của lời gọi đã bắt đầu |
| `@AfterReturning` | Chỉ chạy khi phần bao trong trả về bình thường; với transaction do interceptor sở hữu, thường đã commit thành công | Có thể chạy khi target trả về nhưng **chưa commit** |
| `@AfterThrowing` | Có thể nhìn thấy exception phát sinh từ flush/commit bên trong transaction interceptor | Không nhìn thấy exception commit phát sinh sau khi advice bên trong đã hoàn tất |
| `@After` | Chạy ở giai đoạn finally sau scope transaction phía trong | Chạy trước transaction interceptor hoàn tất scope |
| `@Around` | Có thể bao trùm commit/rollback nếu gọi `proceed()` | Bao quanh target, nhưng phần commit phía ngoài vẫn chưa chạy |

**Tình huống hay sai:** `@AfterReturning` bên trong transaction ghi `"SUCCESSFULLY_COMMITTED"`. Lúc đó target có thể trả về bình thường, nhưng flush/commit vẫn có thể thất bại. Một log có tên chính xác hơn là `"METHOD_RETURNED"`. Nếu muốn ghi nhận **commit đã thành công**, dùng hook commit của Spring (`TransactionSynchronization.afterCommit()`) hoặc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` khi phù hợp.

Ngay cả khi `@AfterReturning` ở ngoài transaction interceptor, nếu interceptor chỉ **tham gia** transaction của caller thì outer commit vẫn còn ở tương lai. Hãy phân biệt ranh giới interceptor và commit vật lý cuối.

Spring còn có thứ tự advice types trong **cùng một `@Aspect`**, nhưng `@After` mang semantics kiểu `finally`. Đừng dựa vào thứ tự khai báo của hai phương thức cùng loại `@Before` hoặc `@Around` trong một aspect để ép thứ tự; khi cần kiểm soát, gom logic hoặc tách aspect với order riêng.

## 7. Thiết kế order theo mục tiêu nghiệp vụ

### 7.1. Logging và profiling

Nếu muốn đo **toàn bộ lời gọi transaction** gồm cả commit/rollback đồng bộ, đặt profiling advice **ngoài** transaction advice (order nhỏ hơn). Tài liệu chính thức Spring có ví dụ profiler chạy trước transaction, sau đó hoàn tất đo khi commit xong.

Nếu muốn đo riêng logic xử lý nghiệp vụ bên trong transaction, đặt profiling advice **trong** transaction; kết quả thường **không bao gồm chi phí commit**.

| Mục tiêu quan sát | Vị trí phù hợp | Giới hạn cần nhớ |
| --- | --- | --- |
| Thời gian method invocation có cả transaction | Advice ngoài | Nếu đã có transaction ngoài thì không bao trọn commit cuối cùng. |
| Thời gian chạy logic nghiệp vụ | Advice trong | Không tính flush/commit sau lúc target trả về. |
| Thông báo chỉ khi commit thành công | `afterCommit`/transaction-bound event | Không coi log trong target là bằng chứng commit. |
| Trace ID/MDC xuyên suốt lời gọi | Thường nằm ở lớp ngoài | Luôn cleanup context trong `finally`. |

### 7.2. Retry

Với lỗi tạm thời, một cách thiết kế hay dùng là **retry advice ngoài transaction advice**, để mỗi attempt bắt đầu transaction mới:

```text
Retry outer:
  attempt #1: TX begin -> target throws -> rollback
  attempt #2: TX begin -> target succeeds -> commit
```

Nếu transaction advice ở ngoài retry advice, nhiều attempt có thể nằm chung trong transaction vật lý, kể cả khi đã `rollback-only`. Với Spring Retry hoặc retry aspect tự viết, cần kiểm tra **order thực tế của advisor**, propagation, transaction ngoài và khả năng retry gây thao tác trùng.

**Đặc biệt:** lỗi kết nối ngay lúc commit có thể khiến phía client không xác định được commit đã thành công hay chưa; không retry ghi thanh toán/đơn hàng một cách mù quáng. Dùng idempotency key hoặc cơ chế kiểm tra trạng thái khi cần.

### 7.3. Caching

Nếu `@Cacheable` nằm **ngoài** transaction advice và cache hit, advice cache có thể trả kết quả mà không chạy service target hay transaction interceptor. Ngược lại, đặt cache trong transaction có thể khiến transaction bắt đầu dù chỉ trả từ cache.

`@CachePut`/`@CacheEvict` kết hợp `@Transactional` cần kiểm tra thứ tự; cập nhật hoặc xóa cache **trước khi DB commit** có thể khiến cache sai nếu transaction rollback. Khi tính nhất quán quan trọng, dùng cơ chế cache transaction-aware hoặc invalidation sau commit và integration test rollback.

### 7.4. Security, validation và exception translation

Method security có thể có nhiều advisor riêng (`@PreAuthorize`, `@PostAuthorize` và các interceptors khác), với thứ tự phụ thuộc cấu hình của Spring Security. Validation có thể diễn ra trước hoặc trong transaction. Quyết định nên dựa vào nhu cầu cần DB transaction để đọc dữ liệu, giới hạn tài nguyên và việc exception cần rollback.

Exception translation cũng chịu ảnh hưởng thứ tự: nếu exception được chuyển **trước khi** đến transaction interceptor, rollback rules có thể xét exception đã dịch; nếu translation ở ngoài, transaction interceptor xét exception từ phía dưới. Với default runtime-exception rollback nhiều trường hợp như nhau, nhưng `rollbackFor`/`noRollbackFor` tùy biến có thể cho kết quả khác. Viết test cho các loại exception quan trọng.

### 7.5. `@Async` và reactive

`@Async` chuyển thực thi sang thread khác; transaction imperative thường gắn với thread. Thay order không tự chuyển transaction context sang thread mới. Nếu tác vụ bất đồng bộ phải dùng transaction, thiết kế boundary transaction ở service được gọi trên thread thực thi và kiểm tra proxy đúng.

Reactive transaction dùng `ReactiveTransactionManager` cùng Reactor context, không suy luận bằng `TransactionSynchronizationManager.isActualTransactionActive()` kiểu thread-bound của demo JDBC.

## 8. Điều gì thay đổi khi đổi order?

Trong demo:

```text
OuterTrace(10) -> Transaction(20) -> InnerTrace(30) -> Target
```

Nếu chỉ đổi `@EnableTransactionManagement(order = 40)`, ta có:

```text
OuterTrace(10) -> InnerTrace(30) -> Transaction(40) -> Target
```

Ở một lời gọi mới chưa có transaction ngoài, `inner.enter` lúc này cũng có thể in `tx=false`, và `inner.exit` chạy sau khi transaction interceptor hoàn tất. Nếu đổi order transaction thành `5`:

```text
Transaction(5) -> OuterTrace(10) -> InnerTrace(30) -> Target
```

Khi đó cả `outer.enter` và `inner.enter` nằm bên trong transaction của target nên dự kiến đều thấy `tx=true`; cả hai log exit chạy **trước commit**.

Đây là **dự đoán dựa trên quy tắc precedence**, không phải stdout đã chạy của hai cấu hình khác. Bạn có thể sửa một giá trị, chạy lại chương trình demo, rồi so sánh kết quả để tự kiểm chứng.

Không có order tối ưu cho mọi ứng dụng. Hãy xác định rõ "advice cần bao toàn bộ transaction" hay "advice chỉ xử lý trong transaction", rồi đặt precedence và bảo vệ bằng test.

## 9. Quan sát advisor chain trong ứng dụng thật

Khi log không khớp dự đoán, hãy kiểm tra:

1. **Có proxy hay không?** Object tạo bằng `new` không qua Spring; self-invocation `this.method()` không kích hoạt transaction advice riêng của phương thức con trong proxy mode.
2. **Pointcut có match cùng join point?** Hai advice áp dụng cho hai phương thức khác nhau sẽ không có chain chung để xếp thứ tự.
3. **Transaction mới hay transaction tham gia?** `Propagation.REQUIRED` có thể chỉ dùng lại transaction ngoài.
4. **Có nhiều proxies hoặc nhiều framework advisors không?** Thứ tự giữa các infrastructure advisors cần xét trên chain thực tế.
5. **Method có thể được proxy không?** JDK proxy thường chặn interface methods, class-based proxy có giới hạn với `final`/`private`; thiết kế phương thức public rõ ràng.
6. **Có commit failure, rollback-only hoặc callback nào không?** Log target trả về không chứng minh DB commit.

Có thể dùng API AOP để kiểm tra bean đang được proxy và liệt kê advisor:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean(LedgerService.class);
System.out.println("isProxy=" + AopUtils.isAopProxy(bean));

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getSimpleName()
                + " -> " + advisor.getAdvice().getClass().getSimpleName());
    }
}
```

Đây là **đoạn minh họa tùy chọn**; có thể đặt trong `App.main` để tìm hiểu, nhưng **không nằm trong stdout cố định của demo**. Tên class advisor có thể phụ thuộc phiên bản Spring. Dùng integration test để xác nhận thứ tự nghiệp vụ thực tế, không dựa hoàn toàn vào tên advisor.

Có thể tăng mức log của `org.springframework.transaction` trong môi trường thử nghiệm để quan sát bắt đầu/hoàn tất transaction. Với event "đã commit", nên dùng transaction synchronization phù hợp; với request có outer transaction, phải theo dõi tới **ranh giới ngoài cùng**.

## 10. Lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Hiểu "order lớn chạy trước" | Đảo ngược chain và suy đoán sai commit | Order nhỏ có precedence cao; trước khi vào, cuối khi ra. |
| Coi `@Order` trên service là order transaction | Transaction advice không được cấu hình như kỳ vọng | Dùng `@EnableTransactionManagement(order=...)`. |
| Có nhiều advisor cùng precedence mà mặc định thứ tự | Behavior có thể phụ thuộc cấu hình/phiên bản | Đặt order rõ và test. |
| Gọi `@AfterReturning` trong transaction là "committed" | Commit có thể thất bại sau đó | Dùng `afterCommit` hoặc tên log chính xác. |
| Retry bên trong transaction đang rollback-only | Retry tiếp nhưng commit cuối thất bại | Thiết kế attempt có transaction mới nếu phù hợp. |
| `@Around` quên `proceed()` | Target và interceptor bên trong không chạy | Chỉ shortcut khi có chủ ý, test các nhánh. |
| `this.inner()` và kỳ vọng advice trên inner chạy | Self-invocation không qua proxy | Tách boundary sang Spring bean khác. |
| Cache update trước DB commit | Dữ liệu cache và DB lệch sau rollback | Invalidate sau commit hoặc cache transaction-aware. |
| Thấy `tx=true` rồi suy ra commit thành công | Có thể chỉ là transaction đang mở | Kiểm tra sau transaction ngoài và DB state. |
| Mong `@Async` kế thừa transaction | Công việc chạy thread khác thiếu boundary | Tạo transaction trên thread thực thi. |
| Tưởng order transaction quyết định thứ tự SQL | Suy đoán sai concurrency và locking | Phân biệt AOP precedence với DB isolation và lock. |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `AuditAspect @Order(5)`, transaction advisor order 50, `MetricAspect @Order(100)`. Mô tả thứ tự đi vào và đi ra.

**Đáp án:** Vào: audit 5 -> transaction 50 -> metric 100 -> target. Ra: target -> metric 100 -> transaction 50 -> audit 5. Với transaction mới do interceptor sở hữu, audit kết thúc sau khi interceptor hoàn tất.

**Câu 2.** Vì sao `@AfterReturning` trong transaction có thể chạy dù commit cuối cùng thất bại?

**Đáp án:** Advice trong nhìn thấy **target trả về bình thường**, sau đó transaction interceptor mới thực hiện flush/commit và có thể ném exception. `@AfterReturning` ngoài sẽ không chạy nếu phía transaction interceptor ném lỗi commit.

**Câu 3.** Đặt retry advisor order 10, transaction advice order 20. Mỗi attempt chắc chắn có transaction riêng?

**Đáp án:** Điều đó đúng khi retry gọi `proceed()` xuyên qua interceptor và interceptor **tạo transaction mới cho mỗi attempt**, không bị bao bởi transaction ngoài. Nếu transaction ngoài tồn tại hoặc propagation khác, cần xét lại.

**Câu 4.** `ServiceA` đã có `@Transactional` và gọi `ServiceB` `@Transactional(REQUIRED)`. Advice ngoài interceptor của B chạy sau commit transaction A không?

**Đáp án:** Không. B thường tham gia cùng transaction A; A quyết định commit vật lý cuối cùng khi scope A hoàn tất.

**Câu 5.** Nếu thay order transaction từ 20 xuống 5 trong demo, `outer.enter` và `inner.enter` nằm ở đâu?

**Đáp án:** Cả hai nằm trong transaction của target đối với lời gọi không có transaction ngoài. Dự kiến cùng in `tx=true`; commit sẽ xảy ra sau khi cả hai kết thúc.

**Câu 6.** Order 10 trên một aspect xử lý `checkout()` có làm service `sendEmail()` chạy trước service `reserveStock()` ở các thread khác nhau không?

**Đáp án:** Không. Advisor order chỉ quyết định precedence trong AOP chain của join point mà aspect match; nó không phải scheduler toàn cục cho mọi tác vụ hay thread.

## Ghi nhớ

- **Số order nhỏ hơn = precedence cao hơn = chạy trước khi vào và sau cùng khi ra.**
- `@EnableTransactionManagement(order=...)` điều khiển **transaction advisor**; mặc định là `Ordered.LOWEST_PRECEDENCE`.
- `@Order` trên aspect điều khiển aspect advice; vị trí bên trong/bên ngoài transaction quyết định thấy transaction đang mở hay đã hoàn tất.
- Với transaction **tham gia transaction ngoài**, kết thúc interceptor con không đồng nghĩa commit cuối.
- Logging/profiling, retry, cache và exception translation cần được đặt theo mốc giao dịch thực sự. Để làm việc **sau commit thành công**, cân nhắc after-commit callback/event phù hợp.
- Hãy xác minh bằng trace trên proxy, rollback test, dữ liệu DB và kiểm tra các nhánh thành công/lỗi.

## Tài liệu chính thức

1. Spring Framework — [Advising Transactional Operations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/applying-more-than-just-tx-advice.html): ví dụ profiling bao transaction.
2. Spring Framework — [Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): quy tắc precedence trên đường vào/ra.
3. Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): `order` mặc định và proxy mode.
4. Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation và giới hạn proxy.
5. Spring Framework — [Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptor.
6. Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): xử lý sau commit.
