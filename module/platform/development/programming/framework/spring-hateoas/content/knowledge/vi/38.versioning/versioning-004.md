# Version trong profile

Trong API hypermedia, **profile** mô tả semantics của một loại resource: các thuộc tính có ý nghĩa gì, relation nào được công bố và những state transition nào client có thể khám phá. Khi semantics thay đổi theo thời gian, profile cũng cần được quản lý phiên bản để client biết mình đang đọc hợp đồng nào.

ALPS (*Application-Level Profile Semantics*) có trường `version` ở cấp profile. Spring HATEOAS biểu diễn ALPS profile bằng `Alps` và cho phép công bố profile qua media type `application/alps+json`. Ngoài version metadata, API có thể định danh từng profile bằng URI và công bố URI đó qua relation `profile` theo RFC 6906.

Bài học này thuộc chương **Versioning** trong module **SPRING_HATEOAS**, tập trung vào ý nghĩa của version trong ALPS profile, cách đặt profile URI, phân biệt profile version với API version và media type version, chiến lược thay đổi tương thích, cách client khám phá profile và cách kiểm thử profile version.

Sau bài học, bạn có thể:

- Giải thích profile và vai trò của ALPS trong API hypermedia.
- Đọc trường `version` trong ALPS document.
- Tạo ALPS profile có version bằng Spring HATEOAS.
- Công bố profile URI bằng relation `profile`.
- Phân biệt relation `profile` với thuộc tính `profile` của một link.
- Thiết kế URI profile ổn định hoặc có version.
- Phân biệt profile version, resource/API version và media type version.
- Đánh giá thay đổi profile theo mức tương thích.
- Giúp client khám phá, lưu cache và kiểm thử đúng profile version.

## 1. Profile mô tả semantics của resource

Một media type như `application/hal+json` cho biết cấu trúc JSON được biểu diễn theo HAL: link nằm trong `_links`, embedded resource nằm trong `_embedded`. Nhưng chỉ biết media type HAL chưa đủ để hiểu ý nghĩa nghiệp vụ của từng field hoặc relation.

Profile bổ sung phần semantics đó. Ví dụ profile của resource đơn hàng có thể mô tả:

- `status` là trạng thái nghiệp vụ của đơn hàng.
- `total` là tổng giá trị phải thanh toán.
- `customer` là quan hệ tới khách hàng của đơn hàng.
- `cancel` là transition yêu cầu hủy đơn hàng.
- `payment` là transition khởi tạo thanh toán khi đơn hàng đang chờ thanh toán.

ALPS mô tả các descriptor ngữ nghĩa và transition ở mức application. Nó không thay thế HAL, JSON Schema hoặc tài liệu validation. HAL mang representation; ALPS giải thích semantics của representation và các transition mà profile định nghĩa.

## 2. Trường version trong ALPS profile

ALPS document có trường `version` ở cấp profile. Một tài liệu JSON có thể có dạng:

```json
{
  "alps": {
    "version": "1.0",
    "doc": {
      "format": "text",
      "value": "Profile mô tả semantics của resource Order."
    },
    "descriptor": [
      {
        "id": "order-status",
        "name": "status",
        "type": "SEMANTIC"
      },
      {
        "id": "cancel-order",
        "name": "cancel",
        "type": "UNSAFE",
        "rt": "#order"
      }
    ]
  }
}
```

`version` là metadata của profile document. Nó cho client và người đọc biết phiên bản semantics mà tài liệu mô tả. Giá trị thường là chuỗi như `1.0`, `1.1` hoặc `2.0`.

ALPS không áp đặt một chính sách semantic versioning duy nhất cho giá trị này. Tổ chức API cần tự định nghĩa quy ước: thay đổi nào tăng minor version, thay đổi nào tăng major version, và profile URI nào tương ứng với từng phiên bản.

Trường `version` không tự động chọn controller, đổi route, thay schema response hoặc ép server từ chối client dùng phiên bản cũ. Nó là metadata mô tả profile. Cơ chế phục vụ profile version nào phải được thiết kế riêng bằng URI, content negotiation hoặc chính sách tương thích của API.

## 3. Tạo ALPS profile có version bằng Spring HATEOAS

Spring HATEOAS cung cấp `Alps` cùng builder để tạo profile. Có thể đặt version trước khi thêm descriptor:

```java
import java.util.List;

import org.springframework.hateoas.mediatype.alps.Alps;
import org.springframework.hateoas.mediatype.alps.Descriptor;
import org.springframework.hateoas.mediatype.alps.Type;

Alps orderProfile = Alps.alps()
        .version("1.0")
        .descriptor(List.of(
                Descriptor.builder()
                        .id("order")
                        .descriptor(List.of(
                                Descriptor.builder()
                                        .id("order-status")
                                        .name("status")
                                        .type(Type.SEMANTIC)
                                        .build(),
                                Descriptor.builder()
                                        .id("order-total")
                                        .name("total")
                                        .type(Type.SEMANTIC)
                                        .build()))
                        .build(),
                Descriptor.builder()
                        .id("cancel-order")
                        .name("cancel")
                        .type(Type.UNSAFE)
                        .rt("#order")
                        .build()))
        .build();
```

Ví dụ tạo profile version `1.0`, mô tả resource `order`, hai semantic descriptor `status` và `total`, cùng transition `cancel`. Khi serialize bằng ALPS media type, version được đặt ở metadata của profile document.

Có thể trả profile từ controller:

```java
import org.springframework.hateoas.mediatype.alps.Alps;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderProfileController {

    private final Alps orderProfile;

    OrderProfileController(Alps orderProfile) {
        this.orderProfile = orderProfile;
    }

    @GetMapping(
            value = "/profiles/orders/1.0",
            produces = "application/alps+json")
    Alps orderProfileV1() {
        return orderProfile;
    }
}
```

Trong ứng dụng, nên tạo profile bằng một bean hoặc factory có thể kiểm thử thay vì dựng toàn bộ descriptor trong controller. Endpoint cần trả đúng `application/alps+json`; nếu dùng nhiều phiên bản, mỗi URI phải trả profile tương ứng với version được công bố.

## 4. Version của profile và URI định danh profile

Profile cần một định danh URI để resource có thể liên kết tới tài liệu semantics. Có hai cách phổ biến:

| Chiến lược | Ví dụ | Khi phù hợp |
|---|---|---|
| URI ổn định | `/profiles/orders` | Profile luôn mô tả semantics hiện hành; client theo URI để lấy tài liệu mới nhất. |
| URI có version | `/profiles/orders/1.0`, `/profiles/orders/2.0` | Client cần tham chiếu chính xác một bản profile và so sánh các thế hệ semantics. |

URI ổn định thuận tiện cho discovery nhưng nội dung tại URI có thể thay đổi theo thời gian. Nếu client cần tái lập hoặc cache một hợp đồng cố định, URI có version giúp xác định rõ profile document.

URI có version không bắt buộc phải chứa đúng chuỗi trường `version`, nhưng nên nhất quán để con người dễ nhận biết. Ví dụ `/profiles/orders/2.0` nên trả ALPS document có `version: "2.0"`. Nếu URI và metadata không khớp, client và người vận hành khó xác định profile nào đang được phục vụ.

Đừng tạo URI mới cho mọi chỉnh sửa văn bản hoặc bổ sung descriptor không ảnh hưởng semantics hiện tại. Hãy dùng chính sách compatibility để quyết định thay đổi nào cần version mới.

## 5. Công bố profile bằng relation profile

RFC 6906 định nghĩa relation `profile` để liên kết một resource tới tài liệu mô tả profile áp dụng cho resource đó. Với HAL, API có thể công bố một link `profile`:

```json
{
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "profile": {
      "href": "/profiles/orders/1.0"
    }
  },
  "id": 42,
  "status": "PENDING",
  "total": 125000
}
```

Client theo relation `profile` để tải ALPS document. URI của profile là đích mô tả semantics, còn URI trong `self` là đích của resource đơn hàng.

Trong Spring HATEOAS, có thể thêm link profile như một link thông thường:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

Link profile = Link.of("/profiles/orders/1.0").withRel("profile");

EntityModel<OrderResponse> model = EntityModel.of(orderResponse, profile);
```

Có thể định nghĩa relation chuẩn `profile` bằng hằng số IANA nếu phiên bản Spring HATEOAS đang dùng cung cấp hằng tương ứng; dùng chuỗi `"profile"` cũng thể hiện rõ relation trong ví dụ.

## 6. Phân biệt relation profile và thuộc tính profile của Link

HAL link object cũng có metadata property tên `profile`. Nó không giống relation key `profile` ở `_links`.

**Relation `profile`:** một link có relation là `profile`, trỏ tới tài liệu mô tả profile.

**Property `profile` của link object:** metadata trên một link khác, cho biết profile áp dụng cho resource đích của link đó.

Ví dụ:

```json
{
  "_links": {
    "profile": {
      "href": "/profiles/orders/1.0"
    },
    "self": {
      "href": "/orders/42",
      "profile": "/profiles/orders/1.0"
    }
  }
}
```

Trong ví dụ, `_links.profile.href` là link dẫn tới profile document. Property `profile` nằm bên trong link `self` mô tả profile của resource mà `self.href` trỏ tới.

Spring HATEOAS `Link` hỗ trợ metadata profile:

```java
Link self = Link.of("/orders/42")
        .withSelfRel()
        .withProfile("/profiles/orders/1.0");
```

Khi dùng `withProfile(...)`, profile được gắn như metadata của link object. Nó không tự thêm một relation `profile` riêng vào `_links`. Nếu client cần khám phá profile document qua relation, hãy thêm link `profile` rõ ràng.

## 7. Khám phá profile từ API root

Một client có thể bắt đầu từ API root, theo các link tới resource và profile thay vì tự ghép URL:

```json
{
  "_links": {
    "orders": {
      "href": "/orders"
    },
    "profile": {
      "href": "/profile"
    }
  }
}
```

Profile root có thể cung cấp link tới profile cụ thể:

```json
{
  "_links": {
    "self": { "href": "/profile" },
    "orders": { "href": "/profiles/orders/1.0" },
    "customers": { "href": "/profiles/customers/1.0" }
  }
}
```

Với Spring Data REST, profile endpoint và link profile được framework cung cấp cho repository resource đã export. Với controller tự viết, ứng dụng cần chủ động thêm link profile hoặc xây dựng profile root nếu muốn client khám phá theo cùng quy ước.

Client nên lấy URI profile từ relation trong response. URI ví dụ trong tài liệu chỉ minh họa cấu trúc; host, context path và prefix có thể khác giữa các môi trường.

## 8. Profile version không phải API version

Profile version và API version giải quyết hai vấn đề liên quan nhưng khác nhau:

| Khái niệm | Mô tả | Ví dụ |
|---|---|---|
| Profile version | Phiên bản tài liệu semantics của resource và transition | ALPS `version: "2.0"`. |
| API/resource version | Phiên bản hợp đồng endpoint hoặc representation được server phục vụ | `/api/v2/orders/42`. |
| Media type version | Phiên bản được thể hiện trong media type do API định nghĩa | `application/vnd.example.order-v2+json`. |
| HAL version/format | Cấu trúc hypermedia mà client parse | `application/hal+json`. |

Một API `/api/v2/orders` có thể dùng profile `orders/2.0`, nhưng không có quy tắc bắt buộc hai số version phải giống nhau. API có thể giữ route `/orders` nhưng công bố profile mới nếu semantics thay đổi theo chính sách tương thích.

Ngược lại, một profile có thể mô tả semantics dùng chung bởi nhiều endpoint hoặc nhiều media type. Không nên đổi profile version chỉ vì server thay đổi host, port hoặc route mà semantics vẫn giữ nguyên.

## 9. Profile version không phải phiên bản của HAL media type

`application/hal+json` xác định cách cấu trúc link và embedded resource. ALPS profile xác định semantics của resource. Hai khái niệm độc lập:

- Server có thể giữ HAL media type trong khi nâng profile từ `1.0` lên `2.0`.
- Server có thể thay đổi profile document mà không thay đổi cấu trúc JSON HAL.
- Server có thể cung cấp cùng semantics qua một media type khác nếu hợp đồng cho phép.

Không tự thêm tham số `version` hoặc `profile` vào `Content-Type` rồi kỳ vọng mọi client và intermediary hiểu cùng một quy ước. Chỉ dùng media type parameter khi định dạng hoặc hợp đồng của API định nghĩa rõ cách thương lượng và xử lý parameter đó.

Nếu cần phân biệt representation version qua content negotiation, hãy định nghĩa media type và quy tắc `Accept`/`Content-Type` rõ ràng, đồng thời kiểm thử server chọn đúng representation. Profile link vẫn có thể được dùng để mô tả semantics của representation đã chọn.

## 10. Khi nào cần tăng version của profile?

Profile version nên phản ánh thay đổi semantics mà client phụ thuộc, không phải mọi thay đổi nội bộ của server.

| Thay đổi | Tác động thường gặp | Hướng version |
|---|---|---|
| Sửa lỗi chính tả trong `doc` | Không đổi semantics | Có thể giữ version. |
| Bổ sung descriptor tùy chọn mới | Client cũ có thể bỏ qua nếu không phụ thuộc vào nó | Minor version theo chính sách. |
| Thêm relation mới nhưng giữ nguyên relation cũ | Thường tương thích nếu client bỏ qua relation chưa biết | Minor version theo chính sách. |
| Đổi nghĩa descriptor hiện có | Client có thể diễn giải sai dữ liệu | Major version mới. |
| Xóa relation/descriptor mà client đang dùng | Client cũ có thể hỏng | Major version mới hoặc giai đoạn deprecation. |
| Đổi transition từ `SAFE` sang `UNSAFE` | Thay đổi cách client được phép thực hiện | Major version mới và tài liệu migration. |
| Thay input bắt buộc hoặc semantics của action | Client cũ có thể không gửi request hợp lệ | Major version mới. |

ALPS không quy định bảng tương thích này. Đây là chính sách quản trị API mà nhóm phát triển cần công bố. Điều quan trọng là không thay đổi semantics của descriptor hiện có mà vẫn giữ cùng profile version nếu client có thể hiểu sai hợp đồng.

## 11. Chiến lược URI ổn định và URI bất biến theo version

Có thể chọn một trong hai chiến lược chính:

**URI ổn định trỏ tới profile mới nhất**

```text
/profiles/orders
```

Client luôn lấy profile mới nhất tại URI này. Cách này đơn giản cho discovery, nhưng nội dung profile có thể thay đổi. Nếu client cache lâu hoặc cần tái lập một phiên bản cụ thể, cần ETag/Last-Modified và quy tắc tương thích rõ ràng.

**URI riêng cho từng version**

```text
/profiles/orders/1.0
/profiles/orders/1.1
/profiles/orders/2.0
```

URI của profile đã phát hành nên giữ nội dung ổn định. Khi có thay đổi semantics không tương thích, tạo profile URI mới và tiếp tục phục vụ profile cũ trong thời gian migration. Cách này thuận tiện cho client pin profile version và cho tài liệu lịch sử.

Một API có thể kết hợp cả hai: `/profiles/orders` trỏ tới profile mới nhất hoặc cung cấp link tới version hiện hành, trong khi URI có version giữ từng profile đã phát hành. Tài liệu cần nói rõ URI ổn định có thể đổi nội dung hay chỉ là alias.

## 12. Quản lý tương thích giữa các profile version

Khi phát hành `2.0`, không nên chỉ thay chuỗi version trong JSON. Cần xác định thay đổi semantics và lộ trình client:

1. Liệt kê descriptor, relation và transition của profile hiện tại.
2. Phân loại từng thay đổi là tương thích hay phá vỡ.
3. Tạo profile mới với URI và trường `version` nhất quán.
4. Giữ profile cũ trong thời gian client chuyển đổi nếu có thể.
5. Ghi relation/descriptor bị thay thế và cách chuyển sang descriptor mới.
6. Cập nhật tài liệu workflow, ví dụ request/response và test contract.
7. Theo dõi client còn dùng profile cũ trước khi ngừng hỗ trợ.

Không xóa profile cũ chỉ vì server đã phát hành version mới. Một profile URI có thể được client lưu lâu trong cấu hình hoặc tài liệu tích hợp. Nếu phải ngừng hỗ trợ, hãy công bố thời hạn, replacement URI và cách xử lý response khi profile cũ không còn được phục vụ.

## 13. Cache profile document

Profile document thường thay đổi ít hơn resource data và có thể được cache. Với URI versioned bất biến, cache dài hạn có thể phù hợp. Với URI stable trỏ tới profile mới nhất, nên dùng validator như `ETag` hoặc `Last-Modified` để client kiểm tra nội dung đã thay đổi.

Ví dụ header:

```http
HTTP/1.1 200 OK
Content-Type: application/alps+json
ETag: "orders-profile-2.0"
Cache-Control: public, max-age=3600
```

Client có thể gửi `If-None-Match` để kiểm tra profile document có thay đổi không. Nếu profile versioned là immutable, ETag có thể tồn tại ổn định theo nội dung; nếu profile URI trỏ latest, validator phải thay đổi khi profile thay đổi.

Đừng dùng cùng ETag cho hai nội dung profile khác nhau. Nếu profile phụ thuộc tenant hoặc quyền người dùng, cache policy phải phản ánh điều đó; profile công khai, không nhạy cảm thường dễ cache hơn profile cá nhân hóa.

## 14. Client sử dụng profile version như thế nào?

Client nên xử lý profile theo trình tự:

1. Gọi API root hoặc resource entry point.
2. Tìm relation `profile` và lấy `href` từ response.
3. Gọi profile URI với `Accept: application/alps+json`.
4. Đọc `alps.version` và descriptor.
5. Xác định profile version có nằm trong tập version client hỗ trợ không.
6. Nếu hỗ trợ, tiếp tục theo relation và transition được mô tả.
7. Nếu không hỗ trợ, dùng fallback an toàn, thông báo không tương thích hoặc chọn endpoint/profile version khác theo hợp đồng.

Ví dụ pseudo-code:

```javascript
async function loadOrderProfile(orderDocument) {
  const profileHref = orderDocument?._links?.profile?.href;
  if (!profileHref) {
    throw new Error("Order resource does not advertise a profile");
  }

  const response = await fetch(profileHref, {
    headers: { Accept: "application/alps+json" }
  });

  if (!response.ok) {
    throw new Error(`Cannot load profile: HTTP ${response.status}`);
  }

  const document = await response.json();
  const version = document?.alps?.version;

  if (!["1.0", "1.1"].includes(version)) {
    throw new Error(`Unsupported order profile version: ${version}`);
  }

  return document.alps;
}
```

Ví dụ client hỗ trợ `1.0` và `1.1`; danh sách version là chính sách của client, không phải giới hạn do ALPS áp đặt. Client không nên giả định một version chưa biết tương thích chỉ vì JSON vẫn parse được.

## 15. Kiểm thử profile version bằng MockMvc

Test cần xác nhận resource công bố đúng profile URI và endpoint profile trả đúng version:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderProfileVersionTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderResourceAdvertisesVersionedProfile() throws Exception {
        mockMvc.perform(get("/orders/42").accept("application/hal+json"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.profile.href")
                        .value(endsWith("/profiles/orders/1.0")));
    }

    @Test
    void profileDocumentDeclaresItsVersion() throws Exception {
        mockMvc.perform(get("/profiles/orders/1.0")
                        .accept("application/alps+json"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.valueOf("application/alps+json")))
                .andExpect(jsonPath("$.alps.version").value("1.0"));
    }
}
```

Test giả định resource `/orders/42` công bố profile link có version `1.0`, còn endpoint `/profiles/orders/1.0` trả ALPS document. Nếu ứng dụng dùng root object hoặc JSON serializer khác, điều chỉnh JSONPath theo representation ALPS thực tế nhưng vẫn kiểm tra trường version.

## 16. Kiểm thử tương thích giữa hai profile version

Khi có `1.0` và `2.0`, nên kiểm tra cả hai URI và các descriptor quan trọng:

```java
@Test
void oldProfileRemainsAvailableDuringMigration() throws Exception {
    mockMvc.perform(get("/profiles/orders/1.0")
                    .accept("application/alps+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.alps.version").value("1.0"))
            .andExpect(jsonPath("$.alps.descriptor[?(@.id == 'cancel-order')]")
                    .exists());
}

@Test
void newProfileDeclaresNewSemantics() throws Exception {
    mockMvc.perform(get("/profiles/orders/2.0")
                    .accept("application/alps+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.alps.version").value("2.0"))
            .andExpect(jsonPath("$.alps.descriptor[?(@.id == 'request-refund')]")
                    .exists());
}
```

Các assertion descriptor minh họa một thay đổi semantics. Test thật nên kiểm tra các descriptor và transition mà client phụ thuộc, không chỉ kiểm tra chuỗi version. Nếu profile `2.0` thay đổi hoặc loại bỏ transition `cancel`, tài liệu migration cần giải thích hành vi thay thế.

## 17. Deprecation của profile version cũ

Khi muốn ngừng hỗ trợ profile cũ, cần có lộ trình rõ ràng:

- Tiếp tục phục vụ profile cũ trong giai đoạn chuyển tiếp.
- Tài liệu hóa version mới và khác biệt semantics.
- Công bố link tới tài liệu migration hoặc profile thay thế.
- Ghi thời điểm dự kiến ngừng hỗ trợ.
- Theo dõi việc sử dụng profile cũ trước khi loại bỏ.

Có thể công bố link `deprecation` trong resource hoặc trong tài liệu profile để dẫn tới hướng dẫn chuyển đổi. Metadata deprecation là tín hiệu cho client; nó không tự động ngừng endpoint hay profile cũ.

Ví dụ resource có link tới profile hiện hành và tài liệu migration:

```json
{
  "_links": {
    "profile": {
      "href": "/profiles/orders/2.0"
    },
    "old-profile-migration": {
      "href": "/docs/migrations/orders-profile-1-to-2"
    }
  }
}
```

Nếu cần đánh dấu một link là deprecated, dùng metadata `deprecation` trên link theo mô hình Spring HATEOAS và giải thích URI tài liệu đó chứa gì. Không dùng trường `version` để biểu thị trạng thái deprecated.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Coi `alps.version` là API version tự động | Client kỳ vọng server chọn route hoặc representation theo trường này. | Xem đây là metadata; định nghĩa cơ chế phục vụ version riêng. |
| Đổi semantics nhưng giữ nguyên version và URI | Client cũ có thể diễn giải sai descriptor. | Tạo version mới khi thay đổi không tương thích. |
| Đổi profile version chỉ vì đổi host hoặc route | Version profile bị gắn với triển khai hạ tầng. | Chỉ tăng version khi semantics profile thay đổi theo policy. |
| Cho rằng relation `profile` và `Link.profile` giống nhau | Client không tìm thấy profile document hoặc hiểu sai metadata. | Phân biệt link relation với property profile của link object. |
| Cho rằng HAL media type version chính là profile version | Nhầm format JSON với semantics nghiệp vụ. | Quản lý HAL, API version và profile version độc lập. |
| URI có version nhưng document version không khớp | Khó xác định profile thực sự được phục vụ. | Kiểm thử URI và `alps.version` cùng nhau. |
| Sửa nội dung tại URI versioned đã phát hành | Client pin URI cũ nhận semantics mới ngoài dự kiến. | Giữ URI versioned ổn định; phát hành URI mới khi cần. |
| Xóa profile cũ ngay khi phát hành bản mới | Client cũ bị lỗi đột ngột. | Duy trì migration window và công bố deprecation. |
| Chỉ kiểm thử trường version | Descriptor hoặc transition có thể sai mà test vẫn pass. | Kiểm tra các descriptor client thực sự sử dụng. |

## 19. Quy trình quản lý version trong profile

1. Xác định semantics resource, relation và transition mà profile mô tả.
2. Tạo ALPS document và đặt `version` theo quy ước của tổ chức.
3. Chọn profile URI ổn định hoặc URI có version; ghi rõ chính sách thay đổi nội dung.
4. Công bố URI bằng relation `profile` và, khi phù hợp, metadata `profile` trên link resource.
5. Phân biệt profile version với API/resource version và media type version.
6. Phân loại thay đổi descriptor theo mức tương thích trước khi phát hành.
7. Giữ profile cũ trong thời gian migration nếu client còn sử dụng.
8. Dùng ETag/Last-Modified và cache policy phù hợp với URI stable hoặc versioned.
9. Kiểm thử profile link, media type, `alps.version` và descriptor quan trọng qua HTTP.
10. Tài liệu hóa deprecation, replacement URI và thời điểm ngừng hỗ trợ.

Version trong profile giúp client nhận diện phiên bản semantics mà resource đang công bố. Khi ALPS version, profile URI và chính sách tương thích được quản lý nhất quán, API có thể tiến hóa mà client vẫn khám phá được hợp đồng, lựa chọn cách xử lý phù hợp và chuyển đổi có lộ trình.

## Tài liệu tham khảo

- [Spring HATEOAS – ALPS media type](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.alps)
- [Spring HATEOAS – Alps API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/alps/Alps.html)
- [Spring HATEOAS – Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [RFC 6906 – The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906)
- [ALPS – Application-Level Profile Semantics](https://alps.io/)
