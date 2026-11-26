# Quy ước self relation

Trong hypermedia, **`self` relation** là quan hệ liên kết dùng để trỏ tới chính tài nguyên đang được biểu diễn. Khi một REST API trả về đơn hàng `/orders/42`, representation có thể chứa link `self` với `href` trỏ tới URI của đơn hàng đó. Client có thể dùng link này để truy cập lại tài nguyên mà không phải tự ghép URL từ mã đơn hoặc ghi nhớ cấu trúc route.

Spring HATEOAS cung cấp `withSelfRel()` và hằng `IanaLinkRelations.SELF` để tạo link theo quy ước này. Link `self` là một phần của hợp đồng hypermedia: nó giúp client nhận biết URI của tài nguyên hiện tại, trong khi server vẫn có thể thay đổi cấu trúc URL nội bộ và cập nhật `href` tương ứng.

## Ý nghĩa của self relation

Relation `self` là một link relation chuẩn được đăng ký trong IANA Link Relation Type Registry. Nó biểu thị một liên kết tới chính tài nguyên đang được đề cập. Trong HAL JSON, link này thường nằm dưới `_links.self`.

Ví dụ representation đơn hàng:

```json
{
  "id": 42,
  "status": "PENDING",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    }
  }
}
```

`href` là URI để client truy cập lại đơn hàng; `self` là ý nghĩa của link. Client nên đọc relation thay vì suy ra URL từ trường `id` hoặc một quy tắc ghép đường dẫn được viết cứng.

Self link nhận diện tài nguyên trong ngữ cảnh API. Nó không phải cơ chế xác thực hoặc phân quyền, cũng không đảm bảo người gọi nào cũng có thể truy cập URI. Endpoint đích vẫn phải kiểm tra danh tính, quyền truy cập và trạng thái nghiệp vụ như bình thường.

## Self link không phải link hành động

`self` và các relation hành động có mục đích khác nhau:

| Relation | Ý nghĩa | Ví dụ đích |
| --- | --- | --- |
| `self` | Chính tài nguyên hiện tại | `/orders/42` |
| `collection` | Collection chứa tài nguyên hoặc nhóm tài nguyên liên quan | `/orders` |
| `customer` | Khách hàng liên quan tới đơn hàng | `/customers/7` |
| `cancel` | Điểm vào thao tác hủy do API định nghĩa | `/orders/42/cancellation` |

Một đơn hàng có thể đồng thời có link `self`, `customer` và `cancel`. Link `self` cho phép client lấy lại đơn hàng; link `cancel` biểu thị một tương tác khác. Không dùng `self` để thay cho link thao tác cập nhật, hủy hoặc thanh toán.

Link `self` cũng không mô tả đầy đủ HTTP method hoặc request body. Nếu cần mô tả thao tác, hãy công bố relation riêng và cân nhắc affordance với media type hỗ trợ, chẳng hạn HAL-FORMS.

## Tạo self link bằng Spring HATEOAS

`WebMvcLinkBuilder` giúp xây dựng URI từ mapping của controller. `linkTo(...)` chọn controller hoặc phương thức đích; `methodOn(...)` tạo lời gọi mô phỏng để Spring HATEOAS đọc mapping và tham số. Lời gọi mô phỏng này không thực thi logic của phương thức controller.

Ví dụ DTO biểu diễn đơn hàng:

```java
import java.math.BigDecimal;

public record OrderRepresentation(
    Long id,
    String status,
    BigDecimal total
) {}
```

Assembler chuyển domain object thành `EntityModel` và gắn self link:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        OrderRepresentation body = new OrderRepresentation(
            order.getId(),
            order.getStatus().name(),
            order.getTotal()
        );

        return EntityModel.of(body,
            linkTo(methodOn(OrderController.class).one(order.getId()))
                .withSelfRel());
    }
}
```

`Order` và `OrderController` là các kiểu thuộc ứng dụng minh họa. `withSelfRel()` tạo link có relation `self`. Cách dựng URI từ mapping giúp link đồng bộ với route controller và giảm việc nối chuỗi thủ công.

Controller có thể trả model do assembler tạo:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository repository;
    private final OrderModelAssembler assembler;

    OrderController(OrderRepository repository, OrderModelAssembler assembler) {
        this.repository = repository;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    EntityModel<OrderRepresentation> one(@PathVariable Long id) {
        Order order = repository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
        return assembler.toModel(order);
    }
}
```

`OrderRepository` và `OrderNotFoundException` là thành phần của ứng dụng. Controller tập trung lấy tài nguyên và trả model; assembler chịu trách nhiệm chuyển đổi dữ liệu và gắn self link. Cách tổ chức này giúp quy tắc biểu diễn được dùng lại ở nhiều endpoint.

## Dùng IanaLinkRelations.SELF

Ngoài `withSelfRel()`, có thể tạo link bằng relation chuẩn `IanaLinkRelations.SELF`:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link self = Link.of("https://api.example.com/orders/42",
    IanaLinkRelations.SELF);
```

Hai cách thể hiện cùng một relation. Trong phần lớn trường hợp, `withSelfRel()` trên link builder dễ đọc hơn vì nêu rõ ý định ngay tại nơi dựng URI. `IanaLinkRelations.SELF` hữu ích khi tạo `Link` từ một URI đã có hoặc khi cần truyền relation như một giá trị riêng.

## Self link cho collection và trang hiện tại

Self link không chỉ dùng cho tài nguyên đơn lẻ. Collection cũng là một tài nguyên và representation collection có thể có link `self` trỏ tới chính collection đó.

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;

CollectionModel<EntityModel<OrderRepresentation>> model =
    CollectionModel.of(items,
        linkTo(methodOn(OrderController.class).all()).withSelfRel());
```

