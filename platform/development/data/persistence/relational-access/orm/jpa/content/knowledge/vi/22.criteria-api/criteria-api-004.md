# Kết hợp Predicate theo điều kiện tìm kiếm tùy chọn trong JPA Criteria API

Một trang tìm kiếm sản phẩm thường cho phép người dùng điền **bất kỳ tập con nào của các bộ lọc**: tên hoặc SKU, trạng thái, danh mục, khoảng giá, tình trạng tồn kho, thời gian tạo và thứ tự sắp xếp. Người dùng có thể bỏ qua mọi tiêu chí, điền một tiêu chí, hoặc kết hợp nhiều tiêu chí.

Nếu viết một câu JPQL cố định cho từng tổ hợp, số trường hợp sẽ tăng rất nhanh. Chỉ với sáu bộ lọc có thể bật/tắt độc lập, đã có tới \(2^6 = 64\) tổ hợp. Cách phù hợp trong JPA là sử dụng **Criteria API** để tạo một truy vấn có cấu trúc, bổ sung những `Predicate` cần thiết theo dữ liệu đầu vào và kết hợp chúng bằng `CriteriaBuilder.and(...)`, `or(...)` và `not(...)`.

Ví dụ người dùng yêu cầu:

> Tìm sản phẩm đang bán, thuộc danh mục Sách hoặc Khóa học, giá từ 100.000 đến dưới 500.000, có hàng và tên chứa “Java”.

Ta muốn biểu diễn điều kiện logic:

~~~text
status = ACTIVE
AND category IN (BOOK, COURSE)
AND price >= 100000
AND price < 500000
AND stockQuantity > 0
AND (
    LOWER(name) LIKE '%java%'
    OR LOWER(sku) LIKE '%java%'
)
~~~

Nếu người dùng bỏ trống khoảng giá hoặc từ khóa, các điều kiện tương ứng **không được thêm vào**. Một bộ lọc bắt buộc như `tenantId` hoặc quyền truy cập vẫn phải được áp dụng trong mọi trường hợp.

Bài học tập trung vào việc xây dựng những điều kiện tìm kiếm **tùy chọn nhưng có ngữ nghĩa rõ ràng**, kết hợp chính xác AND/OR, xử lý null và collection rỗng, dùng JOIN/subquery khi cần, tái sử dụng logic giữa truy vấn danh sách và truy vấn đếm, đồng thời giữ an toàn kiểu dữ liệu, phân quyền và hiệu năng.

## 1. Predicate là gì trong Criteria API?

Các thành phần quan trọng:

| Thành phần | Vai trò |
| --- | --- |
| `EntityManager` | Tạo/truy cập persistence context và thực thi query |
| `CriteriaBuilder` | Tạo biểu thức, điều kiện, phép toán, ORDER BY và CriteriaQuery |
| `CriteriaQuery<T>` | Biểu diễn cấu trúc SELECT với kiểu kết quả T |
| `Root<T>` | Đại diện entity nguồn trong FROM |
| `Path<X>` | Đại diện đường dẫn tới một thuộc tính được ánh xạ |
| `Expression<T>` | Một biểu thức có kiểu trong truy vấn |
| `Predicate` | Một biểu thức điều kiện logic dùng trong WHERE, HAVING, ON... |
| `Join<Z, X>` | Biểu diễn JOIN qua association của entity |
| `TypedQuery<T>` | Đối tượng thực thi query và trả kết quả có kiểu T |

`Predicate` thuộc gói `jakarta.persistence.criteria` và là một dạng biểu thức Boolean của truy vấn. Nó **không phải** `java.util.function.Predicate<T>` dùng để lọc `Stream` trong bộ nhớ.

Ví dụ:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> p = cq.from(Product.class);

Predicate active = cb.equal(
    p.get("status"), ProductStatus.ACTIVE);
Predicate affordable = cb.lessThanOrEqualTo(
    p.<BigDecimal>get("price"),
    new BigDecimal("500000.00"));

cq.select(p).where(cb.and(active, affordable));

List<Product> products = em.createQuery(cq).getResultList();
~~~

`cb.equal(...)` tạo một điều kiện; `cb.lessThanOrEqualTo(...)` tạo điều kiện thứ hai; `cb.and(...)` kết hợp chúng. **Chưa có SQL chỉ vì đã tạo Predicate**. Provider sẽ chuyển cây Criteria thành query phù hợp khi thực thi.

### Sơ đồ cấu trúc truy vấn

~~~text
CriteriaQuery<Product>
    |
    +-- FROM Product p
    |
    +-- WHERE AND
    |         |
    |         +-- EQUAL(p.status, ACTIVE)
    |         |
    |         +-- LESS_OR_EQUAL(p.price, 500000)
    |
    +-- SELECT p
    |
    +-- ORDER BY ...
             |
             v
         SQL do provider sinh
             |
             v
         Database thực thi
~~~

Điểm mạnh của cách này là **điều kiện được tạo thành các đối tượng**, không cần ghép các mảnh `" AND ..."` vào chuỗi JPQL dễ sai dấu cách, dấu ngoặc hoặc tham số.

## 2. Bài toán tìm kiếm động khác truy vấn cố định thế nào?

Với truy vấn cố định, ta luôn có các điều kiện như nhau:

~~~jpql
SELECT p FROM Product p
WHERE p.status = :status
AND p.price >= :minPrice
~~~

Nhưng trang tìm kiếm cho phép:

| Input người dùng | Điều kiện cần áp dụng |
| --- | --- |
| Không chọn trạng thái | Không lọc trạng thái |
| Chọn ACTIVE | `p.status = ACTIVE` |
| Nhập giá tối thiểu | `p.price >= :minPrice` |
| Bỏ trống giá tối đa | Không tạo điều kiện trần giá |
| Gõ “java” | `name LIKE ... OR sku LIKE ...` |
| Chọn hai danh mục | `category.id IN (...)` |
| Không chọn danh mục nào | Theo hợp đồng API: bỏ bộ lọc hoặc không có kết quả; **phải chọn rõ** |
| Chọn “còn hàng” | `stockQuantity > 0` |
| Chọn “hết hàng” | `stockQuantity <= 0` |

Với Criteria API, pattern phổ biến là:

1. Tạo `CriteriaBuilder`, `CriteriaQuery` và `Root`.
2. Tạo một `List<Predicate>` rỗng.
3. Kiểm tra từng input, chỉ thêm Predicate khi cần.
4. Dùng `cb.and(predicates.toArray(...))` để kết hợp.
5. Thêm SELECT, ORDER BY, pagination rồi thực thi.

Các bước này được minh họa đầy đủ sau khi giới thiệu mô hình dữ liệu.

## 3. Mô hình entity ví dụ

Xét một hệ thống catalog đa tenant:

~~~text
Tenant A                         Tenant B
    |                                |
    v                                v
Product#101                     Product#901
  tenantId=A                      tenantId=B
  name="Java Basics"               name="Java Advanced"
  sku="BK-JAVA"                    sku="COURSE-JAVA"
  status=ACTIVE                    status=ACTIVE
  price=150000                     price=800000
  stockQuantity=20                 stockQuantity=0
  category -> Category#10          category -> Category#80
~~~

Với các bộ lọc tùy chọn, điều kiện `tenantId` **không phải tùy chọn**. Dù người dùng không nhập gì, query chỉ được trả những Product trong tenant hiện hành.

### 3.1. Enum trạng thái

~~~java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    INACTIVE
}
~~~

### 3.2. Category

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

    @Column(nullable = false, unique = true)
    private String code;

    @Column(nullable = false)
    private String name;

    protected Category() {
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }
}
~~~

### 3.3. Product

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
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "name", nullable = false)
    private String name;

    @Column(name = "description")
    private String description;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private ProductStatus status;

    @Column(name = "price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal price;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "category_id", nullable = true)
    private Category category;

    protected Product() {
    }
}
~~~

Ở đây `category` **có thể null** để minh họa lọc “chưa được phân loại”. Khi nghiệp vụ bắt buộc mỗi sản phẩm có category, có thể đổi mapping và constraint thành không nullable; khi đó bộ lọc “không có category” trở nên vô nghĩa.

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE categories (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL,
    price NUMERIC(14,2) NOT NULL,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    category_id BIGINT,
    CONSTRAINT fk_product_category
        FOREIGN KEY (category_id) REFERENCES categories(id),
    CONSTRAINT uq_product_tenant_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT ck_product_price CHECK (price >= 0),
    CONSTRAINT ck_product_stock CHECK (stock_quantity >= 0)
);
~~~

`@Column(unique=true)` ở `Category.code` tương ứng với giả định code global unique trong mẫu này; product SKU chỉ unique trong tenant vì ràng buộc `(tenant_id, sku)`. Entity/Product mapping không tự tạo mọi constraint ở database nếu dự án quản lý schema bằng migration.

**Lưu ý đa tenant:** lọc Product theo `tenantId` ngăn trả Product của tenant khác, nhưng chưa tự chứng minh FK Category thuộc đúng tenant. Khi Category thực tế cũng tenant-scoped, cần thiết kế composite FK hoặc quy tắc sở hữu phù hợp để tránh tham chiếu chéo tenant.

## 4. DTO chứa các bộ lọc tùy chọn

Thay vì truyền nhiều tham số rời rạc, tạo một đối tượng mô tả bộ lọc:

~~~java
package com.example.catalog;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Set;

public record ProductFilter(
        String keyword,
        Set<ProductStatus> statuses,
        Set<Long> categoryIds,
        BigDecimal minPrice,
        BigDecimal maxPriceExclusive,
        Boolean inStock,
        Instant createdFromInclusive,
        Instant createdToExclusive,
        Boolean categoryMissing) {
}
~~~

Đoạn này sử dụng Java `record` (Java 16+). Với dự án dùng Java cũ, có thể viết POJO với getter và constructor tương đương.

Quy ước ngữ nghĩa:

| Trường | `null` | Có giá trị |
| --- | --- | --- |
| `keyword` | Không lọc tên/SKU | Tìm keyword trong tên hoặc SKU |
| `statuses` | Không lọc trạng thái | Chỉ nhận status thuộc tập đã chọn |
| `categoryIds` | Không lọc category | Chỉ nhận category trong tập |
| `minPrice` | Không áp trần dưới | Giá từ mức này trở lên |
| `maxPriceExclusive` | Không áp trần trên | Giá nhỏ hơn mức này |
| `inStock` | Không lọc tồn kho | `true`: còn hàng; `false`: hết hàng |
| `createdFromInclusive` | Không lọc thời điểm bắt đầu | Tạo từ thời điểm đó |
| `createdToExclusive` | Không lọc thời điểm kết thúc | Tạo trước thời điểm đó |
| `categoryMissing` | Không lọc tình trạng phân loại | `true`: category NULL; `false`: category không NULL |

Với `statuses` hoặc `categoryIds`:

- `null` có nghĩa **người dùng không cung cấp bộ lọc này**.
- Collection rỗng có thể có nghĩa **người dùng chọn tập giá trị rỗng, nên không hàng nào khớp**.

Đây là **một lựa chọn hợp đồng API có chủ đích**, không phải quy tắc bắt buộc của JPA. Một UI khác có thể xem collection rỗng như “tất cả”; khi đó phải chuẩn hóa input rõ từ boundary và giữ đồng nhất trong toàn hệ thống.

