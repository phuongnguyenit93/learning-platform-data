# `@Transactional.label` và ý nghĩa phụ thuộc từng transaction manager

## 1. Câu hỏi trung tâm

Spring cho phép viết:

```java
@Transactional(label = {"operation:checkout", "audit"})
public void checkout() {
    // Thực hiện thao tác có transaction.
}
```

Vậy hai chuỗi `"operation:checkout"` và `"audit"` có bắt Spring ghi audit log, bật chế độ commit đặc biệt hay chọn transaction manager khác không?

**Không có bảo đảm như vậy.** `label` là **metadata mô tả transaction**, có thể được transaction manager hoặc thành phần mở rộng có hiểu labels sử dụng để đưa ra hành vi riêng. Chính sách cụ thể phụ thuộc **implementation**. Nếu manager không đánh giá những label đó, chúng **không tự thay đổi** commit, rollback, isolation, timeout, read-only hoặc propagation.

Đây là ý chính của chủ đề *“label và ý nghĩa phụ thuộc từng manager”*. Một label có thể:

- Chỉ mô tả mục đích transaction, chẳng hạn `"operation:checkout"`.
- Mang nghĩa là một option **được một transaction manager cụ thể tài liệu hóa**, chẳng hạn một chính sách dành riêng cho tài nguyên của manager ấy.
- Được code mở rộng do đội phát triển viết đọc để log, đo đạc hoặc áp dụng một chính sách tường minh.
- Không tạo hiệu ứng vận hành nào khi manager nhận hoặc bỏ qua metadata.

Đích học tập: đọc đúng API, giải thích đường đi của label, phân biệt **metadata** với **hành vi được thực thi**, sử dụng label an toàn và tự viết kiểm thử để xác minh manager đang làm gì.

> Phạm vi minh họa: `org.springframework.transaction.annotation.Transactional` của Spring Framework 6.x (thuộc tính `label` có từ Spring 5.3), mô hình imperative với `PlatformTransactionManager` và JDBC. Các transaction manager cho JPA, JTA hoặc reactive có thể xử lý metadata khác. Tên label trong ví dụ là **quy ước minh họa**, không phải bộ option chuẩn do Spring quy định.

## 2. Chính xác `label` khai báo điều gì?

Trong Spring, thuộc tính có chữ ký:

```java
String[] label() default {};
```

Đó là một **mảng `String`**, mặc định rỗng. Viết một phần tử hoặc nhiều phần tử đều được:

```java
@Transactional(label = "operation:checkout")
public void singleLabel() {
    // ...
}

@Transactional(label = {"operation:checkout", "audit"})
public void multipleLabels() {
    // ...
}
```

Hai method trên chỉ minh họa cú pháp; phần thân được lược bỏ nên chúng **không phải chương trình độc lập**. Label có thể đặt trên phương thức, lớp hoặc meta-annotation chứa `@Transactional`. Spring đọc annotation khi xây dựng thông tin transaction cho lời gọi được intercept.

Tài liệu API của `@Transactional.label` nêu rõ hai khả năng: label có thể **chỉ để mô tả** hoặc được một manager cụ thể dùng như **option đặc thù của manager**. Không có từ điển label toàn cục của Spring Framework bảo đảm rằng `"retryable"`, `"audit"`, `"read-consistent"` hay `"causal-consistency"` tự có ý nghĩa giống nhau trên mọi hệ thống.

### 2.1. Phân biệt với những thuộc tính dễ nhầm

| Thuộc tính | Mục đích | Spring/framework có semantics chuẩn? |
| --- | --- | --- |
| `label = {"audit", "checkout"}` | Thêm mô tả/option dành cho manager có hỗ trợ | **Không có semantics chung** cho chuỗi tùy ý |
| `value = "ordersTxManager"` | Chọn transaction manager theo tên/qualifier | Có: `value` là alias của `transactionManager` |
| `transactionManager = "ordersTxManager"` | Chọn manager thực thi transaction | Có |
| `propagation = Propagation.REQUIRES_NEW` | Yêu cầu transaction độc lập theo quy tắc propagation | Có, chịu giới hạn khả năng manager |
| `isolation = Isolation.SERIALIZABLE` | Yêu cầu isolation khi tạo transaction mới | Có, phụ thuộc hỗ trợ của database/manager |
| `timeout = 5` | Yêu cầu timeout 5 giây ở transaction thích hợp | Có, phụ thuộc hỗ trợ và thời điểm kiểm tra |
| `readOnly = true` | Cung cấp read-only hint/khả năng tối ưu hóa | Có ý nghĩa quy ước, nhưng không bảo đảm chặn mọi lệnh ghi |
| `rollbackFor = IOException.class` | Chỉ định exception gây rollback | Có, được transaction interceptor sử dụng |

