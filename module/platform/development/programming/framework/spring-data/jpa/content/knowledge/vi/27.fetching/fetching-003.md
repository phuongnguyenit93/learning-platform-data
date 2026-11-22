# JOIN FETCH để tải dữ liệu theo nhu cầu từng trường hợp

## 1. Fetch dữ liệu theo use case

Một Entity thường có nhiều association: đơn hàng tham chiếu khách hàng, có nhiều dòng hàng, thanh toán và lịch sử trạng thái. Không phải use case nào cũng cần tất cả dữ liệu đó. Màn hình danh sách có thể chỉ cần mã đơn và tên khách hàng; màn hình chi tiết cần thêm dòng hàng; báo cáo có thể chỉ cần vài cột tổng hợp.

`JOIN FETCH` trong JPQL cho phép yêu cầu JPA tải một association cùng với Entity gốc trong một truy vấn. Đây là cách xây dựng fetch plan theo từng repository method, phù hợp khi biết rõ use case cần association nào.

Nguyên tắc thiết kế:

- Chỉ tải association mà use case sắp sử dụng.
- Giữ mapping mặc định LAZY cho phần lớn quan hệ, rồi chọn fetch plan ở query hoặc repository method.
- Dùng `JOIN FETCH` cho association có kích thước và cardinality phù hợp.
- Dùng EntityGraph, batch fetching hoặc DTO projection khi chúng thể hiện nhu cầu tốt hơn.
- Kiểm tra SQL, số hàng trả về, số truy vấn và bộ nhớ trên dữ liệu thực tế.

Fetch plan là quyết định đọc dữ liệu. Nó không thay đổi quyền sở hữu association, cascade hay vòng đời Entity.

## 2. JOIN và JOIN FETCH khác nhau thế nào?

`JOIN` kết hợp association để lọc, sắp xếp hoặc lấy thuộc tính liên quan trong query. Nó không yêu cầu provider khởi tạo association trong Entity graph.

`JOIN FETCH` vừa join association vừa yêu cầu tải association đó cùng Entity gốc. Sau query, code có thể truy cập association mà không cần một truy vấn LAZY riêng cho association đã fetch.

Ví dụ chỉ dùng JOIN để lọc đơn hàng theo thành phố của khách hàng:

```java
@Query("""
    select p
    from PurchaseOrder p
    join p.customer c
    where c.city = :city
    """)
List<PurchaseOrder> findByCustomerCity(@Param("city") String city);
```

Query dùng `c.city` để lọc. `p.customer` không được yêu cầu fetch; nếu code truy cập customer sau đó và association chưa có trong persistence context, Hibernate vẫn có thể phát sinh query bổ sung.

Với use case cần hiển thị khách hàng cùng đơn hàng:

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

`join fetch p.customer` yêu cầu tải customer trong cùng query. Chọn JOIN thường hay JOIN FETCH dựa trên việc association có cần được khởi tạo trong kết quả hay chỉ tham gia điều kiện.

## 3. Mapping LAZY và fetch plan theo từng query

Ví dụ Entity:

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private String orderNumber;
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
    private List<PurchaseOrderItem> items = new ArrayList<>();
}
```

Với mapping trên, query mặc định không cần tải `customer` hoặc `items` ngay khi lấy PurchaseOrder. Repository method có thể chọn association tùy màn hình:

- Danh sách đơn hàng: fetch `customer` nếu danh sách hiển thị tên khách hàng.
- Chi tiết đơn hàng: fetch `customer` và `items` nếu trang chi tiết hiển thị cả hai.
- Báo cáo tổng hợp: dùng DTO/projection nếu chỉ cần số đơn, tổng tiền hoặc tên khách hàng.
- Job xử lý đơn hàng: chỉ fetch association mà thuật toán thực sự cần.

JPA mặc định `ManyToOne` và `OneToOne` là EAGER; `OneToMany` và `ManyToMany` là LAZY. Nên cân nhắc khai báo to-one là LAZY để tránh tải ngoài ý muốn, rồi chọn fetch plan rõ ràng theo use case. EAGER không bảo đảm provider luôn dùng một SQL JOIN; provider có thể thực hiện truy vấn phụ.

## 4. INNER JOIN FETCH hay LEFT JOIN FETCH?

Fetch join không ghi loại join thì mặc định là INNER JOIN. INNER JOIN chỉ trả Entity gốc có association phù hợp. Nếu quan hệ có thể null và vẫn muốn giữ Entity gốc, dùng LEFT JOIN FETCH.

Ví dụ khách hàng là tùy chọn:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join fetch p.customer
    where p.id = :id
    """)
Optional<PurchaseOrder> findDetailHeader(@Param("id") Long id);
```

