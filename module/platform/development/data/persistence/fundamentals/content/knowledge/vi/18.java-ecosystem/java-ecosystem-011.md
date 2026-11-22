# Lựa chọn công nghệ triển khai dựa trên yêu cầu thay vì mức độ tự động

Trong chương **Hệ sinh thái Java** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, câu hỏi quan trọng không phải là “framework nào viết ít mã nhất?” mà là **công nghệ nào giúp hệ thống lưu dữ liệu đúng, kiểm soát được và vận hành được dưới các yêu cầu thực tế?**

Java có nhiều cách làm việc với cơ sở dữ liệu: JDBC thuần, Spring JDBC, ORM như JPA/Hibernate, Spring Data JPA, công cụ SQL type-safe như jOOQ, SQL mapper như MyBatis và các API bất đồng bộ như R2DBC. Các lựa chọn này **không nằm trên một thang tuyến tính từ kém đến tốt theo số bước được tự động hóa**. Mỗi lựa chọn chuyển một số trách nhiệm giữa mã ứng dụng, thư viện, database và nhóm vận hành.

Một nền tảng persistence tốt phải phù hợp với mô hình dữ liệu, truy vấn, giao dịch, cô lập và kiểm soát đồng thời, quản lý kết nối, xử lý lỗi, tiến hóa schema, bảo mật, sao lưu và khả năng đo hiệu năng. Bài học này xây dựng phương pháp chọn công nghệ dựa trên **bằng chứng và ràng buộc** thay vì chạy theo sự tiện lợi hoặc độ phổ biến của framework.

## 1. Bắt đầu từ yêu cầu, không bắt đầu từ annotation

Giả sử nhóm phát triển đang chọn công nghệ cho dịch vụ đặt hàng. Hai phương án cùng được đề xuất:

- **Phương án A:** Spring Data JPA, chỉ vài repository interface, sinh nhiều truy vấn tự động.
- **Phương án B:** Spring JDBC hoặc jOOQ, câu SQL hiện rõ, cần viết mapping và truy vấn nhiều hơn.

Không thể kết luận A tốt hơn vì ít mã hơn, hoặc B tốt hơn vì kiểm soát SQL trực tiếp. Câu trả lời phụ thuộc vào những câu hỏi:

1. Mô hình dữ liệu có chủ yếu là các aggregate đơn giản hay nhiều truy vấn tổng hợp, join phức tạp?
2. Nghiệp vụ cần thao tác nguyên tử nào: lưu entity, `UPDATE ... WHERE ...`, khóa hàng, truy vấn có cấu trúc động, batch import?
3. Điều gì phải xảy ra **trong cùng transaction**, và điều gì xảy ra ở hệ thống ngoài?
4. Các bất biến trải trên một hàng hay nhiều hàng? Có rủi ro lost update, write skew, retry sau deadlock?
5. SLO về thông lượng và độ trễ là gì? Dữ liệu lớn đến đâu, có bao nhiêu kết nối, truy vấn chậm xuất hiện khi nào?
6. Lược đồ thay đổi với tần suất nào? Nhóm có kiểm soát migration và khả năng triển khai nhiều phiên bản cùng lúc không?
7. Thành viên hiểu cơ chế SQL, ORM, connection pool và công cụ quan sát tới đâu?
8. Khi xảy ra lỗi ở production, có thể xác định **câu SQL, thời gian chờ, transaction và nguyên nhân** không?

**Nguyên tắc:** mức tự động hóa chỉ là một biến số về chi phí phát triển; nó không thay thế độ đúng đắn, khả năng kiểm soát và tính phù hợp với workload.

## 2. Phân biệt những tầng của một lựa chọn công nghệ

Trước khi so sánh thư viện, cần phân biệt các thành phần hay bị gộp thành một cụm “chọn ORM”.

```text
API / Message Consumer / Batch Job
               |
               v
Application Service ─────── Domain Policy
     (ranh giới transaction, use case)
               |
               v
       Repository Port
               |
               v
  Persistence Adapter (JDBC / Spring JDBC /
       JPA / jOOQ / MyBatis / R2DBC)
               |
               v
   Driver / Connection Pool / Transaction Manager
               |
               v
  Database (schema, index, MVCC, WAL, constraints)
```

Có ít nhất năm quyết định khác nhau:

| Quyết định | Ví dụ | Không giải quyết thay cho |
| --- | --- | --- |
| **Database/engine** | PostgreSQL, MySQL/InnoDB | Thiết kế transaction của ứng dụng. |
| **Data-access API** | JDBC, R2DBC | Lựa chọn mapping entity hay truy vấn SQL. |
| **Mapping và query abstraction** | JPA/Hibernate, jOOQ, MyBatis, Spring JDBC | Bất biến nghiệp vụ và bảo đảm durability. |
| **Transaction management** | JDBC thủ công, Spring `@Transactional`, reactive transaction operator | Tự động chọn isolation đúng cho mọi use case. |
| **Kết nối và vận hành** | HikariCP, metrics, migration, backup | Tự động tối ưu truy vấn hoặc ngăn mọi lỗi cạnh tranh. |

Ví dụ **Spring Data JPA** thường chạy trên một JPA provider như Hibernate và sử dụng JDBC/connection pool bên dưới. **Spring JDBC** cũng dùng JDBC nhưng giảm boilerplate quản lý statement và mapping. **R2DBC** là một mô hình truy cập bất đồng bộ dựa trên driver tương ứng; không phải một cấu hình bật/tắt cho cùng kết nối JDBC.

Chọn một thư viện không cho phép bỏ qua các tầng còn lại.

## 3. Bức tranh các lựa chọn trong hệ sinh thái Java

