# Dùng ParameterExpression để tách cấu trúc và giá trị trong Criteria API

Trong **Jakarta Persistence (JPA)**, Criteria API cho phép tạo truy vấn bằng các đối tượng Java thay vì viết toàn bộ câu JPQL dưới dạng chuỗi. Truy vấn thường gồm hai phần có vai trò khác nhau:

1. **Cấu trúc truy vấn:** entity nào được đọc, quan hệ nào được join, field nào được lọc, điều kiện được ghép bằng `AND` hay `OR`, kết quả có được sắp xếp và tổng hợp hay không.
2. **Giá trị đầu vào:** mã danh mục, ngưỡng giá, trạng thái, khoảng thời gian hoặc ID mà một lần thực thi cụ thể cần sử dụng.

**`ParameterExpression<T>`** là cơ chế tiêu chuẩn của Criteria API để thể hiện một **vị trí nhận giá trị có kiểu** trong cây truy vấn. Thay vì nhúng sẵn `"ACTIVE"` hoặc `100000` vào biểu thức điều kiện, ta tạo parameter lúc xây query rồi gắn giá trị lúc thực thi:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> product = cq.from(Product.class);

ParameterExpression<BigDecimal> minPrice =
    cb.parameter(BigDecimal.class, "minPrice");

cq.select(product)
  .where(
      cb.greaterThanOrEqualTo(
          product.<BigDecimal>get("price"),
          minPrice
      )
  );

TypedQuery<Product> query = em.createQuery(cq);
query.setParameter(minPrice, new BigDecimal("100000.00"));

List<Product> results = query.getResultList();
```

Cấu trúc **`price >= :minPrice`** được dựng bằng Criteria API. Giá trị **100000.00** chỉ được cung cấp khi chạy truy vấn. Ta có thể dùng cùng một cấu trúc truy vấn để chạy với `200000.00`, `500000.00` hoặc giá khác mà không phải dựng lại điều kiện bằng chuỗi.

Bài học này đi từ khái niệm tới ví dụ Java có kiểu, lọc động, tham số ngày giờ, enum, `LIKE`, `IN`, joins, aggregate, bulk update/delete và các lỗi thường gặp.

> **Điểm mấu chốt:** `ParameterExpression<T>` biểu diễn **giá trị dữ liệu**, không biểu diễn tên entity, tên field, hướng sắp xếp, toán tử hay một đoạn JPQL tùy ý. Cấu trúc truy vấn do ứng dụng quyết định; giá trị được truyền riêng qua `setParameter(...)`.

## 1. Vì sao cần tách cấu trúc và giá trị?

Giả sử có chức năng tìm sản phẩm:

- Danh mục: `"keyboard"`.
- Giá tối thiểu: `100000.00`.
- Trạng thái: `ACTIVE`.
- Tên chứa: `"wireless"`.

Cấu trúc logic của truy vấn là:

```text
SELECT Product
FROM Product
JOIN Category
WHERE Category.slug = ?
  AND Product.price >= ?
  AND Product.status = ?
  AND LOWER(Product.name) LIKE ?
ORDER BY Product.price ASC
```

Các dấu hỏi đại diện cho **dữ liệu đầu vào thay đổi theo request**.

Nếu đưa dữ liệu trực tiếp vào cấu trúc dạng chuỗi:

```java
String jpql =
    "SELECT p FROM Product p WHERE p.name = '" +
    userInput + "'";
```

code có thể gặp lỗi escape ký tự, truy vấn khó tái sử dụng và nguy cơ JPQL injection nếu nhận chuỗi không đáng tin từ bên ngoài.

Với Criteria API, ta biểu diễn cấu trúc bằng các đối tượng:

```java
Root<Product> p = cq.from(Product.class);

ParameterExpression<String> nameParam =
    cb.parameter(String.class, "name");

cq.where(cb.equal(p.get("name"), nameParam));
```

Sau đó cung cấp giá trị:

```java
em.createQuery(cq)
    .setParameter(nameParam, userInput)
    .getResultList();
```

JPA provider kiểm soát cách chuyển câu truy vấn thành SQL và bind giá trị theo cơ chế truy vấn có tham số. Giá trị không được tự diễn giải như một đoạn biểu thức JPQL chỉ vì nó chứa dấu nháy, dấu ngoặc hoặc từ khóa SQL.

### 1.1. Minh họa hai lớp trách nhiệm

```text
        GIAI ĐOẠN DỰNG TRUY VẤN
  +-----------------------------------+
  | CriteriaBuilder                   |
  | CriteriaQuery<Product>            |
  | Root<Product>                     |
  | Predicate                         |
  | ParameterExpression<BigDecimal>   |
  +-----------------------------------+
                   |
                   | cấu trúc ổn định
                   v
  WHERE product.price >= :minPrice
                   |
                   v
         GIAI ĐOẠN THỰC THI
  +-----------------------------------+
  | TypedQuery<Product>               |
  | setParameter(minPrice, 100000)    |
  | getResultList()                   |
  +-----------------------------------+
                   |
                   v
           SQL + bind values
                   |
                   v
                Database
```

Sự tách biệt này giúp:

- **Dễ kiểm soát dữ liệu đầu vào:** các giá trị được bind qua API thay vì nối chuỗi.
- **Kiểu dữ liệu rõ ràng hơn:** `ParameterExpression<BigDecimal>` khác `ParameterExpression<String>`.
- **Có thể tái sử dụng logic dựng truy vấn:** thay giá trị mà không thay biểu thức điều kiện.
- **Dễ viết lọc động:** cấu trúc thay đổi theo những bộ lọc được bật, còn giá trị của các bộ lọc vẫn được bind riêng.
- **Có cơ hội tận dụng cache kế hoạch truy vấn:** những lần thực thi có cùng hình dạng truy vấn có thể được provider/database tái sử dụng, nhưng không được bảo đảm tuyệt đối trên mọi hệ thống.

## 2. Mô hình dữ liệu dùng trong bài

Ta dùng hệ thống danh mục sản phẩm đơn giản, có hai entity:

- `Category`: danh mục, có khóa `id`, mã `slug` và tên.
- `Product`: sản phẩm, có tên, giá, tồn kho, trạng thái, thời gian tạo và tham chiếu `Category`.

Sơ đồ:

```text
+-------------------------+
| Category                |
|-------------------------|
| id                      |
| slug                    |
| displayName             |
+-------------------------+
            1
            |
            | @ManyToOne từ Product
            |
            *
+-------------------------+
| Product                 |
|-------------------------|
| id                      |
| name                    |
| price                   |
| stockQuantity           |
| status                  |
| createdAt               |
| version                 |
| category                |
+-------------------------+
```

### 2.1. Schema quan hệ

Ví dụ PostgreSQL:

```sql
CREATE TABLE categories (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    slug VARCHAR(80) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    category_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES categories(id),
    CONSTRAINT ck_product_price
        CHECK (price >= 0),
    CONSTRAINT ck_product_stock
        CHECK (stock_quantity >= 0)
);
```

Dữ liệu giả định:

**Danh mục**

| id | slug | display_name |
| ---: | --- | --- |
| 10 | keyboard | Bàn phím |
| 20 | mouse | Chuột |
| 30 | monitor | Màn hình |

**Sản phẩm**

| id | name | category_id | price | stock_quantity | status |
| ---: | --- | ---: | ---: | ---: | --- |
| 101 | Wireless Keyboard | 10 | 450000.00 | 20 | ACTIVE |
| 102 | Mechanical Keyboard | 10 | 1500000.00 | 0 | ACTIVE |
| 103 | Wireless Mouse | 20 | 230000.00 | 12 | ACTIVE |
| 104 | Gaming Mouse | 20 | 780000.00 | 3 | INACTIVE |
| 105 | 27-inch Monitor | 30 | 4200000.00 | 8 | ACTIVE |

Các ví dụ truy vấn giả định dữ liệu đã persist/commit và không có transaction khác thay đổi hàng trong khi mô tả kết quả.

### 2.2. Enum trạng thái

```java
package com.example.catalog;

public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    DISCONTINUED
}
```

Dùng enum trong Java giúp tránh những chuỗi trạng thái không được kiểm soát. JPA sẽ ánh xạ enum theo annotation `@Enumerated` của entity.

### 2.3. Entity Category

```java
package com.example.catalog;

import jakarta.persistence.*;

@Entity
@Table(name = "categories")
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String slug;

    @Column(
        name = "display_name",
        nullable = false,
        length = 120
    )
    private String displayName;

    protected Category() {
        // JPA constructor.
    }

    public Category(String slug, String displayName) {
        this.slug = slug;
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public String getSlug() { return slug; }
    public String getDisplayName() { return displayName; }
}
```

### 2.4. Entity Product

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    private Category category;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProductStatus status;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Product() {
    }

    public Product(
            Category category,
            String name,
            BigDecimal price,
            int stockQuantity,
            ProductStatus status,
            LocalDateTime createdAt) {
        this.category = category;
        this.name = name;
        this.price = price;
        this.stockQuantity = stockQuantity;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public Category getCategory() { return category; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public int getStockQuantity() { return stockQuantity; }
    public ProductStatus getStatus() { return status; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public Long getVersion() { return version; }
}
```

Các ví dụ Java trong bài dùng `jakarta.persistence.*`, tức Jakarta Persistence. Với ứng dụng cũ dùng `javax.persistence.*`, namespace import và môi trường chạy cần được điều chỉnh.

## 3. Những thành phần cốt lõi của Criteria API

Một truy vấn Criteria cơ bản sử dụng:

| Thành phần | Vai trò |
| --- | --- |
| `CriteriaBuilder` | Factory để tạo CriteriaQuery, Predicate, ParameterExpression và các expression khác. |
| `CriteriaQuery<T>` | Đại diện cho cấu trúc truy vấn SELECT trả kiểu `T`. |
| `Root<T>` | Entity gốc trong mệnh đề FROM. |
| `Path<T>` | Đường dẫn đến một thuộc tính đã ánh xạ. |
| `Join<X,Y>` | Biểu diễn phép nối quan hệ từ entity `X` đến `Y`. |
| `Predicate` | Biểu thức điều kiện trong WHERE, HAVING hoặc ON. |
| `ParameterExpression<T>` | Placeholder có kiểu cho một giá trị sẽ bind khi thực thi. |
| `TypedQuery<T>` | Truy vấn đã được tạo từ CriteriaQuery và có thể bind parameter, phân trang, thực thi. |

Một ví dụ không có parameter riêng:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Product> cq =
    cb.createQuery(Product.class);

Root<Product> root = cq.from(Product.class);

cq.select(root)
  .where(cb.equal(root.get("status"), ProductStatus.ACTIVE));

List<Product> products =
    em.createQuery(cq).getResultList();
```

Ví dụ này tạo một điều kiện bằng giá trị Java `ProductStatus.ACTIVE` truyền trực tiếp cho `cb.equal`.

Nếu ứng dụng muốn **dùng cùng cấu trúc cho nhiều trạng thái**, ta có thể thay bằng `ParameterExpression<ProductStatus>`:

```java
ParameterExpression<ProductStatus> statusParam =
    cb.parameter(ProductStatus.class, "status");

cq.select(root)
  .where(cb.equal(root.get("status"), statusParam));

TypedQuery<Product> query = em.createQuery(cq);

query.setParameter(statusParam, ProductStatus.ACTIVE);

List<Product> activeProducts = query.getResultList();
```

**Không phải mọi giá trị Java đưa vào CriteriaBuilder đều nguy hiểm hoặc trở thành đoạn SQL thô.** `cb.equal(path, value)` vẫn là API có kiểu và provider có thể xử lý giá trị an toàn. Lợi thế riêng của `ParameterExpression` là **thể hiện rõ placeholder tách khỏi cấu trúc truy vấn**, làm việc bind giá trị được quyết định ở giai đoạn thực thi và thuận lợi cho việc tái sử dụng logic.

## 4. Tạo ParameterExpression<T>

Phương thức quan trọng nhất:

```java
<T> ParameterExpression<T> parameter(Class<T> paramClass, String name)
```

Ví dụ:

```java
ParameterExpression<String> nameParam =
    cb.parameter(String.class, "name");

ParameterExpression<BigDecimal> priceParam =
    cb.parameter(BigDecimal.class, "price");

ParameterExpression<Long> productIdParam =
    cb.parameter(Long.class, "productId");

ParameterExpression<ProductStatus> statusParam =
    cb.parameter(ProductStatus.class, "status");

ParameterExpression<LocalDateTime> createdAfterParam =
    cb.parameter(LocalDateTime.class, "createdAfter");
