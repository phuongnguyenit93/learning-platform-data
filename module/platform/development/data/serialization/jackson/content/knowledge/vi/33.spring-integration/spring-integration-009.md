# Kiểm soát entity ORM và quan hệ tải chậm ở biên JSON

Trong ứng dụng Spring dùng JPA/Hibernate, entity là mô hình lưu trữ và quản lý vòng đời dữ liệu. JSON response lại là hợp đồng giao tiếp với client. Hai mô hình này có mục đích khác nhau. Nếu controller trả trực tiếp entity, Jackson có thể truy cập getter của quan hệ lazy, khiến Hibernate chạy thêm SQL trong lúc serialize, phát sinh N+1 query, lỗi LazyInitializationException hoặc vô tình công khai dữ liệu nội bộ.

Cách kiểm soát đáng tin cậy là thiết kế DTO cho request/response, xác định dữ liệu cần tải ở repository/service, ánh xạ entity sang DTO trong một transaction có chủ đích rồi để Jackson serialize DTO. DTO không tự làm cho truy vấn hiệu quả; mapper vẫn có thể kích hoạt lazy loading nếu đọc quan hệ chưa được fetch. Vì vậy cần phối hợp ba phần: **fetch plan**, **ranh giới transaction** và **hợp đồng JSON**.

Bài học này giải thích cách Jackson tương tác với entity ORM và lazy relationship trong Spring, các lựa chọn fetch dữ liệu, cách tránh N+1 và vòng tham chiếu, vai trò của Hibernate Jackson module, cùng cách kiểm thử cả JSON lẫn hành vi truy vấn.

## 1. Entity ORM và JSON response giải quyết hai bài toán khác nhau

Entity JPA thường mô tả dữ liệu được quản lý bởi persistence context:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    private String displayName;

    private String email;

    private String passwordHash;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<Order> orders = new ArrayList<>();

    // Getters and setters
}
```

Entity có thể chứa:

- Quan hệ tới entity khác.
- Collection được Hibernate quản lý.
- Proxy đại diện cho association chưa tải.
- Field phục vụ persistence, audit hoặc optimistic locking.
- Getter có thể truy cập database thông qua persistence context.
- Dữ liệu nội bộ không dành cho client.

JSON response cần một cấu trúc rõ ràng, ổn định và chỉ chứa dữ liệu mà endpoint công bố. Ví dụ:

```json
{
  "id": 42,
  "displayName": "Nguyen An",
  "email": "an@example.com",
  "orderCount": 3
}
```

Response này không cần serialize toàn bộ orders, password hash, trạng thái Hibernate hay các quan hệ ngược.

Nếu trả entity trực tiếp, hình dạng JSON có thể bị ảnh hưởng bởi thay đổi trong entity, getter, mapping ORM hoặc cấu hình Jackson. Thêm một quan hệ JPA có thể làm response thay đổi dù hợp đồng API không có ý định thay đổi.

## 2. Điều gì xảy ra khi Jackson serialize một entity có quan hệ lazy?

Jackson Databind thường đọc property thông qua accessor/getter hoặc field visibility đã cấu hình. Với entity Hibernate, getter của một association lazy có thể trả về proxy hoặc persistent collection.

Ví dụ:

```java
Customer customer = customerRepository.findById(id)
    .orElseThrow();

return customer;
```

Controller trả entity:

```java
@GetMapping("/customers/{id}")
public Customer getCustomer(@PathVariable Long id) {
    return customerService.findById(id);
}
```

Khi Spring MVC ghi response, Jackson bắt đầu đọc các property. Nếu serializer truy cập customer.getOrders(), Hibernate có thể cần chạy SQL để tải collection.

Luồng có thể xảy ra:

```text
Controller trả Customer entity
          │
          ▼
Spring MVC chọn HttpMessageConverter
          │
          ▼
Jackson đọc getter / property
          │
          ▼
customer.getOrders()
          │
          ▼
Hibernate kiểm tra persistent collection
          │
          ├── Đã khởi tạo: dùng dữ liệu trong bộ nhớ
          │
          └── Chưa khởi tạo: cần truy vấn database
                         │
                         ▼
                  SELECT orders ...
          │
          ▼
