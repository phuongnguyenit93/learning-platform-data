# Giới hạn của try-with-resources khi thao tác với tài nguyên được Spring quản lý

Trong Java, `try-with-resources` là cách rất tốt để đóng `Connection`, `PreparedStatement`, `ResultSet`, stream hoặc các đối tượng triển khai `AutoCloseable`. Nhưng trong ứng dụng Spring, **không phải mọi đối tượng có `close()` đều thuộc quyền đóng của đoạn mã đang sử dụng nó**. Một connection có thể đang được transaction manager giữ tới lúc commit/rollback; một `EntityManager` được inject có thể là proxy gắn với persistence context; một `DataSource` có thể là bean sống suốt vòng đời ứng dụng.

Vì vậy, giới hạn quan trọng của `try-with-resources` là: **nó biết phạm vi từ vựng của khối `try`, nhưng không biết chủ sở hữu hoặc thời điểm kết thúc vòng đời mà Spring đã xác lập**. Muốn dọn tài nguyên đúng, cần phân biệt tài nguyên tự tạo/tự mượn với tài nguyên được Spring cấp, chia sẻ và giải phóng theo transaction hoặc container.

Bài này giải thích cơ chế của Java, các trường hợp đúng/sai trong Spring JDBC và JPA, cách xử lý stream và exception, rồi minh họa bằng ví dụ Java 17+ với Spring JDBC.

## 1. `try-with-resources` thực sự bảo đảm điều gì?

Cú pháp Java:

```java
// Ví dụ minh họa; resourceA/resourceB triển khai AutoCloseable.
try (Resource resourceA = openA();
     Resource resourceB = openB()) {
    use(resourceA, resourceB);
}
```

Đây là mã giả minh họa, không phải file Java chạy độc lập; `Resource`, `openA`, `openB` và `use` đại diện cho API thực tế.

Java bảo đảm:

1. Đóng mọi tài nguyên **đã khởi tạo thành công** trong header khi thoát khỏi khối `try`, kể cả khi có `return`, `break` hay exception.
2. Đóng theo thứ tự **ngược thứ tự khai báo**: `resourceB.close()` trước, `resourceA.close()` sau.
3. Nếu thân `try` ném exception và `close()` cũng lỗi, exception từ thân `try` thường được giữ làm exception chính, còn lỗi trong `close()` xuất hiện ở `getSuppressed()`.
4. Gọi `close()` đúng theo hợp đồng của đối tượng Java đó; **Java không hiểu giao dịch Spring, connection pool, transaction propagation, ranh giới commit/rollback hoặc session do container quản lý**.

Từ điều (4) có hai rủi ro đối xứng:

- **Đóng quá sớm:** dùng `try-with-resources` với tài nguyên mà transaction manager còn cần sau khi block kết thúc.
- **Đóng sai tầng:** gọi `close()` trên một đối tượng mà code chỉ được **mượn để sử dụng**, còn Spring quản lý vòng đời, hoặc đóng một proxy không tương đương với giải phóng tài nguyên thực sự.

Ngược lại, bỏ `try-with-resources` với tài nguyên do chính mình mở (ví dụ `ResultSet` hoặc `InputStream` độc lập) có thể gây rò rỉ. Mục tiêu không phải tránh `try-with-resources`, mà là **áp dụng nó ở đúng ranh giới sở hữu**.

## 2. Ba phạm vi khác nhau: lexical scope, resource ownership, transaction scope

```text
Phương thức @Transactional bắt đầu
│
├─ Transaction manager lấy/bind JDBC Connection (khi cần)
│   │
│   ├─ Repository gọi một khối try-with-resources
│   │   ├─ tạo PreparedStatement
│   │   ├─ chạy SQL / đọc ResultSet
│   │   └─ đóng PreparedStatement/ResultSet  ← đúng phạm vi
│   │
│   ├─ Repository khác tiếp tục dùng connection cùng transaction
│   │
│   └─ commit hoặc rollback do transaction manager quyết định
│
└─ Spring unbind/release Connection về DataSource/pool
Phương thức transaction hoàn tất
```

Ở ví dụ trên, khối `try` chỉ bao quanh một statement. Transaction có thể bao quanh **nhiều repository** và dài hơn block `try`. Nếu đóng luôn connection gắn với transaction ở cuối block, thao tác tiếp theo hoặc commit có thể thất bại.

