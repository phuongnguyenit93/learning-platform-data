# Version qua media type

## Mục tiêu

Một API có thể giữ nguyên URI của tài nguyên nhưng cung cấp nhiều phiên bản representation. Ví dụ, cùng một đơn hàng có thể được trả về theo hợp đồng V1 hoặc V2: V1 dùng trường customerName, còn V2 chuyển sang cấu trúc customer lồng nhau và bổ sung thông tin currency. Version qua media type cho phép client chọn hợp đồng representation bằng header HTTP, thay vì bắt buộc phải thay đổi đường dẫn tài nguyên.

Trong Spring MVC, content negotiation có thể chọn handler dựa trên media type mà client chấp nhận. Spring HATEOAS bổ sung yêu cầu về serializer: nếu media type phiên bản là vendor-specific nhưng body vẫn cần HAL, ứng dụng phải đăng ký cấu hình hypermedia tương ứng.

Sau bài học, bạn có thể:

- Giải thích version qua media type và phân biệt nó với version qua URI.
- Phân biệt Accept và Content-Type khi chọn phiên bản.
- Thiết kế vendor media type hoặc version parameter.
- Dùng produces và consumes để định tuyến tới representation phù hợp.
- Tổ chức DTO và assembler riêng cho từng phiên bản.
- Đăng ký custom hypermedia media type khi cần serialize HAL dưới vendor media type.
- Xử lý 406, 415, cache và kiểm thử hợp đồng phiên bản.

## Version qua media type là gì?

Media type mô tả định dạng và ngữ nghĩa của nội dung HTTP. Ví dụ:

~~~http
Content-Type: application/json
Accept: application/hal+json
~~~

Version qua media type dùng media type để nhận diện một phiên bản hợp đồng representation. Cùng một tài nguyên và URI có thể trả về nội dung khác nhau tùy media type client yêu cầu:

~~~http
GET /api/orders/42
Accept: application/vnd.acme.order-v1+json
~~~

hoặc:

~~~http
GET /api/orders/42
Accept: application/vnd.acme.order-v2+json
~~~

Server chọn representation tương ứng và trả media type thực tế trong Content-Type:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.acme.order-v2+json
Vary: Accept
~~~

URI /api/orders/42 vẫn định danh cùng một đơn hàng. Media type quyết định cấu trúc representation mà client nhận được. Vì vậy, version qua media type chủ yếu version hóa hợp đồng biểu diễn dữ liệu, không tạo một tài nguyên nghiệp vụ khác.

## Hai cách đưa version vào media type

Có hai quy ước thường gặp.

### Version trong vendor subtype

~~~text
application/vnd.acme.order-v1+json
application/vnd.acme.order-v2+json
~~~

Trong ví dụ:

- application là top-level type.
- vnd.acme.order-v1 là vendor-specific subtype.
- +json là structured syntax suffix, cho biết nội dung dùng cú pháp JSON.

Ưu điểm là mỗi phiên bản có một media type riêng, dễ nhận diện và định tuyến. Nhược điểm là nếu dùng Spring HATEOAS, media type vendor không tự động được xem là HAL chỉ vì nó kết thúc bằng +json.

### Version trong media type parameter

Một quy ước khác là giữ nguyên media type HAL và thêm parameter:

~~~text
application/hal+json;version=1
application/hal+json;version=2
~~~

Client gửi:

~~~http
Accept: application/hal+json;version=2
~~~

Cách này giữ nguyên subtype HAL và chỉ thay đổi parameter version. Tuy nhiên, tên parameter version và cách hiểu giá trị 1/2 là quy ước của API, không phải một chuẩn versioning chung áp dụng cho mọi media type.

| Tiêu chí | Vendor subtype | Version parameter |
|---|---|---|
| Ví dụ | application/vnd.acme.order-v2+json | application/hal+json;version=2 |
| Nhận diện phiên bản | Mỗi version có subtype riêng. | Cùng media type, khác parameter. |
| Tích hợp HAL | Cần đăng ký hỗ trợ vendor media type nếu muốn serializer HAL. | Có thể tận dụng HAL media type cơ sở; vẫn phải kiểm thử content negotiation và converter. |
| Độ rõ ràng | Media type thể hiện rõ tên sản phẩm và version. | Ngắn gọn, giữ nguyên định dạng HAL. |
| Rủi ro | Dễ nhầm +json với hỗ trợ HAL tự động. | Parameter version là quy ước riêng; wildcard hoặc Accept thiếu parameter cần chính sách mặc định rõ ràng. |

