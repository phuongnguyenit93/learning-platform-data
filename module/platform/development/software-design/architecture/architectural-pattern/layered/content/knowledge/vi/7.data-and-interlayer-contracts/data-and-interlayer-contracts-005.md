# Ngăn trả entity ORM và trạng thái lazy loading trực tiếp ra giao diện

Trong module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** (Học tổ chức phần mềm theo kiến trúc phân tầng), bài học này tập trung vào hợp đồng dữ liệu giữa tầng lưu trữ và tầng trình bày. Ta dùng API tra cứu đơn hàng để tìm hiểu vì sao không nên trả trực tiếp entity ORM ra JSON, lazy loading có thể gây lỗi hoặc truy vấn ngoài dự kiến như thế nào, và cách thiết kế DTO phù hợp.

Entity ORM mô tả cách ứng dụng lưu và liên kết dữ liệu. Response DTO mô tả dữ liệu mà client được phép nhận. Hai mô hình có thể có một số trường giống nhau, nhưng phục vụ mục đích khác nhau. Khi dùng entity làm response, cấu trúc database vô tình trở thành hợp đồng API; thay đổi quan hệ hoặc cách tải dữ liệu có thể làm endpoint thay đổi hành vi.

## 1. Entity ORM và DTO có trách nhiệm khác nhau

ORM (Object-Relational Mapping) ánh xạ đối tượng trong Java với bảng và quan hệ trong cơ sở dữ liệu. Với JPA/Hibernate, một entity có thể chứa khóa chính, quan hệ đến entity khác, trạng thái quản lý bởi persistence context và các thuộc tính được tải khi cần.

DTO (Data Transfer Object) là kiểu dữ liệu dùng để trao đổi qua một ranh giới. Trong bài này, response DTO biểu diễn dữ liệu trả về client qua HTTP. Nó chỉ nên chứa thông tin cần thiết cho use case và hợp đồng API.

| Tiêu chí | Entity ORM | Response DTO |
|---|---|---|
| Mục đích | Biểu diễn dữ liệu được ORM quản lý và lưu trữ | Biểu diễn dữ liệu được phép trả cho client |
| Quan hệ | Có thể chứa association đến entity khác | Thường chứa giá trị đơn giản, danh sách DTO hoặc ID cần thiết |
| Vòng đời | Có thể gắn với persistence context và transaction | Độc lập với session ORM sau khi được tạo |
| Cấu trúc | Phản ánh mô hình lưu trữ và quan hệ | Phản ánh nhu cầu của endpoint |
| Thay đổi | Có thể thay đổi khi schema hoặc mapping thay đổi | Nên thay đổi theo version và nhu cầu của API |
| Dữ liệu | Có thể chứa thông tin nội bộ và thuộc tính phục vụ persistence | Chỉ chứa trường được chủ động công bố |

Ví dụ, entity `OrderEntity` có thể chứa quan hệ đến `CustomerEntity`, `OrderLineEntity`, địa chỉ giao hàng và dữ liệu nội bộ phục vụ xử lý. Trang danh sách đơn hàng có thể chỉ cần mã đơn, ngày tạo, trạng thái và tổng tiền. Trả toàn bộ entity cho trang danh sách vừa thừa dữ liệu vừa khiến endpoint phụ thuộc vào quan hệ ORM.

DTO cũng không nhất thiết là một kiểu dùng chung cho mọi tầng. Request DTO thuộc hợp đồng đầu vào của API; command/input model thuộc hợp đồng của use case; entity thuộc persistence; response DTO thuộc hợp đồng đầu ra. Một ứng dụng nhỏ có thể tái sử dụng kiểu khi mục đích thực sự trùng nhau, nhưng không nên mặc định một lớp phải đại diện cho tất cả.

## 2. Vì sao trả entity ORM trực tiếp ra giao diện dễ gây lỗi?

### 2.1. Lộ cấu trúc lưu trữ và dữ liệu không cần thiết

Giả sử controller trả entity:

```java
@GetMapping("/{id}")
public OrderEntity getOrder(@PathVariable UUID id) {
    return orderRepository.findById(id).orElseThrow();
}
```

