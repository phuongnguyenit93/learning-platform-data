# Mặc định rollback với RuntimeException và Error trong Spring Framework

## 1. Mục tiêu học tập

**Quy tắc rollback mặc định** của giao dịch declarative trong Spring rất cụ thể: khi một `RuntimeException` hoặc một `Error` đi ra khỏi lời gọi đang được transaction advice quản lý, Spring yêu cầu rollback. Một **checked exception** thông thường, chẳng hạn `IOException`, không tự làm transaction rollback theo mặc định.

Điều này dễ gây bất ngờ. Nếu service đã lưu dữ liệu rồi ném `IOException`, caller vẫn nhận lỗi nhưng dữ liệu **có thể đã commit**. Ngược lại, `IllegalStateException` hoặc `AssertionError` đi qua transaction interceptor thường làm các thay đổi thuộc cùng transaction bị hủy.

Sau bài học, bạn có thể:

- Phân biệt `RuntimeException`, `Error` và checked `Exception` trong Java.
- Hiểu cách Spring xác định **commit hay rollback**, và điều kiện để một exception thật sự được interceptor nhìn thấy.
- Giải thích kết quả của exception bị bắt trong method so với exception được caller bắt ở **bên ngoài proxy**.
- Kiểm chứng với ví dụ Java 17+, Spring Boot, Spring JDBC, H2: các ca `RuntimeException`, `Error`, checked exception, `rollbackFor` và `noRollbackFor`.
- Nhận diện tác động của transaction `REQUIRED` lồng nhau, self-invocation, ngoại lệ sau commit và tài nguyên nằm ngoài transaction.

Bài nằm trong chủ đề **Quy tắc rollback** của module Spring Framework — transaction-management. Nội dung trước hết nói về Spring declarative transaction chạy qua proxy với một CSDL. Các cơ chế transaction khác có thể có chi tiết riêng.

## 2. Cây Throwable: compiler và transaction rule là hai khái niệm riêng

Sơ đồ quan hệ kiểu Java rút gọn:

```text
java.lang.Throwable
├── java.lang.Error
│   ├── AssertionError
│   ├── LinkageError
│   └── OutOfMemoryError
└── java.lang.Exception
    ├── java.lang.RuntimeException
    │   ├── IllegalArgumentException
    │   ├── IllegalStateException
    │   └── NullPointerException
    └── checked exceptions (ví dụ)
        ├── IOException
        ├── SQLException
        └── ReflectiveOperationException
```

Về kiểm tra của Java compiler, `RuntimeException` và `Error` là các nhóm **unchecked**: mã gọi không bắt buộc khai báo `throws` hoặc `catch`. Hầu hết các subclass của `Exception` không phải `RuntimeException` là **checked**, buộc caller xử lý hoặc khai báo.

Về Spring, theo chính sách transaction mặc định:

| Throwable thoát qua interceptor | Phân loại | Có yêu cầu rollback mặc định? |
| --- | --- | --- |
| `IllegalArgumentException` | `RuntimeException` | Có |
| `IllegalStateException` | `RuntimeException` | Có |
| `NullPointerException` | `RuntimeException` | Có |
| Spring `DataAccessException` | `RuntimeException` | Có |
| `AssertionError` | `Error` | Có |
| `OutOfMemoryError` | `Error` | Spring cố rollback theo rule; không bảo đảm JVM còn đủ tài nguyên |
| `IOException` | Checked `Exception` | Không |
| `SQLException` ném trực tiếp | Checked `Exception` | Không |
| Method return bình thường sau khi catch lỗi | Không có Throwable đi ra | Thường cố commit, trừ khi transaction đã rollback-only hoặc có lỗi khác |

**`Error` không kế thừa `Exception`.** Vì vậy `catch (Exception ex)` không bắt được `AssertionError`, nhưng Spring rollback rule mặc định vẫn bao gồm `Error`. Đây là hành vi của transaction infrastructure, không phụ thuộc vào việc client có dùng `catch (Exception)` hay không.

