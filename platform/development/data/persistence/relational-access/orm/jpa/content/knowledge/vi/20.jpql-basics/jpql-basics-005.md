# Lọc dữ liệu với toán tử so sánh, logic và điều kiện NULL

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** JPQL cơ bản

Trong ứng dụng JPA, truy vấn thường không chỉ lấy toàn bộ entity mà cần **lọc đúng tập dữ liệu theo điều kiện nghiệp vụ**: sản phẩm có giá trong khoảng cho phép, đơn hàng chưa được giao, khách hàng có email, tài khoản đang hoạt động, hoặc bản ghi chưa được gán cho một danh mục nào. **JPQL (Jakarta Persistence Query Language)** cung cấp mệnh đề **WHERE**, các toán tử **so sánh**, **logic**, **kiểm tra NULL** và những biểu thức tiện dụng như **BETWEEN**, **IN**, **LIKE** để diễn đạt yêu cầu đó ở cấp **entity và thuộc tính Java**.

Ví dụ:

~~~java
List<Product> products = em.createQuery(
    """
    select p
    from Product p
    where p.price >= :minPrice
      and p.active = true
      and p.deletedAt is null
    order by p.price asc
    """,
    Product.class
)
.setParameter("minPrice", new BigDecimal("100000.00"))
.getResultList();
~~~

Đoạn JPQL đọc thuộc tính **p.price**, **p.active**, **p.deletedAt** của entity, không viết tên cột database như **unit_price**, **is_active** hay **deleted_at** nếu các property Java có tên khác. Provider JPA chịu trách nhiệm chuyển JPQL sang SQL phù hợp với mapping và dialect.

Điểm dễ gây lỗi nhất không phải dấu **>** hoặc **=**, mà là **NULL**: trong SQL/JPQL, so sánh với một giá trị NULL thường cho kết quả **UNKNOWN** chứ không phải **TRUE** hoặc **FALSE**. Vì thế:

~~~sql
-- Ý tưởng sai cho truy vấn kiểm tra giá trị NULL:
WHERE p.deletedAt = NULL

-- Cách đúng trong JPQL:
WHERE p.deletedAt IS NULL
~~~

Bài học đi từ cú pháp cơ bản tới cách phối hợp nhiều điều kiện, bảng chân trị ba giá trị, tham số an toàn, quan hệ tùy chọn, hiệu năng và kiểm thử. Sau khi học, bạn sẽ có thể viết các bộ lọc JPQL chính xác ngay cả khi dữ liệu thiếu giá trị hoặc người dùng nhập tiêu chí tìm kiếm tùy chọn.

## 1. JPQL lọc entity, không lọc trực tiếp bảng SQL

JPQL trông giống SQL nhưng sử dụng **entity name** và **persistent attributes**:

~~~java
select p
from Product p
where p.price > :minimum
~~~

Ở đây:

- **Product** là tên entity JPA, mặc định theo tên class nếu không chỉ định tên khác trong **@Entity(name = "...")**.
- **p** là identification variable (alias) đại diện entity Product.
- **p.price** là đường dẫn property được JPA ánh xạ.
- **:minimum** là named parameter; provider bind giá trị khi query chạy.
- **WHERE** chọn những entity thỏa biểu thức điều kiện; không thay đổi trực tiếp database.
- **SELECT p** cho kết quả entity Product; có thể chọn scalar/DTO ở những use case khác.

SQL tương ứng có thể là:

~~~sql
SELECT p.id, p.code, p.name, p.unit_price, p.is_active, p.deleted_at
FROM products p
WHERE p.unit_price > ?;
~~~

SQL chỉ nhằm minh họa: column list, alias, SQL cast và kiểu placeholder do provider quyết định.

### 1.1. Không sử dụng tên bảng/cột trong JPQL

Nếu entity được khai báo:

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Column(name = "unit_price")
    private BigDecimal price;
}
~~~

thì JPQL dùng **Product** và **p.price**, không phải **products** và **p.unit_price**:

~~~java
// Đúng:
"select p from Product p where p.price >= :minPrice"

// Sai với mapping đã cho:
"select p from products p where p.unit_price >= :minPrice"
~~~

Khi thực sự cần cú pháp theo tên bảng/cột, đó là **native SQL** (ví dụ EntityManager.createNativeQuery), không phải JPQL.

### 1.2. WHERE chỉ ảnh hưởng những hàng được chọn

Một truy vấn:

~~~java
select p from Product p where p.active = true
~~~

không sửa active, không xóa bản ghi inactive, cũng không thay đổi persistence context tự nó chỉ vì WHERE có điều kiện. Nó xác định tập entity được trả về tại thời điểm thực thi query theo trạng thái database, transaction, flush mode và provider.

## 2. Mô hình dữ liệu xuyên suốt bài học

Ta sử dụng **Product** liên kết tùy chọn với **Category**, có giá, tên, trạng thái và thời điểm ngừng hiển thị. Một phần dữ liệu có thể cố ý mang NULL để minh họa.

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

    @Column(name = "name", nullable = false, length = 100)
    private String name;

    protected Category() { }

    public Category(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên danh mục không hợp lệ");
        }
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
~~~

### 2.2. Entity Product

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "code", nullable = false, unique = true, length = 40)
    private String code;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    @Column(name = "unit_price", precision = 19, scale = 2)
    private BigDecimal price;

    @Column(name = "stock_quantity")
    private Integer stockQuantity;

    @Column(name = "is_active", nullable = false)
    private boolean active;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() { }

    public Product(
            String code,
            String name,
            BigDecimal price,
            Integer stockQuantity,
            boolean active,
            Category category) {
        this.code = Objects.requireNonNull(code);
        this.name = Objects.requireNonNull(name);
        this.price = price;
        this.stockQuantity = stockQuantity;
        this.active = active;
        this.category = category;
    }

    public Long getId() { return id; }
    public String getCode() { return code; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public Integer getStockQuantity() { return stockQuantity; }
    public boolean isActive() { return active; }
    public Instant getDeletedAt() { return deletedAt; }
    public Category getCategory() { return category; }

    public void markDeleted(Instant when) {
        this.deletedAt = Objects.requireNonNull(when);
    }
}
~~~

Ở đây **price**, **stockQuantity**, **category** và **deletedAt** có thể NULL; **active** là primitive boolean nên không mang NULL trong object Java. Đây là lựa chọn cho ví dụ, không phải quy tắc chung mọi Product.

### 2.3. SQL schema minh họa

~~~sql
CREATE TABLE categories (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    unit_price NUMERIC(19, 2),
    stock_quantity INTEGER,
    is_active BOOLEAN NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    category_id BIGINT REFERENCES categories(id)
);
~~~

Cú pháp trên là ví dụ PostgreSQL; các kiểu dữ liệu và cách sinh ID khác nhau theo RDBMS. JPQL tương đối độc lập với những khác biệt SQL đó.

### 2.4. Dữ liệu giả định để dự đoán kết quả

| Mã | Tên | Giá (VND) | Số lượng | Active | deletedAt | Danh mục |
|---|---|---:|---:|---|---|---|
| P01 | Laptop Basic | 12000000 | 4 | true | NULL | Electronics |
| P02 | Mouse Wireless | 350000 | 20 | true | NULL | Electronics |
| P03 | Chair Office | 950000 | 0 | true | NULL | Furniture |
| P04 | Desk Wood | 2500000 | NULL | false | NULL | Furniture |
| P05 | Mystery Box | NULL | NULL | true | NULL | NULL |
| P06 | Keyboard Old | 700000 | 3 | true | Có timestamp | Electronics |
| P07 | Cable USB | 100000 | 15 | true | NULL | NULL |
| P08 | Monitor | 3500000 | 2 | false | NULL | Electronics |

Bảng này chỉ là dataset giải thích biểu thức, không phải dữ liệu đã được ghi tự động vào DB. Mọi ví dụ sau giả định các giá trị tương ứng đã tồn tại.

## 3. Các toán tử so sánh thông dụng

JPQL hỗ trợ toán tử so sánh áp dụng cho các biểu thức có kiểu thích hợp:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| **=** | Bằng | p.code = :code |
| **<>** | Khác | p.code <> :code |
| **>** | Lớn hơn | p.price > :price |
| **>=** | Lớn hơn hoặc bằng | p.price >= :minPrice |
| **<** | Nhỏ hơn | p.stockQuantity < :limit |
| **<=** | Nhỏ hơn hoặc bằng | p.price <= :maxPrice |

**<>** là toán tử khác chuẩn của JPQL. Không dùng toán tử Java **!=** hoặc **==** trong các câu JPQL portable dù một số provider có thể hỗ trợ cú pháp mở rộng.

### 3.1. Lọc một giá trị chính xác

~~~java
Product found = em.createQuery(
    """
    select p
    from Product p
    where p.code = :code
    """,
    Product.class
)
.setParameter("code", "P02")
.getSingleResult();
~~~

Nếu không có bản ghi phù hợp, **getSingleResult()** có thể ném **NoResultException**; nếu kết quả có nhiều hàng, có thể ném **NonUniqueResultException**. Nếu điều kiện code unique ở database, tối đa một hàng, nhưng vẫn cần xử lý trường hợp không tồn tại.

Một lựa chọn khi có thể không tìm thấy:

~~~java
List<Product> found = em.createQuery(
    "select p from Product p where p.code = :code",
    Product.class
)
.setParameter("code", "P02")
.setMaxResults(1)
.getResultList();
~~~

### 3.2. Lọc theo ngưỡng lớn hơn/nhỏ hơn

~~~java
List<Product> expensive = em.createQuery(
    """
    select p
    from Product p
    where p.price > :threshold
    """,
    Product.class
)
.setParameter("threshold", new BigDecimal("1000000.00"))
.getResultList();
~~~

Với dataset, các sản phẩm có giá **lớn hơn 1.000.000** là P01, P04, P08, kể cả khi inactive vì truy vấn chưa lọc active. P05 có price NULL và **không khớp**, không phải vì price được coi là zero mà vì kết quả so sánh NULL là UNKNOWN.

### 3.3. Phân biệt > và >= ở ranh giới

~~~java
// Lấy sản phẩm giá đúng 350000 cũng được tính:
"select p from Product p where p.price >= :minPrice"
~~~

Nếu minPrice = 350000, P02 được giữ lại. Với **p.price > :minPrice**, P02 bị loại. Ranh giới inclusive/exclusive rất quan trọng đối với giá, ngày đến hạn, phân trang theo cursor hoặc chính sách “ít nhất”.

### 3.4. So sánh các loại dữ liệu khác nhau

- **BigDecimal/BigInteger và numeric fields:** dùng parameter cùng loại phù hợp, không so sánh giá tiền bằng chuỗi.
- **Integer/Long:** các phép so sánh số phải tương thích type JPA/provider.
- **String:** phép bằng thường phụ thuộc cách so sánh chuỗi của database/collation, đặc biệt chữ hoa, dấu tiếng Việt và Unicode.
- **Instant/LocalDate/LocalDateTime:** so sánh thời gian có ý nghĩa theo kiểu cột, precision và timezone của mapping.
- **Enum:** so sánh với enum value tương ứng, không mặc định gắn tên chuỗi ngay trong query nếu có thể bind enum typed.
- **Entity-valued association:** có thể so sánh association bằng entity reference phù hợp, hoặc so sánh ID qua đường dẫn.

Không nên dùng mọi toán tử với mọi kiểu. Ví dụ so sánh lớn hơn với object entity không phải bài toán sắp thứ tự portable; hãy so sánh thuộc tính scalar có nghĩa.

### 3.5. Parameter binding thay vì ghép chuỗi

Không viết:

~~~java
String jpql =
    "select p from Product p where p.code = '" + userInput + "'";
~~~

Hãy dùng:

~~~java
TypedQuery<Product> query = em.createQuery(
    "select p from Product p where p.code = :code",
    Product.class
);
query.setParameter("code", userInput);
~~~

Bind parameters giúp tách cấu trúc query khỏi dữ liệu đầu vào, giảm rủi ro injection và lỗi quote/escape; cũng cho phép provider xử lý type phù hợp.

**Parameter chỉ thay dữ liệu, không thay tên entity, column, alias hoặc một đoạn JPQL tùy ý.** Muốn dynamic sorting hoặc dynamic predicates, dùng whitelist thuộc tính/cấu trúc query được kiểm soát.

