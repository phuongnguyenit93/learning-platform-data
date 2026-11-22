# Tạm ngưng, khôi phục và dọn dẹp tài nguyên gắn với giao dịch trong Spring Framework

## Mục tiêu

Trong Spring transaction management, transaction không chỉ gồm `BEGIN` và `COMMIT`. Framework còn phải **bind tài nguyên vào ngữ cảnh thực thi**, **suspend/resume** chúng khi chuyển sang một transaction khác và **cleanup** sau commit hoặc rollback.

Bài này giúp bạn:

1. Phân biệt physical transaction, logical transaction scope, JDBC connection và `ConnectionHolder`.
2. Hiểu `TransactionSynchronizationManager` quản lý resource binding, metadata và synchronizations theo thread trong mô hình imperative.
3. Giải thích `PROPAGATION_REQUIRES_NEW` và `NOT_SUPPORTED` suspend outer resource rồi resume đúng outer context.
4. Giải thích vì sao `REQUIRED` thường chia sẻ connection và `NESTED` thường dùng savepoint, **không** cần suspend outer như `REQUIRES_NEW`.
5. Phân biệt `TransactionSynchronization.suspend()/resume()` với `beforeCommit`, `beforeCompletion`, `afterCommit`, `afterCompletion`.
6. Theo dõi connection pool, cleanup sau cả commit lẫn rollback, nguy cơ rò rỉ resource và bất ngờ khi JDBC auto-commit ngoài transaction.
7. Chạy ví dụ **Java 17+, Spring Boot 3.3.5, Spring JDBC, H2**, kèm JUnit 5 kiểm tra chính xác thứ tự callbacks và dữ liệu thực sự đã commit.

**Phạm vi:** imperative JDBC transaction qua `DataSourceTransactionManager`. Một số chi tiết không áp dụng trực tiếp cho JPA/JTA hoặc transaction reactive.

---

## 1. “Tài nguyên gắn giao dịch” là gì?

Trong Spring JDBC, `JdbcTemplate` thường không nhận connection qua tham số của mỗi method. Thay vào đó, Spring cung cấp **transaction-bound connection** phù hợp cho thread và `DataSource` đang được quản lý.

```text
Application thread
     |
     v
TransactionSynchronizationManager
     |
     +-- DataSource A -> ConnectionHolder -> JDBC Connection C1
     +-- metadata: name, readOnly, isolation, actual transaction
     +-- registered TransactionSynchronization callbacks
     |
     v
JdbcTemplate -> DataSourceUtils
     |
     +-- truy cập đúng connection C1 đang gắn với transaction
     v
Database transaction T1
```

| Thành phần | Nhiệm vụ |
| --- | --- |
| `DataSource` | Cấp JDBC connections, có thể qua HikariCP |
| `Connection` | Kết nối làm việc với database, nơi physical JDBC transaction được quản lý |
| `ConnectionHolder` | Spring holder giữ connection và một số transaction-related state |
| `TransactionSynchronizationManager` | Quản lý resources và synchronizations gắn với thread hiện tại |
| `DataSourceUtils` | Lấy/release connection tuân theo transaction-bound resource |
| `JdbcTemplate` | Dùng connection do Spring quản lý để thực hiện SQL |
| `PlatformTransactionManager` | Điều phối begin, commit, rollback; cụ thể JDBC manager có suspend/resume/cleanup |
| `TransactionSynchronization` | Callback để phối hợp tài nguyên ở lifecycle transaction |

**Phân biệt ba tầng:** `ThreadLocal` chứa binding, `ConnectionHolder` tham chiếu connection, còn **physical transaction** là trạng thái giao dịch thật của database. Gắn một object vào thread **không tự tạo** transaction; một transaction manager vẫn phải bật và hoàn tất transaction thực.

Ví dụ:

```java
@Transactional
public void createOrder() {
    orderRepository.insert();
    inventoryRepository.decrease();
    ledgerRepository.append();
}
```

Đây là snippet nghiệp vụ, cần các repository thực. Nếu ba repository dùng cùng Spring-managed JDBC datasource/transaction manager, các lệnh có thể dùng cùng transaction-bound connection. Nếu một repository tự mở một connection không được Spring quản lý, atomicity có thể mất.

## 2. Quan sát thread-bound context đúng cách

API sử dụng trong Spring imperative:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;
```

Các lệnh:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean syncActive =
    TransactionSynchronizationManager.isSynchronizationActive();

boolean bound =
    TransactionSynchronizationManager.hasResource(dataSource);

Object resource =
    TransactionSynchronizationManager.getResource(dataSource);
```

`resource` thường là `ConnectionHolder` trong Spring JDBC, **không phải** trực tiếp `java.sql.Connection`.

Điểm dễ sai: `isActualTransactionActive()` khác `isSynchronizationActive()`.

- **Actual transaction active:** Spring context gắn với một giao dịch tài nguyên thực.
- **Synchronization active:** có cơ chế callback/resource synchronization hiện hành; trong một số trường hợp, nó vẫn active **khi không có actual transaction**, như một số nhánh `SUPPORTS`/`NOT_SUPPORTED`.
- **Resource bound:** có một tài nguyên dưới key mà bạn kiểm tra. Việc bound resource cũng không tự chứng minh physical transaction còn tồn tại.

Vì vậy:

> `isSynchronizationActive() == true` không đủ để khẳng định SQL đang chạy trong một physical transaction.

Khi xác định trạng thái của scope, hãy nhìn **propagation**, actual transaction, resource binding và transaction manager đang dùng.

**Không tự gọi** `TransactionSynchronizationManager.bindResource(dataSource, ...)`, `unbindResource(dataSource)`, `clearSynchronization()` hoặc `clear()` đối với connection/holder do transaction manager sở hữu. Hành động đó có thể phá liên kết với resource đang chờ commit/rollback.

## 3. Vòng đời của một transaction JDBC thông thường

`DataSourceTransactionManager` là một concrete implementation của `PlatformTransactionManager` cho local JDBC transaction. Khi một outer `@Transactional(REQUIRED)` được gọi qua proxy và chưa có transaction phù hợp:

```text
Caller -> Spring proxy
    |
    v
TransactionInterceptor
    |
    v
DataSourceTransactionManager
    |
    +-- lấy JDBC Connection C1
    +-- chuẩn bị isolation/read-only/timeout khi hỗ trợ
    +-- đặt autoCommit=false nếu cần
    +-- bind ConnectionHolder(C1) theo key DataSource
    +-- công bố metadata/synchronizations
    |
    v
Business method -> JdbcTemplate -> C1
    |
    +-- method return: cố commit
    |       hoặc
    +-- exception khớp rollback rule: rollback
    |
    v
TransactionSynchronization callbacks
    |
    v
cleanup:
    - unbind holder của transaction
    - phục hồi connection state đã thay đổi
    - release connection về pool
    - xóa context transaction/synchronization tương ứng
    |
    v
Caller nhận kết quả
```

Đây là **mô tả theo chức năng**, không cam kết thứ tự từng internal method đúng như sơ đồ. Quan trọng: `afterCommit` và `afterCompletion` có thể chạy **khi một số resources vẫn còn bound**; không giả định connection đã hoàn toàn release ngay khi callback bắt đầu.

`DataSourceTransactionManager` đảm nhiệm cleanup cả khi commit thành công, rollback, hoặc khi thao tác transaction gặp lỗi theo cơ chế manager. Business code nên để framework điều phối tài nguyên, thay vì đóng connection hoặc xóa ThreadLocal bằng tay.

### Inner `REQUIRED` thì sao?

```java
@Transactional(propagation = Propagation.REQUIRED)
public void outer() {
    innerService.inner();
}
```

Nếu `inner()` là method được advice qua một Spring bean khác và cũng dùng `REQUIRED`, nó **tham gia** physical T1 trên C1, không cần suspend để mở một physical transaction mới. Kết thúc inner thành công **không commit** C1 riêng. Nếu inner đánh dấu rollback-only, outer commit vẫn có thể thất bại với `UnexpectedRollbackException`.

## 4. Suspend và resume: ẩn outer context, không kết thúc outer transaction

Khi outer transaction T1 đang active mà inner dùng `REQUIRES_NEW`, Spring phải để inner có **physical transaction độc lập**:

```text
Outer T1 / C1
  |
  +-- INSERT A trên C1, chưa commit
  |
  +-- SUSPEND outer
  |      - lưu và tạm gỡ outer resource binding
  |      - tạm ngưng outer synchronizations
  |      - giữ metadata/context để khôi phục
  |      - T1 vẫn mở, C1 thường vẫn bị giữ
  |
  +-- BEGIN inner T2 / C2
  |      - bind Holder(C2)
  |      - INSERT B trên C2
  |      - COMMIT hoặc ROLLBACK T2
  |      - cleanup inner resources
  |
  +-- RESUME outer
  |      - bind lại Holder(C1)
  |      - khôi phục outer synchronizations và metadata
  |
  +-- INSERT C trên C1
  |
  +-- COMMIT hoặc ROLLBACK T1
  +-- cleanup outer
```

**Suspend không phải COMMIT/ROLLBACK.** T1 vẫn mở trong database; dữ liệu A chưa commit và lock hoặc snapshot vẫn có thể tồn tại trong lúc inner chạy. **Resume không tạo T1 mới:** nó khôi phục transaction/resource context cũ.

Đối với local JDBC, `DataSourceTransactionManager` có các hooks `doSuspend(...)`, `doResume(...)` để unbind/bind resource. Ở cấp chung, `AbstractPlatformTransactionManager` điều phối transaction synchronizations, suspended resources và metadata.

**Hệ quả connection pool:** outer C1 có thể còn giữ connection trong khi inner T2 cần C2. Với nhiều request đồng thời, pool phải có capacity cho các inner transactions. Spring khuyến cáo pool cần vượt số thread đồng thời ít nhất một connection cho một lớp `REQUIRES_NEW` lồng, và thực tế có thể cần nhiều hơn tùy workloads.

## 5. `NOT_SUPPORTED`: suspend outer nhưng không mở transaction mới

Nếu inner có:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void runWithoutTransaction() {
    // JDBC work trong phạm vi không có Spring-managed physical transaction.
}
```

Spring suspend transaction ngoài khi cần, nhưng **không mở physical transaction mới** chỉ để chạy inner. Nếu `JdbcTemplate.update()` sử dụng một connection mới có `autoCommit=true`, câu SQL có thể **commit độc lập** ngay khi statement hoàn tất.

```text
T1 trên C1: INSERT outer-1 (chưa commit)
    |
    +-- suspend T1
    +-- NOT_SUPPORTED:
    |      INSERT external-2 bằng connection khác / auto-commit
    |      external-2 đã commit (với autoCommit=true)
    +-- resume T1
    |
    +-- ROLLBACK T1