```

Mỗi parameter chứa thông tin quan trọng:

1. **Kiểu giá trị `T`**, chẳng hạn `BigDecimal` hoặc `ProductStatus`.
2. **Tên parameter** nếu có, chẳng hạn `"minPrice"`.
3. **Vị trí trong cấu trúc truy vấn** nơi parameter được dùng.

Một `ParameterExpression<T>` là biểu thức có kiểu trong Criteria API và đồng thời cung cấp metadata của query parameter. Khi tạo nó, ta **chưa truyền giá trị**.

### 4.1. Parameter có tên

```java
ParameterExpression<String> categorySlug =
    cb.parameter(String.class, "categorySlug");
```

Có thể hiểu về mặt khái niệm như named parameter `:categorySlug` trong JPQL:

```jpql
SELECT p
FROM Product p
JOIN p.category c
WHERE c.slug = :categorySlug
```

Nhưng trong Criteria API, thay vì gõ `:categorySlug` vào chuỗi, ta truyền chính object parameter vào biểu thức:

```java
cq.where(cb.equal(category.get("slug"), categorySlug));
```

### 4.2. Parameter không có tên

CriteriaBuilder cũng có overload:

```java
ParameterExpression<BigDecimal> price =
    cb.parameter(BigDecimal.class);
```

Đây là **unnamed parameter**. Nếu dùng cách này, nên giữ tham chiếu đến object để bind:

```java
TypedQuery<Product> query = em.createQuery(cq);
query.setParameter(price, new BigDecimal("500000.00"));
```

Không nên tự suy ra số vị trí `1` hay `2` rồi dùng `setParameter(1, ...)` với unnamed Criteria parameters: việc provider trình bày tham số không tên trong SQL không có nghĩa ứng dụng đã định nghĩa JPQL positional parameter ổn định.

### 4.3. Parameter có tên và không tên: chọn cách nào?

| Lựa chọn | Ưu điểm | Điều cần lưu ý |
| --- | --- | --- |
| `cb.parameter(T.class, "name")` | Dễ đọc, có thể bind bằng tên hoặc object nếu phù hợp. | Tên phải thống nhất, tránh trùng/nhầm kiểu giữa các parameter. |
| `cb.parameter(T.class)` | Không phải quản lý tên chuỗi. | Phải giữ `ParameterExpression<T>` để bind; không tự suy diễn positional index. |

Với nhiều điều kiện động, parameter **có tên ngữ nghĩa rõ** thường giúp đọc và chẩn đoán dễ hơn, nhưng bind bằng object vẫn là lựa chọn có kiểm soát.

## 5. Đặt ParameterExpression vào Predicate

Giả sử tìm sản phẩm có giá không nhỏ hơn `:minPrice`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Product> cq =
    cb.createQuery(Product.class);

Root<Product> p = cq.from(Product.class);

ParameterExpression<BigDecimal> minPrice =
    cb.parameter(BigDecimal.class, "minPrice");

Predicate priceCondition = cb.greaterThanOrEqualTo(
    p.<BigDecimal>get("price"),
    minPrice
);

cq.select(p).where(priceCondition);
```

Ở đây:

- `p.<BigDecimal>get("price")` là một `Path<BigDecimal>`.
- `minPrice` là `ParameterExpression<BigDecimal>`.
- `cb.greaterThanOrEqualTo(...)` ghép hai expression cùng miền so sánh.
- `cq.where(...)` đưa predicate vào cấu trúc truy vấn.

**Chưa có giá cụ thể nào được gắn** lúc dựng predicate.

Thực thi:

```java
TypedQuery<Product> query = em.createQuery(cq);

query.setParameter(
    minPrice,
    new BigDecimal("500000.00")
);

List<Product> results = query.getResultList();
```

Với dữ liệu mẫu, kết quả gồm các sản phẩm có giá từ 500000.00 trở lên: #102, #104 và #105, nếu không có điều kiện bổ sung.

### 5.1. Vì sao có `<BigDecimal>get("price")`?

Phương thức `Path.get(String)` trả một path dựa trên tên thuộc tính. Khi làm việc với overload generic của CriteriaBuilder, ta có thể chỉ định kiểu:

```java
p.<BigDecimal>get("price")
```

để compiler hiểu đối số là biểu thức `BigDecimal`.

Nếu dự án có **JPA static metamodel**, có thể dùng dạng:

```java
p.get(Product_.price)
```

để tăng khả năng kiểm tra tên thuộc tính lúc biên dịch. `Product_` cần được annotation processor tạo ra; nó không tự có trong một Java project chưa cấu hình metamodel generation.

Dù dùng string-based path hay metamodel, `ParameterExpression<BigDecimal>` vẫn tách phần **giá trị** khỏi phần **cấu trúc**.

## 6. Gắn giá trị bằng TypedQuery.setParameter()

Sau khi `em.createQuery(cq)` trả `TypedQuery<Product>`, ta bind giá trị.

### 6.1. Bind bằng chính ParameterExpression

```java
query.setParameter(minPrice, new BigDecimal("100000.00"));
```

Đây là cách rất rõ ràng vì object `minPrice` chính là placeholder đã dùng khi dựng query.

Dạng chung:

```java
query.setParameter(Parameter<T> parameter, T value);
```

`ParameterExpression<T>` có thể được truyền vào overload nhận `Parameter<T>`.

### 6.2. Bind bằng tên

Nếu tạo named parameter:

```java
ParameterExpression<BigDecimal> minPrice =
    cb.parameter(BigDecimal.class, "minPrice");
```

có thể bind theo tên được khai báo:

```java
query.setParameter(
    "minPrice",
    new BigDecimal("100000.00")
);
```

Tuy nhiên, khi tên bị đổi trong cây truy vấn, một chuỗi `"minPrice"` ở nơi khác có thể không được sửa theo. Vì vậy, **bind bằng tham chiếu parameter** thường giảm khả năng gõ nhầm tên.

### 6.3. Không cần viết dấu hai chấm trong tên

Khi tạo:

```java
cb.parameter(BigDecimal.class, "minPrice");
```

tên parameter là `"minPrice"`, **không phải `":minPrice"`**.

Cú pháp `:minPrice` là cách JPQL text biểu diễn named parameter; còn tên truyền cho CriteriaBuilder/setParameter chỉ là tên logic.

### 6.4. Parameter khác tên field

Có thể đặt:

```java
ParameterExpression<BigDecimal> threshold =
    cb.parameter(BigDecimal.class, "threshold");
```

rồi dùng:

```java
cb.greaterThanOrEqualTo(
    p.<BigDecimal>get("price"),
    threshold
);
```

Tên `"threshold"` không cần trùng với tên field `"price"`. Nó mô tả **vai trò giá trị**; còn `get("price")` mô tả **thuộc tính được truy vấn**.

## 7. Ví dụ hoàn chỉnh: tìm sản phẩm theo danh mục và giá

Đây là ví dụ end-to-end nhỏ, có thể đặt trong một service Java SE sử dụng `RESOURCE_LOCAL` EntityManagerFactory.

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.List;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.ParameterExpression;
import jakarta.persistence.criteria.Root;

public final class ProductSearchService {
    private final EntityManagerFactory factory;

    public ProductSearchService(EntityManagerFactory factory) {
        this.factory = factory;
    }

    public List<Product> findByCategoryAndMinimumPrice(
            String categorySlug,
            BigDecimal minimumPrice) {

        EntityManager em = factory.createEntityManager();
        try {
            CriteriaBuilder cb = em.getCriteriaBuilder();
            CriteriaQuery<Product> cq =
                cb.createQuery(Product.class);

            Root<Product> p = cq.from(Product.class);
            Join<Product, Category> c =
                p.join("category", JoinType.INNER);

            ParameterExpression<String> slugParam =
                cb.parameter(String.class, "categorySlug");

            ParameterExpression<BigDecimal> minParam =
                cb.parameter(BigDecimal.class, "minimumPrice");

            cq.select(p)
              .where(
                  cb.and(
                      cb.equal(
                          c.<String>get("slug"),
                          slugParam
                      ),
                      cb.greaterThanOrEqualTo(
                          p.<BigDecimal>get("price"),
                          minParam
                      )
                  )
              )
              .orderBy(
                  cb.asc(p.get("price")),
                  cb.asc(p.get("id"))
              );

            TypedQuery<Product> query = em.createQuery(cq);
            query.setParameter(slugParam, categorySlug);
            query.setParameter(minParam, minimumPrice);

            return query.getResultList();
        } finally {
            em.close();
        }
    }
}
```

Cách gọi:

```java
List<Product> keyboards = service
    .findByCategoryAndMinimumPrice(
        "keyboard",
        new BigDecimal("400000.00")
    );
```

Theo dữ liệu mẫu, hai sản phẩm keyboard có giá ít nhất 400000.00 là #101 và #102. Chúng được sắp xếp theo giá tăng dần.

### 7.1. Truy vấn tương đương trong JPQL

```jpql
SELECT p
FROM Product p
JOIN p.category c
WHERE c.slug = :categorySlug
  AND p.price >= :minimumPrice
ORDER BY p.price ASC, p.id ASC
```

Viết bằng Criteria API dài hơn, nhưng cấu trúc có thể được tạo theo điều kiện ứng dụng, ghép nhiều predicate và giữ tham chiếu đến các parameter một cách tường minh.

### 7.2. SQL minh họa

JPA provider có thể tạo SQL tương tự:

```sql
SELECT p.id, p.category_id, p.name, p.price,
       p.stock_quantity, p.status, p.created_at,
       p.version
FROM products p
JOIN categories c ON c.id = p.category_id
WHERE c.slug = ?
  AND p.price >= ?
ORDER BY p.price ASC, p.id ASC;
```

Hai giá trị `"keyboard"` và `400000.00` được bind riêng. Tên placeholder, SQL dialect, cách chọn cột và phương pháp bind thực tế do provider/driver quyết định.

**Không giả định provider luôn tạo đúng chuỗi SQL trên.** Điều quan trọng là ngữ nghĩa query và việc tham số được cung cấp riêng.

### 7.3. Chỉ mở EntityManager để thực thi

Trong ví dụ, mỗi lời gọi tạo và đóng EntityManager. `EntityManagerFactory` có thể được chia sẻ như tài nguyên dùng chung trong ứng dụng; `EntityManager` không được chia sẻ tùy tiện giữa các thread.

Các truy vấn SELECT có thể chạy không cần explicit transaction trong một số cấu hình, nhưng nếu kết quả cần snapshot nhất quán hoặc phải tham gia luồng đọc-ghi, transaction boundary phải được thiết kế phù hợp. `ParameterExpression` không điều khiển transaction.

## 8. Tái sử dụng cấu trúc truy vấn với nhiều bộ giá trị

Giả sử ứng dụng cần cùng một bộ lọc:

```text
category.slug = :slug
AND product.price >= :minPrice
```

nhưng chạy cho hai request:

- Request A: `slug = "keyboard"`, `minPrice = 100000`.
- Request B: `slug = "mouse"`, `minPrice = 200000`.

Không cần xây query bằng cách nối lại chuỗi giá trị vào `WHERE`.

Có thể tạo hai `TypedQuery` từ cùng một cấu trúc Criteria đã hoàn thành:

```java
TypedQuery<Product> queryA = em.createQuery(cq);
queryA.setParameter(slugParam, "keyboard");
queryA.setParameter(
    minParam,
    new BigDecimal("100000.00")
);

List<Product> first = queryA.getResultList();

TypedQuery<Product> queryB = em.createQuery(cq);
queryB.setParameter(slugParam, "mouse");
queryB.setParameter(
    minParam,
    new BigDecimal("200000.00")
);

List<Product> second = queryB.getResultList();
```

Ở đây `cq`, `slugParam` và `minParam` được tạo trong cùng một quá trình dựng query. Cấu trúc giữ nguyên; **hai TypedQuery riêng** có bộ parameter bindings riêng.

### 8.1. Một TypedQuery có thể bind lại giá trị không?

Trong một đơn vị công việc, ứng dụng cũng có thể set lại parameter trước lần thực thi mới:

```java
TypedQuery<Product> query = em.createQuery(cq);

query.setParameter(slugParam, "keyboard");
query.setParameter(
    minParam,
    new BigDecimal("100000.00")
);
List<Product> first = query.getResultList();