Jackson thường dùng getter để tuần tự hóa đối tượng thành JSON. Nếu entity có các trường như `internalNote`, `paymentProviderPayload`, `createdBy` hoặc quan hệ tới khách hàng, các trường đó có thể bị công bố ngoài ý muốn nếu không có cấu hình giới hạn.

Điều này tạo ra một số rủi ro:

- Client nhận thông tin nội bộ mà endpoint không có chủ đích cung cấp.
- Thay đổi quan hệ JPA có thể làm cấu trúc JSON thay đổi.
- Client phụ thuộc vào tên trường và cấu trúc entity, khiến việc refactor persistence khó hơn.
- Một endpoint đọc có thể vô tình công bố thông tin cá nhân hoặc dữ liệu nhạy cảm.
- Khi client gửi lại một entity đã chỉnh sửa, server có thể vô tình cho phép cập nhật các trường mà người dùng không được quyền sửa.

Response DTO buộc nhóm phát triển lựa chọn rõ ràng trường nào được công bố. Request DTO riêng cũng ngăn việc bind trực tiếp JSON vào entity và giảm nguy cơ mass assignment.

### 2.2. Lazy loading có thể phát sinh truy vấn khi serialize

Lazy loading là cơ chế trì hoãn tải association cho đến khi ứng dụng thực sự truy cập association đó. Ví dụ, khi tải một đơn hàng, Hibernate có thể chưa tải danh sách dòng hàng hoặc khách hàng liên quan. Entity chứa proxy hoặc collection wrapper đại diện cho dữ liệu chưa được tải.

Một mapping đơn giản có thể như sau:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    private BigDecimal total;
}
```

Khi controller trả `OrderEntity`, quá trình serialize có thể gọi `getCustomer()`, `getLines()` và các getter liên quan. Nếu persistence context vẫn mở, Hibernate có thể phát truy vấn để tải association. Nếu persistence context đã đóng, truy cập association chưa được tải có thể gây `LazyInitializationException`.

Vì vậy, một endpoint có thể hoạt động trong môi trường phát triển nhưng lỗi khi transaction kết thúc sớm hơn quá trình serialize, hoặc hoạt động nhưng phát nhiều truy vấn ngoài dự kiến khi session vẫn mở.

### 2.3. Vòng tham chiếu giữa các entity

Quan hệ hai chiều thường tạo chu trình:

- `OrderEntity` có danh sách `OrderLineEntity`.
- Mỗi `OrderLineEntity` lại có thuộc tính `order` trỏ về `OrderEntity`.

Khi Jackson serialize đơn hàng, nó có thể đi từ đơn hàng sang dòng hàng rồi quay lại đơn hàng, tiếp tục lặp. Kết quả có thể là lỗi phát hiện vòng lặp, JSON quá sâu hoặc payload rất lớn.

Các annotation như `@JsonManagedReference`, `@JsonBackReference`, `@JsonIgnore` có thể thay đổi hành vi serialize, nhưng chúng không giải quyết ranh giới kiến trúc giữa entity và API. Chúng cũng không ngăn mọi truy vấn lazy loading hoặc loại bỏ sự phụ thuộc của hợp đồng API vào cấu trúc entity.

### 2.4. N+1 query và hiệu năng khó dự đoán

Giả sử endpoint trả 50 đơn hàng, mỗi đơn có một khách hàng lazy. Khi serializer truy cập tên khách hàng của từng đơn, ORM có thể chạy một truy vấn để lấy danh sách đơn và thêm nhiều truy vấn để lấy từng khách hàng. Đây là dạng vấn đề N+1 query.

Tình hình có thể phức tạp hơn khi mỗi đơn có danh sách dòng hàng và mỗi dòng hàng có sản phẩm. Một thao tác tưởng như chỉ trả JSON có thể tạo ra hàng chục hoặc hàng trăm truy vấn.

### 2.5. API phụ thuộc vào trạng thái session ORM

Nếu endpoint chỉ hoạt động khi session ORM còn mở trong lúc Jackson serialize, hợp đồng API đang phụ thuộc vào vòng đời persistence context. Điều này làm cho việc thay đổi cấu hình transaction, chuyển sang xử lý bất đồng bộ hoặc thay đổi cách triển khai web có thể làm endpoint hỏng.

API nên trả dữ liệu đã được chuẩn bị có chủ đích trước khi rời khỏi ranh giới ứng dụng. Client không nên phụ thuộc vào proxy, session hay cách ORM tải association.

## 3. Lazy loading hoạt động như thế nào?

Với JPA, fetch type quy định association được tải sớm hay trì hoãn:

- `FetchType.LAZY`: association được tải khi được truy cập, tùy khả năng và cách triển khai của provider.
- `FetchType.EAGER`: provider phải cung cấp association theo yêu cầu của mapping, nhưng không có nghĩa mọi trường hợp đều chỉ dùng một câu SQL.

Mặc định của JPA thường là `EAGER` cho `@ManyToOne` và `@OneToOne`, trong khi `@OneToMany` và `@ManyToMany` mặc định là `LAZY`. Nên khai báo fetch behavior có chủ đích cho các quan hệ, đặc biệt khi ứng dụng dùng Hibernate. Với quan hệ to-one, Hibernate có thể dùng proxy để hỗ trợ lazy loading; cách thực hiện cụ thể còn phụ thuộc mapping và cấu hình bytecode enhancement.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private CustomerEntity customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLineEntity> lines;
```

