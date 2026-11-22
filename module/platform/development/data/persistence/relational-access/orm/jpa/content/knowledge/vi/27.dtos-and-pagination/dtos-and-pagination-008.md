# Tránh giả định phân trang đúng khi fetch join tập hợp trong JPA

**Phân trang** và **fetch join collection** là hai nhu cầu rất phổ biến trong ứng dụng sử dụng Jakarta Persistence (JPA), nhưng ghép chúng một cách thiếu kiểm soát có thể tạo kết quả sai hoặc khiến ứng dụng phải tải một lượng dữ liệu rất lớn.

Giả sử trang quản trị cần hiển thị **20 đơn hàng mỗi trang**, đồng thời hiện các dòng sản phẩm (`OrderLine`) trong từng đơn. Một truy vấn trông rất tự nhiên:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.createdAt DESC
```

Sau đó Java gọi:

```java
query.setFirstResult(0);
query.setMaxResults(20);
```

Nhìn qua, câu truy vấn dường như yêu cầu “20 đơn hàng và toàn bộ các dòng hàng của chúng”. Nhưng khi join một quan hệ **một-nhiều**, **một đơn hàng có thể tạo nhiều dòng SQL**. Nếu database giới hạn 20 dòng SQL, điều đó không đồng nghĩa 20 đơn hàng. Nếu provider tránh lỗi bằng cách lấy nhiều dòng rồi **phân trang trong bộ nhớ**, dữ liệu có thể đúng hơn nhưng chi phí hiệu năng rất lớn.

> **Nguyên tắc trọng tâm:** Không giả định `setFirstResult()` và `setMaxResults()` phân trang đúng entity cha khi query có **collection fetch join**. JPA không bảo đảm semantics phân trang kết hợp fetch join tập hợp; chiến lược an toàn thường là **phân trang các entity cha trước, sau đó tải collection cho đúng tập cha đã chọn**.

Bài học thuộc chương **DTO và phân trang**, tập trung vào giới hạn này, cách nhận ra hậu quả và các thiết kế thay thế: phân trang ID hai bước, DTO projection, query riêng cho collection, entity graph có kiểm soát, batch fetching và keyset pagination. Các ví dụ dùng `PurchaseOrder` và `OrderLine`, kèm JPQL, Java service và Spring Data JPA.

## 1. Hai bài toán riêng: lấy trang entity và tải quan hệ

Một ứng dụng thường có hai câu hỏi độc lập:

1. **Những entity cha nào thuộc trang hiện tại?**
2. **Với mỗi entity cha đã chọn, cần tải những dữ liệu liên quan nào?**

Ví dụ người dùng chọn:

```text
Trang 1, pageSize = 3, sắp xếp theo createdAt giảm dần
```

Ứng dụng cần chọn ba đơn hàng đầu tiên theo thứ tự này. Sau khi xác định ba đơn, giao diện mới cần lấy lines của chúng.

Nếu hai câu hỏi được ghép thành một truy vấn `JOIN FETCH` trên collection, SQL xử lý các **hàng kết quả của phép join**, không trực tiếp xử lý “nhóm entity cha” theo đúng ý định giao diện.

### 1.1. Fetch join là gì?

Trong JPQL:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

`FETCH` yêu cầu JPA provider nạp association `o.lines` cùng các `PurchaseOrder` được trả. Nó khác với:

```jpql
SELECT o
FROM PurchaseOrder o
LEFT JOIN o.lines l
```

Dạng không có `FETCH` chủ yếu dùng để truy cập phần tử quan hệ trong điều kiện, phép chiếu hoặc tổng hợp; nó **không tự mang ý nghĩa phải khởi tạo collection**.

### 1.2. Phân trang ở cấp entity cha

Trong Java:

```java
query.setFirstResult(offset);
query.setMaxResults(pageSize);
```

`offset` và `pageSize` diễn đạt ý định của ứng dụng. Với query chỉ chọn root entity và không có join làm nhân các hàng gốc, provider có thể triển khai bằng SQL `OFFSET`/`LIMIT`, `FETCH FIRST` hoặc cú pháp tương đương.

Nhưng với collection fetch join, số hàng SQL sau phép join **không còn tương ứng một-một với số entity cha**.

### 1.3. Ví dụ giao diện cần đạt

Giả sử thứ tự đơn hàng:

```text
Order#1001 (3 lines)
Order#1002 (0 lines)
Order#1003 (2 lines)
Order#1004 (1 line)
Order#1005 (0 lines)
```

Với `pageSize = 3`:

```text
Page 0: [Order#1001, Order#1002, Order#1003]
Page 1: [Order#1004, Order#1005]
```

**Đây là trang theo PurchaseOrder**, bất kể đơn có 0, 2, 3 hay 300 dòng hàng.

Nếu cách triển khai thay đổi danh sách cha chỉ vì số dòng hàng của một đơn thay đổi, đó là dấu hiệu phạm vi phân trang không đúng nhu cầu.

## 2. Mô hình entity dùng trong bài

Giả sử ứng dụng có hai entity:

```text
+-------------------------------+
| PurchaseOrder                 |
|-------------------------------|
| id : Long                     |
| createdAt : LocalDateTime     |
| status : OrderStatus          |
| lines : List<OrderLine>       |
+-------------------------------+
                1
                |
                |
                *
+-------------------------------+
| OrderLine                     |
|-------------------------------|
| id : Long                     |
| order : PurchaseOrder         |
| sku : String                  |
| quantity : int                |
| unitPrice : BigDecimal        |
+-------------------------------+
```

### 2.1. Enum trạng thái

```java
package com.example.orders;

public enum OrderStatus {
    OPEN,
    PAID,
    CANCELLED
}
```

### 2.2. PurchaseOrder

```java
package com.example.orders;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @OneToMany(
        mappedBy = "order",
        fetch = FetchType.LAZY
    )
    @OrderBy("id ASC")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

`@OneToMany` mặc định `LAZY` theo JPA; ở đây ghi rõ để nhấn mạnh rằng collection **chỉ nên được tải khi use case cần**.

`@OrderBy("id ASC")` mô tả cách sắp xếp **các OrderLine bên trong collection**. Nó **không** quyết định thứ tự các `PurchaseOrder` trong trang. Muốn phân trang cha ổn định, phải viết `ORDER BY o.createdAt, o.id` ở query chọn cha.

### 2.3. OrderLine

```java
package com.example.orders;

import java.math.BigDecimal;
import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Column(
        name = "unit_price",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
```

`OrderLine.order` là quan hệ đơn trị về phía cha. Chọn `LAZY` có chủ đích; nếu bỏ `fetch` thì `@ManyToOne` mặc định `EAGER`, có thể kéo theo các truy vấn không cần thiết.

### 2.4. Schema quan hệ

DDL PostgreSQL minh họa:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES purchase_orders(id),
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL
);

CREATE INDEX idx_orders_status_created_id
    ON purchase_orders(
        status,
        created_at DESC,
        id DESC
    );

CREATE INDEX idx_order_lines_order_id
    ON order_lines(order_id);
```

Index đầu hỗ trợ lọc theo trạng thái và thứ tự các đơn trong những trường hợp optimizer thấy phù hợp. Index thứ hai hỗ trợ tìm các dòng hàng theo `order_id`. Không có index nào thay đổi được vấn đề **một entity cha sinh nhiều hàng khi join collection**.

## 3. Ví dụ nhân số hàng sau LEFT JOIN

Giả sử có năm đơn hàng đều ở trạng thái `PAID`, sắp xếp theo `createdAt DESC, id DESC`:

| Order | Số OrderLine | Các line IDs |
| --- | ---: | --- |
| #1001 | 3 | 11, 12, 13 |
| #1002 | 0 | — |
| #1003 | 2 | 31, 32 |
| #1004 | 1 | 41 |
| #1005 | 0 | — |

Một SQL join tương tự:

```sql
SELECT
    o.id AS order_id,
    o.created_at,
    l.id AS line_id,
    l.sku
FROM purchase_orders o
LEFT JOIN order_lines l
    ON l.order_id = o.id
WHERE o.status = 'PAID'
ORDER BY o.created_at DESC, o.id DESC, l.id ASC;
```

Có thể thu được các hàng:

| Hàng SQL | order_id | line_id |
| ---: | ---: | ---: |
| 1 | 1001 | 11 |
| 2 | 1001 | 12 |
| 3 | 1001 | 13 |
| 4 | 1002 | NULL |
| 5 | 1003 | 31 |
| 6 | 1003 | 32 |
| 7 | 1004 | 41 |
| 8 | 1005 | NULL |

Chỉ có **5 đơn hàng**, nhưng `LEFT JOIN` trả **8 dòng SQL**.

### 3.1. Quy tắc đếm hàng từ LEFT JOIN

Với một collection và một phép `LEFT JOIN` không có bộ lọc/phép nối gây nhân khác, mỗi order có:

- `n` lines với `n > 0` → `n` dòng SQL.
- Không có lines → một dòng SQL với phía line là `NULL`.

Tổng số hàng có thể viết minh họa:

\[
\text{joinedRows}=\sum_{\text{order }o}\max(1,\text{lineCount}(o))
\]

Đây không phải công thức cần dùng trong SQL; nó giúp nhìn ra vì sao **row count sau join** khác **root entity count**.

### 3.2. Sai lệch nếu LIMIT áp trên hàng đã join

Nếu database chạy:

```sql
SELECT
    o.id AS order_id,
    l.id AS line_id
FROM purchase_orders o
LEFT JOIN order_lines l
    ON l.order_id = o.id
WHERE o.status = 'PAID'
ORDER BY o.created_at DESC, o.id DESC, l.id ASC
LIMIT 3 OFFSET 0;
```

ba hàng đầu là:

```text
(1001, 11)
(1001, 12)
(1001, 13)
```

Tức trang có **3 dòng SQL nhưng chỉ 1 entity PurchaseOrder**.

Người dùng muốn:

```text
[1001, 1002, 1003]
```

nhưng những hàng SQL được giới hạn chỉ chứa:

```text
[1001, 1001, 1001]
```

Dù JPA provider khử trùng lặp những object cùng ID trong kết quả Java, điều đó **không biến ba hàng SQL thành ba orders khác nhau**.

### 3.3. Sai lệch nghiêm trọng hơn: collection không đầy đủ

Nếu `Order#1001` có 30 lines nhưng SQL bị giới hạn 10 hàng đầu, phần trả về có thể chỉ chứa **10/30 lines**.

Nếu provider dùng những hàng đó để khởi tạo collection, ứng dụng có nguy cơ nhìn thấy một collection không đầy đủ. Một provider có thể tránh nguy cơ này bằng cách **không áp LIMIT trực tiếp vào joined rows** và phân trang theo cách khác. Vì vậy không thể khẳng định mọi JPA provider sẽ trả collection thiếu; điều cần nhớ là **không có bảo đảm phân trang đúng và hiệu quả theo kỳ vọng khi collection fetch join được kết hợp với paging**.

## 4. Giới hạn theo đặc tả JPA

Theo ngữ nghĩa của Jakarta Persistence, việc áp `setFirstResult` hoặc `setMaxResults` lên truy vấn có **fetch join qua collection** không có kết quả được đặc tả bảo đảm theo cách thông thường.

Đây là một giới hạn của **hợp đồng JPA**, chứ không chỉ là lỗi của một ORM.

Vì vậy cần tránh suy luận:

```text
JPA query trả entity cha
+ setMaxResults(20)
+ LEFT JOIN FETCH collection
= bảo đảm đúng 20 entity cha và đầy đủ collection của chúng
```

Đẳng thức trên **không được bảo đảm**.

### 4.1. Tại sao đặc tả không thể đơn giản hóa thành LIMIT SQL?

Provider phải đồng thời xử lý hai yêu cầu:

1. Giới hạn đúng số entity cha.
2. Lấy đầy đủ mọi dòng con cho những entity cha được chọn.

Đặt `LIMIT` vào joined rows thường chỉ đáp ứng một giới hạn về **số hàng SQL**, không đạt cả hai mục tiêu.

Muốn giữ cả hai, provider có thể phải dùng query lồng, bước chọn ID, xử lý trong memory hoặc kỹ thuật đặc thù DBMS. JPA không buộc mọi provider dùng một cách cài đặt duy nhất cho tổ hợp này.

### 4.2. Đừng dựa vào hành vi tình cờ của một phiên bản provider

Một môi trường có thể:

- Phát cảnh báo rồi **phân trang trong memory**.
- Từ chối query khi bật tùy chọn nghiêm ngặt.
- Tạo SQL không giống kỳ vọng.
- Có những tối ưu riêng cho một số query shapes.

Nếu test một trang với hai orders nhỏ và thấy đúng, không nên kết luận query sẽ đúng/nhanh với hàng nghìn đơn có nhiều lines.

**Hướng an toàn là cấu trúc query sao cho không phụ thuộc hành vi không được bảo đảm này.**

## 5. In-memory pagination: đúng số entity chưa chắc nhanh

Một số phiên bản/cấu hình Hibernate có thể phát hiện collection fetch join kết hợp pagination và **đọc nhiều hàng hơn cần thiết**, sau đó cắt danh sách entity trong memory.

Ví dụ người dùng yêu cầu:

```text
Page 0, size 20
```

Database có:

```text
100.000 orders
1.000.000 order_lines
```

Nếu query phải đưa một lượng lớn dữ liệu join về ứng dụng rồi mới phân trang, chi phí có thể là:

```text
Database
   |
   | rất nhiều joined rows
   v
JDBC / network
   |
   | materialize entities/collections
   v
JPA provider / heap memory
   |
   | deduplicate + page in memory
   v
20 PurchaseOrder được trả
```

UI cuối cùng chỉ có 20 orders, nhưng công việc nền có thể xử lý một phần dữ liệu lớn hơn rất nhiều.

### 5.1. “Kết quả đúng” không đồng nghĩa “phân trang ở database”

Giả sử test thấy:

```java
assertEquals(20, result.size());
```

Điều đó chưa chứng minh:

- SQL đã dùng `LIMIT 20` đúng phạm vi root orders.
- Provider không tải toàn bộ joined rows.
- Không có hàng triệu objects trung gian.
- Độ trễ sẽ ổn khi dữ liệu tăng.
- Collection của mỗi order không thiếu.
- Không có cảnh báo ORM.

Cần phân biệt **correctness của danh sách cuối** với **chi phí thực thi**.

### 5.2. Hibernate và cảnh báo pagination over collection fetch

Hibernate có những cảnh báo liên quan tới việc áp `firstResult/maxResults` khi fetch collection; thông báo/mã cảnh báo cụ thể có thể khác giữa các phiên bản.

Trong cấu hình Hibernate, có tùy chọn provider-specific:

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Ý nghĩa: thay vì lặng lẽ xử lý bằng cách phân trang trong memory, Hibernate có thể **ném lỗi** khi phát hiện mẫu query nguy hiểm này.

Đây là **tùy chọn Hibernate**, không phải thuộc tính chuẩn Jakarta Persistence. Khi dự án sử dụng provider khác, cần tìm cơ chế tương ứng hoặc bảo đảm ở tầng repository không xây query sai.

### 5.3. Vì sao nên fail fast?

Một trang nhỏ có thể hoạt động tốt trong môi trường phát triển nhưng trở thành truy vấn tốn hàng giây hoặc phút trong production khi số lượng dòng con tăng.

Nếu bật fail fast, lỗi xuất hiện ngay trong quá trình phát triển/tích hợp thay vì chờ đến khi tải dữ liệu lớn. Tuy nhiên, **đó không thay thế việc thiết kế truy vấn đúng**.

## 6. DISTINCT không giải quyết giới hạn phân trang

Nhiều code cố xử lý bằng:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.createdAt DESC
```

`DISTINCT` diễn đạt ý định trả các entity `PurchaseOrder` không lặp lại theo semantics JPQL.

Nhưng trong SQL join, các hàng:

```text
order_id=1001, line_id=11
order_id=1001, line_id=12
order_id=1001, line_id=13
```

**không giống nhau trên toàn bộ danh sách cột** vì `line_id` khác nhau. Một `SELECT DISTINCT` ở mức SQL không thể tự biến các hàng khác line thành một hàng mà vẫn giữ được mọi line.

### 6.1. DISTINCT xử lý duplicate theo hai tầng khác nhau

- **SQL rows:** mỗi cặp order–line vẫn có thể là một row riêng.
- **JPA entity results:** provider có thể deduplicate entity gốc theo identity.

Nhưng ngay cả khi Java result chỉ chứa một `PurchaseOrder#1001`, `LIMIT 3` áp trên SQL join chưa thể chọn thêm #1002 và #1003.

### 6.2. Hibernate có thể deduplicate entity roots

Một số phiên bản Hibernate xử lý duplicate roots của collection fetch join khác nhau; vì vậy việc cần `DISTINCT` ở JPQL và cách nó được truyền xuống SQL có thể phụ thuộc phiên bản.

**Không được coi “Hibernate tự bỏ trùng root” là giải pháp phân trang collection fetch join.** Vấn đề thứ tự áp giới hạn và phạm vi kết quả vẫn tồn tại.

### 6.3. COUNT DISTINCT cũng là chuyện khác

`COUNT(DISTINCT o.id)` có thể xử lý số lượng **root entities** bị nhân trong truy vấn tổng hợp. Nhưng nó không sửa một `SELECT ... JOIN FETCH` kết hợp `LIMIT/OFFSET` thiếu bảo đảm.

Cần tách ba yêu cầu:

1. Không trùng root entities trong kết quả.
2. Tổng số root entities khớp filter.
3. Page boundaries áp lên root entities, không lên joined rows.

`DISTINCT` có thể giúp mục (1) hoặc (2), nhưng **không tự bảo đảm mục (3)**.

## 7. Giải pháp nền tảng: phân trang ID cha trước, fetch collection sau

Cách tiếp cận phổ biến và dễ kiểm soát gồm hai bước:

**Bước 1:** Chọn đúng `pageSize` **ID của PurchaseOrder** theo thứ tự ổn định, không fetch collection.

**Bước 2:** Tải các orders có ID nằm trong trang đó cùng các `OrderLine`, **không áp pagination vào query fetch collection**.

Sơ đồ:

```text
Request pageIndex=0, pageSize=3
             |
             v
   QUERY 1: SELECT o.id ...
            ORDER BY createdAt DESC, id DESC
            OFFSET 0 LIMIT 3
             |
             v
       [1001, 1002, 1003]
             |
             v
   QUERY 2: SELECT DISTINCT o
            LEFT JOIN FETCH o.lines
            WHERE o.id IN (...)
            [KHÔNG LIMIT/OFFSET]
             |
             v
   PurchaseOrder#1001 + 3 lines
   PurchaseOrder#1002 + 0 lines
   PurchaseOrder#1003 + 2 lines
             |
             v
   Sắp xếp lại root theo [1001,1002,1003]
             |
             v
        DTO của trang
```

### 7.1. Bước 1: lấy ID theo thứ tự ổn định

JPQL:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
```

Java:

```java
List<Long> ids = em.createQuery(
        "SELECT o.id FROM PurchaseOrder o " +
        "WHERE o.status = :status " +
        "ORDER BY o.createdAt DESC, o.id DESC",
        Long.class
    )
    .setParameter("status", OrderStatus.PAID)
    .setFirstResult(pageIndex * pageSize)
    .setMaxResults(pageSize)
    .getResultList();
```

**Không có fetch join tập hợp** ở đây. Kết quả là một danh sách ID cha, nên có thể áp phân trang theo root IDs.

Đoạn tính offset trực tiếp chỉ minh họa; ứng dụng thật cần kiểm tra page index/size và overflow khi nhân.

### 7.2. Vì sao ORDER BY cần tie-breaker?

Nếu chỉ viết:

```jpql
ORDER BY o.createdAt DESC
```

nhiều đơn có thể có cùng `createdAt`. Database không bắt buộc trả chúng theo một thứ tự cố định khi không có thêm điều kiện.

Do đó, nên thêm khóa duy nhất:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

Với `id` là khóa chính duy nhất, cặp điều kiện này tạo **thứ tự xác định** nếu dữ liệu và tiêu chí không đổi.

Không nên nghĩ SQL tự sắp xếp theo PK khi thiếu `ORDER BY`.

### 7.3. Bước 2: fetch collection cho các ID được chọn

JPQL:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

Java:

```java
List<PurchaseOrder> orders = em.createQuery(
        "SELECT DISTINCT o " +
        "FROM PurchaseOrder o " +
        "LEFT JOIN FETCH o.lines " +
        "WHERE o.id IN :ids",
        PurchaseOrder.class
    )
    .setParameter("ids", ids)
    .getResultList();
```

**Cực kỳ quan trọng:** Không gọi `setFirstResult` hoặc `setMaxResults` trên **query fetch collection này**.

Query chỉ tải tập orders đã được chọn bởi bước 1. Tất cả lines của mỗi order trong tập ID có thể được lấy đầy đủ theo fetch join.

### 7.4. Vì sao LEFT JOIN FETCH?

Một order không có lines vẫn thuộc trang. `LEFT JOIN FETCH` giữ nó:

```text
Order#1002 -> lines = []
```

Nếu dùng `JOIN FETCH` (inner join), order có collection rỗng có thể bị loại khỏi kết quả bước 2. Khi đó bước 1 chọn 3 IDs nhưng bước 2 chỉ trả 2 orders — một lỗi nghiệp vụ.

### 7.5. Danh sách ID rỗng

Nếu bước 1 trả `List.of()`, không nên tạo query với `IN ()` rồi kỳ vọng mọi DBMS/dialect xử lý như nhau.

```java
if (ids.isEmpty()) {
    return List.of();
}
```

Một page nằm ngoài phạm vi có thể trả content rỗng, nhưng tổng số records vẫn nên được lấy từ count query theo hợp đồng API.

## 8. Bước 2 không tự giữ thứ tự của bước 1

Một hiểu nhầm khác:

> “`WHERE o.id IN :ids` sẽ trả orders theo thứ tự trong Java List `ids`.”

Không có bảo đảm như vậy.

Nếu `ids = [1001,1002,1003]`, database có thể trả:

```text
[1003,1001,1002]
```

Điều kiện `IN` là điều kiện membership, **không phải `ORDER BY`**.

### 8.1. Sắp xếp lại bằng vị trí ID

```java
Map<Long, PurchaseOrder> byId = new HashMap<>();

for (PurchaseOrder order : orders) {
    byId.put(order.getId(), order);
}

List<PurchaseOrder> ordered = new ArrayList<>();

for (Long id : ids) {
    PurchaseOrder order = byId.get(id);

    if (order == null) {
        // Có thể có xóa/sửa đồng thời giữa hai bước.
        throw new IllegalStateException(
            "Order disappeared between page and fetch: " + id
        );
    }

    ordered.add(order);
}
```

Kết quả Java giữ đúng thứ tự `ids` của bước 1.

### 8.2. Có thể ORDER BY lại trong query fetch?

Có thể lặp các tiêu chí:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
ORDER BY o.createdAt DESC, o.id DESC
```

Tuy nhiên, **bước 1 là nguồn chân lý về membership và thứ tự của trang**. Nếu dữ liệu bị thay đổi giữa hai bước, một `ORDER BY` ở query 2 có thể cho thứ tự khác, hoặc một số entity không còn thỏa bộ lọc ban đầu.

Sắp xếp bằng `ids` trong memory giúp bảo toàn thứ tự đã chọn; vấn đề thay đổi dữ liệu giữa hai queries cần được giải quyết bằng transaction/isolation ở cấp cao hơn.

### 8.3. Đừng phụ thuộc vào thứ tự của một Set

Nếu bước 1 đã có `List<Long> ids`, đừng vô tình chuyển thành `HashSet<Long>` rồi dùng thứ tự iteration để trả API.

Set phục vụ membership/dedup; List giữ thứ tự page.

## 9. Truy vấn COUNT riêng để biết tổng số đơn

Một API trả phân trang thường có:

```json
{
  "pageIndex": 0,
  "pageSize": 3,
  "totalElements": 5,
  "content": ["..."]
}
```

`totalElements` phải đếm **số PurchaseOrder thỏa filter**, không phải số `OrderLine` hay số joined rows.

Với ví dụ chỉ lọc trạng thái:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :status
```

Java:

```java
long total = em.createQuery(
        "SELECT COUNT(o) FROM PurchaseOrder o " +
        "WHERE o.status = :status",
        Long.class
    )
    .setParameter("status", OrderStatus.PAID)
    .getSingleResult();
```

### 9.1. Không dùng collection fetch join trong count query

Không nên:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

`FETCH` có mục đích tải association của entity được chọn. Một aggregate `COUNT` không trả entity owner để khởi tạo collection, nên kết hợp này sai mục đích và có thể bị provider từ chối.

Count query phải được thiết kế **riêng**, không lấy query fetch rồi thay mỗi `SELECT o` thành `COUNT(o)`.

### 9.2. COUNT với join thường có thể đếm trùng

Query:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity >= :minimumQuantity
```

đếm các hàng join thỏa điều kiện. Nếu một order có ba lines phù hợp, order đó có thể bị đếm ba lần.

Nếu mục tiêu là số **orders duy nhất**:

```jpql
SELECT COUNT(DISTINCT o.id)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity >= :minimumQuantity
```

Hoặc tránh nhân root bằng `EXISTS`:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.quantity >= :minimumQuantity
)
```

Cách `EXISTS` thường biểu đạt chính xác “đơn nào có ít nhất một line thỏa điều kiện” mà không cần join child thành root rows của query chính.

### 9.3. COUNT có thể khác kết quả page nếu filter không nhất quán

Nếu query ID lọc:

```jpql
WHERE o.status = :status
  AND o.createdAt >= :fromTime
```

nhưng count query chỉ lọc:

```jpql
WHERE o.status = :status
```

thì metadata tổng sẽ sai.

Phải đảm bảo count và page-id query dùng **cùng định nghĩa tập root thỏa điều kiện**. Khác biệt hợp lệ chỉ nằm ở projection, ordering và pagination — count không cần ORDER BY.

## 10. Java service hoàn chỉnh: page ID, fetch lines, map DTO

Dưới đây là một ví dụ end-to-end cho **trang PurchaseOrder có lines**. Cấu trúc chính:

1. Kiểm tra đầu vào.
2. Đếm root orders.
3. Lấy ID trang với ORDER BY ổn định.
4. Nếu ID rỗng, trả page rỗng.
5. Fetch lines cho đúng IDs, không áp limit.
6. Khôi phục thứ tự trang.
7. Ánh xạ thành DTO trước khi kết thúc persistence context.

### 10.1. DTO để trả về API

Ví dụ các records lồng trong một service:

```java
public record LineDto(
    Long id,
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderDto(
    Long id,
    LocalDateTime createdAt,
    OrderStatus status,
    List<LineDto> lines
) {}

public record OrderPageDto(
    List<OrderDto> content,
    long totalElements,
    int pageIndex,
    int pageSize
) {}
```

DTO khác entity ở chỗ không cần JPA tiếp tục lazy load khi controller serialize chúng.

### 10.2. Service triển khai

```java
package com.example.orders;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;

public final class OrderPageReader {

    public record LineDto(
        Long id,
        String sku,
        int quantity,
        BigDecimal unitPrice
    ) {}

    public record OrderDto(
        Long id,
        LocalDateTime createdAt,
        OrderStatus status,
        List<LineDto> lines
    ) {}

    public record OrderPageDto(
        List<OrderDto> content,
        long totalElements,
        int pageIndex,
        int pageSize
    ) {}

    public OrderPageDto readPage(
            EntityManager em,
            OrderStatus status,
            int pageIndex,
            int pageSize) {

        if (status == null) {
            throw new IllegalArgumentException(
                "status is required"
            );
        }
        if (pageIndex < 0 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException(
                "Invalid page index/size"
            );
        }

        long offset = (long) pageIndex * pageSize;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Offset is too large"
            );
        }

        // Bước A: đếm đúng số entity cha.
        long total = em.createQuery(
                "SELECT COUNT(o) FROM PurchaseOrder o " +
                "WHERE o.status = :status",
                Long.class
            )
            .setParameter("status", status)
            .getSingleResult();

        // Bước B: chọn ID của đúng trang, không fetch lines.
        TypedQuery<Long> idQuery = em.createQuery(
            "SELECT o.id FROM PurchaseOrder o " +
            "WHERE o.status = :status " +
            "ORDER BY o.createdAt DESC, o.id DESC",
            Long.class
        );

        List<Long> ids = idQuery
            .setParameter("status", status)
            .setFirstResult((int) offset)
            .setMaxResults(pageSize)
            .getResultList();

        if (ids.isEmpty()) {
            return new OrderPageDto(
                List.of(), total, pageIndex, pageSize
            );
        }

        // Bước C: fetch đầy đủ lines cho tập IDs đã chọn.
        // KHÔNG áp setFirstResult / setMaxResults ở đây.
        List<PurchaseOrder> fetched = em.createQuery(
                "SELECT DISTINCT o " +
                "FROM PurchaseOrder o " +
                "LEFT JOIN FETCH o.lines " +
                "WHERE o.id IN :ids",
                PurchaseOrder.class
            )
            .setParameter("ids", ids)
            .getResultList();

        // Bước D: ánh xạ theo ID để giữ thứ tự trang.
        Map<Long, PurchaseOrder> byId = new HashMap<>();
        for (PurchaseOrder order : fetched) {
            byId.put(order.getId(), order);
        }

        List<OrderDto> content =
            new ArrayList<>(ids.size());

        for (Long id : ids) {
            PurchaseOrder order = byId.get(id);

            if (order == null) {
                throw new IllegalStateException(
                    "Order missing after ID selection: " + id
                );
            }

            List<LineDto> lines = order.getLines()
                .stream()
                .map(line -> new LineDto(
                    line.getId(),
                    line.getSku(),
                    line.getQuantity(),
                    line.getUnitPrice()
                ))
                .toList();

            content.add(new OrderDto(
                order.getId(),
                order.getCreatedAt(),
                order.getStatus(),
                lines
            ));
        }

        return new OrderPageDto(
            List.copyOf(content),
            total,
            pageIndex,
            pageSize
        );
    }
}
```

Đây là một **compilation unit độc lập** cho `OrderPageReader` nếu các entity/enum ở trên tồn tại trong cùng package và môi trường sử dụng Java hỗ trợ `record`/`Stream.toList()`.

### 10.3. Vì sao DTO được tạo trong phương thức?

Service đang có EntityManager đang hoạt động, do đó có thể đọc `order.getLines()` sau khi fetch. DTO được tạo trước khi trả kết quả để tầng HTTP không phải dựa vào lazy loading.

Phương thức trên **không tự bắt đầu transaction**. Caller hoặc framework phải định nghĩa transaction boundary nếu muốn tính nhất quán giữa count, query ID và query fetch.

### 10.4. Không tạo một trang thiếu content bằng cách bỏ qua ID mất tích

Nếu giữa hai queries, một order bị xóa hoặc không còn hiện diện theo snapshot, query fetch có thể trả thiếu ID.

Ví dụ code chủ động ném lỗi để **không im lặng trả một trang không đáp ứng contract**. Trong ứng dụng thật, cần chọn chính sách:

- Retry toàn bộ thao tác đọc trang.
- Áp transaction/isolation cung cấp snapshot thích hợp.
- Chấp nhận page có ít hơn số phần tử nếu API quy định eventual consistency.
- Trả lỗi có thể retry hoặc hướng người dùng tải lại.

Không có một chính sách đúng cho mọi sản phẩm. Điều không nên làm là lặng lẽ cho rằng hai bước luôn đọc cùng một ảnh chụp dữ liệu.

## 11. Transaction và tính nhất quán giữa các bước

Hai query tải dữ liệu ở hai thời điểm:

```text
t1: COUNT(o)        -> total = 5
t2: SELECT o.id ... -> [1001, 1002, 1003]
t3: FETCH o.lines   -> các orders và lines
```

Giữa `t2` và `t3` có thể xảy ra:

- Order#1002 bị xóa.
- Một order được cập nhật `status`.
- Thêm một line mới cho Order#1001.
- Đổi `createdAt` làm thứ tự trang dịch chuyển.
- Một transaction khác thêm order mới vào đầu danh sách.

### 11.1. READ COMMITTED không tự cung cấp cùng snapshot

Ở nhiều hệ quản trị, transaction `READ COMMITTED` cho phép mỗi statement thấy dữ liệu đã commit ở thời điểm thích hợp của statement đó. Do đó **ba câu SELECT trong cùng transaction chưa chắc thấy một snapshot hoàn toàn giống nhau**.

Không được suy rằng chỉ cần thêm `@Transactional(readOnly = true)` là ba query tự động nhìn cùng dữ liệu. Hành vi còn tùy isolation và implementation database.

### 11.2. Khi cần snapshot ổn định

Nếu nghiệp vụ yêu cầu:

> “Danh sách ID, tổng số đơn và lines phải cùng một ảnh chụp nhất quán.”

cần kiểm tra cơ chế của DBMS, có thể dùng transaction isolation/snapshot phù hợp. Nhưng:

- `REPEATABLE READ` có semantics khác nhau giữa DBMS.
- Snapshot isolation không luôn đồng nghĩa serializable.
- Giữ transaction đọc lâu có thể tăng chi phí và ảnh hưởng concurrency.
- Những thay đổi ở collection có thể cần cân nhắc isolation của bảng child.

Không nên chỉ nâng isolation toàn ứng dụng mà chưa đánh giá tải thực tế.

### 11.3. Phân trang nhiều request còn khó hơn

Ngay cả khi **một trang** được đọc nhất quán, người dùng có thể tải trang 1 sau khi dữ liệu đã thêm order mới. Với offset pagination, một order có thể xuất hiện lại hoặc bị bỏ qua giữa các lần xem trang.

Đây là giới hạn tự nhiên của offset pagination trên dữ liệu thay đổi, **không riêng fetch join**. Keyset pagination có thể cải thiện trong một số trường hợp.

## 12. Đếm và chọn page IDs khi có bộ lọc trên child

Một tình huống phức tạp hơn:

> Hiển thị các đơn PAID có **ít nhất một line có SKU bắt đầu bằng "BOOK"**, vẫn phân trang theo order và trả **toàn bộ lines** của các order được chọn.

Không nên dùng:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN FETCH o.lines l
WHERE l.sku LIKE :skuPattern
```

Có nhiều vấn đề:

1. Theo JPQL chuẩn, fetch join không được đặt identification variable cho fetched association theo cách join thông thường; một số provider có extension nhưng không portable.
2. Điều kiện trên alias child của fetch join có thể dẫn tới collection chỉ chứa các lines khớp filter, thay vì **toàn bộ lines**.
3. Phân trang qua collection fetch join vẫn có vấn đề nhân hàng.
4. `DISTINCT` không tự sửa các vấn đề này.

### 12.1. Đặt điều kiện tồn tại ở bước chọn root IDs

Dùng `EXISTS`:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
  AND EXISTS (
      SELECT l.id
      FROM OrderLine l
      WHERE l.order = o
        AND l.sku LIKE :skuPattern
  )
ORDER BY o.createdAt DESC, o.id DESC
```

Ở đây mỗi PurchaseOrder chỉ xuất hiện **một lần trong kết quả ID**, vì query chính không join collection thành các rows.

### 12.2. Count query cùng filter

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :status
  AND EXISTS (
      SELECT l.id
      FROM OrderLine l
      WHERE l.order = o
        AND l.sku LIKE :skuPattern
  )
```

### 12.3. Fetch toàn bộ lines ở bước 2

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

**Không đặt điều kiện `sku LIKE ...` vào fetch join ở bước 2** nếu màn hình cần toàn bộ lines. Điều kiện SKU đã được dùng để chọn **những orders thuộc trang**, không phải chọn **những lines phải xuất hiện trong collection**.

### 12.4. Phân biệt hai use case khác nhau

**Use case A:** Chọn orders có ít nhất một line khớp SKU, sau đó xem **mọi line** của từng order.

**Use case B:** Chọn orders rồi chỉ hiển thị **những line khớp SKU**.

Hai yêu cầu cần query/DTO mapping khác nhau. Đừng dùng một fetch join có điều kiện mà không xác định rõ collection được xem là đầy đủ hay bị lọc một phần.

Đối với Use case B, thường thích hợp dùng projection riêng cho các matching lines và tạo DTO, không gắn một collection lọc một phần vào trạng thái của managed entity.

## 13. Khi nên dùng DTO projection thay vì fetch join

Không phải trang nào cũng cần nguyên aggregate hoặc toàn bộ collection.

Ví dụ trang danh sách chỉ hiển thị:

- Order ID.
- Thời điểm tạo.
- Trạng thái.
- Tổng số line.
- Tổng tiền.

Không cần tải mọi `OrderLine` thành entity chỉ để tính số lượng.

### 13.1. Projection chọn scalar

DTO:

```java
package com.example.orders.dto;

import java.time.LocalDateTime;

public record OrderSummary(
    Long id,
    LocalDateTime createdAt,
    String status,
    Long lineCount
) {}
```

Nếu enum trong entity là `OrderStatus`, DTO có thể giữ kiểu enum thay vì chuỗi:

```java
public record OrderSummary(
    Long id,
    LocalDateTime createdAt,
    OrderStatus status,
    Long lineCount
) {}
```

Đây là **phương án thay thế** record vừa nêu; khi dùng, chỉ chọn một định nghĩa đúng với projection thực tế.

### 13.2. Count lines bằng correlated subquery trong JPQL WHERE hoặc aggregate

Một cách portable hơn cho danh sách có số lượng line là dùng `LEFT JOIN` và `GROUP BY`:

```jpql
SELECT
    o.id,
    o.createdAt,
    o.status,
    COUNT(l)
FROM PurchaseOrder o
LEFT JOIN o.lines l
WHERE o.status = :status
GROUP BY o.id, o.createdAt, o.status
ORDER BY o.createdAt DESC, o.id DESC
```

Kết quả mỗi group là một order, vì vậy `setFirstResult()/setMaxResults()` có thể được áp theo **các nhóm root** sau GROUP BY trong một query phù hợp.

Tuy nhiên, cần chú ý:

- Không fetch collection.
- COUNT có kiểu `Long`.
- GROUP BY có thể tốn chi phí với dữ liệu lớn.
- Nếu thêm joins nhiều collection, count có thể bị nhân; cân nhắc `COUNT(DISTINCT l.id)` hoặc subquery.
- SQL/provider cần hỗ trợ projection/grouping phù hợp.
- Nếu chỉ cần danh sách đơn không có thống kê, query này vẫn phức tạp hơn cần thiết.

### 13.3. Khi DTO đơn giản còn tốt hơn

Nếu UI chỉ cần `o.id, o.createdAt, o.status`, dùng:

```jpql
SELECT o.id, o.createdAt, o.status
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
```

Không cần JOIN hay FETCH.

**Ưu tiên lấy đúng dữ liệu màn hình cần** trước khi tối ưu mọi mối quan hệ bằng fetch join.

### 13.4. Tránh trả managed entity trực tiếp ra HTTP

Nếu controller serialize `PurchaseOrder` trực tiếp, serializer có thể truy cập `getLines()` và kích hoạt lazy loading, hoặc gặp lỗi khi persistence context đã đóng.

DTO giúp:

- Quy định rõ trường nào trả về.
- Kiểm soát số lượng child records.
- Tránh vòng lặp JSON do quan hệ hai chiều.
- Không vô tình tải thêm association ngoài fetch plan.
- Tách entity persistence khỏi hợp đồng API.

## 14. Một giải pháp khác: trang cha + query riêng cho các child

Nếu chỉ muốn đọc **một trang cha** và **một tập child**, không nhất thiết phải dùng fetch join ở bước 2.

Bước 1 vẫn lấy ID của trang:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
```

Bước 2 lấy thông tin cha:

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.id IN :ids
```

Bước 3 lấy tất cả lines theo ID cha:

```jpql
SELECT l
FROM OrderLine l
WHERE l.order.id IN :ids
ORDER BY l.order.id ASC, l.id ASC
```

Sau đó group lines theo `orderId` và gắn vào **DTO**, không nhất thiết sửa trực tiếp persistent collections trên managed entity.

### 14.1. Vì sao cách này có thể tốt?

- Không có câu SQL join làm nhân fields của parent nhiều lần.
- Tập child được truy vấn đúng phạm vi IDs.
- Dễ tạo DTO độc lập.
- Không có collection fetch join cần phân trang.
- Có thể dùng query child với projection chỉ gồm trường cần thiết.
- Thuận lợi khi một trang cha có **nhiều collection khác nhau**.

### 14.2. Cẩn trọng khi gắn child vào entity managed

Không nên làm:

```java
order.getLines().clear();
order.getLines().addAll(filteredLines);
```

chỉ để thay collection persistent bằng một tập child được lọc theo UI. Điều đó có thể bị JPA hiểu là thay đổi quan hệ và gây cập nhật/xóa dữ liệu khi flush, đặc biệt nếu `orphanRemoval` được bật.

Nếu cần kết quả có tập con được lọc, hãy dựng **DTO**, không sửa trạng thái persistent collection với dữ liệu trình bày.

### 14.3. Không tự tạo N+1

Sau khi lấy 20 orders, đoạn code:

```java
for (PurchaseOrder o : orders) {
    o.getLines().size();
}
```

có thể phát 20 queries để tải collection nếu chưa được khởi tạo. Query child theo `WHERE l.order.id IN :ids` gom việc đọc vào một thao tác có kiểm soát.

## 15. Khi cần nhiều collection: tránh tích số hàng

Giả sử PurchaseOrder có:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@ManyToMany
private Set<Tag> tags;
```

Một order có:

- 30 lines.
- 10 tags.

Nếu fetch cả hai trong một query:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.tags
WHERE o.id IN :ids
```

tập rows join có thể lên tới **30 × 10 = 300 hàng cho một order**.

Nếu trang có 20 orders tương tự, số hàng join có thể rất lớn. Provider còn có thể áp hạn chế riêng với một số kiểu collection; ví dụ một số trường hợp Hibernate có `MultipleBagFetchException` khi fetch nhiều bag.

### 15.1. Tách tải nhiều collection

Một hướng:

1. Page IDs của 20 orders.
2. Tải parents và lines.
3. Tải tags của đúng 20 IDs bằng query riêng.
4. Dựng DTO.

Hoặc:

1. Page IDs.
2. Query DTO parents.
3. Query DTO lines.
4. Query DTO tags.
5. Group theo order ID.

**Hai hoặc ba SQL queries có thể tốt hơn một câu JOIN khổng lồ** nếu nó tránh tích số hàng và giảm dữ liệu trùng lặp truyền qua mạng.

### 15.2. Đo cả số hàng, không chỉ số query

Không nên coi “1 SQL query” luôn tối ưu hơn “3 SQL queries”. Một truy vấn trả 500.000 joined rows có thể tệ hơn ba truy vấn chỉ trả đúng 20 parents, 200 lines và 50 tags.

Chỉ số nên quan sát:

- Số SQL statements.
- Số rows được database trả.
- Lượng dữ liệu qua network.
- Thời gian database thực thi.
- Heap allocation/GC của JVM.
- Latency p50/p95/p99 của endpoint.

## 16. Collection EntityGraph có giải quyết pagination không?

Entity graphs giúp mô tả association cần fetch:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("lines");
```

Có thể gắn:

```java
query.setHint("jakarta.persistence.loadgraph", graph);
```

Nhưng nếu query chính đồng thời dùng:

```java
query.setFirstResult(offset);
query.setMaxResults(pageSize);
```

thì **không được mặc định entity graph biến vấn đề collection pagination thành an toàn**.

### 16.1. Vì sao?

Graph yêu cầu tải collection. Provider có thể đáp ứng bằng:

- Join.
- Secondary SELECT.
- Một chiến lược fetch riêng.
- Kết hợp nhiều kỹ thuật.

Nếu graph dẫn tới SQL join collection trong truy vấn phân trang root, các rủi ro nhân hàng/giới hạn vẫn cần xem xét.

### 16.2. EntityGraph thích hợp khi nào?

- Load **chi tiết một order** với lines.
- Fetch collection cho một tập ID đã được phân trang.
- Mô tả graph có chủ đích cho use case không có root pagination.
- Tải một số quan hệ đơn trị nhỏ trong query trang.

Không dùng graph như “công tắc bảo đảm không còn N+1 và phân trang luôn đúng”.

### 16.3. @EntityGraph trong Spring Data JPA

Ví dụ:

```java
@EntityGraph(attributePaths = "lines")
Page<PurchaseOrder> findByStatus(
    OrderStatus status,
    Pageable pageable
);
```

Cần đặc biệt thận trọng: việc thêm `@EntityGraph` chứa collection lên một method trả `Page` không tự bảo đảm phân trang root bằng SQL đúng và hiệu quả.

Cách ổn định hơn là **page IDs trước**, rồi dùng repository query khác với entity graph/fetch join cho những IDs đó.

## 17. Spring Data JPA: triển khai hai bước

Spring Data JPA cung cấp `Pageable`, `Page<T>` và `@Query` để giảm boilerplate, nhưng vẫn dựa vào JPA provider. Nó **không loại bỏ giới hạn collection fetch join**.

### 17.1. Repository phân trang ID

```java
package com.example.orders;