Một điểm thực tế: JDBC API có `SQLException` checked, nhưng `JdbcTemplate` trong Spring thường chuyển lỗi truy cập DB thành các subclass của `DataAccessException`, vốn là unchecked `RuntimeException`. Hãy xét **kiểu Throwable thực tế thoát khỏi service** thay vì đoán theo kiểu của API thấp hơn.

## 3. Spring quyết định rollback khi nào?

`@Transactional` chỉ mô tả metadata. Với transaction imperative thông qua Spring AOP proxy, luồng thông thường:

```text
Caller
  |
  v
Spring AOP proxy của service
  |
  v
TransactionInterceptor
  |-- xác định transaction attributes
  |-- PlatformTransactionManager mở hoặc tham gia transaction
  |
  v
Phần thân service -> repository/JdbcTemplate -> DB
  |
  +-- return bình thường ---------------> commit nếu có thể
  |
  +-- RuntimeException/Error -----------> rollback theo mặc định
  |
  +-- checked Exception ----------------> commit theo mặc định
                                         (nếu không có rule rollback thêm)
  |
  v
Interceptor hoàn tất transaction
  |
  v
Caller nhận return/exception
```

Dạng mô phỏng quy tắc lõi của `DefaultTransactionAttribute.rollbackOn(Throwable)`:

```java
boolean rollbackOn(Throwable throwable) {
    return throwable instanceof RuntimeException
        || throwable instanceof Error;
}
```

Đây là **pseudocode Java mô tả quy tắc**, không phải toàn bộ source của Spring hay một class chạy độc lập. Nó trả lời “exception loại này có đánh dấu rollback không?”, còn transaction manager mới chịu trách nhiệm quản lý connection, commit hoặc rollback tài nguyên thực.

Với một method tự mở transaction:

1. Spring bắt đầu transaction trước khi chạy phần thân method.
2. Method cập nhật DB qua tài nguyên tham gia đúng transaction.
3. Nếu method ném `RuntimeException` hoặc `Error` ra khỏi proxy, interceptor chọn rollback.
4. Nếu method ném checked exception không thuộc rollback rule, interceptor có thể **commit trước**, sau đó vẫn ném lại exception cho caller.
5. Nếu method hoàn thành bình thường, interceptor cố commit, trừ khi trạng thái đã rollback-only hoặc xuất hiện lỗi khác.

Cần phân biệt “Spring **yêu cầu** rollback” với “đã **hoàn tất** rollback trên CSDL”. Trường hợp mất connection, transaction manager khác nhau hoặc lỗi hạ tầng nặng có thể cần kiểm chứng kết quả DB riêng.

## 4. Các tình huống thiết yếu

### 4.1. RuntimeException thường làm rollback

```java
@Transactional
public void reserve() {
    inventory.decrease();
    orderRepository.save();
    throw new IllegalStateException("cannot finish");
}
```

Đoạn này minh họa, thiếu định nghĩa `inventory` và `orderRepository`. Nếu cả hai thay đổi tham gia cùng transaction Spring và exception runtime thoát ra qua proxy, rollback sẽ hủy cả hai. Đây là lý do default rule phù hợp với nhiều lỗi lập trình hoặc trạng thái không thể tiếp tục.

Spring không tự phân biệt “lỗi nghiệp vụ nhẹ” và “lỗi hệ thống nặng” từ message của exception. Nếu exception là `RuntimeException`, default rule rollback, trừ khi được cấu hình ngược lại bằng chính sách phù hợp.

### 4.2. Error cũng làm rollback theo default

```java
@Transactional
public void writeAndFailForDemo() {
    repository.save();
    throw new AssertionError("simulated error");
}
```

Đây là minh họa, thiếu repository. Khi `AssertionError` thoát qua transaction interceptor, Spring yêu cầu rollback. Chúng ta có thể sử dụng `AssertionError` chủ động trong bài test để chứng minh nhánh này. **Không sử dụng `OutOfMemoryError`, `StackOverflowError` hay `LinkageError` làm công cụ điều khiển nghiệp vụ**, bởi process hoặc JVM có thể đã không còn khả năng phục hồi. Không nên bắt tổng quát mọi `Error` rồi tiếp tục ứng dụng như thể đó là lỗi business bình thường.

