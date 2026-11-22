# Tạo Query và TypedQuery qua EntityManager trong JPQL cơ bản

Trong Jakarta Persistence (JPA), khi cần tìm kiếm, lọc, sắp xếp hoặc tổng hợp dữ liệu, ta thường viết **JPQL** (*Jakarta Persistence Query Language*) và tạo đối tượng truy vấn thông qua `EntityManager`. Hai API quan trọng là `Query` và `TypedQuery<T>`. Chúng giúp tách **câu truy vấn**, **tham số**, **cách thực thi** và **kiểu kết quả Java**, thay vì phải tự xử lý mọi hàng của `ResultSet` như JDBC thuần.

Ví dụ tìm các sản phẩm đang bán và có giá từ một mức tối thiểu:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE p.status = :status AND p.price >= :minPrice " +
    "ORDER BY p.price ASC, p.id ASC",
    Product.class
);

query.setParameter("status", ProductStatus.ACTIVE);
query.setParameter("minPrice", new BigDecimal("100000.00"));

List<Product> products = query.getResultList();
~~~

Ở đây, `Product` là **entity Java**, còn `p.status` và `p.price` là **thuộc tính đã được JPA ánh xạ**. JPQL không viết trực tiếp bằng tên bảng `products` hay cột `price_amount` như SQL. JPA provider dịch truy vấn object thành SQL phù hợp với mapping và dialect của database.

Bài học tập trung vào **cách tạo Query và TypedQuery qua EntityManager**, từ các thao tác cơ bản đến tham số hóa an toàn, kiểu dữ liệu trả về, truy vấn một/nhiều kết quả, phân trang, cấu hình truy vấn, xử lý lỗi, lifecycle và những điểm dễ nhầm với native SQL.

## 1. Phân biệt JPQL, EntityManager, Query và TypedQuery

Sơ đồ tổng quan:

~~~text
Ứng dụng Java
     |
     | JPQL: SELECT p FROM Product p WHERE p.price >= :minPrice
     v
EntityManager
     |
     +-- createQuery(jpql) --------------------> Query
     |
     +-- createQuery(jpql, Product.class) ----> TypedQuery<Product>
     |
     v
Query object:
     - Gắn tham số
     - Giới hạn số kết quả
     - Đặt flush mode, lock mode, hint
     - Gọi getResultList()/getSingleResult()/executeUpdate()
     |
     v
JPA Provider
     |
     | SQL tương ứng với mapping và database dialect
     v
Cơ sở dữ liệu
     |
     v
Entity, scalar, DTO hoặc số hàng được cập nhật
~~~

| Thành phần | Vai trò |
| --- | --- |
| `EntityManager` | Điểm vào quản lý persistence context và tạo truy vấn |
| **JPQL string** | Diễn đạt truy vấn dựa trên entity và thuộc tính Java |
| `Query` | Interface truy vấn không khai báo kiểu kết quả cụ thể ở mức generic |
| `TypedQuery<T>` | Interface truy vấn có kiểu kết quả `T` rõ ràng |
| `setParameter()` | Gắn giá trị vào tham số JPQL |
| `getResultList()` | Thực thi truy vấn SELECT và nhận danh sách |
| `getSingleResult()` | Thực thi SELECT kỳ vọng đúng một kết quả |
| `executeUpdate()` | Thực thi bulk JPQL UPDATE/DELETE |

**Ý chính:** `EntityManager.createQuery(...)` tạo một đối tượng truy vấn; việc tạo đối tượng đó **không đồng nghĩa SQL SELECT đã được gửi ngay**. Thông thường query được thực thi tại `getResultList()`, `getSingleResult()` hoặc `executeUpdate()`. Provider có thể parse/validate JPQL sớm hơn, nhưng không nên lấy thời điểm tạo Query để kết luận database đã được truy vấn.

## 2. Dữ liệu ví dụ: Product và Category

Để các ví dụ thống nhất, giả sử ứng dụng bán hàng có hai entity:

~~~text
Category (1) -------------------- (N) Product
    id                                 id
    code                               sku
    name                               name
                                       price
                                       status
                                       stockQuantity
                                       createdAt
                                       category_id (FK)
                                       version
~~~

Một sản phẩm thuộc một danh mục. Danh mục có thể chứa nhiều sản phẩm.

### 2.1. Enum trạng thái

~~~java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    INACTIVE
}
~~~

### 2.2. Category

~~~java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "code", nullable = false, unique = true)
    private String code;

    @Column(name = "name", nullable = false)
    private String name;

    protected Category() {
    }

    public Category(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }
}
~~~

### 2.3. Product

~~~java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private ProductStatus status;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    private Category category;

    protected Product() {
    }

    public Product(
            String sku,
            String name,
            BigDecimal price,
            ProductStatus status,
            int stockQuantity,
            Instant createdAt,
            Category category) {
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.status = status;
        this.stockQuantity = stockQuantity;
        this.createdAt = createdAt;
        this.category = category;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public ProductStatus getStatus() {
        return status;
    }

    public Category getCategory() {
        return category;
    }

    public void changePrice(BigDecimal price) {
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }
        this.price = price;
    }
}
~~~

Các field được JPA ánh xạ bằng **field access** vì `@Id` nằm trên field. Ta sẽ dùng tên Java `stockQuantity` và `createdAt` trong JPQL, mặc dù tên cột SQL là `stock_quantity` và `created_at`.

### 2.4. Schema SQL tương ứng

DDL PostgreSQL minh họa:

~~~sql
CREATE TABLE categories (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    category_id BIGINT NOT NULL,
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES categories(id)
);
~~~

Tên cột và kiểu SQL cụ thể có thể khác theo DBMS và provider. DDL được đưa ra để người học hình dung mapping; các ví dụ JPQL vẫn sử dụng **entity name** và **persistent attribute names**, không viết trực tiếp tên bảng SQL.

## 3. Tạo Query bằng `EntityManager.createQuery(String)`

Đây là dạng không khai báo kiểu kết quả:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.Query;
import java.util.List;

String jpql =
        "SELECT p FROM Product p " +
        "WHERE p.status = :status";

Query query = em.createQuery(jpql);
query.setParameter("status", ProductStatus.ACTIVE);

List<?> results = query.getResultList();
~~~

`Query` là một interface chung. Nó có thể được dùng cho JPQL SELECT hoặc bulk UPDATE/DELETE, cũng như một số loại query khác do EntityManager tạo.

**Điểm hạn chế:** ở mức Java generic, `Query.getResultList()` không cho compiler biết chắc từng phần tử là `Product`. Nếu muốn:

~~~java
List<Product> products = (List<Product>) query.getResultList();
~~~

thì ép kiểu như trên có thể dẫn tới cảnh báo unchecked cast và nguy cơ lỗi khi câu SELECT không thực sự trả về Product. Nên ưu tiên `TypedQuery<Product>` cho các câu SELECT có kiểu kết quả biết trước.

### Khi nào Query vẫn hữu ích?

- Viết **bulk UPDATE/DELETE** thông qua `executeUpdate()`.
- Tương tác với một API cũ chỉ trả về interface `Query`.
- Làm việc với native SQL qua `createNativeQuery(...)`.
- Kịch bản kết quả động hoặc projection mà tầng gọi đã chủ động xử lý kiểu.

Không phải cứ muốn “mạnh hơn” mới dùng Query; đó đơn giản là API **ít thông tin kiểu hơn** so với TypedQuery.

## 4. Tạo TypedQuery bằng `createQuery(String, Class<T>)`

Đây là cách nên dùng khi SELECT trả về một loại kết quả đã biết:

~~~java
import jakarta.persistence.TypedQuery;
import java.util.List;

TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p WHERE p.status = :status",
    Product.class
);

query.setParameter("status", ProductStatus.ACTIVE);
List<Product> products = query.getResultList();
~~~

Tham số thứ hai `Product.class` khai báo **kiểu kết quả mong muốn**, và compiler biết `getResultList()` trả về `List<Product>`.

### Khác biệt về chữ ký API

~~~java
Query createQuery(String qlString);

<T> TypedQuery<T> createQuery(
        String qlString,
        Class<T> resultClass);
~~~

Nếu JPQL thực tế chọn scalar hoặc nhiều biểu thức mà không tương thích với `resultClass`, quá trình tạo/thực thi truy vấn có thể báo lỗi. **TypedQuery không có phép màu tự chuyển mọi SELECT thành Product**: kết quả JPQL vẫn phải phù hợp với loại Java đã khai báo.

### So sánh

| Tiêu chí | `Query` | `TypedQuery<Product>` |
| --- | --- | --- |
| Cách tạo | `em.createQuery(jpql)` | `em.createQuery(jpql, Product.class)` |
| Thông tin kiểu ở compile time | Không cụ thể | Cụ thể là Product |
| SELECT một entity Product | Dùng được | Nên ưu tiên |
| SELECT số lượng COUNT | Cần kiểm tra kiểu kết quả | `TypedQuery<Long>` phù hợp |
| SELECT DTO | Dùng được nhưng mất thông tin generic | `TypedQuery<ProductSummary>` |
| JPQL UPDATE/DELETE | `executeUpdate()` | Thường dùng `Query` |
| Lọc, phân trang, gắn tham số | Có | Có |

## 5. Cấu trúc một câu SELECT JPQL

Ví dụ:

~~~java
String jpql =
        "SELECT p " +
        "FROM Product p " +
        "WHERE p.price >= :minPrice " +
        "ORDER BY p.price ASC, p.id ASC";
~~~

Giải thích:

| Thành phần | Ý nghĩa |
| --- | --- |
| `SELECT p` | Chọn entity instance được đại diện bởi alias p |
| `FROM Product p` | Tập entity Product, đặt identification variable p |
| `WHERE p.price >= :minPrice` | Lọc theo thuộc tính price và tham số minPrice |
| `ORDER BY p.price ASC` | Sắp xếp tăng dần theo price |
| `p.id ASC` | Sắp xếp phụ theo id để ổn định kết quả |

JPQL là ngôn ngữ **định hướng entity**, không phải chuỗi SQL tùy ý.

### 5.1. Sử dụng tên entity thay vì bảng

Đúng:

~~~jpql
SELECT p FROM Product p
~~~

Sai nếu `products` chỉ là tên bảng SQL và không có entity name như vậy:

~~~jpql
SELECT p FROM products p
~~~

`@Table(name = "products")` chỉ quyết định bảng vật lý. Tên entity mặc định là tên class không kèm package, trừ khi khai báo tường minh:

~~~java
@Entity(name = "CatalogProduct")
@Table(name = "products")
public class Product {
    // ...
}
~~~

Khi đó JPQL phải dùng:

~~~jpql
SELECT p FROM CatalogProduct p
~~~

Không dùng tên bảng `products` hay tên class `Product` nếu entity đã được đổi tên JPA thành `CatalogProduct`.

### 5.2. Sử dụng tên thuộc tính Java thay vì tên cột SQL

Đúng:

~~~jpql
SELECT p FROM Product p WHERE p.stockQuantity > :minStock
~~~

Sai:

~~~jpql
SELECT p FROM Product p WHERE p.stock_quantity > :minStock
~~~

trừ khi entity thực sự có persistent property tên `stock_quantity` (không có trong ví dụ). Tên `stock_quantity` ở DDL được ánh xạ bởi `@Column(name = "stock_quantity")`; JPQL sử dụng `stockQuantity`.

## 6. Named parameter: `:name` và `setParameter(String, Object)`

**Named parameter** thường dễ đọc nhất:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE p.status = :status " +
    "AND p.price BETWEEN :low AND :high",
    Product.class
);

query.setParameter("status", ProductStatus.ACTIVE);
query.setParameter("low", new BigDecimal("100000.00"));
query.setParameter("high", new BigDecimal("500000.00"));

List<Product> products = query.getResultList();
~~~

Những quy tắc quan trọng:

- Trong JPQL, khai báo parameter có dấu `:`, ví dụ `:low`.
- Trong `setParameter`, truyền **tên không có dấu hai chấm**, ví dụ `"low"`.
- Không đặt named parameter trong dấu nháy như một literal: `':low'` chỉ là chuỗi văn bản trong JPQL.
- Cần gắn giá trị cho các tham số query yêu cầu trước khi thực thi.
- Kiểu Java phải phù hợp với kiểu thuộc tính và biểu thức JPQL.

### Vì sao không nối giá trị trực tiếp vào JPQL?

Không nên:

~~~java
String jpql =
        "SELECT p FROM Product p WHERE p.name = '" +
        userInput + "'";
~~~

Cách nối chuỗi này dễ gây lỗi cú pháp với dấu nháy, tăng nguy cơ **query injection**, khiến truy vấn khó tái sử dụng và làm log/diagnostics khó hiểu.

Nên dùng:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p WHERE p.name = :name",
    Product.class
);
query.setParameter("name", userInput);
~~~

Provider xử lý tham số như **giá trị**, không như một phần mã truy vấn. Đây là thực hành quan trọng cho truy vấn an toàn.

## 7. Positional parameter: `?1`, `?2`

JPQL cũng hỗ trợ tham số vị trí:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE p.price >= ?1 AND p.status = ?2",
    Product.class
);

query.setParameter(1, new BigDecimal("100000.00"));
query.setParameter(2, ProductStatus.ACTIVE);
~~~

Vị trí bắt đầu từ **1**, không phải 0.

| JPQL | Java |
| --- | --- |
| `?1` | `setParameter(1, value)` |
| `?2` | `setParameter(2, value)` |
| `:status` | `setParameter("status", value)` |

Nên chọn một cách đặt tham số nhất quán trong cùng query. Named parameters thường ít lỗi hơn khi một câu truy vấn dài có nhiều điều kiện và sau này cần thêm/bớt điều kiện.

### Không nhầm với dấu `?` của JDBC

PreparedStatement JDBC phổ biến dùng placeholder `?` không đánh số trong chuỗi SQL. Trong JPQL portable, positional parameters được viết theo dạng `?1`, `?2`. Một cú pháp chấp nhận bởi HQL hay SQL dialect của provider không nhất thiết là cú pháp JPQL portable.

## 8. Gắn tham số đúng kiểu: Enum, BigDecimal, Instant

Trong entity Product, `status` là `ProductStatus` và dùng `@Enumerated(EnumType.STRING)`. Ta nên truyền **enum Java**, không truyền tên trạng thái dưới dạng string:

~~~java
TypedQuery<Product> q = em.createQuery(
    "SELECT p FROM Product p WHERE p.status = :status",
    Product.class
);
q.setParameter("status", ProductStatus.ACTIVE);
~~~

Provider sẽ dùng mapping để biểu diễn enum ở DB.

### BigDecimal

~~~java
q.setParameter("minPrice", new BigDecimal("199000.00"));
~~~

Giữ kiểu số tiền tương thích với field `BigDecimal` và precision/scale ở SQL. Không dùng `double` tùy tiện cho nghiệp vụ cần số thập phân chính xác.

### Instant

~~~java
TypedQuery<Product> recent = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE p.createdAt >= :since",
    Product.class
);
recent.setParameter(
    "since",
    Instant.parse("2027-01-01T00:00:00Z")
);
~~~

Trong các phiên bản Jakarta Persistence hiện đại, `java.time` được hỗ trợ cho nhiều kiểu ngày giờ; mapping thực tế phải phù hợp DBMS và version đang sử dụng.

### Tránh lỗi thời gian và timezone

- Dùng `Instant` khi dữ liệu biểu diễn một thời điểm tuyệt đối.
- Dùng `LocalDate` cho ngày lịch không có timezone.
- Xác định quy tắc chuyển đổi timezone ở biên API/database.
- Không so sánh thời điểm bằng cách format thành string rồi so sánh chữ nếu không thật sự cần.

Với API cũ dùng `java.util.Date` hoặc `Calendar`, JPA có các overload `setParameter(..., TemporalType)` phù hợp; cần xác định ý nghĩa DATE/TIME/TIMESTAMP của query, không suy luận từ tên biến.

## 9. Điều kiện `IN` và tham số dạng collection

Muốn tìm một nhóm ID:

~~~java
List<Long> ids = List.of(101L, 102L, 103L);

TypedQuery<Product> q = em.createQuery(
    "SELECT p FROM Product p WHERE p.id IN :ids",
    Product.class
);
q.setParameter("ids", ids);

List<Product> result = q.getResultList();
~~~

Đây là truy vấn SELECT sử dụng tham số có nhiều giá trị cho toán tử `IN`. Provider diễn dịch thành cách binding phù hợp với DBMS.

### Danh sách rỗng là trường hợp cần xử lý riêng

Không nên mặc định:

~~~java
q.setParameter("ids", List.of());
~~~

sẽ tạo một câu SQL hợp lệ trên mọi provider. Nhiều dialect không chấp nhận `IN ()`, và hành vi biến đổi tập rỗng có thể khác nhau. Một quy tắc dễ hiểu:

~~~java
public List<Product> findProductsByIds(
        EntityManager em,
        List<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }

    return em.createQuery(
            "SELECT p FROM Product p WHERE p.id IN :ids",
            Product.class)
        .setParameter("ids", ids)
        .getResultList();
}
~~~

Với list rất lớn, một câu `IN` có thể gặp giới hạn tham số, SQL quá dài hoặc hiệu năng kém. Có thể cần chia batch, temporary table, table-valued parameter hoặc cách query khác tùy DBMS.

## 10. Lọc `LIKE` và ký tự đại diện

`LIKE` sử dụng các ký tự:

- `%`: khớp một chuỗi ký tự có độ dài bất kỳ.
- `_`: khớp đúng một ký tự.

Ví dụ:

~~~java
TypedQuery<Product> q = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE LOWER(p.name) LIKE :pattern",
    Product.class
);

q.setParameter("pattern", "%java%");
~~~

### Phân biệt tham số an toàn với escaping wildcard

Tham số hóa tránh việc nhập giá trị bị diễn dịch như mã JPQL, nhưng **không tự biến ký tự `%` và `_` thành ký tự thường của LIKE**. Nếu người dùng nhập “50%”, ứng dụng có thể muốn tìm dấu phần trăm thật, không phải wildcard.

Một cách portable theo JPQL `ESCAPE`:

~~~java
String escaped = userText
    .replace("!", "!!")
    .replace("%", "!%")
    .replace("_", "!_");

TypedQuery<Product> q = em.createQuery(
    "SELECT p FROM Product p " +
    "WHERE LOWER(p.name) LIKE :pattern ESCAPE '!'",
    Product.class
);

q.setParameter(
    "pattern",
    "%" + escaped.toLowerCase(Locale.ROOT) + "%"
);
~~~

Đoạn minh họa dùng `java.util.Locale`. Khả năng so sánh hoa/thường, collation, Unicode và index phụ thuộc database. `LOWER(p.name)` có thể khiến index B-tree thông thường trên cột `name` không được dùng theo cách tối ưu; khi cần tìm kiếm văn bản lớn, cân nhắc index hàm, collation, full-text search hoặc công cụ chuyên dụng.

## 11. Xử lý `NULL` trong JPQL

Với một field nullable, cú pháp so sánh SQL/JPQL cần phân biệt null:

~~~jpql
SELECT p FROM Product p WHERE p.category IS NULL
~~~