```

Kết quả: `outer-1` bị rollback, nhưng `external-2` vẫn còn.

**Điều kiện phải nói rõ:** tính bền vững của statement ngoài transaction phụ thuộc datasource, connection/auto-commit setting, SQL và database. `NOT_SUPPORTED` không hứa rằng mọi thứ tự động commit trong mọi môi trường.

Trong `NOT_SUPPORTED`, `isActualTransactionActive()` là `false`; tuy nhiên transaction synchronization **có thể** active, và `JdbcTemplate` có thể bind một connection dành cho nontransactional synchronization **sau khi thực hiện JDBC access**. Vì thế, đừng viết một assertion kiểu “sau bất kỳ câu SQL trong NOT_SUPPORTED, `hasResource(dataSource)` phải luôn false”.

## 6. Propagation quyết định việc suspend, join hay dùng savepoint

| Propagation inner | Khi outer T1 đang active | Suspend resource? | Transaction vật lý của inner |
| --- | --- | --- | --- |
| `REQUIRED` | Join T1 | Thường không | Cùng T1 |
| `REQUIRES_NEW` | Suspend T1 | Có | T2 độc lập |
| `NOT_SUPPORTED` | Suspend T1 | Có | Không mở transaction mới |
| `NESTED` | Tạo savepoint trong T1 nếu hỗ trợ | Không theo mô hình JDBC savepoint | Cùng T1 |
| `SUPPORTS` | Tham gia T1 | Thường không | Cùng T1 |
| `MANDATORY` | Bắt buộc có T1 | Không | Cùng T1 |
| `NEVER` | Không cho phép T1 | Không; báo lỗi | Không chạy inner khi T1 có sẵn |

`NESTED` **không** giống `REQUIRES_NEW`: rollback tới savepoint có thể hủy một phần thay đổi của cùng T1, nhưng nested success **không commit độc lập**. Với `REQUIRES_NEW`, inner có transaction riêng, có thể commit dù outer rollback.

`NOT_SUPPORTED` **không** tương đương `readOnly=true`: nó chỉ yêu cầu chạy không có transaction vật lý hiện tại. Code vẫn có thể gửi `UPDATE`/`INSERT`.

## 7. Hệ thống Spring điều phối lifecycle như thế nào?

`AbstractPlatformTransactionManager` xác định propagation, transaction đã có hay chưa, phải tạo mới hay tham gia, có cần suspend/resume, và quyết định commit/rollback. Concrete managers như JDBC `DataSourceTransactionManager` cung cấp hooks triển khai với resource cụ thể.

| Hook | Mục đích |
| --- | --- |
| `doBegin(...)` | Bắt đầu physical transaction |
| `doSuspend(...)` | Tạm gỡ resource của transaction hiện tại |
| `doResume(...)` | Phục hồi resource đã suspend |
| `doCommit(...)` | Commit transaction thực |
| `doRollback(...)` | Rollback transaction thực |
| `doSetRollbackOnly(...)` | Đánh dấu transaction được chia sẻ không thể commit |
| `doCleanupAfterCompletion(...)` | Dọn resource sau completion |

Một transaction manager **không nhất thiết** hỗ trợ suspend: base implementation có thể báo `TransactionSuspensionNotSupportedException`. Cấu hình/triển khai JTA, JPA hay custom manager cần kiểm chứng cụ thể; không suy từ JDBC code sang mọi tài nguyên.

### Tại sao không tự suspend connection?

Spring phải tạm gỡ **cả resource binding và synchronizations/metadata**, rồi khôi phục trong trạng thái nhất quán, kể cả khi inner ném exception. Việc gọi `TransactionSynchronizationManager.unbindResource(dataSource)` trong business service chỉ gỡ một binding; nó không thực hiện toàn bộ hợp đồng suspend/resume.

Một lỗi thường gặp là giữ connection cũ, tự chuyển thread hoặc bind thêm connection dưới cùng key và mong Spring xử lý. Kết quả có thể là connection dùng sai transaction, bind trùng, thiếu rollback hoặc pool leak.

## 8. `TransactionSynchronization`: callbacks và thứ tự

Spring cung cấp:

```java
import org.springframework.transaction.support.TransactionSynchronization;
```

Những callback quan trọng:

| Callback | Mốc chạy | Ý nghĩa |
| --- | --- | --- |
| `suspend()` | Khi outer synchronizations bị tạm ngưng | Custom resource synchronization có thể unbind resource của mình |
| `resume()` | Khi outer context được khôi phục | Có thể bind lại custom resource |
| `beforeCommit(boolean readOnly)` | Trước nỗ lực commit | Flush/kiểm tra; **chưa chắc commit thành công** |
| `beforeCompletion()` | Trước completion, cả commit và rollback | Dọn tài nguyên cần giải phóng trước completion |
| `afterCommit()` | Sau commit thành công | Tác vụ hậu commit, có caveat resource còn bound |
| `afterCompletion(int status)` | Sau khi biết trạng thái commit/rollback/unknown | Cleanup và theo dõi kết quả |

`TransactionSynchronization` cung cấp `STATUS_COMMITTED`, `STATUS_ROLLED_BACK` và `STATUS_UNKNOWN`.

Đường commit thông thường:

```text
business method returns
  -> beforeCommit
  -> beforeCompletion
  -> physical commit
  -> afterCommit
  -> afterCompletion(COMMITTED)
  -> hoàn tất resource/context cleanup
