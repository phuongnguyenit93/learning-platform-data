# Chọn fetch plan theo màn hình, DTO và giao dịch

**Module:** Spring Data JPA  
**Nhóm kiến thức:** Tải dữ liệu

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích fetch plan và vai trò của nó trong việc tải quan hệ JPA.
- Chọn cách tải dữ liệu phù hợp với từng màn hình và trường dữ liệu cần hiển thị.
- Dùng EntityGraph, JOIN FETCH và DTO projection đúng trường hợp.
- Tránh N+1 query, tải thừa dữ liệu và lỗi lazy loading.
- Phối hợp fetch plan với ranh giới giao dịch ở tầng Service.
- Thiết kế truy vấn phân trang khi dữ liệu có quan hệ to-many.

## 2. Fetch plan là gì?

Fetch plan mô tả những thuộc tính và quan hệ nào cần được tải khi một truy vấn lấy entity. Trong JPA, mỗi association có chiến lược fetch, thường là LAZY hoặc EAGER. Tuy nhiên, chiến lược khai báo trên mapping chỉ là một phần của quyết định tải dữ liệu. Một use case cụ thể thường cần một tập quan hệ khác nhau.

Ví dụ, cùng một PurchaseOrder có thể xuất hiện trong ba màn hình:

- Danh sách đơn hàng chỉ hiển thị mã, tên khách hàng, ngày tạo và tổng tiền.
- Màn hình chi tiết hiển thị khách hàng, các dòng hàng và tên sản phẩm.
- Màn hình chỉnh sửa cần entity đơn hàng cùng những quan hệ mà nghiệp vụ cập nhật sẽ thay đổi.

Không nên dùng một fetch plan lớn cho mọi trường hợp. Danh sách chỉ cần vài trường có thể dùng DTO projection. Màn hình chi tiết có thể dùng EntityGraph hoặc JOIN FETCH. Luồng cập nhật có thể tải entity cần thiết trong giao dịch rồi thay đổi trạng thái của chúng.

Fetch plan tốt cần cân bằng ba mục tiêu:

1. Tải đủ dữ liệu để hoàn thành use case.
2. Tránh truy vấn lặp lại hoặc tải quan hệ không cần thiết.
3. Giới hạn số hàng, số cột và bộ nhớ phải xử lý.

**Fetch plan không phải transaction boundary.** Fetch plan quyết định dữ liệu nào được lấy; transaction boundary quyết định phạm vi commit/rollback và thời gian persistence context được sử dụng. Hai quyết định này cần phối hợp nhưng giải quyết hai vấn đề khác nhau.

## 3. Bắt đầu từ màn hình và use case

Trước khi viết Repository query, hãy liệt kê dữ liệu màn hình thực sự cần. Đừng bắt đầu bằng cách tải toàn bộ entity graph rồi mới chọn vài thuộc tính để hiển thị.

| Use case | Dữ liệu cần | Cách thường phù hợp |
|---|---|---|
| Danh sách, bảng tìm kiếm | Một số cột, bộ lọc, sắp xếp, tổng số bản ghi | DTO projection hoặc interface projection |
| Thẻ tóm tắt | Một vài trường của entity và quan hệ to-one | DTO projection hoặc EntityGraph nhỏ |
| Chi tiết chỉ đọc | Entity và một số quan hệ cụ thể | EntityGraph hoặc JOIN FETCH |
| Biểu mẫu chỉnh sửa | Entity cần cập nhật và quan hệ nghiệp vụ cần thiết | Tải entity trong Service transaction |
| Báo cáo, thống kê | Tổng hợp, đếm, nhóm, giá trị tính toán | JPQL aggregate hoặc DTO projection |
| API response | Hợp đồng dữ liệu ổn định, không cần entity đầy đủ | DTO projection hoặc ánh xạ DTO trong Service |

Một checklist hữu ích cho từng màn hình:

- Những cột nào thực sự hiển thị?
- Quan hệ nào cần truy cập?
- Quan hệ nào là to-one, quan hệ nào là to-many?
- Có phân trang hoặc sắp xếp không?
- Có cần entity được quản lý để cập nhật không?
- Kết quả được ánh xạ thành DTO ở trong hay ngoài giao dịch?
- Số lượng bản ghi và kích thước collection có thể lớn đến đâu?

Từ câu trả lời, chọn fetch plan nhỏ nhất nhưng vẫn đáp ứng use case.

## 4. LAZY và EAGER: cấu hình mặc định không thay thế fetch plan theo use case

### 4.1. LAZY

LAZY cho phép provider trì hoãn tải association cho tới khi ứng dụng truy cập thuộc tính đó, nếu provider hỗ trợ cách trì hoãn tương ứng.

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

LAZY thường là lựa chọn phù hợp cho association có thể không cần trong mọi use case. Đặc biệt, nên cân nhắc khai báo LAZY rõ ràng cho quan hệ to-one vì mặc định của @ManyToOne và @OneToOne trong JPA là EAGER. Quan hệ to-many mặc định là LAZY.

LAZY không có nghĩa quan hệ sẽ không bao giờ được tải. Khi code truy cập customer hoặc lines, Hibernate có thể phát sinh truy vấn bổ sung nếu dữ liệu chưa được tải và persistence context còn hoạt động.

### 4.2. EAGER

EAGER yêu cầu provider cung cấp association khi entity được tải. Điều đó **không đồng nghĩa** provider luôn dùng một câu SQL JOIN. Tùy truy vấn và provider, dữ liệu EAGER có thể được tải bằng truy vấn bổ sung.

Khai báo EAGER rộng rãi có thể khiến những màn hình không cần quan hệ vẫn phải tải dữ liệu đó, làm tăng số truy vấn, lượng dữ liệu và chi phí bộ nhớ. EAGER cũng không phải giải pháp tổng quát cho LazyInitializationException.

Nên giữ mapping đủ linh hoạt, thường ưu tiên LAZY cho quan hệ và chỉ định dữ liệu cần thiết tại query hoặc use case. Với entity graph và JPQL fetch join, ứng dụng thể hiện rõ hơn ý định tải của từng truy vấn.

## 5. Cách 1: dùng DTO projection cho màn hình cần một tập trường cố định

DTO projection phù hợp khi màn hình chỉ cần một số trường, không cần entity được quản lý và không cần thao tác cập nhật trên kết quả. Cơ sở dữ liệu có thể chỉ trả về những cột cần thiết.

### 5.1. Constructor projection với record

Giả sử danh sách đơn hàng chỉ cần mã, tên khách hàng và tổng tiền:

~~~java
package com.example.orders.dto;

import java.math.BigDecimal;

public record OrderSummary(
        Long orderId,
        String customerName,
        BigDecimal total
) {
}
~~~

