# Chọn entity, DTO, giá trị tổng hợp và Tuple

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Criteria API

Một truy vấn JPA không nhất thiết phải trả về toàn bộ entity. Trong nhiều tình huống, ứng dụng chỉ cần **một entity có thể sửa**, **một tập thuộc tính để hiển thị**, **một con số thống kê** hoặc **một hàng gồm nhiều giá trị không thuộc một DTO cố định**. **Criteria API** cho phép xây dựng những lựa chọn đó bằng đối tượng Java thay vì phải ghép chuỗi JPQL.

Ví dụ, cùng một entity **Product**, bốn yêu cầu sẽ có bốn dạng kết quả khác nhau:

~~~text
Yêu cầu nghiệp vụ                     Kiểu trả về phù hợp
────────────────────────────────────────────────────────────────
Cập nhật tên Product                  Product (entity)
Danh sách card: id, tên, giá          ProductCard (DTO)
Đếm tổng sản phẩm đang bán            Long (scalar aggregate)
Báo cáo linh hoạt: category, số lượng Tuple (nhiều trường có alias)
~~~

Các điểm khác biệt quan trọng:

- **Entity selection** trả các entity được quản lý khi được load trong persistence context, có identity, quan hệ, lazy loading và dirty checking theo trạng thái thực tế.
- **DTO projection** trả những đối tượng Java thông thường được xây từ các giá trị được chọn, không tự có lifecycle của JPA entity.
- **Scalar selection** trả một giá trị như **Long**, **BigDecimal**, **String**, **Double**; rất phù hợp cho count, sum, avg, min, max.
- **Tuple selection** trả nhiều cột với khả năng đọc theo **vị trí**, **alias** hoặc **TupleElement**, hữu ích cho báo cáo và truy vấn động.
- **Object[]** cũng có thể chứa nhiều giá trị, nhưng việc ép kiểu theo chỉ số dễ sai hơn DTO hoặc Tuple.

Mục tiêu của bài là nắm rõ **CriteriaQuery<T>**, **Root<T>**, **Selection<T>**, **CriteriaBuilder.construct**, **multiselect**, **Tuple**, các hàm tổng hợp, **groupBy**, **having** và cách lựa chọn loại kết quả phù hợp với nghiệp vụ, hiệu năng và khả năng bảo trì.

## 1. Tổng quan về Criteria API và kiểu kết quả

### 1.1. Vì sao dùng Criteria API?

Một câu JPQL viết bằng string:

~~~java
List<Product> products = em.createQuery(
    """
    select p
    from Product p
    where p.active = true and p.price >= :minimum
    order by p.name
    """,
    Product.class
)
.setParameter("minimum", new BigDecimal("100000.00"))
.getResultList();
~~~

Có thể được diễn đạt bằng Criteria API:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> p = cq.from(Product.class);

cq.select(p)
  .where(
      cb.isTrue(p.get("active")),
      cb.greaterThanOrEqualTo(
          p.get("price"),
          new BigDecimal("100000.00")
      )
  )
  .orderBy(cb.asc(p.get("name")));

List<Product> products = em.createQuery(cq).getResultList();
~~~

Criteria API có ưu điểm khi cần:
- Thêm/bớt điều kiện tùy chọn mà không ghép chuỗi;
- Tái sử dụng nhóm predicate và biểu thức;
- Xây dynamic joins, sorting và projections;
- Tạo kết quả typed theo một số khả năng của Java compiler;
- Tổ chức query phức tạp thành các phương thức có thể tái sử dụng.

Nhưng **Criteria không tự động nhanh hơn JPQL**, cũng không thay thế việc hiểu schema, SQL, database indexes, transaction và truy vấn dữ liệu có NULL.

### 1.2. Những interface cốt lõi

| Thành phần | Vai trò |
|---|---|
| EntityManager | Tạo/executing query, quản lý persistence context |
| CriteriaBuilder | Xây predicate, expressions, aggregate, constructor selection |
| CriteriaQuery<T> | Định nghĩa cấu trúc truy vấn và kiểu kết quả T |
| Root<Product> | Nguồn entity Product trong FROM |
| Path<X> | Đường dẫn tới thuộc tính của entity/association |
| Expression<T> | Biểu thức có kiểu, có thể được tính/chọn/lọc |
| Selection<T> | Mô tả giá trị/đối tượng được chọn bởi SELECT |
| Predicate | Điều kiện boolean cho WHERE/HAVING |
| Order | Thứ tự ORDER BY |
| Join<X,Y> | Mô hình hóa join qua association |
| Tuple | Một hàng kết quả gồm nhiều selection |

Điểm xuyên suốt:

~~~java
CriteriaQuery<Product> entityQuery;
CriteriaQuery<ProductCard> dtoQuery;
CriteriaQuery<Long> countQuery;
CriteriaQuery<Tuple> tupleQuery;
CriteriaQuery<Object[]> arrayQuery;
~~~

Tham số generic **T của CriteriaQuery<T> mô tả kiểu một hàng kết quả**, không phải kiểu bảng/entity trong FROM. Một truy vấn FROM Product hoàn toàn có thể trả Long, ProductCard hoặc Tuple.

### 1.3. Kết quả một hàng khác với danh sách nhiều hàng

Ví dụ:

~~~java
TypedQuery<Product> query = em.createQuery(cq);
List<Product> products = query.getResultList();
~~~

**getResultList()** diễn đạt nhiều hàng, có thể rỗng.

Khi truy vấn đảm bảo một kết quả như count không group:

~~~java
Long count = em.createQuery(countQuery).getSingleResult();
~~~

**getSingleResult()** trả một hàng hoặc ném exception nếu không có/không duy nhất (tùy semantics query). **Không mặc định rằng mọi aggregate có GROUP BY đều trả một hàng**: một aggregate theo nhóm có thể trả nhiều hàng hoặc không có hàng nào.

## 2. Mô hình dữ liệu dùng trong ví dụ

Để so sánh các dạng projection, ta dùng một catalog đơn giản. Mỗi **Product** có thuộc tính giá, số lượng tồn kho, trạng thái và quan hệ tùy chọn với **Category**.

### 2.1. Entity Category

~~~java
package com.example.catalog;

import jakarta.persistence.*;

@Entity
@Table(name = "categories")
public class Category {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "code", nullable = false, unique = true, length = 40)
    private String code;

    @Column(name = "name", nullable = false, length = 120)
    private String name;

    protected Category() {}

    public Category(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
}
~~~

### 2.2. Entity Product

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(name = "sku", nullable = false, unique = true, length = 48)
    private String sku;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    @Column(name = "unit_price", precision = 19, scale = 2)
    private BigDecimal price;

    @Column(name = "stock_quantity")
    private Integer stockQuantity;

    @Column(name = "active", nullable = false)
    private boolean active;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {}

    public Product(
            String sku,
            String name,
            BigDecimal price,
            Integer stockQuantity,
            boolean active,
            Category category) {
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.stockQuantity = stockQuantity;
        this.active = active;
        this.category = category;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public Integer getStockQuantity() { return stockQuantity; }
    public boolean isActive() { return active; }
    public Instant getDeletedAt() { return deletedAt; }
    public Category getCategory() { return category; }

    public void rename(String nextName) {
        if (nextName == null || nextName.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không hợp lệ");
        }
        this.name = nextName;
    }
}
~~~

Các snippet dùng **jakarta.persistence** (Jakarta Persistence), không phải namespace javax.persistence của một số ứng dụng cũ. Với Spring Data JPA/Hibernate, cần chọn dependency tương thích với phiên bản ứng dụng.

### 2.3. Schema quan hệ minh họa

~~~sql
CREATE TABLE categories (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    sku VARCHAR(48) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    unit_price NUMERIC(19, 2),
    stock_quantity INTEGER,
    active BOOLEAN NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    category_id BIGINT REFERENCES categories(id)
);
~~~

SQL trên gợi hình dạng bảng, không phải migration bắt buộc cho mọi DB/dialect. Vì **price**, **stockQuantity** và **category** có thể NULL, chúng ta sẽ dùng dữ liệu thiếu giá trị để minh họa aggregates và joins.

### 2.4. Bộ dữ liệu mẫu

| SKU | Name | Category | Price | Stock | Active |
|---|---|---|---:|---:|---|
| P01 | Laptop Basic | Electronics | 12.000.000 | 3 | true |
| P02 | Wireless Mouse | Electronics | 350.000 | 20 | true |
| P03 | Office Chair | Furniture | 950.000 | 5 | true |
| P04 | Wooden Desk | Furniture | 2.500.000 | 0 | false |
| P05 | Mystery Item | NULL | NULL | NULL | true |
| P06 | USB Cable | NULL | 100.000 | 10 | true |
| P07 | Monitor Old | Electronics | 3.500.000 | 2 | false |

Giả định ban đầu **deletedAt IS NULL** cho cả 7 sản phẩm. Category Electronics và Furniture đều đã tồn tại trong DB. Các tổng và số lượng minh họa ở những phần sau dựa trên 7 hàng này và chỉ áp bộ lọc khác khi câu query có nêu.

## 3. Chọn toàn bộ entity: CriteriaQuery<Product>

Khi caller cần làm việc với **Product entity** và có thể cập nhật business fields, chọn Root<Product>:

~~~java
public List<Product> findActiveProducts(EntityManager em) {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Product> cq = cb.createQuery(Product.class);
    Root<Product> p = cq.from(Product.class);

    cq.select(p)
      .where(
          cb.isTrue(p.get("active")),
          cb.isNull(p.get("deletedAt"))
      )
      .orderBy(cb.asc(p.get("name")));

    return em.createQuery(cq).getResultList();
}
~~~

Điểm quan trọng: **cq.select(p)** có nghĩa chọn entity Product. Giá trị trong danh sách thường là **managed entities** khi được load trong persistence context đang hoạt động; JPA quản lý identity và dirty checking cho chúng, trừ trường hợp trạng thái đã thay đổi do detach/clear/close.

### 3.1. Dùng entity khi cần dirty checking

~~~java
@Transactional
public void renameProduct(long id, String newName) {
    Product product = em.find(Product.class, id);
    if (product == null) {
        throw new IllegalArgumentException("Product không tồn tại");
    }
    product.rename(newName);
    // UPDATE sẽ được JPA đồng bộ theo transaction/flush.
}
~~~

Nếu query trả ProductCard DTO thay vì entity, **đổi tên DTO sẽ không tạo UPDATE**. DTO không được persistence context theo dõi như entity.

### 3.2. Select entity không có nghĩa SQL SELECT * chính xác

Một entity selection cần tải các state mà provider quyết định phục vụ mapping. SQL có thể chọn nhiều mapped columns, nhưng không nên đồng nhất mọi lần **select(root)** với một statement SELECT * theo nghĩa vật lý.

Mapping lazy associations, bytecode enhancement, fetch plans và inheritance strategy có thể ảnh hưởng columns/joins được load. Tuy vậy, về chủ đích API, **entity selection yêu cầu một entity object**, không phải chỉ vài cột hiển thị.

### 3.3. CriteriaQuery<Product> có thể chứa predicate động

~~~java
public List<Product> findProducts(
        EntityManager em,
        BigDecimal minPrice,
        Boolean activeFilter) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Product> cq = cb.createQuery(Product.class);
    Root<Product> p = cq.from(Product.class);

    List<Predicate> conditions = new ArrayList<>();
    conditions.add(cb.isNull(p.get("deletedAt")));

    if (minPrice != null) {
        conditions.add(cb.greaterThanOrEqualTo(
            p.get("price"), minPrice));
    }

    if (activeFilter != null) {
        conditions.add(cb.equal(
            p.get("active"), activeFilter));
    }

    cq.select(p)
      .where(cb.and(conditions.toArray(new Predicate[0])))
      .orderBy(cb.asc(p.get("id")));

    return em.createQuery(cq).getResultList();
}
~~~

Một query Criteria có Root<Product> có thể chọn entity, nhưng CriteriaQuery<Product> không tự thêm WHERE; bộ lọc phải được khai báo có chủ đích. **cb.and(...)** ở đây kết hợp các predicate đã được xây, không lấy điều kiện từ dữ liệu người dùng để tạo một đoạn JPQL chưa kiểm soát.

### 3.4. Phân biệt entity root và entity return type

**Root<Product>** mô tả FROM. **CriteriaQuery<Product>** mô tả kết quả.

Phép chọn:

~~~java
cq.select(p);
~~~

đúng khi selection type tương thích với result type của query. Nếu muốn trả giá của Product thì phải tạo **CriteriaQuery<BigDecimal>** thay vì giữ **CriteriaQuery<Product>** rồi select(p.get("price")).

### 3.5. Entity result có identity; DTO result không có persistence identity

Trong cùng một persistence context, hai truy vấn trả Product cùng ID được quản lý theo identity map: đối với managed entity cùng identity, context duy trì một instance.

Một DTO mới được tạo bởi constructor projection **không dùng identity map của Product** để đảm bảo duy nhất reference DTO. Nếu query trả cùng một ID trong hai rows, có thể nhận hai DTO riêng (tùy projection và distinct), dù entity identity của chúng cùng là Product đó.

## 4. Chọn một thuộc tính scalar: CriteriaQuery<T>

Nếu chỉ cần danh sách mã SKU, không cần nạp entity:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<String> cq = cb.createQuery(String.class);
Root<Product> p = cq.from(Product.class);

cq.select(p.get("sku"))
  .where(cb.isTrue(p.get("active")))
  .orderBy(cb.asc(p.get("sku")));

List<String> skus = em.createQuery(cq).getResultList();
~~~

