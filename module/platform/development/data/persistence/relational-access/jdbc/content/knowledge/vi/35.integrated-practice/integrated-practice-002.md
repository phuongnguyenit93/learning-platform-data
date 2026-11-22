# Thực hiện CRUD với truy vấn tham số và khóa sinh

Trong ứng dụng Java truy cập cơ sở dữ liệu quan hệ, **CRUD** gồm tạo (*Create*), đọc (*Read*), cập nhật (*Update*) và xóa (*Delete*) bản ghi. Với **JDBC**, bốn thao tác này không chỉ là bốn câu SQL: lập trình viên cần truyền giá trị an toàn bằng `PreparedStatement`, đọc dữ liệu bằng `ResultSet`, nhận **khóa do database sinh** sau `INSERT`, xử lý số dòng bị tác động, quản lý `Connection` và transaction.

Bài thực hành tổng hợp này xây dựng một repository sản phẩm bằng **JDBC thuần** sử dụng `DataSource`, `PreparedStatement`, `ResultSet`, `Statement.RETURN_GENERATED_KEYS` và `Connection.commit()/rollback()`. Kịch bản có một bảng sản phẩm với khóa chính tự sinh và một bảng thẻ liên quan, đủ để kiểm chứng **khóa sinh**, **CRUD tham số hóa** và **tính nguyên tử của transaction nhiều câu lệnh**.

**Kết quả cuối cùng:** tạo sản phẩm và nhận ID từ database; truy vấn theo ID; đọc một trang dữ liệu; cập nhật có kiểm soát phiên bản; xóa; và kiểm thử rằng insert sản phẩm sẽ rollback nếu thao tác gắn thẻ thất bại.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Tạo schema có primary key tự sinh, khóa ngoại và ràng buộc dữ liệu.
2. Dùng `PreparedStatement` và các phương thức `setString`, `setLong`, `setInt`, `setBigDecimal` đúng thứ tự.
3. Phân biệt `executeUpdate()` và `executeQuery()`.
4. Yêu cầu generated keys bằng `Statement.RETURN_GENERATED_KEYS` và đọc bằng `getGeneratedKeys()`.
5. Truyền ID do database sinh vào câu INSERT bảng con trong **cùng transaction**.
6. Ánh xạ `ResultSet` thành domain object và xử lý SQL `NULL` đúng cách.
7. Dùng `version` để tránh cập nhật/xóa bản ghi dựa trên trạng thái cũ.
8. Phân biệt affected rows bằng 0, 1 và lỗi `SQLException`.
9. Giữ danh sách kết quả có giới hạn, không nạp toàn bộ bảng vào RAM.
10. Kiểm thử CRUD và rollback trên DBMS/driver thực tế.

Các ví dụ sử dụng **Java 8+**. Mỗi môi trường cần một `DataSource` được cấu hình với JDBC driver, URL, xác thực và quyền thích hợp; Java SE chỉ cung cấp **interface** `DataSource`, không tự tạo kết nối đến một DBMS bất kỳ.

## 2. Schema và hợp đồng dữ liệu

Giả sử một ứng dụng quản lý danh mục sản phẩm có các thuộc tính:

| Thuộc tính | Kiểu SQL | Kiểu Java | Quy tắc |
| --- | --- | --- | --- |
| `id` | `BIGINT` identity | `long` | DB sinh, không do client gửi khi tạo |
| `sku` | `VARCHAR(40)` | `String` | Không rỗng, duy nhất |
| `name` | `VARCHAR(150)` | `String` | Không rỗng |
| `price` | `DECIMAL(18,2)` | `BigDecimal` | Không âm, 2 chữ số thập phân |
| `quantity` | `INTEGER` | `int` | Không âm |
| `version` | `BIGINT` | `long` | Mặc định 0; tăng theo mỗi UPDATE thành công |

Bảng thứ hai lưu thẻ của sản phẩm, ví dụ `office` hoặc `accessory`. Mỗi sản phẩm không được có hai thẻ trùng nhau.

