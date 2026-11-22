# Ẩn quan hệ bằng @RestResource và kiểm soát đường ghi còn lại

Spring Data REST có thể công bố một association như một liên kết và một association resource riêng. Khi client không nên trực tiếp đọc hoặc thay đổi quan hệ đó qua association endpoint, có thể đánh dấu thuộc tính quan hệ bằng @RestResource(exported = false). Tuy nhiên, ẩn association resource không tự động xóa quan hệ trong mô hình JPA, cũng không phải là một chính sách phân quyền hoàn chỉnh. Cần xác định những đường ghi khác còn mở và kiểm soát chúng theo nghiệp vụ.

## 1. Association resource được công bố như thế nào?

Giả sử một đơn hàng có nhiều sản phẩm:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    private Set<Product> items = new LinkedHashSet<>();

    // getters and setters
}
~~~

Nếu repository của PurchaseOrder được công bố qua Spring Data REST, representation của đơn hàng có thể chứa association link:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "items": {
      "href": "/api/orders/42/items"
    }
  }
}
~~~

Client có thể theo href của items để đọc hoặc thay đổi collection association theo các HTTP method mà Spring Data REST hỗ trợ. Với collection association, POST thường thêm URI của phần tử đích; PUT có thể thay thế tập hợp liên kết; DELETE có thể xóa liên kết theo semantics của association resource.

Nếu quan hệ không nên được công bố như một API độc lập, có thể ẩn nó ngay trên persistent property.

## 2. Ẩn quan hệ bằng @RestResource(exported = false)

Đặt @RestResource(exported = false) trên thuộc tính association mà Spring Data REST đang ánh xạ:

~~~java
import org.springframework.data.rest.core.annotation.RestResource;

@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    @RestResource(exported = false)
    private Set<Product> items = new LinkedHashSet<>();

    // getters and setters
}
~~~

Với mapping dùng property access, đặt annotation trên getter tương ứng thay vì field, theo cùng chiến lược truy cập mà JPA đang sử dụng:

~~~java
@ManyToMany
public Set<Product> getItems() {
    return items;
}

@RestResource(exported = false)
public void setItems(Set<Product> items) {
    this.items = items;
}
~~~

Trong ví dụ thực tế, annotation phải được đặt trên persistent association property theo cách Spring Data REST có thể đọc được. Tránh đặt annotation không nhất quán giữa field và accessor khi entity đang dùng một chiến lược JPA access cụ thể.

Khi association được đánh dấu không export:

- Spring Data REST không công bố association resource đó như một đường dẫn REST độc lập.
- Client không được cung cấp association link tương ứng trong HAL representation.
- Quan hệ JPA vẫn tồn tại trong entity mapping và trong cơ sở dữ liệu.
- Repository của entity đích, ví dụ ProductRepository, vẫn có thể được công bố độc lập.
- Service nội bộ vẫn có thể thay đổi quan hệ thông qua entity và repository nếu logic ứng dụng cho phép.

Ví dụ, ẩn items không đồng nghĩa với việc ẩn toàn bộ /api/products. Client vẫn có thể truy cập repository Product nếu repository đó được công bố. Annotation này kiểm soát việc export association, không tự động ẩn entity đích hoặc mọi API có thể tác động tới dữ liệu liên quan.

## 3. Ẩn association không đồng nghĩa khóa mọi đường ghi

Sau khi ẩn association link, cần xem xét các đường ghi khác có thể làm thay đổi cùng dữ liệu. Một quan hệ có thể bị thay đổi gián tiếp qua:

1. **PUT hoặc PATCH trên parent resource.** Nếu representation của PurchaseOrder cho phép binding thuộc tính quan hệ, request cập nhật đơn hàng có thể tác động tới association tùy cấu hình và cách Spring Data REST xử lý property.
2. **Repository collection và item của entity liên quan.** ProductRepository có thể vẫn cho phép POST, PUT hoặc DELETE trên Product. Thao tác đó có thể ảnh hưởng tới quan hệ theo mapping JPA và quy tắc ràng buộc.
3. **Repository method được export.** Các phương thức ghi như save hoặc delete vẫn có thể cung cấp đường ghi cho repository nếu không bị ẩn hoặc giới hạn.
4. **Controller hoặc service tùy chỉnh.** Endpoint do ứng dụng tự xây dựng vẫn có thể sửa association.
5. **Tác vụ nội bộ.** Batch job, message consumer hoặc service khác có thể thay đổi cùng dữ liệu mà không đi qua association resource.

Do đó, không nên kết luận “association đã an toàn để ghi” chỉ vì link không còn xuất hiện trong HAL. Hãy xác định actor nào được phép thay đổi quan hệ và đường HTTP hoặc service nào còn có thể thực hiện thao tác đó.

## 4. Kiểm soát PUT và PATCH trên parent resource

