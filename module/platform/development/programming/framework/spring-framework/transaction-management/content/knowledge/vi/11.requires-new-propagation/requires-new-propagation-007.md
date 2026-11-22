# REQUIRES_NEW cho nhật ký độc lập: lợi ích và đánh đổi tính nguyên tử nghiệp vụ

## 1. Bài toán: nghiệp vụ thất bại nhưng vẫn cần lưu dấu vết

Giả sử ứng dụng đặt đơn hàng. Ta muốn ghi một bản ghi audit: ai đã thử tạo đơn, lúc nào, với mã thao tác nào. Nếu hệ thống kiểm tra tồn kho không đạt hoặc giao dịch nghiệp vụ bị rollback, một số yêu cầu giám sát, bảo mật hoặc kiểm toán vẫn muốn biết **đã có một lần thử thao tác**.

Vấn đề xuất hiện khi đặt cả nghiệp vụ và audit trong **cùng transaction**:

```text
BEGIN transaction nghiệp vụ
  INSERT business_order
  INSERT audit_log ("ORDER_ATTEMPTED")
  THÀNH PHẦN KHÁC NÉM RuntimeException
ROLLBACK transaction
  => business_order biến mất
  => audit_log cũng biến mất
```

Đây là tính **atomicity** của một transaction: các thay đổi cùng transaction sẽ commit hoặc rollback như một nhóm. Khi mục đích là *ghi dấu vết kể cả khi nghiệp vụ bị rollback*, tính nguyên tử này lại khiến audit không còn.

Một lựa chọn của Spring là tách phương thức audit sang một Spring bean khác và khai báo:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAttempt(...) {
    // INSERT audit_log bằng transaction độc lập.
}
```

Đây là **chữ ký minh họa**, chưa phải chương trình Java độc lập. Khi được Spring transaction interceptor gọi đúng cách, `REQUIRES_NEW` yêu cầu **một transaction vật lý riêng**, không tham gia transaction hiện tại của caller.

**Đổi lại:** nếu audit commit thành công rồi nghiệp vụ rollback, dữ liệu audit **vẫn tồn tại**. Đó có thể chính là yêu cầu đối với nhật ký thao tác thất bại, nhưng cũng có thể phá vỡ quy tắc nghiệp vụ nếu audit được hiểu là chứng nhận "đơn hàng đã được tạo thành công".

Bài học này không chỉ hướng dẫn cú pháp `REQUIRES_NEW`, mà quan trọng hơn là **chọn đúng ý nghĩa log, ranh giới commit và chính sách xử lý lỗi**.

## 2. Hiểu đúng `REQUIRES_NEW`

Spring phân biệt **logical transaction scope** (mỗi phương thức có thuộc tính giao dịch) và **physical transaction** (transaction thực trên JDBC connection/ORM resource). Với `Propagation.REQUIRED`, nhiều logical scopes có thể dùng chung một physical transaction. Với `Propagation.REQUIRES_NEW`, phạm vi bên trong luôn dùng **physical transaction độc lập** nếu transaction manager có thể tạo nó.

Khi caller đã ở trong transaction:

```text
Caller -> BusinessService.placeOrder() [REQUIRED]
           |
           |  TX-A: transaction nghiệp vụ (Connection A)
           |  INSERT business_order
           |
           +--> AuditLogService.record() [REQUIRES_NEW]
           |      SUSPEND TX-A (giữ resource của TX-A để resume)
           |      BEGIN TX-B (Connection B)
           |      INSERT audit_log
           |      COMMIT hoặc ROLLBACK TX-B
           |      RELEASE TX-B resources
           |      RESUME TX-A
           |
           |  Tiếp tục TX-A
           '-- COMMIT hoặc ROLLBACK TX-A
