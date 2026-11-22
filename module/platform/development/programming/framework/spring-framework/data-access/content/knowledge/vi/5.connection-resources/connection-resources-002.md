# JdbcTemplate quản lý tạo và giải phóng tài nguyên theo hợp đồng

## 1. Mục tiêu học tập và phạm vi

Trong Spring Framework, `JdbcTemplate` là lớp trung tâm để dùng JDBC mà không phải viết lặp lại quy trình lấy `Connection`, tạo `Statement`, duyệt `ResultSet`, bắt `SQLException` và dọn tài nguyên sau mỗi thao tác. Tuy nhiên, “Spring tự đóng mọi thứ” là cách hiểu **quá rộng**: `JdbcTemplate` chỉ quản lý những tài nguyên theo **hợp đồng API** mà nó sở hữu. Những tài nguyên do callback tự tạo, `Stream` được trả về để caller tiêu thụ, và vòng đời connection trong transaction phải được xử lý đúng trách nhiệm.

Bài này giải thích chi tiết:
- `Connection`, `Statement`/`PreparedStatement`, `ResultSet` được tạo và giải phóng lúc nào.
- Đường đi của `JdbcTemplate` qua `DataSource`, `DataSourceUtils` và Spring transaction.
- Phân biệt **đóng logical connection**, **trả connection về pool**, **đóng physical connection**.
- Ai đóng tài nguyên đối với `RowMapper`, `ResultSetExtractor`, `RowCallbackHandler`, `PreparedStatementCallback` và `ConnectionCallback`.
- Trường hợp đặc biệt `queryForStream`: **caller phải đóng `Stream`**.
- Dọn tài nguyên khi SQL hoặc callback thất bại, exception translation và những lỗi leak thường gặp.
- Cách viết repository/service/test nhằm xác minh hợp đồng tài nguyên và tránh giữ connection quá lâu.

**Phạm vi:** JDBC kiểu blocking trong Spring Framework 6.x, Spring Boot 3.x và Java 17+. Khi nói tới `DataSourceTransactionManager`/`JdbcTransactionManager`, giả sử transaction manager và `JdbcTemplate` sử dụng cùng một `DataSource`. JPA/Hibernate và R2DBC có cơ chế tài nguyên riêng, không phải trọng tâm bài này.

## 2. Ba loại tài nguyên JDBC và vòng đời của chúng

Trong JDBC thuần, đường đi thường là:

```text
DataSource
    │ getConnection()
    ▼
Connection
    │ prepareStatement(sql)
    ▼
PreparedStatement / Statement
    │ executeQuery()
    ▼
ResultSet
    │ next(), getXxx()
    ▼
Đối tượng/DTO trong ứng dụng
```

**`Connection`** đại diện một phiên làm việc JDBC tới DB (thường là handle/proxy từ pool). Nó giữ trạng thái như auto-commit, isolation, cảnh báo SQL và có thể đang nằm trong một transaction.

**`Statement`/`PreparedStatement`** là tài nguyên thực thi SQL; `PreparedStatement` thường chứa tham số bind, timeout, fetch size và có thể tạo một hoặc nhiều `ResultSet` tùy API.

**`ResultSet`** đại diện tập hàng kết quả gắn với câu lệnh/connection còn hoạt động. Một `ResultSet` đang mở không phải là DTO bất biến; nó có vòng đời và thường cần JDBC driver/server resources.

Nếu tự viết JDBC, ứng dụng phải đóng các tài nguyên đã mở (thông thường theo thứ tự ngược: `ResultSet` → `Statement` → `Connection`), kể cả khi mapping ném lỗi. Java `try-with-resources` thực hiện điều đó với `AutoCloseable`.

**Với `JdbcTemplate`, trách nhiệm được tách:** application cung cấp SQL, tham số, mapping/logic; template thực hiện phần lớn quản lý JDBC. Nhưng vẫn cần hiểu tài nguyên nào do ai tạo, ai đang nắm quyền sở hữu và lúc nào caller nhận một kết quả còn “sống” như `Stream`.

## 3. Bảng hợp đồng ownership: ai tạo và ai giải phóng?

| Tài nguyên hoặc API | Bên thường tạo/lấy | Ai phải giải phóng? | Lưu ý |
|---|---|---|---|
| `Connection` của thao tác `JdbcTemplate.query/update` thông thường | `JdbcTemplate` lấy qua `DataSourceUtils` | `JdbcTemplate` gọi logic release; transaction/pool quyết định có đóng thật lúc đó hay không | Không gọi `connection.close()` từ `RowMapper` |
| `PreparedStatement` của `JdbcTemplate.query/update` thông thường | Template dựa trên SQL và callback chuẩn | Template | Không tự đóng statement template truyền cho callback |
| `ResultSet` do một `query(...)` chuẩn tạo, được truyền vào `RowMapper`/`ResultSetExtractor` | Template thực thi statement | Template | Đọc/mapping trong callback; không trả raw `ResultSet` ra ngoài |
| `Statement` được template cấp cho `StatementCallback` | Template | Template | Callback không đóng statement được cấp |
| `PreparedStatement` được template cấp cho `PreparedStatementCallback` | Template | Template | Callback phải đóng **ResultSet tự mở** bằng `executeQuery()` nếu có |
| `PreparedStatement` tự tạo trong `ConnectionCallback` | Callback | **Callback** | Dùng `try-with-resources` |
| `ResultSet` tự tạo trong `ConnectionCallback` | Callback | **Callback** | Đóng trong scope trước khi callback kết thúc |
| `Connection` được truyền vào `ConnectionCallback` | Template | Template/transaction manager | Callback không được đóng connection này |
| `Stream<T>` từ `JdbcTemplate.queryForStream` | Template trả ra cho caller | **Caller đóng stream** | Dùng `try (Stream<T> rows = ...)` |
| `Connection` tự lấy từ `DataSourceUtils.getConnection` | Application code thấp tầng | Application gọi `DataSourceUtils.releaseConnection` | Phải dùng **cùng `DataSource`**, không đóng connection giao dịch trực tiếp |

Trong các callback chuẩn, tài liệu Spring nhấn mạnh trường hợp **ResultSet do callback tự mở**: template thường đóng statement do nó tạo, nhưng không được suy luận việc đó sẽ luôn giải phóng ResultSet được callback mở riêng, nhất là khi statement/connection có cơ chế pooling. Hãy đóng ResultSet đó trong callback bằng `try-with-resources`.

**Quy tắc đơn giản: tài nguyên được API cấp cho bạn chỉ để dùng thì tuân thủ contract của API; tài nguyên bạn tự tạo thì bạn phải chịu trách nhiệm đóng, trừ khi contract chuyển quyền sở hữu cho bên khác.**

