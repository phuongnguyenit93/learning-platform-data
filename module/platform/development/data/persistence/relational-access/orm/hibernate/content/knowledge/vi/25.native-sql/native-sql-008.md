# doWork hoặc doReturningWork để làm việc với JDBC khi cần

Hibernate ORM giúp ứng dụng thao tác trên database qua entity, HQL/JPQL, Criteria API, native query và persistence context. Tuy nhiên, có những tác vụ cần sử dụng **JDBC trực tiếp**: gọi một hàm hoặc stored procedure đặc thù của database, làm việc với `PreparedStatement` hoặc `ResultSet` ở mức thấp, tận dụng một tính năng driver, thao tác với bảng tạm, hoặc thực hiện một đoạn SQL mà API truy vấn của ORM không biểu đạt thuận tiện.

Trong những trường hợp đó, Hibernate cung cấp hai phương thức trên `Session`:

~~~java
session.doWork(connection -> {
    // Thực hiện JDBC, không trả kết quả cho caller.
});

Result result = session.doReturningWork(connection -> {
    // Thực hiện JDBC và trả một giá trị Java.
    return someResult;
});
~~~

**Ý tưởng cốt lõi:** Hibernate đưa cho callback **JDBC Connection đang do Session quản lý**. Ta có thể thực hiện JDBC trên connection này trong cùng ngữ cảnh transaction mà Session tham gia, thay vì tự mở một connection không liên quan qua `DriverManager` hoặc một `DataSource` khác.

Nhưng quyền sở hữu tài nguyên **không chuyển sang callback**. Code của ứng dụng được phép đóng những `PreparedStatement` và `ResultSet` tự tạo, **không được tự đóng Connection, commit/rollback hoặc thay đổi auto-commit tùy tiện**. Và vì Hibernate không biết toàn bộ SQL được chạy trực tiếp bằng JDBC, ứng dụng phải suy nghĩ rõ ràng về **flush, entity state, first-level cache và second-level cache**.

Bài học này thuộc chương **SQL gốc** trong module *Data Persistence Relational Access ORM Hibernate*. Ví dụ sử dụng Java, Jakarta Persistence và Hibernate Session API. SQL có một số phần minh họa theo PostgreSQL và sẽ được đánh dấu rõ khi không portable.

## 1. JDBC nằm ở đâu trong kiến trúc Hibernate?

Một luồng làm việc thường có các tầng:

~~~text
Service / Application code
          |
          v
JPA EntityManager / Hibernate Session
          |
          +--> Persistence context
          |    - Managed entities
          |    - Dirty checking
          |    - Action queue / Flush
          |
          +--> HQL / JPQL / Criteria / Native SQL
          |
          v
Transaction coordinator / JDBC connection management
          |
          v
java.sql.Connection
          |
          +--> PreparedStatement / CallableStatement
          |    ResultSet / Database-specific JDBC API
          |
          v
Relational Database
~~~

Hibernate dùng JDBC để giao tiếp với database. `doWork` và `doReturningWork` cho ứng dụng mượn **connection phía dưới Session** thông qua một callback.

~~~java
session.doWork(connection -> {
    // connection đến từ Hibernate Session đang được sử dụng.
});
~~~

Nếu Session đang tham gia một transaction, JDBC work trên connection này được thực hiện trong **cùng ngữ cảnh transaction** tương ứng. Đây là khác biệt quan trọng so với việc tự mở connection mới:

~~~java
try (Connection other = dataSource.getConnection()) {
    // Connection khác có thể thuộc transaction khác.
}
~~~

Không được mặc định connection tự mở từ DataSource sẽ tự động cùng transaction và cùng persistence context với Hibernate Session. Trong ứng dụng container/framework, cách enlist connection có thể phụ thuộc transaction manager; `doWork` giúp sử dụng chính connection do Hibernate quản lý.

## 2. Hai API và giá trị trả về

Hibernate định nghĩa hai callback contract:

~~~java
package org.hibernate.jdbc;

@FunctionalInterface
public interface Work {
    void execute(Connection connection) throws SQLException;
}

@FunctionalInterface
public interface ReturningWork<T> {
    T execute(Connection connection) throws SQLException;
}
~~~

Đây là **chữ ký giản lược mang tính minh họa**; cách khai báo annotation hoặc chi tiết thư viện có thể thay đổi theo phiên bản, nhưng điểm chính là `Work` không trả giá trị, còn `ReturningWork<T>` trả một giá trị `T`.

Từ phía Session:

~~~java
void doWork(Work work);

<T> T doReturningWork(ReturningWork<T> work);
~~~

Một exception JDBC xảy ra trong callback có thể được Hibernate chuyển thành ngoại lệ Hibernate, thường là `HibernateException`/ngoại lệ JDBC được bọc phù hợp với provider.

### Bảng so sánh nhanh

| Thuộc tính | `doWork` | `doReturningWork` |
| --- | --- | --- |
| API | `Session.doWork(Work)` | `Session.doReturningWork(ReturningWork<T>)` |
| Kiểu callback | `Work` | `ReturningWork<T>` |
| Kết quả ở caller | `void` | `T` |
| Có truy cập JDBC Connection? | Có | Có |
| Có tự bắt đầu transaction? | Không nên dựa vào | Không nên dựa vào |
| Có tự refresh entity sau SQL? | Không | Không |
| Có tự đóng statement/result set? | Không; ứng dụng đóng tài nguyên mình tạo | Không; ứng dụng đóng tài nguyên mình tạo |
| Có được đóng Connection? | Không | Không |
| Trường hợp tiêu biểu | Gọi procedure, cập nhật JDBC, batch | Đếm hàng, lấy ID, đọc metadata, trả DTO |

### Quy tắc quyết định

**Nếu tác vụ chỉ cần hiệu ứng phụ, dùng `doWork`. Nếu tác vụ cần trả một giá trị, dùng `doReturningWork`.**

Không nên dùng `doWork` và gán kết quả vào biến bên ngoài chỉ để vượt qua việc callback không trả kết quả:

~~~java
AtomicReference<Long> holder = new AtomicReference<>();

session.doWork(connection -> {
    holder.set(42L);
});

Long result = holder.get();
~~~

Mẫu trên làm code phức tạp không cần thiết. Dùng:

~~~java
Long result = session.doReturningWork(connection -> 42L);
~~~

## 3. Mô hình dữ liệu minh họa

Giả sử ứng dụng quản lý sản phẩm và lịch sử điều chỉnh tồn kho:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE inventory_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    delta INTEGER NOT NULL,
    description VARCHAR(240) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Entity tối giản:

~~~java
package com.example.inventory.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Version
    private Long version;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public int getStockQuantity() {
        return stockQuantity;
    }

    public void changeStockQuantity(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("Tồn kho không được âm");
        }
        this.stockQuantity = value;
    }
}
~~~

Mục đích ví dụ là quan sát sự khác nhau giữa **ORM quản lý một Product entity** và **JDBC làm việc trực tiếp trên bảng products/inventory_events**. Không dùng code này như một triển khai tồn kho production đầy đủ nếu chưa xử lý concurrency, phân quyền và idempotency.

## 4. Ví dụ 1 — `doWork` với `PreparedStatement`

Giả sử nghiệp vụ ghi một sự kiện kiểm kê, nhưng `inventory_events` không có entity mapping trong ứng dụng vì dữ liệu được ghi qua một API JDBC chuyên biệt.

~~~java
session.doWork(connection -> {
    String sql = """
        INSERT INTO inventory_events (
            product_id, delta, description
        )
        VALUES (?, ?, ?)
        """;

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, productId);
        statement.setInt(2, adjustment);
        statement.setString(3, reason);

        statement.executeUpdate();
    }
});
~~~

Điều gì xảy ra?