query.setParameter(slugParam, "mouse");
query.setParameter(
    minParam,
    new BigDecimal("200000.00")
);
List<Product> second = query.getResultList();
```

Tuy nhiên, không nên chia sẻ cùng `TypedQuery` cho nhiều request/thread. Một `TypedQuery` là đối tượng có **trạng thái mutable** như parameter bindings, giới hạn kết quả và hints.

Nếu muốn dùng lại cấu trúc cho nhiều request, có thể giữ **logic dựng query** trong một factory/helper, nhưng mỗi request nên tạo EntityManager/TypedQuery và binding riêng trong phạm vi vòng đời phù hợp.

### 8.2. Đừng sửa cây CriteriaQuery đang được sử dụng bởi nhiều luồng

`CriteriaQuery` có các thao tác thay đổi cấu trúc như `where()`, `select()` và `orderBy()`. Không nên coi một instance CriteriaQuery mutable là đối tượng có thể bị nhiều thread cùng chỉnh sửa an toàn.

Một lựa chọn rõ ràng là:

1. Viết một method tạo CriteriaQuery và các ParameterExpression.
2. Mỗi request gọi method đó hoặc dùng một cấu trúc đã hoàn tất trong phạm vi được kiểm soát.
3. Mỗi request tạo TypedQuery riêng từ EntityManager phù hợp.
4. Bind giá trị riêng.
5. Không chỉnh sửa cấu trúc sau khi bắt đầu thực thi các query cần tính ổn định.

## 9. ParameterExpression có tên và tính nhất quán

Trong Criteria API, một tên parameter được dùng để xác định một binding logic. Khi có nhiều giá trị khác nhau, nên tạo các parameter có tên phân biệt:

```java
ParameterExpression<BigDecimal> minPrice =
    cb.parameter(BigDecimal.class, "minPrice");

ParameterExpression<BigDecimal> maxPrice =
    cb.parameter(BigDecimal.class, "maxPrice");
```

Tránh tạo hai parameter có **cùng tên nhưng nghĩa hoặc kiểu khác nhau**:

```java
// Không nên: cùng tên "amount" nhưng hai ý nghĩa khác.
ParameterExpression<BigDecimal> first =
    cb.parameter(BigDecimal.class, "amount");

ParameterExpression<Integer> second =
    cb.parameter(Integer.class, "amount");
```

Điều này có thể gây mơ hồ hoặc lỗi khi provider xử lý query parameters.

### 9.1. Một parameter được dùng nhiều lần

Nếu điều kiện dùng cùng **một giá trị logic**, có thể dùng cùng object parameter ở nhiều vị trí:

```java
ParameterExpression<String> keyword =
    cb.parameter(String.class, "keyword");

Predicate nameMatches =
    cb.like(cb.lower(p.<String>get("name")), keyword);

Predicate categoryMatches =
    cb.like(cb.lower(c.<String>get("displayName")), keyword);

cq.where(cb.or(nameMatches, categoryMatches));
```

Sau đó bind **một lần**:

```java
query.setParameter(keyword, "%wireless%");
```

Cả hai điều kiện sử dụng cùng mẫu `LIKE`. Hãy reuse chính `ParameterExpression` khi cần cùng giá trị, thay vì tạo hai parameter cùng tên một cách không kiểm soát.

### 9.2. Có thể kiểm tra metadata parameter

Các query JPA cung cấp cơ chế xem parameter:

```java
for (jakarta.persistence.Parameter<?> parameter
        : query.getParameters()) {

    System.out.println(parameter.getName());
    System.out.println(parameter.getParameterType());
}
```

Với parameter có tên, `getName()` trả tên đã khai báo. Query cũng có các API như `isBound(...)` hoặc `getParameterValue(...)` để hỗ trợ kiểm tra binding khi cần.

Những API này hữu ích để chẩn đoán nhưng không thay thế việc thiết kế một cấu trúc binding rõ ràng ngay từ đầu.

## 10. So sánh ParameterExpression với literal value

Có ba cách viết gần nhau nhưng cần hiểu sự khác biệt.

### 10.1. Dùng giá trị trực tiếp

```java
cb.equal(
    p.get("status"),
    ProductStatus.ACTIVE
);
```

Cấu trúc query chứa một điều kiện được xây với **giá trị Java đã biết lúc dựng**.

### 10.2. Dùng CriteriaBuilder.literal()

```java
cb.equal(
    p.get("status"),
    cb.literal(ProductStatus.ACTIVE)
);
```

`cb.literal(...)` tạo một **literal expression** đại diện giá trị đã biết trong cây Criteria. Nó không tương đương với việc viết một đoạn SQL tùy ý, và provider có thể quyết định biểu diễn literal bằng SQL literal hoặc JDBC bind parameter nội bộ.

### 10.3. Dùng ParameterExpression

```java
ParameterExpression<ProductStatus> statusParam =
    cb.parameter(ProductStatus.class, "status");

cb.equal(p.get("status"), statusParam);
```

Tại đây cấu trúc ghi rõ vị trí **chưa có giá trị cụ thể**. Giá trị sẽ được cung cấp sau:

```java
query.setParameter(
    statusParam,
    ProductStatus.ACTIVE
);
```

Bảng so sánh:

| Cách dùng | Giá trị quyết định khi nào? | Có object parameter để bind lúc chạy? |
| --- | --- | --- |
| `cb.equal(path, value)` | Khi dựng expression | Không, theo cách này |
| `cb.literal(value)` | Khi dựng expression | Không |
| `cb.parameter(Type.class, "name")` | Khi thực thi TypedQuery | Có |

**Không nên nói rằng `cb.literal(value)` luôn gây SQL injection.** Nó là expression do CriteriaBuilder tạo, không phải tự nối raw JPQL. Tuy nhiên, khi cần một **hình dạng truy vấn dùng với nhiều giá trị**, `ParameterExpression` thể hiện ý định tốt hơn.

## 11. An toàn dữ liệu đầu vào và giới hạn của parameterization

Giả sử tên tìm kiếm đến từ HTTP:

```text
GET /products?name=Wireless%20Keyboard
```

Ứng dụng có thể bind trực tiếp:

```java
ParameterExpression<String> nameParam =
    cb.parameter(String.class, "name");

cq.where(cb.equal(p.get("name"), nameParam));

query.setParameter(
    nameParam,
    requestName
);
```

Giá trị request được đưa vào vị trí **data parameter**, không trở thành tên bảng, alias hay một mệnh đề WHERE mới.

### 11.1. Điều parameterization có thể giúp tránh

Nó giảm nguy cơ ghép chuỗi JPQL không an toàn:

```java
// Không nên tự nối input vào cấu trúc query.
String jpql =
    "SELECT p FROM Product p WHERE p.name = '" +
    requestName +
    "'";
```

Nếu input chứa dấu nháy, chuỗi, toán tử hoặc từ khóa, việc nối chuỗi có thể phá cú pháp hoặc thay ý nghĩa query.

Dùng `ParameterExpression` tránh cách xây dựng đó.

### 11.2. Điều parameterization không tự giải quyết

Parameterization **không tự bảo đảm**:

- Người dùng có quyền xem mọi sản phẩm/tenant.
- Giá nhập hợp lệ hoặc nằm trong giới hạn nghiệp vụ.
- Chuỗi `LIKE` được xử lý theo đúng ý muốn với ký tự `%` và `_`.
- Một danh sách IDs không quá dài.
- Query không làm lộ dữ liệu nhạy cảm.
- Cấu trúc sort/filter tùy chọn đã được whitelist.
- Transaction isolation và concurrency đáp ứng yêu cầu.

**Giá trị được bind an toàn** là một tầng bảo vệ quan trọng, nhưng validation, authorization, tenant isolation và giới hạn tài nguyên vẫn phải được xử lý riêng.

## 12. Dùng parameter với nhiều loại dữ liệu

`ParameterExpression<T>` có khả năng kiểm tra kiểu ở mức Java generic và trong runtime/provider. Đây là một trong các lợi ích của Criteria API.

### 12.1. String

```java
ParameterExpression<String> slug =
    cb.parameter(String.class, "slug");

cq.where(cb.equal(c.<String>get("slug"), slug));

query.setParameter(slug, "keyboard");
```

Không truyền một `Long` vào parameter kiểu `String`.

### 12.2. BigDecimal

```java
ParameterExpression<BigDecimal> min =
    cb.parameter(BigDecimal.class, "min");

cq.where(
    cb.greaterThanOrEqualTo(
        p.<BigDecimal>get("price"), min
    )
);

query.setParameter(min, new BigDecimal("120000.00"));
```

Nên dùng `BigDecimal` cho tiền tệ theo mapping phù hợp, không thay bằng `double` chỉ vì người dùng nhập số thập phân. Khi bind, giữ đúng precision/scale và validation nghiệp vụ.

### 12.3. Enum

```java
ParameterExpression<ProductStatus> state =
    cb.parameter(ProductStatus.class, "state");

cq.where(cb.equal(
    p.<ProductStatus>get("status"),
    state
));

query.setParameter(state, ProductStatus.ACTIVE);
```

Dù database lưu `"ACTIVE"` qua `@Enumerated(EnumType.STRING)`, parameter trong Criteria API vẫn có kiểu Java `ProductStatus`. Không nhất thiết phải bind chuỗi `"ACTIVE"` thay cho enum.

### 12.4. Long ID

```java
ParameterExpression<Long> id =
    cb.parameter(Long.class, "productId");

cq.where(cb.equal(
    p.<Long>get("id"),
    id
));

query.setParameter(id, 101L);
```

Giá trị `101L` là `Long`, phù hợp với khóa `Long id`.

### 12.5. Boolean

Giả sử một entity khác có field `Boolean enabled`:

```java
ParameterExpression<Boolean> enabled =
    cb.parameter(Boolean.class, "enabled");
```

Parameter primitive `boolean` không thể dùng làm generic type `T`; dùng wrapper `Boolean.class`. Nếu field Java là primitive `boolean`, vẫn có thể biểu diễn predicate bằng expression tương ứng và parameter kiểu `Boolean`.

### 12.6. LocalDateTime

```java
ParameterExpression<LocalDateTime> cutoff =
    cb.parameter(LocalDateTime.class, "cutoff");

cq.where(
    cb.greaterThanOrEqualTo(
        p.<LocalDateTime>get("createdAt"),
        cutoff
    )
);

query.setParameter(
    cutoff,
    LocalDateTime.of(2026, 1, 1, 0, 0)
);
```

`LocalDateTime` là kiểu trong `java.time`. Jakarta Persistence hỗ trợ nhiều kiểu java.time phổ biến; không cần mặc định chuyển tất cả sang `java.util.Date`.

**Chú ý:** `LocalDateTime` không chứa timezone. Nếu ứng dụng phân tích khoảng thời gian theo múi giờ người dùng, phải có quy tắc chuyển múi giờ tại API/domain trước khi bind, hoặc dùng kiểu temporal có thông tin offset/instant và mapping phù hợp.

## 13. Khoảng giá: nhiều parameter trong BETWEEN

Một tính năng lọc phổ biến:

```text
minPrice <= product.price <= maxPrice
```

Criteria API:

```java
ParameterExpression<BigDecimal> minPrice =
    cb.parameter(BigDecimal.class, "minPrice");

ParameterExpression<BigDecimal> maxPrice =
    cb.parameter(BigDecimal.class, "maxPrice");

Predicate priceBetween = cb.between(
    p.<BigDecimal>get("price"),
    minPrice,
    maxPrice
);

cq.where(priceBetween);
```

Bind:

```java
query.setParameter(
    minPrice,
    new BigDecimal("200000.00")
);
query.setParameter(
    maxPrice,
    new BigDecimal("1000000.00")
);
```

`BETWEEN` thường bao gồm **cả hai biên**. Với giá tối thiểu 200000 và tối đa 1000000, dữ liệu mẫu cho #101, #103 và #104 nếu không có điều kiện trạng thái.

### 13.1. Kiểm tra trước khi bind

```java
if (min.compareTo(BigDecimal.ZERO) < 0
        || max.compareTo(min) < 0) {
    throw new IllegalArgumentException("Invalid price range");
}
```

Dù parameter có kiểu đúng, giá trị vẫn có thể không hợp lệ về nghiệp vụ. `BigDecimal` không tự giới hạn giá âm hay buộc min không lớn hơn max.

### 13.2. Có thể dùng hai điều kiện thay BETWEEN

```java
Predicate lower = cb.greaterThanOrEqualTo(
    p.<BigDecimal>get("price"),
    minPrice
);

Predicate upper = cb.lessThanOrEqualTo(
    p.<BigDecimal>get("price"),
    maxPrice
);

cq.where(cb.and(lower, upper));
```

Hai predicate cho phép bật/tắt từng biên độc lập. Đây là cơ sở của lọc động khi người dùng chỉ nhập min hoặc chỉ nhập max.

## 14. Lọc động: tạo cấu trúc theo bộ lọc được chọn

Một trang tìm kiếm thường có những điều kiện **tùy chọn**:

- `status`: có hoặc không.
- `categorySlug`: có hoặc không.
- `minPrice`: có hoặc không.
- `maxPrice`: có hoặc không.
- `nameContains`: có hoặc không.

Có hai câu hỏi cần tách:

1. **Predicate nào nên tồn tại trong query?** Đây là quyết định về cấu trúc.
2. **Giá trị của predicate là gì?** Đây là phần `ParameterExpression`/binding.

Nếu filter không xuất hiện, thường nên **không tạo predicate** tương ứng, thay vì tạo predicate bằng `= NULL` một cách máy móc.

### 14.1. DTO đầu vào

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductFilter(
    String categorySlug,
    ProductStatus status,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    String nameContains
) {}
```

