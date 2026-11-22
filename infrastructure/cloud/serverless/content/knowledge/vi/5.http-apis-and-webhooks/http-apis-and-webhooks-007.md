# Rate limiting, quota và bảo vệ endpoint công khai

Một HTTP endpoint serverless có thể được gọi từ trình duyệt, ứng dụng di động, đối tác hoặc hệ thống tự động trên Internet. Khi endpoint trở nên công khai, số request và cách sử dụng không còn nằm hoàn toàn trong tầm kiểm soát của đội phát triển. Một client lỗi có thể gửi request liên tục; một tài khoản có thể chiếm hết năng lực xử lý; bot có thể dò endpoint; hoặc một webhook bị gửi lại nhiều lần.

Rate limiting, quota và các lớp bảo vệ giúp kiểm soát lưu lượng, bảo vệ dịch vụ phía sau và giữ chi phí trong giới hạn dự kiến. Với Java function, cần đặt giới hạn ở đúng lớp: edge hoặc API gateway để chặn lưu lượng trước khi function chạy, lớp ứng dụng để áp dụng chính sách theo người dùng/tenant, và các giới hạn concurrency để bảo vệ cơ sở dữ liệu cùng dịch vụ phụ thuộc.

## 1. Phân biệt rate limit, burst, concurrency và quota

Các thuật ngữ này có liên quan nhưng mô tả những giới hạn khác nhau:

| Khái niệm | Kiểm soát | Ví dụ minh họa |
|---|---|---|
| Rate limit | Số request trong một khoảng thời gian | Một client được phép gửi trung bình 20 request mỗi giây |
| Burst limit | Số request có thể đến dồn trong thời gian ngắn | Cho phép một đợt 40 request tức thời rồi giảm tốc độ |
| Concurrency limit | Số invocation hoặc tác vụ được chạy cùng lúc | Chỉ cho phép tối đa 30 function đồng thời |
| Quota | Tổng mức sử dụng trong một chu kỳ dài hơn | Một tenant có 100.000 request mỗi tháng |
| Payload limit | Kích thước dữ liệu một request hoặc message | Request body không vượt giới hạn được công bố |
| Timeout | Thời gian tối đa dành cho một lần xử lý | Function hoặc lời gọi dịch vụ phải kết thúc trong deadline |

Rate limit ngăn một nguồn gửi request quá nhanh. Burst limit cho phép dao động ngắn hạn mà vẫn giữ tốc độ trung bình. Concurrency limit bảo vệ tài nguyên khi request chậm và chồng lấn. Quota kiểm soát tổng mức sử dụng theo ngày, tháng hoặc kỳ thanh toán.

Không thể thay thế một giới hạn bằng giới hạn khác. Một client gửi 10 request mỗi giây nhưng mỗi request mất 30 giây vẫn có thể tạo ra hàng trăm invocation đồng thời. Ngược lại, giới hạn concurrency thấp có thể khiến request bị xếp hàng hoặc throttled dù tốc độ gửi chưa vượt rate limit.

## 2. Chọn phạm vi áp dụng giới hạn

Một endpoint công khai thường cần nhiều lớp giới hạn:

- **Toàn hệ thống:** bảo vệ API gateway, function và dịch vụ phụ thuộc trước lưu lượng tăng đột biến.
- **Theo IP hoặc dải mạng:** hạn chế bot và client chưa xác thực.
- **Theo danh tính đã xác thực:** áp dụng cho user, service account, API client hoặc tenant.
- **Theo endpoint và phương thức:** endpoint tìm kiếm tốn tài nguyên có thể cần giới hạn thấp hơn endpoint đọc trạng thái.
- **Theo nghiệp vụ:** giới hạn số lần gửi OTP, tạo báo cáo, thử thanh toán hoặc thực hiện thao tác nhạy cảm.
- **Theo chu kỳ sử dụng:** quota theo ngày/tháng cho gói dịch vụ hoặc hợp đồng.