Repository có thể dùng JPQL constructor expression:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select new com.example.orders.dto.OrderSummary(
            o.id,
            c.name,
            o.total
        )
        from PurchaseOrder o
        join o.customer c
        where o.status = :status
        order by o.createdAt desc
        """)
    Page<OrderSummary> findSummariesByStatus(
            @Param("status") OrderStatus status,
            Pageable pageable);
}
~~~

Tên lớp DTO trong constructor expression phải là tên đầy đủ của lớp. Kiểu và thứ tự tham số phải khớp với constructor. Ví dụ này giả định PurchaseOrder có customer, status, createdAt, total và Customer có name.

DTO projection có các lợi ích:

- Chỉ lấy các trường được chọn trong câu truy vấn.
- Không trả entity proxy hoặc collection lazy cho tầng giao diện.
- Tránh vô tình tải toàn bộ quan hệ chỉ để hiển thị vài cột.
- Hợp đồng dữ liệu của API hoặc màn hình ít phụ thuộc vào cấu trúc entity.

### 5.2. Interface projection

Spring Data JPA cũng hỗ trợ interface projection:

~~~java
public interface OrderSummaryView {
    Long getId();
    String getCustomerName();
    BigDecimal getTotal();
}
~~~

Có thể khai báo phương thức Repository với truy vấn đặt alias khớp tên thuộc tính:

~~~java
@Query("""
    select
        o.id as id,
        c.name as customerName,
        o.total as total
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    """)
Page<OrderSummaryView> findSummaryViews(
        @Param("status") OrderStatus status,
        Pageable pageable);
~~~

Interface projection thường tiện cho các kết quả đọc đơn giản. Với class-based projection, record hoặc DTO thể hiện kiểu dữ liệu và constructor rõ ràng hơn. Projection lồng nhau có thể khiến Spring Data phải materialize phần join của thuộc tính lồng nhau; không nên mặc định rằng mọi nested projection đều chỉ chọn đúng một vài cột tối thiểu. Hãy kiểm tra SQL thực tế.

**Khi nên chọn DTO:** danh sách, báo cáo, trang tìm kiếm, dữ liệu tổng hợp và API response có cấu trúc cố định. Nếu cần sửa entity, hãy tải entity được quản lý trong giao dịch thay vì cố cập nhật DTO projection.

## 6. Cách 2: dùng EntityGraph để chỉ định quan hệ cần tải

EntityGraph cho phép chỉ định association cần được tải cùng entity cho một use case, trong khi vẫn giữ mapping dùng chung tương đối gọn.

### 6.1. EntityGraph bằng attributePaths

Ví dụ màn hình chi tiết đơn hàng cần khách hàng, các dòng hàng và sản phẩm của từng dòng:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
    })
    Optional<PurchaseOrder> findWithDetailsById(Long id);
}
~~~

Spring Data JPA tạo EntityGraph động từ attributePaths. Các đường dẫn phải khớp thuộc tính Java của entity, không phải tên cột SQL. Ở đây:

- customer là quan hệ từ PurchaseOrder đến Customer.
- lines là collection OrderLine.
- lines.product là quan hệ từ OrderLine đến Product.

Có thể áp dụng EntityGraph cho query method dẫn xuất hoặc query method có @Query. Hãy kiểm tra SQL được provider tạo ra vì cách thực thi cụ thể phụ thuộc provider và cấu trúc quan hệ.

### 6.2. EntityGraph được đặt tên

Có thể khai báo graph trên entity khi một fetch plan được tái sử dụng:

~~~java
@Entity
@NamedEntityGraph(
    name = "PurchaseOrder.detail",
    attributeNodes = {
        @NamedAttributeNode("customer"),
        @NamedAttributeNode(
            value = "lines",
            subgraph = "lines-with-product"
        )
    },
    subgraphs = {
        @NamedSubgraph(
            name = "lines-with-product",
            attributeNodes = {
                @NamedAttributeNode("product")
            }
        )
    }
)
public class PurchaseOrder {
    // Các thuộc tính và mapping
}
~~~

Repository dùng graph đã đặt tên:

~~~java
@EntityGraph(
    value = "PurchaseOrder.detail",
    type = EntityGraph.EntityGraphType.FETCH
)
Optional<PurchaseOrder> findDetailById(Long id);
~~~

Với graph kiểu FETCH, các thuộc tính được liệt kê được yêu cầu tải eager cho query đó; các thuộc tính không liệt kê được xử lý theo ngữ nghĩa fetch graph của JPA, tức được coi là lazy cho mục đích graph. Với graph kiểu LOAD, thuộc tính được liệt kê được tải eager còn thuộc tính không liệt kê giữ chiến lược fetch đã khai báo trên mapping.

EntityGraph mô tả yêu cầu tải dữ liệu cho query. Nó không bắt buộc provider phải tạo đúng một câu SQL JOIN duy nhất. Hãy đo số câu SQL và kiểm tra dữ liệu trả về trên phiên bản Hibernate và cơ sở dữ liệu thực tế.

**Khi nên chọn EntityGraph:** cần trả entity cùng một số quan hệ cụ thể, có thể tái sử dụng fetch plan, hoặc muốn giữ query chính dễ đọc mà vẫn chỉ định dữ liệu cần tải.

## 7. Cách 3: dùng JOIN FETCH khi cần điều khiển truy vấn trực tiếp

JPQL fetch join yêu cầu tải association cùng truy vấn chính:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    join fetch o.customer
    left join fetch o.lines line
    left join fetch line.product
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailByIdWithFetchJoin(
        @Param("id") Long id);
~~~

- join fetch yêu cầu có association tương ứng; nếu không có association ở phía được join, bản ghi gốc có thể bị loại.
- left join fetch giữ lại entity gốc ngay cả khi quan hệ tùy chọn hoặc collection không có phần tử.
- distinct giúp loại trùng entity gốc trong kết quả JPQL khi join với collection tạo ra nhiều hàng SQL cho cùng một đơn hàng.

Fetch join phù hợp khi query cần thể hiện rõ các quan hệ được tải và cấu trúc truy vấn không quá phức tạp. Nó cũng có thể hữu ích khi EntityGraph không diễn đạt đủ ý định truy vấn.

Cần chú ý rằng JOIN FETCH collection làm số hàng kết quả SQL tăng theo số phần tử collection. Nếu một đơn hàng có nhiều dòng, một entity đơn hàng sẽ xuất hiện trên nhiều hàng SQL trước khi Hibernate hợp nhất kết quả thành entity graph.

Không nên ghép nhiều collection to-many lớn trong cùng fetch join một cách tùy tiện. Số hàng có thể tăng theo tích số phần tử của các collection. Với Hibernate, fetch đồng thời nhiều bag collection còn có thể dẫn đến lỗi MultipleBagFetchException. Hãy dùng DTO, truy vấn riêng, batch fetching hoặc chiến lược tải khác phù hợp.

## 8. Phân trang và collection fetch

Phân trang là nơi cần chọn fetch plan cẩn thận nhất. Ví dụ sau có rủi ro:

~~~java
@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    order by o.createdAt desc
    """)