Ví dụ, cách **đúng** để chọn một manager tên `ordersTxManager`:

```java
@Transactional(
    transactionManager = "ordersTxManager",
    label = {"operation:checkout", "audit"}
)
public void checkout() {
    // ...
}
```

Annotation này chọn manager bằng `transactionManager`; hai label chỉ được truyền làm metadata. Nếu thay `transactionManager` bằng `label = "ordersTxManager"`, Spring **không vì thế tự tìm bean có tên đó**. Tương tự, `label = "timeout:5"` không tương đương `timeout = 5`; `label = "rollback-on-checked"` không thay `rollbackFor`.

### 2.2. Label không phải transaction name

Spring có một transaction name dùng trong cơ chế theo dõi/log, thường được lấy từ tên lớp đầy đủ cộng tên phương thức transactional (ví dụ `com.example.CheckoutService.checkout` trong declarative transaction). `label` là metadata khác, có thể có nhiều phần tử, không tự đổi tên transaction này.

Không nên suy ra rằng:

- Spring tự in mọi label vào log.
- `TransactionSynchronizationManager.getCurrentTransactionName()` trả về label.
- Label nào cũng xuất hiện trong tracing/metrics mà không cần cấu hình thêm.

Một hệ quan sát có thể chủ động dùng label, nhưng đó là kết quả của **mã tích hợp cụ thể**, không phải lời hứa mặc định của annotation.

## 3. Đường đi của metadata: ai có cơ hội đọc label?

Một lời gọi điển hình:

```text
Caller
  |
  v
Spring AOP proxy
  |
  v
AnnotationTransactionAttributeSource
  |  Đọc @Transactional và tạo TransactionAttribute
  |  - propagation, isolation, timeout, readOnly
  |  - rollback rules
  |  - qualifier/transactionManager
  |  - getLabels()
  v
TransactionInterceptor
  |  Chọn transaction manager bằng qualifier (nếu có)
  |  Gọi PlatformTransactionManager.getTransaction(definition)
  v
Transaction manager cụ thể
  |  Có thể đọc metadata label nếu implementation hỗ trợ
  |  Thực thi begin/join/commit/rollback theo contract của manager
  v
Database / tài nguyên transaction
```

Các API liên quan:

- `@Transactional.label()` khai báo các chuỗi.
- `AnnotationTransactionAttributeSource` đọc annotation rồi cung cấp `TransactionAttribute` cho phương thức/lớp.
- `TransactionAttribute.getLabels()` trả về `Collection<String>` metadata đã được phân tích.
- `DefaultTransactionAttribute.getLabels()` và `setLabels(...)` cung cấp cách truy cập/thiết lập label ở lớp biểu diễn attribute.
- `PlatformTransactionManager.getTransaction(TransactionDefinition)` nhận transaction definition để quyết định bắt đầu hoặc tham gia transaction. Với con đường declarative của Spring, tham số này có thể là `TransactionAttribute`, vốn mở rộng `TransactionDefinition` và có `getLabels()`.

**Điểm tinh tế:** `TransactionDefinition` tự nó không khai báo phương thức `getLabels()`. Code manager muốn xem labels trên đường declarative cần đọc từ metadata thích hợp, chẳng hạn kiểm tra `definition instanceof TransactionAttribute`. Cùng interface `PlatformTransactionManager` có thể được gọi bằng một `DefaultTransactionDefinition` thuần, nơi không có labels; manager phải có phương án xử lý trường hợp ấy.

Ví dụ **minh họa riêng phần kiểm tra metadata**, chưa phải service chạy được:

```java
if (definition instanceof TransactionAttribute attribute) {
    Collection<String> labels = attribute.getLabels();
    // Thực thi chính sách đã tài liệu hóa, hoặc chỉ ghi nhận labels.
}
```

Chữ `label` **không phải một contract yêu cầu mọi manager** phải hành động với chuỗi truyền vào. Có manager không quan tâm label, có manager mở rộng nhận diện một số giá trị, và cũng có code bọc manager bổ sung logic. Vì thế không đoán ý nghĩa theo tên label; phải đọc tài liệu của **manager đang dùng** hoặc kiểm thử thực tế.