Khi chạy:

```java
OrderEntity order = orderRepository.findById(id).orElseThrow();
```

ORM có thể chỉ tải bản ghi đơn hàng. Khi truy cập:

```java
String customerName = order.getCustomer().getDisplayName();
int lineCount = order.getLines().size();
```

Hibernate có thể phát thêm truy vấn để tải khách hàng và các dòng hàng. Nếu các truy vấn này xảy ra trong transaction và được dự kiến trước, hành vi đó có thể hợp lệ. Vấn đề xuất hiện khi việc truy cập dữ liệu bị kích hoạt ngầm trong giai đoạn serialize hoặc lặp lại trên nhiều bản ghi.

Không nên giải quyết mọi vấn đề bằng cách đổi tất cả quan hệ thành `EAGER`. Điều đó có thể tải quá nhiều dữ liệu ở những use case không cần chúng, tạo join phức tạp hoặc vẫn dẫn đến nhiều truy vấn tùy cách ORM thực thi. Fetch plan nên được quyết định theo từng use case.

## 4. Tạo response DTO trước khi rời khỏi ranh giới ứng dụng

Một cách phổ biến là để application service truy vấn dữ liệu cần thiết, ánh xạ sang DTO khi persistence context còn sẵn sàng, rồi trả DTO cho controller.

### Response DTO

```java
public record OrderDetailResponse(
    UUID id,
    String status,
    String customerName,
    BigDecimal total,
    List<OrderLineResponse> lines
) {}

public record OrderLineResponse(
    UUID productId,
    String productName,
    int quantity,
    BigDecimal unitPrice,
    BigDecimal subtotal
) {}
```

DTO không chứa `CustomerEntity`, `OrderLineEntity` hoặc proxy Hibernate. Nó chứa các giá trị mà giao diện cần.

### Truy vấn rõ ràng dữ liệu cần tải

Có thể dùng `@EntityGraph` để chỉ định association cần tải cho một use case:

```java
public interface SpringDataOrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    @EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
    })
    @Query("select distinct o from OrderEntity o where o.id = :id")
    Optional<OrderEntity> findDetailById(@Param("id") UUID id);
}
```

Truy vấn này yêu cầu dữ liệu khách hàng, các dòng hàng và sản phẩm của từng dòng hàng được tải theo fetch plan cho trang chi tiết. Cách provider tạo SQL có thể khác nhau; cần kiểm tra truy vấn thực tế khi tối ưu.

### Ánh xạ trong application service

