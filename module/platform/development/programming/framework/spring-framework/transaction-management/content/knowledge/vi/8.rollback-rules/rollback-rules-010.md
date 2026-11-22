# ALL_EXCEPTIONS và thay đổi mặc định toàn cục từ Spring Framework 6.2

## 1. Điều thay đổi thực sự trong Spring Framework 6.2

Từ **Spring Framework 6.2**, ứng dụng có thể cấu hình **mặc định rollback cho mọi exception**, bao gồm checked exception, ở mức hạ tầng quản lý transaction dựa trên annotation:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.RollbackOn;

@Configuration
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
public class TransactionConfiguration {
}
```

Điểm cần nhấn mạnh: đây là **tùy chọn thay đổi mặc định toàn cục trong cấu hình transaction annotation**, **không phải** Spring 6.2 tự động đổi hành vi cho mọi ứng dụng ngay khi nâng cấp. Nếu không khai báo `rollbackOn` (hoặc cấu hình tương đương), giá trị mặc định **vẫn là `RollbackOn.RUNTIME_EXCEPTIONS`**: rollback khi `RuntimeException` hoặc `Error` thoát qua transaction interceptor, còn checked `Exception` thường dẫn tới commit nếu không có rollback rule riêng hay trạng thái rollback-only khác.

Chủ đề này thuộc **Quy tắc rollback**. Điều bạn cần học không chỉ là cú pháp `ALL_EXCEPTIONS` mà còn là:

1. Cơ chế cũ và cơ chế mới khác nhau thế nào khi phương thức ném checked exception.
2. `@EnableTransactionManagement(rollbackOn = ...)` thay đổi **default rule** ở đâu và trong phạm vi nào.
3. Quy tắc `rollbackFor`, `noRollbackFor` của một phương thức có ưu tiên hơn default toàn cục không.
4. Những gì **không** đổi: propagation, commit thất bại, transaction đã rollback-only, ngoại lệ được bắt bên trong phương thức, API transaction programmatic.
5. Cách kiểm tra kết quả bằng dữ liệu thật sau khi lời gọi qua proxy kết thúc.
6. Cách đánh giá tác động khi nâng cấp một ứng dụng đang dùng checked exception như tín hiệu nghiệp vụ.

Ví dụ thực hành bên dưới dùng **Java 17+, Spring Framework 6.2.6, Spring JDBC, H2, JUnit 5 và Gradle**. Phiên bản 6.2.6 được khóa để mã và API có thể kiểm chứng nhất quán; đây là phiên bản minh họa, không phải nhận định về bản Spring mới nhất.

## 2. Nhắc lại: checked và unchecked exception

Java phân loại các lỗi có liên quan tới quy tắc rollback như sau:

```text
java.lang.Throwable
  |
  +-- Error                         -> không phải Exception
  |
  +-- Exception
        |
        +-- RuntimeException        -> unchecked
        |     +-- IllegalArgumentException
        |     +-- IllegalStateException
        |     +-- ...
        |
        +-- IOException             -> checked
        +-- SQLException            -> checked
        +-- BusinessNotice          -> checked tùy chỉnh
```

**Checked exception** thường là các lớp kế thừa `Exception` nhưng không kế thừa `RuntimeException`; Java buộc method khai báo `throws` hoặc bắt chúng. **Unchecked exception** bao gồm `RuntimeException` và `Error`; không cần khai báo `throws`. Kotlin không áp đặt việc kiểm tra checked exception theo cách Java làm, nên quy tắc rollback nhất quán cho cả hai nhóm có thể đặc biệt hữu ích ở ứng dụng Kotlin.

### 2.1. Cơ chế truyền thống của Spring

Ví dụ:

```java
@Transactional
public void saveThenThrow() throws IOException {
    jdbc.update("INSERT INTO audit_event(code) VALUES (?)", "T1");
    throw new IOException("I/O failed");
}
```

Đây là đoạn code minh họa trong service có `JdbcTemplate jdbc`; cần Spring-managed bean, transaction manager và schema bảng thật để chạy. Trong chế độ **`RUNTIME_EXCEPTIONS`** mặc định, `IOException` không khớp rule rollback tự động: Spring có thể **commit INSERT rồi tiếp tục ném IOException cho caller**. Người gọi thấy exception **không đồng nghĩa** thay đổi dữ liệu đã rollback.

Nếu thay bằng `IllegalStateException` thoát qua transaction interceptor, mặc định Spring sẽ yêu cầu rollback. Nếu một `IOException` bị bắt **trong chính method** và method return bình thường, interceptor không nhìn thấy exception đó, vì vậy thay đổi toàn cục sang `ALL_EXCEPTIONS` cũng không tự làm transaction rollback (trừ khi có thành phần khác đánh dấu rollback-only).

### 2.2. Bảng quyết định trước và sau khi bật ALL_EXCEPTIONS

Giả sử một **transaction mới**, không có rollback-only từ trước, thao tác ghi chưa commit và manager có thể hoàn tất bình thường:

| Kịch bản | `RUNTIME_EXCEPTIONS` (mặc định) | `ALL_EXCEPTIONS` (bật tường minh) |
| --- | --- | --- |
| Method return bình thường | Commit | Commit |
| `IllegalStateException` thoát qua proxy | Rollback | Rollback |
| `IOException` thoát qua proxy, không rule riêng | **Commit** | **Rollback** |
| `SQLException` thoát qua proxy, không rule riêng | **Commit** | **Rollback** |
| `Error` thoát qua proxy | Rollback | Rollback |
| `@Transactional(rollbackFor = IOException.class)` ném `IOException` | Rollback | Rollback |
| `@Transactional(noRollbackFor = IOException.class)` ném `IOException` | Commit | Commit — rule của method thắng default |
| `@Transactional(noRollbackFor = BusinessNotice.class)` ném `IOException` | Commit (default cũ) | **Rollback** (vẫn giữ default mới cho lỗi không khớp rule) |
| Checked exception đã bị catch bên trong và method return | Thường commit | Thường commit |
| Inner `REQUIRED` đã đặt rollback-only, outer catch rồi return | Rollback theo trạng thái | Rollback theo trạng thái |

Cột "commit" là **quyết định theo rollback rule**, không phải cam kết rằng database luôn commit thành công: `commit()` vẫn có thể gặp lỗi, hoặc transaction đã bị đánh dấu rollback-only vì nguyên nhân khác.

## 3. API mới: `RollbackOn` và `@EnableTransactionManagement.rollbackOn`

Spring Framework 6.2 đưa vào enum:

```java
package org.springframework.transaction.annotation;

