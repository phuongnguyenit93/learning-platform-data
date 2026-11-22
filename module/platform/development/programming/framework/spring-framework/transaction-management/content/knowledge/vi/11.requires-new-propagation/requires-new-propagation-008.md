# Kiểm chứng REQUIRES_NEW so với REQUIRED bằng dữ liệu thực

## 1. Câu hỏi trung tâm

Hai phương thức cùng ghi vào database, cùng được Spring đánh dấu `@Transactional`, nhưng kết quả **commit/rollback khác nhau** khi inner method dùng `Propagation.REQUIRED` hoặc `Propagation.REQUIRES_NEW`. Chúng khác nhau ở điều gì, và làm sao chứng minh bằng **dữ liệu đã commit**, chứ không chỉ đoán từ tên annotation?

- **`REQUIRED`**: nếu outer đã có transaction vật lý phù hợp, inner **tham gia transaction đó**. Một lỗi buộc rollback của inner có thể khiến cả transaction chung bị rollback. Inner thành công cũng không tự commit trước outer.
- **`REQUIRES_NEW`**: inner luôn yêu cầu **transaction vật lý độc lập**, tạm đình chỉ transaction hiện hữu của outer trong thời gian inner chạy. Inner có thể commit/rollback độc lập; kết quả đã commit của inner **không tự bị hủy** khi outer rollback về sau.

Hãy ghi nhớ một đối chiếu:

```text
A. REQUIRED
Outer transaction T1: [INSERT outer] -> Inner REQUIRED [INSERT inner] -> Outer error
                                  \_____________ chung T1 _____________/
T1 rollback -> KHÔNG còn record outer hoặc inner.

B. REQUIRES_NEW
Outer transaction T2: [INSERT outer] -- suspend --+             +-- resume -- Outer error
                                                  |             |
Inner REQUIRES_NEW:                       T3 [INSERT inner] -> COMMIT T3
Outer T2 rollback -> outer mất, inner của T3 VẪN CÒN.
```

Bài thuộc nhóm **REQUIRES_NEW** trong Spring Framework — transaction management; đề bài trực tiếp là **“Kiểm chứng lựa chọn này so với REQUIRED bằng dữ liệu thực”**. Mục tiêu không chỉ định nghĩa hai propagation mode mà là xây dựng thí nghiệm có dữ liệu đầu vào, câu SQL, exception ở những ranh giới khác nhau, expected output và giải thích kết quả.

Sau bài này, bạn có thể:

1. Phân biệt logical transaction scope và physical transaction; hiểu ý nghĩa suspend/resume của `REQUIRES_NEW`.
2. Dự đoán kết quả DB khi **outer rollback sau inner thành công**, hoặc **inner rollback nhưng outer catch lỗi**.
3. Tự dựng ứng dụng **Java 17+, Spring Boot, Spring JDBC, H2**, chạy đủ các kịch bản với nhiều service bean để proxy thực sự được dùng.
4. Đọc bảng các dòng còn tồn tại sau transaction và giải thích vì sao kết quả của `REQUIRED` và `REQUIRES_NEW` khác nhau.
5. Biết khi nào nên dùng transaction độc lập, khi nào nó phá vỡ atomicity nghiệp vụ, cũng như chi phí connection pool và lock.
6. Kiểm thử lại trên hệ thống thật mà không bị `@Transactional` của test, self-invocation hoặc query trong transaction chưa commit đánh lừa.

## 2. Hai loại transaction cần tách bạch

### 2.1. Logical transaction scope

Mỗi lần đi qua transaction advice cho phương thức `@Transactional`, Spring có thể thiết lập một **logical scope**. Scope ấy chứa transaction attributes, rollback rules và trạng thái được dùng khi lời gọi method return hoặc ném exception.

Khi outer gọi inner qua **Spring proxy của một bean khác**, thường có hai logical scope: scope ngoài cho outer và scope trong cho inner. **Số scope logic không quyết định số transaction vật lý.**

### 2.2. Physical transaction

Physical transaction là transaction thật được DB/transaction manager điều phối qua connection, với commit/rollback cụ thể. Trong demo JDBC này, một `DataSourceTransactionManager` làm việc với một `DataSource` H2.

- Với `REQUIRED`, hai scope logic thường ánh xạ vào **một physical transaction** trên cùng managed connection.
- Với `REQUIRES_NEW`, inner mở **physical transaction mới**; Spring tạm đình chỉ resource context của outer và khôi phục sau khi inner kết thúc.
- Inner `REQUIRES_NEW` không phải savepoint của outer. Nếu inner commit xong, outer rollback sau đó **không thể undo commit ấy**.
- Một transaction mới chỉ thực sự độc lập đối với manager/tài nguyên phù hợp; email, HTTP, Kafka hay CSDL khác không tự được local manager bao phủ.

Sơ đồ:

```text
REQUIRED
caller
  |
outer proxy -> BEGIN T_outer
  |  outer INSERT
  +--> inner proxy REQUIRED -> join T_outer
  |        inner INSERT / exception
  +<-- inner returns
  |  outer returns / exception
outer proxy -> COMMIT hoặc ROLLBACK T_outer

REQUIRES_NEW
caller
  |
outer proxy -> BEGIN T_outer
  |  outer INSERT (chưa commit)
  +--> inner proxy REQUIRES_NEW
  |       suspend T_outer
  |       BEGIN T_inner trên resource riêng
  |       inner INSERT
  |       COMMIT hoặc ROLLBACK T_inner
  |       resume T_outer
  +<-- inner returns / exception
  |  outer returns / exception
outer proxy -> COMMIT hoặc ROLLBACK T_outer
```

**Đây là lý do không thể chỉ nhìn method có `@Transactional` hay không để suy luận atomicity.** Phải xác định propagation, đã có transaction ở caller chưa, method có được intercept không, manager nào được dùng và lỗi được xử lý ở scope nào.

## 3. Bảng giả thuyết trước khi chạy

Ta đặt các INSERT vào **những id khác nhau**, để không gây xung đột khóa/unique constraint do dùng cùng record. Các kịch bản dùng tên A đến F:

| Kịch bản | Inner propagation | Điều gì xảy ra? | Outer row sau cùng | Inner row sau cùng |
| --- | --- | --- | --- | --- |
| **A** | `REQUIRED` | Inner INSERT thành công; outer ném runtime exception | 0 | 0 |
| **B** | `REQUIRES_NEW` | Inner INSERT, commit; outer ném runtime exception | 0 | **1** |
| **C** | `REQUIRED` | Inner INSERT rồi ném runtime exception; outer **catch và return** | 0 | 0 |
| **D** | `REQUIRES_NEW` | Inner INSERT rồi ném runtime exception; outer **catch và return** | **1** | 0 |
| **E** | `REQUIRES_NEW` | Cả inner và outer đều thành công | **1** | **1** |
| **F** | `REQUIRED` và `REQUIRES_NEW` gọi trực tiếp không có outer | Mỗi method tự mở transaction khi chưa có transaction hiện hành | Không áp dụng | Mỗi method 1 |

