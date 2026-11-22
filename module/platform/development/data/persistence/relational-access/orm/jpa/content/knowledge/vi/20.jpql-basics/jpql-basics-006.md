# Sử dụng LIKE, BETWEEN và IN theo ngữ nghĩa JPQL

## 1. Vai trò của ba toán tử trong truy vấn JPA

Trong Jakarta Persistence (JPA), **JPQL (Jakarta Persistence Query Language)** truy vấn mô hình **entity và thuộc tính Java**, không trực tiếp truy vấn tên bảng/cột như SQL thông thường. Ba nhóm điều kiện rất hay gặp khi lọc danh sách là:

- **`LIKE`:** so khớp chuỗi theo **mẫu ký tự**; dùng cho tiền tố, hậu tố, từ khóa, ký tự đại diện.
- **`BETWEEN`:** kiểm tra giá trị nằm trong **khoảng có cả hai đầu mút**, ví dụ giá tiền, ngày, số lượng.
- **`IN`:** kiểm tra giá trị thuộc **một tập các lựa chọn** hoặc kết quả của truy vấn con; dùng cho danh sách ID, trạng thái, nhóm.

Ví dụ một màn hình danh sách sản phẩm cho phép tìm sản phẩm tên chứa “bàn phím”, có giá từ 200.000 đến 2.000.000 đồng và thuộc một trong hai trạng thái `ACTIVE` hoặc `DRAFT`:

```jpql
SELECT p
FROM Product p
WHERE LOWER(p.name) LIKE :namePattern
  AND p.price BETWEEN :minimumPrice AND :maximumPrice
  AND p.status IN :statuses
ORDER BY p.id
```

Ba toán tử cùng nằm trong mệnh đề `WHERE`, nhưng **mỗi toán tử có quy tắc riêng về kiểu dữ liệu, tham số, ranh giới và giá trị null**. Hiểu những quy tắc đó giúp tránh các lỗi như tìm kiếm sai dấu `%`, bỏ sót bản ghi ở thời điểm cuối ngày, điều kiện `IN` rỗng hoặc `NOT IN` trả ít kết quả hơn mong đợi.

**Mục tiêu của bài:** viết các câu JPQL đúng ngữ nghĩa, truyền tham số an toàn, dự đoán kết quả và chọn cách lọc phù hợp với nhu cầu thực tế.

## 2. Entity mẫu và dữ liệu minh họa

### 2.1. JPQL dùng tên entity và thuộc tính

Ta dùng mô hình `Product` và `Category`. Entity `Product` có:

- `name`: tên hiển thị.
- `sku`: mã sản phẩm.
- `description`: mô tả có thể null.
- `price`: đơn giá `BigDecimal`.
- `stock`: tồn kho.
- `status`: enum trạng thái.
- `createdAt`: thời điểm tạo `Instant`.
- `category`: quan hệ `@ManyToOne` đến `Category`.

**`ProductStatus.java`**

```java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
```

**`Category.java`**

```java
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

    @Column(name = "category_name", nullable = false)
    private String name;

    @Column(name = "enabled", nullable = false)
    private boolean enabled;

    protected Category() {
    }

    public Long getId() {
        return id;
    }
}
```

**`Product.java`**

```java
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

    @Column(name = "sku", nullable = false, unique = true, length = 64)
    private String sku;

    @Column(name = "product_name", nullable = false, length = 160)
    private String name;

    @Column(name = "description", length = 1000)
    private String description;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal price;

    @Column(name = "stock", nullable = false)
    private int stock;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private ProductStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "category_id")
    private Category category;

    protected Product() {
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

    public ProductStatus getStatus() {
        return status;
    }
}
```

Các constructor và setter phục vụ khởi tạo dữ liệu được lược bớt để tập trung vào truy vấn. Trong ứng dụng thật, entity vẫn cần cách tạo/biến đổi hợp lệ theo domain.

Ví dụ dữ liệu giả định:

| ID | `name` | `sku` | `price` | `status` | `stock` |
|---:|---|---|---:|---|---:|
| 1 | Bàn phím cơ | KB-001 | 890000.00 | ACTIVE | 12 |
| 2 | Bàn phím văn phòng | KB-002 | 250000.00 | ACTIVE | 0 |
| 3 | Chuột không dây | MS-001 | 390000.00 | DRAFT | 8 |
| 4 | Bàn phím mini | KB_003 | 1200000.00 | ARCHIVED | 2 |
| 5 | USB 100% chính hãng | USB-010 | 190000.00 | ACTIVE | 24 |
| 6 | Bàn di chuột | PAD-001 | 150000.00 | DRAFT | 30 |

Ví dụ trên chỉ dùng để giải thích kết quả; thứ tự mặc định **không được bảo đảm** nếu câu truy vấn thiếu `ORDER BY`.

### 2.2. Phân biệt JPQL với SQL

JPQL:

```jpql
SELECT p
FROM Product p
WHERE p.name LIKE :pattern
```

SQL tương ứng có thể là:

```sql
SELECT p.*
FROM products p
WHERE p.product_name LIKE ?
```

Điểm khác:

- `Product` là **tên entity** (`@Entity`), không phải bảng `products`.
- `p.name` là **thuộc tính Java**, không phải tên cột `product_name`.
- `:pattern` là tham số JPQL được binding, không phải giá trị nối chuỗi vào câu truy vấn.
- JPA provider chuyển JPQL thành SQL tương thích với dialect của database.

Trong toàn bộ bài, các câu JPQL dùng đường dẫn thuộc tính Java như `p.price` và `p.createdAt`. Tên cột vật lý chỉ xuất hiện trong ví dụ SQL/DDL.

### 2.3. Mẫu chạy TypedQuery

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;

TypedQuery<Product> query = em.createQuery(
    "SELECT p FROM Product p WHERE p.status = :status",
    Product.class
);

query.setParameter("status", ProductStatus.ACTIVE);

List<Product> results = query.getResultList();
```

`em` là một `EntityManager` hợp lệ, còn `results` là tập entity trả về theo query. Các ví dụ tiếp theo sẽ dùng kiểu `TypedQuery<Product>` này. Cần import `java.util.List` khi chạy đoạn mã trong lớp Java.

## 3. `LIKE`: tìm chuỗi theo mẫu

### 3.1. Cú pháp và ba ký tự quan trọng

Cú pháp khái quát:

```jpql
string_expression [NOT] LIKE pattern [ESCAPE escape_character]
```

Các ký tự đặc biệt của `LIKE`:

| Ký tự | Ý nghĩa trong mẫu `LIKE` | Ví dụ |
|---|---|---|
| `%` | Đại diện **không hoặc nhiều** ký tự | `'Bàn%'`: bắt đầu bằng “Bàn” |
| `_` | Đại diện **đúng một** ký tự | `'KB_001'`: “KB” + một ký tự + “001” |
| Ký tự escape do bạn chọn | Khiến `%` hoặc `_` được hiểu là ký tự thường | `'100!%' ESCAPE '!'`: khớp chữ “100%” |

Lưu ý: `%` có thể khớp cả **chuỗi rỗng**. Dấu `_` không đại diện một đoạn bất kỳ; nó chỉ khớp **một** ký tự theo ngữ nghĩa so khớp của database.

### 3.2. Tìm bắt đầu bằng tiền tố

```jpql
SELECT p
FROM Product p
WHERE p.name LIKE 'Bàn%'
ORDER BY p.name
```

Mẫu `'Bàn%'` có nghĩa:

- Phần đầu phải là chuỗi “Bàn”.
- Phía sau có thể không có hoặc có nhiều ký tự.

Trong tập dữ liệu minh họa, các tên như “Bàn phím cơ”, “Bàn phím mini” và “Bàn di chuột” phù hợp, nếu quy tắc phân biệt hoa/thường và collation của DB khớp cách viết đó.

Nếu tiền tố đến từ người dùng, truyền bằng tham số:

```java
String prefix = "Bàn";

List<Product> items = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.name LIKE :pattern ORDER BY p.name",
        Product.class
    )
    .setParameter("pattern", prefix + "%")
    .getResultList();
