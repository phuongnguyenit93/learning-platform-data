# Content negotiation

## Mục tiêu

Sau bài này, bạn có thể giải thích content negotiation trong HTTP, phân biệt vai trò của header `Accept` và `Content-Type`, cấu hình endpoint Spring HATEOAS hỗ trợ nhiều media type hypermedia, chọn giữa HAL và HAL-FORMS, xử lý các lỗi 406/415 và kiểm thử kết quả thương lượng nội dung bằng MockMvc.

## 1. Content negotiation là gì?

Một tài nguyên có thể được biểu diễn theo nhiều định dạng. Cùng một đơn hàng có thể được trả về dưới dạng JSON thông thường, HAL hoặc HAL-FORMS. Dữ liệu nghiệp vụ có thể giống nhau, nhưng mỗi media type cung cấp một cấu trúc và khả năng hypermedia khác nhau.

**Content negotiation** là quá trình client và server thống nhất định dạng representation được trao đổi. Trong HTTP, hai header quan trọng là:

- `Accept`: client cho biết những media type mà nó có thể nhận.
- `Content-Type`: bên gửi cho biết định dạng của phần body đang gửi.

Ví dụ client yêu cầu HAL:

```http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
```

Server có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

Nếu client gửi dữ liệu JSON để cập nhật đơn hàng:

```http
PUT /orders/42 HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "note": "Giao sau 17 giờ"
}
```

Ở request này, `Content-Type` mô tả body JSON mà server nhận; `Accept` mô tả response mà client muốn nhận. Hai header có thể mang media type khác nhau vì chúng điều khiển hai chiều trao đổi khác nhau.

## 2. Media type và representation hypermedia

Media type xác định định dạng và semantics của representation. Một số media type thường gặp khi xây API với Spring HATEOAS:

| Media type | Mục đích |
|---|---|
| `application/hal+json` | JSON theo HAL, có `_links` và có thể có `_embedded` |
| `application/prs.hal-forms+json` | HAL-FORMS, bổ sung template tương tác trong `_templates` |
| `application/json` | JSON thông thường, không tự mang semantics HAL |
| `application/problem+json` | Biểu diễn lỗi theo Problem Details nếu ứng dụng cấu hình hỗ trợ |

HAL và HAL-FORMS đều có thể biểu diễn dữ liệu cùng link hypermedia, nhưng khả năng mô tả tương tác khác nhau:

- HAL tập trung vào relation và URI trong `_links`, cùng tài nguyên nhúng trong `_embedded`.
- HAL-FORMS có thể công bố template trong `_templates`, gồm method, target, content type và các trường đầu vào.
- JSON thông thường chỉ xác định cấu trúc JSON; client không thể mặc định có semantics relation hoặc affordance của HAL.

Ví dụ HAL:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "collection": {
      "href": "/orders"
    }
  }
}
```

Ví dụ HAL-FORMS có thể bổ sung template cập nhật:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "update": {
      "method": "put",
      "contentType": "application/json",
      "properties": [
        {
          "name": "note",
          "required": false
        }
      ]
    }
  }
}
```

Client cần chọn media type dựa trên khả năng xử lý của nó. Nếu client cần đọc template để dựng form, nó nên yêu cầu HAL-FORMS; nếu chỉ cần theo link và đọc tài nguyên nhúng, HAL có thể đã đủ.

## 3. Spring HATEOAS và media type

Spring HATEOAS cung cấp các media type và message converter để tuần tự hóa representation model thành định dạng hypermedia tương ứng. Ví dụ, `EntityModel`, `CollectionModel` và các lớp kế thừa `RepresentationModel` có thể được tuần tự hóa thành HAL khi request thương lượng `application/hal+json`.

Các hằng số thường dùng nằm trong `MediaTypes`:

```java
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;

MediaType hal = MediaTypes.HAL_JSON;
MediaType halForms = MediaTypes.HAL_FORMS_JSON;
```

Trong Spring MVC, content negotiation phối hợp với các `HttpMessageConverter` đã đăng ký. Converter phù hợp sẽ đọc request body hoặc ghi response body theo media type được chọn.

Một controller trả `EntityModel<OrderView>` không tự quyết định duy nhất định dạng response. Định dạng còn phụ thuộc vào:

1. Media type mà client gửi trong `Accept`.
2. Media type mà mapping cho phép qua thuộc tính `produces`.
3. Các converter và cấu hình hypermedia đang hoạt động.
4. Kiểu đối tượng mà controller trả về và khả năng tuần tự hóa của converter.

