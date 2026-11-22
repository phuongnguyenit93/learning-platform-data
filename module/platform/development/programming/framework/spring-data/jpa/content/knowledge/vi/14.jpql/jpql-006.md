# JOIN FETCH và khác biệt với join phục vụ lọc dữ liệu

## 1. Hai mục đích khác nhau của JOIN

Trong JPQL, `JOIN` và `JOIN FETCH` đều có thể khiến SQL dùng phép JOIN, nhưng ý nghĩa đối với Entity khác nhau:

- `JOIN` kết hợp association để lọc, sắp xếp hoặc lấy dữ liệu từ phía liên quan. Nó không yêu cầu JPA khởi tạo association trong Entity kết quả.
- `JOIN FETCH` yêu cầu provider tải association được chỉ định cùng với Entity gốc trong truy vấn hiện tại. Đây là chỉ dẫn về fetch plan cho lần truy vấn đó.

Điểm này đặc biệt quan trọng với association LAZY. Một query có `JOIN` vẫn có thể trả về Entity mà association chưa được khởi tạo. Nếu sau đó code truy cập association, Hibernate có thể phát sinh query bổ sung. Muốn tải association cùng lúc, hãy dùng fetch join, entity graph hoặc một fetch plan khác.

## 2. Ví dụ mô hình

Giả sử đơn hàng tham chiếu đến khách hàng:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;
}
```

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String name;
    private String city;
}
```

`PurchaseOrder.customer` là ManyToOne LAZY. Khi tải nhiều đơn hàng rồi gọi `order.getCustomer().getName()`, nếu customer chưa được tải và không có trong persistence context/cache, Hibernate có thể thực hiện thêm truy vấn.

## 3. JOIN thông thường: lọc theo association

Ví dụ chỉ lấy đơn hàng của khách hàng ở một thành phố:

```java
@Query("""
    select p
    from PurchaseOrder p
    join p.customer c
    where c.city = :city
    """)
List<PurchaseOrder> findOrdersByCustomerCity(
    @Param("city") String city
);
```

`join p.customer c` cho phép tham chiếu thuộc tính của Customer trong điều kiện `where`. Kết quả được chọn là `PurchaseOrder`. JPQL không yêu cầu `p.customer` phải được fetch; khi code truy cập customer sau query, association vẫn có thể được tải bằng một truy vấn LAZY riêng.

JOIN thường phù hợp khi association chỉ tham gia điều kiện lọc hoặc sắp xếp, còn kết quả cần trả về không yêu cầu khởi tạo toàn bộ association.

INNER JOIN chỉ giữ đơn hàng có customer phù hợp. Nếu quan hệ có thể null, đơn hàng không có customer sẽ không xuất hiện.

## 4. LEFT JOIN và vị trí đặt điều kiện

`LEFT JOIN` giữ các hàng phía trái ngay cả khi không có association phù hợp. Nhưng đặt điều kiện trong `WHERE` có thể loại các hàng null:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join p.customer c
    where c.city = :city
    """)
List<PurchaseOrder> findOrdersByCustomerCity(
    @Param("city") String city
);
```

Điều kiện `where c.city = :city` không đúng với hàng có `c` là null, nên kết quả gần với INNER JOIN.

Nếu muốn giữ mọi đơn hàng và chỉ giới hạn customer được ghép vào join, đặt điều kiện ở `ON`:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join p.customer c on c.city = :city
    """)
List<PurchaseOrder> findAllWithCustomerMatchingCity(
    @Param("city") String city
);
```

Điều kiện `ON` giới hạn các hàng customer tham gia join nhưng không loại đơn hàng ở phía trái. Đây vẫn là JOIN phục vụ truy vấn; nó không phải chỉ dẫn fetch association.

## 5. JOIN FETCH: tải association cùng Entity gốc

Khi màn hình cần thông tin customer của từng đơn hàng, fetch join yêu cầu Hibernate tải association cùng truy vấn:

```java
@Query("""
    select p
    from PurchaseOrder p
    join fetch p.customer
    where p.status = :status
    """)
List<PurchaseOrder> findWithCustomerByStatus(
    @Param("status") OrderStatus status
);
```

`join fetch p.customer` yêu cầu tải customer cùng PurchaseOrder. Sau khi query hoàn tất, truy cập `p.getCustomer().getName()` không cần truy vấn lazy riêng cho association đó.

Fetch join kiểu INNER JOIN chỉ trả đơn hàng có customer. Nếu muốn giữ cả đơn hàng không có customer, dùng `left join fetch`:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join fetch p.customer
    where p.status = :status
    """)
List<PurchaseOrder> findWithOptionalCustomerByStatus(
    @Param("status") OrderStatus status
);
```