Nếu client được phép cập nhật các trường khác của đơn hàng nhưng không được thay đổi items, cần giới hạn cách cập nhật parent resource. Có thể dùng Spring Security để kiểm soát các HTTP method theo endpoint và quyền của người gọi:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("ORDER_READ")
            .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                .hasAuthority("ORDER_WRITE")
            .requestMatchers(HttpMethod.PATCH, "/api/orders/**")
                .hasAuthority("ORDER_WRITE")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Đây là ví dụ phân quyền theo endpoint. Nếu tất cả người có ORDER_WRITE đều được phép sửa đơn hàng nhưng không được sửa items, chỉ kiểm tra authority ở URL là chưa đủ để phân biệt thuộc tính nào được thay đổi. Khi đó, cần kiểm soát payload hoặc dùng một write API riêng với DTO chỉ chứa những trường được phép cập nhật.

Ví dụ DTO cập nhật thông tin vận chuyển không chứa association items:

~~~java
public record UpdateOrderRequest(
    String shippingNote,
    String deliveryAddress
) {
}
~~~

Controller nhận DTO này và gọi service cập nhật đúng các trường được phép. Vì DTO không nhận danh sách Product, client không thể dùng endpoint này để gửi thay đổi association.

Nếu vẫn cho phép PUT/PATCH mặc định của Spring Data REST trên parent resource, hãy xác định và kiểm soát riêng việc binding association; đừng chỉ dựa vào việc association link đã bị ẩn.

## 5. Ẩn các thao tác ghi ở repository khi cần

Nếu repository không nên nhận thao tác ghi qua Spring Data REST, có thể override phương thức kế thừa và đánh dấu không export:

~~~java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Override
    @RestResource(exported = false)
    <S extends PurchaseOrder> S save(S entity);
}
~~~

Ẩn save có thể làm các luồng ghi dựa trên repository đó qua Spring Data REST không còn khả dụng, bao gồm những thao tác tạo hoặc cập nhật cần lưu entity. Các phương thức khác như delete cũng cần được xem xét riêng nếu không muốn công bố thao tác xóa.

Ví dụ ẩn thao tác xóa theo ID:

~~~java
@Override
@RestResource(exported = false)
void deleteById(Long id);
~~~

Đây là quyết định ở cấp repository method, có phạm vi rộng hơn việc ẩn một association. Nếu chỉ muốn khóa một quan hệ nhưng vẫn cho phép cập nhật các trường đơn hàng khác, không nên ẩn save một cách máy móc; hãy thiết kế write path có DTO và quyền phù hợp.

Nếu cần ẩn toàn bộ repository khỏi Spring Data REST, dùng @RepositoryRestResource(exported = false) trên repository. Điều này không xóa repository bean và không ngăn service nội bộ inject nó, nhưng client không còn sử dụng repository đó như một REST resource được Spring Data REST công bố.

## 6. Tạo write path riêng cho thay đổi association

Khi nghiệp vụ vẫn cần cho phép một số người dùng thêm sản phẩm vào đơn hàng, có thể ẩn association resource mặc định và cung cấp một endpoint riêng. Endpoint này nhận định danh nghiệp vụ, kiểm tra quyền, xác nhận cả hai entity tồn tại và áp dụng quy tắc trước khi cập nhật quan hệ.

Ví dụ request DTO:

~~~java
public record AddOrderItemRequest(Long productId) {
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/order-management/orders")
public class OrderItemController {

    private final OrderService orderService;

    public OrderItemController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{orderId}/items")
    @PreAuthorize("hasAuthority('ORDER_EDIT_ITEMS')")
    public ResponseEntity<Void> addItem(
            @PathVariable Long orderId,
            @RequestBody AddOrderItemRequest request) {

        orderService.addItem(orderId, request.productId());
        return ResponseEntity.noContent().build();
    }
}
~~~

Service thực hiện cập nhật trong transaction:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;
    private final ProductRepository products;

    public OrderService(
            PurchaseOrderRepository orders,
            ProductRepository products) {
        this.orders = orders;
        this.products = products;
    }

    @Transactional
    public void addItem(Long orderId, Long productId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));

        Product product = products.findById(productId)
            .orElseThrow(() -> new EntityNotFoundException("Product not found"));

        // Kiểm tra trạng thái đơn hàng, quyền sở hữu và quy tắc nghiệp vụ tại đây.
        order.getItems().add(product);
    }
}
~~~

Ví dụ trên giả định PurchaseOrder là phía sở hữu quan hệ và collection items có thể được sửa trực tiếp. Nếu mapping dùng owning side khác, hãy cập nhật đúng phía sở hữu và đồng bộ phía inverse nếu ứng dụng cần. Repository hoặc service cũng phải bảo đảm entity được lưu trong transaction theo cấu hình persistence của dự án.

