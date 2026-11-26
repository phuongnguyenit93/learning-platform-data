# Affordance cho POST trong Spring HATEOAS

Một liên kết hypermedia thông thường cho máy khách biết tài nguyên nào có thể được truy cập và quan hệ của liên kết đó. Nhưng khi API cho phép tạo đơn hàng, gửi yêu cầu hoàn tiền hoặc hủy một đơn hàng, chỉ có URI là chưa đủ: máy khách còn cần biết thao tác dùng HTTP method nào, gửi dữ liệu gì và gửi đến đâu.

**Affordance** bổ sung mô tả về hành động có thể thực hiện trên một tài nguyên. Với Spring HATEOAS, có thể gắn affordance vào Link bằng API Affordances. Khi response được xuất dưới dạng **HAL-FORMS**, các hành động này được biểu diễn thành các template trong phần _templates. Bài này tập trung vào affordance dùng **POST**, đặc biệt là tạo tài nguyên mới và thực hiện một lệnh nghiệp vụ.

## 1. Link và affordance giải quyết hai câu hỏi khác nhau

Một Link có href và relation. Nó cho máy khách biết đích đến và ý nghĩa của quan hệ:

~~~json
{
  "_links": {
    "orders": {
      "href": "/orders"
    }
  }
}
~~~

Máy khách biết có thể đi tới collection đơn hàng tại /orders, nhưng chưa biết có thể gửi POST để tạo đơn hàng hay không, dữ liệu nào cần gửi và trường nào bắt buộc.

Affordance bổ sung thông tin hành động:

- HTTP method, chẳng hạn POST.
- URI đích của thao tác.
- Kiểu dữ liệu đầu vào và các thuộc tính có thể gửi.
- Kiểu representation đầu ra khi được khai báo.
- Metadata hỗ trợ máy khách dựng form hoặc request phù hợp.

Có thể phân biệt:

| Thành phần | Vai trò |
|---|---|
| Link | Công bố đích đến và relation |
| Affordance | Mô tả hành động có thể thực hiện trên đích đến |
| Controller endpoint | Nhận request và thực thi nghiệp vụ |
| HAL-FORMS template | Tuần tự hóa affordance thành metadata mà máy khách có thể đọc |

Affordance không thay thế endpoint. Nó mô tả khả năng mà server công bố; request thực tế vẫn được xử lý bởi controller và các lớp nghiệp vụ.

## 2. Vì sao POST thường cần affordance?

POST được dùng cho nhiều loại thao tác. Hai tình huống phổ biến:

1. **Tạo tài nguyên:** POST lên collection, ví dụ POST /orders để tạo đơn hàng mới.
2. **Thực hiện hành động:** POST lên một endpoint hành động, ví dụ POST /orders/42/cancel để yêu cầu hủy đơn hàng.

Với cả hai tình huống, máy khách cần biết request body có cấu trúc nào và gửi đến endpoint nào.

Ví dụ tạo đơn hàng:

~~~http
POST /orders
Content-Type: application/json

{
  "customerId": 7,
  "shippingAddress": "12 Nguyen Hue",
  "items": [
    {
      "productId": 31,
      "quantity": 2
    }
  ]
}
~~~

Ví dụ yêu cầu hủy đơn:

~~~http
POST /orders/42/cancel
Content-Type: application/json

{
  "reason": "Customer requested cancellation"
}
~~~

Các ví dụ trên minh họa hai contract khác nhau. Request tạo đơn có thông tin khách hàng và mặt hàng; request hủy đơn có thể nhận lý do hủy. Không nên dùng chung một DTO đầu vào chỉ vì cả hai endpoint đều dùng POST.

## 3. Affordances API trong Spring HATEOAS

Spring HATEOAS cung cấp lớp Affordances để bổ sung hành động vào một Link. Các phương thức thường gặp:

| API | Vai trò |
|---|---|
| Affordances.of(link) | Bắt đầu khai báo affordance cho một link |
| afford(HttpMethod.POST) | Bắt đầu affordance thủ công với HTTP method cụ thể |
| andAffordance(afford(methodOn(...))) | Gắn affordance suy ra từ phương thức controller vào Link |
| withInput(Type.class) | Khai báo kiểu dữ liệu đầu vào |
| withOutput(Type.class) | Khai báo kiểu representation đầu ra khi cần |
| withInputMediaType(...) | Khai báo media type của request body khi tạo affordance thủ công |
| withName(...) | Đặt tên template |
| toLink() | Trả về Link có affordance đã khai báo khi dùng API thủ công |

Các import thường dùng với Spring MVC:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.hateoas.Link;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
~~~

