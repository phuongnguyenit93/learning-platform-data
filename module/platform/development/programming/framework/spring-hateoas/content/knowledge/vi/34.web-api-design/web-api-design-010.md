# Đánh giá API design

Đánh giá thiết kế Web API là quá trình kiểm tra xem hợp đồng HTTP có giúp client hiểu đúng tài nguyên, thực hiện đúng thao tác, xử lý lỗi và tiến hóa an toàn hay không. Một API có thể chạy đúng trong demo nhưng vẫn khó dùng nếu URL bộc lộ cấu trúc nội bộ, method HTTP sai ngữ nghĩa, response không nhất quán, link hypermedia thiếu quan hệ rõ ràng hoặc lỗi không thể được client xử lý tự động.

Với Spring HATEOAS, việc đánh giá còn cần xem xét representation model, link relation, URI template và affordance. Những thành phần này giúp client khám phá tài nguyên và hành động từ response. Chúng chỉ có giá trị khi phản ánh đúng khả năng mà server thực sự hỗ trợ, được kiểm tra quyền ở mỗi request và giữ ổn định như một phần của hợp đồng API.

Bài học này đưa ra một quy trình review có thể áp dụng cho API mới hoặc API đang vận hành. Bạn sẽ đánh giá mô hình tài nguyên, URI, HTTP semantics, representation và content negotiation, hypermedia, lỗi, bảo mật, hiệu năng, khả năng tương thích và kiểm thử. Cuối bài có ví dụ review một API đơn hàng, bảng chấm điểm và checklist dùng trong pull request.

Sau bài học, bạn có thể:

- Xác định phạm vi và tiêu chí của một buổi review API design.
- Đánh giá cách mô hình hóa resource, collection, quan hệ và URI.
- Kiểm tra method, status code, header và tính idempotent theo HTTP semantics.
- Đánh giá representation, media type và content negotiation.
- Kiểm tra link relation, URI template và affordance trong Spring HATEOAS.
- Đánh giá cách API mô tả lỗi bằng Problem Details.
- Phát hiện rủi ro bảo mật ở object, property, function và luồng nghiệp vụ.
- Kiểm tra caching, concurrency, pagination và giới hạn tài nguyên.
- Nhận diện thay đổi phá vỡ tương thích và lập contract test.
- Sử dụng rubric để ghi nhận bằng chứng, mức độ rủi ro và hướng khắc phục.

## 1. Mục tiêu của một API design review

Một buổi review không chỉ hỏi endpoint có trả đúng JSON hay không. Cần xem toàn bộ hành trình của client:

1. Client bắt đầu từ một URI hoặc entry point đã biết.
2. Client nhận representation và hiểu resource hiện tại.
3. Client khám phá link và các thao tác có thể thực hiện.
4. Client gửi request với method, header và payload phù hợp.
5. Client hiểu kết quả thành công hoặc lỗi.
6. Client có thể tiếp tục làm việc khi server thay đổi implementation mà không phá hợp đồng đã công bố.

Một API tốt cần đáp ứng các nhóm chất lượng sau:

| Nhóm | Câu hỏi review |
|---|---|
| Resource model | API có mô tả đúng các khái niệm và ranh giới nghiệp vụ không? |
| HTTP semantics | Method, status code và header có đúng ngữ nghĩa không? |
| Representation | Client có hiểu dữ liệu và media type được trả về không? |
| Hypermedia | Client có khám phá được link và thao tác từ response không? |
| Error handling | Lỗi có mã HTTP và chi tiết máy đọc được không? |
| Security | API có bảo vệ dữ liệu và hành động theo quyền không? |
| Reliability | API có xử lý retry, concurrency, cache và giới hạn tải hợp lý không? |
| Evolution | Thay đổi có giữ tương thích và có contract test không? |

Review nên dựa trên bằng chứng: request/response mẫu, controller mapping, representation assembler, cấu hình Spring HATEOAS, test và tài liệu API. Không đánh giá một endpoint chỉ từ tên method hoặc một ảnh chụp JSON.

### 1.1. Phân biệt design review và implementation review

Design review kiểm tra hợp đồng mà client nhìn thấy: URI, method, media type, relation, payload, status, lỗi và quy tắc tương thích.

Implementation review kiểm tra cách code thực hiện hợp đồng: transaction, query, validation, mapping, exception handling, logging và bảo mật.

Hai hoạt động liên quan nhưng không thay thế nhau. Một controller có code sạch vẫn có thể công bố API sai ngữ nghĩa; một hợp đồng API tốt cũng có thể được triển khai kém hiệu quả hoặc thiếu an toàn.

## 2. Xác định use case và client trước khi đánh giá endpoint

Trước khi xem URL, hãy xác định ai sử dụng API và họ cần hoàn thành công việc gì.

Ví dụ hệ thống đơn hàng có các client:

- Ứng dụng mua sắm: xem đơn, theo dõi giao hàng, yêu cầu hủy.
- Ứng dụng hỗ trợ: tra cứu đơn, xem lịch sử và xử lý khiếu nại.
- Dịch vụ thanh toán: nhận yêu cầu thanh toán và gửi trạng thái.
- Công cụ quản trị: tìm kiếm và thực hiện các thao tác được cấp quyền.