Vì vậy, hãy kiểm tra response thực tế qua HTTP thay vì chỉ nhìn kiểu trả về Java.

## 4. Khai báo endpoint hỗ trợ HAL và HAL-FORMS

Một endpoint có thể công bố nhiều media type trong thuộc tính `produces`. Spring MVC dùng danh sách này để tham gia chọn representation:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping(
        value = "/{id}",
        produces = {
            "application/hal+json",
            "application/prs.hal-forms+json"
        }
    )
    public EntityModel<OrderView> getOrder(@PathVariable UUID id) {
        return assembler.toModel(orderService.getRequired(id));
    }

    @PutMapping(
        value = "/{id}",
        consumes = "application/json",
        produces = {
            "application/hal+json",
            "application/prs.hal-forms+json"
        }
    )
    public EntityModel<OrderView> updateOrder(
            @PathVariable UUID id,
            @Valid @RequestBody OrderUpdate input) {
        return assembler.toModel(orderService.update(id, input));
    }
}
```

Với cấu hình này:

- Client yêu cầu `application/hal+json` thì server trả HAL nếu converter tương ứng được cấu hình.
- Client yêu cầu `application/prs.hal-forms+json` thì server có thể trả HAL-FORMS.
- Request cập nhật phải gửi body có `Content-Type: application/json`, vì mapping khai báo `consumes`.
- Response của request cập nhật vẫn được thương lượng độc lập qua `Accept`.

Không phải cứ khai báo chuỗi media type trong `produces` là mọi converter đã sẵn sàng. Ứng dụng phải có cấu hình Spring HATEOAS tương ứng và các converter cần thiết. Trong ứng dụng Spring Boot sử dụng starter HATEOAS, cấu hình thường được auto-configure. Với cấu hình thủ công, hãy bật loại hypermedia mà ứng dụng muốn hỗ trợ.

## 5. Bật hỗ trợ hypermedia

Khi dùng Spring Boot và dependency HATEOAS starter phù hợp, auto-configuration thường đăng ký các thành phần cần thiết. Trong cấu hình Spring thủ công, có thể dùng `@EnableHypermediaSupport`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = {
        HypermediaType.HAL,
        HypermediaType.HAL_FORMS
})
public class HypermediaConfiguration {
}
```

Cấu hình trên yêu cầu hạ tầng hỗ trợ cả HAL và HAL-FORMS. Nếu ứng dụng chỉ cần HAL, có thể cấu hình một loại tương ứng. Tránh khai báo cấu hình thủ công trùng với auto-configuration của Boot khi không cần thiết; việc đăng ký converter hoặc module Jackson trùng lặp có thể gây khó hiểu khi chẩn đoán.

Cấu hình media type và cấu hình mapping là hai việc phối hợp với nhau:

- `@EnableHypermediaSupport` đăng ký hỗ trợ định dạng hypermedia.
- `produces` giới hạn định dạng endpoint có thể trả.
- `Accept` chọn định dạng client mong muốn.
- Affordance được gắn vào link cung cấp metadata để HAL-FORMS có thể biểu diễn trong template.

## 6. Accept và Content-Type trong từng tình huống

Hãy xét ba tình huống phổ biến:

| Tình huống | Request header | Ý nghĩa |
|---|---|---|
| Đọc đơn hàng dạng HAL | `Accept: application/hal+json` | Client muốn nhận HAL |
| Đọc đơn hàng dạng HAL-FORMS | `Accept: application/prs.hal-forms+json` | Client muốn nhận template tương tác |
| Cập nhật đơn hàng bằng JSON và nhận HAL | `Content-Type: application/json`, `Accept: application/hal+json` | Body gửi lên là JSON; response mong muốn là HAL |

Ví dụ request cập nhật:

```http
PUT /orders/42 HTTP/1.1
Content-Type: application/json
Accept: application/prs.hal-forms+json

{
  "note": "Giao sau 17 giờ"
}
```

Server đọc body theo `Content-Type` là JSON, xử lý request, rồi chọn response theo `Accept` là HAL-FORMS nếu endpoint và converter hỗ trợ.

Không nên dùng `Content-Type` để yêu cầu định dạng response. Nếu client muốn HAL, nó phải gửi `Accept: application/hal+json`; nếu muốn HAL-FORMS, nó phải gửi media type HAL-FORMS trong `Accept`.