| Công nghệ | Tư duy chính | Điểm mạnh | Điều cần tự chịu trách nhiệm |
| --- | --- | --- | --- |
| **JDBC thuần** | Viết SQL và điều khiển `Connection`/`Statement`/`ResultSet` trực tiếp. | Kiểm soát SQL, transaction và protocol rõ; ít abstraction. | Boilerplate, bind tham số, mapping, đóng tài nguyên, phân loại lỗi. |
| **Spring JDBC / JdbcTemplate** | SQL tường minh, framework hỗ trợ kết nối, callback, xử lý ngoại lệ. | Hợp use case CRUD và query rõ ràng; dễ xem câu SQL. | Mapping và hợp đồng repository vẫn cần thiết kế. |
| **JPA/Hibernate** | Quản lý entity và thay đổi trong persistence context. | Hợp domain có quan hệ entity, lifecycle, optimistic locking, dirty checking. | Fetch plan, N+1, lazy loading, flush, query sinh tự động, state của entity. |
| **Spring Data JPA** | Repository abstraction trên JPA provider. | Giảm mã CRUD và cung cấp cơ chế truy vấn repository thuận tiện. | Cần hiểu JPA/Hibernate bên dưới; method name không thay phân tích SQL. |
| **jOOQ** | Xây truy vấn SQL theo DSL có kiểu và metadata schema. | SQL phức tạp, join/CTE/window function, kiểm soát truy vấn; hỗ trợ code generation. | Phụ thuộc dialect, workflow generate schema, mapping/domain vẫn tự quyết. |
| **MyBatis** | Khai báo SQL tường minh và ánh xạ sang object. | Chủ động truy vấn; thích hợp hệ thống SQL-first hoặc nhiều stored procedure. | SQL/mapping có thể phân tán; phải giữ đồng bộ với schema và test. |
| **R2DBC** | Data access bất đồng bộ theo API reactive. | Hợp pipeline bất đồng bộ có nhu cầu end-to-end non-blocking và driver phù hợp. | Quản lý transaction/reactive context, driver support, debugging, không được dùng JDBC blocking trong chuỗi reactive. |

Đây là **đặc điểm khái quát**, không phải bảng xếp hạng. Tính năng, dialect, API hoặc điều khoản sử dụng của từng phiên bản thư viện có thể khác; khi triển khai cần kiểm tra khả năng tương thích với JDK, Spring, driver, database và yêu cầu bản quyền thực tế.

Một hệ thống còn có thể dùng **kết hợp các lựa chọn**: JPA cho aggregate đơn giản, jOOQ hoặc Spring JDBC cho báo cáo, truy vấn đặc biệt hay cập nhật có điều kiện. Sự kết hợp có ích khi ranh giới transaction, quản lý kết nối và trách nhiệm cập nhật dữ liệu được xác định rõ, chứ không phải mỗi nhóm tự chọn một thư viện khác nhau.

## 4. Dùng bài toán cụ thể làm phép thử lựa chọn

Xét một API giữ hàng cho sản phẩm đang bán. Bất biến cần giữ là:

> Một yêu cầu chỉ được giữ số lượng nguyên dương; sản phẩm phải còn bán; tồn kho sau cập nhật không âm; cùng mã yêu cầu chỉ được áp dụng một lần.

Một bảng tối giản trên PostgreSQL:

```sql
CREATE TABLE inventory (
    sku       TEXT PRIMARY KEY,
    status    TEXT NOT NULL
              CHECK (status IN ('ACTIVE', 'INACTIVE')),
    available INTEGER NOT NULL CHECK (available >= 0),
    version   BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE reservations (
    request_id UUID PRIMARY KEY,
    sku        TEXT NOT NULL REFERENCES inventory(sku),
    quantity   INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO inventory(sku, status, available, version)
VALUES ('BOOK-1', 'ACTIVE', 5, 0);
```

Nếu hai request cùng muốn giữ 4 đơn vị, một quy trình “`SELECT available`, kiểm tra trong Java, rồi `UPDATE` không điều kiện” có thể cho hai yêu cầu đều tin là đủ hàng. Bất kể dùng JDBC hay ORM, **câu hỏi đầu tiên là giao thức ghi có bảo vệ điều kiện ở thời điểm cạnh tranh hay không**.

Một câu SQL có điều kiện:

```sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE sku = :sku
  AND status = 'ACTIVE'
  AND available >= :quantity;
```

Trong PostgreSQL ở mức `READ COMMITTED`, khi hai giao dịch cạnh tranh trên cùng một hàng, thao tác đến sau có thể đợi và kiểm tra lại điều kiện trên trạng thái phù hợp. Sau lần giữ 4 đầu tiên, tồn kho còn 1; lần tiếp theo không được trừ thêm 4. Ứng dụng phải kiểm tra **số hàng cập nhật = 1**; kết quả 0 không phải thành công.

Nếu thao tác còn tạo hàng `reservations`, hai bước cần trong **cùng transaction**. Nếu commit bị mất phản hồi, phải đối soát bằng `request_id` trên nguồn có thẩm quyền; chỉ dùng điều kiện tồn kho không đủ để ngăn cùng request được xử lý lặp.

Đó là **hợp đồng nghiệp vụ và persistence**, không phải chi tiết độc quyền của framework nào. Những phần sau minh họa cách các công nghệ thể hiện hợp đồng này.

## 5. JDBC thuần: khi cần nhìn rõ từng bước

JDBC cung cấp API trực tiếp cho `Connection`, `PreparedStatement` và `ResultSet`. Nó phù hợp khi số câu SQL không nhiều, có yêu cầu kiểm soát rõ, hoặc cần hiểu cách transaction và connection hoạt động trước khi thêm abstraction.

Ví dụ cập nhật có điều kiện kết hợp ghi một reservation trong cùng transaction:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class JdbcReservationWriter {
    private final DataSource dataSource;

    public JdbcReservationWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean reserve(UUID requestId, String sku, int quantity)
            throws SQLException {
        if (requestId == null || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid reservation");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int updated;
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE inventory " +
                        "SET available = available - ?, version = version + 1 " +
                        "WHERE sku = ? AND status = 'ACTIVE' AND available >= ?")) {
                    statement.setInt(1, quantity);
                    statement.setString(2, sku);
                    statement.setInt(3, quantity);
                    updated = statement.executeUpdate();
                }

                if (updated != 1) {
                    connection.rollback();
                    return false;
                }

                try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO reservations(request_id, sku, quantity) " +
                        "VALUES (?, ?, ?)")) {
                    statement.setObject(1, requestId);
                    statement.setString(2, sku);
                    statement.setInt(3, quantity);
                    if (statement.executeUpdate() != 1) {
                        throw new SQLException("Reservation not inserted");
                    }
                }

                connection.commit();
                return true;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
