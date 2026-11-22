# Khóa lạc quan, cột `version` và phát hiện xung đột

## 1. Bài toán: hai người cùng sửa một dữ liệu

Giả sử hệ thống quản lý tài khoản có hàng dữ liệu:

| id | balance | version |
| --- | ---: | ---: |
| 1 | 100 | 0 |

Hai request A và B đọc cùng một hàng gần như đồng thời. Cả hai nhìn thấy `balance=100`, `version=0`.

- Request A muốn tăng 30, dự định ghi `balance=130`.
- Request B muốn giảm 20, dự định ghi `balance=80`.
- Nếu ứng dụng chỉ chạy `UPDATE accounts SET balance = ? WHERE id = ?`, bản ghi sau cùng có thể là `80`: thao tác của A bị **ghi đè mất**, dù A đã báo thành công. Đây là **lost update**.

**Khóa lạc quan (optimistic locking)** xử lý tình huống này bằng cách kiểm tra dữ liệu còn giữ **phiên bản đã đọc** hay không khi ghi. Nó giả định xung đột không quá thường xuyên và **phát hiện xung đột ở thời điểm cập nhật**, thay vì giữ khóa chặn tất cả người đọc/sửa trong suốt quãng thời gian người dùng suy nghĩ.

Quy ước: mỗi hàng có một cột `version`. Một thao tác ghi hợp lệ phải:

1. Biết `version` tại thời điểm đọc, ví dụ `0`.
2. Chỉ cập nhật nếu phiên bản hiện tại **vẫn là 0**.
3. **Tăng `version` trong cùng câu UPDATE nguyên tử** khi thành công.
4. Kiểm tra số hàng bị ảnh hưởng: `1` = cập nhật thành công; `0` = phiên bản cũ, hàng bị xóa, hoặc điều kiện khác không khớp.
5. Khi xung đột, **không báo thành công và không ghi đè**. Trả lỗi có ý nghĩa hoặc đọc dữ liệu mới và quyết định thử lại có kiểm soát.

Sau bài này, bạn sẽ hiểu cơ chế compare-and-swap bằng SQL, cột `@Version` của JPA/Hibernate, cách Spring transaction rollback khi gặp xung đột, và những giới hạn như *write skew*, bulk updates, retry/idempotency.

## 2. Lost update xảy ra thế nào?

### 2.1. Không có kiểm tra phiên bản

```text
Thời điểm       Request A                      Request B
----------------------------------------------------------------
t0              Đọc balance=100                Đọc balance=100
t1              Tính 100 + 30 = 130            Tính 100 - 20 = 80
t2              UPDATE balance=130             Chờ / chuẩn bị ghi
t3              COMMIT                          UPDATE balance=80
t4                                              COMMIT

Kết quả cuối: balance=80.
Phép cộng +30 của A biến mất khỏi giá trị cuối.
```

Đây là lịch trình minh họa khi hai request dựa trên **snapshot cũ** và không có biện pháp phát hiện stale state. Khả năng database phát hiện hoặc ngăn tình huống còn tùy isolation và thời điểm transaction; đừng giả định mọi DB isolation mặc định tự ngăn được lost update của một chuỗi **đọc → xử lý → ghi** trải qua nhiều request.

### 2.2. Có `version` và điều kiện cập nhật

Cả hai request vẫn đọc `version=0`, nhưng ghi theo điều kiện:

```sql
UPDATE accounts
SET balance = 130, version = version + 1
WHERE id = 1 AND version = 0;
```

Request A cập nhật một hàng; database giờ có `balance=130, version=1`.

Request B mang phiên bản đã đọc là `0`:

```sql
UPDATE accounts
SET balance = 80, version = version + 1
WHERE id = 1 AND version = 0;
```

Lúc B tới lượt thực hiện câu UPDATE, phiên bản hàng hiện tại là `1`, nên điều kiện `WHERE version = 0` **không còn khớp**. `UPDATE` ảnh hưởng **0 hàng**. Ứng dụng phải coi đây là **xung đột**, không phải thao tác thành công.

```text
Bản ghi đầu:                  balance=100, version=0
A ghi với expectedVersion=0:  balance=130, version=1  → updatedRows=1
B ghi với expectedVersion=0:  không thay đổi          → updatedRows=0
B đọc lại bản ghi mới:        balance=130, version=1
B áp dụng -20 lên dữ liệu mới: balance=110, version=2  → updatedRows=1
```

Kết quả cuối `110` phản ánh **cả hai thay đổi theo đúng thứ tự nghiệp vụ**. Không phải lúc nào cũng được tự động thử lại: nếu hai người cùng chỉnh sửa tên/mô tả, hệ thống có thể phải báo cho người thứ hai so sánh và giải quyết conflict, thay vì âm thầm chấp nhận bản sửa mới.

## 3. Vì sao câu UPDATE phải là một phép kiểm tra–ghi nguyên tử?

