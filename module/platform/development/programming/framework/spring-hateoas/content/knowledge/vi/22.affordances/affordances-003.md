# Affordance trên Link

Trong REST, một link cho client biết tài nguyên hoặc đích tiếp theo nằm ở đâu. Tuy nhiên, chỉ có `href` và `rel` thường chưa đủ để client biết cần gửi HTTP method nào, cấu trúc request body ra sao hoặc response dự kiến có kiểu dữ liệu gì. **Affordance** bổ sung mô tả về hành động có thể thực hiện thông qua một link.

Spring HATEOAS cho phép gắn một hoặc nhiều affordance vào cùng một `Link`. Ví dụ, link `self` của đơn hàng có thể đồng thời mô tả thao tác `PUT` để thay thế đơn hàng và `PATCH` để cập nhật một phần. Client nhận representation có thể khám phá những thao tác server công bố, cùng metadata đầu vào và đầu ra phù hợp với media type được thương lượng.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt link thông thường với affordance gắn trên link.
- Giải thích các metadata chính của một affordance: HTTP method, target, input, output và query parameters.
- Tạo affordance từ phương thức Spring MVC bằng `afford(methodOn(...))`.
- Gắn nhiều affordance lên cùng một link bằng `andAffordance()`.
- Xây affordance thủ công bằng `Affordances.of()`.
- Hiểu cách HAL-FORMS biểu diễn affordance thành `_templates`.
- Công bố affordance có điều kiện và kiểm thử metadata trong response.

## Link và affordance khác nhau thế nào?

Một link hypermedia cơ bản gồm relation và URI đích:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    }
  }
}
```

Client biết `self` là liên kết tới representation hiện tại và có thể dùng `href` để truy cập. Nhưng link này chưa mô tả liệu server hỗ trợ `PUT`, `PATCH`, `DELETE` hay một thao tác khác trên URI đó. Nó cũng chưa mô tả payload mà thao tác cần nhận.

Affordance bổ sung mô tả hành động gắn với link. Một affordance có thể chứa:

| Metadata | Ý nghĩa | Ví dụ |
|---|---|---|
| HTTP method | Phương thức HTTP được hỗ trợ | `PUT`, `PATCH`, `POST` |
| Target | URI mà thao tác gửi request tới | `/orders/42` |
| Input model | Kiểu dữ liệu request body | `OrderInput` |
| Output model | Kiểu dữ liệu kết quả | `OrderView` |
| Input media type | Định dạng payload server mong đợi | `application/json` |
| Query parameters | Tham số truy vấn của thao tác | `status`, `page` |
| Name | Tên thao tác trong biểu diễn hypermedia | `updateOrder` |

Một link có thể có nhiều affordance. Chẳng hạn, `self` vẫn chỉ tới `/orders/42`, trong khi các affordance gắn với nó mô tả `PUT /orders/42` và `PATCH /orders/42`. Link trả lời câu hỏi “đi tới đâu”; affordance bổ sung câu hỏi “có thể làm gì ở đó và cần gửi dữ liệu nào”.

Affordance là metadata của hợp đồng API, không phải lệnh đã thực thi. Nó cũng không phải cơ chế cấp quyền. Server vẫn phải kiểm tra xác thực, phân quyền, trạng thái nghiệp vụ và dữ liệu đầu vào khi nhận request thực tế.

## Tạo affordance từ controller method

Cách phổ biến nhất là để Spring HATEOAS phân tích mapping controller. API `afford(...)` nhận một lời gọi proxy được tạo bằng `methodOn(...)`, sau đó trích xuất thông tin HTTP method, request body, response type và mapping.

Giả sử API quản lý đơn hàng có các DTO:

```java
import java.util.List;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record OrderInput(
    @NotBlank String reference,
    @NotNull String deliveryAddress
) {
}

record OrderPatch(String deliveryNote) {
}

record Order(long id, String reference, String deliveryAddress, String status) {
    boolean canBeReplaced() {
        return status.equals("DRAFT");
    }

    boolean canBeCancelled() {
        return status.equals("DRAFT") || status.equals("SUBMITTED");
    }
}