```java
@Service
@RequiredArgsConstructor
public class GetOrderDetailService {
    private final SpringDataOrderRepository orderRepository;

    @Transactional(readOnly = true)
    public OrderDetailResponse handle(UUID orderId) {
        var order = orderRepository.findDetailById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

        var lines = order.getLines().stream()
            .map(line -> new OrderLineResponse(
                line.getProduct().getId(),
                line.getProduct().getName(),
                line.getQuantity(),
                line.getUnitPrice(),
                line.getSubtotal()
            ))
            .toList();

        return new OrderDetailResponse(
            order.getId(),
            order.getStatus().name(),
            order.getCustomer().getDisplayName(),
            order.getTotal(),
            lines
        );
    }
}
```

Controller nhận một DTO đã hoàn chỉnh:

```java
@RestController
@RequestMapping("/api/orders")
@RequiredArgsConstructor
public class OrderQueryController {
    private final GetOrderDetailService getOrderDetail;

    @GetMapping("/{id}")
    public OrderDetailResponse get(@PathVariable UUID id) {
        return getOrderDetail.handle(id);
    }
}
```

Sau khi service trả về, response không còn phụ thuộc vào entity hoặc session ORM. Jackson chỉ tuần tự hóa các trường DTO. `@Transactional(readOnly = true)` thể hiện đây là use case đọc; nó không tự bảo đảm association đã được tải. Fetch plan và cách ánh xạ vẫn phải rõ ràng.

Các kiểu entity và repository trong ví dụ là minh họa. Tên trường, cách ánh xạ và transaction manager sẽ phụ thuộc cấu trúc ứng dụng thực tế.

## 5. Dùng projection cho màn hình danh sách

Trang danh sách thường chỉ cần một phần nhỏ dữ liệu. Không nhất thiết phải tải toàn bộ entity và các association rồi mới bỏ phần lớn trường khi tạo DTO.

Spring Data JPA hỗ trợ projection để truy vấn đúng các cột cần thiết:

```java
public interface OrderSummaryView {
    UUID getId();
    OrderStatus getStatus();
    String getCustomerName();
    BigDecimal getTotal();
}
```

```java
public interface SpringDataOrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    @Query("""
        select o.id as id,
               o.status as status,
               c.displayName as customerName,
               o.total as total
        from OrderEntity o
        join o.customer c
        where c.id = :customerId
        order by o.createdAt desc
        """)
    Page<OrderSummaryView> findSummaries(
        @Param("customerId") UUID customerId,
        Pageable pageable
    );
}
```

Application có thể chuyển projection sang response DTO ổn định:

```java
public record OrderSummaryResponse(
    UUID id,
    String status,
    String customerName,
    BigDecimal total
) {}
```

```java
@Transactional(readOnly = true)
public Page<OrderSummaryResponse> listOrders(
        UUID customerId, Pageable pageable) {
    return repository.findSummaries(customerId, pageable)
        .map(row -> new OrderSummaryResponse(
            row.getId(),
            row.getStatus().name(),
            row.getCustomerName(),
            row.getTotal()
        ));
}
```

Projection phù hợp với truy vấn đọc cần ít trường, đặc biệt với danh sách phân trang. Nó giúp tránh tải cả object graph và giảm khả năng kích hoạt lazy loading khi serialize. Nếu API cần dữ liệu tổng hợp hoặc phép tính phức tạp, có thể dùng JPQL constructor projection, native query hoặc read model riêng.

Khi dùng phân trang, cần chú ý truy vấn fetch join collection. Kết quả join có thể nhân số dòng, làm phân trang không chính xác hoặc buộc ORM xử lý phân trang trong bộ nhớ. Với trang danh sách, projection hoặc truy vấn hai bước thường dễ kiểm soát hơn.

## 6. Vì sao không nên bật EAGER hoặc Open Session in View để che vấn đề?

### Không đổi mọi quan hệ thành EAGER

Nếu mọi association đều EAGER, mỗi use case có thể tải dữ liệu mà nó không cần. Điều này làm tăng chi phí truy vấn, bộ nhớ và độ phức tạp của SQL. Một endpoint chỉ cần mã đơn có thể kéo theo khách hàng, dòng hàng, sản phẩm và địa chỉ.

