# Quan hệ giữa tài nguyên

Một REST API hiếm khi chỉ có các tài nguyên đứng riêng lẻ. Đơn hàng thuộc về một khách hàng, đơn hàng chứa các dòng hàng, mỗi dòng hàng tham chiếu đến một sản phẩm; khách hàng có thể có nhiều địa chỉ hoặc tham gia nhiều nhóm. Những mối quan hệ này tạo thành đồ thị tài nguyên mà client khám phá thông qua hypermedia.

Khi thiết kế Spring HATEOAS, cần quyết định quan hệ nào được công bố bằng liên kết, quan hệ nào nên được nhúng trong representation và quan hệ nào cần trở thành một tài nguyên độc lập. Quyết định đó ảnh hưởng đến cách client điều hướng, số request, quyền truy cập và khả năng tiến hóa hợp đồng API.

Bài học này trình bày cách mô hình hóa quan hệ giữa các resource, phân biệt quan hệ nghiệp vụ với quan hệ trong cơ sở dữ liệu, cách tạo link bằng Spring HATEOAS, cách dùng embedded representation và cách thiết kế tài nguyên liên kết khi bản thân quan hệ có dữ liệu hoặc vòng đời riêng.

## 1. Quan hệ giữa tài nguyên trong REST

Resource đại diện cho một khái niệm mà API công bố qua URI. Quan hệ giữa các resource cho biết một tài nguyên có liên quan đến tài nguyên nào và client có thể điều hướng giữa chúng ra sao.

Ví dụ trong hệ thống bán hàng:

- Một Customer có thể có nhiều Order.
- Mỗi Order thuộc về một Customer.
- Một Order có nhiều OrderItem.
- Mỗi OrderItem tham chiếu đến một Product.
- Một Product có thể xuất hiện trong nhiều OrderItem.

Có thể hình dung đồ thị tài nguyên:

~~~mermaid
flowchart TD
    C["Customer<br/>/api/customers/7"]
    O["Order<br/>/api/orders/42"]
    I["OrderItem<br/>/api/orders/42/items/3"]
    P["Product<br/>/api/products/100"]
    C -->|"orders"| O
    O -->|"items"| I
    I -->|"product"| P
~~~

Đồ thị này mô tả cách client đi từ một resource sang resource khác. Nó không yêu cầu mỗi quan hệ phải tương ứng với một foreign key hoặc một bảng join. API có thể biểu diễn một quan hệ bằng link, bằng dữ liệu nhúng hoặc bằng một resource trung gian tùy ý nghĩa nghiệp vụ.

## 2. Phân biệt quan hệ domain, persistence và resource

Ba loại quan hệ thường liên quan nhưng phục vụ các mục tiêu khác nhau:

| Loại quan hệ | Mục đích | Ví dụ |
| --- | --- | --- |
| Domain association | Thể hiện nghiệp vụ và quyền sở hữu | Order thuộc Customer |
| Persistence association | Xác định cách dữ liệu được lưu và truy vấn | Cột customer_id trong bảng orders |
| Resource relationship | Cho client khám phá và tương tác qua HTTP | Link customer trong representation của Order |

Domain model có thể dùng aggregate, entity và value object để bảo vệ quy tắc nghiệp vụ. Persistence model có thể dùng quan hệ JPA như @ManyToOne hoặc @OneToMany. Resource model lại cần trả lời client cần khám phá điều gì và tài nguyên nào có URI riêng.

Không nên sao chép nguyên cấu trúc JPA thành hợp đồng API. Ví dụ, entity Order có thể có trường customer và một proxy lazy của Hibernate. API không nên vô tình tuần tự hóa toàn bộ object graph đó. Thay vào đó, DTO chọn dữ liệu công khai và assembler tạo các link cần thiết.

Một domain association cũng không bắt buộc phải được công bố thành một resource độc lập. Dòng hàng OrderItem có thể chỉ được quản lý qua Order, trong khi Product là tài nguyên độc lập có URI riêng. Hãy chọn resource boundary theo vòng đời, ý nghĩa và nhu cầu client.

## 3. Xác định loại và chiều của quan hệ

Trước khi tạo link, hãy xác định cardinality và ý nghĩa của quan hệ:

| Cardinality | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| One-to-one | Một resource liên quan đến tối đa một resource khác | Customer có một hồ sơ cá nhân |
| One-to-many | Một resource liên quan đến nhiều resource khác | Customer có nhiều Order |
| Many-to-one | Nhiều resource cùng tham chiếu một resource | Nhiều Order thuộc một Customer |
| Many-to-many | Nhiều resource ở hai phía có thể liên quan lẫn nhau | Product thuộc nhiều Category |

Quan hệ có thể được công bố theo một chiều hoặc hai chiều. Order có link customer không có nghĩa representation của Customer bắt buộc phải nhúng toàn bộ Order. Nếu client cần đi ngược từ Customer sang Order, Customer có thể công bố một link orders riêng.

Chiều của link nên phản ánh nhu cầu điều hướng. Không cần tạo mọi liên kết hai chiều chỉ vì domain model có thể truy cập cả hai phía. Mỗi link thêm vào đều trở thành một phần của hợp đồng mà client có thể phụ thuộc.

## 4. Chọn giữa link, embedded representation và resource trung gian

Có ba cách phổ biến để công bố một quan hệ:

| Cách biểu diễn | Nội dung | Phù hợp khi |
| --- | --- | --- |
| Link đến resource liên quan | Representation chứa href và relation | Resource có vòng đời độc lập, dữ liệu lớn hoặc được truy cập riêng |
| Embedded representation | Representation cha chứa một phần dữ liệu của resource liên quan | Client thường cần một projection nhỏ cùng lúc với resource cha |
| Association resource | Quan hệ có URI, dữ liệu hoặc vòng đời riêng | Bản thân mối quan hệ có thuộc tính, trạng thái hoặc thao tác riêng |

### Dùng link khi resource độc lập

Order có thể công bố link đến Customer:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/7"
    }
  }
}
~~~

Client có thể theo link customer để lấy representation mới nhất của khách hàng. Cách này giữ Customer độc lập với Order và không buộc response đơn hàng phải mang toàn bộ thông tin khách hàng.

### Nhúng projection khi client cần dữ liệu tóm tắt

Nếu màn hình đơn hàng luôn cần tên khách hàng, representation có thể nhúng một projection nhỏ:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "customerSummary": {
    "displayName": "Nguyen An"
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/7"
    }
  }
}
~~~

Projection chỉ là phần dữ liệu được chọn để hiển thị nhanh. Nó không biến Customer thành một phần của aggregate Order và cũng không nhất thiết là representation đầy đủ của Customer. Link customer vẫn cho phép client lấy tài nguyên chính.

Nếu muốn công bố một embedded resource theo HAL, dùng vùng _embedded và một relation rõ ràng. Ví dụ:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/api/customers/7"
    }
  },
  "_embedded": {
    "customer": {
      "id": 7,
      "displayName": "Nguyen An",
      "_links": {
        "self": {
          "href": "https://api.example.com/api/customers/7"
        }
      }
    }
  }
}
~~~

Một thuộc tính JSON thông thường như customerSummary và một embedded resource trong _embedded không phải cùng một cấu trúc HAL. Chọn dạng phù hợp với media type và hợp đồng mà client cần. Nếu dùng HAL, kiểm thử tên relation trong _embedded và link self của resource nhúng.

### Dùng association resource khi quan hệ có ý nghĩa riêng

Nếu quan hệ giữa hai tài nguyên có các thuộc tính như vai trò, thời điểm tham gia hoặc trạng thái, hãy cân nhắc mô hình hóa quan hệ thành resource độc lập. Ví dụ Membership nối User với Group và có các trường role, joinedAt, status.

## 5. Link relation mô tả ý nghĩa của quan hệ

Trong Spring HATEOAS, link gồm một URI và một relation. URI xác định đích điều hướng; relation mô tả ý nghĩa của link trong ngữ cảnh representation.

Một số relation thường gặp:

| Relation | Ý nghĩa trong ví dụ |
| --- | --- |
| self | Chính resource hiện tại |
| customer | Khách hàng sở hữu đơn hàng |
| orders | Tập hợp đơn hàng liên quan |
| items | Các dòng hàng thuộc đơn hàng |
| product | Sản phẩm được dòng hàng tham chiếu |
| payment | Thông tin hoặc resource thanh toán |

Relation nên có tên nhất quán và phản ánh ngữ nghĩa mà client cần hiểu. Không nên dùng tên lớp Java, tên bảng hoặc tên repository làm relation. Nếu relation là một quan hệ mở rộng riêng của API, hãy chọn tên ổn định và cân nhắc URI relation khi cần tránh xung đột.