Chỉ giới hạn theo IP thường không đủ. Nhiều người dùng có thể cùng đi qua một NAT, proxy hoặc mạng doanh nghiệp nên dễ bị giới hạn nhầm. Botnet có thể phân tán request qua nhiều IP. IP cũng không xác định được tenant hay quyền nghiệp vụ.

Ngược lại, chỉ giới hạn theo API key cũng chưa đủ. Key có thể bị lộ hoặc được chia sẻ. Cần có giới hạn tổng ở edge, giới hạn theo danh tính sau xác thực và giới hạn theo thao tác nghiệp vụ ở tầng ứng dụng.

Với hệ thống nhiều tenant, mỗi request cần được gắn với tenant đã xác thực từ token hoặc danh tính đáng tin cậy. Không lấy tenant ID từ một header hoặc query parameter do client tự khai báo rồi dùng trực tiếp làm khóa quota. Nếu client được phép chọn tenant, phải kiểm tra quyền truy cập tenant đó trước khi áp dụng quota.

## 3. Các thuật toán rate limiting phổ biến

### 3.1. Fixed window counter

Chia thời gian thành các cửa sổ cố định, ví dụ từng phút. Mỗi request tăng bộ đếm của cửa sổ hiện tại. Khi bộ đếm vượt ngưỡng, từ chối request.

Ưu điểm là đơn giản, dễ triển khai bằng bộ đếm có TTL và chi phí thấp. Nhược điểm là hiện tượng dồn ở ranh giới cửa sổ. Nếu client gửi sát cuối phút rồi tiếp tục gửi ngay đầu phút kế tiếp, nó có thể tạo ra gần gấp đôi số request trong một khoảng thời gian rất ngắn.

### 3.2. Sliding window log

Lưu thời điểm của từng request trong khoảng thời gian gần nhất. Khi có request mới, loại bỏ các thời điểm đã hết hạn rồi đếm số còn lại.

Cách này kiểm soát chính xác hơn nhưng cần lưu nhiều dấu thời gian, làm tăng bộ nhớ và số thao tác. Với lưu lượng lớn, việc ghi từng request vào log có thể tốn kém.

### 3.3. Sliding window counter

Kết hợp bộ đếm của cửa sổ hiện tại và cửa sổ liền trước, có trọng số theo phần thời gian đã trôi qua. Cách này giảm hiện tượng dồn ở ranh giới mà không cần lưu từng request.

Đây là cách xấp xỉ. Nó thường phù hợp khi cần giới hạn mượt hơn fixed window nhưng muốn giữ trạng thái nhỏ.

### 3.4. Token bucket

Một bucket chứa token, được bổ sung theo tốc độ cố định cho đến mức tối đa. Mỗi request tiêu thụ một hoặc nhiều token. Nếu không đủ token, request bị từ chối hoặc phải chờ.

- Refill rate quyết định tốc độ trung bình được phép.
- Bucket capacity quyết định burst tối đa.
- Cost mỗi request có thể khác nhau theo độ nặng của endpoint.

Token bucket phù hợp với API cần cho phép burst ngắn nhưng vẫn kiểm soát tốc độ dài hạn. Có thể gán cost cao hơn cho truy vấn nặng hoặc thao tác tạo báo cáo.

### 3.5. Leaky bucket

Request được đưa vào một hàng đợi và xử lý với tốc độ ổn định. Hàng đợi có giới hạn; khi đầy, request mới bị từ chối.

Cách này làm phẳng lưu lượng và bảo vệ dịch vụ phía sau, nhưng có thể tăng độ trễ. Với HTTP đồng bộ, thời gian chờ trong queue phải nằm trong deadline của client và gateway. Nếu không thể xử lý trong thời gian đó, nên chuyển sang mô hình job bất đồng bộ.

