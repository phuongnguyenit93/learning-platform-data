# Đánh giá tính khả chuyển và tránh phụ thuộc provider ngoài ý muốn khi dùng Native SQL trong JPA

**Native SQL** là một công cụ hữu ích trong Jakarta Persistence (JPA): thay vì chỉ dùng JPQL hoặc Criteria API, ứng dụng có thể gửi câu SQL trực tiếp tới database. Nhờ đó, ta tận dụng được các tính năng như truy vấn phân tích, cú pháp cập nhật hàng loạt, JSON, cơ chế khóa hoặc tối ưu riêng của hệ quản trị.

Đổi lại, **cú pháp và kết quả native query thường có mức phụ thuộc môi trường cao hơn JPQL**. Một câu truy vấn chạy trên Hibernate + PostgreSQL có thể không chạy được trên EclipseLink + PostgreSQL, hoặc chạy được trên Hibernate + MySQL nhưng trả kiểu Java khác. Ngay cả khi query hoạt động với một provider và một database, điều đó chưa chứng minh truy vấn **khả chuyển** (*portable*) hay không chứa **phụ thuộc provider ngoài ý muốn**.

Bài học thuộc chương **Native SQL** trong module *Data Persistence Relational Access ORM JPA*, tập trung vào ba câu hỏi:

1. **Đang phụ thuộc vào thứ gì?** Đặc tả JPA, JPA provider, SQL dialect, JDBC driver, schema hay cấu hình hạ tầng?
2. **Mức phụ thuộc đó có chủ đích không?** Hệ thống có thật sự cần khả năng chạy trên nhiều provider/database, hay chỉ cần tránh những extension bị dùng vô tình?
3. **Làm thế nào để kiểm soát?** Chọn abstraction phù hợp, cô lập SQL đặc thù, chuẩn hóa kết quả, thiết kế kiểm thử và ghi nhận quyết định kỹ thuật.

> **Thông điệp chính:** Không phải mọi phụ thuộc vào database hoặc provider đều xấu. Vấn đề là **không biết mình đang phụ thuộc**, để SQL đặc thù lan khắp business logic rồi bất ngờ phát hiện rằng việc nâng phiên bản, đổi driver, chuyển môi trường test hoặc thay database gây lỗi.

---

## 1. Phân biệt năm lớp tính khả chuyển

Trong JPA, “portable” không phải một thuộc tính có/không đơn giản. Cần xem theo nhiều lớp.

| Lớp | Câu hỏi cần trả lời | Ví dụ phụ thuộc |
|---|---|---|
| **API JPA** | Code có dùng API chuẩn `jakarta.persistence` không? | `EntityManager.createNativeQuery` so với `Session#createNativeQuery` của Hibernate |
| **JPA provider** | Hành vi có giống giữa Hibernate, EclipseLink hoặc provider khác không? | Cách suy ra scalar types, alias, entity hydration, auto-flush |
| **Database/dialect** | SQL có chạy trên PostgreSQL, MySQL, Oracle, SQL Server...? | `ILIKE`, `ON CONFLICT`, `LIMIT`, JSON operators |
| **JDBC driver và kiểu dữ liệu** | ResultSet và parameter binding có được diễn giải giống nhau? | `COUNT(*)` trả một subtype `Number` khác, UUID/JSON/Boolean |
| **Schema, cấu hình và vận hành** | Query có phụ thuộc cấu trúc và thiết lập cụ thể? | Quoted identifiers, schema search path, collation, timezone, isolation, index |

Một ví dụ:

```java
Query query = em.createNativeQuery(
    """
    SELECT p.id, p.sku
    FROM catalog_product p
    WHERE p.name ILIKE ?1
    """);
```

Ở đây:

- `EntityManager.createNativeQuery` là **API chuẩn JPA**.
- `ILIKE` là cú pháp thường gắn với **PostgreSQL**, không phải một toán tử SQL có thể giả định trên mọi database.
- Kết quả scalar `id`/`sku` phụ thuộc kiểu JDBC và cấu hình ResultSet.
- Bảng `catalog_product` và cột `name` là phụ thuộc schema.
- Nếu ứng dụng ép kết quả về một provider-specific tuple transformer, nó còn phụ thuộc provider.

**Đạt tính khả chuyển API không đồng nghĩa đạt tính khả chuyển SQL.**

### 1.1. “Native” không có nghĩa mọi thứ bỏ qua JPA

Dù chuỗi SQL do ứng dụng viết, JPA provider vẫn có thể tham gia:

- Quản lý transaction và persistence context.
- Bind parameters.
- Chuyển kết quả sang entity hoặc scalar.
- Phân trang qua `setFirstResult`/`setMaxResults`.
- Xử lý flush mode trước query.
- Áp dụng result mappings.
- Xử lý exception.
- Đưa hints xuống JDBC hoặc database.

Vì thế vẫn cần hiểu **JPA contract** ngay cả khi SQL hoàn toàn do ứng dụng kiểm soát.

### 1.2. Khả chuyển nên gắn với mục tiêu triển khai

Hai dự án có thể chọn khác nhau:

**Dự án A:** Chỉ chạy PostgreSQL với Hibernate trong nhiều năm. SQL `ON CONFLICT` có thể là quyết định hợp lý, miễn được cô lập, có test và có tài liệu.

**Dự án B:** Sản phẩm đóng gói phải chạy PostgreSQL, MySQL và Oracle. SQL `ON CONFLICT` trong tầng service chung là rủi ro cần loại bỏ hoặc phải có nhánh triển khai theo dialect.

Do đó, không nên tuyên bố mọi query native phải được viết theo “SQL chung cho mọi database”. Hãy xác định **ma trận môi trường được hỗ trợ**, rồi đánh giá mức portable theo ma trận đó.

## 2. JPA chuẩn, phần mở rộng provider và SQL dialect: ba nhóm phải tách riêng

Một codebase có thể trộn cả ba nhóm:

```java
// JPA chuẩn:
Query query = em.createNativeQuery(sql);

// Provider extension:
org.hibernate.Session session =
    em.unwrap(org.hibernate.Session.class);

// Database-specific SQL:
String sql = """
    INSERT INTO catalog_product (id, sku)
    VALUES (?1, ?2)
    ON CONFLICT (sku)
    DO NOTHING
    """;
```

Các thành phần này tạo ba loại phụ thuộc khác nhau:

1. **`jakarta.persistence.Query`:** API JPA chuẩn.
2. **`org.hibernate.Session`:** API Hibernate, không phải hợp đồng JPA chung.
3. **`ON CONFLICT`:** Cú pháp PostgreSQL trong hình thức minh họa, không phải giải pháp upsert SQL chuẩn được mọi database hỗ trợ giống nhau.

Nếu tổ chức chỉ cho phép thư viện JPA chuẩn ở module nghiệp vụ, code có `org.hibernate.Session` trong service là dấu hiệu cần xem lại. Nếu tổ chức có chiến lược sử dụng PostgreSQL lâu dài, `ON CONFLICT` có thể được chấp nhận trong module hạ tầng tương ứng.

**Tách nguồn phụ thuộc giúp ra quyết định hợp lý:** không nên đổ lỗi cho provider khi thực chất query dùng cú pháp DB đặc thù, cũng không nên thay đổi SQL khi lỗi đến từ cách provider map ResultSet.

## 3. Bắt đầu từ giải pháp portable hơn khi yêu cầu cho phép

Trong JPA, một số tác vụ diễn đạt tốt bằng JPQL:

```java
List<Product> products = em.createQuery(
    """
    select p
    from Product p
    where p.status = :status
    order by p.createdAt desc, p.id desc
    """,
    Product.class
)
.setParameter("status", ProductStatus.ACTIVE)
.setMaxResults(100)
.getResultList();
```

Một câu SQL tương đương về ý định:

```sql
SELECT
    p.id,
    p.sku,
    p.display_name,
    p.unit_price,
    p.product_status,
    p.version,
    p.created_at
FROM catalog_product p
WHERE p.product_status = ?
ORDER BY p.created_at DESC, p.id DESC;
```

Nếu query chỉ cần lọc và sắp xếp entity thông thường, **JPQL/Criteria API thường giảm phụ thuộc tên bảng/cột và dialect**. Nó còn giúp provider chọn SQL tương thích database được cấu hình.

Lựa chọn gợi ý:

| Yêu cầu | Công cụ nên cân nhắc trước |
|---|---|
| Đọc entity và quan hệ theo mapping | JPQL, Criteria API, EntityGraph |
| Query động nhiều điều kiện tùy chọn | Criteria API hoặc query builder dựa trên JPA |
| Tổng hợp `COUNT`/`SUM`/`AVG` thông thường | JPQL aggregate |
| DTO projection với vài thuộc tính mapped | JPQL constructor projection |
| Batch DML theo entity với logic đơn giản | JPQL bulk UPDATE/DELETE nếu semantics phù hợp |
| Window functions, recursive CTE hoặc JSON chuyên biệt | Native SQL khi tính năng được hỗ trợ |
| Upsert atomic theo constraint DB | SQL dialect-specific hoặc API DB tương ứng |
| Bulk import cực lớn | JDBC, batch API hoặc native SQL sau khi đo nhu cầu |
| Cần kiểm soát locking/phân vùng/index hint chuyên sâu | Native SQL có thiết kế và test theo database |

**Không nhất thiết thay mọi native query thành JPQL.** Nếu logic cần một tính năng SQL mạnh, sử dụng native có chủ đích có thể rõ ràng, hiệu quả và ít phức tạp hơn cách vòng vèo qua entity graph.

## 4. Ví dụ xuyên suốt: Product và Order

Giả sử có bảng:

```sql
CREATE TABLE catalog_product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL,
    unit_price DECIMAL(18, 2) NOT NULL,
    product_status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE sales_order (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

DDL này cố ý đơn giản hóa để tập trung vào portability. Các hệ quản trị có thể có khác biệt về `TIMESTAMP`, khóa sinh tự động, kiểu Boolean, index, constraint và cú pháp migration.

Entity Product:

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "catalog_product")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(name = "display_name", nullable = false)
    private String name;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(name = "product_status", nullable = false)
    private ProductStatus status;

    @Version
    private Long version;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Product() {
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

    public BigDecimal getPrice() {
        return price;
    }
}
```

Enum:

```java
public enum ProductStatus {
    ACTIVE,
    INACTIVE,
    DISCONTINUED
}
```

Ở phần lớn ví dụ, `Product` được đọc từ DB. Nếu dự án cần tạo Product, hãy bổ sung constructor/domain methods, ID generator và transaction rules thích hợp.

## 5. Kiểm tra tính khả chuyển của chính chuỗi SQL

So sánh hai câu:

```sql
-- Câu A: cú pháp SQL tương đối phổ biến.
SELECT p.id, p.sku
FROM catalog_product p
WHERE p.product_status = ?
ORDER BY p.id;
```

```sql
-- Câu B: sử dụng toán tử đặc thù PostgreSQL.
SELECT p.id, p.sku
FROM catalog_product p
WHERE p.display_name ILIKE ?;
```

Câu A có **mức phụ thuộc thấp hơn về cú pháp**. Câu B dùng `ILIKE`, nên cần đánh dấu “phụ thuộc PostgreSQL” hoặc có triển khai thay thế.

Một phương án dùng hàm phổ biến hơn:

```sql
SELECT p.id, p.sku
FROM catalog_product p
WHERE LOWER(p.display_name) LIKE LOWER(?);
```

Nhưng **ngay cả phương án LOWER/LIKE không đảm bảo cùng kết quả trên mọi DB**:

- Collation và quy tắc so sánh chữ hoa/thường có thể khác.
- Unicode normalization và dấu tiếng Việt ảnh hưởng kết quả.
- Escaping `%` và `_` phải đúng.
- Khả năng dùng index phụ thuộc biểu thức và database.
- Kiểu parameter/driver có thể ảnh hưởng kế hoạch thực thi.

Do đó phân biệt **portable syntax** và **portable semantics**. Cú pháp được nhiều DB hiểu chưa chắc kết quả hoặc hiệu năng giống nhau.

## 6. Bảng một số tính năng SQL dễ tạo vendor lock-in

| Tính năng/cú pháp | Môi trường thường gặp | Câu hỏi khi muốn chuyển DB |
|---|---|---|
| `ILIKE` | PostgreSQL | Có giải pháp case-insensitive tương đương với collation dự án? |
| `ON CONFLICT ... DO UPDATE` | PostgreSQL và một số hệ có cú pháp tương tự | Database đích hỗ trợ upsert qua cú pháp/giao thức nào? |
| `ON DUPLICATE KEY UPDATE` | MySQL/MariaDB | Có phương án upsert tương đương, cùng concurrency semantics? |
| `MERGE` | Một số hệ quản trị | Cú pháp và hành vi khi nhiều rows match có giống không? |
| `RETURNING` | PostgreSQL và các DB có hỗ trợ ở mức khác nhau | Provider/JDBC có thể đọc kết quả DML như thế nào? |
| `LIMIT ... OFFSET` | Phổ biến nhưng không phải mọi dialect như nhau | Dùng JPA pagination hoặc variant theo DB? |
| `TOP` | SQL Server và một số dialect | Query có phiên bản dùng `FETCH FIRST`/JPA pagination? |
| `FOR UPDATE SKIP LOCKED` | Nhiều DB hiện đại ở mức hỗ trợ khác nhau | Locking, timeout, isolation và starvation ra sao? |
| `jsonb_path_query`, `->>` | PostgreSQL JSON/JSONB | DB đích có JSON type/function/operator tương đương? |
| `JSON_EXTRACT` | Các hệ hỗ trợ JSON khác nhau | Path syntax và kiểu scalar trả về có giống không? |
| `DATE_TRUNC` | PostgreSQL và vài DB khác | Cách nhóm ngày/giờ có đúng timezone yêu cầu? |
| `TRUNC` hoặc `TO_CHAR` trên timestamp | Oracle và các hệ có biến thể | Function và format model có tương đồng? |
| `NVL`/`IFNULL` | Oracle/MySQL và môi trường liên quan | Có thể dùng `COALESCE` theo mục tiêu không? |
| Index hints như `USE INDEX` | Database-specific | Có thể bỏ hint và để optimizer chọn hoặc tạo strategy riêng? |
| Recursive CTE `WITH RECURSIVE` | Nhiều DB, nhưng cú pháp/giới hạn khác | Có cần thêm keyword, kiểu dữ liệu hay syntax theo DB? |
| Window function `ROW_NUMBER() OVER (...)` | Nhiều DB hiện đại | Hỗ trợ frame/order semantics và null ordering có tương đương? |

Bảng này **không phải ma trận hỗ trợ phiên bản chính xác**. Tính năng có thể được bổ sung, thay đổi hoặc có syntax khác giữa các phiên bản. Khi cần tuyên bố “hỗ trợ DB X phiên bản Y”, phải kiểm chứng trong tài liệu/version và integration test tương ứng.

### 6.1. “SQL chuẩn” cũng chưa bảo đảm chạy ở mọi database

Một đặc tính có thể nằm trong chuẩn SQL nhưng database đích chưa triển khai, chỉ triển khai một phần hoặc yêu cầu cấu hình riêng. Vì vậy định nghĩa portable theo **tập database/version được dự án cam kết**, không chỉ nhãn “ANSI SQL”.

### 6.2. Nguy cơ đặc thù của quoted identifiers

Ví dụ:

```sql
SELECT "DisplayName" FROM "Product";
```

Tên identifier có dấu nháy và phân biệt chữ hoa/thường có thể được xử lý khác nhau giữa DB, còn cơ chế quoted identifiers cũng không hoàn toàn thống nhất.

Với SQL native, không chỉ query string mà **DDL và naming convention** ảnh hưởng portability. Ưu tiên schema đặt tên nhất quán, tránh từ khóa SQL dành riêng và chỉ quote khi thực sự cần.

## 7. API chuẩn JPA không đảm bảo SQL logic portable

Đoạn code:

```java
List<?> rows = em.createNativeQuery(
    """
    SELECT id, sku
    FROM catalog_product
    WHERE display_name ILIKE ?1
    """
)
.setParameter(1, "%java%")
.getResultList();
```

dùng `EntityManager` và `Query` chuẩn. Tuy nhiên chính chuỗi SQL vẫn phụ thuộc database.

Câu hỏi đánh giá cần hỏi cả hai:

- **API này có chạy với JPA provider khác?**
- **Chuỗi SQL này có chạy với DB khác?**

Không kết luận một đoạn code portable chỉ vì mọi Java import đều thuộc `jakarta.persistence`.

### 7.1. Tách lỗi SQL khỏi lỗi provider

Một cách điều tra:

```text
Query thất bại
     |
     v
SQL chạy trực tiếp trên database đích không?
   /                                 \
 Không                               Có
  |                                   |
  v                                   v
Kiểm tra syntax,                Kiểm tra bind params,
schema, type, dialect           result mapping, provider
                                      |
                                      v
                              Kiểm tra driver/JDBC types,
                              flush/context/transaction
```

Không thay toàn bộ Hibernate sang provider khác để “sửa lỗi” khi thực chất SQL có toán tử PostgreSQL nhưng đang chạy trên MySQL.

## 8. Native query parameters: phân biệt chuẩn JPA và extension

Với JPQL, named parameters được hỗ trợ rõ ràng:

```java
em.createQuery(
    "select p from Product p where p.sku = :sku",
    Product.class
).setParameter("sku", sku);
```

Với **native SQL**, mức portable của cách tham số hóa khác. Theo hướng thận trọng, hãy dùng **positional binding** của JPA cho SQL native khi cần hỗ trợ nhiều provider:

```java
Query query = em.createNativeQuery(
    """
    SELECT id, sku
    FROM catalog_product
    WHERE sku = ?1
      AND product_status = ?2
    """);

query.setParameter(1, requestedSku);
query.setParameter(2, "ACTIVE");
```

Cú pháp placeholder mà provider chuyển đến JDBC cần được kiểm chứng với bộ JPA/provider đang dùng; một số môi trường native SQL sử dụng dấu hỏi theo JDBC, trong khi một số provider hỗ trợ biến thể số thứ tự.

### 8.1. Named parameters trong native SQL

Hibernate và các provider có thể hỗ trợ:

```java
em.createNativeQuery(
    """
    SELECT id, sku FROM catalog_product
    WHERE sku = :sku
    """
)
.setParameter("sku", requestedSku);
```

Nhưng **không xem hỗ trợ named parameters trong native SQL là cam kết portable giữa mọi JPA provider**. Dùng được trong một provider không chứng minh đặc tả bắt mọi provider phải hỗ trợ giống vậy.

Nếu tổ chức chọn named parameters vì tính dễ đọc và chỉ hỗ trợ một provider, hãy ghi rõ đây là **provider extension có chủ đích** và đặt nó trong repository adapter tương ứng.

### 8.2. Collection parameter trong IN

Một ví dụ được dùng nhiều:

```java
String sql = """
    SELECT id, sku
    FROM catalog_product
    WHERE id IN (:ids)
    """;

query.setParameter("ids", List.of(1L, 2L, 3L));
```

Không nên giả định **native SQL collection expansion** sẽ được mọi JPA provider xử lý như JPQL `IN :ids`.

Hướng kiểm soát:

1. Nếu có thể, dùng JPQL collection parameter.
2. Nếu native SQL bắt buộc, dùng provider-specific list binding **có tài liệu** trong adapter.
3. Hoặc dựng đúng số lượng positional placeholders từ kích thước danh sách đã validate, bind từng scalar.
4. Khi danh sách rỗng, xử lý trước, không sinh `IN ()`.
5. Cân nhắc giới hạn số placeholders và hiệu năng với danh sách rất lớn.

Ví dụ xây placeholders an toàn theo dữ liệu đã kiểm soát:

```java
public List<Long> findIds(EntityManager em, List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }

    String placeholders = java.util.stream.IntStream
        .rangeClosed(1, ids.size())
        .mapToObj(i -> "?" + i)
        .collect(java.util.stream.Collectors.joining(", "));

    String sql = """
        SELECT id FROM catalog_product
        WHERE id IN (
        """ + placeholders + ")";

    Query query = em.createNativeQuery(sql);

    for (int i = 0; i < ids.size(); i++) {
        query.setParameter(i + 1, ids.get(i));
    }

    List<?> values = query.getResultList();
    return values.stream()
        .map(value -> ((Number) value).longValue())
        .toList();
}
```

Ở đây số lượng dấu hỏi do code tạo từ **số phần tử**, không phải nối ID trực tiếp vào chuỗi SQL. Kết quả scalar `Number` vẫn cần kiểm tra theo driver/provider. Với môi trường không hỗ trợ cú pháp `?1` như kỳ vọng, adapter cần dùng placeholder/binding format được provider bảo đảm.

### 8.3. Không bind tên bảng, cột hoặc ORDER BY field

```sql
SELECT * FROM ?1 WHERE ?2 = ?3
```

Không thể dùng value parameter để thay identifier SQL theo cách JDBC thông thường.

Để hỗ trợ user chọn sort field, dùng whitelist:

```java
String sortColumn = switch (sortKey) {
    case "name" -> "p.display_name";
    case "price" -> "p.unit_price";
    case "created" -> "p.created_at";
    default -> throw new IllegalArgumentException(
        "Unsupported sort key"
    );
};

String sql = """
    SELECT p.id, p.sku
    FROM catalog_product p
    ORDER BY
    """ + sortColumn;
```

Đây là **cấu trúc SQL động có kiểm soát**, không phải SQL injection vì fragment được lấy từ danh sách literal tin cậy. Vẫn phải bind giá trị điều kiện bằng tham số.

## 9. Mapping scalar: đừng phụ thuộc kiểu Number ngầm định

Native query:

```java
Object raw = em.createNativeQuery(
    "SELECT COUNT(*) FROM catalog_product"
).getSingleResult();
```

Một số người viết:

```java
Long count = (Long) raw;
```

Đây là phụ thuộc không cần thiết vào kiểu cụ thể do provider/driver trả. Cùng `COUNT(*)` có thể được ánh xạ thành những subtype `Number` khác nhau giữa DB/JDBC/provider hoặc cấu hình.

Cách chịu được nhiều numeric types hơn:

```java
Number countNumber = (Number) raw;
long count = countNumber.longValue();
```

Tuy nhiên, cách này cũng cần hiểu giới hạn:

- Nếu số lượng vượt phạm vi `long`, `longValue()` có thể làm mất thông tin.
- Nếu provider trả kiểu không phải `Number`, vẫn lỗi.
- Nếu giá trị aggregate có thể NULL (`SUM` trên tập rỗng), phải xử lý `null`.
- Nếu yêu cầu kiểu cố định, nên dùng result mapping chuẩn hoặc DTO mapping tường minh.

### 9.1. @ColumnResult giúp diễn tả kiểu mong muốn

```java
@SqlResultSetMapping(
    name = "ProductCountMapping",
    columns = @ColumnResult(
        name = "product_count",
        type = Long.class
    )
)
```

SQL:

```sql
SELECT COUNT(*) AS product_count
FROM catalog_product;
```

`@ColumnResult(type=Long.class)` chỉ định kiểu chuyển đổi theo contract JPA/result mapping. Nhưng vẫn phải kiểm chứng trên provider/driver và không dùng nó để che những kết quả không thể biểu diễn chính xác trong kiểu mong muốn.

### 9.2. Boolean, UUID, JSON và thời gian khó portable hơn số nguyên

Các kiểu phổ biến nhưng có khác biệt:

| Dữ liệu nghiệp vụ | Điểm dễ khác nhau |
|---|---|
| Boolean | Cột `BOOLEAN`, `BIT`, `TINYINT`, số 0/1, ký tự Y/N |
| UUID | `UUID` native, `CHAR(36)`, `BINARY(16)` |
| JSON | `JSON`, `JSONB`, text, object JDBC đặc thù |
| Timestamp | Có hoặc không timezone, độ chính xác fractional seconds |
| Enum | DB enum native, VARCHAR, ordinal, converter |
| Decimal | Precision/scale, kiểu `BigDecimal`, overflow |
| Large object | BLOB/CLOB/byte[], streaming, transaction lifetime |

Nếu query trả **entity đầy đủ**, JPA mapping được áp theo provider. Nếu query trả **scalar**, bạn thường phải tự nhận và chuẩn hóa kiểu hoặc dùng `@ColumnResult`/`@ConstructorResult` rõ ràng.

Một lớp DTO ngay sau repository nên đổi kết quả kỹ thuật thành **Java domain types ổn định**, để business service không cần biết JDBC trả `BigInteger` hay `Long`.

## 10. Mapping về entity: một nguồn phụ thuộc provider dễ bị bỏ sót

Native SQL trả entity:

```java
String sql = """
    SELECT
        p.id,
        p.sku,
        p.display_name,
        p.unit_price,
        p.product_status,
        p.version,
        p.created_at
    FROM catalog_product p
    WHERE p.id = ?1
    """;

Product p = (Product) em
    .createNativeQuery(sql, Product.class)
    .setParameter(1, productId)
    .getSingleResult();
```

Ý tưởng `createNativeQuery(sql, Product.class)` là API JPA chuẩn. Nhưng **độ đầy đủ của ResultSet** vẫn là yêu cầu quan trọng:

- Có primary key `id`.
- Có các cột persistent cần hydrate.
- Có `@Version` nếu entity dùng optimistic locking.
- Có cột FK nếu mapping entity có association yêu cầu.
- Có discriminator/secondary-table/subtype columns khi inheritance/mapping cần.
- Tên cột hoặc alias phù hợp metadata/result mapping.

### 10.1. Đừng dùng partial SELECT rồi gắn Entity.class

```java
em.createNativeQuery(
    "SELECT id, sku FROM catalog_product",
    Product.class
);
```

Nếu Product mapping có `display_name`, `unit_price`, `status`, `version`, `created_at`, query trên **không đủ dữ liệu cho một entity đầy đủ**. Một số provider có extension hỗ trợ partial loading, nhưng đừng xem đó là hợp đồng portable.

Nếu chỉ cần id/sku, dùng DTO/scalar projection.

### 10.2. JOIN nhiều bảng: alias trùng làm mapping mơ hồ

```sql
SELECT p.*, o.*
FROM catalog_product p
JOIN order_line o ON o.product_id = p.id;
```

Cả hai bảng có thể có `id`, `created_at` hoặc cột khác trùng label. Một provider có thể chọn nhầm hoặc báo lỗi mapping.

Nếu chỉ muốn Product, chọn `p.*` khi mapping đơn giản phù hợp; tốt hơn là chọn **đủ Product columns rõ ràng**. Nếu muốn hai entity, dùng alias phân biệt và result mapping tường minh.

### 10.3. Native resultClass vẫn là managed entity

Trong persistence context đang hoạt động, một Product được hydrate từ native query theo entity mapping hợp lệ là một **managed entity**. Nó không tự là POJO detached chỉ vì SQL do ứng dụng viết.

Do đó:

- `em.contains(p)` thường là true khi entity vẫn được context quản lý.
- `@Version`/dirty checking có ý nghĩa khi thực hiện thay đổi managed state trong transaction.
- First-level cache có thể trả cùng instance nếu entity cùng ID đã được load.
- Native SELECT **không tự là refresh** của entity đã managed.

Những hành vi này thuộc JPA lifecycle, không nên bị hiểu sai thành “native SQL không liên quan JPA”.

## 11. @SqlResultSetMapping giúp giảm phụ thuộc vào suy đoán alias

Giả sử query muốn đổi alias để tránh trùng cột:

```sql
SELECT
    p.id AS product_id,
    p.sku AS product_sku,
    p.display_name AS product_name,
    p.unit_price AS product_price,
    p.product_status AS product_state,
    p.version AS product_version,
    p.created_at AS product_created
FROM catalog_product p;
```

Một result mapping chuẩn JPA:

```java
@SqlResultSetMapping(
    name = "ProductResult",
    entities = @EntityResult(
        entityClass = Product.class,
        fields = {
            @FieldResult(name = "id", column = "product_id"),
            @FieldResult(name = "sku", column = "product_sku"),
            @FieldResult(name = "name", column = "product_name"),
            @FieldResult(name = "price", column = "product_price"),
            @FieldResult(name = "status", column = "product_state"),
            @FieldResult(name = "version", column = "product_version"),
            @FieldResult(name = "createdAt", column = "product_created")
        }
    )
)
```

Đặt annotation trên entity phù hợp trong persistence unit, rồi:

```java
List<?> values = em.createNativeQuery(
    sql,
    "ProductResult"
).getResultList();
```

Điểm cần nhớ:

- `FieldResult.name` là **tên persistent attribute Java**.
- `FieldResult.column` là **cột/alias của ResultSet**.
- `EntityResult.entityClass` xác định entity cần hydrate.
- Không dùng `name = "display_name"` nếu field Java tên `name`.
- Result mapping không sửa SQL, không cung cấp cột thiếu và không tự làm câu SQL portable.
- Các mapping phức tạp (composite FK, inheritance, secondary table) có thể có yêu cầu bổ sung theo provider.

### 11.1. DTO sẽ portable hơn trong một số truy vấn báo cáo

Nếu chỉ chọn ba cột:

```sql
SELECT
    p.id AS product_id,
    p.sku AS product_sku,
    p.unit_price AS product_price
FROM catalog_product p;
```

Thay vì ép thành Product managed, định nghĩa:

```java
public record ProductBrief(
    Long id,
    String sku,
    BigDecimal price
) { }
```

Dùng `@ConstructorResult`:

```java
@SqlResultSetMapping(
    name = "ProductBriefResult",
    classes = @ConstructorResult(
        targetClass = ProductBrief.class,
        columns = {
            @ColumnResult(name = "product_id", type = Long.class),
            @ColumnResult(name = "product_sku", type = String.class),
            @ColumnResult(
                name = "product_price",
                type = BigDecimal.class
            )
        }
    )
)
```

`ProductBrief` không phải entity, không tham gia dirty checking. Kết quả có contract rõ, giảm nguy cơ phụ thuộc vào partial entity behavior của provider.

### 11.2. DTO mapping vẫn cần kiểm tra contract

`@ConstructorResult` phụ thuộc thứ tự và kiểu constructor parameters. Nếu database trả giá trị DECIMAL không tương thích kiểu mong đợi, hoặc alias không khớp `@ColumnResult`, result mapping vẫn có thể lỗi.

**Chuẩn hóa kiểu không có nghĩa loại bỏ hoàn toàn rủi ro; nó chỉ tập trung rủi ro tại một lớp mapping được kiểm soát.**

## 12. Case sensitivity và alias normalization: lỗi khó nhận biết

Cùng một câu:

```sql
SELECT p.id AS ProductId
FROM catalog_product p;
```

driver/database có thể báo metadata label theo cách normalize chữ hoa/chữ thường khác nhau, đặc biệt khi dùng quoted identifiers:

```sql
SELECT p.id AS "ProductId"
FROM catalog_product p;
```

Nếu `@ColumnResult(name = "ProductId")` hoặc `@FieldResult(column = "ProductId")` chỉ chạy trên một DB, cần kiểm chứng **ResultSet column labels thực tế** trên các database/provider được hỗ trợ.

Phương án giảm rủi ro:

1. Áp naming convention cho aliases: `product_id`, `order_id`, `customer_name`.
2. Hạn chế quoted mixed-case aliases nếu không cần.
3. Luôn chỉ định alias rõ khi JOIN nhiều bảng.
4. Dùng mapping tường minh khi aliases khác mapped column names.
5. Tạo integration test cho các query có aliases phức tạp.
6. Không chỉ kiểm tra SQL chạy, còn kiểm tra các field Java nhận đúng dữ liệu.

## 13. Pagination: API JPA có thể portable, SQL và ngữ nghĩa chưa chắc

Thay vì tự viết:

```sql
SELECT ... FROM catalog_product
ORDER BY created_at DESC
LIMIT 20 OFFSET 40;
```

JPA cho phép:

```java
List<?> rows = em.createNativeQuery(
    """
    SELECT
        id, sku, display_name, unit_price,
        product_status, version, created_at
    FROM catalog_product
    ORDER BY created_at DESC, id DESC
    """,
    Product.class
)
.setFirstResult(40)
.setMaxResults(20)
.getResultList();
```

`setFirstResult` và `setMaxResults` là API chuẩn, tạo cơ hội để provider áp dụng cách phân trang tương thích dialect. Nhưng vẫn phải xét:

- Provider có thể gặp giới hạn khi sửa native SQL phức tạp (CTE, UNION, function, stored procedure).
- Database khác có thể dùng execution plan khác.
- Offset lớn có thể chậm dù cú pháp hợp lệ.
- Không có ORDER BY ổn định thì các trang có thể lặp/mất rows.
- Query JOIN collection có thể trả nhiều SQL rows cho một entity identity, khiến “20 rows” khác “20 entities”.
- Nếu native SQL đã có `LIMIT/OFFSET` và JPA lại đặt pagination, có thể tạo tương tác không mong muốn.

**Tính khả chuyển của API phân trang không bảo đảm tính chính xác nghiệp vụ của pagination.**

### 13.1. Keyset pagination cũng phụ thuộc semantics

Với sort `created_at desc, id desc`, có thể viết điều kiện:

```sql
SELECT
    id, sku, display_name, unit_price,
    product_status, version, created_at
FROM catalog_product
WHERE
    created_at < ?1
    OR (created_at = ?1 AND id < ?2)
ORDER BY created_at DESC, id DESC;
```

Đây là một mô hình keyset pagination. Dù dùng toán tử SQL thông dụng, vẫn cần hiểu:

- Các cột sort có nullable không?
- Kiểu timestamp có precision/timezone thống nhất?
- So sánh timestamp/ID có thứ tự ổn định không?
- Concurrent inserts/deletes ảnh hưởng tính liên tục trang như thế nào?
- Database có index phù hợp hay không?

Nội dung query và kết quả nghiệp vụ vẫn cần test, ngay cả khi mọi provider chấp nhận API.

## 14. Function, JSON và kiểu tùy biến: phụ thuộc thường xuất hiện muộn

Một hệ thống bắt đầu với query đơn giản rồi thêm điều kiện JSON:

```sql
-- Ví dụ chuyên biệt cho PostgreSQL JSONB:
SELECT id, sku
FROM catalog_product
WHERE attributes_json ->> 'color' = ?;
```

Phụ thuộc mới xuất hiện:

- Kiểu cột `JSONB`.
- Toán tử `->>`.
- Cách biểu diễn JSON null/missing property.
- Index JSON.
- JDBC result type của field JSON.
- Cách bind tham số JSON, có thể cần database-specific type.

Không nên đặt JSON operator tùy ý trong service chung và kỳ vọng Hibernate/JPA tự chuyển nó sang cú pháp JSON của database khác.

### 14.1. Ba hướng khi cần dùng JSON

**Hướng A — Chấp nhận ràng buộc database:** Nếu PostgreSQL là lựa chọn chính thức, viết adapter PostgreSQL, document và test tính năng JSONB.

**Hướng B — Dùng field quan hệ:** Nếu dữ liệu như `color` là điều kiện lọc quan trọng và phải portable, cân nhắc một cột quan hệ hoặc bảng thuộc tính được mapping rõ.

**Hướng C — Dùng capability abstraction:** Định nghĩa giao diện truy vấn metadata, mỗi database adapter thực hiện theo cú pháp và index riêng.

Không có hướng nào luôn đúng; đánh đổi gồm chi phí schema, latency, tính linh hoạt và yêu cầu di chuyển.

### 14.2. Boolean và UUID

Một ứng dụng dùng:

```sql
WHERE is_active = TRUE
```

có thể gặp khác biệt nếu DB biểu diễn Boolean bằng `BIT`, `NUMBER(1)` hoặc kiểu riêng. Tương tự, UUID có thể nằm ở `UUID`, `VARCHAR(36)`, `BINARY(16)`.

Đừng suy ra vì Java entity dùng `boolean` hoặc `UUID` nên native SQL type/parameter/ResultSet portable tuyệt đối. Provider mapping và JDBC driver quyết định các bước chuyển đổi tương ứng.

## 15. Thời gian, timezone và precision: SQL chạy được vẫn có thể sai dữ liệu

Một báo cáo:

```sql
SELECT COUNT(*)
FROM sales_order
WHERE created_at >= ?
  AND created_at < ?;
```

Cú pháp cơ bản có thể chạy trên nhiều DB, nhưng kết quả vẫn có thể khác vì:

- Cột `TIMESTAMP` có hoặc không kèm timezone.
- Driver chuyển `Instant`/`LocalDateTime` khác nhau.
- Độ chính xác mili/micro/nanosecond khác nhau.
- Session timezone và database timezone khác nhau.
- Ngày nghiệp vụ được xác định theo timezone khách hàng hay theo UTC.
- Database collation/cast từ String sang timestamp nếu bind sai kiểu.

### 15.1. Cách giảm phụ thuộc

- Định nghĩa loại thời gian ở domain (`Instant` cho một mốc thời gian tuyệt đối, `LocalDate` cho ngày nghiệp vụ).
- Dùng khoảng nửa mở `[startInclusive, endExclusive)` khi lọc kỳ.
- Chuẩn hóa chính sách lưu và đọc timezone.
- Bind đúng Java/JDBC temporal type, không nối string ngày vào SQL.
- Kiểm thử dữ liệu sát ranh giới ngày, DST và precision theo DB đích.
- Tránh function như `DATE(created_at)` hoặc `TRUNC(created_at)` trong query chung nếu làm mất khả năng tận dụng index hoặc phụ thuộc dialect.

Ví dụ Java chuẩn hóa ranh giới theo múi giờ kinh doanh:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 15);

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();
```

Đối với native query, cách bind Instant sang SQL timestamp vẫn phải được xác nhận với driver/provider và schema. Việc tạo ranh giới đúng theo Java time chưa tự giải quyết mọi khác biệt mapping JDBC.

## 16. Native query và transaction: đừng phụ thuộc auto-flush ngầm định

Một transaction JPA có thể đang quản lý Product được sửa:

```java
Product product = em.find(Product.class, productId);

// Giả sử Product có domain method cập nhật giá.
product.changePrice(new BigDecimal("450000"));

Number count = (Number) em.createNativeQuery(
    """
    SELECT COUNT(*)
    FROM catalog_product
    WHERE unit_price >= ?1
    """
)
.setParameter(1, new BigDecimal("400000"))
.getSingleResult();
```

Câu hỏi: Query `COUNT` có thấy giá vừa đổi không?

Câu trả lời phụ thuộc:

- Transaction đang hoạt động và EntityManager đã join transaction chưa.
- Flush mode (`AUTO`, `COMMIT`).
- Provider nhận biết SQL native liên quan bảng nào.
- Thời điểm provider flush pending state.
- Database isolation.
- Cách ứng dụng thực hiện native query.

Với `AUTO`, JPA có các yêu cầu về khả năng query phản ánh thay đổi theo hợp đồng, nhưng **cách provider đồng bộ dữ liệu trước native query không nên bị ngầm coi là giống nhau trong mọi implementation**, đặc biệt khi kết hợp API/hints/provider-specific query synchronization.

### 16.1. Khi cần đồng bộ rõ ràng

Trong transaction ghi phù hợp:

```java
product.changePrice(new BigDecimal("450000"));
em.flush();

Number count = (Number) em.createNativeQuery(
    """
    SELECT COUNT(*)
    FROM catalog_product
    WHERE unit_price >= ?1
    """
)
.setParameter(1, new BigDecimal("400000"))
.getSingleResult();
```

`em.flush()` là cách yêu cầu đồng bộ pending persistence context changes tại mốc có chủ đích, tránh đặt tất cả kỳ vọng vào cơ chế auto-flush ngầm định.

Tuy nhiên:

- **Flush không phải commit**.
- Query trong transaction khác không mặc nhiên thấy thay đổi chưa commit.
- Flush có thể phát hiện lỗi database sớm.
- Khi entity đã managed, native entity query có thể trả managed instance cũ thay vì refresh.
- Nếu không có transaction phù hợp, flush có thể ném exception.

### 16.2. Đừng dựa vào extension “query knows affected tables”

Một số provider có API khai báo các query spaces/tables ảnh hưởng auto-flush hoặc cache synchronization. Nếu code làm:

```java
org.hibernate.query.NativeQuery<?> query = em
    .createNativeQuery(sql)
    .unwrap(org.hibernate.query.NativeQuery.class);
```

rồi gọi API Hibernate-specific về synchronization, đó là phụ thuộc Hibernate, không phải JPA standard.

Nếu chọn tính năng này, cô lập trong **Hibernate adapter** và ghi rõ phiên bản/hợp đồng. Không để service nghiệp vụ phụ thuộc vào Hibernate query type mà không có lý do.

## 17. Native bulk UPDATE/DELETE có rủi ro phụ thuộc lifecycle

Ví dụ:

```java
int updated = em.createNativeQuery(
    """
    UPDATE catalog_product
    SET product_status = ?1
    WHERE product_status = ?2
    """
)
.setParameter(1, "INACTIVE")
.setParameter(2, "ACTIVE")
.executeUpdate();
```

Native DML gửi SQL trực tiếp tới database. Nó không hoạt động như một vòng lặp Java gọi setter trên từng managed entity.

Hệ quả:

- Managed Product trong persistence context có thể giữ state cũ.
- Entity-level lifecycle callbacks không tự chạy như `em.remove`/dirty checking cho từng row.
- `@Version` không tự được tăng theo mapping entity-level nếu SQL không thực hiện điều đó.
- Cascade JPA không tự áp cho từng entity từ native UPDATE/DELETE.
- Database constraints, FK và triggers vẫn có hiệu lực theo DB.
- Số rows returned từ `executeUpdate()` phụ thuộc lệnh/dialect/driver trong những trường hợp đặc biệt.

### 17.1. Ví dụ optimistic version cần có chủ đích

Nếu native SQL cập nhật giá, người lập trình có thể cần:

```sql
UPDATE catalog_product
SET
    unit_price = ?1,
    version = version + 1
WHERE id = ?2
  AND version = ?3;
