# Tránh tải nhiều tập hợp gây nhân số hàng kết quả

Trong JPA, việc tối ưu kế hoạch tải dữ liệu (*fetch plan*) không đơn giản là thêm càng nhiều `JOIN FETCH` càng tốt. Một truy vấn tải một entity cha cùng **hai hoặc nhiều quan hệ tập hợp** có thể sinh một lượng hàng SQL lớn hơn rất nhiều so với số entity thực sự cần dùng. Hiện tượng này thường được gọi là **row multiplication**, **Cartesian product ở phạm vi từng root** hoặc **Cartesian explosion**.

Ví dụ, một đơn hàng có 8 dòng hàng và 5 lần thanh toán. Khi dùng hai `LEFT JOIN FETCH` trong cùng một query:

```sql
select distinct o
from PurchaseOrder o
left join fetch o.lines
left join fetch o.payments
where o.id = :id
```

database có thể trả **8 × 5 = 40 hàng SQL** để biểu diễn **1 đơn hàng, 8 dòng hàng và 5 thanh toán**. Nếu cùng một query lấy 1.000 đơn hàng có cấu trúc tương tự, tổng dữ liệu trung gian có thể đạt khoảng **40.000 hàng** dù số child entities thực chỉ khoảng 13.000 cộng 1.000 parent. Khi các tập hợp lớn hơn hoặc xuất hiện tập hợp thứ ba, số hàng có thể tăng rất nhanh.

Với Hibernate, vấn đề còn có biểu hiện khác: khi đồng thời fetch nhiều collection được ánh xạ theo ngữ nghĩa **bag**, provider có thể từ chối truy vấn bằng `MultipleBagFetchException`. Đổi `List` sang `Set` chỉ để tránh exception không làm biến mất phép nhân ở SQL; nó có thể chỉ chuyển từ **lỗi nhìn thấy ngay** sang **bùng nổ dữ liệu âm thầm**.

Bài học này trình bày cách nhận diện vấn đề, dự đoán chi phí theo số phần tử, phân biệt bag/list/set, hiểu giới hạn của `DISTINCT`, chọn kế hoạch tải nhiều truy vấn có kiểm soát, kết hợp phân trang an toàn, batch/subselect fetching, DTO projection và kiểm tra hành vi thực tế của JPA provider. Nội dung thuộc phần **Kế hoạch tải** của chủ đề **Data Persistence Relational Access ORM JPA**.

## 1. Hai vấn đề tưởng trái ngược: N+1 và nhân số hàng

Khi tối ưu JPA, ta thường gặp **N+1 query**:

```java
List<PurchaseOrder> orders = em.createQuery(
        "select o from PurchaseOrder o",
        PurchaseOrder.class)
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getLines().size());
}
```

Nếu `lines` được tải lazy và không có batch fetching, provider có thể thực hiện:

```text
1 query lấy danh sách orders
+ 1 query cho lines của order 1
+ 1 query cho lines của order 2
+ ...
+ 1 query cho lines của order N
```

Khi thấy nhiều câu SQL, một phản xạ thường gặp là đổi tất cả associations thành EAGER hoặc thêm tất cả vào `JOIN FETCH`:

```sql
select o
from PurchaseOrder o
left join fetch o.lines
left join fetch o.payments
```

Cách này có thể giảm số lần round-trip nhưng lại tạo vấn đề khác: **số SQL rows bị nhân**, băng thông tăng, CPU của database/JDBC/ORM tăng, RAM tăng và pagination trở nên khó tin cậy.

Mục tiêu tối ưu không phải:

> Luôn ít câu query nhất.

Mà là:

> **Tải đúng dữ liệu cần dùng, bằng số lần truy vấn hợp lý, với số hàng trung gian và kích thước object graph nằm trong giới hạn kiểm soát được.**

### 1.1. So sánh hai cực đoan

| Kế hoạch tải | Số statements | Số hàng/khối lượng trung gian | Rủi ro |
|---|---:|---|---|
| Lazy đơn lẻ, không batch | Có thể là N+1 hoặc 1+2N | Mỗi query thường nhỏ | Nhiều round-trips, latency cao |
| JOIN FETCH hai collection | Có thể một query | Kích thước gần tích của collection sizes | Cartesian explosion, bag exception, pagination lỗi |
| Root query + từng collection riêng | Thường vài query cố định | Gần tổng kích thước các collections | Cần quản lý persistence context và giới hạn IDs |
| Root query + batch fetching | Theo số batch | Gần tổng các phần tử được yêu cầu | Nhiều batch queries, phụ thuộc provider |
| DTO projection có chọn lọc | Tùy truy vấn | Chỉ cột/rows cần trả | Không có managed entity; cần map result |

Không có một cấu hình fetch nào tối ưu cho mọi endpoint. Kế hoạch tải phải dựa trên **use case**.

## 2. Mô hình dữ liệu xuyên suốt

Giả sử một đơn hàng có:

- Thông tin chung `PurchaseOrder`.
- Nhiều `OrderLine`.
- Nhiều `Payment`.

Sơ đồ:

```text
                     PurchaseOrder
                       id, code
                       /      \
                      /        \
                     v          v
                OrderLine     Payment
                quantity      amount
                productSku    method

                  1:N          1:N
```

### 2.1. Entity cha

```java
package example.shop;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "order_code", nullable = false)
    private String orderCode;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<Payment> payments = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getOrderCode() { return orderCode; }
    public Instant getCreatedAt() { return createdAt; }
    public List<OrderLine> getLines() { return lines; }
    public List<Payment> getPayments() { return payments; }
}
```

### 2.2. Entity dòng hàng

```java
package example.shop;

import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_sku", nullable = false)
    private String productSku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}

    public Long getId() { return id; }
    public String getProductSku() { return productSku; }
    public int getQuantity() { return quantity; }
}
```

### 2.3. Entity thanh toán

```java
package example.shop;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "payments")
public class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "amount", precision = 15, scale = 2,
            nullable = false)
    private BigDecimal amount;

    @Column(name = "method", nullable = false)
    private String method;

    protected Payment() {}

    public Long getId() { return id; }
    public BigDecimal getAmount() { return amount; }
    public String getMethod() { return method; }
}
```

Ở ví dụ này, hai `List` không có `@OrderColumn`. Với Hibernate, chúng thường có **bag semantics**: database rows không lưu vị trí phần tử để provider phân biệt những lần lặp của cùng một phần tử một cách đủ tin cậy khi đồng thời fetch hai bags.

**Chú ý:** `List` trong Java không tự đồng nghĩa mọi ánh xạ JPA `List` đều là indexed list. Cần xem mapping cụ thể, `@OrderColumn`, cấu hình provider và phiên bản.

## 3. Cơ chế nhân số hàng ở SQL

Giả sử:

```text
purchase_orders
ID = 10

order_lines
L1 -> order 10
L2 -> order 10
L3 -> order 10

payments
P1 -> order 10
P2 -> order 10
```

Một query SQL tương đương với hai fetch joins:

```sql
SELECT o.id, o.order_code,
       l.id AS line_id, l.product_sku,
       p.id AS payment_id, p.amount
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
LEFT JOIN payments p ON p.order_id = o.id
WHERE o.id = 10;
```

Kết quả:

| order_id | line_id | payment_id |
|---:|---|---|
| 10 | L1 | P1 |
| 10 | L1 | P2 |
| 10 | L2 | P1 |
| 10 | L2 | P2 |
| 10 | L3 | P1 |
| 10 | L3 | P2 |

**Một đơn, ba lines, hai payments → sáu hàng SQL.**

Lý do: `order_lines` và `payments` là hai tập hợp **độc lập cùng nối tới order**. Với mỗi line, database phải biểu diễn mọi payment tương ứng theo kết quả JOIN. Những cặp `(line, payment)` xuất hiện đầy đủ dù domain model không có quan hệ “mỗi line gắn với từng payment”.

### 3.1. Công thức cho hai LEFT JOIN

Đặt:

- `L_i`: số lines của order thứ i.
- `P_i`: số payments của order thứ i.

Với hai `LEFT JOIN` độc lập, đóng góp row của mỗi order thường là:

\[
R_i = \max(1,L_i)\times\max(1,P_i)
\]

Tổng số SQL rows:

\[
R_{\text{total}} = \sum_{i=1}^{N}
     \max(1,L_i)\times\max(1,P_i)
\]

Trong khi số entity records thực tế cần tải xấp xỉ:

\[
E_{\text{total}} = N + \sum_i L_i + \sum_i P_i
\]

Hai giá trị này tăng theo quy luật rất khác nhau.

Ví dụ 1.000 orders, mỗi order 8 lines và 5 payments:

```text
JOIN FETCH cùng lúc:
    1000 x 8 x 5 = 40.000 SQL rows

Các entity thực:
    1000 orders
    8000 order lines
    5000 payments
    tổng = 14.000 entities

Fetch collections riêng:
    root query:     khoảng 1000 rows
    lines query:    khoảng 8000 rows
    payments query: khoảng 5000 rows
```

Với dữ liệu lớn, sự chênh lệch không chỉ ở số rows: mỗi row JOIN còn lặp lại cột parent và các cột child của bên còn lại, khiến **số byte truyền qua network** tăng theo.

### 3.2. Nếu có collection thứ ba?

Một order có:

- 10 lines.
- 6 payments.
- 4 shipments.

Ba `LEFT JOIN` độc lập có thể tạo:

\[
10 \times 6 \times 4 = 240
\]

rows chỉ cho **một order**.

Tải riêng ba collections có số child rows `10 + 6 + 4 = 20`, cộng parent. Hiệu ứng “nhân nhiều lần” làm cho một truy vấn SQL duy nhất có thể đắt hơn nhiều truy vấn nhỏ.

### 3.3. Trường hợp collection rỗng

Với `LEFT JOIN`, một collection không có row vẫn giữ lại parent với giá trị child null. Ví dụ 5 lines và 0 payments:

```text
max(1,5) x max(1,0) = 5 SQL rows
```

Với `INNER JOIN` thay vì LEFT, parent **có thể bị loại hoàn toàn** khi một trong hai collection rỗng. Vì vậy cần phân biệt hai câu hỏi:

1. Có bị nhân số hàng khi JOIN không?
2. Có làm thay đổi tập parent được trả về do inner/outer join không?

Đây là hai vấn đề khác nhau.

## 4. Vì sao JPA vẫn có thể trả đúng một entity cha?

Trong persistence context, JPA áp dụng **identity map**: cùng một entity type và primary key trong một persistence context thường tương ứng với một managed entity instance.

