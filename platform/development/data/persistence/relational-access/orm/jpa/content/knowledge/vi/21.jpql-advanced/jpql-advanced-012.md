# Ánh xạ trực tiếp kết quả bằng biểu thức khởi tạo DTO trong JPQL

## 1. Vấn đề: truy vấn chỉ cần vài trường nhưng ứng dụng lại tải cả entity

Trong Jakarta Persistence (JPA), câu truy vấn **select p from Product p** thường trả về các entity Product được quản lý trong **persistence context**. Tuy nhiên, nhiều màn hình và API chỉ cần một tập nhỏ các cột: ID, mã sản phẩm, tên, tên danh mục, giá hoặc một số thống kê.

Ví dụ danh sách sản phẩm chỉ hiển thị:

~~~text
+------+----------+------------------+----------------+-----------+
| ID   | SKU      | Tên              | Danh mục       | Giá       |
+------+----------+------------------+----------------+-----------+
| 101  | KB-001   | Bàn phím cơ      | Phụ kiện       | 890000.00 |
| 102  | MS-002   | Chuột không dây  | Phụ kiện       | 320000.00 |
+------+----------+------------------+----------------+-----------+
~~~

Nếu dùng:

~~~java
List<Product> products = em.createQuery(
    "select p from Product p",
    Product.class
).getResultList();
~~~

ứng dụng có thể phải materialize Product như một entity, quản lý identity, theo dõi trạng thái và có khả năng kích hoạt tải thêm các association khi đọc danh mục. Để trả API, service thường lại chuyển Product sang DTO.

JPA có một cách khác: **JPQL constructor expression**, hay **biểu thức khởi tạo DTO trực tiếp**:

~~~jpql
select new com.example.catalog.dto.ProductRow(
    p.id,
    p.sku,
    p.name,
    c.name,
    p.price
)
from Product p
left join p.category c
~~~

Provider đọc những biểu thức trong danh sách SELECT, sau đó gọi **constructor phù hợp** của ProductRow để tạo object kết quả. Không cần tự lấy từng phần tử của Object[] rồi ép kiểu.

> Trọng tâm của bài: dùng **SELECT NEW** trong JPQL để ánh xạ trực tiếp kết quả truy vấn thành DTO, hiểu chính xác chữ ký constructor, cách dùng JOIN, tập hợp, GROUP BY, phân trang và giới hạn của phép projection này.

## 2. DTO là gì và vì sao dùng trong truy vấn?

**Data Transfer Object (DTO)** là object mô tả dữ liệu cần chuyển giữa các tầng hoặc trả về cho một use case. DTO **không cần** được khai báo @Entity và thông thường không có quan hệ quản lý vòng đời với persistence context.

Ví dụ:

~~~java
package com.example.catalog.dto;

import java.math.BigDecimal;

public record ProductRow(
    Long id,
    String sku,
    String name,
    String categoryName,
    BigDecimal price
) {}
~~~

Đây là một **Java record** (Java 16+). Record có constructor nhận các component theo đúng thứ tự đã khai báo, cùng accessor như id(), sku() và name(). Với Java cũ, có thể dùng một class thông thường với constructor tương ứng.

DTO có thể đem lại lợi ích:

- **Chọn đúng dữ liệu:** tránh mang theo những cột/association không dùng trong danh sách.
- **Hợp đồng API rõ:** không phơi toàn bộ thuộc tính và quan hệ nội bộ của entity.
- **Không cần dirty checking cho bản thân DTO:** DTO chỉ là object Java, không phải managed entity.
- **Giảm mã ánh xạ cơ học:** JPQL dựng DTO trực tiếp thay vì trả Object[] rồi gọi new thủ công.
- **Dễ tối ưu theo màn hình:** mỗi truy vấn có thể chọn phép JOIN, filter và aggregate phù hợp.

DTO không phải giải pháp tự động cho mọi vấn đề hiệu năng. Nếu SELECT vẫn chứa nhiều cột, JOIN sai, trả hàng triệu kết quả hoặc query thiếu index, constructor expression không giúp hệ thống nhanh một cách thần kỳ.

## 3. Mô hình entity làm ví dụ

Ta dùng Product thuộc một Category; Category có thể có nhiều Product.

~~~text
Category                           Product
--------------------               --------------------------
id (PK)              <------------- category_id (FK)
name                                id (PK)
                                    sku
                                    name
                                    price
                                    status
~~~

### 3.1. Category

~~~java
package com.example.catalog.model;

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

    @Column(nullable = false, unique = true, length = 100)
    private String name;

    protected Category() {}

    public Category(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
~~~

### 3.2. Product

~~~java
package com.example.catalog.model;

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

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 180)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ProductStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {}

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public ProductStatus getStatus() { return status; }
    public Category getCategory() { return category; }
}
~~~

### 3.3. Enum

~~~java
package com.example.catalog.model;

public enum ProductStatus {
    ACTIVE,
    INACTIVE
}
~~~

Các class Java trên giả định đã có constructor/factory phục vụ việc tạo dữ liệu test và cấu hình EntityManagerFactory tương ứng. Ví dụ truy vấn chỉ phụ thuộc vào **các thuộc tính được ánh xạ**, không đòi hỏi getter cho mọi field trong DTO.

## 4. Cú pháp SELECT NEW trong JPQL

Cú pháp thường gặp:

~~~jpql
select new ten.package.DayDuCuaDTO(
    bieuThuc1,
    bieuThuc2,
    bieuThuc3
)
from TenEntity alias
where dieuKien
~~~

Ví dụ:

~~~java
String jpql = """
    select new com.example.catalog.dto.ProductRow(
        p.id,
        p.sku,
        p.name,
        c.name,
        p.price
    )
    from Product p
    left join p.category c
    where p.status = :status
    order by p.name asc, p.id asc
    """;

List<ProductRow> rows = em.createQuery(
    jpql, ProductRow.class
).setParameter("status", ProductStatus.ACTIVE)
 .getResultList();
~~~

Đoạn Java dùng text block (Java 15+). Nếu ứng dụng dùng Java cũ hơn, nối chuỗi JPQL hoặc dùng String thông thường. Các import tương ứng: **com.example.catalog.dto.ProductRow**, **com.example.catalog.model.ProductStatus**, **jakarta.persistence.EntityManager** và các lớp Java Collection.

### 4.1. Dùng tên entity và thuộc tính Java, không dùng tên bảng/cột SQL

Trong JPQL:

~~~jpql
from Product p
left join p.category c
~~~

**Product** là tên entity của JPA, **category** là thuộc tính ánh xạ của Product, **name** là thuộc tính Java của Category. Không viết SQL như:

~~~sql
-- Đây là SQL, không phải JPQL:
FROM products p LEFT JOIN categories c ON p.category_id = c.id
~~~

JPQL để provider chuyển đường dẫn quan hệ thành JOIN theo mapping; SQL native dùng tên bảng/cột thật.

### 4.2. Tên class DTO phải xác định được

Trong constructor expression JPA chuẩn, nên dùng **tên class được định danh đầy đủ bằng package**:

~~~jpql
select new com.example.catalog.dto.ProductRow(...)
~~~

Không nên trông chờ một alias ngắn như **new ProductRow(...)** được mọi provider tự hiểu qua import Java. Chuỗi JPQL không kế thừa import của class chứa nó. Một số framework/provider có thể hỗ trợ cú pháp mở rộng hoặc rewrite query, nhưng ví dụ portable nên dùng fully qualified class name.

### 4.3. Thứ tự và kiểu của tham số phải khớp constructor

DTO mẫu:

~~~java
public record ProductRow(
    Long id,
    String sku,
    String name,
    String categoryName,
    BigDecimal price
) {}
~~~

Danh sách SELECT tương ứng:

~~~jpql
new com.example.catalog.dto.ProductRow(
    p.id,       -- Long
    p.sku,      -- String
    p.name,     -- String
    c.name,     -- String hoặc null
    p.price     -- BigDecimal
)
~~~

Nếu đảo c.name và p.price, provider không tìm được constructor có kiểu phù hợp ở vị trí thứ tư/thứ năm. Nếu đổi **Long id** thành **Integer id** nhưng mapping entity vẫn là Long, provider cũng có thể báo lỗi khởi tạo.

Với các kiểu giống nhau ở nhiều vị trí, query có thể chạy nhưng trả giá trị bị **đảo cột theo ngữ nghĩa**. Ví dụ cả sku và name đều String, đảo vị trí có thể không ném exception nhưng DTO nhận sai trường. Vì vậy constructor expression phải được viết và bảo trì đồng bộ với chữ ký DTO.

### 4.4. Constructor phải truy cập được

Với class DTO thông thường, nên khai báo **public class** cùng **public constructor** tương ứng. Ví dụ:

~~~java
package com.example.catalog.dto;

import java.math.BigDecimal;

public final class ProductRow {

    private final Long id;
    private final String sku;
    private final String name;
    private final String categoryName;
    private final BigDecimal price;

    public ProductRow(
        Long id,
        String sku,
        String name,
        String categoryName,
        BigDecimal price
    ) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.categoryName = categoryName;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public String getCategoryName() { return categoryName; }
    public BigDecimal getPrice() { return price; }
}
~~~

Đây là **phương án thay thế record**, không khai báo đồng thời hai class cùng tên/package trong cùng project. Một Java record phù hợp cũng có canonical constructor public khi record public.

Một số module Java dùng JPMS; khi đó cần đảm bảo package DTO có khả năng được provider truy cập theo cấu hình modules. Việc provider cố dùng reflection có thể bị giới hạn bởi module boundaries, đặc biệt nếu dùng constructor hoặc class không public.

## 5. So sánh SELECT NEW với Object[] và Tuple

### 5.1. Cách thủ công với Object[]

~~~java
List<Object[]> result = em.createQuery(
    "select p.id, p.sku, p.name, c.name, p.price " +
    "from Product p left join p.category c",
    Object[].class
).getResultList();

List<ProductRow> rows = new ArrayList<>();
for (Object[] row : result) {
    rows.add(new ProductRow(
        (Long) row[0],
        (String) row[1],
        (String) row[2],
        (String) row[3],
        (BigDecimal) row[4]
    ));
}
~~~

Cách này có nhiều phép ép kiểu và index vị trí. Khi SELECT thêm hoặc đổi cột, mã ánh xạ dễ bị sai. Nếu nhiều query dùng các cấu trúc khác nhau, việc duy trì index thủ công còn khó hơn.

### 5.2. Cách dùng Tuple

~~~java
List<Tuple> result = em.createQuery(
    "select p.id as productId, p.name as productName, " +
    "p.price as price from Product p",
    Tuple.class
).getResultList();

for (Tuple row : result) {
    Long id = row.get("productId", Long.class);
    String name = row.get("productName", String.class);
    BigDecimal price = row.get("price", BigDecimal.class);
}
~~~

**Tuple** hỗ trợ đọc kết quả theo alias và kiểu, thuận tiện cho những query động. Nhưng service vẫn cần tạo DTO nếu API muốn trả object có kiểu rõ.

### 5.3. Cách dùng SELECT NEW

~~~java
List<ProductRow> rows = em.createQuery(
    "select new com.example.catalog.dto.ProductRow(" +
    "p.id, p.sku, p.name, c.name, p.price) " +
    "from Product p left join p.category c",
    ProductRow.class
).getResultList();
~~~

Không cần Object[] hoặc Tuple trung gian **ở mã ứng dụng**. Provider vẫn thực hiện ánh xạ result set và dựng DTO bên trong.

