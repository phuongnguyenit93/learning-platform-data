# Phân trang đúng với quan hệ đa trị và thứ tự ổn định

Phân trang thường có vẻ đơn giản: sắp xếp một danh sách, rồi lấy `LIMIT` dòng với `OFFSET`. Nhưng khi Hibernate phải tải một entity root cùng một quan hệ **to-many** như `@OneToMany` hoặc `@ManyToMany`, một trang “10 đơn hàng” không còn tương đương 10 dòng SQL.

Một đơn hàng có thể có 0, 1 hoặc 20 dòng chi tiết. Khi `JOIN FETCH` collection, database trả về nhiều dòng cho cùng một đơn hàng. Nếu giới hạn SQL trực tiếp trên kết quả join, một trang có thể bị cắt giữa collection, thiếu root entities hoặc tạo ra kết quả không ổn định. Hibernate có thể phải áp dụng pagination trong bộ nhớ để giữ semantics entity, nhưng cách đó có thể đọc một lượng dữ liệu rất lớn.

Một vấn đề độc lập khác là **thứ tự không ổn định**. `ORDER BY created_at` chưa đủ nếu nhiều bản ghi có cùng timestamp. Khi các trang được đọc, bản ghi có thể lặp lại hoặc bị bỏ sót nếu thứ tự không tạo thành một thứ tự toàn phần. Thêm một khóa duy nhất làm tie-breaker, hoặc dùng keyset pagination với cursor chứa toàn bộ sort keys, giúp xác định ranh giới trang rõ ràng hơn.

Bài học giải thích cách phân trang entity root có collection trong Hibernate/JPA, cách tránh row multiplication, chiến lược hai truy vấn lấy ID rồi fetch graph, count query đúng, sort theo thuộc tính child, keyset pagination, consistency khi dữ liệu thay đổi đồng thời, lựa chọn fetch strategy và cách kiểm thử trên database thật.

---

## 1. Trước hết phải xác định “một dòng trong trang” là gì

Giả sử mô hình:

```text
PurchaseOrder
  id
  orderNumber
  createdAt
  status
  |
  +-- lines: List<OrderLine>
          id
          sku
          quantity
```

Yêu cầu màn hình:

> Hiển thị 20 đơn hàng mới nhất, mỗi đơn hàng kèm toàn bộ các dòng chi tiết.

Đơn vị phân trang là **PurchaseOrder**, không phải `OrderLine`, cũng không phải dòng kết quả của SQL join.

Nếu query:

```sql
SELECT o.*, l.*
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
ORDER BY o.created_at DESC;
```

database có thể trả:

| order_id | created_at | line_id | sku |
| --- | --- | --- | --- |
| 105 | 10:00 | 1 | A |
| 105 | 10:00 | 2 | B |
| 105 | 10:00 | 3 | C |
| 104 | 09:59 | 4 | D |
| 103 | 09:58 | NULL | NULL |

Có 5 SQL rows nhưng chỉ có 3 root orders. Nếu thêm `LIMIT 2`, database chỉ trả hai dòng đầu của Order#105. Trang có thể chứa một order nhưng collection bị cắt nếu ORM diễn giải kết quả trực tiếp.

**Pagination phải giới hạn root IDs trước, rồi mới tải collection**, hoặc dùng một query shape khác bảo đảm database giới hạn root entities trước khi mở rộng collection.

## 2. Vì sao `JOIN FETCH` collection làm nhân số dòng?

JPQL:

```java
select o
from PurchaseOrder o
left join fetch o.lines
order by o.createdAt desc
```

`JOIN FETCH` yêu cầu Hibernate tải collection trong cùng truy vấn. Ở SQL, mỗi cặp root-child tạo ra một row.

Nếu một root có 5 children, root columns được lặp 5 lần. Nếu một root không có child, `LEFT JOIN` tạo một row với các child columns null.

Số dòng SQL gần đúng:

\[
\text{rows} \approx \sum_{o \in roots} \max(1, |children(o)|)
\]

Đây là lý do `setMaxResults(20)` trên một query fetch collection không tự nhiên có nghĩa “20 roots”.

### 2.1. Ví dụ một trang bị cắt giữa collection

Giả sử SQL:

```sql
SELECT o.id, o.created_at, l.id, l.sku
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
ORDER BY o.created_at DESC
LIMIT 3 OFFSET 0;
```

Kết quả:

```text
Order#105 + Line#1
Order#105 + Line#2
Order#105 + Line#3
```

Trang có 3 SQL rows nhưng chỉ có 1 order. Nếu giới hạn cắt sau Line#2, ORM không thể coi đó là toàn bộ collection của Order#105.

Với fetch join collection, Hibernate có thể cảnh báo và thực hiện pagination trong memory để không trả collection bị cắt theo cách sai semantics. Khi đó ứng dụng có thể tải nhiều hoặc toàn bộ kết quả join rồi mới chọn page root entities.

**Đừng dựa vào việc Hibernate “tự xử lý” như một giải pháp hiệu năng.** Hãy thiết kế query để giới hạn root trước khi fetch collection.

## 3. Hibernate có thể paginate trong memory

Một query kiểu:

```java
List<PurchaseOrder> page = em.createQuery("""
    select o
    from PurchaseOrder o
    left join fetch o.lines
    order by o.createdAt desc
    """, PurchaseOrder.class)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

có thể khiến Hibernate:
1. Thực thi SQL fetch join mà không có SQL-level limit như mong muốn.
2. Đọc tất cả rows liên quan.
3. Khử trùng lặp root entities và hydrate collections.
4. Áp dụng offset/limit trong bộ nhớ.

Hệ quả: page 20 orders vẫn có thể đọc hàng trăm nghìn joined rows. Database chịu tải, JDBC chuyển nhiều dữ liệu, heap tăng và latency khó dự đoán.

### 3.1. Bật fail-fast để không vô tình chạy query nguy hiểm

Hibernate cung cấp setting:

```properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Hoặc Hibernate setting trực tiếp:

```properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
```

Khi pagination kết hợp collection fetch join dẫn đến xử lý in-memory, setting này giúp query fail thay vì âm thầm chạy theo đường tốn kém.

Tên property và behavior cần xác nhận trên Hibernate version đang dùng. Trong ứng dụng Spring Boot, prefix `spring.jpa.properties.` chuyển property xuống Hibernate.

**Đây là guardrail hữu ích trong development/test**, đặc biệt khi code review không dễ nhận ra một repository method vừa `Pageable` vừa fetch collection.

## 4. `DISTINCT` có giải quyết được pagination collection fetch không?

JPQL:

```java
select distinct o
from PurchaseOrder o
left join fetch o.lines
order by o.createdAt desc
```

`DISTINCT` có thể giúp kết quả entity root không bị lặp trong một số semantics/provider versions. Hibernate 6 cũng có cơ chế tự khử trùng lặp entity results của fetch joins trong nhiều trường hợp.

Nhưng điều đó **không làm SQL row multiplication biến mất**.

Nếu SELECT gồm columns của cả order và line:

```text
order columns + line columns
```

thì mỗi line có giá trị khác nhau; SQL `DISTINCT` vẫn giữ các rows khác nhau. Database vẫn không thể dùng `LIMIT 20` để có 20 roots hoàn chỉnh chỉ bằng cách loại duplicate rows.

Vì vậy:
- `DISTINCT` không thay thế chiến lược phân trang root IDs.
- Không dựa vào việc ORM deduplicate sau khi đọc để chứng minh query hiệu quả.
- Kiểm tra SQL thật, execution plan và số rows được đọc.

## 5. Quan hệ to-one và to-many khác nhau

Một `@ManyToOne` hoặc `@OneToOne` được mapping đúng thường không nhân số root rows vì mỗi root có tối đa một target tương ứng.

Ví dụ:

```java
select o
from PurchaseOrder o
left join fetch o.customer
order by o.createdAt desc, o.id desc
```

thường có thể kết hợp root pagination vì join không làm mỗi order xuất hiện nhiều lần.

Ngược lại:

```java
select o
from PurchaseOrder o
left join fetch o.lines
```

có thể nhân số rows theo số line.

### 5.1. Mapping phải phản ánh đúng cardinality vật lý

Nếu code khai báo `@OneToOne` nhưng database không có unique constraint bảo đảm tối đa một target, join thực tế có thể nhân rows. Query planner và Hibernate mapping đang dựa vào một giả định sai.