Client nên tìm link theo relation rồi theo href. Client không nên tự ghép /api/customers/ với một customerId lấy từ payload nếu server đã cung cấp link customer. Cách điều hướng theo relation giảm sự phụ thuộc vào cấu trúc URI nội bộ.

## 6. Tạo link quan hệ bằng Spring HATEOAS

Giả sử Order có mã đơn và mã khách hàng. DTO công khai:

~~~java
import java.math.BigDecimal;

public record OrderDto(
        Long id,
        String status,
        BigDecimal total
) {
}
~~~

Domain model dùng trong ví dụ:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

~~~java
import java.math.BigDecimal;

public record Order(
        Long id,
        Long customerId,
        OrderStatus status,
        BigDecimal total
) {
}
~~~

Trong dự án Java, mỗi kiểu public được đặt trong file nguồn riêng. Service có thể cung cấp các thao tác được controller sử dụng:

~~~java
import java.util.List;

public interface OrderService {
    Order getRequired(Long id);
    List<Order> findByCustomer(Long customerId);
}
~~~

Assembler tạo representation và các link:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderDto>> {

    @Override
    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.id(),
                order.status().name(),
                order.total()
        );

        EntityModel<OrderDto> model = EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel(),
                linkTo(methodOn(CustomerController.class)
                        .one(order.customerId())).withRel("customer"),
                linkTo(methodOn(OrderController.class)
                        .items(order.id())).withRel("items")
        );

        return model;
    }
}
~~~

Ví dụ giả định domain Order có id(), customerId(), status() và total(). OrderController có các phương thức one và items; CustomerController có phương thức one. Các service và controller được khai báo trong ứng dụng.

Assembler thêm ba quan hệ:

- self dẫn đến chính đơn hàng.
- customer dẫn đến khách hàng liên quan.
- items dẫn đến collection dòng hàng của đơn hàng.

Assembler không cần đưa customerId vào JSON chỉ để client tự ghép URI. Nếu hợp đồng API cần mã khách hàng như dữ liệu nghiệp vụ, có thể công bố trường đó; việc điều hướng vẫn nên dùng link customer.

OrderController cần công bố các phương thức tương ứng với mapping mà assembler tham chiếu, chẳng hạn one(Long id) cho chi tiết và items(Long orderId) cho collection dòng hàng. CustomerController cần có phương thức one(Long id). Các phương thức này có thể trả representation tương ứng; link builder chỉ dùng chữ ký và mapping để tạo URI.

## 7. Biểu diễn quan hệ one-to-many

Một khách hàng có thể có nhiều đơn hàng. Customer resource có thể công bố link đến collection:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;

@Component
public class CustomerModelAssembler {

    public EntityModel<CustomerDto> toModel(Customer customer) {
        CustomerDto dto = new CustomerDto(
                customer.id(),
                customer.name()
        );

        return EntityModel.of(
                dto,
                linkTo(methodOn(CustomerController.class)
                        .one(customer.id())).withSelfRel(),
                linkTo(methodOn(CustomerOrderController.class)
                        .orders(customer.id())).withRel("orders")
        );
    }
}
~~~

Controller collection con:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers/{customerId}/orders")
public class CustomerOrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderAssembler;

    public CustomerOrderController(
            OrderService orderService,
            OrderModelAssembler orderAssembler
    ) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderDto>> orders(
            @PathVariable Long customerId
    ) {
        return orderAssembler.toCollectionModel(
                orderService.findByCustomer(customerId)
        ).add(
                linkTo(methodOn(CustomerOrderController.class)
                        .orders(customerId)).withSelfRel(),
                linkTo(methodOn(CustomerController.class)
                        .one(customerId)).withRel("customer")
        );
    }
}
~~~

OrderModelAssembler được tái sử dụng để tạo từng đơn hàng trong collection con. Controller bổ sung link self của collection hiện tại và link customer quay về resource cha. Nhờ tách hai phạm vi, assembler của một Order không cần biết đơn hàng đang xuất hiện trong collection toàn cục hay collection của khách hàng.

Nếu collection có thể lớn, endpoint nên hỗ trợ phân trang. Client theo link next hoặc prev được server trả về thay vì tự tạo URL cho trang tiếp theo.

## 8. Biểu diễn quan hệ one-to-one

Một Customer có thể có một Profile hoặc một địa chỉ mặc định. Có thể công bố link profile:

~~~java
EntityModel<CustomerDto> model = EntityModel.of(
        customerDto,
        linkTo(methodOn(CustomerController.class)
                .one(customer.id())).withSelfRel(),
        linkTo(methodOn(ProfileController.class)
                .forCustomer(customer.id())).withRel("profile")
);
~~~

Nếu profile có URI và vòng đời độc lập, link riêng là lựa chọn rõ ràng. Nếu client chỉ cần một vài trường như ngôn ngữ hoặc ảnh đại diện trong trang khách hàng, representation có thể nhúng một profile summary.

Quan hệ one-to-one trong domain không bắt buộc phải dùng URI riêng. Nếu đối tượng kia chỉ là một phần không thể tách rời của resource cha và không có nhu cầu truy cập độc lập, nhúng các trường phù hợp có thể đơn giản hơn.

## 9. Biểu diễn quan hệ many-to-many

Giả sử Product có thể thuộc nhiều Category và một Category có nhiều Product. Có thể công bố link categories từ Product và link products từ Category:

~~~java
EntityModel<ProductDto> productModel = EntityModel.of(
        productDto,
        linkTo(methodOn(ProductController.class)
                .one(product.id())).withSelfRel(),
        linkTo(methodOn(ProductCategoryController.class)
                .categories(product.id())).withRel("categories")
);
~~~

~~~java
EntityModel<CategoryDto> categoryModel = EntityModel.of(
        categoryDto,
        linkTo(methodOn(CategoryController.class)
                .one(category.id())).withSelfRel(),
        linkTo(methodOn(CategoryProductController.class)
                .products(category.id())).withRel("products")
);
~~~

Hai link tạo điều hướng hai chiều qua các collection. Tuy nhiên, không cần nhúng toàn bộ Product trong Category và toàn bộ Category trong Product. Nếu làm vậy, representation có thể lặp dữ liệu hoặc tạo đồ thị tuần tự hóa sâu và khó kiểm soát.

Với collection lớn, cung cấp endpoint riêng có lọc và phân trang. Link quan hệ cho phép client khám phá collection khi cần.

## 10. Khi nào quan hệ nên trở thành association resource?

Một số quan hệ có thuộc tính và vòng đời riêng. Ví dụ, quan hệ User tham gia Group có thể chứa:

- role: vai trò của user trong group.
- joinedAt: thời điểm tham gia.
- status: trạng thái thành viên.
- invitedBy: người gửi lời mời.

Khi đó, quan hệ Membership có ý nghĩa độc lập và có thể được mô hình hóa thành resource:

~~~text
/api/groups/5/memberships/18
~~~

Representation:

~~~json
{
  "id": 18,
  "role": "MODERATOR",
  "status": "ACTIVE",
  "joinedAt": "2026-11-20T08:30:00Z",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/groups/5/memberships/18"
    },
    "group": {
      "href": "https://api.example.com/api/groups/5"
    },
    "user": {
      "href": "https://api.example.com/api/users/12"
    }
  }
}
~~~

Membership không chỉ là một link giữa Group và User. Nó có mã định danh, trạng thái và hành vi riêng như thay đổi role hoặc hủy tư cách thành viên. Resource trung gian giúp client thao tác đúng vào quan hệ mà không phải sửa trực tiếp một danh sách ID trong Group.

Các thao tác có thể được mô hình hóa qua URI của Membership, chẳng hạn tạo membership trong collection của group, cập nhật role hoặc hủy membership. Nếu cần mô tả phương thức HTTP và dữ liệu đầu vào mà client được phép gửi, có thể bổ sung affordance tương ứng; một link đơn thuần chủ yếu công bố đích điều hướng.

Một controller có thể công bố:

~~~java
@GetMapping(
        value = "/{groupId}/memberships/{membershipId}",
        produces = MediaTypes.HAL_JSON_VALUE
)
public EntityModel<MembershipDto> membership(
        @PathVariable Long groupId,
        @PathVariable Long membershipId
) {
    return membershipAssembler.toModel(
            membershipService.getRequired(groupId, membershipId)
    );
}
~~~

Hãy tạo association resource khi mối quan hệ có dữ liệu, quyền, trạng thái hoặc vòng đời đáng kể. Nếu quan hệ chỉ là một tham chiếu đơn giản và không có thao tác riêng, một link thường đủ.

## 11. Quan hệ sở hữu và aggregate boundary

Một quan hệ trong API không thay đổi quyền sở hữu dữ liệu của domain. Ví dụ, Order tham chiếu Customer nhưng không sở hữu vòng đời của Customer. Xóa hoặc cập nhật đơn hàng không nên vô tình xóa khách hàng.

Tương tự, OrderItem có thể thuộc aggregate Order. Client có thể đọc dòng hàng qua endpoint con /api/orders/{orderId}/items/{itemId}, nhưng việc thay đổi số lượng vẫn cần đi qua Order aggregate nếu quy tắc nghiệp vụ yêu cầu tính lại tổng tiền, kiểm tra trạng thái hoặc giới hạn số lượng.

Một số câu hỏi giúp xác định ranh giới:

1. Tài nguyên liên quan có danh tính và vòng đời độc lập không?
2. Client có cần truy cập hoặc thay đổi nó độc lập không?
3. Thay đổi quan hệ có quy tắc nghiệp vụ riêng không?
4. Có cần ghi nhận metadata của quan hệ không?
5. Quan hệ có thể thay đổi mà không thay đổi resource cha không?

Aggregate boundary xác định phạm vi nhất quán của nghiệp vụ; resource relationship xác định cách client điều hướng. Hai ranh giới có thể liên quan nhưng không cần trùng nhau.

## 12. Tránh nhúng vòng lặp và representation quá lớn

Một lỗi phổ biến là nhúng Customer đầy đủ trong Order, trong khi Customer lại nhúng toàn bộ Orders. Khi tuần tự hóa, đồ thị có thể quay lại resource ban đầu, lặp dữ liệu hoặc tạo response rất lớn.

Ví dụ không nên thiết kế mặc định:

~~~text
Order
  └── Customer
        └── Orders
              └── Customer
                    └── ...
~~~

Hãy giới hạn mức embedded:

- Order có thể nhúng CustomerSummary.
- Customer công bố link orders.
- Mỗi Order trong collection có link customer.
- Client theo link khi cần dữ liệu chi tiết.

Cách này tránh vòng lặp và giữ mỗi resource có một URI rõ ràng. Embedded representation nên là projection có chủ đích, không phải toàn bộ object graph của ORM.

## 13. Quyền truy cập và tính nhất quán của quan hệ

Không phải client nào cũng được xem mọi resource liên quan. Ví dụ, người dùng có thể xem đơn hàng nhưng không được xem thông tin thanh toán hoặc địa chỉ giao hàng.

API có thể không công bố link đến resource mà người dùng hiện tại không được phép truy cập. Tuy nhiên, việc ẩn link không phải là biện pháp bảo mật duy nhất. Nếu client lưu URI từ trước hoặc tự biết URI, endpoint đích vẫn phải xác thực và phân quyền khi nhận request.

Quan hệ cũng có thể thay đổi theo thời gian. Một Order có thể được gán lại cho Customer khác hoặc Membership có thể bị thu hồi. Link trong representation phản ánh trạng thái tại thời điểm tạo response; server phải kiểm tra lại quyền sở hữu và trạng thái trong thao tác tiếp theo.

Khi tạo link từ dữ liệu quan hệ, hãy bảo đảm service đã xác minh resource cha và resource con thuộc đúng phạm vi. Ví dụ, endpoint /api/orders/42/items/3 phải xác nhận dòng hàng số 3 thực sự thuộc đơn hàng số 42.

## 14. Tiến hóa quan hệ trong hợp đồng API

Tên relation và cấu trúc embedded là một phần của hợp đồng API. Một số nguyên tắc:

- Giữ relation ổn định khi chỉ thay đổi entity hoặc schema lưu trữ.
- Có thể bổ sung link mới để client mới khám phá thêm chức năng; client cũ nên bỏ qua relation chưa biết.
- Đổi ý nghĩa hoặc xóa relation đang được sử dụng cần được xem là thay đổi hợp đồng.
- Không thay link customer bằng một trường customerId mà không đánh giá client đang phụ thuộc vào link.
- Nếu cần nhiều dạng representation, xác định rõ media type, profile hoặc versioning strategy.

Hypermedia giúp giảm sự phụ thuộc vào URI cụ thể, nhưng client vẫn dựa vào ngữ nghĩa relation và cấu trúc representation. Vì vậy, cần quản lý tên relation và embedded relation có chủ đích.

## 15. Kiểm thử quan hệ giữa tài nguyên

Kiểm thử nên xác nhận link trỏ đúng resource, relation đúng ý nghĩa và collection con không làm mất liên kết của từng phần tử.