## 4. Vì sao ý nghĩa phụ thuộc transaction manager?

Spring cung cấp abstraction chung cho các hệ transaction khác nhau: JDBC local transaction, JPA, JTA, reactive transaction và các cách tích hợp tùy chỉnh. Những hệ đó có tài nguyên, khả năng hỗ trợ, thời điểm bắt đầu/kết thúc và mô hình context không đồng nhất.

Một số ví dụ để phân biệt **chủ ý** và **bảo đảm**:

| Label tự đặt | Ý định có thể có | Điều **không được mặc định kết luận** |
| --- | --- | --- |
| `"audit"` | Đánh dấu giao dịch cần giám sát | Spring tự lưu audit record hoặc in log |
| `"operation:checkout"` | Phân loại thao tác nghiệp vụ | Transaction sẽ có tên `checkout` hoặc dùng manager riêng |
| `"retryable"` | Khai báo ý định cho một phần mở rộng | Spring tự retry khi deadlock |
| `"consistency:strong"` | Gợi ý chính sách nhất quán cho manager riêng | JDBC/JPA tự nâng isolation |
| `"readonly-report"` | Phân loại workload đọc | Database tự chặn mọi `INSERT` |
| `"training:reject"` | Quy tắc thử nghiệm do ta tạo ở mục 7 | Spring nguyên bản từ chối transaction vì gặp chuỗi này |

Những chuỗi trong bảng là **ví dụ tên do tác giả tự nghĩ** để học API; không được coi là option có sẵn trên `DataSourceTransactionManager`, `JdbcTransactionManager`, `JpaTransactionManager` hay một manager khác.

Khi thay đổi manager, phải đánh giá lại cả ba mức:

1. **Cú pháp:** `@Transactional(label = "...")` vẫn hợp lệ trên Spring có hỗ trợ label.
2. **Luồng truyền:** Spring đọc và có thể đưa labels vào `TransactionAttribute`.
3. **Hành vi:** Manager đã chọn **có thực sự đánh giá** label đó hay không, và nếu có thì lúc bắt đầu, tham gia, commit hay callback nào?

Mức 1 và 2 không chứng minh mức 3. Nếu đội phát triển hứa hẹn label sẽ bật audit, cấu hình đó phải tồn tại, có tài liệu và có test chứng minh. Mọi quy tắc mang tính tuân thủ/kiểm soát an toàn cũng cần điểm thực thi thực tế, không thể chỉ dựa vào một chuỗi annotation.

## 5. Mẫu sử dụng trong ứng dụng thực tế

### 5.1. Đặt tên để người đọc hiểu intent

Ví dụ quy ước nội bộ:

```java
@Transactional(label = {"operation:invoice", "critical"})
public void issueInvoice() { /* ... */ }
```

Ở mức đơn giản, labels giúp người đọc nhận diện mục đích transaction. Muốn labels có hiệu lực trong giám sát, cần một thành phần đọc metadata và đưa nó vào metrics/tracing/log. Tránh nhúng bí mật, token, tài khoản khách hàng hoặc dữ liệu cá nhân vào tên label tĩnh trong source code.

Một quy ước dễ quản lý nên có danh sách giá trị hợp lệ, chủ sở hữu, mục đích, điều kiện áp dụng và test. Không đổi tên label đang được một manager mở rộng tiêu thụ mà không kiểm tra phụ thuộc.

### 5.2. Dùng composed annotation khi có quy ước lặp lại

Spring hỗ trợ meta-annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Transactional(label = {"operation:payment", "audit"})
public @interface PaymentTransaction {
}
```

Và sử dụng:

```java
@PaymentTransaction
public void pay() {
    // ...
}
```

Đây là **mẫu API minh họa**, chưa phải một dự án hoàn chỉnh. Nó chuẩn hóa metadata đã khai báo; vẫn không làm manager tự triển khai audit. Nếu cần chỉ định transaction manager hoặc rule rollback trong composed annotation, hãy khai báo chúng rõ ràng, kiểm thử thuộc tính thực tế mà Spring đọc, và tránh suy đoán rằng label bị "hợp nhất" tự động giữa nhiều mức annotation.

### 5.3. Label ở class và method

Một `@Transactional` trên lớp cung cấp default cho các method phù hợp. Metadata trên method có thể ưu tiên hơn metadata cấp lớp. Ví dụ:

```java
@Transactional(label = "module:billing")
public class BillingService {
    public void create() { /* ... */ }