Trường hợp này chỉ có ý nghĩa nếu mapping `category` thực sự cho phép null; entity ví dụ đang khai báo `optional=false` và `nullable=false`.

Không viết:

~~~jpql
WHERE p.category = NULL
~~~

vì so sánh bằng toán tử `=` với NULL không có ngữ nghĩa bằng nhau thông thường của SQL ba giá trị.

### Tham số optional filter

Một cách thường thấy:

~~~jpql
WHERE (:status IS NULL OR p.status = :status)
~~~

có thể tiện nhưng không luôn tối ưu cho query plan, và một số provider/DBMS có khó khăn suy luận kiểu khi bind null. Nếu bộ lọc thật sự tùy chọn, cách rõ hơn là **chỉ thêm predicate khi có filter** (sử dụng Criteria API hoặc xây dựng JPQL có whitelist các mảnh cố định) rồi bind tham số có giá trị.

**Không nối nguyên chuỗi điều kiện do user cung cấp vào JPQL.** Chỉ giá trị được lấy từ input; tên field, toán tử và cấu trúc query phải được ứng dụng kiểm soát.

## 12. Truy vấn trả nhiều kết quả: `getResultList()`

Đây là cách phổ biến nhất:

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.status = :status " +
        "ORDER BY p.name ASC, p.id ASC",
        Product.class)
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();
~~~

`getResultList()` trả danh sách. Nếu không có bản ghi phù hợp, kết quả là **list rỗng**, không phải lỗi “không tìm thấy”.

~~~java
if (products.isEmpty()) {
    // Không có sản phẩm phù hợp.
}
~~~

### Không nên ép một list thành một entity

Sai:

~~~java
Product product = (Product) query.getResultList();
~~~

`getResultList()` trả collection, không trả một instance Product đơn lẻ. Khi chỉ cần một kết quả, phải chọn đúng API hoặc giới hạn kết quả có chủ đích.

### Kết quả entity thường là managed

Khi JPQL SELECT trả entity instances từ một persistence context đang hoạt động, các entity được nạp thường ở trạng thái **managed** trong context đó. Sửa field persistent của chúng trong transaction có thể kích hoạt dirty checking.

Ngược lại, nếu SELECT trả một giá trị scalar hoặc DTO projection, kết quả **không tự trở thành managed entity**.

## 13. Truy vấn kỳ vọng một kết quả: `getSingleResult()`

Ví dụ tìm theo SKU được database bảo đảm duy nhất:

~~~java
TypedQuery<Product> q = em.createQuery(
    "SELECT p FROM Product p WHERE p.sku = :sku",
    Product.class
);
q.setParameter("sku", sku);

Product product = q.getSingleResult();
~~~

API này có các trường hợp quan trọng:

| Tình huống | Kết quả |
| --- | --- |
| Có đúng một kết quả | Trả entity/giá trị đó |
| Không có kết quả | `NoResultException` |
| Có nhiều hơn một kết quả | `NonUniqueResultException` |

Ví dụ xử lý trường hợp không tồn tại:

~~~java
import jakarta.persistence.NoResultException;
import java.util.Optional;

public Optional<Product> findBySku(
        EntityManager em, String sku) {
    try {
        Product p = em.createQuery(
                "SELECT p FROM Product p WHERE p.sku = :sku",
                Product.class)
            .setParameter("sku", sku)
            .getSingleResult();

        return Optional.of(p);
    } catch (NoResultException ex) {
        return Optional.empty();
    }
}
~~~

**Không bắt mọi `PersistenceException` rồi trả empty:** làm vậy có thể nuốt lỗi kết nối, query sai, timeout hoặc database exception. Chỉ xử lý trường hợp “không có kết quả” khi đó đúng là một kết quả nghiệp vụ bình thường.

### Khi nào dùng `setMaxResults(1)`?

Nếu nghiệp vụ chỉ cần **một bản ghi đầu tiên theo thứ tự**, không yêu cầu kết quả duy nhất:

~~~java
List<Product> cheapest = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.status = :status " +
        "ORDER BY p.price ASC, p.id ASC",
        Product.class)
    .setParameter("status", ProductStatus.ACTIVE)
    .setMaxResults(1)
    .getResultList();
~~~

Rồi lấy `cheapest.get(0)` nếu list không rỗng. Cách này **không phát hiện trùng**, còn `getSingleResult()` sẽ phát hiện query trả nhiều hơn một kết quả.

## 14. Truy vấn COUNT bằng `TypedQuery<Long>`

Để đếm số sản phẩm đang bán:

~~~java
TypedQuery<Long> q = em.createQuery(
    "SELECT COUNT(p) FROM Product p " +
    "WHERE p.status = :status",
    Long.class
);

long count = q
    .setParameter("status", ProductStatus.ACTIVE)
    .getSingleResult();
~~~

Theo ngữ nghĩa JPQL thông thường, `COUNT` trả `Long`, kể cả khi số lượng bằng 0. Không khai báo `TypedQuery<Integer>` chỉ vì số lượng bản ghi hiện tại còn nhỏ.

### COUNT khác với tải entity rồi đếm

Không nên làm:

~~~java
int count = em.createQuery(
        "SELECT p FROM Product p",
        Product.class)
    .getResultList()
    .size();
~~~

khi chỉ cần số lượng. Đoạn này có thể nạp toàn bộ entity vào memory trước khi đếm. `SELECT COUNT(p)` để database thực hiện phép đếm và chỉ trả về một giá trị.

### COUNT và JOIN

Nếu query JOIN một quan hệ một–nhiều, một entity có thể xuất hiện ở nhiều hàng join. Khi cần đếm **số Product khác nhau**, cân nhắc:

~~~jpql
SELECT COUNT(DISTINCT p.id) FROM Product p JOIN p.someCollection c
~~~

`someCollection` chỉ là ví dụ cho một collection relationship nếu entity thực tế có thuộc tính đó. Cần chọn `COUNT`, `COUNT(DISTINCT ...)` và điều kiện join theo chính đối tượng nghiệp vụ muốn đếm.

## 15. Truy vấn scalar và `Object[]`

Không phải lúc nào ta cũng cần toàn bộ Product entity.

Ví dụ chỉ lấy ID và tên:

~~~java
Query query = em.createQuery(
    "SELECT p.id, p.name FROM Product p " +
    "WHERE p.status = :status"
);

query.setParameter("status", ProductStatus.ACTIVE);

List<?> rows = query.getResultList();
for (Object row : rows) {
    Object[] values = (Object[]) row;
    Long id = (Long) values[0];
    String name = (String) values[1];
    System.out.println(id + " - " + name);
}
~~~

Với nhiều select expressions, mỗi dòng thường được biểu diễn thành một `Object[]` khi sử dụng dạng này.

**Rủi ro:** thứ tự phần tử là thứ tự trong `SELECT`. Đổi câu query từ `p.id, p.name` thành `p.name, p.id` sẽ khiến code cast sai nếu không sửa theo.

### Dùng TypedQuery với Object[]

Có thể diễn đạt kiểu rõ hơn:

~~~java
TypedQuery<Object[]> query = em.createQuery(
    "SELECT p.id, p.name FROM Product p",
    Object[].class
);

List<Object[]> rows = query.getResultList();
~~~

Dù loại collection đã được khai báo, từng vị trí bên trong mảng vẫn cần cast đúng kiểu. Khi có nhiều projection fields và code được sử dụng lâu dài, **constructor expression trả DTO** thường dễ bảo trì hơn.

## 16. TypedQuery trả DTO bằng constructor expression

Giả sử API chỉ cần ID, tên và giá; ta định nghĩa DTO:

~~~java
package com.example.catalog.dto;

import java.math.BigDecimal;

public class ProductSummary {

    private final Long id;
    private final String name;
    private final BigDecimal price;

    public ProductSummary(
            Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

JPQL:

~~~java
TypedQuery<ProductSummary> query = em.createQuery(
    "SELECT NEW com.example.catalog.dto.ProductSummary(" +
    "p.id, p.name, p.price) " +
    "FROM Product p WHERE p.status = :status " +
    "ORDER BY p.name ASC, p.id ASC",
    ProductSummary.class
);

List<ProductSummary> products = query
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();
~~~

### Điều kiện của constructor expression

- Sử dụng tên class đầy đủ gồm package trong JPQL.
- Class phải có constructor phù hợp về **số lượng, thứ tự và kiểu tham số**.
- Constructor cần có mức truy cập phù hợp để provider tạo instance.
- Kết quả là các **DTO object**, không phải managed Product entity.
- Sửa field trong DTO không khiến JPA dirty checking cập nhật Product.

Đây là lựa chọn tốt khi API chỉ đọc một số field, tránh nạp entity graph không cần thiết và giúp giảm nguy cơ lazy loading/N+1 ở tầng serialization.

## 17. Truy vấn với JOIN quan hệ entity

`Product` có thuộc tính:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Category category;
~~~

Nếu cần các sản phẩm thuộc một category có code `BOOK`:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p " +
    "JOIN p.category c " +
    "WHERE c.code = :code",
    Product.class
);

List<Product> books = query
    .setParameter("code", "BOOK")
    .getResultList();
~~~

`p.category` là **đường dẫn quan hệ trong Java**, không phải tên FK `category_id`.

### Navigation và JOIN

| Cách viết | Ý nghĩa |
| --- | --- |
| `p.category` | Thuộc tính quan hệ Product → Category |
| `JOIN p.category c` | Join qua quan hệ và đặt alias c |
| `c.code` | Thuộc tính Java của Category |
| `p.category.id` | Điều hướng tới identity của Category, khi phù hợp |

### Phân biệt `JOIN` và `JOIN FETCH`

Query thường:

~~~jpql
SELECT p FROM Product p JOIN p.category c
~~~

không nhất thiết nạp sẵn category như một entity đã initialized trong mọi tình huống.

Fetch join:

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p " +
        "JOIN FETCH p.category " +
        "WHERE p.status = :status",
        Product.class)
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();
~~~

`JOIN FETCH` hướng provider nạp association cùng lúc như một phần fetch plan, giúp tránh N+1 trong những tình huống phù hợp.

**Lưu ý:** việc JOIN FETCH collection-valued cùng pagination có thể tạo kết quả không như mong muốn hoặc khiến provider phân trang trong bộ nhớ; số row SQL có thể lớn hơn số root entities. Với to-one như `Product.category`, tính toán thường đơn giản hơn, nhưng vẫn phải xem query plan thực tế.

## 18. `DISTINCT` và kết quả entity bị lặp do JOIN

Với quan hệ một–nhiều hoặc nhiều–nhiều, JOIN có thể tạo nhiều hàng SQL tương ứng một entity root. Ví dụ giả sử Product có collection `tags`:

~~~jpql
SELECT p FROM Product p JOIN p.tags t
WHERE t.name = :tag
~~~

Nếu một truy vấn join qua nhiều collection, kết quả có thể chứa nhiều hàng SQL cùng đại diện một Product. Khi cần tập entity không trùng, có thể dùng:

~~~jpql
SELECT DISTINCT p FROM Product p JOIN p.tags t
WHERE t.name = :tag
~~~

`DISTINCT` là ngữ nghĩa JPQL cho kết quả; cách provider đẩy DISTINCT xuống SQL hoặc khử trùng tại tầng ORM có thể khác theo phiên bản/cấu hình. Không dùng DISTINCT chỉ để che một JOIN sai mô hình hoặc để sửa một query count không có tiêu chí đếm rõ.

### Vấn đề với pagination

Khi root entity được nhân bản bởi JOIN collection, phân trang bằng `setFirstResult`/`setMaxResults` có thể gây thiếu/khó đoán số entity trên trang, đặc biệt với fetch join. Một mẫu phổ biến là:

1. Truy vấn page **ID của root** theo điều kiện và thứ tự ổn định.
2. Truy vấn nạp root entities cho danh sách ID đó bằng fetch plan thích hợp.
3. Sắp xếp kết quả theo thứ tự ID đã lấy ở bước đầu nếu query thứ hai không bảo đảm thứ tự tương đương.

Đây là một quyết định thiết kế truy vấn quan trọng, không phải lỗi của `TypedQuery`.

## 19. Sắp xếp kết quả bằng `ORDER BY`

Ví dụ:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p " +
    "ORDER BY p.price DESC, p.id ASC",
    Product.class
);
~~~

Không có `ORDER BY`, database **không bảo đảm thứ tự hàng**. Ngay cả khi lần chạy đầu cho ID tăng dần, dữ liệu lớn, index, query plan hoặc concurrency có thể khiến thứ tự thay đổi.

### Dynamic sort phải dùng whitelist

Không thể binding tên cột:

~~~jpql
ORDER BY p.:sortField
~~~

vì parameter dùng cho **giá trị**, không phải identifier hoặc cấu trúc query.

Không nên:

~~~java
String jpql = "SELECT p FROM Product p ORDER BY p." + userInput;
~~~

Cách tốt hơn:

~~~java
String orderExpression = switch (sortBy) {
    case "price" -> "p.price";
    case "name" -> "p.name";
    case "createdAt" -> "p.createdAt";
    default -> "p.id";
};

String jpql =
        "SELECT p FROM Product p ORDER BY " +
        orderExpression + " ASC, p.id ASC";

TypedQuery<Product> query =
        em.createQuery(jpql, Product.class);
~~~

Đoạn trên dùng switch expression của Java hiện đại; có thể viết tương đương bằng `if/else` nếu dự án dùng Java cũ. Quan trọng nhất là **chỉ ghép các mảnh JPQL do ứng dụng định nghĩa sẵn**, không ghép chuỗi tùy ý do người dùng cung cấp.

## 20. Phân trang với `setFirstResult()` và `setMaxResults()`

`TypedQuery` thừa hưởng các phương thức cấu hình pagination của Query:

~~~java
int page = 2;   // Trang 2 nếu đếm từ 0.
int size = 20;

List<Product> results = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.status = :status " +
        "ORDER BY p.createdAt DESC, p.id DESC",
        Product.class)
    .setParameter("status", ProductStatus.ACTIVE)
    .setFirstResult(page * size)
    .setMaxResults(size)
    .getResultList();
~~~

| API | Ý nghĩa |
| --- | --- |
| `setFirstResult(0)` | Bắt đầu từ kết quả đầu tiên |
| `setFirstResult(40)` | Bỏ qua 40 kết quả trước đó |
| `setMaxResults(20)` | Lấy tối đa 20 kết quả |

Phần lớn provider/DBMS biểu diễn pagination bằng `LIMIT/OFFSET` hoặc cú pháp tương đương. Cú pháp SQL thật phụ thuộc dialect.

### Tránh lỗi overflow và tham số âm

Với API nhận `page` và `size`, nên kiểm tra:

~~~java
if (page < 0 || size <= 0 || size > 200) {
    throw new IllegalArgumentException("Pagination invalid");
}

long offset = (long) page * size;
if (offset > Integer.MAX_VALUE) {
    throw new IllegalArgumentException("Offset too large");
}

query.setFirstResult((int) offset);
query.setMaxResults(size);
~~~

`setFirstResult` và `setMaxResults` dùng `int`; đừng nhân hai số `int` quá lớn rồi để overflow.

### Pagination cần thứ tự ổn định

Nếu chỉ `ORDER BY p.createdAt DESC` và có nhiều sản phẩm cùng `createdAt`, các trang có thể trùng hoặc bỏ sót khi DB chọn thứ tự khác giữa những lần chạy. Thêm tie-breaker duy nhất, ví dụ `p.id DESC`.

Ngay cả khi order ổn định, **offset pagination không cho một snapshot nhất quán qua nhiều request** khi dữ liệu mới được INSERT/DELETE giữa các lần tải trang. Nếu cần hành vi tốt cho danh sách biến động nhanh, cân nhắc keyset pagination và một chính sách nhất quán phù hợp.

## 21. Keyset pagination: khi OFFSET lớn trở nên tốn kém

Với danh sách sắp xếp theo ID tăng:

~~~jpql
SELECT p FROM Product p
WHERE p.id > :lastSeenId
ORDER BY p.id ASC
~~~

Và:

~~~java
List<Product> nextPage = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.id > :lastSeenId ORDER BY p.id ASC",
        Product.class)
    .setParameter("lastSeenId", lastSeenId)
    .setMaxResults(20)
    .getResultList();
~~~

Thay vì bỏ qua hàng triệu row bằng OFFSET, ứng dụng dùng key của item cuối trang trước để tìm trang kế tiếp. Điều này thường hiệu quả hơn khi có index phù hợp.

Nếu sắp xếp theo nhiều field:

~~~jpql
ORDER BY p.price ASC, p.id ASC
~~~

thì cursor cần đủ cả hai thành phần:

~~~jpql
WHERE (p.price > :lastPrice)
   OR (p.price = :lastPrice AND p.id > :lastId)
ORDER BY p.price ASC, p.id ASC
~~~

Cần xử lý giá trị null, sự thay đổi giá giữa trang, filter và quyền truy cập theo yêu cầu. `TypedQuery` vẫn là công cụ tạo và thực thi câu JPQL ấy; kỹ thuật pagination là một thiết kế **ở cấp query/ứng dụng**.

## 22. Named query: khai báo JPQL có tên trên entity

Khi câu JPQL được tái sử dụng nhiều nơi, có thể đặt nó dưới dạng **named query**:

~~~java
@Entity
@NamedQuery(
    name = "Product.findActive",
    query = "SELECT p FROM Product p " +
            "WHERE p.status = :status " +
            "ORDER BY p.id ASC")
public class Product {
    // ...
}
~~~

Ở đây, cần import `jakarta.persistence.NamedQuery` và các annotation khác của entity.

Tạo query bằng tên:

~~~java
TypedQuery<Product> query = em.createNamedQuery(
    "Product.findActive",
    Product.class
);

List<Product> products = query
    .setParameter("status", ProductStatus.ACTIVE)
    .getResultList();
~~~

**Phân biệt:**

- `createQuery(jpql, Product.class)` nhận **chuỗi JPQL**.
- `createNamedQuery("Product.findActive", Product.class)` nhận **tên của truy vấn đã khai báo**.

Không truyền cả chuỗi `SELECT ...` vào `createNamedQuery`, trừ khi một named query được đặt tên nguyên văn kỳ lạ như vậy (không phải thực hành tốt).

### Lợi ích của named query

- Tập trung các truy vấn được tái sử dụng.
- Có thể được provider parse/validate sớm trong lifecycle.
- Dễ gắn với tên nghiệp vụ và truy tìm nơi sử dụng.

Tuy nhiên, named query không tự làm query nhanh hơn mọi dynamic JPQL và không thay thế index, query plan hay kiểm thử.

## 23. Query parameters và metadata

JPA cung cấp interface `Parameter<T>` để mô tả tham số của query. Có thể kiểm tra danh sách parameter:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p WHERE p.status = :status",
    Product.class
);

for (Parameter<?> parameter : query.getParameters()) {
    System.out.println(parameter.getName());
}
~~~

Đoạn minh họa dùng `jakarta.persistence.Parameter`. Các API như `getParameter(...)`, `isBound(...)` và `getParameterValue(...)` có thể hữu ích khi xây dựng tầng tiện ích/truy vấn động và khi debug binding.

### Không lạm dụng introspection để thay kiểm soát input

Biết query có parameter nào không có nghĩa mọi giá trị user input đều an toàn về mặt nghiệp vụ. Vẫn phải:

- Validate giá, số lượng, ID và phạm vi quyền truy cập.
- Giới hạn danh sách IN và pagination.
- Chỉ dùng tên field/ORDER BY từ whitelist.
- Tránh log dữ liệu nhạy cảm khi debug bind values.

Tham số hóa giải quyết **cách truyền giá trị**, không tự giải quyết authorization, multi-tenancy hay data leakage.

## 24. Cấu hình timeout và query hints

`Query` và `TypedQuery` có thể dùng `setHint()`:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p WHERE p.status = :status",
    Product.class
);

query.setParameter("status", ProductStatus.ACTIVE);
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

Giá trị timeout hint ở đây được biểu diễn theo **milli giây** theo quy ước Jakarta Persistence. Tuy nhiên, **không được cam kết mọi DBMS/provider thực hiện ngắt truy vấn chính xác sau 3 giây**: driver, locking, network, DB statement timeout và transaction manager cũng ảnh hưởng.

Ngoài hint chuẩn, provider có thể có các hint riêng về:

- Fetch size.
- Read-only behavior.
- Query cache.
- Execution plan.
- Timeout/lock timeout.

Với Hibernate hoặc EclipseLink, tên hint và ý nghĩa có thể khác. Nếu mã cần portable giữa các provider, chỉ nên phụ thuộc vào khả năng được đặc tả bảo đảm và có phương án xử lý khi hint bị bỏ qua.

### Hints không thay được index

Đặt timeout dài hơn không làm một full table scan trở nên hiệu quả. Nếu truy vấn chậm, xem execution plan, index, số hàng, JOIN, phân trang và lượng dữ liệu đang trả về trước.

## 25. Flush mode ở cấp EntityManager và Query

JPQL SELECT có thể được thực hiện khi persistence context đang chứa những entity đã sửa nhưng chưa flush.

~~~java
Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("249000.00"));

List<Product> expensive = em.createQuery(
        "SELECT p FROM Product p WHERE p.price >= :min",
        Product.class)
    .setParameter("min", new BigDecimal("240000.00"))
    .getResultList();
~~~

### `FlushModeType.AUTO`

Với `AUTO`, provider phải bảo đảm những thay đổi pending có thể ảnh hưởng kết quả query được **phản ánh trong kết quả** theo quy tắc của đặc tả. Provider thường flush trước query có liên quan hoặc có cơ chế khác tương đương.

### `FlushModeType.COMMIT`

Với `COMMIT`, việc đồng bộ có thể được trì hoãn tới commit; tác động của những thay đổi pending đến kết quả query trước commit không được định nghĩa giống AUTO.

Có thể cấu hình:

~~~java
em.setFlushMode(FlushModeType.AUTO);
~~~

hoặc trên một query:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p",
    Product.class
);
query.setFlushMode(FlushModeType.COMMIT);
~~~

**Flush mode không phải transaction isolation.** `AUTO/COMMIT` mô tả tương tác giữa persistence context và query của chính ứng dụng; khả năng một transaction khác nhìn được write chưa commit là do database isolation.

### Đừng dùng query chỉ để “ép flush” không rõ lý do

Nếu nghiệp vụ thực sự cần xác định ràng buộc DB đã được kiểm tra hoặc thứ tự SQL đã hoàn thành trong transaction, nên gọi `em.flush()` rõ ràng ở điểm phù hợp thay vì dựa vào một SELECT vô tình kích hoạt flush. Nhưng flush **không phải commit**, và một số constraint có thể còn được kiểm tra khi transaction kết thúc.

## 26. Query lock mode: đọc để cập nhật

Một truy vấn trả về entity có thể yêu cầu lock:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p WHERE p.id = :id",
    Product.class
);

query.setParameter("id", productId);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);

Product product = query.getSingleResult();
~~~

Đoạn dùng `jakarta.persistence.LockModeType` và cần transaction phù hợp. Provider ánh xạ khóa theo DBMS, có thể sử dụng cú pháp tương tự `SELECT ... FOR UPDATE` khi được hỗ trợ.

### Khi nào cần lock?

- Một transaction cần đọc rồi sửa một entity trong điều kiện có cạnh tranh cao.
- Muốn ngăn/xử lý những cập nhật đồng thời theo giao thức khóa nhất quán.
- Nghiệp vụ có invariant mà optimistic locking đơn thuần chưa đáp ứng.

### Cần phân biệt

- `PESSIMISTIC_WRITE` có thể gây chờ lock, timeout và deadlock.
- `OPTIMISTIC` có thể kiểm tra version ở thời điểm thích hợp; không giữ row lock dài theo cùng cách.
- Lock mode áp dụng chủ yếu cho truy vấn **entity**; không thể coi `SELECT COUNT(...)` hay DTO constructor query là một cách portable để khóa tất cả hàng trong tập kết quả.
- Khóa một hàng không tự khóa mọi row có thể xuất hiện mới do transaction khác.

Không dùng pessimistic lock trên mọi truy vấn chỉ vì muốn “đọc dữ liệu chắc chắn mới nhất”; freshness của dữ liệu còn liên quan isolation/snapshot và cache.

## 27. Cách dùng Query cho JPQL UPDATE

JPA cho phép bulk update bằng JPQL:

~~~java
int affected = em.createQuery(
        "UPDATE Product p " +
        "SET p.status = :newStatus " +
        "WHERE p.status = :oldStatus")
    .setParameter("newStatus", ProductStatus.INACTIVE)
    .setParameter("oldStatus", ProductStatus.DRAFT)
    .executeUpdate();
~~~

Kết quả `affected` là số entity/hàng được báo cáo chịu tác động theo ngữ nghĩa query/provider. **Không có entity Product managed được trả về** như trong SELECT.

Những điểm cần ghi nhớ:

1. Bulk UPDATE phải được thực hiện trong **transaction** phù hợp.
2. Nó trực tiếp tác động dữ liệu ở DB, **không chạy dirty checking từng entity managed**.
3. Các managed Product đã nạp trước đó có thể bị stale sau bulk update.
4. Bulk UPDATE thông thường **không tự làm version check/increment cho từng entity** như khi sửa entity managed có `@Version`.
5. Lifecycle callbacks như `@PreUpdate` không được gọi trên từng hàng theo cùng cách entity-state update.
6. Những quan hệ và cascade có ngữ nghĩa riêng; không suy luận từ bulk query rằng provider sẽ xử lý toàn bộ object graph như gọi `em.remove(entity)` từng cái.

### Khi nào dùng bulk UPDATE?

Khi cần cập nhật số lượng lớn hàng theo một điều kiện rõ ràng, và ứng dụng chấp nhận tự quản lý vấn đề context stale, version, audit và business events. Nếu chỉ cần sửa một Product managed, phương thức nghiệp vụ và dirty checking thường dễ hiểu, an toàn hơn.

## 28. Query cho JPQL DELETE

Ví dụ xóa các sản phẩm ở trạng thái DRAFT đã tạo trước mốc thời gian:

~~~java
int deleted = em.createQuery(
        "DELETE FROM Product p " +
        "WHERE p.status = :status " +
        "AND p.createdAt < :cutoff")
    .setParameter("status", ProductStatus.DRAFT)
    .setParameter(
        "cutoff",
        Instant.parse("2026-01-01T00:00:00Z"))
    .executeUpdate();
~~~

**Cần đặc biệt cẩn thận với FK:** bulk DELETE không tương đương việc xóa từng entity thông qua cascade remove/orphan removal do JPA quản lý. Nếu bảng khác tham chiếu Product và DB không có chính sách xóa phù hợp, SQL sẽ bị chặn.

### Không dùng `getResultList()` cho UPDATE/DELETE

Sai:

~~~java
em.createQuery("UPDATE Product p SET p.status = :status")
    .getResultList();
~~~

Đúng về loại operation:

~~~java
int count = em.createQuery(
        "UPDATE Product p SET p.status = :status")
    .setParameter("status", ProductStatus.ACTIVE)
    .executeUpdate();
~~~

`executeUpdate()` yêu cầu transaction thích hợp; gọi ngoài transaction có thể gặp `TransactionRequiredException`. Không nhầm `executeUpdate()` với cách lấy danh sách entity.

## 29. Bulk query và persistence context stale

Giả sử:

~~~java
Product product = em.find(Product.class, 101L);
ProductStatus oldStatus = product.getStatus();

em.createQuery(
        "UPDATE Product p SET p.status = :status " +
        "WHERE p.id = :id")
    .setParameter("status", ProductStatus.INACTIVE)
    .setParameter("id", 101L)
    .executeUpdate();
~~~

Sau khi bulk SQL đã chạy, `product.getStatus()` **có thể vẫn bằng `oldStatus`**. Điều này không có nghĩa database chưa cập nhật; managed object đang giữ state trước bulk.

Một quy trình có chủ đích:

~~~java
em.flush(); // Đồng bộ pending managed changes trước bulk.

int count = em.createQuery(
        "UPDATE Product p SET p.status = :newStatus " +
        "WHERE p.status = :oldStatus")
    .setParameter("newStatus", ProductStatus.INACTIVE)
    .setParameter("oldStatus", ProductStatus.DRAFT)
    .executeUpdate();

em.clear(); // Detach các managed entities có thể stale.
~~~

**Không áp dụng mẫu này máy móc:** `clear()` detach mọi entity đang managed, nên code còn giữ reference cũ không thể tiếp tục sửa và mong dirty checking hoạt động. Nếu chỉ một entity cần cập nhật lại state, `em.refresh(entity)` có thể phù hợp hơn, nhưng sẽ chịu isolation/snapshot và có thể ghi đè pending changes.

## 30. Query SELECT trong transaction và ngoài transaction

Truy vấn SELECT cơ bản thường có thể thực thi mà không cần transaction ghi đang hoạt động, tùy môi trường và cách EntityManager được quản lý:

~~~java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p",
        Product.class)
    .getResultList();
~~~

Nhưng:

- Bulk UPDATE/DELETE cần transaction thích hợp.
- Pessimistic locking yêu cầu transaction theo ngữ nghĩa JPA.
- Lazy associations có thể cần persistence context còn mở.
- Nhiều SELECT trong transaction muốn có snapshot nhất quán phải dựa vào isolation thực tế của DBMS.
- Việc sửa entity trong một context mở ngoài transaction không đồng nghĩa SQL ghi sẽ tự commit.

### Mẫu RESOURCE_LOCAL đầy đủ

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    List<Product> products = em.createQuery(
            "SELECT p FROM Product p " +
            "WHERE p.status = :status",
            Product.class)
        .setParameter("status", ProductStatus.ACTIVE)
        .getResultList();

    // Xử lý trong cùng đơn vị công việc.

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Trong ứng dụng Spring hoặc Jakarta EE dùng JTA, transaction thường được framework/container quản lý. Không tự gọi `em.getTransaction()` trên JTA-managed EntityManager.

## 31. Vòng đời Query và EntityManager

Một `Query` được tạo từ `EntityManager`, liên hệ tới mapping và persistence context mà EntityManager quản lý.

~~~java
EntityManager em = emf.createEntityManager();
try {
    TypedQuery<Product> query = em.createQuery(
        "SELECT p FROM Product p",
        Product.class);

    List<Product> products = query.getResultList();
} finally {
    em.close();
}
~~~

Không lưu trữ một `TypedQuery` trong singleton service rồi dùng chung đồng thời cho nhiều request:

- `Query` có các trạng thái mutable như parameters, pagination và hints.
- `EntityManager` không được thiết kế để chia sẻ concurrent giữa các thread.
- Query được tạo từ một EntityManager cụ thể; sau khi context/manager đóng, không nên giả định query vẫn thực thi an toàn.

**Tái sử dụng chuỗi JPQL/named query là bình thường; tái sử dụng cùng một instance Query mutable giữa nhiều transaction/thread là thiết kế không phù hợp.**

### Một EntityManager, nhiều Query

Trong cùng transaction:

~~~java
TypedQuery<Long> countQuery = em.createQuery(
    "SELECT COUNT(p) FROM Product p",
    Long.class
);

TypedQuery<Product> pageQuery = em.createQuery(
    "SELECT p FROM Product p ORDER BY p.id ASC",
    Product.class
);
~~~

Hai query có state tham số/pagination riêng nhưng sử dụng cùng persistence context, nên flush mode, managed entities và transaction của EntityManager vẫn có thể ảnh hưởng cả hai.

## 32. First-level cache và query results

Khi `TypedQuery<Product>` trả về Product#101, JPA quản lý identity của entity trong persistence context:

~~~java
Product a = em.find(Product.class, 101L);

Product b = em.createQuery(
        "SELECT p FROM Product p WHERE p.id = :id",
        Product.class)
    .setParameter("id", 101L)
    .getSingleResult();

System.out.println(a == b); // true trong cùng persistence context
~~~

Tuy nhiên, JPQL SELECT thường vẫn phải thực thi truy vấn để tìm **tập kết quả thỏa điều kiện**, dù entity tương ứng đã managed. Có thể database đã thay đổi bởi transaction khác nhưng managed entity trong context vẫn giữ state cũ.

### Phân biệt ba khái niệm

1. **Query result membership:** những ID/hàng nào được database/query lọc ra.
2. **Entity identity:** với cùng ID trong context, provider trả managed instance tương ứng.
3. **Entity field freshness:** giá trị field của managed instance có thể chưa được refresh từ DB.

Vì thế việc gọi lại JPQL query **không phải bảo đảm mọi entity đang managed được làm mới**. Nếu cần đọc lại một entity, cân nhắc `refresh()` hoặc context mới và isolation phù hợp.

## 33. Query cache khác first-level cache

Một số provider hỗ trợ query cache hoặc second-level cache để giảm truy cập DB. Đây là các cơ chế tùy provider/configuration.

| Loại cache | Ý nghĩa |
| --- | --- |
| First-level cache | Identity map trong persistence context, là phần cốt lõi của JPA |
| Second-level cache | Cache entity data giữa nhiều persistence context tùy provider và cấu hình |
| Query cache | Cache thông tin/kết quả truy vấn tùy provider, không phải hành vi mặc định portable |

Đừng bật query cache chỉ vì có câu JPQL được gọi thường xuyên; phải xem tỷ lệ thay đổi dữ liệu, invalidation, độ mới cần thiết và hiệu năng thật. Khi điều tra “JPQL trả dữ liệu cũ”, cần phân biệt cache với transaction snapshot hoặc entity managed đã stale.

## 34. JPQL khác native SQL qua EntityManager

JPA hỗ trợ truy vấn SQL thuần:

~~~java
Query query = em.createNativeQuery(
    "SELECT * FROM products WHERE status = ?1",
    Product.class
);

query.setParameter(1, "ACTIVE");
List<?> rows = query.getResultList();
~~~

Đây là **native query**, nên dùng tên bảng `products` và cột `status`. Ví dụ mapping enum `STRING` khiến giá trị DB lưu chữ `ACTIVE`.

Ngược lại, JPQL:

~~~java
TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p WHERE p.status = :status",
    Product.class
);
query.setParameter("status", ProductStatus.ACTIVE);
~~~

dùng entity Product và enum Java.

### Khi nào dùng native SQL?

- Cần tính năng SQL đặc thù DBMS mà JPQL không hỗ trợ phù hợp.
- Cần truy vấn tối ưu đặc biệt, CTE, window function hoặc database-specific operations.
- Cần dùng table/view/function theo đặc tính hệ thống, với mapping kết quả rõ.

Nhưng native SQL làm giảm tính portable. Bulk native SQL cũng có thể khiến persistence context stale, giống vấn đề bulk JPQL. Không nên chọn native SQL chỉ vì chưa quen cú pháp `JOIN p.category` của JPQL.

## 35. Criteria API so với JPQL string

Khi query có nhiều điều kiện tùy chọn, ngoài cách tạo JPQL string bằng những mảnh cố định, JPA cung cấp Criteria API.

Ví dụ:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq =
        cb.createQuery(Product.class);

Root<Product> p = cq.from(Product.class);

cq.select(p)
  .where(cb.equal(p.get("status"), ProductStatus.ACTIVE))
  .orderBy(cb.asc(p.get("id")));

TypedQuery<Product> query = em.createQuery(cq);
List<Product> result = query.getResultList();
~~~

Cần import `jakarta.persistence.criteria.CriteriaBuilder`, `CriteriaQuery` và `Root`.

Vẫn là `EntityManager.createQuery(...)`, nhưng overload nhận **CriteriaQuery** thay vì String.

### Chọn công cụ

| Tình huống | Lựa chọn thường hợp lý |
| --- | --- |
| SELECT đơn giản, ít điều kiện | JPQL string + TypedQuery |
| Query đã biết trước và tái sử dụng | `@NamedQuery` + createNamedQuery |
| Bộ lọc động nhiều điều kiện | Criteria API hoặc query builder có kiểm soát |
| Truy vấn SQL đặc thù DBMS | NativeQuery |
| Khối lượng lớn update/delete | JPQL bulk DML hoặc native SQL với xử lý context |

Không nên coi Criteria API luôn nhanh hơn JPQL. Cả hai được provider chuyển thành SQL; hiệu năng phụ thuộc SQL cuối cùng, index, parameters và execution plan.

## 36. Lỗi thường gặp khi tạo Query và TypedQuery

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query báo entity không tồn tại | Viết tên bảng SQL thay cho entity name | Dùng `Product` hoặc tên `@Entity(name=...)` |
| Query báo không có thuộc tính `stock_quantity` | Dùng tên cột thay cho field Java | Dùng `p.stockQuantity` |
| Không bind được parameter | `:status` trong JPQL nhưng dùng `setParameter(":status", ...)` | Bỏ dấu `:` trong tên khi set |
| Positional parameter không đúng | `?1` nhưng gọi `setParameter(0, ...)` | Đếm từ 1 |
| Lọc Enum sai kiểu | Bind `"ACTIVE"` thay vì enum | Bind `ProductStatus.ACTIVE` |
| `getSingleResult()` ném NoResultException | Không có bản ghi phù hợp | Xử lý empty nếu hợp nghiệp vụ |
| `getSingleResult()` ném NonUniqueResultException | Query trả nhiều kết quả | Xem uniqueness của điều kiện hoặc dùng list |
| `ClassCastException` khi cast kết quả | SELECT scalar nhưng cast Product | Dùng typed query đúng result class |
| `List<Object[]>` có sai thứ tự field | Thay đổi thứ tự SELECT | Dùng DTO constructor expression |
| `IN :ids` với list rỗng lỗi SQL | Dialect/provider không hỗ trợ empty IN | Trả list rỗng ở ứng dụng hoặc thay predicate |
| Tên sort gây query injection | Nối input trực tiếp vào ORDER BY | Dùng whitelist expression |
| Trang kết quả trùng/thiếu | ORDER BY thiếu tie-breaker hoặc dữ liệu đổi | Sắp xếp ổn định; cân nhắc keyset |
| Query nhanh ở dev, chậm ở prod | Index/data volume/query plan khác | Đo execution plan, tối ưu fetch/index |
| JPQL JOIN fetch collection bị phân trang sai | Root bị nhân bản bởi collection rows | Page root IDs trước, fetch sau |
| UPDATE JPQL nhưng entity managed vẫn cũ | Bulk update bypass managed state | Flush trước, clear/refresh sau nếu phù hợp |
| SELECT gọi executeUpdate | Sai API theo loại query | SELECT dùng getResultList/getSingleResult |
| UPDATE gọi getResultList | Sai API | UPDATE/DELETE dùng executeUpdate trong transaction |
| Pessimistic query không có transaction | Lock mode cần TX | Tạo boundary transaction đúng |
| Query dùng sau khi EntityManager đóng | Gắn query vào context đã kết thúc | Tạo trong lifetime manager hiện hành |
| Chia sẻ Query giữa threads | Query và EntityManager không thread-safe | Tạo query theo unit of work |
| Read-only DTO bị kỳ vọng dirty check | DTO không phải managed entity | Muốn cập nhật phải nạp managed entity |
| JPQL nhìn state bất ngờ sau setter | Flush mode/cache/isolation | Phân biệt pending state, flush và transaction |

## 37. Ví dụ service truy vấn có tham số, phân trang và DTO

Sau khi hiểu từng API, ta kết hợp chúng thành một service trả page summary. Ví dụ này giả sử input được validate và transaction/persistence context do caller quản lý.

~~~java
package com.example.catalog;

import com.example.catalog.dto.ProductSummary;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import java.math.BigDecimal;
import java.util.List;

public class ProductSearchService {

    private final EntityManager em;

    public ProductSearchService(EntityManager em) {
        this.em = em;
    }

    public List<ProductSummary> searchActive(
            BigDecimal minPrice,
            int page,
            int size) {

        if (minPrice == null || minPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid minimum price");
        }
        if (page < 0 || size <= 0 || size > 100) {
            throw new IllegalArgumentException("Invalid pagination");
        }

        long offset = (long) page * size;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Offset too large");
        }

        TypedQuery<ProductSummary> q = em.createQuery(
            "SELECT NEW com.example.catalog.dto.ProductSummary(" +
            "p.id, p.name, p.price) " +
            "FROM Product p " +
            "WHERE p.status = :status " +
            "AND p.price >= :minPrice " +
            "ORDER BY p.price ASC, p.id ASC",
            ProductSummary.class
        );

        return q
            .setParameter("status", ProductStatus.ACTIVE)
            .setParameter("minPrice", minPrice)
            .setFirstResult((int) offset)
            .setMaxResults(size)
            .getResultList();
    }
}
~~~

### Những gì service này làm rõ

1. `createQuery(jpql, ProductSummary.class)` tạo **TypedQuery của DTO**, không phải entity.
2. Status và giá là **tham số**, không ghép giá trị người dùng vào JPQL.
3. Pagination được kiểm tra tránh giá trị âm hoặc overflow.
4. `ORDER BY p.price ASC, p.id ASC` tạo thứ tự rõ và có tie-breaker.
5. DTO chỉ lấy các field cần cho API, tránh nạp toàn bộ Product.
6. Query không tự bảo vệ quyền truy cập hoặc tenant isolation; nếu hệ thống đa tenant, phải bổ sung predicate/authorization phù hợp.

### Nếu API cần tổng số trang

Chạy query COUNT riêng nhưng **cùng điều kiện lọc**:

~~~java
long total = em.createQuery(
        "SELECT COUNT(p) FROM Product p " +
        "WHERE p.status = :status " +
        "AND p.price >= :minPrice",
        Long.class)
    .setParameter("status", ProductStatus.ACTIVE)
    .setParameter("minPrice", minPrice)
    .getSingleResult();
~~~

Sau đó có thể tính tổng trang:

~~~java
long totalPages = (total + size - 1L) / size;
~~~

**Lưu ý:** nếu page query và count query diễn ra ở các transaction/snapshot khác nhau hoặc dữ liệu bị thay đổi giữa hai câu truy vấn, số đếm và nội dung trang có thể không hoàn toàn khớp. Đây là vấn đề isolation/consistency của DBMS, không phải một lỗi của `TypedQuery`.

## 38. Cách xử lý lỗi và transaction

Trong mã thực tế, exception có thể phát sinh khi **tạo query**, **gắn parameter** hoặc **thực thi**:

| Mốc | Loại vấn đề điển hình |
| --- | --- |
| `em.createQuery(...)` | JPQL sai cú pháp, entity/attribute không hợp lệ hoặc result class không phù hợp |
| `query.setParameter(...)` | Tham số không tồn tại, kiểu hoặc giá trị binding không hợp lệ |
| `query.getResultList()` | SQL/DB error, timeout, lock conflict, flush failure |
| `query.getSingleResult()` | NoResultException, NonUniqueResultException hoặc lỗi thực thi |
| `query.executeUpdate()` | Thiếu transaction, vi phạm constraint, SQL/DB error |
| `tx.commit()` | Flush pending, optimistic lock conflict, deferred constraint, transaction failure |

Một catch tổng quát:

~~~java
catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

phù hợp với ví dụ RESOURCE_LOCAL để rollback và không nuốt lỗi. Nhưng trong Spring/JTA, rollback thường do transaction manager xử lý dựa trên exception và annotation/cấu hình, không tự gọi `tx.rollback()` trên JTA-managed EntityManager.

### Không tiếp tục transaction đã lỗi SQL

Nếu database báo constraint violation ở flush hoặc query execution, transaction có thể đã bị đánh dấu rollback-only hoặc connection yêu cầu rollback. Không bắt lỗi rồi thực hiện tiếp các update trong cùng transaction như thể nó vẫn sạch.

### NoResultException có nghĩa gì?

`NoResultException` từ `getSingleResult()` thường biểu diễn không tìm thấy dữ liệu. Nó khác một lỗi SQL hoặc timeout; có thể được chuyển thành `Optional.empty()` hay HTTP 404 theo nghiệp vụ. Không dùng cách xử lý ấy cho mọi `PersistenceException`.

## 39. JPQL, multitenancy và authorization

Giả sử ứng dụng có nhiều tenant. Một câu truy vấn:

~~~jpql
SELECT p FROM Product p WHERE p.id = :id
~~~

chỉ tìm theo ID, không tự kiểm tra user hiện tại có quyền xem sản phẩm không. Nếu mô hình có thuộc tính tenant hoặc quan hệ owner, query cần thêm điều kiện tương ứng:

~~~jpql
SELECT p FROM Product p
WHERE p.id = :id
AND p.tenantId = :tenantId
~~~

Đoạn trên chỉ hợp lệ khi entity thực tế có persistent attribute `tenantId`; entity Product ví dụ chưa khai báo nó.

### Không coi ID có vẻ ngẫu nhiên là kiểm soát quyền

Một UUID hay ID dài chỉ là định danh, không tự bảo đảm phân quyền. Mỗi query cần thực thi tenant scoping, ownership checks hoặc policy bằng cơ chế phù hợp với kiến trúc.

Nếu provider có tenant filters hoặc row-level security của database, cần hiểu chúng hoạt động ra sao với JPQL, native query, bulk DML và background jobs. **TypedQuery cung cấp kiểu kết quả, không cung cấp authorization tự động.**

## 40. Nguyên tắc tối ưu khi dùng Query/TypedQuery

Một số thói quen đáng áp dụng:

1. **Chọn đúng projection:** chỉ cần hiển thị vài field thì ưu tiên DTO; cần chỉnh sửa entity thì chọn entity managed.
2. **Dùng named/positional parameters:** không ghép giá trị người dùng trực tiếp vào JPQL.
3. **Đặt ORDER BY khi phân trang:** bổ sung tie-breaker duy nhất.
4. **Giới hạn số kết quả:** API search không nên cho phép tải không giới hạn toàn bộ dữ liệu.
5. **Tránh N+1:** hiểu lazy associations, fetch join/entity graph và DTO projection.
6. **Kiểm tra query plan:** JOIN, index và predicate quyết định chi phí ở database.
7. **Không lạm dụng DISTINCT:** xử lý root duplication với đúng ngữ nghĩa, không che query sai.
8. **Thận trọng với bulk DML:** state context stale, version, cascade, lifecycle callbacks.
9. **Tách query khỏi transaction semantics:** flush mode khác isolation level.
10. **Không dùng một EntityManager/Query chung giữa threads:** tạo theo unit of work.
11. **Test trên DBMS thật:** những khác biệt dialect và mapping có thể không hiện trong unit test mock.
12. **Quan sát SQL có kiểm soát:** log SQL/bind parameter ở môi trường an toàn, tránh để lộ thông tin nhạy cảm.

### Query nào nên trả entity, query nào nên trả DTO?

| Nhu cầu | Dạng SELECT gợi ý | Kiểu |
| --- | --- | --- |
| Lấy Product để sửa giá trong transaction | `SELECT p FROM Product p ...` | `TypedQuery<Product>` |
| Danh sách catalog công khai | `SELECT NEW ...ProductSummary(...) ...` | `TypedQuery<ProductSummary>` |
| Đếm số sản phẩm ACTIVE | `SELECT COUNT(p) ...` | `TypedQuery<Long>` |
| Báo cáo nhóm theo category | `SELECT c.code, COUNT(p) ... GROUP BY c.code` | `TypedQuery<Object[]>` hoặc DTO |
| Update trạng thái hàng loạt | `UPDATE Product p SET ...` | `Query.executeUpdate()` |
| Xóa bản ghi theo điều kiện | `DELETE FROM Product p WHERE ...` | `Query.executeUpdate()` |

Điểm chính là **result type phải phản ánh SELECT expression**, thay vì chọn `Product.class` cho mọi truy vấn chỉ vì bảng chính là Product.

## 41. Ví dụ báo cáo GROUP BY và HAVING

Một nhu cầu thường gặp là đếm số sản phẩm của từng danh mục:

~~~java
TypedQuery<Object[]> report = em.createQuery(
    "SELECT c.code, COUNT(p) " +
    "FROM Product p JOIN p.category c " +
    "WHERE p.status = :status " +
    "GROUP BY c.code " +
    "HAVING COUNT(p) >= :minCount " +
    "ORDER BY c.code ASC",
    Object[].class
);

List<Object[]> rows = report
    .setParameter("status", ProductStatus.ACTIVE)
    .setParameter("minCount", 5L)
    .getResultList();

for (Object[] row : rows) {
    String categoryCode = (String) row[0];
    Long count = (Long) row[1];
    System.out.println(categoryCode + ": " + count);
}
~~~

Trong ví dụ:

- `JOIN p.category c` đi qua quan hệ entity.
- `GROUP BY c.code` nhóm theo mã danh mục.
- `HAVING COUNT(p) >= :minCount` lọc sau khi nhóm.
- `COUNT(p)` trả Long.
- Mỗi kết quả có hai phần tử trong `Object[]`.

Nếu API dùng báo cáo thường xuyên, DTO projection có constructor `(String categoryCode, Long count)` sẽ giúp tránh cast theo index.

### Phân biệt WHERE và HAVING

`WHERE` lọc từng Product trước khi nhóm. `HAVING` lọc **nhóm kết quả** dựa trên aggregate. Không thể thay `HAVING COUNT(p) >= :minCount` bằng `WHERE COUNT(p) >= :minCount` trong một JPQL grouping query chuẩn.

## 42. Bài tập vận dụng

### Bài 1 — Query hay TypedQuery?

Tìm toàn bộ Product ACTIVE. Chọn API nào để nhận trực tiếp `List<Product>` mà không cần unchecked cast?

**Gợi ý:** `TypedQuery<Product> query = em.createQuery("SELECT p FROM Product p WHERE p.status = :status", Product.class)`.

### Bài 2 — Entity name và tên bảng

Class `Product` có `@Table(name="products")`. Trong JPQL, nên viết `FROM Product p` hay `FROM products p`?

**Gợi ý:** dùng entity name `Product`, trừ khi `@Entity(name=...)` đã đổi tên entity.

### Bài 3 — Tên attribute

Field Java `stockQuantity` ánh xạ cột SQL `stock_quantity`. Điều kiện JPQL đúng là gì?

**Gợi ý:** `p.stockQuantity > :minStock`.

### Bài 4 — Named parameter

JPQL chứa `:minPrice`. Khi binding, gọi `setParameter(":minPrice", amount)` có đúng không?

**Gợi ý:** không. Truyền `setParameter("minPrice", amount)`.

### Bài 5 — Enum

`status` là `ProductStatus` và được ánh xạ `@Enumerated(EnumType.STRING)`. Có nên bind `"ACTIVE"` vào `:status` không?

**Gợi ý:** nên bind `ProductStatus.ACTIVE`; provider xử lý mapping Enum.

### Bài 6 — getSingleResult

Query tìm theo SKU trả về 0 hàng. `getSingleResult()` trả null hay ném exception?

**Gợi ý:** `NoResultException` trong API JPA truyền thống.

### Bài 7 — COUNT

Hãy viết query đếm Product có giá từ 100000 và khai báo kiểu kết quả.

**Gợi ý:** `TypedQuery<Long>` với `SELECT COUNT(p) FROM Product p WHERE p.price >= :minPrice`.

### Bài 8 — Phân trang

API yêu cầu page 3, size 20 (page đánh số từ 0). `setFirstResult()` và `setMaxResults()` nhận gì?

**Gợi ý:** offset 60 và max 20; cần ORDER BY ổn định.

### Bài 9 — Dynamic sort

User nhập `sortBy=name`. Có nên nối trực tiếp chuỗi user vào `ORDER BY p.` không?

**Gợi ý:** không. Dùng whitelist các thuộc tính được cho phép.

### Bài 10 — DTO projection

Query chỉ cần `p.id`, `p.name` và `p.price`. Muốn nhận `List<ProductSummary>`, nên dùng cú pháp nào?

**Gợi ý:** `SELECT NEW com.example.catalog.dto.ProductSummary(p.id, p.name, p.price)` và `ProductSummary.class`.

### Bài 11 — IN rỗng

Một tìm kiếm nhận danh sách ID rỗng. Vì sao không nên tự động gửi `IN :ids` với collection rỗng?

**Gợi ý:** cú pháp/behavior empty IN phụ thuộc provider/DBMS; trả list rỗng ở service khi semantics là không có ID nào.

### Bài 12 — JOIN và FK

Muốn tìm Product theo `Category.code`. Nên dùng `JOIN p.category c` hay ghép trực tiếp tên cột `category_id` vào JPQL?

**Gợi ý:** đi qua association persistent `p.category`, sau đó lọc `c.code`.

### Bài 13 — Bulk update

Code gọi `executeUpdate()` đổi trạng thái 100 Product. Tại sao 100 managed Product đã nạp trước đó có thể vẫn giữ state cũ?

**Gợi ý:** bulk DML bypass cập nhật field per-managed-entity; cần chiến lược flush/refresh/clear phù hợp.

### Bài 14 — Query lock

Một câu `TypedQuery<Product>` dùng `setLockMode(PESSIMISTIC_WRITE)`. Điều gì cần được chuẩn bị?

**Gợi ý:** transaction đang hoạt động, cơ chế DB locking hỗ trợ, timeout/deadlock handling; không dùng lock mode như một cách phân trang hay chuyển scalar thành entity.

### Bài 15 — First-level cache

Một query JPQL SELECT trả Product#101 vốn đã managed và cũ trong context. Có thể khẳng định query tự refresh toàn bộ field từ database không?

**Gợi ý:** không. JPA duy trì identity managed instance; muốn reload phải xem `refresh()`, context và isolation.

### Bài 16 — Named query

Khác biệt giữa `createQuery("Product.findActive", Product.class)` và `createNamedQuery("Product.findActive", Product.class)` là gì?

**Gợi ý:** phương thức đầu cố diễn giải chuỗi như JPQL; phương thức sau tra cứu named query đã được khai báo.

## 43. Quy trình lựa chọn Query trong code hằng ngày

Khi viết một yêu cầu truy vấn mới, có thể làm theo thứ tự:

1. **Xác định kiểu kết quả:** entity, scalar, mảng nhiều cột hay DTO.
2. **Xác định entity và thuộc tính:** chỉ dùng JPA entity names/attribute paths trong JPQL.
3. **Chọn TypedQuery cho SELECT:** `Product.class`, `Long.class`, `ProductSummary.class` hoặc `Object[].class` phù hợp.
4. **Đặt điều kiện có parameter:** các giá trị request qua `setParameter()`, không nối vào query.
5. **Xử lý trường hợp rỗng/null:** empty IN, optional filter, không có kết quả.
6. **Chọn số lượng kết quả:** `getResultList()` hay `getSingleResult()` theo nghiệp vụ.
7. **Giới hạn tải:** pagination, DTO projection và fetch plan.
8. **Sắp xếp rõ:** dùng ORDER BY ổn định, whitelist dynamic sort.
9. **Xem transaction:** SELECT, bulk DML, locking và flush có yêu cầu khác nhau.
10. **Dùng công cụ phù hợp cho update:** managed entity + dirty checking khi sửa một entity; bulk Query khi phù hợp.
11. **Quan sát SQL và execution plan:** không chỉ nhìn chuỗi JPQL mà đánh giá SQL thực thi.
12. **Kiểm thử ngữ nghĩa dữ liệu:** gồm kết quả rỗng, trùng, concurrency, authorization và phân trang.

### Kết luận thiết kế

`Query` và `TypedQuery` không chỉ là hai tên khác nhau cho cùng một lời gọi. Khác biệt quan trọng là **kiểu kết quả được biểu đạt tường minh** và **mục đích sử dụng của query**. Với SELECT thông thường, `TypedQuery<T>` giúp code rõ ràng, an toàn kiểu hơn và dễ refactor. Với bulk UPDATE/DELETE, `Query.executeUpdate()` diễn đạt đúng thao tác và trả số lượng tác động.

## Kết luận

**Tạo Query và TypedQuery qua EntityManager** là thao tác nền tảng của JPQL. `em.createQuery(jpql)` trả `Query` không có result type generic cụ thể; `em.createQuery(jpql, ResultClass.class)` trả `TypedQuery<ResultClass>`, thích hợp cho SELECT entity, COUNT, scalar, DTO và nhiều kết quả có kiểu xác định. Ta gắn dữ liệu bằng `setParameter()`, thực thi SELECT qua `getResultList()` hoặc `getSingleResult()`, và thực thi bulk UPDATE/DELETE qua `executeUpdate()`.

Để dùng đúng, hãy luôn phân biệt **tên entity/attribute trong JPQL** với **tên bảng/cột trong SQL**, dùng parameters thay vì nối giá trị vào chuỗi query, khai báo result class khớp SELECT expression và xử lý rõ các tình huống rỗng, nhiều kết quả, list parameter hoặc pagination. Query trả entity còn tương tác với persistence context, flush mode và lifecycle; bulk DML lại có thể khiến managed state stale và cần transaction phù hợp.

Khi chọn đúng kiểu query, quản lý transaction/locking nhất quán và kiểm tra SQL thực tế, ứng dụng JPA có thể truy vấn dữ liệu quan hệ một cách rõ ràng, type-safe hơn và phù hợp với quy tắc nghiệp vụ mà không phải trộn logic đối tượng với cú pháp SQL đặc thù của từng DBMS.