~~~sql
CREATE TABLE catalog_product (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(18, 2) NOT NULL CHECK (price >= 0),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE product_tag (
    product_id BIGINT NOT NULL,
    tag VARCHAR(40) NOT NULL,
    PRIMARY KEY (product_id, tag),
    FOREIGN KEY (product_id)
        REFERENCES catalog_product(id)
        ON DELETE CASCADE
);
~~~

Đây là **schema minh họa theo cú pháp SQL phổ biến**, phù hợp với các DBMS hỗ trợ identity chuẩn như PostgreSQL phiên bản hiện đại. Với MySQL thường dùng `BIGINT AUTO_INCREMENT`; SQL Server dùng `BIGINT IDENTITY(1,1)`; SQLite có ngữ nghĩa `INTEGER PRIMARY KEY` riêng. Không suy rằng cùng một DDL và mọi ràng buộc `CHECK` đều hoạt động giống nhau trên tất cả phiên bản DBMS.

**Vì sao cần ràng buộc ở DB?** Validation Java giúp phát hiện lỗi sớm, nhưng một job, migration hoặc chương trình khác vẫn có thể truy cập cùng database. `UNIQUE(sku)`, primary key, foreign key và các constraint giúp giữ tính đúng đắn ở nguồn dữ liệu. Ngược lại, constraint không thay thế kiểm tra quyền của người dùng.

### Sơ đồ quan hệ

~~~mermaid
erDiagram
    CATALOG_PRODUCT ||--o{ PRODUCT_TAG : contains
    CATALOG_PRODUCT {
        BIGINT id PK
        VARCHAR sku UK
        VARCHAR name
        DECIMAL price
        INTEGER quantity
        BIGINT version
    }
    PRODUCT_TAG {
        BIGINT product_id PK,FK
        VARCHAR tag PK
    }
~~~

`ON DELETE CASCADE` chỉ là chính sách ví dụ: khi sản phẩm bị xóa, các thẻ cũng bị xóa. Nếu muốn giữ lịch sử hoặc audit, cần thiết kế một bảng lịch sử riêng, không cascade xóa nó.

## 3. PreparedStatement bảo vệ giá trị, không bảo vệ SQL ghép chuỗi

Cách viết có rủi ro:

~~~java
String sql = "INSERT INTO catalog_product (sku, name, price, quantity) "
           + "VALUES ('" + sku + "', '" + name + "', "
           + price + ", " + quantity + ")";
~~~

`sku` hoặc `name` có thể chứa dấu nháy, ký tự đặc biệt hoặc input chưa tin cậy làm thay đổi cú pháp SQL. Cách đúng là giữ SQL cố định và dùng `?` cho **giá trị**:

~~~java
String sql = "INSERT INTO catalog_product "
           + "(sku, name, price, quantity) VALUES (?, ?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, sku);
    ps.setString(2, name);
    ps.setBigDecimal(3, price);
    ps.setInt(4, quantity);
    int affected = ps.executeUpdate();
}
~~~

Vị trí tham số bắt đầu từ **1**. Với các cột ngày giờ, LOB hoặc `NULL`, phải dùng getter/setter tương ứng với kiểu SQL và khả năng hỗ trợ của driver, ví dụ `setNull(index, Types.VARCHAR)` khi cần gán SQL NULL có kiểu.

Dấu `?` **không thể** thay thế bảng hoặc cột:

~~~sql
-- Sai: tên bảng không phải giá trị để bind.
SELECT * FROM ? WHERE id = ?;

-- Sai: tên cột được chọn không được bind bằng ?.
SELECT * FROM catalog_product ORDER BY ?;
~~~

Nếu ứng dụng phải chọn bảng, cột hoặc hướng sắp xếp theo input, hãy dùng một **allowlist các fragment SQL cố định**. Không bao giờ lấy nguyên chuỗi người dùng rồi ghép vào cấu trúc SQL.

## 4. Khóa sinh: từ INSERT đến getGeneratedKeys

Với cột `id` sinh bởi database, câu `INSERT` không bao gồm `id`:

~~~sql
INSERT INTO catalog_product (sku, name, price, quantity)
VALUES (?, ?, ?, ?);
~~~

JDBC cho phép yêu cầu driver trả khóa sinh khi tạo statement:

~~~java
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO catalog_product "
      + "(sku, name, price, quantity) VALUES (?, ?, ?, ?)",
        Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "KB-100");
    ps.setString(2, "Keyboard");
    ps.setBigDecimal(3, new java.math.BigDecimal("249.90"));
    ps.setInt(4, 12);

    if (ps.executeUpdate() != 1) {
        throw new java.sql.SQLException("INSERT không đúng 1 dòng");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new java.sql.SQLException(
                    "Driver không trả generated key");
        }
        long productId = keys.getLong(1);
        if (keys.wasNull()) {
            throw new java.sql.SQLException(
                    "Generated key là SQL NULL");
        }

        // Dùng productId trong cùng transaction.
    }
}
~~~

**Phân biệt ba bước:**

1. `executeUpdate()` thực thi một thao tác thay đổi dữ liệu và trả số dòng được báo cáo là bị tác động.
2. `getGeneratedKeys()` trả `ResultSet` gồm các giá trị khóa do driver cung cấp cho statement đó.
3. `commit()` xác nhận transaction. **Có generated key chưa đồng nghĩa bản ghi đã commit**.

Luôn đọc generated keys khi `PreparedStatement` còn mở. Nếu không có khóa hoặc driver trả kết quả không hợp lệ, báo lỗi thay vì tự đoán ID bằng `SELECT MAX(id)`.

### Vì sao không dùng MAX(id)?

Một transaction khác có thể chèn dòng mới giữa lúc bạn INSERT và SELECT MAX, khiến MAX thuộc một sản phẩm không liên quan. Với concurrency, không có cơ sở để suy ID chính xác của lệnh vừa thực hiện từ giá trị lớn nhất toàn bảng.

### Cách lấy khóa theo driver/DBMS

| Cách | Khi phù hợp | Giới hạn |
| --- | --- | --- |
| `Statement.RETURN_GENERATED_KEYS` | Phương án JDBC tổng quát | Cần driver hỗ trợ và kiểm chứng dữ liệu trả về |
| `prepareStatement(sql, new String[]{"id"})` | Muốn chỉ rõ cột khóa cần lấy | Khả năng hỗ trợ và cách nhận diện tên cột phụ thuộc driver |
| PostgreSQL `INSERT ... RETURNING id` | SQL dialect trả khóa trực tiếp | Dùng `executeQuery()` cho câu lệnh trả result set |
| SQL Server `OUTPUT INSERTED.id` | SQL Server-specific | Cần lưu ý trigger, câu SQL và driver |
| API vendor riêng | Trường hợp API chuẩn không phù hợp | Cô lập phụ thuộc vendor trong DAO adapter |

`Connection.getMetaData().supportsGetGeneratedKeys()` cho biết khả năng driver công bố, nhưng **một phép thử INSERT thật** vẫn cần thiết. Batch insert có generated keys phức tạp hơn: không tự giả định số lượng và thứ tự khóa trả về tương ứng hoàn toàn với input trên mọi driver.

## 5. Thiết kế repository và ranh giới transaction

Ta triển khai một `ProductRepository` tự sở hữu `DataSource`. Mỗi lời gọi ghi sẽ:

1. Mượn một connection.
2. Tắt auto-commit trước DML.
3. Thực thi một hoặc nhiều câu SQL với tham số.
4. Kiểm tra affected rows và khóa sinh.
5. Commit nếu hoàn tất; nếu lỗi thì cố rollback.
6. Đóng statement/result set/connection bằng `try-with-resources`.