record OrderView(long id, String reference, String deliveryAddress) {
    static OrderView from(Order order) {
        return new OrderView(order.id(), order.reference(), order.deliveryAddress());
    }
}

interface OrderService {
    OrderView findById(long id);
    Order getOrder(long id);
    OrderView replace(long id, OrderInput input);
    OrderView patch(long id, OrderPatch input);
    OrderView cancel(long id);
    List<OrderView> findAll(String status, int page);
}
```

Controller công bố endpoint đọc, thay thế và cập nhật một phần đơn hàng:

```java
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping
    List<OrderView> all(
            @RequestParam(required = false) String status,
            @RequestParam(defaultValue = "0") int page) {
        return orders.findAll(status, page);
    }

    @GetMapping("/{id}")
    EntityModel<OrderView> one(@PathVariable long id) {
        OrderView order = orders.findById(id);

        Link self = linkTo(methodOn(OrderController.class).one(id))
            .withSelfRel()
            .andAffordance(afford(methodOn(OrderController.class)
                .replace(null, id)))
            .andAffordance(afford(methodOn(OrderController.class)
                .patch(null, id)));

        return EntityModel.of(order, self);
    }

    @PutMapping(path = "/{id}", consumes = "application/json")
    ResponseEntity<OrderView> replace(
            @Valid @RequestBody OrderInput input,
            @PathVariable long id) {
        return ResponseEntity.ok(orders.replace(id, input));
    }

    @PatchMapping(path = "/{id}", consumes = "application/json")
    ResponseEntity<OrderView> patch(
            @RequestBody OrderPatch input,
            @PathVariable long id) {
        return ResponseEntity.ok(orders.patch(id, input));
    }

    @PostMapping("/{id}/cancellation")
    ResponseEntity<OrderView> cancel(@PathVariable long id) {
        return ResponseEntity.ok(orders.cancel(id));
    }
}
```

`OrderService` là service nghiệp vụ của ứng dụng, cung cấp `findById`, `replace` và `patch`. Trong phương thức `one()`:

1. `linkTo(methodOn(OrderController.class).one(id))` tạo link `self` tới mapping đọc đơn hàng.
2. `afford(methodOn(OrderController.class).replace(null, id))` tham chiếu phương thức `PUT`.
3. `afford(methodOn(OrderController.class).patch(null, id))` tham chiếu phương thức `PATCH`.
4. `andAffordance()` gắn từng affordance vào cùng link `self`.

Giá trị `null` ở vị trí request body chỉ là tham số placeholder để chọn phương thức và cho Spring HATEOAS biết kiểu input từ chữ ký method. Proxy do `methodOn()` tạo ra không thực thi phương thức controller và không gọi service. Path variable `id` được dùng để tạo URI đích; kiểu request body và response được suy ra từ khai báo phương thức.

`Link` là value object bất biến. `andAffordance()` trả về một `Link` mới chứa affordance bổ sung, vì vậy cần gán kết quả trở lại biến `self` nếu đang thêm affordance trong một nhánh điều kiện. Có thể xem metadata đã gắn bằng `link.getAffordances()` khi cần kiểm tra hoặc xử lý ở phía server.

`@RequestBody` giúp Spring HATEOAS nhận diện input payload. `@Valid` và các annotation Bean Validation trên DTO cung cấp thêm metadata để media type hỗ trợ biểu diễn quy tắc trường. Nếu phương thức có `consumes` hoặc affordance được cấu hình input media type tường minh, metadata có thể mô tả định dạng payload cần gửi.

## Một link có thể mô tả nhiều thao tác

Trong ví dụ đơn hàng, `self` là link tới representation hiện tại. Cùng link đó có thể mô tả hai thao tác:

| Affordance | HTTP method | Target | Input |
|---|---|---|---|
| `replace` | `PUT` | `/orders/42` | `OrderInput` |
| `patch` | `PATCH` | `/orders/42` | `OrderPatch` |

Đây là điểm quan trọng của affordance: không cần tạo một link riêng cho mỗi HTTP method nếu các thao tác cùng tác động lên một resource URI. Representation giữ một quan hệ `self`, còn metadata hành động được gắn kèm.

Khi thao tác hướng tới URI khác, affordance vẫn có thể được gắn vào link hiện tại nhưng target của nó sẽ là URI của endpoint thao tác. Media type có thể biểu diễn target riêng nếu target affordance khác link mà nó được gắn vào.

## Công bố affordance theo trạng thái tài nguyên

Không phải mọi thao tác đều khả dụng trong mọi trạng thái. Ví dụ, đơn hàng `DRAFT` có thể cho phép gửi đơn, đơn hàng `SUBMITTED` có thể cho phép xác nhận hoặc hủy, còn đơn đã giao không còn cho phép thay đổi địa chỉ giao hàng.

Có thể chỉ gắn affordance khi điều kiện nghiệp vụ cho phép:

```java
@GetMapping("/{id}")
EntityModel<OrderView> one(@PathVariable long id) {
    Order order = orders.getOrder(id);

    Link self = linkTo(methodOn(OrderController.class).one(id))
        .withSelfRel();

    if (order.canBeReplaced()) {
        self = self.andAffordance(afford(methodOn(OrderController.class)
            .replace(null, id)));
    }

    if (order.canBeCancelled()) {
        self = self.andAffordance(afford(methodOn(OrderController.class)
            .cancel(id)));
    }

    return EntityModel.of(OrderView.from(order), self);
}
```

Đoạn code minh họa giả định controller có endpoint `cancel(...)` và domain object có các phương thức kiểm tra trạng thái. Nếu người dùng hiện tại không có quyền thực hiện thao tác, policy bảo mật cũng cần được xét trước khi công bố affordance. Cần tránh truy vấn hoặc tính toán chính sách khác nhau giữa nơi công bố link và nơi thực thi nghiệp vụ.

Điều kiện công bố affordance giúp client xây dựng giao diện phù hợp với trạng thái hiện tại. Tuy nhiên, trạng thái có thể thay đổi sau khi response được gửi. Vì vậy, endpoint `replace`, `patch` hoặc `cancel` vẫn phải xác thực lại trạng thái và quyền ở phía server. Request dựa trên affordance cũ có thể nhận `409 Conflict` nếu thao tác không còn hợp lệ.

## Xây affordance thủ công bằng `Affordances`

Khi không thể suy ra đầy đủ mô tả từ controller method, Spring HATEOAS cung cấp API `Affordances` trong package `org.springframework.hateoas.mediatype`. Cách này cho phép chỉ định HTTP method, kiểu input/output, tên thao tác và query parameters trực tiếp.

```java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.QueryParameter;
import org.springframework.http.HttpMethod;

