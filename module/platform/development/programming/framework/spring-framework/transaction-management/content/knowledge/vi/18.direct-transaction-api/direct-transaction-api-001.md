# Tạo DefaultTransactionDefinition và đặt tên giao dịch trong Spring Framework

## 1. Mục tiêu bài học và tình huống thực tế

Spring Framework có hai nhóm API để quản lý transaction:

- **Declarative:** khai báo `@Transactional` hoặc cấu hình XML; Spring transaction interceptor mở, commit hoặc rollback theo metadata.
- **Programmatic:** code trực tiếp dùng `PlatformTransactionManager`, `TransactionDefinition`, `TransactionStatus` hoặc dùng `TransactionTemplate` để quyết định ranh giới giao dịch.

Bài này tập trung vào **API giao dịch trực tiếp**, đặc biệt là việc **tạo `DefaultTransactionDefinition` và đặt tên giao dịch với `setName(String)`**. Tên được Spring dùng làm thông tin nhận diện của một transaction khi có khả năng phơi bày qua transaction synchronization/monitoring; **không phải tên bảng, ID transaction do database cấp hoặc tên transaction manager bean**.

Ví dụ cơ bản:

```java
DefaultTransactionDefinition definition =
    new DefaultTransactionDefinition();

definition.setName("orders.create");
definition.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);

TransactionStatus status = transactionManager.getTransaction(definition);
try {
    performDatabaseWork();
} catch (RuntimeException | Error ex) {
    transactionManager.rollback(status);
    throw ex;
}
transactionManager.commit(status);
```

Đây là **mẫu minh họa**: `transactionManager` và `performDatabaseWork()` phải được cung cấp. Ở phần thực hành sẽ có project Java 17+ hoàn chỉnh với H2.

Sau bài học, bạn có thể:

1. Phân biệt `TransactionDefinition`, `DefaultTransactionDefinition`, `PlatformTransactionManager` và `TransactionStatus`.
2. Tạo definition, cấu hình `propagation`, `isolation`, `timeout`, `readOnly` và đặc biệt **`name`**.
3. Gọi `getTransaction(definition)`, tự quyết định `commit(status)` hoặc `rollback(status)`, không rollback nhầm một status đã hoàn thành.
4. Đọc tên hiện hành bằng `TransactionSynchronizationManager.getCurrentTransactionName()` trong mô hình imperative.
5. Giải thích vì sao inner `REQUIRED` tham gia transaction ngoài **thường giữ tên outer**, còn `REQUIRES_NEW` có tên riêng rồi khôi phục tên outer khi kết thúc.
6. Chạy được project Spring Boot/JDBC/H2 để kiểm tra dữ liệu thực sau commit và rollback, đồng thời quan sát tên trong từng scope.
7. Thiết kế convention đặt tên giúp log/tracing hữu ích mà không phát tán thông tin nhạy cảm hoặc tạo metric cardinality quá lớn.

Chủ đề cha là **API giao dịch trực tiếp** của module **Spring Framework — transaction-management**. Tài liệu trình bày **imperative transaction** trên JDBC; reactive transaction dùng `ReactiveTransactionManager`/`TransactionalOperator` và context propagation khác.

## 2. Bốn đối tượng làm nên một transaction programmatic

### 2.1. TransactionDefinition là hợp đồng mô tả ý định

`org.springframework.transaction.TransactionDefinition` là interface cung cấp cấu hình mà một transaction manager nhận được:

- `getPropagationBehavior()`: ví dụ `PROPAGATION_REQUIRED` hoặc `PROPAGATION_REQUIRES_NEW`.
- `getIsolationLevel()`: isolation mong muốn nếu manager mở transaction vật lý mới.
- `getTimeout()`: số giây timeout, hoặc mặc định của manager.
- `isReadOnly()`: read-only hint cho manager/resource.
- `getName()`: tên logic của transaction, có thể `null`.

`TransactionDefinition` **không** tự mở connection, không chứa dữ liệu SQL và không gọi commit. Nó chỉ mô tả **cách transaction manager nên hoạt động**.

### 2.2. DefaultTransactionDefinition là lớp cấu hình mutable

`org.springframework.transaction.support.DefaultTransactionDefinition` là implementation chuẩn, có các setter:

```java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();

def.setName("billing.settle");
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
def.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
def.setTimeout(15); // giây
def.setReadOnly(false);
```

Đây là snippet hợp lệ bên trong một method có các import tương ứng. Nó chỉ **tạo metadata**, chưa bắt đầu transaction. Khi manager gọi `getTransaction(def)`, các thuộc tính được đọc để quyết định mở transaction mới, tham gia transaction có sẵn hoặc từ chối theo propagation.

**Không thay đổi một definition dùng chung sau khi các thread đã bắt đầu sử dụng nó.** Để đơn giản và rõ ràng, nên tạo definition mới hoặc cấu hình một object cố định cho mỗi loại transaction. `DefaultTransactionDefinition` có các setter mutable, không phải nơi lưu trạng thái commit/rollback.

### 2.3. PlatformTransactionManager điều phối transaction

Ba API chính của `org.springframework.transaction.PlatformTransactionManager`:

```java
TransactionStatus status = manager.getTransaction(definition);
manager.commit(status);
manager.rollback(status);
```

`getTransaction` có thể tạo một transaction vật lý mới hoặc cho status tham gia transaction đã có. Hai method hoàn tất transaction **không được gọi liên tiếp trên cùng status**, ví dụ không được commit xong rồi rollback status ấy.

Trong JDBC, một implementation thường dùng là `DataSourceTransactionManager` hoặc `JdbcTransactionManager`. Chúng phải quản lý **cùng DataSource** mà `JdbcTemplate`/repository dùng; nếu code ghi bằng resource ngoài transaction manager, rollback không tự bao phủ nó.

### 2.4. TransactionStatus mô tả scope đang thực thi

`org.springframework.transaction.TransactionStatus` đại diện trạng thái được trả về cho mỗi lời gọi `getTransaction`. Những method đáng biết:

| Method | Ý nghĩa |
| --- | --- |
| `isNewTransaction()` | Scope này có mở transaction mới không? |
| `isRollbackOnly()` | Status đã yêu cầu rollback-only chưa? |
| `setRollbackOnly()` | Chủ động đánh dấu để không commit |
| `isCompleted()` | Status đã hoàn tất hay chưa? |
| `hasSavepoint()` | Status có savepoint được quản lý trong nested transaction không? |
| `flush()` | Yêu cầu flush theo contract của status nếu có cơ chế hỗ trợ |