Đối với to-one association, bảo đảm:
- FK và uniqueness đúng.
- Cardinality của dữ liệu phù hợp mapping.
- Không có dữ liệu legacy vi phạm giả định one-to-one.

## 6. Thứ tự ổn định: `ORDER BY` phải xác định duy nhất từng root

Query:

```sql
SELECT id, created_at
FROM purchase_orders
ORDER BY created_at DESC
LIMIT 20 OFFSET 20;
```

không có thứ tự duy nhất nếu nhiều orders cùng `created_at`.

Ví dụ:

```text
Order#101 created_at=10:00
Order#102 created_at=10:00
Order#103 created_at=10:00
```

Database có thể trả các rows bằng bất kỳ thứ tự nào giữa các giá trị bằng nhau, tùy execution plan, index, parallelism và physical layout.

Trang 1 và trang 2 có thể lặp/mất order dù không có transaction nào thay đổi dữ liệu.

### 6.1. Thêm unique tie-breaker

Một thứ tự ổn định hơn:

```sql
ORDER BY created_at DESC, id DESC
```

Vì `id` duy nhất, cặp `(created_at, id)` xác định thứ tự cho mỗi root.

JPQL:

```java
select o.id
from PurchaseOrder o
where o.tenantId = :tenantId
order by o.createdAt desc, o.id desc
```

**Mọi sort definition dùng để phân trang nên kết thúc bằng một hoặc nhiều khóa tạo tính duy nhất**, thường là primary key.

### 6.2. `ORDER BY id` đơn lẻ có thể đủ

Nếu yêu cầu chỉ cần thứ tự theo ID, `ORDER BY id ASC` tạo total order vì ID duy nhất. Không nhất thiết phải sort thêm timestamp.

Nhưng nếu yêu cầu “mới nhất trước”, cần sort timestamp trước rồi ID làm tie-breaker.

## 7. Null ordering cũng thuộc sort contract

Nếu `created_at` nullable, thứ tự của null có thể khác giữa DBMS/dialect hoặc chiều sort.

PostgreSQL hỗ trợ:

```sql
ORDER BY created_at DESC NULLS LAST, id DESC
```

Không nên dựa vào default null ordering nếu pagination cần nhất quán giữa môi trường.

Một lựa chọn tốt hơn với dữ liệu nghiệp vụ là đặt `created_at NOT NULL` nếu bản ghi luôn phải có thời điểm tạo.

Nếu phải cho phép null:
- Quy định null đứng đầu hay cuối.
- Đưa quy tắc đó vào mọi page query và cursor.
- Dùng expression/index phù hợp.
- Test cả rows null và non-null.

### 7.1. Cursor phải encode null rank

Keyset pagination trên nullable sort field phải biết cursor nằm ở nhóm null hay non-null. Có thể dùng một sort key chuẩn hóa, ví dụ `(is_null_rank, created_at, id)`, hoặc tách query branches cho hai nhóm.

Chỉ encode `created_at=null` mà không encode null ordering dễ làm cursor bỏ sót hoặc lặp rows.

## 8. Chiến lược phổ biến nhất: hai truy vấn

Với yêu cầu “page orders, kèm toàn bộ lines”, hãy tách:

1. Query A: lấy **IDs của root entities** theo filter, sort và page.
2. Query B: tải các roots đó cùng collections cần thiết, không áp pagination lên collection fetch query.
3. Sắp xếp kết quả query B theo thứ tự IDs từ query A vì `IN (:ids)` không bảo toàn thứ tự.

Sơ đồ:

```text
Request: page=2, size=20
           |
           v
Query A: filter + ORDER BY + LIMIT/OFFSET
           |
           v
20 root IDs, in page order
           |
           v
Query B: SELECT roots WHERE id IN (...)
        LEFT JOIN FETCH collection
           |
           v
Complete entity graphs
           |
           v
Restore original ID order
           |
           v
Return page
```

Cách này cho database giới hạn roots trước, rồi tải collection cho đúng nhóm roots đó.

## 9. Query A: phân trang root IDs

Ví dụ JPQL:

```java
@Query(
    value = """
        select o.id
        from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.status = :status
        order by o.createdAt desc, o.id desc
        """,
    countQuery = """
        select count(o)
        from PurchaseOrder o
        where o.tenantId = :tenantId
          and o.status = :status
        """
)
Page<Long> findPageIds(
    @Param("tenantId") Long tenantId,
    @Param("status") OrderStatus status,
    Pageable pageable
);
```

Spring Data áp offset/limit cho query ID theo `Pageable`. Count query đếm root orders, không join collection nên không nhân số rows.

### 9.1. Vì sao count query tách riêng?

`Page<T>` thường cần biết total elements/pages. Nếu query chính join `lines`, `count(*)` có thể đếm số joined rows thay vì số orders.

Ví dụ:
- Order#1 có 5 lines.
- Order#2 có 2 lines.
- `count(*)` trên join trả 7.
- Tổng số root orders chỉ là 2.

Nếu phải dùng join trong count query, dùng `count(distinct o.id)` hoặc viết lại bằng `exists` để tránh nhân dòng.

## 10. Query A với điều kiện lọc theo child: ưu tiên `EXISTS`

Yêu cầu: lấy các orders có ít nhất một line mang SKU `ABC`.

Một query join:

```java
select o.id
from PurchaseOrder o
join o.lines l
where l.sku = :sku
order by o.createdAt desc, o.id desc
```

có thể trả cùng `o.id` nhiều lần nếu order có nhiều lines cùng SKU. Page ID bị duplicate và count cũng có thể sai.

Dùng `EXISTS`:

```java
select o.id
from PurchaseOrder o
where o.tenantId = :tenantId
  and exists (
      select l.id
      from OrderLine l
      where l.order = o
        and l.sku = :sku
  )
order by o.createdAt desc, o.id desc
```

`EXISTS` trả lời câu hỏi “root này có ít nhất một child thỏa điều kiện không?” mà không nhân root rows trong kết quả.

### 10.1. Count query tương ứng

```java
select count(o)
from PurchaseOrder o
where o.tenantId = :tenantId
  and exists (
      select l.id
      from OrderLine l
      where l.order = o
        and l.sku = :sku
  )
```

Count và ID query phải dùng cùng filter semantics, bao gồm tenant, status, soft-delete visibility, authorization scope và mọi điều kiện nghiệp vụ.

## 11. Query B: fetch graph theo danh sách IDs

Sau khi có `ids`:

```java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.lines
    where o.id in :ids
    """)
List<PurchaseOrder> fetchPageWithLines(
    @Param("ids") Collection<Long> ids
);
```

Ở đây không dùng `Pageable`, `setFirstResult()` hoặc `setMaxResults()`.

Query B có thể trả nhiều SQL rows do join lines, nhưng số root IDs đã được giới hạn ở Query A. Hibernate có thể hydrate collections đầy đủ cho các roots trong trang.

### 11.1. Không chạy `IN (:ids)` khi danh sách rỗng

Nếu Query A trả empty page:

```java
if (ids.isEmpty()) {
    return Page.empty(pageable);
}
```

Không dựa vào provider xử lý `IN ()` như thế nào. Nhiều DBMS không chấp nhận empty IN list.

### 11.2. `IN` không bảo toàn thứ tự

Query:

```sql
SELECT *
FROM purchase_orders
WHERE id IN (105, 103, 104);
```

không bảo đảm trả `105, 103, 104` theo đúng thứ tự list. Nếu page order có ý nghĩa, phải khôi phục thứ tự sau Query B hoặc encode thứ tự trong SQL bằng một derived table/`CASE`.

## 12. Khôi phục thứ tự của Query A trong Java

Ví dụ service:

```java
@Transactional(readOnly = true)
public Page<PurchaseOrder> findOrders(
        Long tenantId,
        OrderStatus status,
        Pageable pageable
) {
    Page<Long> idPage =
        repository.findPageIds(tenantId, status, pageable);

    List<Long> ids = idPage.getContent();

    if (ids.isEmpty()) {
        return new PageImpl<>(
            List.of(),
            pageable,
            idPage.getTotalElements()
        );
    }

    List<PurchaseOrder> fetched =
        repository.fetchPageWithLines(ids);

    Map<Long, PurchaseOrder> byId = fetched.stream()
        .collect(Collectors.toMap(
            PurchaseOrder::getId,
            Function.identity()
        ));

    List<PurchaseOrder> ordered = ids.stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();

    return new PageImpl<>(
        ordered,
        pageable,
        idPage.getTotalElements()
    );
}
```

