# Link trong error response

## Mục tiêu

Một REST API có thể trả lỗi khi request không hợp lệ, tài nguyên không còn tồn tại, thao tác xung đột với trạng thái hiện tại hoặc người dùng chưa đáp ứng điều kiện nghiệp vụ. Error response tốt cần giúp client hiểu loại vấn đề, nhận diện lần xảy ra cụ thể và biết bước tiếp theo có thể thực hiện.

Spring HATEOAS có thể giúp server công bố các URI khôi phục như trang hướng dẫn, danh sách phương thức thanh toán hoặc tài nguyên cần cập nhật. Tuy nhiên, error representation thường dùng Problem Details theo RFC 9457, không phải HAL. Vì vậy, cần chọn cách đưa links vào response sao cho client hiểu được và media type vẫn đúng với hợp đồng lỗi.

Sau bài học, bạn có thể:

- Phân biệt Problem Details với HAL error representation.
- Hiểu vai trò của các trường type, title, status, detail và instance.
- Thêm các URI khôi phục vào extension member của Problem Details.
- Tạo URI bằng WebMvcLinkBuilder trong @ControllerAdvice.
- Dùng HTTP Link header cho quan hệ liên kết chuẩn.
- Chọn giữa ProblemDetail của Spring Framework và Problem của Spring HATEOAS.
- Xử lý lỗi từ Spring Security và kiểm thử error links bằng MockMvc.

## Error response có thể giúp client làm gì?

HTTP status cho biết kết quả ở mức giao thức, ví dụ 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict hoặc 422 Unprocessable Content. Body có thể cung cấp thêm thông tin máy đọc được để client sửa request hoặc điều hướng tới bước khắc phục.

Ví dụ, khi thanh toán bị từ chối vì phương thức thanh toán hết hạn, client có thể cần:

- Mã loại lỗi ổn định để phân biệt với lỗi thanh toán khác.
- Thông báo ngắn gọn cho người dùng.
- URI của lần xảy ra lỗi để hỗ trợ hoặc tra cứu.
- Link tới trang hướng dẫn xử lý.
- Link tới danh sách phương thức thanh toán để người dùng chọn phương thức khác.

Một response có thể trông như sau:

~~~http
HTTP/1.1 402 Payment Required
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/payment-declined",
  "title": "Payment was declined",
  "status": 402,
  "detail": "Choose another payment method and submit the payment again.",
  "instance": "https://api.example.com/problem-occurrences/7f8c2d",
  "links": [
    {
      "rel": "help",
      "href": "https://docs.example.com/payments/declined"
    },
    {
      "rel": "payment-methods",
      "href": "https://api.example.com/api/payment-methods"
    }
  ]
}
~~~

Trong ví dụ này, links là extension member do API định nghĩa. Nó giúp client biết các URI liên quan đến cách khắc phục lỗi. Client chỉ nên xử lý những relation mà nó hiểu; các extension member không nhận diện được phải được bỏ qua để API có thể mở rộng trong tương lai.

## Phân biệt các trường của Problem Details

RFC 9457 định nghĩa các trường chuẩn sau:

| Trường | Ý nghĩa | Vai trò đối với điều hướng |
|---|---|---|
| type | URI định danh loại vấn đề. | Có thể trỏ tới tài liệu mô tả loại lỗi. |
| title | Tóm tắt ngắn gọn loại vấn đề. | Dành cho người đọc; không nên dùng làm mã lỗi để so sánh. |
| status | HTTP status của lần xảy ra lỗi. | Phải khớp với status thực tế trong HTTP response. |
| detail | Giải thích cụ thể cho lần xảy ra lỗi. | Nên hướng dẫn cách sửa request, không chứa thông tin debug nội bộ. |
| instance | URI định danh lần xảy ra lỗi cụ thể. | Có thể dùng để tra cứu hoặc gửi cho bộ phận hỗ trợ. |
| Extension members | Dữ liệu bổ sung do problem type định nghĩa. | Có thể chứa links, errors, balance hoặc dữ liệu nghiệp vụ phù hợp. |

Không nhầm type, instance và link khôi phục:

- type định danh loại lỗi, ví dụ payment-declined. Nếu URI này truy cập được, nó nên cung cấp tài liệu mô tả loại lỗi.
- instance định danh một lần xảy ra lỗi cụ thể. Nó có thể là URI truy cập được hoặc chỉ là định danh opaque.
- links công bố những tài nguyên hoặc bước tiếp theo mà client có thể sử dụng.

