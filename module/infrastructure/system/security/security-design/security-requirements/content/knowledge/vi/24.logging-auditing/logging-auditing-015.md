# Không log secret và PII dư thừa

## 1. Log phải giúp điều tra mà không trở thành kho dữ liệu nhạy cảm

Một API ghi toàn bộ request để dễ tìm lỗi. Password nằm trong body, token nằm trong header, số điện thoại nằm trong URL và địa chỉ giao hàng nằm trong object nghiệp vụ. Các dữ liệu đó tiếp tục đi vào console, agent thu log, index tìm kiếm và file xuất cho đội hỗ trợ.

Database chính có thể đã được phân quyền chặt, nhưng bản sao trong hệ thống quan sát lại được nhiều người tìm kiếm và giữ lâu hơn nhu cầu ban đầu. Logging đã tạo ra một đường phát hành dữ liệu ngoài ý định.

Yêu cầu **không log secret và PII dư thừa** có hai phần liên quan nhưng khác nhau:

- Không đưa dữ liệu có khả năng xác thực, cấp quyền hoặc bảo vệ mật mã vào log thông thường.
- Chỉ thu dữ liệu liên quan tới cá nhân khi có mục đích cụ thể, mức chi tiết cần thiết và kiểm soát vòng đời phù hợp.

Trong chương Logging và audit, mục tiêu không dừng ở việc bật một bộ lọc. Cần đặc tả dữ liệu được phép đi vào từng loại sự kiện, nguồn tạo giá trị, các nơi nhận, quyền truy cập, thời hạn lưu và bằng chứng kiểm thử.

Sau bài này, người học có thể chuyển rủi ro phát hành dữ liệu qua log thành yêu cầu đo được, gắn yêu cầu với thiết kế sự kiện và xác minh trên toàn bộ đường đi của dữ liệu.

## 2. Phân loại dữ liệu trước khi quyết định ghi

### 2.1. Secret được xác định theo khả năng sử dụng

Secret là dữ liệu mà việc biết hoặc sở hữu có thể cho phép xác thực, ký, giải mã, khôi phục quyền hoặc sử dụng một khả năng được bảo vệ.

| Nhóm | Ví dụ | Quy tắc cho log thông thường |
|---|---|---|
| Credential | Password, API key, thông tin xác thực database | Không ghi giá trị |
| Dữ liệu phiên | Session cookie, access token, refresh token | Không dùng làm nội dung hoặc mã đối chiếu |
| Bí mật ngắn hạn | OTP, token đặt lại mật khẩu, mã xác nhận | Không ghi vì thời hạn ngắn không loại bỏ nguy cơ sử dụng |
| Khóa mật mã | Private key, khóa đối xứng, secret ký webhook | Không đưa key material vào log |
| Dữ liệu cấp quyền bằng việc sở hữu | URL có chữ ký, đường dẫn tải có token | Không ghi nguyên chuỗi cấp quyền |
| Cấu trúc tổng hợp | Connection string, header, object cấu hình | Không serialize nguyên cấu trúc có thể chứa secret |

Tên field không quyết định bản chất. Một trường `reference` vẫn có thể là secret nếu giá trị của nó đủ để tải tài liệu hoặc đổi mật khẩu. Một chuỗi dài cũng không tự là secret nếu đó là định danh công khai không cấp quyền.

Không ghi password hash hoặc fingerprint tự tạo từ secret để “dễ đối chiếu” mà chưa có thiết kế riêng. Những giá trị này có thể tạo nguy cơ dò đoán, liên kết hoặc phát hành dữ liệu không cần thiết.

### 2.2. PII phụ thuộc vào khả năng nhận diện và liên kết

Trong bài này, PII được dùng như khái niệm phân loại kỹ thuật cho thông tin có thể nhận diện, liên hệ hoặc liên kết tới một cá nhân trong bối cảnh của hệ thống. Đây không phải danh mục nghĩa vụ pháp lý cho mọi khu vực.

Ví dụ cần xem xét:

- Họ tên, email, số điện thoại, địa chỉ và mã định danh cá nhân.
- Tài khoản nội bộ, subject ID, mã nhân viên hoặc mã khách hàng có thể tra ngược.
- Địa chỉ IP, định danh thiết bị, cookie và dữ liệu vị trí.
- Lịch sử hoạt động, thời điểm đăng nhập, nội dung tìm kiếm hoặc hỗ trợ.
- Tổ hợp dữ liệu tưởng như ít nhạy cảm nhưng có thể liên kết về một người.

UUID không chứa họ tên vẫn có thể là dữ liệu liên quan đến cá nhân nếu hệ thống có thể tra về tài khoản. Thay email bằng một ID giúp giảm phát hành trực tiếp, nhưng không tự biến lịch sử thành dữ liệu vô danh.

### 2.3. Không phải secret không có nghĩa là công khai được

Tên tenant, quan hệ khách hàng, hostname nội bộ và mã giao dịch có thể là metadata hạn chế. Phân loại thêm các nhóm đó theo mục đích và mô hình rủi ro.