**Không có `status.getName()` trong contract `TransactionStatus` chuẩn.** Tên được cung cấp qua `TransactionDefinition.getName()` và có thể quan sát bằng `TransactionSynchronizationManager.getCurrentTransactionName()` trong context imperative phù hợp.

## 3. Giá trị mặc định khi new DefaultTransactionDefinition()

Khi không gọi setter, `new DefaultTransactionDefinition()` có đặc tính cơ bản:

| Thuộc tính | Giá trị mặc định | Diễn giải |
| --- | --- | --- |
| Propagation | `PROPAGATION_REQUIRED` | Tham gia transaction đang có; chưa có thì tạo mới |
| Isolation | `ISOLATION_DEFAULT` | Theo mức mặc định của DB/manager |
| Timeout | `TIMEOUT_DEFAULT` (thường biểu diễn bằng -1) | Manager quyết định timeout mặc định |
| Read-only | `false` | Không yêu cầu tối ưu read-only |
| Name | `null` | Không gắn tên tường minh cho programmatic transaction |

Một số setter nhận **hằng số integer** được khai báo trong `TransactionDefinition`; không truyền số “ma thuật” (ví dụ `3`) mà không có ý nghĩa rõ. Chọn hằng số:

```java
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
def.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
def.setTimeout(20);
def.setReadOnly(true);
def.setName("reports.daily");
```

Lưu ý `setReadOnly(true)` chỉ là **hint** hoặc ràng buộc tùy manager/driver/database. Nó không tự cấp quyền bảo mật hoặc chắc chắn cấm mọi câu INSERT. Isolation và timeout thường được áp dụng khi **bắt đầu một transaction vật lý mới**; nếu chỉ tham gia transaction hiện hữu thì outer transaction đã định hình những thuộc tính vật lý đó.

### 3.1. Các propagation thường dùng

| Propagation | Khi transaction T đã tồn tại | Khi chưa có T |
| --- | --- | --- |
| `REQUIRED` | Tham gia T, không tạo physical transaction riêng | Tạo T mới |
| `REQUIRES_NEW` | Suspend T, tạo T2 riêng | Tạo T mới |
| `SUPPORTS` | Tham gia T | Không tạo physical transaction; có thể có synchronization scope |
| `MANDATORY` | Tham gia T | Báo lỗi vì thiếu transaction |
| `NOT_SUPPORTED` | Suspend T để chạy không transaction | Chạy không transaction |
| `NESTED` | Có thể tạo savepoint trong T nếu được manager hỗ trợ | Thường mở T mới theo cấu hình/hỗ trợ |

Bài demo sẽ dùng `REQUIRED` và `REQUIRES_NEW` vì **tên hiện hành** minh họa rất rõ sự khác biệt giữa **logical scope tham gia** và **physical transaction độc lập**.

### 3.2. setIsolationLevelName và setPropagationBehaviorName

Ngoài overload nhận integer constant, `DefaultTransactionDefinition` có setter nhận chuỗi tên hằng số ở các phiên bản Spring phù hợp:

```java
def.setPropagationBehaviorName("PROPAGATION_REQUIRED");
def.setIsolationLevelName("ISOLATION_READ_COMMITTED");
```

Dùng tên hằng rõ ràng thay vì số thô. Đừng truyền tùy tiện chuỗi `"REQUIRED"` nếu API mong tên hằng `"PROPAGATION_REQUIRED"`. Với Java code mới, cú pháp dùng constant integer chuẩn dễ được compiler kiểm tra hơn.

## 4. setName(String): đặt tên cho cái gì?

`setName` ghi một **nhãn logic** vào `DefaultTransactionDefinition`:

```java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setName("orders.create");
System.out.println(def.getName()); // orders.create
```

Tại thời điểm này, **chưa có transaction thực sự**. Mọi thứ mới nằm trong metadata.

Khi gọi `transactionManager.getTransaction(def)` để mở transaction vật lý mới qua manager hỗ trợ synchronization, Spring có thể công bố tên trong thread-bound context. Trong imperative transaction, đọc:

```java
String currentName =
    TransactionSynchronizationManager.getCurrentTransactionName();
```

Kết quả có thể là tên do `setName` cung cấp khi scope đang active, hoặc `null` khi không có tên được công bố. Method này **không tạo transaction** và không phải API trả về DB transaction ID.

### 4.1. Name không phải định danh transaction vật lý duy nhất

Hai lần gọi `getTransaction` với cùng `setName("orders.create")` có thể tạo **hai physical transactions khác nhau**, nhưng chúng mang cùng tên. Điều này hoàn toàn hợp lệ.

Tên dùng để nhóm/nhận diện loại thao tác trong monitoring; muốn correlation giữa một request, các service và SQL cụ thể, hãy dùng thêm trace ID, span ID hoặc business operation ID trong hệ thống observability được bảo vệ. **Không lạm dụng tên transaction làm trace ID**.

### 4.2. Name không đổi commit/rollback policy

Đổi `def.setName("orders.create")` thành `def.setName("orders.cancel")` **không** làm thay đổi isolation, rollback rules hay trạng thái database. Hai names khác nhau có thể có cùng propagation và SQL behavior.

Không sử dụng tên làm cơ chế authorization, lựa chọn transaction manager hoặc khóa nghiệp vụ. Những thứ đó cần cấu hình/resource/API tương ứng.

### 4.3. Tại sao không set tên trực tiếp bằng @Transactional?

Theo tài liệu Spring, đặt **tên tường minh tùy chọn** là khả năng của **programmatic transaction management**. Với declarative `@Transactional` thông thường, tên công bố mặc định thường là **tên lớp đầy đủ + "." + tên phương thức**.

Đặc biệt, cách viết:

```java
@Transactional("mainTransactionManager")
public void saveOrder() {
    // ...
}
```

chọn **transaction manager qualifier** (tương đương thuộc tính value/transactionManager của annotation), **không đặt transaction name** thành `"mainTransactionManager"`. Snippet minh họa chưa có class; nội dung này chỉ giải thích ý nghĩa annotation.

Đừng nhầm `@Transactional` `value` với `DefaultTransactionDefinition.setName`. Hai API phục vụ mục đích khác nhau.

