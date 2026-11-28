# Credential không nằm trong log

## 1. Từ lời nhắc lập trình đến yêu cầu bảo mật

“Đừng log password” là một lời nhắc đúng nhưng chưa đủ để nghiệm thu một hệ thống. Credential có thể đi vào access log của gateway trước khi ứng dụng nhận request, xuất hiện trong thông báo lỗi của HTTP client, được gắn vào trace, hoặc bị một công cụ hỗ trợ kỹ thuật sao chép sang ticket. Một dòng log ở chế độ DEBUG cũng có thể tồn tại trong bản sao lưu lâu hơn chính credential đó.

Trong chương Token và credential, yêu cầu cần đặc tả là: **hệ thống ghi nhận được việc sử dụng credential và kết quả xác thực, nhưng không biến kênh quan sát thành nơi lưu giá trị bí mật có thể dùng để xác thực**. Bài học tập trung chuyển mục tiêu này thành phạm vi kiểm soát, hợp đồng dữ liệu log và bằng chứng kiểm thử.

Trong bài, credential bao gồm mật khẩu, access token, refresh token, API key, client secret, session secret, mã khôi phục và các giá trị khác có thể giúp một bên chứng minh danh tính hoặc giành quyền truy cập. Phạm vi còn bao gồm vật liệu mật mã và dữ liệu xác minh bí mật; không chỉ những chuỗi có tên trường là `password`.

Một yêu cầu có thể kiểm chứng cần trả lời ít nhất năm câu hỏi:

1. Những giá trị nào bị cấm xuất hiện?
2. Những thành phần và đích lưu nào nằm trong phạm vi?
3. Hệ thống vẫn phải ghi những sự kiện nào để điều tra?
4. Điều gì xảy ra khi phân loại hoặc loại bỏ dữ liệu thất bại?
5. Bằng chứng nào cho thấy kiểm soát hoạt động ở cấu hình thực tế?

Đây là yêu cầu về thiết kế dữ liệu và luồng xử lý, không chỉ là cấu hình một bộ lọc tìm chuỗi.

## 2. Vì sao log là một bề mặt làm lộ credential

Giả sử dịch vụ thanh toán nhận request có `Authorization: Bearer ...`. Bộ xử lý nghiệp vụ không ghi token, nhưng middleware ghi toàn bộ request khi có lỗi. Sau đó collector chuyển log tới một hệ thống tìm kiếm mà nhiều nhóm vận hành được phép truy cập. Một người không có quyền đọc secret store có thể lấy credential từ log và sử dụng nó ở dịch vụ khác.

Đường rò rỉ có thể được mô tả như sau:

```text
Credential trong request hoặc cấu hình
          |
          v
Middleware / client / exception / công cụ debug
          |
          v
Đối tượng sự kiện chứa dữ liệu thô
          |
          v
Hàng đợi / stdout / file cục bộ / collector
          |
          v
Kho log / trace / cảnh báo / bản xuất / bản sao lưu
```

Nếu chỉ che token ở giao diện tìm kiếm cuối cùng, dữ liệu thô vẫn có thể nằm trong file cục bộ, hàng đợi và kho gốc. Một người đọc được API xuất dữ liệu có thể nhìn thấy thứ mà giao diện đã che.

Vì vậy, điểm loại bỏ dữ liệu chính phải nằm **trước khi credential được đưa vào sự kiện quan sát, hàng đợi hoặc đích lưu**. Bộ lọc tại collector vẫn có ích như một lớp phòng vệ bổ sung, nhưng không chứng minh được rằng phía trước collector chưa có rò rỉ.

Mã hóa đường truyền và giới hạn người đọc log vẫn cần thiết. Hai biện pháp này bảo vệ log được phép tồn tại; chúng không thay thế yêu cầu không ghi credential. Khi hệ thống log giải mã dữ liệu để tìm kiếm hoặc xuất bản ghi, credential được lưu trong đó vẫn có thể bị lộ.

## 3. Phân loại dữ liệu trước khi thiết kế log

Không phải mọi thứ liên quan tới token đều là credential. Một yêu cầu quá rộng như “không log bất kỳ thông tin nào về xác thực” sẽ làm mất bằng chứng phát hiện tấn công. Ngược lại, coi mọi ID là vô hại có thể làm lộ giá trị dùng được để truy cập.

