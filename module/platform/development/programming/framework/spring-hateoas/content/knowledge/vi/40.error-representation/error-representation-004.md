# Link retry

Một API tạo báo cáo có thể tạm thời không xử lý được yêu cầu vì hệ thống quá tải hoặc đã chạm giới hạn request. Response lỗi cần cho client biết điều gì xảy ra, khi nào nên thử lại và thao tác nào có thể thực hiện tiếp. Với hypermedia, server có thể công bố một link retry để client khám phá target của thao tác thử lại thay vì tự ghép URI.

Retry có ba phần cần phối hợp: **HTTP status và `Retry-After`** mô tả tình trạng cùng thời điểm nên gửi request tiếp theo; **link relation** chỉ ra target của thao tác; **idempotency contract** quyết định gửi lại có gây lặp tác động hay không. Chỉ có link retry chưa đủ để client gửi lại một request an toàn.

## Retry link là gì?

Retry link là một affordance cho biết client có thể thử lại một thao tác hoặc tiếp tục một quy trình sau lỗi tạm thời. Link có thể trỏ đến:

- Cùng resource/action đã thất bại, nếu API cho phép gửi lại request đó.
- Một retry endpoint riêng, nếu server quản lý các lần chạy lại của job hoặc command.
- Một resource hướng dẫn khôi phục, nếu client cần sửa điều kiện trước khi thử lại.

Link retry hữu ích khi server muốn công bố target hiện tại. Client đọc relation và `href` từ response, sau đó áp dụng method, headers và body theo hợp đồng đã công bố.

### Retry link không giống Retry-After

`Retry-After` là HTTP response header, không phải link relation. Header chỉ thời gian tối thiểu nên chờ trước khi follow-up request. Link cung cấp URI đích. Hai thành phần có thể cùng xuất hiện trong một response lỗi:

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Retry-After: 30
Link: </api/report-requests/rpt-1042/retry>; rel="https://api.example.com/rels/retry"

{
  "type": "https://api.example.com/problems/temporarily-unavailable",
  "title": "Dịch vụ tạm thời không khả dụng",
  "status": 503,
  "detail": "Hệ thống báo cáo đang quá tải.",
  "retryable": true
}
```

Trong ví dụ, `Retry-After: 30` hướng dẫn client chờ ít nhất 30 giây. Link relation `https://api.example.com/rels/retry` chỉ target retry endpoint. Client vẫn cần biết retry endpoint dùng method nào và yêu cầu dữ liệu gì.

## Relation retry có phải relation chuẩn IANA không?

Không nên giả định `retry` là một relation chuẩn. Trong IANA Link Relations Registry được kiểm tra ngày 26-11-2026, không có relation chuẩn tên `retry`. Nếu API muốn công bố quan hệ này, hãy định nghĩa extension relation URI do tổ chức kiểm soát, ví dụ:

```text
https://api.example.com/rels/retry
```

Với HAL, URI này có thể được rút gọn bằng CURIE thành `acme:retry`. Trong HTTP `Link` header, dùng URI relation đầy đủ theo RFC 8288; CURIE là quy ước của HAL, không phải cú pháp thay thế relation URI trong header.

Tài liệu extension relation cần nêu rõ context, target, HTTP method, request body, headers bắt buộc, điều kiện được retry, thời hạn của link và các lỗi có thể xảy ra. Không đổi semantics của relation đã công bố âm thầm.

### Phân biệt retry với monitor/status

Một request trả `202 Accepted` nghĩa là server đã nhận yêu cầu để xử lý nhưng chưa hoàn tất. Client cần theo dõi công việc đang chạy, không gửi lại request tạo công việc. RFC 9110 khuyến nghị representation `202` mô tả trạng thái hiện tại và trỏ đến hoặc nhúng status monitor.

IANA có các relation như `monitor` và `status` cho tài nguyên theo dõi/trạng thái. Dùng chúng cho polling; chỉ công bố relation retry khi client thực sự có thể khởi chạy lại thao tác.

| Relation | Ý nghĩa |
| --- | --- |
| `monitor` | Target dùng để theo dõi thay đổi của resource. |
| `status` | Target biểu diễn trạng thái của context. |
| `https://api.example.com/rels/retry` | Extension relation của API để thử lại một thao tác theo hợp đồng đã tài liệu hóa. |

## Các HTTP status thường gặp khi retry

Không phải mọi lỗi đều là lỗi tạm thời. Client cần kết hợp status, headers, problem type và semantics của request.

| Status | Ý nghĩa thường gặp | Hành vi retry |
| --- | --- | --- |
| `408 Request Timeout` | Server không nhận đủ request trong thời gian chờ. | Có thể gửi lại nếu request có thể retry an toàn; nếu tình trạng tạm thời, server nên gửi `Retry-After`. |
| `429 Too Many Requests` | Client vượt giới hạn tốc độ. | Chờ theo `Retry-After` nếu có, rồi thử lại theo rate limit. Response 429 không được cache. |
| `500 Internal Server Error` | Lỗi server không xác định. | Chỉ retry khi client có chính sách cho lỗi có thể tạm thời và request an toàn. |
| `502 Bad Gateway` | Gateway nhận phản hồi không hợp lệ từ upstream. | Có thể retry có giới hạn nếu request an toàn. |
| `503 Service Unavailable` | Server tạm thời không xử lý được request. | Server có thể gửi `Retry-After` để gợi ý thời điểm thử lại. |
| `504 Gateway Timeout` | Gateway không nhận phản hồi kịp thời từ upstream. | Kết quả upstream có thể chưa rõ; chỉ retry khi bảo đảm idempotency. |
| `409 Conflict` | Xung đột trạng thái hoặc request trùng đang xử lý. | Không tự retry mọi 409; làm theo hướng dẫn của problem type hoặc monitor link. |
| `412 Precondition Failed` | Điều kiện như `If-Match` không còn đúng. | Đọc representation mới, hòa giải thay đổi rồi tạo request mới. |
| `400`, `403`, `404`, `422` | Request sai, không được phép, không tìm thấy hoặc không hợp lệ về nghiệp vụ. | Không gửi lại cùng request mà không sửa nguyên nhân. |

`503` và `429` là hai trường hợp phổ biến nhất để server đưa ra thời gian chờ. RFC 9110 cũng định nghĩa `Retry-After` cho phản hồi 3xx: khi redirect, đây là khoảng thời gian tối thiểu cần đợi trước khi gửi request đến URI được chuyển hướng. Đó không phải chỉ dẫn thử lại thao tác ban đầu.

## Đọc Retry-After

Giá trị `Retry-After` có một trong hai dạng:

- `delay-seconds`: số giây không âm, ví dụ `Retry-After: 30`.
- `HTTP-date`: thời điểm tuyệt đối, ví dụ `Retry-After: Fri, 27 Nov 2026 02:00:00 GMT`.

Client cần hỗ trợ cả hai dạng. Nếu là số, chờ đúng số giây tối thiểu. Nếu là HTTP-date, tính khoảng thời gian từ thời điểm hiện tại đến ngày giờ đó. Nếu thời điểm đã qua, delay có thể xem là 0; nếu header sai định dạng, dùng retry policy cục bộ hoặc dừng theo chính sách.

Ví dụ parser Java:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Optional;

