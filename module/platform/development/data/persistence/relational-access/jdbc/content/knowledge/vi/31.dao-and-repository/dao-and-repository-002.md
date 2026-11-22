# Thiết kế hợp đồng trả một đối tượng, nhiều đối tượng và không có dữ liệu trong JDBC

Một phương thức DAO hoặc Repository không chỉ thực thi SQL. Nó còn phải nói rõ **người gọi sẽ nhận được gì** khi truy vấn trả đúng một hàng, nhiều hàng hoặc không có hàng nào. Nếu hợp đồng không rõ, hai lập trình viên có thể hiểu khác nhau về `null`, danh sách rỗng, `Optional.empty()` và ngoại lệ, dẫn đến lỗi `NullPointerException`, bỏ qua dữ liệu hoặc coi một lỗi database là “không tìm thấy”.

Ví dụ, cùng tra cứu sản phẩm, ba nghiệp vụ có thể cần ba cách trả kết quả khác nhau:

- Trang chi tiết tìm sản phẩm theo ID: sản phẩm **có thể tồn tại hoặc không**, phù hợp với `Optional<Product>`.
- Xuất danh sách theo danh mục: có thể nhận **0, 1 hoặc nhiều sản phẩm**, phù hợp với `List<Product>`.
- Xử lý một đơn hàng đã xác thực tham chiếu sản phẩm bắt buộc: nếu không có sản phẩm thì đó là **lỗi nghiệp vụ**, phù hợp với một đối tượng `Product` hoặc ngoại lệ `ProductNotFoundException`.

Bài thuộc chương **DAO và Repository** của module JDBC. Nội dung tập trung vào việc thiết kế hợp đồng trả về có ý nghĩa, triển khai bằng `DataSource`, `PreparedStatement` và `ResultSet`, phân biệt “không có hàng” với “cột SQL là NULL”, xử lý kết quả bất thường, bảo đảm tài nguyên và transaction, cũng như kiểm thử những tình huống 0/1/nhiều hàng.

## 1. Bắt đầu từ lực lượng kết quả (cardinality)

**Cardinality** ở đây là số hàng mà một thao tác đọc *được phép* trả về theo quy tắc nghiệp vụ. Hãy quyết định cardinality **trước khi** chọn kiểu Java.

| Hợp đồng truy vấn | Số hàng hợp lệ | Kiểu trả về gợi ý | Khi 0 hàng | Khi nhiều hơn giới hạn |
|---|---:|---|---|---|
| Tìm đối tượng tùy chọn theo khóa | 0 hoặc 1 | `Optional<T>` | `Optional.empty()` | Lỗi bất biến nếu thực sự trả trên 1 hàng |
| Lấy đối tượng bắt buộc | Đúng 1 | `T` | Ngoại lệ “không tìm thấy” có nghĩa nghiệp vụ | Ngoại lệ vi phạm tính duy nhất |
| Tìm mọi đối tượng thỏa điều kiện | 0 đến N | `List<T>` | Danh sách rỗng | Tất cả hàng hợp lệ, hoặc chia trang nếu lớn |
| Kiểm tra tồn tại | `true` hoặc `false` | `boolean` | `false` | Không cần ánh xạ cả đối tượng |
| Đếm các đối tượng | Một giá trị đếm | `long` | `0` nếu không khớp hàng nào | Không liên quan đến số hàng của `ResultSet` tổng hợp |
| Lấy một trang | 0 đến giới hạn trang | `Page<T>` / cấu trúc kết quả riêng | Trang có `items` rỗng | Cần chuyển sang trang tiếp theo |
| Chạy lệnh cập nhật/xóa | Số hàng bị tác động | `int` hoặc kết quả nghiệp vụ riêng | Thường là `0` hàng tác động | Tùy lệnh, có thể là lỗi bất biến |

Bảng này không có nghĩa mọi repository phải hỗ trợ tất cả kiểu. **Một phương thức chỉ nên có một hợp đồng rõ ràng**. Tên và kiểu trả về phải giúp người gọi hiểu được sự khác biệt giữa “không tìm thấy” và “thất bại khi truy cập dữ liệu”.

### 1.1. Bảng quyết định theo kết quả 0, 1 và 2+ hàng

| Kết quả SQL thực tế | `findById(): Optional<Product>` | `getRequiredById(): Product` | `listByCategory(): List<Product>` |
|---|---|---|---|
| 0 hàng | `Optional.empty()` | Ném `ProductNotFoundException` | `List.of()` hoặc danh sách rỗng khác |
| 1 hàng | `Optional.of(product)` | Trả `product` | Danh sách một phần tử |
| 2+ hàng | **Không hợp lệ** nếu hợp đồng là tối đa một; phải báo lỗi | **Không hợp lệ**; không tùy tiện lấy hàng đầu | Danh sách có nhiều phần tử |
| Lỗi JDBC | Ném/biến đổi ngoại lệ theo chính sách | Ném/biến đổi ngoại lệ theo chính sách | Ném/biến đổi ngoại lệ theo chính sách |

**Không biến `SQLException` thành `Optional.empty()` hoặc danh sách rỗng.** Lỗi kết nối, thiếu bảng và lỗi cú pháp SQL không phải là trường hợp không có dữ liệu; che lỗi sẽ khiến giao diện hiển thị “không tìm thấy” dù hệ thống đang hỏng.

## 2. Ba khái niệm rất dễ bị nhầm

Cần phân biệt **không có hàng**, **có hàng nhưng cột là `NULL`** và **có hàng với giá trị rỗng**.

Giả sử chạy:

```sql
SELECT id, sku, parent_product_id
FROM catalog_products
WHERE id = ?;
```

Ba kết quả khác nhau:

1. **Không có hàng:** `rs.next()` trả `false` ngay lần đầu. Không có `Product` nào để ánh xạ.
2. **Có hàng nhưng `parent_product_id IS NULL`:** `rs.next()` là `true`. Phải trả một `Product` hợp lệ có trường `parentProductId == null`, không phải `Optional.empty()`.
3. **Có hàng và một cột văn bản là chuỗi rỗng:** `rs.next()` là `true`, giá trị cột có thể là `""`. Quy tắc nghiệp vụ quyết định chuỗi rỗng có hợp lệ không. Một số DBMS (đặc biệt Oracle với chuỗi ký tự thông thường) có ngữ nghĩa chuỗi rỗng khác; cần kiểm chứng trên DBMS cụ thể.

```text
ResultSet.next()
      |
      +-- false --------------------> Không có đối tượng
      |                                   Optional.empty()
      |                                   hoặc List.of()
      |
      +-- true ---------------------> Có một hàng
                                         |
                                         +-- cột nullable: SQL NULL
                                         |         -> trường Java null
                                         |
                                         +-- cột không null
                                                   -> giá trị Java
```

Không nên dùng `Optional<Product>` để biểu diễn “có product nhưng cột price NULL”. `Optional` bên ngoài mô tả **sự hiện diện của cả đối tượng**, còn tính nullable của từng thuộc tính là hợp đồng mô hình dữ liệu.

### 2.1. Đọc cột số nullable đúng cách

