# Link đến tài liệu lỗi trong Spring HATEOAS

Khi API trả lỗi, client cần biết lỗi thuộc loại nào và có thể tìm hướng xử lý ở đâu. Một response chỉ có HTTP status và thông báo ngắn thường chưa đủ để ứng dụng hoặc người vận hành hiểu lỗi theo cách nhất quán.

Với Problem Details, mỗi loại lỗi có thể được định danh bằng một URI ổn định. URI này có thể dẫn tới trang tài liệu giải thích nguyên nhân, điều kiện phát sinh và cách khắc phục. API cũng có thể công bố link relation **describedby** trong HTTP response header để client nhận biết liên kết tài liệu mà không phải tự suy luận từ nội dung thông báo.

Bài này tập trung vào cách thiết kế link đến tài liệu lỗi bằng RFC 9457, Spring MVC và Spring HATEOAS. Ví dụ sử dụng lỗi xung đột trạng thái đơn hàng khi client cố hủy một đơn đã được giao.

## 1. Vì sao response lỗi cần link đến tài liệu?

HTTP status mô tả nhóm kết quả ở mức giao thức. Ví dụ:

- **400 Bad Request** cho biết request không hợp lệ.
- **401 Unauthorized** cho biết request cần xác thực.
- **403 Forbidden** cho biết máy chủ từ chối quyền truy cập.
- **404 Not Found** cho biết không tìm thấy tài nguyên.
- **409 Conflict** cho biết request xung đột với trạng thái hiện tại.
- **422 Unprocessable Content** cho biết nội dung request có cú pháp hợp lệ nhưng không thể xử lý theo quy tắc nghiệp vụ.

Status giúp client chọn cách xử lý tổng quát, nhưng chưa giải thích một lỗi nghiệp vụ cụ thể. Ví dụ hai lỗi đều trả **409 Conflict** nhưng có thể có cách khắc phục khác nhau: đơn hàng đã được giao nên không thể hủy; phiên bản dữ liệu đã cũ nên client cần tải lại resource; hoặc một thao tác khác đang giữ quyền cập nhật tài nguyên.

Một trang tài liệu lỗi có thể giải thích điều kiện phát sinh, cách khắc phục và các quy tắc nghiệp vụ liên quan. Khi response cung cấp URI đến tài liệu, client, công cụ hỗ trợ và người vận hành có một điểm tham chiếu ổn định.

## 2. Problem Details và các trường tiêu chuẩn

RFC 9457 định nghĩa Problem Details để mô tả lỗi HTTP bằng dữ liệu có cấu trúc. JSON representation sử dụng media type:

~~~http
Content-Type: application/problem+json
~~~

Một response ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "The order cannot be cancelled because it has already been shipped.",
  "instance": "urn:uuid:6b6dfbf0-6a4f-4e2a-b4d4-ae41d68d8a13"
}
~~~

Các trường tiêu chuẩn có vai trò riêng:

| Trường | Vai trò |
|---|---|
| **type** | URI định danh loại lỗi |
| **title** | Tên ngắn, ổn định của loại lỗi |
| **status** | HTTP status code được mô tả trong body |
| **detail** | Giải thích cụ thể cho lần lỗi hiện tại |
| **instance** | URI nhận diện lần xuất hiện lỗi cụ thể |

Trong đó, **type** là trường quan trọng nhất khi thiết kế tài liệu lỗi. Client dùng URI này làm định danh chính của problem type. Nếu URI dùng HTTP hoặc HTTPS và có thể truy cập, RFC 9457 khuyến nghị URI đó cung cấp tài liệu HTML giải thích lỗi và cách khắc phục.

Nếu không có trường **type**, giá trị mặc định được hiểu là **about:blank**. Loại này chỉ mang semantics của HTTP status code, không bổ sung ý nghĩa nghiệp vụ riêng.

## 3. Phân biệt type URI và instance URI

Hai trường này thường bị dùng nhầm.

