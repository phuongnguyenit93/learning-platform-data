# Tránh payload quá lớn

Trong REST API có hypermedia, một tài nguyên thường liên quan đến nhiều tài nguyên khác. Ví dụ, khách hàng có nhiều đơn hàng; mỗi đơn hàng có nhiều dòng hàng; mỗi dòng hàng lại tham chiếu đến sản phẩm, giá, kho và thông tin giao nhận. Nếu API nhúng toàn bộ quan hệ đó vào một response, payload có thể tăng rất nhanh, thời gian serialize và truyền dữ liệu cũng tăng, đồng thời client nhận nhiều thông tin không cần cho màn hình hiện tại.

Spring HATEOAS giúp thiết kế ranh giới tài nguyên bằng Link, EntityModel, CollectionModel và các representation model. Thay vì đưa toàn bộ đồ thị đối tượng vào một response, API có thể công bố link đến tài nguyên liên quan, chỉ nhúng phần tóm tắt thực sự cần thiết và phân trang các tập hợp lớn. Cách thiết kế này giúp client khám phá dữ liệu theo nhu cầu mà vẫn giữ hợp đồng API rõ ràng.

Bài học này tập trung vào cách kiểm soát kích thước payload khi biểu diễn associations: chọn giữa link và embedding, thiết kế DTO tóm tắt, giới hạn độ sâu quan hệ, phân trang collection, tránh serialize trực tiếp entity JPA, kiểm soát truy vấn N+1 và kiểm thử kích thước response.

## 1. Vì sao associations làm payload tăng nhanh?

Một association trong mô hình miền không nhất thiết phải trở thành một object lồng nhau đầy đủ trong response API.

Giả sử một khách hàng có 40 đơn hàng, mỗi đơn hàng có 8 dòng hàng và mỗi dòng hàng tham chiếu đến một sản phẩm. Nếu response khách hàng nhúng toàn bộ đơn hàng, dòng hàng và sản phẩm, số object được serialize có thể tăng theo cấp số nhân khi quan hệ tiếp tục mở rộng.

Ví dụ cấu trúc miền:

~~~text
Customer
  └── Orders (40)
        └── Items (8 mỗi đơn)
              └── Product
                    ├── Category
                    ├── Supplier
                    └── Inventory
~~~

Nếu API nhúng toàn bộ đồ thị, một request lấy thông tin khách hàng có thể vô tình tải cả dữ liệu kho và nhà cung cấp. Điều này gây ra một số vấn đề:

- Response lớn dù client chỉ cần tên và mã khách hàng.
- Thời gian truy vấn, chuyển đổi DTO, serialize và truyền dữ liệu tăng.
- Thay đổi cấu trúc một entity có thể ảnh hưởng đến nhiều response.
- Quan hệ hai chiều có thể tạo vòng tham chiếu khi serialize.
- ORM có thể tải lazy association trong lúc serialize, làm phát sinh nhiều truy vấn.
- Client bị buộc phụ thuộc vào một cấu trúc response sâu và khó tiến hóa.

Kích thước payload không chỉ là số byte. Nó còn liên quan đến số truy vấn, chi phí CPU, bộ nhớ, độ trễ và mức độ coupling giữa các tài nguyên.

## 2. Chọn link hay nhúng dữ liệu?

Một association có thể được biểu diễn bằng link đến tài nguyên riêng hoặc bằng dữ liệu nhúng trong response hiện tại. Hai cách giải quyết hai nhu cầu khác nhau.

| Tiêu chí | Link đến tài nguyên liên quan | Nhúng dữ liệu |
|---|---|---|
| Response hiện tại | Nhỏ hơn | Lớn hơn |
| Số request phía client | Có thể cần request tiếp theo | Thường ít request hơn |
| Dữ liệu liên quan | Được tải khi client cần | Được gửi ngay |
| Vòng đời tài nguyên | Độc lập | Gắn với response chứa nó |
| Cập nhật dữ liệu | Client lấy phiên bản mới qua link | Dữ liệu có thể cũ theo response hiện tại |
| Phù hợp | Tài nguyên lớn, thay đổi độc lập, ít được dùng | Dữ liệu nhỏ, thường xuyên cần cùng tài nguyên chính |

