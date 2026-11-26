# Giữ link không phụ thuộc hard-code

Trong REST API, client nên nhận URI từ các liên kết hypermedia mà server công bố. Ở phía server, các liên kết nội bộ nên được tạo dựa trên mapping của controller thay vì lặp lại chuỗi đường dẫn trong assembler hoặc service. Spring HATEOAS hỗ trợ việc này bằng `linkTo(...)` và `methodOn(...)`: ứng dụng mô tả controller method cùng tham số, thư viện đọc mapping Spring MVC và tạo URI tương ứng.

Ví dụ, khi nhiều nơi trong ứng dụng tự tạo đường dẫn `"/orders/" + id`, việc đổi mapping từ `/orders/{id}` sang `/api/orders/{id}` đòi hỏi tìm và sửa mọi chuỗi đã sao chép. Nếu link được tạo từ mapping controller, chỉ cần cập nhật mapping ở một nơi; các link sinh ra từ mapping mới sẽ theo thay đổi đó.

Bài học này giải thích cách loại bỏ URI hard-code khỏi quá trình tạo hypermedia, tổ chức link trong `RepresentationModelAssembler`, xử lý path variable và query parameter, phân biệt URI nội bộ với liên kết ngoài, và kiểm thử để phát hiện link bị lệch khỏi controller.

Sau bài học, bạn có thể:

- Nhận diện các chuỗi URI bị lặp và rủi ro khi route thay đổi.
- Dùng `linkTo(Controller.class)` cho mapping cấp controller.
- Dùng `linkTo(methodOn(Controller.class).method(args))` cho endpoint cụ thể.
- Tạo link self, collection và hành động theo mapping Spring MVC.
- Tập trung logic tạo link trong assembler để các response nhất quán.
- Giữ query parameter, path variable và context path chính xác.
- Xử lý link đến hệ thống ngoài bằng cấu hình thay vì giả định chúng thuộc controller nội bộ.
- Kiểm thử href và relation để bảo vệ hợp đồng hypermedia.

## 1. Vấn đề của URI hard-code

Giả sử một ứng dụng quản lý đơn hàng có controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderRepresentation one(@PathVariable("id") UUID id) {
        // ...
    }
}
~~~

Một assembler có thể tự ghép URI:

~~~java
String href = "/orders/" + order.getId();
Link self = Link.of(href).withSelfRel();
~~~

Đoạn mã này hoạt động khi route đang là `/orders/{id}`. Tuy nhiên, path đã được định nghĩa ở controller và lại được sao chép trong assembler. Nếu có thêm service, mapper hoặc controller khác cũng ghép cùng đường dẫn, ứng dụng có nhiều nguồn sự thật cho một route.

Những vấn đề thường xuất hiện:

- Route thay đổi nhưng một số chuỗi cũ không được cập nhật.
- Có endpoint sử dụng prefix khác, ví dụ `/api/v2`, trong khi assembler vẫn phát đường dẫn cũ.
- Path variable bị ghép sai hoặc thiếu URL encoding.
- Link self và link hành động không thống nhất giữa các response.
- Test kiểm tra dữ liệu nhưng không phát hiện href trỏ đến endpoint không còn tồn tại.

Vấn đề không nằm ở việc chuỗi URI luôn sai. Một URI cố định có thể hợp lý khi nó là định danh của tài nguyên ngoài hoặc một endpoint được cấu hình từ môi trường. Rủi ro xuất hiện khi một đường dẫn nội bộ do controller quản lý bị sao chép thành nhiều chuỗi hard-code.

## 2. Dùng mapping của controller làm nguồn tạo link

Spring HATEOAS cung cấp `WebMvcLinkBuilder` để tạo link từ mapping Spring MVC.

Hai hàm thường dùng:

- `linkTo(...)` tạo link builder từ controller class hoặc method mapping.
- `methodOn(...)` mô tả một lời gọi đến phương thức controller và các tham số của nó.

Import tĩnh:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

### 2.1. Link đến mapping cấp controller

Khi muốn liên kết đến collection hoặc entry point của controller, có thể dùng controller class:

~~~java
Link orders = linkTo(OrderController.class)
    .withRel(IanaLinkRelations.COLLECTION);
~~~

Nếu controller có mapping cấp lớp:

~~~java
@RequestMapping("/orders")
public class OrderController {
    // ...
}
~~~

link được tạo từ mapping đó trong ngữ cảnh request hiện tại. Cách này phù hợp khi mapping cấp lớp chính là URI collection mà API muốn công bố.

Nếu controller có path variable ở cấp lớp, chẳng hạn `/customers/{customerId}/orders`, chỉ truyền class có thể không đủ để điền giá trị biến. Khi cần một URI cụ thể, hãy dùng method mapping có tham số và `methodOn(...)`.

### 2.2. Link đến một phương thức cụ thể

Mẫu phổ biến để tạo link self:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
~~~

Spring HATEOAS kết hợp:

1. Mapping cấp lớp của `OrderController`.
2. Mapping cấp phương thức `one(...)`.
3. Giá trị `orderId` được truyền vào lời gọi mô phỏng.

Nếu route đổi từ `/orders/{id}` thành `/api/orders/{id}`, link được tạo từ mapping mới sau khi controller được cập nhật. Assembler không phải biết hoặc lưu chuỗi path đó.

`methodOn(...)` không gọi phương thức controller để chạy nghiệp vụ. Nó tạo proxy và ghi nhận phương thức cùng tham số để Spring HATEOAS phân tích mapping. Không đặt thao tác ghi dữ liệu hoặc side effect trong biểu thức này.

## 3. Refactor từ ghép chuỗi sang linkTo

Xét hai cách tạo link đến cùng một đơn hàng.

**Cách ghép URI thủ công**

~~~java
Link self = Link.of(
    "/orders/" + order.getId()
).withSelfRel();

Link cancel = Link.of(
    "/orders/" + order.getId() + "/cancellation"
).withRel("cancel");
~~~

Đường dẫn `/orders` và cấu trúc `/{id}/cancellation` bị lặp trong code tạo link.

**Cách dùng controller mapping**

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();

Link cancel = linkTo(
    methodOn(OrderController.class).cancel(order.getId())
).withRel("cancel");
~~~

Cả hai link được tạo từ mapping của các phương thức `one` và `cancel`. Khi route thay đổi, mapping controller là nơi cần cập nhật.

### 3.1. Mapping cần có trên controller method

Ví dụ đầy đủ:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable("id") UUID id) {
        // ...
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(
            @PathVariable("id") UUID id) {
        // ...
    }
}
~~~

Các annotation `@GetMapping` và `@PostMapping` định nghĩa route mà link builder đọc. Tên tham số trong `methodOn` phải khớp với chữ ký Java; tên trong `@PathVariable("id")` xác định rõ placeholder được điền.

Link cơ bản chứa relation và href. Relation `cancel` cho biết ý nghĩa nghiệp vụ; href trỏ đến endpoint. Client vẫn cần tuân theo hợp đồng HTTP của endpoint, trong ví dụ này là POST. Nếu cần mô tả method, content type hoặc cấu trúc body cho client, có thể bổ sung affordance và định dạng hypermedia phù hợp.

## 4. Tập trung việc tạo link trong assembler

Nếu nhiều endpoint trả về cùng một loại tài nguyên, hãy tạo link tại một assembler dùng chung. Điều này tránh việc mỗi controller tự xây một biến thể URI khác nhau.

Giả sử API công bố DTO:

~~~java
public record OrderRepresentation(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Assembler chuyển đối tượng miền thành `EntityModel`:

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

Assembler có ba trách nhiệm:

- Chuyển dữ liệu miền thành DTO công khai.
- Tạo link self và collection từ controller mapping.
- Thêm link nghiệp vụ khi điều kiện của tài nguyên cho phép.

Link `cancel` được tạo từ mapping của `cancel(...)`. Điều kiện `canBeCancelled()` quyết định liệu hành động có được công bố trong biểu diễn hiện tại hay không.

### 4.1. Controller sử dụng assembler

Controller trả về biểu diễn đã được assembler tạo:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    public OrderController(
            OrderService service,
            OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<OrderRepresentation> one(
            @PathVariable("id") UUID id) {
        return assembler.toModel(service.getRequired(id));
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderRepresentation>> all() {
        return assembler.toCollectionModel(service.findAll())
            .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
    }

    @PostMapping("/{id}/cancellation")
    public ResponseEntity<Void> cancel(
            @PathVariable("id") UUID id) {
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

Các kiểu `Order` và `OrderService` là thành phần miền của ví dụ. Trong dự án thực tế, thay chúng bằng model và service tương ứng. Controller điều phối HTTP, service thực thi nghiệp vụ, assembler xây dựng biểu diễn.

### 4.2. CollectionModel cũng nên lấy link từ mapping

Link self của collection có thể được tạo từ phương thức `all()`:

~~~java
CollectionModel<EntityModel<OrderRepresentation>> result =
    assembler.toCollectionModel(service.findAll())
        .add(linkTo(methodOn(OrderController.class).all()).withSelfRel());
~~~

Nếu controller thay đổi mapping collection, link self được cập nhật theo. Khi collection hỗ trợ filter, sort hoặc phân trang, method signature cần nhận các tham số tương ứng và lời gọi `methodOn(...)` phải truyền các giá trị hiện tại.

Với phân trang Spring Data, `PagedResourcesAssembler` thường phù hợp hơn việc tự tạo từng link trang. Nó có thể tạo link điều hướng dựa trên request hiện tại và metadata của `Page`.

## 5. Tránh hard-code query parameter

URI hard-code có thể xuất hiện cả ở phần query string:

~~~java
String href = "/orders?status=" + status + "&sort=" + sort;
~~~

Cách này dễ gặp lỗi khi giá trị có ký tự đặc biệt, khi tên query parameter thay đổi hoặc khi bổ sung filter mới.

Khai báo endpoint:

~~~java
@GetMapping("/search")
public CollectionModel<EntityModel<OrderRepresentation>> search(
        @RequestParam(name = "status", required = false) String status,
        @RequestParam(name = "sort", defaultValue = "createdAt") String sort) {
    // ...
}
~~~

Tạo link theo mapping và tham số:

~~~java
Link search = linkTo(
    methodOn(OrderController.class).search(status, sort)
).withRel("search");
~~~

Import cho tham số truy vấn:

~~~java
import org.springframework.web.bind.annotation.RequestParam;
~~~

Spring HATEOAS đọc `@RequestParam` và đưa các giá trị vào query string. URI được tạo theo mapping thực tế, giảm việc lặp tên parameter và xử lý encode thủ công.

### 5.1. Giữ filter và sort trong link self

Nếu response đang đại diện cho collection đã lọc, link self cần phản ánh đúng điều kiện đó:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).search("OPEN", "createdAt")
).withSelfRel();
~~~

Không tạo link self trỏ đến collection mặc định nếu response đang chứa một tập kết quả đã lọc. Với link next, giữ các điều kiện lọc và sort đang áp dụng. Client theo href nguyên vẹn thay vì tự nối thêm query parameter.

### 5.2. Phân trang

Với controller nhận `Pageable`, có thể dùng:

Đây là biến thể của phương thức `all()` ở mục 4.1: dùng chữ ký có `Pageable` và trả về `PagedModel` thay cho phiên bản collection không phân trang. Trong cùng controller, chỉ khai báo một handler cho cùng route và HTTP method, trừ khi có điều kiện mapping để phân biệt rõ.

~~~java
@GetMapping
public PagedModel<EntityModel<OrderRepresentation>> all(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {

    Page<Order> page = service.findAll(pageable);
    return pagedAssembler.toModel(page, assembler);
}
~~~

Các kiểu liên quan đến phân trang:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;
~~~

`PagedResourcesAssembler` tạo các link first, prev, next và last dựa trên request và kết quả trang. Cách này giúp tránh hard-code `?page=...` và giảm nguy cơ làm mất sort hoặc filter khi client chuyển trang.

## 6. Dùng relation ổn định, không nhầm relation với URI

Loại bỏ URI hard-code không có nghĩa là bỏ qua relation. Relation cho biết link có ý nghĩa gì; href là địa chỉ được tạo từ mapping.

Ví dụ:

~~~java
model.add(
    linkTo(methodOn(OrderController.class).one(id))
        .withSelfRel()
);

model.add(
    linkTo(OrderController.class)
        .withRel(IanaLinkRelations.COLLECTION)
);

model.add(
    linkTo(methodOn(OrderController.class).cancel(id))
        .withRel("cancel")
);
~~~

Các relation trong ví dụ:

| Relation | Ý nghĩa |
|---|---|
| `self` | Đơn hàng hiện tại |
| `collection` | Collection chứa đơn hàng |
| `cancel` | Điểm vào yêu cầu hủy đơn hàng |

`self` và `collection` có thể dùng hằng số chuẩn từ `IanaLinkRelations`. Relation nghiệp vụ như `cancel` cần được định nghĩa rõ trong hợp đồng API. Có thể tập trung custom relation thành hằng số trong một lớp chuyên trách để tránh lỗi chính tả:

~~~java
public final class OrderRelations {

    public static final String CANCEL = "cancel";

    private OrderRelations() {
    }
}
~~~

Sau đó:

~~~java
model.add(
    linkTo(methodOn(OrderController.class).cancel(id))
        .withRel(OrderRelations.CANCEL)
);
~~~

Hằng số relation giúp tránh lặp tên quan hệ. Nó không thay thế việc tạo href từ controller mapping.

Client nên tìm link bằng relation và sử dụng href do server cung cấp. Client không nên tự ghép `/orders/` với ID hoặc suy luận endpoint cancel từ trạng thái đơn hàng.

## 7. URI nội bộ và link đến hệ thống bên ngoài

`linkTo(methodOn(...))` phù hợp với endpoint thuộc ứng dụng Spring MVC hiện tại. Không phải mọi link đều thuộc một controller nội bộ.

Ví dụ, đơn hàng có thể liên kết đến trang hỗ trợ của nhà cung cấp hoặc một dịch vụ thanh toán bên ngoài. Với loại link này, URI có thể được lấy từ cấu hình:

~~~yaml
integration:
  payment:
    status-uri: https://payments.example.com/status
~~~

Đọc cấu hình vào properties class và tạo link:

~~~java
Link paymentStatus = Link.of(
    paymentProperties.statusUri()
).withRel("payment-status");
~~~

Không hard-code URL theo môi trường trong assembler. Dùng cấu hình cho domain bên ngoài, vì địa chỉ có thể khác giữa local, staging và production.

Cần phân biệt:

- Route nội bộ của Spring MVC: tạo từ `linkTo(methodOn(...))`.
- Entry point nội bộ ở cấp controller: tạo từ `linkTo(Controller.class)`.
- URI dịch vụ ngoài: lấy từ cấu hình hoặc discovery mechanism phù hợp.
- URI do nghiệp vụ cung cấp: kiểm tra và áp dụng chính sách tin cậy trước khi công bố.

Không nên ép URI ngoài vào một controller nội bộ chỉ để dùng link builder. Chọn cơ chế theo nguồn sở hữu URI.

## 8. Context path, API prefix và reverse proxy

Một ứng dụng có thể được triển khai ở nhiều địa chỉ:

~~~text
Local:       http://localhost:8080/orders
Staging:     https://staging.example.com/api/orders
Production:  https://api.example.com/v2/orders
~~~

Nếu assembler hard-code `https://staging.example.com/api/orders`, link sẽ sai trong production. Khi link được tạo từ mapping controller, path cấp ứng dụng được quản lý tại controller và URI tuyệt đối được dựng theo request hiện tại.

Ví dụ controller có prefix:

~~~java
@RequestMapping("/api/v2/orders")
public class OrderController {
    // ...
}
~~~

Link:

~~~java
linkTo(methodOn(OrderController.class).one(id)).withSelfRel();
~~~

sẽ phản ánh mapping mới. Không cần chép `/api/v2/orders` vào assembler.

### 8.1. Forwarded headers

Khi ứng dụng chạy sau reverse proxy, request nội bộ có thể có scheme hoặc host khác địa chỉ công khai. Nếu link builder nhìn thấy thông tin nội bộ, URI tuyệt đối có thể chứa host hoặc scheme sai.

Cấu hình proxy và ứng dụng để xử lý forwarded headers như `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto` và prefix tương ứng. Chỉ tin các header này từ proxy được kiểm soát. Sau đó kiểm thử link trong cấu hình triển khai thực tế.

### 8.2. Context path và mapping controller là hai phần riêng

Context path là tiền tố triển khai của ứng dụng; mapping controller là route do ứng dụng khai báo. Link builder sử dụng request context và mapping để dựng URI. Cần kiểm tra trường hợp proxy thêm hoặc loại bỏ prefix để bảo đảm href công khai có thể truy cập được.

## 9. Kiểm thử để phát hiện link bị hard-code

Kiểm thử hypermedia nên xác nhận relation và href được tạo đúng. Ví dụ, endpoint chi tiết trả về link self, collection và cancel:

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
            .andExpect(jsonPath("$._links.collection.href").exists())
            .andExpect(jsonPath("$._links.cancel.href")
                .value(endsWith("/orders/" + id + "/cancellation")));
    }
}
~~~

Fixture `cancellableOrder(id)` là hàm dựng dữ liệu kiểm thử của ứng dụng. Các import thường dùng:

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

### 9.1. Kiểm thử khi mapping thay đổi

Để xác nhận link không phụ thuộc chuỗi path cũ, có thể đổi mapping cấp lớp trong controller, ví dụ từ `/orders` sang `/api/orders`, rồi cập nhật request test và kỳ vọng href:

~~~java
.andExpect(jsonPath("$._links.self.href")
    .value(endsWith("/api/orders/" + id)));
~~~

Nếu link được tạo từ `linkTo(methodOn(...))`, href sẽ được dựng từ mapping mới. Một chuỗi `"/orders/" + id` bị bỏ sót trong assembler sẽ làm test thất bại.

### 9.2. Kiểm thử link hành động theo trạng thái

Khi đơn hàng không thể hủy, relation cancel không nên xuất hiện:

~~~java
.andExpect(jsonPath("$._links.cancel").doesNotExist());
~~~

Endpoint cancel vẫn phải kiểm tra quyền và trạng thái ở server. Kiểm thử sự vắng mặt của link xác nhận client được cung cấp đúng khả năng; nó không thay thế kiểm thử bảo vệ endpoint.

### 9.3. Kiểm thử query parameter

Với collection có filter, kiểm tra link self giữ lại điều kiện:

~~~java
.andExpect(jsonPath("$._links.self.href")
    .value(containsString("status=OPEN")));
~~~

Nếu giá trị có ký tự cần encode, hãy phân tích URI và query parameter trong test thay vì phụ thuộc vào một chuỗi encode duy nhất. Có thể kiểm tra link next giữ filter và sort khi dùng phân trang.

### 9.4. Kiểm thử tích hợp qua proxy

MockMvc xác nhận mapping, assembler và serialization trong ứng dụng Spring MVC. Nếu hệ thống chạy sau gateway hoặc reverse proxy, bổ sung kiểm thử tích hợp để xác nhận scheme, host, context path và prefix công khai. Kiểm tra href trong response cuối cùng mà client thực sự nhận được.

## 10. Khi nào vẫn cần URI literal?

Không phải mọi URI literal đều cần loại bỏ. Một số trường hợp có lý do chính đáng:

- URI của dịch vụ ngoài được quản lý bằng cấu hình.
- URI profile hoặc tài liệu hợp đồng đã được công bố.
- Link đến tài nguyên tĩnh hoặc tài liệu công khai có địa chỉ ổn định.
- URI được trả về từ một dịch vụ discovery hoặc registry.

Điều cần tránh là lặp lại route nội bộ mà controller đã định nghĩa. Nếu một link thuộc mapping Spring MVC, để mapping làm nguồn tạo URI. Nếu URI do hệ thống khác sở hữu, lấy nó từ cấu hình hoặc nguồn dữ liệu có trách nhiệm quản lý địa chỉ.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Ghép `"/orders/" + id` trong assembler | Link lệch khi route thay đổi | Dùng `linkTo(methodOn(...))` |
| Sao chép prefix controller vào nhiều lớp | Có nhiều nguồn sự thật cho URI | Để controller mapping quản lý route |
| Dùng `linkTo(Controller.class)` cho member có ID | Thiếu path variable | Dùng `methodOn(...).method(id)` |
| Bỏ query parameter khi tạo self/next | Link trỏ đến tập kết quả khác | Truyền tham số hiện tại hoặc dùng PagedResourcesAssembler |
| Dùng custom relation không ổn định | Client khó diễn giải link | Định nghĩa relation và giữ ngữ nghĩa |
| Cho rằng link đồng nghĩa được cấp quyền | Request trực tiếp có thể vượt giả định client | Kiểm tra quyền ở endpoint |
| Dùng linkTo cho URL của dịch vụ ngoài | URI không thuộc mapping hiện tại | Dùng cấu hình hoặc discovery |
| Không xử lý forwarded headers | Link tuyệt đối có thể dùng host nội bộ | Cấu hình proxy và kiểm thử deploy |
| Chỉ kiểm tra JSON data | Sai href không được phát hiện | Kiểm thử relation, href và media type |

## 12. Quy trình áp dụng

Khi refactor một API để tránh hard-code link, thực hiện theo trình tự:

1. Tìm các chuỗi URI nội bộ đang được ghép trong controller, assembler hoặc service.
2. Xác định controller method sở hữu từng endpoint.
3. Tạo link bằng `linkTo(Controller.class)` cho mapping cấp controller hoặc `linkTo(methodOn(Controller.class).method(args))` cho endpoint cụ thể.
4. Chuyển logic tạo link dùng chung vào `RepresentationModelAssembler`.
5. Giữ relation có ý nghĩa và ổn định; dùng hằng số cho custom relation nếu được lặp lại.
6. Với filter và sort, truyền các giá trị có hiệu lực vào link self; dùng `PagedResourcesAssembler` cho link phân trang.
7. Đưa URL dịch vụ ngoài vào cấu hình hoặc discovery mechanism.
8. Kiểm thử href sau khi đổi mapping, link theo trạng thái, query parameter và media type.
9. Kiểm tra link tuyệt đối trong môi trường có context path hoặc reverse proxy.

## 13. Kết luận

Giữ link không phụ thuộc hard-code nghĩa là dùng mapping Spring MVC làm nguồn tạo URI cho các endpoint nội bộ. `linkTo(Controller.class)` tạo link đến mapping cấp controller; `linkTo(methodOn(Controller.class).method(args))` tạo link đến phương thức cụ thể với path variable và query parameter. Tập trung cách tạo link trong `RepresentationModelAssembler` giúp các response cùng loại có relation và href nhất quán.

URI literal vẫn phù hợp với tài nguyên ngoài hoặc địa chỉ do cấu hình quản lý. Với route nội bộ, dùng controller mapping, kiểm thử href khi route thay đổi và để client điều hướng theo relation cùng href mà server công bố. Server vẫn phải kiểm tra quyền và quy tắc nghiệp vụ ở endpoint đích.

## Tài liệu tham khảo

- [Spring HATEOAS Reference — Building Links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder): tạo link từ Spring MVC mapping.
- [Spring HATEOAS API — WebMvcLinkBuilder](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html): API `linkTo(...)` và các overload.
- [Spring HATEOAS API — RepresentationModelAssembler](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/server/RepresentationModelAssembler.html): chuyển đổi đối tượng thành biểu diễn hypermedia.
- [Spring Framework — Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): khai báo mapping cho controller và handler method.

