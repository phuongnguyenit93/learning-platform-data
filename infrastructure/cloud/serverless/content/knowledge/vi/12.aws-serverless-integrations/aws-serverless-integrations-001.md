# Xây dựng HTTP endpoint bằng API Gateway và Lambda Function URL

AWS Lambda có thể xử lý HTTP request thông qua API Gateway hoặc thông qua Lambda Function URL. Cả hai cách đều cho phép gọi Java function bằng HTTPS và nhận response, nhưng chúng cung cấp những lớp quản lý API khác nhau.

API Gateway phù hợp khi endpoint cần routing, xác thực tập trung, throttling, quản lý phiên bản/stage, custom domain hoặc nhiều API operation. Lambda Function URL phù hợp với endpoint đơn giản gắn trực tiếp vào một function, chẳng hạn webhook hoặc một HTTP handler nhỏ, khi các yêu cầu quản lý API ở mức cơ bản.

Để chọn đúng, cần hiểu request đi vào Lambda như thế nào, event payload được biểu diễn ra sao, ai có quyền invoke function, và giới hạn của từng lớp trong đường đi HTTP.

## 1. Kiến trúc tổng quan

Một HTTP request đến Java Lambda có thể đi qua một trong hai đường chính.

~~~mermaid
flowchart TD
    C["HTTP client / browser / partner"] --> D{"Chọn endpoint"}
    D -->|API Gateway| G["API Gateway route và authorizer"]
    G --> L["AWS Lambda Java function"]
    D -->|Function URL| U["Lambda Function URL"]
    U --> L
    L --> S["Database / queue / dịch vụ AWS"]
    L --> R["HTTP response"]
    R --> C
~~~

Với API Gateway, gateway nhận request, áp dụng các chính sách ở tầng API rồi chuyển request đến Lambda. Lambda xử lý và trả kết quả theo giao thức tích hợp. Gateway chuyển kết quả đó thành HTTP response cho client.

Với Function URL, AWS cung cấp một HTTPS endpoint gắn trực tiếp với Lambda function hoặc alias. Request được chuyển đến function theo payload format HTTP v2.0. Function tự xử lý routing và nghiệp vụ, còn một số chính sách như xác thực ứng dụng, kiểm tra dữ liệu hoặc giới hạn theo tenant có thể cần triển khai ở Lambda hoặc một lớp đứng trước.

Cả hai mô hình đều là request/response đồng bộ. Nếu tác vụ mất nhiều thời gian hoặc không phù hợp với thời gian chờ HTTP, endpoint nên ghi nhận job, phát message vào queue hoặc khởi chạy workflow rồi trả mã tiếp nhận để client tra cứu sau.

## 2. API Gateway và Lambda Function URL khác nhau thế nào?

| Tiêu chí | API Gateway | Lambda Function URL |
|---|---|---|
| Điểm vào | API endpoint quản lý tập trung | URL HTTPS được tạo cho Lambda |
| Routing | Có route, method và stage | Function thường tự kiểm tra path và method |
| Xác thực | Có thể dùng IAM, JWT authorizer, Lambda authorizer và các cơ chế tùy loại API | Chọn AWS_IAM hoặc NONE; xác thực nghiệp vụ bổ sung ở ứng dụng hoặc lớp đứng trước |
| Throttling | Có chính sách throttling ở tầng API | Chủ yếu dựa vào Lambda concurrency và lớp bảo vệ bổ sung |
| Quản lý API | Có stage, deployment, custom domain, access log và tích hợp API | Tối giản, gắn trực tiếp với function |
| CORS | Có thể cấu hình ở API Gateway | Có cấu hình CORS cho Function URL |
| API key và usage plan | Có trên REST API; kiểm tra tính năng theo loại API | Không có usage plan/API key management tương đương tích hợp sẵn |
| Phù hợp | API có nhiều route, nhiều client hoặc yêu cầu quản trị | Webhook hoặc endpoint nhỏ, ít yêu cầu quản lý tập trung |