~~~mermaid
flowchart TD
    A["Validate đầu vào"] --> B["getConnection + setAutoCommit(false)"]
    B --> C["INSERT product"]
    C --> D["getGeneratedKeys -> productId"]
    D --> E["INSERT product_tag theo productId"]
    E --> F{"Mọi thao tác thành công?"}
    F -->|Có| G["commit + trả productId"]
    F -->|Không| H["rollback + ném lỗi"]
    G --> I["READ/UPDATE/DELETE với ID đã sinh"]
~~~

Điều cốt lõi của transaction nhiều bảng: **mọi câu SQL phải dùng cùng một `Connection`**. Nếu hàm insert product tự tạo connection A nhưng insert tag lại dùng connection B, rollback trên A không hoàn tác các câu SQL đã commit trên B.

### Hợp đồng method

| Method | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `create(...)` | `long` | ID sinh bởi database, chỉ trả sau commit |
| `createWithTags(...)` | `long` | Product và tags cùng commit hoặc cùng rollback |
| `findById(id)` | `Optional<Product>` | Rỗng khi không có hàng; lỗi DB vẫn ném `SQLException` |
| `listAfterId(lastId, limit)` | `List<Product>` | Trang nhỏ, sắp xếp ID tăng, tối đa 100 dòng |
| `update(..., expectedVersion)` | `boolean` | `true` khi cập nhật đúng 1 hàng và commit |
| `delete(id, expectedVersion)` | `boolean` | `true` khi xóa đúng 1 hàng và commit |

Với `update`/`delete`, `false` có thể là **ID không tồn tại hoặc version không khớp**. Bài này chủ động không phân biệt hai trường hợp để tránh một lượt kiểm tra thừa có race condition; ứng dụng muốn mã lỗi riêng cần contract và điều phối bổ sung.

## 6. Code Java đầy đủ: ProductRepository