Với `ResultSet.getLong(...)`, JDBC trả `0L` khi cột SQL là `NULL`. Vì vậy cần kiểm tra `wasNull()` **ngay sau** lần đọc:

```java
long rawParentId = rs.getLong("parent_product_id");
Long parentId = rs.wasNull() ? null : rawParentId;
```

Không làm như sau:

```java
// Sai: không thể biết 0 là dữ liệu thật hay SQL NULL.
Long parentId = rs.getLong("parent_product_id");
```

Có thể dùng `rs.getObject("parent_product_id", Long.class)` trên driver hỗ trợ typed getter phù hợp, nhưng hành vi chuyển kiểu cần kiểm thử với JDBC driver thực tế. Cách dùng `getLong` + `wasNull` là minh họa minh bạch cho vấn đề nullable primitive.

### 2.2. Kết quả của `COUNT(*)` vẫn có một hàng

`SELECT COUNT(*) FROM catalog_products WHERE category = ?` **không trả không hàng** khi không có sản phẩm nào khớp, nếu không có `GROUP BY`. Nó trả **một hàng** với giá trị `0`.

```java
try (ResultSet rs = ps.executeQuery()) {
    if (!rs.next()) {
        throw new SQLException("COUNT(*) không trả hàng như kỳ vọng");
    }
    long total = rs.getLong(1); // Có thể bằng 0.
}
```

Với `GROUP BY`, câu truy vấn tổng hợp có thể **không trả hàng** nếu không có nhóm thỏa điều kiện. Đừng thiết kế một helper “hễ không có entity thì SQL không có ResultSet row” áp dụng bừa cho mọi dạng SQL.

## 3. Chọn kiểu trả về từ ý nghĩa nghiệp vụ

### 3.1. `Optional<T>` cho truy vấn trả tối đa một đối tượng

Ví dụ:

```java
Optional<Product> findById(long id) throws SQLException;
Optional<Product> findBySku(String sku) throws SQLException;
```

Người gọi phải xem xét nhánh không có dữ liệu, thay vì nhận `null` bất ngờ.

```java
Optional<Product> found = repository.findById(100L);

found.ifPresent(product ->
        System.out.println("SKU: " + product.sku()));

Product product = repository.findById(100L)
        .orElseThrow(() -> new ProductNotFoundException(100L));
```

**Không gọi `optional.get()` mà không kiểm tra**, bởi nó có thể ném `NoSuchElementException` không có ngữ cảnh nghiệp vụ. Nếu sự vắng mặt là bình thường, có thể dùng `ifPresent`, `map`, `orElse` hoặc `isEmpty`. Nếu sự vắng mặt là lỗi, dùng `orElseThrow` với ngoại lệ thích hợp.

`Optional<T>` thường phù hợp **ở kiểu trả về của method**; không nhất thiết cần dùng làm field của entity hoặc cho mọi tham số phương thức. Tránh trả `null` từ một method đã khai báo `Optional<T>`: điều đó phá vỡ chính hợp đồng tránh null.

### 3.2. `T` cho đối tượng bắt buộc

Ví dụ:

```java
Product getRequiredById(long id) throws SQLException;
```

Method này có lời hứa **trả một đối tượng hoặc báo lý do không thể trả**. Khi không tìm thấy sản phẩm, có thể ném một ngoại lệ domain như `ProductNotFoundException`.

Không cần ném `SQLException` chỉ để biểu diễn ID không tồn tại: database vẫn hoạt động bình thường và SQL vẫn hợp lệ. `SQLException` dành cho lỗi truy cập dữ liệu hoặc sự cố DBMS/driver.

Một lựa chọn khác là để tầng service lấy `Optional<Product>` rồi quyết định điều gì được coi là bắt buộc. Trong nhiều dự án, cách này làm repository đơn giản hơn; không có yêu cầu phải tạo cả `findById` lẫn `getRequiredById` nếu không có tình huống dùng.

### 3.3. `List<T>` cho kết quả 0 đến nhiều đối tượng

Ví dụ:

```java
List<Product> listByCategory(String category) throws SQLException;
```

Không có dữ liệu phải cho danh sách **rỗng**, không phải `null`. Điều đó cho phép người gọi dùng an toàn:

```java
for (Product product : repository.listByCategory("books")) {
    System.out.println(product.sku());
}
```

Không phải thêm:

```java
// Không nên cần thiết khi repository giữ đúng hợp đồng:
if (products != null) {
    for (Product product : products) {
        // ...
    }
}
```

Danh sách rỗng đại diện một **kết quả truy vấn hợp lệ**. Tùy thiết kế, repository có thể trả `List.copyOf(items)` để người gọi không sửa được cấu trúc danh sách, hoặc trả một danh sách mới có thể sửa; nên ghi rõ lựa chọn trong API.

### 3.4. `Page<T>` và `Stream<T>` không thay thế trực tiếp `List<T>`

Nếu truy vấn có thể trả hàng trăm nghìn bản ghi, `List<T>` sẽ giữ toàn bộ dữ liệu đã ánh xạ trong bộ nhớ. Khi đó cần **phân trang** hoặc một abstraction streaming có vòng đời tài nguyên rõ ràng.

Tuy nhiên, `Stream<Product>` trả ra từ DAO **không tự an toàn hơn** `List<Product>`: nếu stream còn phụ thuộc `ResultSet` và connection đã đóng, việc duyệt sau đó sẽ thất bại. Nếu cần stream thật, API phải giao trách nhiệm đóng `ResultSet`/`Connection` rõ ràng hoặc nhận callback xử lý trong scope còn mở.

## 4. Xác định hợp đồng qua tên phương thức

Tên phương thức nên giúp đoán được số lượng kết quả và cách xử lý vắng mặt:

| Tên ví dụ | Hợp đồng phù hợp | Tránh hiểu nhầm |
|---|---|---|
| `findById` | `Optional<Product>` | Không giả định ID luôn tồn tại |
| `getRequiredById` | `Product` hoặc ngoại lệ not found | Không trả `null` khi thiếu |
| `findBySku` | `Optional<Product>` nếu SKU có tính duy nhất | Phải có unique constraint hoặc quy tắc xử lý 2+ hàng |
| `listByCategory` | `List<Product>` | Danh mục rỗng không phải lỗi |
| `existsById` | `boolean` | Không cần SELECT mọi cột rồi ánh xạ Product |
| `countByCategory` | `long` | 0 là một giá trị đếm hợp lệ |
| `findPageByCategory` | `Page<Product>` | Phân biệt “trang rỗng” và “còn trang sau” |
| `deleteById` | `boolean` hoặc số hàng bị xóa | 0 hàng bị xóa không nhất thiết là lỗi SQL |

Một method tên `findOneByCategory` nhưng không nói rõ khi hai sản phẩm cùng danh mục là một thiết kế dễ gây lỗi. Nếu không có ràng buộc duy nhất, cần chọn một trong hai ý định:

- **Tối đa một:** kiểm tra nếu nhiều hơn một hàng thì báo lỗi hợp đồng.
- **Chọn một trong nhiều:** đặt tên có ý nghĩa như `findLatestByCategory` và dùng `ORDER BY ...` theo tiêu chí nghiệp vụ, kèm giới hạn kết quả.

