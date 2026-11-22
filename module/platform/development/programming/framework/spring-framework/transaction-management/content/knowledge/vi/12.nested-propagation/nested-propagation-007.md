# Giới hạn savepoint đối với trạng thái persistence context JPA

## 1. Kết luận quan trọng

**JDBC savepoint quay lại trạng thái dữ liệu trong transaction của database; nó không quay lại trạng thái của JPA persistence context.** Nếu một đoạn code thay đổi hoặc nạp entity managed sau savepoint, rồi rollback về savepoint, `EntityManager` không tự phục hồi identity map, entity fields, dirty-check snapshots, collections, queued actions hoặc lifecycle state về thời điểm trước savepoint.

Đây là cốt lõi của chủ đề **NESTED và savepoint → Giới hạn savepoint đối với trạng thái persistence context JPA**. Cần phân biệt hai vấn đề:

1. **Có thực thi được NESTED hay không?** `JpaTransactionManager` mặc định đặt `nestedTransactionAllowed=false`. Nếu chủ động bật flag này, nested vẫn cần `JpaDialect` và JDBC driver hỗ trợ savepoint. Flag không tự biến JPA thành hệ quản lý nested transaction.
2. **Nếu JDBC rollback được tới savepoint thì sao?** DB có thể phục hồi dữ liệu thành công nhưng entity managed vẫn lưu giá trị cũ trong RAM. Spring/JPA không có bảo đảm tự rewind toàn bộ persistence context theo savepoint.

Spring Framework Javadoc cho `JpaTransactionManager` nói thẳng rằng savepoints chỉ áp dụng vào JDBC connection, không áp dụng cho các cached entity objects và context liên quan; bản thân JPA không hỗ trợ nested transactions với semantics như vậy.

Bài này cung cấp khái niệm, luồng thực thi, tình huống dễ sai, một dự án Java 17+/Spring Boot 3.3.5/JPA/JDBC/H2 hoàn chỉnh và integration tests chứng minh hai kiểu quan sát. **Ví dụ JDBC savepoint thủ công bên trong một JPA transaction chỉ phục vụ mục đích học**, không phải lời khuyên làm như vậy trong production.

## 2. Hai thế giới state: JDBC và JPA

### 2.1. Savepoint thuộc JDBC transaction

Một transaction JDBC trên một connection có thể đánh dấu vị trí để rollback một phần:

```java
// Snippet minh họa với Connection đã ở trong transaction.
Savepoint mark = connection.setSavepoint("before_optional_step");
doSomeSqlOnTheSameConnection();
connection.rollback(mark);
connection.releaseSavepoint(mark);
```

`Savepoint` nằm trong `java.sql`. Đoạn mã trên không phải class chạy độc lập: cần `Connection connection`, method `doSomeSqlOnTheSameConnection()` và xử lý `SQLException`. Cần DB/driver hỗ trợ savepoints, connection đúng và transaction đang active. `rollback(mark)` đảo ngược những SQL changes thuộc transaction trên cùng connection **sau** điểm đánh dấu.

```text
Physical transaction T (một JDBC connection)
  ├─ UPDATE A (trước savepoint)
  ├─ SAVEPOINT S
  ├─ UPDATE B
  ├─ UPDATE C
  ├─ ROLLBACK TO S           -> hủy B và C trên DB
  ├─ UPDATE D
  └─ COMMIT T                -> A và D còn lại, nếu commit thành công
```

Không có physical transaction thứ hai. Nếu outer T sau đó rollback toàn bộ, cả A và D cũng bị rollback. Ngoài ra, `ROLLBACK TO SAVEPOINT` không đảo ngược HTTP call, email, message đã publish, sequence đã cấp số hay tác dụng nằm ngoài tài nguyên DB theo cách portable.

### 2.2. Persistence context thuộc EntityManager

Trong JPA, một `EntityManager` quản lý một persistence context gồm các entity objects và thông tin để đồng bộ với DB:

- **Identity map:** một entity identity đã managed thường được trả lại dưới dạng cùng một object khi gọi `em.find(type,id)` lần nữa.
- **Managed state:** field values và mối quan hệ đang nằm trong Java memory.
- **Dirty checking:** provider theo dõi thay đổi, có thể tạo `UPDATE` trong lúc flush/commit.
- **Write-behind:** `persist`/`setXxx` không nhất thiết tạo SQL tức thời.
- **Loaded collections, snapshots, version và action queue:** là phần của cách provider duy trì/đồng bộ entity state.
- **Transaction-scoped first-level cache:** có vòng đời gắn với `EntityManager`, không phải một JDBC savepoint.

Khả năng kiểm soát savepoint **không đồng nghĩa** có API JPA tự sao chép/restore toàn bộ những trạng thái trên. JPA không định nghĩa các method sau:

```java
// Pseudo-code: KHÔNG tồn tại trong jakarta.persistence.EntityManager.
entityManager.createSavepoint();
entityManager.restorePersistenceContextToSavepoint();
```