| Đặc điểm | Entity result | Object[] | Tuple | Constructor DTO |
|---|---|---|---|---|
| Kiểu kết quả | Entity JPA | Object[] | Tuple | DTO/class/record |
| Entity được managed | Có, nếu select entity | Không đối với scalar arrays | Không đối với scalar Tuple | Không đối với chính DTO |
| Chỉ chọn vài cột | Không nếu select entity đầy đủ | Có | Có | Có |
| Ánh xạ theo vị trí | Không cần ở service | Có | Có thể đọc bằng alias | Constructor dùng thứ tự |
| Mã ép kiểu trong service | Thường không | Nhiều | Ít hơn | Ít |
| Phù hợp API response | Cần cân nhắc data exposure | Thường phải map | Thường phải map | Thường phù hợp |
| Thay đổi query và constructor | Không áp dụng | Sửa index thủ công | Sửa alias/mapping | Sửa chữ ký và danh sách SELECT |

**SELECT NEW không làm DTO trở thành entity.** Trừ trường hợp DTO được chính bạn khai báo @Entity và dùng làm entity result theo mapping khác, một class DTO thông thường chỉ là object Java sau query.

## 6. JOIN trực tiếp để lấy thông tin từ quan hệ

Khi DTO cần tên category, JPQL có thể JOIN qua association:

~~~jpql
select new com.example.catalog.dto.ProductRow(
    p.id, p.sku, p.name, c.name, p.price
)
from Product p
left join p.category c
where p.status = :status
~~~

### 6.1. INNER JOIN và LEFT JOIN khác nhau

**INNER JOIN**:

~~~jpql
from Product p join p.category c
~~~

chỉ trả Product có Category tương ứng thỏa JOIN. Nếu Product.category là optional và null, Product đó bị loại khỏi kết quả.

**LEFT JOIN**:

~~~jpql
from Product p left join p.category c
~~~

giữ cả Product không có Category; lúc đó **c.name** trong projection nhận **null**.

Với DTO:

~~~java
public record ProductRow(
    Long id,
    String sku,
    String name,
    String categoryName,
    BigDecimal price
) {}
~~~

categoryName là **String có thể null**. Nếu constructor yêu cầu một giá trị không-null hoặc biến đổi categoryName bằng một lời gọi không kiểm tra null, query có thể ném exception khi gặp Product không có Category.

### 6.2. Trường hợp cần giá trị thay thế với COALESCE

~~~jpql
select new com.example.catalog.dto.ProductRow(
    p.id,
    p.sku,
    p.name,
    coalesce(c.name, 'Chưa phân loại'),
    p.price
)
from Product p left join p.category c
~~~

Hàm **COALESCE** trả biểu thức khác null đầu tiên, giúp DTO nhận một chuỗi mặc định khi Category không tồn tại. Đây là một yêu cầu về hợp đồng giao diện; không tự làm thay đổi Product.category trong database.

### 6.3. Không đặt filter LEFT JOIN sai chỗ

Ví dụ:

~~~jpql
select new com.example.catalog.dto.ProductRow(
    p.id, p.sku, p.name, c.name, p.price
)
from Product p left join p.category c
where c.name = :categoryName
~~~

Điều kiện **c.name = :categoryName** loại các hàng không có category, khiến kết quả **tương tự INNER JOIN** đối với điều kiện đó. Nếu muốn giữ sản phẩm chưa phân loại, cần thiết kế predicate có chủ đích:

~~~jpql
where c.name = :categoryName or c is null
~~~

Trên một số mô hình/query, có thể dùng điều kiện ON ở JOIN hoặc cấu trúc WHERE khác; cần hiểu ngữ nghĩa WHERE sau LEFT JOIN, không giả định LEFT JOIN luôn giữ tất cả hàng bất kể WHERE.

### 6.4. Tránh implicit inner join không mong muốn

JPQL đường dẫn:

~~~jpql
select p.category.name from Product p
~~~

có thể dẫn tới **implicit inner join** theo ngữ nghĩa điều hướng single-valued association. Nếu Product.category optional và muốn cả product không có category, dùng **left join p.category c** và chọn **c.name** một cách tường minh.

## 7. WHERE, tham số và ORDER BY với constructor DTO

Ví dụ một truy vấn danh sách sản phẩm theo giá:

~~~java
String jpql =
    "select new com.example.catalog.dto.ProductRow(" +
    "p.id, p.sku, p.name, c.name, p.price) " +
    "from Product p left join p.category c " +
    "where p.status = :status " +
    "and p.price between :minPrice and :maxPrice " +
    "order by p.price asc, p.id asc";

List<ProductRow> rows = em.createQuery(
    jpql, ProductRow.class
).setParameter("status", ProductStatus.ACTIVE)
 .setParameter("minPrice", new BigDecimal("100000.00"))
 .setParameter("maxPrice", new BigDecimal("1500000.00"))
 .getResultList();
~~~

**Lưu ý:** tham số là **giá trị**, không phải tên thuộc tính, tên bảng hoặc hướng ORDER BY tùy ý. Khi xây dựng API tìm kiếm động, không nối thẳng tên cột hoặc chuỗi sort do client gửi vào JPQL mà chưa kiểm soát. Nên dùng whitelist các trường và hướng sắp xếp hợp lệ hoặc Criteria API nếu câu query động phức tạp.

### 7.1. Dùng named parameters

~~~jpql
where p.sku = :sku
~~~

và:

~~~java
.setParameter("sku", requestedSku)
~~~

giúp truyền dữ liệu một cách có kiểu và không cần tự escape chuỗi bằng cách nối literal. Nhưng điều đó không thay thế việc validate độ dài, phạm vi giá hoặc quyền truy cập.

### 7.2. Thứ tự ổn định khi phân trang

Nếu chỉ:

~~~jpql
order by p.price
~~~

hai sản phẩm có cùng price không có thứ tự xác định giữa nhau. Khi dùng phân trang, thêm khóa phụ ổn định:

~~~jpql
order by p.price asc, p.id asc
~~~

nhằm giảm khả năng sản phẩm xuất hiện lặp hoặc bị bỏ sót do thứ tự không ổn định. Nếu dữ liệu bị ghi đồng thời giữa các lần gọi API, phân trang OFFSET vẫn có thể bị dịch chuyển; có thể cân nhắc keyset pagination và cơ chế snapshot/consistency tùy yêu cầu.

## 8. Biểu thức tính toán trong constructor

Constructor expression không bị giới hạn ở việc chọn field nguyên bản. Có thể truyền các biểu thức scalar phù hợp với JPQL và kiểu constructor.

### 8.1. CASE WHEN

Ví dụ DTO hiển thị mức giá:

~~~java
package com.example.catalog.dto;

public record ProductPriceLabel(
    Long id,
    String name,
    String priceLevel
) {}
~~~

Query:

~~~jpql
select new com.example.catalog.dto.ProductPriceLabel(
    p.id,
    p.name,
    case
        when p.price >= :premiumThreshold then 'PREMIUM'
        when p.price >= :standardThreshold then 'STANDARD'
        else 'BUDGET'
    end
)
from Product p
~~~

Cách truyền tham số:

~~~java
List<ProductPriceLabel> rows = em.createQuery(
    jpql, ProductPriceLabel.class
).setParameter("premiumThreshold", new BigDecimal("3000000"))
 .setParameter("standardThreshold", new BigDecimal("1000000"))
 .getResultList();
~~~

CASE trả String ở mọi nhánh, phù hợp trường **String priceLevel**. Nếu các nhánh CASE trả kiểu khác nhau, provider/DB có thể không tìm được kiểu kết quả thống nhất.

### 8.2. CONCAT, LOWER và các hàm chuỗi

~~~java
public record ProductSearchRow(
    Long id,
    String searchableName
) {}
~~~

~~~jpql
select new com.example.catalog.dto.ProductSearchRow(
    p.id,
    lower(concat(p.sku, ' - ', p.name))
)
from Product p
~~~

Lưu ý: các hàm JPQL được hỗ trợ tùy phiên bản Jakarta Persistence, và một số hàm phụ thuộc dialect khi dịch sang SQL. Với hàm riêng DBMS, có thể dùng FUNCTION('function_name', ...) nếu provider/dialect hỗ trợ và kiểu kết quả được xác định đúng. **Tính di động không tuyệt đối** nếu query dựa trên extension.

### 8.3. Biểu thức số

Giả sử Product có **price** BigDecimal và **discountPercent** BigDecimal; có thể tính giá dự kiến qua các phép toán:

~~~jpql
select new com.example.catalog.dto.ProductDiscountRow(
    p.id,
    p.name,
    p.price,
    p.price * (1 - p.discountPercent / 100)
)
from Product p
~~~

Đây là biểu thức minh họa nếu trường discountPercent thực sự tồn tại và có kiểu phù hợp trong entity. Khi làm việc với BigDecimal, cần kiểm tra **kiểu trả về, phép chia và precision/scale của DBMS**. Một phép tính tiền tệ có quy tắc rounding nghiệp vụ nên được kiểm thử rõ ràng; đừng mặc định mọi DB sẽ làm tròn giống BigDecimal trong Java.

## 9. Kiểu dữ liệu và constructor resolution

Chữ ký constructor là phần quan trọng nhất của SELECT NEW. JPA phải xác định được **số đối số, thứ tự, kiểu và khả năng gọi constructor**.

| Biểu thức JPQL | Kiểu Java thường gặp | Lưu ý |
|---|---|---|
| **p.id** khi @Id Long | Long | Không tự thay bằng Integer |
| **p.sku**, **p.name** | String | Nullability tùy cột/JOIN |
| **p.price** khi BigDecimal | BigDecimal | Phù hợp tiền tệ hơn Double |
| **p.status** là enum | ProductStatus | Không phải String nếu chưa chuyển đổi |
| **count(p)** | Long | Không dùng int/Integer tùy tiện |
| **sum(x)** trên số nguyên | Long theo quy tắc JPQL | Có thể null nếu nhóm không có giá trị |
| **sum(x)** trên Double/Float | Double | Kiểu theo đặc tả |
| **sum(x)** trên BigDecimal | BigDecimal | Tránh ép BigDecimal sang Long |
| **avg(x)** | Double | Kể cả khi đầu vào là kiểu số nguyên |
| **max(x)**, **min(x)** | Kiểu so sánh của biểu thức | Tùy property được aggregate |
| **coalesce(c.name, 'N/A')** | String | Khớp constructor String |
| **case ... then 'A' else 'B' end** | String | Các nhánh phải tương thích |

Theo ngữ nghĩa JPQL, **COUNT** trả Long; **AVG** trả Double; **SUM** có quy tắc kiểu dựa trên kiểu số của biểu thức đầu vào (Long đối với số nguyên không BigInteger, BigInteger với BigInteger, BigDecimal với BigDecimal, Double với kiểu dấu phẩy động). Tham số của constructor DTO nên phản ánh **kiểu Java trả về của biểu thức JPQL**, không chỉ kiểu cột SQL nhìn bằng mắt.

### 9.1. Wrapper hay primitive?

Giả sử Category là optional. Nếu SELECT lấy:

~~~jpql
select new com.example.catalog.dto.ProductCategoryInfo(
    p.id, c.id
)
from Product p left join p.category c
~~~

với DTO:

~~~java
public record ProductCategoryInfo(Long productId, Long categoryId) {}
~~~