Với collection có lọc hoặc phân trang, self link nên nhận diện đúng view hiện tại, bao gồm những query parameter làm thay đổi kết quả. Ví dụ `/orders?status=PENDING&page=1&size=20` là một view cụ thể của collection. Link `self` nên đưa client trở lại đúng view đó.

Nếu controller nhận các tham số lọc và phân trang, có thể đưa chúng vào lời gọi mô phỏng:

```java
Link self = linkTo(methodOn(OrderController.class)
    .list("PENDING", 1, 20)).withSelfRel();
```

Ví dụ giả định `list(status, page, size)` là mapping GET của collection. Với endpoint phân trang Spring Data, `PagedResourcesAssembler` có thể tạo `PagedModel` và các link `self`, `first`, `prev`, `next`, `last` dựa trên `Page` và request hiện tại. Tránh thêm một self link thứ hai nếu assembler đã tạo link đó.

## Self link và URI của request hiện tại

Đôi khi ứng dụng muốn dùng chính URI của request hiện tại làm self link, chẳng hạn khi endpoint có query parameter động. Spring cung cấp `ServletUriComponentsBuilder` để đọc URI từ request đang được xử lý:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

String currentUri = ServletUriComponentsBuilder
    .fromCurrentRequest()
    .build()
    .toUriString();

Link self = Link.of(currentUri, IanaLinkRelations.SELF);
```

Cách này lấy URI request hiện tại, bao gồm query string hiện tại. Nó hữu ích khi cần phản ánh chính xác filter hoặc tham số đã gửi. Tuy nhiên, chỉ dùng khi URI request thực sự là URI mà API muốn công bố cho tài nguyên. Nếu request có tham số tạm thời, tracking parameter hoặc các tham số không thuộc định danh representation, cần cân nhắc loại bỏ chúng.

Khi dùng `linkTo(methodOn(...))`, URI được suy ra từ mapping controller và các đối số cụ thể. Cách này thường phù hợp khi muốn công bố URI ổn định theo route của tài nguyên. Không nên tạo self link bằng cách nối chuỗi từ host hoặc path thủ công vì dễ sai khi ứng dụng đổi context path, chạy sau reverse proxy hoặc thay đổi mapping.

## Self link, canonical URI và content negotiation

Self link là URI tham chiếu tới tài nguyên trong hợp đồng hypermedia. Trong nhiều API, đó cũng là URI ổn định để truy cập tài nguyên. Tuy nhiên, cần phân biệt self relation với khái niệm canonical URL trong SEO hoặc với một snapshot bất biến của representation.

Cùng một URI có thể trả về các representation khác nhau tùy `Accept`, quyền của người gọi hoặc trạng thái hiện tại của tài nguyên. Ví dụ client có thể yêu cầu `application/hal+json` hoặc một media type khác mà server hỗ trợ. Self link vẫn nhận diện tài nguyên; media type và content negotiation quyết định dạng biểu diễn được trả về.

Với tài nguyên đơn lẻ, thường nên dùng URI định danh ổn định như `/orders/42`. Với collection có filter hoặc phân trang, self link thường bao gồm query parameter xác định view hiện tại. Hãy xác định rõ API đang coi các tham số nào là một phần của view để tránh self link không thể tái tạo response mong muốn.

## Self link trong HAL JSON

Khi representation được serialize theo HAL JSON, self link nằm trong `_links.self`:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/customers/7"
    }
  }
}
```

Client có thể tìm `_links.self.href` để truy cập lại đơn hàng. Nếu có nhiều link cùng một relation, HAL có thể biểu diễn chúng dưới dạng danh sách; với self link của một tài nguyên, thông thường chỉ công bố một đích self rõ ràng để tránh client phải lựa chọn giữa nhiều URI không phân biệt.

## Kiểm thử self relation

Nên kiểm tra self link trong response HTTP cuối cùng để xác nhận assembler đã được gọi, link được tạo đúng và serializer xuất relation đúng định dạng. Ví dụ với MockMvc:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists());
```

Test có thể kiểm tra thêm `href` kết thúc bằng `/orders/42` theo cấu hình ứng dụng, hoặc dùng matcher để xác nhận toàn bộ URI mong muốn. Với collection, kiểm tra self link giữ lại filter và tham số trang hiện tại. Nếu ứng dụng chạy sau reverse proxy hoặc có context path, nên kiểm thử URI được tạo trong cấu hình triển khai tương ứng.

Các lỗi thường gặp:

- **Self link trỏ sai tài nguyên:** dùng nhầm mapping collection hoặc truyền sai ID vào `methodOn(...)`.
- **Tự nối URI:** làm mất context path, scheme hoặc host đúng khi chạy sau proxy.
- **Mất query parameter:** self link của collection không tái tạo được filter/sort/page hiện tại.
- **Thêm trùng self link:** assembler và controller cùng gắn relation `self`, khiến response có nhiều link không cần thiết.
- **Nhầm self với quyền truy cập:** có link không có nghĩa người gọi chắc chắn được phép truy cập endpoint.
- **Nhầm self với affordance:** self chỉ định danh tài nguyên, không mô tả thao tác cập nhật hoặc hủy.

Quy ước self relation giúp client nhận biết URI của tài nguyên hoặc view collection hiện tại qua hypermedia. Khi tạo link từ mapping bằng Spring HATEOAS, giữ query parameter có ý nghĩa, tránh link trùng và kiểm thử response HAL, API có thể thay đổi route nội bộ mà client vẫn điều hướng dựa trên relation ổn định.