## 7. Xử lý nhiều lựa chọn trong Accept

Client có thể gửi nhiều media type cùng mức ưu tiên hoặc kèm quality factor `q`:

```http
Accept: application/prs.hal-forms+json;q=1.0, application/hal+json;q=0.8
```

Trong ví dụ, client ưu tiên HAL-FORMS hơn HAL. Nếu endpoint và converter hỗ trợ cả hai, Spring MVC có thể chọn representation theo thứ tự ưu tiên và khả năng đáp ứng.

Một số lưu ý:

- `q` có giá trị từ 0 đến 1; giá trị cao hơn thể hiện mức ưu tiên cao hơn.
- `*/*` có nghĩa client chấp nhận mọi media type, nhưng kết quả mặc định còn phụ thuộc cấu hình server và converter.
- Không nên dựa vào thứ tự ngầm định khi client có thể gửi `Accept` tường minh.
- Nếu client yêu cầu một media type không được endpoint hỗ trợ, server thường trả `406 Not Acceptable`.

Đối với client có khả năng xử lý nhiều định dạng, hãy gửi danh sách `Accept` theo thứ tự ưu tiên. Đối với API public, nên tài liệu hóa các media type được hỗ trợ để client không phải thử ngẫu nhiên.

## 8. 406 Not Acceptable và 415 Unsupported Media Type

Hai lỗi này liên quan đến hai hướng khác nhau của content negotiation:

**406 Not Acceptable** xảy ra khi server không thể tạo response theo media type mà client yêu cầu. Ví dụ endpoint chỉ công bố HAL và HAL-FORMS nhưng client gửi:

```http
Accept: application/xml
```

**415 Unsupported Media Type** xảy ra khi server không chấp nhận định dạng body mà client gửi. Ví dụ mapping yêu cầu JSON:

```java
@PostMapping(
    value = "/orders",
    consumes = "application/json"
)
public EntityModel<OrderView> createOrder(
        @RequestBody OrderCreate input) {
    // ...
}
```

Nhưng client lại gửi:

```http
Content-Type: text/plain
```

Server không có mapping hoặc converter phù hợp để đọc body theo định dạng đó nên có thể trả 415.

Khi chẩn đoán:

- Kiểm tra `Accept` nếu response bị 406.
- Kiểm tra `Content-Type` của request body và thuộc tính `consumes` nếu request bị 415.
- Kiểm tra converter và cấu hình HATEOAS nếu media type đã đúng nhưng representation vẫn không được tuần tự hóa như mong đợi.

Không nên xử lý 406 bằng cách thay đổi `Content-Type` của request, cũng không nên xử lý 415 bằng cách đổi `Accept`. Hai header có vai trò khác nhau.

## 9. Content negotiation với affordance

Affordance được xây dựng từ mapping controller và gắn vào link. Khi client yêu cầu HAL-FORMS, Spring HATEOAS có thể tuần tự hóa các affordance thành `_templates`. Khi client yêu cầu HAL thông thường, representation vẫn có thể chứa link nhưng không cung cấp đầy đủ template HAL-FORMS.

Ví dụ assembler:

```java
Link self = linkTo(methodOn(OrderController.class)
        .getOrder(order.getId()))
        .withSelfRel()
        .andAffordance(afford(methodOn(OrderController.class)
                .updateOrder(order.getId(), null)));

return EntityModel.of(order.toView(), self);
```

Nếu client yêu cầu HAL-FORMS, response có thể mô tả template cập nhật:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "default": {
      "method": "put",
      "contentType": "application/json"
    }
  }
}
```

Tên template minh họa phụ thuộc cách affordance được đặt tên và số lượng template trong representation. Nếu client phụ thuộc vào tên template cụ thể, hãy đặt tên tường minh bằng API affordance và kiểm thử tên đó.

Affordance không tự làm endpoint hỗ trợ HAL-FORMS. Cần có cả ba điều kiện: mapping/controller được tham chiếu đúng, affordance được gắn vào representation và media type HAL-FORMS được hỗ trợ trong quá trình serialization.

## 10. Kiểm thử content negotiation bằng MockMvc

MockMvc cho phép gửi header `Accept` và `Content-Type` để xác nhận server chọn đúng representation. Ví dụ kiểm tra HAL:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists());
```