static Optional<Duration> parseRetryAfter(String value, Clock clock) {
    if (value == null || value.isBlank()) {
        return Optional.empty();
    }

    try {
        long seconds = Long.parseLong(value.trim());
        return seconds < 0
            ? Optional.empty()
            : Optional.of(Duration.ofSeconds(seconds));
    } catch (NumberFormatException ignored) {
        // Thử phân tích giá trị HTTP-date bên dưới.
    }

    try {
        Instant retryAt = ZonedDateTime.parse(
            value, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant();
        Duration delay = Duration.between(clock.instant(), retryAt);
        return Optional.of(delay.isNegative() ? Duration.ZERO : delay);
    } catch (DateTimeParseException ignored) {
        return Optional.empty();
    }
}
```

`Optional.empty()` nghĩa là header thiếu hoặc sai định dạng; caller phải dùng retry policy cục bộ hoặc dừng, không hiểu nó thành delay bằng 0. Trong production, nên ghi nhận header sai định dạng để theo dõi chất lượng API. Nếu client và server có thể lệch đồng hồ, có thể tham khảo response `Date` để ước lượng thời điểm tương đối. Không retry sớm hơn thời gian server yêu cầu chỉ vì đồng hồ client không chính xác.

## Retry phải tôn trọng idempotency

Một timeout không chứng minh server chưa thực hiện request. Client có thể đã gửi đủ body, server đã ghi dữ liệu, nhưng response bị mất trên đường về. Gửi lại một request không idempotent có thể tạo bản ghi hoặc thanh toán hai lần.

Theo HTTP semantics, một method idempotent có cùng hiệu ứng dự kiến trên server khi thực hiện một lần hoặc nhiều lần cùng request. Điều này không yêu cầu mọi response phải giống nhau. Các method safe như `GET`, `HEAD`, `OPTIONS` là idempotent; `PUT` và `DELETE` cũng được định nghĩa là idempotent. `POST` và `PATCH` không mặc nhiên idempotent.

| Request | Có thể retry tự động? | Điều kiện |
| --- | --- | --- |
| `GET /api/orders/ord-1042` | Thường có | Có giới hạn lần thử, timeout và backoff. |
| `PUT /api/profiles/42` | Có thể | Cùng URI và payload; semantics thực tế của endpoint phải idempotent. |
| `DELETE /api/orders/42` | Có thể | Endpoint tuân theo semantics idempotent; response lần sau có thể khác. |
| `POST /api/payments` | Không mặc định | Chỉ retry khi server hỗ trợ idempotency key hoặc hợp đồng khác bảo đảm không tạo tác động lặp. |
| `PATCH /api/orders/42` | Không mặc định | Chỉ retry khi semantics patch và cơ chế deduplication bảo đảm an toàn. |

Ngay cả với method idempotent, client vẫn cần giới hạn retry để tránh tải tăng đột biến. Với POST/PATCH, chỉ có link retry không biến request thành idempotent.

## Idempotency-Key cho thao tác không idempotent

Với thao tác như tạo thanh toán hoặc gửi lệnh xuất báo cáo, API có thể yêu cầu `Idempotency-Key`. Client tạo một key cho một ý định nghiệp vụ, gửi key cùng request và giữ nguyên key khi retry chính request đó.

```http
POST /api/payments HTTP/1.1
Content-Type: application/json
Idempotency-Key: "pay-7f4d2a1c-9e82-4a56-bcb0-18d6e0f2a113"

{
  "orderId": "ord-1042",
  "amount": 1250000,
  "currency": "VND"
}
```

Nếu client không nhận được response và cần gửi lại cùng thao tác, nó dùng lại key và payload ban đầu. Khi bắt đầu một thao tác thanh toán mới, client phải tạo key mới.

`Idempotency-Key` cần được API công bố rõ: endpoint nào yêu cầu, cú pháp key, phạm vi duy nhất, thời hạn lưu, cách xử lý payload khác nhau và response khi request trùng đang chạy. Header này không tự bảo đảm idempotency; server phải lưu và thực thi trạng thái key một cách nhất quán.

Tại thời điểm 26-11-2026, đặc tả `Idempotency-Key` đang ở trạng thái IETF Internet-Draft `draft-ietf-httpapi-idempotency-key-header-09`, chưa phải RFC. Draft hiện tại mô tả header dưới dạng Structured Field String; ví dụ dùng dấu nháy kép. Client cần tuân thủ cú pháp được endpoint công bố vì các API hiện có có thể dùng quy ước riêng.

### Server xử lý key như thế nào?

Một thiết kế phổ biến lưu các thông tin sau:

- Scope gồm tenant/principal, operation và key.
- Fingerprint của request, thường được tạo từ method, target và payload có liên quan.
- Trạng thái `IN_PROGRESS`, `COMPLETED` hoặc kết quả lỗi có thể retry.
- Response đã hoàn tất để trả lại cho request trùng.
- Thời điểm hết hạn của key.

Khi nhận key đã tồn tại:

1. Nếu fingerprint khác, từ chối vì cùng key đang được dùng cho payload khác.
2. Nếu thao tác đang chạy, trả trạng thái xung đột hoặc link monitor để client theo dõi.
3. Nếu thao tác đã hoàn tất, trả lại kết quả nhất quán với lần xử lý đầu tiên.
4. Nếu key đã hết hạn, hành vi phải theo chính sách expiry được công bố.

Thời gian lưu key phải dài ít nhất bằng cửa sổ retry mà API cam kết. Nếu key hết hạn quá sớm, client gửi lại sau đó có thể vô tình thực hiện thao tác lần hai.

## Backoff, jitter và giới hạn retry

Nhiều client cùng retry ngay lập tức sau khi nhận 503 hoặc 429 có thể làm server quá tải hơn. Client nên dùng exponential backoff có jitter và giới hạn số lần thử.

Một công thức phổ biến:

\[
  d_n = \min(d_{max}, d_{base} \times 2^{n-1})
\]

Trong đó `n` là lần retry, `d_base` là delay ban đầu và `d_max` là giới hạn. Jitter chọn một khoảng delay ngẫu nhiên để các client không đồng bộ gửi lại cùng lúc.

Khi có `Retry-After`, client phải đợi ít nhất khoảng thời gian đó. Có thể kết hợp:

\[
  d = \max(d_{server}, d_{backoff}) + jitter_{positive}
\]

`jitter_positive` chỉ cộng thêm thời gian, không làm request đến sớm hơn mốc server yêu cầu.

Retry policy nên có:

- Số lần thử tối đa.
- Deadline tổng thể cho toàn bộ operation.
- Timeout riêng cho từng attempt.
- Danh sách status/network error được xem là transient.
- Retry budget hoặc circuit breaker để tránh khuếch đại tải.
- Metric cho số lần retry, delay và kết quả cuối.

Nếu `Retry-After` vượt deadline mà client có thể chờ, hãy trả trạng thái cho caller hoặc lưu công việc để xử lý sau; không tự ý rút ngắn thời gian chờ.

## Phân biệt retry và polling một tác vụ bất đồng bộ

Ví dụ client gửi yêu cầu tạo báo cáo lớn. Server trả `202 Accepted` vì đã nhận công việc nhưng chưa hoàn tất:

```http
HTTP/1.1 202 Accepted
Content-Type: application/hal+json
Retry-After: 5

{
  "id": "job-1042",
  "state": "RUNNING",
  "_links": {
    "self": { "href": "/api/jobs/job-1042" },
    "monitor": { "href": "/api/jobs/job-1042/status" }
  }
}
```

Client chờ theo hướng dẫn của API rồi GET link `monitor` để đọc trạng thái. Nó không gửi lại POST tạo báo cáo, vì việc đó có thể tạo job thứ hai. Nếu job kết thúc với trạng thái `FAILED_RETRYABLE`, representation job có thể công bố thêm custom relation `acme:retry` để khởi động một attempt mới.

Trong ví dụ, API dùng `Retry-After: 5` làm gợi ý khoảng chờ trước lần polling tiếp theo. RFC 9110 mô tả cụ thể `Retry-After` cho 503 và 3xx; nếu dùng header này cho polling 202, API cần ghi rõ đó là quy ước polling của mình.

Ví dụ tạo monitor link bằng Spring HATEOAS:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

Link monitor = linkTo(methodOn(JobController.class).status(job.getId()))
    .withRel(IanaLinkRelations.MONITOR);

EntityModel<JobView> model = EntityModel.of(JobView.from(job), monitor);
```

`status(...)` là endpoint đọc trạng thái công việc. `monitor` là relation chuẩn; không dùng nó để biểu diễn một lệnh retry.

## Công bố retry link bằng Spring HATEOAS và Problem Details

Spring HATEOAS cung cấp `Link` và `LinkRelation` để tạo target cùng relation. `ProblemDetail` của Spring Framework có thể biểu diễn lỗi theo RFC 9457. Có thể kết hợp Problem Details body với HTTP `Link` header theo RFC 8288.

Ví dụ dưới đây trả lỗi 503 cho một request có thể thử lại sau 30 giây. API công bố một retry endpoint riêng và yêu cầu idempotency key cho lần retry:

```java
import java.net.URI;
import java.util.Map;
import java.util.UUID;

import org.springframework.hateoas.Link;
import org.springframework.hateoas.LinkRelation;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/report-requests")
class ReportRequestController {

    private static final LinkRelation RETRY_REL = LinkRelation.of(
        "https://api.example.com/rels/retry");

    private final ReportRetryService retryService;

    ReportRequestController(ReportRetryService retryService) {
        this.retryService = retryService;
    }

    @GetMapping("/{requestId}")
    ResponseEntity<ProblemDetail> temporarilyUnavailable(
            @PathVariable("requestId") UUID requestId) {
        Link retryLink = linkTo(methodOn(ReportRequestController.class)
                .retry(requestId, null))
            .withRel(RETRY_REL);

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Dịch vụ báo cáo đang tạm thời quá tải.");
        problem.setType(URI.create(
            "https://api.example.com/problems/temporarily-unavailable"));
        problem.setTitle("Dịch vụ tạm thời không khả dụng");
        problem.setProperty("retryable", true);
        problem.setProperty("retry", Map.of(
            "href", retryLink.getHref(),
            "method", "POST",
            "requiresIdempotencyKey", true));

        String linkHeader = "<" + retryLink.getHref() + ">; rel=\""
            + retryLink.getRel().value() + "\"";

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .header("Retry-After", "30")
            .header(HttpHeaders.LINK, linkHeader)
            .body(problem);
    }

    @PostMapping("/{requestId}/retry")
    ResponseEntity<?> retry(
            @PathVariable("requestId") UUID requestId,
            @RequestHeader("Idempotency-Key") String idempotencyKey) {
        return retryService.retry(requestId, idempotencyKey);
    }
}
```

Ví dụ giả định `ReportRetryService` kiểm tra quyền, trạng thái job và fingerprint của key trước khi tạo attempt mới. Trong `methodOn(...)`, tham số `null` chỉ là placeholder để tạo URI, không phải giá trị header gửi đến server.

`ProblemDetail` extension `retry` là hợp đồng riêng của ứng dụng, mô tả method và yêu cầu idempotency key. HTTP `Link` header cung cấp relation và target theo RFC 8288. Client có thể dùng một trong hai cách đã tài liệu hóa; không giả định mọi Problem Details parser đều tự hiểu extension này.

Nếu API dùng browser client cross-origin, cần expose `Link` header qua CORS để JavaScript đọc được. Nếu response dùng `application/problem+json`, đừng mặc định body đó là HAL; HTTP `Link` header và Problem Details extension cho phép giữ định dạng lỗi chuẩn mà vẫn cung cấp điều hướng.

## Client xử lý retry link

Client nên thực hiện theo trình tự:

1. Đọc status code và Problem Details `type` để xác định lỗi.
2. Xác định request ban đầu có thể retry an toàn không.
3. Đọc `Retry-After` và tính thời gian chờ tối thiểu.
4. Tìm extension relation retry trong `Link` header hoặc error extension theo hợp đồng.
5. Đọc method, body và headers cần thiết từ affordance/tài liệu.
6. Nếu thao tác không idempotent, giữ nguyên idempotency key và payload của logical operation.
7. Retry trong giới hạn attempts/deadline và theo backoff policy.
8. Nếu target không còn khả dụng hoặc lỗi không còn retryable, dừng và báo kết quả cho caller.

Không tự động follow mọi link có relation chưa biết. Client chỉ nên thực thi retry relation mà nó hỗ trợ và hiểu rõ method, payload cùng điều kiện an toàn.

## Kiểm thử retry link

Kiểm thử cần xác nhận status, header thời gian chờ, relation và target. Chỉ kiểm tra `503` là chưa đủ để chứng minh client có thể điều hướng đúng.

### Kiểm tra Problem Details và Link header

```java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(get("/api/report-requests/{id}", requestId)
        .accept(MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(status().isServiceUnavailable())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(header().string("Retry-After", "30"))
    .andExpect(header().string("Link",
        containsString("rel=\"https://api.example.com/rels/retry\"")))
    .andExpect(jsonPath("$.retryable").value(true))
    .andExpect(jsonPath("$.retry.method").value("POST"))
    .andExpect(jsonPath("$.retry.requiresIdempotencyKey").value(true));
```

Test giả định endpoint trả response lỗi minh họa và extension schema đã được công bố. Nếu API dùng HAL error body thay vì Problem Details, hãy kiểm tra `_links` theo media type đó.

### Kiểm tra retry target có thể được follow

Đọc `href` từ `Link` header, parse bằng RFC 8288 parser hoặc Spring HATEOAS `Link.valueOf(...)`, sau đó gửi request đến target với method và headers theo hợp đồng. Không ghép path từ `requestId` trong test.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.test.web.servlet.MvcResult;
import org.springframework.hateoas.Link;
import org.springframework.http.MediaType;

MvcResult result = mockMvc.perform(get("/api/report-requests/{id}", requestId)
        .accept(MediaType.APPLICATION_PROBLEM_JSON))
    .andExpect(status().isServiceUnavailable())
    .andReturn();

String rawLink = result.getResponse().getHeader("Link");
Link retry = Link.valueOf(rawLink);

assertThat(retry.getRel().value()).isEqualTo(
    "https://api.example.com/rels/retry");
assertThat(retry.getHref()).endsWith("/retry");
```

Nếu response có nhiều `Link` header hoặc nhiều link trong một header, dùng parser xử lý toàn bộ link values và tìm đúng relation; không giả định header chỉ chứa một link.

### Kiểm tra Retry-After ở cả hai dạng

- Với `Retry-After: 30`, client phải tính delay ít nhất 30 giây.
- Với `Retry-After` dạng HTTP-date, client phải parse date và tính thời gian còn lại.
- Với header thiếu hoặc sai định dạng, client phải áp dụng fallback policy đã định nghĩa.
- Với ngày trong quá khứ, không tạo delay âm.
- Nếu delay vượt deadline, client phải dừng hoặc chuyển sang xử lý bất đồng bộ.

Dùng `Clock.fixed(...)` trong unit test để kiểm tra date parsing ổn định, không phụ thuộc đồng hồ thật.

### Kiểm tra idempotency khi retry POST

Gửi cùng `Idempotency-Key` và cùng payload hai lần. Xác nhận server chỉ tạo một logical operation và trả kết quả nhất quán. Sau đó gửi lại cùng key với payload khác; server phải từ chối theo hợp đồng. Kiểm tra thêm request trùng khi lần đầu đang chạy và key đã hết hạn.

### Kiểm tra 202 không tạo job trùng

Khi nhận `202 Accepted`, client phải follow `monitor` hoặc `status` link. Test cần xác nhận client không gửi lại POST tạo job chỉ vì công việc chưa hoàn tất. Khi trạng thái job chuyển sang lỗi có thể retry, chỉ lúc đó client mới xem xét action link retry.

### Kiểm tra không retry lỗi vĩnh viễn

Với `400`, `403`, `404` hoặc `422`, xác nhận retry policy dừng và không tiếp tục gửi request. Với `429` hoặc `503`, xác nhận client tôn trọng `Retry-After`, số lần thử tối đa và deadline.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Coi `Retry-After` là một link | Client không có URI đích để điều hướng. | Dùng header cho thời gian chờ và link relation cho target. |
| Giả định `retry` là IANA relation | Client khác có thể không hiểu semantics. | Dùng extension relation URI và tài liệu hóa. |
| Retry POST sau timeout mà không có idempotency | Có thể tạo thanh toán/job/bản ghi trùng. | Dùng idempotency key và server-side deduplication. |
| Tạo key mới mỗi lần retry cùng thao tác | Server xem mỗi lần gửi là một logical operation khác. | Giữ nguyên key và payload trong cùng logical operation. |
| Gửi lại key với payload khác | Một key đại diện cho nhiều ý định nghiệp vụ. | Server kiểm tra fingerprint và từ chối mismatch. |
| Retry ngay lập tức mọi 5xx | Làm tăng tải khi hệ thống đang quá tải. | Phân loại lỗi, backoff, jitter và retry budget. |
| Bỏ qua `Retry-After` | Client vi phạm thời gian chờ server yêu cầu. | Chờ ít nhất giá trị header. |
| Coi `202 Accepted` là thất bại | Tạo nhiều job cho cùng yêu cầu. | Follow monitor/status link để polling. |
| Chỉ kiểm tra relation mà không biết method/body | Client không thể gọi retry target đúng cách. | Dùng affordance hoặc extension mô tả method và headers. |
| Dùng link thay cho authorization | Client có thể gọi target trực tiếp sau khi quyền thay đổi. | Kiểm tra quyền và trạng thái tại retry endpoint. |

## Ghi nhớ

- Retry link chỉ ra target; `Retry-After` chỉ thời gian chờ tối thiểu.
- Relation `retry` chưa phải relation chuẩn IANA; dùng extension URI và tài liệu hóa semantics.
- `monitor`/`status` dùng để theo dõi tác vụ `202 Accepted`, không phải gửi lại thao tác tạo job.
- Retry chỉ phù hợp với lỗi tạm thời và request có thể thực hiện lại an toàn.
- GET/HEAD/OPTIONS và các method idempotent có thể retry theo policy; POST/PATCH cần idempotency contract rõ ràng.
- Dùng `Idempotency-Key` với cùng key và payload cho cùng logical operation; server phải lưu trạng thái và deduplicate.
- `Retry-After` có thể là delay-seconds hoặc HTTP-date; client phải parse cả hai.
- Dùng exponential backoff, jitter, số lần thử tối đa, deadline và retry budget.
- RFC 9457 Problem Details có thể mở rộng bằng dữ liệu retry; HTTP Link header cung cấp relation/target.
- Kiểm thử status, Retry-After, relation, target, idempotency và hành vi polling.

## Tài liệu tham khảo

- [RFC 9110 – HTTP Semantics, Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3)
- [RFC 9110 – 202 Accepted và 503 Service Unavailable](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3)
- [RFC 6585 – 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [IANA Link Relations Registry](https://www.iana.org/assignments/link-relations/link-relations.xhtml)
- [IETF Internet-Draft – The Idempotency-Key HTTP Header Field, draft-ietf-httpapi-idempotency-key-header-09](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-09)
- [Spring HATEOAS API – Link](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [Spring HATEOAS API – LinkRelation](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/LinkRelation.html)
- [Spring Framework API – ProblemDetail](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html)
