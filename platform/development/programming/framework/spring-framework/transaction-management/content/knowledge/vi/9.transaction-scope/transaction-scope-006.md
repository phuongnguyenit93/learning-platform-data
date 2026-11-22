# setValidateExistingTransaction và phát hiện cấu hình không tương thích trong Spring Transaction Management

## 1. Mục tiêu và vấn đề cần giải quyết

Khi nhiều service gọi nhau, mỗi method có thể khai báo thuộc tính giao dịch riêng bằng `@Transactional`, chẳng hạn:

- Service ngoài: `@Transactional(isolation = Isolation.READ_COMMITTED)`.
- Service trong: `@Transactional(isolation = Isolation.SERIALIZABLE)`.
- Hoặc service ngoài chỉ đọc: `@Transactional(readOnly = true)`, trong khi service trong yêu cầu quyền đọc-ghi: `@Transactional(readOnly = false)`.

Nếu cả hai method dùng `Propagation.REQUIRED` (mặc định), method trong thường **tham gia cùng một giao dịch vật lý** đã được method ngoài mở. Nó **không tự nâng isolation** hoặc đảo thuộc tính read-only của JDBC connection chỉ vì trên method trong có annotation khác. Mặc định Spring chấp nhận việc tham gia này theo cách khá “dễ tính” (*lenient*), khiến cấu hình không tương thích có thể bị bỏ qua mà không có lỗi.

`setValidateExistingTransaction(true)` là lựa chọn trên một số **Spring transaction manager** để chuyển sang kiểm tra nghiêm ngặt khi một method chuẩn bị **tham gia giao dịch đang tồn tại**. Khi phát hiện xung đột mà chính sách này kiểm tra, Spring từ chối tham gia và ném `IllegalTransactionStateException` thay vì âm thầm sử dụng thuộc tính của giao dịch ngoài.

Sau bài này bạn sẽ:

1. Hiểu khi nào validation thực sự được gọi và vì sao isolation/read-only của transaction ngoài chi phối.
2. Biết cách bật `setValidateExistingTransaction(true)` trên transaction manager phù hợp.
3. Phân biệt chính xác **xung đột isolation**, **xung đột read-only một chiều**, `Isolation.DEFAULT`, timeout và các propagation khác.
4. Chạy ví dụ **Java 17 + Spring Boot + JDBC + H2** để quan sát kết quả khi bật/tắt kiểm tra.
5. Chọn biện pháp sửa cấu hình đúng nghiệp vụ thay vì chỉ tắt validation để lỗi biến mất.

> **Trọng tâm:** Đây là kiểm tra **tương thích khi tham gia một transaction hiện hữu**, không phải bộ kiểm tra tổng quát mọi thuộc tính `@Transactional`, không phải cơ chế bảo vệ quyền ghi dữ liệu, và cũng không phải một thuật toán tự sửa isolation của database.

## 2. Giao dịch logic và giao dịch vật lý

Một ví dụ quen thuộc:

```java
@Service
public class OrderService {
    private final InventoryService inventory;

    public OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void placeOrder() {
        // Ghi đơn hàng...
        inventory.reserve();
    }
}

@Service
public class InventoryService {
    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void reserve() {
        // Ghi tồn kho...
    }
}
```

Đây là **mã rút gọn minh họa**, cần thêm import/bean/repository trong dự án thật. Giả sử `placeOrder()` được gọi qua Spring proxy, và `inventory.reserve()` cũng là lời gọi qua proxy của **bean khác**.

Với `REQUIRED`, luồng thông thường:

```text
Caller
  |
  v
OrderService proxy
  |-- chưa có transaction
  |-- tạo PHYSICAL transaction: READ_COMMITTED
  |-- mở transaction logic của placeOrder()
  v
placeOrder()
  |
  v
InventoryService proxy
  |-- phát hiện PHYSICAL transaction đã tồn tại
  |-- mở scope logic của reserve(), tham gia cùng transaction
  |-- reserve() yêu cầu SERIALIZABLE
  |
  +-- validateExistingTransaction=false:
  |      tiếp tục với READ_COMMITTED của outer
  |
  +-- validateExistingTransaction=true:
         từ chối mismatch, IllegalTransactionStateException
```

**Transaction logic** là ranh giới do mỗi method transactional khai báo. **Transaction vật lý** là giao dịch thực do connection/resource transaction manager kiểm soát. Với `REQUIRED` tham gia một transaction đã có, hai scope logic cùng chia sẻ **một** transaction vật lý.

Vì vậy:

- Method trong yêu cầu `SERIALIZABLE` không có nghĩa nó được cấp một transaction vật lý `SERIALIZABLE` mới.
- Nếu nó thực sự cần transaction độc lập, `REQUIRES_NEW` là một lựa chọn thiết kế khác, **không phải** một cách đổi isolation của transaction `REQUIRED` đã tồn tại.
- Nếu cần toàn bộ nghiệp vụ dùng cùng isolation, hãy đặt policy nhất quán ngay tại transaction owner/outer boundary và tránh khai mâu thuẫn ở method con.

## 3. `setValidateExistingTransaction` là gì và mặc định thế nào?

API quan trọng nằm ở:

```java
org.springframework.transaction.support.AbstractPlatformTransactionManager
    .setValidateExistingTransaction(boolean validateExistingTransaction)
```

`AbstractPlatformTransactionManager` là lớp nền cho nhiều manager **imperative**, trong đó có `DataSourceTransactionManager`, `JdbcTransactionManager` và `JpaTransactionManager`. Phương thức setter là một cấu hình **của bean transaction manager**, không phải thuộc tính của annotation `@Transactional`.

