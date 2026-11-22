# Phân biệt quản lý tài nguyên, quản lý giao dịch và ánh xạ dữ liệu trong Spring Framework Data Access

## 1. Mục tiêu và bức tranh tổng thể

Khi một ứng dụng Java đọc hoặc ghi cơ sở dữ liệu, có ba câu hỏi độc lập nhưng thường xuất hiện trong cùng một lời gọi:

1. **Quản lý tài nguyên (resource management):** Ai lấy và trả kết nối, đóng câu lệnh và tập kết quả? Tài nguyên sống bao lâu?
2. **Quản lý giao dịch (transaction management):** Những thao tác nào phải thành công hoặc thất bại cùng nhau? Ai quyết định `commit`, `rollback` và ranh giới giao dịch?
3. **Ánh xạ dữ liệu (data mapping):** Hàng/cột từ cơ sở dữ liệu trở thành đối tượng Java như thế nào, và ngược lại?

Ví dụ một dịch vụ chuyển 30 đơn vị từ tài khoản A sang B. Nó cần kết nối để chạy SQL (**tài nguyên**), phải bảo đảm trừ A và cộng B là một đơn vị nhất quán (**giao dịch**), rồi chuyển dòng `account(id, balance)` thành `Account` để trả kết quả (**ánh xạ**). Cùng một lớp có thể dùng cả ba cơ chế, nhưng không cơ chế nào tự thay thế hai cơ chế còn lại.

| Khía cạnh | Quản lý tài nguyên | Quản lý giao dịch | Ánh xạ dữ liệu |
| --- | --- | --- | --- |
| Câu hỏi chính | Lấy, dùng, giải phóng *cái gì* và *khi nào*? | Thao tác nào thuộc cùng một đơn vị công việc? | Giá trị SQL và kiểu Java được chuyển đổi ra sao? |
| Đối tượng điển hình | `DataSource`, JDBC `Connection`, `PreparedStatement`, `ResultSet`, JPA `EntityManager` | `PlatformTransactionManager`, `@Transactional`, `TransactionTemplate` | `RowMapper`, `ResultSetExtractor`, JPA `@Entity`/`@Column`, DTO projection |
| Kết quả mong muốn | Không rò kết nối/cursor, dùng đúng kết nối trong ngữ cảnh | `commit` hoặc `rollback` đúng toàn bộ đơn vị công việc | Giá trị đúng kiểu, đúng cột, đúng quan hệ |
| Lỗi đặc trưng | Hết pool kết nối, cursor không đóng | Ghi một nửa, rollback không xảy ra, khóa giữ quá lâu | Sai tên cột, sai kiểu, dữ liệu trùng hoặc thiếu |
| Không có nghĩa là | Tự bảo đảm tính nguyên tử | Tự đóng mọi loại tài nguyên tùy ý | Tự mở giao dịch hoặc bảo đảm dữ liệu đã commit |

Đừng đồng nhất ba khái niệm vì một lời gọi `JdbcTemplate.query(...)` hoặc repository JPA có thể che giấu cả ba.

## 2. Quản lý tài nguyên: vòng đời kết nối và đối tượng truy cập dữ liệu

### 2.1. JDBC thuần và trách nhiệm đóng tài nguyên

Trong JDBC, một truy vấn điển hình lấy `Connection` từ `DataSource`, tạo `PreparedStatement`, thực thi và đọc `ResultSet`. Nếu tự viết JDBC, nên dùng `try-with-resources` cho các tài nguyên do mình sở hữu:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         "SELECT id, balance FROM account WHERE id = ?")) {
    statement.setLong(1, accountId);

    try (ResultSet rows = statement.executeQuery()) {
        if (rows.next()) {
            long id = rows.getLong("id");
            int balance = rows.getInt("balance");
            // Ở đây chỉ đang đọc và chuyển đổi dữ liệu.
        }
    }
}
~~~