Cùng một domain có thể có nhiều representation hoặc affordance khác nhau theo vai trò và trạng thái. Review cần kiểm tra từng use case, không giả định một response phù hợp cho mọi client.

Có thể lập bảng use case:

| Actor | Tác vụ | Resource liên quan | Điều kiện |
|---|---|---|---|
| Customer | Xem đơn hàng | Order | Chủ sở hữu đơn |
| Customer | Yêu cầu hủy | Order, Cancellation | Đơn còn cho phép hủy |
| Support agent | Xem lịch sử | Order, OrderHistory | Có quyền hỗ trợ |
| Payment service | Ghi nhận thanh toán | Payment | Xác thực service-to-service |

Bảng này giúp phát hiện endpoint hoặc link được công bố mà không có use case rõ ràng, đồng thời tìm ra hành động cần phụ thuộc vào trạng thái nghiệp vụ.

## 3. Đánh giá resource model và URI

REST API nên mô hình hóa các khái niệm nghiệp vụ thành resource có định danh. URI định danh resource; HTTP method mô tả thao tác áp dụng lên target resource.

Ví dụ:

~~~text
/orders
/orders/42
/orders/42/items
/orders/42/payments
/orders/42/cancellations
~~~

Các URI này biểu diễn collection, một order và các tài nguyên liên quan.

### 3.1. Kiểm tra ranh giới resource

Với mỗi URI, hãy hỏi:

- Nó đại diện cho một khái niệm nghiệp vụ có thể nhận diện không?
- Resource có vòng đời hoặc trạng thái riêng không?
- Quan hệ với resource cha có rõ ràng không?
- Client có cần định danh resource sau khi tạo không?
- Có đang bộc lộ tên bảng, tên schema hoặc cấu trúc package nội bộ không?

Ví dụ, orders là collection resource. Một cancellation request có thể là resource riêng nếu hệ thống lưu trạng thái yêu cầu, thời điểm tạo, người yêu cầu và kết quả xử lý. Nếu hủy chỉ là một lệnh không có vòng đời riêng, endpoint action có thể phù hợp hơn, nhưng cần xác định rõ ngữ nghĩa và phản hồi.

### 3.2. URI nên ổn định và dễ dự đoán

Các quy ước thường hữu ích:

- Dùng danh từ cho resource, ví dụ /orders và /customers.
- Dùng một quy tắc nhất quán cho số nhiều, chữ thường và dấu phân cách.
- Dùng path variable cho định danh resource.
- Dùng query parameter cho lọc, tìm kiếm, phân trang và sắp xếp.
- Tránh đưa tên bảng hoặc chi tiết triển khai vào URI công khai.

Không có một quy tắc số nhiều duy nhất bắt buộc cho mọi API. Điều cần review là tính nhất quán và khả năng duy trì URI sau khi implementation thay đổi.

### 3.3. Không dùng GET để thực hiện thay đổi trạng thái

Một endpoint như:

~~~http
GET /orders/42/cancel
~~~

là dấu hiệu thiết kế sai nếu request thực sự hủy đơn hàng. GET là method an toàn; crawler, prefetcher hoặc cache có thể tự động gửi request GET.

Một thiết kế rõ hơn là tạo cancellation request:

~~~http
POST /orders/42/cancellations
Content-Type: application/json

{
  "reason": "Customer request"
}
~~~

Hoặc dùng một mô hình action resource đã được định nghĩa trong hợp đồng. Điểm review là thao tác làm thay đổi trạng thái phải dùng method có semantics phù hợp, và client phải hiểu được kết quả của thao tác.

### 3.4. Kiểm tra query contract

Query parameter cần có tên và ý nghĩa ổn định. Ví dụ:

~~~http
GET /orders?status=shipped&createdAfter=2026-01-01&page=0&size=20
~~~

Review các câu hỏi:

- Filter nào được hỗ trợ?
- Nhiều filter kết hợp theo AND hay OR?
- Giá trị không hợp lệ trả lỗi nào?
- Có giới hạn kích thước trang không?
- Thứ tự mặc định có ổn định không?
- Có hỗ trợ cursor pagination khi collection rất lớn không?
- URI template có công bố đúng các biến server xử lý không?

Với Spring HATEOAS, link template có thể công bố query variable:

~~~java
UriTemplate template = UriTemplate.of("/orders")
    .with(TemplateVariable.requestParameter("status"))
    .with(TemplateVariable.requestParameter("createdAfter"))
    .with(TemplateVariable.requestParameter("page"))
    .with(TemplateVariable.requestParameter("size"));

Link search = Link.of(template, IanaLinkRelations.SEARCH);
~~~

Các import cần thiết:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.TemplateVariable;
import org.springframework.hateoas.UriTemplate;
~~~

Một template không được công bố supplier nếu endpoint không nhận hoặc không xử lý biến đó. Link phải phản ánh hợp đồng thực tế.

## 4. Đánh giá HTTP method và status code

HTTP method là nguồn ngữ nghĩa chính của request. Review không chỉ kiểm tra mapping annotation mà còn xem hành vi thực tế có đúng method được công bố hay không.