Jackson tiếp tục serialize từng Order
```

Việc serialize lúc này không còn là chuyển object có sẵn thành JSON đơn thuần. Nó có thể kéo theo truy cập database, phụ thuộc trạng thái session và làm thay đổi latency của endpoint.

Nếu session đã đóng, truy cập proxy chưa khởi tạo có thể ném LazyInitializationException. Nếu session vẫn mở, query có thể chạy âm thầm trong lúc response được ghi.

## 3. Lazy loading không phải lỗi; tải dữ liệu sai thời điểm mới là vấn đề

FetchType.LAZY cho phép ORM trì hoãn việc tải association cho tới khi ứng dụng thực sự cần dữ liệu. Đây là cơ chế hữu ích để tránh luôn tải toàn bộ object graph.

Ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Một Order có thể được tải mà chưa cần toàn bộ Customer. Khi service chỉ cần order.getTotal(), việc tải customer có thể là không cần thiết.

Vấn đề xuất hiện khi một lớp khác vô tình truy cập quan hệ:

- Jackson serialize entity và gọi getter.
- Logging gọi toString() có chứa association.
- Debugger mở collection trong lúc session còn hoạt động.
- Mapper chuyển entity sang DTO nhưng đọc cả quan hệ không cần thiết.
- Template hoặc JSON view truy cập property trong lúc render.

Do đó, lazy loading nên được kích hoạt trong tầng ứng dụng có chủ đích, nơi có thể nhìn thấy truy vấn và transaction. Không nên để việc serialize response quyết định dữ liệu nào được truy vấn.

## 4. N+1 query khi serialize collection

Giả sử endpoint trả danh sách 50 khách hàng. Mỗi khách hàng có quan hệ lazy tới orders.

Truy vấn ban đầu:

```sql
SELECT c.id, c.display_name, c.email
FROM customers c;
```

Sau đó Jackson truy cập getOrders() của từng customer. Hibernate có thể phát sinh một truy vấn cho mỗi khách hàng:

```sql
SELECT o.*
FROM orders o
WHERE o.customer_id = ?;
```

Tổng số query có thể gần:

```text
1 query lấy customers
+ 50 query lấy orders
= 51 query
```

Đây là N+1 query problem. Endpoint có thể chạy tốt với một khách hàng trong local test nhưng chậm đáng kể khi trả danh sách lớn.

N+1 không chỉ xảy ra khi Jackson serialize. Mapper entity-to-DTO, vòng lặp trong service hoặc getter được gọi nhiều lần đều có thể kích hoạt nó. Cần nhìn toàn bộ fetch path thay vì chỉ tìm trong controller.

### 4.1. N+1 có thể bị che giấu bởi Open Session in View

Nếu persistence context còn mở trong lúc response được ghi, lazy loading có thể thành công nên endpoint không báo lỗi. Điều này khiến vấn đề khó nhận ra: JSON vẫn đúng nhưng số SQL query tăng theo số entity.

Vì vậy, kiểm thử chỉ xác nhận status 200 và JSON body là chưa đủ. Với endpoint có quan hệ lazy, cần kiểm tra số truy vấn hoặc SQL thực tế trên tập dữ liệu nhiều bản ghi.

## 5. Dùng DTO làm ranh giới JSON

DTO định nghĩa chính xác những gì API cần trả:

```java
public record CustomerResponse(
    Long id,
    String displayName,
    String email,
    int orderCount
) {}
```

Mapper:

```java
public CustomerResponse toResponse(Customer customer) {
    return new CustomerResponse(
        customer.getId(),
        customer.getDisplayName(),
        customer.getEmail(),
        customer.getOrders().size()
    );
}
```

DTO giúp kiểm soát JSON shape, nhưng ví dụ trên vẫn truy cập getOrders(). Nếu collection chưa được fetch, mapping có thể kích hoạt lazy query. Với danh sách nhiều customer, mapper này vẫn có thể gây N+1.

**DTO tách hợp đồng JSON khỏi entity, còn fetch plan quyết định truy vấn cần thiết.** Hai việc này phải được thiết kế cùng nhau.

Nếu endpoint chỉ cần số lượng order, có thể lấy count bằng query riêng hoặc projection thay vì tải toàn bộ collection chỉ để gọi size().

## 6. Map entity sang DTO trong transaction có chủ đích

Một mẫu thường dùng trong Spring:

```java
@Service
@RequiredArgsConstructor
public class CustomerService {

    private final CustomerRepository customerRepository;
    private final CustomerMapper customerMapper;

    @Transactional(readOnly = true)
    public CustomerResponse getCustomer(Long id) {
        Customer customer = customerRepository.findById(id)
            .orElseThrow(CustomerNotFoundException::new);

        return customerMapper.toResponse(customer);
    }
}
```

Controller chỉ trả DTO:

```java
@RestController
@RequiredArgsConstructor
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService customerService;

    @GetMapping("/{id}")
    public CustomerResponse getCustomer(@PathVariable Long id) {
        return customerService.getCustomer(id);
    }
}
```

Mapping xảy ra trong transaction service. Sau khi service trả DTO, transaction kết thúc; Jackson serialize DTO không cần mở lazy association của entity.

Tuy nhiên, điều này chỉ an toàn nếu mapper đã truy cập đúng những dữ liệu được fetch. Nếu mapper cần customer.getOrders() mà repository không fetch orders, lazy query vẫn xảy ra trong transaction. Transaction giúp truy cập còn hợp lệ, nhưng không tự ngăn N+1.

Hãy xác định rõ response cần dữ liệu gì rồi xây fetch plan tương ứng.

## 7. Chọn fetch plan bằng EntityGraph

Spring Data JPA hỗ trợ @EntityGraph để khai báo association cần tải cho một repository method.

Ví dụ:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @EntityGraph(attributePaths = {"orders"})
    Optional<Customer> findWithOrdersById(Long id);
}
```

