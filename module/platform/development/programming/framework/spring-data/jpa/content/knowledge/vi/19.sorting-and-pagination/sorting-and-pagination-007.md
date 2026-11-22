# Phân trang khi join quan hệ và tránh đếm trùng

## 1. Vì sao JOIN ảnh hưởng đến phân trang?

Spring Data JPA hỗ trợ phân trang bằng `Pageable`, `Page<T>` và `Slice<T>`. Khi query chỉ đọc một bảng hoặc join tới một association có tối đa một bản ghi ở phía liên quan, việc phân trang thường khá trực tiếp. Vấn đề xuất hiện khi query join một quan hệ to-many như `PurchaseOrder.items`: một đơn hàng có thể tạo nhiều hàng trong kết quả SQL.

Ví dụ một đơn hàng có ba item:

```text
purchase_order       purchase_order_item
order_id = 10        item_id = 1, order_id = 10
                     item_id = 2, order_id = 10
                     item_id = 3, order_id = 10
```

Join tạo ba hàng SQL cho cùng một đơn hàng. Nếu database áp dụng `LIMIT/OFFSET` trên các hàng join, một trang có thể chứa ít Entity gốc hơn kích thước yêu cầu hoặc cùng một Entity xuất hiện ở nhiều vị trí. Count query cũng có thể đếm ba hàng thay vì một đơn hàng.

Điều cần phân trang thường là **root Entity duy nhất**, không phải số hàng sau join. Vì vậy phải xem cardinality của association và cách query chọn/count root.

## 2. JOIN to-one và to-many có tác động khác nhau

- `ManyToOne` hoặc `OneToOne` thường ghép tối đa một hàng liên quan cho mỗi root. Join loại này thường không nhân số root, miễn là schema và mapping bảo đảm cardinality tương ứng.
- `OneToMany` hoặc `ManyToMany` có thể ghép nhiều hàng liên quan cho một root. Join loại này có thể nhân hàng SQL và làm count sai nếu đếm trực tiếp.
- Join nhiều collection to-many trong cùng query có thể tạo tích số hàng. Một đơn hàng có 4 item và 3 payment có thể tạo 12 hàng SQL.

Không phải mọi query có JOIN đều cần `DISTINCT`. Chỉ thêm khi cardinality và kết quả thực tế có thể tạo root trùng. Tránh dùng DISTINCT theo thói quen nếu query không tạo trùng, vì database có thể phải thực hiện thêm công việc sort/hash.

## 3. Dùng DISTINCT khi join collection để lọc

Ví dụ cần lấy các đơn hàng có ít nhất một item thuộc sản phẩm được chọn:

```java
@Query(
    value = """
        select distinct p
        from PurchaseOrder p
        join p.items i
        where i.productCode = :productCode
        """,
    countQuery = """
        select count(distinct p.id)
        from PurchaseOrder p
        join p.items i
        where i.productCode = :productCode
        """
)
Page<PurchaseOrder> findOrdersByProduct(
    @Param("productCode") String productCode,
    Pageable pageable
);
```

`select distinct p` yêu cầu kết quả JPQL chỉ có mỗi root `PurchaseOrder` một lần dù nhiều item cùng khớp. `countQuery` dùng `count(distinct p.id)` để đếm số đơn hàng duy nhất, không đếm số dòng item.

Count query cần giữ nguyên logic lọc ảnh hưởng đến tập root, nhưng thường không cần các fetch join, sort hoặc phần chọn dữ liệu không liên quan đến việc đếm. Với join to-one, `count(p)` có thể đủ; với join to-many, `count(distinct p.id)` thường là lựa chọn an toàn khi cần đếm root duy nhất.

## 4. Dùng EXISTS để tránh nhân hàng

Nếu mục tiêu chỉ là kiểm tra có ít nhất một child thỏa điều kiện, `EXISTS` thường diễn đạt ý định tốt hơn JOIN:

```java
@Query(
    value = """
        select p
        from PurchaseOrder p
        where exists (
            select i.id
            from PurchaseOrderItem i
            where i.purchaseOrder = p
              and i.productCode = :productCode
        )
        """,
    countQuery = """
        select count(p.id)
        from PurchaseOrder p
        where exists (
            select i.id
            from PurchaseOrderItem i
            where i.purchaseOrder = p
              and i.productCode = :productCode
        )
        """
)
Page<PurchaseOrder> findOrdersHavingProduct(
    @Param("productCode") String productCode,
    Pageable pageable
);
```

Subquery chỉ xác định có hay không có item phù hợp; query ngoài vẫn chọn mỗi `PurchaseOrder` một lần. Vì vậy không cần `distinct` cho root trong ví dụ này. Database có thể thực hiện semi-join hoặc kế hoạch tương đương tùy optimizer.

Ưu tiên `EXISTS` khi child chỉ được dùng để kiểm tra điều kiện. Dùng JOIN khi cần lấy thuộc tính child trong projection, sắp xếp theo child, group/aggregate hoặc có lý do khác cần kết hợp hàng.

## 5. Tại sao cần countQuery riêng?

Với kiểu trả về `Page<T>`, Spring Data cần thông tin tổng số phần tử để tính tổng trang. Framework có thể suy luận count query từ query chính trong các trường hợp đơn giản. Khi query có DISTINCT, join phức tạp, group, native SQL hoặc projection đặc biệt, suy luận tự động có thể không phản ánh đúng số root duy nhất.

Khai báo `countQuery` rõ ràng giúp kiểm soát phép đếm:

- Đếm root Entity hoặc root ID, không đếm số hàng join nếu yêu cầu là số root.
- Giữ lại các điều kiện WHERE/EXISTS ảnh hưởng tới tập root.
- Bỏ `fetch join` và `ORDER BY` không cần thiết trong count query.
- Với query có `GROUP BY`/`HAVING`, xác định rõ tổng số nhóm hay tổng số root mà API muốn báo; có thể cần count subquery hoặc native count query riêng.

Không sao chép máy móc query chính rồi thay `select` bằng `count(*)`. Khi join to-many, `count(*)` thường đếm các dòng sau join và cho tổng lớn hơn số Entity duy nhất.

## 6. Phân trang khi cần fetch collection

Không nên phân trang trực tiếp query fetch join collection:

```java
// Không nên dùng trực tiếp cho Page khi items là collection to-many.
@Query("select p from PurchaseOrder p left join fetch p.items where p.status = :status")
Page<PurchaseOrder> findPageWithItemsByStatus(
    @Param("status") OrderStatus status, Pageable pageable
);
```

Fetch join collection tạo nhiều hàng SQL cho mỗi parent. Database phân trang các hàng đó, không phải object graph parent đã khử trùng lặp. Hibernate có thể cảnh báo và thực hiện pagination trong bộ nhớ; dữ liệu lớn có thể gây tốn bộ nhớ và thời gian.

Với Hibernate, có thể bật fail-fast để phát hiện trường hợp này:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
```

Thuộc tính trên giúp biến một tình huống dễ gây chậm thành lỗi rõ ràng trong môi trường kiểm thử. Nó không tự sửa query; cần chọn cách tải dữ liệu phù hợp.

## 7. Chiến lược hai bước: phân trang ID rồi fetch collection

Đây là cách phổ biến khi API cần trang các root Entity và đầy đủ collection của từng root:

**Bước 1 — lấy trang ID duy nhất:**

```java
@Query(
    value = """
        select p.id
        from PurchaseOrder p
        where p.status = :status
          and exists (
              select i.id
              from PurchaseOrderItem i
              where i.purchaseOrder = p
                and i.productCode = :productCode
          )
        """,
    countQuery = """
        select count(p.id)
        from PurchaseOrder p
        where p.status = :status
          and exists (
              select i.id
              from PurchaseOrderItem i
              where i.purchaseOrder = p
                and i.productCode = :productCode
          )
        """
)
Page<Long> findPageOfOrderIds(
    @Param("status") OrderStatus status,
    @Param("productCode") String productCode,
    Pageable pageable
);
```

Caller truyền sort ổn định, có thêm khóa duy nhất làm tie-breaker:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
```

