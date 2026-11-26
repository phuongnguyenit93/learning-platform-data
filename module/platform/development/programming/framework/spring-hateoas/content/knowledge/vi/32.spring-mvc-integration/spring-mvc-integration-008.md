# MockMvc với HATEOAS

Khi controller Spring MVC trả về `EntityModel`, `CollectionModel` hoặc `PagedModel`, response HTTP không chỉ chứa dữ liệu mà còn có link và metadata hypermedia. Kiểm thử controller vì vậy cần xác nhận cả status code, header content negotiation, payload và các quan hệ link được serialize. `MockMvc` cho phép gửi request qua Spring MVC `DispatcherServlet` trong môi trường kiểm thử mà không cần khởi động HTTP server thật.

Với Spring HATEOAS, test thường yêu cầu media type cụ thể như `application/hal+json` hoặc `application/prs.hal-forms+json`, sau đó kiểm tra cấu trúc `_links`, `_embedded`, `page` hoặc `_templates`. Kiểm tra đúng media type rất quan trọng: một object Java có thể chứa link trong bộ nhớ, nhưng nếu converter không serialize bằng hypermedia format phù hợp, client sẽ không nhận được representation như hợp đồng API mong đợi.

## 1. MockMvc kiểm thử điều gì?

`MockMvc` mô phỏng luồng xử lý request của Spring MVC: mapping controller, argument resolver, validation, exception handler, message converter và serialization. Nó phù hợp để kiểm thử:

- Endpoint được chọn theo path, HTTP method, `consumes` và `produces`.
- Query parameter và path variable được bind đúng.
- Controller trả status code và header phù hợp.
- `EntityModel` được serialize thành representation có `_links`.
- `CollectionModel` được serialize với `_embedded` và link collection.
- `PagedModel` có metadata trang và link điều hướng.
- Affordance được biểu diễn khi client yêu cầu media type hỗ trợ nó.
- Lỗi như `404`, `400`, `406` hoặc `415` tuân theo hợp đồng API.

MockMvc chạy trong cùng JVM và không mở cổng mạng. Nó kiểm tra tích hợp Spring MVC, nhưng không thay thế kiểm thử end-to-end qua reverse proxy, TLS, load balancer hoặc môi trường triển khai thực tế.

## 2. Chuẩn bị controller trả về EntityModel

Giả sử API có endpoint đọc đơn hàng. Controller trả về `EntityModel<OrderRepresentation>` thay vì chỉ trả DTO để response có thể mang link điều hướng.

DTO biểu diễn:

```java
import java.util.UUID;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "order", collectionRelation = "orders")
public record OrderRepresentation(UUID id, String status, UUID customerId) {
}
```

Kiểu domain được dùng trong ví dụ có thể là một record đơn giản:

```java
import java.util.UUID;

record Order(UUID id, String status, UUID customerId) {
}
```

Request DTO và service contract rút gọn:

```java
import java.util.List;
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

record UpdateOrderRequest(String note) {
}

interface OrderService {
    Order getRequired(UUID id);
    Order update(UUID id, UpdateOrderRequest request);
    List<Order> findAll();
    Page<Order> findPage(Pageable pageable);
}
```

Assembler tạo representation và link:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler implements
        RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {
        return EntityModel.of(
                new OrderRepresentation(
                        order.id(), order.status(), order.customerId()),
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel()
                        .andAffordance(afford(methodOn(OrderController.class)
                                .update(order.id(), null))),
                linkTo(methodOn(CustomerController.class)
                        .one(order.customerId())).withRel("customer"));
    }
}
```

Controller:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.http.MediaType.APPLICATION_JSON_VALUE;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = {
            "application/hal+json", "application/prs.hal-forms+json"})
    EntityModel<OrderRepresentation> one(@PathVariable("id") UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @PutMapping(value = "/{id}", consumes = APPLICATION_JSON_VALUE, produces = {
            "application/hal+json", "application/prs.hal-forms+json"})
    EntityModel<OrderRepresentation> update(
            @PathVariable("id") UUID id,
            @RequestBody UpdateOrderRequest request) {
        return assembler.toModel(orderService.update(id, request));
    }
}
```

`OrderService`, `UpdateOrderRequest` và `CustomerController` là các thành phần domain/application giả định. Trong dự án thực tế, dùng kiểu dữ liệu và service đang có. Điểm quan trọng là assembler dùng `linkTo(methodOn(...))` để tạo URI từ mapping controller; test có thể kiểm tra link sau khi Spring serialize model.