| Giá trị | Khi một scope thông thường tham gia transaction hiện hữu |
| --- | --- |
| `false` (mặc định) | Chấp nhận participation; những khai báo isolation/read-only riêng của inner có thể bị bỏ qua, outer chi phối |
| `true` | Kiểm tra isolation rõ ràng và sự không tương thích read-only được hỗ trợ; nếu phát hiện xung đột thì ném `IllegalTransactionStateException` trước khi chạy method inner |
| Chưa có transaction để tham gia | Không có “existing transaction” cần so với outer; transaction mới tuân theo definition của chính nó |
| `REQUIRES_NEW` gặp transaction ngoài | Tạm ngưng transaction ngoài và mở transaction riêng; không phải case participation của cùng transaction vật lý |

Một số tài liệu nói đến cờ `validateExistingTransactions` theo nghĩa mô tả ở dạng số nhiều; **tên Java setter thực tế** cần dùng là `setValidateExistingTransaction(boolean)` (số ít).

Không có Spring Boot property phổ biến tên `spring.transaction.validate-existing-transaction` tự động bật cờ này cho mọi manager. Cách an toàn là **lấy đúng manager bean đang được dùng** và gọi setter trong lúc cấu hình nó. Ở ví dụ phía dưới, property `demo.validate-existing` là **property tự đặt của project**, được ứng dụng chủ động đọc và truyền vào setter; không phải một cấu hình built-in của Spring Boot.

### Điều kiện để kiểm tra có hiệu lực

1. Lời gọi vào method inner cần đi qua **Spring transaction interceptor** (thường là Spring AOP proxy).
2. Method inner có transaction definition và propagation phù hợp để **tham gia transaction hiện hữu**.
3. Outer và inner do **cùng transaction manager/tài nguyên liên quan** điều phối. Một manager chỉ kiểm soát các transaction nó quản lý.
4. Transaction manager được cấu hình `validateExistingTransaction=true`.
5. Tồn tại xung đột thuộc loại mà manager thực sự kiểm tra.

Chỉ thay đổi một field trên một manager bean **không** giúp chặn các lời gọi không đi qua proxy hay những transaction được mở bằng connection độc lập ngoài Spring.

## 4. Hai nhóm mismatch mà validation chủ yếu phát hiện

### 4.1. Isolation: inner chỉ định mức không mặc định và khác mức của outer

Giả sử:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outer() {
    innerService.requiresSerializable();
}

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void requiresSerializable() {
    // ...
}
```

Khi `validateExistingTransaction=false`, inner **không đổi** transaction vật lý đang chạy từ `READ_COMMITTED` sang `SERIALIZABLE`. Nó tiếp tục tham gia transaction của outer, với đặc tính đã xác lập.

Khi bật `true`, Spring so sánh isolation mà inner khai báo với isolation hiện tại được **Spring transaction synchronization** ghi nhận. Nếu inner chỉ định một mức **khác `DEFAULT`** mà không tương thích mức hiện tại, Spring ném `IllegalTransactionStateException`.

Đặc biệt:

- Inner `isolation=DEFAULT`: validation **không** yêu cầu một mức cụ thể để so; không tạo lỗi chỉ vì outer dùng `READ_COMMITTED` hay `SERIALIZABLE`.
- Inner khai `SERIALIZABLE`, outer khai `READ_COMMITTED`: strict mode từ chối participation.
- Inner khai `READ_COMMITTED`, outer khai `READ_COMMITTED`: tương thích; được phép tham gia.
- Inner khai `READ_COMMITTED`, outer dùng `DEFAULT`: current isolation có thể được Spring ghi nhận là **không xác định** (`null`), kể cả khi database mặc định đang vận hành ở mức `READ_COMMITTED`. Với strict mode, inner yêu cầu một mức rõ ràng trong khi current isolation không được ghi nhận rõ có thể bị từ chối. **Không được suy rằng database default “tình cờ trùng” là đủ để pass.**

Kiểm tra này đối chiếu **transaction definition và trạng thái mà Spring theo dõi**, không phải một công cụ truy vấn, chứng minh mọi đặc tính isolation thực tế của DB cho từng câu SQL. Dù config tương thích, muốn xác nhận hành vi isolation/locking production vẫn phải kiểm thử trên đúng database engine.

### 4.2. Read-only: xung đột quan trọng là outer chỉ đọc, inner muốn đọc-ghi

Ví dụ:

```java
@Transactional(readOnly = true)
public void generateReport() {
    innerService.persistAudit();
}

