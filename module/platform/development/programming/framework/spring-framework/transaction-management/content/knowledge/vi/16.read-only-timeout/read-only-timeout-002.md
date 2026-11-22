# Phân biệt chỉ dẫn read-only với cơ chế chặn thao tác ghi trong Spring Transaction Management

## 1. Câu trả lời quan trọng nhất

`@Transactional(readOnly = true)` trong Spring **trước hết là một khai báo về ý định của transaction**: phần việc này được dự kiến chỉ đọc, và transaction infrastructure có thể dùng thông tin ấy để tối ưu hóa cách chạy. Nó **không phải một quy tắc bảo mật hay một bộ lọc SQL mặc định của Spring**. Có hệ quản trị hoặc JDBC driver sẽ thật sự từ chối `INSERT`, `UPDATE`, `DELETE` trong transaction được đánh dấu read-only; có hệ thống chỉ coi đó là hint và vẫn cho ghi.

Do đó phải phân biệt ít nhất bốn câu hỏi:

1. **Spring có ghi nhận transaction là read-only không?** Có thể kiểm tra bằng `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` khi ở trong transaction.
2. **JDBC driver có nhận hint read-only không?** Một JDBC transaction manager của Spring có thể gọi `Connection.setReadOnly(true)` khi tạo giao dịch mới. Theo JDBC, đây là *hint*, và driver/database có quyền xử lý khác nhau.
3. **ORM có tối ưu hóa thao tác đọc không?** Một JPA provider như Hibernate có thể điều chỉnh flush mode và hành vi quản lý entity để giảm công việc không cần thiết.
4. **Có biện pháp chặn ghi thực sự không?** Phải xác minh DB transaction mode (chẳng hạn `SET TRANSACTION READ ONLY` ở engine hỗ trợ), quyền của DB user, hoặc chính sách kiểm soát khác; ngay cả các cơ chế này cũng có phạm vi và giới hạn riêng.

Một thiết kế đúng không viết: “Đánh dấu `readOnly=true` nên chắc chắn không có cách nào UPDATE database.” Thay vào đó, hãy xác định **đang mong muốn tối ưu hóa đọc** hay **đang yêu cầu một guarantee cấm ghi**, chọn cơ chế phù hợp và kiểm chứng trên database sản xuất.

## 2. Vì sao có nhầm lẫn về chữ “read-only”?

Trong một ứng dụng Spring, “read-only” có thể chỉ nhiều tầng khác nhau:

| Tầng | Biểu hiện | Có chắc chắn chặn mọi ghi không? |
|---|---|---|
| **Intent của business method** | `@Transactional(readOnly=true)` | **Không**. Đây là metadata dành cho hạ tầng |
| **Spring transaction context** | `TransactionDefinition.isReadOnly()` / `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | **Không**. Cờ trạng thái không phân tích/lọc câu SQL |
| **JDBC connection** | `Connection.setReadOnly(true)` | **Không bảo đảm trên mọi driver**; có driver/environments thực thi read-only, có driver bỏ qua |
| **ORM / Hibernate** | Đổi flush mode, tối ưu dirty checking cho truy vấn | **Không phải hàng rào bảo mật**; hành vi tùy provider và cách phát SQL |
| **Read-only transaction mode của DB** | `SET TRANSACTION READ ONLY` / `BEGIN READ ONLY` ở DB hỗ trợ | **Có thể chặn thao tác sửa dữ liệu trong phạm vi DB mode**, nhưng hạn chế/dạng SQL được phép tùy DB |
| **Quyền database account** | Tài khoản chỉ có `SELECT`, không có quyền DML trên đối tượng cần bảo vệ | **Biện pháp kiểm soát truy cập mạnh hơn**, nếu GRANT/role/ownership đã cấu hình đúng |
| **Chính sách trong ứng dụng** | Guard từ chối command ghi trong read-only flow | Chặn **đường code đi qua guard**, không chặn đường SQL khác bỏ qua guard |

Ba từ dễ bị đánh đồng là **hint**, **optimization** và **enforcement**:

- **Hint**: thông tin đầu vào cho component khác, nhưng không phải một hợp đồng bắt buộc component đó phải từ chối ghi.
- **Optimization**: giảm chi phí thao tác (ví dụ bớt flush/dirty checking) nhưng không nhất thiết đổi quyền thực thi.
- **Enforcement**: có điểm kiểm tra thật sự từ chối lệnh ghi khi điều kiện vi phạm; cần biết điểm kiểm tra nằm ở application, driver, transaction mode hay database authorization.

**Không gọi tối ưu Hibernate là “DB bảo đảm không ghi”.** Và ngược lại, cũng đừng nói mọi database đều bỏ qua read-only: một số driver/DB thật sự chặn lệnh ghi trong transaction read-only.

## 3. Spring xử lý `@Transactional(readOnly=true)` như thế nào?

Ví dụ khai báo ý định trên một service đọc:

```java
@Service
public class InvoiceQueryService {
    private final InvoiceRepository repository;

    public InvoiceQueryService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public InvoiceView findInvoice(long id) {
        return repository.findViewById(id);
    }
}
```

Đoạn code này **chỉ mang tính minh họa**, cần class `InvoiceRepository`/`InvoiceView` và import thích hợp. Khi lời gọi từ bên ngoài đi qua Spring transaction proxy, interceptor đọc `TransactionAttribute` gồm propagation, isolation, timeout và **readOnly flag**. Khi cần bắt đầu physical transaction mới, transaction manager có cơ hội truyền read-only tới tài nguyên bên dưới.

Với transaction manager JDBC địa phương phổ biến (`DataSourceTransactionManager` hoặc subclass `JdbcTransactionManager`), một chu trình rút gọn:

```text
Caller
  |
  v