Các phần tử kết quả là String, không phải Product. JPA không quản lý String như entity.

### 4.1. Lấy danh sách ID

~~~java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Product> p = cq.from(Product.class);

cq.select(p.get("id"))
  .where(cb.isNull(p.get("deletedAt")));

List<Long> ids = em.createQuery(cq).getResultList();
~~~

Đây là lựa chọn phổ biến cho **pagination theo ID**, batch processing hoặc chọn tập key trước khi nạp entities. Query scalar thường giảm chi phí khởi tạo entity và persistence context so với đọc toàn bộ Product.

### 4.2. Lấy giá BigDecimal

~~~java
CriteriaQuery<BigDecimal> cq =
    cb.createQuery(BigDecimal.class);

Root<Product> p = cq.from(Product.class);

cq.select(p.get("price"))
  .where(cb.isNotNull(p.get("price")));

List<BigDecimal> prices = em.createQuery(cq).getResultList();
~~~

Dùng BigDecimal cho tiền nếu entity mapping là BigDecimal; không tự giả định JPA trả Double. Nếu không lọc NULL, List có thể chứa phần tử null tương ứng giá trị cột NULL, tùy semantics SELECT và dữ liệu.

### 4.3. Chọn một thuộc tính nullable

Giả sử 7 Product có một record giá NULL:

~~~java
CriteriaQuery<BigDecimal> cq = cb.createQuery(BigDecimal.class);
Root<Product> p = cq.from(Product.class);
cq.select(p.get("price"));

List<BigDecimal> values = em.createQuery(cq).getResultList();
~~~

Có thể nhận một phần tử null. Điều này **khác** với aggregate sum(price): aggregate tính trên một tập row và có quy tắc bỏ qua NULL, không trả từng hàng riêng lẻ.

### 4.4. Chọn distinct scalar

~~~java
CriteriaQuery<String> cq = cb.createQuery(String.class);
Root<Product> p = cq.from(Product.class);

cq.select(p.get("name"))
  .distinct(true);
~~~

**distinct(true)** loại các giá trị trùng theo semantics kết quả và SQL/provider. Nó không bảo đảm “chọn một entity theo SKU” nếu bạn đang chọn Name; hai sản phẩm cùng tên sẽ tạo cùng một scalar value và được gộp khi distinct.

### 4.5. Scalar không tự trở thành managed

Một Long ID từ Criteria không phải proxy hay Product; gọi **em.contains(id)** không hợp lệ về ý nghĩa vì đối số không phải entity. Muốn sửa Product, phải load nó:

~~~java
Product product = em.find(Product.class, id);
product.rename("Tên mới");
~~~

Không chọn scalar/DTO rồi trông chờ dirty checking.

## 5. Chọn DTO bằng constructor projection

Đối với trang danh sách sản phẩm, thường chỉ cần **ID, SKU, Name, Price**. Tạo DTO để biểu đạt hợp đồng trả về:

~~~java
package com.example.catalog.dto;

import java.math.BigDecimal;

public record ProductCard(
    Long id,
    String sku,
    String name,
    BigDecimal price
) {}
~~~

Record này là một Java value carrier; nó **không phải @Entity** và không được dirty checking. Nếu dùng Java cũ không hỗ trợ record, có thể thay bằng class public có constructor và getters tương ứng.

### 5.1. CriteriaBuilder.construct

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<ProductCard> cq =
    cb.createQuery(ProductCard.class);

Root<Product> p = cq.from(Product.class);

cq.select(cb.construct(
    ProductCard.class,
    p.get("id"),
    p.get("sku"),
    p.get("name"),
    p.get("price")
))
.where(
    cb.isTrue(p.get("active")),
    cb.isNull(p.get("deletedAt"))
)
.orderBy(cb.asc(p.get("name")));

List<ProductCard> cards = em.createQuery(cq).getResultList();
~~~

**cb.construct(ProductCard.class, ...)** diễn đạt: với mỗi hàng được chọn, provider tạo một instance ProductCard bằng constructor phù hợp với danh sách selections.

So với JPQL:

~~~java
select new com.example.catalog.dto.ProductCard(
    p.id, p.sku, p.name, p.price
)
from Product p
where p.active = true and p.deletedAt is null
order by p.name
~~~

Criteria constructor projection tránh phải đặt chuỗi tên class và danh sách field vào JPQL string.

### 5.2. Constructor cần đúng số lượng, thứ tự và kiểu

Record ProductCard có canonical constructor:

~~~java
ProductCard(Long id, String sku, String name, BigDecimal price)
~~~

Vì thế:

~~~java
cb.construct(
    ProductCard.class,
    p.get("id"),      // Long
    p.get("sku"),     // String
    p.get("name"),    // String
    p.get("price")    // BigDecimal
)
~~~

phải khớp constructor. Một lỗi thường gặp:

~~~java
cb.construct(
    ProductCard.class,
    p.get("id"),
    p.get("price"), // BigDecimal thay vì String sku
    p.get("name"),
    p.get("sku")
)
~~~

sẽ không khớp constructor dự định, có thể báo lỗi khi tạo/execute query tùy provider.

Không dựa vào các kiểu tự động chuyển đổi như **BigDecimal → Double**, **Long → Integer** hoặc **Timestamp → Instant** nếu constructor đòi kiểu khác. Cần xác định mapped Java type và result type từ Criteria.

### 5.3. DTO không phải entity một phần

Một ProductCard chứa các trường được chọn:

~~~java
ProductCard card = ...;

// Không có lazy Product.category, @Version hay dirty checking.
// Đây chỉ là dữ liệu đã được projection.
~~~

Thay một field trong DTO (nếu DTO mutable) **không làm UPDATE Product**. Khi cần cập nhật, service nên load Product managed theo ID và thực thi domain method.

DTO projection cũng không tự gây truy vấn N+1 do getter lazy entity nếu DTO chỉ chứa scalars. Nhưng **nếu DTO chứa entity reference** từ một selection khác, entity ấy vẫn có lifecycle/lazy loading riêng; DTO wrapper không xóa tác động ORM.

### 5.4. DTO để giảm lượng dữ liệu được chọn

SQL có thể tương tự:

~~~sql
SELECT p.id, p.sku, p.name, p.unit_price
FROM products p
WHERE p.active = true AND p.deleted_at IS NULL
ORDER BY p.name;
~~~

Provider chỉ cần select những expressions phục vụ DTO, không cần xây Product entity đầy đủ. Đây thường là lựa chọn tốt cho **read-only views**, list pages hoặc API responses, nhất là khi entity có nhiều thuộc tính lớn/associations.

Tuy nhiên không cam kết DTO projection luôn nhanh hơn entity trong mọi workload: join shape, index, cache, DB round trips, object allocation và query complexity vẫn quan trọng.

### 5.5. Constructor DTO là một quyết định thiết kế API

ProductCard là hợp đồng read model:
- Chỉ chứa dữ liệu cần thiết cho màn hình;
- Không lộ những trường nhạy cảm của entity;
- Có thể version độc lập với mapping nội bộ;
- Tránh JSON serialization trực tiếp các lazy associations;
- Giảm mối nối giữa HTTP API và persistence model.

Nhưng nếu sửa tên field/constructor, query projection phải được cập nhật cùng. Không tự động đổi DTO constructor khi entity property đổi.
## 6. Chọn nhiều thuộc tính bằng Object[]

Nếu chưa có DTO phù hợp, JPA có thể trả mỗi hàng thành một mảng Object.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Object[]> cq = cb.createQuery(Object[].class);
Root<Product> p = cq.from(Product.class);

cq.multiselect(
    p.get("id"),
    p.get("name"),
    p.get("price")
)
.where(cb.isTrue(p.get("active")))
.orderBy(cb.asc(p.get("id")));

List<Object[]> rows = em.createQuery(cq).getResultList();

for (Object[] row : rows) {
    Long id = (Long) row[0];
    String name = (String) row[1];
    BigDecimal price = (BigDecimal) row[2];

    System.out.println(id + " / " + name + " / " + price);
}
~~~

**Thứ tự Object[]** phụ thuộc chính thứ tự selections trong multiselect:
- row[0]: ID;
- row[1]: name;
- row[2]: price.

Không có tên field bảo vệ bạn khi người khác đổi thứ tự query.

### 6.1. Rủi ro khi dùng Object[]

Nếu đổi:

~~~java
cq.multiselect(
    p.get("name"),
    p.get("id"),
    p.get("price")
);
~~~

nhưng không đổi code ép kiểu, đoạn:

~~~java
Long id = (Long) row[0];
~~~

sẽ gặp ClassCastException vì row[0] là String.

Mảng Object[] hợp với truy vấn ngắn, ví dụ nội bộ repository, nhưng không nên để các vị trí magic numbers lan qua controller/service/reporting layer. Khi hợp đồng dữ liệu ổn định, DTO constructor rõ ràng hơn.

### 6.2. Nếu một selection có NULL

Một hàng tương ứng Product có price NULL sẽ chứa:

~~~java
row[2] == null
~~~

Điều này được phép nếu code đọc vào BigDecimal reference. Nếu cast sang primitive wrapper rồi unbox:

~~~java
double amount = ((BigDecimal) row[2]).doubleValue();
~~~

sẽ gây NullPointerException khi price NULL. Nếu nghiệp vụ cho phép thiếu giá, DTO/logic xử lý nên biểu diễn nullable đúng cách.

### 6.3. CriteriaBuilder.array

Một lựa chọn khác là:

~~~java
CriteriaQuery<Object[]> cq = cb.createQuery(Object[].class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.array(
    p.get("id"),
    p.get("sku"),
    p.get("name")
));
~~~

**cb.array(...)** tạo một compound selection kiểu Object[]. Đối với trường hợp chọn nhiều thuộc tính, **cq.multiselect(...)** thường dễ đọc hơn. Không dùng các compound selections lồng nhau tùy tiện; JPA có những giới hạn đối với tuple-valued/array-valued selection làm phần tử của multiselect.

### 6.4. Một cột khác với nhiều cột

~~~java
CriteriaQuery<String> cq = cb.createQuery(String.class);
Root<Product> p = cq.from(Product.class);
cq.select(p.get("sku"));
~~~

trả List<String>. Nếu đổi thành:

~~~java
CriteriaQuery<Object[]> cq = cb.createQuery(Object[].class);
Root<Product> p = cq.from(Product.class);
cq.multiselect(p.get("sku"), p.get("name"));
~~~

trả List<Object[]>. **Kiểu của CriteriaQuery quyết định hình dạng một hàng kết quả**. Không viết code xử lý Object[] khi query thực sự trả scalar.

## 7. Tuple: nhiều giá trị nhưng có alias rõ ràng

**Tuple** là lựa chọn có cấu trúc hơn Object[]. Nó chứa nhiều selection trong một hàng, hỗ trợ lấy giá trị theo:
- **Vị trí**: get(0), get(1);
- **Alias**: get("id"), get("price");
- **TupleElement**: get(element) nếu cần khai thác metadata các selections.

### 7.1. Tạo CriteriaQuery<Tuple>

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Product> p = cq.from(Product.class);

cq.multiselect(
    p.get("id").alias("id"),
    p.get("sku").alias("sku"),
    p.get("price").alias("price")
)
.where(cb.isTrue(p.get("active")))
.orderBy(cb.asc(p.get("id")));

List<Tuple> rows = em.createQuery(cq).getResultList();
~~~

Cách đọc:

~~~java
for (Tuple row : rows) {
    Long id = row.get("id", Long.class);
    String sku = row.get("sku", String.class);
    BigDecimal price = row.get("price", BigDecimal.class);

    System.out.println(id + " " + sku + " " + price);
}
~~~

**Alias** phải được đặt chính xác và duy nhất trong selection để code truy cập theo tên. Nếu alias không tồn tại, hoặc yêu cầu type không phù hợp với giá trị, Tuple API có thể ném IllegalArgumentException.

### 7.2. Lấy theo vị trí

~~~java
Tuple first = rows.get(0);

Long id = first.get(0, Long.class);
String sku = first.get(1, String.class);
BigDecimal price = first.get(2, BigDecimal.class);
~~~

Đọc theo vị trí giống Object[] về rủi ro khi thay thứ tự selections. Đọc theo alias dễ theo dõi hơn, nhất là với báo cáo có nhiều trường.

### 7.3. Lấy bằng TupleElement

~~~java
Tuple first = rows.get(0);

for (TupleElement<?> element : first.getElements()) {
    String alias = element.getAlias();
    Class<?> javaType = element.getJavaType();
    Object value = first.get(element);

    System.out.println(alias + " [" + javaType + "] = " + value);
}
~~~

**getElements()** trả danh sách metadata của các trường thuộc Tuple. Nó hữu ích cho những màn hình báo cáo tạo cột động, CSV exporter hoặc công cụ kiểm tra kết quả.

Chú ý **Tuple metadata** là metadata của các selections, không phải metadata cột vật lý của toàn bộ bảng. Alias có thể null nếu query không đặt tên; trường hợp đó không nên tùy tiện dùng alias như khóa bản đồ.

### 7.4. Chọn Tuple bằng cb.tuple(...)

Thay vì multiselect:

~~~java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Product> p = cq.from(Product.class);

cq.select(cb.tuple(
    p.get("id").alias("id"),
    p.get("name").alias("name"),
    p.get("price").alias("price")
));
~~~

**cb.tuple(...)** tạo một compound selection kiểu Tuple. Cả cách này và **cq.multiselect(...)** đều phù hợp; chọn phong cách thống nhất trong dự án.