**Type URI** định danh một loại lỗi. Nhiều request khác nhau có thể gặp cùng problem type.

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict"
}
~~~

**Instance URI** nhận diện một lần xảy ra lỗi cụ thể. Mỗi lần lỗi có thể có một instance khác nhau.

~~~json
{
  "instance": "urn:uuid:6b6dfbf0-6a4f-4e2a-b4d4-ae41d68d8a13"
}
~~~

Một ví dụ khác:

| URI | Ý nghĩa | Có nên dẫn tới tài liệu chung? |
|---|---|---|
| /problems/order-state-conflict | Loại lỗi nghiệp vụ | Có |
| urn:uuid:... | Một lần lỗi cụ thể | Không bắt buộc |
| /problem-occurrences/12345 | Hồ sơ của một lần lỗi nếu API cung cấp | Có thể, với quyền truy cập phù hợp |

Không đặt URI tài liệu vào **instance** chỉ vì muốn tạo một link trợ giúp. Làm vậy khiến client hiểu nhầm tài liệu chung là một lần lỗi cụ thể.

## 4. Thiết kế type URI ổn định

Một type URI nên có các đặc điểm:

- Ổn định trong suốt vòng đời của problem type.
- Dùng URI tuyệt đối khi có thể.
- Không phụ thuộc vào host nội bộ hoặc đường dẫn triển khai tạm thời.
- Có thể truy cập từ môi trường mà client cần đọc tài liệu.
- Trỏ tới tài liệu giải thích đúng loại lỗi.
- Không chứa thông tin cá nhân, token hoặc dữ liệu của lần request cụ thể.

Ví dụ:

~~~text
https://api.example.com/problems/order-state-conflict
https://api.example.com/problems/insufficient-credit
https://api.example.com/problems/invalid-shipping-address
~~~

Không nên dùng một URI chung như **https://api.example.com/errors** cho tất cả loại lỗi nếu URI đó không giúp client phân biệt problem type. Nếu mọi lỗi cùng trỏ đến một trang index, client vẫn phải tìm kiếm thủ công loại lỗi cần đọc.

Cũng không nên tạo type URI có query parameter thay đổi theo request:

~~~text
https://api.example.com/problems/order-state-conflict?orderId=42
~~~

Thông tin định danh loại lỗi cần tách biệt với dữ liệu của lần lỗi cụ thể. Đặt order ID trong **instance** hoặc một extension member phù hợp nếu client thực sự cần thông tin đó.

## 5. Nội dung của trang tài liệu lỗi

Khi type URI được mở trong trình duyệt, tài liệu nên giúp người đọc hiểu và xử lý lỗi.

Một trang tài liệu cho **order-state-conflict** có thể gồm:

1. Tên lỗi và type URI chính thức.
2. HTTP status code thường dùng.
3. Mô tả ngắn về điều kiện phát sinh.
4. Các nguyên nhân nghiệp vụ thường gặp.
5. Cách client có thể khôi phục.
6. Trường hợp nào cần người vận hành can thiệp.
7. Ví dụ Problem Details response.
8. Các extension member có thể xuất hiện.
9. Các link relation hoặc hành động liên quan.
10. Chính sách tương thích và thay đổi của problem type.

Ví dụ nội dung:

~~~text
Problem type: Order state conflict
Type URI: https://api.example.com/problems/order-state-conflict
HTTP status: 409 Conflict

When it occurs:
The requested operation is not valid for the current order state.

Common cause:
The order has already been shipped or delivered.

How to resolve:
Refresh the order representation and inspect its current state.
If the order has already shipped, contact the support workflow for
a return or cancellation exception.
~~~

Tài liệu cần phân biệt thao tác client có thể tự thực hiện và thao tác cần người dùng hoặc nhân viên hỗ trợ. Không hướng dẫn client thử lại vô hạn nếu trạng thái nghiệp vụ không thể tự thay đổi.

## 6. Link relation describedby

HTTP Web Linking định nghĩa các link relation để mô tả mối quan hệ giữa response và tài nguyên đích.

