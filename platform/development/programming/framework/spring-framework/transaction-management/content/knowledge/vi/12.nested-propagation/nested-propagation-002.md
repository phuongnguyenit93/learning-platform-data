# Rollback phạm vi con về savepoint với Spring PROPAGATION_NESTED

## 1. Bản chất vấn đề: hủy một phần mà vẫn giữ giao dịch ngoài

Trong một nghiệp vụ lớn, có lúc một bước **có thể thất bại nhưng không nên buộc cả nghiệp vụ hủy bỏ**. Ví dụ: tạo phiếu nhập kho và ghi dòng nhật ký chính là bắt buộc, còn bước áp dụng một ưu đãi tùy chọn có thể lỗi; ứng dụng muốn hủy những thay đổi SQL của bước ưu đãi và tiếp tục lưu phiếu nhập.

Với Spring transaction management, `Propagation.NESTED` có thể đáp ứng bài toán này bằng **JDBC savepoint**: một dấu mốc nằm bên trong **cùng giao dịch vật lý**. Nếu phạm vi con thất bại và có quy tắc rollback phù hợp, Spring rollback phần công việc từ savepoint đó, trong khi phần giao dịch ngoài trước savepoint vẫn tồn tại và có thể tiếp tục.

Hãy nhớ bốn ý cốt lõi:

1. **NESTED không mở một transaction vật lý độc lập** khi đã có transaction ngoài phù hợp. Nó dùng một transaction vật lý và một (hoặc nhiều) savepoint.
2. **Rollback của phạm vi con** thông thường là `ROLLBACK TO SAVEPOINT`, không phải `ROLLBACK` toàn bộ transaction.
3. **Commit của phạm vi con** không tự làm dữ liệu bền vững: kết quả con chỉ trở thành kết quả cuối cùng nếu transaction ngoài thực sự commit.
4. **Transaction ngoài vẫn có quyền hủy toàn bộ**. Nếu ngoài rollback sau khi con đã chạy thành công, cả thay đổi trước và trong phạm vi con đều bị hủy.

Mục tiêu sau bài:

- Giải thích trình tự tạo savepoint, thực thi SQL, rollback về savepoint, tiếp tục và commit.
- Viết đúng hai Spring-managed service để `@Transactional(propagation = Propagation.NESTED)` được kích hoạt qua proxy.
- Quan sát được việc **hàng trước savepoint vẫn giữ**, **hàng sau savepoint bị loại**, và **giao dịch ngoài vẫn commit được**.
- Phân biệt với `REQUIRED` (dễ dẫn tới rollback-only toàn cục khi phần con thất bại) và `REQUIRES_NEW` (transaction vật lý độc lập).
- Nắm giới hạn hỗ trợ JDBC/JPA, exception rules, cách bắt lỗi và những side effect mà savepoint không thể phục hồi.

> Bài này tập trung vào *rollback phạm vi con về savepoint*, không xem savepoint như công cụ thay thế logic nhất quán dữ liệu, thiết kế exception hay transaction boundary.

## 2. Một transaction vật lý, nhiều mốc rollback

Hình dung trình tự:

```text
Bắt đầu transaction vật lý T
|
+-- Outer: INSERT A                (đang chờ commit)
|
+-- Tạo SAVEPOINT S1
|      |
|      +-- Inner: INSERT B         (đang chờ commit)
|      +-- Inner: phát sinh lỗi
|      +-- ROLLBACK TO SAVEPOINT S1
|             -> loại tác động SQL của B từ sau mốc S1
|
+-- Outer bắt lỗi có chủ đích
+-- Outer: INSERT C
|
+-- COMMIT T
       -> A và C tồn tại; B không tồn tại
```

**Savepoint không phải một commit nhỏ.** Khi tạo savepoint, database không xác nhận vĩnh viễn phần trước mốc; A vẫn thuộc transaction T và có thể bị rollback nếu T thất bại. `ROLLBACK TO SAVEPOINT S1` chỉ đưa trạng thái transaction về thời điểm S1, không đóng T.

Tương tự, nếu inner thành công và Spring giải phóng savepoint, INSERT B vẫn chưa commit riêng. Một lỗi tại outer trước `COMMIT T` có thể khiến A, B và mọi câu SQL khác trong T cùng rollback.

### Phân biệt các lệnh SQL

Ví dụ cú pháp **PostgreSQL** (bảng `events(id, message)` đã tồn tại và chưa có các ID bên dưới):

```sql
BEGIN;

INSERT INTO events(id, message) VALUES (1, 'outer-before');

SAVEPOINT optional_step;
INSERT INTO events(id, message) VALUES (2, 'inner-to-undo');

ROLLBACK TO SAVEPOINT optional_step;
RELEASE SAVEPOINT optional_step;

INSERT INTO events(id, message) VALUES (3, 'outer-after');

COMMIT;
```

Sau khi commit, truy vấn:

```sql
SELECT id, message FROM events ORDER BY id;
```

cho các hàng có ID **1 và 3**, không có ID 2.

| SQL | Tác dụng |
| --- | --- |
| `BEGIN` | Mở transaction vật lý |
| `SAVEPOINT optional_step` | Đánh dấu vị trí có thể quay lại |
| `ROLLBACK TO SAVEPOINT optional_step` | Hoàn tác thay đổi SQL kể từ mốc đó trong cùng transaction |
| `RELEASE SAVEPOINT optional_step` | Giải phóng mốc; không phải commit |
| `COMMIT` | Xác nhận toàn bộ thay đổi còn lại trong transaction |
| `ROLLBACK` | Hủy toàn bộ transaction vật lý, kể cả thay đổi trước savepoint |

Trong PostgreSQL, `ROLLBACK TO SAVEPOINT` không tự hủy savepoint được chỉ định; có thể dùng `RELEASE SAVEPOINT` sau khi không còn cần nó. Việc tạo/xóa mốc, các giới hạn và chi tiết recovery phụ thuộc DB/driver; với Spring, thường để transaction manager thực hiện thao tác savepoint thay vì tự gửi SQL `SAVEPOINT` trộn lẫn.

## 3. Spring thực hiện rollback con như thế nào?

Đối với JDBC transaction manager hỗ trợ nested transaction:

```java
@Transactional
public void outer() {
    // SQL A
    nestedService.doOptionalWork();
    // SQL C
}

@Transactional(propagation = Propagation.NESTED)
public void doOptionalWork() {
    // SQL B
    throw new IllegalStateException("optional work failed");
}
```

Đây là mã **minh họa**, không phải chương trình độc lập: cần import, JDBC implementation và lời gọi `nestedService` qua Spring-managed proxy.

Trình tự chính xác khi `outer()` được gọi qua proxy:

1. Spring mở transaction T cho outer với `Propagation.REQUIRED` mặc định.
2. Outer thực hiện SQL A trong T.
3. Lời gọi qua proxy vào inner với `NESTED` gặp T đã tồn tại.
4. Với JDBC manager có savepoint, Spring tạo savepoint S1 trên connection của T **trước khi chạy thân inner**.
5. Inner thực thi SQL B rồi ném `IllegalStateException`. Runtime exception mặc định kích hoạt rollback.
6. Transaction interceptor của inner yêu cầu rollback **phạm vi nested**; Spring rollback đến S1, thường giải phóng mốc, rồi chuyển exception ra outer.
7. **Nếu outer bắt được exception và quyết định tiếp tục**, nó có thể thực thi SQL C.
8. Khi outer kết thúc bình thường, Spring cố commit T; nếu commit thành công, A và C tồn tại, B bị hủy.

Điểm quan trọng: **outer phải xử lý lỗi đúng chỗ** để đi tiếp. Nếu exception từ inner thoát luôn khỏi method outer, rollback rule mặc định của outer sẽ xử lý nó như một failure của **giao dịch ngoài**, nên toàn bộ T thường bị rollback. Không phải cứ đánh dấu `NESTED` là mọi lỗi chỉ ảnh hưởng phạm vi con bất kể luồng exception.

### Điều gì thay đổi khi chưa có transaction ngoài?

`Propagation.NESTED` không mặc định tạo savepoint rỗng rồi chờ transaction khác. Với `DataSourceTransactionManager`/`JdbcTransactionManager`, nếu lời gọi không gặp transaction hiện hữu, nó hoạt động theo hướng **bắt đầu một transaction mới** giống tình huống `REQUIRED` chưa có outer. Khi đó, thất bại không phải “rollback một phần”; chính transaction mới sẽ rollback toàn bộ công việc của lời gọi.

Do đó, để chứng minh **partial rollback** thật sự, bài kiểm thử phải có một transaction ngoài hoạt động và lời gọi vào nested đi qua transaction proxy.

## 4. Phạm vi của rollback con: cái gì giữ, cái gì mất?

Giả định một DB transaction T với savepoint S1:

| Hoạt động | Trạng thái sau rollback đến S1 | Sau khi outer commit thành công |
| --- | --- | --- |
| INSERT A thực hiện **trước** S1 | Giữ trong T | A tồn tại |
| INSERT B thực hiện **sau** S1 | Bị hoàn tác | B không tồn tại |
| UPDATE trên hàng có trước S1 nhưng chạy **sau** S1 | Hoàn tác lần UPDATE sau S1 | Giá trị trở về trạng thái tại S1 |
| INSERT C thực hiện **sau rollback về S1** | Giữ trong T | C tồn tại |
| Inner chạy thành công rồi outer rollback toàn bộ | Không cứu được inner | Mọi thay đổi của T bị hủy |
| Email/API call thực hiện sau S1 | Không được rollback bằng JDBC savepoint | Side effect bên ngoài DB vẫn có thể đã xảy ra |

Rollback về savepoint là rollback **các thay đổi database trong transaction và tài nguyên được database kiểm soát từ sau mốc**, không phải “chỉ hoàn tác đúng một method Java” theo cơ chế nhận diện method. Nếu trong thời gian scope con mở có những câu SQL khác dùng **cùng transaction/connection** đi qua, chúng cũng có thể thuộc phần bị hoàn tác.

Ví dụ nếu inner sửa cùng một hàng mà outer đã sửa trước đó, rollback tới S1 có thể giữ cập nhật của outer trước S1 và loại riêng cập nhật thêm của inner. Đó là lý do savepoint hữu ích cho các bước tùy chọn nhưng cần hiểu chính xác thời điểm tạo mốc.

**Không đảo ngược bộ nhớ Java:** đối tượng đã bị thay đổi field trong RAM, biến đếm, cache ứng dụng hoặc entity JPA có thể vẫn mang trạng thái cũ sau JDBC rollback. Phải chủ động đồng bộ lại, tránh dựa vào savepoint như một phép “quay ngược JVM”.

## 5. So sánh NESTED với REQUIRED và REQUIRES_NEW

Giả sử outer đang có transaction T; inner ném unchecked exception, và outer catch để cố tiếp tục:

| Đặc tính | `REQUIRED` inner | `NESTED` inner | `REQUIRES_NEW` inner |
| --- | --- | --- | --- |
| Transaction vật lý | Chia sẻ T | Chia sẻ T | Transaction mới T2; T thường được tạm ngưng |
| Savepoint riêng | Không theo propagation này | Thường có trên JDBC | Không cần để phân tách T2 |
| Inner thất bại, interceptor rollback | Thường đánh dấu T rollback-only | Rollback đến savepoint của T | Rollback T2 |
| Outer catch rồi muốn commit | Có thể nhận `UnexpectedRollbackException` và T rollback | **Có thể** commit phần còn lại của T | **Có thể** commit T độc lập với T2 |
| Inner thành công rồi outer rollback | Thay đổi inner bị hủy cùng T | Thay đổi inner bị hủy cùng T | Thay đổi T2 đã commit có thể **vẫn tồn tại** |
| Connection/resource | Cùng resource transaction | Cùng JDBC connection transaction | Thường cần connection/resource transaction độc lập |
| Khi nào dùng | Một nghiệp vụ phải atomic toàn bộ | Một bước tùy chọn cần có thể hủy riêng **nhưng vẫn lệ thuộc outer commit** | Cần kết quả inner commit/rollback **độc lập** |

Câu “outer có thể commit” luôn có điều kiện: chưa bị đánh dấu rollback-only bởi nguyên nhân khác, database vẫn cho phép tiếp tục và commit, và outer không còn lỗi bắt buộc toàn bộ phải rollback.

`NESTED` **không** phải cách viết khác của `REQUIRES_NEW`:

- NESTED rollback B nhưng nếu outer cuối cùng rollback, A/C và mọi thay đổi con còn lại trong T cũng rollback.
- REQUIRES_NEW có thể commit T2 trước khi T rollback, nên phù hợp với một số audit độc lập nhưng **không** bảo đảm atomicity chung; có thể làm tăng nhu cầu connection pool và rủi ro deadlock tài nguyên nếu lạm dụng.
- REQUIRED tham gia cùng T nhưng không tạo mốc cho phần con. Nếu inner thất bại và interceptor quyết định rollback, transaction chia sẻ thường bị đặt rollback-only; outer catch exception không bảo đảm có thể commit.

Chọn propagation dựa vào yêu cầu **atomicity** chứ không dựa vào ý muốn “cho lỗi biến mất”.

## 6. Điều kiện để `PROPAGATION_NESTED` hoạt động đúng

### 6.1. Transaction manager và JDBC driver phải hỗ trợ savepoint

Trong Spring Framework imperative:

- `DataSourceTransactionManager` và lớp kế thừa `JdbcTransactionManager` hỗ trợ JDBC savepoints. Thuộc tính `nestedTransactionAllowed` mặc định là **true** trên `DataSourceTransactionManager`, nhưng driver/database cũng phải thực sự hỗ trợ savepoints.
- `AbstractPlatformTransactionManager` có cấu hình `setNestedTransactionAllowed(boolean)`. Mặc định nền tảng không bảo đảm hỗ trợ nested cho mọi manager; concrete manager quyết định.
- Khi không hỗ trợ nested hoặc không thể tạo savepoint, hệ thống có thể ném `NestedTransactionNotSupportedException` hoặc ngoại lệ transaction tương ứng, **không nên giả định Spring tự động thay NESTED bằng REQUIRES_NEW**.
- `JpaTransactionManager` mặc định **không bật nested transaction**. Có trường hợp cho phép savepoint đối với phần truy cập JDBC nằm trong JPA transaction, nhưng savepoint không đồng bộ hóa toàn bộ **JPA EntityManager/persistence context**. Không coi bật một flag là hỗ trợ NESTED đầy đủ cho mọi thao tác entity.
- Các manager JTA/distributed/reactive có mô hình khác; không mặc định dùng lại kết luận savepoint JDBC.

Nếu chỉ dùng Spring JDBC + một DataSource, nên kiểm chứng driver qua metadata:

```java
try (var connection = dataSource.getConnection()) {
    boolean supported = connection.getMetaData().supportsSavepoints();
    System.out.println("Savepoints supported: " + supported);
}
```

Đây là đoạn **minh họa bên ngoài transaction**, cần có biến `dataSource` kiểu `javax.sql.DataSource`, import Exception/JDBC phù hợp. Metadata hỗ trợ là điều kiện cần, không phải chứng cứ rằng cấu hình Spring proxy/manager đã đúng. Trong method giao dịch, không tự lấy connection mới bằng `dataSource.getConnection()` để điều khiển savepoint của connection khác; hãy để Spring quản lý connection hiện tại.

### 6.2. Phải đi qua Spring AOP proxy

Ví dụ không đúng trong proxy mode thông thường:

```java
@Service
public class SameBeanService {

    @Transactional
    public void outer() {
        inner(); // Gọi nội bộ qua this, không chặn advice của inner.
    }

    @Transactional(propagation = Propagation.NESTED)
    public void inner() {
        // Không tự động được tạo savepoint trong self-invocation này.
    }
}
```

**Đây là mã minh họa**. Trong Spring proxy mode thông thường, lời gọi `outer()` từ bên ngoài qua proxy mở T, nhưng `this.inner()` không đi qua interceptor nên **không tạo nested savepoint** theo annotation trên inner. Cách rõ ràng là tách thành `OuterService` và `InnerService`, inject bean khác và gọi qua Spring-managed proxy.

Nếu bạn tự tạo service bằng `new` ngoài Spring container, hoặc method không được transaction advisor áp dụng, annotation không tự quản lý connection.

### 6.3. Quy tắc exception vẫn quyết định rollback

Khi một method nested ném `RuntimeException`/`Error` ra khỏi proxy, Spring mặc định yêu cầu rollback nested scope. Với checked exception, Spring transaction mặc định truyền thống **không tự rollback** nếu không khai `rollbackFor` thích hợp.

Ví dụ:

```java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = OptionalStepException.class
)
public void performOptionalStep() throws OptionalStepException {
    // SQL trong nested scope
    throw new OptionalStepException("Cannot apply optional step");
}
```

Mảnh minh họa trên giả định `OptionalStepException extends Exception` và các thành phần khác tồn tại. Thiếu `rollbackFor`, một checked exception có thể làm inner scope **kết thúc theo quyết định commit của Spring**, tức release savepoint mà không hoàn tác SQL B; outer bắt exception và commit thì B vẫn có thể được lưu. Vì thế không thể nói “hễ exception thoát ra từ NESTED là tự rollback về savepoint”.

Ngoài ra, nếu exception **bị bắt và nuốt ngay trong thân method nested**, interceptor thấy method trả về bình thường; savepoint thường được release chứ không rollback trừ khi code chủ động yêu cầu rollback nested status hoặc có lỗi transaction khác.

## 7. Ví dụ Spring Boot chạy được: rollback con, giữ giao dịch ngoài

Bộ ví dụ dưới đây dùng **Java 17, Spring Boot 3.3.13, Spring JDBC và H2 in-memory**, một transaction manager JDBC, không dùng JPA. Bộ phiên bản được cố định để tái lập, không phải tuyên bố đây là bản mới nhất. Có thể dùng dự án được tạo bằng Spring Initializr với Gradle Wrapper.

### 7.1. Cấu trúc project và dependency

```text
nested-savepoint-lab/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/savepoint/
    │   ├── SavepointApplication.java
    │   ├── TransactionConfig.java
    │   ├── InnerService.java
    │   └── OuterService.java
    └── resources/
        └── application.yml
```

**`settings.gradle`**

```groovy
rootProject.name = 'nested-savepoint-lab'
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

Spring JDBC starter cung cấp `JdbcTemplate` và transaction infrastructure. Spring Boot cung cấp một DataSource từ cấu hình JDBC URL, thường dùng HikariCP connection pool. Không cần `spring-boot-starter-web` chỉ để kiểm chứng giao dịch.

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:nesteddemo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
```