| Method | Ý nghĩa review | Câu hỏi cần kiểm tra |
|---|---|---|
| GET | Đọc representation hiện tại | Có gây thay đổi trạng thái nghiệp vụ không? |
| HEAD | Đọc metadata tương tự GET | Header có nhất quán với GET không? |
| POST | Xử lý nội dung hoặc tạo subordinate resource | Response có chỉ rõ kết quả và resource mới không? |
| PUT | Tạo hoặc thay thế trạng thái target theo semantics PUT | Request có biểu diễn đầy đủ trạng thái mong muốn không? |
| PATCH | Thay đổi một phần target | Patch format và semantics có được xác định không? |
| DELETE | Xóa hoặc loại bỏ quan hệ của target | Kết quả và khả năng retry có rõ không? |
| OPTIONS | Khám phá giao thức được hỗ trợ | Có cần công bố Allow hoặc CORS policy không? |

### 4.1. Safe và idempotent

Hai khái niệm này ảnh hưởng trực tiếp đến retry, crawler, cache và client library:

- Safe: client không yêu cầu thay đổi trạng thái của resource. GET, HEAD, OPTIONS và TRACE được định nghĩa là safe trong HTTP.
- Idempotent: gửi cùng một request nhiều lần có cùng hiệu ứng dự kiến như gửi một lần. PUT và DELETE là idempotent theo semantics HTTP; POST thường không được mặc định là idempotent.

Ví dụ, client gửi POST tạo đơn hàng nhưng mất kết nối trước khi nhận response. Tự động gửi lại có thể tạo đơn hàng thứ hai. API cần thiết kế cơ chế xử lý retry phù hợp nếu use case yêu cầu, chẳng hạn idempotency key được định nghĩa rõ, lưu kết quả theo key và thời hạn hiệu lực.

Không nên tuyên bố POST idempotent chỉ vì service đang kiểm tra trùng dữ liệu ở một số trường hợp. Cần xác định chính xác khóa idempotency, phạm vi áp dụng và hành vi khi cùng key được gửi với payload khác.

### 4.2. Status code phải phản ánh kết quả HTTP

Một số tình huống thường gặp:

| Tình huống | Status thường phù hợp |
|---|---|
| GET thành công có representation | 200 OK |
| Tạo resource thành công | 201 Created và thường có Location |
| Request được nhận để xử lý bất đồng bộ | 202 Accepted |
| Thành công không có response body | 204 No Content |
| Request sai cú pháp hoặc cấu trúc | 400 Bad Request |
| Chưa xác thực | 401 Unauthorized, thường kèm `WWW-Authenticate` |
| Không có quyền | 403 Forbidden |
| Resource không tồn tại hoặc không được tiết lộ | 404 Not Found |
| Xung đột với trạng thái hiện tại | 409 Conflict |
| Điều kiện request không thỏa | 412 Precondition Failed |
| Nội dung hợp lệ về cú pháp nhưng không xử lý được | 422 Unprocessable Content |
| Lỗi server không dự kiến | 500 Internal Server Error |
| Dịch vụ tạm thời không sẵn sàng | 503 Service Unavailable |

Không dùng 200 OK cho mọi tình huống rồi đặt success=false trong body. Generic HTTP client, cache, proxy và monitoring dựa vào status code để hiểu kết quả.

### 4.3. Location sau khi tạo resource

Khi POST tạo resource mới, response thường nên chỉ ra URI của resource bằng header Location:

~~~http
HTTP/1.1 201 Created
Location: /orders/42
Content-Type: application/hal+json
~~~

Body có thể chứa representation mới với link self. Client có thể tiếp tục điều hướng từ resource vừa tạo.

### 4.4. Cập nhật đồng thời và conditional request

Nếu hai client cùng đọc một order rồi cập nhật, request đến sau có thể ghi đè thay đổi của request trước. ETag và conditional request giúp phát hiện tình huống này.

Ví dụ server trả:

~~~http
HTTP/1.1 200 OK
ETag: "order-42-v7"
~~~

Client cập nhật với:

~~~http
PUT /orders/42
If-Match: "order-42-v7"
Content-Type: application/json
~~~

Nếu resource đã thay đổi và ETag không còn khớp, server có thể trả 412 Precondition Failed. Cơ chế này giúp ngăn lost update thay vì âm thầm ghi đè.

## 5. Đánh giá representation và content negotiation

Representation là dữ liệu mà client nhận được tại một thời điểm. Nó không nhất thiết giống entity hoặc database row.

Với Spring HATEOAS, các kiểu thường gặp:

| Kiểu | Mục đích |
|---|---|
| RepresentationModel<T> | Base model có thể gắn link |
| EntityModel<T> | Bọc một payload cùng link |
| CollectionModel<T> | Biểu diễn collection |
| PagedModel<T> | Biểu diễn collection có thông tin phân trang |

Không nên để entity persistence tự động trở thành hợp đồng công khai nếu nó chứa trường nội bộ, quan hệ không phù hợp hoặc thay đổi thường xuyên. Representation DTO giúp kiểm soát dữ liệu và ổn định hợp đồng.

### 5.1. Kiểm tra media type

Client gửi Accept để yêu cầu representation mong muốn. Server trả Content-Type cho biết media type thực tế.