### Tại sao đặt tên Exclusive/Inclusive?

Với giá và thời gian, ký hiệu biên là một phần của nghiệp vụ:

~~~text
minPrice <= price < maxPriceExclusive
createdFromInclusive <= createdAt < createdToExclusive
~~~

Không nên để cùng một field mang lúc thì nghĩa nhỏ hơn, lúc lại nhỏ hơn hoặc bằng. Tên rõ giúp tránh lỗi điều kiện khoảng ở biên, nhất là với ngày giờ và phân trang theo thời gian.

## 5. Mẫu cơ bản: tạo List<Predicate> và nối AND

Ví dụ tối giản chỉ có ba bộ lọc:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> p = cq.from(Product.class);

List<Predicate> predicates = new ArrayList<>();

predicates.add(cb.equal(
    p.get("tenantId"), tenantId));

if (status != null) {
    predicates.add(cb.equal(
        p.get("status"), status));
}

if (minPrice != null) {
    predicates.add(cb.greaterThanOrEqualTo(
        p.<BigDecimal>get("price"), minPrice));
}

cq.select(p).where(
    cb.and(predicates.toArray(Predicate[]::new))
);

List<Product> results = em.createQuery(cq).getResultList();
~~~

Cần import `jakarta.persistence.criteria.CriteriaBuilder`, `CriteriaQuery`, `Predicate`, `Root` cùng `java.util.ArrayList`, `List` và `BigDecimal`.

### Tại sao tenant được thêm đầu tiên?

`tenantId` là điều kiện **bắt buộc**, không phụ thuộc tình trạng người dùng nhập các ô filter khác. Khi mọi predicate được nối bằng AND, không có nhánh OR tùy chọn nào được phép bỏ qua tenant.

### Có cần lặp `cq.where(...)` sau từng filter?

Không. Có thể dựng mọi predicate trước rồi áp dụng một lần bằng `where(...)`. Cần lưu ý rằng các lần gọi `where(...)` liên tiếp theo API Criteria **thay thế tập restriction cũ**, không tự thêm AND vào restriction trước đó.

Sai về ý định:

~~~java
cq.where(cb.equal(p.get("status"), status));
cq.where(cb.greaterThan(p.<BigDecimal>get("price"), minPrice));
// Lần gọi where thứ hai không có nghĩa tự AND với lần đầu.
~~~

Cách đúng:

~~~java
Predicate byStatus = cb.equal(p.get("status"), status);
Predicate byPrice = cb.greaterThan(
    p.<BigDecimal>get("price"), minPrice);

cq.where(cb.and(byStatus, byPrice));
~~~

Hoặc tích lũy vào `List<Predicate>` rồi gọi `where(...)` một lần.

## 6. Ý nghĩa của and(), or() và not()

CriteriaBuilder có các phép kết hợp Boolean:

~~~java
Predicate both = cb.and(a, b);
Predicate either = cb.or(a, b);
Predicate opposite = cb.not(a);
~~~

| Biểu thức | Ý nghĩa |
| --- | --- |
| `cb.and(a, b)` | a **và** b đều đúng |
| `cb.or(a, b)` | a **hoặc** b đúng |
| `cb.not(a)` | Phủ định điều kiện a |
| `cb.conjunction()` | Predicate hằng đúng (TRUE) |
| `cb.disjunction()` | Predicate hằng sai (FALSE) |

### Kết hợp nhiều điều kiện cùng một toán tử

~~~java
Predicate allRequired = cb.and(
    tenantPredicate,
    activePredicate,
    pricePredicate
);
~~~

Hoặc:

~~~java
Predicate oneOf = cb.or(
    nameMatches,
    skuMatches,
    descriptionMatches
);
~~~

JPA có các overload varargs, nên có thể truyền mảng `Predicate[]` hoặc nhiều predicate theo số lượng động.

### Cấu trúc tổng thể quan trọng hơn số lượng Predicate

Yêu cầu:

~~~text
tenant=A
AND status=ACTIVE
AND (name chứa 'java' OR sku chứa 'java')
~~~

Cách đúng:

~~~java
Predicate tenant = cb.equal(p.get("tenantId"), tenantId);
Predicate active = cb.equal(
    p.get("status"), ProductStatus.ACTIVE);
Predicate textMatch = cb.or(
    nameLike,
    skuLike
);

cq.where(cb.and(tenant, active, textMatch));
~~~

Không được viết:

~~~java
cq.where(cb.or(
    cb.and(tenant, active, nameLike),
    skuLike
));
~~~

vì nhánh `skuLike` có thể đúng **mà không cần tenant hay ACTIVE**, dẫn tới lọt dữ liệu ngoài phạm vi.

## 7. Dấu ngoặc AND/OR là một phần của nghiệp vụ

Giả sử yêu cầu:

> Hiển thị sản phẩm ACTIVE còn hàng, **hoặc** sản phẩm DRAFT được tạo trong 24 giờ gần đây; tất cả đều phải thuộc tenant hiện tại.

Logic:

~~~text
tenant = currentTenant
AND (
    (status = ACTIVE AND stockQuantity > 0)
    OR
    (status = DRAFT AND createdAt >= cutoff)
)
~~~

Criteria:

~~~java
Predicate activeInStock = cb.and(
    cb.equal(p.get("status"), ProductStatus.ACTIVE),
    cb.greaterThan(p.<Integer>get("stockQuantity"), 0)
);

Predicate recentDraft = cb.and(
    cb.equal(p.get("status"), ProductStatus.DRAFT),
    cb.greaterThanOrEqualTo(
        p.<Instant>get("createdAt"), cutoff)
);

Predicate allowedState = cb.or(activeInStock, recentDraft);

cq.where(cb.and(
    cb.equal(p.get("tenantId"), tenantId),
    allowedState
));
~~~

**Không dựa vào thứ tự thêm phần tử vào List để tự tạo dấu ngoặc.** Mỗi `cb.and(...)`/`cb.or(...)` là một nút trong cây biểu thức, vì vậy hãy tạo các nhóm logic có tên, rồi ghép chúng rõ ràng.

### Bảng chân trị ngắn

| A | B | `AND(A,B)` | `OR(A,B)` |
| --- | --- | --- | --- |
| true | true | true | true |
| true | false | false | true |
| false | true | false | true |
| false | false | false | false |

Trong SQL còn có giá trị logic **UNKNOWN** do NULL; vì thế phép NOT/AND/OR ở database không phải lúc nào cũng giống Boolean Java hai giá trị. Phần sau sẽ giải thích.

## 8. Predicate rỗng: conjunction và disjunction

Đây là hai trường hợp rất quan trọng khi các bộ lọc đều tùy chọn.

~~~java
Predicate alwaysTrue = cb.conjunction();
Predicate alwaysFalse = cb.disjunction();
~~~

Theo ngữ nghĩa Criteria API:

- `cb.and()` với **0** đối số là điều kiện đúng.
- `cb.or()` với **0** đối số là điều kiện sai.
- `cb.conjunction()` là TRUE.
- `cb.disjunction()` là FALSE.

Ví dụ:

~~~java
List<Predicate> optional = new ArrayList<>();

if (status != null) {
    optional.add(cb.equal(p.get("status"), status));
}
if (minPrice != null) {
    optional.add(cb.ge(p.<BigDecimal>get("price"), minPrice));
}

Predicate combined =
    cb.and(optional.toArray(Predicate[]::new));
~~~

Khi cả hai input null, `combined` có nghĩa TRUE — tức **không lọc thêm**. Nếu còn `tenant` bắt buộc, cần kết hợp:

~~~java
cq.where(cb.and(
    cb.equal(p.get("tenantId"), tenantId),
    combined
));
~~~

### Vì sao cb.or(empty) có thể là bug?

Nếu tích lũy các lựa chọn “một trong các điều kiện”:

~~~java
List<Predicate> alternatives = new ArrayList<>();
Predicate matchAny =
    cb.or(alternatives.toArray(Predicate[]::new));
~~~

Khi alternatives rỗng, điều kiện là FALSE, tức không có hàng nào khớp. Điều này có thể **đúng** nếu người dùng chọn tập rỗng thực sự, nhưng **sai** nếu ý định là “không áp bộ lọc”.

Hãy xác định:

~~~text
Input không được cung cấp  -> bỏ filter hoặc TRUE.
Input cung cấp tập rỗng    -> không có kết quả (FALSE) nếu API chọn nghĩa đó.
~~~

Không tự lấy `cb.and(empty)` hoặc `cb.or(empty)` thay thế cho quyết định ngữ nghĩa của API.

## 9. Phân biệt null, rỗng và chuỗi toàn khoảng trắng

Với filter từ khóa:

~~~text
null          -> không nhập
""            -> input rỗng
"   "         -> chỉ có khoảng trắng
" Java "      -> có nội dung sau chuẩn hóa
~~~

Một quy tắc UI thường hợp lý: null, chuỗi rỗng hoặc chỉ khoảng trắng đều có nghĩa **không lọc theo từ khóa**.

~~~java
String normalized = keyword == null
    ? null
    : keyword.strip();

if (normalized != null && !normalized.isBlank()) {
    // Tạo Predicate tìm kiếm.
}
~~~

`strip()` và `isBlank()` có từ Java 11. Nếu dự án dùng Java 8, có thể thay bằng một chiến lược trim/kiểm tra whitespace phù hợp, lưu ý khác biệt Unicode.

### Không áp quy tắc này tùy tiện cho mọi input

Với một trường dữ liệu mà **chuỗi rỗng có ý nghĩa** (ví dụ mã được phép rỗng, mặc dù hiếm), việc bỏ chuỗi rỗng làm mất khả năng tìm các row có giá trị rỗng. Quy tắc chuẩn hóa thuộc **hợp đồng filter**, không phải mặc định bắt buộc của JPA.

## 10. So sánh bằng: equal và notEqual

Một enum trạng thái đơn:

~~~java
if (status != null) {
    predicates.add(cb.equal(
        p.get("status"), status));
}
~~~

Loại trạng thái DRAFT:

~~~java
if (excludeDraft) {
    predicates.add(cb.notEqual(
        p.get("status"), ProductStatus.DRAFT));
}
~~~

Có thể viết:

~~~java
cb.not(cb.equal(p.get("status"), ProductStatus.DRAFT));
~~~

Trong trường hợp thuộc tính có thể NULL, `<>` hoặc `NOT (=)` không tự bao gồm hàng NULL. SQL sử dụng ba giá trị TRUE/FALSE/UNKNOWN, và WHERE chỉ giữ các hàng có predicate TRUE.

### Gắn enum đúng kiểu

Nếu Product.status có `@Enumerated(EnumType.STRING)`, trong Criteria nên truyền:

~~~java
ProductStatus.ACTIVE
~~~

chứ không tự chuyển sang `"ACTIVE"` rồi mong mapping luôn chấp nhận. Criteria Builder và provider dùng kiểu thuộc tính Java để tạo binding tương ứng.

## 11. Phạm vi giá: >=, >, <=, < và between

Giả sử người dùng muốn giá trong khoảng:

~~~text
minPrice <= price < maxPriceExclusive
~~~

Criteria:

~~~java
if (minPrice != null) {
    predicates.add(cb.greaterThanOrEqualTo(
        p.<BigDecimal>get("price"), minPrice));
}

if (maxPriceExclusive != null) {
    predicates.add(cb.lessThan(
        p.<BigDecimal>get("price"), maxPriceExclusive));
}
~~~

`BigDecimal` là kiểu phù hợp hơn `double` cho giá tiền.

### Cách viết với ge/lt

CriteriaBuilder còn có:

~~~java
cb.ge(p.<BigDecimal>get("price"), minPrice);
cb.lt(p.<BigDecimal>get("price"), maxPriceExclusive);
~~~

`ge`/`lt` là các toán tử so sánh số, còn `greaterThanOrEqualTo`/`lessThan` xử lý biểu thức có kiểu so sánh phù hợp. Chọn một phong cách rõ ràng, nhất quán.

### BETWEEN thường bao gồm cả hai đầu

~~~java
Predicate within = cb.between(
    p.<BigDecimal>get("price"),
    minPrice,
    maxPrice);
~~~

Biểu thức này tương đương về ý định với:

~~~text
price >= minPrice AND price <= maxPrice
~~~

Nếu filter sử dụng **max exclusive**, không dùng `between` để tránh sai trường hợp giá đúng bằng biên trên.

### Validate khoảng trước khi dựng query

~~~java
if (minPrice != null && minPrice.signum() < 0) {
    throw new IllegalArgumentException("minPrice âm");
}
if (maxPriceExclusive != null && maxPriceExclusive.signum() < 0) {
    throw new IllegalArgumentException("maxPrice âm");
}
if (minPrice != null
        && maxPriceExclusive != null
        && minPrice.compareTo(maxPriceExclusive) >= 0) {
    throw new IllegalArgumentException(
        "Khoảng giá không hợp lệ");
}
~~~

Giá min bằng max exclusive tạo tập rỗng. API có thể chọn trả danh sách rỗng thay vì lỗi, nhưng phải thống nhất; ví dụ chọn **báo lỗi input mâu thuẫn** để người gọi nhận được phản hồi rõ.

## 12. Bộ lọc thời gian với Instant: khoảng nửa mở

Đối với thời điểm tạo:

~~~java
if (from != null) {
    predicates.add(cb.greaterThanOrEqualTo(
        p.<Instant>get("createdAt"), from));
}

if (toExclusive != null) {
    predicates.add(cb.lessThan(
        p.<Instant>get("createdAt"), toExclusive));
}
~~~

Khoảng `[from, to)` tránh phải giả định “cuối ngày” là `23:59:59.999`, trong khi database có độ chính xác timestamp khác Java.

### Tìm theo ngày kinh doanh

Nếu UI chọn ngày 2027-05-01 ở múi giờ Việt Nam:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2027, 5, 1);

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1)
                 .atStartOfDay(zone).toInstant();
~~~

Sau đó dùng `createdAt >= start AND createdAt < end`. Đoạn code yêu cầu import `java.time.ZoneId`, `LocalDate` và `Instant`.

Không cắt chuỗi ISO timestamp theo 10 ký tự đầu rồi so sánh như ngày UTC nếu nghiệp vụ định nghĩa ngày theo timezone khác. Với những vùng có daylight saving time, độ dài một ngày theo giờ địa phương cũng không nhất thiết luôn 24 giờ.

### Lọc thời gian độc lập với thời gian hiện tại

Nếu bộ lọc là “bảy ngày gần nhất”, service nên nhận một thời điểm `now`/Clock do ứng dụng cung cấp và tính cutoff một lần, để count query và list query dùng **cùng mốc**. Không gọi `Instant.now()` độc lập trong từng lần tạo Predicate nếu muốn hai câu query có điều kiện hoàn toàn đồng nhất.

## 13. Optional Boolean: false không giống không cung cấp

Một bộ lọc tồn kho thường có ba trạng thái:

~~~text
null  -> Không quan tâm còn hay hết hàng.
true  -> Chỉ sản phẩm còn hàng (stockQuantity > 0).
false -> Chỉ sản phẩm hết hàng (stockQuantity <= 0).
~~~

Criteria:

~~~java
if (inStock != null) {
    if (inStock) {
        predicates.add(cb.greaterThan(
            p.<Integer>get("stockQuantity"), 0));
    } else {
        predicates.add(cb.lessThanOrEqualTo(
            p.<Integer>get("stockQuantity"), 0));
    }
}
~~~

**Sai lầm phổ biến:** viết `if (Boolean.TRUE.equals(inStock))` rồi bỏ qua luôn trường hợp false. Điều đó có thể phù hợp với filter chỉ có nút “Chỉ còn hàng” (false nghĩa bỏ lọc), nhưng **không phù hợp với filter ba trạng thái** “Tất cả/Còn hàng/Hết hàng”.

Quy ước Boolean phải được quyết định theo UI/API và được test rõ.

## 14. IN với nhiều giá trị trạng thái hoặc category

Người dùng có thể chọn nhiều trạng thái:

~~~java
if (statuses != null) {
    if (statuses.isEmpty()) {
        predicates.add(cb.disjunction());
    } else {
        predicates.add(p.get("status").in(statuses));
    }
}
~~~

Với danh mục:

~~~java
if (categoryIds != null) {
    if (categoryIds.isEmpty()) {
        predicates.add(cb.disjunction());
    } else {
        predicates.add(
            p.get("category").get("id").in(categoryIds));
    }
}
~~~

`Expression.in(Collection<?>)` có ngữ nghĩa membership. Nhiều provider dịch thành SQL `IN (?, ?, ...)`, nhưng SQL cụ thể và cách bind theo dialect.

### Tại sao xử lý tập rỗng ở tầng Java?

Không phải mọi provider/DBMS xử lý `IN ()` giống nhau; có nơi biến đổi thành điều kiện FALSE, nơi khác có thể sinh cú pháp không hợp lệ. Dùng `cb.disjunction()` giúp diễn đạt rõ rằng **tập cho phép rỗng nghĩa không hàng nào khớp**.

### Một tập giá trị chứa null

Đừng kỳ vọng:

~~~java
List.of(1L, null)
~~~

hợp lệ (`List.of` không nhận null), và cũng không nên trộn null vào tập IDs rồi xem `IN` có nghĩa “hoặc category IS NULL”. SQL `IN (..., NULL)` không tự tương đương điều kiện IS NULL.

Nếu API muốn “category thuộc tập IDs **hoặc** chưa phân loại”:

~~~java
Predicate included = p.get("category").get("id")
    .in(categoryIds);
Predicate uncategorized = cb.isNull(p.get("category"));

predicates.add(cb.or(included, uncategorized));
~~~

Đây là **một nhóm OR nằm bên trong AND tổng thể**, không phải điều kiện OR thay thế các predicate tenant và quyền truy cập.

### Bộ lọc quá nhiều giá trị

Nếu categoryIds có hàng chục nghìn ID, `IN` có thể tạo câu SQL dài, vượt giới hạn số bind parameters hoặc làm kế hoạch truy vấn kém hiệu quả. Cần giới hạn kích thước input, chunking theo thiết kế hoặc dùng temporary tables/table-valued parameters theo DBMS.

## 15. NULL phải dùng isNull/isNotNull

Với Product.category nullable:

~~~java
if (categoryMissing != null) {
    predicates.add(categoryMissing
        ? cb.isNull(p.get("category"))
        : cb.isNotNull(p.get("category")));
}
~~~

Không viết:

~~~java
cb.equal(p.get("category"), null);
~~~

và mặc định nó tương đương `IS NULL` ở mọi provider. Cú pháp và semantics SQL với NULL khác phép so sánh thông thường; hãy dùng đúng API `isNull(...)`/`isNotNull(...)`.

### SQL có ba giá trị logic

Giả sử `description` nullable:

| Giá trị description | `description = 'Java'` | `description <> 'Java'` |
| --- | --- | --- |
| "Java" | TRUE | FALSE |
| "Spring" | FALSE | TRUE |
| NULL | UNKNOWN | UNKNOWN |

Trong WHERE, chỉ các hàng với predicate TRUE được giữ. Vì thế `cb.notEqual(description, "Java")` **không tự bao gồm** các Product có description NULL.

Nếu muốn “description khác Java **hoặc trống NULL**”:

~~~java
Predicate notJava = cb.notEqual(
    p.get("description"), "Java");
Predicate absent = cb.isNull(p.get("description"));
predicates.add(cb.or(notJava, absent));
~~~

### Tránh tự suy luận với Boolean nullable

Một cột Boolean nullable có ba trạng thái TRUE/FALSE/NULL, khác một field Java `boolean` primitive vốn chỉ có hai trạng thái. Đối với cờ tùy chọn trong filter request, dùng `Boolean` hoặc enum ba trạng thái để không đánh mất ý nghĩa “không lọc”.

## 16. LIKE với từ khóa tùy chọn và nhiều cột

Yêu cầu tìm sản phẩm có từ khóa xuất hiện ở **name hoặc SKU**:

~~~text
(LOWER(name) LIKE :pattern OR LOWER(sku) LIKE :pattern)
~~~

Criteria:

~~~java
if (keyword != null && !keyword.isBlank()) {
    String searchText = keyword.strip()
        .toLowerCase(Locale.ROOT);

    String pattern = "%" + escapeLike(searchText) + "%";

    Predicate matchName = cb.like(
        cb.lower(p.<String>get("name")),
        pattern, '!');

    Predicate matchSku = cb.like(
        cb.lower(p.<String>get("sku")),
        pattern, '!');

    predicates.add(cb.or(matchName, matchSku));
}
~~~

Hàm escape:

~~~java
private static String escapeLike(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
~~~

`%` và `_` là wildcard trong LIKE. Binding giá trị dưới dạng parameter bảo vệ khỏi injection **vào cấu trúc query**, nhưng **không tự escape wildcard** nếu người dùng thực sự muốn tìm dấu phần trăm hoặc gạch dưới.

### Vì sao dùng ký tự ESCAPE '!'?

`cb.like(expression, pattern, '!')` cho biết `!` là escape character. Khi tìm văn bản có ký tự `%`, hàm escape chuyển thành `!%` để LIKE hiểu đó là ký tự thường trong biểu thức pattern.

Thứ tự thay thế quan trọng: escape chính `!` trước, rồi mới escape `%` và `_`.

### Nối AND bên ngoài, OR bên trong

Ví dụ:

~~~java
Predicate keywordMatch = cb.or(
    matchName,
    matchSku
);
predicates.add(keywordMatch);
~~~

Sau đó:

~~~java
Predicate all = cb.and(
    predicates.toArray(Predicate[]::new));
~~~

Như vậy bộ lọc từ khóa có nghĩa **(name OR sku)**, nhưng các filter khác — tenant, trạng thái, giá — vẫn nối **AND**.

### LIKE không phải full-text search

`LOWER(name) LIKE '%java%'` tiện cho dữ liệu vừa và nhỏ, nhưng tiền tố wildcard `%` có thể khiến B-tree index thông thường khó tối ưu. Với catalog lớn, cần xem tính năng DB như trigram/full-text index hoặc search engine. Còn phân biệt chữ hoa/thường và Unicode cũng phụ thuộc collation/cách chuẩn hóa của DB.

## 17. Kết hợp nhiều từ khóa: ALL terms và ANY term

Nếu người dùng nhập:

~~~text
java persistence
~~~

Ứng dụng có thể có hai ngữ nghĩa:

- **ALL terms:** Product phải khớp cả “java” **và** “persistence”.
- **ANY term:** Product chỉ cần khớp ít nhất một trong hai.

Với ALL terms:

~~~java
List<Predicate> perTerm = new ArrayList<>();

for (String term : terms) {
    String pattern = "%" +
        escapeLike(term.toLowerCase(Locale.ROOT)) + "%";

    Predicate anywhere = cb.or(
        cb.like(cb.lower(p.<String>get("name")),
                pattern, '!'),
        cb.like(cb.lower(p.<String>get("sku")),
                pattern, '!')
    );

    perTerm.add(anywhere);
}

predicates.add(cb.and(
    perTerm.toArray(Predicate[]::new)));
~~~

ANY terms thay phép AND ngoài thành OR:

~~~java
predicates.add(cb.or(
    perTerm.toArray(Predicate[]::new)));
~~~

Trước vòng lặp phải:

1. Chuẩn hóa whitespace và tách term theo quy tắc UI.
2. Bỏ term rỗng.
3. Giới hạn **số lượng từ khóa** và độ dài input để tránh query quá lớn.
4. Quyết định input không có term là bỏ bộ lọc hay không có kết quả.

Không tự biến input người dùng thành JPQL fragment. Mỗi term là một **giá trị** dùng với `cb.like(...)`.

## 18. Một service hoàn chỉnh: ProductSearchService

Sau khi đã biết từng filter, ta xây dựng một class minh họa hoàn chỉnh. Mục tiêu:

- Tenant condition luôn được áp dụng.
- Filter optional độc lập.
- `null` collection nghĩa bỏ lọc; collection rỗng nghĩa không khớp.
- Keyword tìm theo name hoặc SKU.
- Khoảng giá và thời gian dùng biên nửa mở.
- Category có thể null.
- Sắp xếp được chọn từ enum whitelist.
- Có truy vấn danh sách phân trang và truy vấn COUNT dùng chung **logic dựng predicate**.

### 18.1. Enum chỉ định sort

~~~java
package com.example.catalog;

public enum ProductSort {
    NAME,
    PRICE,
    CREATED_AT
}
~~~

Không truyền trực tiếp tên field do người dùng nhập vào `root.get(rawUserInput)`. Service chuyển giá trị yêu cầu sắp xếp sang **enum đã được cho phép**.

### 18.2. Service

~~~java
package com.example.catalog;

import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Order;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class ProductSearchService {

    private final EntityManager em;

    public ProductSearchService(EntityManager em) {
        this.em = em;
    }

    public List<Product> findPage(
            long tenantId,
            ProductFilter filter,
            ProductSort sort,
            boolean descending,
            int page,
            int size) {

        validate(tenantId, filter);
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                "Page hoặc size không hợp lệ");
        }

        long offset = (long) page * size;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Offset vượt phạm vi cho phép");
        }

        CriteriaBuilder cb = em.getCriteriaBuilder();
        CriteriaQuery<Product> cq =
            cb.createQuery(Product.class);
        Root<Product> p = cq.from(Product.class);

        List<Predicate> predicates =
            buildPredicates(cb, p, tenantId, filter);

        cq.select(p);
        cq.where(cb.and(predicates.toArray(Predicate[]::new)));

        Path<?> sortPath = switch (sort) {
            case NAME -> p.get("name");
            case PRICE -> p.get("price");
            case CREATED_AT -> p.get("createdAt");
        };

        Order firstOrder = descending
            ? cb.desc(sortPath)
            : cb.asc(sortPath);

        cq.orderBy(
            firstOrder,
            cb.asc(p.get("id"))
        );

        TypedQuery<Product> q = em.createQuery(cq);
        q.setFirstResult((int) offset);
        q.setMaxResults(size);
        return q.getResultList();
    }

    public long countMatches(
            long tenantId,
            ProductFilter filter) {

        validate(tenantId, filter);
        CriteriaBuilder cb = em.getCriteriaBuilder();
        CriteriaQuery<Long> cq = cb.createQuery(Long.class);
        Root<Product> p = cq.from(Product.class);

        List<Predicate> predicates =
            buildPredicates(cb, p, tenantId, filter);

        cq.select(cb.count(p));
        cq.where(cb.and(predicates.toArray(Predicate[]::new)));

        return em.createQuery(cq).getSingleResult();
    }

    private static List<Predicate> buildPredicates(
            CriteriaBuilder cb,
            Root<Product> p,
            long tenantId,
            ProductFilter filter) {

        List<Predicate> result = new ArrayList<>();

        // Điều kiện bảo vệ dữ liệu, KHÔNG tùy chọn.
        result.add(cb.equal(p.get("tenantId"), tenantId));

        String keyword = filter.keyword();
        if (keyword != null && !keyword.isBlank()) {
            String token = keyword.strip()
                .toLowerCase(Locale.ROOT);
            String pattern = "%" + escapeLike(token) + "%";

            result.add(cb.or(
                cb.like(
                    cb.lower(p.<String>get("name")),
                    pattern, '!'),
                cb.like(
                    cb.lower(p.<String>get("sku")),
                    pattern, '!')
            ));
        }

        Set<ProductStatus> statuses = filter.statuses();
        if (statuses != null) {
            result.add(statuses.isEmpty()
                ? cb.disjunction()
                : p.get("status").in(statuses));
        }

        Set<Long> categoryIds = filter.categoryIds();
        if (categoryIds != null) {
            result.add(categoryIds.isEmpty()
                ? cb.disjunction()
                : p.get("category").get("id").in(categoryIds));
        }

        if (filter.minPrice() != null) {
            result.add(cb.greaterThanOrEqualTo(
                p.<BigDecimal>get("price"),
                filter.minPrice()));
        }

        if (filter.maxPriceExclusive() != null) {
            result.add(cb.lessThan(
                p.<BigDecimal>get("price"),
                filter.maxPriceExclusive()));
        }

        Boolean inStock = filter.inStock();
        if (inStock != null) {
            result.add(inStock
                ? cb.greaterThan(
                    p.<Integer>get("stockQuantity"), 0)
                : cb.lessThanOrEqualTo(
                    p.<Integer>get("stockQuantity"), 0));
        }

        if (filter.createdFromInclusive() != null) {
            result.add(cb.greaterThanOrEqualTo(
                p.<Instant>get("createdAt"),
                filter.createdFromInclusive()));
        }

        if (filter.createdToExclusive() != null) {
            result.add(cb.lessThan(
                p.<Instant>get("createdAt"),
                filter.createdToExclusive()));
        }

        if (filter.categoryMissing() != null) {
            result.add(filter.categoryMissing()
                ? cb.isNull(p.get("category"))
                : cb.isNotNull(p.get("category")));
        }

        return result;
    }

    private static String escapeLike(String value) {
        return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
    }

    private static void validate(
            long tenantId, ProductFilter filter) {
        if (tenantId <= 0) {
            throw new IllegalArgumentException(
                "Tenant ID không hợp lệ");
        }
        if (filter == null) {
            throw new IllegalArgumentException(
                "Filter không được null");
        }

        BigDecimal min = filter.minPrice();
        BigDecimal max = filter.maxPriceExclusive();

        if (min != null && min.signum() < 0) {
            throw new IllegalArgumentException(
                "minPrice không được âm");
        }
        if (max != null && max.signum() < 0) {
            throw new IllegalArgumentException(
                "maxPrice không được âm");
        }
        if (min != null && max != null
                && min.compareTo(max) >= 0) {
            throw new IllegalArgumentException(
                "Khoảng giá không hợp lệ");
        }

        Instant from = filter.createdFromInclusive();
        Instant to = filter.createdToExclusive();
        if (from != null && to != null
                && !from.isBefore(to)) {
            throw new IllegalArgumentException(
                "Khoảng thời gian không hợp lệ");
        }

        if (filter.categoryIds() != null
                && filter.categoryIds().stream()
                    .anyMatch(id -> id == null || id <= 0)) {
            throw new IllegalArgumentException(
                "Danh sách category chứa ID không hợp lệ");
        }

        if (filter.statuses() != null
                && filter.statuses().contains(null)) {
            throw new IllegalArgumentException(
                "Danh sách status chứa null");
        }
    }
}
~~~

### Một vài giả định có chủ đích

- Đây là code Java 17+ vì dùng `record`/switch expression và `Set`.
- Từng request có EntityManager/transaction boundary phù hợp; **không chia sẻ một EntityManager giữa các thread**.
- Giá trị tenantId phải lấy từ **ngữ cảnh xác thực đáng tin cậy**, không tin trực tiếp ID tenant do client tự khai báo.
- Record `ProductFilter` chỉ mô tả bộ lọc; quyền truy cập và tenant là điều kiện độc lập.
- Service minh họa trả entity Product; một API read-only thường cân nhắc DTO projection để tránh lazy loading và vô tình sửa entity.
- `categoryMissing=true` đồng thời `categoryIds` không rỗng sẽ là yêu cầu mâu thuẫn, cho ra tập rỗng (hoặc cách query liên kết có thể không tìm thấy hàng). Với API production có thể chọn validate conflict này ngay từ đầu để trả lỗi rõ.
- Nên giới hạn độ dài keyword, số lượng statuses/categoryIds và kích thước page ở tầng request validation trước khi truy vấn.

### Một lỗi dễ bỏ sót: sort là null

Trong đoạn minh họa, `sort` phải được caller chuẩn hóa thành một giá trị enum hợp lệ, chẳng hạn `ProductSort.CREATED_AT`. Nếu API cho phép bỏ sort, thêm:

~~~java
ProductSort effectiveSort =
    sort == null ? ProductSort.CREATED_AT : sort;
~~~

và switch trên `effectiveSort`. Không lấy raw string từ request đưa thẳng vào `root.get(...)`.

## 19. Cách gọi service từ một request tìm kiếm

Ví dụ người dùng tìm:

- Keyword `" java "`.
- Trạng thái ACTIVE.
- Danh mục 10 hoặc 11.
- Giá từ 100.000 đến dưới 500.000.
- Chỉ còn hàng.
- Không giới hạn ngày.

~~~java
ProductFilter filter = new ProductFilter(
    " java ",
    Set.of(ProductStatus.ACTIVE),
    Set.of(10L, 11L),
    new BigDecimal("100000.00"),
    new BigDecimal("500000.00"),
    true,
    null,
    null,
    null
);

List<Product> page = searchService.findPage(
    tenantId,
    filter,
    ProductSort.PRICE,
    false,
    0,
    20
);

long total = searchService.countMatches(tenantId, filter);
~~~

Provider có thể sinh SQL gần với:

~~~sql
SELECT p.*
FROM products p
WHERE p.tenant_id = ?
  AND (
      LOWER(p.name) LIKE ? ESCAPE '!'
      OR LOWER(p.sku) LIKE ? ESCAPE '!'
  )
  AND p.status IN (?)
  AND p.category_id IN (?, ?)
  AND p.price >= ?
  AND p.price < ?
  AND p.stock_quantity > 0
ORDER BY p.price ASC, p.id ASC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
~~~