```

Điểm mạnh là mọi câu lệnh và ranh giới transaction **hiện rõ**. Tuy nhiên, ví dụ trên **chưa phải API idempotent hoàn chỉnh**: nếu gửi lặp cùng `requestId` và gặp lỗi unique, phải rollback rồi đối soát bản ghi đã commit, so sánh payload và trả kết quả cũ. Nếu mất phản hồi của `commit()`, cố gọi `rollback()` không chứng minh commit đã thất bại; vẫn cần đối soát trước khi phát lại thao tác.

Những việc dễ sai khi viết JDBC thuần:

- Quên `close()` và gây rò rỉ kết nối trong pool.
- Quên đặt `autoCommit=false` khi có nhiều câu ghi phải nguyên tử.
- Bỏ qua số hàng trả về từ `executeUpdate()`.
- Ghép chuỗi SQL thay vì bind bằng `PreparedStatement`.
- Không phân biệt lỗi constraint, deadlock, serialization failure và mất kết nối.
- Giữ kết nối trong lúc gọi HTTP hoặc xử lý tác vụ không liên quan database.

**Khi nên cân nhắc:** các ứng dụng nhỏ, thao tác SQL rất đặc thù, tài nguyên hạn chế, hoặc mô-đun có lợi từ việc kiểm soát transaction trực tiếp. Khi số lượng câu SQL và mapping tăng, một abstraction như Spring JDBC có thể giảm công việc lặp lại.

## 6. Spring JDBC: SQL tường minh, giảm mã hạ tầng

`JdbcTemplate` giúp thực hiện SQL, bind tham số, ánh xạ dòng kết quả và phối hợp với transaction management của Spring. Nó thích hợp nếu nhóm muốn **kiểm soát SQL** nhưng không muốn viết nhiều `try-with-resources` cho mỗi truy vấn.

Một adapter ngắn cho thao tác giữ tồn kho:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class StockJdbcRepository {
    private final JdbcTemplate jdbc;

    public StockJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean decrementIfAvailable(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        int changed = jdbc.update(
            "UPDATE inventory " +
            "SET available = available - ?, version = version + 1 " +
            "WHERE sku = ? AND status = 'ACTIVE' AND available >= ?",
            quantity, sku, quantity
        );
        return changed == 1;
    }
}
```

Nếu cùng use case còn `INSERT reservations`, application service có thể đặt `@Transactional` quanh cả hai thao tác, **với điều kiện các repository dùng cùng transaction manager và nguồn kết nối phù hợp**.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;

@Service
public class ReserveStockService {
    private final StockJdbcRepository stock;
    private final ReservationJdbcRepository reservations;

    public ReserveStockService(
            StockJdbcRepository stock,
            ReservationJdbcRepository reservations) {
        this.stock = stock;
        this.reservations = reservations;
    }

    @Transactional
    public void reserve(UUID requestId, String sku, int quantity) {
        if (!stock.decrementIfAvailable(sku, quantity)) {
            throw new IllegalStateException("Cannot reserve stock");
        }
        reservations.insert(requestId, sku, quantity);
        // Chỉ thành công sau khi transaction được commit.
    }
}
```

Trong ví dụ, `ReservationJdbcRepository` là một adapter giả định có phương thức `insert(...)` ghi hàng reservation; cần triển khai adapter đó và quy trình idempotency trước khi đưa vào sản phẩm. Không nên xem hai đoạn mã là một ứng dụng đầy đủ có thể biên dịch độc lập.

**Giá trị của Spring JDBC nằm ở việc giảm boilerplate**, không phải “SQL đơn giản sẽ tự động tối ưu”. Bạn vẫn phải chọn index, viết câu `WHERE` đúng, phân tích execution plan, xác định transaction và kiểm soát concurrency.

## 7. JPA/Hibernate: quản lý entity và persistence context

JPA phù hợp khi domain thao tác nhiều **entity có vòng đời**, quan hệ, lazy/eager loading và thay đổi object theo một unit of work. Hibernate triển khai JPA và hỗ trợ persistence context cùng dirty checking: thay đổi của managed entity có thể được đồng bộ thành SQL khi flush.

Ví dụ entity dùng version:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory")
public class InventoryItem {
    public enum Status { ACTIVE, INACTIVE }

    @Id
    private String sku;

    @Enumerated(EnumType.STRING)
    private Status status;

    @Column(nullable = false)
    private int available;

    @Version
    private long version;

    protected InventoryItem() {}

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Invalid quantity");
        }
        if (status != Status.ACTIVE || available < quantity) {
            throw new IllegalStateException("Not reservable");
        }
        available -= quantity;
    }
}
```