```

Đường rollback thông thường:

```text
business method throws unchecked exception
  -> beforeCompletion
  -> physical rollback
  -> afterCompletion(ROLLED_BACK)
  -> hoàn tất resource/context cleanup
```

`afterCommit()` và `beforeCommit()` **không** phải các callback cho đường rollback thông thường. `beforeCommit()` không chứng minh commit đã hoàn thành.

### Đăng ký synchronization

```java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                System.out.println("Completed: " + status);
            }
        }
    );
}
```

Đoạn trên là snippet, không phải class độc lập. Khi không có active synchronization, không nên gọi `registerSynchronization(...)` mà bỏ qua điều kiện. Hạ tầng của Spring đảm nhiệm kích hoạt/dừng synchronizations.

**Cảnh báo quan trọng:** theo Javadoc Spring, `afterCommit()` và `afterCompletion(...)` có thể chạy khi transactional resources **vẫn có thể truy cập và còn bound**, dù physical commit/rollback đã xong. Database work trong callback có thể tưởng như “tham gia transaction cũ” nhưng **không còn commit nào kế tiếp**. Nếu thật sự cần ghi DB trong callback, sử dụng một **transaction mới**, chẳng hạn lời gọi qua bean `@Transactional(propagation = REQUIRES_NEW)`. Nếu cần đảm bảo sự kiện liên hệ thống không bị mất khi process chết sau commit, cân nhắc **transactional outbox**.

---

## 9. Dự án runnable: Spring Boot 3.3.5 + JDBC/H2 theo dõi resource suspend/resume

### 9.1. Kịch bản

Demo có hai tình huống độc lập:

**A. Outer rollback, inner vẫn giữ commit độc lập**

- Outer T1 INSERT id 1.
- Inner `REQUIRES_NEW` T2 INSERT id 2 và commit.
- Inner `NOT_SUPPORTED` INSERT id 3 qua connection auto-commit.
- Outer T1 INSERT id 4 rồi ném `IllegalStateException`; T1 rollback.
- DB cuối chỉ còn **2 và 3**.

**B. Inner rollback, outer vẫn commit**

- Outer T1 INSERT id 10.
- Inner `REQUIRES_NEW` T2 INSERT id 11 rồi ném `IllegalStateException`; T2 rollback.
- Outer catch lỗi sau inner proxy, INSERT id 12 và commit.
- DB cuối có **10 và 12**, không có 11.

Trong quá trình đó, outer synchronization sẽ ghi lại `suspend`, `resume`, `beforeCompletion`, `afterCompletion`; trong case B còn có `beforeCommit` và `afterCommit`.

### 9.2. Cấu trúc

```text
resource-lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/lifecycle/
    │   │   ├── InnerScopeService.java
    │   │   ├── OuterScopeService.java
    │   │   ├── ScenarioRunner.java
    │   │   └── ResourceLifecycleApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/java/example/lifecycle/
        └── ResourceLifecycleTest.java
```

Dùng Java 17+, Gradle với Spring Boot 3.3.5. Tạo Gradle wrapper bằng Spring Initializr hoặc Gradle đã cài. Không cần web server.

### 9.3. `settings.gradle`

```groovy
rootProject.name = 'resource-lifecycle-demo'
```

### 9.4. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 9.5. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:resource_lifecycle;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 4
  sql:
    init:
      mode: always
```

Pool 4 connections cho phép outer giữ C1 trong lúc inner `REQUIRES_NEW` hoặc SQL `NOT_SUPPORTED` mượn connection khác. Demo giả định JDBC auto-commit mặc định của pool/driver đối với SQL chạy ngoài physical transaction.

### 9.6. `src/main/resources/schema.sql`

```sql
CREATE TABLE tx_events (
    id INTEGER PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);
```

Mỗi scenario reset bảng trước khi mở outer transaction. Các INSERT dùng ID khác nhau nên không tranh chấp cùng khóa chính.

### 9.7. `src/main/java/example/lifecycle/InnerScopeService.java`

```java
package example.lifecycle;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class InnerScopeService {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;

    public InnerScopeService(JdbcTemplate jdbc, DataSource dataSource) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void commitNew(List<String> trace, Object outerHolder) {
        boolean active = TransactionSynchronizationManager
            .isActualTransactionActive();
        Object innerHolder = TransactionSynchronizationManager
            .getResource(dataSource);

        trace.add(
            "NEW active=" + active
            + " differentHolder=" + (innerHolder != outerHolder)
        );

        jdbc.update(
            "INSERT INTO tx_events (id, description) VALUES (?, ?)",
            2, "new-committed"
        );
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void nonTransactional(List<String> trace, Object outerHolder) {
        boolean active = TransactionSynchronizationManager
            .isActualTransactionActive();
        Object visible = TransactionSynchronizationManager
            .getResource(dataSource);

        trace.add(
            "NOT_SUPPORTED active=" + active
            + " outerHidden=" + (visible == null)
        );

        jdbc.update(
            "INSERT INTO tx_events (id, description) VALUES (?, ?)",
            3, "non-transactional"
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void failNew(List<String> trace) {
        trace.add(
            "NEW_FAIL active="
            + TransactionSynchronizationManager.isActualTransactionActive()
        );

        jdbc.update(
            "INSERT INTO tx_events (id, description) VALUES (?, ?)",
            11, "inner-rolled-back"
        );
        throw new IllegalStateException("inner rejected");
    }
}
```