@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = false
)
public void persistAudit() {
    // Muốn ghi dữ liệu.
}
```

Với strict validation, một inner **không được đánh dấu read-only** (tức `readOnly=false`, cũng là mặc định của `@Transactional`) **không được tham gia một outer transaction đang được đánh dấu read-only**. Spring ném `IllegalTransactionStateException` khi lấy transaction cho inner.

**Đây không phải phép so sánh Boolean đối xứng.** Mã kiểm tra của `AbstractPlatformTransactionManager` về read-only tương ứng với điều kiện:

```java
if (!innerDefinition.isReadOnly()
        && TransactionSynchronizationManager.isCurrentTransactionReadOnly()) {
    throw new IllegalTransactionStateException(/* ... */);
}
```

Kết quả:

| Outer physical transaction | Inner yêu cầu | `validateExistingTransaction=true` |
| --- | --- | --- |
| `readOnly=true` | `readOnly=false` | **Từ chối** |
| `readOnly=true` | `readOnly=true` | Cho tham gia |
| `readOnly=false` | `readOnly=true` | **Cho tham gia**; physical transaction vẫn đọc-ghi |
| `readOnly=false` | `readOnly=false` | Cho tham gia |

**Tại sao chiều ngược lại vẫn được phép?** Một scope chỉ muốn đọc có thể tham gia transaction đọc-ghi của outer. Thuộc tính read-only của inner không tự chuyển connection đang chia sẻ thành read-only. Vì thế, không nói sai rằng “strict mode từ chối mọi trường hợp outer/inner khác nhau về read-only”.

`readOnly=true` tự nó là **hint/chính sách tối ưu hóa**, không thay thế phân quyền database. Tùy transaction manager và database, các thao tác ghi có thể vẫn chạy hoặc bị từ chối; `setValidateExistingTransaction` không quét SQL để khẳng định ứng dụng không ghi dữ liệu.

### 4.3. So sánh nhanh isolation và read-only

| Outer | Inner `REQUIRED` | Validation = `false` | Validation = `true` |
| --- | --- | --- | --- |
| `READ_COMMITTED` | `SERIALIZABLE` | Inner dùng transaction outer | Từ chối isolation mismatch |
| `READ_COMMITTED` | `READ_COMMITTED` | Cho tham gia | Cho tham gia |
| `READ_COMMITTED` | `DEFAULT` | Cho tham gia | Cho tham gia |
| `DEFAULT` (Spring không ghi isolation cụ thể) | `READ_COMMITTED` | Cho tham gia | Có thể từ chối vì isolation hiện hữu unknown |
| `readOnly=true` | `readOnly=false` | Thường cho tham gia, inner không nâng thành read-write | Từ chối read-only mismatch |
| `readOnly=false` | `readOnly=true` | Cho tham gia, outer vẫn read-write | Cho tham gia, outer vẫn read-write |

Điều kiện ở cột cuối giả định transaction manager đã bật strict, đang có transaction do Spring quản lý và lời gọi inner thực sự đi qua interceptor. Khi hai thuộc tính cùng xung đột, kiểm tra isolation có thể báo lỗi trước kiểm tra read-only; đừng viết test giả định luôn nhận thông báo read-only nếu isolation cũng sai.

## 5. Cờ này **không** làm những gì?

`setValidateExistingTransaction(true)` không phải một “strict mode” toàn diện cho mọi thứ có tên transaction.

| Không làm | Lý do |
| --- | --- |
| Không tự chuyển isolation của transaction vật lý | Một `REQUIRED` participant dùng transaction owner đã tạo |
| Không so sánh timeout của inner và outer theo cùng cách isolation | Kiểm tra participation hiện tại không bao gồm phép so timeout tương tự; timeout trên inner `REQUIRED` thường không áp lại cho transaction đã có |
| Không chứng minh rằng DB không có UPDATE trong read-only transaction | Nó so sánh definition/metadata, không phân tích SQL |
| Không kiểm tra `rollbackFor`, `noRollbackFor` là “tương thích” | Rollback rules áp dụng khi exception thoát qua interceptor, là cơ chế khác |
| Không biến `SUPPORTS` không có transaction thành một giao dịch | Nếu không có physical transaction, không có gì để “join” |
| Không thay thế `Propagation.MANDATORY`/`NEVER` | Các propagation này có điều kiện riêng về transaction hiện hữu |
| Không thay thế cơ chế `UnexpectedRollbackException` | Rollback-only là một trạng thái độc lập; outer commit vẫn có thể thất bại |
| Không quản lý nhiều database độc lập như distributed transaction | Mỗi transaction manager có ranh giới resource riêng |
| Không sửa lỗi self-invocation | Lời gọi `this.innerMethod()` không đi qua transaction proxy trong proxy mode thông thường |

**Đặc biệt về timeout:** Nếu outer `@Transactional(timeout=30)` đã mở một transaction và inner `@Transactional(timeout=5)` chỉ **tham gia** cùng transaction vật lý, bật validation **không** có nghĩa Spring sẽ từ chối mismatch 30/5. Muốn có thời hạn thực sự cho toàn nghiệp vụ, cần đặt timeout đúng ở owner hoặc thiết kế transaction boundary khác, sau đó kiểm thử loại transaction manager/database thực tế.

## 6. Ví dụ chạy được: bật/tắt strict validation trong Spring Boot

Ta dựng một ứng dụng nhỏ dùng **Java 17, Spring Boot 3.3.13, Spring JDBC và H2**. Phần này sử dụng một bộ phiên bản cố định để tái lập ví dụ; nó không hàm ý đây là phiên bản Spring Boot mới nhất. Không cần controller hoặc Spring Data JPA.

**Ý tưởng:** chạy hai lần với cùng code:

- `demo.validate-existing=true`: lỗi isolation/read-only bị từ chối ngay khi scope inner cố tham gia.
- `demo.validate-existing=false`: scope inner được phép tham gia, dù khai báo khác outer; các lệnh và trạng thái quan sát được vẫn theo outer.

### 6.1. Cấu trúc project

```text
tx-validation-lab/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/scope/
    │   ├── TxValidationApplication.java
    │   ├── TransactionManagerConfig.java
    │   ├── OuterService.java
    │   └── InnerService.java
    └── resources/
        └── application.yml
```

Dùng Gradle Wrapper do Spring Initializr/Gradle tạo; bản Gradle cần tương thích với Spring Boot 3.3 và JDK 17.

**`settings.gradle`**

```groovy
rootProject.name = 'tx-validation-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate`, JDBC transaction infrastructure và connection pool (thường là HikariCP). H2 là database trong bộ nhớ để kiểm tra commit/rollback. Các phiên bản của Spring/H2 do Spring Boot quản lý; không thêm version riêng cho từng thư viện.

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:scopecheck;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""

demo:
  validate-existing: true
