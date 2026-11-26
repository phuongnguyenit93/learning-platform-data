# Chọn projection và tránh tải dữ liệu ngầm không cần thiết

> Chương: **Tầng truy cập dữ liệu**

Trong module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, chúng ta học cách tổ chức phần mềm theo kiến trúc phân tầng. Bài này tập trung vào cách tầng truy cập dữ liệu lấy đúng phần thông tin mà một ca sử dụng cần: dùng projection cho truy vấn đọc phù hợp, xác định rõ quan hệ nào cần được tải và tránh để việc truy cập một thuộc tính vô tình kích hoạt nhiều truy vấn.

Mục tiêu không phải là luôn tải ít cột nhất bằng mọi giá. Mục tiêu là làm cho nhu cầu dữ liệu rõ ràng, kiểm soát được chi phí truy vấn và giữ tầng Application/Presentation không phụ thuộc vào cách ORM tải entity.

## 1. Vì sao cần quan tâm dữ liệu được tải?

Hãy xem một màn hình danh sách đơn hàng. Mỗi dòng chỉ hiển thị mã đơn, ngày tạo, tổng tiền và tên khách hàng. Nếu repository tải toàn bộ `Order` entity cùng mọi quan hệ, ứng dụng có thể đọc thêm địa chỉ giao hàng, lịch sử trạng thái, từng dòng hàng, sản phẩm và nhiều dữ liệu mà màn hình không sử dụng.

Việc tải dư thừa có thể gây ra:

- Truy vấn lấy nhiều cột và nhiều hàng hơn mức cần thiết, làm tăng I/O và lượng dữ liệu truyền giữa database với ứng dụng.
- ORM tạo thêm object và giữ chúng trong persistence context, làm tăng chi phí bộ nhớ và dirty checking.
- Quan hệ lazy được truy cập trong vòng lặp khiến mỗi đơn hàng phát sinh thêm truy vấn, tạo ra vấn đề N+1.
- Controller hoặc serializer vô tình chạm vào quan hệ sau khi service kết thúc, làm phát sinh truy vấn ở thời điểm khó quan sát hoặc gây lỗi khi persistence context đã đóng.
- Một truy vấn join nhiều collection tạo ra nhiều hàng lặp, làm phân trang và xử lý kết quả phức tạp.

Tầng truy cập dữ liệu nên cung cấp truy vấn phù hợp với mục đích: danh sách, báo cáo, màn hình chi tiết hoặc tải aggregate để thay đổi nghiệp vụ. Không phải mọi trường hợp đều cần trả về một entity đầy đủ.

## 2. Projection là gì?

**Projection** là cách truy vấn và biểu diễn một phần dữ liệu từ nguồn lưu trữ theo đúng những trường mà một tình huống sử dụng cần. Thay vì lấy cả entity `Order`, truy vấn có thể chỉ lấy `id`, `createdAt`, `total` và `customerName` để tạo một dòng tóm tắt.

Projection thường phù hợp với các truy vấn đọc như:

- Danh sách đơn hàng có phân trang.
- Bảng thống kê doanh thu theo ngày hoặc theo khách hàng.
- Danh sách sản phẩm chỉ hiển thị tên, giá và trạng thái bán.
- Báo cáo cần tổng hợp dữ liệu từ nhiều bảng.
- Màn hình tìm kiếm cần một tập trường nhỏ, ổn định.

Projection không phải là một cách thay thế entity trong mọi tình huống. Khi một ca sử dụng cần thay đổi trạng thái và bảo vệ bất biến, Application thường cần tải aggregate hoặc entity phù hợp để gọi hành vi Domain. Projection thường hữu ích nhất cho các đường đọc (read path).

## 3. Dùng interface projection với Spring Data JPA

Spring Data JPA hỗ trợ interface projection. Ta định nghĩa các getter tương ứng với dữ liệu cần trả về:

```java
public interface OrderSummaryView {
    UUID getId();
    Instant getCreatedAt();
    BigDecimal getTotal();
    String getCustomerName();
}
```