categoryId có thể null, nên dùng **Long**. Nếu constructor nhận **long** primitive ở vị trí này, provider không thể truyền null vào primitive mà không có lỗi hoặc hành vi không mong muốn.

Với phép tổng hợp SUM có thể trả null khi không có giá trị tương ứng, DTO cũng nên dùng wrapper/BigDecimal thay vì primitive trừ khi query đã đảm bảo giá trị không null.

### 9.2. Enum không tự trở thành chuỗi

~~~java
public record ProductStatusRow(Long id, ProductStatus status) {}
~~~

~~~jpql
select new com.example.catalog.dto.ProductStatusRow(
    p.id, p.status
)
from Product p
~~~

**@Enumerated(EnumType.STRING)** chỉ hướng dẫn cách lưu enum xuống DB; trong JPQL type của p.status vẫn là **ProductStatus**, không mặc nhiên là String. Nếu muốn response String, DTO có thể giữ enum rồi chuyển trong API mapper hoặc dùng biểu thức trả chuỗi có chủ đích.

### 9.3. Constructor overload

Một class có nhiều constructor:

~~~java
public ProductRow(Long id, String name) { ... }
public ProductRow(Long id, String name, BigDecimal price) { ... }
~~~

có thể dùng nhiều loại projection tùy SELECT NEW. Nhưng các overload khác nhau chỉ ở kiểu wrapper/primitive hoặc thứ tự String giống nhau dễ gây lỗi khó hiểu. Khi DTO có những hình dạng dữ liệu rất khác, thường nên tạo **những DTO có tên phản ánh use case** thay vì nhiều constructor dễ bị gọi nhầm.

### 9.4. Record và public canonical constructor

~~~java
public record CategoryCount(String categoryName, Long count) {}
~~~

Record tạo canonical constructor tương ứng các component. Constructor expression có thể gọi constructor đó nếu provider/JPA runtime hỗ trợ loại class Java trên classpath. **Record không cần @Entity, getter kiểu JavaBean hay constructor không tham số** để dùng làm DTO projection.

Trong JPA entity, constructor không tham số có ý nghĩa riêng; đừng áp dụng nhầm yêu cầu constructor entity sang DTO record.

## 10. Constructor DTO kết hợp COUNT và GROUP BY

Một trong những ứng dụng quan trọng của SELECT NEW là **báo cáo thống kê**. Ví dụ cần số sản phẩm thuộc từng danh mục:

~~~java
package com.example.catalog.dto;

public record CategoryProductCount(
    Long categoryId,
    String categoryName,
    Long productCount
) {}
~~~

JPQL:

~~~jpql
select new com.example.catalog.dto.CategoryProductCount(
    c.id,
    c.name,
    count(p)
)
from Category c
left join Product p on p.category = c
group by c.id, c.name
order by c.name asc
~~~

Nếu Category có collection products được ánh xạ bằng @OneToMany, có thể thay bằng:

~~~jpql
select new com.example.catalog.dto.CategoryProductCount(
    c.id, c.name, count(p)
)
from Category c left join c.products p
group by c.id, c.name
order by c.name asc
~~~

**Hai câu trên là hai biến thể cho hai khả năng mapping.** Entity Category ở đầu bài chưa khai báo products collection nên ví dụ đầu dùng phép entity join với điều kiện ON khi provider/JPA version hỗ trợ; ví dụ thứ hai yêu cầu thêm một mapping @OneToMany(mappedBy="category") trong Category. Để tối đa khả năng tương thích với những phiên bản/provider không hỗ trợ unrelated entity joins đầy đủ, có thể dùng association join khi mapping tồn tại.

### 10.1. Vì sao dùng LEFT JOIN?

**LEFT JOIN** giữ Category chưa có Product, nên những danh mục không có sản phẩm vẫn xuất hiện. Khi dùng **count(p)**, các hàng mà p null **không được đếm**, do đó category trống có count bằng **0**.

Nếu dùng:

~~~jpql
count(c)
~~~

trên LEFT JOIN, mỗi Category không có Product vẫn có một hàng Category nên có thể được đếm là 1. Đối với số lượng sản phẩm, cần đếm **p**, không chỉ đếm **c**.

### 10.2. GROUP BY phải chứa biểu thức phi tổng hợp cần thiết

Trong truy vấn:

~~~jpql
select new com.example.catalog.dto.CategoryProductCount(
    c.id, c.name, count(p)
)
...
group by c.id, c.name
~~~

**c.id** và **c.name** là các biểu thức không aggregate, nên được đưa vào GROUP BY theo cách portable. Một số DB cho phép rút gọn GROUP BY dựa trên phụ thuộc hàm của primary key, nhưng không nên mặc định JPQL và mọi provider đều chấp nhận chỉ **group by c.id** nếu SELECT còn c.name.

### 10.3. COUNT trả Long

Không khai báo:

~~~java
public record CategoryProductCount(
    Long categoryId,
    String categoryName,
    Integer productCount
) {}
~~~

nếu JPQL truyền **count(p)**. Loại kết quả COUNT là **Long**, nên constructor nhận Long. Nếu cần số nhỏ trong UI, có thể chuyển về int sau khi kiểm tra overflow, nhưng không đổi tùy tiện kiểu constructor.

### 10.4. HAVING trong báo cáo

Ví dụ chỉ lấy những Category có ít nhất 5 sản phẩm:

~~~jpql
select new com.example.catalog.dto.CategoryProductCount(
    c.id, c.name, count(p)
)
from Category c left join c.products p
group by c.id, c.name
having count(p) >= :minimumProducts
order by count(p) desc, c.id asc
~~~

**HAVING** lọc các nhóm sau aggregate; **WHERE** lọc từng hàng trước khi GROUP BY. Điều này ảnh hưởng trực tiếp số lượng được đếm.

## 11. Báo cáo có SUM, AVG, MIN, MAX

Giả sử một module đơn hàng có:

~~~text
Customer
  id: Long
  name: String

PurchaseOrder
  id: Long
  orderNumber: String
  customer: Customer
  lines: List<OrderLine>

OrderLine
  id: Long
  quantity: Integer
  lineAmount: BigDecimal
  order: PurchaseOrder
~~~

**lineAmount** được xem là số tiền của một dòng đã tính theo nghiệp vụ, tránh phụ thuộc cách nhân số lượng × đơn giá trong JPQL cho ví dụ đầu tiên.

DTO thống kê một đơn hàng:

~~~java
package com.example.orders.dto;

import java.math.BigDecimal;

public record OrderSalesSummary(
    Long orderId,
    String orderNumber,
    String customerName,
    Long lineCount,
    BigDecimal amount
) {}
~~~

Query:

~~~jpql
select new com.example.orders.dto.OrderSalesSummary(
    o.id,
    o.orderNumber,
    c.name,
    count(l),
    coalesce(sum(l.lineAmount), :zero)
)
from PurchaseOrder o
join o.customer c
left join o.lines l
group by o.id, o.orderNumber, c.name
order by o.id desc
~~~

Và Java:

~~~java
List<OrderSalesSummary> summaries = em.createQuery(
    jpql, OrderSalesSummary.class
).setParameter("zero", BigDecimal.ZERO)
 .getResultList();
~~~

Giải thích:

- **join o.customer c** lấy tên khách hàng. Nếu đơn hàng có thể thiếu Customer mà vẫn phải xuất hiện, cân nhắc LEFT JOIN.
- **left join o.lines l** giữ các Order chưa có dòng.
- **count(l)** đếm số dòng thực tế, trả Long.
- **sum(l.lineAmount)** tổng số tiền, trả BigDecimal khi field tương ứng BigDecimal.
- **coalesce(sum(...), :zero)** thay tổng null bằng BigDecimal.ZERO cho đơn không có dòng.
- **group by** xác định một nhóm trên mỗi đơn hàng và customerName.

### 11.1. COUNT và SUM có thể bị nhân đôi do JOIN khác

Giả sử một PurchaseOrder có 3 OrderLine và 2 Coupon; query JOIN đồng thời:

~~~jpql
from PurchaseOrder o
left join o.lines l
left join o.coupons c
~~~

nếu cả hai association đều là to-many, kết quả SQL có thể có **3 × 2 = 6 hàng** cho một Order. Lúc đó **count(l) = 6** và **sum(l.lineAmount)** có thể bị nhân đôi.

Đây không phải lỗi của DTO constructor; vấn đề nằm ở **cardinality của JOIN** trước khi GROUP BY.

Các hướng xử lý:

- Chỉ JOIN những association thật sự cần.
- Tách thống kê lines và coupons thành các query riêng hoặc truy vấn đã aggregate.
- Sử dụng count(distinct l.id) khi chỉ cần số dòng duy nhất và ngữ nghĩa phù hợp.
- Với SUM, **sum(distinct l.lineAmount)** thường **không tương đương** tổng theo từng dòng vì hai dòng hợp lệ có thể cùng amount; không được dùng như cách sửa nhân bản hàng một cách máy móc.
- Có thể dùng native SQL/subquery/CTE hoặc summary table trong trường hợp báo cáo phức tạp, sau khi cân nhắc khả năng di động.

### 11.2. AVG trả Double

DTO:

~~~java
public record CategoryAveragePrice(
    Long categoryId,
    Double averagePrice
) {}
~~~

JPQL:

~~~jpql
select new com.example.catalog.dto.CategoryAveragePrice(
    c.id,
    avg(p.price)
)
from Category c
left join c.products p
group by c.id
~~~

**AVG** trong JPQL có kiểu Double. Đối với báo cáo tiền tệ cần precision chặt chẽ, nên cân nhắc tính tỷ lệ/average bằng BigDecimal sau khi lấy SUM và COUNT hoặc dùng phương án SQL thích hợp có kiểm soát rounding.

Nếu nhóm có 0 Product, AVG có thể null, nên DTO nhận **Double** wrapper thay vì **double** primitive.

### 11.3. Kết quả tổng hợp không phải entity

Một OrderSalesSummary không phải entity PurchaseOrder hay OrderLine. Sửa:

~~~java
OrderSalesSummary row = summaries.get(0);
// row là record bất biến; không phải managed entity.
~~~

không làm ORM tự update bảng PurchaseOrder. Nếu API cần cho phép sửa trạng thái đơn hàng, ứng dụng phải **load managed entity theo ID**, xác thực quyền/phiên bản rồi thực hiện thao tác nghiệp vụ trong transaction.

## 12. DISTINCT khi truy vấn đi qua quan hệ một-nhiều

Với một Product có nhiều tags:

~~~text
Product #101
  tags = [Tag("java"), Tag("jpa"), Tag("hibernate")]
~~~

Query:

~~~jpql
select new com.example.catalog.dto.ProductSimpleRow(
    p.id, p.name
)
from Product p join p.tags t
where t.name like :pattern
~~~

Nếu nhiều Tag cùng thỏa pattern, cùng Product có thể xuất hiện **nhiều lần** trong danh sách DTO, vì JOIN tạo một hàng cho mỗi cặp Product–Tag phù hợp.

### 12.1. SELECT DISTINCT trên scalar DTO

~~~jpql
select distinct new com.example.catalog.dto.ProductSimpleRow(
    p.id, p.name
)
from Product p join p.tags t
where t.name like :pattern
~~~

**DISTINCT** yêu cầu loại bỏ các kết quả trùng theo ngữ nghĩa truy vấn. Cách provider xử lý khi select constructor expression có thể liên quan SQL DISTINCT hoặc lọc kết quả; quan sát SQL thực tế nếu hiệu năng quan trọng.

