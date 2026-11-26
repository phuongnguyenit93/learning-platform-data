# Media type là gì?

Media type là nhãn chuẩn hóa cho biết nội dung của một HTTP message được biểu diễn theo định dạng nào và cần được diễn giải ra sao. Khi API gửi một object JSON, file PDF, ảnh PNG hoặc một representation hypermedia như HAL, media type giúp bên nhận chọn bộ đọc và cách xử lý phù hợp.

Trong REST API, media type là một phần của hợp đồng trao đổi dữ liệu. Client dùng header `Accept` để nêu những định dạng response có thể xử lý; server dùng `Content-Type` để công bố định dạng thực tế của body. Với Spring HATEOAS, các media type như `application/hal+json` và `application/prs.hal-forms+json` còn cho client biết response tuân theo quy ước hypermedia nào.

## Media type mô tả representation

HTTP truyền dữ liệu trong message body. Body có thể là JSON, XML, văn bản thuần, hình ảnh, âm thanh, multipart hoặc một định dạng ứng dụng chuyên biệt. Chỉ nhìn các byte của body, bên nhận không phải lúc nào cũng xác định chắc chắn được cách diễn giải. Media type cung cấp thông tin đó.

Ví dụ:

| Media type | Nội dung thường gặp | Cách diễn giải |
| --- | --- | --- |
| `application/json` | JSON tổng quát | Parse thành object/array JSON. |
| `application/xml` | XML | Parse theo cú pháp XML và hợp đồng tương ứng. |
| `text/plain` | Văn bản thuần | Đọc như text. |
| `text/html` | HTML | Hiển thị hoặc parse tài liệu HTML. |
| `image/png` | Ảnh PNG | Xử lý như dữ liệu ảnh PNG. |
| `application/pdf` | Tài liệu PDF | Mở bằng bộ đọc PDF. |
| `application/hal+json` | JSON theo HAL | Parse JSON và đọc `_links`, `_embedded`. |
| `application/prs.hal-forms+json` | JSON theo HAL-FORMS | Đọc link cùng `_templates` mô tả thao tác và input. |

Media type mô tả representation được gửi trong message hiện tại. Nó không tự mô tả toàn bộ domain model, không thay thế schema dữ liệu và cũng không quyết định tài nguyên nào được phép truy cập. Ví dụ, `application/json` cho biết body có cú pháp JSON nhưng không nói trường `orderId` mang ý nghĩa gì; ý nghĩa đó đến từ hợp đồng API.

## Cấu trúc type và subtype

Một media type cơ bản có dạng:

```text
type/subtype
```

Ví dụ `application/json` gồm:

- `type`: `application`, nhóm các định dạng dữ liệu dành cho ứng dụng.
- `subtype`: `json`, định dạng cụ thể trong nhóm đó.

Một số type phổ biến:

| Type | Nhóm nội dung điển hình | Ví dụ |
| --- | --- | --- |
| `application` | Dữ liệu ứng dụng hoặc định dạng có cấu trúc | `application/json`, `application/pdf` |
| `text` | Nội dung văn bản | `text/plain`, `text/html`, `text/csv` |
| `image` | Dữ liệu hình ảnh | `image/png`, `image/jpeg` |
| `audio` | Dữ liệu âm thanh | `audio/mpeg`, `audio/wav` |
| `video` | Dữ liệu video | `video/mp4` |
| `multipart` | Một body gồm nhiều phần riêng | `multipart/form-data`, `multipart/mixed` |

Tên type và subtype không phân biệt chữ hoa chữ thường theo quy tắc HTTP. Dù vậy, nên viết nhất quán bằng chữ thường để dễ đọc và tránh so sánh chuỗi thiếu chuẩn hóa.

## Media type có thể có parameters

Sau type/subtype, media type có thể có các parameter phân tách bằng dấu chấm phẩy:

```text
type/subtype; parameter=value
```

Ví dụ:

```http
Content-Type: text/plain; charset=UTF-8
Content-Type: multipart/form-data; boundary=----WebKitFormBoundaryabc123
Content-Type: application/json; charset=UTF-8
```

Parameter bổ sung thông tin cần thiết để diễn giải body. Một số ví dụ:

- `charset` cho biết bảng mã ký tự của nội dung văn bản.
- `boundary` xác định ranh giới giữa các phần trong body `multipart`.
- `profile` có thể tham chiếu một profile mô tả cách diễn giải representation trong những định dạng có hỗ trợ.

Không phải media type nào cũng dùng cùng một parameter. Chỉ gửi parameter có ý nghĩa với định dạng đang dùng và bảo đảm server/client hỗ trợ nó. Với JSON hiện đại, UTF-8 là cách mã hóa cần dùng; không nên dựa vào một charset tùy ý để thay đổi cách diễn giải JSON.

Đối với upload file, `multipart/form-data` mô tả body gồm nhiều part. Mỗi part có thể mang `Content-Disposition` và `Content-Type` riêng. `Content-Disposition` là header mô tả cách xử lý phần nội dung; nó không phải một media type.

## Structured syntax suffix như `+json`