```

Các hệ quả:

- **TX-B có commit/rollback riêng.** TX-A rollback **không thể tự động hoàn tác** bản ghi đã commit trong TX-B.
- Nếu TX-B rollback, trạng thái rollback-only của TX-B **không tự làm TX-A rollback-only**. Nhưng **exception từ TX-B nếu tiếp tục ném ra TX-A** vẫn có thể khiến TX-A rollback theo rollback rules của TX-A.
- Nếu TX-A chưa mở transaction, `REQUIRES_NEW` vẫn mở một transaction mới. Từ "new" không có nghĩa chỉ tạo khi có outer.
- Transaction ngoài thường giữ tài nguyên đã mượn, trong khi inner cần resource riêng. Với JDBC local transaction manager, đây thường là một **connection thứ hai**, không phải savepoint trên Connection A.
- Kết thúc phương thức `record()` theo đường bình thường không phải là đủ để suy ra mọi hệ thống ngoài DB đã được cập nhật. Nó chỉ giúp transaction interceptor bắt đầu quá trình commit của TX-B; commit vẫn có thể thất bại.

### So sánh các propagation thường bị nhầm

| Annotation trên hàm audit | Khi caller đang có TX-A | Nếu TX-A rollback sau khi audit trở về |
| --- | --- | --- |
| `REQUIRED` (mặc định) | Audit tham gia **cùng physical TX-A** | Audit rollback cùng TX-A |
| `REQUIRES_NEW` | Tạm treo TX-A, audit chạy **TX-B độc lập** | Audit đã commit trong TX-B vẫn còn |
| `NESTED` | Thường dùng savepoint trên **chính physical TX-A** (nếu được hỗ trợ) | Audit vẫn rollback nếu **toàn TX-A** rollback |
| `NOT_SUPPORTED` | Tạm treo TX-A, audit chạy **ngoài transaction Spring** | Tùy auto-commit/tài nguyên; không có atomic unit mới bảo vệ nhiều SQL của audit |

Không dùng `NESTED` thay `REQUIRES_NEW` khi yêu cầu là "nhật ký phải sống sót qua rollback toàn bộ nghiệp vụ". Ngược lại, không dùng `REQUIRES_NEW` khi yêu cầu là "audit và đơn hàng phải thành công hoặc thất bại cùng nhau".

## 3. Hai mức nguyên tử khác nhau

Một **transaction vật lý riêng** vẫn bảo đảm tính nguyên tử cho *các câu SQL nằm trong chính nó*. Điều bị đánh đổi là **tính nguyên tử của toàn bộ thao tác nghiệp vụ gồm cả TX-A và TX-B**.

Ví dụ:

- TX-B chỉ có hai câu SQL ghi audit: TX-B rollback thì cả hai được hoàn tác.
- Nhưng TX-B đã commit rồi thì TX-A rollback sau đó không thể điều khiển TX-B nữa.
- Ngược lại, TX-A có thể commit thành công dù TX-B rollback và exception của audit đã được caller xử lý hợp lệ.

Bảng kết quả khi phương thức nghiệp vụ **có chọn cách xử lý exception để tiếp tục**:

| Physical TX nghiệp vụ | Physical TX audit | Kết quả được phép sau cùng |
| --- | --- | --- |
| Commit | Commit | Có business record, có audit |
| Rollback | Commit | Không có business record, **vẫn có audit** |
| Commit | Rollback | Có business record, **không có audit** |
| Rollback | Rollback | Không có business record, không có audit |

Đây là bốn **trạng thái khả dĩ**, không có nghĩa Spring tự phát sinh cả bốn nếu logic luôn ném lỗi. Exception, propagation và cách xử lý tại caller quyết định transaction ngoài có tiếp tục commit được không.

**Tách transaction không phải giải pháp để đạt atomicity liên hệ giữa hai cơ sở dữ liệu hoặc hai hệ thống.** `REQUIRES_NEW` là độc lập, *không phải* distributed transaction coordinator và không đảm bảo exactly-once giữa audit và nghiệp vụ.

## 4. Chọn thông điệp audit theo ý nghĩa thực

Trước khi viết code, hãy phân biệt ba loại sự kiện:

1. **Attempt / intent:** "người dùng X đã *thử* thực hiện hành động Y". Sự kiện này vẫn có ý nghĩa ngay cả khi thao tác thất bại. Đây là ứng viên hợp lý cho audit độc lập.
2. **Outcome:** "hành động Y đã *thực sự* commit" hoặc "đã rollback". Sự kiện này cần được ghi **sau khi biết kết quả cuối của transaction**, hoặc qua cơ chế bền vững phù hợp.
3. **Business event / integration message:** "OrderCreated" để các hệ thống khác cập nhật trạng thái. Nếu phát hành trước commit, consumer có thể tin vào đơn hàng không tồn tại. Loại này thường cần **transactional outbox**, chứ không đơn thuần một `REQUIRES_NEW` trước lúc outer commit.

Ví dụ đặt tên:

| Bản ghi | Outer rollback xảy ra | Diễn giải có đúng không? |
| --- | --- | --- |
| `ORDER_ATTEMPTED` | Audit vẫn giữ | **Đúng:** đã có một lần thử đặt đơn |
| `ORDER_CREATED` trước khi outer commit | Audit vẫn giữ | **Sai lệch:** đơn chưa từng commit |
| `ORDER_CREATION_FAILED` sau khi xác nhận rollback | Audit giữ | Đúng nếu xác nhận đúng kết quả và ghi log thành công |
| `ORDER_COMMITTED` phát trước commit | Audit giữ | Có thể sai nếu commit sau đó thất bại |

Đừng dùng một record "thành công" trong TX-B làm bằng chứng TX-A đã commit. Chính **tên event, timestamp, correlation ID và vị trí ghi** quyết định người vận hành hiểu đúng hay sai.

## 5. Ví dụ hoàn chỉnh chạy được: bốn tình huống đối xứng

Ta viết **một chương trình Java 17+** dùng Spring Framework **6.2.5**, Spring JDBC và H2 **2.2.224**. Không cần Spring Boot, server Jakarta EE hay cơ sở dữ liệu bên ngoài.

Điểm thiết kế của ví dụ:

- `BusinessService`: mỗi phương thức dùng `@Transactional`, propagation mặc định `REQUIRED`, tạo transaction nghiệp vụ TX-A.
- `AuditLogService`: phương thức `record(...)` có `@Transactional(propagation = REQUIRES_NEW)`, tạo transaction TX-B **qua Spring bean riêng**.
- Hai bảng `business_order` và `audit_log` không có foreign key với nhau, bởi TX-B không thể tin rằng row mới của TX-A đã commit hay nhìn thấy row chưa commit.
- H2 in-memory đảm bảo số lượng bản ghi dễ kiểm tra sau mỗi ca.
- Exception dùng `IllegalStateException` (unchecked) để rollback theo mặc định, trừ khi outer chủ động bắt và tiếp tục.

### 5.1. Cấu trúc tệp

```text
independent-audit-demo/
├── pom.xml
└── src/main/java/demo/IndependentAuditDemo.java
```

### 5.2. Tạo `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>independent-audit-demo</artifactId>
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
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.5</version>
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

