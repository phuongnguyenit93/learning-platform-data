# Tham gia, tạm ngưng và khôi phục giao dịch hiện có trong Spring Transaction Management

## Mục tiêu học tập

Khi một phương thức service có `@Transactional` gọi một service khác cũng có `@Transactional`, Spring cần quyết định: **tham gia giao dịch hiện có**, **tạm ngưng giao dịch đó để chạy một giao dịch độc lập**, hay **tạm ngưng để chạy không có giao dịch**. Sau lời gọi bên trong, Spring còn phải khôi phục chính xác ngữ cảnh giao dịch bên ngoài, kể cả khi lời gọi bên trong ném exception.

Sau bài học, bạn có thể:

1. Phân biệt **logical transaction scope** (phạm vi transaction do mỗi interceptor tạo) với **physical transaction** (giao dịch thực trên connection/resource).
2. Dùng `REQUIRED`, `SUPPORTS`, `MANDATORY` để tham gia giao dịch phù hợp; hiểu khi nào phương thức không tạo giao dịch.
3. Giải thích `REQUIRES_NEW` và `NOT_SUPPORTED` tạm ngưng transaction hiện tại như thế nào, và transaction cũ được **resume** sau đó ra sao.
4. Phân biệt `NESTED` sử dụng savepoint với `REQUIRES_NEW` tạo physical transaction độc lập.
5. Dự đoán rollback, `UnexpectedRollbackException`, thời điểm commit, việc giữ connection/lock và hệ quả với connection pool.
6. Chạy thử một chương trình Java 17 + Spring JDBC/H2 xác minh từng trường hợp thay vì chỉ đoán từ annotation.

**Phạm vi:** cơ chế quản lý transaction đồng bộ (imperative) trên Spring AOP proxy với `PlatformTransactionManager` và một `DataSource` JDBC. Phần cuối chỉ ra khác biệt khi dùng reactive transaction hoặc nhiều nguồn dữ liệu.

## 1. Transaction hiện có là gì?

Một transaction có thể được mở ở tầng service bên ngoài, ví dụ:

```java
@Transactional
public void placeOrder() {
    inventoryService.reserve();
    paymentService.recordPayment();
}
```

Các lệnh trên chỉ là **minh họa**, chưa phải chương trình độc lập; mỗi service phải là Spring-managed bean và được gọi thông qua proxy phù hợp. Nếu cả `reserve()` và `recordPayment()` có `@Transactional(propagation = REQUIRED)`, trong trường hợp phổ biến chúng cùng **tham gia** transaction do `placeOrder()` bắt đầu. Nếu một bước cần rollback toàn bộ, tất cả thay đổi DB của transaction vật lý chung sẽ bị rollback.

Trong mô hình JDBC thông thường, Spring gắn `ConnectionHolder` và thông tin transaction vào thread đang xử lý thông qua `TransactionSynchronizationManager`. `JdbcTemplate` và các cơ chế truy cập dữ liệu tương thích Spring sẽ lấy đúng connection đang được ràng buộc, thay vì mở một transaction độc lập cho mỗi câu lệnh.

**Hai khái niệm cần giữ riêng:**

- **Logical transaction scope:** mỗi lời gọi có transaction interceptor có thể có phạm vi, thuộc tính propagation và ý định rollback riêng. Với `REQUIRED`, phương thức bên trong có logical scope mới dù không tạo physical transaction mới.
- **Physical transaction:** giao dịch thật trên database connection (hoặc resource transaction tương ứng), nơi commit/rollback tác động đến dữ liệu. Nhiều logical scope `REQUIRED` có thể cùng dùng một physical transaction.

Ví dụ với `REQUIRED`:

```text
outerService.outer()     [logical scope A] ──────────┐
    innerService.inner() [logical scope B] ───┐       │
                                              │       │
             Cùng một physical transaction ───┴───────┘
                              │
                        commit/rollback
```

Vì cùng physical transaction, **inner không thể commit phần của mình một cách độc lập**. Nếu inner đánh dấu rollback-only, outer không thể biến giao dịch chung thành commit thành công chỉ bằng cách bắt exception rồi bỏ qua.

## 2. Bảy kiểu propagation trong một bảng

Thuộc tính `propagation` của `@Transactional` hoặc XML `tx:method` quyết định quan hệ giữa transaction của method và transaction đang có ở thời điểm lời gọi.

