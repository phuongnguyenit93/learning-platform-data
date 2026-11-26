# Kiểm thử media type

## Mục tiêu

Sau bài này, bạn có thể phân biệt media type của HTTP response, request body và link target; kiểm thử Spring HATEOAS trả đúng định dạng HAL hoặc HAL-FORMS theo header `Accept`; xác nhận server từ chối media type không được hỗ trợ bằng status phù hợp; và kiểm tra thuộc tính `type` của link trong HAL bằng MockMvc.

## 1. Vì sao cần kiểm thử media type?

Một response hypermedia có thể chứa dữ liệu, link và metadata. Client cần biết định dạng representation để đọc đúng cấu trúc và tìm các thành phần như `_links`, `_embedded` hoặc `_templates`.

Ví dụ cùng một tài nguyên đơn hàng có thể được trả về dưới dạng HAL:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

Hoặc HAL-FORMS nếu endpoint và converter hỗ trợ định dạng đó:

```http
HTTP/1.1 200 OK
Content-Type: application/prs.hal-forms+json
```

Hai response có thể cùng mô tả một đơn hàng, nhưng cấu trúc hypermedia và khả năng khám phá form khác nhau. Nếu client yêu cầu HAL mà server trả media type không tương thích, client có thể không giải mã được representation.

Kiểm thử media type giúp xác nhận:

- Server trả đúng định dạng mà client yêu cầu và endpoint hỗ trợ.
- Header `Content-Type` phản ánh representation thực tế.
- Request body chỉ được nhận khi media type phù hợp với hợp đồng.
- Link có thể công bố media type dự kiến của target.
- Những yêu cầu không được hỗ trợ nhận status HTTP rõ ràng như 406 hoặc 415.

Trong Spring HATEOAS, việc kiểm thử không dừng ở status 200. Cần xác nhận media type và cấu trúc hypermedia được serialize.

## 2. Phân biệt Accept, Content-Type và type của link

Ba giá trị thường xuất hiện trong cùng một API nhưng có ý nghĩa khác nhau:

| Giá trị | Nằm ở đâu | Ý nghĩa |
|---|---|---|
| `Accept` | Request header | Client cho biết các media type response mà nó có thể nhận |
| `Content-Type` | Request hoặc response header | Media type của phần body đang được gửi |
| `type` | Link metadata trong representation | Gợi ý media type của tài nguyên đích |

Ví dụ client yêu cầu HAL:

```http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
```

Server trả representation HAL:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

Trong representation, một link có thể cho biết target là PDF:

```json
{
  "_links": {
    "invoice": {
      "href": "/orders/42/invoice",
      "type": "application/pdf"
    }
  }
}
```

Ở ví dụ này:

- `Accept: application/hal+json` yêu cầu định dạng của response hiện tại.
- `Content-Type: application/hal+json` mô tả body response hiện tại.
- `type: application/pdf` mô tả media type dự kiến của target link `invoice`.

Thuộc tính `type` của link là metadata gợi ý cho client. Nó không thay thế việc kiểm tra `Content-Type` khi client thực sự gọi target, và không làm response hiện tại chuyển thành PDF.

## 3. Media type hypermedia trong Spring HATEOAS

Spring HATEOAS cung cấp các hằng số media type để tránh tự gõ chuỗi:

| Định dạng | Hằng số | Media type |
|---|---|---|
| HAL JSON | `MediaTypes.HAL_JSON` | `application/hal+json` |
| HAL-FORMS JSON | `MediaTypes.HAL_FORMS_JSON` | `application/prs.hal-forms+json` |

Ví dụ khai báo endpoint chỉ trả HAL:

```java
import java.util.UUID;

import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping(
        value = "/orders/{id}",
        produces = MediaTypes.HAL_JSON_VALUE
)
public OrderModel getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}
```

Thuộc tính `produces` tham gia vào quá trình chọn handler method theo header `Accept`. Khi client yêu cầu `application/hal+json`, Spring MVC có thể chọn mapping này và dùng message converter tương ứng để serialize representation.