H2 database trong bộ nhớ có dữ liệu chỉ trong JVM hiện tại, không phải database lưu vĩnh viễn. Mỗi lần chạy process mới, bảng trong demo được tạo mới. `DB_CLOSE_DELAY=-1` giúp DB còn sống đến lúc JVM tắt.

### 7.2. Tạo manager có savepoint support

**`src/main/java/demo/savepoint/TransactionConfig.java`**

```java
package demo.savepoint;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfig {

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);
        manager.setNestedTransactionAllowed(true);
        return manager;
    }
}
```

`JdbcTransactionManager` là manager dành cho JDBC, kế thừa `DataSourceTransactionManager` và hỗ trợ JDBC savepoints. Với loại manager này, `nestedTransactionAllowed` đã mặc định **true**; gọi setter ở đây nhằm làm rõ giả định và cho phép kiểm thử cấu hình không mơ hồ. Transaction manager tùy chỉnh được đăng ký với tên bean `transactionManager`; Spring Boot JDBC auto-config thông thường sẽ không tạo một manager khác khi đã có bean tương ứng.

Spring Boot thường đã bật transaction annotation support khi có hạ tầng phù hợp; `@EnableTransactionManagement` được khai rõ ở ví dụ để không phụ thuộc vào người đọc suy đoán từ auto-configuration. Đây là một bean manager **duy nhất** trong project.

### 7.3. InnerService: một method thất bại và một method thành công

**`src/main/java/demo/savepoint/InnerService.java`**

```java
package demo.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void writeThenFail() {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            2L, "inner-to-undo"
        );
        throw new IllegalStateException("nested failed");
    }

    @Transactional(propagation = Propagation.NESTED)
    public void writeSuccessfully() {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            5L, "inner-success"
        );
    }
}
```

`writeThenFail()` chèn ID 2 rồi ném unchecked exception. Chọn trường hợp “**SQL đã chạy thành công, sau đó nghiệp vụ phát hiện lỗi**” để chứng minh rollback thật sự phục hồi thay đổi; nó không dựa vào một INSERT vốn đã thất bại nên chưa tạo dữ liệu.

`writeSuccessfully()` tạo một nested scope có savepoint nhưng kết thúc bình thường. Nó chứng minh rằng **thành công ở inner không commit độc lập**: nếu outer sau đó fail, ID 5 vẫn không thể sống sót.

### 7.4. OuterService: bắt lỗi để tiếp tục và thử rollback toàn cục

**`src/main/java/demo/savepoint/OuterService.java`**

```java
package demo.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final InnerService inner;
    private final JdbcTemplate jdbc;

    public OuterService(InnerService inner, JdbcTemplate jdbc) {
        this.inner = inner;
        this.jdbc = jdbc;
    }

    @Transactional
    public void outerContinuesAfterNestedFailure() {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            1L, "outer-before"
        );

        try {
            inner.writeThenFail();
        } catch (IllegalStateException ex) {
            System.out.println("Caught nested: " + ex.getMessage());
        }

        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            3L, "outer-after"
        );
    }

    @Transactional
    public void outerFailsAfterNestedSuccess() {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            4L, "second-outer"
        );
        inner.writeSuccessfully();
        throw new IllegalStateException("outer failed");
    }
}
```

Lưu ý:

- `OuterService` và `InnerService` là **hai bean khác nhau**. Lời gọi `inner.writeThenFail()` và `inner.writeSuccessfully()` sẽ qua Spring AOP proxy.
- `outerContinuesAfterNestedFailure` **bắt lỗi sau khi lời gọi proxy inner đã hoàn tất rollback đến savepoint**. Nếu lỗi từ inner không phải một lỗi nghiệp vụ có thể bỏ qua, không nên nuốt exception kiểu này.
- `outerFailsAfterNestedSuccess` cố ý ném unchecked exception **sau khi inner đã hoàn tất**. Transaction ngoài rollback toàn bộ cả ID 4 lẫn ID 5.

### 7.5. Chương trình chính, truy vấn và output

**`src/main/java/demo/savepoint/SavepointApplication.java`**

```java
package demo.savepoint;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class SavepointApplication {

    public static void main(String[] args) {
        SpringApplication.run(SavepointApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(OuterService outer, JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE events ("
                    + "id BIGINT PRIMARY KEY, "
                    + "message VARCHAR(80) NOT NULL)"
            );

            System.out.println("Before: " + rows(jdbc));

            outer.outerContinuesAfterNestedFailure();
            System.out.println("After nested rollback: " + rows(jdbc));

            try {
                outer.outerFailsAfterNestedSuccess();
            } catch (IllegalStateException ex) {
                System.out.println("Caught outer: " + ex.getMessage());
            }
            System.out.println("After outer rollback: " + rows(jdbc));
        };
    }

    private static List<String> rows(JdbcTemplate jdbc) {
        return jdbc.query(
            "SELECT id, message FROM events ORDER BY id",
            (rs, rowNum) ->
                rs.getLong(1) + ":" + rs.getString(2)
        );
    }
}
```

Chạy ở thư mục project có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giữa các log Spring Boot và Gradle, năm dòng do chương trình in ra, theo đúng thứ tự:

```text
Before: []
Caught nested: nested failed
After nested rollback: [1:outer-before, 3:outer-after]
Caught outer: outer failed
After outer rollback: [1:outer-before, 3:outer-after]
```

Đọc kết quả:

1. Ban đầu bảng rỗng: `Before: []`.
2. Outer INSERT ID 1.
3. Inner tạo savepoint, INSERT ID 2 và ném `IllegalStateException`. Spring rollback về savepoint; outer bắt exception, in `Caught nested`.
4. Outer INSERT ID 3 rồi trả về bình thường; transaction vật lý commit. DB có ID **1 và 3**, không có ID 2.
5. Lần gọi thứ hai: outer INSERT ID 4; inner nested INSERT ID 5 và kết thúc bình thường. Sau đó outer ném `IllegalStateException`. Spring rollback **toàn bộ transaction thứ hai**, nên cả ID 4 lẫn 5 không có trong DB. Dữ liệu đã commit từ lần gọi đầu vẫn giữ nguyên.