| Propagation | Khi đã có transaction | Khi chưa có transaction |
|---|---|---|
| `REQUIRED` (mặc định) | **Tham gia** physical transaction hiện có | Tạo transaction mới |
| `SUPPORTS` | Tham gia nếu có | Chạy không có actual transaction |
| `MANDATORY` | Bắt buộc tham gia | Ném `IllegalTransactionStateException` |
| `REQUIRES_NEW` | **Tạm ngưng** transaction ngoài, tạo physical transaction độc lập; sau đó **khôi phục** transaction ngoài | Tạo physical transaction mới |
| `NOT_SUPPORTED` | **Tạm ngưng** transaction ngoài, thực hiện đoạn bên trong không có actual transaction; sau đó **khôi phục** transaction ngoài | Chạy không có actual transaction |
| `NEVER` | Ném `IllegalTransactionStateException` | Chạy không có actual transaction |
| `NESTED` | Nếu hỗ trợ, tạo savepoint trong cùng physical transaction | Thường tạo mới như `REQUIRED` |

Đặc biệt, **`NESTED` không đồng nghĩa với `REQUIRES_NEW`**. Nó thường tạo savepoint trên cùng JDBC connection; rollback bên trong có thể về savepoint, còn commit vật lý vẫn do phạm vi ngoài quyết định. Tính khả dụng phụ thuộc transaction manager/driver, phổ biến với JDBC, không thể mặc định áp dụng cho mọi JPA, JTA hay reactive manager.

**Từ khóa:** “tham gia” là chia sẻ transaction; “tạm ngưng” là giữ transaction ngoài ở trạng thái mở nhưng tách khỏi ngữ cảnh hiện tại; “khôi phục” là đưa resource/synchronization và metadata của transaction ngoài trở lại để outer tiếp tục.

## 3. Tham gia giao dịch hiện có với `REQUIRED`, `SUPPORTS`, `MANDATORY`

### 3.1. `REQUIRED`: tham gia nếu có, tạo mới nếu không

```java
@Service
class OrderService {
    private final StockService stock;

    OrderService(StockService stock) { this.stock = stock; }

    @Transactional
    public void placeOrder() {
        // Ghi order vào database.
        stock.reserve();
        // Ghi thêm dữ liệu liên quan.
    }
}

@Service
class StockService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void reserve() {
        // Dùng cùng physical transaction với placeOrder(), nếu có.
    }
}
```

Ví dụ trên là **hai class minh họa**: cần import Spring, cấu hình transaction manager và thao tác database thật. Giả sử lời gọi từ `OrderService` tới `StockService` đi qua proxy và hai bean dùng cùng transaction manager/resource:

- Nếu không có transaction trước `placeOrder()`, outer mở một physical transaction; inner tạo logical scope `REQUIRED` tham gia physical transaction đó.
- `reserve()` kết thúc bình thường **không phải thời điểm commit vật lý**; outer hoàn thành thành công mới commit toàn bộ.
- Nếu inner ném unchecked exception ra khỏi interceptor, inner có thể làm giao dịch chung bị đánh dấu rollback-only. Outer bắt exception rồi trả về bình thường vẫn có thể nhận `UnexpectedRollbackException` ở thời điểm commit vì Spring không thể âm thầm báo “đã commit” khi transaction thực tế đã rollback.

**Thuộc tính khi tham gia:** `isolation`, `timeout` và `readOnly` do inner khai báo thường không thay đổi tính chất của physical transaction đã tồn tại. Với `AbstractPlatformTransactionManager`, có thể cấu hình `validateExistingTransaction=true` để từ chối một số khai báo isolation/read-only không tương thích; không giả định quy tắc inner tự ghi đè outer.

### 3.2. `SUPPORTS`: có thì tham gia, không có thì không tự tạo

```java
@Transactional(propagation = Propagation.SUPPORTS)
public AccountDetails loadDetails(long id) {
    // Nếu caller có transaction tương thích: tham gia.
    // Nếu không: không tạo actual transaction chỉ vì SUPPORTS.
    return repository.findById(id).orElseThrow();
}
```

Đoạn trên là snippet trong service có `repository` phù hợp, không phải file Java độc lập. `SUPPORTS` thường được dùng cho truy vấn có thể chạy trong/ngoài một transaction đã có. Nó có thể tạo transaction **synchronization scope** ngay cả khi actual transaction không tồn tại, tùy transaction manager; vì vậy `TransactionSynchronizationManager.isSynchronizationActive()` và `isActualTransactionActive()` **không phải cùng một phép kiểm tra**.

Không dùng `SUPPORTS` khi nghiệp vụ bắt buộc một physical transaction cho nhiều thao tác ghi. Khi gọi ngoài transaction, mọi thay đổi có thể dùng cơ chế commit riêng tùy API/driver.

### 3.3. `MANDATORY`: luôn phải có transaction của caller