| Nhóm dữ liệu | Ví dụ | Chính sách trong thiết kế minh họa |
|---|---|---|
| Giá trị xác thực bí mật | Password, bearer token, refresh token, API key, client secret | Không ghi giá trị toàn phần hoặc phần có thể sử dụng để xác thực |
| Secret đi kèm cơ chế khôi phục | Mã reset mật khẩu, recovery code, OTP còn hiệu lực | Không ghi; chỉ ghi loại thao tác và kết quả |
| Vật liệu mật mã bí mật | Private key, khóa ký, khóa mã hóa, seed bí mật | Không ghi và không đưa vào thông báo lỗi |
| Vật liệu xác minh nhạy cảm | Password hash, cấu hình chứa secret | Không coi là dữ liệu debug thông thường; loại khỏi log |
| Định danh nội bộ đã phân loại | ID bản ghi credential, ID dịch vụ, phiên bản khóa | Chỉ ghi nếu bản thân ID không cấp quyền và có mục đích điều tra rõ ràng |
| Metadata của quyết định | Loại credential, mã kết quả, mã lý do, route chuẩn hóa | Có thể ghi theo schema đã phê duyệt |
| Nội dung người dùng kiểm soát | Header tùy ý, URL, body, tên tài khoản nhập vào | Không được đưa thẳng vào log; phân loại và giới hạn trước |

Một URL ký sẵn có thể cấp quyền tải tài liệu dù không chứa trường `token`. Chuỗi kết nối có thể chứa mật khẩu. Một cookie có thể vừa mang preference vừa mang session secret. Phân loại phải dựa trên khả năng cấp quyền và mức nhạy cảm, không dựa riêng vào tên biến hoặc vị trí truyền tải.

Các thuộc tính như `sub`, `jti`, email hoặc tên tài khoản cũng không mặc nhiên được ghi. Chúng có thể tạo khả năng theo dõi người dùng hoặc chứa dữ liệu do bên ngoài kiểm soát. Đội thiết kế cần chọn dữ liệu tối thiểu cho mục đích điều tra, kèm quyền truy cập và thời hạn lưu tương ứng.

Nếu một trường được đặt tên `credential_id` nhưng giá trị của nó cũng được chấp nhận như API key, nó vẫn là credential và phải bị loại. Đổi tên trường không làm thay đổi tính chất bảo mật.

## 4. Xác định phạm vi end-to-end

Phạm vi yêu cầu nên được ghi thành danh mục thành phần thực tế. Việc chỉ kiểm tra các lệnh `logger.info` trong mã nghiệp vụ sẽ bỏ sót những nơi tự động thu thập dữ liệu.

| Vị trí | Nguồn rò rỉ thường gặp | Trách nhiệm cần xác định |
|---|---|---|
| Gateway, reverse proxy, load balancer | Request URI đầy đủ, header, access log mặc định | Chủ hạ tầng xác định field được phép và cấu hình log |
| Ứng dụng | Request dump, DTO `toString`, câu lệnh log tạm | Chủ dịch vụ sở hữu schema sự kiện và điểm phát sinh |
| HTTP client và SDK | Wire logging, request/response body, lỗi từ bên thứ ba | Chủ tích hợp cấu hình capture và ánh xạ lỗi |
| Authentication middleware | Token lỗi, thông báo xác minh, cookie | Chủ xác thực ghi mã lý do thay cho dữ liệu bí mật |
| Agent quan sát và tracing | Span attribute, baggage, exception event, auto capture | Chủ nền tảng quy định trường và cấu hình thu thập |
| Container và hệ điều hành | stdout, stderr, crash output, cấu hình khởi động | Chủ runtime kiểm soát đường xuất và diagnostic artifact |
| Collector và kho quan sát | Bản sao thô, retry buffer, dead-letter queue, index | Chủ logging kiểm soát lọc bổ sung và quyền truy cập |
| Cảnh báo và hỗ trợ vận hành | Email, webhook, chat, ticket, file tải xuống | Chủ quy trình giới hạn payload và quyền chia sẻ |

Phải bao phủ cả sự kiện thành công và thất bại. Những đường lỗi như token hết hạn, chữ ký sai, credential bị thu hồi hoặc upstream timeout thường có nhiều dữ liệu chẩn đoán hơn đường thành công.