### 4.3. Checked exception thường không làm rollback mặc định

```java
@Transactional
public void importFile() throws IOException {
    repository.save();
    throw new IOException("read next line failed");
}
```

Đây là minh họa. Theo default, `IOException` là checked exception. Spring có thể commit record do `save()` ghi rồi ném lại `IOException`; caller thấy lỗi **không có nghĩa** dữ liệu đã rollback. Nếu quy tắc nghiệp vụ yêu cầu toàn bộ import thành công hoặc hủy, cần cấu hình `rollbackFor = IOException.class` hoặc xử lý ranh giới/cơ chế lỗi thích hợp.

### 4.4. Catch bên trong method thay đổi điều interceptor nhìn thấy

```java
@Transactional
public void saveAndHandle() {
    repository.save();
    try {
        throw new IllegalStateException("temporary failure");
    } catch (IllegalStateException ex) {
        log.info("Handled failure");
    }
}
```

Mã minh họa thiếu repository/logger. Method return bình thường và Spring **không còn thấy** `IllegalStateException` thoát ra. Nếu transaction chưa bị đánh dấu rollback-only và DB vẫn hợp lệ, nó có thể commit.

Ngược lại, nếu caller bắt `IllegalStateException` **ở bên ngoài method `@Transactional`**:

```java
try {
    orderService.saveThenFail();
} catch (IllegalStateException ex) {
    // Transaction interceptor đã thấy exception trước caller.
}
```

thì việc caller bắt exception không đảo ngược quyết định rollback Spring vừa thực hiện.

## 5. Ví dụ chạy được với Java 17+, Spring Boot, JDBC và H2

Mục tiêu là **đọc lại dữ liệu sau khi method kết thúc**, thay vì chỉ kiểm tra exception có xuất hiện hay không. Chương trình dùng Spring Boot 3.3.13, Spring JDBC và H2 in-memory, không có web server. Version được cố định phục vụ tái hiện API, không phải lời khuyên dùng bản cũ cho môi trường production.

Bảy ca thử:

1. Không lỗi: commit.
2. `IllegalStateException`: rollback mặc định.
3. `AssertionError`: rollback mặc định.
4. `IOException`: commit theo mặc định.
5. RuntimeException bị catch ngay trong service: commit nếu không rollback-only.
6. Checked exception có `rollbackFor`: rollback.
7. RuntimeException có `noRollbackFor`: commit dù có exception.

### 5.1. Tệp và dependency

```text
spring-rollback-default-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lesson/rollback/
    │   ├── RollbackApplication.java
    │   └── RollbackService.java
    └── resources/
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-rollback-default-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'lesson'
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

Spring Boot tự cấu hình `DataSource`, `JdbcTemplate` và transaction infrastructure phù hợp với embedded H2 khi dependencies/configuration thỏa điều kiện. `@Transactional` nằm trên service do Spring quản lý; `CommandLineRunner` gọi service qua proxy từ bên ngoài.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE demo_event (
    id INT PRIMARY KEY
);
```

Spring Boot tự chạy `schema.sql` khi khởi động trên H2 embedded. Các ca dùng id khác nhau, nên có thể đếm độc lập.

### 5.2. Service thực thi bảy loại kết quả

**`src/main/java/lesson/rollback/RollbackService.java`**