Ví dụ Java 8+ dưới đây chỉ dùng JDBC chuẩn và thư viện Java SE. Trong dự án thực có thể tách `Product` thành model và repository thành lớp riêng; bài học giữ chúng cùng một lớp để người đọc thấy luồng dữ liệu đầy đủ.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class ProductRepository {
    private final DataSource dataSource;

    public ProductRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public static final class Product {
        public final long id;
        public final String sku;
        public final String name;
        public final BigDecimal price;
        public final int quantity;
        public final long version;

        public Product(long id, String sku, String name,
                BigDecimal price, int quantity, long version) {
            this.id = id;
            this.sku = sku;
            this.name = name;
            this.price = price;
            this.quantity = quantity;
            this.version = version;
        }
    }

    private static void requireText(
            String value, String field, int maxLength) {
        if (value == null || value.trim().isEmpty()
                || value.length() > maxLength) {
            throw new IllegalArgumentException(
                    field + " không hợp lệ");
        }
    }

    private static BigDecimal requirePrice(BigDecimal price) {
        Objects.requireNonNull(price, "price");
        if (price.signum() < 0) {
            throw new IllegalArgumentException(
                    "Giá không được âm");
        }

        try {
            BigDecimal exact =
                    price.setScale(2, RoundingMode.UNNECESSARY);

            if (exact.precision() > 18) {
                throw new IllegalArgumentException(
                        "Giá vượt DECIMAL(18,2)");
            }
            return exact;
        } catch (ArithmeticException scaleError) {
            throw new IllegalArgumentException(
                    "Giá có hơn 2 chữ số thập phân",
                    scaleError);
        }
    }

    private static void requireQuantity(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "Số lượng không được âm");
        }
    }

    private static void requireId(long id) {
        if (id <= 0) {
            throw new IllegalArgumentException(
                    "ID phải là số dương");
        }
    }

    private static void rollbackBestEffort(
            Connection c, Throwable primary) {
        try {
            c.rollback();
        } catch (SQLException rollbackError) {
            primary.addSuppressed(rollbackError);
        }
    }

    // Chèn product bằng connection của transaction ngoài.
    // Helper KHÔNG tự commit.
    private static long insertProduct(
            Connection c, String sku, String name,
            BigDecimal price, int quantity) throws SQLException {

        String sql = "INSERT INTO catalog_product "
                   + "(sku, name, price, quantity) "
                   + "VALUES (?, ?, ?, ?)";

        try (PreparedStatement ps = c.prepareStatement(
                sql, Statement.RETURN_GENERATED_KEYS)) {
            ps.setString(1, sku);
            ps.setString(2, name);
            ps.setBigDecimal(3, price);
            ps.setInt(4, quantity);
            ps.setQueryTimeout(10);

            if (ps.executeUpdate() != 1) {
                throw new SQLException(
                        "INSERT product không đúng 1 dòng");
            }

            try (ResultSet keys = ps.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException(
                            "Không có generated key");
                }

                long id = keys.getLong(1);
                if (keys.wasNull() || id <= 0) {
                    throw new SQLException(
                            "Generated key không hợp lệ");
                }

                if (keys.next()) {
                    throw new SQLException(
                            "INSERT một product trả nhiều khóa");
                }
                return id;
            }
        }
    }

    // CREATE không có tag.
    public long create(String sku, String name,
            BigDecimal price, int quantity) throws SQLException {
        return createWithTags(
                sku, name, price, quantity,
                Collections.<String>emptyList());
    }

    // CREATE với nhiều tag; tất cả cùng một transaction.
    public long createWithTags(
            String sku, String name, BigDecimal price,
            int quantity, List<String> tags) throws SQLException {

        requireText(sku, "sku", 40);
        requireText(name, "name", 150);
        BigDecimal exactPrice = requirePrice(price);
        requireQuantity(quantity);
        Objects.requireNonNull(tags, "tags");

        if (tags.size() > 20) {
            throw new IllegalArgumentException(
                    "Chỉ hỗ trợ tối đa 20 thẻ mỗi lần tạo");
        }
        for (String tag : tags) {
            requireText(tag, "tag", 40);
        }

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);

            try {
                long id = insertProduct(
                        c, sku, name, exactPrice, quantity);

                if (!tags.isEmpty()) {
                    String sql = "INSERT INTO product_tag "
                               + "(product_id, tag) VALUES (?, ?)";

                    try (PreparedStatement ps = c.prepareStatement(sql)) {
                        ps.setQueryTimeout(10);
                        for (String tag : tags) {
                            ps.setLong(1, id);
                            ps.setString(2, tag);
                            if (ps.executeUpdate() != 1) {
                                throw new SQLException(
                                        "INSERT tag không đúng 1 dòng");
                            }
                        }
                    }
                }

                c.commit();
                return id;

            } catch (SQLException | RuntimeException failure) {
                rollbackBestEffort(c, failure);
                throw failure;
            }
        }
    }

    // READ một bản ghi theo generated ID.
    public Optional<Product> findById(long id)
            throws SQLException {
        requireId(id);

        String sql = "SELECT id, sku, name, price, quantity, version "
                   + "FROM catalog_product WHERE id = ?";

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setQueryTimeout(10);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                Product product = mapProduct(rs);
                if (rs.next()) {
                    throw new SQLException(
                            "Primary key trả nhiều hàng");
                }
                return Optional.of(product);
            }
        }
    }

    // READ nhiều bản ghi, có giới hạn nhỏ.
    public List<Product> listAfterId(long lastId, int limit)
            throws SQLException {
        if (lastId < 0 || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "lastId/limit không hợp lệ");
        }

        String sql = "SELECT id, sku, name, price, quantity, version "
                   + "FROM catalog_product WHERE id > ? "
                   + "ORDER BY id ASC";

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, lastId);
            ps.setMaxRows(limit);
            ps.setQueryTimeout(10);

            List<Product> page = new ArrayList<>(limit);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    page.add(mapProduct(rs));
                }
            }
            return page;
        }
    }

    // UPDATE có điều kiện version để tránh lost update.
    public boolean update(
            long id, long expectedVersion, String newName,
            BigDecimal newPrice, int newQuantity)
            throws SQLException {

        requireId(id);
        if (expectedVersion < 0) {
            throw new IllegalArgumentException(
                    "version không hợp lệ");
        }
        requireText(newName, "name", 150);
        BigDecimal exactPrice = requirePrice(newPrice);
        requireQuantity(newQuantity);

        String sql = "UPDATE catalog_product SET "
                   + "name = ?, price = ?, quantity = ?, "
                   + "version = version + 1 "
                   + "WHERE id = ? AND version = ?";

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);

            try {
                int affected;
                try (PreparedStatement ps = c.prepareStatement(sql)) {
                    ps.setString(1, newName);
                    ps.setBigDecimal(2, exactPrice);
                    ps.setInt(3, newQuantity);
                    ps.setLong(4, id);
                    ps.setLong(5, expectedVersion);
                    ps.setQueryTimeout(10);
                    affected = ps.executeUpdate();
                }

                if (affected < 0 || affected > 1) {
                    throw new SQLException(
                            "UPDATE số dòng bất thường");
                }
                c.commit();
                return affected == 1;

            } catch (SQLException | RuntimeException failure) {
                rollbackBestEffort(c, failure);
                throw failure;
            }
        }
    }

    // DELETE chỉ khi phiên bản vẫn khớp.
    public boolean delete(long id, long expectedVersion)
            throws SQLException {

        requireId(id);
        if (expectedVersion < 0) {
            throw new IllegalArgumentException(
                    "version không hợp lệ");
        }

        String sql = "DELETE FROM catalog_product "
                   + "WHERE id = ? AND version = ?";

        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);

            try {
                int affected;
                try (PreparedStatement ps = c.prepareStatement(sql)) {
                    ps.setLong(1, id);
                    ps.setLong(2, expectedVersion);
                    ps.setQueryTimeout(10);
                    affected = ps.executeUpdate();
                }

                if (affected < 0 || affected > 1) {
                    throw new SQLException(
                            "DELETE số dòng bất thường");
                }
                c.commit();
                return affected == 1;

            } catch (SQLException | RuntimeException failure) {
                rollbackBestEffort(c, failure);
                throw failure;
            }
        }
    }

    private static Product mapProduct(ResultSet rs)
            throws SQLException {
        long id = rs.getLong("id");
        if (rs.wasNull()) {
            throw new SQLException("id là SQL NULL");
        }

        String sku = rs.getString("sku");
        String name = rs.getString("name");
        BigDecimal price = rs.getBigDecimal("price");

        int quantity = rs.getInt("quantity");
        boolean quantityWasNull = rs.wasNull();

        long version = rs.getLong("version");
        boolean versionWasNull = rs.wasNull();

        if (sku == null || name == null || price == null
                || quantityWasNull || versionWasNull) {
            throw new SQLException(
                    "Thiếu cột product bắt buộc");
        }

        return new Product(
                id, sku, name, price, quantity, version);
    }
}
~~~

### Giải thích những lựa chọn quan trọng

**`insertProduct` nhận `Connection` làm tham số.** Vì vậy nó tham gia đúng transaction của `createWithTags`, không tự tạo connection khác hoặc commit sớm. Đây là điều kiện cần để rollback toàn bộ khi một thẻ gây lỗi.

**`getGeneratedKeys()` được đọc trước commit.** Khóa sinh đã có thể dùng làm `product_tag.product_id` trong transaction, nhưng mã chỉ trả ID sau khi `commit()` thành công.

**`BigDecimal` được chuẩn hóa có kiểm soát.** `setScale(2, RoundingMode.UNNECESSARY)` từ chối giá phải làm tròn; `precision()` kiểm tra giới hạn thập phân theo schema demo. Giá âm/số lượng âm bị từ chối trước khi gửi SQL. Các quy tắc chính xác về Unicode/VARCHAR có thể khác giữa DBMS, cần test trên dữ liệu thật.

**`mapProduct` không phỏng đoán SQL NULL.** `getLong`/`getInt` được theo sau bởi `wasNull()`. Với `String` và `BigDecimal`, kiểm tra trực tiếp `null`.