**Quan trọng:** Không nên suy đoán rằng DISTINCT của constructor expression sẽ luôn dùng **DTO.equals()** như HashSet trong Java. Ngữ nghĩa DISTINCT phụ thuộc tập biểu thức được chọn và cách JPQL/provider thực thi. Hai DTO khác giá trị ở bất kỳ cột projection nào có thể tiếp tục là hai kết quả khác nhau.

### 12.2. Giảm JOIN bằng EXISTS khi chỉ cần lọc

Nếu không cần lấy dữ liệu Tag trong DTO mà chỉ muốn tìm Product có Tag phù hợp, có thể dùng EXISTS:

~~~jpql
select new com.example.catalog.dto.ProductSimpleRow(
    p.id, p.name
)
from Product p
where exists (
    select t.id
    from p.tags t
    where t.name like :pattern
)
~~~

Nếu có mapping p.tags, **EXISTS** thể hiện điều kiện “tồn tại ít nhất một Tag” mà không mở rộng mỗi Product thành nhiều hàng trong SELECT ngoài. Provider dịch sang SQL tương ứng tùy dialect. Kỹ thuật này thường giúp tránh phải DISTINCT trên nhiều hàng do JOIN chỉ để lọc.

### 12.3. DISTINCT không sửa dữ liệu trùng tại database

Nếu join table có những liên kết trùng thực sự và vi phạm business invariant, DISTINCT chỉ thay hình dạng kết quả truy vấn. Để ngăn dữ liệu sai cần **UNIQUE constraint/PRIMARY KEY** phù hợp trên bảng quan hệ, không dựa vào DISTINCT DTO.

## 13. DTO không tự chứa một List con bằng một constructor expression

Một nhu cầu phổ biến là:

~~~java
public record OrderDetail(
    Long id,
    String number,
    List<OrderLineRow> lines
) {}
~~~

Liệu một câu JPQL constructor expression chuẩn có tự gom mọi line thành List<OrderLineRow> và truyền vào constructor OrderDetail?

**Thông thường là không.** JPQL SELECT NEW tạo một object DTO từ **một hàng kết quả projection**. Nó không phải một ngôn ngữ gom nhóm object graph lồng nhau thành collection Java tùy ý.

### 13.1. Vì sao JOIN không tự tạo collection?

Giả sử query:

~~~jpql
select new com.example.orders.dto.OrderLineFlatRow(
    o.id, o.orderNumber, l.id, l.sku, l.quantity
)
from PurchaseOrder o left join o.lines l
where o.id = :orderId
order by l.id
~~~

Một đơn hàng có 3 dòng sẽ tạo **3 OrderLineFlatRow** dạng phẳng, cùng orderId nhưng khác lineId:

~~~text
OrderLineFlatRow(100, "PO-1", 501, "KB-01", 1)
OrderLineFlatRow(100, "PO-1", 502, "MS-01", 2)
OrderLineFlatRow(100, "PO-1", 503, "PAD-03", 1)
~~~

Provider **không tự gom ba object đó thành một OrderDetail chứa List** chỉ vì constructor của OrderDetail có một trường List.

### 13.2. Giải pháp A: hai query rồi ghép DTO trong Java

Đầu tiên lấy header:

~~~java
public record OrderHeaderRow(Long id, String number) {}
public record OrderLineRow(Long id, String sku, int quantity) {}
public record OrderDetail(
    Long id,
    String number,
    List<OrderLineRow> lines
) {}
~~~

Truy vấn header:

~~~java
OrderHeaderRow header = em.createQuery(
    "select new com.example.orders.dto.OrderHeaderRow(" +
    "o.id, o.orderNumber) " +
    "from PurchaseOrder o where o.id = :id",
    OrderHeaderRow.class
).setParameter("id", orderId)
 .getSingleResult();
~~~

Truy vấn children:

~~~java
List<OrderLineRow> lines = em.createQuery(
    "select new com.example.orders.dto.OrderLineRow(" +
    "l.id, l.sku, l.quantity) " +
    "from OrderLine l where l.order.id = :id order by l.id",
    OrderLineRow.class
).setParameter("id", orderId)
 .getResultList();

OrderDetail detail = new OrderDetail(
    header.id(),
    header.number(),
    List.copyOf(lines)
);
~~~

Đây là cách đơn giản khi truy vấn **một đơn hàng chi tiết**. Cả header và lines đều được chọn theo projection. Với dữ liệu cần consistency giữa hai query, chạy trong transaction với isolation phù hợp; nếu không, transaction khác có thể chỉnh lines giữa hai lần SELECT.

### 13.3. Giải pháp B: truy vấn phẳng và gom theo ID

Nếu lấy nhiều đơn hàng, có thể tạo Flat DTO rồi group trong service:

~~~java
public record OrderLineFlatRow(
    Long orderId,
    String orderNumber,
    Long lineId,
    String sku,
    Integer quantity
) {}
~~~

Với LEFT JOIN, một Order không có line có thể tạo hàng trong đó **lineId, sku, quantity đều null**. Do đó DTO dùng Integer wrapper cho quantity, thay vì int.

Mã ánh xạ:

~~~java
Map<Long, List<OrderLineRow>> linesByOrder = new LinkedHashMap<>();
Map<Long, String> numberByOrder = new LinkedHashMap<>();

for (OrderLineFlatRow flat : rows) {
    numberByOrder.putIfAbsent(flat.orderId(), flat.orderNumber());
    linesByOrder.computeIfAbsent(
        flat.orderId(), ignored -> new ArrayList<>()
    );

    if (flat.lineId() != null) {
        linesByOrder.get(flat.orderId()).add(new OrderLineRow(
            flat.lineId(), flat.sku(), flat.quantity()
        ));
    }
}

List<OrderDetail> details = new ArrayList<>();
for (Map.Entry<Long, String> entry : numberByOrder.entrySet()) {
    details.add(new OrderDetail(
        entry.getKey(),
        entry.getValue(),
        List.copyOf(linesByOrder.get(entry.getKey()))
    ));
}
~~~

Ví dụ giả định **rows** là List<OrderLineFlatRow> đã được truy vấn và các DTO được khai báo trong package phù hợp. Phương án này cần chú ý số hàng JOIN có thể tăng mạnh nếu trả quá nhiều orders hoặc JOIN nhiều collections.

### 13.4. Phân trang cha trước, tải con sau

Đối với danh sách nhiều orders, không nên phân trang trực tiếp trên những **hàng order × lines** rồi mới group; một page 20 hàng JOIN không tương đương 20 Order.

Hướng thường dùng:

1. **Query 1:** lấy 20 OrderHeaderRow hoặc ID của 20 Order dựa trên điều kiện và sort ổn định.
2. **Query 2:** lấy OrderLineRow cho các orderId thuộc page bằng điều kiện IN :orderIds.
3. **Ghép DTO** theo thứ tự của page đầu.

Đây là pattern **page parents, then batch-fetch children**. Nó tránh N+1 query và giữ ngữ nghĩa “20 đơn hàng mỗi trang”. Nếu yêu cầu tổng số đơn, còn có count query riêng.

## 14. Phân trang DTO với setFirstResult/setMaxResults

Constructor expression hoạt động với **TypedQuery**, nên có thể dùng phân trang chuẩn JPA:

~~~java
int pageNumber = 2;
int pageSize = 20;

List<ProductRow> page = em.createQuery(
    "select new com.example.catalog.dto.ProductRow(" +
    "p.id, p.sku, p.name, c.name, p.price) " +
    "from Product p left join p.category c " +
    "where p.status = :status " +
    "order by p.name asc, p.id asc",
    ProductRow.class
).setParameter("status", ProductStatus.ACTIVE)
 .setFirstResult(pageNumber * pageSize)
 .setMaxResults(pageSize)
 .getResultList();
~~~

**setFirstResult()** nhận vị trí bắt đầu từ 0, **setMaxResults()** đặt số hàng tối đa của kết quả. Kiểm tra pageNumber, pageSize, overflow và giới hạn page size từ API thay vì tin tưởng input.

### 14.1. Count query là một query khác

Nếu API cần **totalElements**:

~~~java
Long total = em.createQuery(
    "select count(p) from Product p where p.status = :status",
    Long.class
).setParameter("status", ProductStatus.ACTIVE)
 .getSingleResult();
~~~

Count query cần cùng logic filter với query dữ liệu. Nếu query dữ liệu join một association để lọc và tạo nhiều hàng cho mỗi Product, count query có thể cần **count(distinct p.id)** hoặc EXISTS để phản ánh **số Product**, không phải số hàng join.

### 14.2. DTO không tự giải quyết page drift

Nếu một sản phẩm mới được thêm vào đầu danh sách giữa page 1 và page 2, OFFSET có thể khiến một kết quả bị lặp hoặc bỏ sót. Sort key ổn định giúp trật tự rõ, nhưng không chặn thay đổi dữ liệu theo thời gian. Với dữ liệu biến động lớn, **keyset pagination** hoặc snapshot/transaction isolation phù hợp có thể tốt hơn.

### 14.3. Không dùng FETCH JOIN collection với DTO tùy tiện

Một câu query kiểu:

~~~jpql
select new com.example.catalog.dto.ProductSimpleRow(
    p.id, p.name
)
from Product p
join fetch p.tags
~~~

không phải cách portable để tải collection vào một DTO. **FETCH JOIN** dùng để điều khiển việc tải association của entity chủ sở hữu được chọn; khi chỉ SELECT NEW DTO mà không chọn owning entity như entity result, provider có thể báo lỗi hoặc query không có semantics mong muốn.

Nếu DTO chỉ cần giá trị scalar từ Tag, hãy dùng **JOIN thường** và chọn những field cần thiết. Nếu cần toàn bộ danh sách tags cho mỗi Product, dùng truy vấn phẳng/two-query grouping theo mục 13, hoặc một chiến lược truy vấn được thiết kế có chủ đích.

## 15. DTO và persistence context: ai được quản lý?

Xét:

~~~java
List<ProductRow> rows = em.createQuery(
    "select new com.example.catalog.dto.ProductRow(" +
    "p.id, p.sku, p.name, c.name, p.price) " +
    "from Product p left join p.category c",
    ProductRow.class
).getResultList();
~~~

Mỗi ProductRow là một object được khởi tạo theo constructor. **Bản thân DTO không phải managed entity**, không tham gia dirty checking và không được JPA tự cập nhật xuống database khi chỉnh field trong một class DTO mutable.

### 15.1. Không thể dùng em.remove(dto) như entity

~~~java
ProductRow row = rows.get(0);
// em.remove(row);  // Không đúng: ProductRow không phải JPA entity.
~~~

Nếu muốn xóa Product:

~~~java
Product managed = em.find(Product.class, row.id());
if (managed != null) {
    em.remove(managed);
}
~~~

Thao tác nghiệp vụ thật còn cần kiểm tra authorization, quyền xóa và constraint FK trong transaction. Dùng ID từ DTO để **xác định** entity cần sửa, không dùng DTO như một object managed.

### 15.2. SELECT NEW vẫn có thể nhận entity làm đối số

JPA cho phép constructor expression chứa **identification variable** hoặc biểu thức dẫn đến entity trong một số trường hợp hợp lệ:

~~~java
public record ProductWithCategory(
    Long id,
    Category category
) {}
~~~

~~~jpql
select new com.example.catalog.dto.ProductWithCategory(
    p.id, c
)
from Product p join p.category c
~~~