## 4. Toán tử logic AND, OR, NOT

Một biểu thức WHERE có thể kết hợp nhiều điều kiện:

~~~java
select p
from Product p
where p.active = true
  and p.price >= :minPrice
  and p.deletedAt is null
~~~

Ở đây sản phẩm phải thỏa **đồng thời**:
1. active = true;
2. price >= minPrice;
3. deletedAt IS NULL.

### 4.1. AND: mọi điều kiện phải đúng

~~~java
List<Product> available = em.createQuery(
    """
    select p
    from Product p
    where p.active = true
      and p.stockQuantity > 0
      and p.deletedAt is null
    """,
    Product.class
).getResultList();
~~~

Trong dataset, P01 và P02 và P07 được chọn. P03 có stockQuantity = 0; P05 có stockQuantity NULL; P06 đã có deletedAt; P04/P08 không active.

### 4.2. OR: ít nhất một nhánh đúng

~~~java
List<Product> selected = em.createQuery(
    """
    select p
    from Product p
    where p.stockQuantity = 0
       or p.price < :budget
    """,
    Product.class
)
.setParameter("budget", new BigDecimal("200000.00"))
.getResultList();
~~~

P03 có stockQuantity = 0, P07 có price = 100000 nên được chọn. Những hàng có cả hai vế UNKNOWN có thể không được chọn; sẽ giải thích bằng logic ba giá trị.

### 4.3. NOT: phủ định biểu thức

~~~java
select p
from Product p
where not (p.active = true)
~~~

Với field active không nullable, có thể hiểu tương đương **p.active = false**, chọn P04 và P08. Tuy nhiên với biểu thức có NULL, **NOT UNKNOWN vẫn là UNKNOWN**, không thành TRUE.

Ví dụ:

~~~java
select p
from Product p
where not (p.price > :threshold)
~~~

không chọn P05 có price NULL, vì **NOT (NULL > threshold)** là UNKNOWN. Nếu muốn xem cả NULL như “không có giá lớn hơn ngưỡng”, cần viết rõ:

~~~java
where p.price <= :threshold or p.price is null
~~~

### 4.4. Độ ưu tiên toán tử

Trong điều kiện JPQL, **NOT** có mức ưu tiên logic cao hơn **AND**, và **AND** cao hơn **OR**. Vì thế:

~~~java
where p.active = true
  or p.stockQuantity = 0
  and p.deletedAt is null
~~~

được hiểu theo nhóm logic:

~~~java
where p.active = true
   or (p.stockQuantity = 0 and p.deletedAt is null)
~~~

Nếu nghiệp vụ thực sự yêu cầu **active hoặc stock bằng 0**, nhưng luôn phải chưa bị xóa, cần đặt ngoặc:

~~~java
where (p.active = true or p.stockQuantity = 0)
  and p.deletedAt is null
~~~

Hai câu truy vấn có thể trả kết quả rất khác nhau. Hãy **đặt ngoặc chủ động** khi có cả AND và OR, ngay cả khi đã biết precedence; nó giúp người bảo trì hiểu đúng yêu cầu.

### 4.5. Một ví dụ nghiệp vụ với nhiều điều kiện

Yêu cầu: “Tìm sản phẩm chưa xóa, đang active, đồng thời **hoặc** có tồn kho **hoặc** có giá dưới 500.000”.

~~~java
List<Product> results = em.createQuery(
    """
    select p
    from Product p
    where p.deletedAt is null
      and p.active = true
      and (
          p.stockQuantity > 0
          or p.price < :cheapPrice
      )
    """,
    Product.class
)
.setParameter("cheapPrice", new BigDecimal("500000.00"))
.getResultList();
~~~

Trong dataset, P01, P02, P07 được giữ vì có stock > 0; P03 không có stock > 0 và giá 950000; P05 có stock NULL và price NULL nên hai vế OR đều UNKNOWN, không được chọn.

## 5. Logic ba giá trị: TRUE, FALSE, UNKNOWN

Đây là trọng tâm khi lọc dữ liệu có NULL. Trong SQL và JPQL, biểu thức điều kiện có thể ở một trong ba trạng thái:

- **TRUE**: điều kiện được xác nhận đúng.
- **FALSE**: điều kiện được xác nhận sai.
- **UNKNOWN**: không đủ thông tin để kết luận đúng/sai, thường do so sánh với NULL.

Khi áp dụng WHERE, **chỉ những hàng có predicate đánh giá TRUE mới được trả về**. Hàng có FALSE hoặc UNKNOWN đều không thỏa bộ lọc.

### 5.1. Vì sao NULL không phải số 0 hoặc chuỗi rỗng?

**NULL** biểu diễn sự vắng mặt của một giá trị trong mô hình quan hệ. Nó không tự được xem là:
- Giá trị số 0;
- Chuỗi rỗng;
- Ngày giờ mặc định;
- Boolean false;
- Một entity “có ID bằng 0”.

Nếu Product.price là NULL, điều kiện **p.price > 100000** không trả false theo nghĩa toán học thông thường; kết quả là UNKNOWN.

### 5.2. So sánh trực tiếp với NULL

| Biểu thức | Kết quả nếu price là NULL |
|---|---|
| price = 100000 | UNKNOWN |
| price <> 100000 | UNKNOWN |
| price > 100000 | UNKNOWN |
| price >= 100000 | UNKNOWN |
| price < 100000 | UNKNOWN |
| price <= 100000 | UNKNOWN |
| price = NULL | UNKNOWN; không dùng để kiểm tra NULL |
| price <> NULL | UNKNOWN; không dùng để tìm NOT NULL |
| price IS NULL | TRUE |
| price IS NOT NULL | FALSE |

Đây là lý do **= NULL** và **<> NULL** đều không phải cách kiểm tra giá trị NULL trong JPQL.

### 5.3. Bảng chân trị NOT

| P | NOT P |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

### 5.4. Bảng chân trị AND

| P | Q | P AND Q |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE |
| UNKNOWN | TRUE | UNKNOWN |
| UNKNOWN | FALSE | FALSE |
| UNKNOWN | UNKNOWN | UNKNOWN |

**FALSE AND UNKNOWN = FALSE** vì chỉ cần một vế sai là cả điều kiện AND không thể đúng.

### 5.5. Bảng chân trị OR

| P | Q | P OR Q |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | TRUE | TRUE |
| UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

**TRUE OR UNKNOWN = TRUE** vì có một vế chắc chắn đúng.

### 5.6. Ví dụ giải thích kết quả không trực giác

Giả sử P05 có **price = NULL**, **stockQuantity = NULL**, **active = true**.

~~~java
where p.price >= :minimum or p.active = true
~~~

Đánh giá với P05:

~~~text
NULL >= 100000  → UNKNOWN
active = true   → TRUE
UNKNOWN OR TRUE → TRUE
~~~

P05 được trả về.

Nhưng:

~~~java
where p.price >= :minimum and p.active = true
~~~

trở thành:

~~~text
UNKNOWN AND TRUE → UNKNOWN
~~~

P05 không được trả về.

Tương tự:

~~~java
where not (p.price >= :minimum)
~~~

trở thành **NOT UNKNOWN = UNKNOWN**, nên P05 vẫn không được chọn.

**Kết luận trung tâm:** các phép so sánh trên dữ liệu có NULL không thể được suy luận hoàn toàn bằng logic boolean hai giá trị của Java.

## 6. IS NULL và IS NOT NULL: kiểm tra dữ liệu thiếu giá trị

Để tìm row có giá trị NULL, dùng **IS NULL**:

~~~java
List<Product> productsWithoutPrice = em.createQuery(
    """
    select p
    from Product p
    where p.price is null
    """,
    Product.class
).getResultList();
~~~

Với dataset, truy vấn này trả **P05**, vì **price** của sản phẩm ấy là NULL.

Để tìm những row có giá đã biết:

~~~java
select p
from Product p
where p.price is not null
~~~

Truy vấn trả tất cả Product trừ P05, không phân biệt active/deletedAt nếu không có điều kiện bổ sung.

### 6.1. Sai: dùng = null hoặc <> null

~~~java
// Sai:
where p.category = null

// Sai:
where p.deletedAt <> null

// Đúng:
where p.category is null

// Đúng:
where p.deletedAt is not null
~~~

**IS NULL** là một predicate đặc biệt dùng để kiểm tra trạng thái vắng mặt. **=** và **<>** là phép so sánh giá trị; khi có NULL, chúng không trả TRUE như nhiều người mong đợi.

JPQL keywords không phân biệt chữ hoa/chữ thường, nhưng nên sử dụng kiểu chữ nhất quán trong dự án.

### 6.2. Kiểm tra một association tùy chọn

Vì Product.category là association @ManyToOne có thể NULL:

~~~java
List<Product> uncategorized = em.createQuery(
    """
    select p
    from Product p
    where p.category is null
    """,
    Product.class
).getResultList();
~~~

Truy vấn này chọn **P05** và **P07**.

Khi cần kiểm tra **có category**:

~~~java
where p.category is not null
~~~

Điều kiện có thể được provider dịch thành kiểm tra FK **category_id IS NOT NULL** hoặc biểu thức SQL tương đương. Không tự suy rằng query nhất thiết cần JOIN categories chỉ để kiểm tra association có NULL hay không.

### 6.3. Kiểm tra soft delete

Ví dụ Product có:

~~~java
@Column(name = "deleted_at")
private Instant deletedAt;
~~~

Quy tắc “chưa bị xóa mềm”:

~~~java
where p.deletedAt is null
~~~

Quy tắc “đã được đánh dấu xóa”:

~~~java
where p.deletedAt is not null
~~~

Nếu muốn danh sách sản phẩm đang bán:

~~~java
where p.active = true
  and p.deletedAt is null
~~~

**Hai thuộc tính active và deletedAt có nghĩa khác nhau.** active=false có thể là tạm ngừng bán nhưng chưa bị xóa; deletedAt không null là đã bị xóa mềm theo mô hình này.

Đừng quên điều kiện soft delete trong truy vấn nghiệp vụ chỉ vì một ví dụ WHERE ngắn gọn. Với hệ thống đa tenant, điều kiện tenant cũng cần được áp dụng nhất quán hoặc bằng cơ chế kiểm soát truy cập phù hợp.

### 6.4. NULL của enum/boolean

Nếu có enum:

~~~java
public enum ReviewStatus {
    PENDING, APPROVED, REJECTED
}
~~~

và field:

~~~java
@Enumerated(EnumType.STRING)
private ReviewStatus reviewStatus;
~~~

thì có thể lọc:

~~~java
where p.reviewStatus is null
~~~

nếu field nullable. Còn nếu field boolean primitive:

~~~java
private boolean active;
~~~

thì **active** trong object Java không có null, và schema khai báo NOT NULL. Nếu muốn ba trạng thái **true/false/chưa xác định**, sử dụng **Boolean** wrapper cùng mapping nullable và xác định rõ semantics nghiệp vụ; lúc đó **where e.flag = false** sẽ không trả các row flag NULL.

### 6.5. Cột NULL và chuỗi rỗng

Điều kiện:

~~~java
where p.name is null
~~~

khác:

~~~java
where p.name = ''
~~~

Ở nhiều RDBMS, chuỗi rỗng là một giá trị cụ thể; ở một số sản phẩm như Oracle, string rỗng có những quy tắc NULL đặc thù. Không viết một query JPQL kỳ vọng mọi database phân biệt NULL/empty string giống nhau trong mọi cấu hình.

Trong mô hình mẫu, name NOT NULL, nhưng ứng dụng vẫn có thể cần xử lý **name = ''** nếu dữ liệu hợp lệ ở mức DB mà domain không cho phép. Nên có validation/constraint phù hợp thay vì dựa vào bộ lọc để che dữ liệu không hợp lệ.

## 7. BETWEEN: lọc giá trị nằm trong khoảng

**BETWEEN** diễn đạt điều kiện khoảng **bao gồm cả hai đầu mút**.

~~~java
List<Product> midRange = em.createQuery(
    """
    select p
    from Product p
    where p.price between :minimum and :maximum
    """,
    Product.class
)
.setParameter("minimum", new BigDecimal("300000.00"))
.setParameter("maximum", new BigDecimal("1000000.00"))
.getResultList();
~~~

Trong dataset: P02 (350000), P03 (950000) và P06 (700000) khớp; P06 vẫn xuất hiện vì query chưa lọc deletedAt.