Hãy chọn dữ liệu theo nhu cầu use case bằng entity graph, fetch join, projection hoặc truy vấn riêng. EAGER không phải là giải pháp chung cho lỗi lazy loading.

### Hiểu đúng Open Session in View (OSIV)

Trong ứng dụng web, Open Session in View giữ persistence context mở xuyên suốt quá trình xử lý request, có thể bao gồm giai đoạn render hoặc serialize response. Điều này có thể khiến một số association lazy tiếp tục tải được sau khi application service kết thúc transaction.

Tuy nhiên, nó cũng làm truy vấn có thể phát sinh ở giai đoạn trình bày. Controller hoặc serializer không nhìn thấy rõ lúc nào database bị truy cập; N+1 query có thể khó phát hiện. Việc session mở lâu hơn cũng làm ranh giới transaction và thời điểm tải dữ liệu khó dự đoán.

Có thể tắt OSIV trong Spring Boot bằng cấu hình:

```properties
spring.jpa.open-in-view=false
```

Khi tắt, ứng dụng cần bảo đảm application service tải đủ dữ liệu và tạo DTO trong ranh giới transaction phù hợp. Đây là cách làm lộ rõ những nơi đang phụ thuộc ngầm vào lazy loading, giúp thiết kế fetch plan có chủ đích hơn. Cấu hình cụ thể nên được xác minh theo phiên bản Spring Boot và cách triển khai ứng dụng.

### Không dựa vào Hibernate.initialize() cho mọi trường hợp

`Hibernate.initialize(collection)` có thể tải một collection khi session còn mở, nhưng gọi nó cho từng association không thay thế được thiết kế truy vấn. Nếu lặp qua nhiều đơn hàng và initialize từng collection, vẫn có thể tạo N+1 query. Hãy ưu tiên truy vấn mô tả rõ dữ liệu cần dùng.

## 7. Giữ hợp đồng API độc lập với entity

DTO giúp API có cấu trúc phù hợp với client và ít bị ảnh hưởng bởi thay đổi lưu trữ.

Ví dụ entity có thể lưu `firstName` và `lastName`, nhưng API chỉ cần `customerDisplayName`. Entity có thể lưu enum `OrderStatus`, trong khi API công bố mã trạng thái ổn định và tài liệu hóa. Một API công khai có thể cần trường `createdAt` theo ISO 8601, dù entity lưu thời gian theo kiểu khác hoặc có thêm cột phục vụ auditing.

Một số nguyên tắc khi thiết kế DTO:

- Chỉ trả trường mà client cần và được phép xem.
- Không đưa entity hoặc collection proxy vào DTO.
- Không trả object graph sâu tùy theo quan hệ ORM.
- Dùng kiểu đơn giản, enum hoặc kiểu dữ liệu công khai có ý nghĩa rõ ràng.
- Đặt tên theo ngôn ngữ của API thay vì tên cột hoặc tên association trong database.
- Xác định rõ nullability, định dạng thời gian, đơn vị tiền tệ và ý nghĩa trường.
- Giữ tính tương thích khi thay đổi API; cân nhắc versioning nếu có thay đổi không tương thích.
- Dùng DTO riêng cho từng mục đích khi request, response, command và persistence có vòng đời khác nhau.

Không cần tạo một DTO riêng cho mọi class nếu hợp đồng thực sự giống nhau. Mục tiêu là giữ ranh giới có ý nghĩa, không phải tăng số lượng lớp.

## 8. Không bind request trực tiếp vào entity

Rủi ro trả entity ra ngoài cũng có chiều ngược lại: nhận JSON rồi bind thẳng vào entity.

Ví dụ không nên dùng:

```java
@PostMapping
public OrderEntity update(@RequestBody OrderEntity order) {
    return orderRepository.save(order);
}
```

Client có thể gửi thêm trường mà endpoint không dự kiến cho phép thay đổi, như `status`, `total`, `customerId` hoặc `paymentReference`. Nếu entity được merge hoặc lưu trực tiếp, dữ liệu không đáng tin cậy có thể thay đổi trạng thái hoặc thuộc tính nhạy cảm.