Trong trường hợp đó, **DTO bên ngoài không managed**, nhưng **Category được truyền vào** có thể là entity managed theo query và persistence context. Như vậy:

- Truy vấn có thể khiến provider materialize Category entity đầy đủ.
- DTO có thể giữ tham chiếu tới entity và kéo theo lazy association khi serialize JSON.
- Sửa Category managed qua reference đó có thể được dirty checking.
- Lợi thế “chỉ tải scalar và không mang entity” có thể bị mất.

Nếu mục đích là tạo API response nhẹ, thường nên truyền **c.id, c.name** vào một CategorySummary DTO thay vì đưa thẳng Category entity vào DTO.

### 15.3. DTO không tự có caching của entity

Các entity result có thể gắn với identity map/persistence context, first-level cache và cơ chế second-level cache của provider. DTO constructor expression **không tự trở thành một managed entity được cache theo khóa chính**.

Nếu bạn chạy cùng DTO query nhiều lần, provider vẫn có thể gửi SQL mỗi lần, trừ khi có query cache/provider-specific caching đã cấu hình hoặc tầng cache riêng. Không nên giả định “dùng DTO là được Hibernate cache tất cả”.

Ngược lại, DTO cũng không phải gánh đầy đủ dirty checking của entity được materialize, tạo lợi thế khi đọc danh sách lớn. Cân bằng giữa chi phí query, materialization và cache theo workload thực tế.

## 16. DTO, N+1 và LazyInitializationException

Một cách phổ biến gây N+1:

~~~java
List<Product> products = em.createQuery(
    "select p from Product p",
    Product.class
).getResultList();

List<ProductRow> rows = products.stream()
    .map(p -> new ProductRow(
        p.getId(),
        p.getSku(),
        p.getName(),
        p.getCategory() == null
            ? null
            : p.getCategory().getName(),
        p.getPrice()
    ))
    .toList();
~~~

Với **@ManyToOne(fetch=LAZY)**, đọc **category.getName()** có thể kích hoạt thêm SELECT cho những Category chưa được tải. Trong một transaction, chuyện này có thể tạo nhiều round-trip; ngoài transaction, có thể gặp LazyInitializationException với provider như Hibernate.

Một constructor DTO query dùng:

~~~jpql
select new com.example.catalog.dto.ProductRow(
    p.id, p.sku, p.name, c.name, p.price
)
from Product p left join p.category c
~~~

cho provider đủ thông tin để lấy **c.name** trực tiếp trong SQL JOIN tương ứng. Service không cần đi qua Product.category ở Java để lập DTO. Đây là lợi ích thường thấy của query projection.

### 16.1. Không có nghĩa mọi DTO query luôn chỉ một SQL

Nếu DTO query gọi hàm vendor-specific, chứa entity reference, hoặc ứng dụng lấy thêm dữ liệu trong vòng lặp sau khi query, có thể vẫn phát thêm SQL. Hãy quan sát SQL log/tracing thực tế. Chỉ SELECT NEW không phải lời cam kết chống N+1 cho mọi workflow.

### 16.2. Nếu API cần dữ liệu nhiều cấp

Ví dụ ProductRow cần:

~~~text
product
  category.name
  supplier.address.city
~~~

JPQL có thể JOIN nhiều single-valued associations và chọn scalar:

~~~jpql
select new com.example.catalog.dto.ProductDetailRow(
    p.id,
    p.name,
    c.name,
    city.name
)
from Product p
left join p.category c
left join p.supplier s
left join s.address a
left join a.city city
~~~

Ví dụ trên giả định **Product.supplier**, **Supplier.address** và **Address.city** là những thuộc tính được mapping phù hợp. Nếu Address là embeddable hoặc thành phần không phải association entity, cách điều hướng có thể khác và JOIN không phải lúc nào cũng hợp lệ. Cần xem mapping trước khi dùng JOIN.

Một câu query với nhiều JOIN không tự nhiên tốt hơn nhiều query nhỏ: lượng dữ liệu và cardinality quyết định chi phí. Tuy nhiên projection scalar thường tránh việc serializer tự điều hướng toàn bộ đồ thị khi trả API.

## 17. Hiệu năng: DTO có lợi ở đâu, không có lợi ở đâu?

### 17.1. Những chi phí có thể tiết kiệm

Khi chỉ cần vài cột, DTO constructor có thể giảm:

- Byte truyền qua JDBC và mạng nếu SELECT ít cột hơn.
- Chi phí materialize entity đầy đủ và identity resolution.
- Bộ nhớ persistence context cho một trang danh sách.
- Dirty checking đối với những entity không được tạo ra.
- Các lần lazy loading phát sinh do map entity sang DTO không đúng fetch plan.

Đặc biệt, các trang báo cáo chỉ đọc với số lượng lớn hàng thường hưởng lợi từ projection hơn việc tải entity rồi bỏ phần lớn field.

### 17.2. Những chi phí DTO không tự loại bỏ

- Scan bảng lớn do thiếu index.
- JOIN to-many làm nhân số hàng.
- Sort/aggregate trên lượng dữ liệu lớn.
- OFFSET pagination sâu.
- Tính toán SQL tốn CPU.
- Đọc toàn bộ 1 triệu DTO vào một List cùng lúc.
- Cache miss, connection contention hoặc isolation/lock chờ.

Đừng so sánh truy vấn DTO chỉ chọn 5 cột với truy vấn entity có FETCH JOIN 3 collection rồi kết luận **constructor expression tự nhiên nhanh hơn mọi entity query**. Phải so sánh những truy vấn phục vụ cùng một use case với cùng lượng thông tin cần thiết.

### 17.3. Khi entity result phù hợp hơn

Nếu nghiệp vụ cần:

- Thay đổi entity có transaction và dirty checking.
- Cascade/orphan removal của aggregate.
- Xử lý domain behavior trên managed entity.
- Tái sử dụng entity đã có trong persistence context.

thì **load entity** là lựa chọn phù hợp hơn trả DTO rồi cố cập nhật DTO. DTO là công cụ cho **read model/transport**, không phải thay thế toàn bộ vai trò của entity trong persistence.

### 17.4. Index và predicate quan trọng hơn cú pháp new

~~~jpql
where p.status = :status
and p.price between :min and :max
order by p.price, p.id
~~~

Trên database, có thể cần index phù hợp với status, price và ID, tùy phân bố dữ liệu. Một DTO projection không giúp tránh full scan nếu filter không tận dụng được index và table quá lớn. Cần xem SQL được sinh và **EXPLAIN/EXPLAIN ANALYZE** trên DBMS thực.

### 17.5. Quản lý transaction cho DTO query

DTO chỉ đọc thường được lập trong một **read-only transaction** hoặc một scope EntityManager hợp lệ. DTO scalar đã được tạo xong có thể dùng ngoài transaction mà không phụ thuộc lazy proxy của entity, miễn không chứa entity references hoặc object lazy bên trong.

Nhưng nếu API cần **hai query** (header và lines), có thể phải dùng transaction/snapshot phù hợp để bảo đảm kết quả nhất quán. Read-only transaction là cấu hình framework/runtime, **không tự là một dạng isolation tuyệt đối hay snapshot cho mọi DBMS**.

## 18. Các khác biệt cần biết với native SQL

**SELECT NEW là cú pháp của JPQL**, không phải cú pháp SQL tiêu chuẩn:

~~~jpql
select new com.example.catalog.dto.ProductRow(
    p.id, p.sku, p.name, c.name, p.price
)
from Product p left join p.category c
~~~

Không gửi nguyên câu này tới JDBC bằng **createNativeQuery()** hoặc chạy trong console SQL của database. SQL không hiểu toán tử **new com.example...** và không biết các tên thuộc tính Java như p.category.

### 18.1. createNativeQuery() cần cách map riêng

Native SQL:

~~~sql
SELECT
    p.id,
    p.sku,
    p.name,
    c.name AS category_name,
    p.price
FROM products p
LEFT JOIN categories c ON c.id = p.category_id
~~~

Nếu dùng:

~~~java
List<?> rows = em.createNativeQuery(sql).getResultList();
~~~

kết quả mặc định cho nhiều cột thường là các mảng giá trị SQL/Java theo provider/JDBC. Nó **không tự nhận dạng** ProductRow chỉ vì class DTO tồn tại.

### 18.2. @SqlResultSetMapping và @ConstructorResult

JPA cung cấp cách ánh xạ constructor cho **native SQL result set**:

~~~java
@SqlResultSetMapping(
    name = "ProductRowMapping",
    classes = @ConstructorResult(
        targetClass = com.example.catalog.dto.ProductRow.class,
        columns = {
            @ColumnResult(name = "id", type = Long.class),
            @ColumnResult(name = "sku", type = String.class),
            @ColumnResult(name = "name", type = String.class),
            @ColumnResult(name = "category_name", type = String.class),
            @ColumnResult(name = "price", type = BigDecimal.class)
        }
    )
)
@Entity
public class Product {
    // Các trường mapping như phần đầu bài.
}
~~~

Các annotation cần import từ **jakarta.persistence**, còn **BigDecimal** từ java.math. Đoạn này chỉ minh họa bổ sung annotation result-set mapping vào một entity hiện có; không tạo một entity Product khác cùng tên trong ứng dụng.

Khi chạy:

~~~java
@SuppressWarnings("unchecked")
List<ProductRow> rows = em.createNativeQuery(
    """
    select p.id as id,
           p.sku as sku,
           p.name as name,
           c.name as category_name,
           p.price as price
    from products p
    left join categories c on c.id = p.category_id
    """,
    "ProductRowMapping"
).getResultList();
~~~

thì @ConstructorResult hướng dẫn provider khởi tạo DTO từ các column aliases theo thứ tự đã khai báo.

### 18.3. Điểm khác biệt giữa hai kỹ thuật

| Đặc điểm | JPQL SELECT NEW | Native @ConstructorResult |
|---|---|---|
| Ngôn ngữ truy vấn | JPQL entity/attribute paths | SQL theo DBMS |
| Cú pháp tạo DTO | new FullyQualifiedDto(...) trong SELECT | @SqlResultSetMapping + @ConstructorResult |
| Tên bảng/cột | Tên entity và property | Tên bảng/cột SQL |
| Column alias | Không bắt buộc cho mỗi constructor argument | Cần khớp @ColumnResult |
| Tính portable | Tương đối cao nếu dùng JPQL chuẩn | SQL và hàm DB có thể đặc thù |
| Truy vấn phức tạp CTE/window | Khả năng phụ thuộc JPQL version/provider | Thường linh hoạt hơn với DBMS |
| Lỗi mapping phổ biến | Constructor/type mismatch | Sai alias, JDBC type, column order |

**Không đồng nhất SELECT NEW với @SqlResultSetMapping.** Cả hai có thể tạo DTO nhưng xuất phát từ hai loại query khác nhau.

## 19. Criteria API và constructor projection

Khi câu query có filter động, Criteria API có thể dựng constructor expression mà không phải tự nối nhiều đoạn JPQL:

~~~java
import jakarta.persistence.TypedQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Join;
import jakarta.persistence.criteria.JoinType;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<ProductRow> cq = cb.createQuery(ProductRow.class);

Root<Product> product = cq.from(Product.class);
Join<Product, Category> category = product.join(
    "category", JoinType.LEFT
);

cq.select(cb.construct(
    ProductRow.class,
    product.get("id"),
    product.get("sku"),
    product.get("name"),
    category.get("name"),
    product.get("price")
));

