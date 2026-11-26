# Mô hình domain và resource

Khi xây dựng REST API bằng Spring HATEOAS, một trong những quyết định quan trọng là xác định tài nguyên API đại diện cho khái niệm nào trong miền nghiệp vụ. Một đối tượng domain có thể chứa nhiều quy tắc và trạng thái nội bộ; một resource là khái niệm mà API công bố để client nhận diện, đọc và tương tác thông qua HTTP. Hai mô hình có liên hệ với nhau nhưng không bắt buộc trùng khớp.

Nếu đưa nguyên đối tượng persistence hoặc domain ra phản hồi, API dễ phụ thuộc vào cấu trúc lưu trữ và chi tiết triển khai. Nếu thiết kế resource chỉ theo từng bảng dữ liệu, API có thể làm lộ mô hình nội bộ và buộc client hiểu quá nhiều về cách hệ thống vận hành. Bài học này trình bày cách phân biệt domain model với resource, cách chọn ranh giới tài nguyên, cách ánh xạ sang representation và cách dùng Spring HATEOAS để công bố các liên kết phù hợp.

## 1. Domain model là gì?

Domain model mô tả các khái niệm, dữ liệu, hành vi và quy tắc của miền nghiệp vụ. Nó trả lời những câu hỏi như: đơn hàng có thể ở những trạng thái nào, khi nào được hủy, số lượng sản phẩm phải thỏa điều kiện gì và ai có quyền thực hiện một thay đổi.

Trong thiết kế hướng domain, mô hình thường gồm một số loại thành phần:

| Thành phần | Vai trò | Ví dụ trong hệ thống bán hàng |
| --- | --- | --- |
| Entity | Đối tượng có danh tính xuyên suốt vòng đời | Order, Customer, Product |
| Value Object | Giá trị được xác định bởi thuộc tính, thường bất biến | Money, Address, Quantity |
| Aggregate | Nhóm đối tượng được quản lý như một ranh giới nhất quán | Order cùng các OrderLine |
| Aggregate Root | Điểm truy cập bên ngoài vào aggregate | Order |
| Domain Service | Hành vi nghiệp vụ không tự nhiên thuộc về một entity cụ thể | Tính chính sách chiết khấu phức tạp |
| Domain Event | Sự kiện thể hiện điều có ý nghĩa đã xảy ra trong nghiệp vụ | OrderCancelled |

Ví dụ, một đơn hàng có thể chứa nhiều dòng hàng. Mỗi dòng hàng có sản phẩm, số lượng và giá tại thời điểm đặt hàng. Đơn hàng chịu trách nhiệm bảo vệ các quy tắc như không được hủy khi đã thanh toán hoặc không được tạo đơn hàng rỗng. Client API không cần biết các quy tắc này được cài đặt bằng entity, method hay repository nào; client cần biết đơn hàng đang ở trạng thái nào và những thao tác nào được phép khám phá.

Một domain model tốt giữ các quy tắc quan trọng ở nơi có thể bảo vệ chúng. Nếu quy tắc hủy đơn hàng chỉ nằm trong controller hoặc giao diện, một luồng gọi khác có thể bỏ qua nó. Domain object hoặc application service cần đảm bảo thao tác luôn tuân thủ invariant, bất kể yêu cầu đến từ HTTP API, hàng đợi hay một tác vụ nền.

## 2. Resource trong REST là gì?

Resource là khái niệm mà API công bố để client tương tác. Resource được nhận diện bằng URI và được trao đổi thông qua các representation. Client không truy cập trực tiếp đối tượng trong bộ nhớ hoặc một hàng cơ sở dữ liệu; client gửi yêu cầu đến URI và nhận biểu diễn của tài nguyên theo media type đã thương lượng.

Một resource có thể là:

- Một đối tượng nghiệp vụ như đơn hàng hoặc khách hàng.
- Một tập hợp như danh sách đơn hàng.
- Một phần tài nguyên được truy cập độc lập, chẳng hạn địa chỉ giao hàng của khách hàng.
- Một kết quả hoặc khái niệm tổng hợp, chẳng hạn báo cáo doanh thu theo tháng.
- Một tài nguyên thể hiện một yêu cầu hoặc hành động, chẳng hạn yêu cầu hủy đơn hàng.

URI nhận diện resource; representation mô tả trạng thái hoặc dữ liệu mà API chọn công bố tại thời điểm phản hồi. Representation có thể chứa dữ liệu, metadata, liên kết và affordance. Với HAL, các liên kết được biểu diễn trong _links và những tài nguyên nhúng được biểu diễn trong _embedded.

Ví dụ, URI /api/orders/42 có thể nhận diện resource đơn hàng số 42. Representation trả về có thể chứa mã đơn hàng, trạng thái, các dòng hàng đã chọn và liên kết đến khách hàng. Một client khác có thể nhận biểu diễn rút gọn của cùng resource, tùy endpoint, quyền truy cập hoặc media type.

Resource không phải là bí danh bắt buộc của bảng cơ sở dữ liệu. API có thể gom nhiều bảng thành một representation, tách một domain concept thành nhiều resource hoặc cung cấp resource dẫn xuất không có hàng dữ liệu riêng. Điều quan trọng là resource có ý nghĩa ổn định với client và hỗ trợ các tương tác mà API muốn công bố.

## 3. Phân biệt domain model, persistence model và resource model

Ba mô hình này thường liên quan nhưng phục vụ những mục tiêu khác nhau:

| Mô hình | Câu hỏi chính | Mối quan tâm |
| --- | --- | --- |
| Domain model | Nghiệp vụ phải hoạt động theo quy tắc nào? | Hành vi, trạng thái, invariant, aggregate |
| Persistence model | Dữ liệu được lưu và truy vấn ra sao? | Bảng, khóa, quan hệ, chỉ mục, ORM |
| Resource/representation model | API công bố điều gì và client điều hướng thế nào? | URI, trường dữ liệu, media type, link relation, affordance |

Ví dụ, domain Order có thể sở hữu danh sách OrderLine để bảo vệ tính nhất quán của đơn hàng. Persistence model có thể lưu Order và OrderLine ở hai bảng riêng. Representation của /api/orders/42 có thể nhúng các dòng hàng vì client cần chúng để hiển thị chi tiết; API cũng có thể cung cấp /api/orders/42/items nếu dòng hàng cần được truy vấn hoặc phân trang độc lập.

Không có quy tắc một domain entity phải trở thành một resource riêng, hoặc một resource phải tương ứng với đúng một bảng. Chọn ranh giới dựa trên vòng đời, ý nghĩa nghiệp vụ, nhu cầu truy cập và mức độ độc lập mà client cần.

## 4. Chọn ranh giới resource từ domain

Một cách bắt đầu hữu ích là xác định các khái niệm nghiệp vụ và hành vi của chúng, sau đó quyết định client cần tương tác với khái niệm nào qua HTTP. Các câu hỏi sau giúp lựa chọn:

1. Khái niệm này có danh tính ổn định mà client cần tham chiếu không?
2. Nó có vòng đời hoặc trạng thái riêng không?
3. Client cần đọc, lọc, phân trang hoặc thao tác với nó độc lập không?
4. Nó có được quản lý bởi một aggregate khác không?
5. Thay đổi nó có cần tuân theo một quy tắc nhất quán riêng không?
6. Việc công bố nó có làm lộ chi tiết nội bộ hoặc tạo phụ thuộc không cần thiết cho client không?

### Aggregate root thường là điểm bắt đầu tốt

Trong mô hình domain có aggregate, aggregate root là điểm truy cập được kiểm soát vào các đối tượng con. Với hệ thống đơn hàng, Order có thể là aggregate root quản lý các OrderLine. Vì vậy, resource đơn hàng thường là một điểm bắt đầu hợp lý: client đọc đơn hàng và những dòng hàng thuộc đơn hàng đó thông qua một representation.