### 7.1. BETWEEN tương đương hai phép so sánh bao gồm ranh giới

Về ý nghĩa:

~~~java
p.price between :min and :max
~~~

tương đương:

~~~java
p.price >= :min and p.price <= :max
~~~

với các toán hạng thông thường có kiểu tương thích. Nếu price là NULL, kết quả là UNKNOWN và row không được chọn.

### 7.2. NOT BETWEEN

~~~java
where p.price not between :min and :max
~~~

tương ứng phủ định điều kiện nằm trong khoảng. Tuy nhiên **price NULL không tự được xem là nằm ngoài khoảng**: NOT UNKNOWN vẫn UNKNOWN.

Nếu nghiệp vụ nói “ngoài khoảng hoặc chưa có giá”, hãy viết:

~~~java
where p.price not between :min and :max
   or p.price is null
~~~

### 7.3. Khoảng thời gian và ranh giới ngày

Giả sử một entity **Order** có:

~~~java
@Column(name = "created_at", nullable = false)
private Instant createdAt;
~~~

Muốn lấy orders từ thời điểm start **bao gồm** đến end **không bao gồm**:

~~~java
List<Order> orders = em.createQuery(
    """
    select o
    from Order o
    where o.createdAt >= :start
      and o.createdAt < :end
    """,
    Order.class
)
.setParameter("start", startInstant)
.setParameter("end", endInstant)
.getResultList();
~~~

Ví dụ này giả định Order là một entity được mapping với property createdAt. Khoảng **[start, end)** thường tiện khi chia theo ngày/tháng liên tiếp, vì không cần suy đoán “thời điểm cuối ngày” với millisecond/microsecond/nanosecond.

~~~text
Ngày 01: [00:00 ngày 01, 00:00 ngày 02)
Ngày 02: [00:00 ngày 02, 00:00 ngày 03)
~~~

Nếu dùng **BETWEEN**, end là inclusive, nên phải định nghĩa end đúng theo quy tắc nghiệp vụ. Chú ý timezone, precision của DB, và sự khác nhau giữa **Instant**, **LocalDateTime**, **LocalDate**.

### 7.4. Bảo đảm minimum không lớn hơn maximum

Nếu người dùng gửi minPrice > maxPrice, query BETWEEN có thể không trả row nào thay vì báo validation error. Trong API, hãy xác thực:

~~~java
if (minPrice != null && maxPrice != null
        && minPrice.compareTo(maxPrice) > 0) {
    throw new IllegalArgumentException(
        "minPrice không được lớn hơn maxPrice");
}
~~~

Việc xử lý input invalid là quyết định của application layer, không phải nhiệm vụ tự động của JPQL.

## 8. IN và NOT IN: lọc nhiều giá trị

**IN** cho phép điều kiện giá trị thuộc một tập.

~~~java
List<Product> products = em.createQuery(
    """
    select p
    from Product p
    where p.code in :codes
    """,
    Product.class
)
.setParameter("codes", List.of("P01", "P03", "P07"))
.getResultList();
~~~

Trong dataset, query chọn P01, P03 và P07. Trong ứng dụng thực, danh sách có thể được lấy từ request đã validate.

### 8.1. IN với tập cố định

~~~java
select p
from Product p
where p.code in ('P01', 'P02', 'P03')
~~~

Đây là cú pháp JPQL có literal strings. Nhưng với giá trị do người dùng nhập, nên bind parameter thay vì nối literal.

### 8.2. IN với parameter collection

~~~java
TypedQuery<Product> query = em.createQuery(
    "select p from Product p where p.code in :codes",
    Product.class
);

query.setParameter(
    "codes",
    List.of("P02", "P08")
);
~~~

Cách bind collection là cách thông dụng với Hibernate và những JPA provider hiện đại hỗ trợ dạng collection-valued parameter ở IN. Tính portable chính xác và cách provider mở rộng placeholder phụ thuộc phiên bản/spec/provider; hãy kiểm tra cấu hình mục tiêu, đặc biệt với collection rỗng và kích thước lớn.

### 8.3. Tập rỗng: không tự sinh IN ()

Một input:

~~~java
List<String> codes = List.of();
~~~

không nên mặc định bind vào **IN :codes** rồi mong mọi database/provider xử lý giống nhau. SQL **IN ()** có thể không hợp lệ trong nhiều dialect.

Chọn semantics nghiệp vụ rõ:
- Danh sách lọc rỗng có nghĩa **không chọn gì**: return List.of() mà không query.
- Danh sách rỗng có nghĩa **không áp bộ lọc**: bỏ predicate IN.
- Danh sách rỗng là request invalid: báo validation error.

Ví dụ khi rỗng có nghĩa không có kết quả:

~~~java
public List<Product> findByCodes(
        EntityManager em, List<String> codes) {
    if (codes == null || codes.isEmpty()) {
        return List.of();
    }

    return em.createQuery(
        "select p from Product p where p.code in :codes",
        Product.class
    )
    .setParameter("codes", codes)
    .getResultList();
}
~~~

### 8.4. NOT IN và bẫy NULL

~~~java
where p.code not in :excludedCodes
~~~

Nếu danh sách **excludedCodes chứa NULL**, biểu thức có thể đánh giá UNKNOWN ngay cả với những giá trị không nằm trong danh sách. Đặc biệt trong SQL, **NOT IN (1, NULL)** thường không khớp các giá trị khác 1 vì **NOT (value = 1 OR value = NULL)** mang UNKNOWN.

Ví dụ logic:

~~~text
code = 'P02'
'P02' IN ('P01', NULL)
  = FALSE OR UNKNOWN
  = UNKNOWN

'P02' NOT IN ('P01', NULL)
  = NOT UNKNOWN
  = UNKNOWN
→ WHERE không chọn P02.
~~~

**Đừng cho phép NULL vô ý xuất hiện trong collection dùng cho NOT IN.** Validate/filter những giá trị null theo nghiệp vụ.

Nếu muốn loại trừ các hàng theo kết quả query phức tạp, có thể cân nhắc **NOT EXISTS** với correlation rõ ràng, đặc biệt khi subquery có khả năng trả NULL. Không khẳng định NOT EXISTS và NOT IN luôn tương đương khi có NULL.

### 8.5. Số lượng phần tử IN rất lớn

Danh sách hàng chục nghìn IDs có thể gây SQL rất dài, vượt giới hạn số bind parameters của DB/driver hoặc có plan không tốt.

Với lượng dữ liệu lớn, có thể:
- Chia input thành các phần phù hợp và hợp nhất kết quả có chủ đích;
- Dùng temporary/staging table, table-valued parameter hoặc native SQL theo DB;
- Dùng subquery/join thay vì chuyển toàn bộ IDs sang Java;
- Xem execution plan và giới hạn của dialect.

Đây là bài toán hiệu năng của query/filter, không giải quyết chỉ bằng sửa cú pháp IN.

## 9. LIKE: lọc chuỗi theo mẫu

**LIKE** dùng để so khớp mẫu chuỗi. Hai ký tự đặc biệt trong mẫu phổ biến là:

- **%**: đại diện cho **không hoặc nhiều** ký tự.
- **_**: đại diện cho **một** ký tự.

Ví dụ:

~~~java
List<Product> laptops = em.createQuery(
    """
    select p
    from Product p
    where p.name like :pattern
    """,
    Product.class
)
.setParameter("pattern", "Laptop%")
.getResultList();
~~~

Với dataset, kết quả là P01.

### 9.1. Các mẫu LIKE cơ bản

| Pattern | Ý nghĩa |
|---|---|
| 'Laptop%' | Bắt đầu bằng Laptop |
| '%Wireless%' | Có chứa Wireless |
| '%Office' | Kết thúc bằng Office |
| 'P0_' | Ba ký tự: P, 0 và một ký tự bất kỳ |
| '%' | Khớp chuỗi không NULL, kể cả chuỗi rỗng theo semantics DB |

Chú ý **LIKE '%'** không phải phép tìm cả các hàng có property NULL. NULL LIKE '%' là UNKNOWN, nên row NULL vẫn không được chọn.

### 9.2. Tham số LIKE phải chứa wildcard nếu cần

Nếu muốn tìm chứa một cụm từ:

~~~java
String keyword = "Wireless";

query.setParameter("pattern", "%" + keyword + "%");
~~~

Không nên nhầm **LIKE :keyword** với việc provider tự thêm %; nó không tự làm vậy. Nếu keyword = "Wireless" mà không có %, query thường chỉ khớp chuỗi đúng bằng pattern "Wireless" theo semantics LIKE.

### 9.3. Không phân biệt hoa/thường: cân nhắc LOWER

~~~java
List<Product> matched = em.createQuery(
    """
    select p
    from Product p
    where lower(p.name) like :pattern
    """,
    Product.class
)
.setParameter("pattern", "%wireless%")
.getResultList();
~~~

Đặt tên input đã chuyển thành lowercase:

~~~java
String normalized =
    keyword.toLowerCase(Locale.ROOT);
String pattern = "%" + normalized + "%";
~~~

Đây là một cách thường gặp để tìm không phân biệt hoa/thường theo case conversion, nhưng **kết quả thực tế còn phụ thuộc Unicode, locale, collation và database**. Tiếng Việt có dấu có thể không được xử lý như người dùng mong muốn nếu chỉ LOWER; cần thiết kế search/collation/full-text phù hợp.

Ngoài ra, dùng **lower(p.name)** có thể làm database khó tận dụng index thông thường trên name; function-based index hoặc cơ chế search riêng có thể cần thiết.

### 9.4. Escape % và _ trong input người dùng

Nếu người dùng nhập chuỗi chứa **%** hoặc **_**, nối thẳng vào pattern sẽ làm ký tự đó mang nghĩa wildcard, không còn là ký tự literal.

Ví dụ người dùng tìm ký tự **%** trong tên sản phẩm. Muốn LIKE coi % là ký tự thường, cần dùng **ESCAPE** trong JPQL.

~~~java
TypedQuery<Product> query = em.createQuery(
    """
    select p
    from Product p
    where p.name like :pattern escape '!'
    """,
    Product.class
);
~~~

Hàm tạo phần mẫu literal:

~~~java
static String escapeLike(String text) {
    return text
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
~~~

Bind:

~~~java
String pattern = "%" + escapeLike(userInput) + "%";
query.setParameter("pattern", pattern);
~~~

Ở đây **!** được chọn làm escape character:
- **!%** có nghĩa ký tự % literal;
- **!_** có nghĩa ký tự _ literal;
- **!!** có nghĩa ký tự ! literal.

Việc escape wildcard **khác** với chống SQL injection. **Named parameter** giúp bind dữ liệu thay vì ghép query; **escapeLike** giúp bảo đảm ý nghĩa tìm kiếm literal của ký tự % và _ trong mẫu. Hai việc giải quyết hai vấn đề khác nhau.

### 9.5. NOT LIKE với NULL

~~~java
where p.name not like :pattern
~~~

không tự chọn các hàng có **name NULL**. Nếu trường name nullable và muốn “không khớp mẫu hoặc chưa có tên”, phải thêm:

~~~java
where p.name not like :pattern
   or p.name is null
~~~

Trong entity mẫu, name NOT NULL nên trường hợp NULL sẽ bị DB constraint ngăn ở data layer nếu schema nhất quán.

### 9.6. LIKE không thay thế full-text search

Pattern bắt đầu bằng wildcard:

~~~java
where lower(p.name) like '%keyword%'
~~~

có thể cần scan nhiều rows, nhất là bảng lớn. Với search ngôn ngữ tự nhiên, tiếng Việt, nhiều từ khóa, typo tolerance hay ranking, có thể dùng full-text index hoặc search engine riêng. JPQL LIKE phù hợp nhất cho bộ lọc chuỗi đơn giản mà người dùng hiểu semantics.

## 10. Toán tử logic và tập NULL với IS EMPTY, MEMBER OF

Ngoài **IS NULL**, JPA còn có các predicate liên quan collection-valued associations như **IS EMPTY** và **MEMBER OF**. Chúng khác với việc so sánh một property nullable.

Ví dụ entity Category có collection:

~~~java
@OneToMany(mappedBy = "category")
private List<Product> products = new ArrayList<>();
~~~

Khi đó:

~~~java
select c
from Category c
where c.products is empty
~~~

tìm những Category không có Product liên kết theo mapping.

Đối chiếu:

~~~java
select p
from Product p
where p.category is null
~~~

tìm những Product chưa có Category. Hai query trả **hai loại entity** và hỏi những câu hỏi khác nhau:
- Category nào **không có phần tử liên kết**?
- Product nào **không có parent reference**?

Cũng có thể dùng **IS NOT EMPTY** và **MEMBER OF** khi mapping collection phù hợp:

~~~java
select c
from Category c
where :product member of c.products
~~~

Đừng viết **c.products is null** để kiểm tra “collection rỗng” trong JPQL. Collection association rỗng không giống một scalar NULL; dùng **IS EMPTY**.

### 10.1. Cẩn thận với NULL khi tham số entity

Nếu bind một object entity vào **:product**, nó cần có loại/identity phù hợp. Với một tham số null muốn tìm Category chứa “NULL product”, đó không phải semantics tự nhiên của MEMBER OF; hãy xử lý null ở tầng service hoặc xác định truy vấn khác.

## 11. Tham số NULL: vì sao setParameter(null) không tự thành IS NULL?

Một hiểu nhầm phổ biến:

~~~java
TypedQuery<Product> query = em.createQuery(
    """
    select p
    from Product p
    where p.category = :category
    """,
    Product.class
);

query.setParameter("category", null);
~~~

Khi **:category** mang NULL, phép so sánh bình thường **p.category = NULL** không biến thành **p.category IS NULL** một cách portable. Kết quả so sánh với NULL là UNKNOWN, nên thường không trả những Product chưa có Category.

### 11.1. Hai mục đích nghiệp vụ khác nhau

Giả sử tham số categoryId được phép null. Ta phải quyết định **null có ý nghĩa gì**:

**Mục đích A: null nghĩa là “chỉ tìm sản phẩm chưa có danh mục”.**

~~~java
String jpql = categoryId == null
    ? "select p from Product p where p.category is null"
    : "select p from Product p where p.category.id = :categoryId";
~~~

Khi categoryId khác null, bind ID; khi null, dùng predicate **IS NULL**.

**Mục đích B: null nghĩa là “không lọc theo danh mục”.**

~~~java
String jpql = """
    select p
    from Product p
    where (:categoryId is null or p.category.id = :categoryId)
    """;
~~~

Trong case categoryId null, nhánh **:categoryId IS NULL** là TRUE và query không hạn chế theo category. Tuy nhiên có nuance về **implicit joins** và cách provider dịch **p.category.id**, sẽ phân tích ở phần 12; để bảo toàn các Product không có category theo cách rõ ràng, có thể tránh path navigation phức tạp bằng dynamic predicate hoặc explicit LEFT JOIN khi phù hợp.

**Mục đích C: null là input không hợp lệ.**

~~~java
Objects.requireNonNull(categoryId, "categoryId");
~~~

Khi yêu cầu tìm theo danh mục bắt buộc, từ chối null từ service là đúng hơn việc chạy query mơ hồ.

### 11.2. NULL không tự giống “không có bộ lọc”

Với minimumPrice:

~~~java
where p.price >= :minimumPrice
~~~

nếu bind **minimumPrice=null**, JPQL không tự hiểu đó là “mọi giá đều được chấp nhận”. Muốn khi không có minPrice thì bỏ điều kiện:

~~~java
where (:minimumPrice is null or p.price >= :minimumPrice)
~~~

Với **minimumPrice=null**, nhánh đầu TRUE, và biểu thức OR thành TRUE ngay cả khi p.price NULL. Nhưng với minimumPrice khác null, p.price NULL vẫn cho UNKNOWN và bị loại.

### 11.3. Optional parameter pattern

Một mẫu tiện cho query nhỏ:

~~~java
List<Product> result = em.createQuery(
    """
    select p
    from Product p
    where p.deletedAt is null
      and (:minPrice is null or p.price >= :minPrice)
      and (:maxPrice is null or p.price <= :maxPrice)
    order by p.id asc
    """,
    Product.class
)
.setParameter("minPrice", minPrice)
.setParameter("maxPrice", maxPrice)
.getResultList();
~~~

Điểm cần hiểu:
- Null của **parameter** ở đây được quy ước là **bỏ filter**.
- Null của **p.price** có thể được giữ lại nếu cả minPrice và maxPrice đều null.
- Khi có ít nhất một giới hạn giá, các Product price NULL không được chọn.
- Điều kiện **p.deletedAt IS NULL** vẫn áp dụng trong mọi tình huống.

### 11.4. Giới hạn về type inference khi bind null

Một JPQL parameter xuất hiện trong biểu thức:

~~~java
:minimumPrice is null
~~~

có thể gây khó khăn cho một số provider/driver/dialect khi giá trị bind thực sự null và kiểu JDBC không được suy luận rõ. Khi cùng parameter xuất hiện ở **p.price >= :minimumPrice**, provider thường có thêm ngữ cảnh type; nhưng không nên coi mọi hệ quản trị đều xử lý như nhau.

Nếu muốn portable và có performance tối ưu cho nhiều tổ hợp bộ lọc, **xây predicate động và bỏ hẳn điều kiện khi tham số null** thường dễ kiểm soát hơn mẫu **:param IS NULL OR ...**.

### 11.5. Một biểu thức “null-safe equality” có chủ đích

Giả sử business rule cần xem hai giá trị cùng NULL là “tương đương”:

~~~java
where p.someField = :value
   or (p.someField is null and :value is null)
~~~

Cách này thường được sử dụng cho equality giữa nullable field và nullable parameter, nhưng cần chú ý type inference và provider. Một phương án sạch hơn là **tạo query với predicate IS NULL khi value null, còn lại dùng equality**.

JPQL chuẩn không tự sử dụng cú pháp **IS NOT DISTINCT FROM** trên mọi provider/dialect như một biểu thức portable; một số DB có cú pháp null-safe equality riêng, nhưng không nên đưa nguyên cú pháp SQL đó vào JPQL mà không kiểm tra khả năng hỗ trợ.

## 12. NULL và association path: implicit JOIN có thể làm mất bản ghi

Đây là bẫy thực tế khi lọc trên thuộc tính của association tùy chọn.

Entity Product có:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "category_id")
private Category category;
~~~

Với một Product không có category, tham chiếu **p.category** là NULL.

### 12.1. Lọc theo tên danh mục

~~~java
select p
from Product p
where p.category.name = :categoryName
~~~

Đường dẫn **p.category.name** đi qua association Category. Trong nhiều mapping/query trường hợp, provider có thể dùng **implicit inner join** để truy cập thuộc tính Category. Product không có category sẽ bị loại khỏi kết quả.

Điều đó hợp lý với yêu cầu “Category phải có tên X”, nhưng có thể sai khi điều kiện nằm trong một OR.

### 12.2. Bẫy với OR và association path

Giả sử yêu cầu:

> Lấy Product có Category tên Electronics **hoặc** Product chưa có Category.

Câu dễ viết nhưng không nên phụ thuộc cách provider xử lý join:

~~~java
select p
from Product p
where p.category.name = :categoryName
   or p.category is null
~~~

Nếu **p.category.name** tạo implicit inner join, hàng không có Category có thể đã bị loại khỏi tập trung gian trước khi xét OR. Dù biểu thức **p.category IS NULL** đúng, row ấy vẫn không xuất hiện từ join.

### 12.3. Dùng explicit LEFT JOIN

Cách rõ ràng:

~~~java
List<Product> products = em.createQuery(
    """
    select p
    from Product p
    left join p.category c
    where c.name = :categoryName
       or p.category is null
    """,
    Product.class
)
.setParameter("categoryName", "Electronics")
.getResultList();
~~~

**LEFT JOIN** giữ Product chưa có Category, tạo cột phía Category là NULL. Predicate **p.category IS NULL** sau đó có thể chọn những Product chưa liên kết.

Với dataset, kết quả gồm P01, P02, P05, P06, P07, P08. P06 vẫn được chọn vì đã có category Electronics dù deletedAt có timestamp; muốn loại soft-deleted Product phải thêm điều kiện riêng.

### 12.4. LEFT JOIN và điều kiện trong WHERE

~~~java
select p
from Product p
left join p.category c
where c.name = :categoryName
~~~

Dù đã dùng LEFT JOIN, điều kiện WHERE **c.name = :categoryName** vẫn loại những hàng Category NULL; hiệu ứng đối với Product không có Category tương tự inner join cho điều kiện này.

Nếu muốn chọn **các Product không có Category cùng với Electronics**, phải viết logic OR rõ như trên.

### 12.5. Điều kiện ON khác WHERE

JPQL hỗ trợ join condition với **ON** trong các phiên bản JPA hiện đại:

~~~java
select p
from Product p
left join p.category c on c.name = :categoryName
~~~

Đặt điều kiện tên Category ở **ON** giới hạn những Category rows được match, nhưng **vẫn giữ Product** từ phía trái kể cả khi category không match. Vì câu query này không có WHERE, nó có thể trả **mọi Product**, không phải chỉ Electronics.

So sánh:

~~~java
-- Ý tưởng 1: chỉ Product thuộc Electronics:
select p
from Product p
join p.category c
where c.name = :categoryName
~~~

~~~java
-- Ý tưởng 2: tất cả Product; join Category chỉ khi tên match:
select p
from Product p
left join p.category c on c.name = :categoryName
~~~

Ý nghĩa của ON/WHERE với outer join là khác nhau; đừng chuyển điều kiện từ WHERE sang ON chỉ vì muốn “giữ NULL” mà không xác định tập entity cần trả.

### 12.6. Kiểm tra không có liên kết đơn giản hơn

Nếu chỉ muốn Product không có Category, viết:

~~~java
where p.category is null
~~~

thường rõ ràng và đơn giản hơn một LEFT JOIN rồi kiểm tra **c.id IS NULL**. Nếu cần kiểm tra Category có trạng thái hoặc metadata khác, explicit join mới cần thiết.

### 12.7. Fetch join không phải bộ lọc mặc định

~~~java
select p
from Product p
left join fetch p.category
where p.active = true
~~~

**LEFT JOIN FETCH** điều khiển việc nạp association cùng query; nó không thay thế bộ lọc **p.active** hoặc **category IS NULL**. Sử dụng fetch join khi phần kết quả cần đọc Category, không chỉ vì muốn điều kiện WHERE có JOIN. Với collection fetch, còn có rủi ro nhân row và phân trang; trong ví dụ Category là to-one nên thường đơn giản hơn.

## 13. Boolean, enum và ngày giờ trong điều kiện JPQL

### 13.1. Boolean literal

~~~java
select p
from Product p
where p.active = true
~~~

hoặc:

~~~java
select p
from Product p
where p.active = false
~~~

Với Boolean nullable, **= false** sẽ không bao gồm NULL. Khi nghiệp vụ muốn “không xác nhận true” gồm false và NULL, có thể viết:

~~~java
where p.flag = false or p.flag is null
~~~

Tuy nhiên null có thể mang nghĩa **chưa xác định** thay vì false; không nên tự gộp hai trạng thái nếu nghiệp vụ cần phân biệt.

### 13.2. Enum parameter

Giả sử một entity Order có:

~~~java
public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
~~~

và:

~~~java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false)
private OrderStatus status;
~~~

JPQL:

~~~java
List<Order> paid = em.createQuery(
    """
    select o
    from Order o
    where o.status = :status
    """,
    Order.class
)
.setParameter("status", OrderStatus.PAID)
.getResultList();
~~~

Bind enum type thay vì tự ghép literal chuỗi giúp giữ đúng kiểu mapping và không phụ thuộc việc enum lưu STRING hay ORDINAL. **ORDINAL** có nguy cơ thay đổi ý nghĩa dữ liệu khi sắp thứ tự enum, vì vậy khi xây hệ thống lâu dài thường cân nhắc lưu enum dạng STRING hoặc mã ổn định phù hợp.

### 13.3. Instant và LocalDate không tự tương đương

Ví dụ:

~~~java
where o.createdAt >= :start
  and o.createdAt < :end
~~~

nên bind **Instant** khi property createdAt là Instant. Nếu người dùng chọn một **LocalDate**, service cần chuyển thành các mốc thời gian theo timezone nghiệp vụ rõ ràng (ví dụ UTC hay múi giờ cửa hàng), không giả định mọi ngày đều có 24 giờ trong mọi timezone.

