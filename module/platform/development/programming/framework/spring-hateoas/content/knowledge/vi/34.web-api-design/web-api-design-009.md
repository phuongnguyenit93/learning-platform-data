# Tài liệu API có hypermedia

Một API HATEOAS tự mô tả một phần cách client khám phá và sử dụng tài nguyên thông qua link, relation và affordance. Tuy nhiên, response có link không có nghĩa API đã có tài liệu đầy đủ cho con người. Đội tích hợp vẫn cần biết ý nghĩa của từng relation, điều kiện link xuất hiện, dữ liệu đầu vào, media type, lỗi có thể gặp và quy tắc bảo mật.

Spring HATEOAS cung cấp các abstraction để tạo representation và affordance; HAL công bố link trong `_links`; HAL-FORMS có thể mô tả template cùng property đầu vào; ALPS mô tả semantics của resource và các state transition. Spring Data REST có thể công bố profile/ALPS tự động. Spring REST Docs bổ sung tài liệu cho con người bằng cách tạo snippet từ các HTTP test thực tế.

Bài học này thuộc chương **Web API design** trong module **SPRING_HATEOAS**, tập trung vào cách thiết kế tài liệu cho API có hypermedia, kết hợp runtime discoverability với tài liệu dành cho nhà phát triển, mô tả relation và affordance, công bố profile ALPS và tạo link documentation có kiểm thử bằng Spring REST Docs.

Sau bài học, bạn có thể:

- Phân biệt hypermedia runtime metadata với tài liệu API dành cho con người.
- Xây dựng bảng mô tả relation và điều kiện xuất hiện của link.
- Sử dụng `profile` link và ALPS để mô tả semantics của resource.
- Phân biệt vai trò của HAL, HAL-FORMS và ALPS.
- Mô tả affordance, HTTP method, input/output và validation.
- Tạo snippet link bằng Spring REST Docs và MockMvc.
- Dùng `optional()`, `ignored()` và `relaxedLinks()` đúng ngữ cảnh.
- Kiểm thử tài liệu đồng bộ với response thực tế.
- Tổ chức tài liệu về authentication, authorization, lỗi và deprecation.

## 1. Hypermedia không thay thế toàn bộ tài liệu API