Fetch join chỉ thay đổi cách tải association cho query đó. Nó không đổi mapping LAZY toàn cục thành EAGER; các query khác vẫn dùng fetch plan riêng.

## 6. Lọc theo child nhưng vẫn tải toàn bộ collection

Giả sử `PurchaseOrder.items` là OneToMany LAZY. Nếu cần tìm đơn hàng có ít nhất một item thuộc sản phẩm `P-100`, JOIN thường có thể lọc:

```java
@Query("""
    select distinct p
    from PurchaseOrder p
    join p.items i
    where i.productCode = :productCode
    """)
List<PurchaseOrder> findOrdersContainingProduct(
    @Param("productCode") String productCode
);
```

Query này chọn các đơn hàng có item khớp điều kiện. Collection `p.items` không được khai báo fetch; khi ứng dụng duyệt collection, Hibernate có thể phát sinh truy vấn khác.

Nếu cần lọc parent theo một child nhưng tải toàn bộ collection của parent đó, tách điều kiện bằng `exists` và fetch join riêng:

```java
@Query("""
    select distinct p
    from PurchaseOrder p
    left join fetch p.items
    where exists (
        select i.id
        from PurchaseOrderItem i
        where i.purchaseOrder = p
          and i.productCode = :productCode
    )
    """)
List<PurchaseOrder> findOrdersAndAllItemsContainingProduct(
    @Param("productCode") String productCode
);
```

`exists` quyết định đơn hàng nào được chọn; fetch join tải collection items của các đơn hàng đó. Cách tách này tránh việc dùng cùng một join alias để lọc child rồi vô tình hiểu collection đã tải là đầy đủ dù query chỉ lấy child khớp điều kiện.

Join collection có thể tạo nhiều hàng SQL cho một root, một hàng trên mỗi child phù hợp. `distinct` thể hiện mong muốn nhận root Entity duy nhất ở mức kết quả JPQL. Hibernate 6 tự loại bản sao root Entity do fetch join khỏi kết quả entity; các provider/phiên bản khác có thể có hành vi khác. Dù ORM khử trùng lặp, SQL vẫn có thể xử lý nhiều hàng vì các child khác nhau.

## 7. N+1 và khi nào fetch join hữu ích

N+1 xảy ra khi lấy N parent rồi truy cập association LAZY của từng parent, làm phát sinh thêm khoảng N truy vấn:

```text
Query 1: lấy 30 PurchaseOrder
Query 2: lấy Customer của order 1
Query 3: lấy Customer của order 2
...
Query 31: lấy Customer của order 30
```

Fetch join ManyToOne có thể lấy đơn hàng và customer trong một query, giảm round-trip. Fetch join collection cũng có thể giảm N+1, nhưng phải xem số lượng child, số hàng SQL, bộ nhớ và pagination.

Không thêm fetch join vào mọi query. Nếu association không được sử dụng, tải thêm dữ liệu chỉ làm tăng truyền tải và chi phí xử lý.

## 8. Fetch join collection và pagination

Fetch join collection cùng `Pageable` cần đặc biệt thận trọng. Một parent có nhiều child tạo nhiều hàng SQL; database phân trang trên hàng join trong khi ứng dụng mong muốn phân trang theo parent. Kết quả có thể sai kích thước trang hoặc Hibernate phải phân trang trong bộ nhớ.

Với Hibernate, có thể bật fail-fast để phát hiện collection fetch join kết hợp pagination:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        query:
          fail_on_pagination_over_collection_fetch: true
```

Một giải pháp phổ biến là hai bước:

1. Truy vấn trang ID hoặc root Entity theo điều kiện và sort, không fetch collection.
2. Truy vấn fetch join collection cho nhóm ID vừa lấy.
3. Sắp xếp kết quả chi tiết theo thứ tự ID của trang đầu, vì `IN (:ids)` không bảo đảm thứ tự.

```java
@Query("""
    select p.id
    from PurchaseOrder p
    where p.status = :status
    order by p.createdAt desc, p.id desc
    """)
Page<Long> findPageIds(
    @Param("status") OrderStatus status, Pageable pageable
);

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

Nếu trang rỗng, bỏ qua query thứ hai để tránh `IN` với collection rỗng. Có thể dùng batch fetching hoặc DTO query nếu phù hợp hơn.

## 9. Tránh fetch nhiều collection lớn

