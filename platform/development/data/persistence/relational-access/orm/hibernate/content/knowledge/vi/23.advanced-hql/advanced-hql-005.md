# Biểu thức bảng chung (CTE) và truy vấn đệ quy khi được hỗ trợ

**Common Table Expression (CTE)**, hay *biểu thức bảng chung*, cho phép đặt tên một kết quả truy vấn trung gian bằng mệnh đề `WITH` rồi tham chiếu kết quả đó trong truy vấn chính. Trong HQL nâng cao của Hibernate, CTE giúp chia một phép tính phức tạp thành các bước dễ đọc, tái sử dụng tập dữ liệu trung gian và — khi Hibernate cùng cơ sở dữ liệu hỗ trợ — biểu diễn các truy vấn đệ quy trên cây hoặc đồ thị.

Truy vấn đệ quy thường xuất hiện trong các bài toán như:

- Lấy toàn bộ đơn vị con của một phòng ban.
- Tìm các cấp quản lý hoặc nhân viên cấp dưới.
- Duyệt cây danh mục sản phẩm.
- Truy vết các nhiệm vụ phụ thuộc hoặc quan hệ cha–con.
- Tính độ sâu, đường đi và thứ tự duyệt trên một cấu trúc phân cấp.

**Phạm vi và lưu ý tương thích:** CTE là một phần mở rộng quan trọng của **HQL trong Hibernate ORM 6.2 trở lên**, không phải cú pháp JPQL di động giữa mọi JPA provider. Hibernate có thể chuyển CTE *không đệ quy* thành subquery trên một số database không hỗ trợ CTE gốc, nhưng **không thể giả lập truy vấn đệ quy khi database không hỗ trợ recursive CTE**. Cú pháp cụ thể, hỗ trợ `SEARCH`/`CYCLE` và gợi ý materialization cần được đối chiếu với Hibernate version, dialect và database đang sử dụng.

Bài học đi từ CTE cơ bản tới recursive CTE với `UNION ALL`, phát hiện chu trình, thứ tự duyệt, ví dụ Java với `EntityManager`, thiết kế hiệu năng, giới hạn portability và các phương án thay thế.

## 1. CTE là gì và khác subquery thế nào?

Giả sử cần xác định các khách hàng có tổng giá trị đơn hàng đã hoàn tất vượt một ngưỡng. Cách truyền thống có thể dùng subquery trong `FROM` hoặc một query tổng hợp trực tiếp. Với CTE, ta đặt tên cho tập kết quả trung gian:

~~~hql
with CustomerTotals as (
    select o.customer.id as customerId,
           sum(o.totalAmount) as amount
    from PurchaseOrder o
    where o.status = :status
    group by o.customer.id
)
select t.customerId, t.amount
from CustomerTotals t
where t.amount >= :minimum
order by t.amount desc
~~~

Trong ví dụ:

1. `CustomerTotals` là **tên CTE**, không phải tên `@Entity`.
2. Phần trong dấu ngoặc là truy vấn HQL tạo một tập hàng trung gian.
3. `customerId` và `amount` là alias của các biểu thức được chọn.
4. Truy vấn chính tham chiếu CTE như một nguồn dữ liệu trong `FROM`.
5. `:status` và `:minimum` là named parameters được bind từ Java.

SQL tạo ra tùy dialect có thể sử dụng `WITH ... AS (...)` hoặc một dạng truy vấn được Hibernate biến đổi. Ta không phải tự khai báo entity mới có tên CustomerTotals.

### 1.1. CTE có phải bảng tạm vật lý?

Không nhất thiết. CTE là một **cấu trúc truy vấn logic**. Database optimizer có thể inline, gộp, tái sử dụng hoặc materialize kết quả trung gian tùy hệ quản trị, phiên bản và kế hoạch truy vấn.

Đừng mặc định rằng mỗi CTE luôn tạo một bảng vật lý, hay CTE được chạy đúng một lần. Việc nó thực thi và lưu kết quả như thế nào là quyết định của SQL engine, có thể chịu ảnh hưởng từ `MATERIALIZED`/`NOT MATERIALIZED` nếu hệ thống hỗ trợ.

### 1.2. Khi nào CTE đáng dùng?

CTE hữu ích khi:

- Một bước tổng hợp hoặc lọc phức tạp cần có tên và được sử dụng rõ ràng.
- Có nhiều bước tính toán phụ thuộc nhau.
- Muốn tách truy vấn thành các khối để người đọc dễ hiểu.
- Cần tái sử dụng một tập kết quả trung gian trong một query.
- Cần biểu diễn đệ quy — năng lực không thể thay bằng subquery thông thường trong mọi trường hợp.

Với truy vấn đơn giản, một `SELECT ... WHERE` trực tiếp có thể rõ ràng và hiệu quả hơn. Không thêm CTE chỉ vì cú pháp trông “nâng cao”.

## 2. Cú pháp WITH trong HQL

Cấu trúc khái quát:

~~~text
WITH CteName AS (
    <HQL query expression>
)
SELECT ...
FROM CteName alias
WHERE ...
~~~

Có thể có nhiều CTE, ngăn cách bằng dấu phẩy:

~~~hql
with
    PaidAmounts as (
        select p.order.id as orderId,
               sum(p.amount) as paid
        from Payment p
        group by p.order.id
    ),
    RequiredAmounts as (
        select l.order.id as orderId,
               sum(l.quantity * l.unitPrice) as required
        from OrderLine l
        group by l.order.id
    )
select r.orderId, r.required, p.paid
from RequiredAmounts r, PaidAmounts p
where r.orderId = p.orderId
  and p.paid < r.required
~~~

Trong ví dụ, hai CTE được tạo độc lập và được nối logic bằng điều kiện `r.orderId = p.orderId`. Đây là minh họa về cấu trúc, không phải công thức tài chính có thể sử dụng cho mọi trạng thái thanh toán; ứng dụng thật có thể cần xử lý `NULL`, hoàn tiền và các ràng buộc khác.

### 2.1. Vị trí và tên CTE

Mệnh đề `WITH` đứng đầu query expression tương ứng. Mỗi CTE có tên nhận diện trong phạm vi truy vấn. Không đặt tên trùng với entity, alias hoặc reserved keyword một cách mơ hồ.

Tên CTE chỉ tồn tại trong phạm vi câu truy vấn đó; nó không phải bảng database được tạo và lưu vĩnh viễn.

### 2.2. Khai báo các cột được tham chiếu

Trong HQL, các alias của select item trong CTE đặc biệt quan trọng:

~~~hql
with RankedCustomers as (
    select c.id as id,
           c.name as name,
           c.loyaltyPoints as points
    from Customer c
)
select r.id, r.name
from RankedCustomers r
where r.points > :threshold
~~~

Truy vấn chính tham chiếu `r.points` vì select item bên trong được đặt alias `points`. Không nên nhầm alias của CTE với property của một `@Entity`; CTE tạo một tập hàng mang các trường từ projection.

