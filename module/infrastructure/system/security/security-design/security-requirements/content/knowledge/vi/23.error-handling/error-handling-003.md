# Không lộ secret trong lỗi

## 1. Từ thông báo lỗi tới sự cố lộ thông tin xác thực

Một dịch vụ gọi nhà cung cấp thanh toán bằng API key. Khi request thất bại, thư viện client tạo exception chứa mô tả request và header. Ứng dụng đã ẩn stack trace khỏi response, nhưng vẫn trả `exception.getMessage()` cho frontend và gửi nguyên exception tới hệ thống theo dõi lỗi. API key có thể xuất hiện ở cả hai nơi.

Vấn đề ở đây không nằm riêng trong hình thức của stack trace. Secret đã đi từ nơi phục vụ xác thực sang các đầu ra có đối tượng nhận, quyền truy cập và thời gian lưu khác hẳn.

Trong chương Error handling, yêu cầu **không lộ secret trong lỗi** cần bảo vệ toàn bộ đường đi của dữ liệu khi thất bại: lúc tạo lỗi, ánh xạ lỗi, ghi log, thu telemetry, hiển thị cho người dùng và chuyển giao hồ sơ hỗ trợ.

Trong phạm vi module đặc tả yêu cầu bảo mật, mục tiêu là xây dựng được chuỗi:

```text
Secret và nơi sử dụng
    -> đường lỗi có thể mang secret
    -> đầu ra và người có thể nhận
    -> yêu cầu ngăn phát hành dữ liệu
    -> thiết kế xử lý lỗi
    -> ca kiểm thử và bằng chứng
    -> cách ứng phó nếu vẫn phát hiện lộ
```

Sau bài này, người học có thể phân loại dữ liệu cần bảo vệ, đặc tả hợp đồng lỗi không mang secret, nhận diện giới hạn của redaction và định nghĩa tiêu chí nghiệm thu có thể tái hiện.

## 2. Secret là gì trong ngữ cảnh xử lý lỗi?

Secret là dữ liệu mà việc nắm giữ hoặc biết giá trị có thể cho phép xác thực, ký, giải mã, khôi phục quyền truy cập hoặc thực hiện hành động được bảo vệ. Phải xác định theo khả năng sử dụng của dữ liệu, không chỉ theo tên field.

| Nhóm | Ví dụ | Hậu quả khi bị phát hành trái phép |
|---|---|---|
| Thông tin xác thực dài hạn | Password, API key, thông tin xác thực database | Truy cập hệ thống hoặc tài nguyên với quyền của chủ thể khác |
| Thông tin phiên | Session cookie, access token, refresh token | Chiếm hoặc kéo dài quyền của một phiên |
| Bí mật ngắn hạn | Mã dùng một lần, token đặt lại mật khẩu, mã xác nhận | Hoàn tất một bước xác thực hoặc khôi phục ngoài ý muốn |
| Khóa mật mã | Private key, khóa đối xứng, secret dùng ký webhook | Ký giả, giải mã hoặc giả mạo quan hệ tin cậy tùy trường hợp |
| Dữ liệu cấp quyền bằng việc sở hữu | URL có chữ ký, đường dẫn tải có token | Sử dụng quyền được gắn vào URL hoặc token |
| Chuỗi tổng hợp chứa secret | Connection string, object cấu hình, bản dump request | Làm lộ nhiều dữ liệu dù field ngoài cùng có tên bình thường |

Một public key hoặc mã sản phẩm công khai không trở thành secret chỉ vì có chuỗi ký tự dài. Ngược lại, một field tên `reference` vẫn là secret nếu ai có giá trị đó có thể đổi mật khẩu hoặc tải tài liệu riêng tư.

Dữ liệu cá nhân, thông tin nghiệp vụ và địa chỉ nội bộ cũng có thể cần bảo vệ, nhưng không phải tất cả đều là secret theo nghĩa xác thực hoặc cấp quyền. Phân loại tách biệt giúp đặt yêu cầu đúng; không dùng việc “không phải secret” để tự cho phép ghi log dữ liệu cá nhân.

### 2.1. Những giả định không đủ để cho phép phát hành

- **“Token sẽ hết hạn sớm.”** Người nhận vẫn có thể dùng trong khoảng còn hiệu lực; không nên dựa vào thời hạn ngắn để cho phép lộ.
- **“Đây là secret của chính người gọi.”** Response, lịch sử trình duyệt và hệ thống hỗ trợ có thể được chuyển tiếp tới người khác.
- **“Log chỉ ở nội bộ.”** Đối tượng truy cập log có thể rộng hơn nhiều so với đối tượng được dùng secret.
- **“Đã mã hóa transport.”** TLS không giới hạn việc bên nhận lưu, tìm kiếm hoặc chuyển tiếp giá trị đã nhận.
- **“Chỉ giữ vài ký tự cuối.”** Phần lộ có thể vẫn hỗ trợ đoán, đối chiếu hoặc liên kết; phải có mục đích và đánh giá riêng.
- **“Đã băm giá trị.”** Giá trị ít khả năng có thể bị dò; fingerprint ổn định cũng có thể tạo khả năng liên kết ngoài dự kiến.