Đừng dùng detail làm nơi nhúng URL để client phải phân tích chuỗi. Đặt URI trong extension member có cấu trúc rõ ràng để client không phụ thuộc vào ngôn ngữ hoặc cách viết thông báo.

## Problem Details không tự có _links của HAL

HAL có cấu trúc liên kết riêng, thường đặt links trong _links. Problem Details có media type application/problem+json và bộ trường chuẩn riêng. RFC 9457 không định nghĩa một trường _links hoặc một cấu trúc links chuẩn.

Vì vậy, khi API dùng Problem Details, có hai cách thường gặp:

1. Định nghĩa extension member như links chứa các object có rel và href. Cấu trúc này thuộc hợp đồng của API.
2. Gửi các quan hệ liên kết qua HTTP Link header theo RFC 8288. Cách này hữu ích cho những link có semantics chuẩn và không cần thêm cấu trúc vào body.

Ví dụ header:

~~~http
Link: <https://docs.example.com/payments/declined>; rel="help"
Link: </api/payment-methods>; rel="payment-methods"
~~~

Hai cách có thể được dùng cùng nhau nếu client cần cả extension data lẫn header link. Không nên serialize một EntityModel<ProblemDetail> thành HAL rồi đặt Content-Type là application/problem+json; body HAL không còn tuân theo cấu trúc Problem Details.

Nếu muốn error body thực sự dùng _links, hãy chọn một media type hypermedia như HAL và thiết kế error representation theo media type đó. Khi cần tương thích với client hiểu RFC 9457, giữ Problem Details và định nghĩa extension member có tài liệu.

## Tạo link khôi phục bằng WebMvcLinkBuilder

Spring HATEOAS có thể tạo URI cho link lỗi dựa trên mapping của controller. Ví dụ, link help trỏ tới tài liệu trong API, còn payment-methods trỏ tới collection phương thức thanh toán:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Link help = linkTo(methodOn(HelpController.class)
        .paymentDeclined())
        .withRel(IanaLinkRelations.HELP);

Link paymentMethods = linkTo(methodOn(PaymentMethodController.class)
        .findAll())
        .withRel(LinkRelation.of("payment-methods"));
~~~

methodOn(...) tạo proxy để Spring HATEOAS đọc mapping của method, không gọi controller method thật. linkTo(...) tạo URI từ mapping và request context hiện tại. Relation help dùng quan hệ chuẩn; payment-methods là relation nghiệp vụ riêng của API.

Nếu link hướng tới một URI bên ngoài như trang tài liệu được host ở hệ thống khác, có thể tạo bằng Link.of(...) với URI công khai đã cấu hình. Không ghép URL nội bộ hoặc hostname của service vào error body.

## Thêm links vào ProblemDetail của Spring Framework

Spring Framework cung cấp ProblemDetail cho RFC 9457. ProblemDetail có các trường chuẩn và map properties để thêm extension members. Với Jackson, Spring đăng ký mixin để các property bổ sung được serialize thành thuộc tính cấp cao nhất của JSON.

Ví dụ @RestControllerAdvice xử lý một lỗi thanh toán:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestControllerAdvice
class PaymentExceptionHandler {

    @ExceptionHandler(PaymentDeclinedException.class)
    ResponseEntity<ProblemDetail> handlePaymentDeclined(
            PaymentDeclinedException exception) {

        Link help = linkTo(methodOn(HelpController.class)
                .paymentDeclined())
                .withRel(IanaLinkRelations.HELP);

        Link paymentMethods = linkTo(methodOn(PaymentMethodController.class)
                .findAll())
                .withRel(LinkRelation.of("payment-methods"));

        List<Map<String, String>> links = List.of(
                Map.of(
                        "rel", "help",
                        "href", help.getHref()),
                Map.of(
                        "rel", "payment-methods",
                        "href", paymentMethods.getHref()));

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.PAYMENT_REQUIRED,
                "Choose another payment method and submit the payment again.");

        problem.setType(URI.create(
                "https://api.example.com/problems/payment-declined"));
        problem.setTitle("Payment was declined");
        problem.setInstance(URI.create(
                "https://api.example.com/problem-occurrences/"
                        + exception.getOccurrenceId()));
        problem.setProperty("links", links);