Không phải mọi tính năng của API Gateway đều có trên mọi loại API. API Gateway có REST API và HTTP API với tập tính năng khác nhau. HTTP API thường phù hợp cho API HTTP đơn giản, cần routing và JWT/Lambda authorizer. REST API có thêm một số tính năng quản lý như usage plan/API key, caching, request validation và các tích hợp nâng cao. Hãy đối chiếu tính năng cần dùng với loại API và tài liệu AWS hiện hành trước khi chọn.

### 2.1. Khi nào chọn API Gateway?

Chọn API Gateway khi cần một lớp quản lý API độc lập với function:

- Nhiều route như GET /orders, POST /orders và GET /orders/{id}.
- Nhiều Lambda function hoặc dịch vụ phía sau cùng một API.
- Xác thực JWT hoặc Lambda authorizer dùng chung.
- Throttling theo route hoặc API stage.
- Custom domain, stage dev/test/prod và access logging.
- Quản lý API key/usage plan hoặc tính năng chỉ có ở REST API.
- Tách vòng đời public API khỏi vòng đời triển khai Lambda.

API Gateway cũng giúp function tập trung vào nghiệp vụ thay vì tự xây dựng toàn bộ lớp HTTP. Tuy vậy, cần quản lý timeout và payload limit của cả gateway lẫn Lambda.

### 2.2. Khi nào chọn Function URL?

Function URL phù hợp khi:

- Chỉ cần một endpoint gắn trực tiếp với một function.
- Muốn giảm thành phần phải cấu hình và vận hành.
- Endpoint phục vụ webhook hoặc tích hợp đơn giản.
- Caller có thể dùng AWS IAM/SigV4, hoặc ứng dụng có cơ chế xác thực riêng.
- Không cần các tính năng API management nâng cao của API Gateway.

Function URL không tự tạo hệ thống user authentication, quota theo tenant, API key management hay routing nhiều dịch vụ. Nếu cần các chức năng đó, hãy đặt thêm lớp phù hợp hoặc dùng API Gateway.

Một Function URL có thể đứng sau CloudFront hoặc một lớp edge khác nếu cần domain, caching hay chính sách bảo vệ bổ sung. Khi đó phải cấu hình origin access, header chuyển tiếp và quyền invoke sao cho client không thể bỏ qua lớp edge để gọi trực tiếp URL gốc ngoài ý muốn.

## 3. Chọn HTTP API hay REST API trong API Gateway

API Gateway cung cấp nhiều loại API. Với HTTP endpoint gọi Lambda, hai lựa chọn thường được cân nhắc là HTTP API và REST API.

| Nhu cầu | HTTP API | REST API |
|---|---|---|
| HTTP routing và Lambda proxy integration | Có | Có |
| JWT authorizer tích hợp | Có | Có thể dùng các cơ chế authorizer khác, gồm Cognito/Lambda/IAM theo cấu hình |
| Lambda authorizer | Có | Có |
| CORS | Có | Có |
| Stage và custom domain | Có | Có |
| API key và usage plan | Không có tính năng tương đương REST API | Có |
| API caching | Không | Có |
| Request validation tích hợp | Hạn chế hơn; thường validate ở Lambda | Có cấu hình request validation |
| Các tính năng quản lý API nâng cao | Tập trung vào HTTP API đơn giản | Nhiều lựa chọn hơn |

HTTP API thường là điểm bắt đầu tốt cho một API HTTP mới nếu các tính năng của nó đáp ứng yêu cầu. REST API phù hợp khi cần những khả năng quản lý cụ thể chỉ có ở loại này. Đừng chọn chỉ dựa vào tên “REST” hay “HTTP”; hãy lập danh sách tính năng bắt buộc và kiểm tra đúng loại API.

## 4. Luồng request và Lambda proxy integration

Với Lambda proxy integration, API Gateway chuyển thông tin request thành một event JSON cho Lambda. Event thường chứa:

- HTTP method và path.
- Query string và path parameters.
- Headers và cookies.
- Request body.
- Thông tin request context như request ID, source IP, identity hoặc authorizer context.
- Cờ cho biết body có được mã hóa Base64 hay không.

Lambda trả về status code, headers và body. API Gateway dùng response này để tạo HTTP response gửi cho client.