public enum RollbackOn {
    RUNTIME_EXCEPTIONS,
    ALL_EXCEPTIONS
}
```

Đoạn trên **chỉ mô phỏng hình dạng enum để học**; không tạo file enum này trong ứng dụng. Trong thực tế, chỉ import enum từ Spring.

| Giá trị | Vai trò |
| --- | --- |
| `RollbackOn.RUNTIME_EXCEPTIONS` | Mặc định truyền thống: runtime exception và `Error` gây rollback |
| `RollbackOn.ALL_EXCEPTIONS` | Chế độ tùy chọn: cả checked `Exception` cũng gây rollback theo default rule |

Cú pháp bật:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.RollbackOn;

@Configuration
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
class GlobalRollbackConfiguration {
}
```

Cú pháp giữ chế độ cũ một cách tường minh:

```java
@EnableTransactionManagement(
    rollbackOn = RollbackOn.RUNTIME_EXCEPTIONS
)
class TraditionalRollbackConfiguration {
}
```

Hai snippet là các ví dụ **cấu hình riêng biệt**; không đăng ký đồng thời hai cấu hình này trong cùng một application context rồi mong mỗi annotation điều khiển một nhóm service. Chế độ mặc định là lựa chọn của **hạ tầng annotation-driven transaction management trong context**, không phải giá trị được chọn riêng tại mỗi lời gọi bằng một annotation trên service.

### 3.1. Nâng phiên bản có tự bật ALL_EXCEPTIONS không?

**Không.** Cần phân biệt hai sự kiện:

- **Nâng từ Spring Framework 6.1 lên 6.2:** ứng dụng có thêm API `RollbackOn`, `@EnableTransactionManagement.rollbackOn` và `AnnotationTransactionAttributeSource.addDefaultRollbackRule(...)`.
- **Bật `rollbackOn = RollbackOn.ALL_EXCEPTIONS`:** bạn chủ động thay fallback rollback rule cho transaction annotations. Đây mới là hành động khiến checked exception chưa có rule cụ thể được xử lý khác.

Nếu chưa thay cấu hình, một checked `IOException` trong `@Transactional` vẫn có thể dẫn tới commit như trước. Viết test hồi quy để phát hiện thay đổi do cấu hình trước khi kết luận "Spring 6.2 làm mọi checked exception rollback".

### 3.2. Phiên bản Spring Boot cần kiểm tra

Spring Boot **3.3.x** dùng nền Spring Framework **6.1.x**, nên mã tham chiếu `RollbackOn` ở trên không compile với dependency set 3.3.x. Spring Boot **3.4.x** dùng nền Spring Framework **6.2.x** (ví dụ Boot 3.4.5 quản lý Spring 6.2.6). Nếu làm trong dự án Boot, hãy kiểm tra dependency tree **thực tế**, không dựa duy nhất vào phiên bản Java hoặc tên plugin.

Một cấu hình ngắn trong dự án Boot có thể là:

```java
@SpringBootApplication
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Snippet này minh họa cách đặt cấu hình; cần import `SpringBootApplication`, `SpringApplication` và transaction annotations, đồng thời ứng dụng phải có transaction manager và cơ chế truy cập dữ liệu phù hợp. Phần thực hành đầy đủ sau dùng **Spring Framework trực tiếp** để so sánh hai mode tách biệt, tránh để auto-configuration che khuất điểm cần học.

## 4. Spring áp dụng default rule mới ở đâu?

Luồng transaction declarative thông thường:

```text
External caller
  -> Spring AOP proxy
       -> TransactionInterceptor
          -> AnnotationTransactionAttributeSource
             - đọc Spring @Transactional / JTA @Transactional
             - tạo RuleBasedTransactionAttribute
             - bổ sung default rollback rule nếu được cấu hình
          -> PlatformTransactionManager.getTransaction(...)
          -> gọi target method
          -> nếu exception thoát ra:
               TransactionAttribute.rollbackOn(exception)
               -> chọn commit / rollback cho scope
          -> manager.commit(status) hoặc rollback(status)
  -> caller nhận kết quả/exception
```

Ở mức API, một cấu hình `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)` cung cấp default rule cho **rule-based transaction attributes** mà hạ tầng annotation của Spring tạo ra. Trong Spring Framework 6.2, `AnnotationTransactionAttributeSource` hỗ trợ:

```java
AnnotationTransactionAttributeSource source =
        new AnnotationTransactionAttributeSource();

source.addDefaultRollbackRule(
        RollbackRuleAttribute.ROLLBACK_ON_ALL_EXCEPTIONS);