Với sáu SQL rows nêu trên:

```text
Row 1: Order#10, Line#1, Payment#1
Row 2: Order#10, Line#1, Payment#2
Row 3: Order#10, Line#2, Payment#1
...
```

provider có thể nhận diện Order#10 và tái sử dụng một managed object thay vì tạo sáu `PurchaseOrder` độc lập. Khi vật liệu hóa collections, provider cũng phải phân biệt những child rows lặp lại do JOIN.

Nhưng điều này **không xóa chi phí hàng trung gian**:

- Database vẫn phải thực hiện JOIN.
- JDBC driver vẫn phải xử lý result set.
- Dữ liệu trùng lặp vẫn có thể được gửi qua network.
- ORM vẫn phải duyệt và giải mã hàng để nhận diện entities/collections.
- Bộ nhớ và CPU có thể tăng dù số parent objects cuối cùng nhỏ.

Vì thế:

> **Số Java objects trong kết quả không phản ánh trực tiếp chi phí SQL/JDBC để tạo ra chúng.**

### 4.1. Duplicated root reference khác duplicated database row

Một query `select o from PurchaseOrder o join o.lines l` có thể tạo nhiều result rows trỏ cùng parent; việc danh sách Java có lặp reference parent hay không phụ thuộc JPQL `DISTINCT`, loại query và hành vi phiên bản provider.

Hibernate 6 tự loại các root entity duplicates sinh ra bởi `join fetch` khi xây kết quả entity theo cơ chế của nó. Hibernate 5 và các provider khác có thể có hành vi/khuyến nghị khác. Nhưng **không phiên bản nào biến 40.000 SQL rows thành 1.000 rows chỉ bằng việc khử duplicate trong Java**.

## 5. `JOIN FETCH`: công cụ mạnh nhưng cần đúng phạm vi

JPQL `JOIN FETCH` yêu cầu tải association cùng root trong truy vấn:

```java
List<PurchaseOrder> orders = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.lines " +
        "where o.tenantId = :tenantId",
        PurchaseOrder.class)
    .setParameter("tenantId", tenantId)
    .getResultList();
```

Đây có thể là một kế hoạch phù hợp nếu:

- Số orders được giới hạn hợp lý.
- Mỗi order chỉ có số lines vừa phải.
- Use case thực sự cần lines ngay.
- Query không phân trang root theo cách gây mất tính đúng đắn.

Vấn đề xuất hiện khi bổ sung **nhiều to-many associations độc lập**:

```sql
select distinct o
from PurchaseOrder o
left join fetch o.lines
left join fetch o.payments
```

Người viết query đang yêu cầu database trả dữ liệu ở **độ hạt của các tổ hợp line × payment**, mặc dù domain cần hai tập hợp tách biệt.

### 5.1. To-one fetch không tạo phép nhân tương tự

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;
```

Query:

```sql
select o
from PurchaseOrder o
join fetch o.customer
```

thường vẫn có **một matching customer mỗi order**, nên không tạo phép nhân do cardinality to-many (dù có thể có chi phí về độ rộng row và join).

Khi muốn tải nhiều dữ liệu, chiến lược hay dùng là:

- **JOIN FETCH các to-one phù hợp**.
- **Tải các to-many collection theo lô hoặc truy vấn riêng**.

### 5.2. Một to-many JOIN có thể vẫn làm tăng số row

Ngay cả một `LEFT JOIN FETCH o.lines` vẫn tạo khoảng `max(1, L_i)` rows cho mỗi order. Đó thường là đánh đổi hợp lý khi cần lines và số lượng không lớn. Điểm nguy hiểm là **tích của nhiều tập hợp**, chứ không phải mọi to-many join đều bị cấm.

## 6. `DISTINCT` có giải quyết Cartesian explosion không?

Một phản ứng thường gặp:

```sql
select distinct o
from PurchaseOrder o
left join fetch o.lines
left join fetch o.payments
```

`DISTINCT` có thể giúp tạo danh sách **root entities không lặp** theo semantics JPQL, nhưng không phải giải pháp cho chi phí nhân hàng.

Trong kết quả SQL:

```text
Order#10, Line#1, Payment#1
Order#10, Line#1, Payment#2
Order#10, Line#2, Payment#1
Order#10, Line#2, Payment#2
```

mỗi row thực sự có tổ hợp columns khác nhau. Kể cả database thực hiện `SELECT DISTINCT` trên toàn projection, nó **không thể loại** các rows khác nhau do Line/Payment IDs.

### 6.1. Hai cấp độ DISTINCT

| Cấp | Ý nghĩa | Có giảm phép nhân giữa collections? |
|---|---|---|
| SQL `DISTINCT` | Loại các rows trùng hoàn toàn theo projection SQL | Không loại được các tổ hợp child khác nhau |
| JPQL `select distinct o` | Yêu cầu kết quả root entity không lặp | Không ngăn SQL row multiplication xảy ra |
| Provider de-dup lúc hydrate | Tái sử dụng entity identity, có thể lọc root duplicates | Không làm giảm số rows DB đã trả |

Một số provider/version có cách đẩy `DISTINCT` xuống SQL khác nhau. Không nên dựa vào một optimizer hint hoặc property provider-specific để “chữa” bản chất multiplicative join.

### 6.2. `DISTINCT` vẫn có tác dụng

Nó phù hợp khi query có JOIN collection nhưng muốn root list không trùng. Điều cần tránh là **đánh đồng việc root list hết duplicate với việc SQL query đã trở nên rẻ**.

## 7. Hibernate `MultipleBagFetchException` là gì?

Với mapping ở phần đầu:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;

@OneToMany(mappedBy = "order")
private List<Payment> payments;
```

nếu Hibernate coi cả hai là **bags**, query:

```java
em.createQuery(
    "select o from PurchaseOrder o " +
    "left join fetch o.lines " +
    "left join fetch o.payments",
    PurchaseOrder.class).getResultList();
```

có thể thất bại với lỗi:

```text
org.hibernate.loader.MultipleBagFetchException:
cannot simultaneously fetch multiple bags
```

Thông điệp cụ thể và thời điểm ném exception có thể khác theo phiên bản Hibernate. Đây là **hạn chế của Hibernate đối với việc đồng thời fetch nhiều bags**, không phải một exception quy định bởi Jakarta Persistence cho mọi provider.

### 7.1. Bag là gì?

Trong ngữ nghĩa collection của Hibernate, một **bag** cho phép phần tử lặp và không có index persistent xác định để phân biệt các vị trí như indexed list.

Ví dụ:

```text
Bag:
    [A, A, B]  (duplicates có thể có)
    không có order index được lưu như một phần mapping

Indexed List:
    position 0 -> A
    position 1 -> A
    position 2 -> B

Set:
    {A, B}     (unique theo equality semantics)
```

Khi JOIN hai bags, một child có thể xuất hiện lặp lại nhiều lần trong result rows vì tổ hợp với bag bên kia. Nếu không có index/identity mapping đầy đủ để nhận diện một lần xuất hiện thật và một lần xuất hiện do JOIN, việc lắp hai bag collections từ result set trở nên mơ hồ.

### 7.2. `List` không tự động là indexed list

Trong nhiều mapping Hibernate, `List` không có `@OrderColumn` thường được hiểu theo bag semantics, mặc dù Java `List` có thứ tự iteration.

`@OrderBy`:

```java
@OrderBy("id ASC")
private List<OrderLine> lines;
```

chỉ mô tả **thứ tự sắp xếp** theo attribute/column khi tải; nó không nhất thiết tạo một **position column** làm cho bag trở thành indexed list đối với bài toán multiple bag fetching.

Với `@OrderColumn`:

```java
@OrderColumn(name = "line_position")
private List<OrderLine> lines;
```

provider có thể quản lý vị trí phần tử trong database, khiến ngữ nghĩa khác bag. Nhưng đây là **thay đổi mapping/schema và DML behavior**: insert/xóa/reorder có thể phát sinh ghi vị trí, constraint và migration.

**Không thêm `@OrderColumn` chỉ để tắt một exception**, nếu domain không thực sự cần persistent list ordering.

### 7.3. Bag exception không phải thước đo duy nhất

Một query có hai collections kiểu Set có thể **không ném `MultipleBagFetchException`** mà vẫn tạo phép nhân hàng nghiêm trọng.

Không nên kết luận:

> Không còn exception nên kế hoạch tải đã tối ưu.

Cần đo SQL rows, bytes, thời gian, memory và số entity/collection elements thực.

## 8. Có nên đổi `List` sang `Set` để tránh lỗi?

Một mẹo thường được chia sẻ là:

```java
@OneToMany(mappedBy = "order")
private Set<OrderLine> lines = new HashSet<>();

@OneToMany(mappedBy = "order")
private Set<Payment> payments = new HashSet<>();
```

Với Hibernate, hai Set có thể được fetch trong cùng query mà không gặp cùng loại lỗi **multiple bag**. Nhưng SQL vẫn có thể trả `L_i × P_i` rows.

### 8.1. `Set` thay đổi ngữ nghĩa domain

`Set` có những đặc điểm:

- Không cho phép trùng phần tử theo `equals()/hashCode()`.
- Không có ordering theo vị trí như `List`.
- Mapping collection và Java iteration semantics có thể khác.
- Với entity có ID sinh sau persist, cách cài đặt equality/hashCode cần được thiết kế cẩn thận.

Nếu business cho phép nhiều phần tử giống nhau, `Set` có thể không phù hợp. Đổi collection type để che lỗi SQL mà không xét domain có thể tạo bug mất phần tử logic hoặc thay đổi API.

### 8.2. `Set` vẫn tiêu thụ CPU/memory để khử trùng

Giả sử `OrderLine#1` xuất hiện 5 lần trong SQL rows. Provider phải nhận diện và xử lý lặp đó khi dựng Set. Chi phí hydrate vẫn tồn tại.

### 8.3. Quy tắc lựa chọn

Chọn `List` khi nghiệp vụ cần thứ tự/lặp theo list semantics; chọn `Set` khi nghiệp vụ thực sự cần tập unique. **Cách chữa fetch plan là thay đổi chiến lược truy vấn**, không phải thay đổi domain collection tùy tiện.

## 9. `FetchType.EAGER` không phải cách khắc phục

Trong JPA:

```java
@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
```

không có nghĩa “luôn lấy bằng một JOIN nhanh”. EAGER là yêu cầu association phải được tải sẵn theo cơ chế provider chọn; provider có thể dùng JOIN, SELECT phụ hoặc tổ hợp. EAGER làm giảm quyền quyết định của từng use case.