Spring transaction proxy
  |
  +-- đọc TransactionAttribute: readOnly=true
  |
  +-- bắt đầu physical transaction mới (nếu cần)
  |      |
  |      +-- lấy JDBC Connection
  |      +-- chuẩn bị connection, có thể gọi setReadOnly(true)
  |      +-- đặt isolation/autoCommit, bind connection vào thread
  |      +-- tùy cấu hình: thực thi SQL enforcement riêng
  |
  +-- chạy method business
  |      |
  |      +-- SELECT / [có thể vẫn cố INSERT, UPDATE...]
  |
  +-- commit hoặc rollback theo transaction rules
  +-- cleanup/reset connection sau completion
```

Spring **không mặc định bao quanh `JdbcTemplate.update()` bằng một if-block bắt mọi thao tác ghi khi metadata read-only là true**. `JdbcTemplate` vẫn gửi SQL xuống connection; chuyện có chạy thành công hay không phụ thuộc toàn bộ chuỗi hạ tầng.

### 3.1. JDBC `Connection.setReadOnly(true)` thực chất là gì?

JDBC định nghĩa `setReadOnly(boolean)` như một **hint** để driver/database có thể tối ưu và/hoặc áp dụng hành vi tương ứng. Không có guarantee thống nhất rằng `setReadOnly(true)` bắt buộc tất cả DBMS từ chối mọi DML.

Đặc biệt, API `JdbcConnection.setReadOnly(boolean)` của **H2** công bố rằng tham số này **bị bỏ qua**: một transaction của Spring được đánh dấu read-only vẫn có thể ghi một bảng H2 thông thường khi không có cơ chế enforcement khác.

Ở môi trường khác, ví dụ PostgreSQL JDBC, driver có tùy chọn và logic quản lý read-only mode có thể tạo transaction thực sự bị hạn chế ghi. Vì vậy không được lấy kết quả từ H2 để suy ra JDBC hint **luôn** vô hiệu, và cũng không dùng một driver chặn ghi để khẳng định annotation tự nó là security control.

### 3.2. Spring metadata không phải `Connection.isReadOnly()`

Hai giá trị có thể khác nhau:

```java
boolean springReadOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();

// Muốn đọc trạng thái connection: cần lấy connection đang bound
// qua DataSourceUtils, không mở bừa một connection mới từ pool.
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    boolean jdbcReadOnly = connection.isReadOnly();
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

Đây là **snippet** dùng trong method có `dataSource` được inject; cần import `Connection`, `DataSourceUtils`, các exception JDBC phù hợp. `springReadOnly` là **metadata đang active** của Spring; `jdbcReadOnly` là kết quả JDBC driver báo cáo trên connection. Giá trị `isReadOnly()` cũng **không xác minh tất cả quyền DML**. Một driver có thể trả `false` dù Spring metadata là `true` (H2), hoặc driver/DB có thể chặn ghi do cấu hình khác.

Muốn kiểm tra **enforcement**, hãy chạy integration test cố ý thử thao tác ghi trên bảng thử nghiệm không nhạy cảm rồi kiểm tra lỗi và trạng thái DB; đừng chỉ xem một boolean.

## 4. Read-only trong JPA/Hibernate là tối ưu hóa, không phải quy tắc SQL chung

Một service dùng Spring Data JPA thường khai báo:

```java
@Transactional(readOnly = true)
public List<CustomerDto> listCustomers() {
    return customerRepository.findAll()
        .stream()
        .map(CustomerDto::fromEntity)
        .toList();
}
```

Đây là snippet, không phải class chạy độc lập. Với Hibernate integration hiện đại, Spring có thể chuyển flush mode sang **`MANUAL`** trong read-only transaction để giảm công việc auto-flush/dirty checking; hành vi còn phụ thuộc phiên bản và cấu hình provider. Đây là **tối ưu hóa**. Nó không giống một lệnh từ chối SQL chung do Spring tạo ra.

Các trường hợp cần phân biệt:

- **Thay đổi thuộc tính một entity đang managed**: dưới chế độ read-only/flush optimization, Hibernate có thể không tự phát `UPDATE` vào DB khi transaction commit. Nếu không thấy SQL, nguyên nhân có thể là flush/dirty checking chứ không phải DB chặn ghi.
- **`EntityManager.createNativeQuery("UPDATE ...").executeUpdate()`** hoặc `JdbcTemplate.update(...)`: đây là các đường phát DML khác. Chúng **có thể** đi xuống JDBC/DB và thành công hoặc bị từ chối theo transaction mode/driver/permission.
- **`repository.save(entity)`** trong outer read-only transaction: gọi method này không tự bảo đảm đã ghi xuống DB; thao tác persist/merge/flush và transaction context quyết định có SQL và commit hay không. Không nên dựa vào chuyện “save chạy không lỗi” để kết luận ghi thành công.
- **`@Modifying`** trên một Spring Data JPA query dùng để đánh dấu query sửa dữ liệu. Nó **không tự biến một physical transaction read-only của caller thành read-write**. Thường cần transaction write thích hợp và cấu hình transaction boundary đúng.
- Một provider, flush mode, JDBC driver hoặc database có thể chủ động chặn một số thao tác; không thể suy ra tất cả trường hợp từ annotation.

