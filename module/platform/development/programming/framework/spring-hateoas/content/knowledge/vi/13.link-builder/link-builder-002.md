# linkTo

`linkTo(...)` là điểm vào quen thuộc của Spring HATEOAS để tạo URI từ mapping của Spring MVC. Thay vì tự ghép chuỗi như `"/orders/" + id`, ứng dụng có thể yêu cầu Spring HATEOAS đọc mapping trên controller và phương thức, sau đó tạo một `Link` trỏ đến endpoint tương ứng.

Khi kết hợp `linkTo(...)` với `methodOn(...)`, link được tạo từ cả mapping cấp controller, mapping cấp phương thức và các tham số của lời gọi mô phỏng. Cách làm này giúp link theo sát hợp đồng HTTP mà controller công bố, giảm lỗi khi đổi path hoặc thêm query parameter.

Trong một API Spring HATEOAS, link được tạo thường được gắn vào `EntityModel`, `CollectionModel` hoặc một lớp kế thừa `RepresentationModel`. Client đọc relation để hiểu ý nghĩa liên kết và dùng href để điều hướng. Bài học này tập trung vào API `linkTo`: tạo link cho controller và method, truyền path variable và request parameter, tích hợp vào assembler, xử lý URI encoding, context path và kiểm thử kết quả.

Sau bài học, bạn có thể:

- Giải thích vai trò của `WebMvcLinkBuilder.linkTo(...)` trong Spring HATEOAS.
- Phân biệt link đến mapping cấp controller với link đến một phương thức cụ thể.
- Dùng `methodOn(...)` để tạo link từ mapping và tham số của controller.
- Tạo link self, collection và link hành động bằng relation phù hợp.
- Xây link cho path variable, query parameter và các endpoint có mapping lồng nhau.
- Tổ chức logic tạo link trong `RepresentationModelAssembler`.
- Tránh ghép URI thủ công và xử lý đúng context path, forwarded headers.
- Kiểm thử href được tạo từ controller mapping bằng MockMvc.

## 1. Vì sao nên dùng linkTo?

Giả sử ứng dụng quản lý đơn hàng có endpoint:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderRepresentation one(@PathVariable UUID id) {
        // ...
    }
}
~~~

Đường dẫn đến một đơn hàng được hình thành từ mapping cấp lớp `/orders` và mapping cấp phương thức `/{id}`. Nếu assembler tự ghép URI:

~~~java
String href = "/orders/" + order.getId();
~~~

thì chuỗi `/orders` và cấu trúc path bị lặp lại ở nhiều nơi. Khi controller đổi thành `/api/orders`, các chuỗi ghép thủ công có thể bị quên cập nhật.

Dùng `linkTo(...)` để lấy đường dẫn từ metadata mapping:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();
~~~

Spring HATEOAS đọc mapping của `OrderController.one(...)`, nhận giá trị `id` và dựng URI cho endpoint đó. Nếu mapping thay đổi, link được tạo từ mapping mới thay vì phụ thuộc vào một chuỗi path được sao chép trong assembler.

Điều này giúp giảm sự trùng lặp đường dẫn và giữ link nhất quán với controller. Nó không tự bảo đảm mọi thay đổi API đều tương thích; relation, dữ liệu và ngữ nghĩa HTTP vẫn cần được quản lý như một phần hợp đồng công khai.

## 2. WebMvcLinkBuilder và các hàm chính

Trong ứng dụng Spring MVC, lớp thường dùng là:

~~~java
org.springframework.hateoas.server.mvc.WebMvcLinkBuilder
~~~

Hai hàm tĩnh quan trọng:

- `linkTo(...)`: tạo một link builder từ controller class, method invocation hoặc thông tin mapping.
- `methodOn(...)`: tạo proxy mô phỏng controller để ghi nhận phương thức được gọi cùng các tham số.

Thông thường, ta import tĩnh hai hàm:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

### 2.1. linkTo với controller class

Khi truyền controller class, link builder xác định URI theo mapping cấp lớp:

~~~java
Link orders = linkTo(OrderController.class)
    .withRel("orders");
~~~

Nếu controller khai báo:

~~~java
@RequestMapping("/orders")
public class OrderController {
    // ...
}
~~~

thì link trỏ đến URI gắn với mapping `/orders` trong ngữ cảnh request hiện tại. Cách này phù hợp khi muốn tạo link đến collection hoặc entry point của controller.

`linkTo(OrderController.class)` chưa chỉ ra một phương thức cụ thể. Nếu cần đường dẫn có path variable, query parameter hoặc mapping riêng ở cấp method, dùng `methodOn(...)`.

### 2.2. linkTo với methodOn

Mẫu phổ biến:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
~~~

Có hai bước:

1. `methodOn(OrderController.class).one(orderId)` mô tả lời gọi đến phương thức `one` với giá trị `orderId`.
2. `linkTo(...)` đọc mapping và tham số của lời gọi mô phỏng để tạo link builder.

Sau đó `withSelfRel()` chuyển builder thành `Link` có relation `self`.

Lời gọi `methodOn(...)` không thực thi logic nghiệp vụ trong controller. Nó tạo proxy và ghi nhận thông tin lời gọi để Spring HATEOAS xây URI. Vì vậy, không nên đặt truy vấn cơ sở dữ liệu, kiểm tra quyền hoặc side effect trong phần được dùng để mô tả link.

### 2.3. Phương thức controller phải có mapping

Để link builder xác định URI, phương thức cần được ánh xạ bằng các annotation Spring MVC như:

- `@GetMapping`
- `@PostMapping`
- `@PutMapping`
- `@PatchMapping`
- `@DeleteMapping`
- `@RequestMapping`

Ví dụ:

~~~java
@GetMapping("/{id}")
public OrderRepresentation one(@PathVariable("id") UUID id) {
    // ...
}
~~~

Spring HATEOAS dùng mapping và annotation tham số để xác định cách đưa giá trị vào path hoặc query. Một phương thức Java không được Spring MVC ánh xạ sẽ không cung cấp đủ thông tin để tạo URI theo cách này.

## 3. Tạo link cho path variable

Path variable là phần động trong path của endpoint. Ví dụ:

~~~java
@GetMapping("/{id}")
public OrderRepresentation one(@PathVariable("id") UUID id) {
    // ...
}
~~~

Tạo link cho một đơn hàng cụ thể:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();
~~~

Spring HATEOAS sử dụng giá trị truyền vào `one(...)` để thay thế biến `id` trong mapping. Ta không cần tự nối UUID vào chuỗi.

### 3.1. Nhiều path variable

Giả sử endpoint có mapping lồng nhau:

~~~java
@RestController
@RequestMapping("/customers/{customerId}/orders")
public class CustomerOrderController {

    @GetMapping("/{orderId}")
    public OrderRepresentation one(
            @PathVariable("customerId") UUID customerId,
            @PathVariable("orderId") UUID orderId) {
        // ...
    }
}
~~~

Tạo link:

~~~java
Link orderLink = linkTo(
    methodOn(CustomerOrderController.class)
        .one(customerId, orderId)
).withSelfRel();
~~~

Các giá trị được truyền theo thứ tự tham số của phương thức Java. Tên biến path trong annotation giúp Spring MVC biết tham số nào tương ứng với placeholder nào. Để code dễ đọc và tránh phụ thuộc vào tên tham số được biên dịch, nên khai báo rõ tên trong `@PathVariable("...")`.

### 3.2. Mapping cấp lớp và cấp phương thức được kết hợp

Trong ví dụ trên, URI được hình thành từ hai phần:

~~~text
@RequestMapping("/customers/{customerId}/orders")
@GetMapping("/{orderId}")
~~~

Kết quả có dạng:

~~~text
/customers/{customerId}/orders/{orderId}
~~~

`linkTo(methodOn(...))` xem xét cả mapping cấp lớp và mapping cấp phương thức. Nếu đổi prefix ở cấp lớp, link vẫn được tạo từ mapping mới.

### 3.3. Path variable có giá trị đặc biệt

Nếu path variable là chuỗi chứa dấu cách, dấu gạch chéo hoặc ký tự dành riêng, không nên tự nối chuỗi vì URI có thể bị sai cấu trúc. Spring HATEOAS xây URI dựa trên metadata mapping và xử lý tham số theo cơ chế URI builder của Spring.

Dù vậy, ứng dụng vẫn cần xác định hợp đồng hợp lệ cho ID. Ví dụ, một ID dạng UUID hoặc số nguyên giúp path dễ dự đoán và ít nhập nhằng hơn một chuỗi tùy ý có thể chứa dấu phân cách.

## 4. Tạo link cho query parameter

Query parameter được khai báo bằng `@RequestParam`. Ví dụ:

~~~java
@GetMapping("/search")
public CollectionModel<OrderRepresentation> search(
        @RequestParam(name = "status", required = false) String status,
        @RequestParam(name = "sort", defaultValue = "createdAt") String sort) {
    // ...
}
~~~

Tạo link đến kết quả tìm kiếm tương ứng:

~~~java
Link search = linkTo(
    methodOn(OrderController.class).search("OPEN", "createdAt")
).withRel("search");
~~~

Spring HATEOAS sử dụng annotation `@RequestParam` để đưa các giá trị vào query string. Link có thể có dạng:

~~~text
/orders/search?status=OPEN&sort=createdAt
~~~

Client theo link này sẽ đến collection được lọc theo trạng thái OPEN và sắp xếp theo createdAt.

### 4.1. Giữ điều kiện lọc trong link

Khi trả về một trang collection đã lọc, link self nên đại diện cho đúng biến thể collection đó:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).search(status, sort)
).withSelfRel();
~~~

Nếu người dùng đang xem `status=OPEN`, link self cần giữ điều kiện đó. Khi tạo link next hoặc link đến trang khác, các điều kiện lọc và sắp xếp cũng cần được giữ.

Đừng tạo link đến `search(null, null)` một cách máy móc nếu điều đó làm mất các tham số đang áp dụng. Truyền các giá trị có hiệu lực của request hiện tại để link thể hiện đúng tập kết quả.

### 4.2. Tham số tùy chọn

Với `@RequestParam(required = false)`, tham số có thể vắng mặt. Nếu giá trị null được truyền vào lời gọi mô phỏng, Spring HATEOAS xử lý theo metadata mapping và quy tắc xây URI của phiên bản thư viện đang dùng. Hãy kiểm thử rõ trường hợp có và không có tham số để xác nhận href đúng hợp đồng.

Với tham số có default value, cần quyết định API có muốn công bố giá trị mặc định thành query parameter hay không. Nếu muốn URI ngắn hơn, có thể chỉ tạo link với tham số thực sự được chọn; nếu muốn link tường minh, có thể đưa cả giá trị mặc định vào href.

### 4.3. Tham số phân trang

Một controller có thể nhận `Pageable`:

~~~java
@GetMapping
public PagedModel<EntityModel<OrderRepresentation>> all(Pageable pageable) {
    // ...
}
~~~

Spring Data Web và `PagedResourcesAssembler` thường là lựa chọn phù hợp để tạo các link first, prev, next và last cho trang. Nếu cần tạo link đến một truy vấn cụ thể bằng `linkTo(methodOn(...))`, hãy dùng đúng kiểu tham số và mapping mà controller công bố; đồng thời kiểm thử filter, sort và các query parameter được giữ.

Không nên tự ghép query string phân trang khi đã có cơ chế tạo link từ request hoặc assembler chuyên dụng.

## 5. LinkTo cho nhiều loại endpoint

Link builder không chỉ tạo link GET. Nó có thể tạo URI cho endpoint có method HTTP khác nhau. HTTP method được quyết định bởi mapping của controller và request client gửi khi theo link.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(@PathVariable("id") UUID id) {
        // ...
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(@PathVariable("id") UUID id) {
        // ...
    }
}
~~~

Tạo link đến thao tác hủy:

~~~java
Link cancel = linkTo(
    methodOn(OrderController.class).cancel(orderId)
).withRel("cancel");
~~~

Link có relation `cancel` trỏ đến URI của endpoint hủy. Khi client sử dụng link, nó vẫn phải gửi POST theo hợp đồng endpoint. Link cơ bản chủ yếu cung cấp relation và href; nếu client cần khám phá method, content type hoặc cấu trúc dữ liệu đầu vào, có thể bổ sung affordance và định dạng hypermedia hỗ trợ.

### 5.1. Link relation là phần ngữ nghĩa

Không nên dùng cùng relation cho các hành động khác nhau. Một số ví dụ:

| Relation | Ý nghĩa |
|---|---|
| `self` | Tài nguyên hiện tại |
| `collection` | Collection chứa member |
| `search` | Điểm vào tìm kiếm |
| `cancel` | Yêu cầu hủy tài nguyên |
| `approve` | Phê duyệt |
| `receipt` | Biểu diễn biên nhận |

Với relation chuẩn, có thể dùng `IanaLinkRelations`. Với relation theo nghiệp vụ, hãy định nghĩa rõ ý nghĩa trong hợp đồng API và giữ ngữ nghĩa ổn định.

### 5.2. Một URI có thể có nhiều hành động

Cùng một tài nguyên có thể có nhiều link đến các thao tác khác nhau:

~~~java
model.add(
    linkTo(methodOn(OrderController.class).cancel(id))
        .withRel("cancel")
);

model.add(
    linkTo(methodOn(OrderController.class).approve(id))
        .withRel("approve")
);
~~~

Client tìm link theo relation để khám phá khả năng. Server có thể chỉ thêm các link tương ứng với trạng thái hiện tại và quyền của người dùng.

## 6. linkTo trong RepresentationModelAssembler

Trong API thực tế, không nên lặp lại logic tạo link ở nhiều controller. `RepresentationModelAssembler` tập trung việc chuyển đổi một đối tượng miền thành biểu diễn hypermedia.

Giả sử DTO:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Assembler:

~~~java
@Component
public class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        UUID id = order.getId();

        EntityModel<OrderRepresentation> model = EntityModel.of(
            new OrderRepresentation(
                id,
                order.getStatus().name(),
                order.getTotal()
            ),
            linkTo(methodOn(OrderController.class).one(id)).withSelfRel(),
            linkTo(OrderController.class)
                .withRel(IanaLinkRelations.COLLECTION)
        );

        if (order.canBeCancelled()) {
            model.add(
                linkTo(methodOn(OrderController.class).cancel(id))
                    .withRel("cancel")
            );
        }

        return model;
    }
}
~~~

Assembler có ba trách nhiệm chính:

1. Chuyển dữ liệu miền thành DTO công khai.
2. Tạo link self và link collection theo mapping controller.
3. Thêm link hành động khi trạng thái nghiệp vụ cho phép.

`linkTo(OrderController.class)` tạo link đến mapping cấp controller. `linkTo(methodOn(...).one(id))` tạo link đến mapping cụ thể có path variable.

### 6.1. Tích hợp vào controller

Controller có thể trả về model do assembler tạo:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(@PathVariable("id") UUID id) {
        return assembler.toModel(service.getRequired(id));
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        return assembler.toCollectionModel(service.findAll())
            .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(@PathVariable("id") UUID id) {
        service.cancel(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Các import chính:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Các kiểu `Order` và `OrderService` là thành phần miền của ví dụ. Trong dự án thực tế, thay bằng model và service tương ứng. Controller chịu trách nhiệm điều phối HTTP; assembler chịu trách nhiệm tạo representation và link; service thực thi nghiệp vụ.

### 6.2. Tạo link self cho collection có query

Nếu collection có filter và sort, controller có thể đưa các giá trị hiện tại vào link self:

Đây là biến thể của phương thức `all()` ở ví dụ trước: dùng chữ ký có tham số khi endpoint hỗ trợ lọc và sắp xếp, thay cho phiên bản không tham số. Không khai báo cả hai phương thức cùng ánh xạ GET `/orders` nếu không có điều kiện mapping để phân biệt.

~~~java
@GetMapping
public CollectionModel<EntityModel<OrderRepresentation>> all(
        @RequestParam(name = "status", required = false) String status,
        @RequestParam(name = "sort", defaultValue = "createdAt") String sort) {

    List<Order> orders = service.findAll(status, sort);

    return assembler.toCollectionModel(orders)
        .add(linkTo(methodOn(OrderController.class).all(status, sort))
            .withSelfRel());
}
~~~

Các import bổ sung cho biến thể này:

~~~java
import java.util.List;

import org.springframework.web.bind.annotation.RequestParam;
~~~

Ở đây `methodOn(...).all(status, sort)` sử dụng đúng các tham số của request. Link self đại diện cho collection đã lọc và sắp xếp. Nếu có thêm query parameter ảnh hưởng kết quả, cần đưa chúng vào phương thức controller và lời gọi `methodOn` tương ứng.

## 7. URI encoding và tham số

Một lợi ích của link builder là giảm việc tự xử lý URI bằng chuỗi. Khi tham số được đưa vào path hoặc query, Spring HATEOAS kết hợp mapping và giá trị tham số để tạo URI.

Ví dụ, tìm kiếm theo từ khóa:

~~~java
@GetMapping("/search")
public CollectionModel<OrderRepresentation> search(
        @RequestParam("q") String query) {
    // ...
}
~~~

Tạo link:

~~~java
Link search = linkTo(
    methodOn(OrderController.class).search("blue & green")
).withRel("search");
~~~

Dữ liệu chứa dấu cách và ký tự `&` cần được encode để không bị hiểu nhầm là nhiều query parameter. Hãy để link builder xử lý tham số theo annotation thay vì nối chuỗi:

~~~java
// Tránh:
String href = "/orders/search?q=" + query;
~~~

Nếu cần tạo URI độc lập với controller mapping, `UriComponentsBuilder` là lựa chọn phù hợp để xây path và query có encode. Nhưng khi endpoint đã được ánh xạ trong controller, `linkTo(methodOn(...))` thường giữ quan hệ giữa link và mapping tốt hơn.

## 8. Class mapping, method mapping và context path

Một URI do `linkTo(...)` tạo ra thường kết hợp:

- Scheme và authority của request hiện tại.
- Context path hoặc servlet path mà ứng dụng nhìn thấy.
- Mapping cấp controller.
- Mapping cấp phương thức.
- Giá trị path variable và query parameter.

Ví dụ:

~~~java
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderRepresentation one(@PathVariable("id") UUID id) {
        // ...
    }
}
~~~

Link được tạo từ:

~~~java
linkTo(methodOn(OrderController.class).one(id)).withSelfRel();
~~~

sẽ phản ánh mapping `/api/orders/{id}` và giá trị ID. Không cần lặp lại prefix `/api/orders` trong assembler.

### 8.1. Ứng dụng chạy sau reverse proxy

Trong môi trường production, ứng dụng có thể nhận request nội bộ từ proxy nhưng được truy cập qua host và scheme công khai khác. Nếu link builder chỉ nhìn thấy thông tin request nội bộ, URI tuyệt đối được tạo có thể chứa host hoặc scheme không đúng.

Cần cấu hình proxy và ứng dụng để xử lý forwarded headers như `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto` và prefix tương ứng. Chỉ tin các header này từ proxy được kiểm soát. Sau đó kiểm thử link trong môi trường có cấu hình proxy thực tế.

### 8.2. Context path không giống mapping của controller

Context path là tiền tố triển khai của ứng dụng; mapping controller là phần path do ứng dụng định nghĩa. Link builder thường kết hợp chúng dựa trên request. Khi hard-code URI, lập trình viên dễ quên context path; khi dùng `linkTo`, việc dựng link bám vào mapping và request context được tập trung hơn.

Dù vậy, cần xác nhận hành vi trong cấu hình deploy thật, đặc biệt nếu proxy thêm hoặc loại bỏ prefix trước khi request đến ứng dụng.

## 9. Những giới hạn và lưu ý khi dùng methodOn

`methodOn(...)` thuận tiện nhưng cần dùng đúng mục đích.

- Nó mô tả lời gọi controller để lấy mapping và tham số; không phải cách gọi controller để chạy nghiệp vụ.
- Các phương thức cần có mapping Spring MVC hợp lệ.
- Tham số truyền vào phải tương ứng với chữ ký phương thức và annotation mapping.
- Nếu controller có overload, hãy gọi đúng overload bằng chữ ký tham số mong muốn.
- Không đặt logic có side effect trong biểu thức mô tả link.
- Không giả định một link được công bố đồng nghĩa người dùng có quyền thực hiện hành động.

Nếu cần tạo URI cho một endpoint không thuộc Spring MVC hoặc một dịch vụ bên ngoài, có thể tạo `Link` từ URI đã biết hoặc dùng URI builder thích hợp. `WebMvcLinkBuilder` được thiết kế cho mapping Spring MVC; ứng dụng WebFlux có API link builder tương ứng trong Spring HATEOAS WebFlux.

## 10. Kiểm thử linkTo bằng MockMvc

Kiểm thử nên xác nhận link được tạo từ mapping đúng, relation đúng và href chứa đúng tham số. Ví dụ, với một đơn hàng có thể hủy, kiểm tra link self và cancel:

~~~java
@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    OrderService service;

    @Test
    void createsLinksFromControllerMappings() throws Exception {
        UUID id = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
        given(service.getRequired(id)).willReturn(cancellableOrder(id));

        mvc.perform(get("/orders/{id}", id)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href")
                .value(endsWith("/orders/" + id)))
            .andExpect(jsonPath("$._links.collection.href")
                .exists())
            .andExpect(jsonPath("$._links.cancel.href")
                .value(endsWith("/orders/" + id + "/cancellation")));
    }
}
~~~

Fixture `cancellableOrder(id)` là hàm dựng dữ liệu của test. Nếu relation collection được tạo từ `IanaLinkRelations.COLLECTION`, HAL có thể serialize key là `collection`.

Các import thường dùng:

~~~java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.endsWith;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

### 10.1. Kiểm thử link theo trạng thái

Nếu đơn hàng đã giao hoặc đã hủy, link cancel không nên xuất hiện:

~~~java
.andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Điều này xác nhận assembler chỉ công bố hành động phù hợp với trạng thái hiện tại. Endpoint cancel vẫn phải kiểm tra trạng thái và quyền khi nhận request.

### 10.2. Kiểm thử query parameter

Với biến thể collection `all(status, sort)` ở mục 6.2:

~~~java
mvc.perform(get("/orders")
        .param("status", "OPEN")
        .param("sort", "createdAt")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.self.href")
        .value(containsString("status=OPEN")));
~~~

Kiểm tra relation self có giữ điều kiện lọc giúp phát hiện trường hợp link được tạo nhưng làm mất query parameter quan trọng. Với tham số có ký tự cần encode, nên parse URI hoặc kiểm tra giá trị đã encode thay vì giả định một cách viết chuỗi duy nhất.

### 10.3. Kiểm thử thay đổi mapping

Một lợi ích của `linkTo` là link lấy từ mapping. Khi đổi prefix controller hoặc path method, hãy cập nhật kiểm thử để xác nhận href phản ánh mapping mới. Điều này giúp phát hiện link hard-code bị bỏ sót ở các assembler khác.

MockMvc xác minh quá trình tích hợp giữa controller, assembler và serializer trong ngữ cảnh Spring MVC. Với reverse proxy hoặc gateway, nên bổ sung kiểm thử tích hợp để xác nhận scheme, host và prefix công khai.

## 11. Lỗi thường gặp khi sử dụng linkTo

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Ghép URI bằng chuỗi dù đã có controller mapping | Link bị lệch khi mapping thay đổi | Dùng `linkTo(methodOn(...))` |
| Dùng `linkTo(Controller.class)` cho endpoint có ID | Link chỉ đến mapping cấp lớp | Dùng `methodOn(...).method(id)` |
| Quên truyền path variable | URI không đại diện đúng member | Truyền giá trị đúng chữ ký phương thức |
| Truyền sai query parameter | Link self hoặc search sai điều kiện | Dùng đúng tham số và annotation của controller |
| Coi methodOn là lời gọi nghiệp vụ | Có thể hiểu sai hành vi của proxy | Chỉ dùng nó để mô tả mapping và tham số |
| Không khai báo tên PathVariable rõ ràng | Dễ phụ thuộc tên tham số khi biên dịch | Dùng `@PathVariable("id")` |
| Bỏ filter/sort khi tạo link next | Client chuyển sang tập kết quả khác | Giữ query parameter hiện tại |
| Không kiểm thử link HAL | Lỗi href hoặc relation không được phát hiện | Kiểm tra cả relation, href và media type |
| Không cấu hình forwarded headers | Link tuyệt đối có thể dùng host nội bộ | Cấu hình proxy và ứng dụng có kiểm soát |

## 12. Quy trình áp dụng linkTo

Khi tạo link cho một endpoint Spring MVC, có thể làm theo trình tự:

1. Xác định controller và mapping cấp lớp.
2. Xác định phương thức HTTP và mapping cấp method.
3. Kiểm tra path variable, query parameter và các tham số cần truyền.
4. Dùng `linkTo(Controller.class)` cho mapping cấp controller hoặc `linkTo(methodOn(Controller.class).method(args))` cho endpoint cụ thể.
5. Chọn relation phù hợp bằng `withSelfRel()` hoặc `withRel(...)`.
6. Gắn link vào `EntityModel`, `CollectionModel` hoặc representation assembler.
7. Tạo link theo trạng thái và quyền nếu đó là hành động nghiệp vụ.
8. Kiểm thử href, relation, query parameter, context path và media type.
9. Xác nhận endpoint thực thi hành động vẫn kiểm tra quyền và quy tắc nghiệp vụ.

## 13. Kết luận

`linkTo(...)` trong Spring HATEOAS giúp tạo URI từ mapping Spring MVC. Dùng `linkTo(Controller.class)` để tạo link đến mapping cấp controller; dùng `linkTo(methodOn(Controller.class).method(args))` để tạo link đến phương thức cụ thể với path variable và query parameter. `methodOn(...)` chỉ mô tả lời gọi để Spring HATEOAS đọc mapping và tham số, không thực thi logic nghiệp vụ của controller.

Khi đưa link vào assembler, chọn relation ổn định và kiểm thử href, API có thể giữ các liên kết nhất quán với controller khi cấu trúc mapping thay đổi. Cần cấu hình đúng context path và forwarded headers khi triển khai sau proxy, đồng thời luôn kiểm tra quyền và điều kiện nghiệp vụ ở endpoint đích.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Building Links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder): cách dùng link builder trong Spring MVC.
- [Spring HATEOAS API — WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html): API `linkTo(...)` và các overload.
- [Spring HATEOAS API — DummyInvocationUtils](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/core/DummyInvocationUtils.html): cơ chế proxy được dùng bởi `methodOn(...)`.
- [Spring Framework — RequestMapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): mapping controller và tham số request.