Relation **describedby** có ý nghĩa: đích của link cung cấp thông tin mô tả cho tài nguyên ở ngữ cảnh hiện tại.

Ví dụ response header:

~~~http
Link: <https://api.example.com/problems/order-state-conflict>; rel="describedby"; type="text/html"
~~~

Header này cho client biết có một tài liệu HTML mô tả lỗi hiện tại.

Spring HATEOAS cung cấp relation tương ứng:

~~~java
IanaLinkRelations.DESCRIBED_BY
~~~

Có thể tạo Link object:

~~~java
Link documentationLink = Link.of(
    "https://api.example.com/problems/order-state-conflict",
    IanaLinkRelations.DESCRIBED_BY
).withType(MediaType.TEXT_HTML_VALUE)
 .withTitle("Order state conflict documentation");
~~~

Relation **help** cũng là relation chuẩn và phù hợp khi đích là tài nguyên trợ giúp theo ngữ cảnh. Hai relation có sắc thái khác nhau:

| Relation | Khi sử dụng |
|---|---|
| describedby | Tài liệu mô tả problem type hoặc response |
| help | Trang trợ giúp theo ngữ cảnh, hướng dẫn người dùng |
| about | Tài nguyên là chủ đề được đề cập trong ngữ cảnh link |

Với trang tài liệu định nghĩa problem type, **describedby** thường diễn đạt chính xác hơn.

## 7. Dùng type URI và Link header cùng nhau

**type** và HTTP **Link** header có thể cùng trỏ tới tài liệu nhưng không có cùng vai trò.

- **type** là định danh chính của problem type theo RFC 9457.
- **Link: rel="describedby"** công bố một liên kết có quan hệ mô tả theo RFC 8288.

Nếu type URI có thể truy cập và chính nó phục vụ tài liệu lỗi, hai URI có thể giống nhau. Nếu API có trang định danh problem type riêng và trang hướng dẫn hỗ trợ riêng, chúng có thể khác nhau.

Ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Link: <https://api.example.com/docs/order-state-conflict>; rel="describedby"; type="text/html"

{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "The order cannot be cancelled because it has already shipped.",
  "instance": "urn:uuid:6b6dfbf0-6a4f-4e2a-b4d4-ae41d68d8a13"
}
~~~

Client có thể dùng **type** để phân loại lỗi và dùng relation **describedby** để hiển thị tài liệu hướng dẫn. Không nên bắt client phân tích nội dung **detail** để suy ra URL tài liệu.

## 8. Tạo ProblemDetail trong Spring MVC

Spring Framework hỗ trợ RFC 9457 qua **ProblemDetail**, **ErrorResponse**, **ErrorResponseException** và **ResponseEntityExceptionHandler**.

Ví dụ dùng **@RestControllerAdvice** để xử lý một lỗi nghiệp vụ:

~~~java
import java.net.URI;
import java.util.UUID;

import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiProblemHandler {

    private static final URI ORDER_STATE_CONFLICT_TYPE =
        URI.create(
            "https://api.example.com/problems/order-state-conflict"
        );

    @ExceptionHandler(OrderStateConflictException.class)
    ResponseEntity<ProblemDetail> handleOrderStateConflict(
            OrderStateConflictException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "The order cannot be cancelled because it has already shipped."
        );

        problem.setType(ORDER_STATE_CONFLICT_TYPE);
        problem.setTitle("Order state conflict");
        problem.setInstance(
            URI.create("urn:uuid:" + UUID.randomUUID())
        );

        HttpHeaders headers = new HttpHeaders();
        headers.add(
            HttpHeaders.LINK,
            "<" + ORDER_STATE_CONFLICT_TYPE + ">; rel=\"describedby\"; type=\"text/html\""
        );

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .headers(headers)
            .contentType(MediaTypes.HTTP_PROBLEM_DETAILS_JSON)
            .body(problem);
    }
}
~~~

Trong ví dụ:

- **ProblemDetail** giữ các trường tiêu chuẩn của RFC 9457.
- **type** trỏ tới URI tài liệu ổn định.
- **instance** được tạo riêng cho mỗi lần lỗi.
- Header **Link** công bố relation **describedby**.
- **MediaTypes.HTTP_PROBLEM_DETAILS_JSON** xác định media type **application/problem+json**.

Nếu ứng dụng đã có **@ControllerAdvice** kế thừa **ResponseEntityExceptionHandler**, có thể đặt logic bổ sung vào exception handler hoặc phương thức xử lý phù hợp. Spring MVC cũng cung cấp **ErrorResponse** để exception mang theo status, headers và body Problem Details.

## 9. Dùng Link object để xây HTTP Link header

Khi API có nhiều loại lỗi, nên tập trung việc tạo link tài liệu vào một helper để tránh lặp chuỗi relation và header.

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

final class ProblemDocumentationLinks {

    private ProblemDocumentationLinks() {
    }

    static Link orderStateConflict() {
        return Link.of(
            "https://api.example.com/problems/order-state-conflict",
            IanaLinkRelations.DESCRIBED_BY
        )
        .withType(MediaType.TEXT_HTML_VALUE)
        .withTitle("Order state conflict documentation");
    }

    static void addTo(HttpHeaders headers, Link link) {
        String value = "<" + link.getHref() + ">; rel=\""
            + link.getRel().value() + "\"";

        if (link.getType() != null) {
            value += "; type=\"" + link.getType() + "\"";
        }

        if (link.getTitle() != null) {
            value += "; title=\"" + link.getTitle() + "\"";
        }

        headers.add(HttpHeaders.LINK, value);
    }
}
~~~

Sử dụng:

~~~java
HttpHeaders headers = new HttpHeaders();

ProblemDocumentationLinks.addTo(
    headers,
    ProblemDocumentationLinks.orderStateConflict()
);
~~~

Helper này tạo Link bằng API Spring HATEOAS, sau đó serialize các thuộc tính cần thiết thành cú pháp HTTP Link header. Nếu mở rộng để nhận URI hoặc title động, cần bảo đảm giá trị được kiểm soát và escape đúng cú pháp header.

## 10. Thêm link như extension member trong Problem Details

HTTP Link header là cách chuẩn để công bố link ngoài response body. Một API cũng có thể định nghĩa extension member nếu client cần đọc danh sách link trực tiếp từ JSON.

RFC 9457 cho phép problem type định nghĩa các extension member, trong đó có thể chứa typed links để hệ thống máy móc sử dụng.

Ví dụ extension **links**:

~~~json
{
  "type": "https://api.example.com/problems/order-state-conflict",
  "title": "Order state conflict",
  "status": 409,
  "detail": "The order cannot be cancelled because it has already shipped.",
  "instance": "urn:uuid:6b6dfbf0-6a4f-4e2a-b4d4-ae41d68d8a13",
  "links": [
    {
      "rel": "describedby",
      "href": "https://api.example.com/problems/order-state-conflict",
      "type": "text/html",
      "title": "Order state conflict documentation"
    }
  ]
}
~~~

**links** ở đây là extension do API định nghĩa, không phải một trường tiêu chuẩn có cấu trúc cố định của RFC 9457. API phải công bố schema của extension để client biết cách đọc rel, href, type và title.

Trong Spring MVC, có thể thêm extension bằng **ProblemDetail.setProperty**:

~~~java
Link documentationLink =
    ProblemDocumentationLinks.orderStateConflict();

problem.setProperty(
    "links",
    List.of(Map.of(
        "rel", documentationLink.getRel().value(),
        "href", documentationLink.getHref(),
        "type", documentationLink.getType(),
        "title", documentationLink.getTitle()
    ))
);
~~~

Spring Framework với Jackson hỗ trợ map properties của ProblemDetail thành các top-level extension member trong JSON. Vì vậy, property links được serialize ngang hàng với type, title, status, detail và instance.

