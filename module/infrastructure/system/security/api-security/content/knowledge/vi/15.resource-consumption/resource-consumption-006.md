# 429, Retry-After và backoff đúng cách

Khi client gửi quá nhiều request trong một khoảng thời gian, API có thể trả `429 Too Many Requests`. Response này cho biết client cần giảm tốc độ hoặc chờ trước khi thử lại. Nếu server biết thời điểm có thể tiếp nhận request tiếp theo, nó có thể gửi header `Retry-After`. Client cần đọc header này và kết hợp với backoff để tránh tiếp tục gây tải lên hệ thống.

Xử lý `429` không chỉ là thêm một vòng lặp retry. Retry quá sớm có thể làm tình trạng quá tải nặng hơn; retry đồng loạt có thể tạo ra một đợt request mới đúng thời điểm quota được làm mới; retry một thao tác không idempotent có thể tạo giao dịch trùng. Vì vậy, server cần trả tín hiệu giới hạn rõ ràng, còn client cần có chiến lược chờ, jitter, giới hạn số lần thử và quy tắc xác định request nào được phép gửi lại.

Trong API Security, `429`, `Retry-After` và backoff là các biện pháp bảo vệ tài nguyên và tính sẵn sàng. Chúng cần phối hợp với xác thực, phân quyền, quota nghiệp vụ, idempotency và giám sát để hạn chế lạm dụng mà vẫn cho client hợp lệ phục hồi đúng cách.

Sau bài học, người đọc có thể:

- Giải thích ý nghĩa của `429 Too Many Requests` và phân biệt nó với `503 Service Unavailable`.
- Đọc và phát `Retry-After` theo đúng định dạng HTTP.
- Thiết kế exponential backoff, cap và jitter để giảm retry storm.
- Chỉ retry các request phù hợp với tính idempotent và có retry budget rõ ràng.
- Triển khai rate limit nhất quán trên nhiều instance và trả response lỗi an toàn.
- Kiểm thử hành vi retry của client và phản hồi giới hạn của server.

## 1. 429 Too Many Requests có nghĩa gì?

`429 Too Many Requests` được định nghĩa trong RFC 6585. Server dùng status này để cho biết client đã gửi quá nhiều request trong một khoảng thời gian. Cách xác định “client” và giới hạn phụ thuộc chính sách triển khai: có thể dựa trên IP, user, API key, access token, tenant, endpoint, tài nguyên hoặc tổ hợp nhiều yếu tố.

Ví dụ, API giới hạn một user gửi tối đa 60 request mỗi phút tới endpoint tìm kiếm. Khi user vượt ngưỡng, server có thể trả:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 30
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/rate-limit-exceeded",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Request limit exceeded. Please retry later.",
  "code": "RATE_LIMIT_EXCEEDED",
  "requestId": "req-7f31"
}
```

`Retry-After: 30` gợi ý client chờ ít nhất 30 giây trước khi thử lại. Response body cung cấp mã lỗi ổn định để ứng dụng xử lý; không cần tiết lộ thuật toán rate limit, khóa nội bộ hoặc ngưỡng bảo vệ nhạy cảm.

Một số điểm cần nhớ:

- `429` là phản hồi từ chối do tần suất/số lượng request vượt chính sách áp dụng.
- Header `Retry-After` có thể được gửi kèm để hướng dẫn thời điểm thử lại; header này không bắt buộc trong mọi response `429`.
- Theo RFC 6585, response `429` không được lưu bởi cache.
- `429` không chứng minh người gọi là attacker. Người dùng hợp lệ có thể vượt quota do ứng dụng gọi quá nhanh hoặc do nhiều tiến trình dùng chung credential.
- Client không nên tự động retry ngay lập tức khi nhận `429`.

## 2. Phân biệt 429 với 503 Service Unavailable

Hai status có thể cùng hướng client chờ trước khi gửi lại, nhưng lý do và phạm vi khác nhau.

| Status | Ý nghĩa thường gặp | Ví dụ | Hành vi phù hợp |
|---|---|---|---|
| `429 Too Many Requests` | Caller hoặc phạm vi request đã vượt giới hạn | User vượt 60 request/phút; tenant hết quota API | Giảm tốc độ, chờ theo `Retry-After`, kiểm tra quota |
| `503 Service Unavailable` | Server tạm thời không thể phục vụ | Bảo trì, quá tải toàn hệ thống, dependency chưa sẵn sàng | Tạm dừng retry, backoff và có thể theo `Retry-After` |

Nếu chỉ một user hoặc API key vượt giới hạn trong khi service vẫn khỏe, `429` thường phù hợp. Nếu toàn bộ service không đủ năng lực hoặc đang bảo trì, `503` thường diễn đạt đúng tình trạng hơn. Không dùng `429` như một mã lỗi chung cho mọi sự cố quá tải.

`Retry-After` cũng có thể xuất hiện trong response `503` để chỉ thời điểm dự kiến service có thể phục vụ lại. Client nên hiểu status code và header cùng nhau thay vì chỉ nhìn header rồi retry mọi loại lỗi.

## 3. Retry-After có hai định dạng

Theo HTTP semantics (RFC 9110), `Retry-After` có thể mang một trong hai dạng:

### 3.1. Delay-seconds

Giá trị là số nguyên không âm biểu thị số giây client nên chờ:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

Client chờ 30 giây rồi mới cân nhắc gửi lại. Server thường nên ưu tiên định dạng này khi biết thời gian chờ tương đối, vì client không phải xử lý sai lệch đồng hồ giữa hai hệ thống.

### 3.2. HTTP-date

Giá trị có thể là một ngày/giờ HTTP:

```http
HTTP/1.1 503 Service Unavailable
Date: Wed, 21 Oct 2015 07:20:00 GMT
Retry-After: Wed, 21 Oct 2015 07:30:00 GMT
```

Client tính khoảng chờ đến thời điểm được nêu. Nếu response có `Date`, client có thể so sánh hai mốc thời gian từ cùng server để giảm ảnh hưởng của đồng hồ máy khách bị lệch. Nếu không có `Date`, client phải dùng đồng hồ của mình và chấp nhận khả năng sai lệch.

### 3.3. Xử lý giá trị không hợp lệ

Client nên xử lý trường hợp header bị thiếu, sai định dạng, nằm trong quá khứ hoặc quá lớn:

- Nếu thiếu hoặc không parse được, dùng backoff mặc định có jitter; không retry ngay.
- Nếu HTTP-date nằm trong quá khứ, khoảng chờ có thể được xem là 0, nhưng vẫn nên áp dụng jitter nhỏ để tránh đồng loạt retry.
- Nếu giá trị vượt quá deadline hoặc thời gian chờ tối đa của ứng dụng, dừng và trả lỗi cho caller thay vì cố tình retry sớm hơn chỉ dẫn của server.
- Chặn giá trị âm, tràn số hoặc giá trị không thể biểu diễn an toàn trong timer.

Không nên giả định `Retry-After` luôn là số giây. Client chỉ parse integer sẽ xử lý sai response dùng HTTP-date.

## 4. Server nên chọn Retry-After như thế nào?

Server cần xác định giới hạn đang áp dụng và thời điểm có thể nhận request tiếp theo. Ví dụ với fixed window, nếu cửa sổ hiện tại kết thúc sau 18 giây, server có thể gửi `Retry-After: 18`. Với token bucket, thời gian chờ phụ thuộc số token còn thiếu và tốc độ refill. Với sliding window, thời điểm mở lại có thể dựa trên request cũ nhất cần hết khỏi cửa sổ.

Không nên trả một giá trị cố định không liên quan tới trạng thái limiter. Nếu mọi client đều nhận `Retry-After: 1` dù hệ thống cần 30 giây mới hồi phục, client sẽ quay lại quá sớm. Ngược lại, thời gian chờ quá dài không cần thiết làm giảm trải nghiệm và khiến client bỏ cuộc.

Một response giới hạn nên:

- Trả đúng status `429` cho caller/phạm vi bị giới hạn.
- Gửi `Retry-After` khi có thể ước tính thời điểm thử lại.
- Cung cấp mã lỗi ổn định và request/correlation ID để hỗ trợ chẩn đoán.
- Tránh tiết lộ khóa limiter, cấu trúc nội bộ hoặc thông tin của user khác.
- Không đưa response `429` vào cache.
- Áp dụng cùng một chính sách trên mọi instance, gateway và endpoint tương ứng.

### 4.1. Ví dụ Spring Boot trả 429

Giả sử limiter trả về thời gian còn lại trước khi user có thể thử lại:

```java
Duration remaining = rateLimitResult.retryAfter();
long retryAfterSeconds = Math.max(
        1,
        (remaining.toMillis() + 999) / 1000);

ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.TOO_MANY_REQUESTS,
        "Request limit exceeded. Please retry later.");
problem.setProperty("code", "RATE_LIMIT_EXCEEDED");

return ResponseEntity
        .status(HttpStatus.TOO_MANY_REQUESTS)
        .header(HttpHeaders.RETRY_AFTER,
                Long.toString(retryAfterSeconds))
        .cacheControl(CacheControl.noStore())
        .body(problem);
```

Đây là phần tạo response; `rateLimitResult` phải đến từ limiter đã kiểm tra request. Với thời gian chờ rất lớn, cần giới hạn kiểu số và định dạng header an toàn. Nếu không xác định được thời điểm refill, có thể bỏ `Retry-After` và để client dùng backoff có jitter.

### 4.2. Rate limit phải nhất quán trên nhiều instance

Nếu API chạy trên nhiều pod/VM, bộ đếm trong bộ nhớ của từng instance không tạo ra giới hạn toàn cục. Một user có thể gửi request luân phiên qua nhiều instance và nhận quota lớn hơn dự kiến.

Tùy yêu cầu, có thể dùng Redis hoặc một bộ lưu trữ chia sẻ hỗ trợ thao tác nguyên tử, API gateway có distributed rate limit, hoặc một dịch vụ quota tập trung. Cần bảo đảm việc kiểm tra và trừ quota không có race condition. Khi kho limiter lỗi, chọn hành vi fail-open hay fail-closed theo mức độ rủi ro và tác động sẵn sàng; thao tác nhạy cảm hoặc có chi phí lớn thường cần chính sách bảo vệ chặt hơn.

## 5. Exponential backoff là gì?

Exponential backoff tăng dần thời gian chờ sau mỗi lần retry. Thay vì gửi lại liên tục mỗi giây, client có thể chờ 1 giây, 2 giây, 4 giây, 8 giây và tiếp tục tăng cho tới một mức trần.

Công thức cơ bản:

\[
delay_n = \min(cap, base \times 2^n)
\]

Trong đó:

- `base` là thời gian chờ ban đầu, ví dụ 500 ms.
- `n` là số lần retry đã thực hiện, bắt đầu từ 0.
- `cap` là thời gian chờ tối đa, ví dụ 30 giây.

Ví dụ với `base = 1s`, `cap = 16s`:

| Lần retry | Backoff chưa có jitter |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |
| 6 trở đi | 16 giây |

Backoff làm giảm tần suất retry khi hệ thống đang gặp vấn đề. Tuy nhiên, nếu hàng nghìn client cùng nhận lỗi và cùng dùng một lịch cố định, tất cả có thể gửi lại tại các mốc giống nhau. Hiện tượng đó gọi là retry storm hoặc thundering herd.

## 6. Jitter giúp tránh retry đồng loạt

Jitter thêm độ ngẫu nhiên vào thời gian chờ để các client không đồng bộ. Một cách phổ biến là **full jitter**:

\[
delay_n = random(0, \min(cap, base \times 2^n))
\]

Ví dụ, nếu backoff tối đa ở lần retry là 8 giây, mỗi client chọn ngẫu nhiên thời gian từ 0 đến 8 giây. Các request được phân tán thay vì dồn vào cùng một thời điểm.

Các biến thể thường gặp:

| Chiến lược | Cách tính | Đặc điểm |
|---|---|---|
| No jitter | `min(cap, base × 2^n)` | Dễ triển khai nhưng các client đồng bộ |
| Full jitter | `random(0, upperBound)` | Phân tán mạnh, giảm đợt retry đồng loạt |
| Equal jitter | `upperBound/2 + random(0, upperBound/2)` | Có thời gian chờ tối thiểu, độ phân tán thấp hơn full jitter |
| Decorrelated jitter | Chọn ngẫu nhiên dựa trên lần chờ trước và base, giới hạn bởi cap | Thời gian chờ thay đổi linh hoạt giữa các lần |

### 6.1. Kết hợp Retry-After với jitter

Khi server gửi `Retry-After`, client phải coi đó là thời gian chờ tối thiểu theo chỉ dẫn. Không dùng full jitter từ 0 đến backoff nếu điều đó có thể làm client gửi lại trước thời điểm server yêu cầu.

Một cách kết hợp:

```text
if có Retry-After hợp lệ:
    delay = retryAfter + random(0, postRetryJitter)
else:
    delay = random(0, min(cap, base * 2^attempt))
```

`postRetryJitter` có thể là một khoảng nhỏ được cấu hình để phân tán client sau mốc server cho phép. Nếu server trả một thời gian chờ rất dài, client vẫn phải tôn trọng nó hoặc dừng vì deadline; không cắt ngắn thời gian rồi retry sớm hơn.

## 7. Chỉ retry khi request phù hợp

Retry có thể gây tác động trùng nếu request đã được xử lý nhưng response bị mất. Client cần xét ngữ nghĩa HTTP và hợp đồng API.

| Request | Có thể retry tự động? | Điều kiện |
|---|---|---|
| `GET` đọc dữ liệu | Thường có | Request không tạo side effect và còn trong deadline |
| `HEAD` | Thường có | Không có side effect nghiệp vụ |
| `PUT` | Có thể | Endpoint tuân thủ idempotency và payload được giữ nguyên |
| `DELETE` | Có thể | Endpoint có hiệu ứng idempotent; xử lý response lần sau theo hợp đồng |
| `PATCH` | Không mặc nhiên | Chỉ retry nếu patch được thiết kế idempotent hoặc có cơ chế chống trùng |
| `POST` tạo giao dịch | Không mặc nhiên | Cần idempotency key hoặc định danh nghiệp vụ duy nhất |

Method không phải yếu tố duy nhất. Một endpoint GET sai thiết kế vẫn có thể gửi email hoặc thay đổi dữ liệu; một POST tìm kiếm có thể chỉ đọc nhưng cần hợp đồng rõ ràng. Client phải dựa trên hành vi thực tế của API.

Với thao tác không idempotent như thanh toán, tạo đơn, gửi OTP hoặc hoàn tiền, server nên hỗ trợ idempotency key. Key phải được scope theo caller/tenant và action, gắn với fingerprint payload, có thời hạn lưu và xử lý request đồng thời. Gửi lại cùng key và cùng payload phải trả cùng kết quả nghiệp vụ; cùng key với payload khác cần bị từ chối.

## 8. Retry budget, deadline và giới hạn số lần thử

Backoff không được biến một request thành vòng retry vô hạn. Mỗi client nên có:

- **Maximum attempts:** tổng số lần gửi tối đa, bao gồm lần đầu hay chỉ tính retry phải được định nghĩa rõ.
- **Deadline/timeout tổng:** thời điểm cuối cùng kết quả còn hữu ích cho caller.
- **Per-attempt timeout:** giới hạn thời gian cho từng lần gọi.
- **Retry budget:** giới hạn tổng lượng retry trong một khoảng thời gian hoặc tỷ lệ retry so với request gốc.
- **Cancellation:** khi người dùng hủy hoặc request cha hết hạn, các lần retry đang chờ phải dừng.
- **Circuit breaker:** tạm ngừng gọi dependency khi lỗi kéo dài để tránh tiếp tục gây tải.

Ví dụ, một request có deadline 5 giây không nên chờ `Retry-After: 60` rồi mới gửi lại. Client nên kết thúc với lỗi phù hợp, có thể trả trạng thái giới hạn cho tầng gọi phía trên hoặc thông báo thử lại sau. Không được bỏ qua chỉ dẫn 60 giây chỉ vì timeout nội bộ ngắn hơn.

Retry budget cũng cần được chia sẻ hợp lý giữa các tầng. Nếu browser retry 3 lần, gateway retry 3 lần và service retry 3 lần, một request gốc có thể tạo tới 27 lần gọi downstream. Hãy xác định một tầng chịu trách nhiệm retry hoặc truyền budget/deadline xuyên suốt để tránh khuếch đại request.

## 9. Những lỗi không nên retry một cách mù quáng

Không phải mọi lỗi đều tạm thời. Ví dụ:

- `400 Bad Request`: request sai cấu trúc; gửi lại y nguyên không sửa sẽ tiếp tục thất bại.
- `401 Unauthorized`: cần xác thực lại hoặc làm mới token theo flow được phép; không retry liên tục cùng credential sai.
- `403 Forbidden`: caller không có quyền; retry không làm quyền tự xuất hiện.
- `404 Not Found`: tài nguyên không tồn tại hoặc bị che giấu; không retry liên tục nếu không có lý do eventual consistency rõ ràng.
- `409 Conflict`: cần đọc trạng thái mới hoặc giải quyết xung đột theo nghiệp vụ.
- `422 Unprocessable Content`: dữ liệu không đáp ứng quy tắc; cần sửa dữ liệu hoặc điều kiện.
- `429 Too Many Requests`: chờ theo `Retry-After` hoặc backoff có jitter và kiểm tra quota.
- `503 Service Unavailable`: có thể retry nếu thao tác phù hợp và còn deadline, ưu tiên theo `Retry-After`.

`500` hoặc các lỗi mạng có thể tạm thời, nhưng không nên retry vô điều kiện. Cần xác định endpoint, tính idempotent, loại lỗi, deadline và retry budget. Nếu không chắc server đã thực hiện thao tác hay chưa, hãy dùng idempotency key hoặc truy vấn trạng thái giao dịch trước khi gửi lại.

## 10. Ví dụ logic retry ở Java

Ví dụ dưới đây minh họa cách tính thời gian chờ. Phần parse header cần hỗ trợ cả delay-seconds và HTTP-date; `retryAfter` là thời lượng đã được parse và kiểm tra an toàn.

```java
Duration nextDelay(
        int attempt,
        Optional<Duration> retryAfter,
        Duration base,
        Duration cap) {

    long multiplier = 1L << Math.min(attempt, 20);
    long upperBoundMillis = Math.min(
            cap.toMillis(),
            Math.multiplyExact(base.toMillis(), multiplier));

    if (retryAfter.isPresent()) {
        long serverMinimum = Math.max(0, retryAfter.get().toMillis());
        long extraJitter = ThreadLocalRandom.current()
                .nextLong(0, 1001);
        return Duration.ofMillis(serverMinimum + extraJitter);
    }

    long fullJitter = ThreadLocalRandom.current()
            .nextLong(0, upperBoundMillis + 1);
    return Duration.ofMillis(fullJitter);
}
```

Đây là đoạn minh họa phần chọn delay, chưa phải một retry engine hoàn chỉnh. Trong code production cần xử lý overflow cho phép cộng/nhân, giới hạn giá trị header, kiểm tra deadline trước khi schedule và tránh dùng `Thread.sleep` trên request thread. Ứng dụng reactive hoặc server nhiều request nên dùng scheduler/bộ retry bất đồng bộ có cancellation.

Luồng xử lý tổng quát:

```text
Gửi request
  ├─ Thành công → trả kết quả
  └─ Lỗi
      ├─ Không retryable → trả lỗi
      ├─ Request không an toàn để gửi lại → trả lỗi hoặc kiểm tra trạng thái
      ├─ Hết attempts / deadline / retry budget → dừng
      └─ Tính delay từ Retry-After hoặc exponential backoff + jitter
          ├─ Delay vượt deadline → dừng
          └─ Schedule retry, giữ nguyên idempotency key và request intent
```

## 11. Ví dụ client xử lý 429 và Retry-After

Một client HTTP nên đọc status trước, rồi chỉ thực hiện retry nếu request phù hợp:

```java
if (response.statusCode() == 429 || response.statusCode() == 503) {
    if (!retryPolicy.isRetryable(request)) {
        return response;
    }

    Optional<Duration> retryAfter = parseRetryAfter(
            response.headers(), clock);
    Duration delay = backoff.nextDelay(attempt, retryAfter);

    if (clock.instant().plus(delay).isAfter(deadline)) {
        return response;
    }

    scheduler.schedule(
            () -> retrySameIntent(request, idempotencyKey),
            delay);
}
```

Đoạn code là pseudocode định hướng vì `retryPolicy`, `parseRetryAfter`, `backoff` và scheduler cần được triển khai theo HTTP client/framework đang dùng. Các nguyên tắc quan trọng:

- `parseRetryAfter` phải nhận cả số giây và HTTP-date.
- Chỉ retry status được policy cho phép; không retry mọi `4xx`/`5xx`.
- Giữ nguyên body, request intent và idempotency key cho cùng một thao tác.
- Không gửi lại request trước thời điểm `Retry-After`.
- Không schedule nếu deadline hoặc retry budget đã hết.
- Khi caller hủy request, hủy tác vụ retry đang chờ.

Với client library đã có retry policy, cần kiểm tra mặc định của thư viện: một số cấu hình có thể retry `429` nhưng không tôn trọng `Retry-After`, hoặc retry POST mà không có idempotency key. Cấu hình phải được kiểm thử bằng response giả lập, không dựa vào tên tính năng.

## 12. Kiểm thử server và client

Kiểm thử cần chứng minh server phát tín hiệu đúng và client tuân thủ tín hiệu đó.

| Tình huống | Kiểm tra phía server | Kiểm tra phía client |
|---|---|---|
| Trong giới hạn | Request được xử lý bình thường | Không retry |
| Vượt giới hạn | Trả `429`, body lỗi ổn định | Không retry ngay |
| Retry-After dạng giây | Trả `Retry-After: 30` | Không gửi trước 30 giây |
| Retry-After dạng ngày | Trả HTTP-date hợp lệ | Parse đúng thời điểm và xử lý clock skew |
| Header thiếu/sai | Response vẫn hợp lệ | Dùng backoff mặc định có jitter |
| Nhiều client cùng bị giới hạn | Giá trị chờ có cơ sở | Jitter phân tán thời điểm retry |
| 503 bảo trì | Có thể trả Retry-After | Backoff và tuân thủ thời gian chờ |
| POST thanh toán bị 429 | Không tạo giao dịch nếu request bị từ chối theo hợp đồng | Chỉ retry với idempotency key hoặc trạng thái đã xác minh |
| Deadline ngắn hơn Retry-After | Trả thời gian chờ chính xác | Dừng, không retry sớm |
| Retry budget cạn | Server không bị gọi thêm | Client dừng retry |
| Nhiều instance | Bộ đếm/giới hạn nhất quán | Không vượt limit khi request phân tán |
| Request bị hủy | Không giữ reservation không cần thiết | Retry đang chờ được cancel |

Test thời gian không nên dựa vào sleep dài trong unit test. Dùng clock/scheduler giả hoặc virtual time để xác minh thời điểm retry có thể tái lập. Integration test cần kiểm tra cả số request thực tế gửi đi và tác động dữ liệu, đặc biệt với POST, PATCH và các thao tác thanh toán.

## 13. Giám sát và vận hành

Server nên theo dõi:

- Số response `429` theo endpoint, tenant, user/client và limiter scope.
- Tỷ lệ request bị giới hạn so với tổng request.
- Số lần client retry, thời gian chờ thực tế và số lần retry thành công.
- Số request bị từ chối vì quota nghiệp vụ so với rate limit kỹ thuật.
- Tình trạng kho limiter phân tán, độ trễ và lỗi đồng bộ bộ đếm.
- Retry storm, request fan-out và tải tăng bất thường sau thời điểm reset.

Client nên ghi nhận status, số lần attempt, thời gian chờ và request/correlation ID. Không log access token, API key, cookie hoặc payload nhạy cảm. Khi nhiều tầng cùng retry, dùng trace/correlation ID để xác định một request gốc đã tạo bao nhiêu lần gọi downstream.

Khi điều chỉnh limit, cân nhắc lưu lượng hợp lệ theo giờ cao điểm, tenant lớn, client có batch và các request dùng chung NAT. Hạn mức quá thấp tạo false positive; hạn mức quá cao không bảo vệ được tài nguyên. Có thể rollout thay đổi theo nhóm client hoặc tenant và quan sát trước khi áp dụng rộng.

## 14. Checklist triển khai

- [ ] Dùng `429` cho caller/phạm vi vượt giới hạn và phân biệt với `503` khi service tạm thời không khả dụng.
- [ ] `Retry-After` được phát theo delay-seconds hoặc HTTP-date đúng định dạng.
- [ ] Giá trị chờ phản ánh thời điểm có thể thử lại; không gửi một con số tùy tiện.
- [ ] Response `429` không được cache và không tiết lộ thông tin limiter nhạy cảm.
- [ ] Rate limit có scope phù hợp và nhất quán trên nhiều instance.
- [ ] Client parse cả hai định dạng `Retry-After`, xử lý header lỗi và clock skew.
- [ ] Client dùng exponential backoff có cap và jitter.
- [ ] Khi có `Retry-After`, client không retry sớm hơn thời gian server chỉ dẫn.
- [ ] Chỉ retry request có ngữ nghĩa an toàn hoặc có idempotency key phù hợp.
- [ ] Có maximum attempts, deadline, retry budget và cancellation.
- [ ] Không retry mù quáng các lỗi `400`, `401`, `403`, `404`, `409` hoặc `422`.
- [ ] Retry không bị nhân lên qua nhiều tầng client/gateway/service.
- [ ] Có test thời gian, test đồng thời, test nhiều instance và test tác động dữ liệu.
- [ ] Có metric/cảnh báo cho `429`, retry storm và lỗi limiter.

## Kết luận

`429` cho biết request đã vượt giới hạn; `Retry-After` hướng dẫn thời điểm nên thử lại; exponential backoff và jitter giúp client phục hồi mà không tạo thêm đợt tải đồng loạt. Thiết kế đúng cần đồng thời giới hạn retry bằng attempts/deadline/budget, chỉ retry thao tác phù hợp với idempotency và bảo đảm limiter nhất quán trên nhiều instance. Server và client phải phối hợp theo cùng một hợp đồng để bảo vệ tài nguyên mà vẫn giữ trải nghiệm ổn định.