**Lý do quan trọng nhất để kiểm chứng C và D:** một exception runtime từ inner `REQUIRED` có thể đánh dấu **transaction chung rollback-only**, dù outer đã catch rồi return. Với `REQUIRES_NEW`, exception gây rollback **inner transaction riêng**; nếu outer catch và không tự lỗi, outer vẫn có thể commit.

Kết quả trên giả định hành vi mặc định của Spring transaction manager: rollback cho `RuntimeException` và `Error`; `REQUIRED` tham gia cùng transaction; `REQUIRES_NEW` tạo transaction riêng; không có side effect ngoài database và không có lỗi tài nguyên khác. Phần demo sẽ chứng minh từng dòng bằng truy vấn SQL sau khi các method transaction đã kết thúc.

## 4. Tại sao “outer rollback sau inner commit” lại có thể xảy ra?

Với `REQUIRES_NEW`, transaction manager phải:

1. Nhận biết transaction T của outer đã active.
2. **Suspend** trạng thái/tài nguyên T của outer khỏi context của thread hiện tại. T không bị commit hay rollback chỉ vì suspend.
3. Bắt đầu transaction T2 cho inner; trên JDBC thường sử dụng **connection khác** trong cùng pool.
4. Chạy inner, commit hoặc rollback T2 theo outcome của inner.
5. Cleanup context của T2, **resume** T của outer.
6. Cho outer tiếp tục; khi outer kết thúc mới xử lý T riêng của nó.

Vì T2 là physical transaction độc lập, nếu T2 đã commit và sau đó T rollback, các row của T2 vẫn tồn tại. **Không có cơ chế “gộp” transaction độc lập vào outer tại thời điểm outer commit.**

Ngược lại, `REQUIRED` chỉ mở inner **logical scope** tham gia cùng T. Inner method return thành công không có commit vật lý mới; T có thể bị outer rollback toàn bộ.

Trong test, nếu bạn query row bên trong transaction T, có thể nhìn thấy dữ liệu chưa commit do chính T ghi (*read your writes*). Việc “đọc thấy” chưa chứng minh dữ liệu đã được commit. Ta sẽ đọc bằng runner sau khi proxy trả về để kiểm tra **trạng thái cuối của DB**.

## 5. Dự án mẫu runnable: Java 17, Spring Boot, JDBC và H2

Dự án này dùng **Spring Boot 3.3.13**, Spring JDBC và H2 in-memory. Spring Boot quản lý `DataSource`; chúng ta khai báo một `DataSourceTransactionManager` tường minh và bật xử lý `@Transactional`. Để tránh tự tạo object ngoài container, outer service và inner service đều là Spring bean được inject.

Đây là một project Gradle hoàn chỉnh cho demo, không cần chạy HTTP server hay dịch vụ ngoài. Version được ghim nhằm tái hiện hành vi, không có nghĩa nó là phiên bản phù hợp nhất cho production ở mọi thời điểm.

### 5.1. Cấu trúc thư mục

```text
compare-propagation/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/example/propagation/
        │   ├── PropagationApplication.java
        │   ├── OuterService.java
        │   └── InnerService.java
        └── resources/
            ├── application.properties
            └── schema.sql
```

Tất cả các class Java có package `example.propagation`, cùng phạm vi component scan của application.

**`settings.gradle`**

```groovy
rootProject.name = 'compare-propagation'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    runtimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-jdbc` cung cấp JDBC, `JdbcTemplate` và Spring transaction support. `spring-boot-starter-aop` bảo đảm hạ tầng AOP cần cho các proxy. H2 chạy trong bộ nhớ, nên mỗi lần khởi động sạch là một phép thử độc lập.

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:propagation_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
spring.main.web-application-type=none
```

**Vì sao `maximum-pool-size=5`?** Outer `REQUIRES_NEW` thường giữ connection của T_outer trong lúc inner cần một connection khác để chạy T_inner. Pool chỉ có 1 connection có thể làm inner chờ đến timeout và khiến bài không chạy như dự kiến. 5 connection đủ cho **demo tuần tự một runner**; trong production phải sizing theo concurrency thực tế, không lấy con số 5 làm khuyến nghị chung.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_event (
    id INT PRIMARY KEY,
    label VARCHAR(80) NOT NULL
);
```

Mỗi ca dùng id riêng để kiểm chứng bằng `SELECT COUNT(*)`. Không update cùng một record trong outer và inner để tránh demo vô tình biến thành bài test tranh chấp row lock. H2 transaction đảm bảo ta thấy khác biệt commit/rollback, còn tham số pool đảm bảo inner có thể xin thêm connection.

### 5.2. InnerService — hai propagation mode và hai cách lỗi

**`src/main/java/example/propagation/InnerService.java`**

```java
package example.propagation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void requiredInsert(int id) {
        printStatus("inner REQUIRED");
        insert(id, "required-ok");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void requiresNewInsert(int id) {
        printStatus("inner REQUIRES_NEW");
        insert(id, "new-ok");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void requiredInsertAndFail(int id) {
        printStatus("inner REQUIRED_FAIL");
        insert(id, "required-fail");
        throw new IllegalStateException("inner-fail");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void requiresNewInsertAndFail(int id) {
        printStatus("inner REQUIRES_NEW_FAIL");
        insert(id, "new-fail");
        throw new IllegalStateException("inner-fail");
    }

    private void insert(int id, String label) {
        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            id, label
        );
    }

    private static void printStatus(String label) {
        boolean newTx = TransactionAspectSupport
            .currentTransactionStatus()
            .isNewTransaction();
        System.out.println(label + " newTx=" + newTx);
    }
}
```

Bốn public method là entry point transaction, đều không final và nằm trên bean. `printStatus` được gọi **bên trong** invocation đã có transaction advice. Trong demo:

- Inner `REQUIRED` được outer gọi khi T_outer đã có: `isNewTransaction() == false`.
- Inner `REQUIRES_NEW` được outer gọi: `isNewTransaction() == true` vì nó mở physical transaction riêng.
- Khi runner gọi trực tiếp `inner.requiredInsert(...)` không có transaction ngoài, ngay cả `REQUIRED` cũng cho `isNewTransaction() == true`.

**Đừng hiểu `isNewTransaction()` là DB transaction ID.** Nó cho biết transaction status của logical scope do Spring tạo có sở hữu một transaction mới hay không. Chứng cứ quyết định về tính độc lập là dữ liệu còn lại khi outer rollback và inner đã commit.

Hai method `*AndFail` luôn INSERT rồi ném unchecked `IllegalStateException`. Default rollback rule của Spring xử lý exception đi qua transaction interceptor. Nếu exception được ném **trước** INSERT, count bằng 0 sẽ không chứng minh rollback; vì vậy đặt INSERT trước là chủ đích.