```

Không cần nối trực tiếp `prefix` vào **chuỗi JPQL**; chỉ xây dựng **giá trị tham số**.

### 3.3. Tìm kết thúc bằng hậu tố

```jpql
SELECT p
FROM Product p
WHERE p.name LIKE :suffixPattern
```

```java
query.setParameter("suffixPattern", "%không dây");
```

Mẫu `'%không dây'` khớp các chuỗi kết thúc đúng bằng “không dây” theo quy tắc so khớp của database.

### 3.4. Tìm chứa một đoạn bất kỳ

```jpql
SELECT p
FROM Product p
WHERE p.name LIKE :containsPattern
```

```java
query.setParameter("containsPattern", "%phím%");
```

Đây là tìm **substring**, không phải tìm một từ độc lập hay tìm kiếm toàn văn (*full-text search*). Mẫu `'%phím%'` khớp bất kỳ chuỗi nào chứa đoạn “phím”, kể cả khi đoạn này nằm giữa một từ dài hơn.

### 3.5. Mẫu có ký tự đại diện ở giữa

```jpql
SELECT p FROM Product p
WHERE p.sku LIKE 'KB_001'
```

Mẫu trên **không có nghĩa** “SKU bằng đúng `KB_001`”. Dấu gạch dưới là wildcard một ký tự; nó có thể khớp `KB-001`, `KB_001` hoặc `KBX001` theo ngữ nghĩa của LIKE.

Nếu cần đối sánh mã SKU **chính xác**, dùng:

```jpql
SELECT p FROM Product p
WHERE p.sku = :sku
```

Với `:sku = "KB_001"`, toán tử `=` tránh toàn bộ quy tắc wildcard. Dùng `LIKE` khi thực sự muốn so khớp mẫu; đừng biến phép so sánh bằng thành LIKE nếu không có nhu cầu.

## 4. `ESCAPE`: tìm ký tự `%` và `_` theo nghĩa đen

### 4.1. Tại sao cần escape?

Giả sử người dùng tìm sản phẩm chứa đúng chuỗi `100%`:

```text
Người dùng nhập: 100%
Ý định: tìm ký tự phần trăm thực sự.
```

Nếu viết:

```java
String pattern = "%100%%";
```

dấu `%` người dùng nhập vẫn là wildcard. Mẫu đó có thể khớp “100 sản phẩm” hoặc “100abc”, không chỉ chuỗi chứa “100%”.

Cần chọn ký tự escape (ví dụ `!`) và viết:

```jpql
SELECT p
FROM Product p
WHERE p.name LIKE :pattern ESCAPE '!'
```

```java
query.setParameter("pattern", "%100!%%");
```

Phân tích `%100!%%`:

- `%` đầu: cho phép ký tự bất kỳ trước “100”.
- `100`: ba ký tự thường.
- `!%`: dấu phần trăm **theo nghĩa đen**.
- `%` cuối: cho phép ký tự bất kỳ phía sau.

Trong dữ liệu minh họa, tên “USB 100% chính hãng” phù hợp.

### 4.2. Escape dấu gạch dưới

Để tìm SKU bắt đầu chính xác bằng chuỗi `KB_`:

```jpql
SELECT p
FROM Product p
WHERE p.sku LIKE 'KB!_%' ESCAPE '!'
```

`!_` được hiểu là ký tự gạch dưới thật, còn `%` cuối vẫn là wildcard. Mẫu này **không** khớp `KB-001`, nhưng có thể khớp `KB_003`.

### 4.3. Escape chính ký tự escape

Nếu dùng `!` làm ký tự escape và chuỗi tìm kiếm cũng chứa `!`, phải thể hiện ký tự này một cách đúng:

```text
Người dùng nhập: A!B
Mẫu cần khớp chứa literal "A!B": %A!!B%
```

`!!` biểu diễn ký tự `!` theo nghĩa đen khi `ESCAPE '!'` được áp dụng.

### 4.4. Hàm Java chuẩn bị mẫu tìm kiếm an toàn

Một helper tìm *substring literal*:

```java
public final class LikePatterns {

    private LikePatterns() {
    }

    public static String containsLiteral(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Từ khóa không được null");
        }

        String escaped = raw
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");

        return "%" + escaped + "%";
    }
}
```

Dùng trong JPQL:

```java
String text = "100%";

List<Product> products = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.name LIKE :pattern ESCAPE '!'",
        Product.class
    )
    .setParameter("pattern", LikePatterns.containsLiteral(text))
    .getResultList();
```

Thứ tự trong helper có ý nghĩa: **escape ký tự `!` trước**, rồi mới escape `%` và `_`. Nếu làm ngược, có thể escape lại ký tự `!` do chính helper mới thêm vào và làm mẫu sai.

Đây là một chính sách cho phép **tìm literal substring**. Nếu giao diện chủ đích cho người dùng nhập mẫu wildcard nâng cao, phải thiết kế một quy tắc đầu vào khác và giải thích rõ cách dùng `%`/`_`. Không trộn hai cách hiểu trong cùng một ô tìm kiếm mà không có quy ước.

### 4.5. ESCAPE là cách định nghĩa pattern, không thay thế parameter binding

Hai việc giải quyết hai vấn đề khác nhau:

- `setParameter` giúp truyền giá trị tách khỏi cú pháp JPQL/SQL; tránh nối text người dùng vào câu truy vấn.
- `ESCAPE` giúp ngăn `%`/`_` trong giá trị người dùng bị diễn giải thành wildcard nếu ý định là tìm chuỗi literal.

Ngay cả khi dùng bind parameter, **`LIKE :pattern` vẫn hiểu wildcard bên trong giá trị tham số**. Ngược lại, escape wildcard không cho phép ghép raw text người dùng vào cấu trúc JPQL.

## 5. `LIKE`, phân biệt hoa/thường và dấu tiếng Việt

### 5.1. Không giả định LIKE mặc nhiên bỏ qua hoa/thường

`LIKE` không được xem là case-insensitive trong mọi database. Kết quả phụ thuộc hệ quản trị, collation và cấu hình cột/query.

Ví dụ:

```jpql
SELECT p FROM Product p
WHERE p.name LIKE :pattern
```

Với `:pattern = "%bàn%"`, kết quả có thể khác giữa các DB/collation khi dữ liệu bắt đầu bằng `"Bàn"`.

Nếu ứng dụng muốn tìm không phân biệt hoa/thường ở mức tương đối phổ biến, có thể chuyển hai phía về chữ thường:

```jpql
SELECT p
FROM Product p
WHERE LOWER(p.name) LIKE :pattern ESCAPE '!'
ORDER BY p.id
```

```java
import java.util.Locale;

String keyword = "BÀN PHÍM";

String pattern = LikePatterns
    .containsLiteral(keyword.toLowerCase(Locale.ROOT));

List<Product> products = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE LOWER(p.name) LIKE :pattern ESCAPE '!'",
        Product.class
    )
    .setParameter("pattern", pattern)
    .getResultList();
```

`LOWER` là hàm chuỗi JPQL, được provider chuyển xuống database. Dùng `Locale.ROOT` ở Java tránh một số bất ngờ do locale mặc định của máy chạy.

### 5.2. Case-insensitive không đồng nghĩa accent-insensitive

Hai chuỗi `"ban phim"` và `"bàn phím"` khác nhau về dấu. Chuyển sang lowercase **không tự động bỏ dấu tiếng Việt**. Việc so khớp có bỏ dấu hay không phụ thuộc collation, cách chuẩn hóa Unicode và/hoặc chiến lược tìm kiếm.

Nếu yêu cầu tìm không dấu, cần xác định cơ chế nhất quán giữa:

- Dữ liệu lưu trong DB.
- Giá trị tìm kiếm người dùng nhập.
- Collation hoặc cột đã chuẩn hóa.
- Index phục vụ tìm kiếm.
- Quy tắc chuẩn hóa Unicode và dấu.

Không tuyên bố rằng `LOWER` tự giải quyết mọi trường hợp không dấu, Unicode hoặc viết tắt.

### 5.3. Hàm trên cột ảnh hưởng index

Điều kiện:

```jpql
WHERE LOWER(p.name) LIKE :pattern
```

có thể khiến index B-tree thông thường trên `name` khó được sử dụng như dự kiến, tùy database. Có thể cần functional index/collation phù hợp, nhưng đây là quyết định ở tầng database, không phải một tính năng JPA bảo đảm.

Tìm kiếm `'%keyword%'` (wildcard ở đầu) cũng thường khó tận dụng tìm kiếm theo tiền tố của index B-tree. Với dữ liệu lớn và tìm kiếm ngôn ngữ tự nhiên, cân nhắc full-text search hoặc cấu trúc index chuyên dụng theo database.

## 6. `NOT LIKE` và giá trị null

### 6.1. Phủ định mẫu

```jpql
SELECT p
FROM Product p
WHERE p.name NOT LIKE :pattern
```

Điều kiện trả về các sản phẩm có tên **không khớp** mẫu, với điều kiện giá trị đủ xác định để đánh giá.

Có thể viết kết hợp:

```jpql
WHERE p.name NOT LIKE :pattern
  AND p.status = :status