Một số media type có structured syntax suffix ở cuối subtype, chẳng hạn `+json` hoặc `+xml`:

```text
application/hal+json
application/vnd.example.order-v2+json
application/problem+json
application/prs.hal-forms+json
```

Hậu tố `+json` cho biết định dạng dùng cú pháp JSON và có thể được xử lý ở mức cú pháp bằng công cụ JSON tổng quát. Tuy nhiên, nó không làm cho mọi media type `+json` có cùng ngữ nghĩa. Client hiểu JSON nhưng vẫn cần biết quy ước riêng của HAL, Problem Details hoặc representation nghiệp vụ.

Vì vậy, `application/hal+json` không đơn giản đồng nghĩa với `application/json`. Một client yêu cầu chính xác `application/json` không nên mặc định coi mọi media type `+json` là thay thế tương đương. Hãy công bố và yêu cầu đúng media type của hợp đồng.

## Media type chuẩn, mở rộng và vendor-specific

Media type được đăng ký theo quy ước chuẩn hóa. Ngoài các loại phổ biến, ứng dụng có thể cần một định dạng riêng. Ví dụ:

```text
application/vnd.example.order-v2+json
```

`vnd.` là cách đặt tên trong vendor tree; `example.order-v2` mô tả định dạng do nhà cung cấp định nghĩa; `+json` cho biết cú pháp nền là JSON. Cách này có thể được dùng khi API muốn biểu diễn một representation đặc thù hoặc một biến thể có version.

Không nên tạo vendor media type chỉ để thay đổi tên một cách tùy tiện. Trước khi dùng, cần định nghĩa cấu trúc, semantics, khả năng tương thích, cách version hóa và hành vi client. Media type versioning là một lựa chọn thiết kế, không tự động giải quyết việc tiến hóa API.

Với quan hệ hypermedia, hãy ưu tiên media type đã có định nghĩa rõ như HAL hoặc HAL-FORMS khi chúng phù hợp. Không tự đặt một media type mới chỉ để thêm trường `_links` vào JSON nếu có định dạng hypermedia tiêu chuẩn đáp ứng nhu cầu.

## `Content-Type` và `Accept` khác nhau thế nào?

Hai header thường bị nhầm lẫn nhưng có hướng và vai trò khác nhau:

| Header | Nằm ở đâu | Ý nghĩa |
| --- | --- | --- |
| `Content-Type` | Request hoặc response | Mô tả định dạng của body đang được gửi. |
| `Accept` | Request | Nêu các media type mà client muốn nhận trong response. |

Khi client gửi JSON để tạo đơn hàng và muốn nhận HAL, request có thể là:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": "c-17",
  "note": "Giao trong giờ hành chính"
}
```

Ở đây:

- `Content-Type: application/json` mô tả request body.
- `Accept: application/hal+json` yêu cầu server trả response theo HAL.

Response có thể là:

```http
HTTP/1.1 201 Created
Content-Type: application/hal+json
Location: https://shop.example/api/orders/o-42

{
  "id": "o-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    }
  }
}
```

`Accept` không mô tả request body và `Content-Type` không phải cách client yêu cầu response. Nếu request không có body, thường không cần `Content-Type` cho request đó; `Accept` vẫn có thể được gửi để chọn định dạng response.

## Content negotiation là gì?

Content negotiation là quá trình client và server chọn representation phù hợp cho một request. Client có thể hỗ trợ nhiều định dạng; server có thể cung cấp nhiều representation của cùng một tài nguyên. Header `Accept` giúp client nêu thứ tự ưu tiên.

Ví dụ:

```http
Accept: application/hal+json;q=1.0, application/json;q=0.8, */*;q=0.1
```

`q` là quality value từ `0` đến `1`, biểu thị mức ưu tiên tương đối của media range. Giá trị mặc định là `1`. `q=0` nghĩa là client không chấp nhận media range đó. Trong ví dụ, client ưu tiên HAL, sau đó JSON tổng quát và cuối cùng là định dạng bất kỳ nếu server cần fallback.

Client cũng có thể dùng wildcard:

| Accept value | Ý nghĩa |
| --- | --- |
| `application/hal+json` | Chấp nhận chính xác HAL JSON. |
| `application/*` | Chấp nhận các subtype thuộc type `application`. |
| `*/*` | Chấp nhận mọi media type. |

Nếu `Accept` không được gửi, server thường xem như client không đặt giới hạn cụ thể về media type response. Nếu có nhiều lựa chọn phù hợp, server chọn theo cấu hình, thứ tự ưu tiên và khả năng hỗ trợ của ứng dụng. Không nên giả định mọi server luôn chọn cùng một representation khi client gửi wildcard.

## Khi không thể thỏa thuận media type

Content negotiation có thể thất bại trong hai tình huống phổ biến:

| HTTP status | Tình huống | Ví dụ |
| --- | --- | --- |
| `406 Not Acceptable` | Server không thể tạo response theo media type mà client chấp nhận. | Client chỉ gửi `Accept: application/xml` nhưng endpoint chỉ trả HAL. |
| `415 Unsupported Media Type` | Server không hỗ trợ định dạng request body được gửi lên. | Client gửi `Content-Type: application/xml` nhưng endpoint chỉ nhận JSON. |

Hai status này mô tả hai chiều khác nhau. `406` liên quan đến representation response; `415` liên quan đến định dạng nội dung request. Lỗi validation của dữ liệu JSON thường là một lỗi khác, chẳng hạn `400 Bad Request` hoặc status do ứng dụng quy định.

## Media type trong Spring Framework

Spring biểu diễn media type bằng lớp `org.springframework.http.MediaType`. Lớp này giúp parse, so sánh và kiểm tra tính tương thích thay vì xử lý chuỗi thủ công.

```java
import org.springframework.http.MediaType;

