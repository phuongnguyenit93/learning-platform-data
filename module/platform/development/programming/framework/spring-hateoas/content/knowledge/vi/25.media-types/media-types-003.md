# Accept header

Trong HTTP, header **Accept** cho server biết client có thể xử lý những media type nào cho response và mức ưu tiên tương ứng. Với Spring HATEOAS, client có thể dùng header này để yêu cầu representation HAL JSON (application/hal+json) hoặc HAL-FORMS (application/prs.hal-forms+json). Spring MVC/WebFlux kết hợp mapping của controller, content negotiation và message converter để chọn định dạng response phù hợp.

Accept chỉ mô tả định dạng client muốn nhận. Nó không tự biến một DTO thông thường thành hypermedia. Để response có _links, _embedded hoặc _templates, ứng dụng cần trả representation model phù hợp và bật cấu hình serializer cho media type tương ứng.

## Accept và Content-Type khác nhau thế nào?

Hai header thường xuất hiện cùng nhau nhưng có nhiệm vụ khác nhau:

| Header | Hướng áp dụng | Ý nghĩa |
| --- | --- | --- |
| Accept | Request → Response | Client yêu cầu server trả về một hoặc nhiều media type có thể xử lý |
| Content-Type | Request body hoặc Response body | Mô tả định dạng nội dung đang được gửi |

Ví dụ client gửi JSON để tạo đơn hàng và muốn nhận HAL JSON:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": "6d2b8e4a-2a10-4d10-a5d3-9b9f5e3a2002",
  "deliveryAddress": "12 Nguyen Hue"
}
~~~

Content-Type: application/json mô tả request body. Accept: application/hal+json yêu cầu response ở dạng HAL JSON. Nếu tạo tài nguyên thành công, server có thể trả 201 Created, header Location và body HAL chứa _links.self.

Nếu request body gửi XML nhưng endpoint chỉ nhận JSON, server có thể trả 415 Unsupported Media Type. Nếu request có Accept: application/xml trong khi endpoint chỉ tạo được HAL JSON, server có thể trả 406 Not Acceptable. Hai lỗi này liên quan tới hai chiều thương lượng khác nhau.

## Cú pháp Accept và q-value

Accept có thể chứa một hoặc nhiều media range, phân tách bằng dấu phẩy. Mỗi lựa chọn có thể kèm tham số q để chỉ mức ưu tiên từ 0 đến 1. Giá trị mặc định của q là 1; q càng cao thì client càng ưu tiên media type đó. q=0 nghĩa là client không chấp nhận media type tương ứng.

Ví dụ:

~~~http
Accept: application/prs.hal-forms+json;q=1.0, application/hal+json;q=0.8, application/json;q=0.5
~~~

Client ưu tiên HAL-FORMS, sau đó HAL JSON, cuối cùng mới tới JSON thông thường. Server chỉ được chọn một representation mà endpoint và message converter thực sự hỗ trợ; q-value không thể làm một định dạng chưa được cấu hình trở nên khả dụng.

Một số dạng media range thường gặp:

| Accept value | Ý nghĩa |
| --- | --- |
| application/hal+json | Chấp nhận HAL JSON |
| application/prs.hal-forms+json | Chấp nhận HAL-FORMS JSON |
| application/json | Chấp nhận JSON thông thường |
| application/* | Chấp nhận các media type thuộc nhóm application |
| */* | Chấp nhận mọi media type |

application/json và application/hal+json là hai media type khác nhau dù cùng dùng cú pháp JSON. Spring Boot mặc định cấu hình Spring HATEOAS để request Accept: application/json nhận HAL JSON; nếu tắt hành vi đó hoặc dùng cấu hình khác, client cần cấu trúc HAL nên yêu cầu application/hal+json thay vì giả định application/json sẽ nhận được _links và _embedded.