import static org.springframework.hateoas.mediatype.Affordances.of;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;

Link collection = linkTo(OrderController.class).withSelfRel();

Link collectionWithActions = of(collection)
    .afford(HttpMethod.POST)
        .withInput(OrderInput.class)
        .withOutput(OrderView.class)
        .withName("createOrder")
    .andAfford(HttpMethod.GET)
        .withOutput(OrderView.class)
        .addParameters(
            QueryParameter.optional("status"),
            QueryParameter.optional("page")
        )
        .withName("searchOrders")
    .toLink();
```

Trong ví dụ:

- `Affordances.of(collection)` tạo context từ link đã có.
- `.afford(HttpMethod.POST)` bắt đầu mô tả thao tác tạo đơn hàng.
- `.withInput(OrderInput.class)` khai báo kiểu payload đầu vào; `.withOutput(OrderView.class)` khai báo kiểu kết quả.
- `.andAfford(HttpMethod.GET)` kết thúc mô tả trước và bắt đầu affordance tìm kiếm.
- `.withOutput(OrderView.class)` mô tả kiểu kết quả tìm kiếm.
- `addParameters(...)` khai báo các query parameter tùy chọn.
- `.withName(...)` đặt tên rõ ràng cho thao tác.
- `.toLink()` trả về link đã mang các affordance vừa cấu hình.

`QueryParameter.required("name")` có thể dùng cho tham số bắt buộc; `QueryParameter.optional("name")` dùng cho tham số tùy chọn. Nếu cần giá trị mặc định hoặc giá trị cụ thể, có thể cấu hình `QueryParameter` tương ứng bằng API của kiểu này.

Nên dùng affordance suy ra từ controller method khi có thể, vì chữ ký method là nguồn mô tả trực tiếp cho mapping, input và output. Dùng API thủ công khi cần mô tả operation không gắn với handler method cụ thể, cần tùy chỉnh metadata hoặc đang tích hợp một API bên ngoài.

## Affordance và media type

Affordance trong Spring HATEOAS là metadata trung lập với định dạng. Spring HATEOAS giữ mô tả hành động trong `Link`, sau đó media type được thương lượng quyết định metadata đó được serialize như thế nào. Vì vậy, cùng một model có thể được biểu diễn khác nhau tùy `Accept` header.

### HAL JSON

HAL chuẩn tập trung vào `_links` và `_embedded`. Link cơ bản vẫn được biểu diễn bằng `href` và relation. HAL JSON không định nghĩa cấu trúc form tổng quát để mô tả mọi input field của affordance. Nếu client chỉ nhận HAL JSON, nó có thể khám phá link nhưng chưa chắc nhận được schema thao tác đầy đủ.

### HAL-FORMS

HAL-FORMS mở rộng HAL bằng thuộc tính `_templates`. Spring HATEOAS có thể chuyển affordance thành template chứa HTTP method, target, content type, tên thao tác và các property của request body.

Client có thể yêu cầu HAL-FORMS bằng header:

```http
GET /orders/42 HTTP/1.1
Host: api.example.test
Accept: application/prs.hal-forms+json
```

Response minh họa có thể chứa:

```json
{
  "id": 42,
  "reference": "ORD-2026-0042",
  "_links": {
    "self": {
      "href": "https://api.example.test/orders/42"
    }
  },
  "_templates": {
    "replace": {
      "method": "put",
      "properties": [
        { "name": "reference", "required": true, "type": "text" },
        { "name": "deliveryAddress", "required": true, "type": "text" }
      ]
    },
    "patch": {
      "method": "patch",
      "properties": [
        { "name": "deliveryNote", "required": false, "type": "text" }
      ]
    }
  }
}
```

Đây là cấu trúc minh họa. Tên template thường được suy ra từ tên phương thức controller khi có nhiều affordance; nếu chỉ có một template, HAL-FORMS dùng tên `default`. Target có thể không xuất hiện riêng khi nó trùng với link mà affordance được gắn vào. Các thuộc tính như `required`, `type`, `regex`, `min`, `max` hoặc `prompt` được suy ra hoặc tùy biến từ kiểu input và metadata validation.

Một số thuộc tính HAL-FORMS thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `method` | HTTP method để gửi template |
| `target` | URI nhận request; chỉ cần khi khác link gốc |
| `contentType` | Media type của request body |
| `title` | Tên hiển thị của template |
| `properties` | Các trường client cần gửi |
| `required` | Trường có bắt buộc hay không |
| `type` | Kiểu input, ví dụ `text`, `date`, `email` |
| `regex`, `min`, `max` | Ràng buộc dữ liệu nếu được cung cấp |

HAL-FORMS giúp client tạo form hoặc giao diện thao tác từ metadata. Nó không tự thay thế validation phía server; mọi dữ liệu client gửi vẫn cần được kiểm tra lại.

## Tùy chỉnh metadata input

Spring HATEOAS có thể lấy thông tin property từ kiểu input. Bean Validation annotations cung cấp các ràng buộc có thể chuyển thành metadata HAL-FORMS.

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

record CustomerInput(
    @NotBlank
    @Size(max = 80)
    String name,

    @NotBlank
    @Email
    String email
) {
}
```