| Thuật toán | Burst | Trạng thái cần lưu | Đặc điểm |
|---|---|---|---|
| Fixed window | Có thể dồn ở ranh giới | Một counter mỗi cửa sổ | Đơn giản, dễ triển khai |
| Sliding log | Kiểm soát chính xác trong cửa sổ | Dấu thời gian từng request | Tốn bộ nhớ và thao tác |
| Sliding counter | Mượt hơn fixed window | Counter của vài cửa sổ | Xấp xỉ, trạng thái nhỏ |
| Token bucket | Cho phép burst có giới hạn | Số token và thời điểm cập nhật | Linh hoạt cho API |
| Leaky bucket | Làm phẳng lưu lượng | Hàng đợi và tốc độ xử lý | Kiểm soát tốc độ đầu ra |

Không có thuật toán tốt nhất cho mọi endpoint. Hãy chọn theo đặc tính lưu lượng, mức độ chính xác, độ trễ cho phép và chi phí lưu trạng thái.

## 4. Triển khai rate limiting trong kiến trúc serverless

### 4.1. Đặt giới hạn ở edge hoặc API gateway

Một request công khai thường đi qua CDN, WAF, load balancer hoặc API gateway trước khi đến Java function. Đặt giới hạn ở lớp này giúp loại bỏ request sớm, tránh tốn chi phí invocation và giảm tải cho dịch vụ phía sau.

Có thể cấu hình:

- Giới hạn tốc độ và burst tổng thể cho API.
- Giới hạn theo route, method hoặc stage.
- Giới hạn theo API key hoặc client identity nếu gateway hỗ trợ.
- Giới hạn kích thước request và timeout.
- Quy tắc WAF để chặn mẫu request độc hại hoặc nguồn có hành vi bất thường.

Cần hiểu ngữ nghĩa của dịch vụ cụ thể. Một số gateway mô tả throttling là best-effort, có thể dao động quanh ngưỡng khi có nhiều node hoặc request đồng thời. Throttling cũng không nhất thiết là quota cứng theo tháng. Nếu cần giới hạn chi tiêu hoặc số request theo hợp đồng, hãy có bộ đếm quota riêng và cảnh báo sử dụng.

### 4.2. Không dùng API key làm bằng chứng xác thực

API key có thể hữu ích để nhận diện ứng dụng, đo usage và áp dụng quota. Nhưng key dạng bearer có thể bị sao chép và sử dụng bởi bất kỳ ai lấy được nó. Không xem việc client gửi đúng API key là đủ để cấp quyền truy cập dữ liệu hoặc thao tác nhạy cảm.

Dùng cơ chế xác thực phù hợp như OAuth 2.0/OIDC, JWT được xác minh đúng issuer/audience/signature, mutual TLS cho một số kết nối dịch vụ hoặc cơ chế danh tính của nền tảng. Sau xác thực, kiểm tra authorization theo tài nguyên và tenant. API key có thể bổ sung cho việc phân loại client nhưng không thay thế xác thực và phân quyền.

### 4.3. Rate limiter phân tán cho nhiều function instance

Một Java function có thể được khởi chạy trên nhiều execution environment. Bộ đếm static hoặc biến trong bộ nhớ chỉ nhìn thấy ở một process. Nếu mỗi instance tự cho phép 20 request/giây, 10 instance có thể cùng cho phép xấp xỉ 200 request/giây.

Vì vậy, giới hạn theo user hoặc tenant cần trạng thái dùng chung, ví dụ Redis, database có thao tác cập nhật có điều kiện hoặc một dịch vụ rate limiting chuyên dụng. Thao tác kiểm tra và tiêu thụ quota phải nguyên tử để hai invocation đồng thời không cùng đọc một giá trị cũ rồi đều cho phép request.

~~~mermaid
flowchart LR
    C["Clients"] --> E["CDN / WAF / API Gateway"]
    E --> A["Xác thực và phân quyền"]
    A --> R["Rate limiter dùng chung"]
    R -->|Được phép| F["Java Function"]
    R -->|Vượt giới hạn| X["HTTP 429"]
    F --> D["Database / dịch vụ phụ thuộc"]
~~~

Một thao tác consume nguyên tử có thể nhận khóa giới hạn, thời điểm hiện tại, refill rate, capacity và cost. Nó trả về quyết định allow/deny cùng số token còn lại và thời điểm có thể thử lại. Với Redis, có thể dùng Lua script để đọc, tính toán và ghi trạng thái trong một thao tác nguyên tử. Với database, dùng conditional update hoặc transaction có điều kiện để tránh lost update.