Một secret đã bị thu hồi vẫn không nên được giữ tùy ý trong lịch sử lỗi. Nó có thể tiết lộ cấu trúc, quan hệ hoặc dữ liệu khác, và việc thu hồi không tự xóa các bản sao đã phát hành.

## 3. Lập mô hình nguồn, phép biến đổi và đầu ra

### 3.1. Nguồn không chỉ có request body

Secret có thể xuất phát từ:

- Header xác thực, cookie, query parameter hoặc path parameter.
- Payload đăng nhập, khôi phục tài khoản hoặc cấu hình kết nối.
- Secret được server đọc từ kho bí mật để gọi dependency.
- Cấu hình môi trường hoặc thông tin kết nối khi khởi động thất bại.
- URL có chữ ký được tạo trong quá trình nghiệp vụ.
- Response của upstream, callback hoặc message trong queue.
- Object đã kết hợp dữ liệu công khai với dữ liệu xác thực.

Trường hợp secret do server tự lấy cần được chú ý: người gọi có thể chưa từng biết secret trước khi tạo ra một lỗi. Không được chỉ kiểm tra nguy cơ phản chiếu lại dữ liệu do client gửi.

### 3.2. Phép biến đổi vẫn có thể bảo toàn khả năng sử dụng

```text
Secret gốc
  -> chuỗi URL / object request / connection string
  -> message của exception hoặc cause
  -> log formatter / trace exporter / DTO lỗi
  -> response, log, telemetry, ticket hỗ trợ
```

URL encoding, Base64, JSON escaping và nén không tạo thành biện pháp bảo vệ secret đối với bên có thể giải mã chúng. Che một dạng biểu diễn cũng không chứng minh mọi dạng khác đã bị loại.

Việc cắt chuỗi cũng không phải redaction đáng tin cậy. Một token có thể vẫn còn nguyên trong đoạn đầu của một message dài, hoặc việc cắt làm mất phần tên field để cơ chế lọc phía sau không còn nhận diện được.

### 3.3. Danh mục đầu ra cần được chốt trước khi viết tiêu chí

| Đầu ra | Điểm dễ phát hành secret | Chủ sở hữu minh họa |
|---|---|---|
| API, HTML, RPC | Message, error details, header, metadata | Đội ứng dụng và nền tảng |
| Log ứng dụng và console | Exception renderer, request dump, cấu hình khởi động | Đội ứng dụng và vận hành |
| Trace và hệ thống báo lỗi | Thu exception tự động, HTTP capture, thuộc tính span | Đội observability và ứng dụng |
| Metric | Label hoặc tên metric được ghép từ input hoặc message | Đội ứng dụng và observability |
| Queue và dead-letter queue | Payload gốc cộng bản mô tả lỗi | Đội tích hợp và nền tảng dữ liệu |
| Giao diện và công cụ client | Thông báo, browser console, crash reporter | Đội frontend hoặc mobile |
| Hỗ trợ và xuất dữ liệu | Email chẩn đoán, ticket, file tải về | Đội hỗ trợ và vận hành |
| Artifact và bản sao | File chẩn đoán, index tìm kiếm, backup của log | Đội quản lý hạ tầng liên quan |

Metric không phải nơi thích hợp để đặt request ID hay giá trị token làm label. Ngoài nguy cơ dữ liệu, việc dùng những giá trị có nhiều biến thể tạo ra số lượng chuỗi thời gian lớn. Chọn mã route và loại lỗi hữu hạn theo danh sách cho phép.

Không cần đưa mọi loại artifact vào một yêu cầu mơ hồ. Cần ghi rõ phạm vi đang kiểm soát, bên sở hữu từng sink và phần nào cần yêu cầu riêng, chẳng hạn memory dump có thể chứa dữ liệu của cả tiến trình.

## 4. Kịch bản rủi ro dẫn tới yêu cầu nào?

Một mô tả rủi ro nên có điều kiện, hành vi, đối tượng nhận và hậu quả:

> Khi nhà cung cấp từ chối request, exception của HTTP client chứa header xác thực. Bộ thu lỗi tự động gửi exception tới kho telemetry có quyền truy cập rộng hơn kho secret. Người có quyền đọc telemetry có thể lấy credential để gọi nhà cung cấp với quyền của hệ thống.

Những kịch bản bổ sung:

| ID | Đường đi của secret | Hậu quả tiềm tàng |
|---|---|---|
| R-01 | Message của exception được đưa vào response | Người gọi nhận credential hoặc token chưa từng được phép biết |
| R-02 | Formatter ghi cả cause và object request | Người đọc log nhận secret dù log message chính đã được che |
| R-03 | Agent thu exception trước bước lọc của ứng dụng | Secret đã ra khỏi tiến trình trước khi redaction chạy |
| R-04 | Secret trong URL đi vào access log hoặc trace | Nhiều bên nhận cùng có bản sao giá trị cấp quyền |
| R-05 | Frontend gửi response lỗi thô tới dịch vụ theo dõi | Phạm vi phát hành mở rộng ngoài ý định của backend |
| R-06 | Sửa log hiện tại nhưng bản export và backup còn nguyên | Secret tiếp tục có thể bị tìm thấy trong lịch sử |
| R-07 | Cấu hình khởi động thất bại bị dump ra console | Secret của server đi vào hệ thống thu log hạ tầng |