Một response HAL có thể công bố các link:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": { "href": "/orders/42" },
    "customer": { "href": "/customers/7" },
    "cancel": { "href": "/orders/42/cancellation" }
  }
}
```

Client có thể khám phá URI bằng relation `self`, `customer` và `cancel`. Nhưng chỉ nhìn response này, một nhà phát triển tích hợp vẫn chưa biết:

- `customer` trả về loại representation nào và cần quyền gì.
- `cancel` dùng `POST`, `DELETE` hay một method khác.
- Request hủy có cần body, media type hoặc trường `reason` không.
- Link `cancel` chỉ xuất hiện khi đơn hàng đang `PENDING` hay trong mọi trạng thái.
- Server phản hồi thế nào nếu đơn hàng đã được giao hoặc người dùng không có quyền hủy.
- Client cần xử lý những status code và lỗi nghiệp vụ nào.

Vì vậy, nên xem tài liệu API có hypermedia gồm hai lớp bổ trợ:

| Lớp | Mục đích | Ví dụ |
|---|---|---|
| Runtime hypermedia | Cho client biết có thể điều hướng hoặc thực hiện thao tác nào tại thời điểm nhận response | `_links`, relation, URI template, affordance, HAL-FORMS template. |
| Tài liệu dành cho con người | Giải thích semantics, điều kiện, payload, lỗi, bảo mật, ví dụ và quy trình tích hợp | ALPS profile, Spring REST Docs snippets, guide và bảng hợp đồng. |

Hypermedia giúp client giảm phụ thuộc vào URL hard-code. Tài liệu dành cho con người giúp đội tích hợp hiểu hợp đồng, thiết kế client và xử lý các trường hợp mà response runtime không thể giải thích đầy đủ.

## 2. Những nội dung cần có trong tài liệu hypermedia

Với mỗi resource, tài liệu nên trả lời các câu hỏi sau:

1. **Resource là gì?** Nêu mục đích, danh tính, media type và cách client khám phá resource.
2. **Representation có gì?** Mô tả field quan trọng, kiểu dữ liệu, ý nghĩa và các field có thể vắng mặt.
3. **Có relation nào?** Ghi tên relation, ý nghĩa, đích, điều kiện xuất hiện và link có bắt buộc hay không.
4. **Có affordance nào?** Mô tả method, target, input, output, content type và điều kiện thực hiện.
5. **Lỗi nào có thể xảy ra?** Nêu status code, mã lỗi nghiệp vụ và cách client khôi phục.
6. **Quyền nào cần có?** Mô tả authentication, authorization và những giới hạn dữ liệu.
7. **Thay đổi hợp đồng ra sao?** Ghi nhận deprecation, profile, phiên bản và quy tắc tương thích.

Một bảng relation nên có ít nhất các cột sau:

| Relation | Ý nghĩa | Khi nào xuất hiện | Đích/ghi chú |
|---|---|---|---|
| `self` | URI của đơn hàng hiện tại | Luôn có trên item representation | Dùng để tải lại resource. |
| `customer` | Khách hàng liên quan | Khi đơn hàng có khách hàng | GET resource khách hàng. |
| `cancel` | Điểm truy cập thao tác hủy | Khi đơn hàng có thể hủy và người dùng được phép thấy thao tác | Có thể đi kèm affordance POST với input `reason`. |
| `invoice` | Hóa đơn của đơn hàng | Sau khi hóa đơn được phát hành | GET tài liệu hóa đơn; có thể có `type=application/pdf`. |

Relation mô tả semantics ổn định; `href` là URI cụ thể. Đừng đưa URL đầy đủ vào tài liệu như một giá trị client phải ghép lại. Hãy chỉ rõ client cần theo relation nào và dùng `href` từ response.

## 3. Tài liệu relation và link

Relation cần được mô tả theo ngữ nghĩa, không theo tên method hoặc cấu trúc controller. Ví dụ `cancel` có nghĩa là điểm truy cập để hủy đơn hàng; client không cần biết controller tên `OrderCancellationController`.

Khi tài liệu một relation, hãy mô tả:

- Tên relation và URI định danh nếu là extension relation.
- Ý nghĩa và resource hoặc hành động mà nó đại diện.
- Điều kiện server công bố link.
- HTTP method và media type nếu link gắn với affordance.
- Dữ liệu đầu vào và kết quả dự kiến.
- Link có thể vắng mặt trong trạng thái nào.
- Link có thể bị deprecated hay không và tài liệu thay thế ở đâu.

Ví dụ mô tả relation `cancel`:

| Thuộc tính | Nội dung |
|---|---|
| Relation | `https://api.example.com/rels/cancel` hoặc CURIE `acme:cancel` trong HAL. |
| Ý nghĩa | Bắt đầu yêu cầu hủy đơn hàng. |
| Điều kiện | Đơn hàng ở trạng thái `PENDING` và người dùng có quyền hủy. |
| Method | `POST` theo affordance được công bố. |
| Input | `application/json`, trường `reason` bắt buộc. |
| Thành công | Trả representation đơn hàng với trạng thái mới. |
| Lỗi | `409 Conflict` nếu trạng thái không còn cho phép hủy; `403 Forbidden` nếu thiếu quyền. |

Nếu relation là extension relation, dùng URI ổn định và tài liệu hóa semantics tại URI đó hoặc trong profile. Nếu dùng CURIE, ghi rõ prefix được mở rộng thành URI nào. Không đổi relation chỉ vì URL hoặc tên class Java thay đổi.

## 4. HAL công bố link; ALPS mô tả semantics

HAL mô tả cấu trúc representation và các link điều hướng. Một HAL resource thường có `_links` và có thể có `_embedded`. Tuy nhiên, một link HAL đơn giản không tự mô tả đầy đủ method, schema request hoặc validation.

ALPS (*Application-Level Profile Semantics*) là định dạng metadata dùng để mô tả semantics của resource theo cách độc lập với media type biểu diễn. Một ALPS profile có thể mô tả:

- Các thuộc tính mang ý nghĩa trong representation.
- Các relation hoặc descriptor liên quan.
- Các state transition mà API hỗ trợ.
- Kiểu transition như `SAFE`, `IDEMPOTENT`, `UNSAFE`.
- Liên kết giữa transition và resource type bằng `rt`.
- Tài liệu giải thích bằng descriptor `doc`.

ALPS không thay thế HAL. HAL là representation mà client đọc để điều hướng; ALPS là profile mô tả semantics của representation và các thao tác.