`spring-context` cung cấp ApplicationContext/JavaConfig, `spring-jdbc` cung cấp JdbcTemplate và JDBC transaction manager; H2 là database thử nghiệm. `DriverManagerDataSource` dưới đây chỉ phù hợp demo, không phải connection pool production.

### 5.3. Tạo `src/main/java/demo/IndependentAuditDemo.java`

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public class IndependentAuditDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            BusinessService business = context.getBean(BusinessService.class);

            jdbc.execute("""
                CREATE TABLE business_order (
                    id INT PRIMARY KEY,
                    description VARCHAR(80) NOT NULL
                )
                """);

            jdbc.execute("""
                CREATE TABLE audit_log (
                    id INT PRIMARY KEY,
                    event_type VARCHAR(80) NOT NULL
                )
                """);

            // CA A: audit commit trước, nghiệp vụ rollback sau.
            try {
                business.businessFailsAfterAudit(1, 101);
            } catch (IllegalStateException ex) {
                System.out.println("CASE_A_ERROR=" + ex.getMessage());
            }
            report("AFTER_A", jdbc);

            // CA B: audit rollback, nhưng nghiệp vụ bắt lỗi và commit.
            business.auditFailsButBusinessCommits(2, 102);
            report("AFTER_B", jdbc);

            // CA C: lỗi audit lan ra ngoài, cả hai transaction rollback.
            try {
                business.auditFailsAndPropagates(3, 103);
            } catch (IllegalStateException ex) {
                System.out.println("CASE_C_ERROR=" + ex.getMessage());
            }
            report("AFTER_C", jdbc);

            // CA D: cả hai transaction commit.
            business.bothCommit(4, 104);
            report("AFTER_D", jdbc);
        }
    }

    private static void report(String label, JdbcTemplate jdbc) {
        int orders = jdbc.queryForObject(
                "SELECT COUNT(*) FROM business_order", Integer.class);
        int audits = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_log", Integer.class);
        System.out.printf("%s business=%d audit=%d%n", label, orders, audits);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:independent_audit;DB_CLOSE_DELAY=-1");
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
        public AuditLogService auditLogService(JdbcTemplate jdbc) {
            return new AuditLogService(jdbc);
        }

        @Bean
        public BusinessService businessService(
                JdbcTemplate jdbc, AuditLogService audit) {
            return new BusinessService(jdbc, audit);
        }
    }

    public static class AuditLogService {
        private final JdbcTemplate jdbc;

        public AuditLogService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void record(int auditId, String eventType, boolean fail) {
            jdbc.update(
                    "INSERT INTO audit_log (id, event_type) VALUES (?, ?)",
                    auditId, eventType);

            if (fail) {
                throw new IllegalStateException("audit failure");
            }
        }
    }

    public static class BusinessService {
        private final JdbcTemplate jdbc;
        private final AuditLogService audit;

        public BusinessService(JdbcTemplate jdbc, AuditLogService audit) {
            this.jdbc = jdbc;
            this.audit = audit;
        }

        @Transactional
        public void businessFailsAfterAudit(int orderId, int auditId) {
            insertOrder(orderId);
            audit.record(auditId, "ORDER_ATTEMPTED", false);
            throw new IllegalStateException("business failure");
        }

        @Transactional
        public void auditFailsButBusinessCommits(int orderId, int auditId) {
            insertOrder(orderId);

            try {
                audit.record(auditId, "ORDER_ATTEMPTED", true);
            } catch (IllegalStateException ex) {
                System.out.println("CASE_B_AUDIT_ERROR=" + ex.getMessage());
                // Đây là chính sách minh họa: lỗi audit KHÔNG chặn business.
            }
        }

        @Transactional
        public void auditFailsAndPropagates(int orderId, int auditId) {
            insertOrder(orderId);
            audit.record(auditId, "ORDER_ATTEMPTED", true);
            // Exception không được bắt: transaction nghiệp vụ rollback.
        }

        @Transactional
        public void bothCommit(int orderId, int auditId) {
            insertOrder(orderId);
            audit.record(auditId, "ORDER_ATTEMPTED", false);
        }

        private void insertOrder(int orderId) {
            jdbc.update(
                    "INSERT INTO business_order (id, description) "
                    + "VALUES (?, ?)", orderId, "example order");
        }
    }
}
```

**Vì sao code đặt hai service ở hai bean khác nhau?** Spring `@Transactional` mặc định hoạt động qua AOP proxy: lời gọi từ bean `BusinessService` sang bean `AuditLogService` được proxy intercept. Nếu đặt `@Transactional(REQUIRES_NEW)` trên một phương thức `private` trong cùng class rồi gọi bằng `this.record()`, annotation mới thường **không được áp** do self-invocation. Khi ấy audit có thể bị gộp vào outer transaction và không còn độc lập.

Ở cấu hình này, `@Bean` tạo Spring-managed beans; `@EnableTransactionManagement` kích hoạt transaction interceptor; `JdbcTransactionManager` quản lý một `DataSource`. `proxyTargetClass = true` yêu cầu class-based proxy, phù hợp khi lấy service theo concrete class từ context. `JdbcTemplate` của hai service dùng cùng `DataSource`, nhưng transaction interceptor cấp connection khác cho inner `REQUIRES_NEW` khi outer còn đang active.

**Vì sao không dùng foreign key từ audit sang business_order?** Nếu TX-A chưa commit row order, TX-B dùng connection riêng có thể không nhìn thấy row đó. Một foreign key bắt buộc tham chiếu order chưa commit có thể chờ lock, lỗi hoặc gây deadlock. Audit attempt nên chứa correlation ID/operation ID độc lập, không giả định business row đã tồn tại bền vững.

### 5.4. Chạy chương trình

Trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.IndependentAuditDemo
```

