# Phân biệt ánh xạ entity được quản lý và dữ liệu kết quả độc lập

## 1. Vì sao cùng một câu SQL có thể tạo ra hai loại kết quả khác nhau?

Trong Jakarta Persistence (JPA), **Native SQL** cho phép thực thi câu SQL viết theo bảng, cột và cú pháp của hệ quản trị cơ sở dữ liệu. Tuy nhiên, **việc viết SQL là một chuyện; JPA diễn giải kết quả SQL thành loại object nào lại là chuyện khác**.

Xem hai lời gọi:

```java
Query mappedQuery = em.createNativeQuery(
    "SELECT p.* FROM products p WHERE p.id = ?1",
    Product.class
);

Query rawQuery = em.createNativeQuery(
    "SELECT p.id, p.sku, p.name FROM products p WHERE p.id = ?1"
);
```

Cả hai đều đọc từ bảng `products`, nhưng kết quả có ý nghĩa khác biệt:

- Với `Product.class`, JPA được yêu cầu **ánh xạ một hàng SQL thành entity `Product`**. Entity được trả về thuộc **persistence context** và có thể được quản lý (*managed*).
- Không khai báo ánh xạ entity, câu thứ hai thường trả **giá trị scalar** hoặc **`Object[]`** cho mỗi hàng. Chúng chỉ là dữ liệu độc lập, không trở thành một `Product` đang được JPA theo dõi.

Sự khác biệt rất lớn trong ứng dụng:

```text
                       SQL result set
                             |
               +-------------+--------------+
               |                            |
               v                            v
     Có khai báo Entity mapping?      Scalar / DTO projection?
               |                            |
               v                            v
         Managed entity                 Dữ liệu độc lập
         trong persistence context      String / Number / Object[]
               |                        record / DTO
               v                            |
      dirty checking, identity map          v
      lifecycle, flush/refresh          Không có entity lifecycle
```

Một câu `SELECT` có thể trả nhiều cột, nhưng **không có nghĩa JPA tự biết đó là một entity**. Ngược lại, kết quả native SQL đã được ánh xạ thành entity **không phải một DTO vô trạng thái chỉ vì xuất phát từ SQL tự viết**.

Bài này giải thích cách quyết định và nhận biết hai loại kết quả, cách dùng `createNativeQuery` và `@SqlResultSetMapping`, các hệ quả về persistence context, dirty checking, dữ liệu stale, transaction và cách thiết kế lớp đọc dữ liệu.

## 2. Nền tảng: managed entity và dữ liệu kết quả độc lập

### 2.1. Managed entity là gì?

Một entity đang **managed** khi **chính instance Java đó** được một persistence context của `EntityManager` theo dõi.

```java
Product product = em.find(Product.class, 10L);

if (product != null) {
    System.out.println(em.contains(product)); // true
}
```

Khi entity managed, provider JPA thường có trách nhiệm:

- Duy trì **identity map**: cùng entity identity trong cùng context tương ứng với một managed instance.
- Theo dõi trạng thái thay đổi (*dirty checking*) theo cơ chế của provider.
- Đồng bộ những thay đổi hợp lệ với database khi `flush` hoặc commit trong transaction phù hợp.
- Hỗ trợ các thao tác vòng đời như `refresh`, `detach`, `remove`.
- Áp dụng optimistic locking khi mapping có `@Version` và thao tác cần thiết.

Managed **không** đồng nghĩa database vừa được truy vấn ở lần truy cập cuối, cũng **không** đồng nghĩa dữ liệu đã commit.

### 2.2. Dữ liệu kết quả độc lập là gì?

Kết quả độc lập có thể là:

```java
String sku = "KB-001";
Long count = 12L;
Object[] row = {10L, "KB-001", "Keyboard"};
ProductSummary summary = new ProductSummary(
    "KB-001", "Keyboard", new BigDecimal("890000.00")
);
```

Trong bốn ví dụ này, các giá trị **không phải managed entity `Product`**. Chúng có thể được tạo từ câu SQL nhưng JPA không tự đăng ký chúng trong identity map, không dirty-check chúng và không ghi những thay đổi trên DTO trở lại bảng.

Một `record` hay một DTO chứa `id`, `sku` và `name` đầy đủ **vẫn là DTO**. Tên field giống entity không biến nó thành entity.

### 2.3. Phân biệt bằng bảng

| Tiêu chí | Entity được ánh xạ và managed | Scalar/DTO độc lập |
|---|---|---|
| Ví dụ | `Product` từ native query có `Product.class` | `String`, `Number`, `Object[]`, `ProductSummary` |
| Có trong persistence context? | Có, nếu query được thực thi hợp lệ trong context đó | Không, trừ khi bên trong cấu trúc kết quả có chứa riêng một managed entity |
| `em.contains(value)` | Có thể trả `true` với entity managed | Không áp dụng cho DTO/scalar; không dùng để kiểm tra |
| Dirty checking | Có cho field được quản lý | Không |
| Thay đổi field rồi commit | Có thể tạo UPDATE khi đúng transaction | Không tự tạo UPDATE |
| Identity map | Cùng khóa/entity trong context nhận cùng instance | Mỗi lần truy vấn có thể tạo object mới, không có identity guarantee |
| `refresh` | Dùng được với managed entity hợp lệ | Không dùng cho DTO/scalar |
| Phù hợp | Cần thao tác domain/lifecycle trên entity | Báo cáo, dashboard, xuất dữ liệu, API read model |
| Mức phụ thuộc mapping | Cần đủ dữ liệu để tái tạo entity đúng mapping | Chỉ cần những cột/biểu thức đầu ra |

**Điểm mấu chốt:** cách JPA **ánh xạ result set** mới quyết định vòng đời của kết quả, không phải việc câu SQL có chữ `SELECT` hay trả tên cột giống entity.

## 3. Entity mẫu và schema dùng trong bài

### 3.1. Entity `Product`

```java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 64)
    private String sku;

    @Column(name = "product_name", nullable = false, length = 160)
    private String name;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    @Version
    @Column(name = "row_version", nullable = false)
    private long version;

    protected Product() {
    }

    public Product(String sku, String name, BigDecimal unitPrice) {
        this.sku = Objects.requireNonNull(sku);
        rename(name);
        changePrice(unitPrice);
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

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = newName;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá không hợp lệ");
        }
        this.unitPrice = newPrice;
    }
}
```

Entity có:

- Khóa chính `id`.
- Các thuộc tính được ánh xạ tới tên cột SQL.
- `@Version` để JPA thực hiện optimistic locking.
- Constructor không tham số cho JPA.
- Hai thao tác domain `rename` và `changePrice`.

### 3.2. Schema PostgreSQL minh họa

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    product_name VARCHAR(160) NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL
        CHECK (unit_price >= 0),
    row_version BIGINT NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

CREATE INDEX ix_order_lines_product_id
    ON order_lines(product_id);
```

Bảng `order_lines` phục vụ ví dụ báo cáo số lần sản phẩm xuất hiện trong đơn hàng. Ở bài này, không cần khai báo một entity `OrderLine` để thực thi câu native SQL đọc trực tiếp bảng `order_lines`.

Dữ liệu giả định:

| ID | SKU | product_name | unit_price | row_version |
|---:|---|---|---:|---:|
| 10 | KB-001 | Bàn phím cơ | 890000.00 | 2 |
| 11 | MS-002 | Chuột không dây | 390000.00 | 0 |
| 12 | USB-003 | USB 64GB | 160000.00 | 4 |

Vì `unitPrice` là `BigDecimal`, phép so sánh tiền tệ trong Java nên dùng `compareTo` hoặc quy tắc chuẩn hóa scale phù hợp, không suy ra `BigDecimal.equals` luôn cho true khi scale khác nhau.

## 4. Native SQL khác JPQL ở đâu?

### 4.1. Câu JPQL

```jpql
SELECT p
FROM Product p
WHERE p.id = :id
```

Đây là truy vấn **entity `Product`**, viết theo tên entity và thuộc tính Java. Provider thường trả một managed entity.

### 4.2. Câu Native SQL ánh xạ entity

```java
Query query = em.createNativeQuery(
    "SELECT p.* FROM products p WHERE p.id = ?1",
    Product.class
);
```

Câu SQL dùng **tên bảng `products`** và cột **`id`**. Đối số `Product.class` yêu cầu JPA ánh xạ kết quả thành `Product`.

### 4.3. Câu Native SQL chỉ lấy các cột

```java
Query query = em.createNativeQuery(
    "SELECT p.sku, p.product_name " +
    "FROM products p WHERE p.id = ?1"
);
```

Không có entity result mapping; các cột được trả như giá trị độc lập. Chúng **không được tự lắp lại thành managed `Product`**.

### 4.4. Cách dùng `Query`

API JPA chuẩn:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.Query;

Query nativeQuery = em.createNativeQuery(
    "SELECT p.* FROM products p WHERE p.id = ?1",
    Product.class
);

nativeQuery.setParameter(1, 10L);

Product product = (Product) nativeQuery.getSingleResult();
```

Cần lưu ý `createNativeQuery(...)` có các overload trả về `Query`, nên cast kết quả phù hợp với mapping. Không tự giả định mọi phương thức native query trả `TypedQuery<Product>` giống `em.createQuery(jpql, Product.class)`.

## 5. Cách 1: `createNativeQuery(sql, Product.class)` trả managed entity

### 5.1. Ví dụ tải Product

```java
Query query = em.createNativeQuery(
    "SELECT p.* FROM products p WHERE p.id = :id",
    Product.class
);

query.setParameter("id", 10L);

Product product = (Product) query.getSingleResult();

System.out.println(product.getSku());       // KB-001
System.out.println(product.getUnitPrice()); // 890000.00
System.out.println(em.contains(product));   // true
```