Không được dùng pseudo-code trên như thư viện thật.

### 2.3. Hình dung một transaction, hai ảnh trạng thái

```text
                Outer transaction
                         |
            +------------+------------+
            |                         |
       JDBC connection           EntityManager
       DB transaction T          persistence context
            |                         |
         SAVEPOINT S             Account#1 managed
            |                         |
         UPDATE row              Account.balance = 250
            |                         |
       ROLLBACK TO S                   |
            |                         |
       DB balance = 100          object vẫn có thể 250
            |                         |
            +-------------+-----------+
                          |
                cùng một nghiệp vụ nhưng
                hai kết quả đọc khác nhau
```

Đây không phải lỗi của JDBC savepoint. Nó hoàn thành nhiệm vụ trên DB. Điều sai là suy luận nó cũng đã khôi phục state mà `EntityManager` quản lý ở JVM.

## 3. `REQUIRED`, `NESTED`, `REQUIRES_NEW` khác nhau thế nào?

| Propagation | Đang có outer transaction | Số physical transaction | Ý nghĩa đối với JPA |
| --- | --- | --- | --- |
| `REQUIRED` | Tham gia transaction ngoài | Thường là một | Dùng transaction/persistence context theo manager; lỗi inner có thể đánh dấu rollback-only |
| `NESTED` | Thường tạo JDBC savepoint trong transaction hiện có | Một | Chỉ nếu manager/resource hỗ trợ; **không** snapshot JPA context |
| `REQUIRES_NEW` | Tạm treo outer và mở transaction độc lập | Hai trong lúc lồng nhau | Inner có boundary độc lập; với manager phù hợp thường có EntityManager scope riêng |

`@Transactional(propagation = Propagation.NESTED)` là **một yêu cầu**, không phải bảo đảm tài nguyên hỗ trợ savepoint. Nếu không có outer transaction, `NESTED` theo manager thường hành xử giống bắt đầu transaction mới; vì vậy phải có outer transaction khi test việc từ chối nested.

Ví dụ syntax:

```java
@Transactional(propagation = Propagation.NESTED)
public void optionalStep() {
    // ...
}
```

Đây là method minh họa, cần class Spring bean và import thích hợp. Nó không tự có nghĩa là nested JPA persistence context.

### 3.1. Tại sao `JpaTransactionManager` cẩn trọng?

Javadoc của `JpaTransactionManager` chỉ ra `nestedTransactionAllowed` mặc định là `false`, bởi nested savepoints chỉ áp dụng cho JDBC connection, không áp dụng cho cached JPA entity objects. Có thể bật flag **nếu muốn nested cho JDBC access code tham gia JPA transaction**, nhưng điều đó còn tùy `JpaDialect`/driver hỗ trợ.

```java
JpaTransactionManager manager = new JpaTransactionManager();
boolean allowedByDefault = manager.isNestedTransactionAllowed();
// false trên Spring Framework 6.x
```

Snippet này chỉ quan sát cấu hình, chưa có `EntityManagerFactory` để manager thật sự chạy. Ví dụ cấu hình:

```java
JpaTransactionManager manager = new JpaTransactionManager(emf);
manager.setDataSource(dataSource);
manager.setNestedTransactionAllowed(true);
```

Cần phân biệt rõ: dòng cuối **chỉ bật phép thử capability**, không mở thêm tính năng nested semantics của JPA. Nếu `JpaDialect` không cung cấp `SavepointManager` thích hợp, Spring vẫn có thể ném `NestedTransactionNotSupportedException`. Ngay cả khi savepoint được tạo, rollback không làm JPA persistence context tự đồng bộ.

### 3.2. Bốn điều kiện độc lập

| Điều kiện | Kiểm tra cách nào? | Kết luận |
| --- | --- | --- |
| DB và JDBC driver hỗ trợ savepoint | `DatabaseMetaData.supportsSavepoints()`, integration test | Chỉ chứng minh khả năng JDBC |
| Manager cho phép nested | `JpaTransactionManager.isNestedTransactionAllowed()` | Chỉ chứng minh cờ cấu hình |
| `JpaDialect` cung cấp savepoint manager trên transaction | Xem implementation và test runtime | Quyết định việc Spring `NESTED` có chạy được |
| EntityManager restore managed objects sau savepoint | Không có contract JPA portable | **Không được suy luận từ ba điều kiện trên** |

Một ứng dụng dùng JPA + Hibernate + H2 có thể có DB hỗ trợ savepoint, nhưng `@Transactional(NESTED)` vẫn bị từ chối bởi manager hoặc dialect. Và kể cả khi savepoint dùng được với JDBC, `em.find()` vẫn có thể trả stale managed entity.

### 3.3. Cảnh báo khi đổi transaction manager

`DataSourceTransactionManager` thường hỗ trợ `NESTED` qua JDBC savepoints trên một `DataSource` khi driver hỗ trợ. Nhưng nó **không mặc nhiên thay `JpaTransactionManager` trong việc điều phối `EntityManager`/JPA flush/lifecycle**. Không đổi manager sang JDBC chỉ để một annotation ngừng ném exception nếu application vẫn cần JPA transaction resource.