Chọn một quy ước cho toàn API và ghi rõ trong tài liệu client. Không trộn vendor subtype cho một số endpoint với version parameter cho endpoint khác nếu không có lý do tương thích cụ thể.

## Accept và Content-Type chọn hai chiều khác nhau

Hai header này thường bị nhầm khi version hóa API:

| Header | Hướng nội dung | Câu hỏi |
|---|---|---|
| Accept | Response từ server về client. | Client muốn nhận phiên bản representation nào? |
| Content-Type | Request body từ client lên server. | Client đang gửi payload theo phiên bản media type nào? |

Ví dụ client gửi payload V1 nhưng muốn nhận response V2:

~~~http
POST /api/orders
Content-Type: application/vnd.acme.order-v1+json
Accept: application/vnd.acme.order-v2+json
~~~

Server dùng Content-Type để chọn cách đọc request body, còn Accept để chọn cách tạo response. Hai phiên bản này không bắt buộc phải giống nhau, nhưng API phải định nghĩa rõ tổ hợp nào được hỗ trợ.

Với GET không có request body, Accept là header chính để chọn representation. Với POST, PUT hoặc PATCH có body, Content-Type và Accept có thể cùng tham gia định tuyến.

## Khai báo media type constants

Nên tập trung tên media type vào một lớp để controller, assembler và test dùng thống nhất:

~~~java
import org.springframework.http.MediaType;

public final class OrderMediaTypes {

    public static final String V1_VALUE =
            "application/vnd.acme.order-v1+json";

    public static final String V2_VALUE =
            "application/vnd.acme.order-v2+json";

    public static final MediaType V1 =
            MediaType.parseMediaType(V1_VALUE);

    public static final MediaType V2 =
            MediaType.parseMediaType(V2_VALUE);

    private OrderMediaTypes() {
    }
}
~~~

Đặt constants giúp tránh lỗi chính tả và cho phép test sử dụng cùng giá trị với controller. Nếu chọn cách version parameter, có thể khai báo các MediaType tương ứng như application/hal+json;version=1 và application/hal+json;version=2.

## Dùng produces để chọn representation version

Spring MVC hỗ trợ điều kiện produces trên handler mapping. Spring so khớp Accept của request với danh sách media type mà method có thể trả về. Hai handler cùng path và HTTP method có thể phân biệt bằng produces:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderV1Assembler v1Assembler;
    private final OrderV2Assembler v2Assembler;

    OrderController(
            OrderService orderService,
            OrderV1Assembler v1Assembler,
            OrderV2Assembler v2Assembler) {
        this.orderService = orderService;
        this.v1Assembler = v1Assembler;
        this.v2Assembler = v2Assembler;
    }

    @GetMapping(path = "/{id}", produces = OrderMediaTypes.V1_VALUE)
    EntityModel<OrderV1> findV1(@PathVariable UUID id) {
        return v1Assembler.toModel(orderService.findById(id));
    }

    @GetMapping(path = "/{id}", produces = OrderMediaTypes.V2_VALUE)
    EntityModel<OrderV2> findV2(@PathVariable UUID id) {
        return v2Assembler.toModel(orderService.findById(id));
    }
}
~~~

Khi client gửi Accept: application/vnd.acme.order-v1+json, Spring chọn findV1. Khi gửi Accept: application/vnd.acme.order-v2+json, Spring chọn findV2. Cùng một URI và HTTP method nhưng mỗi handler trả một kiểu representation khác.

Không nên tạo hai controller method trùng mapping mà không có produces khác nhau. Nếu các điều kiện mapping không phân biệt được request, Spring có thể báo ambiguous handler mapping.

## Dùng consumes để chọn phiên bản request body

Với endpoint nhận payload, consumes ràng buộc Content-Type:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
        path = "/api/orders",
        consumes = OrderMediaTypes.V1_VALUE,
        produces = OrderMediaTypes.V1_VALUE)
ResponseEntity<EntityModel<OrderV1>> createV1(
        @RequestBody CreateOrderV1 request) {

    Order order = orderService.create(CreateOrderV1.toCommand(request));
    return ResponseEntity.ok(v1Assembler.toModel(order));
}

@PostMapping(
        path = "/api/orders",
        consumes = OrderMediaTypes.V2_VALUE,
        produces = OrderMediaTypes.V2_VALUE)
ResponseEntity<EntityModel<OrderV2>> createV2(
        @RequestBody CreateOrderV2 request) {

    Order order = orderService.create(CreateOrderV2.toCommand(request));
    return ResponseEntity.ok(v2Assembler.toModel(order));
}
~~~