```java
@Transactional(propagation = Propagation.MANDATORY)
public void recordInExistingTransaction() {
    // Chỉ hợp lệ nếu có transaction đang hoạt động.
}
```

Nếu không có transaction khi interceptor xử lý lời gọi, Spring ném `IllegalTransactionStateException`. Đây là cách diễn đạt ràng buộc kiến trúc: một helper bắt buộc thuộc giao dịch của nghiệp vụ bên ngoài. Chú ý self-invocation có thể làm interceptor không chạy, khiến cả kiểm tra `MANDATORY` cũng bị bỏ qua.

## 4. `REQUIRES_NEW`: tạm ngưng outer, chạy transaction độc lập, rồi khôi phục

`Propagation.REQUIRES_NEW` yêu cầu một **physical transaction mới** ngay cả khi caller đã ở trong transaction. Với manager hỗ trợ suspension, Spring thực hiện khái quát:

```text
Outer @Transactional(REQUIRED)
  ├─ Mở transaction A; bound connection/resource A
  ├─ Ghi dữ liệu của A
  │
  ├─ Gọi inner @Transactional(REQUIRES_NEW) qua proxy
  │    ├─ Suspend transaction A:
  │    │    unbind resource/synchronization của A khỏi thread
  │    ├─ Mở transaction B với resource/connection B độc lập
  │    ├─ Chạy inner
  │    ├─ Commit hoặc rollback B
  │    └─ Resume transaction A:
  │         bind lại resource và synchronization của A
  │
  ├─ Outer tiếp tục trong transaction A
  └─ Commit hoặc rollback A
```

**Suspension không phải commit hoặc rollback transaction A.** A vẫn là một giao dịch đang mở, có thể giữ database lock và connection trong suốt thời gian B chạy. `REQUIRES_NEW` không “tách” phần code đã ghi trước đó ra khỏi A; chỉ khởi tạo transaction riêng cho code bên trong inner.

Hệ quả quan trọng:

- **Độc lập về commit/rollback:** B commit thành công vẫn tồn tại nếu A rollback về sau. Ngược lại, B rollback không nhất thiết buộc A rollback nếu outer xử lý exception và tiếp tục hợp lệ.
- **Connection riêng:** với JDBC `DataSourceTransactionManager`/`JdbcTransactionManager`, A thường giữ connection được bind trong khi B cần connection khác. Nếu mọi request/thread giữ connection A và đồng thời chờ B lấy connection nhưng pool không còn connection, ứng dụng có thể bị cạn pool hoặc deadlock. Hướng dẫn Spring khuyên sizing pool lớn hơn số thread đồng thời **ít nhất một connection** khi dùng `REQUIRES_NEW` trong trường hợp thông dụng; tính toán thực tế còn phụ thuộc số transaction lồng nhau và tải.
- **Độc lập thuộc tính:** B có thể đặt isolation/timeout/read-only riêng vì nó là physical transaction mới.
- **Khôi phục kể cả khi inner lỗi:** sau khi B kết thúc/rollback, Spring thường resume A trước khi exception truyền về outer. Nếu outer bắt lỗi và quyết định tiếp tục, các thao tác sau đó vẫn thuộc A.
- **Không phải giải pháp transaction phân tán:** hai datasource, message broker hoặc lời gọi HTTP không tự nằm chung một physical transaction.

### Ví dụ ứng dụng: ghi audit độc lập

```java
@Service
class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String event) {
        // INSERT audit trong transaction mới độc lập.
    }
}

@Service
class CheckoutService {
    private final AuditService audit;

    CheckoutService(AuditService audit) { this.audit = audit; }

    @Transactional
    public void checkout() {
        // Thao tác chính nằm trong transaction A.
        audit.recordAttempt("CHECKOUT_ATTEMPT"); // Transaction B.
        // Nếu sau đây ném RuntimeException thì A rollback,
        // bản ghi audit đã commit ở B vẫn có thể tồn tại.
    }
}
```

Đây là mã minh họa chưa độc lập; cần database, các import và implementation thật. Để bảo đảm audit “luôn lưu” trước mọi loại lỗi vẫn phải tính đến trường hợp bản thân B thất bại, DB không sẵn sàng hoặc outer đang giữ lock gây xung đột với B. Không gọi `this.recordAttempt()` từ chính `AuditService`: self-invocation có thể bỏ qua proxy và mất `REQUIRES_NEW`.

## 5. `NOT_SUPPORTED`: tạm ngưng outer và chạy không có actual transaction

`Propagation.NOT_SUPPORTED` cũng cần suspend transaction hiện hành (nếu có), nhưng khác với `REQUIRES_NEW` ở chỗ **không bắt đầu physical transaction B**.