`createdAt` và `id` là property Java của Entity. Thêm `id` giúp thứ tự xác định khi nhiều đơn hàng có cùng timestamp, tránh bản ghi nhảy trang chỉ vì thứ tự bằng nhau không được xác định.

**Bước 2 — tải collection cho ID trong trang:**

```java
@Query("""
    select distinct p
    from PurchaseOrder p
    left join fetch p.items
    where p.id in :ids
    """)
List<PurchaseOrder> findAllWithItemsByIdIn(
    @Param("ids") Collection<Long> ids
);
```

Query thứ hai không dùng `Pageable`; nó chỉ tải các root đã chọn và collection tương ứng. `LEFT JOIN FETCH` giữ đơn hàng ngay cả khi không có item.

**Bước 3 — giữ lại thứ tự trang đầu:**

```java
@Transactional(readOnly = true)
public Page<PurchaseOrder> searchWithItems(
        OrderStatus status, String productCode, Pageable pageable) {
    Page<Long> idPage = repository.findPageOfOrderIds(
        status, productCode, pageable
    );

    if (idPage.isEmpty()) {
        return new PageImpl<>(List.of(), pageable, idPage.getTotalElements());
    }

    List<PurchaseOrder> loaded = repository.findAllWithItemsByIdIn(
        idPage.getContent()
    );
    Map<Long, PurchaseOrder> byId = loaded.stream().collect(
        Collectors.toMap(PurchaseOrder::getId, Function.identity())
    );
    List<PurchaseOrder> ordered = idPage.getContent().stream()
        .map(byId::get)
        .filter(Objects::nonNull)
        .toList();

    return new PageImpl<>(
        ordered, pageable, idPage.getTotalElements()
    );
}
```

Đây là phần triển khai minh họa; cần import `Page`, `PageImpl`, `Pageable`, `List`, `Map`, `Collectors`, `Function` và `Objects`, đồng thời inject repository. `IN (:ids)` không bảo đảm thứ tự nên service phải sắp xếp theo danh sách ID ở bước một. Trong cùng transaction, mức isolation và dữ liệu thay đổi đồng thời vẫn có thể ảnh hưởng kết quả giữa hai query; nếu cần snapshot nhất quán chặt chẽ, chọn isolation phù hợp với database và yêu cầu nghiệp vụ.

## 8. LEFT JOIN: điều kiện ở ON hay WHERE?

Khi join tùy chọn, vị trí đặt điều kiện có thể thay đổi tập root:

```java
select p
from PurchaseOrder p
left join p.customer c
where c.city = :city
```

Điều kiện `WHERE c.city = :city` loại các hàng có customer null, nên kết quả gần như INNER JOIN. Nếu muốn giữ mọi đơn hàng nhưng chỉ ghép customer thuộc thành phố chỉ định, có thể đặt điều kiện trên `ON`:

```java
select p
from PurchaseOrder p
left join p.customer c on c.city = :city
```

Count query phải phản ánh cùng semantics. Nếu điều kiện nằm trong ON và root không bị lọc, số root cần đếm có thể là toàn bộ đơn hàng, kể cả khi không có customer phù hợp. Hãy viết test cho cả trường hợp có và không có association.

## 9. DISTINCT không sửa mọi vấn đề pagination

`DISTINCT` có thể loại root trùng ở mức kết quả query, nhưng không phải giải pháp chung cho fetch join collection cùng `Pageable`:

- Khi join thường và chỉ chọn root Entity, `select distinct p` có thể làm tập root duy nhất trước pagination tùy SQL được sinh.
- Với fetch join collection, SQL cần trả các hàng child để khởi tạo collection. Những hàng này khác nhau ở cột child, nên SQL DISTINCT không thể gộp chúng thành một hàng duy nhất mà vẫn giữ đủ dữ liệu collection.
- ORM có thể khử trùng lặp root trong kết quả Java, nhưng điều đó không làm giảm số hàng mà database đã phân trang.