### 2.3. HQL dùng tên entity và property

Khi viết bên trong CTE:

~~~hql
from PurchaseOrder o
where o.customer.id = :customerId
~~~

`PurchaseOrder` là entity name và `customer` là property của entity. Đây là **HQL**, không phải SQL native sử dụng tên bảng `purchase_orders` hoặc cột `customer_id`.

Nếu muốn dùng cú pháp riêng của PostgreSQL, SQL Server, Oracle hoặc một DB khác, có thể dùng `createNativeQuery()`, nhưng khi đó phải dùng schema/table/column names thực tế và tự quản lý portability.

## 3. CTE không đệ quy qua EntityManager

Một ví dụ Java hoàn chỉnh cho CTE tổng hợp:

~~~java
String hql = """
    with CustomerTotals as (
        select o.customer.id as customerId,
               sum(o.totalAmount) as amount
        from PurchaseOrder o
        where o.status = :status
        group by o.customer.id
    )
    select t.customerId, t.amount
    from CustomerTotals t
    where t.amount >= :minimum
    order by t.amount desc
    """;

List<Object[]> results = entityManager
    .createQuery(hql, Object[].class)
    .setParameter("status", OrderStatus.COMPLETED)
    .setParameter("minimum", new BigDecimal("1000000"))
    .getResultList();

for (Object[] row : results) {
    Long customerId = (Long) row[0];
    BigDecimal total = (BigDecimal) row[1];
    System.out.println(customerId + " : " + total);
}
~~~

Ví dụ giả định `PurchaseOrder.totalAmount` là `BigDecimal` và `PurchaseOrder.customer.id` có kiểu `Long`; kiểu thực tế của aggregate cần tương ứng với mapping/provider.

### 3.1. DTO thay cho Object[]

Kết quả nhiều cột có thể được chuyển thành DTO trong Java:

~~~java
public record CustomerTotalView(
    Long customerId,
    BigDecimal amount
) {}
~~~

Sau khi nhận `Object[]` từ query, ánh xạ từng hàng sang DTO. Với các phiên bản Hibernate hỗ trợ constructor projection phù hợp, có thể dùng `select new ...` hoặc typed result projection theo API hiện hành.

Không mặc định mọi CTE có thể được trả thẳng thành entity managed. Kết quả CTE có thể là aggregate và computed fields, không tương ứng với một row entity có persistent identity.

### 3.2. CTE có thể thay derived subquery không?

Về logic, một CTE không đệ quy thường gần với một derived table/subquery trong `FROM`. Ưu điểm của CTE là có thể đặt tên, sắp xếp nhiều bước hoặc tái sử dụng.

Tuy nhiên, việc viết lại có tương đương và hiệu quả không còn phụ thuộc:

- Correlation tới query ngoài.
- Các điều kiện grouping/aggregation.
- DISTINCT hoặc lọc kết quả.
- Kế hoạch optimizer.
- Việc một CTE được dùng một hay nhiều lần.

Đừng giả định mọi CTE đều nhanh hơn subquery.

## 4. Materialization hint: MATERIALIZED và NOT MATERIALIZED

HQL hỗ trợ khai báo gợi ý materialization theo cú pháp:

~~~hql
with CustomerTotals as materialized (
    select o.customer.id as customerId,
           sum(o.totalAmount) as amount
    from PurchaseOrder o
    group by o.customer.id
)
select t.customerId, t.amount
from CustomerTotals t
~~~

Và:

~~~hql
with CustomerTotals as not materialized (
    select o.customer.id as customerId,
           sum(o.totalAmount) as amount
    from PurchaseOrder o
    group by o.customer.id
)
select t.customerId, t.amount
from CustomerTotals t
~~~

Ý nghĩa định hướng:

| Hint | Ý định |
| --- | --- |
| `MATERIALIZED` | Gợi ý DB materialize kết quả trung gian |
| `NOT MATERIALIZED` | Gợi ý DB inline/tránh materialization khi phù hợp |
| Không ghi hint | Để optimizer/provider quyết định theo mặc định |

Đây là **hint**, không phải mệnh lệnh bắt buộc với mọi dialect. Hibernate/database có thể bỏ qua hoặc xử lý khác nhau. Một số database không hỗ trợ cú pháp này trực tiếp; provider có thể dịch hoặc bỏ hint tùy khả năng.

### 4.1. Khi nào hint có thể có ích?

Khi CTE được tham chiếu nhiều lần hoặc tính toán đắt, materialization đôi khi giúp tránh lặp việc tính. Ngược lại, materialization có thể ngăn optimizer đẩy điều kiện lọc sâu xuống query và làm tăng chi phí lưu kết quả trung gian.

Chọn hint dựa trên `EXPLAIN`/execution plan và đo đạc với dữ liệu thật, không dùng một quy tắc cứng rằng MATERIALIZED luôn nhanh hơn.

## 5. Truy vấn đệ quy giải quyết bài toán nào?

Một cấu trúc cây gồm các node có quan hệ cha–con:

~~~text
Company
├── Engineering
│   ├── Backend
│   │   ├── Platform
│   │   └── API
│   └── Frontend
└── Operations
    └── Support
~~~

Nếu muốn lấy toàn bộ node dưới Engineering, một query cố định chỉ có một hoặc hai JOIN không đủ khi độ sâu cây thay đổi. Có thể viết nhiều lệnh Java lặp để lấy từng cấp, nhưng số lần truy vấn sẽ tăng.

**Recursive CTE** cho phép database tự lặp truy vấn lấy con từ những node tìm được ở vòng trước, dừng khi không còn node mới.

Một CTE đệ quy thường có:

1. **Anchor/base query**: chọn tập node ban đầu.
2. **UNION ALL**: hợp nhất kết quả anchor với các vòng đệ quy.
3. **Recursive member**: tham chiếu CTE để tìm node kế tiếp.
4. **Điều kiện kết thúc**: không còn child hoặc có giới hạn rõ ràng.
5. **Chống chu trình**: cần xử lý khi cấu trúc không thực sự là cây.

~~~mermaid
flowchart TD
    A["Anchor: lấy node gốc"] --> B["Working set: node vừa tìm"]
    B --> C["Recursive member: tìm node con"]
    C --> D{"Có node mới?"}
    D -->|"Có"| E["Thêm kết quả và tiếp tục"]
    E --> B
    D -->|"Không"| F["Kết thúc, trả toàn bộ tập"]
~~~

## 6. Entity mẫu cho cây tổ chức

Giả sử entity `OrgUnit`:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "org_units")
public class OrgUnit {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "parent_id")
    private OrgUnit parent;

    protected OrgUnit() {}

    public OrgUnit(String name, OrgUnit parent) {
        this.name = name;
        this.parent = parent;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public OrgUnit getParent() {
        return parent;
    }
}
~~~

Schema minh họa:

~~~sql
CREATE TABLE org_units (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    parent_id BIGINT NULL,
    CONSTRAINT fk_org_unit_parent
        FOREIGN KEY (parent_id) REFERENCES org_units(id)
);

CREATE INDEX idx_org_units_parent
    ON org_units(parent_id);
~~~

`parent_id` tạo quan hệ tự tham chiếu. Chỉ với khóa ngoại này, database biết parent tồn tại nhưng **không tự chứng minh dữ liệu không có cycle**.

Ví dụ có thể xảy ra nếu nghiệp vụ cho phép cập nhật parent tùy ý:

~~~text
A.parent = B
B.parent = C
C.parent = A
~~~

Đó là đồ thị có chu trình, không còn là cây đúng nghĩa. Truy vấn đệ quy cần tính tới tình huống này.

## 7. Recursive CTE trong HQL: anchor + UNION ALL

HQL Hibernate hỗ trợ cú pháp đệ quy theo cấu trúc:

~~~hql
with Subtree as (
    select root.id as id,
           root.name as name,
           0 as depth
    from OrgUnit root
    where root.id = :rootId

    union all

    select child.id as id,
           child.name as name,
           parent.depth + 1 as depth
    from Subtree parent
    join OrgUnit child
      on child.parent.id = parent.id
)
select s.id, s.name, s.depth
from Subtree s
order by s.depth, s.id
~~~

Đây là ví dụ dành cho **HQL hỗ trợ CTE trong Hibernate 6.2+**, không phải JPQL thuần. Lưu ý tên property như `child.parent.id` là HQL property path; không viết `child.parent_id` nếu entity không có property đó.

### 7.1. Anchor query

~~~hql
select root.id as id,
       root.name as name,
       0 as depth
from OrgUnit root
where root.id = :rootId
~~~

Anchor chọn node bắt đầu, gán độ sâu bằng 0.

Nếu muốn lấy mọi node gốc của toàn cây:

~~~hql
where root.parent is null
~~~

Nếu ứng dụng có tenant hoặc phân quyền theo cây, anchor phải lọc chính xác tập node mà người dùng được quyền truy cập; đừng bắt đầu từ tất cả roots nếu không có lý do.

### 7.2. Recursive member

~~~hql
select child.id as id,
       child.name as name,
       parent.depth + 1 as depth
from Subtree parent
join OrgUnit child
  on child.parent.id = parent.id
~~~

`Subtree parent` là nguồn CTE từ vòng trước, còn `OrgUnit child` là entity mapping thông thường. Điều kiện JOIN tìm các node có parent tương ứng với node đã được phát hiện.

Mỗi vòng sinh ra các hàng mới, tăng độ sâu thêm 1.

### 7.3. Vì sao dùng UNION ALL?

`UNION ALL` giữ các hàng của anchor và recursive member, không tự loại trùng toàn bộ hàng như `UNION`.

Trong duyệt cây đúng nghĩa, một node có một parent và việc sinh row theo mỗi tầng thường phù hợp với `UNION ALL`. Nó tránh chi phí loại trùng không cần thiết.

Tuy nhiên, `UNION ALL` sẽ lặp vô hạn hoặc phát sinh nhiều hàng lặp nếu có cycle mà không có cơ chế dừng. `UNION` có thể loại các hàng trùng hoàn toàn, nhưng **không phải cách chống cycle đáng tin** nếu projection có `depth` thay đổi mỗi vòng, vì cùng node với độ sâu khác vẫn là hàng khác nhau.

### 7.4. Không thêm từ khóa WITH RECURSIVE vào HQL một cách máy móc

Trong SQL của PostgreSQL hoặc một số database, CTE đệ quy thường viết:

~~~sql
WITH RECURSIVE ...
~~~

Nhưng HQL Hibernate hỗ trợ cú pháp `WITH ... AS (...)` và nhận biết sự tự tham chiếu của CTE; ví dụ HQL ở trên **không yêu cầu từ khóa `RECURSIVE`**. Hibernate sẽ tạo SQL phù hợp dialect, trong đó từ khóa `RECURSIVE` có thể được thêm khi database yêu cầu.

Đừng sao chép nguyên văn SQL native vào HQL mà chưa kiểm tra grammar HQL.

## 8. Gọi recursive CTE từ Java

Một cách sử dụng `EntityManager`:

~~~java
public record OrgUnitTreeRow(
    Long id,
    String name,
    int depth
) {}
~~~

~~~java
String hql = """
    with Subtree as (
        select root.id as id,
               root.name as name,
               0 as depth
        from OrgUnit root
        where root.id = :rootId

        union all

        select child.id as id,
               child.name as name,
               parent.depth + 1 as depth
        from Subtree parent
        join OrgUnit child
          on child.parent.id = parent.id
    )
    select s.id, s.name, s.depth
    from Subtree s
    order by s.depth, s.id
    """;

List<Object[]> rows = entityManager
    .createQuery(hql, Object[].class)
    .setParameter("rootId", rootId)
    .getResultList();

List<OrgUnitTreeRow> result = rows.stream()
    .map(row -> new OrgUnitTreeRow(
        (Long) row[0],
        (String) row[1],
        ((Number) row[2]).intValue()
    ))
    .toList();
~~~

Ví dụ giả định `id` được ánh xạ thành `Long`. Với hệ thống thật, kiểu số trả về cho biểu thức tính toán có thể khác theo provider/dialect; `Number.intValue()` giúp chuyển độ sâu sang `int` trong DTO.

Truy vấn trả về **projection**, không phải một danh sách `OrgUnit` managed đầy đủ. Nếu sau đó cần thao tác cập nhật entity, hãy tải entity cần thiết trong transaction thay vì giả định CTE đã tạo một object graph managed.

### 8.1. Nếu rootId không tồn tại

Anchor trả 0 hàng, nên recursive member không có dữ liệu để mở rộng. Kết quả toàn query rỗng. Tùy API, có thể trả danh sách rỗng hoặc phân biệt rõ root không tồn tại bằng một phép kiểm tra trước đó.

### 8.2. Nếu root có nhiều nhánh

Recursive member sinh toàn bộ child thỏa điều kiện cho từng parent ở working set. CTE không chỉ đi theo một đường tới node lá, mà có thể lấy **toàn bộ cây con**.

### 8.3. Độ sâu trong ví dụ

- Root: depth 0.
- Con trực tiếp: depth 1.
- Cháu: depth 2.
- Cấp tiếp theo: depth 3, v.v.

Độ sâu là kết quả logic do query tính; không bắt buộc lưu một cột depth trong bảng `org_units`.

## 9. Bảo vệ đệ quy khỏi cycle

Nếu dữ liệu chứa A → B → C → A, một recursive CTE dùng `UNION ALL` có thể sinh:

~~~text
A depth 0
B depth 1
C depth 2
A depth 3
B depth 4
C depth 5
...
~~~