```

Đừng nhầm `NOT LIKE` với “tất cả các entity còn lại, kể cả tên null”.

### 6.2. Null và logic ba giá trị

SQL/JPQL vận hành theo logic **TRUE, FALSE, UNKNOWN** khi có `NULL`. Nếu `p.description` là `NULL`:

```jpql
p.description LIKE :pattern
```

không cho TRUE, và:

```jpql
p.description NOT LIKE :pattern
```

cũng **không** trở thành TRUE. Cả hai biểu thức có thể cho `UNKNOWN`; các hàng không thỏa `TRUE` không được giữ lại bởi `WHERE`.

Nếu muốn lấy cả mô tả null lẫn mô tả không khớp:

```jpql
SELECT p
FROM Product p
WHERE p.description IS NULL
   OR p.description NOT LIKE :pattern
```

Dùng ngoặc khi còn các điều kiện `AND` khác:

```jpql
SELECT p
FROM Product p
WHERE p.status = :status
  AND (
      p.description IS NULL
      OR p.description NOT LIKE :pattern
  )
```

Nếu bỏ ngoặc, `AND` và `OR` có độ ưu tiên khác nhau, có thể làm trả thêm sản phẩm không đúng trạng thái mong muốn.

### 6.3. Truyền pattern null không có nghĩa “bỏ filter”

```java
query.setParameter("pattern", null);
```

Không phải chỉ thị để provider bỏ điều kiện `LIKE`. So sánh với giá trị null có thể trở thành UNKNOWN và không trả về các hàng mong đợi.

Đối với filter tùy chọn, nên **chỉ thêm điều kiện `LIKE` khi có từ khóa hợp lệ**, hoặc thiết kế biểu thức điều kiện rõ nghĩa. `COALESCE` và `OR :param IS NULL` là các kỹ thuật có thể dùng nhưng cần cân nhắc typing, query plan và yêu cầu logic cụ thể.

## 7. `BETWEEN`: khoảng bao gồm hai đầu mút

### 7.1. Cú pháp

```jpql
value_expression [NOT] BETWEEN lower_bound AND upper_bound
```

Đối với giá trị so sánh hợp lệ, điều kiện:

```jpql
p.price BETWEEN :minPrice AND :maxPrice
```

có ngữ nghĩa tương đương:

```jpql
p.price >= :minPrice AND p.price <= :maxPrice
```

**`BETWEEN` bao gồm cả cận dưới lẫn cận trên.** Đây là khác biệt quan trọng so với nhiều khoảng trong code được thiết kế theo dạng nửa mở `[from, to)`.

### 7.2. Ví dụ lọc đơn giá

```jpql
SELECT p
FROM Product p
WHERE p.price BETWEEN :minPrice AND :maxPrice
ORDER BY p.price ASC, p.id ASC
```

```java
import java.math.BigDecimal;

BigDecimal minimum = new BigDecimal("250000.00");
BigDecimal maximum = new BigDecimal("890000.00");

List<Product> matches = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.price BETWEEN :minPrice AND :maxPrice " +
        "ORDER BY p.price ASC, p.id ASC",
        Product.class
    )
    .setParameter("minPrice", minimum)
    .setParameter("maxPrice", maximum)
    .getResultList();
```

Theo dữ liệu giả định, sản phẩm giá đúng `250000.00` và `890000.00` **đều được chọn** nếu không có điều kiện khác loại chúng.

Dùng `BigDecimal` cho kiểu giá tiền trong Java; tránh chuyển tiền sang `double` rồi hy vọng biểu diễn nhị phân luôn chính xác. Kích thước `precision`/`scale` ở mapping và database phải phù hợp miền dữ liệu.

### 7.3. Khoảng một điểm

Nếu `minPrice = maxPrice = 250000.00`:

```jpql
p.price BETWEEN :minPrice AND :maxPrice
```

chỉ khớp giá bằng điểm đó (với giá trị không null và kiểu so sánh tương thích).

### 7.4. Cận đảo ngược không được tự sắp xếp

Nếu `minPrice = 900000` nhưng `maxPrice = 100000`, `BETWEEN` **không tự đổi chỗ hai cận**. Với dữ liệu số thông thường, không có giá trị nào đồng thời `>= 900000` và `<= 100000`.

Nên kiểm tra input trước khi chạy query:

```java
if (minimum != null
        && maximum != null
        && minimum.compareTo(maximum) > 0) {
    throw new IllegalArgumentException(
        "Giá tối thiểu phải nhỏ hơn hoặc bằng giá tối đa");
}
```

Tùy nghiệp vụ có thể đổi chỗ cận, nhưng đó phải là quyết định được công bố trong API/giao diện, không phải ngữ nghĩa mặc định của JPQL.

### 7.5. Dạng tương đương của `NOT BETWEEN`

```jpql
SELECT p FROM Product p
WHERE p.price NOT BETWEEN :minPrice AND :maxPrice
```

Với các giá trị không null, nó có ngữ nghĩa:

```jpql
WHERE p.price < :minPrice OR p.price > :maxPrice
```

Giá đúng bằng một trong hai cận **không nằm ngoài khoảng**. Nếu `p.price` hoặc một bound là null, phải xét logic UNKNOWN; không giả định phủ định sẽ chọn null.

## 8. `BETWEEN` với ngày và thời điểm

### 8.1. `LocalDate`: ngày không mang giờ

Giả sử entity có:

```java
@Column(name = "available_date")
private LocalDate availableDate;
```

Nếu chỉ muốn lọc lịch theo ngày `LocalDate`, một `BETWEEN` bao gồm hai ngày là dễ hiểu:

```jpql
SELECT p
FROM Product p
WHERE p.availableDate BETWEEN :fromDate AND :toDate
```

```java
LocalDate from = LocalDate.of(2026, 11, 1);
LocalDate to   = LocalDate.of(2026, 11, 30);

query.setParameter("fromDate", from);
query.setParameter("toDate", to);
```

Ngày `2026-11-01` và `2026-11-30` đều nằm trong khoảng. Ví dụ này giả định field `availableDate` tồn tại và được ánh xạ theo kiểu `LocalDate`. Nó độc lập với `Product.createdAt` kiểu `Instant` trong entity nền tảng.

### 8.2. `Instant` hoặc timestamp: lưu ý thời điểm cuối ngày

Giả sử muốn tìm sản phẩm được tạo trong ngày 15/11/2026 theo múi giờ Việt Nam. Một cách dễ sai:

```java
Instant start = ...; // 00:00:00 ngày 15/11.
Instant end = ...;   // 00:00:00 ngày 15/11.

query.setParameter("from", start);
query.setParameter("to", end);
```

Dùng `BETWEEN start AND end` với hai cận đều tại 00:00 cùng ngày chỉ chọn một thời điểm duy nhất, không phải toàn bộ ngày.

Một cách khác cũng dễ sai là đặt cận trên tại `23:59:59`, vì dữ liệu có độ chính xác mili-giây, micro-giây hoặc nanosecond có thể nằm sau thời điểm đó trong cùng ngày.

### 8.3. Khoảng nửa mở `[start, endExclusive)`

Khi lọc dữ liệu timestamp theo **ngày lịch**, thường nên dùng:

```jpql
SELECT p
FROM Product p
WHERE p.createdAt >= :startInclusive
  AND p.createdAt < :endExclusive
ORDER BY p.createdAt, p.id
```

Ví dụ tạo hai cận theo `ZoneId`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

LocalDate chosenDate = LocalDate.of(2026, 11, 15);

Instant startInclusive = chosenDate
    .atStartOfDay(businessZone)
    .toInstant();

Instant endExclusive = chosenDate
    .plusDays(1)
    .atStartOfDay(businessZone)
    .toInstant();

List<Product> matches = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.createdAt >= :startInclusive " +
        "AND p.createdAt < :endExclusive",
        Product.class
    )
    .setParameter("startInclusive", startInclusive)
    .setParameter("endExclusive", endExclusive)
    .getResultList();
```

Điều kiện `>=` và `<` là **nửa mở**:

```text
Ngày được chọn theo businessZone:

[startInclusive ------------------------- endExclusive)
  00:00 ngày 15                            00:00 ngày 16

Bao gồm mọi thời điểm trong ngày 15.
Không bao gồm thời điểm bắt đầu ngày 16.
```

Cách này tránh phải đoán độ chính xác nhỏ nhất mà database lưu. Nó cũng làm các ngày liền kề không bị trùng tại điểm ranh giới.

### 8.4. Vì sao không lấy `start.plus(1, DAYS)` cho mọi timezone?

Ngày lịch ở các múi giờ có điều chỉnh DST có thể không dài chính xác 24 giờ. Tính `endExclusive` bằng **đầu ngày tiếp theo trong đúng `ZoneId` nghiệp vụ** giúp biểu diễn phạm vi ngày lịch, thay vì giả định mọi ngày đều là 86.400 giây.

Với `Asia/Ho_Chi_Minh` hiện đại thường không có chuyển đổi DST, nhưng sử dụng `LocalDate.plusDays(1).atStartOfDay(zone)` vẫn là cách diễn đạt tốt khi ứng dụng có nhiều timezone.

### 8.5. Khi nào dùng `BETWEEN` cho timestamp?

`BETWEEN` phù hợp khi yêu cầu là **đúng nghĩa khoảng đóng**, tức hai thời điểm đầu/cuối đều phải được tính vào:

```jpql
WHERE p.createdAt BETWEEN :exactStart AND :exactEnd
```

Ví dụ một báo cáo lấy bản ghi từ lúc A đến **bao gồm chính thời điểm B**. Tuy nhiên, nếu upper bound biểu diễn ngày cuối của một khoảng theo giao diện người dùng, nửa mở `>= from AND < nextDayStart` thường ít gây lỗi hơn.

### 8.6. Dữ liệu thời gian và mapping

- `LocalDate`: dùng cho ngày lịch không có giờ.
- `LocalDateTime`: chứa ngày và giờ nhưng không có offset/zone; cần quy ước dữ liệu thống nhất.
- `Instant`: biểu diễn thời điểm tuyệt đối, tiện cho audit timestamp.
- `OffsetDateTime`: có offset, cần hiểu cách JPA provider/DB lưu và đọc.
- `java.util.Date` hoặc `Calendar` ở code legacy có các quy tắc ánh xạ thời gian riêng.

Điều kiện `BETWEEN` không tự biết múi giờ mà người dùng muốn. **Chuyển dữ liệu đầu vào sang đúng kiểu và phạm vi thời gian trước khi binding**.

## 9. `BETWEEN` với null và khoảng mở

### 9.1. Null làm điều kiện không xác định

Nếu `p.price` là null, hoặc một cận so sánh null, biểu thức `BETWEEN` không tự bỏ qua phần null. Nó có thể cho kết quả UNKNOWN theo logic ba giá trị (hoặc bị từ chối ở mức binding/type tùy ngữ cảnh).

Không viết:

```java
query.setParameter("minPrice", null);
query.setParameter("maxPrice", maximum);
```

rồi kỳ vọng đó là `price <= maximum`. JPQL không tự biến cận null thành “không giới hạn”.

### 9.2. Chỉ có cận dưới

```jpql
SELECT p FROM Product p
WHERE p.price >= :minPrice
```

### 9.3. Chỉ có cận trên

```jpql
SELECT p FROM Product p
WHERE p.price <= :maxPrice
```

### 9.4. Có cả hai cận

```jpql
SELECT p FROM Product p
WHERE p.price BETWEEN :minPrice AND :maxPrice
```

Với bộ lọc tùy chọn, nên sinh **đúng predicate theo số cận người dùng cung cấp**, hoặc dùng Criteria API để ghép điều kiện có chủ đích. Đặt `null` vào `BETWEEN` để mong provider tự hiểu open-ended range là một lỗi thiết kế thường gặp.

### 9.5. BETWEEN với chuỗi

Một số dạng `BETWEEN` trong JPQL cũng dùng được với các biểu thức chuỗi có thể so sánh, nhưng thứ tự chuỗi phụ thuộc **collation và quy tắc sắp xếp của database**:

```jpql
SELECT p FROM Product p
WHERE p.sku BETWEEN :fromSku AND :toSku
```

Không nên tự cho rằng `'SKU-2'` luôn nằm trước `'SKU-10'` theo logic số học. Với chuỗi, thứ tự có thể là lexicographic/collation order, không phải “natural sort”. Nếu thực sự muốn lọc số thứ tự trong mã, nên lưu thành một cột số có cấu trúc rõ ràng.

## 10. `IN`: thuộc tập giá trị

### 10.1. Cú pháp cơ bản

`IN` kiểm tra một giá trị có bằng **ít nhất một** phần tử trong tập so sánh hay không:

```jpql
SELECT p
FROM Product p
WHERE p.status IN (
    com.example.catalog.ProductStatus.ACTIVE,
    com.example.catalog.ProductStatus.DRAFT
)
```

Đoạn này minh họa enum literal theo tên đầy đủ; trong ứng dụng nên **bind enum value** thay vì cố gắn chặt tên package vào JPQL.

Ví dụ gần gũi hơn với ID:

```jpql
SELECT p
FROM Product p
WHERE p.id IN (1, 3, 5)
ORDER BY p.id
```

Ý nghĩa logic:

```text
p.id = 1 OR p.id = 3 OR p.id = 5
```

Với tập dữ liệu minh họa, điều kiện trả về Product có ID 1, 3 và 5.

### 10.2. Dùng tham số collection

Một tình huống phổ biến là API nhận danh sách các ID:

```java
List<Long> requestedIds = List.of(1L, 3L, 5L);

List<Product> products = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.id IN :ids ORDER BY p.id",
        Product.class
    )
    .setParameter("ids", requestedIds)
    .getResultList();
```

JPQL hỗ trợ tham số collection cho điều kiện `IN` theo cách dùng chuẩn/thông dụng của JPA. Một số codebase/provider còn viết `IN (:ids)`; cần dùng cú pháp nhất quán với phiên bản JPA/provider thực tế, tránh nối thủ công danh sách thành chuỗi SQL.

`IN :ids` được minh họa cho **tham số nhiều phần tử**, còn tham số kiểu `Long` đơn lẻ phù hợp với `= :id`. Dùng collection typed đúng kiểu khóa của entity.

### 10.3. `IN` với enum

Với `@Enumerated(EnumType.STRING)` ở `Product.status`:

```java
List<ProductStatus> statuses = List.of(
    ProductStatus.ACTIVE,
    ProductStatus.DRAFT
);

List<Product> products = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.status IN :statuses",
        Product.class
    )
    .setParameter("statuses", statuses)
    .getResultList();
```

JPA biết metadata enum của `p.status` và thực hiện binding thích hợp. **Không đổi `List<ProductStatus>` thành `List<String>` chỉ vì database đang lưu chuỗi `'ACTIVE'`.** JPQL thao tác với kiểu thuộc tính Java, còn provider chịu trách nhiệm chuyển đổi sang biểu diễn database.

Khi thêm `@Enumerated(EnumType.STRING)`, việc đổi tên hằng enum có thể yêu cầu migration dữ liệu đã lưu. Đây là một quyết định mapping độc lập với cú pháp `IN`.

### 10.4. `NOT IN`

```jpql
SELECT p
FROM Product p
WHERE p.status NOT IN :excludedStatuses
```

Với danh sách không null gồm `ARCHIVED`, truy vấn chọn các sản phẩm có status không phải ARCHIVED.

Tuy nhiên, `NOT IN` **không hoàn toàn tương đương “tất cả trừ các phần tử trong danh sách” khi có null**, vì logic ba giá trị sẽ ảnh hưởng kết quả.

## 11. `IN` với danh sách rỗng và null

### 11.1. Vấn đề danh sách rỗng

Giả sử API nhận:

```java
List<Long> ids = List.of();
```

Rồi chạy:

```jpql
WHERE p.id IN :ids
```

Đừng mặc định mọi JPA provider và database xử lý collection rỗng giống nhau. Provider có thể không chấp nhận, tạo SQL `IN ()` không hợp lệ ở một số hệ quản trị, hoặc áp dụng cách diễn giải riêng.

Cách xử lý nên dựa trên ý định nghiệp vụ.

**Trường hợp A — người dùng yêu cầu tập ID rỗng, nghĩa là không có kết quả:**