Ví dụ response khách hàng chỉ chứa thông tin cơ bản và link đến đơn hàng:

~~~json
{
  "id": "CUS-7",
  "name": "Nguyen An",
  "status": "ACTIVE",
  "_links": {
    "self": {
      "href": "/customers/CUS-7"
    },
    "orders": {
      "href": "/customers/CUS-7/orders"
    }
  }
}
~~~

Client có thể theo relation orders khi cần xem đơn hàng. Nếu giao diện chỉ hiển thị tên khách hàng, client không phải tải danh sách đơn hàng cùng tất cả dòng hàng.

Nếu client thường cần một vài thông tin liên quan để hiển thị ngay, có thể nhúng một DTO tóm tắt:

~~~json
{
  "id": "ORD-42",
  "status": "PROCESSING",
  "total": 125000,
  "customer": {
    "id": "CUS-7",
    "name": "Nguyen An"
  },
  "_links": {
    "self": {
      "href": "/orders/ORD-42"
    },
    "customer": {
      "href": "/customers/CUS-7"
    }
  }
}
~~~

Trong ví dụ, customer chỉ là phần tóm tắt. Link customer vẫn trỏ đến tài nguyên khách hàng đầy đủ. Client có thể dùng dữ liệu tóm tắt để hiển thị ngay hoặc theo link để lấy chi tiết.

Không cần chọn một cách duy nhất cho mọi association. Một representation có thể nhúng dữ liệu nhỏ, đồng thời cung cấp link đến tài nguyên đầy đủ.

## 3. Link trong Spring HATEOAS không tự động tải tài nguyên đích

Một điểm quan trọng khi thiết kế hypermedia: thêm Link vào EntityModel không khiến Spring HATEOAS tự truy vấn hoặc nhúng nội dung của tài nguyên đích.

Ví dụ:

~~~java
EntityModel<CustomerRepresentation> model =
    EntityModel.of(
        customerRepresentation,
        linkTo(methodOn(CustomerController.class).one(customerId))
            .withSelfRel(),
        linkTo(methodOn(CustomerOrderController.class).all(customerId))
            .withRel("orders")
    );
~~~

Model chỉ chứa dữ liệu customerRepresentation và các liên kết. Client quyết định có theo relation orders hay không.

Cách này tạo ranh giới rõ ràng giữa tài nguyên khách hàng và tập hợp đơn hàng. Endpoint orders có thể có bộ lọc, phân trang, quyền truy cập và cache riêng. Thay đổi cách biểu diễn đơn hàng không buộc response khách hàng phải thay đổi theo.

Link không làm giảm tổng dữ liệu mà client có thể tải nếu client vẫn lần lượt gọi mọi endpoint. Nó giúp tải theo nhu cầu, tránh gửi dữ liệu không cần thiết trong mỗi response và cho phép client dừng ở mức thông tin cần dùng.

## 4. Tạo DTO tóm tắt thay vì serialize toàn bộ entity

Một trong những cách hiệu quả nhất để giới hạn payload là định nghĩa representation DTO theo use case.

Ví dụ entity đơn hàng có thể chứa nhiều quan hệ:

~~~java
@Entity
public class Order {

    @Id
    private UUID id;

    private String status;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items;

    // Các trường và quan hệ khác
}
~~~

Không nên trả trực tiếp Order từ controller chỉ vì serializer có thể chuyển nó thành JSON. Entity là mô hình persistence, còn response là hợp đồng công khai của API.

Tạo DTO tóm tắt:

~~~java
public record OrderSummary(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Và DTO chi tiết dòng hàng:

~~~java
public record OrderItemSummary(
    UUID id,
    String productName,
    int quantity,
    BigDecimal lineTotal
) {}
~~~

Representation đơn hàng có thể chứa một vài trường cơ bản và link đến items:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total,
    String customerName
) {}
~~~

Assembler chuyển đổi nguồn thành DTO và thêm link:

~~~java
@Component
public class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        var body = new OrderRepresentation(
            order.getId(),
            order.getStatus(),
            order.getTotal(),
            order.getCustomer().getName()
        );

        return EntityModel.of(
            body,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel(),
            linkTo(methodOn(OrderItemController.class).all(order.getId()))
                .withRel("items")
        );
    }
}
~~~

Ví dụ trên giả định tên khách hàng đã được tải trong truy vấn hoặc nằm trong persistence context. Nếu customer là lazy association, truy cập getCustomer().getName() có thể kích hoạt truy vấn bổ sung. DTO giúp giới hạn trường response nhưng không tự giải quyết chiến lược fetch; phần truy vấn cần được thiết kế phù hợp.

## 5. Tách tài nguyên collection lớn thành endpoint riêng

Với quan hệ một-nhiều, thường nên tạo endpoint riêng cho tập hợp con thay vì nhúng toàn bộ vào tài nguyên cha.

Ví dụ:

- GET /customers/{id}: thông tin cơ bản của khách hàng.
- GET /customers/{id}/orders: tập hợp đơn hàng của khách hàng.
- GET /orders/{id}: chi tiết một đơn hàng.
- GET /orders/{id}/items: tập hợp dòng hàng của đơn hàng.
- GET /products/{id}: chi tiết sản phẩm.

Representation khách hàng:

~~~java
public EntityModel<CustomerRepresentation> toModel(Customer customer) {
    var body = new CustomerRepresentation(
        customer.getId(),
        customer.getName(),
        customer.getStatus()
    );

    return EntityModel.of(
        body,
        linkTo(methodOn(CustomerController.class).one(customer.getId()))
            .withSelfRel(),
        linkTo(methodOn(CustomerOrderController.class)
            .all(customer.getId()))
            .withRel("orders")
    );
}
~~~

Endpoint collection có thể trả CollectionModel:

~~~java
@GetMapping("/customers/{customerId}/orders")
public CollectionModel<EntityModel<OrderSummary>> all(
        @PathVariable UUID customerId) {

    List<OrderSummary> orders =
        service.findSummariesByCustomerId(customerId);

    return assembler.toCollectionModel(orders)
        .add(linkTo(methodOn(CustomerOrderController.class)
            .all(customerId))
            .withSelfRel());
}
~~~

Nếu tập hợp có thể lớn, không nên trả toàn bộ danh sách. Hãy dùng phân trang hoặc cursor để giới hạn số phần tử mỗi response. CollectionModel biểu diễn một tập hợp; khi cần metadata phân trang, dùng PagedModel hoặc cơ chế phân trang Spring Data phù hợp.

## 6. Phân trang để giới hạn kích thước collection

Một endpoint collection nên có giới hạn số phần tử. Nếu API trả hàng nghìn đơn hàng trong một response, payload vẫn lớn dù mỗi đơn hàng chỉ có vài trường.

Spring Data hỗ trợ Pageable và Page. Spring HATEOAS có thể chuyển Page thành PagedModel với metadata và link điều hướng.

Ví dụ controller dùng PagedResourcesAssembler:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;

@RestController
public class CustomerOrderController {

    private final OrderService service;
    private final RepresentationModelAssembler<
        OrderSummary, EntityModel<OrderSummary>> orderSummaryAssembler;

    public CustomerOrderController(
            OrderService service,
            RepresentationModelAssembler<
                OrderSummary, EntityModel<OrderSummary>> orderSummaryAssembler) {
        this.service = service;
        this.orderSummaryAssembler = orderSummaryAssembler;
    }

@GetMapping("/customers/{customerId}/orders")
public PagedModel<EntityModel<OrderSummary>> all(
        @PathVariable UUID customerId,
        Pageable pageable,
        PagedResourcesAssembler<OrderSummary> pagedAssembler) {

    Page<OrderSummary> page =
        service.findOrderSummaries(customerId, pageable);

    return pagedAssembler.toModel(page, orderSummaryAssembler);
}
}
~~~

Assembler chuyển một OrderSummary thành EntityModel<OrderSummary>, bổ sung self link và các relation cần thiết. PagedResourcesAssembler tạo PagedModel có metadata trang và các link điều hướng như first, prev, self, next, last theo trạng thái phân trang.

