# Relation qua phiên bản

Một API đơn hàng có thể chuyển endpoint collection từ `/api/v1/orders` sang `/api/v2/orders`. Client dùng hypermedia không cần tự ghép đường dẫn phiên bản nếu server công bố link đến collection. Tuy nhiên, khi chuyển phiên bản, cần quyết định relation của link có tiếp tục giữ nguyên hay phải có định danh mới. Câu trả lời phụ thuộc vào ngữ nghĩa mà relation đại diện, không chỉ phụ thuộc vào việc URL target có đổi hay không.

Trong thiết kế hypermedia, cần phân biệt ba lớp: **phiên bản API**, **phiên bản representation** và **ngữ nghĩa của link relation**. API có thể thay đổi route hoặc schema mà relation vẫn giữ nguyên ý nghĩa. Ngược lại, nếu ý nghĩa của relation thay đổi không tương thích, nên công bố relation mới để client không diễn giải sai capability hoặc resource đích.

## Ba khái niệm cần tách biệt

Versioning của Web API thường liên quan đến nhiều thành phần. Không nên xem mọi thay đổi phiên bản đều buộc phải đổi link relation.

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| API version | Client đang gọi hợp đồng API nào? | `/api/v1/orders`, `/api/v2/orders`. |
| Representation version/profile | Dữ liệu trả về có cấu trúc hoặc semantics nào? | `application/vnd.acme.order-v2+json`, profile `https://api.example.com/profiles/order-v2`. |
| Link relation | Target có ý nghĩa gì đối với context? | `https://api.example.com/rels/orders`, `.../rels/approve`. |

API version có thể thay đổi route, schema, validation hoặc hành vi HTTP. Representation profile mô tả cách hiểu một representation. Relation mô tả quan hệ giữa context và target. Ba thứ có thể tiến hóa độc lập nhưng cần được công bố nhất quán.

## Giữ relation ổn định khi chỉ đổi URI target

Giả sử relation `acme:orders` luôn có nghĩa “đi đến collection đơn hàng mà client có thể truy vấn”. Phiên bản đầu trỏ đến `/api/v1/orders`; phiên bản sau chuyển sang `/commerce/orders`.

```text
API root
   |
   | rel="acme:orders"
   v
v1: /api/v1/orders

Sau khi thay route:

API root
   |
   | rel="acme:orders"
   v
v2: /commerce/orders
```

Nếu semantics vẫn là collection đơn hàng và client có thể xử lý representation tương thích, relation URI nên giữ nguyên. Server thay đổi `href`; client tiếp tục tìm relation `acme:orders` rồi follow link mới.

Ví dụ hai response ở hai thời điểm:

```json
{
  "_links": {
    "self": { "href": "/api" },
    "acme:orders": { "href": "/api/v1/orders" }
  }
}
```

Sau khi đổi route:

```json
{
  "_links": {
    "self": { "href": "/api" },
    "acme:orders": { "href": "/commerce/orders" }
  }
}
```

Client không cần biết route được đổi. Đây là một lợi ích của hypermedia: relation ổn định là điểm nhận diện ngữ nghĩa, còn URI target do server cung cấp tại runtime.

Điều này không có nghĩa mọi thay đổi schema đều an toàn. Nếu client cũ không thể xử lý representation mới, server vẫn cần cơ chế tương thích, media type/profile hoặc API version riêng. Giữ relation chỉ hợp lý khi semantics của quan hệ vẫn đúng và client có cách nhận diện representation mà nó hỗ trợ.

## Khi nào cần relation mới?

Một relation URI định danh semantics. Nếu semantics thay đổi không tương thích, tái sử dụng URI cũ có thể khiến client hiểu sai target hoặc thực hiện hành động không mong muốn.

Ví dụ relation cũ `approve` có nghĩa “gửi đơn hàng vào quy trình phê duyệt”. Sau một thay đổi nghiệp vụ, target mới lại có nghĩa “phê duyệt và xác nhận đơn ngay lập tức”. Hai thao tác khác nhau về hậu quả và quyền hạn. Không nên âm thầm đổi semantics của relation cũ.

Có thể tạo relation mới:

```text
https://api.example.com/rels/submit-for-approval
https://api.example.com/rels/approve-order
```

Hoặc nếu tổ chức muốn thể hiện rõ hai hợp đồng có phiên bản:

```text
https://api.example.com/rels/approve-v1
https://api.example.com/rels/approve-v2
```

Hậu tố `v1`/`v2` không phải yêu cầu của RFC; đây là quy ước naming của ứng dụng. Chỉ dùng nó khi hai relation thực sự có semantics khác nhau hoặc client cần chọn rõ một capability theo hợp đồng. Không thêm version vào relation URI chỉ vì endpoint chuyển từ `/v1` sang `/v2`.

Một relation mới cần được tài liệu hóa như một định danh mới: context, target, semantics, điều kiện xuất hiện, method, media type, authorization và lỗi có thể xảy ra. URI relation cũ tiếp tục giữ nghĩa cũ, kể cả sau khi API ngừng cung cấp target đó.

## Relation URI không phải API endpoint version

Hãy tách relation URI và target URI:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Relation URI | `https://api.example.com/rels/orders` | Định danh semantics “collection đơn hàng”. |
| Target v1 | `https://api.example.com/api/v1/orders` | Endpoint cụ thể của API version 1. |
| Target v2 | `https://api.example.com/api/v2/orders` | Endpoint cụ thể của API version 2. |

Relation URI không cần chứa `/v1` hoặc `/v2` nếu semantics không đổi. Target URI có thể được version hóa bằng path, query, header hoặc cơ chế định tuyến khác.

Không lấy target path làm relation. Ví dụ, client không nên suy luận rằng `/api/v2/orders` tương ứng với relation `orders-v2` nếu server chưa công bố semantics đó. Client nên đọc relation và `href` từ response.

## Các chiến lược versioning và tác động đến hypermedia

API có thể chọn nhiều chiến lược versioning. Hypermedia không bắt buộc một chiến lược cụ thể; nó giúp client khám phá target thay vì tự tạo URI.

| Chiến lược | Ví dụ | Điều client cần quan sát |
| --- | --- | --- |
| URI path | `/api/v2/orders` | `href` trong link trỏ đến path version tương ứng. |
| Vendor media type | `application/vnd.acme.orders-v2+json` | `type`/media type và `Accept` thể hiện representation được yêu cầu. |
| Header version | `Accept: application/json; version=2` | Client gửi header đã công bố; link có thể giữ URI nhưng representation thay đổi theo header. |
| Profile | `profile="https://api.example.com/profiles/orders-v2"` | Client nhận diện profile/semantics representation theo hợp đồng. |

Không có một chiến lược phù hợp cho mọi hệ thống. Dù chọn cách nào, API cần công bố cách client chọn version, thời gian hỗ trợ và hành vi khi version không được hỗ trợ.

### Version trong URI path

Đây là cách dễ quan sát và kiểm thử. Root resource có thể trỏ đến version hiện hành:

```json
{
  "_links": {
    "self": { "href": "/api" },
    "acme:orders": { "href": "/api/v2/orders" }
  }
}
```

Client theo `acme:orders` và không tự thêm `/v2`. Khi server chuyển version, nó thay target trong root response hoặc cung cấp root version riêng.

### Version trong media type

Nếu cùng một URI có thể trả nhiều representation, media type giúp client yêu cầu hợp đồng mà nó hỗ trợ. Một link có thể công bố `type` như gợi ý về media type của target:

```json
{
  "_links": {
    "self": { "href": "/api/orders/ord-1042" },
    "alternate": {
      "href": "/api/v2/orders/ord-1042",
      "type": "application/vnd.acme.order-v2+json"
    }
  }
}
```

Thuộc tính `type` là metadata gợi ý về media type của target; nó không tự thực hiện content negotiation và không thay thế việc client gửi `Accept` phù hợp. Client phải xử lý `406 Not Acceptable` hoặc các lỗi negotiation theo hợp đồng.

### Version bằng profile

Profile mô tả thêm semantics hoặc quy ước của representation. Relation `profile` có thể trỏ đến tài liệu profile:

```json
{
  "_links": {
    "profile": {
      "href": "https://api.example.com/profiles/order-v2"
    }
  }
}
```

Profile giúp client hiểu representation tuân theo quy ước nào. Không dùng `profile` để giả vờ rằng mọi thay đổi API đều tương thích; tài liệu profile cần nói rõ field, semantics, constraint và hành vi nào được bổ sung hoặc thay đổi.

## Dùng relation chuẩn cho lịch sử phiên bản

IANA Link Relations Registry có các relation dành cho việc điều hướng giữa các phiên bản của một resource. RFC 5829 định nghĩa một số relation như:

- `successor-version`: phiên bản kế tiếp của resource context.
- `predecessor-version`: phiên bản trước của resource context.
- `version-history`: tài nguyên cung cấp lịch sử các phiên bản.

Các relation này phù hợp khi resource có các phiên bản được liên kết trong một lịch sử. Chúng không thay thế relation nghiệp vụ như `orders` hoặc cơ chế chọn API version. Chỉ công bố chúng khi target thực sự biểu diễn phiên bản kế tiếp, phiên bản trước hoặc lịch sử của cùng resource.

Ví dụ một resource tài liệu versioned:

```json
{
  "id": "policy-17",
  "version": 1,
  "_links": {
    "self": { "href": "/api/policies/policy-17/versions/1" },
    "successor-version": {
      "href": "/api/policies/policy-17/versions/2"
    },
    "version-history": {
      "href": "/api/policies/policy-17/versions"
    }
  }
}
```

Phiên bản 2 có thể cung cấp `predecessor-version` trỏ về phiên bản 1. Nếu phiên bản hiện tại chưa có successor, không thêm link `successor-version` với URI giả hoặc URI rỗng.

## Biểu diễn version relations trong Spring HATEOAS

Spring HATEOAS cung cấp `IanaLinkRelations` cho các relation chuẩn. Dùng hằng thay vì viết chuỗi relation rải rác:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

EntityModel<PolicyVersionView> model = EntityModel.of(policyVersion);

model.add(Link.of(
    "/api/policies/policy-17/versions/2",
    IanaLinkRelations.SUCCESSOR_VERSION));

model.add(Link.of(
    "/api/policies/policy-17/versions",
    IanaLinkRelations.VERSION_HISTORY));
```

Ví dụ giả định policy version 1 có successor là version 2. Trong ứng dụng thực tế, nên tạo link bằng `WebMvcLinkBuilder` nếu target thuộc controller Spring MVC:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

model.add(linkTo(methodOn(PolicyController.class)
        .version(policyId, 2))
    .withRel(IanaLinkRelations.SUCCESSOR_VERSION));

model.add(linkTo(methodOn(PolicyController.class)
        .versions(policyId))
    .withRel(IanaLinkRelations.VERSION_HISTORY));
```

`methodOn(...)` tham chiếu mapping và tham số controller để tạo URI. Nó không gọi controller method. Chỉ thêm successor link khi phiên bản kế tiếp đã tồn tại và caller được phép truy cập nó.

## Tạo custom relation có semantics theo phiên bản

Khi relation chuẩn không diễn đạt đúng semantics, tạo extension relation URI ổn định. Ví dụ:

```java
import org.springframework.hateoas.LinkRelation;

final class ApiRelations {

    static final LinkRelation ORDERS = LinkRelation.of(
        "https://api.example.com/rels/orders");

    static final LinkRelation ORDERS_V1 = LinkRelation.of(
        "https://api.example.com/rels/orders-v1");

    static final LinkRelation ORDERS_V2 = LinkRelation.of(
        "https://api.example.com/rels/orders-v2");

    static final LinkRelation APPROVE_V1 = LinkRelation.of(
        "https://api.example.com/rels/approve-v1");

    static final LinkRelation APPROVE_V2 = LinkRelation.of(
        "https://api.example.com/rels/approve-v2");

    private ApiRelations() {
    }
}
```

Đây là lựa chọn phù hợp nếu `approve-v1` và `approve-v2` thực sự biểu diễn hai capability khác nhau. Nếu chỉ route đổi nhưng cả hai đều bắt đầu cùng một quy trình phê duyệt, chỉ cần một relation `approve` với target URI tương ứng.

### Rút gọn relation URI bằng CURIE

Trong HAL, có thể dùng CURIE để rút gọn extension relation:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
class HypermediaConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
            "acme",
            new UriTemplate("https://api.example.com/rels/{rel}"));
    }
}
```

Relation URI `https://api.example.com/rels/approve-v2` có thể được serialize thành `acme:approve-v2`. CURIE chỉ rút gọn cách biểu diễn trong HAL; client vẫn cần nhận diện URI đầy đủ theo namespace đã công bố.

Không tạo prefix mới cho từng API version nếu namespace không cần tách biệt. Có thể dùng cùng prefix `acme` cho các relation `orders`, `approve-v1` và `approve-v2`.

## Cung cấp nhiều API version từ một root

Nếu API đồng thời hỗ trợ v1 và v2, root có thể công bố cả hai entry point. Khi client cần lựa chọn rõ phiên bản, dùng relation riêng đã được tài liệu hóa:

```java
EntityModel<ApiInfo> root = EntityModel.of(apiInfo);

root.add(linkTo(methodOn(OrderV1Controller.class).all())
    .withRel(ApiRelations.ORDERS_V1));

root.add(linkTo(methodOn(OrderV2Controller.class).all())
    .withRel(ApiRelations.ORDERS_V2));
```

Nếu hai collection chỉ khác route nhưng semantics và contract tương thích, có thể công bố một relation `orders` trỏ đến version mặc định. Nếu cả hai cùng được công bố cho client lựa chọn, relation `orders-v1` và `orders-v2` cần được định nghĩa rõ để tránh mơ hồ.

Không thêm hai link khác target nhưng cùng relation `orders` rồi kỳ vọng mọi client biết phải chọn link nào. HAL cho phép relation có nhiều link, nhưng API phải định nghĩa cardinality và cách phân biệt; nếu không có quy tắc rõ, client không thể chọn version một cách đáng tin cậy.

## Dùng alternate khi cùng resource có representation khác

Relation `alternate` được dùng cho một tài nguyên thay thế hoặc representation thay thế của context. Nếu hai link trỏ đến cùng resource theo hai media type khác nhau, có thể dùng `alternate` và `type` để thông báo định dạng:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

model.add(Link.of(
    "/api/orders/ord-1042",
    IanaLinkRelations.ALTERNATE)
    .withType("application/vnd.acme.order-v2+json"));
```

Chỉ dùng `alternate` nếu target thực sự là representation thay thế theo semantics relation. Nếu target là API version mới với hành vi hoặc resource model khác đáng kể, hãy mô tả rõ bằng relation version/capability riêng hoặc liên kết successor phù hợp. `alternate` không tự có nghĩa “API version mới hơn”.

## Relation versioning và deprecation

Khi v2 thay thế v1, cần có lộ trình chuyển tiếp cho client. Một quy trình có thể gồm:

1. Công bố v2 và relation mới nếu semantics thay đổi không tương thích.
2. Giữ v1 hoạt động trong thời gian chuyển tiếp đã công bố.
3. Từ root hoặc resource v1, cung cấp link dẫn đến successor hoặc tài liệu migration nếu phù hợp.
4. Đánh dấu endpoint/version cũ deprecated bằng header và tài liệu rõ ràng.
5. Theo dõi client usage, thông báo thời điểm ngừng hỗ trợ và cung cấp hướng dẫn nâng cấp.
6. Ngừng v1 sau khi hết thời gian hỗ trợ; giữ relation URI cũ như định danh lịch sử, không tái sử dụng nó cho semantics mới.

Header `Deprecation` theo RFC 9745 có thể thông báo resource hoặc API element đã bị deprecated; relation `deprecation` có thể dẫn đến tài liệu giải thích. Header `Sunset` theo RFC 8594 có thể thông báo thời điểm resource dự kiến không còn khả dụng. Đây là metadata về vòng đời hỗ trợ; chúng không thay thế relation điều hướng hoặc tài liệu migration.

Ví dụ response v1 trong giai đoạn chuyển tiếp:

```http
HTTP/1.1 200 OK
Deprecation: @1796083200
Sunset: Thu, 31 Dec 2026 23:59:59 GMT
Link: <https://api.example.com/deprecations/orders-v1>; rel="deprecation"
Content-Type: application/hal+json
```

Ngày trong ví dụ chỉ minh họa cú pháp và cần được thay bằng mốc thực tế. Không gửi `Sunset` nếu chưa có ngày ngừng cung cấp được quyết định và công bố.

## Tài liệu hóa relation qua các phiên bản

Mỗi relation nên có một bản ghi trong danh mục quan hệ của API. Khi API có nhiều phiên bản, ghi rõ relation URI nào dùng cho contract nào và semantics có thay đổi hay không.

Ví dụ:

| Relation URI | API version | Semantics | Trạng thái |
| --- | --- | --- | --- |
| `https://api.example.com/rels/orders` | v1, v2 | Collection đơn hàng có cùng ý nghĩa; target URI thay đổi theo root/configuration. | Stable |
| `https://api.example.com/rels/approve-v1` | v1 | Bắt đầu quy trình phê duyệt hai bước. | Deprecated |
| `https://api.example.com/rels/approve-v2` | v2 | Phê duyệt ngay theo quy trình mới. | Current |
| `https://api.example.com/rels/version-history` | Resource versioned | Collection lịch sử các phiên bản của resource. | Stable |

Trang relation cần mô tả:

- URI định danh và CURIE nếu có.
- Context type và target meaning.
- HTTP method, request/response media type và schema liên quan.
- Điều kiện xuất hiện, authorization và lỗi.
- API version hoặc profile hỗ trợ.
- Quan hệ với relation trước/sau và thời điểm deprecation.
- Chính sách tương thích và migration.

Tài liệu relation URI nên được duy trì lâu dài. Có thể cập nhật nội dung trang tài liệu để bổ sung ví dụ hoặc lịch sử tương thích, nhưng không thay đổi semantics của định danh cũ theo cách làm client cũ hiểu sai.

## Client nên xử lý versioned relations thế nào?

Client hypermedia không nên đoán version từ path hoặc tự tăng `/v1` thành `/v2`. Thay vào đó:

1. Bắt đầu từ entry point được cấu hình.
2. Tìm relation đã được client hỗ trợ, ví dụ `acme:orders` hoặc `acme:orders-v2`.
3. Theo `href` được server công bố.
4. Gửi `Accept` phù hợp nếu API version được chọn qua media type.
5. Kiểm tra `Content-Type` và profile của response trước khi deserialize.
6. Bỏ qua relation không biết nếu hợp đồng cho phép; không thực thi capability chỉ vì relation xuất hiện.
7. Xử lý `Deprecation`, `Sunset` hoặc link migration theo chính sách client.

Client cũ không nên thất bại chỉ vì server thêm một relation mới. Ngược lại, server không nên đổi semantics của relation đã công bố mà không tạo đường chuyển tiếp.

## Kiểm thử relation và version target

Kiểm thử nên tách relation semantics khỏi URI path cụ thể. Nếu route đổi nhưng relation giữ nguyên, test contract có thể xác nhận relation vẫn tồn tại và target mới trỏ đến endpoint version được mong đợi.

### Kiểm thử root links cho API version

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links['acme:orders'].href")
        .value("/api/v2/orders"));
```

Test này giả định root đang trỏ đến v2 và CURIE `acme` được cấu hình. Nếu base URI là absolute, hãy phân tích URI và kiểm tra path thay vì so sánh toàn bộ URL.

### Kiểm thử relation mới khi semantics đổi

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links['acme:approve-v2'].href").exists())
    .andExpect(jsonPath("$._links['acme:approve-v1']").doesNotExist());
```

Ví dụ này giả định resource hiện tại chỉ hỗ trợ capability mới. Trong giai đoạn chuyển tiếp, có thể công bố cả hai relation nếu user có quyền và hai thao tác vẫn khả dụng; khi đó test phải xác nhận target riêng và semantics của từng relation.

### Kiểm thử version history relations

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/policies/{id}/versions/1", policyId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links['successor-version'].href")
        .exists())
    .andExpect(jsonPath("$._links['version-history'].href")
        .exists());
```

Nếu phiên bản hiện tại không có successor, kiểm tra relation `successor-version` vắng mặt. Không tạo link successor giả chỉ để làm test luôn có link.

### Kiểm thử deprecation

Với endpoint v1 trong giai đoạn chuyển tiếp, kiểm tra `Deprecation`, `Sunset` và relation `deprecation` theo chính sách đã công bố. Test cần cố định clock hoặc mốc thời gian để tránh thất bại khi thời gian trôi qua. Không để test giả định một ngày sunset đã hết hạn vẫn còn ở tương lai.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Đổi relation chỉ vì path chuyển từ v1 sang v2 | Client phải sửa dù semantics không đổi. | Giữ relation, cập nhật `href`. |
| Giữ relation khi semantics đổi không tương thích | Client có thể thực hiện sai capability hoặc hiểu sai target. | Tạo relation URI mới và tài liệu hóa migration. |
| Dùng target path làm relation | Client phụ thuộc vào route. | Dùng relation URI ổn định và lấy target từ `href`. |
| Công bố hai target khác version cùng relation nhưng không có quy tắc chọn | Client không biết chọn link nào. | Dùng relation version riêng hoặc quy định cardinality rõ ràng. |
| Dùng `alternate` cho mọi API version | Client hiểu sai alternate representation thành phiên bản kế tiếp. | Chỉ dùng khi target là alternative đúng semantics; dùng successor/predecessor khi phù hợp. |
| Dùng `profile` thay cho version mà không định nghĩa profile | Client không biết khác biệt hợp đồng. | Tài liệu hóa profile và cách client chọn nó. |
| Tái sử dụng relation URI cũ cho semantics mới | Client cũ diễn giải sai. | Giữ URI cũ bất biến về semantics; tạo URI mới. |
| Bỏ endpoint cũ ngay khi công bố v2 | Client chưa nâng cấp bị gián đoạn. | Có thời gian deprecation/sunset và lộ trình migration. |
| Chỉ kiểm tra route, không kiểm tra relation | Test bỏ sót hợp đồng hypermedia. | Kiểm tra cả relation, target và media type/profile. |

## Ghi nhớ

- API version, representation version/profile và link relation semantics là ba khái niệm khác nhau.
- Giữ relation URI ổn định khi chỉ thay target URI hoặc route mà semantics không đổi.
- Tạo relation mới khi semantics thay đổi không tương thích; không tái sử dụng URI cũ cho ý nghĩa mới.
- Dùng relation riêng cho các version cùng được công bố nếu client cần lựa chọn rõ; không để nhiều target cùng relation mà thiếu quy tắc.
- `alternate` dùng cho representation/resource thay thế; `profile` trỏ đến tài liệu profile; không relation nào tự thay thế API versioning policy.
- `successor-version`, `predecessor-version` và `version-history` hỗ trợ điều hướng lịch sử phiên bản khi đúng semantics.
- Dùng `IanaLinkRelations` cho relation chuẩn và `LinkRelation` cho extension relation.
- CURIE rút gọn extension relation URI trong HAL; nó không thay đổi semantics.
- Dùng `Deprecation`, `Sunset` và relation `deprecation` để công bố vòng đời hỗ trợ khi phù hợp.
- Kiểm thử relation, target URI, media type/profile, migration links và deprecation headers.

## Tài liệu tham khảo

- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 5829 – Link Relation Types for Simple Version Navigation between Web Resources](https://www.rfc-editor.org/rfc/rfc5829.html)
- [RFC 6906 – The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906.html)
- [RFC 9745 – The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html)
- [RFC 8594 – The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html)
- [IANA Link Relations Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS API – IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS API – LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