Client có thể gửi nhiều loại cụ thể cùng lúc để khai báo fallback. Với wildcard, server vẫn cần chọn một định dạng có converter phù hợp. Không nên dựa vào */* để giả định server sẽ luôn trả HAL; hãy gửi media type cụ thể khi client phụ thuộc vào cấu trúc hypermedia.

Nếu Accept bị bỏ qua trong request, HTTP xem như client không đặt giới hạn media type và có thể chấp nhận mọi định dạng. Định dạng thực tế vẫn phụ thuộc mapping, cấu hình content negotiation và thứ tự ưu tiên của server.

## Media type thường dùng trong Spring HATEOAS

Spring HATEOAS định nghĩa các hằng media type trong package org.springframework.hateoas.MediaTypes. Những giá trị quan trọng:

| Hằng Spring HATEOAS | Media type | Cách dùng |
| --- | --- | --- |
| MediaTypes.HAL_JSON | application/hal+json | Representation HAL JSON với _links và _embedded |
| MediaTypes.HAL_FORMS_JSON | application/prs.hal-forms+json | HAL mở rộng với _templates mô tả affordance/form |
| MediaTypes.ALPS_JSON | application/alps+json | Mô tả semantic profile bằng ALPS |
| MediaTypes.COLLECTION_JSON | application/vnd.collection+json | Định dạng Collection+JSON khi ứng dụng bật hỗ trợ |
| MediaTypes.UBER_JSON | application/vnd.amundsen-uber+json | Định dạng UBER khi ứng dụng bật hỗ trợ |

Không phải mọi ứng dụng đều cần tất cả định dạng này. Chọn media type theo hợp đồng API và khả năng của client. Một API chỉ dùng HAL có thể chỉ công bố application/hal+json; API cần client khám phá biểu mẫu tương tác có thể công bố thêm HAL-FORMS.

Có thể dùng hằng MediaTypes.HAL_JSON_VALUE và MediaTypes.HAL_FORMS_JSON_VALUE trong thuộc tính annotation produces, nơi yêu cầu chuỗi media type. Trong code cần đối chiếu hoặc truyền một MediaType, dùng hằng không có hậu tố _VALUE.

Lưu ý riêng với Spring Boot: theo cấu hình mặc định của Spring HATEOAS auto-configuration, request có Accept: application/json được trả về application/hal+json. Có thể tắt hành vi này bằng thuộc tính spring.hateoas.use-hal-as-default-json-media-type=false. Vì vậy application/json và application/hal+json vẫn là hai media type khác nhau theo HTTP, nhưng kết quả thực tế của application/json còn phụ thuộc cấu hình Spring Boot. Nếu client yêu cầu hợp đồng HAL một cách tường minh, application/hal+json vẫn là lựa chọn rõ ràng nhất.

## Spring thực hiện content negotiation như thế nào?

Khi nhận request, Spring xử lý việc chọn representation qua một chuỗi bước tổng quát:

1. Đọc Accept từ request.
2. Xác định các media type mà mapping controller có thể sản xuất, ví dụ thuộc tính produces.
3. Tìm message converter có thể ghi kiểu return value sang media type được chấp nhận.
4. Chọn định dạng phù hợp theo media range, mức ưu tiên và khả năng converter.
5. Ghi response body và Content-Type tương ứng.

Với Spring HATEOAS, HAL message converter biết cách serialize RepresentationModel, EntityModel, CollectionModel và PagedModel thành cấu trúc HAL. HAL-FORMS converter có thể biểu diễn thêm affordance dưới _templates khi representation có metadata tương tác phù hợp.

Content negotiation không tự tạo link hoặc affordance. Nếu controller trả DTO thường, chỉ gửi Accept: application/hal+json không đủ để có _links. Controller hoặc assembler phải trả hypermedia model và gắn link cần thiết.

## Khai báo produces trên controller

Thuộc tính produces giới hạn media type mà endpoint công bố có thể trả về. Ví dụ endpoint đơn hàng hỗ trợ cả HAL JSON và HAL-FORMS:

~~~java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(
        value = "/{id}",
        produces = {
            MediaTypes.HAL_JSON_VALUE,
            MediaTypes.HAL_FORMS_JSON_VALUE
        }
    )
    EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        return assembler.toModel(orderService.findById(id));
    }
}
~~~

Ví dụ giả định assembler tạo EntityModel<OrderRepresentation> và gắn self link. Khi client gửi Accept: application/hal+json, server chọn HAL JSON; khi client gửi Accept: application/prs.hal-forms+json, server có thể chọn HAL-FORMS nếu ứng dụng đã cấu hình converter tương ứng và model có affordance cần biểu diễn.

Nếu endpoint chỉ khai báo produces = MediaTypes.HAL_JSON_VALUE, request yêu cầu HAL-FORMS không khớp mapping đó và có thể nhận 406 Not Acceptable. Hãy liệt kê rõ những media type thực sự được hỗ trợ. Không thêm một media type vào produces nếu ứng dụng không có message converter có thể ghi kiểu return value sang định dạng đó.

## Bật hỗ trợ HAL và HAL-FORMS

Với Spring Boot và Spring MVC, spring-boot-starter-hateoas cung cấp tích hợp Spring HATEOAS và auto-configuration cho các thành phần hypermedia phổ biến. Starter này dành cho Spring MVC và không nên kết hợp với Spring WebFlux. Với WebFlux, dùng spring-boot-starter-webflux cùng dependency org.springframework.hateoas:spring-hateoas trực tiếp. Kiểm tra phiên bản Spring Boot và cấu hình hiện có trước khi tự đăng ký message converter.

Trong cấu hình Spring không dùng auto-configuration, có thể bật hỗ trợ hypermedia bằng @EnableHypermediaSupport:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = {
    HypermediaType.HAL,
    HypermediaType.HAL_FORMS
})
class HypermediaConfiguration {
}
~~~

Nếu ứng dụng chỉ dùng HAL JSON, có thể chỉ bật HypermediaType.HAL. Khi muốn HAL-FORMS, bật loại tương ứng và bảo đảm affordance được gắn vào link. Cấu hình cụ thể có thể khác giữa Spring HATEOAS và Spring Boot versions; tránh kết hợp nhiều cấu hình converter trùng nhau.

## Yêu cầu HAL JSON bằng Accept

Client yêu cầu HAL JSON:

~~~http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
~~~

Ví dụ gọi bằng curl:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/orders/42
~~~

Response có thể có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json

{
  "id": "a7c1f4d2-55a1-4e51-93a2-88a12d1e1001",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/a7c1f4d2-55a1-4e51-93a2-88a12d1e1001"
    }
  }
}
~~~

Content-Type trong response cho biết server thực sự đã chọn HAL JSON. Client nên kiểm tra header này khi phụ thuộc vào _links hoặc _embedded, thay vì chỉ dựa vào việc body có cú pháp JSON.

## Yêu cầu HAL-FORMS bằng Accept

Client cần khám phá form và affordance có thể yêu cầu:

~~~http
GET /orders HTTP/1.1
Accept: application/prs.hal-forms+json
~~~

Nếu response có link gắn affordance POST tạo đơn hàng, HAL-FORMS có thể biểu diễn template trong _templates:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders"
    }
  },
  "_templates": {
    "create": {
      "method": "post",
      "contentType": "application/json",
      "properties": [
        {
          "name": "customerId",
          "required": true
        },
        {
          "name": "note"
        }
      ]
    }
  }
}
~~~

Accept chỉ yêu cầu định dạng HAL-FORMS. _templates chỉ xuất hiện khi model có affordance được công bố và cấu hình serialization hỗ trợ. Nếu không có affordance, response có thể vẫn là HAL-FORMS nhưng không có template tương tác.

## Fallback và thứ tự ưu tiên

Client có thể yêu cầu nhiều media type để hỗ trợ server với khả năng khác nhau:

~~~http
Accept: application/prs.hal-forms+json;q=1.0, application/hal+json;q=0.9
~~~

Nếu server hỗ trợ HAL-FORMS, client ưu tiên định dạng đó. Nếu endpoint chỉ sản xuất HAL JSON, server có thể chọn HAL JSON vì nó vẫn nằm trong danh sách chấp nhận. Nếu không có định dạng nào khớp, server trả lỗi 406.

Không nên giả định mọi server luôn chọn media type có q cao nhất bất kể cấu hình. Mapping, converter và quy tắc content negotiation của ứng dụng vẫn giới hạn lựa chọn. Hãy kiểm thử các tổ hợp Accept mà client thực sự gửi.

Một số trường hợp:

| Request Accept | Endpoint hỗ trợ | Kết quả mong đợi |
| --- | --- | --- |
| application/hal+json | HAL JSON | Trả HAL JSON |
| application/prs.hal-forms+json | HAL-FORMS | Trả HAL-FORMS |
| HAL-FORMS ưu tiên, HAL JSON fallback | Chỉ HAL JSON | Có thể chọn HAL JSON |
| application/xml | Chỉ HAL JSON và HAL-FORMS | 406 Not Acceptable |
| */* | Nhiều định dạng | Server chọn định dạng mặc định/phù hợp theo cấu hình |