Một field có thể thuộc nhiều nhóm: URL tải tài liệu vừa chứa token cấp quyền, vừa tiết lộ tên hoặc quan hệ của chủ tài liệu. Chỉ che một phần không chứng minh toàn bộ field đã phù hợp để ghi.

## 3. “Dư thừa” phải được đánh giá theo mục đích

### 3.1. Mỗi sự kiện phải trả lời một câu hỏi cụ thể

Ví dụ câu hỏi vận hành:

> Vì sao thao tác xuất báo cáo thất bại trên một revision triển khai?

Thông tin cần thiết có thể gồm route ID, mã lỗi hữu hạn, request ID, thời điểm và revision. Toàn bộ danh sách khách hàng trong báo cáo thường không giúp trả lời câu hỏi đó.

Ví dụ câu hỏi audit:

> Chủ thể nào đã yêu cầu xuất dữ liệu của tenant nào, kết quả và căn cứ quyền ra sao?

Luồng này có thể cần subject reference và tenant reference trong kho audit có quyền phù hợp. Điều đó không có nghĩa mọi log kỹ thuật đều cần sao chép hai field đó.

### 3.2. Bảng quyết định field

| Field dự kiến | Câu hỏi phải trả lời trước khi cho phép |
|---|---|
| Subject reference | Có cần đối chiếu người cụ thể không? Ai được tra ngược? |
| Email hoặc số điện thoại | Vì sao định danh nội bộ không đủ cho mục đích này? |
| Địa chỉ IP | Cần độ chi tiết nào, nguồn tin cậy nào và giữ bao lâu? |
| User agent | Có cần chuỗi đầy đủ hay chỉ nhóm client đã chuẩn hóa? |
| URL | Có thể dùng tên route và mã lỗi thay cho URL thô không? |
| Payload | Có thể dùng loại dữ liệu, số lượng hoặc trạng thái thay cho nội dung không? |
| Free text | Có cách biểu diễn bằng mã hữu hạn mà không sao chép nội dung người dùng không? |
| Thời điểm chính xác | Mức phân giải nào thực sự cần cho điều tra hoặc audit? |

Nếu không nêu được mục đích và người dùng hợp lệ của field, mặc định không thêm field chỉ vì “sau này có thể cần”.

### 3.3. Ba loại kênh có hợp đồng khác nhau

| Kênh | Nội dung thường phù hợp | Kiểm soát cần có |
|---|---|---|
| Log vận hành | Mã thao tác, kết quả, loại lỗi, revision, correlation ID không cấp quyền | Giảm dữ liệu và thời hạn theo mục đích vận hành |
| Audit bảo mật | Chủ thể tham chiếu, hành động, phạm vi, kết quả, căn cứ theo policy | Quyền đọc, toàn vẹn, đối soát và lưu giữ được chốt |
| Chẩn đoán chuyên sâu | Dữ liệu đã giảm theo một nhu cầu điều tra cụ thể | Phạm vi, bên nhận, thời hạn và cơ chế thu riêng |

Không dùng kênh chẩn đoán như ngoại lệ mặc định để dump mọi credential hoặc hồ sơ cá nhân. Nếu một loại artifact có thể chứa dữ liệu trong bộ nhớ, chẳng hạn heap dump, cần policy riêng; cơ chế che log không chứng minh artifact đó an toàn.

## 4. Lập sơ đồ tất cả nơi dữ liệu có thể đi qua

```text
Request / cấu hình server / dữ liệu nghiệp vụ / lỗi upstream
  -> thư viện hoặc object context
  -> logger ứng dụng, exception renderer, trace agent
  -> console, file cục bộ hoặc buffer
  -> collector, queue, retry spool
  -> index tìm kiếm, kho phân tích, kho audit
  -> dashboard, export, ticket hỗ trợ
  -> lưu trữ dài hạn, backup và môi trường restore
```

Thêm các thành phần tự thu dữ liệu vào sơ đồ: access log của gateway, HTTP client logging, agent báo lỗi, browser telemetry và crash reporter. Không bỏ qua chỉ vì ứng dụng không gọi logger trực tiếp.

Với mỗi cạnh, xác định dữ liệu nào được chuyển, ai nhận, nơi nào lưu và kiểm soát nào chạy trước khi phát hành.

### 4.1. Những đường lộ dễ bị bỏ sót

| Nguồn | Cách dữ liệu lọt ra |
|---|---|
| URL | Token, email hoặc số điện thoại đi vào access log và trace |
| Exception | Message, cause và suppressed exception chứa credential hoặc input |
| Context dùng chung | MDC, tracing context hoặc baggage giữ dữ liệu người dùng qua nhiều lớp |
| Object serialization | Field mới của DTO hoặc domain object tự xuất hiện trong log |
| Retry và dead-letter queue | Payload gốc được lưu cùng mô tả lỗi |
| Debug mode | Framework tự bật body capture hoặc request dump |
| Frontend | Response lỗi hoặc nội dung form được gửi sang dịch vụ theo dõi |
| Công cụ hỗ trợ | File xuất giữ dữ liệu lâu và có đối tượng nhận khác kho gốc |

Một redactor ở collector không bảo vệ file cục bộ đã ghi trước đó. Một màn hình chỉ hiển thị phần che không bảo vệ dữ liệu gốc mà API tìm kiếm hoặc export vẫn trả về.