## 4. Một tình huống cụ thể: DB rollback nhưng JPA vẫn thấy giá trị sau savepoint

Giả sử bảng `accounts` ban đầu là:

```text
id | balance
---+--------
1  | 100
```

Trong outer JPA transaction, code dùng **đúng JDBC connection tham gia transaction**:

1. Tạo savepoint `S`, khi DB có `balance=100`.
2. Chạy JDBC `UPDATE accounts SET balance=250 WHERE id=1`.
3. **Lần đầu trong persistence context này**, gọi `entityManager.find(Account.class,1L)`. JPA nạp giá trị `250` và giữ object managed.
4. JDBC rollback đến `S`; DB quay về `balance=100`.
5. Gọi `entityManager.find(Account.class,1L)` lần nữa. Identity map thường trả lại managed object đã nạp, field vẫn `250`.
6. Dùng `JdbcTemplate` SELECT trên transaction để đọc DB, kết quả `100`.

```text
Thời điểm                JDBC DB       JPA managed Account
---------------------------------------------------------
Trước savepoint           100          chưa nạp
Sau JDBC UPDATE           250          chưa nạp
Sau em.find               250          250
Sau ROLLBACK TO S         100          250
Sau em.find lần nữa       100          250 (từ context)
Sau JDBC SELECT           100          250 (vẫn còn ở RAM)
```

**Kết luận:** một thành công của `Connection.rollback(savepoint)` không đồng nghĩa entity đang managed đã được refresh. Đây là lỗi mô hình tư duy nguy hiểm: business logic ở outer có thể so sánh/nghiệm thu dữ liệu dựa trên `250` dù DB đã quay về `100`.

### 4.1. Một rủi ro thứ hai: dirty state chưa flush

```java
Account account = entityManager.find(Account.class, 1L);
account.setBalance(250); // Java memory dirty; SQL có thể chưa chạy.
```

Nếu chỉ đổi field trong persistence context và chưa `flush`, **database chưa có thao tác SQL đó để savepoint rollback**. Entity vẫn có state `250`. Khi outer transaction commit, provider có thể flush các thay đổi đang chờ xuống DB, khiến thao tác bạn tưởng đã “hủy” lại được lưu.

Nếu đã flush trước rồi mới rollback JDBC về savepoint, object và dirty-check snapshots trong provider vẫn có thể không khớp DB; lần flush kế tiếp là vấn đề phụ thuộc provider/mapping/transaction state. Không hứa một kết quả deterministic trên mọi Hibernate/JPA version.

### 4.2. Các biến thể còn nguy hiểm hơn

Savepoint cũng không tự phục hồi:

- Entity `persist()` và trạng thái managed/identifier sau SQL INSERT bị rollback.
- `@Version` optimistic-locking version và snapshot đang được provider dùng.
- Relations/collections đã thay đổi trong RAM.
- Queued deletes, updates, lifecycle callbacks hoặc domain events.
- Entity bị remove/merge trong persistence context.
- Second-level cache và query cache có cấu hình riêng, nếu ứng dụng sử dụng.

Không phải mọi tình huống luôn gây lỗi giống nhau. Điểm bất biến là **không có cơ chế JPA portable** để restore toàn bộ persistence context về một JDBC savepoint.

## 5. Vì sao `flush`, `refresh` và `clear` không phải rollback JPA theo savepoint?

| API | Ý nghĩa | Rủi ro khi dùng sau JDBC savepoint rollback |
| --- | --- | --- |
| `entityManager.flush()` | Đồng bộ các pending JPA changes xuống DB | Có thể ghi lại dữ liệu dirty; không tải lại state từ DB |
| `entityManager.refresh(entity)` | Tải lại entity managed từ DB | Chỉ targeted entity; có thể overwrite unflushed changes hợp lệ, cascade và phát sinh lỗi |
| `entityManager.clear()` | Detach mọi managed entities | Bỏ unflushed changes của cả outer transaction |
| `entityManager.detach(entity)` | Detach một entity | Không restore các entity khác, có thể mất pending changes |
| `entityManager.find(type,id)` | Đọc theo identity | Có thể trả object đã managed, không nhất thiết chạy SELECT |
| `entityManager.lock(...)` | Lock entity theo JPA contract | Không restore persistence-context snapshot |

Jakarta Persistence API mô tả `refresh(entity)` là thao tác đọc lại state từ DB, ghi đè các thay đổi chưa flush của entity; `clear()` detach toàn bộ managed entities và những unflushed changes sẽ không được làm persistent. Đây không phải “rollback một phần” an toàn cho mọi entity.