## 5. Khám phá profile link trong Spring Data REST

Spring Data REST cung cấp ALPS document cho các repository được export. Ở root resource, client có thể thấy link `profile`:

```json
{
  "_links": {
    "orders": { "href": "https://api.example.com/orders" },
    "customers": { "href": "https://api.example.com/customers" },
    "profile": { "href": "https://api.example.com/profile" }
  }
}
```

Client theo `/profile` để khám phá profile của từng resource:

```json
{
  "_links": {
    "self": { "href": "https://api.example.com/profile" },
    "orders": { "href": "https://api.example.com/profile/orders" },
    "customers": { "href": "https://api.example.com/profile/customers" }
  }
}
```

Sau đó client theo link `orders` để lấy ALPS metadata cho resource đơn hàng. Collection resource cũng có thể công bố link `profile` trỏ tới profile tương ứng.

Ví dụ request:

```http
GET /profile/orders HTTP/1.1
Accept: application/alps+json
```

Response có media type `application/alps+json`, khác với `application/hal+json`. Root `profile` link là một entry duy nhất; `/profile` cung cấp các link riêng cho từng resource type.

## 6. Đọc ALPS descriptor

Một ALPS document có thể mô tả representation và các transition. Ví dụ rút gọn:

```json
{
  "version": "1.0",
  "descriptor": [
    {
      "id": "order-representation",
      "descriptor": [
        { "name": "status", "type": "SEMANTIC" },
        { "name": "total", "type": "SEMANTIC" },
        { "name": "customer", "type": "SAFE", "rt": "#customer-representation" }
      ]
    },
    {
      "id": "get-order",
      "name": "order",
      "type": "SAFE",
      "rt": "#order-representation"
    },
    {
      "id": "cancel-order",
      "name": "cancel",
      "type": "UNSAFE",
      "rt": "#order-representation"
    }
  ]
}
```

Các type thường gặp:

| ALPS type | Ý nghĩa | Ví dụ thao tác |
|---|---|---|
| `SEMANTIC` | Thuộc tính hoặc phần tử ngữ nghĩa trong representation | `status`, `total`, `customerId`. |
| `SAFE` | Transition an toàn, không làm thay đổi trạng thái server | `GET`, `HEAD`. |
| `IDEMPOTENT` | Transition có thể thay đổi trạng thái nhưng lặp lại cùng request có hiệu ứng tương đương | `PUT`, `DELETE`. |
| `UNSAFE` | Transition không an toàn và không đảm bảo idempotent | `POST` tạo yêu cầu hủy hoặc tạo thanh toán. |

`id` định danh descriptor; `name` nêu tên semantics hoặc transition; `type` mô tả loại descriptor; `rt` tham chiếu resource type mà transition trả về hoặc liên quan tới. `descriptor` lồng nhau có thể mô tả các thuộc tính hoặc lựa chọn của một transition. `doc` cung cấp thông tin giải thích cho descriptor.

ALPS là metadata ngữ nghĩa, không phải schema validation đầy đủ. Đừng suy ra mọi ràng buộc kiểu, giới hạn độ dài hoặc quy tắc bảo mật chỉ từ descriptor. Hãy bổ sung tài liệu payload và lỗi tương ứng.

## 7. Tạo ALPS profile bằng Spring HATEOAS

Spring HATEOAS cung cấp kiểu `Alps` và builder để tạo ALPS document. Không cần kích hoạt một hypermedia type riêng chỉ để trả `Alps`; controller MVC hoặc WebFlux có thể trả kiểu này với media type `application/alps+json`.

Ví dụ khung controller:

```java
import java.util.List;

import org.springframework.hateoas.mediatype.alps.Alps;
import org.springframework.hateoas.mediatype.alps.Descriptor;
import org.springframework.hateoas.mediatype.alps.Type;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderProfileController {

    @GetMapping(value = "/profiles/orders", produces = "application/alps+json")
    Alps orderProfile() {
        return Alps.alps()
                .descriptor(List.of(
                        Descriptor.builder()
                                .id("order-representation")
                                .descriptor(List.of(
                                        Descriptor.builder()
                                                .id("order-status")
                                                .name("status")
                                                .type(Type.SEMANTIC)
                                                .build(),
                                        Descriptor.builder()
                                                .id("total")
                                                .name("total")
                                                .type(Type.SEMANTIC)
                                                .build()))
                                .build(),
                        Descriptor.builder()
                                .id("get-order")
                                .name("order")
                                .type(Type.SAFE)
                                .rt("#order-representation")
                                .build()))
                .build();
    }
}
```