Một ngày ở khu vực có daylight saving có thể không kéo dài đúng 24 giờ. Khi tạo khoảng ngày, nên dùng timezone phù hợp và lấy **start-of-next-day**, thay vì cộng bừa 24 giờ nếu yêu cầu là ngày theo giờ địa phương.

### 13.4. NULL trong ngày hạn

Giả sử Promotion.expiresAt nullable, với null có nghĩa **không hết hạn**. Bộ lọc “còn hiệu lực tại now”:

~~~java
where (p.expiresAt is null or p.expiresAt > :now)
~~~

Nếu còn điều kiện startsAt:

~~~java
where p.startsAt <= :now
  and (p.expiresAt is null or p.expiresAt > :now)
~~~

Chọn ranh giới **>** hay **>=** dựa vào cách hiểu “hết hạn tại đúng thời điểm expiresAt”. Ví dụ trên coi promotion hết hiệu lực **ngay khi now bằng expiresAt**.

### 13.5. Không dùng function thiếu tính portable tùy tiện

Những biểu thức thời gian, case-insensitive search hoặc JSON operators có thể được provider/dialect hỗ trợ với các functions mở rộng. Khi cần logic portable, ưu tiên toán tử và chức năng chuẩn JPQL, bind các tham số đã được tính ở application layer khi hợp lý.

Không ghép SQL fragment như **DATE_TRUNC(...)** vào JPQL nếu provider không hỗ trợ; có thể dùng **FUNCTION(...)** theo đặc tả/provider hoặc native SQL khi thực sự cần, nhưng phải ghi rõ database dependency.

## 14. COALESCE, NULLIF và CASE trong lọc dữ liệu

Khi cần biến đổi giá trị NULL thành một giá trị có nghĩa trước khi so sánh, JPQL có các biểu thức hữu ích.

### 14.1. COALESCE

**COALESCE(expr1, expr2, ...)** trả biểu thức đầu tiên không NULL.

Giả sử stockQuantity null có nghĩa “chưa cập nhật tồn kho”, nhưng ở một màn hình nghiệp vụ muốn **tạm coi là 0**:

~~~java
select p
from Product p
where coalesce(p.stockQuantity, 0) = 0
~~~

Điều kiện chọn P03 có stockQuantity=0 và P04/P05 có stockQuantity=NULL. Đây là **quy ước nghiệp vụ cụ thể của query**; không có nghĩa NULL và 0 luôn tương đương ở mọi nơi.

Nếu muốn giữ khác biệt “hết hàng” và “chưa biết tồn kho” thì dùng:
- **p.stockQuantity = 0** cho hết hàng đã biết;
- **p.stockQuantity IS NULL** cho chưa biết.

### 14.2. COALESCE với tên hiển thị

Một entity Customer có **nickname** nullable:

~~~java
select c
from Customer c
where coalesce(c.nickname, c.fullName) like :pattern
~~~

Query lọc theo nickname nếu có, ngược lại theo fullName. Loại dữ liệu các đối số phải tương thích.

### 14.3. NULLIF

**NULLIF(a, b)** trả NULL nếu hai biểu thức bằng nhau, ngược lại trả a. Ví dụ một trường text có dữ liệu legacy chuỗi rỗng, muốn coi chuỗi rỗng như NULL:

~~~java
where nullif(p.name, '') is null
~~~

Predicate có thể khớp name NULL hoặc name bằng chuỗi rỗng theo SQL semantics của DB. Trong entity mẫu, name NOT NULL nhưng vẫn có thể chứa chuỗi rỗng nếu dữ liệu được chèn ngoài constructor.

Không dùng NULLIF vô điều kiện để né ràng buộc dữ liệu: khi dữ liệu sai theo domain, có thể cần migration/validation/constraint.

### 14.4. CASE

Biểu thức CASE diễn đạt nhiều nhánh theo điều kiện:

~~~java
select p
from Product p
where
    case
        when p.stockQuantity is null then 0
        else p.stockQuantity
    end > :minimumStock
~~~

Ví dụ minh họa giá trị NULL được quy đổi thành 0 trước khi lọc. Với nhu cầu đơn giản, **coalesce(p.stockQuantity, 0)** thường ngắn gọn hơn.

CASE có ích khi điều kiện tính toán phức tạp hoặc khi projection cần biểu diễn trạng thái. Tuy nhiên quá nhiều function/case trong WHERE có thể làm query khó tận dụng index và khó tối ưu.

### 14.5. Index và sargability

So sánh trực tiếp:

~~~java
where p.price >= :minimum
~~~

thường dễ tận dụng index trên unit_price hơn một biểu thức tùy ý bao quanh cột:

~~~java
where coalesce(p.price, 0) >= :minimum
~~~

Tùy DB có thể có function-based/expression index; không phải mọi function đều làm mất khả năng dùng index, nhưng cần đo kế hoạch truy vấn và lựa chọn semantics đúng trước khi tối ưu.

## 15. Criteria API: xây predicate động an toàn

Khi form tìm kiếm có nhiều trường tùy chọn, một JPQL với nhiều nhánh **:param IS NULL OR ...** có thể dài và khó bảo trì. **Criteria API** cho phép xây biểu thức điều kiện theo những giá trị hiện có.

Ví dụ input:

~~~java
public record ProductFilter(
    BigDecimal minPrice,
    BigDecimal maxPrice,
    Boolean active,
    String keyword,
    Long categoryId,
    boolean onlyUncategorized
) {}
~~~

Thiết kế semantics:
- minPrice/maxPrice null: **không áp điều kiện biên**.
- active null: **không áp trạng thái active**.
- keyword null hoặc blank: **không lọc name**.
- categoryId null: **không lọc category** trừ khi onlyUncategorized=true.
- onlyUncategorized=true: **lọc Category NULL**, không chỉ “không áp bộ lọc”.

### 15.1. Xây danh sách Predicate

~~~java
public List<Product> searchProducts(
        EntityManager em, ProductFilter filter) {

    CriteriaBuilder cb = em.getCriteriaBuilder();
    CriteriaQuery<Product> cq = cb.createQuery(Product.class);
    Root<Product> p = cq.from(Product.class);

    List<Predicate> predicates = new ArrayList<>();

    // Quy tắc luôn được áp dụng.
    predicates.add(cb.isNull(p.get("deletedAt")));

    if (filter.minPrice() != null) {
        predicates.add(cb.greaterThanOrEqualTo(
            p.get("price"), filter.minPrice()));
    }

    if (filter.maxPrice() != null) {
        predicates.add(cb.lessThanOrEqualTo(
            p.get("price"), filter.maxPrice()));
    }

    if (filter.active() != null) {
        predicates.add(cb.equal(
            p.get("active"), filter.active()));
    }

    if (filter.keyword() != null
            && !filter.keyword().isBlank()) {
        String pattern = "%"
            + filter.keyword().toLowerCase(Locale.ROOT)
            + "%";

        predicates.add(cb.like(
            cb.lower(p.get("name")), pattern));
    }

    if (filter.onlyUncategorized()) {
        predicates.add(cb.isNull(p.get("category")));
    } else if (filter.categoryId() != null) {
        Join<Product, Category> category =
            p.join("category", JoinType.INNER);

        predicates.add(cb.equal(
            category.get("id"), filter.categoryId()));
    }

    cq.select(p)
      .where(cb.and(predicates.toArray(Predicate[]::new)))
      .orderBy(cb.asc(p.get("id")));

    return em.createQuery(cq)
             .setMaxResults(100)
             .getResultList();
}
~~~

Các imports tương ứng:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.Predicate;
import jakarta.persistence.criteria.Root;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
~~~

Đây là ví dụ Java hiện đại (phương thức **toArray(Predicate[]::new)**), có thể thay bằng **toArray(new Predicate[0])** nếu cần. Class Product/Category là những entity ở phần đầu.

### 15.2. Đọc semantics của Criteria rõ ràng

~~~java
cb.equal(path, value)
~~~

diễn đạt phép bằng với giá trị đã biết. Nếu **value=null**, đừng mặc định coi equal là IS NULL portable. Dùng:

~~~java
cb.isNull(path)
~~~

hoặc:

~~~java
cb.isNotNull(path)
~~~

cho NULL checks.

Khi điều kiện tùy chọn không có giá trị, **không thêm predicate** là cách diễn đạt “bỏ lọc”. Điều này khác hoàn toàn với việc thêm một predicate so sánh bằng NULL.

### 15.3. AND/OR/NOT trong Criteria

~~~java
Predicate active = cb.isTrue(p.get("active"));
Predicate inStock = cb.greaterThan(
    p.get("stockQuantity"), 0);

Predicate match = cb.or(active, inStock);
Predicate visible = cb.isNull(p.get("deletedAt"));

cq.where(cb.and(match, visible));
~~~

Cách này tương đương:

~~~java
where (p.active = true or p.stockQuantity > 0)
  and p.deletedAt is null
~~~

**cb.and** và **cb.or** tạo nhóm điều kiện rõ ràng. Khi cần phủ định, có thể dùng **cb.not(predicate)** hoặc predicate.not() theo API.

### 15.4. Criteria API không tự giải quyết mọi vấn đề

Dù không ghép JPQL string thủ công, vẫn phải xử lý:
- Semantics NULL và các bộ lọc tùy chọn;
- Implicit/explicit joins và việc mất row không có association;
- Wildcards của LIKE;
- Bộ lọc tenant/authorization;
- Pagination và order ổn định;
- N+1/plan/index;
- Tránh để user nhập tên property bất kỳ mà code dùng trực tiếp trong path.

Criteria giúp **xây cấu trúc query an toàn và composable**, nhưng không tự quyết định đúng nghiệp vụ.


## 16. Spring Data JPA: phương thức repository và @Query

Khi sử dụng Spring Data JPA, bạn có thể diễn đạt điều kiện WHERE bằng **derived query methods** hoặc JPQL trong **@Query**.

### 16.1. Derived query method

Ví dụ:

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    List<Product> findByActiveTrueAndDeletedAtIsNull();

    List<Product> findByPriceGreaterThanEqualAndDeletedAtIsNull(
        BigDecimal minPrice
    );

    List<Product> findByCategoryIsNull();

    List<Product> findByNameContainingIgnoreCase(String keyword);
}
~~~

Spring Data suy ra predicate dựa trên tên property của entity:
- **ActiveTrue** tương ứng active = true.
- **DeletedAtIsNull** tương ứng deletedAt IS NULL.
- **PriceGreaterThanEqual** tương ứng price >= parameter.
- **CategoryIsNull** tương ứng association NULL.
- **ContainingIgnoreCase** là pattern string search theo cơ chế provider/framework.

Các derived methods này là tính năng Spring Data JPA, **không phải cú pháp JPQL chuẩn**. Khi quy tắc lọc phức tạp, method name dài và khó đọc; chuyển sang @Query, Specifications/Criteria hoặc một query service chuyên biệt.