Service:

```java
@Transactional(readOnly = true)
public CustomerResponse getCustomer(Long id) {
    Customer customer = customerRepository
        .findWithOrdersById(id)
        .orElseThrow(CustomerNotFoundException::new);

    return customerMapper.toResponse(customer);
}
```

EntityGraph làm rõ nhu cầu fetch tại query boundary. Cách Hibernate triển khai cụ thể phụ thuộc mapping, provider và query. Hãy xem SQL thực tế để biết association được tải bằng join hay truy vấn bổ sung.

Có thể dùng named entity graph nếu fetch plan được chia sẻ:

```java
@NamedEntityGraph(
    name = "Customer.withOrders",
    attributeNodes = @NamedAttributeNode("orders")
)
@Entity
public class Customer {
    // ...
}
```

và tham chiếu graph trong repository theo cấu hình phù hợp.

Không nên đưa mọi quan hệ vào một entity graph mặc định. Mỗi endpoint nên tải đúng phần dữ liệu cần dùng; graph quá rộng có thể tạo join lớn, dữ liệu trùng lặp hoặc tăng bộ nhớ.

## 8. Dùng JOIN FETCH khi cần kiểm soát query

JPQL JOIN FETCH có thể tải association cùng entity gốc:

```java
@Query("""
    select distinct c
    from Customer c
    left join fetch c.orders
    where c.id = :id
    """)
Optional<Customer> findWithOrders(@Param("id") Long id);
```

Khi cần một customer cùng orders, fetch join có thể tránh truy vấn bổ sung lúc mapper đọc collection.

Cần lưu ý:

- left join fetch giữ entity gốc ngay cả khi collection không có phần tử.
- distinct có thể cần để loại duplicate root entity trong kết quả object.
- Join collection có thể nhân số hàng SQL theo số phần tử.
- Fetch nhiều collection đồng thời có thể tạo Cartesian product hoặc gặp giới hạn như multiple bag fetch tùy mapping/provider.
- Fetch join collection kết hợp pagination có thể không hoạt động như mong đợi hoặc khiến Hibernate phải xử lý phân trang trong bộ nhớ tùy phiên bản/cấu hình.

Hãy dùng fetch join theo nhu cầu cụ thể và kiểm tra SQL, số hàng và kế hoạch thực thi.

## 9. Cẩn thận khi phân trang với collection lazy

Một endpoint thường cần danh sách khách hàng có phân trang:

```java
Page<Customer> page = customerRepository.findAll(pageable);
```

Nếu thêm fetch join cho collection orders vào query phân trang, database có thể phân trang trên các hàng join thay vì trên customer root. Một customer có nhiều order sẽ làm số hàng tăng và kết quả page không còn đúng như mong đợi.

Các cách xử lý thường gặp:

1. Phân trang customer trước, sau đó tải dữ liệu cần thiết cho tập ID của trang.
2. Dùng batch fetching để giảm số query khi đọc association.
3. Dùng projection query lấy đúng field cần cho response.
4. Dùng query riêng để lấy aggregate như order count.
5. Tránh tải collection lớn nếu endpoint chỉ cần summary.

Ví dụ hai bước:

```java
Page<Customer> page = customerRepository.findAll(pageable);

List<Long> ids = page.getContent().stream()
    .map(Customer::getId)
    .toList();

Map<Long, List<OrderSummary>> ordersByCustomer =
    orderRepository.findSummariesByCustomerIds(ids);
```

Sau đó mapper kết hợp customer page với dữ liệu order summary đã tải theo batch. Cần giữ thứ tự customer theo page ban đầu khi ghép kết quả.

## 10. Projection giúp chỉ truy vấn dữ liệu response cần

Nếu endpoint chỉ cần một vài field, không nhất thiết phải tải entity graph.

Interface projection:

```java
public interface CustomerSummary {
    Long getId();
    String getDisplayName();
    String getEmail();
}
```

Repository:

```java
Page<CustomerSummary> findAllProjectedBy(Pageable pageable);
```

Hoặc DTO projection bằng JPQL constructor expression:

```java
@Query("""
    select new com.example.api.CustomerResponse(
        c.id,
        c.displayName,
        c.email,
        count(o.id)
    )
    from Customer c
    left join c.orders o
    where c.id = :id
    group by c.id, c.displayName, c.email
    """)
Optional<CustomerResponse> findCustomerResponse(@Param("id") Long id);
```

Projection có thể giảm dữ liệu tải và tránh proxy association không cần thiết. Với DTO projection, query trả thẳng response data, không cần entity mapping cho endpoint đọc đơn giản.

Không phải mọi projection đều tự động tối ưu. Nested projection hoặc getter truy cập association vẫn có thể dẫn tới query bổ sung tùy cách Spring Data/Hibernate triển khai. Kiểm tra SQL và chọn projection phẳng khi cần kiểm soát chính xác.

## 11. Batch fetching là công cụ giảm N+1, không thay thế fetch plan

Nếu ứng dụng cần lazy-load cùng một association cho nhiều entity, batch fetching có thể gom nhiều ID vào một số ít query.

Có thể cấu hình theo association:

```java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<Order> orders;
```

Hoặc dùng cấu hình Hibernate phù hợp trong application properties:

```properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
```

Khi nhiều collection/proxy được truy cập, Hibernate có thể tải theo nhóm thay vì một query cho từng entity.

Batch size là tham số cần đo và tùy database/driver. Batch fetching không đảm bảo chỉ còn một query, cũng không có nghĩa mọi association phải được tải. Nó giảm chi phí của một số pattern lazy loading, nhưng DTO/fetch plan vẫn cần rõ ràng.

## 12. Jackson có thể kích hoạt truy vấn qua getter

Một lý do không nên trả entity là việc Jackson truy cập property có thể không hiển nhiên trong code controller.

Ví dụ:

```java
public class Customer {

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<Order> orders;

    public List<Order> getOrders() {
        return orders;
    }
}
```

Khi Jackson nhìn thấy getter, nó có thể xem orders là property cần serialize. Việc gọi getter có thể khiến Hibernate khởi tạo collection nếu session còn mở.

Ngay cả khi application code không gọi getOrders(), serializer có thể gọi nó. Vì vậy, không thể kết luận endpoint không chạy SQL bổ sung chỉ bằng cách đọc controller/service.

DTO giải quyết vấn đề contract. Fetch plan và SQL test giải quyết vấn đề truy vấn.

## 13. Vòng tham chiếu hai chiều có thể gây serialize đệ quy

Entity relationship thường có liên kết hai chiều:

```java
@Entity
public class Customer {

    @OneToMany(mappedBy = "customer")
    private List<Order> orders;
}

@Entity
public class Order {

    @ManyToOne
    private Customer customer;
}
```

Đường object graph:

```text
Customer
  └── orders[]
        └── customer
              └── orders[]
                    └── customer
                          ...
```

Nếu Jackson serialize toàn bộ getter, nó có thể đi qua vòng lặp và báo lỗi nesting/đệ quy, hoặc lặp dữ liệu rất lớn.

Có một số annotation xử lý vòng tham chiếu:

- @JsonManagedReference và @JsonBackReference.
- @JsonIdentityInfo.
- @JsonIgnore.

Ví dụ:

```java
public class Customer {

    @JsonManagedReference
    private List<Order> orders;
}

public class Order {

    @JsonBackReference
    private Customer customer;
}
```

Các annotation này có thể hữu ích trong một số mô hình JSON, nhưng vẫn gắn wire behavior vào entity persistence. Chúng không giải quyết lazy loading, N+1, dữ liệu nhạy cảm hoặc việc entity thay đổi làm response thay đổi.

DTO thường rõ hơn: CustomerResponse có thể chứa danh sách OrderSummary, trong khi OrderSummary không chứa lại toàn bộ customer.

## 14. @JsonIgnore không phải chiến lược API tổng thể

Có thể đánh dấu association không serialize:

```java
@JsonIgnore
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<Order> orders;
```

Điều này có thể ngăn Jackson truy cập association trong response. Tuy nhiên:

- Property bị ẩn khỏi JSON ở mọi endpoint dùng mapper/annotation đó.
- Một endpoint khác có thể cần orders nhưng không thể bật lại một cách rõ ràng nếu vẫn trả entity.
- Annotation Jackson làm entity phụ thuộc thư viện giao tiếp.
- Field nội bộ khác vẫn có thể bị serialize.
- Quan hệ khác vẫn có thể lazy-load hoặc tạo vòng tham chiếu.

Dùng @JsonIgnore có thể là biện pháp tương thích trong code cũ hoặc cho một property nội bộ cụ thể, nhưng không thay thế DTO làm ranh giới API.

## 15. Hibernate Jackson module làm gì?

Jackson có module tích hợp với Hibernate, thường nằm trong nhóm artifact jackson-datatype-hibernate*. Tùy phiên bản Hibernate, artifact và module class khác nhau. Ví dụ với Hibernate 6 có module tương ứng và lớp Hibernate6Module.

Module có thể giúp Jackson hiểu proxy và persistent collection của Hibernate, tránh một số vấn đề khi introspect object ORM. Một số feature cho phép:

- Giữ nguyên hoặc xử lý persistent collection theo cách phù hợp.
- Biểu diễn identifier của proxy chưa tải trong một số cấu hình.
- Điều khiển việc force lazy loading.
- Quy định cách xử lý entity không còn tồn tại khi proxy được truy cập.

Ví dụ đăng ký module trong một cấu hình mapper:

```java
@Bean
ObjectMapper objectMapper(Jackson2ObjectMapperBuilder builder) {
    return builder
        .modulesToInstall(new Hibernate6Module())
        .build();
}
```

Đây chỉ là ví dụ cho stack Hibernate 6 tương thích với module tương ứng. Với Hibernate 5 hoặc Hibernate 7, dùng artifact/module đúng major version. Nếu Spring Boot đã quản lý mapper, hãy tích hợp theo cơ chế cấu hình của ứng dụng để tránh tạo một ObjectMapper thứ hai với behavior khác.

Hibernate module là adapter cho các kiểu Hibernate; nó không tự thiết kế JSON contract và không tự ngăn mọi truy vấn ngoài ý muốn.

## 16. Tránh bật FORCE_LAZY_LOADING một cách tùy tiện

Một feature thường được quan tâm là FORCE_LAZY_LOADING. Khi bật, module có thể yêu cầu khởi tạo proxy/collection lazy trong lúc serialize.

Điều này có vẻ giúp tránh lỗi proxy chưa tải, nhưng có thể làm vấn đề nghiêm trọng hơn:

- Jackson quyết định truy cập database.
- N+1 query xuất hiện trong quá trình ghi response.
- Payload có thể lớn ngoài dự kiến.
- Thời gian response phụ thuộc vào số lượng association.
- Một quan hệ sâu có thể kéo theo nhiều tầng dữ liệu.
- Transaction/session boundary trở nên khó đoán.

Nếu endpoint thực sự cần association, hãy fetch nó ở repository/service và ánh xạ sang DTO. Nếu không cần, đừng để serializer force load.

Một số cấu hình Hibernate module có thể serialize identifier của proxy chưa khởi tạo thay vì toàn bộ object hoặc null. Điều đó cũng là một quyết định wire format: consumer cần biết property này là object đầy đủ hay chỉ là identifier. Không nên thay đổi feature mà không cập nhật contract test.

## 17. Open Session in View và serialization sau transaction

Trong ứng dụng web, Open Session in View (OSIV) có thể giữ persistence context mở trong suốt request. Khi đó, dù service transaction đã kết thúc, Jackson vẫn có thể truy cập lazy association và kích hoạt SQL trong giai đoạn serialize response.

Một luồng dễ gặp:

```text
HTTP request
    │
    ▼
OSIV mở persistence context
    │
    ▼
Controller gọi service
    │
    ▼
Service transaction tải Customer
    │
    ▼
Service trả entity
    │
    ▼
Transaction kết thúc
    │
    ▼
Jackson serialize entity
    │
    ▼
Lazy getter chạy thêm SQL nhờ OSIV
    │
    ▼
HTTP response
```

OSIV có thể làm ứng dụng ít gặp LazyInitializationException, nhưng nó cũng làm truy vấn phát sinh ở giai đoạn khó quan sát hơn. Endpoint có thể vô tình truy cập database trong serializer.

Có thể chủ động tắt OSIV:

```properties
spring.jpa.open-in-view=false
```

Khi đó, code trả entity có association lazy chưa khởi tạo có thể gặp lỗi nếu Jackson truy cập sau khi persistence context đóng. Lỗi này giúp lộ ra fetch boundary chưa rõ.

Tắt OSIV không tự sửa endpoint. Cần chuyển mapping sang DTO trong transaction và fetch dữ liệu cần thiết trước khi trả về. Với một số ứng dụng, OSIV có thể vẫn được giữ theo quyết định kiến trúc; dù vậy, không nên dựa vào nó để định nghĩa fetch plan của API.

## 18. Đừng để mapper DTO vô tình gây N+1

Dùng MapStruct hoặc mapper thủ công không tự động tránh lazy loading.

Ví dụ:

```java
@Mapper(componentModel = "spring")
public interface CustomerMapper {

    CustomerResponse toResponse(Customer customer);
}
```

Nếu mapping có field orders, generated code vẫn phải đọc getter tương ứng. Nếu collection lazy chưa được fetch, Hibernate có thể chạy query.

Với MapStruct, nên khai báo rõ các mapping cần thiết và dùng DTO phù hợp với endpoint. Một mapper có thể có nhiều method:

```java
@Mapper(componentModel = "spring")
public interface CustomerMapper {

    @Mapping(target = "orderCount", ignore = true)
    CustomerSummary toSummary(Customer customer);

    @Mapping(target = "orders", source = "orders")
    CustomerDetail toDetail(Customer customer);
}
```

Service cho summary và detail nên dùng fetch plan riêng. Không dùng một mapper detail cho mọi endpoint nếu danh sách chỉ cần vài field.

Nếu mapper cần orders.size(), nhớ rằng gọi size() trên persistent collection có thể kích hoạt truy vấn hoặc khởi tạo collection tùy mapping/provider. Nếu chỉ cần count, query count(o) thường phù hợp hơn.

## 19. Thiết kế response theo nhu cầu endpoint

Không phải endpoint nào cũng cần cùng một object graph.

| Endpoint | Dữ liệu cần | Cách tải phù hợp |
| --- | --- | --- |
| GET /customers | id, tên, email | Projection hoặc DTO query |
| GET /customers/{id} | thông tin customer | Entity/DTO query theo field |
| GET /customers/{id}/orders | danh sách order có phân trang | Query riêng trên Order |
| GET /customers/{id}/summary | customer và số order | Aggregate query hoặc projection |
| GET /orders/{id} | order và thông tin customer rút gọn | Fetch to-one cần thiết hoặc DTO query |

Một endpoint summary không nên tải toàn bộ orders chỉ để trả order count. Endpoint list không nên serialize toàn bộ quan hệ để tiện tái sử dụng entity. Tách response model theo mục đích giúp kiểm soát cả JSON shape và SQL.

## 20. Ví dụ hoàn chỉnh: endpoint detail với fetch plan rõ ràng

Entity:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    private String displayName;

    private String email;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<Order> orders = new ArrayList<>();

    // Getters and setters
}

@Entity
public class Order {

    @Id
    private Long id;

    private BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    // Getters and setters
}
```

DTO:

```java
public record OrderSummary(
    Long id,
    BigDecimal total
) {}

public record CustomerDetailResponse(
    Long id,
    String displayName,
    String email,
    List<OrderSummary> orders
) {}
```

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @EntityGraph(attributePaths = "orders")
    Optional<Customer> findDetailById(Long id);
}
```

Mapper:

```java
@Component
public class CustomerMapper {

    public CustomerDetailResponse toDetail(Customer customer) {
        List<OrderSummary> orders = customer.getOrders().stream()
            .map(order -> new OrderSummary(
                order.getId(),
                order.getTotal()
            ))
            .toList();

        return new CustomerDetailResponse(
            customer.getId(),
            customer.getDisplayName(),
            customer.getEmail(),
            orders
        );
    }
}
```

Service:

```java
@Service
@RequiredArgsConstructor
public class CustomerService {

    private final CustomerRepository repository;
    private final CustomerMapper mapper;

    @Transactional(readOnly = true)
    public CustomerDetailResponse getDetail(Long id) {
        Customer customer = repository.findDetailById(id)
            .orElseThrow(CustomerNotFoundException::new);

        return mapper.toDetail(customer);
    }
}
```

Controller:

```java
@RestController
@RequiredArgsConstructor
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    @GetMapping("/{id}")
    public CustomerDetailResponse getDetail(@PathVariable Long id) {
        return service.getDetail(id);
    }
}
```

Với cấu trúc này:

1. Repository công bố association cần tải cho endpoint detail.
2. Service giữ transaction trong lúc đọc và mapping.
3. Mapper chỉ tạo DTO đã định nghĩa.
4. Controller trả DTO, không trả entity.
5. Jackson serialize DTO mà không cần duyệt ngược object graph Hibernate.

Vẫn cần kiểm tra SQL thực tế: @EntityGraph có thể được thực hiện theo cách khác nhau tùy provider và query. Nếu collection rất lớn, response detail có thể cần phân trang hoặc query riêng thay vì tải toàn bộ.

## 21. Request JSON cũng không nên bind trực tiếp vào entity

Vấn đề không chỉ ở response. Nếu controller nhận JSON rồi bind thẳng vào entity, client có thể gửi property ngoài ý muốn:

```java
@PostMapping("/customers")
public Customer create(@RequestBody Customer customer) {
    return customerRepository.save(customer);
}
```

Payload có thể chứa id, role, passwordHash, trạng thái kiểm duyệt hoặc quan hệ tới entity khác. Việc bind trực tiếp có thể tạo mass assignment và làm persistence model phụ thuộc input client.

Dùng request DTO allowlist:

```java
public record CreateCustomerRequest(
    @NotBlank String displayName,
    @Email String email
) {}
```

Service tạo entity và kiểm soát field do server quản lý:

```java
@Transactional
public CustomerResponse create(CreateCustomerRequest request) {
    Customer customer = new Customer();
    customer.setDisplayName(request.displayName());
    customer.setEmail(request.email());

    Customer saved = customerRepository.save(customer);

    return mapper.toSummary(saved);
}
```

Request DTO và response DTO có thể khác nhau. Đây là cách giữ quyền kiểm soát rõ ràng đối với dữ liệu client được phép gửi và dữ liệu server được phép công bố.

## 22. Không dùng toString() hoặc logging entity để kiểm tra response

Entity có thể có toString() được sinh bởi Lombok hoặc viết thủ công. Nếu toString() bao gồm quan hệ hai chiều, logging có thể:

- Gây đệ quy.
- Kích hoạt lazy loading.
- Ghi ra dữ liệu nhạy cảm.
- Tạo log rất lớn.
- Làm chậm request trong lúc debug.

Với Lombok, cần thận trọng khi dùng @Data trên entity vì annotation này sinh getter, setter, equals/hashCode và toString. Các method được sinh có thể tương tác không tốt với proxy và association.

Có thể loại association khỏi toString, equals và hashCode theo thiết kế entity. Nhưng logging tốt nhất nên ghi identifier và metadata cần thiết thay vì dump toàn bộ entity graph.

Không dùng mapper.writeValueAsString(entity) chỉ để debug nếu việc đó có thể chạy getter và SQL. Dùng DTO hoặc log field scalar được chọn.

## 23. Cách kiểm thử JSON và truy vấn cùng lúc

Một endpoint có thể trả đúng JSON nhưng chạy quá nhiều query. Cần kiểm tra cả hai chiều.

### 23.1. Test JSON contract

Dùng Spring MVC test hoặc MockMvc để xác nhận property công khai:

```java
@Test
void returnsCustomerSummaryWithoutInternalFields() throws Exception {
    mockMvc.perform(get("/customers/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.displayName").value("Nguyen An"))
        .andExpect(jsonPath("$.passwordHash").doesNotExist());
}
```

Test nên xác nhận field cần có, field không được phép có và cấu trúc collection/nested DTO theo hợp đồng.

### 23.2. Test số query

Có thể dùng Hibernate statistics trong integration test nếu ứng dụng bật statistics cho test:

```java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.clear();

CustomerDetailResponse response = customerService.getDetail(42L);

long queryCount = statistics.getPrepareStatementCount();

assertEquals(expectedQueryCount, queryCount);
```

Đây là ví dụ khái niệm. Test thực tế cần kiểm soát setup/cleanup query, flush/clear persistence context và tránh đếm các truy vấn của fixture setup vào phần đo.

Có thể dùng datasource proxy hoặc SQL instrumentation để đếm query và kiểm tra câu SQL. Điều quan trọng là test với nhiều customer/order, vì N+1 thường không lộ ra khi chỉ có một record.

### 23.3. Kiểm tra lazy collection đã được khởi tạo khi mapper cần nó

Trong test tích hợp, có thể dùng Hibernate.isInitialized(...) để quan sát trạng thái proxy/collection:

```java
assertTrue(Hibernate.isInitialized(customer.getOrders()));
```

Chỉ kiểm tra initialized không chứng minh query tối ưu; nó chỉ giúp xác nhận fetch plan đã tải association trước khi mapping. Vẫn cần xem query count và SQL.

## 24. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| LazyInitializationException khi trả JSON | Jackson truy cập association sau khi session đóng | Map sang DTO trong transaction và fetch dữ liệu cần thiết |
| Response 200 nhưng query tăng theo số entity | OSIV giữ session mở và Jackson lazy-load | Đo SQL, dùng DTO và fetch plan rõ |
| N+1 trong mapper | Mapper đọc collection lazy cho từng entity | EntityGraph, batch fetching, projection hoặc query theo batch |
| JSON chứa proxy/field lạ | Entity/proxy được serialize trực tiếp | Trả DTO và dùng Hibernate module chỉ khi cần cho legacy |
| JSON lặp vô hạn hoặc nesting sâu | Quan hệ hai chiều tạo vòng tham chiếu | DTO không chứa back-reference hoặc kiểm soát graph |
| Response thay đổi sau khi thêm quan hệ JPA | Entity shape đang quyết định JSON | Tách public DTO contract |
| Endpoint list tải hàng nghìn child record | Serialize toàn bộ collection | Projection, summary hoặc endpoint collection riêng có pagination |
| Tắt OSIV làm endpoint lỗi | Mapping vẫn phụ thuộc lazy association ngoài transaction | Fetch trong service và map trước khi transaction kết thúc |
| Bật FORCE_LAZY_LOADING làm chậm response | Serializer kích hoạt tải quan hệ | Không force; xác định fetch plan ở repository/service |
| MapStruct vẫn gây N+1 | Generated mapper gọi getter lazy | Thiết kế method DTO theo endpoint và fetch đúng association |
| JsonIgnore làm mất field ở endpoint khác | Entity annotation áp dụng rộng | DTO riêng cho từng response |
| Logging entity làm phát sinh SQL | toString() truy cập association | Log ID/scalar hoặc DTO nhỏ |

## 25. Quy trình thiết kế endpoint có quan hệ ORM

Khi xây dựng endpoint Spring/JPA trả JSON:

1. Xác định chính xác field và nested data client cần.
2. Tạo response DTO phù hợp với endpoint.
3. Xác định association nào phải được tải để tạo DTO.
4. Chọn query, EntityGraph, fetch join, projection hoặc batch fetching.
5. Giữ entity loading và mapping trong transaction có chủ đích.
6. Không để Jackson serialize entity/proxy trực tiếp.
7. Kiểm tra collection lớn có cần pagination hoặc summary không.
8. Kiểm tra quan hệ hai chiều và field nhạy cảm.
9. Quy định OSIV policy rõ ràng.
10. Chỉ đăng ký Hibernate Jackson module nếu có nhu cầu tương thích cụ thể; không bật force lazy loading tùy tiện.
11. Test JSON contract bằng MockMvc hoặc contract test.
12. Test query count/SQL với tập dữ liệu nhiều record.
13. Test khi persistence context đã đóng để bảo đảm response DTO không còn phụ thuộc entity.
14. Theo dõi query, latency và payload size trên workload thực tế.

## 26. Bài thực hành tổng hợp

Xây dựng API khách hàng có Customer và Order với quan hệ một-nhiều.

Entity:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String displayName;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<Order> orders = new ArrayList<>();
}

@Entity
public class Order {
    @Id
    private Long id;

    private BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

Thực hiện:

1. Tạo endpoint trả Customer entity trực tiếp và quan sát JSON.
2. Kiểm tra getter nào khiến Hibernate tải orders.
3. Thêm nhiều customer để quan sát N+1 query.
4. Tạo CustomerSummary và CustomerDetailResponse.
5. Tạo mapper entity-to-DTO chỉ đọc các field cần thiết.
6. Dùng @EntityGraph hoặc fetch join cho endpoint detail.
7. Tạo projection query cho endpoint list.
8. Dùng query count riêng nếu response chỉ cần số order.
9. Chuyển mapping sang service @Transactional(readOnly = true).
10. Trả DTO từ controller và kiểm tra response vẫn serialize được sau khi transaction kết thúc.
11. Thử tắt OSIV và xác nhận endpoint DTO hoạt động.
12. Thử bật/tắt Hibernate Jackson module trên một endpoint legacy để quan sát behavior của proxy.
13. Không bật FORCE_LAZY_LOADING nếu chưa chứng minh đó là yêu cầu.
14. Kiểm tra vòng tham chiếu Customer–Order.
15. Viết MockMvc test cho JSON field được phép và field nội bộ bị loại.
16. Viết integration test đếm SQL với nhiều customer/order.
17. Thử phân trang và xác nhận query không fetch join collection sai cách.
18. So sánh số query, thời gian và payload size trước/sau khi dùng DTO/fetch plan.

Bài thực hành hoàn thành khi response JSON có cấu trúc ổn định, chỉ chứa dữ liệu được phép, không phụ thuộc lazy proxy sau transaction và số truy vấn không tăng tuyến tính ngoài dự kiến theo số entity.

## 27. Nguyên tắc ghi nhớ

- Entity JPA là mô hình persistence; DTO là mô hình giao tiếp JSON.
- Jackson có thể gọi getter và kích hoạt lazy loading trong lúc serialize entity.
- Lazy loading là cơ chế hợp lệ; truy vấn phát sinh ngoài fetch boundary mới khó kiểm soát.
- Trả entity trực tiếp có thể gây N+1, LazyInitializationException, vòng tham chiếu và lộ field nội bộ.
- DTO kiểm soát JSON shape nhưng mapper vẫn có thể kích hoạt lazy query nếu đọc association chưa fetch.
- Tải dữ liệu cần thiết bằng EntityGraph, fetch join, projection hoặc batch fetching theo endpoint.
- Map entity sang DTO trong transaction có chủ đích; sau đó controller trả DTO.
- Cẩn thận fetch join collection cùng pagination và tải nhiều collection cùng lúc.
- OSIV có thể cho phép Jackson chạy SQL trong lúc ghi response; không dùng nó thay cho fetch plan.
- Hibernate Jackson module giúp xử lý proxy/collection nhưng không thay thế DTO hoặc tối ưu query.
- Tránh FORCE_LAZY_LOADING nếu không muốn serializer quyết định truy cập database.
- JsonIgnore, JsonManagedReference và JsonIdentityInfo xử lý một số vấn đề JSON nhưng không thay thế API model riêng.
- Request DTO giúp ngăn bind trực tiếp field quản trị vào entity.
- Test cả JSON contract lẫn SQL query count; một response đúng vẫn có thể chạy N+1.
- Dữ liệu collection lớn cần pagination, summary hoặc endpoint riêng.
- Logging và toString() cũng có thể kích hoạt lazy loading; chỉ log field cần thiết.

Hãy để repository/service quyết định dữ liệu nào được tải, DTO quyết định dữ liệu nào được công bố và Jackson chỉ serialize cấu trúc đã hoàn chỉnh. Khi ba ranh giới này rõ ràng, quan hệ ORM tải chậm không còn âm thầm quyết định hiệu năng hoặc hình dạng JSON của API.