**`listAfterId` chỉ tạo danh sách có giới hạn.** `setMaxRows(limit)` giới hạn số dòng JDBC trả về nhưng không bảo đảm DB server chỉ đọc/sort đúng `limit` dòng. Với tải lớn, ưu tiên `LIMIT ?` hoặc `FETCH FIRST` theo dialect và chỉ mục thích hợp.

**`update` và `delete` dùng optimistic locking.** Nếu bản ghi bị cập nhật bởi transaction khác sau khi caller đọc, `version` đã đổi và lệnh có điều kiện cũ tác động 0 dòng. Không retry ghi đè tự động.

**`rollbackBestEffort` giữ lỗi gốc.** Nếu rollback cũng lỗi, exception rollback được thêm vào `suppressed`. Nếu kết nối hỏng nghiêm trọng, nó không được tiếp tục dùng cho công việc khác.

**Phạm vi transaction được xác định rõ.** Class này tự mở transaction cho mỗi lời gọi ghi, thích hợp với bài thực hành độc lập. Trong Spring hay một Unit of Work có transaction manager, cần để tầng điều phối sở hữu commit/rollback; không nhúng việc tự commit vào từng DAO con.

## 7. Chạy trọn vòng: tạo, đọc, cập nhật, xóa

Giả sử `dataSource` đã được cấu hình và hai bảng đã tồn tại:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

ProductRepository repository =
        new ProductRepository(dataSource);

// CREATE: database tự sinh id.
long id = repository.createWithTags(
        "KB-100", "Mechanical keyboard",
        new BigDecimal("249.90"), 12,
        Arrays.asList("office", "accessory"));

// READ: lấy theo khóa vừa được sinh.
ProductRepository.Product original =
        repository.findById(id).get();

// UPDATE: phiên bản bắt đầu ở 0 theo schema.
boolean updated = repository.update(
        id, original.version, "Keyboard v2",
        new BigDecimal("259.90"), 10);

if (!updated) {
    throw new IllegalStateException(
            "Bản ghi không còn đúng phiên bản");
}

// READ: lấy version mới sau update.
ProductRepository.Product latest =
        repository.findById(id).get();

// READ theo trang nhỏ, không đọc hết bảng.
List<ProductRepository.Product> page =
        repository.listAfterId(0L, 20);

// DELETE: chỉ xóa phiên bản còn khớp.
boolean deleted = repository.delete(id, latest.version);

boolean missing = !repository.findById(id).isPresent();
~~~

Lưu ý:

- `original.version` được đọc từ database, không tự ước đoán theo số lần gọi method.
- Khi `update(...)` trả `false`, caller phải xử lý xung đột hoặc bản ghi thiếu; không tự động gửi `UPDATE` bỏ điều kiện phiên bản.
- `deleted=false` không tương đương `SQLException`. Một bên là kết quả không khớp điều kiện, bên kia là lỗi truy cập dữ liệu.
- `ON DELETE CASCADE` ở schema demo làm thẻ con biến mất khi sản phẩm được xóa. Nếu không có cascade, câu DELETE có thể thất bại vì foreign key.
- Với hệ thống nhiều tenant, điều kiện `WHERE` phải bao gồm phạm vi tenant/owner được xác thực; ví dụ này chỉ minh họa sản phẩm trong một phạm vi dữ liệu duy nhất.

## 8. Đọc và cập nhật đúng: ResultSet, affected rows, version

### 8.1. READ: `executeQuery` và `Optional`

Một câu `SELECT` trả `ResultSet` và cần gọi `rs.next()`:

~~~java
try (ResultSet rs = ps.executeQuery()) {
    if (!rs.next()) {
        return Optional.empty();
    }
    // Ánh xạ bản ghi hiện tại.
}
~~~

Khi không có dòng, đây là **tình huống dữ liệu bình thường**, khác với lỗi mất DB. Không bắt `SQLException` rồi trả `Optional.empty()` vì điều đó che sự cố hạ tầng.

### 8.2. UPDATE: tránh lost update

Giả sử A và B cùng đọc sản phẩm `id=100` với `version=0`:

~~~text
A đọc version=0.
B đọc version=0.
A cập nhật quantity=11, version tăng thành 1 và commit.
B cố cập nhật quantity=9 dựa trên version=0.
~~~

SQL an toàn:

~~~sql
UPDATE catalog_product
SET name = ?, price = ?, quantity = ?,
    version = version + 1
WHERE id = ? AND version = ?;
~~~

B sẽ tác động **0 dòng** nếu lệnh của A đã commit và version là 1. Nếu bỏ `AND version = ?`, B có thể ghi đè thay đổi của A. Khi cần phân biệt `not found` với `conflict` để trả HTTP 404/409, tầng service phải có hợp đồng và xử lý race condition phù hợp.

Với cùng tên/giá/số lượng, câu UPDATE này vẫn tăng version nếu điều kiện khớp, giúp count nhất quán hơn nhưng có thể tạo phiên bản mới dù dữ liệu nghiệp vụ không đổi. Đó là quyết định thiết kế, không phải quy định của JDBC.

### 8.3. DELETE: bảo vệ bản ghi bị thay đổi

~~~sql
DELETE FROM catalog_product
WHERE id = ? AND version = ?;
~~~

- `affected == 1`, commit thành công: một bản ghi được xóa.
- `affected == 0`: không có ID đó hoặc version đã khác.
- `affected > 1`: vi phạm giả định ID duy nhất, phải báo lỗi.
- `SQLException`: lỗi DB, constraint hoặc connection; không biến thành `false`.
- Lỗi mạng lúc commit: kết quả có thể chưa xác định, không suy chắc xóa thất bại.

### 8.4. READ theo nhiều trang

`listAfterId(lastId, limit)` dùng `WHERE id > ? ORDER BY id ASC` để chọn bản ghi sau một ID. Caller lấy ID cuối của trang trước làm checkpoint cho trang sau.