cq.where(cb.equal(
    product.get("status"), ProductStatus.ACTIVE
));

cq.orderBy(
    cb.asc(product.get("name")),
    cb.asc(product.get("id"))
);

TypedQuery<ProductRow> query = em.createQuery(cq);
List<ProductRow> rows = query.getResultList();
~~~

**cb.construct(ProductRow.class, ...)** là ý tưởng tương đương JPQL SELECT NEW, dùng các **Selection<?>** trong Criteria API làm đối số. Tên property dạng String ở ví dụ có thể thay bằng static metamodel nếu dự án có sinh **Product_**, **Category_**, giúp compiler kiểm tra tốt hơn khi refactor.

### 19.1. Khi nào Criteria API hợp lý?

- Bộ lọc có nhiều nhánh optional và phải kết hợp động.
- Muốn tái sử dụng predicates.
- Có static metamodel giúp giảm lỗi typo property.
- Cần dựng query bằng API thay vì phép ghép chuỗi.

Với query cố định và dễ đọc, **JPQL SELECT NEW thường ngắn hơn**. Không bắt buộc chuyển mọi constructor expression sang Criteria chỉ để giảm vài literal.

### 19.2. Constructor mismatch vẫn có thể xảy ra

Criteria API không tự sửa chữ ký DTO. Nếu **cb.construct()** cung cấp sai số lượng, thứ tự hoặc kiểu Selection, provider vẫn có thể báo lỗi tại thời điểm tạo/thực thi query. Static metamodel hỗ trợ type checking ở property path nhưng **không thay thế việc đảm bảo constructor phù hợp**.

## 20. Spring Data JPA và DTO projection

Trong ứng dụng Spring Data JPA, có thể định nghĩa repository query bằng @Query:

~~~java
package com.example.catalog.repository;