```

Nếu số row được cập nhật bằng 0, có thể do record không tồn tại hoặc version đã khác; service phải quyết định có báo conflict, retry hay tải lại.

**Không coi việc thêm `version = version + 1` là một giải pháp universal** cho mọi mapping/version strategy. Cần đồng bộ với cơ chế optimistic lock của provider/entity và tránh giữ stale managed instances.

### 17.2. Clear/refresh với nhận thức rõ

```java
em.flush();
int rows = em.createNativeQuery(sql).executeUpdate();
em.clear();
```

`clear()` detach **toàn bộ** entities trong context. Đây là cách có thể giúp tránh stale state sau bulk SQL, nhưng có thể làm mất những pending changes chưa flush hoặc khiến code sau đó thao tác trên detached object. Không thêm `clear` bừa bãi vào library/helper toàn cục.

### 17.3. Tránh provider-native bulk query khi JPQL đủ dùng

Nếu chỉ cần:

```jpql
update Product p
set p.status = :newStatus
where p.status = :oldStatus
```

JPQL bulk DML có thể giảm phụ thuộc tên bảng/cột. Nhưng nó vẫn có các giới hạn lifecycle/optimistic locking riêng. Chọn JPQL không có nghĩa bỏ qua correctness của bulk operation.

## 18. Locking: tính khả chuyển cú pháp khác tính khả chuyển concurrency

Một worker lấy nhiệm vụ từ database:

```sql
SELECT *
FROM outbox_event
WHERE status = 'PENDING'
FOR UPDATE SKIP LOCKED;
```

Cú pháp locking như `FOR UPDATE SKIP LOCKED` rất hữu ích nhưng cách hỗ trợ khác nhau theo DB/version. Thậm chí cùng cú pháp, ý nghĩa chờ lock, transaction isolation, ordering và starvation có thể khác.

Không nên thay bằng một query khác chỉ vì “chạy được” mà bỏ qua semantic của claim:

- Hai worker có thể lấy cùng event không?
- Có lock/claim atomic không?
- Nếu worker crash, event có được retry không?
- Có lease và fencing token không?
- Có giới hạn độ dài transaction không?
- Query có thể bỏ qua cùng một row mãi mãi do starvation không?

### 18.1. API JPA lock mode không tự thay thế mọi native SQL lock

Với entity-based read, JPA có:

```java
Product product = em.find(
    Product.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Đây là API chuẩn JPA biểu đạt nhu cầu khóa ghi bi quan. Nhưng:

- Database vẫn quyết định locking semantics thực tế.
- Không phải mọi lock timeout/hint đều được thực thi giống nhau.
- Những nhu cầu như `SKIP LOCKED` cho queue worker có thể không có tương đương portable qua API JPA chuẩn.
- Không giả định `Query.setLockMode` trên một **native SQL query** có hỗ trợ hoặc ngữ nghĩa giống JPQL entity query giữa các provider.

Nếu concurrency invariant quan trọng, hãy test trên **database thực và các transaction đồng thời**, không chỉ compile Java code hoặc assert một result set.

## 19. Query hints: có chuẩn không đồng nghĩa hiệu lực giống nhau

JPA hỗ trợ `Query.setHint(name, value)`. Một ví dụ standard hint thường gặp:

```java
Query query = em.createNativeQuery(sql)
    .setHint("jakarta.persistence.query.timeout", 3000);
```

Hint này diễn đạt mong muốn timeout tính bằng mili giây theo quy tắc được đặc tả/hỗ trợ. Nhưng hiệu lực thực tế có thể chịu ảnh hưởng:

- Provider có nhận và chuyển hint không.
- Driver có hỗ trợ cancel/timeout hay không.
- Database có đang chờ lock/network không.
- Runtime, transaction manager hoặc request deadline có timeout khác.
- Hệ thống đã dùng `javax.persistence.*` cũ hay `jakarta.persistence.*` mới.

Một số JPA hints **có thể bị bỏ qua** nếu không được hỗ trợ, và provider-specific hints có tên/semantics riêng.

### 19.1. Dấu hiệu provider lock-in từ hints

```java
query.setHint("org.hibernate.readOnly", true);
```

Tên hint dạng `org.hibernate...` cho thấy đây là một tính năng Hibernate-specific trong một số môi trường/version, không phải một JPA standard contract. Đừng xem nó là portable chỉ vì gọi qua `Query.setHint`.

### 19.2. Cách kiểm soát

- Dùng standard JPA hints khi đáp ứng yêu cầu.
- Khi dùng vendor hint, đặt tập trung ở adapter/config và ghi rõ provider.
- Test hành vi **thật**, không chỉ test rằng `setHint` không ném exception.
- Có fallback hoặc giới hạn triển khai nếu hint không được hỗ trợ.
- Quan sát timeout và SQL execution ở production, tránh phụ thuộc “hint chắc chắn có tác dụng”.

## 20. Unwrap provider API: sử dụng có chủ đích và khoanh vùng

JPA `EntityManager.unwrap(...)` cho phép truy cập đối tượng provider underlying khi cần. Điều đó **không có nghĩa API nhận được sẽ portable**.

Ví dụ Hibernate-specific:

```java
org.hibernate.Session session =
    em.unwrap(org.hibernate.Session.class);
```

Nếu service cần Hibernate native query transformer:

```java
org.hibernate.query.NativeQuery<?> nativeQuery =
    em.createNativeQuery(sql)
      .unwrap(org.hibernate.query.NativeQuery.class);
```

Đoạn này có thể phụ thuộc version, vì API Hibernate thay đổi qua các major versions và cách gọi transformer/query options cũng thay đổi.

### 20.1. Hạn chế extension ở một ranh giới

**Không nên:**

```text
CheckoutService  -> Hibernate Session/NativeQuery
ProductService   -> Hibernate-specific hint
ReportService    -> Hibernate scalar transformer
InventoryService -> Hibernate Session
```

**Nên:**

```text
Business services
      |
      v
Repository interface / port
      |
      v
JPA adapter / Hibernate-specific adapter
      |
      v
Native SQL, provider hints, JDBC normalization
```

Cách này giảm chỗ phải sửa khi đổi provider hoặc nâng cấp Hibernate. Nó không xóa chi phí chuyển đổi, nhưng **giữ phụ thuộc ở nơi có thể thấy và kiểm soát**.

## 21. Thiết kế một repository port và hai triển khai

Giả sử business logic cần tìm sản phẩm theo từ khóa, chỉ trả danh sách rút gọn.

Định nghĩa contract độc lập provider:

```java
package com.example.shop.catalog;

import java.util.List;

public interface ProductLookup {
    List<ProductSummary> search(String keyword, int limit);
}
```

DTO:

```java
package com.example.shop.catalog;

import java.math.BigDecimal;

public record ProductSummary(
    Long id,
    String sku,
    String name,
    BigDecimal price
) { }
```

### 21.1. Triển khai bằng JPQL: lựa chọn mặc định

```java
@Repository
public class JpaProductLookup implements ProductLookup {

    @PersistenceContext
    private EntityManager em;

    @Override
    @Transactional(readOnly = true)
    public List<ProductSummary> search(
            String keyword,
            int limit
    ) {
        int safeLimit = Math.min(Math.max(limit, 1), 100);

        String pattern = "%" +
            keyword.toLowerCase(Locale.ROOT) + "%";

        return em.createQuery(
            """
            select new com.example.shop.catalog.ProductSummary(
                p.id, p.sku, p.name, p.price
            )
            from Product p
            where lower(p.name) like :pattern
            order by p.id
            """,
            ProductSummary.class
        )
        .setParameter("pattern", pattern)
        .setMaxResults(safeLimit)
        .getResultList();
    }
}
```

Ví dụ dùng annotation Spring (`@Repository`, `@Transactional`), không phải API JPA chuẩn. Phần JPA bên trong vẫn dùng entity properties và DTO projection.

Trong production cần thêm xử lý null/blank keyword, escape `%`/`_`, authorization/tenant filter và quy tắc collation. Ở đây mục đích là minh họa ranh giới giữa interface và adapter.

### 21.2. Triển khai chuyên PostgreSQL khi cần ILIKE

```java
@Repository
public class PostgresProductLookup implements ProductLookup {

    @PersistenceContext
    private EntityManager em;

    @Override
    @Transactional(readOnly = true)
    public List<ProductSummary> search(
            String keyword,
            int limit
    ) {
        int safeLimit = Math.min(Math.max(limit, 1), 100);

        String sql = """
            SELECT
                p.id,
                p.sku,
                p.display_name,
                p.unit_price
            FROM catalog_product p
            WHERE p.display_name ILIKE ?1
            ORDER BY p.id
            """;

        List<?> rows = em.createNativeQuery(sql)
            .setParameter(1, "%" + keyword + "%")
            .setMaxResults(safeLimit)
            .getResultList();

        List<ProductSummary> results = new ArrayList<>();

        for (Object item : rows) {
            Object[] row = (Object[]) item;

            results.add(
                new ProductSummary(
                    ((Number) row[0]).longValue(),
                    (String) row[1],
                    (String) row[2],
                    (BigDecimal) row[3]
                )
            );
        }

        return results;
    }
}
```

**Đây là adapter mang phụ thuộc PostgreSQL có chủ đích.** DTO giúp business service không biết SQL dialect, nhưng các cast JDBC scalar ở adapter vẫn phải được kiểm chứng. Có thể dùng `@ConstructorResult` để giảm mapping thủ công nếu provider/type support phù hợp.

Hệ thống chọn một adapter dựa trên **cấu hình triển khai rõ ràng**, không tạo hai `@Repository` beans cùng interface mà không có bean selection phù hợp.

### 21.3. So sánh hai adapter

| Đặc tính | JpaProductLookup | PostgresProductLookup |
|---|---|---|
| Truy vấn | JPQL | Native SQL với `ILIKE` |
| Tên trong query | Entity và Java properties | Bảng và cột SQL |
| Phụ thuộc cú pháp PostgreSQL | Không trực tiếp | Có |
| Phụ thuộc provider | Thấp hơn, nhưng vẫn cần test | Native scalar mapping vẫn cần test |
| Kiểu kết quả business | `ProductSummary` | `ProductSummary` |
| Nơi chứa đặc thù DB | Không | Bên trong adapter |
| Chuyển DB | Chủ yếu kiểm tra behavior/performance | Thêm/đổi adapter |
| Đòi hỏi test DB thật | Có | Đặc biệt quan trọng |

**Một interface không tự làm SQL portable**. Nó chỉ ngăn phụ thuộc lan ra business layer, giảm chi phí thay đổi.

## 22. Chiến lược dialect adapter cho nhiều database

Nếu phải hỗ trợ hai database có cú pháp upsert khác nhau, đừng rải câu lệnh điều kiện khắp service:

```java
if (dbVendor.equals("postgres")) {
    // ...
} else if (dbVendor.equals("mysql")) {
    // ...
}
```

Thay vào đó, định nghĩa một port:

```java
public interface ProductUpsertPort {
    void upsertProduct(
        long id,
        String sku,
        BigDecimal price
    );
}
```

Các adapter có thể khác nhau:

```text
ProductService
    |
    v
ProductUpsertPort
    |
    +-- PostgresProductUpsertAdapter
    |      INSERT ... ON CONFLICT ...
    |
    +-- MySqlProductUpsertAdapter
    |      INSERT ... ON DUPLICATE KEY UPDATE ...
    |
    +-- PortableJpaProductAdapter
           Strategy khác theo transaction/constraint
```

Quan trọng: **không mặc định SELECT trước rồi INSERT/UPDATE sau là upsert atomic**. Hai transaction có thể đồng thời thấy row chưa có và cùng INSERT, gây unique conflict. Nếu concurrency là invariant trọng yếu, adapter phải có cơ chế atomic phù hợp DB hoặc retry dựa trên constraint với transaction boundaries đúng.

### 22.1. Chọn capability thay vì suy diễn từ tên database khi cần

Đôi khi thiết kế cần:

```text
supportsSkipLocked
supportsReturning
supportsJsonPath
supportsNativeUpsert
supportsWindowFunctions
```

Các capability nên được khai báo/tính toán theo database+version mà deployment thực sự hỗ trợ, có test xác nhận. Không suy luận quá rộng rằng “PostgreSQL” hoặc “MySQL” là một tập khả năng bất biến cho mọi version.

### 22.2. Không thêm quá nhiều abstractions khi không cần

Nếu deployment chỉ sử dụng PostgreSQL có cam kết dài hạn, một repository adapter rõ tên `Postgres...` là đủ. Không cần tạo framework dialect đa tầng với hàng chục interface trống chỉ để đạt cảm giác “portable”.

Mục tiêu là **phụ thuộc có chủ đích và khoanh vùng**, không phải loại bỏ mọi khác biệt hệ thống bằng abstraction giả.

## 23. Schema và migration là một phần portability

Một native query có thể phụ thuộc trực tiếp:

```sql
SELECT p.sku, p.unit_price
FROM catalog_product p;
```

Khi migration đổi `unit_price` thành `price_amount`:

- Entity mapping có thể cập nhật bằng `@Column(name="price_amount")`.
- JPQL `p.price` có thể giữ nguyên.
- Native SQL `p.unit_price` **phải được cập nhật**.

Vì vậy, nhiều native queries phân tán có thể làm chi phí thay schema tăng mạnh.

### 23.1. Những phụ thuộc ngoài truy vấn

- Identity/sequence/auto-increment syntax.
- Data types: `UUID`, `JSONB`, `TEXT`, `CLOB`, `BLOB`, timezone types.
- Partial indexes, expression indexes, computed columns.
- Trigger, stored procedure và transaction semantics.
- Collation/character set.
- Constraint deferrability và null uniqueness rules.
- Schema namespaces/search path.
- Partitioning, table inheritance, views/materialized views.
- Quoted identifier capitalization.
- Database functions nằm trong default schema/extension.

Đổi JPA provider nhưng giữ DB vẫn có thể vướng mappings/DDL tự sinh. Đổi DB nhưng giữ provider có thể vướng rất nhiều migration và SQL đặc thù.

### 23.2. Quản lý migration theo môi trường được hỗ trợ

Với dự án nhiều DB, có thể dùng các migration riêng cho từng dialect (Flyway/Liquibase hoặc công cụ khác), hoặc lựa chọn schema chung trong khả năng thực tế.

Không nên dùng một DDL chỉ được test trên H2 rồi tuyên bố production PostgreSQL/MySQL/Oracle sẽ hoạt động giống nhau. Mỗi database target cần migration và schema verification riêng.

## 24. Test tính khả chuyển theo “ma trận môi trường”

Khả chuyển là một yêu cầu **có thể kiểm chứng**, không chỉ là lời bình luận trong code review.

Ví dụ một ma trận:

| Cấu hình test | Provider | Database | Mục tiêu |
|---|---|---|---|
| A | Hibernate | PostgreSQL | Cấu hình production chính |
| B | EclipseLink | PostgreSQL | Đánh giá phụ thuộc provider |
| C | Hibernate | MySQL | Đánh giá SQL dialect/database |
| D | EclipseLink | MySQL | Kiểm tra tương tác provider + DB nếu chính thức hỗ trợ |

Ma trận này chỉ là mẫu. Không cần chạy đủ 4 cấu hình nếu sản phẩm chính thức chỉ hỗ trợ cấu hình A. Nhưng phải **ghi rõ phạm vi được kiểm thử**; không dùng A để chứng minh tương thích B/C/D.

### 24.1. Hãy kiểm tra ít nhất bốn tầng kết quả

1. **SQL parse/execute:** câu SQL chạy được, bảng/cột/parameter đúng.
2. **Result mapping:** scalar/DTO/entity nhận đúng kiểu và giá trị, không chỉ không ném lỗi.
3. **Semantics:** filtering, NULL, sorting, duplicates, concurrency đúng theo nghiệp vụ.
4. **Operational behavior:** transaction, lock timeout, isolation, performance ở mức chấp nhận được.

Một test chỉ làm:

```java
assertDoesNotThrow(() -> query.getResultList());
```

là chưa đủ. Query có thể chạy mà tổng tiền sai, thiếu tenant filter hoặc ánh xạ nhầm `id` khi JOIN.

### 24.2. Fixture nên chứa những trường hợp dễ lộ khác biệt

- Có giá trị NULL và giá trị 0.
- Có Unicode/tiếng Việt có dấu và case variants.
- Có nhiều rows cùng sort key.
- Có một-to-many tạo duplicate rows.
- Có enum/Boolean/UUID/JSON columns.
- Có timestamp sát ranh giới ngày.
- Có số DECIMAL lớn và scale khác nhau.
- Có entity `@Version` và association FK.
- Có tenant khác và soft-deleted records.
- Có thao tác concurrent insert/upsert/locking.
- Có query trả tập rỗng.

Các fixture này giúp kiểm tra **độ đúng dữ liệu**, không chỉ tính hợp lệ cú pháp.

## 25. Contract test cho repository port

Nếu có hai adapter khác nhau, hãy chạy cùng một bộ contract tests:

```java
interface ProductLookupContract {

    ProductLookup lookup();

    void seedProducts();

    @Test
    default void returnsSameProductForExactKeyword() {
        seedProducts();

        List<ProductSummary> rows =
            lookup().search("Java", 20);

        assertTrue(rows.stream()
            .anyMatch(p -> p.sku().equals("BOOK-JAVA")));
    }
}
```

Đây là skeleton JUnit-style; triển khai thực tế cần fixture setup/teardown, test database và cách tạo `ProductLookup` cho từng môi trường. Các static imports/class annotations được lược bỏ để tập trung vào ý tưởng.

Hãy thêm assertions cho:

- Thứ tự trả về khi cùng `createdAt`/giá.
- Giới hạn result count.
- Không lộ dữ liệu tenant khác.
- Không nhân bản Product khi JOIN.
- Kiểu `BigDecimal`/`Long` đúng.
- Kết quả với keyword rỗng và ký tự wildcard.
- Hành vi Unicode/collation theo contract ứng dụng.

**Cùng contract, khác implementation** giúp thấy nơi native SQL có semantics khác JPQL.

### 25.1. Testcontainers không tự làm một query portable

Testcontainers có thể hỗ trợ khởi động database mục tiêu cho integration tests. Nhưng container chỉ giúp chạy database thật dễ hơn; cần cấu hình đúng:

- Phiên bản database mong muốn.
- Migration tương ứng.
- JDBC driver/provider thật.
- Timezone/collation liên quan.
- Dữ liệu fixture và trạng thái transaction.
- Assertions về behavior.

Không chạy test trên H2 rồi cho rằng có tính đại diện đầy đủ với PostgreSQL chỉ vì đều là relational database.

## 26. Portability review: cách chấm mức rủi ro theo bối cảnh

Để một nhóm dễ đánh giá thay vì tranh luận chung chung, có thể dùng bảng đánh giá định tính sau.

| Tiêu chí | Thấp | Trung bình | Cao |
|---|---|---|---|
| SQL syntax | Tính năng phổ biến, đã test các target | Một số function có biến thể | Dialect-specific syntax không có fallback |
| Provider API | Chỉ dùng chuẩn JPA | Có hint được kiểm soát | Unwrap/provider APIs rải khắp services |
| Result mapping | DTO/`@SqlResultSetMapping` rõ ràng | Một số native scalar casts | Partial entity, alias giả định |
| Type conversion | Kiểu JPA/JDBC cơ bản | UUID/Boolean/temporal có khác biệt | JSON/custom type/LOB gắn driver |
| Schema coupling | Nằm trong một repository | Nhiều truy vấn phụ thuộc DDL | SQL lặp nhiều module, migration khó |
| Transaction semantics | Có contract và test | Phụ thuộc auto-flush/lock timing | Race/lock assumptions không kiểm chứng |
| Test matrix | Đúng tập cấu hình cam kết | Chỉ test production chính | Tuyên bố multi-DB nhưng không có test |
| Security | Tenant/permission filter rõ | Một phần dựa provider filter | Native query bỏ qua authorization |

**Mức rủi ro phải đánh giá theo cam kết dự án.** Ví dụ SQL PostgreSQL-specific nằm trong `PostgresOutboxAdapter`, có concurrency tests trên PostgreSQL và không quảng cáo chạy database khác có thể là **rủi ro được chấp nhận**, không phải một bug.

### 26.1. Tạo quyết định kỹ thuật ngắn

Một bản ghi quyết định (*ADR*) có thể gồm:

```text
Decision: Dùng PostgreSQL ON CONFLICT cho Product upsert.
Scope: PostgresProductRepository, không lộ ra domain.
Reason: Cần atomic upsert cạnh tranh cao.
Portability: Không chuyển trực tiếp sang MySQL/Oracle.
Supported stack: Provider và DB/version trong ma trận chính thức.
Tests: Duplicate SKU dưới nhiều transaction, rollback, retry.
Fallback: Thêm adapter mới nếu hỗ trợ database khác.
Owner: Nhóm Catalog.
```

Một ADR như vậy giúp người nâng cấp/migrate biết đúng vùng bị ràng buộc, thay vì phải tìm ngẫu nhiên trong toàn codebase.

## 27. Phân biệt compile-time portability với runtime portability

Code có thể compile ngay cả khi SQL không hợp lệ:

```java
String sql = """
    SELECT jsonb_path_query(attributes_json, '$.color')
    FROM catalog_product
    """;

em.createNativeQuery(sql).getResultList();
```

Java compiler không phân tích cú pháp SQL bên trong chuỗi. Ngay cả khi provider compile query lúc startup, SQL dialect hoặc schema target có thể chỉ được xác minh khi chạy thật.

### 27.1. Ba thời điểm phát hiện lỗi

```text
Java compilation
   |
   | kiểm tra chữ ký JPA API, Java types
   v
JPA provider query preparation
   |
   | có thể phát hiện tham số/result mapping/hints
   v
Database execution
   |
   | xác nhận SQL syntax, schema, type, locks
   v
Result hydration + transaction completion
   |
   | xác nhận mapped fields, enum, IDs, commit
```

Nhiều lỗi portability xuất hiện **sau compile**, nên cần integration tests trên target matrix.

### 27.2. Thay provider có thể gây lỗi dù SQL không đổi

Giữ PostgreSQL và chuỗi SQL, nhưng đổi Hibernate sang EclipseLink có thể làm lộ:

- Named native parameters không được hỗ trợ giống nhau.
- Result aliases được diễn giải khác.
- Cách ép kiểu scalar khác.
- Flush timing/hints khác.
- Native result mapping với compound relationships khác.
- Cách xử lý paginated native query khác.
- Provider-specific custom type không có tương đương.

Đây là lý do **portability provider** là một trục riêng so với **portability database**.

## 28. Không phụ thuộc vô thức vào first-level cache và native query hydration

Một ví dụ:

```java
Product first = em.find(Product.class, productId);

Product second = (Product) em.createNativeQuery(
    """
    SELECT
        id, sku, display_name, unit_price,
        product_status, version, created_at
    FROM catalog_product
    WHERE id = ?1
    """,
    Product.class
)
.setParameter(1, productId)
.getSingleResult();
```

JPA persistence context quản lý identity của entity. Khi cả hai là cùng persistent identity trong một context, chúng thường là cùng managed instance. Nhưng nếu database đã được transaction khác cập nhật, native SELECT không tự có nghĩa “refresh mọi persistent fields”.

**Sai lầm:** Dùng native SQL để “bỏ qua cache JPA”, rồi ngạc nhiên khi object vẫn có state cũ.

Nếu cần state mới:

- Xác định transaction isolation.
- Xem `em.refresh(entity)` với ý nghĩa rõ.
- Hoặc dùng EntityManager/transaction mới khi phù hợp.
- Kiểm tra whether write pending needs flush or rollback.
- Không dùng `em.clear()` tùy tiện nếu còn managed changes.

Vấn đề ở đây không phải provider sai, mà là ứng dụng **đang kỳ vọng một hành vi ngoài hợp đồng explicit**.

## 29. Native SQL và cache cấp hai/query cache

Provider có thể có second-level cache hoặc query cache với behavior riêng.

Một câu native `UPDATE catalog_product ...` chạy trực tiếp không nhất thiết khiến mọi cache layer hiểu chính xác những rows/entities bị thay đổi, đặc biệt nếu dùng API hoặc công cụ ngoài JPA.

Rủi ro:

- Trả entity stale từ cache.
- Cache query chưa được invalidated theo bảng liên quan.
- Native query bypass một provider filter hoặc cache synchronization.
- Thay provider làm khác cơ chế cache invalidation.

Giảm rủi ro:

1. Dùng contract chuẩn và thiết kế transaction/mapping nhất quán.
2. Cô lập native DML, định nghĩa cache invalidation rõ.
3. Khi cần, dùng `Cache` API chuẩn của JPA để evict có chủ đích, hoặc API provider-specific tại adapter.
4. Kiểm thử đọc lại sau native DML dưới cấu hình cache giống production.
5. Không bật cache/disable cache như một cách “chữa” vấn đề mà chưa hiểu đúng invalidation path.

Ví dụ API chuẩn:

```java
em.getEntityManagerFactory()
  .getCache()
  .evict(Product.class, productId);
```

Việc evict second-level cache không đồng nghĩa clear first-level persistence context hoặc giải quyết mọi query cache của provider. Đây là hai lớp khác nhau.

## 30. Security: native SQL có thể bỏ qua quy ước ứng dụng

Một query repository JPQL có thể luôn kèm:

```jpql
where p.tenantId = :tenantId
  and p.deletedAt is null
```

Nhưng native SQL:

```sql
SELECT id, sku, display_name
FROM catalog_product;
```

nếu chạy không lọc tenant hoặc soft-delete, có thể lộ dữ liệu. Entity mapping về `Product.class` không đảm bảo tự thêm những predicate mà service đã quên.

Một số provider có filter annotation riêng; không giả định chúng được áp cho mọi native SQL giống JPQL.

### 30.1. Cách giảm nguy cơ

- Lấy `authorizedTenantId` từ security context đáng tin.
- Đặt filter tenant/soft-delete trong repository/SQL đúng contract.
- Với hệ thống hỗ trợ DB Row-Level Security, xác minh session/transaction context được thiết lập đúng.
- Đảm bảo integration tests có ít nhất hai tenant.
- Kiểm tra native SQL trong cả read/query, bulk DML và các báo cáo aggregate.
- Không coi chỉ số tổng hợp như `SUM(revenue)` là “không nhạy cảm” vì không trả dữ liệu row.

### 30.2. SQL injection cũng là vấn đề portability của kiến trúc

Không nối:

```java
String sql = "SELECT * FROM catalog_product WHERE sku = '" +
    userInput +
    "'";
```

Ngoài lỗ hổng injection, cách này còn gây khác biệt quoting/escaping giữa DB. Dùng parameter binding cho **giá trị**, whitelist cho **identifier/SQL fragments**.

## 31. Performance portability: chạy đúng chưa chắc chạy tốt

Một query có thể trả kết quả đúng trên cả PostgreSQL và MySQL, nhưng khác biệt:

- Statistics và optimizer.
- Index-only scan, covering index, bitmap scan.
- Join order và join algorithm.
- Function-based indexes.
- Cardinality estimates.
- Locking và MVCC behavior.
- Collation/selectivity.
- CTE materialization/inlining.
- Execution plan caching và parameter sniffing.

Ví dụ:

```sql
SELECT id, sku
FROM catalog_product
WHERE LOWER(display_name) LIKE ?;
```

Có thể khó dùng index thông thường trên `display_name`. Một DB có expression index phù hợp, DB khác cần generated column hoặc full-text index.

**Không xóa native SQL có lý do hiệu năng chỉ vì JPQL “portable hơn” về cú pháp**, nếu việc chuyển đổi gây mất tính năng quan trọng. Hãy đo hai hướng và ghi nhận lựa chọn.

### 31.1. Benchmark và EXPLAIN theo từng DB

Thực hành:

1. Chuẩn bị dữ liệu đại diện (không chỉ 10 rows).
2. Chạy query thực sự qua JPA/provider/driver.
3. Đo latency p50/p95, rows read, memory, network bytes.
4. Dùng `EXPLAIN`/execution plan theo DB.
5. Kiểm tra index/partition/hints.
6. Tách chi phí SQL từ chi phí entity hydration.
7. Kiểm tra số SQL statements do lazy relationships sinh ra.
8. Ghi lại plan/performance baseline khi nâng DB/provider.

Không hứa một index hoặc một SQL hint cho kết quả giống nhau trên mọi database.

## 32. Quy trình review một native query trước khi merge

Một review có cấu trúc có thể đi theo thứ tự:

### Bước 1 — Có cần Native SQL thật không?

- JPQL/Criteria có biểu đạt được mục đích không?
- Query có cần JSON/window/recursive/upsert/locking chuyên biệt không?
- Nếu vì hiệu năng, đã có bằng chứng đo và query plan chưa?

### Bước 2 — Xác định target matrix

- Provider nào được hỗ trợ?
- Database và version nào được hỗ trợ?
- JDBC driver và Java/Jakarta Persistence version nào?
- Cấu hình schema, timezone, collation, isolation nào có liên quan?

### Bước 3 — Tách phần SQL-specific

- Có `ON CONFLICT`, `ILIKE`, `RETURNING`, `JSONB`, `SKIP LOCKED` không?
- Có quoted identifiers, function, cast hoặc hints đặc thù không?
- Có dependency vào view, trigger hoặc stored procedure nào?
- Những khác biệt có nằm trong một adapter hay rải khắp services?

### Bước 4 — Kiểm tra ResultSet contract

- Query trả entity hay DTO?
- Nếu entity, đủ ID/version/FK/mapped columns chưa?
- Alias có trùng khi JOIN không?
- Scalar type có được suy đoán tùy provider không?
- Có dùng `@SqlResultSetMapping`/`@ColumnResult` khi cần không?

### Bước 5 — Kiểm tra state và transaction

- Auto-flush có bị giả định không?
- Native DML có làm managed state stale không?
- Có cần optimistic version/lock handling không?
- Có query cache/second-level cache không?
- Các transaction concurrent có thể tạo race condition không?

### Bước 6 — Kiểm tra security

- SQL có tenant/ownership/soft-delete filter?
- Mọi SQL fragments động đều whitelist?
- Input values đều parameterized?
- Có nguy cơ lộ dữ liệu trong log SQL/bind params?

### Bước 7 — Kiểm chứng

- Có integration tests trên supported DB/provider matrix?
- Có test NULL, duplicates, Unicode, timestamps và concurrency?
- Có assertion đúng dữ liệu, không chỉ assert không lỗi?
- Có query plan/performance check nếu là hot path?
- Có mô tả lựa chọn nếu phụ thuộc vendor là có chủ đích?

## 33. Những hiểu lầm phổ biến

### 33.1. “Dùng EntityManager API là portable”

**Chưa đủ.** Chuỗi native SQL, alias, JDBC types và database schema có thể vẫn phụ thuộc môi trường.

### 33.2. “Native SQL luôn không portable”

**Quá tuyệt đối.** Nhiều câu SQL đơn giản chạy trên nhiều DB. Cần đánh giá cụ thể mức khả chuyển cú pháp, dữ liệu và behavior, không dán nhãn toàn bộ native SQL.

### 33.3. “JPQL luôn nhanh hơn hoặc chậm hơn native SQL”

**Sai.** Hiệu năng phụ thuộc SQL sinh ra, index, data distribution và cách fetch. Đo trên workload thực.

### 33.4. “Hibernate có hỗ trợ thì JPA chuẩn bắt EclipseLink hỗ trợ”

**Sai.** Một API/query option của Hibernate có thể là extension. Cần xem contract Jakarta Persistence và target provider.

### 33.5. “Named parameter native SQL portable như JPQL”

**Không nên giả định.** Named native parameters có thể là hỗ trợ thêm của provider; lựa chọn thận trọng là dùng binding được target matrix xác nhận.

### 33.6. “IN (:ids) với List luôn chạy”

**Sai về tính portable native SQL.** Việc mở rộng collection parameters là provider-specific hoặc cần xử lý bằng adapter.

### 33.7. “COUNT(*) luôn là Long”

**Không chắc trong native scalar result.** Kiểu JDBC/driver/provider khác nhau. Normalize qua Number hoặc result mapping typed có kiểm chứng.

### 33.8. “ResultClass tự hydrate khi SELECT thiếu vài field”

**Không portable.** Entity cần đủ thông tin theo mapping; dùng DTO nếu chỉ cần một phần.

### 33.9. “SELECT * luôn là an toàn nhất”

**Không đúng trong JOIN nhiều bảng hoặc mapping phức tạp.** Có thể gây duplicate aliases, tải thừa dữ liệu và thiếu cột secondary/inheritance.

### 33.10. “@SqlResultSetMapping làm SQL độc lập DB”

**Sai.** Mapping điều khiển ResultSet→Java; cú pháp SQL và schema vẫn có thể vendor-specific.

### 33.11. “Native JOIN tự fetch mọi association”

**Sai.** SQL JOIN dùng lọc không tự xác định JPA association fetch plan trừ khi result mapping tương ứng.

### 33.12. “Native query trả POJO detached”

**Sai khi query ánh xạ entity.** Result có thể là entity managed trong persistence context.

### 33.13. “Native query luôn đọc state mới nhất, bỏ qua first-level cache”

**Sai.** Entity identity và managed state vẫn có hiệu lực; native SELECT không tự là `refresh`.

### 33.14. “Bulk native UPDATE sẽ tự tăng @Version”

**Không nên giả định.** SQL phải được thiết kế cho version/concurrency đúng theo mapping và nghiệp vụ.

### 33.15. “Chỉ cần đổi provider dialect setting thì mọi SQL native tự được viết lại”

**Sai.** Dialect có thể hỗ trợ pagination/type rendering, nhưng không phải trình biên dịch chuyển mọi PostgreSQL-specific SQL sang mọi database.

### 33.16. “LIKE/LOWER tương đương tuyệt đối trên mọi DB”

**Sai.** Collation, Unicode và index tạo khác biệt về semantics/performance.

### 33.17. “SQL query chạy trên H2 chứng minh production compatibility”

**Sai.** H2 có syntax modes và behavior riêng; cần test target DB/provider.

### 33.18. “Chỉ cần pass compile Java là query hợp lệ”

**Sai.** Native SQL trong String thường không được Java compiler kiểm tra. DB/runtime mới xác nhận nhiều lỗi.

### 33.19. “Có adapter interface là không còn vendor lock-in”

**Sai.** Adapter chỉ khoanh vùng phụ thuộc. Khi chuyển DB vẫn phải viết/test implementation khác và migrations tương ứng.

### 33.20. “Portability là mục tiêu cao nhất trong mọi dự án”

**Không phải luôn.** Sản phẩm một DB có thể ưu tiên tính năng/hiệu năng, miễn phụ thuộc được ghi nhận, test và cô lập.

### 33.21. “Provider filter luôn áp lên native SQL”

**Không nên giả định.** Tenant, soft-delete và authorization cần được bảo vệ theo contract có kiểm chứng.

### 33.22. “Query timeout hint chắc chắn dừng SQL đúng mili giây”

**Không đảm bảo.** Provider/driver/database và transaction timeout có thể ảnh hưởng cách cancellation hoạt động.

### 33.23. “Native SQL có setMaxResults sẽ phân trang 20 entity duy nhất”

**Không chắc nếu JOIN làm nhiều result rows trên một entity.** Cần phân trang đúng grain.

### 33.24. “Sau native bulk update, tất cả managed entities đồng bộ ngay”

**Sai.** Persistence context có thể stale; cần chiến lược flush/clear/refresh/context boundary đúng.

## 34. Bài tập thực hành

### Bài 1 — Phân loại phụ thuộc

```java
em.createNativeQuery(
    "SELECT id FROM catalog_product WHERE display_name ILIKE ?1"
);
```

**Câu hỏi:** Thành phần nào chuẩn JPA, thành phần nào phụ thuộc database?

**Gợi ý:** `createNativeQuery` là JPA API; `ILIKE` là SQL-specific.

### Bài 2 — So sánh portability với JPQL

Một truy vấn chỉ lọc Product theo `status` và sắp xếp `createdAt`.

**Câu hỏi:** Có nên ưu tiên native SQL không?

**Gợi ý:** Nếu không cần tính năng/hiệu năng đặc thù, JPQL hoặc Criteria thường giảm phụ thuộc schema/dialect.

### Bài 3 — Phụ thuộc provider bị giấu

```java
em.createNativeQuery(sql)
  .unwrap(org.hibernate.query.NativeQuery.class);
```

**Câu hỏi:** Có portable giữa Hibernate và EclipseLink không?

**Gợi ý:** Không. `unwrap` sang Hibernate-specific type cần adapter/cấu hình/hợp đồng rõ.

### Bài 4 — Scalar type

```java
Long count = (Long) em
    .createNativeQuery("SELECT COUNT(*) FROM catalog_product")
    .getSingleResult();
```

**Câu hỏi:** Vấn đề tiềm ẩn là gì?

**Gợi ý:** JDBC/provider có thể trả subtype Number khác. Dùng `Number` hoặc typed result mapping.

### Bài 5 — Native IN list

```java
em.createNativeQuery(
    "SELECT id FROM catalog_product WHERE id IN (:ids)"
).setParameter("ids", List.of(1L, 2L));
```

**Câu hỏi:** Có được coi là portable mặc định không?

**Gợi ý:** Không. Named native parameters và list expansion cần kiểm chứng/provider adapter; hoặc tạo scalar positional binds.

### Bài 6 — Alias ResultSet

SQL có:

```sql
SELECT id AS product_id, display_name AS product_name
FROM catalog_product;
```

**Câu hỏi:** Muốn map Product entity đầy đủ có vấn đề gì?

**Gợi ý:** Thiếu nhiều mapped columns; aliases khác mapping. Phải SELECT đầy đủ và có explicit `@FieldResult` hoặc dùng DTO nếu chỉ cần hai cột.

### Bài 7 — Upsert

Đoạn:

```sql
INSERT INTO catalog_product (id, sku)
VALUES (?, ?)
ON CONFLICT (sku) DO NOTHING;
```

**Câu hỏi:** Nếu ứng dụng phải hỗ trợ MySQL, nên làm gì?

**Gợi ý:** Định nghĩa adapter/capability theo dialect, bảo vệ atomicity/concurrency và test. Không chỉ thay chuỗi `ON CONFLICT` bằng `IF` ngoài transaction.

### Bài 8 — Unicode

Cần tìm tên có dấu tiếng Việt không phân biệt hoa thường. Query dùng `LOWER(name) LIKE LOWER(?)`.

**Câu hỏi:** Đã đảm bảo cùng semantics trên mọi DB chưa?

**Gợi ý:** Chưa. Phải xác định collation, normalization, wildcard escaping và test dữ liệu tiếng Việt.

### Bài 9 — Quản lý timestamp

Hệ thống thống kê đơn trong một ngày theo múi giờ Việt Nam.

**Câu hỏi:** Những điều gì cần test khi đổi DB?

**Gợi ý:** ZoneId, conversion sang Instant, kiểu timestamp, precision, ranh giới `[start,end)` và session timezone.

### Bài 10 — Native bulk UPDATE

Query cập nhật `unit_price` bằng SQL trực tiếp, Product entity cùng ID đang managed.

**Câu hỏi:** Có thể đọc Product managed thấy giá cũ không?

**Gợi ý:** Có. Native DML không cập nhật instance JPA đã managed theo dirty checking. Cần chiến lược đồng bộ context rõ.

### Bài 11 — Row locking

Worker dùng `FOR UPDATE SKIP LOCKED` để lấy outbox events.

**Câu hỏi:** Kiểm thử như thế nào ngoài query chạy được?

**Gợi ý:** Chạy hai workers concurrent, xác minh claim không trùng, timeout, crash/retry, isolation và starvation trên DB đích.

### Bài 12 — Query hint

`query.setHint("org.hibernate.readOnly", true)`.

**Câu hỏi:** Vì sao cần ghi nhận trong dependency review?

**Gợi ý:** Tên hint provider-specific; ý nghĩa/hỗ trợ có thể đổi giữa provider/version.

### Bài 13 — API phân trang

Native query JOIN Product với OrderLine rồi `setMaxResults(20)`.

**Câu hỏi:** Có chắc lấy 20 Product khác nhau?

**Gợi ý:** Không. JOIN có thể nhân bản rows; phân trang theo ID Product trước khi tải entity.

### Bài 14 — Thay tên cột

Migration đổi `unit_price` thành `price_amount`, entity Java vẫn là `price`.

**Câu hỏi:** Điều gì thay đổi?

**Gợi ý:** Cần cập nhật mapping `@Column` và SQL native tham chiếu tên cột vật lý. JPQL `p.price` có thể giữ nguyên.

### Bài 15 — Kiểm thử provider

Query thành công với Hibernate/PostgreSQL. Team tuyên bố hỗ trợ EclipseLink/PostgreSQL.

**Câu hỏi:** Đã có đủ bằng chứng chưa?

**Gợi ý:** Chưa. Cần integration/contract tests trên EclipseLink, nhất là named parameters, result mapping, pagination, flush/hints.

### Bài 16 — Multiple tenants

Một native SQL report quên filter `tenant_id`, chỉ trả SUM.

**Câu hỏi:** Có phải vấn đề bảo mật không?

**Gợi ý:** Có. Aggregate có thể lộ dữ liệu tenant khác; bảo vệ query hoặc DB RLS theo security context.

### Bài 17 — Phụ thuộc có chủ đích

Một sản phẩm chỉ deploy PostgreSQL, dùng JSONB query trong `PostgresCatalogRepository`, có test.

**Câu hỏi:** Có nhất thiết phải loại bỏ JSONB để “portable” không?

**Gợi ý:** Không. Đánh giá theo cam kết môi trường; document/cô lập/test là điều quan trọng.

### Bài 18 — SQL function với không có index

`WHERE LOWER(display_name) LIKE ?` chậm trên database mới.

**Câu hỏi:** Câu SQL hợp lệ có đủ coi tính khả chuyển đạt yêu cầu không?

**Gợi ý:** Chưa. Còn performance portability; cần query plan, index/collation strategy theo database.

### Bài 19 — Entity identity

Native query trả Product#100 đã managed.

**Câu hỏi:** Có phải một detached snapshot mới không?

**Gợi ý:** Không. First-level cache/entity identity vẫn tham gia; nếu muốn fresh state, xem refresh/context/isolation.

### Bài 20 — Bảng đánh giá rủi ro

Đánh giá hai lựa chọn:

- A: JPQL lọc status, dùng `ProductSummary` DTO, test trên hai DB.
- B: Native SQL dùng JSON operator, named params, custom Hibernate transformer trong service, chỉ test H2.

**Gợi ý:** A có portability cao hơn theo ma trận này. B có nhiều phụ thuộc database/provider và lỗ hổng kiểm thử; nếu tính năng JSON cần thiết thì cô lập vào adapter và test target DB.

## 35. Checklist trước khi chấp nhận một phụ thuộc provider/database

Một native query nên được xem là có trách nhiệm khi nhóm phát triển có thể trả lời rõ:

- [ ] **Tại sao cần native SQL?** Có lý do kỹ thuật hoặc nghiệp vụ cụ thể.
- [ ] **Đang hỗ trợ provider nào?** Có cấu hình/version rõ.
- [ ] **Đang hỗ trợ database nào?** Có version và migration tương ứng.
- [ ] **SQL-specific syntax đã được nhận diện?** Function, JSON, locking, upsert, pagination, hints.
- [ ] **Provider extensions được khoanh vùng?** Không rải `org.hibernate.*` khắp business service.
- [ ] **Result mapping rõ ràng?** Entity đủ cột hoặc DTO/scalar contract phù hợp.
- [ ] **Parameter binding an toàn?** Dùng binds cho values; whitelist identifiers.
- [ ] **NULL, numeric, UUID, Boolean, temporal mapping đã test?**
- [ ] **Alias/quoted identifier behavior đã test?**
- [ ] **Native DML và persistence context đã xử lý?** Version/flush/clear/cache.
- [ ] **Concurrency và locking đã test trên DB thật khi cần?**
- [ ] **Tenant, authorization, soft-delete không bị bỏ qua?**
- [ ] **Pagination/sorting ổn định, không nhân bản entity ngoài ý định?**
- [ ] **Bộ integration tests phản ánh target matrix?**
- [ ] **Performance baseline được đo khi query là hot path?**
- [ ] **Có ADR/tài liệu quyết định và phương án chuyển đổi khi phụ thuộc vendor?**

Đây là checklist để người học áp dụng trong review công việc, **không phải kết quả kiểm thử tự động của một dự án cụ thể**.

## 36. Tổng kết

Những nguyên tắc cần ghi nhớ:

1. **Portability có nhiều trục:** JPA API, JPA provider, database dialect, JDBC type, schema và semantics vận hành.
2. **`EntityManager.createNativeQuery` là API chuẩn**, nhưng chuỗi SQL bên trong vẫn có thể phụ thuộc PostgreSQL/MySQL/Oracle/SQL Server.
3. **Không nhầm tính khả chuyển cú pháp với tính khả chuyển kết quả và hiệu năng.** `LOWER`/`LIKE` chạy được chưa chắc cùng collation hoặc index behavior.
4. **Ưu tiên JPQL/Criteria** khi yêu cầu chỉ là truy vấn entity/association thông thường; dùng native khi có nhu cầu rõ.
5. **Đừng phụ thuộc ngầm vào provider extensions** như native list binding, query transformers, hints, auto-flush synchronization hoặc scalar coercion.
6. **Nếu dùng `unwrap` hoặc `org.hibernate.*`, hãy cô lập trong adapter** và ghi lại lý do, provider/version, test/fallback.
7. **ResultSet mapped về entity cần đủ dữ liệu** theo ID/version/FK/attribute/inheritance; chỉ lấy vài cột nên dùng DTO.
8. **`@SqlResultSetMapping` là công cụ chuẩn giúp khai báo alias và kiểu kết quả**, nhưng không làm SQL vendor-specific trở thành SQL portable.
9. **Native bulk DML có thể làm persistence context stale** và không tự thực hiện entity-level lifecycle/version semantics.
10. **JPA pagination và hints không thay thế thử nghiệm trên target dialect**, nhất là query complex, JOIN collections và locking.
11. **Native SQL phải được bảo vệ khỏi injection và thiếu tenant/soft-delete predicates**; provider filters không phải bảo đảm cho mọi query.
12. **Portability phải được xác nhận bằng integration/contract tests trên ma trận được cam kết**, không chỉ qua Java compile hay H2.
13. **Một phụ thuộc vendor có chủ đích, được cô lập và được kiểm thử có thể hoàn toàn hợp lý.** Không nên xây abstraction giả nếu chỉ hỗ trợ một database.
14. **Ghi nhận quyết định kỹ thuật** giúp lần nâng cấp provider, thay driver hoặc chuyển DB có ranh giới thay đổi dễ xác định.

**Kết luận:** Đánh giá tính khả chuyển của Native SQL trong JPA không phải tìm cách cấm mọi tính năng đặc thù, mà là **nhận diện đúng nguồn phụ thuộc, xác định mức hỗ trợ được cam kết và cô lập các khác biệt có chủ đích**. Hãy dùng JPA chuẩn khi nó đáp ứng nhu cầu; khi cần native SQL hoặc API provider riêng, đưa chúng vào tầng hạ tầng, chuẩn hóa result mapping, đảm bảo transaction/security semantics và kiểm thử trên database/provider thực tế. Làm như vậy giúp ứng dụng tận dụng được sức mạnh SQL mà không để những phụ thuộc vô tình chi phối toàn bộ kiến trúc JPA.
