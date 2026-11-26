# Content-Type header

Trong HTTP, **Content-Type** cho biết định dạng của phần thân (message body) mà một request hoặc response đang mang. Server dùng Content-Type của request để chọn cách đọc payload; client dùng Content-Type của response để biết cách phân tích representation nhận được.

Trong REST API dùng Spring HATEOAS, Content-Type đặc biệt quan trọng vì một tài nguyên có thể được biểu diễn bằng nhiều media type. Ví dụ, cùng một collection đơn hàng có thể được trả dưới dạng HAL JSON với media type `application/hal+json`, trong khi body tạo đơn hàng vẫn có thể dùng `application/json`. Nếu API hỗ trợ HAL-FORMS, response có thể dùng `application/prs.hal-forms+json`, còn template của form mô tả media type mà client phải gửi khi thực hiện thao tác.

Content-Type cần được hiểu cùng với `Accept`, `consumes` và `produces`. Content-Type mô tả body hiện có; Accept cho biết client muốn nhận định dạng nào; consumes giới hạn định dạng request mà endpoint chấp nhận; produces giới hạn định dạng response mà endpoint có thể tạo. Nhầm lẫn các khái niệm này thường dẫn đến lỗi 400, 406 hoặc 415.

Sau bài học, bạn có thể:

- Giải thích cú pháp và ý nghĩa của HTTP Content-Type.
- Phân biệt Content-Type với Accept, Content-Encoding và media type của từng property.
- Hiểu cách Spring MVC dùng HttpMessageConverter.
- Khai báo consumes và produces cho endpoint Spring HATEOAS.
- Chọn media type phù hợp cho HAL, HAL-FORMS, JSON Merge Patch và JSON Patch.
- Hiểu Content-Type trong template HAL-FORMS khác Content-Type của response.
- Chẩn đoán lỗi 406 Not Acceptable và 415 Unsupported Media Type.
- Kiểm thử request/response media type bằng MockMvc.

## Content-Type là gì?

Content-Type là HTTP representation header mô tả định dạng của phần thân message. Giá trị thường có dạng:

~~~http
Content-Type: type/subtype
~~~

Ví dụ:

~~~http
Content-Type: application/json
~~~

Giá trị application/json cho biết body là JSON. Một media type có thể đi kèm tham số:

~~~http
Content-Type: text/html; charset=UTF-8
Content-Type: multipart/form-data; boundary=----FormBoundary7MA4YWxkTrZu0gW
Content-Type: application/merge-patch+json
~~~

Media type gồm type và subtype. Tham số sau dấu chấm phẩy bổ sung thông tin cần thiết để diễn giải nội dung. Ví dụ multipart/form-data cần boundary để phân tách các phần trong body.

Content-Type mô tả định dạng của body cụ thể trong message. Nó không mô tả bản thân tài nguyên, không xác định HTTP method và cũng không cho biết server có hỗ trợ thao tác nào.

### Content-Type của request

Khi client gửi request có body, Content-Type cho server biết body được mã hóa theo định dạng nào:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "productId": 900,
  "quantity": 2
}
~~~

Trong ví dụ:

- Content-Type application/json mô tả body mà client gửi lên.
- Accept application/hal+json yêu cầu server trả response theo HAL JSON.
- POST là method xác định thao tác trên collection.

Server cần một bộ đọc tương thích với media type của request. Nếu endpoint chỉ chấp nhận JSON mà client gửi text/plain, server có thể từ chối request với 415 Unsupported Media Type.

### Content-Type của response

Response cũng có Content-Type để client biết định dạng body:

~~~http
HTTP/1.1 201 Created
Content-Type: application/hal+json
Location: /orders/42

{
  "id": 42,
  "status": "CREATED",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
~~~

Response trên là HAL JSON. Client cần HAL-capable parser hoặc ít nhất phải hiểu cấu trúc HAL để đọc _links.

Nếu response không có body, ví dụ 204 No Content, thường không cần Content-Type vì không có representation để mô tả.

## Phân biệt Content-Type và Accept

Đây là cặp header dễ bị nhầm nhất khi làm REST API:

| Header | Hướng áp dụng | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- | --- |
| Content-Type | Body hiện tại của request hoặc response | Body này được mã hóa theo định dạng nào? | application/json |
| Accept | Request của client | Client muốn nhận response theo định dạng nào? | application/hal+json |

Ví dụ client gửi JSON nhưng muốn nhận HAL:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "productId": 900,
  "quantity": 2
}
~~~

Không có mâu thuẫn giữa hai header. Request body là JSON đầu vào; response là HAL representation của đơn hàng vừa tạo.

