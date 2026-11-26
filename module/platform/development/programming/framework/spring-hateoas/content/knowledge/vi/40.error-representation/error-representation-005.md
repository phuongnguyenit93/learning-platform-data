# Link hỗ trợ

Khi một REST API trả về lỗi, mã trạng thái HTTP cho biết kết quả tổng quát nhưng chưa chắc giúp client biết phải làm gì tiếp theo. Ví dụ, lỗi thanh toán có thể xảy ra vì số dư không đủ, thông tin thẻ không hợp lệ hoặc tài khoản cần xác minh. Một đường dẫn hỗ trợ phù hợp giúp client hoặc người dùng tìm đúng tài liệu hướng dẫn, trang trợ giúp hay kênh xử lý sự cố.

Trong hypermedia, đường dẫn đó được công bố bằng link relation. Relation chuẩn IANA là help, được Spring HATEOAS cung cấp qua IanaLinkRelations.HELP. Với response Problem Details dùng media type application/problem+json, cách phù hợp là gửi link hỗ trợ trong HTTP Link header. Nếu API dùng một error representation dựa trên HAL, có thể thêm link help trực tiếp vào RepresentationModel.

Bài học này trình bày cách chọn và công bố link hỗ trợ trong error response, cách kết hợp Spring HATEOAS với Problem Details, và cách kiểm thử để client có thể khám phá hướng dẫn mà không phải phân tích thông điệp lỗi.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vai trò của link hỗ trợ trong error representation.
- Sử dụng relation help từ IanaLinkRelations.HELP.
- Phân biệt link hỗ trợ với problem type URI và problem instance URI.
- Công bố link hỗ trợ trong HTTP Link header cùng Problem Details.
- Thêm link hỗ trợ vào error representation dựa trên HAL.
- Tạo response lỗi tập trung bằng @RestControllerAdvice.
- Kiểm thử HTTP status, media type, Problem Details và link hỗ trợ.
- Tránh rò rỉ thông tin nội bộ qua error body và support link.
- Nhận diện API cũ VndErrors và relation REL_HELP đã deprecated.

## Vì sao error response cần link hỗ trợ?

Giả sử client gửi yêu cầu thanh toán nhưng server từ chối vì tài khoản không đủ số dư. Một response chỉ có status 403 Forbidden cho biết server từ chối request, nhưng chưa cung cấp nơi tìm hiểu cách khắc phục.

Problem Details có thể mô tả lỗi bằng dữ liệu có cấu trúc:

```json
{
  "type": "https://api.example.com/problems/out-of-credit",
  "title": "Không đủ số dư",
  "status": 403,
  "detail": "Số dư hiện tại không đủ để hoàn tất thanh toán.",
  "instance": "https://api.example.com/problem-occurrences/8a9c2d"
}
```

Server có thể công bố thêm một link help trỏ tới trang hướng dẫn xử lý lỗi này. Client có thể tìm link theo relation help, hiển thị liên kết cho người dùng hoặc ghi lại link trong log hỗ trợ.

Link hỗ trợ hữu ích khi:

- Người dùng cần hướng dẫn giải quyết lỗi theo từng loại nghiệp vụ.
- Client cần chỉ ra nơi xem tài liệu, FAQ hoặc chính sách liên quan.
- Bộ phận hỗ trợ cần một URI ổn định để yêu cầu người dùng tham khảo.
- Lỗi có nhiều cách xử lý và thông điệp ngắn trong response không đủ giải thích.

Không nên bắt client phân tích chuỗi detail để suy ra URL hoặc hành động. Nội dung detail dành cho giải thích con người; link relation mới là metadata điều hướng có cấu trúc.

## Relation help trong Spring HATEOAS

IANA định nghĩa relation help để chỉ tới tài nguyên cung cấp trợ giúp theo ngữ cảnh của resource hiện tại. Spring HATEOAS cung cấp hằng:

```java
import org.springframework.hateoas.IanaLinkRelations;
```