Tình huống này có thể tiêu tốn tài nguyên hoặc khiến database dừng query vì đạt giới hạn đệ quy. **Không giả định cấu trúc parent–child luôn hợp lệ** chỉ vì có foreign key.

### 9.1. Mệnh đề CYCLE trong HQL

Hibernate hỗ trợ cú pháp `CYCLE` cho recursive CTE:

~~~hql
with Subtree as (
    select root.id as id,
           root.name as name,
           0 as depth
    from OrgUnit root
    where root.id = :rootId

    union all

    select child.id as id,
           child.name as name,
           parent.depth + 1 as depth
    from Subtree parent
    join OrgUnit child
      on child.parent.id = parent.id
)
cycle id set isCycle to true default false
select s.id, s.name, s.depth, s.isCycle
from Subtree s
order by s.depth, s.id
~~~

Ở đây:

- `id` là trường trong CTE dùng làm khóa phát hiện cycle.
- `isCycle` là trường phụ do `CYCLE` tạo.
- Giá trị `true` biểu thị cycle theo semantics của clause.
- Engine có thể dừng mở rộng nhánh đã phát hiện cycle.

Cú pháp `CYCLE` và khả năng sinh SQL tương ứng phụ thuộc Hibernate/dialect. Hibernate có thể mô phỏng `CYCLE` khi DB hỗ trợ đệ quy nhưng không hỗ trợ clause CYCLE trực tiếp, tùy khả năng dialect.

### 9.2. CYCLE không thay validation cây

Tốt nhất vẫn phải kiểm tra khi cập nhật parent:

- Không cho node làm parent của chính nó.
- Không cho một node trỏ về descendant của chính nó.
- Giữ quan hệ trong đúng tenant/miền dữ liệu.
- Có transaction và concurrency control phù hợp.

`CYCLE` giúp truy vấn an toàn hơn khi dữ liệu có lỗi hoặc cấu trúc thật sự là graph, nhưng không phải lý do để bỏ validation nghiệp vụ.

### 9.3. Giới hạn độ sâu

Một lớp bảo vệ bổ sung:

~~~hql
with Subtree as (
    select root.id as id,
           root.name as name,
           0 as depth
    from OrgUnit root
    where root.id = :rootId

    union all

    select child.id as id,
           child.name as name,
           parent.depth + 1 as depth
    from Subtree parent
    join OrgUnit child
      on child.parent.id = parent.id
    where parent.depth < :maxDepth
)
select s.id, s.name, s.depth
from Subtree s
~~~

`:maxDepth` giới hạn độ sâu trả về, ví dụ 10. Điều này giúp chặn recursion quá sâu nhưng **không tự phân biệt** cây hợp lệ với cycle, và có thể làm thiếu node nếu dữ liệu thật sự sâu hơn giới hạn.

Đặt giới hạn phù hợp nghiệp vụ, kết hợp kiểm tra cycle khi cần.

## 10. SEARCH: thứ tự duyệt chiều sâu và chiều rộng

Trong truy vấn cây, đôi khi muốn kết quả theo **depth-first** (duyệt sâu trước) hoặc **breadth-first** (duyệt rộng trước).

HQL hỗ trợ `SEARCH` trong recursive CTE; ví dụ:

~~~hql
with Tree as (
    select root.id as id,
           root.name as name
    from OrgUnit root
    where root.id = :rootId

    union all

    select child.id as id,
           child.name as name
    from Tree parent
    join OrgUnit child
      on child.parent.id = parent.id
)
search depth first by id set traversalOrder
select t.id, t.name
from Tree t
order by t.traversalOrder
~~~

Đổi sang breadth-first:

~~~hql
with Tree as (
    select root.id as id,
           root.name as name
    from OrgUnit root
    where root.id = :rootId

    union all

    select child.id as id,
           child.name as name
    from Tree parent
    join OrgUnit child
      on child.parent.id = parent.id
)
search breadth first by id set traversalOrder
select t.id, t.name
from Tree t
order by t.traversalOrder
~~~

Ở đây `traversalOrder` là trường phụ do `SEARCH` tạo để hỗ trợ sắp xếp.

**Điểm dễ nhầm:** `SEARCH` định nghĩa thứ tự logic của duyệt và trường để sắp xếp; ứng dụng vẫn nên có `ORDER BY traversalOrder` nếu cần **thứ tự result set ổn định**. Đừng dựa vào thứ tự hàng ngẫu nhiên của SQL engine.

### 10.1. SEARCH không giống ORDER BY depth

`ORDER BY depth, id` sắp theo cấp, gần với breadth-first cho cây đơn giản nhưng không tự mã hóa toàn bộ path/order của traversal. `SEARCH DEPTH FIRST` có thể xây dựng thứ tự duyệt sâu dựa trên các trường quy định.

Khi chỉ cần hiển thị nhóm theo depth, một cột depth tự tính có thể đủ. Khi cần thứ tự traversal rõ ràng, `SEARCH` có ý nghĩa hơn.

### 10.2. Khả năng hỗ trợ phụ thuộc dialect

Không phải database nào cũng hỗ trợ cú pháp SQL `SEARCH` trực tiếp. Hibernate có cơ chế mô phỏng search clause trên những database phù hợp trong một số trường hợp. Tuy nhiên, nếu bản thân database không hỗ trợ recursive CTE, việc mô phỏng `SEARCH` không làm recursive query trở nên khả thi.

Luôn kiểm tra SQL được sinh ra và test trên database thật của hệ thống.

## 11. CYCLE và SEARCH có thể kết hợp

Một bài toán duyệt graph có thể cần cả:

- Thứ tự duyệt phù hợp cho UI.
- Phát hiện vòng lặp dữ liệu để tránh đệ quy vô hạn.

Cấu trúc HQL có thể gồm cả `SEARCH` và `CYCLE` sau định nghĩa CTE:

~~~hql
with Tree as (
    select root.id as id,
           root.name as name
    from OrgUnit root
    where root.id = :rootId

    union all

    select child.id as id,
           child.name as name
    from Tree parent
    join OrgUnit child
      on child.parent.id = parent.id
)
search breadth first by id set traversalOrder
cycle id set isCycle to true default false
select t.id, t.name, t.isCycle
from Tree t
order by t.traversalOrder
~~~

Nếu dùng `SEARCH` và `CYCLE` cùng lúc, hãy kiểm tra khả năng dịch cú pháp của dialect và giới hạn database. Các cột phụ `traversalOrder` và `isCycle` do CTE định nghĩa không phải field thật trong entity OrgUnit.

### 11.1. Cycle marker có thể nằm ở hàng nào?

Khi phát hiện một node lặp trên đường duyệt, provider/database có thể trả về hàng đánh dấu cycle và dừng mở rộng từ đó, tùy semantics của clause. Không nên mặc định hàng bị lặp luôn bị loại hoàn toàn khỏi kết quả. Nếu UI chỉ muốn node không tạo cycle, có thể lọc `isCycle = false` theo kiểu dữ liệu và cú pháp HQL phù hợp.