Các dòng từ `System.out` của chương trình, **không tính thông báo của Maven/Spring**:

```text
CASE_A_ERROR=business failure
AFTER_A business=0 audit=1
CASE_B_AUDIT_ERROR=audit failure
AFTER_B business=1 audit=1
CASE_C_ERROR=audit failure
AFTER_C business=1 audit=1
AFTER_D business=2 audit=2
```

### 5.5. Phân tích bốn ca

**CA A — Audit commit, business rollback**

1. `BusinessService.businessFailsAfterAudit(1, 101)` mở TX-A và `INSERT business_order`.
2. `audit.record(..., false)` đi qua bean proxy, TX-A được tạm treo, TX-B bắt đầu.
3. TX-B insert `audit_log` rồi commit; audit count thành **1**.
4. TX-A được resume, sau đó method ném `IllegalStateException("business failure")`.
5. TX-A rollback row order. Kết quả `business=0, audit=1`.

Đây là trường hợp **nhật ký thao tác thất bại được giữ lại**, nhưng toàn bộ operation **không còn atomic** như một đơn vị.

**CA B — Audit rollback, business vẫn commit**

1. Outer TX-A insert order số 2.
2. Inner TX-B insert audit số 102 rồi ném `IllegalStateException("audit failure")`; transaction interceptor rollback TX-B.
3. Exception đi về outer method, nhưng `try/catch` ở `BusinessService` xử lý và **không ném tiếp**.
4. TX-A vẫn có thể commit bình thường; kết quả `business=1, audit=1`.

Ca này minh họa lỗi đối xứng: **đơn hàng tồn tại nhưng không có bản ghi audit mới**. Nếu audit là bắt buộc theo chính sách an toàn/tuân thủ, **không được nuốt exception theo kiểu fail-open này**. Ví dụ chỉ dùng để cho thấy khả năng độc lập của hai transactions.

**CA C — Audit rollback, exception lan ra khiến business rollback**

1. Outer TX-A insert order số 3.
2. Inner TX-B insert audit số 103, sau đó lỗi; TX-B rollback.
3. `BusinessService.auditFailsAndPropagates()` không bắt exception. `IllegalStateException` thoát ra khỏi boundary của TX-A.
4. Theo rollback rule mặc định, TX-A cũng rollback. Kết quả không đổi: `business=1, audit=1`.

Quan trọng: hai transaction rollback **vì hai quyết định riêng**, không phải TX-B tự động buộc TX-A rollback. Exception từ inner là nguyên nhân khiến interceptor của outer quyết định rollback. Nếu loại exception/cấu hình `noRollbackFor` khác, kết quả có thể khác.

**CA D — Cả hai commit**

Inner TX-B audit số 104 commit trước; sau đó TX-A tạo order số 4 commit. Kết quả `business=2, audit=2`. Đây là đường đi bình thường, **nhưng vẫn có khoảng hở**: TX-B có thể đã commit, trong khi TX-A bị lỗi khi flush/commit ngay sau đó. Không thể dùng việc cả hai thường thành công để suy ra atomicity giữa chúng.

## 6. Nếu thay `REQUIRES_NEW` bằng `REQUIRED` thì sao?