```

`demo.validate-existing` là **property của ứng dụng demo**: class cấu hình bên dưới chủ động đọc và áp dụng nó. `DB_CLOSE_DELAY=-1` chỉ giữ H2 in-memory sống tới khi JVM dừng; database không trở thành lưu trữ bền vững qua process restart.

### 6.2. Cấu hình transaction manager đúng điểm cần thay đổi

**`src/main/java/demo/scope/TransactionManagerConfig.java`**

```java
package demo.scope;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionManagerConfig {

    @Bean
    JdbcTransactionManager transactionManager(
            DataSource dataSource,
            @Value("${demo.validate-existing:true}") boolean validate) {

        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);

        manager.setValidateExistingTransaction(validate);

        return manager;
    }
}
```

Điểm cần quan sát:

1. Method `transactionManager(...)` tạo bean với tên mặc định `transactionManager`, nên `@Transactional` dùng manager này trong dự án chỉ có một transaction manager.
2. `JdbcTransactionManager` kế thừa cơ chế validation từ `AbstractPlatformTransactionManager`. Ta gọi setter **trên cùng manager sẽ được Spring interceptor dùng**.
3. Spring Boot cung cấp `DataSource` từ `spring.datasource.*`. Bean manager tùy chỉnh khiến cấu hình transaction manager mặc định của Boot nhường chỗ, tránh có hai manager cho cùng DataSource.
4. `@EnableTransactionManagement` bật xử lý annotation theo proxy; trong Boot thường đã có auto-configuration liên quan, nhưng khai rõ giúp ví dụ độc lập về ý tưởng.
5. Thay `demo.validate-existing` trong YAML/command line chỉ có hiệu lực sau khi app dựng lại bean; không nên thử đổi thuộc tính manager tùy tiện trong khi nhiều request đang chạy.

**Lưu ý quan trọng:** `@Transactional` nằm trên service, còn `setValidateExistingTransaction` nằm trên **manager**; không tồn tại cú pháp `@Transactional(validateExistingTransaction=true)`.

### 6.3. Inner service: bốn kiểu yêu cầu transaction

**`src/main/java/demo/scope/InnerService.java`**

```java
package demo.scope;