### 7.5. Alias chỉ là tên projection

Alias **"price"** trong:

~~~java
p.get("price").alias("price")
~~~

không đổi tên thuộc tính của entity, không tạo DB column mới, không ảnh hưởng schema. Nó chỉ đặt tên cho selection trong truy vấn.

Ví dụ:

~~~java
cb.sum(p.<BigDecimal>get("price")).alias("totalPrice")
~~~

cho phép đọc giá trị aggregate theo tên **totalPrice** từ Tuple. Không bắt buộc alias phải giống property Java.

### 7.6. Lỗi alias trùng nhau

Không nên:

~~~java
cq.multiselect(
    p.get("sku").alias("value"),
    p.get("name").alias("value")
);
~~~

Trong compound selection, JPA yêu cầu alias được gán không trùng nhau; trường hợp này có thể gây IllegalArgumentException khi xây query. Dùng các alias ổn định và khác biệt như **sku**, **productName**.

### 7.7. Tuple dùng tốt cho báo cáo động

Ví dụ người dùng được chọn các cột báo cáo:
- SKU và Name;
- SKU, Name và Price;
- SKU, Price và CategoryName.

Nếu mỗi tổ hợp có số trường khác nhau, dùng một DTO riêng cho mọi biến thể có thể cồng kềnh. Tuple kết hợp với danh sách Selection được tạo có kiểm soát giúp đọc cột theo alias.

Nhưng không nhận tên property do người dùng gửi rồi gọi thẳng **p.get(userInput)** mà không whitelist: người dùng có thể yêu cầu trường nhạy cảm, field không tồn tại hoặc path khó tối ưu. Hãy xây một registry những cột được phép.

### 7.8. Tuple không phải entity và không có dirty checking

~~~java
Tuple row = ...;
BigDecimal price = row.get("price", BigDecimal.class);
~~~

Giá trị này chỉ là một phần của kết quả truy vấn. Không thể thay giá trị trong Tuple rồi mặc định Product được update. Nếu chọn cả chính Product:

~~~java
cq.multiselect(
    p.alias("product"),
    p.get("price").alias("price")
);
~~~

thì **row.get("product", Product.class)** là entity selection và có thể managed; **row.get("price", BigDecimal.class)** là scalar. Tuple wrapper không làm entity mất lifecycle, nhưng cũng không tự tạo lifecycle cho các scalars còn lại.

## 8. DTO, Object[] và Tuple: chọn kiểu nào?

| Tiêu chí | DTO constructor | Object[] | Tuple |
|---|---|---|---|
| Kiểu kết quả | Class/record của ứng dụng | Mảng Object | jakarta.persistence.Tuple |
| Truy cập field | Tên property/accessor DTO | Chỉ số | Alias, index, TupleElement |
| Kiểm soát contract | Rõ ràng, ổn định | Yếu | Tương đối rõ khi alias nhất quán |
| Dễ sửa cấu trúc query | Phải sửa DTO/constructor | Dễ lệch chỉ số | Dễ đổi alias/selection |
| Dùng cho API response | Phù hợp | Không khuyến khích truyền trực tiếp | Nên map ra DTO/response |
| Hợp với report cột động | Ít phù hợp hơn | Có thể, nhưng khó đọc | Phù hợp |
| Managed entity? | Không, nếu chỉ scalar fields | Không | Không, trừ entity được chọn làm một trường |
| Rủi ro runtime | Constructor không khớp | ClassCastException do index | Alias/type không khớp |

Quy tắc thực dụng:

1. **Cần sửa entity hoặc xử lý domain lifecycle:** chọn entity.
2. **Read model cố định cho API/service:** chọn DTO.
3. **Chỉ cần một trường:** chọn scalar.
4. **Báo cáo động hoặc truy vấn chưa có DTO:** chọn Tuple.
5. **Đoạn truy vấn rất ngắn, chỉ dùng nội bộ:** Object[] có thể chấp nhận nhưng nên giới hạn phạm vi.

### 8.1. Type safety có giới hạn

CriteriaQuery<T> cung cấp thông tin generic để compiler biết kiểu result. Nhưng khi dùng đường dẫn string:

~~~java
p.get("price")
~~~

compiler chưa tự xác minh rằng entity thật có property price hay giá trị trả về chính xác là BigDecimal. Lỗi tên property và constructor matching vẫn có thể xuất hiện lúc chạy.

Có thể dùng static metamodel được generate:

~~~java
p.get(Product_.price)
~~~

khi dự án cấu hình JPA metamodel generator và class Product_ tồn tại. Cách này có thể tăng mức kiểm tra kiểu tại compile time. **Product_ không có sẵn tự động trong mọi dự án**; ví dụ còn lại dùng string-based paths để dễ học và chạy với setup tối thiểu.

### 8.2. Projection không thay thế authorization

Nếu entity có **costPrice**, **secretNote** hoặc thông tin khách hàng nhạy cảm, việc DTO chỉ chọn field công khai có lợi cho API. Nhưng bạn vẫn phải kiểm soát:
- Ai được quyền xem Product này?
- Tenant/owner filter có luôn áp dụng?
- Có row soft-deleted cần loại?
- Có property được chọn không được phép lộ?

Chọn DTO không tự xác thực người dùng hay áp điều kiện bảo mật.
## 9. Giá trị tổng hợp (aggregate): đếm, tổng, trung bình, nhỏ nhất và lớn nhất

Các hàm tổng hợp cho phép database xử lý tập dữ liệu và trả một hoặc vài con số thay vì nạp từng entity để tính bằng Java.

Những hàm CriteriaBuilder thường dùng:

| Phương thức | Ý nghĩa | Kiểu kết quả tiêu biểu |
|---|---|---|
| cb.count(expression) | Đếm số giá trị không NULL; count(root) đếm rows | Long |
| cb.countDistinct(expression) | Đếm số giá trị phân biệt không NULL | Long |
| cb.sum(expression) | Tổng giá trị numeric phù hợp | Theo kiểu biểu thức, cần xét loại số |
| cb.sumAsLong(integerExpression) | Tổng các giá trị integral kiểu Integer theo Long | Long |
| cb.sumAsDouble(floatExpression) | Tổng Float theo Double | Double |
| cb.avg(expression) | Trung bình cộng các giá trị numeric khác NULL | Double |
| cb.min(expression) | Giá trị số nhỏ nhất | Cùng kiểu numeric thích hợp |
| cb.max(expression) | Giá trị số lớn nhất | Cùng kiểu numeric thích hợp |
| cb.greatest(expression) | Giá trị lớn nhất của biểu thức Comparable | Kiểu comparable |
| cb.least(expression) | Giá trị nhỏ nhất của biểu thức Comparable | Kiểu comparable |

Các phương thức đều tạo **Expression<T>**, không thực thi query ngay tại lúc gọi. Query thực sự chạy khi dùng **em.createQuery(cq).getResultList/getSingleResult**.

### 9.1. COUNT: số lượng toàn bộ Product

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.count(p));

Long productCount = em.createQuery(cq).getSingleResult();
~~~

Với dataset 7 Product, kết quả là **7** nếu không có filter khác.

**cb.count(p)** đếm row entity Product thuộc tập kết quả. Kết quả JPA chuẩn của COUNT là **Long**, không phải Integer.

Một query có WHERE:

~~~java
cq.select(cb.count(p))
  .where(cb.isTrue(p.get("active")));
~~~

cho **5** Product active (P01, P02, P03, P05, P06).

### 9.2. COUNT(expression) khác COUNT(root)

Nếu price nullable:

~~~java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.count(p.get("price")));

Long withPrice = em.createQuery(cq).getSingleResult();
~~~

Dữ liệu mẫu có một Product giá NULL nên **count(price) = 6**, trong khi **count(p) = 7**.

Giải thích:

~~~text
COUNT(Product rows)        = 7
COUNT(non-NULL price)      = 6
Số Product có price NULL   = 1
~~~

Một cách đếm giá NULL là đặt WHERE:

~~~java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.count(p))
  .where(cb.isNull(p.get("price")));

Long withoutPrice = em.createQuery(cq).getSingleResult();
~~~

Kết quả là **1**.

Không dùng **count(price)** rồi mong nó tính cả các giá trị NULL. Đó là khác biệt quan trọng giữa COUNT trên root và COUNT trên một thuộc tính nullable.

### 9.3. COUNT DISTINCT

Nếu muốn đếm số giá khác nhau:

~~~java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.countDistinct(p.get("price")));
~~~

Kết quả trong dataset là 6 vì sáu mức giá không NULL đều khác nhau. Nếu hai Product cùng giá, **countDistinct(price)** sẽ nhỏ hơn **count(price)**.

COUNT DISTINCT không có nghĩa “số entity khác nhau” trong mọi truy vấn; nó đếm những giá trị phân biệt của **biểu thức đã chọn**. Ví dụ:
- countDistinct(price) đếm các mức giá;
- countDistinct(category.id) đếm số category ID xuất hiện trên các Product có association, bỏ giá trị NULL theo aggregate semantics;
- countDistinct(product.id) đếm các Product ID phân biệt.

### 9.4. SUM: tổng giá

Với price BigDecimal:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<BigDecimal> cq =
    cb.createQuery(BigDecimal.class);

Root<Product> p = cq.from(Product.class);

cq.select(cb.sum(p.<BigDecimal>get("price")));

BigDecimal total = em.createQuery(cq).getSingleResult();
~~~

Với dataset:

~~~text
12.000.000
+  350.000
+  950.000
+2.500.000
+  100.000
+3.500.000
------------
19.400.000 VND
~~~

P05 có price NULL nên **không đóng góp vào tổng**. SUM không tự hiểu NULL là một giá trị giá bằng 0 về mặt nghiệp vụ; nó bỏ qua NULL theo aggregate semantics.

Nếu lọc active:

~~~java
cq.select(cb.sum(p.<BigDecimal>get("price")))
  .where(cb.isTrue(p.get("active")));
~~~

kết quả là **13.400.000** vì P04 và P07 inactive, P05 active nhưng price NULL nên không cộng.

### 9.5. SUM trên Integer: dùng sumAsLong khi cần

Một trường stockQuantity được mapping Integer:

~~~java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.sumAsLong(p.<Integer>get("stockQuantity")));

Long stockTotal = em.createQuery(cq).getSingleResult();
~~~

Kết quả với mẫu là 3 + 20 + 5 + 0 + 10 + 2 = **40** (P05 NULL không đóng góp).

**sumAsLong** thể hiện rõ kỳ vọng kết quả Long khi cộng nhiều giá trị Integer, tránh một số nhầm lẫn về kiểu tổng và khả năng tràn số nguyên nhỏ.

### 9.6. AVG: trung bình có kiểu Double

~~~java
CriteriaQuery<Double> cq = cb.createQuery(Double.class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.avg(p.<BigDecimal>get("price")));

Double average = em.createQuery(cq).getSingleResult();
~~~

AVG theo JPA trả kiểu **Double** cho biểu thức số. Với dataset, mẫu số là **6** giá không NULL, không phải 7 Product:

~~~text
19.400.000 / 6 ≈ 3.233.333,33 VND
~~~

**Lưu ý với dữ liệu tiền tệ:** Double là kiểu dấu chấm động nhị phân, có thể không biểu diễn chính xác mọi giá trị decimal. Nếu cần tính tiền pháp lý, thuế hoặc tỷ giá với chính sách làm tròn, thiết kế tính toán bằng BigDecimal và rounding rules được kiểm soát; không dùng kết quả AVG Double trực tiếp như số tiền đã chuẩn hóa. Có thể đưa SUM BigDecimal và COUNT vào DTO, rồi tính trung bình bằng BigDecimal ở service với MathContext hoặc RoundingMode phù hợp.

### 9.7. MIN và MAX

~~~java
CriteriaQuery<BigDecimal> cqMin =
    cb.createQuery(BigDecimal.class);

Root<Product> pMin = cqMin.from(Product.class);
cqMin.select(cb.min(pMin.<BigDecimal>get("price")));

BigDecimal lowest = em.createQuery(cqMin).getSingleResult();
~~~

Tương tự với MAX:

~~~java
CriteriaQuery<BigDecimal> cqMax =
    cb.createQuery(BigDecimal.class);

Root<Product> pMax = cqMax.from(Product.class);
cqMax.select(cb.max(pMax.<BigDecimal>get("price")));

BigDecimal highest = em.createQuery(cqMax).getSingleResult();
~~~

Trong dataset:
- MIN(price) = **100.000** (P06);
- MAX(price) = **12.000.000** (P01).

Cả hai không tính NULL như số 0. Nếu có tất cả price NULL hoặc không có rows phù hợp, kết quả có thể là NULL.

### 9.8. MIN/MAX với thuộc tính không phải số

Với một thuộc tính kiểu Comparable phù hợp như ngày giờ, CriteriaBuilder có **least** và **greatest**:

~~~java
CriteriaQuery<Instant> cq = cb.createQuery(Instant.class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.greatest(p.<Instant>get("deletedAt")));

Instant latestDeletion = em.createQuery(cq).getSingleResult();
~~~

Nếu toàn bộ deletedAt NULL, latestDeletion là NULL theo aggregate semantics. Dùng **greatest/least** khi muốn lấy cực trị kiểu Comparable, còn **min/max** phù hợp cho numeric.

### 9.9. Aggregate trên tập rỗng

Tình huống:

~~~java
Predicate impossible = cb.equal(p.get("sku"), "DOES-NOT-EXIST");
~~~