Ví dụ minh họa cách ghép descriptor; các kiểu `Descriptor` và `Type` thuộc API ALPS của Spring HATEOAS và cần import từ package `org.springframework.hateoas.mediatype.alps`. Với profile lớn, nên tách hàm tạo descriptor và kiểm thử JSON output. Có thể thêm `doc` và `ext` để liên kết tới tài liệu giải thích hoặc semantics mở rộng.

Nếu dùng Spring Data REST, framework đã cung cấp profile cho repository được export. Chỉ tự tạo profile controller khi cần metadata riêng, hoặc khi API không dựa trên repository exporter.

## 8. HAL-FORMS mô tả form và dữ liệu đầu vào

ALPS mô tả semantics và transition ở mức profile. HAL-FORMS mô tả chi tiết hơn cách thực hiện một transition bằng `_templates`, bao gồm:

- `title`: nhãn của thao tác.
- `method`: HTTP method.
- `target`: URI nhận request.
- `contentType`: media type của request body.
- `properties`: danh sách field đầu vào.
- `required`, `readOnly`, `type`, `value`, `options` và constraints.

Ví dụ:

```json
{
  "_links": {
    "self": { "href": "/orders/42" }
  },
  "_templates": {
    "cancelOrder": {
      "title": "Hủy đơn hàng",
      "method": "POST",
      "target": "/orders/42/cancellation",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "prompt": "Lý do hủy",
          "type": "text",
          "required": true,
          "maxLength": 500
        }
      ]
    }
  }
}
```

Client có thể tạo form từ template thay vì đoán method và request body. HAL-FORMS vẫn không thay thế tài liệu nghiệp vụ: tài liệu nên giải thích khi nào được hủy, ý nghĩa của `reason`, lỗi có thể gặp và trạng thái mới sau khi hủy.

## 9. Mô tả affordance bằng Spring HATEOAS

Spring HATEOAS cho phép gắn nhiều affordance vào một link. Ví dụ một self link có thể liên quan tới `GET`, `PUT` và `PATCH`:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@GetMapping("/orders/{id}")
EntityModel<Order> one(@PathVariable Long id) {
    Link self = linkTo(methodOn(OrderController.class).one(id)).withSelfRel();

    return EntityModel.of(orderService.findById(id),
            self.andAffordance(afford(methodOn(OrderController.class).update(null, id)))
                .andAffordance(afford(methodOn(OrderController.class).patch(null, id))));
}
```

Đây là phần thân của một method controller; ví dụ giả định `orderService` đã được inject và `update(...)`, `patch(...)` được khai báo trong cùng controller với `@PutMapping` và `@PatchMapping`. Các method này cần request body và response type rõ ràng. Spring HATEOAS phân tích metadata của controller để media type cụ thể có thể biểu diễn affordance.

Affordance là mô tả khả năng của link. Nó không tự động tạo endpoint hoặc đảm bảo người dùng có quyền thực hiện. Endpoint vẫn phải xác thực, phân quyền và kiểm tra trạng thái domain khi nhận request.

## 10. Tạo tài liệu link có kiểm thử bằng Spring REST Docs

Spring REST Docs tạo snippet tài liệu từ request/response thực tế của test. Với hypermedia, `links(...)` và `linkWithRel(...)` tạo bảng mô tả link trong response. Khi response dùng `application/hal+json`, REST Docs tự nhận diện cấu trúc `_links`.

Ví dụ với MockMvc:

Trong module test, thêm `spring-restdocs-mockmvc` với phiên bản tương thích với Spring REST Docs đang dùng. Nếu dự án dùng Spring Boot dependency management, để BOM quản lý phiên bản; nếu không, khai báo phiên bản Spring REST Docs đồng bộ cho các artifact.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class OrderApiDocumentationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsOrderLinks() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andDo(document("orders/get-order",
                        links(
                                linkWithRel("self").description("URI của đơn hàng hiện tại"),
                                linkWithRel("customer").description("Khách hàng sở hữu đơn hàng"),
                                linkWithRel("cancel").description("Điểm truy cập yêu cầu hủy đơn hàng").optional()
                        )));
    }
}
```