Tài liệu **Spring Data JPA — Transactionality** nói rõ read-only flag **không thực hiện kiểm tra** để chắc chắn bạn không kích hoạt modifying query; nó là hint và có thể giúp provider tối ưu. Đây là luận điểm quan trọng hơn bất kỳ quan sát đơn lẻ nào từ unit test.

## 5. Ví dụ Java 17 chạy được: H2 ghi thành công dù transaction được đánh dấu read-only

Mục tiêu demo là phân biệt **metadata** với **thực thi việc chặn ghi** bằng kết quả DB thật. Chọn H2 vì JDBC driver này công khai bỏ qua `Connection.setReadOnly(boolean)`. Chương trình dùng Spring JDBC và `TransactionTemplate` để không phụ thuộc đến việc self-invocation của `@Transactional` có qua proxy hay không.

Ta thực hiện ba kịch bản liên tiếp:

1. **HINT_ONLY**: `TransactionTemplate.setReadOnly(true)`, in Spring metadata, gọi `INSERT`. Với H2, INSERT được commit thành công.
2. **APPLICATION_GUARD**: cũng `readOnly=true`, nhưng ứng dụng chủ động ném exception **trước khi** gọi INSERT. Không có hàng mới; đó là do guard trong code, **không phải H2 vừa thực thi JDBC hint**.
3. **READ_WRITE**: transaction bình thường, guard cho phép ghi và INSERT thành công.

Demo cố ý không bật `setEnforceReadOnly(true)` vì cơ chế đó phát một **SQL đặc thù DB** không được dùng làm giả định cho H2. Bài sẽ trình bày enforcement DB riêng ở phần tiếp theo.

### 5.1. Cấu trúc dự án

```text
spring-readonly-hint-demo/
├── pom.xml
└── src/main/java/com/example/readonly/Main.java
```

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-readonly-hint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
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

Spring JDBC bao gồm transaction infrastructure và `JdbcTemplate`. H2 là một database trong bộ nhớ; chương trình không cần Spring Boot, container hoặc server. `DriverManagerDataSource` đơn giản, không phải connection pool dùng cho production. JDK 17+ tương thích Spring Framework 6.2.

### 5.3. `src/main/java/com/example/readonly/Main.java`

```java
package com.example.readonly;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class Main {

    private static boolean springReadOnly() {
        return TransactionSynchronizationManager
                .isCurrentTransactionReadOnly();
    }

    // Đây là guard DO ỨNG DỤNG viết, không phải một cơ chế Spring
    // tự động kiểm tra mọi câu SQL.
    private static void requireWritable() {
        if (springReadOnly()) {
            throw new IllegalStateException("application blocked write");
        }
    }

    private static int count(JdbcTemplate jdbc) {
        Integer value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM read_only_events",
                Integer.class
        );
        return value;
    }

    public static void main(String[] args) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:readonly_hint;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(ds);
        jdbc.execute(
                "CREATE TABLE read_only_events (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
                "detail VARCHAR(80) NOT NULL)"
        );

        JdbcTransactionManager manager = new JdbcTransactionManager(ds);

        TransactionTemplate readOnly = new TransactionTemplate(manager);
        readOnly.setReadOnly(true);

        TransactionTemplate readWrite = new TransactionTemplate(manager);

        System.out.println("=== HINT_ONLY ===");
        readOnly.executeWithoutResult(status -> {
            System.out.println("springReadOnly=" + springReadOnly());
            jdbc.update(
                    "INSERT INTO read_only_events(detail) VALUES (?)",
                    "written despite hint"
            );
            System.out.println("writeInReadOnly=SUCCEEDED");
        });
        System.out.println("rows=" + count(jdbc));

        System.out.println("=== APPLICATION_GUARD ===");
        try {
            readOnly.executeWithoutResult(status -> {
                System.out.println("springReadOnly=" + springReadOnly());
                requireWritable(); // Ném lỗi trước câu INSERT.
                jdbc.update(
                        "INSERT INTO read_only_events(detail) VALUES (?)",
                        "guard should prevent this"
                );
            });
        } catch (IllegalStateException ex) {
            System.out.println("guard=" + ex.getMessage());
        }
        System.out.println("rows=" + count(jdbc));

        System.out.println("=== READ_WRITE ===");
        readWrite.executeWithoutResult(status -> {
            System.out.println("springReadOnly=" + springReadOnly());
            requireWritable();
            jdbc.update(
                    "INSERT INTO read_only_events(detail) VALUES (?)",
                    "regular write"
            );
        });
        System.out.println("rows=" + count(jdbc));
    }
}
```

**Tại sao đây là phép thử hợp lệ?**

- Hai `TransactionTemplate` sử dụng cùng `JdbcTransactionManager` và cùng datasource. `executeWithoutResult` mở transaction mới khi chưa có transaction ngoài.
- `isCurrentTransactionReadOnly()` cho biết **metadata của Spring đang nhận**; không phải điều kiện cho phép ghi của H2.
- H2 `Connection.setReadOnly(true)` được tài liệu JDBC công bố **bỏ qua tham số readOnly**. Vì không có enforcement khác, `JdbcTemplate.update` vẫn thực thi INSERT và transaction commit.
- Guard `requireWritable()` ngăn gọi INSERT **trên đường code được kiểm soát**. Một phương thức khác quên gọi guard vẫn có thể ghi; đây không phải một cơ chế phân quyền.
- Khi guard ném unchecked exception, `TransactionTemplate` rollback giao dịch đó; không có INSERT nào đã chạy trong nhánh này.
- `readWrite` để mặc định `readOnly=false`, nên guard cho phép. Cả hai bản ghi (nhánh hint và nhánh write) cuối cùng có trong H2.