```text
A: outer transaction mở ──┐                               ┌── A được resume ── commit/rollback
                          │                               │
                          └── suspend A ──> inner chạy ───┘
                                            không có actual transaction
```

Khi outer đang có transaction, Spring tạm tháo resource/synchronization phù hợp khỏi ngữ cảnh thread, rồi gọi inner ngoài actual transaction. Sau khi inner trả kết quả hoặc ném exception, Spring khôi phục ngữ cảnh outer để tiếp tục. `NOT_SUPPORTED` khác `NEVER`: `NEVER` **ném exception** nếu gặp outer transaction thay vì tự suspend nó.

**Hệ quả trên JDBC:** nếu inner sử dụng một connection khác với `autoCommit=true`, một lệnh INSERT/UPDATE đơn lẻ có thể được commit ngay trong khi outer đang suspend. Nếu outer rollback sau đó, lệnh đã commit trong inner **không bị undo bởi transaction outer**. Đây là hệ quả quan trọng, không nên sử dụng `NOT_SUPPORTED` để “né rollback” mà không có lý do nghiệp vụ rõ ràng.

Phù hợp hơn cho thao tác thực sự không cần một transaction database: đọc dữ liệu độc lập, tính toán hoặc tác vụ có thời gian kéo dài, nhưng cần cân nhắc rằng transaction A vẫn đang mở và tài nguyên A vẫn được giữ. Chạy xử lý chậm giữa transaction là nguy cơ giữ lock/connection quá lâu.

**Khi inner ném exception:** Spring cố gắng resume A trước khi truyền lỗi cho outer. Nếu exception tiếp tục thoát ra khỏi method outer có `@Transactional(REQUIRED)`, mặc định transaction A cũng rollback vì lỗi unchecked, dù lỗi phát sinh ở đoạn `NOT_SUPPORTED`. Nếu outer bắt lỗi, A có thể commit, nhưng các thay đổi non-transactional ở inner có thể đã commit từ trước.

## 6. `REQUIRES_NEW`, `NOT_SUPPORTED` và `NESTED` khác nhau ở đâu?

| Tiêu chí | `REQUIRES_NEW` | `NOT_SUPPORTED` | `NESTED` |
|---|---|---|---|
| Có outer transaction? | Suspend A | Suspend A | Giữ A, tạo savepoint nếu hỗ trợ |
| Inner có actual transaction? | Có: transaction B độc lập | Không | Có: cùng physical transaction A |
| Cần connection/resource khác? | Thường có với JDBC | Có thể dùng connection khác ngoài A | Thường cùng connection A |
| Inner commit có tồn tại nếu outer rollback? | Có, nếu B đã commit | Lệnh non-tx đã commit có thể tồn tại | Không; outer rollback hủy cả phần sau savepoint |
| Inner rollback ảnh hưởng outer? | Không tự động | Không có local transaction để rollback | Có thể rollback về savepoint và outer tiếp tục |
| Khi outer hoàn thành | A commit/rollback độc lập | A commit/rollback độc lập với side effect inner | Commit/rollback cả physical transaction A |
| Rủi ro chính | Cạn connection pool, lock conflict, partial business consistency | Side effect không được rollback, giữ outer mở | Driver/manager không hỗ trợ savepoint |

Ví dụ `NESTED`: outer tạo 2 bản ghi, inner insert thất bại rồi rollback về savepoint, outer vẫn có thể tiếp tục và commit phần hợp lệ. Đây **không phải** một transaction B đã commit độc lập, vì nếu outer rollback toàn bộ thì cả dữ liệu inner từng “thành công” cũng không tồn tại.

Các lựa chọn thường dùng: `REQUIRED` cho nghiệp vụ nguyên tử thống nhất; `REQUIRES_NEW` cho công việc cần commit riêng và chấp nhận hệ quả độc lập; `NOT_SUPPORTED` cho đoạn thực sự không cần transaction; `NESTED` cho savepoint có chủ đích và đã kiểm chứng hỗ trợ.

## 7. Ví dụ chạy được: quan sát join, suspend, resume và rollback-only

Bài demo dùng Java 17, Spring Framework 6.2.19, H2 và Spring JDBC. Một `OuterService` gọi `InnerService` là **bean khác**, nên lời gọi đi qua proxy. Program sẽ so sánh 5 kịch bản:

1. `REQUIRED` tham gia A, outer lỗi → mọi INSERT cùng rollback.
2. `REQUIRES_NEW` commit B, outer rollback A → dữ liệu B vẫn còn.
3. `NOT_SUPPORTED` chạy ngoài A, outer rollback → INSERT auto-commit của inner vẫn còn.
4. B `REQUIRES_NEW` lỗi và rollback, outer bắt exception → Spring resume A và outer commit.
5. Bên trong `REQUIRED` ném unchecked exception, outer bắt lỗi → transaction A bị đánh dấu rollback-only; lúc outer commit nhận `UnexpectedRollbackException`.