import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class InnerService {

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void needSerializable() {
        System.out.println(
            "inner requested SERIALIZABLE; currentIsolation=" + isolationLabel());
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        readOnly = false
    )
    public void needReadWrite() {
        System.out.println(
            "inner requested read-write; currentReadOnly="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly());
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        readOnly = true
    )
    public void needReadOnly() {
        System.out.println(
            "inner requested read-only; currentReadOnly="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly());
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED
    )
    public void needReadCommitted() {
        System.out.println(
            "inner requested READ_COMMITTED; currentIsolation=" + isolationLabel());
    }

    private static String isolationLabel() {
        Integer current =
            TransactionSynchronizationManager.getCurrentTransactionIsolationLevel();

        if (current == null) {
            return "UNSPECIFIED";
        }
        if (current == TransactionDefinition.ISOLATION_READ_COMMITTED) {
            return "READ_COMMITTED";
        }
        if (current == TransactionDefinition.ISOLATION_SERIALIZABLE) {
            return "SERIALIZABLE";
        }
        return String.valueOf(current);
    }
}
```

`TransactionSynchronizationManager` phản ánh trạng thái transaction do Spring quản lý trong model imperative/thread-bound. Nó giúp ta thấy rằng **inner không tự đổi metadata isolation/read-only của outer**. Không coi API này là bằng chứng tuyệt đối về mọi chi tiết isolation hiện hành của database khi có giao dịch từ ngoài Spring hoặc driver/provider đặc biệt.

Nếu validation từ chối participation thì thân method inner tương ứng **không chạy**, do đó dòng log nằm trong method đó cũng không xuất hiện.

### 6.4. Outer service: ba xung đột và một trường hợp hợp lệ

**`src/main/java/demo/scope/OuterService.java`**

```java
package demo.scope;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final InnerService inner;
    private final JdbcTemplate jdbc;

    public OuterService(InnerService inner, JdbcTemplate jdbc) {
        this.inner = inner;
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void isolationMismatch() {
        jdbc.update(
            "INSERT INTO event_log (id, label) VALUES (?, ?)",
            1, "isolation"
        );
        inner.needSerializable();
    }

    @Transactional(readOnly = true)
    public void readOnlyMismatch() {
        inner.needReadWrite();
    }

    @Transactional(readOnly = false)
    public void readWriteCallsReadOnly() {
        inner.needReadOnly();
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void matchingIsolation() {
        jdbc.update(
            "INSERT INTO event_log (id, label) VALUES (?, ?)",
            2, "matching"
        );
        inner.needReadCommitted();
    }
}
```

`OuterService` và `InnerService` là **hai Spring-managed beans khác nhau**, nên lời gọi `inner.need...()` đi qua transaction proxy của inner. Đó là điều kiện thiết yếu để Spring phát hiện xung đột.

Bốn case:

- `isolationMismatch()`: outer `READ_COMMITTED`, inner yêu cầu `SERIALIZABLE`. Lệnh INSERT của outer đã nằm trong transaction, nhưng khi strict validation phát hiện xung đột và exception thoát ra qua outer proxy thì INSERT được rollback.
- `readOnlyMismatch()`: outer `readOnly=true`, inner yêu cầu `readOnly=false`. Không cần thực hiện SQL ghi để phát hiện xung đột; Spring kiểm tra **definition** trước thân inner.
- `readWriteCallsReadOnly()`: outer `readOnly=false`, inner yêu cầu `true`. Đây là trường hợp **được phép**; inner thấy transaction vật lý vẫn ở trạng thái read-write.
- `matchingIsolation()`: outer và inner đều yêu cầu `READ_COMMITTED`, nên được phép tham gia và INSERT của outer commit sau khi method kết thúc.

### 6.5. Runner tạo bảng và in kết quả sau transaction

**`src/main/java/demo/scope/TxValidationApplication.java`**

```java
package demo.scope;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;

@SpringBootApplication
public class TxValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxValidationApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            OuterService outer,
            JdbcTemplate jdbc,
            @Value("${demo.validate-existing:true}") boolean validate) {

        return args -> {
            jdbc.execute(
                "CREATE TABLE event_log "
                    + "(id INT PRIMARY KEY, label VARCHAR(30) NOT NULL)"
            );

            System.out.println("validateExisting=" + validate);

            try {
                outer.isolationMismatch();
            } catch (IllegalTransactionStateException ex) {
                System.out.println(
                    "isolation rejected: " + ex.getClass().getSimpleName());
            }
            System.out.println("rows after isolation=" + count(jdbc));

            try {
                outer.readOnlyMismatch();
            } catch (IllegalTransactionStateException ex) {
                System.out.println(
                    "read-only rejected: " + ex.getClass().getSimpleName());
            }

            outer.readWriteCallsReadOnly();
            outer.matchingIsolation();

            System.out.println("rows at end=" + count(jdbc));
        };
    }

    private static Integer count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM event_log", Integer.class);
    }
}
```

Tất cả lời gọi `outer.*()` trong runner đều tới bean đã được Spring inject, **không phải `new OuterService(...)`**. Runner không có transaction bao ngoài, vì thế phép đếm được thực hiện **sau** khi từng transaction qua proxy đã commit hoặc rollback. Bảng được tạo khi runner khởi chạy; không cần `schema.sql`, không cần Flyway cho ví dụ H2 nhỏ này.

### 6.6. Chạy nghiêm ngặt: `validateExistingTransaction=true`

Tại thư mục project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Các dòng do code `System.out.println` in ra theo thứ tự (ngoài ra có log của Gradle/Spring Boot):

```text
validateExisting=true
isolation rejected: IllegalTransactionStateException
rows after isolation=0
read-only rejected: IllegalTransactionStateException
inner requested read-only; currentReadOnly=false
inner requested READ_COMMITTED; currentIsolation=READ_COMMITTED
rows at end=1
```

Giải thích từng dòng:

1. `isolationMismatch` tạo physical transaction `READ_COMMITTED`, thực thi INSERT ID 1, nhưng khi inner yêu cầu `SERIALIZABLE` thì transaction manager từ chối. Exception unchecked thoát qua outer proxy; transaction outer rollback, nên count bằng 0.
2. `readOnlyMismatch` bị từ chối **trước khi body `needReadWrite()` chạy**. Lời gọi outer kết thúc bằng exception bị runner bắt; không có dòng `inner requested read-write`.
3. `readWriteCallsReadOnly` được phép; `currentReadOnly=false` cho thấy thuộc tính outer vẫn chi phối.
4. `matchingIsolation` cho phép inner tham gia, INSERT ID 2 commit. Chỉ có một hàng trong bảng.

Kết quả này **không** nói rằng cứ có validation exception là database tự rollback bất kể caller làm gì: trong ví dụ, exception thoát khỏi outer transactional method và default rollback-on-runtime-exception kích hoạt rollback. Nếu outer tự bắt/nuốt exception, trạng thái rollback cần phân tích riêng theo đường gọi và transaction status.

### 6.7. Chạy chế độ mặc định/dễ tính: `validateExistingTransaction=false`

Chạy lại trong một JVM mới (H2 in-memory bắt đầu từ database rỗng):

```bash
./gradlew bootRun --args='--demo.validate-existing=false'
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.validate-existing=false"
```

Output từ chương trình:

```text
validateExisting=false
inner requested SERIALIZABLE; currentIsolation=READ_COMMITTED
rows after isolation=1
inner requested read-write; currentReadOnly=true
inner requested read-only; currentReadOnly=false
inner requested READ_COMMITTED; currentIsolation=READ_COMMITTED
rows at end=2
```

Ý nghĩa:

- Mặc dù inner muốn `SERIALIZABLE`, nó **không tạo transaction mới**; Spring đang điều phối transaction outer `READ_COMMITTED`. INSERT ID 1 commit, count là 1.
- Inner yêu cầu read-write nhưng đã tham gia outer read-only; `currentReadOnly=true`. Demo không chạy UPDATE trong scope này vì có thể phụ thuộc database/provider; mục tiêu là đo việc cấu hình bị “bỏ qua”.
- Inner read-only tham gia outer read-write vẫn quan sát `currentReadOnly=false`.
- Case matched isolation ghi thêm ID 2, count cuối là 2.

Đối chiếu hai lần chạy cho thấy vì sao strict validation có giá trị: nó biến một sự khác biệt cấu hình có thể âm thầm tồn tại thành một lỗi dễ phát hiện sớm.

## 7. Bản chất phép kiểm tra trong `AbstractPlatformTransactionManager`

Để không hiểu nhầm scope, có thể diễn giải phần cốt lõi của đường xử lý **existing transaction / normal participation** như sau:

```java
// Pseudocode diễn giải, KHÔNG phải bản sao mã nguồn để chạy độc lập.
if (validateExistingTransaction) {

    if (innerDefinition.isolation != DEFAULT) {
        if (currentIsolation == null
                || currentIsolation != innerDefinition.isolation) {
            throw new IllegalTransactionStateException("Isolation mismatch");
        }
    }

    if (!innerDefinition.readOnly && currentTransactionReadOnly) {
        throw new IllegalTransactionStateException("Read-only mismatch");
    }
}