Một giá trị `null` ở đây có nghĩa **filter đó không được bật**; đây là quy ước của DTO, không phải quy tắc mặc định của JPQL.

### 14.2. Dựng Predicate và lưu cả binding

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.*;

public final class DynamicProductSearch {

    public List<Product> search(
            EntityManager em,
            ProductFilter filter) {

        CriteriaBuilder cb = em.getCriteriaBuilder();
        CriteriaQuery<Product> cq =
            cb.createQuery(Product.class);

        Root<Product> p = cq.from(Product.class);
        List<Predicate> conditions = new ArrayList<>();

        // 1. Chỉ thêm join nếu có categorySlug.
        ParameterExpression<String> categoryParam = null;
        if (filter.categorySlug() != null) {
            Join<Product, Category> c =
                p.join("category", JoinType.INNER);

            categoryParam =
                cb.parameter(String.class, "categorySlug");

            conditions.add(
                cb.equal(
                    c.<String>get("slug"),
                    categoryParam
                )
            );
        }

        // 2. Chỉ thêm status condition nếu có filter.
        ParameterExpression<ProductStatus> statusParam = null;
        if (filter.status() != null) {
            statusParam = cb.parameter(
                ProductStatus.class,
                "status"
            );

            conditions.add(cb.equal(
                p.<ProductStatus>get("status"),
                statusParam
            ));
        }

        // 3. Giá tối thiểu.
        ParameterExpression<BigDecimal> minParam = null;
        if (filter.minPrice() != null) {
            minParam = cb.parameter(
                BigDecimal.class,
                "minPrice"
            );

            conditions.add(
                cb.greaterThanOrEqualTo(
                    p.<BigDecimal>get("price"),
                    minParam
                )
            );
        }

        // 4. Giá tối đa.
        ParameterExpression<BigDecimal> maxParam = null;
        if (filter.maxPrice() != null) {
            maxParam = cb.parameter(
                BigDecimal.class,
                "maxPrice"
            );

            conditions.add(
                cb.lessThanOrEqualTo(
                    p.<BigDecimal>get("price"),
                    maxParam
                )
            );
        }

        // 5. Tên có chứa chuỗi.
        ParameterExpression<String> nameParam = null;
        if (filter.nameContains() != null) {
            nameParam =
                cb.parameter(String.class, "nameLike");

            conditions.add(
                cb.like(
                    cb.lower(p.<String>get("name")),
                    nameParam,
                    '\\'
                )
            );
        }

        cq.select(p)
          .where(conditions.toArray(new Predicate[0]))
          .orderBy(
              cb.asc(p.get("price")),
              cb.asc(p.get("id"))
          );

        TypedQuery<Product> query = em.createQuery(cq);

        // Binding chỉ các parameter đã đưa vào query.
        if (categoryParam != null) {
            query.setParameter(
                categoryParam,
                filter.categorySlug()
            );
        }
        if (statusParam != null) {
            query.setParameter(
                statusParam,
                filter.status()
            );
        }
        if (minParam != null) {
            query.setParameter(
                minParam,
                filter.minPrice()
            );
        }
        if (maxParam != null) {
            query.setParameter(
                maxParam,
                filter.maxPrice()
            );
        }
        if (nameParam != null) {
            String safeTerm =
                escapeLike(filter.nameContains())
                    .toLowerCase(java.util.Locale.ROOT);

            query.setParameter(nameParam, "%" + safeTerm + "%");
        }

        return query.getResultList();
    }

    private static String escapeLike(String value) {
        return value
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_");
    }
}
```

Lời gọi ví dụ:

```java
ProductFilter filter = new ProductFilter(
    "keyboard",
    ProductStatus.ACTIVE,
    new BigDecimal("300000.00"),
    null,
    "wireless"
);

List<Product> products =
    new DynamicProductSearch().search(em, filter);
```

Trong dữ liệu mẫu, kết quả là `Wireless Keyboard`.

### 14.3. Vì sao chỉ bind những parameter đã dùng?

Trong mẫu trên, nếu `filter.maxPrice() == null`:

- Không tạo predicate giới hạn giá tối đa.
- Không đưa `maxParam` vào cấu trúc query.
- Không cố bind `maxParam`.

Đây là điểm rất quan trọng: **parameter tồn tại trong query phải được bind trước khi thực thi**, còn một parameter không thuộc query không cần và không nên được bind.

Nhiều lỗi `IllegalArgumentException` xuất hiện do code dùng `setParameter(...)` với một tên/object parameter **không thuộc truy vấn đã dựng**.

### 14.4. Có thể ghép các predicate bằng AND

`cq.where(Predicate...)` kết hợp những predicate được đưa vào như điều kiện AND theo semantics Criteria API.

Một cách khác:

```java
Predicate combined = cb.and(
    conditions.toArray(new Predicate[0])
);
cq.where(combined);
```

Nếu danh sách rỗng, query sẽ không áp bộ lọc tùy chọn nào. Không nên tạo một predicate luôn false khi không có filter, trừ khi đó là yêu cầu nghiệp vụ.

### 14.5. Đừng tạo query mới với toàn bộ các parameter luôn nullable rồi dùng = NULL

Một cách viết thường gặp:

```jpql
WHERE (:status IS NULL OR p.status = :status)
```

Có thể hữu ích trong một số hệ thống, nhưng không phải luôn là lựa chọn tốt nhất:

- Cần xử lý kiểu null của parameter rõ ràng.
- Điều kiện `OR` có thể ảnh hưởng khả năng dùng index và lựa chọn query plan.
- Một số DBMS/provider xử lý parameter null/type inference khác nhau.
- Cấu trúc vẫn chứa predicate, dù filter không được bật.

Với Criteria API, **dựng động những predicate thật sự cần** thường thể hiện ý định rõ ràng hơn. Tuy vậy, nếu hệ thống cần một hình dạng query cố định vì lý do đo được, có thể cân nhắc cách dùng parameter nullable và kiểm tra trên database mục tiêu.

## 15. Null: vì sao equal(path, nullParam) dễ sai?

Trong SQL, so sánh bằng với `NULL` không hoạt động như so sánh bằng một giá trị bình thường. Biểu thức `column = NULL` thường cho kết quả `UNKNOWN`, không phải TRUE.

Do đó:

```java
ParameterExpression<String> name =
    cb.parameter(String.class, "name");

cq.where(cb.equal(p.get("name"), name));

query.setParameter(name, null);
```

**không phải cách đáng tin để tìm các entity có `name IS NULL`**.

Nếu mục tiêu là tìm field null:

```java
cq.where(cb.isNull(p.get("name")));
```

Nếu mục tiêu là tìm field không null:

```java
cq.where(cb.isNotNull(p.get("name")));
```

### 15.1. Hai nghĩa khác nhau của null từ request

Một request có thể gửi:

- **Không cung cấp filter `name`**: không lọc tên.
- **Yêu cầu field `name` phải null**: lọc `IS NULL`.

Đây là **hai cấu trúc query khác nhau**.

Không dùng cùng một `null` mà không có hợp đồng rõ ràng, vì Criteria API không thể tự biết người dùng muốn **bỏ điều kiện** hay **kiểm tra NULL**.

Ví dụ thiết kế request:

```java
enum NameFilterMode {
    ANY,
    IS_NULL,
    IS_NOT_NULL,
    EQUALS
}
```

Sau đó code chọn predicate dựa trên mode:

```java
switch (mode) {
    case ANY -> {
        // Không thêm predicate.
    }
    case IS_NULL ->
        conditions.add(cb.isNull(p.get("name")));
    case IS_NOT_NULL ->
        conditions.add(cb.isNotNull(p.get("name")));
    case EQUALS -> {
        ParameterExpression<String> value =
            cb.parameter(String.class, "name");
        conditions.add(cb.equal(p.get("name"), value));
        // Lưu value để bind input thực tế.
    }
}
```

Đây là sự tách biệt **cấu trúc** và **giá trị** ở mức nghiệp vụ: null-check là một phép toán riêng, không chỉ là một giá trị của phép bằng.

## 16. LIKE với parameter và ký tự đại diện

Tìm sản phẩm có tên chứa một chuỗi:

```java
ParameterExpression<String> namePattern =
    cb.parameter(String.class, "namePattern");

Predicate condition = cb.like(
    cb.lower(p.<String>get("name")),
    namePattern
);

cq.where(condition);
```

Bind:

```java
query.setParameter(namePattern, "%wireless%");
```

Với dữ liệu mẫu, `Wireless Keyboard` và `Wireless Mouse` có thể được chọn.

### 16.1. Parameterization không tự escape wildcard

Dù giá trị đã được bind an toàn, trong phép `LIKE`:

- `%` thường khớp một chuỗi ký tự bất kỳ.
- `_` thường khớp một ký tự bất kỳ.

Nếu người dùng nhập `"50%"` và mong tìm dấu phần trăm **nguyên văn**, bind `"%50%%"` không có nghĩa giống tìm chuỗi literal `"50%"`.

Một cách dùng ký tự escape rõ ràng:

```java
ParameterExpression<String> pattern =
    cb.parameter(String.class, "pattern");

Predicate like = cb.like(
    cb.lower(p.<String>get("name")),
    pattern,
    '\\'
);
```

Chuẩn bị giá trị:

```java
static String escapeLike(String input) {
    return input
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_");
}

String patternValue =
    "%" +
    escapeLike(userInput).toLowerCase(java.util.Locale.ROOT) +
    "%";

query.setParameter(pattern, patternValue);
```

Lưu ý:

- Cách biểu diễn escape SQL thực tế có thể phụ thuộc dialect.
- `LOWER` giúp so sánh case-insensitive ở mức biểu thức nhưng không nhất thiết trùng mọi quy tắc Unicode/collation của người dùng.
- `LOWER(column)` và mẫu bắt đầu bằng `%` có thể hạn chế hiệu quả của index thông thường.
- Với search full-text lớn, nên cân nhắc chỉ mục/tính năng tìm kiếm chuyên dụng.

**Parameter binding chống việc input trở thành cấu trúc câu query, không tự quyết định semantics của phép LIKE.**

## 17. IN với danh sách giá trị động

Giả sử API nhận một tập product IDs:

```text
ids = [101, 103, 105]
```

Nghiệp vụ cần:

```jpql
WHERE p.id IN (:id1, :id2, :id3)
```

Trong Criteria API, có thể tạo `IN` predicate với **mỗi giá trị là một ParameterExpression<Long>`. Đây là hướng rõ ràng, portable khi số lượng IDs thay đổi.

```java
List<Long> ids = List.of(101L, 103L, 105L);

if (ids.isEmpty()) {
    return List.of();
}

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq =
    cb.createQuery(Product.class);
Root<Product> p = cq.from(Product.class);

CriteriaBuilder.In<Long> idIn =
    cb.in(p.<Long>get("id"));

List<ParameterExpression<Long>> idParams =
    new ArrayList<>();

for (int i = 0; i < ids.size(); i++) {
    ParameterExpression<Long> idParam =
        cb.parameter(Long.class, "id" + i);

    idIn.value(idParam);
    idParams.add(idParam);
}

cq.select(p).where(idIn);

TypedQuery<Product> query = em.createQuery(cq);

for (int i = 0; i < ids.size(); i++) {
    query.setParameter(idParams.get(i), ids.get(i));
}

List<Product> products = query.getResultList();
```

Tất cả IDs vẫn được bind **như dữ liệu**, không phải ghép trực tiếp thành JPQL string.

### 17.1. Vì sao cấu trúc IN thay đổi khi số phần tử thay đổi?

Lần đầu 3 IDs:

```text
p.id IN (?, ?, ?)
```

Lần sau 5 IDs:

```text
p.id IN (?, ?, ?, ?, ?)
```

Đây là hai **hình dạng truy vấn khác nhau**. `ParameterExpression` tách từng ID khỏi cấu trúc, nhưng **số lượng placeholder vẫn là một phần cấu trúc**.

Không thể giả định một parameter đơn luôn thay thế được mọi danh sách độ dài tùy ý trong mọi JPA provider.

### 17.2. Có thể bind một Collection vào IN không?

Một số provider và dạng JPQL hỗ trợ:

```jpql
WHERE p.id IN :ids
```

