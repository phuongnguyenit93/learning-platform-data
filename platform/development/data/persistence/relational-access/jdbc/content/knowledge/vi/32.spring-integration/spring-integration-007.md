# Phối hợp DAO JDBC với giao dịch do Spring quản lý

Trong JDBC thuần, một thao tác nghiệp vụ gồm nhiều câu SQL thường phải tự điều khiển `Connection.setAutoCommit(false)`, `commit()` và `rollback()`. Khi ứng dụng sử dụng **Spring Framework**, phần quản lý ranh giới giao dịch có thể được chuyển cho **Spring transaction management**. Lúc đó, tầng Service khai báo `@Transactional`, còn các DAO tập trung vào câu SQL tham số hóa, ánh xạ `ResultSet` và kiểm tra kết quả cập nhật.

Điểm quan trọng không phải chỉ là thêm annotation. Để một thao tác trên `InventoryDao`, `OrderDao` và `OrderItemDao` thật sự thuộc **cùng transaction**, các DAO phải **lấy và dùng kết nối JDBC mà Spring đã liên kết với transaction hiện tại**. `JdbcTemplate` làm việc này thông qua cơ chế Spring; DAO viết JDBC thủ công cần dùng `DataSourceUtils` hoặc một abstraction tương thích. Nếu DAO gọi `dataSource.getConnection()` trực tiếp rồi tự commit trên kết nối mới, `@Transactional` ở Service có thể **không bao phủ** thao tác đó.

Bài thuộc chương **Tích hợp Spring** của module **JDBC**, tập trung vào phối hợp các DAO JDBC bằng API chuẩn `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và các thành phần Spring JDBC/transaction. Ví dụ sử dụng **Java 17+**, Spring JDBC với transaction manager JDBC cục bộ, và SQL quan hệ. Spring là thư viện/framework bổ sung, không phải một phần của Java SE hoặc JDBC specification.

Sau bài học, bạn có thể:

- Giải thích quan hệ giữa `@Transactional`, `PlatformTransactionManager`, `JdbcTransactionManager`/`DataSourceTransactionManager` và `DataSource`.
- Phối hợp nhiều DAO dùng `JdbcTemplate` trong **cùng transaction của Service**.
- Viết DAO JDBC thuần tham gia transaction Spring bằng `DataSourceUtils.getConnection(...)` và `releaseConnection(...)`.
- Phân biệt rollback mặc định đối với **unchecked exception** và rollback có cấu hình cho **checked `SQLException`**.
- Nhận diện trường hợp proxy, self-invocation, nhiều DataSource, `REQUIRES_NEW` và công việc bất đồng bộ làm mất ranh giới giao dịch mong muốn.
- Kiểm thử thành công, rollback, update count, khóa sinh và thao tác đồng thời trên database thật.

## 1. Bài toán: nhiều DAO, một thao tác đặt hàng

Một đơn hàng cần thực hiện ba việc:

1. Kiểm tra và giảm tồn kho của từng SKU.
2. Tạo bản ghi đơn hàng cha và nhận khóa `order_id` do DB sinh.
3. Chèn các dòng chi tiết với khóa ngoại trỏ tới đơn hàng.

Các bước phải là **một đơn vị nghiệp vụ**: hoặc tất cả thay đổi được commit, hoặc tất cả thay đổi chưa commit phải được rollback khi gặp lỗi.

```text
                      HTTP / Controller
                              |
                              v
                    CheckoutService.placeOrder
                       @Transactional
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
        StockDao          OrderDao          OrderLineDao
       JdbcTemplate      JdbcTemplate        JDBC thuần
             |                |                |
             +----------------+----------------+
                              |
                 Cùng Connection do Spring
                 liên kết với transaction
                              |
                     commit hoặc rollback
                  (Spring transaction manager)
```

Trong bài này, `StockDao` và `OrderDao` dùng `JdbcTemplate`, còn `OrderLineDao` cố ý dùng `PreparedStatement`/`Connection` trực tiếp để minh họa cách **JDBC thuần tham gia transaction đang được Spring quản lý**. Hai phong cách có thể phối hợp nếu dùng đúng cùng `DataSource` và ranh giới transaction.

### Nếu mỗi DAO tự commit thì sao?

Giả sử `StockDao` đã trừ ba sản phẩm nhưng `OrderLineDao` thất bại vì một ràng buộc khóa ngoại. Nếu các DAO tự tạo transaction và commit riêng, đơn hàng có thể dở dang. Ngược lại, nếu mọi thao tác sử dụng đúng transaction của `CheckoutService.placeOrder`, Spring có thể rollback giảm kho và đơn cha khi DAO cuối ném lỗi phù hợp chính sách rollback.

**`@Transactional` không tự động biến mọi thao tác ngoài cùng DataSource thành một giao dịch**, và cũng không tự phối hợp transaction JDBC với HTTP, message broker hoặc hai database độc lập.

## 2. Những thành phần Spring tham gia giao dịch JDBC

| Thành phần | Vai trò |
| --- | --- |
| `DataSource` | Nguồn cấp kết nối JDBC; thường được cấu hình với connection pool |
| `PlatformTransactionManager` | Hợp đồng Spring để bắt đầu, commit hoặc rollback transaction |
| `DataSourceTransactionManager` | Transaction manager cho **một JDBC DataSource**; liên kết connection với thread đang xử lý transaction |
| `JdbcTransactionManager` | Biến thể JDBC transaction manager kế thừa `DataSourceTransactionManager`, có tích hợp chuyển đổi `SQLException` phù hợp Spring |
| `@Transactional` | Metadata khai báo ranh giới, propagation, isolation, rollback rules, read-only... |
| Spring AOP proxy | Chặn lời gọi thích hợp vào bean, thực hiện logic transaction quanh method |
| `JdbcTemplate` | Tạo statement, bind tham số, xử lý `ResultSet`/`SQLException` và sử dụng kết nối phù hợp transaction Spring |
| `DataSourceUtils` | Cấp/giải phóng connection theo context Spring, để JDBC thuần tham gia transaction hiện tại |

Với Spring transaction management **imperative** dùng JDBC, transaction context thường được liên kết với **thread hiện tại** qua `TransactionSynchronizationManager`. Khi một Service gọi các DAO một cách đồng bộ trên thread đó, các DAO dùng cùng cơ chế lấy connection sẽ tham gia transaction.

```text
Spring proxy nhận lời gọi CheckoutService.placeOrder(...)
      |
      +-- TransactionManager: bắt đầu transaction
      |       |
      |       +-- Mượn Connection từ DataSource
      |       +-- Chuyển autoCommit phù hợp, bind vào thread
      |
      +-- Method body:
      |       |
      |       +-- JdbcTemplate -> DataSourceUtils -> connection đang bind
      |       +-- JdbcTemplate -> DataSourceUtils -> cùng connection
      |       +-- Raw JDBC -> DataSourceUtils -> cùng connection
      |
      +-- Method trả về thành công -> commit
      |
      +-- Method ném exception thỏa rollback rule -> rollback
      |
      +-- Gỡ transaction context, trả Connection về pool
```

**Tầng DAO không cần tự gọi `setAutoCommit(false)`, `commit()` hoặc `rollback()`.** Nó chỉ thực thi SQL. Quyền điều khiển transaction thuộc Spring và Service đã khai báo ranh giới.

### Phạm vi hỗ trợ

`JdbcTransactionManager` và `DataSourceTransactionManager` quản lý giao dịch JDBC cục bộ thông qua **một DataSource**. Nếu workflow cập nhật hai database độc lập hoặc gửi message vào broker, một JDBC transaction manager đơn lẻ không thể đảm bảo nguyên tử cho tất cả tài nguyên. Bài sẽ quay lại giới hạn này ở phần cuối.

## 3. Cấu hình DataSource và transaction manager

Nếu ứng dụng dùng **Spring Boot** cùng `spring-boot-starter-jdbc` và có một `DataSource` phù hợp, Boot thường tự cấu hình `JdbcTemplate` và transaction manager theo điều kiện auto-configuration. Đừng đăng ký thêm bean chỉ vì một ví dụ minh họa đã viết `@Bean`; hãy kiểm tra cấu hình thực tế và tránh vô tình tạo nhiều transaction manager cạnh tranh.

Khi cấu hình Spring thuần hoặc muốn kiểm soát rõ ràng, có thể khai báo:

```java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class JdbcConfig {
    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

Ở đây `DataSource` là bean đã được cấu hình **riêng** bằng driver/connection pool và thông số kết nối an toàn. Đoạn `JdbcConfig` không tự tạo DataSource và không cung cấp URL, username/password. Đối với ứng dụng Spring Boot đã có các bean tương đương, **không cần chép nguyên cấu hình này**.

Những yêu cầu quan trọng:

1. `JdbcTemplate`, `DataSourceUtils` và transaction manager phải làm việc với **cùng DataSource phù hợp**, hoặc lớp proxy DataSource được cấu hình theo cách Spring hỗ trợ.
2. Spring phải quản lý `CheckoutService` như một **bean** và thực hiện transaction advice cho lời gọi vào method.
3. DB/driver và bảng mục tiêu phải hỗ trợ transaction; `@Transactional` không sửa được engine không hỗ trợ rollback.
4. DAO không tự thay `autoCommit`, isolation hoặc commit trong transaction của Service.
5. Connection pool phải có đủ connection, cấu hình timeout và chiến lược reset trạng thái phù hợp.

### `JdbcTransactionManager` hay `DataSourceTransactionManager`?

Cả hai đều phù hợp với phạm vi một JDBC DataSource. `JdbcTransactionManager` cung cấp hành vi chuyển đổi `SQLException` ở các bước giao dịch tốt hơn trong Spring JDBC hiện đại; `DataSourceTransactionManager` là nền tảng phổ biến và vẫn được sử dụng. Không cần hai manager cho cùng một DataSource nếu không có lý do thiết kế cụ thể.

Trong ứng dụng có nhiều nguồn dữ liệu, tên bean hoặc qualifier của transaction manager cần được xác định rõ, chẳng hạn `@Transactional(transactionManager = "ordersTxManager")`. **Một annotation không tự quyết định mọi DAO phải dùng database nào**.

## 4. DDL và fixture cho ví dụ đặt hàng

Các bảng minh họa:

```sql
-- DDL gần SQL chuẩn; cú pháp IDENTITY, CHECK, TIMESTAMP
-- có thể cần điều chỉnh theo DBMS.
CREATE TABLE product_stock (
    sku           VARCHAR(64) PRIMARY KEY,
    available_qty INTEGER NOT NULL CHECK (available_qty >= 0)
);

CREATE TABLE purchase_order (
    order_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_ref  VARCHAR(64) NOT NULL,
    order_status  VARCHAR(20) NOT NULL
);

CREATE TABLE purchase_order_item (
    order_id BIGINT NOT NULL,
    line_no  INTEGER NOT NULL,
    sku      VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no),
    UNIQUE (order_id, sku),
    FOREIGN KEY (order_id) REFERENCES purchase_order(order_id),
    FOREIGN KEY (sku) REFERENCES product_stock(sku)
);
```

Seed trong **database dành riêng cho kiểm thử**:

```sql
INSERT INTO product_stock(sku, available_qty)
VALUES ('SKU-A', 8);

INSERT INTO product_stock(sku, available_qty)
VALUES ('SKU-B', 5);

INSERT INTO product_stock(sku, available_qty)
VALUES ('SKU-Z', 0);
```

Với đơn gồm `SKU-A × 2` và `SKU-B × 3`, kết quả sau commit dự kiến là kho còn `6` và `2`, có một đơn cha và hai dòng con. Nếu đặt `SKU-A × 2` rồi `SKU-Z × 1`, toàn thao tác phải thất bại: kho của `SKU-A` vẫn là `8` khi kiểm tra bằng kết nối khác sau rollback.

**Lưu ý:** `GENERATED ALWAYS AS IDENTITY` có cú pháp khác nhau giữa PostgreSQL, SQL Server, MySQL, Oracle và một số DB khác. Ví dụ Java ở phần sau dùng API JDBC chuẩn để lấy khóa sinh; hãy chạy migration và integration test đúng DB/driver triển khai. Không tự tạo các bảng bằng DDL này trong mỗi test rồi mặc định rollback sẽ hoàn tác mọi DDL.

## 5. `StockDao`: dùng `JdbcTemplate` và một `UPDATE` nguyên tử

DAO thứ nhất trừ kho bằng một câu SQL có điều kiện:

```sql
UPDATE product_stock
SET available_qty = available_qty - ?
WHERE sku = ? AND available_qty >= ?;
```

Điều kiện `available_qty >= ?` giúp DB chỉ trừ tồn kho nếu còn đủ hàng. Đây là cách mạnh hơn việc `SELECT` số lượng trước rồi dùng số cũ ở Java để ghi đè, vì hai transaction khác nhau có thể đọc cùng giá trị trước khi cập nhật.

**Tệp `InsufficientStockException.java`:**

```java
public final class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException(String sku) {
        super("Unknown product or insufficient stock: " + sku);
    }
}
```

**Tệp `StockDao.java`:**

```java
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class StockDao {
    private static final String RESERVE = """
            UPDATE product_stock
            SET available_qty = available_qty - ?
            WHERE sku = ? AND available_qty >= ?
            """;

    private final JdbcTemplate jdbc;

    public StockDao(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    public void reserve(String sku, int quantity) {
        int updated = jdbc.update(RESERVE, quantity, sku, quantity);
        if (updated == 0) {
            throw new InsufficientStockException(sku);
        }
        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected one stock row, got " + updated);
        }
    }
}
```

`JdbcTemplate.update(...)` trả số hàng bị tác động. Vì `sku` là khóa chính, hợp đồng của ví dụ là:

| Update count | Diễn giải |
| ---: | --- |
| `1` | Trừ kho thành công **trong transaction hiện tại**; chưa đồng nghĩa đã commit |
| `0` | SKU không tồn tại hoặc lượng kho không đủ |
| Khác `0`/`1` | Bất thường đối với khóa chính, cần báo lỗi |

`InsufficientStockException` là **unchecked exception**, nên mặc định Spring đánh dấu transaction rollback khi exception đi ra khỏi method `@Transactional`. Các lỗi SQL xảy ra bên trong `JdbcTemplate` cũng thường được chuyển sang những kiểu `DataAccessException` không checked; DAO không cần viết code đóng statement/connection hoặc tự rollback.

Không bắt `InsufficientStockException` ở Service rồi âm thầm bỏ qua để tiếp tục tạo đơn. Nếu nghiệp vụ muốn trả lỗi có cấu trúc cho API, có thể bắt ở tầng Controller **sau khi** method giao dịch đã thoát và rollback diễn ra.

## 6. `OrderDao`: chèn đơn hàng và lấy generated key bằng Spring JDBC

`JdbcTemplate` hỗ trợ `GeneratedKeyHolder` để nhận khóa do DB tạo. Ở DAO này, `PreparedStatementCreator` được cung cấp dưới dạng lambda; Spring lấy connection thuộc transaction hiện tại và gọi lambda để chuẩn bị statement.

**Tệp `OrderDao.java`:**

```java
import java.sql.PreparedStatement;
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class OrderDao {
    private static final String INSERT = """
            INSERT INTO purchase_order(customer_ref, order_status)
            VALUES (?, ?)
            """;

    private final JdbcTemplate jdbc;

    public OrderDao(JdbcTemplate jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    public long insert(String customerRef) {
        KeyHolder keyHolder = new GeneratedKeyHolder();

        int updated = jdbc.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                    INSERT, new String[] { "order_id" });
            ps.setString(1, customerRef);
            ps.setString(2, "PLACED");
            return ps;
        }, keyHolder);

        if (updated != 1) {
            throw new IllegalStateException(
                    "Expected one inserted order, got " + updated);
        }

        Number key = keyHolder.getKey();
        if (key == null || key.longValue() <= 0) {
            throw new IllegalStateException(
                    "Database did not return generated order_id");
        }
        return key.longValue();
    }
}
```

Hợp đồng `KeyHolder.getKey()` phù hợp khi driver trả **một khóa số duy nhất**. Với nhiều cột khóa, trigger phức tạp hoặc DBMS có cú pháp trả khóa riêng, cần dùng `getKeys()`/`getKeyList()` hoặc API thích hợp và kiểm tra driver. Overload `prepareStatement(sql, columnNames)` không được hỗ trợ đồng đều trên mọi driver; có thể thay bằng `Statement.RETURN_GENERATED_KEYS` khi phù hợp.

Đơn hàng được chèn **chưa commit** nhưng `order_id` có thể được dùng ngay để tạo dòng con qua DAO khác tham gia **cùng transaction**. Không dùng `SELECT MAX(order_id)` để tìm khóa vừa tạo: giá trị lớn nhất có thể thuộc một request khác khi hệ thống chạy đồng thời.

## 7. `OrderLineDao`: JDBC thuần tham gia transaction Spring

Đây là phần dễ mắc lỗi nhất. DAO sau vẫn dùng `Connection` và `PreparedStatement` của JDBC, nhưng **không trực tiếp gọi `dataSource.getConnection()`**. Nó dùng `DataSourceUtils.getConnection(dataSource)` để lấy connection liên kết với transaction hiện tại, và `DataSourceUtils.releaseConnection(...)` trong `finally` để trả/giải phóng theo đúng cơ chế Spring.

**Tệp `OrderLineDao.java`:**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Repository;

@Repository
public class OrderLineDao {
    private static final String INSERT = """
            INSERT INTO purchase_order_item
                (order_id, line_no, sku, quantity)
            VALUES (?, ?, ?, ?)
            """;

    private final DataSource dataSource;

    public OrderLineDao(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(
                dataSource, "dataSource");
    }

    // Cố ý để SQLException là checked exception của JDBC thuần.
    public void insert(
            long orderId, int lineNo, String sku, int quantity)
            throws SQLException {

        Connection connection = DataSourceUtils.getConnection(dataSource);
        try {
            try (PreparedStatement ps =
                         connection.prepareStatement(INSERT)) {
                ps.setLong(1, orderId);
                ps.setInt(2, lineNo);
                ps.setString(3, sku);
                ps.setInt(4, quantity);

                int updated = ps.executeUpdate();
                if (updated != 1) {
                    throw new SQLException(
                            "Expected one inserted order line");
                }
            }
        } finally {
            DataSourceUtils.releaseConnection(connection, dataSource);
        }
    }
}
```

**Ba quy tắc quan trọng:**

1. `DataSourceUtils.getConnection(dataSource)` có thể lấy **connection đã bind** vào thread của transaction hiện tại. Nếu không có transaction Spring, nó có thể lấy một connection mới để dùng cho thao tác.
2. `PreparedStatement` do DAO tạo vẫn được đóng bằng `try-with-resources`. **Không đưa `Connection` vào `try-with-resources` ở đây**, vì `close()` trực tiếp trên connection có thể làm sai vòng đời của connection do Spring sở hữu.
3. `DataSourceUtils.releaseConnection(connection, dataSource)` được gọi kể cả khi `prepareStatement` hoặc `executeUpdate` ném exception. Khi connection thuộc transaction Spring đang hoạt động, nó **không đóng connection nền trước khi transaction kết thúc**.

`DataSourceUtils` thuộc Spring JDBC. Đây không phải API JDBC chuẩn thuần, mà là cầu nối đúng cách khi muốn tự viết `PreparedStatement` trong ứng dụng có transaction do Spring quản lý.

### Sai: tự mượn kết nối rồi tưởng đang tham gia `@Transactional`

```java
// KHÔNG nên dùng trong DAO phải tham gia transaction của Service:
try (Connection connection = dataSource.getConnection()) {
    // Connection mới này có thể không thuộc Spring transaction hiện tại.
    try (PreparedStatement ps = connection.prepareStatement(SQL)) {
        // ... executeUpdate ...
    }
}
```

Điều này đặc biệt nguy hiểm khi `Connection` mặc định có `autoCommit = true`: một DAO có thể ghi và commit ngoài transaction của Service. Lưu ý có những wrapper như `TransactionAwareDataSourceProxy` được Spring thiết kế để một số code gọi `getConnection()/close()` kiểu JDBC thuần vẫn tham gia transaction; **đừng giả định mọi DataSource đang dùng đều là wrapper đó**. Khi kiểm soát được code DAO, dùng `JdbcTemplate` hoặc `DataSourceUtils` làm hợp đồng rõ ràng.

### Có thể dùng `JdbcTemplate.execute` thay JDBC thủ công không?

Có. Một DAO cần thao tác connection JDBC ở mức thấp có thể dùng `JdbcTemplate.execute(ConnectionCallback<T>)`. Spring sẽ điều phối connection/transaction và việc release cho callback, còn lambda chỉ thao tác trên connection đã cung cấp:

```java
Integer result = jdbcTemplate.execute(connection -> {
    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE product_stock SET available_qty = ? WHERE sku = ?")) {
        ps.setInt(1, newQty);
        ps.setString(2, sku);
        return ps.executeUpdate();
    }
});
```

Đoạn này minh họa callback khi cần dùng API JDBC thấp hơn `JdbcTemplate.update`. **Không đóng `connection` bên trong callback**, vì Spring quản lý nó. Khi có thể dùng `jdbcTemplate.update(sql, params...)` trực tiếp, nên ưu tiên cách đơn giản hơn.

## 8. Tầng Service: `@Transactional` bao trùm mọi DAO

Trước tiên, biểu diễn dòng đặt hàng bằng một `record`:

**Tệp `PurchaseLine.java`:**

```java
import java.util.Objects;

public record PurchaseLine(String sku, int quantity) {
    public PurchaseLine {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank() || sku.length() > 64 || quantity <= 0) {
            throw new IllegalArgumentException("Invalid purchase line");
        }
    }
}
```

**Tệp `CheckoutService.java`:**

```java
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {
    private final StockDao stockDao;
    private final OrderDao orderDao;
    private final OrderLineDao orderLineDao;

    public CheckoutService(
            StockDao stockDao,
            OrderDao orderDao,
            OrderLineDao orderLineDao) {
        this.stockDao = Objects.requireNonNull(stockDao, "stockDao");
        this.orderDao = Objects.requireNonNull(orderDao, "orderDao");
        this.orderLineDao = Objects.requireNonNull(
                orderLineDao, "orderLineDao");
    }

    // Checked SQLException từ DAO JDBC thuần cũng kích hoạt rollback.
    @Transactional(rollbackFor = SQLException.class)
    public long placeOrder(
            String customerRef, List<PurchaseLine> requestedLines)
            throws SQLException {

        Objects.requireNonNull(customerRef, "customerRef");
        if (customerRef.isBlank() || customerRef.length() > 64) {
            throw new IllegalArgumentException("Invalid customerRef");
        }

        List<PurchaseLine> lines = List.copyOf(
                Objects.requireNonNull(requestedLines, "requestedLines"));
        if (lines.isEmpty() || lines.size() > 200) {
            throw new IllegalArgumentException(
                    "Order must have 1..200 lines");
        }

        Set<String> uniqueSkus = new HashSet<>();
        for (PurchaseLine line : lines) {
            if (!uniqueSkus.add(line.sku())) {
                throw new IllegalArgumentException(
                        "Duplicate SKU: " + line.sku());
            }
        }

        // Lấy khóa tồn kho theo thứ tự nhất quán để giảm deadlock.
        List<PurchaseLine> stockOrder = new ArrayList<>(lines);
        stockOrder.sort(Comparator.comparing(PurchaseLine::sku));

        for (PurchaseLine line : stockOrder) {
            stockDao.reserve(line.sku(), line.quantity());
        }

        long orderId = orderDao.insert(customerRef);
        for (int index = 0; index < lines.size(); index++) {
            PurchaseLine line = lines.get(index);
            orderLineDao.insert(
                    orderId, index + 1, line.sku(), line.quantity());
        }

        // Không có connection.commit() ở đây:
        // Spring transaction interceptor quyết định commit khi method trả.
        return orderId;
    }
}
```

Caller lấy Service từ Spring, chẳng hạn bằng constructor injection trong một Controller hoặc test:

```java
long orderId = checkoutService.placeOrder(
        "CUSTOMER-42",
        List.of(
                new PurchaseLine("SKU-A", 2),
                new PurchaseLine("SKU-B", 3)));
```

`CheckoutService` không cần biết cách `JdbcTemplate` tạo statement hay `DataSourceUtils` lấy connection. Nó chỉ điều phối các quy tắc nghiệp vụ. **Spring transaction interceptor**, không phải DAO và cũng không phải câu `return` tự thân, thực hiện commit sau khi method hoàn thành thành công.

### Lưu ý về trình tự và lỗi

| Bước | Thành phần | Trạng thái transaction |
| --- | --- | --- |
| Gọi `placeOrder` qua Spring proxy | Transaction manager | Mở hoặc tham gia transaction theo propagation |
| `stockDao.reserve` lần lượt | `JdbcTemplate` | Thay đổi kho chưa commit |
| `orderDao.insert` | `JdbcTemplate` + `KeyHolder` | Đơn cha được tạo, khóa sẵn dùng trong cùng transaction |
| `orderLineDao.insert` | `DataSourceUtils` + JDBC thuần | Dòng con được chèn cùng transaction |
| Method trả về bình thường | Spring interceptor | Thử commit toàn bộ transaction |
| Method ném `InsufficientStockException` | Spring interceptor | Rollback theo mặc định vì là unchecked exception |
| Method ném `SQLException` | Spring interceptor | Rollback vì `rollbackFor = SQLException.class` |

Không cần biến mọi DAO thành `@Transactional`. Annotation nên đặt ở **ranh giới use case** để một loạt thao tác được xử lý nguyên tử. Việc từng DAO có `@Repository` giúp tổ chức bean và exception translation (tùy cơ chế Spring), nhưng **`@Repository` không tự mở một transaction**.

## 9. Rollback mặc định và quy tắc cho checked exception

Theo quy tắc mặc định của `@Transactional` trong Spring, **`RuntimeException` và `Error`** khiến transaction được đánh dấu rollback. **Checked exception** như `SQLException` **không mặc nhiên** kích hoạt rollback theo quy tắc mặc định truyền thống.

| Tình huống | Nếu chỉ `@Transactional` mặc định | Cách xử lý trong ví dụ |
| --- | --- | --- |
| `InsufficientStockException extends RuntimeException` | Rollback | Không cần bổ sung rule |
| `DataAccessException` từ `JdbcTemplate` | Rollback vì là unchecked | Không cần bổ sung rule |
| `SQLException` từ DAO JDBC thuần | Có thể **không rollback** chỉ vì checked exception được ném ra | `@Transactional(rollbackFor = SQLException.class)` |
| Method bắt exception rồi trả về bình thường | Spring có thể hiểu use case thành công và commit | Rethrow hoặc đánh dấu rollback có chủ đích |
| Có `noRollbackFor`/rule tùy chỉnh | Quy tắc có thể đổi | Kiểm tra cấu hình thật |

Ví dụ rủi ro:

```java
@Transactional
public void saveSomething() throws SQLException {
    stockDao.reserve("SKU-A", 1);
    orderLineDao.insert(999L, 1, "SKU-A", 1);
    // Nếu DAO ném SQLException là checked exception,
    // default rollback rule không tự yêu cầu rollback.
}
```

Đoạn này là ví dụ anti-pattern, không phải use case hợp lệ: `orderId = 999` có thể không tồn tại và gây lỗi khóa ngoại. Nếu tầng này chỉ dùng `@Transactional` mặc định và ngoại lệ checked đi ra ngoài, Spring có thể vẫn cố commit những thay đổi trước đó (phụ thuộc trạng thái transaction do DB/driver để lại). Dùng rule rollback phù hợp hoặc chuyển lỗi hạ tầng qua `DataAccessException` khi muốn nhất quán với Spring JDBC.

### Không nuốt lỗi trong phương thức giao dịch

Một anti-pattern khác:

```java
@Transactional
public boolean placeOrderQuietly() {
    try {
        // stockDao.reserve(...);
        // orderDao.insert(...);
        // orderLineDao.insert(...);
        return true;
    } catch (RuntimeException error) {
        return false; // Spring interceptor nhìn thấy return bình thường.
    }
}
```

Nếu exception đã bị bắt và không có cơ chế khác đánh dấu rollback, transaction **có thể được commit**. Một số thành phần giao dịch có thể đã đánh dấu `rollback-only`, khiến commit cuối cùng báo `UnexpectedRollbackException`; vì vậy không giả định trả `false` luôn khiến transaction commit được hoặc rollback được.

Ưu tiên để lỗi nghiệp vụ hoặc lỗi JDBC phù hợp **đi ra khỏi method `@Transactional`** rồi bắt nó ở tầng phía ngoài. Nếu thực sự cần xử lý nội bộ nhưng vẫn rollback, có thể dùng `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` trong đúng transaction được Spring advice; đây là giải pháp gắn với Spring nên cần dùng thận trọng và ghi rõ hợp đồng.

## 10. Vì sao `@Transactional` đôi khi không hoạt động?

`@Transactional` với cơ chế proxy của Spring chỉ có hiệu lực khi lời gọi **đi qua proxy được Spring quản lý**, với những giới hạn cụ thể của kiểu proxy và phiên bản cấu hình.

### Self-invocation: lời gọi nội bộ không đi qua proxy

```java
@Service
public class CheckoutFacade {
    public void handleRequest() throws SQLException {
        // Gọi method ngay trên this: bỏ qua proxy giao dịch
        // của method placeOrderInternal nếu chỉ dùng proxy mode.
        placeOrderInternal();
    }

    @Transactional(rollbackFor = SQLException.class)
    public void placeOrderInternal() throws SQLException {
        // ... gọi các DAO ...
    }
}
```

Nếu `handleRequest` không có transaction và `placeOrderInternal()` được gọi trực tiếp từ cùng instance, annotation của method nội bộ **không được áp dụng qua proxy thông thường**. Cách rõ ràng là tách method giao dịch sang **một Spring bean riêng**, inject bean đó vào caller và gọi qua proxy; hoặc đặt transaction boundary ở public entry point được gọi từ bean khác.

Ngoài ra:

- Không dùng `new CheckoutService(...)` thủ công nếu bạn muốn lời gọi được Spring proxy quản lý.
- Đối với proxy dạng interface hoặc class, giới hạn ở method `private`, `final`, visibility và kiểu proxy khác nhau; dùng **public method không final** cho ví dụ phổ biến để tránh nhập nhằng.
- `@Transactional` có thể đặt trên class hoặc method, nhưng method-level rule và nơi annotation thực sự được nhận diện cần kiểm tra khi dùng interface/proxy.
- Kiểm tra `@EnableTransactionManagement`/auto-configuration và transaction manager bean thật; có annotation trên class không chứng minh transaction advice đã được kích hoạt.
- Chỉ dùng AspectJ weaving thay proxy khi dự án đã chủ động cấu hình và hiểu cơ chế đó; không mặc định mọi lời gọi nội bộ được intercept.

### Lệch thread, tác vụ async và reactive

Với JDBC transaction manager imperative, transaction context gắn với thread. Nếu trong `placeOrder` bạn tạo thread mới, dùng `CompletableFuture.supplyAsync(...)`, hoặc chạy một phương thức `@Async` trên thread khác, các DAO ở thread mới **không tự tham gia transaction JDBC đang mở ở thread gốc**.

```text
Thread A:
  @Transactional -> Connection A được bind vào thread A

Thread B:
  @Async / Executor -> không tự nhận Connection A
  gọi JDBC DAO -> có thể mở transaction/kết nối khác
```

Không truyền một `Connection` có trạng thái cho nhiều thread cùng ghi để “chia sẻ transaction”. Nếu cần một workflow đa bước bất đồng bộ, thiết kế event/outbox, trạng thái nghiệp vụ và transaction riêng cho mỗi đơn vị xử lý. Spring reactive transaction management dùng mô hình context khác và **không được đánh đồng** với transaction manager JDBC imperative của bài này.

## 11. Propagation: `REQUIRED`, `REQUIRES_NEW` và `NESTED`

`@Transactional` có thuộc tính `propagation` để quyết định một method tham gia transaction đang có hay tạo transaction riêng.

| Propagation | Ý nghĩa đơn giản | Hệ quả khi phối hợp nhiều DAO |
| --- | --- | --- |
| `REQUIRED` (mặc định) | Tham gia transaction hiện tại; nếu chưa có thì mở mới | Thường đúng cho một Service điều phối nhiều DAO |
| `MANDATORY` | Yêu cầu đã có transaction, nếu không thì báo lỗi | Hữu ích khi một API nội bộ bắt buộc được gọi trong transaction |
| `REQUIRES_NEW` | Tạm ngưng transaction hiện tại và mở transaction độc lập | Phần này có thể commit dù transaction ngoài rollback |
| `NESTED` | Tạo nhánh dùng JDBC savepoint trong transaction vật lý hiện tại khi được hỗ trợ | Có thể rollback phần bên trong mà giữ transaction ngoài, nhưng không phải transaction độc lập |
| `SUPPORTS` | Có transaction thì tham gia; nếu không có thì thực thi không transaction | Không phù hợp khi method bắt buộc phải ghi nguyên tử |

### `REQUIRES_NEW` phá vỡ nguyên tử nếu dùng sai mục đích

Giả sử `OrderLineService.insertLine` đặt `@Transactional(propagation = REQUIRES_NEW)` rồi được Service đặt hàng gọi qua proxy. Nó có thể mở một **transaction khác**, sử dụng thêm connection và commit trước transaction ngoài. Nếu transaction ngoài thất bại, phần đã commit độc lập **không tự rollback**.

Điều này thường **không phù hợp** cho các bước trừ kho, tạo đơn và chèn dòng vốn phải nguyên tử. Ngoài ra, nếu pool nhỏ và nhiều transaction ngoài đang giữ connection, `REQUIRES_NEW` cần mượn connection thứ hai có thể gây thiếu pool hoặc timeout.

`NESTED` là một cơ chế khác: trên transaction manager JDBC hỗ trợ savepoint, nó có thể tạo `Savepoint` để rollback một đoạn trong **cùng physical transaction**. Nó không cho phép một transaction con commit độc lập trước transaction ngoài. Khả năng savepoint phụ thuộc JDBC driver/DB và cấu hình transaction manager; không giả định mọi DB luôn hỗ trợ.

### Một ví dụ propagation cần tránh

```java
@Transactional(propagation =
        org.springframework.transaction.annotation.Propagation.REQUIRES_NEW)
public void insertOrderLineIndependently(...) {
    // Không nên dùng như một bước của checkout cần atomic.
}
```

Đây là **chữ ký minh họa** (`...` không phải tham số Java hợp lệ). Mục đích là cảnh báo về propagation, không phải đoạn code có thể biên dịch. Trong ví dụ hoàn chỉnh, DAO không khai báo transaction độc lập; mọi DAO tham gia `@Transactional(REQUIRED)` của `CheckoutService`.

## 12. Transaction isolation, khóa hàng và xử lý deadlock

`@Transactional` không thay thế thiết kế SQL đúng. Để không bán vượt tồn kho, `StockDao.reserve` vẫn dùng:

```sql
UPDATE product_stock
SET available_qty = available_qty - ?
WHERE sku = ? AND available_qty >= ?;
```

Đây là thao tác cập nhật có điều kiện dựa trên giá trị hiện tại của DB. Khi hai transaction cùng trừ một SKU, DBMS có thể phải khóa hoặc điều phối conflict theo cơ chế của nó. Với constraint và transaction phù hợp, ta có thể tránh trạng thái tồn kho âm; nhưng **cần kiểm thử khả năng cạnh tranh thực tế trên DB/driver đích**.

Spring cho phép khai báo:

```java
@Transactional(
        isolation = org.springframework.transaction.annotation.Isolation.READ_COMMITTED,
        rollbackFor = SQLException.class)
public long placeOrder(...) throws SQLException {
    // ...
}
```

Đây cũng là **chữ ký minh họa**, không thay thế method `placeOrder` hoàn chỉnh. Mức cô lập chỉ được áp dụng nếu transaction manager và DB hỗ trợ; nếu method tham gia transaction đã có, thuộc tính isolation của method bên trong có thể không thiết lập lại isolation của transaction ngoài theo mặc định.

Mức cô lập cao hơn không mặc nhiên nhanh hoặc an toàn hơn cho mọi workload. Ở `SERIALIZABLE`, DB có thể phát sinh thêm serialization failures; với `READ_COMMITTED`, atomic conditional `UPDATE` vẫn có thể là lựa chọn hợp lý tùy ngữ nghĩa của DB.

### Giảm deadlock bằng thứ tự khóa nhất quán

Ví dụ `CheckoutService` sắp SKU trước khi trừ kho:

```java
List<PurchaseLine> stockOrder = new ArrayList<>(lines);
stockOrder.sort(Comparator.comparing(PurchaseLine::sku));
```

Nếu các Service cùng cập nhật SKU theo cùng thứ tự, nguy cơ vòng chờ sẽ giảm. Nhưng trigger, index, FK, các workflow khác và kế hoạch thực thi có thể vẫn tạo deadlock. Khi DB báo deadlock/serialization failure, phải rollback transaction lỗi, sau đó **quyết định retry cả use case** với giới hạn lần thử và cơ chế idempotency thích hợp.

## 13. Khi Spring báo rollback nhưng caller đã thấy lỗi gì?

### Exception do `JdbcTemplate` và DAO thuần không cùng kiểu

`JdbcTemplate` thường dịch `SQLException` thành `DataAccessException` (unchecked), còn `OrderLineDao` ở ví dụ để nguyên `SQLException` (checked). Đây là lý do Service khai báo:

```java
@Transactional(rollbackFor = SQLException.class)
public long placeOrder(...) throws SQLException {
    // ...
}
```

Một cách thiết kế khác là **dịch mọi exception DAO thuần** về `DataAccessException` qua công cụ dịch lỗi của Spring, giúp Service không phải để lộ `SQLException`. Nhưng nếu chọn cách ấy, phải phân loại và giữ thông tin lỗi đúng; không tự chuyển mọi exception thành một `RuntimeException` vô nghĩa.

### `UnexpectedRollbackException` không có nghĩa mọi thứ đã commit

Nếu method bên trong tham gia cùng transaction đánh dấu `rollback-only` nhưng method ngoài vẫn cố hoàn thành bình thường, Spring có thể ném `UnexpectedRollbackException` tại thời điểm commit ngoài. Điều này giúp caller biết transaction **không được commit như mong đợi**. Không nên xử lý lỗi bằng cách nuốt exception rồi dựa vào việc transaction sẽ “tự hiểu” trạng thái thành công.

### Lỗi ngay lúc commit có thể không rõ kết quả

Nếu DB đã nhận lệnh commit nhưng kết nối mất trước khi Java nhận phản hồi, trạng thái transaction có thể **không xác định được từ phía caller**. Việc Spring báo exception không chứng minh DB chắc chắn chưa commit. Những thao tác có nguy cơ tạo bản ghi trùng khi retry (đặt hàng, thanh toán, tăng số dư) cần **request ID duy nhất**, unique constraint và quy trình đối soát.

Không retry mọi `DataAccessException` hoặc `SQLException` một cách tự động. Lỗi thiếu tồn kho, vi phạm schema hay khóa ngoại không phải lỗi tạm thời. Deadlock hoặc serialization failure có thể phù hợp retry **toàn transaction** nhưng chỉ khi xác định là an toàn, có giới hạn và có idempotency.

## 14. Kiểm thử tích hợp: phải gọi qua Spring proxy và DB thật

Unit test mock ba DAO có thể xác minh thứ tự lời gọi, nhưng **không chứng minh** `JdbcTemplate` và `DataSourceUtils` thật sự dùng cùng JDBC transaction. Cần integration test chạy Spring application context, kết nối tới database test và đọc lại dữ liệu **sau khi lời gọi Service đã kết thúc**.

Đặc biệt, nếu test method có `@Transactional`, nhiều cơ chế kiểm thử Spring sẽ **tự rollback transaction của test**. Điều này tiện khi thử repository nhưng có thể che giấu hành vi commit/rollback thật của `CheckoutService`: Service `REQUIRED` có thể chỉ tham gia transaction của test, không mở/commit transaction riêng.

Để kiểm tra **commit thật của Service**, ví dụ dưới đây cố ý **không đánh dấu test method bằng `@Transactional`**. Fixture được tạo trên database/schema test riêng và được cleanup theo định danh riêng.

### Thiết lập khóa fixture riêng cho mỗi test

Với JUnit Jupiter 5 và `@SpringBootTest` (thư viện Spring Boot Test bổ sung), có thể xây lớp test:

**Tệp minh họa `CheckoutServiceIT.java`:**

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.sql.SQLException;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class CheckoutServiceIT {
    @Autowired
    private CheckoutService service;

    @Autowired
    private JdbcTemplate jdbc;

    private String skuA;
    private String skuZ;
    private String customerRef;

    @BeforeEach
    void seed() {
        String token = UUID.randomUUID().toString();
        skuA = "IT-" + token + "-A";
        skuZ = "IT-" + token + "-Z";
        customerRef = "IT-" + token;

        jdbc.update(
                "INSERT INTO product_stock(sku, available_qty) VALUES (?, ?)",
                skuA, 8);
        jdbc.update(
                "INSERT INTO product_stock(sku, available_qty) VALUES (?, ?)",
                skuZ, 0);
    }

    @AfterEach
    void cleanup() {
        // Test database riêng; dọn hàng con trước hàng cha.
        jdbc.update("""
                DELETE FROM purchase_order_item
                WHERE order_id IN (
                    SELECT order_id FROM purchase_order WHERE customer_ref = ?
                )
                """, customerRef);
        jdbc.update(
                "DELETE FROM purchase_order WHERE customer_ref = ?",
                customerRef);
        jdbc.update(
                "DELETE FROM product_stock WHERE sku IN (?, ?)",
                skuA, skuZ);
    }

    @Test
    void insufficientSecondSkuRollsBackFirstReservation() {
        assertThrows(InsufficientStockException.class,
                () -> service.placeOrder(
                        customerRef,
                        List.of(
                                new PurchaseLine(skuA, 2),
                                new PurchaseLine(skuZ, 1))));

        Integer remaining = jdbc.queryForObject(
                "SELECT available_qty FROM product_stock WHERE sku = ?",
                Integer.class, skuA);
        assertEquals(8, remaining.intValue());

        Integer orders = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_order WHERE customer_ref = ?",
                Integer.class, customerRef);
        assertEquals(0, orders.intValue());
    }

    @Test
    void successfulCheckoutCommitsAllSteps() throws SQLException {
        // Thêm tồn kho cho SKU còn lại trong fixture riêng.
        jdbc.update(
                "UPDATE product_stock SET available_qty = 5 WHERE sku = ?",
                skuZ);

        long id = service.placeOrder(
                customerRef,
                List.of(
                        new PurchaseLine(skuA, 2),
                        new PurchaseLine(skuZ, 3)));
        assertTrue(id > 0);

        Integer remainingA = jdbc.queryForObject(
                "SELECT available_qty FROM product_stock WHERE sku = ?",
                Integer.class, skuA);
        Integer remainingZ = jdbc.queryForObject(
                "SELECT available_qty FROM product_stock WHERE sku = ?",
                Integer.class, skuZ);
        assertEquals(6, remainingA.intValue());
        assertEquals(2, remainingZ.intValue());

        Integer lines = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_order_item WHERE order_id = ?",
                Integer.class, id);
        assertEquals(2, lines.intValue());
    }
}
```

Ở đây các lần `jdbc.queryForObject(...)` trong test được chạy **sau khi method Service hoàn thành**, thông qua tương tác với DataSource bên ngoài transaction của Service. Vì không có transaction test bao quanh, các câu `SELECT` sẽ quan sát dữ liệu đã commit của Service hoặc trạng thái sau rollback theo isolation của DB.

Lớp test giả định:

- Môi trường CI đã chạy migration tạo ba bảng.
- Spring Boot Test có `@SpringBootTest` và Spring đang quản lý các bean `JdbcTemplate`, transaction manager, DAO, Service.
- Database test được **tách biệt**; không dùng production.
- JUnit 5 và Spring Boot Test là dependencies bổ sung.
- Các test không bị một tác vụ khác sửa các SKU theo token riêng.

Nếu test cleanup ném lỗi, phải cho test suite báo thất bại thay vì bỏ qua. Khi CI bị hủy đột ngột, `@AfterEach` có thể không chạy; một database/schema riêng có thể được hủy sau job để bảo đảm không để lại fixture. Với code nghiệp vụ mở nhiều connection hoặc có worker async, cần test bổ sung; hai test trên không chứng minh tất cả tình huống đồng thời.

### Điều gì đáng kiểm thử thêm?

| Tình huống | Kết quả mong muốn |
| --- | --- |
| SKU đầu tiên không tồn tại | Không giảm kho, không tạo đơn |
| SKU cuối không đủ số lượng | Các lần giảm kho trước rollback, không có đơn |
| DAO JDBC thuần ném `SQLException` | `rollbackFor` khiến kho và đơn cha được rollback |
| Lỗi `DataAccessException` ở `JdbcTemplate` | Spring rollback transaction |
| Service bị gọi qua `new CheckoutService(...)` thay proxy | Test nhận ra không có transaction advice như dự kiến |
| Transaction manager dùng sai DataSource | Test phát hiện dữ liệu commit một phần hoặc sự cố transaction |
| Hai checkout cạnh tranh một SKU | Không tồn kho âm; kết quả phụ thuộc khóa và DB isolation |
| Service tự gọi method `@Transactional` cùng class | Test lộ self-invocation bypass |
| Method bên trong dùng `REQUIRES_NEW` | Quan sát phần commit độc lập, không nhầm với use case nguyên tử |
| DB/driver nâng cấp | SQL, generated keys, rollback và lock vẫn đúng |

## 15. Những lỗi tích hợp thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ thêm `@Transactional` mà không có transaction manager hoặc proxy | Không có transaction như kỳ vọng | Xác minh bean/config và gọi qua Spring-managed bean |
| DAO tự `dataSource.getConnection()` và `close()` | Có thể lấy connection ngoài transaction đang bind | Dùng `JdbcTemplate` hoặc `DataSourceUtils`; chỉ dùng proxy DataSource phù hợp khi có chủ đích |
| DAO JDBC thuần tự `commit()` | Commit trước khi các DAO khác hoàn tất | Để Spring transaction manager quản lý transaction |
| Dùng `try-with-resources` cho connection do `DataSourceUtils` lấy | Có thể đóng connection đang thuộc transaction | Chỉ đóng statement/result set; gọi `releaseConnection` trong `finally` |
| Spring manager và DAO dùng DataSource không tương thích | Các thao tác không cùng transaction | Cấu hình chính xác cùng nguồn và transaction manager |
| Chỉ `@Transactional` mặc định với `SQLException` checked | Exception có thể không kích hoạt rollback | `rollbackFor = SQLException.class` hoặc dịch lỗi phù hợp |
| Bắt mọi exception trong Service rồi trả `false` | Spring có thể commit dữ liệu một phần | Rethrow hoặc đánh dấu rollback-only đúng cách |
| Gọi method giao dịch từ cùng bean qua `this` | Bypass proxy, không có advice riêng của method | Tách bean hoặc đặt boundary tại entry point |
| Tạo Service bằng `new` ngoài Spring | Annotation không được Spring xử lý | Dùng dependency injection |
| `@Async` chạy DAO trên thread khác | Không tham gia transaction JDBC của thread gốc | Thiết kế transaction riêng, outbox hoặc workflow async rõ ràng |
| Lạm dụng `REQUIRES_NEW` cho mỗi DAO | Commit một phần, có thể cạn pool | Dùng `REQUIRED` ở use case cần nguyên tử |
| Giả định `readOnly=true` cấm mọi `UPDATE` | Chỉ là hint; DB/driver có thể xử lý khác | Đặt read-only phù hợp và giữ kiểm soát SQL/quyền |
| Test `@Transactional` tự rollback rồi tuyên bố Service đã commit đúng | Không đo được commit thật của Service | Test ngoài transaction, cleanup theo fixture |
| Nhầm `DataAccessException` với `SQLException` checked | Rollback rule và xử lý lỗi không nhất quán | Hiểu loại exception ở từng DAO |
| Gọi HTTP/broker giữa transaction DB rồi tưởng rollback được | Side effect ngoài DB vẫn tồn tại | Outbox/idempotency/compensation |
| Retry mọi exception sau lỗi `commit` | Có thể tạo đơn trùng nếu commit thực tế đã xảy ra | Request ID và đối soát trạng thái |

## 16. Outbox, nhiều DataSource và giới hạn giao dịch cục bộ

Spring quản lý tốt **một giao dịch JDBC trên một nguồn dữ liệu**, nhưng không tự đảm bảo tất cả nguồn lực bên ngoài đều thuộc giao dịch đó.

### Tránh gửi sự kiện trước commit

```text
@Transactional CheckoutService
  stockDao.reserve(...)
  orderDao.insert(...)
  messageBroker.publish("OrderPlaced")  <-- gửi trước khi DB commit
  orderLineDao.insert(...)              <-- có thể lỗi
  ROLLBACK DB                           <-- không thu hồi được message
```