        return ResponseEntity.status(HttpStatus.PAYMENT_REQUIRED)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
~~~

Ví dụ giả định PaymentDeclinedException có getOccurrenceId() và các controller đích có method tương ứng. ProblemDetail.setProperty("links", links) thêm extension member links; mỗi phần tử chứa relation và href. Client có thể tìm relation payment-methods để chuyển người dùng tới collection.

Status trong ProblemDetail và HTTP response phải giống nhau. Ở đây cả hai đều là 402. Nếu trả ProblemDetail trực tiếp từ một @ExceptionHandler, Spring MVC cũng có thể dùng trường status của nó để tạo response. Dùng ResponseEntity khi muốn đặt thêm header hoặc kiểm soát status rõ ràng.

## Dùng Problem type của Spring HATEOAS

Spring HATEOAS cũng cung cấp Problem trong package org.springframework.hateoas.mediatype.problem. Đây là kiểu miền dữ liệu cho Problem Details, có các phương thức tạo type, title, status, detail, instance và withProperties(...).

Ví dụ tạo problem với extension links:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.hateoas.mediatype.problem.Problem;
import org.springframework.http.HttpStatus;

Problem problem = Problem.create()
        .withType(URI.create(
                "https://api.example.com/problems/payment-declined"))
        .withTitle("Payment was declined")
        .withStatus(HttpStatus.PAYMENT_REQUIRED)
        .withDetail("Choose another payment method and submit the payment again.")
        .withInstance(URI.create(
                "https://api.example.com/problem-occurrences/7f8c2d"))
        .withProperties(Map.of(
                "links",
                List.of(
                        Map.of(
                                "rel", "help",
                                "href", "https://docs.example.com/payments/declined"),
                        Map.of(
                                "rel", "payment-methods",
                                "href", "/api/payment-methods"))));
~~~

Khi dùng kiểu Problem của Spring HATEOAS, cấu hình media type HTTP Problem Details tương ứng bằng @EnableHypermediaSupport(type = HypermediaType.HTTP_PROBLEM_DETAILS) nếu ứng dụng cần đăng ký hỗ trợ này một cách tường minh:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HTTP_PROBLEM_DETAILS)
class ProblemDetailsConfiguration {
}
~~~

Problem không phải RepresentationModel và không tự chuyển extension member thành HAL _links. Các URI được thêm qua withProperties(...) vẫn là extension data theo hợp đồng Problem Details. Nếu ứng dụng đã cấu hình một hypermedia type khác, hãy kiểm tra cách đăng ký media type của ứng dụng trước khi thêm một cấu hình @EnableHypermediaSupport riêng.

@EnableHypermediaSupport nhận một hypermedia type cho mỗi cấu hình. Nếu ứng dụng đang dùng HAL cho response thành công và cần Problem Details cho lỗi, đừng giả định một annotation đơn lẻ sẽ tự bật đồng thời cả hai định dạng. Với Spring MVC, có thể tiếp tục dùng ProblemDetail và setProperty(...) như ví dụ trước; cách này không yêu cầu thay media type hypermedia chính của ứng dụng.

## Spring MVC và xử lý lỗi tập trung

Spring Framework hỗ trợ các abstraction sau:

| Abstraction | Vai trò |
|---|---|
| ProblemDetail | Body theo RFC 9457, có các trường chuẩn và extension properties. |
| ErrorResponse | Hợp đồng cung cấp HTTP status, headers và ProblemDetail body cho lỗi. |
| ErrorResponseException | Base class tiện lợi cho exception mang thông tin HTTP error response. |
| ResponseEntityExceptionHandler | Base class cho @ControllerAdvice, xử lý nhiều exception MVC tích hợp sẵn. |

Có thể mở rộng ResponseEntityExceptionHandler để chuẩn hóa các lỗi từ Spring MVC và thêm handler riêng cho exception nghiệp vụ. Trong Spring Boot, thuộc tính spring.mvc.problemdetails.enabled=true bật auto-configuration cho Problem Details của các exception MVC tích hợp sẵn.

Nếu cần tùy chỉnh một exception tích hợp sẵn khi Boot đã cấu hình handler, cần đảm bảo @ControllerAdvice tùy chỉnh được ưu tiên xử lý trước handler auto-configured. Đừng tạo hai handler cùng bắt một exception mà không kiểm soát thứ tự.

Các lỗi xác thực từ Spring Security có thể bị xử lý trong security filter chain trước khi request tới controller. @ControllerAdvice không nhất thiết bắt được chúng. Với lỗi 401 và 403 phát sinh từ Spring Security, cấu hình AuthenticationEntryPoint và AccessDeniedHandler để tạo Problem Details và các links phù hợp.

## Link header trong error response

HTTP Link header theo RFC 8288 có thể công bố một hoặc nhiều quan hệ liên kết mà không thay đổi cấu trúc body Problem Details:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Link: </docs/orders/conflict>; rel="help"
Link: </api/orders/order-42>; rel="current"
~~~