Test cần có fixture để response `/orders/42` chứa các link `self` và `customer`; link `cancel` có thể vắng mặt nên descriptor được đánh dấu `optional()`. Snippet tạo ra thường có tên `links.adoc` trong thư mục `orders/get-order` dưới output directory.

Nếu một link có `title`, có thể bỏ description trong descriptor để Spring REST Docs dùng title. Nếu cả description và title đều không có, việc tạo snippet sẽ thất bại.

## 11. REST Docs giúp phát hiện tài liệu lệch với API

Mặc định, `links(...)` kiểm tra hai chiều:

- Response có link nhưng không có descriptor tương ứng: test thất bại.
- Descriptor bắt buộc nhưng response không có link: test thất bại.

Đây là cơ chế hữu ích để phát hiện API thêm hoặc xóa relation mà tài liệu chưa cập nhật. Với relation xuất hiện theo trạng thái, có thể:

- Dùng `.optional()` nếu link có thể vắng mặt trong scenario test.
- Dùng `.ignored()` cho link chung không cần lặp lại trong mọi trang tài liệu.
- Dùng `relaxedLinks(...)` nếu snippet chỉ tập trung vào một tập link và chấp nhận các link khác trong response.

Ví dụ bỏ qua link phổ biến `self` và `curies`:

```java
links(
        linkWithRel("self").ignored().optional(),
        linkWithRel("curies").ignored(),
        linkWithRel("customer").description("Khách hàng của đơn hàng"),
        linkWithRel("cancel").description("Yêu cầu hủy đơn hàng").optional()
)
```

Nên tài liệu hóa link chung một lần trong phần tổng quan, sau đó bỏ qua chúng ở các snippet chi tiết. Tránh dùng `relaxedLinks` cho toàn bộ tài liệu nếu mục tiêu là phát hiện link mới chưa được giải thích.

## 12. Chọn LinkExtractor phù hợp

Spring REST Docs hiểu hai định dạng link mặc định:

| Định dạng | Vị trí link | Cách trích xuất |
|---|---|---|
| HAL | Map `_links` | Tự nhận diện khi `Content-Type` tương thích `application/hal+json`; có thể chỉ định `halLinks()`. |
| Atom | Array `links` | Tự nhận diện theo content type tương ứng; có thể chỉ định `atomLinks()`. |

Nếu response dùng cấu trúc link khác, có thể truyền `LinkExtractor` tùy chỉnh vào `links(...)`. Không nên giả định REST Docs sẽ hiểu mọi định dạng hypermedia chỉ bằng cách nhìn tên field.

Ví dụ khi response dùng content type riêng nhưng payload theo HAL:

```java
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.halLinks;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.linkWithRel;
import static org.springframework.restdocs.hypermedia.HypermediaDocumentation.links;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

document("orders/get-order",
        links(halLinks(),
                linkWithRel("self").description("Đơn hàng hiện tại"),
                linkWithRel("customer").description("Khách hàng liên quan")));
```

Nếu API sử dụng media type riêng, hãy kiểm thử `LinkExtractor` trên response thực tế trước khi tin rằng snippet đã mô tả đủ relation.

## 13. Kết hợp link snippets với payload documentation

Tài liệu API không chỉ có link. Spring REST Docs còn có thể tạo snippet cho request fields, response fields, path parameters, query parameters, request/response parts và HTTP headers.

Với một endpoint hủy đơn hàng, tài liệu nên có:

- Link snippet của resource đơn hàng để giải thích relation `cancel`.
- Request fields để giải thích `reason` và validation.
- Response fields hoặc response body snippet để mô tả trạng thái mới.
- Path/query parameter snippet nếu endpoint có tham số.
- Header snippet để giải thích media type và authentication.
- Error response snippets cho `400`, `403`, `404`, `409`.

Các snippet có thể được include vào một trang AsciiDoc tổng hợp:

```adoc
= Order API

== Đọc đơn hàng

include::{snippets}/orders/get-order/http-request.adoc[]
include::{snippets}/orders/get-order/http-response.adoc[]
include::{snippets}/orders/get-order/links.adoc[]

== Hủy đơn hàng

include::{snippets}/orders/cancel-order/http-request.adoc[]
include::{snippets}/orders/cancel-order/request-fields.adoc[]
include::{snippets}/orders/cancel-order/http-response.adoc[]
```

