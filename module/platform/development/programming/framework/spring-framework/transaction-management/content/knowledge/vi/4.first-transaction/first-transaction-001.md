# Chuẩn bị thư viện Spring và cơ sở dữ liệu tương thích

## 1. Mục tiêu: sẵn sàng chạy giao dịch đầu tiên

Để một phương thức Spring dùng `@Transactional` thực sự có thể commit hoặc rollback dữ liệu, ứng dụng cần **thư viện quản lý transaction**, **công cụ truy cập database**, **JDBC driver**, **DataSource**, **transaction manager** và **database hỗ trợ transaction**. Thêm annotation vào code mới chỉ là một phần của công việc.

Sau bài này, bạn có thể:

1. Hiểu vai trò của từng dependency và chọn đúng JDBC/JPA stack.
2. Dựng một ứng dụng **Spring Boot + JDBC + H2** tối thiểu để học transaction mà không phải cài database server.
3. Chuyển sang **PostgreSQL** qua cấu hình profile, xác minh kết nối, schema và rollback.
4. Nhận biết các lỗi dependency/driver/cấu hình và biết lúc nào một transaction thật sự được áp dụng.

Các ví dụ dùng **Java 17, Spring Boot 3.3.13 (Spring Framework 6.x) và Gradle 8.5**: đây là một bộ phiên bản tương thích, được cố định để ví dụ có thể tái lập, không phải khẳng định chúng mới nhất. Với dự án dùng BOM/convention plugin nội bộ, giữ quản lý phiên bản của dự án thay vì chèn thêm plugin version tùy tiện.

> Lộ trình thực hành: chạy đúng với H2 trước, sau đó bật profile PostgreSQL. H2 hỗ trợ minh họa commit/rollback nhưng không phải bản sao hoàn hảo của PostgreSQL về SQL dialect, isolation, locking hay hành vi production.

## 2. Bản đồ thành phần và trách nhiệm

```text
Ứng dụng Spring Boot
    |
    | @Transactional  (Spring AOP / spring-tx)
    v
TransactionInterceptor -> PlatformTransactionManager
                                |
                                | quản lý transaction và JDBC Connection
                                v
                          DataSource / HikariCP
                                |
                                | JDBC driver phù hợp
                                v
                       H2 hoặc PostgreSQL
                                ^
                                |
                       JdbcTemplate / JDBC
```

| Thành phần | Trả lời câu hỏi nào? | Cách có trong bài |
| --- | --- | --- |
| `spring-tx` | Ai khai báo, bắt đầu, commit hoặc rollback transaction? | Starter JDBC kéo transitively |
| `spring-jdbc` | Java gửi SQL và tham gia Spring-managed transaction thế nào? | `spring-boot-starter-jdbc` |
| `JdbcTemplate` | Ai thực thi SQL `SELECT/UPDATE`, nhận kết quả và chuyển đổi JDBC exception? | Tự động có bean khi Boot cấu hình JDBC |
| `DataSource` / HikariCP | Connection đến database lấy từ đâu? | Starter JDBC + `spring.datasource.*` |
| JDBC driver | Ai giao tiếp với đúng protocol của database? | `com.h2database:h2` hoặc `org.postgresql:postgresql` |
| Database engine | Ai bảo đảm commit/rollback và các quy tắc dữ liệu? | H2 cho học tập, PostgreSQL cho kiểm chứng gần thực tế |
| Transaction proxy | Lời gọi `@Transactional` được intercept ở đâu? | Hạ tầng transaction Spring/Boot auto-config |

Với ứng dụng **JDBC đồng bộ**, Spring dùng một `PlatformTransactionManager` phù hợp với `DataSource` (ví dụ `JdbcTransactionManager`/`DataSourceTransactionManager`). `JdbcTemplate` làm việc với connection được Spring liên kết với transaction. Với **JPA**, transaction manager phù hợp với JPA/`EntityManagerFactory` và Hibernate quản lý persistence context.

Đừng nhầm các lớp:

- **Spring `@Transactional`** định nghĩa ranh giới transaction nghiệp vụ qua proxy/interceptor.
- **JDBC driver** chỉ cung cấp khả năng nói chuyện với database; không tự xác định ranh giới transaction của cả method.
- **Database** là nơi thực sự áp dụng COMMIT/ROLLBACK. Trong JDBC, `jdbc.update(...)` có thể đã gửi SQL nhưng transaction vẫn chưa commit.
- **JPA EntityManager** thêm một tầng theo dõi entity/flush. Bài này ưu tiên JDBC để thấy hành vi SQL trực tiếp.