Một service có thể đọc entity trong transaction và thay đổi bằng method domain; JPA provider phát hiện thay đổi rồi tạo SQL khi flush/commit.

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaInventoryService {
    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void reserve(String sku, int quantity) {
        InventoryItem item = entityManager.find(InventoryItem.class, sku);
        if (item == null) {
            throw new IllegalArgumentException("Unknown SKU");
        }
        item.reserve(quantity);
        // @Version giúp phát hiện một số cập nhật cạnh tranh
        // cùng entity khi provider flush/commit.
    }
}
```

Với hai transaction cùng đọc version 0 và sửa cùng hàng, cơ chế `@Version` thường khiến một transaction gặp xung đột optimistic locking; transaction lỗi cần rollback. Tuy nhiên:

- `@Version` **không tự ngăn write skew** nếu hai giao dịch sửa **hai hàng khác nhau** nhưng phá vỡ một bất biến chung.
- Một đoạn code chỉ dựa vào version trong memory của managed entity **không tự so khớp phiên bản client đã đọc từ request trước**; với form sửa lâu, phải mang `expectedVersion` và kiểm tra rõ ràng.
- Bulk JPQL/SQL update hoặc các đường ghi ngoài ORM có thể **bỏ qua** quy trình tăng version tự động; cần thiết kế giao thức đồng nhất.
- Dòng SQL và thời điểm thực thi có thể khác vị trí setter trong mã; lỗi có thể xuất hiện tại `flush()` hoặc `commit()`.
- Quan hệ lazy loading và fetch plan không phù hợp có thể gây **N+1 query** hoặc giữ transaction mở quá lâu.

**JPA không làm database biến mất khỏi thiết kế.** Nhóm vẫn cần hiểu transaction, isolation, chỉ mục, constraint, generated SQL và cách session/persistence context hoạt động.

### Spring Data JPA có thêm gì?

Spring Data JPA cung cấp repository abstraction, các phương thức thao tác entity phổ biến và cách mô tả truy vấn thuận tiện. Điều đó giảm số lớp code lặp lại, nhưng **không bỏ các đặc tính JPA/Hibernate bên dưới**. Một phương thức truy vấn nhìn rất ngắn vẫn có thể tạo nhiều SQL hoặc đọc lượng dữ liệu lớn.

Nếu dùng `save(entity)` cho mọi thao tác, hãy kiểm tra xem đó là một thao tác ghi **phù hợp với bất biến nghiệp vụ** hay chỉ thuận tiện để lưu object. Với giữ tồn kho, điều kiện ngay tại lệnh cập nhật hoặc chiến lược optimistic/pessimistic locking cần được xác định; không mặc định `save` thay cho quyết định transaction.

## 8. jOOQ và MyBatis: khi SQL là một phần quan trọng của thiết kế

Không ít ứng dụng có workload SQL phức tạp: nhiều join, CTE, aggregation, window function, truy vấn thống kê hoặc cập nhật hàng loạt. Khi đó, việc xem SQL như một ngôn ngữ chính thức có thể đơn giản hơn việc ép mọi truy vấn vào object graph.

### jOOQ: dựng SQL có cấu trúc và kiểu

jOOQ cho phép xây truy vấn bằng DSL Java và có thể sinh metadata/type từ schema. Ví dụ giả định đã code-generate bảng `INVENTORY` với những cột có kiểu tương ứng:

```java
// Ví dụ minh họa jOOQ; INVENTORY là bảng được code-generate.
int changed = dsl.update(INVENTORY)
    .set(INVENTORY.AVAILABLE, INVENTORY.AVAILABLE.minus(quantity))
    .set(INVENTORY.VERSION, INVENTORY.VERSION.plus(1L))
    .where(INVENTORY.SKU.eq(sku))
    .and(INVENTORY.STATUS.eq("ACTIVE"))
    .and(INVENTORY.AVAILABLE.ge(quantity))
    .execute();

if (changed != 1) {
    throw new IllegalStateException("Cannot reserve stock");
}
```

Ở đây `dsl` là `DSLContext` được cấu hình trước, còn code chỉ minh họa hình dạng truy vấn, không phải chương trình độc lập. API cụ thể và kiểu được sinh phụ thuộc dialect, cách code generation và phiên bản jOOQ. Transaction quản lý riêng bằng Spring hoặc cơ chế của jOOQ; **việc `execute()` trả 1 chưa có nghĩa toàn bộ use case đã commit**.

Lợi ích đáng cân nhắc là mối liên kết giữa schema và code query, khả năng diễn đạt SQL phức tạp và kiểm soát câu lệnh. Đổi lại, nhóm phải xây quy trình generate type cùng migration, hiểu dialect và quản lý mapping sang domain model. Với ứng dụng chỉ có vài thao tác CRUD, các bước đó có thể không đáng chi phí.

### MyBatis: viết SQL chủ động, ánh xạ bằng mapper

Một mapper có thể mô tả câu SQL trực tiếp:

```java
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