Đây là ví dụ **chạy trong Spring application context**; không sử dụng `@SpringBootApplication`, không yêu cầu web server.

### 7.1. Cấu trúc dự án

```text
spring-propagation-demo/
├── pom.xml
└── src/main/java/com/example/tx/Main.java
```

### 7.2. Tệp `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-propagation-demo</artifactId>
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

Dependency `spring-context` cung cấp application context/AOP; `spring-jdbc` cung cấp `JdbcTemplate` và `JdbcTransactionManager`; H2 là DB in-memory. Bản 6.2.19 đã được phát hành, nhưng dự án thật nên dùng BOM được hỗ trợ và chính sách cập nhật phù hợp.

### 7.3. Tệp `src/main/java/com/example/tx/Main.java`

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
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class Main {
    private static boolean active() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }

    // Chỉ gọi helper này từ phương thức đang được transaction interceptor chặn.
    private static boolean isNew() {
        return TransactionAspectSupport.currentTransactionStatus()
            .isNewTransaction();
    }

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:propagation_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        public OuterService outerService(
                JdbcTemplate jdbc, DataSource ds, InnerService inner) {
            return new OuterService(jdbc, ds, inner);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private void insert(String label) {
            jdbc.update("INSERT INTO tx_events(label) VALUES (?)", label);
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void requiredInsert() {
            System.out.println("inner REQUIRED active=" + active()
                + " new=" + isNew());
            insert("inner-required");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNewInsert() {
            System.out.println("inner REQUIRES_NEW active=" + active()
                + " new=" + isNew());
            insert("inner-new");
        }

        @Transactional(propagation = Propagation.NOT_SUPPORTED)
        public void outsideTransactionInsert() {
            System.out.println("inner NOT_SUPPORTED active=" + active());
            insert("outside-tx");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNewThenFail() {
            System.out.println("inner REQUIRES_NEW fails active=" + active());
            insert("inner-new-failed");
            throw new IllegalStateException("inner failed");
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void requiredThenFail() {
            System.out.println("inner REQUIRED fails active=" + active()
                + " new=" + isNew());
            insert("inner-required-failed");
            throw new IllegalStateException("inner failed");
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;
        private final InnerService inner;

        public OuterService(
                JdbcTemplate jdbc, DataSource dataSource, InnerService inner) {
            this.jdbc = jdbc;
            this.dataSource = dataSource;
            this.inner = inner;
        }

        private void insert(String label) {
            jdbc.update("INSERT INTO tx_events(label) VALUES (?)", label);
        }

        // TransactionSynchronizationManager bind resource của outer theo ds.
        private Object boundResource() {
            return TransactionSynchronizationManager.getResource(dataSource);
        }

        @Transactional
        public void requiredThenOuterFail() {
            System.out.println("outer REQUIRED active=" + active());
            insert("outer-required");
            inner.requiredInsert();
            throw new IllegalStateException("outer failed");
        }

        @Transactional
        public void requiresNewThenOuterFail() {
            Object outerResource = boundResource();
            // Tránh ghi vào cùng bảng ở outer trước khi inner ghi,
            // để demo không phụ thuộc vào tranh chấp khóa của DB.
            inner.requiresNewInsert();
            System.out.println("outer restored="
                + (outerResource == boundResource()) + " active=" + active());
            insert("outer-rolled-back");
            throw new IllegalStateException("outer failed");
        }

        @Transactional
        public void notSupportedThenOuterFail() {
            Object outerResource = boundResource();
            inner.outsideTransactionInsert();
            System.out.println("outer restored="
                + (outerResource == boundResource()) + " active=" + active());
            insert("outer-rolled-back");
            throw new IllegalStateException("outer failed");
        }

        @Transactional
        public void resumeAfterInnerFailure() {
            Object outerResource = boundResource();
            insert("outer-start");
            try {
                inner.requiresNewThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("outer catches inner error");
            }
            System.out.println("outer restored="
                + (outerResource == boundResource()) + " active=" + active());
            insert("outer-end");
        }

        @Transactional
        public void catchRequiredFailure() {
            insert("outer-start");
            try {
                inner.requiredThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("outer catches inner error");
            }
            System.out.println("outer still active=" + active());
            insert("outer-end");
            // Khi return, proxy outer cố commit nhưng transaction
            // đã bị inner REQUIRED đánh dấu rollback-only.
        }
    }

    private static void run(
            String label, Runnable scenario, JdbcTemplate jdbc) {
        System.out.println("=== " + label + " ===");
        try {
            scenario.run();
        } catch (UnexpectedRollbackException ex) {
            System.out.println("result=UnexpectedRollbackException");
        } catch (IllegalStateException ex) {
            System.out.println("result=IllegalStateException");
        }
        System.out.println("rows=" + jdbc.queryForList(
            "SELECT label FROM tx_events ORDER BY id", String.class));
        jdbc.update("DELETE FROM tx_events");
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE tx_events ("
                + "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, "
                + "label VARCHAR(60) NOT NULL)"
            );
            OuterService outer = context.getBean(OuterService.class);
            run("REQUIRED", outer::requiredThenOuterFail, jdbc);
            run("REQUIRES_NEW", outer::requiresNewThenOuterFail, jdbc);
            run("NOT_SUPPORTED", outer::notSupportedThenOuterFail, jdbc);
            run("RESUME_AFTER_INNER_ERROR", outer::resumeAfterInnerFailure, jdbc);
            run("ROLLBACK_ONLY", outer::catchRequiredFailure, jdbc);
        }
    }
}
```

**Giải thích thiết kế và phép kiểm:**

- `InnerService` và `OuterService` là hai bean Spring riêng; outer nhận bean inner đã được Spring proxy khi ứng dụng sẵn sàng. `proxyTargetClass=true` chọn class-based proxy để ví dụ không cần interface.
- Mỗi scenario bên ngoài có `@Transactional` mặc định `REQUIRED`. `InnerService` chỉ đổi policy bằng `propagation`.
- `TransactionSynchronizationManager.isActualTransactionActive()` cho biết **actual transaction** đang hoạt động trong thread. `TransactionAspectSupport.currentTransactionStatus().isNewTransaction()` đo logical scope hiện tại có mở physical transaction mới hay chỉ tham gia. Helper `isNew()` chỉ được gọi từ phương thức đang qua transaction interceptor; gọi ngoài đó có thể ném `NoTransactionException`.
- `boundResource()` trả `ConnectionHolder` (được xem dưới dạng `Object`) mà manager bind với `DataSource`. So sánh `==` trước/sau lời gọi inner minh họa **cùng resource outer được gắn trở lại**; đây là cách quan sát nội bộ trong demo, không phải API để code nghiệp vụ phụ thuộc vào identity của connection holder.
- Dùng `DriverManagerDataSource` chỉ để demo; Spring quản lý connection transaction thông qua `JdbcTransactionManager`. Trong môi trường thật, sử dụng connection pool; `REQUIRES_NEW` cần tính đến nhiều connection.
- Bản ghi outer được tạo sau khi inner `REQUIRES_NEW`/`NOT_SUPPORTED` chạy trong hai case tương ứng để tránh tạo xung đột lock trên một bảng. Demo không cố mô phỏng database isolation của mọi driver.
- Exception được cố tình ném để kiểm tra rollback; không nên copy behavior đó vào nghiệp vụ thật.

### 7.4. Lệnh chạy và output kỳ vọng

Cài JDK 17+ và Maven, từ thư mục `spring-propagation-demo` chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.tx.Main
```

Những dòng **do code ví dụ in ra** (không liệt kê log Maven/JDBC có thể khác tùy môi trường):

```text
=== REQUIRED ===
outer REQUIRED active=true
inner REQUIRED active=true new=false
result=IllegalStateException
rows=[]
=== REQUIRES_NEW ===
inner REQUIRES_NEW active=true new=true
outer restored=true active=true
result=IllegalStateException
rows=[inner-new]
=== NOT_SUPPORTED ===
inner NOT_SUPPORTED active=false
outer restored=true active=true
result=IllegalStateException
rows=[outside-tx]
=== RESUME_AFTER_INNER_ERROR ===
inner REQUIRES_NEW fails active=true
outer catches inner error
outer restored=true active=true
rows=[outer-start, outer-end]
=== ROLLBACK_ONLY ===
inner REQUIRED fails active=true new=false
outer catches inner error
outer still active=true
result=UnexpectedRollbackException
rows=[]
```

**Đọc kết quả:**

1. **REQUIRED:** outer và inner cùng một physical transaction. Inner trả về bình thường, nhưng outer ném exception → cả hai INSERT rollback → `rows=[]`.
2. **REQUIRES_NEW:** inner tạo transaction B riêng, commit `inner-new`; Spring resume resource A (`restored=true`). Outer sau đó rollback A, bản ghi B vẫn còn.
3. **NOT_SUPPORTED:** inner không có actual transaction (`active=false`). H2 với connection auto-commit commit `outside-tx`; Spring resume A, outer rollback, bản ghi bên trong vẫn còn.
4. **RESUME_AFTER_INNER_ERROR:** B rollback bản ghi `inner-new-failed`, Spring resume A **trước khi exception tới catch block của outer**. Outer tiếp tục, commit `outer-start` và `outer-end`.
5. **ROLLBACK_ONLY:** inner `REQUIRED` ném unchecked exception; interceptor đánh dấu physical transaction A là rollback-only. Outer đã catch exception và thấy transaction active, nhưng trạng thái “active” **không có nghĩa là còn được commit**. Khi outer kết thúc bình thường và cố commit, Spring rollback A và ném `UnexpectedRollbackException` để caller biết commit thất bại.

## 8. Những sắc thái quan trọng về suspend/resume

### 8.1. Spring giữ lại những gì khi tạm ngưng?

Ở các triển khai dựa trên `AbstractPlatformTransactionManager`, quá trình suspend thường gồm: tạm dừng transaction synchronizations, gọi thao tác suspend do transaction manager chuyên biệt cung cấp, unbind resource của outer khỏi thread, giữ lại tên transaction, trạng thái read-only, isolation và cờ actual transaction. Sau khi inner hoàn thành, Spring resume resource của outer và khôi phục synchronization/metadata.

Khả năng suspend thực tế **phụ thuộc transaction manager**. Với JDBC local transaction do `DataSourceTransactionManager`/`JdbcTransactionManager` quản lý thì phổ biến; với `JtaTransactionManager`, việc suspend giao dịch JTA có thể cần một JTA `TransactionManager` mà server/container phải cung cấp. Nếu manager hoặc tài nguyên không hỗ trợ, đừng giả định mọi propagation sẽ chạy như ví dụ JDBC.

### 8.2. “Resume” không bắt đầu lại transaction đã tạm ngưng

Transaction A **vẫn mở** trong thời gian inner chạy; khi resume, Spring gắn lại ngữ cảnh để outer tiếp tục. Do đó:

- A không bị tự commit, rollback hoặc reset timeout vì tạm ngưng.
- Những lock của A có thể vẫn còn, làm inner B chờ; đặc biệt nếu B cần cập nhật đúng row mà A đang khóa, B có thể block/timeout và không được A “nhả khóa” chỉ vì suspend.
- Connection của A có thể vẫn bị giữ; B còn cần connection khác. Cần đánh giá thời gian giữ connection và giới hạn pool.
- Đừng coi `REQUIRES_NEW` là một kỹ thuật “né khóa” hoặc “chạy song song” tự động.

### 8.3. Nếu `NOT_SUPPORTED` ném exception thì sao?

Spring resume A trước khi trả exception về caller, nhưng kết quả cuối của A do **transaction boundary của outer** quyết định:

- Nếu outer không bắt unchecked exception: exception thoát ra interceptor của A → A rollback mặc định.
- Nếu outer bắt và xử lý exception mà không đánh dấu rollback-only: A có thể commit.
- Bất kỳ câu lệnh non-transactional đã commit ở inner không tự động rollback theo A trong hai trường hợp trên.

### 8.4. Trong `REQUIRED`, “bắt exception” chưa chắc giúp commit

Khi inner đang tham gia A mà transaction interceptor đánh dấu rollback-only, outer catch có thể xử lý lỗi hiển thị nhưng không xóa được rollback-only. Đây là tình huống dẫn đến `UnexpectedRollbackException`. Nếu cần một phần thất bại nhưng transaction A vẫn commit, phải xem lại mục tiêu nhất quán: dùng savepoint (`NESTED` với manager/driver hỗ trợ), tách physical transaction độc lập bằng `REQUIRES_NEW`, hoặc thiết kế lại nghiệp vụ; không được đơn giản nuốt exception để giả lập thành công.

### 8.5. Tham gia không kế thừa được “quyền commit” riêng

Inner `REQUIRED` với `readOnly=false` vẫn không thể tự nâng một outer `readOnly=true` thành giao dịch ghi đúng nghĩa. Isolation và timeout của inner cũng không tự thay thế cấu hình outer. Nếu cần bảo đảm chắc chắn tính tương thích, kiểm tra `validateExistingTransaction` và chính sách của manager thay vì trông chờ Spring âm thầm ghi đè thuộc tính.

## 9. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| `this.innerMethod()` thay vì gọi bean inner qua proxy | Propagation mới bị bỏ qua; không suspend/join như mong đợi | Tách service, injected bean và gọi qua Spring proxy |
| Dùng `REQUIRES_NEW` cho quá nhiều lời gọi nhỏ | Mở nhiều connection/transaction, tốn tài nguyên, pool exhaustion | Chỉ dùng khi cần commit độc lập; sizing pool và đo tải |
| Nghĩ suspension sẽ nhả lock outer | Inner chờ lock của chính outer hoặc timeout | Giảm phạm vi outer, sắp xếp SQL, không để B đụng dữ liệu A đang khóa |
| Nghĩ `NOT_SUPPORTED` có rollback do outer | Side effect bên trong đã commit còn lại dù outer rollback | Tránh ghi cần atomicity khi không có transaction |
| Outer nuốt exception từ inner `REQUIRED` | Có thể nhận `UnexpectedRollbackException` khi outer commit | Hiểu rollback-only; test luồng lỗi |
| Nhầm `NESTED` là transaction riêng | Outer rollback vẫn mất dữ liệu inner | Phân biệt savepoint và physical transaction |
| Bỏ qua việc xử lý inner lỗi `REQUIRES_NEW` | Exception unchecked thoát ra khỏi outer làm cả A rollback | Catch/đưa ra business policy rõ ràng nếu outer cần tiếp tục |
| Giả định `@Transactional` qua thread mới | Transaction JDBC dựa vào thread-bound context, không tự truyền | Giữ trong call stack hợp lệ; thiết kế transaction riêng cho tác vụ async |
| Dùng JDBC connection raw, không qua Spring-aware API | Ghi ngoài connection bind với transaction | Dùng `JdbcTemplate`/`DataSourceUtils` hoặc repository được Spring quản lý |
| Nhiều `PlatformTransactionManager` nhưng chọn sai | Join/suspend trên manager A không bảo đảm thao tác trên datasource B tham gia | Chỉ định `@Transactional("managerName")` và test tích hợp |
| Dùng `SUPPORTS` rồi xem synchronization active là đang có transaction | Đoán sai phạm vi commit/rollback | Kiểm tra actual transaction, test DB |
| Kiểm tra rollback chỉ bằng unit test mock | Không quan sát được physical transaction hay connection thực | Tạo integration test có database thật |

## 10. Chọn propagation theo mục tiêu nhất quán

- **Tất cả thao tác phải commit/rollback cùng nhau:** outer `REQUIRED`, inner `REQUIRED` (hoặc `MANDATORY` nếu inner tuyệt đối không được chạy độc lập).
- **Service đọc có thể tận dụng transaction của caller, nhưng không tự cần transaction:** cân nhắc `SUPPORTS`, hiểu ràng buộc actual transaction và synchronization.
- **Một bản ghi audit/notification state được commit độc lập với transaction chính:** có thể dùng `REQUIRES_NEW`, nhưng cân nhắc pool, lock và tính nhất quán dữ liệu giữa các giao dịch.
- **Đoạn code thực sự không cần database transaction:** cân nhắc `NOT_SUPPORTED`; nếu có I/O ghi, chấp nhận việc nó có thể commit ngoài A.
- **Muốn rollback một phần và tiếp tục physical transaction chính:** `NESTED` với JDBC/savepoint được hỗ trợ, có kiểm chứng trên DB thật.
- **Phải từ chối gọi khi không có transaction / khi đã có transaction:** `MANDATORY` / `NEVER` tương ứng.

**Bài tập tự kiểm tra:**

1. Outer `REQUIRED` mở transaction A, inner `REQUIRED` thành công. Inner đã commit độc lập chưa? **Chưa**, commit physical A thuộc boundary ngoài.
2. Outer A rollback sau khi inner `REQUIRES_NEW` commit B. B có tự rollback theo A không? **Không**, chúng độc lập.
3. `NOT_SUPPORTED` có tạo transaction mới thay cho A không? **Không**, nó chạy không có actual transaction và resume A sau đó.
4. `REQUIRES_NEW` có làm outer A nhả lock khi suspend không? **Không**, A vẫn mở và lock có thể vẫn giữ.
5. Inner `REQUIRED` ném unchecked exception và outer catch rồi trả bình thường. Có chắc commit được A không? **Không**, có thể rollback-only và `UnexpectedRollbackException`.
6. `NESTED` và `REQUIRES_NEW` khác nhau thế nào? **NESTED thường dùng savepoint trong cùng physical A; REQUIRES_NEW tạo B độc lập**.
7. Transaction local JDBC có tự theo lời gọi `@Async`/thread mới không? **Không**; cần ranh giới transaction riêng ở thread đó.

## Tài liệu tham khảo

- Spring Framework — Transaction Propagation, `REQUIRED` / `REQUIRES_NEW` / `NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `Propagation` enum Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/annotation/Propagation.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — `AbstractPlatformTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