Client theo link next hoặc prev do server công bố thay vì tự xây query string. Nhờ vậy, server có thể thay đổi cách phân trang từ page/size sang cursor mà vẫn duy trì ngữ nghĩa điều hướng nếu hợp đồng được thiết kế phù hợp.

Nên đặt giới hạn tối đa cho page size ở phía server. Nếu client gửi size rất lớn, server có thể giới hạn về mức tối đa cho phép. Việc chỉ cung cấp tham số Pageable mà không có giới hạn có thể vẫn cho phép client yêu cầu một response quá lớn.

Với dữ liệu thay đổi liên tục hoặc bảng rất lớn, cursor pagination có thể ổn định và hiệu quả hơn offset pagination. API có thể công bố link next chứa cursor để client tiếp tục truy vấn.

## 7. Chọn projection để chỉ truy vấn trường cần thiết

DTO tóm tắt chỉ giảm payload nếu tầng truy vấn cũng tránh tải dữ liệu không cần thiết. Nếu repository tải toàn bộ entity graph rồi assembler chỉ dùng ba trường, database và ORM vẫn có thể phải làm nhiều việc.

Spring Data JPA hỗ trợ projection để truy vấn một phần dữ liệu. Ví dụ interface projection:

~~~java
public interface OrderSummaryView {
    UUID getId();
    String getStatus();
    BigDecimal getTotal();
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Page<OrderSummaryView> findByCustomer_Id(
        UUID customerId,
        Pageable pageable
    );
}
~~~

Service có thể chuyển projection thành DTO API hoặc dùng projection làm nguồn cho assembler:

~~~java
public record OrderSummary(
    UUID id,
    String status,
    BigDecimal total
) {
    static OrderSummary from(OrderSummaryView view) {
        return new OrderSummary(
            view.getId(),
            view.getStatus(),
            view.getTotal()
        );
    }
}
~~~

Một lựa chọn khác là class-based projection hoặc constructor expression trong JPQL khi cần chọn trường từ nhiều bảng. Hãy chọn projection dựa trên query và use case thực tế.

Projection có hai lợi ích riêng biệt:

- Giảm số trường được tải từ database.
- Tạo nguồn dữ liệu phù hợp cho response nhỏ.

Nó không tự tạo Link hoặc representation hypermedia. Assembler vẫn có thể dùng DTO projection làm nguồn để thêm self, customer, items hoặc các link cần thiết.

## 8. Tránh N+1 và lazy loading khi tạo representation

Payload nhỏ không đồng nghĩa với ít truy vấn. Ví dụ, endpoint trả 50 đơn hàng; assembler gọi getCustomer().getName() cho từng đơn. Nếu customer chưa được tải, ORM có thể phát sinh thêm truy vấn cho từng đơn hàng.

Đây là vấn đề N+1: một truy vấn lấy danh sách, sau đó nhiều truy vấn riêng để tải quan hệ cho từng phần tử.

Các hướng xử lý:

- Dùng projection lấy sẵn các trường cần cho summary.
- Dùng fetch join có chọn lọc khi endpoint thực sự cần quan hệ.
- Dùng EntityGraph khi cần chỉ định association được tải trong một use case.
- Dùng batch fetching khi phù hợp với ORM và kích thước tập dữ liệu.
- Tránh truy cập quan hệ lazy tùy tiện trong serializer hoặc processor.
- Đo số query trong test tích hợp hoặc công cụ quan sát.

Ví dụ JPQL constructor projection:

~~~java
@Query("""
    select new com.example.api.OrderSummary(
        o.id,
        o.status,
        o.total
    )
    from Order o
    where o.customer.id = :customerId
    """)
Page<OrderSummary> findSummaries(
    UUID customerId,
    Pageable pageable
);
~~~

Tên package và kiểu dữ liệu trong constructor expression phải khớp với lớp DTO thực tế. Query này chỉ lấy những trường được khai báo trong OrderSummary; không cần tải toàn bộ collection items hoặc product của mỗi đơn hàng.

Fetch join cũng cần được dùng thận trọng với phân trang. Join một collection một-nhiều có thể nhân bản dòng kết quả và làm sai hoặc làm tăng chi phí phân trang. Với collection lớn, thường nên phân trang tài nguyên cha trước rồi tải dữ liệu liên quan theo chiến lược riêng.

