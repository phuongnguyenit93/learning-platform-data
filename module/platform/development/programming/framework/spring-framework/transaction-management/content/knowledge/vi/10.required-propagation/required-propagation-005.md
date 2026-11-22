# UnexpectedRollbackException tại ranh giới hoàn tất bên ngoài với PROPAGATION_REQUIRED

## 1. Tình huống đặc trưng: bên trong báo lỗi, bên ngoài tưởng vẫn có thể commit

Xét một luồng nghiệp vụ Spring:

1. Một caller gọi `OuterService.execute()` qua Spring proxy. Method này có `@Transactional` với propagation mặc định `REQUIRED`, nên Spring mở một transaction vật lý nếu chưa có transaction từ trước.
2. `execute()` gọi `InnerService.change()` trên một **Spring bean khác**, cũng có `@Transactional(propagation = REQUIRED)`.
3. Inner gặp một `RuntimeException`. Spring transaction interceptor của inner nhìn thấy exception và đánh dấu transaction chung là **rollback-only**.
4. Outer bắt exception, ghi log rồi tiếp tục xử lý, cuối cùng **return bình thường**, nghĩ rằng transaction có thể commit.
5. Khi outer proxy yêu cầu commit ở ranh giới ngoài cùng, transaction manager phát hiện transaction chung đã bị đánh dấu rollback-only. Nó thực hiện rollback thay vì commit và báo **`UnexpectedRollbackException`** cho caller.

Lỗi này không phải hành động bất thường vô cớ của Spring. Nó bảo vệ một bảo đảm quan trọng: **caller không được nhận một kết quả “thành công” nếu transaction mà nó tưởng đã commit thực tế bị rollback**.

Dòng thông điệp phổ biến từ manager có dạng:

~~~text
Transaction rolled back because it has been marked as rollback-only
~~~

**Cần phân biệt:** “Unexpected” nghĩa là **rollback xảy ra khi bên ngoài đang cố commit**, không phải Spring không biết rollback-only đến từ đâu. Lỗi gốc có thể đã được catch; sự kiện rollback tại outer boundary là một kết quả khác với exception nghiệp vụ của inner.

Bài này tập trung vào `PROPAGATION_REQUIRED`, quan hệ giữa **logical transaction scope** và **physical transaction**, cơ chế rollback-only, thời điểm `UnexpectedRollbackException` xuất hiện và cách kiểm tra/sửa thiết kế.

## 2. Một transaction vật lý, nhiều logical transaction scope

Trong Spring, một lời gọi method được advice bởi `@Transactional(propagation = REQUIRED)` tạo một **logical transaction scope** của riêng method đó. Khi chưa có transaction hiện hữu, nó tạo transaction vật lý mới. Khi đã có transaction phù hợp, nó **tham gia** transaction vật lý đã tồn tại.

Với hai service gọi nhau qua proxy, có thể hình dung:

~~~text
Caller
  |
  v
OuterService proxy -- @Transactional(REQUIRED), logical scope OUTER
  |
  |  mở PHYSICAL TRANSACTION T1, connection C1
  v
OuterService.outer()
  |
  v
InnerService proxy -- @Transactional(REQUIRED), logical scope INNER
  |
  |  tham gia T1, không tạo connection/physical transaction độc lập
  v
InnerService.inner()
  |
  +-- lỗi unchecked -> INNER đánh dấu T1 rollback-only
  |
  v
OuterService.outer() catch lỗi -> return bình thường
  |
  v
OUTER interceptor yêu cầu commit T1
  |
  +-- thấy T1 rollback-only -> rollback T1
  |
  v
Caller nhận UnexpectedRollbackException
~~~

**Không có hai lần commit độc lập**: inner `REQUIRED` không thể commit “phần của nó” khi đang tham gia T1. Khi inner kết thúc bình thường, nó chỉ kết thúc logical scope và tiếp tục để outer quyết định thời điểm hoàn tất transaction vật lý. Khi inner rollback trong trạng thái tham gia T1, chính đánh dấu rollback-only khiến outer không thể commit T1 nữa.

| Khái niệm | Phạm vi | Có thể điều khiển gì? |
| --- | --- | --- |
| Logical scope OUTER | Lời gọi `outer()` đi qua transaction advice | Đưa ra ý định commit/rollback tại điểm outer return/throw |
| Logical scope INNER | Lời gọi `inner()` đi qua transaction advice | Đưa ra kết quả của scope inner, có thể làm transaction chung rollback-only |
| Physical transaction T1 | Một transaction tài nguyên thật, ví dụ JDBC connection | Chỉ có một kết quả cuối cùng: commit **hoặc** rollback |
| Rollback-only marker | Trạng thái gắn với transaction/status, tùy manager | Ngăn việc commit thành công khi transaction đã bị tuyên bố phải rollback |

Ví dụ outer và inner đều gọi `JdbcTemplate` dùng cùng `DataSource` với `JdbcTransactionManager`. Chúng có thể thực thi nhiều câu SQL trên cùng connection tham gia T1. Vì vậy một UPDATE thành công ở outer **vẫn bị hủy** nếu inner khiến T1 rollback-only rồi outer tiếp tục.