**Trong một thí nghiệm read-only với một entity chưa bị dirty theo ý định nghiệp vụ**, `refresh` có thể giải thích cách đồng bộ **một object** về DB state sau savepoint. Tuy nhiên, trong một outer transaction có nhiều managed entities đang có thay đổi hợp lệ, `clear()` hoặc refresh hàng loạt có thể gây mất dữ liệu/ngữ nghĩa không thể lường trước. Cách an toàn khi persistence context không còn đáng tin thường là **rollback toàn bộ JPA transaction, kết thúc context và bắt đầu transaction mới**.

## 6. Thực hành chạy được — Spring JPA, JDBC và savepoint H2

Bộ project này **cố ý tách hai hành vi**:

- `@Transactional(NESTED)` qua `JpaTransactionManager` mặc định bị từ chối khi đang có outer transaction. Test không giả vờ JPA nested transaction đã chạy.
- Một **JDBC savepoint thủ công** bên trong outer transaction do `JpaTransactionManager` quản lý cho thấy DB có thể rollback một phần trong khi JPA-managed object giữ state cũ. Đây là **thí nghiệm có kiểm soát**, không phải một mẫu production nên áp dụng.

Dự án dùng **Java 17+, Spring Boot 3.3.5 (Spring Framework 6.1.x), Hibernate JPA, JDBC và H2**, Gradle/JUnit 5.

### 6.1. Cấu trúc tệp

```text
jpa-savepoint-limits/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/jpasavepoint/
    │   │   ├── JpaSavepointApplication.java
    │   │   ├── JpaTransactionConfiguration.java
    │   │   ├── Account.java
    │   │   ├── NestedAttemptService.java
    │   │   └── SavepointScenarios.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/jpasavepoint/
        └── JpaSavepointIntegrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'jpa-savepoint-limits'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot dependency management cung cấp Spring, Hibernate, JPA API, H2 và JUnit tương thích; không chạy `javac` thuần nếu chưa cấu hình classpath ngoài JDK.

### 6.2. Cấu hình database

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:jpa_savepoints;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
spring.jpa.hibernate.ddl-auto=none
spring.jpa.open-in-view=false
spring.datasource.hikari.maximum-pool-size=5
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance INTEGER NOT NULL
);
```

Chủ động tắt JPA schema generation, vì `schema.sql` tạo bảng. Trong test, account 1 bắt đầu `balance=100`, account 2 bắt đầu `balance=10`. H2 được chọn vì có JDBC savepoint; cần kiểm thử lại trên DB production của ứng dụng nếu muốn áp dụng kết luận về driver/flush/locking.

`src/main/java/com/example/jpasavepoint/JpaSavepointApplication.java`:

```java
package com.example.jpasavepoint;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaSavepointApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaSavepointApplication.class, args);
    }
}
```

### 6.3. Một transaction manager JPA rõ ràng

`src/main/java/com/example/jpasavepoint/JpaTransactionConfiguration.java`:

```java
package com.example.jpasavepoint;

import javax.sql.DataSource;
import jakarta.persistence.EntityManagerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class JpaTransactionConfiguration {
    @Bean("transactionManager")
    public JpaTransactionManager transactionManager(
            EntityManagerFactory emf, DataSource dataSource) {

        JpaTransactionManager manager = new JpaTransactionManager(emf);
        manager.setDataSource(dataSource);
        // Không bật nestedTransactionAllowed: mặc định là false.
        return manager;
    }
}
```

Ở đây có đúng một transaction manager bean. `@EnableTransactionManagement` kích hoạt proxy transaction advice. `JpaTransactionManager` quản lý `EntityManagerFactory` của Hibernate đồng thời biết cùng `DataSource` được dùng cho `JdbcTemplate`. Điều này cho phép code JDBC dùng Spring `DataSourceUtils` tham gia transaction-bound connection trong fixture.

**Không thay manager này bằng `DataSourceTransactionManager` rồi giả định JPA vẫn được điều phối tương đương.** Tài nguyên và semantics khác nhau.

### 6.4. JPA entity và bean inner có NESTED

`src/main/java/com/example/jpasavepoint/Account.java`:

```java
package com.example.jpasavepoint;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "balance", nullable = false)
    private int balance;

    protected Account() {
    }

    public Long getId() {
        return id;
    }

    public int getBalance() {
        return balance;
    }

    public void setBalance(int balance) {
        this.balance = balance;
    }
}
```

`src/main/java/com/example/jpasavepoint/NestedAttemptService.java`:

```java
package com.example.jpasavepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NestedAttemptService {
    private final JdbcTemplate jdbc;

    public NestedAttemptService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void nestedChange() {
        // Khi outer JPA transaction đang active và flag nested=false,
        // Spring từ chối NESTED trước khi vào method này.
        jdbc.update("UPDATE accounts SET balance = 900 WHERE id = 1");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void independentChangeThenFail() {
        jdbc.update("UPDATE accounts SET balance = 900 WHERE id = 1");
        throw new IllegalStateException("Independent step failed");
    }
}
```

`NestedAttemptService` là **bean riêng** để outer service gọi qua proxy. Nếu gọi `this.nestedChange()` bên trong cùng một object trong proxy mode, interceptor không chạy cho method inner và test sẽ không chứng minh điều cần chứng minh.