1. Hibernate đưa JDBC Connection đang được Session quản lý vào callback.
2. Code tạo `PreparedStatement` từ chính Connection đó.
3. Code bind tham số và gọi `executeUpdate()`.
4. `try-with-resources` đóng `PreparedStatement`.
5. Callback kết thúc, **Connection vẫn do Hibernate quản lý**.

Không được thêm:

~~~java
connection.commit();
connection.close();
~~~

vào callback. Hai thao tác này có thể phá vỡ transaction/session lifecycle do Hibernate hoặc framework đang quản lý.

### Tại sao dùng PreparedStatement?

Bind parameter giúp truyền giá trị theo kiểu và tránh ghép trực tiếp dữ liệu không tin cậy vào SQL:

~~~java
statement.setLong(1, productId);
statement.setInt(2, adjustment);
statement.setString(3, reason);
~~~

Không viết:

~~~java
String sql = "INSERT INTO inventory_events(description) VALUES ('"
    + reason + "')";
~~~

vì dễ gây SQL injection, lỗi quoting và sai kiểu dữ liệu. `PreparedStatement` không làm an toàn các tên bảng, tên cột hoặc từ khóa ghép động: những thành phần đó cần whitelist/thiết kế SQL cố định.

## 5. Ví dụ 2 — `doReturningWork` trả về một giá trị

Giả sử muốn biết có bao nhiêu sự kiện tồn kho của một sản phẩm:

~~~java
Long totalEvents = session.doReturningWork(connection -> {
    String sql = """
        SELECT COUNT(*)
        FROM inventory_events
        WHERE product_id = ?
        """;

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, productId);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return 0L;
            }
            return rs.getLong(1);
        }
    }
});
~~~

Điểm quan trọng:

- Callback trả trực tiếp `Long`.
- `ResultSet` và `PreparedStatement` được đóng **trước khi callback kết thúc**.
- `Connection` không bị đóng bởi code trong callback.
- Caller nhận một giá trị Java độc lập với các JDBC resource đã đóng.

`COUNT(*)` thường trả một hàng, nên nhánh `!rs.next()` là bảo vệ lập trình, không phải kịch bản mong đợi với SQL trên.

### Lúc nào nên chọn ReturningWork?

Dùng khi cần:

- Số hàng ảnh hưởng bởi một SQL update.
- Giá trị trả về từ một function/procedure.
- Một aggregate như COUNT hoặc SUM.
- JDBC metadata/feature flag.
- Danh sách DTO được materialize hoàn toàn trong callback.
- Một giá trị ID được sinh bởi database.

Không cần thiết nếu công việc chỉ là `executeUpdate()` mà caller không quan tâm row count.

## 6. Ví dụ 3 — Trả số hàng được UPDATE

Số hàng ảnh hưởng là một tín hiệu quan trọng trong nghiệp vụ, chẳng hạn reserve tồn kho:

~~~java
int updatedRows = session.doReturningWork(connection -> {
    String sql = """
        UPDATE products
        SET stock_quantity = stock_quantity - ?
        WHERE id = ?
          AND stock_quantity >= ?
        """;

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setInt(1, quantity);
        statement.setLong(2, productId);
        statement.setInt(3, quantity);

        return statement.executeUpdate();
    }
});

if (updatedRows != 1) {
    throw new IllegalStateException(
        "Sản phẩm không tồn tại hoặc không đủ tồn kho"
    );
}
~~~

Khi update có điều kiện, việc kiểm tra `updatedRows == 1` giúp xác định thao tác có được chấp nhận hay không. Nó còn giảm nguy cơ lỗi đọc-kiểm tra-ghi khi nhiều transaction cùng thao tác.

Nhưng ví dụ này có hệ quả ORM lớn: nếu `Product(id=productId)` đã được nạp trong persistence context, field `stockQuantity` trên managed entity có thể **vẫn là giá trị cũ** sau JDBC UPDATE. Phải có chiến lược đồng bộ thích hợp, trình bày ở phần sau.

## 7. Ví dụ 4 — Trả danh sách DTO, không trả ResultSet

Ta có thể đọc nhiều hàng rồi trả một danh sách giá trị đã được tạo hoàn toàn trong callback.

DTO:

~~~java
public record InventoryEventRow(
    long id,
    long productId,
    int delta,
    String description
) {
}
~~~

JDBC:

~~~java
List<InventoryEventRow> events =
    session.doReturningWork(connection -> {

        String sql = """
            SELECT id, product_id, delta, description
            FROM inventory_events
            WHERE product_id = ?
            ORDER BY id DESC
            """;

        List<InventoryEventRow> rows = new ArrayList<>();

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, productId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    rows.add(new InventoryEventRow(
                        rs.getLong("id"),
                        rs.getLong("product_id"),
                        rs.getInt("delta"),
                        rs.getString("description")
                    ));
                }
            }
        }

        return rows;
    });
~~~

Ứng dụng trả `List<InventoryEventRow>`, không phụ thuộc vào ResultSet đã đóng.

### Một anti-pattern: trả ResultSet ra ngoài

Không làm:

~~~java
ResultSet rs = session.doReturningWork(connection -> {
    PreparedStatement statement =
        connection.prepareStatement("SELECT * FROM products");

    return statement.executeQuery();
});
~~~

Tại sao sai về lifecycle?

- `ResultSet` phụ thuộc vào `PreparedStatement` và connection còn mở.
- Callback kết thúc, Hibernate có thể đổi thời điểm giữ/release connection theo configuration.
- Statement không được đóng đúng chỗ.
- Nếu session/transaction kết thúc, ResultSet có thể không còn hợp lệ.
- Resource leak có thể gây cạn cursor và connection pool.

Quy tắc: **đọc hết dữ liệu cần thiết trong callback rồi trả một giá trị/danh sách DTO độc lập**. Với dữ liệu khổng lồ cần streaming, phải thiết kế một luồng xử lý đồng bộ trong callback, không trả JDBC resources cho tầng khác tự xử lý sau.

## 8. Transaction boundary phải được xác định bên ngoài callback

`doWork` và `doReturningWork` **không phải API để tự mở/commit transaction**.

Trong ứng dụng Hibernate native, một mẫu rõ ràng là:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction transaction = session.beginTransaction();

    try {
        session.doWork(connection -> {
            try (PreparedStatement statement =
                     connection.prepareStatement(
                         "INSERT INTO inventory_events " +
                         "(product_id, delta, description) " +
                         "VALUES (?, ?, ?)"
                     )) {

                statement.setLong(1, productId);
                statement.setInt(2, delta);
                statement.setString(3, reason);
                statement.executeUpdate();
            }
        });

        transaction.commit();
    } catch (RuntimeException ex) {
        if (transaction.isActive()) {
            transaction.rollback();
        }
        throw ex;
    }
}
~~~

Trong mô hình này:

~~~text
Session.beginTransaction()
           |
           +── Session.doWork
           |      +── JDBC PreparedStatement
           |
           +── các thao tác ORM khác nếu cần
           |
           +── commit hoặc rollback
~~~

Nếu câu JDBC INSERT thành công nhưng sau đó một bước bắt buộc khác thất bại, transaction có thể rollback toàn bộ các thay đổi chưa commit thuộc ngữ cảnh này.

Một transaction hợp lệ còn phụ thuộc cấu hình Hibernate, connection provider và transaction coordinator. Không dựa vào mặc định auto-commit của JDBC để thay transaction boundary do Hibernate quản lý.

## 9. Trộn ORM và JDBC trong cùng transaction

Tình huống thường gặp: ứng dụng cập nhật Product bằng ORM và ghi audit bằng JDBC trong cùng nghiệp vụ.

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        Product product =
            session.find(Product.class, productId);

        product.changeStockQuantity(newQuantity);

        session.doWork(connection -> {
            try (PreparedStatement statement =
                     connection.prepareStatement(
                         "INSERT INTO inventory_events " +
                         "(product_id, delta, description) " +
                         "VALUES (?, ?, ?)"
                     )) {

                statement.setLong(1, productId);
                statement.setInt(2, delta);
                statement.setString(3, reason);
                statement.executeUpdate();
            }
        });

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