Ví dụ này dùng named parameter trong native query như khả năng thường được các provider hỗ trợ. **Để đảm bảo portability theo JPA đối với native SQL, ưu tiên positional parameter** nếu không muốn phụ thuộc cách provider xử lý named native parameters:

```java
Query query = em.createNativeQuery(
    "SELECT p.* FROM products p WHERE p.id = ?1",
    Product.class
);
query.setParameter(1, 10L);
```

Khi không tìm thấy bản ghi, `getSingleResult()` có thể ném `NoResultException`; nếu query bất ngờ có nhiều kết quả, có thể ném `NonUniqueResultException`. Đối với khóa chính đơn, kết quả thường là 0 hoặc 1 hàng nếu dữ liệu hợp lệ.

### 5.2. Vì sao entity trả về managed?

Vì truy vấn đã yêu cầu ánh xạ tới **loại entity được JPA biết**. Provider dùng metadata của `Product`:

- `@Entity`/`@Table` xác định loại và bảng.
- `@Id` xác định persistent identity.
- `@Column` xác định trường tương ứng các cột.
- `@Version` xác định version dùng cho optimistic locking.
- Các association, inheritance và converter liên quan cũng thuộc mapping entity.

Kết quả được hòa vào persistence context hiện tại. Nếu trong context đã có Product ID 10, provider phải duy trì tính nhất quán về entity identity, thay vì tự tạo thêm một managed object khác cho cùng persistent identity.

### 5.3. Native entity vẫn được dirty checking

Giả sử đang chạy một transaction `RESOURCE_LOCAL` hợp lệ:

```java
em.getTransaction().begin();

try {
    Product product = (Product) em.createNativeQuery(
            "SELECT p.* FROM products p WHERE p.id = ?1",
            Product.class
        )
        .setParameter(1, 10L)
        .getSingleResult();

    product.rename("Bàn phím cơ phiên bản mới");

    // Không cần em.merge(product) vì product đã managed.
    em.flush();

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
```

Thay đổi trên `product` có thể dẫn tới SQL `UPDATE` do dirty checking tại flush/commit.

**Đây là khác biệt quan trọng nhất với DTO:** `Product` từ native entity mapping có vòng đời JPA như entity tải bằng `find` hoặc JPQL entity query. Nó không phải một “bản chụp chỉ đọc” chỉ vì dùng native SQL.

### 5.4. Không cần persist/merge lại managed entity

```java
Product product = (Product) em.createNativeQuery(
        "SELECT p.* FROM products p WHERE p.id = ?1",
        Product.class
    )
    .setParameter(1, 10L)
    .getSingleResult();

if (em.contains(product)) {
    product.changePrice(new BigDecimal("950000.00"));
}
```

Đừng gọi `em.persist(product)` với ý định “lưu lại bản tải từ SQL”; entity đã managed. `em.merge(product)` cũng không cần thiết chỉ để cập nhật thuộc tính của managed entity.

Nếu muốn cập nhật theo một command nghiệp vụ, tải managed entity trong transaction và gọi method domain phù hợp, kết hợp validation/authorization.

## 6. Identity map: cùng ID có thể là cùng một Java object

### 6.1. So sánh `find` và native entity query

```java
Product byFind = em.find(Product.class, 10L);

Product byNative = (Product) em.createNativeQuery(
        "SELECT p.* FROM products p WHERE p.id = ?1",
        Product.class
    )
    .setParameter(1, 10L)
    .getSingleResult();

System.out.println(byFind == byNative);         // true
System.out.println(em.contains(byNative));      // true
```

Trong cùng persistence context, hai đường tải entity cùng persistent identity được liên kết với **cùng managed instance**. Đây không phải hai bản độc lập để đem so sánh trạng thái database.

### 6.2. Vì sao một SELECT native mới vẫn có thể trả field cũ?

Giả sử:

```java
Product product = em.find(Product.class, 10L);

product.rename("Tên mới đang ở trong bộ nhớ");

Product again = (Product) em.createNativeQuery(
        "SELECT p.* FROM products p WHERE p.id = ?1",
        Product.class
    )
    .setParameter(1, 10L)
    .getSingleResult();

System.out.println(product == again); // true
System.out.println(again.getName());  // Có thể vẫn là tên trong context.
```

Dù SQL có được thực thi để xác định hàng, **native entity mapping không nên được dùng như cam kết tự động refresh mọi thuộc tính** của entity đã managed. Provider phải giữ identity map và có thể không ghi đè giá trị in-memory bằng dữ liệu nhận từ result set.

Cũng có thể câu query gây flush trước khi chạy, tùy flush mode, provider và các điều kiện đồng bộ. Vì thế, thấy tên mới sau query không chứng minh một SELECT độc lập vừa xác nhận được dữ liệu tại database.

### 6.3. Cần giá trị database mới nhất thì làm gì?

Nếu `product` đang managed, có thể cân nhắc:

```java
em.flush();             // Đồng bộ pending changes trước nếu cần.
em.refresh(product);    // Đọc lại trạng thái DB cho managed entity.
```

Hoặc sau transaction commit thành công:

1. Đóng hoặc kết thúc context đang quản lý entity.
2. Mở `EntityManager` và transaction đọc mới.
3. Truy vấn lại với cache policy phù hợp.
4. Nếu cần kiểm tra trực tiếp bảng nguồn, đọc scalar SQL/JDBC.

**`refresh` chỉ phản ánh dữ liệu mà transaction hiện tại nhìn thấy**; nó chưa chứng minh commit. `clear` hoặc `detach` loại entity khỏi L1 nhưng có thể làm mất pending changes chưa flush; shared L2 cache vẫn cần cân nhắc.

## 7. Khi ánh xạ entity, nên SELECT đủ dữ liệu

### 7.1. Không nhầm projection thiếu cột với một entity hoàn chỉnh

Câu SQL:

```sql
SELECT id, sku
FROM products
WHERE id = 10;
```

có thể hợp lệ về SQL, nhưng:

```java
em.createNativeQuery(
    "SELECT id, sku FROM products WHERE id = ?1",
    Product.class
);
```

**không phải cách portable để yêu cầu JPA tạo managed `Product`** khi entity còn có `name`, `unitPrice` và `version`.

Khi ánh xạ entity, provider cần những cột thích hợp cho metadata của loại entity. Thiếu cột có thể gây exception, tạo object không đầy đủ hoặc hành vi phụ thuộc provider. Những field `@Version`, discriminator của inheritance, khóa ngoại và giá trị cần thiết cho mapping càng khiến partial entity projection khó tin cậy.

### 7.2. Lựa chọn rõ nghĩa

Nếu cần entity managed:

```sql
SELECT p.*
FROM products p
WHERE p.id = ?
```

Nếu chỉ cần hai cột:

```sql
SELECT p.id, p.sku
FROM products p
WHERE p.id = ?
```

và ánh xạ kết quả vào DTO/scalar.

### 7.3. `SELECT *` có ưu và nhược điểm

`SELECT p.*` tiện khi truy vấn chỉ một bảng có cấu trúc khớp entity, nhưng cần chú ý:

- Join nhiều bảng và `SELECT *` có thể tạo **tên cột trùng** (`id`, `name`), gây mơ hồ khi ORM ánh xạ.
- Chỉ nên chọn **cột của entity cần map**, ví dụ `p.*` thay vì `*` qua nhiều bảng.
- Database thay đổi schema có thể thêm cột mới; metadata JPA cũng cần được quản lý nhất quán.
- Với query native nhiều entity, có thể cần alias/`@FieldResult` cụ thể.
- Với báo cáo chỉ cần vài cột, `SELECT *` truyền dữ liệu thừa và không thể hiện output contract rõ ràng.

Không có quy tắc “mọi native entity query bắt buộc viết `*`”. Điều cần thiết là **result set chứa các cột và alias phù hợp với entity mapping**.

## 8. Cách 2: Native SQL không khai báo entity mapping trả dữ liệu thô

### 8.1. Một cột scalar

```java
Object raw = em.createNativeQuery(
        "SELECT p.product_name FROM products p WHERE p.id = ?1"
    )
    .setParameter(1, 10L)
    .getSingleResult();

String name = (String) raw;
```

Query chỉ trả một cột `product_name`, nên giá trị kết quả thường là một `String`. Nó **không phải một `Product`**. Thay đổi biến `name` không có nghĩa JPA sẽ cập nhật bảng `products`.

### 8.2. Nhiều cột: `Object[]`

```java
Object raw = em.createNativeQuery(
        "SELECT p.id, p.sku, p.unit_price " +
        "FROM products p WHERE p.id = ?1"
    )
    .setParameter(1, 10L)
    .getSingleResult();

Object[] row = (Object[]) raw;

Number idNumber = (Number) row[0];
Long id = idNumber.longValue();

String sku = (String) row[1];
BigDecimal price = (BigDecimal) row[2];
```

Ý nghĩa:

- `row[0]` tương ứng `p.id`.
- `row[1]` tương ứng `p.sku`.
- `row[2]` tương ứng `p.unit_price`.
- Thứ tự được lấy từ **thứ tự các cột trong SELECT**, không phải tên field của `Product`.

Với raw native query, kiểu số cụ thể có thể tùy JDBC driver/provider và SQL expression. Ví dụ khóa kiểu BIGINT thường có thể được trả dưới dạng `Long`, nhưng khi muốn xử lý các dạng numeric khác nhau nên cân nhắc đọc qua `Number` thay vì ép mọi trường hợp thành `Long`.

### 8.3. Truy vấn nhiều hàng

