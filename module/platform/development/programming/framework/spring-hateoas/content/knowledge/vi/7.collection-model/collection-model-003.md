# Link của collection

Trong REST API, một **collection resource** đại diện cho một tập hợp tài nguyên cùng loại, ví dụ `/orders` đại diện cho tập hợp đơn hàng. Representation của collection thường chứa các phần tử hoặc thông tin về chúng, đồng thời có thể cung cấp các link mô tả chính collection, cách tìm kiếm, cách tạo phần tử mới và cách chuyển giữa các trang.

Spring HATEOAS dùng `CollectionModel<T>` để biểu diễn một tập hợp các representation model. Các link gắn trực tiếp vào `CollectionModel` mô tả collection ở cấp tập hợp; link nằm trong từng `EntityModel` mô tả từng phần tử. Phân biệt hai cấp này giúp client hiểu mình đang điều hướng collection hay đang thao tác với một tài nguyên cụ thể.

## Link cấp collection và link cấp phần tử

Giả sử API quản lý đơn hàng có hai URI:

- `/orders`: collection resource chứa các đơn hàng.
- `/orders/42`: tài nguyên đơn hàng có mã `42`.

Collection có thể có link `self` trỏ tới `/orders`. Mỗi phần tử trong collection có thể có link `self` trỏ tới URI riêng của nó. Nếu collection có link `create`, link đó mô tả điểm vào để tạo một đơn hàng mới. Nếu collection có link `search`, client có thể khám phá cách tìm kiếm hoặc lọc tập hợp.

| Vị trí của link | Link thường mô tả | Ví dụ relation |
| --- | --- | --- |
| Trên `CollectionModel` | Chính collection, thao tác trên tập hợp, tìm kiếm, phân trang | `self`, `search`, `create`, `next` |
| Trên từng `EntityModel` | Một phần tử cụ thể và các thao tác trên phần tử đó | `self`, `customer`, `cancel`, `update` |

Một collection có thể chứa hàng trăm phần tử, nhưng link `self` của collection vẫn chỉ một URI đại diện cho tập hợp. Không nên dùng link `self` của collection thay cho link `self` của từng đơn hàng. Client cần relation đúng cấp để biết nó đang truy cập danh sách hay một đơn hàng cụ thể.

## Các relation thường gặp trên collection

### `self`: chính collection hiện tại

`self` trỏ tới representation collection đang được trả về. Nếu request có tham số lọc hoặc phân trang, URI `self` nên nhận diện đúng collection view hiện tại, bao gồm những tham số có ảnh hưởng tới kết quả.

Ví dụ, `/orders?status=PENDING&page=1&size=20` là một view của collection đơn hàng. Link `self` trong response nên giúp client truy cập lại đúng view đó. Khi client đi theo link `next`, server có thể trả một representation khác với link `self` mới tương ứng trang mới.

### `search`: khám phá khả năng tìm kiếm

`search` có thể trỏ tới một URI template hoặc tài nguyên mô tả cách tìm kiếm collection. URI template cho phép client điền các biến như trạng thái, ngày tạo hoặc từ khóa. Ví dụ:

```text
/orders{?status,createdAfter,page,size}
```

Đây là URI template với các biến query tùy chọn. Trong HAL, một link template có thể được biểu diễn với thuộc tính `templated: true`. Client cần hiểu URI template theo định dạng được API công bố trước khi mở rộng nó.

### `create`: điểm vào tạo phần tử mới

Một collection thường là điểm vào phù hợp để tạo phần tử mới bằng `POST`. API có thể công bố relation `create` trỏ tới URI collection hoặc một tài nguyên biểu mẫu tạo mới. `create` trong ví dụ là relation do API quy ước; nếu nhiều hệ thống cần dùng chung relation này, nên công bố một định nghĩa relation ổn định, chẳng hạn bằng URI tài liệu.

Một link đơn thuần chỉ cho biết đích đến. Nó không tự mô tả đầy đủ HTTP method, request body hoặc các trường bắt buộc. Nếu client cần mô tả tương tác tạo mới, có thể gắn affordance với link và dùng media type có khả năng biểu diễn affordance, chẳng hạn HAL-FORMS.

### Link phân trang: `first`, `prev`, `next`, `last`

Khi collection được chia thành nhiều trang, response có thể cung cấp các relation điều hướng:

- `first`: trang đầu tiên.
- `prev`: trang ngay trước trang hiện tại, nếu có.
- `next`: trang kế tiếp, nếu có.
- `last`: trang cuối cùng, nếu server có thể xác định.
- `self`: trang hiện tại.