Cả ORM và JDBC đều tham gia transaction do Session quản lý. Nhưng Hibernate có thể **chưa flush thay đổi trên Product** trước khi callback JDBC chạy.

Nếu câu JDBC chỉ insert audit row có FK tới Product đã tồn tại thì thường không cần flush riêng. Nếu câu JDBC cần đọc hoặc phụ thuộc vào **giá trị Product vừa sửa**, phải nghĩ tới thứ tự flush.

## 10. Flush trước JDBC khi cần đọc thay đổi ORM còn pending

Hibernate theo dõi managed entities trong persistence context và thường phát SQL khi flush. Lệnh `product.changeStockQuantity(...)` chỉ thay đổi object Java; SQL UPDATE có thể chưa được gửi.

Ví dụ dễ gặp lỗi kỳ vọng:

~~~java
Product product = session.find(Product.class, productId);
product.changeStockQuantity(12);

Integer databaseValue = session.doReturningWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT stock_quantity FROM products WHERE id = ?"
             )) {

        statement.setLong(1, productId);

        try (ResultSet rs = statement.executeQuery()) {
            rs.next();
            return rs.getInt(1);
        }
    }
});
~~~

Nếu Session chưa flush update, câu JDBC SELECT có thể vẫn đọc **giá trị cũ trong database**. Lý do: JDBC trực tiếp không tự kích hoạt cơ chế query auto-flush của Hibernate như một HQL/JPQL query do Hibernate phân tích.

Khi JDBC cần thấy thay đổi ORM đang chờ:

~~~java
Product product = session.find(Product.class, productId);
product.changeStockQuantity(12);

session.flush();

Integer databaseValue =
    session.doReturningWork(connection -> {
        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "SELECT stock_quantity FROM products WHERE id = ?"
                 )) {

            statement.setLong(1, productId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalStateException(
                        "Product không tồn tại"
                    );
                }
                return rs.getInt(1);
            }
        }
    });
~~~

**`flush()` khác `commit()`.** Flush đồng bộ SQL còn pending trong transaction hiện tại, nhưng các thay đổi đó vẫn có thể rollback.

### Vì sao không tự động flush ở mọi doWork?

Hibernate không phân tích nội dung tất cả JDBC statements được tạo trong callback để xác định bảng nào liên quan tới persistence context. Do đó không nên mặc định mỗi `doWork` làm Session auto-flush trước khi đưa connection.

Chỉ flush tường minh ở điểm cần bảo đảm thứ tự giữa ORM pending changes và JDBC work. Không gọi flush vô điều kiện sau mỗi setter vì sẽ tăng round trip và hạn chế JDBC batching.

## 11. Sau JDBC UPDATE: managed entity có thể giữ state cũ

Đây là cảnh báo quan trọng nhất khi trộn JDBC trực tiếp với ORM.

~~~java
Product product = session.find(Product.class, productId);

// Entity đang managed, stockQuantity = 20.

session.doWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "UPDATE products " +
                 "SET stock_quantity = 15 " +
                 "WHERE id = ?"
             )) {

        statement.setLong(1, productId);
        statement.executeUpdate();
    }
});

// product.getStockQuantity() vẫn có thể trả 20.
~~~

Hibernate **không tự cập nhật các field Java đã managed** khi JDBC UPDATE thay đổi hàng tương ứng. Persistence context có thể còn snapshot và giá trị cũ.

Tệ hơn, nếu sau đó entity bị dirty do thay đổi một field khác, Hibernate có thể tạo một SQL UPDATE ghi lại một số cột từ trạng thái cũ, tùy static/dynamic update mapping, và vô tình ghi đè thay đổi JDBC.

### Chiến lược A — Refresh entity sau JDBC

Nếu cần tiếp tục sử dụng entity trong transaction:

~~~java
session.doWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "UPDATE products " +
                 "SET stock_quantity = stock_quantity + 1 " +
                 "WHERE id = ?"
             )) {

        statement.setLong(1, productId);
        statement.executeUpdate();
    }
});

session.refresh(product);
~~~

`refresh` nạp lại giá trị từ database vào managed entity và cập nhật trạng thái theo provider.

**Chú ý:** refresh có thể ghi đè những thay đổi Java chưa flush trên entity. Nếu có pending changes quan trọng, cần xác định thứ tự: flush chúng trước JDBC, hoặc chọn luồng khác.

### Chiến lược B — Clear rồi load lại

~~~java
session.flush(); // Nếu có pending ORM changes cần giữ.

session.doWork(connection -> {
    // Thay đổi dữ liệu trực tiếp.
});

session.clear();

Product reloaded =
    session.find(Product.class, productId);
~~~

`clear()` detach **tất cả managed entities** trong Session. Thao tác này có tác động rộng; dùng khi muốn bỏ toàn bộ managed state hiện tại hoặc xử lý batch có chủ đích.

Nếu chỉ một entity bị ảnh hưởng, `refresh(product)` hoặc `detach(product)` rồi load lại có thể có phạm vi nhỏ hơn, nhưng cách nào đúng còn phụ thuộc pending changes và cache.

### Chiến lược C — Tránh cập nhật cùng hàng bằng cả ORM và JDBC

Nếu workflow có thể thiết kế để một nhóm dữ liệu chỉ được quản lý bởi một đường ghi, hãy tránh việc một entity managed và một JDBC UPDATE tự thay nhau sửa cùng hàng. Điều này giảm rủi ro dirty checking ghi đè ngoài ý muốn.

## 12. JDBC bypass và second-level cache

Persistence context là first-level cache của Session, nhưng Hibernate còn có thể bật **second-level cache** hoặc query cache.

Một SQL trực tiếp:

~~~java
session.doWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "UPDATE products SET stock_quantity = ? WHERE id = ?"
             )) {

        statement.setInt(1, 50);
        statement.setLong(2, productId);
        statement.executeUpdate();
    }
});
~~~

không nhất thiết khiến Hibernate biết chính xác entity/collection/cache region nào đã bị thay đổi. Nếu Product được cache ở second-level cache, context khác có thể đọc giá trị cũ cho đến khi cache được làm mới hoặc vô hiệu hóa theo chiến lược thích hợp.

Hibernate có các API cache eviction:

~~~java
sessionFactory.getCache().evictEntityData(
    Product.class,
    productId
);
~~~

Đoạn trên chỉ minh họa một thao tác evict entity cache entry. Các cache region khác, collection cache hoặc query cache có thể cần xử lý riêng. API và chiến lược chính xác tùy mapping/version/provider.

**Refresh entity trong một Session không đồng nghĩa mọi cache ở mọi node đã được làm sạch.** Với bulk JDBC write hoặc hệ thống phân tán, cần thiết kế cache invalidation gắn với đường ghi dữ liệu và nhất quán transaction.

## 13. JDBC không tự áp dụng mọi cơ chế entity lifecycle

Một JDBC statement:

~~~sql
UPDATE products SET stock_quantity = stock_quantity - 1 WHERE id = ?;
~~~

không đi qua entity dirty checking bình thường của Hibernate. Những thứ có thể bị bypass gồm:

- Entity callback như `@PreUpdate` hoặc `@PostUpdate`.
- Hibernate event listeners/interceptors áp dụng cho entity update.
- Tự động cập nhật `@Version` theo cơ chế ORM thông thường.
- Entity-level validation được tích hợp trong lifecycle ORM.
- Soft-delete mapping và filter mà ứng dụng thường dựa vào.
- Tenant/row-level điều kiện mà ORM tự chèn vào query.
- Audit framework phụ thuộc entity lifecycle.
- Synchronization của cache và managed entities.

Điều này **không có nghĩa JDBC bỏ qua database constraints/triggers**. Unique, FK, CHECK, trigger, row-level security và transaction isolation ở database vẫn có hiệu lực.

### Tại sao `@Version` đặc biệt quan trọng?

Nếu Product có:

~~~java
@Version
private Long version;
~~~

Hibernate thường phát SQL UPDATE có điều kiện version cho optimistic locking. Một JDBC UPDATE thủ công không tự tăng version hoặc kiểm tra version nếu SQL không làm điều đó.

Nếu nghiệp vụ cần optimistic locking, phải thiết kế rõ:

~~~sql
UPDATE products
SET stock_quantity = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
~~~

Sau đó kiểm tra số hàng bị ảnh hưởng. Nhưng vẫn cần refresh/evict/chiến lược quản lý entity state; chỉ thêm điều kiện version không tự đồng bộ persistence context.

Không áp dụng JDBC write vào entity có soft delete/multitenancy/audit quan trọng mà không biết chính xác các invariant cần được bảo vệ.

## 14. Connection thuộc Session, callback chỉ mượn

Từ góc nhìn tài nguyên, callback được đưa một reference đến `java.sql.Connection`.

**Ứng dụng nên đóng:**

- `PreparedStatement` hoặc `Statement` được tạo trong callback.
- `CallableStatement` được tạo trong callback.
- `ResultSet` được tạo trong callback.
- Các resource driver-specific do callback sở hữu, nếu quy tắc thư viện yêu cầu.

**Ứng dụng không nên tự đóng hoặc điều phối:**

- `Connection` do Session cung cấp.
- Transaction đang được Hibernate/Spring/JTA quản lý.
- Session bên ngoài callback, trừ khi chính method outer đang sở hữu nó và lifecycle đã kết thúc đúng cách.

Sai:

~~~java
session.doWork(connection -> {
    connection.setAutoCommit(false);
    // ...
    connection.commit();
    connection.close();
});
~~~

Đúng:

~~~java
session.doWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {
        // Bind và execute.
    }
});
~~~

### Vì sao không thay `autoCommit`?

Khi Hibernate và transaction coordinator đã quản lý connection, tự gọi `setAutoCommit(true)` hoặc `commit()` có thể xác nhận các SQL pending ngoài ý định. Từ JDBC, chuyển auto-commit mode khi có transaction đang hoạt động có thể gây commit.

Điều này phá vỡ kỳ vọng rằng service transaction có thể rollback toàn bộ thay đổi. Muốn commit/rollback, sử dụng transaction API **bên ngoài callback**.

## 15. `doReturningWork` không cho phép tài nguyên sống lâu hơn callback

Một nguyên tắc thiết kế mạnh:

> Trả **giá trị dữ liệu đã tách khỏi JDBC**, không trả một cursor/statement/connection còn sống.

Phù hợp:

~~~java
String name = session.doReturningWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT name FROM products WHERE id = ?"
             )) {

        statement.setLong(1, productId);

        try (ResultSet rs = statement.executeQuery()) {
            return rs.next() ? rs.getString(1) : null;
        }
    }
});
~~~

Không phù hợp:

~~~java
Connection borrowed = session.doReturningWork(
    connection -> connection
);
~~~

Không nên giữ lại Connection do Session quản lý để dùng sau khi callback kết thúc. Tùy connection release mode, transaction lifecycle và session scope, reference đó có thể không còn hợp lệ hoặc bị pool tái sử dụng.

Tương tự, trả `InputStream`/`Blob` gắn với ResultSet còn mở có thể gặp vấn đề khi đóng JDBC resources. Nếu cần đọc nội dung LOB, hãy đọc/materialize trong scope hợp lệ hoặc thiết kế streaming callback với phạm vi transaction rõ ràng.

## 16. Dùng `CallableStatement` với stored procedure

Một trong những lý do chính để dùng JDBC trực tiếp là procedure có cú pháp hoặc parameter handling đặc thù.

~~~java
session.doWork(connection -> {
    try (CallableStatement call =
             connection.prepareCall("{ call recalculate_stock(?) }")) {

        call.setLong(1, productId);
        call.execute();
    }
});
~~~

Cú pháp `{ call ... }` là JDBC escape syntax; procedure và tham số thực tế phụ thuộc database. Nếu procedure có OUT parameter:

~~~java
Integer resultCode =
    session.doReturningWork(connection -> {

        try (CallableStatement call =
                 connection.prepareCall(
                     "{ call check_inventory(?, ?) }"
                 )) {

            call.setLong(1, productId);
            call.registerOutParameter(2, Types.INTEGER);
            call.execute();

            return call.getInt(2);
        }
    });
~~~

Đây là ví dụ khái niệm. Một số database xử lý function, procedure, OUT parameter hoặc REF_CURSOR khác nhau; cần sử dụng JDBC driver và cú pháp tương thích.

### Khi nào dùng StoredProcedureQuery thay vì doWork?

Nếu procedure có thể gọi dễ dàng bằng chuẩn JPA:

~~~java
StoredProcedureQuery query =
    em.createStoredProcedureQuery("recalculate_stock");

query.registerStoredProcedureParameter(
    "product_id",
    Long.class,
    ParameterMode.IN
);

query.setParameter("product_id", productId);
query.execute();
~~~

thì `StoredProcedureQuery` có thể giúp giảm phụ thuộc JDBC driver. Còn `doWork` hữu ích khi cần điều khiển trực tiếp `CallableStatement`, cursor hoặc tính năng driver đặc thù mà ORM abstraction không hỗ trợ thuận tiện.

## 17. Dùng JDBC batch trong callback

Khi cần gửi nhiều lệnh tương tự tới database:

~~~java
session.doWork(connection -> {
    String sql = """
        INSERT INTO inventory_events (
            product_id, delta, description
        ) VALUES (?, ?, ?)
        """;

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

        for (InventoryChange change : changes) {
            statement.setLong(1, change.productId());
            statement.setInt(2, change.delta());
            statement.setString(3, change.reason());
            statement.addBatch();
        }

        int[] counts = statement.executeBatch();
        // Xử lý counts nếu nghiệp vụ cần xác nhận từng phần tử.
    }
});
~~~

`InventoryChange` được hiểu là một DTO/record của ứng dụng, chứa `productId`, `delta` và `reason`. Đoạn này không tự kiểm tra số lượng batch hoặc retry.

### Lưu ý batch

- JDBC driver và database quyết định cách tối ưu batch.
- `executeBatch()` có thể ném `BatchUpdateException` và cung cấp update counts của các statement đã xử lý.
- Không được mặc định tất cả statement thành công nếu có lỗi giữa batch.
- Nếu nghiệp vụ cần atomicity, đặt callback trong transaction chung và rollback khi batch thất bại.
- Hibernate ORM batching có API/cơ chế riêng; JDBC batch thủ công không đồng nghĩa được quản lý bởi action queue của ORM.
- Nếu batch cập nhật các bảng được mapping thành entity, cần xử lý persistence context/cache như với bất kỳ direct JDBC write nào.

Với số lượng rất lớn, cân nhắc chia batch và transaction theo invariant nghiệp vụ. Đừng chia một nghiệp vụ phải atomic thành nhiều transaction chỉ để giảm kích thước batch.

## 18. Lấy generated key bằng JDBC

Nếu cần ID mới do database sinh, JDBC cung cấp `Statement.RETURN_GENERATED_KEYS`:

~~~java
Long eventId =
    session.doReturningWork(connection -> {

        String sql = """
            INSERT INTO inventory_events (
                product_id, delta, description
            ) VALUES (?, ?, ?)
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(
                     sql,
                     Statement.RETURN_GENERATED_KEYS
                 )) {

            statement.setLong(1, productId);
            statement.setInt(2, delta);
            statement.setString(3, reason);

            int affected = statement.executeUpdate();
            if (affected != 1) {
                throw new SQLException(
                    "Không tạo được inventory event"
                );
            }

            try (ResultSet keys =
                     statement.getGeneratedKeys()) {

                if (!keys.next()) {
                    throw new SQLException(
                        "Driver không trả generated key"
                    );
                }

                return keys.getLong(1);
            }
        }
    });
~~~

Đây là API JDBC phổ biến, nhưng mức hỗ trợ cách lấy generated key phụ thuộc driver và DDL. Với PostgreSQL, có thể dùng `INSERT ... RETURNING id` theo cú pháp native SQL đặc thù. Không mặc định mọi database hỗ trợ cả hai cách y hệt nhau.

Nếu entity đã có mapping và ID generator chuẩn ORM, `persist` thường đơn giản hơn. Chỉ dùng JDBC khi có lý do cụ thể.

## 19. JDBC metadata và tính năng driver-specific

`doReturningWork` hữu ích khi cần truy cập `DatabaseMetaData` hoặc một thông tin kỹ thuật mà HQL không cung cấp:

~~~java
String databaseProduct =
    session.doReturningWork(connection ->
        connection.getMetaData().getDatabaseProductName()
    );
~~~

Hoặc:

~~~java
int maxColumns =
    session.doReturningWork(connection ->
        connection.getMetaData()
                  .getMaxColumnsInSelect()
    );
~~~

Không nên gọi metadata cho mỗi request để đưa ra quyết định schema cố định; thông tin này thường phù hợp ở bước bootstrap/diagnostics hoặc cấu hình.

### Driver-specific API

Một số JDBC driver hỗ trợ `Connection.unwrap(VendorConnection.class)` hoặc những method riêng. Nếu thật sự cần, callback có thể truy cập connection do Session quản lý và thực hiện unwrap theo hợp đồng JDBC.

Nhưng khi chọn cách này:

- Code phụ thuộc driver cụ thể.
- Phải xác nhận proxy connection của pool hỗ trợ unwrap.
- Không giữ vendor connection lâu hơn callback/session.
- Không thay transaction/session lifecycle.
- Có thể cần xử lý tài nguyên hoặc feature hỗ trợ không đồng nhất giữa môi trường.

Ưu tiên SQL/JPA/Hibernate API portable khi nó đã đủ khả năng.

## 20. Bảng tạm và phạm vi connection

Bảng tạm (temporary table) thường có ngữ nghĩa theo connection/session database, nhưng chi tiết phụ thuộc DB.

~~~java
session.doWork(connection -> {
    try (Statement statement =
             connection.createStatement()) {

        statement.execute(
            "CREATE TEMP TABLE temp_product_ids (id BIGINT)"
        );
    }
});
~~~

Ví dụ trên có thể không chạy nguyên trạng trên mọi dialect. Trong một số database, temporary table tồn tại theo database session/connection và có thể bị xóa khi transaction commit hoặc kết nối kết thúc, tùy tùy chọn DDL.

Lợi ích của `doWork` là callback dùng connection mà Hibernate Session đang sử dụng, nên các SQL sau đó trong ngữ cảnh phù hợp có thể truy cập bảng tạm theo quy tắc DB. Nhưng cần thận trọng:

- Connection acquisition/release mode của Hibernate có thể thay đổi thời gian giữ connection.
- Pool có thể tái sử dụng physical connection cho request khác.
- Nếu temp table còn tồn tại sau transaction, cần dọn đúng.
- Một statement khác không chắc dùng cùng physical connection nếu session/transaction lifecycle thay đổi.
- DDL transactional behavior khác nhau giữa các database.

Không dùng bảng tạm mà không hiểu rõ transaction và connection scope của database đang chạy.

## 21. EntityManager và Session: lấy API Hibernate từ JPA

Trong ứng dụng dùng JPA, có thể unwrap `EntityManager` để lấy Hibernate Session:

~~~java
import jakarta.persistence.EntityManager;
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);

session.doWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "INSERT INTO inventory_events " +
                 "(product_id, delta, description) " +
                 "VALUES (?, ?, ?)"
             )) {

        statement.setLong(1, productId);
        statement.setInt(2, delta);
        statement.setString(3, reason);
        statement.executeUpdate();
    }
});
~~~

Cách này **phụ thuộc Hibernate** là JPA provider. Với provider khác, `unwrap(Session.class)` không portable và có thể thất bại.

Một tính năng mới của **Jakarta Persistence 3.2** là API làm việc trực tiếp với JDBC connection qua `EntityManager.runWithConnection(...)` và `callWithConnection(...)` khi provider hỗ trợ. API này có mục tiêu tương tự `doWork` và `doReturningWork` nhưng thuộc Jakarta Persistence 3.2.

Ví dụ về mặt ý tưởng trên stack Jakarta Persistence 3.2:

~~~java
entityManager.runWithConnection(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "INSERT INTO inventory_events " +
                 "(product_id, delta, description) " +
                 "VALUES (?, ?, ?)"
             )) {

        statement.setLong(1, productId);
        statement.setInt(2, delta);
        statement.setString(3, reason);
        statement.executeUpdate();
    }
});
~~~

Với Jakarta Persistence 3.1 trở xuống, không mặc định API trên tồn tại. Khi mục tiêu cụ thể là Hibernate, `unwrap(Session.class)` và `doWork` là con đường phổ biến.

## 22. Spring `@Transactional` và doWork

Trong Spring Data JPA, transaction thường do Spring quản lý. Mẫu service:

~~~java
@Service
public class InventoryService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public int recordEvent(
        long productId,
        int delta,
        String description
    ) {
        Session session =
            entityManager.unwrap(Session.class);

        return session.doReturningWork(connection -> {
            String sql = """
                INSERT INTO inventory_events (
                    product_id, delta, description
                ) VALUES (?, ?, ?)
                """;

            try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {

                statement.setLong(1, productId);
                statement.setInt(2, delta);
                statement.setString(3, description);

                return statement.executeUpdate();
            }
        });
    }
}
~~~

Đoạn ví dụ giả định Hibernate là JPA provider, transaction manager đã cấu hình đúng và các import Spring/JPA/JDBC được thêm phù hợp.

Cần lưu ý:

- `@Transactional` bao trùm entry point service, không đặt trong lambda JDBC.
- Không gọi `session.beginTransaction()` bên trong một Spring transaction đã active.
- Không tự `connection.commit()` hoặc `rollback()`.
- Nếu callback báo lỗi và exception thoát khỏi service, Spring xử lý rollback theo rollback rules.
- Nếu exception bị catch và nuốt, transaction có thể commit những thay đổi trước đó, tùy trạng thái rollback-only.
- Self-invocation của một method annotated `@Transactional` trong cấu hình Spring proxy thường không kích hoạt interceptor mới.

Nếu ứng dụng dùng `DataSourceTransactionManager` và Hibernate/JPA theo một chiến lược transaction không tương thích, cần sửa cấu hình transaction manager thay vì cố ghép Connection thủ công.

## 23. SQLException đi đâu?

Trong callback JDBC:

~~~java
session.doWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {
        statement.executeUpdate();
    }
});
~~~

`PreparedStatement.executeUpdate()` có thể ném `SQLException`. Interface `Work.execute` cho phép khai báo exception này. Hibernate có thể bắt và chuyển exception sang `HibernateException`/`JDBCException` phù hợp.

Do đó caller không nên mặc định chỉ cần catch một `SQLException` trực tiếp:

~~~java
try {
    session.doWork(connection -> {
        // JDBC work có thể ném SQLException.
    });
} catch (RuntimeException ex) {
    // Xử lý lỗi theo transaction boundary.
    throw ex;
}
~~~

**Không nuốt exception của JDBC work rồi tiếp tục commit** nếu thao tác thất bại làm nghiệp vụ không còn hợp lệ.

Một số lỗi SQL còn có thể khiến database transaction rơi vào trạng thái cần rollback (ví dụ PostgreSQL sau một câu SQL lỗi trong transaction, trừ cơ chế savepoint phù hợp). Sau lỗi persistence nghiêm trọng, hãy rollback, kết thúc/discard Session theo quy tắc Hibernate và tạo transaction mới nếu cần tiếp tục.

### Không mất nguyên nhân gốc

Khi Hibernate wrap `SQLException`, chain của exception có thể chứa SQLState, vendor error code và câu SQL. Khi logging, cần giữ nguyên exception chain để hỗ trợ chẩn đoán.

Không ghi toàn bộ SQL bind values vào log nếu chúng chứa dữ liệu cá nhân, bí mật hoặc thông tin nhạy cảm.

## 24. Khi nào dùng `createNativeQuery` thay vì doWork?

Nếu nhu cầu chỉ là chạy một câu SQL gốc và lấy kết quả, JPA/Hibernate **đã có native query**.

Ví dụ:

~~~java
List<Object[]> rows = entityManager.createNativeQuery(
    """
    SELECT id, sku, stock_quantity
    FROM products
    WHERE stock_quantity < :threshold
    """
)
.setParameter("threshold", 10)
.getResultList();
~~~

Hoặc update:

~~~java
int updated = entityManager.createNativeQuery(
    """
    UPDATE products
    SET stock_quantity = stock_quantity + :delta
    WHERE id = :id
    """
)
.setParameter("delta", 5)
.setParameter("id", productId)
.executeUpdate();
~~~

Native query có thể tiện hơn doWork vì:

- Có API bind parameter trực tiếp.
- Có thể dùng result mapping entity/scalar/DTO tùy provider.
- Không phải tự đóng JDBC Statement và ResultSet.
- Provider có thể có cơ chế flush/query synchronization phù hợp, đặc biệt khi biết affected tables.

Nhưng **native query không tự đồng bộ mọi managed entity bị SQL UPDATE trực tiếp thay đổi**, và không nên nhầm nó với entity dirty checking hoặc lifecycle callbacks. Vẫn phải quản lý context/cache khi thực hiện bulk/native mutation.

### Bảng chọn API

| Nhiệm vụ | API thường ưu tiên |
| --- | --- |
| CRUD một entity đã mapping | `EntityManager`/`Session` và entity lifecycle |
| Truy vấn entity với điều kiện | JPQL/HQL/Criteria |
| SQL đặc thù nhưng không cần JDBC API mức thấp | `createNativeQuery` |
| Stored procedure chuẩn | `StoredProcedureQuery` nếu đủ khả năng |
| Callback cần `PreparedStatement`/`ResultSet` trực tiếp | `doWork`/`doReturningWork` |
| Cần scalar/DTO trả từ JDBC | `doReturningWork` |
| JDBC metadata/driver-specific API | `doReturningWork` hoặc `doWork` |
| Batch JDBC tùy biến | `doWork` |
| Read-only streaming khối lượng lớn | Cân nhắc callback JDBC trong transaction, paging hoặc API streaming phù hợp |
| Bulk update/delete entity mapping | Đánh giá JPQL bulk DML, native query hoặc JDBC và cache effects |

Nguyên tắc: **dùng abstraction cao nhất giải quyết đủ yêu cầu mà không che giấu hành vi quan trọng**. Không dùng doWork chỉ vì muốn viết SQL gốc nếu native query đã đáp ứng thuận tiện.

## 25. doWork khác `session.getJdbcCoordinator()` thế nào?

Hibernate có những SPI nội bộ để quản lý JDBC connection và statements. Application code có thể nhìn thấy các class nội bộ như JDBC coordinator, logical connection hoặc connection access.

Không nên dựa vào SPI đó cho thao tác JDBC thường ngày. `Session.doWork` và `doReturningWork` là API công khai với callback được quản lý rõ ràng.

Ưu điểm:

- Đỡ phụ thuộc cấu trúc nội bộ của Hibernate.
- Không cần tự tìm connection từ private SPI.
- Phù hợp với connection acquisition/release strategy do Hibernate quản lý.
- Giúp giữ rõ scope của JDBC resources.

Nếu không có lý do framework integration đặc biệt, đừng lấy Connection qua internal service registry hoặc hack reflection để thao tác JDBC.

## 26. Transaction isolation và locking vẫn áp dụng

JDBC work sử dụng connection đang tham gia transaction, nên hành vi isolation/locking của database vẫn quan trọng.

Ví dụ:

~~~java
Long count = session.doReturningWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT COUNT(*) FROM products WHERE stock_quantity = 0"
             );
         ResultSet rs = statement.executeQuery()) {

        rs.next();
        return rs.getLong(1);
    }
});
~~~

Kết quả có thể phụ thuộc transaction isolation và các thay đổi concurrent.

Nếu dùng `SELECT ... FOR UPDATE`:

~~~java
session.doWork(connection -> {
    try (PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT id FROM products WHERE id = ? FOR UPDATE"
             )) {

        statement.setLong(1, productId);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException(
                    "Không tìm thấy sản phẩm"
                );
            }
        }
    }
});
~~~

Lock thường gắn với transaction, không gắn với sự tồn tại của lambda callback. Khi callback kết thúc, transaction bên ngoài vẫn có thể đang hoạt động và lock được giữ đến thời điểm database giải phóng theo quy tắc isolation.

Tuy nhiên, không tự đổi isolation bằng `connection.setTransactionIsolation(...)` giữa transaction do Hibernate quản lý. Đặt isolation ở transaction configuration/API phù hợp.

## 27. Multi-tenancy và bảo mật dữ liệu

Trong hệ thống nhiều tenant, Hibernate có thể tự thêm điều kiện/filter vào HQL, dùng schema theo tenant hoặc chọn connection theo tenant.

JDBC viết trực tiếp:

~~~sql
SELECT * FROM products WHERE id = ?;
~~~

không tự áp dụng mọi quy tắc tenant filter của Hibernate. Nếu bảng có `tenant_id` và ứng dụng dựa vào Hibernate filter để tránh đọc chéo tenant, một câu JDBC thiếu điều kiện tenant có thể **trả dữ liệu không đúng quyền**.

Điều cần kiểm tra:

- Tenant đang được xác định bằng schema, database, row filter hay kết hợp?
- Connection do Session cung cấp có trỏ đúng schema/tenant không?
- JDBC SQL có phải tự thêm `tenant_id = ?` và bind tenant ID không?
- Database row-level security có được bật và kiểm thử không?
- Có bypass soft-delete/active flag/authorization check không?

**doWork là quyền truy cập mức thấp.** Nó không tự động giữ toàn bộ invariant mà ORM/service layer thường áp dụng. Không dùng truy vấn trực tiếp bỏ qua quyền chỉ vì connection đã có transaction.

## 28. Logging và quan sát SQL trực tiếp

Trong Hibernate, SQL được sinh qua ORM thường có thể xuất hiện ở logger `org.hibernate.SQL`. Còn JDBC statement do ứng dụng tự tạo trong callback **không nhất thiết đi qua đường logging SQL của Hibernate** như query Hibernate.

Ví dụ:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

có thể hữu ích để xem SQL ORM, nhưng không nên mặc định nó ghi lại toàn bộ JDBC statement thủ công.

Muốn quan sát JDBC trực tiếp, có thể dùng:

- Structured logging có kiểm soát ở service/repository.
- DataSource proxy/observability instrumentation được cấu hình đúng.
- Database query logs hoặc tracing phù hợp.
- SQL execution plan bằng EXPLAIN cho truy vấn cụ thể.
- Metrics về số round trip, thời gian, số hàng và pool usage.

Không bật ghi log bind parameter nhạy cảm trên production nếu chưa có chính sách bảo vệ.

## 29. Đừng dùng JDBC callback cho công việc kéo dài không kiểm soát

Callback thực thi trong ngữ cảnh Session/transaction đang hoạt động. Nếu code thực hiện hàng triệu thao tác, gọi API ngoài hoặc chờ người dùng trong callback, nó có thể giữ connection lâu và làm cạn connection pool.

Ví dụ không phù hợp:

~~~java
session.doWork(connection -> {
    // Tránh chờ HTTP request dài hoặc user input ở đây.
    externalService.callRemoteApi();

    // Sau đó mới dùng JDBC.
});
~~~

Thay vào đó:

- Chuẩn bị dữ liệu thuần Java trước transaction nếu không cần DB.
- Mở transaction gần thời điểm cần đọc/ghi SQL.
- Thực hiện JDBC ngắn gọn, dọn resource đúng scope.
- Commit/rollback nhanh.
- Với xử lý lớn, dùng batch/streaming có kiểm soát và phân chia công việc theo invariant.
- Với thao tác ngoài DB cần tính nhất quán, cân nhắc outbox và thiết kế retry/idempotency.

`doWork` không phải công cụ xử lý bất đồng bộ hoặc worker thread. Callback thông thường thực thi đồng bộ trong lời gọi hiện tại; không giữ Connection rồi đưa sang thread khác.

## 30. Phân biệt doWork với external JDBC Connection

Hai cách sau có semantics khác nhau.

**Cách A — Mượn connection đang do Hibernate quản lý:**

~~~java
session.doWork(connection -> {
    // JDBC work tham gia ngữ cảnh Session/transaction hiện tại.
});
~~~

**Cách B — Tự lấy một connection mới:**

~~~java
try (Connection connection =
         dataSource.getConnection()) {

    // Có thể là connection/transaction riêng.
}
~~~

Trong Spring/JTA, một DataSource có thể trả connection được enlist vào transaction tùy cấu hình, nhưng **không được suy luận mặc định** rằng nó là cùng physical connection và cùng ORM context. Nếu cần chia sẻ chính connection mà Session đang sử dụng, `doWork` là API được thiết kế cho mục đích này.

Điều quan trọng là tránh:

- Một transaction ORM ghi Product.
- Một connection JDBC khác ghi inventory_events rồi commit riêng.
- Transaction ORM rollback do lỗi.
- Audit record trên connection JDBC khác vẫn tồn tại.

Đây là lỗi atomicity do hai connection/transaction không được điều phối như một đơn vị.

## 31. Tích hợp Hibernate API với unit of work

Một service kết hợp hai đường ghi có thể tổ chức theo thứ tự rõ:

~~~java
public void updateStockWithAudit(
    Session session,
    Long productId,
    int newQuantity,
    int delta,
    String reason
) {
    Product product = session.find(Product.class, productId);

    if (product == null) {
        throw new IllegalArgumentException(
            "Sản phẩm không tồn tại"
        );
    }

    product.changeStockQuantity(newQuantity);

    // Nếu JDBC procedure cần đọc stock mới:
    session.flush();

    session.doWork(connection -> {
        String sql = """
            INSERT INTO inventory_events (
                product_id, delta, description
            ) VALUES (?, ?, ?)
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, productId);
            statement.setInt(2, delta);
            statement.setString(3, reason);
            statement.executeUpdate();
        }
    });
}
~~~