Repository có thể dùng JPQL để chọn chính xác các trường và đặt alias khớp với tên thuộc tính projection:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {
    @Query("""
        select o.id as id,
               o.createdAt as createdAt,
               o.total as total,
               c.name as customerName
        from Order o
        join o.customer c
        where c.id = :customerId
        order by o.createdAt desc
        """)
    Page<OrderSummaryView> findSummariesByCustomerId(
        UUID customerId, Pageable pageable);
}
```

Application có thể trả projection hoặc ánh xạ nó thành response DTO tùy ranh giới của dự án:

```java
@Service
public class ListCustomerOrdersService {
    private final OrderRepository orders;

    public ListCustomerOrdersService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public Page<OrderSummaryView> execute(UUID customerId, Pageable pageable) {
        return orders.findSummariesByCustomerId(customerId, pageable);
    }
}
```

Trong ví dụ này, truy vấn chỉ chọn bốn giá trị cần cho danh sách. Không cần tải `Order` cùng collection `lines` hoặc toàn bộ `Customer` chỉ để lấy tên. Alias trong JPQL giúp Spring Data ánh xạ kết quả vào getter của interface projection.

Interface projection dạng đóng (closed projection) là lựa chọn rõ ràng khi các getter tương ứng với thuộc tính đã biết. Nếu dùng biểu thức SpEL hoặc nested projection, cách Spring Data lấy dữ liệu có thể phức tạp hơn; nested projection có thể khiến cả thuộc tính liên quan được materialize. Hãy kiểm tra SQL thực tế thay vì giả định mọi interface projection đều chỉ lấy đúng một cột cho mỗi getter.

## 4. Dùng DTO projection khi muốn kiểu kết quả tường minh

Với DTO projection, truy vấn tạo trực tiếp một đối tượng chỉ chứa dữ liệu cần dùng. Java record là lựa chọn gọn cho một read model bất biến:

```java
public record OrderSummaryDto(
    UUID id,
    Instant createdAt,
    BigDecimal total,
    String customerName
) {}
```

JPQL có thể dùng constructor expression để tạo record:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {
    @Query("""
        select new com.example.shop.orders.OrderSummaryDto(
            o.id, o.createdAt, o.total, c.name)
        from Order o
        join o.customer c
        where c.id = :customerId
        order by o.createdAt desc
        """)
    Page<OrderSummaryDto> findSummaryDtosByCustomerId(
        UUID customerId, Pageable pageable);
}
```

Constructor expression cần tên lớp đầy đủ và thứ tự, kiểu tham số phải khớp constructor. Nếu dùng Spring Data JPA với class-based projection mà không viết `@Query`, cần khai báo constructor phù hợp để framework xác định các tham số cần chọn.

DTO projection phù hợp khi muốn hợp đồng đầu ra độc lập với entity, muốn kiểm soát rõ kiểu dữ liệu trả về hoặc cần tổng hợp trường từ nhiều entity. Nó cũng tránh việc tầng trên vô tình gọi getter của entity và kích hoạt lazy loading.

Interface projection và DTO projection đều có ích. Chọn interface khi cấu trúc getter đơn giản và Spring Data có thể ánh xạ trực tiếp; chọn DTO/record khi cần một kiểu kết quả rõ ràng, dễ truyền qua ranh giới Application hoặc API. Với truy vấn phức tạp, native SQL hoặc báo cáo tổng hợp, có thể cần mapping riêng phù hợp với công cụ đang dùng.

## 5. Khi nào nên tải entity thay vì projection?

Một projection chỉ có những trường được chọn. Nó thường không mang đầy đủ hành vi và trạng thái cần thiết để thực hiện thay đổi nghiệp vụ. Ví dụ, nếu ca sử dụng cần hủy đơn hàng, tải `OrderSummaryDto` chỉ có mã và tổng tiền là chưa đủ để kiểm tra trạng thái hiện tại, lý do hủy, quyền hủy hoặc cập nhật các bất biến liên quan.

Trong trường hợp thay đổi nghiệp vụ, hãy tải entity hoặc aggregate qua repository:

```java
@Transactional
public void cancelOrder(UUID orderId, String reason) {
    Order order = orders.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    order.cancel(reason);
}
```