Có thể tạo link hỗ trợ bằng Link.of():

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link help = Link.of(
    "https://support.example.com/payments/out-of-credit",
    IanaLinkRelations.HELP
);
```

Link này có hai thành phần:

- URI đích: trang hỗ trợ cho lỗi thanh toán không đủ số dư.
- Relation help: cho biết đích là tài liệu trợ giúp gắn với ngữ cảnh hiện tại.

Relation mô tả ý nghĩa của link. Client có thể tìm link theo relation mà không cần biết URL được tổ chức theo path nào.

Nếu cần metadata hiển thị cho người dùng, có thể thêm tiêu đề và media type:

```java
Link help = Link.of(
        "https://support.example.com/payments/out-of-credit",
        IanaLinkRelations.HELP)
    .withTitle("Cách xử lý lỗi không đủ số dư")
    .withType("text/html");
```

Link là value object bất biến. Các phương thức withTitle() và withType() trả về một instance mới; hãy giữ giá trị trả về như ví dụ.

## Phân biệt help link, problem type và problem instance

Problem Details theo RFC 9457 có các thành viên chuẩn với mục đích khác nhau:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| type | Định danh loại vấn đề; URI có thể trỏ tới tài liệu mô tả loại lỗi | https://api.example.com/problems/out-of-credit |
| title | Tên ngắn gọn của loại vấn đề | Không đủ số dư |
| detail | Giải thích cụ thể cho lần lỗi này | Số dư hiện tại không đủ để hoàn tất thanh toán. |
| instance | Định danh lần xuất hiện cụ thể của lỗi | https://api.example.com/problem-occurrences/8a9c2d |
| Link relation help | Điều hướng tới tài nguyên trợ giúp theo ngữ cảnh | https://support.example.com/payments/out-of-credit |

type và help có thể cùng dẫn tới tài liệu, nhưng chúng không nhất thiết là một URI:

- type là định danh chính của problem type. Nếu là URI có thể truy cập, RFC 9457 khuyến nghị URI đó cung cấp tài liệu dễ đọc về loại lỗi.
- help là quan hệ điều hướng tới nguồn trợ giúp có liên quan tới response hiện tại. Đích có thể là hướng dẫn khắc phục, trang hỗ trợ hoặc tài liệu vận hành.
- instance định danh một lần xảy ra lỗi. Nó không mặc nhiên là trang trợ giúp hoặc endpoint để tạo ticket.

Giữ các vai trò này riêng biệt giúp client không phải đoán ý nghĩa của URI từ cấu trúc path.

RFC 9457 khuyến nghị dùng URI tuyệt đối cho type và instance khi có thể. URI instance có thể không dereference được và vẫn chỉ đóng vai trò mã định danh lần xuất hiện; nếu có thể truy cập, server có thể cung cấp thêm thông tin sự cố theo chính sách bảo mật.

## Vì sao dùng HTTP Link header với Problem Details?

Spring HATEOAS cung cấp kiểu Problem trong package org.springframework.hateoas.mediatype.problem. Kiểu này biểu diễn các thuộc tính Problem Details và hỗ trợ thêm extension properties. Tuy nhiên, Problem không kế thừa RepresentationModel và không có API add(Link) như EntityModel hoặc model HAL.

Javadoc của kiểu Problem trong Spring HATEOAS 3.1.2 vẫn mô tả mô hình RFC 7807. RFC 9457 đã thay thế RFC 7807; các thành viên cốt lõi được dùng trong bài này vẫn tương thích với định dạng Problem Details hiện hành. Khi thiết kế API mới, hãy dùng RFC 9457 làm chuẩn giao tiếp.

Vì vậy, khi response dùng application/problem+json, hãy giữ body theo cấu trúc Problem Details và công bố link hỗ trợ qua HTTP Link header theo RFC 8288:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Link: <https://support.example.com/payments/out-of-credit>; rel="help"; type="text/html"

{
  "type": "https://api.example.com/problems/out-of-credit",
  "title": "Không đủ số dư",
  "status": 403,
  "detail": "Số dư hiện tại không đủ để hoàn tất thanh toán.",
  "instance": "https://api.example.com/problem-occurrences/8a9c2d"
}
```

HTTP Link header có thể đi cùng nhiều loại response body. Client không cần biết body là Problem Details, JSON thông thường hay một định dạng khác để nhận diện relation help.

Đây cũng là cách giữ ranh giới rõ ràng:

- Body Problem Details mô tả vấn đề.
- HTTP Link header cung cấp liên kết hypermedia theo chuẩn Web Linking.
- Content-Type xác định định dạng của body.
- HTTP status mô tả kết quả của request.

## Xây dựng Problem Details và help header

Ví dụ sau dùng Spring HATEOAS Problem để tạo body và dùng Link cùng IanaLinkRelations.HELP để mô tả đích hỗ trợ. Header được serialize theo cú pháp RFC 8288:

```java
import java.net.URI;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.mediatype.problem.Problem;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

class PaymentErrorResponses {

    ResponseEntity<Problem> outOfCredit(String occurrenceId) {

        Problem problem = Problem.create()
            .withType(URI.create(
                "https://api.example.com/problems/out-of-credit"))
            .withTitle("Không đủ số dư")
            .withStatus(HttpStatus.FORBIDDEN)
            .withDetail(
                "Số dư hiện tại không đủ để hoàn tất thanh toán.")
            .withInstance(URI.create(
                "https://api.example.com/problem-occurrences/" + occurrenceId));

        Link help = Link.of(
            "https://support.example.com/payments/out-of-credit",
            IanaLinkRelations.HELP);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaTypes.HTTP_PROBLEM_DETAILS_JSON);
        headers.add(
            HttpHeaders.LINK,
            "<" + help.getHref() + ">; rel=\""
                + help.getRel().value() + "\"");

        return ResponseEntity.status(HttpStatus.FORBIDDEN)
            .headers(headers)
            .body(problem);
    }
}
```

Đoạn code sử dụng Link để giữ relation và URI trong mô hình Spring HATEOAS. Khi ghi vào HTTP header, nó tạo chuỗi Link theo cú pháp RFC 8288 bằng getHref() và getRel().value().

Nếu muốn bổ sung title hoặc type cho header link, có thể thêm các tham số tương ứng:

```http
Link: <https://support.example.com/payments/out-of-credit>; rel="help"; type="text/html"; title="Cách xử lý lỗi không đủ số dư"
```

Khi tự tạo giá trị header, cần bảo đảm URI và các tham số được escape đúng cú pháp HTTP. Nếu tiêu đề có dấu ngoặc kép hoặc ký tự đặc biệt, hãy escape chúng hoặc bỏ tham số title và để tài liệu đích cung cấp tiêu đề.

### Dùng MediaTypes của Spring HATEOAS

Spring HATEOAS cung cấp hằng media type cho Problem Details:

```java
import org.springframework.hateoas.MediaTypes;

headers.setContentType(MediaTypes.HTTP_PROBLEM_DETAILS_JSON);
```

Dùng hằng này giúp tránh lặp chuỗi application/problem+json trong nhiều controller. Nếu response được tạo bởi Spring Framework ProblemDetail, vẫn có thể dùng cùng media type và HTTP Link header.

## Tạo error response tập trung bằng ControllerAdvice

Trong ứng dụng thực tế, không nên tự tạo Problem Details và help link lặp lại trong từng controller. Có thể tập trung ánh xạ exception sang error response trong @RestControllerAdvice:

```java
import java.net.URI;
import java.util.UUID;

import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.mediatype.problem.Problem;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(InsufficientBalanceException.class)
    ResponseEntity<Problem> handleInsufficientBalance(
            InsufficientBalanceException exception) {

        String occurrenceId = UUID.randomUUID().toString();

        Problem problem = Problem.create()
            .withType(URI.create(
                "https://api.example.com/problems/out-of-credit"))
            .withTitle("Không đủ số dư")
            .withStatus(HttpStatus.FORBIDDEN)
            .withDetail(
                "Hãy kiểm tra số dư hoặc chọn phương thức thanh toán khác.")
            .withInstance(URI.create(
                "https://api.example.com/problem-occurrences/" + occurrenceId));

        Link help = Link.of(
            "https://support.example.com/payments/out-of-credit",
            IanaLinkRelations.HELP);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaTypes.HTTP_PROBLEM_DETAILS_JSON);
        headers.add(
            HttpHeaders.LINK,
            "<" + help.getHref() + ">; rel=\""
                + help.getRel().value() + "\"");

        return ResponseEntity.status(HttpStatus.FORBIDDEN)
            .headers(headers)
            .body(problem);
    }
}
```