Trong ví dụ, `CustomerController` cần có handler `one(UUID id)` được ánh xạ đến `/customers/{id}` để `methodOn(CustomerController.class).one(...)` tạo được link relation `customer`.

## 3. Cấu hình test với SpringBootTest và MockMvc

Khi cần kiểm tra cấu hình MVC, Jackson và Spring HATEOAS cùng hoạt động, có thể khởi tạo application context đầy đủ:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerHateoasTestSkeleton {

    @Autowired
    MockMvc mockMvc;
}
```

`@SpringBootTest` nạp cấu hình ứng dụng; `@AutoConfigureMockMvc` đăng ký `MockMvc` mà không khởi động server. Đây là lựa chọn phù hợp khi cần kiểm tra cả auto-configuration của Spring Boot và converter hypermedia.

Nếu chỉ muốn kiểm tra một controller, có thể dùng `@WebMvcTest(OrderController.class)`. Khi đó, cung cấp các dependency bị loại khỏi slice bằng mock bean và import assembler/cấu hình HATEOAS cần thiết. Test slice chạy nhanh hơn nhưng cần chú ý rằng mọi cấu hình hypermedia tùy biến của ứng dụng phải được đưa vào context test.

Với Spring Framework 6.2 trở lên có thể dùng `@MockitoBean` để thay service bằng Mockito mock. Ở các phiên bản Spring Boot cũ hơn, dự án thường dùng `@MockBean`.

## 4. Kiểm tra response HAL và self link

Ví dụ test dùng `@MockitoBean` để cung cấp đơn hàng cố định:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerHateoasTest {

    private static final UUID ORDER_ID =
            UUID.fromString("a6a1f2b4-1f0d-4a7c-8e12-123456789abc");
    private static final UUID CUSTOMER_ID =
            UUID.fromString("b7b2f3c5-2a1e-4b8d-9f23-23456789abcd");

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsOrderWithHalLinks() throws Exception {
        Order order = new Order(ORDER_ID, "PAID", CUSTOMER_ID);
        given(orderService.getRequired(ORDER_ID)).willReturn(order);

        mockMvc.perform(get("/orders/{id}", ORDER_ID)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value(ORDER_ID.toString()))
                .andExpect(jsonPath("$.status").value("PAID"))
                .andExpect(jsonPath("$._links.self.href")
                        .value(containsString("/orders/" + ORDER_ID)))
                .andExpect(jsonPath("$._links.customer.href").exists());
    }
}
```

`CUSTOMER_ID` là fixture UUID được khai báo trong test; `Order` là record domain minh họa ở phần trước. Nếu dùng Spring Framework trước 6.2, thay `@MockitoBean` bằng cơ chế mock bean mà phiên bản Spring Boot của dự án hỗ trợ.

Test kiểm tra cả payload và link. `contentTypeCompatibleWith(...)` xác nhận response dùng media type HAL tương thích; JSONPath xác nhận link được serialize dưới `_links`. Không nên chỉ kiểm tra object trả về từ assembler trong unit test, vì lỗi converter hoặc content negotiation chỉ xuất hiện ở tầng MVC.

## 5. Phân biệt Accept và Content-Type trong test

Đối với GET, client thường gửi `Accept` để yêu cầu media type response:

```java
mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .accept(MediaTypes.HAL_JSON));
```

Đối với POST hoặc PUT có request body, test cần chỉ rõ `Content-Type` của body và `Accept` của response:

```java
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

mockMvc.perform(put("/orders/{id}", ORDER_ID)
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaTypes.HAL_JSON)
        .content("""
                {"note":"Giao hàng sau 17 giờ"}
                """));
```

`Content-Type` cho MVC biết converter nào đọc request body; `Accept` cho biết client muốn nhận response ở định dạng nào. Không nhầm hai header này khi kiểm tra endpoint ghi dữ liệu.

Nếu controller khai báo `consumes = application/json` và `produces` gồm HAL, test nên gửi đúng cả hai header để kiểm tra đường đi thành công. Các request thiếu hoặc gửi sai media type có thể được kiểm tra riêng ở phần lỗi content negotiation.

## 6. Kiểm tra CollectionModel và embedded relation

Một endpoint collection có thể trả `CollectionModel<EntityModel<OrderRepresentation>>`. HAL serialize các phần tử trong `_embedded`; tên relation của collection nên được định nghĩa rõ để client không phụ thuộc tên class Java.

Relation collection được khai báo ngay trên DTO representation:

`OrderRepresentation` đã khai báo `@Relation(itemRelation = "order", collectionRelation = "orders")` ở phần controller. Annotation này giúp tên `_embedded.orders` ổn định ngay cả khi tên class representation được đổi.

Controller tạo collection model:

```java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@GetMapping(value = "/all", produces = "application/hal+json")
CollectionModel<EntityModel<OrderRepresentation>> all() {
    List<EntityModel<OrderRepresentation>> orders = orderService.findAll().stream()
            .map(orderAssembler::toModel)
            .toList();

    return CollectionModel.of(orders,
            linkTo(methodOn(OrderController.class).all()).withSelfRel());
}
```

Trong method trên, controller cần inject `OrderService` và `OrderModelAssembler`; các import `EntityModel` và `linkTo`/`methodOn` được dùng như các phần trước.

Test collection:

```java
mockMvc.perform(get("/orders/all").accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._embedded.orders").isArray())
        .andExpect(jsonPath("$._embedded.orders[0].id").exists())
        .andExpect(jsonPath("$._links.self.href").exists());
```

Nếu ứng dụng cấu hình `RelProvider` riêng, hãy kiểm tra relation thực tế do provider đó tạo.

## 7. Kiểm tra PagedModel và pagination links

Với kết quả phân trang, `PagedResourcesAssembler` chuyển `Page<T>` thành `PagedModel`. MockMvc có thể kiểm tra metadata trang và các link điều hướng:

Endpoint phân trang dùng collection root `/orders`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PagedResourcesAssembler;
import org.springframework.hateoas.PagedModel;

@GetMapping(produces = "application/hal+json")
PagedModel<EntityModel<OrderRepresentation>> page(
        Pageable pageable,
        PagedResourcesAssembler<Order> pagedAssembler) {
    return pagedAssembler.toModel(
            orderService.findPage(pageable), orderAssembler);
}
```

```java
mockMvc.perform(get("/orders")
        .param("page", "0")
        .param("size", "2")
        .param("sort", "createdAt,desc")
        .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.page.size").value(2))
        .andExpect(jsonPath("$.page.number").value(0))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.next.href").exists());
```

Để link `next` xuất hiện, test cần có nhiều hơn hai phần tử phù hợp. Khi chỉ có một trang, `next` không được mong đợi. Nên kiểm tra thêm rằng link `next` giữ lại filter và sort đang áp dụng, tránh client chuyển sang tập kết quả khác khi điều hướng.

Không nên khẳng định link `prev` tồn tại ở trang đầu hoặc link `next` tồn tại ở trang cuối. Sự hiện diện của chúng phụ thuộc metadata trang và trạng thái collection.

## 8. Kiểm tra affordance với HAL-FORMS

Nếu API công bố affordance và client yêu cầu HAL-FORMS, test cần yêu cầu đúng media type:

```java
import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .accept(MediaTypes.HAL_FORMS_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._templates").exists());
```

Test giả định assembler đã gắn affordance vào link, ví dụ `PUT` để cập nhật đơn hàng. `_templates` là phần HAL-FORMS dùng để công bố thao tác và input metadata. Tên template, property và cấu trúc chi tiết cần được kiểm tra theo hợp đồng ứng dụng; không nên hard-code tên template mặc định nếu ứng dụng đã đặt tên riêng.

HAL cơ bản chủ yếu biểu diễn link và embedded resource. Nếu test cần xác nhận method, content type và các input property của affordance, hãy dùng media type hỗ trợ affordance như HAL-FORMS.

## 9. Kiểm tra custom relation và CURIE

Nếu assembler gắn custom relation, test HAL có thể kiểm tra link xuất hiện dưới relation đã công bố. Khi dùng `CurieProvider`, custom relation có thể được rút gọn bằng namespace:

```java
import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.curies").isArray())
        .andExpect(jsonPath("$._links['acme:payments'].href").exists());
```

Đoạn test giả định đơn hàng fixture có payment và ứng dụng đăng ký CURIE prefix `acme`. Nếu không dùng CURIE, kiểm tra relation URI đầy đủ hoặc tên relation thực tế. Không nên phụ thuộc vào thứ tự phần tử trong mảng `curies`; hãy tìm phần tử theo `name` khi cần xác minh prefix.

## 10. Kiểm tra content negotiation và lỗi

Khi controller giới hạn `produces`, request yêu cầu media type không được hỗ trợ có thể nhận `406 Not Acceptable`:

```java
import org.springframework.http.MediaType;

mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isNotAcceptable());
```

Khi handler giới hạn `consumes`, request gửi `Content-Type` không phù hợp có thể nhận `415 Unsupported Media Type`:

```java
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

mockMvc.perform(put("/orders/{id}", ORDER_ID)
        .contentType(MediaType.TEXT_PLAIN)
        .content("not-json"))
        .andExpect(status().isUnsupportedMediaType());
```

Các kết quả này phụ thuộc mapping và message converter được cấu hình. Nếu endpoint cho phép wildcard hoặc có converter khác hỗ trợ media type, kết quả có thể khác. Hãy viết test theo hợp đồng `produces`/`consumes` thực tế.

Có thể kiểm tra lỗi không tìm thấy resource:

```java
given(orderService.getRequired(ORDER_ID))
        .willThrow(new OrderNotFoundException(ORDER_ID));

mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isNotFound());
```

Nếu API dùng `@ControllerAdvice` để trả error representation có hypermedia, hãy kiểm tra cả `Content-Type`, body lỗi và các link phù hợp. Không phải mọi error response đều cần link; chỉ công bố những liên kết có ý nghĩa trong ngữ cảnh lỗi.

## 11. Dùng @WebMvcTest cho controller slice

`@WebMvcTest` giới hạn application context vào thành phần web và phù hợp khi cần test controller nhanh. Ví dụ:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(OrderModelAssembler.class)
class OrderControllerSliceTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
```

