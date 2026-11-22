# Trả thực thể trực tiếp qua API khiến đồ thị bị tải hoặc lộ ngoài dự kiến

## 1. Vấn đề: một entity không phải là response contract

Trong ứng dụng Spring Boot dùng Hibernate, controller có thể trả thẳng entity:

```java
@GetMapping("/orders/{id}")
public PurchaseOrder getOrder(@PathVariable Long id) {
    return orderRepository.findById(id).orElseThrow();
}
```

Code rất ngắn, và Jackson có thể serialize object thành JSON. Nhưng entity được thiết kế để biểu diễn trạng thái persistence và quan hệ dữ liệu; nó không nhất thiết được thiết kế để trở thành hợp đồng HTTP.

Khi Jackson duyệt object graph, những vấn đề có thể xuất hiện:

- Một getter truy cập association lazy và kích hoạt thêm SQL.
- Một response nhỏ ban đầu trở thành hàng trăm query (N+1).
- Serialization xảy ra sau khi transaction/Session đóng, gây LazyInitializationException.
- Quan hệ hai chiều khiến JSON lặp vô hạn hoặc ném lỗi self-reference.
- Những field nội bộ như trạng thái kiểm duyệt, tenant ID, giá vốn, token hoặc dữ liệu cá nhân bị lộ.
- Một thay đổi mapping entity làm cấu trúc JSON API đổi ngoài dự kiến.
- Client gửi JSON ngược lại và vô tình cập nhật các field mà user không được phép sửa.

Vấn đề không chỉ là hiệu năng. Đây còn là **ranh giới bảo mật và hợp đồng API**. Cách xử lý bền vững là thiết kế response DTO/read model riêng, tải đúng dữ liệu cần thiết trong transaction và chỉ serialize dữ liệu đã được chọn.

## 2. Entity, persistence context và JSON serializer có mục đích khác nhau

Ba thành phần thường bị ghép trực tiếp:

```text
Database
   |
   v
Hibernate Entity / Persistence Context
   |
   v
Jackson ObjectMapper
   |
   v
HTTP JSON response
```

Mỗi thành phần có một trách nhiệm:

| Thành phần | Mục tiêu |
|---|---|
| Entity | Mô hình hóa dữ liệu và quan hệ trong persistence layer |
| Hibernate Session/EntityManager | Quản lý identity, dirty checking, lazy loading và unit of work |
| DTO/API response | Mô tả dữ liệu client được phép nhận |
| Jackson | Chuyển object đã chọn thành JSON theo serialization configuration |

Nếu trả entity trực tiếp, API vô tình phụ thuộc vào mapping, fetch strategy, proxy implementation và getters của entity. Một thay đổi nội bộ có thể làm thay đổi response mà không có chủ đích.

Một response DTO tạo ranh giới rõ:

```text
Database
   |
   v
Hibernate Entity
   |
   v
Service maps selected fields
   |
   v
OrderResponse DTO
   |
   v
Jackson
   |
   v
Stable, intentional JSON contract
```

## 3. Vì sao Jackson có thể kích hoạt lazy loading?

Giả sử:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
```

Jackson serialize một object bằng cách tìm các properties (thường qua getters/fields theo cấu hình) rồi đọc giá trị của chúng. Khi nó gọi các getter như getCustomer().getName() hoặc getLines().size(), Hibernate có thể phải truy vấn database để khởi tạo proxy hoặc collection lazy.

Ví dụ JSON được mong muốn:

```json
{
  "id": 42,
  "customer": {
    "id": 7,
    "name": "Lan"
  },
  "lines": [
    {"productCode": "BOOK-1", "quantity": 2}
  ]
}
```

Để tạo JSON này, serializer có thể đi từ Order sang Customer rồi sang các quan hệ khác mà mapping/getters cho phép. Nó không hiểu giới hạn nghiệp vụ “response chỉ cần tên khách hàng và hai dòng hàng”.

**Serialization có thể trở thành một chuỗi truy cập object graph và truy vấn DB.** Vì vậy, số SQL không chỉ phụ thuộc query trong repository mà còn phụ thuộc các getter được serializer gọi.

## 4. Lazy loading và thời điểm Session còn mở

Một association lazy thường cần persistence context còn hợp lệ để tải dữ liệu:

```text
Transaction begins
  |
  v
Repository loads PurchaseOrder
  |
  v
Service returns entity
  |
  v
Transaction commits / EntityManager closes
  |
  v
Jackson serializes entity
  |
  v
Getter touches uninitialized association
  |
  v
LazyInitializationException
```

Lỗi thường thấy:

```text
org.hibernate.LazyInitializationException:
could not initialize proxy - no Session
```

Không phải mọi association đều lazy và không phải mọi serializer đều gọi cùng getter. Nhưng khi serialization phụ thuộc một association chưa được tải, Session đã đóng thì Hibernate không còn context để thực hiện query.

### 4.1. Tại sao lỗi có thể chỉ xuất hiện ở production?

- Local profile bật Open EntityManager in View nên Session còn mở trong web request.
- Production tắt OSIV hoặc transaction boundary khác.
- Một dữ liệu cụ thể có association chưa được khởi tạo.
- Jackson module/configuration khác nhau.
- Response có thêm getter mới sau một lần refactor.
- Một collection chỉ có dữ liệu ở một số orders.

Đừng kết luận “chạy local được” là response an toàn. Hãy kiểm tra behavior với OSIV tắt và dữ liệu có quan hệ thật.

## 5. Open EntityManager in View (OSIV) có thể che lỗi

Spring Boot MVC có thể cấu hình Open EntityManager in View (OSIV). Khi bật, EntityManager có thể được giữ mở đến cuối quá trình xử lý web request, dù service transaction đã kết thúc.

Điều này có thể khiến Jackson truy cập lazy association mà không ném LazyInitializationException. Nhưng query có thể được thực hiện trong lúc serialize response, sau business transaction:

```text
Service transaction:
  SELECT purchase_order
  COMMIT
       |
       v
Controller returns entity
       |
       v
Jackson serialization
  SELECT customer
  SELECT order_lines
  SELECT products ...
       |
       v
HTTP response
```

OSIV có thể làm ứng dụng “chạy được” nhưng SQL phát sinh ở tầng web, khiến:

- Hiệu năng khó dự đoán.
- Transaction/query boundary không rõ.
- N+1 bị che khuất.
- Lỗi DB có thể xuất hiện khi response đang được ghi.
- Developer khó kiểm soát fetch plan cho từng endpoint.

Với REST API, một lựa chọn phổ biến là tắt OSIV và tải dữ liệu cần thiết trong service transaction:

```properties
spring.jpa.open-in-view=false
```

Khi đó, lỗi lazy access ngoài transaction sẽ lộ sớm hơn. Điều này hữu ích để phát hiện response còn phụ thuộc entity graph chưa được chuẩn bị.

OSIV không phải lúc nào cũng sai trong mọi ứng dụng; nhưng không nên dùng nó để thay thế thiết kế fetch plan và DTO.

## 6. N+1 query do serializer duyệt collections

Một service lấy danh sách 50 orders:

```java
List<PurchaseOrder> orders =
    orderRepository.findAllByStatus(OrderStatus.OPEN);