```java
public List<Product> findByIds(
        EntityManager em,
        List<Long> ids) {

    if (ids == null) {
        throw new IllegalArgumentException("ids không được null");
    }

    if (ids.isEmpty()) {
        return List.of();
    }

    return em.createQuery(
            "SELECT p FROM Product p WHERE p.id IN :ids",
            Product.class
        )
        .setParameter("ids", ids)
        .getResultList();
}
```

**Trường hợp B — bộ lọc trạng thái là tùy chọn, list rỗng nghĩa là không lọc:**

```java
if (statuses == null || statuses.isEmpty()) {
    // Không thêm predicate "p.status IN :statuses".
}
```

Hai ý nghĩa này khác nhau. Ví dụ “lấy đúng các ID đã chọn” với danh sách rỗng phải trả kết quả rỗng; nhưng “chưa chọn filter trạng thái” có thể trả mọi trạng thái. **Quy ước API phải phân biệt chúng.**

### 11.2. Null bên trong danh sách

Giả sử:

```text
IN ('ACTIVE', NULL)
```

Với giá trị `ACTIVE`, biểu thức `IN` có thể TRUE vì đã khớp một phần tử. Với giá trị không phải ACTIVE và khác null, phép so sánh với NULL có thể cho UNKNOWN thay vì FALSE.

Quan trọng hơn với `NOT IN`:

```text
status NOT IN ('ARCHIVED', NULL)
```

Một status không bằng ARCHIVED cũng **không chắc được chọn**, bởi phép so sánh với NULL vẫn UNKNOWN. Kết quả của `NOT IN` có thể rỗng một cách khó hiểu.

**Thực hành an toàn:** lọc hoặc từ chối giá trị `null` trong danh sách dùng cho `IN`/`NOT IN` theo quy tắc đầu vào; đặc biệt không để null lẫn vào danh sách loại trừ.

### 11.3. Muốn tìm cột null phải dùng `IS NULL`

Nếu `p.description` có thể null và muốn tìm những Product có mô tả null **hoặc** thuộc một danh sách mô tả:

```jpql
SELECT p
FROM Product p
WHERE p.description IS NULL
   OR p.description IN :descriptions
```

Tương tự, `p.description NOT IN :values` không tự bao gồm hàng có description null.

### 11.4. Null cho tham số collection

```java
query.setParameter("ids", null);
```

không nên được coi là “bỏ qua `IN`”. Ngoài semantics UNKNOWN, provider có thể không suy ra được cách bind collection khi nhận null. Dùng một nhánh điều kiện tạo truy vấn phù hợp với logic API.

## 12. `IN` với subquery

### 12.1. Danh sách tĩnh và truy vấn con

`IN` có thể dùng **truy vấn con** thay cho danh sách literal/parameter:

```jpql
SELECT p
FROM Product p
WHERE p.category.id IN (
    SELECT c.id
    FROM Category c
    WHERE c.enabled = TRUE
)
```

Điều kiện này chọn các Product thuộc Category đang enabled. Truy vấn con trả các `Category.id`, cùng loại với `p.category.id`.

Câu JPQL không viết `FROM products` hoặc `FROM categories`; vẫn dùng tên entity `Product` và `Category`, cùng đường dẫn thuộc tính.

### 12.2. Khi nào `JOIN` phù hợp hơn?

Cùng bài toán có thể viết:

```jpql
SELECT p
FROM Product p
JOIN p.category c
WHERE c.enabled = TRUE
```

Hai cách có thể có ý nghĩa tương đương đối với mapping và điều kiện này, nhưng chiến lược thực thi phụ thuộc optimizer/database. **`IN (subquery)` không mặc định nhanh hơn hoặc chậm hơn `JOIN`** trong mọi tình huống.

Chọn cách diễn đạt rõ ràng nhất cho yêu cầu, kiểm tra SQL sinh ra và execution plan với dữ liệu thực tế khi hiệu năng là vấn đề.

### 12.3. `IN` không phải phép kiểm tra collection relationship theo mọi hướng

Nếu `Product` có `@ManyToMany Set<Tag> tags`, cú pháp:

```jpql
-- Không dùng collection-valued path trực tiếp như một scalar:
WHERE p.tags IN :tags
```

không phải cách đúng để lọc nhiều tag ID. Nên join vào phần tử collection:

```jpql
SELECT DISTINCT p
FROM Product p
JOIN p.tags t
WHERE t.id IN :tagIds
```

`DISTINCT` cần cân nhắc vì một Product có thể được ghép nhiều tag phù hợp và xuất hiện nhiều lần trong kết quả của phép join. Với một tag cụ thể, có thể dùng `:tag MEMBER OF p.tags` khi đó đúng mô hình và mục tiêu truy vấn.

Đừng nhầm **“một thuộc tính scalar thuộc tập giá trị”** (`IN`) với **“một entity nằm trong collection relationship”** (`MEMBER OF` hoặc `JOIN`).

### 12.4. `NOT IN` subquery và NULL

`NOT IN (subquery)` cũng chịu ảnh hưởng của NULL trong tập do subquery trả về. Nếu một hàng null xuất hiện, điều kiện phủ định có thể trả ít kết quả bất ngờ.

Khi nhu cầu là **“không tồn tại hàng liên quan thỏa điều kiện”**, `NOT EXISTS` thường diễn tả ý định rõ hơn:

```jpql
SELECT p
FROM Product p
WHERE NOT EXISTS (
    SELECT c.id
    FROM Category c
    WHERE c = p.category
      AND c.enabled = FALSE
)
```

Ví dụ cần xác định thêm ý nghĩa của `p.category IS NULL`: với `NOT EXISTS`, Product không có Category cũng có thể được chọn, trong khi một `JOIN` nội bộ có thể loại nó. Hãy thiết kế theo domain và kiểm tra null rõ ràng.

## 13. Kiểu tham số và ngữ nghĩa so sánh

### 13.1. Tham số phải tương thích kiểu thuộc tính

Các loại thường gặp:

| JPQL | Thuộc tính Java | Kiểu tham số nên dùng |
|---|---|---|
| `p.name LIKE :pattern` | `String` | `String` |
| `p.price BETWEEN :min AND :max` | `BigDecimal` | `BigDecimal` |
| `p.stock BETWEEN :low AND :high` | `int` / `Integer` | `Integer` phù hợp |
| `p.createdAt >= :from` | `Instant` | `Instant` |
| `p.status IN :statuses` | `ProductStatus` | `Collection<ProductStatus>` |
| `p.id IN :ids` | `Long` | `Collection<Long>` |
| `p.category.id IN :categoryIds` | `Long` | `Collection<Long>` |

JPQL là ngôn ngữ định kiểu theo mô hình entity. Giá trị từ JSON/HTTP thường bắt đầu là chuỗi; hãy parse/validate ở service trước khi binding. Không kỳ vọng provider tự đoán một chuỗi `"250000"` thành `BigDecimal` trong mọi mapping.

### 13.2. Named parameter

```jpql
WHERE p.price BETWEEN :minPrice AND :maxPrice
```

```java
query.setParameter("minPrice", minPrice);
query.setParameter("maxPrice", maxPrice);
```

Named parameter phải có tên nhất quán. Không dùng dấu `:` khi truyền tên vào `setParameter`; dùng `"minPrice"`.

### 13.3. Positional parameter

JPQL cũng có positional parameters:

```jpql
SELECT p
FROM Product p
WHERE p.price BETWEEN ?1 AND ?2
```

```java
query.setParameter(1, minPrice);
query.setParameter(2, maxPrice);
```

Trong truy vấn nhiều bộ lọc, named parameters thường dễ đọc và ít lỗi khi thay thứ tự điều kiện. Không trộn tùy tiện cách binding tham số trong một query.

### 13.4. Không nối raw input vào JPQL

Ví dụ không nên dùng:

```java
String jpql = "SELECT p FROM Product p " +
              "WHERE p.name LIKE '%" + userInput + "%'";
```

Cách này trộn dữ liệu người dùng vào cú pháp query; ngoài nguy cơ injection còn có thể lỗi dấu nháy và escape. Hãy dùng:

```java
String jpql =
    "SELECT p FROM Product p " +
    "WHERE p.name LIKE :pattern ESCAPE '!'";

List<Product> rows = em.createQuery(jpql, Product.class)
    .setParameter(
        "pattern",
        LikePatterns.containsLiteral(userInput)
    )
    .getResultList();
```

