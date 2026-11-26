# Backward compatibility

Backward compatibility (tương thích ngược) là khả năng một phiên bản API mới tiếp tục phục vụ các client đã được xây dựng theo hợp đồng cũ. Khi server thay đổi, ứng dụng mobile chưa cập nhật, service đối tác hoặc một bản frontend cũ vẫn có thể gọi API và hiểu response như trước. Với REST API có hypermedia, tính tương thích không chỉ nằm ở JSON field mà còn ở HTTP status, media type, link relation, URI template và affordance.

Spring HATEOAS giúp giảm phụ thuộc của client vào cấu trúc URL bằng cách để client khám phá và theo link do server công bố. Tuy nhiên, hypermedia không tự làm mọi thay đổi trở nên tương thích. Xóa một relation, đổi ý nghĩa của link, thay kiểu dữ liệu hoặc ngừng công bố một affordance mà client đang dùng vẫn có thể phá vỡ tích hợp.

## Tương thích ngược nghĩa là gì?

Giả sử client phiên bản 1 đang đọc response đơn hàng:

```json
{
  "id": "o-42",
  "status": "PAID",
  "total": 125000,
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    }
  }
}
```

Server muốn bổ sung tên khách hàng và link đến hóa đơn. Nếu các phần tử cũ vẫn giữ nguyên ý nghĩa, client cũ vẫn đọc được `id`, `status`, `total` và theo `self`, trong khi client mới có thể sử dụng thêm thông tin:

```json
{
  "id": "o-42",
  "status": "PAID",
  "total": 125000,
  "customerName": "Nguyen An",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "invoice": {
      "href": "https://shop.example/api/orders/o-42/invoice"
    }
  }
}
```

Việc thêm field và link thường là thay đổi additive (bổ sung). Nhưng nếu client cũ dùng JSON parser từ chối field không biết, hoặc coi mọi link là một tập cố định, thay đổi additive vẫn có thể gây lỗi. Vì vậy, tương thích phải được đánh giá từ góc nhìn của client thực tế, không chỉ dựa trên cấu trúc response của server.

## Phân biệt tương thích phía client và phía server

Có hai chiều cần xem xét:

| Chiều tương thích | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Client cũ với server mới | Client đã phát hành có tiếp tục dùng server mới được không? | Client không bị lỗi khi response thêm `customerName`. |
| Client mới với server cũ | Client mới có thể hoạt động với server chưa nâng cấp không? | Client không bắt buộc dùng link `invoice` nếu server cũ chưa công bố. |

Trong hệ thống triển khai độc lập, hai chiều đều quan trọng. Mobile client có thể cập nhật chậm hơn server; các service nội bộ cũng có thể được rollout theo từng đợt. Thiết kế tốt cần cho phép khoảng thời gian mà nhiều phiên bản client và server cùng tồn tại.

## Phân loại thay đổi API

Một thay đổi được xem là tương thích hay phá vỡ phụ thuộc vào hợp đồng hiện tại và cách client sử dụng nó. Bảng sau là quy tắc thực hành phổ biến:

| Thay đổi | Đánh giá thường gặp | Lý do |
| --- | --- | --- |
| Thêm response field tùy chọn | Thường tương thích | Client cũ có thể bỏ qua field mới nếu parser hỗ trợ unknown field. |
| Thêm link relation mới | Thường tương thích | Client cũ có thể bỏ qua link chưa biết. |
| Thêm affordance tùy chọn | Thường tương thích | Client cũ không cần dùng hành động mới. |
| Thêm request parameter tùy chọn | Thường tương thích | Client cũ tiếp tục gửi request như trước. |
| Thêm giá trị enum trong response | Có thể phá vỡ | Client cũ có thể dùng exhaustive switch hoặc enum parser nghiêm ngặt. |
| Xóa hoặc đổi tên response field | Phá vỡ | Client cũ không còn nhận được dữ liệu mà nó phụ thuộc. |
| Đổi kiểu field hoặc đơn vị đo | Phá vỡ | Client có thể parse sai hoặc tính toán sai. |
| Đổi relation hoặc ý nghĩa của link | Phá vỡ | Client không còn tìm thấy hoặc hiểu sai khả năng. |
| Xóa query parameter hoặc đổi default | Có thể phá vỡ | Kết quả truy vấn thay đổi dù client không đổi request. |
| Thay đổi HTTP status hoặc media type | Có thể phá vỡ | Client có thể không chọn đúng parser hoặc nhánh xử lý. |
| Làm request field trước đây tùy chọn thành bắt buộc | Phá vỡ | Client cũ không gửi field mới và request bị từ chối. |