| Câu hỏi | Ai trả lời? | Ý nghĩa |
| --- | --- | --- |
| `close()` sẽ được gọi khi nào? | Cú pháp `try-with-resources`, tại cuối lexical scope. | Chỉ là lịch đóng do Java quyết định. |
| Code này có quyền gọi `close()` trên đối tượng nào? | Hợp đồng API và **quyền sở hữu** tài nguyên. | Tài nguyên mượn từ container có thể cần giao cho container release. |
| Giao dịch commit/rollback khi nào? | Transaction manager và quy tắc giao dịch. | Có thể xảy ra sau khi nhiều khối `try` đã kết thúc. |
| Có đóng kết nối vật lý hay trả về pool? | `DataSource`, proxy/pool và tình trạng kết nối. | `Connection.close()` trên handle pool thường là trả handle, không nhất thiết cắt socket. |

Không có quan hệ “một khối `try` bằng một giao dịch”. Một transaction có thể chứa nhiều khối `try`; một khối `try` cũng có thể không tham gia transaction Spring nào.

## 3. Bảng quyết định nhanh theo loại tài nguyên

| Nguồn tài nguyên | Có nên dùng `try-with-resources` trực tiếp? | Cách giải phóng đúng |
| --- | --- | --- |
| `DriverManager.getConnection(...)` do chính code gọi | **Có**, nếu code sở hữu connection. | `Connection.close()` cuối phạm vi; commit/rollback riêng khi auto-commit tắt. |
| `dataSource.getConnection()` từ pool **ngoài** giao dịch Spring, code tự mượn | **Thường có**. | Đóng handle để trả pool; vẫn phải kết thúc transaction tự quản lý. |
| `DataSourceUtils.getConnection(dataSource)` | **Không đặt connection vào header `try`** khi muốn tương thích transaction Spring. | Dùng `DataSourceUtils.releaseConnection(con, dataSource)` trong `finally`. |
| `Connection` đưa vào `JdbcTemplate.execute(ConnectionCallback)` | **Không đóng connection callback nhận được**. | Spring/JdbcTemplate chịu trách nhiệm; chỉ đóng tài nguyên con tự tạo khi cần. |
| `Connection` từ `TransactionAwareDataSourceProxy` | **Có thể có**, vì proxy xử lý `close()` theo transaction nếu cấu hình đúng. | Dùng theo hợp đồng proxy; transaction manager vẫn quản lý DataSource đích. |
| `PreparedStatement` / `ResultSet` mà code tự tạo | **Có**, kể cả khi dùng connection do Spring quản lý. | Đóng statement/result set ở cuối thao tác, giữ connection cho chủ sở hữu. |
| `EntityManager` được inject bằng `@PersistenceContext` | **Không dùng `try-with-resources` để quản lý vòng đời**. | Spring/container quản lý persistence context, transaction và cleanup. |
| `EntityManagerFactory.createEntityManager()` do code tự tạo | **Có thể dùng** với Jakarta Persistence hỗ trợ `AutoCloseable`. | Chủ tạo ra EntityManager phải đóng; tự quyết định transaction theo cấu hình thích hợp. |
| `Stream<T>` do `JdbcTemplate.queryForStream(...)` trả | **Có, nên dùng** quanh **stream**. | `Stream.close()` giải phóng cursor/statement; tiêu thụ trước khi hết transaction cần thiết. |
| `InputStream` lấy bằng `Resource.getInputStream()` | **Có** với stream đã mở do code sở hữu. | Đóng stream; không suy ra phải đóng luôn bean `Resource`. |
| `HikariDataSource` được Spring quản lý như bean | **Không đóng trong request/service**. | Spring đóng pool theo vòng đời application context hoặc chủ sở hữu bean. |

Bảng áp dụng cho Spring JDBC/JPA đồng bộ thông thường. Trong luồng reactive R2DBC, mô hình sở hữu gắn với publisher và subscriber; `try-with-resources` bao quanh một lệnh trả `Mono`/`Flux` thường kết thúc trước khi I/O thực sự được đăng ký/chạy.

## 4. Sai lầm thứ nhất: mở connection thô trong `@Transactional`