## 5. Thiết kế schema theo allowlist

### 5.1. Bắt đầu từ sự kiện nhỏ

Một log vận hành tối thiểu có thể là:

```json
{
  "schemaVersion": 1,
  "eventType": "OPERATION_FAILED",
  "eventId": "da3192f0-842a-48d9-a725-c18cb13fb553",
  "occurredAt": "2026-11-27T05:10:00Z",
  "operation": "REPORT_EXPORT",
  "failureCode": "DEPENDENCY_UNAVAILABLE",
  "requestId": "be6f3b3d-cb3f-4082-bae7-92e0caf5fcd7",
  "deploymentRevision": "candidate-build-21"
}
```

Không cần email, body báo cáo hoặc raw exception để biết loại thao tác và lớp nguyên nhân. Khi cần đối chiếu sâu hơn, request ID liên kết tới các bằng chứng mà người điều tra có quyền xem theo mục đích phù hợp.

Request ID cũng có thể liên kết hoạt động, nên vẫn cần policy truy cập và lưu giữ. Nó không phải bằng chứng ủy quyền và không được dùng thay cho token xác thực.

### 5.2. Audit chỉ thêm những field được chứng minh cần thiết

Một audit cho xuất dữ liệu có thể cần `subjectAuditRef`, `tenantRef`, `action`, `decisionRef` và `outcome`. Những field đó phải lấy từ context tin cậy, có schema và quyền đọc riêng.

Không thêm toàn bộ profile vì đã cần một subject reference. Không thêm số tài khoản, địa chỉ hoặc nội dung hồ sơ vì đã cần một resource reference.

Nếu dùng định danh giả danh, xác định phạm vi liên kết: dùng chung toàn hệ thống hay theo mục đích. Một reference toàn cục có thể giúp điều tra nhưng cũng làm nhiều kho dữ liệu dễ liên kết với nhau hơn. Quyết định đó cần được ghi nhận, không phải hệ quả vô tình của một helper dùng chung.

### 5.3. Loại bỏ field mới theo mặc định

Tránh mẫu lấy toàn bộ object rồi bỏ một số tên nhạy cảm. Blacklist khó bao phủ field mới, object lồng nhau, phần tử mảng, tên động và nội dung tự do.

Schema allowlist chỉ chọn các trường đã được xác nhận. Khi domain object có thêm `recoveryToken` hoặc `deliveryAddress`, log không tự thay đổi vì không serialize domain object đó.

Các field tự do như `message`, `details` hoặc `Map<String, Object>` cũng có thể phá vỡ allowlist nếu chúng nhận dữ liệu tùy ý. Cần xác định nguồn và schema của nội dung bên trong, không chỉ tên trường ngoài cùng.

## 6. Ví dụ Java: log vận hành không nhận request hoặc principal