### 5.4. Chạy và stdout dự kiến

Cài JDK 17+ và Maven, từ thư mục `spring-readonly-hint-demo` chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.readonly.Main
```

Những dòng do **chính chương trình** in ra; Maven hoặc logging thêm tùy môi trường không được liệt kê:

```text
=== HINT_ONLY ===
springReadOnly=true
writeInReadOnly=SUCCEEDED
rows=1
=== APPLICATION_GUARD ===
springReadOnly=true
guard=application blocked write
rows=1
=== READ_WRITE ===
springReadOnly=false
rows=2
```

**Cách diễn giải đúng:** Trong **môi trường H2 cụ thể của demo**, Spring readOnly metadata là true nhưng câu INSERT vẫn thành công. Nhánh thứ hai từ chối ghi nhờ **một kiểm tra viết trong ứng dụng**, không phải do database. Output đó **không có nghĩa** mọi database luôn chấp nhận SQL ghi dưới `@Transactional(readOnly=true)`; ví dụ PostgreSQL hoặc một JDBC driver khác có thể áp dụng chế độ read-only thật.

Nếu bạn thay H2 bằng production database, hãy giữ nguyên ý đồ bài test nhưng **không giữ cứng expected stdout**: cần đánh giá transaction manager, JDBC driver, DB session mode và quyền của connection.

## 6. Cơ chế chặn ghi ở cấp transaction của database

Nếu nghiệp vụ yêu cầu **database thực sự từ chối DML** trong một transaction, cần chọn cơ chế thực thi có bảo đảm từ DB. Một ví dụ với PostgreSQL (bảng thường, không phải temporary table) là:

```sql
BEGIN;
SET TRANSACTION READ ONLY;

SELECT current_setting('transaction_read_only');  -- 'on'

-- Ví dụ bảng permanent có sẵn trong schema:
INSERT INTO invoices(id, amount) VALUES (1001, 50);
-- PostgreSQL báo ERROR: cannot execute INSERT in a read-only transaction

ROLLBACK;
```

Đây là **SQL minh họa chạy trên PostgreSQL khi bảng invoices đã tồn tại**. PostgreSQL sẽ từ chối câu lệnh DML không được cho phép trong transaction read-only. Sau một SQL error, transaction có thể chuyển sang trạng thái failed và cần `ROLLBACK`. **Đừng nhầm** cơ chế này với `Connection.setReadOnly(true)` như một hint thuần trong mọi JDBC driver.

### 6.1. Dùng `setEnforceReadOnly(true)` với Spring JDBC

`DataSourceTransactionManager` hỗ trợ cấu hình `setEnforceReadOnly(true)`. Khi transaction definition là read-only và một **physical transaction mới** được bắt đầu, manager có thể chạy SQL:

```sql
SET TRANSACTION READ ONLY
```

Spring Javadoc nói SQL này được hiểu bởi **Oracle, MySQL và PostgreSQL**; hành vi/độ nghiêm ngặt dựa vào engine. Đây là lựa chọn **mạnh hơn JDBC hint**, nhưng **không phổ dụng cho mọi DB**. Có driver hoặc DB không hỗ trợ cú pháp SQL này; việc bật enforcement trên H2 demo không phải mặc định an toàn.

Một cách cấu hình cho Spring JDBC khi **đã xác nhận DB hỗ trợ**:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class JdbcTxConfig {
    @Bean
    public PlatformTransactionManager transactionManager(DataSource ds) {
        JdbcTransactionManager manager = new JdbcTransactionManager(ds);
        manager.setEnforceReadOnly(true);
        return manager;
    }
}
```

Code trên là **configuration class**; cần cung cấp bean `DataSource`, driver, credentials và repository phù hợp trong ứng dụng. Với manager này và lời gọi Spring `@Transactional(readOnly=true)` qua proxy **đang mở physical transaction mới**, Spring có thể yêu cầu DB vào transaction read-only mode; một câu INSERT bị cấm sẽ thất bại **ngay tại database**.

**Ba giới hạn phải ghi nhớ:**

1. `setEnforceReadOnly(true)` thuộc **`DataSourceTransactionManager` và subclass** như `JdbcTransactionManager`. Không giả định một cấu hình cùng tên/ý nghĩa tự tồn tại cho `JpaTransactionManager`, `JtaTransactionManager` hay mọi reactive manager.
2. Mức độ “cấm ghi” dựa vào SQL/DB: PostgreSQL read-only transaction có những chi tiết về temporary tables và loại lệnh được phép; không phải sandbox chống mọi side effect hoặc mọi hành vi SQL.
3. Nếu `REQUIRED` **tham gia một physical transaction đã có**, phần inner thường không chạy lại câu `SET TRANSACTION READ ONLY` để ghi đè transaction của caller. Muốn boundary mới với read-only mode riêng cần thiết kế propagation phù hợp và đánh giá đánh đổi.

### 6.2. `Connection.setReadOnly` vẫn có thể được driver thực thi mạnh