**Đừng dùng `LIMIT 1` để che một lỗi dữ liệu trùng** khi nghiệp vụ đòi đúng một bản ghi duy nhất.

## 5. Schema và mô hình dùng trong bài

Ta xây một DAO/Repository đọc sản phẩm từ bảng `catalog_products`. DDL gần với SQL quan hệ thông dụng; khi chạy thật có thể cần chỉnh kiểu dữ liệu hoặc cú pháp theo DBMS.

```sql
CREATE TABLE catalog_products (
    id                BIGINT PRIMARY KEY,
    sku               VARCHAR(64) NOT NULL UNIQUE,
    category          VARCHAR(80) NOT NULL,
    price             DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    parent_product_id BIGINT NULL,
    CONSTRAINT fk_product_parent
        FOREIGN KEY (parent_product_id)
        REFERENCES catalog_products(id)
);

INSERT INTO catalog_products
    (id, sku, category, price, parent_product_id)
VALUES
    (100, 'JDBC-BOOK', 'books', 120000.00, NULL),
    (101, 'JAVA-BOOK', 'books', 85000.00, 100),
    (102, 'JDBC-MUG',  'gifts', 40000.00, NULL);
```

Từ dữ liệu trên:

- `id=100` trả một sản phẩm.
- `id=999` không có sản phẩm.
- `category='books'` trả **hai** sản phẩm.
- `category='unknown'` trả **danh sách rỗng**.
- `parent_product_id` của sản phẩm 100 là SQL NULL; sản phẩm vẫn **tồn tại**.
- `sku` có `UNIQUE`, nên `findBySku` có hợp đồng tối đa một đối tượng được DB bảo vệ.

### 5.1. Model Java

Ví dụ dùng Java 17+ để có `record`:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record Product(
        long id,
        String sku,
        String category,
        BigDecimal price,
        Long parentProductId) {

    public Product {
        if (id <= 0) {
            throw new IllegalArgumentException("ID phải dương");
        }
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(category, "category");
        Objects.requireNonNull(price, "price");

        if (sku.isBlank() || category.isBlank()
                || price.signum() < 0) {
            throw new IllegalArgumentException(
                    "Thông tin sản phẩm không hợp lệ");
        }
    }
}
```

`parentProductId` là `Long`, không phải primitive `long`, để biểu diễn khi cột SQL có giá trị NULL. Trong ví dụ này model không được tạo nếu thiếu ID, SKU, danh mục hoặc giá; những trường đó cũng có constraint ở schema.

### 5.2. Ngoại lệ nghiệp vụ cho đối tượng bắt buộc

```java
public final class ProductNotFoundException
        extends RuntimeException {

    public ProductNotFoundException(long productId) {
        super("Không tìm thấy sản phẩm id=" + productId);
    }
}
```

Đây là một lựa chọn thiết kế, không phải ngoại lệ có sẵn của JDBC. Trong API HTTP, service có thể biến tình trạng không tìm thấy thành phản hồi 404 khi phù hợp; ở một nghiệp vụ khác, nó có thể là lỗi xác thực quan hệ dữ liệu hoặc một sự kiện cần xử lý. **Repository không nên tự mã hóa status HTTP vào lớp dữ liệu**.

## 6. Ví dụ đầy đủ: Repository với hợp đồng nhất quán

Lớp sau dùng `javax.sql.DataSource` và các API JDBC chuẩn. Từng method đọc mở một logical `Connection`, đóng `PreparedStatement` và `ResultSet` bằng `try-with-resources`, rồi trả **đối tượng Java đã ánh xạ**, không trả tài nguyên JDBC còn sống.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class JdbcProductRepository {
    private static final String COLUMNS =
            "id, sku, category, price, parent_product_id";

    private final DataSource dataSource;

    public JdbcProductRepository(DataSource dataSource) {
        this.dataSource =
                Objects.requireNonNull(dataSource, "dataSource");
    }

    /** Hợp đồng: 0 hoặc 1 đối tượng. */
    public Optional<Product> findById(long id) throws SQLException {
        requirePositiveId(id);

        String sql = "SELECT " + COLUMNS
                + " FROM catalog_products WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                return readAtMostOne(rs);
            }
        }
    }

    /** Hợp đồng: một đối tượng hoặc lỗi nghiệp vụ. */
    public Product getRequiredById(long id) throws SQLException {
        return findById(id).orElseThrow(
                () -> new ProductNotFoundException(id));
    }

    /** Hợp đồng: 0 hoặc 1; cột sku được DB đặt UNIQUE. */
    public Optional<Product> findBySku(String sku)
            throws SQLException {

        requireNonBlank(sku, "sku");

        String sql = "SELECT " + COLUMNS
                + " FROM catalog_products WHERE sku = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, sku);

            try (ResultSet rs = ps.executeQuery()) {
                return readAtMostOne(rs);
            }
        }
    }

    /** Hợp đồng: danh sách rỗng hoặc nhiều đối tượng; không null. */
    public List<Product> listByCategory(String category)
            throws SQLException {

        requireNonBlank(category, "category");

        String sql = "SELECT " + COLUMNS
                + " FROM catalog_products "
                + "WHERE category = ? ORDER BY id";

        List<Product> products = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, category);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    products.add(mapProduct(rs));
                }
            }
        }

        // Trả snapshot danh sách, không lộ danh sách mutable nội bộ.
        return List.copyOf(products);
    }

    /** Hợp đồng: true nếu có ít nhất một hàng phù hợp. */
    public boolean existsById(long id) throws SQLException {
        requirePositiveId(id);

        String sql =
                "SELECT 1 FROM catalog_products WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                return rs.next();
            }
        }
    }

    /** Hợp đồng: số hàng phù hợp, bao gồm 0. */
    public long countByCategory(String category)
            throws SQLException {

        requireNonBlank(category, "category");

        String sql = "SELECT COUNT(*) "
                + "FROM catalog_products WHERE category = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setString(1, category);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                            "COUNT(*) không trả hàng như kỳ vọng");
                }

                return rs.getLong(1);
            }
        }
    }

    /**
     * Đọc tối đa một đối tượng.
     *
     * Nếu result set có 2+ hàng, dữ liệu/SQL vi phạm hợp đồng;
     * không im lặng chọn hàng đầu.
     */
    private static Optional<Product> readAtMostOne(ResultSet rs)
            throws SQLException {

        if (!rs.next()) {
            return Optional.empty();
        }

        Product first = mapProduct(rs);

        if (rs.next()) {
            throw new SQLException(
                    "Truy vấn vi phạm hợp đồng tối đa một sản phẩm");
        }

        return Optional.of(first);
    }

    private static Product mapProduct(ResultSet rs)
            throws SQLException {

        long id = rs.getLong("id");
        String sku = rs.getString("sku");
        String category = rs.getString("category");
        BigDecimal price = rs.getBigDecimal("price");

        long rawParentId = rs.getLong("parent_product_id");
        Long parentProductId =
                rs.wasNull() ? null : rawParentId;

        return new Product(
                id, sku, category, price, parentProductId);
    }

    private static void requirePositiveId(long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("ID phải dương");
        }
    }

    private static void requireNonBlank(
            String value, String field) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " không được rỗng");
        }
    }
}
```

