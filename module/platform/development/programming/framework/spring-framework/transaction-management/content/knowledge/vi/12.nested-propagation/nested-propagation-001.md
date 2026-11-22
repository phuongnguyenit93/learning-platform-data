# Một giao dịch vật lý với nhiều điểm khôi phục: `NESTED` và JDBC savepoint trong Spring

## Mục tiêu

Sau bài học, bạn có thể:

1. Mô tả chính xác ý nghĩa của **một physical transaction có nhiều savepoint**, khác với việc tạo nhiều transaction độc lập.
2. Giải thích `@Transactional(propagation = Propagation.NESTED)` tạo phạm vi con và sử dụng savepoint như thế nào khi đã có một giao dịch JDBC.
3. Theo dõi thứ tự tạo, release, rollback các savepoint, nhất là tình huống **savepoint bên trong thành công nhưng savepoint cha bị rollback**.
4. Dự đoán dữ liệu nào còn lại khi inner scope thất bại, outer bắt ngoại lệ rồi tiếp tục và cuối cùng commit; và vì sao outer rollback làm mất cả những inner scope đã thành công.
5. Phân biệt `NESTED`, `REQUIRED` và `REQUIRES_NEW`, biết các điều kiện về transaction manager, JDBC driver và việc gọi qua Spring proxy.
6. Chạy ví dụ **Java 17+, Spring Boot 3.3.5, JDBC/H2**, kiểm thử bằng JUnit 5 và sử dụng `SavepointManager` khi cần kiểm soát thủ công.

**Phạm vi:** trong Spring Framework transaction management, bài này tập trung vào `NESTED`/savepoint của transaction JDBC. Không giả định rằng JPA, JTA, reactive transaction hay mọi DBMS tự động hỗ trợ cùng cơ chế.

---

## 1. Một transaction, nhiều điểm có thể quay lại

Một giao dịch vật lý (physical transaction) là đơn vị được database xử lý ở thời điểm `BEGIN`, `COMMIT` hoặc `ROLLBACK`. Với JDBC, transaction manager quản lý trạng thái `autoCommit`, connection và việc kết thúc transaction. Khi phương thức ngoài cùng đã bắt đầu transaction T, các bước nghiệp vụ có thể tạo **savepoint** bên trong T.

Savepoint là một **mốc trong transaction đang mở**. Ta có thể yêu cầu database `ROLLBACK TO SAVEPOINT S` để hủy các thay đổi được thực hiện **sau S** mà vẫn giữ transaction T đang chạy. Sau đó tiếp tục SQL rồi commit T. Tuy nhiên, **savepoint không commit bất kỳ dữ liệu nào**.

Ví dụ khái niệm:

```text
BEGIN T
  INSERT A             -- thao tác ngoài
  SAVEPOINT S1
  INSERT B             -- thao tác trong phạm vi con 1
  ROLLBACK TO S1       -- hủy B, giữ A

  SAVEPOINT S2
  INSERT C             -- thao tác trong phạm vi con 2
  RELEASE S2           -- kết thúc mốc S2, C vẫn CHƯA COMMIT

  INSERT D             -- thao tác ngoài
COMMIT T               -- A, C, D cùng commit
```

Kết quả sau commit: **A, C, D còn; B mất**.

Nếu thay dòng cuối thành `ROLLBACK T`, **A, B, C, D đều không được commit**, kể cả C thuộc một phạm vi nested đã hoàn tất thành công. Đây là điểm quan trọng nhất của bài.

### Ba cấp khái niệm cần phân biệt

| Khái niệm | Vai trò | Thời điểm tồn tại |
| --- | --- | --- |
| Physical transaction **T** | Đơn vị commit/rollback của DB | Từ bắt đầu transaction đến commit/rollback cuối |
| Logical transaction scope | Ranh giới mà `TransactionInterceptor` thiết lập cho mỗi method được advice | Khi đi qua `@Transactional` tương ứng |
| JDBC **savepoint** | Mốc rollback một phần trong T | Khi T đang active và driver/manager hỗ trợ |

Nhiều logical scopes không đương nhiên tương ứng với nhiều physical transactions. Với `NESTED`, ta thường có **một T** và **một savepoint cho mỗi inner scope cần lồng**. Savepoint chỉ cho phép phục hồi một phần; không biến inner scope thành giao dịch tự trị.

## 2. `PROPAGATION_NESTED` hoạt động như thế nào?

Spring có enum `org.springframework.transaction.annotation.Propagation.NESTED`.

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.NESTED)
public void saveOptionalDetail() {
    // SQL cần được rollback riêng về một savepoint khi outer T đã tồn tại.
}
```

Đây là snippet minh họa vị trí annotation, không phải phương thức độc lập có thể dùng `javac` ngay. Quy tắc hoạt động:

- **Có transaction T hiện hữu, cùng manager phù hợp:** Spring tạo một **nested logical scope**; với `DataSourceTransactionManager` và JDBC savepoint, nó tạo một savepoint mới **bên trong T**.
- **Nested method thành công:** Spring kết thúc scope con, thường release savepoint. Những thay đổi sau mốc này **vẫn nằm trong T, chưa commit**.
- **Nested method thất bại và khớp rollback rule:** Spring rollback đến savepoint, bỏ phần thay đổi của scope con. Outer có thể bắt exception **sau khi inner interceptor hoàn tất**, tiếp tục T và commit những phần còn hợp lệ.
- **Không có transaction hiện hữu:** `NESTED` có hành vi như `REQUIRED`, bắt đầu transaction vật lý mới. Không có T bên ngoài để tạo savepoint lồng vào.
- **Không hỗ trợ nested/savepoint:** không được tự hạ cấp từ `NESTED` thành một giải pháp có semantics khác. Framework có thể báo `NestedTransactionNotSupportedException` hoặc lỗi transaction/resource liên quan, tùy nguyên nhân.

Spring AOP proxy phải **thực sự intercept lời gọi** ở nested method. Nếu một bean tự gọi `this.nestedMethod()`, annotation có thể bị bỏ qua do self-invocation. Khi đó không có savepoint riêng do `@Transactional(NESTED)` sinh ra tại lời gọi đó.

### Một timeline chi tiết

```text
Outer proxy -> BEGIN T
  outer INSERT(1)

  Nested-A proxy -> SAVEPOINT S1
    INSERT(2)
    throw RuntimeException
  Nested-A interceptor -> ROLLBACK TO S1, exit with exception

  outer catches error from Nested-A
  Nested-B proxy -> SAVEPOINT S2
    INSERT(3)
  Nested-B interceptor -> release S2 (KHÔNG COMMIT T)

  outer INSERT(4)
  Outer proxy -> COMMIT T