## 5. Vòng đời begin/commit/rollback chuẩn

### 5.1. Sơ đồ

```text
Tạo DefaultTransactionDefinition + setName("orders.create")
                              |
                              v
         PlatformTransactionManager.getTransaction(def)
                              |
                     TransactionStatus s
                              |
             +----------------+----------------+
             |                                 |
        Work thành công                 Work thất bại
             |                                 |
             v                                 v
        commit(s)                         rollback(s)
             |                                 |
             +---------------+-----------------+
                             |
                      status hoàn tất
                             |
                  Không dùng lại status
```

Một transaction status do manager trả về là **một lần tham gia scope cụ thể**; không được lưu nó trong singleton và dùng lại cho request sau.

### 5.2. Mẫu Java kiểm soát RuntimeException và Error

```java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setName("inventory.reserve");
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);

TransactionStatus status = manager.getTransaction(def);
try {
    performBusinessWrites();
} catch (RuntimeException | Error ex) {
    manager.rollback(status);
    throw ex;
}
manager.commit(status);
```

Đoạn này là **mẫu minh họa**; cần một manager được inject và implementation của `performBusinessWrites`.

Hai chi tiết quan trọng:

1. `commit(status)` nằm **ngoài try-catch của business work**. Khi commit đã bắt đầu mà ném lỗi, cố `rollback(status)` thêm một lần có thể sai vì transaction đã cleanup/hoàn thành; kết quả commit khi mất ACK có thể còn chưa xác định.
2. Bắt `RuntimeException | Error` là **một chính sách do code tự chọn**, không phải Spring tự áp quy tắc declarative lên mọi lời gọi low-level. Nếu business method ném checked exception, bạn phải thiết kế đường rollback cho nó khi cần.

Trong ví dụ thực hành, ta chủ động rollback một trường hợp thất bại để chứng minh trạng thái DB.

### 5.3. Checked exception với API trực tiếp

Khác với transaction advice có rollback rule mặc định, khi dùng `PlatformTransactionManager` **trực tiếp**, caller **phải quyết định** lúc nào gọi rollback/commit. Ví dụ nghiệp vụ nhập file trả `IOException` checked, nhưng toàn bộ thao tác DB cần atomic:

```java
TransactionStatus s = manager.getTransaction(def);
try {
    importFileAndPersist(); // Có thể throws IOException.
} catch (IOException | RuntimeException | Error ex) {
    manager.rollback(s);
    throw ex;
}
manager.commit(s);
```

Mã minh họa cần method `importFileAndPersist`, definition và manager. Nó nêu một policy “hủy cả transaction cho IOException và unchecked errors”. Nếu nghiệp vụ cho phép commit dù checked exception, code phải quyết định rõ; không suy luận rằng low-level API sẽ tự rollback khi Java method thoát bằng checked exception.

### 5.4. setRollbackOnly() khác rollback(status)

`status.setRollbackOnly()` đánh dấu **ý định không commit**, còn `manager.rollback(status)` kết thúc (hoặc tác động lên) scope transaction qua manager. Với một scope **tham gia REQUIRED** trong transaction chung, rollback thường đánh dấu transaction vật lý chung rollback-only; nó không thực hiện commit/rollback vật lý độc lập cho inner.

Nếu outer cố commit transaction vật lý đã bị một inner scope đánh dấu rollback-only, có thể nhận `UnexpectedRollbackException`. Đây là hành vi quan trọng khi dùng API trực tiếp và các service declarative lồng nhau.

### 5.5. Không commit rồi rollback cùng status

Ví dụ sai:

```java
TransactionStatus status = manager.getTransaction(def);
manager.commit(status);
manager.rollback(status); // Sai: status đã hoàn tất.
```

Kết quả có thể là `IllegalTransactionStateException`. Nếu cần transaction khác, tạo definition phù hợp, gọi `getTransaction` lại để lấy **status mới**. Trong flow có exception lúc commit, đừng sử dụng một fallback “rollback để an toàn” nếu manager đã cleanup; xử lý outcome không chắc chắn bằng idempotency và tra cứu trạng thái dữ liệu.

## 6. Dự án thực hành chạy được: tên giao dịch và phạm vi lồng nhau

Dự án dùng **Java 17+**, **Spring Boot 3.3.13**, **Spring JDBC**, **H2 in-memory**, **Gradle 8.x**. Ta dùng `PlatformTransactionManager` trực tiếp; không cần `@Transactional` trên class chạy demo.

Năm quan sát chính:

- **A — Commit:** đặt tên `orders.create`, mở T, INSERT rồi commit; DB còn record.
- **B — Rollback:** đặt tên `orders.fail`, INSERT rồi chủ động rollback khi lỗi runtime; DB không còn record.
- **C — Inner REQUIRED:** outer có tên `orders.batch`, inner đề xuất `inventory.join` nhưng thực chất tham gia T. `getCurrentTransactionName()` vẫn cho thấy tên outer; commit inner không commit vật lý, outer rollback cả hai record.
- **D — Inner REQUIRES_NEW:** outer `checkout.outer`, inner `audit.persist` mở T2 riêng. Trong inner tên là `audit.persist`; sau inner commit, tên outer được khôi phục; outer rollback nhưng record audit vẫn tồn tại.
- **E — Scope đã kết thúc:** ngoài các transaction, tên hiện hành trở lại `null`.

Bài kiểm chứng **không đòi chạy hai thread**: lồng transaction qua `getTransaction` và `REQUIRES_NEW` trong cùng thread đủ thể hiện suspend/resume; mỗi physical transaction dùng connection phù hợp từ pool.

### 6.1. Cấu trúc thư mục

```text
named-tx-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/edu/transactionnames/
    │   ├── TransactionNamesApplication.java
    │   └── TransactionNamesDemo.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'named-tx-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'edu'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-jdbc` đưa vào `JdbcTemplate` và transaction support. Chúng ta đăng ký một `DataSourceTransactionManager` tường minh để mọi lần gọi `getTransaction` quản lý cùng `DataSource` của JDBC. Vì không dùng declarative `@Transactional` trong demo, không cần AOP starter để hiểu cơ chế programmatic.