MediaType json = MediaType.APPLICATION_JSON;
MediaType plainText = MediaType.TEXT_PLAIN;
MediaType custom = MediaType.parseMediaType(
        "application/vnd.example.order-v2+json");
String type = custom.getType();
String subtype = custom.getSubtype();
```

Khi kiểm tra tương thích bằng `isCompatibleWith(...)`, cần hiểu rằng Spring so sánh media range theo quy tắc type/subtype và wildcard; structured suffix `+json` không tự biến media type chuyên biệt thành `application/json`. Không nên suy ra mọi media type JSON-based có thể thay thế `application/json` trong mọi hợp đồng hoặc mọi content negotiation. Dùng `MediaType` để làm việc với media type cụ thể mà API công bố.

Spring HATEOAS bổ sung các hằng trong `org.springframework.hateoas.MediaTypes`:

```java
import org.springframework.hateoas.MediaTypes;

MediaTypes.HAL_JSON;             // application/hal+json
MediaTypes.HAL_JSON_VALUE;       // String dùng trong annotation
MediaTypes.HAL_FORMS_JSON;       // application/prs.hal-forms+json
MediaTypes.HAL_FORMS_JSON_VALUE;
```

Các hằng này giúp tránh gõ sai media type và làm rõ representation mà endpoint công bố. HAL JSON dùng `_links` và `_embedded`; HAL-FORMS bổ sung `_templates` để mô tả các thao tác có input.

## Khai báo media type trong controller

Trong Spring MVC, `produces` xác định media type response mà handler có thể tạo; `consumes` giới hạn media type request body mà handler chấp nhận.

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderAssembler assembler;

    OrderController(OrderService service, OrderAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<OrderDto> one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaTypes.HAL_JSON_VALUE)
    ResponseEntity<EntityModel<OrderDto>> create(
            @RequestBody CreateOrderRequest request) {
        Order created = service.create(request);
        EntityModel<OrderDto> model = assembler.toModel(created);

        return ResponseEntity
                .created(model.getRequiredLink("self").toUri())
                .body(model);
    }
}
```

Client gọi endpoint chi tiết với `Accept: application/hal+json`. Với endpoint tạo mới, request body phải có `Content-Type: application/json`; response được chọn theo `Accept` và công bố HAL. Các kiểu `Order`, `OrderDto`, `OrderService`, `OrderAssembler` và `CreateOrderRequest` là thành phần ứng dụng minh họa.

Nếu một endpoint hỗ trợ nhiều representation, có thể khai báo nhiều giá trị trong `produces` hoặc tạo handler/representation tương ứng. Hãy bảo đảm message converter có thể serialize kiểu trả về sang từng media type đã khai báo.

## Message converter và media type

Trong Spring MVC, `HttpMessageConverter` đọc request body và ghi response body. Converter được chọn dựa trên kiểu Java, media type của request/response và cấu hình ứng dụng.

| Công việc | Thành phần Spring MVC |
| --- | --- |
| Đọc JSON request thành DTO | Jackson HTTP message converter |
| Ghi DTO thành JSON | Jackson HTTP message converter |
| Ghi `EntityModel`/`CollectionModel` thành HAL | Spring HATEOAS hypermedia message converter |
| Chọn handler theo media type | Request mapping với `consumes`/`produces` và content negotiation |

Với WebFlux, cơ chế tương ứng sử dụng `HttpMessageReader` và `HttpMessageWriter`/codec. Vì vậy, một ứng dụng WebFlux cần cấu hình và starter phù hợp với WebFlux stack; không nên giả định converter Servlet được dùng y nguyên.

Khi response có `EntityModel` nhưng thiếu `_links`, hãy kiểm tra kiểu trả về, media type được yêu cầu và hypermedia converter. Việc DTO có trường tên `links` không tự biến nó thành HAL representation.

## Media type và cache

Nếu cùng một URI có thể trả nhiều representation tùy theo `Accept`, cache trung gian cần biết response thay đổi theo header nào. Server thường cần gửi:

```http
Vary: Accept
```

`Vary: Accept` hướng dẫn cache tách các biến thể response theo giá trị `Accept`. Nếu thiếu thông tin này trong hệ thống cache phù hợp, client có thể nhận nhầm representation đã được cache cho một media type khác.

Cache key còn phụ thuộc các header khác nếu representation thay đổi theo chúng. Không thêm `Vary` tùy tiện; hãy cấu hình theo các yếu tố thực sự làm thay đổi response và chính sách cache của ứng dụng.

