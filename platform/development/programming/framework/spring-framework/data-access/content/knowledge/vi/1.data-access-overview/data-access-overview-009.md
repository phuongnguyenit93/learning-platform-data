# Lộ trình học và kiến thức Java, SQL cần có để học Spring Framework Data Access

> **Định hướng:** Bài này giúp bạn xác định kiến thức nền, thứ tự học, bài thực hành và tiêu chí sẵn sàng trước khi đi sâu vào các cơ chế truy cập dữ liệu của Spring Framework. Bạn không cần thuộc hết mọi API ngay từ đầu, nhưng cần hiểu dữ liệu đi từ Java đến cơ sở dữ liệu như thế nào, điều gì được bảo đảm bởi SQL/JDBC và Spring bổ sung phần nào.

## 1. Đích đến và ranh giới kiến thức

Sau lộ trình, bạn cần có khả năng:

1. Thiết kế bảng quan hệ đơn giản có khóa chính, khóa ngoại và ràng buộc; viết truy vấn SQL đúng kết quả và biết xem xét hiệu năng.
2. Dùng JDBC để hiểu `Connection`, `PreparedStatement`, `ResultSet`, giao dịch và quản lý tài nguyên.
3. Giải thích vai trò của `DataSource`, `JdbcTemplate`, `DataAccessException`, transaction manager và `@Transactional` trong Spring Framework.
4. Tách trách nhiệm giữa service, repository/DAO và cấu hình kết nối; viết luồng đọc/ghi có kiểm soát giao dịch.
5. Biết khi nào nên bắt đầu với Spring JDBC và khi nào cần tìm hiểu JPA/Hibernate hoặc các dự án Spring Data; kiểm thử được cả thành công lẫn rollback.

**Phạm vi:** Spring Framework Data Access tập trung vào JDBC, tích hợp ORM và quản lý giao dịch. Spring Data JPA, Spring Data JDBC, Spring Boot auto-configuration, hệ quản trị cơ sở dữ liệu và JPA/Hibernate là những thành phần liên quan nhưng có phạm vi riêng. Đừng đồng nhất `Spring Framework`, `Spring Boot`, `Spring Data`, `JPA` và `Hibernate`: Spring cung cấp hạ tầng truy cập dữ liệu và giao dịch; Boot thuận tiện hóa cấu hình; Spring Data cung cấp các mô hình repository; JPA là đặc tả; Hibernate là một ORM triển khai JPA phổ biến.

## 2. Bức tranh tổng thể trước khi học API

```text
HTTP / CLI / batch job
        ↓
Application service       ← quy tắc nghiệp vụ, ranh giới transaction
        ↓
Repository / DAO          ← câu lệnh SQL hoặc thao tác với entity
        ↓
JdbcTemplate / JPA        ← hỗ trợ thực thi, mapping, xử lý lỗi
        ↓
DataSource / connection   ← kết nối, pool, transaction resource
        ↓
Database                  ← bảng, khóa, index, ràng buộc, khóa giao dịch
```

- **Database** quyết định tính nhất quán dữ liệu qua constraint và transaction; Java không thể thay thế `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE` hay `CHECK`.
- **JDBC** là giao diện tiêu chuẩn của Java để làm việc với cơ sở dữ liệu quan hệ qua driver.
- **Spring JDBC** giảm mã lặp quanh lấy/đóng kết nối, statement, result set và chuyển đổi lỗi. Nó **không** tự thiết kế SQL, khóa, chỉ mục hay giao dịch đúng thay bạn.
- **Spring transaction abstraction** phối hợp transaction manager và tài nguyên đang được sử dụng. Một transaction phải bao trùm trọn đơn vị nghiệp vụ cần nguyên tử; annotation chỉ có hiệu lực khi được hạ tầng Spring áp dụng đúng.
- **ORM/JPA** ánh xạ đối tượng sang dữ liệu quan hệ và quản lý vòng đời entity; vẫn cần hiểu SQL, join, index, transaction và các truy vấn ORM phát sinh.