Ví dụ HAL:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

HAL-FORMS có media type riêng:

~~~http
GET /orders/42
Accept: application/prs.hal-forms+json
~~~

HAL và HAL-FORMS không phải hai tên thay thế cho cùng một định dạng. HAL công bố resource và link; HAL-FORMS bổ sung _templates để mô tả form thao tác.

Review cần xác nhận:

- API hỗ trợ media type nào?
- Accept không được hỗ trợ xử lý thế nào?
- Content-Type của request body có được kiểm tra bằng consumes không?
- Client có thể phân biệt response HAL và HAL-FORMS không?
- Cache có tính đến Vary: Accept khi response thay đổi theo media type không?

### 5.2. Representation không nên lộ implementation detail

Kiểm tra JSON response có chứa:

- Tên bảng hoặc khóa ngoại chỉ dùng trong persistence.
- Trường nội bộ như passwordHash, access token hoặc secret.
- Lazy proxy hoặc object graph không kiểm soát.
- Trường có thể thay đổi theo refactor mà client không cần biết.
- Dữ liệu cá nhân vượt quá nhu cầu của use case.

Dùng request DTO và response representation riêng khi payload đầu vào/đầu ra có mục đích khác nhau. Validation của request không nên dựa vào việc entity có thể được deserialize.

## 6. Đánh giá hypermedia với Spring HATEOAS

HATEOAS có ý nghĩa khi representation giúp client khám phá tài nguyên và hành động tiếp theo. Chỉ thêm một link self vào JSON chưa đủ để chứng minh API đã hỗ trợ workflow hypermedia.

Một representation order có thể chứa:

~~~json
{
  "id": "42",
  "number": "ORD-2026-0042",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/orders/42"
    },
    "collection": {
      "href": "/orders"
    },
    "customer": {
      "href": "/orders/42/customer"
    }
  }
}
~~~

Review các điểm sau:

- Link self trỏ đúng resource đang biểu diễn.
- Relation mô tả đúng ý nghĩa của target.
- Link không được hard-code từ client hoặc từ một route không ổn định.
- Link quan hệ được công bố khi có ý nghĩa trong ngữ cảnh.
- Client có thể theo link để tiếp tục workflow.
- Relation chuẩn IANA được ưu tiên khi định nghĩa phù hợp.
- Custom relation có định danh ổn định và được mô tả rõ.

### 6.1. Dùng WebMvcLinkBuilder để tránh lặp URI

Spring HATEOAS cung cấp WebMvcLinkBuilder và methodOn(...) để xây link từ controller mapping:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();
~~~

Cách này giúp link theo mapping hiện tại của controller. Review nên phát hiện các chuỗi URI bị lặp rải rác trong controller, assembler và service.

Lưu ý: tham số method thông thường không tự động trở thành query template variable. methodOn(...) chủ yếu dùng mapping và path variable để tạo URI. Query parameter cần được khai báo và xử lý theo cơ chế phù hợp.

### 6.2. Dùng RepresentationModelAssembler để tập trung mapping

Khi nhiều endpoint trả cùng một resource, assembler giúp thống nhất payload và link:

~~~java
@Component
class OrderModelAssembler
        implements RepresentationModelAssembler<Order, EntityModel<OrderRepresentation>> {

    @Override
    public EntityModel<OrderRepresentation> toModel(Order order) {

        OrderRepresentation payload = new OrderRepresentation(
            order.getId(),
            order.getNumber(),
            order.getStatus().name()
        );

        Link self = linkTo(
            methodOn(OrderController.class).one(order.getId())
        ).withSelfRel();

        return EntityModel.of(payload, self);
    }
}
~~~

Các import chính:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Đây là ví dụ minh họa. Trong ứng dụng thật, assembler có thể thêm link theo trạng thái order, relation tới customer, payment hoặc cancellation. Review cần bảo đảm cùng một loại resource không có cách tạo link khác nhau ở từng controller mà không có lý do.

### 6.3. Kiểm tra affordance và hành động khả dụng

Một order đang PENDING có thể cho phép yêu cầu hủy; order đã SHIPPED có thể không còn khả năng đó. Affordance cho phép server mô tả method và input mà client có thể gửi.

Ví dụ:

~~~java
Link self = linkTo(
    methodOn(OrderController.class).one(orderId)
).withSelfRel();

if (order.canRequestCancellation()) {
    self = self.andAffordance(
        afford(methodOn(OrderController.class).cancel(orderId, null))
    );
}

return EntityModel.of(representation, self);
~~~

Controller method được trỏ tới có thể khai báo trong controller có base mapping `/orders`:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

@PostMapping(
    value = "/{id}/cancellations",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<?> cancel(
        @PathVariable UUID id,
        @Valid @RequestBody CancelOrderRequest request) {
    // Xác thực quyền, kiểm tra trạng thái và tạo cancellation request.
    return ResponseEntity.accepted().build();
}
}
~~~

Các import liên quan đến affordance và request:

~~~java
import java.util.UUID;

import jakarta.validation.Valid;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;
~~~

Khi client yêu cầu HAL-FORMS, affordance có thể được chuyển thành template mô tả HTTP method, target và properties.

Review cần hỏi:

- Hành động có được công bố đúng theo trạng thái nghiệp vụ không?
- Input model có chỉ chứa trường client được phép gửi không?
- consumes có khớp với contentType được mô tả không?
- Template có phản ánh đúng method và target của controller không?
- Server có kiểm tra quyền và trạng thái lại khi nhận request không?

Ẩn affordance chỉ cải thiện trải nghiệm client. Nó không thay thế authorization ở server.

### 6.4. Kiểm tra link sau khi qua reverse proxy

Nếu ứng dụng chạy sau proxy hoặc load balancer, link absolute có thể được dựng từ host nội bộ nếu forwarded header không được xử lý đúng. Ngược lại, tin forwarded header từ nguồn không đáng tin có thể tạo link giả mạo.

Review deployment cần xác nhận proxy được tin cậy và forwarded header handling được cấu hình đúng. Không bật xử lý forwarded header một cách mù quáng trên mọi request từ Internet.

## 7. Đánh giá lỗi bằng Problem Details

Status code cho biết loại kết quả HTTP tổng quát. Body lỗi nên giúp client nhận diện loại vấn đề và biết cách khắc phục.

RFC 9457 định nghĩa Problem Details cho HTTP API, sử dụng JSON media type application/problem+json. Spring HATEOAS cũng có kiểu Problem để tạo response theo định dạng này.

Ví dụ lỗi validation:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Order data is invalid",
  "status": 422,
  "detail": "The requested delivery date is not available.",
  "instance": "/orders/requests/8f9d",
  "errors": [
    {
      "pointer": "#/deliveryDate",
      "detail": "Choose a date within the next 30 days."
    }
  ]
}
~~~

Các thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| type | URI định danh loại problem |
| title | Mô tả ngắn, ổn định cho loại problem |
| status | Status code được gắn với problem |
| detail | Giải thích cho lần xảy ra cụ thể |
| instance | Định danh occurrence |
| Extension members | Dữ liệu máy đọc được dành riêng cho problem type |

Review cần xác nhận:

- HTTP status vẫn phản ánh lỗi chính xác.
- type ổn định và mô tả một loại problem.
- detail giúp client sửa request, không tiết lộ stack trace.
- Client không phải parse câu văn trong detail để tìm mã lỗi.
- Extension field có tên và kiểu dữ liệu ổn định.
- Không đưa secret, SQL, tên class hoặc thông tin nội bộ vào response.

Nếu lỗi hoàn toàn chung và status code đã đủ nghĩa, không cần tạo một problem type riêng cho mọi trường hợp.

## 8. Đánh giá bảo mật của API

Bảo mật phải được review ở từng resource, property và thao tác. Việc API có authentication không đồng nghĩa các request đều được authorization đúng.

### 8.1. Object-level authorization

Với endpoint:

~~~http
GET /orders/42
~~~

server phải xác minh người dùng hiện tại được phép đọc order 42. Không được coi việc client biết ID là bằng chứng sở hữu hoặc quyền truy cập.

Kiểm tra tương tự cho PUT, PATCH, DELETE, download file và mọi endpoint nhận object identifier.

### 8.2. Property-level authorization và mass assignment

Nếu request nhận trực tiếp entity, client có thể thử gửi thêm trường như:

~~~json
{
  "deliveryAddress": "New address",
  "status": "PAID",
  "approvedBy": "admin"
}
~~~

Một API chỉ cho phép cập nhật địa chỉ giao hàng không được bind các trường trạng thái hoặc người phê duyệt từ payload này.

Dùng request DTO chỉ chứa trường cho phép, validate dữ liệu và kiểm tra quyền ở server. Không dựa vào UI hoặc projection để ngăn client gửi property khác.

### 8.3. Function-level authorization

Các hành động như approve, refund, cancel hoặc export cần kiểm tra quyền riêng. Một người dùng có thể được phép đọc order nhưng không có quyền hoàn tiền.

Review mọi affordance và endpoint action, xác nhận quyền ở server được áp dụng cả khi client gọi URI trực tiếp.

### 8.4. Giới hạn tài nguyên và luồng nghiệp vụ

API cần giới hạn:

- Kích thước request body và upload.
- Page size, số filter và độ dài query.
- Số lần gọi các thao tác tốn kém.
- Tần suất tạo tài khoản, đặt hàng, gửi OTP hoặc hoàn tiền.
- Số request đồng thời và thời gian xử lý.

Các luồng nhạy cảm có thể cần rate limit, quota, xác minh bổ sung hoặc kiểm soát chống tự động hóa. Đánh giá theo rủi ro nghiệp vụ thay vì chỉ dựa trên số endpoint.

### 8.5. Kiểm tra URL do client cung cấp

Nếu API nhận URL để tải ảnh, gọi webhook hoặc nhập dữ liệu từ xa, cần đánh giá SSRF. Không truy cập URL tùy ý mà không có allowlist, kiểm tra địa chỉ IP/redirect và giới hạn giao thức phù hợp.

### 8.6. Không dùng link hypermedia làm cơ chế bảo mật

Server có thể không công bố link refund nếu user không có quyền hoàn tiền. Tuy vậy, client có thể tự gửi request đến endpoint nếu biết URI.