Ví dụ với MockMvc:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderAssociationTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void orderExposesCustomerAndItemsRelations() throws Exception {
        Order order = new Order(
                42L,
                7L,
                OrderStatus.PENDING,
                BigDecimal.valueOf(1250000)
        );
        when(orderService.getRequired(42L)).thenReturn(order);

        mockMvc.perform(get("/api/orders/42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists())
                .andExpect(jsonPath("$._links.customer.href")
                        .value(org.hamcrest.Matchers.endsWith(
                                "/api/customers/7"
                        )))
                .andExpect(jsonPath("$._links.items.href")
                        .value(org.hamcrest.Matchers.endsWith(
                                "/api/orders/42/items"
                        )));
    }
}
~~~

Đây là ví dụ minh họa. Các kiểu Order, OrderDto, OrderService, controller và assembler cần được khai báo trong package của ứng dụng. @Import đăng ký assembler trong test slice; service được mock để kiểm soát dữ liệu.

Nên kiểm thử thêm:

- Customer có link orders đến collection đúng khách hàng.
- Order item có link product đến sản phẩm được tham chiếu.
- Collection con có link self và link quay về resource cha.
- Resource liên quan không tồn tại trả status phù hợp.
- Item không thuộc resource cha không được trả về.
- Quan hệ bị thu hồi hoặc thay đổi quyền không còn được công bố trong representation mới.
- Collection rỗng vẫn có cấu trúc hypermedia hợp lệ.

Không nên khóa toàn bộ hostname và cổng trong test nếu môi trường khác nhau. Ưu tiên xác nhận relation và phần path cần thiết để chứng minh đích điều hướng đúng.

## 16. Những lỗi thường gặp

**Sao chép nguyên quan hệ ORM ra JSON.** Điều này có thể làm lộ trường persistence, tạo vòng lặp hoặc tải dữ liệu không cần thiết. Dùng DTO và assembler để chọn representation công khai.

**Nhúng toàn bộ resource liên quan.** Response dễ lớn và lặp dữ liệu. Dùng link đến resource độc lập; chỉ nhúng projection nhỏ khi client có nhu cầu rõ ràng.

**Dùng ID để client tự ghép URI.** Client phụ thuộc vào cấu trúc path và có thể tạo link sai khi API đổi mapping. Công bố link relation và href.

**Tạo mọi quan hệ hai chiều.** Nhiều link không có ích làm hợp đồng phức tạp. Chỉ công bố chiều điều hướng mà client cần.

**Không tạo association resource khi quan hệ có trạng thái riêng.** Nếu membership có role, status và vòng đời, chỉ dùng link giữa User và Group sẽ không đủ để mô tả các thao tác trên quan hệ.

**Nhầm link với quyền truy cập.** Link chỉ là thông tin điều hướng. Endpoint đích vẫn phải xác thực và phân quyền.

**Bỏ qua aggregate boundary.** Endpoint cập nhật resource con có thể làm hỏng invariant nếu thay đổi trực tiếp mà không đi qua aggregate root. Service phải bảo vệ quy tắc nghiệp vụ.

**Tạo embedded graph có vòng lặp.** Nhúng resource cha-con qua lại có thể gây lặp hoặc response quá lớn. Giới hạn embedded và dùng link để điều hướng.

## 17. Ghi nhớ

Quan hệ giữa resource tạo thành đồ thị hypermedia mà client có thể khám phá bằng link relation. Hãy phân biệt domain association, persistence association và resource relationship; chúng có liên quan nhưng không bắt buộc có cùng cấu trúc.

Dùng link khi resource liên quan có vòng đời độc lập hoặc cần truy cập riêng. Dùng embedded projection khi client cần một phần dữ liệu nhỏ cùng resource cha. Tạo association resource khi bản thân quan hệ có thuộc tính, trạng thái, danh tính hoặc thao tác riêng. Với Spring HATEOAS, assembler tạo EntityModel và thêm link bằng linkTo(methodOn(...)); controller hoặc collection assembler bổ sung link theo ngữ cảnh collection.

Giữ relation ổn định, tránh nhúng toàn bộ object graph, xác minh quyền và aggregate boundary ở service, đồng thời kiểm thử link ở cả resource cha, resource con và collection. Hypermedia giúp client điều hướng theo ý nghĩa của quan hệ thay vì phải tự suy đoán cấu trúc URI.