## 3. Sơ đồ thời gian: vì sao lỗi chỉ lộ ra khi outer hoàn tất?

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant OP as Outer proxy
    participant O as OuterService
    participant IP as Inner proxy
    participant I as InnerService
    participant TM as TransactionManager/DB

    C->>OP: outer()
    OP->>TM: begin physical transaction T1
    OP->>O: invoke outer()
    O->>IP: inner()
    IP->>TM: join T1 (logical scope)
    IP->>I: invoke inner()
    I-->>IP: throw RuntimeException
    IP->>TM: mark T1 rollback-only
    IP-->>O: rethrow RuntimeException
    Note over O: catch, xử lý rồi return bình thường
    O-->>OP: return success
    OP->>TM: commit T1?
    TM->>TM: detect rollback-only
    TM->>TM: rollback T1
    TM-->>OP: UnexpectedRollbackException
    OP-->>C: throw UnexpectedRollbackException
~~~

Ở đây, outer **không thể sửa** chuyện inner đã đánh dấu transaction chung rollback-only chỉ bằng cách catch exception hoặc trả về một DTO thành công. Khi transaction manager thực hiện commit của outer, nó không thể âm thầm bỏ marker rồi commit. Hành vi thông thường là rollback và ném exception cho caller.

### Lỗi xuất hiện ở “đâu”?

Trong kịch bản trên:

- Inner ném **`IllegalStateException`** từ method nghiệp vụ.
- Outer **bắt được `IllegalStateException`** trong `try/catch` bao quanh `inner()`.
- Outer chạy đến hết method và **return bình thường**.
- Sau khi method outer return, proxy transaction advice thực hiện commit; **`UnexpectedRollbackException` được ném từ quá trình hoàn tất của proxy**, rồi truyền tới caller ngoài proxy.

Vì vậy, đặt một `try/catch (UnexpectedRollbackException)` **bên trong thân method outer, chỉ bao quanh `inner()`** sẽ thường **không bắt được exception ở outer commit boundary** trong cấu hình mặc định. Catch phải nằm ở **caller bên ngoài outer proxy**, hoặc tại tầng xử lý lỗi bao trùm invocation đó.

Spring có thiết lập fail-early ở một số manager khiến `UnexpectedRollbackException` có thể xuất hiện sớm hơn, nhưng **mặc định của `AbstractPlatformTransactionManager` là báo ở ranh giới ngoài cùng** khi global rollback-only đã được nhận diện. Không đồng nhất mọi nơi ném exception với cùng một pha của transaction.

## 4. Vì sao outer đã catch mà vẫn rollback?

Java `try/catch` chỉ thay đổi **luồng điều khiển exception**, không xóa trạng thái transaction đã được manager đặt. Khi inner proxy thấy unchecked exception, nó có cơ hội đánh dấu transaction vật lý đang tham gia là rollback-only. Một khi global marker này đã được đặt, việc outer catch không phục hồi transaction về trạng thái có thể commit.

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        try {
            inner.fail(); // Đi qua proxy InnerService.
        } catch (IllegalStateException ex) {
            System.out.println("Đã bắt lỗi inner");
        }
        System.out.println("Outer sắp return bình thường");
    }
}

@Service
class InnerService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void fail() {
        throw new IllegalStateException("inner failed");
    }
}
~~~

Đây là **mã minh họa** chưa có imports/ứng dụng bootstrap, nhằm thể hiện cấu trúc hai Spring bean. Với một manager theo default, inner advice xử lý unchecked exception, đặt global rollback-only; outer catch và return; outer advice sau đó có thể ném `UnexpectedRollbackException`. Không nên suy ra nếu thay bean inner thành một method cùng lớp được gọi bằng `this.fail()`: **self-invocation** bỏ qua proxy interception của inner trong proxy mode, nên dấu rollback-only riêng của inner có thể không được đặt.

### Chìa khóa: “exception đi qua advice nào?”

- Nếu inner được gọi **qua proxy**, exception đi qua inner advice trước khi đến `catch` của outer.
- Nếu inner là lời gọi trực tiếp `this.inner()` trong cùng target, inner annotation thường không tạo một interceptor riêng; nếu outer bắt exception và return bình thường, outer advice có thể quyết định commit nếu không có nguyên nhân rollback-only khác.
- Nếu outer **không bắt** exception và để unchecked exception đi ra ngoài, outer advice thấy lỗi và có thể **chủ động rollback**. Trong đường đi đó caller thường nhận **exception gốc**, không nhất thiết `UnexpectedRollbackException`.
- Nếu inner `@Transactional(noRollbackFor = IllegalStateException.class)` và lỗi phù hợp rule này, advice của inner thường không đánh dấu rollback-only chỉ vì exception đó; outer bắt lỗi rồi hoàn tất bình thường thì commit có thể hợp lệ, với điều kiện DB/manager vẫn cho phép.

Không có công thức “cứ inner throw thì chắc chắn UnexpectedRollbackException”. Phải kiểm tra **rollback rule của từng logical scope**, lời gọi qua proxy, trạng thái tài nguyên và điều outer làm khi hoàn tất.

## 5. Ba đường đi quan trọng: cùng lỗi gốc nhưng kết quả khác

Giả sử một physical transaction đang được tạo bởi outer; mỗi case được chạy độc lập với dữ liệu ban đầu giống nhau:

| Kịch bản | Inner xảy ra | Outer làm gì? | Thông thường caller thấy | Physical transaction |
| --- | --- | --- | --- | --- |
| A — Inner `REQUIRED` throw unchecked | Inner proxy đặt rollback-only | Catch và return bình thường | `UnexpectedRollbackException` tại outer commit | Rollback |
| B — Inner `REQUIRED` throw unchecked | Inner proxy đặt rollback-only | Không catch, exception thoát outer | Exception nghiệp vụ gốc (ví dụ `IllegalStateException`) | Rollback |
| C — Inner `REQUIRED` throw unchecked nhưng có `noRollbackFor` phù hợp | Inner proxy không đánh dấu rollback vì rule đó | Catch và return bình thường | Return bình thường nếu commit được | Commit |
| D — Inner `REQUIRED` chỉ gọi `status.setRollbackOnly()` rồi return | Inner scope chủ động yêu cầu rollback | Outer không biết, return bình thường | `UnexpectedRollbackException` tại outer commit (cấu hình thông thường) | Rollback |
| E — Outer **tự đánh dấu rollback-only** và return | Outer trực tiếp chọn rollback | Return bình thường | Thường return bình thường, rollback được thực hiện | Rollback |

Bảng giả định Spring declarative transaction theo proxy mode, cùng manager/tài nguyên, các lời gọi qua proxy, không có lỗi SQL/connection/commit khác. `UnexpectedRollbackException` có thể không phải exception duy nhất trong hệ thống thực; đây là các đường đi điển hình để đọc semantics.

Ở kịch bản E, “rollback-only” thuộc **scope khởi tạo transaction**. Nếu chính scope ngoài cùng gọi `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`, rollback là quyết định **chủ động**, không phải một rollback âm thầm trái với ý định commit của outer. Vì vậy không nên khẳng định mọi trường hợp đánh dấu rollback-only sẽ ném `UnexpectedRollbackException`.

## 6. Ví dụ hoàn chỉnh Java 17+: quan sát UnexpectedRollbackException và số dư thật

Ví dụ dùng **Spring Boot 3.3.5 (Spring Framework 6.1.x)**, **Spring JDBC**, **H2 in-memory** và Maven. Không dùng web server, JPA, R2DBC hay nhiều database. Các method được gọi qua proxy của Spring bean; mọi UPDATE chạy trên cùng `JdbcTemplate` và `DataSource` do `JdbcTransactionManager` quản lý.

Ứng dụng có năm phép thử:

1. Inner `REQUIRED` ném unchecked, outer catch và return: rollback + `UnexpectedRollbackException` ở caller.
2. Inner ném unchecked nhưng outer **không catch**: rollback, caller thấy exception gốc.
3. Inner `REQUIRED` tự đánh dấu rollback-only rồi return bình thường: outer commit thất bại với `UnexpectedRollbackException`.
4. Inner ném unchecked có rule `noRollbackFor` phù hợp, outer catch: transaction commit được.
5. Luồng thành công: outer và inner cùng `REQUIRED`, mọi UPDATE commit một lần ở cuối.

### 6.1. Tạo project

~~~text
required-rollback-demo/
├── pom.xml
└── src/main/java/example/requiredrollback/
    ├── RequiredRollbackApplication.java
    ├── OuterService.java
    └── InnerService.java
~~~

Cần **JDK 17+**, Maven và truy cập Maven Central để tải dependencies khi chạy lần đầu.

### 6.2. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>required-rollback-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. Tệp RequiredRollbackApplication.java

~~~java
package example.requiredrollback;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class RequiredRollbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequiredRollbackApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource source) {
        return new JdbcTransactionManager(source);
    }

    @Bean
    CommandLineRunner runDemo(JdbcTemplate jdbc, OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO account (id, balance) VALUES (?, ?)", 1, 100
            );
            System.out.println("START=" + balance(jdbc));

            try {
                outer.catchInnerFailure();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "CALLER_UNEXPECTED=" + ex.getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_CATCH=" + balance(jdbc));

            try {
                outer.propagateInnerFailure();
            } catch (IllegalStateException ex) {
                System.out.println("CALLER_ORIGINAL=" + ex.getMessage());
            }
            System.out.println("AFTER_PROPAGATE=" + balance(jdbc));

            try {
                outer.innerMarksOnly();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "CALLER_UNEXPECTED_MANUAL="
                        + ex.getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_MANUAL=" + balance(jdbc));

            outer.catchesNoRollbackRule();
            System.out.println(
                "AFTER_NO_ROLLBACK_RULE=" + balance(jdbc)
            );

            outer.allSuccess();
            System.out.println("AFTER_HAPPY=" + balance(jdbc));
        };
    }

    private static Integer balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?", Integer.class, 1
        );
    }
}
~~~

### 6.4. Tệp OuterService.java