Ở đây `Order.cancel(...)` có thể kiểm tra trạng thái có cho phép hủy không và ghi nhận lý do. Persistence provider có thể tự đồng bộ entity đang được quản lý khi giao dịch flush. Nếu dùng cơ chế lưu trữ khác, repository adapter sẽ thực hiện cập nhật tương ứng.

Không nên lấy projection một phần rồi chuyển nó thành entity với các trường còn lại mặc định `null` để gọi `save`. Cách này có thể làm mất dữ liệu, bỏ qua bất biến hoặc tạo một trạng thái không hợp lệ. Projection cho đọc và entity/aggregate cho thay đổi là một quy ước hữu ích, dù không phải quy tắc tuyệt đối cho mọi hệ thống.

## 6. Quan hệ lazy và tải dữ liệu ngầm

ORM như Hibernate có thể trì hoãn việc tải quan hệ cho tới khi ứng dụng truy cập thuộc tính đó. Ví dụ:

```java
@Entity
public class Order {
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
```

Khi repository tải `Order`, Hibernate có thể chưa tải `customer` hoặc `lines`. Nếu code gọi `order.getCustomer().getName()` hoặc duyệt `order.getLines()`, ORM có thể phát sinh truy vấn bổ sung. Đây là hành vi lazy loading; nó tiện khi chỉ một số luồng cần quan hệ, nhưng có thể gây tải dữ liệu ngầm nếu người viết không nhận ra thời điểm truy cập.

Trong JPA, mặc định của quan hệ `@ManyToOne` và `@OneToOne` là `EAGER`, còn `@OneToMany` và `@ManyToMany` là `LAZY`. Với `EAGER`, provider phải cung cấp quan hệ khi entity được truy cập, nhưng điều đó không bảo đảm nó được tải bằng một câu SQL join duy nhất; provider có thể phát sinh truy vấn phụ. Vì vậy, khai báo EAGER rộng khắp không phải cách đáng tin cậy để giải quyết N+1.

## 7. Nhận biết và tránh N+1

Vấn đề **N+1** xảy ra khi một truy vấn ban đầu tải danh sách N đối tượng, sau đó việc truy cập một quan hệ trên từng đối tượng lại tạo thêm khoảng N truy vấn. Ví dụ:

```java
List<Order> orders = orderRepository.findRecentOrders();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Nếu `customer` chưa được tải, vòng lặp có thể chạy một truy vấn lấy danh sách đơn và thêm một truy vấn cho mỗi khách hàng. Với 100 đơn hàng, số truy vấn có thể tăng lên 101. Con số thực tế phụ thuộc cache, quan hệ và cách ORM tối ưu, nhưng mẫu truy cập này là tín hiệu cần kiểm tra.

Có một số cách xử lý, tùy mục tiêu truy vấn:

1. Dùng projection nếu chỉ cần một vài trường như mã đơn và tên khách hàng.
2. Dùng fetch join hoặc entity graph nếu cần entity cùng một số quan hệ cho một thao tác cụ thể.
3. Dùng batch fetching khi cần giữ mô hình entity nhưng muốn gom các lần tải lazy thành nhóm; đây là tối ưu theo cấu hình provider, không thay thế việc chọn fetch plan đúng.
4. Tránh duyệt quan hệ không cần thiết trong mapper, serializer hoặc vòng lặp xử lý danh sách.

## 8. Xác định fetch plan tường minh

Khi một use case cần entity cùng các quan hệ cụ thể, hãy mô tả rõ fetch plan cho truy vấn đó. Một lựa chọn là JPQL fetch join:

```java
@Query("""
    select distinct o
    from Order o
    join fetch o.customer
    where o.id = :orderId
    """)