Không có quy tắc “chỉ cần thêm field là luôn an toàn”. Hãy xác định client cũ có thể gặp thay đổi đó ở đâu: parser, validation, logic nghiệp vụ, cache, điều hướng hoặc xử lý lỗi.

## Thay đổi response representation theo hướng additive

Khi bổ sung dữ liệu, giữ nguyên tên, kiểu, ý nghĩa và đơn vị của field đã công bố. Ví dụ, thêm `currency` có thể hữu ích nếu API trước đây trả `total` nhưng hợp đồng đã quy định đơn vị tiền tệ. Nếu chưa quy định, thêm field mới không sửa được sự mơ hồ cũ; cần làm rõ semantics theo cách không làm thay đổi cách client cũ diễn giải `total`.

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderRepresentation(
        UUID id,
        String status,
        BigDecimal total,
        String currency,
        String customerName) {
}
```

Nếu các field mới có thể chưa có giá trị, hãy xác định rõ chúng có thể vắng mặt hay `null`. Client nên phân biệt:

- Field vắng mặt: server không công bố thông tin đó trong representation này.
- Field có giá trị `null`: server công bố field nhưng hiện không có giá trị.
- Field có giá trị: server công bố dữ liệu cụ thể.

Đừng thay một field số bằng chuỗi chỉ để thêm đơn vị, ví dụ từ `125000` thành `"125.000 VND"`. Cách đó phá kiểu dữ liệu và khiến client cũ không parse được. Thêm field `currency` hoặc tạo representation mới nếu cần thay đổi định dạng.

## Tolerant reader ở phía client

Client nên đọc những field cần thiết và bỏ qua field mở rộng mà nó không hiểu, khi việc bỏ qua đó an toàn. Với Jackson, có thể cấu hình DTO của client bỏ qua unknown property:

```java
import java.math.BigDecimal;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrderResponse(
        UUID id,
        String status,
        BigDecimal total) {
}
```

Annotation này minh họa DTO ở phía consumer. Trong ứng dụng server, không nên tự động bỏ qua mọi request field không biết nếu điều đó có thể che giấu lỗi client hoặc mở đường cho mass assignment. Request DTO nên chỉ nhận các field được cho phép và validation phải rõ ràng.

Tolerant reader không có nghĩa là chấp nhận mọi dữ liệu. Client vẫn cần kiểm tra field bắt buộc, kiểu dữ liệu, miền giá trị và invariants. Nếu một field lạ có thể làm thay đổi nghiệp vụ hoặc quyền truy cập, không được bỏ qua một cách mù quáng.

## Giữ ổn định enum và trạng thái

Enum thường gây lỗi tương thích khi server thêm trạng thái mới. Ví dụ client cũ chỉ biết `PENDING`, `PAID`, `SHIPPED`, nhưng server bổ sung `REFUNDED`. Một client dùng switch exhaustive có thể lỗi hoặc hiển thị sai.

```java
String labelForStatus(String status) {
    return switch (status) {
        case "PENDING" -> "Đang chờ";
        case "PAID" -> "Đã thanh toán";
        case "SHIPPED" -> "Đã giao vận";
        default -> "Trạng thái khác";
    };
}
```

Với client, nên có nhánh fallback cho giá trị enum chưa biết. Với server, thêm giá trị enum vào response có thể là thay đổi cần thông báo, đặc biệt khi client được sinh từ OpenAPI hoặc dùng enum đóng. Nếu API cần mở rộng trạng thái thường xuyên, cân nhắc mô hình hóa trạng thái thành string có semantics được tài liệu hóa thay vì giả định danh sách enum không đổi.

Không đổi tên một giá trị enum đã công bố. Nếu cần ngừng dùng giá trị cũ, có thể duy trì nó trong thời gian chuyển tiếp và đánh dấu deprecated trong schema/tài liệu trước khi loại bỏ theo phiên bản breaking.

## Hypermedia giúp client ít phụ thuộc URL

Client REST có hypermedia nên bắt đầu từ entry point đã biết, đọc link relation và theo `href`. Nếu server đổi route từ `/api/orders/{id}` sang `/commerce/orders/{id}`, client vẫn có thể hoạt động nếu server tiếp tục công bố cùng relation `self` và relation nghiệp vụ với semantics không đổi.

Spring HATEOAS hỗ trợ cách xây link theo controller mapping:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;

EntityModel<OrderRepresentation> toModel(Order order) {
    OrderRepresentation body = toRepresentation(order);

    EntityModel<OrderRepresentation> model = EntityModel.of(body);
    model.add(linkTo(methodOn(OrderController.class)
            .one(order.getId())).withRel(IanaLinkRelations.SELF));

    return model;
}
```