Một câu hỏi nền tảng nên trả lời được: “Khi chuyển 25 đơn vị tiền từ A sang B, việc trừ và cộng có cần cùng một transaction không; điều gì xảy ra nếu thao tác thứ hai lỗi?” Đáp án: cả hai bước phải nguyên tử; nếu lỗi trước commit thì cả hai thay đổi phải rollback.

## 3. Nền tảng Java cần học trước

| Nhóm | Phải hiểu | Bằng chứng thực hành |
| --- | --- | --- |
| Java 17+ và công cụ | JDK/JRE, `javac`/`java`, classpath, Gradle/Maven, dependency, logging cơ bản | Tạo project, thêm JDBC driver, chạy một `main` |
| OOP và thiết kế | class, interface, constructor, encapsulation, dependency injection, trách nhiệm của service và DAO | Viết `AccountRepository` interface và một implementation |
| Kiểu dữ liệu | primitive vs wrapper, `String`, `enum`, `BigDecimal`, `LocalDate`/`Instant`, `null` | Lưu số tiền bằng `BigDecimal`; xác định quy ước múi giờ |
| Collections và generics | `List<T>`, `Map<K,V>`, `Optional<T>`, vòng lặp, immutable DTO, `record` | Ánh xạ nhiều dòng thành `List<Account>` |
| Lambda và functional interfaces | lambda, method reference, xử lý callback | Đọc được `RowMapper<T>` và callback trong `JdbcTemplate` |
| Exception và tài nguyên | checked/unchecked exceptions, `try-with-resources`, `finally`, lan truyền lỗi | Đóng `Connection`/`Statement`/`ResultSet` kể cả khi truy vấn lỗi |
| Đa luồng cơ bản | thread safety, shared mutable state, race condition | Giải thích vì sao hai request không được chia sẻ cùng một `Connection` tùy tiện |
| Testing | JUnit, assertion, unit vs integration test | Kiểm chứng cập nhật thành công và rollback khi phát sinh lỗi |

**Những chi tiết dễ bỏ sót:**

- Dùng `BigDecimal` với giá trị tiền tệ và quy định rõ precision/scale; tránh tính tiền bằng `double` vì biểu diễn nhị phân không chính xác tuyệt đối.
- `java.time` phù hợp hơn API ngày giờ cũ; phân biệt thời điểm tuyệt đối (`Instant`) với ngày nghiệp vụ (`LocalDate`) và giờ địa phương (`LocalDateTime`).
- `Optional` thích hợp diễn đạt kết quả có thể không tồn tại ở ranh giới API; không dùng nó để che giấu dữ liệu bắt buộc hoặc thay thế mọi trường có thể null.
- Exception trong Java khác với lỗi SQL: cần biết phân loại lỗi, không nuốt exception rồi coi nghiệp vụ là thành công.
- Repository nên chứa logic truy cập dữ liệu; service quyết định trình tự và quy tắc nghiệp vụ. Không đặt mọi SQL và transaction ngay trong controller.

**Nếu còn yếu Java:** luyện một chương trình CRUD dữ liệu trong bộ nhớ trước, dùng interface + implementation + test; sau đó thay implementation bằng JDBC. Cách này tách được khó khăn thiết kế Java khỏi khó khăn database.

## 4. SQL và cơ sở dữ liệu quan hệ: mức tối thiểu bắt buộc

### 4.1. Mô hình dữ liệu và kiểu dữ liệu

Cần hiểu database/schema/table/row/column; khóa chính (`PRIMARY KEY`), khóa ngoại (`FOREIGN KEY`), khóa ứng viên và ràng buộc `NOT NULL`, `UNIQUE`, `CHECK`. Chọn kiểu dữ liệu phù hợp: `BIGINT` cho mã định danh dạng số, `VARCHAR` cho chuỗi có giới hạn, `DECIMAL(p,s)` cho giá trị chính xác, kiểu DATE/TIMESTAMP theo yêu cầu hệ quản trị. Đừng giả định SQL giữa PostgreSQL, MySQL, H2, Oracle và SQL Server luôn giống nhau.

Mô hình ví dụ:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL CHECK (total_amount >= 0),
    CONSTRAINT fk_orders_customers
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