~~~java
package example.requiredrollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void catchInnerFailure() {
        add(10);
        try {
            inner.failRequired(); // Gọi qua proxy của bean khác.
        } catch (IllegalStateException ex) {
            System.out.println("INNER_CAUGHT=" + ex.getMessage());
        }
        System.out.println(
            "ROLLBACK_ONLY_IN_OUTER="
                + TransactionAspectSupport.currentTransactionStatus()
                    .isRollbackOnly()
        );
        add(30);
        // Return bình thường nhưng T1 đã rollback-only.
        // UnexpectedRollbackException xảy ra SAU return, trong proxy.
    }

    @Transactional
    public void propagateInnerFailure() {
        add(11);
        inner.failRequired();
        // Không tới đây khi inner throw.
    }

    @Transactional
    public void innerMarksOnly() {
        add(3);
        inner.markRollbackOnly();
        System.out.println(
            "MANUAL_ROLLBACK_ONLY="
                + TransactionAspectSupport.currentTransactionStatus()
                    .isRollbackOnly()
        );
        add(5);
    }

    @Transactional
    public void catchesNoRollbackRule() {
        add(1);
        try {
            inner.nonFatal();
        } catch (IllegalStateException ex) {
            System.out.println(
                "INNER_NONFATAL_CAUGHT=" + ex.getMessage()
            );
        }
        System.out.println(
            "NO_ROLLBACK_RULE_FLAG="
                + TransactionAspectSupport.currentTransactionStatus()
                    .isRollbackOnly()
        );
        add(3);
    }

    @Transactional
    public void allSuccess() {
        add(10);
        inner.success();
    }

    private void add(int delta) {
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = 1",
            delta
        );
    }
}
~~~

### 6.5. Tệp InnerService.java

~~~java
package example.requiredrollback;

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
    public void failRequired() {
        add(20);
        throw new IllegalStateException("inner-failure");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void markRollbackOnly() {
        add(40);
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        // Return bình thường; shared physical transaction bị đánh dấu.
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        noRollbackFor = IllegalStateException.class
    )
    public void nonFatal() {
        add(2);
        throw new IllegalStateException("nonfatal-inner");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void success() {
        add(20);
    }

    private void add(int delta) {
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = 1",
            delta
        );
    }
}
~~~

### 6.6. Chạy và đối chiếu kết quả

Từ thư mục `required-rollback-demo`:

~~~bash
mvn -q spring-boot:run
~~~

Các dòng do **chương trình tự in**, bỏ qua log khởi động Spring Boot/Hikari:

~~~text
START=100
INNER_CAUGHT=inner-failure
ROLLBACK_ONLY_IN_OUTER=true
CALLER_UNEXPECTED=UnexpectedRollbackException
AFTER_CATCH=100
CALLER_ORIGINAL=inner-failure
AFTER_PROPAGATE=100
MANUAL_ROLLBACK_ONLY=true
CALLER_UNEXPECTED_MANUAL=UnexpectedRollbackException
AFTER_MANUAL=100
INNER_NONFATAL_CAUGHT=nonfatal-inner
NO_ROLLBACK_RULE_FLAG=false
AFTER_NO_ROLLBACK_RULE=106
AFTER_HAPPY=136
~~~

### 6.7. Giải thích bằng từng transaction thực sự

**Case 1 — Outer catch, outer commit không được:**

- T1 bắt đầu ở `outer.catchInnerFailure()`. Outer UPDATE `+10`.
- Inner `REQUIRED` tham gia T1, UPDATE `+20` rồi ném `IllegalStateException`. Inner interceptor gặp unchecked exception và đánh dấu T1 rollback-only.
- Outer catch, `isRollbackOnly()` trả true; outer vẫn UPDATE `+30`. Các câu SQL có thể đã chạy, **không có nghĩa chúng sẽ commit**.
- Outer return. Interceptor outer muốn commit T1 nhưng phải rollback; caller bên ngoài nhận `UnexpectedRollbackException`. Số dư trở lại 100, không phải 160.

**Case 2 — Exception gốc thoát khỏi outer:**

- T1 mới được mở, outer UPDATE `+11`, inner UPDATE `+20` rồi ném `IllegalStateException`.
- Outer không catch. Interceptor outer nhận chính unchecked exception đó, xử lý rollback thay vì đi theo đường commit. Caller bắt được `IllegalStateException("inner-failure")`.
- Số dư vẫn 100. Việc không thấy `UnexpectedRollbackException` không có nghĩa rollback thất bại; ngược lại, **rollback ở đây đã đúng với exception đi ra outer**.

**Case 3 — Inner tự setRollbackOnly rồi return:**

- Outer UPDATE `+3`, inner UPDATE `+40`, sau đó inner gọi `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`.
- Inner không ném exception, nhưng khi logical scope tham gia T1 kết thúc, transaction chung được đánh dấu rollback-only.
- Outer vẫn UPDATE `+5` rồi return. Outer commit bị từ chối bằng rollback + `UnexpectedRollbackException`. Số dư vẫn 100.

**Case 4 — Inner có quy tắc không rollback riêng:**

- Outer UPDATE `+1`, inner UPDATE `+2` rồi ném `IllegalStateException`.
- Inner annotation có `noRollbackFor = IllegalStateException.class`. Với policy này, inner advice không yêu cầu rollback **chỉ vì exception đó**, và physical transaction T1 vẫn hợp lệ.
- Outer catch, in flag false, UPDATE thêm `+3` và return. Commit thành công, số dư 100 + 1 + 2 + 3 = **106**.
- Rule này chỉ có ý nghĩa khi nghiệp vụ cho phép tiếp tục; đừng dùng `noRollbackFor` tùy tiện để che lỗi dữ liệu hoặc lỗi hạ tầng.

**Case 5 — Hai logical scope cùng hoàn tất bình thường:**