Trong thực tế, global EAGER trên nhiều to-many associations có thể:

- Tăng tải cho những endpoint chỉ cần parent.
- Tạo N+1 hoặc truy vấn thừa, tùy provider.
- Kéo vào nhiều collection không cần thiết.
- Tạo multiple bag exception hoặc row explosion khi kế hoạch tải gộp JOIN.

Mặc định cho `@OneToMany` và `@ManyToMany` là LAZY theo JPA; thường nên giữ **collection LAZY**, rồi quyết định tải theo từng truy vấn/use case.

**Cũng cần nhớ:** `FetchType.LAZY` không đồng nghĩa “không bao giờ tải”. Khi code truy cập collection trong transaction/session, provider vẫn phát query để tải.

## 10. Cách khắc phục phổ biến nhất: tách các collection fetches

Giả sử use case cần **một order cùng lines và payments**. Thay vì fetch cả hai trong một SQL JOIN:

```java
PurchaseOrder order = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.lines " +
        "where o.id = :id",
        PurchaseOrder.class)
    .setParameter("id", orderId)
    .getSingleResult();

em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.payments " +
        "where o.id = :id",
        PurchaseOrder.class)
    .setParameter("id", orderId)
    .getResultList();

// Truy cập sau khi cả hai query chạy:
order.getLines();
order.getPayments();
```

Hai query ở đây phải chạy trong **cùng persistence context**. JPA identity map giúp entity `PurchaseOrder` có cùng ID liên kết với cùng managed instance trong context đó; các collection được nạp bởi query tương ứng.

### 10.1. Vì sao hai query ít dữ liệu hơn?

Với 8 lines và 5 payments:

```text
Một query JOIN cả hai:
    8 x 5 = 40 rows

Hai query:
    query lines:    8 rows
    query payments: 5 rows
    tổng:           13 rows
```

Chi phí có thêm một round-trip nhưng giảm số hàng trung gian. Khi collections lớn, lợi ích có thể rất đáng kể.

### 10.2. Tính nhất quán giữa hai query

Vì là hai SQL statements:

- Có thể có concurrent update/insert/delete giữa lần tải lines và lần tải payments.
- Trong một transaction, isolation level quyết định chúng có cùng snapshot hay không.
- Nếu nghiệp vụ yêu cầu một snapshot nhất quán tuyệt đối, phải chọn transaction isolation/locking/workflow phù hợp với database.

Tách fetch queries không tự bảo đảm **transaction-level snapshot**, nhưng vẫn thường là chiến lược tốt để giảm row multiplication.

### 10.3. Không dùng hai EntityManager độc lập rồi mong collections tự hợp nhất

Nếu query 1 chạy qua `EntityManager` A, query 2 chạy qua `EntityManager` B, các parent objects không nhất thiết là cùng instance. Nếu A đã đóng, `order` có thể detached và không được B cập nhật collection của nó.

Để tận dụng identity map, chạy các truy vấn cho cùng entity graph trong **một persistence context và transaction phù hợp**.

## 11. Danh sách nhiều orders: tải theo tập IDs

Use case điển hình: màn hình cần 50 orders mới nhất, kèm lines và payments.

Kế hoạch:

1. Tìm **IDs của đúng 50 parents** theo điều kiện và thứ tự.
2. Fetch orders + lines bằng query giới hạn các IDs.
3. Fetch orders + payments bằng query khác giới hạn cùng IDs.
4. Ghép kết quả và **khôi phục thứ tự parents** như trang ID ban đầu.

Đây là mô hình **two-phase pagination + split collection fetching**. Có thể cần ba SQL statements (một ID query và hai collection queries).

### 11.1. Phase 1 — Chọn page root IDs

```java
List<Long> ids = em.createQuery(
        "select o.id from PurchaseOrder o " +
        "where o.tenantId = :tenantId " +
        "order by o.createdAt desc, o.id desc",
        Long.class)
    .setParameter("tenantId", tenantId)
    .setFirstResult(pageIndex * pageSize)
    .setMaxResults(pageSize)
    .getResultList();
```

Điểm quan trọng:

- Query ID không fetch collections nên pagination áp dụng ở **độ hạt parent rows**.
- `ORDER BY createdAt DESC, id DESC` có tie-breaker để giảm bất định khi nhiều orders cùng timestamp.
- Cần validate `pageIndex`, `pageSize`, tránh tràn số phép nhân và đặt giới hạn tối đa cho một page.
- Với dataset rất lớn, keyset pagination có thể tốt hơn OFFSET; nguyên tắc vẫn là **chọn parent page trước**.

### 11.2. Phase 2 — Fetch collection thứ nhất

```java
if (ids.isEmpty()) {
    return List.of();
}

List<PurchaseOrder> orders = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.lines " +
        "where o.id in :ids",
        PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
```

Không dùng `setMaxResults(pageSize)` ở query đã `JOIN FETCH o.lines`. Giới hạn đã được áp dụng khi **chọn parent IDs**, không phải khi SQL rows bị nhân theo lines.

### 11.3. Phase 3 — Fetch collection thứ hai

```java
em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.payments " +
        "where o.id in :ids",
        PurchaseOrder.class)
    .setParameter("ids", ids)
    .getResultList();
```

Query này có thể trả lại parent objects đã có trong persistence context và nạp `payments` cho chúng.

### 11.4. Phase 4 — Khôi phục thứ tự của page IDs

SQL `IN (:ids)` **không bảo đảm rows sẽ xuất hiện theo thứ tự các phần tử của `ids`**.

Để tạo danh sách kết quả đúng thứ tự trang:

```java
Map<Long, PurchaseOrder> byId = orders.stream()
    .collect(Collectors.toMap(
        PurchaseOrder::getId,
        Function.identity()
    ));

List<PurchaseOrder> ordered = ids.stream()
    .map(byId::get)
    .filter(Objects::nonNull)
    .toList();
```

Cần import `java.util.*`, `java.util.function.Function` và `java.util.stream.Collectors`. Trong ví dụ, mỗi ID chỉ tương ứng một parent; do đã chọn `distinct o` nên collector không phải xử lý nhiều result entries trùng ID. Nếu có race khiến một order bị xóa sau phase 1, `byId` có thể thiếu ID; đoạn `filter(Objects::nonNull)` minh họa việc bỏ qua, nhưng production nên có **policy rõ ràng về page drift/empty rows**, thay vì luôn âm thầm bỏ.

### 11.5. Có bắt buộc dùng hai fetch query sau ID query?

Không. Tùy use case có thể:

- Phase 2 chỉ `select o from PurchaseOrder o where o.id in :ids` lấy parents.
- Dùng batch fetching lazy để nạp lines/payments khi cần.
- Fetch một collection bằng JOIN và để collection kia batch.

Mục tiêu không phải tuân thủ một số query cố định, mà là **giới hạn rows trung gian** và giữ nguyên độ hạt phân trang.

## 12. Ví dụ service hoàn chỉnh: chọn page IDs rồi fetch hai collections

Ví dụ dùng Spring và `@Transactional(readOnly = true)` để giữ cùng persistence context trong một service call. Việc thiết lập transaction chỉ mang tính minh họa; ứng dụng Jakarta EE hoặc resource-local JPA có thể quản lý theo cách khác.

```java
package example.shop;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class OrderReadService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public List<PurchaseOrder> findPageWithChildren(
            String tenantId, int pageIndex, int pageSize) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        if (pageIndex < 0 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid page");
        }

        long offset = (long) pageIndex * pageSize;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Page offset too large");
        }

        List<Long> ids = em.createQuery(
                "select o.id from PurchaseOrder o " +
                "where o.tenantId = :tenantId " +
                "order by o.createdAt desc, o.id desc",
                Long.class)
            .setParameter("tenantId", tenantId)
            .setFirstResult((int) offset)
            .setMaxResults(pageSize)
            .getResultList();

        if (ids.isEmpty()) {
            return List.of();
        }

        List<PurchaseOrder> roots = em.createQuery(
                "select distinct o from PurchaseOrder o " +
                "left join fetch o.lines " +
                "where o.id in :ids and o.tenantId = :tenantId",
                PurchaseOrder.class)
            .setParameter("ids", ids)
            .setParameter("tenantId", tenantId)
            .getResultList();

        em.createQuery(
                "select distinct o from PurchaseOrder o " +
                "left join fetch o.payments " +
                "where o.id in :ids and o.tenantId = :tenantId",
                PurchaseOrder.class)
            .setParameter("ids", ids)
            .setParameter("tenantId", tenantId)
            .getResultList();

        Map<Long, PurchaseOrder> byId = roots.stream()
            .collect(Collectors.toMap(
                PurchaseOrder::getId,
                Function.identity()
            ));

        return ids.stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .toList();
    }
}
```

### 12.1. Tại sao lặp tenant predicate ở hai fetch queries?

IDs đã được chọn theo tenant, nhưng việc thêm `o.tenantId = :tenantId` vào các truy vấn tiếp theo là một **defense-in-depth guard**. Ứng dụng nhiều tenant cần xác định tenant từ authenticated context, không chỉ tin giá trị do client cung cấp.

Đối với dữ liệu cần ràng buộc mạnh về visibility, phải có database/application authorization và kiểm tra concurrency phù hợp.

### 12.2. Vì sao không dùng `getSingleResult()` ở bước fetch?

Danh sách `ids` có thể chứa nhiều orders; `getResultList()` là đúng. Tên collection fetch queries nói rõ chúng trả **0..N root entities**. Truy vấn theo một ID duy nhất có thể dùng `getSingleResult()` nếu nghiệp vụ xác nhận tồn tại, nhưng cần xử lý no result.

### 12.3. Chuyện gì xảy ra nếu associations đã được khởi tạo?

Kế hoạch trên dựa vào **cùng EntityManager** và các collections chưa bị nạp theo một kế hoạch xung đột. Nếu application đã khởi tạo một collection với dữ liệu đã lọc, hoặc có stale cache/context, việc chạy một query fetch mới không nhất thiết “thay thế đúng” collection contents theo kỳ vọng. Nên tổ chức một transaction đọc riêng cho mỗi use case, hạn chế trộn nhiều kiểu graph fetch không nhất quán.

### 12.4. Có cần `DISTINCT`?

JPQL `distinct o` thể hiện mong muốn mỗi root một lần; hữu ích cho portability/dễ đọc. Hibernate 6 có thể tự khử parent duplicates từ fetch join, nhưng cú pháp `DISTINCT` **không xử lý chi phí SQL multiplication**. Ở đây chỉ có một to-many fetch mỗi query, nên không còn tích lines × payments.