### 16.2. JPQL tường minh qua @Query

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.deletedAt is null
          and p.active = true
          and p.price between :minPrice and :maxPrice
        order by p.price asc, p.id asc
        """)
    List<Product> findActiveInPriceRange(
        @Param("minPrice") BigDecimal minPrice,
        @Param("maxPrice") BigDecimal maxPrice
    );
}
~~~

Cần import:
- **org.springframework.data.jpa.repository.JpaRepository**;
- **org.springframework.data.jpa.repository.Query**;
- **org.springframework.data.repository.query.Param**;
- **java.math.BigDecimal**;
- **java.util.List**.

Phương thức minh họa dùng khoảng bao gồm hai biên; nếu minPrice/maxPrice null, phải xử lý input trước hoặc viết predicate tùy chọn khác, không mong BETWEEN tự bỏ điều kiện.

### 16.3. Tránh viết static @Query với quá nhiều điều kiện OR tùy chọn

Ví dụ:

~~~java
@Query("""
    select p
    from Product p
    where p.deletedAt is null
      and (:active is null or p.active = :active)
      and (:minPrice is null or p.price >= :minPrice)
      and (:maxPrice is null or p.price <= :maxPrice)
      and (:keyword is null or lower(p.name) like :keyword)
    """)
List<Product> search(
    Boolean active,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    String keyword
);
~~~

Mẫu này có thể hữu ích với form nhỏ; tuy nhiên có nhiều vấn đề cần quản lý:
- **keyword** phải được chuẩn bị theo nghĩa LIKE mong muốn, bao gồm escape wildcard nếu cần.
- **null parameter type inference** không giống nhau ở mọi dialect/provider.
- Predicate OR có thể khó được optimizer dùng index trong một số tổ hợp.
- Khi form tăng lên 20–30 bộ lọc, query trở nên khó bảo trì.
- Phải luôn áp các điều kiện security/tenant/soft delete theo policy.

Với nhiều điều kiện tùy chọn, dùng Criteria API hoặc Spring Data Specification có thể làm logic **thêm/bỏ predicate** rõ ràng hơn.

## 17. Phân biệt điều kiện lọc với việc sắp xếp NULL

**WHERE** quyết định row nào được giữ; **ORDER BY** quyết định thứ tự các row đó.

~~~java
select p
from Product p
where p.price is not null
order by p.price asc
~~~

Ở đây price NULL bị loại từ WHERE, nên thứ tự NULL không còn quan trọng.

Nhưng:

~~~java
select p
from Product p
order by p.price asc
~~~

sẽ gồm cả price NULL nếu không có filter khác. **Vị trí NULL trong ORDER BY có thể khác theo database/provider và dialect**. Không mặc định NULL luôn đứng đầu hay cuối trên mọi DB.

Nếu cần quy tắc portable hơn, có thể dùng CASE trong ORDER BY:

~~~java
select p
from Product p
order by
    case when p.price is null then 1 else 0 end asc,
    p.price asc,
    p.id asc
~~~

Ý nghĩa:
1. Giá không NULL trước (CASE = 0);
2. Giá NULL sau (CASE = 1);
3. Trong từng nhóm, sắp theo giá và ID.

Việc thêm **p.id** làm thứ tự ổn định hơn khi nhiều sản phẩm cùng giá, quan trọng đối với pagination. Một số JPQL provider có cú pháp **NULLS FIRST / NULLS LAST** mở rộng, nhưng không giả định portable trên mọi cấu hình JPA.

## 18. Lọc chính xác khi dữ liệu liên quan NULL

### 18.1. “Không phải Electronics” có bao gồm chưa gán Category không?

Yêu cầu mơ hồ:

> Hiển thị những Product không thuộc Electronics.

Có hai cách hiểu:

**Cách A:** Chỉ các Product đã có Category, nhưng tên không phải Electronics.

~~~java
select p
from Product p
join p.category c
where c.name <> :electronics
~~~

Trong dataset, P03 và P04 có Category Furniture, nên được chọn (nếu chưa áp soft delete). P05 và P07 không có Category, bị loại.

**Cách B:** Mọi Product không thuộc Electronics, bao gồm cả Product chưa có Category.

~~~java
select p
from Product p
left join p.category c
where c.name <> :electronics
   or c.id is null
~~~

Trong dataset, P03, P04, P05 và P07 được chọn. Sự khác nhau không nằm ở cú pháp ngẫu nhiên, mà ở **định nghĩa nghiệp vụ của “không thuộc” khi dữ liệu category vắng mặt**.

### 18.2. “Giá không cao hơn X” có bao gồm chưa có giá không?

Diễn đạt:

~~~java
where p.price <= :maximum
~~~

chỉ chọn sản phẩm có price so sánh được và không quá X. Product price NULL bị loại.

Nếu muốn coi **chưa có giá** cũng thuộc nhóm “chưa vượt X”:

~~~java
where p.price <= :maximum
   or p.price is null
~~~

Đây là một lựa chọn semantics cần được giải thích cho người dùng, không phải phép tương đương toán học bắt buộc.

### 18.3. “Không phải inactive” với Boolean nullable

Nếu state có kiểu Boolean nullable:

~~~java
where p.active <> false
~~~

không chọn active NULL. Nếu nghiệp vụ muốn mọi trạng thái trừ false:

~~~java
where p.active = true
   or p.active is null
~~~

Một hệ thống có nhiều trạng thái nên cân nhắc enum rõ ràng như ACTIVE/SUSPENDED/PENDING, thay vì dùng Boolean nullable như một enum ba giá trị không được tài liệu hóa.

### 18.4. NULL ở cột FK khác NULL trong bảng target

Một Product có **category_id NULL** là thiếu association; một Product có **category_id** trỏ tới Category tồn tại nhưng Category.name NULL (nếu được phép) là **có association nhưng thiếu tên**.

Hai điều kiện khác:
- **p.category IS NULL**: không có Category liên kết.
- **c.name IS NULL** qua LEFT JOIN: có thể gồm Product không liên kết **và** Product có Category nhưng Category.name NULL.

Nếu muốn tách:
- Không có Category: **p.category IS NULL**.
- Có Category nhưng tên NULL: **p.category IS NOT NULL AND c.name IS NULL** với LEFT JOIN rõ ràng.
- Mọi trường hợp không có tên Category: LEFT JOIN và **c.name IS NULL**, biết rằng nó gộp hai nguyên nhân.

Khi dữ liệu có ý nghĩa khác nhau, nên dùng predicate phản ánh khác biệt ấy thay vì coi mọi NULL là như nhau.

## 19. Subquery, EXISTS và NULL trong bộ lọc

Dù bài tập trung JPQL cơ bản, cần hiểu sơ bộ cách xử lý NULL khi điều kiện dựa vào một tập kết quả khác.

Giả sử muốn lọc Category **chưa có Product**. Nếu Category có collection Products đã mapping, ta có thể dùng:

~~~java
select c
from Category c
where c.products is empty
~~~

Một cách khác là correlated subquery:

~~~java
select c
from Category c
where not exists (
    select p.id
    from Product p
    where p.category = c
)
~~~

**EXISTS** quan tâm có ít nhất một row từ subquery, không so sánh mỗi giá trị trả về với một danh sách có NULL. Vì vậy trong nhiều trường hợp chống bẫy NOT IN NULL, **NOT EXISTS** là lựa chọn dễ hiểu hơn.

### 19.1. So sánh NOT IN và NOT EXISTS

Một truy vấn:

~~~java
where c.id not in (
    select p.category.id
    from Product p
)
~~~

có thể gây nhầm vì subquery lấy category ID từ Product có category nullable; NULL trong tập subquery làm **NOT IN** có semantics ba giá trị không như người viết mong muốn. Ngoài ra, path navigation có thể sinh join và ảnh hưởng cách xử lý null.

Viết:

~~~java
where not exists (
    select p.id
    from Product p
    where p.category = c
)
~~~

thường diễn đạt trực tiếp “không có Product nào thuộc Category này”.

Đừng vì thế khẳng định **NOT EXISTS luôn nhanh hơn NOT IN**. Chọn theo semantics rồi xem execution plan trên database thực tế.

### 19.2. Phân biệt tập rỗng và phần tử NULL

Trong logic set/subquery:
- **Không có hàng trả về** là tập rỗng.
- **Có một hàng mang giá trị NULL** là một tập có phần tử NULL.

Hai trường hợp này có thể dẫn đến kết quả khác với NOT IN, ANY/ALL và phép so sánh. Khi query theo association nullable, phải xác định mình đang kiểm tra **không tồn tại bản ghi** hay **bản ghi tồn tại nhưng một field NULL**.

## 20. Hiệu năng và tính đúng đắn của bộ lọc JPQL

Một câu JPQL “đúng cú pháp” chưa chắc đúng nghiệp vụ hoặc đủ nhanh khi dữ liệu lớn.

### 20.1. Không tự đưa logic của WHERE xuống Java

Không nên:

~~~java
List<Product> all = em.createQuery(
    "select p from Product p",
    Product.class
).getResultList();

List<Product> selected = all.stream()
    .filter(p -> p.getPrice() != null)
    .filter(p -> p.getPrice().compareTo(minPrice) >= 0)
    .toList();
~~~

nếu có thể lọc bằng database:

~~~java
List<Product> selected = em.createQuery(
    """
    select p
    from Product p
    where p.price >= :minPrice
    """,
    Product.class
)
.setParameter("minPrice", minPrice)
.getResultList();
~~~

Lọc ở DB có thể giảm số row chuyển qua mạng, số entities ORM phải tạo, memory và chi phí dirty checking. Ngoại lệ là khi điều kiện không biểu diễn được ở DB hoặc business logic có lý do chính đáng để xử lý trong RAM, và tập dữ liệu đã được giới hạn.

### 20.2. Không gọi function lên cột khi không cần

So sánh trực tiếp:

~~~java
where p.price >= :minimum
~~~

thường dễ dùng index trên unit_price hơn:

~~~java
where coalesce(p.price, 0) >= :minimum
~~~

nhưng cái thứ hai còn có **semantics khác với NULL**, nên không chỉ là vấn đề tối ưu. Luôn chọn điều kiện đúng ý nghĩa trước.

### 20.3. Index cho bộ lọc phổ biến

Ví dụ schema:

~~~sql
CREATE INDEX idx_products_active_deleted
    ON products(is_active, deleted_at);

CREATE INDEX idx_products_price
    ON products(unit_price);

CREATE INDEX idx_products_category
    ON products(category_id);
~~~

Đây là các chỉ mục minh họa, không phải danh sách bắt buộc. Tác dụng phụ thuộc độ chọn lọc, số row, quy tắc DB optimizer và workload. Index một boolean có ít giá trị có thể không hiệu quả nếu phần lớn row cùng giá trị; index kết hợp hoặc partial index có thể phù hợp hơn tùy database.

Khi đọc EXPLAIN/EXPLAIN ANALYZE, xem số row scan, index usage, joins, sort, memory và thời gian thực tế. Không đánh giá tốc độ chỉ từ độ dài câu JPQL.

### 20.4. Optional OR có thể ảnh hưởng execution plan

~~~java
where (:minimum is null or p.price >= :minimum)
~~~

tiện để dùng một query cho nhiều trường hợp, nhưng tùy DB, cached query plan và cách parameter binding, điều kiện OR có thể được tối ưu kém hơn một query thực sự chỉ chứa **p.price >= :minimum** khi parameter không null.

Nếu màn hình nhiều filter tùy chọn và lượng dữ liệu lớn, Criteria API hoặc query builder tạo **chỉ những predicate cần thiết** có thể cho SQL rõ ràng hơn. Không khẳng định mọi OR đều chậm; cần đo trên dữ liệu thật.

### 20.5. Giới hạn kết quả và thứ tự ổn định

~~~java
List<Product> page = em.createQuery(
    """
    select p
    from Product p
    where p.deletedAt is null
    order by p.price asc, p.id asc
    """,
    Product.class
)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

Nếu order by price có NULL, thứ tự NULL phụ thuộc DB; nếu cần nhất quán giữa dialect, thêm CASE như phần 17. Thêm **ID** làm tie-breaker giúp kết quả ít bị đảo vị trí khi nhiều hàng cùng giá, nhưng pagination OFFSET vẫn có thể biến động khi dữ liệu được insert/delete đồng thời.

### 20.6. Vấn đề N+1 khác logic WHERE

Một query:

~~~java
select p
from Product p
where p.category is not null
~~~

chỉ lọc Product. Nếu category là LAZY và sau đó code duyệt mọi Product rồi gọi **p.getCategory().getName()**, có thể sinh N+1 SELECT.

Khi cần dữ liệu Category trong cùng response, dùng **join fetch**, entity graph hoặc DTO projection phù hợp. Không nhầm việc WHERE dùng association với việc association đã được fetch đầy đủ.

### 20.7. Bộ lọc bảo mật không phải input tùy chọn

Nếu hệ thống có **tenantId**, **ownerId**, **visibility** hoặc soft-delete policy, đừng để user tùy ý bỏ những predicate bảo mật bằng tham số null. Ví dụ:

~~~java
where p.tenantId = :authorizedTenantId
  and p.deletedAt is null
  and (:minimum is null or p.price >= :minimum)
~~~

Trong ví dụ giả định Product có field tenantId phù hợp. **authorizedTenantId** phải được xác định từ context xác thực/ủy quyền của server, không tin hoàn toàn vào request input.

Bộ lọc tùy chọn chỉ nên áp dụng cho **tiêu chí tìm kiếm**; điều kiện bảo mật/quyền truy cập là bất biến nghiệp vụ cần luôn được thực thi.

## 21. Kiểm thử bộ lọc JPQL và NULL

Một test tốt cần có dữ liệu đủ đa dạng để phát hiện lỗi ưu tiên logic, giá trị biên, NULL và association tùy chọn. Chỉ test bằng những row “đẹp” có đầy đủ field sẽ bỏ sót lỗi nghiêm trọng.

### 21.1. Chuẩn bị dataset kiểm thử

Tạo những Product:
- giá 100000, 350000, 950000, NULL;
- stock 0, dương và NULL;
- active true/false;
- deletedAt NULL/có timestamp;
- category có liên kết/không có liên kết;
- name bắt đầu/kết thúc/chứa keyword, và một tên chứa ký tự wildcard literal như **20% OFF**.

Dùng migration/schema giống production khi có thể. Khác biệt database về NULL ordering, collation và LIKE là lý do quan trọng để có integration tests trên DB mục tiêu, không chỉ unit tests giả lập trong Java.

### 21.2. Test IS NULL và IS NOT NULL

~~~java
@Test
void findsProductsWithoutPrice() {
    List<Product> result = em.createQuery(
        """
        select p
        from Product p
        where p.price is null
        """,
        Product.class
    ).getResultList();

    assertTrue(
        result.stream().anyMatch(p -> "P05".equals(p.getCode()))
    );
}
~~~

Mẫu giả định fixture có P05 như phần đầu; để test chính xác, nên assert tập mã đầy đủ theo dữ liệu test đã cố định.

### 21.3. Test biên BETWEEN

~~~java
@Test
void betweenIncludesBothBoundaries() {
    List<Product> result = em.createQuery(
        """
        select p
        from Product p
        where p.price between :min and :max
        """,
        Product.class
    )
    .setParameter("min", new BigDecimal("350000.00"))
    .setParameter("max", new BigDecimal("950000.00"))
    .getResultList();

    Set<String> codes = result.stream()
        .map(Product::getCode)
        .collect(Collectors.toSet());

    assertTrue(codes.contains("P02"));
    assertTrue(codes.contains("P03"));
}
~~~

Đây là JUnit với **java.util.Set** và **java.util.stream.Collectors**. Test dựa vào fixture có đúng các mức giá tương ứng.

### 21.4. Test precedence AND/OR

Hai query:

~~~java
where p.active = true
   or (p.stockQuantity = 0 and p.deletedAt is null)
~~~

và:

~~~java
where (p.active = true or p.stockQuantity = 0)
  and p.deletedAt is null
~~~

có thể cho tập kết quả khác, ví dụ P06 active nhưng đã deleted: query đầu có thể giữ P06 vì vế active TRUE; query sau loại P06 vì deletedAt không NULL. Test nên assert sự khác biệt, để tránh người bảo trì xóa ngoặc làm sai semantics.

### 21.5. Test NULL với NOT

~~~java
where not (p.price > :threshold)
~~~

không nên trả Product có price NULL. Test thêm:

~~~java
where p.price <= :threshold or p.price is null
~~~

để khẳng định trường hợp muốn bao gồm NULL được viết rõ.

### 21.6. Test category NULL với LEFT JOIN

Với:

~~~java
select p
from Product p
left join p.category c
where c.name = :name
   or p.category is null
~~~

test phải có ít nhất một Product chưa gán category. Nếu chỉ test Product có category, không thể phát hiện lỗi do thay LEFT JOIN bằng implicit INNER JOIN.

### 21.7. Test LIKE wildcard literal

Tạo Product có tên chứa **20% OFF** và Product khác có tên **20X OFF**. Truy vấn tìm ký tự **%** literal phải chỉ khớp tên có dấu phần trăm, không coi % trong input là wildcard. Dùng **ESCAPE** và hàm escapeLike tương ứng.

### 21.8. Test tham số tùy chọn

Kiểm tra ít nhất:
- minPrice = null, maxPrice = null;
- minPrice có giá trị, maxPrice null;
- minPrice null, maxPrice có giá trị;
- cả hai có giá trị;
- minPrice > maxPrice;
- categoryId null nghĩa bỏ filter;
- onlyUncategorized true nghĩa category IS NULL;
- keyword blank;
- code list rỗng;
- NOT IN list có NULL nếu đó là lỗi cần được chặn.

### 21.9. Test không chỉ so Java stream

Đừng lấy mọi Product rồi filter bằng Java trong test và kết luận JPQL đúng mà chưa thực thi query. Integration test nên chạy **TypedQuery thực sự** với persistence provider/database, kiểm tra tập IDs/codes mong đợi.

Nếu test cần xác nhận dữ liệu đã persist, có thể flush/clear trước khi truy vấn để không vô tình dựa vào object graph còn trong persistence context. Đây là kiểm tra readback và query semantics, không phải dấu hiệu commit nếu transaction còn mở.

## 22. Bài tập thực hành

Các bài tập dùng dataset Product ở phần 2, trừ khi đề bài nêu một entity khác. Hãy **viết JPQL**, dự đoán kết quả và giải thích rõ khi có NULL. Với bài có mã Java, dùng named parameters và TypedQuery phù hợp.

### Bài 1. So sánh giá cơ bản

Viết JPQL lấy các Product có giá **lớn hơn hoặc bằng 350.000**, sắp theo giá tăng dần. Trong dataset, những mã nào được chọn? Tại sao Product P05 không nằm trong kết quả?

**Định hướng:**

~~~java
select p
from Product p
where p.price >= :minPrice
order by p.price asc
~~~

P05 có price NULL, so sánh với minPrice cho UNKNOWN nên bị loại.

### Bài 2. Phân biệt > và >=

MinPrice là **350.000**. Hãy so sánh:

~~~java
where p.price > :minPrice
~~~

với:

~~~java
where p.price >= :minPrice
~~~

Truy vấn nào giữ P02? Nếu yêu cầu “tối thiểu 350.000” thì dùng toán tử nào?

### Bài 3. Lọc sản phẩm chưa xóa và đang bán

Yêu cầu: Product **active=true** và **deletedAt NULL**.

Viết JPQL cùng Java TypedQuery. Dự đoán P06 có được chọn không. Giải thích vì sao chỉ kiểm tra active=true là chưa đủ trong model soft delete.

### Bài 4. Tìm số lượng hàng bằng 0

Viết truy vấn tìm Product có **stockQuantity = 0**. Có nên coi P04/P05 (stockQuantity NULL) là hàng hết tồn kho không?

Viết hai phiên bản:
1. Chỉ lấy tồn kho có giá trị 0;
2. Quy ước NULL được coi như 0.

**Định hướng:** bản một dùng **p.stockQuantity = 0**; bản hai có thể dùng **p.stockQuantity = 0 OR p.stockQuantity IS NULL** hoặc COALESCE nếu nghiệp vụ chấp thuận.

### Bài 5. Lọc các sản phẩm trong khoảng giá

Lấy Product có giá từ **350.000** đến **950.000**, bao gồm hai đầu. Dùng:
1. BETWEEN;
2. >= và <=.

Giải thích vì sao hai cách có cùng ý nghĩa với dữ liệu giá bình thường và cách NULL được xử lý.

### Bài 6. Điều kiện nhiều nhánh

Yêu cầu: Product **chưa xóa** và (**còn tồn kho** hoặc **giá dưới 500.000**). Viết JPQL có dấu ngoặc rõ ràng:

~~~java
where p.deletedAt is null
  and (p.stockQuantity > 0 or p.price < :limit)
~~~

Nếu lược bỏ ngoặc và thay đổi thứ tự OR/AND, sản phẩm đã xóa nào có thể xuất hiện? Dùng P06 để giải thích.

### Bài 7. Bảng chân trị ba giá trị

Cho:
- A = UNKNOWN;
- B = TRUE;
- C = FALSE.

Hãy tính:
1. A AND B;
2. A OR B;
3. NOT A;
4. A AND C;
5. A OR C;
6. NOT (A AND C).

Sau đó giải thích câu WHERE chỉ giữ những biểu thức có kết quả nào.

### Bài 8. Sai lầm với NOT

Một developer viết:

~~~java
where not (p.price > :threshold)
~~~

và kỳ vọng Product giá NULL được xem như “không đắt”. Tại sao P05 không được chọn? Viết lại để bao gồm NULL:

~~~java
where p.price <= :threshold
   or p.price is null
~~~

Phân tích sự khác biệt về nghĩa nghiệp vụ.

### Bài 9. Category NULL

Lấy những Product chưa gán Category bằng **p.category IS NULL**. Theo dataset, có những mã nào?

Sau đó viết truy vấn lấy Product đã có Category và lọc theo tên Furniture, không dùng tên cột **category_id** trực tiếp trong JPQL.

### Bài 10. Implicit INNER JOIN và LEFT JOIN

Một câu JPQL:

~~~java
select p
from Product p
where p.category.name = :name
   or p.category is null
~~~

có thể gặp vấn đề gì đối với Product chưa có Category nếu path navigation tạo implicit join?

Viết lại bằng **LEFT JOIN p.category c** và dự đoán kết quả với name="Electronics". Giải thích vì sao đặt **c.name = :name** vào WHERE có thể lại loại Product không có Category nếu không có nhánh OR.

### Bài 11. Tham số NULL có ba nghĩa khác nhau

Một API nhận **categoryId** nullable. Hãy thiết kế ba phiên bản:
1. null nghĩa **chưa gán category**;
2. null nghĩa **không áp bộ lọc**;
3. null là **input không hợp lệ**.

Tại sao không thể dùng mỗi câu:

~~~java
where p.category.id = :categoryId
~~~

và bind null để đáp ứng cả ba mục tiêu?

### Bài 12. IN với danh sách mã

Input gồm **P01, P03, P07**. Viết JPQL dùng named parameter collection. Nếu input rỗng:
- Khi nào nên return List.of()?
- Khi nào nên bỏ predicate?
- Tại sao không nên tạo SQL IN () một cách máy móc?

### Bài 13. NOT IN và phần tử NULL

Cho code list:

~~~text
['P01', NULL]
~~~

Hãy giải thích vì sao:

~~~java
where p.code not in :excludedCodes
~~~

không tự trả về mọi Product trừ P01. Sử dụng logic **UNKNOWN** để phân tích. Đề xuất validation/filter NULL ở tầng service hoặc query **NOT EXISTS** nếu nghiệp vụ yêu cầu.

### Bài 14. Tìm tên chứa dấu % literal

Người dùng tìm Product có tên chứa đúng chuỗi **20% OFF**.

Viết:
1. JPQL LIKE với **ESCAPE '!'**;
2. Hàm escape ký tự **!**, **%**, **_** trong input;
3. Bind pattern có wildcard ở hai đầu.

Giải thích vì sao vừa cần parameter binding, vừa cần escape wildcard theo semantics LIKE.

### Bài 15. Tìm không phân biệt hoa/thường

Viết query tìm Product có tên chứa **wireless**, bất kể chữ hoa/chữ thường. Dùng **LOWER** và named parameter. Nếu dữ liệu chứa tiếng Việt có dấu, tại sao kết quả có thể còn phụ thuộc collation/Unicode?

### Bài 16. Tìm đơn hàng theo khoảng thời gian

Một Order có createdAt kiểu Instant. Người dùng muốn tất cả Order trong ngày 15/11 theo timezone cửa hàng. Thiết kế khoảng **[startOfDay, startOfNextDay)** và JPQL:

~~~java
where o.createdAt >= :start
  and o.createdAt < :end
~~~

Tại sao cách này thường an toàn hơn BETWEEN với “23:59:59.999”? Những điều gì phải xác định khi chuyển LocalDate sang Instant?

### Bài 17. Dùng COALESCE có chủ đích

Một báo cáo coi stockQuantity NULL là 0. Viết query có **COALESCE** để tìm những Product mà số tồn kho quy đổi là 0.

Sau đó giải thích tại sao trong báo cáo chất lượng dữ liệu, nên dùng **IS NULL** riêng để phân biệt “không có số liệu” với “thực sự hết hàng”.

### Bài 18. Xây Criteria API có điều kiện

Nhận input:
- minPrice tùy chọn;
- maxPrice tùy chọn;
- active tùy chọn;
- onlyUncategorized boolean.

Hãy tạo danh sách Predicate, chỉ thêm giới hạn giá khi parameter khác null, dùng **cb.isNull** để lọc Category NULL và **cb.and** để kết hợp.

Giải thích vì sao **cb.equal(path, null)** không phải lựa chọn nên dùng thay cho cb.isNull.

### Bài 19. Tối ưu một màn hình tìm kiếm

Màn hình có 20 filter tùy chọn trên bảng nhiều triệu Product. Developer viết một @Query rất dài với **(:param IS NULL OR ...)** cho tất cả filter.

Hãy phân tích:
- Độ rõ của semantics;
- Type inference cho parameter NULL;
- Kế hoạch dùng index;
- Khả năng xây SQL tối ưu từ Criteria/Specification;
- Cách đo bằng EXPLAIN và thống kê DB;
- Yêu cầu luôn áp tenant/soft-delete filters.

Không kết luận kiểu “OR luôn chậm”; đề xuất cách đo phù hợp.

### Bài 20. Kiểm thử bộ lọc không bị sai bởi NULL

Thiết kế test fixtures với:
- một Product price NULL;
- một Product stock 0;
- một Product stock NULL;
- một Product category NULL;
- một Product active true nhưng deletedAt khác NULL;
- một Product name chứa ký tự %.

Viết test case cho **IS NULL, NOT, AND/OR precedence, LEFT JOIN** và **LIKE ESCAPE**, rồi giải thích vì sao chỉ dùng test fixture có đầy đủ giá trị khác NULL sẽ bỏ sót bug.

### Bài 21. Soft delete và tenant isolation

Hệ thống nhiều tenant có Product. Yêu cầu:
- chỉ trả records thuộc tenant đã xác thực;
- luôn loại deletedAt khác NULL;
- người dùng được chọn minPrice tùy ý.

Hãy viết JPQL với điều kiện bắt buộc **tenantId** và **deletedAt IS NULL**, trong khi minPrice được bỏ qua khi không cung cấp. Tại sao không được lấy tenantId từ request rồi cho user sửa tùy ý?

### Bài 22. Sắp xếp giá và NULL ổn định

Viết JPQL lấy tất cả Product, sắp theo:
1. giá khác NULL trước;
2. giá tăng dần;
3. ID tăng dần khi giá bằng nhau;
4. giá NULL ở cuối.

Dùng **CASE WHEN p.price IS NULL THEN 1 ELSE 0 END** trong ORDER BY. Giải thích vì sao không thể luôn dựa vào thứ tự NULL mặc định giữa các DB.

### Bài 23. Truy vấn “không có child”

Category có mapped collection products. Viết:
1. **c.products IS EMPTY**;
2. một correlated **NOT EXISTS**.

Giải thích vì sao **c.products IS NULL** không phải phép kiểm tra collection rỗng phù hợp và vì sao **NOT IN** có thể gây rắc rối khi tập subquery chứa NULL.

### Bài 24. Chọn đúng cách khi yêu cầu mơ hồ

Bộ phận kinh doanh nói: “Lấy những mặt hàng không đắt và không thuộc Electronics”. Hãy hỏi rõ hai điểm:
- Price NULL có được coi là “không đắt” không?
- Category NULL có được coi là “không thuộc Electronics” không?

Viết hai truy vấn khác nhau cho hai cách hiểu (loại NULL và bao gồm NULL), dùng LEFT JOIN khi cần. Đây là bài tập mô hình hóa **nghĩa nghiệp vụ** trước khi chọn toán tử.

## 23. Bảng tra cứu nhanh

| Yêu cầu | Mẫu JPQL |
|---|---|
| Bằng giá trị | p.code = :code |
| Khác giá trị | p.code <> :code |
| Lớn hơn | p.price > :threshold |
| Lớn hơn hoặc bằng | p.price >= :minimum |
| Nhỏ hơn | p.price < :maximum |
| Nhỏ hơn hoặc bằng | p.price <= :maximum |
| Cùng thỏa hai điều kiện | conditionA AND conditionB |
| Thỏa ít nhất một điều kiện | conditionA OR conditionB |
| Phủ định điều kiện | NOT (condition) |
| Nhóm logic | (A OR B) AND C |
| NULL | p.price IS NULL |
| Không NULL | p.price IS NOT NULL |
| Khoảng bao gồm hai biên | p.price BETWEEN :min AND :max |
| Không nằm trong khoảng | p.price NOT BETWEEN :min AND :max |
| Nằm trong tập | p.code IN :codes |
| Không nằm trong tập | p.code NOT IN :codes |
| Bắt đầu bằng mẫu | p.name LIKE :prefixPattern |
| Chứa mẫu | p.name LIKE :containsPattern |
| Escape wildcard | p.name LIKE :pattern ESCAPE '!' |
| Association không gán | p.category IS NULL |
| Association đã gán | p.category IS NOT NULL |
| Collection không phần tử | c.products IS EMPTY |
| Có ít nhất một child phù hợp | EXISTS (subquery) |
| Không có child phù hợp | NOT EXISTS (subquery) |
| Giá trị thay thế NULL | COALESCE(p.stockQuantity, 0) |
| Null nếu hai biểu thức bằng nhau | NULLIF(a, b) |
| Chỉ apply filter khi parameter có giá trị | Tạo predicate động hoặc :p IS NULL OR ... |

Bảng này là ký pháp minh họa. Khi viết query hoàn chỉnh cần có **SELECT ... FROM ...** và bind parameters đúng type; nhiều mẫu ở đây không thể dùng một mình như câu JPQL độc lập.

## 24. Checklist trước khi đưa bộ lọc JPQL vào ứng dụng

1. **Đã dùng entity/property names chưa?** JPQL dùng Product.price, không dùng products.unit_price.
2. **Toán tử có đúng ngưỡng không?** Kiểm tra > so với >=, < so với <=.
3. **Đã bao ngoặc khi kết hợp AND/OR chưa?** Tránh precedence thay đổi semantics.
4. **Có NULL nào ảnh hưởng kết quả không?** So sánh NULL dẫn tới UNKNOWN.
5. **Đã dùng IS NULL / IS NOT NULL chưa?** Không dùng = NULL hoặc <> NULL.
6. **NOT có cần bao gồm các row NULL không?** NOT UNKNOWN vẫn UNKNOWN.
7. **Danh sách IN có rỗng hoặc chứa NULL không?** Quy định semantics trước khi bind.
8. **NOT IN có thể gặp NULL không?** Cân nhắc NOT EXISTS hoặc validation.
9. **BETWEEN có đúng ranh giới inclusive không?** Với ngày giờ cân nhắc [start, end).
10. **LIKE có cần escape % và _ từ input không?** Parameter binding không tự escape wildcard.
11. **Case/diacritics có cần chuẩn hóa không?** Kiểm tra collation/Unicode/locale.
12. **Parameter NULL có nghĩa gì?** Bỏ filter, tìm NULL, hay invalid?
13. **Có navigation qua association nullable không?** Xem implicit join và LEFT JOIN.
14. **Điều kiện ON/WHERE có làm thay đổi outer join không?** Kiểm tra tập row thực tế.
15. **Collection rỗng và scalar NULL có bị nhầm không?** Dùng IS EMPTY cho collection.
16. **Boolean nullable có ba trạng thái nghiệp vụ không?** Không tự coi NULL là false.
17. **Có DTO/query dynamic an toàn không?** Không map partial DTO thành entity rồi dựa vào magic filter.
18. **Tenant/authorization/soft delete đã áp bắt buộc chưa?** Không để filter bảo mật thành tùy chọn.
19. **Có hạn chế số row trả về không?** Pagination, order ổn định, tránh load toàn DB.
20. **Có nguy cơ N+1 không?** Filter association không tự fetch dữ liệu association.
21. **DB indexes và kế hoạch query có phù hợp không?** Đo với dữ liệu thực.
22. **Đã có integration test với NULL/boundary/wildcard chưa?** Test cả trường hợp dữ liệu thiếu.
23. **SQL/dialect có đặc thù cần ghi chú không?** Không mặc định mọi provider có cùng extension.
24. **Kết quả có đúng định nghĩa nghiệp vụ không?** Đặc biệt các yêu cầu “không phải”, “không đắt”, “chưa gán”, “chưa hết hạn”.

### 24.1. Sơ đồ quyết định nhanh khi lọc một thuộc tính

~~~text
Cần lọc thuộc tính X
        |
        +-- X không được phép NULL?
        |       |
        |       +-- So sánh bằng/ngưỡng/khoảng/tập/mẫu
        |           với parameter đúng type và ngữ nghĩa
        |
        +-- X có thể NULL?
                |
                +-- Tìm đúng những row thiếu X?
                |       → X IS NULL
                |
                +-- Tìm những row có X?
                |       → X IS NOT NULL
                |
                +-- So sánh X với giá trị V?
                |       → X <op> :value
                |         nhớ rằng X NULL → UNKNOWN
                |
                +-- Có cần bao gồm X NULL khi phủ định?
                |       → (điều kiện phủ định) OR X IS NULL
                |
                +-- Parameter V có thể NULL?
                        |
                        +-- NULL nghĩa "bỏ lọc"?
                        |       → bỏ predicate động
                        |         hoặc :v IS NULL OR ...
                        |
                        +-- NULL nghĩa "tìm X NULL"?
                        |       → X IS NULL
                        |
                        +-- NULL không hợp lệ?
                                → validate trước query
~~~

### 24.2. Ví dụ hoàn chỉnh kết hợp các chủ điểm

Yêu cầu:
- Chỉ lấy Product **chưa xóa mềm**;
- Có thể lọc **giá tối thiểu/tối đa**;
- Có thể lọc **tên chứa một chuỗi**;
- Có thể chọn **chỉ sản phẩm chưa gán danh mục**;
- Sắp theo **giá khác NULL trước**, sau đó theo giá và ID.

Một phiên bản query tĩnh cho điều kiện giá và tên, với category filter được chọn trước từ service:

~~~java
String jpql = """
    select p
    from Product p
    where p.deletedAt is null
      and (:minPrice is null or p.price >= :minPrice)
      and (:maxPrice is null or p.price <= :maxPrice)
      and (:pattern is null or lower(p.name) like :pattern escape '!')
    order by
      case when p.price is null then 1 else 0 end asc,
      p.price asc,
      p.id asc
    """;

// Nếu chỉ tìm Product chưa gán Category, thêm predicate
// "and p.category is null" vào WHERE trước ORDER BY bằng
// query builder/Criteria thay vì nối sau ORDER BY.
~~~

Khi form có nhiều tổ hợp tùy chọn, nên dùng Criteria API để tạo đúng các predicates; đoạn trên chỉ minh họa các biểu thức WHERE/ORDER BY. **pattern** phải được tạo bằng hàm escapeLike và chuẩn hóa hoa/thường nếu có input, hoặc bind null để bỏ filter theo thiết kế. Với category filter, đừng ghép chuỗi sau ORDER BY; chọn query shape/Criteria ngay từ đầu.

Một ví dụ Criteria ở phần 15 đã trình bày cách chủ động thêm bộ lọc dựa trên tham số hiện hữu và giữ bắt buộc **p.deletedAt IS NULL**.

## 25. Tổng kết

Lọc dữ liệu trong JPQL là việc diễn đạt **những hàng nào thuộc tập kết quả** ở tầng entity model. Các toán tử **=, <>, >, >=, <, <=, BETWEEN, IN và LIKE** giúp so sánh thuộc tính; **AND, OR, NOT** giúp kết hợp điều kiện; **IS NULL / IS NOT NULL** giúp xử lý sự thiếu vắng giá trị một cách chính xác.

Ba nguyên tắc quan trọng nhất:

~~~text
1. JPQL dùng entity và thuộc tính Java.
   FROM Product p WHERE p.price >= :minimum

2. NULL không hoạt động như một giá trị bình thường.
   p.price = NULL       → không phải cách kiểm tra NULL
   p.price IS NULL      → đúng
   NOT UNKNOWN          → vẫn UNKNOWN
   WHERE chỉ giữ TRUE

3. Nghĩa của filter phải được định nghĩa trước cú pháp.
   Parameter null = bỏ lọc? tìm NULL? hay invalid?
   "không thuộc X" có gồm chưa gán X không?
   "chưa vượt giá" có gồm chưa có giá không?
~~~

Khi biểu thức bắt đầu có nhiều điều kiện tùy chọn, association nullable hoặc tính chất bảo mật, hãy chủ động sử dụng dấu ngoặc, parameter binding, **LEFT JOIN** khi cần bảo toàn row chưa liên kết, và **Criteria API** để xây predicate đúng nghĩa. Cuối cùng, xác minh bộ lọc bằng integration tests có dữ liệu **NULL**, giá trị ranh giới và chuỗi chứa wildcard để tránh những kết quả sai âm thầm mà một câu JPQL vẫn có thể chạy thành công.