Che nội dung ở API chỉ xử lý một phần R-01. Nó không tự xử lý R-02, R-03 hoặc bản sao lịch sử của R-06. Mỗi đường đi phải có biện pháp và bằng chứng riêng.

## 5. Nguyên tắc thiết kế: giảm dữ liệu trước khi tạo lỗi

### 5.1. Không đưa secret vào exception nếu không cần

Một exception phục vụ điều khiển luồng hoặc phân loại thất bại thường chỉ cần loại lỗi, mã nội bộ và một số metadata không bí mật.

Ví dụ nguy hiểm:

```java
throw new IllegalStateException(
    "Provider rejected apiKey=" + apiKey + ", request=" + request
);
```

Ngay cả khi response được ánh xạ an toàn, secret đã nằm trong exception và có thể bị một agent, debugger hoặc formatter khác thu lại.

Một thông báo nội bộ tốt hơn có thể dùng mã sự kiện và tên dependency đã được phép ghi, không chứa credential, payload gốc hoặc object có `toString()` không kiểm soát. Chỉ sửa dòng message chưa đủ nếu cause được gắn vào vẫn mang dữ liệu gốc; cần xem toàn bộ cây exception và cơ chế thu thập.

### 5.2. Chọn field theo allowlist

Một bản ghi lỗi an toàn theo schema có thể gồm:

```json
{
  "event": "dependency_call_failed",
  "requestId": "46c3385b-8d63-41af-8fe6-7c6068e79548",
  "routeId": "payment.create",
  "dependencyId": "payment-provider",
  "failureCategory": "UPSTREAM_UNAVAILABLE",
  "deploymentRevision": "candidate-build-15"
}
```

Các giá trị này là dữ liệu minh họa. Route ID là tên route đã định nghĩa, không phải URL thô; dependency ID là tên logic, không phải connection string; failure category là mã hữu hạn, không phải message do upstream cung cấp.

Không lấy một object context lớn rồi chỉ bỏ vài field tên `password` hoặc `token`. Field mới, cấu trúc lồng nhau, phần tử mảng hoặc tên không dự đoán trước có thể làm secret lọt qua blacklist.

Với dữ liệu không có trong schema được phép, hành vi mặc định nên là không phát hành vào sự kiện lỗi. Cần cập nhật schema và đánh giá mục đích trước khi bổ sung trường mới.

### 5.3. Tách định danh chẩn đoán khỏi dữ liệu cấp quyền

Request ID nên do thành phần tin cậy tạo, không chứa secret và không tự cấp quyền xem log. Không dùng session ID, access token hoặc token khôi phục làm correlation ID.

Nếu cần đối chiếu lần sử dụng một credential, ưu tiên định danh credential không bí mật do hệ thống quản lý credential cung cấp, nếu có và phù hợp. Không tự tạo fingerprint từ mọi secret rồi coi đó là dữ liệu an toàn mặc định. Mục đích liên kết, độ nhạy, quyền truy cập và thời hạn lưu vẫn phải được xem xét.

## 6. Hợp đồng lỗi công khai không mang secret

Ví dụ phản hồi cho một lỗi xử lý bất ngờ:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store

{
  "code": "INTERNAL_ERROR",
  "message": "Không thể xử lý yêu cầu lúc này.",
  "requestId": "46c3385b-8d63-41af-8fe6-7c6068e79548"
}
```

`code` là mã ổn định cho client, `message` được chọn từ nội dung công khai đã xác nhận, còn `requestId` dùng cho đối chiếu. Không trường nào lấy giá trị từ raw exception hoặc payload xác thực.

Với lỗi nhập liệu, có thể trả tên field và mã quy tắc đã cho phép, nhưng không cần trả lại giá trị secret:

```json
{
  "code": "INVALID_INPUT",
  "message": "Dữ liệu chưa đáp ứng quy tắc đã công bố.",
  "fields": [
    {"field": "password", "rule": "POLICY_NOT_MET"}
  ],
  "requestId": "e3d287a7-dd51-40f3-b955-688a466fa296"
}
```

Một số luồng cần thông báo chung để không tiết lộ tài khoản có tồn tại hay không. Quy tắc đó cần được thiết kế cùng chính sách xác thực, không suy trực tiếp từ loại exception.

Không thay mọi lỗi bằng status thành công chỉ để che chi tiết. Status và hành vi nghiệp vụ vẫn phải đúng hợp đồng. Cũng không cam kết giao dịch chưa xảy ra hoặc yêu cầu retry mù khi trạng thái của dependency còn chưa xác định.

Các header mới được tạo để mang token theo hợp đồng xác thực, chẳng hạn khi phát hành phiên, là một luồng dữ liệu khác với việc secret vô tình xuất hiện trong chẩn đoán lỗi. Cần phân biệt luồng cấp credential được thiết kế với luồng tiết lộ ngoài ý muốn; không dùng ngoại lệ này để phản chiếu credential cũ trong body hoặc header debug.

## 7. Ví dụ Java: schema lỗi không nhận raw exception

Ví dụ dưới đây dùng cú pháp Java 17 trở lên. Nó minh họa hai kiểu dữ liệu riêng cho response công khai và sự kiện vận hành tối thiểu.

```java
import java.util.UUID;