Header link hữu ích khi client đã hỗ trợ Web Linking và cần một relation chuẩn hoặc URI tham chiếu mà không cần đọc extension member trong JSON. Body extension phù hợp hơn khi ứng dụng cần định nghĩa một cấu trúc riêng gồm nhiều trường cho mỗi link, ví dụ rel, href, title hoặc type.

Trong controller, có thể thêm giá trị Link header vào ResponseEntity bằng HttpHeaders.LINK. Giá trị header tuân theo cú pháp RFC 8288, gồm URI tham chiếu trong dấu ngoặc nhọn và thuộc tính rel. Khi có nhiều link, gửi nhiều giá trị Link header thay vì nối chúng thành một chuỗi tùy ý.

Không phải mọi link đều nên xuất hiện trong error response. Chỉ công bố link có ích cho bước sửa lỗi, như help, payment methods hoặc current representation. Nếu tài nguyên đích yêu cầu quyền, endpoint đó vẫn phải thực hiện authentication và authorization như bình thường.

## Chọn relation và thiết kế đường khôi phục

Relation phải mô tả ý nghĩa của link, không phải tên class hoặc method Java. Có thể dùng relation chuẩn như help khi semantics phù hợp và relation tùy chỉnh như payment-methods cho nghiệp vụ riêng.

Ví dụ:

| Loại lỗi | Link có ích | Mục đích |
|---|---|---|
| Thanh toán bị từ chối | help, payment-methods | Đọc hướng dẫn hoặc chọn phương thức khác. |
| Dữ liệu xung đột | current, help | Tải representation hiện tại và xem cách xử lý xung đột. |
| Validation thất bại | help, profile | Xem quy tắc trường hoặc hợp đồng dữ liệu. |
| Phiên đăng nhập hết hạn | login hoặc relation đăng nhập do API định nghĩa | Bắt đầu lại quy trình xác thực. |
| Giới hạn tốc độ | help, status | Xem chính sách giới hạn hoặc tình trạng dịch vụ. |

Với lỗi validation, nên cung cấp extension errors chứa mã lỗi và JSON Pointer tới vị trí trong request body. Link help có thể dẫn tới tài liệu về schema hoặc quy tắc validation. Không yêu cầu client phân tích câu detail để tìm tên trường.

Link retry chỉ nên xuất hiện khi thao tác có thể thử lại an toàn. Với request không idempotent, client cần biết quy tắc idempotency hoặc dùng idempotency key trước khi retry. Đừng công bố link retry chung cho mọi lỗi 5xx nếu thao tác có thể tạo giao dịch trùng lặp.

## Bảo mật và nội dung error response

Error response là dữ liệu công khai của API. Không đưa stack trace, SQL query, tên bảng, đường dẫn file nội bộ, access token, secret, thông tin cá nhân không cần thiết hoặc nội dung exception thô vào detail hay extension members.

Khi tạo links, lưu ý:

- Không công bố URI của tài nguyên mà người gọi không được phép biết.
- Không đưa token hoặc dữ liệu nhạy cảm vào query string.
- Không dùng link ẩn như cơ chế bảo mật; endpoint đích vẫn phải kiểm tra quyền.
- Không tạo link dựa trên Host hoặc forwarded headers không đáng tin cậy.
- Không để instance tiết lộ ID tuần tự hoặc thông tin nội bộ nếu không cần thiết.
- Chỉ dùng link tới hệ thống ngoài khi đó là đích được kiểm soát và có chủ đích.

type URI có thể dẫn tới tài liệu công khai mô tả problem type. instance nên là định danh duy nhất cho occurrence và có thể liên kết với correlation ID trong log nội bộ. Không trả correlation ID nhạy cảm hoặc dữ liệu log trực tiếp cho client.

## Kiểm thử error links bằng MockMvc