Đây là mẫu minh họa; cần imports, constructor và repository declarations phù hợp ứng dụng.

### 12.1. Vì sao có `.filter(Objects::nonNull)`?

Giữa hai queries, một root có thể bị xóa hoặc không còn thỏa điều kiện do concurrent transaction nếu isolation không giữ snapshot nhất quán. Khi đó Query B không tìm thấy một ID đã có trong Query A.

Nếu chạy trong snapshot transaction phù hợp, tình huống này ít xảy ra hơn. Nếu chấp nhận read-committed listing, cần quyết định:
- Bỏ qua root biến mất và giữ total count từ Query A.
- Retry trang.
- Trả warning/consistency token.
- Dùng transaction isolation mạnh hơn.

Không âm thầm coi đây là hành vi bình thường nếu màn hình yêu cầu snapshot chặt chẽ.

## 13. Một service hoàn chỉnh hơn với Page và count

Cấu trúc:

```java
@Transactional(
    readOnly = true,
    isolation = Isolation.REPEATABLE_READ
)
public Page<PurchaseOrder> findOrders(
        Long tenantId,
        OrderStatus status,
        Pageable pageable
) {
    Page<Long> idPage =
        repository.findPageIds(tenantId, status, pageable);

    if (idPage.isEmpty()) {
        return new PageImpl<>(
            List.of(), pageable, idPage.getTotalElements()
        );
    }

    List<PurchaseOrder> fetched =
        repository.fetchPageWithLines(idPage.getContent());

    Map<Long, PurchaseOrder> byId = fetched.stream()
        .collect(Collectors.toMap(
            PurchaseOrder::getId,
            Function.identity()
        ));

    List<PurchaseOrder> ordered = idPage.getContent().stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();

    return new PageImpl<>(
        ordered,
        pageable,
        idPage.getTotalElements()
    );
}
```

`REPEATABLE_READ` là lựa chọn để minh họa snapshot consistency, nhưng semantics cụ thể tùy DBMS/transaction manager. Trong Spring, isolation level thường chỉ được áp dụng khi tạo transaction mới; một method tham gia transaction có sẵn có thể kế thừa isolation của transaction ngoài.

Nếu không cần snapshot nhất quán qua nhiều câu query, có thể dùng isolation mặc định và chấp nhận listing mang tính best-effort.

## 14. Không fetch nhiều collection to-many cùng một query

Ví dụ:

```java
select o
from PurchaseOrder o
left join fetch o.lines
left join fetch o.tags
left join fetch o.attachments
```

Nếu một order có:
- 5 lines.
- 4 tags.
- 3 attachments.

join có thể tạo tới \(5 \times 4 \times 3 = 60\) rows cho một root, tùy quan hệ và dữ liệu.

Đây là **Cartesian multiplication**. Nó làm tăng:
- Network payload.
- JDBC row processing.
- Hibernate hydration work.
- Heap pressure.
- Thời gian sort/distinct.
- Nguy cơ multiple-bag fetching exception với một số collection mappings.

### 14.1. Fetch từng collection bằng query riêng

Một phương án:
1. Query A lấy root IDs.
2. Query B fetch roots + lines.
3. Query C fetch tags cho cùng root IDs.
4. Query D fetch attachments nếu thực sự cần.

Trong cùng Persistence Context, Hibernate identity map kết hợp các rows vào cùng root entities. Không cần join tất cả collection vào một câu SQL.

### 14.2. DTO read model có thể hiệu quả hơn entity graph

Nếu màn hình chỉ cần `orderNumber`, `status`, `lineCount` và `total`, đừng hydrate toàn bộ `OrderLine` entities. Dùng projection/DTO query với aggregate có thể tiết kiệm nhiều công việc.

## 15. `Page`, `Slice` và `List` trong Spring Data JPA

| Kiểu trả về | Metadata | Thường cần count query? | Khi phù hợp |
| --- | --- | --- | --- |
| `Page<T>` | Total elements/pages | Có, nếu cần xác định total | UI cần tổng số trang |
| `Slice<T>` | Có next/previous slice | Thường không cần total count; đọc thêm một phần tử | Infinite scroll hoặc “xem thêm” |
| `List<T>` + `Pageable` | Chỉ danh sách hiện tại | Không tự cung cấp total | Caller tự quản lý metadata |
| `Window<T>`/Scroll API | Vị trí tiếp tục theo scroll model | Tùy API/strategy | Duyệt tập lớn theo keyset/offset |

`Page` tiện nhưng count query có thể tốn đáng kể trên bảng lớn hoặc filter phức tạp. Nếu UI chỉ cần biết còn dữ liệu không, `Slice` thường nhẹ hơn.

### 15.1. `Slice` với hai-phase fetch

Có thể lấy `pageSize + 1` root IDs:
- Nếu có phần tử thứ `pageSize + 1`, `hasNext=true`.
- Bỏ phần tử dư.
- Fetch graph cho `pageSize` IDs còn lại.

Như vậy tránh count query. Query fetch collection ở pha hai vẫn không có pagination.

### 15.2. Không nhầm page size với số child rows

Nếu page size là 20 orders và mỗi order có 100 lines, response có thể chứa 2.000 line objects. Page size giới hạn root entities, không giới hạn tổng kích thước graph.

Nếu graph quá lớn, nên phân trang child collection riêng hoặc trả summary trước.

## 16. Sort theo thuộc tính của collection là bài toán riêng

Yêu cầu:

> Lấy 20 orders có `OrderLine.createdAt` mới nhất trước.

Không thể đơn giản:

```java
order by line.createdAt desc
```

nếu một order có nhiều lines. Một root có nhiều giá trị sort; “thứ tự của order” chưa được định nghĩa.

Phải xác định rule:
- Sort theo line mới nhất: `MAX(line.createdAt)`.
- Sort theo line cũ nhất: `MIN(line.createdAt)`.
- Sort theo line có giá cao nhất: `MAX(line.unitPrice)`.
- Sort theo một child được chọn theo ranking (ví dụ line mới nhất với tie-breaker).
- Sort theo một thuộc tính đã denormalize lên root.

### 16.1. Sort theo aggregate

SQL PostgreSQL:

```sql
SELECT
    o.id,
    MAX(l.created_at) AS latest_line_at
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
WHERE o.tenant_id = :tenantId
GROUP BY o.id
ORDER BY
    MAX(l.created_at) DESC NULLS LAST,
    o.id DESC
LIMIT :limit OFFSET :offset;
```

Mỗi root chỉ có một row sau `GROUP BY`, nên database paginate root IDs đúng. Query thứ hai fetch entity graph theo danh sách IDs.

Count query có thể đếm orders thỏa root filters; nếu filter phụ thuộc child, dùng `EXISTS` hoặc `COUNT(DISTINCT o.id)` tương ứng.

### 16.2. Sort theo child row được chọn

Nếu cần sort theo “line mới nhất” và còn muốn trả thông tin line đó, có thể dùng window function:

```sql
WITH ranked_lines AS (
    SELECT
        l.order_id,
        l.created_at,
        l.id,
        ROW_NUMBER() OVER (
            PARTITION BY l.order_id
            ORDER BY l.created_at DESC, l.id DESC
        ) AS rn
    FROM order_lines l
),
root_page AS (
    SELECT
        o.id,
        rl.created_at AS latest_line_at
    FROM purchase_orders o
    LEFT JOIN ranked_lines rl
      ON rl.order_id = o.id
     AND rl.rn = 1
    WHERE o.tenant_id = :tenantId
    ORDER BY rl.created_at DESC NULLS LAST, o.id DESC
    LIMIT :limit OFFSET :offset
)
SELECT id
FROM root_page
ORDER BY latest_line_at DESC NULLS LAST, id DESC;
```

Đây là SQL minh họa cho PostgreSQL và cần điều chỉnh aliases/filters thực tế. Sau khi có root IDs, fetch graph bằng query riêng.

## 17. Sort theo collection và count query

Nếu query chính dùng:

```sql
LEFT JOIN order_lines l ...
GROUP BY o.id
```

thì count query không thể đơn giản giữ nguyên `COUNT(*)`, vì mỗi order có thể có nhiều lines trước grouping.

Có thể:
- `SELECT COUNT(*) FROM purchase_orders o WHERE ...` nếu filter chỉ root.
- Dùng `EXISTS` cho điều kiện child.
- Dùng `COUNT(DISTINCT o.id)` khi join cần thiết.
- Dùng derived table đếm số root rows sau aggregate nếu filter/sort semantics yêu cầu.

Đếm đúng **đơn vị UI đang phân trang** là nguyên tắc. Nếu UI hiển thị orders, total phải là số orders.

## 18. Lọc collection mà vẫn muốn fetch toàn bộ collection

Một lỗi thường gặp:

```java
select distinct o
from PurchaseOrder o
join fetch o.lines l
where l.sku = :sku
```

Ý định có thể là “tìm orders có SKU này, rồi hiển thị tất cả lines”. Nhưng điều kiện join có thể làm query chỉ trả rows của những lines khớp, và collection có thể bị hydrate không đầy đủ tùy query/provider semantics.

Cách rõ ràng:
- Query A dùng `EXISTS` để chọn roots có line phù hợp.
- Query B fetch toàn bộ `o.lines` không có filter trên alias collection.

Nếu muốn hiển thị **chỉ những lines khớp**, hãy trả DTO/projection riêng hoặc query child rows riêng. Không đánh dấu một collection entity là initialized đầy đủ khi thực tế chỉ có subset.

## 19. `EntityGraph` có tự giải quyết pagination collection không?

Ví dụ Spring Data:

```java
@EntityGraph(attributePaths = {"customer", "lines"})
Page<PurchaseOrder> findByTenantId(
    Long tenantId,
    Pageable pageable
);
```

`@EntityGraph` mô tả fetch plan, nhưng provider có thể hiện thực bằng joins hoặc chiến lược khác. Nếu collection được join fetch trong SQL, vấn đề row multiplication vẫn tồn tại.

**EntityGraph không phải cam kết rằng database giới hạn root rows trước collection expansion.**

Với paged root queries:
- Fetch to-one associations thường đơn giản hơn.
- Collection lớn nên fetch ở pha hai hoặc batch/subselect.
- Kiểm tra SQL thực tế và bật fail-on-pagination-over-collection-fetch khi phù hợp.

## 20. Batch fetching thay vì join fetch collection

Hibernate hỗ trợ batch fetching:

```java
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "order")
@BatchSize(size = 50)
private List<OrderLine> lines;
```

Hoặc setting:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=50
```

Khi nhiều collections/proxies được truy cập, Hibernate có thể gom IDs vào một `IN (...)` query thay vì phát một SELECT riêng cho từng root.

Ưu điểm:
- Root page query giữ pagination đơn giản.
- Collection được tải theo batches.
- Tránh join multiplication ở root query.

Đánh đổi:
- Nếu code truy cập collection của mọi root, vẫn có thêm query(s).
- Có thể tải collections mà UI không thực sự cần.
- Batch size phải phù hợp parameter limits/DBMS và workload.

## 21. `FetchMode.SUBSELECT`

Hibernate có thể tải collections của một nhóm owners bằng subselect fetching:

```java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order")
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines;
```

Khi một collection được khởi tạo, Hibernate có thể dùng một query dựa trên truy vấn owners trước đó để tải collections cho các owners trong Persistence Context phù hợp.

Ưu điểm:
- Giảm N+1 cho nhóm root entities.
- Không nhân root rows trong query page ban đầu.

Nhược điểm:
- Có thể tải nhiều collection hơn dự định.
- Query subselect phụ thuộc truy vấn owner ban đầu và persistence context.
- Cần xem query plan, filter và paging behavior của version thực tế.

Batch fetching và subselect fetching là các lựa chọn thay thế cần đo; chúng không thay thế việc xác định page roots đúng.

## 22. DTO projection: khi không cần managed entity graph

Một danh sách hiển thị có thể dùng DTO:

```java
public record OrderRow(
    Long id,
    String orderNumber,
    String status,
    BigDecimal total,
    Instant createdAt,
    long lineCount
) {}
```

JPQL projection:

```java
select new com.example.dto.OrderRow(
    o.id,
    o.orderNumber,
    o.status,
    o.total,
    o.createdAt,
    count(l)
)
from PurchaseOrder o
left join o.lines l
where o.tenantId = :tenantId
group by
    o.id,
    o.orderNumber,
    o.status,
    o.total,
    o.createdAt
order by o.createdAt desc, o.id desc
```

Mỗi root được group thành một row DTO. Có thể paginate query này nếu SQL/JPQL group semantics đúng.

Nếu cần danh sách line details, lấy riêng bằng query:

```java
select new com.example.dto.OrderLineRow(
    l.order.id, l.id, l.sku, l.quantity
)
from OrderLine l
where l.order.id in :orderIds
order by l.order.id, l.id
```

Sau đó nhóm DTO theo `orderId` trong Java.

### 22.1. DTO query thường tốt cho read-heavy screens

Lợi ích:
- Không cần persistence context đầy đủ.
- Không bị lazy-loading ngoài ý muốn.
- Chỉ lấy columns cần thiết.
- Có thể aggregate/filter/sort rõ ràng.
- Dễ giới hạn payload.

Đánh đổi: caller phải dựng read model và không thể dùng DTO như managed entity để update.

## 23. Keyset pagination (seek pagination)

Offset pagination:

```sql
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
```

database có thể phải tìm/đi qua một lượng lớn rows trước khi trả page sâu. Đồng thời inserts/deletes ở đầu danh sách có thể làm vị trí offset dịch chuyển.

Keyset pagination xác định trang tiếp theo dựa trên **sort key của phần tử cuối trang trước**.

Với sort:

```sql
ORDER BY created_at DESC, id DESC
```

cursor gồm:
- `lastCreatedAt`
- `lastId`

Query tiếp theo:

```sql
SELECT id, created_at
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSizePlusOne;
```

Điều kiện `<` vì cả hai sort keys đang DESC. Với ASC, chiều so sánh tương ứng đổi thành `>`.

### 23.1. Vì sao phải đưa ID vào cursor?

Nếu cursor chỉ có `created_at`, những rows có cùng timestamp với row cuối trang có thể bị bỏ qua hoặc lặp.

Predicate phải so sánh **toàn bộ tuple sort keys** theo đúng thứ tự, bao gồm unique tie-breaker.

### 23.2. Keyset không phải offset được mã hóa

Cursor không phải page number. Nó mô tả ranh giới sau/before một row trong thứ tự đã định. API thường trả `nextCursor` opaque thay vì `page=5000`.

## 24. Keyset với nhiều sort columns

Ví dụ:

```sql
ORDER BY priority DESC, created_at ASC, id ASC
```

Cursor gồm `(lastPriority, lastCreatedAt, lastId)`.

Điều kiện “sau cursor”:

```sql
WHERE
       priority < :lastPriority
    OR (
        priority = :lastPriority
        AND created_at > :lastCreatedAt
    )
    OR (
        priority = :lastPriority
        AND created_at = :lastCreatedAt
        AND id > :lastId
    )
```

Mỗi thành phần so sánh phải theo chiều sort của chính cột đó. Đây là lỗi phổ biến: dùng cùng một dấu `<` cho mọi cột dù sort directions khác nhau.

Với nhiều columns hoặc nullable keys, query builder/cursor codec nên sinh predicate từ một sort definition chuẩn hóa, tránh viết tay nhiều biến thể dễ sai.

## 25. Keyset với nullable columns

Giả sử `created_at` nullable và sort:

```sql
ORDER BY created_at DESC NULLS LAST, id DESC
```

Một cursor cần phân biệt:
1. Đang ở nhóm `created_at IS NOT NULL`.
2. Đang ở nhóm `created_at IS NULL`.

Khi cursor còn non-null, các rows “sau” có thể gồm:
- `created_at < cursorCreatedAt`.
- Cùng timestamp nhưng `id < cursorId`.
- Tất cả rows có `created_at IS NULL`, vì nulls nằm cuối.

Khi cursor đã ở nhóm null, chỉ còn các rows null với `id < cursorId`.

Có thể viết hai nhánh predicate hoặc tạo sort rank tường minh:

```sql
ORDER BY
    CASE WHEN created_at IS NULL THEN 1 ELSE 0 END ASC,
    created_at DESC,
    id DESC