```

**Sau commit có 1, 3, 4; không có 2.** Inner thất bại được khôi phục về mốc riêng, transaction vật lý không nhất thiết bị đánh dấu rollback-only toàn cục như một participating scope `REQUIRED` thông thường.

**Không suy diễn quá mức:** một lỗi DB nghiêm trọng, một rollback-only được đánh dấu từ phạm vi khác, hoặc exception tại outer boundary vẫn có thể làm T bị rollback toàn bộ. `NESTED` không có phép màu biến mọi lỗi thành trạng thái DB hợp lệ.

## 3. Nhiều savepoint: liên tiếp và lồng nhau

Cụm “nhiều điểm khôi phục” có hai ý hay gặp.

### 3.1. Nhiều savepoint liên tiếp

```text
BEGIN T
  INSERT outer-A
  S1 -> INSERT inner-1 -> rollback S1
  S2 -> INSERT inner-2 -> release S2
  S3 -> INSERT inner-3 -> rollback S3
  INSERT outer-B
COMMIT T
```

Các savepoint S1, S2, S3 giúp mỗi bước tùy chọn có thể thành công hoặc thất bại riêng. Inner-2 “thành công” chỉ có nghĩa **không bị rollback về savepoint của nó**, chứ không phải đã được commit độc lập.

Đây là mô hình thích hợp nếu một bản ghi chính phải tồn tại, nhưng vài enrichment/line-item được phép bị loại bỏ khi kiểm tra thất bại; **phải có hợp đồng nghiệp vụ cho phép partial success**.

### 3.2. Savepoint lồng trong savepoint khác

Một nested method có thể gọi **một bean khác** cũng có `@Transactional(NESTED)`:

```text
BEGIN T
  outer INSERT A

  SAVEPOINT S_PARENT
    INSERT B
    SAVEPOINT S_CHILD
      INSERT C
    RELEASE S_CHILD        -- C còn trong T, chưa commit

    throw ParentFailure
  ROLLBACK TO S_PARENT     -- hủy C và B

  outer INSERT D
COMMIT T
```

Kết quả cuối: **A và D**. C dù ở một child scope đã return thành công vẫn bị loại, vì **S_PARENT được tạo trước cả B và C**. Release một savepoint con không khiến dữ liệu của nó trở nên bền vững trước rollback về savepoint cha.

**Quy tắc thứ tự:** `ROLLBACK TO S` tác động lên các thay đổi trong T kể từ khi S được tạo, không chỉ các thay đổi của method có tên gắn với S. Trong cùng connection, rollback về mốc cũ có thể hủy thành quả của những scope con đã release savepoint nhưng phát sinh sau mốc đó.

### Savepoint có phải một bản sao database?

Không. DBMS thường duy trì transactional state và log/undo/lock structures để rollback một phần; không tạo bản sao toàn DB cho từng savepoint. Vòng đời, chi phí tài nguyên, tên và cách xử lý savepoint sau rollback tùy DBMS/driver. Đừng xem savepoint là một phiên bản dữ liệu có thể gọi lại sau khi T đã commit hoặc đã rollback hoàn toàn.

## 4. `NESTED` khác `REQUIRED` và `REQUIRES_NEW` ở điểm nào?

| Đặc điểm | `REQUIRED` bên trong | `NESTED` bên trong | `REQUIRES_NEW` bên trong |
| --- | --- | --- | --- |
| Khi outer T đang tồn tại | Tham gia T | Tham gia T và tạo savepoint khi hỗ trợ | Tạm đình chỉ T và tạo physical transaction mới |
| Transaction vật lý | Cùng T | **Cùng T** | Inner độc lập với T |
| Rollback inner theo lỗi | Thường mark shared T rollback-only | **Rollback về savepoint**; outer có thể tiếp tục | Rollback physical inner transaction riêng |
| Inner return thành công | Không commit T | Release savepoint, **không commit T** | Có thể commit inner transaction riêng |
| Outer rollback sau inner thành công | Inner SQL trong T cũng rollback | Inner SQL trong T cũng rollback | Inner đã commit riêng không tự rollback theo outer |
| Khả năng partial recovery | Hạn chế khi shared T đã rollback-only | Có, khi savepoint phục hồi được và T còn hợp lệ | Có, nhờ transaction riêng |
| Tài nguyên | Một transaction/connection phù hợp | Một transaction/connection JDBC phù hợp | Có thể cần connection mới, chú ý connection pool |
| Phụ thuộc JDBC savepoint | Không | Thường có | Không dùng cùng ý nghĩa savepoint |

Trong `REQUIRED`, một inner `TransactionInterceptor` gặp unchecked exception thường đánh dấu shared T rollback-only. Nếu outer catch rồi cố commit, caller có thể thấy `UnexpectedRollbackException`. Với `NESTED` có savepoint thật sự, Spring thường rollback **đúng phạm vi con** rồi cho outer tiếp tục. Đây là hai chính sách khác nhau, không phải chỉ khác tên.

Trong `REQUIRES_NEW`, inner transaction thật sự độc lập và có thể commit dù outer cuối cùng rollback. Chọn nó thay cho `NESTED` làm thay đổi atomicity, tạo yêu cầu về connection và khả năng dữ liệu lệch nhau. Không dùng chỉ để “làm hết lỗi rollback”.

## 5. Điều kiện để có nhiều JDBC savepoint trong Spring

Muốn tin rằng mô hình trên đúng, phải kiểm tra các yếu tố sau.

1. **Transaction manager hỗ trợ:** `DataSourceTransactionManager` hỗ trợ savepoint JDBC; `JdbcTransactionManager` là subclass của nó. Cờ `nestedTransactionAllowed` của `DataSourceTransactionManager` mặc định là `true`, nhưng nên xác nhận manager và cấu hình thật.
2. **JDBC driver và DBMS hỗ trợ savepoint:** kiểm tra tài liệu database và `Connection.getMetaData().supportsSavepoints()` khi cần. Không phải mọi tổ hợp driver, DB hoặc thao tác SQL đều có cùng quy tắc.
3. **Cùng một transaction manager/DataSource:** `NESTED` phải thấy transaction T phù hợp đã gắn với resource hiện tại. Không mặc nhiên tạo savepoint xuyên hai datasource.
4. **Cùng đường điều phối connection:** code dùng `JdbcTemplate` hoặc `DataSourceUtils` để tham gia transaction Spring, không tự lấy connection mới theo cách bỏ qua transaction-bound resource.
5. **Lời gọi đi qua Spring proxy:** khác bean, hoặc một transaction boundary rõ ràng mà Spring thực sự intercept; không chỉ có annotation trên source.
6. **Transaction T vẫn committable sau khi rollback đến savepoint:** SQL error, ORM state, các resource khác hoặc một scope `REQUIRED` đánh dấu global rollback-only vẫn có thể phá khả năng commit.
7. **Không có commit riêng trong nested scope:** toàn bộ SQL nested vẫn chỉ bền vững sau `COMMIT T`.

Đặc biệt, `JpaTransactionManager` mặc định đặt `nestedTransactionAllowed=false`. Ngay cả khi bật cho một số thao tác JDBC trực tiếp, savepoint chỉ phản ánh **JDBC connection**, không tự đưa **JPA EntityManager/persistence context** về trạng thái tương ứng. Không được hứa rằng rollback đến savepoint sẽ phục hồi đầy đủ state ORM đã được cache trong bộ nhớ. JPA không cung cấp nested transactions theo semantics JDBC savepoint một cách tổng quát.

Với các ví dụ dưới đây, dùng JDBC/H2 thuần để tránh nhầm lẫn đó.

## 6. Ví dụ chạy được: Spring Boot + Java 17 + JDBC/H2

Chúng ta sẽ xây dựng project với một bảng `tx_events`. Mỗi event có `id` và `event_name`; cuối mỗi scenario đọc danh sách event **sau khi transaction boundary đã hoàn tất**. Nhờ đó ta phân biệt rõ một câu SQL từng chạy với dữ liệu đã commit.

Có **ba tình huống**:

- **A — Khôi phục chọn lọc:** một inner savepoint thất bại; inner khác thành công; một nested parent thất bại sau khi nested child đã thành công. Outer catch đúng chỗ rồi commit các bước hợp lệ.
- **B — Outer rollback toàn bộ:** inner `NESTED` hoàn tất thành công nhưng outer ném runtime exception; toàn T rollback, inner không có commit riêng.
- **C — `NESTED` đứng một mình:** không có transaction ngoài; nested method tạo physical transaction mới như `REQUIRED`, và commit khi thành công.

### 6.1. Cấu trúc project

```text
nested-savepoints-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/savepoint/
    │   │   ├── DeepStepService.java
    │   │   ├── NestedStepService.java
    │   │   ├── OuterWorkflowService.java
    │   │   └── SavepointsApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/java/example/savepoint/
        └── SavepointsApplicationTest.java