Ví dụ dùng Java 17 trở lên. Nó minh họa DTO chỉ chứa metadata cần cho một loại lỗi vận hành, chưa triển khai toàn bộ pipeline logging.

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class MinimalOperationalLog {
    private MinimalOperationalLog() {}

    public enum Operation {
        LOGIN,
        REPORT_EXPORT,
        PAYMENT_CREATE
    }

    public enum FailureCode {
        VALIDATION_REJECTED,
        DEPENDENCY_UNAVAILABLE,
        UNEXPECTED_FAILURE
    }

    public enum EventType {
        OPERATION_FAILED
    }

    public record OperationalFailure(
        int schemaVersion,
        EventType eventType,
        UUID eventId,
        Instant occurredAt,
        Operation operation,
        FailureCode failureCode,
        UUID requestId
    ) {
        public OperationalFailure {
            Objects.requireNonNull(eventType);
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(occurredAt);
            Objects.requireNonNull(operation);
            Objects.requireNonNull(failureCode);
            Objects.requireNonNull(requestId);
        }
    }

    public static OperationalFailure create(
        UUID eventId,
        Instant occurredAt,
        Operation operation,
        FailureCode failureCode,
        UUID requestId
    ) {
        return new OperationalFailure(
            1,
            EventType.OPERATION_FAILED,
            eventId,
            occurredAt,
            operation,
            failureCode,
            requestId
        );
    }
}
```

Điểm có ý nghĩa bảo mật nằm ở giao diện dữ liệu:

- Không có tham số password, token, email, principal, request hoặc Throwable.
- Operation và nguyên nhân là enum, không phải chuỗi được ghép từ input.
- Request ID là định danh do tầng tin cậy cung cấp, không phải session credential.
- Subject reference không xuất hiện trong loại sự kiện vận hành này vì mục đích chưa cần nó.
- Serializer chỉ nhận DTO đã chọn trường, không tự duyệt object nghiệp vụ.

Kiểu dữ liệu không tự chứng minh toàn bộ hệ thống đã giảm dữ liệu. Factory phải được dùng đúng, nguồn ID phải phù hợp và adapter phải dùng serializer theo định dạng đầu ra.

Một dòng như sau có thể mở lại đường lộ dù DTO an toàn:

```java
// Raw exception vẫn có thể chứa token hoặc dữ liệu cá nhân.
logger.error("operation_failed", exception);
```

Tương tự, không đưa lại request body vào một trường phụ hoặc context dùng chung sau khi tạo DTO. Cần xem xét mọi tham số, formatter và agent tự thu quanh lời gọi logging.

## 7. Omission, masking, pseudonymization và encryption khác nhau thế nào?

| Biện pháp | Tác dụng | Giới hạn cần nhớ |
|---|---|---|
| Không thu hoặc không ghi | Dữ liệu không đi vào kênh log đã thiết kế | Phải kiểm tra cả nguồn tự thu khác |
| Giảm độ chi tiết | Chỉ giữ nhóm, loại hoặc độ phân giải cần thiết | Tổ hợp và nhóm nhỏ vẫn có thể liên kết tới cá nhân |
| Masking | Che một phần để phục vụ hiển thị hoặc mục đích đã chốt | Phần còn lại vẫn có thể nhận diện hoặc hỗ trợ đoán |
| Tokenization hoặc reference | Thay dữ liệu trực tiếp bằng tham chiếu được quản lý | Bảng ánh xạ và quyền tra ngược cần được bảo vệ |
| Hashing | Tạo giá trị biến đổi có thể dùng đối chiếu trong một thiết kế cụ thể | Giá trị ít khả năng có thể bị dò; liên kết ổn định vẫn tồn tại |
| Mã hóa | Hạn chế việc đọc nếu không có quyền và khóa phù hợp | Người được giải mã vẫn nhận dữ liệu; bản sao vẫn được thu thập |

Ưu tiên không ghi dữ liệu không cần thiết trước khi chọn cách che. Mã hóa toàn bộ kho log không làm một field dư thừa trở thành cần thiết.

Không mặc định email đã băm là dữ liệu vô danh. Nếu hệ thống có thể đối chiếu, hoặc không gian giá trị dễ đoán, rủi ro nhận diện vẫn tồn tại. Một reference có khóa quản lý riêng có thể hỗ trợ mục đích cụ thể, nhưng vẫn cần quyền truy cập, thời hạn và đánh giá khả năng liên kết.

Không dùng quy tắc giữ vài ký tự cuối cho mọi secret. Với credential, mục tiêu thông thường là không ghi giá trị. Nếu cần đối chiếu credential, ưu tiên ID không bí mật từ hệ thống quản lý credential thay vì trích một phần secret.

## 8. Redaction phải chạy trước nơi dữ liệu không được phép đến

### 8.1. Thứ tự xử lý

```text
Dữ liệu nguồn
  -> phân loại theo schema và mục đích
  -> chọn field được phép
  -> xử lý dữ liệu nhạy cảm được nhận diện trong phạm vi cho phép
  -> serialize và escape đúng định dạng
  -> giới hạn kích thước bản ghi
  -> gửi tới sink đã được cấp quyền