### Kiểm tra database có phù hợp

- Database cần cơ chế transaction; PostgreSQL đáp ứng. Với MySQL, hãy sử dụng table engine có transaction như InnoDB, không dùng MyISAM cho ví dụ rollback.
- JDBC URL và driver phải cùng loại DB: `jdbc:h2:...` với H2; `jdbc:postgresql://...` với PostgreSQL. URL `r2dbc:...` dành cho stack reactive khác.
- Tài khoản có quyền kết nối, tạo và thao tác bảng cần cho demo; môi trường thật nên cấp quyền tối thiểu và không lưu mật khẩu trong Git.
- Các phiên bản Spring, Gradle, Java và driver cần nằm trong dải tương thích của bộ công cụ. Không trộn dependency thuộc Spring Boot 2.x với 3.x.

## 3. Chọn bộ thư viện tối thiểu: Spring Boot Starter JDBC

`JdbcTemplate` là lựa chọn dễ quan sát cho giao dịch đầu tiên: chúng ta tự viết hai câu SQL và kiểm tra cả hai rollback khi một bước sau thất bại. Không cần `spring-boot-starter-web` hay ORM nếu chưa dùng HTTP hoặc JPA.

Tạo một project Spring Boot độc lập, Gradle Groovy DSL, Java 17, có Gradle Wrapper. **`build.gradle`**:

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

    // Hai driver có thể cùng nằm trên classpath.
    // JDBC URL của profile chọn DB thực tế cần kết nối.
    runtimeOnly 'com.h2database:h2'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`settings.gradle`**:

```groovy
rootProject.name = 'tx-lab'
```

Giải thích các dependency:

- `spring-boot-starter-jdbc` đã đưa vào Spring JDBC, hạ tầng Spring transaction và HikariCP. Không cần khai `spring-tx` lần nữa chỉ để dùng `@Transactional`.
- `runtimeOnly` phù hợp vì code biên dịch dựa trên các API JDBC/Spring JDBC; JDBC driver thực sự cần lúc chạy. Nếu chỉ học trên H2, có thể bỏ PostgreSQL driver và ngược lại.
- Spring Boot dependency management chọn version tương thích cho thư viện được quản lý; đừng ghi version riêng cho starter, H2 hay PostgreSQL driver nếu không có lý do.
- `io.spring.dependency-management` trong cấu hình Gradle này giúp áp dụng BOM do Spring Boot plugin quản lý. Khi dùng build convention đã có sẵn version catalog/BOM, hãy tuân thủ cách làm của project đó.
- `@Transactional` trong ví dụ import `org.springframework.transaction.annotation.Transactional`.

Kiểm tra môi trường ở thư mục project:

```bash
java -version
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
```

Trên Windows dùng `gradlew.bat` thay `./gradlew`. Java phải tương thích với Spring Boot; Gradle cần tìm được toolchain JDK 17. `runtimeClasspath` phải có `spring-jdbc`, HikariCP và driver bạn định kết nối. Nếu dependency resolution lỗi, giải quyết trước khi chạy nghiệp vụ: Maven Central/Plugin Portal, proxy mạng, plugin Gradle không phù hợp hoặc dependency override sai đều có thể là nguyên nhân.

## 4. Cấu hình H2 cho bài thực hành đầu tiên

Đặt các file như sau:

```text
tx-lab/
├── build.gradle
├── settings.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/transaction/
    │   ├── TxLabApplication.java
    │   └── TransferService.java
    └── resources/
        ├── application.yml
        ├── application-postgres.yml
        ├── schema.sql
        └── data.sql
```

**`src/main/resources/application.yml`**:

```yaml
spring:
  application:
    name: tx-lab
  datasource:
    url: "jdbc:h2:mem:txlab;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

`jdbc:h2:mem:txlab` tạo database **trong bộ nhớ của JVM**; dữ liệu không được giữ khi process kết thúc. `DB_CLOSE_DELAY=-1` giữ DB sống tới khi JVM dừng ngay cả khi connection cuối cùng đóng; nó **không** làm H2 bền vững như database ghi ra ổ đĩa.

`spring.sql.init.mode=always` chạy script khởi tạo SQL khi ứng dụng start. Spring Boot cũng hỗ trợ tự khởi tạo embedded DB theo mặc định; ta đặt rõ property này để luồng demo dễ đối chiếu sau khi chuyển profile. Driver class thường được suy ra từ JDBC URL, không bắt buộc ghi thêm `spring.datasource.driver-class-name`.

**`src/main/resources/schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);
```

**`src/main/resources/data.sql`**:

```sql
-- Chỉ dùng trên database thực hành riêng: reset dữ liệu mỗi lần boot.
DELETE FROM accounts;
INSERT INTO accounts (id, balance) VALUES (1, 100);
INSERT INTO accounts (id, balance) VALUES (2, 100);
```

Hai tài khoản giúp kiểm tra một nghiệp vụ chuyển 10 đơn vị mà tổng số dư vẫn bằng 200. Script `data.sql` chủ động xóa dữ liệu trước mỗi lần chạy; **không sử dụng trên production hay database lưu dữ liệu cần giữ**. Trong hệ thống thật dùng migration versioned (Flyway hoặc Liquibase), seed dữ liệu test độc lập và kiểm soát quyền DB.

### Có cần `@EnableTransactionManagement` hay tạo `DataSource` bean thủ công?

Với **Spring Boot auto-configuration**, một `DataSource` hợp lệ cùng starter JDBC thường đủ để Boot cấu hình `JdbcTemplate` và transaction manager phù hợp; bạn không cần tự khai `@Bean DataSource`, tạo connection pool hay đặt `@EnableTransactionManagement` thủ công để chạy ví dụ này. Trong **Spring Framework không dùng Boot**, hoặc khi bạn vô hiệu hóa auto-configuration, bạn phải chủ động cung cấp infrastructure tương ứng.

## 5. Thực hiện một transaction và một rollback

Hai class sau thuộc cùng package `demo.transaction`. Đây là mã ứng dụng **Spring Boot đầy đủ khi kết hợp build.gradle, application.yml và SQL files phía trên**; nó không phải một file Java có thể chạy độc lập bằng `javac` vì cần Spring và database dependencies.

**`src/main/java/demo/transaction/TransferService.java`**:

```java
package demo.transaction;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        move(fromId, toId, amount);
    }

    @Transactional
    public void transferThenFail(long fromId, long toId, long amount) {
        move(fromId, toId, amount);
        throw new IllegalStateException("simulated failure");
    }

    private void move(long fromId, long toId, long amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? "
                + "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalArgumentException(
                "Source missing or insufficient balance");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalArgumentException("Destination missing");
        }
    }
}
```

**`src/main/java/demo/transaction/TxLabApplication.java`**:

```java
package demo.transaction;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class TxLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxLabApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService service, JdbcTemplate jdbc) {
        return args -> {
            System.out.println("Before: " + balances(jdbc));

            try {
                service.transferThenFail(1L, 2L, 10L);
            } catch (IllegalStateException ex) {
                System.out.println("Caught: " + ex.getMessage());
            }

            System.out.println("After rollback: " + balances(jdbc));

            service.transfer(1L, 2L, 10L);
            System.out.println("After commit: " + balances(jdbc));
        };
    }

    private static String balances(JdbcTemplate jdbc) {
        Long first = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = 1", Long.class);
        Long second = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = 2", Long.class);
        return first + " / " + second;
    }
}
```

Chạy trên Linux/macOS:

```bash
./gradlew bootRun
```

Chạy trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giữa nhiều log của Spring Boot, bốn dòng `System.out.println` có nội dung theo thứ tự:

```text
Before: 100 / 100
Caught: simulated failure
After rollback: 100 / 100
After commit: 90 / 110
```

**Vì sao kết quả này đáng tin?**

1. Spring Boot kết nối H2, chạy `schema.sql` và `data.sql` trước khi `CommandLineRunner` truy vấn bảng.
2. `transferThenFail` thực thi hai câu `UPDATE` rồi ném `IllegalStateException`. Đây là unchecked exception, mặc định Spring rollback transaction.
3. Sau khi proxy xử lý rollback và chuyển exception ra ngoài, runner đọc lại DB ở lời gọi `balances(jdbc)`: kết quả trở lại `100 / 100`.
4. `transfer` hoàn tất bình thường và transaction do proxy điều phối được commit trước khi lời gọi trả về; lần đọc cuối là `90 / 110`.

Điểm quan trọng: runner được inject **Spring-managed `TransferService`**, nên lời gọi `service.transfer(...)` đi qua transaction proxy. Nếu tự gọi một method `@Transactional` khác ngay bên trong cùng bean (*self-invocation*), proxy mode thông thường **không** áp dụng advice mới cho lời gọi nội bộ. Cũng không nên tự khởi tạo service bằng `new` ngoài container rồi kỳ vọng `@Transactional` hoạt động.

Trong JDBC, `jdbc.update(...)` gửi SQL tới DB trong transaction đang mở. **SQL đã thực thi không đồng nghĩa đã commit**. Khi method kết thúc với unchecked exception, transaction manager gọi rollback; nếu mỗi `UPDATE` được chạy ở connection autocommit độc lập thì dữ liệu sẽ không có tính nguyên tử như ví dụ.

## 6. Kết nối PostgreSQL bằng profile riêng

H2 hữu ích để bắt đầu, nhưng một phần kiểm thử transaction cần thực hiện trên đúng DB engine production. PostgreSQL phù hợp để thực hành sâu hơn về constraints, locking, isolation và deadlock. Ví dụ sau chuyển DB bằng **configuration**, không phải sửa Java service.

### 6.1. Khởi chạy PostgreSQL cục bộ

Khi có Docker và cổng 5432 chưa bị sử dụng:

```bash
docker run -d --name txlab-postgres \
  -e POSTGRES_DB=txlab \
  -e POSTGRES_USER=txlab \
  -e POSTGRES_PASSWORD=local_only \
  -p 5432:5432 postgres:16