```

Tạo project Gradle Spring Boot phù hợp JDK 17+ hoặc dùng Spring Initializr để có Gradle wrapper. Các file Java phải nằm đúng package `example.savepoint`. Lệnh chạy ở mục 6.9 không yêu cầu web server.

### 6.2. File `settings.gradle`

```groovy
rootProject.name = 'nested-savepoints-demo'
```

### 6.3. File `build.gradle`

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

Spring Boot quản lý phiên bản Spring Framework, JDBC, H2 thông qua dependency management. Bản 3.3.5 dùng Spring Framework 6.1.x, phù hợp ví dụ Java 17. `spring-boot-starter-jdbc` đưa `JdbcTemplate` và transaction infrastructure vào classpath. Chúng ta sẽ tạo **transaction manager JDBC tường minh** để hành vi savepoint không phụ thuộc vào việc người đọc đoán bean mặc định.

### 6.4. File `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:nested_savepoints_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

H2 in-memory tồn tại trong quá trình chạy; `spring.sql.init.mode=always` giúp Boot thực thi `schema.sql`. Không sử dụng `@Transactional` trên ApplicationRunner, để mỗi scenario tự mở và kết thúc physical transaction riêng theo code service.

### 6.5. File `src/main/resources/schema.sql`

```sql
CREATE TABLE tx_events (
    id INTEGER PRIMARY KEY,
    event_name VARCHAR(80) NOT NULL
);
```

Bảng không có dữ liệu ban đầu. ApplicationRunner sẽ xóa dữ liệu trước từng case để kết quả không phụ thuộc vào case chạy trước. Các câu INSERT của demo có id duy nhất trong mỗi case và hợp lệ đối với schema; lỗi được ném **từ Java sau INSERT thành công**, giúp ta đánh giá riêng hành vi savepoint mà không phải xử lý trạng thái transaction sau SQL syntax/constraint error.

### 6.6. File `src/main/java/example/savepoint/DeepStepService.java`

```java
package example.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DeepStepService {
    private final JdbcTemplate jdbc;

    public DeepStepService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void succeed(int id, String name) {
        jdbc.update(
            "INSERT INTO tx_events (id, event_name) VALUES (?, ?)",
            id, name
        );
    }
}
```

`DeepStepService` là một bean riêng có method public. Khi nó được gọi qua Spring proxy từ một nested method khác đang tham gia T, nó tạo **savepoint của scope sâu hơn**. Nếu nó hoàn tất bình thường, savepoint được release nhưng dữ liệu vẫn là uncommitted data trong T.

### 6.7. File `src/main/java/example/savepoint/NestedStepService.java`

```java
package example.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NestedStepService {
    private final JdbcTemplate jdbc;
    private final DeepStepService deep;

    public NestedStepService(JdbcTemplate jdbc, DeepStepService deep) {
        this.jdbc = jdbc;
        this.deep = deep;
    }

    private void insert(int id, String name) {
        jdbc.update(
            "INSERT INTO tx_events (id, event_name) VALUES (?, ?)",
            id, name
        );
    }

    @Transactional(propagation = Propagation.NESTED)
    public void failAfterInsert(int id, String name) {
        insert(id, name);
        throw new IllegalStateException("nested-failed-" + id);
    }

    @Transactional(propagation = Propagation.NESTED)
    public void succeed(int id, String name) {
        insert(id, name);
    }

    @Transactional(propagation = Propagation.NESTED)
    public void failAfterDeepChildSuccess() {
        insert(5, "parent-write");
        deep.succeed(6, "child-write");
        throw new IllegalStateException("parent-failed");
    }
}
```

Ở `failAfterInsert()`, SQL thành công nhưng code cố ý ném unchecked exception. Khi exception đi ra khỏi method, **nested interceptor** áp dụng rollback rule mặc định và rollback về savepoint của scope này.

Ở `succeed()`, không có exception nên scope thành công, nhưng chưa commit T.

Ở `failAfterDeepChildSuccess()`, Spring tạo savepoint **S_PARENT** trước `insert(5)`; lời gọi `deep.succeed(6, ...)` đi qua proxy của **bean khác**, nên tạo **S_CHILD** sau `insert(5)`. Child return thành công, Spring release S_CHILD. Ngay sau đó parent ném lỗi, interceptor rollback về S_PARENT: cả **5 và 6** đều bị hủy. Đây là hành vi “nhiều điểm khôi phục” quan trọng nhất.

### 6.8. File `src/main/java/example/savepoint/OuterWorkflowService.java`