Tuy nhiên, aggregate boundary và resource boundary không phải một. Aggregate xác định phạm vi nhất quán của nghiệp vụ; resource xác định khái niệm API công bố. API có thể cung cấp một resource con để hỗ trợ truy vấn hoặc thao tác thuận tiện, nhưng thay đổi vẫn phải đi qua aggregate root để bảo vệ invariant.

Ví dụ, API có thể cho client xem /api/orders/42/items/3. Điều đó không có nghĩa client được phép cập nhật trực tiếp dòng hàng bằng cách bỏ qua Order. Nếu thay đổi số lượng cần tính lại tổng tiền, kiểm tra trạng thái và ghi nhận lịch sử, service phải tải aggregate Order, thực hiện hành vi tương ứng rồi lưu aggregate theo quy tắc nghiệp vụ.

### Khi nào nên nhúng đối tượng con?

Nhúng dữ liệu con vào representation của resource cha phù hợp khi:

- Đối tượng con chỉ có ý nghĩa trong phạm vi cha.
- Nó có vòng đời phụ thuộc vào cha.
- Client thường cần dữ liệu con cùng lúc với cha.
- Số lượng dữ liệu con nhỏ và có giới hạn hợp lý.

Ví dụ, một đơn hàng thường hiển thị các dòng hàng ngay trong trang chi tiết. Representation có thể chứa mảng items. Client nhận được một phản hồi đầy đủ để hiển thị đơn hàng mà không phải gọi từng dòng hàng.

### Khi nào nên tạo resource con riêng?

Resource con riêng hữu ích khi:

- Đối tượng con có thể được truy vấn hoặc phân trang độc lập.
- Số lượng phần tử lớn hoặc tăng không giới hạn.
- Client có nhu cầu lọc, tìm kiếm hoặc liên kết trực tiếp đến từng phần tử.
- Đối tượng con có vòng đời hoặc quyền truy cập riêng theo hợp đồng API.

Ví dụ, danh sách lịch sử giao dịch của đơn hàng có thể lớn. Thay vì nhúng toàn bộ lịch sử vào đơn hàng, API có thể cung cấp /api/orders/42/events với phân trang. Dù vậy, việc đọc lịch sử qua resource riêng không tự động cho phép client chỉnh sửa các sự kiện đó.

## 5. Thiết kế resource và URI

URI nên phản ánh danh tính hoặc tập hợp tài nguyên, có ý nghĩa ổn định với client và không để lộ cấu trúc bảng dữ liệu. Một cách tổ chức phổ biến:

| URI | Ý nghĩa |
| --- | --- |
| /api/orders | Tập hợp đơn hàng |
| /api/orders/42 | Một đơn hàng |
| /api/orders/42/items | Các dòng hàng của đơn hàng |
| /api/customers/7 | Một khách hàng |
| /api/orders/42/cancellation | Tài nguyên yêu cầu hủy hoặc điểm tương tác hủy theo hợp đồng API |

Tên collection thường dùng danh từ số nhiều. URI của một phần tử chứa định danh ổn định. Query parameter phù hợp để lọc, sắp xếp hoặc phân trang một tập hợp, ví dụ /api/orders?status=PENDING&page=0&size=20.

Không nên đưa tên bảng, tên cột hoặc chi tiết công nghệ lưu trữ vào URI, chẳng hạn /api/t_order_header hoặc /api/orders_table. Nếu thay đổi cơ sở dữ liệu làm thay đổi URI công khai, client sẽ bị phụ thuộc vào kiến trúc nội bộ.

Đối với hành vi nghiệp vụ, có thể chọn một trong hai cách tùy bản chất:

- Mô hình hóa hành động như một resource có vòng đời hoặc kết quả riêng. Ví dụ POST /api/orders/42/cancellations tạo một yêu cầu hủy và có thể trả về representation của yêu cầu đó.
- Công bố một liên kết affordance đến endpoint thực hiện chuyển trạng thái. Ví dụ quan hệ cancel trỏ đến URI mà client có thể dùng để yêu cầu hủy.