    @Transactional(label = "operation:refund")
    public void refund() { /* ... */ }
}
```

Hãy kiểm tra attribute đã được resolve trên `refund` thay vì **giả định** hai bộ label tự được cộng lại. Trong proxy mode mặc định, lời gọi nội bộ dạng `this.refund()` không được AOP interceptor xử lý như một lần gọi qua proxy; vì vậy test nên gọi method từ một Spring bean khác.

## 6. Thực hành 1 — đọc chính xác label mà Spring đã phân tích

Mục tiêu: chứng minh Java annotation được Spring chuyển thành `TransactionAttribute` như thế nào, không cần kết nối database.

Giả sử có class:

```java
package com.example.txlabels;

import org.springframework.transaction.annotation.Transactional;

public class LabelledOperations {
    @Transactional(
        transactionManager = "transactionManager",
        label = {"operation:checkout", "audit"}
    )
    public void checkout() {
    }

    @Transactional
    public void ordinary() {
    }
}
```

Ta đọc metadata bằng `AnnotationTransactionAttributeSource`. Đây là unit test với JUnit 5 và dependency `spring-tx` (trong ví dụ Gradle đầy đủ mục 7, dependency đã được starter kéo vào):

```java
package com.example.txlabels;

import java.lang.reflect.Method;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionAttribute;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LabelsMetadataTest {
    @Test
    void extractsLabelSetAndManagerQualifier() throws Exception {
        Method method = LabelledOperations.class.getMethod("checkout");
        var source = new AnnotationTransactionAttributeSource();
        TransactionAttribute attr = source.getTransactionAttribute(
                method, LabelledOperations.class);

        assertNotNull(attr);
        assertEquals(Set.of("operation:checkout", "audit"),
                Set.copyOf(attr.getLabels()));
        assertEquals("transactionManager", attr.getQualifier());
    }

    @Test
    void absentLabelMeansEmptyCollection() throws Exception {
        Method method = LabelledOperations.class.getMethod("ordinary");
        var source = new AnnotationTransactionAttributeSource();
        TransactionAttribute attr = source.getTransactionAttribute(
                method, LabelledOperations.class);

        assertNotNull(attr);
        assertEquals(Set.of(), Set.copyOf(attr.getLabels()));
    }
}
```

Ở đây `Set.copyOf(...)` giúp so sánh **tập label** mà không phụ thuộc thứ tự iteration của `Collection`. Hai test chỉ chứng minh metadata. Chúng **không** chứng minh database đã mở transaction hay manager tiêu thụ các label ấy. Để quan sát hành vi, cần kết hợp lời gọi qua proxy và transaction manager thật.

## 7. Thực hành 2 — một manager có và không có chính sách label

Dự án tối thiểu dùng **Spring Boot 3.3.5 + Java 17 + Spring JDBC + H2**. Ta tự viết wrapper `LabelAwareTransactionManager` quanh `JdbcTransactionManager` với hai trách nhiệm **do chúng ta định nghĩa**:

1. Ghi nhận những label Spring truyền vào `getTransaction`.
2. Từ chối label `"training:reject"` **chỉ để làm thí nghiệm**.

Những trách nhiệm đó **không phải hành vi mặc định của `JdbcTransactionManager`**. Wrapper chuyển tiếp mọi thao tác còn lại cho manager JDBC thực.

### 7.1. Cấu trúc dự án

```text
tx-labels/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txlabels/
    │   │   ├── TxLabelsApplication.java
    │   │   ├── TransactionConfig.java
    │   │   ├── LabelAwareTransactionManager.java
    │   │   ├── LabelledOperations.java
    │   │   └── CheckoutService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txlabels/
        ├── LabelsMetadataTest.java
        └── LabelsIntegrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'tx-labels'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txlabels;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);
```

Đây là test database trong bộ nhớ. Gradle quản lý toàn bộ classpath Spring, JDBC, H2 và JUnit; không chạy `javac` trần khi không có các dependency này.

### 7.2. Entry point và cấu hình manager

`src/main/java/com/example/txlabels/TxLabelsApplication.java`:

```java
package com.example.txlabels;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxLabelsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxLabelsApplication.class, args);
    }
}
```

`src/main/java/com/example/txlabels/TransactionConfig.java`:

```java
package com.example.txlabels;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfig {
    @Bean("transactionManager")
    public LabelAwareTransactionManager transactionManager(DataSource dataSource) {
        return new LabelAwareTransactionManager(
                new JdbcTransactionManager(dataSource));
    }
}
```

Bean `transactionManager` là wrapper, còn `JdbcTransactionManager` giữ trách nhiệm begin/commit/rollback JDBC thực. Annotation `@EnableTransactionManagement` kích hoạt hạ tầng proxy, nên không phụ thuộc vào việc người đọc có biết Spring Boot tự cấu hình phần nào trong ứng dụng.

### 7.3. Wrapper có chủ đích đọc labels

`src/main/java/com/example/txlabels/LabelAwareTransactionManager.java`:

```java
package com.example.txlabels;