Xét service dưới đây. Giả định `dataSource` trỏ trực tiếp tới pool hoặc driver `DataSource` thông thường, **không phải `TransactionAwareDataSourceProxy`**.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WrongPaymentService {
    private final DataSource dataSource;

    public WrongPaymentService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Transactional
    public void pay(long invoiceId) throws SQLException {
        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(
                 "UPDATE invoice SET paid = TRUE WHERE id = ?")) {
            ps.setLong(1, invoiceId);
            ps.executeUpdate();
        }

        // Nếu thao tác này ném lỗi, UPDATE phía trên
        // có thể đã commit độc lập khi auto-commit = true.
        throw new IllegalStateException("Downstream failure");
    }
}
```

Đây là đoạn code **minh họa tình huống sai**, cần ứng dụng Spring có `DataSource`, bảng `invoice` và transaction management; không phải chương trình độc lập.

Vấn đề không nằm ở cú pháp `try`. `dataSource.getConnection()` trên DataSource gốc có thể cấp **một connection mới ngoài connection đã bind vào transaction Spring**. Nếu connection ấy bật auto-commit, `UPDATE` có thể được commit ngay, bất chấp `@Transactional` ở service sau đó rollback transaction mà Spring sở hữu. Gọi `close()` chỉ trả handle đó về pool; nó không đưa câu SQL đã commit quay về giao dịch khác.

Thậm chí khi connection thô đặt `autoCommit(false)`, đây vẫn là một giao dịch JDBC **tự quản lý và độc lập**, không tự hợp nhất vào transaction Spring. Nếu muốn Spring quản lý ranh giới nghiệp vụ, hãy để mọi thao tác liên quan tham gia đúng transaction manager/DataSource.

Cách thường dùng là `JdbcTemplate`:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void pay(long invoiceId) {
        int changed = jdbc.update(
            "UPDATE invoice SET paid = TRUE WHERE id = ?",
            invoiceId
        );
        if (changed != 1) {
            throw new IllegalStateException("Invoice not found");
        }

        // Một RuntimeException ở bước tiếp theo
        // khiến transaction Spring rollback theo mặc định.
        performBusinessChecks();
    }

    private void performBusinessChecks() {
        // Logic nghiệp vụ thực tế được triển khai tại đây.
    }
}
```

Code thứ hai là ví dụ **tích hợp Spring**, không có schema/database hoàn chỉnh để chạy độc lập. `JdbcTemplate` sử dụng cơ chế `DataSourceUtils` để lấy connection tương thích với transaction đã bind. Không tự đóng connection hay gọi commit/rollback trong repository nếu Spring đang quản lý transaction.

Điều kiện áp dụng: transaction manager thích hợp, bean Spring và interception `@Transactional` thực sự hoạt động; self-invocation trên cùng bean trong proxy mode thường không kích hoạt interceptor mới.

## 5. Sai lầm thứ hai: đóng connection do `DataSourceUtils` cấp

Spring cung cấp `DataSourceUtils.getConnection(dataSource)` để tham gia các transaction JDBC gắn với luồng hiện tại. Khi có connection đã bind cho cùng DataSource, lời gọi này trả về connection tương ứng; khi không có transaction, nó có thể lấy connection mới từ DataSource.

Mã sau **nguy hiểm bên trong transaction Spring**:

```java
// SAI trong trường hợp connection đã bind vào transaction Spring.
try (Connection con = DataSourceUtils.getConnection(dataSource)) {
    doSomething(con);
}
// Java gọi con.close() trực tiếp, có thể đóng connection
// mà transaction manager còn cần để tiếp tục / commit.
```

Ở đây `DataSourceUtils.getConnection` không tự biến `Connection.close()` thành một thao tác transaction-aware. Khi code gọi trực tiếp `close()` trên connection đã bind, nó có thể đóng connection vật lý hoặc trả handle về pool **quá sớm**. Transaction manager vẫn coi connection đó đang thuộc giao dịch, nên câu SQL kế tiếp hoặc commit có thể gặp lỗi “connection closed”/trạng thái không hợp lệ. Hành vi cụ thể phụ thuộc driver, proxy và pool.

Cách đúng là dùng cặp API tương ứng của Spring:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;

public final class SpringJdbcAccess {
    private final DataSource dataSource;

