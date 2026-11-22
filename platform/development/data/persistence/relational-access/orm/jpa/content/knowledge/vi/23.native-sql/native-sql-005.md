# Ánh xạ nhiều phần kết quả bằng SqlResultSetMapping trong JPA Native SQL

Khi sử dụng JPQL hoặc Criteria API, JPA provider hiểu entity, thuộc tính, quan hệ và kiểu dữ liệu Java để tạo truy vấn. Tuy nhiên, nhiều hệ thống cần **Native SQL** vì báo cáo tổng hợp, CTE, window function, truy vấn tối ưu theo database hoặc phải tích hợp schema sẵn có. Lúc đó một hàng SQL đôi khi chứa **nhiều phần kết quả khác nhau**, không chỉ một entity hay một scalar đơn lẻ.

Ví dụ một câu SQL có thể trả:

~~~text
Mỗi hàng kết quả:
┌───────────────────────┬─────────────────────┬─────────────────┐
│ Dữ liệu Product       │ Dữ liệu Category    │ line_count      │
│ id, sku, price, ...   │ id, code, name      │ COUNT(...)      │
└───────────────────────┴─────────────────────┴─────────────────┘

Mong muốn ở Java:
Object[] row
    [0] = Product entity
    [1] = Category entity
    [2] = Long lineCount
~~~

Nếu dùng `EntityManager.createNativeQuery(sql)` mà không khai báo ánh xạ, kết quả mặc định thường là scalar hoặc `Object[]` chứa **các giá trị JDBC thô**. JPA không tự hiểu rằng một nhóm alias thuộc Product, nhóm khác thuộc Category và một cột tổng hợp phải chuyển thành Long.

**`@SqlResultSetMapping`** là cơ chế khai báo cách JPA chuyển một result set của Native SQL thành **một hoặc nhiều entity, DTO qua constructor, và scalar columns**, kể cả phối hợp chúng trong **cùng một hàng kết quả**.

Đây là nội dung chính của bài học: cấu trúc ánh xạ nhiều phần; sự khác nhau giữa `@EntityResult`, `@ConstructorResult` và `@ColumnResult`; cách dùng `@FieldResult` với alias; hình dạng `Object[]`; dữ liệu entity được quản lý so với DTO; xử lý JOIN, aggregate, khóa chính, quan hệ, kiểu dữ liệu, phân trang và những lỗi thường gặp.

## 1. Khi nào cần SqlResultSetMapping?

Giả sử hệ thống có bảng sản phẩm và danh mục. Một dashboard cần lấy:

1. **Product** đầy đủ để phục vụ một thao tác nghiệp vụ có entity.
2. **Category** tương ứng để hiển thị thông tin danh mục.
3. **Số dòng đơn hàng** tham chiếu tới Product.

Một Native SQL có thể JOIN dữ liệu và tính COUNT cùng lúc:

~~~sql
SELECT
    p.id          AS prod_id,
    p.sku         AS prod_sku,
    c.id          AS cat_id,
    c.name        AS cat_name,
    COUNT(ol.id)  AS line_count
FROM products p
JOIN categories c ON c.id = p.category_id
LEFT JOIN order_lines ol ON ol.product_id = p.id
GROUP BY p.id, p.sku, c.id, c.name;
~~~

Kết quả SQL chứa nhiều cột, nhưng **SQL không mang thông tin class Java một cách tự động**. Để JPA ánh xạ thành Product và Category hợp lệ, câu SELECT còn phải cung cấp **đủ các cột persistent của từng entity**, không chỉ bốn cột minh họa ở trên.

`@SqlResultSetMapping` giải quyết bước chuyển đổi giữa **cột/alias của result set** và **cấu trúc kết quả Java**:

| Nhu cầu | Công cụ ánh xạ |
| --- | --- |
| Một entity từ một hàng SQL | `@EntityResult` hoặc một số overload native query đơn giản |
| Hai entity trên một hàng SQL | Hai `@EntityResult` trong cùng mapping |
| Một DTO chỉ đọc | `@ConstructorResult` |
| Một scalar như COUNT, SUM, mã | `@ColumnResult` |
| Entity + scalar | `@EntityResult` và `@ColumnResult` |
| Entity + DTO + scalar | Kết hợp ba loại kết quả trong một `@SqlResultSetMapping` |
| Cùng kiểu entity xuất hiện hai vai trò | Hai `@EntityResult` với alias khác nhau |
| Tên cột SQL không trùng tên field | `@FieldResult` hoặc alias tương ứng |

**Không nên dùng SqlResultSetMapping chỉ vì muốn chọn hai thuộc tính**. Nếu truy vấn đơn giản và có thể biểu diễn bằng JPQL constructor expression, `TypedQuery<DTO>` thường gọn hơn, portable hơn và dễ bảo trì hơn.

## 2. Phân biệt một hàng SQL với nhiều result set

Tên “SqlResultSetMapping” đôi khi gây nhầm lẫn. Trong bài này, “nhiều phần kết quả” có nghĩa:

~~~text
Một JDBC ResultSet:
  Row 1 -> Product + Category + Long
  Row 2 -> Product + Category + Long
  Row 3 -> Product + Category + Long
~~~

**Không phải**:

~~~text
Stored procedure:
  ResultSet #1: Products
  ResultSet #2: Categories
  ResultSet #3: Summary
~~~

Trường hợp một stored procedure trả **nhiều JDBC result sets riêng biệt** cần xử lý thông qua API `StoredProcedureQuery`, `getResultList()`, `hasMoreResults()` và các quy tắc của stored procedure. SqlResultSetMapping vẫn có thể được dùng để định nghĩa kiểu hàng của một result set, nhưng **một mapping phối hợp nhiều phần không có nghĩa tự gộp ba result set thành một Object[]**.

Trong phần còn lại, mỗi Object[] tương ứng **một hàng SQL duy nhất** và chứa nhiều thành phần đã được mapping.

## 3. Ba thành phần chính của @SqlResultSetMapping

Một khai báo tiêu biểu:

~~~java
@SqlResultSetMapping(
    name = "SomeMapping",
    entities = {
        @EntityResult(...)
    },
    classes = {
        @ConstructorResult(...)
    },
    columns = {
        @ColumnResult(...)
    }
)
~~~

Các annotation nằm trong namespace `jakarta.persistence`.

| Thành phần | Dùng để làm gì? | Đầu ra Java |
| --- | --- | --- |
| `@EntityResult` | Ánh xạ một tập cột thành một entity class được JPA quản lý | Entity instance |
| `@FieldResult` | Bên trong EntityResult: gắn field/property Java với alias cột result set | Metadata ánh xạ field |
| `@ConstructorResult` | Ánh xạ nhiều cột thành lời gọi constructor | DTO/object được tạo |
| `@ColumnResult` | Định nghĩa một cột scalar và kiểu mong muốn | Giá trị đơn |
| `name` của mapping | Tên để tra cứu từ native query | Identifier của metadata |

`@ColumnResult` có thể xuất hiện trong:

1. `columns = {...}` trực tiếp của SqlResultSetMapping, nghĩa là scalar độc lập.
2. `columns = {...}` bên trong `@ConstructorResult`, nghĩa là **tham số constructor theo đúng thứ tự**.

Hai vị trí dùng cùng annotation nhưng có ý nghĩa khác nhau.

### Một mapping chứa nhiều phần

~~~text
SqlResultSetMapping "ProductCategoryCount"
    |
    +-- EntityResult(Product.class)
    |      +-- FieldResult("id", "prod_id")
    |      +-- FieldResult("sku", "prod_sku")
    |      +-- ...
    |
    +-- EntityResult(Category.class)
    |      +-- FieldResult("id", "cat_id")
    |      +-- FieldResult("code", "cat_code")
    |      +-- ...
    |
    +-- ColumnResult("line_count", Long.class)
    |
    v
Object[] mỗi hàng:
    Product, Category, Long
~~~

## 4. Vị trí khai báo và cách JPA tìm mapping

`@SqlResultSetMapping` là annotation trên **kiểu được quản lý và được persistence unit nhận diện**, thường đặt ở class `@Entity` để dễ theo dõi:

~~~java
@Entity
@SqlResultSetMapping(
    name = "ProductWithCount",
    entities = @EntityResult(entityClass = Product.class),
    columns = @ColumnResult(name = "line_count"))
public class Product {
    // Các field JPA...
}
~~~

Tên `"ProductWithCount"` có thể được tham chiếu khi tạo native query. Mapping **không bị giới hạn chỉ sử dụng cho entity nơi đặt annotation**: đó là metadata được đăng ký trong persistence unit.

### Quy ước đặt tên

Nên dùng tên có phạm vi/chức năng rõ:

~~~text
Product.withCategoryAndLineCount
Category.totalLineValue
Report.productAndPeriodMetrics
~~~

Các mapping cần có tên không xung đột trong phạm vi persistence unit. Đặt nhiều mapping cùng tên ở nhiều entity rồi hy vọng provider chọn theo context là thiết kế không an toàn.

### Có thể khai báo nhiều mapping

Thông qua annotation repeatable hoặc container annotation `@SqlResultSetMappings` phù hợp phiên bản:

~~~java
@SqlResultSetMappings({
    @SqlResultSetMapping(
        name = "Product.basic",
        entities = @EntityResult(entityClass = Product.class)
    ),
    @SqlResultSetMapping(
        name = "Product.idOnly",
        columns = @ColumnResult(name = "id", type = Long.class)
    )
})
@Entity
public class Product {
    // ...
}
~~~

**Lưu ý:** cách ánh xạ entity trong ví dụ `Product.basic` đòi hỏi SQL cung cấp đầy đủ các cột entity theo mapping mặc định. Tên `idOnly` chỉ là một scalar Long, không phải “entity Product chỉ có id”.

Ngoài annotation, JPA có thể định nghĩa result set mapping trong **ORM XML metadata** khi dự án muốn tách khai báo khỏi source code. Không cần tạo một entity giả chỉ vì không muốn đặt annotation trên class chính nếu dự án đã quản lý metadata XML đúng cách.

## 5. Mô hình dữ liệu xuyên suốt

Ta dùng ba bảng:

~~~text
categories
--------------------------------------------------
id (PK) | code (UNIQUE) | name

products
-------------------------------------------------------------
id (PK) | tenant_id | sku | price | status | version
category_id (FK -> categories.id)

order_lines
--------------------------------------------------
id (PK) | product_id (FK) | line_total
~~~

DDL PostgreSQL minh họa:

~~~sql
CREATE TABLE categories (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    category_id BIGINT NOT NULL,
    CONSTRAINT uq_product_tenant_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    line_total NUMERIC(18, 2) NOT NULL,
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX idx_order_lines_product
    ON order_lines(product_id);
~~~

Trong thực tế, OrderLine còn cần `order_id`, số lượng, giá tại thời điểm mua và trạng thái đơn hàng. Bảng rút gọn này chỉ dùng để giải thích **COUNT các dòng tham chiếu một Product** và **SUM các line_total đã lưu**, không phải mô hình doanh thu hoàn chỉnh.

### Những quy ước quan trọng

- `Product.id` là khóa chính; `(tenant_id, sku)` là unique business key.
- `Product.version` dùng optimistic locking; khi ánh xạ entity từ Native SQL, ta phải quan tâm cả cột version.
- `Product.category` là quan hệ many-to-one sở hữu FK `category_id`.
- `Category.code` là mã hiển thị; nếu nó có thể thay đổi, nên dùng ID để xác định identity.
- `order_lines.product_id` dùng để đếm số dòng. Không đồng nhất `COUNT(order_lines)` với số Order duy nhất nếu một Order có nhiều dòng.

## 6. Entity Category

~~~java
package com.example.shop;

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

    @Column(nullable = false, unique = true, length = 60)
    private String code;

    @Column(nullable = false, length = 160)
    private String name;

    protected Category() {
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

Entity Category có ba persistent fields: `id`, `code` và `name`. Nếu Native SQL chọn Category dưới dạng EntityResult, SQL phải cung cấp dữ liệu cần thiết để dựng Category hợp lệ theo mapping.

## 7. Entity Product và vị trí @SqlResultSetMapping

Sau đây là ví dụ **trọng tâm**. Ta khai báo mapping tại Product, nhưng mapping trả **cả Product, Category và Long**.

~~~java
package com.example.shop;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityResult;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.FieldResult;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.SqlResultSetMapping;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
@SqlResultSetMapping(
    name = "ProductCategoryLinesMapping",
    entities = {
        @EntityResult(
            entityClass = Product.class,
            fields = {
                @FieldResult(
                    name = "id", column = "prod_id"),
                @FieldResult(
                    name = "tenantId", column = "prod_tenant"),
                @FieldResult(
                    name = "sku", column = "prod_sku"),
                @FieldResult(
                    name = "price", column = "prod_price"),
                @FieldResult(
                    name = "status", column = "prod_status"),
                @FieldResult(
                    name = "version", column = "prod_version"),
                @FieldResult(
                    name = "category",
                    column = "prod_category_fk")
            }
        ),
        @EntityResult(
            entityClass = Category.class,
            fields = {
                @FieldResult(
                    name = "id", column = "cat_id"),
                @FieldResult(
                    name = "code", column = "cat_code"),
                @FieldResult(
                    name = "name", column = "cat_name")
            }
        )
    },
    columns = {
        @ColumnResult(name = "line_count", type = Long.class)
    }
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProductStatus status;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    private Category category;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Category getCategory() {
        return category;
    }
}
~~~

Enum đi kèm:

~~~java
package com.example.shop;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    INACTIVE
}
~~~

### Giải thích @EntityResult thứ nhất

~~~java
@EntityResult(
    entityClass = Product.class,
    fields = {
        @FieldResult(name = "id", column = "prod_id"),
        // ...
    }
)
~~~

Có nghĩa: lấy các cột result set tương ứng và ánh xạ vào các persistent fields của Product.

- `name="id"` là **tên field/property JPA của Product**.
- `column="prod_id"` là **nhãn cột (column label/alias) trong SQL result set**.
- Mọi field cần để dựng entity đúng phải có mặt.
- Foreign key của quan hệ `category` được lấy từ alias `prod_category_fk`.

### Giải thích @EntityResult thứ hai

~~~java
@EntityResult(
    entityClass = Category.class,
    fields = {
        @FieldResult(name = "id", column = "cat_id"),
        @FieldResult(name = "code", column = "cat_code"),
        @FieldResult(name = "name", column = "cat_name")
    }
)
~~~

JPA ánh xạ các cột có tiền tố `cat_` thành **một entity Category độc lập**, thay vì trả thẳng các scalar Category trong Object[].

### Giải thích ColumnResult

~~~java
@ColumnResult(name = "line_count", type = Long.class)
~~~

`line_count` là một cột tính toán `COUNT(...)`, không phải persistent property của Product hay Category. Ta giữ nó như một scalar độc lập, không thêm field `lineCount` vào entity chỉ để phục vụ một query.

## 8. Câu SQL phải chọn đủ cột và đặt alias tường minh

Native SQL đi cùng mapping:

~~~sql
SELECT
    p.id          AS prod_id,
    p.tenant_id   AS prod_tenant,
    p.sku         AS prod_sku,
    p.price       AS prod_price,
    p.status      AS prod_status,
    p.version     AS prod_version,
    p.category_id AS prod_category_fk,

    c.id          AS cat_id,
    c.code        AS cat_code,
    c.name        AS cat_name,

    COUNT(ol.id)  AS line_count
FROM products p
JOIN categories c
  ON c.id = p.category_id
LEFT JOIN order_lines ol
  ON ol.product_id = p.id
WHERE p.tenant_id = ?1
GROUP BY
    p.id,
    p.tenant_id,
    p.sku,
    p.price,
    p.status,
    p.version,
    p.category_id,
    c.id,
    c.code,
    c.name
ORDER BY p.id ASC;
~~~

Trong ví dụ, tất cả cột thuộc Product và Category được liệt kê trong `GROUP BY` để biểu diễn kết quả nhóm nhất quán trên nhiều DBMS. Một số hệ quản trị có thể tối ưu hoặc cho phép nhóm theo khóa chính nhờ phụ thuộc hàm; **không cần dựa vào ngoại lệ đó** khi muốn ví dụ rõ ràng.

### Tại sao dùng AS prod_id và AS cat_id?

Hai bảng đều có `id`. Nếu viết:

~~~sql
SELECT p.*, c.*, COUNT(ol.id) ...
~~~

result set có thể chứa nhiều column label trùng nhau như `id`, `name`. JDBC driver và provider có thể không phân biệt đúng “id của Product” và “id của Category”.

Alias tường minh làm ranh giới rõ:

~~~text
prod_id -> Product.id
cat_id  -> Category.id
~~~

**Quy tắc thực hành:** trong Native SQL có nhiều entity hoặc scalar trùng tên, không dùng `SELECT *`; khai báo đầy đủ cột và alias duy nhất cho từng cột cần ánh xạ.

### Tại sao COUNT(ol.id) thay vì COUNT(*)?

`LEFT JOIN order_lines` giữ Product ngay cả khi không có dòng đơn hàng. Khi không có OrderLine:

~~~text
Product = có dữ liệu
OrderLine = NULL
~~~

- `COUNT(ol.id)` trả **0** vì cột ol.id không có giá trị.
- `COUNT(*)` sẽ đếm **dòng LEFT JOIN** và có thể trả 1.

Vì vậy, tên biểu thức được đếm là một phần quan trọng của tính đúng đắn thống kê, không chỉ của mapping Java.

## 9. Thực thi query bằng EntityManager

Khai báo một chuỗi SQL tương ứng:

~~~java
String sql = """
    SELECT
        p.id AS prod_id,
        p.tenant_id AS prod_tenant,
        p.sku AS prod_sku,
        p.price AS prod_price,
        p.status AS prod_status,
        p.version AS prod_version,
        p.category_id AS prod_category_fk,
        c.id AS cat_id,
        c.code AS cat_code,
        c.name AS cat_name,
        COUNT(ol.id) AS line_count
    FROM products p
    JOIN categories c ON c.id = p.category_id
    LEFT JOIN order_lines ol ON ol.product_id = p.id
    WHERE p.tenant_id = ?1
    GROUP BY
        p.id, p.tenant_id, p.sku, p.price,
        p.status, p.version, p.category_id,
        c.id, c.code, c.name
    ORDER BY p.id ASC
    """;

Query query = em.createNativeQuery(
    sql,
    "ProductCategoryLinesMapping");

query.setParameter(1, tenantId);

List<?> rows = query.getResultList();

for (Object result : rows) {
    Object[] parts = (Object[]) result;

    Product product = (Product) parts[0];
    Category category = (Category) parts[1];
    Long lineCount = (Long) parts[2];

    System.out.printf(
        "%s (%s): %d lines%n",
        product.getSku(),
        category.getCode(),
        lineCount
    );
}
~~~

Cần import `jakarta.persistence.Query` và `java.util.List`. Java text block `"""` sử dụng Java 15+; dự án cũ có thể ghép chuỗi nhiều dòng.

### Giải thích overload

~~~java
em.createNativeQuery(sql, "ProductCategoryLinesMapping");
~~~

- Tham số thứ nhất: **Native SQL string**.
- Tham số thứ hai: **tên SqlResultSetMapping đã được đăng ký**.
- Kết quả trả về của API này là `Query`.
- `getResultList()` trả danh sách kết quả; mỗi hàng có nhiều phần nên là `Object[]` trong ví dụ.

### Cẩn trọng với positional parameters

Trong ví dụ dùng `?1` và `setParameter(1, tenantId)` theo cách phổ biến cho native query. Việc dùng **named parameter như `:tenantId` trong Native SQL** được nhiều provider hỗ trợ nhưng không nên mặc định portable như JPQL. Khi nhắm nhiều nhà cung cấp JPA/DBMS, hãy kiểm tra quy tắc parameter binding của native query trên stack đang hỗ trợ.

### Tại sao không dùng TypedQuery<Product>?

Một hàng trả **Product + Category + Long**, chứ không phải chỉ Product. Vì vậy:

~~~java
TypedQuery<Product> ...
~~~

không biểu diễn đầy đủ cấu trúc kết quả này. `Query` + `List<?>` + chuyển `Object[]` theo mapping là mô hình API phù hợp cho một native mapping nhiều phần. Nếu chỉ cần đọc DTO, phần sau sẽ đưa ra cách giảm nguy cơ ép kiểu theo index.

## 10. Kết quả nhiều phần được sắp thứ tự thế nào?

Khi khai báo nhiều thành phần kết quả, JPA trả một `Object[]` cho mỗi hàng. **Thứ tự các phần tử theo khai báo result mapping**, không được suy ra tùy tiện từ thứ tự các cột `SELECT`.

Trong mapping trên:

~~~java
entities = {
    @EntityResult(entityClass = Product.class, ...),
    @EntityResult(entityClass = Category.class, ...)
},
columns = {
    @ColumnResult(name = "line_count", type = Long.class)
}
~~~

Hình dạng cần xử lý:

| Index | Thành phần | Kiểu Java |
| --- | --- | --- |
| `parts[0]` | Product từ EntityResult thứ nhất | `Product` |
| `parts[1]` | Category từ EntityResult thứ hai | `Category` |
| `parts[2]` | line_count | `Long` |

Nếu đổi thứ tự các `@EntityResult` hoặc thêm một `@ConstructorResult`, phần xử lý `Object[]` cần được xem lại. Không nên viết code phụ thuộc “cột đầu tiên trong SQL là phần tử đầu tiên trong Object[]”, bởi một entity đã sử dụng nhiều cột SQL.

### Một lớp adapter để bớt cast rải rác

~~~java
public record ProductCategoryLineView(
        Product product,
        Category category,
        long lineCount) {
}
~~~

Chuyển đổi tại repository:

~~~java
List<ProductCategoryLineView> views =
    new ArrayList<>();

for (Object raw : query.getResultList()) {
    Object[] row = (Object[]) raw;
    views.add(new ProductCategoryLineView(
        (Product) row[0],
        (Category) row[1],
        ((Number) row[2]).longValue()
    ));
}
~~~

`((Number) row[2]).longValue()` là cách chuyển đổi linh hoạt hơn khi một provider/driver trả loại Number cụ thể khác với dự đoán. Trong mapping đã khai `type=Long.class` thì kỳ vọng Long, nhưng adapter vẫn nên được giữ ở **một điểm chuyển đổi có kiểm soát**, không phân tán các phép cast tại controller, service và UI.

## 11. EntityResult khác ConstructorResult ở lifecycle

Đây là khác biệt quan trọng nhất về mặt JPA.

### EntityResult

~~~java
@EntityResult(entityClass = Product.class, ...)
~~~

Khi SQL result được ánh xạ thành entity, JPA đưa các instance có identity phù hợp vào **persistence context** (trong ngữ cảnh truy vấn đang được thực hiện). Chúng có thể là các managed entities; nếu một Product#101 đã managed trước đó, provider phải duy trì nguyên tắc identity map trong cùng persistence context.

Với entity được trả:

~~~java
Product product = (Product) row[0];
boolean managed = em.contains(product);
~~~

Trong bối cảnh EntityManager còn mở và truy vấn trả entity managed, `managed` là true. Nhưng nếu context đã bị clear/đóng, entity có thể trở thành detached. Một lần nạp native query không làm entity bất tử ngoài persistence context.

### ConstructorResult

~~~java
@ConstructorResult(
    targetClass = CategorySalesDto.class,
    columns = { ... }
)
~~~

Đây là cách tạo **object qua constructor** từ các scalar columns. Nếu target là một DTO class thông thường, DTO **không phải entity managed**. Thay đổi một field DTO không kích hoạt dirty checking để UPDATE database.

### ColumnResult

~~~java
@ColumnResult(name = "line_count", type = Long.class)
~~~

Đây là **giá trị scalar**. Một Long không có lifecycle entity, không có identity map và không có quan hệ lazy loading.

| Loại kết quả | Managed trong persistence context? | Dirty checking khi sửa? |
| --- | --- | --- |
| EntityResult(Product) | Có, khi đang thuộc context và được load như entity | Có, theo các quy tắc managed entity |
| ConstructorResult(DTO) | Không, nếu là DTO thuần | Không |
| ColumnResult(Long) | Không | Không |
| Object[] chứa cả ba | Mảng không managed; thành phần entity bên trong có thể managed | Chỉ áp dụng cho các entity managed |

Không nên đặt class `@Entity` làm target của ConstructorResult trừ khi đã hiểu kỹ trạng thái new/detached khi constructor tạo đối tượng có hoặc không có primary key. Với truy vấn chỉ đọc, **DTO thuần** là mục tiêu rõ ràng và ít gây nhầm lẫn hơn.

## 12. Một entity đã managed được tải lại qua Native SQL

Giả sử:

~~~java
Product existing = em.find(Product.class, 101L);

// Transaction khác có thể đã thay price và commit.

Query query = em.createNativeQuery(
    sql,
    "ProductCategoryLinesMapping");
query.setParameter(1, tenantId);

List<?> rows = query.getResultList();
~~~

Nếu một hàng SQL đại diện Product#101, entity được trả trong context phải tuân thủ identity map: provider không tạo hai managed instances độc lập cùng entity identity trong cùng context.

Nhưng **không được giả định native query tự refresh mọi field của entity đã managed**:

- Context có thể giữ state đã nạp trước đó.
- SQL SELECT diễn ra tại snapshot/isolation của transaction.
- Entity có thể đã bị sửa pending trong RAM.
- Provider có thể quyết định tương tác giữa result hydration và state managed theo quy tắc persistence.

Nếu mục tiêu là “lấy dữ liệu mới nhất của Product#101”, cần xem `em.refresh(product)`, transaction isolation và cache strategy. `@SqlResultSetMapping` mô tả cấu trúc result set, **không phải lệnh refresh hoặc thay đổi isolation**.

## 13. Tại sao EntityResult phải có đủ cột?

Trong ví dụ Product, các persistent field gồm:

~~~text
id
tenantId
sku
price
status
version
category
~~~

Với EntityResult, SQL phải cung cấp dữ liệu cần thiết cho tất cả field tương ứng, bao gồm khóa và cột FK của quan hệ. Không nên viết:

~~~sql
SELECT
    p.id AS prod_id,
    p.sku AS prod_sku
FROM products p;
~~~

rồi áp dụng một EntityResult đòi hỏi cả `price`, `status`, `version` và `category`. Khi thiếu dữ liệu cần thiết, kết quả không phải một “partial managed entity” được JPA chuẩn hứa hẹn an toàn; nó có thể thất bại hoặc cho hành vi không xác định.

### Sai lầm: coi EntityResult như projection DTO

Nếu dashboard chỉ cần:

~~~text
Product ID, SKU, Category code, lineCount
~~~

thì không cần nạp Product/Category entity đầy đủ. Có thể dùng:

- Một `@ConstructorResult` với DTO chứa bốn giá trị.
- Nhiều `@ColumnResult` rồi chuyển Object[].
- JPQL constructor projection nếu không cần SQL đặc thù.

**Đừng dùng entity một phần để tiết kiệm cột.** Thay đổi kiểu kết quả sang DTO khi nhu cầu thật là chỉ đọc một projection.

## 14. Khóa chính không được thiếu hoặc mơ hồ

EntityResult cần xác định được entity identity. Với:

~~~java
@Id
private Long id;
~~~

SQL phải chọn đúng ID và mapping:

~~~sql
p.id AS prod_id
~~~

~~~java
@FieldResult(name = "id", column = "prod_id")
~~~

Nếu alias `prod_id` không tồn tại, sai kiểu, hoặc bị JOIN gán nhầm Category ID, provider có thể ném exception hoặc nhận diện sai entity.

### Khác alias nhưng cùng giá trị không có nghĩa cùng entity

Product#10 và Category#10 có cùng giá trị ID số 10, nhưng chúng là **hai entity types khác nhau**:

~~~text
(Product.class, 10)
(Category.class, 10)
~~~

Identity của JPA gồm loại entity và primary key phù hợp, không chỉ một số Long trần. Vì thế trong Object[] có thể đồng thời chứa Product#10 và Category#10 mà không có xung đột identity.

## 15. Ánh xạ quan hệ @ManyToOne trong EntityResult

Product có:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "category_id", nullable = false)
private Category category;
~~~