Không đặt tên extension là **_links** rồi mặc định cho rằng response sẽ trở thành HAL. **application/problem+json** vẫn là Problem Details; extension links chỉ có semantics do API công bố.

## 11. Spring HATEOAS Problem và extension links

Spring HATEOAS có lớp **org.springframework.hateoas.mediatype.problem.Problem** để tạo representation theo định dạng Problem Details kiểu RFC 7807. RFC 9457 kế nhiệm RFC 7807 và giữ mô hình các trường cốt lõi này.

Có thể xây dựng Problem và bổ sung extension:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.problem.Problem;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;

URI type = URI.create(
    "https://api.example.com/problems/order-state-conflict"
);

Link documentationLink = Link.of(
    type.toString(),
    IanaLinkRelations.DESCRIBED_BY
)
.withType(MediaType.TEXT_HTML_VALUE)
.withTitle("Order state conflict documentation");

Problem baseProblem = Problem.create()
    .withType(type)
    .withTitle("Order state conflict")
    .withStatus(HttpStatus.CONFLICT)
    .withDetail(
        "The order cannot be cancelled because it has already shipped."
    )
    .withInstance(
        URI.create("urn:uuid:6b6dfbf0-6a4f-4e2a-b4d4-ae41d68d8a13")
    );

Problem.ExtendedProblem<Map<String, Object>> problem =
    baseProblem.withProperties(Map.of(
        "links",
        List.of(Map.of(
            "rel", documentationLink.getRel().value(),
            "href", documentationLink.getHref(),
            "type", documentationLink.getType(),
            "title", documentationLink.getTitle()
        ))
    ));
~~~

**Problem** cung cấp builder cho các trường problem tiêu chuẩn và **withProperties** để thêm extension. Lưu ý **Problem** không kế thừa **RepresentationModel** và không có collection Links để gọi **add(Link)** trực tiếp. Khi cần link trong body, hãy dùng extension member có schema rõ ràng; khi cần link chuẩn ngoài body, dùng HTTP **Link** header.

Trong dự án Spring MVC mới, **ProblemDetail** của Spring Framework là lựa chọn trực tiếp để xây dựng RFC 9457 response. **Problem** của Spring HATEOAS vẫn hữu ích khi ứng dụng đang dùng abstraction này hoặc cần builder cho extension properties.

## 12. Tài liệu lỗi là một resource có thể content negotiate

Type URI không nhất thiết chỉ trả một trang HTML tĩnh. API có thể cung cấp nhiều representation cho cùng URI tài liệu:

~~~http
GET /problems/order-state-conflict
Accept: text/html
~~~

Server trả trang giải thích cho người dùng hoặc developer:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
~~~

Một công cụ tích hợp có thể yêu cầu tài liệu dạng JSON:

~~~http
GET /problems/order-state-conflict
Accept: application/json
~~~

Nếu API cung cấp representation JSON, response có thể mô tả schema, nguyên nhân và remediation metadata.

Điều quan trọng là type URI phải giữ nguyên định danh problem type. Nội dung tài liệu có thể được cải thiện hoặc mở rộng mà không thay đổi identity của lỗi.

Không bắt buộc mọi type URI phải được dereference bằng máy. RFC 9457 cho phép URI không thể truy cập, nhưng khuyến khích URI có thể phân giải để có thể bổ sung công cụ khám phá tài liệu về sau.

## 13. Nội dung tài liệu và remediation link là hai việc khác nhau

Tài liệu giải thích lỗi không nhất thiết là endpoint để sửa lỗi.

Ví dụ lỗi thiếu phương thức thanh toán:

- **describedby** trỏ tới tài liệu giải thích vì sao cần phương thức thanh toán hợp lệ.
- **payment** hoặc một extension relation có thể trỏ tới endpoint cho phép người dùng cập nhật phương thức thanh toán.
- **instance** định danh lần lỗi hiện tại.

Ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/payment-method-required",
  "title": "Payment method required",
  "status": 402,
  "detail": "Add a valid payment method before continuing.",
  "instance": "urn:uuid:7e7a8d3d-fc39-4fd2-86a4-9d5b42d4f90",
  "links": [
    {
      "rel": "describedby",
      "href": "https://api.example.com/problems/payment-method-required",
      "type": "text/html"
    },
    {
      "rel": "https://api.example.com/rels/payment-method",
      "href": "https://api.example.com/customers/7/payment-methods",
      "type": "application/hal+json"
    }
  ]
}
~~~

Relation URI **https://api.example.com/rels/payment-method** là relation mở rộng do API định nghĩa. Tài liệu cần mô tả ý nghĩa relation và cách sử dụng endpoint đích.

Không biến mọi link trong lỗi thành action có thể thực hiện. Một link tài liệu chỉ giúp hiểu vấn đề; một link remediation mới chỉ ra endpoint có thể thay đổi trạng thái. Server vẫn phải kiểm tra quyền và điều kiện nghiệp vụ khi client gọi endpoint hành động.

## 14. Giữ tài liệu ổn định khi API thay đổi

Problem type URI là một phần contract. Nếu đổi URI chỉ vì đổi tên trang hoặc cấu trúc website, client có thể không còn nhận diện được loại lỗi.

Nên tách định danh problem type khỏi đường dẫn file triển khai:

~~~text
/problem-types/order-state-conflict
/docs/problems/order-state-conflict
/static/content/errors/order-state-conflict.html
~~~

Có thể dùng redirect từ type URI đến vị trí tài liệu hiện tại, nhưng cần giữ URI định danh lâu dài và kiểm soát redirect. Tốt nhất là thiết kế type URI ngay từ đầu để có thể giữ ổn định.

Khi semantics của lỗi thay đổi đáng kể, hãy cân nhắc tạo problem type mới thay vì thay đổi ý nghĩa của URI cũ. Ví dụ, nếu **order-state-conflict** ban đầu chỉ áp dụng khi đơn đã giao nhưng sau này được dùng cho mọi xung đột dữ liệu, client có thể hiểu sai nếu vẫn dùng cùng type URI.

## 15. Localization cho trang tài liệu lỗi

Tài liệu có thể hỗ trợ nhiều ngôn ngữ. URI định danh problem type vẫn ổn định, còn server chọn ngôn ngữ dựa trên **Accept-Language**.

Ví dụ:

~~~http
GET /problems/order-state-conflict
Accept: text/html
Accept-Language: vi
~~~

Server có thể trả trang tiếng Việt:

~~~http
Content-Language: vi
Vary: Accept-Language
~~~

Nếu cùng URI phục vụ nhiều ngôn ngữ, cache cần phân biệt theo Accept-Language. Không đưa locale vào type URI chỉ để chọn bản dịch, trừ khi API thực sự định nghĩa các problem type khác nhau theo ngôn ngữ.

Trường **title** và **detail** trong Problem Details cũng có thể được quốc tế hóa. title cần giữ semantics ổn định, còn câu chữ có thể được dịch theo ngôn ngữ client yêu cầu.

## 16. Không để tài liệu lỗi tiết lộ thông tin nội bộ

Trang tài liệu lỗi là tài nguyên công khai hoặc bán công khai tùy API. Hãy chỉ đưa thông tin cần thiết để người gọi hiểu và khắc phục lỗi.

Không công bố:

- Stack trace hoặc tên class nội bộ.
- SQL, tên bảng và cấu trúc database.
- Internal hostname, private IP hoặc đường dẫn máy chủ.
- Access token, session ID hoặc credential.
- Dữ liệu cá nhân của người dùng khác.
- Thông tin bảo mật có thể giúp dò tìm hệ thống.

Trường **detail** nên hướng dẫn client khắc phục request. Thông tin chẩn đoán dành cho support nên được truy xuất bằng instance ID qua một hệ thống đã xác thực và phân quyền.