public final class SecretSafeErrors {
    private SecretSafeErrors() {}

    public enum RouteId {
        LOGIN,
        PAYMENT_CREATE
    }

    public enum FailureKind {
        CREDENTIAL_REJECTED,
        UNEXPECTED_FAILURE
    }

    public record PublicBody(
        String code,
        String message,
        String requestId
    ) {}

    public record PublicReply(int status, PublicBody body) {}

    public record SafeEvent(
        UUID requestId,
        RouteId route,
        FailureKind failure
    ) {}

    public static PublicReply credentialRejected(UUID requestId) {
        return new PublicReply(
            401,
            new PublicBody(
                "AUTHENTICATION_FAILED",
                "Không thể xác thực bằng thông tin đã cung cấp.",
                requestId.toString()
            )
        );
    }

    public static PublicReply unexpected(UUID requestId) {
        return new PublicReply(
            500,
            new PublicBody(
                "INTERNAL_ERROR",
                "Không thể xử lý yêu cầu lúc này.",
                requestId.toString()
            )
        );
    }
}
```

Những quyết định có ý nghĩa bảo mật:

- Hai factory response không nhận password, token, exception hoặc object request.
- Message công khai là nội dung cố định, không nối với input hoặc upstream message.
- `SafeEvent` chỉ có UUID và enum, không có trường tự do chứa payload chẩn đoán.
- Request ID được tạo và truyền từ tầng tin cậy; nó không được lấy từ secret.
- Sự kiện vận hành được gửi tới sink phù hợp, không được gộp vào DTO trả client.

Đây là một giới hạn về luồng dữ liệu ở cấp thiết kế, chưa phải chứng minh toàn bộ ứng dụng an toàn. Các constructor kiểu dữ liệu vẫn cần được dùng đúng, request ID cần hợp lệ và tầng HTTP phải thực hiện đầy đủ hợp đồng giao thức của luồng xác thực. Giá trị `status` trong object phải được adapter đặt thành HTTP status thực.

Mẫu chưa xử lý parser, middleware, gateway, agent tự thu lỗi hoặc trường hợp logger ngừng hoạt động. Nó cũng không bảo vệ một secret đã được thư viện ghi ra console trước khi mapper được gọi.

Khi tích hợp logging, không vô tình viết thêm raw exception bên cạnh sự kiện an toàn:

```java
// Việc event đã an toàn không làm cho exception tự trở nên an toàn.
// Không coi cách gọi này là đã đáp ứng yêu cầu chống lộ secret.
logger.error("dependency_call_failed", exception);
```

Cần xác minh exception renderer và mọi exporter thực sự hoạt động. Nếu không chứng minh được nội dung exception đã phù hợp policy, sự kiện chuẩn không nên đính kèm nó.

## 8. Redaction: đặt đúng chỗ và hiểu giới hạn

### 8.1. Redaction trước ranh giới phát hành

Redaction là loại bỏ hoặc thay thế phần dữ liệu không được phép phát hành, chẳng hạn bằng hằng `[REDACTED]`. Nó hữu ích như một lớp kiểm soát bổ sung cho các dữ liệu có schema và ngữ nghĩa đã biết.

Thứ tự xử lý cần được thiết kế rõ:

```text
Dữ liệu có schema
  -> chọn trường được phép
  -> loại hoặc che trường nhạy cảm được nhận diện
  -> tạo message / serialize theo ngữ cảnh đầu ra
  -> giới hạn kích thước và phát hành