**`src/main/resources/application.properties`**

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:named_tx;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
```

Pool 5 chỉ để đảm bảo demo `REQUIRES_NEW` khi outer đang giữ một connection có thể mượn connection thứ hai. Production phải sizing theo concurrency và số tầng lồng nhau; không lấy số 5 làm cấu hình tối ưu chung.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_event (
    id INT PRIMARY KEY,
    event_name VARCHAR(80) NOT NULL
);
```

Mỗi ca sử dụng id khác nhau; H2 in-memory bắt đầu trống ở mỗi lần khởi động JVM mới. Nếu kết nối tới DB bền vững, phải reset test data để tránh trùng primary key.

### 6.2. Spring Boot application: chỉ một manager cho một DataSource

**`src/main/java/edu/transactionnames/TransactionNamesApplication.java`**

```java
package edu.transactionnames;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class TransactionNamesApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransactionNamesApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner run(TransactionNamesDemo demo) {
        return args -> demo.demonstrate();
    }
}
```

Ứng dụng không có web server. `CommandLineRunner` gọi bean demo, **không** được `@Transactional` đánh dấu. Vì thế ở đầu/kết thúc runner không có transaction; mỗi lần `getTransaction` trong `TransactionNamesDemo` tạo hoặc tham gia transaction theo definition.

### 6.3. TransactionNamesDemo: một file Java hoàn chỉnh

**`src/main/java/edu/transactionnames/TransactionNamesDemo.java`**

```java
package edu.transactionnames;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class TransactionNamesDemo {
    private final PlatformTransactionManager manager;
    private final JdbcTemplate jdbc;

    public TransactionNamesDemo(
            PlatformTransactionManager manager, JdbcTemplate jdbc) {
        this.manager = manager;
        this.jdbc = jdbc;
    }

    public void demonstrate() {
        System.out.println("before name=" + currentName());

        committed();
        rolledBack();
        requiredJoin();
        requiresNew();

        System.out.println("after name=" + currentName());
    }

    private void committed() {
        DefaultTransactionDefinition def =
            definition("orders.create",
                TransactionDefinition.PROPAGATION_REQUIRED);

        // Tham khảo thêm các thuộc tính khi tạo transaction mới.
        def.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED);
        def.setTimeout(10);
        def.setReadOnly(false);

        TransactionStatus status = manager.getTransaction(def);
        try {
            System.out.println(
                "A name=" + currentName() +
                " new=" + status.isNewTransaction());
            insert(1, "committed");
        } catch (RuntimeException | Error ex) {
            manager.rollback(status);
            throw ex;
        }
        manager.commit(status);
        System.out.println("A count=" + count(1));
    }

    private void rolledBack() {
        TransactionStatus status = manager.getTransaction(
            definition("orders.fail",
                TransactionDefinition.PROPAGATION_REQUIRED));

        try {
            System.out.println(
                "B name=" + currentName() +
                " new=" + status.isNewTransaction());
            insert(2, "should-disappear");
            throw new IllegalStateException("intentional");
        } catch (RuntimeException | Error ex) {
            manager.rollback(status);
            if (!(ex instanceof IllegalStateException)
                    || !"intentional".equals(ex.getMessage())) {
                throw ex;
            }
            System.out.println("B rolledBack=" + ex.getMessage());
        }
        System.out.println("B count=" + count(2));
    }

    private void requiredJoin() {
        TransactionStatus outer = manager.getTransaction(
            definition("orders.batch",
                TransactionDefinition.PROPAGATION_REQUIRED));
        try {
            System.out.println(
                "C outer=" + currentName() +
                " new=" + outer.isNewTransaction());
            insert(3, "outer-required");

            TransactionStatus inner = manager.getTransaction(
                definition("inventory.join",
                    TransactionDefinition.PROPAGATION_REQUIRED));
            try {
                System.out.println(
                    "C inner=" + currentName() +
                    " new=" + inner.isNewTransaction());
                insert(4, "inner-required");
            } catch (RuntimeException | Error ex) {
                manager.rollback(inner);
                throw ex;
            }
            manager.commit(inner);

            System.out.println("C afterInner=" + currentName());
        } catch (RuntimeException | Error ex) {
            manager.rollback(outer);
            throw ex;
        }

        // Cố ý rollback outer để chứng minh inner REQUIRED chưa commit riêng.
        manager.rollback(outer);
        System.out.println(
            "C counts=" + count(3) + "," + count(4));
    }

    private void requiresNew() {
        TransactionStatus outer = manager.getTransaction(
            definition("checkout.outer",
                TransactionDefinition.PROPAGATION_REQUIRED));
        try {
            System.out.println(
                "D outer=" + currentName() +
                " new=" + outer.isNewTransaction());
            insert(5, "outer-will-rollback");

            TransactionStatus inner = manager.getTransaction(
                definition("audit.persist",
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW));
            try {
                System.out.println(
                    "D inner=" + currentName() +
                    " new=" + inner.isNewTransaction());
                insert(6, "inner-commits");
            } catch (RuntimeException | Error ex) {
                manager.rollback(inner);
                throw ex;
            }
            manager.commit(inner);

            System.out.println("D resumed=" + currentName());
        } catch (RuntimeException | Error ex) {
            manager.rollback(outer);
            throw ex;
        }

        // Inner đã commit độc lập. Outer mới rollback.
        manager.rollback(outer);
        System.out.println(
            "D counts=" + count(5) + "," + count(6));
    }

    private static DefaultTransactionDefinition definition(
            String name, int propagation) {
        DefaultTransactionDefinition def =
            new DefaultTransactionDefinition();
        def.setName(name);
        def.setPropagationBehavior(propagation);
        return def;
    }

    private void insert(int id, String eventName) {
        jdbc.update(
            "INSERT INTO tx_event(id, event_name) VALUES (?, ?)",
            id, eventName
        );
    }

    private int count(int id) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_event WHERE id = ?",
            Integer.class, id
        );
        return result;
    }

    private static String currentName() {
        return TransactionSynchronizationManager
            .getCurrentTransactionName();
    }
}
```

Các import/class/method ở đây khớp Java 17 và Spring Framework 6.1 đi kèm Spring Boot 3.3. Các helper `definition`, `insert`, `count`, `currentName` đều có implementation trong cùng file.

**Vì sao code không dùng `@Transactional`?** Mục tiêu là học `DefaultTransactionDefinition` và `PlatformTransactionManager` trực tiếp. Annotation không cần để manager tạo transaction; lời gọi `getTransaction` tự thực hiện transaction boundary.