## 406 Not Acceptable và 415 Unsupported Media Type

Hai lỗi này thường bị nhầm khi debug:

- **406 Not Acceptable:** client yêu cầu response media type mà endpoint/converter không thể cung cấp. Kiểm tra Accept, produces và message converter.
- **415 Unsupported Media Type:** request body dùng media type mà endpoint không nhận. Kiểm tra Content-Type và thuộc tính consumes.

Ví dụ endpoint POST chỉ nhận JSON và trả HAL JSON:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.net.URI;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaTypes.HAL_JSON_VALUE
)
ResponseEntity<EntityModel<OrderRepresentation>> create(
        @RequestBody CreateOrderRequest request) {
    Order created = orderService.create(request);
    EntityModel<OrderRepresentation> body = assembler.toModel(created);
    URI location = linkTo(methodOn(OrderController.class)
        .one(created.getId())).toUri();
    return ResponseEntity.created(location).body(body);
}
~~~

Nếu client gửi XML body, server có thể trả 415 vì consumes chỉ cho phép JSON. Nếu client gửi JSON body nhưng đặt Accept: application/xml, server có thể trả 406 vì response XML không được endpoint công bố.

## Kiểm thử Accept header bằng MockMvc

MockMvc có thể xác nhận Spring chọn đúng representation và Content-Type:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderMediaTypeTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsHalJsonWhenRequested() throws Exception {
        mockMvc.perform(get("/orders/{id}", EXISTING_ORDER_ID)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

EXISTING_ORDER_ID là ID fixture đã được nạp trong test. Test này xác nhận response là HAL JSON và có self link. Có thể viết test tương tự với MediaTypes.HAL_FORMS_JSON, rồi kiểm tra Content-Type và _templates khi controller công bố affordance.

Kiểm tra trường hợp Accept không được hỗ trợ:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(get("/orders/{id}", EXISTING_ORDER_ID)
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isNotAcceptable());
~~~

Đoạn test giả định endpoint chỉ công bố HAL JSON và HAL-FORMS, không có converter XML. Nếu ứng dụng hỗ trợ thêm XML hoặc wildcard mapping, kết quả sẽ phụ thuộc cấu hình thực tế.

## Kiểm thử bằng WebTestClient cho WebFlux

Với controller WebFlux, dùng WebTestClient để xác nhận negotiation trên reactive stack:

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveOrderMediaTypeTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void returnsHalWhenRequested() {
        webTestClient.get()
            .uri("/orders/{id}", EXISTING_ORDER_ID)
            .accept(MediaTypes.HAL_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaTypes.HAL_JSON)
            .expectBody()
                .jsonPath("$._links.self.href").exists();
    }
}
~~~

Ví dụ giả định test fixture có đơn hàng tương ứng và ứng dụng đã cấu hình HAL cho WebFlux. Dùng MockMvc cho Spring MVC và WebTestClient cho WebFlux để test đi qua đúng hạ tầng của ứng dụng.

## Accept, cache và Vary header

Nếu cùng một URI có thể trả HAL JSON hoặc HAL-FORMS tùy Accept, cache trung gian cần biết response phụ thuộc vào request header nào. Header **Vary: Accept** thông báo rằng representation được chọn có thể thay đổi theo Accept. Nếu cache không phân biệt Accept, client có thể nhận nhầm định dạng đã được cache từ request trước.

Kiểm tra cấu hình cache/CDN và response header của ứng dụng. Nếu endpoint thương lượng nhiều định dạng, bảo đảm cache key hoặc Vary header phản ánh Accept. Không cache một representation HAL-FORMS rồi trả cho client chỉ chấp nhận HAL JSON.

## Nguyên tắc thiết kế media type

- **Công bố đúng định dạng hỗ trợ:** produces phải khớp converter và representation thực tế.
- **Dùng Accept cụ thể:** client phụ thuộc hypermedia nên yêu cầu media type HAL/HAL-FORMS rõ ràng.
- **Phân biệt request và response:** dùng Content-Type cho body gửi lên, Accept cho response mong muốn.
- **Giữ semantics của representation:** HAL JSON cho link/embedded; HAL-FORMS thêm template tương tác khi có affordance.
- **Không dựa vào wildcard khi cần cấu trúc cụ thể:** */* cho server quyền chọn định dạng.
- **Kiểm thử fallback và lỗi:** bao gồm q-value, media type không hỗ trợ, 406 và 415.
- **Bảo vệ cache:** dùng Vary: Accept khi response thay đổi theo Accept.
- **Không coi media type là versioning duy nhất:** nếu cấu trúc hợp đồng thay đổi không tương thích, cần chiến lược versioning và tương thích riêng.

Accept header là đầu vào quan trọng của content negotiation trong Spring HATEOAS. Khi client yêu cầu đúng media type, controller khai báo produces rõ ràng, ứng dụng cấu hình converter tương ứng và test xác nhận Content-Type cùng cấu trúc HAL, các bên có thể trao đổi representation phù hợp mà không nhầm lẫn giữa JSON thông thường, HAL JSON và HAL-FORMS.

## Tài liệu tham khảo

- [Spring HATEOAS – Media types](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [Spring Boot – Spring HATEOAS auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [Spring Framework – HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [RFC 9110 – Accept](https://www.rfc-editor.org/rfc/rfc9110.html#name-accept)
- [Spring HATEOAS – MediaTypes API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