Vì vậy, hãy giải quyết cardinality và fetch plan trước; không thêm DISTINCT rồi giả định collection pagination đã an toàn.

## 10. Page, Slice và giới hạn của OFFSET

| Kiểu trả về | Thông tin cung cấp | Hệ quả truy vấn |
| --- | --- | --- |
| `Page<T>` | Nội dung trang, số phần tử tổng, tổng số trang | Thường cần count query |
| `Slice<T>` | Nội dung trang và có trang tiếp theo hay không | Thường lấy dư một phần tử để xác định hasNext, không cần tổng count |
| `List<T>` với `Pageable` | Nội dung của một đoạn dữ liệu | Không cung cấp tổng số trang |

Nếu UI không cần tổng số bản ghi, `Slice<T>` có thể tránh count query đắt tiền. Với dữ liệu rất lớn, OFFSET sâu có thể chậm vì database phải bỏ qua nhiều hàng trước khi trả trang.

Keyset/seek pagination dùng giá trị của hàng cuối trang trước làm điểm bắt đầu cho trang tiếp theo, ví dụ `(createdAt, id) < (:lastCreatedAt, :lastId)` khi sort giảm dần. Cách này phù hợp với sort ổn định, có index và có khóa tie-breaker duy nhất. Spring Data hỗ trợ scrolling/keyset trong các API phù hợp theo phiên bản; kiểm tra giới hạn của repository method và query đang dùng trước khi áp dụng.

## 11. Sort phải ổn định và hợp lệ

Phân trang cần thứ tự xác định. Nếu sort chỉ theo `createdAt` nhưng nhiều hàng có cùng timestamp, database có thể trả thứ tự khác nhau giữa các request. Thêm khóa duy nhất như `id` làm tie-breaker.

Sort từ `Pageable` phải dùng property/path hợp lệ của Entity hoặc alias được Spring Data hỗ trợ trong query khai báo. Không nối trực tiếp chuỗi sort do client gửi vào JPQL/native SQL. Nếu API chỉ cho phép sort theo một số trường, dùng allow-list và ánh xạ sang `Sort` an toàn.

Với native query, khả năng Spring Data thêm sort động phụ thuộc phiên bản và dạng SQL. Nếu query có CTE, union, function hoặc alias phức tạp, khai báo sort/count phù hợp hoặc xử lý trong custom repository.

## 12. Count query với projection, GROUP BY và native SQL

Với projection hoặc query tổng hợp, phải xác định rõ đơn vị cần đếm:

- Đếm root Entity: `count(distinct p.id)` khi join to-many có thể nhân hàng.
- Đếm nhóm: đếm số nhóm sau `GROUP BY`, không phải số bản ghi nguồn.
- Đếm dòng projection: đếm số dòng kết quả theo đúng semantics projection.

Với JPQL có group/having hoặc native SQL phức tạp, khai báo `countQuery` riêng. Count query không nhất thiết giống query nội dung; nó cần trả về đúng một số tổng theo hợp đồng của `Page`.

Ví dụ native query có join to-many:

```java
@Query(
    value = """
        select distinct p.*
        from purchase_order p
        join purchase_order_item i on i.purchase_order_id = p.id
        where i.product_code = :productCode
        """,
    countQuery = """
        select count(distinct p.id)
        from purchase_order p
        join purchase_order_item i on i.purchase_order_id = p.id
        where i.product_code = :productCode
        """,
    nativeQuery = true
)
Page<PurchaseOrder> findNativeOrdersByProduct(
    @Param("productCode") String productCode,
    Pageable pageable
);
```

Native query dùng tên bảng/cột vật lý và cú pháp phụ thuộc database. `countQuery` tường minh đặc biệt hữu ích vì Spring Data không thể luôn suy luận count chính xác từ mọi SQL native.