Với HTTP API payload format 2.0, một số trường có cấu trúc như rawPath, rawQueryString, cookies và requestContext.http. Lambda Function URL cũng sử dụng payload format 2.0. Vì vậy, Java handler dùng event type HTTP API v2 có thể dùng chung cho hai kiểu endpoint trong nhiều trường hợp, miễn là ứng dụng không phụ thuộc vào trường context chỉ có ở một loại tích hợp.

Không nên giả định event của API Gateway REST API v1 và HTTP API/Function URL v2 có cùng cấu trúc. REST API proxy integration thường dùng payload format 1.0 với tên trường và cách biểu diễn khác. Chọn đúng event class và response class theo payload format đã cấu hình.

## 5. Java handler cho HTTP API payload v2.0

AWS Lambda Java Events cung cấp các kiểu event cho API Gateway HTTP API v2.0 và Function URL. Ví dụ dưới đây minh họa một handler nhận event v2 và trả response JSON.

Ví dụ dùng Java 17 và thư viện AWS Lambda Java Core cùng AWS Lambda Java Events. Hãy chọn phiên bản dependency tương thích với JDK và build tool của dự án.

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.APIGatewayV2HTTPEvent;
import com.amazonaws.services.lambda.runtime.events.APIGatewayV2HTTPResponse;

import java.util.Map;

public class HttpHandler
        implements RequestHandler<APIGatewayV2HTTPEvent, APIGatewayV2HTTPResponse> {

    @Override
    public APIGatewayV2HTTPResponse handleRequest(
            APIGatewayV2HTTPEvent event,
            Context context) {

        String method = event.getRequestContext().getHttp().getMethod();
        String path = event.getRawPath();

        if ("GET".equals(method) && "/health".equals(path)) {
            return response(200, "{\"status\":\"ok\"}");
        }

        if (!"GET".equals(method)) {
            return response(405, "{\"error\":\"method_not_allowed\"}");
        }

        return response(404, "{\"error\":\"not_found\"}");
    }

    private static APIGatewayV2HTTPResponse response(
            int statusCode,
            String body) {

        return APIGatewayV2HTTPResponse.builder()
                .withStatusCode(statusCode)
                .withHeaders(Map.of(
                        "content-type", "application/json; charset=utf-8",
                        "cache-control", "no-store"
                ))
                .withBody(body)
                .build();
    }
}
~~~

Trong ví dụ, handler chỉ hỗ trợ GET /health. Một API thực tế cần thêm router hoặc framework phù hợp, validate input, xử lý lỗi tập trung và không trả stack trace ra client.

Nếu dùng API Gateway REST API payload v1.0, hãy dùng event/response type tương ứng, chẳng hạn APIGatewayProxyRequestEvent và APIGatewayProxyResponseEvent. Đừng ép event v1 vào class v2 hoặc ngược lại.

### 5.1. Cấu hình handler và đóng gói

Lambda cần biết handler class và runtime Java được chọn. Với custom runtime hoặc native executable, cách nhận event và trả response sẽ khác với Java managed runtime thông thường. Hãy dùng AWS Lambda Java runtime interface và adapter được hỗ trợ cho mô hình triển khai.

Một dự án Java thường cần các thư viện:

- AWS Lambda Java Core để triển khai RequestHandler.
- AWS Lambda Java Events để dùng event/response type có sẵn.
- Thư viện JSON nếu cần parse/serialize payload.
- AWS SDK v2 nếu function gọi các dịch vụ AWS.

Đóng gói artifact đúng định dạng mà runtime yêu cầu, cấu hình handler class đầy đủ package, và kiểm tra JAR hoặc deployment package có chứa dependency cần thiết. Nếu dùng Maven Shade hoặc Gradle Shadow, kiểm tra service metadata và resource sau khi đóng gói.

## 6. Đọc request body và xử lý dữ liệu an toàn

HTTP event có thể mang body dạng chuỗi. Với body nhị phân hoặc một số kiểu tích hợp, body có thể được mã hóa Base64. Ứng dụng phải kiểm tra cờ encoding trước khi giải mã.

Các nguyên tắc quan trọng:

- Kiểm tra Content-Type và kích thước body.
- Parse JSON bằng thư viện có giới hạn phù hợp.
- Validate field bắt buộc, kiểu dữ liệu, độ dài và miền giá trị.
- Không tin các header do client tự khai báo như tenant ID, role hoặc user ID.
- Không ghi toàn bộ body vào log nếu có thông tin nhạy cảm.
- Trả 400 cho dữ liệu sai định dạng, 413 khi vượt giới hạn payload và 415 khi media type không được hỗ trợ.
- Đặt giới hạn ở gateway và ứng dụng; kiểm tra giới hạn payload thực tế của cả gateway và Lambda.

Đối với request có file lớn, nên tải file lên S3 bằng URL được cấp quyền có thời hạn rồi gửi object key trong request. Không nên chuyển toàn bộ file lớn qua API Gateway và Lambda nếu không cần thiết.

## 7. Routing, path parameter và query string

API Gateway có thể định nghĩa route rõ ràng như:

~~~text
GET    /health
POST   /orders
GET    /orders/{orderId}
DELETE /orders/{orderId}
~~~

Mỗi route có thể được nối với Lambda integration tương ứng. Có thể dùng một function cho nhiều route hoặc tách function theo bounded context, mức quyền và tải. Một function lớn có nhiều route giúp giảm số deployment nhưng có thể khiến quyền IAM, concurrency và scale của các route gắn chặt với nhau.

Với Function URL, URL được gắn trực tiếp vào function; handler hoặc framework trong function cần tự phân biệt method và path. Nếu cần nhiều route hoặc nhiều backend, có thể dùng router trong ứng dụng, CloudFront/API Gateway ở phía trước hoặc tách endpoint theo function.

Query string cần được parse đúng chuẩn URL encoding. Không tự nối chuỗi để tạo SQL, shell command hoặc URL đích. Path parameter cần được validate và encode khi dùng trong truy vấn hoặc log.

## 8. CORS và preflight request

CORS là cơ chế trình duyệt kiểm soát trang web nào được phép đọc response từ một origin khác. Nó không phải cơ chế xác thực người dùng và không chặn được client ngoài trình duyệt như curl hoặc server-to-server caller.

Nếu frontend ở một origin khác gọi API, cần cấu hình:

- Allowed origins: chỉ các origin thực sự được phép.
- Allowed methods: các method frontend cần.
- Allowed headers: Authorization, Content-Type hoặc header nghiệp vụ cần thiết.
- Exposed headers: các header frontend cần đọc như request ID hoặc rate-limit metadata.
- Credentials: chỉ bật khi thật sự cần cookie hoặc credential trình duyệt.

Browser có thể gửi OPTIONS preflight trước request thật. API Gateway hoặc Function URL có thể được cấu hình xử lý CORS. Nếu gateway đã quản lý CORS, tránh để Lambda trả các header xung đột. Với origin động, chỉ phản hồi origin đã được allowlist; không phản chiếu bất kỳ Origin nào mà client gửi.

Không kết hợp wildcard origin với credentialed requests. Nếu cần cookies, cấu hình origin cụ thể, credentials và các thuộc tính cookie phù hợp như Secure, HttpOnly và SameSite.

## 9. Xác thực và quyền invoke

### 9.1. API Gateway

API Gateway có thể kiểm tra caller trước khi gọi Lambda:

- IAM authorization cho caller dùng AWS Signature Version 4.
- JWT authorizer cho access token từ identity provider tương thích.
- Lambda authorizer để áp dụng logic xác thực hoặc authorization riêng.
- Các cơ chế tích hợp khác tùy loại API và cấu hình.

Sau khi xác thực, vẫn cần kiểm tra quyền trên tài nguyên và tenant trong ứng dụng. Một token hợp lệ không có nghĩa caller được phép đọc mọi order hoặc thực hiện mọi thao tác.

API Gateway cần quyền invoke Lambda integration. Thường dùng resource-based policy trên function để cho phép service principal của API Gateway invoke đúng function, giới hạn theo API, account, stage hoặc source ARN phù hợp. Không cấp quyền rộng hơn nhu cầu.

### 9.2. Lambda Function URL

Function URL có hai chế độ xác thực tích hợp:

- **AWS_IAM:** caller phải ký request bằng SigV4 và có IAM permission cần thiết để invoke URL.
- **NONE:** không yêu cầu IAM authentication ở lớp Function URL; endpoint có thể được gọi bởi bất kỳ client nào có thể truy cập URL nếu resource policy cho phép.