Optional<Order> findWithCustomerById(UUID orderId);
```

Truy vấn này yêu cầu tải `customer` cùng `Order`. Từ khóa `distinct` giúp loại kết quả gốc trùng lặp ở mức entity khi join tạo ra nhiều hàng cho cùng đơn; cách xử lý chính xác còn phụ thuộc provider và loại quan hệ được join.

Spring Data JPA cũng hỗ trợ `@EntityGraph`:

```java
@EntityGraph(attributePaths = {"customer", "lines", "lines.product"})
Optional<Order> findDetailsById(UUID id);
```

Entity graph mô tả những thuộc tính cần được tải cho truy vấn này mà không buộc phải thay đổi fetch type mặc định trên entity. Provider quyết định chiến lược SQL để đáp ứng graph; hãy kiểm tra truy vấn được tạo và số hàng trả về.

Không nên thêm fetch join mọi quan hệ vào mọi truy vấn. Join nhiều collection có thể nhân số hàng theo tổ hợp phần tử, làm dữ liệu lớn lên nhanh và gây khó khăn cho phân trang. Đặc biệt, phân trang trên truy vấn fetch join collection có thể không hoạt động như mong đợi hoặc buộc provider tải nhiều hàng rồi phân trang trong bộ nhớ. Với danh sách phân trang, projection thường là lựa chọn gọn; nếu cần entity và collection, cân nhắc truy vấn hai bước: lấy trang ID trước, sau đó tải chi tiết cho các ID đó.

## 9. Tránh để Presentation vô tình kích hoạt truy vấn

Một lỗi thường gặp là trả entity JPA trực tiếp từ controller:

```java
@GetMapping("/orders/{id}")
Order get(@PathVariable UUID id) {
    return orderRepository.findById(id).orElseThrow();
}
```

JSON serializer có thể gọi getter của entity và chạm vào quan hệ lazy. Khi Open Session in View được bật, các truy vấn bổ sung có thể xảy ra trong lúc serialize response, bên ngoài phần code mà nhóm tưởng là đã hoàn tất việc truy cập dữ liệu. Khi persistence context đã đóng, truy cập quan hệ lazy chưa được tải có thể gây `LazyInitializationException`.

Nên ánh xạ sang response DTO bên trong ranh giới service khi dữ liệu cần thiết còn được tải hợp lệ:

```java
@Transactional(readOnly = true)
public OrderDetailResponse getOrder(UUID id) {
    Order order = orders.findDetailsById(id)
        .orElseThrow(OrderNotFoundException::new);

    return new OrderDetailResponse(
        order.getId(),
        order.getCustomer().getName(),
        order.getLines().stream()
            .map(line -> new OrderLineResponse(
                line.getProduct().getName(), line.getQuantity()))
            .toList()
    );
}
```

Ở đây repository dùng fetch plan phù hợp với màn hình chi tiết, còn service chuyển entity thành DTO trong lúc transaction và persistence context còn hoạt động. Controller chỉ nhận DTO và không cần biết quan hệ JPA.

Một số ứng dụng cấu hình `spring.jpa.open-in-view=false` để tránh truy vấn persistence bị kích hoạt ngầm trong tầng web. Khi tắt, các quan hệ cần thiết phải được tải và ánh xạ trong ranh giới giao dịch thích hợp; không nên chỉ tắt cấu hình rồi để controller tiếp tục truy cập lazy association.

## 10. Phân trang, sắp xếp và kiểm tra truy vấn

Projection thường rất hữu ích cho danh sách lớn vì có thể chọn một tập cột nhỏ và kết hợp với `Pageable`:

```java
Page<OrderSummaryDto> page = orderRepository
    .findSummaryDtosByCustomerId(customerId, PageRequest.of(
        0, 20, Sort.by(Sort.Direction.DESC, "createdAt")));