consumes chọn handler theo Content-Type của request. produces chọn media type response theo Accept. Khi client gửi media type không được hỗ trợ, Spring MVC có thể trả 415 Unsupported Media Type cho request body hoặc 406 Not Acceptable khi không có representation phù hợp với Accept.

Ví dụ trên minh họa hai hợp đồng request/response tương ứng. Ứng dụng có thể hỗ trợ các tổ hợp khác, chẳng hạn nhận V1 nhưng trả V2; khi đó cần khai báo mapping và quy tắc chuyển đổi riêng thay vì giả định version request và response luôn giống nhau.

## Tách representation và assembler theo phiên bản

Không nên thay đổi cùng một DTO theo version bằng các nhánh điều kiện rải rác. Tạo representation riêng cho mỗi hợp đồng giúp kiểm soát trường dữ liệu và links:

~~~java
public record OrderV1(
        UUID id,
        String customerName,
        BigDecimal total) {
}

public record OrderV2(
        UUID id,
        CustomerSummary customer,
        Money total,
        String fulfillmentStatus) {
}
~~~

V1 trả customerName dạng chuỗi. V2 trả CustomerSummary có cấu trúc riêng, dùng Money để biểu diễn số tiền và thêm fulfillmentStatus. Domain model vẫn có thể là một Order duy nhất; assembler chịu trách nhiệm ánh xạ domain sang representation version tương ứng.

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderV2Assembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderV2>> {

    @Override
    public EntityModel<OrderV2> toModel(Order order) {
        OrderV2 body = new OrderV2(
                order.getId(),
                CustomerSummary.from(order.getCustomer()),
                Money.of(order.getTotal(), order.getCurrency()),
                order.getFulfillmentStatus().name());

        return EntityModel.of(body,
                linkTo(methodOn(OrderController.class)
                        .findV2(order.getId())).withSelfRel());
    }
}
~~~

Các link relation nên giữ ngữ nghĩa nhất quán giữa các version nếu hành động vẫn có cùng ý nghĩa. Client V1 và V2 có thể đọc cùng relation self, customer hoặc cancel, dù trường dữ liệu và URI chi tiết có thể khác. Không đổi relation chỉ vì tên DTO hoặc tên controller method thay đổi.

Nếu affordance được công bố, mỗi version cần mô tả input model và thao tác tương ứng với hợp đồng version đó. Không để V1 quảng bá một affordance nhưng endpoint lại chỉ chấp nhận payload V2.

## Lưu ý quan trọng khi dùng Spring HATEOAS với vendor media type

Tên media type application/vnd.acme.order-v2+json cho biết nội dung dùng cú pháp JSON. Structured syntax suffix +json không có nghĩa Spring HATEOAS sẽ tự serialize EntityModel thành HAL.

Spring HATEOAS mặc định có mapping cho các media type hypermedia được hỗ trợ, chẳng hạn application/hal+json. Nếu controller trả RepresentationModel dưới một vendor media type riêng, cần đăng ký custom hypermedia mapping phù hợp.

Spring HATEOAS cung cấp SPI HypermediaMappingInformation. Một implementation custom thường cần:

1. Trả về danh sách media type mà mapping hỗ trợ qua getMediaTypes().
2. Cung cấp Jackson module hoặc cấu hình JSON mapper để serialize/deserialize RepresentationModel, EntityModel, CollectionModel và PagedModel theo cấu trúc hypermedia mong muốn.
3. Đăng ký LinkDiscoverer bean nếu client-side link discovery cần nhận diện link trong định dạng đó.
4. Đăng ký implementation như Spring bean để Spring HATEOAS phát hiện và cấu hình converter.

Đây là công việc định nghĩa một hypermedia media type thực sự. Chỉ thêm produces = "application/vnd.acme.order-v2+json" hoặc dùng Jackson converter mặc định không đủ để đảm bảo các trường _links và _embedded được serialize theo HAL.

Nếu mục tiêu chỉ là version hóa JSON DTO không dùng HAL, Jackson JSON converter thông thường có thể xử lý vendor media type có hậu tố +json. Nếu mục tiêu là version hóa representation HATEOAS, phải kiểm tra message converter và hypermedia mapping được chọn trong runtime.

Một lựa chọn đơn giản hơn là dùng application/hal+json;version=1 và application/hal+json;version=2, giữ HAL làm media type gốc. Dù vậy, cần kiểm thử mapping produces, Content-Type thực tế và converter trong ứng dụng, đặc biệt khi có nhiều version cùng media type cơ sở.

## Link và URI khi version hóa qua media type

Version qua media type không bắt buộc version phải xuất hiện trong href. Ví dụ V1 và V2 có thể cùng trả:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "collection": {
      "href": "/api/orders"
    }
  }
}
~~~