## 4. Chu trình thực thi cơ bản của JdbcTemplate

Với một `JdbcTemplate.query(sql, rowMapper, args)` thông thường, sơ đồ logic như sau:

```text
Repository gọi JdbcTemplate.query(...)
  1. DataSourceUtils.getConnection(dataSource)
         │
         ├─ Nếu đang có Spring JDBC transaction phù hợp:
         │    lấy connection đã gắn với transaction hiện tại
         └─ Nếu không: lấy connection từ DataSource/pool
  2. Tạo PreparedStatement
  3. Bind các tham số và thực thi SQL
  4. Nhận ResultSet, duyệt từng row
  5. Gọi RowMapper trên mỗi row để tạo Java object
  6. Đóng ResultSet và PreparedStatement do template quản lý
  7. DataSourceUtils.releaseConnection(connection, dataSource)
         │
         ├─ Connection thuộc transaction còn đang hoạt động:
         │    giữ cho transaction manager quản lý đến cuối transaction
         └─ Connection không thuộc transaction:
         │    đóng/release handle theo DataSource/pool
  8. Trả List/DTO hoặc ném exception thích hợp
```

Đây là **mô hình logic**. Thứ tự/số lời gọi thấp tầng chính xác có thể thay đổi theo overload, driver, phiên bản Spring và kỹ thuật thực thi; điều bắt buộc cần nhớ là template bố trí cleanup đúng hợp đồng, kể cả khi phần việc trung gian ném lỗi.

### Không phải “mỗi câu SQL tạo một kết nối vật lý mới”

`DataSource` thực tế trong ứng dụng server thường dùng connection pool, ví dụ HikariCP. Khi ứng dụng yêu cầu connection, pool có thể cấp một **logical handle** tới kết nối vật lý đã tồn tại. Khi code gọi `close()` trên handle bên ngoài transaction, pool thường trả connection vào danh sách sẵn sàng sử dụng, **không** thiết lập/kết thúc một kết nối TCP/DB vật lý trong mỗi request. Một pool có thể đóng physical connection khi bị loại, hết vòng đời hoặc shutdown.

Do đó:
- “`JdbcTemplate` release connection” là **release đúng lifecycle**.
- “Mọi lần truy vấn tạo và đóng TCP session” là **sai trong trường hợp pooled DataSource**.
- “Có pool nên không cần release connection” cũng **sai**: quên release làm pool cạn handle, request khác phải chờ và cuối cùng timeout.

## 5. Bài toán mẫu có thể triển khai trong Spring Boot

Giả sử có bảng đơn hàng và nhật ký, với PostgreSQL:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(64) NOT NULL UNIQUE,
    status VARCHAR(16) NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0)
);

CREATE TABLE order_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    event VARCHAR(32) NOT NULL
);
```

Dependency Gradle điển hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

`application.properties` dùng biến môi trường thay cho việc hardcode mật khẩu:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/orders_db
spring.datasource.username=orders_app
spring.datasource.password=your-local-secret
```

Cấu hình trên chỉ là **mẫu local**, cần có DB, user, migration phù hợp và secret được cung cấp an toàn trong môi trường chạy. Spring Boot thường cấu hình `DataSource`, connection pool, `JdbcTemplate` và transaction manager tương ứng khi dependency/điều kiện auto-configuration phù hợp. Không cần tự `new JdbcTemplate()` cho từng request.

DTO immutable:

```java
// OrderRow.java
package example.jdbc;

public record OrderRow(
    long id,
    String code,
    String status,
    long amountCents
) {}
```

Repository:

```java
// OrderJdbcRepository.java
package example.jdbc;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {

    private static final RowMapper<OrderRow> ORDER_MAPPER = (rs, rowNum) ->
        new OrderRow(
            rs.getLong("id"),
            rs.getString("order_code"),
            rs.getString("status"),
            rs.getLong("amount_cents")
        );

    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderRow> findByStatus(String status) {
        return jdbc.query("""
                SELECT id, order_code, status, amount_cents
                FROM orders
                WHERE status = ?
                ORDER BY id
                """, ORDER_MAPPER, status);
    }

    public Optional<OrderRow> findByCode(String code) {
        List<OrderRow> matches = jdbc.query("""
                SELECT id, order_code, status, amount_cents
                FROM orders
                WHERE order_code = ?
                """, ORDER_MAPPER, code);

        if (matches.size() > 1) {
            throw new IllegalStateException(
                "Order code must be unique");
        }
        return matches.stream().findFirst();
    }

    public int markPaid(long id) {
        return jdbc.update("""
                UPDATE orders
                SET status = 'PAID'
                WHERE id = ? AND status = 'NEW'
                """, id);
    }

    public void addAudit(long orderId, String event) {
        jdbc.update("""
                INSERT INTO order_audit (order_id, event)
                VALUES (?, ?)
                """, orderId, event);
    }
}
```

**Điểm cần quan sát:** repository chỉ quản lý dữ liệu và contract kết quả; **không thấy `Connection`, `PreparedStatement` hay `ResultSet` ở code gọi**. `ORDER_MAPPER` được template gọi khi ResultSet còn hợp lệ. Sau khi `query()` trả về, `List<OrderRow>` chứa Java record tách khỏi tài nguyên JDBC; caller có thể sử dụng nó mà không giữ cursor hay connection.

`Optional` là lựa chọn 0..1; SQL có unique constraint nên một mã đơn không được trả nhiều hàng. Việc xử lý `matches.size()>1` trong ví dụ làm rõ invariant; trong ứng dụng thực, API `JdbcClient.optional()` của Spring Framework 6.1+ cũng có thể biểu đạt 0..1 trực tiếp, nhưng vẫn phải có unique constraint ở database. `query()` dùng JDBC blocking; không liên quan đến async/reactive.

### Connection được lấy ở đâu?

Lệnh `findByStatus()` thực hiện toàn bộ query dưới quyền điều phối của `JdbcTemplate`. Khi query hoàn tất, statement/resultset được cleanup, connection được release theo context. Application **không cần `finally { conn.close(); }`** quanh `jdbc.query()`.

Tạo một `JdbcTemplate` dùng chung với `DataSource` có cấu hình ổn định là bình thường. Sau khi đã cấu hình, template được thiết kế dùng đồng thời bởi nhiều repository/caller; tránh thay đổi mutable settings của cùng template trong lúc nhiều thread đang sử dụng.

## 6. Không có @Transactional: tài nguyên của mỗi thao tác

Giả sử service gọi hai lệnh, nhưng **không** khai báo transaction Spring bao quanh:

```java
public void payWithoutTransaction(long id) {
    int updated = repository.markPaid(id);
    if (updated != 1) {
        throw new IllegalStateException("Order not NEW");
    }
    repository.addAudit(id, "PAID");
}
```

Đây là **method minh họa trong service có field `repository`**, không phải chương trình độc lập.

Trường hợp thông dụng:
1. `markPaid()` lấy connection, chạy `UPDATE`, dọn statement và release connection; nếu cấu hình connection tự commit, lệnh đã commit.
2. `addAudit()` lấy một connection handle cho `INSERT`, xử lý rồi release.
3. Nếu insert audit lỗi, update trước có thể đã commit: **dọn resource đúng không đồng nghĩa các lệnh được commit nguyên tử**.

Hai lệnh có thể tình cờ dùng cùng physical connection do pool cấp lại, nhưng **không tạo thành một transaction chỉ vì cùng pool hoặc cùng `JdbcTemplate`**. Transaction là một chính sách riêng do transaction manager và ranh giới nghiệp vụ điều phối.

## 7. Có @Transactional: vì sao connection không release ngay sau mỗi câu SQL?

Khi Spring transaction được kích hoạt qua proxy, với `DataSourceTransactionManager` hoặc `JdbcTransactionManager` trỏ đúng `DataSource`, transaction manager lấy/buộc một JDBC connection cho transaction hiện tại. `JdbcTemplate` dùng `DataSourceUtils` nên các lời gọi cùng transaction thường dùng chính connection đó.

```text
Service.payOrder()       @Transactional bắt đầu
  |
  | Spring transaction manager
  |   └── lấy/bind Connection C vào thread hiện tại
  |
  ├── repository.markPaid(id)
  |      JdbcTemplate → DataSourceUtils → Connection C
  |      tạo Statement A → UPDATE → đóng Statement A
  |      release(C) → nhận biết C thuộc transaction, chưa trả pool
  |
  ├── repository.addAudit(id, "PAID")
  |      JdbcTemplate → DataSourceUtils → Connection C
  |      tạo Statement B → INSERT → đóng Statement B
  |      release(C) → C vẫn thuộc transaction
  |
  └── service trả thành công / ném exception
         |
         ├── commit (nếu hợp lệ)
         └── rollback (theo rollback policy)
                |
                └── unbind/cleanup C, trả connection về DataSource/pool
```

Ví dụ service hoàn chỉnh trong bối cảnh dự án Spring:

```java
// OrderPaymentService.java
package example.jdbc;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {
    private final OrderJdbcRepository repository;

    public OrderPaymentService(OrderJdbcRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void pay(long orderId) {
        int updated = repository.markPaid(orderId);
        if (updated != 1) {
            throw new IllegalStateException("Order not NEW");
        }
        repository.addAudit(orderId, "PAID");
    }
}
```

Ở đây:
- Nếu update thành công và audit insert thành công, transaction được commit.
- Nếu insert audit gây `DataAccessException` (unchecked), mặc định Spring rollback transaction.
- Nếu application ném `IllegalStateException` như ví dụ, mặc định cũng rollback.
- Nếu dùng **checked exception**, cấu hình rollback phải được quyết định rõ (ví dụ `@Transactional(rollbackFor = SomeCheckedException.class)` khi có yêu cầu).
- `@Transactional` trên một method thường chỉ có tác dụng khi lời gọi đi qua Spring proxy; **self-invocation** trong cùng object không kích hoạt proxy transaction mới theo mặc định.
- Logic transaction imperative dựa vào context gắn với thread thực thi; không mặc nhiên truyền transaction qua `@Async`/thread khác.

Một transaction đang chờ API mạng, message broker hay xử lý kéo dài có thể **giữ connection lâu**, dù `JdbcTemplate` đã đóng từng statement. Đó có thể là nguyên nhân pool cạn; phải rút ngắn transaction và không dùng transaction như “vỏ” bao toàn bộ công việc chậm.

### Connection cleanup không giống commit/rollback

`JdbcTemplate` chịu trách nhiệm lifecycle JDBC statement/resultset và gọi release connection đúng quy tắc. **Transaction manager** chịu trách nhiệm ranh giới commit/rollback và release connection khi transaction kết thúc. Đừng gọi `con.commit()`, `con.rollback()` hay `con.close()` trực tiếp trong `RowMapper`/callback đang tham gia Spring transaction: làm vậy phá vỡ ownership và consistency.

## 8. Callback tiêu chuẩn: trách nhiệm của template và application

`JdbcTemplate` nhận callback cho SQL/mapping, nhưng không phải tất cả callback có cùng ownership. Xét một số trường hợp phổ biến.

### 8.1. RowMapper<T>

`RowMapper` được gọi cho từng hàng của ResultSet do `JdbcTemplate` tạo. Input gồm `ResultSet` hiện hành và số thứ tự hàng. Callback:
- Đọc cột cần thiết, tạo Java object/record.
- Không `close()` `ResultSet`, `Statement` hay `Connection` nhận được gián tiếp.
- Không giữ tham chiếu `ResultSet` để xử lý sau khi `query()` trả về.
- Nếu mapping thất bại, để lỗi đi lên; template vẫn thực hiện cleanup cần thiết.

**Ví dụ tốt:** `ORDER_MAPPER` ở phần 5 trả `OrderRow` immutable. **Ví dụ sai:** return object chứa field `ResultSet`, rồi đợi tầng HTTP đọc dữ liệu; tại thời điểm đó ResultSet đã hết vòng đời.

### 8.2. ResultSetExtractor<T>

`ResultSetExtractor` nhận cả `ResultSet` của một query để ánh xạ cấu trúc phức tạp; ví dụ gom nhiều hàng thành aggregate. Template quản lý ResultSet này, callback không đóng nó. Hãy xử lý hết dữ liệu cần dùng **trong lúc callback đang chạy**.

```java
// Method minh họa trong OrderJdbcRepository.
public long sumPaidAmounts() {
    return jdbc.query("""
            SELECT amount_cents
            FROM orders
            WHERE status = ?
            """, rs -> {
                long total = 0;
                while (rs.next()) {
                    total = Math.addExact(
                        total, rs.getLong("amount_cents"));
                }
                return total;
            }, "PAID");
}
```

Đây là mapping toàn tập kết quả sang một giá trị; `Math.addExact` báo lỗi nếu overflow `long`. Với dữ liệu lớn, SQL `SUM` tại DB có thể hiệu quả hơn; ví dụ chỉ để thấy callback **được phép duyệt** ResultSet và template **sở hữu** ResultSet. Không dùng `return rs;`.

### 8.3. RowCallbackHandler

`RowCallbackHandler` cũng do template gọi trong quá trình duyệt, hữu ích để tiêu thụ từng hàng, chẳng hạn tạo checksum hoặc đưa vào bộ xử lý có kiểm soát. Không tự gọi `rs.next()` trong callback này: template đã điều khiển việc di chuyển con trỏ tới hàng hiện tại theo contract của `RowCallbackHandler`.

```java
// Method minh họa trong repository, với JdbcTemplate jdbc.
public void visitOrderCodes(
        java.util.function.Consumer<String> visitor) {
    jdbc.query("""
            SELECT order_code
            FROM orders
            ORDER BY id
            """, (org.springframework.jdbc.core.RowCallbackHandler) rs ->
                visitor.accept(rs.getString("order_code")));
}
```

`visitor` phải xử lý dữ liệu đồng bộ trong callback và không giữ `ResultSet`. Cần giới hạn query khi bảng rất lớn, hoặc cân nhắc batch/streaming với cơ chế đo và kiểm soát. `RowCallbackHandler` giúp tránh tự tạo một `List` chứa toàn bộ row, nhưng **không biến JDBC thành non-blocking**.

### 8.4. PreparedStatementCreator / PreparedStatementSetter

`PreparedStatementCreator` nhận connection và **trả về `PreparedStatement` do nó tạo** để `JdbcTemplate` thực thi. Với statement được trả về đúng contract, template chịu trách nhiệm đóng sau khi dùng. `PreparedStatementSetter` chỉ bind tham số vào statement mà template cấp; callback **không** được đóng statement đó. Nếu callback tạo thêm stream, file, resultset/statement phụ trợ ngoài API chính, callback phải dọn tài nguyên nó sở hữu.

Không cần dùng callback thấp tầng khi `jdbc.query(sql, mapper, args)` hoặc `jdbc.update(sql, args)` đủ rõ. Dùng API đơn giản thường giảm khả năng phá hợp đồng resource.

## 9. ConnectionCallback: được cấp Connection, tự quản lý Statement mình tạo

Với `ConnectionCallback<T>`, `JdbcTemplate.execute(...)` đưa connection cho callback để chạy công việc JDBC tùy biến. **`JdbcTemplate` vẫn sở hữu connection**, nhưng những statement/resultset callback tự mở phải được callback đóng.

Ví dụ:

```java
// JdbcLowLevelCounter.java
package example.jdbc;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcLowLevelCounter {
    private final JdbcTemplate jdbc;

    public JdbcLowLevelCounter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long count(String status) {
        return jdbc.execute((ConnectionCallback<Long>) connection -> {
            try (PreparedStatement statement =
                     connection.prepareStatement("""
                         SELECT COUNT(*) FROM orders WHERE status = ?
                         """)) {
                statement.setString(1, status);
                try (ResultSet rows = statement.executeQuery()) {
                    rows.next(); // COUNT(*) không GROUP BY trả một hàng
                    return rows.getLong(1);
                }
            }
        });
    }
}
```

Phân tích ownership:
- **Không** `try (Connection con = connection)`, **không** `connection.close()` trong callback. Connection được template cấp và được transaction manager giữ nếu đang trong transaction.
- `PreparedStatement` được callback **tự gọi** `connection.prepareStatement(...)` nên callback đóng bằng try-with-resources.
- `ResultSet` được callback **tự gọi** `statement.executeQuery()` nên callback đóng trước khi thoát callback.
- Nếu SQL ném `SQLException`, try-with-resources vẫn cleanup statement/resultset đã được mở; `JdbcTemplate` tiếp nhận SQLException và dịch sang hệ lỗi Spring.
- Nếu `rows.getLong(1)` hay mapping ném `RuntimeException`, cleanup vẫn xảy ra, ngoại lệ application được truyền lên, không tự biến thành `DataAccessException` chỉ vì ở trong template.

Không gọi `connection.setAutoCommit(false)`, `commit`, `rollback` tùy tiện trong callback đang nằm trong Spring transaction. Khi thật sự cần transaction, đặt `@Transactional` ở service hoặc dùng `TransactionTemplate`/transaction manager phù hợp.

### 9.1. PreparedStatementCallback cũng có ngoại lệ ownership của ResultSet

Có thể cho `JdbcTemplate` tạo statement, rồi callback trực tiếp thực thi. Lúc này:
- Template **đóng `PreparedStatement` mà nó cung cấp**.
- Callback phải đóng `ResultSet` do chính `executeQuery()` mở.

```java
// Method minh họa trong repository có field JdbcTemplate jdbc.
public long countWithPreparedStatementCallback(String status) {
    return jdbc.execute("""
            SELECT COUNT(*) FROM orders WHERE status = ?
            """, (org.springframework.jdbc.core.PreparedStatementCallback<Long>) ps -> {
        ps.setString(1, status);
        try (java.sql.ResultSet rs = ps.executeQuery()) {
            rs.next();
            return rs.getLong(1);
        }
    });
}
```

Đây là lý do câu “`JdbcTemplate` sẽ tự đóng tất cả ResultSet do callback mở” không chính xác. Tài liệu callback của Spring lưu ý rõ ResultSet do callback mở **nên được đóng trong chính callback**, vì đóng statement có thể chỉ trả statement về pool, không nhất thiết dọn tài nguyên ResultSet theo cách mong đợi.

## 10. queryForStream: caller nhận một resource chưa hoàn tất vòng đời

`JdbcTemplate.queryForStream(...)` (Spring Framework 5.3+) là trường hợp khác với `query(...)` trả `List`:
- Nó trả `java.util.stream.Stream<T>`.
- Stream có thể đọc row trong khi statement/resultset/connection vẫn cần mở.
- **Caller phải đóng Stream**, tốt nhất bằng `try-with-resources`.
- “Đã gọi `forEach` hoặc `toList`” **không có nghĩa Stream tự được đóng**; terminal operation không thay cho `close()`.

```java
// OrderStreamReader.java
package example.jdbc;

import java.util.stream.Stream;
import java.util.function.Consumer;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStreamReader {
    private static final RowMapper<OrderRow> MAPPER =
        (rs, rowNum) -> new OrderRow(
            rs.getLong("id"),
            rs.getString("order_code"),
            rs.getString("status"),
            rs.getLong("amount_cents"));

    private final JdbcTemplate jdbc;

    public OrderStreamReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void visitRecentOrders(
            String status, int maxRows,
            Consumer<OrderRow> consumer) {
        if (maxRows < 1 || maxRows > 5000) {
            throw new IllegalArgumentException("maxRows out of range");
        }

        try (Stream<OrderRow> rows = jdbc.queryForStream("""
                SELECT id, order_code, status, amount_cents
                FROM orders
                WHERE status = ?
                ORDER BY id
                LIMIT ?
                """, MAPPER, status, maxRows)) {
            rows.forEach(consumer);
        }
    }
}
```

Tại khi thoát `try`, `rows.close()` được gọi ngay cả khi `consumer.accept(...)` ném lỗi. `queryForStream` bảo đảm cơ chế đóng tài nguyên khi **stream được đóng**. Không viết:

```java
// SAI: trả Stream từ DAO mà không đặt trách nhiệm đóng rõ ràng.
public java.util.stream.Stream<OrderRow> leakProne() {
    return jdbc.queryForStream(
        "SELECT id, order_code, status, amount_cents FROM orders",
        MAPPER);
}
```

Đoạn sai là **minh họa method ở class có field `jdbc` và `MAPPER`**, không phải code độc lập. Việc trả stream có thể hợp lệ nếu API explicitly chuyển quyền sở hữu và caller chắc chắn đóng nó, nhưng thiết kế dễ bị quên nhất là “trả Stream qua nhiều tầng rồi không ai đóng”.

**Cũng không nên mở stream trong method `@Transactional` rồi trả stream ra ngoài** và tưởng transaction vẫn sống: khi method trả, proxy transaction có thể kết thúc, làm việc tiêu thụ stream sau đó thất bại hoặc vi phạm ranh giới. Cần consume stream *bên trong* scope transaction hoặc dùng API/cơ chế xử lý dữ liệu khác.

### Streaming không tự bảo đảm memory thấp trong mọi database

Mức độ stream thực tế phụ thuộc JDBC driver, fetch size, autocommit, câu SQL và database. Ví dụ PostgreSQL JDBC thường cần fetch size dương và giao dịch phù hợp để đọc theo cursor thay vì tải toàn bộ dữ liệu ngay. `queryForStream` không thay thế giới hạn `LIMIT`/pagination, cũng không tạo một reactive `Flux`. Luôn đo heap, connection hold time và server cursor trên môi trường thật.

## 11. Nếu thật sự dùng JDBC thuần: try-with-resources và DataSourceUtils

Đôi khi một thư viện yêu cầu raw `Connection`. Có hai trường hợp **không nên lẫn lộn**.

### 11.1. JDBC thuần khi bạn thực sự tự sở hữu Connection

```java
// Phương thức JDBC thuần; caller cấp DataSource và xử lý SQLException.
public long countRaw(
        javax.sql.DataSource dataSource, String status)
        throws java.sql.SQLException {

    try (java.sql.Connection con = dataSource.getConnection();
         java.sql.PreparedStatement ps = con.prepareStatement(
             "SELECT COUNT(*) FROM orders WHERE status = ?")) {
        ps.setString(1, status);
        try (java.sql.ResultSet rs = ps.executeQuery()) {
            rs.next();
            return rs.getLong(1);
        }
    }
}
```

Ở đây code **tự lấy connection** nên nó phải đóng. Nhưng lấy trực tiếp bằng `dataSource.getConnection()` trên một DataSource thông thường **không nhất thiết tham gia Spring thread-bound transaction**. Đừng copy method này vào một service có `@Transactional` rồi mặc định nó dùng cùng connection với `JdbcTemplate`.

### 11.2. JDBC thấp tầng có ý thức transaction của Spring

Nếu không thể dùng `JdbcTemplate` vì một API đặc biệt, `DataSourceUtils` là đường thấp tầng:

```java
// Method minh họa; có field javax.sql.DataSource dataSource.
public long countSpringAware(String status)
        throws java.sql.SQLException {

    java.sql.Connection con =
        org.springframework.jdbc.datasource.DataSourceUtils
            .getConnection(dataSource);
    try {
        try (java.sql.PreparedStatement ps = con.prepareStatement(
                "SELECT COUNT(*) FROM orders WHERE status = ?")) {
            ps.setString(1, status);
            try (java.sql.ResultSet rs = ps.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        }
    } finally {
        org.springframework.jdbc.datasource.DataSourceUtils
            .releaseConnection(con, dataSource);
    }
}
```

Phải dùng cùng đối tượng `DataSource` khi get/release. `DataSourceUtils.releaseConnection` **không đóng ngay connection đang được transaction manager gắn với thread**, nhưng release handle ngoài transaction theo chính sách datasource. Code trên vẫn tự quản lý statement/resultset và tự quyết định cách dịch `SQLException`; vì vậy chỉ dùng khi có lý do thực sự. Với công việc SQL thông thường, `JdbcTemplate` gọn và ít rủi ro hơn.

Spring có `TransactionAwareDataSourceProxy` dành cho tích hợp legacy code chỉ biết gọi `getConnection()/close()` theo chuẩn `DataSource`. Đây là phương án tích hợp tương thích, không cần dùng cho repository mới viết bằng `JdbcTemplate`.

## 12. Khi xảy ra lỗi, JdbcTemplate vẫn phải cleanup

Giả sử một `RowMapper` lỗi ở hàng thứ 13 vì định dạng cột không như mong đợi. Nếu template không dọn tài nguyên trong nhánh ngoại lệ thì:
1. `ResultSet` còn mở.
2. `Statement` còn mở/được pool giữ.
3. `Connection` không được trả đúng hạn.
4. Sau nhiều request lỗi, pool cạn dù cả query thành công trước đó đều release đúng.

`JdbcTemplate` tổ chức các nhánh cleanup để xử lý cả **thành công lẫn thất bại**. Nó cũng dùng `SQLExceptionTranslator` chuyển `SQLException` của JDBC sang hệ `DataAccessException` của Spring: ví dụ sai cú pháp SQL, lỗi constraint, sự cố truy cập resource. Loại cụ thể phụ thuộc driver/translator; không hứa một subtype giống nhau trên mọi database.

```text
Chạy query
   |
   ├─ thành công ──► map rows ──► cleanup ──► return
   |
   ├─ SQLException ─────────────► cleanup ──► DataAccessException
   |
   └─ RuntimeException từ app ──► cleanup ──► propagate exception
```

**Lưu ý:** RuntimeException do callback của ứng dụng ném không tự động trở thành SQL error; nó thường được truyền lên cho caller. Nếu method ở trong `@Transactional`, rollback còn phụ thuộc loại exception và cấu hình rollback policy, không phụ thuộc vào việc statement có bị đóng hay không.

### Vì sao không nuốt lỗi để “trả connection sớm”?

Đoạn sau là anti-pattern:

```java
// SAI: nuốt mọi lỗi và trả danh sách rỗng.
try {
    return jdbc.query(sql, mapper);
} catch (RuntimeException ex) {
    return java.util.List.of();
}
```

Đây là snippet **không độc lập** với `jdbc`/`sql`/`mapper` ở phạm vi hiện hành. `JdbcTemplate` vốn đã cleanup trong nhánh lỗi; nuốt exception không làm cleanup tốt hơn. Nó chỉ làm client tưởng không có dữ liệu và che mất lỗi SQL/connection.

Nên chỉ bắt lỗi cụ thể khi hợp đồng nghiệp vụ cần, dùng `DataAccessException`/subtype phù hợp và để exception translation hoạt động; log ở boundary được kiểm soát, tránh lặp log tại mọi tầng.

## 13. Nguyên tắc transaction và “giữ connection lâu”

Một request có `@Transactional` đôi khi query chỉ mất 5 ms, nhưng transaction giữ connection 3 giây vì sau đó gọi API bên ngoài. Cơ sở dữ liệu/connection pool vẫn phải dành nguồn lực cho transaction này. Khi nhiều request tương tự, pool chờ và timeout.

Ví dụ thiết kế kém:

```java
@Transactional
public void process(long id) {
    repository.markPaid(id);
    slowRemoteGateway.notifyPayment(id); // I/O mạng có thể rất chậm
    repository.addAudit(id, "PAID");
}
```

Đây là **đoạn phác họa service** với các dependency đã inject, không phải file Java độc lập. Dù `JdbcTemplate` đóng từng statement, transaction vẫn còn và connection có thể bị giữ trong lúc chờ mạng.

Một cách thiết kế phù hợp thường là:
- Hoàn tất phần thay đổi DB trong transaction ngắn.
- Không gọi API mạng dài trong transaction nếu có thể tránh.
- Nếu cần giao sự kiện sau commit và không được mất sự kiện, cân nhắc **transactional outbox** và consumer riêng.
- Tránh dùng `REQUIRES_NEW` vô tội vạ khi pool ít connection; propagation lồng nhau có thể cần thêm connection và gây pool exhaustion.
- Có timeout cho transaction và query, nhưng không coi timeout là cơ chế tự động thay thế cleanup, giới hạn đồng thời hay tuning pool.

**Dọn statement sớm và trả connection về pool là hai mốc khác nhau**. Hiểu chúng giúp tìm đúng nguyên nhân của connection pool starvation.

## 14. Một ví dụ Java 17 thuần về dọn tài nguyên khi lỗi

Đoạn dưới đây không dùng Spring/JDBC. Nó mô phỏng **nguyên lý ownership và thứ tự try-with-resources** để người học chạy ngay, không phụ thuộc database. Nó **không phải kiểm thử implementation JdbcTemplate**.

Tên file: `CloseOrderDemo.java`.

```java
public class CloseOrderDemo {

    static final class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Tracked connection = new Tracked("Connection");
             Tracked statement = new Tracked("Statement");
             Tracked rows = new Tracked("ResultSet")) {

            System.out.println("read rows");
            throw new IllegalStateException("mapping failed");

        } catch (IllegalStateException ex) {
            System.out.println("caught " + ex.getMessage());
        }
    }
}
```

Chạy:

```bash
javac CloseOrderDemo.java
java CloseOrderDemo
```

Stdout chính xác:

```text
read rows
close ResultSet
close Statement
close Connection
caught mapping failed
```

Điểm cần nhớ: tài nguyên `AutoCloseable` đã mở trước lỗi vẫn được đóng theo thứ tự ngược. `JdbcTemplate` sử dụng cơ chế cleanup thích hợp và ranh giới transaction/pool, còn `queryForStream` chuyển một phần trách nhiệm đóng sang caller. Không áp dụng dòng “close Connection” của demo một cách máy móc bên trong callback của template.

## 15. Các nguyên nhân khiến pool cạn dù dùng JdbcTemplate

`JdbcTemplate` giảm rủi ro rò rỉ JDBC resource, **không giải quyết mọi vấn đề về sức chứa pool**.

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
|---|---|---|
| Active connections tăng và lâu giảm | Transaction dài, query chậm, lock wait | Transaction duration, slow SQL, lock metrics |
| Pool pending threads tăng | Số request đồng thời vượt pool hoặc DB đang nghẽn | Pool size, concurrency, p95/p99, DB capacity |
| Sau nhiều thao tác stream, pool cạn | `queryForStream` không được close | Bọc mọi stream trong try-with-resources |
| Chỉ khi callback thấp tầng lỗi | Callback tạo `ResultSet`/`Statement` riêng mà quên đóng | Ownership theo API callback; test đường lỗi |
| Lỗi xuất hiện khi gọi dịch vụ mạng | Giữ transaction trong lúc chờ network | Tách transaction DB và side effect bên ngoài |
| Timeout sau nhiều lần batch | Batch quá lớn hoặc ResultSet/materialization lớn | Fetch size, chunk size, SQL plan, batch strategy |
| Cùng service có hai DataSource | Transaction manager không quản đúng DataSource mà template dùng | Wiring bean/qualifier và transaction manager |
| Sau lỗi DB, connection “bẩn” | Ứng dụng tự sửa autoCommit/isolation mà không reset; driver/pool lỗi | Tránh tự thao tác state dưới transaction; pool health |
| Thấy nhiều physical DB connections | Pool cấu hình/đếm nhiều instance, không phải template “leak” mặc định | Active/idle/max per instance, tổng instance |

Cần phân biệt:
- **Leaked resource:** caller không đóng tài nguyên mình sở hữu, dẫn đến handle giữ quá lâu.
- **Long-held connection:** transaction/query hợp lệ nhưng chạy rất lâu; không nhất thiết là leak.
- **Pool exhaustion:** nhu cầu vượt supply trong thời gian nào đó; có thể do truy vấn chậm, lock, thiếu pool hoặc leak.
- **Physical connection churn:** DB/TCP sessions được tạo/hủy liên tục, thường liên quan cấu hình pool, mạng hoặc DB, không được kết luận chỉ từ số lần gọi `JdbcTemplate.query`.

## 16. Cấu hình và quan sát tài nguyên trong Spring Boot

Spring Boot JDBC starter thường tích hợp pool như HikariCP khi trên classpath và auto-configuration phù hợp. Ví dụ cấu hình tối thiểu có thể điều chỉnh sau khi đo:

```properties
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=30000
```

`maximum-pool-size` giới hạn số connection do pool quản lý; `connection-timeout` là thời gian chờ lấy connection từ pool (đơn vị millisecond trong cấu hình HikariCP). Các số trên chỉ là minh họa, **không phải khuyến nghị mặc định cho mọi production system**. Tăng pool bừa bãi có thể đẩy bottleneck sang DB, tăng số transaction/lock và giảm hiệu quả.

Quan sát:
- Pool active/idle/pending và thời gian chờ cấp connection.
- Thời gian transaction, query latency p50/p95/p99.
- Số request đồng thời, tỉ lệ timeout và lỗi `CannotGetJdbcConnectionException`/connection failure.
- DB sessions, slow queries, lock wait, CPU/I/O.
- Đường code dùng `queryForStream` hoặc `ConnectionCallback` và đường lỗi hiếm gặp.

Với Spring Boot Actuator/Micrometer được cấu hình đúng, có thể lấy metric pool; tên/số liệu cụ thể phụ thuộc registry, phiên bản và bean được instrument. Tính năng leak detection của HikariCP có thể hỗ trợ điều tra, nhưng giữ connection lâu có thể tạo cảnh báo giả; nên dùng có chủ đích, không coi đó là test chứng minh tuyệt đối có leak.

**Không chỉ nhìn Java heap:** một JDBC connection/statement/resultset có thể giữ tài nguyên từ driver, socket, server cursor và DB; heap ít không đồng nghĩa mọi connection đã trả về pool.

## 17. Kiểm thử để chứng minh đúng hợp đồng

### 17.1. Kiểm thử hành vi repository

Với PostgreSQL thật qua Testcontainers hoặc database tích hợp tương đương, chuẩn bị fixture và xác minh:
1. `findByStatus("NEW")` trả DTO đúng.
2. `findByStatus("MISSING")` trả list rỗng, không trả `null`.
3. `markPaid(id)` trả số row cập nhật như kỳ vọng.
4. Khi SQL lỗi hoặc mapping lỗi, application nhận đúng lỗi thay vì im lặng trả rỗng.
5. Với cùng dữ liệu, gọi lại nhiều lần không tích lũy connection active ngoài dự kiến.

Ví dụ JUnit 5 với Spring Boot JDBC test slice (cần entity/schema/fixture được chuẩn bị, ví dụ qua `schema.sql` hoặc migration):

```java
// OrderJdbcRepositoryTest.java
package example.jdbc;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
@Import(OrderJdbcRepository.class)
class OrderJdbcRepositoryTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired OrderJdbcRepository repository;

    @Test
    void queryReturnsMappedRows() {
        jdbc.update("""
            INSERT INTO orders (order_code, status, amount_cents)
            VALUES (?, ?, ?)
            """, "TEST-1", "NEW", 1500L);

        var rows = repository.findByStatus("NEW");
        assertThat(rows)
            .anySatisfy(row -> {
                assertThat(row.code()).isEqualTo("TEST-1");
                assertThat(row.amountCents()).isEqualTo(1500L);
            });
    }
}
```

Test này **chỉ biên dịch/chạy trong project Spring Boot có JUnit 5, AssertJ, Spring Boot test starter và schema được tạo**; không chạy được bằng `javac` độc lập. Spring JDBC test slice thường tạo transaction và rollback cho test; vì thế không dùng test này một mình để khẳng định “connection đã trở lại pool ngay sau query”. Muốn đo release ngoài transaction, cần thiết kế test instrumentation riêng và tránh proxy/transaction của test che kết quả.

### 17.2. Kiểm thử transaction và rollback

Trong test tích hợp, chuẩn bị một ID hợp lệ, gọi `pay(id)`; xác minh cả `orders.status` lẫn `order_audit` sau commit. Sau đó tạo lỗi insert audit có kiểm soát và xác minh:
- Update đơn hàng bị rollback cùng audit.
- Exception vẫn được truyền lên theo contract.
- Sau transaction kết thúc, connection không bị giữ vô hạn.
- Không có hành vi tự `commit/close` từ callback.

Không chỉ dựa vào mock repository để khẳng định đã rollback: mock không tạo JDBC transaction thật. Dùng DB phù hợp để xác minh.

### 17.3. Kiểm thử nhánh lỗi và stream

- Gây `SQLException` có chủ đích (truy vấn sai cột ở môi trường test) rồi thực hiện truy vấn hợp lệ khác trên pool nhỏ: thao tác lỗi không được khiến tài nguyên giữ mãi.
- Tạo `RowMapper` ném `IllegalStateException` ở một hàng, kiểm tra exception propagate và pool không tích lũy handle.
- Dùng `queryForStream` trong try-with-resources, cho consumer ném lỗi giữa chừng: sau khi block thoát, stream vẫn bị đóng.
- Với `PreparedStatementCallback` mở ResultSet thủ công, dùng test/instrumentation để xác nhận ResultSet đã đóng cả trong đường thành công và đường lỗi.
- Nếu muốn đếm chính xác `Connection.close()`, có thể dùng proxy/spying DataSource được kiểm soát, **nhưng phải diễn giải cùng bối cảnh transaction/pool**: logical close không chứng minh physical socket bị đóng.

### 17.4. Test dưới tải

Chạy truy vấn thực tế với cùng dataset/driver/pool:
- Tăng concurrency đến gần giới hạn.
- Đo active/pending/idle, tốc độ trả handle, timeout, DB utilization.
- So sánh dùng `query(...)` trả danh sách, `queryForStream(...)` được đóng, và một testcase stream cố tình không đóng trong môi trường kiểm thử cô lập.
- Kiểm tra độ trễ query, transaction dài và lock wait; **đừng kết luận pool leak chỉ vì active connections cao tại một thời điểm**.

## 18. Những lỗi thường gặp và sửa thế nào

**Sai 1 — Tự đóng Connection trong callback template**

```java
// SAI: connection do JdbcTemplate cấp không thuộc quyền đóng của callback.
jdbc.execute((org.springframework.jdbc.core.ConnectionCallback<Void>) con -> {
    con.close();
    return null;
});
```

Điều này có thể phá transaction hoặc làm những thao tác cùng transaction thất bại. **Đúng:** dùng connection do template cấp trong callback; chỉ đóng statement/resultset callback **tự tạo**.

**Sai 2 — Dùng raw DataSource.getConnection() rồi không đóng**

```java
// SAI: connection giữ mãi nếu không có finally/try-with-resources.
java.sql.Connection con = dataSource.getConnection();
java.sql.PreparedStatement ps = con.prepareStatement("SELECT 1");
// ...
```

Đây là snippet minh họa, không phải method hoàn chỉnh. **Đúng:** ưu tiên `JdbcTemplate`. Nếu tự lấy JDBC connection thì try-with-resources; nếu cần tham gia Spring JDBC transaction, lấy/release bằng `DataSourceUtils` hoặc dùng `JdbcTemplate.execute(ConnectionCallback)`.

**Sai 3 — Tưởng queryForStream tự close sau terminal operation**

```java
// SAI: thiếu close cho Stream dù đã tiêu thụ.
var results = jdbc.queryForStream(
    "SELECT id, order_code, status, amount_cents FROM orders",
    MAPPER);
results.forEach(System.out::println);
```

Đây là đoạn trong class có `jdbc`/`MAPPER`. **Đúng:** `try (var results = jdbc.queryForStream(...)) { ... }`.

**Sai 4 — Đóng ResultSet mà template đang quản lý trong RowMapper**

`RowMapper` không sở hữu ResultSet và không được đóng nó. **Đúng:** chỉ tạo DTO và trả về. Với ResultSet do `PreparedStatementCallback` tự mở qua `executeQuery()` thì callback lại **phải đóng** vì nó sở hữu.

**Sai 5 — Mở thêm connection trong mỗi RowMapper invocation**

Truy vấn 500 hàng mà mỗi callback lại truy vấn DB có thể tạo 500 round-trip (N+1) và tăng áp lực pool. **Đúng:** JOIN/projection/batch ở SQL khi phù hợp, hoặc thiết kế lookup tách riêng theo batch.

**Sai 6 — Nghĩ @Transactional luôn hoạt động trên mọi lời gọi**

Self-invocation, thiếu proxy, transaction manager trỏ DataSource khác hoặc chuyển thread có thể làm transaction scope không như mong đợi. **Đúng:** đặt ranh giới transaction ở public service được Spring quản lý, kiểm thử bằng DB thật, kiểm tra wiring transaction manager/DataSource.

**Sai 7 — Dùng @Transactional để giải quyết leak Stream**

Transaction không miễn trách nhiệm đóng Stream và không kéo dài tự động nếu method trả Stream. **Đúng:** kết thúc tiêu thụ trong transaction và try-with-resources cùng phạm vi.

**Sai 8 — Nuốt mọi SQLException/RuntimeException**

Nuốt lỗi không giải phóng được thêm tài nguyên mà chỉ che lỗi vận hành. **Đúng:** giữ nguyên error signal, phân loại tại boundary cần thiết, ghi metrics/log phù hợp.

## 19. Câu hỏi tự kiểm tra

1. Khi `JdbcTemplate.query(...)` trả một `List<OrderRow>`, các bản ghi Java có còn phụ thuộc `ResultSet` không? **Không**: chúng là các object đã được mapping; template đã hoàn tất vòng đời ResultSet của query chuẩn.
2. Nếu `PreparedStatementCallback` gọi `ps.executeQuery()`, ai đóng ResultSet vừa nhận? **Callback** nên dùng try-with-resources, dù statement được template cấp.
3. Khi `JdbcTemplate` đang tham gia `@Transactional`, gọi `releaseConnection` sau query có trả connection về pool ngay không? **Không nhất thiết**: connection gắn với transaction được transaction manager giữ đến khi transaction hoàn tất.
4. `Connection.close()` trên Hikari pooled connection có luôn đóng socket DB vật lý không? **Không**: thường chỉ trả logical connection cho pool.
5. Vì sao `Stream.toList()` không thay `Stream.close()`? **Terminal operation** tiêu thụ phần tử nhưng không bảo đảm gọi close cho stream; phải dùng try-with-resources.
6. Nếu một `RowMapper` ném RuntimeException, `JdbcTemplate` có dọn tài nguyên không? **Có, theo hợp đồng cleanup**, nhưng ngoại lệ từ mapper vẫn có thể truyền lên; dọn JDBC và xử lý lỗi nghiệp vụ là hai trách nhiệm khác.
7. Vì sao transaction dài làm pool cạn dù không có leak? Vì connection có thể bị giữ hợp lệ trong suốt transaction, kể cả khi từng statement đã đóng.
8. Có nên gọi `dataSource.getConnection()` trực tiếp bên trong service `@Transactional`? Chỉ khi hiểu và xử lý rõ transaction awareness; ưu tiên template hoặc `DataSourceUtils` cho mã thấp tầng.

## 20. Checklist trước khi review code

- [ ] Repository dùng một `JdbcTemplate` được inject/configure với `DataSource` đúng.
- [ ] Query/update chuẩn chỉ cung cấp SQL, parameters và mapping; không tự mở hoặc đóng connection.
- [ ] Callback không đóng JDBC resource do template cấp.
- [ ] Mọi `PreparedStatement`/`ResultSet` được callback **tự mở** đều có try-with-resources/finally thích hợp.
- [ ] Mọi `queryForStream` được đóng bằng `try-with-resources` hoặc ownership caller được ghi rõ và kiểm thử.
- [ ] Không trả `ResultSet`, `PreparedStatement`, raw `Connection` ra khỏi scope lifetime của chúng.
- [ ] Transaction manager và template sử dụng đúng `DataSource`; transaction method được gọi qua Spring proxy.
- [ ] Transaction đủ ngắn; không giữ connection trong lúc chờ gọi hệ thống ngoài.
- [ ] Không nuốt `DataAccessException` hoặc map lỗi SQL thành danh sách rỗng.
- [ ] Pool, query, transaction được đo; phân biệt long-held connection với resource leak.
- [ ] Có integration test cho thành công, SQL exception, mapping exception, rollback và stream cleanup.
- [ ] Không nhầm `close()` logical handle với đóng kết nối vật lý.

## 21. Kết luận

**`JdbcTemplate` thực thi và dọn tài nguyên JDBC theo hợp đồng của API.** Nó lấy connection bằng cơ chế tương thích Spring transaction, tạo statement, duyệt/mapping ResultSet và release tài nguyên template sở hữu ngay cả trong nhiều đường lỗi. **Transaction manager** quyết định khi nào connection đang tham gia transaction thực sự được trả lại pool; **pool** quyết định khi nào logical close đồng nghĩa đóng physical connection.

Phần code ứng dụng vẫn có trách nhiệm rõ ràng: đóng những statement/resultset tự tạo trong callback, đóng stream trả từ `queryForStream`, giữ transaction ngắn và không phá ownership của connection được template cấp. Hiểu đúng ba tầng trách nhiệm **template – transaction – pool** mới giúp tránh leak, phòng pool starvation và thiết kế tầng JDBC đáng tin cậy.

## Tài liệu chính thức để tra cứu thêm

- Spring Framework — Data Access with JDBC (Spring quản lý việc nào, application chịu trách nhiệm việc nào): https://docs.spring.io/spring-framework/reference/data-access/jdbc.html
- Spring Framework — JDBC Core, JdbcTemplate, callbacks và SQLExceptionTranslator: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Controlling Database Connections, DataSourceUtils: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Framework — Annotation-driven Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring API — JdbcTemplate queryForStream và yêu cầu đóng Stream: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