```

Nếu dữ liệu đã được ghi vào file tạm, gửi qua exporter hoặc đưa vào queue trước bước che, redaction phía sau không bảo vệ bản sao đó.

Log formatter của ứng dụng không tự kiểm soát được agent thu exception trước formatter. Tương tự, frontend che lỗi trên màn hình không xóa response đã xuất hiện trong network inspector hoặc đã được gửi tới telemetry.

### 8.2. Những quy tắc cụ thể cần xác nhận

| Trường hợp | Yêu cầu cần làm rõ |
|---|---|
| Header xác thực và cookie | Không ghi giá trị; nhận diện theo ngữ nghĩa giao thức, kể cả biến thể tên hợp lệ |
| JSON lồng nhau hoặc mảng | Áp dụng policy theo schema cho mọi độ sâu trong phạm vi, không chỉ field cấp ngoài |
| URL và connection string | Không phát hành bản gốc; ưu tiên route hoặc dependency ID thay thế |
| Exception có cause và suppressed | Không chỉ xử lý message cấp ngoài rồi render nguyên phần còn lại |
| Object bất kỳ | Không gọi `toString()` trước rồi hy vọng bộ lọc sẽ hiểu mọi định dạng |
| Dữ liệu quá lớn hoặc cấu trúc chưa hỗ trợ | Bỏ phần không an toàn, tạo sự kiện tối giản và tín hiệu nội bộ không mang payload |
| Lỗi trong bộ lọc | Không fallback sang dữ liệu gốc khi không thể hoàn tất redaction |

Che bằng số lượng dấu sao bằng độ dài secret có thể làm lộ độ dài. Một placeholder cố định giúp tránh tiết lộ đó, nhưng không thay thế việc kiểm tra các field và bản sao khác.

### 8.3. Vì sao regex hoặc tìm giá trị chính xác chưa đủ?

Một regex có thể bỏ sót secret không có tiền tố quen thuộc, giá trị đã encode, chuỗi bị chia nhỏ hoặc tên field do thư viện tự tạo. Bộ lọc theo giá trị chính xác cũng có thể không biết secret mới do dependency phát hành.

Không nên phân phối toàn bộ secret thật tới mọi hệ thống logging chỉ để dùng làm danh sách tìm và che. Cách đó tự tạo thêm nhiều nơi nắm giữ secret.

Ưu tiên ngăn đưa secret vào dữ liệu lỗi từ nguồn, dùng schema hạn chế trường và vô hiệu hóa việc thu payload không cần thiết. Scanner và regex hỗ trợ phát hiện hoặc giảm một số dạng đã biết; chúng không phải chứng minh hoàn chỉnh cho mọi chuỗi có thể xuất hiện.

## 9. Bộ yêu cầu bảo mật có thể nghiệm thu

Các mã dưới đây là mẫu cho dự án, chưa phải kết quả kiểm chứng của một hệ thống đang vận hành.

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| SECERR-01 | Danh mục secret và nguồn sử dụng được xác định cho các luồng nằm trong phạm vi | Sơ đồ dữ liệu và phân loại field |
| SECERR-02 | Message và DTO lỗi công khai chỉ lấy dữ liệu từ schema cùng danh sách nội dung được phép | Schema, mapper và ca lỗi chưa biết |
| SECERR-03 | Standard log và telemetry lỗi không nhận credential, secret hoặc object request thô ngoài policy đã xác định | Cấu hình thu thập và quan sát dữ liệu thực xuất |
| SECERR-04 | Không dùng secret, session token hoặc URL cấp quyền làm correlation ID hoặc metric label | Schema sự kiện và danh mục metric |
| SECERR-05 | Việc xử lý exception xem xét cả message, cause, suppressed exception và trường do framework thêm | Fixture nhiều tầng và kết quả thu thập |
| SECERR-06 | Upstream body và cấu hình kết nối không được chuyển thẳng tới client khi lỗi | Thử lỗi dependency và lỗi khởi tạo |
| SECERR-07 | Cơ chế redaction hoàn tất trước khi dữ liệu đi tới sink không có quyền nhận dữ liệu gốc | Sơ đồ thứ tự xử lý và quan sát từng sink |
| SECERR-08 | Khi redaction hoặc logging lỗi, hệ thống không phát hành lại payload gốc làm fallback | Fault injection và response cùng sự kiện tối giản |
| SECERR-09 | Parser, middleware, edge và client telemetry đều có chủ sở hữu kiểm soát lỗi trong phạm vi | Ma trận tầng và kết quả kiểm thử |
| SECERR-10 | Bản triển khai không tự bật request dump, debug payload hoặc capture secret ngoài cấu hình được xác nhận | Cấu hình hiệu lực và thử trên candidate build |
| SECERR-11 | Bằng chứng nghiệm thu dùng secret tổng hợp không có quyền truy cập thật | Hồ sơ fixture và kết quả kiểm tra |
| SECERR-12 | Quy trình xử lý phát hiện lộ xác định được credential liên quan, nơi nhận và hành động thu hồi hoặc thay thế | Diễn tập và danh sách chủ sở hữu |

### 9.1. Một đặc tả chi tiết cho đường lỗi dependency

```text
Phạm vi:
  API tạo đơn và lời gọi tới nhà cung cấp thanh toán của candidate build.

Dữ liệu không được phát hành qua chẩn đoán:
  API key của server, header xác thực, cookie, token ký URL,
  connection string và raw body đã phân loại chứa secret.

Đầu ra cần kiểm tra:
  Response API, standard log, trace exporter, kho báo lỗi và telemetry client.

Hành vi:
  Dùng mã lỗi và thông báo công khai cố định.
  Ghi sự kiện tối thiểu theo schema, không đính kèm request hoặc Throwable thô.
  Không fallback về payload gốc nếu redaction hoặc logging thất bại.

Điều kiện đạt:
  Các ca lỗi bắt buộc thực sự được kích hoạt.
  Không có canary secret ở các sink bị cấm trong cửa sổ quan sát đã chốt.
  Response giữ đúng schema và ngữ nghĩa nghiệp vụ của từng ca.

Giới hạn:
  Ghi rõ sink chưa quan sát được, nền tảng chưa thử và bằng chứng còn thiếu.