import java.util.Collection;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            SELECT o.id
            FROM PurchaseOrder o
            WHERE o.status = :status
            ORDER BY o.createdAt DESC, o.id DESC
            """,
        countQuery = """
            SELECT COUNT(o)
            FROM PurchaseOrder o
            WHERE o.status = :status
            """
    )
    Page<Long> findPageIds(
        @Param("status") OrderStatus status,
        Pageable pageable
    );

    @Query("""
        SELECT DISTINCT o
        FROM PurchaseOrder o
        LEFT JOIN FETCH o.lines
        WHERE o.id IN :ids
        """)
    List<PurchaseOrder> fetchWithLines(
        @Param("ids") Collection<Long> ids
    );
}
```

`Page<Long>` chứa **root IDs** cùng metadata. `fetchWithLines(...)` không nhận Pageable và không tự áp `LIMIT/OFFSET`.

### 17.2. Service dùng repository

```java
package com.example.orders;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPagingService {

    private final PurchaseOrderRepository repository;

    public OrderPagingService(
            PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<PurchaseOrder> findPaidWithLines(
            int pageIndex,
            int pageSize) {

        if (pageIndex < 0
                || pageSize < 1
                || pageSize > 100) {
            throw new IllegalArgumentException(
                "Invalid pagination"
            );
        }

        Page<Long> idsPage = repository.findPageIds(
            OrderStatus.PAID,
            PageRequest.of(pageIndex, pageSize)
        );

        List<Long> ids = idsPage.getContent();

        if (ids.isEmpty()) {
            return idsPage.map(id -> {
                throw new IllegalStateException(
                    "No IDs expected in empty page"
                );
            });
        }

        List<PurchaseOrder> fetched =
            repository.fetchWithLines(ids);

        Map<Long, PurchaseOrder> byId = new HashMap<>();
        for (PurchaseOrder order : fetched) {
            byId.put(order.getId(), order);
        }

        return idsPage.map(id -> {
            PurchaseOrder order = byId.get(id);
            if (order == null) {
                throw new IllegalStateException(
                    "Order missing: " + id
                );
            }
            return order;
        });
    }
}
```

Đoạn trên minh họa `Page.map` giữ metadata trang và thứ tự IDs. Trong REST API production, **nên map tiếp sang DTO trong transaction** thay vì trả thẳng entity:

```java
Page<OrderPageReader.OrderDto> dtoPage =
    entityPage.map(order -> new OrderPageReader.OrderDto(
        order.getId(),
        order.getCreatedAt(),
        order.getStatus(),
        order.getLines()
            .stream()
            .map(l -> new OrderPageReader.LineDto(
                l.getId(),
                l.getSku(),
                l.getQuantity(),
                l.getUnitPrice()
            ))
            .toList()
    ));
```

Đoạn dùng `OrderPageReader.OrderDto`/`LineDto` từ ví dụ trước; nó phải chạy trong phạm vi có thể đọc collections đã fetch.

### 17.3. Vì sao Pageable không đi vào fetchWithLines?

Vì đã xác định đúng IDs của trang tại `findPageIds`. Query thứ hai cần tải đầy đủ dữ liệu của các IDs đó, không giới hạn lại theo joined rows.

### 17.4. Metadata Page có thể cần một count query

Spring Data có thể phát sinh count query từ truy vấn phân trang; với JPQL phức tạp, nên **khai báo `countQuery` tường minh** để bảo đảm tổng số root đúng.

Đừng để framework cố tạo count query bằng cách giữ nguyên một `JOIN FETCH` collection. Đó là một hình dạng truy vấn không thích hợp cho aggregate count.

### 17.5. Cần lưu ý về sắp xếp Pageable

Ở ví dụ trên, JPQL đã có `ORDER BY o.createdAt DESC, o.id DESC`. Vì thế `PageRequest.of(pageIndex, pageSize)` không truyền dynamic Sort.

Nếu API cho user chọn sort field, hãy whitelist các field được phép và thiết kế JPQL/Criteria tương ứng, không tự nối tên cột tùy ý từ input. Mọi query chọn IDs phải giữ một **tie-breaker duy nhất**.

## 18. Nếu chỉ fetch quan hệ đơn trị thì sao?

Quan hệ `@ManyToOne` hoặc `@OneToOne` có cardinality tối đa một target cho mỗi root. Vì thế một phép to-one fetch join đúng mapping **thường không nhân nhiều rows cho một root** như collection fetch join.

Ví dụ:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
WHERE o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
```

Nếu `o.customer` là quan hệ nhiều-một bắt buộc, query dạng này có thể phù hợp với phân trang root vì mỗi order tương ứng tối đa một Customer row.

Tuy vậy, cần phân biệt:

- Một to-one fetch join đúng cardinality không có vấn đề **nhân hàng theo collection**.
- Nếu query còn join một collection khác để lọc, root vẫn có thể lặp.
- LEFT/INNER join có thể loại root theo tính tùy chọn của association.
- Provider có thể phát SQL bổ sung từ các eager associations khác.

Vì vậy, không nên nói “mọi fetch join đều không thể phân trang”. **Rủi ro đặc trưng ở đây là fetch join của collection-valued association.**

### 18.1. Phân trang ID vẫn hữu ích với nhiều to-one liên quan?

Có thể, nhưng không phải lúc nào cũng cần. Với một màn hình chỉ cần order và customer, một query DTO hoặc to-one fetch join thường đã đủ, không nhất thiết tách thành hai bước.

Chọn chiến lược dựa trên shape của query và use case, không áp dụng máy móc “mọi phân trang phải hai bước”.

## 19. Keyset pagination: tránh giới hạn của OFFSET sâu

Offset pagination:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
ORDER BY o.createdAt DESC, o.id DESC
```

với:

```java
setFirstResult(100000);
setMaxResults(20);
```

có thể trở nên đắt khi offset rất sâu, tùy DBMS/index. Nó cũng dễ gặp hiện tượng trùng/bỏ qua bản ghi giữa các page nếu nhiều dữ liệu mới được thêm vào đầu.

**Keyset pagination** (seek pagination) xác định trang tiếp theo dựa trên khóa của phần tử cuối trang trước.

### 19.1. Cursor theo createdAt và ID

Giả sử sort:

```jpql
ORDER BY o.createdAt DESC, o.id DESC
```

Cursor chứa:

```text
lastCreatedAt
lastId
```

Truy vấn trang tiếp:

```jpql
SELECT o.id
FROM PurchaseOrder o
WHERE o.status = :status
  AND (
      o.createdAt < :lastCreatedAt
      OR (
          o.createdAt = :lastCreatedAt
          AND o.id < :lastId
      )
  )
ORDER BY o.createdAt DESC, o.id DESC
```

Áp:

```java
setMaxResults(pageSize + 1);
```

để xác định có thêm trang hay không.

### 19.2. Vì sao phải có ID trong cursor?

Nếu nhiều orders cùng `createdAt`, chỉ lưu timestamp sẽ bỏ qua hoặc lặp một số orders. Cặp `(createdAt, id)` tạo thứ tự xác định vì ID duy nhất.

Đoạn JPQL giả định `createdAt` khác null; nếu field nullable thì cần định nghĩa thứ tự NULL và logic cursor tương ứng.

### 19.3. Keyset không tự fetch collections

Sau khi lấy một trang IDs bằng keyset, vẫn tải lines ở bước tiếp theo:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id IN :ids
```

**Keyset thay thế cách chọn root IDs**, không thay quy tắc phải tải collection theo đúng trang.

### 19.4. Những giới hạn của keyset

- Không tiện nhảy tùy ý tới “trang 237”.
- API thường dùng next cursor thay vì pageIndex.
- Cần sort keys ổn định và index phù hợp.
- Nếu giá trị sort key bị thay đổi giữa các request, vẫn có thể có hiện tượng drift.
- Có thể không cần total count ở mỗi request, nhưng nếu cần tổng chính xác vẫn cần count query.

Keyset là một kỹ thuật hữu ích, không phải một cách giải quyết tất cả vấn đề nhất quán dữ liệu.

## 20. Tách việc phân trang collection con khỏi phân trang cha

Một use case khác:

> Trang danh sách 20 orders, mỗi order chỉ hiển thị **hai dòng sản phẩm đầu tiên**, và có nút “Xem thêm”.

Nếu fetch toàn bộ lines của 20 orders, một order có 10.000 lines vẫn khiến service phải tải tất cả, dù UI chỉ cần hai.

### 20.1. Hai chiều phân trang khác nhau

- **Pagination theo cha:** chọn 20 orders.
- **Pagination theo con:** chọn 2 lines cho mỗi order.

Hai bài toán này không phải một `LIMIT 40` trên joined rows.

### 20.2. Cách đơn giản cho API

Có thể:

1. Trả DTO của 20 orders, kèm `lineCount`.
2. Khi user mở một order, gọi endpoint `GET /orders/{id}/lines?page=...`.
3. Phân trang `OrderLine` trực tiếp theo `orderId` và thứ tự ổn định.

Truy vấn child:

```jpql
SELECT l
FROM OrderLine l
WHERE l.order.id = :orderId
ORDER BY l.id ASC
```

Khi đó:

```java
setFirstResult(childOffset);
setMaxResults(childPageSize);
```

áp lên **OrderLine roots**, không phải một fetch join collection của PurchaseOrder.

### 20.3. Nếu cần top-N children cho mỗi parent trong một lần

Một SQL dùng window function như `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY ...)` có thể lấy N dòng con đầu cho mỗi order. Nhưng cú pháp và performance tùy DBMS, nhiều khi dùng native query/DTO mapping.

Không cố dùng một `JOIN FETCH` có `LIMIT` chung để đạt “2 lines cho mỗi order”. Nó không diễn đạt phân trang theo từng nhóm con.

## 21. Batch fetching và subselect fetching

Nếu ứng dụng chọn một trang PurchaseOrder mà không fetch join lines, rồi lần lượt truy cập lines, có thể gặp N+1:

```text
1 query lấy 20 orders
20 queries lấy lines
```

Một số provider có khả năng:

- **Batch fetching:** gom nhiều collection owner keys vào một số truy vấn.
- **Subselect fetching:** tải collection cho một nhóm entities dựa trên tập được chọn trước.
- **Second-level cache:** tránh một số lần đọc database nếu dữ liệu đã cache.

Ví dụ Hibernate-specific:

```java
@org.hibernate.annotations.BatchSize(size = 32)
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Đây không phải annotation Jakarta Persistence chuẩn. Nó có thể giảm N+1 với provider hỗ trợ, nhưng:

1. Cần đo SQL để xác nhận.
2. Không thay thế thiết kế DTO theo use case.
3. Không bảo đảm đúng batch size/truy vấn trên mọi cấu hình.
4. Không cho phép bỏ qua giới hạn pagination nếu query vẫn chứa collection fetch join.

### 21.1. Batch fetching vs hai bước

**Hai bước IDs + fetch join**:

- Rất rõ ràng về root page membership.
- Tải collection ngay cho những IDs được chọn.
- Có thể có joined rows lớn nếu một owner có collection rất lớn.

**Page roots + batch loading**:

- Có thể phát nhiều SQL, nhưng không nhất thiết lặp N lần.
- Có thể hữu ích khi provider tối ưu collection load.
- Cần bảo đảm collection thực sự được khởi tạo trong transaction trước khi trả DTO.

Không có một chiến lược tối ưu cho mọi tỷ lệ parent/child.

## 22. Tính toàn vẹn của collection và orphanRemoval

Khi đọc collection được fetch join, JPA thường đưa dữ liệu vào persistent collection được quản lý trong persistence context.

Nếu query tự lọc child và provider coi collection đã khởi tạo, có nguy cơ nhầm rằng **collection chỉ gồm những phần tử thỏa filter**.

Điều này đặc biệt đáng chú ý với:

```java
@OneToMany(
    mappedBy = "order",
    orphanRemoval = true,
    cascade = CascadeType.ALL
)
private List<OrderLine> lines;
```

Nếu ứng dụng dựa trên một collection bị lọc một phần rồi sửa/xóa phần tử, hậu quả có thể nghiêm trọng.

### 22.1. Chỉ lọc root bằng EXISTS

Nếu cần “orders có ít nhất một line quantity > 5”, dùng `EXISTS` để chọn root IDs. Sau đó fetch **toàn bộ** lines nếu domain muốn thao tác trên aggregate.

### 22.2. Dùng DTO cho dữ liệu con đã lọc

Nếu giao diện chỉ muốn các lines khớp điều kiện, có thể:

```jpql
SELECT l
FROM OrderLine l
WHERE l.order.id IN :ids
  AND l.quantity > :minQuantity
ORDER BY l.order.id, l.id
```

rồi group vào DTO. Đừng ghi tập con được lọc đó đè lên collection managed của entity.

### 22.3. Không nhầm fetch với cascade

- `fetch = LAZY/EAGER`: khi nào dữ liệu được tải.
- `CascadeType.ALL`: những lifecycle operations được lan truyền.
- `orphanRemoval = true`: xử lý child bị rời quan hệ sở hữu.

Chúng là các khái niệm khác nhau. Vấn đề phân trang fetch join là vấn đề **truy vấn và tải dữ liệu**, không phải một đặc tính của cascade.

## 23. Vì sao @OrderBy hoặc @OrderColumn không sửa pagination root?

`@OrderBy` trên collection:

```java
@OneToMany(mappedBy = "order")
@OrderBy("id ASC")
private List<OrderLine> lines;
```

chỉ điều khiển thứ tự các line.

`@OrderColumn` lưu vị trí phần tử của một `List` trong database:

```java
@OneToMany(mappedBy = "order")
@OrderColumn(name = "position_idx")
private List<OrderLine> lines;
```

Hai annotation này không biến collection thành một association đơn trị và không khiến SQL JOIN bớt nhân hàng.

**Thứ tự collection** khác với **thứ tự trang entity cha**.

### 23.1. Ví dụ hai thứ tự độc lập

```text
Order page:
  1003, 1002, 1001  (theo createdAt DESC)

Lines trong Order#1003:
  31, 32, 33        (theo @OrderBy/@OrderColumn)
```

Một query chọn root IDs cần bảo toàn thứ tự đầu. Một query tải lines cần bảo toàn thứ tự thứ hai, nếu UI cần. Không thể dùng một `ORDER BY l.id` đơn thuần để thay thế cả hai.

## 24. Phân trang khi có JOIN cho mục đích lọc nhưng không FETCH

Một câu query không có `FETCH` vẫn có thể bị nhân root rows nếu join collection:

```jpql
SELECT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity >= :minQuantity
ORDER BY o.createdAt DESC, o.id DESC
```

Nếu một order có 4 lines thỏa điều kiện, query có thể có nhiều result rows cho order đó.

Do đó:

> **Không chỉ `JOIN FETCH` mới cần chú ý tới phép nhân hàng.** Collection JOIN thông thường cũng có thể làm pagination root sai nếu không kiểm soát duplicates.

### 24.1. Khi nào DISTINCT có thể giúp?

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity >= :minQuantity
ORDER BY o.createdAt DESC, o.id DESC
```

Với query chỉ chọn root entity và không fetch child, SQL/provider có thể áp `DISTINCT` sao cho tập root trước LIMIT được khử trùng lặp đúng — tùy SQL shape, projection và ordering.

Nhưng đây vẫn là một query phức tạp hơn và countQuery cần được định nghĩa đúng. Cách `EXISTS` thường đơn giản hơn cho nhu cầu **lọc root theo sự tồn tại của child**, vì nó tránh nhân root ngay từ đầu.

### 24.2. Dùng EXISTS khi câu hỏi là có hay không

```jpql
SELECT o
FROM PurchaseOrder o
WHERE EXISTS (
    SELECT l.id
    FROM OrderLine l
    WHERE l.order = o
      AND l.quantity >= :minQuantity
)
ORDER BY o.createdAt DESC, o.id DESC
```

Query chính vẫn có một root candidate cho mỗi order, thích hợp hơn để phân trang.

## 25. Kiểm thử tính đúng đắn của trang

Để đánh giá một giải pháp pagination, không chỉ thử với mỗi order có một line. Cần dữ liệu có những hình dạng dễ bộc lộ lỗi.

| Trường hợp | Mục tiêu |
| --- | --- |
| Order có 0 lines | LEFT JOIN vẫn giữ order trong trang. |
| Order có 1 line | Trường hợp cơ sở. |
| Order có 30 lines, pageSize 10 | Không để một order chiếm cả page SQL rows. |
| Hai orders cùng createdAt | Tie-breaker ID tạo thứ tự xác định. |
| 5 orders, pageSize 3 | Page 0 có 3 roots; page 1 có 2 roots. |
| Order có nhiều lines thỏa child filter | Không đếm root nhiều lần. |
| Hai collection lines/tags | Không vô tình tạo tích số hàng lớn. |
| Result page ngoài phạm vi | Content rỗng, metadata total hợp lệ. |
| Child được thêm giữa hai queries | Chính sách consistency được xác định. |
| Order bị xóa giữa hai queries | Xử lý missing ID, không âm thầm trả sai contract. |
| Bộ lọc có/không có child | Count và page ID dùng cùng predicates. |
| IN list rỗng | Không tạo SQL `IN ()` không portable. |

### 25.1. Các bất biến của kết quả trang

Với page size `N` và tập dữ liệu ổn định, nên có những tính chất:

1. `content.size() <= N`.
2. Mỗi root ID xuất hiện nhiều nhất một lần trong content.
3. Content IDs theo đúng `ORDER BY` đã chọn.
4. `totalElements` đếm root entities, không đếm child rows.
5. Các roots thuộc page đúng theo filter.
6. Nếu UI cần full collection, lines của mỗi root là **đầy đủ theo ảnh chụp dữ liệu**.
7. Trang không bị thay đổi kích thước vì một root có quá nhiều child rows.
8. Không có collection fetch query bị áp `setFirstResult`/`setMaxResults` ngoài ý muốn.

Đây là các **yêu cầu chất lượng của giải pháp nghiệp vụ**. Bài hiện tại trình bày cách thiết kế kiểm thử; không thực thi test trong bước viết tài liệu.

### 25.2. Kiểm tra SQL thực tế

Có thể bật SQL logging/metrics của provider để quan sát:

- Query ID có LIMIT/OFFSET hay cú pháp tương ứng không?
- Query fetch có vô tình mang LIMIT/OFFSET không?
- Có cảnh báo in-memory pagination không?
- Có thêm N+1 ngoài dự kiến không?
- Tổng số SQL rows gần đúng là bao nhiêu?
- Khi pageSize tăng, heap và latency thay đổi thế nào?

Không lấy số lượng entities trả về trong Java làm phép đo duy nhất.

### 25.3. Hibernate-specific fail fast

Trong môi trường Hibernate, có thể bật:

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

rồi chạy integration tests để phát hiện sớm repository method nguy hiểm. Đây là biện pháp phòng vệ provider-specific, không thay cho các tests về số lượng roots và collections.

## 26. Các sai lầm thường gặp

### Lỗi 1 — Tin rằng setMaxResults giới hạn đúng số root với collection fetch join

```java
query.setMaxResults(20);
```

khi query dùng `LEFT JOIN FETCH o.lines` không bảo đảm nhận đúng 20 orders theo mong muốn.

**Cách tránh:** Page root IDs trước, fetch lines sau không paging.

### Lỗi 2 — Nghĩ DISTINCT đã giải quyết mọi vấn đề

`SELECT DISTINCT o` có thể loại duplicate root results, nhưng không tự sửa phạm vi SQL LIMIT/OFFSET trên rows của join.

### Lỗi 3 — Không phân biệt SQL rows và entity roots

Một order có 100 lines có thể sinh 100 SQL rows. Không lấy số SQL rows làm số orders.

### Lỗi 4 — Bỏ qua cảnh báo in-memory pagination

Provider có thể đưa về rất nhiều rows rồi mới cắt content, gây áp lực RAM/latency. Cần sửa query shape thay vì chỉ im log.

### Lỗi 5 — Dùng INNER JOIN FETCH khi collection có thể rỗng

Order không có lines bị loại khỏi kết quả fetch.

**Cách tránh:** `LEFT JOIN FETCH` khi cần giữ root rỗng.

### Lỗi 6 — Dùng Pageable cho query fetch collection ở bước 2

Trang đã được chọn bằng IDs; query fetch không cần và không nên có limit/offset.

### Lỗi 7 — Giả định IN giữ thứ tự IDs

`WHERE id IN :ids` không bảo đảm output theo thứ tự Java List.

**Cách tránh:** Reorder trong Java theo IDs bước 1 hoặc dùng `ORDER BY` tương ứng.

### Lỗi 8 — Sort chỉ theo timestamp không duy nhất

Nếu nhiều orders có cùng `createdAt`, các page có thể thiếu ổn định ngay cả khi không có join.

**Cách tránh:** Thêm `id` làm tie-breaker.

### Lỗi 9 — COUNT joined rows thay cho COUNT root

`COUNT(o)` trên `JOIN o.lines` có thể đếm một order nhiều lần.

**Cách tránh:** `COUNT(DISTINCT o.id)` hoặc `COUNT(o)` với `EXISTS`.

### Lỗi 10 — Đưa JOIN FETCH vào countQuery

Aggregate count không cần tải collection, và dạng fetch join có thể không hợp lệ.

### Lỗi 11 — Bước 1 lọc child, bước 2 chỉ fetch những child khớp

Nếu UI muốn full lines, fetched collection có thể bị thiếu. Tách **root predicate** khỏi **child projection**.

### Lỗi 12 — Ghép nhiều collections vào một JOIN FETCH

Có thể tạo tích số hàng và gặp hạn chế provider.

**Cách tránh:** Query riêng các collections hoặc DTO grouping.

### Lỗi 13 — Nghĩ @EntityGraph tự động sửa phân trang

Entity graph yêu cầu fetch; provider vẫn có thể dùng collection join hoặc load strategy khác. Phải quan sát SQL.

### Lỗi 14 — Chuyển mọi OneToMany sang EAGER

EAGER tĩnh có thể khiến mọi use case tải collection, tăng chi phí và không giải quyết đúng yêu cầu phân trang.

### Lỗi 15 — Trả entity managed trực tiếp ra JSON

Serializer có thể truy cập lazy collections ngoài transaction hoặc phát thêm SQL không kiểm soát.

**Cách tránh:** Map DTO trong service theo fetch plan đã xác định.

### Lỗi 16 — Sửa persistent collection chỉ để hiện tập con kết quả

Nếu entity managed và có `orphanRemoval`/cascade, thay collection có thể dẫn tới DML không mong muốn.

**Cách tránh:** Dùng DTO cho dữ liệu con được lọc.

### Lỗi 17 — Dùng transaction nhưng không xác định isolation

Hai query trong cùng transaction chưa chắc thấy snapshot giống nhau, tùy DBMS/isolation.

### Lỗi 18 — Dùng offset lớn mà không đo hiệu năng

OFFSET sâu có thể tốn tài nguyên. Cân nhắc keyset pagination nếu use case phù hợp.

### Lỗi 19 — Nghĩ keyset pagination tự tải collection an toàn

Keyset chọn IDs; vẫn cần tải collection cho IDs đó bằng query thích hợp.

### Lỗi 20 — Chỉ test đơn có một line

Với một line mỗi order, joined rows trông như 1:1 và che giấu vấn đề. Phải test dữ liệu lệch, có collection rỗng và collection rất lớn.

## 27. Bài tập thực hành

### Bài 1 — Đếm số SQL rows

Có bốn orders với số lines là 3, 0, 2, 1. Một `LEFT JOIN` trên lines trả bao nhiêu hàng nếu không có điều kiện khác?

**Đáp án:** `3 + 1 + 2 + 1 = 7` hàng. Order có zero lines vẫn tạo một hàng với phía line null.

### Bài 2 — LIMIT 3 đúng số orders?

Một order đầu tiên có 5 lines. SQL join có `LIMIT 3`.

**Đáp án:** Có thể chỉ nhận ba rows của cùng order đầu tiên, không phải ba orders. Với fetch join collection, không có bảo đảm phân trang root đúng theo ý định.

### Bài 3 — DISTINCT giúp gì?

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

**Đáp án:** Diễn đạt ý định không trả duplicate root entities, nhưng không biến nhiều joined rows thành một row mà vẫn giữ toàn bộ children để `LIMIT` đúng root page.

### Bài 4 — Chọn IDs cho trang thứ hai

Có năm orders, pageSize 3, pageIndex tính từ 0.

**Đáp án:** Bước 1 chọn pageIndex 1 → `offset = 3`, `maxResults = 3`; kết quả lý thuyết là #1004, #1005.

### Bài 5 — Fetch orders không có lines

Một order trong page IDs không có lines. Query bước 2 nên dùng JOIN hay LEFT JOIN FETCH?

**Đáp án:** `LEFT JOIN FETCH` để giữ order đó trong kết quả.

### Bài 6 — Bước 2 bị xáo thứ tự

IDs là `[1001,1002,1003]` nhưng fetch query trả `[1003,1001,1002]`.

**Đáp án:** Dùng Map theo ID rồi duyệt List IDs để dựng output theo thứ tự ban đầu. `IN` không phải ORDER BY.

### Bài 7 — COUNT có đúng không?

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
JOIN o.lines l
WHERE l.quantity > 2
```

Một order có ba lines thỏa điều kiện.

**Đáp án:** Order đó có thể được đếm ba lần. Dùng `COUNT(DISTINCT o.id)` hoặc `EXISTS` nếu cần đếm root orders.

### Bài 8 — Tìm orders có một line BOOK

Giao diện cần **mọi line** của những order có ít nhất một BOOK line.

**Đáp án:** Dùng `EXISTS` ở query chọn root IDs, sau đó fetch toàn bộ lines cho tập IDs. Đừng chỉ fetch những line BOOK nếu collection đầy đủ là yêu cầu.

### Bài 9 — Nhiều collection

Một order có 20 lines và 10 tags. Query fetch join hai collections có thể có bao nhiêu rows cho order đó?

**Đáp án:** Khoảng `20 × 10 = 200` joined rows, tùy dữ liệu và join conditions.

### Bài 10 — Entity graph và Page

Spring Data repository trả `Page<PurchaseOrder>` và đặt `@EntityGraph(attributePaths="lines")`.

**Đáp án:** Không tự giả định an toàn; kiểm tra fetch strategy và sửa thành page root IDs rồi fetch collection nếu cần.

### Bài 11 — Chọn DTO

Danh sách chỉ cần ID, trạng thái, số lines.

**Đáp án:** Có thể dùng scalar/DTO projection với `COUNT`/`GROUP BY` hoặc count logic phù hợp. Không cần fetch toàn bộ entity lines.

### Bài 12 — Đồng thời xóa order

Bước 1 lấy IDs có Order#1002; trước bước 2, transaction khác xóa order đó.

**Đáp án:** Query 2 có thể trả thiếu order. Thiết kế snapshot/transaction policy hoặc retry/error rõ, không silently khẳng định page đầy đủ.

### Bài 13 — Keyset pagination

Sort theo `createdAt DESC, id DESC`. Cursor là `(2026-11-15T09:00, 1003)`.

**Đáp án:** Chọn tiếp những order có `createdAt < cursorTime` hoặc cùng timestamp và `id < cursorId`, rồi `ORDER BY createdAt DESC, id DESC`. Fetch lines cho IDs đã chọn ở bước tiếp theo.

### Bài 14 — Lazy N+1

Trang 20 orders đã tải xong; một vòng lặp truy cập `o.getLines()` làm phát nhiều SQL.

**Đáp án:** Batch fetching/provider optimization, fetch lines theo tập IDs hoặc query child riêng. Không chuyển mọi collections sang EAGER theo phản xạ.

### Bài 15 — Kiểm tra page metadata

`totalElements` đang bằng số lines, trong khi content là orders.

**Đáp án:** Count query sai phạm vi; nó phải đếm PurchaseOrder roots theo cùng filter, không đếm các rows của join.

## 28. Câu hỏi tự kiểm tra

**1. Vì sao một `JOIN FETCH o.lines` làm pagination root khó bảo đảm?**

Vì một entity cha có thể tạo nhiều SQL rows, trong khi LIMIT/OFFSET thường áp cho rows chứ không tự hiểu nhóm cha.

**2. Có thể dựa vào `setMaxResults(20)` với collection fetch join để bảo đảm đúng 20 root entities không?**

Không. JPA không bảo đảm kết quả của tổ hợp này.

**3. DISTINCT có sửa được bản chất nhân hàng khi fetch collection không?**

Không. Nó giúp deduplicate roots ở mức kết quả nhưng không tự làm SQL pagination theo root.

**4. Provider có thể làm gì khi gặp collection fetch pagination?**

Tùy provider/phiên bản: phân trang trong memory, cảnh báo, fail fast hoặc hành vi khác. Không nên phụ thuộc vào một cách xử lý không được bảo đảm.

**5. Hình dạng truy vấn hai bước an toàn là gì?**

Page root IDs không fetch collection; sau đó fetch collection cho đúng những IDs mà không đặt pagination lên query fetch.

**6. Vì sao cần `LEFT JOIN FETCH` khi collection có thể rỗng?**

Để không loại entity cha không có child.

**7. Vì sao query `WHERE id IN :ids` không đủ để giữ thứ tự trang?**

Vì `IN` là membership, không phải ordering.

**8. Vì sao `ORDER BY createdAt DESC` chưa đủ ổn định?**

Vì timestamp có thể trùng; thêm khóa duy nhất như `id DESC`.

**9. Count query nên đếm gì?**

Đếm root entities thỏa filter, không phải joined child rows.

**10. Có nên dùng `JOIN FETCH` trong `COUNT` không?**

Không; count không cần tải collection và sự kết hợp có thể không hợp lệ.

**11. Lọc root theo child có thể dùng phương pháp nào tránh nhân root?**

`EXISTS` correlated subquery.

**12. Nếu UI cần tất cả lines của một order thỏa điều kiện child, có nên filter fetch join theo điều kiện đó không?**

Không nên; chọn root bằng EXISTS rồi fetch full collection.

**13. Nếu chỉ cần hai child đầu mỗi order, một `LIMIT 40` trên join của 20 orders có giải quyết không?**

Không. Phân trang theo nhóm child là bài toán khác, cần query/DTO riêng.

**14. Entity graph có loại bỏ mọi rủi ro collection fetch pagination không?**

Không. Nó mô tả fetch requirements, provider vẫn quyết định cách tải.

**15. To-one fetch join có nhất thiết nhân root rows như collection fetch join không?**

Không. Với cardinality đơn trị đúng, nó thường không nhân rows theo số child; nhưng các join khác vẫn phải xét.

**16. Vì sao dùng DTO projection cho danh sách thường phù hợp?**

Vì giảm dữ liệu tải và tránh khởi tạo collection entity khi UI chỉ cần vài scalar fields.

**17. Hai query trong cùng transaction READ COMMITTED có chắc cùng snapshot không?**

Không nhất thiết, tùy DBMS/isolation.

**18. Keyset pagination thay thế bước nào của quy trình?**

Thay cách chọn root IDs của trang; không thay cách tải collection cho những IDs đó.

**19. Một order có 100 lines nhưng pageSize 10 có ý nghĩa gì?**

Page size 10 giới hạn **số orders** nếu đó là contract API, không phải chỉ 10 SQL rows của join.

**20. Cần quan sát những gì ngoài `content.size()`?**

SQL shape, số rows, SQL count, warning in-memory pagination, heap usage, latency và tính đầy đủ của collections.

**21. Vì sao không dùng một JOIN FETCH để tải cả lines và tags vô điều kiện?**

Vì có thể tạo tích số hàng lớn và gặp hạn chế provider.

**22. Một collection persistent bị gán tập con của dữ liệu trình bày có thể nguy hiểm vì sao?**

Vì có thể gây thay đổi quan hệ/DML khi flush, nhất là với orphanRemoval/cascade; nên dùng DTO.

**23. Có thể chọn root IDs bằng query không có ORDER BY không?**

Không nên nếu cần phân trang ổn định.

**24. Vì sao cần test trường hợp order không có child?**

Để phát hiện query dùng inner join làm mất root và sai kích thước trang.

**25. Kết luận quan trọng nhất của bài là gì?**

**Phân trang root trước, tải collection sau; không giả định collection fetch join kết hợp LIMIT/OFFSET sẽ tự phân trang đúng entity cha.**

## 29. Ghi nhớ cuối bài

Trong ứng dụng JPA, **fetch join collection** và **pagination theo entity cha** là hai yêu cầu cần được phối hợp có chủ đích.

Với:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
ORDER BY o.createdAt DESC
```

kèm `setFirstResult()/setMaxResults()`, JPA **không cung cấp bảo đảm phân trang root chính xác và hiệu quả theo kỳ vọng**. Một order có nhiều lines có thể tạo nhiều SQL rows; provider có thể phân trang trong memory hoặc xử lý khác theo phiên bản. `DISTINCT` không tự giải quyết vấn đề.

Khi cần trang cha cùng đầy đủ collection, hãy ưu tiên:

1. **Query IDs của entity cha** với filter đúng và `ORDER BY` xác định, có tie-breaker duy nhất.
2. **Áp pagination trên query ID**, không trên query fetch collection.
3. **Fetch associations cho đúng IDs** bằng `LEFT JOIN FETCH` không có limit/offset, hoặc bằng những child queries riêng.
4. **Khôi phục thứ tự trang** theo danh sách ID đã chọn.
5. **Đếm tổng root entities bằng count query riêng** với cùng bộ lọc.
6. **Map DTO trong đơn vị công việc** để không để serialization kích hoạt lazy loading.
7. **Xác định consistency policy** cho dữ liệu thay đổi giữa count, ID query và fetch query.
8. **Đo SQL rows, latency, memory và cảnh báo provider** thay vì chỉ nhìn số entities được trả.

Nếu UI chỉ cần scalar fields, dùng **DTO projection** thay vì tải collection. Nếu cần phân trang rất sâu hoặc dữ liệu biến động liên tục, cân nhắc **keyset pagination** ở bước chọn root IDs. Nếu cần nhiều collections, cân nhắc **query riêng/batch fetching** để tránh tích số hàng.

**Không đánh đồng “query cuối cùng trả đúng số phần tử Java” với “database đã phân trang đúng phạm vi entity cha”.** Thiết kế phân trang tốt phải đồng thời bảo đảm membership của trang, thứ tự ổn định, dữ liệu collection đầy đủ theo use case và chi phí truy vấn chấp nhận được.