    public SpringJdbcAccess(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int markProcessed(long jobId) {
        Connection con = DataSourceUtils.getConnection(dataSource);
        try (PreparedStatement ps = con.prepareStatement(
                "UPDATE job SET processed = TRUE WHERE id = ?")) {
            ps.setLong(1, jobId);
            return ps.executeUpdate();
        } catch (SQLException ex) {
            throw new IllegalStateException("JDBC write failed", ex);
        } finally {
            DataSourceUtils.releaseConnection(con, dataSource);
        }
    }
}
```

Đây là class có thể biên dịch với Spring JDBC, nhưng cần DataSource và bảng `job` thực tế để chạy.

Cơ chế cần hiểu:

1. `getConnection` lấy một connection phù hợp với transaction hiện tại.
2. `PreparedStatement` **do phương thức tạo** nên `try-with-resources` được phép đóng nó.
3. `releaseConnection(con, dataSource)` kiểm tra connection có đang gắn với transaction Spring phù hợp hay không.
4. Nếu đang gắn với transaction, Spring tránh đóng connection sớm; transaction manager release khi transaction kết thúc. Nếu không có transaction phù hợp, Spring có thể gọi close để trả connection cho pool/driver.
5. Gọi `releaseConnection` phải dùng đúng DataSource tương ứng với connection đã lấy. Không tráo đối tượng DataSource/proxy giữa hai lần gọi.

Không gọi `con.commit()`, `con.rollback()` hoặc tự đổi auto-commit bên trong phạm vi mà transaction manager Spring đang sở hữu. Nếu muốn transaction có kiểm soát bằng code, dùng `TransactionTemplate` hoặc API transaction của Spring.

## 6. Một ngoại lệ có chủ ý: `TransactionAwareDataSourceProxy`

Spring cung cấp `TransactionAwareDataSourceProxy` cho **code JDBC thuần không biết `DataSourceUtils`** nhưng vẫn cần tham gia transaction Spring.

```java
// Minh họa cấu hình; targetDataSource là DataSource thực.
DataSource aware = new TransactionAwareDataSourceProxy(targetDataSource);

// Code JDBC thuần dùng "aware":
try (Connection con = aware.getConnection();
     PreparedStatement ps = con.prepareStatement(
         "SELECT name FROM item WHERE id = ?")) {
    ps.setLong(1, itemId);
    try (ResultSet rs = ps.executeQuery()) {
        // Tiêu thụ kết quả ở đây.
    }
}
```

Đoạn trên là mã **tích hợp**; cần import JDBC/Spring, `targetDataSource`, `itemId` và schema thật. `TransactionAwareDataSourceProxy` trả connection proxy có xử lý `close()` và liên hệ `DataSourceUtils`. Nếu connection được Spring giữ cho transaction, lời gọi `close()` trên **proxy** được xử lý để không đóng connection gốc trước thời điểm cần thiết; ngoài transaction, cơ chế release bình thường được áp dụng.

Các ràng buộc quan trọng:

- Transaction manager phải làm việc với **DataSource gốc**, không dùng proxy awareness này làm nguồn điều phối chính.
- Proxy phải được kết nối và sắp xếp đúng với các DataSource proxy khác; Spring yêu cầu `TransactionAwareDataSourceProxy` là lớp ngoài cùng nếu dùng chuỗi proxy/adapter.
- Chỉ vì một đối tượng mang kiểu `DataSource` không có nghĩa nó transaction-aware. Đừng sao chép ví dụ này sang `HikariDataSource`/`DriverManagerDataSource` trực tiếp rồi mong `close()` được chặn.
- Nếu có thể sửa code, ưu tiên `JdbcTemplate` hoặc `DataSourceUtils`; proxy chủ yếu hữu ích với API JDBC cũ.

Đây là lý do không thể đưa ra quy tắc máy móc “`Connection.close()` luôn sai khi có Spring” hoặc “`try-with-resources` luôn an toàn với `Connection`”. **Điều quyết định là hợp đồng của đối tượng được trao và chủ sở hữu vòng đời.**

## 7. `JdbcTemplate` và callback: framework đóng connection, code đóng phần mình tạo

`JdbcTemplate` đã quản lý việc mở/release connection, đóng statement/result set theo các thao tác chuẩn và chuyển nhiều `SQLException` sang `DataAccessException`. Vì thế, code business chỉ cần gọi các phương thức của template:

```java
// Ví dụ tích hợp; jdbc là JdbcTemplate được cấu hình.
int updated = jdbc.update(
    "UPDATE job SET processed = TRUE WHERE id = ?",
    jobId
);
```

Nếu cần truy cập JDBC API thấp hơn, có thể dùng `ConnectionCallback`:

```java
import java.sql.PreparedStatement;
import org.springframework.jdbc.core.ConnectionCallback;

// Đoạn minh họa trong ứng dụng có jdbc và jobId.
Integer updated = jdbc.execute((ConnectionCallback<Integer>) con -> {
    try (PreparedStatement ps = con.prepareStatement(
            "UPDATE job SET processed = TRUE WHERE id = ?")) {
        ps.setLong(1, jobId);
        return ps.executeUpdate();
    }
});
```

Trong callback, `con` được `JdbcTemplate` cấp cho công việc; **không đặt `con` vào header `try` và không tự close nó**. `PreparedStatement` do callback tự tạo nên được đóng bằng `try-with-resources`. Để callback kết thúc, `JdbcTemplate` sẽ xử lý việc release theo transaction context của Spring.

Tương tự, khi sử dụng `RowMapper` hoặc `ResultSetExtractor`, framework nắm việc đóng `ResultSet` và statement phù hợp; callback chỉ nên đọc dữ liệu trong thời gian được gọi. Không trả trực tiếp một `ResultSet` còn sống ra khỏi callback để dùng sau khi template đã dọn tài nguyên.

## 8. `EntityManager` và persistence context do Spring quản lý

Với Spring JPA, một field được inject:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class ArticleRepository {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void rename(long id, String newTitle) {
        Article article = entityManager.find(Article.class, id);
        if (article == null) {
            throw new IllegalArgumentException("Article not found");
        }
        article.setTitle(newTitle);
    }
}
```

Đây là đoạn tích hợp cần entity `Article` và JPA provider/configuration, không phải file chạy độc lập.

`EntityManager` qua `@PersistenceContext` thường là một **shared proxy** trỏ tới EntityManager phù hợp với transaction hiện tại. Spring quản lý lúc nào persistence context được tạo, tham gia transaction, flush và đóng. Không viết:

```java
// SAI về mặt ownership với EntityManager được inject.
try (EntityManager em = entityManager) {
    em.persist(new Article());
}
```

Mặc dù `EntityManager` trong Jakarta Persistence hiện đại triển khai `AutoCloseable`, điều đó **không chuyển quyền sở hữu persistence context sang phương thức sử dụng**. Với một số proxy `@PersistenceContext` của Spring, `close()` còn có thể bị suppress; điều này càng cho thấy khối `try` không phải cơ chế điều phối vòng đời ở đây. Với EntityManager gốc không được proxy bảo vệ, đóng sai lúc có thể phá hỏng thao tác tiếp theo.

Một EntityManager do **chính ứng dụng tạo** bằng `entityManagerFactory.createEntityManager()` lại có trách nhiệm khác: code tạo phải đóng nó sau khi kết thúc công việc và xử lý transaction theo kiểu quản lý được cấu hình. Với Jakarta Persistence 3.1+, EntityManager là `AutoCloseable`, nên có thể đặt EntityManager ứng dụng sở hữu trong `try-with-resources`. Tuy nhiên, nó không tự tham gia transaction Spring chỉ vì được tạo bên trong một phương thức `@Transactional`.

Tương tự trong Hibernate: một `Session` do ứng dụng tự `openSession()` thường phải đóng theo hợp đồng của nó; còn `getCurrentSession()` được liên kết với ngữ cảnh giao dịch nên không nên tự đóng như session tự tạo. Hãy kiểm tra đúng cách lấy tài nguyên trước khi chọn `close()`.

**Phân biệt thêm:** `flush()` của JPA có thể đồng bộ SQL xuống DB nhưng không đồng nghĩa `commit`. `try-with-resources` không biến flush thành commit và không bảo đảm rollback nếu code đóng một persistence context không do mình sở hữu.

## 9. Stream từ Spring: một nơi `try-with-resources` thực sự cần thiết

Một số API trả về đối tượng `Stream<T>` **còn gắn với cursor/statement**. Ví dụ `JdbcTemplate.queryForStream(...)` trả stream cần được đóng sau khi tiêu thụ, vì một terminal operation như `count()` hoặc `toList()` **không tự động gọi `Stream.close()`**.

Ví dụ dùng `try-with-resources` đúng trên **stream**, không đóng connection thủ công:

```java
import java.util.List;
import java.util.stream.Stream;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskReportService {
    private final JdbcTemplate jdbc;

    public TaskReportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(readOnly = true)
    public List<Long> loadIds() {
        try (Stream<Long> ids = jdbc.queryForStream(
                "SELECT id FROM task ORDER BY id",
                (rs, rowNum) -> rs.getLong(1))) {
            return ids.toList();
        }
    }
}
```

Đây là service tích hợp, cần bảng `task` và transaction manager thích hợp. Stream được **mở, tiêu thụ và đóng trong cùng phạm vi method/transaction**. Khi stream đóng, Spring có thể dọn cursor/statement và release connection theo đúng ownership; nếu transaction vẫn tồn tại, connection chưa nhất thiết được trả về pool cho đến cuối transaction.

Phản ví dụ:

```java
// Minh họa không nên áp dụng cho stream giữ cursor sống.
@Transactional(readOnly = true)
public Stream<Long> loadIds() {
    return jdbc.queryForStream(
        "SELECT id FROM task ORDER BY id",
        (rs, rowNum) -> rs.getLong(1));
}
// Caller có thể tiêu thụ stream sau khi transaction đã kết thúc.
```

Nếu caller dùng stream sau khi service return, transaction có thể đã đóng; cursor/JDBC resource hoặc lazy loading có thể không còn hợp lệ. Người gọi cũng có nguy cơ quên đóng stream. Cách an toàn phổ biến là **tiêu thụ và đóng stream bên trong transaction**, rồi trả về DTO hoặc danh sách dữ liệu đã materialize. Với stream từ repository JPA, giới hạn transaction và cleanup cũng phải được đánh giá theo provider/cách truy vấn.

Với `InputStream`/`Reader` do code gọi `Resource.getInputStream()` hoặc API file, có thể dùng `try-with-resources` để đóng stream được mở. Đừng vì vậy đóng luôn bean `Resource` hay cả `ApplicationContext`: vòng đời bean là việc của container.

## 10. `try-with-resources` không thay thế chính sách rollback

Xét phương thức sau:

```java
// Đoạn minh họa, không phải một chương trình độc lập.
@Transactional
public void importData() throws java.io.IOException {
    jdbc.update("INSERT INTO audit_event(id) VALUES (1)");

    try (java.io.InputStream input = openInput()) {
        consume(input); // Có thể ném IOException.
    }
}
```

`try-with-resources` chỉ bảo đảm gọi `input.close()`. Nó **không quyết định** liệu `INSERT` sẽ rollback. Với cấu hình `@Transactional` mặc định trong Spring, một `RuntimeException`/`Error` thoát ra ngoài thường kích hoạt rollback; checked exception như `IOException` **không tự động** làm rollback trừ khi cấu hình rollback rule hoặc đánh dấu rollback-only.

Nếu việc đọc file thất bại phải hủy transaction, có thể đặt:

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void importData() throws java.io.IOException {
    // Các thao tác dữ liệu và đọc file thuộc cùng nghiệp vụ.
}
```

Cả hai đoạn trong mục này là **minh họa**, không có `openInput`/`consume` cụ thể để chạy độc lập. Cấu hình `rollbackFor` áp dụng cho exception đi ra ngoài interception phù hợp. Nếu exception bị bắt và method kết thúc bình thường, Spring có thể commit, trừ trường hợp transaction đã bị đánh dấu rollback-only vì nguyên nhân khác.

Đặc biệt, nếu thân `try` thành công nhưng `close()` ném exception, quyết định rollback vẫn phụ thuộc loại exception và chính sách transaction. Nếu thân `try` và `close()` đều lỗi, xem `Throwable.getSuppressed()` để không bỏ sót nguyên nhân cleanup.

**Không dùng `try-with-resources` để tưởng tượng một transaction con.** `@Transactional` với `REQUIRED`, `REQUIRES_NEW`, `NESTED` hay `TransactionTemplate` mới là nơi quyết định cách tham gia, tách hoặc tạo savepoint cho giao dịch theo khả năng transaction manager.

## 11. Ví dụ Java 17+ chạy độc lập: giữ connection cho Spring đến commit

Ví dụ dưới đây sử dụng **Spring JDBC 6.1.14 và H2 2.2.224**. `JdbcDataSource` của H2 được dùng để giữ dự án nhỏ; đó **không phải connection pool**. Mục tiêu là kiểm chứng một connection có thể do Spring transaction manager sở hữu, `PreparedStatement` được đóng ở phạm vi ngắn, và connection chỉ được Spring release sau transaction.

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>spring-resource-ownership-demo</artifactId>
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
```

Tạo `src/main/java/ResourceOwnershipDemo.java`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.transaction.support.TransactionTemplate;

public class ResourceOwnershipDemo {
    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:owner_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        DataSourceTransactionManager manager =
                new DataSourceTransactionManager(dataSource);
        TransactionTemplate transaction = new TransactionTemplate(manager);