// Nếu hợp lệ, scope inner tham gia transaction vật lý hiện hữu.
```

Bài học rút ra từ cách kiểm tra này:

- So sánh isolation chỉ được thực hiện khi **inner không dùng `DEFAULT`**.
- Khi current isolation Spring đang ghi nhận là **unknown**, một yêu cầu isolation cụ thể từ inner không được coi là tương thích một cách mặc nhiên.
- So sánh read-only là **một chiều**: chỉ từ chối inner **read-write** muốn tham gia outer **read-only**.
- Không có phép so sánh timeout trong đoạn validation này.
- Kiểm tra diễn ra **trước thân method inner**, không chờ DB chạm vào một câu SQL ghi mới báo lỗi.

Đừng áp dụng sơ đồ mã này một cách máy móc cho mọi implementation `TransactionManager`. Nó phản ánh luồng xử lý của `AbstractPlatformTransactionManager` cho participation hiện hữu; manager reactive hoặc implementation đặc thù có thể dùng cơ chế khác.

## 8. Propagation quyết định có phải kiểm tra participation hay không

| Propagation inner | Khi outer đã có transaction | Quan hệ với strict validation |
| --- | --- | --- |
| `REQUIRED` | Tham gia transaction outer | **Đối tượng chính** của kiểm tra mismatch |
| `SUPPORTS` | Tham gia transaction outer nếu có | Có thể bị kiểm tra khi đang tham gia |
| `MANDATORY` | Buộc có transaction outer và tham gia | Có thể bị kiểm tra nếu có transaction |
| `REQUIRES_NEW` | Tạm ngưng outer, mở transaction vật lý mới | Không phải tham gia cùng physical transaction; inner có đặc tính riêng nếu DB hỗ trợ |
| `NOT_SUPPORTED` | Tạm ngưng outer, chạy không có actual transaction | Không tham gia, không là case isolation/read-only conflict này |
| `NEVER` | Có outer transaction thì báo lỗi theo quy tắc NEVER | Lỗi propagation độc lập với flag validation |
| `NESTED` | Thường dùng savepoint trong cùng physical JDBC transaction nếu manager hỗ trợ | Nhánh xử lý riêng; **không** suy rằng flag này ép một isolation độc lập cho nested savepoint |

Khi **không có transaction ngoài**:

- `REQUIRED` có thể mở transaction mới với isolation/read-only của chính inner.
- `SUPPORTS` có thể chạy không có actual transaction.
- `MANDATORY` báo lỗi vì thiếu transaction mà nó yêu cầu.
- `REQUIRES_NEW` mở transaction mới.

Đừng dùng `REQUIRES_NEW` để chỉ “làm lỗi validation biến mất”. Nó thay đổi tính nguyên tử: inner có thể commit riêng rồi outer rollback, và có thể cần connection thứ hai trong pool khi outer vẫn giữ tài nguyên. Nếu nghiệp vụ bắt buộc tất cả thao tác commit/rollback cùng nhau, cách đúng thường là **thống nhất isolation tại outer boundary**.

## 9. Cấu hình XML tương đương

Nếu dự án dùng cấu hình XML thay cho Java `@Bean`, có thể bật strict validation trên **bean transaction manager**:

```xml
<bean id="transactionManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="dataSource"/>
    <property name="validateExistingTransaction" value="true"/>
</bean>

<tx:annotation-driven transaction-manager="transactionManager"/>
```

Đây là **mảnh XML minh họa**, cần bao trong `<beans>` và khai báo `xmlns:tx`/schema tương ứng; `dataSource` phải tồn tại. Cấu hình `validateExistingTransaction` là property có setter trên manager, **không phải** attribute của `<tx:method>`.

Nếu ứng dụng dùng `DataSourceTransactionManager` cho JDBC, hoặc `JpaTransactionManager` cho JPA, có thể áp dụng setter tương ứng nếu manager đó kế thừa `AbstractPlatformTransactionManager` và đang thực sự quản lý transaction của service. Với JPA, phải chọn đúng `EntityManagerFactory`/transaction manager; không thay manager JPA đang dùng bằng JDBC manager chỉ để có setter.

**Tác động phạm vi:** đây là chính sách của một **manager bean**. Nếu có nhiều transaction managers, bật cờ trên manager A không tự bật trên B; `@Transactional(transactionManager="...")` hoặc qualifier/bean routing quyết định method dùng manager nào. Một project có nhiều resource cần rà lại cấu hình theo từng manager, không dựa vào một bean tên ngẫu nhiên.

## 10. Các tình huống cấu hình dễ gây hiểu nhầm

### 10.1. Outer `DEFAULT` nhưng database thực tế mặc định `READ_COMMITTED`

Inner khai `READ_COMMITTED` có thể bị strict validation từ chối vì outer **không khai rõ** isolation, nên Spring theo dõi `currentIsolation=null`. Dù `SHOW transaction_isolation` của database trả về `read committed`, không nên coi kết quả đó chứng minh cờ validation sẽ pass. Nếu muốn tất cả scopes đều tuyên bố một mức cụ thể, hãy thiết kế/khai rõ mức ở outer owner, thử lại và theo dõi transaction manager.

### 10.2. Quên rằng `@Transactional` mặc định `readOnly=false`

Một method inner chỉ ghi `@Transactional`, hoặc `@Transactional(propagation=REQUIRED)`, có default **readOnly=false**. Khi được gọi từ outer `readOnly=true`, strict mode có thể từ chối **ngay cả nếu body inner chỉ SELECT**, bởi validation kiểm tra metadata chứ không phân tích logic SQL. Nếu method thực chất là truy vấn, khai `readOnly=true` đúng semantics; nếu method có ghi, thiết kế lại transaction boundary.

### 10.3. Inner `readOnly=true` không thu hẹp được outer read-write

Outer có transaction đọc-ghi thì inner read-only vẫn tham gia; strict mode không từ chối chiều này. Nếu yêu cầu bảo đảm không có SQL ghi, cần dùng quyền database, test, review và boundary riêng chứ không tin `readOnly` của inner sẽ cưỡng chế transaction vật lý đang tồn tại.

### 10.4. Có cấu hình timeout khác nhau nhưng strict mode không báo lỗi

Một inner `timeout=5` tham gia transaction outer `timeout=30` không làm cờ này phát hiện “timeout mismatch”. Hãy chỉnh timeout ở transaction owner hoặc sử dụng transaction độc lập khi nghiệp vụ thực sự cần, đồng thời đánh giá tài nguyên và tính nguyên tử.

### 10.5. Không đi qua proxy do self-invocation

```java
@Service
public class SameBeanService {
    @Transactional(readOnly = true)
    public void outer() {
        inner(); // Lời gọi nội bộ trong cùng bean.
    }