`outerHolder` được truyền để so sánh **object identity** của resource holder trong demo; nó không phải một connection ID để dùng trong production logic.

`nonTransactional` kiểm tra binding **trước khi JDBC access**. Sau `jdbc.update`, Spring có thể bind tạm một connection theo synchronization policy, mặc dù **không có physical transaction** trong scope; đó là lý do ta không in `hasResource` sau câu SQL rồi suy diễn `NOT_SUPPORTED` đã mở T.

### 9.8. `src/main/java/example/lifecycle/OuterScopeService.java`

```java
package example.lifecycle;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OuterScopeService {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;
    private final InnerScopeService inner;

    public OuterScopeService(
            JdbcTemplate jdbc, DataSource dataSource,
            InnerScopeService inner) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
        this.inner = inner;
    }

    private static String completionName(int status) {
        return switch (status) {
            case TransactionSynchronization.STATUS_COMMITTED -> "COMMITTED";
            case TransactionSynchronization.STATUS_ROLLED_BACK -> "ROLLED_BACK";
            default -> "UNKNOWN";
        };
    }

    private static void registerTrace(List<String> trace) {
        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void suspend() {
                    trace.add("SYNC suspend");
                }
                @Override
                public void resume() {
                    trace.add("SYNC resume");
                }
                @Override
                public void beforeCommit(boolean readOnly) {
                    trace.add("SYNC beforeCommit");
                }
                @Override
                public void beforeCompletion() {
                    trace.add("SYNC beforeCompletion");
                }
                @Override
                public void afterCommit() {
                    trace.add("SYNC afterCommit");
                }
                @Override
                public void afterCompletion(int status) {
                    trace.add(
                        "SYNC afterCompletion=" + completionName(status)
                    );
                }
            }
        );
    }

    private void insert(int id, String description) {
        jdbc.update(
            "INSERT INTO tx_events (id, description) VALUES (?, ?)",
            id, description
        );
    }

    @Transactional
    public void rollbackOuter(List<String> trace) {
        Object outerHolder = TransactionSynchronizationManager
            .getResource(dataSource);

        trace.add(
            "OUTER active="
            + TransactionSynchronizationManager.isActualTransactionActive()
            + " bound=" + (outerHolder != null)
        );

        registerTrace(trace);
        insert(1, "outer-before");

        inner.commitNew(trace, outerHolder);
        trace.add(
            "RESUMED after NEW="
            + (TransactionSynchronizationManager.getResource(dataSource)
               == outerHolder)
        );

        inner.nonTransactional(trace, outerHolder);
        trace.add(
            "RESUMED after NOT_SUPPORTED="
            + (TransactionSynchronizationManager.getResource(dataSource)
               == outerHolder)
        );

        insert(4, "outer-after");
        throw new IllegalStateException("outer rejected");
    }

    @Transactional
    public void commitOuter(List<String> trace) {
        trace.add(
            "OUTER active="
            + TransactionSynchronizationManager.isActualTransactionActive()
        );

        registerTrace(trace);
        insert(10, "outer-before");

        try {
            inner.failNew(trace);
        } catch (IllegalStateException ex) {
            trace.add("OUTER caughtInner=" + ex.getMessage());
        }

        insert(12, "outer-after");
    }
}
```

`registerTrace()` chạy trong outer transaction đã mở nên synchronization active. `suspend`/`resume` chỉ ghi trace; **không** unbind JDBC holder thủ công. Framework xử lý holder theo `DataSourceTransactionManager`.

Trong case A, callback `beforeCompletion` và `afterCompletion(ROLLED_BACK)` xảy ra, **không** có `afterCommit`. Trong case B, callback before/after commit xảy ra và status completion là `COMMITTED`.

### 9.9. `src/main/java/example/lifecycle/ScenarioRunner.java`

```java
package example.lifecycle;

import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ScenarioRunner {
    private final JdbcTemplate jdbc;
    private final DataSource dataSource;
    private final OuterScopeService outer;

    public ScenarioRunner(
            JdbcTemplate jdbc, DataSource dataSource,
            OuterScopeService outer) {
        this.jdbc = jdbc;
        this.dataSource = dataSource;
        this.outer = outer;
    }

    private void reset() {
        jdbc.update("DELETE FROM tx_events");
    }

    private String persistedRows() {
        List<String> rows = jdbc.query(
            "SELECT id, description FROM tx_events ORDER BY id",
            (rs, index) ->
                rs.getInt("id") + ":" + rs.getString("description")
        );
        return rows.toString();
    }

    private boolean contextClean() {
        return !TransactionSynchronizationManager
                .isActualTransactionActive()
            && !TransactionSynchronizationManager
                .isSynchronizationActive()
            && !TransactionSynchronizationManager
                .hasResource(dataSource);
    }

    public List<String> scenarioA() {
        reset();
        List<String> trace = new ArrayList<>();

        try {
            outer.rollbackOuter(trace);
        } catch (IllegalStateException ex) {
            trace.add("A caught=" + ex.getMessage());
        }

        trace.add("A rows=" + persistedRows());
        trace.add("A cleanup=" + contextClean());
        return trace;
    }

    public List<String> scenarioB() {
        reset();
        List<String> trace = new ArrayList<>();

        outer.commitOuter(trace);
        trace.add("B rows=" + persistedRows());
        trace.add("B cleanup=" + contextClean());
        return trace;
    }
}
```