Với affordance trỏ tới phương thức nhận `CustomerInput`, HAL-FORMS có thể mô tả `name` là bắt buộc và giới hạn độ dài, đồng thời đánh dấu `email` là trường email bắt buộc. Các annotation được hỗ trợ và cách ánh xạ cụ thể phụ thuộc metadata provider của Spring HATEOAS và validation provider trong ứng dụng.

Nếu kiểu dữ liệu hoặc thuộc tính cần metadata đặc biệt, có thể dùng các annotation và cấu hình HAL-FORMS chuyên biệt như `@InputType`, `HalFormsConfiguration` hoặc resource bundle để bổ sung pattern, options, prompt, placeholder và title. Không nên đưa thông tin bí mật hoặc dữ liệu nội bộ vào metadata được công bố cho client.

## Kiểm thử affordance

Kiểm thử nên xác nhận cả link cơ sở lẫn metadata hành động mà media type công bố. Ví dụ với MockMvc:

```java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderAffordanceTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orders;

    @Test
    void exposesUpdateTemplatesInHalForms() throws Exception {
        given(orders.findById(42L)).willReturn(
            new OrderView(42L, "ORD-2026-0042", "12 Nguyen Trai")
        );

        mockMvc.perform(get("/orders/{id}", 42)
                .accept("application/prs.hal-forms+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._templates.replace.method").value("put"))
            .andExpect(jsonPath("$._templates.patch.method").value("patch"))
            .andExpect(jsonPath("$._templates.replace.properties").isArray());
    }
}
```