### 6.5. Service khảo sát JDBC rollback và JPA cache

`src/main/java/com/example/jpasavepoint/SavepointScenarios.java`:

```java
package com.example.jpasavepoint;

import java.sql.Connection;
import java.sql.Savepoint;
import java.sql.SQLException;

import javax.sql.DataSource;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SavepointScenarios {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;
    private final NestedAttemptService nested;

    @PersistenceContext
    private EntityManager entityManager;

    public SavepointScenarios(
            JdbcTemplate jdbc,
            DataSource dataSource,
            NestedAttemptService nested) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
        this.nested = nested;
    }

    public record Snapshot(
            int atInitialJpaLoad,
            int inJpaContextAfterRollback,
            int inDatabaseAfterRollback) {
    }

    @Transactional
    public void nestedAnnotationRejectedByDefault() {
        jdbc.update("UPDATE accounts SET balance = 20 WHERE id = 2");
        nested.nestedChange();
    }

    @Transactional
    public void jdbcOnlySavepointKeepsEarlierOuterWork() {
        jdbc.update("UPDATE accounts SET balance = 20 WHERE id = 2");

        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            Savepoint point = connection.setSavepoint("jdbc_only");
            jdbc.update("UPDATE accounts SET balance = 900 WHERE id = 1");
            connection.rollback(point);
            connection.releaseSavepoint(point);
        } catch (SQLException ex) {
            throw new IllegalStateException("Savepoint operation failed", ex);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    @Transactional
    public Snapshot staleManagedEntityAfterRollback() {
        return snapshotAfterSavepoint(false);
    }

    @Transactional
    public Snapshot refreshedEntityAfterRollback() {
        return snapshotAfterSavepoint(true);
    }

    private Snapshot snapshotAfterSavepoint(boolean refresh) {
        // Chỉ là thí nghiệm về JDBC state và JPA first-level cache.
        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            Savepoint point = connection.setSavepoint("probe");
            jdbc.update("UPDATE accounts SET balance = 250 WHERE id = 1");

            // Lần đầu nạp Account#1 trong persistence context này.
            Account managed = entityManager.find(Account.class, 1L);
            int atLoad = managed.getBalance();

            connection.rollback(point);
            connection.releaseSavepoint(point);

            if (refresh) {
                // An toàn trong thí nghiệm vì không có dirty
                // changes hợp lệ nào ở entity này cần giữ.
                entityManager.refresh(managed);
            }

            int inContext =
                    entityManager.find(Account.class, 1L).getBalance();
            Integer inDatabase = jdbc.queryForObject(
                    "SELECT balance FROM accounts WHERE id = 1",
                    Integer.class);

            return new Snapshot(atLoad, inContext, inDatabase);
        } catch (SQLException ex) {
            throw new IllegalStateException("Savepoint operation failed", ex);
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }

    @Transactional
    public void independentInnerRollback() {
        jdbc.update("UPDATE accounts SET balance = 20 WHERE id = 2");
        try {
            nested.independentChangeThenFail();
        } catch (IllegalStateException expected) {
            // REQUIRES_NEW rollback transaction riêng.
        }
    }

    @Transactional
    public void fullTransactionRollback() {
        jdbc.update("UPDATE accounts SET balance = 20 WHERE id = 2");
        throw new IllegalStateException("Abort entire transaction");
    }
}
```

Giải thích code:

- `@PersistenceContext` inject shared proxy trỏ đến `EntityManager` của transaction hiện hành.
- `DataSourceUtils.getConnection(dataSource)` lấy connection Spring đang bind vào transaction, không phải mở connection ngoài transaction.
- `JdbcTemplate` truy cập cùng `DataSource` nên SQL trong demo dùng resource tương ứng.
- `connection.rollback(point)` hoàn tác JDBC UPDATE trên account 1. Nhưng JPA đã load object với `250` sau UPDATE đó và giữ object managed.
- `entityManager.find` lần thứ hai có thể trả object cached `250` mà không truy vấn lại DB; `JdbcTemplate` SELECT sau rollback trả `100`.
- Nhánh `refresh=true` làm mới **một entity** để minh họa, không khôi phục toàn bộ context.
- Mọi method có `@Transactional` được gọi qua Spring proxy bên ngoài. Helper private không tạo transaction boundary riêng.
- `DataSourceUtils.releaseConnection` không đóng connection còn bound với transaction đang active; transaction manager chịu trách nhiệm cleanup sau boundary.
- SQLException từ savepoint được chuyển thành runtime exception để whole transaction rollback trong fixture. Nếu resource thật có lỗi nghiêm trọng, không cố tiếp tục trong context có thể đã hỏng.

**Đặc biệt:** việc dùng JDBC savepoint thủ công ngay trong transaction JPA này là một **anti-pattern được tạo có chủ ý cho bài học**, không phải giải pháp chuẩn để thực thi nested JPA.