### 5.3. OuterService — tạo bốn cặp hành vi để so sánh

**`src/main/java/example/propagation/OuterService.java`**

```java
package example.propagation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    // A: REQUIRED của inner tham gia T_outer.
    // Outer lỗi sau inner thành công -> cả hai rollback.
    @Transactional
    public void requiredThenOuterFails() {
        insert(11, "outer-A");
        inner.requiredInsert(12);
        throw new IllegalStateException("outer-fail");
    }

    // B: REQUIRES_NEW commit riêng trước khi outer lỗi.
    @Transactional
    public void requiresNewThenOuterFails() {
        insert(21, "outer-B");
        inner.requiresNewInsert(22);
        throw new IllegalStateException("outer-fail");
    }

    // C: Inner REQUIRED lỗi -> transaction chung rollback-only.
    // Outer bắt lỗi và return, nhưng commit outer vẫn thất bại.
    @Transactional
    public void requiredFailureCaught() {
        insert(31, "outer-C");
        try {
            inner.requiredInsertAndFail(32);
        } catch (IllegalStateException ex) {
            System.out.println("C inner caught=" + ex.getMessage());
        }
        System.out.println("C outer finished body");
    }

    // D: Inner REQUIRES_NEW lỗi, chỉ transaction inner rollback.
    // Outer đã catch và không tự lỗi -> transaction outer commit.
    @Transactional
    public void requiresNewFailureCaught() {
        insert(41, "outer-D");
        try {
            inner.requiresNewInsertAndFail(42);
        } catch (IllegalStateException ex) {
            System.out.println("D inner caught=" + ex.getMessage());
        }
    }

    // E: Cả outer và inner NEW đều thành công.
    @Transactional
    public void bothCommit() {
        insert(51, "outer-E");
        inner.requiresNewInsert(52);
    }

    private void insert(int id, String label) {
        jdbc.update(
            "INSERT INTO tx_event(id, label) VALUES (?, ?)",
            id, label
        );
    }
}
```

**Giải thích cấu trúc để proxy hoạt động:**

- `OuterService` được runner gọi từ bean khác qua Spring AOP proxy; `@Transactional` mặc định là `REQUIRED` nên mỗi lời gọi outer mới bắt đầu một physical transaction khi runner chưa có T.
- `inner` là một bean `InnerService` được constructor-inject vào outer. Các lời gọi `inner.method()` đi qua **proxy của một bean khác**, để transaction interceptor thực sự áp dụng `REQUIRED` hoặc `REQUIRES_NEW`.
- `insert` là private helper chạy bên trong transaction đã mở của method public; nó không cần `@Transactional` riêng.
- Không gọi `new InnerService(jdbc)` hoặc `this.requiresNewInsert(...)` trong cùng bean rồi kỳ vọng propagation đổi được. Self-invocation trong proxy mode sẽ bỏ qua advice cho inner method.
- Tất cả INSERT dùng cùng `JdbcTemplate`, tức cùng `DataSource` và transaction manager, nhưng connection giao dịch là khác nhau khi inner yêu cầu `REQUIRES_NEW`.

### 5.4. Application — chạy và đọc dữ liệu đã kết thúc transaction

**`src/main/java/example/propagation/PropagationApplication.java`**

```java
package example.propagation;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class PropagationApplication {
    public static void main(String[] args) {
        SpringApplication.run(PropagationApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner verify(
            OuterService outer, InnerService inner, JdbcTemplate jdbc) {
        return args -> {
            // A — inner REQUIRED success, outer rollback.
            try {
                outer.requiredThenOuterFails();
            } catch (IllegalStateException ex) {
                System.out.println("A caught=" + ex.getMessage());
            }
            showCounts(jdbc, "A", 11, 12);

            // B — inner REQUIRES_NEW commits, outer rolls back.
            try {
                outer.requiresNewThenOuterFails();
            } catch (IllegalStateException ex) {
                System.out.println("B caught=" + ex.getMessage());
            }
            showCounts(jdbc, "B", 21, 22);

            // C — inner REQUIRED rolls back, outer catches exception.
            try {
                outer.requiredFailureCaught();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "C caught=" + ex.getClass().getSimpleName());
            }
            showCounts(jdbc, "C", 31, 32);

            // D — inner REQUIRES_NEW rolls back; outer commits.
            outer.requiresNewFailureCaught();
            showCounts(jdbc, "D", 41, 42);

            // E — both transaction scopes commit.
            outer.bothCommit();
            showCounts(jdbc, "E", 51, 52);

            // F — no outer transaction, both modes start a new one.
            inner.requiredInsert(61);
            inner.requiresNewInsert(62);
            showCounts(jdbc, "F", 61, 62);
        };
    }

    private static void showCounts(
            JdbcTemplate jdbc, String label, int outerId, int innerId) {
        int first = count(jdbc, outerId);
        int second = count(jdbc, innerId);
        System.out.println(
            label + " rows first=" + first + " second=" + second);
    }

    private static int count(JdbcTemplate jdbc, int id) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_event WHERE id = ?",
            Integer.class, id
        );
        return result;
    }
}
```

`@SpringBootApplication` quét `OuterService` và `InnerService` cùng package. `@EnableTransactionManagement` bật annotation-driven proxy transaction; Spring Boot ở nhiều cấu hình cũng có thể tự kích hoạt, nhưng ví dụ khai báo tường minh để ranh giới học tập rõ. `transactionManager` là bean được transaction advice dùng và điều phối cùng `DataSource` của `JdbcTemplate`.

Quan trọng nhất: `CommandLineRunner` **không được `@Transactional` đánh dấu**. Các phép `showCounts` xảy ra **sau khi lời gọi outer/inner đã trở về hoặc ném exception qua proxy**, nên DB đã được yêu cầu commit/rollback. Không kết luận từ giá trị query khi outer transaction còn mở.

### 5.5. Cách chạy

