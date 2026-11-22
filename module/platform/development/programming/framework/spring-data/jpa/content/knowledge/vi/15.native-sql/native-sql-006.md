# Phân trang native query và khai báo countQuery

## 1. Vì sao native query cần quan tâm đến countQuery?

Spring Data JPA cho phép viết SQL thuần bằng `@Query(nativeQuery = true)` để tận dụng cú pháp hoặc tính năng riêng của database, xử lý truy vấn phức tạp, CTE, window function, hint hay cấu trúc SQL mà JPQL không biểu đạt thuận tiện.

Khi kết quả cần phân trang, method repository thường nhận thêm `Pageable` và trả về `Page<T>`. Một trang có hai phần thông tin:

- **Content:** danh sách bản ghi của trang hiện tại.
- **Metadata:** tổng số phần tử, tổng số trang, số trang hiện tại, kích thước trang và trạng thái còn trang tiếp theo hay không.

Để tạo metadata tổng, Spring Data cần biết tổng số hàng phù hợp với điều kiện lọc. Với native query, việc tự suy ra câu đếm từ mọi cấu trúc SQL không phải lúc nào cũng đáng tin cậy. Vì vậy, nên khai báo `countQuery` rõ ràng cho native query, đặc biệt khi có JOIN, DISTINCT, GROUP BY, CTE hoặc subquery.

Một native query phân trang thường gồm hai câu lệnh có mục đích khác nhau:

1. Câu truy vấn dữ liệu lấy đúng các hàng thuộc trang hiện tại.
2. Câu truy vấn đếm trả về tổng số kết quả logic thỏa điều kiện lọc.

Hai câu phải cùng mô tả một tập kết quả. Nếu content query lọc theo trạng thái và ngày tạo nhưng count query bỏ một điều kiện, tổng số trang sẽ sai dù dữ liệu của trang hiện tại đúng.

## 2. Pageable, Page và cơ chế phân trang

### 2.1. Pageable

`Pageable` mô tả yêu cầu phân trang:

- `pageNumber`: số trang, bắt đầu từ 0.
- `pageSize`: số phần tử tối đa trong một trang.
- `sort`: thông tin sắp xếp nếu query hỗ trợ.

Tạo một yêu cầu trang:

```java
Pageable pageable = PageRequest.of(0, 20);
```

Yêu cầu trên lấy trang đầu tiên với tối đa 20 kết quả. Trang thứ hai:

```java
Pageable pageable = PageRequest.of(1, 20);
```

Không nhầm số trang bắt đầu từ 0 của Spring Data với cách hiển thị số trang bắt đầu từ 1 ở giao diện người dùng.

### 2.2. Page

`Page<T>` chứa content và metadata tổng:

```java
Page<PurchaseOrder> page =
    repository.searchOrders("PAID", from, PageRequest.of(0, 20));

List<PurchaseOrder> orders = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

Vì `Page` cung cấp tổng số phần tử và tổng số trang, framework thường cần chạy count query. Spring Data có thể tối ưu một số trường hợp khi suy ra tổng từ content, nhưng không nên thiết kế dựa trên giả định count query sẽ luôn bị bỏ qua.

### 2.3. Slice

Nếu giao diện chỉ cần biết còn dữ liệu để tải tiếp hay không, không cần tổng số bản ghi, có thể dùng `Slice<T>`. Slice thường lấy thêm một phần tử để xác định có trang tiếp theo và tránh yêu cầu tổng count.

Với native query, việc dùng Slice phụ thuộc cách khai báo query và phiên bản Spring Data JPA. Nếu muốn kiểm soát rõ, có thể dùng `Pageable` với custom repository hoặc truy vấn giới hạn kích thước và kiểm tra phần tử dư. Chọn Page khi tổng số trang thực sự có giá trị với người dùng.

### 2.4. Ai áp dụng LIMIT/OFFSET?

Khi truyền `Pageable` vào repository query, Spring Data JPA áp dụng vị trí bắt đầu và số kết quả tối đa qua JPA query API. JPA provider như Hibernate chuyển chúng thành cú pháp phân trang phù hợp dialect của database.

Do đó, trong native query có thể giữ SQL phần lọc và sắp xếp; không cần tự nối LIMIT/OFFSET vào chuỗi SQL trong trường hợp Pageable đã được áp dụng. Cú pháp thực tế do dialect quyết định. Nếu tự thêm LIMIT/OFFSET đồng thời với Pageable, có thể phân trang hai lần hoặc tạo kết quả sai.

## 3. Native query cơ bản có countQuery

Giả sử bảng `purchase_order` lưu đơn hàng với các cột `id`, `order_no`, `status`, `created_at` và `total_amount`. Entity `PurchaseOrder` được ánh xạ đầy đủ với bảng này.

Repository có thể viết:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query(
        value = """
            select o.*
            from purchase_order o
            where o.status = :status
              and o.created_at >= :from
            order by o.created_at desc, o.id desc
            """,
        countQuery = """
            select count(*)
            from purchase_order o
            where o.status = :status
              and o.created_at >= :from
            """,
        nativeQuery = true
    )
    Page<PurchaseOrder> searchOrders(
        @Param("status") String status,
        @Param("from") LocalDateTime from,
        Pageable pageable
    );
}
```