```java
package example.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterWorkflowService {
    private final JdbcTemplate jdbc;
    private final NestedStepService nested;

    public OuterWorkflowService(
            JdbcTemplate jdbc, NestedStepService nested) {
        this.jdbc = jdbc;
        this.nested = nested;
    }

    private void insert(int id, String name) {
        jdbc.update(
            "INSERT INTO tx_events (id, event_name) VALUES (?, ?)",
            id, name
        );
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void recoverSelectedSteps() {
        insert(1, "outer-before");

        try {
            nested.failAfterInsert(2, "failed-A");
        } catch (IllegalStateException ignored) {
            // Nested interceptor đã rollback về S1.
        }

        nested.succeed(3, "nested-ok");
        insert(4, "outer-middle");

        try {
            nested.failAfterDeepChildSuccess();
        } catch (IllegalStateException ignored) {
            // Parent nested interceptor đã rollback về S_PARENT;
            // cả thao tác 5 lẫn 6 bị hủy.
        }

        insert(7, "outer-after");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void abortAfterNestedSuccess() {
        insert(10, "outer-start");
        nested.succeed(11, "nested-success");
        throw new IllegalStateException("outer-failed");
    }
}
```

Phân biệt chính xác hai kiểu `catch`:

- `recoverSelectedSteps()` bắt `IllegalStateException` **sau khi exception đã đi qua nested proxy**, vì vậy rollback về savepoint đã thực hiện trước lúc control quay lại outer catch. Outer tiếp tục với T còn hợp lệ.
- Nếu catch **ngay trong `NestedStepService.failAfterInsert()`** rồi return, interceptor của nó chỉ thấy completion, nên thông thường **không rollback** về savepoint do lỗi đó. Phải để exception thoát qua nested boundary hoặc chủ động `setRollbackOnly()` trong nested scope.

`abortAfterNestedSuccess()` chứng minh release savepoint không bằng commit: `nested.succeed(11)` thành công, nhưng unchecked exception của outer buộc rollback **T**, xóa cả event 10 và 11.

### 6.9. File `src/main/java/example/savepoint/SavepointsApplication.java`

```java
package example.savepoint;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class SavepointsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SavepointsApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
        manager.setNestedTransactionAllowed(true);
        return manager;
    }

    private static String snapshot(JdbcTemplate jdbc) {
        List<String> rows = jdbc.query(
            "SELECT id, event_name FROM tx_events ORDER BY id",
            (rs, rowNum) ->
                rs.getInt("id") + ":" + rs.getString("event_name")
        );
        return rows.toString();
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("DELETE FROM tx_events");
    }

    @Bean
    ApplicationRunner demonstration(
            OuterWorkflowService outer,
            NestedStepService nested,
            JdbcTemplate jdbc) {
        return args -> {
            reset(jdbc);
            outer.recoverSelectedSteps();
            System.out.println("A rows=" + snapshot(jdbc));

            reset(jdbc);
            try {
                outer.abortAfterNestedSuccess();
            } catch (IllegalStateException ex) {
                System.out.println("B outer error=" + ex.getMessage());
            }
            System.out.println("B rows=" + snapshot(jdbc));

            reset(jdbc);
            nested.succeed(20, "standalone");
            System.out.println("C rows=" + snapshot(jdbc));
        };
    }
}
```

Có một bean `PlatformTransactionManager` duy nhất, tên `transactionManager`; Spring Boot JDBC auto-configuration không cần tự chọn thêm manager khác. `DataSourceTransactionManager` sử dụng JDBC connection được Spring quản lý, và đặt `nestedTransactionAllowed=true` tường minh nhằm làm rõ tiền đề ví dụ. Với H2, các savepoint JDBC được hỗ trợ.

`ApplicationRunner` gọi **bean Spring được inject**, chứ không gọi `new OuterWorkflowService(...)` hoặc self-invocation. Mỗi bước `JdbcTemplate` dùng transaction-bound connection; vì vậy nhiều nested logical scopes đều có thể thao tác savepoint bên trong **một physical transaction** mà outer khởi tạo.

### 6.10. Cách chạy và stdout dự kiến

Tại thư mục gốc project đã có Gradle wrapper, chạy trên macOS/Linux:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu dự án chưa có wrapper, có thể dùng `gradle bootRun` với Gradle đã cài phù hợp, hoặc tạo wrapper trước. Không chạy `javac`/`java` trực tiếp mà không cung cấp classpath Spring/H2.

Phần stdout do ứng dụng in ra (không tính log khởi động của Boot/Gradle) dự kiến:

```text
A rows=[1:outer-before, 3:nested-ok, 4:outer-middle, 7:outer-after]
B outer error=outer-failed
B rows=[]
C rows=[20:standalone]
```

**Vì sao các dòng này đúng?**

- **A:** id 2 bị rollback về S1. Id 3 thuộc nested scope thành công nên giữ lại trong T. Id 5 và 6 bị rollback về S_PARENT, dù id 6 thuộc child savepoint đã thành công. Outer commit T với id 1, 3, 4, 7.
- **B:** id 11 đã đi qua nested method thành công và savepoint được release. Outer ném `IllegalStateException`, do đó rollback T xóa cả id 10 và id 11. Caller bắt exception sau outer proxy để in lỗi; việc bắt này không đảo ngược rollback.
- **C:** `nested.succeed(20, ...)` được gọi khi không có transaction hiện hữu. `NESTED` hoạt động như `REQUIRED`, tự mở transaction mới rồi commit khi method thành công. Vì vậy id 20 tồn tại.

Đây là **kết quả dự kiến theo code và cấu hình**, không phải khẳng định đã chạy Gradle trong môi trường đang thao tác. Để kiểm tra thật, chạy `bootRun` và các test ở mục 8.

## 7. Xem chính xác từng savepoint của case A

Bảng dưới đi theo thứ tự chạy `recoverSelectedSteps()` trong một T.

| Thời điểm | Scope | Hành động | Event có thể nhìn thấy *tạm thời trong T* | Kết quả cuối của hành động |
| --- | --- | --- | --- | --- |
| T0 | Outer | Begin T | — | Chưa commit |
| T1 | Outer | Insert id 1 | 1 | Giữ tạm trong T |
| T2 | Nested-A | Tạo S1, insert id 2 | 1, 2 | Chưa commit |
| T3 | Nested-A | Exception -> rollback S1 | 1 | 2 bị hủy |
| T4 | Nested-B | Tạo S2, insert id 3, release S2 | 1, 3 | 3 còn tạm trong T |
| T5 | Outer | Insert id 4 | 1, 3, 4 | Giữ tạm trong T |
| T6 | Nested-Parent | Tạo S_PARENT, insert id 5 | 1, 3, 4, 5 | Giữ tạm |
| T7 | Nested-Child | Tạo S_CHILD, insert id 6, release S_CHILD | 1, 3, 4, 5, 6 | 6 vẫn chưa commit |
| T8 | Nested-Parent | Exception -> rollback S_PARENT | 1, 3, 4 | 5 và 6 bị hủy |
| T9 | Outer | Insert id 7 | 1, 3, 4, 7 | Giữ tạm |
| T10 | Outer | Commit T | 1, 3, 4, 7 | **Commit một lần duy nhất** |