Cần JDK 17+ và Gradle 8.x tương thích, mạng để lấy dependency lần đầu. Ở thư mục `compare-propagation`:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper tương thích, chạy `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Không dùng `javac` với JDK classpath thuần vì chương trình phụ thuộc Spring và H2; Gradle tải dependency, compile rồi chạy ứng dụng.

Mỗi lần khởi động mới dùng H2 in-memory; nếu chạy lại trong cùng JVM hoặc đổi cấu hình để database tồn tại lâu, hãy đảm bảo xóa bảng/record kiểm thử để tránh trùng primary key. Ở bản demo, 12 giá trị id khác nhau và không có xung đột giữa các scenario.

### 5.6. Stdout dự kiến, theo đúng thứ tự

Bỏ qua log của Gradle, Spring Boot, Hikari và startup. Các dòng được các lệnh `System.out.println` in ra (một lần chạy mới với DB sạch) là:

```text
inner REQUIRED newTx=false
A caught=outer-fail
A rows first=0 second=0
inner REQUIRES_NEW newTx=true
B caught=outer-fail
B rows first=0 second=1
inner REQUIRED_FAIL newTx=false
C inner caught=inner-fail
C outer finished body
C caught=UnexpectedRollbackException
C rows first=0 second=0
inner REQUIRES_NEW_FAIL newTx=true
D inner caught=inner-fail
D rows first=1 second=0
inner REQUIRES_NEW newTx=true
E rows first=1 second=1
inner REQUIRED newTx=true
inner REQUIRES_NEW newTx=true
F rows first=1 second=1
```

Đây là **expected output** theo code và behavior chuẩn của `DataSourceTransactionManager`, không phải bản chép từ một lượt thực thi. Khi ứng dụng chạy đúng precondition, các dòng count là bằng chứng về trạng thái đã commit/rollback. Nếu kết quả khác, xem phần chẩn đoán: proxy, manager, resource, connection pool, transaction của runner hoặc việc database chưa sạch.

## 6. Diễn giải từng ca kiểm chứng bằng dữ liệu thực

### 6.1. A — REQUIRED inner thành công, outer rollback: cả hai mất

`outer.requiredThenOuterFails()`:

1. Outer mở T_A, INSERT id 11.
2. Inner `REQUIRED` nhìn thấy T_A đã tồn tại, **tham gia cùng T_A**, in `newTx=false`, INSERT id 12.
3. Inner return, chỉ hoàn thành logical scope — **chưa commit** id 12.
4. Outer ném `IllegalStateException` đi qua interceptor, Spring yêu cầu rollback T_A.
5. Runner bắt exception và query id 11, 12 sau rollback: **0 và 0**.

Trong thực tế, đây là kết quả mong muốn khi “tạo đơn” và “ghi tồn kho” phải cùng thành công. Bất kỳ bước nào thuộc cùng một unit of work thất bại đều khiến toàn bộ giao dịch hủy.

**Điều được chứng minh:** `REQUIRED` không tách kết quả inner thành commit độc lập; nó **phụ thuộc kết quả transaction vật lý của outer**.

### 6.2. B — REQUIRES_NEW inner commit, outer rollback: dữ liệu inner vẫn còn

`outer.requiresNewThenOuterFails()`:

1. Outer mở T_B, INSERT id 21, **chưa commit**.
2. Inner `REQUIRES_NEW` tạm suspend T_B, lấy resource/connection mới, mở T_B2 và in `newTx=true`.
3. Inner INSERT id 22 vào T_B2 rồi return bình thường. Spring **commit T_B2**; id 22 bền vững.
4. Outer resume T_B và ném `IllegalStateException`. Spring rollback T_B; id 21 biến mất.
5. Runner query: **id 21 = 0, id 22 = 1**.

**Điều được chứng minh:** outer rollback không “đè” được transaction inner đã commit. Đây là kiểm chứng rõ nhất về khả năng commit độc lập của `REQUIRES_NEW`. Nó không phải “REQUIRED nhưng ưu tiên chạy trước”; đó là một physical transaction thực sự tách biệt.

Một câu hỏi nghiệp vụ quan trọng: liệu sau khi đơn hàng thất bại có hợp lệ khi bản ghi inner vẫn tồn tại? Với log kiểm toán độc lập, có thể **có**. Với trừ tồn kho cho đơn thất bại, nhiều hệ thống sẽ coi đây là **lỗi nhất quán** nếu không có bù trừ.

### 6.3. C — REQUIRED inner lỗi, outer catch: rollback-only phá commit ngoài

`outer.requiredFailureCaught()`:

1. Outer mở T_C, INSERT id 31.
2. Inner `REQUIRED` tham gia T_C, INSERT id 32 rồi ném `IllegalStateException`.
3. Inner transaction interceptor nhận exception runtime và đánh dấu transaction chung **rollback-only** theo hành vi mặc định.
4. Outer `catch` được exception và in `C outer finished body`; code Java của outer đã hoàn tất bình thường.
5. Outer transaction interceptor cố commit T_C, phát hiện rollback-only, rollback và ném `UnexpectedRollbackException`.
6. Runner bắt `UnexpectedRollbackException`; id 31 và 32 đều **0**.

**Điều được chứng minh:** với `REQUIRED`, inner rollback rule có thể tác động cả physical transaction của outer. `catch` ở outer **không tự xóa cờ rollback-only**. Spring ném `UnexpectedRollbackException` để caller không tưởng rằng outer đã commit khi thực tế rollback.

Đây là hành vi tiêu biểu của `AbstractPlatformTransactionManager` mặc định với participating transaction. Nếu ứng dụng đổi cờ transaction manager, dùng rule ngoại lệ khác hoặc inner không qua proxy, kết quả có thể khác; đó là lý do test cần xác minh môi trường thực.

### 6.4. D — REQUIRES_NEW inner lỗi, outer catch: outer commit

`outer.requiresNewFailureCaught()`:

1. Outer mở T_D, INSERT id 41.
2. Inner suspend T_D, mở T_D2 độc lập, INSERT id 42.
3. Inner ném `IllegalStateException`. Transaction interceptor rollback T_D2; id 42 không còn.
4. Spring resume T_D và rethrow exception cho outer. Outer catch và return bình thường.
5. T_D không tự bị đánh dấu rollback-only chỉ vì inner T_D2 rollback; outer có thể commit id 41.
6. Runner query: **id 41 = 1, id 42 = 0**.

**Điều được chứng minh:** inner `REQUIRES_NEW` rollback **không tự lan** cờ rollback-only sang outer physical transaction. Tuy nhiên, nếu outer **không bắt exception**, exception runtime tiếp tục thoát qua outer interceptor, lúc đó **outer vẫn rollback theo rollback rule của chính outer**. `REQUIRES_NEW` không giúp outer miễn nhiễm với exception được truyền ra ngoài.

### 6.5. E — Cả hai thành công: kết quả cùng còn nhưng không phải một transaction

`outer.bothCommit()` INSERT id 51, inner `REQUIRES_NEW` INSERT/commit id 52, rồi outer commit id 51. Kết quả **1/1** nhìn giống một unit of work `REQUIRED` thành công.

Nhưng **trạng thái cuối giống nhau không chứng minh atomicity giống nhau**. Chỉ khi chủ động tạo lỗi ở những ranh giới khác nhau (A–D) ta mới thấy khác biệt quan trọng: REQUIRES_NEW có thể để lại **partial success** khi một transaction lỗi.

### 6.6. F — Không có outer transaction: cả hai cùng tạo transaction mới

Runner gọi trực tiếp `inner.requiredInsert(61)` và `inner.requiresNewInsert(62)`, khi không có transaction bên ngoài. Cả hai đều in `newTx=true` và commit row của mình; count **1/1**.

Vì thế, nếu chỉ test `REQUIRED` và `REQUIRES_NEW` khi không có outer transaction, bạn dễ kết luận “chúng giống nhau”. **Điểm phân biệt chỉ thể hiện khi có transaction hiện hữu** và cách xử lý scope/outcome khác nhau.

## 7. Bảng chéo: ai lỗi, ai catch, DB còn gì?

Một bản đồ quyết định ngắn:

| Outer | Inner | Propagation inner | Outer có catch inner exception? | Kết quả điển hình |
| --- | --- | --- | --- | --- |
| Ném RuntimeException sau inner success | Success | REQUIRED | Không liên quan | Cả outer và inner rollback |
| Ném RuntimeException sau inner success | Success | REQUIRES_NEW | Không liên quan | Inner đã commit; outer rollback |
| Return bình thường | RuntimeException | REQUIRED | Có | Shared transaction rollback-only; outer thường gặp `UnexpectedRollbackException` |
| Return bình thường | RuntimeException | REQUIRES_NEW | Có | Inner rollback, outer commit được |
| Return bình thường | RuntimeException | REQUIRES_NEW | **Không** | Exception thoát qua outer proxy, nên outer cũng có thể rollback |
| Return bình thường | Success | REQUIRED | Không áp dụng | Một physical transaction commit chung |
| Return bình thường | Success | REQUIRES_NEW | Không áp dụng | Hai physical transactions commit độc lập |
| Không có outer transaction | Success | Bất kỳ mode nào | Không áp dụng | Mode tự tạo physical transaction của nó |

Điểm tinh tế ở hàng **inner REQUIRES_NEW thất bại nhưng outer không catch**: hai transactions độc lập về mặt manager, nhưng outer vẫn có thể rollback do **exception propagation trong Java**. Độc lập physical transaction không đồng nghĩa độc lập điều khiển luồng chương trình.

## 8. Đo lường kết quả DB cho đúng: “real data”, không chỉ active flag

### 8.1. Vì sao `isNewTransaction()` chưa đủ?

`TransactionAspectSupport.currentTransactionStatus().isNewTransaction()` cho thấy invocation hiện tại có transaction mới hay tham gia transaction đã có. Nhưng flag này:

- Không phải transaction ID do database cung cấp.
- Không chứng minh câu SQL đã commit.
- Không xác nhận thao tác của hệ thống khác cùng tham gia.
- Có thể bị hiểu nhầm nếu gọi ngoài transaction-advised method hoặc có manager/transaction scope khác.

Trong bài, flag đóng vai trò **giải thích cơ chế**, còn kết quả thật dựa trên `SELECT COUNT(*)` **sau khi outer/inner hoàn tất**.

### 8.2. Query khi outer vẫn active có thể đánh lừa

Một outer transaction thường thấy row mình vừa ghi dù chưa commit. Nếu query bằng cùng connection trong outer, count có thể là 1; nhưng rollback phía sau khiến kết quả thực tế là 0.

Vì vậy, demo đặt `showCounts` trong runner không có transaction, **sau return hoặc catch exception từ proxy**. Đọc ở thời điểm này cho phép phân biệt dữ liệu đã được commit và dữ liệu đã bị rollback trong mỗi kịch bản.

### 8.3. Cần tách lỗi SQL, business exception và commit exception

Một exception từ JDBC ở giữa transaction có thể gây rollback theo mặc định vì `DataAccessException` là unchecked. Nhưng exception xảy ra **sau khi inner đã commit** sẽ không undo transaction inner. Khi lỗi mất ACK ở commit và kết quả chưa xác định, không suy luận từ exception rằng DB chắc chắn đã rollback; cần truy vấn trạng thái nghiệp vụ, idempotency key và đối soát nếu quan trọng.

### 8.4. Kiểm chứng isolation thật có thể khó hơn demo

H2 cho phép tạo giao dịch mới trên connection khác, nhưng nếu inner transaction thử đọc record outer mới INSERT mà chưa commit, nó **thường không thấy** thay đổi đó dưới isolation thông dụng. Nó không có snapshot thần kỳ vượt qua transaction isolation. Nếu inner cập nhật cùng row đang bị outer khóa, inner có thể bị chặn hoặc timeout vì outer đang suspend nhưng chưa nhả lock. Vì thế demo **chủ ý dùng các id độc lập**, để phép đo chỉ kiểm tra propagation.

Trong production, isolation, locking, constraint và timeout của database có thể tạo thêm kết quả khác. Khi mở rộng test, luôn nêu rõ mức isolation và tài nguyên nào đang bị khóa.

## 9. Những tình huống có thể khiến REQUIRES_NEW thành lựa chọn sai

### 9.1. Trừ tồn kho rồi outer thất bại

Ví dụ đơn hàng:

```java
@Transactional
public void placeOrder() {
    orders.insertPending();
    inventory.reserveIndependently(); // @Transactional(REQUIRES_NEW)
    chargeCard();
    throw new IllegalStateException("checkout failed");
}
```

Đây là mã minh họa, thiếu dependency/implementation. Nếu `reserveIndependently` commit tồn kho trong inner T2, outer DB transaction rollback không đảo ngược tồn kho. Ngay cả khi `chargeCard` là thao tác ngoài DB, transaction của Spring cũng không tự hoàn tác thanh toán.

Nếu business invariant đòi hỏi tồn kho và đơn hàng cùng thành công trong **một CSDL**, việc inner `REQUIRED` tham gia outer transaction có thể phù hợp hơn. Với nhiều hệ thống phân tán, cần workflow và compensation; không dùng `REQUIRES_NEW` như cách thay thế cơ chế đảm bảo nhất quán.

### 9.2. Audit log độc lập có thể là use case hợp lý

Một trường hợp khác:

```java
@Transactional
public void createOrder() {
    try {
        persistOrder();
        // Nghiệp vụ thất bại...
        throw new IllegalStateException("cannot create");
    } finally {
        auditService.recordAttempt();
    }
}
```

Nếu `auditService.recordAttempt()` được proxy intercept với `REQUIRES_NEW`, nó **có thể commit riêng** log sự kiện ngay cả khi transaction đơn hàng rollback. Điều này có thể là **mục đích thiết kế** khi cần lưu dấu các attempt thất bại.

Tuy nhiên, đoạn mã là minh họa chưa có implementation; cần làm rõ thứ tự, xử lý lỗi audit, việc log gửi đi ngoài database, connection pool và constraint. Nếu audit method ném exception, nó có thể che exception chính; cần chính sách logging/failure handling cẩn thận.

Audit độc lập không tự giải quyết việc gửi Kafka/email đáng tin. Muốn phát sự kiện gắn với transaction DB, hãy cân nhắc transactional outbox; muốn ghi attempt thất bại bền vững, transaction độc lập hoặc hệ thống audit chuyên dụng phải được thiết kế và kiểm thử riêng.

### 9.3. Kết quả partial commit không phải bug của Spring

Một số người xem “outer rollback mà inner vẫn còn record” là lỗi transaction. Thực ra đó **chính là semantics `REQUIRES_NEW`**: mỗi scope có physical transaction riêng và tự commit/rollback. Nếu business không chấp nhận partial success, lựa chọn propagation hoặc transaction boundary đang sai.

Khi thiết kế, hãy hỏi: “Nếu bước sau cùng thất bại, có còn hợp lệ khi thay đổi của bước inner vẫn bền vững không?” Nếu **không**, `REQUIRES_NEW` thường không thích hợp cho bước đó.

## 10. Connection pool và khóa: chi phí có thể không hiển thị trong demo

### 10.1. Outer vẫn giữ tài nguyên khi bị suspend

Trong giao dịch JDBC, outer thường đã lấy connection và có thể giữ lock. Khi inner `REQUIRES_NEW` bắt đầu, nó cần thêm connection. Nếu có N thread, mỗi thread đang giữ một outer connection và đợi inner connection mà pool chỉ có N, không ai lấy được connection mới. Kết quả có thể là **pool starvation** hoặc deadlock-like wait, sau đó timeout.

Spring khuyến nghị sizing pool lớn hơn số thread đồng thời có thể giữ outer transaction, tối thiểu dư một connection trong giả định phù hợp; thực tế cần capacity planning cho nhiều tầng nesting và workload.

Demo dùng:

```properties
spring.datasource.hikari.maximum-pool-size=5
```

Số 5 chỉ giúp **một runner tuần tự** có ít nhất hai connection. Nó **không** chứng minh cấu hình sản xuất an toàn. Với 20 request đồng thời, một pool 5 có thể thất bại ngay cả khi demo đơn lẻ luôn pass.

### 10.2. REQUIRES_NEW không giải phóng lock do outer giữ

Suspend transaction outer **không commit hoặc rollback outer**, do đó không tự nhả lock của outer. Inner cần cập nhật cùng record mà outer đang giữ lock có thể chờ chính connection outer đang bị suspend trong cùng thread. Đây là một anti-pattern dễ tạo timeout khó hiểu.

Dùng id khác nhau trong bài test để tránh biến phép thử propagation thành phép thử lock contention. Khi thiết kế transaction thật, cần phân tích thứ tự SQL và những row/bảng mỗi scope sẽ đụng tới.

### 10.3. Isolation/timeout/readOnly của inner là riêng

Vì `REQUIRES_NEW` thực sự mở physical transaction khác, inner có thể khai báo isolation, timeout và read-only phù hợp riêng:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 5,
    readOnly = true
)
public ReportView loadSnapshot() {
    return repository.loadSnapshot();
}
```