**Phân biệt trước/sau proxy:** Runner không có transaction bao ngoài, gọi các method của `OuterService` qua Spring bean. Mỗi lần `rows(jdbc)` đọc là **sau khi proxy outer đã commit hoặc rollback**. Đọc bên trong outer trước commit có thể thấy dữ liệu chưa commit, nên không dùng hiện tượng đó làm chứng cứ dữ liệu đã được xác nhận vĩnh viễn.

Bộ ví dụ này **là một project Spring Boot đầy đủ khi đặt các file đúng cấu trúc, có Gradle Wrapper và dependency đã khai**. Các file Java không chạy độc lập bằng `javac` thiếu classpath Spring; lệnh chạy là `./gradlew bootRun`.

## 8. Bắt exception ở đâu tạo ra khác biệt?

### 8.1. Catch ở outer, sau khi nested interceptor rollback

Mẫu trong ví dụ:

```java
@Transactional
public void outer() {
    writeRequiredPart();

    try {
        nestedService.optionalStep();
    } catch (OptionalOperationException ex) {
        recordFallbackState();
    }

    writeFinalPart();
}
```

Đây là mã minh họa với các helper chưa khai báo. Giả định `optionalStep()` là method ở bean khác, có `@Transactional(propagation = NESTED, rollbackFor = OptionalOperationException.class)`, exception thật sự thoát qua proxy inner, savepoint được hỗ trợ và transaction vẫn khỏe. Khi outer bắt exception, bước con đã được rollback, còn công việc outer trước savepoint vẫn nằm trong cùng physical transaction.

Cần quyết định **ngoại lệ nào có thể phục hồi**. Không nên `catch (Exception)` rồi làm như transaction chắc chắn an toàn; một số lỗi connection/database khiến transaction không thể tiếp tục. Với lỗi hệ thống nghiêm trọng, để exception thoát ngoài nhằm rollback toàn bộ thường an toàn hơn.

### 8.2. Catch ngay bên trong inner, rồi trả về bình thường

```java
@Transactional(propagation = Propagation.NESTED)
public void optionalStep() {
    try {
        jdbc.update("INSERT INTO events ...");
        validateAfterWrite();
    } catch (IllegalStateException ex) {
        // Nuốt lỗi và return; interceptor không nhận exception.
    }
}
```

Đoạn minh họa không thể chạy độc lập vì câu SQL/helper bị rút gọn. Khi không có rollback-only và method trả về bình thường, interceptor thường **release savepoint** thay vì rollback. Những thay đổi SQL đã thực hiện có thể được commit cùng outer. Nếu muốn hoàn tác bước con, tốt nhất để exception có rollback rule **thoát qua transaction advice của inner**, rồi catch ở outer.

### 8.3. Inner ném exception nhưng outer không catch

```text
outer transaction T
  |
  +-- tạo savepoint cho inner NESTED
  +-- inner ném RuntimeException
  +-- rollback inner về savepoint
  +-- exception tiếp tục thoát khỏi outer
  +-- outer interceptor nhìn thấy RuntimeException
  +-- rollback toàn bộ T
```

Một phần đã được rollback về savepoint, **nhưng sau đó toàn bộ giao dịch vẫn rollback** do outer không xử lý lỗi. Vì vậy, statement “NESTED luôn giúp outer commit” là sai. NESTED tạo *khả năng* phục hồi cục bộ; nghiệp vụ outer vẫn phải quyết định có tiếp tục hay không.

### 8.4. Checked exception phải khai rollback rule

Giả sử:

```java
public class OptionalStepException extends Exception {
    public OptionalStepException(String message) {
        super(message);
    }
}
```

Khi inner khai:

```java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = OptionalStepException.class
)
public void optionalStep() throws OptionalStepException {
    jdbc.update("INSERT INTO events (id, message) VALUES (?, ?)",
                20L, "checked-step");
    throw new OptionalStepException("optional step rejected");
}
```

đây là một mảnh class/service minh họa sử dụng field `jdbc` trong bean thực tế. `rollbackFor` giúp unchecked/checked rollback rules phản ánh đúng nghiệp vụ. Nếu **bỏ `rollbackFor`**, Spring theo default truyền thống không rollback khi chỉ nhận một checked exception, dù scope là NESTED; inner có thể kết thúc bằng release savepoint và outer vẫn commit SQL đã làm.

Cũng cần phân biệt:

- `noRollbackFor` có thể khiến một exception cụ thể **không** kích hoạt rollback con.
- `rollbackForClassName` so khớp mẫu chuỗi tên exception, có nguy cơ khớp nhầm; dùng `rollbackFor = OptionalStepException.class` khi có type trên classpath.
- Nếu inner gọi qua self-invocation, cả `NESTED` lẫn `rollbackFor` trên inner đều không được transaction advice áp dụng theo proxy mode thông thường.
- Những project bật chính sách rollback toàn cục khác mặc định cần kiểm thử theo policy thực tế, không suy luận từ ví dụ default.

## 9. Programmatic NESTED bằng TransactionTemplate

Không bắt buộc dùng annotation. Khi cần tạo transaction boundary động, `TransactionTemplate` cung cấp một cách điều khiển cụ thể. Dưới đây là **một method minh họa có thể biên dịch trong class sở hữu các dependency thích hợp**; giả định bảng `events` đã có, ID không trùng:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public void processWithTemplates(
        PlatformTransactionManager manager,
        JdbcTemplate jdbc) {

    TransactionTemplate outer = new TransactionTemplate(manager);
    TransactionTemplate nested = new TransactionTemplate(manager);
    nested.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_NESTED);

    outer.execute(outerStatus -> {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            10L, "outer-10"
        );

        try {
            nested.execute(nestedStatus -> {
                jdbc.update(
                    "INSERT INTO events (id, message) VALUES (?, ?)",
                    11L, "inner-11"
                );
                throw new IllegalStateException("recoverable");
            });
        } catch (IllegalStateException ex) {
            // Nested template đã rollback về savepoint nếu hỗ trợ.
        }

        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            12L, "outer-12"
        );
        return null;
    });
}
```

Đặt method này bên trong một class Java (imports ở đầu file), có `PlatformTransactionManager` hỗ trợ nested/savepoints và `JdbcTemplate` dùng đúng DataSource. `TransactionTemplate.execute(...)` tự quản lý transaction status và exception, nên cùng một manager thấy outer đang tồn tại, nested tạo savepoint; khi unchecked exception thoát callback nested, nó rollback scope con trước khi exception bị outer bắt. Nếu toàn bộ transaction outer commit, DB có ID 10 và 12, không có 11.

**Lợi điểm:** không phụ thuộc proxy cho lời gọi nested giữa hai callback vì transaction boundary được tạo **trực tiếp qua template**. Nhưng vẫn phụ thuộc manager/driver hỗ trợ savepoint; không nên tạo thêm một manager khác trỏ sang DataSource khác rồi mong nó tham gia cùng physical transaction.

Nếu bạn gọi `TransactionTemplate` cho outer nhưng bên trong sử dụng repository JPA với một `JpaTransactionManager` khác, không thể tự suy ra cùng connection hay cùng savepoint. Cần kiểm tra kiến trúc transaction thật sự.

## 10. Tự tạo savepoint bằng JDBC / TransactionStatus khi cần mức điều khiển thấp

### 10.1. API JDBC thuần

JDBC cung cấp `java.sql.Savepoint`, `Connection.setSavepoint()`, `rollback(savepoint)` và `releaseSavepoint(savepoint)`. Ví dụ thuần JDBC:

```java
import java.sql.Connection;
import java.sql.Savepoint;