```

Đoạn trên **chỉ minh họa cấu hình một instance metadata source**, cần import `AnnotationTransactionAttributeSource` và `RollbackRuleAttribute`. Tạo biến `source` riêng trong application code **không tự thay thế** source mà proxy transaction infrastructure đang sử dụng. Muốn thay đổi behavior thật phải cấu hình đúng infrastructure bean, hoặc đơn giản dùng `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`.

### 4.1. Vì sao có `addDefaultRollbackRule`?

API này cho phép bổ sung **fallback rule** cho những exception mà method chưa có rule cụ thể. Nó đặc biệt hữu ích khi ứng dụng có một quy ước rollback mặc định muốn áp dụng trên các attribute do Spring phân tích, nhưng vẫn giữ các ngoại lệ nghiệp vụ được khai báo tường minh.

Không cần mỗi service đều lặp `rollbackFor = Exception.class`. Tuy nhiên, **global fallback không xóa rule cục bộ**. Một method `noRollbackFor` tường minh vẫn có thể cho phép commit đối với một loại exception được chỉ định.

### 4.2. Phạm vi thay đổi không phải “toàn JVM”

Từ **toàn cục** ở đây cần hiểu chính xác: phạm vi của **annotation-driven transaction management infrastructure đang được cấu hình** (thường là một Spring `ApplicationContext`). Không nên suy ra:

- Mọi ứng dụng khác trong cùng JVM hoặc microservice khác cũng đổi default.
- Mọi API `PlatformTransactionManager` được gọi thủ công đều phải áp dụng default này.
- `TransactionTemplate` được cấu hình lại rule rollback bằng annotation này.
- Mọi transaction do database/JTA container tạo bên ngoài Spring cũng thay đổi.
- Transaction trong thread khác/`@Async` tự tham gia transaction đang mở.
- Hành vi commit/rollback của tài nguyên không tham gia manager (email, HTTP, message broker) tự được điều chỉnh.

Chế độ này có tác động đến các annotation `org.springframework.transaction.annotation.Transactional` và, khi được Spring transaction infrastructure phân tích, cả `jakarta.transaction.Transactional`. Điều đó **không có nghĩa** nó tái cấu hình EJB/JTA transaction container độc lập ngoài Spring. Các `TransactionAttribute` không dựa trên rollback rules không bị đổi theo kiểu “chèn default rule vào mọi object” một cách tự động.

## 5. Thứ tự ưu tiên: rule cục bộ mạnh hơn fallback

Với Spring `@Transactional`, các thuộc tính liên quan là:

- `rollbackFor`: những exception class nào yêu cầu rollback.
- `rollbackForClassName`: mẫu tên exception yêu cầu rollback.
- `noRollbackFor`: những exception class nào yêu cầu **không** rollback.
- `noRollbackForClassName`: mẫu tên exception yêu cầu **không** rollback.

Ví dụ:

```java
@Transactional(noRollbackFor = IOException.class)
public void saveEvenIfIoFails() throws IOException {
    // ...
}
```

Khi có `ALL_EXCEPTIONS`, một `IOException` thoát ra từ method trên khớp `noRollbackFor = IOException.class` **cụ thể hơn** fallback quy định rollback cho `Exception`, nên Spring chọn **commit** nếu transaction chưa rollback-only và manager commit thành công.

Trong khi đó:

```java
@Transactional(noRollbackFor = BusinessNotice.class)
public void saveThenThrowDifferentChecked() throws IOException {
    // ...
}
```

Nếu method ném `IOException`, rule `noRollbackFor = BusinessNotice.class` **không khớp** exception này. Vì vậy fallback ALL_EXCEPTIONS vẫn hoạt động → **rollback**.

### 5.1. “Strongest matching rule wins”

Spring so khớp một rule theo exception class và các superclass. Rule khớp trực tiếp với type cụ thể thường mạnh hơn một rule khớp qua superclass xa hơn. Ví dụ:

```java
@Transactional(
    noRollbackFor = IOException.class,
    rollbackFor = java.io.FileNotFoundException.class
)
public void openFile() throws IOException {
    // ...
}
```

- Nếu phát sinh `FileNotFoundException`: rule rollback cho chính class này mạnh hơn no-rollback dành cho `IOException` → **rollback**.
- Nếu phát sinh `EOFException`: no-rollback cho `IOException` khớp qua superclass → **commit** theo rule, trừ rollback-only/nguyên nhân khác.
- Nếu phát sinh `SQLException`: không có rule cục bộ khớp, dùng default: **rollback** dưới `ALL_EXCEPTIONS`; **commit** dưới `RUNTIME_EXCEPTIONS`.

Snippet chỉ minh họa rule; không phải method có logic độc lập chạy được. Không dùng hai rule **mâu thuẫn và cùng độ cụ thể** cho một exception rồi trông chờ một chính sách dễ đọc; hãy đưa ra một quy tắc tường minh và kiểm thử.

### 5.2. Tại sao nên dùng type thay vì pattern?

`rollbackForClassName` và `noRollbackForClassName` dùng **substring matching** trên tên exception, không phải glob/regex đầy đủ. Một pattern ngắn như `"Exception"` dễ khớp ngoài dự kiến; thậm chí tên class chứa cùng tiền tố cũng có thể bị ảnh hưởng. Dùng `rollbackFor = MyException.class` / `noRollbackFor = MyException.class` khi có thể, để rule type-safe và không vô tình mở rộng phạm vi.

### 5.3. Global ALL_EXCEPTIONS không phủ quyết trạng thái rollback-only

Nếu inner transactional scope tham gia physical transaction theo `REQUIRED` và đánh dấu rollback-only, outer method có thể bắt exception rồi return bình thường. Khi outer định commit, manager vẫn không được commit physical transaction. `noRollbackFor` ở một boundary không phải lệnh “xóa rollback-only” do boundary khác đã đặt. Tình huống này có thể đưa tới `UnexpectedRollbackException` khi outer commit.

## 6. Vì sao Spring giới thiệu chế độ ALL_EXCEPTIONS?

Trong nhiều ứng dụng hiện đại, checked exception không còn được dùng như một tín hiệu "ngoại lệ nghiệp vụ chấp nhận commit" một cách nhất quán. Một repository có thể ném checked exception do I/O; một service đôi khi khai báo `throws Exception`; Kotlin không bắt buộc checked exception. Nếu developer quên `rollbackFor`, một thao tác đã ghi dữ liệu có thể **commit dù caller nhận lỗi**.

`ALL_EXCEPTIONS` cho phép đặt baseline nhất quán: **mọi exception được ném ra khỏi transactional method sẽ yêu cầu rollback, trừ khi method khai báo khác**. Bởi vậy Spring 6.2 khuyến nghị cân nhắc chế độ này nếu ứng dụng không dựa vào quy tắc EJB-style business exception mang ý nghĩa commit.

Nhưng bật toàn cục cũng là **thay đổi hợp đồng nghiệp vụ**, không chỉ dọn code. Ví dụ một service nhận yêu cầu, lưu hồ sơ và ném checked `DocumentPendingReviewException` để caller biết còn phải phê duyệt. Trước đây nó có thể commit hồ sơ; khi bật ALL_EXCEPTIONS, cùng code sẽ rollback trừ khi được điều chỉnh. Cần xác định đây có thật là thiết kế nên giữ hay là lỗ hổng cần sửa.

### 6.1. Ba nhóm method cần rà soát khi migration

| Nhóm | Hiện trạng trước thay đổi | Hành động khi bật ALL_EXCEPTIONS |
| --- | --- | --- |
| Checked exception biểu thị **thất bại, dữ liệu phải hủy** | Dễ commit ngoài ý muốn nếu thiếu `rollbackFor` | Default mới giúp nhất quán; thêm test rollback |
| Checked exception biểu thị **kết quả nghiệp vụ có chủ ý giữ dữ liệu** | Có thể cố ý commit rồi ném exception | Cân nhắc đổi kiểu kết quả thành return value hoặc khai báo `noRollbackFor` rõ ràng; thêm test commit |
| Method đã có `rollbackFor/noRollbackFor` chi tiết | Rule cụ thể đã điều khiển một số loại exception | Giữ rule; kiểm tra **các loại exception chưa được rule bao phủ** vì chúng chịu fallback mới |

Phải xem call path thật qua proxy, exception bị bắt ở đâu, propagation và transaction manager. Các phương thức không có transaction advice, hoặc tự gọi nhau qua `this` trong proxy mode, không tự được sửa bằng default mới.

## 7. Thực hành so sánh trực tiếp hai mode trên Spring Framework 6.2

Thay vì hai ứng dụng Spring Boot riêng, ta dùng **hai Spring test application contexts độc lập** với cùng một service:

- Context thứ nhất dùng `@EnableTransactionManagement` mặc định (tức `RUNTIME_EXCEPTIONS`).
- Context thứ hai bật `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`.

Mỗi context có H2 database riêng được đặt tên duy nhất để tránh nhiễu. Ta quan sát số hàng sau khi service được Spring proxy gọi và exception đã đến test. Đây là **kiểm thử tích hợp**, có database transaction thật trong H2; không cần web server hay Spring Boot.

### 7.1. Cấu trúc tệp

```text
rollback-defaults/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/rollback/
    │   │   ├── BusinessNotice.java
    │   │   ├── RollbackScenarios.java
    │   │   ├── DatabaseBeans.java
    │   │   ├── TraditionalMode.java
    │   │   └── AllExceptionsMode.java
    │   └── resources/
    │       └── schema.sql
    └── test/
        └── java/com/example/rollback/
            ├── TraditionalModeTest.java
            └── AllExceptionsModeTest.java
```

Yêu cầu: **Java 17+**, Gradle 8.x tương thích và có kết nối Maven Central cho dependency lần chạy đầu tiên. Mọi file Java ở cùng package `com.example.rollback`. Không tạo thêm `@EnableTransactionManagement` nào khác trong hai test contexts.

`settings.gradle`:

```groovy
rootProject.name = 'rollback-defaults'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
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
    implementation 'org.springframework:spring-context:6.2.6'
    implementation 'org.springframework:spring-jdbc:6.2.6'
    implementation 'org.springframework:spring-tx:6.2.6'

    runtimeOnly 'com.h2database:h2:2.3.232'
    testImplementation 'org.springframework:spring-test:6.2.6'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Các bản `spring-context`, `spring-jdbc`, `spring-tx` và `spring-test` được khóa cùng **6.2.6** để API `RollbackOn` nhất quán. H2 là runtime dependency vì `EmbeddedDatabaseBuilder` nạp driver H2 khi context khởi tạo. `spring-context`/`spring-tx` cung cấp hạ tầng AOP/annotation transaction và `spring-test` cung cấp `@SpringJUnitConfig`.

### 7.2. Schema H2

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_receipts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    business_key VARCHAR(80) NOT NULL UNIQUE
);
```

Ràng buộc `UNIQUE` giúp xác định một business key riêng cho mỗi test. H2 chỉ là môi trường kiểm chứng quy tắc Spring; các đặc tính isolation/lock/DDL khác có thể cần thử lại với database production.

### 7.3. Một checked exception nghiệp vụ

`src/main/java/com/example/rollback/BusinessNotice.java`:

```java
package com.example.rollback;

public class BusinessNotice extends Exception {
    public BusinessNotice(String message) {
        super(message);
    }
}
```

Class này extends `Exception`, **không extends `RuntimeException`**, nên nó là checked exception. Mỗi method ném nó phải khai báo `throws BusinessNotice` hoặc catch. Trong thực tế, chỉ thiết kế exception kiểu này nếu việc ném exception thật sự phù hợp hợp đồng của API.

### 7.4. Service có các nhánh kiểm chứng

`src/main/java/com/example/rollback/RollbackScenarios.java`:

```java
package com.example.rollback;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

public class RollbackScenarios {
    private final JdbcTemplate jdbc;

    public RollbackScenarios(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void success(String businessKey) {
        insert(businessKey);
    }

    @Transactional
    public void checkedIOException(String businessKey) throws IOException {
        insert(businessKey);
        throw new IOException("simulated checked failure");
    }

    @Transactional
    public void runtimeFailure(String businessKey) {
        insert(businessKey);
        throw new IllegalStateException("simulated runtime failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void checkedWithExplicitRollback(String businessKey) throws IOException {
        insert(businessKey);
        throw new IOException("explicit rollback rule");
    }

    @Transactional(noRollbackFor = IOException.class)
    public void checkedWithExplicitNoRollback(String businessKey) throws IOException {
        insert(businessKey);
        throw new IOException("explicit no-rollback rule");
    }

    @Transactional(noRollbackFor = BusinessNotice.class)
    public void acceptedBusinessNotice(String businessKey) throws BusinessNotice {
        insert(businessKey);
        throw new BusinessNotice("saved, but needs review");
    }

    @Transactional(noRollbackFor = BusinessNotice.class)
    public void unrelatedCheckedIOException(String businessKey) throws IOException {
        insert(businessKey);
        throw new IOException("unrelated to BusinessNotice");
    }

    @Transactional
    public void caughtCheckedInside(String businessKey) {
        insert(businessKey);
        try {
            throw new IOException("handled internally");
        } catch (IOException ignored) {
            // Để giải thích cơ chế: interceptor sẽ thấy return bình thường.
            // Production không nên nuốt một lỗi nghiệp vụ quan trọng như thế.
        }
    }

    private void insert(String businessKey) {
        jdbc.update(
                "INSERT INTO tx_receipts(business_key) VALUES (?)",
                businessKey);
    }
}
```

Các method public được gọi qua **Spring-managed proxy** trong test. `insert` là helper private; nó không cần `@Transactional` riêng vì mọi method công khai đã tạo hoặc tham gia transaction trước khi gọi helper.

Tám nhánh này cố ý giữ logic SQL giống nhau. Chỉ khác **exception thoát ra**, **rollback rule cục bộ** và **global default**, giúp quan sát quyết định của Spring rõ ràng.

### 7.5. Cấu hình database và transaction manager dùng chung

`src/main/java/com/example/rollback/DatabaseBeans.java`:

```java
package com.example.rollback;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class DatabaseBeans {
    @Bean
    public DataSource dataSource() {
        return new EmbeddedDatabaseBuilder()
                .generateUniqueName(true)
                .setType(EmbeddedDatabaseType.H2)
                .addScript("schema.sql")
                .build();
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public RollbackScenarios rollbackScenarios(JdbcTemplate jdbcTemplate) {
        return new RollbackScenarios(jdbcTemplate);
    }
}
```

`generateUniqueName(true)` rất quan trọng: mỗi `ApplicationContext` tạo một in-memory database riêng. `DataSourceTransactionManager` sở hữu transaction JDBC trên datasource đó. `RollbackScenarios` là Spring bean, nên `@EnableTransactionManagement` có thể tạo proxy cho nó. Ta không cần gọi `commit()` hoặc `rollback()` bằng tay trong service.

### 7.6. Hai cấu hình độc lập

`src/main/java/com/example/rollback/TraditionalMode.java`:

```java
package com.example.rollback;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@Import(DatabaseBeans.class)
@EnableTransactionManagement // mặc định RUNTIME_EXCEPTIONS
public class TraditionalMode {
}
```

`src/main/java/com/example/rollback/AllExceptionsMode.java`:

```java
package com.example.rollback;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.RollbackOn;

@Configuration(proxyBeanMethods = false)
@Import(DatabaseBeans.class)
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
public class AllExceptionsMode {
}
```

**Lưu ý:** ta không thêm cả hai config vào cùng một context. Mỗi test class bên dưới chọn **một** config qua `@SpringJUnitConfig(classes = ...)`. Đây là cách cô lập lựa chọn toàn cục để đối chiếu; không yêu cầu ứng dụng production có nhiều context.

### 7.7. Test chế độ cũ: checked exception vẫn có thể commit

`src/test/java/com/example/rollback/TraditionalModeTest.java`:

```java
package com.example.rollback;

import java.io.IOException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(classes = TraditionalMode.class)
class TraditionalModeTest {
    @Autowired
    private RollbackScenarios service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_receipts");
    }

    private long rows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_receipts", Long.class);
    }

    @Test
    void checkedIOExceptionCommitsWithLegacyDefault() {
        assertThrows(IOException.class,
                () -> service.checkedIOException("legacy-checked"));
        assertEquals(1L, rows());
    }

    @Test
    void runtimeExceptionRollsBackWithLegacyDefault() {
        assertThrows(IllegalStateException.class,
                () -> service.runtimeFailure("legacy-runtime"));
        assertEquals(0L, rows());
    }

    @Test
    void explicitRollbackForCheckedStillWorks() {
        assertThrows(IOException.class,
                () -> service.checkedWithExplicitRollback("legacy-explicit"));
        assertEquals(0L, rows());
    }
}
```

Bằng chứng quan trọng là test **không có `@Transactional`**. Mỗi lời gọi service đi qua transaction proxy, transaction của service kết thúc, rồi test đọc dữ liệu. Vì vậy `1L` trong test checked exception là kết quả **đã commit** của transaction mới trong ví dụ, không phải bản ghi còn nằm trong test-managed transaction chưa commit.

### 7.8. Test chế độ mới: mặc định ALL_EXCEPTIONS và các ngoại lệ cục bộ

`src/test/java/com/example/rollback/AllExceptionsModeTest.java`:

```java
package com.example.rollback;

import java.io.IOException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(classes = AllExceptionsMode.class)
class AllExceptionsModeTest {
    @Autowired
    private RollbackScenarios service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_receipts");
    }

    private long rows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_receipts", Long.class);
    }

    @Test
    void normalReturnStillCommits() {
        service.success("all-ok");
        assertEquals(1L, rows());
    }

    @Test
    void checkedIOExceptionNowRollsBackByDefault() {
        assertThrows(IOException.class,
                () -> service.checkedIOException("all-checked"));
        assertEquals(0L, rows());
    }

    @Test
    void runtimeExceptionStillRollsBack() {
        assertThrows(IllegalStateException.class,
                () -> service.runtimeFailure("all-runtime"));
        assertEquals(0L, rows());
    }

    @Test
    void explicitRollbackForIsStillHonored() {
        assertThrows(IOException.class,
                () -> service.checkedWithExplicitRollback("all-explicit"));
        assertEquals(0L, rows());
    }

    @Test
    void explicitNoRollbackForOverridesGlobalFallback() {
        assertThrows(IOException.class,
                () -> service.checkedWithExplicitNoRollback("all-excluded"));
        assertEquals(1L, rows());
    }

    @Test
    void specificBusinessNoRollbackForCanStillCommit() {
        assertThrows(BusinessNotice.class,
                () -> service.acceptedBusinessNotice("all-notice"));
        assertEquals(1L, rows());
    }

    @Test
    void unrelatedCheckedExceptionStillUsesAllExceptionsDefault() {
        assertThrows(IOException.class,
                () -> service.unrelatedCheckedIOException("all-unrelated"));
        assertEquals(0L, rows());
    }

    @Test
    void exceptionCaughtInsideIsInvisibleToRollbackRules() {
        service.caughtCheckedInside("all-caught");
        assertEquals(1L, rows());
    }
}
```

### 7.9. Chạy và hiểu kết quả

Nếu thư mục dự án được tạo bằng Spring Initializr hoặc đã có Gradle Wrapper, chạy:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

Nếu tự tạo các file như cây thư mục mà chưa có wrapper, dùng Gradle đã cài tương thích để chạy `gradle test` hoặc tạo wrapper trước. Không dùng `javac` trần cho dự án Spring vì classpath gồm nhiều thư viện; Gradle xử lý compile và test.

**Kết quả kỳ vọng** khi dependency đúng và không có môi trường test chạy song song gây nhiễu: **11 test pass** (3 ở `TraditionalModeTest` và 8 ở `AllExceptionsModeTest`). JUnit không bảo đảm thứ tự các method test và các test **không in stdout cố định**. Xem `build/reports/tests/test/index.html` để kiểm tra kết quả chạy thật.

Bảng đối chiếu chính:

| Phép thử | Context truyền thống | Context ALL_EXCEPTIONS |
| --- | ---: | ---: |
| Method success, không exception | Commit 1 hàng | Commit 1 hàng |
| Checked `IOException`, không rule riêng | **Commit 1 hàng** | **Rollback 0 hàng** |
| Runtime `IllegalStateException` | Rollback 0 hàng | Rollback 0 hàng |
| Checked với `rollbackFor=IOException.class` | Rollback 0 hàng | Rollback 0 hàng |
| Checked với `noRollbackFor=IOException.class` | Commit 1 hàng | Commit 1 hàng |
| Checked `BusinessNotice` với `noRollbackFor` cụ thể | Commit 1 hàng | Commit 1 hàng |
| Checked `IOException` không khớp `noRollbackFor=BusinessNotice.class` | Commit 1 hàng | Rollback 0 hàng |
| Checked exception đã bị catch trong method | Commit 1 hàng | Commit 1 hàng |

Bảng cung cấp **dự đoán từ Spring 6.2 và mã ví dụ**; test thực tế chỉ triển khai những trường hợp được liệt kê trong hai class test. Đừng suy từ việc `assertThrows` thành công rằng transaction đã rollback; `rows()` mới là bằng chứng trạng thái dữ liệu sau khi service boundary hoàn tất.

## 8. Các giới hạn không được bỏ qua

### 8.1. “ALL_EXCEPTIONS” không có nghĩa rollback mọi tình huống

Tham số này điều khiển **quyết định rollback trên exception thoát qua transaction interception** theo default rules. Nó **không** tự rollback khi:

- Method return bình thường và không có rollback-only.
- Exception bị bắt rồi nuốt bên trong transactional method.
- SQL đã commit bởi transaction **khác** hoặc trước khi transaction này bắt đầu.
- Tác dụng ngoài database như HTTP request, email hoặc message broker đã xảy ra.
- Lỗi xuất hiện **sau physical commit** hoặc ở một tài nguyên không nằm trong transaction manager đang dùng.
- Transaction ở một thread khác không được truyền ngữ cảnh giao dịch phù hợp.

Khi commit thất bại hoặc connection đứt ở thời điểm commit, outcome có thể không chắc chắn. **Không coi mọi exception là bằng chứng rollback đã thành công.** Với tác vụ có tác dụng nghiệp vụ quan trọng, cần idempotency key và cơ chế đối soát.

### 8.2. Checked exception và “no rollback” vẫn có thể bị rollback-only

Giả sử outer `@Transactional(noRollbackFor = IOException.class)` bắt hoặc phát ra `IOException`, nhưng một inner `REQUIRED` đã bị đánh dấu rollback-only trước đó. Dù rule outer chọn commit, transaction manager vẫn phải tuân theo trạng thái rollback-only; có thể ném `UnexpectedRollbackException`. **Thứ tự ưu tiên của rule không phải cách xóa rollback-only đã được đặt.**

### 8.3. Proxy và self-invocation

`@Transactional` được thực thi khi lời gọi đi qua transactional proxy (trong proxy mode mặc định). Nếu một method mang annotation được gọi qua `this.innerMethod()` trong cùng bean, Spring proxy thường không intercept lời gọi nội bộ đó; rollback default cũng không tự áp dụng như một transaction boundary riêng.

```java
@Service
class ExampleService {
    public void outer() throws IOException {
        this.inner(); // Không đi qua proxy cho lời gọi inner().
    }

    @Transactional
    public void inner() throws IOException {
        throw new IOException("checked");
    }
}
```

Đây là ví dụ cơ chế cần import `@Service`, `@Transactional`, `IOException`; không phải chương trình độc lập. Muốn kiểm thử, gọi một **Spring-managed bean khác** qua injection hoặc dùng transaction template khi cần điều khiển programmatic. Đừng tuyên bố default toàn cục sai khi thực tế advice chưa chạy.

### 8.4. Reactive transaction và các dạng trả về đặc biệt

Với `ReactiveTransactionManager`, transaction liên kết với **Reactor context** và lifecycle publisher thay vì ThreadLocal imperative. Một cấu hình rollback mặc định có thể được dùng khi hạ tầng reactive phân tích transaction attributes, nhưng tín hiệu `onError`, `cancel` và thời điểm subscribe cần hiểu riêng. Không áp công thức "method Java return bình thường → commit" cho `Mono`/`Flux`.

Trong Spring 6.1+, một `Future` đã hoàn thành exceptional tại thời điểm method return có thể được transaction infrastructure xét theo rollback rules. Điều này không đồng nghĩa transaction imperative sẽ chờ mọi tác vụ background hoàn tất sau đó. Các tác vụ `@Async` và retry advice cần được thử ở đúng boundary và thứ tự advice thực tế.

### 8.5. Test-managed transaction che khuất kết quả

Trong Spring TestContext, một test gắn `@Transactional` thường được mở transaction riêng và rollback sau test. Service với `REQUIRED` có thể tham gia transaction của test, nên việc nhìn thấy bản ghi **trong test** chưa chứng minh service đã commit. Bộ test thực hành không gắn annotation ấy lên test class nhằm quan sát sau boundary.

### 8.6. Hệ quản trị dữ liệu có thể ném exception khác kỳ vọng

`JdbcTemplate` thường dịch SQL exception sang `DataAccessException` (unchecked); trường hợp này vốn đã rollback dưới mặc định cũ. ALL_EXCEPTIONS chủ yếu tạo khác biệt khi **checked exception thực sự thoát ra** từ transactional method. Khi dùng JPA, SQL có thể được flush lúc commit, khiến exception xuất hiện sau method body. Kiểm thử với H2 không chứng minh mọi loại isolation/lock/flush của database production.

## 9. Checklist migration khi bật global rollback

Không nên đổi một annotation rồi dự đoán mọi luồng nghiệp vụ vẫn giữ nguyên. Có thể triển khai theo thứ tự:

1. **Xác nhận dependency** thật sự dùng Spring Framework 6.2+; nếu là Spring Boot, đối chiếu phiên bản Spring do BOM quản lý.
2. **Kiểm kê các public transactional methods** có checked `throws` hoặc gọi thư viện ném checked exception. Với Kotlin, tìm cả những lỗi checked của Java mà Kotlin không bắt khai báo.
3. **Phân loại exception theo ý nghĩa nghiệp vụ**: lỗi phải hủy toàn bộ thay đổi, lỗi nên giữ dữ liệu, lỗi được bắt và phục hồi, lỗi vượt qua tài nguyên khác.
4. **Viết regression test trước khi đổi mode** cho những method đang phụ thuộc checked exception commit: quan sát số hàng/trạng thái thực sau proxy.
5. **Bật `rollbackOn = ALL_EXCEPTIONS`** ở đúng transaction configuration context; không lặp nhiều cấu hình mâu thuẫn.
6. **Khai báo `noRollbackFor` cụ thể** cho những exception mà nghiệp vụ chủ ý commit; hoặc tốt hơn, cân nhắc trả về một result type để không dùng exception làm tín hiệu thành công một phần.
7. **Kiểm tra rule không được bao phủ** bởi rollbackFor/noRollbackFor cục bộ, nhất là các method vốn chỉ khai báo một exception nhưng có thể ném exception khác.
8. **Thử nested propagation và rollback-only**, ví dụ inner `REQUIRED` ném checked exception được outer catch; global default mới có thể đánh dấu shared transaction rollback-only.
9. **Đọc dữ liệu sau transaction boundary** trong test không gắn `@Transactional` để xác nhận commit/rollback thật.
10. **Xác minh thực tế với database production-compatible** nếu logic liên quan constraint, flush, savepoint, lock hoặc transaction manager đặc biệt.
11. **Đo và cập nhật contract** của các API trả về error/exception: caller có thể vẫn nhận cùng IOException nhưng dữ liệu đằng sau đã thay đổi từ committed sang rolled back.
12. **Theo dõi deployment**, vì thay đổi này có thể làm tăng rollback và thay đổi số lần retry/khả năng quan sát sự kiện nghiệp vụ.

Một migration đúng phải giữ **invariant nghiệp vụ**, không chỉ chạy xanh một unit test kiểm tra annotation. Nếu nghiệp vụ "lưu đơn rồi báo cần bổ sung thông tin" phải giữ đơn, cần thiết kế status phù hợp; đừng chỉ dùng checked exception và dựa vào thói quen commit mặc định.

## 10. Các ngộ nhận thường gặp

**Ngộ nhận 1 — Nâng lên Spring 6.2 tự động rollback mọi checked exception.**  
Sai. `RollbackOn.RUNTIME_EXCEPTIONS` vẫn là default; cần opt in để đổi.

**Ngộ nhận 2 — `ALL_EXCEPTIONS` tương đương `@Transactional(rollbackFor=Exception.class)` được sửa vào từng method.**  
Không hoàn toàn. Nó là **global fallback rule** do infrastructure cung cấp, có ưu tiên thấp hơn các rule cụ thể; không thay đổi source annotation từng method hay các transaction API ngoài phạm vi.

**Ngộ nhận 3 — Có `noRollbackFor` ở method thì không còn áp dụng default toàn cục cho exception khác.**  
Sai. Chỉ exception khớp rule được ưu tiên; exception không khớp vẫn dùng fallback.

**Ngộ nhận 4 — `noRollbackFor` đảm bảo commit thành công.**  
Sai. Transaction có thể đã rollback-only, SQL/commit có thể thất bại hoặc resource khác có lỗi.

**Ngộ nhận 5 — Checked exception bị catch bên trong vẫn làm rollback vì ALL_EXCEPTIONS.**  
Sai khi interceptor chỉ thấy method return bình thường và chưa có rollback-only.

**Ngộ nhận 6 — Đặt `@EnableTransactionManagement` ở bất kỳ context nào cũng ảnh hưởng mọi bean.**  
Sai. Transaction annotation processing gắn với Spring application context đã cấu hình; phải xác nhận bean được proxy ở đúng context.

**Ngộ nhận 7 — Chế độ ALL_EXCEPTIONS thay `@Transactional(propagation=...)`.**  
Sai. Nó chỉ đổi rollback rule mặc định; propagation vẫn được áp dụng riêng.

**Ngộ nhận 8 — Mọi `DataAccessException` mới rollback nhờ ALL_EXCEPTIONS.**  
Sai. `DataAccessException` là runtime exception, đã được rollback trong trường hợp thông thường ngay từ default cũ.

**Ngộ nhận 9 — Commit ném exception thì database chắc chắn đã rollback.**  
Sai. Một số lỗi commit khiến trạng thái chưa rõ; cần đối soát, business key và cơ chế idempotency.

**Ngộ nhận 10 — XML transaction advice và TransactionTemplate đều tự nhận global switch.**  
Không nên suy ra như vậy. Tùy chọn được tài liệu hóa cho hạ tầng rule-based **annotation transaction** trong Spring; cấu hình XML/programmatic có đường đi và contract riêng.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng nâng từ Spring 6.1 sang 6.2 nhưng không thay config. Method `@Transactional` ném `IOException`. Điều gì thay đổi?  
**Đáp án:** Không có thay đổi mặc định chỉ vì nâng version: vẫn theo `RUNTIME_EXCEPTIONS`, trừ khi có rollback rule hoặc trạng thái transaction khác.

**Câu 2.** Bật `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)` rồi một method có `noRollbackFor = IOException.class` ném `IOException`. Theo rollback rule Spring chọn gì?  
**Đáp án:** Chọn commit cho method đó vì rule cục bộ cụ thể thắng default. Kết quả thực vẫn phụ thuộc trạng thái/khả năng commit.

**Câu 3.** Cùng method chỉ khai báo `noRollbackFor = BusinessNotice.class` nhưng ném `IOException`. Kết quả dưới ALL_EXCEPTIONS?  
**Đáp án:** `IOException` không khớp rule cục bộ; fallback chọn rollback.

**Câu 4.** `@Transactional` bị gọi qua `this.method()` trong một bean không có outer transaction. Bật ALL_EXCEPTIONS có giúp advice được chạy không?  
**Đáp án:** Không. Cần lời gọi qua proxy hoặc cơ chế transaction khác; global rule không khắc phục self-invocation.

**Câu 5.** Vì sao `assertThrows(IOException.class, ...)` là chưa đủ chứng minh rollback?  
**Đáp án:** Caller có thể nhận IOException **sau khi Spring commit** (ở default truyền thống). Phải truy vấn dữ liệu sau khi transaction boundary kết thúc.

**Câu 6.** Bật ALL_EXCEPTIONS có tự đổi behavior của `TransactionTemplate` hoặc một JTA container không dùng Spring interceptor không?  
**Đáp án:** Không nên suy ra. Đây là cấu hình default rollback rule cho annotation transaction infrastructure trong context; hệ programmatic/ngoài Spring có contract riêng.

**Câu 7.** Khi migration một service dùng checked `BusinessNotice` để báo “đã lưu và đang chờ kiểm duyệt”, nên kiểm tra gì?  
**Đáp án:** Xác nhận invariant rằng bản ghi phải được giữ. Cân nhắc trả về trạng thái nghiệp vụ bình thường hoặc đặt `noRollbackFor = BusinessNotice.class` có kiểm thử, rồi đo dữ liệu sau boundary.

**Câu 8.** Vì sao nên thử inner `REQUIRED` khi đổi global default?  
**Đáp án:** Checked exception mà inner từng không đánh dấu rollback-only nay có thể làm shared physical transaction rollback-only, khiến outer dù catch vẫn không commit.

## 12. Tài liệu chính thức

- [Spring Framework 6.2 — Using @Transactional: global rollback defaults](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — EnableTransactionManagement Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html)
- [Spring Framework 6.2 — RollbackOn enum Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/RollbackOn.html)
- [Spring Framework 6.2 — AnnotationTransactionAttributeSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/AnnotationTransactionAttributeSource.html)
- [Spring Framework 6.2 — RollbackRuleAttribute Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/RollbackRuleAttribute.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Embedded Database Support](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/embedded-database-support.html)