import com.example.catalog.dto.ProductRow;
import com.example.catalog.model.ProductStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select new com.example.catalog.dto.ProductRow(
            p.id,
            p.sku,
            p.name,
            c.name,
            p.price
        )
        from Product p
        left join p.category c
        where p.status = :status
        order by p.name, p.id
        """)
    List<ProductRow> findRows(
        @Param("status") ProductStatus status
    );
}
~~~

Spring Data JPA cung cấp nhiều cơ chế projection khác như **interface-based projection**, class-based projection theo convention và dynamic projection. Tuy nhiên, **khi viết JPQL SELECT NEW rõ ràng**, việc tạo DTO vẫn theo constructor expression của JPA.

### 20.1. Interface projection không giống SELECT NEW

Một interface:

~~~java
public interface ProductNameView {
    Long getId();
    String getName();
}
~~~

có thể được Spring Data ánh xạ bằng cơ chế proxy/projection riêng. Đây **không phải** class được JPA gọi constructor theo cú pháp SELECT NEW.

### 20.2. Repository Pageable và count query

Với Spring Data:

~~~java
@Query(
    value = """
        select new com.example.catalog.dto.ProductRow(
            p.id, p.sku, p.name, c.name, p.price
        )
        from Product p left join p.category c
        where p.status = :status
        """,
    countQuery = """
        select count(p) from Product p
        where p.status = :status
        """
)
Page<ProductRow> findPage(
    @Param("status") ProductStatus status,
    Pageable pageable
);
~~~

Đoạn này giả định import **org.springframework.data.domain.Page**, **Pageable** và các class repository/model thích hợp. Nếu query dữ liệu JOIN để lọc to-many, **countQuery** phải phản ánh đúng số root thực tế, có thể cần DISTINCT hoặc EXISTS. Một count query sai khiến totalElements và totalPages sai dù content của DTO được tạo đúng.

### 20.3. Không dựa vào query rewrite tùy framework

Một số phiên bản Spring Data có thể rewrite những dạng query để tạo DTO projection theo return type. Đây là tính năng framework, không phải cú pháp bắt buộc của JPQL. Nếu muốn hiểu rõ SQL và constructor, dùng **SELECT NEW** tường minh cùng test tích hợp phù hợp. Luôn kiểm tra khả năng hỗ trợ theo version Spring Data và JPA provider đang sử dụng.

## 21. Lỗi thường gặp và cách xác định nguyên nhân

### 21.1. Không tìm được constructor phù hợp

Thông báo provider có thể là:

~~~text
Could not resolve constructor for class ...
Missing constructor for type ...
Cannot instantiate class ...
~~~

Các nguyên nhân:

1. Sai số lượng tham số.
2. Sai thứ tự tham số.
3. Sai kiểu Java (Long vs Integer, BigDecimal vs Double, enum vs String).
4. Constructor thiếu public hoặc class DTO không truy cập được.
5. DTO thay đổi nhưng chuỗi JPQL chưa được cập nhật.
6. Null được truyền vào tham số primitive.

Ví dụ:

~~~java
public record ProductCount(String name, Integer count) {}
~~~

nhưng query:

~~~jpql
select new com.example.catalog.dto.ProductCount(
    p.name, count(p)
)
from Product p
group by p.name
~~~

**COUNT trả Long**, nên sửa component thành **Long count**.

### 21.2. Class DTO không được tìm thấy

~~~jpql
select new ProductRow(p.id, p.name) from Product p
~~~

Nếu provider báo không tìm được ProductRow, hãy dùng **fully qualified name**:

~~~jpql
select new com.example.catalog.dto.ProductSimpleRow(
    p.id, p.name
)
from Product p
~~~

Đồng thời đảm bảo class có trên runtime classpath/module path và package đúng. Nếu đổi tên package trong Java nhưng quên sửa JPQL literal, query không còn hợp lệ.

### 21.3. Sai tên property

~~~jpql
select new com.example.catalog.dto.ProductSimpleRow(
    p.product_id, p.product_name
)
from Product p
~~~

Nếu entity chỉ có **id** và **name**, query sai vì dùng tên cột SQL. Dùng **p.id, p.name** trong JPQL. Tên cột dưới @Column(name="...") không đổi tên property Java.

### 21.4. Dùng join c.name nhưng không khai báo c

~~~jpql
select new com.example.catalog.dto.ProductRow(
    p.id, p.sku, p.name, c.name, p.price
)
from Product p
~~~

Alias **c** chưa được khai báo. Cần thêm:

~~~jpql
left join p.category c
~~~

vào FROM/JOIN của query. Alias phải có trong scope phù hợp.

### 21.5. Không có kết quả do INNER JOIN

Product có category=null nhưng query dùng:

~~~jpql
from Product p join p.category c
~~~

Product đó bị loại khỏi kết quả. Nếu muốn giữ Product chưa có danh mục, dùng **left join**, xử lý **c.name** null hoặc COALESCE.

### 21.6. Bị lặp DTO do JOIN to-many

Query chọn Product ID/name nhưng JOIN tags tạo nhiều hàng. Nếu chỉ cần lọc theo Tag, dùng EXISTS hoặc SELECT DISTINCT phù hợp; nếu cần nhiều Tag trong response, dùng projection phẳng rồi group ở Java hoặc hai query.

### 21.7. Lỗi aggregate và GROUP BY

~~~jpql
select new com.example.catalog.dto.CategoryProductCount(
    c.id, c.name, count(p)
)
from Category c join c.products p
~~~

thiếu GROUP BY khi chọn các trường phi tổng hợp, nên có thể bị lỗi query/SQL. Thêm **group by c.id, c.name** để tạo một kết quả mỗi Category.

### 21.8. Sai số liệu vì nhiều to-many JOIN

Nếu query đồng thời JOIN lines và discounts/coupons, số hàng bị nhân. **sum(distinct amount)** không khắc phục được tổng khi nhiều dòng thật sự có số tiền giống nhau. Phải thay hình dạng query hoặc aggregate theo từng association trước khi JOIN.

### 21.9. DTO có List nhưng provider không tự gom con

JPQL constructor tạo **một DTO theo mỗi hàng projection**, không tự tạo List<OrderLineDTO> khi một Order có nhiều lines. Dùng two-query approach hoặc flat rows + grouping để kiểm soát collection.

### 21.10. Fetch join không phù hợp với SELECT NEW

Đừng thêm **join fetch** chỉ để tránh N+1 trong một constructor query chọn scalar DTO. Fetch join dành cho entity result owner được tải; query DTO nên JOIN thường và chọn field cần thiết.

### 21.11. DTO chứa entity, lại gặp LazyInitializationException

Nếu DTO nhận **Category** nguyên entity và API serialize các getter của Category sau khi transaction đóng, lazy association vẫn có thể bị truy cập. Muốn DTO độc lập với persistence context, truyền các **scalar** hoặc DTO con thuần giá trị thay vì giữ entity.

### 21.12. Sửa DTO rồi dữ liệu không thay đổi

DTO không phải managed entity. Thay giá trị của DTO mutable không được JPA dirty checking. Muốn cập nhật DB, load managed entity và thực hiện domain operation hoặc chạy DML có kiểm soát.

### 21.13. Thay đổi constructor làm query cũ lỗi

Một record được thêm component **currency** sẽ đổi canonical constructor. Những JPQL SELECT NEW cũ chỉ truyền 5 tham số sẽ không còn khớp nếu không có overload được hỗ trợ. Khi sửa DTO dùng chung, cần cập nhật các query gọi constructor hoặc tạo DTO phiên bản mới cho use case.

### 21.14. Alias bên trong constructor expression

Không viết:

~~~jpql
select new com.example.catalog.dto.ProductSimpleRow(
    p.id as id,
    p.name as name
)
from Product p
~~~

theo kỳ vọng một constructor expression JPQL chuẩn nhận alias sau mỗi argument. Constructor xác định tham số theo vị trí; các alias bên trong argument list không phải cú pháp JPQL portable. Viết:

~~~jpql
select new com.example.catalog.dto.ProductSimpleRow(
    p.id, p.name
)
from Product p
~~~

Nếu muốn truy cập theo alias, dùng **Tuple** bên ngoài constructor thay vì gắn alias vào các constructor arguments.

### 21.15. Khác kiểu số do phép toán trong DB

Nếu field **quantity** là Integer và SUM(quantity) trả Long, một record constructor **Integer totalQuantity** không khớp. Nếu field **price** là BigDecimal mà AVG(price) trả Double, record **BigDecimal averagePrice** có thể không khớp. Cần dựa vào **kiểu trả của biểu thức JPQL**, không chỉ kiểu cột gốc.

### 21.16. Truy vấn native SQL dùng SELECT NEW

Cú pháp **new com.example.Dto(...)** chỉ có ý nghĩa trong JPQL/HQL thích hợp, không phải SQL database. Dùng JPQL createQuery hoặc native @SqlResultSetMapping/@ConstructorResult, không lẫn hai API.

### 21.17. Grouping DTO trả sai tổng và total count

Một API trả Page<ProductRow> nhưng count query đếm hàng Tag JOIN thay vì Product. Result page có thể đúng nhưng **totalElements** bị phóng đại. Cần xác định đơn vị phân trang là Product, Tag hay hàng quan hệ, rồi viết count query khớp.

## 22. Kiểm thử projection theo hợp đồng dữ liệu

Một test tích hợp có thể dùng JUnit 5 trong môi trường JPA đã cấu hình. Mục tiêu là xác nhận **shape và giá trị** của DTO, không chỉ “query không ném exception”.

### 22.1. Test một sản phẩm có category

Giả sử fixture đã có Product với ID xác định, Category và giá tương ứng:

~~~java
@Test
void productRowContainsExpectedFields() {
    ProductRow row = em.createQuery(
        "select new com.example.catalog.dto.ProductRow(" +
        "p.id, p.sku, p.name, c.name, p.price) " +
        "from Product p left join p.category c " +
        "where p.sku = :sku",
        ProductRow.class
    ).setParameter("sku", "KB-001")
     .getSingleResult();

    assertEquals("KB-001", row.sku());
    assertEquals("Bàn phím cơ", row.name());
    assertEquals("Phụ kiện", row.categoryName());
    assertEquals(0, new BigDecimal("890000.00")
        .compareTo(row.price()));
}
~~~

Test giả định import JUnit Assertions, **BigDecimal** và **ProductRow**; fixture phải được chuẩn bị trong schema/test transaction. So sánh BigDecimal bằng compareTo() khi chỉ quan tâm giá trị số, vì equals() còn xét scale.

### 22.2. Test null từ LEFT JOIN

Tạo Product không có Category:

~~~java
ProductRow row = em.createQuery(
    "select new com.example.catalog.dto.ProductRow(" +
    "p.id, p.sku, p.name, c.name, p.price) " +
    "from Product p left join p.category c " +
    "where p.sku = :sku",
    ProductRow.class
).setParameter("sku", "UNCATEGORIZED")
 .getSingleResult();

assertNull(row.categoryName());
~~~

Nếu code dùng COALESCE trong SELECT, hãy kiểm tra giá trị mặc định thay vì null.

### 22.3. Test aggregate và Category rỗng

Chuẩn bị một Category chưa có Product. Chạy query:

~~~jpql
select new com.example.catalog.dto.CategoryProductCount(
    c.id, c.name, count(p)
)
from Category c left join c.products p
group by c.id, c.name
~~~

Kết quả Category trống phải có **productCount = 0L**. Nếu dùng INNER JOIN, Category trống sẽ không có hàng kết quả; test nên phát hiện điều đó khi requirement đòi giữ tất cả danh mục.

### 22.4. Test DTO không phải managed

~~~java
ProductRow row = em.createQuery(
    "select new com.example.catalog.dto.ProductRow(" +
    "p.id, p.sku, p.name, c.name, p.price) " +
    "from Product p left join p.category c",
    ProductRow.class
).setMaxResults(1)
 .getSingleResult();

assertFalse(
    ProductRow.class.isAnnotationPresent(jakarta.persistence.Entity.class)
);
~~~

Vì ProductRow không phải @Entity, **EntityManager.contains(row)** có thể ném **IllegalArgumentException** với non-entity object thay vì trả false. Do đó test trên xác nhận class DTO **không có @Entity**; không dùng contains(nonEntity) như một assertion bắt buộc để chứng minh không managed.

Nếu cần kiểm tra thực tế việc sửa DTO không ghi DB, dùng một DTO mutable có setter, sửa nó, commit và load Product bằng EntityManager mới để xác nhận Product không đổi. Với record, bất biến của record đã ngăn chỉnh component trực tiếp.

### 22.5. Test pagination và order ổn định

Chuẩn bị nhiều Product có cùng price nhưng khác ID:

~~~java
List<ProductRow> page = em.createQuery(
    "select new com.example.catalog.dto.ProductRow(" +
    "p.id, p.sku, p.name, c.name, p.price) " +
    "from Product p left join p.category c " +
    "order by p.price asc, p.id asc",
    ProductRow.class
).setFirstResult(10)
 .setMaxResults(10)
 .getResultList();
~~~

Kiểm tra số phần tử tối đa và thứ tự price/id. Với dataset có đủ hàng, test có thể xác nhận ID không bị lặp giữa các page khi không có concurrent writes.

### 22.6. Test với DBMS/provider giống production

H2 hoặc một in-memory DB có thể không phản ánh chính xác type conversion, collation, JOIN behavior, precision/scale và lỗi constructor của DB production. Với những query aggregate hoặc native function phức tạp, cần test trên DBMS/dialect/provider thực tế hoặc test container phù hợp.

**Không nên đo hiệu năng từ JUnit chỉ có vài hàng fixture.** Kiểm chứng giá trị DTO và đo plan/latency là hai mục tiêu khác nhau.

## 23. Thiết kế DTO theo use case thay vì một DTO cho mọi màn hình

Một anti-pattern thường gặp là tạo một class **ProductDTO** với hàng chục field rồi dùng nó cho trang danh sách, trang chi tiết, màn hình tìm kiếm và xuất báo cáo:

~~~text
ProductDTO
  id, sku, name, price, categoryName, supplierName,
  stock, warehouse, tags, reviews, createdAt, updatedAt, ...
~~~

Khi mỗi query chỉ có một phần field, đội phát triển có thể tạo nhiều constructor gần giống, truyền rất nhiều null, hoặc thêm cột không cần thiết để khớp constructor chung.

Thay vào đó, có thể tách theo mục đích:

~~~java
public record ProductListRow(
    Long id,
    String sku,
    String name,
    BigDecimal price
) {}

public record ProductSearchHit(
    Long id,
    String name,
    String categoryName
) {}

public record ProductPriceStats(
    String categoryName,
    Long count,
    BigDecimal totalPrice
) {}
~~~

Mỗi DTO có:

- **Tên phản ánh nội dung** và mục đích hiển thị.
- **Constructor rõ ràng** với số tham số vừa phải.
- **Kiểu đúng** cho giá trị nullable và aggregate.
- **Thứ tự tham số** có thể kiểm soát.
- **Không chứa entity managed** nếu muốn kết quả thuần read model.

Với nhiều DTO, có thể cần bảo trì nhiều query nhưng đổi lại tránh một hợp đồng “khổng lồ” dễ làm các màn hình phụ thuộc lẫn nhau. Không nhất thiết tách DTO cho từng SELECT nếu nhiều use case thật sự chia sẻ cùng một cấu trúc ổn định.

### 23.1. Quy tắc null của DTO

Nếu trường có thể null do LEFT JOIN hoặc aggregate, hãy quyết định rõ:

1. API cho phép null?
2. Dùng COALESCE để có giá trị mặc định?
3. Bỏ trường khỏi DTO?
4. Trả một trạng thái bổ sung thể hiện “chưa có dữ liệu”?

Đừng che dấu việc Category bị thiếu bằng chuỗi rỗng nếu client cần phân biệt **chưa phân loại** với **tên danh mục rỗng**. Cũng đừng dùng 0 để thay cho “không có dữ liệu thống kê” khi nghiệp vụ cần giữ ý nghĩa khác nhau.

### 23.2. Yêu cầu bảo mật không tự được SELECT NEW xử lý

Một DTO chỉ chọn vài cột có thể giúp giảm data exposure, nhưng **không tự áp dụng authorization**:

~~~jpql
select new com.example.orders.dto.OrderHeaderRow(
    o.id, o.orderNumber
)
from PurchaseOrder o
where o.tenant.id = :tenantId
~~~

Nếu ứng dụng đa tenant, phải ràng buộc query với tenant hoặc quyền người dùng theo chính sách thực tế. Không để client tự chọn tenantId của người khác mà không kiểm tra. Một constructor expression tạo DTO rất gọn vẫn có thể làm lộ thông tin nếu **WHERE predicate** thiếu điều kiện phân quyền.

### 23.3. Entity projection để cập nhật và DTO projection để đọc

Một pattern hữu ích trong codebase:

~~~text
GET /products:
  SELECT NEW ProductListRow(...)
  -> JSON read model

POST /products/{id}/rename:
  em.find(Product.class, id)
  -> authorize, validate, product.rename(...)
  -> transaction commit
~~~

Cách này tránh dùng DTO như entity và giúp service nhận trách nhiệm cho thay đổi dữ liệu. Không nhất thiết mọi ứng dụng phải theo kiến trúc CQRS đầy đủ, nhưng **phân biệt read projection và write model** là hữu ích ngay cả trong CRUD đơn giản.

## 24. Quy trình viết một constructor expression mới

Khi có một yêu cầu danh sách hoặc báo cáo, có thể làm theo các bước sau:

1. **Xác định một hàng kết quả đại diện cho gì:** Product, Order, Category, hay một nhóm aggregate?
2. **Liệt kê trường thực sự cần:** ID, tên, thuộc tính JOIN, số lượng và tổng.
3. **Xác định kiểu Java của từng biểu thức:** đọc entity mapping và quy tắc COUNT/SUM/AVG.
4. **Xác định nullability:** nhất là LEFT JOIN, aggregate nhóm rỗng và CASE/COALESCE.
5. **Viết DTO trước:** record hoặc class immutable với constructor đúng thứ tự.
6. **Viết SELECT NEW với full package name:** truyền chính xác các biểu thức cho constructor.
7. **Thêm JOIN có chủ đích:** hiểu inner vs left, tránh JOIN to-many không cần.
8. **Kiểm tra số hàng:** một entity có xuất hiện nhiều lần vì JOIN không, có cần EXISTS/DISTINCT/GROUP BY?
9. **Thêm WHERE và ORDER BY:** dùng bound parameters và thứ tự ổn định.
10. **Nếu cần phân trang:** viết count query có cùng filter và đúng đơn vị đếm.
11. **Nếu cần collection DTO:** chọn two-query hoặc flat/group, không mong constructor tự gom.
12. **Chạy test và quan sát SQL khi triển khai:** xác nhận kết quả, null, kiểu và kế hoạch truy vấn trên provider thực.

### 24.1. Ví dụ từ yêu cầu đến DTO

Yêu cầu: “Hiển thị danh sách sản phẩm đang hoạt động, kèm tên danh mục nếu có, giá, sắp theo tên.”

**Bước A — DTO:**

~~~java
package com.example.catalog.dto;

import java.math.BigDecimal;

public record ProductListRow(
    Long id,
    String name,
    String categoryName,
    BigDecimal price
) {}
~~~

**Bước B — query:**

~~~jpql
select new com.example.catalog.dto.ProductListRow(
    p.id,
    p.name,
    c.name,
    p.price
)
from Product p
left join p.category c
where p.status = :active
order by p.name asc, p.id asc
~~~

**Bước C — thực thi:**

~~~java
List<ProductListRow> rows = em.createQuery(
    jpql, ProductListRow.class
).setParameter("active", ProductStatus.ACTIVE)
 .setMaxResults(50)
 .getResultList();
~~~

**Bước D — diễn giải:** một row tương ứng một Product vì JOIN tới category là quan hệ nhiều-một. Category có thể null nhưng Product vẫn xuất hiện nhờ LEFT JOIN. Constructor nhận đúng **Long, String, String, BigDecimal**.

Đây là một ví dụ DTO projection phù hợp: đơn giản, không chứa entity references, không cần collection, chỉ tải dữ liệu dành cho màn hình.

## 25. Bài tập thực hành

### Bài 1: Chuyển Object[] sang constructor expression

Cho:

~~~java
List<Object[]> rows = em.createQuery(
    "select p.id, p.name, p.price from Product p",
    Object[].class
).getResultList();
~~~

Hãy định nghĩa DTO **ProductBrief(Long id, String name, BigDecimal price)** và viết lại JPQL để trả List<ProductBrief>.

**Gợi ý:**

~~~java
public record ProductBrief(Long id, String name, BigDecimal price) {}
~~~

~~~jpql
select new com.example.catalog.dto.ProductBrief(
    p.id, p.name, p.price
)
from Product p
~~~

Khi chạy, truyền **ProductBrief.class** cho EntityManager.createQuery() để được TypedQuery.

### Bài 2: Sai thứ tự và kiểu constructor

DTO:

~~~java
public record ProductRow2(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

Query:

~~~jpql
select new com.example.catalog.dto.ProductRow2(
    p.name, p.price, p.id
)
from Product p
~~~

**Câu hỏi:** Query có khớp constructor không?

**Đáp án:** Không. Constructor yêu cầu Long, String, BigDecimal nhưng query cung cấp String, BigDecimal, Long. Phải đảo đối số thành **p.id, p.name, p.price**.

### Bài 3: Category optional

Product.category cho phép null. Query hiện tại:

~~~jpql
select new com.example.catalog.dto.ProductSearchHit(
    p.id, p.name, c.name
)
from Product p join p.category c
~~~

**Yêu cầu:** giữ cả Product chưa phân loại.

**Gợi ý:** Đổi thành **left join p.category c**. Để categoryName null, hoặc dùng **coalesce(c.name, 'Chưa phân loại')** nếu đúng yêu cầu API.

### Bài 4: COUNT với DTO

DTO được khai báo:

~~~java
public record StatusCount(ProductStatus status, int count) {}
~~~

Query:

~~~jpql
select new com.example.catalog.dto.StatusCount(
    p.status, count(p)
)
from Product p
group by p.status
~~~

**Câu hỏi:** Chữ ký DTO có vấn đề không?

**Đáp án:** COUNT trả **Long**, nên nên dùng **Long count**, không phải int. Khi muốn int, chuyển có kiểm soát sau projection và xử lý overflow.

### Bài 5: Danh mục không có sản phẩm

Một Category chưa có Product. Báo cáo cần trả Category đó với productCount=0.

**Yêu cầu:** chọn INNER JOIN hay LEFT JOIN? Dùng count(c) hay count(p)?

**Đáp án:** **LEFT JOIN** để giữ Category trống; **count(p)** để kết quả bằng 0 cho nhóm không có Product.

### Bài 6: Tổng tiền đơn hàng

Có PurchaseOrder.lines và OrderLine.lineAmount: BigDecimal.

**Yêu cầu:** tạo OrderAmountRow(Long orderId, BigDecimal amount), lấy cả đơn chưa có dòng với amount=0.

**Gợi ý:**

~~~jpql
select new com.example.orders.dto.OrderAmountRow(
    o.id,
    coalesce(sum(l.lineAmount), :zero)
)
from PurchaseOrder o
left join o.lines l
group by o.id
~~~

Đặt **:zero = BigDecimal.ZERO**, kiểm tra DTO nhận BigDecimal.

### Bài 7: JOIN tags tạo DTO trùng

Một Product có ba Tag đều thỏa tìm kiếm. Query ProductSimpleRow JOIN p.tags và trả ba hàng có cùng productId.

**Câu hỏi:** Sửa như thế nào nếu chỉ muốn một Product?

**Gợi ý:** Có thể dùng **SELECT DISTINCT NEW** nếu các projection values tương ứng, hoặc dùng **WHERE EXISTS** để lọc Product mà không nhân hàng SELECT ngoài. Đừng tạo một HashSet DTO rồi mặc định coi đó là giải pháp tối ưu SQL.

### Bài 8: Nhiều JOIN làm SUM sai

Order có 3 lines, 2 coupons. Query JOIN cả hai rồi SUM(lineAmount) và thấy tổng tăng gấp đôi.

**Câu hỏi:** Dùng sum(distinct lineAmount) có chắc đúng?

**Đáp án:** Không. Hai line có cùng lineAmount hợp lệ sẽ bị DISTINCT gộp thành một giá trị, làm tổng sai. Cần tách aggregate, thiết kế query/CTE phù hợp hoặc xử lý hai tập dữ liệu độc lập trước khi ghép.

### Bài 9: Nested DTO

Bạn muốn:

~~~java
public record OrderDetail(
    Long id,
    List<OrderLineRow> lines
) {}
~~~

**Câu hỏi:** Một JPQL SELECT NEW với JOIN o.lines có tự tạo List<OrderLineRow> không?

**Đáp án:** Không theo cách thông thường của JPQL constructor expression. Nó tạo DTO theo hàng projection. Dùng hai query hoặc flat DTO rồi nhóm theo orderId.

### Bài 10: Pagination theo Order

Một truy vấn JOIN Order với lines trả 1000 hàng, nhưng bạn muốn 20 Order mỗi page. Nếu gọi setMaxResults(20) trên query phẳng, có đúng 20 Order không?

**Đáp án:** Không chắc. Một Order có nhiều lines chiếm nhiều hàng JOIN. Nên phân trang IDs/headers của 20 Order trước, sau đó tải lines của những Order đó trong một query khác.

### Bài 11: DTO không được managed

Một ProductRow mutable có setPrice(). Lập trình viên gọi setPrice(100) rồi commit transaction, mong products.price đổi.

**Câu hỏi:** Có xảy ra dirty checking không?

**Đáp án:** Không cho chính DTO. Nó không phải entity được quản lý. Muốn sửa dữ liệu phải load Product managed theo ID và gọi method nghiệp vụ trong transaction.

### Bài 12: Native SQL

Một query được viết:

~~~sql
SELECT new com.example.catalog.dto.ProductBrief(
    p.id, p.name, p.price
)
FROM products p
~~~

**Câu hỏi:** Có chạy bằng createNativeQuery() được không?

**Đáp án:** Không. SELECT NEW là JPQL, không phải cú pháp SQL. Dùng **createQuery()** với tên entity và thuộc tính Java, hoặc dùng native SQL + @SqlResultSetMapping/@ConstructorResult nếu cần SQL riêng DB.

### Bài 13: DTO chứa Category entity

~~~java
public record ProductWithCategory(Long id, Category category) {}
~~~

**Câu hỏi:** ProductWithCategory có hoàn toàn độc lập với persistence context không?

**Gợi ý:** DTO bên ngoài không managed, nhưng Category reference bên trong có thể là managed entity và vẫn có lazy associations. Nếu yêu cầu response độc lập, nên chọn categoryId/categoryName scalar hoặc DTO con.

### Bài 14: CASE WHEN

Ứng dụng cần mức giá **PREMIUM**, **STANDARD**, **BUDGET** tùy price.

**Yêu cầu:** trả ProductPriceLabel(Long id, String name, String priceLevel) từ một query.

**Gợi ý:** Dùng **CASE WHEN** trong danh sách SELECT NEW với ba nhánh String, truyền thresholds dưới dạng parameters thay vì hardcode giá trong Java string.

### Bài 15: Null vào primitive

DTO:

~~~java
public record ProductCategoryInfo(Long id, long categoryId) {}
~~~

Query LEFT JOIN Category có thể cho c.id null.

**Câu hỏi:** Cách sửa?

**Đáp án:** Dùng **Long categoryId** nếu null là giá trị hợp lệ. Không ép null vào primitive long.

### Bài 16: Spring Data projection

Một repository dùng **@Query** và return **Page<ProductRow>**. Data query có JOIN p.tags để lọc tagName, count query chỉ dùng **count(p)** với JOIN tương ứng.

**Câu hỏi:** Vì sao totalElements có thể sai?

**Gợi ý:** JOIN to-many có thể đếm một Product nhiều lần. Xác định đơn vị phân trang, cân nhắc **count(distinct p.id)** hoặc EXISTS trong count query theo ngữ nghĩa filter.

### Bài 17: Dữ liệu khách hàng và quyền truy cập

Một DTO chỉ có orderId và orderNumber, nhưng JPQL không lọc tenant/user và trả đơn hàng của mọi khách.

**Câu hỏi:** DTO có tự bảo vệ quyền truy cập không?

**Đáp án:** Không. Constructor expression không thay thế authorization. Query phải áp dụng điều kiện truy cập hợp lệ, tenant isolation và những field được phép trả.

## 26. Bảng tham chiếu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Chỉ cần vài trường của một entity | SELECT NEW DTO scalar |
| Cần thuộc tính của nhiều-một optional | LEFT JOIN, xử lý null |
| Cần đảm bảo chỉ những entity có association | INNER JOIN hoặc WHERE EXISTS |
| Cần số lượng mỗi nhóm | SELECT NEW với COUNT, GROUP BY, Long |
| Cần tổng tiền | SUM trên BigDecimal, xem null và cardinality JOIN |
| Cần giá trị trung bình | AVG trả Double theo ngữ nghĩa JPQL |
| Cần phân loại hiển thị theo điều kiện | CASE WHEN trong constructor expression |
| Cần chuỗi mặc định | COALESCE khi phù hợp contract |
| JOIN to-many làm lặp DTO | DISTINCT/EXISTS hoặc đổi cấu trúc query |
| Cần List con trong DTO | Hai query hoặc flat rows rồi grouping |
| Cần phân trang root có children | Phân trang root IDs/headers trước, tải children sau |
| Cần cập nhật database | Load entity managed thay vì sửa DTO |
| Cần SQL riêng DB | Native SQL với ConstructorResult hoặc mapping phù hợp |
| Có nhiều filter động | Criteria API với cb.construct hoặc JPQL xây dựng an toàn |
| Dùng Spring Data JPA | @Query SELECT NEW hoặc projection framework phù hợp |
| DTO constructor báo lỗi | Kiểm tra FQCN, số lượng, thứ tự, kiểu, nullability |
| Query chậm | Xem SQL/EXPLAIN, cardinality, index, sort và pagination |
| Cần dữ liệu an toàn theo người dùng | Thêm authorization/tenant predicates |

## 27. Tổng kết

**JPQL constructor expression** cho phép viết **SELECT NEW tên.package.DTO(...)** để JPA provider tạo object kết quả theo constructor từ các biểu thức được chọn. Đây là kỹ thuật trực tiếp, rõ ràng và hữu ích cho **read model, trang danh sách, báo cáo và REST API** khi không cần tải toàn bộ entity managed.

Muốn dùng hiệu quả, hãy đảm bảo bốn điều:

1. **Chữ ký constructor khớp tuyệt đối** số lượng, vị trí, kiểu Java và nullability của các biểu thức JPQL. Đặc biệt COUNT trả Long, AVG trả Double và LEFT JOIN có thể trả null.
2. **Một hàng projection tương ứng một DTO.** JOIN to-many có thể tạo nhiều hàng; SELECT NEW không tự gom các children thành List lồng nhau. Cần GROUP BY, EXISTS, DISTINCT, hoặc quá trình ghép DTO có chủ đích tùy yêu cầu.
3. **DTO không tự được JPA quản lý.** Nó phù hợp để đọc và truyền dữ liệu; thao tác ghi vẫn cần entity managed, transaction và validation/authorization phù hợp.
4. **Hiệu năng đến từ hình dạng truy vấn thực tế.** Chọn ít cột, JOIN đúng cardinality, filter và index tốt, phân trang đúng đơn vị. Constructor expression là một công cụ biểu diễn kết quả, không thay thế việc thiết kế SQL/JPQL.

Khi hệ thống cần kết quả gọn, typed và ít phụ thuộc vào persistence context, **SELECT NEW DTO** là một lựa chọn quan trọng trong bộ công cụ JPQL nâng cao. Hãy sử dụng nó theo đúng **use case**, kiểm tra chữ ký constructor và hiểu rõ dữ liệu nào thực sự được trả về trước khi tối ưu hoặc đưa ra API công khai.