`methodOn(...)` và `linkTo(...)` giúp URI được tạo theo mapping hiện tại. Client không cần biết controller hoặc route đó. Điều kiện quan trọng là relation phải giữ đúng semantics và server vẫn công bố nó.

Hypermedia không cứu được client đã hard-code URL, tự nối `/orders/{id}` từ ID hoặc giả định relation luôn có một `href` cố định. Client cần thực sự theo link được cung cấp.

## Thêm link relation mới thường an toàn hơn đổi relation cũ

Giả sử order trước đây có `self` và `collection`. Server muốn bổ sung link `invoice`:

```java
import org.springframework.hateoas.LinkRelation;

model.add(linkTo(methodOn(InvoiceController.class)
        .download(order.getId()))
        .withRel(LinkRelation.of(
                "https://api.example.com/rels/invoice")));
```

Client cũ có thể bỏ qua relation mới; client mới có thể dùng nó. Khi thêm relation, cần định nghĩa semantics, điều kiện xuất hiện và response target. Nếu relation là extension, dùng URI relation ổn định và tài liệu hóa nó.

Đổi tên relation cũ hoặc tái sử dụng cùng relation với ý nghĩa khác thường là breaking change. Ví dụ, nếu client tìm `https://api.example.com/rels/cancel` để hủy order, không được đổi relation đó thành “yêu cầu hoàn tiền”. Hãy tạo relation mới cho hành động mới và duy trì relation cũ trong giai đoạn chuyển tiếp.

## Giữ ổn định affordance và hành vi thao tác

Affordance mô tả thao tác khả dụng, chẳng hạn HTTP method, input type và metadata. Client có thể dùng affordance để dựng form hoặc chọn request đúng cách. Thêm một affordance mới thường là additive:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.Affordances;
import org.springframework.hateoas.Link;

Link self = linkTo(methodOn(OrderController.class)
        .one(order.getId())).withSelfRel();

Link link = Affordances.of(self)
        .afford(afford(methodOn(OrderController.class)
                .cancel(order.getId(), null))
                .withInput(CancelOrderRequest.class)
                .withName("cancel"))
        .toLink();