public interface InventoryMapper {
    @Update("""
        UPDATE inventory
        SET available = available - #{quantity},
            version = version + 1
        WHERE sku = #{sku}
          AND status = 'ACTIVE'
          AND available >= #{quantity}
        """)
    int reserve(
        @Param("sku") String sku,
        @Param("quantity") int quantity
    );
}
```

MyBatis có thể sử dụng annotation hoặc XML mapper, phù hợp nơi nhóm muốn SQL rõ ràng mà vẫn có mapping thuận tiện. Đừng để logic nghiệp vụ bị rải giữa nhiều XML mapper bằng những điều kiện khác nhau; application service vẫn phải sở hữu use case và transaction.

**So sánh:** jOOQ thường nhấn mạnh xây dựng SQL qua DSL có kiểu và metadata schema, trong khi MyBatis thường nhấn mạnh câu SQL do lập trình viên khai báo và ánh xạ kết quả. Cả hai yêu cầu hiểu SQL thực thi và chiến lược transaction.

## 9. R2DBC: reactive không đồng nghĩa database nhanh hơn

R2DBC cung cấp cách làm việc với relational database qua API bất đồng bộ, có driver và hệ sinh thái riêng. Nó có thể phù hợp khi ứng dụng đã xử lý end-to-end theo reactive streams, có nhiều thời gian chờ I/O và cần tránh giữ thread trong lúc đợi kết quả.

Nhưng phải phân biệt:

- **Non-blocking I/O** giảm việc một thread phải chờ I/O; nó **không tăng số lõi CPU, tốc độ WAL hoặc throughput vật lý** của database.
- **Backpressure** ở pipeline không tự động ngăn quá tải DB nếu ứng dụng tạo quá nhiều truy vấn đồng thời; vẫn cần giới hạn concurrency và pool.
- **R2DBC transaction** dùng context/phạm vi reactive riêng; không nên giả định `@Transactional` kiểu imperative và `ThreadLocal` hoạt động như JDBC trong mọi chuỗi reactive.
- Trộn một JDBC blocking call vào event-loop/reactive pipeline có thể chặn luồng điều phối và đánh mất lợi ích bất đồng bộ.
- Chức năng driver, dialect, batch, kiểu dữ liệu, exception mapping và công cụ giám sát phải được đánh giá trên các phiên bản đang dùng.

Ví dụ phác thảo theo Spring R2DBC:

```java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public final class ReactiveStockRepository {
    private final DatabaseClient client;

    public ReactiveStockRepository(DatabaseClient client) {
        this.client = client;
    }

    public Mono<Boolean> reserve(String sku, int quantity) {
        if (quantity <= 0) {
            return Mono.error(new IllegalArgumentException("Invalid quantity"));
        }
        return client.sql("""
                UPDATE inventory
                SET available = available - :qty,
                    version = version + 1
                WHERE sku = :sku
                  AND status = 'ACTIVE'
                  AND available >= :qty
                """)
            .bind("qty", quantity)
            .bind("sku", sku)
            .fetch()
            .rowsUpdated()
            .map(rows -> rows == 1L);
    }
}
```

Cách bind tên, kiểu trả về và API có thể khác theo phiên bản Spring/R2DBC; ví dụ chỉ mô tả thao tác cập nhật. Nếu use case còn tạo reservation, cả hai thao tác phải được bao trong **cùng reactive transaction** bằng cơ chế hỗ trợ, và chỉ công bố thành công sau khi commit. Không đặt `subscribe()` thủ công để chạy riêng một câu lệnh rồi giả định nó vẫn thuộc transaction của pipeline gọi.

**Chọn R2DBC** khi đã có yêu cầu và năng lực vận hành reactive rõ ràng, không chỉ vì “non-blocking” nghe tiên tiến hơn JDBC.

## 10. Ma trận yêu cầu: công nghệ nào phù hợp với dạng workload nào?

Thay vì xếp hạng công nghệ bằng một điểm tổng cố định, hãy đánh dấu mức phù hợp **tương đối** cho từng loại tác vụ và xác minh bằng thử nghiệm:

| Yêu cầu chủ đạo | Ứng viên nên khảo sát trước | Điều cần xác minh |
| --- | --- | --- |
| CRUD entity có vòng đời, nhiều quan hệ và thay đổi object | JPA/Hibernate, Spring Data JPA | Fetch plan, N+1, flush, version, migration. |
| Giao dịch nhỏ với nhiều câu cập nhật có điều kiện rõ ràng | Spring JDBC, JDBC, jOOQ, MyBatis | Số hàng cập nhật, isolation, retry, mapping lỗi. |
| SQL phân tích, join/CTE/window function, truy vấn động phức tạp | jOOQ, Spring JDBC, MyBatis; có thể dùng native SQL của JPA | SQL và plan rõ, type/mapping, khả năng kiểm thử với DB thật. |
| Một batch import nhiều dữ liệu | JDBC batching, Spring JDBC, jOOQ, MyBatis hoặc công cụ import của DB | Memory, transaction size, throughput, idempotency, recovery. |
| Ứng dụng dùng JPA sẵn, thỉnh thoảng có truy vấn hiệu năng đặc thù | JPA cho nghiệp vụ chính + SQL-focused adapter cho truy vấn nóng | Nhất quán transaction/persistence context và trách nhiệm cập nhật. |
| Pipeline end-to-end reactive với nhiều I/O, driver phù hợp | R2DBC và reactive transaction stack | Không có blocking call, concurrency limit, tính năng driver và debugging. |
| Domain cực kỳ đơn giản, nhóm nhỏ, ít query | JDBC hoặc Spring JDBC, JPA nếu đã có nền tảng phù hợp | Tổng chi phí vận hành và học công nghệ, không chỉ số dòng mã. |
| Nghiệp vụ có nhiều bất biến xuyên hàng/dịch vụ | Bất kỳ lựa chọn nào **có transaction/giao thức đúng** | SERIALIZABLE/locking, outbox/saga, idempotency; ORM không quyết định thay. |

Một truy vấn có thể chuyển từ JPA sang SQL tường minh mà không cần viết lại toàn bộ domain. Tuy nhiên, dùng song song nhiều adapter **không nên** tạo nhiều nơi cập nhật cùng entity theo những quy tắc concurrency khác nhau.

## 11. Chọn theo transaction và tính đúng đắn dữ liệu

Một tiêu chí khó nhìn từ demo framework là **nơi kết thúc transaction và cách phát hiện xung đột**.

### 11.1. Mỗi thao tác ghi phải có một ranh giới rõ

Giữ hàng và ghi reservation phải cùng commit hoặc cùng rollback; điều đó đúng với JDBC, Spring JDBC, JPA, jOOQ, MyBatis và R2DBC. Nếu một repository tự mở connection ngoài transaction manager, một phần cập nhật có thể commit độc lập và tạo dữ liệu lệch.

Với JPA, lỗi có thể chỉ xuất hiện khi flush/commit, không phải lúc gọi setter. Với SQL tường minh, `UPDATE` trả thành công vẫn có thể bị rollback khi bước tiếp theo thất bại. **Không được trả “đã lưu bền vững” chỉ từ kết quả một câu SQL nếu transaction chưa commit.**

### 11.2. Optimistic và pessimistic locking không do tên framework quyết định

Đối với cập nhật cùng một hàng, có thể dùng:

- `UPDATE ... WHERE version = ?` và tăng version trong cùng lệnh.
- `@Version` trong JPA trên managed entity, với mọi đường ghi cùng tuân thủ.
- `SELECT ... FOR UPDATE` hoặc cơ chế khóa được DB hỗ trợ khi cần bảo vệ một chuỗi đọc–quyết định–ghi.
- `UPDATE ... WHERE available >= ?` để cưỡng chế trực tiếp bất biến một hàng.

Với bất biến nhiều hàng, ví dụ phải luôn còn ít nhất một bác sĩ trực, hai giao dịch có thể cùng sửa hai hàng khác nhau và phá vỡ quy tắc (*write skew*). Lúc đó cần thiết kế như `SERIALIZABLE`, khóa cùng hàng đại diện, hay mô hình bộ đếm có điều kiện. **ORM, query builder hay mapper đều không tự thay thế phân tích lịch giao dịch.**

### 11.3. Retry phải gắn với ranh giới nghiệp vụ

Deadlock, serialization failure, timeout query và mất kết nối quanh commit là những tình huống khác nhau. Ví dụ PostgreSQL `40001` thường yêu cầu chạy lại **toàn bộ transaction** đã bị từ chối; còn khi client mất ACK của `COMMIT`, trạng thái có thể chưa rõ và cần đối soát bằng `request_id`.

Một thư viện có thể chuyển exception sang kiểu thuận tiện hơn nhưng **không tự biết** việc thử lại có khiến khách hàng bị thu tiền hai lần hay không. Idempotency key, ràng buộc unique, outbox và khả năng truy vấn kết quả là quyết định của use case và kiến trúc, không phải thuộc tính của số lượng annotation.

## 12. SQL được tạo tự động vẫn cần được kiểm tra

Tự động sinh SQL làm giảm số dòng mã, nhưng không bảo đảm câu SQL có execution plan tốt hoặc chỉ thực thi một lần.

### N+1 query

Giả sử truy vấn lấy 100 đơn hàng, sau đó vòng lặp đọc danh sách dòng hàng của từng đơn:

```text
SELECT orders ...                      -- 1 truy vấn
SELECT order_lines WHERE order_id = 1  -- truy vấn 2
SELECT order_lines WHERE order_id = 2  -- truy vấn 3
...
SELECT order_lines WHERE order_id = 100