Các lớp `Product`, `ProductNotFoundException` và `JdbcProductRepository` có thể được đặt vào những tệp Java riêng trong cùng package. Mẫu trên sử dụng Java 17+; các lệnh SQL sử dụng cấu trúc phổ biến, cần kiểm chứng và điều chỉnh nếu DBMS có quy tắc riêng.

### 6.1. Vì sao `readAtMostOne(...)` cần gọi `next()` hai lần?

Đọc một object chưa đủ chứng minh truy vấn trả **tối đa một** hàng:

```java
if (rs.next()) {
    return Optional.of(mapProduct(rs));
}
return Optional.empty();
```

Đoạn trên sẽ **âm thầm bỏ qua** hàng thứ hai nếu dữ liệu bị trùng hoặc SQL không bảo đảm uniqueness. Trong repository mẫu, gọi thêm `rs.next()` để phát hiện tình trạng 2+ hàng, rồi ném `SQLException` thể hiện một lỗi hợp đồng dữ liệu.

Với `findById`, khóa chính làm tình huống 2+ hàng không thể xảy ra nếu database thực thi constraint đúng. Với `findBySku`, ràng buộc `UNIQUE` bảo vệ điều tương tự. Kiểm tra thêm là biện pháp phòng thủ, **không thay thế unique constraint** trong database.

Ở hệ thống có nhiều hàng hoặc muốn tránh driver fetch thừa, có thể giới hạn kết quả để chỉ đọc **tối đa hai hàng** khi xác minh “at most one”, nhưng cú pháp SQL `LIMIT 2`, `FETCH FIRST 2 ROWS ONLY` hoặc biến thể khác tùy DBMS. Dù có giới hạn, vẫn phải kiểm tra nếu nhận được hàng thứ hai.

### 6.2. Vì sao trả `List.copyOf(products)`?

Đối với `listByCategory`, kết quả trả về là danh sách đã ánh xạ hoàn toàn trước khi đóng JDBC resources. `List.copyOf(...)` tạo danh sách **không cho phép thêm/xóa phần tử**, giúp người gọi không sửa nhầm cấu trúc snapshot mà repository trả ra.

Tuy nhiên, danh sách bất biến **không làm các object con tự động bất biến**. Ở đây `Product` là `record` với các kiểu field sử dụng trong ví dụ có ngữ nghĩa bất biến phù hợp. Nếu `Product` chứa đối tượng mutable, người gọi vẫn có thể đổi state của đối tượng con trừ khi model cũng bảo vệ nó.

Không bắt buộc mọi repository trả immutable list; quan trọng là **hợp đồng nhất quán** và người dùng API biết họ có thể sửa danh sách hay không.

### 6.3. Vì sao mọi method không tự viết `catch(SQLException)` rồi trả rỗng?

Ví dụ:

```java
// CÁCH LÀM SAI:
public Optional<Product> findById(long id) {
    try {
        // ... truy vấn DB
    } catch (SQLException error) {
        return Optional.empty(); // Che giấu sự cố hạ tầng!
    }
}
```

Khi database mất kết nối, người gọi sẽ nhận `Optional.empty()` và có thể kết luận sản phẩm không tồn tại, trong khi kết quả thực sự là **không thể truy cập dữ liệu**. Repository trong bài chọn khai báo `throws SQLException` để giữ minh bạch.

Trong ứng dụng lớn, có thể bọc `SQLException` thành ngoại lệ hạ tầng riêng như `DataAccessException`, nhưng phải **giữ cause**, SQLSTATE và loại lỗi phù hợp để dễ quan sát, không đổi nó thành “not found” hoặc danh sách rỗng.

## 7. Cách sử dụng Repository ở tầng service

Giả sử cần hiển thị trang chi tiết sản phẩm theo URL. Trường hợp không thấy là một kết quả hợp lệ của truy vấn:

```java
Optional<Product> found = repository.findById(100L);

if (found.isPresent()) {
    Product product = found.get();
    System.out.println("Chi tiết: " + product.sku());
} else {
    System.out.println("Không tìm thấy sản phẩm");
}
```

Có thể viết gọn hơn bằng `ifPresentOrElse(...)` khi không cần trả kết quả:

```java
repository.findById(999L).ifPresentOrElse(
        product -> System.out.println(product.sku()),
        () -> System.out.println("Không tìm thấy")
);
```

Trong nghiệp vụ tạo đơn hàng, có thể yêu cầu sản phẩm phải tồn tại:

```java
Product product = repository.getRequiredById(100L);

// Các kiểm tra tồn kho, giá, trạng thái khác...
System.out.println("Đã xác thực SKU " + product.sku());
```

Nếu ID không tồn tại, `getRequiredById` ném `ProductNotFoundException`. **Đừng dùng method này cho trang danh sách mà “không có dữ liệu” là bình thường.**

Với danh mục:

```java
List<Product> books = repository.listByCategory("books");

if (books.isEmpty()) {
    System.out.println("Danh mục chưa có sản phẩm");
} else {
    for (Product product : books) {
        System.out.println(product.sku());
    }
}
```

Danh sách rỗng nói về **kết quả SQL hợp lệ** chứ không phải “query bị timeout”. Nếu một lỗi timeout xảy ra, method phải giữ đường báo lỗi riêng.

## 8. “Không tìm thấy”, “không có quyền”, “có nhưng chưa sẵn sàng” không giống nhau

`Optional.empty()` phù hợp khi dữ liệu **không tồn tại theo điều kiện truy vấn**, nhưng không nên dùng nó để gom mọi trạng thái nghiệp vụ.

Ví dụ dịch vụ đặt hàng có thể gặp:

- Sản phẩm không tồn tại.
- Sản phẩm tồn tại nhưng đã ngừng bán.
- Sản phẩm tồn tại nhưng người dùng không có quyền xem.
- Sản phẩm tồn tại nhưng hết tồn kho.
- Không thể kiểm tra vì database tạm thời không khả dụng.

Một repository có thể trả `Optional<Product>` từ `findById`, còn tầng service quyết định có được mua hay không. Nếu hệ thống cần phân biệt nhiều trạng thái, có thể dùng mô hình kết quả nghiệp vụ có kiểu rõ ràng, như enum trạng thái hoặc sealed interface, thay vì đặt `Optional.empty()` cho tất cả.

Về bảo mật, có API cố ý **không tiết lộ** tài nguyên tồn tại đối với người không có quyền và trả cùng phản hồi bên ngoài. Đây là **chính sách hiển thị của service/API**, không có nghĩa repository được tự tiện coi lỗi SQL là dữ liệu vắng mặt.

## 9. SQL NULL trong các kiểu kết quả khác nhau

### 9.1. `Optional<Product>` không diễn đạt “hàng có một cột NULL”

Trong repository mẫu:

```java
return Optional.of(new Product(
        id, sku, category, price, parentProductId));
```

Nếu `parentProductId == null`, `Optional.of(product)` vẫn chứa **một sản phẩm**. Không nên viết:

```java
// Sai ý nghĩa: thiếu parent không có nghĩa thiếu product.
if (parentProductId == null) {
    return Optional.empty();
}
```

