# Mối liên hệ giữa nghiệp vụ, tầng dữ liệu, kết nối và cơ sở dữ liệu

> **Phạm vi:** Bài học giải thích đường đi của một thao tác nghiệp vụ trong ứng dụng Spring Framework dùng cơ sở dữ liệu quan hệ: từ Service, qua Repository/DAO, API truy cập dữ liệu, kết nối JDBC, đến hệ quản trị cơ sở dữ liệu (DBMS). Spring JDBC là ví dụ thực hành; phần so sánh với JPA giúp nhận ra những điểm chung và khác biệt. Đây là các vai trò logic, không nhất thiết tương ứng với bốn máy chủ hay bốn tiến trình riêng.

## 1. Hình dung toàn cảnh

Giả sử người dùng yêu cầu **chuyển 30 đơn vị tiền từ tài khoản A sang B**. Nghiệp vụ đòi hỏi số tiền dương, tài khoản nguồn có đủ số dư và hai thay đổi số dư phải thành công hoặc thất bại cùng nhau. Ứng dụng không nên để màn hình/API tự lắp câu SQL; nó giao việc cho Service. Service sử dụng Repository để đọc/ghi dữ liệu, Repository dùng công cụ truy cập dữ liệu của Spring, công cụ này mượn kết nối đến DBMS từ DataSource.

~~~mermaid
flowchart TD
    Client["HTTP controller / CLI / scheduled job"] --> Service["Service: quy tắc và điều phối nghiệp vụ"]
    Service --> Repo["Repository / DAO: thao tác dữ liệu"]
    Repo --> API["JdbcTemplate / JPA EntityManager"]
    API --> DS["DataSource: nguồn kết nối, thường có pool"]
    DS --> JDBC["JDBC Driver + Connection"]
    JDBC <--> DB[("Cơ sở dữ liệu quan hệ")]
~~~

Mũi tên thể hiện **quan hệ gọi hoặc phụ thuộc**. Trên đường về, DBMS trả kết quả SQL; JDBC và lớp truy cập dữ liệu chuyển kết quả thành giá trị/đối tượng Java; Repository trả dữ liệu cho Service; Service quyết định kết quả nghiệp vụ. Với JPA, một JPA provider (như Hibernate) đứng giữa EntityManager và JDBC, có thể trì hoãn SQL đến lúc flush.

**Phân biệt cốt lõi:** Service quyết định *điều gì được phép xảy ra*; Repository quyết định *cần truy vấn hoặc cập nhật dữ liệu nào*; DataSource/Connection quyết định *ứng dụng giao tiếp với DBMS qua phiên kết nối nào*; DBMS thực thi truy vấn, quản lý giao dịch và lưu giữ dữ liệu.

## 2. Trách nhiệm và ranh giới của từng tầng

| Thành phần | Trả lời câu hỏi | Thường chứa | Không nên gánh |
| --- | --- | --- | --- |
| Controller / bộ kích hoạt | Ai gọi, đầu vào/đầu ra có dạng gì? | Ánh xạ HTTP, xác thực đầu vào ở ranh giới, mã trạng thái | SQL, quản lý Connection hoặc quy tắc nghiệp vụ phức tạp |
| Service nghiệp vụ | Thao tác có hợp lệ và cần những bước nào? | Quy tắc, kiểm tra điều kiện, điều phối nhiều repository, ranh giới giao dịch | Chi tiết mở/đóng JDBC Connection hay câu SQL của từng bảng |
| Repository / DAO | Lấy hoặc ghi dữ liệu bằng cách nào? | SQL hoặc truy vấn JPA, tham số, ánh xạ hàng dữ liệu, thao tác CRUD | Chính sách nghiệp vụ thuộc nhiều đối tượng hoặc điều phối workflow |
| Spring Data Access | Đơn giản hóa tương tác lưu trữ như thế nào? | JdbcTemplate, JdbcClient, EntityManager, dịch ngoại lệ, phối hợp giao dịch | Định nghĩa ý nghĩa nghiệp vụ |
| DataSource và pool | Lấy, tái sử dụng, trả kết nối như thế nào? | Cấu hình URL, credentials, giới hạn pool, timeout | Phân xử một giao dịch chuyển tiền có hợp lệ |
| JDBC Driver / Connection | Gửi lệnh đến DBMS qua kết nối nào? | Giao thức, PreparedStatement, ResultSet, trạng thái giao dịch | Nắm toàn bộ quy tắc nghiệp vụ |
| DBMS | Đọc, ghi, khóa, bảo toàn dữ liệu ra sao? | Bảng, chỉ mục, ràng buộc, SQL, log giao dịch, isolation, commit/rollback | Quyết định toàn bộ chính sách nghiệp vụ của ứng dụng |