Không nên cố biến mọi method domain thành một endpoint riêng. Hãy chọn tương tác HTTP dựa trên ngữ nghĩa nghiệp vụ, tính idempotent, kết quả và hợp đồng mà client cần hiểu.

## 6. Ánh xạ domain model sang representation

Luồng ánh xạ thường có ba bước:

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Controller"]
    B --> C["Application service"]
    C --> D["Domain aggregate"]
    D --> C
    C --> E["Resource DTO"]
    E --> F["Representation assembler"]
    F --> G["EntityModel + links"]
    G --> H["HAL representation"]
~~~

Service truy xuất hoặc thay đổi domain model. Lớp ứng dụng chọn dữ liệu cần cung cấp cho trường hợp sử dụng. DTO mô tả phần dữ liệu API công khai. Assembler chuyển DTO thành RepresentationModel và gắn liên kết. Cách tách này cho phép thay đổi domain model mà không nhất thiết phải thay đổi cấu trúc representation.

Một DTO cho đơn hàng có thể như sau:

~~~java
import java.util.List;

public record OrderRepresentation(
        Long id,
        OrderStatus status,
        List<OrderItemRepresentation> items
) {
}

public record OrderItemRepresentation(
        Long productId,
        String productName,
        int quantity
) {
}
~~~

Trong dự án Java, mỗi kiểu public ở ví dụ trên được đặt trong file nguồn riêng tương ứng. Các DTO này là hợp đồng dữ liệu của API; chúng không cần kế thừa từ domain entity hoặc mang theo hành vi nghiệp vụ.

Domain model có thể chứa hành vi và trạng thái được đóng gói:

~~~java
import java.util.List;

public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}

public record OrderLine(
        Long productId,
        String productName,
        int quantity
) {
    public OrderLine {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}

public class Order {
    private final Long id;
    private final Long customerId;
    private final List<OrderLine> lines;
    private OrderStatus status;

    public Order(
            Long id,
            Long customerId,
            List<OrderLine> lines,
            OrderStatus status
    ) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("An order needs at least one item");
        }
        this.id = id;
        this.customerId = customerId;
        this.lines = List.copyOf(lines);
        this.status = status;
    }

    public Long id() {
        return id;
    }

    public Long customerId() {
        return customerId;
    }

    public List<OrderLine> lines() {
        return lines;
    }

    public OrderStatus status() {
        return status;
    }

    public boolean canBeCancelled() {
        return status == OrderStatus.PENDING;
    }

    public void cancel() {
        if (!canBeCancelled()) {
            throw new IllegalStateException("Only pending orders can be cancelled");
        }
        status = OrderStatus.CANCELLED;
    }
}
~~~

Đây là mô hình rút gọn để minh họa ranh giới. Trong ứng dụng thật, constructor thường được quản lý bởi factory hoặc repository; các quy tắc chuyển trạng thái có thể phát sinh domain event và cần phối hợp với transaction. Điều quan trọng là trạng thái và invariant được kiểm soát bởi domain model hoặc application service, không phụ thuộc vào việc client có nhìn thấy liên kết nào.

Các kiểu public OrderStatus, OrderLine và Order trong ví dụ được đặt ở những file Java riêng. Chúng được trình bày cùng một khối để người đọc thấy mối quan hệ giữa các thành phần.

Assembler chuyển domain model thành representation:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
public class OrderRepresentationAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        List<OrderItemRepresentation> items = order.lines().stream()
                .map(line -> new OrderItemRepresentation(
                        line.productId(),
                        line.productName(),
                        line.quantity()
                ))
                .toList();

        OrderRepresentation representation = new OrderRepresentation(
                order.id(),
                order.status(),
                items
        );

        EntityModel<OrderRepresentation> model = EntityModel.of(
                representation,
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel(),
                linkTo(methodOn(OrderController.class)
                        .all()).withRel("orders"),
                linkTo(methodOn(CustomerController.class)
                        .one(order.customerId())).withRel("customer")
        );

        if (order.canBeCancelled()) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.id())).withRel("cancel"));
        }

        return model;
    }
}
~~~