Nếu instance URI có thể truy cập, endpoint đó phải kiểm tra quyền trước khi trả dữ liệu chi tiết của lần lỗi. UUID khó đoán không thay thế authorization.

## 17. Tích hợp với ErrorResponse và ResponseEntityExceptionHandler

Spring MVC có thể trả Problem Details từ **@ExceptionHandler** hoặc **@RequestMapping**. Với lỗi framework, các exception tích hợp Spring MVC có thể triển khai **ErrorResponse**.

Nếu cần xử lý tập trung nhiều exception, có thể kế thừa **ResponseEntityExceptionHandler** trong một **@ControllerAdvice**. Tại đó, ứng dụng có thể thêm type URI hoặc header Link theo loại lỗi.

Một cách tổ chức là tạo registry cho problem metadata:

~~~java
record ProblemDocumentation(
    URI type,
    URI documentation,
    String title
) {}

final class ProblemCatalog {

    static final ProblemDocumentation ORDER_STATE_CONFLICT =
        new ProblemDocumentation(
            URI.create(
                "https://api.example.com/problems/order-state-conflict"
            ),
            URI.create(
                "https://api.example.com/problems/order-state-conflict"
            ),
            "Order state conflict"
        );

    private ProblemCatalog() {
    }
}
~~~

Handler dùng catalog để tạo body và header. Khi nhiều exception chia sẻ cùng problem type, chúng có thể dùng cùng metadata. Nếu một exception cần type URI riêng, thêm một entry mới và tài liệu tương ứng.

Cách tập trung metadata giúp tránh tình trạng body dùng type URI này trong khi Link header lại trỏ tới tài liệu khác.

## 18. Kiểm thử type URI và documentation link bằng MockMvc

Test cần kiểm tra cả Problem Details body lẫn HTTP Link header.

Ví dụ các assertion chính:

~~~java
mockMvc.perform(
        post("/orders/42/cancel")
            .accept(MediaTypes.HTTP_PROBLEM_DETAILS_JSON)
    )
    .andExpect(status().isConflict())
    .andExpect(content().contentTypeCompatibleWith(
        MediaTypes.HTTP_PROBLEM_DETAILS_JSON
    ))
    .andExpect(jsonPath("$.type")
        .value(
            "https://api.example.com/problems/order-state-conflict"
        ))
    .andExpect(jsonPath("$.title")
        .value("Order state conflict"))
    .andExpect(jsonPath("$.instance").isNotEmpty())
    .andExpect(header().string(
        HttpHeaders.LINK,
        org.hamcrest.Matchers.containsString("rel=\"describedby\"")
    ));
~~~

Có thể kiểm tra chính xác href của documentation link:

~~~java
.andExpect(header().string(
    HttpHeaders.LINK,
    org.hamcrest.Matchers.containsString(
        "https://api.example.com/problems/order-state-conflict"
    )
));
~~~

Nếu API định nghĩa extension **links**, hãy kiểm tra cả relation và href trong body:

~~~java
.andExpect(jsonPath("$.links[0].rel").value("describedby"))
.andExpect(jsonPath("$.links[0].href")
    .value("https://api.example.com/problems/order-state-conflict"));
~~~

Nên có test riêng cho trang tài liệu:

- Type URI trả HTTP 200.
- Content-Type tương thích với text/html.
- Trang có tiêu đề và problem type chính xác.
- Nội dung mô tả cách khắc phục lỗi.
- Bản dịch có Content-Language phù hợp.
- Cache có Vary: Accept-Language khi representation thay đổi theo ngôn ngữ.

## 19. Cách client sử dụng link tài liệu lỗi

Client nên xử lý lỗi theo trình tự:

1. Đọc HTTP status để chọn nhánh xử lý tổng quát.
2. Nếu body là Problem Details, đọc type để phân loại problem type.
3. Dùng extension member hoặc HTTP Link header để tìm tài liệu liên quan.
4. Hiển thị detail như thông tin hướng dẫn cho request hiện tại.
5. Chỉ gọi remediation link khi client hiểu relation và người dùng có quyền thực hiện.
6. Ghi lại instance để hỗ trợ tra cứu khi cần.