Môi trường phát triển, kiểm thử và staging cũng cần chính sách rõ ràng. Một môi trường có thể dùng tài khoản thử nhưng vẫn kết nối dịch vụ trả phí hoặc tài nguyên dùng chung. “Không phải production” không phải bằng chứng rằng credential có thể công khai.

Với diagnostic artifact như heap dump hoặc core dump, không nên hứa rằng một bộ lọc log sẽ loại hết secret trong bộ nhớ. Chúng cần chính sách tạo, truy cập, lưu và hủy riêng. Yêu cầu logging phải ngăn việc tự động đính kèm các artifact này vào kênh log hoặc ticket thông thường.

## 5. Viết bộ yêu cầu có thể nghiệm thu

Các mã dưới đây là ví dụ cho một hệ thống giả định. Đội dự án phải liên kết chúng với mô hình đe dọa, danh mục thành phần và chủ sở hữu của hệ thống mình.

### LOG-CRED-01 — Không phát sinh giá trị bí mật

Mọi thành phần trong phạm vi không được đưa giá trị credential, private key, password hash hoặc secret cấu hình vào log, trace, metric label, thông báo cảnh báo hay artifact quan sát thông thường. Điều này áp dụng cho thông điệp, trường có cấu trúc, exception, request/response capture và dữ liệu do thư viện tự động bổ sung.

**Bằng chứng:** schema sự kiện; cấu hình các điểm capture; kết quả thử nghiệm bằng credential tổng hợp trên các đường xử lý đã xác định.

### LOG-CRED-02 — Schema cho phép thay cho ghi đối tượng tùy ý

Sự kiện xác thực phải được tạo từ một schema có danh sách trường được phép. Không serialize nguyên request, response, đối tượng credential hoặc cấu hình môi trường để ghi log. Trường không có trong schema không được tự động xuất ra.

**Bằng chứng:** hợp đồng field; điểm gọi API ghi sự kiện; kiểm thử thêm field nhạy cảm mới vào đối tượng đầu vào mà không làm thay đổi payload log.

### LOG-CRED-03 — Loại bỏ trước điểm lưu hoặc truyền

Credential phải được loại trước khi tạo payload cho logging appender, hàng đợi bất đồng bộ, tracing exporter hoặc stdout/stderr. Collector có lớp phát hiện và lọc bổ sung, nhưng không phải điểm loại bỏ duy nhất.

**Bằng chứng:** quan sát payload tại ranh giới ứng dụng, appender và collector; cấu hình buffer và retry; dữ liệu ghi cục bộ trong cùng kịch bản.

### LOG-CRED-04 — Bao phủ mọi mức log và đường lỗi

Chính sách phải giữ hiệu lực ở các mức INFO, WARN, ERROR, DEBUG và TRACE được phép sử dụng trong môi trường triển khai. Việc bật hỗ trợ chẩn đoán không được kích hoạt request dump, wire logging hoặc exception capture có credential.

**Bằng chứng:** ma trận cấu hình được hỗ trợ; kiểm thử chuyển mức log; cấu hình ghi đè lúc chạy và quy trình thay đổi cấu hình.

### LOG-CRED-05 — Sự kiện điều tra vẫn đầy đủ

Hệ thống phải ghi sự kiện liên quan tới phát hành, sử dụng thất bại, thu hồi và thay đổi credential theo thiết kế audit đã phê duyệt, với định danh không bí mật và kết quả thích hợp. Không dùng giải pháp tắt toàn bộ logging để đáp ứng yêu cầu loại secret.

**Bằng chứng:** các sự kiện mong đợi xuất hiện khi chạy kịch bản; có mã liên kết để theo dõi cùng một thao tác mà không cần token.

### LOG-CRED-06 — Lỗi xử lý log không làm bật đường ghi thô

Nếu bộ xử lý trường nhạy cảm, formatter hoặc exporter lỗi, hệ thống không được ghi lại payload gốc như một cơ chế fallback. Đường xử lý dự phòng chỉ được phát ra mã lỗi cố định và metadata đã được phân loại an toàn, hoặc bỏ sự kiện theo chính sách đã quyết định.

**Bằng chứng:** fault injection với lỗi formatter, lỗi collector và lỗi hàng đợi; không có request, exception message hoặc secret trong output dự phòng.