## 13. Phân trang kết hợp collection fetch: bẫy lớn

Truy vấn:

```java
List<PurchaseOrder> page = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.lines " +
        "order by o.createdAt desc",
        PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

có rủi ro vì SQL JOIN có **nhiều rows cho một parent**. Nếu database áp `LIMIT 20` lên SQL rows, có thể chỉ nhận một phần lines của parent cuối trang và trả quá ít parent entities. Để giữ semantics của collection fetch, một số provider (ví dụ Hibernate trong các trường hợp phổ biến) có thể phải **đọc nhiều rows rồi phân trang trong memory**, tạo vấn đề hiệu năng.

### 13.1. Vì sao Hibernate có thể cảnh báo?

Một cảnh báo điển hình trên Hibernate liên quan:

```text
firstResult/maxResults specified with collection fetch
applying in memory
```

Hibernate còn có cấu hình:

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

để làm lộ vấn đề bằng lỗi thay vì silently pagination in memory trong những trường hợp phù hợp. Tên property và hành vi cụ thể phụ thuộc phiên bản Hibernate; đây là **Hibernate-specific**, không phải setting chuẩn của Jakarta Persistence.

### 13.2. `DISTINCT` không làm pagination an toàn hơn

`DISTINCT` có thể khử root duplicates trong result Java, nhưng database vẫn cần xử lý child rows để bảo toàn collection. Không nên thêm `DISTINCT` rồi coi `setMaxResults(20)` là bảo đảm DB chỉ đọc đúng dữ liệu của 20 parents.

### 13.3. Quy tắc

**Phân trang parent roots trước, sau đó fetch collections theo IDs.**

Query phase 1 không có collection fetch; phase 2/3 giới hạn bởi `WHERE o.id IN :ids` và không áp pagination vào fetch query.

## 14. OFFSET pagination và keyset pagination

Với số trang sâu, OFFSET có thể chậm:

```sql
select o.id
from PurchaseOrder o
order by o.createdAt desc, o.id desc
```

kèm `setFirstResult(100000)` có thể buộc database bỏ qua nhiều rows trước khi tới trang.

Keyset pagination dùng tuple sort của phần tử cuối trang trước:

```sql
select o.id
from PurchaseOrder o
where o.tenantId = :tenantId
  and (
      o.createdAt < :lastCreatedAt
      or (
          o.createdAt = :lastCreatedAt
          and o.id < :lastId
      )
  )
order by o.createdAt desc, o.id desc
```

Sau `setMaxResults(pageSize)`, ta vẫn có danh sách parent IDs để fetch collections riêng như phần trước.

### 14.1. Cần dùng toàn bộ sort key

Nếu sắp xếp `createdAt DESC, id DESC` nhưng chỉ dùng `WHERE id < :lastId`, keyset có thể bỏ sót hoặc lấy sai rows vì ID không nhất thiết tương ứng với createdAt.

### 14.2. Keyset không đóng băng dữ liệu

Concurrent inserts/updates có thể làm thứ tự thay đổi giữa các request. Nếu ứng dụng cần một snapshot cố định xuyên nhiều trang, phải thiết kế snapshot token, as-of time hoặc transaction/isolation riêng; một keyset predicate không tự bảo đảm tính bất biến của dữ liệu.

## 15. Batch fetching: giảm N+1 mà không nhân collections

Nếu không muốn viết hai fetch joins riêng, có thể giữ collections lazy và sử dụng **batch fetching**.

Ý tưởng:

```text
Tải 60 orders
    |
    +-- Khi truy cập lines của một order:
    |      SELECT lines WHERE order_id IN (60 IDs hoặc các nhóm)
    |
    +-- Khi truy cập payments:
           SELECT payments WHERE order_id IN (các nhóm)
```

Thay vì mỗi order một SELECT, provider có thể tải cùng loại collection cho nhiều owners theo một nhóm.

### 15.1. Hibernate `@BatchSize`

Ví dụ provider-specific:

```java
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines = new ArrayList<>();

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<Payment> payments = new ArrayList<>();
```

Trong một persistence context đã nạp 60 orders, khi code truy cập một collection lazy, Hibernate có thể gom nhiều owners và chạy các SQL `WHERE order_id IN (...)` để nạp collections theo batch. Với size 32, về trực giác có thể cần khoảng vài queries cho mỗi loại collection thay vì 60 queries, nhưng số lượng chính xác còn phụ thuộc cache, order of access, provider version và batching algorithm.

### 15.2. Cấu hình mặc định Hibernate

```properties
hibernate.default_batch_fetch_size=32
```

Đây là Hibernate-specific property để cấu hình batch fetch size mặc định cho lazy associations được hỗ trợ. Trong Spring Boot, cách khai báo đi qua property binding của Hibernate/JPA provider:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Không coi đây là một thuộc tính JPA portable hoặc một giá trị được khuyên dùng cho mọi workload.

### 15.3. Ưu điểm của batch fetching

- Giảm N+1 round-trips.
- Không cần kết hợp hai to-many collections trong cùng SQL.
- Giữ associations lazy: endpoint nào cần mới truy cập.
- Thường dễ tích hợp với pagination root.
- Có thể tái sử dụng cho nhiều use cases mà không cần viết fetch join riêng.

### 15.4. Trade-off

- Không phải “một SQL query cho mọi thứ”.
- Batch size quá lớn có thể tạo câu SQL nhiều parameters, áp lực query planning, memory và driver bind limits.
- Không đọc collections thì không cần fetch; nhưng nếu serialization tự động chạm vào chúng, vẫn có thể phát queries ngoài dự kiến.
- Hiệu quả phụ thuộc lúc khởi tạo association và số owners đang có trong persistence context.

**Batch fetching là cách kiểm soát N+1, không phải tính năng luôn nhanh hơn mọi split-query khác.** Đo trên workload thực tế.

## 16. Subselect fetching: một phương án Hibernate-specific

Hibernate có:

```java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines = new ArrayList<>();
```

Ý tưởng của `FetchMode.SUBSELECT`: khi lazy collection cần khởi tạo, provider có thể tải cùng loại collection cho nhiều parent entities từ một nhóm owners bằng **một truy vấn phụ** dựa trên selection context của parents.

### 16.1. Khi nào hữu ích?

- Đã tải một nhóm parents bằng một query phù hợp.
- Hầu hết các parents sẽ cần cùng loại collection.
- Dữ liệu ở group có kích thước hợp lý.
- Muốn tránh N individual selects.

### 16.2. Khi nào cần thận trọng?

- Parent selection ban đầu quá rộng.
- Chỉ một vài parents thật sự cần collections.
- Query có filter/scroll/pagination phức tạp.
- Nhiều entity classes/contexts có batch selection khác nhau.
- Provider có những chi tiết subselect fetching thay đổi theo phiên bản.

Không dùng `@Fetch(SUBSELECT)` như một công tắc mặc định áp lên mọi collection; nếu parent scope lớn, một subselect load có thể nạp nhiều child rows không cần thiết.

### 16.3. Batch vs subselect

| Tiêu chí | Batch fetching | Subselect fetching |
|---|---|---|
| Ý tưởng | Tải collections cho nhiều owners theo nhóm IDs | Tải collections của nhóm parents liên quan tới parent selection |
| SQL thường gặp | `WHERE parent_id IN (...)` | Một truy vấn với subselect/group selection |
| Điều chỉnh kích thước | `@BatchSize`/default size | Phụ thuộc tập parents |
| Phù hợp | Nhiều owners, khởi tạo theo lô | Tập parents xác định, phần lớn cần cùng collection |
| Rủi ro | Nhiều batches/bind parameters | Vô tình fetch tập quá rộng |
| Portability | Hibernate-specific nếu dùng các annotations/properties trên | Hibernate-specific |

## 17. Entity graphs có giúp tránh nhân hàng không?

JPA entity graph mô tả **những attributes cần tải** trong một fetch plan:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("lines");
graph.addAttributeNodes("payments");

List<PurchaseOrder> orders = em.createQuery(
        "select o from PurchaseOrder o " +
        "where o.tenantId = :tenantId",
        PurchaseOrder.class)
    .setParameter("tenantId", tenantId)
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getResultList();
```

Entity graph là công cụ hữu ích, nhưng **không bảo đảm provider sẽ tải mỗi collection qua SQL riêng**. Một provider có thể quyết định JOIN nhiều collections, dẫn đến row explosion hoặc multiple-bag restriction.

### 17.1. Entity graph nói “cần gì”, không luôn nói “lấy bằng SQL nào”

Phân biệt:

- **Fetch graph:** thuộc tính nào cần có sẵn theo yêu cầu của query.
- **Fetching strategy:** JOIN, SELECT, BATCH, SUBSELECT hoặc cách provider thực thi.
- **Result shape:** root entities/DTO được trả là gì.

Thêm cả `lines` và `payments` vào graph có thể **mở rộng lượng dữ liệu tải** nhưng không kiểm soát được bản chất nhân hàng nếu provider chọn một JOIN chung.

### 17.2. Cách dùng thận trọng

Với một màn hình chỉ cần:

```text
PurchaseOrder
    customer (to-one)
    lines (to-many)
```

graph chứa `customer` và `lines` có thể hợp lý. Với màn hình cần thêm `payments`, cân nhắc query riêng hoặc batch fetching thay vì mặc định thêm tất cả to-many vào graph.

### 17.3. `fetchgraph` và `loadgraph`

Hai hint Jakarta Persistence:

```java
"jakarta.persistence.fetchgraph"
"jakarta.persistence.loadgraph"
```

có semantics khác nhau về cách xử lý các attributes được/không được liệt kê cùng fetch defaults. Tuy nhiên, **cả hai không phải bộ tối ưu Cartesian-product tự động**; SQL strategy vẫn do provider quyết định.

## 18. Một collection fetch + một to-one fetch thường là tổ hợp tốt

Ví dụ domain:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
```

Query:

```sql
select distinct o
from PurchaseOrder o
join fetch o.customer
left join fetch o.lines
where o.id in :ids
```

To-one `customer` không làm nhân rows theo collection độc lập. Số rows vẫn gần số `lines`, không phải `lines × customers` vì mỗi order thường chỉ có một customer.

Nhưng cần lưu ý:

- Nếu to-one là optional và dùng `INNER JOIN`, những root không có association sẽ bị loại; có thể cần `LEFT JOIN FETCH`.
- Cột của customer làm row rộng hơn, gây overhead network nhất định.
- Một chain to-one sâu có thể tạo join rộng và khó đọc/duy trì.
- Nếu có to-many sâu bên dưới, số rows có thể tiếp tục tăng theo dữ liệu.

Không phải mọi fetch join đều xấu; **số collection branches độc lập** và cardinality của từng branch mới là điểm cảnh báo chính.

## 19. “Nested collection” và “sibling collections” khác nhau

Xét hai hình:

**Hai collections cùng cấp:**

```text
Order
 ├── lines    (5)
 └── payments (4)

5 × 4 = 20 combinations
```

**Collection lồng nhau:**

```text
Order
 └── lines (5)
       └── adjustments (mỗi line 2)

Tổng adjustment rows ~ 5 × 2 = 10
```

Với nested chain `Order → lines → adjustments`, rows tương ứng với mối quan hệ cha-con thực sự ở từng cấp. Tuy nhiên, nó vẫn có thể rất lớn và tạo nhiều rows do child multiplicity. Nếu mỗi line còn có collection độc lập `taxes`, JOIN cả `adjustments` và `taxes` có thể tiếp tục nhân các branches **ở cấp line**.

### 19.1. Công thức khái niệm

Nếu một node có nhiều **to-many branches độc lập**, chi phí JOIN ở node đó thường gần **tích cardinalities** của các branches.

Nếu là **một chuỗi to-many lồng nhau**, chi phí theo số paths/leaf rows của cây, vẫn có thể lớn nhưng không nhất thiết là tích của những sets cùng cấp trên cùng root.

### 19.2. Kế hoạch fetch theo tầng

Với graph sâu:

1. Chọn parent page/IDs.
2. Fetch lines của parents.
3. Fetch adjustments cho lines đã chọn (bằng IDs/batch).
4. Fetch payments của parents riêng.

Cách này tránh bắt database tạo tổ hợp adjustments × payments của mỗi order nếu chúng độc lập.

## 20. Tránh lọc collection trực tiếp trong FETCH JOIN

Giả sử muốn lấy **tất cả orders có ít nhất một line mang SKU A** nhưng sau đó cần **đầy đủ lines** của các orders đó.

Một truy vấn kiểu:

```sql
select distinct o
from PurchaseOrder o
join fetch o.lines l
where l.productSku = :sku
```

có vấn đề:

1. Trong JPQL chuẩn, fetch join không được định nghĩa như một join alias tự do để lọc các phần tử fetched; nhiều dạng đặt alias/filter trên fetched side là **không portable**.
2. Ngay cả khi provider cho phép, điều kiện `WHERE l.productSku = :sku` có thể khiến collection `o.lines` chỉ chứa **những phần tử matching**, tức **collection đã được nạp không đầy đủ**.

### 20.1. Lọc roots bằng EXISTS

Nếu nghiệp vụ muốn chọn parents có SKU A nhưng fetch **toàn bộ lines**:

```java
List<PurchaseOrder> orders = em.createQuery(
        "select distinct o from PurchaseOrder o " +
        "left join fetch o.lines " +
        "where exists (" +
        "  select l.id from OrderLine l " +
        "  where l.order = o " +
        "  and l.productSku = :sku" +
        ")",
        PurchaseOrder.class)
    .setParameter("sku", "A-001")
    .getResultList();
```

`EXISTS` quyết định **order nào phù hợp**, còn `LEFT JOIN FETCH o.lines` tải **các lines của order đó**. Hai nhiệm vụ được tách rõ.

### 20.2. Phân trang với EXISTS

Nếu cần page:

```sql
select o.id
from PurchaseOrder o
where exists (
    select l.id from OrderLine l
    where l.order = o and l.productSku = :sku
)
order by o.createdAt desc, o.id desc
```

Chọn IDs kèm pagination, rồi fetch lines/payments theo IDs **không lọc child elements**. Cách này vừa giữ parent cardinality vừa tránh collection partial-load.

### 20.3. Nếu chỉ cần matching lines, đừng giả làm full collection

Một endpoint chỉ cần order ID và các lines có SKU A có thể query DTO rows trực tiếp:

```sql
select l
from OrderLine l
where l.order.id in :orderIds
  and l.productSku = :sku
```

Không cần gán kết quả lọc vào `PurchaseOrder.lines` như thể đó là toàn bộ relation trong persistence context.

## 21. Khi chỉ cần danh sách, dùng DTO projection thay entity graph

Một trang danh sách orders thường chỉ cần:

```text
id
orderCode
createdAt
lineCount
totalPaid
```

Nó **không cần toàn bộ OrderLine và Payment entities**.

### 21.1. DTO cho parent

```java
package example.shop.api;

import java.time.Instant;

public record OrderListRow(
    Long id,
    String orderCode,
    Instant createdAt
) {}
```

JPQL:

```java
List<OrderListRow> page = em.createQuery(
        "select new example.shop.api.OrderListRow(" +
        "o.id, o.orderCode, o.createdAt) " +
        "from PurchaseOrder o " +
        "where o.tenantId = :tenantId " +
        "order by o.createdAt desc, o.id desc",
        OrderListRow.class)
    .setParameter("tenantId", tenantId)
    .setMaxResults(50)
    .getResultList();
```

Ưu điểm:

- Không hydrate toàn bộ entity graph.
- Query có độ hạt parent nên pagination dễ hiểu.
- Không tải lines/payments chỉ để hiển thị ba cột.
- Không cần trả JPA managed entities ra API.

### 21.2. Đếm children bằng aggregate

Nếu cần `lineCount`:

```java
List<Object[]> counts = em.createQuery(
        "select l.order.id, count(l) " +
        "from OrderLine l " +
        "where l.order.id in :ids " +
        "group by l.order.id",
        Object[].class)
    .setParameter("ids", ids)
    .getResultList();
```

Query này trả mỗi group theo order ID, **không cần fetch tất cả line entities**. Với orders không có line, `GROUP BY` trên `OrderLine` không tạo row, nên application phải điền `0` cho IDs còn thiếu khi dựng DTO.

### 21.3. Hai aggregate queries thay vì JOIN cả hai collections

Đếm lines và cộng payments bằng hai queries riêng:

```sql
select l.order.id, count(l)
from OrderLine l
where l.order.id in :ids
group by l.order.id
```

```sql
select p.order.id, sum(p.amount)
from Payment p
where p.order.id in :ids
group by p.order.id
```

Vì sao không viết:

```sql
select o.id, count(l), sum(p.amount)
from PurchaseOrder o
left join o.lines l
left join o.payments p
group by o.id
```

? JOIN hai collections có thể làm **count(lines)** và **sum(payments)** bị nhân. Nếu một order có 3 lines và 2 payments, `count(l)` trên JOIN có thể ra 6 và mỗi payment amount bị cộng 3 lần.

`COUNT(DISTINCT l.id)` có thể chữa một phần vấn đề count, nhưng **`SUM(DISTINCT p.amount)` không đúng nếu hai payments khác nhau có cùng amount**. Tách aggregate theo từng collection hoặc dùng pre-aggregated subqueries phù hợp với database là lựa chọn an toàn hơn.

## 22. Chi phí thực: số SQL queries chưa đủ để đo

Để đánh giá fetch plan, nên xem nhiều chỉ số:

| Chỉ số | Ý nghĩa |
|---|---|
| Statement count | Có bao nhiêu lần round-trip tới database |
| Rows returned | SQL/JDBC phải chuyển bao nhiêu hàng |
| Bytes transferred | Bao nhiêu dữ liệu lặp lại trong result set |
| Query wall time | Database + network + driver + hydration |
| JDBC/result processing CPU | Chi phí giải mã và hydrate rows |
| Heap allocations | Entity objects, collections và các cấu trúc tạm |
| Managed entity count | Số object bị persistence context theo dõi |
| Pagination correctness | Có đúng số lượng/thứ tự root của page không |
| DB plan | JOIN order, scans, sorts, indexes, cardinality estimates |
| Cache hit/miss | Collections có tải từ cache hay database |

Một query duy nhất trả 250.000 rows có thể chậm hơn 3 queries tổng cộng trả 20.000 rows. Ngược lại, nếu round-trip latency rất cao và collections rất nhỏ, một fetch join có thể tốt hơn.

### 22.1. Kinh nghiệm thiết kế

Trước khi tối ưu “số SELECT”, hỏi:

1. Mỗi root có bao nhiêu children ở các associations?
2. Dữ liệu có lệch phân bố, ví dụ một root có 100.000 lines?
3. Tất cả children có thật sự được sử dụng?
4. SQL rows có lặp lại dữ liệu parent/child bao nhiêu lần?
5. Endpoint cần page parent hay export toàn bộ?
6. Entity graph có cần managed entities hay chỉ DTO?

## 23. Logging và quan sát SQL do provider sinh

JPQL:

```sql
select distinct o
from PurchaseOrder o
left join fetch o.lines
left join fetch o.payments
```

không cho thấy trực tiếp toàn bộ SQL, aliases và execution plan. Nên bật SQL logging có kiểm soát trong dev/test.

Ví dụ Hibernate-specific properties:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
hibernate.generate_statistics=true
```

Trong production, tránh bật SQL/parameter logging tràn lan vì tăng overhead và có thể lộ dữ liệu nhạy cảm. Tùy logging framework, có thể dùng logger categories dành cho SQL và bind values, nhưng tên logger thay đổi theo Hibernate version.

### 23.1. Không chỉ nhìn SQL text

Một câu SQL dài không có nghĩa nó tệ, và một câu SQL ngắn không có nghĩa nó rẻ. Cần chạy execution plan (ví dụ `EXPLAIN`/`EXPLAIN ANALYZE` cho SELECT khi phù hợp), đo rows actual, join cardinality và thời gian.

Khi query có 8 lines × 5 payments, plan có thể ước lượng 40 rows cho một order; với nhiều orders, cost tăng mạnh. Nếu optimizer estimates sai, plan có thể còn kém hơn.

### 23.2. Dùng `EXPLAIN ANALYZE` với nhận thức về chi phí

Với SELECT, `EXPLAIN ANALYZE` trên nhiều database thực sự chạy query và đo chi phí. Nó không sửa dữ liệu theo bản chất SELECT, nhưng vẫn có thể tiêu tốn nhiều CPU/IO và giữ locks/snapshots theo database. Không chạy một query quá nặng trên production chỉ để “xem thử” mà thiếu kế hoạch.

### 23.3. Kiểm tra collection size theo phân bố

Một `avg(lines per order) = 5` có thể đánh lừa khi một số đơn chứa 20.000 lines. Với `JOIN FETCH`, **outliers** có thể thống trị tổng hàng. Nên xem percentiles (p50, p95, p99, max) của collection cardinality khi lập fetch plan cho hệ thống lớn.

## 24. Quan sát Hibernate statistics

Hibernate cung cấp công cụ thống kê provider-specific, ví dụ `SessionFactory.getStatistics()`, để theo dõi số statement execution, entities/collections loaded/fetched, cache hits và các chỉ số khác theo khả năng phiên bản.

Ví dụ mã minh họa:

```java
org.hibernate.SessionFactory sessionFactory =
    em.getEntityManagerFactory().unwrap(
        org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics statistics =
    sessionFactory.getStatistics();

long statements =
    statistics.getPrepareStatementCount();

long entitiesLoaded =
    statistics.getEntityLoadCount();

long collectionsFetched =
    statistics.getCollectionFetchCount();
```

Lưu ý:

- Thống kê cần bật và có thể có overhead.
- Số liệu này có thể là toàn SessionFactory và chịu ảnh hưởng workload khác.
- `getPrepareStatementCount()` không đồng nghĩa ước lượng database rows transferred.
- `getCollectionFetchCount()` và các counters không thay cho việc quan sát SQL rows/plan.
- `unwrap` tới Hibernate types là **provider-specific**, không chạy portable trên provider khác.

Để so sánh hai fetch plans, đo dưới workload kiểm soát, cùng dữ liệu, cùng cache state và transaction boundary.

## 25. Đánh đổi bộ nhớ và persistence context

Khi fetch 1.000 orders + 8.000 lines + 5.000 payments thành managed entities, persistence context có thể giữ hàng chục nghìn objects và collection wrappers.

Nếu một query sinh 40.000 SQL rows, provider còn phải xử lý các row-level state và duplicate references trong quá trình hydration. Row explosion không nhất thiết tạo 40.000 entity objects, nhưng **tốn CPU và bộ nhớ tạm** đáng kể.

### 25.1. Tránh nạp graph khổng lồ vào một EntityManager lâu sống

Một batch/report job có thể dùng các trang hoặc đơn vị xử lý:

```text
Page 1 -> fetch roots + needed collections -> map DTO/export
Page 2 -> fetch roots + needed collections -> map DTO/export
...
```

Nếu dùng EntityManager lâu sống, managed entities có thể tích tụ. Có thể tổ chức transaction/context theo batch hoặc `clear()` có chủ đích **sau khi đã map dữ liệu cần thiết**, nhưng:

- `clear()` detach toàn bộ entities.
- Những lazy collections chưa được init sẽ không tự tải sau khi context đóng.
- Chưa flush những thay đổi cần giữ thì `clear()` có thể làm mất pending managed state.
- Đối với read-only export, DTO/streaming JDBC/SQL có thể phù hợp hơn.

### 25.2. Open Session in View không phải giải pháp

Giữ session mở tới lúc serialize REST response có thể giúp lazy associations được tải sau service, nhưng có thể gây:

- SQL phát sinh ngoài dự kiến trong serializer.
- N+1 không được nhìn thấy ở service code.
- Khó kiểm soát transaction/read consistency.
- Graph bị tải quá rộng do recursion/serialization.

Tốt hơn là dựng response DTO và chủ động fetch đúng associations trong một service boundary được thiết kế rõ.

## 26. Fetch plan phải theo use case

Một entity `PurchaseOrder` có nhiều associations, nhưng từng màn hình cần tập khác nhau:

| Use case | Cần gì? | Kế hoạch phù hợp |
|---|---|---|
| Order list | ID, code, createdAt, status | DTO parent projection, pagination |
| Order detail | Một order + lines + payments | Hai collection fetch queries cùng context hoặc batch |
| Order detail giản lược | Order + customer + lines | To-one fetch + một collection fetch |
| Financial dashboard | Count lines, sum payments | Aggregate queries tách theo collection |
| Export 1 triệu orders | Trường dữ liệu chọn lọc | Paged DTOs/streaming được kiểm chứng, không hydrate toàn bộ graph |
| Customer account history | Page orders + payment summary | Page IDs + aggregate payment, tránh full collection |
| Administrative search | Filter động trên lines, trả orders | EXISTS cho root predicate + page IDs + fetch những dữ liệu cần |

Không nên đặt `FetchType.EAGER` trên mọi association chỉ vì **một** endpoint cần nhiều dữ liệu.

### 26.1. Nhân số hàng đôi khi là chi phí chấp nhận được

Với đúng **một order** có 2 lines và 1 payment, query gộp có thể rất nhỏ. Nhưng nếu cùng mapping được dùng với 10.000 orders mà mỗi order có 30 lines và 20 payments, tổng rows có thể cực lớn. Tối ưu dựa trên **kích thước và phân bố dữ liệu thực**.

## 27. Tách truy vấn có luôn chính xác nếu dữ liệu thay đổi?

Không nhất thiết. Ví dụ:

```text
T1: SELECT page order IDs
T2: Một order bị xóa / thêm payment
T1: SELECT orders + lines WHERE id IN (...)
T1: SELECT orders + payments WHERE id IN (...)
```

Một transaction đọc ở isolation `READ COMMITTED` có thể nhìn thấy những commit khác nhau giữa các statements. Khi cần tính nhất quán giữa lines và payments:

- Chọn isolation level/snapshot semantics phù hợp với database.
- Dùng một transaction cho logic đọc nếu framework/provider yêu cầu.
- Cân nhắc cơ chế version/as-of timestamp cho reporting.
- Với workflows tài chính, có thể sử dụng bảng/materialized read model nhất quán theo thời điểm.

**Không phải cứ một SQL JOIN là luôn “đúng hơn” về nghiệp vụ**, và không phải cứ tách SQL là luôn “không nhất quán”. Cần xác định yêu cầu đọc snapshot và cơ chế database.

### 27.1. Không cố gắng có đồng thời ít round-trips, full graph và snapshot mạnh mà không đo

Ba mục tiêu:

1. Ít statements.
2. Ít rows/bytes.
3. Snapshot consistency mạnh.

Đôi khi cần đánh đổi và chọn transaction isolation hoặc kiến trúc read model. Không có một annotation giải quyết mọi mục tiêu.

## 28. Giới hạn `IN (:ids)` khi fetch theo page

Các truy vấn:

```sql
where o.id in :ids
```

phù hợp khi `ids` là một page vừa phải. Với hàng nghìn/chục nghìn IDs:

- Database có thể có giới hạn số phần tử trong `IN` hoặc số bind parameters.
- SQL plan và parse overhead có thể tăng.
- JDBC driver/provider có thể chia parameter lists theo cơ chế riêng.
- Query text/caching thay đổi theo kích thước `IN`.

Vì thế, page size hoặc batch size cần có giới hạn. Đối với report lớn, xử lý các ID chunks hoặc dùng staging/temp table/SQL join theo khả năng database.

### 28.1. Không truyền empty list

Khi phase 1 không có IDs:

```java
if (ids.isEmpty()) {
    return List.of();
}
```

Không giả định `IN ()` với danh sách rỗng có syntax/semantics portable trên mọi DB/JPA provider.

### 28.2. SQL thứ tự kết quả không dựa vào thứ tự `IN`

`WHERE id IN (10, 5, 7)` không có nghĩa DB trả parent theo thứ tự 10, 5, 7. Dùng `ORDER BY` hoặc khôi phục thứ tự từ danh sách page IDs ở Java.

## 29. Hibernate fetch hints và cấu hình không thay đổi bản chất toán học

Một số cấu hình/hints có thể ảnh hưởng cách provider tải dữ liệu:

- `@BatchSize` hoặc `hibernate.default_batch_fetch_size`.
- `@Fetch(FetchMode.SUBSELECT)`.
- Fetch entity graphs.
- Query-specific fetch joins.
- Hibernate read-only/stateless processing cho use case phù hợp.

Những công cụ này có mục tiêu khác nhau. **Không có hint nào làm phép JOIN SQL của hai to-many collections độc lập thôi tạo các tổ hợp rows** nếu vẫn yêu cầu database JOIN cả hai trong một result set phẳng.

### 29.1. Thay `List` thành `Set` không chữa SQL

Nó có thể tránh Hibernate multiple-bag restriction, nhưng `L×P` vẫn tồn tại.

### 29.2. Thêm `DISTINCT` không chữa SQL

Nó xử lý duplicate root results, không giảm số combinations child.

### 29.3. Thêm index không chữa multiplicative rows

Index có thể giúp tìm/cấp dữ liệu nhanh hơn nhưng output row cardinality vẫn theo joins. Khi 8 lines và 5 payments thật sự matching, SQL JOIN phải biểu diễn 40 combinations.

### 29.4. Đổi sang native SQL không tự chữa

Một native `SELECT ... LEFT JOIN lines ... LEFT JOIN payments` vẫn có phép nhân. SQL nâng cao như aggregation thành JSON/ARRAY, lateral joins hoặc pre-aggregation có thể thay đổi result shape, nhưng các kỹ thuật đó **database-specific** và cần mapping/size controls riêng.

## 30. Khi nào dùng SQL JSON aggregation hoặc read model?

Trong một số hệ thống, API cần kết quả dạng:

```json
{
  "orderId": 10,
  "lines": [
    {"id": 1, "sku": "A"},
    {"id": 2, "sku": "B"}
  ],
  "payments": [
    {"id": 50, "amount": 100.00}
  ]
}
```

RDBMS hiện đại có thể cung cấp JSON aggregation hoặc các cấu trúc tổng hợp khác để trả một row cho mỗi parent với hai arrays đã gom riêng. Nhưng:

- SQL syntax khác giữa PostgreSQL, Oracle, MySQL, SQL Server...
- Cần **pre-aggregate mỗi collection độc lập** trước khi join để tránh duplicate nested JSON elements.
- Có thể tạo JSON rất lớn cho một parent nhiều children.
- Cần xử lý null/empty arrays, ordering và encoding.
- Không còn là JPA entity fetch theo semantics thông thường; thường là DTO/native projection.

Một lựa chọn khác cho dashboard nhiều phép tổng hợp là bảng read model/materialized view được cập nhật có kiểm soát. Chỉ dùng khi workload và consistency requirements phù hợp, không phải mặc định mỗi query ORM đều cần chuyển sang native JSON.

## 31. Vì sao query có `GROUP BY` đôi khi vẫn sai?

Ví dụ tính tổng thanh toán và số dòng:

```sql
select o.id, count(l), sum(p.amount)
from PurchaseOrder o
left join o.lines l
left join o.payments p
group by o.id
```

Với Order#10 có 3 lines và 2 payments, JOIN tạo 6 rows. Nếu payments lần lượt có amount 100 và 200:

```text
Raw join rows:
L1-P1 (100)
L1-P2 (200)
L2-P1 (100)
L2-P2 (200)
L3-P1 (100)
L3-P2 (200)

count(l) = 6     (đúng phải 3 lines)
sum(p.amount) = 900 (đúng phải 300)
```

`COUNT(DISTINCT l.id)` có thể trả 3 lines, nhưng không được dùng `SUM(DISTINCT p.amount)` như một “cách chữa” tổng quát: nếu có hai payment cùng 100, `SUM(DISTINCT)` chỉ cộng một lần giá trị 100.

**Cách đúng là tính tổng mỗi collection trước khi ghép**, ví dụ chạy hai aggregate queries riêng theo parent IDs, hoặc dùng SQL subquery pre-aggregation phù hợp. Vấn đề nhân số hàng ảnh hưởng không chỉ hiệu năng mà còn **tính chính xác của thống kê**.

## 32. Kiểm thử tích hợp kế hoạch tải

Kế hoạch tải nên được kiểm chứng bằng các trường hợp dữ liệu cụ thể.

### 32.1. Bộ dữ liệu mẫu

Chuẩn bị:

| Order | Lines | Payments | Ý nghĩa |
|---|---:|---:|---|
| A | 0 | 0 | Hai collections rỗng |
| B | 1 | 0 | Một child collection rỗng |
| C | 0 | 2 | Collection khác rỗng |
| D | 3 | 2 | Row multiplication 3×2 |
| E | 8 | 5 | Row multiplication 8×5 |
| F | 100 | 80 | Outlier 8.000 combinations |

### 32.2. Những điều cần xác minh

- Số root entities returned đúng và không có duplicates ngoài semantics mong muốn.
- `lines.size()`, `payments.size()` đúng cho từng order.
- Không mất child vì alias/filter trên fetched collection.
- Page size/root order được giữ đúng sau khi fetch children.
- Có/không có `MultipleBagFetchException` theo provider/mapping.
- Số SQL statements hợp lý.
- Số rows/JDBC bytes không bùng nổ so với kế hoạch.
- Query không phát LazyInitializationException khi map DTO trong service.
- Không có N+1 khi access cả hai collections trên page.
- Transaction và context boundaries đúng.

### 32.3. JUnit test skeleton

```java
@Test
void loadsBothCollectionsWithoutMultiplyingResults() {
    // Fixture: Order D có 3 lines và 2 payments.
    // Gọi service đã dùng split-fetch kế hoạch.

    List<PurchaseOrder> result =
        orderReadService.findPageWithChildren(
            "TENANT_A", 0, 10);

    PurchaseOrder orderD = result.stream()
        .filter(o -> "D".equals(o.getOrderCode()))
        .findFirst()
        .orElseThrow();

    assertEquals(3, orderD.getLines().size());
    assertEquals(2, orderD.getPayments().size());
}
```

Đây chỉ là skeleton: cần fixtures, transaction và Spring/JPA test configuration phù hợp. Test số child entities đúng **chưa đủ** chứng minh SQL không tạo Cartesian explosion; nên kết hợp SQL logging/statistics/plan hoặc instrumentation trong integration test.

### 32.4. Đừng thay database thực bằng mock nếu đang kiểm tra JOIN behavior

Một mock repository có thể trả list Java đã dựng sẵn, nhưng không mô phỏng:

- SQL join cardinality.
- Hibernate multiple bag restrictions.
- Pagination over collection fetch.
- JDBC row hydration.
- Transaction isolation/identity map.

Tính chất này cần được kiểm chứng bằng provider/database thật hoặc môi trường test tương đương.

## 33. Những lỗi thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `MultipleBagFetchException` | Fetch đồng thời nhiều bags với Hibernate | Tách collection queries, batch/subselect hoặc thiết kế mapping thật sự phù hợp |
| Một SELECT nhưng response rất chậm | JOIN nhiều to-many tạo row explosion | Xem SQL rows/plan, split queries |
| Parent list có duplicates | JOIN collection nhân root result rows | `DISTINCT`/provider de-dup cho root; vẫn kiểm soát SQL rows |
| `DISTINCT` không giảm tải | Child combinations vẫn khác nhau | Không JOIN nhiều collections độc lập |
| Đổi `List` sang `Set` không nhanh hơn | SQL row multiplication vẫn tồn tại | Chọn fetch plan theo use case |
| Page 20 roots nhưng SQL load hàng nghìn rows | Pagination over collection fetch | Chọn page IDs trước, fetch children sau |
| Hibernate cảnh báo pagination in memory | Collection fetch + `setMaxResults` | Hai-phase pagination; bật fail-fast setting khi phù hợp |
| N+1 sau khi bỏ JOIN FETCH | Lazy collections được gọi từng parent | `@BatchSize`/default batch fetching hoặc split-fetch |
| Page order sai thứ tự | Query `IN (:ids)` không bảo đảm order | Khôi phục thứ tự theo page IDs |
| Collections thiếu phần tử | Filter alias bên fetched side | `EXISTS` chọn parents; fetch full collection riêng |
| DTO tổng tiền sai | JOIN hai collections trước aggregate | Tổng hợp riêng mỗi collection/pre-aggregate |
| Lỗi lazy khi serialize REST | Session đóng trước khi truy cập collection | Dựng DTO và load trong service transaction |
| RAM tăng mạnh | Managed graph quá lớn/hydration quá nhiều rows | Giới hạn page/DTO, transaction theo batch |
| Cùng ID nhưng parent không “ghép” collections | Hai query khác persistence contexts | Dùng cùng EntityManager/context |
| IN list quá lớn | Nhiều bind parameters/driver limit | Chunk IDs hoặc staging strategy |
| Đọc hai collections không cùng snapshot | Concurrency/isolation giữa hai SELECT | Chọn transaction isolation/consistency policy |
| Chuyển `@OrderBy` vẫn lỗi multiple bag | `@OrderBy` không phải index persistent | Không dùng làm mẹo; split queries |
| Thêm `@OrderColumn` làm DML tăng | Reordering cập nhật vị trí trong DB | Chỉ dùng nếu domain cần indexed list |
| Entity graph tải tất cả vẫn chậm | Graph không quyết định SQL join strategy | Giới hạn attributes, kiểm tra SQL, split collections |
| SQL query count thấp nhưng CPU cao | JDBC phải hydrate nhiều duplicate rows | Đo rows/bytes, không chỉ query count |

## 34. Bài tập thực hành

### Bài 1 — Tính row multiplication

Một đơn hàng có 12 lines và 7 payments.

**Yêu cầu:**

1. Tính số SQL rows có thể sinh từ hai `LEFT JOIN` độc lập.
2. Tính số records cha/con thực tế.
3. Tính số rows xấp xỉ nếu fetch hai collections bằng hai queries.
4. Giải thích vì sao chi phí truyền bytes có thể tăng nhanh hơn số entities.

**Gợi ý:** `12 × 7 = 84` rows JOIN cho một parent.

### Bài 2 — Collection rỗng

Một order có 5 lines và 0 payments. So sánh kết quả khi dùng:

```sql
left join fetch o.lines
left join fetch o.payments
```

với:

```sql
join fetch o.lines
join fetch o.payments
```

**Câu hỏi:** vì sao left join vẫn giữ parent nhưng inner join có thể loại parent?

### Bài 3 — `DISTINCT` có đủ không?

Cho 3 lines và 2 payments. Viết bảng sáu SQL rows. Thêm `select distinct o` vào JPQL rồi giải thích điều gì được khử trùng ở root result và điều gì vẫn xảy ra tại database/JDBC.

### Bài 4 — Hibernate multiple bags

Cho:

```java
private List<OrderLine> lines;
private List<Payment> payments;
```

cả hai đều là `@OneToMany`, không có `@OrderColumn`. Viết một query có thể gây multiple-bag restriction trong Hibernate; đề xuất giải pháp **không phải đổi ngữ nghĩa domain**.

### Bài 5 — Tạo kế hoạch split-fetch

Viết hai JPQL queries: query đầu tải Order và lines, query sau tải Order và payments theo cùng `:id`. Giải thích vai trò persistence context và tránh dùng EntityManager độc lập.

### Bài 6 — Phân trang 20 parents

Thiết kế:

1. JPQL lấy 20 IDs mới nhất theo `createdAt DESC, id DESC`.
2. Query `WHERE o.id IN :ids` fetch lines.
3. Query `WHERE o.id IN :ids` fetch payments.
4. Khôi phục thứ tự page IDs.

Giải thích vì sao không đặt `setMaxResults(20)` trên query có collection fetch.

### Bài 7 — N+1 sau khi bỏ JOIN FETCH

Màn hình tải 100 orders và duyệt `getLines()` của mọi order. Đề xuất:

- Một phương án Hibernate `@BatchSize`.
- Một phương án tách fetch query.
- Những metrics cần đo để chọn.

### Bài 8 — Aggregates bị sai

Một order có 4 lines và payments là 100, 100, 50.

**Yêu cầu:** giải thích vì sao `COUNT(l)` và `SUM(p.amount)` trên cùng JOIN có thể sai; vì sao `SUM(DISTINCT p.amount)` cũng sai; viết hai aggregate JPQL queries theo order IDs.

### Bài 9 — Tìm orders có SKU A nhưng lấy tất cả lines

Viết query dùng `EXISTS` chọn orders theo SKU A và fetch **full lines collection**. Giải thích vì sao filter trên alias fetched collection có thể tạo partially initialized collection.

### Bài 10 — EntityGraph

Tạo `EntityGraph<PurchaseOrder>` với `lines` và `payments`. Đánh giá:

- Graph yêu cầu tải những attributes nào?
- JPA có bảo đảm dùng hai SQL SELECTs không?
- Nếu provider chọn hai JOINs trong một SQL, rủi ro gì xảy ra?
- Cách thay thế có kiểm soát?

### Bài 11 — Cây nhiều tầng

Một order có 5 lines; mỗi line có 3 adjustments và 4 taxes; order còn có 6 payments.

**Yêu cầu:** dự đoán vì sao JOIN mọi branch có thể bùng nổ; chia kế hoạch fetch theo root page, lines, adjustments/taxes và payments.

### Bài 12 — Integration test

Tạo fixtures cho orders có 0/0, 3/2, 8/5 và 100/80 children. Test kết quả graph chính xác, cùng lúc quan sát SQL row count, statement count, memory và pagination. Không dựa duy nhất vào kích thước `List<PurchaseOrder>`.

## 35. Câu hỏi tự kiểm tra

**1. Row multiplication xảy ra khi nào?**

Khi một SQL result set JOIN nhiều one-to-many/many-to-many associations và mỗi root có nhiều phần tử ở những branches độc lập; các tổ hợp child rows tạo ra nhiều SQL rows.

**2. Hai collections có 8 và 5 phần tử tạo bao nhiêu rows khi LEFT JOIN cùng lúc?**

Thông thường 40 rows cho root đó, nếu mỗi collection thực sự có 8 và 5 matching rows.

**3. Nếu một collection rỗng thì sao?**

Với LEFT JOIN, parent được giữ; số rows gần `max(1, L) × max(1, P)` cho hai branches.

**4. Có phải JOIN FETCH một collection luôn xấu không?**

Không. Với tập root được giới hạn và collection nhỏ, một collection fetch join có thể hiệu quả.

**5. To-one JOIN FETCH có nhân rows như to-many không?**

Thông thường không, vì mỗi root có tối đa một matching target ở association to-one.

**6. `DISTINCT` có chữa phép nhân rows ở database không?**

Không. Nó có thể khử root duplicates trong Java/JPQL, nhưng child combinations vẫn tạo SQL rows khác nhau.

**7. `MultipleBagFetchException` là lỗi chuẩn của JPA hay Hibernate-specific?**

Hibernate-specific; nó liên quan việc đồng thời fetch nhiều bag collections.

**8. Vì sao `List` không có `@OrderColumn` có thể là bag?**

Hibernate có thể ánh xạ collection đó theo ngữ nghĩa không có persistent index, nên khó phân biệt những lần lặp khi fetch cùng các bags khác.

**9. `@OrderBy` có giống `@OrderColumn` không?**

Không. `@OrderBy` mô tả thứ tự sort khi tải; `@OrderColumn` quản lý vị trí phần tử trong database.

**10. Có nên đổi mọi `List` sang `Set` để tránh exception?**

Không. Nó đổi domain semantics và không loại bỏ SQL row multiplication.

**11. `FetchType.EAGER` có bảo đảm một JOIN nhanh không?**

Không. Provider có thể sử dụng SQL strategy khác; EAGER còn có thể tải dữ liệu không cần.

**12. Hai split-fetch queries cần dùng cùng cái gì?**

Cùng persistence context/EntityManager trong một unit of work thích hợp, để managed parents cùng identity và collections được nạp cho đúng objects.

**13. Vì sao query `WHERE id IN :ids` không tự giữ thứ tự IDs?**

Vì SQL không bảo đảm row order nếu không có `ORDER BY`; phải sắp xếp lại hoặc dùng order phù hợp.

**14. Vì sao không kết hợp pagination root với collection fetch join tùy tiện?**

Vì SQL rows bị nhân theo children, nên DB LIMIT có thể cắt collection; provider có thể buộc phải pagination in memory.

**15. Cách phân trang phổ biến an toàn là gì?**

Chọn root IDs với pagination trước, rồi fetch từng collection theo danh sách IDs được giới hạn.

**16. Hibernate setting nào giúp phát hiện pagination over collection fetch?**

`hibernate.query.fail_on_pagination_over_collection_fetch`, tùy version/configuration.

**17. Batch fetching khắc phục vấn đề gì?**

Giảm N+1 queries bằng cách nạp cùng loại collections cho nhiều owners theo nhóm, không JOIN hai collections độc lập trong cùng result set.

**18. `@BatchSize` là chuẩn JPA không?**

Không, đó là Hibernate-specific annotation.

**19. `FetchMode.SUBSELECT` có bắt buộc portable trên mọi JPA provider không?**

Không, đó là tính năng Hibernate-specific.

**20. Entity graph có buộc provider dùng nhiều SELECTs không?**

Không. Entity graph chỉ định attributes cần tải; SQL strategy do provider quyết định.

**21. Làm sao lọc root có line SKU A nhưng vẫn tải full lines?**

Dùng `EXISTS` hoặc query IDs chọn roots phù hợp, rồi fetch full collection mà không lọc phần tử ở fetched side.

**22. Vì sao filter trực tiếp trên fetch join alias có nguy cơ?**

Không portable theo JPQL chuẩn ở nhiều dạng và có thể làm loaded collection chỉ chứa subset.

**23. Vì sao `SUM(payment.amount)` có thể sai khi JOIN thêm lines?**

Mỗi payment amount bị lặp lại theo số lines của cùng order.

**24. `SUM(DISTINCT amount)` có luôn khắc phục được không?**

Không. Hai payments có cùng amount là hai giao dịch khác nhau nhưng DISTINCT có thể gộp một giá trị.

**25. Cách tính count lines và sum payments an toàn hơn?**

Chạy aggregate theo từng collection riêng hoặc pre-aggregate rồi join ở SQL mức DB-specific.

**26. Chỉ đếm số SQL statements có đủ đánh giá hiệu năng fetch plan không?**

Không. Cần xem rows, bytes, hydration CPU, memory, SQL plan và độ chính xác pagination.

**27. `getResultList()` trả đúng 20 orders có chứng minh SQL chỉ đọc 20 rows không?**

Không. Query fetch collections có thể cần đọc nhiều rows rồi de-duplicate/paginate.

**28. Có nên fetch cả graph khi trang list chỉ hiển thị ID/code/date không?**

Không; DTO projection thường phù hợp hơn.

**29. Split queries có thể thấy dữ liệu không cùng snapshot không?**

Có, tùy transaction isolation và concurrent writes.

**30. Khi nào cân nhắc read model/JSON aggregation?**

Khi use case read-heavy cần nested DTO hoặc aggregates đặc thù và có khả năng chấp nhận database-specific SQL/mapping/trade-offs.

## 36. Checklist lựa chọn kế hoạch tải

Trước khi thêm một association vào `JOIN FETCH` hoặc entity graph, tự hỏi:

1. **Use case có thật sự dùng collection này không?** Nếu không, giữ lazy/không fetch.
2. **Đây là to-one hay to-many?** To-many làm đổi cardinality SQL.
3. **Có bao nhiêu to-many branches độc lập được JOIN cùng lúc?** Hai trở lên là tín hiệu cần xem xét tích cardinality.
4. **Kích thước collection là bao nhiêu ở p50/p95/p99/max?** Đừng chỉ xem giá trị trung bình.
5. **Collection là bag, indexed list hay set?** Giữ domain semantics, không đổi tùy tiện vì provider exception.
6. **Có pagination root không?** Nếu có, chọn root IDs trước rồi fetch children.
7. **`DISTINCT` đang được dùng để làm gì?** Đừng coi khử duplicate Java là giải pháp SQL performance.
8. **Có filter trực tiếp child được fetch không?** Tránh partial collection; dùng EXISTS/ID selection.
9. **Có thể dùng DTO hoặc aggregate thay full entity graph không?**
10. **Có thể dùng batch/subselect fetching thay JOIN nhiều collections không?**
11. **Các split queries có cùng persistence context và consistency policy không?**
12. **Có đo SQL rows/bytes và statement count trên dataset đại diện không?**
13. **Các cache và serialization có vô tình kích hoạt lazy load không?**
14. **Query có giữ đúng thứ tự parent page không?**
15. **Có giới hạn page/IN-list/transaction memory và xử lý outliers không?**
16. **Giải pháp dùng Hibernate-specific APIs có được ghi rõ version/provider không?**

Một kế hoạch tải tốt phải đáp ứng đồng thời **correctness của object graph, correctness của pagination, chi phí SQL/JDBC hợp lý và contract dữ liệu của use case**.

## 37. Tổng kết

**Tải nhiều tập hợp bằng một JOIN FETCH duy nhất không nhất thiết nhanh.** Với hai to-many associations độc lập, số hàng SQL có thể tăng gần theo tích kích thước collections; với ba branches, nguy cơ còn lớn hơn. JPA/Hibernate có thể hợp nhất root entities thành cùng managed instances nhưng database, JDBC và ORM vẫn phải xử lý toàn bộ các tổ hợp hàng.

Các điều quan trọng cần nhớ:

1. **N+1 và Cartesian explosion là hai phía của bài toán fetch planning.** Giảm số query bằng mọi giá có thể khiến số hàng và bytes tăng quá mức.
2. **`JOIN FETCH` một to-many collection** thường hợp lý cho root scope nhỏ, nhưng **JOIN FETCH nhiều collection branches độc lập** phải được cân nhắc nghiêm túc.
3. **Hibernate `MultipleBagFetchException`** báo hạn chế khi đồng thời fetch nhiều bags. Đổi `List` sang `Set` hoặc thêm `@OrderColumn` chỉ để tránh lỗi không phải cách tối ưu đúng.
4. **`DISTINCT` xử lý root duplicates, không loại bỏ SQL row multiplication.** Không đánh giá hiệu năng chỉ bằng kích thước Java List.
5. **Tách fetch queries theo collection** là chiến lược chủ đạo: một query cho lines, một query cho payments, cùng persistence context và phạm vi IDs được kiểm soát.
6. **Với pagination, chọn parent IDs trước**, sau đó fetch children theo IDs; không áp `setMaxResults` trực tiếp lên query fetch collection và mong database cắt đúng root rows.
7. **Batch fetching và subselect fetching** giúp giảm N+1 mà không nhất thiết tạo một JOIN phẳng cho nhiều collections; các tùy chọn `@BatchSize`/`@Fetch(SUBSELECT)` thuộc Hibernate.
8. **Entity graphs định nghĩa dữ liệu cần tải, không cam kết chiến lược SQL cụ thể.** Cần kiểm tra SQL thực.
9. **DTO/aggregate queries** thường tối ưu hơn full entity graphs cho list/reporting. JOIN hai collections còn có thể làm `COUNT` và `SUM` sai vì dữ liệu bị nhân.
10. **Đo lường trên dữ liệu đại diện**: SQL statements, rows, network bytes, memory, query plan, pagination correctness và outliers để chọn kế hoạch fetch phù hợp.

Quy tắc thực hành ngắn nhất: **mỗi lần định fetch thêm một collection, hãy hỏi nó làm tăng số hàng theo phép cộng hay phép nhân**. Nếu câu trả lời là **phép nhân**, cần nghĩ tới split queries, batch fetching hoặc projection trước khi đưa giải pháp vào production.