RFC 9457 khuyến nghị client không tự động dereference type URI trong mọi tình huống. Công cụ developer, trang quản trị hoặc giao diện support có thể cung cấp nút mở tài liệu để người dùng chủ động xem hướng dẫn.

Client không nên phân tích nội dung detail để suy ra action hoặc URL. Nếu cần dữ liệu máy có thể xử lý, hãy công bố extension member hoặc typed link có schema rõ ràng.

## 20. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng instance làm link tài liệu | Mỗi lỗi bị nhầm thành một loại lỗi | Dùng type để định danh problem type |
| Dùng cùng một type cho mọi lỗi | Client không phân biệt được lỗi nghiệp vụ | Định nghĩa type URI theo problem type |
| Dùng URI tương đối không rõ base | Client phân giải ra URI khác nhau | Ưu tiên URI tuyệt đối |
| Đổi type URI khi đổi vị trí file HTML | Client mất định danh ổn định | Duy trì URI và dùng redirect có kiểm soát |
| Đưa stack trace vào detail | Lộ cấu trúc nội bộ | Chỉ trả hướng dẫn an toàn cho client |
| Coi links là field chuẩn của RFC 9457 | Client không biết schema extension | Công bố extension contract hoặc dùng Link header |
| Coi ProblemDetail là HAL resource | Client chờ _links nhưng không có | Dùng Problem Details và extension links đúng cách |
| Tự động tải mọi type URI | Có thể tạo request không cần thiết | Chỉ mở tài liệu trong ngữ cảnh developer/support |
| Dùng describedby cho action cập nhật | Client hiểu sai mục đích link | Dùng relation mô tả action riêng |
| Công bố remediation link nhưng không kiểm tra quyền | Có thể lộ hoặc gọi thao tác trái phép | Kiểm tra authorization tại endpoint đích |

## 21. Quy trình thiết kế link đến tài liệu lỗi

Khi xây dựng error representation cho Spring HATEOAS, hãy thực hiện theo trình tự:

1. Xác định problem type riêng cho từng lỗi nghiệp vụ cần phân biệt.
2. Chọn type URI tuyệt đối và giữ ổn định.
3. Xuất bản tài liệu HTML giải thích nguyên nhân và cách khắc phục tại type URI.
4. Dùng ProblemDetail hoặc Problem để tạo response theo Problem Details.
5. Đặt type URI vào trường type và instance URI riêng cho lần lỗi cụ thể.
6. Công bố tài liệu bằng Link header với relation describedby.
7. Nếu cần link trong JSON body, định nghĩa extension member và schema của nó.
8. Dùng relation riêng cho remediation action, không nhầm với link tài liệu.
9. Kiểm tra bảo mật, quyền truy cập và thông tin được công bố.
10. Kiểm thử body, type URI, Link header, docs endpoint và localization.
11. Giữ type URI tương thích khi website hoặc cấu trúc tài liệu thay đổi.

Link đến tài liệu lỗi giúp response HTTP trở nên dễ hiểu và có thể khám phá hơn. RFC 9457 cung cấp type URI để định danh problem type; RFC 8288 cung cấp relation describedby để công bố liên kết mô tả; Spring MVC và Spring HATEOAS cung cấp các abstraction để tạo Problem Details và link có cấu trúc. Khi type URI ổn định, tài liệu rõ ràng và link được công bố đúng semantics, client có thể xử lý lỗi nhất quán qua nhiều phiên bản API.

## Tài liệu tham khảo

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [IANA — Link Relation Types](https://www.iana.org/assignments/link-relations/)
- [Spring Framework — Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring HATEOAS API — Problem](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/problem/Problem.html)
- [Spring HATEOAS API — Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS API — IanaLinkRelations](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS API — MediaTypes](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/MediaTypes.html)