Fetch join hai collection lớn cùng lúc có thể tạo tích Descartes. Nếu một đơn hàng có 5 item và 4 payment, join cả hai collection có thể tạo 20 hàng SQL cho cùng một đơn hàng. Dữ liệu lặp làm tăng truyền tải, bộ nhớ và công việc khử trùng lặp.

Hibernate cũng có thể ném `MultipleBagFetchException` khi cùng fetch nhiều bag collection, thường là các List không có mapping thứ tự/index phù hợp. Không đổi List thành Set chỉ để né lỗi nếu điều đó làm thay đổi semantics hoặc equality. Thường nên tải các collection lớn bằng query riêng, batch fetching, DTO projection hoặc endpoint tách biệt.

## 10. JOIN FETCH và DTO projection

Nếu chỉ cần vài trường để trả API, DTO projection có thể rõ ràng và nhẹ hơn việc tải Entity graph:

```java
public record OrderCustomerView(
    Long orderId, String orderNumber, String customerName
) {
}
```

```java
@Query("""
    select new com.example.api.OrderCustomerView(
        p.id, p.orderNumber, c.name
    )
    from PurchaseOrder p
    join p.customer c
    where c.city = :city
    """)
List<OrderCustomerView> findOrderViewsByCustomerCity(
    @Param("city") String city
);
```

Query dùng JOIN thường để lọc và chọn dữ liệu cho DTO. Không cần fetch join vì kết quả không phải Entity `PurchaseOrder` cần khởi tạo association. DTO giúp giới hạn cột trả về và tránh serialize Entity graph hai hướng.

## 11. Giới hạn JPQL cần nhớ

- Fetch join phải chỉ rõ association path, ví dụ `join fetch p.customer` hoặc `left join fetch p.items`.
- Trong JPQL chuẩn, fetch join không khai báo identification variable/alias như JOIN thông thường. Một số extension của Hibernate cho phép alias trong trường hợp đặc biệt, nhưng không nên dựa vào nếu cần portable JPQL.
- Fetch join không dùng trong subquery theo JPQL chuẩn.
- Fetch join được thiết kế để tải association của Entity owner; không dùng nó như công cụ thay thế DTO projection.
- Không dùng fetch join collection trực tiếp với pagination nếu chưa đánh giá số hàng và hành vi provider.

## 12. Lỗi thường gặp

**Dùng JOIN nhưng vẫn gặp N+1.** JOIN phục vụ lọc không bảo đảm association được fetch. Kiểm tra SQL khi truy cập association và cân nhắc fetch join hoặc EntityGraph.

**Fetch join làm số kết quả tăng.** Collection join tạo nhiều hàng SQL cho một root. Kiểm tra `distinct`, số child và cách provider xử lý duplicate entity.

**Parent không có association bị mất khỏi kết quả.** `join fetch` là inner join; dùng `left join fetch` nếu cần giữ parent không có association.

**Collection chỉ chứa child thỏa điều kiện.** Tách lọc bằng `exists` và fetch toàn collection bằng join fetch riêng.

**Phân trang chậm hoặc cảnh báo in-memory pagination.** Dùng hai bước lấy ID rồi fetch, batch fetching hoặc DTO.

**MultipleBagFetchException.** Tránh fetch nhiều bag collection trong một query; cân nhắc query riêng hoặc batch fetching.

**DTO query báo lỗi khi có fetch join.** Dùng JOIN thường để chọn các trường projection; fetch join dành cho association của Entity được tải.

## 13. Checklist lựa chọn

- Cần lọc theo thuộc tính association: dùng `JOIN` hoặc `EXISTS`.
- Cần tải Entity cùng association: dùng `JOIN FETCH` hoặc EntityGraph.
- Cần giữ parent không có association: dùng `LEFT JOIN` hoặc `LEFT JOIN FETCH`.
- Chỉ cần vài trường cho API: dùng DTO projection và JOIN thường.
- Cần phân trang parent cùng collection: lấy trang ID trước rồi fetch collection theo ID hoặc dùng batch fetching.
- Tránh fetch nhiều collection lớn cùng lúc.
- Kiểm tra SQL, số hàng trả về, round-trip và execution plan trên database thực tế.

`JOIN` dùng để kết hợp và lọc dữ liệu; `JOIN FETCH` điều khiển việc tải association vào Entity graph. Phân biệt hai mục đích này giúp giảm N+1 mà không tải thừa dữ liệu, làm sai pagination hoặc tạo truy vấn có quá nhiều hàng.