Authorization phải được kiểm tra trên từng request. Link chỉ giúp client hiểu hành động đang được công bố trong representation hiện tại.

## 9. Đánh giá caching, concurrency và hiệu năng

Một API design review cần kiểm tra khả năng vận hành khi dữ liệu lớn, nhiều client truy cập đồng thời và response được cache qua intermediary.

### 9.1. Cache policy và validator

GET response có thể được cache khi chính sách cho phép. Review:

- Cache-Control có phù hợp với dữ liệu công khai hoặc riêng tư không?
- Response có chứa dữ liệu người dùng mà shared cache không được lưu không?
- ETag hoặc Last-Modified có giúp kiểm tra thay đổi không?
- Vary có liệt kê header làm thay đổi representation như Accept hoặc Accept-Language không?
- Response thay đổi theo quyền có được cache an toàn không?

Không dùng một cache policy giống nhau cho mọi resource. Dữ liệu nhạy cảm hoặc cá nhân thường cần chính sách riêng.

### 9.2. Pagination và collection lớn

Không nên trả hàng trăm nghìn phần tử trong một response. API cần xác định page size tối đa, thứ tự ổn định và link điều hướng.

Với Spring HATEOAS, PagedModel có thể biểu diễn collection cùng metadata trang và các link như first, prev, next, last.

Review các trường hợp:

- Collection rỗng có representation rõ ràng.
- Page size vượt giới hạn bị từ chối hoặc giới hạn theo chính sách.
- Sort field được allowlist.
- Pagination không bỏ sót hoặc lặp item khi dữ liệu thay đổi trong quá trình duyệt.
- Link next và prev phản ánh chính xác query hiện tại.

### 9.3. Tránh N+1 và payload quá lớn

Representation có nhiều embedded resource có thể thuận tiện cho client nhưng cũng làm tăng query và payload. Review bằng dữ liệu có quy mô thực tế:

- Số query khi đọc collection.
- Số association được tải.
- Kích thước response.
- Thời gian serialize.
- Số link hoặc embedded object cho mỗi item.

Chỉ embed dữ liệu cần cho use case. Có thể công bố link tới resource liên quan để client tải khi cần, thay vì luôn nhúng toàn bộ graph.

### 9.4. Retry và xử lý bất đồng bộ

Nếu thao tác mất nhiều thời gian, cân nhắc trả 202 Accepted cùng link đến resource theo dõi trạng thái công việc. Client có thể poll resource đó hoặc theo link callback nếu hợp đồng hỗ trợ.

Đừng giữ request đồng bộ lâu chỉ để client chờ. Đừng khuyến khích client retry POST không có cơ chế chống tạo trùng khi kết quả lần đầu chưa rõ.

## 10. Đánh giá khả năng tiến hóa của hợp đồng

API sẽ thay đổi theo nghiệp vụ. Review cần xác định thay đổi nào có thể triển khai mà không làm client cũ hỏng.

Các thay đổi thường có rủi ro phá vỡ:

- Xóa hoặc đổi tên field.
- Đổi kiểu dữ liệu của field.
- Thay query parameter hoặc ngữ nghĩa filter.
- Thêm field bắt buộc vào request cũ.
- Đổi method, status code hoặc media type.
- Xóa relation mà client đang theo.
- Đổi ý nghĩa của custom relation.
- Thay đổi mặc định sort hoặc pagination mà không công bố.
- Đổi response shape của collection hoặc embedded resource.

Các thay đổi thường dễ tương thích hơn nếu client bỏ qua dữ liệu chưa biết:

- Thêm field response tùy chọn.
- Thêm link relation mới.
- Thêm affordance tùy chọn.
- Thêm một filter mới mà không đổi nghĩa filter cũ.

Đây không phải bảo đảm tuyệt đối. Một client có thể dùng schema strict hoặc phụ thuộc thứ tự field. Cần kiểm tra cách client tiêu thụ representation trước khi kết luận thay đổi là an toàn.

### 10.1. Giữ relation ổn định qua thay đổi URL

Client hypermedia nên tìm link theo relation và theo href server công bố. Nếu endpoint chuyển từ /orders/42/history sang /order-history/42, relation mô tả lịch sử đơn hàng có thể giữ nguyên nếu ngữ nghĩa không đổi.

Không tái sử dụng một relation cho ý nghĩa mới. Nếu ngữ nghĩa thay đổi không tương thích, định nghĩa relation mới và có kế hoạch chuyển đổi.

### 10.2. Versioning là quyết định hợp đồng

Có thể version API bằng URI, media type hoặc một chiến lược tương thích có kiểm soát. Không có một lựa chọn phù hợp cho mọi hệ thống.

Review cần xác nhận:

- Khi nào một thay đổi cần version mới?
- Client cũ được hỗ trợ trong bao lâu?
- Có chính sách deprecation và thông báo thời điểm ngừng hỗ trợ không?
- Có contract test cho từng phiên bản đang vận hành không?
- Hypermedia link có dẫn client đến resource cùng phiên bản hoặc profile phù hợp không?

Không version mọi endpoint theo phản xạ nếu có thể giữ tương thích. Cũng không âm thầm thay đổi semantics của một phiên bản đang được client sử dụng.