```java
package lesson.rollback;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RollbackService {
    private final JdbcTemplate jdbc;

    public RollbackService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void normal() {
        insert(1);
    }

    @Transactional
    public void runtimeFailure() {
        insert(2);
        throw new IllegalStateException("runtime-failure");
    }

    @Transactional
    public void errorFailure() {
        insert(3);
        throw new AssertionError("error-failure");
    }

    @Transactional
    public void checkedFailure() throws IOException {
        insert(4);
        throw new IOException("checked-failure");
    }

    @Transactional
    public void caughtRuntime() {
        insert(5);
        try {
            throw new IllegalStateException("caught-failure");
        } catch (IllegalStateException ignored) {
            // Minh họa: không rethrow, không mark rollback-only.
        }
    }

    @Transactional(rollbackFor = IOException.class)
    public void configuredCheckedFailure() throws IOException {
        insert(6);
        throw new IOException("checked-failure");
    }

    @Transactional(noRollbackFor = IllegalStateException.class)
    public void configuredNoRollback() {
        insert(7);
        throw new IllegalStateException("runtime-failure");
    }

    private void insert(int id) {
        jdbc.update("INSERT INTO demo_event(id) VALUES (?)", id);
    }
}
```

Mọi method `@Transactional` ở trên đều public, không phải final, và nằm trên một Spring bean. `insert` là private helper; nó dùng `JdbcTemplate` trong **transaction đã được method public mở**. Helper không cần annotation riêng.

Các exception được ném **sau câu INSERT**, vì thế nếu record biến mất, đó là bằng chứng rollback của phần ghi, không phải vì chương trình chưa ghi gì.

### 5.3. Caller chạy thử và quan sát DB

**`src/main/java/lesson/rollback/RollbackApplication.java`**

```java
package lesson.rollback;

import java.io.IOException;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RollbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackApplication.class, args);
    }

    @Bean
    CommandLineRunner examples(RollbackService service, JdbcTemplate jdbc) {
        return args -> {
            service.normal();
            System.out.println("normal=" + count(jdbc, 1));

            try {
                service.runtimeFailure();
            } catch (IllegalStateException ignored) {
                // Caller bắt lỗi sau khi interceptor rollback.
            }
            System.out.println("runtime=" + count(jdbc, 2));

            try {
                service.errorFailure();
            } catch (AssertionError ignored) {
                // AssertionError tự tạo dành riêng cho demo.
            }
            System.out.println("error=" + count(jdbc, 3));

            try {
                service.checkedFailure();
            } catch (IOException ignored) {
                // Checked exception không kích hoạt rollback mặc định.
            }
            System.out.println("checked=" + count(jdbc, 4));

            service.caughtRuntime();
            System.out.println("caught=" + count(jdbc, 5));

            try {
                service.configuredCheckedFailure();
            } catch (IOException ignored) {
                // rollbackFor đã yêu cầu rollback.
            }
            System.out.println("checkedRollbackFor=" + count(jdbc, 6));

            try {
                service.configuredNoRollback();
            } catch (IllegalStateException ignored) {
                // noRollbackFor đã thay đổi rule cho ngoại lệ này.
            }
            System.out.println("noRollbackRuntime=" + count(jdbc, 7));
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM demo_event WHERE id = ?",
            Integer.class, id
        );
        return value;
    }
}
```

Ứng dụng Spring Boot quét `RollbackService` trong package con phù hợp vì nó cùng package `lesson.rollback` với application. `examples` nhận service qua dependency injection, nên lời gọi `service.runtimeFailure()` đi qua proxy. Runner không được đánh dấu `@Transactional`, do đó các truy vấn `count` được thực hiện **sau khi transaction của từng lời gọi service đã kết thúc**.

Trong sản phẩm thật, không nên catch tổng quát `Error` hay cố tiếp tục chạy sau lỗi JVM nghiêm trọng. Ở đây ta chỉ bắt **một `AssertionError` do demo tự tạo**, để minh họa rollback và cho chương trình tiếp tục chạy các ca sau.

### 5.4. Chạy và dự đoán stdout

Yêu cầu JDK 17+ và Gradle 8.x. Chạy tại thư mục `spring-rollback-default-demo`:

```bash
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Vì code phụ thuộc Spring và H2, không thể dùng `javac` thuần chỉ với JDK classpath để biên dịch các file này.

Bỏ qua log Spring Boot và Gradle. Bảy dòng `System.out.println` của chương trình là:

```text
normal=1
runtime=0
error=0
checked=1
caught=1
checkedRollbackFor=0
noRollbackRuntime=1
```

| Method | Lỗi thoát qua interceptor | Rollback rule | Số dòng còn lại |
| --- | --- | --- | --- |
| `normal` | Không | Commit | 1 |
| `runtimeFailure` | `IllegalStateException` | Default: rollback RuntimeException | 0 |
| `errorFailure` | `AssertionError` | Default: rollback Error | 0 |
| `checkedFailure` | `IOException` | Default: không rollback checked exception | 1 |
| `caughtRuntime` | Không, method return bình thường | Commit nếu chưa rollback-only | 1 |
| `configuredCheckedFailure` | `IOException` | `rollbackFor = IOException.class` | 0 |
| `configuredNoRollback` | `IllegalStateException` | `noRollbackFor` | 1 |

**Chốt quan sát:** cùng là caller bắt được exception, nhưng dữ liệu có thể được commit hoặc rollback tùy loại throwable và rollback rule áp dụng. Thêm `try/catch` ở caller sau khi method kết thúc **không** làm thay đổi kết quả mà transaction interceptor đã quyết định.

### 5.5. Bài tập thay đổi từng dòng

- Bỏ `rollbackFor` khỏi `configuredCheckedFailure` và khởi chạy lại với DB mới: dòng `checkedRollbackFor` sẽ thành 1.
- Bỏ `noRollbackFor` khỏi `configuredNoRollback`: dòng `noRollbackRuntime` sẽ thành 0.
- Đổi `checkedFailure` thành `@Transactional(rollbackFor = IOException.class)`: dòng `checked` thành 0.
- Đổi `caughtRuntime` để rethrow exception rồi thêm catch bên ngoài runner: dòng `caught` thành 0.
- Di chuyển catch `IllegalStateException` từ service ra caller: transaction interceptor được thấy exception nên rollback theo default.

Chỉ thay đổi trong dự án demo; khi chạy lại, dùng H2 in-memory sạch. Không suy luận từ số bản ghi cũ của lần chạy trước.

## 6. rollbackFor, noRollbackFor và thứ tự ưu tiên

`@Transactional` cho phép khai báo exception-specific policy:

```java
@Transactional(rollbackFor = IOException.class)
public void importRecord() throws IOException {
    persist();
    throw new IOException("cannot finish");
}
```

Với `rollbackFor = IOException.class`, `IOException` cùng subclass của nó sẽ match rule. Ngược lại:

```java
@Transactional(noRollbackFor = IllegalStateException.class)
public void auditAttempt() {
    persistAudit();
    throw new IllegalStateException("already processed");
}
```

Ở đoạn thứ hai, Spring có thể commit `persistAudit()` rồi ném exception. Hai đoạn chỉ là minh họa thiếu `persist`/`persistAudit`, không tự biên dịch độc lập.

**Nguyên tắc: rule cụ thể hơn thắng.** Nếu một transaction attribute có nhiều rule, Spring tìm rule khớp với class throwable gần nhất trong hierarchy; ví dụ `rollbackFor = Exception.class` và `noRollbackFor = DuplicateRequestException.class` thường làm `DuplicateRequestException` không rollback vì rule cụ thể hơn. `RollbackRuleAttribute` chọn theo class hierarchy giúp tránh phụ thuộc vào nội dung message. Nên ưu tiên class-based rule thay vì tên chuỗi chứa một phần tên class có thể vô tình match ngoài ý muốn.

Khi dùng XML, cũng có các thuộc tính `rollback-for` và `no-rollback-for` trong `<tx:method>`:

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="import*" rollback-for="java.io.IOException"/>
        <tx:method name="*" />
    </tx:attributes>
</tx:advice>
```

Mảnh XML này chỉ định rule, nhưng cần AOP pointcut/advisor, manager và Spring context phù hợp để thực thi. Không nên thêm cả transaction advisor XML lẫn annotation advisor với policy khác nhau trên cùng method nếu chưa kiểm soát việc chồng advice.