Không nên viết quy tắc “chỉ khi bật `setEnforceReadOnly(true)` thì PostgreSQL mới bao giờ chặn ghi”. Driver JDBC có thể dựa vào `Connection.setReadOnly(true)` để khởi tạo DB transaction ở chế độ read-only hoặc có cấu hình riêng. Vì thế **mặc định manager + driver cụ thể** có thể đã chặn ghi mà không dùng SQL enforcement của Spring.

Điều đúng trên mọi hệ thống là: **Spring annotation không tự hứa một guarantee cấm ghi độc lập với driver/database**. Muốn biết đã có enforcement hay chưa, phải kiểm tra **hành vi thật** của driver/version/database đang dùng.

### 6.3. Không dùng transaction read-only thay cho quyền truy cập

Ngay cả một DB read-only transaction mode đúng nghĩa cũng áp dụng **theo transaction/session**, tùy cú pháp và lifecycle. Trong ứng dụng lớn, một method khác có thể mở read-write transaction riêng, một job dùng tài khoản khác hoặc một hệ thống khác gọi DB trực tiếp.

Nếu mục tiêu là **bảo vệ dữ liệu không được sửa bởi một actor/service**, cần quyền database riêng biệt và least privilege, không chỉ annotation. Điều này đặc biệt quan trọng khi phân tách service query và service command.

## 7. Phân quyền DB: hàng rào chặn ghi thực tế hơn

Trong PostgreSQL, một ví dụ nguyên tắc về quyền của user/role chỉ đọc:

```sql
-- Chạy các thao tác quản trị này bằng một vai trò có quyền thích hợp.
CREATE ROLE app_reader LOGIN PASSWORD 'replace-with-secure-secret';

-- Ví dụ một bảng cụ thể:
GRANT USAGE ON SCHEMA public TO app_reader;
GRANT SELECT ON TABLE public.invoices TO app_reader;

-- Đừng cấp INSERT, UPDATE, DELETE, TRUNCATE cho app_reader.
-- Đồng thời kiểm tra quyền thừa kế từ role khác, PUBLIC và
-- quyền trên view/function/schema khác mà service có thể dùng.
```

Đây là **SQL mô tả chính sách**, không phải script cấp quyền production hoàn chỉnh. Role có thể nhận quyền gián tiếp từ group roles, quyền `PUBLIC`, chủ sở hữu đối tượng hoặc các function có quyền đặc biệt; cần audit chính xác trên hệ thống. Không lưu mật khẩu mẫu trong mã nguồn. Với những bảng mới hoặc schema khác, cần chính sách GRANT và default privileges tương ứng.

**Phân biệt mục tiêu:**

- **Read-only transaction mode:** áp dụng theo transaction đối với những lệnh DB cấm trong mode đó.
- **Read-only account/role:** áp dụng theo quyền truy cập đối tượng và đặc quyền của principal, ngay cả khi code quên `readOnly=true`.
- **App-level guard:** kiểm tra business intent trước SQL, giúp phản hồi sớm nhưng không thay thế DB permissions.

Nên dùng **defense in depth** khi cần bảo vệ quan trọng: tài khoản truy vấn ít quyền, transaction read-only được kiểm chứng, ứng dụng tách query/command rõ ràng và tests cố tình thử các đường ghi ngoài dự kiến.

## 8. `REQUIRED` và việc tham gia transaction có thể làm hint bị hiểu sai

Xét hai service Spring:

```java
@Service
class OuterService {
    private final ReaderService reader;

    OuterService(ReaderService reader) {
        this.reader = reader;
    }

    @Transactional(readOnly = false)
    public void updateAndRead() {
        // Outer đã mở physical transaction read-write.
        reader.list();   // Inner REQUIRED tham gia transaction ngoài.
    }
}

@Service
class ReaderService {
    @Transactional(readOnly = true)
    public void list() {
        // Không có physical transaction mới nếu tham gia outer.
        // Flag của inner không tự biến transaction ngoài thành read-only.
    }
}
```

Hai class là **snippet minh họa** chưa có imports/configuration. Khi cả hai `REQUIRED` (mặc định) và cùng transaction manager/resource, inner tham gia outer. **Physical transaction** đã có của outer quyết định trạng thái JDBC/DB; khai báo `readOnly=true` của inner **không tự tạo lệnh cấm ghi**.

Đảo lại tình huống:

```java
@Transactional(readOnly = true)
public void outerQuery() {
    writerService.performWrite(); // Inner REQUIRED mặc định readOnly=false.
}
```

Nếu `writerService.performWrite()` chỉ tham gia physical transaction read-only của outer, nó thường **không tự bật lại read-write**. Kết quả:

- H2 hint-only trong demo có thể vẫn cho ghi.
- DB có transaction read-only enforcement có thể từ chối DML.
- Spring có thể phát hiện một số mismatch nếu cấu hình `AbstractPlatformTransactionManager.setValidateExistingTransaction(true)`; chính sách này dùng để **validate joining transaction**, không phải SQL firewall toàn cục.

Đừng cho rằng một inner method khai báo `@Transactional(readOnly=false)` sẽ “mở khóa” transaction read-only ngoài.

### 8.1. Muốn độc lập về readOnly, cần boundary thật

Một inner `@Transactional(propagation = REQUIRES_NEW, readOnly = true)` có thể suspend outer và mở **physical transaction riêng**, dùng configuration read-only của chính nó. Đổi lại, Spring cần transaction/resource độc lập; outer có thể vẫn giữ connection/locks trong khi inner chạy, và kết quả commit/rollback của inner không gắn nguyên tử với outer.