Nếu WHERE không chọn row nào, truy vấn aggregate **không có GROUP BY** thường có một hàng kết quả:
- **COUNT** trả **0L**;
- **SUM** trả **null**;
- **AVG** trả **null**;
- **MIN/MAX** trả **null**.

Phân biệt:
- “Có một row chứa số 0/null từ aggregate toàn tập”;
- “Không có group nào, nên query GROUP BY trả danh sách rỗng”.

Điều này quan trọng khi lựa chọn **getSingleResult()** hay **getResultList()**.

### 9.10. COALESCE khi cần tổng bằng 0

Nếu nghiệp vụ muốn tổng bằng BigDecimal.ZERO khi tập không có giá trị:

~~~java
CriteriaQuery<BigDecimal> cq =
    cb.createQuery(BigDecimal.class);
Root<Product> p = cq.from(Product.class);

Expression<BigDecimal> sumPrice =
    cb.sum(p.<BigDecimal>get("price"));

cq.select(cb.coalesce(sumPrice, BigDecimal.ZERO));
~~~

COALESCE thay giá trị NULL của **aggregate result** bằng 0, không thêm giả một Product có giá 0. Việc này khác với đổi mọi giá NULL thành 0 trước khi tính trung bình: hai cách có thể cho AVG khác nhau.

## 10. Kết hợp nhiều aggregates trong một Tuple

Màn hình dashboard thường cần cùng lúc:
- Số Product;
- Số Product đã có giá;
- Tổng giá;
- Giá thấp nhất và cao nhất.

Một query có thể chọn nhiều aggregate expressions:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Product> p = cq.from(Product.class);

cq.multiselect(
    cb.count(p).alias("productCount"),
    cb.count(p.get("price")).alias("pricedCount"),
    cb.sum(p.<BigDecimal>get("price")).alias("totalPrice"),
    cb.min(p.<BigDecimal>get("price")).alias("minimumPrice"),
    cb.max(p.<BigDecimal>get("price")).alias("maximumPrice")
);

Tuple summary = em.createQuery(cq).getSingleResult();

Long productCount = summary.get("productCount", Long.class);
Long pricedCount = summary.get("pricedCount", Long.class);
BigDecimal totalPrice = summary.get("totalPrice", BigDecimal.class);
BigDecimal minPrice = summary.get("minimumPrice", BigDecimal.class);
BigDecimal maxPrice = summary.get("maximumPrice", BigDecimal.class);
~~~

Với 7 Product trong dataset:
- productCount = 7;
- pricedCount = 6;
- totalPrice = 19.400.000;
- minimumPrice = 100.000;
- maximumPrice = 12.000.000.

Một query aggregate như vậy có thể tiết kiệm round trips so với thực hiện năm query riêng. Tuy nhiên SQL query plan và chi phí tính tổng phụ thuộc dữ liệu/index/DB.

### 10.1. DTO cho dashboard ổn định

Nếu dashboard có hợp đồng cố định, tạo:

~~~java
public record ProductMetrics(
    Long productCount,
    Long pricedCount,
    BigDecimal totalPrice,
    BigDecimal minimumPrice,
    BigDecimal maximumPrice
) {}
~~~

Và:

~~~java
CriteriaQuery<ProductMetrics> cq =
    cb.createQuery(ProductMetrics.class);
Root<Product> p = cq.from(Product.class);

cq.select(cb.construct(
    ProductMetrics.class,
    cb.count(p),
    cb.count(p.get("price")),
    cb.sum(p.<BigDecimal>get("price")),
    cb.min(p.<BigDecimal>get("price")),
    cb.max(p.<BigDecimal>get("price"))
));

ProductMetrics metrics = em.createQuery(cq).getSingleResult();
~~~

Một query có thể dựng **DTO aggregate** trực tiếp. Không có quy tắc “aggregates phải dùng Tuple”; Tuple chỉ là một trong các cách nhận nhiều values.

### 10.2. Dùng DTO hay Tuple cho metrics?

**DTO** tốt khi:
- Dashboard có trường cố định;
- API muốn type contract rõ ràng;
- Có logic hiển thị/formatting riêng.

**Tuple** tốt khi:
- Người dùng có thể chọn một số metrics động;
- Query builder cần alias linh hoạt;
- Bộ báo cáo không muốn tạo class DTO cho mọi tổ hợp.

Khi metrics được đưa ra API công khai, thường nên map Tuple sang response DTO thay vì expose trực tiếp object Tuple cho JSON serializer.

## 11. GROUP BY: tổng hợp theo nhóm

Khi query tổng hợp cho từng Category, cần phân biệt:
- Aggregate toàn tập: một con số/tập metrics;
- Aggregate theo nhóm: một hàng kết quả cho mỗi nhóm.

### 11.1. Ví dụ tổng hợp theo categoryId và categoryName

Để giữ các Product **không có Category**, ta dùng **LEFT JOIN**.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<Product> p = cq.from(Product.class);
Join<Product, Category> c =
    p.join("category", JoinType.LEFT);

Path<Long> categoryId = c.get("id");
Path<String> categoryName = c.get("name");
Expression<Long> count = cb.count(p);
Expression<BigDecimal> totalPrice =
    cb.sum(p.<BigDecimal>get("price"));

cq.multiselect(
    categoryId.alias("categoryId"),
    categoryName.alias("categoryName"),
    count.alias("productCount"),
    totalPrice.alias("totalPrice")
)
.groupBy(categoryId, categoryName)
.orderBy(cb.asc(categoryName));

List<Tuple> report = em.createQuery(cq).getResultList();
~~~

Đọc kết quả:

~~~java
for (Tuple row : report) {
    Long id = row.get("categoryId", Long.class);
    String name = row.get("categoryName", String.class);
    Long number = row.get("productCount", Long.class);
    BigDecimal total = row.get("totalPrice", BigDecimal.class);

    System.out.println(
        (name == null ? "(Chưa phân loại)" : name)
        + " / " + number
        + " / " + total
    );
}
~~~

Dữ liệu mẫu cho kết quả logic:

| Category | Product count | Total price |
|---|---:|---:|
| Electronics | 3 | 15.850.000 |
| Furniture | 2 | 3.450.000 |
| NULL (chưa phân loại) | 2 | 100.000 |

Không suy ra thứ tự hàng từ bảng này; thứ tự khi CategoryName NULL tùy DB nếu không kiểm soát NULL ordering cụ thể.

### 11.2. Vì sao cần GROUP BY các field không phải aggregate?

Trong SELECT có:
- categoryId;
- categoryName;
- COUNT(Product);
- SUM(price).

Với truy vấn tổng hợp theo nhóm, những biểu thức selected **không nằm trong aggregate** phải được group tương ứng theo các quy tắc JPQL/SQL. Ở ví dụ, cả categoryId và categoryName đều được đưa vào groupBy.

Nếu chỉ group theo tên category mà hai Category khác ID trùng tên, bạn có thể gộp nhầm dữ liệu của hai Category. **Group theo identity (ID) và tên** giúp báo cáo chính xác theo category entity.

### 11.3. LEFT JOIN rất quan trọng

Nếu đổi thành:

~~~java
Join<Product, Category> c =
    p.join("category", JoinType.INNER);
~~~

Product P05 và P06 không có Category bị loại khỏi kết quả trước khi grouping. Khi đó báo cáo chỉ có Electronics và Furniture, thiếu nhóm “Chưa phân loại”.

Đây không phải lỗi CriteriaBuilder.count mà là tác động của **join type**.

### 11.4. GROUP BY NULL

Với LEFT JOIN, Product không có Category mang NULL ở c.id và c.name. Khi GROUP BY hai field đó, chúng có thể được gộp thành một nhóm NULL. Group đó vẫn có Product rows nên count(p) = 2; SUM(price) bỏ price NULL của P05 và cộng 100.000 của P06.

Nếu toàn bộ Product trong nhóm chưa phân loại đều có price NULL, **SUM(price)** cho nhóm ấy là NULL, trừ khi dùng COALESCE trong selection.

### 11.5. GroupBy không tự loại dữ liệu soft-deleted

Trong query mẫu, mọi Product được tính, không có WHERE. Nếu hệ thống dùng soft delete, thêm:

~~~java
cq.where(cb.isNull(p.get("deletedAt")));
~~~

trước khi execute query. Đây là điều kiện chọn rows **trước khi grouping**, không phải phần của GROUP BY.

### 11.6. GROUP BY không phải DISTINCT

- **distinct(true)** loại bản ghi kết quả trùng theo các selected values;
- **groupBy(...)** chia source rows thành nhóm để tính các aggregate;
- **countDistinct(...)** đếm những giá trị khác nhau trong một tập hoặc nhóm.

Ba khái niệm có liên quan nhưng không thể thay thế tùy tiện.

## 12. HAVING: lọc nhóm bằng aggregate

WHERE áp dụng lên **source rows** trước khi group; HAVING áp dụng lên **nhóm đã được tính tổng hợp**.

Ví dụ chỉ lấy Category có **trên 2 Product**:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<Product> p = cq.from(Product.class);
Join<Product, Category> c =
    p.join("category", JoinType.LEFT);

Path<Long> categoryId = c.get("id");
Path<String> categoryName = c.get("name");
Expression<Long> count = cb.count(p);

cq.multiselect(
    categoryId.alias("categoryId"),
    categoryName.alias("categoryName"),
    count.alias("productCount")
)
.groupBy(categoryId, categoryName)
.having(cb.gt(count, 2L));

List<Tuple> rows = em.createQuery(cq).getResultList();
~~~

Trong dataset, Electronics có 3 Product nên được giữ. Furniture và nhóm NULL mỗi nhóm có 2 Product nên bị loại.

### 12.1. Không viết aggregate predicate trong WHERE

Ví dụ ý tưởng sai:

~~~java
cq.where(cb.gt(cb.count(p), 2L));
~~~

WHERE không phải vị trí đúng để lọc giá trị COUNT sau GROUP BY. Dùng:

~~~java
cq.having(cb.gt(cb.count(p), 2L));
~~~

Hãy đặt điều kiện lên entity rows trước grouping vào WHERE, và điều kiện lên aggregate/group vào HAVING.

### 12.2. WHERE và HAVING cùng tồn tại

Yêu cầu: với **Product đang active**, tìm Category có **ít nhất hai Product active**.

~~~java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Product> p = cq.from(Product.class);
Join<Product, Category> c =
    p.join("category", JoinType.LEFT);

Path<Long> categoryId = c.get("id");
Path<String> categoryName = c.get("name");
Expression<Long> number = cb.count(p);

cq.multiselect(
    categoryId.alias("categoryId"),
    categoryName.alias("categoryName"),
    number.alias("activeCount")
)
.where(cb.isTrue(p.get("active")))
.groupBy(categoryId, categoryName)
.having(cb.ge(number, 2L));
~~~

Trước tiên WHERE loại inactive Products (P04, P07), sau đó grouping:
- Electronics: P01/P02 → 2;
- Furniture: P03 → 1;
- NULL: P05/P06 → 2.

HAVING giữ Electronics và NULL, loại Furniture.

### 12.3. Group query có thể không trả hàng nào

Nếu HAVING yêu cầu **count > 100** với dataset nhỏ, query trả **List<Tuple> rỗng**, không phải một Tuple có count = 0. Điều này khác COUNT toàn tập không có GROUP BY, vốn trả một hàng chứa 0 khi không có source rows.

Vì vậy **getResultList()** thường phù hợp cho GROUP BY/HAVING; **getSingleResult()** chỉ phù hợp khi thiết kế query thực sự bảo đảm một nhóm.

### 12.4. HAVING với tổng

~~~java
Expression<BigDecimal> total =
    cb.sum(p.<BigDecimal>get("price"));

cq.having(cb.greaterThan(
    total, new BigDecimal("1000000.00")
));
~~~

Điều kiện này chỉ giữ các nhóm có SUM(price) lớn hơn 1.000.000. Nếu SUM của một nhóm là NULL, so sánh với ngưỡng dẫn tới UNKNOWN, nhóm đó không được chọn; nếu muốn coi SUM NULL bằng 0 theo nghiệp vụ, dùng COALESCE rõ ràng.
## 13. JOIN và DISTINCT: khi một entity xuất hiện nhiều lần

Kết quả tổng hợp thường sai không phải do COUNT, mà do **JOIN tạo ra nhiều row**. Nếu Category có collection Products:

~~~java
@OneToMany(mappedBy = "category")
private List<Product> products = new ArrayList<>();
~~~

và truy vấn:

~~~java
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Category> c = cq.from(Category.class);
Join<Category, Product> p = c.join("products", JoinType.INNER);

cq.select(cb.count(c));
~~~

COUNT(c) đếm **rows của kết quả JOIN**: Electronics có ba Products và Furniture có hai Products nên count(c) = 5, **không phải hai Category**. Muốn đếm danh mục khác nhau có ít nhất một sản phẩm:

~~~java
cq.select(cb.countDistinct(c.get("id")));
~~~

kết quả là 2.

### 13.1. LEFT JOIN và COUNT(child)

Nếu muốn liệt kê cả Category chưa có Product:

~~~java
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Category> c = cq.from(Category.class);
Join<Category, Product> p = c.join("products", JoinType.LEFT);

cq.multiselect(
    c.get("id").alias("categoryId"),
    c.get("name").alias("categoryName"),
    cb.count(p).alias("productCount")
)
.groupBy(c.get("id"), c.get("name"));
~~~

Với Category rỗng, LEFT JOIN giữ một row Category nhưng phần child NULL. **COUNT(p) = 0**. Ngược lại **COUNT(c)** có thể bằng 1 cho group đó. Để đếm children, chọn đúng joined child trong COUNT.