## Media type không phải ngôn ngữ hoặc mã hóa nội dung

Một số HTTP header liên quan đến cách client nhận nội dung nhưng không phải media type:

| Header | Ý nghĩa |
| --- | --- |
| `Accept-Language` | Ngôn ngữ tự nhiên client muốn nhận, ví dụ `vi`, `en`. |
| `Content-Encoding` | Cách body được mã hóa/nén ở tầng truyền tải, ví dụ `gzip`, `br`. |
| `Content-Disposition` | Gợi ý cách trình duyệt xử lý nội dung, ví dụ tải file với tên nào. |
| `Accept-Encoding` | Các content coding client có thể giải nén. |

Ví dụ, một response có thể là `Content-Type: application/json`, `Content-Encoding: gzip` và `Content-Language: vi`. JSON là media type; gzip là content coding; tiếng Việt là ngôn ngữ của nội dung. Không dùng `Accept-Language` để chọn giữa HAL và JSON.

## Kiểm thử media type với MockMvc

Kiểm thử nên xác nhận cả content negotiation và cấu trúc representation. Ví dụ endpoint trả HAL:

```java
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
class OrderMediaTypeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsHalWhenClientAcceptsHal() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href").exists());
    }

    @Test
    void rejectsUnsupportedAcceptType() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-42")
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }
}
```

Fixture cần có đơn hàng `o-42`. Test `406` giả định endpoint chỉ hỗ trợ HAL và ứng dụng không có converter hoặc handler XML khác. Nếu ứng dụng hỗ trợ XML, hãy chọn một media type không được endpoint hỗ trợ trong test.

Với endpoint nhận JSON, kiểm tra `415` bằng cách gửi một request body có `Content-Type` không được `consumes` chấp nhận. Với WebFlux, dùng `WebTestClient` để kiểm tra tương tự.

Các assertion hữu ích:

- `Content-Type` response tương thích với media type được yêu cầu.
- `_links` và `_embedded` có mặt khi response là HAL.
- `_templates` xuất hiện khi response là HAL-FORMS và affordance được công bố.
- Request JSON được đọc đúng khi `Content-Type` phù hợp.
- `406` và `415` xảy ra theo hợp đồng content negotiation của ứng dụng.
- Cache header `Vary` có mặt nếu response thay đổi theo `Accept`.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm `Accept` với `Content-Type` | Client yêu cầu sai định dạng hoặc server đọc body sai. | `Accept` chọn response; `Content-Type` mô tả body đang gửi. |
| Trả HAL với `application/json` | Client không biết response tuân theo cấu trúc HAL. | Công bố `application/hal+json`. |
| Coi mọi `+json` là `application/json` | Client hiểu sai semantics của representation chuyên biệt. | Dùng đúng media type và parser theo định dạng. |
| Không khai báo `produces`/`consumes` khi cần giới hạn rõ | Handler có thể được chọn hoặc bị từ chối khác kỳ vọng. | Khai báo media type phù hợp và kiểm thử negotiation. |
| Thiếu converter/codec | Spring không đọc hoặc ghi được body theo media type. | Kiểm tra starter và message converter/codec tương ứng. |
| Bỏ qua `Vary: Accept` | Cache có thể dùng nhầm biến thể response. | Khai báo Vary khi response phụ thuộc Accept. |
| Nhầm `Accept-Language` với media type | Chọn sai representation. | Dùng header ngôn ngữ riêng cho localization. |

## Nguyên tắc thiết kế

- Chọn media type phản ánh đúng cấu trúc và semantics của representation.
- Dùng `type/subtype` cùng parameters theo quy ước của định dạng.
- Phân biệt cú pháp `+json` với ngữ nghĩa riêng của HAL hoặc media type chuyên biệt.
- Dùng `Accept` để thương lượng response và `Content-Type` để mô tả body.
- Trong Spring, dùng `MediaType`, `MediaTypes`, `produces` và `consumes` thay vì ghép chuỗi tùy tiện.
- Bảo đảm message converter hoặc WebFlux codec hỗ trợ media type đã công bố.
- Xử lý `406` và `415` nhất quán với hợp đồng API.
- Kiểm thử media type, hypermedia structure và cache variation.

Media type là nền tảng để client và server thống nhất cách diễn giải HTTP representation. Trong Spring HATEOAS, lựa chọn media type còn xác định client đọc hypermedia theo quy ước nào: HAL cho link và embedded resource, HAL-FORMS cho link cùng template thao tác. Khi header, converter và cấu trúc response thống nhất, client có thể tiêu thụ API đúng cách và tiếp tục điều hướng theo hợp đồng mà server công bố.
# Media type là gì?

Khi một REST API trả về dữ liệu, máy khách cần biết cách diễn giải phần body của HTTP response. Một chuỗi JSON, một tài liệu XML và một hình ảnh PNG có cấu trúc khác nhau; máy khách không thể chỉ nhìn vào byte dữ liệu để luôn đoán đúng định dạng. HTTP dùng **media type** để công bố loại nội dung được gửi trong request hoặc response.