```

Nếu phải giảm payload có cấu trúc, cần quy tắc cho object lồng nhau, mảng, null, field mới và tên động. Không chỉ áp dụng trên JSON cấp ngoài.

Tránh gọi `toString()` trên object tùy ý trước rồi mới che. Khi đã trở thành chuỗi tự do, hệ thống mất nhiều thông tin về ngữ nghĩa field và khó biết đâu là secret.

### 8.2. Truncation và encoding không thay thế redaction

Cắt message còn một phần có thể vẫn giữ nguyên token ở đầu. Nó cũng có thể làm mất tên field khiến bộ lọc phía sau không nhận diện được dữ liệu.

Base64, URL encoding, JSON escaping hoặc nén vẫn có thể bảo toàn giá trị đối với người giải mã được. Tìm chuỗi secret dạng gốc không phát hiện mọi dạng biểu diễn.

Không phân phối danh sách secret thật tới mọi logger để dùng làm từ điển che. Cách đó tự mở rộng số nơi nắm giữ secret. Ưu tiên giới hạn nguồn dữ liệu và schema; scanner hoặc regex là lớp hỗ trợ cho những dạng đã biết.

### 8.3. Khi redaction hoặc serialization lỗi

Nếu không thể tạo bản ghi an toàn, bỏ phần không an toàn hoặc bản ghi đó theo policy và tạo tín hiệu tối giản không chứa payload gốc. Không fallback về raw object, console dump hoặc exception thô.

Cần giới hạn độ sâu, kích thước và chi phí xử lý để dữ liệu bất thường không làm logger chiếm tài nguyên không kiểm soát. Dữ liệu vòng tham chiếu hoặc quá lớn không được khiến cơ chế dự phòng xuất toàn bộ context.

Việc có tiếp tục nghiệp vụ hay không là câu hỏi riêng. Nếu log chỉ phục vụ chẩn đoán best effort, lỗi log không tự tạo yêu cầu dừng mọi chức năng. Nếu một audit bền vững là điều kiện bắt buộc trước hành động nhạy cảm, không được bỏ qua điều kiện đó. Cả hai trường hợp đều không cho phép phát hành secret để cứu logging.

## 9. Kiểm soát framework, context và chế độ debug

### 9.1. Tránh tự thu rộng hơn schema ứng dụng

Cần kiểm tra cấu hình hiệu lực của những thành phần thực sự được dùng:

- Access log của gateway và web server.
- HTTP client, middleware xác thực và bộ xử lý validation.
- Exception renderer, formatter và appender của logger.
- Trace agent, hệ thống báo lỗi, span attributes và context propagation.
- Console, sidecar, collector, buffer và đường export.
- Frontend telemetry hoặc crash reporter của ứng dụng client.

Một cấu hình che ở ứng dụng không chứng minh agent đã không thu request trước bước đó. Tên property và hành vi phụ thuộc stack cụ thể; phải xác minh trên build và cấu hình triển khai của dự án.

### 9.2. Context dùng chung cũng cần schema

MDC hoặc context tracing dễ làm field được tự động gắn vào hàng nghìn bản ghi. Không đưa token, email hoặc nội dung form vào context để tiện tra cứu.

Cần xác định field nào được truyền qua ranh giới service, field nào chỉ tồn tại cục bộ và cách kết thúc context theo request hoặc job. Context của request trước không được gắn nhầm vào request sau.

Không tin correlation ID hoặc tenant ID do client gửi như dữ liệu đã xác thực. Giá trị đầu vào cần giới hạn và lưu theo ngữ nghĩa riêng; nguồn tin cậy phải xác lập identity và phạm vi audit.

### 9.3. Debug không phải ngoại lệ cho dữ liệu nhạy cảm

Level DEBUG vẫn có thể đi vào cùng collector, index và backup như INFO. Đổi level không bảo vệ password hoặc dữ liệu cá nhân.

Nếu cần chẩn đoán có thời hạn, hãy chốt loại field, phạm vi luồng, nơi nhận và thời điểm hết hiệu lực. Không dùng một query parameter hoặc header công khai để bật dump dữ liệu thật.

Môi trường staging có dữ liệu thật hoặc nhiều người truy cập cũng cần policy phù hợp. Tên môi trường không làm giảm độ nhạy của nội dung.

## 10. Giới hạn quyền truy cập và thời gian lưu

### 10.1. Quyền đọc log không nên rộng hơn nhu cầu

Xác định ai được tìm kiếm, xem chi tiết, tra ngược reference và export. Một lập trình viên cần mã lỗi vận hành chưa chắc cần lịch sử cá nhân đầy đủ. Quản trị một tenant không tự có quyền đọc sự kiện tenant khác.

Mã hóa transport và storage, xác thực collector và bảo vệ toàn vẹn là các biện pháp bổ sung. Chúng không thay thế việc giảm field tại nguồn.

Khi bổ sung dashboard hoặc kho phân tích mới, coi đó là một bên nhận mới cần đánh giá quyền và dữ liệu. Không mặc định dữ liệu đã được ghi ở nơi cũ thì có thể sao chép sang mọi nơi.

### 10.2. Retention theo mục đích và mốc rõ ràng

Đặc tả thời hạn bằng policy của từng nhóm, chẳng hạn `T_operational` và `T_security_audit`, cùng người sở hữu và lý do. Không tự chọn một thời hạn chung chỉ vì dung lượng lưu trữ rẻ.

Phải chốt thời điểm bắt đầu tính thời hạn, cách xử lý sự kiện đến muộn, retry và replay. Không để mỗi lần gửi lại tự kéo dài thời gian giữ dữ liệu mà không có chủ đích.

Khi dùng fixture thời gian để kiểm thử, giá trị trong fixture chỉ chứng minh phép tính và quá trình dọn hoạt động, không quyết định thời hạn của dữ liệu thật.

### 10.3. Index không phải bản sao duy nhất

Xem xét queue, retry spool, file đệm, dead-letter queue, index phụ, kho lạnh, file export và backup. Xóa một document trên giao diện tìm kiếm không tự xóa các bản khác.

Với nơi không hỗ trợ xóa chọn lọc, cần ghi rõ giới hạn, chu kỳ lưu, quyền truy cập và hành vi khi phục hồi. Trước khi mở lại index hoặc luồng phục vụ sau restore, áp dụng những điều kiện hết hạn hoặc hạn chế liên quan theo policy.

Không cam kết đã xóa mọi nơi nếu chưa có danh mục bản sao và bằng chứng tương ứng. Tương tự, rotation credential bị lộ không xóa dữ liệu cá nhân đã nằm trong file xuất.

## 11. Bộ yêu cầu bảo mật có thể kiểm chứng

Các mã sau là mẫu đặc tả cho dự án, chưa phải kết quả nghiệm thu một sản phẩm cụ thể.

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| LOG-MIN-01 | Mỗi loại sự kiện có mục đích, chủ sở hữu, schema và danh sách field được phép | Registry sự kiện cùng giải thích field |
| LOG-MIN-02 | Log thông thường không nhận credential, token, key material hoặc dữ liệu cấp quyền | Canary tại nguồn và kiểm tra từng sink |
| LOG-MIN-03 | Field PII chỉ xuất hiện khi có mục đích, mức chi tiết, quyền và retention đã chốt | Ma trận field theo mục đích |
| LOG-MIN-04 | Không serialize request, principal, domain object hoặc raw exception tùy ý | DTO allowlist và cấu hình formatter |
| LOG-MIN-05 | Field mới hoặc không được nhận diện không tự được thêm vào sự kiện | Ca thay đổi schema và object lồng nhau |
| LOG-MIN-06 | Kiểm soát dữ liệu hoàn tất trước từng ranh giới không được nhận bản gốc | Sơ đồ pipeline và quan sát buffer, agent, exporter |
| LOG-MIN-07 | Lỗi redaction hoặc serialization không fallback về dữ liệu thô | Fault injection và tín hiệu tối giản |
| LOG-MIN-08 | Context truyền qua request, job và service chỉ có field theo schema phù hợp | Thử rò context, nguồn giả và truyền liên dịch vụ |
| LOG-MIN-09 | Debug hoặc capture tự động không bỏ qua policy trên môi trường thuộc phạm vi | Cấu hình hiệu lực và thử các đường bật debug |
| LOG-MIN-10 | Tìm kiếm, tra ngược reference và export bị giới hạn theo vai trò, tenant và mục đích | Ma trận quyền cùng ca truy cập chéo |
| LOG-MIN-11 | Hết hạn, retry, replay, bản sao và restore tuân theo policy lưu giữ được xác định | Fixture thời gian và diễn tập phục hồi |
| LOG-MIN-12 | Phát hiện vi phạm tạo cảnh báo đã giảm dữ liệu, không sao chép secret vào hệ thống báo lỗi mới | Canary phát hiện và kiểm tra nội dung cảnh báo |
| LOG-MIN-13 | Việc giảm dữ liệu vẫn giữ đủ thông tin cho các tác vụ vận hành hoặc audit đã chốt | Ca đối chiếu sự kiện và điều tra tổng hợp |
| LOG-MIN-14 | Thay schema, agent, sink hoặc mục đích sử dụng kích hoạt xem xét yêu cầu liên quan | Lịch sử thay đổi và bằng chứng nghiệm thu |

### 11.1. Đặc tả chi tiết cho lỗi xuất báo cáo

```text
Mục đích:
  Phân loại nguyên nhân lỗi và đối chiếu một request trong phạm vi vận hành.