Nếu dùng Redis, cần xác định TTL, xử lý key hết hạn, clock source và hành vi khi Redis lỗi. Không nên tạo một key cho mọi giá trị tùy ý từ client mà không kiểm soát, vì attacker có thể làm tăng cardinality và chi phí lưu trữ. Khóa limiter nên dựa trên danh tính đã xác thực hoặc giá trị IP đã được gateway chuẩn hóa.

### 4.4. Java nên gọi một hợp đồng rate limiter rõ ràng

Phần ứng dụng nên phụ thuộc vào một giao diện để có thể thay implementation theo môi trường. Ví dụ sau minh họa cách handler nhận quyết định từ một limiter dùng chung. Phần lưu token và phép consume nguyên tử được triển khai bởi adapter cho Redis hoặc dịch vụ quota; không thay bằng counter static khi chạy nhiều instance.

~~~java
public interface RateLimiter {
    LimitDecision consume(String key, int cost);
}

public record LimitDecision(
        boolean allowed,
        long remaining,
        long retryAfterSeconds
) {}

public Response handle(Request request) {
    Principal principal = authenticate(request);
    authorize(principal, request);

    String key = "tenant:" + principal.tenantId() + ":reports";
    LimitDecision decision = rateLimiter.consume(key, 1);

    if (!decision.allowed()) {
        return Response.status(429)
                .header("Retry-After",
                        Long.toString(Math.max(1, decision.retryAfterSeconds())))
                .header("Cache-Control", "no-store")
                .body("Rate limit exceeded")
                .build();
    }

    return createReport(request);
}
~~~

Đây là cấu trúc minh họa; kiểu Request, Response và Principal tùy framework. Trong triển khai thật, limiter cần xác định policy theo endpoint, xử lý lỗi store và cung cấp metric. Không gọi thao tác tạo báo cáo trước khi quyết định rate limit được chấp nhận.

Nếu thao tác có nhiều mức chi phí, truyền cost tương ứng. Ví dụ đọc metadata có cost 1, tìm kiếm phức tạp có cost 5 và tạo báo cáo lớn có cost 20. Việc định giá cost cần dựa trên đo đạc tài nguyên và được công bố rõ trong chính sách API nếu ảnh hưởng đến người dùng.

## 5. Xử lý request vượt giới hạn

Khi client vượt rate limit, HTTP 429 Too Many Requests là phản hồi phù hợp. Có thể gửi header Retry-After để chỉ thời gian tối thiểu trước khi thử lại. Nếu có thể, cung cấp thêm thông tin về giới hạn, số lượng còn lại và thời điểm reset theo hợp đồng API đã công bố.

Ví dụ:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
Cache-Control: no-store
Content-Type: application/json

{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Retry later."
}
~~~

Không nên trả 500 cho request bị giới hạn có chủ đích. 401 phù hợp khi thiếu hoặc sai thông tin xác thực; 403 khi danh tính hợp lệ nhưng không có quyền; 413 khi payload quá lớn; 429 khi vượt chính sách lưu lượng; 503 khi dịch vụ tạm thời không thể phục vụ do quá tải hoặc lỗi phụ thuộc.

Client nên tôn trọng Retry-After, dùng exponential backoff có jitter và giới hạn số lần retry. Nếu mọi client đều retry đúng cùng một thời điểm, chúng có thể tạo một đợt tải mới ngay khi limiter mở lại. Với request không idempotent, retry cần idempotency key hoặc cơ chế tra cứu kết quả trước khi gửi lại.

Không trả thời gian reset hoặc thông tin nội bộ nhạy cảm nếu nó giúp attacker suy ra cấu trúc hạ tầng. Nội dung lỗi nên đủ để client xử lý nhưng không tiết lộ policy nội bộ chi tiết.

## 6. Quota theo ngày, tháng và tenant