Đây là ví dụ API minh họa, thiếu định nghĩa `ReportView` và repository. Khi inner `REQUIRED` tham gia outer transaction, thuộc tính physical của outer thường được giữ nguyên; khai báo read-only/timeout/isolation trên inner không tự thay đổi transaction vật lý đã mở (và nếu bật `validateExistingTransaction`, manager có thể từ chối mismatch).

Không coi `readOnly=true` là biện pháp bảo mật cấm mọi câu INSERT ở mọi database. Nó có thể là hint tối ưu hoặc được thực thi khác nhau tùy manager/driver.

## 11. Tại sao không thay REQUIRES_NEW bằng NESTED?

`Propagation.NESTED` thường dựa vào **savepoint** trong **một physical transaction** khi dùng JDBC manager hỗ trợ. Nó không tạo transaction độc lập như `REQUIRES_NEW`.

| Tiêu chí | REQUIRED | REQUIRES_NEW | NESTED (khi hỗ trợ) |
| --- | --- | --- | --- |
| Physical transaction khi outer đã có T | Cùng T | T2 mới, độc lập | Cùng T, thêm savepoint |
| Inner commit riêng trước outer | Không | **Có** | Không, chỉ hoàn thành scope/savepoint |
| Outer rollback sau inner success | Hủy inner | Không hủy T2 đã commit | Hủy inner |
| Inner lỗi, outer muốn tiếp tục | Có thể mark T rollback-only | Inner rollback T2, outer có thể tiếp tục | Có thể rollback tới savepoint và tiếp tục |
| Cần connection mới cho inner | Thường không | Thường có | Thường không |
| Hỗ trợ | Manager có transaction | Manager hỗ trợ suspend/new | Manager/driver hỗ trợ savepoint |