INSERT INTO customers (id, full_name)
VALUES (1, 'An'), (2, 'Binh');

INSERT INTO orders (id, customer_id, total_amount)
VALUES (10, 1, 150.00), (11, 1, 50.00);
```

Cần hiểu vì sao một `orders.customer_id` không tồn tại phải bị từ chối bởi khóa ngoại; vì sao `DECIMAL` phù hợp với tiền; và vì sao một `CHECK` không thay thế kiểm tra nghiệp vụ trong service.

### 4.2. Đọc, ghi và tổng hợp dữ liệu

Học theo thứ tự:

1. `SELECT`, `FROM`, `WHERE`, `ORDER BY`, `LIMIT`/cú pháp phân trang của hệ quản trị.
2. `INSERT`, `UPDATE`, `DELETE`, điều kiện `WHERE` và số dòng bị tác động.
3. `INNER JOIN`, `LEFT JOIN` và cách dữ liệu thiếu ở bảng phải thể hiện thành `NULL`.
4. `GROUP BY`, `COUNT`, `SUM`, `HAVING`, `DISTINCT`, truy vấn con và `EXISTS` khi cần.
5. `NULL` và logic ba giá trị; dùng `IS NULL` thay cho `= NULL`.
6. Index, thứ tự truy cập dữ liệu, `EXPLAIN`/execution plan, chi phí đọc nhiều dòng.
7. Transaction, ACID, isolation, locking và các vấn đề cập nhật đồng thời.

Ví dụ đếm số đơn và tổng chi tiêu, kể cả khách chưa mua:

```sql
SELECT c.id,
       c.full_name,
       COUNT(o.id) AS order_count,
       COALESCE(SUM(o.total_amount), 0) AS spent
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
GROUP BY c.id, c.full_name
ORDER BY c.id;
```

Với dữ liệu đã chèn, An có 2 đơn với tổng 200.00; Binh có 0 đơn và tổng 0. `COUNT(o.id)` không đếm dòng `NULL` do `LEFT JOIN` tạo ra. Nếu dùng `COUNT(*)`, khách chưa mua vẫn có thể bị đếm thành 1 — một lỗi SQL rất thường gặp.

### 4.3. Transaction và concurrency

Một transaction là nhóm thao tác có kết quả **commit toàn bộ hoặc rollback toàn bộ** đối với cơ sở dữ liệu hỗ trợ transaction. Hiểu tính nguyên tử, nhất quán, cô lập và bền vững (ACID). Mức cô lập như `READ COMMITTED`, `REPEATABLE READ` hoặc `SERIALIZABLE` quy định các hiện tượng đồng thời có thể quan sát được; hành vi cụ thể phụ thuộc database.

Học qua ba tình huống:
- **Chuyển tiền:** trừ A và cộng B phải cùng transaction; kiểm tra số dư và dùng chiến lược tránh race condition.
- **Đặt hàng:** lưu đơn và chi tiết cùng đơn vị nghiệp vụ; lỗi khi lưu chi tiết phải không để đơn dang dở.
- **Cập nhật đồng thời:** hai request cùng đọc số lượng tồn rồi cùng trừ có thể làm mất cập nhật; tìm hiểu `UPDATE ... WHERE quantity >= ?` và kiểm tra affected rows, khóa bi quan hoặc optimistic locking.

Nắm rõ ranh giới: **transaction không thay cho constraint**, constraint không tự giải quyết mọi race condition, và chỉ tạo index khi truy vấn thực tế cần nó. Kế hoạch truy vấn và hiệu năng phải đo trên database mục tiêu với dữ liệu đủ đại diện.

## 5. JDBC là cầu nối bắt buộc trước Spring JDBC

JDBC cung cấp các khái niệm `Driver`, `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và `SQLException`. Một luồng truy vấn thuần JDBC thường là:

1. Lấy `Connection` từ `DataSource`.
2. Tạo `PreparedStatement` chứa SQL có tham số `?`.
3. Bind tham số đúng kiểu, gọi `executeQuery` hoặc `executeUpdate`.
4. Đọc `ResultSet` và ánh xạ từng dòng sang đối tượng Java.
5. Đóng tài nguyên bằng `try-with-resources`; quản lý commit/rollback nếu tự điều khiển transaction.