Đường dẫn snippet phụ thuộc identifier truyền vào `document(...)` và output directory của Spring REST Docs. Hãy include đúng tên snippet được build sinh ra.

## 14. Tài liệu lỗi và bảo mật

Hypermedia không thay thế tài liệu về lỗi hoặc bảo mật. Với mỗi thao tác, nên ghi rõ:

| Chủ đề | Nội dung cần tài liệu hóa |
|---|---|
| Authentication | Cơ chế gửi credential, token expiry và cách refresh nếu có. |
| Authorization | Role/scope cần thiết và điều kiện link có thể bị ẩn. |
| Validation | Field bắt buộc, kiểu dữ liệu, giới hạn và lỗi validation. |
| Domain conflict | Các trạng thái nghiệp vụ khiến thao tác bị từ chối, thường là `409 Conflict`. |
| Not found | Resource không tồn tại hoặc không còn truy cập được. |
| Rate limiting | Giới hạn request và cách xử lý `429 Too Many Requests` nếu API áp dụng. |
| Retry | Thao tác nào an toàn để retry; cách dùng idempotency key nếu có. |

Link chỉ cho biết server công bố khả năng hoặc điểm điều hướng trong representation hiện tại. Nó không phải bằng chứng rằng request chắc chắn thành công hoặc người dùng được phép thực hiện. Server phải kiểm tra quyền và trạng thái ở mỗi request.

Nếu một link bị ẩn vì quyền, tài liệu nên giải thích nguyên tắc chung mà không làm lộ dữ liệu hoặc policy nhạy cảm. Không mô tả một link như public chỉ vì nó xuất hiện trong ví dụ test.

## 15. Tài liệu hóa deprecation và tiến hóa hợp đồng

API hypermedia có thể thay đổi route mà không làm client phụ thuộc trực tiếp vào URL, nhưng relation và semantics vẫn cần được quản lý ổn định.

Khi relation cũ được thay thế:

1. Công bố relation mới và tài liệu semantics tương ứng.
2. Nếu có thể, giữ relation cũ trong giai đoạn chuyển tiếp.
3. Dùng metadata `deprecation` của link để trỏ tới tài liệu giải thích thay đổi.
4. Ghi rõ thời điểm ngừng hỗ trợ, hành vi thay thế và client cần cập nhật gì.
5. Kiểm thử cả representation cũ và mới trong giai đoạn tương thích.

Ví dụ link deprecated:

```java
Link legacy = Link.of("/legacy/orders/42")
        .withRel("legacy-order")
        .withDeprecation("https://docs.example.com/deprecations/legacy-order");
```

`deprecation` là URI dẫn tới tài liệu giải thích, không phải ngày hết hạn hoặc cờ boolean. Tài liệu tại URI đó cần mô tả lý do, replacement relation, thời gian chuyển đổi và tác động tới client.

## 16. Tổ chức tài liệu cho một API lớn

Với API có nhiều resource, nên tổ chức tài liệu theo resource và workflow thay vì chỉ theo controller hoặc package Java:

```text
api-docs/
├── overview.adoc
├── concepts/
│   ├── authentication.adoc
│   ├── media-types.adoc
│   ├── link-relations.adoc
│   └── errors.adoc
├── resources/
│   ├── orders.adoc
│   ├── customers.adoc
│   └── payments.adoc
├── workflows/
│   ├── place-order.adoc
│   ├── cancel-order.adoc
│   └── pay-order.adoc
└── profiles/
    ├── orders-alps.json
    └── customers-alps.json
```

Phần overview giới thiệu base entry point, media type, authentication và cách client khám phá link. Trang resource mô tả representation và relation. Trang workflow giải thích chuỗi transition nghiệp vụ. Profile ALPS hoặc schema có thể được công bố riêng và liên kết từ resource tương ứng.

Không cần sao chép mọi relation chung vào mọi trang. Có thể định nghĩa `self`, `profile`, `curies` một lần trong overview rồi dùng snippet chung để bỏ qua chúng ở các endpoint khác.

## 17. Quy trình tài liệu hóa một workflow hypermedia

Ví dụ workflow thanh toán đơn hàng:

1. Client theo `orders` từ API root và lấy collection.
2. Client theo `self` của item đơn hàng.
3. Representation công bố relation `payment` khi đơn hàng cần thanh toán.
4. Affordance hoặc HAL-FORMS template mô tả `POST`, target, content type và input.
5. Client gửi request và nhận representation mới.
6. Representation mới có thể công bố `receipt` và không còn `payment`.