Nếu ứng dụng chỉ công bố HAL, hãy ghi rõ điều đó trong hợp đồng và kiểm thử request có `Accept` không tương thích.

## 4. Cấu hình nhiều định dạng response

Một endpoint có thể hỗ trợ nhiều media type nếu ứng dụng đã đăng ký converter tương ứng và representation có thể được chuyển đổi sang từng định dạng.

Ví dụ mapping chấp nhận HAL và HAL-FORMS:

```java
@GetMapping(
        value = "/orders/{id}",
        produces = {
                MediaTypes.HAL_JSON_VALUE,
                MediaTypes.HAL_FORMS_JSON_VALUE
        }
)
public OrderModel getOrder(@PathVariable UUID id) {
    return assembler.toModel(orderService.getRequired(id));
}
```

Client có thể chọn định dạng bằng `Accept`:

```http
GET /orders/42 HTTP/1.1
Accept: application/hal+json
```

Hoặc:

```http
GET /orders/42 HTTP/1.1
Accept: application/prs.hal-forms+json
```

Với cấu hình Spring HATEOAS phù hợp, có thể đăng ký hỗ trợ các hypermedia type bằng `@EnableHypermediaSupport`:

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

Trong ứng dụng Spring Boot, một phần cấu hình converter có thể đã được auto-configure. Hãy kiểm tra cấu hình thực tế trước khi thêm cấu hình trùng lặp. Điều kiện quan trọng là endpoint mapping và message converter phải cùng hỗ trợ media type mà test yêu cầu.

Không nên khai báo `produces` một media type mà ứng dụng không có converter để ghi body. Mapping có thể được chọn nhưng response vẫn không serialize được như mong muốn.

## 5. Kiểm thử response HAL bằng MockMvc

MockMvc cho phép gửi request với header `Accept` và kiểm tra `Content-Type` cùng body mà không cần mở cổng HTTP thật.