Field cho phép:
  Event ID, thời điểm, operation ID hữu hạn, failure code hữu hạn,
  request ID không cấp quyền và deployment revision từ nguồn tin cậy.

Field không ghi vào loại sự kiện này:
  Nội dung báo cáo, email, địa chỉ, credential, token,
  request/response thô và Throwable chưa được kiểm soát.

Kênh cần kiểm tra:
  Logger, console, file đệm, agent, collector, index và export liên quan.

Khi không tạo được bản ghi an toàn:
  Không phát hành payload gốc; dùng tín hiệu tối giản theo policy.

Nghiệm thu:
  Sự kiện an toàn vẫn cho phép phân loại và đối chiếu request thử.
  Canary secret và PII bị cấm không xuất hiện ở những kênh đã liệt kê.
  Quyền đọc và thời hạn giữ đúng policy của sự kiện.
```

Nếu cần audit ai đã yêu cầu xuất, dùng loại audit có schema và quyền riêng phù hợp. Không mở rộng log vận hành bằng cách đính kèm toàn bộ tài khoản.

## 12. Kiểm thử bằng dữ liệu tổng hợp và quan sát đường đi

### 12.1. Chọn fixture có thể truy vết

Đặt marker khác nhau theo nguồn và nhóm dữ liệu:

```text
SYNTHETIC_ONLY_PASSWORD_6A21
SYNTHETIC_ONLY_SERVER_TOKEN_9D43
PII_FIXTURE_CONTACT_2F18
PII_FIXTURE_ADDRESS_7C52
```

Các marker không có quyền truy cập thật và không thuộc một người thật. Dùng riêng marker cho request, credential server, upstream error, cause và suppressed exception để xác định đường nào lọt qua.

Với kiểm thử scanner theo định dạng, dùng fixture tổng hợp của bộ thử và xác nhận không phải dữ liệu đang hoạt động. Không dùng secret hoặc hồ sơ thật để kiểm tra xem pipeline có ghi chúng không.

### 12.2. Ma trận kiểm thử minh họa

| Ca | Điều kiện kích hoạt | Điều kiện đạt |
|---|---|---|
| TC-MIN-01 | Một lỗi vận hành bình thường | Chỉ có field được phép, vẫn đủ mã và request ID để đối chiếu |
| TC-MIN-02 | Canary trong password, token, cookie và header | Không có giá trị ở sink bị cấm, kể cả capture tự động |
| TC-MIN-03 | Secret server bị upstream đưa vào exception và cause | Không lọt qua formatter hoặc exporter ngoài policy |
| TC-MIN-04 | Thêm field PII trong object lồng nhau và mảng | Schema không tự thu field mới hoặc serialize toàn object |
| TC-MIN-05 | URL chứa token, email hoặc tham số riêng tư | Log dùng route ID phù hợp, không giữ URL nguyên bản |
| TC-MIN-06 | Dữ liệu encode, xuống dòng, quá dài hoặc có cấu trúc bất thường | Không tạo sự kiện giả, không fallback ra raw data |
| TC-MIN-07 | Redactor hoặc serializer ném lỗi | Payload không an toàn bị bỏ, cảnh báo tối giản không lặp dữ liệu |
| TC-MIN-08 | Agent thu exception trước logger hoặc có sink phụ | Từng đường nhận giữ đúng policy, không chỉ index cuối |
| TC-MIN-09 | Bật debug bằng cấu hình hoặc request trong phạm vi thử | Không vượt giới hạn field và quyền đã chốt |
| TC-MIN-10 | Context được tái sử dụng qua request hoặc job | Không gắn PII, tenant hoặc subject của luồng trước sang luồng sau |
| TC-MIN-11 | Log vận hành và audit cùng một hành động | Subject reference chỉ ở nơi có mục đích và quyền tương ứng |
| TC-MIN-12 | Vai trò sai hoặc tenant khác tìm kiếm, tra ngược, export | Không nhận dữ liệu ngoài phạm vi |
| TC-MIN-13 | Sự kiện tới biên retention, đến muộn hoặc replay | Hành vi hết hạn đúng policy, không tự kéo dài vô ý |
| TC-MIN-14 | Restore backup hoặc index cũ | Áp dụng lại điều kiện dữ liệu trước khi mở đường truy cập |
| TC-MIN-15 | Scanner phát hiện canary trong kênh thử được kiểm soát | Cảnh báo không sao chép giá trị bị phát hiện sang ticket hoặc metric |
| TC-MIN-16 | Điều tra một lỗi tổng hợp sau khi đã giảm dữ liệu | Người có quyền vẫn hoàn thành tác vụ đã chốt, không cần dump payload |

### 12.3. Điều kiện quan sát để tránh PASS giả

Một ca chỉ có giá trị khi nhánh mục tiêu thực sự chạy. Nếu request bị chặn trước HTTP client, chưa kiểm thử được việc client có đưa credential vào exception hay không.

Cần xác nhận sự kiện đã đi qua logger, agent và exporter tương ứng. Buffer, sampling, thời gian giao nhận và quyền truy cập kho dữ liệu có thể làm kết quả “không tìm thấy” trở nên thiếu căn cứ.

Kiểm tra những dạng biểu diễn thuộc fixture sau khi giải mã theo định dạng. Không chỉ tìm chuỗi gốc trên byte nén hoặc một trường message trong khi exception renderer có output riêng.

Đồng thời xác minh dữ liệu được phép còn tồn tại. Một pipeline bỏ tất cả sự kiện có thể không phát hành secret nhưng chưa đáp ứng yêu cầu vận hành hoặc audit.

### 12.4. Giới hạn của scanner

Scanner có thể có false positive và false negative. Không coi kết quả không phát hiện là chứng minh mọi nội dung đều an toàn, đặc biệt với free text và secret không theo mẫu quen thuộc.

Kết hợp schema, kiểm tra nguồn field, cấu hình hiệu lực và quan sát runtime. Nếu dùng sampling để phát hiện rủi ro, nêu rõ giới hạn của nó; sampling không chứng minh tính tuân thủ của những bản ghi chưa quan sát.

Kết quả phát hiện cũng phải được giảm dữ liệu. Dùng loại vi phạm, event reference và vị trí đã kiểm soát thay vì đưa nguyên secret vào tên alert, screenshot hoặc ticket rộng quyền.

## 13. Khi phát hiện dữ liệu đã bị ghi sai

Hai mục tiêu cần xử lý song song: ngăn phát hành thêm và xử lý ảnh hưởng của những bản đã tồn tại.

Một trình tự có thể gồm:

1. Xác định nguồn tạo dữ liệu, cấu hình capture và những sink đã nhận.
2. Chặn đường ghi không phù hợp bằng schema, cấu hình hoặc sửa điểm phát hành.
3. Nếu có credential bị lộ, áp dụng revoke hoặc rotate theo loại credential và xác minh hiệu lực xử lý.
4. Hạn chế quyền tìm kiếm và export dữ liệu liên quan trong phạm vi cần thiết.
5. Xử lý bản sao ở index, buffer, queue, file xuất và nơi lưu khác theo khả năng cùng policy.
6. Ghi rõ giới hạn với backup hoặc lưu trữ không hỗ trợ xóa chọn lọc và điều kiện phục hồi.
7. Đối chiếu việc truy cập hoặc sử dụng liên quan theo bằng chứng có được.
8. Bổ sung ca hồi quy bằng canary tổng hợp, không tái sử dụng dữ liệu bị lộ.

Đổi secret không xóa bản sao lịch sử. Xóa bản ghi không làm mất quyền của credential còn hiệu lực. Với PII, cũng không thể coi việc thu hồi token là đã xử lý toàn bộ ảnh hưởng của việc phát hành dữ liệu cá nhân.

Không sao chép dữ liệu nhạy cảm vào chính hồ sơ xử lý để giải thích sự cố. Tham chiếu bằng chứng trong nơi có quyền phù hợp và dùng bản tóm tắt đã giảm dữ liệu cho trao đổi rộng hơn.

## 14. Vận hành và quản lý thay đổi

### 14.1. Theo dõi tín hiệu không mang dữ liệu gốc

Có thể đo số bản ghi bị từ chối schema, số trường bị loại theo nhóm, số lần redaction lỗi, tuổi backlog và kết quả kiểm tra retention.

Metric cần dùng nhãn hữu hạn như loại sự kiện hoặc loại vi phạm. Không dùng email, subject ID, request ID hoặc giá trị secret làm label. Những định danh cần thiết cho điều tra chỉ xuất hiện ở kênh được kiểm soát theo mục đích.

Một bộ đếm bằng không có thể do không có vi phạm, nhưng cũng có thể do detector không chạy. Cần có bằng chứng kiểm tra cơ chế phát hiện bằng fixture hoặc canary phù hợp trong môi trường kiểm soát.

### 14.2. Những thay đổi phải xem xét lại hợp đồng dữ liệu

- Thêm field nghiệp vụ, phương thức xác thực hoặc loại token.
- Thay logger, formatter, HTTP client, agent hoặc cấu hình capture.
- Thêm sink, dashboard, kho phân tích, bên nhận hoặc đường export.
- Mở rộng quyền tra cứu, tra ngược reference hoặc phạm vi tenant.
- Thay mục đích sử dụng, retention, backup và quy trình restore.
- Bật chẩn đoán tạm thời hoặc chuyển dữ liệu giữa môi trường.

Khi thay đổi, cập nhật schema và ca thử liên quan. Không dùng kết quả nghiệm thu cũ để kết luận một agent mới không thu thêm body hoặc header.

Registry sự kiện có thể giữ mục đích, field, nguồn, phân loại, người sở hữu và policy lưu giữ. Đưa các thông tin này vào hợp đồng kỹ thuật giúp việc kiểm tra thay đổi cụ thể hơn một ghi chú chung “tuân thủ privacy”.

## 15. Truy vết rủi ro tới tiêu chí nghiệm thu

Một chuỗi minh họa:

```text
Rủi ro:
  Raw exception chứa token và email bị thu tự động trước redaction.
    -> LOG-MIN-02, LOG-MIN-04, LOG-MIN-06, LOG-MIN-09
    -> DTO allowlist và cấu hình capture theo từng ranh giới
    -> TC-MIN-02, TC-MIN-03, TC-MIN-07, TC-MIN-08
    -> nội dung thực nhận ở logger, buffer, agent và collector
    -> kết luận theo build, cấu hình và sink đã quan sát