với `setParameter("ids", collection)`. Tuy nhiên, trong Criteria API, tạo một `ParameterExpression<List<Long>>` bằng `List.class` vướng **type erasure** và chi tiết hỗ trợ collection-valued parameter có thể khác giữa provider/phiên bản.

Nếu cần độ portable cao và số phần tử vừa phải, **một parameter cho mỗi phần tử** là lựa chọn dễ kiểm soát. Nếu muốn dùng collection-valued binding gọn hơn, cần xác nhận đặc tả phiên bản và provider thực tế.

### 17.3. Xử lý danh sách rỗng

Không nên tạo:

```jpql
WHERE p.id IN ()
```

rồi hy vọng mọi DBMS chấp nhận.

Nếu nghiệp vụ “IDs rỗng” nghĩa là “không có sản phẩm nào được chọn”, trả danh sách rỗng ngay. Hoặc nếu bắt buộc trả query kết quả rỗng, dùng predicate **luôn sai**:

```java
cq.where(cb.disjunction());
```

`cb.disjunction()` không có disjunct là FALSE theo semantics Criteria API.

Ngược lại, `cb.conjunction()` không có conjunct là TRUE. Hai phương thức này hữu ích trong các builder cho truy vấn động.

### 17.4. Giới hạn số parameter

Một danh sách hàng chục nghìn IDs có thể vượt giới hạn bind parameters của DBMS/driver hoặc tạo query plan kém.

Hãy cân nhắc:

- Chia batch theo giới hạn thực tế.
- Sử dụng bảng tạm/staging table khi phù hợp.
- Dùng một cách truyền tập dữ liệu đặc thù DBMS nếu cần hiệu năng cao.
- Hạn chế kích thước request đầu vào.

`ParameterExpression` không miễn trừ các giới hạn tài nguyên của database.

## 18. ParameterExpression với JOIN và quan hệ entity

Một predicate có thể kết hợp parameter và join.

Ví dụ tìm sản phẩm theo `Category.slug` và `Product.status`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq =
    cb.createQuery(Product.class);

Root<Product> p = cq.from(Product.class);
Join<Product, Category> c =
    p.join("category", JoinType.INNER);

ParameterExpression<String> slug =
    cb.parameter(String.class, "slug");

ParameterExpression<ProductStatus> status =
    cb.parameter(ProductStatus.class, "status");

cq.select(p)
  .where(
      cb.equal(c.get("slug"), slug),
      cb.equal(p.get("status"), status)
  );

TypedQuery<Product> query = em.createQuery(cq);
query.setParameter(slug, "keyboard");
query.setParameter(status, ProductStatus.ACTIVE);
```

Cấu trúc **JOIN** vẫn thuộc cây Criteria. `slug` và `status` chỉ là values.

### 18.1. Parameter không thay thế association name

Không được coi đoạn sau là cách tạo dynamic join portable:

```java
ParameterExpression<String> pathName =
    cb.parameter(String.class, "pathName");

// Không có nghĩa có thể:
// p.join(pathName)
```

`p.join("category")` nhận tên association/metamodel attribute để xác định **cấu trúc**. Nếu yêu cầu chọn join tới `category` hay association khác, code cần nhánh logic dựng join tương ứng, không dùng string parameter thay cho tên field.

### 18.2. LEFT JOIN và điều kiện ở ON

Nếu một entity có association tùy chọn và muốn giữ entity bên trái dù phía phải không khớp, có thể đặt predicate ở `Join.on(...)`.

Ví dụ quan hệ tùy chọn `Product.promotion` (một mapping **giả định bổ sung**, không có trong Product mẫu):

```java
Join<Product, Promotion> promotion =
    p.join("promotion", JoinType.LEFT);

ParameterExpression<Boolean> enabled =
    cb.parameter(Boolean.class, "enabled");

promotion.on(
    cb.equal(promotion.get("enabled"), enabled)
);
```

Ở đây cần thực sự định nghĩa entity `Promotion` và association tương ứng nếu muốn chạy. Ví dụ chỉ minh họa rằng **parameter có thể xuất hiện trong `ON`**, không chỉ trong WHERE.

Một `LEFT JOIN ... ON condition` có thể giữ Product không có promotion phù hợp; còn đưa điều kiện lên alias phía phải vào `WHERE` có thể loại các sản phẩm ấy. Tách cấu trúc và giá trị không làm thay đổi quy tắc semantics của outer join.

## 19. ParameterExpression trong ORDER BY: giới hạn cần nhớ

Giả sử người dùng chọn:

```text
sortBy = "price"
direction = "desc"
```

Không nên nghĩ có thể:

```java
ParameterExpression<String> sortField =
    cb.parameter(String.class, "sortField");

// Không có nghĩa ORDER BY sẽ dùng tên field từ sortField.
```

Một parameter giá trị không được dùng để biểu diễn **tên cột hoặc expression cấu trúc**.

Hãy whitelist các lựa chọn được phép:

```java
String requestedSort = inputSort;

jakarta.persistence.criteria.Expression<?> sortExpression =
    switch (requestedSort) {
        case "price" -> p.get("price");
        case "name" -> p.get("name");
        case "createdAt" -> p.get("createdAt");
        default -> p.get("id");
    };

boolean descending = "desc".equalsIgnoreCase(inputDirection);

cq.orderBy(
    descending
        ? cb.desc(sortExpression)
        : cb.asc(sortExpression),
    cb.asc(p.get("id"))
);
```

Lưu ý:

- `switch` ở đây quyết định **cấu trúc query** bằng các field được ứng dụng cho phép.
- `ParameterExpression` vẫn dành cho **giá trị lọc**.
- Không lấy raw input rồi đưa thẳng vào một hàm tạo SQL expression không an toàn.
- Có thể thêm `id` làm tie-breaker để phân trang ổn định hơn.

### 19.1. Không bind ASC hoặc DESC như giá trị

`ASC` và `DESC` là **lựa chọn cấu trúc ORDER BY**, không phải hai giá trị dữ liệu được so sánh ở WHERE.

Do đó không thể thay cả câu `ORDER BY p.price DESC` bằng một parameter như `:sortClause` rồi kỳ vọng provider diễn giải nội dung chuỗi thành JPQL mới.

## 20. ParameterExpression không dùng cho LIMIT/OFFSET

Muốn phân trang:

```java
TypedQuery<Product> query = em.createQuery(cq);

query.setFirstResult(offset);
query.setMaxResults(pageSize);
```

`offset` và `pageSize` thường được cung cấp qua API của `Query`, **không phải `ParameterExpression` trong CriteriaQuery**.

Ví dụ:

```java
int pageIndex = 2;
int pageSize = 20;

query.setFirstResult(pageIndex * pageSize);
query.setMaxResults(pageSize);
```

Trong môi trường production cần:

- Kiểm tra `pageIndex >= 0`.
- Giới hạn `pageSize` để tránh truy vấn quá lớn.
- Kiểm tra overflow khi tính offset.
- Có `ORDER BY` ổn định để tránh các page không dự đoán được.
- Xét keyset pagination nếu offset rất lớn hoặc dữ liệu thay đổi nhanh.

ParameterExpression giải quyết **giá trị trong biểu thức Criteria**, còn API pagination điều khiển cách lấy một phần kết quả.

## 21. ParameterExpression với COUNT, GROUP BY và HAVING

Ngoài WHERE, parameter có thể xuất hiện trong `HAVING` để so sánh giá trị aggregate.

Ví dụ yêu cầu:

> Trong những sản phẩm ACTIVE, danh mục nào có ít nhất `minimumCount` sản phẩm?

Cách viết Criteria:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<jakarta.persistence.Tuple> cq =
    cb.createTupleQuery();

Root<Product> p = cq.from(Product.class);
Join<Product, Category> c =
    p.join("category", JoinType.INNER);

ParameterExpression<ProductStatus> state =
    cb.parameter(ProductStatus.class, "state");

ParameterExpression<Long> minimumCount =
    cb.parameter(Long.class, "minimumCount");

var countProducts = cb.count(p);

cq.multiselect(
      c.<Long>get("id").alias("categoryId"),
      c.<String>get("displayName").alias("categoryName"),
      countProducts.alias("total")
  )
  .where(cb.equal(
      p.<ProductStatus>get("status"), state
  ))
  .groupBy(
      c.get("id"),
      c.get("displayName")
  )
  .having(
      cb.ge(countProducts, minimumCount)
  );

TypedQuery<jakarta.persistence.Tuple> query =
    em.createQuery(cq);

query.setParameter(state, ProductStatus.ACTIVE);
query.setParameter(minimumCount, 2L);

List<jakarta.persistence.Tuple> rows =
    query.getResultList();
```

Ở đây:

- `state` lọc đầu vào trước grouping.
- `minimumCount` đặt ngưỡng cho aggregate trong HAVING.
- `cb.count(p)` trả expression kiểu `Long`; vì vậy parameter ngưỡng có kiểu `Long`.
- `GROUP BY` tạo các nhóm danh mục theo ID/tên.

Theo dữ liệu mẫu, danh mục keyboard có 2 sản phẩm ACTIVE nên có thể xuất hiện; mouse chỉ có 1 ACTIVE, monitor có 1 ACTIVE.

### 21.1. Đừng nhầm COUNT trả Long với SIZE trả Integer

Thông thường trong JPA:

- `COUNT(...)` trả giá trị kiểu `Long`.
- `SIZE(collection)` trả giá trị đếm kiểu số nguyên `Integer` theo semantics JPQL.

Vì vậy, khi xây parameter so sánh với `COUNT`, `Long.class` là lựa chọn tự nhiên; khi so sánh ngưỡng `SIZE`, `Integer.class` thường phù hợp.

Giữ nhất quán kiểu numeric giúp tránh ép kiểu không cần thiết và lỗi binding.

### 21.2. Parameter trong HAVING vẫn phải được bind

Nếu cấu trúc query có:

```java
cq.having(cb.ge(cb.count(p), minimumCount));
```

thì trước `getResultList()` phải:

```java
query.setParameter(minimumCount, 2L);
```

Không có quy tắc “parameter trong HAVING tự nhận giá trị mặc định” khác WHERE.

## 22. Subquery dùng chung giá trị parameter

Một query có thể dùng parameter trong subquery tương quan, ví dụ:

> Chỉ lấy Category có ít nhất một Product ACTIVE và giá >= một ngưỡng.

Đây là dạng Criteria có parameter dùng bên trong subquery:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<Category> cq =
    cb.createQuery(Category.class);

Root<Category> c = cq.from(Category.class);

ParameterExpression<ProductStatus> state =
    cb.parameter(ProductStatus.class, "state");

ParameterExpression<BigDecimal> price =
    cb.parameter(BigDecimal.class, "minimumPrice");

Subquery<Long> subquery = cq.subquery(Long.class);
Root<Product> p = subquery.from(Product.class);

subquery.select(p.<Long>get("id"))
        .where(
            cb.equal(p.get("category"), c),
            cb.equal(
                p.<ProductStatus>get("status"),
                state
            ),
            cb.greaterThanOrEqualTo(
                p.<BigDecimal>get("price"),
                price
            )
        );

cq.select(c)
  .where(cb.exists(subquery));

TypedQuery<Category> query = em.createQuery(cq);

query.setParameter(state, ProductStatus.ACTIVE);
query.setParameter(
    price,
    new BigDecimal("400000.00")
);

List<Category> categories = query.getResultList();
```

Parameter trong subquery vẫn là parameter của **toàn bộ truy vấn thực thi**. Bind một lần trên TypedQuery gốc.

### 22.1. Reuse một parameter ở query chính và subquery

Nếu cùng một giá trị ngưỡng được dùng ở cả outer query và subquery, hãy truyền **cùng ParameterExpression** tới những biểu thức cần dùng, thay vì tạo hai parameter khác tên rồi bind trùng dữ liệu.

Nhưng không thể tái sử dụng `Root` của một query hoàn toàn khác như thể đó là một entity Java độc lập. `Root`/`Join` thuộc cấu trúc Criteria query cụ thể; cần dựng đúng scope cho subquery và outer query.

## 23. ParameterExpression trong CriteriaUpdate

Criteria API không chỉ có `CriteriaQuery` cho SELECT mà còn có **CriteriaUpdate** cho cập nhật hàng loạt.

Ví dụ:

> Đổi trạng thái những sản phẩm INACTIVE được tạo trước một ngày cutoff thành DISCONTINUED.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);

ParameterExpression<ProductStatus> newStatus =
    cb.parameter(ProductStatus.class, "newStatus");

ParameterExpression<ProductStatus> oldStatus =
    cb.parameter(ProductStatus.class, "oldStatus");

ParameterExpression<LocalDateTime> cutoff =
    cb.parameter(LocalDateTime.class, "cutoff");

update.set(
    p.<ProductStatus>get("status"),
    newStatus
);

update.where(
    cb.equal(
        p.<ProductStatus>get("status"),
        oldStatus
    ),
    cb.lessThan(
        p.<LocalDateTime>get("createdAt"),
        cutoff
    )
);

EntityTransaction tx = em.getTransaction();

tx.begin();
try {
    jakarta.persistence.Query query =
        em.createQuery(update);

    query.setParameter(
        newStatus,
        ProductStatus.DISCONTINUED
    );
    query.setParameter(
        oldStatus,
        ProductStatus.INACTIVE
    );
    query.setParameter(
        cutoff,
        LocalDateTime.of(2026, 1, 1, 0, 0)
    );

    int affected = query.executeUpdate();
    tx.commit();

    System.out.println("Updated: " + affected);
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Ví dụ trên giả định EntityManager được tạo từ persistence unit `RESOURCE_LOCAL`, vì vậy ứng dụng có quyền dùng `getTransaction()`. Với Spring/JTA EntityManager do container quản lý, transaction phải được điều phối bởi framework.

### 23.1. Điều quan trọng về bulk update

`CriteriaUpdate` có semantics của bulk update, không giống sửa từng managed entity:

- Câu lệnh cập nhật trực tiếp ở database.
- Không tự đồng bộ giá trị field của các managed instances đã tải trong persistence context.
- Không chạy mọi lifecycle logic/dirty checking như entity update thông thường.
- Không tự áp dụng optimistic version checking theo từng entity như thao tác managed update.
- Với field `@Version`, việc update version cần được thiết kế cụ thể nếu concurrency semantics yêu cầu.

`ParameterExpression` giúp **bind values**, nhưng **không làm bulk update trở thành managed-entity update**.

Sau bulk update, nếu trong context đã tải Product cũ, state Java có thể lỗi thời. Cần thiết kế `clear`/`refresh`/context mới, lưu ý những thay đổi chưa flush và caching.

### 23.2. Không cập nhật mọi field tùy ý từ input

Ví dụ API cho phép người dùng chọn tên cột bất kỳ để update là rủi ro bảo mật và toàn vẹn dữ liệu. ParameterExpression chỉ ràng buộc **giá trị mới**, không ngăn việc ứng dụng tự dựng một cấu trúc `update.set(...)` trên field không được phép.

Cần whitelist những field có thể cập nhật theo vai trò của caller.

## 24. ParameterExpression trong CriteriaDelete

JPA còn hỗ trợ bulk delete:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaDelete<Product> delete =
    cb.createCriteriaDelete(Product.class);

Root<Product> p = delete.from(Product.class);

ParameterExpression<ProductStatus> status =
    cb.parameter(ProductStatus.class, "status");

ParameterExpression<LocalDateTime> cutoff =
    cb.parameter(LocalDateTime.class, "cutoff");

delete.where(
    cb.equal(
        p.<ProductStatus>get("status"),
        status
    ),
    cb.lessThan(
        p.<LocalDateTime>get("createdAt"),
        cutoff
    )
);
```

Bind/thực thi trong transaction:

```java
EntityTransaction tx = em.getTransaction();

tx.begin();
try {
    jakarta.persistence.Query query =
        em.createQuery(delete);

    query.setParameter(
        status,
        ProductStatus.DISCONTINUED
    );

    query.setParameter(
        cutoff,
        LocalDateTime.of(2025, 1, 1, 0, 0)
    );

    int deleted = query.executeUpdate();

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Cần chú ý:

- Đây là **bulk delete**, không phải gọi `em.remove(product)` trên từng entity.
- Không tự thực hiện mọi cascade REMOVE/lifecycle callbacks của từng entity như khi remove managed entity.
- Foreign key ở database vẫn có thể từ chối thao tác.
- Managed Product cũ có thể trở nên stale.
- Chỉ dùng hard delete nếu domain và chính sách lưu trữ cho phép.

`ParameterExpression` không quyết định entity nào được phép xóa; nó chỉ truyền ngưỡng/trạng thái vào điều kiện mà ứng dụng đã cho phép.

## 25. Kiểu dữ liệu và type erasure của Java

`ParameterExpression<T>` có generic type `T` ở Java, nhưng generic không thay thế mọi quy tắc runtime.

Ví dụ:

```java
ParameterExpression<List<Long>> ids = /* ... */;
```

Không thể dễ dàng viết:

```java
cb.parameter(List<Long>.class, "ids");
```

vì Java không có `List<Long>.class` do **type erasure**.

Đây là một lý do vì sao collection-valued IN parameters đôi khi cần cơ chế riêng hoặc cách tạo nhiều `ParameterExpression<Long>` như mục 17.

### 25.1. Đừng ép kiểu runtime bừa bãi

Không nên che lỗi bằng raw cast:

```java
// Không nên dùng raw ParameterExpression rồi ép bừa sang kiểu khác.
ParameterExpression raw =
    cb.parameter(String.class, "value");
```

Kiểu có thể không phù hợp với path và giá trị bind, dẫn đến lỗi runtime hoặc hành vi provider khó hiểu. Hãy để kiểu generic thể hiện đúng kiểu domain đang so sánh.

### 25.2. Numeric promotion không thay cho thiết kế kiểu rõ

Nếu `Product.price` là `BigDecimal`, dùng `BigDecimal.class` cho ngưỡng so sánh. Tránh đặt parameter kiểu `Double` rồi hy vọng provider tự đổi chính xác dữ liệu tiền tệ.

Tương tự, field `Long id` nên dùng `Long.class` thay vì `Integer.class` chỉ vì ID nhỏ.

## 26. Các lỗi binding thường gặp

### 26.1. Quên bind một parameter

```java
ParameterExpression<BigDecimal> min =
    cb.parameter(BigDecimal.class, "min");

cq.where(cb.ge(p.<BigDecimal>get("price"), min));

TypedQuery<Product> query = em.createQuery(cq);

// Quên query.setParameter(min, value).
query.getResultList();
```

Truy vấn có parameter bắt buộc nhưng chưa được bind có thể thất bại khi thực thi, tùy thời điểm provider phát hiện.

Cách xử lý: giữ danh sách những parameter thực sự được đưa vào query và bảo đảm mọi parameter cần thiết đã có giá trị trước khi gọi `getResultList()`/`getSingleResult()`/`executeUpdate()`.

### 26.2. Bind tên không tồn tại

```java
query.setParameter("minimum", new BigDecimal("100000"));
```

Nếu query chỉ có tên `"minPrice"`, provider có thể ném `IllegalArgumentException`. Bind bằng object `minPrice` làm giảm rủi ro lỗi chính tả.

### 26.3. Bind object ParameterExpression của truy vấn khác

Một query được dựng với `minParamA` nhưng code cố dùng `minParamB` tạo ở một query khác:

```java
queryA.setParameter(minParamB, value);
```

Đừng giả định hai object khác nhau có tên giống nhau là cùng placeholder đối với mọi cách bind. Hãy giữ liên kết giữa **cấu trúc Criteria** và **parameter object đã dùng để tạo nó**.

### 26.4. Bind kiểu không tương thích

```java
ParameterExpression<ProductStatus> status =
    cb.parameter(ProductStatus.class, "status");
```

Không nên bind chuỗi `"ACTIVE"` vào object parameter này; dùng `ProductStatus.ACTIVE`.

Compiler có thể bắt được nhiều lỗi khi dùng typed overload; nhưng khi đi qua raw `Query`, cast hoặc input tổng quát, lỗi có thể chỉ lộ ra ở runtime.

### 26.5. Trộn giá trị và tên field

`ParameterExpression<String> sortField` không có nghĩa provider sẽ hiểu giá trị `"price"` thành path `p.price` trong ORDER BY. Đây là **nhầm dữ liệu với cấu trúc**, chứ không phải lỗi syntax nhỏ.

### 26.6. Dùng một tên cho hai mục đích khác nhau

Không nên dùng cùng tên `"threshold"` cho một parameter `BigDecimal` và một parameter `LocalDateTime`. Đặt tên theo domain: `"minPrice"`, `"createdAfter"`, `"status"`.

### 26.7. Dùng parameter null để bỏ filter mà không đổi cấu trúc

`WHERE p.status = :status` với `status = null` không tự biến thành không lọc. Nếu không có filter, hãy bỏ predicate hoặc chủ động viết logic nullable rõ ràng.

### 26.8. Quên phần trăm trong LIKE

Nếu query là `LIKE :pattern` và bind `"wireless"`, nó không tự tìm mọi chuỗi chứa wireless. Muốn chứa chuỗi, bind `"%wireless%"` và escape wildcard nếu đó là yêu cầu.

### 26.9. Thực thi khi EntityManager đã đóng

`TypedQuery` gắn với EntityManager/persistence context. Không tạo query rồi đóng EntityManager và kỳ vọng dùng query tùy ý ở nơi khác.

### 26.10. Giữ TypedQuery làm singleton

`TypedQuery` chứa binding mutable và không dùng an toàn đồng thời giữa thread. Hãy tạo query cho mỗi đơn vị công việc.

## 27. Tách truy vấn và giá trị trong thiết kế repository

Một hệ thống lớn có thể cần tái sử dụng cách dựng query mà không sao chép code bind ở nhiều nơi. Có thể tạo một **cấu trúc kết quả dựng query** gồm CriteriaQuery và các ParameterExpression của nó.

Ví dụ nhỏ cho filter bắt buộc:

```java
package com.example.catalog;

import java.math.BigDecimal;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.ParameterExpression;

public record ProductQueryTemplate(
    CriteriaQuery<Product> criteria,
    ParameterExpression<String> slug,
    ParameterExpression<BigDecimal> minimumPrice
) {}
```

Factory dựng cấu trúc:

```java
public static ProductQueryTemplate buildProductQuery(
        CriteriaBuilder cb) {

    CriteriaQuery<Product> cq =
        cb.createQuery(Product.class);
    Root<Product> p = cq.from(Product.class);
    Join<Product, Category> c = p.join("category");

    ParameterExpression<String> slug =
        cb.parameter(String.class, "slug");

    ParameterExpression<BigDecimal> minimumPrice =
        cb.parameter(BigDecimal.class, "minimumPrice");

    cq.select(p)
      .where(
          cb.equal(c.get("slug"), slug),
          cb.ge(p.<BigDecimal>get("price"), minimumPrice)
      );

    return new ProductQueryTemplate(
        cq, slug, minimumPrice
    );
}
```

Lưu ý đoạn `buildProductQuery` trên phải được đặt trong một class Java có import tương ứng (`CriteriaBuilder`, `Root`, `Join`, `Product`, `Category`, `BigDecimal`). Nó minh họa method, không phải một compilation unit độc lập.

Caller:

```java
ProductQueryTemplate template =
    buildProductQuery(em.getCriteriaBuilder());

TypedQuery<Product> query =
    em.createQuery(template.criteria());

query.setParameter(template.slug(), "keyboard");
query.setParameter(
    template.minimumPrice(),
    new BigDecimal("100000.00")
);

List<Product> products = query.getResultList();
```

### 27.1. Vì sao record/template hữu ích?

Nó giữ **cặp dữ liệu gắn bó**:

- CriteriaQuery đã dựng.
- Các ParameterExpression được dùng trong query ấy.

Tầng thực thi không phải đoán parameter nào tồn tại hoặc tên đã được sửa hay chưa.

### 27.2. Không biến template thành cache mutable toàn cục không kiểm soát

`CriteriaQuery` có thể tiếp tục bị sửa bằng `where`/`orderBy`. Nếu template được chia sẻ giữa request/thread, cần bảo đảm không có code chỉnh sửa nó khi đang thực thi.

Trong nhiều ứng dụng, phương thức factory dựng query theo request là đủ rõ. Chi phí dựng cây Criteria thường nhỏ hơn chi phí database I/O, nhưng điều này không thay thế việc đo đạc với workload thực tế.

## 28. Query plan caching: lợi ích có điều kiện

Khi chạy nhiều lần cùng một truy vấn:

```text
SELECT ...
WHERE category_slug = ?
  AND price >= ?