Nếu toàn bộ hàng không thỏa yêu cầu của domain model, hãy báo lỗi dữ liệu hoặc mô tả rõ trạng thái không hợp lệ, thay vì ngầm coi là “không tìm thấy”.

### 9.2. `LEFT JOIN` có thể có hàng ngoài nhưng không có hàng trong

Ví dụ:

```sql
SELECT p.id AS product_id,
       p.sku,
       parent.id AS parent_id
FROM catalog_products p
LEFT JOIN catalog_products parent
    ON parent.id = p.parent_product_id
WHERE p.id = ?;
```

Nếu sản phẩm tồn tại nhưng không có parent, truy vấn vẫn trả **một hàng** với `parent_id = NULL`. Đó không phải là 0 hàng. Nếu một JOIN tạo ra nhiều bản ghi con trên mỗi sản phẩm, số hàng SQL có thể lớn hơn số entity cha; lúc đó mapper cần **gom nhóm/deduplicate** theo yêu cầu, không dùng helper `readAtMostOne` trực tiếp lên raw result set.

### 9.3. Chuỗi rỗng, danh sách rỗng và giá trị 0

Đây là những dữ liệu hợp lệ tùy schema:

- Chuỗi `""` khác với Java `null` theo nhiều hệ quản trị.
- `List.of()` là kết quả không có entity, không phải một entity với danh sách thuộc tính rỗng.
- `0` là một số nguyên hợp lệ; không nên coi ID hoặc count bằng 0 là “SQL NULL” nếu không dùng `wasNull()` đúng cách.
- `BigDecimal.ZERO` là giá trị tiền bằng 0, khác với không có hàng.

Thiết kế trả về tốt giúp người gọi không phải đoán ý nghĩa của những giá trị đặc biệt.

## 10. Chọn đúng hành vi khi truy vấn trả nhiều hơn kỳ vọng

Giả sử đội phát triển muốn “một bản ghi cấu hình duy nhất cho mỗi tenant” nhưng database chưa đặt `UNIQUE(tenant_id)`. Có ba hướng thiết kế, với ý nghĩa khác nhau:

| Cách xử lý | Khi 2 bản ghi cùng tenant | Đánh giá |
|---|---|---|
| `SELECT ... LIMIT 1` rồi trả bản đầu | Che giấu dữ liệu trùng | Không phù hợp nếu nghiệp vụ đòi duy nhất |
| Đọc tối đa 2 bản ghi, nếu có bản thứ hai thì ném ngoại lệ | Phát hiện vi phạm dữ liệu | Phù hợp để bảo vệ hợp đồng đọc |
| Thêm `UNIQUE(tenant_id)` và vẫn kiểm tra số hàng | Chặn trùng ngay khi ghi | Phù hợp nhất nếu uniqueness là bất biến dữ liệu |

Nếu yêu cầu là “lấy bản ghi gần nhất”, có thể dùng:

```sql
SELECT id, sku, category, price, parent_product_id
FROM catalog_products
WHERE category = ?
ORDER BY id DESC
FETCH FIRST 1 ROW ONLY;
```

Đây là dạng cú pháp SQL chuẩn được một số DBMS hỗ trợ; cú pháp tương đương như `LIMIT 1` tùy sản phẩm. **Quan trọng là tiêu chí sắp xếp được định nghĩa rõ**, và tên method nên thể hiện ý nghĩa “latest” thay vì “unique”.

Nếu không có `ORDER BY`, “hàng đầu tiên” của tập nhiều hàng **không có thứ tự nghiệp vụ bảo đảm**. Kế hoạch truy vấn, index hay version DBMS có thể khiến hàng được trả trước thay đổi.

## 11. Danh sách nhiều đối tượng cần thứ tự và giới hạn

`List<Product>` là kết quả thích hợp cho 0 đến N hàng, nhưng có hai vấn đề khi dùng trong hệ thống thật.

### 11.1. Thứ tự phải xuất phát từ SQL

`ResultSet` trả hàng theo thứ tự mà query cho phép. Nếu repository hứa “sắp theo ID tăng dần”, SQL phải có:

```sql
SELECT id, sku, category, price, parent_product_id
FROM catalog_products
WHERE category = ?
ORDER BY id ASC;
```

Không dựa vào thứ tự vật lý của bảng hay chỉ mục. Không có `ORDER BY`, DBMS **không cam kết thứ tự** kết quả, ngay cả khi thử trên dữ liệu nhỏ luôn thấy giống nhau.

### 11.2. Đừng materialize danh sách không giới hạn

Một `List<Product>` chứa 20 hàng rất tiện. Nhưng truy vấn trả 2 triệu sản phẩm có thể làm JVM thiếu bộ nhớ, giữ connection lâu và chiếm bandwidth lớn. Với giao diện danh sách, hãy xác định giới hạn trang, filter và sort.

`Statement.setMaxRows(int)` không đồng nghĩa một chiến lược phân trang hiệu quả; tùy driver, DBMS vẫn có thể phải xử lý lượng dữ liệu lớn. Các cơ chế `LIMIT/OFFSET`, `FETCH FIRST` hoặc keyset pagination cần được thiết kế theo DBMS và các index tương ứng.

## 12. Hợp đồng trang dữ liệu: kết quả rỗng khác “hết trang”

Khi một danh sách lớn cần chia trang, phương thức có thể trả:

```java
import java.util.List;

public record Page<T>(
        List<T> items,
        boolean hasNext) {

    public Page {
        items = List.copyOf(items);
    }
}
```

Ý nghĩa:

- `items.isEmpty()`: trang này không có hàng.
- `hasNext == true`: theo kết quả truy vấn tại thời điểm đó, còn dữ liệu sau trang này.
- `hasNext == false`: không quan sát được trang kế tiếp theo cách truy vấn hiện tại.

Không đồng nhất “trang cuối có 0 hàng” với “repository lỗi”. Trong hệ thống dữ liệu thay đổi liên tục, pagination không tự cung cấp một snapshot bất biến giữa các request.

### 12.1. Ví dụ keyset pagination trên PostgreSQL

Ví dụ sau dùng PostgreSQL/MySQL-style `LIMIT ?`, không phải SQL portable cho mọi DBMS. Với bảng có ID tăng dần, ta lấy **`pageSize + 1` hàng** để biết còn trang tiếp hay không.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public Page<Product> listPageByCategory(
        String category, long afterId, int pageSize)
        throws SQLException {

    requireNonBlank(category, "category");

    if (afterId < 0 || pageSize <= 0 || pageSize > 100) {
        throw new IllegalArgumentException(
                "Cursor hoặc pageSize không hợp lệ");
    }

    String sql = "SELECT " + COLUMNS
            + " FROM catalog_products "
            + "WHERE category = ? AND id > ? "
            + "ORDER BY id ASC LIMIT ?";

    List<Product> rows = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(sql)) {

        ps.setString(1, category);
        ps.setLong(2, afterId);
        ps.setInt(3, pageSize + 1);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                rows.add(mapProduct(rs));
            }
        }
    }

    boolean hasNext = rows.size() > pageSize;

    List<Product> visible = hasNext
            ? rows.subList(0, pageSize)
            : rows;

    return new Page<>(visible, hasNext);
}
```

**Đoạn này là method bổ sung** đặt bên trong `JdbcProductRepository` từ phần 6, sử dụng `COLUMNS`, `dataSource`, `mapProduct` và `requireNonBlank` đã khai báo; cần import `Page` trong package nếu các lớp khác package.

Caller lấy khóa `id` của hàng **cuối cùng trong `page.items()`** làm `afterId` cho trang tiếp theo, chỉ khi `hasNext` là `true`:

```java
Page<Product> page = repository.listPageByCategory(
        "books", 0L, 20);