### 13.2. Hai hướng báo cáo cho kết quả khác nhau

- Bắt đầu từ **Product** và LEFT JOIN Category: có thể có nhóm “chưa phân loại” của P05/P06, nhưng không có Category rỗng.
- Bắt đầu từ **Category** và LEFT JOIN Products: có thể có Category với count 0, nhưng không tạo nhóm những Product chưa gán Category.

Việc chọn **Root** quyết định domain của tập rows trước khi group.

### 13.3. DISTINCT không phải GROUP BY

Ví dụ:

~~~java
CriteriaQuery<Category> cq = cb.createQuery(Category.class);
Root<Category> c = cq.from(Category.class);
Join<Category, Product> p = c.join("products", JoinType.INNER);

cq.select(c).distinct(true);
~~~

DISTINCT ở đây yêu cầu các Category entities khác nhau trong kết quả. Với Tuple gồm CategoryName và SKU, DISTINCT chỉ loại những tổ hợp **(Name, SKU)** trùng; ba SKU của Electronics vẫn là ba rows khác nhau. Muốn một row mỗi Category kèm COUNT thì phải GROUP BY.

Không dựa vào việc persistence context dùng identity map để khẳng định một List của query có to-many JOIN không thể chứa cùng managed entity reference nhiều lần. Việc loại trùng theo yêu cầu là phần của query.

### 13.4. Không dùng fetch join để tính COUNT

**join()** giúp lọc hoặc group associations. **fetch()** dùng để nạp graph khi select entity; fetch join trong aggregate count query thường không phù hợp và có thể gây lỗi/SQL dư. Với truy vấn chỉ tính số liệu, chọn scalar/DTO/Tuple và regular joins.

## 14. DTO lấy dữ liệu từ nhiều entity

Ví dụ trang card cần Product ID, Name, Price và CategoryName:

~~~java
public record ProductWithCategory(
    Long id,
    String name,
    BigDecimal price,
    String categoryName
) {}
~~~

Projection:

~~~java
CriteriaQuery<ProductWithCategory> cq =
    cb.createQuery(ProductWithCategory.class);

Root<Product> p = cq.from(Product.class);
Join<Product, Category> c =
    p.join("category", JoinType.LEFT);

cq.select(cb.construct(
    ProductWithCategory.class,
    p.get("id"),
    p.get("name"),
    p.get("price"),
    c.get("name")
))
.where(cb.isNull(p.get("deletedAt")))
.orderBy(cb.asc(p.get("sku")));
~~~

**LEFT JOIN** giữ P05/P06 với categoryName NULL. Nếu dùng INNER JOIN, hai Product ấy biến mất khỏi kết quả, dù DTO cho phép String categoryName là null.

### 14.1. DTO chứa entity reference cần cân nhắc

Một DTO constructor có thể nhận Category entity, nhưng khi trả qua API sẽ kéo theo lifecycle, lazy associations và serialization concerns. Nếu màn hình chỉ cần tên, ưu tiên **c.get("name")** scalar. DTO không tự vô hiệu hóa lazy loading của một entity được đặt bên trong nó.

### 14.2. Không làm I/O trong constructor DTO

Constructor DTO nên gán các values đã được select. Nếu constructor gọi repository/remote service hoặc truy cập lazy association, một query trả nhiều hàng có thể gây N+1 hoặc side effects bất ngờ. Enrichment phức tạp nên được tổ chức riêng theo batch.

## 15. DTO tổng hợp theo nhóm

Báo cáo ổn định có thể dùng record:

~~~java
public record CategorySummary(
    Long categoryId,
    String categoryName,
    Long productCount,
    BigDecimal totalPrice
) {}
~~~

Và:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<CategorySummary> cq =
    cb.createQuery(CategorySummary.class);

Root<Product> p = cq.from(Product.class);
Join<Product, Category> c =
    p.join("category", JoinType.LEFT);

Path<Long> categoryId = c.get("id");
Path<String> categoryName = c.get("name");
Expression<Long> count = cb.count(p);
Expression<BigDecimal> total =
    cb.sum(p.<BigDecimal>get("price"));

cq.select(cb.construct(
    CategorySummary.class,
    categoryId,
    categoryName,
    count,
    total
))
.groupBy(categoryId, categoryName)
.orderBy(cb.asc(categoryName));

List<CategorySummary> summaries =
    em.createQuery(cq).getResultList();
~~~

Không có yêu cầu “aggregate phải trả Tuple”. **Constructor projection** vẫn kết hợp được COUNT/SUM và GROUP BY.

Nếu chỉ cần những nhóm có count từ 2 trở lên:

~~~java
cq.having(cb.ge(count, 2L));
~~~

Với soft delete hoặc active filter, thêm WHERE để xác định các source rows được đưa vào nhóm.

### 15.1. Nhóm có tổng NULL

Nếu mọi Product trong một nhóm đều có price NULL, SUM(price) trả NULL. DTO.totalPrice kiểu BigDecimal có thể null. Khi báo cáo muốn dùng 0, thay total bằng:

~~~java
Expression<BigDecimal> displayedTotal =
    cb.coalesce(total, BigDecimal.ZERO);
~~~

Đó là quyết định về semantics của báo cáo, không phải quy tắc mọi NULL tự được coi là 0.

### 15.2. Không group theo tên khi cần identity

Hai Category khác ID có thể cùng Name. Nếu GROUP BY chỉ theo c.name, hai nhóm bị gộp. Khi mục tiêu là mỗi **Category entity** có một row, group theo categoryId và categoryName.

## 16. Multiselect phụ thuộc CriteriaQuery result type

Cùng một danh sách selections có thể tạo kết quả khác nhau:

| Result type | Lệnh gợi ý | Một row trả về |
|---|---|---|
| CriteriaQuery<Product> | cq.select(root) | Product entity |
| CriteriaQuery<Long> | cq.select(cb.count(root)) | Long scalar |
| CriteriaQuery<Tuple> | cq.multiselect(...) | Tuple |
| CriteriaQuery<Object[]> | cq.multiselect(...) | Object[] |
| CriteriaQuery<ProductCard> | cq.select(cb.construct(...)) | ProductCard DTO |

Với CriteriaQuery của một user-defined class và multiselect tương thích constructor, spec có quy tắc dựng object tương ứng. Nhưng để code biểu đạt mục đích rõ ràng, **cb.construct(ProductCard.class, ...)** thường dễ đọc hơn.

### 16.1. Tránh Object result type nếu hình dạng đã biết

CriteriaQuery<Object> với nhiều selections có những quy tắc trả scalar/array tùy hình dạng. Nếu caller cần type cố định, chọn CriteriaQuery<T> cụ thể để giảm ép kiểu và đoán runtime shape.

### 16.2. Compound selection lồng nhau có giới hạn

Không mặc định rằng:

~~~java
cq.multiselect(
    cb.tuple(p.get("id"), p.get("name")),
    p.get("price")
);
~~~

là một cách portable để tạo Tuple lồng bên trong Tuple hoặc Object[]. JPA có giới hạn với tuple-/array-valued compound selections lồng. Nếu cần dữ liệu lồng sâu, chọn scalars phẳng và dựng cấu trúc Java sau truy vấn, hoặc thiết kế DTO thích hợp.

### 16.3. Alias của selections phải duy nhất

~~~java
cq.multiselect(
    p.get("sku").alias("value"),
    p.get("name").alias("value")
);
~~~

đặt trùng alias là không hợp lệ cho compound selection. Đặt tên theo ý nghĩa như sku và productName; khi đọc Tuple bằng alias, phải sử dụng đúng tên đã định nghĩa.

## 17. Tổng hợp với NULL và không có row

Với bộ dữ liệu mẫu:

| Phép tổng hợp | Kết quả | Lưu ý |
|---|---:|---|
| COUNT(p) | 7 | Đếm Product |
| COUNT(p.price) | 6 | Bỏ Product có giá NULL |
| COUNT DISTINCT price | 6 | Sáu mức giá khác nhau |
| SUM(price) | 19.400.000 | Bỏ NULL |
| AVG(price) | ~3.233.333,33 | Chia cho 6 giá có giá trị |
| MIN(price) | 100.000 | Giá thấp nhất đã biết |
| MAX(price) | 12.000.000 | Giá cao nhất |
| SUM(stockQuantity) | 40 | Một Product stock NULL |
| COUNT(p) WHERE active | 5 | Bao gồm P05 giá NULL |
| SUM(price) WHERE active | 13.400.000 | P05 không cộng vào SUM |

Nếu WHERE không chọn row nào nhưng không GROUP BY:
- COUNT trả 0;
- SUM/AVG/MIN/MAX trả NULL;
- truy vấn aggregate vẫn có một hàng kết quả.

Nếu query có GROUP BY và không có nhóm nào, **getResultList()** có thể trả list rỗng. Không gọi getSingleResult cho mọi grouped query.

### 17.1. Hai cách AVG khác nhau

~~~java
cb.avg(p.<BigDecimal>get("price"))
~~~

tính trung bình trên những giá đã biết. Ngược lại:

~~~java
cb.avg(cb.coalesce(
    p.<BigDecimal>get("price"), BigDecimal.ZERO
))
~~~

coi giá NULL như 0, làm thay đổi mẫu số. Hai biểu thức đáp ứng hai yêu cầu nghiệp vụ khác nhau. Đừng thêm coalesce chỉ để tránh null mà không giải thích ý nghĩa thống kê.

## 18. Xây báo cáo động: Tuple và danh sách cột được phép

Một công cụ báo cáo nội bộ có thể cho người dùng chọn các cột: SKU, Name, Price hoặc CategoryName. Số lượng cột không cố định, nên **Tuple với alias** thường thuận tiện hơn việc định nghĩa một DTO cho từng tổ hợp.

### 18.1. Giới hạn các cột được chọn

Không nên lấy trực tiếp tên thuộc tính bất kỳ từ HTTP request rồi truyền vào:

~~~java
p.get(request.getColumnName());
~~~

Criteria API xây query có cấu trúc, nhưng không tự xác định người dùng được phép xem field nào. Hãy dùng một tập cột đã được kiểm soát:

~~~java
public enum ReportColumn {
    SKU,
    NAME,
    PRICE,
    CATEGORY_NAME
}
~~~

### 18.2. Tạo selections có alias

~~~java
public List<Tuple> buildReport(
        EntityManager em,
        List<ReportColumn> requestedColumns) {

    if (requestedColumns == null || requestedColumns.isEmpty()) {
        throw new IllegalArgumentException("Cần chọn cột");
    }

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Tuple> cq = cb.createTupleQuery();
    Root<Product> p = cq.from(Product.class);

    List<Selection<?>> selections = new ArrayList<>();
    Join<Product, Category> category = null;

    for (ReportColumn column : requestedColumns) {
        switch (column) {
            case SKU ->
                selections.add(p.get("sku").alias("sku"));

            case NAME ->
                selections.add(p.get("name").alias("name"));

            case PRICE ->
                selections.add(p.get("price").alias("price"));

            case CATEGORY_NAME -> {
                if (category == null) {
                    category = p.join(
                        "category", JoinType.LEFT);
                }

                selections.add(
                    category.get("name").alias("categoryName")
                );
            }
        }
    }

    cq.multiselect(selections)
      .where(cb.isNull(p.get("deletedAt")))
      .orderBy(cb.asc(p.get("id")));

    return em.createQuery(cq)
             .setMaxResults(1000)
             .getResultList();
}
~~~

**requestedColumns** nên được kiểm tra trùng lặp trước khi xây query, vì hai selection có cùng alias là không hợp lệ. Đối với Java switch arrow syntax, chọn phiên bản Java hỗ trợ hoặc thay bằng switch cổ điển.

### 18.3. Đọc các cột của Tuple

~~~java
for (Tuple row : rows) {
    for (TupleElement<?> element : row.getElements()) {
        String alias = element.getAlias();
        Object value = row.get(element);
        System.out.println(alias + " = " + value);
    }
}
~~~

Khi xuất CSV/JSON:
- Xác định thứ tự và tên hiển thị cột;
- Escape CSV/JSON đúng quy tắc;
- Format BigDecimal/Instant dựa vào locale, timezone và nghiệp vụ;
- Giới hạn tổng số hàng;
- Không đưa tên field nhạy cảm vào whitelist;
- Không expose Tuple như một API contract mặc định.

### 18.4. Báo cáo động có aggregate cần định nghĩa grain

Nếu người dùng chọn CategoryName và COUNT Product, query cần group theo Category. Nếu thêm SKU thì báo cáo có thể chuyển sang một row mỗi Product và không còn là số liệu mỗi Category.

Do đó query builder phải biết **grain** của report: một row mỗi Product, Category, ngày hoặc tháng. Không thể chỉ thêm một COUNT vào multiselect mà bỏ qua GROUP BY.

## 19. CASE, COALESCE và biểu thức tính trong Selection

Criteria selection không nhất thiết là Path tới field có sẵn. Nó có thể là một Expression được tính.

### 19.1. Nhãn trạng thái tồn kho

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();
Root<Product> p = cq.from(Product.class);

Expression<String> stockState = cb.<String>selectCase()
    .when(
        cb.isNull(p.get("stockQuantity")),
        "UNKNOWN"
    )
    .when(
        cb.equal(p.get("stockQuantity"), 0),
        "OUT_OF_STOCK"
    )
    .otherwise("IN_STOCK");

cq.multiselect(
    p.get("sku").alias("sku"),
    stockState.alias("stockState")
);
~~~

Với P05 stock NULL, stockState là UNKNOWN; với P04 stock 0 là OUT_OF_STOCK; Product có stock dương là IN_STOCK.

Đây là quy ước cụ thể của ví dụ. Nếu một Product có stockQuantity âm do dữ liệu lỗi, CASE trên cũng đặt IN_STOCK, vì vậy business validation hoặc biểu thức riêng là cần thiết khi muốn xử lý trạng thái bất thường.

### 19.2. Giá trị thay thế NULL chỉ để hiển thị

~~~java
Expression<BigDecimal> displayPrice =
    cb.coalesce(
        p.<BigDecimal>get("price"),
        BigDecimal.ZERO
    );
~~~

Khi dùng trong DTO hoặc Tuple, displayPrice bằng 0 nếu price NULL. **Giá trong DB vẫn là NULL**. Đừng coi biểu thức này là migration hoặc cập nhật entity.

Nếu NULL mang ý nghĩa “chưa báo giá”, việc hiển thị 0 có thể gây hiểu nhầm nghiêm trọng. Một DTO với price nullable và flag priceAvailable có thể rõ hơn.

### 19.3. Kiểu của biểu thức quyết định kiểu constructor

Các expressions:
- COUNT → Long;
- AVG numeric → Double;
- SUM BigDecimal → BigDecimal;
- COALESCE price/zero → BigDecimal;
- CASE khi các nhánh trả String → String.

DTO constructor phải khớp **kiểu kết quả của expression**, không chỉ kiểu field nguồn ban đầu.

### 19.4. Trung bình BigDecimal với quy tắc làm tròn

Một report tiền tệ cần chính sách rõ ràng. Có thể chọn SUM BigDecimal và COUNT non-null rồi tính trung bình trong service:

~~~java
static BigDecimal averagePrice(
        BigDecimal total, Long nonNullCount) {

    if (total == null || nonNullCount == null
            || nonNullCount == 0L) {
        return null;
    }

    return total.divide(
        BigDecimal.valueOf(nonNullCount),
        2,
        RoundingMode.HALF_UP
    );
}
~~~

RoundingMode.HALF_UP và scale 2 chỉ minh họa; quy định kế toán/tiền tệ thực tế có thể khác. Không dùng Double từ AVG như một số tiền được làm tròn theo chính sách nếu chưa có xử lý rõ.

## 20. Phân trang DTO và COUNT tách riêng

Một màn hình pageable thường cần:
1. Trang hiện tại: **List<ProductCard>**;
2. Tổng số Product khớp filter: **Long**.

### 20.1. Query trang dữ liệu

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<ProductCard> dataQuery =
    cb.createQuery(ProductCard.class);

Root<Product> p = dataQuery.from(Product.class);

List<Predicate> filters = new ArrayList<>();
filters.add(cb.isNull(p.get("deletedAt")));

if (minimumPrice != null) {
    filters.add(cb.greaterThanOrEqualTo(
        p.get("price"), minimumPrice));
}

dataQuery.select(cb.construct(
    ProductCard.class,
    p.get("id"),
    p.get("sku"),
    p.get("name"),
    p.get("price")
))
.where(cb.and(filters.toArray(new Predicate[0])))
.orderBy(cb.asc(p.get("id")));

List<ProductCard> page =
    em.createQuery(dataQuery)
      .setFirstResult(offset)
      .setMaxResults(pageSize)
      .getResultList();
~~~

### 20.2. Query đếm số kết quả

~~~java
CriteriaQuery<Long> countQuery = cb.createQuery(Long.class);
Root<Product> countRoot = countQuery.from(Product.class);

List<Predicate> countFilters = new ArrayList<>();
countFilters.add(
    cb.isNull(countRoot.get("deletedAt")));

if (minimumPrice != null) {
    countFilters.add(cb.greaterThanOrEqualTo(
        countRoot.get("price"), minimumPrice));
}

countQuery.select(cb.count(countRoot))
          .where(cb.and(
              countFilters.toArray(new Predicate[0])
          ));

Long total = em.createQuery(countQuery).getSingleResult();
~~~

Không lấy **page.size()** làm tổng số kết quả; đó chỉ là số rows trong trang.

### 20.3. Không chia sẻ Root giữa hai CriteriaQuery

Các Root, Join và Predicate thuộc cây truy vấn được tạo. Không dùng root **p** của dataQuery trong countQuery. Hãy tạo Root mới và xây lại logic predicates tương đương qua helper nhận CriteriaBuilder + Root hiện tại.

Nếu có to-many JOIN làm nhiều rows cho một Product, countRoot có thể cần **countDistinct(countRoot.get("id"))** để khớp semantics unique Product của data query.

### 20.4. ORDER BY và thời điểm hai queries

Để pagination ổn định, nên dùng một thứ tự đầy đủ, ví dụ Name rồi ID làm tie-breaker. Count query không cần ORDER BY.

Hai query chạy riêng có thể nhìn dataset khác nhau nếu concurrent transactions thay đổi dữ liệu và isolation cho phép. Criteria không tự cung cấp một snapshot consistency trên cả hai queries; nếu yêu cầu nhất quán tuyệt đối cần thiết kế transaction/isolation hoặc read snapshot.

## 21. Spring Data JPA: phân biệt Specifications và projections

Trong Spring Data JPA, Specification thường xây Predicates:

~~~java
Specification<Product> activeProducts =
    (root, query, cb) -> cb.and(
        cb.isTrue(root.get("active")),
        cb.isNull(root.get("deletedAt"))
    );
~~~

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long>,
                JpaSpecificationExecutor<Product> {
}
~~~

Gọi:

~~~java
Page<Product> products =
    repository.findAll(activeProducts, pageable);
~~~

Ví dụ trả **entity Product** theo API này, không tự động trả Tuple hoặc CategorySummary. Những khả năng projection khác có thể tùy Spring Data version và API cụ thể.

Với report gồm aggregate và GROUP BY phức tạp, một **custom repository** dùng EntityManager và CriteriaQuery<CategorySummary> hoặc CriteriaQuery<Tuple> có thể rõ ràng hơn.

### 21.1. Read-only transaction không thay result type

~~~java
@Transactional(readOnly = true)
public List<ProductCard> listCards() {
    // Query CriteriaQuery<ProductCard>.
}
~~~

Kết quả vẫn là DTO. Nếu cùng method chạy CriteriaQuery<Product>, kết quả là entity selection theo persistence context; annotation readOnly không biến entity thành DTO.

### 21.2. Không biến Criteria query thành business action

Criteria SELECT chỉ định dữ liệu đọc; nếu service muốn update Product, cần quản lý transaction và một managed Product hoặc dùng bulk DML thích hợp. Không sửa DTO rồi cho rằng Spring Data tự flush DTO vào bảng.

## 22. Hiệu năng, quản lý entity và độ chính xác của báo cáo

### 22.1. DTO thường phù hợp cho read-only API

Nếu API hiển thị 20 Product, chỉ cần 4 field, chọn DTO thường giúp:
- Giảm số trường được truyền từ database;
- Tránh xây đầy đủ Product entity khi không cần;
- Giảm graph lazy relationships bị truy cập ngoài ý muốn;
- Tránh expose field nội bộ;
- Giảm số managed entities được giữ trong persistence context.

Nhưng DTO không tự nhanh hơn mọi entity query. Một DTO projection có nhiều JOIN và GROUP BY có thể tốn nhiều tài nguyên DB hơn một entity query đơn giản có index tốt.

### 22.2. N+1 còn xảy ra nếu DTO chứa entity

~~~java
cb.construct(
    WrapperDto.class,
    p,
    p.get("sku")
)
~~~

Nếu WrapperDto chứa chính Product entity và code sau đó truy cập p.getCategory().getName() trên hàng trăm Product, có thể phát sinh lazy-loading N+1. Nếu chỉ cần CategoryName, select scalar **c.get("name")** qua JOIN phù hợp.

### 22.3. To-many JOIN có thể làm sai cả SUM

Giả sử một Product có:
- 3 Tags;
- 4 Promotions.

Khi join cả hai collections, một Product có thể tạo **3 × 4 = 12 rows** ở SQL intermediate result.

Nếu query SUM(Product.price) trên những rows ấy, **giá của cùng Product có thể bị cộng 12 lần**. COUNT DISTINCT Product ID giải quyết đếm entity trùng, nhưng **không tự sửa được SUM**.

Đừng dùng SUM(DISTINCT price) để khắc phục máy móc: hai Product khác nhau có cùng giá sẽ bị gộp sai. Giải pháp cần xác định đúng grain:
- Query theo Product không join to-many nếu không cần;
- Dùng EXISTS khi chỉ kiểm tra liên kết tồn tại;
- Tổng hợp trước khi join nếu schema/dialect cho phép;
- Chia report thành queries chuyên biệt;
- Thiết kế read model phù hợp.

### 22.4. Các aggregates không thay thế business rules

Một Product có price NULL có thể nghĩa là chưa được báo giá, không phải zero. **SUM bỏ NULL**, **COUNT(price) bỏ NULL**, và **AVG(price) bỏ NULL** là semantics SQL. Nếu báo cáo yêu cầu “giá trị ước tính của cả những sản phẩm chưa có giá”, bạn phải xác định công thức ước tính chứ không tự cho price NULL bằng 0.

### 22.5. Đặt WHERE trước khi tính aggregate

~~~java
cq.where(
    cb.isTrue(p.get("active")),
    cb.isNull(p.get("deletedAt"))
);
~~~

Nếu báo cáo chỉ tính sản phẩm đang bán, điều kiện này cần được thêm vào trước grouping. Một báo cáo khác chỉ tính hàng đã giao có thể có filter khác. Không gán nhầm một aggregate “total” là total toàn DB nếu query thật có WHERE.

### 22.6. Index và SQL thực tế

Các truy vấn nhóm theo category_id, lọc active/deletedAt hoặc sắp theo price có những đường truy cập DB khác nhau. Xem SQL provider sinh và dùng EXPLAIN/EXPLAIN ANALYZE khi cần.

Bật statistics phù hợp có thể giúp nhận ra:
- Query trả quá nhiều rows;
- JOIN làm nhân cardinality;
- Sort/group aggregate dùng nhiều memory;
- Index không được sử dụng;
- N+1 do lazy associations;
- Count query chạy đắt hơn cả data query.

Criteria là API xây truy vấn, **không bảo đảm kế hoạch SQL tối ưu**.

### 22.7. Một báo cáo nhiều câu query cần snapshot nhất quán

Nếu màn hình chạy:
1. Count Product;
2. Sum Price;
3. Group by Category;

thì concurrent inserts/updates có thể khiến ba con số được tính tại những thời điểm khác nhau tùy transaction isolation. Dùng một Tuple aggregate query cho các metrics cùng grain có thể giảm số statement, nhưng không đủ để bảo đảm nhất quán khi dashboard còn nhiều truy vấn và có concurrent writes.

Với báo cáo cần chính xác tại một thời điểm, thiết kế transaction/isolation, snapshot hoặc ETL/read model riêng.

### 22.8. Bộ lọc tenant và quyền không được bỏ

Ví dụ một hệ thống có Product.tenantId. Query read model phải có:

~~~java
cb.equal(p.get("tenantId"), authorizedTenantId)
~~~

và soft-delete filter phù hợp, trong đó **authorizedTenantId phải do server xác thực xác định**, không tin một tham số request tùy ý.

Chọn DTO chỉ để giới hạn cột trả về **không thay thế row-level authorization**. Criteria query builder cần xây các predicates bắt buộc nhất quán giữa entity query, DTO query, count query và aggregate report.

## 23. Các lỗi thường gặp khi chọn kiểu kết quả

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Expected Product but got scalar | CriteriaQuery<Product> nhưng select(price) | Chọn result type tương ứng selection |
| ClassCastException khi lấy Object[] | Sai index hoặc sai kiểu ở row | Dùng DTO hoặc Tuple alias |
| Tuple.get("price") báo lỗi | Không đặt alias hoặc alias không đúng | Đặt alias ổn định và đọc đúng |
| Tuple.get(alias, Class) báo lỗi | Runtime type không tương thích | Kiểm tra kiểu expression/aggregate |
| Trùng alias trong multiselect | Nhiều fields alias giống nhau | Alias phải duy nhất |
| DTO constructor not found | Sai số/thứ tự/kiểu fields | Khớp constructor và selections |
| DTO không được save khi sửa field | DTO không phải JPA entity | Load managed entity hoặc dùng command update |
| COUNT trả Long nhưng code ép Integer | Kiểu aggregate JPA COUNT là Long | Dùng Long |
| AVG trả Double thay vì BigDecimal | Semantics AVG numeric của JPA | Dùng Double hoặc tính từ SUM/COUNT |
| SUM không có kết quả = null | Không có giá trị non-NULL | COALESCE nếu nghiệp vụ muốn zero |
| COUNT(price) nhỏ hơn COUNT(Product) | Price chứa NULL | Dùng count(root) khi đếm rows |
| GROUP BY query không trả row | Không có group hoặc HAVING lọc hết | getResultList và xử lý empty |
| Query có GROUP BY nhưng select field lạ | Non-aggregate expression không được group phù hợp | Group tất cả expressions cần thiết |
| COUNT(Category) quá lớn | To-many JOIN tạo row trùng | countDistinct(identity) khi cần |
| SUM(price) bị phóng đại | JOIN hai collection | Chọn đúng grain/aggregate trước join |
| Danh mục NULL biến mất | INNER JOIN hoặc implicit join | LEFT JOIN nếu muốn giữ |
| Category rỗng không có report row | Query bắt đầu từ Product | Bắt đầu từ Category + LEFT JOIN Product |
| COUNT của Category rỗng thành 1 | Dùng count(parent) trên LEFT JOIN | count(child) |
| Dữ liệu hiển thị bị lặp | Multiselect join nhiều hàng | DISTINCT hoặc GROUP BY đúng nghĩa |
| Null ở constructor primitive | Projection có field nullable | Dùng reference type và xử lý NULL |
| Query đếm tổng bằng page.size | Chỉ đo số rows của trang | Tạo count CriteriaQuery riêng |
| Count query dùng Root của data query | Root thuộc query khác | Tạo Root/Predicate tương ứng cho mỗi query |
| Thêm query với filter thiếu tenant | Bỏ predicate bảo mật trong báo cáo | Tái sử dụng policy filter rõ ràng |
| N+1 khi duyệt DTO | DTO chứa entity rồi truy cập lazy getter | Select scalars/join đúng field |
| Query Criteria không compile do path | Dùng string name sai hoặc type inference | Dùng typed path/static metamodel |
| Nhiều DTO có cùng ID | DTO không dùng entity identity map | Xem JOIN/distinct/projection grain |
| Empty result nhưng gọi getSingleResult | Query không bảo đảm một hàng | Dùng getResultList hoặc xử lý NoResult |
| Query tổng hợp quá chậm | Scan/group lớn, index thiếu, JOIN dư | Xem SQL plan, read model, index |
| ORDER BY NULL khác giữa DB | NULL ordering phụ thuộc dialect | CASE expression hoặc tính năng dialect phù hợp |

### 23.1. Khi lỗi xuất hiện ở đâu?

Lỗi có thể xuất hiện:
- Khi xây Criteria selections (alias trùng);
- Khi gọi EntityManager.createQuery (query không hợp lệ);
- Khi execute query (constructor/type mismatch, SQL syntax/dialect);
- Khi đọc Tuple/Object[] (alias/ép kiểu sai);
- Khi serialize response (DTO chứa lazy entity);
- Khi update business flow (nhầm DTO với managed entity).

Không vì một query không ném exception mà khẳng định report đúng: GROUP BY sai grain hoặc COUNT bị nhân row có thể trả con số hợp lệ về mặt SQL nhưng sai nghiệp vụ.

### 23.2. Chẩn đoán theo thứ tự

1. Kiểu **CriteriaQuery<T>** và selection có khớp không?
2. Query trả entity, scalar, DTO, Tuple hay Object[]?
3. Constructor DTO có đúng số/kiểu/thứ tự không?
4. Có alias trùng hoặc đọc sai alias không?
5. JOIN type và cardinality có đúng không?
6. Các field group không phải aggregate đã được group chưa?
7. WHERE được áp trước grouping, HAVING sau grouping đúng chưa?
8. COUNT(root), COUNT(child), COUNT(field) có cùng nghĩa không?
9. NULL có làm sum/avg/min/max thành null không?
10. Có filter authorization/soft delete và pagination đúng chưa?

## 24. Integration tests cho từng loại selection

Các ví dụ giả định JUnit 5, EntityManager đang hoạt động trong test transaction, và entity Product/Category ở phần 2. Nên tạo fixture riêng từng test hoặc dùng data setup ổn định để tránh test ảnh hưởng lẫn nhau.

### 24.1. Entity selection trả managed instance

~~~java
@Test
void entityProjectionIsManaged() {
    Product product = new Product(
        "TEST-P01",
        "Keyboard",
        new BigDecimal("500000.00"),
        5,
        true,
        null
    );

    em.persist(product);
    em.flush();

    Long id = product.getId();
    em.clear();

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Product> cq = cb.createQuery(Product.class);
    Root<Product> p = cq.from(Product.class);

    cq.select(p)
      .where(cb.equal(p.get("id"), id));

    Product loaded = em.createQuery(cq).getSingleResult();

    assertTrue(em.contains(loaded));
    assertEquals(id, loaded.getId());
}
~~~

### 24.2. DTO selection không phải entity

~~~java
@Test
void dtoProjectionContainsSelectedValues() {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<ProductCard> cq =
        cb.createQuery(ProductCard.class);

    Root<Product> p = cq.from(Product.class);

    cq.select(cb.construct(
        ProductCard.class,
        p.get("id"),
        p.get("sku"),
        p.get("name"),
        p.get("price")
    ))
    .where(cb.equal(p.get("sku"), "TEST-P01"));

    ProductCard card = em.createQuery(cq).getSingleResult();

    assertEquals("TEST-P01", card.sku());
    assertEquals("Keyboard", card.name());

    // Không gọi em.contains(card): DTO không phải entity.
}
~~~

Test trên giả định fixture TEST-P01 tồn tại. **EntityManager.contains chỉ nhận entity phù hợp**, không dùng chứa DTO để kiểm tra trạng thái của DTO.

### 24.3. Tuple đọc đúng alias

~~~java
@Test
void tupleProjectionReadsByAlias() {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Tuple> cq = cb.createTupleQuery();

    Root<Product> p = cq.from(Product.class);
    cq.multiselect(
        p.get("sku").alias("sku"),
        p.get("price").alias("price")
    )
    .where(cb.equal(p.get("sku"), "TEST-P01"));

    Tuple row = em.createQuery(cq).getSingleResult();

    assertEquals("TEST-P01", row.get("sku", String.class));
    assertEquals(
        new BigDecimal("500000.00"),
        row.get("price", BigDecimal.class)
    );
}
~~~

Giá BigDecimal được mapping NUMERIC(19,2); cách biểu diễn scale của giá được lưu/đọc có thể phụ thuộc dữ liệu và mapping, nên khi cần so sánh giá trị số thay vì scale chính xác có thể dùng compareTo theo yêu cầu kiểm thử.

### 24.4. COUNT field nullable và COUNT entity

~~~java
@Test
void countIgnoresNullPriceButCountRootDoesNot() {
    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Tuple> cq = cb.createTupleQuery();
    Root<Product> p = cq.from(Product.class);

    cq.multiselect(
        cb.count(p).alias("allCount"),
        cb.count(p.get("price")).alias("pricedCount")
    );

    Tuple row = em.createQuery(cq).getSingleResult();

    assertTrue(
        row.get("allCount", Long.class)
            >= row.get("pricedCount", Long.class)
    );
}
~~~

Test này xác nhận bất biến COUNT(root) không nhỏ hơn COUNT(nullable field). Để xác minh số cụ thể, tạo fixture riêng có một Product price NULL rồi assert expected counts chính xác.

### 24.5. Tổng hợp với group và HAVING

Tạo Category có ba Product, một Category khác chỉ một Product. Query GROUP BY Category ID/Name, HAVING count >= 2. Assert group lớn được giữ, group nhỏ bị loại. Test thêm một Product không Category và lựa chọn LEFT JOIN để thấy nhóm NULL khi query bắt đầu từ Product.

### 24.6. COUNT to-many JOIN

Tạo một Category có ba Products, rồi:
- count(category) qua JOIN;
- countDistinct(category.id);
- count(product) qua JOIN.

Kỳ vọng count(category) của result join là 3, countDistinct(category.id) là 1 và count(product) là 3. Test này cho thấy **số hàng join khác số entity root duy nhất**.

### 24.7. Không có kết quả aggregate

Tạo query WHERE sku không tồn tại:
- Count Product = 0L;
- Sum price = null;
- GroupBy Category sau WHERE → List<Tuple> rỗng.

Phân biệt ngay ở tests để code service không gọi getSingleResult cho một grouped report có thể rỗng.

### 24.8. Round-trip và provider thực

Nếu một test dựa vào entity đang managed ở persistence context, có thể che lỗi truy vấn hoặc dữ liệu DB. Sau setup persist, **em.flush(); em.clear()** để dữ liệu được query từ context không còn giữ những instances cũ. Đây là kỹ thuật thiết lập test, không phải dấu hiệu transaction đã commit.

Với số liệu tài chính/NULL behavior/dialect-specific functions, nên chạy integration tests trên DB cùng loại production khi có thể, không chỉ dựa vào unit tests giả lập Criteria expressions.

## 25. Bài tập thực hành

Các bài tập dựa trên Product, Category và bộ dữ liệu mẫu ở phần 2, trừ khi đề bài nêu biến thể riêng. Mỗi bài yêu cầu viết code Criteria API hoặc giải thích chính xác shape của kết quả, không chỉ viết câu JPQL tương đương.

### Bài 1. Chọn entity đang hoạt động

Viết CriteriaQuery<Product> lấy Product active=true và deletedAt IS NULL, sắp theo SKU. Trả List<Product>.

Giải thích:
- Vì sao root Product và kiểu result Product trùng nhau trong truy vấn này?
- Các entities được trả có thể managed trong phạm vi context nào?
- Nếu muốn sửa tên Product, tại sao entity selection có thể phù hợp hơn DTO?

### Bài 2. Chỉ lấy SKU

Viết CriteriaQuery<String> trả danh sách SKU của các Product active. Không load Product entity chỉ để gọi getSku sau đó.

So sánh lượng dữ liệu cần tải và memory impact với CriteriaQuery<Product> khi chỉ cần SKU.

### Bài 3. DTO card sản phẩm

Tạo record:

~~~java
public record ProductCard(
    Long id, String sku, String name, BigDecimal price
) {}
~~~

Viết CriteriaQuery<ProductCard> dùng **cb.construct**. Đặt WHERE active=true, ORDER BY name rồi id. Tại sao thứ tự constructor arguments phải giống record components?

### Bài 4. Constructor không khớp

Cho DTO nhận:

~~~java
ProductCard(Long id, String sku, String name, BigDecimal price)
~~~

nhưng Selection list lại là:

~~~java
p.get("id"),
p.get("price"),
p.get("sku"),
p.get("name")
~~~

Phân tích loại lỗi có thể gặp. Nếu DTO dùng Long id nhưng database ID property lại được mapping UUID, điều gì cần thay trong constructor và Criteria result type?

### Bài 5. Object[] và index

Viết CriteriaQuery<Object[]> lấy id, sku, price. Đọc mỗi hàng theo row[0], row[1], row[2] và ép kiểu phù hợp.

Sau đó đổi thứ tự select thành sku, id, price nhưng giữ code đọc cũ. Giải thích nguy cơ ClassCastException, và vì sao DTO/Tuple có thể dễ bảo trì hơn.

### Bài 6. Tuple với alias

Viết CriteriaQuery<Tuple> chọn SKU, Name và Price với alias **sku**, **name**, **price**. Đọc theo:
1. row.get("sku", String.class);
2. row.get(1, String.class);
3. row.getElements() và TupleElement.

Hỏi: alias không tồn tại thì xảy ra gì? Hai selections cùng alias có được chấp nhận không?

### Bài 7. Tạo Tuple từ cb.tuple

Viết lại bài 6 bằng:

~~~java
cq.select(cb.tuple(
    p.get("sku").alias("sku"),
    p.get("price").alias("price")
));
~~~

Phân biệt kiểu kết quả với CriteriaQuery<Object[]> dùng cb.array hoặc multiselect.

### Bài 8. COUNT toàn bộ và COUNT price

Theo dataset:
- COUNT(Product) bằng bao nhiêu?
- COUNT(Product.price) bằng bao nhiêu?
- Vì sao hai số khác nhau?

Viết một CriteriaQuery<Tuple> lấy cả hai trong một statement, đặt alias **allProducts** và **pricedProducts**, đọc bằng Long.class.

### Bài 9. SUM BigDecimal và SUM Integer

Viết:
- CriteriaQuery<BigDecimal> dùng SUM(price);
- CriteriaQuery<Long> dùng sumAsLong(stockQuantity).

Tại sao SUM giá nên giữ BigDecimal? Tại sao sumAsLong hữu ích với nguồn Integer khi dữ liệu lớn?

### Bài 10. AVG và NULL

Giả sử một Product có price NULL. So sánh:
- AVG(price);
- AVG(COALESCE(price, 0)).

Chúng có cùng mẫu số không? Khi nào coi NULL là 0 làm sai ý nghĩa nghiệp vụ? Nếu cần BigDecimal trung bình với scale 2, đề xuất lấy SUM và COUNT non-null rồi chia theo RoundingMode đã được định nghĩa.

### Bài 11. Group theo Category

Viết CriteriaQuery<Tuple> chọn:
- categoryId;
- categoryName;
- count(Product);
- sum(price).

Dùng LEFT JOIN Category từ Product, GROUP BY categoryId/categoryName. Theo dataset, Category Electronics, Furniture và nhóm chưa phân loại có count, sum như thế nào?

### Bài 12. INNER JOIN so với LEFT JOIN

Thay LEFT JOIN ở bài 11 bằng INNER JOIN. Nhóm nào biến mất? Vì sao P05/P06 không có Category không được đưa vào báo cáo?

Tiếp theo, viết một query bắt đầu từ Category và LEFT JOIN Products để hiển thị Category không có Product với count=0.

### Bài 13. HAVING có điều kiện

Viết CriteriaQuery<Tuple> chỉ lấy những Category có COUNT(Product) >= 3. Theo dataset, nhóm nào được giữ?

Sửa yêu cầu thành “Category có ít nhất hai **Product active**”. Chỉ ra điều kiện active phải đặt trong WHERE trước GROUP BY, còn điều kiện count phải đặt trong HAVING.

### Bài 14. COUNT do JOIN bị nhân

Một Category có ba Product. Query từ Category join Products và dùng count(category). Kết quả có phải 1 không? Viết lại bằng countDistinct(category.id) để đếm Category identity.