*Đây là đoạn minh họa nằm trong một phương thức có sẵn `dataSource` và `accountId`; nó không phải chương trình Java độc lập.* `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` cả khi gặp ngoại lệ. Khi dùng pool, gọi `Connection.close()` thường là **trả kết nối logic về pool**, không nhất thiết đóng socket vật lý. Thiếu thao tác giải phóng có thể làm cạn pool dù SQL rất nhanh.

### 2.2. Spring giảm việc xử lý tài nguyên thủ công

- `JdbcTemplate` tạo/đóng `Statement`, `ResultSet` và lấy/giải phóng `Connection` qua cơ chế của Spring; lập trình viên tập trung vào SQL và kết quả.
- `DataSourceUtils.getConnection(dataSource)` biết kết nối đang gắn với giao dịch của Spring; `DataSourceUtils.releaseConnection(...)` không trả một kết nối đang cần cho giao dịch quá sớm. Không tự ý lấy một kết nối khác bằng `dataSource.getConnection()` rồi cho rằng nó luôn tham gia giao dịch hiện hành.
- `DataSourceTransactionManager` có thể gắn một `Connection` với luồng thực thi khi giao dịch bắt đầu; các thao tác `JdbcTemplate` dùng cùng `DataSource` sẽ tham gia ngữ cảnh đó. Sau `commit`/`rollback`, transaction manager dọn trạng thái và giải phóng kết nối.
- Với JPA, `EntityManager` và persistence context có vòng đời riêng, thường gắn với giao dịch; provider có thể trì hoãn việc lấy JDBC connection. Quản lý `EntityManager` không đồng nghĩa với việc một `Connection` vật lý luôn được giữ từ đầu đến cuối.

`DataSource` là điểm cung cấp kết nối. `DriverManagerDataSource` phù hợp bài học hoặc thử nghiệm, **không có pool**; ứng dụng thực tế thường dùng pool như HikariCP, theo dõi active/idle/waiting, thời gian chờ và rò rỉ. Đóng đủ tài nguyên không nói lên điều gì về việc **hai lệnh UPDATE đã được commit cùng nhau hay chưa**.

### 2.3. Phạm vi tài nguyên không nhất thiết bằng phạm vi phương thức

Không có giao dịch Spring, hai lệnh `jdbcTemplate.update(...)` có thể lấy hai kết nối và được database tự commit riêng theo cấu hình auto-commit. Trong một giao dịch JDBC đúng cách, Spring điều phối để các lệnh dùng kết nối liên quan đến cùng transaction. Việc pool có 20 kết nối không có nghĩa một giao dịch dùng cả 20 kết nối.

Ngược lại, mở transaction quá lâu có thể giữ kết nối và khóa quá lâu dù từng `ResultSet` đã đóng. Vì vậy cần đo **vòng đời tài nguyên** và **thời gian giao dịch** như hai tín hiệu khác nhau.

## 3. Quản lý giao dịch: ranh giới nhất quán

### 3.1. Giao dịch giải quyết vấn đề gì?

Một transaction nhóm các thay đổi phải tuân theo quy tắc nghiệp vụ chung. Chẳng hạn, chuyển tiền cần:

1. Kiểm tra điều kiện và số dư theo cơ chế kiểm soát đồng thời thích hợp.
2. Trừ A.
3. Cộng B.
4. Commit cả hai, hoặc rollback cả hai nếu bước cần thiết thất bại.

Nếu mỗi `UPDATE` tự commit riêng, lỗi giữa bước 2 và bước 3 để lại dữ liệu sai, **kể cả kết nối và statement đều được đóng đúng cách**. Transaction giải quyết tính nguyên tử; isolation và cơ chế khóa/phiên bản còn quyết định tác động của các giao dịch đồng thời. Transaction không tự ngăn chuyển số dư âm nếu nghiệp vụ không kiểm tra điều kiện, không tự giải quyết mọi race condition.

### 3.2. Cơ chế trong Spring

Spring định nghĩa `PlatformTransactionManager` cho mô hình transaction imperative; hai triển khai thường gặp là:

- `DataSourceTransactionManager`: điều phối giao dịch JDBC trên một `DataSource`.
- `JpaTransactionManager`: điều phối transaction JPA qua `EntityManagerFactory`; khi kết hợp JPA với JDBC phải kiểm tra cách cùng tham gia transaction và cấu hình nguồn dữ liệu tương ứng.

Hai cách phổ biến để đặt ranh giới:

**Khai báo** bằng `@Transactional` trên phương thức dịch vụ được gọi qua Spring proxy/AOP:

~~~java
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, int amount) {
        jdbc.update(
            "UPDATE account SET balance = balance - ? WHERE id = ?",
            amount, fromId);
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId);
    }
}
~~~

*Đoạn này cần ứng dụng Spring cấu hình `JdbcTemplate` và transaction manager; nó minh họa ranh giới, chưa có kiểm tra số dư/số hàng được cập nhật.* Proxy mở hoặc tham gia transaction trước lời gọi, rồi commit khi thành công hoặc rollback theo quy tắc rollback.

**Lập trình** bằng `TransactionTemplate`: gọi `execute(...)` hoặc `executeWithoutResult(...)`, phù hợp chương trình nhỏ và nơi cần kiểm soát một khối lệnh rõ ràng. Ví dụ runnable ở mục 5 dùng cách này để không cần khởi chạy Spring container.

### 3.3. Các thiết lập cần hiểu đúng

- **Propagation:** `REQUIRED` (mặc định) tham gia transaction hiện có, nếu chưa có thì tạo mới. `REQUIRES_NEW` tạo transaction độc lập, thường cần thêm kết nối; có thể gây áp lực lên pool. `NESTED` dùng savepoint khi transaction manager/tài nguyên hỗ trợ; không đồng nghĩa `REQUIRES_NEW`.
- **Isolation:** mức cô lập của database quyết định phạm vi quan sát và dị thường đồng thời có thể xảy ra; chọn theo yêu cầu nhất quán và khả năng DB, không dùng để thay việc thiết kế cập nhật có điều kiện.
- **Rollback mặc định:** trên transaction được điều phối bởi `@Transactional`, `RuntimeException` và `Error` thường gây rollback; checked exception mặc định không gây rollback nếu chưa cấu hình `rollbackFor`. Không được giả định mọi ngoại lệ đều rollback.
- **readOnly:** `@Transactional(readOnly = true)` là chỉ dẫn/hint cho transaction manager, JDBC driver hoặc provider tùy môi trường; không phải hàng rào quyền ghi dữ liệu đáng tin cậy.
- **Timeout:** giúp giới hạn thời gian giao dịch khi hệ thống và thao tác liên quan hỗ trợ; không thay thế timeout truy vấn/kết nối và quản lý retry.

**Giới hạn thường gặp của Spring AOP:** khi một phương thức trong bean gọi phương thức `@Transactional` khác qua `this`, lời gọi nội bộ có thể bỏ qua proxy, nên transaction mong đợi không được tạo. Một lời gọi qua `@Async` hoặc luồng mới cũng không tự kế thừa transaction imperative đang gắn với luồng cũ. Reactive transaction (R2DBC) có ngữ cảnh riêng và không nên suy diễn bằng quy tắc `ThreadLocal` của JDBC.

**Phân biệt rollback với bù trừ nghiệp vụ:** một database transaction không làm cho lời gọi HTTP, gửi email hay thanh toán ở hệ thống ngoài tự rollback. Với tác động xuyên hệ thống, cần thiết kế như outbox, idempotency hoặc saga tùy bài toán.

## 4. Ánh xạ dữ liệu: từ hàng và cột thành mô hình Java

### 4.1. Spring JDBC: ánh xạ tường minh

JDBC trả về `ResultSet` theo cột và kiểu SQL. `RowMapper<T>` chuyển **một hàng** thành **một đối tượng**; `JdbcTemplate.query(...)` duyệt nhiều hàng còn `queryForObject(...)` đòi hỏi số hàng đúng như mong đợi. Ví dụ:

~~~java
record Account(long id, int balance) {}