Ví dụ giả định InsufficientBalanceException là exception nghiệp vụ do application service ném ra. Trong ứng dụng thật, có thể dùng một factory hoặc component chuyên tạo Problem Details để chuẩn hóa type URI, title, detail, instance và help link cho từng loại lỗi.

Không nên dùng cùng một trang hỗ trợ chung cho tất cả lỗi nếu người dùng cần hướng dẫn khác nhau. Có thể định nghĩa map từ problem type tới help URI hoặc tạo policy service để chọn link dựa trên loại exception.

## Thêm help link vào HAL error representation

Một số API muốn error response cũng là hypermedia representation theo HAL. Khi đó, có thể tạo model riêng kế thừa RepresentationModel và thêm relation help trực tiếp:

```java
import org.springframework.hateoas.RepresentationModel;

class ApiErrorModel extends RepresentationModel<ApiErrorModel> {

    private final String code;
    private final String message;

    ApiErrorModel(String code, String message) {
        this.code = code;
        this.message = message;
    }

    public String getCode() {
        return code;
    }

    public String getMessage() {
        return message;
    }
}
```

Controller có thể thêm link:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InventoryController {

    @GetMapping(
        value = "/inventory/check",
        produces = MediaTypes.HAL_JSON_VALUE)
    ResponseEntity<ApiErrorModel> checkInventory() {

        ApiErrorModel error = new ApiErrorModel(
            "INVENTORY_UNAVAILABLE",
            "Sản phẩm hiện không còn hàng.");

        error.add(Link.of(
            "https://support.example.com/inventory/unavailable",
            IanaLinkRelations.HELP));

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(error);
    }
}
```

Nếu ứng dụng trả model này dưới dạng HAL, response có thể trông như sau:

```json
{
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Sản phẩm hiện không còn hàng.",
  "_links": {
    "help": {
      "href": "https://support.example.com/inventory/unavailable"
    }
  }
}
```

Đây là một error representation riêng của ứng dụng. Content type cần là HAL, ví dụ application/hal+json, nếu client cần hiểu cấu trúc _links.

Không nên gắn _links vào body Problem Details rồi vẫn tuyên bố response tuân thủ nguyên dạng application/problem+json, trừ khi phần mở rộng đó được định nghĩa rõ trong hợp đồng problem type. Nếu cần giữ Problem Details chuẩn, ưu tiên HTTP Link header cho relation help.

## VndErrors và REL_HELP trong API cũ

Các phiên bản Spring HATEOAS cũ có VndErrors và VndErrors.VndError cho media type application/vnd.error+json. Kiểu này kế thừa RepresentationModel, vì vậy có thể gắn link relation help vào error item.

Ví dụ cũ thường dùng:

```java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.mediatype.vnderrors.VndErrors;