Quota thường biểu diễn tổng lượng sử dụng trong một kỳ. Ví dụ, tenant có thể có giới hạn số request, số báo cáo, số phút xử lý hoặc số byte truyền trong tháng.

Một bộ quota nên xác định rõ:

- Chủ thể: user, tenant, API client hay tài khoản thanh toán.
- Chỉ số: request, tác vụ, byte, thời gian xử lý hoặc đơn vị nghiệp vụ.
- Chu kỳ: phút, giờ, ngày, tháng hoặc chu kỳ hợp đồng.
- Thời điểm reset: múi giờ UTC hay timezone hợp đồng.
- Hành vi khi hết quota: từ chối, yêu cầu nâng cấp hoặc chờ kỳ tiếp theo.
- Cách tính request lỗi, request retry và thao tác bị hủy.

Quota theo tháng không nên được triển khai chỉ bằng một bộ đếm trong memory. Cần lưu bền vững và cập nhật nguyên tử. Nếu việc tiêu thụ quota gắn với một giao dịch nghiệp vụ, hãy thiết kế transaction hoặc ledger để tránh trừ quota hai lần khi request được retry.

Có thể tách quota cứng và quota cảnh báo. Quota cứng chặn thao tác khi đã hết mức được cấp. Ngưỡng cảnh báo như 70%, 85% hoặc 95% giúp chủ tenant và vận hành nhận biết sớm. Các tỷ lệ chỉ là ví dụ; chọn ngưỡng theo thời gian cần để nâng hạn mức hoặc xử lý sự cố.

Nếu quota được đồng bộ qua nhiều vùng, cần xác định mức nhất quán. Replication trễ có thể khiến hai region cùng cho phép request vượt tổng quota. Với giới hạn cứng, có thể phân bổ ngân sách theo vùng hoặc dùng một bộ điều phối nhất quán; đánh đổi là độ trễ và khả năng phục vụ khi vùng điều phối gặp sự cố.

## 7. Bảo vệ endpoint công khai theo nhiều lớp

Rate limiting là một lớp bảo vệ. Endpoint công khai còn cần các biện pháp sau.

### 7.1. TLS, xác thực và phân quyền

- Chỉ phục vụ qua HTTPS.
- Xác minh token theo issuer, audience, chữ ký, thời hạn và thuật toán được cho phép.
- Kiểm tra quyền trên từng tài nguyên, không chỉ kiểm tra người dùng đã đăng nhập.
- Không tin tenant ID, role hoặc user ID do client gửi nếu không được suy ra từ danh tính đã xác minh.
- Hạn chế quyền của service account theo nguyên tắc least privilege.
- Xoay vòng secret và thu hồi credential bị lộ.

CORS chỉ là chính sách cho trình duyệt quyết định trang web nào được đọc response. CORS không xác thực caller và không ngăn được curl, bot hoặc server khác gọi endpoint. Không dùng CORS thay cho authorization.

### 7.2. Kiểm tra đầu vào và giới hạn tài nguyên

- Giới hạn body size, số phần tử, độ sâu JSON và độ dài chuỗi.
- Kiểm tra kiểu dữ liệu, miền giá trị và định dạng trước khi gọi dịch vụ phía sau.
- Dùng allowlist cho giá trị như sort field, filter hoặc tên operation.
- Đặt connect timeout, read timeout và tổng deadline.
- Giới hạn số thread, connection pool, batch size và tác vụ đồng thời.
- Không cho client tùy ý quyết định URL mà function sẽ gọi nếu điều đó có thể tạo SSRF.
- Không ghi token, secret, thông tin thanh toán hoặc toàn bộ payload nhạy cảm vào log.

Validate dữ liệu ở tầng function vẫn cần thiết dù gateway đã có schema validation, vì không phải mọi trigger đều đi qua cùng một gateway và client có thể bỏ qua lớp UI.

### 7.3. WAF, bot và nguồn lưu lượng