## 9. Kiểm soát độ sâu của representation

Một payload lồng nhau có thể bắt đầu từ một quan hệ nhỏ rồi mở rộng thành nhiều tầng:

~~~text
Order
  └── Customer
        └── Orders
              └── Items
                    └── Product
                          └── Supplier
~~~

Nếu mỗi tầng tiếp tục nhúng toàn bộ quan hệ tiếp theo, response dễ phình to và có thể tạo vòng lặp.

Một quy tắc hữu ích là xác định rõ độ sâu embedding cho từng endpoint:

- Tầng gốc: dữ liệu chính mà endpoint đại diện.
- Tầng lồng đầu tiên: chỉ nhúng summary nhỏ nếu client thường xuyên cần.
- Các tầng sâu hơn: cung cấp link đến tài nguyên riêng.
- Collection có số lượng không giới hạn: tách endpoint và phân trang.

Ví dụ OrderRepresentation có thể nhúng CustomerSummary, nhưng không nhúng toàn bộ Customer cùng tất cả Orders. Order có link items; mỗi item có link product. Nếu client cần chi tiết sản phẩm, nó theo link product.

Không nên tạo một quy tắc embedding toàn cục cho mọi entity. Độ sâu phù hợp phụ thuộc vào use case của endpoint và dữ liệu client thực sự cần.

## 10. Tránh vòng tham chiếu khi serialize association

JPA entity thường có quan hệ hai chiều:

~~~java
@Entity
class Customer {

    @OneToMany(mappedBy = "customer")
    private List<Order> orders;
}

@Entity
class Order {

    @ManyToOne
    private Customer customer;
}
~~~

Nếu serialize trực tiếp, Customer có orders, mỗi Order lại có customer, rồi customer có orders tiếp. Tùy serializer và annotation, kết quả có thể là vòng lặp, lỗi serialize hoặc cấu trúc JSON quá sâu.

Không nên dựa vào annotation serializer để biến entity graph thành hợp đồng API lâu dài. Cách ổn định hơn là dùng DTO riêng cho mỗi hướng biểu diễn:

~~~java
public record CustomerSummary(
    UUID id,
    String name
) {}

public record OrderRepresentation(
    UUID id,
    String status,
    CustomerSummary customer
) {}
~~~

CustomerSummary không chứa danh sách orders. Link customer trong OrderModel dẫn đến tài nguyên khách hàng đầy đủ. Việc tách DTO giúp chủ động kiểm soát độ sâu và tránh vòng tham chiếu.

## 11. Thiết kế embedding có chọn lọc

Một số client có thể cần thêm dữ liệu trong một số trường hợp. Có thể thiết kế query parameter như include hoặc expand để client yêu cầu phần nhúng tùy chọn.

Ví dụ hợp đồng tùy chỉnh:

~~~text
GET /orders/ORD-42
GET /orders/ORD-42?include=customer
GET /orders/ORD-42?include=customer,items
~~~

Đây là quy ước API do ứng dụng thiết kế; Spring HATEOAS không tự cung cấp tham số include hoặc expand cho mọi endpoint.

Nếu hỗ trợ include, cần quy định:

- Những relation nào được phép nhúng.
- Mức độ sâu tối đa.
- Số phần tử tối đa cho mỗi collection được nhúng.
- Quyền truy cập đối với từng relation.
- Hành vi khi client yêu cầu relation không hỗ trợ.
- Cách biểu diễn link khi relation không được nhúng.
- Cách giới hạn tổng kích thước response.

Ví dụ, client có thể yêu cầu customer summary, nhưng không được yêu cầu toàn bộ lịch sử giao dịch và tất cả tài liệu đính kèm trong cùng response. Server cần kiểm soát danh sách include được hỗ trợ và từ chối hoặc bỏ qua tham số không hợp lệ theo hợp đồng đã công bố.

Ngay cả khi nhúng dữ liệu, nên giữ link đến tài nguyên đầy đủ. Link cho phép client điều hướng đến nguồn chuẩn và lấy dữ liệu mới khi cần.

## 12. Giữ relation ổn định khi thay đổi cách embedding