Foreign key của quan hệ là `products.category_id`. Trong câu SQL, ta đặt alias:

~~~sql
p.category_id AS prod_category_fk
~~~

Và trong EntityResult:

~~~java
@FieldResult(
    name = "category",
    column = "prod_category_fk")
~~~

Ý nghĩa: cột FK trong result set được dùng để ánh xạ association Product.category theo metadata của quan hệ.

### Vì sao không dùng cat_id để thay FK của Product?

Trong INNER JOIN đúng, `p.category_id` và `c.id` thường bằng nhau. Nhưng hai cột có **vai trò khác nhau**:

- `prod_category_fk` là dữ liệu khóa ngoại thuộc Product.
- `cat_id` là primary key của Category entity được trả độc lập.

Đặt alias riêng cho hai vai trò làm truy vấn rõ và tránh phụ thuộc vào việc provider suy luận cột trùng tên.

### Quan hệ không nhất thiết được eager load

Ngay cả khi SQL trả thêm Category dưới dạng EntityResult, không nên giả định mọi đường điều hướng của Product đều được fetch theo một quy tắc khác mapping và provider. Việc Product.category có cùng managed Category instance trong context, được initialized ngay hoặc vẫn tuân theo fetch policy, phụ thuộc vào cách provider thực hiện hydration và identity resolution.

Nếu mục tiêu chỉ hiển thị categoryCode trong báo cáo, DTO có thể đơn giản và ít bất ngờ hơn việc kết hợp hai managed entity.

## 16. Hai entity cùng loại trong một hàng SQL

Một trường hợp khác là tự JOIN bảng entity, ví dụ nhân viên và người quản lý đều là `Employee`:

~~~sql
SELECT
    e.id AS employee_id,
    e.full_name AS employee_name,
    m.id AS manager_id,
    m.full_name AS manager_name
FROM employees e
LEFT JOIN employees m ON m.id = e.manager_id;
~~~

Ta có thể khai báo **hai EntityResult cùng `entityClass = Employee.class`** nhưng dùng tập alias khác nhau:

~~~java
@SqlResultSetMapping(
    name = "EmployeeAndManager",
    entities = {
        @EntityResult(
            entityClass = Employee.class,
            fields = {
                @FieldResult(name = "id",
                             column = "employee_id"),
                @FieldResult(name = "fullName",
                             column = "employee_name")
                // Thêm mọi persistent field/FK khác của Employee.
            }
        ),
        @EntityResult(
            entityClass = Employee.class,
            fields = {
                @FieldResult(name = "id",
                             column = "manager_id"),
                @FieldResult(name = "fullName",
                             column = "manager_name")
                // Thêm mọi persistent field/FK khác của Employee.
            }
        )
    }
)
~~~

Đây là **sơ đồ ánh xạ rút gọn**: nếu Employee thực tế còn nhiều persistent fields như `manager`, `version`, `department`, cần chọn đủ cột và khai báo tương ứng. Không coi đoạn minh họa hai field là mapping hoàn chỉnh cho một entity nhiều field.

### Nullable manager

Với LEFT JOIN, manager có thể NULL. Cần kiểm tra hành vi provider khi mọi cột identity của EntityResult manager NULL và xử lý thành phần manager có thể null theo semantics thực tế. Nếu yêu cầu luôn trả một DTO ổn định cho cấu trúc nullable, constructor projection với nullable managerName có thể dễ quản lý hơn.

### Không tạo hai managed Employee độc lập cùng identity

Nếu employee và manager trùng ID trong một tình huống được mô hình cho phép, JPA vẫn phải tôn trọng identity map. Hai vị trí trong Object[] không có nghĩa provider được tạo hai managed Employee instances khác nhau cùng ID.

## 17. Ánh xạ DTO bằng @ConstructorResult

Đối với báo cáo chỉ đọc, ánh xạ sang DTO thường phù hợp hơn nạp entity đầy đủ.

Giả sử ta muốn một DTO cho:

~~~text
Category code | Tổng line_total của sản phẩm trong category
~~~

DTO Java:

~~~java
package com.example.shop.dto;

import java.math.BigDecimal;

public class CategoryLineValueDto {

    private final String categoryCode;
    private final BigDecimal totalLineValue;

    public CategoryLineValueDto(
            String categoryCode,
            BigDecimal totalLineValue) {
        this.categoryCode = categoryCode;
        this.totalLineValue = totalLineValue;
    }

    public String getCategoryCode() {
        return categoryCode;
    }

    public BigDecimal getTotalLineValue() {
        return totalLineValue;
    }
}
~~~

Khai báo mapping ở một entity được persistence unit quét:

~~~java
@SqlResultSetMapping(
    name = "CategoryLineValueMapping",
    classes = {
        @ConstructorResult(
            targetClass =
                com.example.shop.dto.CategoryLineValueDto.class,
            columns = {
                @ColumnResult(
                    name = "cat_code",
                    type = String.class),
                @ColumnResult(
                    name = "total_line_value",
                    type = BigDecimal.class)
            }
        )
    }
)
~~~

Các cột `cat_code` và `total_line_value` được truyền **theo đúng thứ tự khai báo** vào constructor:

~~~java
new CategoryLineValueDto(
    (String) catCode,
    (BigDecimal) totalLineValue);