Ngược lại, nếu client gửi Content-Type application/hal+json, điều đó có nghĩa client đang gửi body theo định dạng HAL JSON. Server chỉ chấp nhận nếu endpoint có hỗ trợ media type đó. Việc client yêu cầu HAL trong Accept không có nghĩa request body cũng phải là HAL.

### Content-Type khác Content-Encoding

Content-Type mô tả định dạng dữ liệu sau khi giải mã content coding. Content-Encoding mô tả cách body được mã hóa hoặc nén khi truyền:

~~~http
Content-Type: application/json
Content-Encoding: gzip
~~~

Body ở ví dụ vẫn là JSON, nhưng được nén gzip. Không dùng Content-Type application/gzip để thay cho Content-Encoding nếu nội dung sau giải nén là JSON.

### Content-Type khác charset

Charset là tham số mô tả bộ ký tự của một số media type văn bản. Ví dụ:

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

Với JSON trao đổi giữa các hệ thống, UTF-8 là encoding cần dùng. Nhiều framework hiện đại phát ra application/json mà không thêm tham số charset. Client không nên yêu cầu charset riêng để suy ra cấu trúc JSON.

## Media type trong Spring MVC

Spring MVC sử dụng HttpMessageConverter để đọc request body và ghi response body. Converter được chọn dựa trên:

- Kiểu Java của tham số hoặc giá trị trả về.
- Content-Type của request khi đọc body.
- Accept của request và media type endpoint có thể produces khi ghi response.
- Các converter và cấu hình đã đăng ký trong application context.

Ví dụ, Jackson converter đọc JSON thành DTO và ghi DTO thành JSON. Khi bật Spring HATEOAS với cấu hình HAL phù hợp, converter hypermedia có thể serialize RepresentationModel, EntityModel, CollectionModel thành HAL JSON.

### consumes: media type được endpoint chấp nhận

consumes khai báo media type mà endpoint chấp nhận cho request body:

~~~java
@PostMapping(
    path = "/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
EntityModel<OrderResponse> create(
        @RequestBody CreateOrderRequest request) {
    // ...
}
~~~

Spring so khớp Content-Type của request với consumes. Nếu không có mapping nào chấp nhận media type được gửi, request thường bị từ chối với 415 Unsupported Media Type.

### produces: media type endpoint có thể trả về

produces khai báo media type của response representation:

~~~java
@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
CollectionModel<EntityModel<OrderResponse>> all() {
    // ...
}
~~~

Spring dùng produces cùng Accept của client để chọn handler và converter phù hợp. Nếu client chỉ chấp nhận application/xml nhưng endpoint chỉ produces HAL JSON, server thường trả 406 Not Acceptable.

### Kết hợp consumes và produces

Một endpoint có thể đồng thời giới hạn cả hai chiều:

~~~java
@PostMapping(
    path = "/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaTypes.HAL_JSON_VALUE
)
ResponseEntity<EntityModel<OrderResponse>> create(
        @Valid @RequestBody CreateOrderRequest request) {

    Order created = orderService.create(request);
    EntityModel<OrderResponse> body = assembler.toModel(created);

    return ResponseEntity
        .created(URI.create(body.getRequiredLink("self").getHref()))
        .contentType(MediaTypes.HAL_JSON)
        .body(body);
}
~~~

Ví dụ giả định OrderService và assembler được inject, CreateOrderRequest là DTO đầu vào và assembler tạo self link. consumes ràng buộc request body JSON; produces và Content-Type của ResponseEntity mô tả HAL response.

Thông thường Spring có thể tự chọn Content-Type response từ converter và negotiation. Gọi contentType(...) tường minh hữu ích khi API cần cố định representation của response. Không cần đặt header thủ công nếu converter đã tạo đúng media type.

## Content-Type trong Spring HATEOAS và HAL

HAL JSON sử dụng media type application/hal+json. Trong Spring HATEOAS, dùng hằng số để tránh gõ sai:

~~~java
import org.springframework.hateoas.MediaTypes;

MediaTypes.HAL_JSON
MediaTypes.HAL_JSON_VALUE
~~~

Endpoint có thể công bố HAL:

~~~java
@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
CollectionModel<OrderModel> all() {
    return assembler.toCollectionModel(orderService.findAll());
}
~~~

Client yêu cầu:

~~~http
GET /orders HTTP/1.1
Accept: application/hal+json
~~~

Server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

HAL JSON là một media type cụ thể dựa trên JSON. Nó cho biết body không chỉ là JSON tùy ý mà tuân theo cấu trúc hypermedia HAL, gồm các thuộc tính như _links và _embedded.

### application/json và application/hal+json không đồng nghĩa

Cả hai đều có cú pháp JSON, nhưng semantics khác nhau:

- application/json biểu thị JSON tổng quát.
- application/hal+json biểu thị JSON tuân theo cấu trúc HAL.

Client phân tích JSON thuần có thể đọc cú pháp của HAL, nhưng chưa chắc biết cách điều hướng relation hoặc diễn giải embedded resources. API HATEOAS nên công bố đúng media type để client biết representation có hypermedia semantics.

Không nên đặt Content-Type application/json cho body HAL chỉ vì body có cú pháp JSON. Hãy trả media type phù hợp với định dạng representation thực tế.

### Cấu hình hỗ trợ HAL

Trong ứng dụng Spring Boot, dùng dependency Spring HATEOAS tương ứng, thường là spring-boot-starter-hateoas. Cấu hình tự động của Boot có thể đăng ký các thành phần hypermedia. Với cấu hình Spring MVC thủ công, bật hỗ trợ HAL bằng cấu hình Spring HATEOAS:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
~~~

Chỉ thêm produces = application/hal+json không tự biến một object bất kỳ thành HAL. Controller cần trả representation model phù hợp và application phải có converter hypermedia tương ứng.

## Content-Type trong HAL-FORMS

HAL-FORMS là media type hypermedia mở rộng HAL để mô tả các template và affordance. Response HAL-FORMS sử dụng application/prs.hal-forms+json.

Client yêu cầu representation:

~~~http
GET /orders/42 HTTP/1.1
Accept: application/prs.hal-forms+json
~~~

Trong HAL-FORMS, template có thể chứa thuộc tính contentType:

~~~json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "update": {
      "method": "PATCH",
      "contentType": "application/merge-patch+json",
      "properties": [
        {
          "name": "deliveryNote",
          "type": "text"
        }
      ]
    }
  }
}
~~~