Ví dụ giả định OrderController có phương thức one, all và cancel; CustomerController có phương thức one nhận customerId. Assembler không trả nguyên Order ra JSON. Nó tạo representation chỉ gồm mã, trạng thái và các dòng hàng đã chọn, sau đó gắn liên kết self, orders, customer và cancel khi phù hợp.

Quan hệ customer cho phép client khám phá resource khách hàng. Client không cần tự tạo URI từ customerId. Liên kết cancel chỉ xuất hiện khi domain model cho biết đơn hàng còn có thể hủy. Khi client theo liên kết, service vẫn phải kiểm tra trạng thái trong transaction vì đơn hàng có thể đã được thanh toán sau khi representation được tạo.

## 7. Resource boundary và quyền sở hữu dữ liệu

Resource có thể liên quan đến nhiều aggregate hoặc nhiều bounded context. Ví dụ representation đơn hàng có thể chứa tên khách hàng để hiển thị nhanh, nhưng Customer vẫn là aggregate riêng. Khi đó, tên khách hàng được xem là một projection hoặc snapshot phù hợp với nhu cầu đọc; thay đổi hồ sơ khách hàng không nhất thiết làm thay đổi đơn hàng.

Một số lựa chọn thiết kế thường gặp:

| Cách thiết kế | Phù hợp khi | Điểm cần cân nhắc |
| --- | --- | --- |
| Nhúng dữ liệu khách hàng vào đơn hàng | Client luôn cần một vài trường khách hàng khi xem đơn hàng | Tránh sao chép quá nhiều dữ liệu hoặc gây nhầm lẫn quyền sở hữu |
| Gắn link customer | Client cần điều hướng đến hồ sơ khách hàng độc lập | Client có thể cần thêm một request để lấy chi tiết |
| Trả cả projection và link customer | Cần hiển thị nhanh nhưng vẫn cho phép mở hồ sơ đầy đủ | Phải xác định rõ dữ liệu nhúng chỉ là projection |

Nếu hai aggregate có vòng đời và quyền sở hữu độc lập, nên cân nhắc giữ chúng thành resource riêng và kết nối bằng link. Nếu một dữ liệu con chỉ có ý nghĩa trong aggregate cha, representation có thể nhúng nó hoặc cung cấp subresource đọc tùy nhu cầu client.

Không nên để API trở thành bản sao trực tiếp của sơ đồ quan hệ cơ sở dữ liệu. Một thay đổi bảng hoặc ORM mapping không nên buộc client phải thay đổi nếu ngữ nghĩa resource không đổi.

## 8. Thiết kế collection, item và subresource

### Collection resource

Collection đại diện cho tập hợp các resource cùng loại. Nó thường hỗ trợ lọc, sắp xếp và phân trang. Collection có liên kết self và có thể có các liên kết tạo mới hoặc điều hướng đến những collection liên quan.

Ví dụ, GET /api/orders trả về CollectionModel của các đơn hàng. Với tập hợp lớn, nên dùng PagedModel để cung cấp metadata trang và liên kết first, prev, next, last. Không nên trả toàn bộ dữ liệu không giới hạn chỉ vì nó dễ truy vấn.

### Item resource

Item resource đại diện cho một phần tử có danh tính riêng. Ví dụ GET /api/orders/42 trả về biểu diễn đơn hàng. Link self trỏ đến chính resource; các link khác có thể dẫn đến collection, customer hoặc thao tác được phép.

### Subresource

Subresource được truy cập qua quan hệ với resource cha, ví dụ /api/orders/42/items. Dùng subresource khi quan hệ cha-con có ý nghĩa với client hoặc khi dữ liệu con cần truy vấn độc lập. Nếu client chỉ cần một vài dòng hàng để hiển thị chi tiết đơn hàng, nhúng trong representation có thể đơn giản hơn.

Subresource không nhất thiết là aggregate riêng. Một endpoint đọc các dòng hàng có thể chỉ là projection của aggregate Order. Với thao tác ghi, service vẫn nên tải aggregate root và thực hiện thay đổi qua hành vi được domain cho phép.

## 9. Resource và hypermedia theo trạng thái

Một representation nên công bố các liên kết có ý nghĩa ở thời điểm phản hồi. Ví dụ:

| Trạng thái đơn hàng | Liên kết phù hợp có thể công bố |
| --- | --- |
| PENDING | self, orders, customer, cancel, payment |
| PAID | self, orders, customer, receipt |
| CANCELLED | self, orders, customer |

Bảng chỉ minh họa một hợp đồng. Tập liên kết thực tế phụ thuộc vào nghiệp vụ, quyền của người dùng và khả năng endpoint. Nếu người dùng không có quyền hủy đơn hàng, API có thể không công bố liên kết cancel cho người dùng đó. Endpoint vẫn phải kiểm tra quyền nếu client cố gọi URI đã lưu từ trước.

Hypermedia giúp client khám phá chuyển tiếp thông qua quan hệ link thay vì suy đoán đường dẫn. Client nên tìm rel như self, customer, cancel hoặc payment rồi theo href được trả về. Client không nên ghép URI từ ID hoặc phân tích đường dẫn để suy ra cấu trúc domain.

Khi bổ sung resource hoặc link relation mới, client cũ có thể bỏ qua quan hệ chưa biết. Tuy nhiên, thay đổi ý nghĩa của rel, xóa một liên kết mà client phụ thuộc hoặc đổi cấu trúc dữ liệu vẫn có thể phá vỡ hợp đồng. Vì vậy, rel và representation cần được quản lý như một phần của API contract.

## 10. Tổ chức controller và service

Controller nên điều phối giao tiếp HTTP, service thực hiện use case, còn assembler tạo representation. Một controller minh họa:

Application service có thể công bố một giao diện đơn giản cho use case của controller:

~~~java
import java.util.List;

public interface OrderService {
    Order getRequired(Long id);
    List<Order> findAll();
    void cancel(Long id);
}
~~~