```

Khi serialize theo HAL-FORMS, affordance có thể được thể hiện thành template trong `_templates`. Việc bổ sung template `cancel` không ảnh hưởng client cũ nếu client bỏ qua template chưa biết. Tuy nhiên, đổi method từ `POST` sang `DELETE`, đổi request property, hoặc thay semantics của template đã có có thể phá vỡ client đang sử dụng nó.

Affordance có thể xuất hiện hoặc biến mất theo trạng thái resource và quyền người dùng. Client cần hiểu đây là tập khả năng hiện tại, không phải danh sách cố định cho mọi trạng thái. Endpoint vẫn phải kiểm tra authorization và business rule khi nhận request.

## Thay đổi pagination, filter và sort

Phân trang là một phần của hợp đồng API. Các thay đổi sau có thể phá vỡ client:

- Đổi tên `page`, `size`, `sort` mà không duy trì alias hoặc phiên bản cũ.
- Đổi page index từ zero-based sang one-based.
- Đổi default sort làm kết quả xuất hiện theo thứ tự khác.
- Xóa một filter hoặc đổi semantics từ AND sang OR.
- Bỏ các filter hiện tại khỏi link `next`.
- Thay page response bằng một mảng JSON thuần và xóa metadata.

Khi bổ sung filter mới, giữ nó ở dạng tùy chọn. Khi thay đổi cấu trúc pagination, hãy duy trì link relation và metadata cũ trong thời gian chuyển tiếp hoặc phát hành representation version mới. Client nên theo `next`/`prev` do server tạo thay vì tự tính URL.

## Giữ ổn định media type và error contract

Client chọn parser qua `Accept` và hiểu body theo `Content-Type`. Nếu endpoint đang trả `application/hal+json`, việc đổi sang một media type khác có thể làm client cũ không nhận response. Nếu thay đổi representation, có thể cung cấp song song media type mới và cho client chọn qua content negotiation.

Error response cũng cần được duy trì. Đổi `404` thành `200` với body báo lỗi, đổi `application/problem+json` thành HTML hoặc xóa extension `code` mà client đang dùng đều có thể phá vỡ tích hợp. Hãy giữ HTTP status và error type ổn định; có thể thêm extension field tùy chọn nếu consumer xử lý unknown field an toàn.

Ví dụ Problem Details với extension mới:

```json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "Đơn hàng không thể hủy ở trạng thái hiện tại.",
  "code": "ORDER_STATE_CONFLICT",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Thêm `traceId` là additive nếu client cũ bỏ qua extension. Thay đổi `code` hoặc `type` có thể làm hỏng logic phân nhánh của client.

## Deprecation và Sunset

Khi một endpoint, field, relation hoặc media type cần ngừng hỗ trợ, không nên xóa ngay khi đã có phương án thay thế. Một quy trình chuyển đổi thường gồm:

1. Công bố phương án thay thế và tài liệu migration.
2. Bổ sung API mới song song với API cũ.
3. Đánh dấu thành phần cũ là deprecated và thông báo thời điểm dự kiến ngừng hỗ trợ.
4. Theo dõi traffic để biết client nào còn sử dụng.
5. Gửi nhắc nhở trước ngày sunset và hỗ trợ client chuyển đổi.
6. Chỉ loại bỏ khi hết thời gian hỗ trợ và đáp ứng chính sách tương thích đã cam kết.

RFC 9745 định nghĩa HTTP `Deprecation` response header để thông báo resource đã bị deprecated. RFC 8594 định nghĩa `Sunset` header để thông báo thời điểm resource dự kiến không còn khả dụng. Ví dụ minh họa:

```http
HTTP/1.1 200 OK
Deprecation: @1798761599
Sunset: Thu, 31 Dec 2026 23:59:59 GMT
Link: <https://api.example.com/deprecations/orders-v1>; rel="deprecation"
Content-Type: application/hal+json
```

Giá trị `Deprecation` dùng cú pháp Structured Fields Date; `Sunset` dùng HTTP-date. Link relation `deprecation` dẫn đến tài liệu giải thích lý do, ảnh hưởng và cách chuyển đổi. Chỉ gửi `Sunset` khi đã có ngày dự kiến cụ thể và có thể thực hiện; header này không tự động xóa endpoint vào ngày đó.

Trong hypermedia, có thể tiếp tục công bố link cũ trong giai đoạn deprecation và bổ sung link mới hoặc relation `successor-version` khi semantics phù hợp. Client nên được hướng dẫn qua tài liệu và link thay thế, không phải tự đoán endpoint mới.