```

Trên Windows PowerShell có thể dùng một dòng:

```powershell
docker run -d --name txlab-postgres -e POSTGRES_DB=txlab -e POSTGRES_USER=txlab -e POSTGRES_PASSWORD=local_only -p 5432:5432 postgres:16
```

Đây là mật khẩu **chỉ dùng local demo**, không phải mẫu cấu hình secret production. Kiểm tra tiến trình DB đã nhận kết nối:

```bash
docker ps --filter "name=txlab-postgres"
docker exec txlab-postgres pg_isready -U txlab -d txlab
```

Đầu ra của `pg_isready` cần báo `accepting connections`. Nếu database được cài ngoài Docker, tự chuẩn bị database `txlab`, user hợp lệ, host và cổng tương ứng.

### 6.2. Đổi profile và chạy

Trong `build.gradle` đã có `runtimeOnly 'org.postgresql:postgresql'`. Tạo **`src/main/resources/application-postgres.yml`**:

```yaml
spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/txlab"
    username: ${DB_USER:txlab}
    password: ${DB_PASSWORD:local_only}
  sql:
    init:
      mode: always
```

Chạy trên Linux/macOS:

```bash
./gradlew bootRun --args='--spring.profiles.active=postgres'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=postgres"
```

Khi bật profile `postgres`, `spring.datasource.url` trong file profile ghi đè URL H2 trong `application.yml`. Không phụ thuộc vào Spring Boot đoán driver; URL `jdbc:postgresql://...` phải có PostgreSQL driver trong runtime classpath. `schema.sql` và `data.sql` ở bài này dùng cú pháp tương thích cả H2 lẫn PostgreSQL; với `spring.sql.init.mode=always`, PostgreSQL **cũng reset dữ liệu thực hành mỗi lần boot**.

Sau khi app chạy xong, xem trạng thái bảng trong PostgreSQL:

```bash
docker exec txlab-postgres psql -U txlab -d txlab \
  -c "SELECT id, balance FROM accounts ORDER BY id;"
```

Kết quả truy vấn tương ứng với hai hàng:

```text
 id | balance
----+---------
  1 |      90
  2 |     110
(2 rows)
```

Nếu lần chạy khác đọc `100 / 100`, kiểm tra xem ứng dụng vừa khởi động lại và script `data.sql` đã reset dữ liệu hay chưa. Với production, dùng migration và **không** đặt `mode=always` kèm file `data.sql` chứa `DELETE`; nên tắt script initialization sau khi chuyển sang Flyway/Liquibase. Tách tài khoản, profile và secret của từng môi trường để tránh kết nối nhầm DB.

### 6.3. Khi nào H2 không thay thế được PostgreSQL?

| Tiêu chí | H2 in-memory | PostgreSQL |
| --- | --- | --- |
| Chạy bài tập không cài server | Tốt | Cần server/container |
| Học transaction boundary, rollback SQL cơ bản | Tốt | Tốt |
| Dữ liệu sau khi process JVM kết thúc | Mất với URL `mem:` | Có thể giữ nếu server/storage được duy trì |
| SQL dialect và kiểu dữ liệu PostgreSQL | Không bảo đảm giống | Đúng engine |
| Lock, deadlock, isolation, query planner | Không nên suy rộng kết quả | Nên kiểm thử trực tiếp |
| Triển khai sản xuất | Không chọn H2 in-memory làm nơi lưu chính | Là lựa chọn production phổ biến |