Trong Spring HATEOAS, media type còn cho biết representation hypermedia đang dùng quy ước nào. Cùng một đơn hàng có thể được biểu diễn bằng JSON thông thường, HAL JSON với các quan hệ `_links` và `_embedded`, hoặc HAL-FORMS với template mô tả hành động. Hiểu media type giúp thiết kế hợp đồng API rõ ràng và để máy khách chọn định dạng phù hợp.

## 1. Media type mô tả điều gì?

Media type là định danh cho một định dạng nội dung và cách diễn giải nội dung đó. Trong HTTP, nó thường xuất hiện ở header `Content-Type` hoặc `Accept`.

Một media type có cấu trúc tổng quát:

~~~text
type/subtype
~~~

Ví dụ:

| Media type | Nội dung thường biểu diễn |
|---|---|
| `application/json` | Dữ liệu JSON |
| `application/xml` | Dữ liệu XML |
| `text/plain` | Văn bản thuần |
| `text/html` | Tài liệu HTML |
| `image/png` | Hình ảnh PNG |
| `application/hal+json` | Representation hypermedia theo HAL, dùng cú pháp JSON |
| `application/prs.hal-forms+json` | Representation theo HAL-FORMS, dùng cú pháp JSON |

`type` nhóm các loại nội dung lớn như `application`, `text`, `image`, `audio` hoặc `video`. `subtype` xác định định dạng cụ thể trong nhóm đó.

Media type không phải tên file và cũng không phải phần mở rộng URL. Một response có thể được trả về từ `/orders/42` nhưng nội dung là HAL JSON; URL không cần kết thúc bằng `.json` hoặc `.hal`.

## 2. Type, subtype và structured syntax suffix

Trong `application/hal+json`:

- `application` là type.
- `hal+json` là subtype.
- Phần `+json` là structured syntax suffix, cho biết representation dùng cú pháp JSON.

Suffix giúp công cụ nhận biết cấu trúc cú pháp chung. Tuy nhiên, nó không làm mất ngữ nghĩa riêng của subtype. `application/json` và `application/hal+json` đều có thể được phân tích cú pháp như JSON, nhưng hợp đồng của chúng khác nhau.

Ví dụ JSON thông thường:

~~~json
{
  "id": 42,
  "status": "PAID"
}
~~~

Ví dụ HAL JSON:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "customer": {
      "href": "/customers/7"
    }
  }
}
~~~

Một JSON parser có thể đọc cả hai payload. Nhưng chỉ khi biết media type và quy ước HAL, máy khách mới hiểu `_links.self` là liên kết tới tài nguyên hiện tại và `_links.customer` là quan hệ tới tài nguyên khách hàng.

Vì vậy, không nên dùng `application/json` để thay thế tùy tiện cho một media type hypermedia chỉ vì cả hai đều có cú pháp JSON.

## 3. Parameters của media type

Media type có thể đi kèm parameters để bổ sung thông tin cho representation hoặc cách xử lý nội dung.

Ví dụ:

~~~http
Content-Type: application/json; charset=UTF-8
Accept: application/hal+json; profile="https://api.example.com/profiles/orders"
~~~

Phần đứng sau dấu chấm phẩy là parameter:

- `charset` mô tả bộ ký tự của nội dung văn bản trong những định dạng có sử dụng parameter này.
- `profile` có thể nhận diện một profile bổ sung cho representation, nếu media type và hợp đồng API định nghĩa cách dùng nó.

Parameter không tạo ra một media type hoàn toàn mới. `application/json; charset=UTF-8` vẫn là `application/json` với parameter đi kèm.

Khi so sánh media type, cần xem cả type, subtype và các parameter có ý nghĩa trong hợp đồng. Không nên tự giả định mọi parameter đều có thể bỏ qua.

## 4. Content-Type và Accept khác nhau thế nào?

Hai header thường bị nhầm lẫn:

- `Content-Type` mô tả định dạng của body đang được gửi.
- `Accept` liệt kê những media type mà bên gửi có thể nhận.

Ví dụ máy khách tạo đơn hàng bằng JSON nhưng muốn nhận lại representation HAL:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": 7,
  "shippingAddress": "12 Nguyen Hue"
}
~~~

Server có thể trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/hal+json
Location: /orders/42

{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  }
}
~~~

Ở đây:

1. `Content-Type: application/json` nói rằng request body là JSON thông thường.
2. `Accept: application/hal+json` nói rằng máy khách muốn response theo HAL.
3. `Content-Type: application/hal+json` trong response xác nhận server đã trả HAL JSON.

Request và response có thể dùng hai media type khác nhau. Đây là tình huống rất phổ biến trong API có hypermedia.

## 5. Content negotiation là gì?

**Content negotiation** là quá trình các bên chọn một representation phù hợp với khả năng và yêu cầu của nhau. Trong HTTP, máy khách thường gửi `Accept`; server chọn một media type mà endpoint có thể cung cấp.

Ví dụ máy khách chấp nhận HAL trước, JSON thông thường sau:

~~~http
GET /orders/42 HTTP/1.1
Accept: application/hal+json, application/json;q=0.8
~~~