Nếu yêu cầu là inner có thể rollback cục bộ nhưng vẫn muốn **outer commit toàn bộ transaction vật lý cuối**, `NESTED` có thể đáng nghiên cứu khi tài nguyên hỗ trợ, thay vì `REQUIRES_NEW` gây commit độc lập. Không mặc định JPA/R2DBC/driver đều hỗ trợ savepoint theo cách giống JDBC.

## 12. Exception propagation: độc lập transaction nhưng không độc lập Java call stack

Một điều nhiều người bỏ qua: `REQUIRES_NEW` tách physical transaction, nhưng method vẫn gọi nhau bằng Java. Nếu inner ném runtime exception và outer **không bắt** nó:

```java
@Transactional
public void outer() {
    saveOuter();
    inner.requiresNewInsertAndFail(99); // Ném IllegalStateException.
    // Lời gọi bên dưới không chạy.
}
```

Đây là mảnh code minh họa, cần các dependency/implementation. Trong trường hợp này:

1. Inner T2 bị rollback bởi transaction interceptor của inner.
2. Spring resume T_outer và rethrow `IllegalStateException`.
3. Exception tiếp tục thoát qua outer transaction interceptor.
4. Outer rollback T_outer theo default rule cho `RuntimeException`.

**Cả hai transaction có thể rollback** dù độc lập về vật lý, vì exception đã đi qua cả hai transaction scopes. Điều này không mâu thuẫn với `REQUIRES_NEW`; outer tự rollback do exception của chính nó không được catch.

Kịch bản D trong demo bắt exception ở outer, khiến outer return bình thường. Khi ấy chỉ inner T2 rollback và outer T commit. Do đó hãy luôn ghi rõ **ai bắt exception ở đâu** khi mô tả kết quả, thay vì viết “REQUIRES_NEW lỗi không bao giờ ảnh hưởng outer” — câu đó quá mạnh.

### 12.1. Checked exception và rollback rule

Theo mặc định, Spring rollback với `RuntimeException` hoặc `Error`; checked `IOException` thường không kích hoạt rollback nếu không có rule bổ sung. Nếu inner `REQUIRES_NEW` INSERT rồi ném checked `IOException`:

- Không có `rollbackFor`: Spring có thể **commit** inner T2 rồi ném checked exception lên outer.
- Có `@Transactional(rollbackFor = IOException.class)`: inner có thể rollback T2.
- Outer có thể catch hoặc rethrow; nếu nó rethrow checked exception, rollback của outer còn phụ thuộc rollback rule **của outer**, không tự theo inner.