## Khi nào cần version API?

Không cần tạo version mới cho mọi thay đổi. Nếu có thể bổ sung field, link hoặc affordance tùy chọn mà giữ nguyên semantics cũ, hãy tiến hóa hợp đồng hiện tại. Version mới phù hợp khi cần thay đổi không tương thích, ví dụ:

- Xóa/đổi tên field bắt buộc hoặc đổi kiểu dữ liệu.
- Thay đổi semantics của relation hoặc thao tác.
- Đổi cấu trúc representation khiến parser cũ không thể tiếp tục.
- Thay đổi quy tắc xác thực hoặc request contract theo cách client cũ không đáp ứng được.
- Thay đổi pagination/query semantics không thể duy trì song song.

Một số cách versioning phổ biến:

| Cách | Ví dụ | Đặc điểm |
| --- | --- | --- |
| URI path | `/api/v2/orders` | Dễ quan sát và routing; version xuất hiện trong URL. |
| Media type | `application/vnd.example.order-v2+json` | Chọn representation qua `Accept`/`Content-Type`. |
| Custom header | `API-Version: 2` | Tách version khỏi URI nhưng cần tài liệu và hỗ trợ tooling. |

Không có một cách versioning phù hợp cho mọi hệ thống. Chọn một chiến lược nhất quán, hỗ trợ nhiều phiên bản trong thời gian migration và tránh duy trì vô hạn những phiên bản không còn consumer.

## Hypermedia và versioning

Một API có hypermedia nên giúp client tìm entry point và theo link thay vì tự tạo URL theo version. Ví dụ, client nhận được link relation `orders` từ API root và theo `href` của server. Khi server chuyển route từ `/api/v1/orders` sang `/api/v2/orders`, client có thể không cần đổi nếu relation và representation mà nó sử dụng vẫn tương thích.

Tuy nhiên, nếu media type v2 thay đổi semantics hoặc field bắt buộc, client vẫn cần chọn representation phù hợp. Link discovery giải quyết coupling về URI; content negotiation/versioning giải quyết khác biệt representation. Hai cơ chế bổ sung nhau.

Đừng nhúng version vào mọi custom relation nếu semantics không thay đổi. Một relation URI nên mô tả ý nghĩa ổn định; version có thể nằm trong `href` hoặc media type. Nếu semantics relation thực sự thay đổi, hãy định nghĩa relation mới thay vì âm thầm tái sử dụng tên cũ.

## Consumer-driven contract testing

Contract test xác nhận những gì consumer thực sự phụ thuộc vẫn được server đáp ứng. Thay vì snapshot toàn bộ JSON và khóa test vào mọi field, hãy kiểm tra các phần quan trọng của hợp đồng:

- Status code và media type.
- Field bắt buộc, kiểu dữ liệu và semantics.
- Link relation mà client cần, cùng khả năng theo href.
- Affordance/template mà client sử dụng, gồm method và input.
- Pagination/filter behavior mà client dựa vào.
- Error type và extension code đã công bố.