Khi tham chiếu phương thức controller, Spring HATEOAS có thể suy ra mapping và metadata của request/response:

~~~java
Link collectionWithCreate = linkTo(
    methodOn(OrderController.class).all()
).withSelfRel()
    .andAffordance(afford(methodOn(OrderController.class).create(null)));
~~~

Lời gọi afford(methodOn(...)) tạo metadata từ phương thức POST được tham chiếu. Giá trị null chỉ là đối số placeholder cho request body khi mô tả phương thức; methodOn không gọi thân controller và không tạo đơn hàng.

Khi cần khai báo thủ công, dùng API Affordances:

~~~java
Link collection = linkTo(
    methodOn(OrderController.class).all()
).withSelfRel();

Link createOrder = Affordances.of(collection)
    .afford(HttpMethod.POST)
    .withInput(CreateOrderRequest.class)
    .withInputMediaType(MediaType.APPLICATION_JSON)
    .withOutput(OrderDto.class)
    .toLink();
~~~

Ở cách thủ công này, withInput và withOutput cung cấp kiểu dữ liệu cho template; withInputMediaType khai báo kiểu request body; toLink() trả về Link đã gắn affordance. Có thể thêm withName(...) nếu muốn đặt tên template tường minh. Nếu muốn framework tự phân tích mapping và kiểu payload từ controller, dùng cách andAffordance(afford(methodOn(...))) ở ví dụ trước.

## 4. Khai báo endpoint POST tạo đơn hàng

Trước tiên, controller cần có endpoint POST thực sự. Ví dụ dùng DTO đầu vào riêng:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;

public record CreateOrderRequest(
    @NotNull Long customerId,
    @NotNull @Size(min = 1) String shippingAddress,
    @NotNull @Size(min = 1) List<@Valid CreateOrderLineRequest> items
) {}

public record CreateOrderLineRequest(
    @NotNull Long productId,
    @NotNull @Min(1) Integer quantity
) {}
~~~

Các annotation validation mô tả điều kiện dữ liệu mà server kiểm tra khi nhận request. Với ứng dụng dùng Spring Boot 2 hoặc Java EE namespace cũ, package validation có thể là javax.validation thay vì jakarta.validation.

Controller:

~~~java
import org.springframework.http.MediaType;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;
    private final OrderAssembler assembler;

    public OrderController(
            OrderService orderService,
            OrderAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping
    public CollectionModel<EntityModel<OrderDto>> all() {
        // Phần truy vấn danh sách được rút gọn trong ví dụ.
        throw new UnsupportedOperationException("Ví dụ minh họa");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<EntityModel<OrderDto>> create(
            @Valid @RequestBody CreateOrderRequest request) {

        Order created = orderService.create(request);
        EntityModel<OrderDto> representation = assembler.toModel(created);

        URI location = representation
            .getRequiredLink(IanaLinkRelations.SELF)
            .toUri();

        return ResponseEntity
            .created(location)
            .body(representation);
    }
}
~~~

Endpoint nhận request body, kiểm tra dữ liệu, gọi service và trả về tài nguyên vừa tạo. Với trường hợp tạo tài nguyên thành công, HTTP 201 Created cùng Location header thường phù hợp. Representation trả về có thể chứa link self của tài nguyên mới.

Affordance chỉ mô tả endpoint này cho máy khách. Nó không tạo ra mapping POST, không gọi service và không tự sinh response 201.

## 5. Gắn affordance POST vào link collection

Sau khi có endpoint POST, API có thể công bố khả năng tạo đơn hàng ngay trên representation collection.

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;

@Component
public class OrderCollectionAssembler {

    private final OrderService orderService;
    private final OrderAssembler orderAssembler;

    public OrderCollectionAssembler(
            OrderService orderService,
            OrderAssembler orderAssembler) {
        this.orderService = orderService;
        this.orderAssembler = orderAssembler;
    }

    public CollectionModel<EntityModel<OrderDto>> toModel() {
        var content = orderService.findAll().stream()
            .map(orderAssembler::toModel)
            .toList();

        Link collectionWithCreate = linkTo(
            methodOn(OrderController.class).all()
        ).withSelfRel()
            .andAffordance(afford(
                methodOn(OrderController.class).create(null)
            ));

        return CollectionModel.of(content, collectionWithCreate);
    }
}
~~~

Trong ví dụ:

1. Link collection được tạo từ mapping của phương thức all.
2. afford(methodOn(...).create(null)) tham chiếu phương thức POST tạo đơn.
3. andAffordance gắn mô tả thao tác POST vào link collection.
4. Spring HATEOAS phân tích kiểu request body và response từ chữ ký controller.
5. CollectionModel trả về các đơn hàng và link collection có affordance.

Nếu collection được trả về từ controller, hãy dùng assembler này để tạo representation. Máy khách có thể đọc link collection và affordance tạo mới từ cùng một response.

Không nên thêm affordance POST nếu endpoint chưa tồn tại hoặc không khả dụng trong contract hiện tại. Metadata công bố cần phản ánh đúng mapping mà server có thể xử lý.

## 6. HAL-FORMS biểu diễn POST affordance như thế nào?

HAL-FORMS là một media type hypermedia có thể biểu diễn link và các template hành động. Khi một Link có affordance được tuần tự hóa thành HAL-FORMS, metadata hành động được đặt trong _templates.

Ví dụ minh họa cho template tạo đơn hàng:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders"
    }
  },
  "_templates": {
    "default": {
      "method": "post",
      "properties": [
        {
          "name": "customerId",
          "required": true
        },
        {
          "name": "shippingAddress",
          "required": true
        },
        {
          "name": "items",
          "required": true
        }
      ]
    }
  }
}
~~~