Mẫu minh họa JDBC dưới đây là **đoạn mã trong một method**, giả định có biến `DataSource dataSource` và `long customerId`, chưa phải chương trình độc lập:

```java
String sql = "SELECT id, full_name FROM customers WHERE id = ?";
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            String fullName = rs.getString("full_name");
            System.out.println(id + ": " + fullName);
        }
    }
}
```

Cần import `javax.sql.DataSource` và `java.sql.Connection`, `PreparedStatement`, `ResultSet`. Dùng bind parameter để truyền **giá trị** thay vì ghép input người dùng vào chuỗi SQL. Placeholder không dùng để thay tên bảng/cột; danh sách tên cột động phải được kiểm soát bằng whitelist ở ứng dụng.

Hiểu `autoCommit`: khi tự quản JDBC transaction, thường tắt auto-commit, thực hiện nhóm lệnh, commit khi thành công và rollback khi lỗi; khôi phục trạng thái hoặc đóng kết nối đúng cách. Khi dùng Spring-managed transaction, **để Spring quản lý kết nối/commit/rollback**, không tự gọi `connection.commit()` trong DAO.

**Tiêu chí qua chặng JDBC:** tự viết được một hàm đọc/ghi có parameter binding, resource cleanup, mapping một dòng và xử lý lỗi; giải thích được tại sao việc quản lý kết nối lặp đi lặp lại dễ sai.

## 6. Bản đồ API Spring Framework Data Access

| Thành phần | Vai trò | Cần thực hành |
| --- | --- | --- |
| `DataSource` | Nơi cấp JDBC connection; production thường dùng connection pool | Cấu hình URL, credentials, pool và lifecycle |
| `JdbcTemplate` | Thực thi SQL với callback, binding, mapping và dọn tài nguyên | `query`, `queryForObject`, `update`, `RowMapper` |
| `NamedParameterJdbcTemplate` | Tham số có tên thay vì `?` theo vị trí | Dùng `:id`, `:status` cho truy vấn nhiều tham số |
| `DataAccessException` | Hệ ngoại lệ truy cập dữ liệu dạng unchecked của Spring | Biết xem loại lỗi và nguyên nhân gốc, không nuốt lỗi |
| `PlatformTransactionManager` | Giao diện điều phối transaction | Phân biệt transaction manager theo công nghệ |
| `DataSourceTransactionManager` | Transaction manager cho một JDBC `DataSource` | Dùng với Spring JDBC trong ứng dụng mẫu |
| `TransactionTemplate` | Điều khiển transaction bằng callback | Thử commit và rollback theo chương trình |
| `@Transactional` | Khai báo ranh giới transaction qua hạ tầng Spring | Đặt tại service bean, kiểm tra interception |
| JPA `EntityManager` / Spring ORM | Làm việc với entity và persistence context khi chọn ORM | Nhận diện mapping, lazy loading, flush và N+1 |

`JdbcTemplate` không tự tạo một transaction mới cho mỗi lời gọi. Khi một transaction đang hoạt động và cùng `DataSource` được quản lý đúng, các thao tác JDBC tham gia transaction đó. Nếu không có transaction bao ngoài, hành vi commit phụ thuộc kết nối/driver và cấu hình database.

Ví dụ phân biệt ba cách: JDBC thuần cho bạn quyền điều khiển trực tiếp nhưng nhiều mã lặp; Spring JDBC vẫn yêu cầu viết SQL và mapping nhưng giảm ceremony; JPA làm việc chủ yếu qua entity/persistence context, đổi lại cần hiểu SQL do ORM sinh và chi phí truy vấn. Với bài nhập môn Data Access, nên thành thạo Spring JDBC **trước** khi đào sâu ORM.

## 7. Lộ trình học theo thứ tự phụ thuộc