Đây là **lỗi sai** rất phổ biến:

```java
// MÃ MINH HỌA SAI
long currentVersion = repository.readVersion(id);
if (currentVersion == expectedVersion) {
    repository.updateWithoutVersionCheck(id, newBalance);
}
```

Hai request có thể **cùng đọc** `currentVersion=0` trong khoảng giữa hai statement. Sau đó cả hai update không điều kiện và tạo lost update. Việc đặt `if` trong Java **không biến hai câu SQL thành một thao tác nguyên tử**.

Cách đúng là gộp điều kiện phiên bản và thay đổi dữ liệu **ngay trong một câu UPDATE**:

```sql
UPDATE accounts
SET balance = :newBalance,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

Dạng SQL trên dùng **named parameters minh họa**. Với `JdbcTemplate` thường, dùng dấu `?`; với `NamedParameterJdbcTemplate` mới dùng tên `:newBalance`, `:id`, `:expectedVersion`.

### 3.1. Ý nghĩa số hàng được cập nhật

| `updatedRows` | Diễn giải và hành động |
| ---: | --- |
| `1` | Có đúng một hàng thỏa điều kiện; phiên bản mới đã được tăng trong cùng câu UPDATE. |
| `0` | Không có hàng khớp. Thường là stale version, nhưng cũng có thể do hàng đã bị xóa hoặc một điều kiện `WHERE` khác không thỏa. **Không được báo thành công.** |
| `>1` | Với `id` là primary key thì đây là bất thường; kiểm tra schema/điều kiện, dừng nghiệp vụ. |

Không nên khẳng định `updatedRows=0` **luôn luôn** là xung đột version. Ví dụ khi câu SQL còn có điều kiện `balance >= amount`, 0 hàng cũng có thể do không đủ tiền. Nếu cần phân loại lỗi chính xác, truy vấn lại trạng thái và áp dụng domain policy trong một bước phù hợp, nhưng chú ý trạng thái có thể đổi tiếp giữa các lần đọc.

### 3.2. Tăng version ở mọi đường ghi

Cơ chế chỉ hoạt động tin cậy nếu **mọi đường cập nhật quan trọng của cùng aggregate/row đều thay đổi version nhất quán**:

- Ghi từ Spring JDBC phải có `WHERE version = ?` và tăng `version`.
- Ghi từ Hibernate/JPA qua entity có `@Version` thường do ORM thực hiện.
- Một admin script, background job, stored procedure hoặc native SQL thay đổi dữ liệu nhưng **không tăng `version`** có thể khiến client cũ không phát hiện stale snapshot.
- Bulk update/delete theo JPQL hoặc native SQL có thể **bỏ qua kiểm tra version ở mức từng entity**. Nếu sử dụng, phải thiết kế điều kiện/increment tương ứng thay vì giả định `@Version` tự bảo vệ mọi câu SQL.

`version` không phải timestamp hệ thống để so ai cập nhật «gần đây hơn». Giá trị nguyên tăng đơn điệu trên mỗi lần ghi có ý nghĩa; đừng tự chỉnh version tuỳ ý nếu đang để ORM quản lý.

## 4. So sánh khóa lạc quan với khóa bi quan

| Tiêu chí | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Cách xử lý tranh chấp | Cho các bên đọc/làm việc, **phát hiện xung đột khi ghi** | Giữ khóa database để ngăn một số thao tác đồng thời |
| Cơ chế điển hình | `version` + conditional `UPDATE` hoặc JPA `@Version` | `SELECT ... FOR UPDATE` / JPA pessimistic lock modes |
| Khi ít người sửa cùng bản ghi | Thường hiệu quả, không phải giữ row lock từ lúc đọc trong thời gian dài | Có thể tăng thời gian chờ/lock footprint |
| Khi rất nhiều người liên tục cập nhật cùng hàng | Nhiều conflict, retry tốn chi phí | Có thể phù hợp hơn tùy lock contention, throughput, timeout |
| Dữ liệu người dùng đang chỉnh sửa trong vài phút | Dễ lưu `version` từ lúc mở form và phát hiện xung đột lúc Submit | Giữ transaction/row lock xuyên suốt vài phút là rất rủi ro |
| Cơ chế thất bại | `0 rows updated`, ORM optimistic exception | Lock wait, timeout, deadlock, không lấy được lock |

**Optimistic locking không có nghĩa database hoàn toàn không dùng khóa.** Database vẫn có thể khóa hàng rất ngắn khi câu `UPDATE` chạy, hoặc có MVCC/isolation/serialization error riêng. Điểm khác là ứng dụng **không chủ ý giữ exclusive row lock từ lúc đọc đến lúc người dùng hoàn tất chỉnh sửa**. Kiểm tra `version` phát hiện thay đổi cũ trước khi ghi đè.

## 5. Vị trí của Spring transaction trong optimistic locking

`@Transactional` và optimistic locking giải quyết **hai câu hỏi khác nhau**:

- `@Transactional`: một nhóm thao tác tài nguyên có được commit/rollback **cùng nhau** không?
- `version`/optimistic locking: dữ liệu mà request định sửa có **còn là phiên bản đã đọc** hay không?

Một phương thức service có thể vừa là transaction boundary, vừa dùng conditional update. Với Spring JDBC:

```java
@Transactional
public void applyChange(Snapshot old, long delta) {
    // Ghi thêm một hàng journal trong transaction hiện tại.
    journalRepository.insert(...);

    int changed = jdbc.update(
        "UPDATE accounts SET balance=?, version=version+1 " +
        "WHERE id=? AND version=?",
        newBalance, old.id(), old.version()
    );
    if (changed != 1) {
        throw new OptimisticConflictException(...);
    }
}
```

Đây là **đoạn minh họa, không phải chương trình độc lập**; `Snapshot`, `newBalance`, repository và exception cần định nghĩa. Khi không khớp version, exception unchecked thoát khỏi transaction interceptor khiến **toàn bộ transaction rollback**, bao gồm hàng journal đã insert trước đó.

Nếu không có `@Transactional` hoặc tài nguyên không tham gia cùng manager, hàng journal **có thể đã commit** trước khi phát hiện conflict. Vì vậy **phát hiện xung đột** và **rollback các tác dụng phụ nội bộ** đều quan trọng. Đừng bắt exception rồi return thành công khi transaction đã gặp xung đột; cần rollback đúng scope, sau đó trả kết quả nghiệp vụ rõ ràng.

Với long-running workflow, dữ liệu/snapshot có thể được đọc **ngoài transaction ghi**, lưu version vào HTTP form, message hoặc request DTO. Khi nhận lệnh ghi, service mở transaction ngắn để thực thi conditional update bằng version đó. Không mở một database transaction kéo dài toàn bộ thời gian người dùng đang chỉnh sửa trên UI.

## 6. Dự án thực hành chạy được (Java 17+, Spring JDBC và H2)

Chúng ta xây một ứng dụng nhỏ có một bảng `accounts` và một bảng `journal`. Dùng **Java 17+**, **Maven**, **Spring Framework 6.2.8**, **H2 2.3.232**. Không cần Spring Boot hay web server.

Bài lab mô phỏng hai request **đã đọc cùng snapshot** bằng cách giữ hai object Java riêng trước khi update. Nó không tạo hai thread chạy thực sự; cách này **cố ý deterministic** để chứng minh stale version và rollback mà không phụ thuộc lịch scheduler. Khi chạy trong server thật, hai HTTP requests/threads khác nhau có thể tạo ra đúng trạng thái tranh chấp đó.

### 6.1. Cấu trúc tệp

```text
optimistic-version-demo/
├── pom.xml
└── src/main/java/example/OptimisticVersionDemo.java
```

### 6.2. `pom.xml`

Lưu toàn bộ block sau vào đúng `pom.xml`. **Dòng đầu tiên là XML declaration**; không thêm comment phía trước.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>optimistic-version-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.OptimisticVersionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp ApplicationContext và bean configuration; `spring-jdbc` có `JdbcTemplate` và `DataSourceTransactionManager`; `spring-tx` cung cấp `@Transactional`; H2 là in-memory database. Import `JdbcDataSource` trực tiếp nên H2 nằm trên **compile classpath**. Version dependency trong bài cố định để người học tái lập, còn dự án thật nên có BOM và kế hoạch cập nhật bảo mật.

### 6.3. `src/main/java/example/OptimisticVersionDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public class OptimisticVersionDemo {

    // Snapshot được đọc từ database tại một thời điểm cụ thể.
    // Version trong snapshot sẽ KHÔNG tự cập nhật khi DB thay đổi.
    public record Snapshot(long id, long balance, long version) { }

    // Lỗi domain dùng trong demo: unchecked để Spring rollback mặc định.
    public static final class OptimisticConflictException
            extends RuntimeException {
        public OptimisticConflictException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            AccountRepository repository =
                context.getBean(AccountRepository.class);
            AccountService service =
                context.getBean(AccountService.class);

            repository.initialize();
            printState("Initial", repository);

            // Hai client đọc TRƯỚC khi bất kỳ client nào ghi.
            Snapshot snapshotA = repository.read(1L);
            Snapshot snapshotB = repository.read(1L);

            System.out.println(
                "Both clients read version: A="
                + snapshotA.version()
                + ", B=" + snapshotB.version()
            );

            // A đổi 100 -> 130 và nâng version 0 -> 1.
            service.applyDelta(snapshotA, 30L, "A");
            printState("After A", repository);

            // B vẫn giữ snapshot cũ version=0 -> conflict.
            try {
                service.applyDelta(snapshotB, -20L, "B");
            } catch (OptimisticConflictException ex) {
                System.out.println("B conflict: " + ex.getMessage());
            }
            printState("After B conflict", repository);
            System.out.println(
                "B journal persisted: " + repository.hasJournal("B")
            );

            // Retry có chủ đích: đọc lại rồi tái áp dụng delta.
            Snapshot refreshedB = repository.read(1L);
            service.applyDelta(refreshedB, -20L, "B-RETRY");
            printState("After B retry", repository);
        }
    }

    private static void printState(
        String label,
        AccountRepository repository
    ) {
        Snapshot current = repository.read(1L);
        System.out.println(
            label + ": balance=" + current.balance()
            + ", version=" + current.version()
            + ", journal=" + repository.countJournal()
        );
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:optimistic_version;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        public AccountRepository accountRepository(JdbcTemplate jdbc) {
            return new AccountRepository(jdbc);
        }

        @Bean
        public AccountService accountService(AccountRepository repository) {
            return new AccountService(repository);
        }
    }

    public static class AccountRepository {
        private final JdbcTemplate jdbc;

        public AccountRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void initialize() {
            jdbc.execute("DROP TABLE IF EXISTS journal");
            jdbc.execute("DROP TABLE IF EXISTS accounts");

            jdbc.execute(
                "CREATE TABLE accounts (" +
                "id BIGINT PRIMARY KEY, " +
                "balance BIGINT NOT NULL, " +
                "version BIGINT NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE journal (" +
                "tag VARCHAR(32) PRIMARY KEY, " +
                "delta BIGINT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO accounts (id,balance,version) VALUES (?,?,?)",
                1L, 100L, 0L
            );
        }

        public Snapshot read(long id) {
            return jdbc.queryForObject(
                "SELECT id,balance,version FROM accounts WHERE id = ?",
                (rs, rowNum) -> new Snapshot(
                    rs.getLong("id"),
                    rs.getLong("balance"),
                    rs.getLong("version")
                ),
                id
            );
        }

        public void insertJournal(String tag, long delta) {
            jdbc.update(
                "INSERT INTO journal (tag,delta) VALUES (?,?)", tag, delta
            );
        }

        public int updateIfVersionMatches(
            long id,
            long expectedVersion,
            long newBalance
        ) {
            return jdbc.update(
                "UPDATE accounts " +
                "SET balance = ?, version = version + 1 " +
                "WHERE id = ? AND version = ?",
                newBalance, id, expectedVersion
            );
        }

        public Integer countJournal() {
            return jdbc.queryForObject(
                "SELECT COUNT(*) FROM journal", Integer.class
            );
        }

        public boolean hasJournal(String tag) {
            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM journal WHERE tag = ?",
                Integer.class,
                tag
            );
            return count != null && count == 1;
        }
    }

    public static class AccountService {
        private final AccountRepository repository;

        public AccountService(AccountRepository repository) {
            this.repository = repository;
        }

        @Transactional
        public void applyDelta(Snapshot old, long delta, String tag) {
            long newBalance = Math.addExact(old.balance(), delta);
            if (newBalance < 0) {
                throw new IllegalArgumentException("insufficient balance");
            }

            // Thao tác ghi 1: cần rollback nếu update account conflict.
            repository.insertJournal(tag, delta);

            // Thao tác ghi 2: conditional UPDATE + tăng version nguyên tử.
            int updated = repository.updateIfVersionMatches(
                old.id(), old.version(), newBalance
            );

            if (updated != 1) {
                throw new OptimisticConflictException(
                    "expected version " + old.version()
                );
            }
        }
    }
}
```

### 6.4. Tại sao code này tạo ra xung đột đúng cách?

**Một hàng dữ liệu, hai snapshot:** `snapshotA` và `snapshotB` được đọc trước thao tác ghi đầu tiên. Cả hai chứa `version=0`. Việc giữ snapshot cũ mô phỏng client B đã mở form từ trước; không cần tạo race ngẫu nhiên bằng `Thread.sleep()`.

**Một transaction cho cả journal và account update:** `AccountService.applyDelta()` là public method trên một bean do Spring quản lý. `main()` lấy service bằng `context.getBean` và gọi qua proxy. `@EnableTransactionManagement` tạo transaction advice; `DataSourceTransactionManager` quản lý cùng datasource H2 mà `JdbcTemplate` sử dụng.

**Không trùng lẫn với `@Version` của JPA:** đây là **Spring JDBC thuần**, nên `@Transactional` bảo vệ hai thao tác cùng commit/rollback, còn kiểm tra version được **tự viết bằng SQL**. Spring JDBC không tự sinh điều kiện `WHERE version=?` chỉ vì database có cột tên là `version`.

**Conflict phải là exception:** khi B dùng `version=0` trong lúc database đã là `version=1`, `updateIfVersionMatches` trả về 0. Service ném `OptimisticConflictException extends RuntimeException`. Vì exception **thoát ra ngoài public transactional method**, Spring mặc định rollback transaction của B, bao gồm `INSERT INTO journal` đã chạy trước khi phát hiện conflict.

**Retry B là một transaction khác:** caller bắt conflict **sau khi proxy của B đã rollback**, đọc lại current row `balance=130, version=1` rồi gọi service qua proxy lần nữa. Lần này version khớp, delta -20 hợp lệ, cập nhật ra `balance=110, version=2`. Không retry trong transaction đã bị đánh dấu rollback-only.

### 6.5. Lệnh chạy

Từ thư mục `optimistic-version-demo` sau khi tạo đúng hai tệp:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Các dòng do **Java program** in ra theo thiết kế, không tính log Maven/Spring ngoài ứng dụng:

```text
Initial: balance=100, version=0, journal=0
Both clients read version: A=0, B=0
After A: balance=130, version=1, journal=1
B conflict: expected version 0
After B conflict: balance=130, version=1, journal=1
B journal persisted: false
After B retry: balance=110, version=2, journal=2
```

Diễn giải:

1. Trước khi có ghi, snapshot là `(100,0)`.
2. A thành công, tăng balance lên 130, version lên 1, tạo journal A.
3. B dùng version 0 nên không có hàng khớp. Service ném exception; **journal B bị rollback**. Bản ghi account giữ `(130,1)`.
4. `B journal persisted: false` chứng minh rollback của B bao gồm cả thao tác ghi ở **trước** câu UPDATE conflict.
5. Đọc lại và thử lại như một transaction mới, B áp dụng delta -20 lên balance 130, kết quả `(110,2)` với journal A và `B-RETRY`.

**Cảnh báo về mẫu tiền bạc:** lab dùng số nguyên để minh họa, không giải quyết đầy đủ domain tài chính (đơn vị tiền, phân quyền, debit/credit đối ứng, kiểm tra số dư cùng cập nhật, idempotency, audit bền vững và concurrency toàn hệ). Trong nghiệp vụ ví/tiền thật, cần thêm các ràng buộc và kiểm thử chuyên biệt; không sao chép demo như hệ thống chuyển tiền production.

## 7. JPA/Hibernate với `@Version`

Khi sử dụng Spring Data JPA/Hibernate, cách thông dụng hơn là khai báo cột version trên entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    private Long id;

    @Column(nullable = false)
    private long balance;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Account() {
        // Constructor cho JPA.
    }

    public void addToBalance(long delta) {
        this.balance = Math.addExact(this.balance, delta);
    }
}
```