Đặc biệt, “cùng JDBC API” không có nghĩa hai DB xử lý SQL, DDL, isolation hay error code y hệt nhau. Nếu DB thật là MySQL/SQL Server/Oracle, kiểm thử trên chính engine đó.

## 7. Chuyển từ JDBC sang JPA cần thay đổi gì?

Nếu bài học hoặc dự án dùng entity, repository và Hibernate thay cho `JdbcTemplate`, starter phù hợp là **`spring-boot-starter-data-jpa`**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Starter JPA kéo theo Hibernate, Spring Data JPA, Spring ORM và thành phần JDBC cần thiết. Với một `DataSource` và JPA setup điển hình, Spring Boot cấu hình transaction manager phù hợp JPA. **Không cần thêm JDBC starter chỉ để lấy Spring JDBC cơ bản** vì JPA starter đã bao gồm các phụ thuộc liên quan; chỉ thêm stack khác khi thực sự dùng nó.

Khác biệt cần nhớ:

- `JdbcTemplate` gửi câu SQL khi gọi `update`; JPA có `Persistence Context`, dirty checking và flush, nên thay đổi entity có thể được đồng bộ sau.
- Spring Boot 3.x dùng `jakarta.persistence.*`, không dùng `javax.persistence.*` trong các ví dụ JPA đời cũ.
- Không dùng `spring.jpa.hibernate.ddl-auto=create` hoặc `create-drop` trên database thật có dữ liệu. `ddl-auto=update` cũng không thay thế công cụ migration versioned cho production.
- Không bật song song cơ chế tự tạo schema của Hibernate và SQL initialization/migration mà không chủ động kiểm soát thứ tự; trong ví dụ JDBC ở bài này không cần Hibernate.
- Nếu trộn JDBC/JPA hoặc nhiều DataSource, xác định chính xác transaction manager nào sở hữu tài nguyên nào. Một `@Transactional` thông thường không tự biến nhiều DB độc lập thành distributed transaction.

Để học giao dịch đầu tiên, chọn **một stack trước**: JDBC đơn giản để xem SQL, hoặc JPA khi đã nắm entity và persistence context.

## 8. Kiểm tra từng tầng khi khởi động thất bại

| Hiện tượng | Nguyên nhân có thể | Bước xác minh |
| --- | --- | --- |
| `Failed to configure a DataSource` | Thiếu URL/embedded DB/driver, profile chưa đúng | Kiểm tra `spring.datasource.*` và dependency runtime |
| `Cannot load driver class` hoặc `No suitable driver` | Driver không nằm trong runtime classpath hoặc URL không đúng | Kiểm tra `gradlew dependencies`, driver H2/PostgreSQL |
| `Connection refused` | PostgreSQL chưa chạy, host/port sai | `docker ps`, `pg_isready`, port 5432 |
| `password authentication failed` | Sai user/password hoặc secret không đồng bộ | Kiểm tra user và môi trường chạy |
| `Table "ACCOUNTS" not found` / `relation "accounts" does not exist` | Schema initialization chưa chạy hoặc nối nhầm database | Xem `schema.sql`, `mode`, active profile, quyền tạo bảng |
| Lỗi `NoUniqueBeanDefinitionException` về manager | Có nhiều transaction managers và không chọn rõ | Rà bean manager, chỉ định `@Transactional(transactionManager = "...")` khi cần |
| Không rollback sau lỗi | Method không qua Spring proxy, exception bị bắt mất hoặc không khớp rollback rule | Dùng bean được inject, để unchecked exception thoát ra hoặc khai rollback rules |
| Chạy lại thấy dữ liệu mất/trở lại trạng thái gốc | H2 `mem` kết thúc hoặc `data.sql` reset | Xác nhận đúng môi trường demo; không dùng reset script trên DB thật |
| H2 chạy nhưng PostgreSQL lỗi | SQL dialect, schema, constraint hoặc cấu hình khác | Đọc SQL exception và thử với PostgreSQL thật |

### Checklist ngắn trước khi nói “transaction đã sẵn sàng”