Chỉ thêm vào chuỗi JPQL **những fragment cố định do ứng dụng kiểm soát**, không ghép trực tiếp giá trị không tin cậy.

## 14. Kết hợp `LIKE`, `BETWEEN` và `IN`

### 14.1. Câu JPQL tích hợp

Giả sử màn hình quản trị cần lọc:

- Tên chứa từ khóa (không phân biệt hoa/thường).
- Giá nằm trong một khoảng đóng.
- Trạng thái thuộc danh sách đã chọn.
- Chỉ hiển thị sản phẩm tạo trước thời điểm kết thúc báo cáo.

```jpql
SELECT p
FROM Product p
WHERE LOWER(p.name) LIKE :namePattern ESCAPE '!'
  AND p.price BETWEEN :minPrice AND :maxPrice
  AND p.status IN :statuses
  AND p.createdAt < :beforeExclusive
ORDER BY p.createdAt DESC, p.id DESC
```

`AND` yêu cầu tất cả điều kiện phải TRUE. Nếu bất kỳ điều kiện nào là FALSE hoặc UNKNOWN do null, hàng đó không được chọn.

### 14.2. Ví dụ binding

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Locale;

String keyword = "Bàn phím";
String namePattern = LikePatterns.containsLiteral(
    keyword.toLowerCase(Locale.ROOT)
);

BigDecimal minPrice = new BigDecimal("200000.00");
BigDecimal maxPrice = new BigDecimal("1200000.00");

List<ProductStatus> statuses = List.of(
    ProductStatus.ACTIVE,
    ProductStatus.DRAFT
);

Instant beforeExclusive =
    Instant.parse("2026-12-01T00:00:00Z");

List<Product> rows = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE LOWER(p.name) LIKE :namePattern ESCAPE '!' " +
        "AND p.price BETWEEN :minPrice AND :maxPrice " +
        "AND p.status IN :statuses " +
        "AND p.createdAt < :beforeExclusive " +
        "ORDER BY p.createdAt DESC, p.id DESC",
        Product.class
    )
    .setParameter("namePattern", namePattern)
    .setParameter("minPrice", minPrice)
    .setParameter("maxPrice", maxPrice)
    .setParameter("statuses", statuses)
    .setParameter("beforeExclusive", beforeExclusive)
    .getResultList();
```

Cách làm này giả định người dùng **có đủ cả ba filter bắt buộc**. Nếu một filter không được nhập, ta không nên truyền null hoặc collection rỗng một cách máy móc; phải chọn logic của filter tùy chọn.

### 14.3. Thứ tự ưu tiên `AND` và `OR`

`AND` có độ ưu tiên cao hơn `OR` trong biểu thức điều kiện thông thường. Xét:

```jpql
WHERE p.status = :active
   OR p.status = :draft
  AND p.price < :maxPrice
```

Nó không đồng nghĩa:

```jpql
WHERE (p.status = :active OR p.status = :draft)
  AND p.price < :maxPrice
```

Ở dạng đầu, điều kiện giá có thể chỉ ràng buộc nhánh `DRAFT` theo thứ tự ưu tiên. Nếu muốn cùng ràng buộc giá cho hai trạng thái, dùng ngoặc hoặc `IN`:

```jpql
WHERE p.status IN :statuses
  AND p.price < :maxPrice
```

### 14.4. Khi nào `IN` tốt hơn chuỗi `OR`?

Đoạn:

```jpql
WHERE p.status = :active OR p.status = :draft
```

có thể viết ngắn gọn:

```jpql
WHERE p.status IN :statuses
```

nếu các lựa chọn cùng thuộc tính. `IN` dễ bảo trì khi danh sách từ 2 tăng lên nhiều giá trị; binding collection giúp không cần tạo một tham số mới cho từng phần tử. Tuy nhiên, nếu các nhánh `OR` liên quan tới **những cột khác nhau** hoặc có logic khác nhau, chúng không thể được thay bằng một `IN` đơn.

## 15. Bộ lọc tùy chọn: xây query đúng semantics

### 15.1. Quy tắc API phải rõ ràng

Giả sử API nhận bộ lọc:

```java
public record ProductFilter(
    String keyword,
    BigDecimal minPrice,
    BigDecimal maxPrice,
    List<ProductStatus> statuses
) {}
```

Một thiết kế thường gặp:

- `keyword == null` hoặc blank → không lọc theo tên.
- `minPrice == null` → không có cận dưới.
- `maxPrice == null` → không có cận trên.
- `statuses == null` hoặc rỗng → không lọc trạng thái.

**Đây là chính sách của API ví dụ**, không phải ngữ nghĩa tự động của JPQL. Với API “chỉ lấy đúng các trạng thái người dùng chọn”, list rỗng có thể cần trả danh sách rỗng; phải quyết định trước.

### 15.2. Ghép những fragment cố định và bind tham số

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class ProductQueries {

    public List<Product> search(
            EntityManager em, ProductFilter filter) {

        List<String> predicates = new ArrayList<>();

        StringBuilder jpql = new StringBuilder(
            "SELECT p FROM Product p"
        );

        boolean hasKeyword = filter.keyword() != null
            && !filter.keyword().isBlank();

        if (hasKeyword) {
            predicates.add(
                "LOWER(p.name) LIKE :namePattern ESCAPE '!'"
            );
        }

        if (filter.minPrice() != null) {
            predicates.add("p.price >= :minPrice");
        }

        if (filter.maxPrice() != null) {
            predicates.add("p.price <= :maxPrice");
        }

        boolean hasStatuses = filter.statuses() != null
            && !filter.statuses().isEmpty();

        if (hasStatuses) {
            predicates.add("p.status IN :statuses");
        }

        if (!predicates.isEmpty()) {
            jpql.append(" WHERE ");
            jpql.append(String.join(" AND ", predicates));
        }

        jpql.append(" ORDER BY p.id");

        TypedQuery<Product> query =
            em.createQuery(jpql.toString(), Product.class);

        if (hasKeyword) {
            query.setParameter(
                "namePattern",
                LikePatterns.containsLiteral(
                    filter.keyword().toLowerCase(Locale.ROOT)
                )
            );
        }

        if (filter.minPrice() != null) {
            query.setParameter("minPrice", filter.minPrice());
        }

        if (filter.maxPrice() != null) {
            query.setParameter("maxPrice", filter.maxPrice());
        }

        if (hasStatuses) {
            query.setParameter("statuses", filter.statuses());
        }

        return query.getResultList();
    }
}
```

Ở đây các điều kiện được thêm vào truy vấn bằng những **chuỗi cố định trong source code**, còn giá trị người dùng luôn được đưa qua `setParameter`. Vì vậy đây không phải cách ghép raw input vào cú pháp JPQL.

Nếu cả `minPrice` và `maxPrice` có giá trị, ta dùng hai phép so sánh `>=` và `<=`, tương đương khoảng đóng `BETWEEN`. Cách viết đó cho phép dùng chung một cấu trúc code cho cả trường hợp có một hoặc hai cận.

### 15.3. Validate cận và giới hạn input

Trước khi gọi method tìm kiếm, có thể kiểm tra:

```java
if (filter.minPrice() != null
        && filter.maxPrice() != null
        && filter.minPrice().compareTo(filter.maxPrice()) > 0) {
    throw new IllegalArgumentException(
        "minPrice phải nhỏ hơn hoặc bằng maxPrice");
}
```

Cũng nên xác định giới hạn độ dài từ khóa, số lượng ID/trạng thái, số kết quả và phân trang. Một query có điều kiện đúng cú pháp vẫn có thể làm hệ thống quá tải nếu cho phép tìm `'%...%'` trên bảng rất lớn và trả không giới hạn dữ liệu.

### 15.4. Biểu thức `OR :param IS NULL`: tiện nhưng không luôn tối ưu

Một cách viết hay gặp:

```jpql
WHERE (:minPrice IS NULL OR p.price >= :minPrice)
  AND (:maxPrice IS NULL OR p.price <= :maxPrice)
```

Cách này có thể giúp giữ một query cố định, nhưng cần chú ý **kiểu của tham số null** và kế hoạch thực thi database. Một số DB/provider có thể khó suy ra loại tham số ở phép `IS NULL` hoặc sinh plan không tối ưu.

Không nên xem đây là kỹ thuật bắt buộc. Với filter phức tạp và nhiều trường tùy chọn, xây predicate có điều kiện bằng Criteria API hoặc các fragment JPQL cố định thường dễ kiểm soát hơn.

