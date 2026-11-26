# JSON property của link

Trong Spring HATEOAS, `Link` là value object mô tả một liên kết bằng URI đích, relation và metadata. Khi một representation được trả về dưới dạng HAL JSON, Jackson không tuần tự hóa `Link` như một Java bean thông thường. Spring HATEOAS đăng ký cấu hình Jackson riêng cho HAL để đưa các thuộc tính của link vào đúng cấu trúc mà định dạng quy định.

Điểm quan trọng là relation không nằm bên trong link object. Trong HAL, relation trở thành tên property ở cấp `_links`; object bên trong chứa `href` và các metadata như `type`, `title`, `hreflang` hoặc `deprecation`. Vì vậy, `Link.getRel()` là thông tin cần thiết khi tổ chức `_links`, nhưng không xuất hiện thành property `rel` bên trong mỗi link object.

Bài học này thuộc chương **Jackson serialization** trong module **SPRING_HATEOAS**, tập trung vào ánh xạ giữa `Link` trong Java và JSON property, vai trò của HAL Jackson module/mixin, các thuộc tính được tuần tự hóa, cách cấu hình định dạng link và kiểm thử JSON thực tế.

Sau bài học, bạn có thể:

- Phân biệt relation key trong `_links` với property bên trong link object.
- Nhận biết các JSON property tiêu chuẩn như `href`, `templated`, `type`, `title`, `hreflang`, `deprecation`, `name` và `profile`.
- Hiểu vì sao HAL cần Jackson module và `LinkMixin`.
- Tạo link có metadata bằng API `Link` thay vì tự dựng JSON.
- Cấu hình cách biểu diễn một relation có một link hoặc nhiều link.
- Phân biệt property của link với property của content DTO.
- Kiểm thử serialization qua MockMvc và JSONPath.

## 1. Link trong Java và link trong JSON

Trong Java, một liên kết được biểu diễn bằng `org.springframework.hateoas.Link`. Một đối tượng `Link` có các thông tin như:

- URI đích (`href`).
- Quan hệ liên kết (`LinkRelation`).
- Kiểu media của đích (`type`).
- Tiêu đề (`title`).
- Ngôn ngữ (`hreflang`).
- Trạng thái deprecated (`deprecation`).
- Tên phân biệt (`name`).
- Profile (`profile`).
- Thông tin URI template.

Ví dụ tạo link:

```java
import org.springframework.hateoas.Link;

Link self = Link.of("https://api.example.com/orders/42")
        .withSelfRel();

Link help = Link.of("https://docs.example.com/orders")
        .withRel("help")
        .withType("text/html")
        .withTitle("Hướng dẫn đơn hàng")
        .withHreflang("vi");
```