Đây là **SQL minh họa**. Cú pháp pagination, biểu diễn enum, alias và thứ tự predicate do provider/dialect quyết định; không kiểm tra đúng-sai của Criteria bằng việc yêu cầu SQL sinh ra có cùng thứ tự AND như danh sách Java.

### Nếu người dùng không nhập bộ lọc nào?

~~~java
ProductFilter filter = new ProductFilter(
    null, null, null, null, null,
    null, null, null, null
);
~~~

Query vẫn có:

~~~text
WHERE tenant_id = currentTenant
~~~

**Không bao giờ vì tất cả filter optional đều null mà bỏ mất predicate tenant.**

## 20. Tái sử dụng Predicate giữa query danh sách và query đếm

Phân trang thường cần:

1. Query danh sách một trang, có `ORDER BY`, `setFirstResult` và `setMaxResults`.
2. Query `COUNT` tổng số entity khớp điều kiện, không pagination.

Hai query phải dùng **cùng định nghĩa filter**. Nếu một query quên điều kiện trạng thái hoặc category, UI sẽ hiển thị sai tổng số trang.

### Không dùng lại chính instance Predicate/Root giữa hai CriteriaQuery

Sai về cấu trúc:

~~~java
Root<Product> rootPage = pageQuery.from(Product.class);
Predicate onPageRoot = cb.equal(
    rootPage.get("status"), ProductStatus.ACTIVE);

countQuery.where(onPageRoot);  // Không nên tái sử dụng như thế.
~~~

`Predicate` và `Path` tham chiếu tới cây Criteria cụ thể. Một Root thuộc query trang không được coi là Root của count query khác. Tái sử dụng bằng cách **gọi lại hàm tạo Predicate với Root mới**, như `buildPredicates(cb, p, tenantId, filter)` trong ví dụ service.

### Tái sử dụng logic chứ không tái sử dụng node

~~~text
ProductFilter
      |
      +--> buildPredicates(cb, pageRoot, ...)
      |         |
      |         v
      |      CriteriaQuery<Product>
      |
      +--> buildPredicates(cb, countRoot, ...)
                |
                v
             CriteriaQuery<Long>
~~~

Hàm dựng predicate có thể được tổ chức thành các helper nhỏ theo domain, nhưng cần để hàm rõ:

- Có tạo JOIN không?
- Có thêm predicate quyền truy cập bắt buộc không?
- Có phụ thuộc loại query SELECT/COUNT không?
- Có làm query distinct/grouping không?

Đừng biến builder thành một hàm có side effect khó đoán trên CriteriaQuery chung.

## 21. Count query và DISTINCT khi xuất hiện JOIN nhiều giá trị

Ví dụ Product có thêm quan hệ nhiều–nhiều Tag:

~~~java
@ManyToMany
@JoinTable(
    name = "product_tags",
    joinColumns = @JoinColumn(name = "product_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
~~~

Tag là entity riêng có ID và name; mapping này chỉ minh họa phần mở rộng, không phải trường đã có trong Product ở mục 3.

Nếu tìm Product theo nhiều tag:

~~~java
Join<Product, Tag> t = p.join("tags", JoinType.INNER);
predicates.add(t.get("id").in(tagIds));
~~~

Một Product có hai Tag khớp có thể tạo **hai hàng JOIN cho cùng một Product**.

### Query danh sách

~~~java
cq.select(p).distinct(true);
~~~

`distinct(true)` biểu diễn mong muốn trả mỗi Product root một lần.

### Count query

~~~java
countQuery.select(cb.countDistinct(countRoot.get("id")));
~~~

Nếu dùng `cb.count(countRoot)` sau JOIN nhiều tag, có thể đếm trùng Product.

### Cẩn trọng với pagination và fetch join

Khi `JOIN FETCH` collection kết hợp `setFirstResult()/setMaxResults()`, provider có thể không phân trang hiệu quả trên root entities hoặc báo lỗi/tải nhiều hàng. Một chiến lược phổ biến:

1. Query trang **ID Product** theo filter và thứ tự ổn định.
2. Query nạp Product theo tập ID đã lấy và fetch associations khi cần.
3. Khôi phục thứ tự trang theo danh sách ID gốc.

Đây là vấn đề cardinality và fetch plan, không đơn thuần giải quyết bằng cách thêm DISTINCT.

## 22. JOIN tùy chọn qua Category

Nếu chỉ lọc theo category ID, biểu thức:

~~~java
p.get("category").get("id").in(categoryIds)
~~~

có thể được provider dịch sang JOIN hoặc sử dụng khóa FK tùy mapping. Khi cần tìm theo **Category.name**, có thể tạo JOIN:

~~~java
Join<Product, Category> category =
    p.join("category", JoinType.LEFT);

Predicate categoryNameMatch = cb.like(
    cb.lower(category.<String>get("name")),
    "%sach%"
);
predicates.add(categoryNameMatch);
~~~

### INNER JOIN hay LEFT JOIN?

- `INNER JOIN` loại Product không có Category.
- `LEFT JOIN` giữ Product không có Category ở tập JOIN ban đầu.
- Nhưng `WHERE category.name LIKE ...` vẫn loại những Product có Category NULL, vì predicate trên NULL trả UNKNOWN.

Do đó **LEFT JOIN + điều kiện thuộc tính phía phải trong WHERE không tự bảo đảm giữ entity thiếu quan hệ**.

### Từ khóa khớp name Product HOẶC name Category

Nếu muốn giữ Product chưa phân loại nhưng tên Product vẫn khớp:

~~~java
Join<Product, Category> category =
    p.join("category", JoinType.LEFT);

Predicate productName = cb.like(
    cb.lower(p.<String>get("name")), pattern, '!');
Predicate categoryName = cb.like(
    cb.lower(category.<String>get("name")), pattern, '!');

predicates.add(cb.or(productName, categoryName));
~~~

Ở đây, một Product có category null vẫn có thể khớp `productName`. Nếu dùng INNER JOIN, Product đó đã bị loại trước khi OR được tính.

### Chỉ tạo JOIN khi cần

Không nên JOIN mọi association trong mọi query chỉ vì có các ô tìm kiếm trên UI. Hãy tạo JOIN trong nhánh filter thực sự cần; JOIN thừa có thể làm SQL dài, tăng số row, ảnh hưởng performance và số lượng kết quả.

## 23. Điều kiện ON và WHERE khác nhau

Khi dùng LEFT JOIN một collection, filter ở ON khác filter ở WHERE. Giả sử Category có collection products và cần thống kê Category kể cả không có Product ACTIVE.

Có thể tạo:

~~~java
Root<Category> c = cq.from(Category.class);
Join<Category, Product> p = c.join(
    "products", JoinType.LEFT);

p.on(cb.equal(
    p.get("status"), ProductStatus.ACTIVE));
~~~

Điều kiện `p.on(...)` được áp dụng vào JOIN, giúp giữ Category ở phía trái ngay cả khi không có Product ACTIVE. Nếu viết cùng điều kiện trong WHERE, Category có p null có thể bị loại.

### ON không phải cách chung để thay WHERE

Trong tìm kiếm Product root thông thường, điều kiện status của Product nên đặt ở WHERE. Dùng ON khi cần điều chỉnh **những hàng association được nối**, đặc biệt với LEFT JOIN và tính toán điều kiện trên collection.

Không cố đưa mọi filter tùy chọn vào ON để “tối ưu” mà chưa xem semantics của kết quả.

## 24. OR trên nhiều association: nguy cơ nhân hàng

Giả sử Product có tags và reviews:

~~~text
Product#101
  tags: java, orm
  reviews: review1, review2, review3
~~~

Nếu JOIN đồng thời:

~~~java
Join<Product, Tag> t =
    p.join("tags", JoinType.LEFT);
Join<Product, Review> r =
    p.join("reviews", JoinType.LEFT);

Predicate matches = cb.or(
    cb.equal(t.get("name"), "java"),
    cb.greaterThan(r.<Integer>get("stars"), 4)
);
~~~

Provider/database có thể tạo **2 × 3 = 6 hàng** trung gian cho một Product vì fan-out. `cq.distinct(true)` có thể khử trùng entity root nhưng không giải quyết mọi vấn đề:

- Count query cần COUNT DISTINCT phù hợp.
- Pagination root entities có thể bị ảnh hưởng.
- SUM/COUNT aggregate từ JOIN có thể sai.
- Query plan có thể rất tốn kém.

Với các điều kiện kiểu “tồn tại một tag” hoặc “tồn tại review đánh giá tốt”, **EXISTS subquery** thường biểu diễn ý nghĩa trực tiếp và tránh nhân bản root rows do JOIN.

## 25. EXISTS: Predicate cho điều kiện tồn tại phần tử liên quan

Ví dụ Product có tags và muốn tìm Product có tag `"java"`.

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq = cb.createQuery(Product.class);
Root<Product> p = cq.from(Product.class);

Subquery<Long> sq = cq.subquery(Long.class);
Root<Tag> tag = sq.from(Tag.class);
Join<Tag, Product> taggedProduct =
    tag.join("products");

sq.select(cb.literal(1L));
sq.where(
    cb.equal(taggedProduct, p),
    cb.equal(tag.get("name"), "java")
);

Predicate hasJavaTag = cb.exists(sq);
Predicate tenant = cb.equal(p.get("tenantId"), tenantId);

cq.select(p).where(cb.and(tenant, hasJavaTag));
~~~

Giả sử `Tag.products` là quan hệ many-to-many mapped phù hợp với Product.tags. Code chỉ minh họa **correlated EXISTS** qua product entity. Trong model thật, có thể dùng đường dẫn từ `Product.tags` với một correlated subquery theo mapping provider hỗ trợ.

### Dùng NOT EXISTS

Nếu muốn Product không có Tag bị cấm:

~~~java
Predicate notTagged =
    cb.not(cb.exists(sq));
~~~

Điều này khác với việc INNER JOIN rồi so sánh `tag.name <> 'forbidden'`: một Product có cả tag “forbidden” và “java” vẫn có một dòng JOIN không phải forbidden, nên JOIN + notEqual có thể trả Product sai. **NOT EXISTS** mới diễn đạt “không tồn tại bất kỳ tag forbidden nào”.

### EXISTS với query count

Hàm dựng filter cho count query phải xây dựng **Subquery riêng thuộc count CriteriaQuery**. Không gắn Subquery đã tạo từ query trang vào count query khác như một node dùng chung.

## 26. Bộ lọc "có ít nhất một OrderLine" và "không có OrderLine"

Một ví dụ độc lập với Product.tags: giả sử Order và OrderLine là hai entity có quan hệ một–nhiều.

Để lọc Order có ít nhất một dòng hàng, có thể dùng:

~~~java
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);
Root<PurchaseOrder> o = cq.from(PurchaseOrder.class);

Subquery<Long> existsLine =
    cq.subquery(Long.class);
Root<OrderLine> line = existsLine.from(OrderLine.class);
existsLine.select(cb.literal(1L));
existsLine.where(cb.equal(
    line.get("order"), o));

cq.where(cb.exists(existsLine));
~~~

Để tìm Order **chưa có dòng hàng**:

~~~java
cq.where(cb.not(cb.exists(existsLine)));
~~~

Nếu cần thêm các filter khác, không gọi `cq.where(...)` nhiều lần và tưởng chúng tự kết hợp AND. Hãy đưa `cb.exists(existsLine)` hoặc `cb.not(...)` vào danh sách Predicate tổng thể.

Đây là ví dụ về **Predicate linh hoạt nhưng phải gắn với CriteriaQuery đang tạo**.

## 27. Dynamic sort cũng cần whitelist

Filter optional thường đi cùng sort optional:

~~~text
sort=name&direction=asc
sort=price&direction=desc
sort=createdAt&direction=desc
~~~

Với Criteria API, có thể tạo `Order` tương ứng:

~~~java
Path<?> sortPath = switch (sortField) {
    case NAME -> root.get("name");
    case PRICE -> root.get("price");
    case CREATED_AT -> root.get("createdAt");
};

Order order = descending
    ? cb.desc(sortPath)
    : cb.asc(sortPath);

cq.orderBy(order, cb.asc(root.get("id")));
~~~

Không dùng:

~~~java
root.get(request.getParameter("sort"))
~~~

cho input chưa được kiểm soát. Dù Criteria API không có injection từ cú pháp string JPQL theo cùng cách nối query text, nó vẫn có thể tạo lỗi runtime, cho phép lộ field không nên sort, kích hoạt JOIN nặng hoặc expose cấu trúc domain.

### Sort theo giá trị có NULL

Nếu một cột sort nullable, vị trí NULL trong ASC/DESC có thể khác giữa DBMS. Nếu UI yêu cầu “NULL luôn cuối”, phải thiết kế biểu thức CASE/ordering theo ngữ nghĩa thích hợp hoặc dùng tính năng provider-specific rõ ràng; không giả định mọi DB sắp NULL cùng thứ tự.

### Sort theo association

Sort theo `Category.name` có thể cần JOIN và xử lý Product chưa phân loại. Lúc đó phải xem INNER/LEFT JOIN, số hàng và thứ tự ổn định; không coi sort như một phần vô hại có thể thêm ở cuối mà không ảnh hưởng query plan.

## 28. Pagination: setFirstResult và setMaxResults

Sau khi tạo `TypedQuery<Product>`:

~~~java
TypedQuery<Product> query = em.createQuery(cq);
query.setFirstResult(page * size);
query.setMaxResults(size);
List<Product> pageItems = query.getResultList();
~~~

Với API công khai:

- `page >= 0`.
- `size >= 1` và nên có giới hạn tối đa.
- Tính offset bằng `long` để tránh overflow.
- Thêm ORDER BY có tie-breaker duy nhất, ví dụ `id`.
- Không lấy toàn bộ results rồi dùng `subList` trong RAM để phân trang.

**Phân trang qua nhiều request không bảo đảm một snapshot cố định** nếu dữ liệu bị thêm/xóa/chỉnh sửa giữa các lần tải. Nếu dữ liệu thay đổi nhanh và người dùng duyệt nhiều trang, có thể cân nhắc keyset pagination và chính sách consistency phù hợp.

### Trang rỗng khác tổng số 0

Nếu `page` quá lớn, danh sách trang có thể rỗng dù `countMatches(...) > 0`. Đây là kết quả hợp lệ, không phải bug; UI nên xử lý trang vượt phạm vi và tổng số trang rõ ràng.

## 29. CriteriaBuilder.construct cho DTO projection

Đối với màn hình catalog chỉ cần ID, tên và giá, trả toàn bộ entity có thể gây lazy loading hoặc serialization không cần thiết.

DTO:

~~~java
public record ProductCard(
        Long id,
        String name,
        BigDecimal price) {
}
~~~

Criteria:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<ProductCard> cq =
    cb.createQuery(ProductCard.class);

Root<Product> p = cq.from(Product.class);

cq.select(cb.construct(
    ProductCard.class,
    p.get("id"),
    p.get("name"),
    p.get("price")
));

Predicate tenant = cb.equal(
    p.get("tenantId"), tenantId);

cq.where(tenant);
cq.orderBy(cb.asc(p.get("id")));

List<ProductCard> cards =
    em.createQuery(cq).getResultList();
~~~

`cb.construct(...)` tạo đối tượng DTO từ các biểu thức SELECT. Constructor phải tương thích số lượng, thứ tự và kiểu tham số. DTO không phải managed entity; sửa một `ProductCard` không kích hoạt dirty checking cập nhật Product.

### Kết hợp với filter optional

Hàm dựng predicate có thể nhận cùng `Root<Product> p` và thêm WHERE cho CriteriaQuery DTO, như với CriteriaQuery<Product>. Tuy nhiên, hãy **tạo predicate trên Root thuộc query DTO đó**, không dùng lại Root của query entity khác.

## 30. Static metamodel giúp type safety

Mẫu dùng chuỗi:

~~~java
p.get("price")
~~~

có rủi ro lỗi khi đổi tên field và compiler không phát hiện. JPA hỗ trợ **static metamodel** (được tạo bằng annotation processing hoặc công cụ phù hợp).

Ví dụ:

~~~java
Path<BigDecimal> price =
    p.get(Product_.price);

Path<ProductStatus> status =
    p.get(Product_.status);

Predicate affordable = cb.lessThan(
    price,
    new BigDecimal("500000.00"));
~~~

`Product_` là class metamodel được **generated**, không phải file JPA tự sinh trong runtime ở mọi dự án. Muốn dùng, cần cấu hình annotation processor phù hợp với phiên bản Jakarta Persistence/provider và build tool.

### Lợi ích

- Compiler có thể phát hiện một số thay đổi tên/kiểu field.
- Tránh nhiều magic string trong query builder.
- Tăng khả năng IDE hỗ trợ completion/refactor.

### Giới hạn

Static metamodel không tự bảo đảm logic AND/OR đúng hay transaction được cô lập phù hợp. Nó cũng không thay thế kiểm thử query SQL thực sự trên database.

## 31. Spring Data JPA Specification: lớp bọc trên Predicate

Nếu dự án dùng Spring Data JPA, một mẫu thường gặp là `Specification<T>`. Đây **không phải interface tiêu chuẩn của JPA**, nhưng được xây dựng trên Criteria API.

Ví dụ:

~~~java
import org.springframework.data.jpa.domain.Specification;

public final class ProductSpecifications {

    public static Specification<Product> tenant(long tenantId) {
        return (root, query, cb) ->
            cb.equal(root.get("tenantId"), tenantId);
    }

    public static Specification<Product> status(
            ProductStatus status) {
        return (root, query, cb) ->
            status == null
                ? cb.conjunction()
                : cb.equal(root.get("status"), status);
    }

    public static Specification<Product> minPrice(
            BigDecimal min) {
        return (root, query, cb) ->
            min == null
                ? cb.conjunction()
                : cb.greaterThanOrEqualTo(
                    root.<BigDecimal>get("price"), min);
    }
}
~~~

Có thể kết hợp:

~~~java
Specification<Product> spec =
    ProductSpecifications.tenant(tenantId)
        .and(ProductSpecifications.status(status))
        .and(ProductSpecifications.minPrice(minPrice));
~~~

Với repository kế thừa `JpaSpecificationExecutor<Product>`, Spring Data JPA có thể thực thi Specification với phân trang.

### Khi nào dùng?

- Ứng dụng đã sử dụng Spring Data JPA.
- Filter có thể tổ hợp và tái sử dụng giữa nhiều service.
- Muốn đóng gói các điều kiện theo module.

**Không bắt buộc phải thêm Spring chỉ để kết hợp Predicate.** Với JPA thuần, `CriteriaBuilder` và các helper dựng Predicate đã đủ.

### Kiểm tra các Specification tạo JOIN/fetch

Một Specification thêm `root.fetch(...)` hoặc `query.distinct(true)` có thể ảnh hưởng count query mà Spring Data tự dựng. Không nên dùng Specification để âm thầm sửa cấu trúc query theo cách chỉ đúng cho một loại SELECT. Các phiên bản Spring Data có API và xử lý count query khác nhau, nên khi tìm kiếm qua to-many association cần kiểm thử cụ thể.

## 32. Những điều không nên ghép thành Predicate tùy ý

Không phải mọi input người dùng đều nên biến thành một điều kiện:

| Input | Lý do cần kiểm soát |
| --- | --- |
| Raw field name | Có thể truy cập field ngoài phạm vi và gây lỗi |
| Raw operator string | Không được chuyển trực tiếp thành cấu trúc SQL/JPQL |
| Raw join path | Có thể tạo JOIN sâu, cardinality lớn hoặc rò rỉ metadata |
| Raw SQL fragment | Phá ranh giới Criteria API và có nguy cơ injection |
| Tenant ID do client tự chọn | Không được vượt chính sách phân quyền |
| IN list cực lớn | Có thể vượt bind limit, gây DoS truy vấn |
| Keyword quá dài/nhiều term | Có thể làm query rất tốn CPU |
| Page size không giới hạn | Có thể tải quá nhiều data vào RAM |
| User-supplied timezone không validate | Có thể làm sai ranh giới ngày hoặc gây exception |

Criteria API giúp xây dựng **cây truy vấn từ các đối tượng có kiểu**, nhưng không miễn trừ kiểm soát authorization, resource usage và validation.

## 33. Query SQL có thể thay đổi khi thêm bộ lọc

Với dynamic predicates, provider có thể sinh SQL có các WHERE clauses khác nhau theo tập filter:

~~~text
Request A:
  WHERE tenant_id = ?

Request B:
  WHERE tenant_id = ?
    AND status = ?

Request C:
  WHERE tenant_id = ?
    AND status IN (?, ?)
    AND price >= ?
    AND price < ?
~~~

Điều này có ưu điểm là chỉ áp dụng những predicate cần thiết, nhưng đồng thời tạo nhiều hình dạng SQL:

- Database có thể có nhiều query plan khác nhau.
- Plan cache/prepared statement cache phụ thuộc SQL shape.
- Mỗi filter có thể làm index lựa chọn thay đổi.
- Query với `LIKE '%term%'` có thể tốn kém.
- JOIN tùy chọn có thể làm số hàng trung gian tăng.

### Một cách khác: query tĩnh với điều kiện null

Đôi khi thấy:

~~~jpql
WHERE (:status IS NULL OR p.status = :status)
AND (:minPrice IS NULL OR p.price >= :minPrice)
~~~

Ưu điểm là cố giữ cùng một cấu trúc JPQL, nhưng có nhược điểm:

- OR có thể gây khó khăn cho việc tối ưu index ở một số DBMS.
- Provider/DBMS có thể gặp vấn đề suy luận kiểu khi bind null.
- Khó diễn đạt collection rỗng, LIKE wildcard, JOIN optional.
- Có thể khó đọc khi nhiều điều kiện.

Không có một chiến lược luôn nhanh hơn; nhưng với **bộ lọc tùy chọn nhiều loại**, xây predicate động thường dễ thể hiện đúng ngữ nghĩa hơn.

## 34. Tối ưu hiệu năng với bộ lọc động

### 34.1. Chỉ JOIN khi cần

Nếu tìm theo Product.name và status, đừng JOIN tags/reviews. Một JOIN thừa có thể loại Product, nhân bản row hoặc tăng I/O.

### 34.2. Tạo index dựa trên workload thật

Ví dụ database hay chạy:

~~~sql
WHERE tenant_id = ?
  AND status = ?
  AND price >= ?
ORDER BY price ASC, id ASC
~~~

Một index minh họa có thể là:

~~~sql
CREATE INDEX idx_products_tenant_status_price_id
ON products(tenant_id, status, price, id);
~~~

Index này **không được khẳng định là tối ưu cho mọi tổ hợp filter**. Cần xem độ chọn lọc của status, phân bố giá, data volume, read/write ratio và execution plan.

### 34.3. Cân nhắc index cho createdAt

Nếu bộ lọc thường xuyên giới hạn thời gian theo tenant:

~~~sql
CREATE INDEX idx_products_tenant_created
ON products(tenant_id, created_at);
~~~

DBMS có thể dùng index theo điều kiện range và sort. Nhưng thêm quá nhiều index làm chậm INSERT/UPDATE và tốn storage.

### 34.4. LIKE ở đầu chuỗi

`LIKE 'java%'` thường có cơ hội tối ưu index hơn `LIKE '%java%'`, tùy collation/index/operator. Nếu nghiệp vụ là prefix search, không tự thêm wildcard ở đầu. Với contains search lớn, cân nhắc index/trigram/full-text theo DBMS.

### 34.5. Query count đôi khi tốn hơn page query

`SELECT COUNT(*)` trên hàng triệu Product có nhiều JOIN và filter có thể rất tốn chi phí dù trang chỉ cần 20 dòng. Nếu UI không cần total chính xác, có thể chọn **slice pagination**: lấy tối đa `size+1` item để biết còn trang tiếp hay không, không chạy COUNT mỗi request. Đây là lựa chọn API/design, không phải API mặc định của CriteriaBuilder.

## 35. Flush mode, transaction và consistency

Criteria API tạo truy vấn nhưng **không thay đổi** quy tắc persistence context và transaction của JPA.

Ví dụ:

~~~java
Product p = em.find(Product.class, 101L);
// Giả sử entity có changePrice():
p.changePrice(new BigDecimal("249000.00"));

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Long> cq = cb.createQuery(Long.class);
Root<Product> root = cq.from(Product.class);

cq.select(cb.count(root));
cq.where(cb.greaterThan(
    root.<BigDecimal>get("price"),
    new BigDecimal("200000.00")));

long count = em.createQuery(cq).getSingleResult();
~~~

Với `FlushModeType.AUTO`, provider phải bảo đảm thay đổi managed pending có thể ảnh hưởng kết quả query được phản ánh theo quy tắc JPA; nó có thể flush trước SELECT. Với `COMMIT`, tác động của pending changes lên query trước commit không được xác định theo cùng cách.

**Flush mode không phải database isolation level.** Dữ liệu transaction khác thấy được còn phụ thuộc commit, snapshot, lock và cấu hình DBMS.

### Hai query page/count không tự dùng cùng snapshot

Nếu code chạy `findPage(...)` rồi `countMatches(...)` mà transaction khác tạo hoặc xóa Product ở giữa, số lượng trang và tổng đếm có thể không hoàn toàn khớp theo isolation. Một yêu cầu snapshot nhất quán cần được thiết kế tại tầng transaction/database, không chỉ dùng chung ProductFilter.

### EntityManager không thread-safe

Service có thể được singleton trong framework, nhưng `EntityManager` thực dùng phải được cấp theo scope/transaction đúng. Không dùng chung một instance EntityManager có trạng thái mutable giữa nhiều thread.

## 36. Dùng CriteriaUpdate và CriteriaDelete có giống Predicate SELECT không?

JPA có:

~~~java
CriteriaUpdate<Product> update =
    cb.createCriteriaUpdate(Product.class);

Root<Product> p = update.from(Product.class);
update.set("status", ProductStatus.INACTIVE);
update.where(cb.and(
    cb.equal(p.get("tenantId"), tenantId),
    cb.lessThan(
        p.<Instant>get("createdAt"), cutoff)
));

int affected = em.createQuery(update).executeUpdate();
~~~

Tương tự, `CriteriaDelete<Product>` có thể xóa theo predicate.

### Nhưng bulk DML không giống sửa managed entity

- Cần transaction thích hợp.
- Bulk update/delete trực tiếp tác động database.
- Không tự đồng bộ mọi managed Product đã nạp.
- Thông thường bỏ qua callbacks và version checks per-entity kiểu dirty checking.
- Có giới hạn về JOIN và những cấu trúc query được phép trong bulk DML.
- Phải áp dụng tenant/security filter ở bulk DML giống SELECT.

Vì vậy hàm `buildPredicates(...)` dành cho SELECT **không mặc định có thể chuyển nguyên xi sang CriteriaUpdate/Delete**, nhất là khi filter tạo JOIN/collection/subquery phụ thuộc query type. Muốn dùng lại, cần thiết kế riêng ranh giới hỗ trợ và test.

## 37. Cách kiểm thử bộ lọc tùy chọn

Một bài test đúng không chỉ kiểm tra một trường hợp “status ACTIVE”. Cần kiểm tra **ngữ nghĩa của từng loại input** và các tổ hợp quan trọng.

Ví dụ dữ liệu:

| ID | Tenant | Tên | Status | Price | Stock | Category |
| --- | ---: | --- | --- | ---: | ---: | --- |
| 1 | 10 | Java Basics | ACTIVE | 150.000 | 10 | BOOK |
| 2 | 10 | Java JPA | ACTIVE | 350.000 | 0 | BOOK |
| 3 | 10 | Spring Intro | DRAFT | 200.000 | 5 | COURSE |
| 4 | 10 | Java Notes | INACTIVE | 100.000 | 2 | NULL |
| 5 | 20 | Java Advanced | ACTIVE | 180.000 | 30 | BOOK |

Các ca kiểm thử:

| Filter | Kết quả mong muốn trong tenant 10 |
| --- | --- |
| Tất cả optional null | ID 1, 2, 3, 4 |
| keyword="Java" | ID 1, 2, 4 |
| statuses={ACTIVE} | ID 1, 2 |
| minPrice=200000 | ID 2, 3 |
| maxPriceExclusive=200000 | ID 1, 4 |
| inStock=true | ID 1, 3, 4 |
| inStock=false | ID 2 |
| categoryMissing=true | ID 4 |
| categoryMissing=false | ID 1, 2, 3 |
| statuses=empty set | Không có kết quả |
| categoryIds=empty set | Không có kết quả |
| keyword="java", statuses={ACTIVE}, inStock=true | Chỉ ID 1 |
| status ACTIVE, category BOOK, price >=300000 | Chỉ ID 2 |
| Tenant 10, keyword="Advanced" | Không có Product của tenant 20 |

Trong test, tạo Category/Products thật, flush/commit và kiểm tra kết quả bằng ID trong context phù hợp. Không dùng mock EntityManager để kết luận Criteria SQL và JOIN semantics đã đúng trên DBMS.

### Test các điểm biên

- Giá đúng bằng min: **được bao gồm**.
- Giá đúng bằng maxExclusive: **bị loại**.
- CreatedAt đúng bằng fromInclusive: được bao gồm.
- CreatedAt đúng bằng toExclusive: bị loại.
- Keyword chỉ khoảng trắng: bỏ filter.
- Keyword chứa `%` hoặc `_`: được xử lý như ký tự thường theo chính sách escape.
- `Boolean.FALSE`: không được coi như null.
- Collection null khác collection rỗng.
- Hai nhánh OR phải nằm dưới AND tenant.
- Sorting nhiều Product cùng price: có tie-breaker id.
- Page vượt phạm vi: list rỗng nhưng count vẫn có thể dương.

### Test logic OR độc lập

Với:

~~~text
tenant=10
AND (name contains Java OR sku contains Java)
~~~

phải cố ý tạo một Product tenant 20 có SKU chứa Java. Nếu query vô tình viết `(tenant=10 AND nameLike) OR skuLike`, test sẽ phát hiện dữ liệu tenant 20 bị trả về.

**Đây là test bảo mật quan trọng hơn việc kiểm tra SQL có đúng số dấu hỏi hay không.**

## 38. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Chỉ có filter cuối có hiệu lực | Gọi `query.where(...)` nhiều lần và ghi đè restriction trước | Gom predicates rồi where một lần |
| Không có filter nào thì trả 0 hàng | Dùng `cb.or(empty)` thay vì bỏ lọc/AND empty | Chọn semantics empty rõ |
| Collection ID rỗng làm SQL lỗi | Tạo IN với danh sách rỗng | Xử lý `cb.disjunction()` hoặc normalize |
| Boolean false không hoạt động | Chỉ kiểm tra `if (Boolean.TRUE.equals(flag))` | Xử lý cả true, false, null |
| Tìm “50%” ra quá nhiều | Không escape wildcard LIKE | Escape %/_ và khai báo escape char |
| Query lọt Product tenant khác | Tenant predicate nằm trong một nhánh OR | Áp tenant bằng AND bên ngoài toàn bộ optional expression |
| Giá trị NULL không được trả như mong đợi | Dùng notEqual thay vì OR isNull | Hiểu SQL ba giá trị |
| Category null biến mất khi tìm theo name/sku | INNER JOIN category không cần thiết | Dùng LEFT JOIN nếu cần giữ root không có category |
| Trả Product trùng khi lọc Tag | JOIN to-many nhân root rows | `distinct(true)` hoặc EXISTS thích hợp |
| Count lớn hơn số entity | Count sau to-many JOIN mà không DISTINCT | `countDistinct(root.get("id"))` |
| Page có 20 row SQL nhưng ít Product | Fetch join collection/pagination | Page ID trước rồi fetch riêng |
| COUNT và page khác filter | Hai hàm dựng predicate không đồng bộ | Dùng chung logic builder với Roots riêng |
| Hibernate báo “invalid path” ở count query | Dùng Root/Predicate của page query cho count | Dựng lại node theo count Root |
| Giá vượt khoảng vẫn xuất hiện | Dùng `between` inclusive trong khi max phải exclusive | Dùng >= và < |
| Sort tùy ý gây lỗi | `root.get(input)` không whitelist | Ánh xạ input sang enum/field cho phép |
| Query quá chậm vì nhiều OR/LIKE | Conditions không dùng index hiệu quả | Đo SQL, plan, index và chọn search solution |
| Có `@Version` nhưng bulk update vẫn ghi đè | Bulk DML bypass per-entity version | Dùng update managed hoặc thiết kế version SQL rõ |
| Dùng LEFT JOIN nhưng predicate ở WHERE làm mất nhóm rỗng | WHERE loại giá trị phía JOIN null | Đặt điều kiện ở ON khi cần giữ left rows |
| UI hiển thị 0 trang nhưng có data | Count query thiếu điều kiện hoặc dư JOIN | Test đồng bộ page/count và isolation |
| Input null tạo `= NULL` | Dùng equal(field, null) | Dùng isNull/isNotNull |
| Kết quả query thiếu authorization | Chỉ filter search, quên điều kiện bắt buộc | Đưa tenant/ACL vào mọi query, kể cả count/bulk |

## 39. Quy trình thiết kế Predicate có thể bảo trì

Khi thêm một ô lọc mới vào ứng dụng, đừng bắt đầu bằng cách chèn ngay một dòng Criteria. Hãy theo quy trình:

1. **Định nghĩa ngữ nghĩa input:** null có nghĩa gì, rỗng có nghĩa gì, false có nghĩa gì?
2. **Xác định field persistent:** dùng tên entity/thuộc tính JPA, không dùng tên cột SQL trong Criteria.
3. **Validate ở boundary:** định dạng, độ dài keyword, range, danh sách ID, enum, timezone.
4. **Phân loại điều kiện:** bắt buộc bảo mật hay tùy chọn tìm kiếm?
5. **Xác định toán tử:** equal, IN, LIKE, range, IS NULL, EXISTS.
6. **Xác định nhóm logic:** AND của các filter; OR trong những nhóm cần tìm ở nhiều field.
7. **Xác định JOIN:** có làm loại root null hoặc nhân bản row không?
8. **Xác định kiểu query:** entity page, DTO projection, COUNT, bulk update/delete.
9. **Dựng Predicate theo Root của từng query:** tái sử dụng công thức, không tái sử dụng node.
10. **Thêm ORDER BY ổn định và giới hạn page:** không lấy sort raw từ user.
11. **Test nhóm biên và bảo mật:** đặc biệt null, collection empty, OR tenant scope.
12. **Quan sát SQL thật và query plan:** không tối ưu bằng suy đoán từ số Predicate Java.

### Một sơ đồ quyết định ngắn

~~~text
Input filter vừa nhận
        |
        v
Có phải điều kiện bắt buộc? ----Có----> Luôn thêm vào AND ngoài.
        |
       Không
        |
        v
Input có được cung cấp?
    |                |
   Không             Có
    |                |
    v                v
Bỏ filter       Validate input
                     |
                     v
              Rỗng có ý nghĩa gì?
                 |          |
             Bỏ lọc      Không match
                 |          |
                 v          v
            TRUE/skip    disjunction()
                     |
                     v
            Xây expression đúng
               |           |
          Một field     Nhiều field
               |           |
               v           v
            equal/...   or(a,b,...)
               +-----------+
                     |
                     v
               AND tất cả
                     |
                     v
          Query + count + pagination
~~~

**Mỗi bước trong sơ đồ phải phản ánh hợp đồng API, không phải lựa chọn ngẫu nhiên dựa trên việc CriteriaBuilder có sẵn method nào.**

## 40. Bài tập vận dụng

### Bài 1 — Hai bộ lọc tùy chọn

Viết CriteriaQuery tìm Product theo status và minPrice, trong đó bất kỳ input nào có thể null.

**Gợi ý:** khởi tạo `List<Predicate>`, thêm `equal` và `greaterThanOrEqualTo` khi input khác null, rồi `cb.and(...)`.

### Bài 2 — OR nằm trong AND

Tìm Product thuộc tenant 10 và có `name` **hoặc** `sku` chứa từ khóa `"java"`. Viết cây Predicate tránh lọt dữ liệu tenant 20.

**Gợi ý:** `cb.and(tenant, cb.or(nameLike, skuLike))`.

### Bài 3 — where() gọi hai lần

Tại sao:

~~~java
cq.where(cb.equal(p.get("status"), status));
cq.where(cb.ge(p.<BigDecimal>get("price"), min));
~~~

không tạo hai điều kiện AND?

**Gợi ý:** mỗi `where(...)` thay tập restrictions trước; hãy gom vào `cb.and(...)`.

### Bài 4 — Bộ lọc rỗng

API quy định `categoryIds=null` nghĩa tất cả danh mục, nhưng `categoryIds=Set.of()` nghĩa người dùng chọn tập rỗng. Predicate nên thế nào?

**Gợi ý:** null không thêm filter; empty thêm `cb.disjunction()`.

### Bài 5 — Tri-state Boolean

Filter inStock có giá trị null/true/false. Hãy mô tả ba kết quả.

**Gợi ý:** null không lọc; true `stockQuantity > 0`; false `stockQuantity <= 0`.

### Bài 6 — LIKE wildcard

User nhập `"50%"` và muốn tìm ký tự phần trăm thật. Vì sao chỉ binding parameter chưa đủ?

**Gợi ý:** giá trị parameter vẫn là LIKE pattern; escape `%` và `_` bằng escape character được khai báo.

### Bài 7 — Search price range

Filter `minPrice=100` và `maxPriceExclusive=200` có trả Product giá 200 không?

**Gợi ý:** không. Tạo >= 100 và < 200, không dùng BETWEEN inclusive.

### Bài 8 — Nullable Category

Tìm Product chưa được gán Category. Nên dùng `cb.equal(p.get("category"), null)` hay `cb.isNull(...)`?

**Gợi ý:** `cb.isNull(p.get("category"))`.

### Bài 9 — Count trên JOIN Tag

Một Product có ba tag phù hợp, JOIN trả ba row. Tại sao `cb.count(root)` có thể đếm thành 3?

**Gợi ý:** JOIN fan-out; khi đếm root Product, dùng count distinct identity hoặc EXISTS.

### Bài 10 — Hai CriteriaQuery

Vì sao không dùng `Predicate` từ `pageQuery.from(Product.class)` cho một count query mới?

**Gợi ý:** Predicate/Root là node thuộc cây query; tái sử dụng logic tạo node với Root khác.

### Bài 11 — Sort injection

User gửi `sort=category.owner.secretField`. Có nên gọi `root.get(rawSort)` không?

**Gợi ý:** không. Map field sort từ enum whitelist, không cho client chọn tùy ý đường dẫn persistence.

### Bài 12 — LEFT JOIN và WHERE

Muốn tìm Product mà tên Product **hoặc tên Category** khớp keyword, kể cả Product category null. Dùng INNER JOIN category có phù hợp?

**Gợi ý:** không. Dùng LEFT JOIN để Product category null vẫn có thể khớp tên Product; OR được đặt trong WHERE tổng.

### Bài 13 — NOT EXISTS

Product có tag Java và tag Forbidden. Truy vấn JOIN tag với điều kiện `tag.name <> 'Forbidden'` có thực sự chứng minh Product không có tag Forbidden không?

**Gợi ý:** không. Một hàng join của tag Java vẫn thỏa. Dùng NOT EXISTS trên tag bị cấm.

### Bài 14 — Optional date range

Lọc Product tạo trong ngày 2027-05-01 theo giờ Việt Nam, field `createdAt` là Instant. Tính khoảng như thế nào?

**Gợi ý:** start of day ở `Asia/Ho_Chi_Minh`, end là start of next day ở zone đó, chuyển về Instant, lọc >= start và < end.

### Bài 15 — Trang và tổng đếm

Query page có filter status ACTIVE + tenant 10, nhưng count query chỉ lọc tenant 10. UI sẽ mắc vấn đề gì?

**Gợi ý:** total/count không tương ứng items thực, số trang sai. Dùng chung logic tạo predicate.

### Bài 16 — Thanh tìm kiếm không có filter

Tất cả trường tùy chọn null. Có nên trả toàn bộ Product của mọi tenant?

**Gợi ý:** không. Điều kiện tenant/authorization luôn thuộc AND ngoài, dù không có search filter.

### Bài 17 — SQL/QueryBuilder

Ứng dụng có 10 bộ lọc tùy chọn, SQL sinh ra nhiều shape khác nhau. Cách đánh giá hiệu năng nào phù hợp?

**Gợi ý:** đo workload thực, log SQL có kiểm soát, EXPLAIN/index, giới hạn input và so sánh các tổ hợp phổ biến; không suy đoán chỉ từ số lượng Predicate.

### Bài 18 — CriteriaUpdate

Vì sao không thể mặc định áp dụng nguyên hàm filter có JOIN/fetch vào CriteriaUpdate?

**Gợi ý:** bulk DML có quy tắc và giới hạn query structure riêng; lifecycle/context/version cũng khác SELECT managed entities.

## 41. Tổng kết các công thức Predicate thường gặp

| Nhu cầu | Criteria API |
| --- | --- |
| Bằng nhau | `cb.equal(path, value)` |
| Khác nhau | `cb.notEqual(path, value)` |
| Lớn hơn | `cb.greaterThan(path, value)` hoặc `cb.gt(...)` cho số |
| Lớn hơn hoặc bằng | `cb.greaterThanOrEqualTo(path, value)` |
| Nhỏ hơn | `cb.lessThan(path, value)` |
| Khoảng đóng | `cb.between(path, low, high)` |
| Giá trị NULL | `cb.isNull(path)` |
| Giá trị không NULL | `cb.isNotNull(path)` |
| Thuộc tập | `path.in(values)` |
| LIKE | `cb.like(stringPath, pattern, escapeChar)` |
| Lowercase | `cb.lower(stringPath)` |
| Tất cả điều kiện | `cb.and(a, b, ...)` |
| Ít nhất một điều kiện | `cb.or(a, b, ...)` |
| Phủ định | `cb.not(a)` |
| Điều kiện đúng | `cb.conjunction()` |
| Điều kiện sai | `cb.disjunction()` |
| Tồn tại bản ghi con | `cb.exists(subquery)` |
| Không tồn tại bản ghi con | `cb.not(cb.exists(subquery))` |
| JOIN qua association | `root.join("association", JoinType.LEFT)` |
| Lọc điều kiện JOIN | `join.on(predicate)` |
| Root không trùng | `cq.distinct(true)` |
| Count root không trùng | `cb.countDistinct(root.get("id"))` |

Các công thức trên là **khối xây dựng**, không thay thế suy luận nghiệp vụ: cùng một API Criteria có thể cho kết quả khác hẳn nếu dấu ngoặc AND/OR, NULL semantics, JOIN cardinality hoặc biên khoảng được chọn sai.

## Kết luận

**Kết hợp Predicate theo điều kiện tìm kiếm tùy chọn** là một trong những ứng dụng thực tế nhất của JPA Criteria API. Thay vì duy trì nhiều chuỗi JPQL tương ứng mọi tổ hợp filter, ứng dụng tạo `List<Predicate>`, chỉ thêm điều kiện khi input có ý nghĩa và ghép chúng bằng `CriteriaBuilder.and(...)` hoặc các nhóm `or(...)` rõ ràng. Từ khóa có thể tìm trên nhiều field, tập category/status dùng `IN`, khoảng giá/thời gian dùng phép so sánh có biên rõ ràng, còn nullable field dùng `isNull/isNotNull`.

Điều quan trọng hơn cú pháp là **ngữ nghĩa input**: null khác empty collection, Boolean false khác không cung cấp, `AND(a, OR(b,c))` khác `OR(AND(a,b),c)`, và JOIN có thể làm mất entity không có quan hệ hoặc nhân bản rows. Khi có nhiều query cho trang và tổng đếm, hãy **tái sử dụng logic dựng Predicate nhưng tạo Root/Predicate mới cho từng CriteriaQuery**. Luôn giữ tenant/authorization trong điều kiện bắt buộc, whitelist dynamic sort, validate input, giới hạn tài nguyên và kiểm tra kết quả trên database thật.

Một bộ lọc Criteria tốt không chỉ tạo được SQL hợp lệ; nó còn **diễn đạt đúng ý định tìm kiếm, không bỏ sót hoặc lộ dữ liệu, cho kết quả nhất quán giữa trang và số đếm, và có thể mở rộng khi nghiệp vụ xuất hiện bộ lọc mới**.