Đây là **đoạn entity JPA minh họa**, không thuộc project JDBC bên trên; muốn chạy cần dependency JPA provider, datasource và cấu hình persistence của Spring Boot/JPA phù hợp.

### 7.1. JPA làm gì với `@Version`?

- Hibernate quản lý thuộc tính version, ghi nhận version lúc entity được load.
- Khi entity bị thay đổi và flush, ORM sinh UPDATE/DELETE có điều kiện kiểm tra version cũ (khái quát: `WHERE id=? AND version=?`).
- Khi ghi thành công, version được tăng theo cơ chế của provider.
- Nếu phiên bản trong database đã khác, provider không được phép âm thầm ghi đè snapshot cũ; nó báo một optimistic locking failure (ví dụ `jakarta.persistence.OptimisticLockException` hoặc exception cụ thể của Hibernate; Spring có thể dịch thành `ObjectOptimisticLockingFailureException` hay `OptimisticLockingFailureException`).
- **Thời điểm phát hiện lỗi** có thể là lúc `flush()` hoặc lúc transaction commit, không nhất thiết ngay tại `save(...)`. Khi Spring proxy commit sau method body, caller có thể nhận lỗi dù thân method đã return xong.

Hibernate/JPA thường quản lý version thay bạn. **Không tự tăng trường `@Version` bằng application code** để «chắc chắn» nó đổi; có thể làm sai cơ chế provider. Hãy cập nhật những thuộc tính nghiệp vụ và để ORM xử lý version.