```

Không dùng câu “đã bật mask” làm điều kiện đóng. Cần chứng minh giá trị thực nhận ở đúng ranh giới và cấu hình áp dụng cho bản đang nghiệm thu.

## 10. Thiết kế kiểm thử bằng secret tổng hợp

### 10.1. Canary có nguồn và vị trí xác định

Một canary trong bài kiểm thử là giá trị đánh dấu không có quyền truy cập thật, được đặt vào những vị trí có khả năng mang secret.

```text
SYNTHETIC_ONLY_AUTH_A_6D3F
SYNTHETIC_ONLY_SERVER_KEY_B_8A42
SYNTHETIC_ONLY_RESET_C_5E19
```

Tách canary theo nguồn để biết đường nào bị lộ: secret do client gửi, credential do server dùng và secret xuất hiện từ upstream. Có thể thêm marker riêng cho message, cause và suppressed exception.

Không tạo credential hoạt động trên production để làm canary kiểm tra bài học. Fixture chỉ cần đủ khác biệt để tìm thấy trong môi trường kiểm soát.

Nếu scanner yêu cầu định dạng cụ thể, tạo giá trị tổng hợp theo fixture của scanner và xác nhận không gắn với quyền truy cập thật. Tránh để dữ liệu kiểm thử bị hiểu là credential đang sử dụng.

### 10.2. Ma trận kiểm thử minh họa

| Ca | Cách tạo tình huống | Điều kiện kiểm tra |
|---|---|---|
| TC-01 | Đăng nhập thất bại với password canary | Response và log không có giá trị password hoặc rejected value thô |
| TC-02 | Header xác thực hoặc cookie có canary, request lỗi | Các tầng thu request không phát hành canary vào sink bị cấm |
| TC-03 | API key tổng hợp của server được dependency giả lập phản chiếu trong lỗi | Client, log chuẩn và exporter không nhận giá trị đó |
| TC-04 | Canary nằm trong cause và suppressed exception | Không bị render gián tiếp cùng outer exception |
| TC-05 | URL có token hoặc connection string tổng hợp gặp lỗi | Access log, trace và thông báo không giữ nguyên chuỗi cấp quyền |
| TC-06 | Field nhạy cảm nằm trong object lồng nhau hoặc mảng | Không bỏ sót vì chỉ lọc cấp ngoài |
| TC-07 | Dữ liệu có biểu diễn URL-encoded, JSON-escaped hoặc Base64 trong fixture | Không dựa vào một lần tìm chuỗi nguyên bản để kết luận |
| TC-08 | Error message rất dài, secret nằm trước và sau vị trí cắt | Không lộ phần secret hoặc fallback về bản gốc |
| TC-09 | Bộ lọc redaction ném lỗi hoặc không hỗ trợ cấu trúc | Bỏ dữ liệu không an toàn, giữ đường lỗi tối giản |
| TC-10 | Logging hoặc exporter gặp lỗi, retry hoặc đệm dữ liệu | Không có sink phụ hoặc spool chứa payload ngoài policy |
| TC-11 | Lỗi parser, middleware hoặc cấu hình khởi tạo | Không cần tới controller vẫn giữ chính sách chống lộ |
| TC-12 | Frontend nhận body lỗi có canary từ server thử | Không tự chuyển tiếp body thô vào telemetry hoặc ticket |
| TC-13 | Export bản ghi và đọc index liên quan trong phạm vi thử | Không tồn tại bản sao mà pipeline chính đã bỏ qua |
| TC-14 | Thay credential canary A bằng B trong cùng kịch bản | Nội dung công khai không đổi theo giá trị secret, trừ trường độc lập đã cho phép |

Ca TC-14 giúp phát hiện việc nội dung lỗi phụ thuộc vào secret, nhưng không tự chứng minh không có mọi side channel. Khác biệt về thời gian, độ dài, status và hành vi xác thực có thể cần phân tích riêng theo mô hình đe dọa.

### 10.3. Oracle cần biết mình đã quan sát gì

Kiểm tra tối thiểu gồm:

1. Xác nhận đúng nhánh lỗi được kích hoạt và đúng fixture được sử dụng.
2. Thu toàn bộ response gồm body, header và metadata phù hợp giao thức.
3. Đợi hoặc xác nhận hoàn tất việc export trong cửa sổ quan sát đã chốt; không coi chưa thấy dữ liệu ngay là dữ liệu không được gửi.
4. Kiểm tra từng sink thuộc danh mục, kể cả formatter exception và cơ chế capture tự động.
5. Tìm dạng gốc và những dạng biến đổi thuộc fixture; kiểm tra cấu trúc để phát hiện vị trí không được phép.
6. Xác minh nội dung được phép vẫn tồn tại: code, schema, status và request ID đúng hợp đồng.
7. Ghi rõ độ trễ, sampling, quyền truy cập và khu vực chưa quan sát được.

Sampling có thể khiến một sự kiện không xuất hiện ở lần chạy đơn lẻ. Trong môi trường thử cần cấu hình hoặc cơ chế xác nhận phù hợp để biết dữ liệu có thực sự đi qua điểm kiểm tra. Không gộp nhánh chưa được quan sát vào kết quả PASS.

Tìm canary không thay thế kiểm tra nguồn tạo message và cấu hình agent. Cả hai loại bằng chứng bổ sung cho nhau: một loại cho thấy hành vi đã quan sát, loại kia giúp nhận diện đường đi chưa được kích hoạt.

## 11. Log, telemetry và artifact cần được bảo vệ xuyên vòng đời

### 11.1. Nội bộ không có nghĩa là được lưu secret

Kho log, trace và ticket thường có mục đích tìm lỗi, nhiều người truy cập và khả năng export. Quyền dùng một credential trong runtime không tự chuyển thành quyền đọc credential trong kho chẩn đoán.

Phải giới hạn quyền đọc, thời hạn giữ và bên nhận cho những dữ liệu chẩn đoán được phép lưu. Những biện pháp này hỗ trợ bảo vệ dữ liệu; chúng không thay thế mục tiêu không ghi secret không cần thiết.

Một response có `Cache-Control: no-store` không ngăn ứng dụng tự đưa body vào log hoặc chụp màn hình. Tương tự, mã hóa kho log không loại bỏ nguy cơ người đã được quyền tìm kiếm lấy được secret.

### 11.2. Bản sao, retry và phục hồi

Pipeline quan sát có thể tạo file đệm, bản ghi retry, index tìm kiếm và backup. Nếu bộ lọc nằm sau một bước lưu đệm, secret có thể tồn tại trong bản đệm dù bản ghi hiển thị cuối cùng đã được che.

Đối với dữ liệu lỗi đã được xử lý xóa hoặc hạn chế sau sự cố, quy trình restore cần xem xét khả năng đưa bản cũ trở lại nơi có thể tìm kiếm. Ghi rõ hành vi phục hồi, các giới hạn không thể xóa chọn lọc và biện pháp kiểm soát truy cập tương ứng.

Không tuyên bố “đã sạch mọi nơi” chỉ vì sửa một record trên giao diện log. Phạm vi xử lý phải bám theo danh mục bên nhận và bản sao thực tế.

### 11.3. Artifact chẩn đoán chuyên sâu

Memory dump, heap dump hoặc snapshot tiến trình có thể chứa secret nằm trong bộ nhớ ngay cả khi DTO và log đều đúng. Đây là bề mặt cần chính sách riêng về việc tạo, truy cập, vận chuyển, thời hạn lưu và sử dụng.

Không tự động đính kèm các artifact này vào mọi ticket lỗi. Nếu dự án có nhu cầu điều tra bằng chúng, phải đặc tả rõ phạm vi và giới hạn; không coi việc đã che log là bằng chứng artifact cũng an toàn.

## 12. Nếu phát hiện secret đã lộ qua lỗi

Phát hiện lộ secret cần hai hướng xử lý song song: giảm khả năng secret tiếp tục được sử dụng và ngăn đường phát hành tạo thêm bản sao.

Một trình tự ứng phó có thể gồm:

1. **Chặn nguồn phát hành:** tắt capture không cần thiết, sửa mapper hoặc formatter, giới hạn luồng export liên quan.
2. **Xác định phạm vi:** loại credential, môi trường, thời gian, bên nhận và những bản sao có thể tồn tại.
3. **Thu hồi hoặc thay thế:** áp dụng khả năng revoke, rotate hoặc kết thúc phiên phù hợp loại credential; xác minh credential cũ thực sự không còn được chấp nhận trong phạm vi cần thiết.
4. **Kiểm tra phụ thuộc:** credential mới đã tới đúng consumer, không bị lỗi khi chuyển đổi và không tiếp tục lọt vào cùng đường lỗi.
5. **Hạn chế bản sao:** xóa hoặc cô lập dữ liệu ở nơi có thể xử lý, giảm quyền tìm kiếm và export, ghi rõ giới hạn của backup hoặc lưu trữ bất biến.
6. **Điều tra việc sử dụng:** xem xét bằng chứng truy cập và hành vi liên quan theo quy trình của tổ chức, không mặc định lộ đồng nghĩa đã bị khai thác hoặc chưa có dấu hiệu đồng nghĩa an toàn.
7. **Bổ sung kiểm thử hồi quy:** tái hiện bằng canary tổng hợp và xác minh những sink đã bỏ sót.

Việc đổi secret không xóa các bản sao lịch sử. Việc xóa log cũng không làm mất quyền của một credential còn hiệu lực. Hai hành động giải quyết những phần khác nhau của sự cố.

Không sao chép secret vào tiêu đề ticket, ảnh chụp, chat hỗ trợ hoặc báo cáo để mô tả chính sự cố lộ secret. Dùng định danh không bí mật và bằng chứng đã giảm dữ liệu; giữ dữ liệu điều tra cần thiết trong phạm vi quyền phù hợp.

## 13. Truy vết từ yêu cầu tới quyết định nghiệm thu

Một chuỗi minh họa cho R-03:

```text
Rủi ro:
  Agent tự thu raw exception trước bước lọc của ứng dụng.
    -> SECERR-03, SECERR-05, SECERR-07, SECERR-10
    -> Thiết kế: bỏ capture payload và chọn schema sự kiện an toàn
    -> Ca thử: TC-03, TC-04, TC-07, TC-10
    -> Bằng chứng: cấu hình hiệu lực và dữ liệu thực nhận ở exporter
    -> Kết luận: phần đạt, phần chưa quan sát được và hành động còn thiếu