### 6.6. Integration tests

`src/test/java/com/example/jpasavepoint/JpaSavepointIntegrationTest.java`:

```java
package com.example.jpasavepoint;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.NestedTransactionNotSupportedException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class JpaSavepointIntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private SavepointScenarios scenarios;

    @Autowired
    private JpaTransactionManager transactionManager;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM accounts");
        jdbc.update("INSERT INTO accounts(id, balance) VALUES (1, 100)");
        jdbc.update("INSERT INTO accounts(id, balance) VALUES (2, 10)");
    }

    private int balance(long id) {
        Integer value = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, id);
        return value;
    }

    @Test
    void nestedFlagDefaultsToFalseForJpaManager() {
        assertFalse(transactionManager.isNestedTransactionAllowed());
    }

    @Test
    void nestedRequestInsideExistingJpaTransactionIsRejected() {
        assertThrows(NestedTransactionNotSupportedException.class,
                scenarios::nestedAnnotationRejectedByDefault);

        assertEquals(100, balance(1));
        assertEquals(10, balance(2));
    }

    @Test
    void jdbcSavepointRevertsOnlyWorkAfterSavepoint() {
        scenarios.jdbcOnlySavepointKeepsEarlierOuterWork();

        assertEquals(100, balance(1));
        assertEquals(20, balance(2));
    }

    @Test
    void managedEntityCanRemainStaleAfterJdbcRollback() {
        var snapshot = scenarios.staleManagedEntityAfterRollback();

        assertEquals(250, snapshot.atInitialJpaLoad());
        assertEquals(250, snapshot.inJpaContextAfterRollback());
        assertEquals(100, snapshot.inDatabaseAfterRollback());
        assertEquals(100, balance(1));
    }

    @Test
    void targetedRefreshReloadsThisOneEntityInTheFixture() {
        var snapshot = scenarios.refreshedEntityAfterRollback();

        assertEquals(250, snapshot.atInitialJpaLoad());
        assertEquals(100, snapshot.inJpaContextAfterRollback());
        assertEquals(100, snapshot.inDatabaseAfterRollback());
        assertEquals(100, balance(1));
    }

    @Test
    void requiresNewInnerRollbackDoesNotUndoOuterJdbcUpdate() {
        scenarios.independentInnerRollback();

        assertEquals(100, balance(1));
        assertEquals(20, balance(2));
    }

    @Test
    void outerRuntimeExceptionRollsBackEverything() {
        assertThrows(IllegalStateException.class,
                scenarios::fullTransactionRollback);

        assertEquals(100, balance(1));
        assertEquals(10, balance(2));
    }
}
```

**Bảy test** kiểm tra: default nested flag, từ chối `NESTED`, rollback JDBC savepoint, JPA managed state lệch DB, refresh targeted, `REQUIRES_NEW` và rollback toàn bộ.

Không đặt `@Transactional` lên test class. Nếu test tự mở transaction, service `REQUIRED` có thể chỉ tham gia transaction của test, còn kiểm tra “commit” chỉ đang nhìn state chưa commit. Ở đây các lệnh `balance(...)` chạy **sau khi proxy kết thúc lời gọi service** nên có ý nghĩa kiểm tra state cuối trong fixture.

### 6.7. Chạy và đọc kết quả

Với Gradle Wrapper:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

Nếu project được tạo thủ công mà chưa có wrapper, dùng Gradle đã cài phiên bản tương thích với Boot 3.3.5 để tạo wrapper hoặc chạy `gradle test`. Kết quả kỳ vọng của fixture là **7 test pass**; không có stdout Java cố định của JUnit tests. Xem `build/reports/tests/test/index.html` sau khi chạy. Bộ mã được **giải thích và kiểm tra tĩnh**, không có tuyên bố rằng test đã thực sự chạy trên thiết bị của bạn.

| Tình huống | Result kỳ vọng |
| --- | --- |
| `JpaTransactionManager` mặc định | `nestedTransactionAllowed=false` |
| `@Transactional(NESTED)` khi outer JPA transaction active | `NestedTransactionNotSupportedException` trước inner body |
| JDBC savepoint thuần | Account 1 về 100; outer update account 2 thành 20 vẫn commit |
| JPA load 250 sau JDBC UPDATE rồi rollback savepoint | Entity managed còn 250, JDBC query thấy 100 |
| `em.refresh` trong thí nghiệm không dirty state | Managed entity được nạp lại 100 |
| `REQUIRES_NEW` inner rollback riêng | Account 1 = 100, account 2 = 20 |
| Outer runtime exception | Rollback whole transaction, account 1 = 100, account 2 = 10 |

**Chú ý về độ tin cậy:** ví dụ dùng H2 + Hibernate và một connection transaction-bound. Nếu driver/provider/JpaDialect của bạn không phơi bày cùng connection cho JDBC, hoặc một cache/flush mode tùy chỉnh làm thay đổi thời điểm nạp dữ liệu, thí nghiệm cần điều chỉnh trên stack thực. Đó chính là lý do không xem `JPA + savepoint` như một khả năng portable.