**Vì sao status khác nhau?** Mỗi lời gọi `getTransaction(def)` trả `TransactionStatus` cho một logical scope. Inner REQUIRED có status riêng nhưng `isNewTransaction() == false`; inner REQUIRES_NEW có status riêng và `isNewTransaction() == true`, vì manager mở physical transaction mới.

### 6.4. Chạy ứng dụng và dự đoán console

Tại thư mục `named-tx-demo` với JDK 17+ và Gradle 8.x tương thích:

```bash
gradle bootRun
```

Nếu project có Gradle Wrapper được cấu hình phù hợp, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Lần đầu Gradle cần tải dependencies; Java code này không thể biên dịch bằng `javac` thuần với JDK classpath do phụ thuộc Spring/H2.

Bỏ qua log từ Gradle/Spring/Hikari, **các dòng `System.out.println` dự kiến theo thứ tự**:

```text
before name=null
A name=orders.create new=true
A count=1
B name=orders.fail new=true
B rolledBack=intentional
B count=0
C outer=orders.batch new=true
C inner=orders.batch new=false
C afterInner=orders.batch
C counts=0,0
D outer=checkout.outer new=true
D inner=audit.persist new=true
D resumed=checkout.outer
D counts=0,1
after name=null
```

Đây là **output dự kiến từ code** trong điều kiện demo H2 sạch, không phải bản log đã được chụp từ một lần build thực thi. Nếu khác, kiểm tra có một transaction bên ngoài runner hay không, bean manager có đúng DataSource không, dữ liệu cũ còn trong H2 hay không và có code nào bật transaction synchronization khác.

### 6.5. Diễn giải những số liệu quan trọng nhất

| Ca | Tên hiện hành | Physical transaction | Kết quả dữ liệu |
| --- | --- | --- | --- |
| Trước runner | `null` | Không có | Chưa viết |
| A: tạo `orders.create` | `orders.create` | T1 mới | id 1 commit, count 1 |
| B: tạo `orders.fail` | `orders.fail` | T2 mới | id 2 rollback, count 0 |
| C: outer `orders.batch` | `orders.batch` | T3 mới | id 3 đang chờ commit |
| C: inner `inventory.join` REQUIRED | Vẫn `orders.batch` | **Tham gia T3** | id 4 chưa commit riêng |
| C: outer rollback | Không còn tên trong scope | T3 rollback | id 3 và id 4 đều 0 |
| D: outer `checkout.outer` | `checkout.outer` | T4 mới | id 5 chưa commit |
| D: inner `audit.persist` REQUIRES_NEW | `audit.persist` | T5 độc lập | id 6 commit riêng |
| D: resume và outer rollback | `checkout.outer` rồi `null` | T4 rollback | id 5 = 0; id 6 = 1 |

**Quan sát quyết định:** inner `REQUIRED` cấu hình `setName("inventory.join")` nhưng tên đang được Spring công bố vẫn là `orders.batch` vì nó **tham gia physical transaction đã có** và không tạo một synchronization context mới thay thế outer. Inner `REQUIRES_NEW` lại thực sự mở physical transaction mới, nên có tên `audit.persist` trong inner rồi khôi phục tên outer khi resume.

Đừng xem tên là bằng chứng duy nhất của atomicity. Chính kết quả readback `C counts=0,0` so với `D counts=0,1` mới cho thấy khác biệt commit/rollback vật lý.

### 6.6. Tại sao C inner commit không giữ được id 4?

Trong case C:

```text
getTransaction("orders.batch", REQUIRED)   -> T3 mới
  INSERT id=3
  getTransaction("inventory.join", REQUIRED) -> join T3
    INSERT id=4
  commit(innerStatus)                        -> kết thúc scope logic
  [T3 vẫn chưa commit]
rollback(outerStatus)                        -> rollback T3
SQL readback id=3 = 0, id=4 = 0
```

`manager.commit(innerStatus)` khi inner chỉ tham gia `REQUIRED` **không tương đương JDBC Connection.commit() cho toàn T3**. Transaction manager biết status tham gia chứ không sở hữu transaction vật lý.

### 6.7. Tại sao D inner có tên riêng rồi trở về tên outer?

Trong case D:

```text
getTransaction("checkout.outer", REQUIRED) -> T4 mới
  [Spring current name: checkout.outer]
  INSERT id=5

  getTransaction("audit.persist", REQUIRES_NEW)
    suspend T4 / outer synchronization
    begin T5
    [Spring current name: audit.persist]
    INSERT id=6
  commit(innerStatus) -> COMMIT T5
    resume T4 / outer synchronization
  [Spring current name: checkout.outer]

rollback(outerStatus) -> ROLLBACK T4
SQL readback id=5 = 0, id=6 = 1
```

Đây là đặc tính **REQUIRES_NEW**, không phải `setName` đã gây ra transaction độc lập. Nếu giữ propagation REQUIRED và chỉ đổi tên inner thành `audit.persist`, inner vẫn tham gia T4.

**Lưu ý production:** inner REQUIRES_NEW thường phải xin thêm JDBC connection trong khi outer vẫn giữ resource. Pool quá nhỏ hoặc thao tác inner đụng row outer đang khóa có thể gây chờ/deadlock-like timeout. Chỉ dùng khi nghiệp vụ thực sự cho phép inner commit/rollback riêng.

## 7. Tên của transaction hiện hành không phải dữ liệu từ database

### 7.1. Thread-bound metadata trong imperative Spring

`TransactionSynchronizationManager.getCurrentTransactionName()` đọc thông tin do Spring transaction infrastructure công bố trên **thread hiện hành**. Nó không chạy `SELECT transaction_id`, không truy vấn DB session và không cấp ID transaction.

Bạn có thể có:

```text
Def A name="orders.create" -> JDBC transaction T1
Def B name="orders.create" -> JDBC transaction T2
```

Hai transactions tách biệt, cùng nhãn. Ngược lại, khi một inner `REQUIRED` tham gia T1, nó có thể có definition name khác nhưng **current name không đổi** do outer đang làm chủ current context.

### 7.2. Sync active và actual transaction active

Các API:

```java
boolean sync =
    TransactionSynchronizationManager.isSynchronizationActive();

boolean actual =
    TransactionSynchronizationManager.isActualTransactionActive();
```