```

database có thể tái sử dụng parse/plan hoặc áp dụng prepared statement caching, còn JPA provider có thể tái sử dụng một số biểu diễn query nội bộ. Parameterization thường tạo điều kiện thuận lợi cho việc này.

Nhưng không nên khẳng định:

> “Cứ dùng ParameterExpression là database chỉ lập execution plan đúng một lần.”

Thực tế còn tùy:

- JPA provider và phiên bản.
- JDBC driver và statement cache.
- Database, thống kê bảng, index và parameter-sensitive optimization.
- Số lần gọi, kết nối và pool.
- Query shape: optional predicates, số lượng IN parameters, joins, ORDER BY.
- Dữ liệu/bộ lọc phân bố rất khác nhau có thể khiến optimizer chọn kế hoạch khác.

Đặc biệt, query với các filter được bật/tắt sẽ có **cấu trúc khác nhau**, dù mỗi giá trị trong cùng một cấu trúc được bind bằng ParameterExpression.

### 28.1. Bảo mật và hiệu năng là hai lợi ích khác nhau

- **Bảo mật:** dữ liệu không bị tự diễn giải là cú pháp query thông qua cách ghép chuỗi thủ công.
- **Khả năng tái sử dụng kế hoạch:** có thể được cải thiện khi shape ổn định và dùng bind parameters.

Không nên đổi một query có logic đúng thành một query có nhiều `OR :param IS NULL` chỉ vì nghe rằng “ít shape hơn là nhanh hơn”. Hãy dựa trên explain plan và số liệu.

## 29. Hỗ trợ nhiều tenant và phân quyền

Một ứng dụng SaaS có thể có field `tenantId` trên Product hoặc các entity khác. Nếu dữ liệu thuộc tenant khác nhau, filter theo tenant là **điều kiện bảo mật bắt buộc**, không phải filter tùy chọn giống minPrice.

Ví dụ một entity có `tenantId`:

```java
ParameterExpression<Long> tenantId =
    cb.parameter(Long.class, "tenantId");

conditions.add(
    cb.equal(root.<Long>get("tenantId"), tenantId)
);
```

Bind:

```java
query.setParameter(
    tenantId,
    authenticatedTenantId
);
```

Giá trị `authenticatedTenantId` phải đến từ **ngữ cảnh xác thực đáng tin**, không trực tiếp lấy từ query parameter mà người dùng có thể đổi tùy ý.

`ParameterExpression` giúp bind tenant ID như một value, nhưng **không tự bảo đảm quyền truy cập**. Cấu trúc query phải luôn chứa predicate đúng phạm vi tenant hoặc sử dụng cơ chế isolation được thiết kế ở tầng database/provider.

Không bao giờ bỏ predicate bắt buộc chỉ vì request không truyền tenant ID. Ngược lại với lọc tùy chọn, thiếu tenant context thường phải được xem là lỗi quyền truy cập hoặc lỗi cấu hình.

## 30. Giao dịch và thời điểm quan sát dữ liệu

`ParameterExpression` không quyết định dữ liệu mới/cũ được đọc. Ví dụ hai truy vấn với cùng `minPrice` trong một transaction có thể thấy kết quả khác hoặc giống nhau tùy isolation, flush và những thay đổi đang chờ.

Các yếu tố cần xét:

- `FlushModeType.AUTO` có thể khiến provider đồng bộ thay đổi trước một số truy vấn để bảo đảm semantics.
- Một transaction khác có thể commit thay đổi giữa hai lần query.
- `READ COMMITTED`, `REPEATABLE READ` và isolation kiểu snapshot có hành vi quan sát khác nhau tùy DBMS.
- Persistence context có identity map; entity trả về có thể là managed instance đã tồn tại.
- CriteriaQuery không tự tạo transaction hoặc lock.

Nếu nghiệp vụ cần cập nhật tồn kho một cách an toàn, dùng `@Version`, locking hoặc atomic update phù hợp. **Parameter binding không phải cơ chế concurrency control.**

### 30.1. Dùng ParameterExpression với lock mode

`TypedQuery` có thể được cấu hình lock mode khi phù hợp:

```java
TypedQuery<Product> query = em.createQuery(cq);

query.setParameter(idParam, productId);
query.setLockMode(
    jakarta.persistence.LockModeType.PESSIMISTIC_WRITE
);
```

Việc yêu cầu pessimistic lock cần transaction/DBMS hỗ trợ và có thể gặp timeout hoặc lỗi khóa. `idParam` vẫn chỉ là giá trị ID để lọc; lock mode là **thuộc tính thực thi của query**.

## 31. Java SE, Spring Data JPA và Criteria API

### 31.1. Java SE

Với `RESOURCE_LOCAL`, ứng dụng thường tạo EntityManager từ EntityManagerFactory, dựng query, bind và thực thi:

```java
EntityManager em = factory.createEntityManager();
try {
    CriteriaBuilder cb = em.getCriteriaBuilder();

    CriteriaQuery<Product> cq =
        cb.createQuery(Product.class);
    Root<Product> p = cq.from(Product.class);

    ParameterExpression<Long> id =
        cb.parameter(Long.class, "id");

    cq.select(p).where(cb.equal(p.get("id"), id));

    Product product = em.createQuery(cq)
        .setParameter(id, 101L)
        .getResultStream()
        .findFirst()
        .orElse(null);
} finally {
    em.close();
}
```

Ví dụ dùng `getResultStream().findFirst()` để không phải bắt `NoResultException`. Nếu ID là khóa chính và không cần cấu trúc query động, `em.find(Product.class, id)` ngắn hơn; ví dụ Criteria ở đây chỉ để minh họa parameter.

### 31.2. Spring Data JPA

Trong Spring, có thể inject EntityManager:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.List;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.criteria.*;
import org.springframework.stereotype.Repository;

@Repository
public class ProductCriteriaRepository {

    @PersistenceContext
    private EntityManager em;

    public List<Product> findAtLeast(BigDecimal minimumPrice) {
        CriteriaBuilder cb = em.getCriteriaBuilder();
        CriteriaQuery<Product> cq =
            cb.createQuery(Product.class);

        Root<Product> p = cq.from(Product.class);

        ParameterExpression<BigDecimal> min =
            cb.parameter(BigDecimal.class, "minPrice");

        cq.select(p).where(
            cb.ge(p.<BigDecimal>get("price"), min)
        );

        return em.createQuery(cq)
            .setParameter(min, minimumPrice)
            .getResultList();
    }
}
```

Spring transaction manager và EntityManager lifecycle được quản lý theo cấu hình framework. Không tự gọi `em.getTransaction().begin()` trên injected EntityManager do framework/container quản lý.

### 31.3. Spring Data Specification có cần ParameterExpression không?

Spring Data JPA cung cấp `Specification<T>` để dựng Criteria predicates, thường qua lambda:

```java
Specification<Product> minPrice(BigDecimal value) {
    return (root, query, cb) ->
        cb.ge(root.<BigDecimal>get("price"), value);
}
```

Cách này tiện để ghép filter và provider có thể tự xử lý giá trị truyền trực tiếp. Nếu muốn **tách explicit query parameter** rồi bind tại một bước riêng, repository tự dựng CriteriaQuery và ParameterExpression sẽ cho quyền kiểm soát binding rõ ràng hơn.

`Specification` và `ParameterExpression` không loại trừ nhau về mặt kỹ thuật, nhưng API Specification tự nó không cung cấp một cơ chế binding parameter ở ngoài đơn giản như code truy vấn thủ công. Hãy chọn mức trừu tượng phù hợp, tránh thêm parameter object khi tầng gọi không có cách bind nó.

## 32. Dùng setParameter theo object hay theo tên?

Hai cách đều hợp lệ với named parameter thuộc truy vấn:

```java
query.setParameter(minPrice, new BigDecimal("100000"));
```

và:

```java
query.setParameter("minPrice", new BigDecimal("100000"));
```

Khuyến nghị theo tình huống:

| Tình huống | Cách thường dễ kiểm soát |
| --- | --- |
| Dựng query và bind ngay trong cùng method | Theo object `ParameterExpression<T>` |
| Truyền template có sẵn cùng các parameter refs | Theo object refs trong template |
| Một framework tự ánh xạ tên/value từ metadata | Có thể theo tên, nếu tên ổn định |
| Query được tạo động với nhiều filter optional | Lưu parameter refs thực sự được dùng rồi bind |
| Unnamed parameter | Theo object parameter |
| Kết hợp nhiều parameter cùng kiểu | Đặt tên riêng hoặc giữ refs riêng rõ ràng |

Khi debug lỗi binding, hãy kiểm tra **parameter nào đã xuất hiện trong CriteriaQuery cuối**, không chỉ parameter nào đã được tạo bởi CriteriaBuilder trước đó.

## 33. Kiểm tra và xử lý lỗi truy vấn

Một query có thể thất bại ở nhiều giai đoạn:

1. **Dựng cấu trúc:** sai tên field, sai kiểu Path, join association không tồn tại.
2. **Tạo TypedQuery:** provider kiểm tra query tree, metadata và khả năng dịch.
3. **Bind:** thiếu parameter, bind sai kiểu hoặc dùng parameter không thuộc query.
4. **Thực thi:** SQL lỗi, timeout, connection lỗi, constraint hoặc lỗi database.
5. **Đọc kết quả:** kết quả không đúng cardinality khi dùng `getSingleResult()`.

Ví dụ code không nên:

```java
try {
    return query.getResultList();
} catch (RuntimeException ex) {
    return List.of(); // Che mọi lỗi thành "không có dữ liệu".
}
```

Một query lỗi không đồng nghĩa query chạy thành công nhưng không có sản phẩm nào.

Nên phân biệt:

- **Input không hợp lệ:** trả lỗi validation trước khi bind.
- **Không có kết quả:** `getResultList()` trả danh sách rỗng.
- **Sai parameter hoặc tên field:** lỗi lập trình, cần sửa.
- **Database unavailable/timeout:** lỗi hạ tầng, cần log/giám sát.
- **Optimistic/pessimistic lock conflict:** xử lý transaction/retry theo nghiệp vụ.

Không log raw tham số chứa dữ liệu nhạy cảm hoặc thông tin cá nhân nếu không có chính sách bảo vệ dữ liệu tương ứng.

## 34. Các hiểu lầm thường gặp

### “ParameterExpression làm CriteriaQuery tự động chạy”

Không. Nó chỉ là expression placeholder. Phải dùng `em.createQuery(cq)` và thực thi `getResultList()`, `getSingleResult()` hoặc phương thức thích hợp.

### “Gọi cb.parameter(...) đã có giá trị mặc định”

Không. `parameter(Class<T>, name)` chỉ tạo placeholder. Giá trị được gắn riêng qua `setParameter`.

### “Tên parameter phải giống tên cột SQL”

Không. `"minPrice"` là tên logic trong query. `Product.price` là property Java; tên cột SQL có thể khác.

### “Dùng ParameterExpression cho mọi thứ, kể cả ORDER BY column”

Không. Parameter chỉ mang giá trị; tên field và hướng sắp xếp thuộc cấu trúc Criteria.

### “ParameterExpression luôn giúp query nhanh hơn”

Không có bảo đảm. Nó có thể giúp ổn định query shape và cơ hội cache, nhưng kế hoạch SQL, index, dữ liệu và provider mới quyết định hiệu năng.

### “CriteriaBuilder.literal là lỗ hổng injection”

Không mặc định. Nó là Criteria expression do provider quản lý. Rủi ro rõ ràng hơn đến từ **tự nối input không tin cậy thành chuỗi JPQL/SQL**.

### “Dùng setParameter là không cần validate input”

Sai. Giá âm, date range sai, danh sách quá lớn và thiếu quyền tenant vẫn là vấn đề ứng dụng.

### “NULL được bind vào equal sẽ tự thành IS NULL”

Không nên giả định. Dùng `cb.isNull(path)` khi chủ ý kiểm tra null, hoặc bỏ predicate khi filter không xuất hiện.

### “LIKE parameter tự coi % và _ là ký tự bình thường”

Không. Chúng là wildcard theo semantics LIKE; phải escape nếu nghiệp vụ cần tìm literal substring.

### “Cùng tên parameter nhưng khác object luôn chắc chắn bind như một”

Không nên dựa vào điều đó. Reuse cùng object ParameterExpression cho một logical value, đặt tên riêng cho những giá trị khác nhau.

### “Tạo parameter nhưng không đưa vào where vẫn phải bind”

Không. Chỉ bind parameter thực sự thuộc query; cố bind parameter không có trong query có thể lỗi.

### “Mọi IN đều có thể dùng một ParameterExpression<List<Long>> portable”

Không mặc định. Hỗ trợ collection-valued parameter và type erasure cần được xem xét theo đặc tả/provider; có thể dùng parameter riêng cho từng ID.

### “CriteriaUpdate có @Version nên tự kiểm tra version giống entity update”

Không. Bulk update có semantics riêng và không tự kiểm tra lifecycle/version của từng managed entity.

### “Dùng query param tenantId là đủ để phân quyền”

Không. Giá trị tenant phải lấy từ nguồn xác thực đáng tin và predicate bảo mật phải luôn được áp dụng.