public void optionalJdbcWork(Connection connection) throws Exception {
    // Caller phải cung cấp một connection đang trong transaction,
    // autoCommit=false, và driver hỗ trợ savepoint.

    Savepoint savepoint = connection.setSavepoint();

    try {
        // Thực hiện các JDBC Statements trên chính connection này.
        performJdbcStep(connection);
        connection.releaseSavepoint(savepoint);
    } catch (Exception ex) {
        connection.rollback(savepoint);
        connection.releaseSavepoint(savepoint);
        throw ex;
    }
}
```

Đây là **mã minh họa**, helper `performJdbcStep` phải được cung cấp. Quy tắc quan trọng là tất cả SQL thuộc bước cần rollback dùng **cùng connection đã tạo savepoint**. Sau `rollback(savepoint)`, transaction ngoài vẫn mở. Caller quyết định khi nào commit/rollback transaction vật lý. Nếu bản thân rollback đến savepoint thất bại, cần xử lý như lỗi tài nguyên nghiêm trọng, không tiếp tục commit một cách mù quáng.

Không nên tự gọi `connection.commit()` hoặc `connection.rollback()` toàn bộ từ DAO trong khi Spring đang sở hữu transaction; làm vậy sẽ phá ranh giới mà transaction manager đang quản lý. Trong ứng dụng Spring, dùng `TransactionTemplate` hoặc `@Transactional(propagation = NESTED)` thường an toàn hơn.

### 10.2. SavepointManager / TransactionStatus của Spring

Spring cung cấp các thao tác trên `TransactionStatus`, khi transaction manager hỗ trợ:

```java
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

// Bên trong method đang được transaction interceptor quản lý:
TransactionStatus status =
    TransactionAspectSupport.currentTransactionStatus();

Object savepoint = status.createSavepoint();
try {
    performOptionalDatabaseWork();
    status.releaseSavepoint(savepoint);
} catch (RuntimeException ex) {
    status.rollbackToSavepoint(savepoint);
    status.releaseSavepoint(savepoint);
    // Caller có thể quyết định tiếp tục hoặc ném lỗi.
}
```

Đây là **mảnh minh họa**; `performOptionalDatabaseWork()` cần được định nghĩa và chạy trên resource của đúng transaction. `currentTransactionStatus()` chỉ có ý nghĩa khi thật sự ở trong advice quản lý transaction. Việc dùng `status.setRollbackOnly()` có semantics khác (đánh dấu status cần rollback khi scope hoàn tất), **không phải lời gọi trực tiếp “rollback to savepoint”**; với code khó kiểm soát, ưu tiên API savepoint rõ ràng hoặc nested transaction declarative như ví dụ chính.

Trong phiên bản Spring mới, API savepoint có thể còn hỗ trợ callbacks đồng bộ liên quan savepoint; không cần sử dụng chúng cho bài thực hành đầu tiên. Luôn kiểm tra version của Spring API trong dự án thay vì sao chép snippet của version khác.

## 11. Nested không đồng nghĩa rollback an toàn với mọi loại tài nguyên

### 11.1. JDBC vs JPA/Hibernate

`DataSourceTransactionManager`/`JdbcTransactionManager` sử dụng JDBC connection/savepoint nên phù hợp với ví dụ SQL trực tiếp. Trong khi đó, `JpaTransactionManager` mặc định `nestedTransactionAllowed=false` vì một JDBC savepoint **không thể đưa JPA persistence context trở về trạng thái trước savepoint**.

Ví dụ entity:

```java
order.setStatus(OrderStatus.CONFIRMED);
entityManager.flush();
// JDBC rollback về savepoint phía sau thao tác SQL
// không tự khôi phục trường status trong Java object.
```

Đây là snippet minh họa, không phải method chạy độc lập. Nếu có rollback SQL phía dưới ORM, managed entity trong persistence context có thể vẫn phản ánh trạng thái không còn tồn tại trong DB. Những lần flush sau có thể dẫn đến sai lệch hoặc lỗi. **Không bật nested cho JPA rồi giả định Hibernate entity được “đảo ngược” đồng bộ.**

Khi dùng Spring Data JPA, cân nhắc thiết kế lại boundary, làm việc ở JDBC layer riêng nếu phù hợp, hoặc để cả nghiệp vụ rollback toàn bộ. Chọn cơ chế dựa trên transaction manager thực sự và khả năng của persistence provider.

### 11.2. Lỗi cơ sở dữ liệu có thể làm transaction không thể tiếp tục

Rollback về savepoint thường giúp phục hồi **những thay đổi SQL kể từ mốc** và trong PostgreSQL có thể cho phép tiếp tục sau một lỗi statement bằng cách rollback đến savepoint. Nhưng không bảo đảm mọi lỗi connection, mất kết nối, transaction timeout, lỗi hệ thống hay side effect bên ngoài đều có thể phục hồi.

Nếu connection đã bị mất hoặc DB không chấp nhận transaction nữa, cố tiếp tục sẽ tạo lỗi mới. Những lỗi như vậy nên bubble lên và để outer rollback/cảnh báo. Chỉ catch những exception nghiệp vụ mà service thực sự xác định là **optional, recoverable**.

### 11.3. Những gì savepoint không quay ngược được

- HTTP request, email đã gửi, Kafka event đã publish, file đã ghi hoặc thao tác trên một hệ thống khác không nằm trong cùng DB transaction.
- Các thay đổi biến Java, static state, cache và persistence context không đồng bộ với rollback JDBC.
- Một số hiệu ứng đặc thù database có tính không-transactional, ví dụ sequence increments (như `nextval` trong PostgreSQL) không đảm bảo được hoàn tác khi rollback.
- DDL ở một số database có thể gây implicit commit hoặc có semantics khác; không suy luận mọi DDL đều rollback về savepoint an toàn.

Nếu bước tùy chọn gây side effect ngoài DB, xem xét transactional outbox, after-commit processing, idempotency hoặc cơ chế bù trừ (*compensation*) thay vì kỳ vọng JDBC savepoint xử lý tất cả.

### 11.4. Isolation và lock không trở thành “riêng” cho nested scope

Vì NESTED chia sẻ một physical transaction, nó không có isolation level độc lập như `REQUIRES_NEW`. Savepoint có thể ảnh hưởng đến các thay đổi và lock được tạo sau mốc theo quy tắc của từng DB, nhưng không làm phần outer trước savepoint đã được commit hay giải phóng toàn bộ tài nguyên trước khi outer kết thúc.

Nếu một inner method ghi `@Transactional(propagation=NESTED, isolation=SERIALIZABLE)` trong outer đã mở `READ_COMMITTED`, đừng kỳ vọng có một physical transaction SERIALIZABLE độc lập. Với policy nghiêm ngặt hoặc manager đặc biệt, có thể phát sinh lỗi hoặc những yêu cầu riêng bị bỏ qua; xác nhận theo manager/version thay vì dựa vào tên NESTED.

## 12. Một số ngộ nhận cần sửa ngay

| Ngộ nhận | Điều đúng |
| --- | --- |
| “`NESTED` tạo một transaction riêng” | Nó thường tạo **JDBC savepoint trong cùng physical transaction** khi outer đã tồn tại |
| “Inner NESTED thành công tức đã commit xong” | Thành công thường chỉ release savepoint; outer rollback sau đó vẫn hủy inner |
| “Inner lỗi là outer luôn commit được” | Outer phải xử lý lỗi, transaction/database còn khả năng commit; nếu exception thoát outer thì outer có thể rollback tất cả |
| “Bắt exception bên trong inner là đã rollback con” | Interceptor không thấy exception đã bị nuốt; có thể release savepoint thay vì rollback |
| “Mọi checked exception trong NESTED đều rollback” | Cần cấu hình `rollbackFor`/policy tương ứng |
| “`REQUIRED` lỗi rồi outer catch giống NESTED” | REQUIRED có thể đánh dấu shared transaction rollback-only, làm outer commit thất bại |
| “`REQUIRES_NEW` và NESTED là một” | REQUIRES_NEW là transaction vật lý độc lập; inner commit có thể sống sót dù outer rollback |
| “Cứ thêm `@Transactional(NESTED)` trong cùng class là đủ” | Self-invocation trong proxy mode thường bỏ qua interceptor của inner |
| “`JpaTransactionManager` mặc định xử lý NESTED entity như JDBC” | JPA context không tự được hoàn tác bởi JDBC savepoint; nested mặc định disabled |
| “Savepoint rollback hủy được email/API/file” | Chỉ xử lý tài nguyên transactional phù hợp, không hoàn tác external side effects |

## 13. Thiết kế trường hợp sử dụng phù hợp

Một tình huống đúng:

- Outer transaction phải lưu **đơn hàng và trạng thái vận hành chính**.
- Một bước tùy chọn ghi **bảng ghi chú/ưu đãi phụ**.
- Nếu bước phụ bị từ chối theo **quy tắc nghiệp vụ có thể phục hồi**, chỉ hủy SQL của bước phụ.
- Outer ghi một trạng thái fallback rõ ràng và tiếp tục commit, không che giấu lỗi hệ thống quan trọng.

Thí dụ cấu trúc nghiệp vụ:

```text
outer @Transactional REQUIRED
    |
    +-- INSERT order
    +-- INSERT inventory reservation
    |
    +-- inner @Transactional NESTED
    |      +-- INSERT optional promotion records
    |      +-- validate promotion
    |      +-- nếu invalid -> rollback to savepoint
    |
    +-- catch OptionalPromotionRejectedException
    +-- UPDATE order SET promotion_status='SKIPPED'
    +-- COMMIT outer