## 11. Đánh giá khả năng kiểm thử và tài liệu

Một API dễ review cần có bằng chứng kiểm thử cho hợp đồng, không chỉ unit test cho service.

### 11.1. Contract test bằng MockMvc

Ví dụ kiểm tra một order resource:

~~~java
mvc.perform(get("/orders/{id}", orderId)
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$.status").value("PENDING"));
~~~

Các import chính:

~~~java
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Test nên xác nhận cả status, media type, field quan trọng và link relation. Không chỉ kiểm tra body chứa một chuỗi JSON bất kỳ.

### 11.2. Kiểm thử affordance và trạng thái

Nếu cancellation chỉ khả dụng khi order đang pending, test hai trạng thái:

- PENDING: representation công bố affordance yêu cầu hủy.
- SHIPPED: representation không công bố affordance đó.

Sau đó gọi trực tiếp endpoint trong cả hai trạng thái để xác nhận server từ chối thao tác không hợp lệ. Test link và test authorization/state transition là hai kiểm tra riêng.

### 11.3. Kiểm thử lỗi và header

Ngoài JSON body, hãy kiểm tra:

- Status code.
- Content-Type application/problem+json khi trả Problem Details.
- Location sau khi tạo resource.
- ETag và phản hồi conditional request.
- Cache-Control và Vary.
- Allow nếu cần cho method discovery.
- Retry-After trong trường hợp server yêu cầu client chờ.

### 11.4. Tài liệu và ví dụ

Tài liệu nên có:

- Entry point hoặc cách khám phá API.
- Media type được hỗ trợ.
- Authentication và authorization model.
- Request/response mẫu.
- Error model và problem type.
- Query parameter, pagination và sort contract.
- Link relation và affordance quan trọng.
- Rate limit, retry và versioning policy.

OpenAPI có thể mô tả endpoint, schema và status code. Với API hypermedia, tài liệu cũng cần giải thích semantics của relation, URI template và cách client khám phá workflow.

## 12. Ví dụ review một API đơn hàng

Giả sử API ban đầu có các endpoint:

~~~text
GET    /orders/42/cancel
POST   /orders/42/updateStatus
GET    /orders?state=all
GET    /orders/42
~~~

Response của GET /orders/42:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "canCancel": true,
  "cancelUrl": "/orders/42/cancel",
  "customerPasswordHash": "..."
}
~~~

Một số vấn đề có thể nhận diện:

| Vấn đề | Rủi ro | Hướng sửa |
|---|---|---|
| GET /cancel làm thay đổi trạng thái | Crawler hoặc prefetch có thể hủy đơn | Dùng POST cho cancellation request |
| POST /updateStatus nhận trạng thái tùy ý | Client có thể tự đặt trạng thái nghiệp vụ | Thiết kế transition cụ thể và kiểm tra quyền |
| state=all không mô tả rõ filter | Query contract khó mở rộng | Dùng filter rõ nghĩa và tài liệu hóa |
| cancelUrl là field tự ghép | Client phải tự hiểu URL | Công bố link relation hoặc affordance |
| Password hash xuất hiện trong response | Lộ dữ liệu nhạy cảm | Loại bỏ khỏi representation |
| canCancel có thể lệch với server state | UI hiển thị hành động không còn hợp lệ | Dùng affordance để mô tả, server vẫn xác minh |

Một thiết kế có thể được cải thiện:

~~~text
GET    /orders
GET    /orders/42
POST   /orders/42/cancellations
GET    /orders/42/cancellations/{cancellationId}
~~~

Representation order:

~~~json
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
~~~

Nếu order đang cho phép yêu cầu hủy, server có thể gắn affordance POST vào link self. Client HAL-FORMS có thể khám phá template và các property được phép gửi. Khi order chuyển sang trạng thái không thể hủy, affordance không còn được công bố.

Khi client submit:

~~~http
POST /orders/42/cancellations
Content-Type: application/json

{
  "reason": "Customer request"
}
~~~

Server phải xác minh quyền sở hữu, kiểm tra trạng thái order và validate reason. Nếu tạo cancellation resource, trả 201 Created cùng Location; nếu nhận một công việc bất đồng bộ, trả 202 Accepted cùng link theo dõi trạng thái.

Thiết kế này làm rõ resource cancellation và dùng method HTTP phù hợp với hành động thay đổi trạng thái.

## 13. Rubric chấm điểm API design

Có thể dùng rubric dưới đây để review nhất quán giữa các endpoint. Mỗi nhóm được chấm từ 0 đến 2:

- 0: thiếu, sai ngữ nghĩa hoặc có rủi ro nghiêm trọng.
- 1: có một phần nhưng thiếu nhất quán hoặc thiếu bằng chứng.
- 2: rõ ràng, nhất quán và có test hoặc tài liệu chứng minh.

| Nhóm | Điểm cần xem xét |
|---|---|
| Resource model và URI | Resource, collection, quan hệ và query contract rõ ràng |
| HTTP semantics | Method, status, header, safe/idempotent đúng |
| Representation | DTO, media type và content negotiation phù hợp |
| Hypermedia | Relation, link, template và affordance chính xác |
| Error handling | Status và Problem Details nhất quán |
| Security | Authentication, object/property/function authorization, giới hạn tải |
| Reliability và performance | Cache, ETag, pagination, retry, query và payload |
| Evolution và testing | Tương thích, versioning, contract test và tài liệu |