return orders;
```

Nếu mỗi Order có một Customer lazy và Jackson gọi getCustomer().getName(), có thể xảy ra:

```text
1 query: load 50 orders
50 queries: load customer for each order
```

Nếu serializer tiếp tục truy cập order.getLines():

```text
1 query: load orders
50 queries: load customers
50 queries: load order lines
N queries: load products referenced by lines
```

Đây là một dạng N+1: một query lấy danh sách gốc, sau đó nhiều query bổ sung để khởi tạo associations.

Không nhất thiết mỗi association luôn gây đúng một query; first-level cache, batch fetching, join fetching và dữ liệu trùng có thể làm số lượng khác nhau. Nhưng serialize entity graph rộng khiến SQL count phụ thuộc số bản ghi và shape dữ liệu.

## 7. Quan hệ hai chiều có thể tạo vòng lặp JSON

Ví dụ:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;
}

@Entity
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne
    private PurchaseOrder order;
}
```

Object graph:

```text
PurchaseOrder
  |
  +-- lines[0] -> OrderLine
                    |
                    +-- order -> PurchaseOrder
                                  |
                                  +-- lines[0] -> ...
```

Jackson có thể đi theo vòng:

```text
order -> lines -> line.order -> lines -> line.order -> ...
```

Tùy cấu hình, kết quả có thể là:

- Lỗi max nesting depth/stack overflow.
- JSON bị lặp nhiều cấp.
- Dữ liệu dư thừa rất lớn.
- Một annotation Jackson ngăn vòng lặp nhưng vô tình bỏ field client cần.

Đây là lý do quan hệ domain hai chiều không nên được serialize trực tiếp thành API graph.

## 8. Rủi ro lộ field không thuộc API

Một entity:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String displayName;
    private String email;
    private String passwordHash;
    private boolean internalReviewRequired;
    private BigDecimal creditLimit;
    private String tenantId;
}
```

API danh sách khách hàng chỉ cần:

```json
{
  "id": 12,
  "displayName": "Lan"
}
```

Nhưng nếu controller serialize entity, Jackson có thể serialize thêm các getters tương ứng với email, passwordHash, creditLimit, tenantId hoặc field nội bộ khác, trừ khi có cấu hình/annotation loại trừ. Một số dữ liệu không được lộ ngay cả với người dùng cùng tenant.

**Không dùng entity field visibility làm authorization policy.** DTO response cho phép chọn đúng field được phép công bố theo endpoint, user role và trạng thái nghiệp vụ.

## 9. Rủi ro mass assignment khi nhận entity từ request

Trả entity trực tiếp đã nguy hiểm; nhận request JSON và bind thẳng vào entity còn có thể nghiêm trọng hơn:

```java
@PutMapping("/customers/{id}")
public Customer update(
        @PathVariable Long id,
        @RequestBody Customer customer) {
    customer.setId(id);
    return repository.save(customer);
}
```

Client có thể gửi các property ngoài ý muốn:

```json
{
  "displayName": "New name",
  "tenantId": "another-tenant",
  "creditLimit": 999999999,
  "internalReviewRequired": false
}
```

Nếu mapping và service không giới hạn field, request có thể ghi đè dữ liệu nhạy cảm. Đây là **mass assignment/over-posting**.

Tách request DTO:

```java
public record UpdateCustomerRequest(
    @NotBlank String displayName
) {}
```

Service tải managed entity rồi gọi domain method:

```java
@Transactional
public CustomerResponse update(
        long id, UpdateCustomerRequest request) {

    Customer customer = customers.findById(id)
        .orElseThrow(CustomerNotFoundException::new);

    customer.changeDisplayName(request.displayName());
    return CustomerResponse.from(customer);
}
```

Chỉ những fields nằm trong request contract mới được phép thay đổi. Tenant, role, ownership, version và các trạng thái đặc quyền phải được xử lý theo policy riêng.

## 10. Entity không phải API versioning contract

Giả sử entity thêm field:

```java
private String internalRiskScore;
```

Nếu controller serialize entity, response JSON có thể tự động xuất hiện property mới. Client cũ có thể:

- Lưu field ngoài dự kiến.
- Hiển thị thông tin nội bộ.
- Phụ thuộc vào property không được đảm bảo.
- Gửi lại field ấy trong PUT/PATCH.

Ngược lại, đổi tên Java property, thêm association hoặc thay cách map enum có thể phá API clients dù database migration không có lỗi.

DTO cho phép API contract được version và review độc lập với persistence model:

```java
public record CustomerResponseV1(
    Long id,
    String displayName
) {}
```

Khi cần thêm trường:

```java
public record CustomerResponseV2(
    Long id,
    String displayName,
    String accountStatus
) {}
```

Không nhất thiết phải tạo một DTO class cho mọi phiên bản nhỏ, nhưng cần một contract có chủ đích thay vì để entity mapping tự quyết định JSON.

## 11. Giải pháp chính: Response DTO

Một DTO chỉ chứa dữ liệu endpoint cần:

```java
public record OrderLineResponse(
    String productCode,
    String productName,
    int quantity,
    BigDecimal unitPrice
) {}

public record OrderResponse(
    Long id,
    String orderNumber,
    String status,
    String customerName,
    List<OrderLineResponse> lines,
    BigDecimal total
) {}
```

Service chuyển entity thành DTO:

```java
@Transactional(readOnly = true)
public OrderResponse getOrder(long id) {
    PurchaseOrder order = orders.findForResponse(id)
        .orElseThrow(OrderNotFoundException::new);

    List<OrderLineResponse> lines = order.getLines()
        .stream()
        .map(line -> new OrderLineResponse(
            line.getProduct().getCode(),
            line.getProduct().getName(),
            line.getQuantity(),
            line.getUnitPrice()))
        .toList();

    return new OrderResponse(
        order.getId(),
        order.getOrderNumber(),
        order.getStatus().name(),
        order.getCustomer().getDisplayName(),
        lines,
        order.getTotal());
}
```

Ví dụ giả định repository method findForResponse() được cấu hình để tải associations cần thiết. Việc map DTO nằm trong transaction để các lazy values cần dùng có thể được đọc ở đúng boundary.

DTO giúp:

- Chọn field được phép trả.
- Tránh lộ association không cần.
- Giới hạn graph và response size.
- Định nghĩa API contract độc lập với entity.
- Kiểm soát serialization sau khi Session đóng.
- Dễ test JSON shape.

## 12. DTO không tự giải quyết N+1 nếu mapping vẫn chạm từng proxy

Đoạn:

```java
orders.stream()
    .map(order -> new OrderResponse(
        order.getId(),
        order.getCustomer().getName()))
    .toList();