Tham số `q` biểu thị mức ưu tiên tương đối:

- `q=1.0` là mức ưu tiên mặc định cao nhất.
- `q=0.8` có ưu tiên thấp hơn.
- `q=0` có nghĩa là không chấp nhận media type tương ứng.

Máy khách cũng có thể dùng wildcard:

~~~http
Accept: application/*, */*;q=0.5
~~~

`application/*` chấp nhận các subtype thuộc nhóm application; `*/*` chấp nhận mọi media type nếu không có quy tắc cụ thể hơn loại trừ nó.

Server có thể hỗ trợ nhiều representation cho cùng một tài nguyên. Khi đó, content negotiation giúp chọn định dạng mà máy khách yêu cầu thay vì buộc mọi client dùng chung một cấu trúc response.

## 6. Media type và REST representation

Một resource là khái niệm tài nguyên mà API cung cấp, ví dụ đơn hàng số 42. Representation là cách server mô tả tài nguyên đó trong một lần trao đổi HTTP.

Cùng resource có thể có nhiều representation:

| Resource | Media type | Đặc điểm |
|---|---|---|
| Order 42 | `application/json` | Các trường dữ liệu JSON |
| Order 42 | `application/hal+json` | Dữ liệu cùng `_links` và `_embedded` |
| Order 42 | `application/prs.hal-forms+json` | Dữ liệu HAL cùng template hành động |

Media type giúp máy khách biết cách diễn giải representation. Nó không nhất thiết thay đổi bản thân resource hoặc nghiệp vụ phía server.

Ví dụ, trạng thái đơn hàng vẫn là `PAID` dù server trả JSON thường hay HAL. Điều thay đổi là cách trạng thái đó được đóng gói và các khả năng hypermedia được công bố kèm theo.

## 7. Media type trong Spring HATEOAS

Spring HATEOAS cung cấp các media type để biểu diễn tài nguyên theo những quy ước hypermedia khác nhau.

| Media type | Hằng số Spring HATEOAS | Mục đích |
|---|---|---|
| HAL JSON | `MediaTypes.HAL_JSON` | Link và embedded resource theo HAL |
| HAL-FORMS JSON | `MediaTypes.HAL_FORMS_JSON` | HAL cùng template mô tả hành động |
| JSON thông thường | `MediaType.APPLICATION_JSON` | Dữ liệu JSON không mặc định có ngữ nghĩa HAL |

Các hằng số dạng chuỗi dùng trong annotation có hậu tố `_VALUE`, chẳng hạn `MediaTypes.HAL_JSON_VALUE` và `MediaTypes.HAL_FORMS_JSON_VALUE`.

HAL JSON sử dụng các trường đặc biệt như `_links` và `_embedded`. HAL-FORMS mở rộng cách biểu diễn để công bố các template trong `_templates`, giúp máy khách khám phá phương thức, target và metadata của input.

Không phải cứ response có trường `_links` là tự động trở thành HAL. Media type và hợp đồng representation cần thống nhất với cấu trúc được tuần tự hóa.

## 8. Cấu hình media type hypermedia

Với ứng dụng Spring Boot dùng starter Spring HATEOAS phù hợp, nhiều cấu hình hypermedia có thể được auto-configure. Khi tự cấu hình Spring HATEOAS, có thể bật hỗ trợ media type mong muốn bằng `@EnableHypermediaSupport`.

Ví dụ bật HAL:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {}
~~~

Nếu API cần cả HAL và HAL-FORMS, có thể đăng ký cả hai:

~~~java
@Configuration
@EnableHypermediaSupport(type = {
    HypermediaType.HAL,
    HypermediaType.HAL_FORMS
})
class HypermediaConfiguration {}
~~~

Cấu hình cụ thể phụ thuộc phiên bản Spring HATEOAS và cách ứng dụng khởi tạo message converter. Tránh đăng ký lặp cấu hình nếu Spring Boot đã tự cấu hình các converter cần thiết.

## 9. Khai báo media type trong controller

Spring MVC cho phép giới hạn media type được chấp nhận hoặc được tạo ra bằng `consumes` và `produces`.

- `consumes` giới hạn media type của request body.
- `produces` giới hạn media type của response.

Ví dụ endpoint nhận JSON và trả HAL:

~~~java
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaTypes.HAL_JSON_VALUE
    )
    public ResponseEntity<EntityModel<OrderDto>> create(
            @RequestBody CreateOrderRequest request) {

        Order order = orderService.create(request);

        EntityModel<OrderDto> model = orderAssembler.toModel(order);

        return ResponseEntity
            .created(model.getRequiredLink(IanaLinkRelations.SELF).toUri())
            .body(model);
    }
}
~~~

Trong ví dụ:

- `consumes` nói rằng endpoint nhận request body theo `application/json`.
- `produces` nói rằng response được công bố theo `application/hal+json`.
- `EntityModel` mang nội dung DTO cùng các link.
- Message converter phù hợp chịu trách nhiệm tuần tự hóa representation theo media type đã thương lượng.

Với endpoint GET không có request body, thường chỉ cần khai báo `produces`:

~~~java
@GetMapping(
    value = "/{id}",
    produces = MediaTypes.HAL_JSON_VALUE
)
public EntityModel<OrderDto> one(@PathVariable Long id) {
    return orderAssembler.toModel(orderService.findById(id));
}
~~~

## 10. Một endpoint hỗ trợ nhiều media type

Một tài nguyên có thể hỗ trợ nhiều định dạng. Ví dụ endpoint GET có thể trả HAL hoặc HAL-FORMS tùy theo `Accept`.

~~~java
@GetMapping(
    value = "/{id}",
    produces = {
        MediaTypes.HAL_JSON_VALUE,
        MediaTypes.HAL_FORMS_JSON_VALUE
    }
)
public EntityModel<OrderDto> one(@PathVariable Long id) {
    return orderAssembler.toModel(orderService.findById(id));
}
~~~

Cấu hình hypermedia cần hỗ trợ các media type được khai báo. Máy khách có thể chọn:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

hoặc:

~~~http
GET /orders/42
Accept: application/prs.hal-forms+json
~~~

Cùng một resource có thể được tuần tự hóa theo định dạng khác nhau. HAL-FORMS chỉ hữu ích khi representation có affordance/template phù hợp; nếu API không công bố hành động, response có thể không có `_templates` đáng kể.

Nếu API chỉ hỗ trợ một media type, hãy khai báo đúng media type đó. Đừng khai báo nhiều định dạng mà message converter hoặc representation thực tế không thể tạo ra.

## 11. consumes, produces và các lỗi HTTP thường gặp

Khi media type của request hoặc response không khớp hợp đồng endpoint, Spring MVC có thể trả về các lỗi HTTP sau:

| Tình huống | Status | Ý nghĩa |
|---|---|---|
| Request body gửi media type không nằm trong `consumes` | 415 Unsupported Media Type | Server không chấp nhận định dạng body được gửi |
| `Accept` không có định dạng nào endpoint có thể trả | 406 Not Acceptable | Server không thể tạo representation mà client yêu cầu |
| Body có media type hợp lệ nhưng nội dung sai cấu trúc hoặc không parse được | Thường là 400 Bad Request | Dữ liệu request không hợp lệ |
| Body parse được nhưng vi phạm validation | Thường là 400 Bad Request | Dữ liệu không đáp ứng điều kiện đầu vào |

Ví dụ endpoint chỉ nhận JSON:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Void> create(
        @RequestBody CreateOrderRequest request) {
    // Xử lý tạo đơn hàng.
    return ResponseEntity.accepted().build();
}
~~~

Nếu máy khách gửi `Content-Type: text/plain`, request không phù hợp với `consumes` và có thể nhận 415.

Nếu endpoint chỉ `produces = application/hal+json` nhưng máy khách yêu cầu duy nhất `application/xml`, server không thể đáp ứng Accept và có thể trả 406.

Không nên nhầm 415 với 406: 415 liên quan định dạng body được gửi; 406 liên quan định dạng response mà máy khách muốn nhận.

## 12. Media type, charset và content encoding

Media type mô tả loại representation. Một số header khác mô tả thuộc tính truyền tải:

| Header | Vai trò |
|---|---|
| `Content-Type` | Loại nội dung của body |
| `Accept` | Loại response mà client chấp nhận |
| `Content-Encoding` | Cách mã hóa/nén body, ví dụ gzip |
| `Accept-Encoding` | Các content encoding client chấp nhận |
| `Content-Language` | Ngôn ngữ của nội dung |
| `Accept-Language` | Ngôn ngữ client ưu tiên |

Ví dụ response có thể là HAL JSON và được nén gzip:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Content-Encoding: gzip
Vary: Accept, Accept-Encoding
~~~

Ở đây media type vẫn là HAL JSON. gzip chỉ thay đổi cách body được mã hóa khi truyền qua mạng.

Không nên dùng `Content-Type` để mô tả gzip, ngôn ngữ hoặc phiên bản API. Mỗi header có một trách nhiệm riêng.

## 13. Media type và cache

Nếu server trả nhiều representation tùy theo `Accept`, một cache cần phân biệt các response được tạo từ những lựa chọn khác nhau.

Ví dụ:

- Client A yêu cầu `application/hal+json`.
- Client B yêu cầu `application/prs.hal-forms+json`.

Nếu cache dùng chung response HAL cho request HAL-FORMS, client có thể nhận sai định dạng. Header `Vary: Accept` cho cache biết response phụ thuộc vào giá trị Accept.

Tương tự, nếu response còn phụ thuộc vào `Accept-Encoding`, có thể cần `Vary: Accept-Encoding`.

Việc dùng `Vary` và cache policy cần phù hợp với cách reverse proxy, CDN hoặc cache trung gian được cấu hình. Không nên giả định mọi cache tự hiểu các lựa chọn representation nếu server không công bố chúng.

## 14. Media type không thay thế versioning hoặc relation

Media type có thể tham gia vào chiến lược versioning của API, nhưng bản thân nó không tự giải quyết mọi vấn đề tương thích.