## 16. Criteria API: biểu diễn cùng toán tử bằng Java

JPQL không phải cách duy nhất để xây các điều kiện này. JPA Criteria API cho phép tạo biểu thức theo kiểu cấu trúc, hữu ích khi số filter động tăng.

### 16.1. LIKE bằng CriteriaBuilder

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> cq =
    cb.createQuery(Product.class);

Root<Product> p = cq.from(Product.class);

String pattern = LikePatterns.containsLiteral("bàn");

Predicate nameCondition = cb.like(
    cb.lower(p.get("name")),
    pattern,
    '!'
);
```

Ở đây `cb.like` biểu diễn `LOWER(p.name) LIKE :pattern ESCAPE '!'` theo cùng ý định so khớp. Các overload của `CriteriaBuilder.like` cho phép dùng pattern và escape character thích hợp.

### 16.2. BETWEEN bằng CriteriaBuilder

```java
Path<BigDecimal> pricePath = p.get("price");

Predicate priceCondition = cb.between(
    pricePath,
    new BigDecimal("250000.00"),
    new BigDecimal("890000.00")
);
```

`cb.between` dùng cùng ngữ nghĩa bao gồm hai cận như JPQL `BETWEEN`.

Khi chỉ có một cận:

```java
Predicate minPriceCondition = cb.greaterThanOrEqualTo(
    pricePath,
    new BigDecimal("250000.00")
);
```

### 16.3. IN bằng CriteriaBuilder

```java
List<ProductStatus> statuses = List.of(
    ProductStatus.ACTIVE,
    ProductStatus.DRAFT
);

Predicate statusCondition = p.get("status").in(statuses);
```

Hoặc dùng builder `cb.in(expression)` và thêm các giá trị theo ý định.

Phải kiểm tra danh sách rỗng theo **semantics API** trước khi tạo `in`; không nên mặc định một `IN` rỗng có hành vi portable như mong muốn trên mọi provider.

### 16.4. Kết hợp điều kiện

```java
cq.select(p)
  .where(cb.and(
      nameCondition,
      priceCondition,
      statusCondition
  ))
  .orderBy(cb.asc(p.get("id")));

List<Product> result =
    em.createQuery(cq).getResultList();
```

Các đoạn ở mục này là **một luồng minh họa** khi ghép lại trong cùng method, với import từ `jakarta.persistence.criteria` cùng `BigDecimal`, `List`. Trong code thực tế, chỉ thêm `Predicate` khi filter tương ứng được người dùng cung cấp; từ đó có thể xử lý linh hoạt trường hợp khoảng chỉ có một cận hoặc không có trạng thái.

### 16.5. Khi nào chọn JPQL hoặc Criteria API?

| Nhu cầu | Gợi ý |
|---|---|
| Một query cố định, ít filter | JPQL dễ đọc và ngắn |
| Vài filter tùy chọn, cách ghép đơn giản | JPQL với fragment cố định và named parameters |
| Nhiều filter động, nhánh AND/OR lồng nhau | Criteria API có thể dễ tổ chức |
| Cần kiểm tra kiểu property tại compile time | Criteria metamodel có thể hỗ trợ tốt hơn string path |
| Query hiệu năng quan trọng | So sánh SQL sinh ra và execution plan; API nào không tự bảo đảm nhanh hơn |

Cả hai cách đều phải hiểu đúng **`LIKE`, `BETWEEN`, `IN` và logic null**.

## 17. Hiệu năng và thiết kế chỉ mục

### 17.1. LIKE với wildcard đầu chuỗi

```jpql
WHERE p.name LIKE '%phím%'
```

Điều kiện có wildcard `%` ở đầu thường không cho phép dùng B-tree index theo kiểu tìm tiền tố thông thường. Với bảng nhỏ điều này có thể không đáng kể; với hàng triệu sản phẩm, truy vấn có thể phải kiểm tra rất nhiều dòng.

Nếu chỉ cần tìm tiền tố:

```jpql
WHERE p.name LIKE 'Bàn%'
```

database có thể có nhiều cơ hội tận dụng index hơn, tùy collation, operator class và query plan.

Nếu yêu cầu là tìm substring ngẫu nhiên có dấu/không dấu, cân nhắc giải pháp full-text, trigram hoặc search engine; đó là lựa chọn **phụ thuộc hệ thống**, không phải cú pháp JPQL portable.

### 17.2. LOWER và functional index

Điều kiện:

```jpql
WHERE LOWER(p.name) LIKE :pattern
```

áp dụng hàm lên cột; index thông thường trên `product_name` có thể không phục vụ tốt. Một số database hỗ trợ expression/functional index theo `LOWER(product_name)` hoặc collation/index chuyên dụng.

Không tạo index một cách máy móc trước khi biết workload, tính chọn lọc và cấu trúc query. Kiểm tra execution plan bằng công cụ của database.

### 17.3. BETWEEN và range scan

`BETWEEN` trên một cột số/ngày có index thích hợp thường có cơ hội dùng range scan:

```jpql
WHERE p.price BETWEEN :minPrice AND :maxPrice
```

Nhưng độ hiệu quả còn phụ thuộc độ rộng khoảng, thống kê dữ liệu, các điều kiện kết hợp và sắp xếp. Nếu khoảng bao phủ gần như toàn bộ bảng, optimizer có thể chọn quét bảng vì hợp lý hơn.

### 17.4. IN với danh sách rất lớn

Một `IN :ids` với vài giá trị là bài toán khác hẳn một danh sách hàng chục nghìn ID. Hệ quản trị/driver có thể có giới hạn số tham số hoặc kích thước câu SQL; kế hoạch thực thi và thời gian parse/bind cũng tăng.

Nếu danh sách lớn, xem xét:

- Giới hạn số ID được gửi qua API.
- Chia lô theo giới hạn database và kết hợp kết quả theo semantics của ứng dụng.
- Sử dụng bảng tạm, bảng giá trị, table-valued parameters hoặc cơ chế chuyên dụng của database.
- Dùng `IN (subquery)` thay vì tải toàn bộ ID ra Java rồi nạp ngược vào DB khi dữ liệu vốn nằm trong một bảng có thể lọc được.
- Kiểm tra duplicate IDs, null và thứ tự đầu ra.

**`IN` không bảo toàn thứ tự phần tử trong list đầu vào**. Nếu cần trả kết quả theo thứ tự ID do người dùng truyền, phải xây quy tắc sắp xếp riêng.

### 17.5. Phân trang và ORDER BY

Lọc đúng nhưng trả hàng chục nghìn entity vẫn có thể là vấn đề. Hạn chế tập kết quả:

```java
List<Product> page = em.createQuery(
        "SELECT p FROM Product p " +
        "WHERE p.name LIKE :pattern ESCAPE '!' " +
        "ORDER BY p.id",
        Product.class
    )
    .setParameter("pattern", "%bàn%")
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

`setFirstResult`/`setMaxResults` giúp phân trang kết quả query. `ORDER BY` làm thứ tự có thể dự đoán; dùng một cột duy nhất không unique khi phân trang dễ gây trùng/bỏ sót giữa các trang, vì vậy có thể thêm `p.id` làm tie-breaker.

Không tin rằng bảng dữ liệu tự có thứ tự nếu thiếu `ORDER BY`, kể cả lúc query được tối ưu qua index.

## 18. Những lỗi thường gặp