Chỉ dùng khi cần transaction mới vì yêu cầu nghiệp vụ, không dùng như cách sửa chữa mặc định cho mô hình chia transaction chưa rõ.

### 8.2. Self-invocation làm annotation không có tác dụng

```java
@Service
class BrokenService {
    public void entry() {
        this.queryOnly(); // Bypass transaction proxy trong proxy mode.
    }

    @Transactional(readOnly = true)
    public void queryOnly() {
        // Không thể giả định một transaction read-only mới đã được mở.
    }
}
```

Đây là snippet. Với Spring AOP proxy mode, lời gọi `this.queryOnly()` không đi qua interceptor của proxy; `@Transactional` có thể không được áp dụng. Vì vậy một test chỉ gọi method trực tiếp trên `new BrokenService()` càng không có ý nghĩa để kiểm chứng DB read-only. Dùng service được Spring quản lý, lời gọi thông qua proxy, hoặc `TransactionTemplate`.

## 9. Phân biệt với timeout, isolation, rollback và “tự rollback khi có INSERT”

`@Transactional` có nhiều thuộc tính độc lập:

```java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED,
    timeout = 5,
    propagation = Propagation.REQUIRED
)
public Report loadReport() {
    // Mã minh họa trong service có repository và Report phù hợp.
    return repository.fetch();
}
```

- **`readOnly=true`:** ý định đọc, có thể ảnh hưởng driver/ORM/DB enforcement.
- **`isolation=...`:** quy tắc visibility và concurrency giữa các transaction.
- **`timeout=5`:** giới hạn thời gian theo transaction manager/resource; cách xử lý timeout phụ thuộc hạ tầng.
- **`propagation=REQUIRED`:** tham gia transaction đang có hoặc mở mới.

**Read-only không đồng nghĩa timeout ngắn, không bảo đảm snapshot nhất quán toàn transaction và không phải một rollback rule riêng.** Nếu DB chặn INSERT, thường SQL ném lỗi; exception đó có thể kích hoạt rollback theo chính sách transaction. Không phải Spring lặng lẽ “rollback riêng câu INSERT” rồi commit phần còn lại. Ngoài ra, một transaction có readOnly metadata không tự kích hoạt exception khi gọi `JdbcTemplate.update()` trong tất cả môi trường.

`readOnly=true` cũng không có nghĩa `autoCommit=true`. Spring vẫn có thể tạo một physical transaction chỉ đọc, commit/rollback nó như transaction bình thường; cơ chế commit không tự khiến mọi câu SQL bị cấm.

## 10. Tác dụng phụ ngoài database và những đường ghi bị bỏ sót

Ngay cả DB transaction được đánh dấu read-only **không quản lý tất cả tài nguyên trong ứng dụng**. Một method query có thể gây side effects:

- Ghi Redis cache hoặc cập nhật counter trong cache.
- Gửi HTTP request có tác dụng thay đổi dữ liệu hệ thống khác.
- Xuất message ra broker, publish domain event hoặc gọi email.
- Ghi file, gọi API lưu trạng thái, cập nhật search index.
- Khởi tạo tác vụ `@Async`/thread mới có transaction riêng.
- Gọi datasource thứ hai do transaction manager khác quản lý.
- Kích hoạt database function/procedure có quyền hoặc semantics đặc biệt.

Chặn JDBC write trên datasource A **không tự chặn** những side effect đó. Nếu “chỉ đọc” là **contract nghiệp vụ hay bảo mật xuyên hệ thống**, phải định nghĩa rõ những hành động nào được phép, tách role/credential và có kiểm soát riêng cho từng hệ.

**Đừng coi tên method `find...` hoặc annotation readOnly như kiểm chứng không có side effect.** Kiểm tra cả call graph và code thực sự thực thi.

## 11. Khi nào nên sử dụng mỗi lớp bảo vệ?

| Mục tiêu | Cơ chế nên ưu tiên | Kiểm chứng |
|---|---|---|
| Tối ưu truy vấn chỉ đọc | `@Transactional(readOnly=true)`, provider settings, transaction boundary ngắn | Profiling, SQL logs, flush mode, query plan |
| Truyền ý định read-only tới JDBC | `TransactionTemplate.setReadOnly(true)` hoặc annotation qua proxy | Spring metadata và transaction manager logs |
| DB phải từ chối DML **trong transaction này** | Read-only transaction mode được DB hỗ trợ, có thể cấu hình `setEnforceReadOnly(true)` với JDBC manager tương thích | Integration test cố ý INSERT/UPDATE/DELETE, kiểm tra rollback |
| Một ứng dụng/dịch vụ **không được phép ghi** vào bảng nhất định | Tài khoản DB riêng với quyền SELECT và không có quyền write/ownership tương ứng | Kiểm tra role grants và SQL ghi bị từ chối kể cả khi không có readOnly annotation |
| Ngăn bug ghi do code vô tình gọi command | Application guard, CQRS boundary, test hành vi | Test qua mọi code path; DB privilege vẫn bảo vệ đường bypass |
| Bảo vệ một báo cáo nhất quán nhiều SELECT | Chọn isolation/snapshot phù hợp DB và nghiệp vụ, có thể read-only transaction | Concurrent integration test của dữ liệu đọc và thời điểm snapshot |
| Tránh transaction treo quá lâu | Timeout hợp lý, query timeout và đo transaction duration | Runtime metrics, timeout tests, connection pool metrics |