Đổi **riêng** annotation của `AuditLogService.record(...)`:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void record(int auditId, String eventType, boolean fail) {
    // Cùng logic INSERT audit_log và ném lỗi như demo.
}
```

Đây là **mã mô tả thay đổi**, không phải một phương thức chạy độc lập.

Khi outer đã có TX-A, audit dùng cùng TX-A:

- Ở **ca A**, outer rollback sẽ rollback **cả order và audit**. Không còn bảo đảm lưu audit attempt.
- Ở **ca B**, inner method ném unchecked exception. Dù outer bắt exception, transaction interceptor của inner có thể đã đánh dấu **TX-A rollback-only**. Lúc outer tìm cách commit, Spring có thể ném `UnexpectedRollbackException` thay vì âm thầm commit. **Bắt exception ở outer không xóa rollback-only.**
- Ở **ca C**, cả hai thay đổi rollback trong cùng TX-A.
- Ở **ca D**, cả order và audit commit chung một transaction.

Vậy `REQUIRED` phù hợp khi audit phải **đồng nhất số phận** với business state; `REQUIRES_NEW` phù hợp khi audit có chủ đích tồn tại ngay cả sau failure của business. Không có cách đổi propagation nào vừa cho phép "audit phải commit dù business rollback" **và** bắt buộc "business và audit luôn commit/rollback cùng nhau": hai yêu cầu đó mâu thuẫn ở cấp transaction.

## 7. Lỗi audit: fail-open hay fail-closed?

**Fail-open** nghĩa là audit lỗi nhưng nghiệp vụ vẫn được phép commit. Nó tối ưu availability, nhưng có thể vi phạm yêu cầu audit bắt buộc.

**Fail-closed** nghĩa là audit lỗi thì nghiệp vụ phải thất bại/rollback. Nó giảm nguy cơ tạo business state không có audit, nhưng làm nghiệp vụ phụ thuộc sức khỏe hạ tầng audit.

| Yêu cầu | Hướng thiết kế | Đánh đổi |
| --- | --- | --- |
| Cần giữ lại mọi **attempt** kể cả business rollback | Audit bằng `REQUIRES_NEW` ở bean độc lập, có error policy rõ | Audit có thể tồn tại dù business không commit |
| Không được tồn tại business record thiếu audit đồng nhất | Ghi business + audit/outbox bằng `REQUIRED` cùng DB transaction | Business rollback thì audit cũng rollback |
| Audit lỗi phải ngăn nghiệp vụ | Không bắt/nuốt exception; hoặc chủ động đánh dấu outer rollback-only | Giảm availability nếu audit DB bị lỗi |
| Audit best-effort | Bắt lỗi có kiểm soát, metric/alert và fallback phù hợp | Có thể mất record; không quảng bá là audit đầy đủ |
| Cần event "nghiệp vụ đã commit" gửi ra hệ thống khác | Transactional outbox hoặc transaction-aware delivery sau commit | Cần sender/consumer, dedupe và vận hành thêm |

**Chú ý:** kể cả fail-closed, `REQUIRES_NEW` không tạo atomicity ngược chiều. Nếu audit TX-B đã commit nhưng business TX-A thất bại sau đó, audit vẫn sống sót. Fail-closed chỉ quyết định **phản ứng với lỗi audit**, không đồng bộ hai commit vào một đơn vị.

Trong hệ thống yêu cầu kiểm toán nghiêm ngặt, phải định nghĩa cả **log phải tồn tại kể cả rollback** và **nghiệp vụ được phép commit khi không ghi được log hay không**. Hai câu hỏi tách biệt.

## 8. Vì sao `REQUIRES_NEW` dễ gây rủi ro về connection pool và lock?

Spring cảnh báo trực tiếp: khi inner `REQUIRES_NEW` chạy, transaction outer thường vẫn giữ connection của nó, còn inner phải lấy connection mới từ pool. Điều này có thể làm cạn pool.

Giả sử **10 threads** đồng thời giữ **10 connections** ở outer, pool chỉ có **10**. Cả 10 threads gọi audit `REQUIRES_NEW` và chờ connection thứ hai; không thread nào trả connection outer cho đến khi inner xong. Kết quả có thể là pool starvation/timeout, thậm chí deadlock ở cấp cấp phát connection.

Hướng dẫn Spring là pool cần **lớn hơn số lượng threads đồng thời ít nhất 1**, nhưng kích thước thực tế phụ thuộc số mức lồng `REQUIRES_NEW`, số requests cạnh tranh, các tác vụ DB khác và timeout. Không diễn giải "thêm 1" thành công thức đảm bảo trong mọi tải.

### Lock và tính nhìn thấy dữ liệu

Inner chạy bằng physical transaction riêng. Ở isolation phổ biến như `READ_COMMITTED`, inner không được xem như đã thấy các row mới **chưa commit** từ outer. Inner audit cố đọc/update chính row mà outer đang khóa có thể chờ; nếu outer đang chờ inner hoàn thành thì xảy ra lock wait/deadlock hoặc timeout.

**Thiết kế tốt hơn cho audit độc lập:**

- Không để inner truy vấn bản ghi nghiệp vụ chỉ mới được outer insert nhưng chưa commit.
- Dùng một `operationId`/`requestId` được tạo trước, đưa vào audit như **giá trị mô tả**, không yêu cầu foreign key đến row chưa commit.
- Giữ transaction audit **ngắn**, chỉ insert dữ liệu cần thiết.
- Tránh audit service mở thêm nhiều `REQUIRES_NEW` lồng nhau.
- Theo dõi pool active/idle/wait, lock waits, deadlock, connection acquisition latency, thời gian commit và lỗi audit.
- Cấu hình timeout hợp lý và không giữ transaction outer trong lúc gọi mạng hay xử lý chậm kéo dài.

Ví dụ này dùng hai bảng độc lập để tránh một kiểu lock sai, **không chứng minh** mọi tình huống production đều không deadlock.

## 9. Điều gì `REQUIRES_NEW` không thể đảm bảo?

Một transaction audit độc lập không phải hệ thống audit hoàn hảo:

1. **Không bảo đảm record khi ứng dụng chết trước khi gọi audit.** Chưa bắt đầu TX-B thì chưa có gì để commit.
2. **Không bảo đảm record khi DB audit không dùng được.** TX-B vẫn có thể thất bại; phải có policy lỗi rõ ràng.
3. **Không chứng minh outcome nghiệp vụ cuối cùng.** TX-A vẫn có thể rollback sau TX-B commit.
4. **Không bảo đảm exactly-once.** Retry request/inner method có thể ghi log trùng nếu không có unique idempotency key.
5. **Không tự bảo đảm thứ tự toàn cục.** Các transaction riêng và concurrent requests có thể commit theo thứ tự khác nhau.
6. **Không bảo đảm thông tin không bị sửa.** Phân quyền insert-only, chống tamper, lưu retention và kiểm soát dữ liệu nhạy cảm vẫn là vấn đề riêng.
7. **Không biến nhiều DB thành giao dịch phân tán.** Một manager JDBC local không tự điều phối XA/2PC.
8. **Không làm cho external side effects rollback được.** Gửi email, HTTP request, queue publish bên trong TX-B không có nghĩa có thể undo nếu DB rollback.
9. **Không cam kết commit chắc chắn chỉ vì method target trả về.** Transaction interceptor còn phải flush/commit; lỗi tại bước đó có thể ném exception.
10. **Không tránh mọi race condition.** Người kiểm tra trạng thái order có thể thấy audit event ATTEMPTED trước khi TX-A quyết định commit hay rollback.

### Sự cố kết nối lúc commit

Một trường hợp khó là driver mất kết nối tại thời điểm gửi `COMMIT`: phía ứng dụng có thể không biết transaction audit đã commit hay chưa. Thử lại `INSERT` vô điều kiện có thể tạo log trùng. Nên có **operation ID ổn định** và unique constraint/idempotent write. Chính sách retry cần phân biệt lỗi rõ ràng có thể thử lại với lỗi commit outcome chưa xác định.

## 10. Tách audit attempt khỏi audit outcome

Nếu bài toán cần lưu **cả nỗ lực và kết quả**, có thể thiết kế hai event:

```text
Before/at request start:
  independent audit -> ACTION_ATTEMPTED(operationId)