WAF hoặc lớp bảo vệ edge có thể chặn mẫu tấn công phổ biến, request có dấu hiệu tự động hóa hoặc lưu lượng bất thường trước khi function được gọi. Quy tắc IP allowlist hữu ích cho webhook từ đối tác có dải IP ổn định, nhưng IP có thể thay đổi và không chứng minh nội dung request là hợp lệ. Hãy kết hợp IP filtering với xác minh chữ ký và xác thực.

Khi endpoint đứng sau proxy, chỉ tin các header như X-Forwarded-For hoặc Forwarded nếu chúng được ghi bởi proxy đáng tin cậy và gateway đã loại bỏ giá trị client tự chèn. Nếu đọc trực tiếp header do client kiểm soát để xác định IP, attacker có thể giả mạo địa chỉ và né limiter.

### 7.4. Giới hạn concurrency và bảo vệ dịch vụ phía sau

Rate limit ở gateway không thay thế giới hạn concurrency. Một function có thể nhận lượng request vừa phải nhưng mỗi invocation chậm vì database hoặc API ngoài. Khi đó, số invocation đồng thời tăng và gây cạn connection.

Cần giới hạn concurrency ở function hoặc nền tảng, giới hạn pool ở Java và áp dụng backpressure. Nếu database chỉ chịu được một mức kết nối nhất định, tổng concurrency của tất cả function phải nằm trong khả năng đó. Có thể dùng connection proxy/pooler phù hợp, queue cho công việc nền hoặc từ chối sớm khi hệ thống quá tải.

Không để retry khuếch đại sự cố. Khi dependency lỗi, retry đồng loạt từ nhiều function có thể tạo retry storm. Dùng exponential backoff, jitter, retry budget, circuit breaker và timeout ngắn hơn deadline tổng.

## 8. Bảo vệ webhook

Webhook là HTTP request do một hệ thống khác gửi đến khi có sự kiện. Endpoint nhận webhook thường công khai và có thể nhận retry, duplicate hoặc request giả mạo.

Một quy trình tiếp nhận an toàn:

1. Nhận raw request body và metadata cần thiết.
2. Xác minh chữ ký HMAC hoặc cơ chế chữ ký mà nhà cung cấp quy định trên đúng bytes được ký.
3. Kiểm tra timestamp hoặc nonce để giảm nguy cơ replay.
4. Xác định event ID và kiểm tra idempotency.
5. Ghi event vào nơi lưu bền vững hoặc queue.
6. Chỉ trả 2xx sau khi đã tiếp nhận bền vững theo hợp đồng của webhook.
7. Xử lý nghiệp vụ bất đồng bộ và có retry riêng.

Không parse JSON rồi serialize lại trước khi xác minh chữ ký nếu nhà cung cấp ký trên raw body. Khoảng trắng, thứ tự field hoặc encoding có thể thay đổi khiến chữ ký không còn khớp.

Ví dụ Java dưới đây minh họa HMAC-SHA256 với chữ ký dạng hex và dùng HexFormat có từ Java 17. Định dạng thực tế phải theo tài liệu của nhà cung cấp. Timestamp được ghép vào dữ liệu ký để chữ ký ràng buộc với thời điểm; ứng dụng vẫn phải tự kiểm tra timestamp nằm trong khoảng chấp nhận.

~~~java
static boolean verifyWebhook(
        byte[] rawBody,
        String timestamp,
        String signatureHex,
        byte[] secret) throws GeneralSecurityException {

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(new SecretKeySpec(secret, "HmacSHA256"));

    mac.update(timestamp.getBytes(StandardCharsets.UTF_8));
    mac.update((byte) '.');
    byte[] expected = mac.doFinal(rawBody);

    final byte[] supplied;
    try {
        supplied = HexFormat.of().parseHex(signatureHex);
    } catch (IllegalArgumentException invalidHex) {
        return false;
    }

    return MessageDigest.isEqual(expected, supplied);
}
~~~

Cần kiểm tra timestamp trước hoặc sau bước xác minh theo giao thức đã chọn, giới hạn độ lệch thời gian và từ chối timestamp quá cũ hoặc quá xa trong tương lai. Không dùng timestamp đơn lẻ làm chống replay nếu event có thể được gửi lại trong cửa sổ thời gian. Lưu event ID hoặc nonce đã xử lý trong kho bền vững với TTL phù hợp.

So sánh chữ ký bằng hàm constant-time như MessageDigest.isEqual thay vì so sánh chuỗi thông thường. Secret phải được lấy từ secret manager hoặc cấu hình bảo mật, không hardcode trong source code. Hỗ trợ key rotation bằng cách chấp nhận key hiện tại và key cũ trong một khoảng chuyển tiếp có giới hạn.

Webhook sender thường retry khi không nhận 2xx hoặc timeout. Receiver cần idempotent: cùng một event ID chỉ tạo hiệu ứng nghiệp vụ một lần. Có thể dùng unique constraint trên event ID hoặc bảng inbox. Nếu xử lý lâu, lưu event bền vững rồi trả 202 Accepted; worker xử lý sau. Không trả 2xx trước khi event đã được lưu ở nơi có thể khôi phục, nếu không sender sẽ ngừng retry trong khi hệ thống đã làm mất event.

## 9. Chính sách khi rate limiter hoặc kho trạng thái gặp lỗi

Rate limiter phân tán là một dependency. Khi nó lỗi, hệ thống phải có chính sách rõ ràng:

- **Fail closed:** từ chối request nếu không xác minh được quota. Phù hợp với thao tác có rủi ro cao hoặc quota là yêu cầu bắt buộc.
- **Fail open có giới hạn:** cho phép một phần request khi limiter lỗi để giữ tính sẵn sàng, nhưng cần global concurrency cap, giới hạn tạm thời ở edge và cảnh báo.
- **Fallback:** dùng giới hạn cục bộ thấp hơn trong thời gian ngắn, hiểu rằng tổng giới hạn có thể bị vượt khi có nhiều instance.

Không có lựa chọn mặc định đúng cho mọi API. Đăng nhập, gửi OTP, thanh toán hoặc thao tác tiêu thụ tài nguyên đắt tiền thường cần chính sách chặt. Endpoint đọc dữ liệu công khai có thể ưu tiên availability hơn, nếu có lớp bảo vệ khác.

Không nên âm thầm bỏ qua limiter khi timeout. Ghi metric về lỗi store, quyết định fallback, số request được cho phép trong chế độ suy giảm và thời gian phục hồi. Đặt timeout ngắn cho lời gọi limiter để dependency lỗi không làm cạn toàn bộ concurrency của function.

## 10. Quan sát và vận hành

Các metric nên theo dõi gồm:

- Request count và request rate theo route, tenant và status code.
- Số response 429, 401, 403, 413 và 5xx.
- Tỷ lệ request bị WAF chặn.
- Số token còn lại hoặc mức quota đã dùng.
- Số lần limiter store timeout, error và fallback.
- Function concurrency, throttling, duration p95/p99 và timeout.
- Connection pool usage, database latency và dependency error rate.
- Số webhook duplicate, signature failure, replay rejection và retry.
- Chi phí theo tenant hoặc API client nếu mô hình tính phí yêu cầu.

Log nên có request ID, tenant ID đã xác thực, route, quyết định limiter và mã lý do. Tránh log API key, bearer token, webhook secret hoặc chữ ký đầy đủ. Nếu cần điều tra credential, log fingerprint hoặc một định danh không thể dùng lại làm credential.

Tạo dashboard để phân biệt lưu lượng bình thường, tăng đột biến và tấn công. Một tỷ lệ 429 cao có thể cho thấy limiter đang hoạt động, nhưng cũng có thể chỉ ra policy quá chặt hoặc client retry sai. Kết hợp metric với phản hồi người dùng và phân tích theo tenant.

## 11. Kiểm thử rate limit và bảo vệ endpoint

Kiểm thử cần mô phỏng cả tải bình thường lẫn hành vi bất thường:

1. Gửi request ở mức dưới ngưỡng, đúng ngưỡng và vượt ngưỡng.
2. Gửi burst tại ranh giới fixed window để tìm hiện tượng dồn.
3. Gửi đồng thời từ nhiều function instance để kiểm tra thao tác consume có nguyên tử.
4. Dùng nhiều IP nhưng cùng tenant, và nhiều tenant qua cùng NAT.
5. Thử request không xác thực, token hết hạn, token sai audience và tenant không có quyền.
6. Thử body quá lớn, JSON lồng sâu, field quá dài và content type không hợp lệ.
7. Thử limiter store timeout, mất kết nối và phục hồi.
8. Thử dependency chậm để xác minh concurrency cap và backpressure.
9. Gửi webhook có chữ ký sai, timestamp cũ, event ID trùng và body bị thay đổi.
10. Kiểm tra retry của webhook khi receiver trả 5xx hoặc timeout.
11. Xác minh 429 có Retry-After và client tuân thủ backoff.
12. Theo dõi chi phí khi tăng request rate và khi function bị throttled.

Load test phải có giới hạn và được thực hiện trong môi trường được phép. Dùng dữ liệu thử nghiệm và kiểm soát concurrency để tránh vô tình tạo tải lên dịch vụ production hoặc đối tác bên ngoài.

## 12. Quy trình thiết kế policy

Có thể áp dụng quy trình sau cho một endpoint mới:

1. **Phân loại nghiệp vụ.** Xác định endpoint công khai hay nội bộ, dữ liệu nhạy cảm, chi phí mỗi request và tác động nếu bị lạm dụng.
2. **Xác định danh tính.** Chọn cách xác thực, nguồn tenant ID đáng tin cậy và quy tắc authorization.
3. **Đo workload.** Đo duration, CPU, memory, số kết nối và tải lên dependency để ước lượng năng lực.
4. **Đặt giới hạn nhiều lớp.** Cấu hình edge rate/burst, tenant quota, concurrency, payload size và timeout.
5. **Chọn thuật toán và kho trạng thái.** Xác định fixed/sliding window hoặc token bucket; bảo đảm cập nhật nguyên tử khi chạy nhiều instance.
6. **Thiết kế phản hồi.** Quy định status code, Retry-After, lỗi quota và cách client retry.
7. **Thiết kế suy giảm.** Chọn fail open, fail closed hoặc fallback khi limiter/dependency lỗi.
8. **Kiểm thử và quan sát.** Chạy thử burst, concurrency, duplicate, replay và lỗi phụ thuộc; tạo dashboard và cảnh báo.

Một endpoint công khai an toàn không chỉ có một con số request/giây. Nó cần policy rõ theo danh tính và nghiệp vụ, cơ chế thực thi nhất quán trên nhiều instance, giới hạn concurrency để bảo vệ dependency, và quy trình xử lý retry có thể dự đoán.

## 13. Câu hỏi tự kiểm tra

- Rate limit khác concurrency limit và quota theo tháng như thế nào?
- Vì sao counter static trong Java không đủ để giới hạn toàn bộ function khi scale out?
- Token bucket kiểm soát tốc độ trung bình và burst bằng những tham số nào?
- Vì sao API key không thay thế xác thực và phân quyền?
- HTTP 429 nên đi kèm thông tin gì để client retry đúng cách?
- Vì sao cần giới hạn cả ở API gateway lẫn tầng ứng dụng?
- CORS có ngăn được client ngoài trình duyệt gọi endpoint không?
- Vì sao webhook cần xác minh chữ ký trên raw body và chống replay?
- Khi rate limiter store lỗi, fail open và fail closed có đánh đổi gì?
- Làm thế nào để một webhook được giao lại nhiều lần mà không tạo hiệu ứng nghiệp vụ trùng?

Nắm được rate limiting, quota và bảo vệ endpoint giúp người phát triển Java serverless kiểm soát lưu lượng từ lúc request đi vào edge cho đến khi function gọi dịch vụ phía sau. Các giới hạn nên được đo bằng workload thực tế, gắn với danh tính đáng tin cậy và kiểm thử trong điều kiện nhiều invocation chạy đồng thời.