- Outer UPDATE `+10`, inner UPDATE `+20`. Không có rollback-only.
- Outer hoàn tất transaction vật lý, commit một lần; số dư thành **136**.

**Vì sao ví dụ đáng tin?** Tất cả service được Spring inject, `OuterService` gọi `InnerService` qua bean khác chứ không gọi `this.inner()`; `JdbcTemplate` và transaction manager dùng cùng `DataSource` H2. Caller `CommandLineRunner` không được gắn `@Transactional`, nên mỗi method `outer.*` có ranh giới vật lý riêng. Dữ liệu được đọc **sau khi proxy hoàn tất** để thấy commit/rollback thật, không chỉ dựa vào log.

## 7. Phân biệt inner mark rollback-only với outer chủ động rollback

Hai đoạn code sau dễ bị đánh đồng:

~~~java
// A: InnerService tham gia transaction chung bằng REQUIRED.
@Transactional(propagation = Propagation.REQUIRED)
public void inner() {
    TransactionAspectSupport.currentTransactionStatus()
        .setRollbackOnly();
}
~~~

~~~java
// B: OuterService là nơi khởi tạo physical transaction.
@Transactional
public void outer() {
    TransactionAspectSupport.currentTransactionStatus()
        .setRollbackOnly();
}
~~~

Cả hai là **trích đoạn minh họa**; thiếu lớp Spring/điều kiện bootstrap. Ở A, **inner logical scope** tự chọn rollback-only, rồi outer có thể vẫn ngây thơ đề nghị commit: đó là đường đi dẫn đến `UnexpectedRollbackException`. Ở B, **outer scope sở hữu transaction** đã tự nói “tôi muốn rollback”: manager có thể rollback và outer return bình thường, không nhất thiết phải báo “unexpected”.

Với propagation tham gia transaction đã tồn tại từ **caller cao hơn**, ngay cả một method tưởng là “outer” trong một service cũng chỉ là inner logical scope đối với physical transaction thật. Do đó chữ “outer” trong tên method **không quyết định** ranh giới vật lý; phải tìm entrypoint nào ban đầu mở transaction và manager nào hoàn tất nó.

## 8. Khi nào rollback-only được đặt?

Những nguyên nhân thường gặp:

- **Unchecked exception rời inner `@Transactional(REQUIRED)`**: rollback rule mặc định đánh dấu transaction chung; exception có thể bị catch ở outer **sau** khi marker đã đặt.
- **Checked exception có `rollbackFor` phù hợp**: tuy checked exception thường không tự kích hoạt rollback theo mặc định, một rule tường minh có thể đặt marker.
- **Code gọi `setRollbackOnly()`** trên scope đang tham gia transaction.
- **Một inner transaction template hoặc tầng repository được advice quản lý** quyết định rollback, với điều kiện cùng physical transaction và rule phù hợp.
- **Hạ tầng hoặc database** khiến transaction không còn commitable (ví dụ một lỗi SQL làm DB transaction aborted). Đây là tình huống cần xem trạng thái tài nguyên và exception chính xác, không tự động gán mọi lỗi SQL cho một marker duy nhất của Spring.

Trên nhiều transaction manager kế thừa `AbstractPlatformTransactionManager`, thiết lập `globalRollbackOnParticipationFailure` mặc định là true: một participating scope thất bại với rollback decision có thể khiến toàn transaction rollback-only. Một số manager/hệ tài nguyên có semantics riêng; cần biết manager thực tế trước khi dự đoán.

### IsRollbackOnly và transactionActive nói được điều gì?

~~~java
boolean rollbackOnly =
    TransactionAspectSupport.currentTransactionStatus()
        .isRollbackOnly();
~~~

API trên chỉ hợp lệ khi đang có transaction advice phù hợp với thread hiện tại; gọi ngoài proxy context có thể lỗi. Khi gọi trong outer scope JDBC ở ví dụ, nó giúp xác nhận trạng thái rollback-only đã đến scope hiện tại. Tuy nhiên một kết quả `false` tại thời điểm kiểm tra **không hứa** commit về sau sẽ thành công, vì tài nguyên/logic khác còn có thể thất bại sau đó.

Tương tự, `TransactionSynchronizationManager.isActualTransactionActive()` cho biết transaction đang hoạt động theo context **imperative** hiện tại, nhưng không cho biết transaction đang rollback-only, có phải inner được intercept riêng không, hay commit cuối cùng có thành công không.

## 9. Những trường hợp không nên suy luận là UnexpectedRollbackException

### 9.1. Outer chủ động ném unchecked exception

Nếu outer để `IllegalStateException` thoát ra và rollback rules quyết định rollback, caller thường nhận **exception gốc**, không phải `UnexpectedRollbackException` vì outer **không yêu cầu commit**. Tài nguyên vẫn có thể ném lỗi khác trong rollback; vì vậy từ “thường” có ý nghĩa.

### 9.2. Inner lỗi nhưng bị catch **trước khi đến inner transaction advice**

~~~java
@Service
class InnerService {
    @Transactional
    public void inner() {
        try {
            throw new IllegalStateException("handled locally");
        } catch (IllegalStateException ex) {
            // Không rethrow, không setRollbackOnly.
        }
    }
}
~~~