Template cho máy khách biết:

- Phương thức cần dùng là POST.
- Các thuộc tính đầu vào được công bố.
- Những thuộc tính nào được đánh dấu bắt buộc.
- Link hoặc target liên quan xác định nơi gửi thao tác.

Đây là cấu trúc minh họa để giải thích HAL-FORMS. Tên template, target, contentType và metadata property thực tế phụ thuộc affordance, cấu hình serializer và kiểu dữ liệu được khai báo.

Máy khách cần đọc template thay vì tự suy luận rằng mọi collection đều hỗ trợ POST hoặc tự đoán tên field của request.

## 7. Chọn media type để công bố affordance

HAL JSON thông thường chủ yếu công bố link và embedded resource. Để gửi metadata biểu mẫu của affordance, API có thể trả về HAL-FORMS:

~~~http
GET /orders
Accept: application/prs.hal-forms+json
~~~

Trong Spring HATEOAS, media type có hằng số tương ứng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = {
    HypermediaType.HAL,
    HypermediaType.HAL_FORMS
})
class HypermediaConfiguration {}
~~~

Controller có thể khai báo media type sản xuất:

~~~java
import org.springframework.hateoas.MediaTypes;

@GetMapping(produces = {
    MediaTypes.HAL_JSON_VALUE,
    MediaTypes.HAL_FORMS_JSON_VALUE
})
public CollectionModel<EntityModel<OrderDto>> all() {
    return orderCollectionAssembler.toModel();
}
~~~

Nếu endpoint cần hỗ trợ nhiều định dạng, có thể cấu hình content negotiation để trả về HAL-FORMS hoặc HAL JSON theo Accept header. Cần kiểm thử đúng media type mà máy khách yêu cầu.

HAL-FORMS mở rộng ý tưởng của HAL nhưng là một media type riêng, không thể xem hai định dạng là thay thế trực tiếp cho nhau. Một response HAL JSON vẫn có thể chứa link collection, nhưng máy khách sẽ không nhận được cấu trúc template HAL-FORMS giống như response được tuần tự hóa theo media type HAL-FORMS.

## 8. Affordance cho POST hành động trên một tài nguyên

POST không chỉ dùng để tạo tài nguyên mới. Một số API dùng POST cho hành động nghiệp vụ, ví dụ hủy đơn hàng hoặc xác nhận thanh toán.

Request DTO:

~~~java
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CancelOrderRequest(
    @NotNull @Size(min = 1) String reason
) {}
~~~

Endpoint:

~~~java
import org.springframework.http.MediaType;