for (Product product : page.items()) {
    System.out.println(product.sku());
}

if (page.hasNext() && !page.items().isEmpty()) {
    long nextAfterId =
            page.items().get(page.items().size() - 1).id();

    // Dùng nextAfterId cho lần gọi tiếp theo.
}
```

Đây là kiểu pagination theo `id`, không phù hợp khi UI yêu cầu sắp theo giá hay ngày mà không có cursor/tie-breaker tương ứng. Ngoài ra, keyset pagination phải cân nhắc xóa/thêm dữ liệu đồng thời và mức nhất quán mong muốn giữa các trang.

### 12.2. Không trả `ResultSet` để “tiết kiệm bộ nhớ” theo cách vô tình

Ví dụ cần tránh:

```java
public ResultSet findAllUnsafe() throws SQLException {
    try (Connection c = dataSource.getConnection();
         PreparedStatement ps = c.prepareStatement(
                 "SELECT id, sku FROM catalog_products")) {

        return ps.executeQuery();
        // Ở đây ps và connection sẽ bị đóng trước khi caller đọc.
    }
}
```

`ResultSet` là tài nguyên phụ thuộc vào statement/connection. Khi chúng đã đóng, caller không thể tin vào việc `rs.next()` còn hoạt động. Cách đơn giản là ánh xạ dữ liệu **trước khi** đóng tài nguyên và trả `List<T>`, hoặc định nghĩa API streaming rõ nghĩa, buộc caller đóng scope.

Với dữ liệu lớn, thường nên **phân trang** hoặc dùng callback xử lý từng hàng ngay trong scope JDBC còn mở; không đơn thuần trả một raw `ResultSet` ra ngoài DAO.

## 13. Lệnh ghi cũng cần hợp đồng khi không tìm thấy hàng

Dù bài tập trung ở kết quả truy vấn, các phương thức CRUD ghi dữ liệu cũng cần phân biệt “không có hàng bị tác động” với lỗi database.

Ví dụ xóa sản phẩm theo ID:

```java
public boolean deleteById(long id) throws SQLException {
    requirePositiveId(id);

    String sql = "DELETE FROM catalog_products WHERE id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement ps = connection.prepareStatement(sql)) {

        ps.setLong(1, id);

        int count = ps.executeUpdate();

        if (count == 0) {
            return false;
        }
        if (count == 1) {
            return true;
        }
        throw new SQLException(
                "DELETE theo khóa chính đã tác động nhiều hơn một hàng");
    }
}
```

Đây là **method bổ sung** cho lớp `JdbcProductRepository`. Nó hoạt động theo một câu DML/connection với auto-commit do `DataSource` cấp, tương tự các method đọc đã trình bày.

Hợp đồng `boolean` ở đây có nghĩa:

- `true`: một sản phẩm đã bị xóa.
- `false`: không có sản phẩm khớp ID.
- `SQLException`: có lỗi truy cập dữ liệu hoặc vi phạm bất biến đếm số hàng.

Một số ứng dụng chọn **xóa idempotent** và trả `void`, coi việc không tồn tại như trạng thái đích đã đạt. Hãy chọn chính sách và đặt tên method phù hợp, thay vì thay đổi tùy chỗ.

Nếu lệnh `DELETE` có ràng buộc khóa ngoại hoặc trigger, kết quả và lỗi còn phụ thuộc schema. `executeUpdate() == 0` không tự chứng minh đối tượng chưa từng tồn tại; có thể có thao tác đồng thời xóa nó trước đó.

### 13.1. Trả số hàng hay trả đối tượng sau khi ghi?

Có nhiều hợp đồng hợp lệ:

| Nghiệp vụ | Kiểu trả | Diễn giải |
|---|---|---|
| `updatePrice(id, price)` | `boolean` | Có cập nhật được đúng một hàng hay không |
| `updatePrice(id, price)` | `int` | Có bao nhiêu hàng bị tác động |
| `insert(product)` | `Product` | Đối tượng vừa lưu sau khi lấy đủ giá trị cần thiết |
| `insert(product)` | `long` | ID sinh ra, nếu schema/driver hỗ trợ và API cam kết |
| `save(product)` | Kết quả giàu thông tin | Tách rõ created/updated/conflict nếu nghiệp vụ cần |

**Không suy rằng `executeUpdate()` trả ID**: giá trị này là số hàng bị ảnh hưởng theo hợp đồng JDBC; khóa tự sinh cần API `getGeneratedKeys()` hoặc cơ chế DB riêng. Kết quả từ khóa tự sinh và update counts khi batch có thể phụ thuộc driver, vì vậy cần kiểm thử tích hợp.

## 14. Phân biệt lỗi truy cập dữ liệu và kết quả vắng mặt

Một repository tốt cần có **kênh báo lỗi riêng** cho tình trạng không thể thực hiện truy vấn.

| Tình huống | Có phải “không có dữ liệu”? | Ứng xử |
|---|---|---|
| `SELECT` hợp lệ trả 0 hàng | Có | `Optional.empty()` / `List.of()` / `false` tùy hợp đồng |
| `SELECT` trả hàng có cột `NULL` | Không | Ánh xạ nullable field đúng cách |
| `COUNT(*)` trả 0 | Không phải 0 hàng; là một giá trị đếm 0 | Trả `0L` |
| Trùng khóa khi INSERT | Không | Lỗi constraint; xử lý nghiệp vụ hoặc báo SQL error |
| Database bị mất kết nối | Không | Giữ ngoại lệ và phục hồi theo chính sách |
| Sai cú pháp SQL / thiếu bảng | Không | Báo lỗi, không che thành empty |
| Deadlock / serialization failure | Không | Xử lý transaction và retry có điều kiện |
| Lỗi timeout | Không | Phân biệt timeout, trạng thái transaction và kết quả commit |
| Không có quyền đọc | Không | Phân quyền/exception, không tùy tiện trả empty |
| Truy vấn hứa 0/1 nhưng trả 2+ | Không | Lỗi invariant hoặc cấu hình schema/SQL |

### 14.1. Ngoại lệ SQL và ngoại lệ domain

Một thiết kế có thể dùng:

```java
Optional<Product> findById(long id) throws SQLException;

Product getRequiredById(long id)
        throws SQLException, ProductNotFoundException;
