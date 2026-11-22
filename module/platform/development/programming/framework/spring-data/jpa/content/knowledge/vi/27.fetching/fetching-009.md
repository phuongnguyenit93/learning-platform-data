# Open EntityManager in View, cấu hình open-in-view và đánh đổi

Trong ứng dụng Spring Data JPA chạy trên web, một request thường đi qua controller, service, repository rồi mới tạo response. Entity được tải trong transaction của service có thể chứa các quan hệ lazy chưa được truy vấn. Khi service kết thúc, transaction đã commit và persistence context có thể đã đóng; nếu controller, template hoặc bộ tuần tự JSON tiếp tục truy cập quan hệ lazy, Hibernate có thể ném `LazyInitializationException`.

Open EntityManager in View (OSIV) là cơ chế giữ một `EntityManager` mở trong suốt vòng đời HTTP request. Nhờ đó, một số quan hệ lazy vẫn có thể được tải khi response đang được tạo, kể cả sau khi transaction nghiệp vụ kết thúc. Cơ chế này giúp tránh một số lỗi lazy loading, nhưng cũng có thể che giấu truy vấn database phát sinh ngoài tầng service, tạo N+1 query và làm ranh giới truy cập dữ liệu khó quan sát.

## 1. EntityManager, persistence context và transaction

Ba khái niệm này liên quan chặt chẽ nhưng không đồng nghĩa:

- **EntityManager** là API JPA dùng để tương tác với persistence context và database.
- **Persistence context** theo dõi các entity đang được quản lý, identity của entity, thay đổi được dirty checking và các trạng thái entity.
- **Transaction** xác định phạm vi commit hoặc rollback các thay đổi dữ liệu. Trong ứng dụng Spring, transaction thường được quản lý bởi `@Transactional` và transaction manager.

Một `EntityManager` có thể còn mở trong khi transaction nghiệp vụ đã kết thúc. Đây chính là điều OSIV tận dụng. Mở EntityManager không đồng nghĩa với việc giữ một transaction database mở trong toàn bộ request.

Khi một entity được tải, các thuộc tính cơ bản thường được lấy cùng truy vấn chính. Các quan hệ được cấu hình `FetchType.LAZY` có thể chỉ được tải khi mã ứng dụng truy cập chúng. Ví dụ, `order.getItems()` có thể phát sinh một truy vấn riêng nếu collection chưa được tải.

Nếu persistence context đã đóng tại thời điểm truy cập, provider không còn EntityManager để thực hiện lazy loading và có thể phát sinh `LazyInitializationException`.

## 2. OSIV hoạt động trong vòng đời HTTP request như thế nào?

Trong môi trường Spring MVC, OSIV thường được triển khai bằng filter hoặc interceptor. Cơ chế này mở EntityManager trước khi xử lý request, gắn nó với thread hiện tại, rồi đóng nó khi request hoàn tất.

Một luồng điển hình:

1. HTTP request đi vào filter/interceptor của OSIV.
2. OSIV mở EntityManager và gắn nó với request thread.
3. Controller gọi service có `@Transactional`.
4. Transaction manager sử dụng EntityManager đang gắn với thread, bắt đầu transaction cho phương thức service.
5. Repository thực hiện truy vấn; service xử lý nghiệp vụ và có thể trả về entity.
6. Khi phương thức service kết thúc, transaction commit hoặc rollback. EntityManager do OSIV quản lý vẫn có thể còn mở.
7. Controller, view template hoặc JSON serializer truy cập thuộc tính lazy. Nếu cần, JPA provider có thể phát sinh thêm truy vấn.
8. Khi request kết thúc, OSIV tháo EntityManager khỏi thread và đóng nó.

Sơ đồ rút gọn:

```text
HTTP request
    |
    v
OSIV: mở EntityManager
    |
    v
Controller
    |
    v
Service @Transactional
    |       Repository / JPA
    |       truy vấn và thay đổi dữ liệu
    v
Commit hoặc rollback transaction
    |
    v
Tạo response / render / JSON serialization
    |       Có thể phát sinh lazy query khi OSIV còn mở
    v
OSIV: đóng EntityManager
    |
    v
HTTP response hoàn tất
```

Sau khi transaction service kết thúc, các truy vấn lazy phát sinh trong lúc render response không tự động nằm trong transaction nghiệp vụ vừa commit. Việc chúng có được thực thi hay không còn phụ thuộc provider, cách quản lý connection và trạng thái persistence context. Vì vậy, không nên xem OSIV như một cách kéo dài transaction hoặc bảo đảm tính nhất quán giao dịch cho toàn bộ request.

## 3. Cấu hình open-in-view trong Spring Boot

Spring Boot cung cấp thuộc tính `spring.jpa.open-in-view` để bật hoặc tắt OSIV cho ứng dụng web có JPA.

Trong nhiều cấu hình ứng dụng web Spring Boot, OSIV được bật mặc định nếu không khai báo thuộc tính này. Khi bật, Spring Boot đăng ký cơ chế mở EntityManager theo request. Để tránh phụ thuộc vào mặc định giữa các môi trường, nên đặt giá trị rõ ràng trong cấu hình ứng dụng.

**Tắt OSIV** trong `application.properties`:

```properties
spring.jpa.open-in-view=false
```

Hoặc trong `application.yml`:

```yaml
spring:
  jpa:
    open-in-view: false
```

Nếu muốn bật tường minh:

```properties
spring.jpa.open-in-view=true
```

Đây là thuộc tính cấu hình của Spring Boot, không phải thuộc tính chuẩn của JPA. Nó có ý nghĩa trong ứng dụng web mà Spring Boot cấu hình OSIV. Với ứng dụng Spring MVC tự cấu hình không dùng auto-configuration của Boot, OSIV có thể được đăng ký thủ công bằng `OpenEntityManagerInViewFilter` hoặc `OpenEntityManagerInViewInterceptor`.

Khi chuyển từ `true` sang `false`, các đoạn code đang vô tình truy cập quan hệ lazy sau khi service kết thúc có thể bắt đầu lỗi. Vì vậy, hãy kiểm tra controller, mapper, serializer và view template trước hoặc trong quá trình thay đổi cấu hình.

## 4. Ví dụ về lỗi lazy loading khi tắt OSIV

Giả sử có entity `Order` tham chiếu đến `Customer` bằng quan hệ lazy:

```java
@Entity
public class Order {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

Service chỉ tải đơn hàng rồi trả entity:

```java
@Service
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(readOnly = true)
    public Order findOrder(Long id) {
        return orderRepository.findById(id)
                .orElseThrow();
    }
}
```

Controller tiếp tục truy cập quan hệ:

```java
@RestController
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/{id}")
    public String getOrder(@PathVariable Long id) {
        Order order = orderService.findOrder(id);
        return order.getCustomer().getName();
    }
}
```

Khi OSIV tắt, transaction của `findOrder()` kết thúc trước khi controller gọi `getCustomer().getName()`. Nếu quan hệ customer chưa được tải, truy cập này có thể ném `LazyInitializationException`.

Khi OSIV bật, truy cập có thể thành công vì EntityManager còn mở trong request. Tuy nhiên, truy vấn customer được thực hiện tại controller hoặc trong quá trình tạo response, khiến tầng trình bày phát sinh SQL mà người viết service không nhìn thấy trực tiếp.

Cách sửa tốt là xác định dữ liệu response cần dùng rồi tải dữ liệu đó trong transaction của service. Không nên bật OSIV chỉ để che đi một quan hệ chưa được tải đúng chỗ.

## 5. Đánh đổi khi bật OSIV

| Lợi ích | Chi phí và rủi ro |
|---|---|
| Giảm lỗi `LazyInitializationException` khi template hoặc serializer truy cập quan hệ lazy. | Truy vấn database có thể phát sinh ở controller, view hoặc quá trình serialize response. |
| Có thể dùng entity trực tiếp trong một số luồng render server-side. | Khó nhận biết và kiểm soát số lượng SQL; dễ phát sinh N+1 query. |
| Giảm nhu cầu khai báo fetch cho một số quan hệ chỉ được truy cập ở bước render. | Response có thể chứa dữ liệu được tải ở các thời điểm khác nhau, sau transaction nghiệp vụ. |
| Có thể thuận tiện khi ứng dụng cũ được xây dựng dựa trên lazy loading ở tầng view. | Tầng trình bày phụ thuộc vào entity và cấu trúc persistence; thay đổi model có thể ảnh hưởng API hoặc giao diện. |
| Giảm lỗi tức thời khi chuyển một số code cũ sang JPA. | Lỗi truy vấn hoặc serialize có thể xuất hiện sau khi service đã commit, làm request thất bại dù nghiệp vụ đã ghi dữ liệu. |

### 5.1. Truy vấn ẩn và N+1

Một trong những rủi ro quan trọng nhất là truy vấn ẩn. Một service chỉ thực hiện một truy vấn lấy danh sách đơn hàng, nhưng JSON serializer sau đó đọc customer của từng đơn hàng. Nếu mỗi customer chưa được tải, provider có thể thực hiện thêm một truy vấn cho từng order.

Ví dụ về số lượng truy vấn có thể phát sinh:

```text
1 truy vấn: lấy 100 đơn hàng
100 truy vấn: tải customer cho từng đơn hàng
--------------------------------------------
101 truy vấn
```

Số lượng thực tế phụ thuộc vào quan hệ, cache và cấu hình fetch của provider. Dù vậy, ví dụ cho thấy một endpoint có thể trở nên chậm khi serializer truy cập collection hoặc quan hệ lazy trên nhiều entity.

OSIV không tự tạo N+1 trong mọi trường hợp, nhưng nó cho phép lazy loading tiếp tục ở giai đoạn tạo response, nơi các truy vấn phát sinh khó được dự đoán hơn.

### 5.2. Transaction và tính nhất quán của response

Service có thể đọc và xử lý dữ liệu trong một transaction, sau đó commit. Khi serializer tiếp tục tải một quan hệ lazy, truy vấn mới có thể chạy sau transaction đó. Nếu dữ liệu liên quan thay đổi giữa hai thời điểm, response có thể ghép dữ liệu từ các thời điểm khác nhau.

Mức độ ảnh hưởng phụ thuộc isolation level, database và cách provider thực thi truy vấn. OSIV không cung cấp một snapshot nhất quán xuyên suốt request. Nếu nghiệp vụ cần dữ liệu nhất quán, hãy tải các phần dữ liệu cần thiết trong cùng transaction và tạo response từ kết quả đó.

### 5.3. Tài nguyên và độ phức tạp vòng đời

OSIV giữ persistence context tồn tại lâu hơn transaction service. Entity được quản lý và các proxy lazy có thể tồn tại đến cuối request. Điều này làm vòng đời persistence khó quan sát hơn và có thể khiến các truy vấn phát sinh muộn.

Không nên mặc định rằng OSIV luôn giữ một JDBC connection suốt toàn bộ HTTP request. Thời điểm lấy và trả connection phụ thuộc JPA provider, connection handling mode và transaction. Tuy nhiên, việc cho phép truy vấn tiếp tục ở giai đoạn render vẫn có thể làm tăng thời gian sử dụng database và khiến tải SQL khó dự báo.

### 5.4. Entity bị lộ ra response

Trả entity trực tiếp từ controller có thể khiến serializer:

- Đọc các quan hệ lazy và phát sinh truy vấn.
- Đi qua quan hệ hai chiều, gây vòng lặp serialize hoặc cần cấu hình xử lý đặc biệt.
- Vô tình trả thêm trường nội bộ khi entity thay đổi.
- Tạo API gắn chặt với cấu trúc database và mô hình persistence.

DTO giúp xác định rõ dữ liệu công khai của response và tránh để quá trình serialize quyết định truy vấn database.

## 6. Cách thay thế OSIV bằng fetch dữ liệu tường minh

Khi tắt OSIV, service cần tải đầy đủ dữ liệu mà response sẽ sử dụng trước khi transaction kết thúc. Có một số cách phổ biến.

### 6.1. Dùng JOIN FETCH

Repository có thể tải entity cùng quan hệ cần thiết trong một truy vấn:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @Query("""
        select o
        from Order o
        join fetch o.customer
        where o.id = :id
        """)
    Optional<Order> findByIdWithCustomer(@Param("id") Long id);
}
```

Service dùng phương thức repository này trong transaction:

```java
@Transactional(readOnly = true)
public OrderResponse getOrder(Long id) {
    Order order = orderRepository.findByIdWithCustomer(id)
            .orElseThrow();

    return new OrderResponse(
            order.getId(),
            order.getCustomer().getName()
    );
}
```

Vì customer đã được tải trong truy vấn, service có thể đọc tên customer và tạo DTO trước khi transaction kết thúc.

Dùng `left join fetch` thay cho `join fetch` nếu cần giữ lại order ngay cả khi quan hệ customer có thể không tồn tại. Hãy chọn kiểu join phù hợp với tính bắt buộc của quan hệ.

Lưu ý với collection: fetch join nhiều collection cùng lúc có thể tạo tích Descartes và nhân số hàng trong kết quả. Fetch join collection kết hợp phân trang cũng có giới hạn tùy provider; Hibernate có thể phải tải nhiều dữ liệu rồi phân trang trong bộ nhớ hoặc phát cảnh báo. Với danh sách lớn, cân nhắc projection, batch fetching hoặc truy vấn theo từng bước.

### 6.2. Dùng @EntityGraph

Nếu muốn khai báo quan hệ cần tải ngay trên phương thức repository, có thể dùng `@EntityGraph`:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    @EntityGraph(attributePaths = {"customer"})
    Optional<Order> findWithCustomerById(Long id);
}
```

`attributePaths` mô tả các thuộc tính cần được fetch cho truy vấn. Cách provider tạo SQL cụ thể phụ thuộc JPA provider và cấu hình fetch; hãy kiểm tra SQL thực tế khi tối ưu.

### 6.3. Dùng DTO projection

Nếu endpoint chỉ cần một số trường, truy vấn thẳng DTO hoặc projection thường gọn hơn tải toàn bộ entity:

```java
public record OrderSummary(
        Long id,
        String customerName
) {}
```

Một repository có thể dùng constructor expression trong JPQL:

```java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        c.name
    )
    from Order o
    join o.customer c
    where o.id = :id
    """)
Optional<OrderSummary> findSummaryById(@Param("id") Long id);
```

Service trả projection hoặc chuyển thành response DTO. Vì dữ liệu cần thiết đã được truy vấn, serializer không phải đi qua proxy lazy của entity.

Tên package trong constructor expression phải khớp package thực tế của record trong ứng dụng.

### 6.4. Ánh xạ entity sang DTO bên trong transaction

Ngay cả khi repository trả entity, service vẫn có thể ánh xạ sang DTO khi persistence context còn hoạt động:

```java
@Transactional(readOnly = true)
public OrderResponse getOrder(Long id) {
    Order order = orderRepository.findById(id)
            .orElseThrow();

    return new OrderResponse(
            order.getId(),
            order.getCustomer().getName(),
            order.getItems().stream()
                    .map(item -> new OrderItemResponse(
                            item.getProductName(),
                            item.getQuantity()
                    ))
                    .toList()
    );
}
```

Để đoạn code này hoạt động, service phải bảo đảm `customer` và `items` được tải trong transaction, chẳng hạn bằng EntityGraph hoặc truy vấn fetch phù hợp. Chỉ đặt `@Transactional` không tự tải mọi quan hệ lazy; nó chỉ tạo phạm vi để truy vấn được thực hiện khi mã truy cập quan hệ.

`readOnly = true` thể hiện ý định chỉ đọc và có thể giúp transaction manager/provider tối ưu một số thao tác. Nó không thay thế fetch plan và không bảo đảm mọi thay đổi dữ liệu đều bị chặn.

## 7. Chọn fetch strategy theo từng trường hợp

Không nên chuyển tất cả quan hệ sang `FetchType.EAGER` để tránh lỗi lazy loading. Eager loading có thể tải dữ liệu không cần thiết, tạo truy vấn lớn và gây hiệu ứng phụ trên các truy vấn khác.

Một số nguyên tắc lựa chọn:

- Dùng `LAZY` làm lựa chọn phù hợp cho nhiều quan hệ, đặc biệt là collection; yêu cầu truy vấn cụ thể quyết định dữ liệu cần tải.
- Dùng `JOIN FETCH` khi một truy vấn cần lấy một quan hệ rõ ràng.
- Dùng `@EntityGraph` khi muốn mô tả fetch plan tại repository mà không viết lại toàn bộ JPQL.
- Dùng DTO projection khi response chỉ cần một tập trường xác định.
- Dùng batch fetching khi cần tải quan hệ cho nhiều entity mà không muốn thực hiện một truy vấn riêng cho từng entity.
- Với collection lớn, dùng phân trang riêng cho collection hoặc truy vấn theo hai bước thay vì fetch join nhiều collection cùng lúc.

Fetch plan nên dựa trên từng use case. Một màn hình chi tiết có thể cần customer và items; một màn hình danh sách chỉ cần mã đơn, ngày tạo và tên khách hàng. Hai luồng có thể cần hai phương thức repository khác nhau.

## 8. Quy trình chuyển ứng dụng từ OSIV bật sang tắt

Khi ứng dụng hiện đang bật OSIV, hãy chuyển đổi theo từng bước để phát hiện các chỗ đang phụ thuộc vào lazy loading ngoài service:

1. **Liệt kê endpoint và response:** xác định controller trả entity trực tiếp, view template đọc quan hệ hoặc serializer truy cập thuộc tính lazy.
2. **Xác định dữ liệu cần thiết:** với từng use case, ghi rõ trường và quan hệ thực sự xuất hiện trong response.
3. **Chọn fetch plan:** dùng fetch join, EntityGraph, projection hoặc batch fetching tùy hình dạng dữ liệu.
4. **Tạo DTO trong service:** ánh xạ dữ liệu khi transaction còn hoạt động; controller chỉ nhận và trả response.
5. **Tắt OSIV ở môi trường kiểm thử:** đặt `spring.jpa.open-in-view=false` để lỗi truy cập lazy ngoài transaction xuất hiện sớm.
6. **Kiểm tra SQL:** bật log SQL hoặc dùng công cụ quan sát để tìm N+1, truy vấn dư thừa và truy vấn phát sinh khi serialize.
7. **Kiểm thử endpoint:** kiểm tra response, số truy vấn, phân trang, trường hợp quan hệ null và lỗi khi dữ liệu không tồn tại.
8. **Triển khai cấu hình nhất quán:** đặt thuộc tính rõ ràng cho các môi trường để hành vi không phụ thuộc vào mặc định.

Nếu ứng dụng có trang server-side cũ phụ thuộc vào lazy loading trong template, có thể cần chuyển từng trang hoặc giữ OSIV có chủ đích trong giai đoạn chuyển tiếp. Hãy giới hạn các nơi phụ thuộc và đo truy vấn thực tế.

## 9. Kiểm thử và chẩn đoán

Khi tắt OSIV, một số lỗi thường gặp có thể được xử lý theo hướng sau:

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `LazyInitializationException` khi tạo JSON | Serializer đọc quan hệ lazy sau transaction | Tải quan hệ trong service và trả DTO. |
| Endpoint chạy được nhưng phát sinh rất nhiều SELECT | OSIV cho phép lazy loading trong quá trình serialize | Kiểm tra SQL, dùng fetch plan hoặc projection để giảm N+1. |
| Lỗi chỉ xuất hiện ở một endpoint | Endpoint đó trả entity hoặc mapper truy cập quan hệ chưa tải | Tìm đường truy cập thuộc tính lazy và bổ sung dữ liệu vào truy vấn. |
| Trang template lỗi sau khi tắt OSIV | Template truy cập quan hệ sau khi service hoàn tất | Chuẩn bị view model/DTO trong service hoặc tải dữ liệu cần thiết trước khi render. |
| Response chứa dữ liệu liên quan không nhất quán | Các quan hệ được truy vấn ở thời điểm khác nhau | Đọc dữ liệu cần thiết trong transaction phù hợp rồi tạo DTO. |
| Query tăng mạnh sau khi thêm collection vào response | Collection lazy được duyệt cho từng entity | Dùng batch fetching, projection hoặc thiết kế truy vấn theo trang. |

Nên có kiểm thử tích hợp cho cả trường hợp OSIV tắt. Ví dụ, dùng Spring Boot test với thuộc tính `spring.jpa.open-in-view=false`, gọi endpoint bằng MockMvc, rồi xác nhận response chứa đầy đủ dữ liệu mong muốn. Có thể kết hợp thống kê Hibernate hoặc datasource proxy để kiểm tra số lượng truy vấn thay vì chỉ xác nhận HTTP status.

Khi kiểm tra SQL, hãy chú ý cả truy vấn trong service lẫn truy vấn phát sinh khi serialize response. Một endpoint trả HTTP 200 chưa đủ chứng minh fetch plan hiệu quả.

## 10. Checklist khi thiết kế

- [ ] Đã quyết định rõ OSIV bật hay tắt và đặt `spring.jpa.open-in-view` tường minh.
- [ ] Không coi EntityManager mở là transaction database đang mở.
- [ ] Controller và serializer không vô tình quyết định dữ liệu cần truy vấn.
- [ ] Service tải đủ quan hệ cần thiết trước khi transaction kết thúc.
- [ ] Response API dùng DTO hoặc projection phù hợp với hợp đồng API.
- [ ] Fetch plan tránh N+1 và tránh tải quá nhiều dữ liệu.
- [ ] Cân nhắc riêng collection fetch join và phân trang.
- [ ] Có kiểm thử tích hợp chạy với OSIV tắt.
- [ ] Đã kiểm tra SQL thực tế, thời gian response và tính nhất quán dữ liệu.

OSIV là một cơ chế quản lý vòng đời EntityManager theo HTTP request, giúp lazy loading tiếp tục trong giai đoạn tạo response. Nó có thể hữu ích cho một số ứng dụng render server-side hoặc hệ thống cũ, nhưng làm mờ ranh giới truy cập database và khiến truy vấn phát sinh ngoài service. Với API và ứng dụng cần kiểm soát rõ dữ liệu, tắt OSIV, tải dữ liệu theo từng use case và ánh xạ DTO trong transaction thường giúp hành vi dễ dự đoán, kiểm thử và tối ưu hơn.