Tổng gần 101 lượt truy vấn thay vì một số ít truy vấn có kế hoạch tải dữ liệu hợp lý.
```

Đây là một kiểu lỗi thường gặp khi ORM lazy-load quan hệ trong vòng lặp; SQL tường minh cũng có thể mắc lỗi tương tự nếu gọi repository một lần cho mỗi hàng. Cách xử lý có thể là fetch join, entity graph, batch fetching, projection, truy vấn gom dữ liệu hoặc thay đổi thiết kế API.

### Không đo bằng cảm giác

Với mọi lựa chọn, cần quan sát:

1. Số câu SQL cho mỗi request; có round trip ngoài ý muốn không?
2. Thời gian thực thi thực tế, thời gian chờ khóa/I/O và độ trễ p95/p99.
3. Số hàng đọc, dữ liệu truyền về, chi phí mapping và dung lượng bộ nhớ.
4. Index được sử dụng hay truy vấn đang quét nhiều bản ghi?
5. Thời gian giữ connection và transaction; pool đang chờ hay DB đã bão hòa?
6. Số transaction bị retry, lỗi constraint và số lần commit không rõ kết quả.

Ví dụ với PostgreSQL, có thể phân tích truy vấn bằng `EXPLAIN (ANALYZE, BUFFERS)` **trong môi trường phù hợp**. Lưu ý `ANALYZE` thực sự chạy câu lệnh; với câu DML có tác dụng phụ, cần quy trình kiểm thử/rollback phù hợp, không chạy tùy tiện trên production.

**Một thao tác SQL viết tay không mặc nhiên nhanh hơn ORM.** Nếu query và kế hoạch thực thi giống nhau, hiệu năng có thể tương tự; khác biệt thường nằm ở số lượt query, hành vi fetch/flush, mapping và cách ứng dụng giữ tài nguyên.

## 13. Mô hình dữ liệu, migration và mức khóa vào công nghệ

Việc chọn thư viện ảnh hưởng tới cách nhóm tiến hóa schema:

- **JPA entity:** mapping có thể thể hiện rõ quan hệ và ràng buộc ở lớp ứng dụng, nhưng không nên coi việc tự động cập nhật schema là chiến lược migration an toàn cho production.
- **jOOQ code generation:** type/schema ở mã Java cần được sinh lại đồng bộ với migration; nếu thiếu pipeline này, lỗi không khớp schema có thể xuất hiện muộn.
- **MyBatis/SQL tường minh:** câu SQL và mapping phải được cập nhật khi cột/kiểu đổi; cần test truy vấn thật.
- **JDBC/Spring JDBC:** kiểm soát trực tiếp nhưng dễ thiếu một đường code khi schema đổi; contract test và integration test rất quan trọng.
- **R2DBC:** phải kiểm tra hỗ trợ kiểu dữ liệu, driver và transaction theo nền tảng mà ứng dụng triển khai.

Một quy trình migration có kiểm soát thường dùng công cụ như Flyway hoặc Liquibase và các bước **mở rộng → chuyển đổi dữ liệu → chuyển code → thắt ràng buộc**, tùy yêu cầu. Ví dụ đổi tên cột khi đang rolling deployment cần để cả phiên bản ứng dụng cũ và mới hoạt động trong giai đoạn chuyển tiếp.

**Nguyên tắc:** schema là tài sản dùng chung của hệ thống, không phải chỉ là phản chiếu tự động của class Java. Ràng buộc như `CHECK`, `UNIQUE`, `FOREIGN KEY` và index phải được thiết kế, version-control, kiểm thử và triển khai có kế hoạch.

### Khóa chặt vào công nghệ có đáng lo?

Công cụ càng tiện lợi, dự án có thể càng dựa nhiều vào lifecycle hoặc tính năng riêng của nó. Nhưng **giảm phụ thuộc framework bằng cách tự viết lại toàn bộ ORM cũng không mặc nhiên có lợi**.

Khi cân nhắc khả năng thay thế, hãy đánh giá:

- Domain model có phụ thuộc trực tiếp API persistence hay không.
- Repository interface có thể diễn đạt hợp đồng nghiệp vụ mà không lộ `EntityManager` hoặc `ResultSet` không.
- SQL đặc thù dialect tập trung ở adapter hay rải qua service.
- Mức độ cần thiết của tính năng riêng, chi phí kiểm thử và giá trị nó mang lại.
- Có lý do kinh doanh hoặc vận hành thực tế để thay công nghệ trong vòng đời sản phẩm không.

Không phải hệ thống nào cũng cần một tầng trừu tượng “đổi được database trong một ngày”. Một số tính năng rất quan trọng của PostgreSQL hoặc MySQL đáng được dùng có chủ đích, miễn nhóm chấp nhận và kiểm soát sự phụ thuộc đó.

## 14. Vận hành, bảo mật và kết nối là tiêu chí bắt buộc

Framework dữ liệu chỉ là một phần của đường ghi. Một ứng dụng sử dụng ORM tối tân vẫn có thể thất bại vì connection pool cạn, câu SQL không có timeout, quyền database quá rộng hoặc backup chưa từng được restore.

### Kết nối và tài nguyên

Khi lựa chọn stack, hãy xác định:

- Driver và pool được hỗ trợ có tương thích database/version không?
- Bao nhiêu kết nối tối đa **trên mỗi instance**, tổng số ở giờ cao điểm/rolling deployment là bao nhiêu?
- Application mượn kết nối trong bao lâu và có mở transaction xuyên API call không?
- Có thiết lập timeout cho mượn kết nối, statement, lock và transaction phù hợp không?
- Hệ thống dùng primary/replica thế nào, có nguy cơ stale read không?
- Khi kết nối chết hoặc proxy failover, framework đưa ra ngoại lệ gì và làm sao phục hồi?

Với JDBC stack, HikariCP là lựa chọn pool thường gặp; với R2DBC, dùng cơ chế pooling tương thích reactive stack. **Không lấy cấu hình pool của JDBC áp dụng nguyên xi cho R2DBC** mà không kiểm tra ngữ nghĩa và thông số thực tế.

### Bảo mật

Mọi adapter phải dùng **bind parameter**, không ghép giá trị người dùng trực tiếp thành SQL; cấp quyền database tối thiểu cần thiết; quản lý credential qua cơ chế bảo mật; phân quyền API/domain và kiểm soát truy vấn theo tenant nếu có.

ORM không tự ngăn SQL injection khi dùng query động sai cách. SQL mapper cũng không an toàn nếu dùng cơ chế chèn nguyên văn chuỗi thay vì bind tham số. Với batch job hoặc stored procedure có quyền cao hơn, cần kiểm tra đường vượt quyền.

### Độ bền và khả năng phục hồi

Quyết định dữ liệu phải tồn tại sau crash/failover hay cần RPO/RTO bao nhiêu là trách nhiệm kiến trúc. Database WAL, chính sách flush, replication, backup/PITR và kiểm thử restore không thể được thay thế bằng annotation `@Transactional` hoặc thư viện mapper. Ranh giới commit và idempotency phải được kiểm thử ở tầng tích hợp.

## 15. Cách ra quyết định bằng một thử nghiệm nhỏ có đo lường

Thay vì tranh luận “Hibernate tiện hơn” hoặc “SQL thuần luôn nhanh hơn”, hãy chọn **hai hoặc ba ứng viên** thực sự phù hợp, rồi xây một thử nghiệm có cùng yêu cầu nghiệp vụ.

### Bước 1: Viết hợp đồng chức năng

Ví dụ:

> API nhận `request_id`, `sku` và `quantity`; chỉ giữ hàng đang bán, không trừ tồn kho âm; một request không được áp dụng hai lần; tạo reservation trong cùng transaction; trả kết quả có thể đối soát sau timeout.

Các test chức năng và dữ liệu thử phải giống nhau giữa các công nghệ.

### Bước 2: Chọn workload đại diện

Một bản thử phù hợp nên gồm ít nhất:

- CRUD đơn giản có quan hệ giữa bảng.
- Một câu update có điều kiện dưới cạnh tranh hai giao dịch.
- Một truy vấn nhiều join hoặc projection lớn.
- Một batch hoặc thao tác ghi số lượng lớn nếu đó là workload thật.
- Một lỗi commit/connection giả lập để kiểm tra quy trình đối soát.

Không nên benchmark chỉ bằng `SELECT 1` rồi suy ra hiệu năng của hệ thống đặt hàng.

### Bước 3: Đặt tiêu chí kiểm chứng

| Nhóm tiêu chí | Câu hỏi đánh giá |
| --- | --- |
| **Đúng đắn** | Có giữ được bất biến khi hai transaction cạnh tranh? Có xử lý timeout/commit không rõ? |
| **Hiệu năng** | Throughput, p95/p99 latency, số SQL/request, CPU, bộ nhớ, thời gian giữ connection? |
| **Truy vấn** | Có biểu diễn được SQL khó nhất mà vẫn kiểm soát execution plan? |
| **Năng suất** | Mức độ mã lặp lại, dễ kiểm thử, chi phí onboarding và review? |
| **Schema** | Migration, code generation, tương thích rollout, tránh schema drift? |
| **Vận hành** | Metrics, logging/tracing SQL, lỗi, timeout, pool, phục hồi? |
| **Khả năng tiến hóa** | Thay đổi chính sách hoặc câu query có lan rộng qua nhiều tầng không? |
| **Rủi ro phụ thuộc** | Tính năng chỉ có ở vendor/provider, giấy phép, compatibility và chi phí duy trì? |

### Bước 4: Đo trong điều kiện công bằng

Giữ tương đương database, schema, index, dữ liệu, loại instance, JDK, pool/connection budget, số client và tỷ lệ request. Khởi động hệ thống cho trạng thái ổn định trước khi so sánh. Đo cả khi tải vừa, sát ngưỡng bão hòa và khi có burst.

Nếu thử nghiệm A dùng một câu SQL còn B phát sinh 101 câu vì N+1, hãy ghi nhận **vì sao** khác biệt xuất hiện, tối ưu fetch plan phù hợp rồi đo lại. Kết quả tốt cần đi kèm code dễ review, test concurrency và quan sát được nguyên nhân, không chỉ một con số throughput.

### Bước 5: Ra quyết định có điều kiện

Ví dụ kết luận hợp lý là:

> “Dùng Spring Data JPA cho nhóm aggregate đơn giản vì giảm nhiều mã mapping; dùng jOOQ cho báo cáo có nhiều CTE và truy vấn động; giữ transaction trong application service; các cập nhật tồn kho được kiểm chứng bằng điều kiện SQL; dùng cùng migration pipeline và kiểm thử integration.”

Đây là một quyết định **theo đặc tính use case**, không phải “framework A thắng framework B trong mọi tình huống”.

## 16. Ba tình huống kiến trúc và cách chọn

### Tình huống A: hệ thống nội bộ CRUD ổn định

Ứng dụng quản lý hồ sơ với entity quan hệ tương đối đơn giản, ít truy vấn phân tích, tải vừa phải và đội ngũ đã quen Spring. **JPA/Hibernate cùng Spring Data JPA** có thể giảm mã đáng kể. Điều kiện là có chiến lược fetch, ranh giới transaction, validation/constraint, migration và test SQL thực tế. Đừng thêm jOOQ chỉ để thay mọi `findById` vốn đã rõ.

### Tình huống B: nền tảng xử lý đơn hàng tải lớn

Nghiệp vụ có tồn kho, hạn mức, chuyển trạng thái, retry, idempotency và điều kiện đồng thời. **Spring JDBC hoặc jOOQ cho các thao tác cập nhật có điều kiện** thường dễ biểu đạt hợp đồng SQL; vẫn có thể dùng JPA cho aggregate khác. Quan trọng nhất là thiết kế transaction, xử lý 0 hàng, unique request ID, kiểm tra version và benchmark lock/commit latency. Không chọn chỉ vì số dòng repository.

### Tình huống C: dịch vụ truy vấn báo cáo phức tạp

Yêu cầu gồm CTE, window function, join nhiều bảng, phân trang và projection rộng. **jOOQ hoặc SQL tường minh qua Spring JDBC/MyBatis** là ứng viên đáng khảo sát. Mô hình JPA vẫn có thể dùng cho thao tác ghi entity, nhưng đừng bắt một object graph tải rất nhiều dữ liệu chỉ để tạo một bảng báo cáo. Cần đo dữ liệu truyền về, chỉ mục và kế hoạch thực thi.

Trong cả ba trường hợp, một thư viện **đủ dùng, quen thuộc và có đường kiểm chứng rõ** thường phù hợp hơn một lựa chọn mới chỉ vì hứa hẹn tự động hóa nhiều hơn.

## 17. Các ngộ nhận cần tránh

| Nhận định | Điều cần hiểu |
| --- | --- |
| “Ít code repository nhất nghĩa là hệ thống tốt nhất.” | Năng suất chỉ là một tiêu chí; tính đúng đắn và vận hành có thể quan trọng hơn. |
| “JPA tự động ngăn mọi race condition.” | ORM không tự bảo vệ mọi bất biến, đặc biệt bất biến trên nhiều hàng. |
| “SQL viết tay chắc chắn nhanh hơn Hibernate.” | Phải so số truy vấn, execution plan, fetch và workload thực. |
| “Có `@Transactional` là dữ liệu không thể mất sau mọi sự cố.” | Độ bền phụ thuộc DB/WAL/flush/replication và hạ tầng. |
| “R2DBC reactive nên database xử lý được nhiều truy vấn hơn.” | Non-blocking không tăng tài nguyên CPU, I/O hoặc WAL của DB. |
| “Thêm connection pool lớn là đủ giải quyết DB chậm.” | Có thể chỉ tăng hàng đợi và tranh chấp trên server. |
| “Spring Data repository không cần xem SQL sinh ra.” | Phải quan sát N+1, query plan và số round trip. |
| “Có `@Version` thì batch job ghi trực tiếp không cần tăng version.” | Đường ghi ngoài ORM có thể phá giao thức optimistic locking. |
| “Thư viện mới nhất mặc định phù hợp với production.” | Compatibility, hỗ trợ, driver, migration và vận hành phải được xác minh. |
| “Có thể đổi database bất kỳ lúc nào nhờ ORM.” | Dialect, schema, transaction semantics và SQL đặc thù vẫn tạo phụ thuộc. |
| “Framework xử lý exception thì retry lúc nào cũng an toàn.” | Retry sau commit không rõ cần request ID và đối soát; không thể đoán từ exception. |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Một ứng dụng có nhiều entity liên quan và các API CRUD khá đơn giản. Có nên loại JPA chỉ vì SQL viết tay có vẻ kiểm soát tốt hơn không?

**Không mặc định.** Cần xét chi phí phát triển, truy vấn thực tế, khả năng kiểm thử và nhu cầu kiểm soát. JPA có thể phù hợp nếu mapping/fetch/transaction được quản lý tốt.

**Câu 2.** Một API dùng Spring Data JPA đọc tồn kho = 5 rồi hai request cùng mua 4. Việc repository `save(entity)` rất ngắn có bảo đảm tồn kho không âm không?

**Không đủ để kết luận.** Cần hiểu version/locking/transaction và ràng buộc DB. Có thể dùng câu cập nhật nguyên tử có điều kiện hoặc giao thức concurrency phù hợp.

**Câu 3.** Một truy vấn báo cáo dùng nhiều CTE và window function. Tiêu chí nào khiến nhóm nên cân nhắc jOOQ hoặc SQL tường minh?

**Khả năng diễn đạt, review, kiểm thử và tối ưu câu SQL thực tế**, cùng type/mapping và chi phí bảo trì. Không phải vì jOOQ mặc nhiên chạy nhanh hơn mọi truy vấn JPA.

**Câu 4.** Nếu pipeline sử dụng R2DBC nhưng một bước gọi JDBC đồng bộ trên event loop, có rủi ro gì?

Lời gọi JDBC **blocking** có thể chặn luồng xử lý reactive, làm tăng latency và giảm khả năng phục vụ. Cần đánh giá lại kiến trúc hoặc cách cô lập tác vụ blocking.

**Câu 5.** Vì sao phải kiểm thử hai transaction cạnh tranh trên DB thật thay vì chỉ mock repository?

Vì mock không mô phỏng đầy đủ khóa hàng, snapshot, isolation level, unique constraint, serialization failure và lịch commit thực tế.

**Câu 6.** Một request tạo đơn nhận timeout quanh `COMMIT`. Có thể dùng thư viện xử lý retry chung để phát lại với ID mới không?

**Không.** Commit có thể đã thành công. Phải dùng cùng request ID, cơ chế idempotency và đối soát kết quả trước khi quyết định thử lại.

**Câu 7.** Nhóm có thể dùng JPA và Spring JDBC trong cùng ứng dụng không?

**Có thể**, nếu phân định rõ trách nhiệm và giữ được transaction nhất quán. Cần tránh native SQL cập nhật dữ liệu trong khi persistence context JPA vẫn giữ bản cũ mà không có biện pháp đồng bộ/refresh phù hợp.

## Kết luận

**Chọn công nghệ persistence là chọn cách phân phối trách nhiệm, không phải chọn mức tự động hóa cao nhất.** JDBC, Spring JDBC, JPA/Hibernate, Spring Data JPA, jOOQ, MyBatis và R2DBC mỗi loại có điểm mạnh, giới hạn và chi phí riêng. Một quyết định tốt bắt đầu từ bất biến nghiệp vụ, dạng truy vấn, ranh giới transaction, workload, khả năng chẩn đoán và mức độ chấp nhận rủi ro.

Trong ứng dụng Java, hãy giữ domain và use case rõ ràng, buộc database cưỡng chế các điều kiện cần thiết, đo SQL thực thi, kiểm thử concurrency và thiết kế lỗi/retry/idempotency ngay từ đầu. Công nghệ phù hợp nhất là công nghệ giúp đội ngũ **chứng minh được dữ liệu đúng, hệ thống đáp ứng yêu cầu và có thể vận hành, tiến hóa an toàn** — dù một phần mã được sinh tự động hay được viết tường minh.