Ví dụ MockMvc kiểm tra hợp đồng cũ vẫn có mặt sau khi server bổ sung field và link mới:

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
class OrderCompatibilityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void preservesV1FieldsAndLinks() throws Exception {
        mockMvc.perform(get("/api/orders/{id}", "o-42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$.id").value("o-42"))
                .andExpect(jsonPath("$.status").value("PAID"))
                .andExpect(jsonPath("$.total").exists())
                .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

Test trên cố ý không yêu cầu client cũ phải biết `customerName` hoặc link `invoice`. Có thể viết thêm một consumer test dùng DTO cũ để deserialize response mới và xác nhận field cũ vẫn đọc đúng.

Với hệ thống nhiều service, công cụ consumer-driven contract như Spring Cloud Contract hoặc Pact có thể ghi lại kỳ vọng của consumer và xác minh provider đáp ứng. Chọn công cụ theo stack hiện tại; điều quan trọng là contract test phải phản ánh hành vi mà consumer cần, không phải toàn bộ chi tiết triển khai.

## Quy trình thay đổi an toàn

Trước khi thay đổi API đã được sử dụng, thực hiện quy trình review:

1. Xác định consumer và phiên bản client đang dùng endpoint/field/relation bị thay đổi.
2. Phân loại thay đổi là additive, behavior-changing hay breaking.
3. Kiểm tra cả request, response, status, media type, link relation, affordance và pagination.
4. Nếu tương thích, bổ sung theo hướng optional và giữ nguyên semantics cũ.
5. Nếu breaking, thiết kế version hoặc giai đoạn chuyển tiếp; công bố deprecation/sunset khi cần.
6. Viết contract test cho consumer quan trọng và chạy trong pipeline trước khi phát hành.
7. Theo dõi log, metric và traffic theo client/version sau rollout.

Không dựa hoàn toàn vào việc code server compile thành công. Một thay đổi có thể không làm server lỗi build nhưng vẫn khiến client cũ parse sai, không tìm thấy link hoặc gửi request không hợp lệ.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Xóa field vì server không còn dùng nội bộ | Client cũ vẫn có thể phụ thuộc field đó. | Giữ field trong giai đoạn chuyển tiếp hoặc phát hành version breaking. |
| Đổi tên relation | Client không tìm thấy link đã dùng. | Bổ sung relation mới và duy trì relation cũ có thời hạn. |
| Thay đổi semantics nhưng giữ nguyên tên relation | Client thực hiện hành động sai. | Định nghĩa relation mới khi semantics thay đổi. |
| Thêm enum mà không có fallback phía client | Client cũ có thể lỗi khi gặp trạng thái mới. | Tolerant enum handling và contract test. |
| Bỏ qua unknown request field một cách vô điều kiện | Che giấu lỗi client hoặc tăng nguy cơ mass assignment. | Dùng request DTO allow-list và validation rõ ràng. |
| Đổi media type mà không thông báo | Client không chọn được parser. | Content negotiation hoặc version representation rõ ràng. |
| Xóa endpoint ngay khi công bố endpoint thay thế | Client cũ chưa kịp migration bị gián đoạn. | Deprecation, theo dõi traffic và sunset có kế hoạch. |
| Snapshot toàn bộ JSON quá cứng | Test hỏng vì thay đổi additive vô hại. | Assert các contract element mà consumer thực sự phụ thuộc. |

## Nguyên tắc thiết kế

- Giữ ổn định semantics của field, relation, method, status và media type đã công bố.
- Ưu tiên thay đổi additive: thêm field tùy chọn, link mới và affordance mới.
- Thiết kế client theo tolerant reader nhưng vẫn validate dữ liệu quan trọng.
- Có fallback cho enum và relation chưa biết; không giả định danh sách đóng nếu hợp đồng cho phép mở rộng.
- Dùng hypermedia link thay vì hard-code URL và query string.
- Không đổi nghĩa relation cũ; tạo relation mới khi khả năng nghiệp vụ thay đổi.
- Duy trì pagination, filter và error contract trong giai đoạn chuyển tiếp.
- Dùng deprecation và sunset để thông báo việc ngừng hỗ trợ.
- Chỉ version hóa khi thay đổi không thể duy trì tương thích.
- Kiểm thử contract từ góc nhìn consumer trước và sau rollout.

Backward compatibility là kỷ luật tiến hóa hợp đồng API qua thời gian. Với Spring HATEOAS, link và affordance giúp client khám phá khả năng hiện tại mà không phụ thuộc vào route, nhưng server vẫn phải giữ semantics ổn định và quản lý thay đổi có kế hoạch. Khi ưu tiên bổ sung tương thích, công bố deprecation rõ ràng, version hóa những thay đổi thực sự breaking và kiểm thử theo nhu cầu consumer, nhiều phiên bản client có thể cùng hoạt động trong khi API tiếp tục phát triển.