Ưu điểm của write path riêng:

- Chỉ một quyền cụ thể, ví dụ ORDER_EDIT_ITEMS, mới cho phép sửa association.
- Request DTO không cho client gửi tùy ý toàn bộ entity.
- Service có thể kiểm tra đơn hàng còn ở trạng thái cho phép sửa hay không.
- Có thể kiểm tra sản phẩm có thuộc danh mục, kho hoặc tenant phù hợp hay không.
- Có thể ghi audit log và phát sự kiện nghiệp vụ tại đúng thời điểm.

Nếu API chỉ cần đọc association, có thể giữ một endpoint đọc riêng hoặc cung cấp thông tin liên kết phù hợp trong representation khác. Việc ẩn association resource mặc định không buộc ứng dụng phải bỏ toàn bộ khả năng đọc dữ liệu liên quan.

## 7. Kiểm soát cả repository của entity đích

Ẩn association trên PurchaseOrder không tự động ngăn client thay đổi Product qua ProductRepository. Nếu Product được công bố độc lập, client có thể vẫn có các thao tác trên /api/products hoặc /api/products/{id}.

Hãy xác định phạm vi cần bảo vệ:

- Nếu chỉ cần ngăn client thay đổi mối liên kết, bảo vệ write path của PurchaseOrder và association.
- Nếu cần ngăn client sửa dữ liệu Product, kiểm soát POST, PUT, PATCH và DELETE trên ProductRepository.
- Nếu Product chỉ dùng nội bộ, cân nhắc ẩn repository bằng @RepositoryRestResource(exported = false).
- Nếu nhiều nhóm người dùng có quyền khác nhau, dùng Spring Security và kiểm tra quyền ở service theo tài nguyên cụ thể.

Ví dụ, Product có thể vẫn được đọc công khai nhưng thao tác ghi chỉ dành cho PRODUCT_ADMIN. Có thể đặt quyền theo HTTP method trên endpoint Product hoặc ẩn các phương thức ghi của repository, tùy hợp đồng API cần duy trì.

## 8. Quy trình kiểm tra sau khi ẩn association

Sau khi cấu hình @RestResource(exported = false), hãy kiểm tra từng đường truy cập và ghi dữ liệu:

1. GET parent resource, ví dụ /api/orders/42; xác nhận association link items không còn được công bố.
2. Thử truy cập association URL cũ; xác nhận Spring Data REST không còn cung cấp association resource đó.
3. GET Product qua repository riêng nếu Product vẫn được công bố; xác nhận việc ẩn association không làm mất repository đích.
4. Thử PUT/PATCH parent resource với payload chỉ cập nhật trường được phép.
5. Thử payload có chứa items để xác nhận client không thể vượt qua chính sách bằng đường cập nhật parent.
6. Thử POST/PUT/PATCH/DELETE trên repository liên quan theo quyền của từng vai trò.
7. Gọi endpoint ghi riêng nếu có; xác nhận người không có ORDER_EDIT_ITEMS bị từ chối.
8. Đọc lại parent resource và dữ liệu persistence để xác nhận quan hệ chỉ thay đổi qua write path được cho phép.

Khi kiểm tra, dùng cả người dùng được phép và không được phép. Kiểm tra status code cùng dữ liệu sau request; một phản hồi 2xx không đủ chứng minh association được lưu đúng theo quy tắc nghiệp vụ.

## 9. Những nhầm lẫn thường gặp

- **Ẩn link được xem là xóa quan hệ.** Annotation chỉ điều khiển việc công bố association qua Spring Data REST; mapping JPA và dữ liệu quan hệ vẫn tồn tại.
- **Ẩn association được xem là khóa mọi thao tác ghi.** Parent PUT/PATCH, repository method, custom controller và service nội bộ vẫn có thể là đường ghi.
- **Ẩn association được xem là ẩn entity đích.** ProductRepository có thể tiếp tục được công bố độc lập.
- **Chỉ kiểm tra HAL response.** Cần thử trực tiếp các endpoint và payload ghi có thể còn hoạt động.
- **Dùng một quyền chung cho mọi thao tác.** Đọc đơn hàng, sửa trường đơn hàng và thay đổi danh sách sản phẩm có thể cần quyền khác nhau.
- **Quên owning side của JPA.** Cập nhật phía inverse mà không cập nhật owning side có thể không lưu thay đổi vào cơ sở dữ liệu.

@​RestResource(exported = false) là cách gọn để loại một association khỏi bề mặt REST tự động. Chính sách ghi hoàn chỉnh cần bao gồm cả parent resource, repository của entity liên quan và các endpoint tùy chỉnh. Hãy chọn rõ một write path được phép, đưa kiểm tra quyền và quy tắc nghiệp vụ vào đường đi đó, rồi xác nhận bằng các request thực tế.