Không phải lúc nào hai giá trị đều bằng nhau. `SUPPORTS` không có physical transaction có thể vẫn có synchronization scope tùy `AbstractPlatformTransactionManager` configuration; việc current name khác null hoặc sync active **không đủ chứng minh JDBC transaction đã bắt đầu**. Muốn kiểm tra commit/rollback, cần data source đúng và DB readback.

### 7.3. Không tự gọi setCurrentTransactionName để “đổi tên”

`TransactionSynchronizationManager.setCurrentTransactionName(...)` là API hạ tầng phục vụ manager khi begin/cleanup. Code business **không nên tự gọi** nó để “đặt tên cho transaction” trong khi manager đang quản lý scope; làm vậy dễ phá metadata, restore behavior khi nested/suspend và khiến log khó hiểu.

Đặt tên đúng cách là **trước** `getTransaction` bằng `DefaultTransactionDefinition.setName(...)`, hoặc dùng `TransactionTemplate.setName(...)` khi cần template.

### 7.4. Propagation khác có ảnh hưởng tới tên

| Tình huống | Kết quả thường thấy trên DataSourceTransactionManager |
| --- | --- |
| Không có outer, `REQUIRED` named | Manager tạo physical T, current name là tên định nghĩa |
| Đã có outer T, inner `REQUIRED` named | Inner tham gia T, current name vẫn là tên của outer |
| Đã có outer T, inner `REQUIRES_NEW` named | Suspend outer; inner có tên riêng; resume trả lại outer name |
| `NESTED` với savepoint | Không mở một physical transaction riêng; đừng giả định nó thay tên outer |
| `SUPPORTS` không có T | Có thể tồn tại logical/synchronization scope; xem mode manager, không suy current name = physical T |
| Sau commit/rollback đã cleanup | Current name được manager khôi phục/xóa đúng scope; ngoài transaction thường `null` |

Những câu trong bảng là mô tả **mô hình imperative của manager và synchronization**, không phải hợp đồng cho mọi reactive/JTA/vendor transaction. Với nhiều manager hoặc synchronization mode tùy chỉnh, kết quả có thể khác.

## 8. Đặt tên để phục vụ quan sát, không gây vấn đề vận hành

Một convention nên giúp người vận hành xác định **loại nghiệp vụ**, không tiết lộ thông tin cá nhân:

| Tên đề xuất | Lý do |
| --- | --- |
| `orders.create` | Ổn định, mô tả một loại transaction |
| `payments.capture` | Cho biết operation đã được quản lý |
| `inventory.adjust` | Dễ nhóm theo luồng xử lý |
| `reports.monthly.close` | Phân biệt batch/report có mục đích |
| `audit.persistAttempt` | Gợi ý nếu transaction độc lập dùng cho audit |

Tránh:

- `"orders.create.customer-email@example.com"`: lộ PII.
- `"orders.create.cardNumber=..."`: nguy cơ lộ dữ liệu nhạy cảm.
- `"orders.create#" + UUID.randomUUID()`: tên quá nhiều giá trị duy nhất có thể làm metric/log cardinality rất cao.
- Chỉ đặt `"transaction"` cho mọi nghiệp vụ: không hỗ trợ debug.
- Đặt tên mô tả sai semantics, chẳng hạn `"committed"` trước khi biết transaction có commit thành công hay không.

**Nên tách transaction name (low cardinality) khỏi correlation ID (high cardinality)**. Correlation ID nên nằm trong trace/MDC/context được thiết kế riêng; cũng phải tuân thủ policy bảo mật và hạn chế dữ liệu nhạy cảm.

Tên trong Spring chỉ hữu ích với công cụ thực sự thu thập/hiển thị nó. Không mặc nhiên khẳng định mọi APM tự thêm transaction name vào mọi SQL span; phải xác minh instrumentation/agent đang triển khai.

## 9. Chọn trực tiếp PlatformTransactionManager hay TransactionTemplate?

Spring khuyên dùng `TransactionTemplate` cho nhiều trường hợp **imperative programmatic transaction**, bởi nó giảm boilerplate begin/commit/rollback. `DefaultTransactionDefinition` vẫn hữu ích để hiểu metadata và khi cần điều khiển manager trực tiếp.

So sánh:

| Tiêu chí | Manager trực tiếp | TransactionTemplate |
| --- | --- | --- |
| Tạo transaction | `getTransaction(def)` | `execute(callback)` |
| Hoàn tất transaction | Tự gọi `commit`/`rollback` | Template xử lý |
| Đặt tên | `DefaultTransactionDefinition.setName` | `TransactionTemplate.setName` |
| Propagation/isolation/timeout | Definition setters | Template setters |
| Kiểm soát nhiều scopes lồng nhau | Rõ ràng nhưng nhiều code | Có thể tạo template riêng theo scope |
| Rủi ro quên rollback, commit trùng status | Cao hơn | Thấp hơn nhờ callback |

### 9.1. Một ví dụ TransactionTemplate cùng name

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setName("inventory.reserve");
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);