Nếu assembler phụ thuộc thêm bean hoặc ứng dụng có cấu hình HAL/CURIE tùy biến, import các thành phần cần thiết vào slice. Nếu slice test không có hypermedia message converter mà ứng dụng sử dụng, response có thể không serialize như khi chạy toàn bộ application context. Trong trường hợp đó, dùng `@SpringBootTest` để kiểm tra cấu hình đầy đủ hoặc cấu hình converter tường minh cho slice.

Không nên mock chính assembler khi mục tiêu của test là xác nhận link được tạo đúng. Mock service/repository để cô lập dữ liệu, nhưng để assembler và converter thật hoạt động trong request.

## 12. Dùng standaloneSetup khi cần kiểm soát MVC tối thiểu

`MockMvcBuilders.standaloneSetup(...)` tạo MockMvc trực tiếp từ controller mà không tải Spring application context:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController(orderService, assembler))
        .build();
```

Cách này nhanh và phù hợp cho controller đơn giản, nhưng không tự động mang theo toàn bộ cấu hình Spring Boot, `WebMvcConfigurer`, exception handler, argument resolver hoặc HAL message converter của ứng dụng. Nếu test representation HATEOAS, cần đăng ký converter và cấu hình Jackson hypermedia tương ứng; nếu không, test có thể chỉ serialize DTO như JSON thông thường hoặc không xử lý được `EntityModel`.

Khi mục tiêu là kiểm tra hành vi tích hợp Spring HATEOAS, `@WebMvcTest` với cấu hình cần thiết hoặc `@SpringBootTest` thường phản ánh ứng dụng thật tốt hơn.

## 13. Kiểm tra link mà không khóa test vào hostname

Link được tạo bởi `WebMvcLinkBuilder` có thể chứa scheme, host, port, context path và forwarded header. Một test chạy trên máy khác có thể tạo base URI khác nhau. Tránh so sánh toàn bộ URL nếu hostname không phải phần hợp đồng cần kiểm tra.

Ví dụ:

```java
.andExpect(jsonPath("$._links.self.href")
        .value(containsString("/orders/" + ORDER_ID)))
```

Nếu cần kiểm tra chính xác base URI, cấu hình request host hoặc forwarded header trong test và kiểm tra riêng tình huống triển khai sau reverse proxy. Không thay đổi production URL chỉ để làm assertion test ổn định.

Đối với custom relation, ưu tiên kiểm tra relation và sự hiện diện của `href`; đối với link pagination, kiểm tra query parameter quan trọng được giữ lại. Điều này giúp test tập trung vào hợp đồng hypermedia thay vì chi tiết triển khai không liên quan.

## 14. Kiểm tra forwarded headers và context path

Ứng dụng có thể chạy dưới context path hoặc phía sau proxy. Khi đó, link tuyệt đối phải phản ánh địa chỉ công khai mà client dùng để gọi API. MockMvc có thể mô phỏng forwarded headers để kiểm tra cấu hình `ForwardedHeaderFilter` hoặc chiến lược xử lý forwarded header của ứng dụng.

Ví dụ request có header:

```java
mockMvc.perform(get("/orders/{id}", ORDER_ID)
        .header("X-Forwarded-Proto", "https")
        .header("X-Forwarded-Host", "api.example.test")
        .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href")
                .value(containsString("https://api.example.test/")));