NONE không có nghĩa là ứng dụng đã được bảo vệ. Nếu dùng chế độ này cho webhook hoặc API công khai, handler phải xác minh chữ ký webhook, JWT/session hoặc credential nghiệp vụ phù hợp. Không xem URL khó đoán là cơ chế xác thực.

Với AWS_IAM, kiểm tra cả identity policy của caller và resource-based policy của Lambda. Với NONE, kiểm tra resource-based policy và phạm vi principal được phép invoke. Quyền cụ thể có thể phụ thuộc cấu hình Function URL và các thay đổi chính sách Lambda; hãy kiểm tra tài liệu IAM hiện hành khi triển khai.

### 9.3. Không nhầm CORS, API key và authentication

- CORS kiểm soát trình duyệt có được đọc response hay không.
- API key thường dùng để nhận diện client, đo usage hoặc áp dụng usage plan; không phải bằng chứng danh tính đủ mạnh cho dữ liệu nhạy cảm.
- Authentication xác định caller là ai.
- Authorization xác định caller được phép làm gì.
- Rate limiting và quota kiểm soát mức sử dụng.

Một endpoint an toàn thường cần phối hợp các cơ chế trên theo mức rủi ro của nghiệp vụ.

## 10. IAM least privilege và bảo vệ Lambda

Lambda execution role xác định function được phép làm gì khi chạy. Đây là quyền của code trong function, khác với quyền của client được phép gọi endpoint.

Ví dụ, một function tạo order có thể chỉ cần quyền ghi vào một bảng DynamoDB cụ thể và phát message vào một queue cụ thể. Không gắn policy AdministratorAccess hoặc quyền đọc toàn bộ S3 chỉ vì muốn triển khai nhanh.

Cần phân biệt ba loại quyền:

1. **Caller permission:** client hoặc service nào được gọi endpoint.
2. **Lambda resource policy:** principal nào được phép invoke function hoặc Function URL.
3. **Lambda execution role:** function được phép truy cập dịch vụ AWS nào khi đang chạy.

Một cấu hình sai ở một trong ba lớp có thể tạo lỗi 403/AccessDenied hoặc mở quyền quá rộng. Khi dùng API Gateway, giới hạn quyền invoke theo đúng API Gateway source ARN nếu có thể. Khi dùng Function URL, giới hạn principal và auth type theo thiết kế.

Không đưa AWS access key vào request body, query string hoặc biến môi trường nếu có thể dùng IAM role. Dùng execution role và secret manager/parameter store cho secret ứng dụng; giới hạn quyền đọc secret theo đúng function cần sử dụng.

## 11. Throttling, concurrency và timeout

API Gateway có thể áp dụng throttling để bảo vệ API. Lambda có concurrency limit riêng, gồm reserved concurrency và các giới hạn tài khoản/vùng. Hai lớp này bổ sung cho nhau:

- API Gateway throttling hạn chế tốc độ request đi vào API.
- Lambda concurrency giới hạn số invocation đang chạy.
- Connection pool và giới hạn của database bảo vệ dependency phía sau.
- Quota theo tenant cần trạng thái dùng chung hoặc dịch vụ quota riêng.

Một API có thể chưa vượt request rate nhưng vẫn làm Lambda đạt concurrency cao nếu mỗi invocation xử lý lâu. Ngược lại, concurrency thấp có thể làm request bị throttled dù rate trung bình nhỏ. Hãy tính cả thời gian xử lý và số request đồng thời.

Timeout của client, API Gateway và Lambda cần được đặt có quan hệ rõ ràng. Nếu Lambda chạy lâu hơn thời gian chờ của gateway hoặc client, caller có thể nhận timeout trong khi function vẫn đang thực hiện side effect. Điều này khiến caller retry và tạo thao tác trùng. Với tác vụ dài, dùng job ID, queue hoặc workflow để trả kết quả bất đồng bộ.

Không dùng retry vô hạn ở client. Với lỗi 429 hoặc 503, client nên tôn trọng Retry-After nếu có, dùng exponential backoff có jitter và idempotency key cho thao tác không idempotent.

## 12. HTTP response, status code và lỗi