Một **domain object** biểu diễn khái niệm nghiệp vụ; một **row/entity** biểu diễn dữ liệu lưu trữ. Chúng có thể giống nhau trong ứng dụng nhỏ, nhưng không buộc phải trùng cấu trúc. Chẳng hạn, Service trả về `TransferReceipt` mà không cần để bên gọi biết bảng `account` có bao nhiêu cột. Cách tách này giúp thay schema, thay công nghệ lưu trữ hoặc kiểm thử quy tắc nghiệp vụ mà giảm ảnh hưởng giữa các tầng.

Repository là một ranh giới thiết kế: với Spring JDBC, ta thường tự viết SQL trong lớp `@Repository`; với Spring Data JPA, có thể khai báo interface kế thừa `JpaRepository` và để framework tạo implementation. Không phải mọi Repository đều trực tiếp mở Connection.

## 3. Một yêu cầu đi xuống DB rồi quay về như thế nào?

Với ví dụ chuyển tiền sử dụng Spring JDBC:

1. **Nhận lệnh:** Controller hoặc tác vụ nền tạo yêu cầu `transfer(A, B, 30)`, xác định người gọi và kiểm tra định dạng đầu vào.
2. **Vào Service:** Service xác minh số tiền dương, hai tài khoản khác nhau, và tổ chức việc ghi nợ/ghi có. Service thường là nơi đặt `@Transactional` vì thao tác cần một kết quả nghiệp vụ nguyên tử.
3. **Gọi Repository:** Service yêu cầu Repository trừ tiền của A và cộng tiền cho B. Repository mô tả thao tác bằng SQL có tham số.
4. **Spring truy cập dữ liệu:** `JdbcTemplate` lấy Connection phù hợp với ngữ cảnh giao dịch đang hoạt động; nó tạo PreparedStatement, gắn tham số, thực thi và xử lý tài nguyên JDBC.
5. **DataSource và driver:** DataSource thường lấy một kết nối từ pool; JDBC driver truyền lệnh đến DBMS. Kết nối có thể đã được lấy từ trước khi câu SQL đầu tiên chạy, tùy transaction manager/cấu hình.
6. **DBMS xử lý:** DBMS kiểm tra ràng buộc, thực thi UPDATE, quản lý khóa và trạng thái giao dịch; nó trả số hàng bị tác động hoặc dữ liệu truy vấn.
7. **Kết quả đi lên:** Repository báo số hàng cập nhật; Service quyết định thành công hay ném exception. Transaction manager commit nếu hoàn tất đúng, rollback nếu xảy ra lỗi thuộc quy tắc rollback. Tài nguyên được giải phóng, kết nối logic trả về pool.

Một lời gọi Service có thể tạo **nhiều lệnh SQL** nhưng vẫn thuộc **một giao dịch cơ sở dữ liệu**. Ngược lại, một lần lấy Connection không có nghĩa tự động đảm bảo toàn bộ workflow đã được bao bởi giao dịch nghiệp vụ.

### Đường đi của một thao tác đọc

Với yêu cầu `getBalance(accountId)`, Service có thể gọi Repository để `SELECT balance ... WHERE id = ?`. DBMS trả một dòng; JdbcTemplate ánh xạ cột thành `BigDecimal`; Service trả về giá trị hoặc kiểu phản hồi phù hợp. Truy vấn đọc thường không cần khởi tạo một giao dịch ghi dài, nhưng có thể cần cùng snapshot/transaction khi tính nhất quán nhiều lần đọc quan trọng.

### Đường đi của một thao tác ghi

Với UPDATE, Repository nên kiểm tra số hàng bị tác động. `0 rows updated` có thể nghĩa là bản ghi không tồn tại hoặc điều kiện tiền đề không thỏa, chứ không mặc nhiên là thành công. Service chuyển tín hiệu kỹ thuật đó thành kết quả có ý nghĩa nghiệp vụ. Ràng buộc của DB (primary key, unique, foreign key, check) là hàng rào bảo vệ tính nhất quán cuối cùng, kể cả khi nhiều yêu cầu chạy đồng thời.

## 4. DataSource, Connection, pool và transaction không phải một khái niệm

- **DataSource:** Đối tượng Java cấu hình nguồn kết nối; `getConnection()` trả một JDBC Connection. Ứng dụng Spring Boot thường tự cấu hình DataSource từ `spring.datasource.*` khi có thư viện JDBC và driver phù hợp.
- **Connection:** Đại diện cho phiên làm việc với DBMS. Nó có trạng thái như auto-commit, isolation, thời điểm bắt đầu/kết thúc giao dịch, session settings. Không chia sẻ tùy tiện một Connection giữa các request/luồng.
- **Connection pool:** Tập kết nối có thể tái sử dụng (ví dụ HikariCP). Borrow → dùng → `close()` trên connection được pool cung cấp thường là **trả về pool**, không phải đóng socket vật lý ngay. Pool giảm chi phí tạo kết nối nhưng không biến SQL chậm thành nhanh.
- **Transaction:** Đơn vị công việc cần commit hoặc rollback cùng nhau, được quản lý qua Connection hoặc bởi transaction manager tương ứng. Trong bài toán JDBC dùng một DataSource, Spring thường liên kết một Connection vào ngữ cảnh giao dịch của luồng thực thi để các lời gọi JdbcTemplate cùng tham gia.

**Quan hệ cần nhớ:** DataSource cấp Connection; Spring transaction manager quản lý ranh giới giao dịch và phối hợp Connection; JdbcTemplate dùng Connection đó để phát SQL; DBMS quyết định kết quả commit/rollback theo bảo đảm giao dịch của nó.

Ví dụ sai thường gặp: gọi `dataSource.getConnection()` thủ công trong một đoạn Service đã gắn `@Transactional`, sau đó gọi `commit()` riêng. Kết nối tự lấy không đương nhiên là kết nối Spring đã ràng buộc với transaction; làm vậy có thể tạo hai giao dịch độc lập. Với JDBC, ưu tiên `JdbcTemplate` hoặc công cụ giao dịch Spring như `DataSourceUtils` nếu cần truy cập JDBC mức thấp, và để Spring quản lý commit/rollback.

Pool có thể có 10 kết nối phục vụ nhiều request; một request giữ transaction quá lâu có thể chiếm một kết nối, làm request khác chờ pool. Quy mô pool là tài nguyên hữu hạn, không phải số lượng transaction được phép chạy vô hạn.

## 5. Ranh giới giao dịch nằm ở đâu?

Trong một thao tác chuyển tiền, **nghiệp vụ** yêu cầu cả hai UPDATE thuộc cùng đơn vị nguyên tử. Vì vậy đặt `@Transactional` trên **public method của Service được gọi qua Spring proxy** thường phù hợp hơn đặt mỗi Repository method trong giao dịch riêng:

~~~text
Bắt đầu Service.transfer(...) qua Spring proxy
    BEGIN / tham gia transaction
        Repository.debit(A, 30)  --> UPDATE account ...
        Repository.credit(B, 30) --> UPDATE account ...
    Nếu mọi điều kiện đạt: COMMIT
    Nếu lỗi cần rollback: ROLLBACK
Kết thúc: dọn ngữ cảnh transaction và trả Connection
~~~

Nếu debit commit độc lập rồi credit lỗi, dữ liệu có thể chỉ bị trừ ở A. Khi hai lệnh nằm trong cùng một giao dịch, một exception phù hợp sẽ khiến rollback cả hai. Các thao tác trên DBMS vẫn chịu quy tắc isolation và cạnh tranh đồng thời: **atomicity** không có nghĩa tự động không có deadlock, lost update hoặc mọi anomaly.

Các điểm dễ nhầm:

- Theo cấu hình mặc định của Spring transaction, `RuntimeException` và `Error` khiến rollback; checked exception thường cần cấu hình, ví dụ `@Transactional(rollbackFor = IOException.class)` khi phù hợp.
- Trong proxy mode thông dụng, lời gọi `this.transfer(...)` từ một method khác của **cùng đối tượng** không đi qua proxy, nên annotation trên phương thức được gọi nội bộ có thể không có tác dụng như mong đợi.
- `@Transactional(readOnly = true)` chủ yếu là hint tối ưu/định hướng cho tài nguyên liên quan, không đảm bảo mọi DBMS sẽ từ chối ghi.
- Transaction JDBC trên một DataSource không tự tạo một transaction nguyên tử xuyên hai database hoặc một HTTP API bên ngoài. Khi workflow qua nhiều hệ thống, cần thiết kế riêng (ví dụ outbox, retry có idempotency, bù trừ).
- Không để thao tác chờ người dùng, gọi API mạng lâu hoặc xử lý CPU kéo dài giữ Connection/lock trong giao dịch khi có thể tách ra.

## 6. Ví dụ chạy được: Service → Repository → JDBC → H2

Ví dụ dùng **Java 21, Gradle, Spring Boot 3.3.5, Spring JDBC và H2**. H2 chạy trong bộ nhớ giúp tái hiện đường đi dữ liệu mà không cần cài database server. Có ba file Java, ba file cấu hình/SQL và một `build.gradle`. Trong thực tế thay H2 bằng PostgreSQL/MySQL bằng cách cấu hình driver, URL và kiểm tra lại SQL dialect.

Cấu trúc tối thiểu:

~~~text
build.gradle
src/main/java/com/example/dataaccess/DataAccessDemoApplication.java
src/main/java/com/example/dataaccess/AccountRepository.java
src/main/java/com/example/dataaccess/TransferService.java
src/main/resources/application.properties
src/main/resources/schema.sql
src/main/resources/data.sql
~~~

**`build.gradle`** — Spring JDBC kéo theo JDBC transaction management và pool mặc định khi đủ phụ thuộc.

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

**`src/main/resources/application.properties`** — ứng dụng console, DataSource H2, nạp `schema.sql`/`data.sql` khi khởi động.

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:lesson;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

**`src/main/resources/schema.sql`** — DBMS áp dụng CHECK để bảo vệ số dư.

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL,
    CONSTRAINT chk_balance_nonnegative CHECK (balance >= 0)
);
~~~

**`src/main/resources/data.sql`** — dữ liệu ban đầu.

~~~sql
INSERT INTO account (id, balance) VALUES (1, 100.00);
INSERT INTO account (id, balance) VALUES (2, 50.00);
~~~

**`AccountRepository.java`** — chỉ biết cấu trúc bảng, truy vấn và số dòng tác động. Tham số SQL dùng dấu `?` để driver bind giá trị, tránh nối chuỗi đầu vào trực tiếp vào SQL.

~~~java
package com.example.dataaccess;

import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountRepository {
    private final JdbcTemplate jdbc;

    public AccountRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean debit(long id, BigDecimal amount) {
        int rows = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, id, amount
        );
        return rows == 1;
    }

    public boolean credit(long id, BigDecimal amount) {
        int rows = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, id
        );
        return rows == 1;
    }

    public BigDecimal balance(long id) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            BigDecimal.class,
            id
        );
    }
}
~~~

**`TransferService.java`** — ràng buộc nghiệp vụ và transaction bao quanh hai lời gọi Repository.

~~~java
package com.example.dataaccess;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Giao dịch không hợp lệ");
        }
        if (!accounts.debit(fromId, amount)) {
            throw new IllegalArgumentException(
                "Nguồn không tồn tại hoặc không đủ số dư"
            );
        }
        if (!accounts.credit(toId, amount)) {
            throw new IllegalArgumentException("Đích không tồn tại");
        }
    }
}
~~~

**`DataAccessDemoApplication.java`** — khởi tạo Spring context, gọi Service qua bean Spring và in trạng thái để quan sát.

~~~java
package com.example.dataaccess;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DataAccessDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DataAccessDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService transfers, AccountRepository accounts) {
        return args -> {
            show("Trước", accounts);
            transfers.transfer(1L, 2L, new BigDecimal("30.00"));
            show("Sau thành công", accounts);

            try {
                transfers.transfer(1L, 999L, new BigDecimal("10.00"));
            } catch (IllegalArgumentException ex) {
                System.out.println("Giao dịch bị huỷ: " + ex.getMessage());
            }
            show("Sau rollback", accounts);
        };
    }

    private static void show(String label, AccountRepository accounts) {
        System.out.println(label + ": A=" + accounts.balance(1L)
            + ", B=" + accounts.balance(2L));
    }
}
~~~

Tại thư mục dự án có Gradle wrapper, chạy `./gradlew bootRun` (Windows PowerShell: `.\gradlew.bat bootRun`); nếu đã cài Gradle phù hợp và chưa có wrapper, dùng `gradle bootRun`. Các dòng **do chương trình chủ động in** (không tính log khởi động của Spring) là:

~~~text
Trước: A=100.00, B=50.00
Sau thành công: A=70.00, B=80.00
Giao dịch bị huỷ: Đích không tồn tại
Sau rollback: A=70.00, B=80.00
~~~

**Giải thích theo từng tầng:**

1. Ứng dụng console đóng vai trò bộ kích hoạt; tình huống HTTP controller cũng có thể gọi cùng Service.
2. `TransferService.transfer` kiểm tra điều kiện và mở giao dịch qua Spring proxy. Tài khoản đích 999 không có thật nên thao tác thứ hai trong lần thử sau trả `false`.
3. `AccountRepository` chạy hai UPDATE bằng JdbcTemplate; nó không tự quyết định việc rollback, chỉ báo kết quả thao tác dữ liệu.
4. JdbcTemplate phối hợp với Spring transaction manager để các UPDATE trong một lần `transfer` sử dụng transaction hiện hành; HikariCP cung cấp kết nối và H2 thực thi SQL.
5. Lần chuyển đầu commit: A 100 → 70, B 50 → 80. Lần chuyển đến id 999 trừ A tạm thời nhưng ném `IllegalArgumentException`, là RuntimeException, nên rollback trả A về 70; B vẫn 80.

Ví dụ cố tình đơn giản: chưa xử lý xác thực người dùng, hạn mức, tiền tệ, audit, yêu cầu idempotency, chính sách lỗi HTTP, các tranh chấp/khóa giữa hai tài khoản hoặc nhiều hệ thống khác nhau. Khi xây dựng giao dịch tài chính thực, những điểm đó là thiết kế bắt buộc cần giải quyết riêng; đừng xem mã demo là hệ thống ngân hàng hoàn chỉnh.

## 7. Cùng một đường đi, hai cách truy cập dữ liệu của Spring

| Khía cạnh | Spring JDBC (JdbcTemplate) | Spring Data JPA / JPA provider |
| --- | --- | --- |
| Tầng nghiệp vụ | Service điều phối, thường dùng `@Transactional` | Service điều phối, thường dùng `@Transactional` |
| Tầng dữ liệu | Repository tự viết SQL và ánh xạ dữ liệu | Repository/EntityManager làm việc với entity, JPQL hoặc query methods |
| Thời điểm SQL | Phần lớn lệnh `update/query` gửi SQL khi gọi | Có persistence context; thay đổi entity có thể đợi flush trước commit hoặc query |
| Kết nối | JdbcTemplate mượn Connection do Spring điều phối | JPA provider lấy Connection từ DataSource theo chiến lược của nó |
| Giao dịch | Transaction manager tương ứng với JDBC DataSource | Transaction manager cho JPA (thường JpaTransactionManager) |
| Vấn đề cần chú ý | SQL, mapping, đóng tài nguyên, số hàng cập nhật | N+1 query, lazy loading, flush, dirty checking, trạng thái entity |

**Điểm không đổi:** nghiệp vụ vẫn thuộc Service; dữ liệu vẫn phải qua một adapter/repository; DBMS vẫn quyết định việc thực thi và tính bền vững của dữ liệu. Không nên nghĩ JPA loại bỏ Connection: nó trừu tượng hóa việc sử dụng JDBC bên dưới khi làm việc với cơ sở dữ liệu quan hệ.

Không phải mọi hệ lưu trữ đi qua JDBC. Redis, MongoDB hoặc một API bên ngoài có client/protocol riêng; lúc đó tầng kết nối thay đổi, nhưng nguyên tắc tách nghiệp vụ khỏi chi tiết lưu trữ vẫn hữu ích.

## 8. Tính nhất quán, hiệu năng và lỗi nằm ở những ranh giới nào?

**Nghiệp vụ ↔ Repository:** Service có thể kiểm tra số dư trước rồi UPDATE, nhưng hai request đồng thời có thể cùng đọc số dư cũ. Ví dụ trên dùng UPDATE có điều kiện `balance >= ?` ngay trong DBMS để giảm lỗi chi tiêu quá số dư khi cạnh tranh. Với workflow phức tạp hơn, cần xem xét isolation, optimistic locking/version hoặc pessimistic locking; điều kiện UPDATE là một kỹ thuật, không giải quyết mọi dạng race condition.

**Repository ↔ DBMS:** SQL đúng nghĩa chưa chắc chạy nhanh. Chỉ mục phù hợp, kế hoạch truy vấn, lượng dữ liệu trả về và batch operation quyết định nhiều đến độ trễ. Truy vấn N+1 trong ORM là triệu chứng tầng dữ liệu gọi DB quá nhiều lần để phục vụ một yêu cầu nghiệp vụ.

**Connection pool ↔ DBMS:** Pool cạn có thể gây timeout **trước khi SQL được gửi đến DB**, dù bản thân câu truy vấn nhanh. Ngược lại, pool còn rảnh nhưng SQL có thể chậm vì thiếu chỉ mục, khóa hoặc tải DB. Khi chẩn đoán, phân biệt thời gian đợi Connection, thời gian SQL chạy và thời gian xử lý nghiệp vụ.

**Giao dịch ↔ dữ liệu:** DBMS giữ trách nhiệm bảo đảm ACID theo engine và isolation đang dùng. Nếu giao dịch quá dài, các connection/lock bị giữ lâu. Nếu chia sai transaction, thao tác nghiệp vụ nhiều bước có thể chỉ thành công một phần.

**Lỗi kỹ thuật ↔ lỗi nghiệp vụ:** `0 rows updated`, unique violation, timeout, lost connection là tín hiệu khác nhau. Spring JDBC thường chuyển SQLException thành hệ phân cấp `DataAccessException` (unchecked) để tầng trên có thể xử lý nhất quán. Không nên biến mọi ngoại lệ cơ sở dữ liệu thành “không tìm thấy” hoặc tự động retry mọi UPDATE; retry phải dựa trên lỗi cụ thể và tính idempotent.

## 9. Những sai lầm phổ biến và cách sửa

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Controller tự viết SQL và kiểm tra mọi quy tắc | Khó tái sử dụng/test nghiệp vụ, trộn giao diện với lưu trữ | Controller gọi Service; Service gọi Repository |
| Đặt hai UPDATE trong hai transaction độc lập | Có thể trừ tiền mà không cộng tiền | Bao cả thao tác bằng một transaction ở Service |
| Tự mở Connection và tự commit giữa `@Transactional` | Có thể thoát khỏi transaction do Spring quản lý | Dùng JdbcTemplate/JPA hoặc API tích hợp transaction của Spring |
| Ghép input vào chuỗi SQL | SQL injection hoặc lỗi escape | PreparedStatement/parameter binding |
| Bỏ qua số dòng UPDATE | Không phát hiện bản ghi thiếu/điều kiện thất bại | Kiểm tra rows affected và chuyển thành lỗi nghiệp vụ |
| Tin rằng `@Transactional` luôn chạy khi gọi cùng class | Self-invocation bỏ qua proxy | Gọi qua bean được Spring quản lý, thiết kế ranh giới rõ |
| Tin rằng pool lớn chữa được mọi chậm trễ | Tăng tải DB, vẫn chậm vì SQL/lock | Đo latency, wait time, SQL plan; tối ưu đúng điểm nghẽn |
| Đọc xong mới quyết định ghi mà không xét concurrency | Có thể dùng trạng thái đã cũ | Atomic UPDATE, khóa hoặc version khi cần |
| Chỉ kiểm tra dữ liệu ở Java, bỏ ràng buộc DB | Nhiều đường ghi có thể tạo dữ liệu sai | Giữ constraint quan trọng trong schema |
| Giữ transaction khi gọi API chậm | Kết nối và khóa bị chiếm lâu | Thu gọn transaction, thiết kế tích hợp bất đồng bộ khi cần |

## 10. Tự kiểm tra sự hiểu biết

1. Một Service cần cập nhật ba bảng để hoàn tất một lệnh. Nên đặt ranh giới giao dịch ở đâu? **Ở một thao tác Service bao trọn các bước cần nguyên tử**, rồi kiểm tra rằng tất cả Repository dùng tài nguyên/giao dịch phù hợp.
2. Tại sao DataSource và Connection không đồng nghĩa? **DataSource cung cấp/quản lý việc cấp Connection; Connection là phiên sử dụng thực tế đến DBMS.**
3. Nếu lệnh SQL thứ hai thất bại, Repository đã trả dữ liệu cho Service, vậy rollback có còn xảy ra? **Có, nếu lỗi làm transaction được đánh dấu rollback trước commit và toàn bộ lệnh cùng tham gia transaction đó.**
4. Với Spring Data JPA, ứng dụng có “không cần database connection” không? **Không.** JPA provider vẫn sử dụng kết nối tới DBMS quan hệ, chỉ che bớt thao tác JDBC cho mã ứng dụng.
5. Khi API chậm, thấy nhiều thread chờ pool nhưng query nhanh, nên điều tra gì trước? **Connection bị giữ quá lâu, giao dịch dài, pool size/timeout và việc giải phóng tài nguyên**, thay vì mặc định tối ưu câu SELECT.

**Ghi nhớ:** Một thao tác nghiệp vụ có thể đi qua nhiều lớp mã nhưng chỉ nên có **một nơi xác định ý nghĩa nghiệp vụ** và **ranh giới giao dịch đúng với đơn vị nhất quán**. Repository, DataSource, Connection và DBMS mỗi bên có trách nhiệm riêng; hiểu rõ ranh giới sẽ giúp thiết kế đúng, xử lý lỗi chính xác và xác định điểm nghẽn khi ứng dụng vận hành.