Business transaction:
  perform business changes
  -> COMMIT hoặc ROLLBACK

After known completion:
  best-effort or durable mechanism
  -> ACTION_COMMITTED(operationId)
  -> ACTION_ROLLED_BACK(operationId)
```

Nhưng **không chỉ thêm một lệnh audit `REQUIRES_NEW` trong business method rồi đổi tên thành `ACTION_COMMITTED`**; event đó có thể được commit trước business.

Có vài lựa chọn:

- Ở tầng caller **sau khi service transactional proxy trả về thành công**, có thể biết interceptor đã hoàn tất phạm vi mà nó sở hữu. Tuy nhiên, nếu service ấy chỉ tham gia một transaction ngoài, kết quả cuối vẫn chưa có.
- `TransactionSynchronization.afterCommit()` hoặc `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` phù hợp cho logic chỉ chạy sau commit thành công của transaction vật lý tương ứng.
- `AFTER_ROLLBACK`/`AFTER_COMPLETION` callbacks có thể biết kết quả transaction được Spring quản lý; cần hiểu propagation, exception và thời điểm cleanup.
- Nếu callback muốn **ghi DB mới**, dùng một service riêng mở `REQUIRES_NEW` khi thích hợp; các resource của transaction vừa hoàn tất có thể còn gắn vào thread trong giai đoạn callbacks.
- Callback sau commit **không khiến việc ghi outcome vào DB khác trở nên atomic** với business commit. Nếu callback lỗi hoặc process chết sau commit, outcome log có thể thiếu.

Vì thế, khi yêu cầu là "đừng báo ORDER_COMMITTED cho consumer khi đơn chưa commit" và cần bền vững khi process chết, **outbox** thường là phương án đúng hơn.

## 11. Transactional outbox khi cần atomicity giữa business và event

Outbox khác về mục tiêu. Cùng một physical transaction `REQUIRED`, ghi cả business row và bản ghi outbox:

```sql
-- Hai thao tác nằm trong CÙNG transaction nghiệp vụ.
INSERT INTO business_order (id, description)
VALUES (10, 'new order');

INSERT INTO outbox_event (event_id, event_type, aggregate_id, payload)
VALUES ('op-10', 'ORDER_CREATED', 10, '{"orderId":10}');
```

Đoạn SQL chỉ minh họa mô hình bảng; `outbox_event` không được định nghĩa trong chương trình H2 ở mục 5 nên **không chạy độc lập** nếu chưa tạo bảng.

Kết quả:

- TX-A commit: cả order và outbox event cùng tồn tại.
- TX-A rollback: cả order và outbox event đều biến mất.
- Worker/background publisher đọc outbox đã commit, gửi message đến broker, ghi trạng thái đã gửi hoặc retry.
- Sender/consumer phải xử lý **at-least-once / idempotency**, vì publish có thể thành công trước khi worker cập nhật trạng thái outbox.

Outbox giải quyết **atomicity giữa trạng thái business và ý định phát sự kiện trong cùng DB**, chứ không tự làm message broker tham gia cùng transaction. Nó cũng **không giữ được audit attempt** nếu transaction nghiệp vụ rollback, vì audit attempt và outbox có mục tiêu khác nhau.

### Bảng chọn cách làm

| Mục tiêu | Cách tiếp cận thường phù hợp |
| --- | --- |
| Ghi lại nỗ lực dù thao tác thất bại | Audit attempt bằng transaction độc lập `REQUIRES_NEW` |
| Đơn hàng và audit phải cùng commit/rollback | `REQUIRED`, cùng actual transaction/cùng tài nguyên |
| Phát `ORDER_CREATED` sau commit và chống mất event | Transactional outbox + publisher |
| Chỉ cần callback in-memory sau commit, chấp nhận thiếu khi process chết | `afterCommit`/`@TransactionalEventListener(AFTER_COMMIT)` |
| Bắt buộc ghi audit trước khi cho phép nghiệp vụ commit | Fail-closed, kiểm tra thực tế; cân nhắc ghi trong cùng transaction nếu cần atomicity |
| Giao dịch trên nhiều datasource phải atomic | Kiến trúc phù hợp JTA/XA hoặc phối hợp nghiệp vụ (saga), không chỉ `REQUIRES_NEW` |

## 12. Exception propagation, rollback-only và self-invocation

### 12.1. Exception không đồng nghĩa với shared rollback

Ở ca C, audit error được ném ra khỏi `AuditLogService` và rồi ra khỏi `BusinessService`. Cả hai roll back, nhưng **mỗi transaction rollback vì interceptor của riêng nó thấy unchecked exception**. `REQUIRES_NEW` không sao chép rollback-only flag vào outer transaction.

Ở ca B, ngoại lệ đã bị bắt trong business method, nên outer tiếp tục đến cuối và commit. Nếu yêu cầu kiểm toán bắt buộc, chính sách "bắt rồi bỏ qua" là vấn đề nghiệp vụ chứ không phải lỗi Spring.

### 12.2. Checked exception và tùy chỉnh rollback

Mặc định `RuntimeException` và `Error` làm Spring rollback, checked exception thường **không** tự rollback. Nếu audit ném một checked exception mà bạn muốn TX-B rollback, phải cấu hình rõ:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    rollbackFor = java.io.IOException.class)
public void recordWithCheckedError() throws java.io.IOException {
    throw new java.io.IOException("audit store unavailable");
}
```