~~~java
List<ProductRepository.Product> page =
        repository.listAfterId(0L, 50);

if (!page.isEmpty()) {
    long lastId = page.get(page.size() - 1).id;
    List<ProductRepository.Product> next =
            repository.listAfterId(lastId, 50);
}
~~~

Đây là keyset theo ID. **Phân trang không tự tạo snapshot**: nếu dữ liệu bị chèn/xóa/cập nhật giữa các trang, kết quả có thể thay đổi. Với báo cáo cần tính nhất quán tại một thời điểm, phải thiết kế isolation/snapshot hoặc cơ chế export riêng.

## 9. Transaction nhiều bảng: khóa sinh là đầu vào của bảng con

Hãy nhìn lịch thao tác `createWithTags`:

~~~text
BEGIN
INSERT catalog_product -> generated id = 501
INSERT product_tag(501, "office")
INSERT product_tag(501, "accessory")
COMMIT
~~~

Nếu thay thẻ thứ hai bằng `"office"` một lần nữa:

~~~text
BEGIN
INSERT catalog_product -> generated id = 502
INSERT product_tag(502, "office")
INSERT product_tag(502, "office")  -- trùng PRIMARY KEY
ROLLBACK
~~~

Một transaction thực với DBMS hỗ trợ rollback sẽ **không để lại sản phẩm 502 hoặc tag vừa chèn**, dù identity generator có thể đã tiêu thụ ID 502. Lần insert tiếp theo **không cần** dùng lại ID 502; lỗ hổng trong chuỗi ID không phải lỗi.

Điều này giải thích vì sao method phải lấy `getGeneratedKeys()` trước khi commit nhưng chỉ trả ID sau khi commit xác nhận thành công.

### Nếu mỗi thao tác có Connection riêng?

~~~java
// Sai về tính nguyên tử: insertProduct tự commit trên A,
// insertTag dùng B, rollback B không thể hủy product trên A.
long id = productDao.createWithItsOwnConnection(...);
tagDao.insertWithItsOwnConnection(id, "office");
~~~

Không thể coi hai DAO tự mở connection là một transaction chỉ vì chúng được gọi liên tiếp. Trong một service có nhiều DAO, cần truyền **cùng connection** hoặc dùng transaction manager để mọi thao tác tham gia đúng transaction.

### Savepoint có cần ở đây không?

Kịch bản yêu cầu “product và tất cả tags cùng thành công hoặc cùng thất bại”, nên rollback **toàn transaction** là hợp lý. Savepoint hữu ích khi một bước phụ có thể thất bại mà nghiệp vụ vẫn cho phép commit phần chính; tuy nhiên phải kiểm thử khả năng hỗ trợ và trạng thái transaction sau lỗi theo DBMS. Savepoint không phải transaction con có commit riêng.

## 10. Thận trọng khi COMMIT báo lỗi

Một trường hợp đặc biệt: database đã nhận `COMMIT` và ghi bền vững, nhưng phản hồi về client bị mất vì lỗi mạng. JDBC có thể ném `SQLException` dù database **đã commit**.

Hệ quả:

- `SQLException` từ `commit()` **không chứng minh** rollback.
- `rollback()` trên connection đã đứt chỉ là nỗ lực tốt nhất; không hoàn tác một commit đã hoàn tất.
- Không tự động retry tạo sản phẩm bằng một SKU hoặc operation key mới vì có thể tạo bản ghi trùng nghiệp vụ.
- Nếu SKU là định danh duy nhất thực sự của sản phẩm, có thể dùng nó để đối soát, nhưng chỉ theo **hợp đồng nghiệp vụ**.
- Với thao tác quan trọng, thiết kế **idempotency key**, unique constraint và truy vấn xác minh trạng thái qua connection mới khi database phục hồi.

Thao tác auto-commit một câu SQL cũng có thể có **outcome bất định** nếu phản hồi bị mất. Việc chủ động quản lý transaction giúp xác định ranh giới, nhưng không tự giải quyết được vấn đề mất phản hồi khi commit.

## 11. Kiểm thử tích hợp CRUD, khóa sinh và rollback

Mock `Connection` có thể xác nhận method được gọi, nhưng không chứng minh database thực sự sinh khóa hoặc rollback đúng. Cần **database test với đúng driver/DBMS** hoặc ít nhất một suite tích hợp gần production.

### Ma trận kiểm thử

| Tình huống | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Insert bình thường | Tạo sản phẩm mới | Nhận ID, `findById` thấy đúng SKU/giá/số lượng |
| Generated key | Không gửi cột `id` | Driver trả ID đúng bản ghi vừa tạo |
| Không có ID | `findById` với ID chưa tồn tại | `Optional.empty()` |
| SKU trùng | Hai lần tạo cùng SKU | Lần thứ hai lỗi constraint, bản gốc không bị ghi đè |
| Update thành công | Dùng version hiện tại | Dữ liệu đổi, version tăng |
| Update stale | Dùng version cũ | Trả `false`, không ghi đè |
| Delete stale | Xóa bằng version cũ | Trả `false` |
| Delete thành công | Xóa bằng version hiện tại | Bản ghi biến mất |
| Insert nhiều tag | Product + tags thành công | Đều quan sát được sau commit |
| Tag trùng | Hai tag giống nhau trong cùng transaction | Toàn bộ product và tag chưa commit bị rollback |
| Input sai | Giá âm, quantity âm, name rỗng | Validation từ chối |
| Precision | Giá `123.45`, Unicode name | Đọc lại đúng |
| Trang nhỏ | `listAfterId` | Thứ tự tăng, số dòng không vượt limit |
| Hai update đồng thời | Cùng expectedVersion | Không thể cả hai cùng ghi đè dựa trên cùng version cũ |

### Ví dụ JUnit 5

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Arrays;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;

final class ProductRepositoryIT {
    // TestDb là fixture của dự án, KHÔNG thuộc Java/JDBC.
    // DataSource trỏ đến database/schema TEST đã tạo hai bảng.
    private final DataSource ds = TestDb.dataSource();
    private final ProductRepository repo =
            new ProductRepository(ds);

    @Test
    void fullCrudRoundTrip() throws Exception {
        String sku = "SKU-" + UUID.randomUUID();

        long id = repo.create(
                sku, "Bàn phím",
                new BigDecimal("123.45"), 8);

        try {
            ProductRepository.Product before =
                    repo.findById(id).get();

            assertEquals(sku, before.sku);
            assertEquals("Bàn phím", before.name);
            assertEquals(0, before.price.compareTo(
                    new BigDecimal("123.45")));
            assertEquals(8, before.quantity);
            assertEquals(0L, before.version);

            assertTrue(repo.update(
                    id, before.version, "Bàn phím mới",
                    new BigDecimal("130.00"), 6));

            // Version cũ không còn hợp lệ.
            assertFalse(repo.update(
                    id, before.version, "Ghi đè",
                    new BigDecimal("1.00"), 1));

            ProductRepository.Product after =
                    repo.findById(id).get();

            assertEquals("Bàn phím mới", after.name);
            assertEquals(1L, after.version);

            assertFalse(repo.delete(id, before.version));
            assertTrue(repo.delete(id, after.version));
            assertFalse(repo.findById(id).isPresent());

        } finally {
            cleanupProduct(id);
        }
    }

    @Test
    void duplicateTagRollsBackProduct() throws Exception {
        String sku = "SKU-" + UUID.randomUUID();

        // PRIMARY KEY(product_id, tag) ở product_tag
        // khiến lần INSERT thẻ thứ hai thất bại.
        assertThrows(java.sql.SQLException.class,
                () -> repo.createWithTags(
                        sku, "Chuột thử nghiệm",
                        new BigDecimal("50.00"), 2,
                        Arrays.asList("same", "same")));

        // Một connection mới quan sát dữ liệu đã commit.
        try (Connection c = ds.getConnection();
             PreparedStatement ps = c.prepareStatement(
                     "SELECT COUNT(*) FROM catalog_product "
                   + "WHERE sku = ?")) {

            ps.setString(1, sku);
            try (ResultSet rs = ps.executeQuery()) {
                assertTrue(rs.next());
                assertEquals(0, rs.getInt(1));
            }
        }
    }

    private void cleanupProduct(long id) throws Exception {
        // Chỉ trên database test! ON DELETE CASCADE dọn tags.
        try (Connection c = ds.getConnection();
             PreparedStatement ps = c.prepareStatement(
                     "DELETE FROM catalog_product WHERE id = ?")) {
            ps.setLong(1, id);
            ps.executeUpdate();
        }
    }
}
~~~

**Chú ý về khả năng chạy:** `TestDb.dataSource()` là phần cần được dự án tự cung cấp qua một database test, JDBC driver và migration; không phải một lớp có sẵn của JDK. Nếu DataSource dùng transaction do framework quản lý, cần điều chỉnh fixture đúng hợp đồng ở mục 5.

**Chú ý về cleanup:** `finally` có thể ném lỗi cleanup và che assertion failure; suite test lớn nên bảo toàn lỗi gốc và gắn cleanup exception dưới dạng suppressed. Không chạy lệnh xóa toàn bộ bảng trên môi trường dùng chung hoặc production.

### Những ca cần bổ sung

- Tạo hai sản phẩm trên hai connection khác nhau, đối chiếu generated ID với SKU để phát hiện nhầm khóa.
- Test tên có dấu nháy đơn, Unicode, giá `0.00` và giá có scale không hợp lệ.
- Test `getGeneratedKeys` không hỗ trợ hoặc driver trả sai tên/thứ tự cột; có fallback theo dialect được kiểm chứng.
- Test unique constraint và SQLState theo DBMS thật, **không suy mọi mã lớp 23 đều là duplicate key**.
- Test concurrent update thực bằng hai connection và cơ chế điều phối có timeout.
- Test lỗi mạng quanh commit và quy trình đối soát, không giả định mọi lần lỗi đều rollback.
- Test `getConnection()`/query timeout và việc pool loại connection chết, không rò connection khi exception.
- Test phân trang khi có nhiều bản ghi hơn giới hạn, bảo đảm không lấy thiếu/trùng vì thứ tự không ổn định.

## 12. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ghép `sku`/`name` thẳng vào SQL | Injection, lỗi cú pháp | `PreparedStatement` và `?` |
| Dùng `?` cho tên bảng/cột | Sai ngữ nghĩa SQL | SQL cố định/allowlist |
| Quên `RETURN_GENERATED_KEYS` | Driver có thể không trả key | Tạo statement với cờ thích hợp |
| Gọi `getGeneratedKeys` sau khi statement đóng | ResultSet không hợp lệ | Đọc trong phạm vi statement |
| Dùng `SELECT MAX(id)` | Lấy nhầm ID của transaction khác | `getGeneratedKeys` hoặc dialect `RETURNING` |
| Trả ID trước khi commit | Caller hiểu nhầm dữ liệu đã bền vững | Trả sau commit |
| Coi ID phải liên tục | Báo lỗi sai sau rollback | Không dùng ID như bộ đếm liên tục |
| Dùng `double` cho giá | Sai số nhị phân | `BigDecimal`/`DECIMAL` |
| Không dùng `wasNull()` sau getter primitive | Nhầm SQL NULL với 0 | Kiểm tra ngay sau getter |
| UPDATE không có version khi concurrency | Lost update | `WHERE version=?` và tăng version |
| INSERT product/tag bằng hai connection | Partial commit | Một connection/transaction |
| Bắt SQLException rồi trả `false`/empty | Che lỗi hạ tầng | Phân biệt dữ liệu thiếu và SQL error |
| Reset `autoCommit=true` trước rollback | Có thể commit ngoài ý muốn | Kết thúc transaction trước khi reset |
| Đọc toàn bộ bảng vào List | Hết heap/GC lớn | Giới hạn, keyset, cursor |
| Retry INSERT sau commit timeout | Tạo trùng dữ liệu | Idempotency và đối soát |
| Test chỉ bằng mock | Không chứng minh driver hay transaction | Integration test DBMS thật |