template.executeWithoutResult(status -> {
    jdbc.update("UPDATE inventory SET quantity = quantity - 1 WHERE id = ?", 5);
});
```

Đây là **mảnh code minh họa**: cần manager, jdbc, bảng inventory và import. Template cũng dùng transaction manager; `setName` thiết lập metadata tương tự, sau đó callback được chạy trong boundary transaction.

### 9.2. Template có cấu hình mutable

`TransactionTemplate` có configuration state; một instance có thể dùng lại giữa các thread khi **không thay đổi setters trong lúc sử dụng**. Nếu cần nhiều tên/propagation khác nhau, tạo các instance cấu hình riêng hoặc một factory phù hợp; không mutate một template singleton theo từng request đồng thời.

### 9.3. TransactionTemplate và ngoại lệ

Khi callback ném unchecked exception, `TransactionTemplate` tự xử lý rollback theo cơ chế template. Khi muốn rollback nhưng không ném exception, callback có thể gọi `status.setRollbackOnly()`. Với checked exception trong callback, Java lambda/functional interface cần thiết kế chuyển đổi/xử lý phù hợp; không giả định mọi checked exception đều được ném xuyên suốt giống low-level API.

Trong bài này, demo sử dụng manager trực tiếp để hiển thị rõ **`DefaultTransactionDefinition` → `getTransaction` → `TransactionStatus` → `commit/rollback`**.

## 10. Các lỗi thường gặp với getTransaction, setName và rollback

### Lỗi 1 — Nghĩ setName mở transaction ngay

`def.setName("orders.create")` chỉ sửa metadata. Chỉ khi manager nhận `getTransaction(def)` mới tạo hoặc tham gia scope.

### Lỗi 2 — Nghĩ tên là physical transaction ID

Một tên có thể lặp trên nhiều lần gọi; một physical transaction có thể có nhiều logical scopes với definitions đặt tên khác nhau. Nếu cần xác định transaction phía DB, sử dụng công cụ DB-specific và correlation đáng tin.

### Lỗi 3 — Đọc current name trước khi gọi getTransaction

`TransactionSynchronizationManager.getCurrentTransactionName()` khi chưa có transaction context thông thường trả `null`, dù bạn vừa tạo một `DefaultTransactionDefinition` đặt tên.

### Lỗi 4 — Inner REQUIRED đặt tên khác nhưng không thấy tên mới

Nếu inner tham gia transaction đang mở, manager có thể giữ synchronization/name của outer. Đổi inner sang `REQUIRES_NEW` chỉ để thấy tên khác là sai nếu nghiệp vụ vẫn cần atomicity chung.

### Lỗi 5 — Bắt exception rồi quên rollback

Với API manager trực tiếp, Java `catch` không tự kết thúc transaction. Phải gọi `rollback(status)` hoặc thiết kế `TransactionTemplate`; nếu không, connection có thể bị giữ và dữ liệu ở trạng thái khó kiểm soát.

### Lỗi 6 — Commit rồi cố rollback trong catch chung

Nếu để `commit(status)` trong cùng try-catch quanh toàn bộ flow, một lỗi ngay tại commit có thể khiến catch gọi `rollback(status)` **lần thứ hai**. Manager có thể đã hoàn tất/cleanup status hoặc DB commit có kết quả chưa rõ. Tách xử lý lỗi business khỏi commit và thiết kế idempotency nếu cần.

### Lỗi 7 — Dùng lại một TransactionStatus cho transaction khác

Status chỉ thuộc một logical scope. Sau commit/rollback nó đã completed; không được lưu static/singleton để tái sử dụng cho request sau.

### Lỗi 8 — Hiểu setReadOnly(true) là chặn ghi chắc chắn

Read-only là hint/behavior phụ thuộc manager và DB. Nó không thay thế quyền DB, constraint và kiểm tra nghiệp vụ.

### Lỗi 9 — Isolation/timeout của inner REQUIRED tự thay đổi outer

Một inner REQUIRED tham gia T đã có thường không thay physical isolation/timeout mà outer đã thiết lập. Có thể bật validation mode của manager để phát hiện mismatch thay vì trông chờ override.

### Lỗi 10 — Dùng sai manager hoặc DataSource

Một programmatic transaction do manager A quản lý không tự rollback thao tác dùng connection B không tham gia cùng tài nguyên. Kiểm tra bean, DataSource, EntityManagerFactory và các repository thật.

### Lỗi 11 — Bật tên transaction mà không bảo vệ dữ liệu

Nếu transaction name chứa tên người dùng, token, email hoặc ID có thể định danh, thông tin ấy có thể đi vào log/tracing/metrics. Dùng nhãn nghiệp vụ ổn định và correlation ID đã được quản trị riêng.

### Lỗi 12 — Mở transaction rồi gọi API mạng rất lâu

Transaction vật lý có thể giữ DB connection và row locks trong thời gian chờ. Sử dụng scope ngắn và workflow idempotent/outbox/saga khi cần phối hợp hệ thống ngoài; đặt tên giao dịch không tự giảm lock contention.

## 11. Debug khi currentName không giống expected

Nếu `getCurrentTransactionName()` trả `null` hoặc tên khác:

| Điều cần hỏi | Cách kiểm tra |
| --- | --- |
| Có gọi `getTransaction(def)` chưa? | Xem thứ tự gọi, log manager |
| `def.getName()` là gì ngay trước khi gọi? | Assert tên, tránh mutate shared definition |
| Manager có mở transaction/synchronization mới không? | `status.isNewTransaction()` và `TransactionSynchronizationManager` flags |
| Có outer transaction được tạo trước không? | `REQUIRED` chỉ tham gia; current name có thể là outer |
| Inner có `REQUIRES_NEW` thật không? | Kiểm tra status, suspend/resume, transaction manager |
| Có nhiều transaction managers không? | Kiểm tra bean thực được inject và DataSource tương ứng |
| Code chạy trên thread khác không? | Imperative synchronization/name là thread-bound |
| Có ai gọi thủ công `setCurrentTransactionName` không? | Tìm code hạ tầng can thiệp lifecycle |
| Có measurement ở ngoài transaction scope không? | Sau cleanup, current name thường null |
| Có transaction test bao ngoài không? | Spring TestContext có thể mở T trước code demo |

Các log tạm thời có thể bật:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Với **manager API trực tiếp**, log transaction manager quan trọng hơn log interceptor vì code có thể không đi qua declarative `TransactionInterceptor`. Không đánh giá thành công chỉ từ “name printed”; đọc lại DB và scope status để kiểm chứng commit/rollback.

### 11.1. Khi chạy @Async hoặc Executor

Mô hình `TransactionSynchronizationManager` imperative gắn với thread. `@Async` hoặc `Executor` không tự đem transaction context/name sang thread khác. Nếu phương thức khác chạy trên worker thread, nó cần transaction context riêng và name riêng; không dùng một string currentName ở thread request để suy rằng DB changes của thread worker tham gia T cũ.

### 11.2. Khi dùng reactive stack

Spring reactive sử dụng `ReactiveTransactionManager` và `org.springframework.transaction.reactive.TransactionSynchronizationManager` khác mô hình static thread-bound imperative. Không lấy ví dụ JDBC trên đây để suy rằng Reactor subscriber có thể đọc bằng static method imperative. Dùng `TransactionalOperator` và Reactor context phù hợp.

### 11.3. Khi transaction đã kết thúc nhưng DB kết quả chưa chắc chắn

Nếu exception xảy ra tại commit và connection/ACK bị mất, trạng thái commit đôi khi có thể **chưa xác định**. Transaction name chỉ là nhãn; cần operation ID bền vững, idempotency và đối soát để biết business operation đã được thực hiện chưa.

## 12. Kiểm thử chính xác: tên, scope và dữ liệu

Một test có ý nghĩa nên xác minh **cả metadata lẫn trạng thái DB sau transaction**:

1. Dùng một Spring context thật với `PlatformTransactionManager` gắn đúng resource.
2. Tạo definition mới, `setName("test.operation")`, gọi `getTransaction` rồi assert current name trong scope.
3. Kiểm tra `status.isNewTransaction()` khi không có outer transaction.
4. INSERT record rồi commit, đọc lại trên connection/transaction phù hợp sau boundary; assert record còn.
5. INSERT record khác rồi rollback, đọc lại; assert record đã biến mất.
6. Mở outer `REQUIRED` đặt tên A, inner `REQUIRED` đặt tên B; assert inner new=false và current name vẫn A trong manager demo.
7. Mở outer `REQUIRED` đặt tên A, inner `REQUIRES_NEW` đặt tên C; assert trong inner là C, sau khi inner hoàn tất tên outer A được khôi phục.
8. Rollback outer sau inner NEW commit để xác minh inner đã commit độc lập; rollback outer sau inner REQUIRED success để xác minh inner chưa commit riêng.
9. Sau mỗi call, assert không còn transaction/name bị rò rỉ sang bước chạy khác.

### 12.1. Bẫy @Transactional trên method test

Nếu Spring TestContext mở transaction cho method test mang `@Transactional`, một programmatic `REQUIRED` có thể **tham gia transaction của test** thay vì tạo transaction vật lý mới. Khi đó `isNewTransaction()` có thể false, tên currentName là của test/outer, và các commit của inner scope không làm dữ liệu bền vững như bài demo.

Để kiểm thử như một caller thật không có transaction, dùng test method không `@Transactional`, hoặc chủ động điều khiển test transaction bằng `TestTransaction` rồi đọc lại ở boundary chính xác.

### 12.2. Kiểm tra rollback-only và UnexpectedRollbackException

Nếu inner status tham gia cùng T, gọi `manager.rollback(innerStatus)` có thể làm T chung rollback-only. Outer code vẫn có thể return bình thường nhưng khi `manager.commit(outerStatus)` chạy, Spring có thể rollback và ném `UnexpectedRollbackException`. Đó không phải “bug commit”: manager cố ý không báo commit giả.

Nếu nghiệp vụ cần inner commit độc lập, `REQUIRES_NEW` là một lựa chọn nhưng thay đổi atomicity. Không đổi propagation chỉ để triệt tiêu exception mà không kiểm tra dữ liệu còn lại sau lỗi.

## 13. Tự kiểm tra kiến thức

**Câu 1.** `DefaultTransactionDefinition def = new DefaultTransactionDefinition();` có tự mở DB transaction không?

**Đáp án:** Không. Đây chỉ là metadata; phải gọi `PlatformTransactionManager.getTransaction(def)`.

**Câu 2.** `def.setName("report.monthly")` có làm tên transaction vật lý phía DB thành chuỗi này không?

**Đáp án:** Không phải bảo đảm. Nó là tên logic mà Spring có thể công bố/đưa vào transaction monitoring. Đừng dùng như DB transaction ID.

**Câu 3.** Làm sao đọc tên hiện hành trong Spring imperative?

**Đáp án:** `TransactionSynchronizationManager.getCurrentTransactionName()` trong scope phù hợp. Có thể nhận `null` khi chưa có tên/context.

**Câu 4.** Outer mở T tên `"orders.batch"`, inner `REQUIRED` setName `"inventory.join"`. Inner thấy tên nào trong demo?

**Đáp án:** `"orders.batch"`, vì inner tham gia T đang có; nó không mở context vật lý mới để thay tên outer.

**Câu 5.** Thay inner thành `REQUIRES_NEW` với tên `"audit.persist"`. Điều gì xảy ra?

**Đáp án:** Spring suspend T của outer và mở T2 mới; trong inner thấy `"audit.persist"`, sau commit/rollback T2 và resume outer lại thấy tên outer.

**Câu 6.** Inner `REQUIRED` đã gọi `manager.commit(innerStatus)`. Dữ liệu inner đã commit vật lý chưa?

**Đáp án:** Chưa chắc. Nếu inner chỉ tham gia outer T, commit inner status không commit T vật lý; outer rollback sau đó hủy cả thay đổi của inner.

**Câu 7.** Có nên gọi `rollback(status)` trong catch khi `commit(status)` ném exception không?

**Đáp án:** Không được làm mù quáng. Status có thể đã completed/cleanup hoặc outcome phía DB chưa rõ. Phải xử lý theo lifecycle manager và business idempotency.

**Câu 8.** `@Transactional("transactionManager")` có đặt tên giao dịch là `"transactionManager"` không?

**Đáp án:** Không. Chuỗi ấy chọn bean transaction manager/qualifier, không phải transaction name được set bằng `DefaultTransactionDefinition.setName`.

**Câu 9.** Có thể dùng `TransactionTemplate` để đặt tên không?

**Đáp án:** Có. `TransactionTemplate` có `setName(...)` và dùng `execute`/`executeWithoutResult` để giảm boilerplate trực tiếp.

**Câu 10.** Vì sao nên dùng tên `"orders.create"` thay vì `"orders.create#UUID"` trong metric?

**Đáp án:** Tên ổn định giúp nhóm cùng loại transaction, không tăng cardinality vô hạn hoặc tiết lộ identifier. Request/operation ID nên ở trace context riêng với chính sách bảo vệ.

## 14. Tài liệu tham khảo chính thức

- Spring Framework — Programmatic Transaction Management, `Using the PlatformTransactionManager`: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework 6.1 — `DefaultTransactionDefinition` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html
- Spring Framework 6.1 — `TransactionDefinition` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework 6.1 — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html

**Ghi nhớ:** `DefaultTransactionDefinition` mô tả transaction sẽ được quản lý ra sao; `setName` đặt một **tên logic để quan sát**, không tự mở transaction. `PlatformTransactionManager.getTransaction` trả status để code **commit/rollback đúng một lần**. Khi tham gia `REQUIRED`, tên hiện hành có thể vẫn là outer; với `REQUIRES_NEW`, inner có tên riêng rồi resume outer name. Hãy dùng tên ổn định và xác minh cả thread-bound name lẫn **trạng thái DB sau transaction**.