Client tiếp tục theo link và gửi Accept tương ứng để nhận representation version mong muốn. Không nên tự thêm /v1 hoặc /v2 vào href nếu API đã chọn media type làm cơ chế versioning; điều đó sẽ trộn hai chiến lược và làm client khó dự đoán.

Nếu hai version có khả năng tương tác khác nhau, server có thể công bố affordances hoặc links phù hợp trong từng representation. Relation vẫn nên phản ánh ý nghĩa nghiệp vụ, còn media type xác định cấu trúc representation.

## Content negotiation và chính sách mặc định

Client có thể gửi một hoặc nhiều media type trong Accept, kèm quality value q để biểu thị mức ưu tiên:

~~~http
Accept: application/vnd.acme.order-v2+json;q=1.0, application/vnd.acme.order-v1+json;q=0.8
~~~

Spring MVC dùng content negotiation để chọn handler phù hợp với media type được chấp nhận. Nếu client không gửi Accept rõ ràng hoặc gửi */*, API cần có chính sách mặc định:

- Chọn một version mặc định và công bố rõ trong tài liệu.
- Hoặc yêu cầu client chỉ định version, từ chối request không xác định được version.
- Không để nhiều handler cùng khớp wildcard mà không có quy tắc ưu tiên rõ ràng.

Với version parameter, cần chú ý quy tắc matching của Spring: nếu media type trong mapping có parameter nhưng media type client gửi không có parameter đó, parameter có thể được bỏ qua khi matching. Vì vậy, nếu version parameter là bắt buộc, hãy kiểm thử trường hợp Accept thiếu parameter và bổ sung chính sách mặc định hoặc validation phù hợp để tránh chọn version ngoài ý muốn.

Khi không có representation nào phù hợp với Accept, trả 406 Not Acceptable. Khi Content-Type của request body không được endpoint chấp nhận, trả 415 Unsupported Media Type. Không âm thầm trả một version khác với version client đã yêu cầu.

## Cache và Vary: Accept

Khi cùng một URI trả nhiều representation tùy theo Accept, cache phải phân biệt response theo header này. Response nên có:

~~~http
Vary: Accept
~~~

Header Vary cho cache biết rằng nội dung response phụ thuộc vào Accept. Nếu representation còn phụ thuộc Accept-Language, có thể cần Vary: Accept, Accept-Language. Hãy xác minh cấu hình cache, reverse proxy và CDN tôn trọng Vary; nếu không, client có thể nhận nhầm representation V1 từ cache khi đang yêu cầu V2.

ETag cũng cần được tính theo representation thực tế. Cùng một tài nguyên nhưng body V1 và V2 khác nhau thì validator không nên khiến cache coi hai representation là cùng một nội dung nếu chúng không tương đương.

Ví dụ với ResponseEntity:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

return ResponseEntity.ok()
        .contentType(OrderMediaTypes.V2)
        .varyBy(HttpHeaders.ACCEPT)
        .body(v2Assembler.toModel(order));
~~~

Khi handler đã khai báo produces tương ứng, Spring MVC chọn media type theo content negotiation. Việc đặt Content-Type tường minh trong ví dụ giúp minh họa response version và có thể hữu ích khi xây response qua ResponseEntity; giá trị phải khớp với media type đã thương lượng.

## Vòng đời phiên bản

Versioning không chỉ là thêm một handler. API cần chính sách duy trì và kết thúc hỗ trợ version:

1. Xác định thay đổi nào là breaking change và cần version mới.
2. Giữ representation cũ ổn định trong thời gian client chuyển đổi.
3. Công bố version mới và tài liệu migration.
4. Theo dõi mức sử dụng version cũ trước khi lên lịch ngừng hỗ trợ.
5. Thông báo deprecation và sunset theo chính sách của API.
6. Xóa handler, assembler và media type cũ khi đã kết thúc thời gian hỗ trợ.

Không tạo version mới chỉ vì thêm một trường optional có thể tương thích ngược. Ngược lại, đổi ý nghĩa trường, xóa trường bắt buộc hoặc thay đổi cấu trúc payload thường là thay đổi cần đánh giá version mới.

Không duy trì vô hạn nhiều representation nếu không có client sử dụng. Mỗi version làm tăng chi phí kiểm thử, tài liệu, cache và bảo trì.

## Kiểm thử version qua media type

MockMvc có thể xác minh cùng URI trả về representation khác nhau theo Accept:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(OrderMediaTypes.V1))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(OrderMediaTypes.V1))
        .andExpect(jsonPath("$.customerName").exists());

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(OrderMediaTypes.V2))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(OrderMediaTypes.V2))
        .andExpect(jsonPath("$.customer.name").exists())
        .andExpect(jsonPath("$.fulfillmentStatus").exists());
~~~

Nếu body là HAL, kiểm tra thêm link structure:

~~~java
mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(OrderMediaTypes.V2))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.collection.href").exists());
~~~

Kiểm thử media type không được hỗ trợ:

~~~java
mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept("application/vnd.acme.order-v3+json"))
        .andExpect(status().isNotAcceptable());
~~~

Với POST hoặc PUT, kiểm thử Content-Type không được hỗ trợ:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

mockMvc.perform(post("/api/orders")
                .contentType("application/vnd.acme.order-v3+json")
                .accept(OrderMediaTypes.V2)
                .content("{}"))
        .andExpect(status().isUnsupportedMediaType());
~~~

Các test nên xác minh:

- Accept V1 chọn đúng handler và Content-Type V1.
- Accept V2 chọn đúng handler và Content-Type V2.
- Cùng resource URI vẫn giữ link relation đúng.
- Vendor media type được serialize đúng cấu trúc hypermedia nếu dùng HAL.
- Content-Type request chọn đúng input model.
- Accept version không hỗ trợ trả 406.
- Content-Type không hỗ trợ trả 415.
- Accept thiếu version hoặc wildcard tuân theo chính sách mặc định.
- Response có Vary: Accept và cache phân biệt các representation.

## Những lỗi thường gặp

- **Nhầm Accept với Content-Type:** Accept chọn response; Content-Type mô tả request body.
- **Cho rằng +json đồng nghĩa HAL:** hậu tố +json chỉ biểu thị cú pháp JSON. Cần hypermedia mapping để serialize HATEOAS đúng định dạng.
- **Chỉ đổi produces nhưng dùng chung một DTO:** hai handler có thể chọn đúng nhưng representation vẫn không khác theo hợp đồng. Dùng DTO và assembler phù hợp từng version.
- **Để link thay đổi không cần thiết giữa các version:** giữ relation ổn định khi ngữ nghĩa không đổi để client tái sử dụng logic điều hướng.
- **Không xử lý wildcard Accept:** nhiều handler có thể cùng khớp; xác định default version hoặc yêu cầu client chỉ định.
- **Coi version parameter là chuẩn chung:** tên version và giá trị version là quy ước API; phải ghi tài liệu và kiểm thử matching.
- **Trả version khác khi client yêu cầu version không hỗ trợ:** trả 406 thay vì âm thầm fallback sai hợp đồng.
- **Không cấu hình Vary: Accept:** cache có thể trả nhầm representation của version khác.
- **Không kiểm thử converter:** mapping có thể chọn đúng handler nhưng serializer không hỗ trợ vendor hypermedia media type.
- **Tạo version mới cho mọi thay đổi nhỏ:** chỉ version hóa khi cần thay đổi hợp đồng có tính phá vỡ tương thích.

## Quy trình triển khai version qua media type

1. Xác định breaking changes và hợp đồng representation cho từng version.
2. Chọn vendor subtype hoặc version parameter; định nghĩa MediaType constants tập trung.
3. Tạo DTO và RepresentationModelAssembler riêng cho từng version cần hỗ trợ.
4. Dùng produces để chọn response version theo Accept.
5. Dùng consumes để chọn request body version theo Content-Type.
6. Nếu dùng vendor media type cho HAL, đăng ký HypermediaMappingInformation, Jackson module và LinkDiscoverer phù hợp.
7. Quy định version mặc định, hành vi 406/415, cache Vary và chính sách deprecation.
8. Kiểm thử handler selection, Content-Type, representation fields, links và custom hypermedia converter.

Version qua media type cho phép API giữ URI tài nguyên ổn định trong khi cung cấp nhiều hợp đồng representation. Khi Spring MVC định tuyến bằng produces/consumes và Spring HATEOAS serialize đúng hypermedia media type, client có thể chọn version qua header HTTP và tiếp tục điều hướng bằng các links do server công bố.

## Tài liệu tham khảo

- Spring Framework Reference, Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring HATEOAS Reference, Registering a custom media type: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.custom
- Spring HATEOAS API, HypermediaMappingInformation: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/config/HypermediaMappingInformation.html
- RFC 6838, Media Type Specifications and Registration Procedures: https://www.rfc-editor.org/rfc/rfc6838
- RFC 6839, Additional Media Type Structured Syntax Suffixes: https://www.rfc-editor.org/rfc/rfc6839