```java
@SuppressWarnings("unchecked")
List<Object[]> rows = em.createNativeQuery(
        "SELECT p.id, p.sku, p.product_name " +
        "FROM products p " +
        "WHERE p.unit_price >= ?1 " +
        "ORDER BY p.id"
    )
    .setParameter(1, new BigDecimal("300000.00"))
    .getResultList();

for (Object[] row : rows) {
    long id = ((Number) row[0]).longValue();
    String sku = (String) row[1];
    String name = (String) row[2];

    System.out.printf("%d - %s - %s%n", id, sku, name);
}
```

Dạng `Object[]` nhanh để thử hoặc xử lý dữ liệu nội bộ đơn giản, nhưng dễ nhầm vị trí và kiểu nếu query thay đổi.

### 8.4. Một cột và nhiều cột có shape khác nhau

Không nên giả định mọi native result row đều là `Object[]`:

```java
Object oneColumn =
    em.createNativeQuery("SELECT COUNT(*) FROM products")
      .getSingleResult();

Object manyColumns =
    em.createNativeQuery(
        "SELECT id, sku FROM products WHERE id = ?1"
    )
    .setParameter(1, 10L)
    .getSingleResult();
```

Một cột thường trả scalar, nhiều cột thường trả `Object[]`. Với result-set mapping tường minh hoặc extension của provider, shape có thể khác theo mapping được cấu hình.

### 8.5. `COUNT(*)` và kiểu numeric

```java
Object rawCount = em.createNativeQuery(
    "SELECT COUNT(*) FROM products"
).getSingleResult();

long count = ((Number) rawCount).longValue();
```

Một số môi trường có thể trả `Long`, một số trả loại `Number` khác. Không ép cứng thành `Integer` rồi ngầm giả định mọi driver ánh xạ giống nhau.

Nếu báo cáo cần độ chính xác rất lớn hoặc aggregate DECIMAL, dùng kiểu phù hợp và xem xét `@ColumnResult(type=...)` khi có mapping tường minh.

## 9. Vì sao dữ liệu thô không được dirty checking?

### 9.1. Object[] chỉ giữ giá trị

```java
Object[] row = (Object[]) em.createNativeQuery(
        "SELECT p.id, p.product_name " +
        "FROM products p WHERE p.id = ?1"
    )
    .setParameter(1, 10L)
    .getSingleResult();

row[1] = "Tên mới trong Object[]";
```

Đây là thao tác thay phần tử mảng Java. Không có mapped entity `Product` nào được cập nhật, vì vậy `flush`/commit **không tự sinh UPDATE** từ thay đổi này.

### 9.2. DTO cũng không khác

```java
public record ProductSummary(
    Long id,
    String sku,
    String name,
    BigDecimal unitPrice
) {}
```

`ProductSummary` là data carrier. Dù DTO có đủ các trường và ID giống `Product`, JPA **không quản lý nó như entity**.

Nếu muốn cập nhật Product từ dữ liệu DTO, service nên tải Product managed theo ID và áp dụng thay đổi có kiểm soát:

```java
Product managed = em.find(Product.class, summary.id());

if (managed == null) {
    throw new IllegalArgumentException("Product không tồn tại");
}

managed.rename(summary.name());
```

Ví dụ phải nằm trong transaction phù hợp, và cần kiểm tra quyền/validation. Đừng cố `em.merge(summary)`: `merge` nhận entity, không phải DTO tự do.

### 9.3. DTO là lựa chọn tốt cho read model

Đối với truy vấn chỉ đọc phục vụ:

- Danh sách sản phẩm cho frontend.
- Báo cáo tổng doanh thu.
- Dashboard có aggregate.
- Xuất CSV/JSON.
- Truy vấn dùng window function, CTE, cột tính toán.
- Kết hợp dữ liệu từ nhiều bảng mà không tương ứng một entity đơn lẻ.

thì dữ liệu độc lập thường **phù hợp hơn** việc cố ép output vào một managed entity.

## 10. Chuyển Object[] thành DTO ở tầng Java

### 10.1. Record read model

```java
package com.example.catalog.readmodel;

import java.math.BigDecimal;

public record ProductSummary(
    Long id,
    String sku,
    String name,
    BigDecimal unitPrice
) {}
```

### 10.2. Chuyển thủ công

```java
List<ProductSummary> results = new ArrayList<>();

@SuppressWarnings("unchecked")
List<Object[]> rows = em.createNativeQuery(
        "SELECT id, sku, product_name, unit_price " +
        "FROM products " +
        "WHERE unit_price BETWEEN ?1 AND ?2 " +
        "ORDER BY id"
    )
    .setParameter(1, new BigDecimal("100000.00"))
    .setParameter(2, new BigDecimal("900000.00"))
    .getResultList();

for (Object[] row : rows) {
    ProductSummary summary = new ProductSummary(
        ((Number) row[0]).longValue(),
        (String) row[1],
        (String) row[2],
        (BigDecimal) row[3]
    );

    results.add(summary);
}
```

Cần import `java.util.List` và `java.util.ArrayList`. Đây là cách rõ ràng nhưng dễ bị lỗi nếu thay đổi thứ tự cột của SELECT mà quên sửa index.

### 10.3. Ưu và nhược điểm

Ưu điểm:

- Không phụ thuộc toàn bộ mapping entity.
- Có thể đọc đúng những cột cần dùng.
- DTO được thiết kế cho response và không chịu dirty checking.
- Không lo sửa DTO làm JPA tự ghi thay đổi.

Nhược điểm:

- Mapping bằng vị trí `row[n]` khó bảo trì.
- Cần xử lý kiểu numeric/date/null của JDBC.
- Có thể sinh lỗi runtime nếu ép kiểu sai.
- Dễ lặp code mapping ở nhiều nơi.

Khi số query tăng, cân nhắc `@SqlResultSetMapping` với `@ConstructorResult` hoặc một mapper được quản lý rõ ràng.

## 11. `@SqlResultSetMapping`: khai báo cách diễn giải kết quả native SQL

### 11.1. Vì sao cần result-set mapping?

Native query có thể trả:

- Một entity.
- Một tập cột scalar.
- Một DTO.
- Kết hợp một entity với các cột tính toán.

JPA cho phép khai báo **`@SqlResultSetMapping`** để mô tả cách đưa các cột SQL vào đối tượng Java.

Các thành phần chính:

| Thành phần | Công dụng |
|---|---|
| `@EntityResult` | Ánh xạ cột SQL thành entity JPA |
| `@FieldResult` | Gắn tên thuộc tính entity với alias cột cụ thể |
| `@ColumnResult` | Ánh xạ một cột/biểu thức scalar |
| `@ConstructorResult` | Gọi constructor của một lớp DTO từ tập cột |
| `@SqlResultSetMapping` | Đặt tên cho một cách mapping result set |

Các mapping thường được khai báo ở lớp entity hoặc một lớp được JPA quét như metadata của persistence unit. Ví dụ sau giả định annotation được **đặt trên `Product`**.

### 11.2. Đặt tên mapping và sử dụng

```java
@SqlResultSetMapping(
    name = "ProductNameColumns",
    columns = {
        @ColumnResult(name = "sku", type = String.class),
        @ColumnResult(name = "product_name", type = String.class)
    }
)
@Entity
@Table(name = "products")
public class Product {
    // ... các trường/method đã trình bày ...
}
```

Gọi:

```java
Query query = em.createNativeQuery(
    "SELECT sku, product_name FROM products WHERE id = ?1",
    "ProductNameColumns"
);

query.setParameter(1, 10L);

Object[] columns = (Object[]) query.getSingleResult();

String sku = (String) columns[0];
String name = (String) columns[1];
```

Mapping `ProductNameColumns` chỉ khai báo **hai ColumnResult**. Dù annotation được đặt trên `Product`, kết quả **không trở thành managed `Product`**: nó vẫn là hai giá trị scalar.

**Đặt annotation mapping trên entity không đồng nghĩa mapping đó trả entity.** Cần xem **thành phần `entities`, `columns` hay `classes`** của mapping.

## 12. `@EntityResult`: ánh xạ bằng entity metadata

### 12.1. Khi SQL dùng tên cột chuẩn

Nếu câu native query trả các cột đúng với metadata `Product`, có thể dùng:

```java
@SqlResultSetMapping(
    name = "MappedProduct",
    entities = @EntityResult(entityClass = Product.class)
)
```

Thực thi:

```java
Product product = (Product) em.createNativeQuery(
        "SELECT p.* FROM products p WHERE p.id = ?1",
        "MappedProduct"
    )
    .setParameter(1, 10L)
    .getSingleResult();

System.out.println(em.contains(product)); // true
```

Mapping khai báo `EntityResult`, do đó entity tham gia persistence context giống trường hợp `createNativeQuery(sql, Product.class)`.

### 12.2. Khi SQL đặt alias khác tên cột trong mapping

Giả sử báo cáo SQL yêu cầu đổi alias:

```sql
SELECT
    p.id AS pid,
    p.sku AS psku,
    p.product_name AS pname,
    p.unit_price AS price_value,
    p.row_version AS version_value
FROM products p
WHERE p.id = ?;
```

Cần chỉ ra alias tương ứng với thuộc tính entity:

```java
@SqlResultSetMapping(
    name = "AliasedProductEntity",
    entities = @EntityResult(
        entityClass = Product.class,
        fields = {
            @FieldResult(name = "id", column = "pid"),
            @FieldResult(name = "sku", column = "psku"),
            @FieldResult(name = "name", column = "pname"),
            @FieldResult(name = "unitPrice", column = "price_value"),
            @FieldResult(name = "version", column = "version_value")
        }
    )
)
```

`@FieldResult.name` sử dụng **tên thuộc tính Java**, còn `@FieldResult.column` sử dụng **alias trong SQL result set**.

Để chạy:

```java
Product product = (Product) em.createNativeQuery(
        "SELECT p.id AS pid, p.sku AS psku, " +
        "p.product_name AS pname, " +
        "p.unit_price AS price_value, " +
        "p.row_version AS version_value " +
        "FROM products p WHERE p.id = ?1",
        "AliasedProductEntity"
    )
    .setParameter(1, 10L)
    .getSingleResult();
```

**Không hiểu `FieldResult` là nơi khai báo getter mới**. Nó chỉ mô tả ánh xạ giữa tên field của entity đã được cấu hình và alias của cột SQL.

### 12.3. EntityResult vẫn là managed entity

Ngay cả khi `FieldResult` dùng nhiều alias, kết quả vẫn là `Product` thuộc persistence context. Có thể có dirty checking, optimistic locking và identity map. Không nên dùng `EntityResult` chỉ để “dễ ánh xạ cột” nếu thực ra cần read-only DTO độc lập.

### 12.4. Multiple result mappings

Một entity có thể khai báo nhiều named mapping bằng container `@SqlResultSetMappings`:

```java
@SqlResultSetMappings({
    @SqlResultSetMapping(
        name = "MappedProduct",
        entities = @EntityResult(entityClass = Product.class)
    ),
    @SqlResultSetMapping(
        name = "ProductNameColumns",
        columns = {
            @ColumnResult(name = "sku", type = String.class),
            @ColumnResult(name = "product_name", type = String.class)
        }
    )
})
@Entity
public class Product {
    // ...
}
```

Ví dụ này cho thấy cách tổ chức khi có nhiều mapping; không áp dụng nguyên văn `@Entity` hai lần nếu đang thêm annotation vào lớp Product đã được khai báo ở phần trước.

## 13. `@ConstructorResult`: tạo DTO độc lập

### 13.1. DTO cho báo cáo số dòng bán

Giả sử muốn trả mã SKU và **số dòng OrderLine** tham chiếu sản phẩm.

```java
package com.example.catalog.readmodel;

public record ProductSalesSummary(
    String sku,
    Long orderLineCount
) {}
```

DTO không được đánh dấu `@Entity`.

### 13.2. Khai báo mapping

Trên entity được JPA nhận diện, khai báo:

```java
@SqlResultSetMapping(
    name = "ProductSalesSummaryMapping",
    classes = @ConstructorResult(
        targetClass = ProductSalesSummary.class,
        columns = {
            @ColumnResult(name = "sku", type = String.class),
            @ColumnResult(name = "order_line_count", type = Long.class)
        }
    )
)
```

Thứ tự các `@ColumnResult` **phải khớp thứ tự constructor** của record:

```java
ProductSalesSummary(String sku, Long orderLineCount)
```

Tên alias phải khớp với các cột SELECT được trả, không phải tự suy ra từ tên thành viên Java.

### 13.3. Truy vấn native tương ứng

```java
@SuppressWarnings("unchecked")
List<ProductSalesSummary> reports = em.createNativeQuery(
        "SELECT p.sku AS sku, " +
        "COUNT(ol.id) AS order_line_count " +
        "FROM products p " +
        "LEFT JOIN order_lines ol ON ol.product_id = p.id " +
        "GROUP BY p.id, p.sku " +
        "ORDER BY p.sku",
        "ProductSalesSummaryMapping"
    )
    .getResultList();

for (ProductSalesSummary report : reports) {
    System.out.printf(
        "%s: %d dòng%n",
        report.sku(),
        report.orderLineCount()
    );
}
```

Mỗi hàng là một `ProductSalesSummary` độc lập. Không có một `Product` managed được tạo chỉ vì SQL truy vấn bảng products.

### 13.4. Vì sao dùng COUNT thay vì SUM cho ví dụ đơn giản?

`COUNT(ol.id)` đếm số dòng order line, và type `Long` là một lựa chọn thường phù hợp khi chỉ định `@ColumnResult(type=Long.class)`.

Nếu nghiệp vụ muốn **tổng số lượng sản phẩm bán được**, cần dùng `SUM(ol.quantity)`, chú ý kiểu numeric trả về, giá trị null ở sản phẩm không có OrderLine và việc dùng `COALESCE` phù hợp. Số dòng đơn hàng và tổng số lượng là **hai đại lượng khác nhau**.

### 13.5. ConstructorResult không có dirty checking

```java
ProductSalesSummary report = reports.get(0);
```

Đây là một record immutable do constructor tạo ra. Không có setter để sửa, và kể cả dùng DTO mutable thì JPA cũng không theo dõi biến đổi của DTO.

Khi `@ConstructorResult.targetClass` trỏ tới **một entity class** thay vì DTO, chuẩn JPA có quy tắc trạng thái riêng (new hoặc detached tùy có khóa định danh trong constructor result). Không nên coi constructor mapping entity là cách thay thế an toàn cho `@EntityResult` để lấy managed entity. **Với read model, dùng class/record không phải entity sẽ rõ ràng hơn.**

## 14. `@ColumnResult`: khi chỉ cần scalar có tên/kiểu rõ ràng

### 14.1. Một scalar

```java
@SqlResultSetMapping(
    name = "ProductCountScalar",
    columns = @ColumnResult(
        name = "product_count",
        type = Long.class
    )
)
```

Truy vấn:

```java
Number countValue = (Number) em.createNativeQuery(
        "SELECT COUNT(*) AS product_count FROM products",
        "ProductCountScalar"
    )
    .getSingleResult();

long count = countValue.longValue();
```

Một `ColumnResult` thường tạo một giá trị scalar, không có entity lifecycle.

### 14.2. Nhiều scalar

```java
@SqlResultSetMapping(
    name = "ProductIdAndSku",
    columns = {
        @ColumnResult(name = "id_value", type = Long.class),
        @ColumnResult(name = "sku_value", type = String.class)
    }
)
```

```java
Object[] values = (Object[]) em.createNativeQuery(
        "SELECT id AS id_value, sku AS sku_value " +
        "FROM products WHERE id = ?1",
        "ProductIdAndSku"
    )
    .setParameter(1, 10L)
    .getSingleResult();
```

Không phải cứ dùng `@SqlResultSetMapping` thì JPA sẽ tạo entity; **`ColumnResult` chỉ mang giá trị của cột hoặc biểu thức SQL**.

### 14.3. SQL aggregate và kiểu đầu ra

Khi dùng các biểu thức như `COUNT(*)`, `AVG(...)`, `SUM(...)`, `ROW_NUMBER()` hoặc `CAST(...)`, kiểu do database/driver trả về có thể khác kiểu của thuộc tính entity gốc.

`@ColumnResult(type=...)` giúp chỉ định kiểu mong muốn theo cơ chế mapping JPA, nhưng phải dùng một kiểu **phù hợp với giá trị SQL và khả năng chuyển đổi của provider**. Không thể mong ép một chuỗi tùy ý thành `Long` chỉ bằng một annotation mà không có quy tắc chuyển đổi hợp lệ.

## 15. Kết hợp entity managed với scalar trong cùng một hàng

### 15.1. Nhu cầu thực tế

Một màn hình có thể cần:

- Entity `Product` để thao tác nghiệp vụ.
- Số dòng `OrderLine` liên quan để hiển thị.

Thay vì hai query riêng, có thể dùng mapping kết hợp:

```java
@SqlResultSetMapping(
    name = "ProductAndOrderLineCount",
    entities = @EntityResult(entityClass = Product.class),
    columns = @ColumnResult(
        name = "line_count",
        type = Long.class
    )
)
```

### 15.2. SQL và kết quả

```java
@SuppressWarnings("unchecked")
List<Object[]> rows = em.createNativeQuery(
        "SELECT p.*, (" +
        "    SELECT COUNT(*) FROM order_lines ol " +
        "    WHERE ol.product_id = p.id" +
        ") AS line_count " +
        "FROM products p ORDER BY p.id",
        "ProductAndOrderLineCount"
    )
    .getResultList();

for (Object[] row : rows) {
    Product product = (Product) row[0];
    Long lineCount = (Long) row[1];

    System.out.println(em.contains(product)); // true
    System.out.println(product.getSku() + ": " + lineCount);
}
```

Đây là kiểu kết quả **hỗn hợp**:

```text
Object[] row
   |
   +--- [0] Product              ---> managed entity
   |
   +--- [1] Long lineCount       ---> scalar độc lập
```

Không được nói rằng **toàn bộ `Object[]` là managed**, cũng không được nói rằng **Product bên trong `Object[]` không managed**. Mỗi thành phần mang semantics riêng theo `@EntityResult` và `@ColumnResult`.

### 15.3. Khi nào nên tách thành DTO hoàn toàn?

Nếu màn hình chỉ đọc `sku`, `name` và `lineCount`, việc trả Product managed có thể không cần thiết. Một `ProductWithCount` record được tạo bằng `ConstructorResult` sẽ đơn giản hơn:

- Chỉ tải đúng cột cần hiển thị.
- Không làm tăng số entity managed trong context.
- Tránh vô tình sửa entity trong tầng trình bày.
- Output contract dễ chuyển sang JSON.

Ngược lại, nếu service tiếp tục thực hiện logic thay đổi Product **trong cùng transaction**, việc có managed entity có thể phù hợp. Chọn theo mục đích, không theo thói quen mapping.

## 16. Native JOIN nhiều entity và alias trùng nhau

### 16.1. Lỗi thường gặp với SELECT *

Giả sử hai bảng cùng có `id` và `name`:

```sql
SELECT *
FROM products p
JOIN categories c ON c.id = p.category_id;
```

Result set có thể có hai cột `id`, hai cột `name` và các alias không đủ phân biệt. Nếu yêu cầu ánh xạ entity bằng native query, provider có thể báo lỗi alias trùng hoặc nhận sai metadata.

Cách tiếp cận:

```sql
SELECT p.*
FROM products p
JOIN categories c ON c.id = p.category_id
WHERE c.enabled = TRUE;
```

Nếu chỉ muốn trả **Product**, vẫn có thể dùng JOIN để **lọc** nhưng chỉ chọn các cột `p.*` để ánh xạ Product.

### 16.2. Hai entity cùng nằm trong một hàng kết quả

Khi thực sự cần cả Product và Category, có thể xây result-set mapping gồm **hai `EntityResult`**, với alias/`FieldResult` tách biệt cho các cột hai loại entity.

Khi đó, mỗi hàng có thể là `Object[]` gồm hai entity managed, nhưng số hàng phụ thuộc multiplicity của JOIN. Cần ánh xạ đầy đủ các cột định danh và các field quan trọng của cả hai entity, đặc biệt nếu có association, version hoặc inheritance.

Vì mapping nhiều entity dễ phức tạp và phụ thuộc provider/schema, nếu chỉ phục vụ read model, một DTO kết hợp cột cần dùng thường dễ duy trì hơn.

### 16.3. JOIN 1-n có thể nhân bản entity ở result list

```sql
SELECT p.*
FROM products p
JOIN order_lines ol ON ol.product_id = p.id;
```

Nếu Product ID 10 xuất hiện ở ba OrderLine, result set SQL có ba hàng tương ứng Product đó. Khi ánh xạ bằng `Product.class`, persistence context vẫn giữ **cùng managed Product instance cho ID 10**, nhưng danh sách kết quả có thể chứa tham chiếu lặp theo các hàng SQL.

Không mặc định rằng `List<Product>` tự loại trùng theo ID. Nếu cần Product không lặp, hãy chọn SQL `DISTINCT` hoặc thiết kế `EXISTS`:

```sql
SELECT p.*
FROM products p
WHERE EXISTS (
    SELECT 1
    FROM order_lines ol
    WHERE ol.product_id = p.id
);
```

**Identity map giải quyết duy nhất instance managed, không đồng nghĩa khử trùng các hàng logic của câu query.**

## 17. Native SQL trên object đã có trong persistence context

### 17.1. Managed entity có thể giữ state cũ

Giả sử:

```java
Product product = em.find(Product.class, 10L);
String before = product.getName();
```

Sau đó một SQL khác cập nhật hàng trực tiếp (có thể do ứng dụng khác, trigger hoặc một native UPDATE). `product` vẫn là một instance managed, nhưng provider **không chắc tự biết** có thay đổi ngoài đường dirty checking.

Khi gọi native entity SELECT:

```java
Product again = (Product) em.createNativeQuery(
        "SELECT p.* FROM products p WHERE p.id = ?1",
        Product.class
    )
    .setParameter(1, 10L)
    .getSingleResult();
```

`again` có thể vẫn là `product`. Native entity query không phải cam kết reload một snapshot mới, bởi context cần bảo vệ entity identity và trạng thái đã được quản lý.

### 17.2. Native scalar SELECT tách khỏi entity state

Nếu muốn hỏi chính giá trị cột theo góc nhìn của transaction hiện tại:

```java
String dbName = (String) em.createNativeQuery(
        "SELECT product_name FROM products WHERE id = ?1"
    )
    .setParameter(1, 10L)
    .getSingleResult();

System.out.println("Managed: " + product.getName());
System.out.println("SQL scalar: " + dbName);
```

Scalar query không ánh xạ về `Product` managed, nên có thể cho biết database trả gì ở thời điểm query, theo **transaction, isolation và nguồn dữ liệu đang dùng**.

Tuy nhiên:

- Nó chưa chứng minh transaction đã commit.
- Nếu có pending changes, provider có thể flush trước query tùy flush mode/cơ chế.
- Nếu transaction đang dùng snapshot cũ, query SQL cũng có thể thấy dữ liệu cũ từ transaction khác.
- Nếu đang đọc replica, có thể gặp replication lag.

**Dữ liệu độc lập tránh identity map của entity, nhưng không tránh được mọi quy tắc nhất quán của database.**

### 17.3. `refresh` và `clear` có vai trò riêng

```java
em.flush();
em.refresh(product);
```

`refresh` yêu cầu cập nhật state của **managed Product** từ database. Ngược lại:

```java
em.flush();
em.clear();
Product reloaded = em.find(Product.class, 10L);
```

`clear` tách toàn bộ entity khỏi L1 trước khi tải lại. `clear` có thể làm mất pending changes nếu gọi trước `flush`.

Với cache L2/shared cache, `clear` không luôn đủ để ép SELECT trực tiếp từ bảng. Khi cần bằng chứng vật lý, có thể dùng một native scalar/JDBC query sau commit tại database nguồn hoặc cache bypass phù hợp.

## 18. Native UPDATE/DELETE không giống dirty checking

### 18.1. Native UPDATE thay đổi database trực tiếp

```java
em.getTransaction().begin();

int changed = em.createNativeQuery(
        "UPDATE products " +
        "SET product_name = ?1 " +
        "WHERE id = ?2"
    )
    .setParameter(1, "Tên đổi bằng SQL")
    .setParameter(2, 10L)
    .executeUpdate();

em.getTransaction().commit();
```

`executeUpdate()` thực thi DML, thường trả số hàng bị ảnh hưởng theo semantics của driver/provider. Nó **không tự tạo một managed Product mới**.

### 18.2. Context stale sau UPDATE

```java
Product managed = em.find(Product.class, 10L);

em.createNativeQuery(
        "UPDATE products SET product_name = ?1 WHERE id = ?2"
    )
    .setParameter(1, "SQL Updated Name")
    .setParameter(2, 10L)
    .executeUpdate();

System.out.println(managed.getName());
// Có thể vẫn là tên cũ.
```

Khi native SQL thay đổi database, provider không nhất thiết cập nhật field của managed instances đang có. **Đừng dùng getter của managed entity để kiểm chứng trực tiếp câu SQL DML** nếu chưa xử lý sự bất đồng bộ.

### 18.3. Không tự tăng version nếu muốn giữ optimistic locking

Native SQL tự viết không mặc nhiên tuân thủ toàn bộ protocol `@Version` mà ORM dùng khi UPDATE một managed entity.

Ví dụ ORM-managed update thường dựa trên version cũ trong điều kiện và tăng version khi ghi. Native SQL:

```sql
UPDATE products
SET product_name = ?
WHERE id = ?;
```

**không có điều kiện version** và cũng không tăng `row_version`. Nó có thể làm hỏng giả định optimistic concurrency nếu đồng thời dùng ORM để cập nhật cùng bảng.

Nếu thực sự cần native DML, phải thiết kế một protocol đồng thời rõ ràng:

```sql
UPDATE products
SET product_name = ?,
    row_version = row_version + 1
WHERE id = ?
  AND row_version = ?;
```

Sau đó kiểm tra số hàng bị ảnh hưởng và xử lý conflict; đồng thời dọn/refresh state ORM phù hợp. Đây là ví dụ logic, cần thống nhất với cách provider quản lý version và policy transaction toàn ứng dụng.

### 18.4. Lifecycle callbacks và cascade không được giả định

Native `UPDATE`/`DELETE` hoạt động ở tầng SQL, **không phải lần lượt gọi setters, `@PreUpdate`, `@PreRemove` hoặc cascade REMOVE trên từng entity**. Constraint database, trigger và FK vẫn được áp dụng theo schema.

Nếu business logic phụ thuộc JPA lifecycle callbacks hoặc association cascade, cần cân nhắc dùng thao tác entity-managed hoặc tự chịu trách nhiệm tương ứng ở đường native DML.

### 18.5. Flush trước native DML và làm sạch context sau đó

Một quy trình thận trọng khi kết hợp native DML với managed entities:

1. Xác định các thay đổi pending trong persistence context.
2. `flush` trước nếu muốn SQL native nhìn thấy các thay đổi ORM trong transaction.
3. Thực thi native DML.
4. Cân nhắc `refresh` entity liên quan hoặc `clear`/`detach` khi phù hợp.
5. Commit hoặc rollback transaction đúng cách.
6. Không tiếp tục dùng reference stale như thể nó mới được cập nhật.

Các bước phải phù hợp use case. `clear` tách **mọi entity**, nên không nên dùng một cách mù quáng giữa service lớn. Nếu native SQL làm thay đổi version hoặc FK, rủi ro stale state và lỗi flush sau đó càng cần được xử lý chủ động.

## 19. `executeUpdate` khác `getResultList`

### 19.1. SELECT

```java
List<?> rows = em.createNativeQuery(
    "SELECT sku FROM products"
).getResultList();
```

Đây là native SELECT trả dữ liệu.

### 19.2. UPDATE/DELETE

```java
int affected = em.createNativeQuery(
        "DELETE FROM order_lines WHERE product_id = ?1"
    )
    .setParameter(1, productId)
    .executeUpdate();
```

DML dùng `executeUpdate()`, không phải `getResultList()`. Phải có transaction phù hợp cho cập nhật/xóa theo JPA.

### 19.3. SQL RETURNING và tính portable

Một số database như PostgreSQL có `INSERT ... RETURNING` hoặc `UPDATE ... RETURNING`. Không nên mặc định mọi JPA provider và database đều hỗ trợ cùng cách đưa DML có RETURNING vào `getResultList()` hay ánh xạ entity.

Nếu use case phụ thuộc RETURNING, CTE, stored procedure hoặc upsert native, cần xác định **database dialect, JDBC/JPA provider và contract kết quả**. Có thể dùng JDBC hoặc API đặc thù một cách có chủ đích.

## 20. Hai EntityManager và transaction độc lập

### 20.1. Cùng một hàng, hai managed instance trong hai context