Một lựa chọn là **transactional outbox**:

```text
Cùng transaction Spring/JDBC:
  StockDao.reserve
  OrderDao.insert
  OrderLineDao.insert
  OutboxDao.insert(event)
             |
         DB commit
             |
   Worker riêng đọc outbox
             |
    Gửi event tới broker
             |
   Retry + deduplication/idempotency
```

`OutboxDao` phải dùng **cùng transaction**; có thể dùng `JdbcTemplate` như các DAO khác. Worker gửi event sau commit vẫn cần xử lý tình huống gửi lặp, vì xác nhận từ broker và cập nhật trạng thái outbox không nhất thiết là một thao tác nguyên tử.

### Hai database không tự thành một transaction

Nếu một Service dùng `ordersDataSource` và `billingDataSource`, rồi chỉ annotate `@Transactional` cho transaction manager của đơn hàng, thao tác ghi vào database thanh toán **không tự được enlist**. Muốn tính nguyên tử qua nhiều tài nguyên có thể cần JTA/XA khi hạ tầng hỗ trợ và chi phí phù hợp, hoặc một thiết kế saga/outbox với idempotency và compensation. Không trình bày `@Transactional` trên hai JDBC DataSource như một cam kết distributed transaction.

### `@Transactional(readOnly = true)`

`readOnly = true` là hint hữu ích cho các transaction truy vấn, tùy manager/DB có thể tối ưu hoặc từ chối thao tác ghi trong những điều kiện nhất định. **Không phải cơ chế phân quyền bắt buộc** thay thế SQL privilege hoặc kiểm tra nghiệp vụ. Với use case checkout cần `UPDATE`/`INSERT`, không đặt `readOnly = true`.

## 17. Câu hỏi và bài tập thực hành

**Bài 1 — Ai sở hữu transaction?** Một Service gọi ba DAO JDBC để trừ kho, tạo đơn và ghi dòng. Những lớp nào nên gọi `commit()`?

**Đáp án:** Với Spring transaction management, **Spring transaction manager** commit sau lời gọi Service được advice bằng `@Transactional` thành công. DAO và Service không tự gọi `Connection.commit()`.

**Bài 2 — Cùng DataSource là đủ?** `OrderLineDao` nhận `DataSource` giống `JdbcTemplate` nhưng lại dùng `dataSource.getConnection()` trực tiếp. Có thể chắc chắn nó đang dùng connection bound bởi Spring không?

**Đáp án:** Không. Dùng `DataSourceUtils.getConnection(...)`/`releaseConnection(...)` hoặc abstraction Spring được hỗ trợ. Có `TransactionAwareDataSourceProxy` nhưng không mặc định mọi DataSource là proxy đó.

**Bài 3 — Checked `SQLException`.** Method `@Transactional` gọi DAO JDBC thuần và ném `SQLException` sau khi đã giảm kho. Quy tắc mặc định Spring có luôn rollback không?

**Đáp án:** Không. Theo mặc định truyền thống, checked exception không tự kích hoạt rollback. Cấu hình `@Transactional(rollbackFor = SQLException.class)` hoặc áp dụng một chiến lược dịch exception phù hợp.

**Bài 4 — Self-invocation.** Một Spring bean có method `handle()` gọi trực tiếp `this.save()`, còn `save()` mang `@Transactional`. Nếu `handle()` không có transaction, transaction của `save()` có chắc được khởi tạo trong proxy mode không?

**Đáp án:** Không. Lời gọi nội bộ không đi qua proxy transaction. Tách method thành bean khác hoặc đặt boundary transaction ở method được gọi từ ngoài qua proxy.

**Bài 5 — `REQUIRES_NEW`.** `OrderLineDao` mở transaction độc lập với `REQUIRES_NEW` và commit, sau đó Service ngoài rollback. Dòng hàng có chắc được rollback theo Service không?

**Đáp án:** Không. Transaction độc lập có thể đã commit; nó còn có nguy cơ không nhìn thấy đơn cha chưa commit hoặc vi phạm foreign key. Với checkout nguyên tử, các DAO nên tham gia transaction của Service.

**Bài 6 — Test Service commit thật.** Vì sao một test `@Transactional` tự rollback ở cuối không chứng minh chính xác `CheckoutService.placeOrder` đã commit ở production?

**Đáp án:** Service `REQUIRED` có thể tham gia transaction test; commit thật nằm ở transaction của test chứ không phải Service. Kiểm thử commit nên chạy ngoài test transaction, dùng database test riêng và cleanup.

**Bài 7 — Connection và thread.** Service `@Transactional` tạo một `CompletableFuture` chạy DAO ở executor khác. DAO trong executor có tự nhận transaction JDBC đang bind ở thread Service không?

**Đáp án:** Không. Với Spring JDBC transaction imperative, context gắn với thread. Thiết kế job async với transaction riêng hoặc outbox, không truyền connection mutable giữa các thread.

**Bài 8 — Xử lý lỗi và rollback.** Vì sao bắt `InsufficientStockException` ngay trong `placeOrder` rồi `return -1` có thể nguy hiểm?

**Đáp án:** Vì proxy có thể thấy method trả về bình thường và cố commit những bước đã chạy. Cho exception đi ra khỏi transactional method hoặc đánh dấu rollback-only khi hợp đồng thật sự yêu cầu.

**Bài 9 — Kết quả commit chưa rõ.** Một lần đặt hàng ném exception vì mất kết nối tại thời điểm commit. Có thể gửi lại nguyên request một cách vô điều kiện không?

**Đáp án:** Không. Server có thể đã commit; cần idempotency key, unique constraint và đối soát kết quả để tránh tạo đơn/trừ kho hai lần.

**Bài 10 — Thực hành thay đổi DAO.** Chuyển `OrderLineDao` từ `DataSourceUtils` sang `JdbcTemplate.update(...)`. Cần giữ nguyên điều kiện gì để vẫn ở trong transaction checkout?

**Gợi ý:** `JdbcTemplate` phải dùng cùng DataSource phù hợp với transaction manager; code chạy đồng bộ trong lời gọi `@Transactional` qua Spring proxy; không tự mở transaction độc lập hoặc commit trong DAO. Viết integration test cho cả commit và rollback.

## Tổng kết

**Phối hợp DAO JDBC với giao dịch do Spring quản lý** dựa trên một nguyên tắc: **ranh giới transaction thuộc Service/use case; các DAO phải tham gia đúng kết nối do Spring quản lý**. Với `@Transactional` và `JdbcTransactionManager`/`DataSourceTransactionManager`, `JdbcTemplate` tự dùng connection phù hợp, còn JDBC thuần nên dùng `DataSourceUtils.getConnection`/`releaseConnection` thay vì mượn/đóng connection tùy tiện. Khi có `SQLException` checked, thiết lập `rollbackFor` hoặc dịch lỗi đúng; tránh nuốt exception, self-invocation, `REQUIRES_NEW` không đúng chỗ và async làm mất transaction context. Cuối cùng, kiểm chứng bằng integration test **gọi Service qua Spring proxy**, quan sát commit/rollback bằng database test thật, và dùng idempotency/outbox khi nghiệp vụ cần vượt khỏi ranh giới của một JDBC transaction.