```

Hồ sơ nghiệm thu nên ghi build, revision schema, policy field, cấu hình hiệu lực, danh mục sink, fixture, kết quả từng ca và phần chưa quan sát được.

Một tiêu chí đo được có thể là:

> Trong các luồng và sink đã liệt kê, mọi ca bắt buộc được kích hoạt đúng nhánh; sự kiện chỉ có field được phép theo mục đích; không có canary secret hoặc PII bị cấm trong cửa sổ quan sát đã chốt; quyền đọc, export và retention đạt policy; tác vụ vận hành hoặc audit được yêu cầu vẫn thực hiện được. Phần chưa có bằng chứng được ghi riêng, không tính là PASS.

Tiêu chí này không khẳng định mọi chuỗi tự do trong mọi cấu hình tương lai đều đã được chứng minh an toàn. Độ tin cậy đến từ việc giới hạn luồng dữ liệu, kiểm chứng các ranh giới và cập nhật bằng chứng khi phạm vi thay đổi.

## 16. Thực hành đặc tả cho hệ thống hỗ trợ khách hàng

Một API tiếp nhận yêu cầu hỗ trợ có email, số điện thoại, nội dung mô tả và file đính kèm. Người dùng đôi khi dán token hoặc thông tin riêng tư vào free text. Backend ghi toàn bộ body ở DEBUG, HTTP client ghi lỗi upstream và frontend gửi response lỗi tới dịch vụ theo dõi. Đội hỗ trợ có thể export kết quả tìm kiếm log; backup được lưu riêng.

Hãy xây dựng một đặc tả gồm:

1. Phân loại secret, PII, metadata nội bộ và dữ liệu công khai theo khả năng sử dụng.
2. Hai mục đích riêng cho log vận hành và audit; giải thích field thực sự cần cho mỗi mục đích.
3. Schema allowlist không nhận raw body, credential hoặc toàn bộ principal.
4. Cách xử lý URL, header, free text, exception, object lồng nhau và file metadata.
5. Ranh giới phải loại dữ liệu trước logger, agent, exporter và frontend telemetry.
6. Hành vi khi redaction hoặc serialization thất bại, không dùng raw payload làm fallback.
7. Chính sách reference, quyền tra ngược, tenant và export.
8. Retention, bản sao, queue, backup và điều kiện restore.
9. Bộ fixture tổng hợp cùng oracle xác nhận đã đi qua từng nhánh mục tiêu.
10. Cách phát hiện vi phạm và tạo hồ sơ xử lý không sao chép dữ liệu nhạy cảm.

Kết quả cần cho người khác thấy được mỗi field được ghi vì mục đích gì, nơi nào được nhận nó, ai có quyền sử dụng, bao lâu phải hết hiệu lực và bằng chứng nào xác nhận dữ liệu không cần thiết đã được giữ ngoài luồng logging.