Quyết định có tiếp tục giao dịch khi audit không ghi được hay không thuộc yêu cầu audit và khả dụng riêng. Dù quyết định là tiếp tục hay từ chối giao dịch, hệ thống vẫn không được phát tán credential để báo lỗi logging.

### LOG-CRED-07 — Không tạo kênh vòng qua chính sách

Cấu hình runtime, endpoint debug, công cụ hỗ trợ và job xuất dữ liệu không được có chế độ bỏ qua chính sách credential. Thay đổi chính sách capture phải có chủ sở hữu, được đánh giá tác động và được ghi nhận bằng sự kiện không chứa secret.

**Bằng chứng:** cấu hình triển khai; quyền thay đổi; kịch bản bật debug hoặc xuất bản ghi.

### LOG-CRED-08 — Bằng chứng quét không làm lộ secret lần nữa

Công cụ phát hiện credential trong log phải hạn chế quyền đọc và không đưa đoạn khớp bí mật vào cảnh báo, tên file, artifact CI hoặc ticket. Kết quả báo cáo chỉ cần loại phát hiện, vị trí bản ghi, mã kiểm thử và số lượng phù hợp.

**Bằng chứng:** payload cảnh báo khi cố ý đưa secret tổng hợp vào đích kiểm thử có kiểm soát; quyền truy cập của công cụ và chính sách artifact.

Một câu yêu cầu như “không có credential trong log” có thể được dùng làm mục tiêu tổng quát. Tám yêu cầu chi tiết trên biến mục tiêu đó thành các trách nhiệm và bằng chứng khác nhau, tránh để một kết quả grep đơn lẻ đại diện cho toàn bộ thiết kế.

## 6. Thiết kế sự kiện vẫn hữu ích khi không có token

Đội vận hành thường muốn biết “credential nào gặp lỗi” để liên hệ với người sở hữu hoặc xác định tác động. Cách thiết kế phù hợp là tạo định danh quản trị không bí mật, tách khỏi giá trị dùng để xác thực.

Ví dụ sự kiện:

```json
{
  "event": "credential_validation_failed",
  "service": "payment-api",
  "request_id": "req-demo-2041",
  "route": "/payments/{paymentId}",
  "credential_type": "ACCESS_TOKEN",
  "reason_code": "EXPIRED",
  "credential_record_id": "cred-record-demo-27"
}
```

Giá trị trong ví dụ là dữ liệu minh họa. `credential_record_id` chỉ được ghi khi có sẵn từ một nguồn được tin cậy và được phân loại là không cấp quyền. Khi không xác định được bản ghi credential, có thể bỏ trường hoặc dùng một giá trị cố định như `UNKNOWN`; không lấy token làm ID thay thế.

`request_id` giúp liên kết gateway, ứng dụng và upstream. ID nên được tạo hoặc xác thực theo hợp đồng của hệ thống, có giới hạn độ dài và được xuất bằng serializer an toàn. Không chấp nhận header tùy ý rồi sao chép nguyên vào trường này.

Route chuẩn hóa cho biết loại endpoint mà không chép toàn bộ query string hay giá trị đường dẫn. Nếu cần một resource ID cụ thể, nó phải qua quyết định phân loại riêng; route chuẩn hóa không tự động làm mọi metadata trở nên vô hại.

### Không mặc định dùng hash của secret để liên kết

Hash một password rồi ghi ra log vẫn tạo thêm dữ liệu có thể hỗ trợ dò đoán, và không cần thiết cho phần lớn mục đích điều tra. Với token, hash có thể trở thành định danh bền vững giúp liên kết nhiều hoạt động vốn không cần liên kết.

Ưu tiên request ID, session record ID không cấp quyền hoặc credential record ID nội bộ. Chỉ xem xét fingerprint dẫn xuất khi thực sự cần và đã đánh giá loại secret, entropy, nguy cơ liên kết, khóa bảo vệ, phân quyền và thời hạn lưu. Không coi việc đổi từ plaintext sang hash là tự động đáp ứng yêu cầu.

Với token tự chứa, việc giải mã phần payload để lấy một claim cũng không đồng nghĩa claim đã đáng tin. Không dùng claim chưa được xác minh làm kết luận rằng một người dùng hay credential cụ thể đã thực hiện hành động.