Đây là ví dụ cho Spring Data JPA với Java text blocks. Các import và entity tương ứng cần có trong dự án.

Các điểm cần chú ý:

- `nativeQuery = true` cho biết phần `value` và `countQuery` là SQL của database.
- `value` lấy dữ liệu cho trang hiện tại.
- `countQuery` đếm toàn bộ kết quả thỏa cùng điều kiện.
- `@Param` liên kết tên tham số trong SQL với tham số method.
- `Pageable` được Spring Data dùng để giới hạn trang.
- `order by o.created_at desc, o.id desc` tạo thứ tự ổn định khi nhiều đơn hàng có cùng thời điểm tạo.

Vì query trả về `PurchaseOrder`, câu SELECT cần trả đủ các cột mà entity mapping yêu cầu. `o.*` phù hợp khi bảng có đúng các cột persistent của entity và không có xung đột tên cột do join. Với query join nhiều bảng, nên chọn rõ các cột của entity root hoặc dùng DTO projection.

Cách gọi:

```java
Pageable firstPage = PageRequest.of(0, 20);

Page<PurchaseOrder> result =
    repository.searchOrders(
        "PAID",
        LocalDateTime.of(2026, 1, 1, 0, 0),
        firstPage
    );

System.out.println(result.getNumber());
System.out.println(result.getSize());
System.out.println(result.getNumberOfElements());
System.out.println(result.getTotalElements());
System.out.println(result.getTotalPages());
```

Các giá trị in ra phụ thuộc dữ liệu trong database; không thể đưa ra stdout cố định nếu chưa có fixture cụ thể. Trong code thực tế, thường trả content và metadata cho service/controller thay vì in ra console.

## 4. countQuery phải đếm đúng tập kết quả

### 4.1. Giữ nguyên điều kiện lọc

Nguyên tắc quan trọng nhất là content query và count query phải có cùng điều kiện lọc.

Ví dụ content:

```sql
select o.*
from purchase_order o
where o.status = :status
  and o.created_at >= :from
order by o.created_at desc, o.id desc
```

Count tương ứng:

```sql
select count(*)
from purchase_order o
where o.status = :status
  and o.created_at >= :from
```

Count query không cần `ORDER BY`, vì thứ tự không ảnh hưởng tổng số hàng và chỉ làm công việc thừa.

Không bỏ sót điều kiện trong count query. Nếu content query lọc theo tenant, quyền truy cập, trạng thái hoặc ngày, count query phải áp dụng cùng điều kiện để không tiết lộ tổng số bản ghi ngoài phạm vi người dùng được phép xem.

### 4.2. JOIN có thể nhân số hàng

Giả sử một đơn hàng có nhiều dòng hàng. Truy vấn:

```sql
select o.*
from purchase_order o
join order_item i on i.order_id = o.id
where i.sku = :sku
order by o.created_at desc, o.id desc
```

Nếu một đơn hàng có nhiều dòng cùng SKU, một order có thể xuất hiện nhiều lần trong kết quả join. Nếu mục tiêu là phân trang theo đơn hàng, cần loại trùng ở content query:

```sql
select distinct o.*
from purchase_order o
join order_item i on i.order_id = o.id
where i.sku = :sku
order by o.created_at desc, o.id desc
```

Count query cần đếm ID đơn hàng duy nhất:

```sql
select count(distinct o.id)
from purchase_order o
join order_item i on i.order_id = o.id
where i.sku = :sku
```

Nếu dùng `count(*)` trong ví dụ này, database sẽ đếm số dòng sau JOIN, không phải số đơn hàng. Total elements và total pages vì vậy có thể lớn hơn số entity thực tế.

Một lựa chọn khác là dùng EXISTS để tránh nhân dòng:

```sql
select o.*
from purchase_order o
where exists (
    select 1
    from order_item i
    where i.order_id = o.id
      and i.sku = :sku
)
order by o.created_at desc, o.id desc
```

Count tương ứng:

```sql
select count(*)
from purchase_order o
where exists (
    select 1
    from order_item i
    where i.order_id = o.id
      and i.sku = :sku
)
```

EXISTS thường diễn đạt tốt ý định “đơn hàng có ít nhất một dòng hàng phù hợp” và tránh duplicate root rows. Hiệu năng thực tế phụ thuộc index và optimizer.

### 4.3. DISTINCT và count distinct

Khi content query trả DISTINCT theo entity root, count query cần đếm số entity root duy nhất. Không phải lúc nào `count(distinct o.id)` cũng đủ nếu projection là một tổ hợp nhiều cột hoặc một nhóm kết quả. Hãy xác định đơn vị mà Page đang phân trang: entity, DTO hay nhóm tổng hợp.

Nếu truy vấn trả một hàng cho mỗi nhóm GROUP BY, count query phải đếm số nhóm, không phải tổng số bản ghi nguồn. Có thể dùng subquery:

```sql
select count(*)
from (
    select o.status
    from purchase_order o
    where o.created_at >= :from
    group by o.status
) grouped_result
```

Đây là ví dụ SQL minh họa cho database hỗ trợ derived table trong FROM. Với truy vấn phức tạp, viết count query riêng hoặc custom repository rõ ràng hơn việc cố gắng tự động biến đổi SQL.

## 5. Native query có JOIN, CTE và truy vấn phức tạp

Native SQL có thể dùng CTE, window function, database function hoặc cú pháp riêng mà JPQL không hỗ trợ thuận tiện. Những cấu trúc này khiến việc tự suy ra count query khó hơn.

Ví dụ CTE:

```sql
with recent_orders as (
    select o.id, o.status, o.created_at
    from purchase_order o
    where o.created_at >= :from
)
select r.id, r.status, r.created_at
from recent_orders r
where r.status = :status
order by r.created_at desc, r.id desc
```

Count query phải đếm cùng tập kết quả sau mọi filter:

```sql
with recent_orders as (
    select o.id, o.status, o.created_at
    from purchase_order o
    where o.created_at >= :from
)
select count(*)
from recent_orders r
where r.status = :status
```

Không thể chỉ xóa phần SELECT hoặc ORDER BY một cách máy móc nếu query có DISTINCT, GROUP BY, HAVING, UNION hoặc nhiều tầng subquery. Count query phải giữ lại các phần ảnh hưởng đến tập kết quả.

Một số phiên bản Spring Data JPA có query enhancer/parser để hỗ trợ rewrite native SQL đơn giản hoặc phức tạp. Khả năng phụ thuộc phiên bản và parser có trên classpath. Với query phức tạp, khai báo countQuery tường minh là cách dễ kiểm soát và review nhất.

## 6. Sort trong native query

### 6.1. ORDER BY cố định

Cách đơn giản nhất là đặt thứ tự trực tiếp trong SQL:

```sql
order by o.created_at desc, o.id desc
```

Sau đó truyền Pageable không có Sort:

```java
Pageable pageable = PageRequest.of(0, 20);
```

Thứ tự nên có tie-breaker duy nhất, thường là primary key. Nếu chỉ sort theo created_at mà nhiều hàng có cùng thời điểm, database có thể trả chúng theo thứ tự khác nhau giữa các lần chạy. Khi chuyển trang, hàng có thể bị lặp hoặc bị bỏ qua.

### 6.2. Sort động phụ thuộc phiên bản và query parser

Khả năng thêm Sort động vào native query phụ thuộc phiên bản Spring Data JPA và cơ chế phân tích/rewrite SQL. Query đơn giản có thể được xử lý, nhưng SQL phức tạp, alias, CTE hoặc vendor-specific syntax có thể khiến rewrite thất bại hoặc tạo SQL không đúng.

Nếu API cần nhiều kiểu sort, hãy kiểm tra rõ phiên bản framework và test từng kiểu. Một lựa chọn an toàn là tạo các query variant cho các trường sort được hỗ trợ, hoặc dùng custom repository để chọn SQL từ danh sách cột và hướng sort đã cho phép.

Không bind tên cột hoặc từ khóa ASC/DESC như một parameter SQL thông thường. Parameter binding chỉ dành cho giá trị. Nếu phải tạo ORDER BY động, chỉ dùng identifier và hướng sort từ allowlist do ứng dụng định nghĩa; tuyệt đối không nối trực tiếp chuỗi sort do người dùng gửi vào SQL.

### 6.3. Count query không cần sort

Count query chỉ trả tổng số phần tử nên không cần ORDER BY. Nếu count query chứa ORDER BY không cần thiết, database có thể làm thêm công việc hoặc từ chối cú pháp tùy cấu trúc truy vấn.

## 7. Mapping kết quả native query

### 7.1. Trả về Entity

Khi method trả `Page<PurchaseOrder>`, native query cần cung cấp các cột đủ để Hibernate hydrate entity.

Ví dụ:

```sql
select o.*
from purchase_order o
where o.status = :status
```

Nếu chỉ chọn `o.id, o.order_no` nhưng entity còn nhiều persistent field bắt buộc, provider có thể báo lỗi hoặc không thể ánh xạ đầy đủ. Với join nhiều bảng, tránh chọn hai cột cùng tên không có alias rõ ràng.

Không dùng native entity query như một cách lấy vài cột rồi xem object là entity đầy đủ. Nếu chỉ cần một phần dữ liệu, dùng projection hoặc DTO.

### 7.2. Interface projection

Có thể trả về interface projection nếu alias của cột khớp tên getter:

```java
public interface OrderSummary {
    Long getId();
    String getOrderNo();
    BigDecimal getTotalAmount();
}
```

Query:

```java
@Query(
    value = """
        select
            o.id as id,
            o.order_no as orderNo,
            o.total_amount as totalAmount
        from purchase_order o
        where o.status = :status
        order by o.created_at desc, o.id desc
        """,
    countQuery = """
        select count(*)
        from purchase_order o
        where o.status = :status
        """,
    nativeQuery = true
)
Page<OrderSummary> findSummariesByStatus(
    @Param("status") String status,
    Pageable pageable
);
```

Alias phải được chọn theo cách Spring Data/provider ánh xạ projection trong phiên bản đang dùng. Với database phân biệt cách viết identifier hoặc tự chuyển alias về chữ thường, hãy kiểm thử mapping thực tế.

### 7.3. DTO class và SqlResultSetMapping

Với DTO class hoặc kết quả có kiểu phức tạp, có thể dùng @SqlResultSetMapping và @ConstructorResult theo JPA, hoặc custom repository để đọc native result và map rõ ràng.

Đừng giả định mọi native query đều tự động map constructor DTO theo cùng quy tắc giữa các phiên bản Spring Data JPA. Với mapping phức tạp, integration test là cần thiết.

## 8. Page và count query có chi phí riêng