```

`ProductNotFoundException` trong ví dụ là **unchecked exception**, nên viết nó trong `throws` là tùy chọn và thường không cần thiết. Việc trình bày cả hai ở đây chỉ để làm rõ hai luồng lỗi khác nhau:

- `SQLException`: không thể lấy dữ liệu vì SQL/driver/database hoặc vi phạm hợp đồng kỹ thuật.
- `ProductNotFoundException`: SQL thành công nhưng không có thực thể mà nghiệp vụ yêu cầu.

Nếu ứng dụng dùng một `DataAccessException` unchecked để bọc lỗi JDBC, hãy giữ `cause` và dữ liệu chẩn đoán cần thiết. Không biến một lỗi mạng thành `ProductNotFoundException`.

### 14.2. Không tự động thử lại sau mọi ngoại lệ

Một lỗi mất kết nối tại thời điểm commit có thể khiến kết quả ghi **chưa xác định**: database có thể đã commit dù client chưa nhận phản hồi. Không nên retry ngay một lệnh tạo đơn/hạch toán có nguy cơ nhân đôi dữ liệu chỉ vì method ném `SQLException`.

Phải có idempotency key, transaction boundary và quy trình đối soát khi cần. Đây là lý do “trả `Optional.empty()` khi lỗi” đặc biệt nguy hiểm: nó xóa luôn dấu hiệu cần xử lý sự cố hạ tầng.

## 15. Hợp đồng trả về phải phù hợp với ranh giới transaction

Trong ví dụ `JdbcProductRepository`, mỗi method mở một connection riêng. Với các truy vấn độc lập, đây là cách đơn giản và phổ biến khi dùng pool.

Nhưng nếu service cần **đọc sản phẩm rồi giảm tồn kho trong cùng một transaction**, không thể gọi hai repository method mà mỗi method tự mở connection rồi coi chúng thuộc một transaction chung.

```text
Cách KHÔNG bảo đảm cùng transaction:

service
  ├── repo.findById(100)     -> Connection A, truy vấn
  └── repo.decrement(100)    -> Connection B, cập nhật

Hai connection không tự cùng một transaction chỉ vì được lấy
từ cùng DataSource.
```

Có hai cách thiết kế thông dụng:

1. **Truyền `Connection` do service/unit-of-work sở hữu** cho những method DAO nội bộ; DAO không đóng connection của caller.
2. Dùng **transaction manager / Unit of Work** để tất cả các thao tác được enlist đúng transaction, thường thông qua DataSource do framework quản lý.

Ví dụ ranh giới transaction JDBC trực tiếp:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        String sql = "UPDATE catalog_products SET price = ? WHERE id = ?";

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, new java.math.BigDecimal("99000.00"));
            ps.setLong(2, 100L);

            if (ps.executeUpdate() != 1) {
                throw new ProductNotFoundException(100L);
            }
        }

        // Thực hiện các SQL khác trên CÙNG connection nếu cần.
        connection.commit();

    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đoạn minh họa nằm trong phương thức có `DataSource dataSource`; `ProductNotFoundException` là class từ phần trước. Nên đặt logic nghiệp vụ/transaction ở service hoặc một lớp transaction boundary, không để từng DAO con tự commit giữa chừng.

**Giới hạn về tính nhất quán:** hai lời gọi `findById` và `listByCategory` độc lập có thể quan sát dữ liệu ở hai thời điểm khác nhau. Nếu một API cần trả tổng số phần tử cùng một trang danh sách **trong cùng snapshot**, phải thiết kế transaction/isolation phù hợp hoặc chấp nhận tổng đếm có thể thay đổi khi các transaction khác ghi dữ liệu.

## 16. Kiểm thử hợp đồng 0/1/nhiều trên DBMS thật

Unit test logic ánh xạ giúp kiểm tra `mapProduct` và nhánh `Optional`. Nhưng SQL, constraint `UNIQUE`, kiểu `DECIMAL`, trạng thái `NULL` và transaction cần được xác minh bằng **JDBC driver/DBMS thật**.

Một tập kiểm thử tối thiểu nên có:

| Test case | Fixture | Kỳ vọng |
|---|---|---|
| Không có ID | Không có hàng ID 999 | `findById(999).isEmpty() == true` |
| Có đúng một ID | Hàng ID 100 | `Optional` có Product ID 100 |
| Bắt buộc nhưng thiếu | Không có ID 999 | `getRequiredById(999)` ném `ProductNotFoundException` |
| Danh mục rỗng | Không có category `unknown` | `listByCategory("unknown").isEmpty() == true` |
| Danh mục nhiều hàng | Hai hàng category `books` | Danh sách có 2 phần tử theo `ORDER BY id` |
| Cột nullable | ID 100 với parent NULL | Product tồn tại, `parentProductId() == null` |
| Cột có giá trị | ID 101 với parent 100 | Product có `parentProductId() == 100L` |
| Tìm theo unique SKU | `sku='JDBC-BOOK'` | Đúng một Product |
| Count | Category không có hàng | `countByCategory(...) == 0L` |
| Exists | ID 999 không tồn tại | `existsById(999) == false` |
| Lỗi SQL/driver | Kết nối sai hoặc schema thiếu trong lab | Ném lỗi, **không** trả empty |
| Xóa ID không tồn tại | Không có ID tương ứng | `deleteById` trả `false` |
| Ràng buộc `UNIQUE` | Thử INSERT SKU trùng | DB báo lỗi, không tự trả `Optional.empty()` |

Ví dụ JUnit Jupiter (phương thức test trong lớp đã được cấu hình `repository` và fixture `catalog_products`):

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

@Test
void distinguishesMissingSingleFromEmptyCollection()
        throws Exception {

    assertTrue(repository.findById(999L).isEmpty());

    List<Product> missingCategory =
            repository.listByCategory("unknown");
    assertNotNull(missingCategory);
    assertTrue(missingCategory.isEmpty());

    assertThrows(ProductNotFoundException.class,
            () -> repository.getRequiredById(999L));
}

@Test
void readsOneAndManyResults() throws Exception {
    Product one = repository.findById(100L).orElseThrow();

    assertEquals("JDBC-BOOK", one.sku());
    assertNull(one.parentProductId());

    List<Product> books =
            repository.listByCategory("books");

    assertEquals(2, books.size());
    assertEquals(100L, books.get(0).id());
    assertEquals(101L, books.get(1).id());
    assertEquals(Long.valueOf(100L),
            books.get(1).parentProductId());
}
```

Những test này chỉ đúng nếu fixture đã tạo schema và dữ liệu theo phần 5, dùng `DataSource` tới **database thử nghiệm**. Trong CI có thể dùng Testcontainers hoặc DB lab riêng; không chạy DDL/test xóa dữ liệu trên production.

### 16.1. Test nhánh 2+ hàng cho truy vấn “tối đa một”

Vì bảng `catalog_products` đã có `PRIMARY KEY` và `UNIQUE(sku)`, không thể cố ý tạo hai hàng có cùng ID hoặc SKU rồi vẫn mong DB chấp nhận. Để test thuật toán `readAtMostOne`:

- Có thể mock `ResultSet` để lần gọi `next()` đầu và thứ hai đều trả `true`, rồi assert ném `SQLException`. Đây là **unit test logic kiểm tra cardinality**, không phải integration test DB.
- Hoặc tạo một truy vấn test trên **cột không unique** với nhiều hàng và áp dụng helper tương đương (nếu thiết kế cho phép), để kiểm tra phát hiện vi phạm.