Đề xuất bài kiểm thử minh họa khác biệt giữa số hàng JOIN và số entity gốc.

### Bài 15. COUNT child bằng 0

Một Category chưa có Product. Với LEFT JOIN từ Category tới Product:
- count(category) cho group rỗng có thể là bao nhiêu?
- count(product) là bao nhiêu?
- Khi nào dùng countDistinct(product.id)?

Giải thích vì sao chọn đúng expression cho COUNT là điều kiện để kết quả có ý nghĩa.

### Bài 16. Group theo Name bị gộp sai

Hai Category khác ID nhưng cùng tên "Accessories". Một developer group chỉ theo categoryName và report có một row.

Viết lại GROUP BY categoryId và categoryName để giữ hai thực thể riêng. Khi nào group theo name thật sự là yêu cầu hợp lý?

### Bài 17. Constructor DTO tổng hợp

Tạo CategorySummary gồm categoryId, categoryName, productCount, totalPrice. Viết CriteriaQuery<CategorySummary> dùng cb.construct, GROUP BY và HAVING count >= 2.

So sánh với cách dùng Tuple rồi tự map ở service. Trong trường hợp báo cáo có contract cố định, cách nào dễ tránh sai kiểu hơn?

### Bài 18. Dataset không có record

Viết hai query có WHERE sku="NO-RECORD":
1. COUNT không GROUP BY;
2. GROUP BY Category và COUNT.

Dự đoán getSingleResult/getResultList có kết quả như thế nào. Thêm SUM(price) và chỉ ra khác biệt giữa 0 và NULL.

### Bài 19. Lựa chọn cho REST API

Một endpoint GET /products hiển thị 50 card với ID, Name, Price. Một endpoint khác PUT /products/{id}/name cập nhật tên.

Hãy chọn giữa Product entity và ProductCard DTO cho từng use case, giải thích:
- Dirty checking;
- Lazy associations;
- Dữ liệu nhạy cảm;
- DTO không phải entity một phần;
- Transaction boundary.

### Bài 20. Báo cáo động bằng Tuple

Một form cho phép chọn SKU/Name/Price/CategoryName. Viết danh sách enum ReportColumn và xây các Selection có alias theo whitelist.

Giải thích vì sao không dùng trực tiếp một string property do client gửi. Nếu người dùng chọn cột CategoryName hai lần, cần làm gì để tránh alias trùng?

### Bài 21. CASE cho tồn kho

Dùng CASE để chọn stockState:
- UNKNOWN nếu stock NULL;
- OUT_OF_STOCK nếu stock=0;
- IN_STOCK nếu stock>0.

Thêm nhánh INVALID nếu stock<0. Đưa stockState vào Tuple cùng SKU và test ba hoặc bốn trường hợp dữ liệu.

### Bài 22. Query trang và query tổng số

Viết CriteriaQuery<ProductCard> trả 20 Product của trang hiện tại và CriteriaQuery<Long> đếm tổng Product khớp cùng filter minPrice + deletedAt IS NULL.

Tại sao không dùng page.size() làm total count? Có thể tái sử dụng Root<Product> của data query trong count query không? Hãy tạo helper Predicate để tái sử dụng **logic**, không tái sử dụng Root instance.

### Bài 23. To-many joins làm sai SUM

Một Product giá 500.000 có 3 Tags và 4 Promotions. Query join cả Tags và Promotions rồi SUM(price).

Tại sao kết quả có thể là 6.000.000? Vì sao SUM(DISTINCT price) không phải biện pháp sửa tổng quát? Đề xuất cách tính tổng ở grain Product trước khi join hoặc dùng EXISTS.

### Bài 24. Phân quyền và bộ lọc bắt buộc

Hệ thống đa tenant có Product.tenantId và deletedAt. Viết CriteriaQuery<ProductCard> với:
- tenantId do server xác thực;
- deletedAt IS NULL;
- minPrice tùy chọn từ client.

Tại sao filter bảo mật phải được áp dụng cả ở CriteriaQuery<Long> dùng đếm số Product?

### Bài 25. Chọn đúng kỹ thuật cho dashboard

Một dashboard cần số sản phẩm, số sản phẩm có giá, giá thấp nhất, cao nhất và tổng giá. Có thể dùng:
- Năm query scalar riêng;
- Một CriteriaQuery<Tuple>;
- Một CriteriaQuery<ProductMetrics> DTO constructor.

So sánh mục tiêu hiệu năng, contract API và khả năng đổi danh sách metrics. Viết code cho phương án bạn chọn và giải thích.

### Bài 26. Viết integration test xác nhận kết quả

Tạo fixture hai Category, nhiều Product, một Product giá NULL và một Product chưa có Category. Viết test cho:
- Product entity selection;
- ProductCard DTO projection;
- Tuple với alias;
- COUNT(root) khác COUNT(price);
- SUM(price);
- LEFT JOIN groupBy;
- HAVING;
- COUNT DISTINCT khi join to-many.

Thêm bước flush/clear trước query khi muốn kiểm chứng dữ liệu được đọc từ persistence context mới, và kiểm tra số liệu cụ thể theo fixture.

## 26. Bảng tham chiếu Criteria selection

| Mục tiêu | Result type | Selection cơ bản |
|---|---|---|
| Trả Product entity | CriteriaQuery<Product> | cq.select(root) |
| Trả SKU | CriteriaQuery<String> | cq.select(root.get("sku")) |
| Trả ID | CriteriaQuery<Long> | cq.select(root.get("id")) |
| Trả Price | CriteriaQuery<BigDecimal> | cq.select(root.get("price")) |
| DTO card | CriteriaQuery<ProductCard> | cb.construct(ProductCard.class, ...) |
| Nhiều cột theo vị trí | CriteriaQuery<Object[]> | cq.multiselect(...) |
| Nhiều cột theo alias | CriteriaQuery<Tuple> | cq.multiselect(selection.alias(...)) |
| Tuple compound selection | CriteriaQuery<Tuple> | cb.tuple(...) |
| Object[] compound selection | CriteriaQuery<Object[]> | cb.array(...) |
| Đếm entity | CriteriaQuery<Long> | cb.count(root) |
| Đếm field không NULL | CriteriaQuery<Long> | cb.count(root.get("field")) |
| Đếm giá trị phân biệt | CriteriaQuery<Long> | cb.countDistinct(path) |
| Tổng BigDecimal | CriteriaQuery<BigDecimal> | cb.sum(root.<BigDecimal>get("price")) |
| Tổng Integer ra Long | CriteriaQuery<Long> | cb.sumAsLong(root.<Integer>get("stockQuantity")) |
| Trung bình numeric | CriteriaQuery<Double> | cb.avg(numericExpression) |
| Min/Max numeric | CriteriaQuery<NumberType> | cb.min(...), cb.max(...) |
| Cực trị Comparable | CriteriaQuery<T> | cb.least(...), cb.greatest(...) |
| Nhiều metrics một hàng | CriteriaQuery<Tuple> | multiselect(count, sum, min, max) |
| Metrics DTO | CriteriaQuery<ProductMetrics> | cb.construct(...aggregate expressions) |
| Một hàng mỗi Category | CriteriaQuery<Tuple>/DTO | groupBy(categoryId, categoryName) |
| Lọc nhóm có count lớn | Cùng query group | having(cb.gt(cb.count(root), n)) |
| Giữ Product chưa có Category | Query với LEFT JOIN | root.join("category", JoinType.LEFT) |

Bảng trên minh họa các mảnh cấu trúc, không phải các câu query hoàn chỉnh. Cần có Root/FROM, WHERE và orderBy khi bài toán đòi hỏi, cùng với kiểu Java chính xác của từng expression.

## 27. Checklist lựa chọn loại kết quả

Trước khi triển khai một Criteria query, trả lời theo thứ tự:

1. **Trả về đối tượng gì?** Entity, DTO, scalar, Tuple hay Object[]?
2. **Có cần cập nhật entity không?** Nếu cần dirty checking, chọn managed entity và transaction thích hợp.
3. **Nếu read-only, đã chỉ chọn những cột cần thiết chưa?** DTO/scalar tránh tải graph không cần thiết.
4. **CriteriaQuery<T> có khớp Selection<T> không?** Đừng chọn price vào query khai báo Product.
5. **DTO constructor có đúng thứ tự và kiểu không?** Đặc biệt BigDecimal, Double, Long, Integer, Instant.
6. **Tuple có đặt alias duy nhất chưa?** Đọc bằng alias ổn định.
7. **Object[] có đang tạo magic indices không?** Nếu dùng dài hạn, cân nhắc DTO/Tuple.
8. **Aggregate đang tính trên row hay field nullable?** count(root) khác count(nullableField).
9. **SUM/AVG có bỏ NULL không?** Xác định có nên dùng COALESCE theo nghiệp vụ.
10. **Tập dữ liệu trống xử lý ra sao?** COUNT=0, SUM=NULL; GROUP BY có thể trả list rỗng.
11. **Có JOIN to-many không?** COUNT/SUM có thể bị nhân row.
12. **Cần DISTINCT hay GROUP BY?** Hai thao tác có mục đích khác nhau.
13. **Root report đúng chưa?** Product-root giữ nhóm chưa phân loại; Category-root giữ Category rỗng.
14. **JOIN type đúng chưa?** INNER có thể loại entity không có association.
15. **Group theo identity chưa?** Tránh gộp hai entity cùng name.
16. **WHERE và HAVING có đặt đúng vị trí không?** WHERE lọc rows, HAVING lọc groups.
17. **Result có thể nhiều nhóm không?** Dùng getResultList thay vì getSingleResult khi có khả năng nhiều/không nhóm.
18. **Có cần pagination không?** Sắp xếp ổn định, giới hạn kết quả.
19. **Có count query tương ứng không?** Tạo Root/Predicates riêng cho count.
20. **Có filter bảo mật/soft-delete bắt buộc không?** Không để chúng trở thành tùy chọn.
21. **Có khả năng N+1 không?** DTO có entity reference, lazy associations hoặc to-many JOIN.
22. **Đã kiểm tra SQL plan/NULL/collation/dialect chưa?** Đo với DB mục tiêu khi cần.
23. **Read model có contract rõ chưa?** Tránh expose entity/Tuple trực tiếp nếu API cần ổn định.
24. **Có test với data edge cases chưa?** NULL, zero count, duplicate join, nhiều Category trùng name.
25. **Có hiểu transaction/snapshot của báo cáo chưa?** Nhiều query có thể đọc tại thời điểm khác nhau.

### 27.1. Sơ đồ quyết định nhanh

~~~text
Cần đọc dữ liệu từ JPA
         |
         +-- Cần sửa entity theo domain logic?
         |       |
         |       +-- Có → CriteriaQuery<Entity>, select(root)
         |                 dùng managed entity trong transaction
         |
         +-- Chỉ đọc?
                 |
                 +-- Một field?
                 |       → CriteriaQuery<String/Long/BigDecimal/...>
                 |
                 +-- Nhiều field, schema cố định?
                 |       → DTO + CriteriaBuilder.construct(...)
                 |
                 +-- Nhiều field, cột báo cáo động?
                 |       → Tuple + aliases + whitelist
                 |
                 +-- Mảng nội bộ rất ngắn?
                 |       → Object[] (cẩn thận thứ tự)
                 |
                 +-- Một/tập số liệu tổng hợp?
                         |
                         +-- Một metric → scalar COUNT/SUM/AVG/...
                         |
                         +-- Metrics cố định → DTO aggregate
                         |
                         +-- Metrics động → Tuple aggregate
                         |
                         +-- Một row mỗi nhóm?
                                 → GROUP BY + HAVING nếu cần
                                   kiểm tra join cardinality và NULL
~~~

## 28. Tổng kết

**Criteria API tách biệt nguồn dữ liệu khỏi hình dạng kết quả.** Bắt đầu từ Root<Product> không buộc query phải trả Product. Tùy mục đích, bạn có thể chọn:

- **Entity** bằng **CriteriaQuery<Product> và select(root)** để nhận đối tượng được JPA quản lý;
- **DTO** bằng **CriteriaBuilder.construct** để trả dữ liệu đọc có contract rõ;
- **Scalar** bằng CriteriaQuery<String/Long/BigDecimal/Double> để nhận một thuộc tính hoặc một aggregate;
- **Tuple** bằng **createTupleQuery/multiselect/alias** để nhận nhiều giá trị và báo cáo động;
- **Object[]** khi cần một tổ hợp đơn giản nhưng chấp nhận truy cập theo chỉ số.

Các hàm **count, countDistinct, sum, sumAsLong, avg, min, max, least, greatest** cho phép tính toán ở database. **GROUP BY** chia dữ liệu thành nhóm, **HAVING** lọc nhóm, còn **WHERE** lọc các source rows trước khi tổng hợp. Khi có NULL hoặc JOIN, phải biết rõ mình đang đếm entity, đếm field non-null hay đếm rows của JOIN; nếu không, báo cáo có thể sai dù câu truy vấn chạy thành công.

**Nguyên tắc cốt lõi:** chọn loại kết quả theo nhu cầu nghiệp vụ trước, sau đó xây **CriteriaQuery<T> và Selection** cùng kiểu; kiểm soát constructor/alias/NULL, chọn JOIN và aggregate ở đúng grain, áp filter bắt buộc và kiểm thử trên dữ liệu có edge cases. Làm như vậy giúp truy vấn **dễ đọc, có cấu trúc, không tải dư entity và trả số liệu đáng tin cậy**.