```

Hồ sơ nghiệm thu nên có:

| Thành phần | Nội dung cần ghi |
|---|---|
| Phạm vi | Route, dependency, môi trường và các sink được kiểm tra |
| Phiên bản | Build ứng dụng, cấu hình thu thập và revision policy |
| Fixture | Loại canary, vị trí đưa vào và nhánh lỗi cần kích hoạt |
| Kết quả | Schema, status, việc xuất dữ liệu và kết quả từng ca |
| Giới hạn | Sampling, độ trễ, sink không có quyền quan sát hoặc nhánh chưa thử |
| Chủ sở hữu | Người sửa nguồn dữ liệu, agent, exporter, client và quy trình hỗ trợ |
| Rủi ro còn lại | Vấn đề chưa xử lý và quyết định theo thẩm quyền áp dụng |

Một tiêu chí đóng có thể là:

> Trên build và cấu hình đã ghi trong hồ sơ, mọi ca bắt buộc của các luồng cùng sink trong phạm vi đã thực sự chạy; không canary nào xuất hiện tại kênh bị cấm trong cửa sổ quan sát đã chốt; response và sự kiện cho phép vẫn đúng hợp đồng; phần chưa kiểm chứng được ghi riêng và chưa được tính là đạt.

Đây là kết luận trong phạm vi bằng chứng. Nó không phải bảo đảm rằng mọi thư viện, mọi cấu hình tương lai hoặc mọi secret có thể xuất hiện đều đã được kiểm chứng.

Khi thay HTTP client, agent báo lỗi, log formatter, schema request, nhà cung cấp hoặc đường export, cần xem xét lại giả định và bộ thử liên quan. Một cấu hình capture mới có thể mở lại đường lộ dù mapper công khai không thay đổi.

## 14. Những sai lầm cần tránh

| Sai lầm | Vì sao không đủ | Cách cải thiện |
|---|---|---|
| Ẩn stack trace nhưng trả message nguyên bản | Secret vẫn có thể nằm ngay trong message | Dùng mã và thông báo công khai từ allowlist |
| Chỉ che field tên `password` | Secret có thể nằm trong URL, header hoặc field tên khác | Phân loại theo nguồn và schema |
| Che sau khi đã serialize hoặc gửi exporter | Bản gốc có thể đã được lưu hoặc chuyển đi | Đặt kiểm soát trước từng ranh giới phát hành |
| Ghi raw exception cạnh structured event an toàn | Exception renderer vẫn xuất message và cause | Kiểm soát từng tham số cùng cơ chế tự thu |
| Dùng secret làm mã đối chiếu | Chuyển dữ liệu cấp quyền sang kho chẩn đoán | Dùng request ID độc lập, không cấp quyền |
| Dùng regex như bằng chứng duy nhất | Bỏ sót định dạng, encoding hoặc secret mới | Ngăn từ nguồn, schema hạn chế và kiểm thử nhiều tầng |
| Fallback về dữ liệu gốc khi che lỗi | Chính lúc bảo vệ thất bại lại phát hành secret | Bỏ phần không an toàn và giữ sự kiện tối giản |
| Chỉ quét kho log chính | Exporter, client, queue và backup có thể giữ bản khác | Duy trì danh mục sink và chủ sở hữu |
| Rotate rồi coi như hoàn tất | Bản sao lịch sử và đường lỗi có thể vẫn tồn tại | Kết hợp thu hồi, chặn nguồn và xử lý bản sao |
| Dùng secret thật để chứng minh lỗi | Tạo thêm chính sự cố cần tránh | Dùng canary tổng hợp không có quyền thật |

## 15. Thực hành đặc tả cho luồng đặt lại mật khẩu

Một hệ thống tạo URL đặt lại mật khẩu có token dùng một lần. Khi dịch vụ email thất bại, exception chứa toàn bộ URL. Backend trả message cho frontend, ghi exception vào log và gửi lỗi tới dịch vụ theo dõi. Đội hỗ trợ có thể export bản ghi lỗi ra file. Hệ thống thu log có index tìm kiếm và backup riêng.

Hãy xây dựng một đặc tả gồm:

1. Phân loại token và URL theo khả năng cấp quyền, chỉ rõ dữ liệu nào không phải secret nhưng vẫn cần hạn chế.
2. Vẽ đường dữ liệu từ lúc tạo token đến exception, response, log, exporter và file hỗ trợ.
3. Viết ít nhất ba kịch bản rủi ro có người nhận và hậu quả cụ thể.
4. Thiết kế schema lỗi công khai cùng sự kiện vận hành tối thiểu không mang URL hoặc token.
5. Chỉ rõ vị trí loại dữ liệu trước khi tạo exception và trước các ranh giới phát hành còn lại.
6. Đặt hành vi khi logging hoặc redaction thất bại, tránh fallback về URL gốc.
7. Thiết kế canary riêng cho outer message, cause, suppressed exception và dữ liệu exporter.
8. Chốt danh mục sink, cửa sổ quan sát, cấu hình thử và tiêu chí không tính nhánh chưa quan sát là PASS.
9. Xác định cách vô hiệu hóa token đã phát hành nếu phát hiện lộ, cùng giới hạn xử lý log, export và backup.
10. Gắn từng yêu cầu với chủ sở hữu, ca kiểm thử và bằng chứng cần để nghiệm thu.

Hồ sơ hoàn thành cần cho người khác thấy được secret đã bị loại ở đâu, đầu ra nào đã được quan sát, phần nào còn thiếu bằng chứng và cách hệ thống giữ thông báo lỗi hữu ích mà không biến chẩn đoán thành kênh cấp quyền ngoài ý muốn.
