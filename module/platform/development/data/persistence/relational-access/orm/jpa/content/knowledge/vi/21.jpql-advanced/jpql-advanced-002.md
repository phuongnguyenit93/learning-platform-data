# Nhóm và lọc nhóm bằng GROUP BY và HAVING trong JPQL

Trong truy vấn dữ liệu quan hệ, nhiều yêu cầu không hỏi “những bản ghi nào thỏa điều kiện?” mà hỏi **“mỗi nhóm có bao nhiêu bản ghi, tổng giá trị là bao nhiêu, trung bình là bao nhiêu, và nhóm nào đạt một ngưỡng nhất định?”**. Ví dụ: mỗi danh mục có bao nhiêu sản phẩm đang bán; mỗi khách hàng có bao nhiêu đơn đã thanh toán; doanh thu của từng tháng; danh mục nào có giá trung bình vượt một mức tiền; khách hàng nào có ít nhất ba đơn trong một khoảng thời gian.

Trong Jakarta Persistence (JPA), ta có thể diễn đạt các câu hỏi đó bằng **JPQL (Jakarta Persistence Query Language)** với hai mệnh đề quan trọng:

- `GROUP BY`: **gom các dòng đầu vào thành các nhóm** theo một hoặc nhiều biểu thức/thuộc tính.
- `HAVING`: **lọc các nhóm sau khi phép gom nhóm và tính toán aggregate được áp dụng**.

Ví dụ:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c
JOIN c.products p
WHERE p.status = :status
GROUP BY c.code
HAVING COUNT(p) >= :minCount
ORDER BY COUNT(p) DESC, c.code ASC
~~~

Truy vấn này không trả một entity `Product` trên mỗi hàng kết quả. Nó trả **một hàng cho mỗi mã danh mục đạt điều kiện**, chứa mã danh mục và số sản phẩm được đếm. `WHERE` loại các sản phẩm không đúng trạng thái trước khi nhóm; `HAVING` chỉ giữ các danh mục có đủ số sản phẩm sau khi đã đếm.

Điểm cần nắm vững là JPQL viết trên **entity và thuộc tính Java**, không viết trực tiếp trên tên bảng và tên cột SQL. Bên cạnh cú pháp, người học phải hiểu ngữ nghĩa JOIN, NULL, các hàm aggregate, kiểu kết quả của JPA và cách tránh các phép đếm sai khi một entity bị nhân bản bởi JOIN.

## 1. GROUP BY và HAVING giải quyết bài toán gì?

Giả sử cửa hàng có dữ liệu:

| Danh mục | SKU | Tình trạng | Giá |
| --- | --- | --- | ---: |
| BOOK | BK-01 | ACTIVE | 100.000 |
| BOOK | BK-02 | ACTIVE | 200.000 |
| BOOK | BK-03 | DRAFT | 300.000 |
| TECH | TC-01 | ACTIVE | 900.000 |
| TECH | TC-02 | ACTIVE | 1.100.000 |
| GAME | GM-01 | DRAFT | 400.000 |

Yêu cầu: **Tìm các danh mục có ít nhất hai sản phẩm ACTIVE**, kèm số lượng và giá trung bình của sản phẩm ACTIVE.

Kết quả mong muốn:

| Mã danh mục | Số sản phẩm ACTIVE | Giá trung bình ACTIVE |
| --- | ---: | ---: |
| BOOK | 2 | 150.000 |
| TECH | 2 | 1.000.000 |

Danh mục GAME không thỏa vì không có sản phẩm ACTIVE. Ta cần:

1. Chọn các sản phẩm ACTIVE.
2. Nhóm chúng theo danh mục.
3. Đếm sản phẩm và tính trung bình từng nhóm.
4. Giữ các nhóm có số lượng từ hai trở lên.
5. Sắp xếp kết quả nếu cần.

Đó chính là công việc kết hợp **WHERE → GROUP BY → HAVING → ORDER BY**.

### Sơ đồ xử lý logic

~~~text
Nguồn entity và các JOIN
            |
            v
WHERE: lọc từng dòng đầu vào
            |
            v
GROUP BY: phân dòng vào các nhóm
            |
            v
COUNT / SUM / AVG / MIN / MAX: tính trên từng nhóm
            |
            v
HAVING: loại những nhóm không đủ điều kiện
            |
            v
SELECT: biểu diễn kết quả nhóm
            |
            v
ORDER BY, pagination: trình bày/trả trang
~~~

Đây là **thứ tự diễn giải logic**, không phải cam kết về thứ tự các toán tử trong kế hoạch thực thi vật lý của database. DBMS có quyền tối ưu hóa SQL thành hash aggregation, sort aggregation, index scan hoặc các kế hoạch khác mà vẫn giữ đúng ngữ nghĩa truy vấn.

## 2. Mô hình entity dùng trong bài

Ta sử dụng hệ thống catalog và đơn hàng:

~~~text
Category (1) ---- (N) Product
   id                  id
   code                sku
   name                price
                       status
                       stockQuantity
                       category_id

Customer (1) ---- (N) PurchaseOrder (1) ---- (N) OrderLine
   id                      id                       id
   email                   customer_id              order_id
                           status                   product_id
                           placedAt                 quantity
                           businessDate             lineTotal
~~~

Quy tắc nghiệp vụ ví dụ:

- Mỗi sản phẩm thuộc một danh mục.
- Mỗi đơn hàng thuộc một khách hàng.
- Mỗi dòng đơn hàng thuộc một đơn, tham chiếu một sản phẩm.
- `OrderLine.lineTotal` là giá trị tiền của dòng đã được tính và lưu theo quy tắc nghiệp vụ, không đơn giản lấy giá Product hiện tại để tính lại lịch sử.
- Các báo cáo doanh thu chỉ cộng các đơn ở trạng thái đã được nghiệp vụ công nhận, chẳng hạn `PAID`. Nếu có hoàn tiền, hủy đơn hoặc điều chỉnh, phải xử lý trong mô hình dữ liệu và quy tắc báo cáo riêng.

### 2.1. Entity Category

~~~java
package com.example.shop;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

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

    @OneToMany(mappedBy = "category")
    private List<Product> products = new ArrayList<>();

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

### 2.2. Entity Product

~~~java
package com.example.shop;

import jakarta.persistence.*;
import java.math.BigDecimal;

public enum ProductStatus {
    DRAFT, ACTIVE, INACTIVE
}

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true)
    private String sku;

    @Column(name = "price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private ProductStatus status;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    private Category category;

    protected Product() {
    }
}
~~~

Trong mã Java thực tế, `ProductStatus` nên được đặt trong file `ProductStatus.java` vì là top-level public enum. Ví dụ gộp kiểu liên quan để người học dễ nhìn cấu trúc ánh xạ.

### 2.3. Customer, PurchaseOrder và OrderLine

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }
}
~~~

~~~java
public enum OrderStatus {
    NEW, PAID, CANCELLED, REFUNDED
}

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(name = "placed_at", nullable = false)
    private Instant placedAt;

    @Column(name = "business_date", nullable = false)
    private LocalDate businessDate;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }
}
~~~

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "line_total", nullable = false,
            precision = 18, scale = 2)
    private BigDecimal lineTotal;

    protected OrderLine() {
    }
}
~~~

Các đoạn Customer, PurchaseOrder và OrderLine giả sử import các annotation từ `jakarta.persistence`, collection từ `java.util`, `java.math.BigDecimal` cùng `java.time.Instant` / `LocalDate` phù hợp. Những class/enum public riêng phải nằm trong source file Java tương ứng.

### 2.4. Vì sao có businessDate?

`placedAt` biểu diễn **thời điểm tuyệt đối** bằng `Instant`. `businessDate` biểu diễn **ngày kinh doanh đã được xác định** theo múi giờ và quy tắc của cửa hàng. Nếu báo cáo theo ngày bằng một thuộc tính `LocalDate` rõ ràng, ta tránh phụ thuộc vào hàm `DATE()` hoặc cách trích ngày theo timezone khác nhau của DBMS.

Trong hệ thống thực, phải xác định businessDate từ placedAt và timezone theo một quy tắc nghiệp vụ thống nhất. Hai trường này không thay thế nhau.

## 3. Nhớ lại: JPQL dùng tên entity và thuộc tính Java

Đúng:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c JOIN c.products p
GROUP BY c.code
~~~

Không dùng tên bảng hoặc cột SQL vật lý thay cho tên thuộc tính:

~~~sql
-- Đây là SQL, không phải JPQL:
SELECT c.code, COUNT(p.id)
FROM categories c JOIN products p ON p.category_id = c.id
GROUP BY c.code;
~~~

Khác biệt:

| JPQL | SQL vật lý minh họa |
| --- | --- |
| `Category` | `categories` |
| `Product` | `products` |
| `c.products` | Quan hệ qua FK `products.category_id` |
| `p.stockQuantity` | `products.stock_quantity` |
| `o.businessDate` | `purchase_orders.business_date` |
| `ol.lineTotal` | `order_lines.line_total` |

JPA provider dịch đường dẫn quan hệ và thuộc tính thành SQL. Đây là lý do cùng một JPQL có thể chạy trên các DBMS khác nhau khi mapping và những tính năng sử dụng được hỗ trợ.

## 4. Một truy vấn GROUP BY tối giản

Đếm sản phẩm theo danh mục:

~~~jpql
SELECT c.code, COUNT(p)
FROM Product p JOIN p.category c
GROUP BY c.code
~~~

Chạy qua EntityManager:

~~~java
TypedQuery<Object[]> query = em.createQuery(
    "SELECT c.code, COUNT(p) " +
    "FROM Product p JOIN p.category c " +
    "GROUP BY c.code",
    Object[].class
);

List<Object[]> rows = query.getResultList();

for (Object[] row : rows) {
    String categoryCode = (String) row[0];
    Long productCount = (Long) row[1];
    System.out.println(categoryCode + ": " + productCount);
}
~~~

Ý nghĩa:

- `Product p` là các entity sản phẩm.
- `JOIN p.category c` đi theo quan hệ many-to-one.
- `GROUP BY c.code` tạo một nhóm cho mỗi giá trị mã danh mục.
- `COUNT(p)` đếm số sản phẩm trong nhóm.
- Kết quả là các giá trị **scalar**, không phải một entity Category/Product được quản lý.

**Quan trọng:** `COUNT` trong JPQL trả kiểu `Long`. Không dùng `Integer` chỉ vì bảng hiện có ít dữ liệu.

### Một thuộc tính GROUP BY là một khóa nhóm

Nếu có ba sản phẩm thuộc BOOK và hai sản phẩm thuộc TECH:

~~~text
Input rows:
(BOOK, Product#1)
(BOOK, Product#2)
(BOOK, Product#3)
(TECH, Product#4)
(TECH, Product#5)

Sau GROUP BY c.code:
BOOK -> [#1, #2, #3]
TECH -> [#4, #5]

Sau COUNT(p):
(BOOK, 3)
(TECH, 2)
~~~

Trong phép nhóm này, tất cả Product thuộc cùng mã danh mục tạo một nhóm, bất kể thứ tự đọc hàng đầu vào.

## 5. GROUP BY theo nhiều thuộc tính

Một báo cáo có thể cần đếm theo **danh mục và trạng thái**:

~~~jpql
SELECT c.code, p.status, COUNT(p)
FROM Product p JOIN p.category c
GROUP BY c.code, p.status
ORDER BY c.code ASC, p.status ASC
~~~

Với BOOK có ACTIVE và DRAFT, đây là **hai nhóm khác nhau**:

~~~text
BOOK + ACTIVE  -> 2
BOOK + DRAFT   -> 1
TECH + ACTIVE  -> 2
GAME + DRAFT   -> 1
~~~

Quy tắc:

- Mỗi tổ hợp giá trị của các biểu thức nhóm xác định một nhóm.
- Cùng danh mục nhưng khác trạng thái sẽ xuất hiện trên các hàng kết quả khác nhau.
- Muốn gộp mọi trạng thái của danh mục, **không** đưa `p.status` vào GROUP BY; hoặc dùng tổng hợp có điều kiện nếu cần đếm từng trạng thái trên một dòng.

Ví dụ Java:

~~~java
TypedQuery<Object[]> q = em.createQuery(
    "SELECT c.code, p.status, COUNT(p) " +
    "FROM Product p JOIN p.category c " +
    "GROUP BY c.code, p.status " +
    "ORDER BY c.code ASC, p.status ASC",
    Object[].class
);

for (Object[] row : q.getResultList()) {
    String code = (String) row[0];
    ProductStatus status = (ProductStatus) row[1];
    Long count = (Long) row[2];
    System.out.println(code + " " + status + ": " + count);
}
~~~

Tham số và enum dùng kiểu Java theo mapping; `@Enumerated(EnumType.STRING)` ảnh hưởng cách lưu ở DB, không làm JPQL trả chuỗi SQL `"ACTIVE"` thay cho enum Java trong một projection theo entity attribute.

## 6. Các hàm tổng hợp trong JPQL

Các aggregate tiêu biểu:

| Hàm | Ý nghĩa | Kiểu kết quả thường gặp |
| --- | --- | --- |
| `COUNT(x)` | Đếm các giá trị không null của biểu thức x | `Long` |
| `COUNT(DISTINCT x)` | Đếm số giá trị x khác nhau và không null | `Long` |
| `SUM(x)` | Tổng các giá trị số không null | Phụ thuộc kiểu số của x |
| `AVG(x)` | Giá trị trung bình của các giá trị số không null | `Double` theo JPQL |
| `MIN(x)` | Giá trị nhỏ nhất không null | Theo kiểu thuộc tính x |
| `MAX(x)` | Giá trị lớn nhất không null | Theo kiểu thuộc tính x |

Với `Product.price` là `BigDecimal`:

~~~jpql
SELECT c.code,
       COUNT(p),
       MIN(p.price),
       MAX(p.price),
       AVG(p.price),
       SUM(p.price)
FROM Product p JOIN p.category c
GROUP BY c.code
~~~

Các giá trị:

- `COUNT(p)`: `Long`.
- `MIN(p.price)` và `MAX(p.price)`: `BigDecimal`.
- `AVG(p.price)`: `Double`.
- `SUM(p.price)`: `BigDecimal`.

### Quy tắc kiểu kết quả của SUM

Trong JPQL, kiểu kết quả `SUM` phụ thuộc kiểu số của biểu thức được tính:

- Kiểu số nguyên thông thường: thường là `Long`.
- `BigInteger`: `BigInteger`.
- `BigDecimal`: `BigDecimal`.
- Kiểu số thực thông thường: `Double`.

`AVG` trả `Double` theo quy tắc JPQL, ngay cả khi nguồn là `BigDecimal`. Nếu doanh nghiệp cần **trung bình tiền chính xác theo chính sách rounding cụ thể**, cần xác định giải pháp tính và kiểu dữ liệu thích hợp; đừng giả định `AVG(price)` luôn trả `BigDecimal`.

### SUM trên số lượng kiểu int

Entity có:

~~~java
private int stockQuantity;
~~~

Nên sử dụng:

~~~java
TypedQuery<Long> q = em.createQuery(
    "SELECT SUM(p.stockQuantity) " +
    "FROM Product p WHERE p.status = :status",
    Long.class
);
~~~

Với `int`/`Integer`, tổng có thể lớn hơn phạm vi int nên `Long` phù hợp. Cần chú ý nếu toàn bộ tập dữ liệu rỗng, `SUM` không trả 0 mặc định (xem phần NULL).

## 7. WHERE và HAVING khác nhau ở chỗ nào?

**WHERE lọc từng dòng trước khi nhóm. HAVING lọc nhóm sau khi tính aggregate.**

Đếm sản phẩm ACTIVE của từng danh mục và giữ các danh mục có ít nhất hai sản phẩm ACTIVE:

~~~jpql
SELECT c.code, COUNT(p)
FROM Product p JOIN p.category c
WHERE p.status = :status
GROUP BY c.code
HAVING COUNT(p) >= :minCount
~~~

Ở đây:

- `WHERE p.status = :status` loại Product DRAFT/INACTIVE khỏi đầu vào của phép đếm.
- `GROUP BY c.code` tạo nhóm danh mục từ các Product ACTIVE còn lại.
- `COUNT(p)` đếm các Product ACTIVE trong nhóm.
- `HAVING COUNT(p) >= :minCount` loại những nhóm không đủ số lượng.

### Ví dụ với dữ liệu

~~~text
Trước WHERE:
BOOK: ACTIVE, ACTIVE, DRAFT
TECH: ACTIVE, ACTIVE
GAME: DRAFT

Sau WHERE status=ACTIVE:
BOOK: ACTIVE, ACTIVE
TECH: ACTIVE, ACTIVE
GAME: không còn dòng

GROUP BY / COUNT:
BOOK=2, TECH=2

HAVING COUNT>=2:
BOOK=2, TECH=2
~~~

**GAME không tự xuất hiện với COUNT=0** trong truy vấn bắt đầu từ Product và dùng INNER JOIN; muốn hiển thị cả danh mục trống, cần bắt đầu từ Category và sử dụng LEFT JOIN theo cách phù hợp.

## 8. Vì sao aggregate không thuộc WHERE?

Câu sau sai về ý nghĩa và cú pháp nhóm:

~~~jpql
SELECT c.code, COUNT(p)
FROM Product p JOIN p.category c
WHERE COUNT(p) >= 2
GROUP BY c.code
~~~

`WHERE` được áp dụng trên các dòng đầu vào trước khi nhóm, nên không dùng trực tiếp aggregate của nhóm như `COUNT(p)` trong predicate WHERE ở cùng query block.

Cách đúng:

~~~jpql
SELECT c.code, COUNT(p)
FROM Product p JOIN p.category c
GROUP BY c.code
HAVING COUNT(p) >= 2
~~~

### Có thể đặt điều kiện thông thường trong HAVING không?

Một số điều kiện trên khóa nhóm có thể được diễn đạt trong HAVING, ví dụ `HAVING c.code <> :excludedCode`. Tuy nhiên, khi điều kiện **không cần biết kết quả aggregate**, thường nên viết trong WHERE:

~~~jpql
WHERE c.code <> :excludedCode
GROUP BY c.code
HAVING COUNT(p) >= :minCount
~~~

Việc lọc trước giúp nêu rõ ý nghĩa và thường cho database thêm cơ hội giảm dữ liệu đầu vào. Không dùng HAVING thay WHERE theo thói quen.

## 9. Một ví dụ TypedQuery hoàn chỉnh với WHERE và HAVING

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import java.util.List;

public List<Object[]> findLargeCategories(
        EntityManager em,
        ProductStatus status,
        long minCount) {

    if (minCount < 1) {
        throw new IllegalArgumentException(
                "minCount phải >= 1");
    }

    TypedQuery<Object[]> query = em.createQuery(
        "SELECT c.code, COUNT(p) " +
        "FROM Product p JOIN p.category c " +
        "WHERE p.status = :status " +
        "GROUP BY c.code " +
        "HAVING COUNT(p) >= :minCount " +
        "ORDER BY COUNT(p) DESC, c.code ASC",
        Object[].class
    );

    return query
        .setParameter("status", status)
        .setParameter("minCount", minCount)
        .getResultList();
}
~~~

Điểm đáng lưu ý:

1. `COUNT(p)` có kiểu `Long`, nên `minCount` có thể dùng `long`.
2. `TypedQuery<Object[]>` phù hợp khi SELECT nhiều biểu thức scalar.
3. Named parameters `:status`, `:minCount` được bind riêng; không nối input vào JPQL.
4. `ORDER BY COUNT(p) DESC, c.code ASC` có tie-breaker để sắp xếp nhóm khi có cùng số lượng.
5. Nếu không có nhóm nào thỏa, `getResultList()` trả danh sách rỗng, không phải `null`.

## 10. Quy tắc SELECT khi đã dùng GROUP BY

Khi một query có GROUP BY, các biểu thức trong SELECT phải nhất quán với ý nghĩa **một kết quả cho mỗi nhóm**.

Ví dụ đúng:

~~~jpql
SELECT c.code, COUNT(p), MAX(p.price)
FROM Product p JOIN p.category c
GROUP BY c.code
~~~

`c.code` là khóa nhóm. `COUNT(p)` và `MAX(p.price)` là aggregate của từng nhóm.

Ví dụ sai hoặc không có ý nghĩa portable:

~~~jpql
SELECT c.code, p.sku, COUNT(p)
FROM Product p JOIN p.category c
GROUP BY c.code
~~~

Vì một danh mục có thể chứa nhiều SKU, **SKU nào sẽ được trả về đại diện cho cả nhóm?** Không có lựa chọn duy nhất được xác định bởi GROUP BY `c.code`.

### Cách sửa

Nếu muốn **đếm theo từng SKU**:

~~~jpql
SELECT c.code, p.sku, COUNT(p)
FROM Product p JOIN p.category c
GROUP BY c.code, p.sku
~~~

Nếu muốn **SKU nhỏ nhất theo thứ tự từ điển** của mỗi danh mục:

~~~jpql
SELECT c.code, MIN(p.sku), COUNT(p)
FROM Product p JOIN p.category c
GROUP BY c.code
~~~

Nếu muốn một **sản phẩm đại diện theo tiêu chí phức tạp** (ví dụ sản phẩm đắt nhất nhưng hòa giá phải lấy ID nhỏ nhất), cần thiết kế subquery hoặc một bước truy vấn khác; không lấy `p.sku` ngẫu nhiên từ một nhóm.

### Đừng phụ thuộc vào chế độ SQL “dễ dãi”

Một số DBMS/chế độ SQL có thể cho phép SELECT cột không nằm trong GROUP BY hoặc aggregate rồi trả giá trị không xác định. Điều đó không phải quy tắc an toàn/portable của JPQL. Nên viết truy vấn sao cho **mỗi biểu thức được chọn có ý nghĩa xác định cho một nhóm**.

## 11. GROUP BY theo khóa định danh và thuộc tính hiển thị

Thực tế, danh mục có:

~~~text
id=1, code=BOOK, name=Sách
id=2, code=TECH, name=Thiết bị
~~~

Nếu báo cáo cần cả `id`, `code` và `name`:

~~~jpql
SELECT c.id, c.code, c.name, COUNT(p)
FROM Category c LEFT JOIN c.products p
GROUP BY c.id, c.code, c.name
ORDER BY c.code ASC
~~~

Ưu điểm:

- `c.id` là khóa chính xác định danh mục.
- `c.code` và `c.name` là thông tin hiển thị.
- Cả ba thuộc tính non-aggregate xuất hiện trong GROUP BY, làm ý nghĩa query rõ ràng.
- `LEFT JOIN` giữ lại category không có sản phẩm, được đếm 0.

### Chỉ GROUP BY theo tên có đủ không?

Không nhất thiết. Hai category có thể vô tình cùng tên hiển thị:

~~~text
id=10, code=BOOK-VN, name=Sách
id=11, code=BOOK-EN, name=Sách
~~~

Nếu chỉ `GROUP BY c.name`, hai category này sẽ bị gộp vào cùng nhóm. Khi đối tượng báo cáo là **mỗi category entity**, nên dùng khóa định danh hoặc bộ business key thực sự duy nhất. Tên hiển thị không phải lúc nào cũng là key.

### GROUP BY toàn entity

Một số cú pháp JPQL cho phép nhóm theo một entity trong những điều kiện nhất định, nhưng khả năng diễn dịch/phạm vi hỗ trợ có giới hạn liên quan mapping và provider. Khi cần tính portable, nhất là với eager relationship hoặc kiểu dữ liệu LOB/serialized, **nhóm tường minh theo scalar key và các thuộc tính được chọn** thường rõ ràng hơn `GROUP BY c`.

## 12. INNER JOIN có thể làm biến mất nhóm không có phần tử

Truy vấn:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c JOIN c.products p
GROUP BY c.code
~~~

dùng **INNER JOIN**. Với danh mục GAME không có sản phẩm, không có dòng join nào tương ứng nên không có nhóm GAME trong kết quả.

Muốn báo cáo tất cả category, kể cả category không có Product:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c LEFT JOIN c.products p
GROUP BY c.code
ORDER BY c.code ASC
~~~

Với LEFT JOIN:

~~~text
Category BOOK -> Product#1, Product#2, Product#3
Category TECH -> Product#4, Product#5
Category EMPTY -> NULL phía Product
~~~

Kết quả:

~~~text
BOOK  -> 3
TECH  -> 2
EMPTY -> 0
~~~

`COUNT(p)` đếm các giá trị `p` **không null**, nên nhóm category không có sản phẩm trả 0.

### Tại sao `COUNT(c)` không giống `COUNT(p)`?

Khi bắt đầu từ Category, ngay cả category EMPTY vẫn có một dòng Category ở phía trái của LEFT JOIN:

~~~jpql
SELECT c.code, COUNT(c), COUNT(p)
FROM Category c LEFT JOIN c.products p
GROUP BY c.code
~~~

Với EMPTY:

~~~text
COUNT(c) = 1
COUNT(p) = 0
~~~

Với BOOK có ba Product, `COUNT(c)` có thể bằng 3 vì Category được lặp lại trên ba dòng join. **Đếm phía nào là quyết định về ngữ nghĩa báo cáo**, không chỉ thay tên biến.

## 13. Lọc LEFT JOIN sai chỗ làm mất nhóm rỗng

Giả sử muốn hiển thị **mọi category và số sản phẩm ACTIVE**, kể cả category có 0 sản phẩm ACTIVE.

Truy vấn dễ viết nhưng có vấn đề:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c LEFT JOIN c.products p
WHERE p.status = :active
GROUP BY c.code
~~~

Với category không có sản phẩm, `p` là NULL và điều kiện `p.status = :active` không đúng. Dòng này bị loại ở WHERE, nên LEFT JOIN **mất tác dụng giữ category rỗng** cho truy vấn cụ thể.

### Cách đúng khi muốn đếm phần tử match mà vẫn giữ category

Sử dụng điều kiện trên JOIN:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c
LEFT JOIN c.products p ON p.status = :active
GROUP BY c.code
ORDER BY c.code ASC
~~~

Giải thích:

- Category là tập bên trái.
- LEFT JOIN chỉ gắn các Product ACTIVE.
- Category không có Product ACTIVE vẫn còn một dòng với `p = NULL`.
- `COUNT(p)` bằng 0 cho category đó.

`JOIN ... ON` là cú pháp JPQL được hỗ trợ trong các phiên bản JPA hiện đại; cần xác nhận phiên bản Jakarta Persistence/provider của dự án nếu làm việc với stack cũ. Cú pháp `WITH` trong HQL là một biến thể provider-specific, không nên nhầm là từ khóa JPQL chuẩn thay cho `ON`.

### So sánh

| Câu truy vấn | Category có 0 Product ACTIVE có xuất hiện? |
| --- | --- |
| `JOIN c.products p WHERE p.status = :active` | Không |
| `LEFT JOIN c.products p WHERE p.status = :active` | Không, vì WHERE loại dòng NULL |
| `LEFT JOIN c.products p ON p.status = :active` | Có, với COUNT(p)=0 |

Đây là lỗi rất phổ biến khi viết báo cáo nhóm có yêu cầu hiển thị các nhóm **không có bản ghi con**.

## 14. HAVING kết hợp LEFT JOIN: chọn nhóm có ít nhất một phần tử

Khi đã dùng LEFT JOIN:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c LEFT JOIN c.products p
GROUP BY c.code
HAVING COUNT(p) >= :minCount
~~~

- `minCount = 0`: có thể giữ cả category trống.
- `minCount = 1`: chỉ giữ category có ít nhất một Product.
- `minCount = 3`: chỉ giữ category có ít nhất ba Product.

Nếu muốn **chỉ category chưa có sản phẩm**:

~~~jpql
SELECT c.code
FROM Category c LEFT JOIN c.products p
GROUP BY c.code
HAVING COUNT(p) = 0
~~~

Cũng có thể diễn đạt bằng subquery với `NOT EXISTS`:

~~~jpql
SELECT c.code
FROM Category c
WHERE NOT EXISTS (
    SELECT p.id FROM Product p
    WHERE p.category = c
)
~~~

Hai cách diễn đạt cùng ý nghĩa nghiệp vụ trong mô hình này nhưng có thể có query plan khác nhau. Không thể khẳng định một cách luôn nhanh hơn nếu chưa xem execution plan của DBMS với dữ liệu thực.

## 15. Giá trị NULL trong COUNT, SUM, AVG, MIN và MAX

Quy tắc tổng quát: các hàm aggregate thông thường **bỏ qua giá trị NULL của biểu thức đầu vào**, ngoại trừ khác biệt giữa các cách đếm.

Giả sử một nhóm có các giá trị doanh thu:

~~~text
100.00
NULL
300.00
~~~

Kết quả:

| Biểu thức | Giá trị |
| --- | ---: |
| `COUNT(x)` | 2 |
| `SUM(x)` | 400.00 |
| `AVG(x)` | 200.00 |
| `MIN(x)` | 100.00 |
| `MAX(x)` | 300.00 |

`AVG` chia cho **số giá trị không NULL**, không phải tổng số hàng của nhóm.

### COUNT trên giá trị nullable

Nếu một thuộc tính như `p.optionalExternalCode` có thể null, thì `COUNT(p.optionalExternalCode)` đếm những Product có code không null, còn `COUNT(p)` đếm Product entity hợp lệ của nhóm. Hai phép đếm phục vụ hai câu hỏi khác nhau.

### Một nhóm không có giá trị số phù hợp

Với LEFT JOIN không có hàng con, `COUNT(child)` trả 0, còn `SUM(child.amount)` hoặc `AVG(child.amount)` thường trả **NULL**, không tự trả số 0.

Điều này ảnh hưởng tới kiểu trả về Java và điều kiện HAVING:

~~~jpql
HAVING SUM(ol.lineTotal) >= :threshold
~~~

Nhóm có SUM NULL sẽ không vượt điều kiện này. Nếu muốn diễn đạt số 0 cho nhóm rỗng, dùng `COALESCE` theo kiểu kết quả rõ ràng.

## 16. COALESCE để biểu diễn tổng bằng 0 khi nhóm không có dữ liệu

Giả sử báo cáo doanh thu theo Customer, giữ cả khách hàng chưa có đơn:

~~~jpql
SELECT c.id, COALESCE(SUM(ol.lineTotal), :zero)
FROM Customer c
LEFT JOIN c.orders o
LEFT JOIN o.lines ol
GROUP BY c.id
~~~

Java:

~~~java
TypedQuery<Object[]> query = em.createQuery(
    "SELECT c.id, COALESCE(SUM(ol.lineTotal), :zero) " +
    "FROM Customer c " +
    "LEFT JOIN c.orders o " +
    "LEFT JOIN o.lines ol " +
    "GROUP BY c.id " +
    "ORDER BY c.id",
    Object[].class
);

List<Object[]> rows = query
    .setParameter("zero", BigDecimal.ZERO)
    .getResultList();
~~~

Với `OrderLine.lineTotal` kiểu `BigDecimal`, `SUM` phù hợp với kiểu tiền này. Việc bind `BigDecimal.ZERO` giúp diễn đạt rõ kiểu của nhánh thay thế.

**Tuy nhiên, đây chưa phải truy vấn “doanh thu đã thanh toán” hoàn chỉnh.** Nó đang cộng mọi dòng ở mọi Order bất kể trạng thái; nếu chỉ doanh thu của Order PAID, phải thêm điều kiện lọc đúng vị trí (trên JOIN hoặc dùng biểu thức tổng hợp có điều kiện), và xác định refund/discount/tax theo nghiệp vụ.

### COALESCE không thay bản chất NULL

Có những báo cáo cần phân biệt:

- **Không có dữ liệu**: SUM/AVG là NULL.
- **Có dữ liệu nhưng tổng bằng 0**: SUM thực sự bằng 0.

Nếu gộp cả hai thành 0 bằng COALESCE, thông tin này bị mất. Hãy chọn cách trình bày theo yêu cầu báo cáo, không tự động COALESCE mọi aggregate.

## 17. HAVING dùng nhiều điều kiện aggregate

Ví dụ tìm danh mục có:

- Ít nhất năm sản phẩm ACTIVE.
- Giá trung bình ACTIVE trên 500.000.

~~~jpql
SELECT c.code, COUNT(p), AVG(p.price)
FROM Product p JOIN p.category c
WHERE p.status = :active
GROUP BY c.code
HAVING COUNT(p) >= :minCount
   AND AVG(p.price) > :minAvgPrice
ORDER BY AVG(p.price) DESC, c.code ASC
~~~

Java:

~~~java
TypedQuery<Object[]> query = em.createQuery(
    "SELECT c.code, COUNT(p), AVG(p.price) " +
    "FROM Product p JOIN p.category c " +
    "WHERE p.status = :active " +
    "GROUP BY c.code " +
    "HAVING COUNT(p) >= :minCount " +
    "AND AVG(p.price) > :minAverage " +
    "ORDER BY AVG(p.price) DESC, c.code ASC",
    Object[].class
);

List<Object[]> rows = query
    .setParameter("active", ProductStatus.ACTIVE)
    .setParameter("minCount", 5L)
    .setParameter("minAverage", 500000.0)
    .getResultList();

for (Object[] row : rows) {
    String code = (String) row[0];
    Long count = (Long) row[1];
    Double avg = (Double) row[2];
}
~~~

Trong ví dụ `AVG` trả `Double`; ngưỡng được truyền là `Double` tương thích với biểu thức aggregate. Với nghiệp vụ tài chính, cần chú ý sai số tính toán và chính sách rounding khi so sánh trung bình tiền. Nếu yêu cầu tính toán tài chính tuyệt đối chính xác, cần phương án kiểu số và SQL phù hợp với domain.

### Dùng OR trong HAVING

~~~jpql
HAVING COUNT(p) >= :minCount
    OR MAX(p.price) >= :premiumPrice
~~~

Ý nghĩa: giữ nhóm nếu **có đủ số lượng hoặc có ít nhất một mức giá tối đa đạt ngưỡng**. Nên dùng dấu ngoặc khi AND/OR kết hợp phức tạp để tránh hiểu sai độ ưu tiên logic.

## 18. COUNT(DISTINCT ...) để tránh đếm trùng do JOIN

Một nguồn lỗi phổ biến là **JOIN tạo nhiều hàng từ cùng một entity gốc**.

Ví dụ Customer C1 có:

~~~text
Order O1:
  Line L1
  Line L2
  Line L3

Order O2:
  Line L4
~~~

Truy vấn:

~~~jpql
SELECT c.id, COUNT(o)
FROM Customer c
JOIN c.orders o
JOIN o.lines ol
GROUP BY c.id
~~~

Do JOIN sang OrderLine, số dòng đầu vào cho C1 là:

~~~text
C1 O1 L1
C1 O1 L2
C1 O1 L3
C1 O2 L4
~~~

`COUNT(o)` có thể trả **4**, mặc dù C1 chỉ có **2 Order**.

### Cách đếm đúng số Order

~~~jpql
SELECT c.id, COUNT(DISTINCT o.id)
FROM Customer c
JOIN c.orders o
JOIN o.lines ol
GROUP BY c.id
~~~

Kết quả là 2 Order distinct.

| Cần đếm gì? | Biểu thức phù hợp |
| --- | --- |
| Số dòng OrderLine | `COUNT(ol)` |
| Số Order khác nhau | `COUNT(DISTINCT o.id)` |
| Số Customer khác nhau sau JOIN | `COUNT(DISTINCT c.id)` |
| Số SKU khác nhau, nếu SKU là business key duy nhất | `COUNT(DISTINCT p.sku)` |

**COUNT DISTINCT không phải thuốc chữa mọi truy vấn sai.** Nó chỉ giải quyết trường hợp cần đếm các giá trị/entity khác nhau; tổng tiền bị nhân đôi bởi JOIN có thể vẫn sai nếu không sửa cấu trúc truy vấn.

## 19. Fan-out khi JOIN hai collection: nguy cơ nhân doanh thu

Giả sử một Order có:

- 3 OrderLine.
- 2 PaymentAttempt.

Nếu entity có cả hai collection và ta viết một truy vấn JOIN đồng thời:

~~~jpql
SELECT o.id, SUM(ol.lineTotal)
FROM PurchaseOrder o
JOIN o.lines ol
JOIN o.paymentAttempts pa
GROUP BY o.id
~~~

`paymentAttempts` chỉ là quan hệ minh họa nếu entity thực tế định nghĩa nó. JOIN tạo tích kết hợp:

~~~text
3 OrderLine x 2 PaymentAttempt = 6 dòng join
~~~

Mỗi `lineTotal` có thể xuất hiện hai lần trong tập đầu vào, khiến `SUM(ol.lineTotal)` **bị nhân đôi**. Đổi `COUNT(o)` thành `COUNT(DISTINCT o.id)` không sửa được `SUM` đã nhân.

### Đừng sửa bằng SUM(DISTINCT lineTotal) nếu giá trị có thể trùng

Giả sử hai OrderLine đều có `lineTotal=100.00`. `SUM(DISTINCT ol.lineTotal)` chỉ cộng 100.00 một lần, dù đó là **hai dòng hàng thật sự khác nhau**.

Giải pháp đúng phải theo **danh tính dòng dữ liệu**, không dựa vào sự khác nhau tình cờ của giá trị tiền.

### Cách xử lý

1. **Đơn giản hóa JOIN:** bỏ những collection không cần cho phép tính.
2. **Tách thành nhiều truy vấn aggregate độc lập** khi cần nhiều metric từ các collection khác nhau.
3. **Tổng hợp trước rồi join kết quả tổng hợp** bằng derived table/CTE ở native SQL khi cần và DBMS hỗ trợ.
4. **Dùng correlated subquery** ở nơi JPQL cho phép (đặc biệt WHERE/HAVING) khi cấu trúc báo cáo phù hợp.
5. Xây dựng read model/materialized view có quản lý nếu đây là báo cáo lớn được truy vấn thường xuyên.

**Nguyên tắc:** trước khi SUM hoặc COUNT, phải biết **một hàng trong tập JOIN đang đại diện cho điều gì**.

## 20. Tổng doanh thu theo khách hàng

Với đơn hàng PAID, tính tổng `OrderLine.lineTotal` theo khách hàng:

~~~jpql
SELECT c.id, SUM(ol.lineTotal)
FROM Customer c
JOIN c.orders o
JOIN o.lines ol
WHERE o.status = :paid
GROUP BY c.id
ORDER BY SUM(ol.lineTotal) DESC, c.id ASC
~~~

Java:

~~~java
TypedQuery<Object[]> q = em.createQuery(
    "SELECT c.id, SUM(ol.lineTotal) " +
    "FROM Customer c " +
    "JOIN c.orders o " +
    "JOIN o.lines ol " +
    "WHERE o.status = :paid " +
    "GROUP BY c.id " +
    "ORDER BY SUM(ol.lineTotal) DESC, c.id ASC",
    Object[].class
);

List<Object[]> rows = q
    .setParameter("paid", OrderStatus.PAID)
    .getResultList();

for (Object[] row : rows) {
    Long customerId = (Long) row[0];
    BigDecimal totalRevenue = (BigDecimal) row[1];
    System.out.println(customerId + " -> " + totalRevenue);
}
~~~

Trong mô hình này, mỗi OrderLine thuộc một Order và mỗi Order thuộc một Customer. Khi chỉ JOIN đúng một nhánh Customer → Order → OrderLine, mỗi OrderLine xuất hiện một lần trong tập đầu vào, nên SUM của `lineTotal` phản ánh tổng các dòng đã thanh toán, **nếu** dữ liệu lineTotal và trạng thái PAID được quản lý nhất quán theo domain.

### Doanh thu và giá Product hiện tại

Không nên tính doanh thu lịch sử như:

~~~jpql
SUM(ol.quantity * p.price)
~~~

nếu `p.price` là **giá hiện tại**, vì giá Product có thể thay đổi sau khi khách mua. Nên tính từ giá/lineTotal đã chốt trong OrderLine hoặc một cấu trúc ledger/invoice phù hợp. Đây là vấn đề **nguồn dữ liệu nghiệp vụ đúng**, không chỉ cú pháp aggregate.

## 21. HAVING lọc khách hàng theo số đơn và doanh thu

Muốn tìm khách hàng có **ít nhất ba đơn PAID** và tổng doanh thu từ 1.000.000:

~~~jpql
SELECT c.id,
       COUNT(DISTINCT o.id),
       SUM(ol.lineTotal)
FROM Customer c
JOIN c.orders o
JOIN o.lines ol
WHERE o.status = :paid
GROUP BY c.id
HAVING COUNT(DISTINCT o.id) >= :minOrders
   AND SUM(ol.lineTotal) >= :minRevenue
ORDER BY SUM(ol.lineTotal) DESC, c.id ASC
~~~

Tại sao phải `COUNT(DISTINCT o.id)`?

Vì một Order có thể có nhiều OrderLine. Sau JOIN, một Order xuất hiện lặp lại trên nhiều dòng. Nếu dùng `COUNT(o)` sẽ đếm số OrderLine gắn với Order, không phải số Order.

Ví dụ binding:

~~~java
List<Object[]> rows = em.createQuery(
        "SELECT c.id, COUNT(DISTINCT o.id), SUM(ol.lineTotal) " +
        "FROM Customer c " +
        "JOIN c.orders o JOIN o.lines ol " +
        "WHERE o.status = :paid " +
        "GROUP BY c.id " +
        "HAVING COUNT(DISTINCT o.id) >= :minOrders " +
        "AND SUM(ol.lineTotal) >= :minRevenue " +
        "ORDER BY SUM(ol.lineTotal) DESC, c.id ASC",
        Object[].class)
    .setParameter("paid", OrderStatus.PAID)
    .setParameter("minOrders", 3L)
    .setParameter("minRevenue", new BigDecimal("1000000.00"))
    .getResultList();
~~~

### Một giới hạn ngầm của INNER JOIN

Chỉ những Order có **ít nhất một OrderLine** mới xuất hiện trong JOIN. Nếu một Order PAID nhưng chưa có line (thường là dữ liệu bất thường theo domain), nó không được tính ở `COUNT(DISTINCT o.id)` trong truy vấn này. Nếu báo cáo cần đếm mọi Order PAID bất kể lines, phải dùng LEFT JOIN tới lines hoặc tách query sao cho ngữ nghĩa chính xác.

## 22. Lọc theo thời gian trước khi nhóm

Ví dụ doanh thu PAID theo Customer trong khoảng thời gian:

~~~jpql
SELECT c.id, SUM(ol.lineTotal)
FROM Customer c
JOIN c.orders o
JOIN o.lines ol
WHERE o.status = :paid
  AND o.placedAt >= :fromInclusive
  AND o.placedAt < :toExclusive
GROUP BY c.id
~~~

Java:

~~~java
Instant from = Instant.parse("2027-05-01T00:00:00Z");
Instant to = Instant.parse("2027-06-01T00:00:00Z");

TypedQuery<Object[]> q = em.createQuery(
    "SELECT c.id, SUM(ol.lineTotal) " +
    "FROM Customer c JOIN c.orders o JOIN o.lines ol " +
    "WHERE o.status = :paid " +
    "AND o.placedAt >= :from " +
    "AND o.placedAt < :to " +
    "GROUP BY c.id",
    Object[].class
);

List<Object[]> rows = q
    .setParameter("paid", OrderStatus.PAID)
    .setParameter("from", from)
    .setParameter("to", to)
    .getResultList();
~~~

Dùng khoảng **[from, to)** (bao gồm đầu, không bao gồm cuối) thường thuận tiện hơn cố đoán “23:59:59.999” của ngày cuối, vì độ chính xác timestamp có thể khác giữa Java, JDBC và database.

### Timezone của kỳ báo cáo

Nếu kỳ kinh doanh là **tháng theo giờ Việt Nam** hoặc một múi giờ cụ thể, phải chuyển ranh giới ngày/tháng của zone đó thành Instant đúng trước khi binding. Không lấy giờ UTC 00:00 làm đầu mọi ngày kinh doanh nếu domain định nghĩa ngày ở zone khác.

## 23. Nhóm theo ngày/tháng: cách portable và cách DB-specific

Với trường `businessDate` kiểu `LocalDate`:

~~~jpql
SELECT o.businessDate, COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :paid
GROUP BY o.businessDate
ORDER BY o.businessDate ASC
~~~

Đây là cách đơn giản và tương đối portable để đếm số Order theo **ngày kinh doanh đã lưu**.

### Muốn nhóm theo tháng thì sao?

Có một số lựa chọn:

1. **Thêm thuộc tính đã chuẩn hóa**, ví dụ `businessMonth` (YearMonth không phải kiểu basic JPA portable ở mọi phiên bản; có thể lưu bằng `LocalDate` là ngày đầu tháng hoặc hai field `businessYear`/`businessMonthNumber`).
2. Dùng các hàm ngày giờ được phiên bản JPQL/provider hỗ trợ và kiểm tra khả năng ánh xạ xuống DBMS.
3. Dùng hàm database qua `FUNCTION(...)` hoặc native SQL khi chấp nhận phụ thuộc dialect.
4. Dùng bảng calendar/date dimension trong read model phục vụ báo cáo lớn.

Ví dụ thuộc tính đã chuẩn hóa:

~~~java
@Column(name = "business_year", nullable = false)
private int businessYear;

@Column(name = "business_month", nullable = false)
private int businessMonth;
~~~

JPQL:

~~~jpql
SELECT o.businessYear, o.businessMonth, COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :paid
GROUP BY o.businessYear, o.businessMonth
ORDER BY o.businessYear, o.businessMonth
~~~

Đoạn này giả sử PurchaseOrder thực tế có hai field mới đã được mapping và điền nhất quán; model ví dụ ban đầu chưa khai báo.

### Dùng FUNCTION khi chấp nhận phụ thuộc provider/DBMS

Ví dụ phác họa:

~~~jpql
SELECT FUNCTION('date_trunc', 'month', o.placedAt), COUNT(o)
FROM PurchaseOrder o
GROUP BY FUNCTION('date_trunc', 'month', o.placedAt)
~~~

`date_trunc` là hàm của PostgreSQL; cách provider suy luận result type và hỗ trợ GROUP BY biểu thức FUNCTION có thể khác. Không coi truy vấn này là JPQL portable trên mọi database.

Nếu phải dùng hàm/CTE phức tạp, có thể chọn native SQL và DTO projection, kèm test DBMS cụ thể.

## 24. DTO projection cho kết quả nhóm

Trả `Object[]` hoạt động nhưng dễ lỗi khi thêm hoặc đổi thứ tự biểu thức SELECT. Với query được dùng lâu dài, có thể dùng **constructor expression**.

DTO:

~~~java
package com.example.shop.dto;

public class CategoryProductStats {

    private final Long categoryId;
    private final String categoryCode;
    private final Long productCount;
    private final Double averagePrice;

    public CategoryProductStats(
            Long categoryId,
            String categoryCode,
            Long productCount,
            Double averagePrice) {
        this.categoryId = categoryId;
        this.categoryCode = categoryCode;
        this.productCount = productCount;
        this.averagePrice = averagePrice;
    }

    public Long getCategoryId() {
        return categoryId;
    }

    public String getCategoryCode() {
        return categoryCode;
    }

    public Long getProductCount() {
        return productCount;
    }

    public Double getAveragePrice() {
        return averagePrice;
    }
}
~~~

Query:

~~~java
TypedQuery<CategoryProductStats> query = em.createQuery(
    "SELECT NEW com.example.shop.dto.CategoryProductStats(" +
    "c.id, c.code, COUNT(p), AVG(p.price)) " +
    "FROM Category c LEFT JOIN c.products p " +
    "GROUP BY c.id, c.code " +
    "ORDER BY c.code ASC",
    CategoryProductStats.class
);

List<CategoryProductStats> stats = query.getResultList();
~~~

### Những điểm quan trọng

- `COUNT(p)` trả `Long` nên constructor nhận Long.
- `AVG(p.price)` trả `Double`; với category không có Product, nó có thể là `null`, nên DTO dùng `Double` thay vì primitive `double`.
- Nếu cần tên category trong DTO, thêm `c.name` vào SELECT và GROUP BY; constructor cũng phải đổi cho khớp.
- Kết quả DTO **không phải managed entity**. Sửa field DTO không gây dirty checking cập nhật database.

Nếu API công khai yêu cầu định dạng số tiền và chính sách rounding, có thể chuyển `Double` trung bình thành loại biểu diễn phù hợp ở tầng báo cáo; tránh định dạng số quá sớm trong JPQL nếu muốn còn tính toán.

## 25. Nhóm theo một entity có nên dùng không?

Một số truy vấn viết:

~~~jpql
SELECT c, COUNT(p)
FROM Category c LEFT JOIN c.products p
GROUP BY c
~~~

Điều này có thể được một số provider hỗ trợ, nhưng có giới hạn portability liên quan tới cách JPA/DBMS diễn giải toàn entity trong GROUP BY, đặc biệt với trạng thái eager relationship, LOB hoặc mapping phức tạp.

Để viết báo cáo ổn định, thường dễ hiểu hơn:

~~~jpql
SELECT c.id, c.code, c.name, COUNT(p)
FROM Category c LEFT JOIN c.products p
GROUP BY c.id, c.code, c.name
~~~

Nếu ứng dụng thật sự cần entity `Category` đầy đủ, có thể:

1. Query nhóm trả ID và aggregate.
2. Dùng các ID đó nạp Category theo fetch plan riêng.
3. Ghép dữ liệu trong DTO theo ID.

Phương pháp hai bước có thêm chi phí query nhưng làm rõ **thành phần aggregate** và **entity state/lifecycle**, đặc biệt khi báo cáo phức tạp.

## 26. HAVING với subquery: so sánh nhóm với mức chuẩn toàn hệ thống

Yêu cầu: **danh mục nào có giá trung bình của sản phẩm ACTIVE cao hơn giá trung bình của tất cả sản phẩm ACTIVE**?

Có thể diễn đạt:

~~~jpql
SELECT c.code, AVG(p.price)
FROM Product p JOIN p.category c
WHERE p.status = :active
GROUP BY c.code
HAVING AVG(p.price) > (
    SELECT AVG(p2.price)
    FROM Product p2
    WHERE p2.status = :active
)
ORDER BY AVG(p.price) DESC
~~~

Subquery ở HAVING trả mức trung bình của toàn bộ tập Product ACTIVE; aggregate ở query ngoài trả trung bình **từng danh mục**.

Java:

~~~java
TypedQuery<Object[]> query = em.createQuery(
    "SELECT c.code, AVG(p.price) " +
    "FROM Product p JOIN p.category c " +
    "WHERE p.status = :active " +
    "GROUP BY c.code " +
    "HAVING AVG(p.price) > (" +
    "  SELECT AVG(p2.price) FROM Product p2 " +
    "  WHERE p2.status = :active" +
    ") ORDER BY AVG(p.price) DESC, c.code ASC",
    Object[].class
);

List<Object[]> rows = query
    .setParameter("active", ProductStatus.ACTIVE)
    .getResultList();
~~~

### Quy tắc dùng subquery

Trong JPQL portable, subquery được dùng trong **WHERE** và **HAVING**. Không nên giả định mọi database subquery viết trong `FROM` hoặc một `SELECT` expression tùy ý cũng là JPQL hợp lệ; những trường hợp đó có thể là HQL extension hoặc native SQL.

Nếu nhóm có AVG NULL, phép so sánh với AVG toàn hệ thống cũng có thể trả UNKNOWN. Khi các nhóm rỗng phải xuất hiện, hãy xác định logic NULL/COALESCE trước.

## 27. HAVING với truy vấn có tương quan

Một ví dụ sâu hơn: tìm customer có số đơn PAID lớn hơn **số đơn PAID trung bình theo customer**, khi domain tính cả customer không có đơn.

Thay vì cố viết một câu JPQL khổng lồ với nhiều cấp GROUP BY trong FROM, có thể:

1. Truy vấn số đơn PAID của mỗi customer bằng LEFT JOIN + ON.
2. Tính mức chuẩn theo một truy vấn riêng trong cùng boundary nhất quán phù hợp.
3. Truy vấn lọc lại customer có COUNT vượt ngưỡng bằng HAVING.

Ví dụ phần thứ ba:

~~~jpql
SELECT c.id, COUNT(o)
FROM Customer c
LEFT JOIN c.orders o ON o.status = :paid
GROUP BY c.id
HAVING COUNT(o) > :averagePaidOrders
~~~

`:averagePaidOrders` là một tham số được ứng dụng tính từ phép thống kê khác theo đúng định nghĩa. **Không tự coi hai query riêng chắc chắn đọc một snapshot thống nhất**; nếu yêu cầu báo cáo một thời điểm, cần transaction/isolation hoặc read model thích hợp.

Với subquery **có tương quan** trực tiếp trên từng Customer, có thể dùng trong WHERE để diễn đạt một số điều kiện tập con:

~~~jpql
SELECT c
FROM Customer c
WHERE (
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.customer = c
      AND o.status = :paid
) >= :minOrders
~~~

Đây là cách đếm đơn cho từng Customer mà **không cần GROUP BY ở outer query**. Nó có thể phù hợp với những yêu cầu chỉ cần trả entity Customer thỏa một ngưỡng. Hiệu năng phụ thuộc tối ưu hóa subquery, index và DBMS.

### Chọn GROUP BY hay correlated subquery?

| Yêu cầu | Cách diễn đạt thường rõ |
| --- | --- |
| Trả số lượng/aggregate cho mọi nhóm | GROUP BY |
| Chỉ lấy những entity thỏa điều kiện aggregate liên quan | GROUP BY + HAVING hoặc correlated subquery WHERE |
| Cần nhiều metric khác nhau từ nhiều collection | Tách aggregation, tránh fan-out |
| Cần derived table/CTE để tối ưu báo cáo lớn | Native SQL/read model khi cần |

Không có một cách luôn nhanh hơn. Khi truy vấn thật chậm, phải quan sát SQL được sinh và execution plan với dữ liệu điển hình.

## 28. Tổng hợp có điều kiện: đếm nhiều trạng thái trên cùng dòng

Yêu cầu báo cáo mỗi Category có:

- Tổng số Product.
- Số Product ACTIVE.
- Số Product DRAFT.

Thay vì `GROUP BY c.code, p.status` tạo nhiều dòng cho một Category, có thể dùng biểu thức CASE bên trong SUM:

~~~jpql
SELECT c.code,
       COUNT(p),
       SUM(CASE WHEN p.status = :active THEN 1 ELSE 0 END),
       SUM(CASE WHEN p.status = :draft THEN 1 ELSE 0 END)
FROM Category c LEFT JOIN c.products p
GROUP BY c.code
ORDER BY c.code
~~~

Ý nghĩa: `CASE WHEN` chuyển từng dòng thành 1 nếu khớp trạng thái, ngược lại 0, rồi `SUM` cộng trên mỗi nhóm. Trong nhiều stack Jakarta Persistence/Hibernate hiện đại, dạng tổng hợp có điều kiện này được hỗ trợ; khi cần portability tuyệt đối sang provider/phiên bản cũ, hãy kiểm tra cú pháp CASE trong aggregate và kiểu trả về thực tế.

### Nhóm rỗng với LEFT JOIN

Với Category không có Product, biểu thức `CASE WHEN p.status = ... THEN 1 ELSE 0 END` nhận nhánh ELSE 0 trên dòng LEFT JOIN, nên SUM được 0 trong mô hình thông thường này. Tuy nhiên, khi viết aggregate phức tạp hơn với nullable values, nên kiểm tra COALESCE và null semantics rõ.

### Đừng để điều kiện trạng thái lọt vào WHERE ngoài ý định

Nếu thêm:

~~~jpql
WHERE p.status = :active
~~~

thì trước khi GROUP BY, mọi Product DRAFT đã bị loại; kết quả đếm Draft sẽ luôn 0 và category chỉ có Draft có thể biến mất. Khi cần **nhiều metric điều kiện trên một nhóm**, điều kiện thích hợp có thể nằm trong CASE thay vì WHERE.

## 29. DISTINCT trong SELECT khác DISTINCT trong COUNT

Hai câu:

~~~jpql
SELECT DISTINCT c.code
FROM Product p JOIN p.category c
~~~

và:

~~~jpql
SELECT c.code, COUNT(DISTINCT p.id)
FROM Product p JOIN p.category c
GROUP BY c.code
~~~

phục vụ hai mục tiêu khác nhau:

- `SELECT DISTINCT c.code` chỉ trả những mã danh mục không trùng trong tập kết quả; không cung cấp số lượng.
- `COUNT(DISTINCT p.id)` đếm số Product identity khác nhau trong **mỗi nhóm**.

Với:

~~~jpql
SELECT DISTINCT c.code, COUNT(p)
FROM Product p JOIN p.category c
GROUP BY c.code
~~~

`DISTINCT` trên cả hàng kết quả thường không bổ sung lợi ích nếu `GROUP BY c.code` đã cho một hàng mỗi mã danh mục; nó **không sửa COUNT(p) bị nhân do các JOIN khác**.

Hãy đặt DISTINCT ở đúng cấp ngữ nghĩa. Nếu vấn đề là đếm trùng các Order khi JOIN lines, dùng `COUNT(DISTINCT o.id)`, không đơn giản thêm `SELECT DISTINCT` ở ngoài.

## 30. ORDER BY kết quả nhóm và thứ tự ổn định

Ví dụ:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c LEFT JOIN c.products p
GROUP BY c.code
ORDER BY COUNT(p) DESC, c.code ASC
~~~

Điều này sắp xếp theo số sản phẩm giảm dần, rồi mã danh mục tăng dần khi cùng số lượng.

### Vì sao cần tie-breaker?

Nếu BOOK và TECH đều có hai Product, chỉ `ORDER BY COUNT(p) DESC` không xác định ai đứng trước. Khi phân trang, thứ tự không ổn định có thể gây trùng hoặc bỏ sót nhóm giữa các lần query, ngay cả khi dữ liệu chưa đổi đáng kể.

### Dùng alias aggregate trong ORDER BY

Một số biểu thức JPQL có thể đặt result variable:

~~~jpql
SELECT c.code AS categoryCode, COUNT(p) AS productCount
FROM Category c LEFT JOIN c.products p
GROUP BY c.code
ORDER BY productCount DESC
~~~

Khả năng tham chiếu result variable trong ORDER BY có ngữ nghĩa được JPQL hỗ trợ. Nhưng **đừng mặc định alias SELECT có thể thay thế biểu thức aggregate trong HAVING trên mọi provider**, vì các DBMS/provider có khác biệt. Cách an toàn, rõ ràng trong HAVING là lặp lại `COUNT(p)` hoặc `SUM(...)`.

## 31. Phân trang kết quả GROUP BY/HAVING

Với câu query trả nhiều nhóm, có thể dùng:

~~~java
int page = 0;
int size = 20;

List<Object[]> rows = em.createQuery(
        "SELECT c.code, COUNT(p) " +
        "FROM Category c LEFT JOIN c.products p " +
        "GROUP BY c.code " +
        "HAVING COUNT(p) >= :minCount " +
        "ORDER BY COUNT(p) DESC, c.code ASC",
        Object[].class)
    .setParameter("minCount", 2L)
    .setFirstResult(page * size)
    .setMaxResults(size)
    .getResultList();
~~~

Trong ví dụ, `setFirstResult` bỏ qua số **nhóm kết quả**, không phải số Product đầu vào. Phải xác định tổng số nhóm phù hợp nếu API cần `totalPages`.

### Đếm số nhóm có HAVING phức tạp không giống COUNT số Product

Với:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c JOIN c.products p
GROUP BY c.code
HAVING COUNT(p) >= 5
~~~

`SELECT COUNT(p) FROM Product p` không trả số nhóm; nó trả số Product. Ngay cả `COUNT(DISTINCT c.code)` cũng chỉ đếm toàn bộ category có sản phẩm nếu thiếu điều kiện “COUNT Product >= 5”.

JPQL portable không có cùng khả năng dùng một grouped subquery làm derived table trong FROM như nhiều SQL dialect. Các lựa chọn thực tế:

1. Với số nhóm ít, nhận danh sách group keys và đếm ở tầng ứng dụng (không phù hợp báo cáo rất lớn).
2. Xây dựng một câu count group tương đương thông qua correlated subquery trong WHERE.
3. Dùng native SQL với CTE/derived table khi cần đếm nhóm phức tạp hiệu quả.
4. Tạo read model/materialized view nếu thống kê lớn và yêu cầu phân trang lặp lại.

### Một cách count nhóm đạt ngưỡng bằng correlated subquery

~~~jpql
SELECT COUNT(c)
FROM Category c
WHERE (
    SELECT COUNT(p)
    FROM Product p
    WHERE p.category = c
) >= :minCount
~~~

Đây là số Category có ít nhất `minCount` Product theo đúng định nghĩa này, kể cả các category trống khi `minCount=0`. Cần giữ **mọi điều kiện filter tương đương** với query page. Nếu query page chỉ đếm ACTIVE, subquery count cũng phải chỉ đếm ACTIVE.

## 32. GROUP BY với native SQL và giới hạn JPQL

JPQL hỗ trợ các trường hợp grouping phổ biến bằng entity paths. Khi báo cáo phức tạp, DBMS có thể hỗ trợ thêm:

- CTE (`WITH ...` ở SQL).
- Derived tables trong FROM.
- Window functions như `ROW_NUMBER() OVER (...)` hoặc `SUM(...) OVER (...)`.
- `ROLLUP`, `CUBE`, `GROUPING SETS`.
- Percentiles, median, statistical aggregates.
- Filtered aggregate như `COUNT(*) FILTER (WHERE ...)`.
- Materialized views.

Các tính năng trên **không được coi là cú pháp JPQL portable** chỉ vì DBMS hỗ trợ chúng. Có thể dùng native SQL hoặc extension của provider theo yêu cầu.

Ví dụ PostgreSQL tính số nhóm thỏa HAVING bằng CTE:

~~~sql
WITH category_counts AS (
    SELECT c.id, COUNT(p.id) AS product_count
    FROM categories c
    LEFT JOIN products p ON p.category_id = c.id
    GROUP BY c.id
)
SELECT COUNT(*)
FROM category_counts
WHERE product_count >= :min_count;
~~~

Đây là **native SQL minh họa**, không phải JPQL. Cú pháp named parameter trong native query được nhiều provider hỗ trợ, nhưng vị trí/kiểu parameter portable nhất cho native SQL cần tuân thủ API và nhà cung cấp đang dùng.

### Khi nào nên chuyển sang native SQL?

Khi tính năng DB-specific tạo lợi ích rõ về cách biểu diễn nghiệp vụ hoặc performance, và dự án chấp nhận chi phí phụ thuộc dialect. Không đổi mọi báo cáo sang native SQL chỉ vì mới gặp `GROUP BY`; các phép nhóm đơn giản trong JPQL vẫn có ưu điểm bám theo entity mapping và hỗ trợ đa DBMS.

## 33. Hiệu năng của GROUP BY và HAVING

Aggregate có thể tốn nhiều CPU, I/O, memory hoặc temporary storage khi dữ liệu lớn. Một query:

~~~jpql
SELECT c.code, COUNT(p)
FROM Product p JOIN p.category c
WHERE p.status = :active
GROUP BY c.code
HAVING COUNT(p) >= :minCount
~~~

trên vài trăm bản ghi khác nhiều so với vài trăm triệu Product.

### 33.1. Lọc sớm bằng WHERE

Nếu chỉ cần ACTIVE, lọc:

~~~jpql
WHERE p.status = :active
~~~

trước GROUP BY thường giảm số dòng đầu vào. Đừng chuyển mọi predicate sang HAVING khi nó không dựa trên kết quả tổng hợp.

### 33.2. Index các cột lọc và liên kết

Ví dụ schema Product có:

~~~sql
CREATE INDEX idx_products_status_category
ON products(status, category_id);
~~~

Index này có thể hỗ trợ một số query lọc theo status rồi nhóm/join theo category. Nhưng không có index “tốt nhất” cho mọi điều kiện:

- Tỷ lệ Product ACTIVE là bao nhiêu?
- Query thường lọc theo tenant, date hay category nào trước?
- DBMS có dùng index-only scan hay không?
- Có cần cover cột price cho phép AVG/SUM không?
- Phép nhóm là hash aggregate hay sort aggregate?

Phải dùng `EXPLAIN`/execution plan và đo trên dữ liệu đại diện, không chọn index chỉ từ chuỗi JPQL.

### 33.3. Tránh JOIN không cần thiết

Nếu Product có `category_id` FK và mục tiêu chỉ là đếm theo category identity, provider/SQL có thể có phương án tối ưu khác nếu không phải JOIN lấy tên category. Nhưng ở JPQL, việc dùng đường dẫn quan hệ và điều kiện mapping vẫn phải giữ tính portable. Khi query lớn, đánh giá SQL sinh ra và quyết định liệu projection theo FK, navigation hay native SQL có phù hợp.

### 33.4. Kiểm tra số hàng sau JOIN

Trước khi tối ưu COUNT/SUM, hãy xác định **cardinality** của từng JOIN. Một fan-out từ nhiều collection có thể tạo rất nhiều hàng trung gian vừa chậm vừa sai số liệu. Đây thường là lỗi thiết kế query nghiêm trọng hơn việc thiếu một index.

### 33.5. Pre-aggregation và read model

Với báo cáo doanh thu theo tháng đọc thường xuyên, có thể dùng bảng tổng hợp:

~~~text
monthly_revenue
------------------------------------
business_year | business_month | revenue
~~~

Đây là read model riêng, được cập nhật bằng batch/event hoặc luồng dữ liệu có đối soát. Khi chọn cách này, phải xác định **độ trễ thống kê được chấp nhận**, không tuyên bố bảng tổng hợp luôn realtime.

## 34. Kết quả nhóm và transaction isolation

Giả sử query:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c LEFT JOIN c.products p
GROUP BY c.code
~~~

chạy hai lần trong một transaction, trong khi transaction khác tạo Product mới và commit.

Kết quả có thay đổi hay không phụ thuộc:

- Isolation của DBMS (ví dụ READ COMMITTED và các kiểu snapshot).
- Thời điểm statement lấy snapshot.
- Có dữ liệu pending trong persistence context và flush mode nào không?
- Provider có query cache hay không?
- Query có được chạy ở cùng transaction/connection không?

**GROUP BY không tự cung cấp một snapshot nhất quán xuyên nhiều lần truy vấn**. Nếu API gọi query trang và query COUNT riêng, giữa hai câu có thể có INSERT/DELETE/UPDATE làm thay đổi kết quả.

### First-level cache có làm mọi aggregate cố định không?

Không. JPA identity map quản lý các **entity instances**, còn `COUNT`/`SUM` là scalar aggregate được tính từ kết quả query và điều kiện transactional. Một entity Product đã managed không có nghĩa lần sau `SELECT COUNT(p)` luôn trả lại giá trị cũ từ first-level cache.

### AUTO flush và thay đổi pending

Nếu transaction vừa thêm Product mới hoặc đổi status của một Product managed, rồi chạy JPQL GROUP BY với `FlushModeType.AUTO`, JPA phải bảo đảm các thay đổi pending có thể ảnh hưởng kết quả query được phản ánh theo quy tắc của đặc tả. Provider có thể flush trước query.

Với `FlushModeType.COMMIT`, tác động của các thay đổi chưa đồng bộ lên query trước commit không được xác định giống AUTO. **Không nhầm flush mode với database isolation level.**

## 35. Grouping và quyền truy cập dữ liệu

Một aggregate query có thể **lộ thông tin** dù chỉ trả COUNT:

~~~jpql
SELECT c.code, COUNT(p)
FROM Category c JOIN c.products p
GROUP BY c.code
~~~

Nếu ứng dụng đa tenant mà không giới hạn dữ liệu theo tenant, người dùng có thể nhận số lượng sản phẩm của tenant khác. Query không cần trả tên hay ID chi tiết mới bị coi là rò rỉ.

Với entity có field `tenantId`, query phải áp dụng filter thích hợp:

~~~jpql
SELECT c.code, COUNT(p)
FROM Product p JOIN p.category c
WHERE p.tenantId = :tenantId
GROUP BY c.code
~~~

Đoạn này giả sử Product được mở rộng với `tenantId`; model đơn giản ở đầu bài chưa khai báo field đó.

### Các nguyên tắc an toàn

- Áp dụng tenant/authorization filter **trước aggregate** ở nguồn dữ liệu.
- Không chỉ lọc kết quả nhóm cuối cùng khi dữ liệu đầu vào đã bị trộn tenant.
- Nếu một category dùng chung giữa tenant, xác định rõ nhóm theo tenant và category identity hay theo category code toàn hệ thống.
- Kiểm tra cả query page lẫn query count groups.
- Với native SQL hoặc bulk jobs, xác nhận row-level security/filter có còn hiệu lực không.

`TypedQuery<Object[]>` hay DTO chỉ cung cấp thông tin kiểu; nó **không tự áp dụng authorization**.

## 36. Truy vấn tổng hợp dưới dạng service tái sử dụng

Ta viết DTO cho báo cáo số sản phẩm ACTIVE trong danh mục:

~~~java
package com.example.shop.dto;

public class ActiveCategoryCount {

    private final Long categoryId;
    private final String categoryCode;
    private final Long activeCount;

    public ActiveCategoryCount(
            Long categoryId,
            String categoryCode,
            Long activeCount) {
        this.categoryId = categoryId;
        this.categoryCode = categoryCode;
        this.activeCount = activeCount;
    }

    public Long getCategoryId() {
        return categoryId;
    }

    public String getCategoryCode() {
        return categoryCode;
    }

    public Long getActiveCount() {
        return activeCount;
    }
}
~~~

Service:

~~~java
package com.example.shop;

import com.example.shop.dto.ActiveCategoryCount;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import java.util.List;

public class CategoryReportService {

    private final EntityManager em;

    public CategoryReportService(EntityManager em) {
        this.em = em;
    }

    public List<ActiveCategoryCount> findCategories(
            long minActiveCount, int maxResults) {

        if (minActiveCount < 0) {
            throw new IllegalArgumentException(
                    "Ngưỡng số lượng phải >= 0");
        }
        if (maxResults < 1 || maxResults > 200) {
            throw new IllegalArgumentException(
                    "maxResults phải thuộc [1, 200]");
        }

        TypedQuery<ActiveCategoryCount> q = em.createQuery(
            "SELECT NEW com.example.shop.dto.ActiveCategoryCount(" +
            "c.id, c.code, COUNT(p)) " +
            "FROM Category c " +
            "LEFT JOIN c.products p ON p.status = :active " +
            "GROUP BY c.id, c.code " +
            "HAVING COUNT(p) >= :minCount " +
            "ORDER BY COUNT(p) DESC, c.id ASC",
            ActiveCategoryCount.class
        );

        return q
            .setParameter("active", ProductStatus.ACTIVE)
            .setParameter("minCount", minActiveCount)
            .setMaxResults(maxResults)
            .getResultList();
    }
}
~~~

### Vì sao service được thiết kế như vậy?

1. **Bắt đầu từ Category** để có thể giữ cả category không có sản phẩm.
2. **LEFT JOIN ... ON** chỉ gắn Product ACTIVE mà không loại category trống.
3. **COUNT(p)** đếm Product được gắn, trả 0 khi không có.
4. **GROUP BY c.id, c.code** định danh từng danh mục rõ ràng.
5. **HAVING** thực thi điều kiện ngưỡng ở cấp nhóm.
6. **ORDER BY COUNT DESC, c.id ASC** tạo thứ tự ổn định khi số lượng bằng nhau.
7. **DTO constructor** thể hiện kiểu kết quả, không đòi hỏi cast Object[].
8. **Parameter binding** giữ giá trị bên ngoài query structure.
9. **setMaxResults** tránh trả tập kết quả không giới hạn.

Các method chỉ đọc vẫn cần xác định ranh giới EntityManager, transaction/isolation, quyền truy cập dữ liệu và lifetime của persistence context theo môi trường sử dụng. Không chia sẻ cùng một EntityManager giữa các thread.

## 37. Một số lỗi phổ biến và cách sửa

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `COUNT(p)` trong WHERE | Aggregate không hợp lệ ở mức lọc từng dòng | Chuyển sang HAVING |
| SELECT `p.sku` nhưng chỉ GROUP BY `c.code` | Không biết SKU đại diện cho nhóm | Nhóm thêm SKU hoặc dùng aggregate phù hợp |
| GROUP BY `c.name` khi tên không unique | Gộp nhiều category khác nhau | Nhóm theo ID/business key thật |
| Dùng INNER JOIN mà muốn hiển thị nhóm rỗng | Category không có Product biến mất | Bắt đầu từ Category, dùng LEFT JOIN |
| LEFT JOIN nhưng đặt `p.status=:active` ở WHERE | Loại dòng NULL, làm mất category có 0 ACTIVE | Đặt điều kiện ở ON hoặc tổng hợp có điều kiện |
| Dùng `COUNT(c)` để đếm Product ở LEFT JOIN | Category vẫn được đếm khi không có Product | Dùng `COUNT(p)` |
| Dùng `COUNT(o)` sau JOIN OrderLine | Đếm mỗi Order nhiều lần | `COUNT(DISTINCT o.id)` |
| Dùng `SUM(DISTINCT lineTotal)` để chống fan-out | Mất các dòng khác nhau có cùng số tiền | Sửa JOIN hoặc aggregate theo identity |
| Giả định AVG BigDecimal trả BigDecimal | DTO/TypedQuery sai kiểu | AVG trả Double theo JPQL |
| Giả định SUM rỗng trả 0 | Nhận NULL, có thể gây NPE | Chấp nhận NULL hoặc dùng COALESCE |
| Dùng `COUNT(*)` theo thói quen SQL ở mọi JPQL | Cú pháp/portability không đúng theo mẫu query | Dùng `COUNT(p)` hoặc `COUNT(p.id)` với alias phù hợp |
| Nối input vào HAVING/ORDER BY | Query injection, sai cú pháp | Bind giá trị, whitelist cấu trúc |
| Dùng `GROUP BY p.createdAt` để nhóm theo ngày | Nhóm theo thời điểm, nhiều nhóm trong một ngày | Group theo businessDate hoặc hàm date được hỗ trợ |
| Group theo ngày mà bỏ timezone | Số liệu ngày kinh doanh sai | Chuẩn hóa businessDate theo zone nghiệp vụ |
| Query page có HAVING nhưng count query chỉ COUNT Product | Sai tổng số trang | Đếm số nhóm thỏa cùng điều kiện |
| Dùng JPQL subquery trong FROM như SQL CTE | Không phải cú pháp JPQL portable | Dùng correlated subquery WHERE/HAVING hoặc native SQL |
| Dùng HAVING để lọc điều kiện row thông thường | Khó hiểu, có thể tốn xử lý | Ưu tiên WHERE khi không cần aggregate |
| Bỏ tenant filter trước GROUP BY | Aggregate trộn dữ liệu các tenant | Lọc/giới hạn quyền ở nguồn |
| Mong JPQL GROUP BY luôn cho kết quả realtime | Query chịu transaction/cache/replication | Xác định consistency policy |
| Chọn index chỉ dựa vào tên GROUP BY | Có thể không cải thiện query plan | EXPLAIN và đo trên dữ liệu thực |

## 38. Quy trình thiết kế một báo cáo GROUP BY/HAVING

Khi nhận một yêu cầu tổng hợp, đi theo thứ tự:

1. **Xác định thực thể được đếm/cộng:** Product, Order, OrderLine hay Customer?
2. **Xác định khóa nhóm:** một Category entity, trạng thái, ngày kinh doanh hay tổ hợp nhiều thuộc tính?
3. **Xác định đơn vị số liệu:** COUNT số bản ghi, SUM tiền của line, AVG giá sản phẩm, MAX tồn kho?
4. **Xác định nguồn dữ liệu đúng:** giá tại thời điểm mua hay giá hiện tại; trạng thái PAID hay đã hoàn tất?
5. **Thiết kế JOIN:** một hàng sau JOIN đại diện cho một đơn vị nào, có fan-out không?
6. **Quyết định cần nhóm rỗng không:** nếu có, xem LEFT JOIN và vị trí điều kiện ON.
7. **Viết WHERE:** chỉ lọc những dòng đầu vào hợp lệ cho aggregate.
8. **Viết GROUP BY:** nhóm theo key thật, tránh dùng tên hiển thị không unique.
9. **Viết SELECT:** các scalar không aggregate phải phù hợp khóa nhóm.
10. **Viết HAVING:** chỉ giữ nhóm theo COUNT/SUM/AVG/MIN/MAX.
11. **Xử lý NULL:** COUNT=0 khác SUM/AVG=NULL; COALESCE nếu domain muốn.
12. **Chọn kiểu Java:** Long cho COUNT, Double cho AVG, BigDecimal cho SUM tiền BigDecimal, DTO khi cần.
13. **ORDER BY rõ:** tie-breaker khi các nhóm có cùng metric.
14. **Phân trang và đếm nhóm:** tổng số nhóm khác tổng số dòng nguồn.
15. **Bảo vệ dữ liệu:** tenant/authorization filters trước tổng hợp.
16. **Kiểm tra hiệu năng và tính nhất quán:** SQL plan, index, isolation, thời điểm báo cáo.

Một cách tự hỏi ngắn:

~~~text
Mình muốn "bao nhiêu" cái gì?
              |
              v
Sau JOIN, một dòng có thực sự là một "cái" đó?
        |                         |
       Có                        Không
        |                         |
        v                         v
   Chọn COUNT/SUM           Sửa JOIN, DISTINCT đúng
        |                   đối tượng, hoặc tách query
        +------------+------------+
                     |
                     v
        Nhóm theo khóa nào?
                     |
                     v
        Lọc dòng với WHERE
                     |
                     v
        GROUP BY -> aggregate
                     |
                     v
        HAVING -> lọc nhóm
                     |
                     v
        DTO / ORDER BY / page
~~~

## 39. Bài tập thực hành

### Bài 1 — Đếm sản phẩm theo danh mục

Viết JPQL trả mã danh mục và số Product của từng danh mục.

**Gợi ý:**

~~~jpql
SELECT c.code, COUNT(p)
FROM Product p JOIN p.category c
GROUP BY c.code
~~~

### Bài 2 — Lọc danh mục từ năm sản phẩm

Từ bài 1, chỉ giữ các danh mục có số Product từ năm trở lên.

**Gợi ý:** thêm `HAVING COUNT(p) >= :minCount` và bind `5L`.

### Bài 3 — Chỉ đếm ACTIVE

Yêu cầu chỉ đếm Product ACTIVE trong từng danh mục. Điều kiện `p.status=:active` nên nằm ở WHERE hay HAVING?

**Gợi ý:** WHERE nếu chỉ báo cáo những danh mục có Product ACTIVE; nếu phải giữ cả category có 0 ACTIVE, xem LEFT JOIN ... ON.

### Bài 4 — Giữ nhóm có 0 sản phẩm

Muốn mọi Category xuất hiện, kể cả Category chưa có Product. Từ entity nào nên bắt đầu và dùng JOIN nào?

**Gợi ý:** `FROM Category c LEFT JOIN c.products p`, sau đó `COUNT(p)`.

### Bài 5 — LEFT JOIN và WHERE

Vì sao query `LEFT JOIN c.products p WHERE p.status=:active` không giữ category không có Product ACTIVE?

**Gợi ý:** WHERE loại dòng có `p=NULL`. Đặt filter vào ON.

### Bài 6 — Hai thuộc tính nhóm

Viết query đếm Product theo `Category.code` và `Product.status`.

**Gợi ý:** `GROUP BY c.code, p.status`, chọn cả hai thuộc tính và COUNT(p).

### Bài 7 — HAVING và AVG

Tìm những Category có giá trung bình Product ACTIVE trên 500.000.

**Gợi ý:** `WHERE p.status=:active GROUP BY c.code HAVING AVG(p.price)>:threshold`. Kiểm tra kiểu AVG=Double.

### Bài 8 — Đếm số đơn nhưng JOIN nhiều dòng

Một khách có hai Order, mỗi Order có năm OrderLine. Query JOIN OrderLine rồi dùng `COUNT(o)` cho kết quả bao nhiêu?

**Gợi ý:** có thể trả 10. Nếu muốn đếm Order, dùng `COUNT(DISTINCT o.id)`.

### Bài 9 — Doanh thu bị nhân hai

Một Order có 3 lines và 2 payment attempts. Query JOIN đồng thời hai collection rồi SUM(lineTotal) gây gì?

**Gợi ý:** fan-out nhân hàng, doanh thu có thể bị tính hai lần. Sửa nguồn JOIN hoặc tách aggregation; không tùy tiện SUM(DISTINCT amount).

### Bài 10 — SUM với nhóm rỗng

Customer chưa có OrderLine. Với LEFT JOIN và `SUM(ol.lineTotal)`, kết quả nên được xử lý ra sao?

**Gợi ý:** SUM có thể NULL, dùng `COALESCE(SUM(...), :zero)` nếu báo cáo muốn hiển thị 0.

### Bài 11 — DTO constructor

Query SELECT `c.id, c.code, COUNT(p), AVG(p.price)`. Constructor DTO cần những kiểu tham số nào?

**Gợi ý:** `Long, String, Long, Double`; Double cần nullable khi category trống.

### Bài 12 — GROUP BY và select field

Vì sao `SELECT c.code, p.sku, COUNT(p) ... GROUP BY c.code` không biểu diễn đúng một hàng cho mỗi category?

**Gợi ý:** mỗi Category có thể có nhiều SKU, không có SKU đại diện duy nhất.

### Bài 13 — Trang nhóm

Một query `GROUP BY c.code HAVING COUNT(p)>=5` được phân trang. Có thể lấy `SELECT COUNT(p)` làm total number of pages không?

**Gợi ý:** không, cần đếm **số nhóm thỏa HAVING**, không phải tổng số Product.

### Bài 14 — Kỳ báo cáo theo giờ địa phương

Hệ thống lưu `placedAt` theo Instant, nghiệp vụ muốn doanh thu theo ngày tại Việt Nam. Vì sao nhóm trực tiếp theo phần ngày UTC có thể sai?

**Gợi ý:** thời điểm cận nửa đêm UTC có thể thuộc ngày khác tại múi giờ Việt Nam; cần businessDate hoặc ranh giới timestamp đúng zone.

### Bài 15 — Tenant scoping

Ứng dụng đa tenant chạy query GROUP BY mà không có điều kiện tenant. Dù chỉ trả COUNT, liệu có rủi ro rò rỉ dữ liệu?

**Gợi ý:** có. Aggregate cũng tiết lộ thông tin; lọc dữ liệu ở nguồn trước GROUP BY.

### Bài 16 — Subquery trong HAVING

Muốn lấy danh mục có giá trung bình cao hơn mức trung bình toàn hệ thống. Có thể đặt một subquery `SELECT AVG(p2.price)` trong HAVING không?

**Gợi ý:** có, trong những trường hợp JPQL cho phép subquery ở WHERE/HAVING. Chú ý cùng điều kiện ACTIVE nếu so sánh trên tập ACTIVE.

### Bài 17 — DISTINCT ở sai cấp

Query JOIN Order và OrderLine rồi `SELECT DISTINCT c.id, COUNT(o)`. Tại sao COUNT(o) vẫn có thể quá lớn?

**Gợi ý:** DISTINCT ngoài SELECT chỉ khử trùng hàng kết quả cuối, không sửa các giá trị COUNT đã tính từ các hàng JOIN nhân bản. Dùng COUNT(DISTINCT o.id).

### Bài 18 — Đọc một báo cáo hai lần

Một query COUNT theo category chạy hai lần, transaction khác INSERT Product ở giữa. Có thể bảo đảm hai kết quả y hệt chỉ nhờ dùng `TypedQuery<Object[]>` không?

**Gợi ý:** không. Kết quả phụ thuộc isolation/snapshot, flush mode và nguồn dữ liệu; TypedQuery chỉ làm rõ kiểu Java.

## 40. Tóm tắt công thức tư duy

| Câu hỏi | Công cụ JPQL thường cần |
| --- | --- |
| “Chỉ lấy Product ACTIVE?” | `WHERE p.status=:active` |
| “Mỗi danh mục có bao nhiêu Product?” | `GROUP BY c.id` + `COUNT(p)` |
| “Chỉ danh mục có ít nhất N Product?” | `HAVING COUNT(p)>=:n` |
| “Mỗi danh mục có giá trung bình?” | `AVG(p.price)` |
| “Chỉ danh mục giá trung bình cao?” | `HAVING AVG(p.price)>:minAvg` |
| “Giữ cả danh mục chưa có Product?” | `LEFT JOIN` + `COUNT(p)` |
| “Chỉ đếm ACTIVE nhưng giữ category rỗng?” | `LEFT JOIN ... ON p.status=:active` |
| “Đếm số Order khi đã JOIN OrderLine?” | `COUNT(DISTINCT o.id)` |
| “Tổng tiền của OrderLine?” | `SUM(ol.lineTotal)` với JOIN không nhân bản |
| “Tổng bằng 0 khi không có lines?” | `COALESCE(SUM(...), :zero)` |
| “Trả kết quả nhóm type-safe?” | `SELECT NEW ...DTO(...)` + `TypedQuery<DTO>` |
| “Sắp xếp nhiều nhóm cùng COUNT?” | `ORDER BY COUNT(...) DESC, key ASC` |
| “Đếm tổng số nhóm sau HAVING?” | Một count-group query tương đương hoặc native SQL/CTE |

## Kết luận

**`GROUP BY` và `HAVING` là hai công cụ cốt lõi để viết báo cáo tổng hợp trong JPQL.** `GROUP BY` gom các dòng theo khóa nhóm; `COUNT`, `SUM`, `AVG`, `MIN` và `MAX` tính số liệu trên từng nhóm; `HAVING` lọc những nhóm có số liệu đáp ứng điều kiện. Ngược lại, `WHERE` lọc từng dòng trước khi nhóm, vì thế vị trí đặt điều kiện ảnh hưởng trực tiếp kết quả.

Khi viết truy vấn nhóm trong JPA, cần giữ các nguyên tắc: **dùng entity và thuộc tính Java thay cho tên bảng/cột SQL; SELECT các scalar phù hợp GROUP BY; chọn đúng kiểu kết quả aggregate; hiểu sự khác biệt của COUNT và SUM với NULL; dùng LEFT JOIN và ON nếu muốn giữ nhóm không có phần tử; tránh nhân bản dữ liệu do JOIN; chỉ dùng DISTINCT đúng đối tượng đang đếm**. Nếu query có số liệu tài chính hoặc dùng nhiều collection, phải kiểm tra đơn vị tính và nguồn dữ liệu trước khi tối ưu cú pháp.

Một truy vấn GROUP BY/HAVING tốt không chỉ chạy được: nó phải **đếm/cộng đúng đơn vị nghiệp vụ, xử lý dữ liệu rỗng minh bạch, trả kết quả có kiểu rõ ràng, tôn trọng phân quyền và nhất quán với transaction**. Khi bảo đảm các điều đó, JPQL cho phép xây dựng phần lớn báo cáo nhóm thông thường trên mô hình entity mà không cần viết SQL thủ công cho từng DBMS.