Phương thức này **không tự mở hoặc đóng transaction**, vì nó được thiết kế để chạy dưới một transaction boundary của caller.

Caller:

~~~java
try (Session session = sessionFactory.openSession()) {
    Transaction tx = session.beginTransaction();

    try {
        updateStockWithAudit(
            session,
            productId,
            newQuantity,
            delta,
            reason
        );

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
}
~~~

Điểm thiết kế:

- Một tầng chịu trách nhiệm transaction.
- Một method xử lý nghiệp vụ.
- JDBC work mượn connection của Session.
- ORM changes được flush trước khi JDBC phải đọc dữ liệu mới.
- Không có JDBC update cùng hàng Product trong ví dụ audit, nên tránh xung đột managed state.
- Kết thúc transaction rõ ràng khi thành công hoặc thất bại.

## 32. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `session.doWork` không nhận lambda | Session/API version/import không đúng | Dùng `org.hibernate.Session` và interface đúng version |
| SQL chạy nhưng transaction khác không thấy dữ liệu | Chưa commit hoặc isolation ngăn đọc | Kiểm tra transaction boundary |
| Callback JDBC đọc giá trị cũ của entity vừa sửa | ORM chưa flush pending changes | `session.flush()` trước JDBC read khi cần |
| Managed entity giữ giá trị cũ sau JDBC UPDATE | JDBC bypass persistence context | `refresh`/`clear`/reload có chủ đích |
| JDBC UPDATE bị ghi đè ở flush sau | ORM giữ snapshot/state cũ và phát update | Tránh mix cùng hàng, refresh/flush đúng thứ tự |
| `@PreUpdate` không chạy | JDBC UPDATE bypass entity lifecycle | Dùng ORM hoặc thực thi logic cần thiết riêng |
| `@Version` không tăng sau JDBC UPDATE | SQL thủ công không theo quy tắc ORM | Thiết kế version check/increment rõ ràng |
| Second-level cache còn dữ liệu cũ | JDBC không invalidation theo entity mapping | Evict cache region/entry đúng thời điểm |
| Connection pool báo cạn | Callback không đóng Statement/ResultSet hoặc giữ connection lâu | try-with-resources, giảm transaction duration |
| Connection bị đóng giữa transaction | Callback tự `connection.close()` | Không đóng borrowed Connection |
| Transaction commit sớm | Callback tự `commit()`/`setAutoCommit(true)` | Để transaction coordinator quản lý |
| JDBC trả ResultSet ra ngoài rồi lỗi | ResultSet sống lâu hơn callback/connection scope | Materialize DTO bên trong callback |
| Native SQL bị SQL injection | Ghép input trực tiếp vào SQL string | `PreparedStatement` và whitelist identifier |
| SQL không được Hibernate SQL logger ghi lại | JDBC đi ngoài query engine của Hibernate | Logging/proxy/database tracing phù hợp |
| Dữ liệu tenant khác bị đọc | Bỏ qua tenant filter hoặc row constraints | Rà soát tenant/authorization trong SQL |
| SQLException bị mất khi wrap | Không giữ exception cause | Giữ chain và SQLState khi chẩn đoán |
| Bulk JDBC write làm query cache stale | Direct JDBC bypass ORM cache synchronization | Chính sách cache invalidation thích hợp |

## 33. Quy trình chọn giữa ORM, native query và JDBC work

~~~mermaid
flowchart TD
    A["Nhu cầu truy cập database"] --> B{"Entity/HQL/Criteria làm được không?"}
    B -- "Có" --> C["Ưu tiên ORM / JPQL / HQL"]
    B -- "Không" --> D{"Chỉ cần SQL gốc và bind/result mapping?"}
    D -- "Có" --> E["Native query / StoredProcedureQuery"]
    D -- "Không" --> F{"Cần JDBC API mức thấp?"}
    F -- "Không" --> E
    F -- "Có" --> G{"Cần trả giá trị về caller?"}
    G -- "Có" --> H["Session.doReturningWork"]
    G -- "Không" --> I["Session.doWork"]
    H --> J["Borrow Connection; đóng Statement/ResultSet"]
    I --> J
    J --> K["Transaction boundary ở ngoài callback"]
    K --> L["Xử lý flush, stale state, cache, tenant/security"]
    E --> L
    C --> M["Kiểm tra SQL, transaction và hiệu năng"]
    L --> M
~~~

Sơ đồ giúp tránh hai cực đoan: cố viết mọi thứ bằng ORM dù tính năng JDBC rõ ràng hơn, hoặc chuyển mọi thao tác sang JDBC trực tiếp rồi đánh mất lợi ích quản lý entity của Hibernate.

## 34. Bài tập tình huống

**Bài 1 — Ghi audit bằng JDBC.** Service chỉ muốn INSERT một hàng inventory event và không cần giá trị trả về. Chọn API nào?

**Đáp án:** `Session.doWork` với `PreparedStatement`, trong transaction do Session/framework quản lý.

**Bài 2 — Trả số hàng cập nhật.** Service cần biết một conditional UPDATE có ảnh hưởng đúng một hàng không. Chọn API nào?

**Đáp án:** `doReturningWork` vì callback có thể trả `executeUpdate()` row count.

**Bài 3 — Trả ResultSet.** Có thể trả `ResultSet` ra khỏi callback để Controller xử lý không?

**Đáp án:** Không nên. ResultSet phụ thuộc Statement/Connection và resource scope. Đọc dữ liệu rồi trả DTO/List trong callback.

**Bài 4 — Entity vừa được sửa bằng ORM.** JDBC SELECT chạy ngay sau setter nhưng đọc giá trị cũ. Vì sao?

**Đáp án:** Hibernate chưa flush pending entity update. Nếu JDBC cần giá trị DB mới, flush trước callback trong transaction phù hợp.

**Bài 5 — JDBC UPDATE một Product đang managed.** Vì sao `product.getStockQuantity()` vẫn cũ?

**Đáp án:** JDBC bypass persistence context. Cần refresh/reload hoặc tránh trộn hai đường ghi cùng hàng.

**Bài 6 — Đóng Connection trong callback.** Có hợp lệ vì đã dùng xong JDBC không?

**Đáp án:** Không. Connection thuộc Hibernate Session/transaction coordinator; callback chỉ mượn. Chỉ đóng resources do callback tạo.

**Bài 7 — Gọi `connection.commit()` trong doWork.** Có nên tự commit SQL vừa chạy không?

**Đáp án:** Không. Điều đó có thể commit cả những thao tác khác trong cùng transaction và phá vỡ rollback của service.

**Bài 8 — SQL trực tiếp có kích hoạt `@PreUpdate` không?**

**Đáp án:** Không theo entity lifecycle bình thường. JDBC mutation không đi qua dirty checking/callback của entity.

**Bài 9 — Product có `@Version`.** Một JDBC UPDATE chỉ đổi stock mà không kiểm tra/increment version có rủi ro gì?

**Đáp án:** Nó bỏ qua optimistic locking của ORM, làm tăng nguy cơ lost update hoặc state không nhất quán. Cần SQL có version semantics phù hợp hoặc dùng ORM.

**Bài 10 — Dùng Spring `@Transactional`.** Có cần gọi `session.beginTransaction()` nữa không?

**Đáp án:** Không. Khi transaction được Spring quản lý, không tự mở transaction Hibernate/JDBC riêng trong callback.

**Bài 11 — Stored procedure với OUT parameter.** Chọn `doWork` hay `doReturningWork`?

**Đáp án:** Nếu caller cần OUT value, `doReturningWork` cùng `CallableStatement` phù hợp. Nếu JPA `StoredProcedureQuery` đủ nhu cầu, có thể ưu tiên API đó.

**Bài 12 — JDBC chỉ đọc metadata.** Dùng API nào?

**Đáp án:** `doReturningWork` để trả giá trị như database product name hoặc metadata khác.

**Bài 13 — Direct JDBC thay đổi nhiều entity đã cache.** Chỉ refresh một entity có bảo đảm cache toàn hệ thống đúng không?

**Đáp án:** Không. Cần chiến lược eviction/invalidation cho second-level cache, query cache, những entity liên quan và transaction khác.

**Bài 14 — Native query đã chạy được SQL.** Có nhất thiết đổi sang doWork không?

**Đáp án:** Không. Nếu chỉ cần SQL + parameter/result mapping, `createNativeQuery` thường đơn giản hơn. doWork dành cho trường hợp thực sự cần JDBC API mức thấp.

## 35. Checklist trước khi dùng JDBC callback

- Có thật sự cần JDBC API thấp hơn `createNativeQuery` hoặc `StoredProcedureQuery` không?
- Session có đang tham gia transaction phù hợp không?
- Callback có trả giá trị cho caller không? Chọn `doWork` hay `doReturningWork`.
- Có dùng `PreparedStatement` và bind parameter an toàn không?
- Có đóng mọi Statement/ResultSet trong callback không?
- Có tránh đóng Connection hoặc gọi commit/rollback/setAutoCommit không?
- Có ORM pending changes cần flush trước JDBC không?
- JDBC có sửa hàng mà entity managed đang giữ không?
- Có cần refresh/clear/reload và xử lý second-level cache không?
- SQL direct có bypass `@Version`, soft delete, tenant filter, callback hoặc authorization không?
- Transaction có quá dài hoặc giữ connection cho I/O bên ngoài không?
- Có lỗi SQLException nào cần rollback và discard Session không?
- Có cần integration test với database/dialect thật để xác nhận hành vi không?

## 36. Tổng kết

**`Session.doWork` và `Session.doReturningWork` là cánh cửa chính thức của Hibernate để thực hiện JDBC trên Connection do Session quản lý.** Chúng không biến JDBC thành entity operation và không tự giải quyết toàn bộ lifecycle/caching của ORM.

Những điều quan trọng nhất:

1. **`doWork` dùng khi không cần kết quả**, còn **`doReturningWork` dùng khi cần giá trị trả về**.
2. **Connection được mượn từ Session**, nên JDBC work tham gia ngữ cảnh connection/transaction mà Session đang sử dụng.
3. **Không đóng Connection hoặc tự commit/rollback** bên trong callback.
4. **Đóng PreparedStatement, CallableStatement và ResultSet** do callback tạo bằng try-with-resources.
5. **JDBC không tự flush ORM changes**. Flush trước callback khi SQL cần đọc dữ liệu ORM vừa sửa.
6. **JDBC direct writes không tự cập nhật persistence context**. Cần refresh/clear/reload và cache invalidation theo yêu cầu.
7. **SQL gốc bypass entity lifecycle**, bao gồm nhiều callback, validation, versioning và filter ORM.
8. **`createNativeQuery` thường đủ cho SQL gốc thông thường**; doWork chỉ cần khi muốn thao tác JDBC cấp thấp.
9. **Trong Spring/JPA, lấy Hibernate Session qua `unwrap(Session.class)`** và dùng transaction của framework; trên Jakarta Persistence 3.2 còn có API chuẩn cho JDBC connection callback nếu provider hỗ trợ.
10. **Tính đúng đắn và an toàn dữ liệu quan trọng hơn việc né abstraction**: transaction, authorization, multitenancy, cache và concurrency phải được thiết kế rõ.

Khi thật sự cần JDBC, hãy giữ callback nhỏ, transaction rõ ràng và ranh giới tài nguyên chặt chẽ. Cách tiếp cận này cho phép tận dụng khả năng mức thấp của JDBC mà vẫn sử dụng Hibernate để quản lý phần lớn entity và nghiệp vụ.

## Tài liệu tham khảo

- [Hibernate ORM 7.2 — SharedSessionContract: doWork / doReturningWork](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/SharedSessionContract.html)
- [Hibernate ORM — A Short Guide: Interacting directly with JDBC](https://docs.hibernate.org/stable/orm/introduction/html_single/)
- [Hibernate ORM User Guide — JDBC callbacks](https://docs.hibernate.org/orm/8.0/userguide/html_single/)
- [Hibernate ORM User Guide — Flushing](https://docs.hibernate.org/orm/7.2/userguide/html_single/)