```

vẫn có thể gây N+1 nếu query ban đầu chỉ load orders và mỗi customer được lazy-load riêng.

DTO là **ranh giới response**, còn fetch plan là **chiến lược tải dữ liệu**. Cần thiết kế cả hai:

1. Xác định fields cần trả.
2. Xác định associations/columns cần tải.
3. Dùng projection, fetch join, entity graph hoặc batch fetching phù hợp.
4. Map DTO trong transaction.
5. Kiểm tra SQL count và response JSON.

Không thay entity bằng DTO rồi cho rằng query count tự giảm.

## 13. Cách 1: JPQL constructor projection

Nếu response chỉ cần một vài scalar fields, projection trực tiếp thường hiệu quả:

```java
public record OrderSummaryResponse(
    Long id,
    String orderNumber,
    String customerName,
    BigDecimal total
) {}
```

Repository:

```java
@Query("""
    select new com.example.api.OrderSummaryResponse(
        o.id,
        o.orderNumber,
        c.displayName,
        o.total
    )
    from PurchaseOrder o
    join o.customer c
    where o.id = :id
    """)
Optional<OrderSummaryResponse> findSummaryById(
    @Param("id") Long id);
```

Hibernate thực hiện query để tạo DTO, không cần trả entity graph cho Jackson. JPQL constructor expression dùng tên class đầy đủ và kiểu/thứ tự arguments phải khớp constructor/record.

Nếu cần quan hệ optional, cân nhắc left join thay cho join; inner join có thể làm mất Order khi association không có target hợp lệ.

## 14. Cách 2: Spring Data interface projection

Ví dụ:

```java
public interface OrderSummaryProjection {
    Long getId();
    String getOrderNumber();
    String getCustomerName();
    BigDecimal getTotal();
}
```

Repository:

```java
@Query("""
    select
      o.id as id,
      o.orderNumber as orderNumber,
      c.displayName as customerName,
      o.total as total
    from PurchaseOrder o
    join o.customer c
    where o.id = :id
    """)
Optional<OrderSummaryProjection> findSummary(
    @Param("id") Long id);
```

Spring Data JPA có thể tạo projection từ query aliases. Cần đảm bảo alias khớp getter property names và kiểm tra SQL thật. Nested interface projections có thể khiến association traversal/fetch behavior phức tạp hơn; không giả định mọi nested projection đều chỉ phát một query.

## 15. Cách 3: EntityGraph cho use case cần entity

Nếu service cần entity behavior và associations cụ thể, dùng `@EntityGraph` để khai báo fetch plan:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {
        "customer",
        "lines",
        "lines.product"
    })
    @Query("select o from PurchaseOrder o where o.id = :id")
    Optional<PurchaseOrder> findForResponse(
        @Param("id") Long id);
}
```

Sau đó service map entity sang DTO trong transaction.

EntityGraph mô tả association cần fetch; nó không phải cam kết rằng Hibernate luôn sinh một SQL duy nhất. Collection fetch, pagination, multiple bags và mapping shape có thể khiến SQL strategy khác.

Đừng đưa mọi association vào một graph chung cho mọi endpoint. Mỗi response nên có fetch plan phù hợp use case.

## 16. Cách 4: JOIN FETCH