Đây là khung kiểm thử; `OrderService` và DTO cần khớp với controller hoàn chỉnh của ứng dụng. Tên template trong assertion phải khớp tên method hoặc tên affordance đã cấu hình. Nếu ứng dụng chỉ bật HAL JSON mà chưa đăng ký HAL-FORMS mapping, cần bật media type HAL-FORMS trong cấu hình hypermedia.

Nên bổ sung các trường hợp:

- `GET` trả link `self` và affordance `PUT`/`PATCH` theo đúng trạng thái.
- Một trạng thái không cho phép cập nhật sẽ không công bố template tương ứng.
- Template chứa đúng HTTP method và target.
- Input model tạo ra property và validation metadata đúng.
- Query parameters bắt buộc và tùy chọn được biểu diễn chính xác.
- Client nhận được media type phù hợp với `Accept` header.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng `href` mô tả đầy đủ hành động | Client không biết method hoặc request body | Gắn affordance vào link khi cần mô tả thao tác |
| Tạo link riêng cho mọi method cùng target mà không cần thiết | Representation lặp URI và khó nhóm thao tác | Gắn nhiều affordance lên link tài nguyên phù hợp |
| Nghĩ `methodOn()` thực thi controller method | Có thể nhầm lẫn việc tạo metadata với xử lý nghiệp vụ | `methodOn()` tạo proxy để Spring HATEOAS phân tích mapping và chữ ký method |
| Dùng `null` placeholder như dữ liệu thực | Hiểu nhầm request body được gửi khi tạo affordance | Placeholder chỉ chọn method và cung cấp kiểu; handler không được gọi |
| Dùng HAL JSON nhưng kỳ vọng có form schema | Client chỉ thấy link cơ bản | Thương lượng `application/prs.hal-forms+json` nếu cần `_templates` |
| Công bố affordance như một cơ chế phân quyền | Client có thể gọi endpoint trực tiếp dù link không xuất hiện | Luôn kiểm tra quyền và trạng thái ở server |
| Input DTO không có validation metadata | Form có thể thiếu ràng buộc hữu ích | Dùng Bean Validation hoặc cấu hình metadata rõ ràng |
| Đổi tên method/affordance mà không kiểm thử | Tên template hoặc hợp đồng client thay đổi | Đặt tên ổn định và kiểm thử `_templates` |

## Ghi nhớ

Affordance bổ sung mô tả hành động cho một link. Spring HATEOAS có thể suy ra affordance từ controller method bằng `afford(methodOn(...))`, rồi gắn vào link bằng `andAffordance()`. Khi cần kiểm soát thủ công, dùng `Affordances.of(link).afford(HttpMethod)` để khai báo input, output, tên và query parameters. Metadata affordance được chuyển thành biểu diễn riêng theo media type; HAL-FORMS sử dụng `_templates` để mô tả HTTP method, target và các trường input. Hãy công bố hành động theo trạng thái và quyền hiện tại, đồng thời luôn xác thực lại mọi request ở phía server.

## Tài liệu tham khảo

- [Spring HATEOAS – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
- [Affordances API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/Affordances.html)
- [ConfigurableAffordance API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/ConfigurableAffordance.html)