### 7.2. Những giới hạn của `@Version`

**Không bảo vệ mọi câu SQL:** gọi `JdbcTemplate` hoặc native SQL thẳng vào bảng, hoặc chạy bulk JPQL `UPDATE/DELETE`, có thể **bỏ qua logic version check của entity**. Nếu dùng các đường này cùng JPA, phải chủ động kiểm tra version và tăng version hoặc áp dụng chiến lược đồng bộ hóa tương ứng.

**Không phải mọi lần đọc đều bị kiểm tra lại:** một entity chỉ được đọc mà không sửa không mặc nhiên báo conflict chỉ vì có `@Version`. Nếu nghiệp vụ cần bảo đảm version của dữ liệu đã đọc vẫn không đổi dù không update, hãy nghiên cứu `LockModeType.OPTIMISTIC` và semantics flush/commit.

**Không mặc nhiên giải quyết stale HTTP form:** nếu request gửi một version cũ nhưng service luôn load entity **mới nhất** ngay trước khi ghi rồi bỏ qua expected version từ request, ORM chỉ bảo vệ transaction của lần load mới; nó không tự biết người dùng từng xem bản cũ. Cần so sánh expected version từ request với current version hoặc giữ đúng detached version theo mô hình persistence và xử lý conflict rõ ràng.