```java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

try {
    Product p1 = (Product) em1.createNativeQuery(
            "SELECT p.* FROM products p WHERE p.id = ?1",
            Product.class
        )
        .setParameter(1, 10L)
        .getSingleResult();

    Product p2 = (Product) em2.createNativeQuery(
            "SELECT p.* FROM products p WHERE p.id = ?1",
            Product.class
        )
        .setParameter(1, 10L)
        .getSingleResult();

    System.out.println(p1 == p2);       // false trong context riêng.
    System.out.println(em1.contains(p1)); // true
    System.out.println(em2.contains(p2)); // true
    System.out.println(em1.contains(p2)); // false
} finally {
    em1.close();
    em2.close();
}
```

Giả định là hai `EntityManager` application-managed với persistence context riêng. Cùng giá trị ID không khiến một instance tự managed trong context khác.

### 20.2. Ra khỏi context: entity có thể detached

```java
Product product;

EntityManager em = emf.createEntityManager();
try {
    product = (Product) em.createNativeQuery(
            "SELECT p.* FROM products p WHERE p.id = ?1",
            Product.class
        )
        .setParameter(1, 10L)
        .getSingleResult();
} finally {
    em.close();
}

// Lúc này product vẫn là object Java, nhưng không còn
// được persistence context vừa đóng theo dõi.
```

Không nên kết luận “native entity luôn managed vĩnh viễn”. Managed state chỉ tồn tại **trong phạm vi persistence context**. Khi đóng context, entity thường chuyển thành detached. Thay đổi nó ở một request khác không tự được flush về database.

### 20.3. DTO không “detached” theo nghĩa JPA entity lifecycle

Nếu một `ProductSummary` được trả ra khỏi service, nó vẫn là một object Java bình thường. Không cần gọi `detach`, và cũng không có trạng thái new/managed/removed theo lifecycle của entity. Thuật ngữ “detached” dành cho **entity instance từng được quản lý**, không phải mọi DTO đi qua ranh giới transaction.

## 21. `getSingleResult`, số hàng và xử lý lỗi

### 21.1. Một hàng hay không có hàng

```java
Product product = (Product) em.createNativeQuery(
        "SELECT p.* FROM products p WHERE p.id = ?1",
        Product.class
    )
    .setParameter(1, id)
    .getSingleResult();
```

Nếu không có hàng, JPA có thể ném `NoResultException`. Nếu có nhiều hàng do SQL/JOIN hoặc dữ liệu không đúng giả định, `NonUniqueResultException` có thể xuất hiện.

Một phiên bản muốn xử lý “không có sản phẩm” rõ ràng:

```java
@SuppressWarnings("unchecked")
List<Product> products = em.createNativeQuery(
        "SELECT p.* FROM products p WHERE p.id = ?1",
        Product.class
    )
    .setParameter(1, id)
    .setMaxResults(1)
    .getResultList();

Product product = products.isEmpty() ? null : products.get(0);
```

`setMaxResults(1)` cố ý chỉ lấy một kết quả; nó **không chứng minh** rằng SQL vốn có nhiều hay một hàng. Với `WHERE id = ?` trên PK hợp lệ, số hàng được xác định bởi constraint PK.

### 21.2. Đúng kiểu output

Lỗi thường thấy:

```java
Product product = (Product) em.createNativeQuery(
    "SELECT sku, product_name FROM products"
).getSingleResult();
```

Không có entity mapping; cast từ `Object[]` sang `Product` sẽ không hợp lệ.

Một lỗi khác:

```java
Object[] row = (Object[]) em.createNativeQuery(
    "SELECT sku FROM products WHERE id = ?1"
).setParameter(1, 10L).getSingleResult();
```

Chỉ một cột nên kết quả thường là `String`, không phải `Object[]`.

Cách sửa không phải ép kiểu mạnh hơn mà là **đọc đúng contract của query và mapping**.

### 21.3. Null trong cột scalar

Nếu truy vấn trả `NULL`:

```java
Object value = em.createNativeQuery(
    "SELECT nullable_column FROM some_table WHERE id = ?1"
).setParameter(1, id).getSingleResult();
```

`value` có thể null. Nếu dùng constructor mapping, kiểu tham số DTO phải cho phép null hoặc có chính sách `COALESCE`/normalization. Đừng cast null thành primitive hoặc gọi method trên giá trị null mà không kiểm tra.

## 22. Mẫu tổ chức repository theo mục tiêu trả về

### 22.1. Hai phương thức có tên rõ ràng

Một repository dùng EntityManager có thể cung cấp:

```java
public final class ProductNativeRepository {

    private final EntityManager em;

    public ProductNativeRepository(EntityManager em) {
        this.em = em;
    }

    public Product findManagedEntity(long id) {
        @SuppressWarnings("unchecked")
        List<Product> results = em.createNativeQuery(
                "SELECT p.* FROM products p WHERE p.id = ?1",
                Product.class
            )
            .setParameter(1, id)
            .getResultList();

        return results.isEmpty() ? null : results.get(0);
    }

    public ProductSummary findSummary(long id) {
        @SuppressWarnings("unchecked")
        List<Object[]> rows = em.createNativeQuery(
                "SELECT id, sku, product_name, unit_price " +
                "FROM products WHERE id = ?1"
            )
            .setParameter(1, id)
            .getResultList();

        if (rows.isEmpty()) {
            return null;
        }

        Object[] row = rows.get(0);
        return new ProductSummary(
            ((Number) row[0]).longValue(),
            (String) row[1],
            (String) row[2],
            (BigDecimal) row[3]
        );
    }
}
```

Ví dụ giả định `ProductSummary` là record ở mục trước. Cần import `jakarta.persistence.EntityManager`, `java.util.List`, `java.math.BigDecimal`.

Sự khác nhau nằm ngay ở tên method:

- `findManagedEntity`: caller nhận entity có thể tham gia lifecycle JPA nếu context còn mở.
- `findSummary`: caller nhận **bản dữ liệu độc lập** chỉ phục vụ đọc.

Không nên dùng một method tên chung `queryProduct` mà lúc trả managed entity, lúc trả Object[] tùy điều kiện. Contract không rõ sẽ dẫn đến lỗi update ngoài ý định hoặc ClassCastException.

### 22.2. Khi nào chọn managed entity?

Phù hợp khi service cần:

- Thực hiện thao tác nghiệp vụ trên entity trong transaction.
- Sửa state và để JPA dirty checking đồng bộ.
- Dùng association hoặc entity graph đã ánh xạ.
- Áp dụng `@Version` và các quy tắc lifecycle.
- Chuyển tiếp một instance managed tới những thao tác ORM khác trong cùng context.

Nếu chỉ đọc theo khóa chính mà không cần SQL đặc thù, **`em.find(Product.class, id)` có thể đơn giản hơn native SQL**.

### 22.3. Khi nào chọn DTO/scalar?

Phù hợp khi:

- Chỉ hiển thị vài cột.
- Query có aggregate, window function, union hoặc CTE.
- Dữ liệu là tổng hợp nhiều bảng không có entity tương ứng.
- Muốn tránh để đối tượng read model bị thay đổi và tự dirty-check.
- Kết quả cần ổn định như một response contract cho API.
- Chỉ cần ID, tên, thống kê, không cần mở entity graph.

**Không phải DTO luôn nhanh hơn entity trong mọi trường hợp**, nhưng DTO giúp kiểm soát cột được lấy và tránh chi phí quản lý entity khi chỉ cần dữ liệu đọc.

## 23. Caching, query hints và tính nhất quán

### 23.1. L1 cache: persistence context

Khi native SQL trả `Product` managed, JPA phải duy trì identity trong context. Nếu Product ID 10 đã được tải, query có thể trả chính instance cũ. Điều này có thể khiến dữ liệu Java khác với giá trị mới trong database do update trực tiếp.

### 23.2. L2 cache: shared cache

Một số provider bật shared second-level cache. Mở EntityManager mới tránh L1 cũ nhưng không tự chứng minh đã đọc bảng thực tế nếu provider có thể dùng L2.

Ví dụ hint chuẩn dùng để bỏ qua shared cache khi phù hợp:

```java
import jakarta.persistence.CacheRetrieveMode;

Product product = em.find(
    Product.class,
    10L,
    Map.of(
        "jakarta.persistence.cache.retrieveMode",
        CacheRetrieveMode.BYPASS
    )
);
```

Cần import `java.util.Map`. Hint này nhắm tới **shared cache retrieval**, không biến lần `find` trên entity đã managed trong L1 thành một lượt SELECT mới. Với native query, cách áp dụng hint/cache policy cũng cần xét provider và query cụ thể.

### 23.3. Native SQL scalar làm rõ góc nhìn database

Một native `SELECT product_name ...` trả scalar có thể tránh việc đọc getter của entity cũ. Nhưng kết quả vẫn chịu **transaction isolation**, snapshot và source DB.

Nếu ứng dụng ghi vào primary nhưng đọc từ replica, một scalar SQL trên replica có thể thấy dữ liệu cũ do replication lag. Vì vậy cần xác định đang muốn kiểm tra **in-memory state**, **flushed SQL state** hay **committed state trên đúng nguồn**.

### 23.4. Khi đã có entity managed nhưng muốn read-only response

Có thể chuyển managed entity sang DTO:

```java
Product managed = em.find(Product.class, id);

ProductSummary summary = new ProductSummary(
    managed.getId(),
    managed.getSku(),
    managed.getName(),
    managed.getUnitPrice()
);
```

Bản DTO độc lập, nhưng **nguồn dữ liệu** của nó vẫn có thể là entity đang stale trong L1. DTO không tự làm dữ liệu mới hơn.

Muốn truy vấn báo cáo độc lập khỏi identity map, có thể viết projection SQL scalar/ConstructorResult trực tiếp. Muốn xác minh committed state, đọc sau commit bằng transaction và kết nối phù hợp.