Không có một checkbox read-only duy nhất thỏa mãn tất cả mục tiêu trên.

## 12. Thiết kế test đúng: chứng minh hint hay enforcement?

Một test tốt nên tách ba giả thuyết:

**Giả thuyết A — chỉ metadata:**

- Mở transaction read-only qua Spring.
- Kiểm tra `TransactionSynchronizationManager.isCurrentTransactionReadOnly() == true`.
- Kết luận hợp lệ: **Spring biết ý định**. Chưa thể kết luận DB sẽ từ chối DML.

**Giả thuyết B — DB enforcement:**

- Mở transaction read-only **mới** với đúng production driver/transaction manager/cấu hình.
- Thực hiện một INSERT vào bảng thử nghiệm mà DB account thường có quyền viết.
- Nếu DB từ chối do transaction read-only mode, xác nhận **lỗi từ DB**, transaction outcome và dữ liệu sau rollback.
- Chạy thêm test read-write bình thường trên cùng credential để phân biệt lỗi **do read-only mode** với lỗi **do không có quyền table**.

**Giả thuyết C — DB authorization:**

- Dùng credential read-only của service.
- Thử INSERT trong một **read-write transaction** hoặc session bình thường.
- Nếu DB từ chối do permission, xác nhận hàng rào phân quyền hoạt động **không phụ thuộc** annotation readOnly.
- Kiểm tra vai trò thừa kế, quyền trên schema/view/function và các con đường thực thi khác.

### 12.1. Tại sao unit test với mock không đủ?

Mock `JdbcTemplate` hoặc repository chỉ cho thấy code có gọi method ghi hay không. Nó không kiểm chứng driver có bỏ qua `Connection.setReadOnly` hay không, database có `SET TRANSACTION READ ONLY`, Hibernate có flush hay không hoặc credential có quyền DML không.

Đối với **guarantee cấm ghi**, test tích hợp với database đúng engine/version là bắt buộc. H2 hữu ích cho phản ví dụ **hint không tự cấm ghi**, không chứng minh cấu hình PostgreSQL hay MySQL production sẽ hành xử y hệt.

### 12.2. Một checklist test tích hợp cần có

1. Một lời gọi service **qua Spring proxy** (nếu dùng declarative transactions).
2. Một transaction **physical mới**, hoặc một test khác kiểm tra khi phương thức inner tham gia transaction outer.
3. Cùng JDBC datasource/manager với dữ liệu muốn bảo vệ.
4. Một INSERT, UPDATE và DELETE rõ ràng trên bảng thử nghiệm; kiểm tra từng loại theo DB.
5. Kiểm tra lỗi được ném ra và trạng thái transaction sau lỗi; không chỉ kiểm tra mã Java không ném exception.
6. Sau completion, mở transaction khác để xác nhận **không có thay đổi dữ liệu không mong muốn**.
7. Lặp test cho JDBC SQL trực tiếp, JPA entity update, native query, stored procedures nếu ứng dụng dùng các đường đó.
8. Kiểm tra database username/roles và cấu hình driver thực tế, không chỉ `application.yml`.
9. Với production connection pool, xác nhận trạng thái readOnly/isolation được reset đúng khi connection trả về pool sau transaction.
10. Nếu nghi ngờ read-only chỉ là hint, chạy case đối chứng với một transaction read-write thực để định vị nguồn gây lỗi.

## 13. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Giải thích có thể | Cách xác minh/khắc phục |
|---|---|---|
| Có `@Transactional(readOnly=true)` mà INSERT vẫn thành công | Driver/database coi JDBC readOnly là hint, ví dụ H2; hoặc annotation không áp dụng | Kiểm tra proxy, manager, datasource, DB mode và quyền |
| Hibernate entity đổi thuộc tính nhưng DB không cập nhật | Flush mode/dirty-check optimization có thể bỏ qua auto-flush | Bật SQL logging, kiểm tra flush mode, đừng nhầm với SQL enforcement |
| Native UPDATE bị DB từ chối trong readOnly transaction | Driver/DB đang thực thi transaction read-only mode | Đọc SQLSTATE/error code, kiểm tra DB mode và manager config |
| Method inner `readOnly=true` không có tác dụng | `REQUIRED` tham gia outer đã là read-write | Đặt ranh giới transaction đúng; hiểu join; kiểm thử |
| Method inner `readOnly=false` vẫn không ghi được | Đang tham gia transaction read-only của outer | Đừng cố “bật write” bằng annotation inner; thiết kế lại boundary |
| Có cờ Spring readOnly nhưng connection `isReadOnly()` false | Hệ driver không áp dụng hint hoặc trả trạng thái khác, ví dụ H2 | Test SQL thật, không dựa một boolean |
| Bật `setEnforceReadOnly(true)` thì lỗi cú pháp | DB không hỗ trợ `SET TRANSACTION READ ONLY` theo cú pháp manager | Kiểm tra DB dialect, docs, cấu hình riêng hoặc dùng permissions |
| Tài khoản read-only vẫn ghi được qua một function/view | Role/ownership/SECURITY DEFINER hoặc privilege thừa kế đặc biệt | Audit quyền theo database, không chỉ `GRANT SELECT` một bảng |
| `@Transactional(readOnly=true)` không chặn Redis/email | Ngoài phạm vi database transaction | Chính sách side effect riêng, outbox/role phù hợp |
| Read-only báo cáo vẫn đọc dữ liệu thay đổi giữa hai query | Read-only **không** tự đổi isolation/snapshot level | Chọn isolation phù hợp, test concurrent snapshots |
| Một request đọc làm nghẽn pool | Read-only vẫn có thể giữ connection, snapshot, lock tùy DB | Giảm thời gian transaction, đo pooling/slow query |
| Test pass trên H2, fail trên PostgreSQL | Driver/database thực thi read-only khác H2 | Dùng integration tests theo DB production |
| Đánh dấu method query readOnly nhưng self-invocation không tạo transaction | Lời gọi không qua Spring proxy | Gọi bean qua proxy hoặc dùng `TransactionTemplate` |
| Chỉ chỉnh `setReadOnly` trên connection mượn từ pool | Can thiệp trạng thái ngoài transaction manager; khó reset | Để Spring quản lý lifecycle và reset, không tự điều khiển bừa |