### 11.2. Khóa phát hiện cycle

Trong ví dụ, mỗi OrgUnit có ID duy nhất nên `cycle id` phù hợp. Với graph có trạng thái bổ sung, cần xác định khóa đủ để nhận diện một node/trạng thái. Chọn trường không đủ phân biệt có thể chặn nhánh hợp lệ; chọn trường luôn thay đổi như depth có thể khiến cycle không được phát hiện như mong muốn.

## 12. Phân biệt HQL CTE với SQL native

Ví dụ HQL:

~~~hql
with Tree as (
    select n.id as id,
           n.name as name,
           0 as depth
    from OrgUnit n
    where n.id = :rootId

    union all

    select c.id as id,
           c.name as name,
           p.depth + 1 as depth
    from Tree p
    join OrgUnit c on c.parent.id = p.id
)
select id, name, depth
from Tree
~~~

Còn trên PostgreSQL, SQL native có thể viết:

~~~sql
WITH RECURSIVE tree(id, name, depth) AS (
    SELECT id, name, 0
    FROM org_units
    WHERE id = :rootId

    UNION ALL

    SELECT c.id, c.name, p.depth + 1
    FROM tree p
    JOIN org_units c ON c.parent_id = p.id
)
SELECT id, name, depth
FROM tree;
~~~

Các khác biệt quan trọng:

| Nội dung | HQL | SQL native |
| --- | --- | --- |
| Tên nguồn dữ liệu | `OrgUnit` entity name | `org_units` table name |
| Quan hệ parent | `c.parent.id` property path | `c.parent_id` column |
| Đệ quy | `WITH Tree AS (...)` tự tham chiếu | Nhiều DB dùng `WITH RECURSIVE` |
| Tính di động | Phụ thuộc Hibernate HQL + dialect | Phụ thuộc SQL dialect của DB |
| Kết quả | HQL projection/entity tùy select | Native result mapping/projection |
| Hỗ trợ SEARCH/CYCLE | Hibernate có thể dịch/mô phỏng | Tùy DB hỗ trợ trực tiếp |

Nếu Hibernate/dialect không hỗ trợ tạo SQL đệ quy phù hợp cho database đang dùng, native SQL cũng **không thể vượt qua việc DB không có tính năng recursive CTE**; lúc đó phải dùng chiến lược khác hoặc một tính năng đặc thù của DB.

### 12.1. Khi nào native SQL phù hợp hơn?

Native SQL đáng cân nhắc khi:

- Cần hint riêng của database không được HQL diễn đạt.
- Cần các hàm path/array/JSON đặc thù.
- Cần truy vấn graph với tính năng đặc thù như `CONNECT BY` ở một hệ quản trị.
- Cần tối ưu query dựa trên execution plan riêng.
- Phải hỗ trợ Hibernate version chưa có HQL CTE tương ứng.

Đổi lại, native SQL cần test theo từng DB, tự quản lý tên bảng/cột và ánh xạ kết quả.

## 13. Database có hỗ trợ CTE không?

CTE không đệ quy và CTE đệ quy là hai mức năng lực khác nhau. Hibernate có thể rewrite một số CTE không đệ quy thành subquery khi DB không có CTE native. Nhưng recursive CTE cần SQL engine có khả năng xử lý đệ quy.

Theo Hibernate dialect, có thể tồn tại các capability tương ứng như:

- `supportsRecursiveCTE()`
- `supportsRecursiveSearchClause()`
- `supportsRecursiveCycleClause()`

Đây là thông tin nội bộ/API dialect, không phải lời hứa rằng mọi cấu hình mọi phiên bản hỗ trợ giống nhau. Hãy dùng dialect chính xác của DB và phiên bản Hibernate để kiểm chứng.

### 13.1. Kiểm tra theo các bước

1. Xác định Hibernate ORM version.
2. Xác định database product và version.
3. Xác định Hibernate dialect đang được sử dụng.
4. Thử một CTE không đệ quy đơn giản.
5. Thử recursive CTE với cây nhỏ, không cycle.
6. Thử trường hợp có cycle và `CYCLE` nếu cần.
7. Kiểm tra SQL được Hibernate sinh ra.
8. Chạy trên DB thật trong integration test, không chỉ DB in-memory.
9. Kiểm tra giới hạn recursion của DB.
10. Đo execution plan với tập dữ liệu lớn.

### 13.2. JPQL compliance mode

CTE là một extension của HQL so với JPQL truyền thống. Nếu ứng dụng bật chế độ strict JPQL compliance của Hibernate, truy vấn dùng extension có thể bị từ chối.

Đừng mặc định một query chạy trong `EntityManager.createQuery()` tức là cú pháp JPQL portable. API EntityManager có thể chạy HQL extension của Hibernate khi Hibernate là JPA provider.

## 14. Hiệu năng và chỉ mục cho truy vấn cây

Recursive CTE có thể hiệu quả khi được thiết kế đúng, nhưng không phải lúc nào cũng rẻ.

### 14.1. Index trên khóa parent

Ở recursive member:

~~~hql
join OrgUnit child
  on child.parent.id = parent.id
~~~

SQL thường cần tìm child theo `parent_id`. Chỉ mục:

~~~sql
CREATE INDEX idx_org_units_parent
ON org_units(parent_id);
~~~

có thể giúp truy vấn tìm con nhanh hơn, tùy kích thước bảng, phân phối dữ liệu và optimizer.

Không nhất thiết index này giải quyết mọi performance issue; vẫn cần kiểm tra `EXPLAIN`, số hàng thực và lock/IO.

### 14.2. Giới hạn điểm bắt đầu

Nếu chỉ cần cây con của một root, dùng:

~~~hql
where root.id = :rootId
~~~

trong anchor thay vì lấy mọi root. Giới hạn seed sớm giúp giảm lượng node được mở rộng.

### 14.3. Giới hạn độ sâu khi nghiệp vụ cho phép

Điều kiện `parent.depth < :maxDepth` trong recursive member giúp giới hạn work. Nhưng phải xác định rõ UI cần **toàn bộ cây** hay chỉ 2–3 cấp. Giới hạn ngầm có thể khiến người dùng không thấy node sâu hơn.

### 14.4. Chỉ project những cột cần thiết

Nếu cần id, tên và depth:

~~~hql
select s.id, s.name, s.depth
from Subtree s
~~~

Không nhất thiết tải toàn bộ OrgUnit entity, mọi association hoặc collection để dựng cây cho màn hình. Projection giúp giảm lượng dữ liệu qua JDBC và tránh tự phát sinh N+1 do serializer truy cập entity lazy.

### 14.5. LIMIT ngoài query có thể không giới hạn recursion

Viết:

~~~hql
select s.id, s.name
from Subtree s
order by s.depth
limit 100
~~~

không bảo đảm database chỉ mở rộng 100 node trước khi dừng. Tùy execution plan, database có thể phải tạo hoặc sắp xếp nhiều kết quả của recursive CTE trước khi áp dụng LIMIT.

Khi cần chống query quá rộng, đặt điều kiện trong anchor/recursive member, giới hạn độ sâu, xác thực input và áp dụng query timeout phù hợp.

## 15. CTE và transaction, tính nhất quán dữ liệu

Một recursive CTE đọc một snapshot/hàng tập hợp theo isolation của transaction đang chạy. Nếu transaction khác sửa cây cùng lúc, tính nhất quán của kết quả có thể phụ thuộc database MVCC, locking và isolation level.

Ví dụ khi ứng dụng đang đọc descendant nodes, transaction khác có thể chuyển một node sang parent khác. Truy vấn đệ quy không tự đặt pessimistic lock trên mọi node chỉ vì nó đang duyệt cây.

Nếu dùng kết quả để thực hiện thao tác quan trọng như:

- Xóa toàn bộ cây con.
- Thay đổi phân quyền theo nhánh.
- Di chuyển danh mục có nhiều node con.
- Tính hạn mức tổng trên cây.

thì cần thiết kế transaction và concurrency control bảo vệ invariant, không chỉ dựa vào việc recursive CTE trả danh sách ID.

### 15.1. CTE đọc không có nghĩa dữ liệu luôn mới nhất

Persistence context Hibernate có thể đã giữ entity managed từ trước. Một CTE projection đọc trực tiếp kết quả query có thể có semantics khác với các entity đã managed. Nếu trộn truy vấn CTE với việc sửa entity trong cùng transaction, lưu ý flush mode, isolation và managed state.

### 15.2. CTE không tự commit

`EntityManager.createQuery()` cho một CTE đọc không tự kết thúc transaction. Nếu ứng dụng thực hiện DML sau đó, commit/rollback vẫn do transaction boundary quản lý.

## 16. Bài toán đa tenant và an toàn truy vấn

Trong hệ thống đa tenant, một cây có thể chứa các node thuộc nhiều tenant. Truy vấn chỉ lọc anchor chưa chắc đủ nếu dữ liệu sai hoặc mapping cho phép liên kết cross-tenant.

Ví dụ có thuộc tính `tenantId` trên OrgUnit:

~~~hql
with Subtree as (
    select root.id as id,
           root.tenantId as tenantId,
           0 as depth
    from OrgUnit root
    where root.id = :rootId
      and root.tenantId = :tenantId

    union all

    select child.id as id,
           child.tenantId as tenantId,
           parent.depth + 1 as depth
    from Subtree parent
    join OrgUnit child
      on child.parent.id = parent.id
    where child.tenantId = :tenantId
)
select s.id, s.depth
from Subtree s
~~~

Điều kiện tenant trong cả anchor và recursive member giúp tránh mở rộng qua node không thuộc tenant dự định. Thiết kế database cũng nên có constraint phù hợp để cấm liên kết parent–child sai tenant, thay vì chỉ dựa vào query.

### 16.1. Bind parameter, không nối chuỗi HQL từ input

Không tạo query bằng cách nối trực tiếp `rootId`, `tenantId` hoặc điều kiện tùy ý từ client vào HQL. Sử dụng named parameter:

~~~java
query.setParameter("rootId", rootId);
query.setParameter("tenantId", tenantId);
~~~

Tên CTE/alias nên do code cố định, không cho input người dùng tự quyết định biểu thức HQL tùy ý.

### 16.2. Tránh request không giới hạn

Một API nhận rootId bất kỳ rồi duyệt toàn bộ graph lớn có thể tạo truy vấn rất đắt. Có thể áp dụng:

- Kiểm tra quyền truy cập root.
- Giới hạn độ sâu hoặc số node theo nghiệp vụ.
- Query timeout.
- Pagination/lazy expansion ở tầng UI.
- Tách các workload phân tích lớn sang job bất đồng bộ.
- Metrics và cảnh báo truy vấn chậm.

## 17. Khi không hỗ trợ recursive CTE thì làm gì?

Nếu database không hỗ trợ recursive CTE, Hibernate không thể mô phỏng đệ quy chỉ bằng cách chuyển HQL sang subquery thông thường.

Các lựa chọn thay thế:

### 17.1. Duyệt theo từng tầng trong Java

Thuật toán breadth-first khái quát:

~~~text
result  = []
frontier = [rootId]
visited = set()

while frontier không rỗng:
    nextFrontier = []
    query tất cả child WHERE parent_id IN frontier

    for child:
        nếu child.id chưa thuộc visited:
            thêm child vào result
            đánh dấu visited
            thêm child.id vào nextFrontier

    frontier = nextFrontier
~~~

Có thể batch truy vấn theo từng tầng thay vì một query cho từng node, giảm N+1. Phải có visited set để tránh cycle, giới hạn độ sâu/nodes và lưu ý giới hạn số parameter trong `IN`.

Nhược điểm là nhiều round-trip phụ thuộc độ sâu và cần duy trì một góc nhìn dữ liệu nhất quán giữa các truy vấn nếu có concurrent updates.

### 17.2. Closure table

Lưu quan hệ ancestor–descendant trong bảng riêng:

~~~sql
CREATE TABLE org_unit_closure (
    ancestor_id BIGINT NOT NULL,
    descendant_id BIGINT NOT NULL,
    depth INTEGER NOT NULL,
    PRIMARY KEY (ancestor_id, descendant_id)
);
~~~

Khi cần toàn bộ descendants:

~~~sql
SELECT descendant_id, depth
FROM org_unit_closure
WHERE ancestor_id = ?;
~~~

Ưu điểm: truy vấn descendant/ancestor rất nhanh với index phù hợp. Nhược điểm: thêm hoặc di chuyển một nhánh cần cập nhật nhiều hàng closure table một cách nhất quán.

### 17.3. Materialized path

Lưu đường dẫn tổ tiên, ví dụ:

~~~text
/1/4/9/
~~~

Tìm descendants theo prefix có thể nhanh với index và kiểu dữ liệu/path phù hợp. Nhưng đổi parent có thể yêu cầu cập nhật path của toàn bộ nhánh; cách query/index phụ thuộc DB.

### 17.4. Nested set

Lưu hai giá trị left/right để biểu diễn thứ tự duyệt trong cây. Descendant query có thể dựa vào khoảng, nhưng thêm, xóa hoặc di chuyển node thường phức tạp hơn và gây nhiều update.

### 17.5. Tính năng cây riêng của DB

Một số database có tính năng hierarchical query riêng như `CONNECT BY`. Nếu dùng, cần native SQL hoặc API hỗ trợ, chấp nhận vendor lock-in và kiểm thử riêng. Hibernate HQL không biến tất cả những tính năng đặc thù thành một cú pháp portable duy nhất.

## 18. So sánh các phương án biểu diễn cây

| Phương án | Đọc descendants | Cập nhật cây | Portability | Điểm cần nhớ |
| --- | --- | --- | --- | --- |
| Adjacency list + recursive CTE | Tốt nếu DB hỗ trợ | Thường sửa parent_id | HQL phụ thuộc dialect recursive CTE | Đơn giản, dễ quản lý schema |
| Java traversal theo tầng | Nhiều query theo depth | Thường sửa parent_id | Cao với JPQL/SQL cơ bản | Cần visited set, batching và consistency |
| Closure table | Truy vấn descendant nhanh | Cập nhật closure phức tạp | Khá cao với SQL phổ biến | Tốn thêm bảng/ghi |
| Materialized path | Prefix/path query | Di chuyển nhánh có thể tốn cập nhật | Phụ thuộc kiểu path/index | Hữu ích khi đọc nhiều |
| Nested set | Range query | Cập nhật cây đắt | SQL tương đối phổ biến | Phù hợp cây ít thay đổi |
| Native hierarchical SQL | Theo khả năng DB | Tùy mô hình | Thấp | Dùng feature đặc thù DB |

Không có mô hình tốt nhất cho mọi hệ thống. Chọn theo số node, độ sâu, số lần đọc/ghi, thao tác di chuyển và khả năng database.

## 19. Các lỗi thường gặp khi viết HQL CTE

| Tình huống | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Parser từ chối `WITH` | Hibernate quá cũ hoặc strict JPQL compliance | Xác định Hibernate version và chế độ HQL |
| HQL dùng `WITH RECURSIVE` như PostgreSQL | Lẫn cú pháp SQL native với HQL | Dùng `WITH ... AS (...)` theo Hibernate HQL |
| Tên `org_units` trong HQL không được nhận | Dùng tên bảng thay entity | Dùng `OrgUnit` entity name |
| Dùng `parent_id` như property HQL | Lẫn cột SQL với property Java | Dùng `child.parent.id` |
| Không khai báo alias cho field CTE | CTE field không truy cập rõ ràng | Đặt `AS id`, `AS depth`, ... |
| UNION/UNION ALL có số cột khác nhau | Anchor và recursive member không tương thích | Đồng nhất số lượng, thứ tự và kiểu biểu thức |
| Không dừng khi có cycle | Đồ thị có vòng lặp, UNION ALL tiếp tục mở rộng | Dùng CYCLE, visited set, depth guard |
| Dùng UNION để mong chắc chắn hết cycle | Các hàng có depth khác nhau vẫn khác | Chọn cycle detection đúng khóa |
| `SEARCH` được khai báo nhưng kết quả không có thứ tự | Thiếu ORDER BY trên trường search | ORDER BY traversalOrder |
| Recursive CTE không chạy trên DB | Dialect/database không hỗ trợ recursion | Chọn DB/mô hình/thuật toán thay thế |
| Materialization hint không cải thiện tốc độ | Hint không được hỗ trợ hoặc optimizer chọn plan khác | Đo EXPLAIN thay vì dự đoán |
| Query rất chậm trên cây lớn | Thiếu index parent_id hoặc root quá rộng | Thêm index, lọc anchor, giới hạn phạm vi |
| API đọc vượt tenant | Chỉ lọc root hoặc dữ liệu cross-tenant | Ràng buộc cả recursive member |
| LIMIT 100 nhưng query vẫn chậm | DB phải thực hiện recursion trước LIMIT | Giới hạn recursive member và thiết kế query |

## 20. Một service ví dụ: lấy cây con có giới hạn độ sâu

Đối với API hiển thị cây, có thể định nghĩa DTO:

~~~java
public record OrgUnitNodeView(
    Long id,
    String name,
    int depth
) {}
~~~

Service minh họa:

~~~java
@Service
public class OrgUnitQueryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public List<OrgUnitNodeView> findSubtree(
            Long rootId,
            int maxDepth) {

        if (rootId == null) {
            throw new IllegalArgumentException("rootId bắt buộc");
        }
        if (maxDepth < 0 || maxDepth > 20) {
            throw new IllegalArgumentException(
                "maxDepth ngoài phạm vi cho phép");
        }

        String hql = """
            with Subtree as (
                select root.id as id,
                       root.name as name,
                       0 as depth
                from OrgUnit root
                where root.id = :rootId

                union all

                select child.id as id,
                       child.name as name,
                       parent.depth + 1 as depth
                from Subtree parent
                join OrgUnit child
                  on child.parent.id = parent.id
                where parent.depth < :maxDepth
            )
            cycle id set isCycle to true default false
            select s.id, s.name, s.depth
            from Subtree s
            where s.isCycle = false
            order by s.depth, s.id
            """;

        List<Object[]> rows = em.createQuery(hql, Object[].class)
            .setParameter("rootId", rootId)
            .setParameter("maxDepth", maxDepth)
            .getResultList();

        return rows.stream()
            .map(r -> new OrgUnitNodeView(
                (Long) r[0],
                (String) r[1],
                ((Number) r[2]).intValue()
            ))
            .toList();
    }
}
~~~

**Giả định của ví dụ:** Hibernate version và dialect hỗ trợ recursive CTE cùng biểu thức `CYCLE` phù hợp, database thực sự hỗ trợ recursion, `OrgUnit` có các mapping đã mô tả, `rootId` được xác thực quyền ở tầng thích hợp. Nếu dialect không thể xử lý `CYCLE`, dùng cơ chế cycle detection khác hoặc một query chỉ áp dụng cho cây đã được validation không có cycle.

### 20.1. Vì sao giới hạn maxDepth nằm trong recursive member?

Điều kiện:

~~~hql
where parent.depth < :maxDepth
~~~

hạn chế việc mở rộng node tại các tầng sâu hơn. Nếu chỉ lọc `s.depth <= :maxDepth` ở query ngoài, database vẫn có thể thực hiện nhiều bước recursion không cần thiết trước khi áp dụng filter cuối.

### 20.2. Nếu muốn trả luôn isCycle

Có thể thêm `s.isCycle` vào `SELECT` và DTO, rồi cho client biết nhánh nào bị chặn vì cycle. Đây là lựa chọn hữu ích cho công cụ quản trị sửa cây lỗi; còn API thông thường có thể chỉ trả các node không bị đánh dấu cycle.

### 20.3. Vì sao không trả thẳng OrgUnit entity?

Một cây có thể chứa hàng nghìn node. Trả entity managed với các association lazy có thể khiến serializer sinh N+1 hoặc kéo theo object graph không kiểm soát. DTO chỉ mang ID, tên, depth giúp giao diện dựng cây mà không cần mọi association.

## 21. Kiểm thử CTE và truy vấn đệ quy

Một bộ integration test nên bao gồm những dữ liệu tối thiểu:

~~~text
A (root)
├── B
│   └── D
└── C
    └── E

F (root khác)
~~~

Các tình huống:

1. **Root A:** kết quả gồm A, B, C, D, E; không có F.
2. **Root B:** kết quả chỉ gồm B và D.
3. **Root không tồn tại:** kết quả rỗng.
4. **maxDepth = 0:** chỉ trả root.
5. **maxDepth = 1:** root và các child trực tiếp.
6. **Node không có child:** trả đúng một hàng.
7. **Cycle:** không treo, phát hiện hoặc từ chối dữ liệu lỗi theo contract.
8. **Nhiều tenant:** không đọc node ngoài tenant.
9. **Dữ liệu lớn:** đo thời gian query và số hàng xử lý.
10. **DB thực tế:** xác nhận SQL và dialect chính xác.

Nếu dùng H2 hoặc database in-memory cho unit test nhưng production dùng PostgreSQL/SQL Server/Oracle, nên có integration test chạy trên cùng database product/version chính của production vì recursive CTE, materialization và search/cycle có thể khác nhau.

### 21.1. Kiểm tra kết quả depth

Với A depth 0, B/C depth 1, D/E depth 2. Kiểm tra cả số node và độ sâu; đừng chỉ assert số hàng, vì một truy vấn bị duplicate đường đi vẫn có thể trùng số hàng trong vài dataset nhỏ.

### 21.2. Kiểm tra query timeout

Với cấu trúc lỗi hoặc root quá rộng, database có thể chạy lâu. Bên cạnh `CYCLE` và giới hạn depth, có thể cấu hình timeout cho query:

~~~java
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

Thời gian tính bằng millisecond theo JPA hint thông dụng; mức độ áp dụng và cách driver cancel query phụ thuộc provider/database. Timeout là lớp bảo vệ bổ sung, không thay validation và giới hạn truy vấn.

## 22. Bài tập thực hành

### Bài 1 — Phân biệt CTE và bảng thật

Đọc HQL:

~~~hql
with ActiveOrders as (
    select o.id as id, o.totalAmount as total
    from PurchaseOrder o
    where o.status = :status
)
select a.id, a.total
from ActiveOrders a
~~~

`ActiveOrders` là entity, table, view hay kết quả trung gian trong phạm vi query? Tại sao không cần tạo `@Entity` cho nó?

### Bài 2 — Hai CTE liên tiếp

Viết query HQL khai báo CTE thống kê số đơn theo customer và CTE thống kê tổng giá trị theo customer, sau đó ghép theo customerId. Cần đặt alias cho những select item nào?

### Bài 3 — Anchor và recursive member

Cho cây A → B → D, A → C. Viết recursive CTE lấy toàn bộ descendants của A cùng độ sâu. Anchor chọn gì? Recursive member nối những dữ liệu nào?

### Bài 4 — UNION và UNION ALL

Vì sao thường dùng `UNION ALL` cho traversal? Nếu dữ liệu có cycle A → B → A và projection có depth tăng mỗi vòng, dùng `UNION` liệu chắc chắn dừng được hay không?

### Bài 5 — SEARCH và CYCLE

Trong truy vấn recursive CTE, `SEARCH BREADTH FIRST` và `CYCLE id` giải quyết hai vấn đề khác nhau ra sao? Vì sao vẫn nên có `ORDER BY traversalOrder`?

### Bài 6 — HQL khác PostgreSQL SQL thế nào?

Một developer chép `WITH RECURSIVE ... FROM org_units ... parent_id` vào `EntityManager.createQuery()`. Hãy giải thích vì sao có thể bị parser từ chối, và cách viết với entity `OrgUnit`/property `parent` theo HQL.

### Bài 7 — Hỗ trợ database

Một database không hỗ trợ recursive CTE. Vì sao Hibernate không thể rewrite truy vấn đệ quy thành subquery thông thường? Đề xuất hai giải pháp thay thế.

### Bài 8 — Hiệu năng và bảo mật

Một API cho phép người dùng nhập rootId để tải toàn bộ cây. Hãy nêu tối thiểu năm biện pháp giúp tránh truy vấn quá lớn hoặc lộ dữ liệu giữa các tenant.

### Bài 9 — Materialization

So sánh `AS MATERIALIZED` và `AS NOT MATERIALIZED`. Tại sao cần dùng execution plan thay vì giả định mọi CTE materialized đều nhanh hơn?

### Bài 10 — Test với dữ liệu lỗi

Một OrgUnit tự đặt parent bằng chính nó. Viết kịch bản test đảm bảo truy vấn không lặp mãi và API trả lỗi hoặc chặn cycle phù hợp.

### Gợi ý trả lời

- **Bài 1:** ActiveOrders là CTE scoped theo query, không phải entity hoặc bảng vật lý bắt buộc.
- **Bài 2:** Đặt alias cho customerId, count, total và dùng các tên đó từ CTE query.
- **Bài 3:** Anchor lấy A depth 0; recursive member tìm child có parent ID bằng ID của CTE từ vòng trước.
- **Bài 4:** UNION ALL tránh loại trùng; UNION không chắc chặn cycle nếu depth thay đổi và hàng không hoàn toàn trùng.
- **Bài 5:** SEARCH điều khiển thứ tự traversal, CYCLE phát hiện lặp; ORDER BY bảo đảm thứ tự result.
- **Bài 6:** HQL dùng entity/property và WITH self-reference; native SQL dùng table/column và có thể cần WITH RECURSIVE.
- **Bài 7:** Recursion đòi engine lặp theo working set; dùng Java BFS có batching hoặc closure table/materialized path.
- **Bài 8:** Kiểm tra quyền root, tenant filter cả anchor/recursive branch, maxDepth, maxNodes, timeout, indexes, metrics và DTO.
- **Bài 9:** Hai hint định hướng materialize/inline; kết quả phụ thuộc optimizer/dialect và phải đo.
- **Bài 10:** Ngăn self-parent khi ghi, dùng CYCLE hoặc visited set và timeout/giới hạn độ sâu khi đọc.

---

## Tóm tắt

**CTE không đệ quy** trong HQL đặt tên cho một tập kết quả trung gian bằng `WITH`, giúp cấu trúc truy vấn phức tạp dễ đọc và tái sử dụng. **Recursive CTE** mở rộng tập kết quả bằng anchor query cộng recursive member qua `UNION ALL`, phù hợp dữ liệu cây/đồ thị; HQL không cần từ khóa SQL `WITH RECURSIVE`.

**Giới hạn quan trọng nhất:** khả năng recursive CTE thực sự phụ thuộc Hibernate version, dialect và database. Hibernate có thể rewrite CTE thông thường nhưng không thể tự mô phỏng recursion khi DB thiếu năng lực đệ quy. Khi dùng recursion, cần kiểm soát cycle, độ sâu, quyền truy cập và hiệu năng; nếu không được hỗ trợ, hãy cân nhắc traversal theo tầng, closure table hoặc mô hình cây khác.

**Tài liệu tham khảo chính thức:** [Hibernate ORM 6.6 — HQL Guide, Common Table Expressions](https://docs.hibernate.org/orm/6.6/querylanguage/html_single/#hql-with).