    @Transactional(readOnly = false)
    public void inner() {
        // ...
    }
}
```

Trong **Spring proxy mode thông thường**, `outer()` được gọi qua proxy có thể mở transaction, nhưng `inner()` gọi qua `this` không đi qua interceptor lần nữa. Vì vậy flag validation **không được dùng để kiểm tra declaration của inner** ở đường gọi đó. Để kiểm tra đúng, gọi service qua Spring-managed bean khác, như `OuterService -> InnerService` trong ví dụ đầy đủ.

### 10.6. Có nhiều transaction managers hoặc không dùng cùng resource

Nếu service A dùng `transactionManagerA` còn service B dùng `transactionManagerB`, chúng không nhất thiết cùng transaction vật lý. Một mismatch mong đợi có thể không được so sánh vì B không tham gia transaction của A. Đừng dùng cờ này làm phép kiểm tra distributed transaction hay resource routing. Nếu cần atomicity trên nhiều resource, đánh giá transaction strategy riêng.

### 10.7. Nuốt `IllegalTransactionStateException` rồi tưởng mọi thứ đã rollback

Flag validation ném exception tại thời điểm **lấy transaction cho inner**. Nếu exception thoát khỏi outer method `@Transactional`, mặc định Spring rollback với unchecked exception. Nhưng nếu outer bắt và nuốt lỗi, giao dịch ngoài **có thể** tiếp tục/commit tùy trạng thái và code; không nên kết luận chỉ riêng việc validation từ chối participation chắc chắn đánh dấu outer rollback-only.

Biện pháp an toàn thường là để exception báo lỗi cấu hình **fail fast**, sửa policy, không catch-and-ignore trong nghiệp vụ.

### 10.8. Nhầm `IllegalTransactionStateException` với `UnexpectedRollbackException`

- `IllegalTransactionStateException` trong bài này: Spring thấy transaction definition của scope muốn tham gia **không tương thích** và từ chối participation.
- `UnexpectedRollbackException`: một transaction vật lý đã bị đánh dấu rollback-only (ví dụ inner scope trước đó thất bại); outer tưởng commit nhưng không thể commit thực tế.

Hai lỗi có thể đều xuất hiện trong hệ thống nhiều scope, nhưng **khác nguyên nhân và thời điểm**. Cờ validation không thay thế rollback-only detection.

### 10.9. Nhầm với `setEnforceReadOnly(true)`

`DataSourceTransactionManager` còn có lựa chọn `setEnforceReadOnly(true)` đối với một số database để chủ động áp dụng chế độ read-only bằng câu lệnh SQL tương ứng cho transaction mới. **Đó là cơ chế khác** so với `setValidateExistingTransaction(true)`:

- `setValidateExistingTransaction`: so definition khi **tham gia** existing transaction; không phân tích và chặn mọi câu ghi.
- `setEnforceReadOnly`: nhằm cưỡng chế read-only ở tầng database khi mở transaction tùy backend/driver hỗ trợ.

Không dùng một setter để thay thế setter còn lại, và không giả định mọi DB/driver thực thi read-only giống nhau.

## 11. Cách thiết kế chính sách transaction nhất quán

Trước khi bật strict validation trên hệ thống đang hoạt động:

1. **Vẽ sơ đồ transaction owner**: controller/service facade nào thực sự mở transaction vật lý? Có lời gọi `REQUIRED` lồng nhau không?
2. **Rà thuộc tính inner**: isolation có được khai rõ hay DEFAULT? read-only có vô tình để mặc định false dù method chỉ đọc?
3. **Chọn một transaction-level policy có chủ đích**: nếu nghiệp vụ cần isolation cao hơn, đặt ngay tại outer owner và xác nhận DB hỗ trợ, thay vì hy vọng inner nâng mức.
4. **Giữ scope inner rõ nghĩa**: method ghi không nên bị gọi sâu bên trong outer read-only; method chỉ đọc nên khai chính xác nếu cấu hình strict cần phân biệt.
5. **Xem xét `REQUIRES_NEW` cẩn trọng**: chỉ dùng khi thật sự cần một giao dịch độc lập, vì nó thay đổi commit boundary và nhu cầu connection.
6. **Bật validation trong test/staging trước**: lỗi mới có thể xuất hiện ở những đường gọi trước đây silently ignored. Ghi nhận service/manager/method pair và sửa policy, không tắt flag ngay.
7. **Kiểm tra trên DB production-like**: isolation support và read-only behavior phụ thuộc database; H2 chỉ minh họa Spring logic.
8. **Quan sát rollback sau exception**: kiểm tra DB sau khi service proxy đã kết thúc. Nếu test tự bọc `@Transactional`, transaction của test có thể làm lệch kết luận.
9. **Rà nhiều managers**: mỗi manager cần cấu hình chủ đích; kiểm tra bean thực tế và `@Transactional(transactionManager=...)` khi có nhiều loại giao dịch.
10. **Giữ cảnh báo và test regression** khi refactor các service, vì thay đổi boundary/propagation có thể khiến một mismatch previously checked không còn được kiểm tra.

Các test nên bao phủ ít nhất các case sau (trong cùng manager, lời gọi qua proxy):

| Case | Mong đợi strict mode |
| --- | --- |
| Outer `READ_COMMITTED` → inner `SERIALIZABLE REQUIRED` | Ném `IllegalTransactionStateException`, inner body chưa chạy |
| Outer `READ_COMMITTED` → inner `READ_COMMITTED REQUIRED` | Chạy bình thường |
| Outer `READ_COMMITTED` → inner `DEFAULT REQUIRED` | Chạy bình thường |
| Outer `readOnly=true` → inner `readOnly=false REQUIRED` | Ném `IllegalTransactionStateException` |
| Outer `readOnly=false` → inner `readOnly=true REQUIRED` | Chạy bình thường; physical transaction vẫn read-write |
| Không có outer → inner `REQUIRED` | Tạo transaction mới; không so với outer |
| Outer transaction → inner `REQUIRES_NEW` | Transaction mới độc lập, không “join” physical outer |
| Outer `timeout=30` → inner `timeout=5 REQUIRED` | Flag validation **không** tự phát hiện timeout mismatch |

Mục đích của test là xác nhận hành vi runtime **dựa trên Spring bean proxy thật**, không chỉ kiểm tra xem source có annotation hay không.

## 12. Câu hỏi tự kiểm tra

**1. Vì sao method inner khai `SERIALIZABLE` nhưng runtime chỉ ở `READ_COMMITTED`?**

Vì `REQUIRED` tham gia transaction đã được outer mở. Với validation mặc định `false`, Spring bỏ qua yêu cầu isolation khác của participant và transaction outer tiếp tục chi phối.

**2. Muốn Spring từ chối yêu cầu khác nhau cần khai `@Transactional(validateExistingTransaction=true)` chứ?**

Không. Thuộc tính này nằm trên **transaction manager** qua setter `setValidateExistingTransaction(true)`.

**3. Strict mode có từ chối outer read-write + inner read-only không?**

Không, theo phép kiểm tra của `AbstractPlatformTransactionManager`. Nó từ chối **inner read-write tham gia outer read-only**, không từ chối chiều ngược lại.

**4. Vì sao outer `Isolation.DEFAULT` và inner `READ_COMMITTED` vẫn có thể bị từ chối dù DB default là READ_COMMITTED?**

Vì Spring có thể ghi nhận current isolation là `null` khi outer không khai isolation cụ thể. Validation dựa trên thông tin transaction do Spring theo dõi, không giả định DB default trùng với yêu cầu của inner.

**5. Cờ này có phát hiện inner timeout 5 giây khi outer timeout 30 giây không?**

Không. Đây không phải phép validator tất cả transaction attributes; timeout của participant không được so khớp như isolation.

**6. `REQUIRES_NEW` có tạo được isolation độc lập không?**

Với transaction manager/DB hỗ trợ, `REQUIRES_NEW` mở transaction vật lý mới để áp dụng definition của inner; đổi lại nó độc lập về commit/rollback và tài nguyên, nên chỉ dùng khi đúng nghiệp vụ.

**7. Tại sao vẫn không thấy exception khi bật flag ở bean transaction manager?**

Kiểm tra liệu bean đó có thực sự được transaction interceptor sử dụng không; outer có transaction hiện hữu không; inner có đi qua Spring proxy không; propagation có tham gia không; và kiểu mismatch có thuộc phạm vi validation không.

**8. Validation mismatch tự rollback outer dù outer catch-and-ignore exception chứ?**

Không nên giả định vậy. Trong ví dụ hoàn chỉnh, unchecked exception **thoát ra ngoài outer** nên outer interceptor rollback. Nếu outer nuốt exception, cần kiểm tra transaction status và thiết kế xử lý lỗi, không dựa vào flag như cơ chế đánh dấu rollback-only tổng quát.

## 13. Tổng kết

`setValidateExistingTransaction(true)` giúp phát hiện **sớm các khai báo transaction không tương thích khi một scope gia nhập transaction đã tồn tại**. Nó đặc biệt hữu ích khi:

- Outer và inner khai isolation rõ ràng nhưng khác nhau.
- Outer `readOnly=true` mà inner mặc định hoặc khai rõ `readOnly=false`.
- Hệ thống có nhiều service `REQUIRED`, dễ tưởng rằng inner tự tạo transaction với thuộc tính mới.

Quy tắc chính xác cần nhớ:

**Strict validation so isolation rõ ràng của inner với isolation Spring ghi nhận ở outer; từ chối inner read-write đi vào outer read-only; không kiểm tra timeout như một mismatch tương tự; và không thay thế transaction boundary, proxy, rollback rules hay quyền database.**

Giải pháp thiết kế thường là đặt thuộc tính mong muốn ở **transaction owner**, bảo đảm các scope tham gia có khai báo phù hợp, và chỉ dùng giao dịch độc lập khi thật sự cần. Kiểm chứng bằng lời gọi Spring proxy và database là bước không thể bỏ qua.

## Tài liệu tham khảo chính thức

- Spring Framework — *Transaction Propagation* (REQUIRED, REQUIRES_NEW, validation): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — *Understanding Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework 6.1 API — *AbstractPlatformTransactionManager* và `setValidateExistingTransaction`: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework API — *JdbcTransactionManager*: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html
- Spring Framework source — *AbstractPlatformTransactionManager* (nhánh `handleExistingTransaction`): https://github.com/spring-projects/spring-framework/blob/main/spring-tx/src/main/java/org/springframework/transaction/support/AbstractPlatformTransactionManager.java
- Spring Boot 3.3 — *SQL Databases and JDBC*: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