Đơn hàng vẫn được trả về ngay cả khi `customer` là null. Với `join fetch p.customer`, đơn hàng không có customer sẽ bị loại khỏi kết quả.

Chọn loại join theo nghiệp vụ:

| Nhu cầu | Cách dùng |
| --- | --- |
| Association bắt buộc và chỉ lấy root có association | `join fetch` |
| Association tùy chọn nhưng vẫn cần giữ root | `left join fetch` |
| Không cần association trong kết quả | Không fetch association |

Không đổi INNER thành LEFT chỉ để “an toàn” mà không xác định semantics. Loại join quyết định Entity gốc nào có mặt trong kết quả.

## 5. Use case 1: danh sách cần một association to-one

Màn hình danh sách đơn hàng thường hiển thị mã đơn, ngày tạo, trạng thái và tên khách hàng. Nếu tải danh sách PurchaseOrder rồi gọi `getCustomer().getName()` cho từng đơn, có thể phát sinh N+1.

Repository có thể fetch to-one association:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join fetch p.customer
    where p.status = :status
    order by p.createdAt desc, p.id desc
    """)
List<PurchaseOrder> findListRowsWithCustomer(
    @Param("status") OrderStatus status
);
```

Đây là lựa chọn phù hợp khi số lượng root đã được giới hạn hợp lý và danh sách thật sự cần customer. Với màn hình phân trang, fetch join to-one thường phù hợp hơn fetch join collection vì mỗi root chỉ ghép tối đa một customer.

Nếu chỉ cần `customer.name` để trả response, DTO projection có thể còn nhẹ hơn vì không cần materialize toàn bộ Entity graph.

## 6. Use case 2: trang chi tiết cần collection có kích thước kiểm soát

Trang chi tiết một đơn hàng thường cần thông tin khách hàng và toàn bộ dòng hàng của đúng một đơn. Có thể fetch cả to-one và một collection:

```java
@Query("""
    select distinct p
    from PurchaseOrder p
    left join fetch p.customer
    left join fetch p.items
    where p.id = :id
    """)
Optional<PurchaseOrder> findDetailById(@Param("id") Long id);
```

Truy vấn được giới hạn theo ID nên số root nhỏ. `items` vẫn có thể nhiều, do đó cần bảo đảm một đơn hàng không chứa collection khổng lồ ngoài dự kiến. Nếu collection có hàng chục nghìn phần tử, không nên tải tất cả chỉ vì endpoint đang hiển thị header.

`distinct` thể hiện mong muốn nhận root Entity duy nhất trong kết quả JPQL khi collection join tạo nhiều hàng cho cùng đơn hàng. SQL vẫn cần trả các hàng child khác nhau để Hibernate khởi tạo collection. Hibernate 6 tự loại bản sao root Entity do fetch join khỏi kết quả entity; hành vi có thể khác ở provider/phiên bản khác.

## 7. Use case 3: chỉ tải một phần dữ liệu liên quan

Fetch join tải association theo mapping của association. Nó không phải cơ chế projection từng cột bên trong collection. Nếu trang chỉ cần mã sản phẩm, số lượng và giá của các dòng hàng, có thể dùng DTO projection:

```java
public record OrderItemRow(
    Long orderId,
    String orderNumber,
    String productCode,
    int quantity,
    BigDecimal unitPrice
) {
}
```

```java
@Query("""
    select new com.example.order.OrderItemRow(
        p.id, p.orderNumber, i.productCode, i.quantity, i.unitPrice
    )
    from PurchaseOrder p
    join p.items i
    where p.id = :id
    order by i.id
    """)
List<OrderItemRow> findItemRows(@Param("id") Long id);
```

Đây là JPQL constructor projection; tên class đầy đủ và constructor phải khớp với expression. Query dùng JOIN thường vì nó tạo DTO từ các cột cần thiết, không cần khởi tạo `PurchaseOrder.items` trong persistence context.

Dùng DTO khi cần dữ liệu đọc có cấu trúc cố định, không cần thao tác trên Entity hoặc cascade/dirty checking. Dùng fetch join khi caller thực sự cần Entity cùng association được khởi tạo.

## 8. Use case 4: lọc theo child nhưng tải toàn bộ collection

Giả sử cần tìm các đơn hàng có ít nhất một item thuộc sản phẩm `P-100`, sau đó trang chi tiết cần toàn bộ items của mỗi đơn hàng.

Không nên dùng một fetch join alias vừa lọc child vừa kỳ vọng collection đã được tải đầy đủ. Nếu collection chỉ được fetch qua những child khớp điều kiện, ứng dụng có thể nhìn thấy một collection không đầy đủ.

Tách điều kiện lọc bằng EXISTS và fetch collection riêng:

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
List<PurchaseOrder> findOrdersWithAllItemsForProduct(
    @Param("productCode") String productCode
);
```

`exists` xác định root nào thỏa điều kiện. `left join fetch p.items` tải collection items đầy đủ của các root đã chọn. Query này có thể trả nhiều hàng SQL cho mỗi đơn hàng; không dùng trực tiếp với pagination collection fetch nếu chưa có chiến lược riêng.

## 9. Tránh N+1 bằng fetch join

N+1 thường xuất hiện khi query lấy N Entity gốc, sau đó code truy cập association LAZY của từng Entity:

```text
Query 1: lấy 30 đơn hàng
Query 2: lấy customer của đơn hàng 1
Query 3: lấy customer của đơn hàng 2
...
Query 31: lấy customer của đơn hàng 30
```

Fetch join to-one có thể tải customer trong cùng query, giảm số round-trip. Với collection, fetch join cũng có thể giảm N+1 nhưng làm tăng số hàng SQL theo số child.

Để xác định N+1 thật sự:

- Bật log SQL ở môi trường phát triển/test.
- Đếm số câu SELECT khi xử lý một trang dữ liệu.
- Kiểm tra association nào bị truy cập sau query chính.
- Dùng dữ liệu có nhiều root để thấy số truy vấn tăng theo N.
- Đo tổng số hàng và thời gian, không chỉ nhìn số câu SQL.

Không fetch toàn bộ association chỉ để tránh một truy vấn bổ sung nếu use case không sử dụng dữ liệu đó. Truy vấn ít hơn chưa chắc rẻ hơn nếu mỗi query trả quá nhiều cột và hàng.

## 10. Fetch join nhiều association

Có thể fetch nhiều association to-one trong cùng query nếu chúng có cardinality phù hợp:

```java
@Query("""
    select p
    from PurchaseOrder p
    left join fetch p.customer
    left join fetch p.createdBy
    where p.id = :id
    """)
Optional<PurchaseOrder> findHeaderWithPeople(@Param("id") Long id);
```

Fetch nhiều collection to-many cần thận trọng. Nếu một đơn hàng có 5 items và 4 payments, join cả hai collection có thể tạo 20 hàng SQL cho cùng root. Đây là tích Descartes giữa hai tập child.

Hibernate có thể ném `MultipleBagFetchException` khi cùng fetch nhiều bag collection, thường là các List không có thứ tự/index mapping phù hợp. Đổi List thành Set chỉ để tránh exception có thể thay đổi semantics và equality; nó cũng không loại bỏ tích số hàng SQL.

Với nhiều collection lớn, ưu tiên:

- Fetch một collection chính trong query đầu và tải collection còn lại bằng query riêng.
- Batch fetching để gom các truy vấn tải association.
- DTO projection chỉ lấy dữ liệu cần thiết.
- Tách endpoint/use case nếu dữ liệu có vòng đời hoặc kích thước độc lập.

## 11. Fetch join và phân trang

Fetch join to-one thường có thể kết hợp với `Pageable`, vì join không nhân số root nếu cardinality đúng. Fetch join collection thì khác: mỗi root có thể tạo nhiều hàng SQL, trong khi LIMIT/OFFSET của database áp dụng trên hàng join.

Vì vậy không nên phân trang trực tiếp một query `Page<PurchaseOrder>` có `left join fetch p.items`. Hibernate có thể cảnh báo hoặc phải phân trang trong bộ nhớ; với dữ liệu lớn, việc này gây tải nhiều hàng và tốn bộ nhớ.

Giải pháp phổ biến là hai bước:

1. Lấy trang ID của root theo filter và sort ổn định, không fetch collection.
2. Fetch collection cho danh sách ID đó bằng query thứ hai.
3. Sắp xếp lại kết quả theo thứ tự ID của trang đầu vì `IN (:ids)` không bảo đảm thứ tự.

Ví dụ repository:

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

Nếu trang đầu rỗng, bỏ qua query thứ hai để tránh `IN` với collection rỗng. Dùng thêm ID làm tie-breaker để sort ổn định. Nếu cần snapshot nhất quán giữa hai query trong lúc dữ liệu thay đổi đồng thời, cân nhắc transaction isolation theo yêu cầu nghiệp vụ và database.

## 12. EntityGraph: lựa chọn khai báo fetch plan

Không phải lúc nào cũng cần viết JPQL fetch join. Spring Data JPA hỗ trợ `@EntityGraph` để chỉ định association cần tải cho một repository method:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer", "items"})
    Optional<PurchaseOrder> findWithCustomerAndItemsById(Long id);
}
```

`attributePaths` dùng tên property Java của Entity. EntityGraph giúp tách điều kiện query khỏi fetch plan và dễ tái sử dụng cho nhiều method. Provider quyết định cách thực thi graph thành SQL; kiểm tra SQL thực tế để biết có join hay query bổ sung.

Có thể khai báo named entity graph trên Entity khi graph được dùng lặp lại. Dynamic EntityGraph phù hợp khi repository method cần fetch plan khác nhau theo use case.

EntityGraph cũng không giải quyết tự động mọi vấn đề pagination với collection. Nếu graph tải collection trong một query phân trang, vẫn phải đánh giá cardinality và hành vi provider.

## 13. Batch fetching và các phương án khác

Khi cần truy cập một association LAZY cho nhiều root nhưng không muốn join tất cả hàng vào một query, batch fetching có thể tải nhiều association trong một số truy vấn theo nhóm.

Ví dụ Hibernate:

```java
@BatchSize(size = 50)
@OneToMany(mappedBy = "purchaseOrder", fetch = FetchType.LAZY)
private List<PurchaseOrderItem> items = new ArrayList<>();
```

Hoặc cấu hình mặc định:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        default_batch_fetch_size: 50
```

`@BatchSize` là annotation riêng của Hibernate. Batch fetching vẫn giữ association LAZY cho đến khi được truy cập, sau đó có thể tải nhiều collection/proxy trong một query dùng nhiều ID. Kích thước batch cần đo theo workload và giới hạn bind parameter của database.

Với báo cáo hoặc response chỉ đọc, DTO projection thường tốt hơn việc tải Entity graph lớn. Với một collection được truy cập cho nhiều root, batch fetching có thể cân bằng số query và số hàng. Chọn theo dữ liệu và hành vi thật, không chỉ theo số annotation.

## 14. Fetch plan không thay đổi mapping và vòng đời

`JOIN FETCH` không làm association trở thành EAGER trong mọi query. Nó chỉ yêu cầu tải association cho query hiện tại.

Fetch plan cũng không:

- Thay đổi owning side hay `mappedBy`.
- Tự đồng bộ hai phía của quan hệ trong bộ nhớ.
- Bật cascade persist/merge/remove.
- Bật orphan removal.
- Quyết định API được phép trả dữ liệu nào.

Ví dụ, fetch `p.items` chỉ tải collection. Nó không có nghĩa thêm item vào collection sẽ tự persist nếu cascade chưa được cấu hình hoặc owning side chưa được cập nhật.

## 15. Ranh giới transaction và serialization

Association LAZY có thể phát sinh query khi được truy cập. Nếu persistence context đã đóng, truy cập một association chưa được tải có thể gây `LazyInitializationException` trong Hibernate.

Không nên dựa vào Open Session in View để mọi association luôn truy cập được khi serialize response. Cách đó có thể khiến quá trình tạo JSON âm thầm phát sinh N+1 và giữ database session lâu hơn dự kiến.

Thay vào đó:

- Tải association cần thiết trong service transaction bằng fetch join hoặc EntityGraph.
- Map kết quả sang DTO trước khi transaction kết thúc.
- Không trả Entity graph hai hướng trực tiếp nếu có thể tạo vòng lặp JSON hoặc lộ dữ liệu nội bộ.
- Dùng projection khi chỉ cần một tập trường xác định.

## 16. Cách kiểm tra fetch plan có đúng nhu cầu

Với mỗi use case, lập danh sách dữ liệu thực sự được dùng:

| Use case | Dữ liệu cần | Cách tải nên cân nhắc |
| --- | --- | --- |
| Danh sách đơn hàng | Header + tên khách hàng | Fetch join to-one hoặc DTO |
| Chi tiết đơn hàng | Header + customer + items có giới hạn | Fetch join collection cho một root hoặc EntityGraph |
| Báo cáo tổng hợp | ID, tổng tiền, số lượng | DTO projection/aggregate query |
| Xử lý nhiều đơn hàng | Một collection cần dùng cho mỗi root | Batch fetching hoặc query theo nhóm |
| Trang phân trang đơn hàng và items | Trang root + collection | Hai bước lấy ID rồi fetch collection |

Kiểm tra bằng SQL log, Hibernate statistics hoặc công cụ quan sát database:

- Số câu SELECT cho một request.
- Số hàng SQL được trả về sau join.
- Các cột được chọn và kích thước payload.
- Số association thực sự được truy cập.
- Thời gian query và execution plan.
- Bộ nhớ khi xử lý collection lớn.

Test nên dùng nhiều root và nhiều child; một test chỉ có một đơn hàng và một item thường không bộc lộ N+1 hoặc tích số hàng.

## 17. Lỗi thường gặp

**Dùng JOIN thường nhưng vẫn gặp N+1.** JOIN dùng để lọc/kết hợp; dùng `JOIN FETCH` hoặc EntityGraph nếu association cần được khởi tạo.

**Dùng INNER FETCH làm mất root không có association.** Chuyển sang `LEFT JOIN FETCH` nếu nghiệp vụ cần giữ root đó.

**Fetch collection khiến query trả nhiều hàng.** Một root có nhiều child là hành vi tự nhiên của join. Dùng `distinct` khi cần root duy nhất và đánh giá số hàng SQL.

**Fetch nhiều collection gây query rất lớn hoặc MultipleBagFetchException.** Tách query, batch fetch hoặc DTO; không đổi collection type một cách máy móc.

**Fetch collection cùng Page làm pagination trong bộ nhớ.** Lấy trang ID trước rồi fetch collection sau, hoặc chọn batch/DTO.

**Collection chỉ chứa child khớp điều kiện.** Không dùng điều kiện lọc trên alias fetch join để giả định collection đã tải đầy đủ; tách filter bằng EXISTS rồi fetch collection riêng.

**LazyInitializationException khi tạo response.** Tải dữ liệu cần thiết trong transaction và map sang DTO trước khi đóng persistence context.

**Fetch quá nhiều dữ liệu dù không dùng.** Rà soát từng use case, loại association không cần và xem xét DTO projection.

## 18. Checklist chọn JOIN FETCH

- Use case có thực sự cần association trong kết quả không?
- Association là to-one hay to-many? Số lượng child có được giới hạn hợp lý không?
- Chọn INNER hay LEFT theo việc có cần giữ root không có association hay không.
- Có thể dùng DTO projection nếu chỉ cần một số trường không?
- Có nhiều collection fetch cùng lúc gây tích số hàng hoặc bag exception không?
- Có kết hợp collection fetch với pagination không? Nếu có, chuyển sang chiến lược hai bước hoặc batch fetching.
- Điều kiện lọc child có tách khỏi fetch collection để collection không bị tải thiếu không?
- Fetch plan có được giới hạn theo query/use case thay vì đổi toàn cục sang EAGER không?
- Đã kiểm tra SQL, số hàng, số truy vấn, bộ nhớ và transaction chưa?

`JOIN FETCH` hiệu quả nhất khi được chọn theo dữ liệu mà một use case thực sự cần. Fetch to-one cho danh sách, fetch collection có giới hạn cho trang chi tiết, và dùng EntityGraph, batch fetching hoặc DTO khi hình dạng dữ liệu khác đi. Kiểm soát cardinality và pagination giúp giảm N+1 mà không biến một request nhỏ thành truy vấn tải quá nhiều dữ liệu.