```

Các precondition cần ghi thành test:

1. Nếu promotion invalid, hàng/record chỉ thuộc bước promotion **không còn**.
2. Đơn hàng và inventory reservation trước savepoint vẫn được commit nếu nghiệp vụ cho phép.
3. Nếu outer phát hiện một lỗi bắt buộc sau đó, **tất cả** thay đổi DB trong outer, kể cả những bước nested thành công, đều rollback.
4. Với lỗi hạ tầng không thể phục hồi, ứng dụng fail-fast thay vì catch tất cả để “cố commit”.
5. Nếu có JPA/ORM, phải xử lý đúng vấn đề persistence context; không mặc định dùng JDBC savepoint cho entity changes.

Một tình huống không phù hợp: “Ghi audit phải tồn tại **ngay cả khi outer rollback**.” NESTED **không** đạt được yêu cầu này vì vẫn cùng physical transaction. Có thể cần `REQUIRES_NEW` nếu audit ở một DB transaction độc lập phù hợp, hoặc outbox/hệ thống ghi audit chuyên biệt với trade-off đã được đánh giá.

## 14. Kiểm thử thế nào để phân biệt các propagation?

Một bài kiểm thử hiệu quả nên tách các kịch bản:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Outer ghi A → nested ghi B rồi RuntimeException → outer catch → ghi C → outer commit | DB có A/C, không có B |
| Outer ghi A → nested ghi B, return bình thường → outer commit | DB có A/B |
| Outer ghi A → nested ghi B, return bình thường → outer rollback | DB không có A/B |
| Outer ghi A → nested ghi B rồi lỗi → outer **không catch** | Outer cũng rollback; DB không có A/B |
| Cùng kịch bản lỗi nhưng inner dùng `REQUIRED` thay NESTED | Có thể `UnexpectedRollbackException` khi outer cố commit |
| Inner ném checked exception không có `rollbackFor`, outer catch và commit | Có thể giữ B, do Spring không rollback con theo default checked |
| Driver hoặc transaction manager không hỗ trợ savepoint | Có lỗi không hỗ trợ/không tạo được nested transaction, không được giả định silently fallback |

**Nguyên tắc test:** đọc dữ liệu **sau khi outer method qua proxy đã kết thúc**. Một test `@Transactional` bao quanh cả lời gọi và query có thể nhìn thấy dữ liệu chưa commit hoặc tự rollback cuối test, che giấu semantics cần kiểm tra.

Có thể dùng H2 để học Spring lifecycle, nhưng test thêm trên DB production (PostgreSQL, MySQL InnoDB, ...) để xác minh hành vi JDBC savepoint, constraint và error recovery thực tế.

### Debug khi tưởng có savepoint nhưng vẫn rollback toàn bộ

Kiểm tra theo thứ tự:

1. Manager thực sự đang dùng là gì? `JdbcTransactionManager`, `DataSourceTransactionManager` hay `JpaTransactionManager`?
2. Driver/DB có `Connection.getMetaData().supportsSavepoints()` không?
3. Outer có actual transaction khi gọi inner không?
4. Lời gọi vào inner có qua Spring proxy khác bean không?
5. `Propagation.NESTED` có được khai trên method thực sự được intercept không?
6. Exception có thoát ra khỏi inner proxy và khớp rollback rules không?
7. Outer catch exception sau nested hay để exception thoát khỏi outer?
8. Đã có một lỗi khác khiến outer transaction bị rollback-only hoặc DB không thể commit chưa?
9. Có dùng đúng DataSource/connection không? Một connection riêng nằm ngoài transaction không thuộc savepoint.
10. Có lẫn JPA persistence context với rollback JDBC khiến state quan sát lệch không?

Khi nghi ngờ, bật log debug có chọn lọc cho Spring transaction/JDBC trong môi trường test; xem thời điểm tạo transaction, tạo savepoint, rollback và commit. Tránh log secret hoặc dữ liệu nhạy cảm. Tách thao tác phụ và nghiệp vụ chính rõ ràng để test các ranh giới độc lập.

## 15. Câu hỏi tự kiểm tra

**1. Sau khi inner NESTED thành công, outer ném `RuntimeException`. Dữ liệu inner có còn không?**

Không, nếu mọi ghi thuộc cùng physical JDBC transaction và outer rollback thành công. “Inner success” không phải một commit riêng.

**2. Inner NESTED ném `IllegalStateException`, outer catch rồi chạy tiếp. Vì sao A có thể còn nhưng B mất?**

Vì Spring rollback phần nested về savepoint trước khi trả exception cho outer; các thay đổi A trước mốc không bị rollback cục bộ. Outer có thể tiếp tục và commit nếu transaction vẫn hợp lệ.

**3. Nếu inner NESTED ném checked `Exception` mà thiếu `rollbackFor`, có chắc rollback B không?**

Không. Với rollback rules mặc định truyền thống, checked exception không tự kích hoạt rollback. Hãy khai `rollbackFor = YourCheckedException.class` nếu mục tiêu là rollback con.

**4. Có cần `REQUIRES_NEW` để rollback con về savepoint không?**

Không. `REQUIRES_NEW` tạo transaction riêng, trong khi `NESTED` dùng savepoint trên cùng transaction JDBC. Hai cơ chế có semantics khác nhau khi outer rollback.

**5. Vì sao @Transactional(NESTED) không có tác dụng khi gọi qua `this.inner()`?**

Vì trong Spring AOP proxy mode, lời gọi nội bộ không đi qua transaction interceptor của inner. Tách bean hoặc dùng programmatic TransactionTemplate để tạo scope thực sự.

**6. Khi có JPA EntityManager, liệu savepoint rollback có tự sửa lại field của managed entity không?**

Không. JDBC savepoint và JPA persistence context có cơ chế quản lý trạng thái khác nhau; phải tránh suy ra JPA hỗ trợ nested đầy đủ.

**7. Rollback về savepoint có commit những thay đổi trước savepoint không?**

Không. Nó chỉ rollback phần sau mốc, để transaction vật lý vẫn mở. Commit phải xảy ra tại outer boundary.

## 16. Kết luận

**Rollback phạm vi con về savepoint** là khả năng quan trọng của `Propagation.NESTED` trong hệ Spring JDBC: một transaction vật lý có thể chia thành các đoạn có thể phục hồi cục bộ. Khi inner thất bại và Spring thực hiện rollback về savepoint, outer có thể bắt lỗi có chủ đích, tiếp tục ghi và cuối cùng commit phần còn lại. Nhưng outer vẫn chịu trách nhiệm với **kết quả cuối cùng**, và một outer rollback sẽ hoàn tác mọi thay đổi DB còn thuộc transaction đó.

Công thức thiết kế để nhớ:

- **Đúng manager/driver có savepoint**.
- **Outer transaction đang hoạt động + inner đi qua Spring proxy**.
- **`NESTED` + rollback rule phù hợp**.
- **Bắt lỗi ở outer khi thật sự được phép phục hồi**.
- **Đọc DB sau outer commit/rollback để kiểm chứng**.

Nếu cần inner commit độc lập, hãy đánh giá `REQUIRES_NEW` chứ không gán nhiệm vụ đó cho savepoint. Nếu dùng JPA hoặc có external side effects, hãy thiết kế rõ giới hạn và chiến lược nhất quán thay vì giả định mọi thứ tự quay về như trạng thái Java trước lỗi.

## Tài liệu chính thức để đối chiếu

- Spring Framework — *Transaction Propagation*, phần `PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — *Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework 6.1 — `DataSourceTransactionManager` API và nested savepoint support: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `JdbcTransactionManager`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html
- Spring Framework — `JpaTransactionManager` và giới hạn JDBC savepoints/JPA context: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html
- Spring Framework — `TransactionStatus` / savepoint API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/TransactionStatus.html
- PostgreSQL — `SAVEPOINT`: https://www.postgresql.org/docs/current/sql-savepoint.html
- PostgreSQL — `ROLLBACK TO SAVEPOINT`: https://www.postgresql.org/docs/current/sql-rollback-to.html
- PostgreSQL — `RELEASE SAVEPOINT`: https://www.postgresql.org/docs/current/sql-release-savepoint.html