Khi các link này được gắn vào `EntityModel` và tuần tự hóa bằng HAL, chúng không trở thành một mảng Java bean với tất cả getter. HAL có cấu trúc riêng:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "help": {
      "href": "https://docs.example.com/orders",
      "type": "text/html",
      "title": "Hướng dẫn đơn hàng",
      "hreflang": "vi"
    }
  }
}
```

Ở đây `self` và `help` là relation key; `href`, `type`, `title`, `hreflang` là JSON property bên trong link object.

## 2. Relation không phải JSON property bên trong link object

Một nhầm lẫn thường gặp là mong đợi JSON có cấu trúc:

```json
{
  "_links": {
    "self": {
      "rel": "self",
      "href": "https://api.example.com/orders/42"
    }
  }
}
```

Đây không phải cách HAL biểu diễn relation. Trong HAL, relation đã nằm ở tên property `self` bên dưới `_links`, do đó link object chỉ cần mô tả đích và metadata:

```json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    }
  }
}
```

Spring HATEOAS sử dụng HAL-specific `LinkMixin` để tránh serialize thuộc tính `rel` như một property riêng. Khi thêm link bằng `model.add(link)`, framework lấy relation của link để nhóm link vào đúng key trong `_links`.

Vì vậy, nếu cần đổi relation, hãy dùng `withRel(...)` hoặc `withSelfRel()` trên `Link`. Không thêm một field `rel` vào DTO chỉ để mong serializer HAL đổi relation của link.

## 3. Các JSON property tiêu chuẩn của link

HAL link object hỗ trợ các thuộc tính sau:

| JSON property | Ý nghĩa | API tương ứng trong Spring HATEOAS |
|---|---|---|
| `href` | URI reference của đích liên kết | `getHref()`, `Link.of(...)`, `withHref(...)` |
| `templated` | `href` chứa URI template cần mở rộng | `isTemplated()`, `Link.of(UriTemplate, rel)` |
| `type` | Gợi ý media type của resource đích | `getType()`, `withType(...)` |
| `deprecation` | URI tài liệu mô tả link/relation deprecated | `getDeprecation()`, `withDeprecation(...)` |
| `name` | Tên phụ để phân biệt link cùng relation | `getName()`, `withName(...)` |
| `profile` | URI profile mô tả semantics của resource đích | `getProfile()`, `withProfile(...)` |
| `title` | Tiêu đề dễ đọc cho link | `getTitle()`, `withTitle(...)` |
| `hreflang` | Ngôn ngữ của resource đích | `getHreflang()`, `withHreflang(...)` |

`href` là property cốt lõi của link object. Các property còn lại là metadata tùy chọn. Nếu metadata không có giá trị, HAL serializer thường không ghi property tương ứng vào JSON. `templated` được ghi khi link thực sự là URI template; link thông thường không cần mang `templated: false`.

Không nên tự thêm mọi property vào mọi link. Chỉ công bố metadata khi client có thể dùng nó để chọn resource, hiển thị nhãn, xác định ngôn ngữ hoặc hiểu vòng đời liên kết.

## 4. `type` và `media` không phải cùng một khái niệm

Spring HATEOAS `Link` có API `withType(...)` và `withMedia(...)`, nhưng hai thuộc tính có ý nghĩa khác nhau trong mô hình link. `type` mô tả media type dự kiến của resource đích, ví dụ `application/pdf` hoặc `text/html`. `media` là một thuộc tính khác của mô hình Web Linking, thường liên quan tới điều kiện media mà link áp dụng.

Với HAL link object, property tiêu chuẩn được công bố cho media type của resource đích là `type`. Không nên đổi `type` thành `media` hoặc tự tạo JSON property `mediaType` nếu hợp đồng HAL không định nghĩa nó. Nếu dùng một media type hypermedia khác, hãy xem serializer của media type đó để biết thuộc tính nào được biểu diễn.

Ví dụ:

```java
Link pdf = Link.of("/orders/42.pdf")
        .withRel("alternate")
        .withType("application/pdf")
        .withTitle("Tải đơn hàng PDF");
```

HAL output tương ứng:

```json
{
  "_links": {
    "alternate": {
      "href": "/orders/42.pdf",
      "type": "application/pdf",
      "title": "Tải đơn hàng PDF"
    }
  }
}
```

## 5. URI template và property `templated`

Khi `href` chứa biến URI template, HAL cần công bố `templated: true` để client biết phải mở rộng template trước khi gửi request.

```java
import org.springframework.hateoas.Link;

Link search = Link.of("/orders{?status,page}", "search");
```

Biểu diễn HAL có dạng:

```json
{
  "_links": {
    "search": {
      "href": "/orders{?status,page}",
      "templated": true
    }
  }
}
```

Client đọc `templated` để biết `href` cần được mở rộng theo URI Template trước khi sử dụng. Nếu link là URI cụ thể như `/orders/42`, không cần property `templated`.

Trong Java, có thể kiểm tra `link.isTemplated()` hoặc lấy thông tin từ `link.getTemplate()`. Không nên tự kiểm tra chuỗi có dấu `{` để quyết định mọi trường hợp; dùng API của `Link` giúp tuân theo cách Spring HATEOAS phân tích URI template.

## 6. Cách Spring HATEOAS và Jackson tạo JSON property

Spring HATEOAS tích hợp với Jackson thông qua module và mixin dành riêng cho từng hypermedia media type. Với HAL, `HalJacksonModule` đăng ký serializer/deserializer và `LinkMixin` tùy chỉnh cách Jackson nhìn thấy `Link`.

`LinkMixin` có vai trò quan trọng:

- Không để `rel` xuất hiện bên trong link object, vì relation đã được dùng làm key của `_links`.
- Công bố các getter metadata phù hợp với HAL như `getTitle()`, `getType()`, `getHreflang()`, `getName()`, `getProfile()` và `getDeprecation()`.
- Công bố trạng thái URI template qua `isTemplated()`.
- Giữ `href` làm URI đích của link.

Trong ứng dụng Spring, bật hỗ trợ HAL để framework đăng ký cấu hình Jackson tương ứng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
```

Trong Spring Boot, starter và auto-configuration có thể đã thiết lập hỗ trợ hypermedia theo cấu hình ứng dụng. Nếu đã có cấu hình đó, không cần đăng ký lặp module hoặc tạo thêm một `ObjectMapper` riêng cho response HAL.

Không nên tự serialize `Link` bằng một `ObjectMapper` trống rồi kỳ vọng kết quả giống HAL. Một mapper không có module HAL sẽ không tự biết cách nhóm relation vào `_links` hoặc áp dụng các quy tắc của media type. Hãy dùng mapper/converter được Spring cấu hình cho HAL.

## 7. Vì sao không nên dùng `@JsonProperty` để đổi tên Link field?

`@JsonProperty` phù hợp để định nghĩa tên JSON của property thuộc DTO hoặc model do ứng dụng kiểm soát. Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderResponse(
        @JsonProperty("order_code") String code,
        String status
) {}
```

Khi serialize content, trường `code` trở thành `order_code`. Annotation này tác động tới JSON property của content DTO.

Đối với link, `href`, `title`, `type` và các property khác do HAL serializer/mixin quy định. Không nên cố thêm `@JsonProperty("url")` lên getter của `Link` hoặc tự tạo DTO bao quanh `Link` chỉ để đổi `href` thành `url`, vì kết quả sẽ không còn tuân theo cấu trúc HAL tiêu chuẩn.

Nếu API cần một định dạng JSON khác HAL, hãy chọn media type phù hợp hoặc triển khai custom hypermedia media type với Jackson module riêng. Không sửa ngữ nghĩa của HAL chỉ để đáp ứng một quy ước tên field nội bộ.

## 8. Tạo JSON property bằng API Link

Các phương thức `with...` trên `Link` trả về một link mới với metadata tương ứng. Vì `Link` là immutable, hãy giữ kết quả trả về của từng lời gọi:

```java
import org.springframework.hateoas.Link;

Link help = Link.of("https://docs.example.com/orders")
        .withRel("help")
        .withTitle("Tài liệu đơn hàng")
        .withType("text/html")
        .withHreflang("vi");

Link legacy = Link.of("/legacy/orders/42")
        .withRel("legacy-order")
        .withName("legacy")
        .withDeprecation("https://docs.example.com/deprecations/orders-v1")
        .withProfile("https://api.example.com/profiles/order-v1");
```

Thêm link vào representation:

```java
import org.springframework.hateoas.EntityModel;

EntityModel<OrderResponse> model = EntityModel.of(orderResponse);
model.add(help, legacy);
```

Serializer HAL sẽ đặt từng link dưới relation tương ứng. Các metadata không có giá trị sẽ không cần được gán thủ công thành chuỗi rỗng hoặc `null`.

## 9. Relation key và nhiều link cùng relation

Một relation có thể chứa một link hoặc nhiều link. Trong HAL, nhiều link cùng relation được biểu diễn thành mảng:

```java
Link html = Link.of("/orders/42", "alternate")
        .withType("application/hal+json")
        .withTitle("Đơn hàng HAL");

Link pdf = Link.of("/orders/42.pdf", "alternate")
        .withType("application/pdf")
        .withTitle("Đơn hàng PDF");

EntityModel<OrderResponse> model = EntityModel.of(orderResponse, html, pdf);
```

Kết quả HAL:

```json
{
  "_links": {
    "alternate": [
      {
        "href": "/orders/42",
        "type": "application/hal+json",
        "title": "Đơn hàng HAL"
      },
      {
        "href": "/orders/42.pdf",
        "type": "application/pdf",
        "title": "Đơn hàng PDF"
      }
    ]
  }
}
```

Với một link duy nhất, Spring HATEOAS mặc định dùng object thay vì mảng một phần tử. HAL cho phép cả hai hình thức khi chỉ có một link, nên client nên xử lý cả object và array.

Nếu muốn luôn serialize link đơn thành mảng, có thể cấu hình `HalConfiguration`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.mediatype.hal.HalConfiguration;

@Configuration
class HalLinkConfiguration {

    @Bean
    HalConfiguration halConfiguration() {
        return new HalConfiguration()
                .withRenderSingleLinks(HalConfiguration.RenderSingleLinks.AS_ARRAY);
    }
}
```

Cũng có thể cấu hình theo từng relation bằng `withRenderSingleLinksFor(...)`. Chỉ thay đổi chính sách này khi client có hợp đồng rõ ràng về kiểu dữ liệu; hãy kiểm thử response trước khi phát hành vì thay đổi object thành array ảnh hưởng cách client đọc JSON.

## 10. Quốc tế hóa JSON property `title`

HAL định nghĩa `title` để client có thể hiển thị nhãn link. Spring HATEOAS hỗ trợ lấy title từ resource bundle tên `rest-messages`.

Ví dụ file `src/main/resources/rest-messages.properties`:

```properties
_links.cancel.title=Hủy đơn hàng
_links.payment.title=Tiến hành thanh toán
_links.help.title=Xem hướng dẫn
```

Khi serializer HAL xử lý các relation tương ứng, title có thể được bổ sung vào link object:

```json
{
  "_links": {
    "cancel": {
      "href": "/orders/42/cancellation",
      "title": "Hủy đơn hàng"
    },
    "payment": {
      "href": "/orders/42/payment",
      "title": "Tiến hành thanh toán"
    }
  }
}
```

Có thể đặt các resource bundle theo locale, ví dụ `rest-messages_vi.properties` và `rest-messages_en.properties`, để title hiển thị theo ngôn ngữ được ứng dụng chọn. `title` chỉ là nhãn cho người dùng; client vẫn phải dùng relation để nhận diện semantics của link.

## 11. CURIE và tên relation trong JSON

Với extension relation được định danh bằng URI, Spring HATEOAS có thể dùng CURIE để rút gọn tên relation trong `_links`. Khi đó relation key có thể là `ex:cancel` thay vì URI đầy đủ.

Ví dụ HAL:

```json
{
  "_links": {
    "curies": {
      "name": "ex",
      "href": "https://api.example.com/rels/{rel}",
      "templated": true
    },
    "ex:cancel": {
      "href": "/orders/42/cancellation",
      "title": "Hủy đơn hàng"
    }
  }
}
```

`ex:cancel` là relation key; `href` và `title` vẫn là các property bên trong link object. CURIE chỉ rút gọn relation URI, không đổi tên property của link object.

## 12. Phân biệt HAL Link property với HAL-FORMS template property

HAL và HAL-FORMS có cấu trúc liên quan nhưng không giống nhau. HAL dùng `_links` để mô tả liên kết. HAL-FORMS mở rộng document bằng `_templates`, trong đó `method`, `target`, `contentType` và `properties` mô tả request form.

Ví dụ:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    }
  },
  "_templates": {
    "cancelOrder": {
      "method": "POST",
      "target": "/orders/42/cancellation",
      "properties": [
        { "name": "reason", "required": true }
      ]
    }
  }
}
```

`href` thuộc link object trong `_links`; `method`, `target` và `properties` thuộc template trong `_templates`. Không đưa `method` vào link object rồi kỳ vọng HAL serializer biến nó thành affordance. Nếu cần mô tả thao tác, dùng affordance và media type có hỗ trợ như HAL-FORMS.

## 13. Kiểm thử JSON property của Link

Nên kiểm thử response HTTP với đúng media type thay vì chỉ gọi `ObjectMapper.writeValueAsString(link)` bằng mapper tùy ý. Ví dụ MockMvc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LinkJsonPropertiesTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void linkMetadataUsesHalPropertyNames() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.self.href",
                        containsString("/orders/42")))
                .andExpect(jsonPath("$._links.help.type").value("text/html"))
                .andExpect(jsonPath("$._links.help.title").value("Hướng dẫn đơn hàng"))
                .andExpect(jsonPath("$._links.help.hreflang").value("vi"))
                .andExpect(jsonPath("$._links.self.rel").doesNotExist());
    }
}
```

Ví dụ giả định endpoint `/orders/42` trả `EntityModel<OrderResponse>` với link `help` được tạo bằng `withType`, `withTitle`, `withHreflang`. Assertion `self.rel` xác nhận relation không bị lặp bên trong link object.

Nếu API có nhiều link cùng relation, kiểm tra array:

```java
mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.alternate[0].href").exists())
        .andExpect(jsonPath("$._links.alternate[1].type").value("application/pdf"));
```

Ngoài ra, nên kiểm thử URI template có `templated: true`, title theo locale, relation CURIE và chính sách render single link nếu ứng dụng có tùy chỉnh `HalConfiguration`.

## 14. Khi cần tùy chỉnh Jackson sâu hơn

Với HAL tiêu chuẩn, nên dùng `Link` API và cấu hình có sẵn của Spring HATEOAS. Chỉ viết serializer hoặc thay đổi `ObjectMapper` khi ứng dụng thực sự triển khai một media type riêng hoặc cần một quy tắc tuần tự hóa ngoài chuẩn.

Spring HATEOAS hỗ trợ tích hợp custom media type thông qua `HypermediaMappingInformation`. Implementation có thể cung cấp:

- Media type mà representation hỗ trợ.
- Jackson module chứa serializer/deserializer cho `RepresentationModel`, `EntityModel`, `CollectionModel` và `PagedModel`.
- `LinkDiscoverer` để client tìm link theo relation.
- Cấu hình `ObjectMapper` bổ sung khi cần handler hoặc serializer đặc biệt.