Nếu không có nguyên nhân rollback-only khác, inner advice thấy **return bình thường**, không đánh dấu global rollback-only chỉ vì một exception Java đã được catch. Outer có thể commit.

### 9.3. Self-invocation bỏ qua inner proxy

~~~java
@Service
class OneBean {
    @Transactional
    public void outer() {
        try {
            this.inner();
        } catch (IllegalStateException ignored) {
            // Không có advice inner tại self-call.
        }
    }

    @Transactional
    public void inner() {
        throw new IllegalStateException("failure");
    }
}
~~~

Ở chế độ proxy mặc định, `this.inner()` không chạy interceptor của inner, nên Spring **không tự đánh dấu rollback-only tại logical scope inner**. Vì outer catch và return bình thường, physical transaction có thể commit. Đừng xem đây là cách “sửa” lỗi: nó vô tình bỏ qua transaction semantics khai báo ở method inner.

### 9.4. Inner REQUIRES_NEW thay vì REQUIRED

`PROPAGATION_REQUIRES_NEW` mở một physical transaction độc lập, suspend transaction ngoài khi có hỗ trợ. Nếu inner rollback, outer catch exception và tiếp tục, transaction ngoài **không tự bị đánh dấu rollback-only chỉ vì inner độc lập thất bại**. Tuy nhiên inner commit thành công cũng **không bị rollback** khi outer thất bại sau đó — một thay đổi nhất quán nghiệp vụ cần đánh giá nghiêm túc. Pool JDBC phải đủ connection trong khi outer giữ connection và inner cần thêm tài nguyên.

### 9.5. Inner NESTED với savepoint khi được hỗ trợ

`PROPAGATION_NESTED` có thể tạo savepoint trong cùng physical transaction, rollback phần inner về savepoint rồi để outer tiếp tục và commit phần còn lại. Nó phụ thuộc transaction manager/driver, thường phù hợp JDBC với savepoint support; không có quyền giả định JPA/JTA/R2DBC đều hỗ trợ tương tự.

### 9.6. Manager có cấu hình fail-early

`AbstractPlatformTransactionManager.setFailEarlyOnGlobalRollbackOnly(true)` có thể khiến `UnexpectedRollbackException` xuất hiện sớm hơn trong một inner boundary khi manager đã biết global marker. Mặc định là false, nên lỗi thường chỉ lộ ra ở outermost boundary. Chỉnh cấu hình này nhằm **chẩn đoán sớm hơn**, không làm transaction đã rollback-only trở nên có thể commit.

## 10. Những “cách sửa” sai hoặc nguy hiểm

### 10.1. Catch UnexpectedRollbackException trong outer method

Ở ví dụ cơ bản, exception xảy ra **sau khi thân outer method đã return**, trong `TransactionInterceptor`. Một `try/catch` bên trong outer quanh inner không bắt được outer completion failure. Nếu muốn xử lý exception để tạo response thích hợp, đặt handler ở **caller/tầng API ngoài outer proxy**, đồng thời sửa nguyên nhân rollback-only thay vì chỉ che thông báo.

### 10.2. Bỏ @Transactional ở inner để tránh rollback marker

Việc này có thể làm hết `UnexpectedRollbackException` ở một đường gọi, nhưng đổi cả semantics của inner, có thể dẫn đến partial commit hoặc không được rollback khi được gọi độc lập. Hãy làm rõ yêu cầu atomicity trước.

### 10.3. Đổi tất cả inner thành REQUIRES_NEW

Điều này không còn bảo đảm outer + inner cùng thành công/thất bại. Transaction độc lập có thể commit dù outer rollback, và tốn thêm connection. Chỉ dùng khi nghiệp vụ thực sự cần commit độc lập, ví dụ ghi audit độc lập với giao dịch chính, và đã xác nhận hậu quả phù hợp.

### 10.4. Tắt globalRollbackOnParticipationFailure

Một số manager dựa trên `AbstractPlatformTransactionManager` cho phép `setGlobalRollbackOnParticipationFailure(false)`. Khi đó, một participating scope thất bại với exception có thể nhường quyết định rollback cho transaction originator nếu tài nguyên vẫn commitable. **Đây không phải cách sửa mặc định an toàn**: Hibernate session hoặc transaction database sau lỗi dữ liệu có thể không thể tiếp tục; và `setRollbackOnly()` chủ động vẫn thể hiện quyết định rollback không nên bỏ qua. Không khuyến nghị đổi flag chỉ để ngăn exception xuất hiện.

### 10.5. “Xóa” rollback-only bằng cách catch thêm lần nữa

Không có API nghiệp vụ tổng quát để xóa một global rollback-only marker rồi commit như chưa có lỗi. Cách đúng là **thiết kế lại ranh giới**, xử lý lỗi trước khi transactional scope quyết định rollback, hoặc rollback toàn bộ rồi retry ở một **transaction mới** nếu thao tác idempotent và an toàn.

### 10.6. Dựa vào log INSERT/UPDATE success

SQL đã thực thi thành công vẫn chưa phải commit. Một số provider còn trì hoãn flush cho đến gần commit. Khi transaction cuối cùng rollback, các update thành công trước đó bị hủy. Kiểm tra từ một connection/transaction khác **sau khi boundary hoàn tất** là cách xác minh đúng.

## 11. Chọn hành vi đúng theo nhu cầu nghiệp vụ