Tài liệu workflow nên ghi rõ từng bước, relation cần theo, trạng thái trước/sau, input và lỗi có thể xảy ra. REST Docs test từng bước để đảm bảo link và payload thực tế khớp với snippet.

Ví dụ bảng workflow:

| Bước | Resource/Relation | Điều kiện | Kết quả |
|---|---|---|---|
| 1 | API root → `orders` | Client đã xác thực | URI collection đơn hàng. |
| 2 | Order item → `payment` | Đơn hàng ở trạng thái `AWAITING_PAYMENT` | Điểm truy cập thanh toán. |
| 3 | Affordance `POST` | Client có quyền thanh toán | Request tạo giao dịch. |
| 4 | Payment response → `receipt` | Thanh toán thành công | Link tới biên nhận. |

Client không cần dựa vào đường dẫn cố định của từng bước. Tài liệu dùng relation và semantics để giải thích; response runtime cung cấp href và affordance thực tế.

## 18. Lỗi thường gặp khi tài liệu hóa hypermedia

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ công bố JSON sample mà không giải thích relation | Client biết URL nhưng không biết semantics. | Mô tả từng relation và điều kiện xuất hiện. |
| Coi `_links` là tài liệu đầy đủ cho con người | Thiếu method, payload, lỗi và bảo mật. | Kết hợp ALPS, HAL-FORMS và tài liệu hướng dẫn. |
| Coi ALPS là JSON Schema | Client kỳ vọng validation mà profile không cung cấp. | Dùng ALPS cho semantics; mô tả schema/constraints riêng. |
| Giả định link luôn xuất hiện | Client lỗi khi state hoặc quyền thay đổi. | Ghi rõ điều kiện và test từng trạng thái. |
| Dùng `relaxedLinks` cho mọi snippet | Link mới có thể lọt qua mà chưa được giải thích. | Ưu tiên strict `links()` cho hợp đồng chính. |
| Không đánh dấu link optional | Test thất bại khi link hợp lệ vắng mặt theo trạng thái. | Dùng `.optional()` và test các state riêng. |
| Tài liệu hóa URL hard-code | Client phụ thuộc route nội bộ. | Tài liệu relation và hướng dẫn follow `href`. |
| Không kiểm thử link thực tế | Tài liệu dần lệch response. | Tạo snippets từ HTTP test. |
| Nhầm affordance với authorization | Client nghĩ có link là chắc chắn được phép. | Server luôn kiểm tra quyền khi thực hiện request. |
| Không tài liệu hóa deprecation | Client không có lộ trình chuyển đổi. | Dùng deprecation URI và migration guide. |

## 19. Quy trình xây dựng tài liệu API có hypermedia

1. Xác định resource, representation và media type được công bố.
2. Liệt kê relation chuẩn và extension relation; định nghĩa semantics ổn định.
3. Ghi điều kiện xuất hiện của từng link theo trạng thái và quyền.
4. Dùng HAL cho link, ALPS cho profile semantics và HAL-FORMS/affordance khi cần mô tả thao tác.
5. Viết hướng dẫn cho con người về input, output, lỗi, authentication và retry.
6. Dùng Spring REST Docs để mô tả link và payload từ HTTP test.
7. Dùng strict link snippets để phát hiện relation mới hoặc relation bị thiếu.
8. Test các trạng thái resource khác nhau, bao gồm link optional và thao tác bị từ chối.
9. Include snippets vào tài liệu tổng hợp và kiểm tra chúng được build sinh ra.
10. Quản lý profile, deprecation và migration guide khi hợp đồng thay đổi.

Tài liệu API có hypermedia tốt kết hợp khả năng tự khám phá của response với phần giải thích đủ sâu cho nhà phát triển. Relation cho client biết nên đi đâu, affordance cho biết có thể làm gì, profile mô tả semantics, còn tài liệu được sinh từ test giúp bảo đảm lời giải thích vẫn khớp với API đang chạy.

## Tài liệu tham khảo

- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – ALPS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.alps)
- [Spring Data REST – Metadata and ALPS](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring REST Docs – Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs – API documentation](https://docs.spring.io/spring-restdocs/reference/)
- [RFC 6906 – The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906)
- [ALPS – Application-Level Profile Semantics](https://alps.io/)