Bảng này không đảm bảo các transaction đồng thời bên ngoài nhìn thấy cùng tập event ở T1–T9: mức isolation thường che thay đổi chưa commit. Mục “nhìn thấy tạm thời trong T” chỉ mô tả state **bên trong connection của T**, không mô tả dữ liệu mà client khác có thể đọc.

### Vì sao thành công ở child không đủ?

Hãy hình dung S_PARENT là dấu mốc chụp trạng thái logic trước khi chạy một cụm thao tác, trong khi S_CHILD là dấu mốc nằm **sau** S_PARENT. Release S_CHILD không làm C trở thành dữ liệu có commit độc lập; C vẫn nằm sau S_PARENT. Khi rollback tới S_PARENT, DB phải hủy tất cả thay đổi thuộc phần thời gian đó, kể cả các thay đổi vừa qua một child scope thành công.

Một cách tư duy hữu ích:

```text
T--------------------------COMMIT------------------------>
 \-- S_PARENT
      insert 5
      \-- S_CHILD
           insert 6
      /-- release S_CHILD (không commit)
 /-- ROLLBACK TO S_PARENT (hủy cả 5 và 6)
```

Nếu outer sau đó ném lỗi, cả các event 1, 3, 4, 7 cũng bị rollback vì commit T chưa hoàn tất. Do đó khi cần nghiệp vụ bền vững độc lập với outer, `NESTED` **không đáp ứng**; phải xem xét `REQUIRES_NEW`, outbox hoặc cơ chế khác theo invariant.

## 8. Kiểm thử JUnit 5 bằng trạng thái database

Tạo `src/test/java/example/savepoint/SavepointsApplicationTest.java`:

```java
package example.savepoint;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class SavepointsApplicationTest {
    @Autowired OuterWorkflowService outer;
    @Autowired NestedStepService nested;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
    }

    private List<String> events() {
        return jdbc.query(
            "SELECT id, event_name FROM tx_events ORDER BY id",
            (rs, rowNum) ->
                rs.getInt("id") + ":" + rs.getString("event_name")
        );
    }

    @Test
    void rollbackToMultipleSavepointsKeepsOnlyValidEvents() {
        outer.recoverSelectedSteps();

        assertEquals(
            List.of(
                "1:outer-before",
                "3:nested-ok",
                "4:outer-middle",
                "7:outer-after"
            ),
            events()
        );
    }

    @Test
    void successfulNestedScopeIsNotAnIndependentCommit() {
        assertThrows(
            IllegalStateException.class,
            outer::abortAfterNestedSuccess
        );
        assertEquals(List.of(), events());
    }

    @Test
    void nestedWithoutExistingTransactionBehavesLikeRequired() {
        nested.succeed(20, "standalone");
        assertEquals(List.of("20:standalone"), events());
    }
}
```

Chạy:

```bash
./gradlew test
```

**Lưu ý quan trọng cho test:**

- **Không gắn `@Transactional` lên test method hoặc test class**, vì transaction do test framework tạo ra có thể che kết quả commit/rollback của service.
- `@SpringBootTest` khởi tạo context và có thể chạy `ApplicationRunner`; `@BeforeEach` xóa các event trước mỗi test để bảo đảm dữ liệu nền phù hợp.
- Các assertion đọc dữ liệu **sau khi proxy service đã hoàn tất**, không chỉ đọc giữa transaction rồi suy diễn commit.
- Nếu chạy nhiều test song song trên cùng H2 database và cùng bảng, các lần `DELETE` có thể race. Hãy dùng database/schema riêng hoặc tổ chức test tuần tự khi chia sẻ fixture.
- Test A là phép thử mạnh: phải giữ 1, 3, 4, 7 nhưng không được giữ 2, 5, 6. Nếu implementation lỡ dùng `REQUIRED` cho inner, kết quả có thể thành `UnexpectedRollbackException`; nếu dùng `REQUIRES_NEW`, có thể thấy dữ liệu được commit khác mong đợi.

**Chỉ đọc/khẳng định từ annotation chưa đủ.** Test trạng thái DB mới cho biết rollback savepoint và commit outer đã thực sự diễn ra như contract.

## 9. Hai kiểu rollback cho nested scope

### 9.1. Exception đi ra khỏi nested interceptor

```java
@Transactional(propagation = Propagation.NESTED)
public void optionalStep() {
    jdbc.update("INSERT INTO tx_events (id, event_name) " +
                "VALUES (100, 'optional')");
    throw new IllegalStateException("Reject this step");
}
```

Nếu method được gọi qua proxy trong outer T và `IllegalStateException` đi ra, transaction advice thường rollback về savepoint rồi ném tiếp exception. Outer **có thể** catch exception sau proxy và tiếp tục T:

```java
@Transactional
public void orchestrate() {
    requiredWrite();
    try {
        otherBean.optionalStep();
    } catch (IllegalStateException rejected) {
        recordOptionalStepSkipped(rejected);
    }
}
```

Hai snippet này giả định đã có bean, `JdbcTemplate`, method nghiệp vụ và Spring transaction infrastructure. Không phải hai file Java độc lập. `recordOptionalStepSkipped` nếu chỉ ghi log Java thì không cần transaction; nếu ghi DB, nó dùng T đang còn active và cần được thiết kế đúng invariant.

**Điểm mấu chốt:** exception đã qua **inner transaction advice**, nên savepoint đã được rollback trước khi outer `catch`.

### 9.2. Chủ động `setRollbackOnly()` trong nested scope