        jdbc.execute(
                "CREATE TABLE ledger (id INT PRIMARY KEY, amount INT NOT NULL)");

        transaction.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO ledger(id, amount) VALUES (?, ?)",
                    1, 100);

            // getConnection tham gia transaction Spring đang hoạt động.
            Connection con = DataSourceUtils.getConnection(dataSource);
            try (PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO ledger(id, amount) VALUES (?, ?)")) {
                ps.setInt(1, 2);
                ps.setInt(2, 200);
                ps.executeUpdate();

                System.out.println("Bound to transaction: " +
                        DataSourceUtils.isConnectionTransactional(
                                con, dataSource));
            } catch (SQLException ex) {
                throw new IllegalStateException("JDBC operation failed", ex);
            } finally {
                // Không gọi con.close() trực tiếp:
                // transaction manager vẫn cần con để commit.
                DataSourceUtils.releaseConnection(con, dataSource);
            }
        });

        Integer afterCommit = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ledger", Integer.class);
        System.out.println("Rows after commit: " + afterCommit);

        try {
            transaction.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO ledger(id, amount) VALUES (?, ?)",
                        3, 300);
                throw new IllegalStateException("Business failure");
            });
        } catch (IllegalStateException expected) {
            System.out.println("Rollback triggered");
        }

        Integer afterRollback = jdbc.queryForObject(
                "SELECT COUNT(*) FROM ledger", Integer.class);
        System.out.println("Rows after rollback: " + afterRollback);
    }
}
```

Chạy khi đã cài **JDK 17+ và Maven**:

```bash
mvn -q compile exec:java -Dexec.mainClass=ResourceOwnershipDemo
```

Các dòng do `System.out.println` tạo ra:

```text
Bound to transaction: true
Rows after commit: 2
Rollback triggered
Rows after rollback: 2
```

Nếu môi trường build/logger in thông báo riêng, chúng không phải các dòng stdout ứng dụng được liệt kê ở trên.

**Phân tích từng bước:**

1. `TransactionTemplate` khởi tạo transaction bằng `DataSourceTransactionManager` và liên kết connection với ngữ cảnh thực thi phù hợp.
2. `JdbcTemplate` chạy `INSERT` đầu bằng connection tham gia transaction.
3. `DataSourceUtils.getConnection(dataSource)` lấy connection đang được transaction quản lý. Kết quả `isConnectionTransactional` là `true`.
4. `PreparedStatement` được tạo trong block con; `try-with-resources` đóng nó ngay khi hoàn tất. `DataSourceUtils.releaseConnection` không đóng connection đang bind trong transaction.
5. Callback transaction kết thúc bình thường, transaction manager commit; hai hàng cùng tồn tại.
6. Callback thứ hai thêm hàng thứ ba rồi ném `IllegalStateException`. `TransactionTemplate` rollback, nên số hàng sau rollback vẫn là 2.

Điều ví dụ chứng minh là **đúng ownership khi phối hợp JDBC thủ công với Spring**. Nó không chứng minh tự động có pool, cũng không có nghĩa các kết nối đến nhiều database đều tham gia một transaction.

## 12. Chẩn đoán sự cố do đóng nhầm hoặc quên đóng

Khi gặp “connection is closed”, timeout mượn connection hoặc lazy loading lỗi sau khi method kết thúc, hãy xác định **tài nguyên được tạo ở đâu, ai sở hữu, ai có trách nhiệm release và ranh giới transaction ở đâu** trước khi thay đổi timeout.

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| `Connection is closed` ở SQL thứ hai hoặc khi commit | Connection Spring đang bind bị code `close()` trực tiếp. | Tìm `try (Connection con = DataSourceUtils.getConnection(...))`, thay bằng `releaseConnection`. |
| SQL đã commit dù `@Transactional` ném lỗi | SQL chạy trên connection khác lấy trực tiếp từ DataSource gốc có auto-commit bật. | Chuyển sang `JdbcTemplate`/`DataSourceUtils`, xác minh transaction manager và DataSource. |
| `getConnection()` timeout, active không giảm | Connection do ứng dụng tự mượn nhưng thiếu `close()` ở đường lỗi. | Dùng `try-with-resources`/`finally` cho connection **do mình sở hữu**. |
| `ResultSet` không dùng được sau callback | Trả cursor còn sống ra ngoài phạm vi mà `JdbcTemplate` đã đóng. | Map dữ liệu thành DTO/list trong callback. |
| Stream JDBC/lazy JPA báo lỗi sau khi method return | Stream cần cursor hoặc persistence context đã hết transaction. | Tiêu thụ và đóng stream trong phạm vi transaction phù hợp. |
| DB transaction không rollback khi IOException/checked exception | `try-with-resources` đã đóng stream nhưng rollback rule mặc định không áp dụng cho checked exception. | Cấu hình `rollbackFor` phù hợp và bảo đảm exception đi qua interceptor. |
| Connection/persistence context bị đóng không đúng lúc | Code tự đóng bean, EntityManager được inject, hoặc Session transaction-bound. | Để Spring quản lý vòng đời container/transaction. |
| Một method có `@Transactional` nhưng connection không bind | Lời gọi bypass proxy, cấu hình transaction manager/DataSource khác, hoặc thread khác. | Xác minh đường đi interceptor, resource binding và propagation. |
| Lỗi cleanup che mất lỗi chính | `close()` cũng ném exception. | Kiểm tra `getSuppressed()` và log ngữ cảnh lỗi, không nuốt exception. |

Đối với Spring JDBC, có thể quan sát số connection đang mượn/rảnh trong pool, transaction duration và thông báo từ database. `DataSourceUtils.isConnectionTransactional(con, dataSource)` hữu ích như phép kiểm tra có ngữ cảnh trong code chẩn đoán, nhưng không nên dùng nó để viết logic nghiệp vụ phụ thuộc vào danh tính vật lý của connection.

## 13. Checklist quyết định trước khi viết `try (...)`

1. **Tài nguyên này từ đâu ra?** Do code gọi constructor/factory tạo mới, do pool cấp theo lượt mượn, hay do Spring inject/bind?
2. **Ai sở hữu lời gọi close?** API tài liệu nói caller phải đóng, hay framework sẽ tự release ở cuối callback/transaction/context?
3. **Tài nguyên còn được dùng sau khối try không?** Nếu còn, `try-with-resources` có thể đóng quá sớm.
4. **Có giao dịch Spring đang hoạt động không?** Raw `DataSource.getConnection()` có tham gia đúng transaction hay tạo một connection độc lập?
5. **Đang muốn đóng tài nguyên con hay cả tài nguyên cha?** Đóng `Statement`/`ResultSet` do mình tạo thường đúng; đóng transaction-bound `Connection` thường sai.
6. **Có stream/cursor lazy không?** Stream tự nó cần `close()` và cần được tiêu thụ trước khi connection/transaction kết thúc.
7. **Exception sẽ tác động tới transaction thế nào?** Phân biệt checked/unchecked, suppressed exception, bắt lỗi trong method, `rollbackFor` và trạng thái rollback-only.
8. **Nếu không có transaction, tài nguyên có được release không?** `DataSourceUtils.releaseConnection` vừa xử lý connection bound vừa xử lý trường hợp tự mượn ngoài transaction.

### Những điều cần nhớ

- `try-with-resources` giải quyết **đóng đối tượng `AutoCloseable` theo lexical scope**; nó không xác định resource ownership và không thay thế transaction manager.
- Với JDBC tự quản lý, `try (Connection con = dataSource.getConnection())` thường đúng **khi code thực sự sở hữu connection**. Với connection do `DataSourceUtils` lấy trong Spring, dùng **`DataSourceUtils.releaseConnection`**.
- Với `JdbcTemplate`, Spring quản lý connection; callback có thể dùng `try-with-resources` cho `PreparedStatement`/`ResultSet` do chính callback tạo.
- Với `@PersistenceContext EntityManager`, Spring quản lý persistence context; không tự đóng entity manager được inject dù API có `AutoCloseable`.
- Với `JdbcTemplate.queryForStream` hoặc các stream giữ cursor, đóng **stream** bằng `try-with-resources` và tiêu thụ nó trong phạm vi transaction thích hợp.
- **Commit/rollback**, **đóng handle** và **đóng bean/pool** là ba trách nhiệm khác nhau; chỉ một trong số đó không thể thay thế các trách nhiệm còn lại.

### Tài liệu tham khảo

- Java 17 — `try-with-resources` và exception suppression: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html
- Spring Framework — điều khiển JDBC connection: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring — `DataSourceUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring — `TransactionAwareDataSourceProxy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/TransactionAwareDataSourceProxy.html
- Spring — rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring — `JdbcTemplate.queryForStream`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Jakarta Persistence — `EntityManager`: https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html