Các relation này giúp client điều hướng theo link server trả về thay vì tự tính số trang hoặc ghép query parameter. Ở trang đầu, `prev` thường không xuất hiện; ở trang cuối, `next` thường không xuất hiện. Client cần xử lý trường hợp link không có như một phần bình thường của hợp đồng hypermedia.

## Tạo link collection bằng Spring HATEOAS

`CollectionModel<T>` có thể được tạo từ danh sách model và các link dành cho collection. Ví dụ dưới đây dùng assembler để tạo representation cho từng đơn hàng, sau đó gắn các link cấp collection:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.List;
import java.util.stream.Collectors;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderRepository repository;
    private final OrderModelAssembler assembler;

    OrderController(OrderRepository repository, OrderModelAssembler assembler) {
        this.repository = repository;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EntityModel<OrderRepresentation>> all() {
        List<EntityModel<OrderRepresentation>> items = repository.findAll().stream()
            .map(assembler::toModel)
            .collect(Collectors.toList());

        Link self = linkTo(methodOn(OrderController.class).all())
            .withSelfRel();

        Link create = linkTo(methodOn(OrderController.class).create(null))
            .withRel("create")
            .andAffordance(afford(methodOn(OrderController.class).create(null)));

        return CollectionModel.of(items, self, create);
    }

    @PostMapping
    ResponseEntity<?> create(@RequestBody CreateOrderRequest request) {
        // Gọi application service để tạo đơn hàng và trả kết quả phù hợp.
        return ResponseEntity.accepted().build();
    }
}
```

`OrderRepository`, `OrderModelAssembler`, `OrderRepresentation` và `CreateOrderRequest` là các kiểu thuộc ứng dụng. Phần thân của `create` được lược giản để tập trung vào cách xây link. `methodOn(...)` mô phỏng lời gọi phương thức controller để Spring HATEOAS suy ra URI từ mapping; nó không thực thi nghiệp vụ tạo đơn hàng.

`self` được tạo từ phương thức GET `all()`. Link `create` trỏ tới cùng URI collection nhưng gắn quan hệ tạo mới; affordance lấy metadata tương tác từ phương thức POST `create(...)`. Nếu response dùng HAL JSON thông thường, client nhận được link nhưng định dạng này không nhất thiết biểu diễn toàn bộ affordance. Khi cần mô tả method và request body cho client, hãy chọn media type hỗ trợ affordance và cấu hình tương ứng.

Với một collection không cần affordance, có thể tạo link đơn giản:

```java
CollectionModel<EntityModel<OrderRepresentation>> model =
    CollectionModel.of(items,
        linkTo(methodOn(OrderController.class).all()).withSelfRel(),
        linkTo(methodOn(CustomerController.class).all()).withRel("customers"));
```

Link `customers` ở ví dụ này cho phép client điều hướng từ collection đơn hàng tới một collection liên quan. Relation cần phản ánh ý nghĩa của đích đến và được duy trì ổn định trong hợp đồng API.

## Link tìm kiếm và URI template

Nếu collection hỗ trợ lọc theo trạng thái và phân trang, API có thể công bố một link `search` dạng template. Ví dụ sau minh họa một URI template tương đối từ gốc ứng dụng:

```java
import org.springframework.hateoas.Link;

Link search = Link.of("/orders{?status,createdAfter,page,size}", "search");

CollectionModel<EntityModel<OrderRepresentation>> model =
    CollectionModel.of(items, self, search);
```

Khi triển khai thực tế, cần bảo đảm URI template phản ánh đúng route, query parameter và context path của ứng dụng. Client có thể mở rộng template bằng giá trị phù hợp, ví dụ `status=PENDING` và `page=0`. Server vẫn phải xác thực và kiểm tra các giá trị lọc, giới hạn kích thước trang, đồng thời áp dụng phân quyền cho kết quả trả về.

Ví dụ HAL rút gọn cho link template:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders"
    },
    "search": {
      "href": "https://api.example.com/orders{?status,createdAfter,page,size}",
      "templated": true
    }
  }
}
```

Link template mô tả cách tạo URI theo một mẫu được công bố. Client không nên đoán tên tham số hoặc tự thêm tham số ngoài hợp đồng.

## Phân trang và link điều hướng collection

Với collection lớn, không nên tải tất cả phần tử trong một response. Spring Data và Spring HATEOAS có thể phối hợp để tạo `PagedModel` từ một `Page<T>`. `PagedResourcesAssembler` giúp chuyển page thành representation phân trang và tạo các link điều hướng tương ứng. Nếu endpoint cần phân trang, dùng phương thức `all(...)` dưới đây thay cho phương thức `all()` đơn giản ở ví dụ trước; hai phương thức không phải hai mapping đồng thời trên cùng route.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;

@GetMapping
PagedModel<EntityModel<OrderRepresentation>> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = repository.findAll(pageable);
    return pagedAssembler.toModel(page, assembler);
}
```

Ví dụ giả định `OrderModelAssembler` triển khai `RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>>`, còn repository hỗ trợ truy vấn theo `Pageable`. `PagedResourcesAssembler` tạo `PagedModel` có metadata phân trang và các link điều hướng phù hợp với trang hiện tại. Các link phổ biến gồm `first`, `prev`, `self`, `next` và `last` khi trang tương ứng tồn tại.

Không nên buộc client tự tăng `page` hoặc tính `last` bằng tổng số phần tử. Server có thể thay đổi chiến lược phân trang hoặc cấu trúc URI; client theo link sẽ ít phụ thuộc hơn vào cách triển khai. Với cursor pagination, relation vẫn có thể là `next` và `prev`, dù giá trị trong URI là cursor thay vì số trang.

## Collection link trong HAL JSON

Trong HAL JSON, link của collection nằm dưới `_links`. Các phần tử được nhúng có thể nằm dưới `_embedded`; relation dùng làm tên phần tử nhúng phụ thuộc cấu hình relation của model. Ví dụ minh họa sau tập trung vào các link cấp collection và lược bỏ phần tử:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders"
    },
    "create": {
      "href": "https://api.example.com/orders"
    },
    "search": {
      "href": "https://api.example.com/orders{?status,page,size}",
      "templated": true
    },
    "next": {
      "href": "https://api.example.com/orders?page=1&size=20"
    }
  }
}
```

`create` và `self` có thể cùng trỏ tới một URI nhưng biểu thị quan hệ khác nhau. `self` nhận diện collection; `create` biểu thị tương tác tạo phần tử mới theo hợp đồng do API công bố. Nếu client cần biết `create` dùng POST và yêu cầu body nào, hãy dùng affordance với định dạng hỗ trợ thay vì suy ra chỉ từ URL.

## Nguyên tắc thiết kế link collection

- **Đặt link đúng cấp:** link của collection nằm trên `CollectionModel`; link của phần tử nằm trên model phần tử.
- **Chọn relation theo ý nghĩa:** `self`, `next`, `prev`, `first`, `last` có ngữ nghĩa điều hướng rõ; relation nghiệp vụ tùy chỉnh cần được định nghĩa và giữ ổn định.
- **Tạo URI từ mapping:** ưu tiên `linkTo(...)` và `methodOn(...)` để hạn chế ghép chuỗi URL thủ công.
- **Không phát link vô nghĩa:** chỉ công bố `next` khi còn trang tiếp theo; chỉ công bố thao tác khi nó khả dụng với ngữ cảnh hiện tại.
- **Phân biệt link và affordance:** link chỉ ra đích đến; affordance có thể mô tả phương thức và dữ liệu tương tác nếu media type hỗ trợ.
- **Giữ hợp đồng nhất quán:** thay đổi relation hoặc ý nghĩa của link có thể ảnh hưởng client dù dữ liệu collection không đổi.
- **Kiểm soát dữ liệu:** link không thay thế xác thực, phân quyền hoặc kiểm tra đầu vào ở endpoint đích.

## Kiểm thử link của collection

Nên kiểm thử response HTTP thực tế thay vì chỉ kiểm tra danh sách link trong unit test. Với MockMvc và HAL JSON, có thể xác nhận link collection và link phân trang:

```java
mockMvc.perform(get("/orders?page=0&size=20")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.create.href").exists());
```

Với endpoint phân trang, kiểm tra `next` xuất hiện khi còn trang sau và vắng mặt ở trang cuối. Kiểm tra thêm rằng URI `self` giữ các bộ lọc và tham số trang hiện tại, URI `next` chuyển đúng trang, và link của từng phần tử trỏ tới đúng tài nguyên. Nếu dùng URI template, xác nhận `templated` được tuần tự hóa và tên biến đúng với contract.

Một collection representation tốt cho client biết collection hiện tại là gì, có thể tìm kiếm hoặc tạo phần tử ra sao, và tiếp tục điều hướng thế nào. Khi dùng `CollectionModel`, hãy thiết kế link ở cấp tập hợp một cách có chủ đích, giữ link từng phần tử riêng biệt và để client khám phá đường đi qua relation thay vì phụ thuộc vào cách server ghép URL.