Nếu contract yêu cầu trả kết quả thất bại thay vì ném exception:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional(propagation = Propagation.NESTED)
public boolean optionalStep() {
    if (shouldSkipThisStep()) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return false;
    }
    performNestedWrites();
    return true;
}
```

Khi `NESTED` đã có savepoint riêng và transaction manager hỗ trợ, local rollback-only của **inner status** khiến Spring rollback tới savepoint khi scope kết thúc; outer có thể tiếp tục. Đây là điểm khác với participating `REQUIRED`, nơi rollback-only có thể được đẩy lên shared transaction T làm T không còn commit được.

Cần phân biệt:

- **Inner `NESTED` status local rollback-only:** mong đợi rollback về savepoint của inner.
- **Outer status local rollback-only:** outer yêu cầu rollback toàn bộ T.
- **Transaction đã global rollback-only từ một nơi khác:** tạo/rollback savepoint không bảo đảm làm T trở lại committable.

Chỉ gọi `TransactionAspectSupport.currentTransactionStatus()` khi code đang được Spring transaction advice quản lý; lời gọi ngoài scope đó có thể thất bại. Nếu chỉ cần code declarative, để exception phù hợp đi ra thường đơn giản hơn việc phụ thuộc Spring API này.

### 9.3. Checked exception mặc định có thể không rollback savepoint

Theo default rollback rules thông dụng trong Spring Framework 6.1, `RuntimeException`/`Error` làm rollback, còn checked exception **không mặc nhiên rollback**:

```java
@Transactional(propagation = Propagation.NESTED)
public void step() throws java.io.IOException {
    insertSomething();
    throw new java.io.IOException("Checked failure");
}
```

Ở ví dụ này, nếu không khai báo rollback rule khác, nested interceptor có thể kết thúc scope **không rollback về savepoint**, dù caller nhận checked exception. Muốn nghiệp vụ hủy phần nested:

```java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = java.io.IOException.class
)
public void step() throws java.io.IOException {
    insertSomething();
    throw new java.io.IOException("Checked failure");
}
```

Hai block là snippet minh họa, chưa khai báo helper `insertSomething()`. Tùy version/cấu hình Spring, default rollback rules có thể được thay đổi. Luôn kiểm tra settings thực tế, nhất là khi nâng cấp framework.

## 10. API programmatic: nhiều savepoint với `SavepointManager`

`@Transactional(NESTED)` là cách declarative. Khi cần nhiều điểm khôi phục **bên trong chính một method**, Spring có API `SavepointManager` thông qua `TransactionStatus`.

Mẫu code minh họa:

```java
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.TransactionStatus;

@Transactional
public void importBatch() {
    TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

    insertRequiredHeader();

    Object pointA = status.createSavepoint();
    try {
        importOptionalSegmentA();
    } catch (RecoverableImportException failure) {
        status.rollbackToSavepoint(pointA);
    } finally {
        status.releaseSavepoint(pointA);
    }

    Object pointB = status.createSavepoint();
    try {
        importOptionalSegmentB();
    } catch (RecoverableImportException failure) {
        status.rollbackToSavepoint(pointB);
    } finally {
        status.releaseSavepoint(pointB);
    }

    insertRequiredFooter();
}
```

**Đây là ví dụ API ở mức thiết kế**, không phải class Java chạy độc lập: các helper và `RecoverableImportException` là kiểu nghiệp vụ cần tự định nghĩa. Với một transaction JDBC hỗ trợ savepoints, phương thức tương đương ý tưởng: bắt đầu T, lưu mốc A, tùy tình hình quay về A, lưu mốc B, tùy tình hình quay về B, rồi để outer transaction quyết định commit.

Các lưu ý:

- `TransactionStatus` triển khai giao diện `SavepointManager` nhưng không phải **mọi manager/status** đều hỗ trợ tạo savepoint. Không được sử dụng trên JTA/JPA bất kỳ rồi mặc định nó hoạt động.
- Nếu một thao tác có thể gây DB error khiến transaction bị aborted, phải hiểu DBMS có cho phép phục hồi bằng savepoint hay không.
- Bắt exception rồi rollback thủ công là một lựa chọn thiết kế có tính chặt chẽ cao: phải bảo đảm báo kết quả partial success/minh bạch cho caller.
- Không gọi `status.setRollbackOnly()` cho **outer status** chỉ vì muốn hủy đoạn A; điều đó yêu cầu rollback **toàn bộ T**.
- Trong code Spring service nhiều tầng, `@Transactional(NESTED)` trên các bean rõ trách nhiệm thường dễ kiểm thử và đọc hơn là tạo/giải phóng rất nhiều savepoint thủ công trong một method.

### Dùng `TransactionTemplate` khi không muốn dựa vào AOP proxy

Có thể đặt transaction vật lý bằng `TransactionTemplate`, rồi dùng status để tạo savepoint:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

template.execute(status -> {
    insertRequiredHeader();

    Object savepoint = status.createSavepoint();
    try {
        writeOptionalDetails();
    } catch (RuntimeException rejected) {
        status.rollbackToSavepoint(savepoint);
    } finally {
        status.releaseSavepoint(savepoint);
    }

    insertRequiredFooter();
    return null;
});
```

Đây là snippet giả định có bean `transactionManager` và các helper thực tế, không phải chương trình độc lập. Ý nghĩa là tạo **một physical transaction T** và thao tác trực tiếp với các savepoint trong T; callback kết thúc bình thường thì template cố commit, exception chưa được xử lý thì rollback theo rule được triển khai. Không phối trộn `TransactionTemplate`/savepoint với `@Transactional` một cách ngẫu nhiên khi chưa hiểu transaction propagation hiện có.

## 11. Một số giới hạn và tình huống dễ hiểu sai

### 11.1. Nested thành công không “bền vững” trước outer rollback

```java
@Transactional
public void outer() {
    nestedBean.stepSuccess(); // @Transactional(NESTED)
    throw new IllegalStateException("Fail outer");
}
```

Nested step chỉ release savepoint. Khi outer proxy nhận unchecked exception, **rollback T** vẫn hủy toàn bộ các SQL mà nested step đã thực hiện. Nếu audit/payment bắt buộc tồn tại độc lập, đó là yêu cầu có semantics khác `NESTED`.

### 11.2. Nested thất bại không tự động làm cả T rollback

```java
@Transactional
public void outer() {
    writeRequiredPart();
    try {
        nestedBean.optionalStep();  // NESTED, runtime failure
    } catch (OptionalFailure ex) {
        // Chấp nhận bỏ optional step.
    }
    writeRequiredCompletion();
}
```

Nếu đúng là `NESTED` có savepoint, lỗi đã đi qua nested interceptor, outer chấp nhận partial recovery, và DB còn committable, outer **có thể commit** hai bước bắt buộc. Nếu business invariant không cho phép mất optional step thì không nên catch để tiếp tục.

### 11.3. Catch bên trong nested method có thể làm savepoint không rollback

```java
@Transactional(propagation = Propagation.NESTED)
public void optionalStep() {
    insertOptionalData();
    try {
        validateOptionalData();
    } catch (IllegalArgumentException ignored) {
        // Interceptor không thấy exception.
    }
}
```

Nếu `validateOptionalData()` chỉ ném lỗi ứng dụng nhưng nested method trả về bình thường, transaction advice có thể release savepoint và giữ phần INSERT trong T. Dùng exception propagation hoặc đánh dấu rollback-only **tại nested status** khi muốn bỏ toàn bộ phần của scope.

### 11.4. Self-invocation không tạo scope mới

```java
@Service
public class WrongWorkflow {
    @Transactional
    public void outer() {
        inner();  // this.inner(), không qua proxy
    }

    @Transactional(propagation = Propagation.NESTED)
    public void inner() {
        // Không có nested interceptor riêng tại self-invocation.
    }
}
```

Với proxy mode mặc định, annotation trên `inner()` không được áp dụng cho lời gọi qua `this`. Tách sang bean khác để có ranh giới interceptor thật, hoặc chọn transaction API programmatic nếu logic phải nằm trong cùng class. Đổi JDK proxy sang CGLIB **không tự sửa** vấn đề self-invocation.

### 11.5. `final`, `private`, và không phải Spring bean

`@Transactional` thường được thực thi bằng proxy: method private, method final không thể advice theo cách class proxy override; hoặc object tạo bằng `new` ngoài Spring container không có transaction proxy. Với interface proxy, method cần là public và nằm trên proxied interface. Không thể kết luận một annotation sẽ mở nested scope nếu lời gọi chưa từng qua Spring transaction advice.

### 11.6. Isolation và lock không được “reset toàn cục”

Savepoint không tạo transaction riêng với isolation độc lập. Khi `NESTED` tham gia T, **T vẫn dùng chính isolation/connection của outer**. Tùy DBMS, rollback tới savepoint có thể giải phóng một số locks được lấy sau savepoint, nhưng nhiều locks/resources khác có quy tắc riêng. Không hứa rằng mọi lock sau mốc đó đều được trả về ở tất cả DB.

Outer transaction có thể vẫn giữ lock, connection và trạng thái transaction cho tới commit cuối, kể cả sau nhiều nested rollbacks. Việc thêm vô số savepoint không tự làm transaction ngắn hơn hoặc tăng throughput.

### 11.7. DDL và side effect ngoài DB

Một số DBMS có DDL gây implicit commit hoặc có semantics savepoint khác DML thông thường; không giả định có thể rollback mọi thao tác schema bằng savepoint. Tương tự, gửi email, gọi HTTP, đăng event lên hệ thống ngoài transaction manager, hay ghi file **không tự hoàn tác** khi rollback JDBC savepoint. Cần thiết kế outbox, idempotency hoặc compensation khi các side effect ấy là phần bắt buộc của nghiệp vụ.

### 11.8. Tạo savepoint rồi rollback về mốc cũ có ảnh hưởng gì tới savepoint mới?

Ở nhiều DBMS, rollback về savepoint cũ có thể làm **những savepoint được tạo sau nó** bị mất hiệu lực; phần thay đổi sau mốc cũng bị hủy. Spring quản lý thứ tự nested scopes và savepoint tương ứng. Với API thủ công, người lập trình phải quản lý rõ vòng đời tạo/rollback/release; đừng giữ tham chiếu mốc con rồi dùng lại sau khi transaction đã rollback về mốc cha, commit hoặc kết thúc.

## 12. Vì sao JPA/Hibernate cần cảnh giác đặc biệt?

Ví dụ JDBC/H2 phía trên dùng `JdbcTemplate` nên connection và database state khá trực quan. Với JPA:

- `JpaTransactionManager` mặc định **không bật** nested transaction (`nestedTransactionAllowed=false`).
- Việc cho phép savepoint JDBC khi có JPA transaction **không đồng nghĩa** với rollback đầy đủ state của `EntityManager`/first-level cache, entity đang managed hoặc pending flush.
- Một entity đã thay đổi trong persistence context có thể không tự trở lại giá trị như DB sau JDBC `ROLLBACK TO SAVEPOINT`, dẫn đến hành vi khó đoán nếu tiếp tục dùng EntityManager như bình thường.
- JPA không cung cấp mô hình nested transaction bằng JDBC savepoints một cách tổng quát. Không đổi flag rồi coi `@Transactional(NESTED)` của JPA repository sẽ có cùng semantics với `JdbcTemplate`.

Nếu kiến trúc là Spring Data JPA, hãy kiểm chứng manager/driver/persistence context cụ thể và cân nhắc **thiết kế lại transaction boundary** hoặc xử lý trường hợp phục hồi bằng bước nghiệp vụ tách biệt. Không lặng lẽ áp dụng mã JDBC này lên JPA rồi hứa cùng kết quả.

## 13. Debug nhiều savepoint và sự cố nested transaction

Nếu thấy `UnexpectedRollbackException`, `NestedTransactionNotSupportedException`, hoặc dữ liệu cuối khác kỳ vọng, hãy đi theo trình tự:

1. Xác nhận **đã có outer physical transaction T** trước khi nested method được gọi.
2. Xác nhận inner method dùng đúng `Propagation.NESTED`, không phải `REQUIRED` mặc định.
3. Kiểm tra inner method có **đi qua proxy** và là Spring bean thật không; không gọi `this.inner()`.
4. Kiểm tra `PlatformTransactionManager` đang chạy: `DataSourceTransactionManager`/`JdbcTransactionManager` hay JPA/JTA manager khác?
5. Xác minh driver/database hỗ trợ savepoint và nested transactions được manager cho phép.
6. Quan sát transaction logs để biết savepoint được tạo, release, rollback đến mốc nào. Nếu không thấy dấu hiệu nested transaction, kiểm tra lại interception và propagation.
7. Xác minh exception có **thoát qua nested interceptor** và khớp rollback rule không; nếu bị catch trong nested method, savepoint có thể được release.
8. Nếu outer catch lỗi, xác nhận **transaction T còn committable** hay đã bị mark rollback-only từ scope khác/SQL error.
9. Đọc DB **sau khi outer proxy đã commit/rollback**, không chỉ nhìn affected row count giữa transaction.
10. Khi có savepoint lồng nhau, kiểm tra liệu rollback của parent có hủy cả các thay đổi của child đã hoàn tất hay không.

Có thể thêm cấu hình log tạm thời:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.jdbc.datasource.DataSourceTransactionManager: DEBUG
```

Đây là phần bổ sung cho `application.yml`, không bắt buộc để chạy demo. Log level TRACE có thể gây lượng log lớn, nên chỉ bật trong môi trường debug và tránh đưa dữ liệu nhạy cảm vào log.

### Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Inner `NESTED` thất bại làm cả outer rollback | Inner thực tế chạy `REQUIRED`, DB/resource đã global rollback-only, hoặc outer rethrows lỗi | Xác nhận savepoint, proxy, manager và trạng thái T |
| `NestedTransactionNotSupportedException` | Manager không cho phép/hỗ trợ nested transaction | Dùng manager phù hợp; kiểm tra driver; không tự ép semantics |
| Inner thành công nhưng outer rollback thì dữ liệu inner mất | NESTED không có commit riêng | Đây là hành vi đúng; cần transaction độc lập mới có semantics khác |
| Child nested thành công nhưng parent nested rollback thì child mất | Parent savepoint được tạo trước child | Rollback về mốc cha xóa mọi thay đổi sau đó |
| Catch lỗi rồi nested vẫn giữ dữ liệu | Exception bị bắt trong nested, interceptor thấy return | Để lỗi thoát ra hoặc mark local rollback-only |
| `@Transactional(NESTED)` không có tác dụng | Gọi qua `this`, `new`, method không được advice | Tạo service bean và gọi qua proxy |
| JPA entity state không khớp sau savepoint | JDBC rollback không đồng bộ persistence context | Không áp dụng JDBC savepoint semantics trực tiếp lên JPA |
| Dùng `REQUIRES_NEW` thì một phần commit dù outer rollback | Inner có physical transaction riêng | Thiết kế lại theo business invariant; không thay propagation tùy tiện |
| Có SQL error, rollback savepoint không khôi phục được | DBMS/driver semantics hoặc lỗi connection | Kiểm tra DBMS cụ thể; rollback toàn T khi cần |
| Đọc giữa T thấy dữ liệu, sau commit không có | Dữ liệu tạm hoặc đã rollback về savepoint/outer | Assert sau khi transaction boundary kết thúc |
| Tạo quá nhiều savepoint, transaction kéo dài | Savepoint không rút ngắn duration T | Giảm scope/giữ transaction ngắn; xem pool và lock |
| Thao tác email/API không hoàn tác | Không thuộc JDBC transaction | Dùng outbox/idempotency/compensation |

## 14. Khi nào nên và không nên dùng `NESTED`?

### Phù hợp

- Một thao tác ngoài cùng phải commit nguyên khối **những bước được chấp nhận**, nhưng một vài bước con **được phép bỏ** khi validation thất bại.
- Các thao tác con đều dùng **cùng JDBC datasource/connection**; savepoint có thể rollback đúng phạm vi.
- Phạm vi con có ranh giới rõ ràng qua Spring proxy và có test tích hợp chứng minh dữ liệu đúng.
- Cần nhiều điểm khôi phục nhưng **không cần** inner commit độc lập trước outer.

### Không phù hợp hoặc cần cân nhắc kỹ

- Inner transaction **bắt buộc** commit dù outer fail: `NESTED` không đáp ứng.
- Hệ thống xử lý **đa datasource** và muốn atomicity toàn cục: savepoint một connection không tự phối hợp các tài nguyên.
- Logic cốt lõi không cho phép partial success: dùng `NESTED` + catch lỗi có thể làm nghiệp vụ sai dù transaction kỹ thuật commit hợp lệ.
- Chủ yếu thao tác JPA managed entities hoặc database/driver không hỗ trợ savepoint theo semantics cần thiết.
- Phần con gây side effects ra bên ngoài DB (email, HTTP, message broker): JDBC savepoint không hoàn tác các side effects đó.

Câu hỏi thiết kế quan trọng hơn “có hỗ trợ `NESTED` không?” là: **Khi một bước con thất bại, business có thực sự cho phép bỏ riêng bước đó, nhưng vẫn commit những bước còn lại không?** Nếu câu trả lời là “không”, hãy để toàn T rollback thay vì đưa vào savepoint một cách máy móc.

## 15. Bài tập tự luyện

### Bài tập 1: dự đoán trạng thái sau nhiều savepoint

Xét luồng:

```text
BEGIN T
  insert A
  SAVEPOINT S1
    insert B
    SAVEPOINT S2
      insert C
    RELEASE S2
    insert D
  ROLLBACK TO S1
  insert E
COMMIT T
```

**Đáp án:** A và E còn; B, C, D mất. Release S2 không commit C, và rollback S1 xóa tất cả thay đổi sau S1. Có đúng **một commit vật lý**.

### Bài tập 2: outer đổi thành rollback

Nếu thay `COMMIT T` bằng `ROLLBACK T` ở bài tập 1 thì còn những insert nào? **Không có insert nào được commit từ T**, kể cả A trước S1 và E sau rollback S1.

### Bài tập 3: checked exception

Một method `@Transactional(NESTED)` viết bản ghi rồi ném `IOException`. Outer catch rồi commit; mặc định Spring 6.1 có rollback về savepoint không? **Không tự động** nếu exception không khớp rollback rules. Muốn rollback riêng inner, khai báo `rollbackFor = IOException.class`.

### Bài tập 4: self-invocation

`outer()` và `inner()` nằm trong cùng bean; `outer()` gọi trực tiếp `inner()` trong Spring proxy mode. Có tự sinh savepoint cho `inner()` không? **Không**, nếu lời gọi bỏ qua proxy. Cần một bean khác hoặc transaction API programmatic.

### Bài tập 5: chọn propagation

Bạn muốn ghi audit độc lập ngay cả khi đơn hàng outer rollback. Chọn `NESTED` có đủ không? **Không**. Cần một chiến lược cho audit độc lập phù hợp, có thể dùng `REQUIRES_NEW` với caveat connection/atomicity, hoặc outbox theo consistency requirements.

## 16. Checklist triển khai thực tế

1. Ghi rõ transaction **ngoài cùng** và các scope con được phép partial rollback.
2. Xác nhận cùng `DataSource`, đúng `PlatformTransactionManager`, driver hỗ trợ `Savepoint`.
3. Dùng `@Transactional(propagation = NESTED)` ở method public được gọi qua **Spring bean proxy**.
4. Nhớ `NESTED` khi không có outer T sẽ tạo T mới như `REQUIRED`.
5. Định nghĩa exception nào được rollback về savepoint; với checked exception cần rule minh thị nếu default chưa phù hợp.
6. Catch lỗi **sau nested interceptor** tại outer nếu muốn tiếp tục; không nuốt lỗi bên trong nested rồi kỳ vọng tự rollback.
7. Nếu nested parent rollback, tất cả nested child changes **sau mốc parent** cũng rollback, dù child đã thành công.
8. Không coi `releaseSavepoint` là commit. Mọi thay đổi chỉ bền vững nếu outer physical T commit.
9. Không coi savepoint là công cụ khôi phục side effect ngoài database hoặc trạng thái JPA persistence context.
10. Test bằng database sau khi proxy method hoàn tất: inner fail, inner success, parent nested fail, outer fail, standalone nested.
11. Khi thấy lỗi unexpected rollback, kiểm tra có participating `REQUIRED`, global rollback-only hoặc DB error ngoài nested scope hay không.
12. Giữ T ngắn, quản lý lock/connection cẩn thận và ưu tiên business invariant hơn sự tiện lợi của một propagation setting.

## Tài liệu tham khảo

- Spring Framework — **Transaction Propagation** (`REQUIRED`, `REQUIRES_NEW`, `NESTED`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **Declarative Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — **Rolling Back a Declarative Transaction**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework Javadoc — **`DataSourceTransactionManager`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework Javadoc — **`Propagation.NESTED`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Propagation.html
- Spring Framework Javadoc — **`SavepointManager`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/SavepointManager.html
- Spring Framework Javadoc — **`JpaTransactionManager`** (JPA persistence context caveat): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html