Ví dụ API có thể công bố profile hoặc media type chuyên biệt khi representation có hợp đồng khác biệt đáng kể. Tuy nhiên, không nên tạo media type mới cho mọi thay đổi nhỏ nếu các trường và relation có thể được mở rộng tương thích.

Cần phân biệt:

- **Media type:** cách diễn giải representation.
- **Relation:** ý nghĩa của một liên kết hypermedia, ví dụ `self`, `next` hoặc relation mở rộng.
- **URI:** địa chỉ định vị tài nguyên hoặc hành động.
- **Version:** quy ước quản lý thay đổi hợp đồng theo thời gian.
- **Profile:** mô tả thêm các ràng buộc hoặc ý nghĩa của representation trong một ngữ cảnh cụ thể.

Một API có thể giữ `application/hal+json` và bổ sung relation mới mà không cần tạo media type khác. Chỉ nên thay đổi media type khi cách diễn giải hoặc cấu trúc hợp đồng cần được phân biệt rõ.

## 15. Kiểm thử media type với MockMvc

Kiểm thử cần xác nhận cả định dạng response và hành vi content negotiation.

Kiểm tra response HAL:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaTypes.HAL_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_JSON
    ))
    .andExpect(jsonPath("$._links.self.href").exists());
~~~

Kiểm tra response HAL-FORMS:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaTypes.HAL_FORMS_JSON)
    )
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_FORMS_JSON
    ));
~~~

Kiểm tra endpoint từ chối media type request không được hỗ trợ:

~~~java
mockMvc.perform(
        post("/orders")
            .contentType(MediaType.TEXT_PLAIN)
            .content("not-json")
    )
    .andExpect(status().isUnsupportedMediaType());
~~~

Kiểm tra endpoint không hỗ trợ Accept:

~~~java
mockMvc.perform(
        get("/orders/42")
            .accept(MediaType.APPLICATION_XML)
    )
    .andExpect(status().isNotAcceptable());
~~~

Các trường hợp nên có trong bộ kiểm thử:

- Request `Accept: application/hal+json` nhận đúng Content-Type HAL.
- Request `Accept: application/prs.hal-forms+json` nhận đúng Content-Type HAL-FORMS.
- HAL response có `_links` và `_embedded` theo hợp đồng.
- HAL-FORMS response có template khi representation công bố affordance.
- `consumes` từ chối request body không được hỗ trợ.
- `produces` từ chối Accept không tương thích.
- Cache header `Vary` phù hợp khi response phụ thuộc Accept hoặc Accept-Encoding.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `application/json` cho representation HAL | Client không biết cần diễn giải `_links` theo HAL | Công bố `application/hal+json` |
| Nhầm `Accept` với `Content-Type` | Chọn sai định dạng request hoặc response | `Content-Type` mô tả body gửi; `Accept` chọn response |
| Nghĩ `+json` làm mọi subtype giống nhau | Mất ngữ nghĩa hypermedia | Phân biệt cú pháp JSON và semantics của media type |
| Khai báo `produces` nhưng thiếu converter phù hợp | Không tuần tự hóa được representation | Bật hỗ trợ media type và kiểm tra message converter |
| Khai báo `consumes` không khớp request | Client nhận 415 | Gửi đúng Content-Type hoặc điều chỉnh contract |
| Client yêu cầu media type không hỗ trợ | Client nhận 406 | Thương lượng một media type được endpoint hỗ trợ |
| Coi HAL và HAL-FORMS là cùng một định dạng | Client không nhận được template như mong đợi | Dùng đúng media type và serializer |
| Cache không phân biệt Accept | Có thể trả nhầm representation | Cấu hình `Vary: Accept` khi cần |
| Dùng media type như relation hoặc version | Hợp đồng khó hiểu và khó tiến hóa | Tách media type, relation, URI, profile và version |

## 17. Quy trình chọn media type cho REST API

Khi thiết kế một endpoint trong Spring HATEOAS, hãy đi theo trình tự:

1. Xác định representation mà máy khách cần nhận.
2. Chọn media type mô tả đúng định dạng và ngữ nghĩa representation.
3. Dùng `Content-Type` để mô tả body request hoặc response.
4. Dùng `Accept` để máy khách yêu cầu representation mong muốn.
5. Khai báo `consumes` cho request body và `produces` cho response nếu cần giới hạn rõ.
6. Cấu hình hypermedia support và message converter tương ứng.
7. Xử lý 406 và 415 theo đúng nguyên nhân không tương thích.
8. Xem xét `Vary` khi cache có nhiều representation theo header.
9. Kiểm thử media type, cấu trúc HAL/HAL-FORMS và content negotiation ở cấp HTTP.

Media type là một phần của hợp đồng HTTP: nó cho biết body được định dạng và diễn giải như thế nào. Trong Spring HATEOAS, chọn đúng media type giúp máy khách nhận ra representation HAL hoặc HAL-FORMS, khám phá liên kết và hành động theo đúng quy ước, đồng thời hỗ trợ API phục vụ nhiều loại client mà vẫn giữ cách biểu diễn tài nguyên nhất quán.