### “EntityManager và TypedQuery dùng chung nhiều thread là bình thường”

Không. Tránh dùng chung mutable query/persistence context giữa các luồng; quản lý theo đơn vị công việc.

### “setParameter quyết định có JOIN nào trong query”

Không. JOIN phải được dựng trong Criteria tree. Parameter chỉ cung cấp giá trị cho điều kiện.

## 35. Bài tập thực hành

### Bài 1 — Tìm sản phẩm có giá từ 1 triệu

**Yêu cầu:** Tạo ParameterExpression có kiểu và bind giá.

**Đáp án:**

```java
ParameterExpression<BigDecimal> min =
    cb.parameter(BigDecimal.class, "minPrice");

cq.where(cb.ge(p.<BigDecimal>get("price"), min));

TypedQuery<Product> query = em.createQuery(cq);
query.setParameter(min, new BigDecimal("1000000.00"));
```

### Bài 2 — Thay đổi giá trị mà giữ query shape

**Yêu cầu:** Dùng một cấu trúc lọc theo giá tối thiểu cho 200000 và 500000.

**Gợi ý:** Tạo `CriteriaQuery` và `ParameterExpression<BigDecimal>` một lần trong một đơn vị công việc, sau đó tạo hai TypedQuery hoặc bind lại giá trị trước hai lần thực thi. Không thay predicate `price >= ...`.

### Bài 3 — Tìm sản phẩm ACTIVE

```java
ParameterExpression<ProductStatus> state =
    cb.parameter(ProductStatus.class, "state");

cq.where(cb.equal(
    p.<ProductStatus>get("status"),
    state
));

query.setParameter(state, ProductStatus.ACTIVE);
```

Giải thích: bind enum `ProductStatus`, không phải một chuỗi nếu field được mapping thành enum.

### Bài 4 — Lọc giá theo hai biên

**Yêu cầu:** Người dùng nhập `min = 100000` và `max = 500000`.

**Gợi ý:** Tạo hai parameter `BigDecimal`, dùng `cb.between` hoặc hai điều kiện `>=` và `<=`; kiểm tra `max >= min` trước khi bind.

### Bài 5 — Filter status không được truyền

**Yêu cầu:** Nếu status null nghĩa là không lọc trạng thái.

**Gợi ý:** Không tạo predicate status trong CriteriaQuery. Đừng bind null vào `p.status = :status` và nghĩ nó tự bỏ điều kiện.

### Bài 6 — Tìm field null

**Yêu cầu:** Tìm Product có một field tùy chọn `description` bằng null.

**Gợi ý:** `cb.isNull(p.get("description"))`. Đó là cấu trúc khác với `cb.equal(path, parameter)`.

### Bài 7 — Tên chứa ký tự % nguyên văn

**Yêu cầu:** User nhập `"50%"` và muốn tìm chính chuỗi đó trong tên.

**Gợi ý:** Tạo LIKE với escape character, escape `%`/`_`/ký tự escape trong input, sau đó bind pattern có `%` ở đầu/cuối.

### Bài 8 — Lọc theo ba Product IDs

**Yêu cầu:** Dùng `IN` với ba ID.

**Gợi ý:** Tạo ba `ParameterExpression<Long>` rồi `CriteriaBuilder.In<Long>.value(parameter)`. Bind từng ID với TypedQuery. Với danh sách rỗng, xử lý từ nghiệp vụ thay vì tạo `IN ()`.

### Bài 9 — Đếm sản phẩm theo trạng thái

**Yêu cầu:** Đếm Product ACTIVE có giá tối thiểu 500000.

**Gợi ý:**

```java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Product> p = cq.from(Product.class);

ParameterExpression<ProductStatus> state =
    cb.parameter(ProductStatus.class, "state");

ParameterExpression<BigDecimal> minPrice =
    cb.parameter(BigDecimal.class, "minPrice");

cq.select(cb.count(p))
  .where(
      cb.equal(p.get("status"), state),
      cb.ge(p.<BigDecimal>get("price"), minPrice)
  );
```

Bind cả hai parameter trước `getSingleResult()`.

### Bài 10 — Sort field tùy chọn

**Yêu cầu:** Client chọn sort theo `price`, `name` hoặc `createdAt`.

**Gợi ý:** Dùng `switch`/whitelist để chọn `Path<?>` và `cb.asc/desc`. Không truyền `"price DESC"` vào `ParameterExpression<String>` rồi dùng như một SQL clause.

### Bài 11 — Bulk update giá

**Yêu cầu:** Tăng giá cố định của một nhóm sản phẩm.

**Gợi ý:** Dùng `CriteriaUpdate<Product>`, parameter cho giá mới hoặc mức điều chỉnh, predicate nhóm rõ ràng và transaction. Sau bulk update, quản lý persistence context bị stale.

### Bài 12 — Tenant filter

**Yêu cầu:** Mọi query của một endpoint đều phải bị giới hạn bởi tenant của người dùng đăng nhập.

**Gợi ý:** Thêm predicate tenant bắt buộc và bind giá trị tenant lấy từ authentication context. Không bỏ predicate khi request không cung cấp tenant ID.

### Bài 13 — Reuse cùng keyword trong hai trường

**Yêu cầu:** Tìm từ khóa trong Product.name hoặc Category.displayName.

**Gợi ý:** Tạo **một** `ParameterExpression<String> keyword`, đưa vào hai `cb.like(...)` rồi bind một pattern đã escape đúng.

### Bài 14 — Lỗi bind nhầm parameter

**Tình huống:** Query được dựng với `minPrice` nhưng caller chỉ có một object `maxPrice` tạo từ query khác.

**Giải thích:** Không bind nhầm parameter object. Đóng gói CriteriaQuery cùng refs cần thiết hoặc dùng tên có kiểm soát; sửa ở tầng thiết kế factory/query template.

### Bài 15 — Query plan reuse

**Câu hỏi:** Hai lần gọi cùng cấu trúc `WHERE price >= :min` nhưng giá trị khác có chắc database chỉ lập một execution plan không?

**Giải thích:** Không bảo đảm. ParameterExpression giúp ổn định hình dạng query và tạo cơ hội cache; provider, driver, DBMS, parameter-sensitive plans và cấu hình quyết định việc reuse thực tế.

## 36. Câu hỏi tự kiểm tra

**1. `ParameterExpression<T>` là gì?**

Là một biểu thức tham số có kiểu trong Criteria API, đại diện cho vị trí nhận giá trị sẽ được bind khi thực thi truy vấn.

**2. Phương thức nào tạo một named parameter?**

`CriteriaBuilder.parameter(Class<T>, String name)`.

**3. Có thể tạo unnamed parameter không?**

Có, bằng `CriteriaBuilder.parameter(Class<T>)`; nên giữ object để bind.

**4. ParameterExpression nhận giá trị ngay khi gọi `cb.parameter` không?**

Không. Giá trị được gắn bằng `setParameter` trên Query/TypedQuery.

**5. Nên bind bằng object hay tên?**

Cả hai có thể dùng với named parameter hợp lệ, nhưng bind bằng chính object `ParameterExpression` giúp giữ sự liên kết có kiểu với cấu trúc đã dựng.

**6. Có viết `cb.parameter(BigDecimal.class, ":minPrice")` không?**

Không cần dấu hai chấm. Tên logic là `"minPrice"`.

**7. Vì sao `ParameterExpression<BigDecimal>` phù hợp hơn `ParameterExpression<Double>` cho Product.price?**

Vì field được mapping thành `BigDecimal` để biểu diễn số tiền/giá chính xác và tránh conversion sai kiểu.

**8. Có thể dùng ParameterExpression để chọn tên cột ORDER BY không?**

Không. Tên field và hướng sắp xếp thuộc cấu trúc truy vấn; cần whitelist và dựng `orderBy` tương ứng.

**9. Muốn tìm field NULL thì bind null vào equal có đủ không?**

Không nên. Dùng `cb.isNull(path)` theo ý định.

**10. Nếu một filter tùy chọn không được nhập, nên làm gì?**

Thường không tạo predicate/parameter của filter đó; chỉ bind những parameter thực sự được dùng.

**11. LIKE nhận input người dùng có `%` thì sao?**

`%` là wildcard của LIKE; dùng escape nếu cần tìm dấu phần trăm như ký tự nguyên văn.

**12. Tham số ID kiểu Long nên tạo bằng Class nào?**

`Long.class`.

**13. Nếu query có hai parameter cùng kiểu BigDecimal, có phải dùng cùng object không?**

Không nếu chúng là hai giá trị logic khác nhau. Tạo `minPrice` và `maxPrice` riêng.

**14. Khi nào dùng lại cùng ParameterExpression ở nhiều nơi?**

Khi nhiều predicates cần chính **một giá trị logic**, chẳng hạn cùng mẫu keyword cho tên Product và Category.

**15. Vì sao không nên coi `ParameterExpression<List<Long>>` luôn portable cho IN?**

Vì generic collection vướng Java type erasure và việc bind collection-valued parameter có những giới hạn theo provider/phiên bản. Có thể tạo các parameter `Long` riêng.

**16. Có thể dùng ParameterExpression trong HAVING không?**

Có, ví dụ so sánh `COUNT(p) >= :minimumCount`.

**17. ParameterExpression trong subquery được bind ở đâu?**

Trên Query/TypedQuery thực thi truy vấn chứa subquery.

**18. `CriteriaUpdate` với parameter có tự tăng @Version và đồng bộ entity managed không?**

Không theo semantics managed update thông thường. Bulk update có giới hạn về version/lifecycle và có thể làm persistence context stale.

**19. `setFirstResult` và `setMaxResults` có phải ParameterExpression không?**

Không. Chúng là API phân trang của Query.

**20. ParameterExpression có tự ngăn người dùng truy cập dữ liệu tenant khác không?**

Không. Ứng dụng phải thêm predicate bảo mật bắt buộc và bind tenant ID đáng tin cậy.

**21. Nếu quên bind một parameter bắt buộc, điều gì xảy ra?**

Provider có thể ném lỗi khi thực thi. Query phải được bind đầy đủ trước khi lấy kết quả.

**22. Có nên chia sẻ một TypedQuery giữa các request để tiết kiệm tài nguyên không?**

Không. TypedQuery mutable và gắn với EntityManager; mỗi đơn vị công việc nên có binding/truy vấn phù hợp riêng.

**23. Dùng ParameterExpression có bảo đảm không có JPQL injection từ tên field động không?**

Không. Nó chỉ bind values; tên field động vẫn phải được whitelist và dựng như cấu trúc đáng tin.

**24. `CriteriaBuilder.literal(value)` có phải là parameter chờ setParameter không?**

Không. Nó tạo expression đại diện giá trị đã biết trong cây Criteria.

## 37. Tổng kết

**`ParameterExpression<T>` là công cụ then chốt để tách phần cấu trúc và phần giá trị trong Criteria API.** Ta xây entity root, joins, predicates, grouping và ordering bằng `CriteriaBuilder`/`CriteriaQuery`; đồng thời tạo các placeholder bằng `cb.parameter(Type.class, "name")`. Khi thực thi, `TypedQuery.setParameter(parameter, value)` truyền đúng giá trị cho từng placeholder mà không phải dựng lại điều kiện bằng nối chuỗi.

Để sử dụng tốt:

- **Dùng kiểu parameter tương ứng với kiểu thuộc tính**: `BigDecimal` cho giá, enum cho trạng thái, `Long` cho ID, `LocalDateTime` cho mốc thời gian.
- **Giữ parameter object gắn với cây query** và bind tất cả parameter thực sự được dùng.
- **Phân biệt cấu trúc với dữ liệu**: tên field, JOIN, sort direction, operator và optional predicate phải do code dựng; không dùng parameter để giả lập đoạn JPQL.
- **Xử lý null, LIKE và IN theo semantics riêng**: null-check bằng `isNull`, escape wildcard khi cần, và chú ý danh sách rỗng/giới hạn bind parameters.
- **Cân nhắc hiệu năng và bảo mật**: parameterization không tự tối ưu mọi SQL, không thay authorization, tenant isolation hay validation.
- **Nhớ giới hạn của bulk DML và transaction**: ParameterExpression chỉ bind giá trị, không biến CriteriaUpdate/Delete thành thao tác trên managed entity có đầy đủ cascade, callback và version checking.

Khi những nguyên tắc này được tuân thủ, Criteria API không chỉ giúp viết truy vấn động mà còn giúp **định nghĩa rõ phần nào của câu truy vấn do ứng dụng kiểm soát và phần nào là dữ liệu đầu vào thay đổi theo mỗi lần thực thi**. Đó là cơ sở để xây dựng repository JPA có tính bảo trì, rõ kiểu, dễ mở rộng và an toàn hơn.