~~~

**Điều kiện:** class phải có constructor phù hợp về thứ tự, số lượng và kiểu dữ liệu. Provider không tự sắp xếp tham số constructor theo tên field Java của DTO.

### Native SQL tương ứng

~~~sql
SELECT
    c.code AS cat_code,
    COALESCE(
        SUM(ol.line_total),
        CAST(0 AS NUMERIC(18, 2))
    ) AS total_line_value
FROM categories c
JOIN products p ON p.category_id = c.id
LEFT JOIN order_lines ol ON ol.product_id = p.id
WHERE p.tenant_id = ?1
GROUP BY c.id, c.code
ORDER BY c.code;
~~~

`COALESCE(SUM(...), 0)` giúp các Category có Product nhưng không có OrderLine trả 0 theo chính sách báo cáo này. **Category không có Product trong tenant** không xuất hiện vì INNER JOIN products; muốn giữ Category đó cần điều chỉnh JOIN/tenant semantics cẩn thận.

Tổng này là **giá trị các dòng OrderLine đang được lưu**, không tự được coi là “doanh thu đã thanh toán” nếu chưa xét trạng thái thanh toán, hoàn tiền, thuế và điều chỉnh nghiệp vụ.

### Thực thi

~~~java
Query query = em.createNativeQuery(
    sql,
    "CategoryLineValueMapping");
query.setParameter(1, tenantId);

List<?> results = query.getResultList();

for (Object raw : results) {
    CategoryLineValueDto dto = (CategoryLineValueDto) raw;
    System.out.println(
        dto.getCategoryCode() + " = "
        + dto.getTotalLineValue());
}
~~~

Với **chỉ một ConstructorResult** và không có phần mapping độc lập khác, mỗi hàng thường được trả trực tiếp dưới dạng DTO. Khi bổ sung một scalar `@ColumnResult` ngoài ConstructorResult, hình dạng trở thành Object[] chứa nhiều phần.

## 18. ConstructorResult + ColumnResult trên cùng một hàng

Đây là ví dụ **hai phần khác loại**:

~~~text
Phần 1: CategoryLineValueDto(categoryCode, totalLineValue)
Phần 2: Long lineCount
~~~

Khai báo:

~~~java
@SqlResultSetMapping(
    name = "CategoryValueAndCountMapping",
    classes = {
        @ConstructorResult(
            targetClass =
                com.example.shop.dto.CategoryLineValueDto.class,
            columns = {
                @ColumnResult(
                    name = "cat_code",
                    type = String.class),
                @ColumnResult(
                    name = "total_line_value",
                    type = BigDecimal.class)
            }
        )
    },
    columns = {
        @ColumnResult(
            name = "line_count",
            type = Long.class)
    }
)
~~~

Native SQL:

~~~sql
SELECT
    c.code AS cat_code,
    COALESCE(
        SUM(ol.line_total),
        CAST(0 AS NUMERIC(18,2))
    ) AS total_line_value,
    COUNT(ol.id) AS line_count
FROM categories c
JOIN products p ON p.category_id = c.id
LEFT JOIN order_lines ol ON ol.product_id = p.id
WHERE p.tenant_id = ?1
GROUP BY c.id, c.code;
~~~

Java:

~~~java
Query query = em.createNativeQuery(
    sql, "CategoryValueAndCountMapping");
query.setParameter(1, tenantId);

for (Object raw : query.getResultList()) {
    Object[] row = (Object[]) raw;
    CategoryLineValueDto dto =
        (CategoryLineValueDto) row[0];
    Long numberOfLines = (Long) row[1];
}
~~~

**Điểm tinh tế:** hai `@ColumnResult` ở **bên trong ConstructorResult** không trở thành hai phần tử Object[] độc lập. Chúng được dùng làm **hai tham số để dựng một DTO**, rồi DTO được đặt ở một phần tử của Object[]. Chỉ `@ColumnResult(name="line_count")` ở mức SqlResultSetMapping mới là một scalar kết quả riêng.

## 19. Hai hoặc nhiều ConstructorResult trong một mapping

Nếu một hàng SQL có hai nhóm dữ liệu độc lập, có thể định nghĩa hai constructor projections:

~~~java
@SqlResultSetMapping(
    name = "ProductAndCategoryCards",
    classes = {
        @ConstructorResult(
            targetClass = ProductCardDto.class,
            columns = {
                @ColumnResult(name = "prod_id", type = Long.class),
                @ColumnResult(name = "prod_sku", type = String.class)
            }
        ),
        @ConstructorResult(
            targetClass = CategoryCardDto.class,
            columns = {
                @ColumnResult(name = "cat_id", type = Long.class),
                @ColumnResult(name = "cat_name", type = String.class)
            }
        )
    }
)
~~~

Với:

~~~java
public record ProductCardDto(Long id, String sku) {
}

public record CategoryCardDto(Long id, String name) {
}
~~~

Ví dụ Java 17+ dùng record; nếu provider/phiên bản không hỗ trợ constructor record ổn định trong trường hợp đang dùng, dùng POJO có constructor công khai tương ứng. Các annotation trên phải được đặt ở entity/metadata phù hợp, không đặt tùy tiện vào DTO rồi giả định JPA sẽ tự quét DTO.

Một hàng có thể trở thành:

~~~text
Object[]:
  [0] ProductCardDto
  [1] CategoryCardDto
~~~

Đây là một **projection thuần DTO**, không sinh hai managed entity. Trong nhiều API chỉ đọc, cách này an toàn về lifecycle hơn so với trả Product/Category managed.

### Có nhất thiết cần hai DTO?

Không. Nếu service luôn sử dụng hai phần cùng nhau, **một DTO tổng hợp**:

~~~java
public record ProductCategoryCard(
        Long productId,
        String sku,
        Long categoryId,
        String categoryName) {
}
~~~

có thể dễ đọc hơn `Object[]` chứa hai DTO. Chọn nhiều ConstructorResult khi có lý do rõ về tái sử dụng cấu trúc, không để tăng số lớp vô ích.

## 20. EntityResult + ConstructorResult + ColumnResult

SqlResultSetMapping cho phép khai báo cả ba nhóm:

~~~java
@SqlResultSetMapping(
    name = "MixedReportMapping",
    entities = {
        @EntityResult(
            entityClass = Product.class,
            fields = { /* Các FieldResult đầy đủ */ })
    },
    classes = {
        @ConstructorResult(
            targetClass = CategoryCardDto.class,
            columns = {
                @ColumnResult(name = "cat_id", type = Long.class),
                @ColumnResult(name = "cat_name", type = String.class)
            })
    },
    columns = {
        @ColumnResult(name = "line_count", type = Long.class)
    }
)
~~~

Đây là **sơ đồ cú pháp**, không phải mapping có thể chạy độc lập: phải thay chú thích `/* Các FieldResult đầy đủ */` bằng các FieldResult thực tế của Product và SELECT đủ các cột tương ứng.

Ý tưởng đối tượng:

~~~text
Mỗi hàng:
  Product entity
  CategoryCardDto DTO
  Long lineCount
~~~

Khi kết hợp nhiều loại kết quả, hãy xác nhận thứ tự phần tử theo định nghĩa mapping, ghi rõ schema ở adapter/repository và tránh truyền Object[] tùy ý lên business layer.

**Quan trọng:** việc một hàng có nhiều thành phần không biến toàn bộ hàng thành một aggregate root managed. Chỉ các entity parts có lifecycle entity; DTO/scalar chỉ là dữ liệu kết quả.

## 21. Chọn EntityResult hay ConstructorResult?

| Câu hỏi | Nghiêng về EntityResult | Nghiêng về ConstructorResult |
| --- | --- | --- |
| Có cần sửa entity sau query trong transaction? | Có | Không |
| Có cần identity map của JPA? | Có | Không |
| Chỉ cần 2–5 cột để hiển thị? | Thường quá nặng | Phù hợp |
| SQL trả đủ tất cả cột của entity? | Bắt buộc chú ý | Không cần |
| Dữ liệu đến từ nhiều bảng để lập report? | Có thể, nhưng phức tạp | Thường rõ hơn |
| Có field tính toán như COUNT/SUM? | Dùng thêm ColumnResult | Có thể nhét vào DTO |
| Muốn tránh dirty checking ngoài ý định? | Không phù hợp nếu entity managed | Phù hợp |
| Kết quả có thể thay đổi độc lập với state entity? | Cần cẩn trọng stale state | DTO thể hiện snapshot kết quả |

### Một nguyên tắc kiến trúc

Với **query phục vụ hiển thị/báo cáo**, ưu tiên projection có nghĩa rõ ràng, thường là DTO. Với **query phục vụ thao tác nghiệp vụ đang dùng entity**, EntityResult có thể phù hợp, nhưng phải chọn đủ cột và quản lý persistence context đúng.

Đừng chọn EntityResult chỉ vì tên Java type dễ ép kiểu, rồi cố “SELECT một vài field” thành managed entity nửa vời.

## 22. ColumnResult và chuyển đổi kiểu scalar

Database và JDBC driver có thể trả kiểu dữ liệu thô khác với kiểu domain mong muốn:

| Biểu thức SQL | Giá trị JDBC có thể thấy | Kiểu Java mong muốn |
| --- | --- | --- |
| `COUNT(*)` | Long, BigInteger hoặc kiểu Number khác tùy provider/dialect | Long |
| `SUM(NUMERIC)` | BigDecimal | BigDecimal |
| `id BIGINT` | Long hoặc Number phù hợp | Long |
| `VARCHAR` | String | String |
| `DATE` | Date/LocalDate tùy stack | LocalDate theo mapping phù hợp |
| `BOOLEAN` hoặc CASE | Boolean/Number/String tùy DB | Boolean/Enum theo yêu cầu |

Khai báo:

~~~java
@ColumnResult(name = "line_count", type = Long.class)
~~~

làm rõ **kiểu yêu cầu**. Tuy nhiên, chuyển đổi thực tế vẫn cần phù hợp dữ liệu JDBC, provider và DBMS; không phải mọi kiểu custom đều chuyển được chỉ nhờ đặt `type`.

### Không dùng Integer cho COUNT chỉ vì bảng nhỏ

`COUNT` có thể vượt phạm vi `int`. `Long` là lựa chọn quen thuộc cho các đếm lớn.

### NUMERIC và BigDecimal

~~~java
@ColumnResult(
    name = "total_line_value",
    type = BigDecimal.class)
~~~

phù hợp với tổng giá trị tiền từ cột `NUMERIC(18,2)`. Không ép sang `double` nếu cần bảo toàn độ chính xác thập phân.

### Xử lý giá trị NULL

Với:

~~~sql
SUM(ol.line_total) AS total_line_value
~~~

nếu nhóm không có giá trị, SUM có thể NULL. Constructor nên nhận `BigDecimal` nullable, không dùng primitive. Nếu domain muốn hiển thị số 0, dùng `COALESCE` trong SQL hoặc xử lý NULL ở DTO/service bằng một quy ước rõ ràng.

## 23. Tên cột trong ColumnResult là nhãn result set

Giả sử:

~~~sql
SELECT COUNT(*) AS product_count
FROM products;
~~~

Mapping:

~~~java
@SqlResultSetMapping(
    name = "ProductCount",
    columns = {
        @ColumnResult(name = "product_count", type = Long.class)
    }
)
~~~

`name="product_count"` trỏ đến **alias của SELECT**, không nhất thiết là tên cột có thật trong bảng.

Nếu SQL đổi thành:

~~~sql
SELECT COUNT(*) AS total_products
FROM products;
~~~

nhưng mapping vẫn trỏ tới `product_count`, query có thể báo không tìm thấy column label hoặc lỗi chuyển đổi.

### Aliases có thể bị DBMS chuyển chữ hoa/thường

Ví dụ PostgreSQL thường chuẩn hóa identifier không quote về chữ thường. Cách dùng alias thường:

~~~sql
AS product_count
~~~

và:

~~~java
@ColumnResult(name = "product_count")
~~~

giúp tránh nhầm. Nếu dùng alias có quote và chữ hoa:

~~~sql
AS "productCount"
~~~

thì mapping phải nhất quán:

~~~java
@ColumnResult(name = "productCount")
~~~

Một số provider/driver có xử lý case khác nhau; để portable hơn, ưu tiên alias đơn giản, chữ thường, không có khoảng trắng hay ký tự đặc biệt.

## 24. Vì sao không dùng SELECT * khi ánh xạ nhiều entity?

Ví dụ:

~~~sql
SELECT p.*, c.*, ol.*
FROM products p
JOIN categories c ON ...
LEFT JOIN order_lines ol ON ...;
~~~

Câu SQL này có nhiều vấn đề:

- `id` lặp lại ở cả ba bảng.
- `name` hoặc `status` có thể trùng.
- Số lượng cột thay đổi khi schema migration thêm cột.
- Thứ tự cột có thể không được duy trì theo giả định ứng dụng.
- Một Product xuất hiện lặp lại theo số OrderLine do JOIN.
- JPA không biết bảng/cột nào tạo entity nào nếu mapping không phân biệt được alias.

Với SqlResultSetMapping nhiều phần, nên viết:

~~~sql
SELECT
    p.id AS prod_id,
    p.sku AS prod_sku,
    -- Các cột Product còn lại...
    c.id AS cat_id,
    c.code AS cat_code,
    -- Các cột Category còn lại...
    COUNT(ol.id) AS line_count
...
~~~

Các dòng comment chỉ mô tả cấu trúc; query thực tế phải **chọn đủ toàn bộ cột cần thiết**. Đây là chi phí về tính tường minh mà Native SQL + nhiều EntityResult thường phải chấp nhận.

## 25. @Version có vai trò gì khi nhận EntityResult?

Product có:

~~~java
@Version
private Long version;
~~~

Để JPA optimistic locking hoạt động đúng, state version của entity phải được quản lý nhất quán. Với native entity result, cần bao gồm:

~~~sql
p.version AS prod_version
~~~

và:

~~~java
@FieldResult(
    name = "version",
    column = "prod_version")
~~~

### Có version không có nghĩa query tự khóa

Native SELECT ở trên chỉ đọc Product và COUNT; nó không tự áp dụng `PESSIMISTIC_WRITE`, không tự nâng isolation. Nếu hai transaction cùng sửa Product, optimistic version check thường phát huy khi flush/commit update managed entity.

### Bulk/native UPDATE từ bên ngoài có thể phá cơ chế version

Ví dụ:

~~~sql
UPDATE products
SET price = 999000
WHERE id = 101;
~~~

nếu không cập nhật/check version theo giao thức phù hợp, một đường ghi native có thể không được nhận diện bởi cơ chế optimistic locking của JPA như mong đợi.

**SqlResultSetMapping chỉ ánh xạ SELECT result set**. Nó không tự bổ sung version check vào mọi SQL UPDATE trong hệ thống.

## 26. @EmbeddedId và khóa tổng hợp

Nếu entity có khóa phức hợp:

~~~java
@EmbeddedId
private ProductKey id;
~~~

và:

~~~java
@Embeddable
public class ProductKey {
    private Long tenantId;
    private String sku;
}
~~~

thì ánh xạ EntityResult phải xác định **đủ các cột của embedded key**. Với những trường hợp ánh xạ nested attribute được provider/phiên bản JPA hỗ trợ, `@FieldResult.name` có thể biểu diễn đường dẫn như:

~~~java
@FieldResult(
    name = "id.tenantId",
    column = "key_tenant_id"),
@FieldResult(
    name = "id.sku",
    column = "key_sku")
~~~

Những ví dụ này minh họa cách đi theo thuộc tính embedded. Khi dùng `@IdClass`, nhiều `@Id` fields hoặc FK tổng hợp, cần ánh xạ **từng field và từng join column** theo đúng metadata cụ thể.

### Vì sao thiếu một cột composite key nguy hiểm?

Nếu identity thật là:

~~~text
(tenantId=10, sku=BK-01)
~~~

mà SQL chỉ chọn `sku`, ứng dụng không thể phân biệt Product của tenant 10 với Product của tenant 20 cùng SKU. Đây không chỉ là lỗi ép kiểu, mà là lỗi xác định entity identity.

### Kiểu dữ liệu của embedded key

`@Embeddable` dùng làm khóa nên có `equals()/hashCode()` đúng theo các trường identity. SqlResultSetMapping không sửa được một chiến lược equals/hashCode sai, và cũng không thay thế yêu cầu composite UNIQUE/PK tại database.

## 27. Kế thừa entity và discriminatorColumn

Nếu Product tham gia một hierarchy có inheritance mapping:

~~~java
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "product_type")
public class Product {
    // ...
}
~~~

thì Native SQL ánh xạ EntityResult có thể phải cung cấp **discriminator column** để provider xác định subtype.

`@EntityResult` có thuộc tính:

~~~java
@EntityResult(
    entityClass = Product.class,
    discriminatorColumn = "prod_type",
    fields = { /* Mapping đầy đủ các cột cần thiết */ }
)
~~~

và SQL:

~~~sql
p.product_type AS prod_type
~~~

Đây là sơ đồ minh họa; mapping inheritance thực tế còn phụ thuộc SINGLE_TABLE/JOINED/TABLE_PER_CLASS, các field riêng subtype và SQL do provider yêu cầu. Không bê nguyên EntityResult đơn giản vào một hierarchy phức tạp rồi kỳ vọng provider tự tìm mọi cột.

### Không tự sinh subtype từ scalar DTO

Nếu query chỉ cần hiển thị loại sản phẩm, một `ColumnResult(name="prod_type")` hoặc DTO field có thể phù hợp hơn tạo cả hierarchy managed. Lựa chọn này phụ thuộc việc có thực sự cần lifecycle entity hay không.

## 28. ConstructorResult với enum hoặc dữ liệu phi chuẩn

Giả sử SQL trả:

~~~sql
SELECT p.status AS prod_status
FROM products p;
~~~

Trong entity, `Product.status` là `ProductStatus` qua `@Enumerated(EnumType.STRING)`. Nhưng trong **ConstructorResult scalar**, `prod_status` có thể được JDBC trả như String từ VARCHAR.

Nếu DTO constructor muốn nhận enum:

~~~java
public ProductStatusDto(ProductStatus status) {
    // ...
}
~~~

không được mặc định `@ColumnResult(name="prod_status", type=ProductStatus.class)` sẽ được mọi provider tự chuyển String thành enum giống `@Enumerated` của entity.

Cách portable hơn về ý nghĩa là:

~~~java
public class ProductStatusDto {
    private final ProductStatus status;

    public ProductStatusDto(String status) {
        this.status = ProductStatus.valueOf(status);
    }
}
~~~

với:

~~~java
@ColumnResult(
    name = "prod_status",
    type = String.class)
~~~

Cần kiểm soát giá trị lỗi khi database chứa chuỗi không hợp lệ, và chỉ áp dụng nếu schema thực sự lưu enum name dưới dạng VARCHAR. Việc parse String có thể nằm trong adapter sau query thay vì constructor nếu muốn xử lý lỗi một cách tường minh.

### Các kiểu ngày giờ

`DATE`, `TIMESTAMP` và `TIMESTAMP WITH TIME ZONE` có thể được driver ánh xạ khác nhau. Nếu DTO cần `Instant` hoặc `LocalDate`, nên kiểm tra cách `ColumnResult.type` được provider/driver hỗ trợ; nếu không ổn định, dùng loại JDBC tương thích rồi chuyển ở adapter với timezone policy rõ.

## 29. Không nhầm SqlResultSetMapping với @Converter

`AttributeConverter<X,Y>` dùng để chuyển đổi **persistent basic attribute** của entity giữa kiểu domain và kiểu DB. Nó không phải một ánh xạ tổng quát “cột 1 vào Product, cột 2 vào Category, cột 3 thành DTO”.

So sánh:

| Tính năng | Phạm vi |
| --- | --- |
| `@Convert`/`AttributeConverter` | Chuyển kiểu một persistent attribute |
| `@ColumnResult(type=...)` | Chỉ định kiểu scalar trong native query result mapping |
| `@FieldResult` | Ánh xạ alias SQL với field/property của entity |
| `@EntityResult` | Dựng entity từ nhiều cột theo mapping |
| `@ConstructorResult` | Dựng DTO/object bằng constructor |
| `@SqlResultSetMapping` | Gom các phần kết quả trên thành một result mapping có tên |

Một converter có thể tham gia việc xử lý một thuộc tính entity theo quy tắc mapping, nhưng không thay thế SQL aliases hay mapping nhiều entity.

## 30. NamedNativeQuery kết hợp SqlResultSetMapping

Nếu SQL được sử dụng cố định và lặp lại nhiều nơi, có thể khai báo `@NamedNativeQuery` với `resultSetMapping`:

~~~java
@NamedNativeQuery(
    name = "Category.countProducts",
    query = """
        SELECT
            c.code AS cat_code,
            COUNT(p.id) AS product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id
        GROUP BY c.id, c.code
        ORDER BY c.code
        """,
    resultSetMapping = "CategoryProductCountMapping"
)
@SqlResultSetMapping(
    name = "CategoryProductCountMapping",
    columns = {
        @ColumnResult(
            name = "cat_code",
            type = String.class),
        @ColumnResult(
            name = "product_count",
            type = Long.class)
    }
)
@Entity
public class Category {
    // Mapping entity Category thông thường.
}
~~~

Các annotation được đặt cùng entity trong ví dụ; với Java 15+ có thể sử dụng text block. Nếu dùng source level cũ, thay bằng các string literals thông thường.

Thực thi:

~~~java
Query query = em.createNamedQuery(
    "Category.countProducts");

List<?> rows = query.getResultList();

for (Object raw : rows) {
    Object[] values = (Object[]) raw;
    String code = (String) values[0];
    Long count = (Long) values[1];
}
~~~

### Hai tên khác nhau

`"Category.countProducts"` là **tên named native query**.

`"CategoryProductCountMapping"` là **tên result set mapping**.

Không hoán đổi chúng:

~~~java
em.createNamedQuery("Category.countProducts");
~~~

khác với:

~~~java
em.createNativeQuery(sql, "CategoryProductCountMapping");
~~~

Phương thức đầu tra cứu một query đã được khai báo. Phương thức sau nhận SQL động và tên mapping để sử dụng.

### Không dùng resultClass và resultSetMapping tùy tiện cùng mục tiêu