```

Sau đó cursor phải chứa null-rank cùng các giá trị khác. Dùng expression này có thể ảnh hưởng index; cân nhắc generated column/functional index theo DBMS.

## 26. Keyset query với child filter

Keyset vẫn kết hợp tốt với `EXISTS`:

```sql
SELECT o.id, o.created_at
FROM purchase_orders o
WHERE o.tenant_id = :tenantId
  AND EXISTS (
      SELECT 1
      FROM order_lines l
      WHERE l.order_id = o.id
        AND l.sku = :sku
  )
  AND (
      o.created_at < :lastCreatedAt
      OR (
          o.created_at = :lastCreatedAt
          AND o.id < :lastId
      )
  )
ORDER BY o.created_at DESC, o.id DESC
LIMIT :pageSizePlusOne;
```

Sau đó query thứ hai fetch collection cho root IDs đã chọn.

Nếu sort key phụ thuộc child aggregate, cursor phải chứa giá trị aggregate đã tính (ví dụ `latestLineAt`) và ID. Cần bảo đảm cùng một aggregate được tính nhất quán trong cả predicate lẫn `ORDER BY`.

## 27. Keyset có giải quyết mọi vấn đề dữ liệu đồng thời không?

Keyset tránh nhiều vấn đề do offset dịch chuyển khi rows mới được chèn trước vị trí hiện tại. Nhưng nó **không tạo snapshot bất biến**.

Ví dụ:
- Một order chưa đọc được cập nhật `created_at` khiến nó nhảy qua cursor.
- Một order đã đọc bị thay đổi `priority` khiến nó xuất hiện lại hoặc biến mất khỏi phần còn lại.
- Một child được thêm làm thay đổi `MAX(line.created_at)` dùng để sort.
- Một row bị xóa giữa hai trang.

Nếu sort keys là bất biến sau khi tạo (ví dụ `created_at`, `id`) và filter ổn định, keyset cho hành vi tiếp tục đáng tin cậy hơn.

Nếu cần snapshot chính xác cho báo cáo, hãy xác định snapshot boundary:
- Transaction isolation snapshot trong một transaction dài (thường không phù hợp cho HTTP pagination nhiều requests).
- `asOf`/version boundary do ứng dụng quản lý.
- Export job tạo danh sách IDs cố định.
- Temporal data model hoặc materialized snapshot.

Không tuyên bố keyset tự bảo đảm “mọi trang là cùng một snapshot” khi dữ liệu có thể đổi.

## 28. Offset pagination vẫn có chỗ dùng

Offset phù hợp khi:
- Tập dữ liệu nhỏ/vừa.
- UI cần nhảy trực tiếp tới trang N.
- Sort/filter ít thay đổi.
- Count query rẻ.
- Có index tốt và page depth không lớn.

Keyset phù hợp khi:
- Infinite scroll.
- Duyệt feed/timeline.
- Tập dữ liệu lớn và page sâu.
- Thứ tự có cursor keys rõ.
- Không cần nhảy tùy ý tới page 500.

Hai phương pháp giải quyết mục tiêu khác nhau. Không phải lúc nào keyset cũng thay thế được numbered pages.

### 28.1. Offset + unique ordering vẫn có thể dịch trang khi có insert/delete

`ORDER BY created_at DESC, id DESC` làm thứ tự deterministic tại một snapshot, nhưng nếu một row mới được chèn ở đầu giữa hai HTTP requests, offset trang sau sẽ dịch một vị trí.

Stable sort order và stable multi-request snapshot là **hai vấn đề riêng**.

## 29. Count query có thể là phần đắt nhất của `Page`

Query dữ liệu:

```sql
SELECT id
FROM purchase_orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

có thể dừng sớm nhờ index.

Count:

```sql
SELECT COUNT(*)
FROM purchase_orders
WHERE tenant_id = :tenantId;
```

có thể phải đếm nhiều rows, đặc biệt khi filter phức tạp/joins.

Nếu UI chỉ cần “còn trang tiếp theo”, dùng `Slice` hoặc query `pageSize + 1` IDs. Đừng tính total pages chỉ vì repository mặc định trả `Page`.

### 29.1. Không thay count bằng ước lượng mà không đổi API contract

Database statistics/approximate counts có thể nhanh hơn nhưng không chính xác tuyệt đối. Nếu dùng, UI/API phải thể hiện đây là estimate; không trả một con số ước lượng dưới tên `totalElements` chính xác.

## 30. Index cho root pagination

Với query:

```sql
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT 20
```

PostgreSQL có thể tận dụng index:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
ON purchase_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
```

Với child filter:

```sql
EXISTS (
    SELECT 1
    FROM order_lines l
    WHERE l.order_id = o.id
      AND l.sku = ?
)
```

có thể cần index:

```sql
CREATE INDEX idx_order_lines_order_sku
ON order_lines (order_id, sku);
```

Index tốt nhất phụ thuộc selectivity và access plan; nếu query bắt đầu từ SKU có selectivity cao, `(sku, order_id)` có thể hợp lý hơn.

### 30.1. Index phải khớp predicate và sort

Nguyên tắc thường gặp:
- Equality predicates ở đầu composite index.
- Sort columns tiếp theo theo thứ tự phù hợp.
- Unique tie-breaker cuối.
- Child FK/filter index cho EXISTS/join.
- Partial indexes khi filter chỉ nhắm active rows và DBMS hỗ trợ.

Không tạo một index cho mỗi sort combination mà chưa đo storage/write cost.

## 31. Kiểm tra bằng `EXPLAIN`/execution plan

Trên PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM purchase_orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 1000;
```

So sánh:
- Rows scanned vs rows returned.
- Index Scan vs Seq Scan.
- Sort node và memory/disk spill.
- Buffers hit/read.
- Actual time.
- Rows removed by filter.