Phần triển khai service chịu trách nhiệm tải aggregate, thực thi hành vi domain và lưu thay đổi trong transaction.

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderRepresentationAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderRepresentationAssembler assembler
    ) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    public EntityModel<OrderRepresentation> one(@PathVariable Long id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        return assembler.toCollectionModel(orderService.findAll())
                .add(linkTo(methodOn(OrderController.class)
                        .all()).withSelfRel());
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(@PathVariable Long id) {
        orderService.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

OrderService trong ví dụ đại diện cho application service, có thể phối hợp repository và domain model trong transaction. Phương thức cancel nên gọi hành vi domain tương ứng, lưu thay đổi và phát sinh sự kiện cần thiết. Controller không tự thay đổi trường status vì làm như vậy sẽ bỏ qua nơi bảo vệ invariant.

Nếu ứng dụng cần trả representation của kết quả hủy, service có thể trả về Order sau khi cập nhật và controller có thể chuyển nó qua assembler. Nếu API mô hình hóa cancellation thành resource riêng, endpoint có thể trả 201 Created cùng Location đến resource yêu cầu hủy. Hãy chọn status code và response theo ý nghĩa nghiệp vụ của thao tác.

## 11. Kiểm thử ranh giới domain và representation

Kiểm thử domain và kiểm thử API trả lời hai nhóm câu hỏi khác nhau. Kiểm thử domain xác nhận invariant và chuyển trạng thái đúng. Kiểm thử representation xác nhận dữ liệu công khai, link relation và media type phù hợp với hợp đồng.

Ví dụ kiểm thử quy tắc domain:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.Test;

class OrderTest {

    @Test
    void pendingOrderCanBeCancelled() {
        Order order = new Order(
                42L,
                7L,
                List.of(new OrderLine(100L, "Keyboard", 1)),
                OrderStatus.PENDING
        );

        order.cancel();

        assertEquals(OrderStatus.CANCELLED, order.status());
    }

    @Test
    void paidOrderCannotBeCancelled() {
        Order order = new Order(
                42L,
                7L,
                List.of(new OrderLine(100L, "Keyboard", 1)),
                OrderStatus.PAID
        );

        assertThrows(IllegalStateException.class, order::cancel);
    }
}
~~~

Kiểm thử assembler hoặc controller nên xác nhận:

- Representation chỉ chứa trường API đã chọn, không vô tình làm lộ trường nội bộ.
- Mỗi order có link self và link đến collection.
- Link customer trỏ đến resource khách hàng đúng định danh.
- Link cancel chỉ xuất hiện khi trạng thái và quyền cho phép.
- Các dòng hàng được nhúng hoặc công bố qua subresource theo thiết kế đã chọn.
- HAL được trả về với media type application/hal+json khi client yêu cầu.

Không nên chỉ kiểm tra URL tuyệt đối trong test vì host, cổng và context path có thể thay đổi. Ưu tiên kiểm tra rel và xác nhận URI dẫn đến endpoint đúng. Với thao tác thay đổi trạng thái, cần có kiểm thử tích hợp để đảm bảo service kiểm tra lại invariant ngay cả khi client gửi một URI đã cũ.

## 12. Những sai lầm thường gặp

**Đồng nhất resource với bảng dữ liệu.** Bảng lưu trữ phục vụ persistence; resource phục vụ hợp đồng API. Hãy chọn resource theo ý nghĩa và cách client tương tác.

**Trả trực tiếp entity domain hoặc entity ORM.** Việc này có thể làm lộ trạng thái nội bộ, quan hệ persistence hoặc trường không nên công khai. Hãy tạo representation DTO rõ ràng.

**Tách mọi đối tượng con thành endpoint độc lập.** Quá nhiều resource nhỏ có thể khiến client phải thực hiện nhiều request và hiểu các chi tiết không cần thiết. Hãy cân nhắc nhúng dữ liệu con nếu vòng đời phụ thuộc vào cha và số lượng có giới hạn.

**Nhúng toàn bộ dữ liệu con không giới hạn.** Representation có thể trở nên lớn và tốn kém. Với danh sách lớn hoặc cần phân trang, hãy cung cấp subresource hoặc collection riêng.

**Để controller thay đổi domain state trực tiếp.** Thay đổi phải đi qua hành vi nghiệp vụ hoặc application service để giữ invariant.

**Xem link hypermedia như quyền truy cập.** Link chỉ công bố khả năng; server phải xác thực và phân quyền lại khi nhận request.

**Để URI phụ thuộc vào cấu trúc nội bộ.** Dùng URI ổn định theo resource và tạo link từ mapping controller hoặc cơ chế URI builder của ứng dụng.

## 13. Ghi nhớ

Domain model mô tả nghiệp vụ, hành vi và invariant; resource mô tả khái niệm API công bố qua URI; representation là dữ liệu và liên kết được gửi cho client. Persistence model lại phục vụ lưu trữ và truy vấn. Ba mô hình có thể liên hệ nhưng không cần trùng nhau.

Aggregate root thường là điểm bắt đầu tốt để xác định resource, nhưng aggregate boundary không quyết định cứng resource boundary. Dữ liệu con có thể được nhúng khi nó phụ thuộc vào cha và thường được đọc cùng nhau; subresource phù hợp khi dữ liệu cần truy vấn, phân trang hoặc điều hướng độc lập. Resource nên được thiết kế theo vòng đời, ý nghĩa và nhu cầu client, không theo từng bảng dữ liệu.

Trong Spring HATEOAS, DTO xác định dữ liệu công khai, RepresentationModelAssembler ánh xạ domain model thành EntityModel hoặc CollectionModel, còn WebMvcLinkBuilder tạo link theo mapping controller. Link relation nên phản ánh khả năng và trạng thái hiện tại. Service và domain model vẫn phải bảo vệ invariant, xác thực và phân quyền khi client thực hiện thao tác.