## 7. Cách thiết kế thay vì cố restore persistence context bằng savepoint

### 7.1. Nếu công việc JPA phải nguyên tử: rollback toàn bộ

Khi nhiều managed entities phải cùng được commit hoặc cùng rollback, chọn một transaction JPA rõ ràng và để lỗi không thể phục hồi khiến toàn bộ transaction rollback:

```java
@Transactional
public void updateOrderAndInventory() {
    // Cập nhật các JPA entities trong cùng transaction.
    // Nếu một invariant thất bại, ném exception phù hợp
    // và để manager rollback whole transaction.
}
```

Đây là snippet minh họa, không phải class độc lập. Spring mặc định rollback runtime exception/Error; checked exceptions cần rollback rules tương ứng, hoặc cấu hình global theo phiên bản/framework.

Ưu điểm: khi transaction kết thúc, persistence context được kết thúc/detach theo lifecycle phù hợp, thay vì tiếp tục tính toán trong state vừa chịu một JDBC rollback savepoint mà JPA không hay biết.

### 7.2. Nếu bước phụ cần transaction độc lập: `REQUIRES_NEW`

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentRecord() {
    // ...
}
```

Method phải được gọi qua proxy của Spring-managed bean, không tự `this.method()` trong proxy mode mặc định. Đây là transaction physical khác, có thể commit/rollback độc lập. Nó không phải savepoint và sẽ **thay đổi tính nguyên tử** của workflow. Cần đủ connection pool, và outer persistence context vẫn có thể stale nếu inner transaction độc lập sửa những bản ghi outer đã load.

### 7.3. Nếu chỉ cần rollback một vài câu SQL: thiết kế JDBC-only substep

Với code chỉ dùng `JdbcTemplate` trên một local JDBC transaction và không có managed JPA entities trong vùng rollback, `DataSourceTransactionManager`/`PROPAGATION_NESTED` có thể phù hợp nếu DB hỗ trợ savepoints.

Trong ứng dụng JPA pha JDBC, phải kiểm tra manager cùng resource, connection binding và khả năng JpaDialect nếu định dùng `NESTED`. Không tạo một bean `DataSourceTransactionManager` song song rồi giả định mọi JPA repository cũng tham gia đúng transaction. Một JDBC-only sub-work có savepoint thủ công vẫn là lựa chọn nâng cao phải có test phủ DB state, JPA state và failure paths.

### 7.4. Nếu nghiệp vụ có nhiều bước không thể chung transaction: workflow rõ state

Với thao tác liên quan hệ thống bên ngoài, cân nhắc trạng thái nghiệp vụ như `PENDING`, `CONFIRMED`, `FAILED`, transactional outbox hoặc saga/compensation. Savepoint trên DB không đảo ngược API call đã gửi hoặc entity state ở JVM. Thiết kế workflow có trạng thái quan sát và idempotency thường rõ ràng hơn một chuỗi nested transactions mơ hồ.

## 8. Debug checklist cho tình huống JPA + savepoint

1. Xác định bean transaction manager nào thực thi method `@Transactional`; có đúng `JpaTransactionManager` không?
2. Xem `@Transactional(propagation=NESTED)` có đi qua Spring proxy, và lúc ấy có outer transaction hay chưa.
3. Kiểm tra `manager.isNestedTransactionAllowed()`; nhớ default của JPA manager là false.
4. Nếu đã bật flag, kiểm tra `JpaDialect` thực tế có hỗ trợ savepoint hay không; một số provider không cung cấp `SavepointManager` thích hợp.
5. Kiểm tra connection mà savepoint áp dụng có chính là connection SQL/JPA cùng dùng hay không.
6. Ghi rõ thời điểm `em.persist`, `em.find`, field mutation, `flush`, JDBC UPDATE và rollback.
7. So sánh entity managed (`em.find`) với query JDBC sau rollback ở trong transaction; đừng nhầm hai kết quả có nghĩa như nhau.
8. Kiểm tra dirty state, flush mode, optimistic version và pending changes trước outer commit.
9. Khi resource/ORM đã throw lỗi nghiêm trọng, không mặc định có thể tiếp tục commit chỉ vì outer đã catch.
10. Kiểm tra DB sau outer transaction boundary bằng một transaction/connection độc lập; đừng chỉ nhìn cache trong một test `@Transactional`.
11. Không xóa first-level cache hàng loạt bằng `em.clear` nếu còn outer unflushed changes hợp lệ.
12. Chọn thiết kế rollback toàn bộ, `REQUIRES_NEW` hoặc JDBC-only nested có giới hạn rõ và test trên database production-compatible.

Trong môi trường test/dev, log có thể hỗ trợ:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.orm.jpa=DEBUG
logging.level.org.hibernate.SQL=DEBUG
```

Không gắn assertion với chuỗi log cố định. Thứ tự và nội dung log có thể thay đổi; DB commit và JPA context consistency cần được chứng minh bằng trạng thái dữ liệu, không chỉ một dòng DEBUG.