new VndErrors(
    "PAYMENT-42",
    "Không đủ số dư",
    Link.of(
        "https://support.example.com/payments/out-of-credit",
        IanaLinkRelations.HELP)
);
```

Tuy nhiên, VndErrors và VndErrors.VndError đã deprecated từ Spring HATEOAS 1.1. Tài liệu API khuyến nghị dùng Problem để tạo error message có tính trung lập hơn. Hằng VndErrors.REL_HELP cũng deprecated; thay bằng IanaLinkRelations.HELP.

Khi duy trì API legacy, có thể tiếp tục hỗ trợ application/vnd.error+json trong giai đoạn tương thích đã cam kết. Với API mới, nên ưu tiên Problem Details và công bố link hỗ trợ qua HTTP Link header hoặc qua HAL error representation có hợp đồng riêng.

## Thiết kế URI cho trang hỗ trợ

Một help link tốt cần ổn định và hữu ích với đúng loại lỗi:

- Dùng HTTPS và URI ổn định.
- Trỏ tới tài liệu theo problem type hoặc nhóm lỗi nghiệp vụ.
- Giải thích cách khắc phục, điều kiện cần kiểm tra và bước tiếp theo.
- Tránh URL chứa token, session ID, email, số tài khoản hoặc dữ liệu nhạy cảm.
- Nếu tài liệu có nhiều ngôn ngữ, có thể dùng content negotiation hoặc URI theo locale.
- Nếu cần người dùng liên hệ hỗ trợ, trang đích nên giải thích cách mở ticket và thông tin cần cung cấp.

Không nên đưa trực tiếp thông tin lỗi cá nhân vào URI hỗ trợ. Một help URI chung có thể được dùng bởi nhiều lần lỗi; mã tương quan riêng nên nằm trong instance hoặc một mã tham chiếu an toàn.

### Help link và support ticket

Relation help thường trỏ tới tài liệu hoặc trang trợ giúp. Nếu hệ thống cần tạo một yêu cầu hỗ trợ mới, đó là một thao tác khác:

- Link help dẫn tới hướng dẫn hoặc trung tâm hỗ trợ.
- Link create-form có thể dẫn tới form để tạo yêu cầu hỗ trợ nếu API cung cấp form theo semantics đó.
- Một action tạo ticket có thể được mô tả bằng affordance trong media type hỗ trợ affordance.

Không nên dùng help như một cách ngầm định để gửi ticket hoặc thực hiện thao tác thay đổi trạng thái.

## Client sử dụng help link như thế nào?

Với HTTP Problem Details, client đọc response header Link và tìm link có relation help. Client không cần parse body detail để xây URL:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Link: <https://support.example.com/payments/out-of-credit>; rel="help"
```

Luồng xử lý ở client:

1. Đọc HTTP status và content type.
2. Nếu body là Problem Details, đọc type, title, detail và instance.
3. Phân tích các HTTP Link header.
4. Tìm relation help.
5. Hiển thị hoặc lưu URI trợ giúp theo chính sách của client.

Client nên tiếp tục hoạt động nếu không có link help. Không phải mọi lỗi đều có tài liệu riêng, và một số response có thể được tạo bởi proxy hoặc gateway không biết support URI của ứng dụng.

Với response HAL, client tìm relation help trong _links bằng cơ chế link discovery tương ứng với media type.

## Kiểm thử help link

Với response Problem Details, kiểm thử cần xác nhận cả body lẫn HTTP Link header:

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PaymentErrorHelpLinkTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesHelpLinkForOutOfCreditProblem() throws Exception {
        mockMvc.perform(post("/payments")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaTypes.HTTP_PROBLEM_DETAILS_JSON)
                .content("""
                    {
                      "accountId": "account-42",
                      "amount": 500
                    }
                    """))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HTTP_PROBLEM_DETAILS_JSON))
            .andExpect(jsonPath("$.type")
                .value("https://api.example.com/problems/out-of-credit"))
            .andExpect(header().string(
                "Link",
                containsString(
                    "<https://support.example.com/payments/out-of-credit>")))
            .andExpect(header().string(
                "Link",
                containsString("rel=\"help\"")));
    }
}
```

Đây là mẫu kiểm thử tích hợp. Endpoint, request body và dữ liệu tài khoản cần được điều chỉnh theo ứng dụng. Nếu có nhiều Link header, hãy kiểm tra header tương ứng thay vì giả định chỉ có một giá trị.

Với HAL error representation, kiểm thử relation trong body:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/inventory/check")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isConflict())
    .andExpect(jsonPath("$._links.help.href")
        .value("https://support.example.com/inventory/unavailable"));
```

Nên kiểm thử thêm:

- Response lỗi giữ đúng HTTP status tương ứng với tình huống nghiệp vụ.
- Content type là application/problem+json khi trả Problem Details.
- Relation help có URI tuyệt đối và dùng HTTPS.
- Link hỗ trợ trỏ tới tài liệu phù hợp với problem type.
- Response không chứa stack trace, câu lệnh SQL, secret hoặc dữ liệu cá nhân.
- Client vẫn xử lý được lỗi khi không có link help.
- Các response HAL và Problem Details không bị trộn cấu trúc hoặc media type.

## CORS và HTTP Link header

Nếu client chạy trong browser và gọi API khác origin, JavaScript có thể không đọc được header Link trừ khi server expose header đó qua CORS.