Kiểm tra HAL-FORMS:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_FORMS_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_FORMS_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._templates").exists());
```

Kiểm tra 406 khi client yêu cầu media type không được hỗ trợ:

```java
mockMvc.perform(get("/orders/{id}", orderId)
        .accept(MediaType.APPLICATION_XML))
    .andExpect(status().isNotAcceptable());
```

Kiểm tra 415 khi gửi body sai media type đến endpoint chỉ nhận JSON:

```java
mockMvc.perform(post("/orders")
        .contentType(MediaType.TEXT_PLAIN)
        .accept(MediaTypes.HAL_JSON)
        .content("not-json"))
    .andExpect(status().isUnsupportedMediaType());
```

Các test giả định endpoint giới hạn `produces` và `consumes` như các ví dụ trước. Nếu ứng dụng có exception handler tùy chỉnh hoặc mapping khác, status có thể được chuẩn hóa theo hợp đồng riêng; hãy xác nhận hành vi thực tế.

Nên kiểm tra thêm:

1. Request không gửi body nhưng có Accept phù hợp vẫn chọn đúng response format.
2. Client gửi nhiều media type với quality factor thì server chọn định dạng phù hợp.
3. Request JSON hợp lệ được đọc và response được trả theo Accept.
4. HAL-FORMS có template khi representation chứa affordance.
5. HAL thông thường không bị nhầm với HAL-FORMS.
6. Response có Content-Type tương thích với media type đã thương lượng.

## 11. Những lỗi thường gặp

**Dùng nhầm Accept và Content-Type.** Accept chọn định dạng response; Content-Type mô tả body request. Hãy kiểm tra đúng header khi gặp lỗi.

**Chỉ khai báo produces mà không có converter.** Mapping có thể cho phép media type nhưng ứng dụng chưa có hạ tầng tuần tự hóa tương ứng. Kiểm tra starter hoặc cấu hình hypermedia.

**Kỳ vọng HAL có _templates.** Template tương tác là phần mở rộng của HAL-FORMS. Yêu cầu đúng media type nếu client cần metadata này.

**Cho rằng affordance tự bật HAL-FORMS.** Affordance là metadata tương tác; converter và content negotiation vẫn phải hỗ trợ HAL-FORMS.

**Không khai báo consumes cho request body.** Server có thể nhận nhiều định dạng hơn dự kiến hoặc không báo lỗi đúng như hợp đồng. Khai báo rõ media type đầu vào nếu API cần ràng buộc.

**Phụ thuộc vào wildcard Accept.** Khi client gửi `*/*`, kết quả chọn media type có thể phụ thuộc cấu hình mặc định. Client cần định dạng cụ thể nên gửi Accept tường minh.

**Không kiểm thử lỗi 406/415.** Chỉ test happy path không phát hiện client gửi sai media type hoặc server công bố sai khả năng hỗ trợ.

## 12. Nguyên tắc thiết kế

- Dùng `Accept` để chọn representation response và `Content-Type` để mô tả request body.
- Công bố rõ media type mà từng endpoint hỗ trợ bằng `produces`.
- Giới hạn định dạng request body bằng `consumes` khi hợp đồng yêu cầu.
- Dùng HAL cho link và embedded resource; dùng HAL-FORMS khi client cần template tương tác.
- Bảo đảm converter và cấu hình Spring HATEOAS hỗ trợ media type được công bố.
- Không phụ thuộc vào kết quả mặc định của wildcard nếu client cần định dạng xác định.
- Kiểm thử status, Content-Type, cấu trúc HAL/HAL-FORMS và lỗi 406/415.
- Xem media type và semantics representation là một phần hợp đồng API cần quản lý khi tiến hóa.

## Kết luận

Content negotiation cho phép client và server thống nhất representation được trao đổi. Trong Spring HATEOAS, `Accept` chọn giữa HAL và HAL-FORMS, còn `Content-Type` xác định định dạng body request; `produces` và `consumes` giới hạn khả năng của endpoint. Hãy cấu hình converter phù hợp, dùng HAL-FORMS khi client cần template affordance và kiểm thử cả đường đi thành công lẫn lỗi 406/415 để hợp đồng media type rõ ràng, nhất quán.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Hypermedia formats](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [Spring Framework Reference – Content Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html#mvc-ann-requestmapping-produces)
- [RFC 9110 – HTTP Semantics: Content Negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#name-content-negotiation)