## 7. Ranh giới của default rule: proxy, propagation và tài nguyên

### 7.1. Annotation được tìm thấy chưa bảo đảm advice đã chạy

Trong proxy mode thông thường của Spring AOP, lời gọi nội bộ qua `this.method()` bypass proxy:

```java
@Service
class OrderService {
    public void process() {
        this.persistAndFail();
    }

    @Transactional
    public void persistAndFail() {
        save();
        throw new IllegalStateException("failure");
    }
}
```

Mã chỉ minh họa, thiếu `save()`. Nếu `process()` không có transaction và được gọi từ bên ngoài, `this.persistAndFail()` **không đi qua transaction interceptor riêng**; exception runtime không tự làm Spring rollback thao tác đã auto-commit. Trường hợp tương tự xảy ra khi tạo object bằng `new` thay vì lấy Spring bean.

Nhưng nếu `process()` đã chạy trong một transaction do scope bên ngoài mở, `persistAndFail()` vẫn **tham gia transaction đã tồn tại** ngay cả khi self-invocation không được advice intercept riêng. Do đó câu đúng là “inner annotation không được áp dụng”, không phải “self-invocation luôn không có transaction”.

### 7.2. REQUIRED lồng nhau có thể tạo rollback-only

Nếu service A có transaction `REQUIRED`, gọi service B khác cũng có `REQUIRED` qua proxy, hai scope có thể chia sẻ cùng một transaction vật lý:

```text
Outer @Transactional(REQUIRED) -- mở transaction T
   |
   +-- Inner @Transactional(REQUIRED) -- tham gia T
             |
             +-- ném IllegalStateException
                  -> Inner interceptor đánh dấu T rollback-only
   |
   +-- Outer catch và tiếp tục
   |
   +-- Outer cố commit T
        -> rollback T; có thể báo UnexpectedRollbackException
```

Một inner exception có thể đã **đánh dấu toàn bộ transaction chung** rollback-only trước khi outer bắt exception. Catch phía outer không tự xóa trạng thái này. Ngược lại, `REQUIRES_NEW` mở transaction vật lý riêng: nếu nó đã commit thì outer rollback về sau không undo transaction inner. Cần xét business invariant và propagation, không đoán mỗi method có một commit độc lập.

### 7.3. Không có rollback cho tác dụng phụ ngoài transaction

Nếu service vừa ghi DB vừa gửi email, publish Kafka, gọi REST API hoặc ghi file, local transaction manager không tự điều khiển các tác dụng phụ ngoài DB. Spring rollback sau RuntimeException chỉ hủy thay đổi **thuộc tài nguyên transaction được quản lý**. Với hệ thống phát sự kiện, có thể dùng transactional outbox và idempotent consumer khi cần phối hợp đáng tin.

### 7.4. Exception xảy ra sau commit không undo commit

Một method transaction có thể commit xong, rồi callback `afterCommit` hoặc bước gửi HTTP response phát sinh RuntimeException. Caller nhận lỗi **sau khi** dữ liệu đã commit. Khi lỗi phát sinh ngay tại lệnh commit và ACK bị mất, kết quả còn có thể **chưa xác định**; không dùng loại exception đơn độc để kết luận rollback. Khi đó cần tra cứu operation ID, idempotency và đối soát.

## 8. Catch exception bên trong transaction: khi nào vẫn rollback?

Không nên nói rằng “catch rồi return chắc chắn commit” trong mọi trường hợp. Các ngoại lệ:

- Một scope `REQUIRED` bên trong đã đánh dấu rollback-only; scope ngoài cố commit có thể gặp `UnexpectedRollbackException`.
- Lỗi SQL có thể khiến transaction DB chuyển sang trạng thái aborted; dù code bắt exception, commit có thể không thành công.
- Application có thể chủ động gọi `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`.
- Có thể có constraint violation ở flush hoặc lỗi khác tại commit, ngoài exception business mà code vừa catch.