## 7. Ví dụ Java: giới hạn dữ liệu ngay ở API logging

Đoạn mã sau minh họa hợp đồng hẹp cho một loại sự kiện xác thực. Nó không phải một framework logging hoàn chỉnh. Điểm chính là API không nhận request, token, password hay exception tùy ý.

```java
import java.util.Objects;
import java.util.UUID;
import java.util.function.Consumer;

public final class CredentialAuditExample {
    enum CredentialType {
        ACCESS_TOKEN, API_KEY, SESSION, PASSWORD
    }

    enum FailureReason {
        MISSING, INVALID, EXPIRED, REVOKED, DEPENDENCY_UNAVAILABLE
    }

    enum RouteId {
        CREATE_PAYMENT, READ_PAYMENT
    }

    record CredentialFailureEvent(
            UUID requestId,
            RouteId route,
            CredentialType credentialType,
            FailureReason reason) {

        CredentialFailureEvent {
            Objects.requireNonNull(requestId);
            Objects.requireNonNull(route);
            Objects.requireNonNull(credentialType);
            Objects.requireNonNull(reason);
        }
    }

    static final class CredentialAudit {
        private final Consumer<CredentialFailureEvent> sink;

        CredentialAudit(Consumer<CredentialFailureEvent> sink) {
            this.sink = Objects.requireNonNull(sink);
        }

        void validationFailed(
                UUID requestId,
                RouteId route,
                CredentialType type,
                FailureReason reason) {
            sink.accept(new CredentialFailureEvent(
                    requestId, route, type, reason));
        }
    }

    public static void main(String[] args) {
        CredentialAudit audit = new CredentialAudit(System.out::println);
        UUID requestId = UUID.randomUUID();

        audit.validationFailed(
                requestId,
                RouteId.CREATE_PAYMENT,
                CredentialType.ACCESS_TOKEN,
                FailureReason.EXPIRED);
    }
}
```

Ví dụ dùng enum và UUID do hệ thống tạo nên không có chỗ để một caller truyền token vào trường lý do hoặc route. Khi thiết kế thực tế cần thêm field, từng field phải có mục đích và quy tắc phân loại; không thêm `Map<String, Object> extra` rồi cho phép tùy ý đưa dữ liệu vào.

Adapter của `sink` trong hệ thống thật vẫn phải kiểm soát serializer, context tự động, quyền truy cập, việc chuyển dữ liệu và lỗi ghi. Một API hẹp giảm nguy cơ từ caller nhưng không bảo đảm agent hoặc appender bên ngoài không thu thập thêm dữ liệu.

Ví dụ những cách gọi cần tránh:

```java
// Các dòng sau minh họa anti-pattern, không phải cách triển khai được phép.
logger.debug("incoming request: {}", request);
logger.warn("invalid credential: {}", rawCredential);
logger.error("authentication failed: {}", exception.getMessage());
logger.debug("client configuration: {}", clientConfiguration);
```

Việc dùng placeholder của logger không tự che secret. Nó giúp định dạng thông điệp, nhưng đối tượng được truyền vào vẫn có thể bị chuyển thành chuỗi chứa credential. Structured logging cũng chỉ thay cách biểu diễn; một field JSON mang raw token vẫn là rò rỉ.

Nếu thư viện tạo exception có URL, header hoặc body trong message, không truyền nguyên message hoặc nguyên throwable vào kênh quan sát thông thường. Cần ánh xạ sang mã lỗi nội bộ và cấu hình công cụ thu exception. Cả `cause`, suppressed exception và các thuộc tính do agent tự động gắn thêm cũng cần nằm trong phạm vi thiết kế.

## 8. Vai trò và giới hạn của redaction

Redaction là loại bỏ hoặc thay thế một giá trị nhạy cảm bằng dấu cố định như `[REDACTED]`. Nó hữu ích khi có trường nằm ở ranh giới tích hợp chưa thể thay đổi ngay, hoặc để bảo vệ thêm ở collector.

Tuy nhiên, redaction dựa trên blacklist khó bao phủ mọi cách biểu diễn:

- Cùng một secret có thể nằm trong header, cookie, query, body, URL ký sẵn hoặc một exception.
- Tên field có thể khác nhau giữa nhà cung cấp và các lớp lồng nhau.
- Dữ liệu có thể được URL-encode, JSON-escape, chia thành nhiều trường hoặc ghi nhiều dòng.
- Một token có thể không khớp hình thức mà biểu thức chính quy đang nhận diện.
- Formatter có thể chuyển cả đối tượng thành một chuỗi trước khi bộ lọc field chạy.

Vì vậy, thứ tự ưu tiên là giảm capture, dùng schema cho phép, loại dữ liệu nhạy cảm tại nguồn, rồi mới dùng bộ lọc bổ sung. Không nên thu toàn bộ request chỉ vì “đã có regex che token”.

Nếu một pipeline bắt buộc xử lý dữ liệu hỗn hợp, hợp đồng redaction phải mô tả cấu trúc đầu vào, trường lồng nhau, mảng, so sánh tên trường, giới hạn kích thước, kiểu dữ liệu không hợp lệ và hành vi khi lỗi. Gặp input không phân loại được thì không xuất nguyên input ra log để giúp điều tra lỗi bộ lọc.

Không dùng phương án che phần giữa làm mặc định cho credential. Một phần còn lại có thể đủ để đối chiếu, suy luận hoặc phục vụ tấn công, tùy định dạng và cơ chế xác thực. Nếu chỉ cần biết một secret đã bị loại, marker cố định thường đủ.

Đối với input có ký tự xuống dòng hoặc delimiter, serializer và bộ mã hóa đầu ra phải ngăn việc giả mạo một bản ghi mới. Chống log injection bổ sung tính toàn vẹn của sự kiện; nó không thay thế việc loại secret.

## 9. Lập ma trận kiểm thử theo đường rò rỉ

Kiểm thử cần dùng credential tổng hợp hoặc tài nguyên thử chuyên biệt có kiểm soát. Không sao chép credential production vào bộ test, snapshot hoặc lệnh tìm kiếm để chứng minh rằng nó không xuất hiện trong log.

Mỗi lần chạy có thể sinh một marker khác nhau cho từng đường vào. Marker cần đủ đặc trưng để phát hiện và phải được quản lý trong test harness, thay vì in toàn bộ vào báo cáo CI.

| Kịch bản | Điểm kích hoạt | Những đích phải quan sát | Kết quả mong đợi |
|---|---|---|---|
| Xác thực thành công | Credential thử hợp lệ | Gateway, app, audit, trace, collector | Có sự kiện cần thiết; không có giá trị credential |
| Token hết hạn hoặc sai | Đường từ chối xác thực | Error log, exception event, access log | Có mã lý do phù hợp; không có token hoặc message chứa token |
| Refresh thất bại | Refresh token thử | Auth service, HTTP client, retry log | Không xuất refresh token và response nhạy cảm |
| Upstream timeout | Gọi dịch vụ bằng API key thử | Client log, circuit-breaker event, trace | Có thông tin lỗi vận hành an toàn; không có header bí mật |
| Bật mức DEBUG được hỗ trợ | Thay cấu hình lúc chạy | Wire log, stdout, agent | Chính sách loại credential tiếp tục hiệu lực |
| Collector không sẵn sàng | Lỗi mạng hoặc queue đầy | Buffer, fallback, stderr | Không ghi payload thô trong đường dự phòng |
| Body hoặc URL bất thường | Cấu trúc lồng, encoding, nhiều dòng | Capture middleware, parser error, access log | Không phát sinh bản dump chứa secret |
| Xuất cảnh báo hoặc ticket | Sự kiện lỗi xác thực | Webhook, email, file xuất | Chỉ có metadata được phép và định danh liên kết |

Một số hệ thống dùng request body hợp lệ cho logging nhưng gateway vẫn ghi URI ban đầu. Cần kiểm thử cả request bị từ chối trước ứng dụng, vì những request này không đi qua bộ lọc của ứng dụng.

Với endpoint buộc phải tiếp nhận secret trong URL theo một tích hợp đặc thù, phải kiểm soát các lớp nhìn thấy URL trước khi request tới ứng dụng. Việc loại query trong application log không sửa được access log đã phát sinh ở gateway. Thiết kế giao thức nên tránh đặt credential trong URL khi có lựa chọn phù hợp.

Không chỉ tìm marker trong kho tập trung. Cần kiểm tra các đích cục bộ và trung gian được liệt kê trong phạm vi, kể cả bản ghi bị loại ở collector, bộ đệm retry và dữ liệu trace. Nếu không có quyền quan sát một đích, báo giới hạn bằng chứng và giao chủ thành phần xác minh, thay vì mặc định đích đó an toàn.

## 10. Tiêu chí chấp nhận và cách đọc kết quả

Một bộ tiêu chí minh họa có thể gồm:

1. Mọi thành phần trong danh mục có chủ sở hữu và cấu hình capture được ghi nhận.
2. Sự kiện xác thực chỉ dùng schema đã phê duyệt; không có trường tùy ý chứa request hoặc secret.
3. Mọi kịch bản trong ma trận đã được thực thi ở cấu hình cần hỗ trợ.
4. Không phát hiện marker credential thử tại bất kỳ đích nào được kiểm tra, kể cả stderr và output dự phòng.
5. Sự kiện điều tra mong đợi vẫn xuất hiện và liên kết được bằng ID không bí mật.
6. Khi bộ lọc hoặc exporter lỗi, không phát sinh bản ghi dữ liệu thô.
7. Báo cáo kiểm thử và cảnh báo không chứa giá trị secret được phát hiện.

Mức “không phát hiện” là kết quả trong phạm vi và thời gian thử nghiệm, không phải chứng minh toán học rằng mọi input tương lai đều không thể rò rỉ. Bằng chứng mạnh hơn cần kết hợp thiết kế schema, giảm capture, cấu hình các lớp và thử nghiệm đường lỗi.

Nếu dùng tỷ lệ bao phủ, mẫu số phải là danh mục cụ thể. “100% log an toàn” không có ý nghĩa rõ ràng nếu không biết đang đếm thành phần, event type hay kịch bản. Một chỉ số hữu ích hơn là “12/12 điểm capture thuộc phạm vi đã được cấu hình và kiểm tra trong cấu hình production tương đương”. Con số này chỉ là ví dụ, không phải mức tối thiểu áp dụng cho mọi hệ thống.

Việc quét không có kết quả cũng có thể do test không đi qua nhánh cần kiểm tra, log chưa được flush, sampling bỏ bản ghi hoặc collector chưa nhận dữ liệu. Test harness cần xác nhận các sự kiện an toàn tương ứng đã tới các đích mong đợi, và phân biệt không có rò rỉ với không có dữ liệu quan sát.

Đối với log có độ trễ, phải xác định cửa sổ chờ và điều kiện kết thúc kiểm tra. Đối với các lớp có sampling, cần cấu hình thử nghiệm bảo đảm đường kiểm tra được quan sát hoặc có bằng chứng thay thế phù hợp. Không suy rằng một token không xuất hiện chỉ vì bản ghi đã bị sampling bỏ qua.

## 11. Xử lý khi đã phát hiện credential trong log

Phát hiện secret trong log cần kích hoạt quy trình sự cố phù hợp với khả năng credential đã bị truy cập. Việc sửa câu lệnh log chỉ ngăn một phần phát sinh mới; nó không làm credential đã ghi trở nên an toàn.

Luồng xử lý nên bao gồm:

1. Ngăn đường capture đang rò rỉ và hạn chế quyền truy cập vào dữ liệu liên quan.
2. Xác định loại credential, phạm vi quyền, thời gian lộ, đích đã nhận dữ liệu và các bản sao có thể có.
3. Thu hồi hoặc xoay vòng credential theo khả năng hệ thống, đồng thời xử lý các phụ thuộc cần cập nhật.
4. Đánh giá dấu hiệu sử dụng bất thường trong khoảng thời gian liên quan bằng metadata an toàn.
5. Bảo toàn bằng chứng cần thiết trong vùng hạn chế theo quy trình sự cố, rồi xử lý dữ liệu và bản sao theo chính sách đã thống nhất.
6. Bổ sung kiểm soát và kịch bản tái hiện đường rò rỉ mà không dùng secret thật.

Không đưa secret vào ticket để chứng minh sự cố. Dùng mã bản ghi, khoảng thời gian, tên nguồn và loại credential. Nếu cần tiếp cận bằng chứng gốc, dùng kênh được phân quyền riêng.