1. JDK, Gradle, phiên bản Spring Boot và graph dependency tương thích.
2. Có starter truy cập dữ liệu thích hợp và driver khớp JDBC URL.
3. DataSource kết nối đúng database, đúng user/port/schema.
4. Transaction manager phù hợp và được chọn rõ khi có nhiều manager.
5. Lời gọi `@Transactional` thực sự đi qua Spring-managed proxy.
6. Schema/data được tạo trên đúng DB, không reset nhầm dữ liệu thật.
7. Case thành công commit và case lỗi rollback đã được kiểm tra bằng **đọc lại database sau khi method kết thúc**.

Nếu ứng dụng chỉ kết nối DB được và chạy `UPDATE`, vẫn chưa đủ chứng minh transaction toàn nghiệp vụ. Khi câu SQL thứ nhất đã commit riêng bằng autocommit, lỗi ở câu SQL thứ hai không thể tự hoàn tác câu thứ nhất. Thử kịch bản thất bại nằm **sau cả hai câu UPDATE**, như `transferThenFail`, sẽ cho thấy transaction manager có thực sự bao quanh chúng hay không.

## 9. Chuẩn bị đúng cho môi trường ngoài demo

- **Dữ liệu và schema:** dùng migration kiểm soát version, seed test riêng, backup phù hợp. Không chạy script xóa dữ liệu khi startup ở production.
- **Credentials:** đọc từ environment/secret manager, dùng tài khoản ít quyền nhất có thể; không đẩy secret thật lên Git.
- **Connection pool:** giữ pool size/timeouts phù hợp; tránh mở `DriverManager.getConnection(...)` riêng bên trong service vì connection đó có thể không tham gia Spring transaction.
- **Transaction boundary:** gọi qua Spring bean proxy; hạn chế transaction kéo dài qua HTTP call hoặc thao tác chờ người dùng.
- **Quan sát:** log SQL/error có mục đích và không log dữ liệu nhạy cảm. Tắt transaction debug quá chi tiết trong production nếu không cần.
- **Kiểm thử đúng DB:** với hành vi isolation, locking, deadlock, constraint hoặc dialect, dùng PostgreSQL/MySQL engine thật (có thể sử dụng Testcontainers trong integration tests). H2 chỉ là bước khởi động.
- **Reactive:** nếu chuyển sang R2DBC, dùng reactive connection factory và `ReactiveTransactionManager`; không trộn cơ chế JDBC thread-bound vào pipeline reactive rồi kỳ vọng transaction tự lan truyền.

## 10. Câu hỏi tự kiểm tra

1. **Chỉ có dependency `spring-tx` là đủ kết nối PostgreSQL chưa?** Chưa: cần JDBC layer, driver, DataSource, database server và cấu hình tương ứng.
2. **Vì sao có H2 driver vẫn không kết nối được `jdbc:postgresql://...`?** H2 driver nói protocol H2; PostgreSQL yêu cầu driver PostgreSQL.
3. **Tại sao example dùng `@Transactional` trên public service methods?** Để lời gọi từ runner đi qua Spring transaction proxy; private helper chỉ được gọi bên trong transaction đã mở.
4. **Vì sao sau rollback lại cần query mới?** Để quan sát trạng thái DB sau khi transaction manager đã xử lý rollback, không nhầm SQL gửi đi với dữ liệu đã commit.
5. **H2 chạy thành công thì có bỏ kiểm thử PostgreSQL được không?** Không, vì dialect/isolation/locking và lỗi production có thể khác.
6. **Khi thay bằng JPA, một managed entity sửa field có nhất thiết gửi UPDATE ngay?** Không. JPA/Hibernate có thể trì hoãn SQL tới flush; vẫn cần transaction manager và DB thật sự commit.

**Ghi nhớ:** Một giao dịch đầu tiên đáng tin cần **đúng dependency + driver + DataSource + transaction manager + database có transaction + phép thử commit/rollback**. Khi môi trường đã ổn, mới nên học sâu các chính sách propagation, isolation, timeout, rollback rules và JPA flush.

## Tài liệu đối chiếu

- Spring Boot 3.3, yêu cầu Java/Gradle: https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3, SQL Databases / JDBC / DataSource / JPA: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
- Spring Boot, Database Initialization: https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html
- Spring Framework, Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework, Declarative Transactions và proxy: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Boot Gradle Plugin 3.3.13: https://plugins.gradle.org/plugin/org.springframework.boot/3.3.13
- Dependency Management Gradle Plugin 1.1.7: https://plugins.gradle.org/plugin/io.spring.dependency-management/1.1.7
- PostgreSQL JDBC driver documentation: https://jdbc.postgresql.org/documentation/