Nếu cần trả kết quả nghiệp vụ nhưng **vẫn phải rollback**, có thể đánh dấu rollback-only có chủ ý, hoặc tốt hơn thiết kế exception và xử lý tại service boundary:

```java
@Transactional
public BusinessResult apply() {
    try {
        persistChanges();
        return BusinessResult.success();
    } catch (BusinessFailure ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return BusinessResult.failure(ex.getMessage());
    }
}
```

Đây là mã kiến trúc minh họa, thiếu định nghĩa `BusinessResult`, `BusinessFailure` và `persistChanges`. Cách đánh dấu rollback-only buộc business service phụ thuộc trực tiếp vào transaction API của Spring; chỉ dùng khi hợp đồng trả kết quả cần thiết.

## 9. Error là lỗi hệ thống: đừng coi rollback là phục hồi an toàn

`Error` được default rollback vì khi một thao tác bị gián đoạn nghiêm trọng, commit một phần dữ liệu là lựa chọn rủi ro. Nhưng lỗi `OutOfMemoryError`, `StackOverflowError` và một số `LinkageError` có thể báo JVM không còn hoạt động bình thường. Trong tình huống này:

- Spring chỉ có thể **cố** gọi rollback nếu transaction interceptor còn khả năng chạy.
- Một database transaction chưa commit có thể được DB phục hồi/rollback khi connection bị đóng, nhưng hành vi cụ thể phụ thuộc driver và DB.
- Không bắt `Throwable` ở tầng business rồi trả HTTP 200 như thể mọi lỗi đã được xử lý.
- Vận hành cần giám sát, phục hồi process và kiểm tra trạng thái transaction/DB; không dùng `AssertionError` trong production để báo lỗi nghiệp vụ thông thường.

Trong bài demo, `AssertionError` được tạo có chủ đích, không khiến JVM rơi vào tình trạng thiếu tài nguyên nên có thể bắt ở runner để minh họa chính sách Spring.

## 10. Kiểm thử đúng kết quả, tránh false positive

Một test có ý nghĩa nên xác minh **trạng thái DB sau lời gọi**, không chỉ kiểm tra `assertThrows`:

1. Tạo dữ liệu độc lập, gọi service được Spring quản lý qua proxy.
2. Thực hiện ít nhất một câu INSERT/UPDATE, sau đó ném exception thích hợp.
3. Bắt exception từ bên ngoài lời gọi service rồi đọc lại DB.
4. Với RuntimeException hoặc Error trong một local transaction bình thường, assert thay đổi đã rollback.
5. Với checked exception không cấu hình rollback, assert kết quả commit nếu đó là kịch bản kiểm chứng.
6. Thêm test cho `rollbackFor`, `noRollbackFor`, exception bị catch trong service, scope `REQUIRED` bên trong và side effect ngoài DB.
7. Với JPA, kiểm tra `flush`, persistence context, constraint và transaction scope thực, vì SQL có thể được đẩy tới DB muộn.

**Cạm bẫy Spring TestContext:** test method có `@Transactional` thường được framework rollback cuối test. Service `REQUIRED` sẽ tham gia transaction của test; một test “không thấy row cuối cùng” chưa chứng minh service đã rollback đúng policy. Khi kiểm tra commit/rollback, dùng test không transactional hoặc điều khiển test transaction rồi đọc DB ngoài scope.

Có thể bật tạm log cho transaction interceptor và JDBC manager:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Log giúp biết method nào thực sự được intercept, manager có mở transaction không, và đang commit hay rollback. Dù vậy, bằng chứng mạnh nhất vẫn là readback trạng thái dữ liệu sau khi transaction kết thúc.

## 11. Checklist khi RuntimeException mà dữ liệu vẫn được lưu