Tổng tối đa là 16 điểm. Có thể dùng cách diễn giải nội bộ sau:

| Tổng điểm | Đánh giá tham khảo |
|---|---|
| 0–7 | Cần thiết kế lại các phần cốt lõi |
| 8–11 | Có thể dùng thử trong phạm vi hạn chế sau khi xử lý rủi ro |
| 12–14 | Thiết kế tương đối vững, cần hoàn tất các điểm còn thiếu |
| 15–16 | Có bằng chứng tốt trên các nhóm review |

Điểm số không thay thế đánh giá rủi ro. Một lỗi nghiêm trọng về authorization, rò rỉ dữ liệu hoặc method HTTP gây side effect vẫn cần được xử lý trước khi phát hành dù tổng điểm cao.

Mỗi nhận xét review nên ghi:

1. Bằng chứng: endpoint, request/response, đoạn code hoặc test.
2. Tác động: client, dữ liệu hoặc luồng nghiệp vụ bị ảnh hưởng.
3. Mức độ: blocker, high, medium hoặc low theo chính sách nhóm.
4. Đề xuất: thay đổi hợp đồng hoặc implementation cụ thể.
5. Cách xác nhận: test hoặc tiêu chí nghiệm thu.

## 14. Checklist dùng trong pull request

Có thể dùng checklist sau khi review một API mới hoặc thay đổi API hiện có.

### Resource và HTTP

- [ ] Resource phản ánh đúng khái niệm nghiệp vụ.
- [ ] URI không phụ thuộc tên bảng hoặc package nội bộ.
- [ ] Query parameter có ý nghĩa và giới hạn rõ ràng.
- [ ] GET không gây thay đổi trạng thái nghiệp vụ.
- [ ] POST, PUT, PATCH và DELETE dùng đúng semantics.
- [ ] Status code phản ánh kết quả thực tế.
- [ ] Tạo resource có Location khi phù hợp.
- [ ] Retry và idempotency được thiết kế cho thao tác cần thiết.

### Representation và hypermedia

- [ ] Response không lộ entity field hoặc dữ liệu nhạy cảm.
- [ ] Accept và Content-Type được xử lý nhất quán.
- [ ] Link self trỏ đúng resource.
- [ ] Relation phản ánh đúng ý nghĩa của target.
- [ ] URI template chỉ công bố biến được hỗ trợ.
- [ ] Affordance phản ánh đúng method, target và input.
- [ ] Hành động phụ thuộc trạng thái được công bố phù hợp.
- [ ] Server kiểm tra lại quyền và trạng thái khi nhận request.

### Errors, security và operations

- [ ] Status code và Problem Details có cấu trúc nhất quán.
- [ ] Authorization được kiểm tra theo object, property và function.
- [ ] Request DTO không cho mass assignment ngoài ý muốn.
- [ ] Có giới hạn payload, pagination, query và rate.
- [ ] Cache policy, ETag và Vary phù hợp.
- [ ] Không để lỗi tiết lộ stack trace hoặc secret.
- [ ] Forwarded header chỉ được tin từ proxy được kiểm soát.

### Evolution và tests

- [ ] Thay đổi response/query/link được đánh giá tương thích.
- [ ] Custom relation giữ URI và ngữ nghĩa ổn định.
- [ ] Contract test kiểm tra status, media type, payload và link.
- [ ] Có test cho state transition và authorization.
- [ ] Có test cho lỗi, conditional request và cache header khi cần.
- [ ] Tài liệu request/response và workflow được cập nhật.

## 15. Kết luận

Đánh giá API design cần nhìn hợp đồng từ góc độ client và vận hành: resource có được mô hình hóa rõ ràng không, HTTP method và status code có đúng ngữ nghĩa không, representation có ổn định không, hypermedia có giúp khám phá workflow không, lỗi có thể được xử lý bằng máy không, và bảo mật có được kiểm tra tại server không.

Trong Spring HATEOAS, RepresentationModel, EntityModel, CollectionModel, WebMvcLinkBuilder và affordance giúp xây dựng hợp đồng hypermedia. Review cần xác nhận link và template phản ánh đúng endpoint, trạng thái và input; đồng thời không coi việc ẩn link là cơ chế phân quyền. Khi kết hợp contract test, Problem Details, conditional request, cache policy và quy tắc tương thích, nhóm có thể phát hiện sớm những thiết kế gây khó khăn cho client trước khi API được phát hành.

## Tài liệu tham khảo

- [Spring HATEOAS Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/): representation model, link relation, URI template, controller link builder, affordance, HAL, HAL-FORMS và Problem Details.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): method semantics, safe/idempotent, status code, content negotiation và conditional request.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): định dạng lỗi máy đọc được application/problem+json.
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html): link relation và thuộc tính liên kết.
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/): các nhóm rủi ro như broken object/property/function authorization, unrestricted resource consumption và SSRF.
- [Spring Framework — Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html): nền tảng request mapping, request handling và response handling của Spring MVC.