## 24. Native SQL và tính portable

### 24.1. Ngôn ngữ SQL phụ thuộc database

Native query cho phép:

- Window functions như `ROW_NUMBER()`.
- CTE bằng `WITH`.
- JSON operators và aggregate đặc thù.
- Vendor-specific pagination/locking.
- DML nâng cao theo database.

Nhưng chúng **không nhất thiết portable** giữa PostgreSQL, MySQL, SQL Server, Oracle và các hệ quản trị khác.

### 24.2. Result-set mapping là contract riêng

Ngay cả khi câu SQL chạy trên database mới, các alias và kiểu cột phải khớp mapping:

```java
@ColumnResult(name = "line_count", type = Long.class)
```

Nếu SQL đổi:

```sql
COUNT(ol.id) AS total_lines
```

nhưng mapping vẫn đòi `line_count`, provider có thể không tìm thấy cột. Phải cập nhật SQL và mapping cùng nhau.

### 24.3. Named parameter trong native SQL có thể kém portable hơn positional

JPA hỗ trợ `setParameter`, nhưng **native SQL named parameters** không phải đặc điểm được đảm bảo giống nhau trên mọi provider ở mọi thế hệ chuẩn. Khi ưu tiên portability, dùng positional parameter `?1` hoặc cơ chế provider hỗ trợ đã được xác định rõ.

Không tự đặt dấu `?` trong SQL rồi trông chờ mọi cách binding tương thích nếu nhà cung cấp dùng quy tắc riêng; hãy dùng cú pháp phù hợp phiên bản JPA/provider và database của dự án.

### 24.4. Không bind identifier như giá trị

Parameter binding được thiết kế cho **giá trị**:

```java
em.createNativeQuery(
    "SELECT p.* FROM products p WHERE p.sku = ?1",
    Product.class
).setParameter(1, sku);
```

Không thể dùng parameter để thay tên bảng/cột theo kiểu:

```sql
SELECT * FROM ?1 ORDER BY ?2
```

Nếu ứng dụng cần chọn động cột sort hoặc bảng theo chế độ báo cáo, phải dùng **whitelist tên identifier hợp lệ** do ứng dụng kiểm soát, không nối raw input không tin cậy vào SQL. Native SQL không miễn trừ nguy cơ SQL injection.

## 25. Transaction và dữ liệu đọc độc lập

### 25.1. Entity managed cần transaction để ghi

Một native entity SELECT có thể được thực hiện để đọc, nhưng muốn thay đổi entity được flush/commit đúng cách thì phải có ranh giới transaction phù hợp.

```java
em.getTransaction().begin();

try {
    Product product = (Product) em.createNativeQuery(
            "SELECT p.* FROM products p WHERE p.id = ?1",
            Product.class
        )
        .setParameter(1, 10L)
        .getSingleResult();

    product.changePrice(new BigDecimal("990000.00"));
    em.flush();
    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
```

Trong Spring/Jakarta EE, transaction có thể được quản lý bởi framework/container; không trộn mô hình RESOURCE_LOCAL với JTA khi triển khai.

### 25.2. DTO độc lập không cần dirty checking

Nếu native query trả DTO, có thể đọc trong transaction read-only phù hợp, nhưng thay đổi DTO không được tự lưu.

```java
ProductSummary summary = repository.findSummary(10L);

// Muốn cập nhật dữ liệu, gọi một command/use case riêng,
// không kỳ vọng thay đổi summary sẽ tạo UPDATE.
```

Tầng HTTP/controller thường an toàn hơn khi chỉ nhận DTO vì không lộ semantics quản lý entity qua nhiều request.

### 25.3. Xác minh sau commit bằng context mới

Một quy trình integration test có chủ đích:

```text
Writer EntityManager
  |
  +-- begin transaction
  +-- native entity SELECT -> Product managed
  +-- sửa Product qua domain method
  +-- flush
  +-- commit thành công
  +-- close

Reader EntityManager mới
  |
  +-- bắt đầu transaction đọc phù hợp
  +-- native scalar SELECT/DTO query
  +-- so sánh giá trị từ DB source
  +-- end transaction / close
```

Chỉ gọi lại `createNativeQuery(sql, Product.class)` trên writer chưa đóng **không phải kiểm tra đọc độc lập**, vì identity map có thể trả lại cùng Product instance.

## 26. Kiểm thử hai dạng kết quả

### 26.1. Test entity mapping và trạng thái managed

Giả sử test đã chuẩn bị Product ID 10 trong database thử nghiệm:

```java
@Test
void nativeEntityResultIsManaged() {
    Product product = (Product) em.createNativeQuery(
            "SELECT p.* FROM products p WHERE p.id = ?1",
            Product.class
        )
        .setParameter(1, 10L)
        .getSingleResult();

    assertTrue(em.contains(product));

    Product same = em.find(Product.class, 10L);
    assertSame(product, same);
}
```

Hai assert này xác nhận semantics của entity result trong context hiện tại. Chúng **không chứng minh transaction đã commit**.

### 26.2. Test scalar không phải entity

```java
@Test
void nativeScalarResultIsIndependentValue() {
    Object value = em.createNativeQuery(
            "SELECT sku FROM products WHERE id = ?1"
        )
        .setParameter(1, 10L)
        .getSingleResult();

    assertInstanceOf(String.class, value);
    assertEquals("KB-001", value);
}
```

`assertInstanceOf` dùng JUnit 5 phiên bản hỗ trợ API này; với phiên bản khác có thể dùng `assertTrue(value instanceof String)`. Không gọi `em.contains(value)` cho `String`, bởi nó không phải entity.

### 26.3. Test DTO result không bị dirty checking

```java
@Test
void nativeDtoDoesNotBecomeManagedEntity() {
    ProductSalesSummary result =
        (ProductSalesSummary) em.createNativeQuery(
                "SELECT p.sku AS sku, " +
                "COUNT(ol.id) AS order_line_count " +
                "FROM products p " +
                "LEFT JOIN order_lines ol ON ol.product_id = p.id " +
                "WHERE p.id = ?1 " +
                "GROUP BY p.id, p.sku",
                "ProductSalesSummaryMapping"
            )
            .setParameter(1, 10L)
            .getSingleResult();

    assertEquals("KB-001", result.sku());
    // ProductSalesSummary là DTO/record, không có lifecycle entity.
}
```

Trong test thực tế, dữ liệu mẫu phải được seed và `ProductSalesSummaryMapping` phải được đăng ký trong persistence unit.

### 26.4. Test đọc lại sau native UPDATE

```java
@Test
void nativeUpdateDoesNotRefreshExistingManagedState() {
    Product product = em.find(Product.class, 10L);
    String before = product.getName();

    em.createNativeQuery(
            "UPDATE products SET product_name = ?1 WHERE id = ?2"
        )
        .setParameter(1, "Tên từ native SQL")
        .setParameter(2, 10L)
        .executeUpdate();

    String sqlValue = (String) em.createNativeQuery(
            "SELECT product_name FROM products WHERE id = ?1"
        )
        .setParameter(1, 10L)
        .getSingleResult();

    assertEquals("Tên từ native SQL", sqlValue);
    // product.getName() có thể vẫn giữ giá trị cũ.
    // Không dùng assertEquals(before, product.getName()) như một
    // cam kết portable trong mọi cấu hình, hãy xác minh semantics cần.
}
```

Test phải được thực thi trong transaction ghi phù hợp và rollback/cleanup dữ liệu sau thử nghiệm. Nếu muốn kết luận dữ liệu **đã commit**, cần tạo transaction đọc mới sau khi writer commit thành công.

## 27. Những hiểu nhầm thường gặp

| Nhận định | Cách hiểu đúng |
|---|---|
| “Native SQL luôn trả object độc lập, không managed.” | Native entity mapping bằng `Product.class` hoặc `EntityResult` trả entity managed trong context. |
| “Trả đủ cột entity thì JPA tự tạo entity.” | Không khai báo mapping, query thường trả scalar/`Object[]`. |
| “Có `@SqlResultSetMapping` là entity managed.” | Phải xem mapping dùng `EntityResult`, `ColumnResult` hay `ConstructorResult`. |
| “`Object[]` chứa Product thì cả mảng là managed.” | Chỉ phần tử Product được ánh xạ entity mới managed; scalar khác vẫn độc lập. |
| “DTO có ID nên có thể merge vào JPA.” | DTO không phải entity; áp dụng dữ liệu vào managed entity có kiểm soát. |
| “Gọi native SELECT lần nữa luôn refresh entity.” | Identity map có thể trả cùng instance đã quản lý; dùng refresh/readback riêng. |
| “Ánh xạ entity chỉ cần id và name.” | Native entity query cần result set đủ cho metadata entity, bao gồm version/mapping liên quan. |
| “Native query dùng JOIN luôn tránh duplicate.” | JOIN 1-n có thể nhân bản hàng; identity map không đồng nghĩa result list khử trùng. |
| “Dùng `COUNT(*)` luôn nhận Integer.” | Driver/provider có thể trả dạng Number khác; dùng kiểu phù hợp. |
| “ConstructorResult làm DTO managed.” | ConstructorResult tạo object kết quả, không tự tạo managed entity DTO. |
| “Đổi `row[1]` trong Object[] sẽ tự UPDATE.” | Mảng giá trị không có dirty checking. |
| “Native UPDATE tự cập nhật mọi entity đang managed.” | Direct SQL có thể làm persistence context stale. |
| “Native DML tự thực hiện `@PreUpdate`/`@PreRemove`.” | Nó không gọi lifecycle callbacks từng entity như thao tác ORM-managed. |
| “Native UPDATE mặc nhiên tuân thủ `@Version`.” | Phải tự thiết kế version check/update nếu dùng SQL thủ công. |
| “`clear()` cũng xóa mọi shared cache.” | Clear chỉ tách entities khỏi context L1; L2 có cơ chế riêng. |
| “Native scalar sau flush chứng minh commit.” | Scalar đọc theo transaction hiện tại; flush khác commit. |
| “Mở EntityManager mới luôn đọc bảng gốc.” | Shared cache, replica và isolation còn ảnh hưởng. |
| “Native SQL cho phép bind tên bảng bằng `?1`.” | Tham số bind giá trị; tên identifier cần whitelist nếu động. |
| “Query DTO luôn nhanh hơn query entity.” | Phụ thuộc số cột, query plan, cache và workload; không có bảo đảm tuyệt đối. |
| “`createNativeQuery` trả TypedQuery<Product>.” | API thường trả `Query`; cast phần tử theo mapping đã khai báo. |