## 14. Các câu hỏi tự kiểm tra

1. **`@Transactional(readOnly=true)` có tự động phân tích mọi SQL và cấm INSERT không?** — Không. Nó là transaction attribute/hint; enforcement phụ thuộc các tầng bên dưới.
2. **Vì sao demo H2 có `springReadOnly=true` mà INSERT vẫn thành công?** — H2 công bố JDBC `setReadOnly(true)` bỏ qua tham số; Spring metadata vẫn là true.
3. **Hibernate MANUAL flush mode có phải quyền SELECT-only của database không?** — Không. Nó là tối ưu hóa/hành vi ORM, không phải DB permission.
4. **Một DB có thể chặn INSERT dù Spring chỉ gọi `setReadOnly(true)` không?** — Có thể. Driver có thể chuyển hint thành transaction read-only thực sự; test trên driver cụ thể.
5. **`setEnforceReadOnly(true)` làm gì với DataSourceTransactionManager?** — Trong DB tương thích, manager phát `SET TRANSACTION READ ONLY` khi mở physical transaction read-only mới.
6. **Bật `setEnforceReadOnly(true)` có áp dụng được cho mọi DB/transaction manager không?** — Không; có giới hạn cú pháp và loại manager.
7. **Inner REQUIRED(readOnly=true) trong outer REQUIRED(readOnly=false) có nâng quyền chặn ghi không?** — Không; inner thường tham gia transaction ngoài.
8. **Bảo đảm service query không ghi DB dù quên annotation bằng cách nào?** — Dùng DB credential không có quyền ghi cần thiết và audit quyền, kết hợp với app guard khi phù hợp.
9. **Read-only transaction có chặn HTTP POST hoặc Redis SET từ method Java không?** — Không; đó là tài nguyên khác, cần chính sách riêng.
10. **Chỉ quan sát `Connection.isReadOnly()==true` đã chứng minh chặn mọi lệnh ghi chưa?** — Chưa. Cần integration test DML và kiểm tra permission/mode thực tế.

## 15. Tóm tắt quyết định kỹ thuật

- **Chỉ tối ưu hóa truy vấn:** dùng `@Transactional(readOnly=true)`, đo bằng query/flush metrics; đừng dựa vào annotation để kiểm soát bảo mật.
- **Cần từ chối DML trong transaction:** chọn transaction read-only mode mà DB hỗ trợ; với Spring JDBC có thể cân nhắc `setEnforceReadOnly(true)`, kiểm tra driver/database cụ thể.
- **Cần chống ghi ngoài ý muốn từ một service/query actor:** dùng tài khoản DB read-only với quyền tối thiểu; annotation và guard chỉ là lớp bổ sung.
- **Cần bảo vệ toàn bộ side effects của một business flow:** định nghĩa ranh giới business, tách các external resources, test từng đường thực thi; một JDBC readOnly flag không thể giải quyết tất cả.
- **Cần đúng trong Spring AOP:** xác minh lời gọi qua proxy, propagation và physical transaction thực sự mới; isolation/readOnly/timeout ở method inner không tự ghi đè outer đang hoạt động.

**Kết luận:** `readOnly=true` là một khai báo **rất có giá trị về ngữ nghĩa và tối ưu hiệu năng**, nhưng “read-only **hint**” và “**write prohibited**” là hai khẳng định khác nhau. Chỉ gọi là “đã chặn ghi” khi đã xác định rõ **component nào từ chối ghi, trong phạm vi nào, và đã kiểm chứng lỗi trên dữ liệu/driver/database thật**.

## 16. Tài liệu tham khảo

- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Data JPA — Transactionality (read-only là hint, Hibernate MANUAL flush): https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Framework — `DataSourceTransactionManager`, `setEnforceReadOnly`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework — `TransactionSynchronizationManager`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — `AbstractPlatformTransactionManager`, `validateExistingTransaction`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- H2 JDBC `JdbcConnection.setReadOnly` — tham số readOnly bị bỏ qua: https://h2database.github.io/javadoc/org/h2/jdbc/JdbcConnection.html
- Java JDBC `Connection.setReadOnly` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html#setReadOnly(boolean)
- PostgreSQL — `SET TRANSACTION` và READ ONLY mode: https://www.postgresql.org/docs/current/sql-set-transaction.html
- PostgreSQL — Database Roles and Privileges: https://www.postgresql.org/docs/current/user-manag.html
