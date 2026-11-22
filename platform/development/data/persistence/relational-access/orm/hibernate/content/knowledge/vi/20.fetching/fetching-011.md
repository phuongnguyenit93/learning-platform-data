# Chọn DTO projection khi chỉ cần dữ liệu đọc

## 1. Vì sao không phải truy vấn nào cũng cần tải một entity?

Trong Hibernate ORM/Jakarta Persistence (JPA), cách quen thuộc để đọc dữ liệu là truy vấn entity:

~~~java
Product product = entityManager.find(Product.class, productId);
~~~

Entity phù hợp khi use case cần làm việc với trạng thái domain: kiểm tra quy tắc, thay đổi thuộc tính, điều hướng association hoặc để Hibernate theo dõi thay đổi qua dirty checking.

Nhưng nhiều màn hình và API chỉ cần một phần dữ liệu:

- Trang danh sách chỉ hiển thị ID, tên, giá và ảnh đại diện.
- Dashboard chỉ cần tổng số đơn hàng và doanh thu theo tháng.
- Trang tìm kiếm chỉ cần tên sản phẩm, tên danh mục và trạng thái còn hàng.
- Báo cáo chỉ cần nhóm dữ liệu, số lượng và tổng tiền.
- API autocomplete chỉ cần ID và nhãn hiển thị.

Nếu truy vấn entity cho tất cả những tình huống này, ứng dụng có thể tải nhiều cột và association hơn mức cần thiết, đưa nhiều entity vào persistence context và phát sinh N+1 khi code truy cập các quan hệ lazy.

**DTO projection** cho phép truy vấn trực tiếp những giá trị cần dùng và đóng gói chúng thành một đối tượng đọc (read model), không cần biến kết quả thành một managed entity đầy đủ.

Bài học tập trung vào cách chọn projection trong ngữ cảnh Hibernate/JPA:

- Phân biệt entity query, scalar projection và DTO projection.
- Dùng JPQL constructor expression, Java record, interface projection của Spring Data JPA.
- Dùng Criteria API, Tuple và native SQL khi phù hợp.
- Xử lý association, aggregate, pagination và dữ liệu lặp khi join.
- Tránh N+1, fetch quá nhiều và những projection gây tải entity ngầm.
- Chọn projection cho read use case và entity cho write use case.
- Hiểu tác động đến persistence context, transaction, lazy loading và hiệu năng.
- Kiểm thử query và mapping dựa trên SQL thực tế.

> Các ví dụ dùng Jakarta Persistence và Hibernate ORM hiện đại; một số ví dụ repository dùng Spring Data JPA. API, khả năng hỗ trợ record, native projection và dynamic projection phụ thuộc phiên bản JPA/Hibernate/Spring Data đang dùng. Luôn đối chiếu tài liệu của đúng phiên bản trong dự án.

## 2. Entity query và DTO projection khác nhau ở đâu?

Giả sử entity sản phẩm:

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    @OneToMany(mappedBy = "product")
    private List<ProductImage> images = new ArrayList<>();

    @Version
    private long version;

    protected Product() {}

    public void changePrice(BigDecimal newPrice) {
        if (newPrice.signum() < 0) {
            throw new IllegalArgumentException("Price must not be negative");
        }
        this.price = newPrice;
    }

    // getters ...
}
~~~

Trang danh sách chỉ cần ba trường:

~~~text
ID | Name | Price
---+------+------
10 | Java | 299.00
11 | SQL  | 199.00
~~~

### 2.1. Đọc entity

~~~java
List<Product> products = entityManager.createQuery(
    "select p from Product p where p.active = true order by p.name",
    Product.class
).getResultList();
~~~

Kết quả là các entity Product được quản lý trong persistence context hiện tại (nếu query chạy trong context phù hợp). Hibernate materialize entity theo mapping, quản lý identity và dirty checking, đồng thời có thể thiết lập proxy/collection cho association lazy.

Nếu sau đó code làm:

~~~java
for (Product product : products) {
    System.out.println(product.getCategory().getName());
}
~~~

mỗi lần truy cập category có thể kích hoạt truy vấn bổ sung nếu association chưa được nạp. Với nhiều sản phẩm, điều này dễ tạo N+1.

### 2.2. Đọc DTO projection

Khai báo read model:

~~~java
public record ProductCard(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

JPQL constructor expression:

~~~java
List<ProductCard> cards = entityManager.createQuery(
    "select new com.example.catalog.ProductCard(" +
    "p.id, p.name, p.price) " +
    "from Product p " +
    "where p.active = true " +
    "order by p.name",
    ProductCard.class
).getResultList();
~~~

Kết quả là những object ProductCard chứa đúng các giá trị được chọn. DTO không phải Product entity và không được Hibernate theo dõi như một managed entity. Sửa một DTO không làm thay đổi bảng products.

SQL có thể có hình dạng:

~~~sql
SELECT p.id, p.name, p.price
FROM products p
WHERE p.active = true
ORDER BY p.name;
~~~

Cột thực tế, alias và cú pháp phụ thuộc mapping/dialect. Điểm chính là query chỉ yêu cầu các trường cần cho màn hình.

### 2.3. So sánh

| Tiêu chí | Entity query | DTO projection |
|---|---|---|
| Kết quả | Entity instance | Đối tượng đọc hoặc scalar |
| Managed trong persistence context | Có, nếu entity được truy vấn trong context | Không, DTO không phải entity |
| Dirty checking | Có | Không |
| Dữ liệu được chọn | Theo entity mapping và fetch plan | Theo danh sách field/query |
| Association | Có thể lazy/eager theo mapping | Chỉ lấy giá trị được query chọn |
| Phù hợp | Use case thay đổi domain state | Danh sách, báo cáo, API đọc |
| Có thể persist/remove trực tiếp | Entity có thể tham gia lifecycle | DTO không phải entity |
| Cấu trúc kết quả | Gắn với domain/persistence model | Gắn với nhu cầu trình bày/đọc |

**Không có nghĩa DTO projection luôn nhanh hơn entity query.** Với query đơn giản chỉ một entity, fetch plan tốt và context nhỏ, chênh lệch có thể không đáng kể. Projection có lợi khi nó tránh tải nhiều cột, nhiều association hoặc nhiều entity không cần thiết. Hãy đo SQL, số row, số round-trip, memory và thời gian mapping trong workload thật.

## 3. Khi nào nên chọn DTO projection?

Một cách ra quyết định hữu ích là bắt đầu từ mục tiêu của use case.

### 3.1. Dùng DTO khi chỉ cần hiển thị hoặc trả dữ liệu

Ví dụ:

- Product card: ID, tên, giá.
- Order list: mã đơn, ngày tạo, trạng thái, tổng tiền.
- Customer search result: ID, tên, email.
- Dashboard: count, sum, average.
- Báo cáo: nhóm theo tháng, loại hoặc khu vực.
- Autocomplete: ID và nhãn.
- API read response: một cấu trúc dữ liệu ổn định, không cần domain methods.

Trong những trường hợp này, DTO mô tả chính xác hợp đồng dữ liệu của use case. Query không cần tải toàn bộ entity graph chỉ để chuyển thành JSON.

### 3.2. Dùng entity khi cần hành vi và thay đổi trạng thái

Ví dụ cập nhật giá:

~~~java
@Transactional
public void changeProductPrice(Long id, BigDecimal newPrice) {
    Product product = entityManager.find(Product.class, id);
    if (product == null) {
        throw new EntityNotFoundException("Product not found");
    }

    product.changePrice(newPrice);
}
~~~

Entity ở đây hữu ích vì domain method kiểm tra quy tắc và Hibernate dirty-check thay đổi. Nếu chỉ lấy ProductCard, đổi giá trên DTO sẽ không cập nhật entity.

### 3.3. Có thể kết hợp entity và DTO trong cùng ứng dụng

~~~text
Read use case:
  Query -> DTO projection -> API response

Write use case:
  Command/ID -> load managed entity
              -> domain behavior
              -> flush/commit
~~~

Không cần ép toàn bộ ứng dụng dùng DTO hoặc toàn bộ dùng entity. Chọn kết quả phù hợp với công việc.

### 3.4. Map entity sang DTO sau khi load không phải DTO projection

~~~java
List<Product> products = repository.findAll();

return products.stream()
    .map(p -> new ProductResponse(
        p.getId(),
        p.getName(),
        p.getCategory().getName()
    ))
    .toList();
~~~

Đây là mapping entity sang DTO ở tầng Java, không phải database DTO projection. Hibernate vẫn tải Product entities và có thể truy vấn category từng lần. Nếu Product có nhiều field/association, việc map sau khi load không làm giảm lượng dữ liệu đã đọc.

Khi mục tiêu là chỉ lấy ID, tên và tên category, hãy cân nhắc query projection trực tiếp.

## 4. JPQL constructor expression: cách chuẩn và dễ kiểm soát

JPA hỗ trợ constructor expression với từ khóa `new`:

~~~sql
select new com.example.catalog.ProductCard(p.id, p.name, p.price)
from Product p
where p.active = true
~~~

### 4.1. Quy tắc cơ bản

- Tên class trong `new` là tên đầy đủ (fully qualified class name), gồm package.
- Constructor phải nhận tham số theo đúng thứ tự và kiểu tương thích với các biểu thức SELECT.
- Số tham số phải khớp constructor được gọi.
- Tên tham số của DTO không cần trùng alias hay tên field entity.
- Constructor expression tạo object kết quả; object đó không trở thành managed entity chỉ vì được tạo từ JPQL.
- Query vẫn dùng tên entity và thuộc tính Java, không dùng trực tiếp tên bảng/cột SQL như native SQL.

DTO dạng class:

~~~java
package com.example.catalog;

public class ProductCard {
    private final Long id;
    private final String name;
    private final BigDecimal price;

    public ProductCard(Long id, String name, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
}
~~~

JPQL:

~~~java
List<ProductCard> cards = em.createQuery(
    "select new com.example.catalog.ProductCard(p.id, p.name, p.price) " +
    "from Product p where p.active = true",
    ProductCard.class
).getResultList();
~~~

### 4.2. Java record phù hợp với read model bất biến

~~~java
public record ProductCard(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Record cung cấp constructor canonical, accessor và semantics value-based tiện cho dữ liệu đọc. Constructor expression có thể tạo record nếu provider hỗ trợ constructor tương ứng và kiểu tham số khớp.

Record chỉ bất biến ở mức tham chiếu component: nếu component là một collection mutable, bản thân collection vẫn có thể thay đổi. Với DTO đọc đơn giản gồm ID, String, BigDecimal, LocalDate, Instant và các value types, record thường phù hợp.

Nếu dự án dùng JPA/Hibernate version cũ, xác nhận khả năng constructor projection với record thay vì giả định mọi provider hỗ trợ như nhau.

### 4.3. Alias không phải điều kiện cho constructor expression

Với constructor expression, thứ tự biểu thức là yếu tố quyết định:

~~~java
select new com.example.catalog.ProductCard(
    p.id, p.name, p.price
)
~~~

Đổi thứ tự thành `p.name, p.id, p.price` sẽ không còn khớp constructor. Alias có ích cho interface projection/Tuple, nhưng không thay thế chữ ký constructor.

### 4.4. Constructor projection với join

Màn hình cần tên category:

~~~java
public record ProductCard(
    Long id,
    String name,
    BigDecimal price,
    String categoryName
) {}
~~~

JPQL:

~~~java
List<ProductCard> cards = em.createQuery(
    "select new com.example.catalog.ProductCard(" +
    "p.id, p.name, p.price, c.name) " +
    "from Product p " +
    "left join p.category c " +
    "where p.active = true " +
    "order by p.name",
    ProductCard.class
).getResultList();
~~~

`LEFT JOIN` giữ sản phẩm chưa có category; `categoryName` có thể null. Nếu dùng `JOIN` (inner join), sản phẩm không có category sẽ không xuất hiện.

### 4.5. Constructor expression với giá trị nullable

Nếu category có thể không tồn tại, constructor DTO phải chấp nhận giá trị null:

~~~java
public record ProductCard(
    Long id,
    String name,
    BigDecimal price,
    String categoryName
) {}
~~~

Không dùng primitive như `long`, `int`, `double` cho component có thể null. Dùng wrapper (`Long`, `Integer`, `Double`) hoặc quy định rõ giá trị thay thế trong query.

Có thể dùng `coalesce` khi nghiệp vụ thực sự muốn chuỗi mặc định:

~~~sql
select new com.example.catalog.ProductCard(
    p.id, p.name, p.price, coalesce(c.name, 'Uncategorized')
)
from Product p left join p.category c
~~~

Không dùng `coalesce` chỉ để che mất sự khác nhau giữa “không có category” và “category có tên rỗng”.

## 5. Scalar projection: khi chỉ cần một vài giá trị

Nếu kết quả chỉ là một giá trị, không cần DTO riêng.

### 5.1. Một cột

~~~java
List<String> names = em.createQuery(
    "select p.name from Product p where p.active = true",
    String.class
).getResultList();
~~~

### 5.2. Một giá trị tổng hợp

~~~java
Long count = em.createQuery(
    "select count(p) from Product p where p.active = true",
    Long.class
).getSingleResult();
~~~

~~~java
BigDecimal total = em.createQuery(
    "select sum(p.price) from Product p where p.active = true",
    BigDecimal.class
).getSingleResult();
~~~

Với `sum`, kết quả có thể null nếu không có hàng phù hợp, tùy kiểu biểu thức và database/provider semantics. Cần xác định cách xử lý null; có thể dùng `coalesce` hoặc wrapper logic.

### 5.3. Nhiều scalar bằng Object[] hoặc Tuple

Một query nhiều biểu thức:

~~~java
List<Object[]> rows = em.createQuery(
    "select p.id, p.name, p.price from Product p",
    Object[].class
).getResultList();
~~~

Cách này đơn giản nhưng khó đọc vì phải nhớ index:

~~~java
Long id = (Long) row[0];
String name = (String) row[1];
BigDecimal price = (BigDecimal) row[2];
~~~

Có thể dùng `Tuple` để truy cập theo alias:

~~~java
List<Tuple> rows = em.createQuery(
    "select p.id as id, p.name as name, p.price as price " +
    "from Product p",
    Tuple.class
).getResultList();

for (Tuple row : rows) {
    Long id = row.get("id", Long.class);
    String name = row.get("name", String.class);
    BigDecimal price = row.get("price", BigDecimal.class);
}
~~~

`Tuple` phù hợp cho query động hoặc số lượng cột thay đổi theo điều kiện. Với read model cố định được dùng rộng rãi, DTO/record thường biểu đạt contract rõ hơn và giảm lỗi cast/index.

## 6. Spring Data JPA interface projection

Spring Data JPA bổ sung cơ chế projection bằng interface. Đây là tính năng của Spring Data, không phải kiểu DTO chuẩn được định nghĩa bởi Jakarta Persistence.

### 6.1. Closed interface projection

Khai báo interface:

~~~java
public interface ProductCardView {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<ProductCardView> findByActiveTrueOrderByNameAsc();
}
~~~

Spring Data có thể tạo projection proxy và chỉ lấy những thuộc tính cần thiết cho closed projection trong các trường hợp phù hợp. SQL cụ thể cần được kiểm tra; không nên giả định mọi nested property đều được chuyển thành một truy vấn tối ưu.

### 6.2. Projection qua @Query và alias

~~~java
public interface ProductCategoryView {
    Long getId();
    String getProductName();
    String getCategoryName();
}
~~~

~~~java
@Query("""
    select p.id as id,
           p.name as productName,
           c.name as categoryName
    from Product p
    left join p.category c
    where p.active = true
    order by p.name
    """)
List<ProductCategoryView> findActiveProductCards();
~~~

Alias cần khớp tên property/accessor projection theo cách Spring Data ánh xạ. Với query native, alias cột cần đặc biệt chú ý vì database có thể trả tên theo snake_case hoặc chữ thường; không giả định tự động camel-case mapping trong mọi version/provider.

### 6.3. Closed projection và open projection

Closed projection chỉ khai báo accessor ánh xạ tới thuộc tính cụ thể:

~~~java
public interface ProductNameView {
    String getName();
}
~~~

Open projection có thể dùng SpEL để tính từ target:

~~~java
public interface ProductLabel {
    @Value("#{target.name + ' - ' + target.price}")
    String getLabel();
}
~~~

Open projection cần truy cập target entity để tính biểu thức và có thể khiến provider phải tải nhiều dữ liệu hơn. Khi mục tiêu là query chỉ lấy một vài cột, closed projection hoặc explicit DTO query thường dễ dự đoán hơn.

### 6.4. Nested interface projection

Có thể khai báo:

~~~java
public interface ProductWithCategory {
    Long getId();
    String getName();
    CategoryView getCategory();

    interface CategoryView {
        Long getId();
        String getName();
    }
}
~~~

Nested projection tiện cho cấu trúc kết quả lồng nhau. Tuy nhiên, việc Spring Data tạo join/materialize projection phụ thuộc loại projection, query, mapping và version. Đặc biệt với collection/to-many association, nested projection có thể tạo nhiều row hoặc join rộng. Nếu cần kiểm soát chính xác số cột và join, explicit JPQL constructor expression thường rõ hơn.

## 7. Class-based projection trong Spring Data JPA

Ngoài interface, Spring Data JPA hỗ trợ DTO class/record projection.

~~~java
public record ProductSummary(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Repository method có thể dùng query:

~~~java
@Query("""
    select new com.example.catalog.ProductSummary(
        p.id, p.name, p.price
    )
    from Product p
    where p.active = true
    order by p.name
    """)
List<ProductSummary> findActiveSummaries();
~~~

Spring Data cũng có thể suy luận constructor projection từ derived query trong các trường hợp phù hợp. Nếu DTO có nhiều constructor, có thể cần đánh dấu constructor được dùng bằng annotation thích hợp của Spring Data (ví dụ `@PersistenceCreator`) theo version.

### 7.1. Dynamic projection

Một repository có thể cho caller chọn kiểu projection:

~~~java
<T> Collection<T> findByCategoryId(Long categoryId, Class<T> type);
~~~

Caller có thể yêu cầu entity hoặc một projection type được hỗ trợ:

~~~java
Collection<Product> entities =
    repository.findByCategoryId(categoryId, Product.class);

Collection<ProductSummary> summaries =
    repository.findByCategoryId(categoryId, ProductSummary.class);
~~~

Dynamic projection hữu ích khi nhiều caller cần các hình dạng đọc khác nhau từ cùng điều kiện lọc. Nhưng không nên biến repository thành một API projection tùy ý cho mọi trường hợp: query phức tạp, aggregate và join đặc biệt thường dễ bảo trì hơn với method/query riêng có tên rõ.

## 8. Criteria API và DTO projection

Khi query được xây dựng động theo bộ lọc, Criteria API có thể tạo DTO qua `CriteriaBuilder.construct`.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<ProductCard> cq = cb.createQuery(ProductCard.class);
Root<Product> product = cq.from(Product.class);

cq.select(cb.construct(
    ProductCard.class,
    product.get("id"),
    product.get("name"),
    product.get("price")
));

cq.where(cb.isTrue(product.get("active")));
cq.orderBy(cb.asc(product.get("name")));

List<ProductCard> result = em.createQuery(cq).getResultList();
~~~

`construct` tìm constructor phù hợp với các biểu thức được truyền theo thứ tự. Kiểu và thứ tự tham số vẫn phải khớp DTO.

### 8.1. Criteria với join

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<ProductCard> cq = cb.createQuery(ProductCard.class);
Root<Product> product = cq.from(Product.class);
Join<Product, Category> category =
    product.join("category", JoinType.LEFT);

cq.select(cb.construct(
    ProductCard.class,
    product.get("id"),
    product.get("name"),
    product.get("price"),
    category.get("name")
));

cq.where(cb.isTrue(product.get("active")));
~~~

Ví dụ cần DTO ProductCard có constructor bốn tham số tương ứng. Criteria API giúp tạo predicate, join và sort động mà vẫn chọn kết quả DTO.

Với query chỉ có vài điều kiện cố định, JPQL thường dễ đọc hơn. Criteria phù hợp khi nhiều filter optional cần được ghép bằng code.

## 9. Aggregate projection cho báo cáo và dashboard

DTO projection không chỉ dành cho một hàng entity. Nó đặc biệt hữu ích với dữ liệu tổng hợp.

Giả sử entity Order có `createdAt`, `status`, `totalAmount`. Dashboard cần doanh thu và số đơn theo tháng:

~~~java
public record MonthlySales(
    Integer year,
    Integer month,
    Long orderCount,
    BigDecimal revenue
) {}
~~~

JPQL minh họa:

~~~java
List<MonthlySales> rows = em.createQuery(
    "select new com.example.reporting.MonthlySales(" +
    "year(o.createdAt), month(o.createdAt), count(o), sum(o.totalAmount)) " +
    "from Order o " +
    "where o.status = :status " +
    "group by year(o.createdAt), month(o.createdAt) " +
    "order by year(o.createdAt), month(o.createdAt)",
    MonthlySales.class
).setParameter("status", OrderStatus.COMPLETED)
 .getResultList();
~~~

JPQL hỗ trợ các hàm ngày như `year`/`month` theo khả năng ngôn ngữ/provider; nếu query function không portable hoặc database có cách nhóm thời gian riêng, cân nhắc function được hỗ trợ hoặc native SQL.

### 9.1. Vì sao aggregate projection tiết kiệm hơn?

Nếu chỉ cần số đơn và tổng doanh thu, không cần tải từng Order entity rồi cộng bằng Java:

~~~java
List<Order> orders = ...;
BigDecimal revenue = orders.stream()
    .map(Order::getTotalAmount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Cách này tải nhiều hàng/entity, tiêu tốn bộ nhớ và có thể kích hoạt association không cần thiết. Aggregate ở database cho phép DB tính COUNT/SUM và trả về số hàng tổng hợp nhỏ hơn.

### 9.2. Null trong aggregate

Một số hàm tổng hợp như `SUM` có thể trả null khi không có input row phù hợp. DTO nên dùng wrapper/value type chấp nhận null, hoặc query dùng `coalesce` nếu nghiệp vụ xác định giá trị mặc định:

~~~sql
coalesce(sum(o.totalAmount), 0)
~~~

Kiểu số của biểu thức aggregate cần khớp constructor. Ví dụ `count` trả `Long`; không khai báo constructor nhận `Integer` rồi kỳ vọng tự chuyển đổi trong mọi provider.

## 10. Projection qua nhiều association: join có thể nhân số hàng

Ví dụ Product có nhiều ProductImage. Query:

~~~sql
select p.id, p.name, i.url
from Product p
left join p.images i
~~~

Một sản phẩm có ba ảnh tạo ba row kết quả. DTO dạng:

~~~java
public record ProductImageRow(
    Long productId,
    String productName,
    String imageUrl
) {}
~~~

sẽ có ba DTO cho cùng một product. Đây là kết quả đúng của quan hệ to-many, nhưng có thể không khớp mong muốn một DTO Product chứa một collection ảnh.

### 10.1. Constructor DTO không tự gom collection

JPQL constructor expression tạo một kết quả cho mỗi row/tuple phù hợp. Nó không tự nhóm nhiều row thành một DTO với collection lồng nhau chỉ vì DTO có component List.

Có một số hướng:

- Trả về row DTO phẳng, rồi nhóm theo product ID ở tầng service.
- Chạy query thứ hai lấy ảnh theo danh sách product IDs.
- Dùng database aggregation như JSON aggregation nếu chấp nhận native SQL và phụ thuộc DB.
- Dùng entity fetch plan khi thực sự cần aggregate/domain graph đầy đủ.
- Thiết kế read model/materialized view cho báo cáo phức tạp.

### 10.2. Hai query để tránh cartesian multiplication

Một cách thường dễ kiểm soát:

1. Query trang sản phẩm thành ProductCard DTO.
2. Lấy danh sách IDs.
3. Query tất cả ảnh thuộc các IDs đó.
4. Nhóm ảnh theo product ID trong Java.
5. Ghép thành response DTO.

~~~java
public record ProductImageView(Long productId, String url) {}

public record ProductDetails(
    Long id,
    String name,
    BigDecimal price,
    List<String> imageUrls
) {}
~~~

JPQL ảnh:

~~~java
List<ProductImageView> images = em.createQuery(
    "select new com.example.catalog.ProductImageView(p.id, i.url) " +
    "from Product p join p.images i " +
    "where p.id in :ids",
    ProductImageView.class
).setParameter("ids", productIds).getResultList();
~~~

Sau đó nhóm theo `productId`. Nếu danh sách IDs rỗng, xử lý riêng để tránh query `IN :ids` với collection rỗng vì hành vi có thể phụ thuộc provider/database.

Hai query có thể tránh N+1 vì số query cố định theo page thay vì một query cho mỗi sản phẩm. Tuy nhiên, dữ liệu có thể thay đổi giữa hai câu query nếu transaction isolation cho phép; nếu cần một snapshot nhất quán, hãy chọn transaction/isolation phù hợp.

## 11. DTO projection và N+1

N+1 thường xuất hiện khi một query tải N entity, rồi code truy cập lazy association làm phát sinh thêm query.

~~~java
List<Product> products = em.createQuery(
    "select p from Product p where p.active = true",
    Product.class
).getResultList();

for (Product p : products) {
    System.out.println(p.getCategory().getName());
}
~~~

Có thể phát sinh:
- 1 query lấy products.
- N query lấy category nếu chưa có trong context/cache và từng association cần initialize.

### 11.1. Projection join thẳng field cần dùng

~~~java
public record ProductCategoryCard(
    Long id,
    String name,
    BigDecimal price,
    String categoryName
) {}
~~~

~~~java
List<ProductCategoryCard> cards = em.createQuery(
    "select new com.example.catalog.ProductCategoryCard(" +
    "p.id, p.name, p.price, c.name) " +
    "from Product p " +
    "left join p.category c " +
    "where p.active = true",
    ProductCategoryCard.class
).getResultList();
~~~

Query lấy dữ liệu category trong cùng câu SQL, không cần lazy-load category qua từng Product entity.

### 11.2. Projection không xóa mọi N+1 tự động

Nếu service tiếp tục query một association khác cho từng DTO:

~~~java
for (ProductCategoryCard card : cards) {
    Long stock = inventoryRepository.findStock(card.id());
}
~~~

vẫn có thể tạo N+1 ở tầng repository/service. DTO projection chỉ kiểm soát query được viết; nó không tự gom các truy vấn độc lập khác.

Giải pháp là:
- Join hoặc subquery trong query projection nếu phù hợp.
- Lấy tất cả dữ liệu phụ theo danh sách IDs.
- Dùng aggregate query trả một row cho mỗi key.
- Thiết kế read model để đáp ứng use case.
- Kiểm tra SQL count trong integration test/log.

### 11.3. EntityGraph và fetch join là lựa chọn khác

Nếu use case cần entity đầy đủ và association để thao tác domain, có thể dùng `JOIN FETCH` hoặc `@EntityGraph`. Các cách này điều chỉnh fetch plan của entity query, không phải DTO projection.

~~~java
List<Product> products = em.createQuery(
    "select p from Product p " +
    "left join fetch p.category " +
    "where p.active = true",
    Product.class
).getResultList();
~~~

Kết quả vẫn là managed Product entities. Nếu chỉ cần tên category cho response, DTO projection thường biểu đạt mục tiêu đọc rõ hơn.

## 12. Pagination với DTO projection

DTO projection phù hợp với màn hình danh sách có phân trang.

### 12.1. JPA setFirstResult/setMaxResults

~~~java
TypedQuery<ProductCard> query = em.createQuery(
    "select new com.example.catalog.ProductCard(p.id, p.name, p.price) " +
    "from Product p " +
    "where p.active = true " +
    "order by p.name, p.id",
    ProductCard.class
);

List<ProductCard> page = query
    .setFirstResult(offset)
    .setMaxResults(pageSize)
    .getResultList();
~~~

Thêm tie-breaker `p.id` giúp thứ tự ổn định hơn khi nhiều sản phẩm cùng tên. Nếu không có ORDER BY, database không bảo đảm thứ tự hàng giữa các lần query.

### 12.2. Spring Data Page

~~~java
@Query(
    value = """
        select new com.example.catalog.ProductSummary(
            p.id, p.name, p.price
        )
        from Product p
        where p.active = true
        """,
    countQuery = """
        select count(p)
        from Product p
        where p.active = true
        """
)
Page<ProductSummary> findActiveSummaries(Pageable pageable);
~~~

`Page` thường cần thêm count query để biết tổng số kết quả/trang. Có thể dùng `Slice` nếu UI chỉ cần biết còn trang tiếp theo và không cần tổng số hàng, qua đó tránh count query trong một số trường hợp.

### 12.3. Pagination với to-many join

Cẩn trọng với query:

~~~sql
select p from Product p
left join fetch p.images
order by p.id
~~~

Nếu một product có nhiều image, SQL row bị nhân lên. Database pagination trên join rows không tương đương pagination trên product identities. Hibernate có thể phải xử lý collection fetch pagination đặc biệt, đôi khi tải nhiều hàng rồi giới hạn trong memory hoặc cảnh báo theo cấu hình/version.

Với DTO projection cũng có vấn đề tương tự nếu query join to-many: một Product có thể chiếm nhiều row, khiến page bị tính theo rows chứ không phải số product duy nhất.

Cách an toàn thường là:
1. Phân trang ID/DTO của parent trước.
2. Query dữ liệu to-many cho IDs của page.
3. Ghép kết quả trong Java.

### 12.4. Count query phải phản ánh đúng điều kiện lọc

Nếu query có join to-many làm một product xuất hiện nhiều lần, count có thể cần `count(distinct p.id)`. Count query không nhất thiết giống nguyên văn query select; nó phải đếm đúng đơn vị hiển thị.

## 13. Native SQL và DTO projection

JPQL thuận tiện và portable hơn khi query diễn đạt được bằng entity model. Nhưng báo cáo có thể cần:
- Window functions.
- CTE.
- JSON aggregation.
- Database-specific date functions.
- Hints hoặc tối ưu đặc thù.
- Join tới view hoặc bảng không mapping thành entity.

Khi đó native SQL có thể phù hợp.

### 13.1. Native query với scalar result

~~~java
List<Object[]> rows = em.createNativeQuery(
    "select id, name, price from products where active = true"
).getResultList();
~~~

Kết quả Object[] phụ thuộc JDBC/DB types, nên phải cast cẩn thận. Với query dùng lâu dài, mapping rõ ràng hơn sẽ dễ bảo trì.

### 13.2. @SqlResultSetMapping và ConstructorResult

JPA hỗ trợ khai báo mapping kết quả native query tới constructor DTO:

~~~java
@SqlResultSetMapping(
    name = "ProductSummaryMapping",
    classes = @ConstructorResult(
        targetClass = ProductSummary.class,
        columns = {
            @ColumnResult(name = "id", type = Long.class),
            @ColumnResult(name = "name", type = String.class),
            @ColumnResult(name = "price", type = BigDecimal.class)
        }
    )
)
@Entity
@Table(name = "products")
public class Product {
    // Entity mapping...
}
~~~

Sử dụng:

~~~java
List<ProductSummary> summaries = em.createNativeQuery(
    "select id, name, price from products where active = true",
    "ProductSummaryMapping"
).getResultList();
~~~

Mapping cần khai báo ở nơi provider quét metadata theo quy tắc JPA. Alias cột trong native SQL phải khớp `@ColumnResult(name=...)`. Type conversion có thể phụ thuộc dialect/driver; kiểm tra kiểu số, timestamp, enum và null.

### 13.3. Spring Data interface projection với native query

~~~java
public interface ProductSummaryView {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
~~~

~~~java
@Query(
    value = """
        select p.id as id,
               p.name as name,
               p.price as price
        from products p
        where p.active = true
        """,
    nativeQuery = true
)
List<ProductSummaryView> findActiveSummaryViews();
~~~

Các alias được dùng để ánh xạ tới accessor. Tên cột/alias và quy tắc camel-case có thể khác giữa DB và Spring Data versions; khai báo alias rõ ràng và kiểm thử thực tế.

Nếu native result cần nhiều kiểu lồng nhau hoặc mapping phức tạp, `@SqlResultSetMapping`, DTO class hoặc một read model/service mapping rõ ràng thường dễ kiểm soát hơn interface projection.

### 13.4. Không đưa entity vào native result nếu chỉ cần DTO

Nếu native query trả về entity class, Hibernate sẽ materialize entity theo mapping và có thể đưa nó vào persistence context. Điều đó khác với constructor/scalar result mapping. Hãy xác định rõ kiểu kết quả trước khi chọn API.

## 14. DTO projection có read-only thật sự không?

DTO thường được dùng như read model, nhưng “read-only” là ý nghĩa ở tầng thiết kế, không phải một constraint tự động của database.

### 14.1. DTO không được dirty-check

~~~java
ProductCard card = ...;
// card là DTO, không phải managed Product.
~~~

Thay đổi một DTO (nếu DTO mutable) không tạo SQL UPDATE. Hibernate không theo dõi DTO trong persistence context.

### 14.2. Entity được chọn trong DTO có thể vẫn là managed

JPQL có thể trả cả entity trong constructor expression:

~~~java
public record ProductAndCategory(
    Product product,
    String categoryName
) {}
~~~

~~~java
select new com.example.catalog.ProductAndCategory(p, c.name)
from Product p left join p.category c
~~~

Ở đây Product là entity được chọn làm component; nó vẫn có thể là managed entity trong context. Không nên kết luận “constructor DTO thì tất cả dữ liệu bên trong đều detached/read-only”. Nếu DTO chứa entity references, lifecycle và lazy associations của những entity đó vẫn tồn tại.

Khi muốn một read model thuần dữ liệu, chọn scalar/value fields thay vì nhúng entity vào DTO.

### 14.3. @Transactional(readOnly = true) không phải bảo đảm cấm ghi ở database

Trong Spring:

~~~java
@Transactional(readOnly = true)
public List<ProductCard> findCards() {
    // ...
}
~~~

`readOnly = true` là hint/optimization cho transaction manager/provider và có thể ảnh hưởng flush behavior tùy cấu hình. Nó không tự thay thế quyền database, không đảm bảo mọi câu SQL ghi bị chặn và không biến entity thành DTO. Nếu cần bảo đảm không thể ghi, phải dùng quyền DB, kiến trúc và transaction policy phù hợp.

### 14.4. DTO không tự giải quyết consistency

Một DTO projection là kết quả query tại một thời điểm theo transaction/isolation và cache behavior tương ứng. Nếu query có nhiều phần hoặc hai query để ghép dữ liệu, những thay đổi đồng thời có thể làm kết quả không thuộc cùng một snapshot nếu isolation không bảo đảm.

Nếu read model cần snapshot nhất quán, hãy xác định transaction boundary/isolation và số câu query. Projection chỉ quyết định hình dạng dữ liệu trả về.

## 15. Các lỗi mapping và kiểu dữ liệu thường gặp

### 15.1. Constructor không khớp

Query:

~~~sql
select new com.example.ProductCard(p.id, p.name, p.price)
~~~

DTO:

~~~java
public ProductCard(String name, Long id, BigDecimal price) { ... }
~~~

Thứ tự/kiểu không khớp có thể khiến query thất bại khi parse hoặc thực thi. Đồng bộ:
- Số biểu thức SELECT.
- Thứ tự biểu thức.
- Kiểu Java tương thích.
- Constructor public/khả dụng theo yêu cầu provider.

### 15.2. Primitive và NULL

Nếu category.name null nhưng DTO constructor nhận primitive (không áp dụng cho String) hoặc component primitive tương ứng một cột nullable, mapping có thể lỗi hoặc không biểu đạt đúng dữ liệu. Dùng wrapper type khi giá trị có thể null và xác định default ở domain/query nếu thực sự cần.

### 15.3. Enum và converter

Nếu entity dùng `@Enumerated` hoặc `AttributeConverter`, JPQL projection thuộc tính enum thường trả về kiểu Java của attribute. Native query có thể trả kiểu DB khác, ví dụ VARCHAR hoặc integer; mapping phải khớp converter/driver và DTO constructor.

Không giả định native result tự gọi converter giống mọi entity attribute path trong mọi tình huống. Kiểm tra provider behavior hoặc dùng result mapping rõ.

### 15.4. Date/time và timezone

Các kiểu `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime` có semantics khác nhau. Khi projection native SQL, JDBC driver và DB type ảnh hưởng chuyển đổi. Không ép `Instant` thành chuỗi tùy tiện nếu API cần timestamp có timezone semantics rõ ràng.

### 15.5. BigDecimal và numeric precision

Đối với tiền tệ, dùng `BigDecimal` và cột `DECIMAL/NUMERIC` với precision/scale thích hợp. Aggregate có thể có precision khác với cột gốc. DTO nên nhận đúng kiểu và không dùng `double` để biểu diễn giá trị tiền chính xác.

### 15.6. Tên alias và chữ hoa/thường

Native SQL có thể làm DB normalize alias. Nếu projection dùng accessor `getProductName()`, đặt alias `productName` hoặc quy tắc được Spring Data hỗ trợ. Tránh dựa vào implicit mapping không được xác nhận.

## 16. Query projection và hiệu năng: cần đo điều gì?

Projection có thể giảm lượng dữ liệu và entity hydration, nhưng không tự bảo đảm query nhanh. Một projection join nhiều bảng hoặc aggregate trên cột không có index vẫn có thể chậm.

Khi so sánh entity query và DTO query, quan sát:

1. **Số câu SQL:** có N+1 hay không?
2. **Số cột:** query có lấy field/LOB không cần thiết không?
3. **Số row:** join to-many có nhân số row không?
4. **Execution plan:** DB có dùng index phù hợp, join order và predicate hợp lý không?
5. **Network payload:** dữ liệu trả từ DB có lớn không?
6. **Hydration/memory:** có materialize hàng nghìn entity và association không cần thiết không?
7. **Mapping cost:** constructor/proxy/DTO mapping có chi phí đáng kể không?
8. **Pagination/count:** có query count bổ sung hoặc OFFSET lớn không?
9. **Cache:** kết quả đo có bị ảnh hưởng bởi first-level/second-level/query cache không?
10. **Consistency:** có cần nhiều query để ghép DTO và có yêu cầu snapshot nhất quán không?

### 16.1. SQL logging

Trong môi trường phát triển/test, bật SQL logging theo cấu hình Hibernate phù hợp version để xác nhận:
- Cột nào được SELECT.
- Join nào được thực thi.
- Query bổ sung có phát sinh khi gọi accessor không.
- Bulk query có đồng bộ context không.
- Count query có chạy cùng Page không.

Không bật log bind parameter chứa dữ liệu nhạy cảm ở production nếu không có chính sách bảo vệ.

### 16.2. Đo trên dữ liệu đại diện

Dataset nhỏ có thể che giấu N+1 và thiếu index. Cần đo với:
- Số hàng gần thực tế.
- Phân bố association (một parent có bao nhiêu child).
- Tỷ lệ null/optional relationship.
- Bộ lọc và sort phổ biến.
- Kích thước page thật.
- Cache warm/cold theo cách ứng dụng chạy.

Đừng chọn projection chỉ dựa trên số lượng dòng code hoặc giả định “ít cột chắc chắn nhanh hơn”. Hãy xác nhận query plan và thời gian thực tế.

## 17. Những trường hợp nên cân nhắc cách khác

### 17.1. Cần thay đổi trạng thái aggregate

Nếu use case cần kiểm tra nhiều business invariants, cập nhật nhiều entity liên quan và phát domain event, tải managed aggregate thường phù hợp hơn DTO projection. Không dùng DTO đọc để thay thế domain model cho command.

### 17.2. Cần nhiều collection lồng nhau

Một DTO lớn chứa danh sách con, danh sách cháu và nhiều quan hệ to-many có thể tạo SQL join nhân hàng hoặc yêu cầu grouping phức tạp. Cân nhắc:
- Parent DTO page + query con theo ID.
- Nhiều projection phẳng rồi group.
- Entity graph khi cần domain graph.
- Read model được denormalize/materialize.
- Native SQL JSON aggregation nếu chấp nhận phụ thuộc DB.

### 17.3. Query động phức tạp

Criteria API, QueryDSL hoặc specification có thể giúp ghép predicate. Nếu cấu trúc query phức tạp đến mức constructor expression khó đọc, có thể tách query builder hoặc dùng Tuple/native mapping rõ ràng. Không nhất thiết phải ép mọi truy vấn vào một method repository dài.

### 17.4. Cần cache kết quả báo cáo

DTO projection không tự cung cấp cache. Nếu dữ liệu báo cáo ít thay đổi và có thể cache, hãy chọn cache key, TTL, invalidation và consistency rõ. Query cache Hibernate và application cache có lifecycle khác nhau; không trộn chúng với persistence context.

## 18. Quy trình chọn projection cho một use case

Một quy trình thực tế:

1. Viết ra chính xác các field API/màn hình cần.
2. Xác định nguồn dữ liệu và association nào cần join.
3. Xác định mỗi kết quả tương ứng một entity, một row join hay một nhóm aggregate.
4. Chọn scalar, DTO constructor, Spring interface projection, Tuple hoặc native mapping.
5. Xác định nullability và kiểu Java của từng field.
6. Xác định sort, pagination và count semantics.
7. Kiểm tra query không gây N+1 hoặc nhân row ngoài ý muốn.
8. Kiểm tra DTO có nhúng entity managed hay chỉ value fields.
9. Xác định transaction/isolation nếu kết quả ghép từ nhiều query.
10. Đo SQL, execution plan và memory trên dữ liệu đại diện.

### Ví dụ: màn hình tìm kiếm sản phẩm

Yêu cầu:
- Chỉ lấy sản phẩm đang hoạt động.
- Lọc theo từ khóa tên.
- Hiển thị ID, tên, giá và tên category.
- Sắp xếp theo tên, ID.
- Trả trang 20 kết quả.

DTO:

~~~java
public record ProductSearchRow(
    Long id,
    String name,
    BigDecimal price,
    String categoryName
) {}
~~~

JPQL:

~~~java
TypedQuery<ProductSearchRow> query = em.createQuery(
    "select new com.example.catalog.ProductSearchRow(" +
    "p.id, p.name, p.price, c.name) " +
    "from Product p " +
    "left join p.category c " +
    "where p.active = true " +
    "and lower(p.name) like :keyword " +
    "order by p.name, p.id",
    ProductSearchRow.class
);

List<ProductSearchRow> rows = query
    .setParameter("keyword", "%" + keyword.toLowerCase(Locale.ROOT) + "%")
    .setFirstResult(offset)
    .setMaxResults(20)
    .getResultList();
~~~

Đây là một query DTO phẳng:
- Không cần load Product entity.
- Category chỉ được join để lấy tên.
- Sản phẩm chưa có category vẫn được trả do LEFT JOIN.
- ID là tie-breaker cho sort.
- `page * 20` cần kiểm tra overflow/giới hạn đầu vào trong code production.
- `%keyword%` có thể không dùng index B-tree thông thường; nếu tìm kiếm lớn, xem full-text/trigram/index phù hợp database.

Nếu API cần tổng số kết quả, chạy count query có cùng predicate; nếu chỉ cần `hasNext`, có thể lấy `pageSize + 1` hoặc dùng Spring Data Slice.

## 19. Các lỗi thường gặp khi dùng DTO projection

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query báo không tìm thấy constructor | FQCN, số tham số, thứ tự hoặc kiểu không khớp | Kiểm tra constructor expression và DTO |
| DTO nhận null dù entity có dữ liệu | LEFT JOIN, alias, nullability hoặc mapping | Kiểm tra join/predicate và SQL |
| DTO query vẫn phát N+1 | Query/service khác tải association theo từng row | Join/project hoặc batch query theo IDs |
| Projection trả nhiều dòng cho một parent | Join to-many nhân row | Group, query con riêng hoặc aggregate |
| Page có ít parent hơn pageSize | Pagination áp dụng trên joined rows | Page parent IDs trước rồi tải child |
| Interface projection native trả null | Alias/case không khớp accessor | Đặt alias rõ, kiểm tra version |
| DTO mapping lỗi với aggregate | Kiểu count/sum không khớp constructor | Dùng Long, BigDecimal và xử lý null |
| find() trả entity cũ sau native update | First-level cache còn managed instance | Refresh/clear/context mới có kiểm soát |
| DTO không lưu thay đổi | DTO không phải managed entity | Dùng command service và load entity |
| DTO chứa entity vẫn lazy-load | Component của DTO là managed entity/proxy | Chỉ chọn scalar/value fields nếu muốn read model thuần |
| @Transactional(readOnly=true) vẫn có SQL ghi | Read-only là hint, không phải DB permission | Dùng quyền DB và transaction policy phù hợp |
| Query DTO chậm hơn entity query | Join/aggregate/plan hoặc thiếu index | Đo execution plan và số row |
| Count page rất chậm | Count query phức tạp hoặc join trùng | Tối ưu count, distinct, Slice nếu phù hợp |
| Native projection sai timezone/precision | JDBC/DB type conversion | Map kiểu rõ, test đúng DB/driver |
| Record projection không chạy ở version cũ | Provider chưa hỗ trợ constructor/type mong muốn | Dùng DTO class constructor hoặc nâng cấp phù hợp |

## 20. Bài tập tự luyện

### Bài 1 — Danh sách đơn giản

Màn hình chỉ cần ID, tên và giá của 50 sản phẩm.

**Câu hỏi:** nên query entity rồi map sang DTO, hay constructor projection?

**Định hướng:** Nếu không cần domain behavior/association, DTO projection trực tiếp thường tránh tải state không cần. So sánh SQL thực tế để xác nhận.

### Bài 2 — Cập nhật giá

Service phải kiểm tra giá không âm, kiểm tra trạng thái sản phẩm và thay đổi giá.

**Câu hỏi:** DTO projection có thay entity query được không?

**Định hướng:** Không nên dùng read DTO làm command model. Load managed Product, gọi domain method và để Hibernate dirty-check.

### Bài 3 — Category optional

Product có thể không có Category. Query DTO dùng INNER JOIN.

**Câu hỏi:** sản phẩm chưa có category có xuất hiện không?

**Đáp án:** Không. Dùng LEFT JOIN nếu muốn giữ sản phẩm đó và chấp nhận categoryName null.

### Bài 4 — Constructor không khớp

Query chọn `(p.id, p.name, p.price)`, DTO constructor nhận `(String, Long, BigDecimal)`.

**Câu hỏi:** lỗi nằm ở đâu?

**Đáp án:** Thứ tự/kiểu constructor không khớp biểu thức SELECT. Sửa chữ ký hoặc thứ tự query.

### Bài 5 — N+1

Query lấy 100 Product entities rồi gọi `getCategory().getName()` từng phần tử.

**Câu hỏi:** DTO projection giải quyết thế nào?

**Định hướng:** Join category và chọn `c.name` trực tiếp vào DTO, hoặc dùng fetch plan phù hợp nếu vẫn cần entity.

### Bài 6 — To-many join

Mỗi Product có 4 Image. Query DTO join images trả về 4 row cho Product đó.

**Câu hỏi:** constructor expression có tự gom thành một DTO chứa 4 URL không?

**Đáp án:** Không. Nó tạo kết quả theo row. Cần group, query thứ hai hoặc aggregation/read model khác.

### Bài 7 — Pagination

Query page Product và fetch join `p.images`.

**Câu hỏi:** vì sao pagination có thể sai/không hiệu quả?

**Định hướng:** Join collection nhân SQL rows. Page IDs/DTO của parent trước, rồi lấy child theo IDs.

### Bài 8 — Aggregate

Dashboard chỉ cần số đơn và tổng tiền.

**Câu hỏi:** có nên load tất cả Order entities rồi cộng trong Java?

**Định hướng:** Thường không. Dùng count, sum, group by và DTO projection để DB tính aggregate.

### Bài 9 — Spring interface projection

Interface có `@Value` SpEL truy cập `target.category.name`.

**Câu hỏi:** có chắc chỉ lấy đúng ba cột đã khai báo không?

**Định hướng:** Không. Open projection có thể cần target entity và dữ liệu liên quan. Dùng closed projection hoặc explicit query nếu cần kiểm soát.

### Bài 10 — Native SQL

Báo cáo cần window function và JSON aggregation riêng của PostgreSQL.

**Câu hỏi:** có nên cố viết JPQL constructor expression không?

**Định hướng:** Không bắt buộc. Native SQL phù hợp nếu cần tính năng DB-specific; dùng result mapping rõ và test đúng DB/driver.

### Bài 11 — DTO chứa entity

`ProductAndCategory` record chứa component `Product product`.

**Câu hỏi:** có thể xem toàn bộ record là detached/read-only không?

**Định hướng:** Không. Component Product vẫn có thể là managed entity; lazy loading và lifecycle vẫn áp dụng cho nó.

### Bài 12 — Hai query ghép response

Query 1 lấy trang Product; query 2 lấy images theo IDs.

**Câu hỏi:** dữ liệu có chắc cùng snapshot không?

**Định hướng:** Không tự động. Cần xác định transaction boundary/isolation và khả năng dữ liệu thay đổi giữa hai query.

## 21. Ghi nhớ

DTO projection phù hợp khi một use case **chỉ cần dữ liệu đọc cụ thể**. Nó cho phép query chọn đúng field, join đúng association và trả về một read model không tham gia persistence context.

Các lựa chọn chính:

- **Scalar projection:** một vài giá trị đơn lẻ như String, Long, BigDecimal.
- **JPQL constructor expression:** DTO class/record với constructor rõ ràng.
- **Spring Data interface projection:** accessor-based read view, hữu ích cho repository query.
- **Criteria construct:** DTO projection trong query được xây dựng động.
- **Tuple/Object[]:** kết quả nhiều cột linh hoạt, nhưng cần quản lý alias/index/type.
- **Native SQL result mapping:** cho query đặc thù database hoặc báo cáo phức tạp.

Khi dùng projection, vẫn phải quan tâm đến join cardinality, nullability, pagination, count query, N+1 ở những query khác, transaction consistency và kiểu dữ liệu. DTO không tự sửa mọi vấn đề hiệu năng; nó chỉ tạo điều kiện để ứng dụng đọc ít và đúng dữ liệu hơn.

**Quy tắc thực tế:** dùng DTO cho read use case có hình dạng dữ liệu xác định; dùng managed entity khi cần hành vi domain và cập nhật trạng thái. Chọn projection theo dữ liệu màn hình/API thật sự cần, sau đó xác nhận SQL và execution plan trên database mục tiêu.

### Tài liệu chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — JPQL constructor expressions, Criteria API, Tuple, native queries và entity lifecycle.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — HQL/JPQL, projections, fetching, query execution và performance theo version.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — query projections, fetching, batching và native query mapping.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — interface/class-based projections, dynamic projections, pagination và repository queries.
- [Spring Data JPA Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html) — closed/open/nested/interface/DTO projections.
- [Jakarta Persistence API](https://jakarta.ee/specifications/persistence/) — EntityManager, TypedQuery, CriteriaBuilder, Tuple và SqlResultSetMapping.

> Cú pháp JPQL/Criteria và khả năng mapping projection phụ thuộc JPA provider/version. Interface projection và dynamic projection là tính năng Spring Data JPA. Native SQL mapping phụ thuộc database, JDBC driver và alias/type conversion. Trong production, kiểm tra SQL thực tế và kiểm thử trên đúng hệ quản trị được triển khai.