Một JPQL query:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    left join fetch o.lines line
    left join fetch line.product
    where o.id = :id
    """)
Optional<PurchaseOrder> findDetailedById(
    @Param("id") Long id);
```

JOIN FETCH yêu cầu Hibernate lấy association trong query đó. Dùng left join fetch nếu association/collection có thể vắng mặt; join fetch inner join có thể loại root row không có target.

### 16.1. Fetch nhiều collections có thể nhân số rows

Nếu Order có 5 lines và 3 payments, join fetch cả hai collections có thể tạo khoảng 15 result rows cho một order trước khi Hibernate khử trùng lặp entity references. Với nhiều orders, số rows tăng nhanh.

Một số Hibernate mappings có thể báo MultipleBagFetchException khi cố fetch đồng thời nhiều bag collections. Đổi List thành Set chỉ để né exception có thể thay đổi semantics và không tự giải quyết Cartesian multiplication.

Các phương án:

- Fetch một collection chính bằng join, collection khác tải batch.
- Chạy hai queries có kiểm soát trong cùng transaction.
- Dùng DTO projection/aggregation.
- Chia endpoint hoặc response theo use case.

## 17. Cách 5: Batch fetching cho lazy associations

Nếu cần duyệt một danh sách entities và load association, Hibernate batch fetching có thể giảm N+1 bằng cách tải nhiều IDs trong một query:

```java
@ManyToOne(fetch = FetchType.LAZY)
@BatchSize(size = 32)
private Customer customer;
```

Hoặc cấu hình batch size phù hợp:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Batch fetching là chiến lược tối ưu tải lazy association; nó không làm DTO/response contract an toàn hơn. Jackson vẫn có thể tải những association mà endpoint không nên trả.

Batch size cần đo theo database parameter limits, số entities và workload; 32 chỉ là giá trị minh họa.

## 18. Không dùng EAGER để sửa lỗi serialization

Một phản ứng thường gặp:

```java
@OneToMany(fetch = FetchType.EAGER)
private List<OrderLine> lines;
```

để Jackson không gặp LazyInitializationException.

Điều này có thể làm:

- Mọi query load Order đều kéo OrderLine dù endpoint không cần.
- Danh sách orders kéo theo nhiều collection.
- Query plan và row multiplication tăng.
- N+1 chuyển sang các associations khác.
- API vô tình lộ thêm graph.

FetchType.EAGER là yêu cầu fetch ở mức mapping, không phải một fetch plan tối ưu cho mọi use case. Thường giữ associations lazy theo nhu cầu và định nghĩa fetch plan rõ tại query/service.

## 19. Cách map DTO an toàn trong transaction

Một service:

```java
@Service
public class OrderQueryService {
    private final PurchaseOrderRepository orders;

    public OrderQueryService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderResponse get(long id) {
        PurchaseOrder order = orders.findForResponse(id)
            .orElseThrow(OrderNotFoundException::new);

        return OrderResponse.from(order);
    }
}
```

Factory method:

```java
public record OrderResponse(
    Long id,
    String number,
    String customerName,
    List<OrderLineResponse> lines
) {
    static OrderResponse from(PurchaseOrder order) {
        List<OrderLineResponse> lineResponses =
            order.getLines().stream()
                .map(line -> new OrderLineResponse(
                    line.getProduct().getCode(),
                    line.getQuantity()))
                .toList();

        return new OrderResponse(
            order.getId(),
            order.getOrderNumber(),
            order.getCustomer().getDisplayName(),
            lineResponses);
    }
}
```

Sau khi service trả về, controller chỉ nhận DTO không còn phụ thuộc Hibernate proxy:

```java
@GetMapping("/{id}")
public OrderResponse get(@PathVariable long id) {
    return queryService.get(id);
}
```

Controller không phải nơi điều khiển lazy loading; service/repository chịu trách nhiệm lấy dữ liệu cho use case.

## 20. Tại sao DTO nên là immutable?

Java record là một cách thuận tiện cho response:

```java
public record CustomerResponse(
    Long id,
    String displayName,
    String status
) {}
```

Ưu điểm:

- Không có setter để thay đổi response sau khi tạo.
- Constructor thể hiện rõ các fields bắt buộc.
- Dễ so sánh trong tests.
- Không mang Hibernate proxy hoặc persistence lifecycle.

Immutable DTO không tự bảo đảm data privacy; developer vẫn phải chọn fields đúng. Nhưng nó giảm khả năng một tầng sau vô tình sửa object đang chuẩn bị trả.

## 21. DTO cho request và DTO cho response nên tách

Không dùng cùng một class làm entity, request và response nếu các quyền đọc/ghi khác nhau.

Ví dụ:

```java
public record CreateOrderRequest(
    @NotNull Long customerId,
    @NotEmpty List<CreateOrderLineRequest> lines
) {}

public record CreateOrderLineRequest(
    @NotBlank String productCode,
    @Positive int quantity
) {}

public record OrderResponse(
    Long id,
    String orderNumber,
    String status,
    BigDecimal total
) {}
```

Request chỉ chứa command inputs mà client được phép cung cấp. Response chỉ chứa outputs mà client được phép xem.

Entity vẫn quản lý persistence state:

```text
CreateOrderRequest -> validate -> service command
                                   |
                                   v
                              Entity changes
                                   |
                                   v
                             DB transaction
                                   |
                                   v
                              OrderResponse
                                   |
                                   v
                               JSON
```

Không bind request vào entity rồi gọi save() như một cách cập nhật chung.

## 22. Không expose entity IDs hoặc relationships một cách thiếu chủ đích

Một entity có:

```java
@ManyToOne
private Tenant tenant;

@ManyToOne
private User createdBy;

@OneToMany
private List<AuditRecord> auditRecords;
```

Trả entity có thể làm Jackson duyệt tenant, createdBy, auditRecords, rồi tiếp tục duyệt graph của những object đó. Response có thể lộ:

- Tenant identifiers/names nội bộ.
- User profile fields.
- Audit metadata.
- Quan hệ của các entities khác.

DTO nên biểu diễn đúng API needs, ví dụ createdByDisplayName nếu user được phép xem, thay vì serialize cả User.

Nếu client cần link tới resource khác, có thể trả ID/URI có chủ đích và enforce authorization ở endpoint đích.

## 23. Jackson annotations có thể xử lý vòng lặp, nhưng không thay DTO

Một số annotation:

- `@JsonIgnore`: bỏ property khỏi JSON.
- `@JsonManagedReference`/`@JsonBackReference`: xử lý một số quan hệ hai chiều.
- `@JsonIdentityInfo`: serialize object identity/reference.
- `@JsonIgnoreProperties`: bỏ qua một số properties.

Ví dụ:

```java
@OneToMany(mappedBy = "order")
@JsonManagedReference
private List<OrderLine> lines;

@ManyToOne
@JsonBackReference
private PurchaseOrder order;
```

Chúng có thể ngăn vòng lặp serialization trong một số model. Nhưng:

- Không giải quyết quyền truy cập field theo từng endpoint.
- Không tự ngăn lazy loads/N+1.
- Không tạo API contract ổn định.
- Có thể khiến một endpoint cần field nhưng field bị bỏ.
- Làm entity phụ thuộc Jackson.

Dùng Jackson annotations khi có lý do rõ ràng ở serialization boundary; với API nghiệp vụ, DTO thường dễ kiểm soát hơn.

## 24. Jackson Hibernate module có giải quyết hết vấn đề không?

Jackson có module tích hợp Hibernate ở các artifact phù hợp với version Hibernate, ví dụ các module có tên gắn với Hibernate 5/6/7. Chúng có thể giúp serializer hiểu proxy/persistent collection, ví dụ tránh cố serialize proxy chưa khởi tạo hoặc xử lý một số Hibernate-specific types.

Nhưng module này:

- Không chọn fields theo quyền user.
- Không quyết định fetch plan tối ưu.
- Không thay thế DTO.
- Không bảo đảm không có N+1 nếu cấu hình cho phép lazy loading.
- Phải tương thích với Jackson/Hibernate version.

Đừng cài một Hibernate module chỉ để “JSON chạy được” rồi bỏ qua data exposure và query count.

## 25. Tránh trả Hibernate proxy trực tiếp

Một proxy có thể chứa handler nội bộ và chỉ tải target khi truy cập. Nếu serializer nhìn thấy proxy, tùy Jackson module/configuration nó có thể:

- Serialize các property nội bộ không mong muốn.
- Gọi getter và khởi tạo proxy.
- Bỏ qua proxy chưa initialized.
- Ném exception.

Không dùng Hibernate.initialize() cho mọi association trước khi trả entity như một cách sửa tổng quát. Nó chỉ chủ động tải graph, có thể làm query count và response size lớn hơn.

Hãy tạo DTO chứa scalar values đã được tải có chủ đích.

## 26. Projection cho danh sách và phân trang

Một endpoint list thường không cần toàn bộ aggregate:

```java
public record OrderListItem(
    Long id,
    String orderNumber,
    String customerName,
    String status,
    BigDecimal total,
    Instant createdAt
) {}
```

Query:

```java
@Query("""
    select new com.example.api.OrderListItem(
        o.id,
        o.orderNumber,
        c.displayName,
        o.status,
        o.total,
        o.createdAt
    )
    from PurchaseOrder o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<OrderListItem> findOrderPage(
    @Param("status") OrderStatus status,
    Pageable pageable);