Phải phân biệt hai nơi:

- HTTP header Content-Type application/prs.hal-forms+json mô tả response template mà server vừa trả.
- Thuộc tính template contentType application/merge-patch+json mô tả media type mà client phải dùng khi gửi payload để thực hiện affordance PATCH.

Khi client thực hiện template update, request có thể là:

~~~http
PATCH /orders/42 HTTP/1.1
Content-Type: application/merge-patch+json
Accept: application/hal+json

{
  "deliveryNote": "Giao tại quầy lễ tân"
}
~~~

Response HAL-FORMS không bắt buộc client gửi lại body theo HAL-FORMS. Client phải tuân theo method, target và contentType được mô tả trong template.

### Property type không phải Content-Type

Trong HAL-FORMS, từng property có thể có type như text, email, date hoặc number. Đây là gợi ý loại input control, không phải media type của HTTP body.

Ví dụ:

~~~json
{
  "method": "POST",
  "contentType": "application/json",
  "properties": [
    {
      "name": "email",
      "type": "email"
    },
    {
      "name": "birthDate",
      "type": "date"
    }
  ]
}
~~~

Ở đây contentType là application/json, còn type của email và birthDate chỉ định cách client có thể hiển thị input. Client sẽ gửi JSON có key email và birthDate.

## Content-Type cho các định dạng PATCH

PATCH không có một định dạng body duy nhất. Media type của patch document xác định semantics mà server phải áp dụng.

### JSON Merge Patch

JSON Merge Patch dùng application/merge-patch+json. Ví dụ:

~~~http
PATCH /orders/42 HTTP/1.1
Content-Type: application/merge-patch+json

{
  "deliveryNote": "Giao tại quầy lễ tân"
}
~~~

Thuộc tính không xuất hiện giữ nguyên theo semantics Merge Patch; thuộc tính có giá trị null biểu thị yêu cầu loại bỏ thuộc tính tương ứng. Object được merge đệ quy và array được thay thế như một giá trị.

Controller có thể khai báo:

~~~java
@PatchMapping(
    path = "/{id}",
    consumes = "application/merge-patch+json",
    produces = MediaTypes.HAL_JSON_VALUE
)
EntityModel<OrderResponse> mergePatch(
        @PathVariable Long id,
        @RequestBody JsonNode patchDocument) {
    Order updated = orderService.applyMergePatch(id, patchDocument);
    return assembler.toModel(updated);
}
~~~

JsonNode cho phép service phân biệt property bị bỏ qua với property có giá trị null. Service vẫn phải kiểm tra field được phép cập nhật, kiểu dữ liệu và quy tắc nghiệp vụ.