```

Với `Page<T>`, Spring Data có thể thực hiện thêm count query để tính tổng số phần tử và số trang. Nếu chỉ cần biết còn trang tiếp theo hay không, `Slice<T>` có thể tránh yêu cầu tổng số bản ghi. Truy vấn count cần được xem xét riêng khi JPQL có join hoặc điều kiện phức tạp; có thể khai báo `countQuery` tường minh nếu cần.

Khi dùng projection, hãy kiểm tra các điểm sau:

- SQL chỉ chọn những cột cần thiết, không âm thầm lấy toàn bộ entity.
- Join không tạo ra số hàng lớn bất thường.
- Điều kiện lọc và sắp xếp có index phù hợp với khối lượng dữ liệu.
- Truy vấn count không tốn kém không cần thiết.
- Kết quả phân trang ổn định khi có nhiều bản ghi cùng giá trị sắp xếp; có thể thêm khóa duy nhất làm tiêu chí phụ.

Không nên suy luận hiệu năng chỉ từ chữ `projection`, `LAZY` hay `fetch join`. Bật log SQL trong môi trường phát triển, xem execution plan của database và đo số truy vấn/độ trễ với dữ liệu gần thực tế. Kiểm tra query count giúp phát hiện N+1 và truy vấn bị lặp trong mapper hoặc serializer.

## 11. Chọn chiến lược theo từng loại use case

| Use case | Chiến lược thường phù hợp | Lý do |
|---|---|---|
| Danh sách đơn hàng phân trang | Interface hoặc DTO projection | Chỉ cần một số trường để hiển thị |
| Báo cáo tổng doanh thu | Projection có aggregate như `SUM`, `COUNT` | Database có thể tổng hợp mà không tải từng entity |
| Màn hình chi tiết đơn | Entity graph hoặc fetch plan rõ ràng, sau đó ánh xạ DTO | Cần một số quan hệ cụ thể |
| Hủy đơn hoặc thay đổi trạng thái | Tải aggregate/entity để gọi hành vi Domain | Cần kiểm tra và bảo vệ bất biến |
| Tìm kiếm tự do nhiều tiêu chí | Projection hoặc read model chuyên biệt | Có thể tối ưu riêng cho truy vấn đọc |

Một hệ thống có thể sử dụng nhiều chiến lược cùng lúc. Cùng một bảng `orders` có thể được truy vấn bằng projection cho trang danh sách, entity graph cho màn hình chi tiết và aggregate đầy đủ cho thao tác hủy đơn. Chọn theo mục đích của từng truy vấn giúp tránh một repository method duy nhất phải phục vụ mọi tình huống.

## 12. Checklist khi thiết kế truy vấn

Trước khi viết repository method, hãy trả lời:

1. Use case cần hiển thị hoặc xử lý những trường nào?
2. Nó chỉ đọc dữ liệu hay cần thay đổi trạng thái và bảo vệ bất biến?
3. Có cần entity đầy đủ hay một projection/DTO là đủ?
4. Quan hệ nào phải được tải ngay trong truy vấn? Quan hệ nào có thể không cần truy cập?
5. Có vòng lặp hoặc serializer nào có thể kích hoạt lazy loading và N+1 không?
6. Truy vấn có phân trang, count, sắp xếp và join collection không?
7. SQL thực tế và số truy vấn đã được kiểm tra với dữ liệu có quy mô phù hợp chưa?

Nếu danh sách chỉ cần bốn trường, hãy bắt đầu bằng projection bốn trường. Nếu một thao tác cần aggregate và hành vi, hãy tải entity cùng fetch plan phù hợp. Sau đó kiểm tra SQL thực tế để chắc rằng cách chọn dữ liệu đáp ứng cả tính đúng đắn lẫn hiệu năng.

## Ghi nhớ

- Projection lấy một phần dữ liệu theo nhu cầu của truy vấn, thường phù hợp với danh sách, báo cáo và read model.
- Interface projection và DTO/record projection giúp giới hạn dữ liệu trả về; cần kiểm tra SQL, đặc biệt với nested projection.
- Khi cần thay đổi nghiệp vụ và bảo vệ bất biến, hãy tải entity/aggregate phù hợp thay vì cập nhật từ projection một phần.
- Lazy loading có thể phát sinh truy vấn khi getter được gọi; truy cập quan hệ trong vòng lặp dễ tạo N+1.
- Fetch join và `@EntityGraph` giúp xác định fetch plan, nhưng join nhiều collection có thể làm phình số hàng và gây vấn đề với phân trang.
- Ánh xạ entity thành DTO trong ranh giới service giúp Presentation không kích hoạt truy vấn ngầm khi serialize.
- Đo SQL, số truy vấn và execution plan để xác nhận hiệu quả; annotation hoặc tên kỹ thuật tự nó không bảo đảm truy vấn tốt.