Lambda proxy response thường chứa status code, headers và body. Hãy dùng status code đúng ngữ nghĩa:

| Status | Khi dùng |
|---|---|
| 200 OK | Request thành công và có kết quả |
| 201 Created | Đã tạo tài nguyên |
| 202 Accepted | Đã tiếp nhận công việc bất đồng bộ |
| 204 No Content | Thành công, không có body |
| 400 Bad Request | Request sai định dạng hoặc thiếu dữ liệu |
| 401 Unauthorized | Thiếu hoặc sai thông tin xác thực |
| 403 Forbidden | Caller không có quyền |
| 404 Not Found | Không tìm thấy route hoặc tài nguyên |
| 405 Method Not Allowed | Route không hỗ trợ method |
| 409 Conflict | Trạng thái hoặc idempotency conflict |
| 413 Payload Too Large | Body vượt giới hạn |
| 415 Unsupported Media Type | Content-Type không hỗ trợ |
| 429 Too Many Requests | Vượt rate limit hoặc quota |
| 500 Internal Server Error | Lỗi không dự kiến trong function |
| 502/503 | Lỗi tích hợp hoặc dịch vụ tạm thời không khả dụng, tùy lớp tạo response |

Không trả stack trace, SQL, ARN nội bộ hoặc secret trong response. Ghi chi tiết lỗi ở log có kiểm soát và trả error code ổn định cho client. Với API Gateway, lỗi có thể được tạo bởi gateway, authorizer hoặc Lambda; log và status cần giúp phân biệt nguồn lỗi.

## 13. Webhook qua API Gateway hoặc Function URL

Webhook là một trường hợp sử dụng phổ biến cho HTTP endpoint serverless. Nhà cung cấp bên ngoài gửi event đến endpoint khi có sự kiện như thanh toán, thay đổi trạng thái hoặc hoàn tất tác vụ.

Một handler webhook nên:

1. Đọc raw body đúng như nhà cung cấp gửi.
2. Xác minh chữ ký HMAC hoặc cơ chế xác thực của nhà cung cấp.
3. Kiểm tra timestamp/nonce nếu giao thức có hỗ trợ chống replay.
4. Kiểm tra event ID để chống xử lý trùng.
5. Lưu event bền vững hoặc ghi vào inbox/queue.
6. Trả 2xx sau khi đã tiếp nhận bền vững.
7. Xử lý nghiệp vụ qua worker nếu tác vụ dài.

Không parse JSON rồi serialize lại trước khi xác minh chữ ký nếu chữ ký được tính trên raw bytes. Thay đổi whitespace hoặc encoding có thể khiến chữ ký không khớp.

API Gateway hữu ích khi cần nhiều webhook route, xác thực tập trung hoặc throttling ở edge. Function URL phù hợp với webhook đơn giản nếu ứng dụng tự xác minh chữ ký và quản lý idempotency. Với webhook, endpoint công khai không nên phụ thuộc vào secret nằm trong URL; dùng header chữ ký và secret được quản lý an toàn.

## 14. Quan sát và truy vết request

Một request có thể đi qua API Gateway, authorizer, Lambda và nhiều dịch vụ AWS. Hãy tạo khả năng nối các log:

- API Gateway request ID.
- Lambda awsRequestId.
- Correlation ID do ứng dụng tạo hoặc nhận từ nguồn tin cậy.
- Route, method và status code.
- Thời gian gateway, thời gian khởi tạo và duration của Lambda.
- Authorizer result và lỗi xác thực, không ghi token.
- Dependency latency và lỗi downstream.
- Thông tin throttling, concurrency và retry.

API Gateway access logs giúp phân biệt lỗi ở gateway với lỗi trong Lambda. Lambda logs ghi chi tiết xử lý ở ứng dụng. CloudWatch metrics/alarms có thể theo dõi request count, latency, 4xx/5xx, Lambda errors, throttles, duration và concurrency. X-Ray hoặc tracing tương thích có thể giúp nối các đoạn gọi giữa dịch vụ.

Không ghi Authorization header, cookie, API key, chữ ký webhook hoặc payload nhạy cảm. Nếu cần điều tra, ghi fingerprint hoặc ID tham chiếu không thể dùng lại làm credential.

## 15. Triển khai và kiểm thử endpoint