### JSON Patch

JSON Patch dùng application/json-patch+json. Body là một mảng thao tác:

~~~http
PATCH /orders/42 HTTP/1.1
Content-Type: application/json-patch+json

[
  {
    "op": "replace",
    "path": "/deliveryNote",
    "value": "Giao tại quầy lễ tân"
  }
]
~~~

JSON Patch định nghĩa các thao tác như add, remove, replace, move, copy và test. Server phải giới hạn path và thao tác được phép; không để client tùy ý sửa các trường nội bộ hoặc trường chỉ được thay đổi qua quy trình nghiệp vụ.

### Định dạng riêng của API

API có thể dùng application/json cho DTO cập nhật một phần riêng, nhưng phải định nghĩa semantics rõ ràng. Nếu thuộc tính bị bỏ qua và thuộc tính có giá trị null đều deserialize thành null, DTO đơn giản có thể không đủ để phân biệt giữ nguyên và xóa giá trị.

Không nên gắn media type Merge Patch hoặc JSON Patch cho một body có semantics khác các RFC tương ứng. Media type là hợp đồng về cách diễn giải nội dung, không chỉ là nhãn trang trí.

## Media type có tham số và custom media type

Media type có thể chứa tham số để làm rõ cách diễn giải:

~~~http
Content-Type: application/json; charset=UTF-8
Content-Type: multipart/form-data; boundary=----abc123
Content-Type: application/vnd.example.order+json
~~~

application/vnd.example.order+json là ví dụ vendor media type. Hậu tố +json cho biết cú pháp dựa trên JSON, nhưng semantics của media type vẫn do hợp đồng vendor định nghĩa.

Trong Java, có thể phân tích media type:

~~~java
MediaType vendorOrder = MediaType.parseMediaType(
    "application/vnd.example.order+json");
~~~

Nếu API dùng custom media type, hãy đăng ký converter hoặc cấu hình converter hiện có để đọc/ghi kiểu dữ liệu phù hợp. Đừng cho rằng hậu tố +json tự động khiến mọi converter tùy chỉnh xử lý đúng trong mọi cấu hình.

### Media type và versioning

Một số API đưa version vào media type, ví dụ:

~~~http
Accept: application/vnd.example.order-v2+json
~~~

Đây là một chiến lược versioning có thể dùng, nhưng cần cân nhắc khả năng cache, tài liệu hóa và độ phức tạp negotiation. Không nên thay đổi media type chỉ vì thêm một field tương thích vào representation. Chọn chiến lược versioning nhất quán và giữ semantics của media type ổn định.

## Các lỗi thường gặp liên quan đến Content-Type

### 415 Unsupported Media Type

415 thường xuất hiện khi server không chấp nhận định dạng body của request hoặc không có converter phù hợp.

Ví dụ endpoint chỉ nhận JSON:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
void create(@RequestBody CreateOrderRequest request) {
    // ...
}
~~~

Request sau không phù hợp:

~~~http
POST /orders
Content-Type: text/plain

{"productId":900}
~~~

Kiểm tra:

- Client đã đặt Content-Type đúng với body chưa?
- Endpoint có consumes giới hạn media type không?
- Application có HttpMessageConverter đọc media type đó không?
- Body có thực sự được mã hóa theo media type khai báo không?

### 406 Not Acceptable

406 thường xuất hiện khi server không thể tạo representation phù hợp với Accept của client.

Ví dụ endpoint chỉ trả HAL:

~~~java
@GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
CollectionModel<OrderModel> all() {
    // ...
}
~~~

Client yêu cầu:

~~~http
GET /orders
Accept: application/xml
~~~

Nếu không có converter hoặc endpoint nào trả XML, server có thể trả 406. Client nên gửi media type mà API công bố hỗ trợ, ví dụ application/hal+json.

### 400 Bad Request không đồng nghĩa 415

Nếu Content-Type được hỗ trợ nhưng body sai cú pháp hoặc không thể deserialize thành DTO, server thường trả 400 Bad Request. Ví dụ khai báo application/json nhưng body bị thiếu dấu ngoặc hoặc gửi chuỗi vào trường số.

Phân biệt nhanh:

| Status | Vấn đề thường gặp |
| --- | --- |
| 400 Bad Request | Body không hợp lệ hoặc không thể đọc/validate theo hợp đồng |
| 406 Not Acceptable | Server không tạo được response theo Accept |
| 415 Unsupported Media Type | Server không chấp nhận Content-Type của request body |

Status cuối cùng phụ thuộc exception handler và cấu hình ứng dụng; hãy giữ cách ánh xạ lỗi nhất quán.