import java.util.List;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.interceptor.TransactionAttribute;

public final class LabelAwareTransactionManager
        implements PlatformTransactionManager {

    private final PlatformTransactionManager delegate;
    private final List<Set<String>> observed = new CopyOnWriteArrayList<>();

    public LabelAwareTransactionManager(PlatformTransactionManager delegate) {
        this.delegate = delegate;
    }

    @Override
    public TransactionStatus getTransaction(TransactionDefinition definition)
            throws TransactionException {
        Set<String> labels =
                definition instanceof TransactionAttribute attribute
                        ? Set.copyOf(attribute.getLabels())
                        : Set.of();

        observed.add(labels);

        // Chính sách TỰ ĐỊNH NGHĨA để chứng minh manager-dependent.
        // Spring nguyên bản không hiểu "training:reject".
        if (labels.contains("training:reject")) {
            throw new IllegalTransactionStateException(
                    "Rejected by the demo label policy");
        }

        return delegate.getTransaction(definition);
    }

    @Override
    public void commit(TransactionStatus status) throws TransactionException {
        delegate.commit(status);
    }

    @Override
    public void rollback(TransactionStatus status) throws TransactionException {
        delegate.rollback(status);
    }

    public List<Set<String>> observedLabels() {
        return List.copyOf(observed);
    }

    public void clearObservedLabels() {
        observed.clear();
    }
}
```

**Phân tích:** `getTransaction` nhận definition do Spring interceptor gửi. Với lời gọi qua `@Transactional`, definition là một `TransactionAttribute` (hoặc wrapper của nó) và expose `getLabels()`. Khi gọi bằng `TransactionTemplate`/API thủ công với `TransactionDefinition` thông thường, có thể không có metadata label, nên code xử lý tập rỗng. Chỉ điều kiện `training:reject` làm thay đổi hành vi: wrapper ném lỗi **trước khi delegate bắt đầu transaction**.

Các điểm giới hạn phải hiểu:

- `observed` là danh sách để phục vụ test, **không phải cơ chế logging/metrics production**. Trong ứng dụng nhiều request, cần thiết kế thu thập metrics có giới hạn, thread-safe và không để dữ liệu nhạy cảm trong label.
- Wrapper ghi nhận khi `getTransaction` được gọi, **không chứng minh mỗi lần gọi tạo physical transaction mới**. Với `Propagation.REQUIRED`, một scope có thể tham gia transaction hiện có.
- Custom policy ném exception là thiết kế *thực nghiệm*; một manager production cần hợp đồng chính sách rõ, validation, xử lý lỗi và kiểm thử đặc tính propagation.
- Wrapper không tự thêm khả năng JDBC đặc biệt. Nó chuyển tiếp commit/rollback; kết quả DB vẫn tuân theo delegate.

### 7.4. Service dùng các loại label khác nhau

`src/main/java/com/example/txlabels/CheckoutService.java`:

```java
package com.example.txlabels;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {
    private final JdbcTemplate jdbc;

    public CheckoutService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        transactionManager = "transactionManager",
        label = {"operation:checkout", "audit"}
    )
    public void checkout(String code) {
        insert(code);
    }

    @Transactional(label = "training:reject")
    public void rejected(String code) {
        insert(code); // Phần thân sẽ không chạy do policy của wrapper.
    }

    @Transactional(label = "training:ignored")
    public void failsWithRuntimeException(String code) {
        insert(code);
        throw new IllegalStateException("Simulated failure");
    }

    @Transactional
    public void ordinary(String code) {
        insert(code);
    }

    private void insert(String code) {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", code);
    }
}
```

`"operation:checkout"` và `"audit"` được wrapper ghi nhận, nhưng **wrapper không có nhánh xử lý đặc biệt cho chúng**. `"training:ignored"` cũng chỉ được ghi nhận: method vẫn rollback khi `IllegalStateException` thoát ra ngoài vì rollback rule chuẩn của `@Transactional`, không phải nhờ label. `"training:reject"` thì **chỉ** bị từ chối do dòng `if (labels.contains(...))` trong wrapper của bài học.

### 7.5. Integration test so sánh metadata với hành vi DB

`src/test/java/com/example/txlabels/LabelsIntegrationTest.java`:

```java
package com.example.txlabels;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class LabelsIntegrationTest {
    @Autowired
    private CheckoutService checkoutService;

    @Autowired
    private LabelAwareTransactionManager manager;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
        manager.clearObservedLabels();
    }

    private long rows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events", Long.class);
    }

    @Test
    void multipleLabelsAreVisibleButNormalCommitStillWorks() {
        checkoutService.checkout("checkout-A");

        assertEquals(1L, rows());
        assertEquals(
                List.of(Set.of("operation:checkout", "audit")),
                manager.observedLabels());
    }

    @Test
    void customPolicyRejectsBeforeServiceBody() {
        assertThrows(IllegalTransactionStateException.class,
                () -> checkoutService.rejected("reject-B"));

        assertEquals(0L, rows());
        assertEquals(
                List.of(Set.of("training:reject")),
                manager.observedLabels());
    }

    @Test
    void arbitraryLabelDoesNotChangeRollbackRule() {
        assertThrows(IllegalStateException.class,
                () -> checkoutService.failsWithRuntimeException("fail-C"));

        assertEquals(0L, rows());
        assertEquals(
                List.of(Set.of("training:ignored")),
                manager.observedLabels());
    }

    @Test
    void noLabelIsAValidEmptySet() {
        checkoutService.ordinary("plain-D");

        assertEquals(1L, rows());
        assertEquals(
                List.of(Set.of()),
                manager.observedLabels());
    }
}
```

Không thêm `@Transactional` lên lớp test. Nếu test tự mở transaction và rollback sau test, kết quả `rows()` có thể chỉ phản ánh dữ liệu chưa commit, không chứng minh service boundary. Ở đây, Spring gọi service bean qua proxy và hoàn tất transaction; test đọc dữ liệu sau đó bằng `JdbcTemplate`.

### 7.6. Ghép thêm bài kiểm tra metadata từ mục 6

Lưu `LabelledOperations.java` và `LabelsMetadataTest.java` từ mục 6 vào đúng đường dẫn trong cây thư mục. Khi đó toàn bộ bài có **6 test**: 2 test đọc annotation và 4 integration test qua service/manager.

Chạy ở thư mục dự án bằng Gradle Wrapper (nếu tạo từ Spring Initializr) với JDK 17+:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu tạo project thủ công mà chưa có Gradle Wrapper, hãy tạo wrapper bằng Gradle đã cài hoặc chạy `gradle test` bằng phiên bản Gradle tương thích với Spring Boot 3.3.5. Gradle sẽ compile Java và chạy JUnit. **Kết quả kỳ vọng:** 6 test pass; không có stdout Java cố định của các test. Kiểm tra `build/reports/tests/test/index.html` để xem kết quả thực tế.

| Trường hợp | Label manager nhận | Thay đổi dữ liệu | Ý nghĩa |
| --- | --- | --- | --- |
| Checkout thành công | `operation:checkout` và `audit` | 1 hàng được commit | Label được truyền nhưng không tự gây audit |
| Reject | `training:reject` | 0 hàng | **Custom wrapper** từ chối trước khi chạy service body |
| Runtime exception | `training:ignored` | 0 hàng | Rollback do exception rule mặc định |
| Không label | Tập rỗng | 1 hàng được commit | Annotation không cần label để tạo transaction |

Kết quả ví dụ là **kỳ vọng của mã được cung cấp**, không phải khẳng định đã chạy test trên máy của người đọc. Đừng suy ra output log cụ thể, vì log phụ thuộc cấu hình và phiên bản framework.

## 8. Lưu ý quan trọng khi có nested call hoặc nhiều transaction manager

### 8.1. Label ở nested `REQUIRED` không có nghĩa mở transaction mới

Xét hai bean:

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(label = "scope:outer")
    public void process() {
        inner.step();
    }
}

@Service
class InnerService {
    @Transactional(label = "scope:inner")
    public void step() {
        // ...
    }
}
```

Đây là **mã minh họa**, cần import `@Service` và `@Transactional` để dùng trong dự án thực tế. `REQUIRED` mặc định có thể khiến inner tham gia **cùng physical transaction** do outer tạo. Một wrapper tương tự ví dụ có thể ghi nhận cả hai bộ label khi `getTransaction` được gọi; điều đó **không có nghĩa hai transaction độc lập được bắt đầu** hoặc chính sách chỉ áp dụng ở lúc bắt đầu được chạy lại cho physical transaction.

Vì thế phải làm rõ chính sách label có tác dụng ở:

- Lúc nhận một **logical transaction scope**.
- Lúc bắt đầu một **physical transaction mới**.
- Lúc commit/rollback hoặc trong callback cụ thể.
- Hay chỉ lúc hiển thị metadata/telemetry.

Nếu việc quan sát đó quan trọng, kiểm thử hai bean gọi qua proxy với `REQUIRED`, `REQUIRES_NEW` và trường hợp rollback. Đừng suy diễn nghĩa của label từ việc scope được gắn annotation.

### 8.2. Label không được dùng để chọn manager

Khi ứng dụng có cả `ordersTxManager` và `reportingTxManager`, Spring lựa chọn manager theo cơ chế qualifier, cấu hình mặc định và `transactionManager/value`, **không dựa trên label trừ khi có hạ tầng tùy chỉnh được viết rõ**.