Page<PurchaseOrder> findAllWithLines(Pageable pageable);
~~~

Một đơn hàng có thể chiếm nhiều hàng SQL vì có nhiều OrderLine. Áp dụng LIMIT/OFFSET ở SQL trên kết quả join có thể không tương ứng với số đơn hàng mong muốn. Hibernate có thể phải xử lý phân trang trong bộ nhớ hoặc phát cảnh báo tùy phiên bản/cấu hình; điều này có thể tốn tài nguyên đáng kể.

Các hướng xử lý thường dùng:

### 8.1. Phân trang bằng DTO projection

Nếu màn hình danh sách chỉ cần trường tóm tắt, dùng Page<OrderSummary> như ví dụ ở phần DTO. Đây thường là cách đơn giản và hiệu quả nhất.

### 8.2. Phân trang ID trước, tải chi tiết sau

Nếu màn hình cần entity cùng collection, thực hiện hai truy vấn:

1. Truy vấn trang ID của entity gốc theo điều kiện và thứ tự mong muốn.
2. Dùng một truy vấn khác để tải entity và các quan hệ cần thiết theo danh sách ID đó.
3. Sắp xếp lại kết quả theo thứ tự ID ở trang đầu, vì IN (...) không đảm bảo giữ thứ tự đầu vào.

Ví dụ:

~~~java
@Query("""
    select o.id
    from PurchaseOrder o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findPageIds(
        @Param("status") OrderStatus status,
        Pageable pageable);

@Query("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.customer
    left join fetch o.lines line
    left join fetch line.product
    where o.id in :ids
    """)
List<PurchaseOrder> findDetailsByIds(
        @Param("ids") Collection<Long> ids);
~~~

Service gọi hai truy vấn trong cùng một read transaction nếu cần quan sát nhất quán theo ranh giới giao dịch:

~~~java
@Transactional(readOnly = true)
public Page<OrderDetailDto> findOrderPage(
        OrderStatus status,
        Pageable pageable) {

    Page<Long> idPage = repository.findPageIds(status, pageable);

    if (idPage.isEmpty()) {
        return new PageImpl<>(
                List.of(), pageable, idPage.getTotalElements());
    }

    Map<Long, PurchaseOrder> byId =
            repository.findDetailsByIds(idPage.getContent())
                    .stream()
                    .collect(Collectors.toMap(
                            PurchaseOrder::getId,
                            Function.identity()));

    List<OrderDetailDto> content = idPage.getContent().stream()
            .map(byId::get)
            .filter(Objects::nonNull)
            .map(orderMapper::toDetailDto)
            .toList();

    return new PageImpl<>(
            content, pageable, idPage.getTotalElements());
}
~~~

Ví dụ giả định Service có repository và orderMapper được inject. Trong ứng dụng thực tế, cần quyết định cách xử lý trường hợp một ID không còn được trả về ở truy vấn thứ hai do dữ liệu thay đổi đồng thời. Mức isolation và thời điểm đọc phụ thuộc cơ sở dữ liệu.

Truy vấn thứ nhất cung cấp tổng số bản ghi qua Page. Truy vấn thứ hai chỉ tải chi tiết cho các ID của trang. Nếu số ID lớn, chú ý giới hạn tham số IN của cơ sở dữ liệu và kích thước trang.

## 9. Phối hợp fetch plan với DTO và transaction boundary

Fetch plan cần được thực thi trong phạm vi persistence context phù hợp. Với Spring Data JPA, phương thức Service thường là nơi tốt để đặt transaction boundary cho use case đọc nhiều Repository hoặc ánh xạ entity sang DTO.

Ví dụ:

~~~java
@Service
@RequiredArgsConstructor
public class OrderQueryService {

    private final PurchaseOrderRepository repository;
    private final OrderMapper orderMapper;

    @Transactional(readOnly = true)
    public OrderDetailDto getDetail(Long id) {
        PurchaseOrder order = repository
                .findWithDetailsById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Không tìm thấy đơn hàng"));

        return orderMapper.toDetailDto(order);
    }
}
~~~

Trong phương thức này:

- Service xác định ranh giới giao dịch cho use case đọc.
- Repository tải entity và các quan hệ cần thiết theo EntityGraph.
- Mapper đọc dữ liệu khi persistence context còn hoạt động và tạo DTO.
- DTO được trả về thay vì entity có association lazy.

Nếu mapper truy cập một quan hệ lazy chưa được tải, Hibernate có thể phát sinh query bổ sung trong lúc transaction còn mở. Vì vậy, fetch plan cần bao gồm mọi quan hệ mà mapper thực sự sử dụng. Hãy kiểm tra SQL để xác nhận không có N+1.

Không nên dựa vào Open Session in View (OSIV) để vô tình tải dữ liệu khi template hoặc JSON serializer truy cập entity sau khi Service đã kết thúc. OSIV có thể giữ persistence context mở trong suốt request web tùy cấu hình, nhưng khi đó query có thể phát sinh ở tầng web và khó quan sát. Một thiết kế rõ ràng thường ánh xạ sang DTO bên trong Service transaction và cân nhắc tắt OSIV bằng cấu hình phù hợp với ứng dụng:

~~~properties
spring.jpa.open-in-view=false
~~~

Khi tắt OSIV, các lỗi truy cập lazy ngoài giao dịch sẽ dễ được phát hiện sớm hơn. Cần bảo đảm các Service đã tải đủ dữ liệu và trả DTO trước khi bật cấu hình này trong môi trường triển khai.

readOnly = true là gợi ý tối ưu cho transaction manager/provider, không phải cơ chế bảo mật cấm ghi. Với use case chỉ đọc, nó thể hiện ý định rõ ràng và có thể giúp Hibernate tối ưu dirty checking tùy cấu hình.

## 10. Các chiến lược bổ sung khi cần tải collection

Không phải mọi trường hợp đều phù hợp với một fetch join lớn. Một số chiến lược khác:

### 10.1. Batch fetching

Hibernate có thể gom việc tải nhiều association lazy thành các truy vấn theo lô. Có thể cấu hình mặc định:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Hoặc cấu hình cho một association:

~~~java
@OneToMany(mappedBy = "order")
@BatchSize(size = 32)
private List<OrderLine> lines;
~~~

Khi nhiều entity cùng có association chưa tải được truy cập, Hibernate có thể lấy dữ liệu cho một nhóm ID trong một truy vấn IN thay vì một truy vấn cho mỗi entity. Batch fetching giảm N+1 trong một số mẫu truy cập nhưng không thay thế việc thiết kế projection hoặc fetch plan theo màn hình. Kích thước batch cần được đo và điều chỉnh theo dữ liệu, driver và giới hạn tham số của cơ sở dữ liệu.

### 10.2. Subselect fetching

Hibernate hỗ trợ @Fetch(FetchMode.SUBSELECT) cho một số association collection. Khi collection của các entity trong một tập kết quả được truy cập, provider có thể dùng một truy vấn phụ để tải các collection đó. Đây là tính năng riêng của Hibernate, không phải annotation chuẩn JPA. Hãy đo truy vấn và kiểm tra tác động trên use case thực tế trước khi áp dụng.

### 10.3. Truy vấn riêng cho collection

Nếu màn hình có danh sách cha và một collection độc lập, đôi khi truy vấn danh sách cha và truy vấn collection theo các ID cha là dễ kiểm soát hơn. Sau đó nhóm dữ liệu theo parent ID trong Service. Cách này tránh nhân số hàng do join nhiều collection và có thể trả DTO rõ ràng.

## 11. Nhận diện và xử lý N+1 query

N+1 xảy ra khi ứng dụng tải một danh sách bằng một truy vấn, sau đó mỗi entity phát sinh thêm một truy vấn khi truy cập association lazy. Ví dụ:

~~~java
List<PurchaseOrder> orders = repository.findAll();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nếu customer chưa được tải, vòng lặp có thể phát sinh một truy vấn cho mỗi đơn hàng. Với N đơn hàng, tổng số truy vấn có thể gần 1 + N.

Các cách xử lý:

- Nếu chỉ cần tên khách hàng, dùng DTO projection và JOIN customer trong query.
- Nếu cần entity và quan hệ customer, dùng EntityGraph hoặc JOIN FETCH.
- Nếu truy cập nhiều association lazy theo lô, cân nhắc batch fetching.
- Nếu có collection lớn hoặc phân trang, tách truy vấn hoặc dùng DTO thay vì fetch join collection.

Không phải mọi truy vấn bổ sung đều là lỗi. Vấn đề là số truy vấn tăng theo số phần tử và chi phí thực tế. Bật log SQL hoặc thống kê Hibernate trong môi trường kiểm thử, đếm số truy vấn với bộ dữ liệu đủ lớn, rồi xác nhận số truy vấn không tăng tuyến tính ngoài dự kiến.

Ví dụ cấu hình log SQL khi phát triển:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

TRACE có thể ghi giá trị tham số nhạy cảm; chỉ bật trong môi trường phát triển/kiểm thử được kiểm soát và tắt khi không còn cần thiết.

## 12. Lỗi thường gặp

### 12.1. Đặt EAGER cho mọi quan hệ

Điều này khiến nhiều use case tải dữ liệu không cần thiết và không bảo đảm provider chỉ dùng một JOIN. Hãy chọn quan hệ theo query hoặc use case cụ thể.

### 12.2. Trả entity trực tiếp cho JSON serializer

Serializer có thể truy cập association lazy, gây N+1, vòng lặp tham chiếu hoặc LazyInitializationException. Hãy tạo DTO phù hợp với hợp đồng API.

### 12.3. Ánh xạ DTO sau khi transaction đã đóng

Mapper truy cập association lazy sau khi persistence context đóng sẽ gây LazyInitializationException. Hãy ánh xạ DTO trong Service transaction hoặc truy vấn thẳng DTO từ Repository.