## 28. Bảng chọn chiến lược ánh xạ

| Mục tiêu của use case | Cách bắt đầu | Vì sao |
|---|---|---|
| Tải Product để thay đổi trong transaction | `em.find`, JPQL entity query hoặc `createNativeQuery(sql, Product.class)` | Cần managed entity và dirty checking |
| Tải Product bằng SQL đặc thù nhưng vẫn cần managed | `createNativeQuery(sql, Product.class)` hoặc `@EntityResult` | Ánh xạ theo entity metadata |
| Trả SKU/tên cho API | Native scalar projection hoặc DTO | Không cần entity lifecycle |
| Trả số Product đang có | `COUNT(*)` scalar với `Number` | Không tạo entity vô ích |
| Báo cáo OrderLine theo Product | `@ConstructorResult` DTO hoặc Object[] mapper | Kết quả là aggregate, không phải Product entity đơn |
| SQL có alias không trùng entity mapping | `@FieldResult` trong `@EntityResult` | Liên kết alias với thuộc tính Java |
| Một Product kèm một số đếm | Mapping kết hợp `EntityResult` + `ColumnResult` | Phần tử entity managed; scalar độc lập |
| Muốn immutable read model | Record/DTO | Tránh vô tình sửa entity managed |
| Cần UPDATE qua SQL tối ưu hàng loạt | Native `executeUpdate` với version/cache/transaction policy rõ | DML không tự theo dõi entity lifecycle |
| Cần xác minh SQL từ database nguồn sau commit | Native scalar/JDBC trong reader mới | Không chỉ đọc lại object từ L1 |
| Query native kết hợp nhiều bảng, tên cột trùng | Alias rõ, `FieldResult` hoặc DTO | Tránh mơ hồ result mapping |

## 29. Bài thực hành

### Bài 1 — Cùng SQL nhưng hai cách trả kết quả

Với Product ID 10, chạy:

```java
em.createNativeQuery(
    "SELECT p.* FROM products p WHERE p.id = ?1",
    Product.class
);
```

và:

```java
em.createNativeQuery(
    "SELECT p.id, p.sku, p.product_name " +
    "FROM products p WHERE p.id = ?1"
);
```

Quan sát kiểu Java trả về, kết quả `em.contains` với entity và việc raw query trả `Object[]`. Giải thích vì sao cùng bảng không có nghĩa cùng lifecycle.

### Bài 2 — Kiểm tra managed identity

Tải Product ID 10 bằng `em.find` rồi bằng native query `Product.class` trong cùng EntityManager. So sánh hai reference với `==` và `em.contains`.

Sau đó mở một EntityManager khác, tải cùng Product và phân biệt persistent identity với Java object identity.

### Bài 3 — Dirty checking của native entity

Trong transaction, tải Product bằng native entity query, gọi `rename`, `flush` rồi commit. Mở reader context mới đọc lại cột `product_name`.

So sánh với việc đổi một phần tử trong `Object[]` hoặc sửa một DTO mutable rồi commit. Vì sao chỉ một trong những cách đó có thể tạo UPDATE tự động?

### Bài 4 — Thiếu cột khi ánh xạ entity

Thử `createNativeQuery("SELECT id, sku FROM products", Product.class)` và quan sát phản ứng provider. Xem metadata của `Product` gồm `unitPrice` và `@Version`.

Giải thích tại sao partial projection nên là DTO thay vì yêu cầu managed entity không đầy đủ.

### Bài 5 — ColumnResult và ConstructorResult

Tạo hai mapping:

1. `@SqlResultSetMapping` gồm hai `ColumnResult`.
2. `@SqlResultSetMapping` gồm một `ConstructorResult` tới record `ProductSalesSummary`.

Viết câu SQL với alias khớp annotation, quan sát shape của `getResultList()` và chứng minh DTO không có dirty checking.

### Bài 6 — EntityResult và FieldResult

Đổi alias các cột Product thành `pid`, `psku`, `pname`, `price_value`, `version_value`. Khai báo `@FieldResult` tương ứng để map về Product.

So sánh với việc chỉ cast `Object[]` thành Product: vì sao JPA cần metadata result mapping?

### Bài 7 — Kết quả hỗn hợp

Truy vấn `ProductAndOrderLineCount` trả `Object[]`, trong đó phần tử đầu là `Product` managed và phần tử sau là `Long` scalar.

Kiểm tra identity của Product với `em.find` và phân tích tại sao số đếm không phải thuộc tính được dirty-check của Product.

### Bài 8 — JOIN nhân bản hàng

Tạo Product có ba OrderLine. Chạy native SQL `SELECT p.* FROM products p JOIN order_lines ol ...` và quan sát result list.

Viết lại bằng `WHERE EXISTS` hoặc `DISTINCT` để chỉ lấy Product duy nhất. Giải thích vì sao persistence context quản lý một instance không tự bảo đảm danh sách không lặp.

### Bài 9 — Native UPDATE làm context stale

Tải Product bằng `find`, sau đó chạy native `UPDATE products SET product_name = ...` trong cùng transaction. So sánh:

- `product.getName()`.
- Native scalar `SELECT product_name`.
- `em.refresh(product)` rồi đọc getter.

Giải thích những giá trị nào phản ánh DB trong transaction và tại sao vẫn chưa chứng minh commit.

### Bài 10 — Optimistic locking với native SQL

Thêm hai transaction cùng cập nhật Product có `@Version`. So sánh cách ORM-managed update dùng version với native UPDATE chỉ có `WHERE id = ?`.

Thiết kế native UPDATE có `WHERE id = ? AND row_version = ?`, tăng version và kiểm tra số hàng ảnh hưởng. Đánh giá việc refresh/clear context sau DML.

### Bài 11 — DTO API và command cập nhật

Tạo endpoint chỉ đọc trả `ProductSummary` record. Thiết kế endpoint cập nhật nhận `ProductUpdateCommand`, tìm Product managed theo ID và áp dụng thay đổi có phân quyền/validation.

Tại sao không nên deserialize DTO rồi gửi trực tiếp vào `em.merge` như một entity?

### Bài 12 — Test sau commit

Viết integration test:

1. Writer transaction tải native Product entity, sửa giá, flush và commit.
2. Reader transaction/context mới chạy native scalar SELECT trên database nguồn.
3. So sánh giá với BigDecimal theo chính sách scale.
4. Kiểm tra việc rollback ở một test khác không để lại committed change.

Tách kết luận “managed trong context” khỏi “đã commit và reader độc lập đọc thấy”.

### Bài 13 — Tối ưu độ rộng kết quả

So sánh hai query với dữ liệu nhiều Product:

- `SELECT p.*` ánh xạ entity.
- `SELECT p.sku, p.product_name` ánh xạ DTO.

Quan sát SQL, kích thước dữ liệu truyền, thời gian và memory/persistence context. Không kết luận một cách luôn nhanh hơn mà không có số đo.

### Bài 14 — Portability của alias và kiểu dữ liệu

Chạy `COUNT(*)` và một aggregate numeric qua raw native query trên database/provider đang dùng. Ghi nhận kiểu Java nhận được rồi dùng `ColumnResult(type=...)` phù hợp.

Thử đổi alias SQL mà không đổi mapping để hiểu vì sao `SqlResultSetMapping` là một contract cần đồng bộ với câu SELECT.

## 30. Ghi nhớ cốt lõi

**Native SQL không quyết định entity được quản lý hay dữ liệu độc lập chỉ dựa trên câu SQL.** Quyết định quan trọng là **cách ánh xạ result set**:

- `createNativeQuery(sql, Product.class)` hoặc `@EntityResult` trả **entity managed** trong persistence context tương ứng.
- `createNativeQuery(sql)` không ánh xạ entity thường trả **scalar/`Object[]`**.
- `@ColumnResult` trả **giá trị cột**.
- `@ConstructorResult` tạo **DTO/read model độc lập** khi target class không phải entity.
- Mapping kết hợp có thể trả `Object[]` chứa **cả managed entity và scalar**, với semantics riêng cho từng phần tử.

Managed entity có identity map, dirty checking và vòng đời JPA; DTO/scalar chỉ chứa dữ liệu và **không tự được flush** khi sửa. Native SELECT ánh xạ entity cũng **không nhất thiết làm mới** instance đã managed. Native UPDATE/DELETE lại có thể khiến persistence context stale và không tự thực hiện các callback, cascade hay kiểm tra `@Version` như thao tác entity-managed.

Vì vậy, hãy bắt đầu từ mục đích: **cần chỉnh sửa một entity trong transaction hay chỉ cần trả dữ liệu cho API/báo cáo?** Sau đó chọn entity mapping hoặc scalar/DTO projection, quản lý alias/kiểu kết quả rõ ràng, xác định transaction/cache và dùng lượt đọc độc lập khi cần xác minh dữ liệu tại database.