```

Projection chỉ lấy columns cần thiết và tránh hydrate toàn bộ entity graph. Với Page<T>, Spring Data có thể chạy thêm count query; kiểm tra query thực tế và joins, đặc biệt khi query phức tạp.

Nếu customer optional, dùng left join và DTO field có thể null.

## 27. Pagination và collection fetch join

Không nên tùy tiện kết hợp pagination với collection fetch join:

```java
select distinct o
from PurchaseOrder o
left join fetch o.lines
order by o.createdAt desc
```

Nếu phân trang trên result rows sau join, một Order có nhiều lines sẽ chiếm nhiều rows. Hibernate có thể phải xử lý pagination trong memory hoặc cảnh báo/throw tùy cấu hình/version.

Một pattern thường tốt hơn:

1. Query trang IDs/scalar summaries của Orders.
2. Query detail/collection cho các IDs trong trang.
3. Map sang DTO, bảo toàn thứ tự trang.

Ví dụ:

```java
Page<Long> ids = repository.findOrderIds(status, pageable);

List<PurchaseOrder> details =
    repository.findDetailsByIds(ids.getContent());
```

Cần giữ thứ tự IDs theo trang vì IN (:ids) không tự bảo đảm order giống danh sách input. Có thể sắp xếp lại trong service hoặc dùng query có ordering rõ.

## 28. EntityGraph và DTO projection nên chọn khi nào?

| Use case | Lựa chọn thường phù hợp |
|---|---|
| Chỉ cần một vài cột scalar | DTO constructor/interface projection |
| Cần domain methods và một số associations | EntityGraph/fetch query rồi map DTO |
| Một entity detail với graph nhỏ, cố định | Fetch join hoặc EntityGraph |
| List/page lớn | DTO projection, tránh fetch nhiều collections |
| Báo cáo tổng hợp/group by | DTO projection/aggregate query |
| Graph lớn/nhiều collections | Nhiều queries có kiểm soát hoặc read model |
| Client cần dữ liệu tùy chọn theo màn hình | Endpoint/projection riêng theo use case |

Không có một fetch strategy duy nhất tốt cho mọi endpoint.

## 29. MapStruct có thể giúp map entity sang DTO

MapStruct tạo code mapping ở compile time:

```java
@Mapper(componentModel = "spring")
public interface OrderMapper {

    @Mapping(target = "customerName",
             source = "customer.displayName")
    @Mapping(target = "lineCount",
             expression = "java(order.getLines().size())")
    OrderResponse toResponse(PurchaseOrder order);
}
```

Mapper này vẫn gọi association getters. Nếu customer hoặc lines chưa được tải, mapping có thể kích hoạt lazy query hoặc thất bại khi Session đóng.

MapStruct giải quyết boilerplate chuyển đổi, **không tự quyết định dữ liệu đã được fetch đúng chưa**. Repository query/fetch plan phải được thiết kế trước, và mapper nên được gọi trong transaction nếu cần đọc entity associations.

Với expression gọi method có side effects hoặc truy vấn, tránh để mapper biến thành service layer ẩn.

## 30. DTO projection trực tiếp không cần entity có thể tốt hơn

Một báo cáo:

```java
public record RevenueByCustomer(
    Long customerId,
    String customerName,
    BigDecimal revenue
) {}
```

Query:

```java
@Query("""
    select new com.example.api.RevenueByCustomer(
        c.id,
        c.displayName,
        sum(o.total)
    )
    from PurchaseOrder o
    join o.customer c
    where o.createdAt >= :from
      and o.createdAt < :to
    group by c.id, c.displayName
    """)
List<RevenueByCustomer> revenueByCustomer(
    @Param("from") Instant from,
    @Param("to") Instant to);
```

Query trả DTO aggregate trực tiếp; không cần hydrate Customer/Order entities và sau đó duyệt graph trong Java.

Khi báo cáo lớn, cần index phù hợp, query plan và pagination/export strategy. DTO projection không thay thế tối ưu SQL.

## 31. Tách command model khỏi entity update

Request update:

```java
public record ChangeOrderStatusRequest(
    @NotNull OrderStatus status
) {}
```

Service:

```java
@Transactional
public OrderResponse changeStatus(
        long id, ChangeOrderStatusRequest request) {

    PurchaseOrder order = orders.findById(id)
        .orElseThrow(OrderNotFoundException::new);

    order.changeStatus(request.status());
    return mapper.toResponse(order);
}
```

Domain method có thể kiểm tra state transition hợp lệ. Client không thể gửi tenantId, total, createdAt, approvedBy hoặc version tùy ý rồi ghi đè entity.

Nếu response mapping truy cập lazy fields, query ban đầu phải tải chúng hoặc service cần query DTO thích hợp.

## 32. PATCH semantics không nên dựa trên null entity fields

Một PATCH request:

```json
{
  "displayName": "New name"
}
```

không có nghĩa các fields còn lại phải trở thành null. Nếu bind vào entity đầy đủ, property không có trong JSON có thể bị default/null và vô tình ghi đè.

Dùng patch DTO/command với semantics rõ:

- Field omitted: không thay đổi.
- Field present with value: cập nhật.
- Field present with null: xóa giá trị nếu API cho phép.

Có thể dùng wrapper/JSON Merge Patch model phù hợp để phân biệt missing và explicit null. Đừng dựa vào entity setters mặc định để suy ra semantics của PATCH.

## 33. Kiểm soát dữ liệu nhạy cảm theo role

Có thể cùng một entity cần hai response:

```java
public record CustomerPublicResponse(
    Long id,
    String displayName
) {}

public record CustomerAdminResponse(
    Long id,
    String displayName,
    String email,
    String accountStatus,
    Instant createdAt
) {}
```

Không tạo một DTO chứa mọi fields rồi dựa vào client tự bỏ qua dữ liệu không dùng. Nếu field không được phép xem, server không nên gửi nó.

Authorization cần được kiểm tra trước khi query/trả dữ liệu, đặc biệt với PII và dữ liệu tenant. Việc chỉ ẩn field bằng CSS/JavaScript phía client không phải bảo vệ.

## 34. DTO vẫn phải tránh nested graph không giới hạn

Một DTO có thể vô tình tái tạo entity graph:

```java
public record CustomerResponse(
    Long id,
    List<OrderResponse> orders
) {}

public record OrderResponse(
    Long id,
    CustomerResponse customer
) {}
```

Hai DTO tham chiếu vòng vẫn có thể gây vòng lặp nếu mapper tạo object graph tuần hoàn hoặc Jackson đi theo tham chiếu.

API response nên dùng graph có hướng và độ sâu xác định:

```text
CustomerResponse
  -> recentOrders: List<OrderSummaryResponse>
       -> orderId
       -> orderNumber
       -> total

OrderDetailResponse
  -> customer: CustomerSummaryResponse
       -> customerId
       -> displayName