```java
@Transactional(
    transactionManager = "reportingTxManager",
    label = "operation:report"
)
public void generateReport() {
    // ...
}
```

Ở đây manager đã được chọn theo `transactionManager`; `operation:report` là metadata mà manager đã chọn *có thể* xét tiếp. Không dùng label để ngầm định route dữ liệu sang database khác.

### 8.3. Reactive transaction có context khác

Mô hình imperative thường gắn trạng thái transaction với thread; reactive transaction quản lý state qua Reactor context. Một label có thể nằm trong metadata đưa tới `ReactiveTransactionManager`, nhưng không vì vậy được truyền thành thread-local label sẵn dùng hoặc có semantics giống JDBC. Khi viết code đọc label, phải xác định rõ mình đang tích hợp với **imperative** hay **reactive** manager và đường đi transaction thực tế.

## 9. Cách thiết kế label có ý nghĩa trong một đội kỹ thuật

Dùng một hợp đồng tối thiểu trước khi nhóm quyết định label kích hoạt behavior:

| Câu hỏi | Ví dụ trả lời có thể kiểm chứng |
| --- | --- |
| Tên label nào được chấp nhận? | `"operation:checkout"`; `"policy:strict"`, có tài liệu |
| Ai đọc label? | Một custom `PlatformTransactionManager` hoặc một integration đã đăng ký rõ |
| Label tác động ở đâu? | Trước `getTransaction`, khi bắt đầu physical transaction hoặc chỉ khi ghi metrics |
| Không có label thì sao? | Giữ mặc định của transaction manager |
| Gặp label lạ thì sao? | Bỏ qua hoặc fail-fast theo hợp đồng đã công bố |
| Có nhiều label thì ưu tiên thế nào? | Một quy tắc deterministic, có kiểm thử xung đột |
| Với `REQUIRED` lồng nhau? | Định nghĩa tác dụng trên logical scope hay physical transaction |
| Chuyển manager thì sao? | Có integration test chứng minh mapping hành vi không bị mất |
| Làm sao thấy lỗi khi chính sách không được áp dụng? | Test boundary + metrics/cảnh báo phù hợp |

Với chính sách bảo mật, tuân thủ, chống gian lận hoặc dữ liệu quan trọng, không bao giờ coi một label **không có consumer** là một hàng rào kỹ thuật. Nếu dự án chuyển từ manager tùy chỉnh sang manager tiêu chuẩn mà không mang theo consumer, code vẫn compile nhưng semantics mở rộng có thể biến mất.

## 10. Các lỗi suy luận thường gặp