Đây là **phương thức minh họa**; cần đặt trên Spring-managed bean, không phải method trực tiếp trong demo. Nếu outer cũng nhận exception và được cấu hình rollback tương ứng, TX-A có thể rollback theo quy tắc riêng.

### 12.3. Self-invocation không tạo transaction mới

**Sai lầm phổ biến:**

```java
@Service
class WrongService {
    @Transactional
    public void business() {
        saveAudit(); // this.saveAudit(): không đi qua proxy!
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit() {
        // Có thể đang dùng transaction outer thay vì mở TX-B.
    }
}
```

Đây là mã giải thích anti-pattern, không chạy độc lập vì chưa có imports/implementation. Ở Spring proxy mode mặc định, `this.saveAudit()` là lời gọi nội bộ nên **không được transaction advice intercept như một boundary mới**.

**Đúng:** dùng một bean `AuditLogService` riêng, để `BusinessService` gọi qua Spring proxy như ví dụ. Có thể dùng `TransactionTemplate` với propagation `REQUIRES_NEW` khi cần chương trình hóa boundary mà không phụ thuộc self-invocation, nhưng phải cấu hình transaction manager và exception handling cẩn thận.

### 12.4. Tránh ghi audit bằng đối tượng tự khởi tạo

`new AuditLogService(jdbc)` cũng không đi qua proxy nên không tự tạo transaction mới. Ngay cả khi method có annotation đúng, đối tượng phải được Spring quản lý và lời gọi đi qua proxy/transaction interceptor.

## 13. Kiểm thử transaction độc lập đúng cách

Chỉ assert phương thức audit đã được gọi là **chưa đủ**. Cần kiểm tra trạng thái DB **sau khi transaction ngoài đã kết thúc**:

- **Case A**: sau exception của outer, `business_order` không có row 1 nhưng `audit_log` có row 101.
- **Case B**: inner exception được outer xử lý, row 2 tồn tại nhưng row audit 102 không có.
- **Case C**: inner exception lan ra, cả row 3 và audit 103 không có.
- **Case D**: row 4 và audit 104 đều có.

Các truy vấn kiểm tra nên chạy ngoài transaction đang thử hoặc trong transaction mới có khả năng đọc kết quả commit. Nếu sử dụng Spring TestContext với `@Transactional` trên **test method**, nó có thể mở transaction test bên ngoài và rollback lúc test kết thúc, làm thay đổi ranh giới mà bạn muốn quan sát. Với integration test chuyên kiểm tra commit/rollback, cân nhắc bỏ `@Transactional` trên test, hoặc dùng `TestTransaction` với quản lý kết thúc transaction tường minh.

Để kiểm tra độc lập hiệu quả, đừng chỉ nhìn số lượng; ở hệ thống thật nên kiểm tra **operationId**, event type, transaction timestamps, trạng thái được mã hóa chính xác, và khả năng idempotent khi retry.

### Những ca lỗi cần thêm trong hệ thống thực

1. Audit DB không truy cập được: business fail-open hay fail-closed?
2. Transaction audit commit rồi connection rơi, caller không biết kết quả: retry có tạo log trùng không?
3. Outer giữ lock trên business row, inner audit vô tình đọc row ấy: có timeout không?
4. Pool đủ cho traffic cao điểm cùng lúc có outer + inner không?
5. Có transaction outer khác bao quanh service không? Ranh giới commit cuối cùng ở đâu?
6. Có callback `afterCommit`/`afterRollback` bị lỗi hoặc process chết giữa chừng không?
7. Các dữ liệu nhạy cảm được masking/retention phù hợp không?
8. Event audit có còn **đúng nghĩa** khi business fail nhưng audit row tồn tại không?

## 14. Checklist triển khai production

Trước khi chọn `REQUIRES_NEW` cho audit, hãy trả lời:

- **Yêu cầu nghiệp vụ:** Có thật sự cần giữ audit khi business rollback hay không? Nếu có, event ghi nhận **attempt** hay **committed outcome**?
- **Chính sách lỗi:** Audit down thì request có được commit? Ai nhận cảnh báo? Có fallback durable không?
- **Boundary:** Service audit là Spring bean độc lập? `@Transactional(REQUIRES_NEW)` có đi qua proxy không?
- **Tài nguyên:** Outer transaction và inner transaction có thể cùng giữ connections? Pool và timeout đã được load-test?
- **Lock:** Inner có chạm dữ liệu chưa commit/đang bị khóa bởi outer? Có FK gây block không?
- **Dữ liệu:** Có `operationId`/correlation ID, actor, loại thao tác, kết quả, thời điểm rõ ràng? Có unique constraint tránh duplicate?
- **Tính nhất quán:** Có đang dùng `REQUIRES_NEW` để phát business event "đã thành công" trước commit không? Nếu có, cân nhắc outbox.
- **Test:** Có integration test đủ ca A/B/C/D và lỗi commit không? Có test thiếu connection, rollback và retry?
- **Bảo mật:** Audit có quyền ghi tối thiểu, retention, masking dữ liệu nhạy cảm, chính sách chống sửa xóa không?

Thường nên giữ inner transaction **ngắn, chỉ một nhiệm vụ** và tránh những thao tác mạng chậm trong khi outer đang giữ connection/lock. Giao dịch độc lập là công cụ, không phải mặc định "an toàn hơn" cho mọi lời gọi audit.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Outer `@Transactional(REQUIRED)` ghi order, inner `@Transactional(REQUIRES_NEW)` ghi audit và commit. Outer sau đó ném `IllegalStateException`. Điều gì còn lại?

**Đáp án:** Outer rollback order; audit đã commit trong physical transaction riêng có thể vẫn còn. Không có atomicity chung cho hai transaction.

**Câu 2.** Inner audit rollback và ném unchecked exception. Outer bắt lỗi rồi trả về bình thường. Outer luôn rollback không?

**Đáp án:** Không. Với inner `REQUIRES_NEW`, rollback-only của inner không tự áp sang outer. Outer có thể commit nếu nó không bị đánh dấu rollback-only hoặc gặp lỗi khác; đó là ca B.

**Câu 3.** Nếu outer không bắt exception audit, điều gì xảy ra?

**Đáp án:** Exception thoát khỏi outer boundary có thể kích hoạt rollback rule của outer. Hai transaction rollback riêng biệt, như ca C.

**Câu 4.** Muốn audit chỉ xuất hiện nếu order thật sự commit. Dùng `REQUIRES_NEW` trước khi outer commit có phù hợp không?

**Đáp án:** Không phù hợp: audit có thể commit trước rồi outer rollback. Nếu cùng DB và cần atomicity, dùng transaction chung/outbox; nếu chỉ là tác vụ sau commit, cân nhắc after-commit hook với giới hạn reliability tương ứng.

**Câu 5.** Audit ở một phương thức của chính `BusinessService` gọi bằng `this.saveAudit()`, có `REQUIRES_NEW`. Nó có độc lập không?

**Đáp án:** Không thể mặc định như vậy. Proxy mode bỏ qua self-invocation, nên cần gọi qua proxy/bean khác hoặc dùng giao dịch chương trình hóa được cấu hình đúng.

**Câu 6.** Vì sao pool 10 connections cho 10 request đồng thời, mỗi request giữ outer connection rồi cần inner connection, có thể bị kẹt?

**Đáp án:** Mọi connection có thể bị outer chiếm; không có connection mới cho inner, nhưng outer lại đang chờ inner hoàn thành để giải phóng connection. Cần sizing và timeout phù hợp.

**Câu 7.** Audit độc lập đã ghi `ORDER_CREATED` và commit, nhưng business transaction rollback. Lỗi ở đâu?

**Đáp án:** Không nhất thiết do Spring; đó là lỗi **đặt tên/sự kiện sai thời điểm**. `ORDER_CREATED` là outcome, trong khi inner chỉ biết request đã được thử. Nên phân biệt attempted vs committed hoặc dùng outbox.

## Ghi nhớ

**`REQUIRES_NEW` tạo một physical transaction độc lập.** Nó thích hợp cho audit/nhật ký **ý định hoặc nỗ lực thao tác** cần tồn tại dù giao dịch nghiệp vụ rollback. Nhưng chính tính độc lập tạo ra hai hướng bất nhất: **audit có thể commit khi business rollback**, hoặc **business có thể commit khi audit rollback** nếu được phép bỏ qua lỗi audit.

Muốn bảo đảm cùng commit/rollback thì **không tách physical transaction**; muốn event chắc chắn gắn với business commit thì cần thiết kế transaction cùng DB/outbox hoặc một cơ chế bền vững phù hợp. Hãy lựa chọn dựa trên semantics, không dựa trên việc method có annotation đẹp.

## Tài liệu tham khảo chính thức

1. Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): phân biệt `REQUIRED`, `REQUIRES_NEW`, `NESTED`, độc lập physical transaction và cảnh báo pool.
2. Spring Framework — [Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptor/proxy.
3. Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): rollback rules và hạn chế self-invocation.
4. Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `AFTER_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION`.
5. Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`.
6. Spring Framework — [Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): lưu ý callback theo transaction và giới hạn của event.