Thí nghiệm chính dùng `IllegalStateException` vì nó có rollback mặc định, tránh trộn biến số exception rule vào biến số propagation. Với bài kiểm thử nâng cao, hãy thử thêm checked exception để đảm bảo policy được hiểu rõ.

### 12.2. Nếu inner đã commit, lỗi tại outer không undo inner

Một sự kiện `afterCommit` của T2, một callback hoặc thao tác tiếp theo ở outer phát sinh lỗi không đảo ngược T2 đã bền vững. Nếu commit outcome bị mất ACK từ DB và chưa biết transaction có commit hay không, cần tra cứu bằng khóa nghiệp vụ, idempotency và đối soát; không chỉ xem exception là bằng chứng rollback.

## 13. Làm đúng để Spring proxy thực thi propagation

### 13.1. Gọi qua bean khác được inject

`@Transactional` chỉ có hiệu lực khi hạ tầng transaction thực sự intercept lời gọi. Với Spring AOP proxy mode mặc định:

```java
@Service
class TransferService {
    public void transfer() {
        this.logIndependently();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logIndependently() {
        // Ghi dữ liệu...
    }
}
```

Đây là code minh họa. `this.logIndependently()` gọi trực tiếp target method trong cùng bean, **bỏ qua proxy** của method đó. Vì vậy `REQUIRES_NEW` trên inner không tự tạo physical transaction mới. Nếu caller ngoài đang có transaction, code inner có thể chỉ chạy trong transaction ấy; nếu không có transaction, nó có thể chạy ngoài Spring transaction.

Thử nghiệm A–F của bài dùng **hai bean** `OuterService` và `InnerService`, để cả hai transaction interceptors đều có cơ hội chạy. Nếu viết tất cả method trong một class rồi gọi `this.inner()`, bạn **không còn so sánh propagation** như đề bài yêu cầu.

### 13.2. Method phải được intercept được

Class-based proxy thường không intercept method `private` hoặc `final` theo cách cần thiết. Dùng public non-final method làm transaction entry point. Nếu dựa vào JDK proxy, interface/cách inject cũng quan trọng. Với `@PostConstruct`/constructor, đừng mặc định proxy đã hoàn tất. AspectJ mode có cơ chế weaving khác, không phải hành vi của demo.

### 13.3. Sử dụng đúng manager và DataSource

Một `@Transactional(REQUIRES_NEW)` trỏ tới manager của database A không biến thao tác bằng connection không được manager quản lý trên database B thành transaction độc lập trên B. Cần kiểm tra repository/EntityManager/JDBC thật dùng tài nguyên nào. Ví dụ chỉ có **một manager** và một DataSource để so sánh đơn biến.

Trong multi-resource workflows, local transaction độc lập có thể gây partial commit giữa các hệ thống. Cần thiết kế Saga/outbox/compensation hoặc distributed transaction thích hợp; `REQUIRES_NEW` không tự trở thành XA transaction.

### 13.4. @Async và reactive là ngữ cảnh khác

Imperative transaction thông thường gắn theo thread. Gọi `@Async`/Executor không tự mang transaction context của outer sang thread mới; inner `REQUIRES_NEW` ở thread khác không có cùng ngữ nghĩa suspend/resume như lời gọi đồng bộ qua proxy trong demo. Với reactive transaction, context được quản lý bằng Reactor context và `ReactiveTransactionManager`; hãy test theo pipeline thay vì sao chép nguyên kết luận của JDBC thread-bound.

## 14. Cách viết integration test có khả năng phát hiện sai khác thật

### 14.1. Không chỉ assert exception

Một test như:

```java
assertThrows(IllegalStateException.class,
    () -> outer.requiresNewThenOuterFails());
```

chưa đủ. Cả `REQUIRED` và `REQUIRES_NEW` đều có thể khiến outer ném đúng exception đó. **Điểm khác nằm ở dữ liệu sau rollback outer**, nên cần thêm:

```java
assertEquals(0, count(21)); // Outer đã rollback.
assertEquals(1, count(22)); // Inner REQUIRES_NEW đã commit.
```

Hai đoạn này là cú pháp JUnit minh họa, **không phải file test runnable độc lập** vì chưa khai báo JUnit, context và helper `count`. Dự án demo ở mục 5 là chương trình tự chạy có SQL readback đầy đủ.

Để kiểm tra `REQUIRED`, thay vào id 11 và 12: **cả hai count phải bằng 0**.

### 14.2. Không để @Transactional của test che kết quả

Spring TestContext có thể tự mở transaction quanh test method mang `@Transactional` rồi rollback cuối test. Nếu test gọi một service `REQUIRED`, nó có thể **tham gia transaction của test**, khiến thời điểm commit/rollback và `isNewTransaction()` khác production.

Dùng integration test không có outer test transaction hoặc chủ động kết thúc test transaction bằng `TestTransaction` trước khi đọc trạng thái. Các phép SQL kiểm chứng phải được thực hiện **sau khi boundary mà bạn đang đo đã kết thúc**, tốt nhất bằng transaction độc lập phù hợp.

### 14.3. Tách khỏi transaction đã mở ngoài ý muốn

Nếu controller, filter, scheduled job hoặc runner được cấu hình transaction bao ngoài, một method `REQUIRED` có thể join transaction ấy; `REQUIRES_NEW` lại suspend transaction đó và mở mới. Trước khi kết luận from test, xác định nguồn của physical transaction hiện có.

### 14.4. Kiểm tra rollback-only đúng chỗ

Với `REQUIRED`, một inner scope gặp `RuntimeException` đi qua transaction interceptor có thể đánh dấu transaction vật lý chung rollback-only. Outer catch rồi return sẽ thường dẫn tới `UnexpectedRollbackException` **tại outer commit boundary**. Test phải bắt exception ngoài proxy và xác minh hai row cùng biến mất.

Với `REQUIRES_NEW`, inner rollback được xử lý ngay trong transaction riêng. Outer catch rồi return vẫn có thể commit record outer; test D xác nhận bằng count 1/0.

## 15. Chẩn đoán khi số liệu không giống expected output