1. **Nhầm `label` với `transactionManager/value`.** Label không mặc định chọn bean transaction manager.
2. **Tự đặt `label = "retryable"` và chờ auto retry.** Retry cần cơ chế và chính sách riêng, cân nhắc idempotency.
3. **Tự đặt `label = "audit"` rồi coi đó là audit trail.** Metadata không thay thế record, log hoặc sự kiện audit được ghi thực tế.
4. **Dùng label thay `rollbackFor`.** Quy tắc rollback vẫn do transaction infrastructure và cấu hình rollback rule quyết định.
5. **Dùng label thay `isolation`, `readOnly`, `timeout`.** Những thuộc tính đó có API riêng, chịu điều kiện hỗ trợ manager/database.
6. **Đọc `@Transactional` bằng reflection ở một method rồi cho rằng proxy đã chạy.** Metadata tồn tại không chứng minh annotation được intercept ở runtime.
7. **Quên self-invocation.** Lời gọi `this.methodWithLabel()` trong proxy mode thông thường không kích hoạt interceptor riêng của method bị gọi.
8. **Coi `getLabels()` có thứ tự được đảm bảo.** Mục đích thường là tập nhãn; test tập giá trị thay vì phụ thuộc thứ tự không được API hứa hẹn.
9. **Mặc định label trên method kết hợp với label của class.** Cần kiểm tra resolution thực tế; đừng giả định tự hợp nhất.
10. **Thấy wrapper ghi hai nhãn và tưởng có hai physical transaction.** `REQUIRED` có thể tham gia transaction outer.
11. **Phụ thuộc hẳn vào manager cụ thể mà không có test.** Khi đổi công nghệ, các option riêng có thể không còn tác dụng.
12. **Thử behavior chỉ bằng unit test đọc annotation.** Cần integration test gọi qua proxy và đo thay đổi dữ liệu/quan sát manager.

## 11. Quy trình xác minh cho một label trong dự án thật

Dùng các bước sau trước khi tuyên bố label “có tác dụng”:

1. **Xác định annotation chính xác:** import `org.springframework.transaction.annotation.Transactional`, phiên bản Spring có `label`, method/class nào khai báo.
2. **Kiểm tra metadata:** `AnnotationTransactionAttributeSource.getTransactionAttribute(method, clazz)` rồi `getLabels()`, xác minh tập label như mong đợi.
3. **Kiểm tra lời gọi qua proxy:** service được Spring quản lý, caller gọi từ bean khác, AOP transaction advice thực sự chạy.
4. **Xác định manager được chọn:** chú ý `transactionManager`, qualifier, transaction manager mặc định; đừng suy từ label.
5. **Đọc implementation hoặc tài liệu manager:** có đánh giá labels không, có whitelist không, hành vi áp dụng ở stage nào?
6. **Viết test đối chứng:** cùng nghiệp vụ có/không label; đo ít nhất một dấu hiệu cụ thể do consumer làm ra. Ví dụ bài học đo `observedLabels` và việc manager từ chối `training:reject`.
7. **Kiểm tra dữ liệu sau transaction boundary:** đừng để `@Transactional` trên chính test che khuất commit/rollback thật.
8. **Kiểm tra nested/proxy/propagation:** scope mới hay tham gia transaction sẵn có, label của mỗi scope có được quan sát theo contract hay không.
9. **Kiểm tra khi thay manager:** chạy lại các test về label và semantics mở rộng; cập nhật tài liệu cho người dùng API.

### Câu hỏi tự kiểm tra

**1.** `@Transactional(label = "timeout:10")` có chắc làm transaction timeout sau 10 giây không?  
**Không.** Dùng thuộc tính `timeout = 10` theo contract Spring, và xác minh manager hỗ trợ. Chuỗi label chỉ có ý nghĩa nếu manager/integration đã định nghĩa điều đó.

**2.** `@Transactional(value = "ordersTxManager", label = "audit")` chọn manager nào?  
Spring dùng `value` (alias của `transactionManager`) để định vị `ordersTxManager`; label `audit` là metadata dành cho manager đã chọn.

**3.** Chỉ dùng `getLabels()` trong unit test có chứng minh audit đã chạy?  
**Không.** Nó chứng minh Spring đã phân tích annotation. Muốn chứng minh audit phải quan sát kết quả của consumer thực sự.

**4.** Vì sao inner `@Transactional(label="inner")` không chắc tạo một transaction mới?  
Vì `PROPAGATION_REQUIRED` mặc định có thể tham gia physical transaction của outer. Label không thay đổi propagation.

**5.** Khi đổi `JdbcTransactionManager` sang một manager khác mà mọi test nghiệp vụ vẫn pass, có thể tuyên bố label mở rộng vẫn hoạt động không?  
**Không.** Phải có test riêng cho consumer của label và các hiệu ứng tùy manager; test commit/rollback thông thường chưa chứng minh option đặc thù được áp dụng.

## Tài liệu chính thức

- [Spring Framework — `@Transactional` settings và thuộc tính `label`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — `@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework 6.2 — `TransactionAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/TransactionAttribute.html)
- [Spring Framework 6.2 — `AnnotationTransactionAttributeSource` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/AnnotationTransactionAttributeSource.html)
- [Spring Framework — Transaction Propagation (`REQUIRED` và `REQUIRES_NEW`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