Trước khi đưa endpoint ra Internet, cần kiểm thử cả đường đi thành công lẫn lỗi:

1. Gọi route hợp lệ bằng method đúng.
2. Gọi route không tồn tại và method không hỗ trợ.
3. Gửi query string, path parameter và body có encoding đặc biệt.
4. Gửi body sai JSON, body quá lớn và Content-Type không hỗ trợ.
5. Gọi thiếu token, token hết hạn và token có quyền không phù hợp.
6. Kiểm tra CORS preflight OPTIONS từ origin được phép và origin bị từ chối.
7. Gửi request vượt throttling và kiểm tra response 429.
8. Mô phỏng Lambda timeout và dependency chậm.
9. Gửi webhook có chữ ký sai, event ID trùng và timestamp cũ.
10. Kiểm tra caller không có quyền invoke Function URL hoặc API Gateway integration.
11. Xác minh Lambda execution role chỉ có quyền cần thiết.
12. Kiểm tra access log, Lambda log, correlation ID và cảnh báo.

Có thể dùng SAM, CDK, CloudFormation hoặc Terraform để quản lý API Gateway, Lambda, IAM policy, environment variables và log configuration dưới dạng code. Dù dùng công cụ nào, hãy quản lý thay đổi theo môi trường, tránh chỉnh tay production mà không có nguồn cấu hình tái lập.

Tách endpoint dev/test/prod bằng stage, alias hoặc stack riêng phù hợp kiến trúc. Không để dev endpoint có quyền truy cập dữ liệu production. Với Lambda alias, cấu hình API integration hoặc Function URL trỏ đến đúng alias/version theo chiến lược release. Kiểm tra rollback và quyền invoke sau mỗi lần deploy.

## 16. Quy trình chọn và xây dựng endpoint

1. **Xác định nhu cầu API.** Số route, client, xác thực, quota, domain và yêu cầu vận hành.
2. **Chọn API Gateway hay Function URL.** Nếu cần quản lý API tập trung, ưu tiên API Gateway; nếu endpoint đơn giản và ít tính năng quản trị, cân nhắc Function URL.
3. **Chọn loại API Gateway.** So sánh HTTP API và REST API theo tính năng bắt buộc.
4. **Chọn payload format.** Dùng event/response type phù hợp với v1.0 hoặc v2.0.
5. **Viết Java handler.** Validate method/path/body, xác thực caller và trả status/header/body đúng chuẩn.
6. **Cấu hình quyền.** Tách caller permission, Lambda resource policy và execution role.
7. **Đặt giới hạn.** Cấu hình payload size, timeout, throttling, concurrency và quota.
8. **Cấu hình CORS và domain.** Chỉ mở origin, method và header cần thiết.
9. **Thêm logging và tracing.** Dùng request ID và correlation ID, loại bỏ secret khỏi log.
10. **Kiểm thử và triển khai.** Kiểm tra quyền, lỗi, retry, webhook duplicate và rollback.

## 17. Câu hỏi tự kiểm tra

- API Gateway và Lambda Function URL khác nhau ở lớp quản lý API nào?
- Khi nào HTTP API phù hợp hơn REST API?
- Function URL có những chế độ xác thực tích hợp nào?
- Vì sao Function URL với AuthType NONE cần được bảo vệ ở tầng ứng dụng hoặc lớp đứng trước?
- Payload format 1.0 và 2.0 ảnh hưởng Java event class như thế nào?
- Vì sao CORS không thay thế authentication hoặc authorization?
- Caller permission, Lambda resource policy và execution role khác nhau ra sao?
- Vì sao timeout của gateway phải được xem cùng timeout của Lambda?
- Webhook cần xác minh chữ ký trên raw body và chống duplicate như thế nào?
- Những metric và log nào giúp tìm lỗi giữa API Gateway và Lambda?

API Gateway và Lambda Function URL đều có thể đưa Java Lambda ra HTTP, nhưng phục vụ các mức nhu cầu khác nhau. Hãy chọn theo yêu cầu routing, xác thực, throttling, quản lý API và vận hành; sau đó kiểm tra payload contract, IAM, timeout, CORS và idempotency để endpoint hoạt động an toàn khi có tải thật.