## 13. Kiểm thử pagination khi có join

Test nên tạo dữ liệu có cardinality khác nhau:

1. Một parent có nhiều child cùng khớp filter.
2. Một parent có nhiều child nhưng chỉ một child khớp.
3. Parent không có child.
4. Nhiều parent có cùng giá trị sort.
5. Trang đầu, trang giữa, trang cuối và trang rỗng.
6. Dữ liệu có thay đổi đồng thời nếu nghiệp vụ yêu cầu consistency giữa các trang.

Với mỗi trường hợp, kiểm tra:

- Không có root ID trùng trong nội dung trang.
- Kích thước trang đúng, ngoại trừ trang cuối.
- `totalElements` là số root/group theo hợp đồng, không phải số hàng join.
- Thứ tự ổn định và không thiếu/trùng bản ghi giữa các trang trong cùng snapshot dữ liệu.
- Count query có SQL và execution plan phù hợp.
- Query fetch collection không gây in-memory pagination hoặc tải quá nhiều hàng.

Chạy integration test trên database mục tiêu hoặc một database tương thích sát với môi trường triển khai. In-memory database có thể có khác biệt về optimizer, kiểu dữ liệu và cú pháp native SQL.

## 14. Lỗi thường gặp và cách xử lý

**`totalElements` lớn hơn số Entity duy nhất.** Count query đang đếm hàng sau join. Dùng `count(distinct root.id)` hoặc EXISTS nếu child chỉ phục vụ lọc.

**Trang có ít Entity hơn page size.** Join to-many đang nhân hàng trước LIMIT/OFFSET. Chọn root ID trước, rồi tải association ở query thứ hai.

**Entity lặp trong kết quả.** Kiểm tra cardinality, `select distinct root` và liệu query có đang trả projection/tuple thay vì root Entity.

**Hibernate cảnh báo pagination over collection fetch.** Không dùng `Pageable` trực tiếp với fetch join collection; dùng hai bước, batch fetching hoặc DTO.

**Count query trả tổng sai sau khi thêm LEFT JOIN.** Kiểm tra điều kiện ở ON/WHERE và xác định root nào phải được giữ.

**Trang bị trùng hoặc thiếu khi sort.** Thêm unique tie-breaker vào sort và xem xét dữ liệu thay đổi giữa các request.

**Native Page query không phân trang/đếm đúng.** Kiểm tra `countQuery`, SQL dialect, alias, sort và hỗ trợ của phiên bản Spring Data.

**DISTINCT làm query chậm.** Xem execution plan; nếu chỉ cần kiểm tra child tồn tại, thử EXISTS để tránh nhân hàng.

## 15. Checklist lựa chọn chiến lược

- Xác định association là to-one hay to-many trước khi thêm JOIN.
- Nếu child chỉ dùng để lọc, cân nhắc EXISTS.
- Nếu join to-many và chọn root, dùng DISTINCT khi cần và count distinct root ID.
- Với `Page<T>`, khai báo `countQuery` khi query phức tạp hoặc cần bảo đảm đếm đúng.
- Không phân trang trực tiếp collection fetch join.
- Dùng hai bước: trang ID/root trước, fetch collection sau; giữ thứ tự ID ban đầu.
- Dùng `Slice<T>` khi không cần tổng count; cân nhắc keyset khi OFFSET sâu.
- Dùng sort ổn định có unique tie-breaker.
- Kiểm thử parent nhiều child, parent không có child, count và trang rỗng trên database thực tế.

Phân trang chính xác khi join bắt đầu từ việc xác định đơn vị cần phân trang: root Entity, nhóm hay dòng projection. Khi join to-many, hãy kiểm soát số hàng phát sinh, đếm root duy nhất và tách fetch collection khỏi query phân trang khi cần. Cách làm này giữ cho nội dung trang, tổng số và thứ tự nhất quán với yêu cầu nghiệp vụ.