```

OrderSummaryResponse không chứa CustomerResponse lồng ngược lại. Đó là graph DTO hữu hạn và dễ hiểu.

## 35. API link và identifier thay cho object graph

Một response có thể tham chiếu resource khác bằng ID hoặc URI:

```json
{
  "id": 42,
  "customer": {
    "id": 7,
    "href": "/api/customers/7"
  }
}
```

Điều này giúp client lấy detail khi cần và không buộc mọi endpoint tải toàn bộ graph.

Tuy nhiên ID/URI không phải quyền truy cập. Endpoint customer vẫn phải kiểm tra tenant và authorization. Không trả internal database identifiers nếu API contract không cần.

## 36. Serialization và transaction boundary

Một quy tắc hữu ích:

**Mọi dữ liệu cần cho response phải được đọc và chuyển thành DTO trước khi persistence transaction kết thúc.**

Luồng:

```text
Controller
   |
   v
Service @Transactional(readOnly = true)
   |
   +-- Repository query / projection
   +-- Load needed associations
   +-- Map to immutable DTO
   |
   v
Transaction ends
   |
   v
Controller returns DTO
   |
   v
Jackson serializes DTO (no Hibernate lazy access)
```

Đây là ranh giới dễ test và ít phụ thuộc OSIV. DTO có thể vẫn chứa object graph, nhưng graph ấy được tạo có chủ đích và không có proxy cần Hibernate Session.

## 37. Nếu cần streaming response lớn

Không nên tải hàng trăm nghìn entities rồi trả một List<Entity> để Jackson serialize:

- Memory tăng theo graph.
- Persistence context giữ nhiều managed entities.
- Lazy association có thể tạo query bùng nổ.
- Transaction có thể giữ connection quá lâu.
- Response serialization có thể kéo dài và gặp lỗi giữa chừng.

Các phương án:

- DTO projection phân trang.
- Keyset pagination cho dữ liệu lớn/thứ tự ổn định.
- Export job bất đồng bộ tạo file.
- Streaming cursor/scroll với transaction lifecycle được thiết kế rõ.
- Giới hạn số records và response payload.

Nếu stream từ JDBC/Hibernate, phải quản lý connection/transaction cho tới khi stream hoàn tất và đóng tài nguyên khi client disconnect. Không giữ một Session mở tùy tiện trong một HTTP download dài.

## 38. Khi nào dùng Jackson annotations trực tiếp?

Có những trường hợp DTO chưa cần thiết, ví dụ:

- Internal tool nhỏ với entity đơn giản, không có sensitive fields/associations.
- Serialization của một value object không gắn persistence lifecycle.
- Một endpoint nội bộ có contract cố định và graph được kiểm soát chặt.

Ngay cả khi dùng entity:

- Chỉ expose properties đã review.
- Chặn lazy associations không cần.
- Kiểm soát vòng lặp hai chiều.
- Test JSON schema và query counts.
- Không dùng cùng object làm request update.

Nhưng với API nghiệp vụ công khai hoặc nhiều clients, DTO thường là lựa chọn rõ ràng hơn.

## 39. Không serialize trực tiếp Hibernate PersistentCollection

Hibernate collection như PersistentBag, PersistentSet, PersistentList là wrapper quản lý lazy state và snapshot/dirty checking. Chúng không phải collection DTO thông thường.

Jackson có thể duyệt chúng như collection, nhưng khi truy cập có thể kích hoạt initialization. Trả wrapper trực tiếp khiến API behavior phụ thuộc vào Hibernate runtime.

Map sang List<OrderLineResponse> hoặc Set<TagResponse> trong transaction. Sau khi map, collection trong DTO là data đã được tạo, không còn phụ thuộc Hibernate collection wrapper.

## 40. Một ví dụ hoàn chỉnh với repository projection

DTO:

```java
public record OrderDetailResponse(
    Long id,
    String orderNumber,
    String customerName,
    OrderStatus status,
    BigDecimal total
) {}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select new com.example.api.OrderDetailResponse(
            o.id,
            o.orderNumber,
            c.displayName,
            o.status,
            o.total
        )
        from PurchaseOrder o
        join o.customer c
        where o.id = :id
        """)
    Optional<OrderDetailResponse> findDetailResponse(
        @Param("id") Long id);
}
```

Service:

```java
@Service
public class OrderQueryService {
    private final PurchaseOrderRepository orders;

    public OrderQueryService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public OrderDetailResponse get(long id) {
        return orders.findDetailResponse(id)
            .orElseThrow(OrderNotFoundException::new);
    }
}
```

Controller:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderQueryService queries;

    public OrderController(OrderQueryService queries) {
        this.queries = queries;
    }

    @GetMapping("/{id}")
    public OrderDetailResponse get(@PathVariable long id) {
        return queries.get(id);
    }
}
```

Trong ví dụ này Jackson serialize một record chỉ có các giá trị cần thiết. Không cần trả PurchaseOrder entity hoặc để serializer quyết định tải association nào.

## 41. Tenant filtering và DTO không thay thế nhau

Trong multi-tenancy, một query projection:

```java
select new OrderDetailResponse(...)
from PurchaseOrder o
...
where o.id = :id
```

vẫn phải chạy trong tenant context đúng. Nếu Hibernate discriminator mapping được cấu hình đúng, Hibernate có thể thêm tenant restriction cho query ORM tương ứng. Nếu dùng native SQL, phải đưa tenant predicate/RLS policy vào rõ ràng.

DTO chỉ giới hạn **fields trả về**. Nó không tự bảo đảm user được quyền xem row.

Một response không lộ tenantId nhưng chứa dữ liệu của tenant khác vẫn là data leak.

## 42. Lỗi thường gặp khi dùng projection

### 42.1. Constructor expression không khớp

JPQL constructor expression yêu cầu constructor/class name và argument types/order khớp. Nếu đổi record fields mà quên query, ứng dụng có thể lỗi lúc query parsing/execution.

### 42.2. Alias sai với interface projection

Với interface projection, aliases phải khớp getters theo Spring Data mapping. Nếu alias thiếu/sai, property có thể null hoặc không được resolve như mong đợi.

### 42.3. Join làm mất dữ liệu

Join là inner join. Nếu association optional, dùng left join và chấp nhận null trong DTO.

### 42.4. Count query không đúng

Một pageable query có joins/group by có thể cần countQuery riêng để total count chính xác. Kiểm tra SQL và kết quả pagination.

### 42.5. Projection không tự giải quyết mọi JSON shape

Nested response phức tạp có thể cần nhiều queries/DTO mapping. Đừng ép một query thành một graph khổng lồ nếu query plan khó tối ưu.

## 43. Cách phát hiện N+1 bằng SQL logs

Trong môi trường dev/test, bật:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Với Hibernate 6.x, bind logging có thể dùng:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Logger category thay đổi theo Hibernate version. Bind values có thể chứa PII/credentials; chỉ bật khi dữ liệu đã được giả lập/redaction và giới hạn thời gian.

Khi xem log, đếm:

- Query gốc cho list/detail.
- Số query lặp theo từng entity ID.
- Query phát sinh trong lúc serialization.
- Query count khi tăng page size từ 10 lên 50.

Nếu 10 orders tạo 21 queries và 50 orders tạo 101 queries, có dấu hiệu query count tăng tuyến tính theo số records.

## 44. Dùng Hibernate Statistics và datasource metrics

Có thể bật statistics trong môi trường test:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Lấy một số counters:

```java
Statistics stats = entityManagerFactory
    .unwrap(SessionFactory.class)
    .getStatistics();

long statements = stats.getPrepareStatementCount();
long entityFetches = stats.getEntityFetchCount();
long collectionFetches = stats.getCollectionFetchCount();
long queryExecutions = stats.getQueryExecutionCount();
```

Đo trước/sau khi gọi endpoint, nhưng nhớ các counters có thể ở phạm vi SessionFactory và chịu ảnh hưởng requests đồng thời. Integration test nên chạy cô lập; production observability cần tracing/datasource metrics để liên hệ query với request.

## 45. Kiểm thử JSON contract

Dùng MockMvc hoặc WebTestClient để xác nhận JSON chỉ có fields được phép:

```java
mockMvc.perform(get("/api/orders/{id}", orderId))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(orderId))
    .andExpect(jsonPath("$.customerName").value("Lan"))
    .andExpect(jsonPath("$.passwordHash").doesNotExist())
    .andExpect(jsonPath("$.tenantId").doesNotExist());
```

Đây là ví dụ kiểm thử Spring MVC; cần imports, fixtures và authentication setup phù hợp. Kiểm tra cả những fields **không được phép** xuất hiện, không chỉ fields mong muốn.

Response contract tests giúp phát hiện việc thêm field nhạy cảm hoặc đổi shape khi entity mapping được sửa.

## 46. Kiểm thử lazy loading với OSIV tắt

Một test hữu ích:

1. Cấu hình spring.jpa.open-in-view=false.
2. Gọi endpoint thực qua HTTP test client.
3. Dùng dataset có customer, lines và products.
4. Assert response thành công.
5. Assert response không phụ thuộc proxy sau transaction.
6. Đo query count để phát hiện N+1.

Nếu endpoint chỉ chạy được khi OSIV bật, có thể service đang trả entity hoặc DTO mapper chưa tải đủ dữ liệu trong transaction.

Không chỉ unit test mapper.toDto(entity) bằng entity được tạo trong memory; cần integration test với Hibernate Session thật để xác nhận fetch behavior.

## 47. Kiểm thử query count khi page size thay đổi

Một test performance-focused có thể so sánh:

```text
Page size 10 -> query count Q10
Page size 50 -> query count Q50
```

Nếu Q50 tăng gần 5 lần so với Q10, có thể mỗi row đang kích hoạt thêm một query. Mục tiêu không phải luôn có query count hằng số; mục tiêu là hiểu sự tăng trưởng và tránh N+1 không cần thiết.

Query count cụ thể phụ thuộc pagination count query, batch size, cache state và fetch plan. Test cần clear persistence context/cache khi đo để không bị kết quả warm-cache che lấp.

## 48. Kiểm thử vòng lặp JSON và response size

Tạo fixtures có:

- Order có nhiều lines.
- Line trỏ ngược về Order.
- Product có quan hệ tới nhiều entities khác.
- Customer có danh sách Orders.

Sau đó serialize endpoint và xác nhận:

- Không có JSON cycle/error.
- Graph trả về đúng độ sâu dự kiến.
- Không lặp lại parent object.
- Payload size có giới hạn hợp lý.
- Các fields nội bộ không xuất hiện.

Một response có thể không lặp vô hạn nhưng vẫn chứa 10 cấp association không cần thiết. Hãy kiểm tra JSON thực tế, không chỉ kiểm tra HTTP 200.

## 49. Kiểm thử mass assignment

Gửi request có thêm các properties mà client không được quyền sửa:

```json
{
  "displayName": "New name",
  "tenantId": "another-tenant",
  "creditLimit": 999999,
  "internalReviewRequired": false,
  "role": "ADMIN"
}
```

Assert:

- API chỉ bind fields được định nghĩa trong request DTO.
- Tenant/role/credit limit không thay đổi.
- Service kiểm tra authorization và domain rules.
- Response chỉ trả field được phép.

Đây là test bảo mật quan trọng hơn việc chỉ xác nhận displayName được cập nhật.

## 50. Entity listener/callback không phải nơi xây API response

Không cố thêm Jackson annotations hoặc response logic vào entity lifecycle callbacks như `@PostLoad`, `@PrePersist`, `@PostUpdate` để “chuẩn bị JSON”.

Entity callbacks phục vụ persistence lifecycle. Việc phụ thuộc request role, locale, authorization hoặc response shape trong callback làm entity gắn chặt với web layer và có thể chạy trong batch/background jobs không có cùng context.

Mapping DTO nên nằm ở application/service/API layer, nơi có use case và quyền truy cập rõ.

## 51. Tránh serialize lazy collection trong logging

Một lỗi khó phát hiện: service không trả entity ra API nhưng log:

```java
log.debug("Loaded order: {}", order);
```

Nếu toString() được Lombok sinh ra và bao gồm associations, logging có thể:

- Khởi tạo proxy/collections.
- Gây N+1.
- Tạo vòng lặp.
- Lộ PII trong logs.

Tránh `@Data`/generated toString() bao gồm toàn bộ JPA graph. Tự định nghĩa toString() với identifier và một vài scalar fields an toàn; không đưa collections/associations nhạy cảm vào log.

Tương tự equals()/hashCode() dựa trên associations có thể làm truy cập lazy hoặc recursion. Thiết kế equality cho entity cần tuân thủ identity semantics, không dựa vào toàn graph.

## 52. Khi entity có inheritance hoặc polymorphic associations

Nếu entity graph có inheritance:

```java
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    @Id
    private Long id;
}
```

trả entity có thể làm serializer expose subclass-specific fields hoặc trigger joins/loads mà endpoint không dự kiến.

DTO có thể flatten thành một response contract rõ:

```java
public record PaymentResponse(
    Long id,
    String type,
    BigDecimal amount,
    String maskedReference
) {}
```

Service quyết định field nào hợp lệ theo subtype và role. Không trả raw payment entity nếu subclass có dữ liệu nhạy cảm như token/provider payload.

## 53. Tránh dùng entity trong message/event payload

Không serialize entity trực tiếp vào Kafka/RabbitMQ/outbox payload:

```java
eventPublisher.publish(order); // Không nên.
```

Entity có thể mang:

- Proxy/lazy wrappers.
- Association cycles.
- Internal fields.
- State thay đổi sau khi event được tạo.
- Version/mapping details không ổn định.

Tạo immutable event contract:

```java
public record OrderCreatedEvent(
    UUID eventId,
    String tenantId,
    Long orderId,
    String orderNumber,
    BigDecimal total,
    Instant occurredAt
) {}
```

Event DTO chỉ chứa dữ liệu consumer cần. Với transactional outbox, persist event payload trong cùng transaction với aggregate update và giữ schema/version compatibility.

## 54. Version hóa DTO và compatibility

Entity có thể thay đổi thường xuyên khi domain phát triển. API DTO cần compatibility policy:

- Thêm field optional thường có thể backward compatible nếu client chịu được unknown fields.
- Đổi tên/xóa field là breaking change.
- Đổi enum value có thể làm client cũ không parse được.
- Đổi nullability hoặc number format có thể phá clients.
- Thay nested object bằng scalar ID là breaking change.

Không để persistence refactor tự thay response. Có thể dùng API version path/header hoặc một contract evolution policy tùy sản phẩm.

DTO giúp chủ động review thay đổi và tạo contract tests.

## 55. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Hướng thay thế |
|---|---|---|
| Controller trả entity trực tiếp | JSON phụ thuộc mapping | Response DTO |
| Bật OSIV để hết lazy exception | SQL phát trong serialization | Fetch plan + map trong transaction |
| Chuyển mọi association sang EAGER | Graph tải rộng, query nặng | Query-specific fetch |
| Gọi Hibernate.initialize() cho mọi field | Tải graph quá lớn | Chọn fields/DTO |
| Dùng @JsonIgnore để xử lý mọi relation | API field biến mất ngoài ý muốn | DTO graph hữu hạn |
| Trả Page<Entity> | Lazy/N+1 trên từng row | Page<Projection> |
| Bind @RequestBody Entity | Mass assignment | Request DTO/command |
| Dùng một DTO cho mọi role | Lộ field dư | DTO theo use case/role |
| Serialize entity trong log | N+1, cycle, PII leak | Safe toString()/structured log |
| Publish entity qua broker | Payload không ổn định | Immutable event DTO |
| DTO mapper truy cập proxy tùy ý | N+1 hoặc lazy failure | Fetch plan trước mapping |
| Fetch nhiều collections cùng lúc | Cartesian rows/bag exception | Nhiều query/projection |

## 56. Quy trình thiết kế endpoint đọc

**Bước 1 — Xác định contract.** Client cần những fields nào? Role nào được xem? Có phân trang không?

**Bước 2 — Chọn response DTO.** Chỉ đưa fields được phép công bố; tránh associations lồng vô hạn.

**Bước 3 — Chọn data access.** Projection nếu chỉ cần columns; EntityGraph/fetch query nếu cần domain entity và associations.

**Bước 4 — Xác định transaction.** Tải và map DTO trong service transaction, tránh lazy access ở controller/serializer.

**Bước 5 — Kiểm tra SQL.** Query count, joins, indexes, pagination và N+1.

**Bước 6 — Kiểm tra security.** Tenant/ownership/field-level authorization và sensitive data.

**Bước 7 — Kiểm tra JSON.** Contract, nullability, cycles, payload size, enum/time/number formats.

**Bước 8 — Test OSIV off.** Endpoint phải trả DTO đầy đủ mà không cần Session mở trong quá trình Jackson serialize.

## 57. Quy trình thiết kế endpoint ghi

**Bước 1 — Tạo request DTO** chỉ gồm những fields client được phép gửi.

**Bước 2 — Validate input** ở Bean Validation và business layer.

**Bước 3 — Load managed entity** trong transaction hiện tại bằng ID đã được kiểm tra quyền.

**Bước 4 — Gọi domain methods** thay vì bind toàn bộ JSON lên entity.

**Bước 5 — Kiểm tra invariants** như tenant, ownership, version, status transitions và uniqueness.

**Bước 6 — Flush/commit** và xử lý constraint/concurrency errors đúng contract.

**Bước 7 — Map response DTO** nếu endpoint trả kết quả.

Không dùng response entity làm input cho request tiếp theo rồi kỳ vọng mọi field đều được phép ghi.

## 58. Sơ đồ quyết định

```text
                   API cần trả dữ liệu persistence?
                                |
                                v
                       Trả entity trực tiếp?
                                |
                                v
                    Có lazy associations / cycles /
                     internal or sensitive fields?
                           /             \
                         CÓ               KHÔNG
                          |                 |
                          v                 v
                   Response DTO       Entity có thực sự
                          |            là API contract?
                          |              /       \
                          |            KHÔNG      CÓ
                          |              |         |
                          |              v         v
                          |         DTO vẫn là   Kiểm tra
                          |         lựa chọn rõ  serializer,
                          |                      security và tests
                          v
                  Chọn fetch strategy
                    /       |       \
                   v        v        v
               Projection EntityGraph JOIN FETCH
                   \        |        /
                    \       |       /
                     v      v      v
                Map DTO trong transaction
                            |
                            v
                  Transaction kết thúc
                            |
                            v
                 Jackson serialize DTO
                            |
                            v
              Contract/security/query-count tests
```

## 59. Tổng kết

Trả entity Hibernate trực tiếp qua API khiến Jackson phụ thuộc vào persistence mapping và có thể duyệt toàn bộ object graph. Getter truy cập association lazy có thể phát SQL trong lúc serialize, tạo N+1 hoặc ném LazyInitializationException khi Session đã đóng. Quan hệ hai chiều có thể tạo vòng lặp JSON; fields nội bộ, PII, tenant metadata hoặc trạng thái đặc quyền có thể bị expose. Khi nhận JSON vào entity, mass assignment còn có thể cho client sửa những thuộc tính họ không được quyền thay đổi.

Giải pháp chính là tách **request DTO**, **response DTO** và **entity**. Dùng DTO projection cho dữ liệu scalar/list/report; dùng EntityGraph hoặc fetch join khi cần entity và associations; map sang DTO trong service transaction. Sau đó controller trả DTO để Jackson serialize mà không cần Hibernate Session. Batch fetching và query tuning có thể giảm N+1 nhưng không thay thế response contract.

OSIV, Jackson Hibernate modules và các annotations như `@JsonIgnore` có thể hữu ích trong một số tình huống, nhưng không tự giải quyết authorization, fetch plan, API versioning hay field exposure. Hãy kiểm thử với OSIV tắt, dữ liệu có quan hệ thật, query count, JSON contract, mass assignment và tenant isolation.

**Nguyên tắc cần nhớ:** Hibernate entity là mô hình persistence; API response là hợp đồng với client. Chọn dữ liệu được tải và được công bố trong service, rồi trả một DTO hữu hạn, thay vì để JSON serializer quyết định ứng dụng sẽ truy vấn và tiết lộ những gì.