| Tình huống | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Tìm `100%` nhưng khớp cả `100abc` | `%` trong LIKE là wildcard | Dùng `ESCAPE` và escape ký tự từ người dùng |
| Tìm SKU `KB_003` nhưng khớp `KB-003` | `_` đại diện đúng một ký tự | Dùng `=` nếu tìm chính xác, hoặc `LIKE ... ESCAPE` |
| `LIKE '%term%'` không trả kết quả như mong đợi về chữ hoa | Case sensitivity phụ thuộc DB/collation | `LOWER` hai phía hoặc chiến lược collation phù hợp |
| Người dùng nhập không dấu nhưng dữ liệu có dấu | Lowercase không bỏ dấu tiếng Việt | Xác định chuẩn hóa/collation/search phù hợp |
| Query dùng `products.product_name` trong JPQL | JPQL dùng tên entity và property | `FROM Product p WHERE p.name ...` |
| Nối nguyên từ khóa người dùng vào query | Trộn input với cú pháp, lỗi quote/injection | Bind `:pattern` bằng `setParameter` |
| Giá đúng cận trên lại được chọn | `BETWEEN` bao gồm cả hai cận | Nếu muốn loại cận trên, dùng `< :max` |
| Báo cáo ngày bỏ sót bản ghi cuối ngày | Dùng `23:59:59` làm cận cuối | Dùng `>= start AND < nextDayStart` |
| Đặt `from > to` mà query không đổi lại | BETWEEN không tự sắp cận | Validate trước khi query |
| Truyền null vào cận BETWEEN | Null không có nghĩa “vô hạn” | Chỉ thêm predicate cho cận có giá trị |
| `IN :ids` rỗng gây lỗi hoặc kết quả lạ | Collection rỗng không portable | Xử lý nhánh rỗng theo ý định API |
| `NOT IN` không trả hàng nào khi list có null | UNKNOWN trong logic ba giá trị | Loại bỏ/từ chối null trong danh sách |
| `NOT LIKE` không lấy hàng có description null | UNKNOWN không được WHERE chọn | Thêm `IS NULL OR ...` khi cần |
| `IN` với danh sách enum string không tương thích | Thuộc tính entity có kiểu enum | Bind `ProductStatus` thay vì string tùy tiện |
| `p.tags IN :tags` không hợp lệ | `p.tags` là collection-valued path | `JOIN p.tags t WHERE t.id IN :ids` |
| `IN` có nhiều ID nhưng kết quả sai thứ tự | IN không bảo toàn input order | Thêm ORDER BY/quy tắc sắp xếp rõ |
| Kết hợp `OR` và `AND` trả thừa hàng | Độ ưu tiên toán tử | Dùng ngoặc đúng logic |
| LIKE/LOWER trên bảng lớn chạy chậm | Wildcard đầu, function và index không phù hợp | Kiểm tra SQL/plan; cân nhắc index/search chuyên dụng |
| Predicate optional null làm mất hết dữ liệu | So sánh với null tạo UNKNOWN | Tạo query động có điều kiện |
| Câu JPQL được viết đúng nhưng DB so khớp khác kỳ vọng | Collation, timezone, kiểu dữ liệu, dialect | Thử với dữ liệu và database thực tế |

## 19. Bài thực hành

### Bài 1 — Phân biệt ba dạng LIKE

Với bảng Product minh họa, viết ba query:

1. Tên bắt đầu bằng `"Bàn"`.
2. Tên kết thúc bằng `"không dây"`.
3. Tên có chứa `"phím"` ở bất kỳ vị trí nào.

Cho biết mẫu `LIKE` cần truyền và dự đoán các Product có thể được chọn theo collation đang sử dụng.

### Bài 2 — Tìm ký tự phần trăm thật

Thêm Product tên `"USB 100% chính hãng"`. Tạo một tìm kiếm substring literal từ khóa `"100%"`. So sánh:

```jpql
WHERE p.name LIKE :pattern
```

với:

```jpql
WHERE p.name LIKE :pattern ESCAPE '!'
```

Sử dụng helper `LikePatterns.containsLiteral` và kiểm tra tên nào được trả. Giải thích vì sao `%100%%` không phải mẫu literal đúng.

### Bài 3 — Tìm SKU có gạch dưới

Có hai SKU: `KB_003` và `KB-003`. Viết một điều kiện bằng `=` để chọn đúng SKU thứ nhất, rồi viết một điều kiện `LIKE ... ESCAPE '!'` chọn các SKU có tiền tố literal `KB_`.

Giải thích khác biệt giữa dấu `_` thường và wildcard một ký tự.

### Bài 4 — BETWEEN bao gồm cận

Tạo Product có giá chính xác `250000.00`, `500000.00` và `890000.00`. Dùng:

```jpql
WHERE p.price BETWEEN :min AND :max
```

với `min = 250000` và `max = 890000`. Dự đoán ba sản phẩm nào được chọn. Sau đó đổi cận trên thành điều kiện `p.price < :max` và giải thích khác biệt.

### Bài 5 — Khoảng thời gian của một ngày

Ghi vài Product `createdAt` tại:

- 00:00:00 ngày 15/11 theo business timezone.
- 12:30:00 cùng ngày.
- 23:59:59.900 cùng ngày.
- 00:00:00 ngày 16/11.

Viết điều kiện `>= startInclusive AND < endExclusive` cho ngày 15/11 và xác định bản ghi nào được chọn. So sánh với `BETWEEN` dùng cận trên `23:59:59`.

### Bài 6 — IN enum và empty list

Tạo các Product có trạng thái ACTIVE, DRAFT, ARCHIVED. Viết:

```jpql
WHERE p.status IN :statuses
```

Bind `List.of(ACTIVE, DRAFT)`. Sau đó thử list rỗng và thiết kế hai chính sách: trả kết quả rỗng hoặc bỏ filter trạng thái. Mỗi chính sách phù hợp loại API nào?

### Bài 7 — NOT IN với null

Hình dung tập loại trừ chứa `ARCHIVED` và `NULL`. Phân tích vì sao một Product ACTIVE có thể không được chọn bởi `NOT IN`. Sửa dữ liệu đầu vào để danh sách loại trừ không chứa null, hoặc dùng điều kiện riêng khi cần xử lý status null.

### Bài 8 — JPQL subquery

Viết query lấy tất cả Product thuộc Category đang enabled bằng `IN (SELECT ...)`. Viết lại bằng `JOIN p.category c` và so sánh ý nghĩa. Xem SQL sinh ra từ provider để hiểu provider ánh xạ đường dẫn quan hệ sang FK và JOIN.

### Bài 9 — Ba filter tùy chọn

Xây API nhận `keyword`, `minPrice`, `maxPrice`, `statuses`. Cho các trường hợp:

- Chỉ có keyword.
- Chỉ có minPrice.
- Có cả min/max.
- Chỉ có statuses.
- Không có filter nào.
- List statuses rỗng.

Dùng fragment JPQL cố định hoặc Criteria API để thêm đúng predicate. Không bind null vào `BETWEEN` hoặc IN collection rỗng một cách mặc định.

### Bài 10 — Nối điều kiện AND/OR

So sánh hai câu:

```jpql
WHERE p.status = :active
   OR p.status = :draft
  AND p.price < :maximum
```

và:

```jpql
WHERE (p.status = :active OR p.status = :draft)
  AND p.price < :maximum
```

Tạo một Product ACTIVE có giá cao hơn `maximum` rồi dự đoán truy vấn nào có thể trả nó. Viết lại dạng thứ hai bằng `IN`.

### Bài 11 — Đo hiệu năng

Tạo đủ dữ liệu để quan sát query plan. So sánh:

```jpql
WHERE p.name LIKE :prefixPattern
```

với:

```jpql
WHERE p.name LIKE :containsPattern
```

và:

```jpql
WHERE LOWER(p.name) LIKE :containsPattern
```

Đo execution plan trên database đang dùng. Giải thích vì sao index B-tree không mặc nhiên tối ưu tìm substring có `%` ở đầu.

## 20. Ghi nhớ cốt lõi

**`LIKE`, `BETWEEN` và `IN` là ba cách lọc có ngữ nghĩa khác nhau trong JPQL**: `LIKE` so khớp mẫu chuỗi với `%`/`_`, `BETWEEN` kiểm tra khoảng **bao gồm hai đầu mút**, còn `IN` kiểm tra một giá trị thuộc tập lựa chọn hoặc kết quả truy vấn con.

Khi dùng `LIKE` với từ khóa người dùng, **bind tham số** và dùng **`ESCAPE`** nếu muốn `%`/`_` là ký tự literal. Khi lọc timestamp theo ngày, thường nên dùng **`>= startInclusive AND < endExclusive`** thay vì tự đoán thời điểm cuối ngày. Khi dùng `IN`, truyền đúng kiểu collection, **xử lý danh sách rỗng và null có chủ đích**, đặc biệt thận trọng với `NOT IN`.

Cuối cùng, JPQL vận hành theo **thuộc tính và kiểu entity**, còn kết quả so khớp thực tế còn chịu ảnh hưởng của collation, timezone, transaction và database. Các điều kiện tùy chọn nên được xây rõ ràng, không dùng null như lệnh “bỏ lọc”. Truy vấn đúng ngữ nghĩa, tham số hóa an toàn và có chiến lược index/phân trang phù hợp sẽ giúp API lọc dữ liệu dễ hiểu, đáng tin cậy và dễ mở rộng.