| Chặng | Kiến thức chính | Bài tập kiểm chứng | Điều kiện chuyển chặng |
| --- | --- | --- | --- |
| 0. Java nền | OOP, generics, `BigDecimal`, exception, Gradle/Maven, test | Mô hình account và repository in-memory | Chạy test và giải thích ranh giới service/DAO |
| 1. SQL căn bản | DDL, DML, constraint, join, aggregate, NULL | Tạo customers/orders; truy vấn tổng chi tiêu | Truy vấn đúng cả khách chưa có đơn |
| 2. SQL vận hành | Index, execution plan, ACID, isolation, concurrency | Thử lỗi khóa ngoại, rollback, cập nhật cạnh tranh | Biết lý do dữ liệu sai và cách quan sát |
| 3. JDBC thuần | Driver, `DataSource`, prepared statement, result set, resource | CRUD một bảng bằng JDBC | Không nối chuỗi SQL từ input; đóng tài nguyên |
| 4. Spring JDBC | DI, `JdbcTemplate`, `RowMapper`, exception translation | Đổi DAO JDBC sang JdbcTemplate | Kết quả tương đương, mã truy cập rõ ràng |
| 5. Transaction Spring | `TransactionTemplate`, `@Transactional`, rollback, propagation | Chuyển tiền với trường hợp lỗi bước hai | Kiểm chứng dữ liệu không bị cập nhật một nửa |
| 6. Kiểm thử và vận hành | Test tích hợp, migrations, pool, log/metrics, EXPLAIN | Chạy test trên engine gần production | Có test thành công, rollback và input bất hợp lệ |
| 7. Mở rộng khi cần | JPA/Hibernate, Spring Data, batching, locking | So sánh SQL và ORM cho cùng use case | Giải thích N+1, mapping và trade-off |

Không cần ấn định số ngày cho mọi người. Hãy chuyển chặng khi làm được bài tập và giải thích được lỗi; học thêm thuật ngữ mà chưa viết được truy vấn/test sẽ tạo cảm giác tiến bộ giả.

## 8. Thực hành hoàn chỉnh: Spring JDBC + transaction (Java 17)

Ví dụ này dùng **Spring Framework 6.2.3** và **H2 2.3.232** để học cơ chế JDBC/transaction mà không cần khởi động server hay Spring Boot. Các phiên bản được cố định cho mục đích tái lập ví dụ; khi triển khai ứng dụng thật, chọn phiên bản được hỗ trợ và quản lý dependency đồng bộ. Cần JDK 17+ và Gradle có sẵn (hoặc Gradle Wrapper tương đương).

Tạo các file:

```text
spring-data-access-roadmap/
├── settings.gradle
├── build.gradle
└── src/main/java/lesson/DataAccessDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-data-access-roadmap'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.3'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'lesson.DataAccessDemo'
}
```

`src/main/java/lesson/DataAccessDemo.java`:

```java
package lesson;

import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class DataAccessDemo {
    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:lesson;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE accounts (
                    id BIGINT PRIMARY KEY,
                    owner VARCHAR(100) NOT NULL,
                    balance DECIMAL(12, 2) NOT NULL CHECK (balance >= 0)
                )
                """);

        jdbc.update("INSERT INTO accounts VALUES (?, ?, ?)",
                1L, "Minh", new BigDecimal("100.00"));
        jdbc.update("INSERT INTO accounts VALUES (?, ?, ?)",
                2L, "Lan", new BigDecimal("40.00"));

        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));

        // Cả hai UPDATE cùng commit khi callback thành công.
        tx.executeWithoutResult(status -> {
            jdbc.update("UPDATE accounts SET balance = balance - ? WHERE id = ?",
                    new BigDecimal("25.00"), 1L);
            jdbc.update("UPDATE accounts SET balance = balance + ? WHERE id = ?",
                    new BigDecimal("25.00"), 2L);
        });

        // UPDATE dưới đây phải rollback do RuntimeException.
        try {
            tx.executeWithoutResult(status -> {
                jdbc.update("UPDATE accounts SET balance = balance - ? WHERE id = ?",
                        new BigDecimal("10.00"), 1L);
                throw new IllegalStateException("demo rollback");
            });
        } catch (IllegalStateException expected) {
            // Chỉ bỏ qua lỗi đã chủ động tạo trong ví dụ học tập.
        }

        jdbc.query("SELECT id, owner, balance FROM accounts ORDER BY id",
                (RowCallbackHandler) rs -> {
                    System.out.printf("%d | %s | %s%n",
                            rs.getLong("id"),
                            rs.getString("owner"),
                            rs.getBigDecimal("balance").toPlainString());
                });
    }
}
```

Tại thư mục chứa `build.gradle`, chạy `gradle run`; nếu dự án đã có Wrapper thì dùng `./gradlew run` trên Unix/macOS hoặc `gradlew.bat run` trên Windows. Chương trình in hai dòng dữ liệu (ngoài log của Gradle):

```text
1 | Minh | 75.00
2 | Lan | 65.00
```

**Vì sao kết quả đúng?** Bước đầu giảm Minh từ 100.00 xuống 75.00 và tăng Lan từ 40.00 lên 65.00. Bước thử thứ hai giảm Minh 10.00 rồi cố ý ném `IllegalStateException`, nên Spring transaction manager rollback bước giảm đó. `JdbcTemplate` dùng connection do transaction đang ràng buộc với cùng `DataSource`. `DriverManagerDataSource` dùng để demo đơn giản, **không phải connection pool phù hợp cho production**. H2 là cơ sở dữ liệu thử nghiệm; hãy kiểm thử lại trên database thực tế vì dialect, kiểu dữ liệu, khóa và isolation có thể khác.

**Thử biến thể để hiểu sâu:** bỏ transaction bao quanh hai lệnh đầu rồi cố tình ném exception giữa hai lệnh, quan sát nguy cơ dữ liệu cập nhật một nửa; khôi phục transaction và xác nhận trạng thái cuối. Thêm một case trừ quá số dư để thấy `CHECK (balance >= 0)` bảo vệ dữ liệu, đồng thời viết rule nghiệp vụ rõ ràng trước khi gọi SQL.

## 9. Từ TransactionTemplate sang @Transactional

Sau khi hiểu transaction bằng callback, chuyển sang khai báo tại **public method của Spring-managed service bean**, để transaction interceptor thực sự có cơ hội áp dụng:

```java
// Mã minh họa ranh giới nghiệp vụ, chưa phải chương trình chạy độc lập:
// AccountRepository và các method debit/credit do ứng dụng tự định nghĩa.
@Service
public class TransferService {
    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        accounts.debit(fromId, amount);
        accounts.credit(toId, amount);
    }
}
```

Đoạn này cần các import Spring `@Service`, `@Transactional`, `BigDecimal`, cùng bean repository hợp lệ và hạ tầng transaction được bật/cấu hình; trong ứng dụng Spring Boot tương ứng, auto-configuration có thể chuẩn bị nhiều thành phần. Không suy ra rằng chỉ viết annotation là transaction chắc chắn đã hoạt động.

Các quy tắc phải nắm:

- `Propagation.REQUIRED` là mặc định: tham gia transaction hiện có hoặc mở mới nếu chưa có. `REQUIRES_NEW` tạo transaction độc lập khi hạ tầng hỗ trợ; `NESTED` dựa vào savepoint và khả năng transaction manager/database.
- Trong cấu hình mặc định, `@Transactional` rollback khi `RuntimeException` hoặc `Error` thoát ra ngoài; checked exception không tự rollback nếu chưa khai báo rule như `rollbackFor`. Một số cấu hình Spring mới có thể thay đổi mặc định toàn cục, nên kiểm tra dự án cụ thể.
- Với proxy mode thường dùng, lời gọi nội bộ từ method này sang method `@Transactional` khác **trên cùng một instance** không đi qua proxy, nên annotation ở method được gọi có thể không có hiệu lực như mong đợi.
- `readOnly = true` chủ yếu là hint/định hướng tối ưu, không bảo đảm cơ sở dữ liệu sẽ cấm mọi lệnh ghi.
- Không giữ transaction mở trong lúc chờ HTTP call chậm hoặc thao tác ngoài cơ sở dữ liệu không cần thiết. Transaction database không tự làm cho hệ thống ngoài (email, message broker, HTTP) rollback theo.
- Một transaction chỉ đúng khi những DAO tham gia dùng connection/transaction manager phù hợp; trộn tài nguyên độc lập đòi hỏi thiết kế rõ ràng.

Bài kiểm chứng: gọi service qua Spring bean, cho bước `credit` ném runtime exception; đọc lại database và assert cả hai số dư như cũ. Làm thêm test checked exception để xác nhận cấu hình rollback thật sự.

## 10. Các chủ đề tiếp theo sau Spring JDBC

**JPA/Hibernate:** học `@Entity`, `@Id`, quan hệ one-to-many/many-to-one, persistence context, trạng thái transient/managed/detached, dirty checking, flush, fetch eager/lazy, N+1 và transaction. Đọc SQL thật do ORM phát sinh. Không suy ra rằng gọi `save` luôn lập tức phát một câu `INSERT`, hoặc truy cập collection lazy sau khi context đóng luôn thành công.

**Spring Data JDBC / Spring Data JPA:** là các dự án Spring Data, giúp định nghĩa repository và query abstraction cho mô hình dữ liệu tương ứng. Chúng **không đồng nghĩa** Spring JDBC `JdbcTemplate` hoặc JPA/Hibernate; cách mapping và lifecycle của Spring Data JDBC khác JPA. Chỉ chọn khi bài toán phù hợp và khi bạn đã đọc được SQL/transaction phía dưới.

**Vận hành thực tế:** migration bằng Flyway/Liquibase; connection pool và giới hạn kết nối; transaction timeout; query timeout; batch updates; phân trang; index và execution plan; logging tham số nhạy cảm an toàn; idempotency cho retry; optimistic/pessimistic locking; kiểm thử tích hợp trên hệ quản trị gần production. Đây là chặng sau khi đã làm chủ kiến thức cơ bản.

## 11. Lỗi phổ biến và cách tự phát hiện

| Dấu hiệu | Nguyên nhân cần điều tra | Cách kiểm tra/cải thiện |
| --- | --- | --- |
| Kết quả join bị nhân dòng | Quan hệ 1-n, điều kiện join sai, aggregate sai | Vẽ cardinality, xem tập dữ liệu nhỏ, so `COUNT(*)` với `COUNT(column)` |
| Input gây SQL injection | Nối chuỗi từ input vào SQL | Dùng bind parameter; whitelist identifier động |
| Ghi thành công nửa chừng | Thiếu transaction bao toàn bộ use case | Thêm integration test ném lỗi ở bước giữa |
| `@Transactional` dường như không hoạt động | Bean không do Spring quản lý, self-invocation, thiếu config | Test qua bean/proxy, xem transaction log |
| Giao dịch vẫn commit dù lỗi | Exception bị nuốt hoặc checked exception không khớp rollback rule | Kiểm tra exception thoát ra và rule rollback |
| Số tiền lệch ít | Dùng `double`, scale/rounding không rõ | Dùng `BigDecimal` và quy tắc rounding tường minh |
| Truy vấn chậm khi dữ liệu tăng | Thiếu index phù hợp, truy vấn N+1, trả quá nhiều dòng | Kiểm tra SQL thật, `EXPLAIN`, pagination và metrics |
| Hết connection hoặc tài nguyên | Không đóng JDBC resource, pool quá nhỏ, transaction kéo dài | `try-with-resources` với JDBC thuần; quan sát pool và thời gian transaction |
| Test chạy H2 nhưng production lỗi | Dialect, constraint, isolation, kiểu dữ liệu khác | Integration test trên engine/phiên bản gần production |
| Cập nhật tồn kho bị âm hoặc mất lượt | Race condition, thiếu atomic update/locking/constraint | Viết test concurrent, dùng điều kiện UPDATE và kiểm tra affected rows |

Đừng bắt `Exception` rộng rồi trả về “thành công” hoặc giá trị mặc định. Hãy phân biệt lỗi nghiệp vụ dự kiến, lỗi dữ liệu, lỗi kết nối và bug; rollback, log có ngữ cảnh và trả lỗi đúng tầng.

## 12. Dự án nhỏ để khép kín lộ trình

Xây dựng **Mini Order Service** với `customers`, `products`, `orders`, `order_items` và `stock`. Không cần REST ở phiên bản đầu; chạy từ `main` hoặc test là đủ.

1. **Schema:** định nghĩa PK/FK/UNIQUE/NOT NULL/CHECK và migration có thể chạy lặp lại trong môi trường mới.
2. **SQL:** viết truy vấn liệt kê đơn theo khách, tổng tiền, sản phẩm chưa bán, top sản phẩm; nêu vì sao cần LEFT JOIN và một vài index.
3. **JDBC:** triển khai một query và một update dùng `PreparedStatement`, đóng tài nguyên đúng cách.
4. **Spring JDBC:** tạo DAO dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`; map row sang DTO/record; kiểm tra số dòng được cập nhật.
5. **Transaction:** đặt hàng gồm tạo order, thêm item, giảm stock trong một transaction; cố tình lỗi ở bước giữa để chứng minh rollback.
6. **Concurrency:** cho hai luồng cùng đặt phần hàng cuối; không để stock âm hoặc bán vượt tồn, dùng atomic conditional update/locking và test.
7. **Quality:** integration test cho thành công, khách/sản phẩm không tồn tại, lượng đặt không hợp lệ, lỗi constraint, rollback và truy vấn phân trang. Kiểm tra SQL log, thời gian và tài nguyên kết nối.

**Definition of Done:** mỗi nghiệp vụ có transaction boundary rõ ràng; SQL không nối input; dữ liệu được bảo vệ bằng constraint và code; test chỉ ra các trường hợp thất bại; bạn giải thích được công cụ nào chịu trách nhiệm cho mỗi tính chất.

## 13. Tự đánh giá mức sẵn sàng

Bạn có thể chuyển sang các bài Spring Framework Data Access chuyên sâu khi tự trả lời và minh họa được:

- `Connection`, `DataSource`, JDBC driver và connection pool khác nhau ở đâu?
- Tại sao `PreparedStatement` bảo vệ giá trị input tốt hơn SQL nối chuỗi; nó không xử lý được loại input động nào?
- `LEFT JOIN` khác `INNER JOIN` thế nào; vì sao `COUNT(o.id)` khác `COUNT(*)` trong ví dụ khách không có đơn?
- Khi nào chọn `DECIMAL`/`BigDecimal` và cần thống nhất scale/rounding ra sao?
- Spring `JdbcTemplate` làm gì giúp JDBC thuần, và vẫn để bạn chịu trách nhiệm những gì?
- Điều gì xảy ra với hai lệnh UPDATE nếu lỗi giữa chừng khi có hoặc không có transaction?
- Tại sao `@Transactional` gọi từ cùng class đôi khi không có tác dụng trong proxy mode?
- Checked exception có mặc định gây rollback không; làm sao chứng minh qua test thay vì phỏng đoán?
- Tại sao test H2 chưa đủ xác nhận truy vấn/index/locking ở PostgreSQL hoặc MySQL?
- Khi chọn ORM, làm sao phát hiện N+1 và hiểu transaction/persistence context?

Nếu chưa trả lời chắc một nhóm, quay lại chặng tương ứng và xây dựng một test nhỏ có thể tái hiện. Mục tiêu là **quan sát được kết quả và giải thích được cơ chế**, không phải học thuộc annotation.

## 14. Tài liệu chính thống để đi tiếp

- Java JDBC API: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/package-summary.html
- Spring Framework 6.2 – JDBC: https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc.html
- Spring Framework 6.2 – Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html
- Spring Framework 6.2 – `@Transactional`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- PostgreSQL SQL Tutorial (để thực hành SQL quan hệ trên một DB thật): https://www.postgresql.org/docs/current/tutorial-sql.html

Dùng tài liệu đúng **nhánh phiên bản đang chạy trong dự án**, đối chiếu hành vi với integration test và SQL mà database thực thi. Đây là nền vững để học Spring JDBC, transaction management và ORM theo thứ tự hiệu quả.