| Nhu cầu | Hướng thiết kế phù hợp |
| --- | --- |
| Mọi bước phải atomic: inner thất bại thì hủy toàn bộ | Duy trì `REQUIRED`, để lỗi đúng loại lan ra ngoài outer; caller xử lý sau rollback |
| Inner báo lỗi nghiệp vụ có thể bỏ qua và muốn commit các bước khác | Tránh đặt rollback-only khi lỗi thực sự không cần rollback; kiểm tra rollback rules và tình trạng DB; không nuốt lỗi hạ tầng nguy hiểm |
| Inner cần commit/rollback riêng biệt với outer | Cân nhắc `REQUIRES_NEW` và tách boundary đúng proxy, chấp nhận độc lập tài nguyên/kết quả |
| Muốn chỉ hủy một phần SQL nhưng giữ outer transaction | Cân nhắc `NESTED`/savepoint khi manager và JDBC driver hỗ trợ |
| Đã đánh dấu rollback-only và muốn tiếp tục “thành công” | Không thể bảo đảm commit transaction ấy; hoàn tất rollback, trả kết quả lỗi đúng nghĩa hoặc bắt đầu transaction mới |
| Muốn thông báo lỗi sớm hơn thay vì chờ outer boundary | Xem `failEarlyOnGlobalRollbackOnly` ở manager tương ứng; chỉ thay thời điểm phát hiện, không thay kết quả cuối |

Điều đáng học nhất là **quy tắc propagation là quy tắc nhất quán**, không phải mẹo ngăn exception. Nếu muốn gọi một bước “best effort” mà lỗi của nó không ảnh hưởng phần còn lại, thiết kế dựa trên ý nghĩa nghiệp vụ và khả năng tiếp tục của tài nguyên; đừng đơn giản catch ở outer và giả định marker tự biến mất.

## 12. Quy trình debug UnexpectedRollbackException trên ứng dụng thật

1. **Xác định physical transaction bắt đầu ở đâu.** Lần gọi nào của proxy tạo transaction mới, và phương thức “outer” có thực sự sở hữu physical transaction không? Có `@Transactional` ở caller/test framework không?
2. **Xác định mọi logical REQUIRED scope** mà outer đã gọi. Đặc biệt chú ý các repository Spring Data, service được inject, transaction template và sự khác biệt lời gọi qua proxy với `this.method()`.
3. **Tìm exception gốc của inner.** Trước khi outer bắt lỗi và commit thất bại, đã có `RuntimeException`, exception translation từ DAO, checked exception có `rollbackFor` hay `setRollbackOnly()` chưa?
4. **Tìm vị trí catch/translate.** Catch xảy ra bên trong inner trước interceptor hay ở outer sau khi inner interceptor đã xử lý? Có code rethrow nguyên bản hay chuyển exception type?
5. **Xem rollback rules và status.** `rollbackFor`, `noRollbackFor`, custom global rules (nếu có) và flag rollback-only. Bật logging chỉ ở môi trường test, tránh lộ SQL/PII.
6. **Đọc chính xác stack trace.** `UnexpectedRollbackException` tại commit path không nhất thiết chứa exception nguyên nhân trong `getCause()`; hãy tìm log của **lỗi đầu tiên** đã bị catch/ghi trước đó.
7. **Kiểm tra transaction manager và tài nguyên.** JDBC `DataSourceTransactionManager`/`JdbcTransactionManager`, JPA `JpaTransactionManager` hoặc manager khác có behavior và nguồn connection nào? Đừng giả định mọi DAO dùng cùng transaction chỉ vì cùng DB URL.
8. **Tạo integration test có failure case.** Gọi outer qua Spring proxy từ test client không bọc transaction test; sau hoàn tất đọc dữ liệu từ session khác và assert toàn bộ biến đổi đã rollback.
9. **Kiểm tra giới hạn của môi trường test.** Spring TestContext thường rollback các `@Transactional` test theo mặc định; test transaction có thể làm method “outer” của ứng dụng chỉ là một logical scope tham gia.
10. **Sửa ranh giới theo ý nghĩa nghiệp vụ.** Giữ atomic transaction và để lỗi lan ra, hoặc lựa chọn independent/nested transaction có chủ đích; không chỉ bắt và bỏ exception.

Có thể tạm bật log:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
~~~

Log thực tế tùy manager/version. Khi dùng reactive transaction, status có thể gắn với **Reactor subscriber Context** thay vì ThreadLocal imperative; đừng sao chép nguyên một test `TransactionSynchronizationManager` từ JDBC để suy luận R2DBC. Điểm chung vẫn là logical scope, propagation và việc physical transaction được đánh dấu rollback-only.

## 13. Các nhầm lẫn thường gặp