Client nên tìm tài nguyên liên quan bằng relation thay vì phụ thuộc vào vị trí cố định của trường JSON hoặc cấu trúc URL tự tạo.

Ví dụ response ban đầu chỉ có link:

~~~json
{
  "id": "ORD-42",
  "_links": {
    "customer": {
      "href": "/customers/CUS-7"
    }
  }
}
~~~

Sau đó API có thể thêm customer summary vào payload:

~~~json
{
  "id": "ORD-42",
  "customer": {
    "id": "CUS-7",
    "name": "Nguyen An"
  },
  "_links": {
    "customer": {
      "href": "/customers/CUS-7"
    }
  }
}
~~~

Relation customer vẫn chỉ cùng một tài nguyên liên quan. Client cũ có thể tiếp tục theo link; client mới có thể tận dụng summary nếu hợp đồng cho phép.

Khi thay đổi từ link-only sang embedded representation hoặc ngược lại, cần xem xét tương thích client. Không xóa link chỉ vì đã nhúng dữ liệu; client có thể cần URI canonical để lấy bản đầy đủ hoặc thao tác trên tài nguyên.

## 13. Giới hạn payload theo use case

Không có một ngưỡng byte phù hợp cho mọi endpoint. Một endpoint summary trên mobile có thể cần rất nhỏ; endpoint export có thể được thiết kế để trả dữ liệu lớn theo luồng hoặc file tải xuống.

Nên đặt ngân sách theo use case:

| Loại endpoint | Chiến lược |
|---|---|
| Chi tiết tài nguyên | DTO vừa đủ, link đến association lớn |
| Danh sách tài nguyên | Summary DTO và page size giới hạn |
| Dashboard | Projection chỉ lấy trường hiển thị |
| Chi tiết có quan hệ | Embed có chọn lọc, giới hạn độ sâu |
| Lịch sử giao dịch | Collection riêng, phân trang hoặc cursor |
| Export | Endpoint riêng, streaming hoặc tác vụ bất đồng bộ |

Kích thước cần đo ở nhiều lớp:

- Số trường và số phần tử trong representation.
- Số byte response JSON trước nén.
- Số byte truyền trên mạng sau nén.
- Thời gian truy vấn và serialize.
- Số query phát sinh.
- Bộ nhớ cần để dựng response.

Nén gzip hoặc Brotli có thể giảm byte truyền nhưng không giải quyết việc server tải quá nhiều entity, chạy nhiều query hoặc serialize một object graph khổng lồ. Tối ưu payload nên bắt đầu từ thiết kế representation và query.

## 14. Kiểm thử payload và associations bằng MockMvc

Integration test nên xác nhận response chỉ chứa dữ liệu cần thiết và có link đến association lớn.