Hãy định nghĩa request DTO chỉ gồm trường mà client được phép gửi:

```java
public record ChangeShippingAddressRequest(
    @NotBlank String recipientName,
    @NotBlank String street,
    @NotBlank String city,
    @NotBlank String postalCode
) {}
```

Use case nhận command và kiểm tra quyền, trạng thái đơn cùng chính sách địa chỉ giao hàng trước khi cập nhật entity. ID của chủ sở hữu nên lấy từ ngữ cảnh xác thực hoặc được kiểm tra ở use case, không mặc định tin giá trị client gửi.

## 9. Các cách ánh xạ DTO phổ biến

| Cách làm | Khi phù hợp | Lưu ý |
|---|---|---|
| Ánh xạ thủ công | DTO nhỏ, số trường ít, cần nhìn rõ dữ liệu được công bố | Dễ kiểm soát nhưng có thể lặp khi mapping nhiều |
| MapStruct | Nhiều DTO và mapping lặp lại, muốn sinh mã lúc biên dịch | Cần kiểm tra mapping để tránh vô tình công bố trường |
| Spring Data projection | Truy vấn đọc chỉ cần một phần trường | Tối ưu dữ liệu truy vấn; nên chuyển thành DTO API nếu cần hợp đồng ổn định |
| JPQL constructor projection | Cần dữ liệu tổng hợp hoặc join có chủ đích | Câu truy vấn mô tả rõ output, nhưng gắn với cấu trúc truy vấn |
| Read model riêng | Màn hình đọc phức tạp hoặc nhu cầu đọc khác mô hình ghi | Có thêm chi phí đồng bộ và quản lý dữ liệu |

Với mapping thủ công, nên đặt logic chuyển đổi ở application service hoặc mapper được gọi trong ranh giới phù hợp. Tránh viết mapper chung chung dùng reflection để tự động duyệt mọi association, vì nó có thể kích hoạt lazy loading không chủ ý và khó kiểm soát dữ liệu được công bố.

Nếu dùng MapStruct, có thể khai báo rõ trường nguồn và đích. Tuy nhiên, MapStruct không tự giải quyết fetch plan. Mapper gọi getter trên association lazy vẫn có thể làm Hibernate phát truy vấn hoặc ném exception nếu session đã đóng.

## 10. Kiểm thử để phát hiện entity leakage và lazy loading

Kiểm thử cần xác minh hợp đồng API và hành vi truy vấn, không chỉ xác minh phương thức controller trả về HTTP 200.

| Phạm vi | Điều cần xác minh |
|---|---|
| Controller/web test | JSON chỉ có trường DTO dự kiến; không lộ thuộc tính nội bộ hoặc cấu trúc entity |
| Application test | Use case tạo đúng DTO và xử lý trường hợp không tìm thấy dữ liệu |
| Repository integration test | Entity graph, projection và truy vấn trả đủ dữ liệu cần thiết |
| Serialization test | DTO có thể serialize sau khi transaction kết thúc mà không cần session ORM |
| Query/performance test | Số truy vấn không tăng tuyến tính bất ngờ theo số bản ghi |

Ví dụ kiểm thử JSON có thể xác minh các trường công bố:

```java
@WebMvcTest(OrderQueryController.class)
class OrderQueryControllerTest {
    @Autowired MockMvc mvc;
    @MockBean GetOrderDetailService service;

    @Test
    void returnsOnlyTheOrderResponseContract() throws Exception {
        var response = new OrderDetailResponse(
            UUID.fromString("11111111-1111-1111-1111-111111111111"),
            "PAID",
            "Nguyen An",
            new BigDecimal("250000"),
            List.of()
        );

        given(service.handle(any())).willReturn(response);

        mvc.perform(get("/api/orders/11111111-1111-1111-1111-111111111111"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.customerName").value("Nguyen An"))
            .andExpect(jsonPath("$.total").value(250000))
            .andExpect(jsonPath("$.internalNote").doesNotExist())
            .andExpect(jsonPath("$.customer").doesNotExist());
    }
}
```

Kiểm thử này minh họa hợp đồng JSON. Với kiểm thử persistence, hãy dùng database kiểm thử phù hợp để xác minh association được tải và mapper không phát truy vấn ngoài dự kiến. Có thể bật Hibernate statistics hoặc ghi nhận SQL trong test để quan sát số lượng truy vấn; tránh đặt một ngưỡng truy vấn cứng thiếu cơ sở nếu cấu hình database/provider thay đổi.

Một bài test hữu ích là gọi application service, nhận DTO, kết thúc transaction rồi serialize DTO. Nếu serialize DTO vẫn cần session ORM, có thể DTO đang chứa entity, proxy hoặc kiểu dữ liệu phụ thuộc persistence.

## 11. Lỗi thường gặp và cách xử lý

**Trả entity rồi thêm @JsonIgnore vào trường nhạy cảm.** Cách này có thể ẩn một số trường nhưng API vẫn phụ thuộc cấu trúc entity và association. Hãy dùng response DTO với danh sách trường được chọn rõ ràng.

**Chuyển tất cả quan hệ thành EAGER.** Cách này có thể làm nhiều use case tải dữ liệu dư thừa và vẫn không đảm bảo chỉ có một truy vấn. Hãy chọn fetch plan theo use case.

**Tắt OSIV nhưng vẫn ánh xạ entity sau transaction.** Khi association chưa tải, mapper có thể ném `LazyInitializationException`. Hãy tải đủ dữ liệu và ánh xạ DTO trong transaction phù hợp, hoặc dùng projection.

**Dùng DTO nhưng bên trong vẫn chứa entity.** Ví dụ `OrderResponse(CustomerEntity customer)` vẫn mang proxy và ranh giới ORM ra ngoài. DTO nên chứa `customerName`, `customerId` hoặc một `CustomerResponse` được tạo từ dữ liệu đã tải.

**Dùng mapper tự động trên toàn bộ object graph.** Mapper có thể duyệt association sâu, gây N+1 hoặc vòng lặp. Hãy cấu hình mapping tường minh và giới hạn chiều sâu.

**Dùng fetch join collection cho mọi trang phân trang.** Join collection có thể nhân bản dòng và ảnh hưởng giới hạn trang. Với danh sách, projection thường phù hợp hơn; với trang chi tiết, fetch graph có thể là lựa chọn tốt.

**Trả dữ liệu nội bộ vì tiện cho frontend.** Mỗi trường được công bố đều trở thành một phần hợp đồng. Hãy xác định nhu cầu giao diện và quyền truy cập trước khi thêm trường.

## 12. Cách rà soát một endpoint đọc

Khi xem lại một endpoint trả dữ liệu, hãy tự hỏi:

1. Kiểu trả về có phải DTO hoặc projection được kiểm soát không?
2. DTO có chứa entity, Hibernate proxy hoặc collection ORM không?
3. Trường nào thực sự cần cho client và người dùng có quyền xem chúng không?
4. Association nào được truy cập trong lúc mapping và chúng được tải bằng fetch plan nào?
5. Nếu tắt OSIV hoặc kết thúc transaction trước serialize, endpoint có còn hoạt động không?
6. Truy vấn có thể phát N+1 khi số lượng bản ghi tăng không?
7. Nếu quan hệ entity thay đổi, hợp đồng API có bị thay đổi ngoài ý muốn không?
8. Request có bind trực tiếp vào entity và cho phép sửa trường nhạy cảm không?
9. Có kiểm thử JSON contract, lazy loading và hiệu năng truy vấn phù hợp không?

Khi tầng trình bày chỉ nhận DTO đã được chuẩn bị có chủ đích, client không phải biết entity được lưu thế nào hoặc association được tải khi nào. Tầng lưu trữ có thể thay đổi mapping và fetch strategy theo nhu cầu, còn hợp đồng API giữ được sự ổn định và kiểm soát rõ dữ liệu được công bố.