Runner được gọi **ngoài transaction**, nên `reset()` và `persistedRows()` không tham gia outer T1. Kết quả DB chỉ được đọc sau khi transaction proxy đã commit/rollback.

`contextClean()` kiểm tra không còn actual transaction, active synchronization hay datasource resource bound trên thread. Nó là một kiểm tra lifecycle hữu ích; metrics từ pool vẫn cần để phát hiện connection leak trong hệ thống thật.

### 9.10. `src/main/java/example/lifecycle/ResourceLifecycleApplication.java`

```java
package example.lifecycle;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class ResourceLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceLifecycleApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    ApplicationRunner demonstrate(ScenarioRunner scenarios) {
        return args -> {
            scenarios.scenarioA().forEach(System.out::println);
            scenarios.scenarioB().forEach(System.out::println);
        };
    }
}
```

Có một JDBC transaction manager, cùng một `DataSource` với `JdbcTemplate`; `@EnableTransactionManagement` tạo transaction advice. Các lời gọi `ScenarioRunner -> OuterScopeService -> InnerScopeService` đều qua Spring bean proxies, tránh self-invocation.

### 9.11. Chạy và stdout dự kiến

Linux/macOS:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Bỏ qua startup logs, chương trình dự kiến in:

```text
OUTER active=true bound=true
SYNC suspend
NEW active=true differentHolder=true
SYNC resume
RESUMED after NEW=true
SYNC suspend
NOT_SUPPORTED active=false outerHidden=true
SYNC resume
RESUMED after NOT_SUPPORTED=true
SYNC beforeCompletion
SYNC afterCompletion=ROLLED_BACK
A caught=outer rejected
A rows=[2:new-committed, 3:non-transactional]
A cleanup=true
OUTER active=true
SYNC suspend
NEW_FAIL active=true
SYNC resume
OUTER caughtInner=inner rejected
SYNC beforeCommit
SYNC beforeCompletion
SYNC afterCommit
SYNC afterCompletion=COMMITTED
B rows=[10:outer-before, 12:outer-after]
B cleanup=true
```

Đây là **stdout dự kiến theo source và cấu hình**, không phải khẳng định code đã chạy trên máy đang ghi tài liệu.

Giải thích:

- `SYNC suspend`/`SYNC resume` xuất hiện quanh `REQUIRES_NEW`, `NOT_SUPPORTED` và inner thất bại, vì outer synchronizations được tạm ngưng rồi phục hồi.
- `differentHolder=true` nghĩa inner đã bind holder mới, thay vì dùng holder của outer.
- `NOT_SUPPORTED active=false` xác nhận không có Spring-managed physical transaction trong callback đó.
- `RESUMED ...=true` xác nhận đúng outer holder đã được bind lại.
- Khi outer rollback, **inner đã commit id2** và SQL auto-commit id3 vẫn còn.
- Khi inner T2 rollback nhưng outer bắt lỗi sau inner proxy, outer T1 vẫn có thể commit id10/id12.
- `cleanup=true` xác nhận thread context đã được dọn sau outer boundary.

## 10. Test JUnit 5 kiểm chứng resource lifecycle

File `src/test/java/example/lifecycle/ResourceLifecycleTest.java`:

```java
package example.lifecycle;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.util.List;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootTest
class ResourceLifecycleTest {
    @Autowired ScenarioRunner scenarios;
    @Autowired DataSource dataSource;

    @Test
    void outerRollbackLeavesIndependentWrites() {
        assertEquals(
            List.of(
                "OUTER active=true bound=true",
                "SYNC suspend",
                "NEW active=true differentHolder=true",
                "SYNC resume",
                "RESUMED after NEW=true",
                "SYNC suspend",
                "NOT_SUPPORTED active=false outerHidden=true",
                "SYNC resume",
                "RESUMED after NOT_SUPPORTED=true",
                "SYNC beforeCompletion",
                "SYNC afterCompletion=ROLLED_BACK",
                "A caught=outer rejected",
                "A rows=[2:new-committed, 3:non-transactional]",
                "A cleanup=true"
            ),
            scenarios.scenarioA()
        );
    }

    @Test
    void innerRollbackDoesNotForceOuterRollback() {
        assertEquals(
            List.of(
                "OUTER active=true",
                "SYNC suspend",
                "NEW_FAIL active=true",
                "SYNC resume",
                "OUTER caughtInner=inner rejected",
                "SYNC beforeCommit",
                "SYNC beforeCompletion",
                "SYNC afterCommit",
                "SYNC afterCompletion=COMMITTED",
                "B rows=[10:outer-before, 12:outer-after]",
                "B cleanup=true"
            ),
            scenarios.scenarioB()
        );
    }

    @Test
    void noTransactionResourcesRemainAfterBoundary() {
        scenarios.scenarioB();

        assertFalse(
            TransactionSynchronizationManager.isActualTransactionActive()
        );
        assertFalse(
            TransactionSynchronizationManager.isSynchronizationActive()
        );
        assertFalse(
            TransactionSynchronizationManager.hasResource(dataSource)
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

Không đặt `@Transactional` trên test class/method: transaction do test framework mở có thể khiến method outer join **transaction của test** và thay đổi hoàn toàn ý nghĩa của `REQUIRES_NEW`, `NOT_SUPPORTED`, commit/rollback cuối cùng.

`@SpringBootTest` có thể gọi `ApplicationRunner` khi tạo context. Mỗi scenario tự `DELETE` fixture trước lúc chạy, nên assertions độc lập với output khi startup. Không chạy nhiều test dùng chung một H2 table song song nếu chưa cô lập database/fixture. Mockito đơn thuần không thể chứng minh resource suspend/resume hay persisted rows sau physical commit.

## 11. Custom resource binding: chỉ dành cho lớp hạ tầng

Đa số application không cần `bindResource`/`unbindResource`. Nhưng một **resource management integration** có thể bind object tự quản dưới một key riêng và dùng synchronizations:

```java
private static final Object CUSTOM_KEY = new Object();