Kiểm thử response status, media type và extension links:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@Test
void paymentDeclinedResponseContainsRecoveryLinks() throws Exception {
    mockMvc.perform(post("/api/payments")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "orderId": "order-42",
                              "paymentMethodId": "expired-card"
                            }
                            """))
            .andExpect(status().isPaymentRequired())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.type").value(
                    "https://api.example.com/problems/payment-declined"))
            .andExpect(jsonPath("$.status").value(402))
            .andExpect(jsonPath("$.links[0].rel").value("help"))
            .andExpect(jsonPath("$.links[0].href").exists())
            .andExpect(jsonPath("$.links[1].rel").value("payment-methods"))
            .andExpect(jsonPath("$.links[1].href").exists());
}
~~~

Test giả định endpoint và service được cấu hình để ném PaymentDeclinedException. Nếu link được tạo bằng WebMvcLinkBuilder, kiểm tra href theo path của mapping và tránh so sánh hostname/port tuyệt đối nếu chúng thay đổi trong test environment.

Nếu API gửi Link header, kiểm thử header riêng:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;

// requestBody là JSON đầu vào được chuẩn bị trong test fixture.
mockMvc.perform(post("/api/payments")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody))
        .andExpect(status().isPaymentRequired())
        .andExpect(header().string(
                HttpHeaders.LINK,
                containsString("rel=\"help\"")));
~~~

Với @ControllerAdvice, nên kiểm thử:

- Exception nghiệp vụ được ánh xạ tới đúng HTTP status.
- Content-Type là application/problem+json.
- status trong body khớp status HTTP.
- type ổn định và instance định danh đúng occurrence.
- Extension links chứa relation và href mong muốn.
- Link được tạo từ controller mapping và đúng context path.
- Error response không để lộ exception message hoặc dữ liệu nhạy cảm.

Với lỗi 401/403 từ Spring Security, dùng MockMvc có security filter chain và kiểm thử AuthenticationEntryPoint/AccessDeniedHandler. Đừng chỉ kiểm thử @ControllerAdvice rồi kết luận mọi lỗi bảo mật đều được xử lý.

## Những lỗi thường gặp

- **Coi Problem Details là HAL:** application/problem+json không tự có _links; dùng extension member hoặc Link header.
- **Đặt URL trong detail:** client không nên phân tích văn bản; dùng links có cấu trúc.
- **Nhầm type với link khôi phục:** type định danh loại lỗi, thường trỏ tới tài liệu mô tả problem type.
- **Dùng instance làm link hành động:** instance định danh lần xảy ra lỗi, không phải endpoint để client thực hiện thao tác.
- **Không đồng bộ status:** trường status trong body phải khớp HTTP status thực tế.
- **Trả HAL body với Content-Type Problem Details:** media type và cấu trúc JSON phải thống nhất.
- **Dùng VndErrors cho dự án mới:** kiểu này đã deprecated; dùng Problem Details hoặc Problem của Spring HATEOAS.
- **Cho rằng ControllerAdvice xử lý mọi lỗi:** lỗi từ Spring Security filter chain cần entry point và access denied handler riêng.
- **Công bố link tới tài nguyên bị cấm:** chỉ công bố link có thể sử dụng trong ngữ cảnh hiện tại; endpoint vẫn phải kiểm tra quyền.
- **Công bố retry không an toàn:** cân nhắc idempotency và khả năng tạo tác dụng phụ trước khi đưa link retry.
- **Đưa stack trace vào detail:** chỉ cung cấp thông tin giúp client sửa request; giữ dữ liệu debug trong log nội bộ.

## Quy trình thiết kế error links

1. Chọn HTTP status đúng với semantics của lỗi.
2. Định nghĩa problem type URI ổn định và nội dung title/detail có thể hiển thị an toàn.
3. Tạo instance để nhận diện occurrence cụ thể.
4. Xác định những relation và URI thật sự giúp client khắc phục lỗi.
5. Tạo URI bằng WebMvcLinkBuilder hoặc nguồn cấu hình công khai đáng tin cậy.
6. Thêm links vào extension member của Problem Details hoặc HTTP Link header.
7. Bảo đảm media type, status body và status HTTP nhất quán.
8. Kiểm tra quyền trên tài nguyên đích và loại bỏ thông tin nhạy cảm.
9. Kiểm thử cả error body, link headers và lỗi do security filter chain tạo ra.

Link trong error response giúp client hiểu bước tiếp theo sau khi request thất bại. Khi dùng Problem Details làm định dạng lỗi, hãy giữ nguyên semantics RFC 9457 và công bố links qua extension member có cấu trúc hoặc HTTP Link header. Spring HATEOAS hỗ trợ tạo URI theo mapping để các đường khôi phục luôn khớp với API, còn Spring MVC cung cấp ProblemDetail và ResponseEntityExceptionHandler để chuẩn hóa nội dung lỗi.

## Tài liệu tham khảo

- Spring HATEOAS Reference Documentation, HTTP Problem Details: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.problem
- Spring HATEOAS API, Problem: https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/problem/Problem.html
- Spring Framework Reference Documentation, Error Responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework API, ProblemDetail: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html
- RFC 9457, Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 8288, Web Linking: https://www.rfc-editor.org/rfc/rfc8288