| Cần kiểm tra | Điều có thể đã xảy ra |
| --- | --- |
| Bean có phải Spring-managed không? | `new` làm annotation không được advice xử lý |
| Lời gọi có đi qua proxy không? | Self-invocation bỏ qua advice cho inner method |
| Exception có thoát khỏi method được intercept không? | Catch bên trong khiến interceptor thấy return bình thường |
| Có `noRollbackFor` hoặc rule toàn cục đặc biệt không? | Policy tường minh ghi đè default |
| Transaction đã rollback-only từ scope khác chưa? | Kết quả có thể chỉ được quyết định ở outer commit |
| Có transaction `REQUIRES_NEW` đã commit không? | Outer rollback không hủy inner commit |
| Mọi thao tác dùng cùng transaction manager/tài nguyên không? | Connection/DB khác không tham gia rollback |
| Exception xảy ra trước hay sau commit? | Lỗi sau commit không undo dữ liệu đã bền vững |
| Có transaction test tự rollback không? | Test có thể cho kết luận sai |
| DB đã xác nhận kết quả chưa? | Lỗi commit mất ACK có thể dẫn đến outcome chưa xác định |

Đừng chữa một lỗi mất transaction bằng cách thêm `rollbackFor = Exception.class` lên mọi method. Nếu proxy không chạy hoặc dữ liệu nằm ngoài tài nguyên transaction, rule ấy vẫn chỉ là metadata không có tác dụng.

## 12. Tự kiểm tra

**Câu 1.** `@Transactional` method INSERT hai dòng rồi ném `IllegalArgumentException` thoát ra ngoài proxy. Mặc định ra sao?

**Trả lời:** Đây là `RuntimeException`; Spring yêu cầu rollback. Nếu cả hai INSERT thuộc cùng transaction và rollback thành công, cả hai đều không được commit.

**Câu 2.** `AssertionError` có làm rollback mặc định dù không kế thừa `Exception`?

**Trả lời:** Có. Default rule bao gồm `Error`. Không vì vậy mà coi mọi Error nghiêm trọng là có thể phục hồi an toàn ở JVM.

**Câu 3.** `@Transactional` method INSERT rồi ném checked `IOException`, caller bắt lỗi. DB có nhất định trống không?

**Trả lời:** Không. Checked exception mặc định không kích hoạt rollback, nên nếu commit thành công thì bản ghi vẫn tồn tại. Cần `rollbackFor = IOException.class` nếu nghiệp vụ đòi hỏi hủy.

**Câu 4.** RuntimeException phát sinh trong method nhưng bị catch rồi return, có mặc định rollback?

**Trả lời:** Thường không, vì interceptor không thấy exception thoát ra; nhưng transaction vẫn có thể rollback nếu bị đánh dấu rollback-only hoặc gặp lỗi tài nguyên.

**Câu 5.** Vì sao test có `@Transactional` bên ngoài đôi khi gây hiểu nhầm?

**Trả lời:** Vì transaction của test có thể tự rollback cuối test. Service `REQUIRED` có thể chỉ tham gia transaction ấy, không chứng minh được commit/rollback độc lập như runtime thật.

**Câu 6.** Caller nhận RuntimeException từ bước sau commit. Có chắc DB đã rollback?

**Trả lời:** Không. Commit đã hoàn tất không thể bị exception sau đó đảo ngược. Cần tra trạng thái dữ liệu thật và idempotency khi kết quả có thể mơ hồ.

**Câu 7.** `@Transactional(noRollbackFor = IllegalStateException.class)` trên method khác có phá quy tắc mặc định không?

**Trả lời:** Đây là một override có chủ đích; Spring có thể commit mặc dù exception loại này thoát ra, miễn transaction còn commit được.

## 13. Tài liệu tham khảo

- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.1 — `Transactional` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Boot 3.3 — System Requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html

**Điểm cần nhớ:** trong cấu hình Spring declarative transaction mặc định, `RuntimeException` và `Error` đi qua transaction interceptor **kích hoạt rollback**, còn checked exception thường **không**. Kết luận chính xác đòi hỏi biết lời gọi có đi qua proxy, transaction nào đang được quản lý và dữ liệu đã commit hay chưa; hãy xác minh kết quả trên DB thay vì chỉ nhìn exception.