## 13. Bài tập tự luyện

### Bài 1 — Tự chèn và đọc khóa sinh

Hãy tạo một `PreparedStatement` cho `catalog_product`, bind bốn giá trị, gọi `executeUpdate()` rồi `getGeneratedKeys()`. Kiểm tra affected rows, khóa khác SQL NULL và dùng connection mới để đọc sau commit.

**Gợi ý:** Dùng `Statement.RETURN_GENERATED_KEYS` khi tạo statement và đọc khóa trước khi statement đóng.

### Bài 2 — Vì sao dấu ? không thay bảng?

~~~java
PreparedStatement ps = connection.prepareStatement(
        "SELECT * FROM ?");
ps.setString(1, "catalog_product");
~~~

**Hỏi:** Điều gì sai? Nếu API cần chọn một trong hai bảng cố định, nên làm gì?

**Gợi ý:** Dấu `?` chỉ là placeholder **giá trị**; tạo một allowlist chọn giữa hai SQL query cố định.

### Bài 3 — Tránh sai độ chính xác

Vì sao `new BigDecimal(0.1)` có thể gây kết quả không mong muốn? Nếu cột là `DECIMAL(18,2)`, cách tạo giá minh bạch hơn là gì?

**Gợi ý:** Dùng `new BigDecimal("0.10")` và quy tắc scale/rounding rõ ràng; không lấy trực tiếp biểu diễn nhị phân của `double`.

### Bài 4 — Lost update

Hai request cùng đọc `version=4`. A cập nhật thành công rồi commit version 5. B dùng `WHERE version=4`. Hỏi B tác động mấy dòng và nên làm gì?

**Gợi ý:** 0; trả conflict/tải dữ liệu mới thay vì ghi đè mù.

### Bài 5 — Rollback nhiều câu SQL

Một transaction sinh ID 501, tạo product và gắn một thẻ thành công; thẻ thứ hai trùng và lỗi. Sau rollback, sản phẩm có còn không? Identity 501 có bắt buộc được dùng lại không?

**Gợi ý:** Product chưa commit phải bị rollback; ID có thể bị bỏ qua do sequence/identity không rollback như dữ liệu hàng.

### Bài 6 — Xóa có điều kiện

Caller giữ version 2; người khác cập nhật thành 3. `DELETE WHERE id=? AND version=2` trả gì? Tại sao không tự xóa lại bằng version 3?

**Gợi ý:** 0; bản ghi đã thay đổi nên người dùng cần quyết định lại theo dữ liệu mới.

### Bài 7 — Kiểm thử generated key thật

Thiết kế test chạy hai INSERT ở hai connection, so sánh generated ID và dữ liệu đọc lại. Vì sao test đó mạnh hơn `verify(ps).getGeneratedKeys()` trên một mock?

**Gợi ý:** Nó chứng minh DBMS/driver thật trả ID của đúng bản ghi và transaction đã commit.

### Bài 8 — Lỗi mạng khi commit

`commit()` ném `SQLException` sau khi client gửi yêu cầu. Có thể kết luận chưa tạo sản phẩm không? Khi retry cần thiết kế thêm gì?

**Gợi ý:** Không. Cần idempotency key, unique constraint và xác minh trạng thái nghiệp vụ trên connection mới sau khi database phục hồi.

## 14. Checklist hoàn thành thực hành

- [ ] SQL có cấu trúc cố định, mọi giá trị đầu vào đều bind bằng `PreparedStatement`.
- [ ] Không cố bind identifier, tên bảng hoặc hướng `ORDER BY` bằng `?`.
- [ ] Schema có primary key sinh tự động và constraint phù hợp.
- [ ] INSERT không cung cấp cột ID; statement yêu cầu `RETURN_GENERATED_KEYS`.
- [ ] `getGeneratedKeys()` được đọc khi statement còn mở và có kiểm tra khóa trả về.
- [ ] Không dùng `SELECT MAX(id)` hay suy đoán ID liên tiếp.
- [ ] Các INSERT liên quan sử dụng cùng `Connection` và chỉ commit khi hoàn tất.
- [ ] `ResultSet` được ánh xạ đúng kiểu; SQL NULL được phân biệt với giá trị mặc định.
- [ ] UPDATE/DELETE kiểm tra số dòng tác động và trạng thái phiên bản.
- [ ] READ nhiều dòng có giới hạn/phân trang và không nạp hết dữ liệu vào RAM.
- [ ] Lỗi SQL không bị biến thành kết quả “không có bản ghi”.
- [ ] Rollback giữ lỗi gốc; commit outcome bất định có chính sách đối soát.
- [ ] Tài nguyên JDBC được đóng bằng `try-with-resources`.
- [ ] Có integration test với DBMS/driver đích cho CRUD, generated keys, unique, rollback và optimistic locking.
- [ ] Dữ liệu test được cô lập và không tác động môi trường production.

**Kết luận:** Một bài thực hành CRUD bằng **JDBC** hoàn chỉnh phải kết hợp **`PreparedStatement` tham số hóa**, **`getGeneratedKeys()` lấy ID do database sinh**, **`ResultSet` để đọc dữ liệu**, cùng **transaction và rollback** để bảo đảm các bước ghi có liên quan được thực hiện nguyên tử. Kiểm tra affected rows, phiên bản cập nhật, SQL NULL, phân trang và chạy integration test trên DBMS/driver thật sẽ giúp đưa mẫu DAO/Repository này từ bài học cơ bản thành một nền tảng đáng tin cậy cho ứng dụng Java truy cập dữ liệu quan hệ.