| Triệu chứng | Nguyên nhân có thể | Phép kiểm cần làm |
| --- | --- | --- |
| B ra `0/0` thay vì `0/1` | Inner `REQUIRES_NEW` không được intercept, hoặc manager/resource sai | Kiểm tra gọi qua proxy, log transaction mới, bean manager |
| A ra `0/1` thay vì `0/0` | Inner không thật sự join transaction; chạy với manager/connection riêng | Kiểm tra `DataSource` và connection resource |
| C không ném `UnexpectedRollbackException` | Inner advice không chạy, lỗi bị nuốt ở inner, rule rollback thay đổi | Kiểm tra `newTx`, exception và transaction manager policy |
| D ra `0/0` thay vì `1/0` | Outer không catch, outer tự rollback-only, hoặc commit failure | Kiểm tra đường exception ngoài proxy và trạng thái DB |
| App bị treo ở `REQUIRES_NEW` | Pool thiếu connection hoặc inner chờ lock outer giữ | Kiểm tra Hikari active/idle/waiting, locks và timeout |
| Kết quả `1/1` ở mọi ca | Test chưa thực sự rollback; exception được ném trước/không thoát; đọc nhầm DB | In logs, đọc bằng SQL sau method, kiểm tra ids |
| `newTx` đều là `true` | Không có outer transaction hoặc method outer bypass proxy | Kiểm tra caller, proxy của outer, tên manager |
| `newTx` đều là `false` | Inner `REQUIRES_NEW` không được intercept hoặc transaction context sai | Kiểm tra self-invocation và bean injection |
| SQL báo unique constraint | Id cũ từ lần chạy trước hoặc thay đổi schema/data lifecycle | Reset DB in-memory, dùng id duy nhất |
| Count khác giữa hai lần chạy | DB không sạch, transaction test/runner còn active hoặc thao tác đồng thời | Cô lập data và scope, tránh shared fixtures |

Bật thêm log trong `application.properties` khi điều tra:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Đây là **cấu hình debug tùy chọn**, không bắt buộc để thấy expected output của `System.out.println`. Log có thể giúp nhận ra manager tạo transaction mới, suspend/resume, commit hay rollback. Không lấy một dòng log thay cho SQL readback, và không đưa payload nhạy cảm vào log.

## 16. Checklist lựa chọn REQUIRED hay REQUIRES_NEW

Trước khi chấp nhận `REQUIRES_NEW`, hãy trả lời:

1. Thay đổi inner có **được phép sống sót** khi outer rollback không? Nếu không, `REQUIRED` thường phù hợp hơn với cùng DB.
2. Nếu inner thất bại, outer có cần tiếp tục và commit không? Nếu có, phải thiết kế catch/recovery và nhất quán; `REQUIRES_NEW` là một lựa chọn, nhưng `NESTED` cũng đáng nghiên cứu khi hỗ trợ savepoint.
3. Nếu inner đã commit nhưng outer lỗi, bạn có cơ chế **đối soát/compensation** để tránh dữ liệu mồ côi không?
4. Inner có thực sự được gọi qua Spring proxy không? Nó dùng đúng manager/connection chứ?
5. Pool có đủ connection cho outer và inner cùng active với tải đồng thời không? Inner có lock row outer còn giữ không?
6. Isolation, timeout, read-only và exception rollback rule của inner đã được test chưa?
7. Có thao tác side effect ngoài transaction (HTTP, email, event broker) mà rollback DB không bao phủ không?
8. Test đã chứng minh SQL **sau commit/rollback**, thay vì chỉ assert exception hoặc nhìn thấy row chưa commit không?

**Nguyên tắc ra quyết định:** chọn propagation theo **yêu cầu bền vững và atomicity của nghiệp vụ**. Đừng chọn `REQUIRES_NEW` chỉ để loại bỏ một `UnexpectedRollbackException`; nó có thể biến lỗi dễ phát hiện thành partial commit âm thầm.

## 17. Bài tập tự kiểm tra và đáp án

**Câu 1.** Outer đã mở T, inner `REQUIRED` INSERT thành công rồi return. Outer ném `IllegalStateException`. Inner row có còn sau khi outer rollback không?

**Đáp án:** Không, nếu cùng manager/tài nguyên và transaction thực sự rollback. Inner chỉ tham gia T, không có commit vật lý riêng.

**Câu 2.** Thay inner thành `REQUIRES_NEW`, nó INSERT/commit rồi outer ném exception. Inner row còn không?

**Đáp án:** Có, nếu inner commit thực sự thành công. T_inner độc lập; rollback outer không undo nó.

**Câu 3.** Inner `REQUIRED` ném RuntimeException, outer catch và return bình thường. Caller có chắc nhận success không?

**Đáp án:** Không. Inner scope có thể đã đặt rollback-only lên transaction chung; outer cố commit có thể nhận `UnexpectedRollbackException`.

**Câu 4.** Inner `REQUIRES_NEW` ném RuntimeException, outer catch rồi return. Outer row có chắc bị rollback không?

**Đáp án:** Không. Inner transaction riêng rollback, outer có thể commit nếu không có lỗi/cờ rollback-only khác. Demo D cho kết quả outer 1, inner 0.

**Câu 5.** Nếu outer không catch exception của inner `REQUIRES_NEW` thì outer có được miễn rollback không?

**Đáp án:** Không. Exception runtime sẽ tiếp tục đi qua outer transaction interceptor và có thể khiến chính outer rollback. “Independent transaction” không làm exception biến mất khỏi Java call stack.

**Câu 6.** Không có outer transaction: khác biệt giữa `REQUIRED` và `REQUIRES_NEW` có dễ nhìn qua count không?

**Đáp án:** Không. Cả hai đều có thể tự tạo transaction và commit. Cần test khi một transaction outer đã active.

**Câu 7.** Với pool chỉ có 1 connection, outer bắt đầu T rồi gọi inner `REQUIRES_NEW`. Vấn đề có thể xảy ra?

**Đáp án:** Outer giữ connection trong lúc suspend; inner cần connection khác nên có thể chờ đến timeout. Pool sizing, lock và concurrency là yếu tố quan trọng khi dùng `REQUIRES_NEW`.

**Câu 8.** `NESTED` và `REQUIRES_NEW` đều có thể giúp inner rollback mà outer tiếp tục; chúng có cùng physical semantics không?

**Đáp án:** Không. `NESTED` có thể dùng savepoint trong cùng một physical transaction; outer rollback cuối vẫn undo phần inner. `REQUIRES_NEW` tạo physical transaction riêng, nên inner đã commit có thể tồn tại dù outer rollback.

**Câu 9.** Làm sao chứng minh `REQUIRES_NEW` hơn một flag `isNewTransaction=true`?

**Đáp án:** Tạo inner INSERT thành công rồi outer rollback, đọc DB **sau khi transaction ngoài kết thúc**. Nếu inner row còn, đó là bằng chứng commit độc lập theo điều kiện test đã kiểm soát.

## 18. Tài liệu tham khảo

- Spring Framework — Transaction Propagation, so sánh `PROPAGATION_REQUIRED`, `PROPAGATION_REQUIRES_NEW` và `PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Kết luận từ dữ liệu:** thử nghiệm **A = 0/0** và **B = 0/1** cho thấy outer rollback hủy inner `REQUIRED` nhưng không hủy inner `REQUIRES_NEW` đã commit. Thử nghiệm **C = 0/0 kèm UnexpectedRollbackException** và **D = 1/0** cho thấy inner rollback trong `REQUIRED` có thể làm transaction chung không thể commit, trong khi `REQUIRES_NEW` cho phép outer tiếp tục sau khi xử lý exception. Chọn cơ chế nào là **quyết định về tính nhất quán nghiệp vụ**, không chỉ là một tham số annotation.