## Kiểm thử Content-Type bằng MockMvc

Kiểm thử nên xác minh cả Content-Type request được gửi và Content-Type response được trả.

Ví dụ POST JSON và nhận HAL:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderMediaTypeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void acceptsJsonAndReturnsHal() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "productId": 900,
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(header().exists("Location"));
    }
}
~~~

Test giả định dữ liệu hợp lệ, service tạo đơn hàng thành công và endpoint trả 201 Created cùng HAL representation.

Kiểm thử 415 khi request gửi sai Content-Type:

~~~java
@Test
void rejectsUnsupportedRequestContentType() throws Exception {
    mockMvc.perform(post("/orders")
            .contentType(MediaType.TEXT_PLAIN)
            .accept(MediaTypes.HAL_JSON)
            .content("productId=900"))
        .andExpect(status().isUnsupportedMediaType());
}
~~~

Kiểm thử 406 khi client yêu cầu response format không hỗ trợ:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@Test
void rejectsUnsupportedAcceptType() throws Exception {
    mockMvc.perform(get("/orders")
            .accept(MediaType.APPLICATION_XML))
        .andExpect(status().isNotAcceptable());
}
~~~

Test 406 giả định endpoint chỉ produces HAL JSON và ứng dụng không đăng ký XML converter cho endpoint đó.

Các trường hợp nên kiểm thử:

1. Request JSON hợp lệ được đọc thành DTO.
2. Request có Content-Type không được hỗ trợ nhận 415.
3. Request JSON sai cú pháp nhận lỗi 400.
4. Accept HAL JSON trả Content-Type HAL JSON.
5. Accept media type không hỗ trợ nhận 406.
6. HAL-FORMS response trả đúng application/prs.hal-forms+json.
7. Template HAL-FORMS công bố contentType phù hợp với request affordance.
8. JSON Merge Patch và JSON Patch chỉ được nhận ở endpoint có consumes tương ứng.
9. Response 204 không chứa body và không phụ thuộc Content-Type.
10. Các custom media type được đọc/ghi bởi converter đã cấu hình.

## Những sai lầm thường gặp

**Dùng Content-Type thay cho Accept.** Content-Type mô tả body đang gửi; Accept mô tả response client muốn nhận.

**Cho rằng request và response phải có cùng media type.** Client có thể gửi application/json và nhận application/hal+json trong cùng một request.

**Đặt application/json cho response HAL.** Cú pháp JSON giống nhau nhưng semantics hypermedia khác nhau. Hãy công bố application/hal+json khi body là HAL.

**Nghĩ produces kiểm tra request body.** produces ràng buộc response; consumes ràng buộc Content-Type của request.

**Nghĩ Content-Type trong HAL-FORMS template là header response.** Thuộc tính template contentType mô tả payload client sẽ gửi khi thực hiện affordance.

**Dùng type của property thay cho media type.** type: email là metadata input control; nó không thay thế contentType: application/json.

**Dùng media type PATCH sai semantics.** Chỉ khai báo application/merge-patch+json nếu server thực sự áp dụng quy tắc JSON Merge Patch.

**Coi hậu tố +json là đủ để hỗ trợ converter.** Custom media type vẫn cần converter và negotiation phù hợp.

**Chỉ kiểm tra status code.** Hãy kiểm tra cả request Content-Type, response Content-Type và cấu trúc representation.

## Kết luận

Content-Type mô tả định dạng body của HTTP message. Trong Spring MVC, nó tham gia vào việc chọn HttpMessageConverter và được ràng buộc ở endpoint bằng consumes; Accept cùng produces quyết định representation response. Với Spring HATEOAS, HAL JSON dùng application/hal+json, HAL-FORMS dùng application/prs.hal-forms+json, còn payload của từng affordance có thể dùng application/json, JSON Merge Patch hoặc JSON Patch tùy hợp đồng.

Hãy chọn media type theo đúng semantics của body, phân biệt header response với contentType trong template HAL-FORMS, và không nhầm type của input property với HTTP media type. Kiểm thử 400, 406 và 415 cùng Content-Type thực tế để bảo đảm client và server thống nhất cách trao đổi representation.

Tài liệu tham khảo:

- RFC 9110 — HTTP Semantics, Content-Type: https://www.rfc-editor.org/rfc/rfc9110.html#section-8.3
- RFC 9110 — Accept: https://www.rfc-editor.org/rfc/rfc9110.html#section-12.5.1
- Spring Framework Reference — HTTP Message Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html
- Spring HATEOAS Reference — HAL and HAL-FORMS: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes
