# Tài liệu resource

Trong API HATEOAS, một resource được mô tả bằng representation, các thuộc tính dữ liệu và những link cho phép client khám phá resource liên quan hoặc thực hiện transition. Tài liệu resource cần giúp người tích hợp hiểu resource đại diện cho điều gì, cách tìm nó, các field có ý nghĩa gì và client có thể làm gì với representation đang nhận.

Spring HATEOAS cung cấp mô hình `RepresentationModel`, `EntityModel`, `CollectionModel`, link và affordance để xây representation. Spring REST Docs có thể tạo tài liệu từ HTTP test thực tế, gồm snippet cho link, field, parameter, header và request/response. Kết hợp hai công cụ giúp trang tài liệu mô tả đúng hợp đồng mà server đang phát ra.

Bài học này thuộc chương **Tài liệu HATEOAS** trong module **SPRING_HATEOAS**, tập trung vào cách viết tài liệu cho một resource: danh tính và URI entry point, media type, cấu trúc representation, field semantics, relation, affordance, association/embedded resource, request và response, cùng cách tạo snippet bằng Spring REST Docs.

Sau bài học, bạn có thể:

- Xác định thông tin cần có trên một trang tài liệu resource.
- Mô tả representation và field theo semantics thay vì tên thuộc tính đơn thuần.
- Tài liệu hóa relation, điều kiện xuất hiện và đích của link.
- Phân biệt association link với embedded resource.
- Mô tả affordance, method, input, output và điều kiện thực hiện.
- Dùng Spring REST Docs tạo snippet link và field từ MockMvc test.
- Tổ chức tài liệu cho item resource, collection resource và thao tác ghi.
- Duy trì ví dụ, media type, status code và tài liệu đồng bộ với API.

## 1. Một trang tài liệu resource cần trả lời điều gì?

Tài liệu resource nên cho người đọc biết cách khám phá, đọc và tương tác với resource mà không cần suy đoán từ URL hoặc tên class Java.

| Phần | Câu hỏi cần trả lời |
|---|---|
| Mục đích | Resource đại diện cho khái niệm nghiệp vụ nào? |
| Entry point | Client tìm resource từ API root hoặc relation nào? |
| Media type | Server trả HAL, HAL-FORMS hay representation khác? |
| Representation | Field nào xuất hiện, kiểu dữ liệu và ý nghĩa của chúng? |
| Links | Relation nào được công bố và khi nào relation xuất hiện? |
| Affordances | Có thể thực hiện hành động nào, bằng method và input nào? |
| Associations | Resource liên kết với resource nào; link hay embedded representation được dùng? |
| HTTP contract | Status, header, request body và response body ra sao? |
| Security | Cần authentication, authority hoặc quyền trên resource nào? |
| Evolution | Field/link nào ổn định, deprecated hoặc có profile mô tả? |

Ví dụ, trang tài liệu `Order` không nên chỉ nói endpoint là `GET /orders/{id}`. Client cần biết cách tìm link `orders` từ API root, theo `self` tới item, dùng `customer` để mở khách hàng và chỉ hiển thị hành động `cancel` khi server công bố relation đó.

## 2. Mô tả resource bằng ngôn ngữ nghiệp vụ

Mở đầu trang bằng mục đích và ranh giới của resource. Tránh bắt đầu bằng tên controller, repository hoặc entity vì đó là chi tiết triển khai.

Ví dụ:

> **Order** đại diện cho một yêu cầu mua hàng đã được hệ thống tiếp nhận. Resource mô tả trạng thái xử lý, tổng tiền và các liên kết tới khách hàng, thanh toán, vận chuyển. Client khám phá thao tác tiếp theo qua các relation mà server công bố theo trạng thái hiện tại.

Phần giới thiệu nên nêu rõ:

- Ai hoặc hệ thống nào sở hữu vòng đời resource.
- Resource có định danh ổn định hay chỉ tồn tại trong một workflow.
- Quan hệ với resource khác.
- Trạng thái nghiệp vụ quan trọng.
- Những điều client không nên suy ra từ representation.

Không mô tả semantics bằng cách sao chép comment của entity. Ví dụ field `status` cần giải thích các giá trị nghiệp vụ và transition có thể xảy ra, không chỉ ghi “trạng thái của đơn hàng”.

## 3. Tài liệu hóa cách khám phá resource

API HATEOAS nên cung cấp entry point để client bắt đầu điều hướng. Trang tài liệu có thể chỉ ra URI gốc dùng trong môi trường ví dụ, nhưng phải nhấn mạnh client nên theo link relation từ response.

Ví dụ API root:

```http
GET /api HTTP/1.1
Accept: application/hal+json
```

```json
{
  "_links": {
    "self": { "href": "/api" },
    "orders": { "href": "/api/orders" },
    "customers": { "href": "/api/customers" }
  }
}
```

Từ đó client theo relation `orders` để lấy collection, sau đó theo relation `self` của một item để lấy chi tiết. Trong tài liệu, ghi rõ base URL chỉ là ví dụ và client không nên ghép `/api/orders/{id}` từ một quy ước URL tự đoán.

Nếu API có nhiều entry point theo tenant hoặc phiên bản, hãy mô tả cách client nhận entry point phù hợp và cách xác định profile hoặc media type được hỗ trợ.

## 4. Mô tả media type và representation

Một resource có thể có nhiều representation. Tài liệu cần nói rõ media type mà endpoint hỗ trợ và nội dung nào được biểu diễn trong mỗi loại.

| Media type | Mục đích | Nội dung đáng chú ý |
|---|---|---|
| `application/hal+json` | Resource JSON có link theo HAL | `_links`, `_embedded` và các field dữ liệu. |
| `application/prs.hal-forms+json` | HAL kèm form template | `_links` và `_templates` mô tả thao tác cùng input. |
| `application/problem+json` | Nội dung lỗi theo RFC 9457 | `type`, `title`, `status`, `detail`, `instance` và extension fields. |
| `application/json` | JSON không có cấu trúc hypermedia bắt buộc | Chỉ dùng nếu API công bố representation này như một phần hợp đồng. |

Ví dụ request:

```http
GET /api/orders/42 HTTP/1.1
Accept: application/hal+json
```

Tài liệu cần phân biệt request `Accept` với response `Content-Type`. Nếu server hỗ trợ nhiều representation, ghi rõ cách content negotiation hoạt động và client nên gửi media type nào.

Không gộp error representation vào ví dụ HAL thành công. Khi request thất bại, response có thể dùng `application/problem+json`; client cần chọn parser theo `Content-Type` thực tế.

## 5. Mô tả cấu trúc representation

Ví dụ item resource `Order`:

```json
{
  "id": 42,
  "orderNumber": "ORD-2026-0042",
  "status": "PENDING",
  "total": {
    "amount": 125000,
    "currency": "VND"
  },
  "createdAt": "2026-11-26T08:30:00Z",
  "_links": {
    "self": { "href": "/api/orders/42" },
    "customer": { "href": "/api/customers/7" },
    "cancel": { "href": "/api/orders/42/cancellation" }
  }
}
```

Không chỉ đưa JSON mẫu. Sau ví dụ, hãy có bảng mô tả field:

| Field | Kiểu | Ý nghĩa | Ghi chú |
|---|---|---|---|
| `id` | Integer | Định danh nội bộ của đơn hàng | Chỉ dùng để hiển thị hoặc đối chiếu nếu hợp đồng cho phép. |
| `orderNumber` | String | Mã đơn hàng hiển thị cho người dùng | Không nhất thiết là URI của resource. |
| `status` | String | Trạng thái nghiệp vụ hiện tại | Giá trị ví dụ: `PENDING`, `PAID`, `SHIPPED`, `CANCELLED`. |
| `total.amount` | Number | Số tiền theo đơn vị nhỏ nhất hoặc quy ước tiền tệ đã công bố | Nêu rõ quy tắc scale. |
| `total.currency` | String | Mã tiền tệ | Ví dụ mã ISO 4217 `VND`. |
| `createdAt` | String/date-time | Thời điểm tạo đơn hàng | ISO 8601, UTC trong ví dụ. |

Với mỗi field, ghi kiểu, ý nghĩa, định dạng, nullability, tính bắt buộc và điều kiện xuất hiện. Nếu field có thể vắng mặt, phân biệt “không được gửi” với “được gửi bằng `null`”; hai trường hợp có thể mang semantics khác nhau.

## 6. Mô tả field có thể thay đổi hoặc chỉ đọc

Không phải field nào xuất hiện trong response cũng có thể gửi trong request. Ví dụ `id`, `createdAt` và `status` có thể chỉ đọc; client không được tự cập nhật chúng qua payload tạo đơn hàng.

Nên ghi rõ:

- `read-only`: server quản lý, client không gửi khi tạo/cập nhật.
- `write-only`: client gửi nhưng server không trả lại, ví dụ secret hoặc credential nếu API có lý do hợp lệ để nhận.
- `required`: bắt buộc trong request cụ thể, không nhất thiết bắt buộc trong mọi representation.
- `nullable`: field có thể mang giá trị JSON `null`.
- `optional`: field có thể không xuất hiện.
- `deprecated`: field còn được hỗ trợ trong giai đoạn chuyển đổi.

Ví dụ bảng request:

| Field | Required | Read-only | Quy tắc |
|---|---:|---:|---|
| `customerId` | Có | Không | Khách hàng phải tồn tại và người gọi phải có quyền đặt hàng cho khách hàng đó. |
| `items` | Có | Không | Ít nhất một dòng hàng; mỗi dòng có product và quantity hợp lệ. |
| `status` | Không nhận | Có | Server khởi tạo trạng thái theo workflow. |
| `createdAt` | Không nhận | Có | Server ghi nhận thời điểm tạo. |

Tránh dùng một bảng field chung cho cả request và response nếu các quy tắc khác nhau. Tách request fields và response fields để client biết dữ liệu nào được gửi và dữ liệu nào chỉ được đọc.

## 7. Tài liệu hóa relation trong `_links`

Relation là tên ngữ nghĩa mà client dùng để tìm link. Tài liệu cần giải thích ý nghĩa relation và điều kiện server công bố nó.

Ví dụ bảng links cho `Order`:

| Relation | Ý nghĩa | Điều kiện xuất hiện | Cách dùng |
|---|---|---|---|
| `self` | URI của đơn hàng hiện tại | Có trên item resource | GET representation mới nhất. |
| `customer` | Khách hàng liên quan | Khi đơn hàng có khách hàng | Theo link để đọc resource khách hàng. |
| `cancel` | Điểm truy cập yêu cầu hủy | Đơn hàng còn được hủy và principal đủ quyền | Gửi request theo affordance được công bố. |
| `payment` | Điểm truy cập thanh toán | Đơn hàng đang chờ thanh toán | Khởi tạo workflow thanh toán. |
| `receipt` | Biên nhận thanh toán | Sau khi thanh toán thành công | Theo link để đọc biên nhận. |

Với extension relation, ghi URI định danh hoặc CURIE prefix và nơi mô tả semantics. Không tạo relation dựa trên tên controller hay tên role nội bộ.

Đừng chỉ ghi `href` mẫu. URI có thể đổi theo context path, gateway hoặc deployment. Client phải dùng `href` do server gửi và tìm nó bằng relation đã tài liệu hóa.

## 8. Tài liệu hóa link có điều kiện

Một relation có thể xuất hiện hoặc biến mất theo state, ownership hoặc quyền. Trang resource nên mô tả điều kiện để client hiểu vì sao một action link không có trong response.

Ví dụ:

| Trạng thái | Relation có thể xuất hiện |
|---|---|
| `PENDING` | `self`, `customer`, `cancel`, `payment` |
| `PAID` | `self`, `customer`, `receipt` |
| `SHIPPED` | `self`, `customer`, `tracking` |
| `CANCELLED` | `self`, `customer` |

Điều kiện quyền có thể làm thay đổi link ngay cả khi state giống nhau. Ví dụ `cancel` chỉ xuất hiện khi principal có authority và quyền trên đơn hàng. Hãy ghi rõ link vắng mặt có thể do trạng thái, quyền, association hoặc policy khác.

Link không phải bảo đảm thao tác sẽ thành công. Resource có thể thay đổi giữa lúc client đọc link và lúc gửi request; endpoint vẫn phải kiểm tra lại trạng thái và quyền.

## 9. Tài liệu hóa affordance và action

HAL link cơ bản cho biết relation và target URI. Affordance bổ sung mô tả thao tác, chẳng hạn HTTP method, input và output. Nếu API dùng HAL-FORMS, form template có thể được biểu diễn trong `_templates`.

Với mỗi action, tài liệu nên nêu:

- Relation hoặc template name.
- HTTP method và target được server công bố.
- Request media type và schema input.
- Field bắt buộc, tùy chọn và validation constraints.
- Response media type, status và representation sau thao tác.
- Điều kiện để action xuất hiện.
- Lỗi nghiệp vụ và cách client xử lý.

Ví dụ action `cancel`:

```json
{
  "_templates": {
    "cancel": {
      "title": "Hủy đơn hàng",
      "method": "POST",
      "target": "/api/orders/42/cancellation",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "type": "text",
          "required": true,
          "maxLength": 500
        }
      ]
    }
  }
}
```

Tài liệu cần giải thích `reason` có ý nghĩa gì và vì sao bắt buộc. Không yêu cầu client tự ghép target hoặc suy ra method từ tên relation nếu affordance đã công bố method.

## 10. Association link và embedded resource

Một association có thể được biểu diễn bằng link hoặc embedded representation. Hai cách này có ý nghĩa khác nhau:

| Cách biểu diễn | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Link relation | Cho client URI để khám phá resource liên quan khi cần | Resource lớn, độc lập, có thể tải riêng hoặc cần quyền riêng. |
| Embedded resource | Đưa representation của resource liên quan vào response hiện tại | Dữ liệu nhỏ, thường cần cùng lúc và có lợi ích giảm round trip. |

Ví dụ link association:

```json
{
  "id": 42,
  "_links": {
    "self": { "href": "/orders/42" },
    "customer": { "href": "/customers/7" }
  }
}
```

Ví dụ embedded association:

```json
{
  "id": 42,
  "_embedded": {
    "customer": {
      "id": 7,
      "name": "Lan Nguyen",
      "_links": {
        "self": { "href": "/customers/7" }
      }
    }
  },
  "_links": {
    "self": { "href": "/orders/42" },
    "customer": { "href": "/customers/7" }
  }
}
```

Tài liệu cần ghi rõ association có thể embedded hay không, relation name trong `_embedded`, field nào được rút gọn và link `self` của embedded resource có được công bố hay không. Không giả định mọi association luôn được nhúng; server có thể thay đổi representation theo media type, projection hoặc cấu hình.

## 11. Tài liệu collection resource

Collection resource thường có `_embedded` chứa item, cùng các link điều hướng như `self`, `next`, `prev`, `first`, `last` hoặc link tìm kiếm. Trang tài liệu collection cần giải thích:

- Relation dùng để tìm collection từ API root.
- Relation trong `_embedded` đại diện cho loại item nào.
- Query parameter filter, sort và page/size.
- Link phân trang nào có thể xuất hiện hoặc vắng mặt.
- Representation của mỗi embedded item có giống item resource độc lập hay không.
- Tổng số phần tử và metadata trang nếu API công bố.

Ví dụ:

```json
{
  "_embedded": {
    "orders": [
      {
        "id": 42,
        "status": "PENDING",
        "_links": {
          "self": { "href": "/api/orders/42" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "/api/orders?page=0&size=20" },
    "next": { "href": "/api/orders?page=1&size=20" },
    "profile": { "href": "/profiles/orders" }
  },
  "page": {
    "size": 20,
    "totalElements": 57,
    "totalPages": 3,
    "number": 0
  }
}
```

Mô tả `next` chỉ xuất hiện khi còn trang tiếp theo; `prev` có thể vắng ở trang đầu. Client nên theo link phân trang thay vì tự tăng page number nếu API đã công bố link đó.

## 12. Tài liệu request và response cho từng thao tác

Mỗi thao tác của resource nên có một phần riêng:

| Thao tác | Tài liệu cần có |
|---|---|
| Đọc item | Path parameter, Accept, status, Content-Type, response fields và links. |
| Đọc collection | Query parameters, filter/sort, pagination links, embedded item fields. |
| Tạo resource | Request fields, validation, status `201`, `Location` hoặc link `self`, representation trả về. |
| Cập nhật | Method, request fields, concurrency headers nếu có, response hoặc `204`. |
| Xóa/transition | Điều kiện, affordance, request body, status và state mới. |

Ví dụ tạo đơn hàng:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": 7,
  "items": [
    { "productId": 15, "quantity": 2 }
  ]
}
```

Response thành công:

```http
HTTP/1.1 201 Created
Location: /api/orders/42
Content-Type: application/hal+json
```

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": { "href": "/api/orders/42" },
    "customer": { "href": "/api/customers/7" },
    "cancel": { "href": "/api/orders/42/cancellation" }
  }
}
```

Ghi rõ `Location` và relation `self` cùng chỉ tới resource vừa tạo theo hợp đồng. Nếu server không trả body hoặc không hỗ trợ `Location`, tài liệu phải mô tả hành vi thực tế thay vì giả định.

## 13. Dùng Spring REST Docs để tạo trang resource

Spring REST Docs tạo snippet từ test chạy thật. Với MockMvc, có thể kết hợp:

- `pathParameters(...)` cho URI template variables.
- `queryParameters(...)` cho query string.
- `requestFields(...)` cho JSON request body.
- `responseFields(...)` cho response body.
- `links(...)` cho relation trong hypermedia response.
- `requestHeaders(...)` và `responseHeaders(...)` cho header.
- `document(...)` để đặt tên thư mục snippet.

Trong module test, thêm `spring-restdocs-mockmvc` với phiên bản đồng bộ cùng Spring REST Docs của dự án. Với Spring Boot dependency management, để BOM quản lý phiên bản nếu starter/dependency management đã bao gồm nó.

## 14. Tạo snippet links và response fields

Ví dụ test tài liệu hóa item resource:

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
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.RestDocumentationRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class OrderResourceDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsOrderResource() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", 42)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andDo(document("orders/get-order",
                        links(
                                linkWithRel("self").description("Đơn hàng hiện tại"),
                                linkWithRel("customer").description("Khách hàng của đơn hàng"),
                                linkWithRel("cancel").description("Yêu cầu hủy đơn hàng").optional()
                        ),
                        responseFields(
                                fieldWithPath("id").description("Định danh đơn hàng"),
                                fieldWithPath("orderNumber").description("Mã đơn hàng hiển thị"),
                                fieldWithPath("status").description("Trạng thái nghiệp vụ"),
                                fieldWithPath("total.amount").description("Số tiền của đơn hàng"),
                                fieldWithPath("total.currency").description("Mã tiền tệ ISO 4217"),
                                fieldWithPath("createdAt").description("Thời điểm tạo đơn hàng theo ISO 8601"),
                                subsectionWithPath("_links").ignored()
                        )));
    }
}
```

`links(...)` strict mặc định: relation trong response cần được mô tả; descriptor bắt buộc cũng phải xuất hiện. `cancel` được đánh dấu `.optional()` vì link phụ thuộc state hoặc quyền. `_links` được bỏ khỏi `responseFields` vì quan hệ đã có snippet riêng `links.adoc`.

Test giả định response thực tế có các field như ví dụ và các link relation đúng như fixture. Nếu response có thêm field, strict `responseFields(...)` sẽ báo thiếu descriptor; hãy bổ sung tài liệu cho field mới hoặc chủ động dùng `relaxedResponseFields(...)` khi chỉ muốn mô tả một phần.

## 15. Strict và relaxed field descriptors

Spring REST Docs có hai cách thường dùng:

| API | Hành vi | Phù hợp khi |
|---|---|---|
| `responseFields(...)` | Kiểm tra descriptor bao phủ các field trong payload và field bắt buộc tồn tại | Muốn tài liệu phản ánh đầy đủ response contract. |
| `relaxedResponseFields(...)` | Cho phép field không được mô tả xuất hiện trong payload | Snippet chỉ tập trung vào một phần response có chủ đích. |
| `requestFields(...)` | Mô tả và kiểm tra request payload | Muốn phát hiện request field mới hoặc thiếu descriptor. |
| `relaxedRequestFields(...)` | Cho phép request payload có field ngoài snippet | Tài liệu hóa một phần payload hoặc ví dụ rút gọn. |

Không dùng relaxed descriptors ở mọi nơi để né lỗi test. Nếu API thêm field công khai, strict test buộc người duy trì quyết định có cần tài liệu hóa field đó hay không.

Nếu `_embedded` chứa nhiều loại resource, nên tài liệu hóa phần embedded riêng thay vì đánh dấu bỏ qua toàn bộ body. Có thể dùng `subsectionWithPath(...)` để mô tả cấu trúc cấp cao và `beneathPath(...).withSubsectionId(...)` để tạo snippet field riêng cho một phần payload.

## 16. Tài liệu hóa embedded resource riêng

Khi collection response chứa embedded item, phần `_embedded` có thể lớn. Tách snippet giúp trang collection không trộn metadata phân trang với field của item.

Ví dụ cách trích subsection:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

responseFields(
        beneathPath("_embedded.orders").withSubsectionId("orders"),
        fieldWithPath("[].id").description("Định danh đơn hàng"),
        fieldWithPath("[].status").description("Trạng thái đơn hàng")
)
```

Path extractor và field path phụ thuộc shape JSON được serialize. Với response collection thực tế, kiểm tra snippet được sinh ra để xác nhận array path; nếu extractor trả về một item mẫu thay vì array, dùng descriptor tương ứng với subsection đã trích. Không ghi tài liệu dựa trên một JSONPath giả định mà chưa chạy test.

Một lựa chọn khác là mô tả `_embedded.orders` như một subsection và tạo test riêng cho item resource độc lập. Khi đó cần ghi rõ embedded representation có field/link nào khác với item resource đầy đủ.

## 17. Tài liệu hóa request fields và query parameters

Với thao tác tạo resource, dùng `requestFields(...)` để ghi field input, required/optional và validation:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
        fieldWithPath("customerId").description("Định danh khách hàng đặt đơn"),
        fieldWithPath("items[].productId").description("Định danh sản phẩm"),
        fieldWithPath("items[].quantity").description("Số lượng, tối thiểu là 1")
)
```

Nếu endpoint có filter hoặc pagination, mô tả query parameter:

```java
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.restdocs.request.RequestDocumentation.queryParameters;

queryParameters(
        parameterWithName("status").optional().description("Lọc theo trạng thái đơn hàng"),
        parameterWithName("page").optional().description("Số trang, bắt đầu từ 0"),
        parameterWithName("size").optional().description("Số item tối đa trong một trang")
)
```

Với request fields lồng nhau, descriptor path phải khớp JSON payload thực tế. Nếu một field có thể vắng mặt, đánh dấu `.optional()`; nếu field luôn có nhưng có thể là `null`, mô tả rõ nullable trong nội dung tài liệu vì optional và nullable không đồng nghĩa.

## 18. Tài liệu hóa header và status code

Header có thể là một phần quan trọng của hợp đồng resource:

- `Accept`: representation client muốn nhận.
- `Content-Type`: media type của request body.
- `Location`: URI của resource vừa tạo.
- `ETag` và `Last-Modified`: validator cho cache hoặc concurrency.
- `If-Match`/`If-None-Match`: conditional request.
- `Cache-Control`: chính sách lưu cache.

Spring REST Docs hỗ trợ snippet cho request/response headers và status. Ví dụ response tạo resource nên ghi `201 Created`, `Location` và `Content-Type`; thao tác cập nhật có thể trả `200`, `204` hoặc representation mới tùy hợp đồng.

Không ghi status code theo thông lệ chung nếu endpoint thực tế trả status khác. Dùng test để ghi nhận response thật, rồi giải thích lý do status đó được chọn.

## 19. Tài liệu lỗi của resource

Trang resource nên liên kết tới phần error contract liên quan tới từng thao tác. Ví dụ:

| Status | Tình huống | Problem type hoặc mã lỗi |
|---|---|---|
| `400` | Request body hoặc field không hợp lệ | `validation-error` |
| `401` | Chưa xác thực | `authentication-required` |
| `403` | Không đủ quyền đọc hoặc thực hiện action | `access-denied` |
| `404` | Resource không tồn tại hoặc không được phép tiết lộ | `order-not-found` |
| `409` | State hiện tại không cho phép transition | `order-cannot-be-cancelled` |
| `412` | Conditional request không thỏa | `precondition-failed` |

Nếu API dùng RFC 9457, ghi media type `application/problem+json`, `type` URI và extension fields mà client có thể sử dụng. Không trộn error fields vào bảng response fields của HAL success representation.

## 20. Tài liệu hóa security và quyền trên resource

Tài liệu resource cần mô tả yêu cầu truy cập ở mức có ích cho client:

- Resource có public hay cần authentication.
- Role/authority cần cho thao tác nếu API công bố policy đó.
- Link nào có thể vắng mặt theo quyền hoặc ownership.
- Status trả về khi request trực tiếp bị từ chối.
- Resource có được che giấu bằng `404` trong một số ngữ cảnh hay không.

Không xem link vắng mặt là cơ chế phân quyền. Client có thể gọi URI đã biết; server vẫn phải kiểm tra quyền tại endpoint. Tài liệu cần nói rõ link chỉ phản ánh affordance được công bố trong representation hiện tại.

## 21. Tổ chức trang tài liệu resource bằng AsciiDoc

Spring REST Docs tạo snippet, còn AsciiDoc có thể ghép chúng thành trang tài liệu hoàn chỉnh. Ví dụ:

```adoc
= Order resource

== Mục đích

Order đại diện cho yêu cầu mua hàng đã được tiếp nhận.

== Representation

include::{snippets}/orders/get-order/http-request.adoc[]
include::{snippets}/orders/get-order/http-response.adoc[]
include::{snippets}/orders/get-order/response-fields.adoc[]
include::{snippets}/orders/get-order/links.adoc[]

== Đọc collection

include::{snippets}/orders/list/http-request.adoc[]
include::{snippets}/orders/list/query-parameters.adoc[]
include::{snippets}/orders/list/links.adoc[]

== Tạo đơn hàng

include::{snippets}/orders/create/http-request.adoc[]
include::{snippets}/orders/create/request-fields.adoc[]
include::{snippets}/orders/create/http-response.adoc[]
```

Tên thư mục snippet lấy từ identifier truyền vào `document(...)`. Hãy giữ naming convention ổn định để trang tài liệu dễ bảo trì khi endpoint tăng lên.

## 22. Tạo trang resource theo cấu trúc nhất quán

Với API có nhiều resource, mỗi trang nên dùng cùng thứ tự mục:

1. Mục đích và vòng đời resource.
2. Entry point và cách khám phá.
3. Media type và representation mẫu.
4. Bảng response fields.
5. Relation và điều kiện xuất hiện.
6. Embedded/association behavior.
7. Affordances và các thao tác.
8. Request fields, query parameters và headers.
9. Status code và error types.
10. Authentication, authorization và cache.
11. Version/profile và deprecation nếu có.

Không cần lặp toàn bộ tài liệu dùng chung trên từng trang. Có thể tạo trang overview cho media types, relation conventions, error format và authentication; trang resource chỉ liên kết tới phần dùng chung và mô tả điểm riêng.

## 23. Kiểm soát thay đổi tài liệu bằng strict snippets

Spring REST Docs strict descriptors giúp phát hiện khi response hoặc request thay đổi:

- Field mới xuất hiện nhưng chưa có descriptor.
- Field đã tài liệu hóa không còn xuất hiện.
- Relation mới chưa được mô tả.
- Relation bắt buộc bị thiếu trong scenario test.
- Query parameter hoặc request field thay đổi.

Với link chỉ xuất hiện trong một số trạng thái, dùng `.optional()` và viết test riêng cho từng trạng thái. Với field tùy chọn, descriptor cũng cần `.optional()`. Chỉ dùng relaxed snippets khi cố ý tài liệu hóa một phần contract.

Đưa bước build tài liệu vào CI để test sinh snippet thất bại nếu hợp đồng lệch. Sau khi snippet sinh thành công, ghép AsciiDoc và publish artifact theo quy trình của dự án. Việc build snippet không tự bảo đảm trang cuối đã include đầy đủ; nên kiểm tra build tài liệu tổng hợp.

## 24. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ ghi URL endpoint | Client phụ thuộc route và khó khám phá resource. | Ghi entry point và relation cần follow. |
| Chỉ liệt kê field name | Không hiểu semantics, format hoặc nullability. | Mô tả kiểu, ý nghĩa, required/optional và ví dụ. |
| Dùng một bảng cho cả request và response | Client có thể gửi field chỉ đọc hoặc bỏ sót field bắt buộc. | Tách request fields và response fields. |
| Không mô tả điều kiện relation | Client không hiểu vì sao action link vắng mặt. | Ghi state, role, ownership và association conditions. |
| Nhầm association link với embedded resource | Client kỳ vọng dữ liệu luôn nằm trong body. | Mô tả rõ link, `_embedded` và representation của từng loại. |
| Bỏ qua `_links` trong field docs mà không có link snippet | Relation không được giải thích. | Dùng `links(...)` để tạo `links.adoc`. |
| Dùng relaxed descriptors cho mọi test | Field/link mới có thể lọt qua mà không được tài liệu hóa. | Ưu tiên strict descriptors cho contract chính. |
| Ghi ví dụ không khớp response thật | Người tích hợp dùng payload sai. | Sinh snippet từ HTTP test và review ví dụ. |
| Không ghi media type | Client chọn parser sai. | Tài liệu hóa Accept và Content-Type. |
| Coi affordance là bảo đảm thành công | Client không xử lý state race hoặc authorization failure. | Ghi điều kiện và lỗi; server re-check khi thực thi. |

## 25. Quy trình tài liệu hóa một resource

1. Xác định mục đích nghiệp vụ, danh tính và vòng đời resource.
2. Xác định entry point, media type và cách client khám phá resource.
3. Chụp representation thực tế qua HTTP test.
4. Mô tả từng field: kiểu, semantics, format, required, nullable, read-only và deprecated.
5. Liệt kê relation, URI semantics và điều kiện xuất hiện.
6. Mô tả association dưới dạng link hoặc embedded resource.
7. Liệt kê affordance, method, input, output và điều kiện thực hiện.
8. Tài liệu hóa request/response fields, query parameters, headers và status.
9. Tạo snippets bằng Spring REST Docs từ MockMvc/WebTestClient test.
10. Dùng strict descriptors để phát hiện thay đổi contract chưa được ghi nhận.
11. Ghép snippets vào trang resource và kiểm tra tài liệu build thành công.
12. Cập nhật profile, error docs và migration notes khi semantics thay đổi.

Tài liệu resource tốt cho client một bản đồ để khám phá và sử dụng resource: field giải thích dữ liệu, relation dẫn tới tài nguyên hoặc hành động, affordance mô tả cách tương tác, còn HTTP contract cho biết request và response thực tế. Khi tài liệu được sinh và kiểm tra từ test, nó có thể tiến hóa cùng API mà vẫn giữ semantics rõ ràng cho người tích hợp.

## Tài liệu tham khảo

- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring REST Docs – Documenting Your API](https://docs.spring.io/spring-restdocs/reference/)
- [Spring REST Docs – Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs – Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [HAL – JSON Hypertext Application Language](https://stateless.group/hal_specification.html)