Một lời gọi Page thường cần:
- Truy vấn content cho trang hiện tại.
- Truy vấn count để tính tổng số hàng.

Count có thể tốn đáng kể nếu query có nhiều JOIN, DISTINCT, GROUP BY, CTE hoặc filter thiếu index. Đừng chỉ tối ưu query content rồi bỏ qua count query.

Các cách giảm chi phí:

1. Dùng Slice nếu không cần tổng số phần tử.
2. Viết count query tối giản nhưng vẫn đếm đúng tập kết quả.
3. Dùng EXISTS khi chỉ cần xác nhận có bản ghi liên quan.
4. Tạo index cho điều kiện lọc và cột join.
5. Tránh JOIN không cần thiết trong cả content và count query.
6. Kiểm tra execution plan riêng cho hai câu SQL.
7. Giới hạn page size ở tầng API.

Count query có thể cần scan nhiều hàng để trả tổng chính xác. Nếu giao diện không thực sự cần số trang cuối, Slice hoặc keyset pagination có thể phù hợp hơn.

## 9. Offset pagination và dữ liệu thay đổi liên tục

PageRequest sử dụng page number và page size, tương ứng với offset pagination. Ví dụ page 100 với size 20 phải bỏ qua khoảng 2.000 hàng trước khi trả dữ liệu.

Offset lớn có thể chậm vì database vẫn phải tìm và bỏ qua nhiều hàng. Ngoài ra, nếu dữ liệu thay đổi giữa hai lần request, một bản ghi mới được chèn ở đầu danh sách có thể làm trang sau bị lặp hoặc bỏ sót hàng.

Để giảm rủi ro:
- Luôn dùng ORDER BY ổn định có tie-breaker duy nhất.
- Dùng transaction/snapshot phù hợp nếu nhiều trang phải nhất quán trong một phiên đọc.
- Với dữ liệu lớn hoặc thay đổi liên tục, cân nhắc keyset/seek pagination.

Ví dụ keyset theo created_at và id:

```sql
select o.*
from purchase_order o
where o.created_at < :lastCreatedAt
   or (
       o.created_at = :lastCreatedAt
       and o.id < :lastId
   )
order by o.created_at desc, o.id desc
fetch first :limit rows only
```

Cú pháp giới hạn hàng phụ thuộc database; đoạn SQL trên chỉ minh họa ý tưởng seek theo cặp khóa. Keyset thường không trả tổng số trang tự nhiên như Page, nhưng phù hợp cho luồng “tải thêm” với dữ liệu lớn.

## 10. Kiểm thử native pagination