`@NamedNativeQuery` có lựa chọn ánh xạ bằng `resultClass` và `resultSetMapping`. Với kết quả nhiều phần, nên chọn `resultSetMapping` đã mô tả rõ structure, thay vì khai báo resultClass như thể query chỉ trả một entity. Kiểm tra contract API/annotation của phiên bản đang dùng khi cấu hình hai thuộc tính này.

## 31. So sánh ba overload của createNativeQuery

Các dạng thường gặp:

~~~java
em.createNativeQuery(sql);

em.createNativeQuery(sql, Product.class);

em.createNativeQuery(sql, "ProductCategoryLinesMapping");
~~~

| Cách tạo | Ý nghĩa |
| --- | --- |
| `createNativeQuery(sql)` | Kết quả native mặc định/scalar không có mapping tùy chỉnh |
| `createNativeQuery(sql, Product.class)` | Ánh xạ result set vào một entity result class thích hợp |
| `createNativeQuery(sql, "MappingName")` | Dùng `@SqlResultSetMapping` được khai báo với tên đó |

### Khi nào resultClass là đủ?

Khi SQL chỉ chọn **một entity** và cung cấp đủ các cột đúng mapping, ví dụ:

~~~sql
SELECT p.*
FROM products p
WHERE p.id = ?1
~~~

`createNativeQuery(sql, Product.class)` có thể phù hợp. Với SQL JOIN nhiều bảng có tên cột trùng, hoặc trả entity cộng aggregate, **mapping tường minh** thường an toàn và có ý nghĩa hơn.

### Không coi String overload là tên class

~~~java
em.createNativeQuery(sql, "ProductCategoryLinesMapping");
~~~

đòi hỏi tên metadata mapping đã đăng ký; không phải một class name tùy ý và cũng không phải tên bảng SQL.

## 32. Sắp xếp và phân trang result set nhiều phần

Sau khi tạo native query:

~~~java
Query query = em.createNativeQuery(
    sql,
    "ProductCategoryLinesMapping");

query.setParameter(1, tenantId);
query.setFirstResult(0);
query.setMaxResults(20);

List<?> page = query.getResultList();
~~~

JPA provider có thể chuyển pagination thành cú pháp SQL của dialect, hoặc có những giới hạn riêng. **Thứ tự trang phải dựa trên ORDER BY của Native SQL**, không dựa vào thứ tự map/collection sau khi query.

### Cẩn trọng khi JOIN làm nhân bản Product

Nếu không GROUP BY hoặc không chọn DISTINCT theo ngữ nghĩa đúng:

~~~text
Product#101 + OrderLine#1
Product#101 + OrderLine#2
Product#101 + OrderLine#3
~~~

SQL trả ba hàng cho cùng Product. Dù EntityResult của ba hàng có thể trỏ tới cùng managed Product instance, **danh sách kết quả vẫn có thể chứa ba hàng Object[]**, mỗi hàng kết hợp với scalar/association riêng.

Không nên ép “vì Product là cùng entity” thành kết luận resultList tự khử trùng mọi row trong kết quả nhiều phần.

### Nếu muốn đúng một hàng một Product

Trong ví dụ COUNT, ta dùng:

~~~sql
GROUP BY p.id, ...
~~~

để trả mỗi Product một hàng cùng số OrderLine. Khi có JOIN nhiều collection khác, phải kiểm tra fan-out và ngữ nghĩa aggregate cẩn thận; chỉ `DISTINCT` ở SELECT không sửa được mọi phép SUM/COUNT đã tính sai.

## 33. COUNT và SUM dễ sai khi JOIN nhiều quan hệ

Ví dụ một Product có:

~~~text
3 OrderLine
2 Tag
~~~

Nếu SQL JOIN cả:

~~~sql
FROM products p
JOIN order_lines ol ON ol.product_id = p.id
JOIN product_tags pt ON pt.product_id = p.id
~~~

tập kết quả có thể có:

~~~text
3 lines × 2 tags = 6 rows
~~~

Nếu tính:

~~~sql
COUNT(ol.id)
~~~

sẽ ra 6 thay vì 3. Có thể dùng:

~~~sql
COUNT(DISTINCT ol.id)
~~~

cho số dòng OrderLine thật sự, nhưng **SUM(ol.line_total)** cũng bị nhân đôi nếu không sửa JOIN hoặc tổng hợp dữ liệu theo đúng identity.

**Không dùng `SUM(DISTINCT ol.line_total)` như giải pháp chung**: hai OrderLine có cùng tiền vẫn là hai dòng nghiệp vụ khác nhau; DISTINCT theo số tiền sẽ làm mất một dòng hợp lệ.

### Hướng đúng

- Bỏ JOIN không cần thiết.
- Dùng các CTE/derived tables để aggregate từng quan hệ trước rồi join theo Product.
- Tách thành hai native queries khi dễ bảo trì hơn.
- Xây dựng read model/materialized view khi dashboard lớn và được đọc thường xuyên.

`@SqlResultSetMapping` chỉ chuyển **kết quả SQL thành Java object**. Nó không sửa được **SQL aggregate sai ngữ nghĩa**.

## 34. Kết hợp DTO và entity có thực sự cần thiết?

Một query trả:

~~~text
Product entity + Category DTO + line_count
~~~

có thể thuận tiện khi Product cần được cập nhật tiếp trong transaction, còn thông tin Category chỉ để hiển thị.

Tuy nhiên, hãy đặt câu hỏi:

1. Có thật cần Product managed hay chỉ cần Product ID/SKU?
2. Query có nhiều cột entity phải duy trì khi schema thay đổi?
3. Có muốn report object sống sau khi EntityManager đóng?
4. Có cần tránh lazy-loading và serialization entity?
5. Có thể gom các scalar vào một DTO duy nhất không?

Đối với API đọc:

~~~java
public record ProductReportRow(
    Long productId,
    String sku,
    String categoryCode,
    long lineCount) {
}
~~~

một ConstructorResult duy nhất thường dễ hiểu hơn Object[] nhiều phần.

Nếu nhu cầu đúng là **nhiều managed entities cùng scalar trong một SQL**, phối hợp EntityResult/ColumnResult là công cụ đúng, nhưng chi phí hiểu lifecycle cần được nhận diện rõ.

## 35. Vấn đề NULL với LEFT JOIN và EntityResult tùy chọn

Ví dụ Category có thể chưa gán cho Product:

~~~sql
SELECT ...
FROM products p
LEFT JOIN categories c ON c.id = p.category_id
~~~

Khi Category không có:

~~~text
p.id  = 101
c.id  = NULL
c.code = NULL
c.name = NULL
~~~

Nếu mapping gồm `@EntityResult(Category.class)`, phần kết quả Category có thể là NULL khi không có identity ở phía phải, nhưng hành vi hydration khi entity result có các cột null hoặc thiếu cột cần dựa theo mapping và provider.

### Thiết kế an toàn hơn cho nullable association

Nếu chỉ cần một vài thông tin Category:

~~~sql
c.code AS cat_code
~~~

và:

~~~java
@ColumnResult(name = "cat_code", type = String.class)
~~~

thì ứng dụng có thể xử lý null trực tiếp trong DTO. Điều này tránh dựng một managed Category từ một tập cột tất cả NULL.

### Đừng dùng INNER JOIN nếu muốn giữ Product chưa có Category

Ngay từ SQL:

~~~sql
JOIN categories c ...
~~~

đã loại Product không có quan hệ. Kết quả mất trước khi SqlResultSetMapping được áp dụng. Mapping không thể khôi phục hàng mà SQL không trả.

## 36. Xử lý lỗi ở đâu?

Một Native SQL có mapping nhiều phần có thể lỗi ở nhiều giai đoạn:

| Mốc | Lỗi ví dụ |
| --- | --- |
| Khởi động persistence unit | Mapping name trùng/metadata annotation sai |
| Tạo `createNativeQuery` | Tên SqlResultSetMapping không tồn tại |
| Bind parameter | Thiếu tham số hoặc binding không phù hợp |
| Thực thi SQL | Tên bảng/cột sai, SQL syntax, permissions, timeout, lock conflict |
| Chuyển result set thành entity | Alias thiếu, thiếu PK/FK/version, field mapping sai |
| Dựng DTO | Constructor không tồn tại/không tương thích kiểu, scalar NULL vào primitive |
| Cast Object[] | Giả định sai thứ tự hoặc số phần trong mapping |
| Truy cập association sau query | Lazy initialization khi context đóng |
| Sửa entity rồi commit | Dirty checking, optimistic lock exception hoặc constraint error |

### Ví dụ lỗi alias

SQL:

~~~sql
SELECT p.id AS product_id ...
~~~

Mapping:

~~~java
@FieldResult(name = "id", column = "prod_id")
~~~

Nếu query không hề có `prod_id`, provider không thể tìm đúng column label mong đợi. Lỗi này thường xuất hiện **khi thực thi/hydrate result set**, không nhất thiết lúc Java gọi `createNativeQuery(...)`.

### Ví dụ lỗi constructor

DTO:

~~~java
CategoryLineValueDto(String, BigDecimal)
~~~

Mapping:

~~~java
@ColumnResult(name = "cat_code", type = String.class),
@ColumnResult(name = "total_line_value", type = Long.class)
~~~

Lúc này constructor cần BigDecimal nhưng mapping yêu cầu Long. Hãy sửa ColumnResult type cho đúng, không cố ép tất cả Number thành Long.

### Hành vi lỗi provider-specific

Một provider có thể kiểm tra tên mapping sớm khi bootstrap; provider khác có thể chỉ báo lỗi khi query được tạo hoặc thực thi. Vì vậy **đừng xác định loại exception và thời điểm lỗi tuyệt đối** mà không xem stack hiện tại.

## 37. Native SQL không tự giải quyết an toàn truy vấn

Ví dụ lọc theo tenant:

~~~sql
WHERE p.tenant_id = ?1
~~~

Tham số tenant phải đến từ **ngữ cảnh xác thực tin cậy**, không lấy trực tiếp từ request rồi coi đó là quyền truy cập hợp lệ.

### Không nối input trực tiếp vào SQL

Không nên:

~~~java
String sql =
    "SELECT ... FROM products WHERE sku = '" +
    userInput + "'";
~~~

Cách này có rủi ro SQL injection.

Nên:

~~~sql
WHERE p.sku = ?1
~~~

và:

~~~java
query.setParameter(1, userInput);
~~~

### ORDER BY động phải whitelist

Không thể bind tên cột:

~~~sql
ORDER BY ?1
~~~

như thể đó là identifier SQL; parameter đại diện **giá trị**, không phải tên cột.

Nên map input sang các mảnh SQL cố định:

~~~java
String orderBy = switch (sortBy) {
    case "sku" -> "p.sku ASC, p.id ASC";
    case "price" -> "p.price ASC, p.id ASC";
    default -> "p.id ASC";
};
~~~

Sau đó chỉ ghép `orderBy` từ whitelist do ứng dụng kiểm soát.

### Cẩn trọng với row-level security

Khi DB có RLS hoặc ứng dụng có tenant filter của provider, hãy xác minh Native SQL có được áp dụng cùng chính sách như JPQL/Criteria không. Không giả định mọi provider-specific filter tự được chèn vào native query.

## 38. Flush, transaction và Native SQL result

Giả sử:

~~~java
Product product = em.find(Product.class, 101L);
// product.changePrice(...);

Query report = em.createNativeQuery(
    sql, "ProductCategoryLinesMapping");
report.setParameter(1, tenantId);

List<?> rows = report.getResultList();
~~~

Nếu Product đã được sửa trong RAM nhưng chưa flush, SQL báo cáo có thể đọc state của database tùy flush mode, provider và cách Native SQL được thực thi.

### Phân biệt ba lớp trạng thái

1. **Entity managed trong RAM**: giá trị persistent fields có thể đã đổi mà chưa có UPDATE.
2. **Database sau flush**: SQL đã được thực thi trong transaction nhưng chưa chắc commit.
3. **Transaction khác**: khả năng nhìn thấy thay đổi tùy isolation và commit.

`@SqlResultSetMapping` không điều khiển flush, commit hoặc isolation; nó chỉ mô tả kết quả khi SQL đã trả các cột.

### Đồng bộ trước native report khi cần

Nếu một báo cáo bắt buộc bao gồm những thay đổi của chính transaction đang pending, có thể xem xét:

~~~java
em.flush();
List<?> rows = report.getResultList();
~~~

Tuy nhiên, flush đồng bộ cả persistence context, có thể làm phát sinh constraint errors và lock sớm; nó **không commit**. Quyết định flush cần bám theo yêu cầu consistency, không đặt vô tội vạ trước mọi SELECT.

### Bulk native UPDATE khác SELECT mapping

`@SqlResultSetMapping` chủ yếu dùng cho **result set trả về**. Native UPDATE/DELETE thực thi bằng `executeUpdate()` không tự mang theo một Object[] có EntityResult chỉ vì class được gắn annotation.

Sau bulk/native DML, managed entities có thể stale; cần kế hoạch refresh/clear phù hợp trước khi tiếp tục thao tác.

## 39. Query result nhiều phần và phân tách tầng kiến trúc

Một repository có thể biết:

~~~text
parts[0] = Product
parts[1] = Category
parts[2] = lineCount
~~~

Nhưng controller/API không nên phụ thuộc trực tiếp các index này.

Gợi ý thiết kế:

~~~text
Database
   |
   v
Native SQL + SqlResultSetMapping
   |
   v
Repository Adapter
   - đọc Object[]
   - kiểm tra/cast types
   - chuyển thành result model
   |
   v
Service
   - nghiệp vụ, phân quyền, giao dịch
   |
   v
API DTO
~~~

Nếu service cần managed Product để tiếp tục sửa, result model có thể giữ tham chiếu entity kèm các số liệu báo cáo. Nếu service chỉ đọc, chuyển sang DTO immutable sớm thường làm contract đơn giản hơn.

### Ví dụ Result model

~~~java
public record ProductWithCategoryAndCount(
        Product product,
        Category category,
        long lineCount) {
}
~~~

Repository:

~~~java
List<ProductWithCategoryAndCount> answer =
    new ArrayList<>();

for (Object raw : nativeQuery.getResultList()) {
    Object[] values = (Object[]) raw;
    answer.add(new ProductWithCategoryAndCount(
        (Product) values[0],
        (Category) values[1],
        ((Number) values[2]).longValue()
    ));
}
~~~

Giữ logic index/cast trong repository giúp thay đổi mapping hoặc SQL mà không làm lan thay đổi kỹ thuật JDBC/ORM ra toàn ứng dụng.

## 40. Một ví dụ đầy đủ theo dạng @NamedNativeQuery

Nếu muốn đưa **tên query và mapping** cạnh nhau để dễ quản lý, có thể viết:

~~~java
@NamedNativeQuery(
    name = "Product.fetchCategoryAndLineCount",
    query = """
        SELECT
            p.id AS prod_id,
            p.tenant_id AS prod_tenant,
            p.sku AS prod_sku,
            p.price AS prod_price,
            p.status AS prod_status,
            p.version AS prod_version,
            p.category_id AS prod_category_fk,
            c.id AS cat_id,
            c.code AS cat_code,
            c.name AS cat_name,
            COUNT(ol.id) AS line_count
        FROM products p
        JOIN categories c ON c.id = p.category_id
        LEFT JOIN order_lines ol ON ol.product_id = p.id
        WHERE p.tenant_id = ?1
        GROUP BY
            p.id, p.tenant_id, p.sku, p.price,
            p.status, p.version, p.category_id,
            c.id, c.code, c.name
        ORDER BY p.id ASC
        """,
    resultSetMapping = "ProductCategoryLinesMapping"
)
@Entity
public class Product {
    // Các field entity và @SqlResultSetMapping đã nêu ở trên.
}
~~~

Đây là **phần annotation bổ sung** cho Product, không phải khai báo class Product thứ hai trong cùng source file. Khi triển khai, đặt `@NamedNativeQuery` cạnh `@SqlResultSetMapping` ở class Product đã định nghĩa tại mục 7.

Lệnh gọi:

~~~java
Query query = em.createNamedQuery(
    "Product.fetchCategoryAndLineCount");
query.setParameter(1, tenantId);
query.setMaxResults(50);

List<?> rows = query.getResultList();
~~~

### Ưu điểm

- SQL và tên mapping được gắn vào metadata triển khai.
- Những nơi gọi chỉ cần biết tên truy vấn.
- Dễ tìm kiếm và có thể được provider kiểm tra sớm khi bootstrap.

### Nhược điểm

- SQL dài làm class entity nhiều metadata.
- SQL thay đổi khi schema migration cần cập nhật annotation.
- Một số báo cáo cần cấu trúc điều kiện động; Native SQL string được build từ mảnh cố định có whitelist có thể phù hợp hơn.

Lựa chọn giữa named native query và native SQL xây động là quyết định tổ chức code, **không làm thay đổi ngữ nghĩa của SqlResultSetMapping**.

## 41. Kiểm thử mapping nhiều phần

Một unit test chỉ mock `Query.getResultList()` để trả Object[] không xác nhận JPA provider ánh xạ đúng alias, FK và constructor. Cần integration test với provider và DBMS đủ gần môi trường production.

### Bộ dữ liệu nhỏ

~~~text
Category:
    id=1, code=BOOK, name=Sách
    id=2, code=TECH, name=Thiết bị

Product:
    id=101, tenant=10, sku=BK-01, category=1, price=100000
    id=102, tenant=10, sku=BK-02, category=1, price=150000
    id=201, tenant=20, sku=TC-01, category=2, price=900000

OrderLine:
    id=1, product=101, lineTotal=100000
    id=2, product=101, lineTotal=200000
    id=3, product=102, lineTotal=150000
~~~

Với tenant=10, query ProductCategoryLinesMapping phải trả:

| Product | Category | line_count |
| --- | --- | ---: |
| BK-01 | BOOK | 2 |
| BK-02 | BOOK | 1 |

Product TC-01 không được trả vì thuộc tenant 20.

### Những tình huống cần thử

1. Product có **0 OrderLine**: COUNT=0 nhờ LEFT JOIN và COUNT(ol.id).
2. Hai entity cùng có ID số 1: ánh xạ đúng identity theo class.
3. Product.category là FK bắt buộc: mapping không thiếu FK alias.
4. SQL đổi alias nhưng annotation chưa đổi: test phát hiện mapping failure.
5. Scalar COUNT lớn: xử lý bằng Long/Number thích hợp.
6. DTO constructor đúng số lượng, thứ tự và kiểu args.
7. Entity returned có `em.contains(entity)` đúng trong persistence context.
8. Query không đưa dữ liệu tenant khác vào Object[].
9. Pagination có ORDER BY ổn định.
10. Native report và managed state có hành vi phù hợp sau flush/clear/refresh theo transaction.

### Vì sao phải kiểm tra trên DBMS đang dùng?

Native SQL phụ thuộc dialect. PostgreSQL, MySQL, SQL Server và Oracle có khác biệt về:

- Kiểu dữ liệu số.
- Case/quoting của alias.
- Cú pháp pagination.
- Cách CAST/COALESCE.
- Function và aggregate SQL.
- Kết quả driver trả cho DATE/TIMESTAMP/NUMERIC.

`@SqlResultSetMapping` không tự làm cho một câu SQL đặc thù DBMS trở thành SQL portable.

## 42. Những lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy mapping | Tên result set mapping sai hoặc class chưa được quét | Đăng ký metadata và kiểm tra tên chính xác |
| Chỉ dùng `createNativeQuery(sql)` nhưng muốn nhận Entity + DTO | Không có khai báo result mapping | Dùng overload có mapping name |
| `ClassCastException` cast row thành Product | Mapping trả nhiều phần Object[] | Xử lý đúng cấu trúc row |
| `parts[1]` không phải Category | Đổi thứ tự khai báo hoặc hiểu sai mapping | Đồng bộ mapping với repository adapter |
| SQL có `p.id` và `c.id` nhưng không alias | Trùng column labels | Alias độc lập `prod_id`, `cat_id` |
| FieldResult trỏ tới `price` nhưng SQL alias là `prod_price` | Tên column không khớp | `@FieldResult(name="price", column="prod_price")` |
| EntityResult trả entity thiếu state | SQL chỉ chọn vài cột | Chọn đủ persistent columns/FK/version hoặc đổi sang DTO |
| Entity có khóa tổng hợp nhận sai identity | Thiếu một phần composite PK | Ánh xạ toàn bộ key |
| Hibernate/JPA báo lỗi FK khi hydrate | Thiếu `category_id` hoặc alias quan hệ sai | Chọn và map join column của association |
| DTO constructor không được gọi | Số lượng/thứ tự/type của ColumnResult sai | Đồng bộ constructor signature |
| COUNT nhận sai kiểu | Driver/provider trả Number khác | Khai `type=Long.class` phù hợp và kiểm tra khi adapter |
| SUM rỗng nhận null | SQL aggregate không tự bằng 0 | COALESCE hoặc DTO nullable |
| COUNT Product=1 khi không có OrderLine | Dùng COUNT(*) trên LEFT JOIN | COUNT(ol.id) |
| COUNT/SUM lớn gấp đôi | JOIN nhiều to-many associations | Sửa JOIN/fan-out trước khi map |
| Dữ liệu Product stale sau native query | Identity map hoặc snapshot transaction | Xem refresh/clear và isolation |
| Entity sửa không commit được | Transaction/optimistic version/constraint | Quản lý transaction và @Version đúng |
| SQL báo syntax error | Native SQL không đúng DBMS | Xác nhận dialect và execution plan |
| Named native query không tìm thấy | Nhầm name với mapping name | Dùng `createNamedQuery(queryName)` |
| Dùng `getSingleResult()` nhưng query trả nhiều Product | Không có điều kiện unique | Dùng list/pagination hoặc điều kiện ID |
| DTO không được dirty-check | DTO không managed | Muốn cập nhật thì nạp entity managed |
| SQL không lọc tenant | Native SQL không tự kế thừa mọi filter | Áp ACL/tenant trong SQL và tại hạ tầng |
| Query phân trang trùng Product | JOIN nhân nhiều rows | Nhóm/khử trùng đúng đơn vị; page IDs trước |
| Lộ dữ liệu qua logging | Log SQL parameters nhạy cảm | Log có kiểm soát, mask thông tin |