Ví dụ test endpoint trả HAL:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderControllerMediaTypeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsHalWhenClientAcceptsHal() throws Exception {
        mockMvc.perform(get("/orders/{id}", "42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href")
                        .value(endsWith("/orders/42")));
    }
}
```

`contentTypeCompatibleWith(...)` kiểm tra media type tương thích, không yêu cầu header phải giống hệt từng ký tự. Cách này phù hợp khi response có thêm tham số như charset.

Với `@WebMvcTest`, cần mock service và import assembler hoặc các bean cấu hình mà controller sử dụng. Ví dụ trên tập trung vào assertion; fixture và `@MockBean` phụ thuộc cấu trúc ứng dụng.

Nên kiểm tra cả body HAL. Một response có `Content-Type` đúng nhưng thiếu `_links` hoặc serialize representation thành JSON thông thường vẫn chưa đáp ứng hợp đồng hypermedia.

## 6. Kiểm thử HAL-FORMS

Nếu endpoint hỗ trợ HAL-FORMS, test cần gửi đúng media type trong `Accept` và kiểm tra `Content-Type` tương ứng:

```java
@Test
void returnsHalFormsWhenClientRequestsHalForms() throws Exception {
    mockMvc.perform(get("/orders/{id}", "42")
                    .accept(MediaTypes.HAL_FORMS_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_FORMS_JSON));
}
```

Nếu representation có affordance tạo template, có thể kiểm tra `_templates`:

```java
.andExpect(jsonPath("$._templates").exists());
```

Không phải mọi representation HAL-FORMS đều bắt buộc có template. Chỉ thêm assertion `_templates` khi endpoint thực sự công bố affordance hoặc form theo hợp đồng.

Nếu client yêu cầu HAL-FORMS nhưng endpoint chỉ hỗ trợ HAL, test không nên kỳ vọng server tự chuyển đổi trong mọi cấu hình. Kết quả phụ thuộc mapping, converter và hypermedia configuration. Hãy định nghĩa rõ media type endpoint hỗ trợ rồi kiểm thử theo cấu hình đó.

## 7. Kiểm thử Accept không được hỗ trợ

Khi endpoint chỉ hỗ trợ HAL mà client yêu cầu XML, Spring MVC thường trả `406 Not Acceptable` vì không có representation phù hợp với `Accept`.

```java
@Test
void rejectsUnsupportedAcceptHeader() throws Exception {
    mockMvc.perform(get("/orders/{id}", "42")
                    .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
}
```

Test này giả định mapping có `produces = MediaTypes.HAL_JSON_VALUE` và ứng dụng không đăng ký XML representation cho endpoint. Nếu ứng dụng có converter hoặc mapping khác hỗ trợ XML, cần điều chỉnh fixture để kiểm tra đúng hợp đồng.

Không nên nhầm 406 với 415:

- 406: client yêu cầu response media type mà server không thể cung cấp.
- 415: server không chấp nhận media type của request body.

Đây là hai lỗi ở hai hướng khác nhau của content negotiation.

## 8. Kiểm thử Content-Type của request body

Với endpoint nhận JSON, khai báo `consumes` để xác định định dạng request body:

```java
import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
        value = "/orders",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaTypes.HAL_JSON_VALUE
)
public ResponseEntity<OrderModel> createOrder(
        @Valid @RequestBody CreateOrderRequest request) {
    Order created = orderService.create(request);
    OrderModel model = assembler.toModel(created);
    URI location = URI.create(
            model.getRequiredLink(IanaLinkRelations.SELF).getHref()
    );

    return ResponseEntity.created(location).body(model);
}
```

Request hợp lệ gửi JSON:

```java
@Test
void acceptsJsonRequestBody() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaTypes.HAL_JSON)
                    .content("""
                            {
                              "customerId": "customer-7",
                              "note": "Deliver after 5 PM"
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(header().exists(HttpHeaders.LOCATION));
}
```

Request gửi media type không được hỗ trợ:

```java
@Test
void rejectsUnsupportedRequestContentType() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaTypes.HAL_JSON)
                    .content("customer-7"))
            .andExpect(status().isUnsupportedMediaType());
}
```

Khi `consumes` chỉ nhận JSON, request `text/plain` không khớp mapping và thường bị từ chối bằng 415. Test này xác nhận hợp đồng request độc lập với định dạng response được yêu cầu qua `Accept`.

## 9. Kiểm thử thuộc tính type của link

Trong Spring HATEOAS, `Link` có thể công bố media type dự kiến của tài nguyên đích bằng `withType(...)`.

Ví dụ một đơn hàng có link đến hóa đơn PDF:

```java
import org.springframework.hateoas.Link;
import org.springframework.http.MediaType;

Link invoiceLink = Link.of("/orders/42/invoice")
        .withRel("invoice")
        .withType(MediaType.APPLICATION_PDF_VALUE);
```

Representation HAL có thể serialize metadata đó:

```json
{
  "_links": {
    "invoice": {
      "href": "/orders/42/invoice",
      "type": "application/pdf"
    }
  }
}
```

Test xác nhận link có đúng relation, href và type:

```java
@Test
void exposesTargetMediaTypeOnInvoiceLink() throws Exception {
    mockMvc.perform(get("/orders/{id}", "42")
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.invoice.href")
                    .value(endsWith("/orders/42/invoice")))
            .andExpect(jsonPath("$._links.invoice.type")
                    .value(MediaType.APPLICATION_PDF_VALUE));
}
```

Assertion này kiểm tra metadata của link trong representation HAL. Nó không chứng minh endpoint hóa đơn thực sự trả PDF. Muốn kiểm thử target, cần gọi href đó trong một test riêng và xác nhận response `Content-Type: application/pdf`.

Ví dụ kiểm tra endpoint target:

```java
mockMvc.perform(get("/orders/{id}/invoice", "42")
                .accept(MediaType.APPLICATION_PDF))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PDF));
```

Nếu target hỗ trợ nhiều định dạng, hãy kiểm tra negotiation của target riêng. Giá trị `type` trên link là gợi ý giúp client chọn cách xử lý; response thực tế vẫn là nguồn xác nhận cuối cùng.

## 10. Kiểm tra media type khi có nhiều link

Một representation có thể chứa nhiều link đến các loại tài nguyên khác nhau:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42",
      "type": "application/hal+json"
    },
    "invoice": {
      "href": "/orders/42/invoice",
      "type": "application/pdf"
    },
    "events": {
      "href": "/orders/42/events",
      "type": "application/stream+json"
    }
  }
}
```

Client có thể dùng `type` để quyết định bộ xử lý phù hợp trước khi theo link. Tuy nhiên, không nên mặc định mọi link đều phải có `type`. Nhiều link chỉ trỏ đến tài nguyên hypermedia cùng media type hoặc không cần công bố hint.

Trong test, kiểm tra `type` cho các link mà hợp đồng yêu cầu:

```java
.andExpect(jsonPath("$._links.invoice.type")
        .value(MediaType.APPLICATION_PDF_VALUE))
.andExpect(jsonPath("$._links.events.type")
        .value("application/stream+json"));
```

Đừng kiểm tra thứ tự các link trong JSON. Hãy truy cập bằng relation vì thứ tự serialize không phải một phần ngữ nghĩa của hypermedia.

## 11. Kiểm thử media type có tham số

Một số response có thể trả thêm tham số trong `Content-Type`, ví dụ charset. So sánh chuỗi tuyệt đối có thể khiến test thất bại dù media type chính tương thích.

Ưu tiên:

```java
.andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HAL_JSON));
```

Thay vì so sánh header bằng chuỗi cứng:

```java
.andExpect(header().string(
        HttpHeaders.CONTENT_TYPE,
        "application/hal+json"
));
```

Nếu hợp đồng yêu cầu chính xác một tham số cụ thể, hãy kiểm tra tham số đó riêng. Còn nếu chỉ cần bảo đảm client nhận HAL, assertion tương thích media type rõ ý định hơn.

Có thể dùng `header().string(...)` khi cần kiểm tra một giá trị header cụ thể, nhưng nên tránh phụ thuộc vào cách framework định dạng tham số không liên quan đến hợp đồng.

## 12. Kiểm thử fallback và wildcard Accept

Client có thể gửi `Accept: */*` khi không giới hạn định dạng response. Nếu endpoint chỉ hỗ trợ HAL, server có thể chọn HAL làm representation phù hợp.

```java
@Test
void returnsDefaultSupportedRepresentationForWildcardAccept()
        throws Exception {

    mockMvc.perform(get("/orders/{id}", "42")
                    .accept(MediaType.ALL))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON));
}
```

Kết quả mặc định phụ thuộc mapping, converter và cấu hình content negotiation của ứng dụng. Nếu ứng dụng hỗ trợ nhiều định dạng mà không có thứ tự ưu tiên rõ ràng, hãy cấu hình hoặc kiểm thử lựa chọn mặc định thay vì dựa vào thứ tự đăng ký converter.

Nếu client gửi nhiều giá trị `Accept` cùng quality factor, server sẽ chọn representation theo quy tắc negotiation và khả năng hỗ trợ. Không nên viết test giả định thứ tự trong header luôn quyết định kết quả.

## 13. Một bộ test media type đầy đủ

Với một API Spring HATEOAS, nên chia test theo các hợp đồng độc lập:

| Trường hợp | Request | Assertion chính |
|---|---|---|
| HAL response | `Accept: application/hal+json` | 200, Content-Type HAL, có `_links` |
| HAL-FORMS response | `Accept: application/prs.hal-forms+json` | 200, Content-Type HAL-FORMS |
| Unsupported Accept | `Accept: application/xml` | 406 nếu endpoint không hỗ trợ XML |
| JSON request | `Content-Type: application/json` | Request được bind và xử lý |
| Unsupported request body | `Content-Type: text/plain` | 415 khi endpoint chỉ nhận JSON |
| Link target hint | Link có `type=application/pdf` | JSON HAL chứa đúng `type` |
| Target response | Gọi link PDF | Content-Type của target là PDF |
| Wildcard Accept | `Accept: */*` | Representation mặc định theo cấu hình |

Một bộ test có thể được chia thành các class theo controller hoặc nhóm media type. Mỗi test nên kiểm tra một hành vi chính để khi lỗi xảy ra, nguyên nhân dễ xác định.

## 14. Những lỗi thường gặp

**Chỉ kiểm tra status 200.** Response có thể trả JSON thông thường thay vì HAL. Kiểm tra `Content-Type` và cấu trúc `_links`.

**Nhầm `Accept` với `Content-Type`.** Một header mô tả định dạng response client chấp nhận; header còn lại mô tả body đang gửi. Test riêng hai hướng.

**Cho rằng link `type` là Content-Type của response hiện tại.** `type` mô tả target link. Kiểm tra response target bằng request riêng.

**Khai báo `produces` nhưng thiếu converter.** Mapping có thể nhận request nhưng representation không được serialize đúng. Kiểm tra cấu hình hypermedia và message converter.

**Kỳ vọng 415 khi `Accept` không phù hợp.** Trường hợp này thường là 406. 415 dành cho media type của request body không được endpoint chấp nhận.

**Kỳ vọng 406 khi request body sai định dạng.** Nếu `Content-Type` không khớp `consumes`, server thường trả 415.

**So sánh Content-Type bằng chuỗi cứng.** Tham số charset có thể làm test thất bại không cần thiết. Dùng `contentTypeCompatibleWith` khi chỉ cần so sánh media type.

**Giả định HAL-FORMS luôn có `_templates`.** Template chỉ xuất hiện khi representation công bố affordance phù hợp. Chỉ kiểm tra khi endpoint thực sự cung cấp form.

**Cho rằng `type` trên link bảo đảm target trả đúng định dạng.** Đây là metadata gợi ý. Gọi target và kiểm tra response thực tế.

## 15. Nguyên tắc thiết kế

- Dùng hằng số `MediaTypes` của Spring HATEOAS thay vì tự gõ media type hypermedia.
- Xác định rõ `produces` cho response và `consumes` cho request body.
- Kiểm tra `Accept` và response `Content-Type` trong MockMvc.
- Kiểm tra cấu trúc HAL hoặc HAL-FORMS ngoài status code.
- Dùng 406 cho response media type không được hỗ trợ và 415 cho request body media type không được chấp nhận.
- Dùng `contentTypeCompatibleWith` khi không cần so sánh tham số header.
- Kiểm tra `Link.type` riêng với `Content-Type` của target.
- Gọi target link trong test riêng nếu cần xác nhận media type thực tế.
- Chỉ kiểm tra `_templates` khi API thực sự công bố affordance.
- Kiểm thử wildcard hoặc nhiều giá trị `Accept` theo cấu hình negotiation của ứng dụng.

## Kết luận

Kiểm thử media type bảo vệ khả năng trao đổi representation giữa client và server. Với Spring HATEOAS, hãy kiểm tra media type response như HAL hoặc HAL-FORMS, media type request body qua `Content-Type`, và media type hint của target qua thuộc tính `type` trên link. MockMvc có thể xác nhận negotiation, cấu trúc hypermedia và các lỗi 406/415. Khi cần xác nhận target thực sự trả định dạng đã công bố, hãy gọi target và kiểm tra `Content-Type` của response đó riêng.

## Tài liệu tham khảo

- [Spring HATEOAS Reference – Hypermedia formats](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes)
- [Spring HATEOAS API – MediaTypes](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring Framework Reference – Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework Reference – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [RFC 9110 – HTTP Semantics, Content Negotiation](https://www.rfc-editor.org/rfc/rfc9110.html#section-12)