~~~java
mockMvc.perform(get("/customers/{id}", customerId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(customerId.toString()))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.orders.href").exists())
    .andExpect(jsonPath("$._embedded.orders").doesNotExist());
~~~

Test này xác nhận endpoint khách hàng có link orders nhưng không nhúng cả collection đơn hàng. Nếu hợp đồng có customer summary trong response đơn hàng, kiểm tra đúng các trường được công bố:

~~~java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.customer.id").exists())
    .andExpect(jsonPath("$.customer.name").exists())
    .andExpect(jsonPath("$.customer.address").doesNotExist())
    .andExpect(jsonPath("$._links.customer.href").exists());
~~~

Kiểm tra trường không xuất hiện hữu ích để ngăn việc vô tình công bố thêm quan hệ hoặc trường nhạy cảm khi entity thay đổi.

## 15. Đặt ngân sách kích thước response

Nếu payload là một yêu cầu hiệu năng quan trọng, có thể đo số byte response trong integration test:

~~~java
MvcResult result = mockMvc.perform(
        get("/customers/{id}", customerId)
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andReturn();

int responseBytes =
    result.getResponse().getContentAsByteArray().length;

assertThat(responseBytes)
    .isLessThanOrEqualTo(16 * 1024);
~~~

Ngưỡng 16 KiB chỉ là ví dụ. Hãy đặt giới hạn dựa trên dữ liệu thật, yêu cầu client và mục tiêu hiệu năng của endpoint. Nếu response chứa URI tuyệt đối thay đổi theo môi trường, timestamp hoặc trường động, cần chuẩn hóa dữ liệu test hoặc chọn ngưỡng có khoảng đệm hợp lý.

Một bài test kích thước không thay thế kiểm thử cấu trúc. Payload có thể nhỏ nhưng thiếu link cần thiết; ngược lại, một response có thể vượt ngân sách do dữ liệu test không thực tế. Kết hợp kiểm tra:

- Relation bắt buộc có mặt.
- Collection lớn không bị nhúng ngoài ý muốn.
- DTO không có trường ngoài hợp đồng.
- Số phần tử trong page không vượt giới hạn.
- Kích thước byte không vượt ngân sách đã thống nhất.

## 16. Những lỗi thường gặp khi xử lý associations

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhúng toàn bộ quan hệ một-nhiều | Response lớn theo số phần tử | Tách endpoint collection và phân trang |
| Trả trực tiếp JPA entity | Lộ trường persistence, lazy loading và vòng tham chiếu | Dùng DTO/representation |
| Chỉ giới hạn trường DTO nhưng vẫn tải toàn bộ entity graph | Database và ORM vẫn tốn tài nguyên | Dùng projection hoặc query có chọn lọc |
| Dùng link cho mọi quan hệ dù client luôn cần summary | Client phát sinh nhiều request không cần thiết | Nhúng DTO summary nhỏ khi hợp lý |
| Không cung cấp link khi đã nhúng summary | Client khó lấy tài nguyên đầy đủ hoặc điều hướng | Giữ relation link đến tài nguyên canonical |
| Cho phép include không giới hạn | Client có thể yêu cầu đồ thị dữ liệu quá lớn | Whitelist relation, giới hạn độ sâu và số phần tử |
| Fetch join collection cùng phân trang một cách tùy tiện | Kết quả trùng dòng hoặc phân trang sai | Phân trang tài nguyên cha, tải quan hệ theo chiến lược riêng |
| Chỉ dựa vào nén response | Giảm byte mạng nhưng không giảm query/serialize | Tối ưu representation, truy vấn và số phần tử |
| Không kiểm thử payload | Thay đổi entity làm response phình to âm thầm | Kiểm tra trường, relation, page size và byte budget |

## 17. Quy trình thiết kế association gọn nhẹ

Khi thiết kế response có nhiều quan hệ, hãy đi theo các bước:

1. Xác định use case của endpoint và trường nào client thật sự cần ngay.
2. Chọn link cho tài nguyên lớn hoặc có vòng đời độc lập.
3. Chỉ nhúng DTO summary nhỏ khi dữ liệu liên quan thường xuyên cần cùng response.
4. Tách collection một-nhiều thành endpoint riêng.
5. Phân trang hoặc dùng cursor cho collection có thể tăng không giới hạn.
6. Dùng projection hoặc query có chọn lọc để tránh tải entity graph không cần thiết.
7. Giữ độ sâu embedding có giới hạn và tránh vòng tham chiếu.
8. Nếu có include/expand, định nghĩa whitelist, giới hạn độ sâu, quyền và số phần tử.
9. Giữ relation ổn định và link đến tài nguyên canonical.
10. Kiểm thử cả cấu trúc hypermedia, số phần tử, truy vấn và ngân sách byte.

Một payload nhỏ không có nghĩa API thiếu khả năng khám phá. Với Spring HATEOAS, response có thể chứa dữ liệu cốt lõi, summary vừa đủ và các link đến association lớn. Client theo link khi cần chi tiết; server kiểm soát số phần tử, độ sâu và trường được công bố. Kết hợp representation DTO, assembler, projection và phân trang giúp API giữ response gọn, giảm chi phí truy vấn và cho phép từng tài nguyên tiến hóa độc lập.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation – Representation Models and HAL](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [EntityModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [CollectionModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [PagedModel API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/PagedModel.html)
- [RepresentationModelAssembler API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html)
- [Spring Data JPA Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Data Web Support and Pagination](https://docs.spring.io/spring-data/commons/reference/repositories/core-extensions.html)