**Không tự đảm bảo invariants trải nhiều hàng:** nếu hai giao dịch đọc các hàng khác nhau rồi ghi các hàng khác nhau, từng hàng vẫn có version hợp lệ nhưng toàn cục có thể vi phạm quy tắc (write skew). Cần ràng buộc database, isolation thích hợp, pessimistic lock hoặc một aggregate-level version theo yêu cầu.

### 7.3. Trả xung đột cho client

Trong API HTTP, stale version thường phù hợp với response **409 Conflict**. Nếu dùng HTTP conditional requests và ETag/`If-Match` thì có thể sử dụng **412 Precondition Failed** theo contract API. Không nên dùng 200 OK khi một update đã thất bại do version mismatch.

Response nên cho client biết dữ liệu cần được refresh/merge theo policy (có thể trả current version và một số trường cần thiết nhưng không tiết lộ dữ liệu vượt quyền). Đừng để stack trace ORM trở thành giao diện công khai.

## 8. Retry khi xung đột: khi nào được, khi nào không?

Một conflict **không phải lỗi transient mà luôn nên tự retry**. Có hai nhóm use case khác nhau.

### 8.1. Lệnh thay đổi có thể tái áp dụng trên trạng thái mới

Ví dụ «tăng bộ đếm 1» hoặc «cộng thêm 30» có thể được tính lại trên bản ghi mới, nếu business rule vẫn hợp lệ. Thứ tự đúng là:

```text
Lần 1: đọc snapshot version 0
      mở transaction ngắn
      conditional UPDATE → xung đột
      rollback transaction
      đóng scope/connection

Lần 2: đọc lại snapshot version 1
      kiểm tra lại business rule theo dữ liệu mới
      mở transaction MỚI
      conditional UPDATE → thành công (hoặc conflict tiếp)
```

Hạn chế số lần retry, dùng backoff/jitter khi có tải cao, quan sát metrics. Mỗi attempt phải có **transaction mới**, vì transaction đã lỗi hoặc bị đánh dấu rollback-only không thích hợp để cố commit lại. Trong mô hình Spring proxy, gọi lại một public transactional method qua proxy; không dùng self-invocation tùy tiện rồi tưởng transaction mới đã được mở.

### 8.2. Sửa nội dung do người dùng nhập tay

Nếu A và B cùng sửa `displayName` hoặc địa chỉ giao hàng từ hai snapshot khác nhau, tự retry bằng cách ghi nguyên giá trị cũ của B có thể lại **ghi đè có chủ đích của A**. Thường nên báo conflict và cho người dùng:

- Xem dữ liệu hiện tại.
- So sánh với dữ liệu họ đã chỉnh.
- Quyết định merge, ghi đè có chủ đích hoặc hủy.

Nếu product đặc biệt cho phép last-write-wins, đó là **quyết định nghiệp vụ**; không gọi nó là optimistic locking đúng nghĩa khi bỏ qua stale version.

### 8.3. Idempotency và tác dụng phụ ngoài database

Nếu một attempt đã gửi email, gọi HTTP hoặc publish message **trước khi** conditional update conflict, rollback JDBC **không tự thu hồi** tác dụng phụ. Retry có thể phát lại side effect nhiều lần. Với payment, order hay event processing cần idempotency keys, outbox/after-commit hoặc orchestration thích hợp.

Ví dụ lab insert `journal` trong **cùng local JDBC transaction**, nên journal được rollback khi conflict. Điều đó không đảm bảo một thao tác bên ngoài database cũng tự rollback.

## 9. Các tình huống khó trong ứng dụng thực tế

### 9.1. Phát hiện conflict sớm hay muộn

Trong Spring JDBC, `JdbcTemplate.update(...)` trả affected-row count ngay sau câu SQL; có thể ném conflict trong thân service transaction. Trong JPA, entity mutations được tích lũy trong persistence context và SQL có thể được phát tại flush/commit. Vì thế test integration phải kiểm tra lỗi **sau khi transaction boundary kết thúc**, không chỉ khẳng định `repository.save(...)` đã return.

### 9.2. Điều kiện số dư cùng điều kiện version

Một tài khoản thực cần kiểm tra domain constraint tại thời điểm ghi. Đôi khi điều kiện update có thể kết hợp:

```sql
UPDATE accounts
SET balance = balance - :amount,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND balance >= :amount;
```

Đây là **SQL minh họa với named parameters**. Nếu trả 0 hàng, cần phân biệt: không đủ số dư, version mismatch hoặc account đã xóa. Không dùng một thông báo `optimistic conflict` để che mọi lỗi nghiệp vụ. Đồng thời, nếu request có snapshot cũ và tính một `newBalance` ở application, cần bảo đảm phép tính và validation vẫn hợp lệ sau retry.

### 9.3. Phạm vi aggregate và write skew

Giả sử quy tắc «ít nhất một bác sĩ phải trực» được biểu diễn bằng hai hàng. Hai giao dịch cùng đọc cả hai hàng, sau đó mỗi giao dịch đánh dấu **một hàng khác nhau** là nghỉ. Version của từng hàng có thể vẫn không đụng nhau, nhưng kết quả không còn ai trực. Đây là một biến thể của **write skew**: version theo từng row không đủ để bảo vệ invariant **trải nhiều row**.

Có thể cần unique/check constraints phù hợp, serializable isolation, khóa một hàng đại diện của aggregate, hoặc update vào một aggregate version chung. Chọn giải pháp theo database và tần suất tranh chấp thực tế.

### 9.4. Xóa hàng và tái tạo hàng

Nếu client lưu version 5 nhưng hàng đã bị xóa, `WHERE id=? AND version=5` trả 0. Nếu id được tái sử dụng rồi version khởi tạo lại theo cách không phù hợp, một stale client có thể tạo tình huống giống «ABA» (giá trị có vẻ quay lại trạng thái cũ). Hạn chế tái sử dụng identity, quản lý version/epoch và phân loại lỗi không tìm thấy record theo contract.

### 9.5. Phiên bản và cache

Nếu cache/API trả snapshot cũ, conflict tăng lên khi update. Điều này không làm optimistic locking sai; nó cho thấy cơ chế đang **phát hiện stale data**. Cần theo dõi cache invalidation, TTL, latency và tỷ lệ failed updates. Không bỏ `WHERE version=?` chỉ để giảm lỗi hiển thị.

### 9.6. Hot row và hiệu năng

Optimistic locking thường tốt khi collision hiếm. Với hot row (ví dụ một bộ đếm toàn hệ thống) có hàng nghìn requests/giây, mọi request đọc cùng một version rồi retry có thể gây thundering herd, contention và tăng latency. Một lệnh SQL atomic `UPDATE counters SET n=n+1 WHERE id=?` có thể tốt hơn nếu nghiệp vụ chỉ cần cộng đếm và không yêu cầu phát hiện stale snapshot. Khi cần invariant phức tạp, cân nhắc pessimistic locking, phân mảnh aggregate, queue, hoặc serialize writes. **Không có một propagation/isolation duy nhất tối ưu cho mọi tải.**

### 9.7. Transaction isolation không thay thế version check tùy tiện

Isolation như `READ_COMMITTED`, `REPEATABLE_READ` và `SERIALIZABLE` ảnh hưởng điều gì được đọc và loại conflict nào database chặn. Một số DB ở isolation cao sẽ phát hiện serialization failure; nhưng việc người dùng đọc một form, chờ vài phút rồi submit thường **trải qua nhiều transaction HTTP**. Giữ version trong form/request và kiểm tra ở lúc ghi vẫn hữu ích. Hãy phân biệt **database snapshot trong một transaction** với **application snapshot qua nhiều request**.

## 10. Kiểm thử đủ sâu để tránh tự tin giả

Một bộ test đúng nên có:

1. **Cập nhật đơn lẻ:** version ban đầu 0; update thành công đúng 1 hàng; version thành 1, dữ liệu đúng.
2. **Stale write:** hai client lưu cùng version 0; A thành công, B dùng version 0 nhận 0 rows hoặc optimistic exception.
3. **Không có side effect trước conflict:** nếu transaction đã ghi journal rồi mới gặp conflict, xác minh journal **không tồn tại** sau rollback.
4. **Retry hợp lệ:** B đọc lại version 1, kiểm tra lại nghiệp vụ và update thành công lên version 2.
5. **Không tự retry text edits:** hai user sửa dữ liệu nội dung khác nhau; API trả 409/412 theo contract thay vì ngầm ghi đè.
6. **Không tồn tại bản ghi:** update với id không tồn tại trả 0; kiểm tra cách phân biệt 404/409 theo policy.
7. **Business precondition thất bại:** chẳng hạn số dư không đủ, trả lỗi domain rõ ràng; tránh gộp hết thành conflict.
8. **Đường ghi khác:** native SQL, batch update, background job có tăng version đúng không?
9. **JPA flush/commit:** kiểm tra exception ở đúng transaction boundary, không chỉ method repository.
10. **Xung đột thật:** thêm integration test hai transaction/threads có barrier để tạo contention, không chỉ deterministic snapshots. Kết quả có thể phụ thuộc DB/isolation, nên test phải phân loại cả optimistic conflict và serialization error theo policy.
11. **Idempotency:** nếu retry một lệnh cùng request ID, xác minh không nhân đôi journal hoặc tác dụng phụ ngoài DB.
12. **Phạm vi đa hàng:** test các invariants qua nhiều row, vì `version` một hàng không tự giải quyết write skew.

### 10.1. Checklist khi code đang báo «version conflict»

| Câu hỏi | Tại sao quan trọng |
| --- | --- |
| Request gửi `expectedVersion` từ bản đọc nào? | Client đã cũ hay đang dùng version tự đoán? |
| UPDATE có `WHERE id=? AND version=?` không? | Không có thì không phát hiện stale write. |
| UPDATE có tăng version trong cùng statement không? | Nếu không tăng, các client tiếp theo có thể cùng ghi đè. |
| `updatedRows` được kiểm tra nghiêm túc không? | 0 rows phải dẫn tới conflict/missing/precondition, không phải success. |
| Transaction có bao cả journal và account update không? | Để rollback toàn bộ thao tác ghi khi phát hiện conflict. |
| Lời gọi service đi qua Spring proxy không? | `@Transactional` không chạy khi self-invocation hoặc raw `new` target trong proxy mode. |
| Xung đột được catch ở đâu? | Không nuốt trong cùng transaction rồi cố commit. |
| Retry có đọc lại state và mở transaction mới không? | Lặp lại y nguyên version cũ sẽ tiếp tục fail. |
| Có nhiều đường update bypass version không? | Background SQL/bulk JPQL có thể tạo lost update. |
| Có invariant trải nhiều hàng không? | Cần bảo vệ aggregate, không chỉ từng row. |

## 11. Bài tập

**Bài 1 — Lược bỏ điều kiện version:** trong demo, tạm thay câu UPDATE thành `WHERE id=?` và bỏ expected version khỏi tham số. Dự đoán kết quả sau hai request A/B dựa trên snapshot cũ; giải thích vì sao output không còn phản ánh cả hai delta. Chỉ làm trên database thử nghiệm.

**Bài 2 — Quên tăng version:** giữ `WHERE version=?` nhưng bỏ `version=version+1`. Hai request có thể tiếp tục cùng khớp version cũ. Sửa và chứng minh bằng test.

**Bài 3 — Tính số dư tại database:** đổi từ `SET balance=?` sang `SET balance=balance+?` kết hợp `WHERE version=?`. Phân tích trường hợp nào vẫn cần version check, và trường hợp nào một SQL atomic increment đã đủ.

**Bài 4 — Chính sách retry:** thêm loop giới hạn tối đa ba lần, mỗi lần đọc lại state và gọi public transactional service qua Spring proxy. Nếu conflict còn tiếp tục, trả lỗi chứ không lặp vô hạn.

**Bài 5 — Tách side effect:** thử phát thông báo giả bên ngoài transaction trước khi UPDATE, sau đó tạo conflict. Giải thích vì sao rollback database không tự hủy thông báo và vì sao outbox/idempotency cần được cân nhắc.

**Bài 6 — JPA:** ánh xạ cùng bảng sang entity có `@Version`; tạo hai persistence contexts đọc cùng entity rồi lần lượt sửa/commit, quan sát lỗi khi flush/commit thứ hai. Đừng thay code JdbcTemplate bằng `@Version` và kỳ vọng JdbcTemplate tự quản lý version.

**Bài 7 — Phát hiện write skew:** thiết kế hai bản ghi cùng tham gia một invariant. Tạo hai transaction ghi khác row và lý giải vì sao version riêng của từng row không phát hiện được conflict xuyên row.

**Kết luận:** khóa lạc quan là cơ chế **phát hiện dữ liệu đã bị thay đổi kể từ lúc đọc**, thường thông qua `version` và thao tác `UPDATE ... WHERE version = expectedVersion` có tăng version **trong cùng statement**. Khi affected rows = 0, ứng dụng phải **xử lý xung đột thật sự**, không được lặng lẽ ghi đè. `@Transactional` đảm bảo rollback các thao tác trong cùng boundary; `@Version` của JPA có thể tự động hóa việc kiểm tra, nhưng không thay thế quản lý retry, transaction, dữ liệu stale giữa các request và invariants đa hàng.

## 12. Tài liệu tham khảo

- [Hibernate ORM — User Guide: Locking](https://docs.hibernate.org/orm/8.0/userguide/html_single/) — khái niệm optimistic/pessimistic locking, version check, phiên bản của entity, bulk update limitations.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — Spring transaction interceptor và rollback của một nhóm JDBC writes.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — annotation metadata, propagation, scope của AOP proxy.
- [Spring Framework — JDBC `JdbcTemplate`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html) — chạy SQL và đọc affected-row count.
- [Jakarta Persistence — `@Version`](https://jakarta.ee/specifications/persistence/) — contract của optimistic locking qua version attribute.