Không nên thay `LinkMixin` nội bộ của HAL để đổi `href` thành `url` hoặc xóa metadata tùy ý. Làm vậy có thể khiến response không còn tương thích với client HAL và các công cụ link discovery.

Tên Jackson module cũng phụ thuộc phiên bản Spring HATEOAS/Jackson. Các bản dựa trên Jackson 2 sử dụng tên `Jackson2HalModule`; tài liệu mới hơn có `HalJacksonModule` gắn với Jackson 3. Hãy dùng module được phiên bản dự án hỗ trợ thay vì sao chép import từ một phiên bản khác.

## 15. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Mong đợi `rel` bên trong link object | JSON không đúng cấu trúc HAL. | Relation là key trong `_links`. |
| Dùng `@JsonProperty` để đổi `href` thành `url` | Link không còn tuân theo HAL. | Dùng property chuẩn hoặc một media type riêng. |
| Tự tạo `ObjectMapper` trống | Mất cấu hình serializer hypermedia. | Dùng Jackson converter/mapper do Spring HATEOAS cấu hình. |
| Cho rằng mọi getter của `Link` đều xuất hiện trong HAL | Dễ nhầm lẫn giữa mô hình Java và schema media type. | Kiểm tra HAL link object và serializer/mixin của phiên bản đang dùng. |
| Nhầm `type` với `media` | Client nhận metadata sai ý nghĩa. | Dùng `type` cho media type của resource đích. |
| Gửi link URI template nhưng không có `templated` | Client không biết phải mở rộng URI. | Tạo link bằng API URI template của Spring HATEOAS. |
| Giả định một relation luôn là object | Client lỗi khi relation có nhiều link hoặc chính sách render array. | Hỗ trợ cả object và array. |
| Dùng `method` trong HAL link object | Client không nhận được affordance theo chuẩn. | Dùng affordance và HAL-FORMS khi cần mô tả thao tác. |
| Chỉ kiểm tra object Java mà không kiểm tra JSON | Không phát hiện sai serializer hoặc media type. | Kiểm thử HTTP bằng MockMvc với `application/hal+json`. |

## 16. Quy trình làm việc với JSON property của Link

Khi cần công bố một liên kết trong HAL, hãy thực hiện theo trình tự:

1. Chọn relation phù hợp với ngữ nghĩa của link.
2. Tạo `Link` với `href` bằng `Link.of(...)` hoặc link builder của Spring HATEOAS.
3. Thêm metadata cần thiết bằng `withType`, `withTitle`, `withHreflang`, `withName`, `withProfile` hoặc `withDeprecation`.
4. Nếu URI có biến, tạo URI template để serializer công bố `templated`.
5. Thêm link vào `RepresentationModel` hoặc `EntityModel`.
6. Bảo đảm HAL Jackson support được cấu hình và response dùng media type HAL.
7. Kiểm tra relation key và các property bên trong link object bằng JSONPath.
8. Nếu có nhiều link cùng relation, kiểm thử array và chính sách render link đơn.
9. Chỉ tùy chỉnh Jackson sâu hơn khi xây media type riêng hoặc có yêu cầu serialization ngoài HAL.

JSON property của link được quyết định bởi hợp đồng media type và Jackson module của Spring HATEOAS. Khi relation được đặt ở đúng cấp `_links`, còn `href` và metadata được serialize theo cấu trúc HAL, client có thể nhận diện link ổn định mà không phụ thuộc vào cách Java lưu trữ value object `Link`.

## Tài liệu tham khảo

- [Spring HATEOAS – Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS – LinkMixin API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/hal/LinkMixin.html)
- [Spring HATEOAS – HAL reference, link rendering](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – Serialized Form](https://docs.spring.io/spring-hateoas/docs/current/api/serialized-form.html)
- [HAL – Hypertext Application Language specification](https://stateless.group/hal_specification.html)