Account account = jdbcTemplate.queryForObject(
    "SELECT id, balance FROM account WHERE id = ?",
    (rs, rowNum) -> new Account(
        rs.getLong("id"),
        rs.getInt("balance")
    ),
    1L
);
~~~

*Đoạn này giả định có `jdbcTemplate` và bảng `account`; ví dụ đầy đủ ở mục 5.* Lambda `RowMapper` quyết định chính xác tên cột, chuyển kiểu và cấu trúc đối tượng. Nó **không** quyết định mở transaction, commit, rollback hay khi nào trả connection về pool. `ResultSetExtractor` hữu ích khi cần tổng hợp nhiều hàng thành một cấu trúc; `BeanPropertyRowMapper` có thể ánh xạ theo quy ước tên thuộc tính nhưng cần chú ý tên cột, kiểu dữ liệu và khả năng khởi tạo bean.

Không nên nhầm mapping với kiểm tra nghiệp vụ. Chuyển `balance` từ SQL `INTEGER` thành Java `int` không chứng minh số dư hợp lệ. Các giá trị `NULL`, kiểu ngày giờ, kiểu thập phân, enum và timezone cần cách biểu diễn phù hợp; dữ liệu tiền tệ thực tế thường cần kiểu và chính sách độ chính xác thích hợp, không lấy `int` trong ví dụ làm quy tắc cho mọi hệ thống.

### 4.2. JPA/ORM: ánh xạ đối tượng và quan hệ

Trong JPA, ánh xạ có thể được khai báo bằng `@Entity`, `@Id`, `@Column`, `@ManyToOne` và các cấu hình quan hệ. Provider chuyển đổi trạng thái entity ↔ câu lệnh SQL, duy trì identity/persistence context, dirty checking và flush. Đây là tầng mapping/phối hợp lưu trữ phong phú hơn `RowMapper`, nhưng vẫn cần transaction để bảo đảm những thao tác cần đồng nhất được commit cùng nhau.

Phân biệt rõ:

- **Mapping** xác định cột/quan hệ nào tương ứng với trường/đối tượng.
- **Persistence context** theo dõi entity được quản lý và thay đổi của nó.
- **Flush** đồng bộ các thay đổi đang chờ thành SQL; **flush không đồng nghĩa commit**.
- **Transaction** quyết định commit/rollback đối với các SQL phát sinh.
- **Resource management** quản lý `EntityManager`, JDBC connection và các tài nguyên bên dưới.

Lỗi `LazyInitializationException` thường cho thấy dữ liệu lazy được truy cập khi session/persistence context cần thiết không còn khả dụng; đó là vấn đề ở ranh giới fetch và vòng đời context, không thể kết luận chỉ cần tăng pool hoặc thêm transaction khắp nơi. Chiến lược fetch, projection và N+1 query cũng ảnh hưởng hiệu năng, nhưng không tự thay thế transactional consistency.

### 4.3. Spring Data repository che giấu chi tiết nhưng không xóa ranh giới

Repository như `JpaRepository` có thể đồng thời cung cấp API lưu/đọc, dùng `EntityManager`, mapping entity và tham gia transaction. Giao diện đơn giản không có nghĩa một repository chịu trách nhiệm đặt ranh giới nghiệp vụ cho nhiều repository khác nhau. Nếu một thao tác cần thay đổi hai aggregate/DAO cùng nhất quán, ranh giới transaction thường đặt ở **service** bao quanh toàn bộ thao tác. Việc chuyển entity sang DTO để trả API là một bước chuyển đổi riêng, không phải commit.

## 5. Ví dụ chạy được: ba trách nhiệm trong một chương trình Spring JDBC

Ví dụ dùng **JDK 17+**, **Maven 3.9+**, Spring JDBC 6.1.14 và H2 2.2.224. H2 chạy in-memory để quan sát commit/rollback. Tạo cấu trúc:

~~~text
spring-data-concerns/
├── pom.xml
└── src/main/java/demo/ConcernsDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-data-concerns</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.14</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/ConcernsDemo.java`**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.support.TransactionTemplate;

public class ConcernsDemo {
    record Account(long id, int balance) {}

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:concerns;DB_CLOSE_DELAY=-1", "sa", "");
        dataSource.setDriverClassName("org.h2.Driver");

        // Tài nguyên: JdbcTemplate lấy/trả kết nối, dọn statement/result set.
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE account (id BIGINT PRIMARY KEY, balance INT NOT NULL)");
        jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1L, 100);
        jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2L, 50);

        // Giao dịch: hai lệnh update được commit như một đơn vị.
        TransactionTemplate transaction = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));
        transaction.executeWithoutResult(status -> {
            jdbc.update("UPDATE account SET balance = balance - ? WHERE id = ?",
                    30, 1L);
            jdbc.update("UPDATE account SET balance = balance + ? WHERE id = ?",
                    30, 2L);
        });

        printBalances(jdbc, "Sau commit");

        // Lỗi sau UPDATE thứ nhất => transaction rollback toàn bộ.
        try {
            transaction.executeWithoutResult(status -> {
                jdbc.update("UPDATE account SET balance = balance - ? WHERE id = ?",
                        10, 1L);
                throw new IllegalStateException("Lỗi mô phỏng");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Giao dịch lỗi đã rollback");
        }

        printBalances(jdbc, "Sau rollback");
    }

    private static Account find(JdbcTemplate jdbc, long id) {
        // Ánh xạ: một hàng ResultSet trở thành record Account.
        return jdbc.queryForObject(
                "SELECT id, balance FROM account WHERE id = ?",
                (rs, rowNum) -> new Account(
                        rs.getLong("id"), rs.getInt("balance")),
                id);
    }

    private static void printBalances(JdbcTemplate jdbc, String prefix) {
        System.out.println(prefix + ": A=" + find(jdbc, 1L).balance()
                + ", B=" + find(jdbc, 2L).balance());
    }
}
~~~

Trong thư mục `spring-data-concerns`, chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConcernsDemo
~~~

Các dòng do chương trình in ra:

~~~text
Sau commit: A=70, B=80
Giao dịch lỗi đã rollback
Sau rollback: A=70, B=80
~~~

**Vì sao kết quả này đáng tin?**

1. `JdbcTemplate` giải phóng statement/result set và kết nối phù hợp từng ngữ cảnh (**resource management**). `DriverManagerDataSource` chỉ dùng cho demo; connection pooling trong production có thể thay thế mà không phải viết lại mapping.
2. `TransactionTemplate` gọi `DataSourceTransactionManager`. Trong callback, `JdbcTemplate` sử dụng transaction-bound connection cùng `DataSource`; hai `UPDATE` đầu commit với nhau. Lần chạy thứ hai ném `IllegalStateException` (unchecked) nên transaction rollback; A không bị trừ thêm 10 (**transaction management**).
3. Hàm `find` dùng `RowMapper` tạo `Account` từ hai cột; mapping vẫn hoạt động trước và sau rollback nhưng **không quyết định** commit (**data mapping**).

Ví dụ ưu tiên minh họa ranh giới trách nhiệm. Một hệ thống chuyển tiền thật cần kiểm tra số dư, xác minh số hàng cập nhật, kiểm soát truy cập đồng thời, idempotency, logging và cách xử lý lỗi theo yêu cầu nghiệp vụ.

## 6. Các tình huống dễ nhầm và cách chẩn đoán

| Triệu chứng | Hướng kiểm tra trước | Vì sao |
| --- | --- | --- |
| Pool hết connection, truy vấn chờ lâu | Kết nối/cursor chưa trả, transaction kéo dài, số kết nối đang giữ | Chủ yếu thuộc tài nguyên và vòng đời giao dịch |
| A đã bị trừ nhưng B chưa được cộng | Có transaction bao cả hai câu lệnh chưa; đúng transaction manager/DataSource chưa; rollback có hiệu lực không | Đóng connection đúng vẫn không đảm bảo atomicity |
| Lỗi trong phương thức `@Transactional` mà thay đổi vẫn commit | Phương thức có được gọi qua proxy không; ngoại lệ có bị nuốt không; checked exception có cấu hình rollback không | Quy tắc AOP/rollback quyết định kết quả |
| DTO có trường null hoặc ánh xạ sai | Alias/tên cột, kiểu SQL ↔ Java, mapping record/entity, nullability | Transaction không tự sửa mapping |
| `LazyInitializationException` | Thời điểm truy cập quan hệ lazy, fetch plan, vòng đời persistence context | Mapping/fetch phụ thuộc context; tăng connection pool không sửa nguyên nhân |
| Nhiều truy vấn ngoài dự kiến | N+1, fetch strategy, projection, batch fetch | Hành vi ORM và thiết kế query, không mặc định là leak |
| Deadlock/lost update khi nhiều người ghi | Isolation, locking, version column, thứ tự cập nhật, độ dài transaction | Transaction có tồn tại vẫn cần chính sách đồng thời |

Một số nguyên tắc thực hành:

- Đặt transaction quanh **một thao tác nghiệp vụ cần nhất quán**, thường ở service, thay vì tự động mở transaction dài cho mọi tầng. Tránh giữ transaction trong lúc gọi mạng hoặc thực hiện công việc tốn thời gian không cần thiết.
- Dùng tham số SQL (`?` hoặc named parameters) thay vì ghép dữ liệu người dùng vào chuỗi SQL; mapping không chống SQL injection.
- Dùng `JdbcTemplate` khi muốn kiểm soát SQL và mapping tường minh; dùng JPA/ORM khi phù hợp mô hình entity/quan hệ và yêu cầu theo dõi trạng thái. Cả hai vẫn phải có chính sách resource và transaction đúng.
- Phân biệt exception translation (ví dụ Spring chuyển `SQLException` thành hệ `DataAccessException`) với rollback: việc chuyển loại ngoại lệ hỗ trợ xử lý nhất quán, còn transaction manager mới quyết định rollback.
- Kiểm thử cả happy path lẫn ngoại lệ giữa hai thao tác ghi; đọc lại trạng thái database sau lỗi để chứng minh atomicity, không chỉ kiểm tra rằng exception đã được ném.

## 7. Tự kiểm tra hiểu bài

**Câu 1.** Hai `JdbcTemplate.update(...)` chạy thành công lần lượt, connection đều được trả. Có chắc hai lệnh tạo thành một giao dịch nguyên tử? **Không.** Phải có transaction boundary bao trùm cả hai; nếu không, mỗi thao tác có thể được auto-commit riêng.

**Câu 2.** Thêm `@Transactional` có tự động làm `RowMapper` chuyển đúng tên cột? **Không.** Mapping vẫn cần cấu hình/logic đúng. Transaction quyết định tính nhất quán của thay đổi, không diễn giải dữ liệu trả về.

**Câu 3.** JPA gọi `flush()` có nghĩa dữ liệu đã commit? **Không.** Flush đẩy SQL xuống database trong transaction; rollback vẫn có thể hủy những thay đổi đó.

**Câu 4.** Đóng connection sớm khi transaction Spring chưa kết thúc có đúng không? **Không.** Dùng cơ chế quản lý tài nguyên của Spring để kết nối tham gia transaction được giữ và giải phóng đúng thời điểm.

**Câu 5.** Nếu giao dịch rollback nhưng hệ thống đã gửi email thông báo, email có được thu hồi? **Không.** Transaction cơ sở dữ liệu không bao trùm tác động của dịch vụ ngoài; cần thiết kế nhất quán liên hệ thống riêng.

**Ghi nhớ:** quản lý tài nguyên trả lời *sử dụng và giải phóng kết nối ra sao*; quản lý giao dịch trả lời *những thay đổi nào commit/rollback cùng nhau*; ánh xạ dữ liệu trả lời *SQL và đối tượng Java biểu diễn nhau thế nào*. Thiết kế data access đúng cần cả ba, với ranh giới trách nhiệm rõ ràng.