void bindCustomResource(Object holder) {
    if (!TransactionSynchronizationManager.isSynchronizationActive()) {
        throw new IllegalStateException("No active synchronization");
    }

    TransactionSynchronizationManager.bindResource(CUSTOM_KEY, holder);

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void suspend() {
                TransactionSynchronizationManager.unbindResource(CUSTOM_KEY);
            }
            @Override
            public void resume() {
                TransactionSynchronizationManager.bindResource(
                    CUSTOM_KEY, holder
                );
            }
            @Override
            public void afterCompletion(int status) {
                TransactionSynchronizationManager
                    .unbindResourceIfPossible(CUSTOM_KEY);
            }
        }
    );
}
```

Đây là **snippet kiến trúc, không phải Java class độc lập**, và còn cần chính sách đóng tài nguyên, error handling, nested scopes, key ownership thực tế. Nó không được sao chép mù vào production.

Ý nghĩa: custom resource phải được **tạm unbind khi suspend**, **bind lại khi resume**, và **dọn sau transaction completion**. Tuyệt đối không dùng code này để tự thao tác key `DataSource` của `ConnectionHolder` mà Spring manager đang sở hữu. Với Spring 6.1, một resource key chỉ nên có một binding hợp lệ; bind trùng thường ném `IllegalStateException`.

## 12. Lỗi nguy hiểm ở `afterCommit()` và `afterCompletion()`

```java
TransactionSynchronizationManager.registerSynchronization(
    new TransactionSynchronization() {
        @Override
        public void afterCommit() {
            auditRepository.insertAuditEntry();
        }
    }
);
```

Snippet này **không bảo đảm** `insertAuditEntry()` sẽ có một commit mới. Theo Javadoc Spring, transaction đã commit nhưng một số resource **vẫn có thể bound** trong callbacks. JDBC code trong callback có thể thấy connection cũ, tưởng như tham gia transaction cũ **mà không còn commit tiếp theo**.

Nếu muốn viết DB thật sự sau commit, gọi một **Spring bean khác** có method `@Transactional(propagation = REQUIRES_NEW)` để tạo transaction mới, hoặc dùng một `TransactionTemplate` cấu hình `PROPAGATION_REQUIRES_NEW` tại đúng chỗ. Không gọi `this.innerRequiresNew()` bằng self-invocation rồi kỳ vọng proxy advice chạy.

Với yêu cầu phát event/message không được mất khi process chết ngay sau database commit, `afterCommit()` gửi thẳng tới broker vẫn có một failure gap. **Transactional outbox** cùng retry/idempotency là một giải pháp nhất quán hơn.

## 13. Cleanup và connection pool

Với connection pool như HikariCP, `release` thường là **trả connection proxy về pool**, không bắt buộc đóng vật lý TCP socket ngay lập tức.

Sau physical completion, JDBC manager thường chịu trách nhiệm unbind holder, phục hồi auto-commit/isolation/read-only khi đã thay đổi, release connection và xóa transaction-specific context. Spring sẽ chạy cleanup trên các nhánh thành công/thất bại phù hợp; vì thế code ứng dụng không nên `close` transaction-bound connection tùy tiện.

Ba tình huống cần phân biệt:

| Hiện tượng | Điều cần điều tra |
| --- | --- |
| Pool hết connection | Outer T còn mở khi suspend, inner `REQUIRES_NEW` cần C2; transaction quá dài |
| Thread mang resource cũ qua request | Custom binding không unbind sau completion hoặc code tự thay ThreadLocal |
| Leak detection báo cảnh báo | Connection thật sự không trả pool **hoặc** transaction giữ connection quá lâu |

Cách phòng: dùng `JdbcTemplate`, giữ transaction ngắn, tránh blocking network call trong T, kiểm tra số lớp `REQUIRES_NEW`, pool capacity và connection metrics, thay vì tăng max pool không giới hạn.

## 14. Đồng bộ với thread khác và reactive context

Trong imperative JDBC, `TransactionSynchronizationManager` là **thread-bound**. `@Async`, `Executor` hay `CompletableFuture` chạy thread khác **không tự kế thừa** transaction holder của thread gọi:

```java
@Transactional
public void perform(Executor executor) {
    saveToDatabase();
    executor.execute(() -> sendMessage());
}
```

Snippet minh họa này không đảm bảo task có cùng transaction hay được rollback nếu outer fail. Không sao chép `getResourceMap()` sang thread khác: connection/holder có thể không thread-safe và lifecycle của manager sẽ bị phá.

Reactive (`ReactiveTransactionManager`/R2DBC) sử dụng ngữ cảnh subscription/Reactive Context, không dùng cùng implicit JDBC thread-local semantics. Không áp dụng trực tiếp kỹ thuật này vào reactive flow.

## 15. Checklist debug suspend/resume

1. Xác định outer physical transaction bắt đầu ở đâu và qua proxy hay không.
2. Kiểm tra `PlatformTransactionManager`, `DataSource` và JDBC connection pool.
3. Xác định inner propagation: `REQUIRED`, `REQUIRES_NEW`, `NOT_SUPPORTED`, `NESTED`.
4. Nếu `REQUIRES_NEW`, outer có tạm ngưng và lấy connection mới không? Pool có đủ connections?
5. Nếu `NOT_SUPPORTED`, code có thực hiện SQL auto-commit ngoài transaction không?
6. Nếu `NESTED`, driver/manager có hỗ trợ savepoint thay vì transaction mới không?
7. Theo dõi `TransactionSynchronization.suspend()/resume()` để phân biệt outer context với inner context.
8. Đọc `isActualTransactionActive()` và `getResource(dataSource)` ở đúng thời điểm; không nhầm với `isSynchronizationActive()`.
9. Đừng chỉ nhìn SQL “đã chạy”: kiểm tra dữ liệu sau **outermost transaction boundary**.
10. Theo dõi `beforeCompletion`/`afterCompletion` và transaction outcome.
11. Kiểm tra thread context đã sạch sau method; đối chiếu pool metrics để phát hiện leaks.
12. Tránh chỉnh `TransactionSynchronizationManager` thủ công trong business service.
13. Nếu thấy unexpected rollback, kiểm tra inner `REQUIRED` đã đánh dấu rollback-only hay chưa.
14. Nếu cần ghi DB từ `afterCommit`, chuyển qua transaction mới thực sự.
15. Khi đổi từ JDBC sang JPA/JTA/reactive, kiểm tra lại toàn bộ resource/lifecycle assumptions.

Có thể bật log trong môi trường debug:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.jdbc.datasource.DataSourceTransactionManager: DEBUG
```