## 9. Sai lầm phổ biến

1. **“NESTED là một EntityManager transaction con.”** Sai: JDBC savepoint không tạo JPA context độc lập.
2. **“Bật `setNestedTransactionAllowed(true)` là giải quyết xong.”** Sai: manager/dialect/driver và JPA state là các điều kiện khác nhau.
3. **“DB hỗ trợ savepoint nên Hibernate JPA cũng sẽ hỗ trợ NESTED.”** Không có bảo đảm như vậy.
4. **“Rollback savepoint tự hủy JPA managed entity changes.”** Sai nếu thay đổi còn ở Java memory hoặc context snapshot.
5. **“`em.find` luôn đọc DB.”** Sai khi entity đã managed.
6. **“`em.flush` là rollback.”** Sai: flush gửi pending changes xuống DB.
7. **“`em.clear` chỉ hủy thay đổi của bước con.”** Sai: nó detach toàn bộ persistence context.
8. **“`em.refresh` khôi phục mọi entity tự động.”** Sai: targeted refresh có thể ghi đè legitimate outer changes.
9. **“Đổi sang `DataSourceTransactionManager` thì JPA sẽ nested được.”** Không nên thay manager JPA tùy tiện.
10. **“`REQUIRES_NEW` giống `NESTED` nhưng an toàn hơn.”** Chúng có tính nguyên tử khác nhau; đều cần thiết kế/test.
11. **“SQL bị rollback rồi thì callback/event ngoài database cũng đảo ngược.”** Sai.
12. **“Test `@Transactional` thấy row có nghĩa đã commit.”** Có thể chỉ đang nhìn dữ liệu chưa commit.
13. **“Không có exception thì persistence context và DB chắc chắn đồng bộ.”** Không đúng sau các can thiệp JDBC vào savepoint mà JPA không biết.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** JDBC rollback savepoint thực hiện thành công. `EntityManager.find` có chắc trả lại field trước savepoint không?

**Trả lời:** Không. `EntityManager` giữ identity map và managed state riêng; không có contract snapshot/restore theo JDBC savepoint.

**Câu 2.** `JpaTransactionManager` mặc định cho phép `NESTED` không?

**Trả lời:** Không, `nestedTransactionAllowed` mặc định false. Với outer JPA transaction hiện có, yêu cầu `NESTED` có thể bị từ chối trước method body.

**Câu 3.** Nếu bật `nestedTransactionAllowed=true` và driver hỗ trợ savepoints, vậy là đủ chưa?

**Trả lời:** Chưa. `JpaDialect` còn cần hỗ trợ cơ chế savepoint mà manager dùng. Kể cả có JDBC savepoint, JPA context vẫn không được restore.

**Câu 4.** Tại sao entity managed có `balance=250` trong khi JDBC query trả `100`?

**Trả lời:** Entity được nạp khi DB tạm là 250; rollback savepoint hoàn tác SQL về 100 nhưng entity cached vẫn mang 250 trong persistence context.

**Câu 5.** Gọi `flush` sau rollback savepoint có thể gây điều gì?

**Trả lời:** Nó có thể ghi các dirty changes đang chờ vào DB, bao gồm thay đổi business logic tưởng đã loại bỏ.

**Câu 6.** Vì sao `clear` nguy hiểm trong outer JPA transaction?

**Trả lời:** Nó detach mọi entity và có thể làm mất unflushed changes hợp lệ của outer, không chỉ của bước sub-operation.

**Câu 7.** `refresh` có giúp trong một thí nghiệm với entity read-only không có pending changes không?

**Trả lời:** Có thể giúp nạp lại riêng entity đó từ DB, nhưng không biến savepoint thành JPA nested rollback.

**Câu 8.** Nếu một bước có thể commit độc lập, nên cân nhắc gì?

**Trả lời:** `REQUIRES_NEW` ở bean/proxy riêng với test và pool đủ lớn; hiểu rằng đó là physical transaction khác và outer JPA context có thể vẫn cần được đọc lại.

**Câu 9.** Cách đo đáng tin cậy nhất của một transaction outcome là gì?

**Trả lời:** Gọi method qua proxy, đợi completion, kiểm tra DB bằng connection/transaction độc lập, đồng thời quan sát state managed nếu đang kiểm tra cache divergence.

## Tài liệu chính thức

- [Spring JpaTransactionManager Javadoc — nested savepoint và JPA context](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html)
- [Spring Framework — Transaction propagation và NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Transaction advice và implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring JpaDialect Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/JpaDialect.html)
- [Spring NestedTransactionNotSupportedException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/NestedTransactionNotSupportedException.html)
- [Spring — JDBC connection handling/DataSourceUtils](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Jakarta Persistence EntityManager Javadoc — flush, refresh, clear](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html)
- [Hibernate ORM User Guide — Persistence context và dirty checking](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html)
- [Spring — Test-managed transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