## 43. Quy trình thiết kế một SqlResultSetMapping nhiều phần

Khi có một truy vấn Native SQL mới, nên làm theo thứ tự:

1. **Xác định ý nghĩa một hàng kết quả:** Product, OrderLine hay một nhóm aggregate?
2. **Liệt kê các phần cần trả:** entity, DTO, scalar; có thật cần managed entity?
3. **Thiết kế SQL đúng nghiệp vụ:** JOIN cardinality, WHERE, GROUP BY, NULL semantics.
4. **Đặt alias duy nhất cho mọi cột:** tránh `SELECT *` với nhiều bảng.
5. **Chọn đủ persistent fields cho EntityResult:** PK, FK, version và mọi field cần thiết.
6. **Khai báo FieldResult theo alias:** không nhầm tên Java field với tên cột thực hoặc column label.
7. **Khai báo ConstructorResult:** chọn DTO và constructor công khai với các tham số theo thứ tự.
8. **Khai báo ColumnResult:** chỉ rõ tên alias và kiểu scalar phù hợp.
9. **Đặt tên mapping duy nhất:** để repository tạo NativeQuery bằng tên.
10. **Dựng adapter cho Object[]:** tập trung cast/type handling và che giấu index khỏi service.
11. **Áp dụng security filters:** tenant/authorization không được bỏ sót.
12. **Xử lý transaction/lifecycle:** EntityResult managed, DTO không managed, flush/isolation độc lập.
13. **Thêm ORDER BY khi phân trang:** tie-breaker ổn định.
14. **Chạy integration test với DBMS thật:** bao gồm cột NULL, scalar aggregate, nhiều entity và phần result không khớp.
15. **Theo dõi SQL plan:** native query vẫn cần index, thống kê và giới hạn kết quả.

### Cây quyết định ngắn

~~~text
Cần Native SQL trả dữ liệu cho Java
                 |
                 v
           Chỉ 1 entity?
           /           \
         Có             Không
         |                |
         v                v
  SQL đủ mọi field?   Cần managed entity?
      /     \             /          \
    Có      Không       Có            Không
    |         |          |              |
    v         v          v              v
 resultClass  DTO     EntityResult    ConstructorResult
   hoặc       projection   +          hoặc ColumnResult
 EntityResult             DTO/scalar
                               |
                               v
                    SqlResultSetMapping nhiều phần
                               |
                               v
                        Object[] / Adapter
                               |
                               v
                       Service / API DTO
~~~

## 44. Bài tập thực hành

### Bài 1 — Entity và scalar

Một Native SQL trả mọi cột Product và `COUNT(ol.id) AS line_count`. Cần những annotation nào?

**Gợi ý:** `@SqlResultSetMapping` chứa `@EntityResult(Product.class)` và `@ColumnResult(name="line_count",type=Long.class)`; SQL phải chọn đủ cột Product.

### Bài 2 — Hai entity

SQL JOIN products và categories, cả hai có cột `id`. Vì sao nên dùng `prod_id` và `cat_id`?

**Gợi ý:** tránh trùng column labels; `@FieldResult` của mỗi EntityResult trỏ tới đúng alias.

### Bài 3 — Hình dạng Object[]

Mapping khai báo một Product EntityResult, một Category EntityResult và một ColumnResult Long. `getResultList()` trả từng hàng dưới dạng gì?

**Gợi ý:** một Object[] với Product, Category, Long theo cấu trúc mapping.

### Bài 4 — ConstructorResult

DTO `CategoryLineValueDto(String, BigDecimal)`. SQL trả `cat_code` và `total_line_value`. Hãy viết hai ColumnResult trong một ConstructorResult đúng thứ tự.

**Gợi ý:** `@ColumnResult(name="cat_code",type=String.class)` trước, `@ColumnResult(name="total_line_value",type=BigDecimal.class)` sau.

### Bài 5 — ConstructorResult + ColumnResult

Một mapping có ConstructorResult DTO chứa hai trường, và ColumnResult `line_count` ở ngoài. Object[] có mấy phần?

**Gợi ý:** hai: DTO và Long. Hai field constructor không thành hai phần tử độc lập.

### Bài 6 — Entity một phần

SQL chỉ trả `p.id, p.sku` nhưng ánh xạ thành Product có price/status/version/category. Có nên coi đó là managed Product đầy đủ?

**Gợi ý:** không. Chọn đủ persistent columns hoặc trả DTO chỉ gồm ID/SKU.

### Bài 7 — Optimistic version

Product có `@Version Long version`. Khi Native SQL mapping trả Product entity, vì sao phải chú ý cột version?

**Gợi ý:** version thuộc persistent state phục vụ optimistic locking; thiếu nó làm entity result không đủ dữ liệu.

### Bài 8 — Association FK

Product.category là ManyToOne qua `category_id`. Mapping EntityResult nên tham chiếu alias nào?

**Gợi ý:** alias cột FK của Product như `prod_category_fk`; map quan hệ qua `@FieldResult(name="category",column="prod_category_fk")`.

### Bài 9 — COUNT trong LEFT JOIN

Một Product không có OrderLine. `COUNT(*)` và `COUNT(ol.id)` khác nhau thế nào?

**Gợi ý:** COUNT(*) có thể là 1 vì LEFT JOIN giữ một hàng NULL; COUNT(ol.id)=0.

### Bài 10 — Managed hay DTO?

Query trả CategorySalesDto từ ConstructorResult. Sửa thuộc tính DTO trong transaction có tự UPDATE Category/Product không?

**Gợi ý:** không. DTO không phải managed entity.

### Bài 11 — Named query

Phân biệt `createNamedQuery("Product.fetchCategoryAndLineCount")` với `createNativeQuery(sql,"ProductCategoryLinesMapping")`.

**Gợi ý:** tên thứ nhất tra cứu NamedNativeQuery; tên thứ hai tra cứu result set mapping cho SQL được cung cấp.

### Bài 12 — SQL aliases

Mapping yêu cầu `@ColumnResult(name="line_count")` nhưng SQL viết `AS lines_total`. Vấn đề gì có thể xảy ra?

**Gợi ý:** không tìm thấy column label. Giữ tên alias và metadata nhất quán.

### Bài 13 — JOIN nhân bản hàng

Product có 2 tags và 3 order lines; SQL JOIN cả hai rồi SUM(line_total). Kết quả có thể sai thế nào?

**Gợi ý:** 6 hàng trung gian, mỗi line_total lặp hai lần. Phải sửa truy vấn/aggregate, mapping không tự sửa được.

### Bài 14 — Tenant scope

Query native không có predicate tenant nhưng JPA entity có tenant field. Có thể mặc định mọi provider tự thêm điều kiện tenant vào native SQL không?

**Gợi ý:** không. Phải kiểm chứng policy trên stack; thêm lọc quyền ở nơi đáng tin.

### Bài 15 — Scalar type

`SUM(NUMERIC(18,2))` được trả về như số tiền. Nên chọn `BigDecimal` hay `Double` trong DTO tài chính?

**Gợi ý:** BigDecimal, và kiểm soát null/rounding theo nghiệp vụ.

### Bài 16 — DTO nhiều phần

API chỉ cần ID Product, SKU, Category code và Count; có thật phải trả Product + Category managed entities không?

**Gợi ý:** không. Một DTO constructor projection có thể đơn giản, nhẹ và tách khỏi persistence context hơn.

### Bài 17 — Composite ID

Product identity là `(tenantId, sku)`. Native SQL chỉ chọn sku. Vì sao không đủ cho EntityResult?

**Gợi ý:** không thể xác định duy nhất entity identity qua nhiều tenant; phải chọn đủ composite key.

### Bài 18 — Stored procedure

Procedure trả hai ResultSet tách biệt, một chứa Products và một chứa Categories. Có thể coi một SqlResultSetMapping nhiều phần là tự ghép hai ResultSet thành Object[] không?

**Gợi ý:** không. Đây là hai JDBC result sets riêng; cần StoredProcedureQuery và xử lý từng result set theo contract tương ứng.

## 45. Bảng ghi nhớ nhanh

| Mong muốn | Cách làm |
| --- | --- |
| Map một entity đủ cột | `@EntityResult` |
| Map hai entity cùng hàng | Hai `@EntityResult`, alias tách biệt |
| Đổi alias SQL thành field Java | `@FieldResult(name="field", column="alias")` |
| Map COUNT thành Long | `@ColumnResult(name="count_alias",type=Long.class)` |
| Map SUM tiền thành BigDecimal | `@ColumnResult(name="sum_alias",type=BigDecimal.class)` |
| Map nhiều scalar vào DTO | `@ConstructorResult(targetClass=...,columns=...)` |
| Entity + DTO + scalar | Kết hợp `entities`, `classes` và `columns` |
| Chạy SQL động với mapping | `em.createNativeQuery(sql,"MappingName")` |
| Chạy query đã đặt tên | `em.createNamedQuery("QueryName")` |
| Lấy các phần đã mapping | `Object[]` mỗi hàng khi có nhiều phần |
| Tránh index/cast rải rác | Repository adapter chuyển thành result model |
| Một entity có @Version | Chọn/map cột version và các persistent fields |
| Cột SQL trùng tên | Alias rõ như `prod_id`, `cat_id` |
| Entity trả thiếu column | Chọn đủ column hoặc dùng DTO projection |
| SQL JOIN nhiều collection | Kiểm tra fan-out và aggregate trước khi mapping |
| Query có phân trang | ORDER BY ổn định, giới hạn trang |
| Query đa tenant | Bảo vệ tenant/ACL trong SQL hoặc policy xác thực |

## Kết luận

**`@SqlResultSetMapping` cho phép JPA ánh xạ một hàng Native SQL thành nhiều thành phần có ngữ nghĩa rõ ràng**, thay vì bắt ứng dụng xử lý mọi cột JDBC như một danh sách không có kiểu. `@EntityResult` dùng để tạo các entity từ tập cột đầy đủ, `@FieldResult` nối persistent field với SQL alias, `@ConstructorResult` dựng DTO bằng constructor từ các `@ColumnResult` có thứ tự, còn `@ColumnResult` trực tiếp biểu diễn scalar như COUNT hoặc SUM.

Khi một mapping có nhiều phần kết quả, mỗi hàng thường được xử lý dưới dạng **Object[] chứa entity, DTO và/hoặc scalar theo cấu trúc đã khai báo**. Chỉ thành phần entity mới có vòng đời managed/detached theo persistence context; DTO và scalar không tự dirty-check. Nếu chỉ cần projection đọc, một DTO thuần thường phù hợp hơn việc cố ánh xạ entity với thiếu cột.

Để dùng SqlResultSetMapping đúng và bền vững, hãy **thiết kế SQL có alias duy nhất, chọn đủ cột và khóa của entity, giữ constructor/type nhất quán, hiểu ảnh hưởng của JOIN/NULL/aggregate, áp dụng điều kiện bảo mật và đóng gói Object[] trong repository adapter**. Ánh xạ tốt giúp Native SQL hòa nhập rõ ràng với mô hình Java, nhưng không thay thế việc viết SQL đúng nghiệp vụ, kiểm thử trên DBMS thật hay quản lý transaction và concurrency phù hợp.