| Kết luận sai | Cách hiểu đúng |
| --- | --- |
| “Outer bắt exception nên phải commit.” | Catch không xóa global rollback-only mà inner proxy đã đặt. |
| “Inner `REQUIRED` rollback riêng nhưng outer commit phần còn lại.” | REQUIRED tham gia **cùng physical transaction**; không có commit/rollback độc lập của inner. |
| “UnexpectedRollbackException phát sinh ngay trong thân outer.” | Thông thường nó phát sinh **ở proxy khi outer muốn commit sau return**, nếu không bật fail-early. |
| “UnexpectedRollbackException là chính exception gốc của inner.” | Đó là thông báo transaction bị rollback không như ý định commit; exception gốc có thể đã bị catch. |
| “Rollback xảy ra nên nhất định có UnexpectedRollbackException.” | Outer có thể chủ động rollback khi unchecked exception thoát ra hoặc tự set rollback-only; không nhất thiết throw exception này. |
| “Có `isActualTransactionActive() == true` là chắc chắn commit được.” | Active không đồng nghĩa commitable; rollback-only có thể đã true. |
| “Inner đã UPDATE thành công nên rollback-only không ảnh hưởng.” | UPDATE thành công trước commit vẫn có thể bị rollback toàn bộ. |
| “Tắt failEarly thì transaction sẽ commit được.” | Flag chỉ quyết định **thời điểm thông báo**, không sửa trạng thái rollback-only. |
| “Đổi sang `REQUIRES_NEW` luôn là cách khắc phục tốt.” | Nó thay đổi atomicity, commit độc lập, có rủi ro connection pool. |
| “Lệnh catch trong outer bắt được mọi lỗi của outer method.” | Lỗi commit sau return xảy ra tại transaction interceptor, ngoài thân method. |
| “Inner `@Transactional` cùng class luôn tạo logical scope riêng.” | Self-invocation ở proxy mode thường bỏ qua interception của inner. |
| “Chỉ JDBC mới có rollback-only.” | Nhiều Spring transaction manager khác cũng có khái niệm rollback-only; cách quản lý resource khác nhau. |

## 14. Bài tập kiểm tra hiểu đúng ranh giới hoàn tất

**Câu 1.** Outer `@Transactional(REQUIRED)` gọi inner bean khác `@Transactional(REQUIRED)`, inner ném `IllegalArgumentException`, outer catch và return. Manager mặc định, không có lỗi khác. Caller ngoài outer proxy thấy gì?

**Đáp án:** Inner advice đánh dấu shared transaction rollback-only; outer cố commit sau return, dẫn tới rollback và thường nhận `UnexpectedRollbackException`.

**Câu 2.** Giữ nguyên nhưng outer không catch lỗi inner, để exception ra ngoài proxy. Caller thấy gì?

**Đáp án:** Thường nhận `IllegalArgumentException` gốc, vì outer advice đã xử lý rollback theo exception thoát ra; không phải mặc định luôn nhận `UnexpectedRollbackException`.

**Câu 3.** Outer catch checked `IOException` từ inner. Inner không có `rollbackFor` và không có lỗi DB/marker khác. Điều gì có thể xảy ra?

**Đáp án:** Với policy mặc định trước các tùy chọn global rollback mới, inner advice **không bắt buộc rollback vì IOException**, nên outer có thể commit. Cần kiểm tra framework/config và rollback rules để kết luận.

**Câu 4.** Inner `REQUIRED` gọi `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` rồi return bình thường. Outer return bình thường. Có cần inner phải throw exception để outer rollback không?

**Đáp án:** Không. Marker đã đủ làm physical transaction không thể commit. Outer commit thường dẫn đến `UnexpectedRollbackException`.

**Câu 5.** Outer từ bên trong method `@Transactional` bắt được `UnexpectedRollbackException` bằng `try { inner(); } catch (UnexpectedRollbackException e)` trong khi inner chỉ là `REQUIRED`? Điều đó có chắc là lỗi outer completion theo mặc định?

**Đáp án:** Không chắc. Mặc định global rollback-only được báo ở **outermost boundary**. Một exception sớm có thể do config fail-early, nested call có physical boundary khác, hoặc lỗi tại một transaction manager khác. Phải xem call graph và stack trace.

**Câu 6.** Inner chuyển từ `REQUIRED` sang `REQUIRES_NEW`, catch exception ở outer. Có còn bảo đảm inner và outer cùng atomic không?

**Đáp án:** Không. Hai physical transaction độc lập; rollback inner không tự rollback outer, commit inner cũng không bị hủy nếu outer rollback về sau.

## 15. Ghi nhớ bản chất

**`UnexpectedRollbackException` ở ranh giới ngoài cùng là tín hiệu rằng Spring đã phải rollback một physical transaction mà bên ngoài đang muốn commit.** Mẫu nguyên nhân điển hình: inner `PROPAGATION_REQUIRED` đi qua proxy, gặp exception theo rollback rule hoặc đánh dấu rollback-only; outer catch lỗi rồi return bình thường.

Đọc tình huống theo trình tự **proxy boundary → logical scopes → rollback-only → physical commit/rollback**, không theo số lượng annotation hay số câu SQL đã chạy. Lỗi cần được giải quyết ở **quyết định transaction và thiết kế nghiệp vụ**, không bằng cách nuốt thêm exception.

## Tài liệu tham khảo

- [Spring Framework — Transaction Propagation: REQUIRED, REQUIRES_NEW, NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical vs physical transaction, rollback-only và nguyên nhân `UnexpectedRollbackException`.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): annotation advice và rollback policy.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): các thuộc tính propagation và rollback rules.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): checked/unchecked exception, `rollbackFor` và `noRollbackFor`.
- [Spring Framework — AbstractPlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `globalRollbackOnParticipationFailure` và `failEarlyOnGlobalRollbackOnly`.