### 12.4. Fetch join collection rồi phân trang trực tiếp

Join làm nhân số hàng SQL, khiến giới hạn trang không còn tương ứng đơn giản với số entity gốc. Dùng DTO projection hoặc phân trang ID trước rồi tải chi tiết sau.

### 12.5. Fetch nhiều collection lớn cùng lúc

Có thể tạo tích số hàng rất lớn và với Hibernate có thể gặp MultipleBagFetchException nếu nhiều bag được fetch đồng thời. Chia truy vấn, dùng batch fetching hoặc DTO theo cấu trúc màn hình.

### 12.6. Dùng EntityGraph nhưng không kiểm tra SQL

EntityGraph là yêu cầu fetch, không phải cam kết về một câu SQL cụ thể. Kiểm tra truy vấn thật, số hàng và lượng dữ liệu để chắc chắn nó giải quyết đúng vấn đề.

### 12.7. Dùng DTO projection cho luồng cần cập nhật entity

DTO không phải entity được quản lý. Thay đổi DTO không tự được dirty checking lưu xuống cơ sở dữ liệu. Với nghiệp vụ ghi, tải entity cần thiết trong transaction, áp dụng thay đổi rồi commit.

## 13. Quy trình chọn fetch plan

Có thể áp dụng quy trình sau cho từng use case:

1. **Liệt kê đầu ra:** xác định chính xác trường và quan hệ cần dùng.
2. **Xác định kiểu thao tác:** chỉ đọc, báo cáo hay cập nhật entity.
3. **Kiểm tra cardinality:** phân biệt to-one và to-many, ước lượng số phần tử.
4. **Chọn kỹ thuật:** DTO cho tập trường cố định; EntityGraph hoặc JOIN FETCH cho entity cùng quan hệ cần thiết; batch fetching hoặc truy vấn riêng cho collection phù hợp.
5. **Đặt transaction boundary:** giữ truy vấn và ánh xạ entity trong Service transaction khi cần persistence context.
6. **Đo SQL:** kiểm tra số truy vấn, cột, số hàng và thời gian thực thi.
7. **Kiểm thử dữ liệu lớn:** đặc biệt với phân trang, collection và truy cập đồng thời.
8. **Điều chỉnh theo bằng chứng:** chỉ mở rộng fetch plan khi có use case thực sự cần.

## 14. Checklist trước khi hoàn thành một màn hình

- [ ] Đã liệt kê đúng các trường màn hình cần hiển thị.
- [ ] Đã chọn DTO projection nếu chỉ cần dữ liệu đọc cố định.
- [ ] Nếu trả entity, đã chỉ định association cần tải bằng EntityGraph hoặc query phù hợp.
- [ ] Mapping không đặt EAGER tràn lan.
- [ ] Mapper chạy trong phạm vi persistence context phù hợp.
- [ ] API không vô tình serialize entity và collection lazy.
- [ ] Đã kiểm tra N+1 bằng SQL log hoặc Hibernate statistics.
- [ ] Không phân trang trực tiếp trên fetch join collection.
- [ ] Không fetch nhiều collection lớn trong một truy vấn.
- [ ] Có kiểm thử với số lượng dữ liệu gần thực tế.
- [ ] Đã đo hiệu năng thay vì giả định EntityGraph hoặc JOIN FETCH luôn nhanh hơn.

## 15. Kết luận

Chọn fetch plan bắt đầu từ dữ liệu mà từng màn hình hoặc use case thực sự cần. DTO projection phù hợp với danh sách và báo cáo có tập trường cố định; EntityGraph và JOIN FETCH phù hợp khi cần entity cùng các quan hệ cụ thể; batch fetching hoặc truy vấn riêng có thể hữu ích cho collection và dữ liệu lớn. Service transaction giữ việc đọc entity và ánh xạ DTO trong phạm vi persistence context rõ ràng. Kết hợp lựa chọn này với kiểm tra SQL, N+1 và phân trang sẽ giúp ứng dụng tải đúng dữ liệu với chi phí có thể kiểm soát.