Test cần xác nhận cả content lẫn metadata. Ví dụ với repository ở phần trước:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void returnsPageAndCorrectTotal() {
        LocalDateTime from = LocalDateTime.of(2026, 1, 1, 0, 0);

        repository.saveAll(List.of(
            new PurchaseOrder("PO-001", "PAID", from.plusDays(1)),
            new PurchaseOrder("PO-002", "PAID", from.plusDays(2)),
            new PurchaseOrder("PO-003", "PAID", from.plusDays(3)),
            new PurchaseOrder("PO-004", "CANCELLED", from.plusDays(4))
        ));

        Page<PurchaseOrder> page = repository.searchOrders(
            "PAID",
            from,
            PageRequest.of(0, 2)
        );

        assertThat(page.getContent()).hasSize(2);
        assertThat(page.getTotalElements()).isEqualTo(3);
        assertThat(page.getTotalPages()).isEqualTo(2);
        assertThat(page.hasNext()).isTrue();
    }
}
```

Đây là ví dụ minh họa; constructor và mapping của PurchaseOrder phải phù hợp schema test. Nếu dùng database embedded, SQL native cần tương thích với dialect của nó. Với SQL vendor-specific, nên chạy integration test trên cùng loại database production.

Nên kiểm thử thêm:

- Trang đầu, trang giữa và trang cuối.
- Trang vượt quá số trang hiện có.
- Không có kết quả.
- Hai hoặc nhiều hàng có cùng giá trị sort.
- JOIN làm nhân bản root entity.
- DISTINCT và count distinct.
- Filter có null nếu query hỗ trợ tùy chọn.
- Page size bằng 1 và page size tối đa được phép.
- Content và count có cùng điều kiện tenant/quyền truy cập.

## 11. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tổng số trang lớn hơn thực tế | countQuery dùng count(*) sau JOIN một-nhiều | Dùng count(distinct root.id) hoặc EXISTS |
| Content đúng nhưng total sai | countQuery thiếu điều kiện lọc | Đồng bộ mọi predicate giữa hai query |
| Query không phân trang | Method không nhận Pageable hoặc query được gọi sai cách | Thêm Pageable vào repository method và truyền PageRequest |
| Phân trang hai lần | SQL đã có LIMIT/OFFSET đồng thời Pageable cũng được áp dụng | Để provider áp dụng Pageable hoặc tự quản lý pagination trong custom query, không làm cả hai |
| Entity mapping lỗi | Native SELECT thiếu cột hoặc alias xung đột | Chọn đủ cột entity hoặc dùng projection/DTO |
| Sort động lỗi | Parser không rewrite được native SQL | ORDER BY cố định hoặc custom repository với allowlist |
| Trang bị lặp/bỏ sót hàng | ORDER BY không có tie-breaker duy nhất hoặc dữ liệu thay đổi | Thêm primary key vào thứ tự; cân nhắc snapshot/keyset |
| Count query chậm | JOIN, DISTINCT hoặc filter không có index | Tối giản count, dùng EXISTS, xem execution plan |
| GROUP BY có total sai | Đếm hàng nguồn thay vì số nhóm | Count subquery chứa cùng GROUP BY |
| Query chạy trên máy dev nhưng lỗi production | SQL/dialect/alias/collation khác nhau | Integration test trên database cùng loại production |

## 12. Checklist trước khi đưa native pagination vào production

- [ ] Content query trả đúng đơn vị cần phân trang: entity, DTO hay nhóm.
- [ ] countQuery đếm đúng cùng tập kết quả.
- [ ] Mọi điều kiện filter và quyền truy cập xuất hiện trong cả hai query.
- [ ] JOIN một-nhiều không làm nhân bản root nếu mục tiêu là phân trang root.
- [ ] Dùng count distinct hoặc EXISTS khi cần.
- [ ] Count query bỏ ORDER BY không cần thiết.
- [ ] ORDER BY content có tie-breaker duy nhất.
- [ ] Pageable được áp dụng một lần.
- [ ] Sort động chỉ nhận giá trị từ allowlist và tương thích parser.
- [ ] Entity mapping trả đủ cột; projection có alias rõ ràng.
- [ ] Page thực sự cần tổng số; nếu không, cân nhắc Slice hoặc keyset.
- [ ] Đã kiểm tra execution plan của content và count riêng.
- [ ] Integration test chạy trên database tương ứng với production.

## 13. Kết luận

Phân trang native query trong Spring Data JPA cần một câu SQL lấy content và một countQuery đếm chính xác tổng kết quả. Pageable mô tả trang và kích thước; JPA provider áp dụng pagination theo dialect. countQuery phải giữ cùng điều kiện lọc và đếm đúng đơn vị logic, đặc biệt khi query có JOIN, DISTINCT hoặc GROUP BY.

Với query đơn giản, count(*) có thể đủ. Với JOIN một-nhiều, thường cần count(distinct root.id) hoặc EXISTS. Với truy vấn nhóm, count subquery phải đếm số nhóm. Native query phức tạp nên có countQuery tường minh để dễ kiểm soát.

Hãy dùng thứ tự ổn định, kiểm tra sort theo phiên bản Spring Data, ánh xạ kết quả đúng kiểu, đo riêng chi phí count và cân nhắc Slice/keyset khi tổng số trang không cần thiết hoặc offset lớn. Integration test trên database thật là bước xác nhận cuối cùng cho cú pháp, dialect, mapping và metadata phân trang.