@PostMapping(value = "/{id}/cancel", consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<EntityModel<OrderDto>> cancel(
        @PathVariable Long id,
        @Valid @RequestBody CancelOrderRequest request) {

    Order updated = orderService.cancel(id, request.reason());
    EntityModel<OrderDto> representation = assembler.toModel(updated);

    return ResponseEntity.ok(representation);
}
~~~

Khi đơn hàng có thể hủy, assembler có thể gắn affordance vào link self:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

Link self = linkTo(
    methodOn(OrderController.class).one(order.getId())
).withSelfRel();

if (order.canBeCancelled()) {
    self = self.andAffordance(afford(methodOn(OrderController.class)
        .cancel(order.getId(), null)));
}

return EntityModel.of(orderMapper.toDto(order), self);
~~~

Ở đây, link self vẫn dẫn đến tài nguyên đơn hàng. Affordance bổ sung mô tả thao tác POST cancel mà controller cung cấp. Nếu trạng thái đơn hàng không cho phép hủy, response không công bố affordance đó.

Vì URI của thao tác cancel khác href của link self, HAL-FORMS có thể đưa target riêng vào template để máy khách gửi POST đến /orders/{id}/cancel. Với thao tác tạo đơn, target thường trùng href của link collection nên thuộc tính target có thể được lược bỏ.

Việc không công bố affordance không phải cơ chế bảo mật. Endpoint cancel vẫn phải kiểm tra quyền, trạng thái và điều kiện nghiệp vụ tại thời điểm nhận request.

## 9. Metadata đầu vào và validation

Khi khai báo affordance thủ công, withInput(CreateOrderRequest.class) cho Spring HATEOAS biết kiểu dữ liệu mà thao tác POST nhận. Khi tham chiếu trực tiếp phương thức controller bằng afford(methodOn(...)), framework phân tích tham số request body và kiểu response từ chữ ký phương thức.

Nếu controller khai báo consumes = application/json, Spring HATEOAS có thể đưa contentType tương ứng vào HAL-FORMS template. Khi dùng API thủ công, withInputMediaType(MediaType.APPLICATION_JSON) cung cấp cùng thông tin đó.

Khi thiết kế DTO đầu vào:

- Dùng kiểu dữ liệu cụ thể, có tên field rõ ràng.
- Tách DTO tạo mới khỏi DTO đọc hoặc DTO cập nhật nếu contract khác nhau.
- Dùng validation annotation để server kiểm tra dữ liệu.
- Chỉ đưa các trường mà máy khách được phép gửi vào input type.
- Tránh dùng trực tiếp JPA entity làm request body.

HAL-FORMS có thể chuyển một số metadata Bean Validation thành thuộc tính của form:

| Annotation/metadata | Thuộc tính HAL-FORMS có thể tạo |
|---|---|
| @NotNull | required |
| @Pattern | regex |
| @Size, @Min, @Max, @DecimalMin, @DecimalMax | min hoặc max |
| @Email hoặc kiểu dữ liệu tương ứng | type phù hợp, chẳng hạn email |

Bean Validation vẫn phải được thực thi ở server. Không phải mọi annotation hoặc custom validator đều được chuyển thành một quy tắc tương tác trong HAL-FORMS. Máy khách có thể dùng metadata để dựng form, nhưng server vẫn là nơi quyết định request có hợp lệ hay không.

Nếu API có enum, collection lồng nhau, giá trị mặc định hoặc quy tắc phụ thuộc trạng thái, hãy kiểm tra JSON HAL-FORMS được sinh ra và tài liệu hóa các giới hạn mà template không thể diễn đạt đầy đủ.

## 10. Mô tả output và response của POST

Một thao tác POST có thể trả về nhiều kiểu kết quả:

| Kết quả | HTTP response thường gặp | Ý nghĩa |
|---|---|---|
| Tạo tài nguyên đồng bộ | 201 Created | Tài nguyên mới đã được tạo; thường kèm Location |
| Chấp nhận xử lý nền | 202 Accepted | Yêu cầu được nhận nhưng chưa hoàn tất |
| Hoàn tất thao tác không có body | 204 No Content | Thao tác thành công, không trả representation |
| Trả kết quả nghiệp vụ | 200 OK | Server trả representation kết quả |

Affordance có thể mô tả kiểu output bằng withOutput(...) khi cần khai báo rõ representation đầu ra. Tuy nhiên, metadata đó không thay thế status code, response header hoặc nội dung response thực tế.

Ví dụ tạo tài nguyên nên trả 201 và Location trỏ tới tài nguyên vừa tạo. Nếu POST chỉ khởi động một tác vụ nền, response có thể là 202 cùng link tới trạng thái tác vụ. Hãy thiết kế response theo semantics HTTP và contract của endpoint.

## 11. POST và khả năng gửi lặp

POST không mặc nhiên có tính idempotent. Nếu máy khách gửi lại cùng một request do timeout hoặc mất kết nối, server có thể tạo nhiều tài nguyên hoặc thực hiện hành động nhiều lần.

Affordance chỉ mô tả cách gọi thao tác; nó không bảo đảm thao tác an toàn khi gửi lặp. Với nghiệp vụ nhạy cảm như tạo đơn hàng, thanh toán hoặc hoàn tiền, có thể cần cơ chế idempotency key hoặc mã yêu cầu duy nhất do server quản lý.

Ví dụ header:

~~~http
POST /orders
Idempotency-Key: 4b1e9a0c-unique-request-key
Content-Type: application/json
~~~

Nếu contract sử dụng idempotency key, cần tài liệu hóa cách gửi, phạm vi duy nhất, thời gian lưu và response khi máy khách gửi lại cùng key. Không nên cho rằng HAL-FORMS tự sinh hoặc quản lý cơ chế này.

## 12. Kiểm thử affordance POST

Nên kiểm tra cả endpoint thực thi POST lẫn metadata affordance được công bố trong response HAL-FORMS.

Kiểm tra media type và template:

~~~java
mockMvc.perform(
        get("/orders")
            .accept(MediaTypes.HAL_FORMS_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_FORMS_JSON
    ))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates.default.method").value("post"))
    .andExpect(jsonPath(
        "$._templates.default.properties[?(@.name=='customerId')]"
    ).exists());
~~~

Kiểm tra endpoint tạo đơn:

~~~java
mockMvc.perform(
        post("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "customerId": 7,
                  "shippingAddress": "12 Nguyen Hue",
                  "items": [
                    {
                      "productId": 31,
                      "quantity": 2
                    }
                  ]
                }
                """)
    )
    .andExpect(status().isCreated())
    .andExpect(header().exists(HttpHeaders.LOCATION))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Với dự án Java trước phiên bản 15, hãy tạo request JSON bằng ObjectMapper hoặc chuỗi phù hợp thay vì dùng text block.

Kiểm tra affordance hành động theo trạng thái:

- Đơn hàng có thể hủy: template POST cancel xuất hiện.
- Đơn hàng đã giao hoặc đã hủy: template cancel không xuất hiện.
- Request hủy thiếu reason: server trả lỗi validation theo contract.
- Người gọi không có quyền: server từ chối request dù đã biết URI.
- Gửi request hợp lệ: trạng thái đơn hàng thay đổi theo nghiệp vụ.

Ngoài ra, cần xác nhận target và method trong template trỏ đến đúng endpoint. Chỉ kiểm tra template có tồn tại là chưa đủ.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ công bố link collection mà không mô tả POST | Máy khách không biết cách tạo tài nguyên | Gắn affordance với input type |
| Có affordance nhưng chưa có endpoint | Máy khách gửi request vào route không tồn tại | Triển khai mapping POST trước |
| Dùng sai input DTO | Template công bố field không khớp request | Dùng DTO đầu vào đúng với @RequestBody |
| Nhầm HAL JSON với HAL-FORMS | Máy khách không thấy template affordance | Trả đúng media type HAL-FORMS |
| Gắn affordance hủy cho mọi đơn hàng | Công bố hành động không khả dụng | Kiểm tra trạng thái trước khi gắn |
| Dùng affordance như authorization | Request trực tiếp vẫn có thể vượt qua nếu endpoint không kiểm tra | Kiểm tra quyền tại server |
| Cho rằng validation metadata bảo đảm request hợp lệ | Client có thể gửi dữ liệu sai | Validate lại bằng Bean Validation và nghiệp vụ |
| Cho rằng POST an toàn khi retry | Có thể tạo trùng hoặc thực hiện lặp hành động | Thiết kế idempotency khi cần |

## 14. Quy trình thiết kế Affordance cho POST

Khi công bố một thao tác POST bằng Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định POST dùng để tạo tài nguyên hay thực hiện hành động nghiệp vụ.
2. Thiết kế endpoint, HTTP status và response theo semantics HTTP.
3. Tạo DTO đầu vào riêng và xác định các trường bắt buộc.
4. Dùng linkTo và methodOn để tạo link cơ sở theo mapping controller.
5. Dùng andAffordance(afford(methodOn(...))) để lấy metadata từ phương thức POST, hoặc Affordances.of(link).afford(HttpMethod.POST) để khai báo thủ công.
6. Với cách khai báo thủ công, dùng withInput(...), withInputMediaType(...) và withOutput(...) nếu cần mô tả kiểu dữ liệu và media type.
7. Trả response HAL-FORMS khi máy khách cần đọc form template.
8. Chỉ công bố affordance khi thao tác khả dụng trong ngữ cảnh hiện tại.
9. Kiểm tra authorization, validation và quy tắc nghiệp vụ tại endpoint.
10. Kiểm thử cả template được công bố và request POST thực tế.

Affordance cho POST giúp API mô tả rõ một hành động có thể thực hiện, gồm đích đến, HTTP method và dữ liệu đầu vào. Khi kết hợp Affordances với controller mapping và HAL-FORMS, máy khách có thể khám phá thao tác tạo tài nguyên hoặc lệnh nghiệp vụ ngay từ response. Server vẫn chịu trách nhiệm xác thực, kiểm tra dữ liệu, áp dụng quy tắc nghiệp vụ và trả response đúng contract.