Với keyset:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM purchase_orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND (
      created_at < TIMESTAMP '2026-01-01 10:00:00'
      OR (
          created_at = TIMESTAMP '2026-01-01 10:00:00'
          AND id < 9000
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 21;
```

Đây là SQL minh họa. Dữ liệu, statistics, index, DB version và parameter selectivity quyết định plan thật.

## 32. Batch fetch và hai-phase fetch: chọn theo use case

| Chiến lược | Query shape | Điểm mạnh | Rủi ro |
| --- | --- | --- | --- |
| Collection fetch join + page | Một query join + limit | Viết ngắn | Pagination collection sai/được đẩy vào memory |
| Two-phase ID then graph | Query page IDs, query fetch graph | Root page chính xác, graph đầy đủ | Nhiều round trips, cần restore order |
| Batch fetching | Page roots, collection loads theo batch | Tránh row multiplication | Nhiều queries, có thể tải thừa |
| Subselect fetching | Page roots, collection subselect | Giảm N+1 | Phụ thuộc owner query/persistence context |
| DTO projection | Một query aggregate/projection | Ít hydration, payload gọn | Không phải managed graph |
| Window/CTE native SQL | Paginate root relation trong DB | Kiểm soát sort/aggregate mạnh | DB-specific, phức tạp hơn |

Không có một fetch strategy tối ưu cho mọi màn hình.

## 33. `@OrderBy` và `@OrderColumn` không thay thế root ordering

Collection:

```java
@OneToMany(mappedBy = "order")
@OrderBy("createdAt DESC, id DESC")
private List<OrderLine> lines;
```

`@OrderBy` xác định thứ tự phần tử trong collection khi load theo mapping/provider. Nó không xác định thứ tự các `PurchaseOrder` trong root page.

`@OrderColumn` lưu vị trí list trong DB, khác với sắp xếp theo thuộc tính. Nếu vị trí thay đổi, ORM có thể phát UPDATE cho nhiều child rows.

Phải có:
- Root `ORDER BY` riêng.
- Collection ordering riêng.
- Unique tie-breaker cho cả hai nếu thứ tự phải ổn định.

## 34. Phân trang với composite primary key

Nếu root entity có composite ID:

```java
@EmbeddedId
private OrderKey id;
```

Query phase một cần lấy khóa đầy đủ, không chỉ một phần ID. Query phase hai phải lọc đúng tập composite keys.

Một số DBMS hỗ trợ row-value constructor:

```sql
WHERE (tenant_id, order_number)
      IN ((:tenant1, :number1), (:tenant2, :number2))
```

JPQL/provider support cho tuple IN có giới hạn. Có thể dùng:
- OR predicates theo từng key pair.
- Temporary/staging table.
- CTE/VALUES table trong native SQL.
- Một surrogate key ổn định nếu schema cho phép.

Thứ tự khôi phục cũng phải map theo composite key equality đúng (`equals`/`hashCode` của embedded ID).

## 35. Page fetch graph và giới hạn `IN` parameters

Một page 2.000 root IDs có thể tạo:

```sql
WHERE id IN (?, ?, ..., ?)
```

Nhiều DBMS/driver có giới hạn số bind parameters hoặc query size. Chia Query B thành chunks:

```text
ids 1..500
ids 501..1000
ids 1001..1500
ids 1501..2000
```

Sau đó merge results theo ID map và khôi phục thứ tự từ Query A.

Tuy nhiên, page size 2.000 roots với collection lớn có thể là API design không tốt. Hãy giới hạn payload/page size theo dữ liệu trả về, không chỉ theo số root rows.

## 36. Không để collection lazy loading kéo query ra ngoài transaction

Một page trả entity có lazy collection:

```java
Page<PurchaseOrder> orders = service.findOrders(...);
```

Sau khi transaction đóng, serializer truy cập `order.getLines()` có thể gây `LazyInitializationException` hoặc N+1 nếu Open Session in View còn mở.

Các lựa chọn:
- Fetch graph cần thiết trong service transaction (two-phase/batch).
- Map DTO trong transaction.
- Tắt OSIV nếu kiến trúc muốn kiểm soát rõ database access.
- Không serialize entity graph tùy tiện.

Không giải quyết pagination bằng cách bật OSIV rồi để JSON serializer tự phát hàng trăm SELECT.

## 37. Page DTO có collection lồng nhau

Nếu API cần:

```json
{
  "id": 105,
  "orderNumber": "PO-105",
  "lines": [
    {"id": 1, "sku": "A"},
    {"id": 2, "sku": "B"}
  ]
}
```

có thể:
1. Lấy page DTO/root IDs.
2. Query lines cho các IDs.
3. Group lines theo `orderId`.
4. Build response DTO.

Ví dụ grouping:

```java
Map<Long, List<OrderLineDto>> linesByOrder =
    lineDtos.stream().collect(
        Collectors.groupingBy(OrderLineDto::orderId)
    );

List<OrderDto> result = orderRows.stream()
    .map(row -> new OrderDto(
        row.id(),
        row.orderNumber(),
        linesByOrder.getOrDefault(row.id(), List.of())
    ))
    .toList();
```

Đây là cách rõ ràng để giới hạn roots mà vẫn trả child rows cần thiết. Nếu mỗi order có hàng nghìn lines, có thể cần endpoint riêng để phân trang lines.

## 38. Filters, tenant và soft-delete phải giống nhau ở mọi phase

Giả sử Query A lọc:
- `tenant_id`.
- `deleted=false`.
- `status`.
- quyền truy cập theo organization.

Nhưng Query B chỉ:

```sql
WHERE id IN (:ids)
```

Nếu IDs đến từ Query A và DB không thay đổi, có thể vẫn đúng. Tuy nhiên, để bảo vệ tenant/security và chống race, Query B nên có scope phù hợp khi cần:

```java
where o.tenantId = :tenantId
  and o.deleted = false
  and o.id in :ids
```

Nếu Hibernate `@SoftDelete` tự thêm restriction, hãy xác nhận nó áp dụng trong Query B và admin/native paths đúng như thiết kế.

**Không dùng page ID từ một tenant rồi fetch theo ID thiếu tenant condition** trong model cho phép ID collision hoặc khi query boundary không đáng tin.

## 39. Consistency giữa Query A và Query B

Hai-phase fetch dùng ít nhất hai câu SELECT. Ở isolation `READ COMMITTED`, mỗi statement có thể thấy snapshot khác nhau.

Ví dụ:
1. Query A chọn Order#105.
2. Transaction khác xóa Order#105 hoặc đổi tenant/status.
3. Query B không còn tìm thấy Order#105.

Hoặc:
1. Query A chọn Order#105.
2. Transaction khác thêm OrderLine.
3. Query B thấy collection mới hơn root page snapshot.

Nếu UI chấp nhận “dữ liệu gần nhất tại lúc fetch graph”, đây có thể là behavior hợp lệ.

Nếu cần page nhất quán:
- Chạy hai queries trong cùng transaction với isolation snapshot phù hợp (ví dụ PostgreSQL REPEATABLE READ).
- Hoặc dùng version/snapshot token.
- Hoặc tạo materialized list IDs cho export/report.
- Tránh lock hàng loạt chỉ để làm một màn hình list nếu không cần.

### 39.1. Count query cũng thuộc consistency question

Spring Data `Page` có thể chạy count query riêng. Nếu dữ liệu thay đổi giữa ID query và count query ở READ COMMITTED, `content.size`, `totalElements` và `hasNext` có thể không mô tả cùng một snapshot.

Đó không nhất thiết là bug provider; đó là hệ quả của nhiều statements và isolation policy.

## 40. Stable ordering không đảm bảo snapshot qua nhiều HTTP requests

Ngay cả khi mỗi page query chạy trong transaction repeatable-read riêng, page 1 và page 2 là hai transaction khác nhau.

Nếu yêu cầu duyệt một tập dữ liệu cố định qua nhiều requests, cần một cursor/snapshot model:
- `asOfCreatedAt`/high-watermark nếu sort key phù hợp.
- Snapshot ID list được tạo một lần.
- Database snapshot/temporal version boundary được quản lý.
- Export job materialize result set.

Keyset + immutable sort key giảm dịch chuyển nhưng không tự đóng băng filter membership.

## 41. Window functions có thể phân trang roots và child summaries trong một SQL

Ví dụ PostgreSQL:

```sql
WITH root_rows AS (
    SELECT
        o.id,
        o.created_at,
        ROW_NUMBER() OVER (
            ORDER BY o.created_at DESC, o.id DESC
        ) AS page_row
    FROM purchase_orders o
    WHERE o.tenant_id = :tenantId
      AND o.status = :status
),
page_ids AS (
    SELECT id, created_at, page_row
    FROM root_rows
    WHERE page_row BETWEEN :firstRow AND :lastRow
)
SELECT
    p.id,
    p.created_at,
    l.id AS line_id,
    l.sku,
    l.quantity
FROM page_ids p
LEFT JOIN order_lines l ON l.order_id = p.id
ORDER BY p.page_row, l.id;
```

`ROW_NUMBER()` đánh số root rows trước khi join collection. SQL cuối vẫn trả nhiều rows per root, nhưng chỉ cho các root IDs trong trang.

Cách này có thể hiệu quả cho read models/reporting, nhưng:
- Native SQL DB-specific.
- Result mapping DTO phức tạp hơn.
- Count query riêng.
- Không nhất thiết nên hydrate managed entity graph từ một projection phức tạp.
- Sort/filter expressions cần khớp với page cursor.

## 42. `DISTINCT ON`, lateral join và database-specific tools

PostgreSQL có `DISTINCT ON`:

```sql
SELECT DISTINCT ON (o.id)
    o.id,
    l.created_at AS latest_line_at,
    l.id AS latest_line_id
FROM purchase_orders o
LEFT JOIN order_lines l ON l.order_id = o.id
ORDER BY
    o.id,
    l.created_at DESC,
    l.id DESC;
```

Đây là cách chọn một child đại diện cho mỗi root, nhưng `DISTINCT ON` yêu cầu `ORDER BY` có cấu trúc phù hợp. Sau đó cần một query/CTE khác sắp xếp roots theo `latest_line_at` và paginate.

Lateral joins và window functions cũng có thể giúp chọn child representative. Chỉ dùng khi query plan và business sort definition đã rõ; không dùng SQL đặc thù chỉ để tránh một query ID đơn giản.

## 43. Spring Data keyset scrolling

Spring Data có scrolling abstractions ở một số phiên bản, ví dụ `ScrollPosition`, `Window<T>` và keyset-based scrolling cho các query/method phù hợp.

Ý tưởng:
- Query trả một `Window<T>`.
- `ScrollPosition` mô tả vị trí tiếp tục.
- Keyset position lấy sort properties từ phần tử cuối window.
- Sort cần xác định và chứa key đủ để phân biệt rows.
- Projection phải chứa các sort properties cần cho cursor.
- Không phải mọi query method/JPQL/native query đều hỗ trợ mọi scrolling mode.

Đọc reference docs đúng Spring Data version trước khi thiết kế public cursor API. Không giả định `Pageable` và keyset scrolling là cùng một abstraction.

## 44. Một mẫu repository cho hai-phase pagination

Ví dụ interface:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            select o.id
            from PurchaseOrder o
            where o.tenantId = :tenantId
              and o.status = :status
            order by o.createdAt desc, o.id desc
            """,
        countQuery = """
            select count(o)
            from PurchaseOrder o
            where o.tenantId = :tenantId
              and o.status = :status
            """
    )
    Page<Long> findPageIds(
        Long tenantId,
        OrderStatus status,
        Pageable pageable
    );

    @Query("""
        select distinct o
        from PurchaseOrder o
        left join fetch o.customer
        left join fetch o.lines
        where o.tenantId = :tenantId
          and o.id in :ids
        """)
    List<PurchaseOrder> fetchGraph(
        Long tenantId,
        Collection<Long> ids
    );
}
```

Service:

```java
@Transactional(readOnly = true)
public Page<PurchaseOrder> findPage(
        Long tenantId,
        OrderStatus status,
        Pageable pageable
) {
    Page<Long> idPage =
        repository.findPageIds(tenantId, status, pageable);

    if (idPage.getContent().isEmpty()) {
        return new PageImpl<>(
            List.of(), pageable, idPage.getTotalElements()
        );
    }

    List<PurchaseOrder> loaded =
        repository.fetchGraph(tenantId, idPage.getContent());

    Map<Long, PurchaseOrder> byId = loaded.stream()
        .collect(Collectors.toMap(
            PurchaseOrder::getId,
            Function.identity()
        ));

    List<PurchaseOrder> ordered = idPage.getContent().stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();

    return new PageImpl<>(
        ordered, pageable, idPage.getTotalElements()
    );
}
```

Lưu ý:
- JPQL sort ở Query A là nguồn thứ tự chính.
- Query B không áp pagination.
- Query B giữ tenant scope.
- `IN` không bảo toàn thứ tự nên service reorder.
- Count query phải cùng filter.
- Nếu IDs rỗng, không chạy Query B.
- Nếu dùng composite key, cách lọc phase hai thay đổi.
- Nếu cần nhiều collections, cân nhắc query riêng thay vì join tất cả.

## 45. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Page size 20 nhưng chỉ có 3 orders | SQL limit đang giới hạn joined rows | Phân trang root IDs trước |
| Hibernate đọc rất nhiều rows cho page nhỏ | In-memory pagination trên collection fetch | Bật fail setting, dùng two-phase |
| Orders lặp trong page | Join child tạo duplicate root IDs | `EXISTS`, `DISTINCT` root IDs hoặc count distinct |
| Total count lớn hơn số orders | `COUNT(*)` trên join collection | Count root hoặc `COUNT(DISTINCT root.id)` |
| Trang đầu và trang sau lặp order | Sort key không unique | Thêm primary key tie-breaker |
| Trang sâu rất chậm | OFFSET lớn | Keyset/seek pagination |
| Order lines thiếu sau fetch | Collection join bị giới hạn/filtered | Fetch graph riêng không filter subset |
| EntityGraph vẫn chậm | Provider join collection rồi paginate | Kiểm tra SQL, two-phase/batch |
| Hai collection tạo nhiều rows | Cartesian multiplication | Fetch collection riêng |
| Multiple bag exception | Join fetch nhiều bag collections | Chia queries, Set/order mapping có chủ đích |
| Kết quả Query B sai thứ tự | `IN` không đảm bảo order | Reorder theo IDs Query A |
| `Page` total sai | Count query khác filters hoặc nhân rows | Đồng bộ predicates/count distinct |
| Empty page ném lỗi SQL | `IN ()` | Bỏ qua phase hai |
| Root biến mất giữa hai query | Concurrent transaction, READ COMMITTED | Snapshot isolation hoặc best-effort policy |
| Cursor bỏ sót rows cùng timestamp | Cursor chỉ chứa timestamp | Include unique tie-breaker |
| Keyset sai với sort ASC/DESC hỗn hợp | Predicate dùng sai chiều so sánh | Sinh lexicographic predicate theo từng key |
| Null sort gây lặp/bỏ sót | Không định nghĩa null ordering/cursor rank | Explicit null order và cursor đầy đủ |
| Sort theo child không xác định | Root có nhiều child sort values | MIN/MAX hoặc chọn child đại diện |
| Filter child làm collection thiếu | Join fetch alias bị lọc | EXISTS ở root query, fetch full collection sau |
| Native query bỏ tenant filter | Không có ORM predicate tự động | Explicit tenant/deleted/authorization conditions |
| Count query làm chậm API | Total count quá đắt | Slice/keyset hoặc async/approx total rõ contract |
| JSON response phát N+1 | Lazy collections truy cập ngoài service | DTO hoặc fetch có kiểm soát trong transaction |
| Kết quả hai page thay đổi khi insert | Offset bị dịch | Keyset hoặc snapshot boundary |
| Query phase hai vượt bind limit | IN list quá lớn | Chunk IDs hoặc thiết kế page nhỏ hơn |
| Sort theo aggregate chậm | Thiếu index/query plan không tốt | Aggregate/index/materialized read model |

## 46. Quy trình chọn chiến lược phân trang

**Bước 1 — Xác định root unit.** UI đang phân trang Orders, Lines hay DTO rows? Không để join quyết định ngầm.

**Bước 2 — Xác định associations cần hiển thị.** Chỉ to-one, một collection, nhiều collections hay summary?

**Bước 3 — Kiểm tra cardinality.** Một root có thể có bao nhiêu children? Có nguy cơ Cartesian multiplication không?

**Bước 4 — Viết root query trước.** Filter, tenant/security scope và deterministic `ORDER BY` phải đúng khi chưa fetch collection.

**Bước 5 — Dùng `EXISTS` cho điều kiện “có child thỏa mãn”.** Tránh nhân root IDs.

**Bước 6 — Chọn offset hay keyset.** UI cần jump-to-page hay chỉ next/previous? Tập dữ liệu lớn đến đâu?

**Bước 7 — Đảm bảo total order.** Sort columns + unique tie-breaker + explicit null ordering.

**Bước 8 — Chọn cách tải graph.** Two-phase, batch fetch, subselect, DTO hoặc SQL window function.

**Bước 9 — Count đúng root.** Không đếm joined child rows.

**Bước 10 — Xử lý consistency.** Query nhiều pha trong transaction nào? Có cần snapshot không?

**Bước 11 — Kiểm tra index và execution plan.** Đo deep offset, keyset và child filter với dữ liệu gần production.

**Bước 12 — Kiểm tra payload.** 20 roots có thể chứa hàng nghìn children; page size phải phù hợp.

**Bước 13 — Kiểm thử concurrent writes.** Inserts, deletes và sort-key updates giữa requests.

**Bước 14 — Kiểm tra SQL Hibernate thật.** Không chỉ dựa vào annotation, method name hoặc kỳ vọng ORM.

## 47. Bài tập tình huống

### Bài 1 — Page size sai

Một order có 8 lines. SQL fetch join dùng `LIMIT 10`. Vì sao page có thể không có 10 orders?

**Đáp án:** SQL limit áp trên joined rows; 8 rows đầu có thể thuộc một root, các roots khác chưa xuất hiện.

### Bài 2 — `DISTINCT` có đủ không?

Thêm `select distinct o` vào collection fetch join có đảm bảo SQL pagination đúng root không?

**Đáp án:** Không. Child columns khác nhau làm joined rows vẫn khác; dedup entity sau truy vấn không đảo ngược SQL limit đã áp trên rows.

### Bài 3 — Fail fast

Cần property nào để Hibernate fail khi pagination buộc phải in-memory trên collection fetch?

**Đáp án:** `hibernate.query.fail_on_pagination_over_collection_fetch=true` (Spring Boot: `spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true`) trên version hỗ trợ.

### Bài 4 — Stable order

`ORDER BY created_at DESC` có đủ deterministic không nếu nhiều rows cùng timestamp?

**Đáp án:** Không. Thêm unique tie-breaker, ví dụ `id DESC`.

### Bài 5 — Count query

Order#1 có 5 lines, Order#2 có 2 lines. `COUNT(*)` trên join trả 7. UI cần total orders. Nên làm gì?

**Đáp án:** Count root rows không join hoặc `COUNT(DISTINCT o.id)` nếu join là cần thiết.

### Bài 6 — Filter child

Muốn orders có SKU ABC và hiển thị toàn bộ lines. Query nào tốt hơn: join fetch + where SKU, hay root `EXISTS` rồi fetch collection riêng?

**Đáp án:** `EXISTS` ở pha root IDs, sau đó fetch full collection riêng.

### Bài 7 — Query B đảo thứ tự

Query A trả IDs `[9, 3, 7]`; Query B dùng `IN (9,3,7)` trả `[3,7,9]`. Có lỗi database không?

**Đáp án:** Không. `IN` không bảo đảm thứ tự. Khôi phục thứ tự theo danh sách Query A.

### Bài 8 — Hai collection

Order có lines và tags. Join fetch cả hai làm rows tăng 5×4. Giải pháp?

**Đáp án:** Fetch từng collection trong query riêng, batch/subselect hoặc DTO.

### Bài 9 — Keyset cursor

Sort `(createdAt DESC, id DESC)`. Predicate tiếp theo chỉ `createdAt < :lastCreatedAt`. Điều gì xảy ra với rows cùng timestamp?

**Đáp án:** Các rows còn lại có timestamp bằng cursor bị bỏ qua. Thêm nhánh so sánh ID.

### Bài 10 — Mixed sort directions

Sort `priority DESC, createdAt ASC, id ASC`. Có thể dùng dấu `<` cho cả ba cột không?

**Đáp án:** Không. Predicate lexicographic phải theo chiều từng cột.

### Bài 11 — Offset và insert

Page 1 đã đọc 20 rows; một row mới được insert đầu danh sách; client lấy page 2 bằng OFFSET 20. Có thể lặp row không?

**Đáp án:** Có. Insert làm vị trí offset dịch chuyển. Keyset giảm vấn đề này với sort keys ổn định.

### Bài 12 — Keyset và sort key mutable

Order đã đọc rồi được cập nhật `priority` để chuyển qua cursor. Keyset có bảo đảm không lặp/mất không?

**Đáp án:** Không. Keyset không đóng băng snapshot khi sort key thay đổi.

### Bài 13 — `Page` hay `Slice`

UI chỉ cần nút “Load more”, không cần total pages. Chọn gì?

**Đáp án:** `Slice` hoặc keyset window, tránh count query không cần thiết.

### Bài 14 — EntityGraph

`@EntityGraph(attributePaths={"lines"})` trên method trả `Page<Order>` có tự bảo đảm root pagination không?

**Đáp án:** Không. Provider có thể join collection và gặp cùng vấn đề. Kiểm tra SQL/fetch plan.

### Bài 15 — Batch fetching

Muốn page roots không join lines, nhưng giảm N+1 khi truy cập collections. Có thể dùng gì?

**Đáp án:** `@BatchSize` hoặc `hibernate.default_batch_fetch_size`, hoặc `FetchMode.SUBSELECT` theo workload.

### Bài 16 — Count và concurrent writes

ID query chạy trước, count query chạy sau khi một order mới được thêm ở READ COMMITTED. Total có thể khác snapshot content không?

**Đáp án:** Có. Nhiều statements có thể thấy snapshots khác nhau; dùng isolation snapshot nếu yêu cầu consistency.

### Bài 17 — Sort theo child

Một order có nhiều lines, yêu cầu sort theo `line.createdAt`. Tại sao phải định nghĩa aggregate/representative?

**Đáp án:** Một root có nhiều child timestamps nên không có một sort value duy nhất nếu không chọn rule như MAX/MIN/latest child.

### Bài 18 — Composite ID

Root dùng `@EmbeddedId`. Query phase hai chỉ lọc một thành phần ID. Có an toàn không?

**Đáp án:** Không nếu thành phần đó không duy nhất. Phải giữ toàn bộ composite key.

### Bài 19 — Empty IDs

Query A trả empty list, code vẫn gọi `WHERE id IN :ids`. Rủi ro?

**Đáp án:** Provider/DB có thể tạo SQL empty IN không hợp lệ. Trả empty page mà không chạy query B.

### Bài 20 — Consistency của collection

Query A lấy Order#100; transaction khác thêm Line#9 trước Query B. Query B có thể thấy Line#9 dù nó chưa tồn tại khi Query A chạy không?

**Đáp án:** Có ở isolation cho phép mỗi statement có snapshot mới, ví dụ PostgreSQL READ COMMITTED. Dùng transaction snapshot phù hợp nếu cần graph nhất quán.

## 48. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Fetching](https://docs.hibernate.org/orm/7.2/userguide/html_single/#fetching): join fetching, batch fetching, subselect fetching và fetch strategies.
- [Hibernate ORM User Guide — HQL/JPQL joins and fetch joins](https://docs.hibernate.org/orm/7.2/querylanguage/html_single/): join semantics, fetch joins, distinct và query behavior.
- [Hibernate ORM User Guide — Batch fetching](https://docs.hibernate.org/orm/7.2/userguide/html_single/#batch-fetching): `@BatchSize`, default batch fetch size.
- [Hibernate ORM Javadocs — `BatchSize`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/annotations/BatchSize.html): batch fetching annotation.
- [Hibernate ORM Javadocs — `Fetch`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/annotations/Fetch.html): Hibernate fetch mode customization.
- [Hibernate ORM Configuration — Query settings](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/cfg/QuerySettings.html): query settings including pagination over collection fetch behavior for supported versions.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): query pagination, fetch joins, entity graphs and relationship mapping.
- [Spring Data JPA Reference — Paging, Sorting and Limiting](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): `Pageable`, `Page`, `Slice`, sort and query method behavior.
- [Spring Data Commons Reference — Scrolling](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html): `ScrollPosition`, `Window` and keyset-based scrolling.
- [PostgreSQL Documentation — LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html): pagination and need for predictable `ORDER BY`.
- [PostgreSQL Documentation — Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): index ordering and sort direction.
- [PostgreSQL Documentation — Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): `ROW_NUMBER()` and partitioned ranking.
- [PostgreSQL Documentation — EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): execution plans and performance diagnosis.
- [PostgreSQL Documentation — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshot visibility and concurrent changes.

**Ghi chú phiên bản:** Hành vi pagination kết hợp collection fetch, cảnh báo in-memory pagination, `fail_on_pagination_over_collection_fetch`, fetch strategy và Spring Data scrolling phụ thuộc Hibernate/Spring Data version. SQL `NULLS LAST`, window functions, CTE và index examples trong bài dùng PostgreSQL; cần chuyển đổi nếu dùng MySQL, Oracle hoặc SQL Server. Luôn kiểm tra generated SQL và integration test trên đúng DBMS/dialect của ứng dụng.

## Kết luận

Phân trang đúng với quan hệ đa trị bắt đầu bằng việc xác định **root entity là đơn vị của một trang**. Collection fetch join nhân root rows; SQL `LIMIT/OFFSET` trên join không tương đương giới hạn số roots, còn Hibernate in-memory pagination có thể đọc dữ liệu vượt xa page size. Với entity graph cần collections, chiến lược phổ biến và dễ kiểm soát là **query root IDs theo filter + deterministic order + pagination, sau đó fetch graph cho IDs đó và khôi phục thứ tự ban đầu**.

Thứ tự phải là một total order: mọi sort columns cần quy tắc null rõ ràng và một unique tie-breaker. Nếu cần duyệt sâu, keyset pagination dùng cursor chứa đầy đủ sort keys sẽ tránh chi phí offset lớn và giảm dịch chuyển trang do inserts ở đầu danh sách; nhưng nó không tự tạo snapshot khi sort keys hoặc membership thay đổi.

Cuối cùng, count phải đếm roots, nhiều collections nên được tải có chiến lược, và mọi phase cần dùng cùng tenant/security/filter scope. Hãy kiểm tra SQL thật, execution plan, concurrency và payload trên database tương đương production; một repository method trả `Page<T>` không tự bảo đảm pagination đúng khi entity graph có collection.