Ví dụ cấu hình Spring MVC:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .exposedHeaders("Link");
    }
}
```

exposedHeaders("Link") cho phép browser client đọc header Link sau khi CORS policy đã chấp nhận request. Nếu ứng dụng đã cấu hình CORS qua Spring Security hoặc gateway, hãy expose header tại đúng lớp đang quản lý CORS; không cần khai báo trùng lặp.

## Bảo mật của error response và help link

Error response là dữ liệu công khai gửi tới client, vì vậy cần kiểm soát nội dung:

- Không gửi stack trace, class name nội bộ, đường dẫn filesystem hoặc SQL query.
- Không đưa token, session ID, secret hoặc thông tin xác thực vào URI.
- Không đưa dữ liệu cá nhân vào detail, instance hoặc query string của help link.
- Không để help URI trở thành một endpoint vượt qua authorization.
- Không trả thông tin về resource mà caller không được phép biết.
- Dùng mã occurrence có thể tra cứu trong log nội bộ nhưng không chứa dữ liệu nhạy cảm.

Nếu support page cho phép tạo ticket hoặc xem dữ liệu tài khoản, endpoint đó vẫn phải xác thực và phân quyền riêng. Biết được help URI không đồng nghĩa có quyền truy cập nội dung nhạy cảm.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhúng link vào chuỗi detail | Client phải parse văn bản và phụ thuộc ngôn ngữ | Dùng relation help trong HTTP Link header hoặc HAL |
| Dùng relation self cho trang trợ giúp | Client hiểu nhầm URI hỗ trợ là chính resource lỗi | Dùng IanaLinkRelations.HELP |
| Nhầm type với help link | Mất phân biệt giữa định danh problem type và trang trợ giúp theo ngữ cảnh | Giữ type ổn định, thêm link help riêng khi cần |
| Cố gọi add(Link) trên Problem | Problem không phải RepresentationModel | Dùng HTTP Link header hoặc một HAL error model riêng |
| Dùng VndErrors cho API mới | Phụ thuộc API đã deprecated | Dùng Problem Details và relation help |
| Dùng VndErrors.REL_HELP | Dùng hằng deprecated | Dùng IanaLinkRelations.HELP |
| Trả body Problem Details nhưng thêm _links tùy tiện | Client theo chuẩn Problem Details có thể không hiểu cấu trúc mở rộng | Dùng HTTP Link header hoặc định nghĩa extension member rõ ràng |
| Trả HAL nhưng không khai báo media type HAL | Client không biết cách phân tích _links | Dùng content negotiation và application/hal+json |
| Dùng một help URI không liên quan cho mọi lỗi | Người dùng không tìm được hướng xử lý phù hợp | Ánh xạ problem type tới trang trợ giúp cụ thể |
| Đưa dữ liệu nhạy cảm vào help URI | Dữ liệu có thể xuất hiện trong log, history hoặc referrer | Dùng URI tài liệu chung và occurrence identifier an toàn |
| Quên expose Link header qua CORS | JavaScript trong browser không đọc được help link | Thêm Link vào Access-Control-Expose-Headers |

## Ghi nhớ

Link hỗ trợ giúp client khám phá tài liệu hoặc nguồn trợ giúp theo ngữ cảnh của lỗi. Spring HATEOAS cung cấp relation chuẩn IanaLinkRelations.HELP. Với Problem Details, Problem là kiểu dữ liệu mô tả lỗi chứ không phải RepresentationModel, vì vậy hãy công bố link hỗ trợ bằng HTTP Link header theo RFC 8288. Nếu dùng error representation dựa trên HAL, có thể thêm link help trực tiếp vào RepresentationModel và trả đúng media type HAL. Phân biệt help URI với type và instance, kiểm thử cả body lẫn header, và không để error response làm lộ thông tin nội bộ.

## Tài liệu tham khảo

- [Spring HATEOAS – HTTP Problem Details](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.problem)
- [Spring HATEOAS – Problem API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/problem/Problem.html)
- [Spring HATEOAS – IanaLinkRelations API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/IanaLinkRelations.html)
- [Spring HATEOAS – VndErrors API and deprecation notice](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/vnderrors/VndErrors.html)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [Spring Framework – Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