```

Header chỉ ảnh hưởng link nếu ứng dụng được cấu hình tin và xử lý forwarded header. Không nên tin header do client bất kỳ gửi trong production; proxy đáng tin cậy phải ghi đè hoặc loại bỏ các giá trị forwarded không đáng tin.

## 15. Chiến lược tổ chức bộ kiểm thử

Một bộ test tốt nên chia trách nhiệm theo tầng:

| Loại test | Phạm vi | Điều cần xác nhận |
| --- | --- | --- |
| Unit test assembler | Java model trước serialization | Relation, `href`, điều kiện thêm link |
| MVC slice test | Controller và web layer cần thiết | Mapping, validation, status, binding và HAL converter đã import |
| MVC integration test | Application context đầy đủ với MockMvc | Content negotiation, converter, `_links`, `_embedded`, pagination và affordance |
| End-to-end test | Ứng dụng chạy qua hạ tầng thật | Proxy, TLS, base URI, gateway và cache |

Không cần lặp mọi assertion ở mọi tầng. Unit test tập trung logic assembler; MVC integration test xác nhận representation thực tế; end-to-end test kiểm tra các thành phần chỉ xuất hiện trong môi trường triển khai.

## 16. Lỗi thường gặp

**Không đặt `Accept` trong request:** test có thể nhận JSON thông thường hoặc representation khác với định dạng hypermedia mong đợi. Hãy yêu cầu `MediaTypes.HAL_JSON` hoặc media type cần kiểm tra.

**Chỉ kiểm tra status 200:** endpoint có thể thành công nhưng link không được serialize. Kiểm tra `Content-Type`, `_links` và metadata liên quan.

**Dùng standaloneSetup mà quên converter:** cấu hình HATEOAS của ứng dụng không tự được tải. Đăng ký converter hoặc dùng Spring test context.

**Mock assembler trong test hypermedia:** test không còn kiểm tra logic tạo link. Hãy để assembler thật chạy và mock service/repository.

**Khẳng định `next` luôn tồn tại:** trang cuối không có link `next`. Chuẩn bị dữ liệu phù hợp với trang đang kiểm tra.

**Hard-code hostname trong assertion:** test dễ hỏng giữa môi trường. Kiểm tra path hoặc cấu hình base URI rõ ràng.

**Kiểm tra HAL-FORMS bằng HAL media type:** template affordance cần media type hỗ trợ như `MediaTypes.HAL_FORMS_JSON`.

**Bỏ qua lỗi content negotiation:** mapping `produces`/`consumes` có thể sai mà test happy path chưa phát hiện. Bổ sung test `406` và `415` theo hợp đồng.

## 17. Checklist kiểm thử MockMvc với HATEOAS

- Dùng `@SpringBootTest` hoặc `@WebMvcTest` theo phạm vi cần kiểm tra.
- Đảm bảo HATEOAS message converter và Jackson hypermedia module được cấu hình trong test context.
- Gửi `Accept` đúng media type.
- Với request body, gửi đúng `Content-Type`.
- Kiểm tra status code và `Content-Type` response.
- Kiểm tra `self` link và các relation nghiệp vụ.
- Kiểm tra `_embedded` và collection relation khi trả collection.
- Kiểm tra `page` metadata và link điều hướng khi trả PagedModel.
- Kiểm tra `_templates` khi test affordance bằng HAL-FORMS.
- Kiểm tra lỗi `400`, `404`, `406` và `415` theo hợp đồng.
- Tránh phụ thuộc hostname/port nếu chúng không phải một phần của hợp đồng.
- Kiểm tra forwarded header ở test phù hợp và chỉ tin proxy đáng tin trong production.
- Giữ assembler thật trong test integration; mock tầng service/repository.

MockMvc giúp kiểm tra representation HATEOAS ở đúng ranh giới HTTP của Spring MVC. Khi test yêu cầu media type rõ ràng, để converter hypermedia thật serialize model và xác nhận link cùng metadata bằng JSONPath, nhóm phát triển có thể phát hiện sớm lỗi trong content negotiation và hợp đồng điều hướng trước khi client tích hợp.

## Tài liệu tham khảo

- [Spring Framework Reference – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Boot Reference – Testing Spring MVC applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring HATEOAS Reference – HAL support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal)
- [Spring HATEOAS Reference – Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