Chỉ bật tạm khi cần; không in resource map hoặc connection secrets ra logs production.

## 16. Câu hỏi tự kiểm tra

1. `suspend` có commit outer transaction không? **Không**; outer thường vẫn mở trong DB.
2. `resume` có tạo transaction ngoài mới không? **Không**; nó khôi phục context/resource cũ.
3. `REQUIRES_NEW` có thể commit dù outer rollback không? **Có**, vì independent physical transaction.
4. `NOT_SUPPORTED` có mở transaction vật lý mới không? **Không**.
5. Nếu JDBC auto-commit ở `NOT_SUPPORTED`, outer rollback có xóa INSERT inner đã commit không? **Không**.
6. Inner `REQUIRED` có mở C2 khi outer đã có C1 không? **Thông thường không**, nó tham gia C1/T1.
7. `NESTED` dùng gì để phục hồi một phần? **Savepoint trong cùng physical transaction** khi hỗ trợ.
8. `isSynchronizationActive()` nghĩa chắc chắn có actual transaction? **Không**.
9. `getResource(dataSource)` trả gì? **Resource bound theo key**, với JDBC thường là `ConnectionHolder`.
10. `beforeCommit` nghĩa commit đã thành công? **Không**.
11. `afterCompletion` có thể chạy trước khi tài nguyên được dọn hoàn toàn không? **Có**.
12. Muốn ghi audit trong `afterCommit`, nên tạo gì? **Một transaction mới thật sự** nếu nghiệp vụ cho phép.
13. Vì sao `REQUIRES_NEW` dễ gây pool starvation? **C1 outer vẫn bị giữ trong lúc cần C2 inner**.
14. Nên tự gọi `unbindResource(dataSource)` trong service không? **Không**, manager sở hữu resource đó.
15. Transaction context imperative có tự đi sang thread async khác không? **Không**.
16. `afterCompletion(STATUS_ROLLED_BACK)` có đồng nghĩa “không có side effects ngoài DB” không? **Không**, transaction manager chỉ quản lý các tài nguyên thuộc transaction của nó.

## 17. Tài liệu tham khảo chính thức

- Spring Framework — **Transaction Propagation**, `REQUIRED`, `REQUIRES_NEW`, `NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **Declarative Transaction Implementation**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — **TransactionSynchronizationManager** (imperative): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — **TransactionSynchronization** (`suspend`, `resume`, `afterCompletion`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — **AbstractPlatformTransactionManager** lifecycle: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework — **DataSourceTransactionManager**, suspend/resume/cleanup: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — **DataSourceUtils**, JDBC resource binding: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — **Transaction-bound Events** và `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html