**Không bỏ unique constraint ở production chỉ để tạo dữ liệu trùng cho bài test.** Phát hiện 2+ hàng là một biện pháp phòng vệ; nguyên tắc chính vẫn là xây ràng buộc dữ liệu đúng từ database.

### 16.2. Đừng chỉ kiểm tra giá trị trả về mà quên tài nguyên

Test cũng nên xác nhận:

- `Connection` được trả về pool sau khi ánh xạ xong.
- `PreparedStatement`/`ResultSet` được đóng ở cả nhánh 0 hàng và nhánh có dữ liệu.
- Exception trong mapper không làm rò rỉ connection.
- API không trả `ResultSet` ra ngoài phạm vi đã đóng.
- Truy vấn dùng `ORDER BY` có thứ tự ổn định.
- SQL tham số hóa với ký tự đầu vào đặc biệt không làm thay đổi cấu trúc câu lệnh.

Trong hệ thống dùng pool, một test integration với pool thật sẽ phát hiện các lỗi về vòng đời mà mock đơn giản có thể bỏ qua.

## 17. Những lỗi thiết kế thường gặp

| Thiết kế sai hoặc mơ hồ | Hậu quả | Cách cải thiện |
|---|---|---|
| `Product findById(...)` trả `null` khi thiếu | Caller dễ `NullPointerException` | `Optional<Product>` cho 0/1, hoặc ngoại lệ domain cho bắt buộc |
| `List<Product> list(...)` trả `null` khi không có hàng | Mọi caller phải kiểm tra null | Luôn trả danh sách rỗng |
| Catch mọi `SQLException` rồi trả empty | Che downtime, lỗi schema/SQL | Giữ lỗi truy cập dữ liệu trên đường riêng |
| `Optional.of(null)` | `NullPointerException` ngay tại chỗ | Chỉ tạo `Optional.of(product)` khi đã có object hợp lệ |
| Dùng `rs.getLong(...) == 0` để nhận biết SQL NULL | Nhầm giá trị thật 0 với NULL | `wasNull()` ngay sau getter |
| Chỉ `rs.next()` một lần trong query hứa unique | Âm thầm bỏ hàng trùng | Ràng buộc UNIQUE + kiểm tra có hàng thứ hai |
| Dùng `LIMIT 1` để “sửa” dữ liệu trùng | Che lỗi invariant | Xác định uniqueness hoặc đặt tên/tie-breaker đúng |
| Trả raw `ResultSet` từ DAO đã đóng connection | Caller không còn đọc được | Ánh xạ trong scope rồi trả model/list |
| List lớn vô hạn | Tốn memory, giữ connection lâu | Phân trang hoặc streaming có quản lý tài nguyên |
| Không có `ORDER BY` nhưng UI đòi thứ tự | Kết quả thay đổi ngẫu nhiên | Sắp xếp tường minh trong SQL |
| Dùng `getRequiredById` cho màn tìm kiếm tùy chọn | Coi “không thấy” như lỗi | Chọn `findById` và xử lý empty bình thường |
| Dùng count bằng 0 để kết luận `ResultSet` không có hàng | Sai với `COUNT(*)` không `GROUP BY` | Hiểu đúng cardinality của SQL aggregate |
| DAO tự mở connection mới trong transaction nhiều bước | Không cùng transaction | Truyền context/connection hoặc dùng transaction manager |
| Dùng `CONCUR_UPDATABLE` chỉ để trả object | Phức tạp, phụ thuộc driver | Đọc `CONCUR_READ_ONLY` và dùng SQL UPDATE tường minh nếu cần |
| Xem “không có quyền” là “không tồn tại” ở mọi tầng | Che hoặc lộ sai thông tin | Phân định repository và chính sách quyền ở service |

## 18. Checklist trước khi công bố một hợp đồng DAO/Repository

1. Method trả **tối đa một**, **bắt buộc một**, **nhiều**, **đếm**, **tồn tại** hay **trang dữ liệu**?
2. Trường hợp **0 hàng** được trả bằng `Optional.empty()`, `List.of()`, `false`, `0L` hay ngoại lệ domain?
3. Với truy vấn **tối đa một**, DB đã bảo vệ tính duy nhất bằng khóa chính/unique constraint hoặc query có điều kiện đủ mạnh chưa?
4. Nếu SQL trả **nhiều hơn dự kiến**, code có báo lỗi thay vì bỏ qua một cách im lặng không?
5. Cột `NULL`, chuỗi rỗng, số 0 và **không có hàng** đã được phân biệt rõ chưa?
6. `SQLException` có giữ đường báo lỗi riêng, không bị biến thành dữ liệu vắng mặt không?
7. SQL có tham số hóa qua `PreparedStatement`, có thứ tự `ORDER BY` khi API hứa thứ tự không?
8. Kết quả lớn có giới hạn trang hoặc chiến lược streaming quản lý tài nguyên không?
9. `ResultSet`, `PreparedStatement`, `Connection` có được đóng đúng scope trước khi trả object Java không?
10. Nghiệp vụ nhiều bước có cùng transaction/connection và phân định tầng sở hữu `commit`/`rollback` không?
11. Khi xóa/cập nhật 0 hàng, hợp đồng phân biệt “không có dữ liệu” với lỗi thực thi có rõ không?
12. Đã test các tình huống **0, 1, 2+ hàng**, cột nullable, lỗi SQL, transaction và resource cleanup trên driver thật khi cần chưa?

## Ghi nhớ

- **`Optional<T>`** biểu diễn một đối tượng **có thể vắng mặt** (0 hoặc 1), không dùng để che lỗi SQL.
- **`T` hoặc ngoại lệ domain** phù hợp khi nghiệp vụ **bắt buộc** phải có một đối tượng.
- **`List<T>`** biểu diễn 0 đến nhiều đối tượng; **không có dữ liệu thì trả danh sách rỗng, không trả null**.
- Một hàng có cột **SQL NULL vẫn là một hàng**; `ResultSet.next()` quyết định có hàng hay không, `wasNull()` giúp đọc cột số nullable.
- **Tính duy nhất cần được bảo vệ bằng ràng buộc DB**; repository nên kiểm tra và báo lỗi khi hợp đồng “tối đa một” bị vi phạm.
- **Lỗi JDBC, timeout, mất kết nối và ràng buộc SQL** là một luồng lỗi riêng, không phải trạng thái not found.
- **Không trả `ResultSet` đã hết vòng đời**; ánh xạ thành model/list trước khi đóng statement và connection.
- Với danh sách lớn, **phân trang có thứ tự ổn định** phù hợp hơn việc materialize không giới hạn; với transaction nhiều bước, dùng **cùng connection/transaction**.

Thiết kế đúng hợp đồng trả về khiến repository JDBC trở nên **dễ gọi, dễ kiểm thử và khó bị hiểu nhầm**: người dùng API biết khi nào nhận một đối tượng, khi nào nhận tập rỗng và khi nào cần xử lý lỗi thực sự. Đây là nền tảng để các tầng service xây nghiệp vụ CRUD rõ ràng trên driver, `DataSource` và cơ sở dữ liệu quan hệ.