Việc xóa log cần phối hợp với trách nhiệm bảo toàn bằng chứng và lưu trữ của hệ thống; không tự động xóa toàn bộ audit trail chỉ vì một bản ghi có secret. Đồng thời, không chờ xóa sạch mọi bản sao mới xử lý credential bị lộ. Khi có thể, thu hồi hoặc xoay vòng sớm giúp vô hiệu hóa khả năng sử dụng tiếp giá trị đó.

## 12. Những cách đặc tả dễ gây hiểu nhầm

| Cách viết chưa đủ | Vì sao khó nghiệm thu | Cách làm rõ |
|---|---|---|
| “Không log password” | Bỏ sót token, API key, cookie, mã khôi phục | Liệt kê nhóm credential và vật liệu bí mật theo khả năng cấp quyền |
| “Logger tự mask dữ liệu” | Không rõ ở nguồn hay ở giao diện cuối | Nêu điểm loại bỏ trước queue và mọi đích quan sát |
| “Log production không có secret” | Debug hoặc staging có thể dùng credential thật | Xác định mọi môi trường và cấu hình được hỗ trợ |
| “Có regex nhận dạng token” | Không bao phủ cấu trúc và định dạng tùy ý | Giảm capture, schema cho phép, lọc bổ sung và kiểm thử |
| “Đã dùng JSON log” | JSON vẫn có thể mang raw credential | Giới hạn field và nguồn giá trị của từng field |
| “Log đã được mã hóa” | Người hoặc dịch vụ được đọc vẫn lấy được credential | Loại credential; bảo vệ truy cập như một yêu cầu riêng |
| “Tắt toàn bộ auth log” | Mất khả năng phát hiện và điều tra | Ghi loại thao tác, kết quả, mã lý do và ID không bí mật |
| “Quét không thấy token nên PASS” | Có thể chưa chạy đúng nhánh hoặc log chưa tới | Xác nhận sự kiện đối chứng và phạm vi đích kiểm tra |

Một đặc tả tốt làm rõ cả dữ liệu bị cấm lẫn dữ liệu phải có. Nó giúp đội phát triển, nền tảng và vận hành đạt cùng một kết quả mà không cần giả định tất cả đều hiểu giống nhau về từ “log”.

## 13. Bài tập áp dụng

Một API đăng nhập không log password trong controller. Khi xác thực lỗi, HTTP client ghi response body từ identity provider vào exception; agent quan sát tự động thu exception. Gateway ghi toàn bộ URI, còn đội hỗ trợ có quyền tải log ứng dụng nhưng không có quyền truy cập secret store.

Hãy thực hiện các bước sau trên thiết kế của tình huống:

1. Vẽ các điểm credential hoặc nội dung chứa credential có thể được sao chép sang kênh quan sát.
2. Viết một yêu cầu loại dữ liệu tại nguồn và một yêu cầu dành cho agent quan sát.
3. Chọn các field an toàn cần giữ để điều tra một lần xác thực thất bại.
4. Thiết kế kiểm thử khi identity provider trả một message chứa secret tổng hợp.
5. Nêu điều kiện PASS, dữ liệu đối chứng và các đích cần kiểm tra ngoài log ứng dụng.
6. Mô tả cách báo một phát hiện mà không sao chép giá trị bí mật vào ticket.

Kết quả cần chỉ ra ranh giới kiểm soát cụ thể. Câu trả lời “thêm một regex ở collector” chưa xử lý bản ghi ở gateway, exception event và những bản sao xuất hiện trước collector.

## 14. Nguồn tham khảo và hướng mở rộng

OWASP khuyến nghị loại hoặc xử lý dữ liệu nhạy cảm như mật khẩu, access token và khóa bí mật trước khi ghi log, đồng thời bảo vệ dữ liệu log đã thu thập. Đây là cơ sở tham khảo cho việc xác định nhóm dữ liệu; schema, phạm vi và mã yêu cầu trong bài là thiết kế minh họa riêng. Xem [OWASP Logging Cheat Sheet — Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

Khi áp dụng vào một hệ thống cụ thể, hãy gắn yêu cầu với danh mục điểm capture, hợp đồng sự kiện, cấu hình runtime và ma trận kiểm thử. Bằng chứng cần cho thấy đồng thời hai điều: credential không bị biến thành dữ liệu quan sát, và hệ thống vẫn có thông tin cần thiết để phát hiện, điều tra và phục hồi sau các vấn đề xác thực.
