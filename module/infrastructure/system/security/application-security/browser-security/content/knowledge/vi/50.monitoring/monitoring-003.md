# Authentication event

Authentication event là sự kiện ghi nhận một bước có ý nghĩa trong vòng đời xác thực của người dùng, thiết bị hoặc phiên làm việc. Các sự kiện này giúp đội vận hành biết một lần đăng nhập đã được thử, được chấp nhận, bị từ chối hay bị gián đoạn; yếu tố xác thực nào đã được dùng; phiên được tạo, gia hạn hoặc thu hồi ra sao; và có dấu hiệu bất thường nào cần điều tra.

Trong ứng dụng web, hoạt động xác thực đi qua nhiều ranh giới: giao diện chạy trong trình duyệt, endpoint đăng nhập, dịch vụ định danh, kho phiên hoặc token, reverse proxy và hệ thống giám sát. Mỗi lớp nhìn thấy một phần khác nhau của quá trình. Muốn có dữ liệu đáng tin cậy, hệ thống phải định nghĩa rõ sự kiện nào được phát ra ở đâu, ý nghĩa của kết quả và dữ liệu nào được phép ghi lại.

Sự kiện xác thực là dữ liệu vận hành và bảo mật có thể chứa dấu vết về tài khoản, thiết bị và hành vi truy cập. Thiết kế sai có thể làm lộ thông tin đăng nhập, tạo cảnh báo giả hoặc khiến nhóm ứng phó không thể dựng lại diễn biến. Bài học này trình bày cách thiết kế, thu thập, bảo vệ và sử dụng authentication event trong ứng dụng web.

## 1. Phân biệt sự kiện xác thực với sự kiện giao diện

Một sự kiện phía trình duyệt chỉ mô tả điều trình duyệt quan sát được. Ví dụ, người dùng bấm nút đăng nhập, biểu mẫu được gửi, trang chuyển sang bước MFA hoặc popup đăng nhập bị đóng. Những sự kiện này hữu ích để phân tích trải nghiệm và lỗi giao diện, nhưng không chứng minh danh tính đã được xác thực.

Kết quả xác thực phải được ghi nhận tại thành phần có thẩm quyền quyết định kết quả, thường là dịch vụ xác thực hoặc backend quản lý phiên. Backend chỉ phát sự kiện đăng nhập thành công sau khi đã kiểm tra thông tin xác thực, áp dụng chính sách, tạo hoặc xoay vòng phiên và hoàn tất bước xác thực cần thiết. Nếu chỉ ghi nhận sự kiện từ JavaScript, một người dùng có thể tự gọi hàm ghi log hoặc sửa payload để tạo ra sự kiện thành công giả.

| Nguồn | Ví dụ | Giá trị tin cậy |
|---|---|---|
| Giao diện trình duyệt | `login_form_submitted`, `mfa_screen_opened`, `popup_closed` | Tín hiệu UX; có thể bị sửa, giả mạo hoặc mất khi tab đóng |
| API gateway hoặc reverse proxy | Request tới endpoint đăng nhập, status code, request ID | Cho biết yêu cầu đã đi qua lớp mạng; không tự chứng minh xác thực thành công |
| Authentication service | Credential accepted/rejected, MFA verified, policy denied | Nguồn có thẩm quyền cho kết quả xác thực |
| Session/token service | Session created, rotated, revoked; refresh token reuse detected | Nguồn có thẩm quyền cho vòng đời phiên và token |
| Hệ thống giám sát | Correlation, aggregation, alert, risk score | Kết quả phân tích từ các sự kiện nguồn; không thay thế bản ghi gốc |

Một request trả HTTP 200 chưa chắc là đăng nhập thành công. Endpoint có thể trả trang nhập MFA, thông báo chung cho cả tài khoản tồn tại và không tồn tại, hoặc trang chứa lỗi nghiệp vụ. Ngược lại, một lần đăng nhập thành công có thể kết thúc bằng redirect. Hãy ghi nhận kết quả từ trạng thái xác thực thực tế thay vì suy ra từ status code hoặc URL chuyển hướng.

Sự kiện giao diện và sự kiện backend có thể liên kết bằng request ID hoặc correlation ID do server cấp. Khi ghép dữ liệu, luôn giữ nguồn phát và mức tin cậy của từng sự kiện. Không nâng một sự kiện trình duyệt thành bằng chứng xác thực chỉ vì timestamp hoặc tên sự kiện giống với bản ghi backend.

## 2. Xây dựng taxonomy sự kiện

Một taxonomy thống nhất giúp dashboard, cảnh báo và điều tra hiểu cùng một ý nghĩa. Tên sự kiện nên ổn định, mô tả một hành động hoặc chuyển trạng thái, tránh gom nhiều kết quả khác nhau vào một tên chung như `login_event`.

| Nhóm | Tên sự kiện gợi ý | Thời điểm ghi nhận |
|---|---|---|
| Đăng nhập | `auth.login.attempted` | Backend nhận yêu cầu đăng nhập và bắt đầu xử lý |
| Đăng nhập | `auth.login.succeeded` | Backend đã xác thực thành công và hoàn tất việc tạo phiên hoặc cấp quyền tương ứng |
| Đăng nhập | `auth.login.failed` | Backend từ chối thông tin xác thực hoặc không hoàn tất được bước xác thực |
| Chính sách | `auth.login.denied` | Chính sách truy cập từ chối yêu cầu, ví dụ tài khoản bị khóa hoặc điều kiện thiết bị không đạt |
| MFA | `auth.mfa.challenge_issued` | Hệ thống yêu cầu thêm một yếu tố |
| MFA | `auth.mfa.succeeded` / `auth.mfa.failed` | Backend xác minh kết quả MFA |
| MFA | `auth.mfa.factor_enrolled` / `auth.mfa.factor_removed` | Yếu tố xác thực được thêm hoặc gỡ |
| Khôi phục | `auth.recovery.requested` / `auth.recovery.completed` | Quy trình khôi phục tài khoản bắt đầu hoặc hoàn tất |
| Phiên | `auth.session.created` | Phiên mới được tạo |
| Phiên | `auth.session.rotated` | Session identifier được thay mới, ví dụ sau đăng nhập hoặc nâng quyền |
| Phiên | `auth.session.refreshed` | Phiên hoặc credential được gia hạn thành công |
| Phiên | `auth.session.revoked` / `auth.session.expired` | Phiên bị thu hồi hoặc hết hạn |
| Token | `auth.token.issued` / `auth.token.rejected` | Token được cấp hoặc bị từ chối khi xác minh |
| Token | `auth.refresh.reuse_detected` | Refresh token đã bị dùng lại theo cách vi phạm chính sách rotation |
| Đăng xuất | `auth.logout.completed` | Backend đã thu hồi hoặc kết thúc phiên |
| Tài khoản | `auth.account.locked` / `auth.account.unlocked` | Trạng thái khóa được thay đổi |
| Quyền | `auth.privilege.elevated` / `auth.privilege.changed` | Quyền hoặc mức assurance của phiên thay đổi |

Taxonomy có thể điều chỉnh theo kiến trúc, nhưng cần phân biệt các trạng thái sau:

- `attempted`: yêu cầu đã được tiếp nhận, chưa có kết luận.
- `challenged`: hệ thống yêu cầu thêm bằng chứng, chẳng hạn MFA.
- `succeeded`: bước được mô tả đã hoàn tất thành công.
- `failed`: kiểm tra thất bại hoặc quá trình không thể hoàn tất.
- `denied`: chính sách chủ động từ chối.
- `abandoned`: có bằng chứng đáng tin cậy rằng luồng đã bị bỏ dở; không suy ra chỉ vì thiếu sự kiện kết thúc.
- `unknown`: không đủ dữ liệu để kết luận, ví dụ timeout trước khi backend xác định trạng thái.

Không ghi `auth.login.succeeded` khi mới phát challenge MFA. Nếu xác thực nhiều bước, hãy ghi nhận riêng từng bước và chỉ phát sự kiện đăng nhập hoàn tất khi toàn bộ yêu cầu đã đạt. Tương tự, `auth.logout.completed` phải phản ánh việc backend đã thu hồi hoặc kết thúc phiên; thao tác xóa giao diện hoặc đóng tab chưa đủ.

Một sự kiện có thể là kết quả của nhiều lần thử. Hãy giữ `attempt_id` hoặc correlation ID để liên kết các bước của cùng một luồng mà không gộp mất lịch sử. Khi một yêu cầu được retry, dùng event ID riêng cho từng bản ghi và idempotency key phù hợp cho thao tác nghiệp vụ.

## 3. Thiết kế event contract

Event contract là cấu trúc dữ liệu chung mà các dịch vụ dùng để phát và nhận sự kiện. Một schema ổn định giúp hệ thống tìm kiếm và phân tích mà không phải đoán ý nghĩa của từng trường.

Một bản ghi có thể gồm các trường sau:

| Trường | Ý nghĩa | Quy tắc |
|---|---|---|
| `event_id` | ID duy nhất của bản ghi | Sinh ở nguồn phát; không dùng lại khi tạo một sự kiện mới |
| `event_name` | Tên theo taxonomy | Dùng danh mục có version và kiểm tra hợp lệ |
| `schema_version` | Phiên bản cấu trúc | Tăng khi thay đổi không tương thích |
| `occurred_at` | Thời điểm sự kiện thực sự xảy ra | UTC, đồng hồ máy chủ được đồng bộ |
| `recorded_at` | Thời điểm hệ thống ghi bền vững | Giúp phát hiện độ trễ pipeline |
| `outcome` | Kết quả của bước được mô tả | Giá trị có danh mục, không dùng câu tự do |
| `reason_code` | Mã nguyên nhân đã chuẩn hóa | Không đưa thông báo lỗi chứa dữ liệu người dùng vào đây |
| `actor_ref` | Tham chiếu người hoặc principal thực hiện | Dùng định danh nội bộ hoặc giá trị giả danh có kiểm soát |
| `session_ref` | Tham chiếu phiên | Không phải session ID hoặc cookie thực |
| `attempt_id` | Liên kết các bước của một lần xác thực | Không chứa username hay token |
| `request_id` / `trace_id` | Liên kết log qua các dịch vụ | Được tạo hoặc xác thực tại biên tin cậy |
| `auth_method` | Phương thức xác thực | Ví dụ password, passkey, SSO |
| `factor` | Yếu tố đã được kiểm tra | Ví dụ password, TOTP, WebAuthn |
| `assurance_level` | Mức bảo đảm mà hệ thống kết luận | Theo mô hình chính sách của ứng dụng |
| `source` | Dịch vụ phát sự kiện | Tên service và môi trường |
| `client_context` | Ngữ cảnh thiết bị/trình duyệt đã rút gọn | Chỉ giữ trường cần thiết và có mục đích rõ ràng |
| `policy_version` | Phiên bản chính sách áp dụng | Hỗ trợ giải thích quyết định cũ |

Ví dụ JSON đã loại bỏ dữ liệu nhạy cảm:

```json
{
  "event_id": "evt_01J9Z6M7R2",
  "event_name": "auth.login.failed",
  "schema_version": 1,
  "occurred_at": "2026-11-22T08:15:30.412Z",
  "recorded_at": "2026-11-22T08:15:30.419Z",
  "outcome": "failed",
  "reason_code": "INVALID_CREDENTIAL",
  "actor_ref": "usr_ref_7f2c",
  "session_ref": null,
  "attempt_id": "att_01J9Z6KQ",
  "request_id": "req_01J9Z6JX",
  "auth_method": "password",
  "factor": "password",
  "assurance_level": "none",
  "source": {
    "service": "identity-api",
    "environment": "production"
  },
  "client_context": {
    "browser_family": "Chromium",
    "platform_family": "Windows",
    "device_class": "desktop"
  },
  "policy_version": "login-policy-12"
}
```

Ví dụ này dùng thời điểm UTC và mã nguyên nhân tổng quát. Không đưa email, mật khẩu, OTP, token hoặc cookie vào event. Nếu cần phân tích số lần thử trên cùng một tài khoản, dùng tham chiếu giả danh được tạo ở backend và giới hạn quyền truy cập dữ liệu có khả năng ánh xạ ngược.

Không bắt buộc mọi sự kiện phải có đủ mọi trường. Với sự kiện trước khi biết principal, `actor_ref` có thể vắng mặt; với sự kiện tạo phiên, `session_ref` có thể được gắn sau khi phiên đã tồn tại. Hãy định nghĩa trường bắt buộc theo từng loại event, kiểm tra kiểu dữ liệu và từ chối hoặc đưa vào dead-letter queue những bản ghi sai schema. Tránh điền giá trị giả như chuỗi rỗng vào trường không áp dụng vì nó làm sai kết quả thống kê.

## 4. Bảo vệ bí mật và dữ liệu cá nhân

Log xác thực là mục tiêu hấp dẫn vì chúng thường được tập trung và lưu lâu. Quy tắc quan trọng nhất là chỉ ghi dữ liệu cần để hiểu sự kiện và điều tra, không ghi credential hoặc bí mật có thể dùng lại.

Không ghi các giá trị sau vào log, trace, metric label hoặc event payload:

- Mật khẩu, mật khẩu tạm thời, mã OTP, mã recovery và câu trả lời bảo mật.
- Access token, refresh token, authorization code, API key, private key hoặc nội dung header `Authorization`.
- Cookie phiên, session ID thực, giá trị CSRF token và URL chứa các credential đó.
- Nội dung request/response thô của endpoint đăng nhập, MFA, đổi mật khẩu hoặc khôi phục tài khoản.
- WebAuthn assertion/attestation payload, private credential material hoặc dữ liệu challenge thô nếu không có nhu cầu đã được đánh giá.
- Query string hoặc fragment có thể chứa mã reset, mã OAuth, token hoặc dữ liệu cá nhân.

Không ghi toàn bộ object request, object principal hoặc exception vào log một cách tự động. Những object này có thể chứa password, token, email, phone number, cookie hoặc dữ liệu từ nhà cung cấp SSO. Hãy tạo một DTO sự kiện chỉ có trường được cho phép và dùng allowlist để serialize.

Đối với định danh tài khoản trong sự kiện thất bại, tránh lưu email hoặc username rõ nếu mục tiêu chỉ là đếm và liên kết các lần thử. Có thể dùng HMAC với khóa riêng của hệ thống trên định danh đã chuẩn hóa để tạo `actor_ref` giả danh. HMAC giúp liên kết các sự kiện mà không phát lộ trực tiếp giá trị đầu vào, nhưng vẫn là dữ liệu có khả năng liên kết cùng một người. Cần giới hạn quyền truy cập, vòng đời khóa, phạm vi dùng và thời hạn lưu; không gọi dữ liệu giả danh là dữ liệu vô danh.

IP address và user-agent cũng có thể là dữ liệu cá nhân hoặc dữ liệu có khả năng nhận diện. Chỉ thu thập khi có mục đích bảo mật cụ thể, xác định chính sách lưu trữ và quyền truy cập. Nếu cần phân nhóm nguồn tấn công, có thể chuẩn hóa thành dải mạng hoặc dùng một phép biến đổi có khóa và thời hạn phù hợp. Không tin header `X-Forwarded-For` từ mọi client; chỉ lấy địa chỉ nguồn đã được proxy tin cậy xác nhận theo cấu hình triển khai.

Giới hạn quyền đọc log theo vai trò. Nhân viên hỗ trợ không nhất thiết cần xem dữ liệu nguồn mạng hoặc tham chiếu tài khoản có thể ánh xạ; nhóm ứng phó sự cố có thể cần quyền cao hơn trong thời gian điều tra. Ghi audit cho hành động tìm kiếm, xuất và thay đổi quyền truy cập log. Đặt retention theo mục đích, quy định và rủi ro; hết thời hạn thì xóa hoặc tổng hợp theo quy trình đã định.

## 5. Ghi nhận sự kiện tại backend

Sự kiện nên được phát từ nơi biết chính xác trạng thái nghiệp vụ. Với đăng nhập, có thể ghi `attempted` khi backend bắt đầu xử lý và `succeeded` hoặc `failed` khi đã có kết quả. Khi phát sinh MFA, ghi challenge và kết quả MFA riêng. Khi tạo phiên, ghi event phiên sau khi session store xác nhận thao tác thành công.

Ví dụ Java rút gọn dưới đây minh họa cách tạo một bản ghi thất bại với trường đã chọn. Đây là mã phác thảo; các kiểu `AuthEvent`, `EventPublisher` và `RequestContext` là thành phần của ứng dụng, không phải API chuẩn của Java.

```java
public void recordLoginFailure(
        String pseudonymousActorRef,
        String attemptId,
        String requestId,
        String reasonCode,
        RequestContext context) {

    AuthEvent event = new AuthEvent(
        UUID.randomUUID().toString(),
        "auth.login.failed",
        1,
        Instant.now(),
        "failed",
        reasonCode,
        pseudonymousActorRef,
        null,
        attemptId,
        requestId,
        context.authMethod(),
        context.clientContext(),
        "login-policy-12"
    );

    eventPublisher.publish(event);
}
```

Đoạn mã chỉ nhận `pseudonymousActorRef` và context đã được lọc. Không truyền password, raw username, cookie hoặc toàn bộ HTTP request vào hàm ghi sự kiện. `reasonCode` phải đến từ danh mục cố định như `INVALID_CREDENTIAL`, `ACCOUNT_LOCKED`, `MFA_REQUIRED` hoặc `RATE_LIMITED`, không phải message tùy ý từ exception.

Thời điểm phát sự kiện phụ thuộc trạng thái cần mô tả. Nếu ghi `auth.session.created` trước khi session store tạo phiên, log có thể nói phiên tồn tại trong khi thao tác thực tế thất bại. Nếu sự kiện phải phản ánh thay đổi dữ liệu cùng transaction, cân nhắc transactional outbox: ghi bản ghi outbox trong cùng transaction với thay đổi nghiệp vụ, sau đó worker chuyển tiếp sang message broker. Cách này giảm nguy cơ trạng thái đã commit nhưng sự kiện bị mất giữa chừng.

Không phải mọi event đều cần cùng mức bảo đảm. Event phân tích giao diện có thể chấp nhận mất một tỷ lệ nhỏ; event audit cho đăng nhập, thu hồi phiên hoặc thay đổi yếu tố MFA cần độ bền và khả năng truy vết cao hơn. Phân loại yêu cầu trước khi chọn queue, retry và retention.

## 6. Thu thập tín hiệu từ trình duyệt

Trình duyệt vẫn hữu ích để hiểu trải nghiệm xác thực. Các tín hiệu có thể gồm biểu mẫu được gửi, người dùng bắt đầu hoặc hủy MFA, popup SSO bị đóng, WebAuthn API trả về lỗi phía client hoặc giao diện gặp lỗi mạng. Chúng giúp phân biệt người dùng bỏ dở với lỗi backend và xác định khu vực giao diện có tỷ lệ thất bại cao.

Tuy nhiên, payload trình duyệt phải được xem là dữ liệu không đáng tin cậy. Người dùng có thể sửa JavaScript, phát lại request, tự tạo event hoặc thay đổi timestamp. Không dùng sự kiện client để mở khóa tài khoản, đánh dấu login thành công, thu hồi phiên hoặc đưa ra quyết định phân quyền.

Một event UI tối giản có thể như sau:

```javascript
const uiEvent = {
  event_name: "auth.ui.mfa_cancelled",
  schema_version: 1,
  occurred_at: new Date().toISOString(),
  attempt_id: serverIssuedAttemptId,
  page_id: pageTelemetryId
};

telemetry.track(uiEvent);
```

Ví dụ chỉ minh họa việc gửi tín hiệu vào SDK telemetry. `serverIssuedAttemptId` cần được cấp từ backend, có thời hạn ngắn và không chứa định danh tài khoản hoặc credential. `pageTelemetryId` chỉ liên kết hoạt động trong phạm vi cần thiết. Không tự thêm email, số điện thoại, nội dung ô nhập, token hoặc URL đầy đủ vào payload.

Nếu gửi event trực tiếp tới endpoint thu thập, endpoint phải có giới hạn kích thước, schema allowlist, rate limit và kiểm soát nguồn gửi. Dùng HTTPS, giới hạn CORS theo origin thực sự cần và cấu hình CSP `connect-src` cho endpoint telemetry. Không bật CORS wildcard kèm credentials. Endpoint telemetry không được có quyền thay đổi trạng thái xác thực. Nếu endpoint dùng cookie phiên, đánh giá CSRF và chính sách same-site phù hợp; nếu không cần cookie, thiết kế để không phụ thuộc phiên đăng nhập.

Dữ liệu trình duyệt có thể bị mất khi tab đóng, mạng ngắt hoặc trình duyệt chặn request nền. Vì vậy, backend phải tự ghi các kết quả bảo mật trọng yếu. Khi ghép event UI và backend, hiển thị nguồn phát, độ tin cậy và trạng thái ghép nối để người điều tra không nhầm lẫn.

## 7. Xử lý thứ tự, trùng lặp và thời gian

Sự kiện có thể đến hệ thống giám sát không đúng thứ tự. Một message queue có thể retry, consumer có thể xử lý lại, và một dịch vụ có thể gửi event muộn sau khi kết nối được khôi phục. Pipeline phải phân biệt thời điểm xảy ra với thời điểm nhận.

- `occurred_at` biểu diễn lúc nguồn phát ghi nhận sự kiện.
- `recorded_at` biểu diễn lúc bản ghi được lưu bền vững ở nguồn.
- `received_at` biểu diễn lúc hệ thống thu thập tiếp nhận sự kiện.

Dùng đồng hồ UTC và đồng bộ thời gian cho máy chủ. Theo dõi clock skew; không dùng timestamp từ trình duyệt làm căn cứ duy nhất để xếp thứ tự sự kiện bảo mật. Với các bước trong cùng một lần xác thực, `attempt_id`, `request_id` và sequence number do server cấp hữu ích hơn việc chỉ so sánh timestamp.

Consumer nên idempotent. Có thể dùng `event_id` làm khóa chống xử lý trùng và lưu trạng thái đã xử lý trong khoảng thời gian phù hợp. Không xóa bản ghi trùng khỏi audit trail nếu chính sách yêu cầu giữ dấu vết; có thể đánh dấu duplicate hoặc deduplicate ở lớp phân tích. Khi event bị sai schema hoặc không thể xử lý sau số lần retry, chuyển sang dead-letter queue có kiểm soát và cảnh báo cho owner.

Không gộp sự kiện chỉ vì cùng tên và cùng tài khoản. Một người có thể đăng nhập nhiều thiết bị hoặc nhiều lần trong một khoảng thời gian ngắn. Dùng khóa tương quan có phạm vi rõ ràng như `attempt_id`, `session_ref` hoặc `request_id`; tránh tạo một khóa tổng quát khiến nhiều phiên độc lập bị nhập thành một.

## 8. Phát hiện hành vi bất thường

Một event riêng lẻ thường không đủ để kết luận có tấn công. Giá trị nằm ở việc kết hợp nhiều sự kiện theo thời gian, tài khoản, nguồn mạng, thiết bị, phương thức xác thực và trạng thái phiên. Mỗi quy tắc cần xác định dữ liệu đầu vào, ngưỡng, mức độ nghiêm trọng, cách giảm false positive và hành động phản hồi.

| Tín hiệu | Cách kết hợp event | Cách diễn giải |
|---|---|---|
| Brute force | Nhiều `auth.login.failed` liên tiếp với cùng account ref hoặc nguồn trong cửa sổ thời gian | Có thể là đoán mật khẩu; cũng có thể là người dùng nhập sai nhiều lần |
| Password spraying | Một nguồn thử một mật khẩu hoặc mẫu tương tự trên nhiều account ref | Có thể là tấn công phân tán theo tài khoản; cần tránh khóa hàng loạt do NAT dùng chung |
| Credential stuffing | Nhiều tài khoản có lần thử thất bại và một số lần thành công từ nguồn hoặc thiết bị có dấu hiệu tự động | Kết hợp với tốc độ, ASN, danh tiếng nguồn và lịch sử đăng nhập |
| MFA fatigue | Nhiều `auth.mfa.challenge_issued` hoặc `auth.mfa.failed` mà không có hoàn tất hợp lệ | Có thể là người dùng bị thúc ép chấp thuận; cần thông báo và giới hạn challenge |
| Đăng nhập bất thường | Thành công từ thiết bị mới, vùng mạng mới hoặc sau chuỗi thất bại | Là tín hiệu đánh giá rủi ro, không phải bằng chứng chắc chắn |
| Session/token abuse | `auth.refresh.reuse_detected`, session rotation bất thường hoặc token bị từ chối lặp lại | Có thể là token bị sao chép hoặc client đồng thời dùng refresh token |
| Chiếm quyền tài khoản | Đăng nhập mới rồi đổi yếu tố MFA, email khôi phục hoặc quyền truy cập | Cần liên kết chuỗi sự kiện theo account và session |

Một truy vấn minh họa để tìm nhiều lần thất bại theo tham chiếu tài khoản trong cửa sổ thời gian:

```sql
SELECT
    actor_ref,
    COUNT(*) AS failed_attempts,
    MIN(occurred_at) AS first_seen,
    MAX(occurred_at) AS last_seen
FROM auth_events
WHERE event_name = 'auth.login.failed'
  AND occurred_at >= CURRENT_TIMESTAMP - INTERVAL '10 minutes'
GROUP BY actor_ref
HAVING COUNT(*) >= 8;
```

Cú pháp thời gian và hàm tổng hợp có thể khác giữa các hệ thống SQL/SIEM. Ngưỡng trong ví dụ chỉ để minh họa, không phải ngưỡng áp dụng chung. Một công ty có nhiều người dùng sau cùng NAT, dịch vụ kiểm thử tự động hoặc thiết bị kiosk có thể tạo nhiều lần thất bại hợp lệ. Hãy điều chỉnh theo baseline, phân nhóm ứng dụng và mức độ rủi ro.

Kết hợp tín hiệu ở nhiều chiều để tránh phụ thuộc vào một chỉ số. Ví dụ, nhiều lần thất bại từ cùng IP có thể là một văn phòng dùng NAT; nhiều tài khoản bị thử từ một nguồn, kết hợp user-agent giống nhau và tốc độ cao, đáng điều tra hơn. User-agent có thể bị giả mạo và vị trí IP chỉ là ước lượng; không dùng một mình các giá trị này để kết luận danh tính hoặc khóa tài khoản.

Phát hiện refresh token reuse cần hiểu thiết kế rotation. Nếu nhiều tab hợp lệ cùng refresh gần như đồng thời, hệ thống có thể ghi nhận reuse giả. Cần kiểm soát đồng bộ phía client, grace window nếu kiến trúc cho phép và chính sách thu hồi rõ ràng. Khi có dấu hiệu reuse thực sự, sự kiện cần liên kết token family bằng tham chiếu giả danh, không ghi token gốc.

## 9. Cảnh báo và quy trình ứng phó

Một cảnh báo hữu ích phải cho người trực biết điều gì xảy ra, phạm vi ảnh hưởng, độ tin cậy và bước kiểm tra tiếp theo. Cảnh báo không nên chứa mật khẩu, OTP, token, cookie hoặc toàn bộ URL có query nhạy cảm.

Một quy tắc cảnh báo có thể định nghĩa:

1. **Điều kiện:** số lần thất bại hoặc số tài khoản bị thử vượt baseline trong một cửa sổ thời gian.
2. **Phạm vi:** ứng dụng, môi trường, nguồn phát và nhóm account ref bị ảnh hưởng.
3. **Mức độ:** dựa trên số lượng tài khoản, có thành công sau thất bại hay không, MFA có bị tác động và mức độ đặc quyền.
4. **Bằng chứng:** event ID, request ID, khoảng thời gian, reason code và số lượng sự kiện liên quan.
5. **Hành động:** xác minh nguồn, xem chuỗi login/MFA/session, áp dụng rate limit hoặc khóa tạm thời theo chính sách đã phê duyệt.
6. **Kết thúc:** ghi kết luận, hành động đã thực hiện và lý do đóng cảnh báo.

Khi điều tra, bắt đầu từ event ID hoặc request ID rồi mở rộng theo `attempt_id`, `actor_ref` và `session_ref`. Dựng timeline từ backend, session service, gateway và tín hiệu trình duyệt. Kiểm tra sự kiện thành công có thực sự xảy ra sau challenge hay không, phiên có được xoay vòng, và yếu tố xác thực có bị thêm hoặc gỡ ngay sau đăng nhập hay không.

Không tự động khóa hàng loạt tài khoản chỉ dựa trên số lần thất bại từ một địa chỉ IP. Cách đó có thể biến log thành công cụ từ chối dịch vụ. Ưu tiên rate limit theo nhiều chiều, tăng yêu cầu xác thực theo rủi ro và quy trình khôi phục có kiểm soát. Với tài khoản đặc quyền hoặc dấu hiệu token bị lộ, có thể cần thu hồi phiên, buộc xác thực lại và chuyển sự cố cho nhóm ứng phó.

## 10. Bảo vệ tính toàn vẹn của audit trail

Nếu người có quyền quản trị ứng dụng có thể sửa hoặc xóa log xác thực mà không để lại dấu vết, dữ liệu sẽ kém giá trị khi điều tra. Hệ thống cần phân tách quyền giữa dịch vụ phát event, pipeline thu thập, người quản trị nền tảng và người đọc log.

Các biện pháp vận hành có thể gồm:

- Chuyển log ra khỏi máy chủ ứng dụng tới kho tập trung với quyền ghi hạn chế.
- Dùng transport có xác thực và mã hóa; xác thực danh tính dịch vụ gửi event.
- Lưu audit trail theo chế độ append-only hoặc storage có khả năng chống sửa đổi theo yêu cầu.
- Ghi nhận thao tác truy cập, xuất, xóa và thay đổi chính sách retention.
- Theo dõi khoảng trống sequence, độ trễ, queue backlog, dead-letter queue và lỗi ghi log.
- Tách log ứng dụng, log bảo mật và metric vận hành theo quyền truy cập và retention phù hợp.

Hash chain hoặc chữ ký số có thể hỗ trợ phát hiện thay đổi trái phép, nhưng chỉ có ích khi khóa ký được bảo vệ độc lập, quy trình kiểm tra được vận hành và quyền sửa dữ liệu được kiểm soát. Không xem việc thêm một trường checksum vào JSON là đủ để bảo đảm tính bất biến.

Khi pipeline ngừng hoạt động, cần có chính sách rõ ràng: event bảo mật trọng yếu có được buffer tại nguồn, ghi vào outbox hoặc lưu cục bộ có giới hạn hay không; hệ thống có được tiếp tục cho đăng nhập nếu audit sink tạm thời lỗi hay không. Quyết định fail-open hay fail-closed phải dựa trên rủi ro và yêu cầu sẵn sàng. Không âm thầm bỏ event. Theo dõi số event phát ra so với số event được nhận để phát hiện thất thoát.

## 11. Kiểm thử event trong vòng đời xác thực

Kiểm thử cần xác nhận cả ý nghĩa nghiệp vụ lẫn cách dữ liệu đi qua pipeline. Không chỉ kiểm tra rằng một log có xuất hiện; cần xác minh nó được phát đúng thời điểm, đúng outcome, không chứa bí mật và có thể liên kết với các bước liên quan.

| Kịch bản | Sự kiện mong đợi | Điều cần xác minh |
|---|---|---|
| Đăng nhập thành công bằng mật khẩu | `auth.login.attempted`, `auth.login.succeeded`, event tạo phiên | Success chỉ xuất hiện sau khi phiên được tạo |
| Mật khẩu sai | `auth.login.failed` | Reason code tổng quát; không lộ tài khoản có tồn tại hay không |
| Tài khoản bị khóa | `auth.login.denied` | Quyết định chính sách được ghi rõ; không ghi dữ liệu bí mật |
| MFA bắt buộc | `auth.mfa.challenge_issued` rồi event kết quả | Challenge không bị nhầm thành login success |
| MFA sai hoặc hết hạn | `auth.mfa.failed` | Phân biệt sai mã, hết hạn và giới hạn thử theo reason code |
| Đăng xuất | `auth.logout.completed`, `auth.session.revoked` nếu áp dụng | Phiên thực sự bị thu hồi ở backend |
| Session rotation | `auth.session.rotated` | Tham chiếu cũ/mới không chứa session ID thực |
| Refresh token reuse | `auth.refresh.reuse_detected` | Không log token; phân biệt retry hợp lệ với reuse đáng ngờ |
| Thêm hoặc gỡ MFA | Event factor enrolled/removed | Actor, thời điểm, session và yêu cầu xác thực lại được liên kết |
| Browser gửi event giả | Event UI có thể xuất hiện; không có backend success giả | Không có thay đổi trạng thái xác thực do telemetry client |
| Queue xử lý lại | Consumer có thể nhận event trùng | Idempotency ngăn tạo cảnh báo hoặc số liệu đếm trùng |
| Log sink ngừng hoạt động | Buffer/outbox và cảnh báo pipeline | Không mất dấu vết âm thầm; hành vi fail-open/closed đúng chính sách |

Có thể bổ sung kiểm thử bảo mật dữ liệu bằng cách quét log mẫu để tìm các mẫu nhạy cảm như `Bearer`, `Set-Cookie`, `password`, `otp`, `access_token`, `refresh_token` và query parameter chứa mã. Các chuỗi kiểm tra cần được thiết kế để không vô tình in giá trị bí mật ra báo cáo kiểm thử. Kiểm thử cả exception path, debug mode, trace và dead-letter queue vì dữ liệu nhạy cảm thường bị lộ ở những đường phụ này.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Frontend tự phát `login.succeeded` | Người dùng có thể giả mạo trạng thái xác thực | Backend phát kết quả từ trạng thái thực tế |
| Dùng HTTP 200 làm bằng chứng đăng nhập | Nhầm challenge hoặc lỗi nghiệp vụ thành thành công | Ghi event tại điểm quyết định xác thực |
| Ghi request hoặc principal object nguyên vẹn | Lộ password, token, cookie hoặc PII | Dùng event DTO allowlist |
| Gộp login attempt, MFA và session vào một event | Không dựng được timeline hoặc phân biệt bước hoàn tất | Dùng event riêng và ID tương quan |
| Dùng timestamp client làm chuẩn | Dễ sai lệch hoặc bị sửa | Dùng thời gian backend UTC và ghi nhận độ trễ |
| Consumer không idempotent | Retry tạo số đếm và cảnh báo trùng | Dùng event ID và cơ chế deduplication |
| Tin `X-Forwarded-For` từ client | Kẻ tấn công giả mạo nguồn | Chỉ tin proxy đã cấu hình |
| Dùng IP hoặc user-agent làm định danh | False positive và đánh giá sai người dùng | Kết hợp nhiều tín hiệu và tham chiếu principal |
| Không giám sát chính pipeline log | Mất event mà không biết | Theo dõi backlog, drop, delay và dead-letter |
| Lưu log vô thời hạn | Tăng rủi ro rò rỉ và vi phạm mục đích thu thập | Thiết lập retention và quyền truy cập |

## 13. Checklist triển khai

- [ ] Đã định nghĩa taxonomy và outcome cho login, MFA, recovery, session, token và logout.
- [ ] Đã xác định nguồn phát có thẩm quyền cho từng sự kiện.
- [ ] Backend ghi sự kiện sau khi trạng thái tương ứng thực sự hoàn tất.
- [ ] Event schema có version, event ID, thời gian UTC và correlation ID.
- [ ] Event payload chỉ chứa trường allowlist; không có password, OTP, token, cookie hoặc request body thô.
- [ ] Định danh và ngữ cảnh client được tối thiểu hóa, giả danh và giới hạn truy cập.
- [ ] Event UI được đánh dấu là tín hiệu không tin cậy và không điều khiển trạng thái xác thực.
- [ ] Pipeline có xác thực nguồn gửi, mã hóa, retry, idempotency và dead-letter handling.
- [ ] Có giám sát độ trễ, queue backlog, event drop và khả năng truy vấn audit trail.
- [ ] Quy tắc phát hiện có baseline, xử lý false positive và quy trình phản hồi.
- [ ] Retention, phân quyền, audit truy cập và xóa dữ liệu đã được xác định.
- [ ] Đã kiểm thử login thành công/thất bại, MFA, session rotation, logout, token reuse và sự cố pipeline.

Authentication event có giá trị khi mỗi bản ghi phản ánh đúng một bước trong vòng đời xác thực, có nguồn phát đáng tin cậy, không làm lộ bí mật và có thể liên kết với các sự kiện liên quan. Khi taxonomy, schema, pipeline và quy trình ứng phó được thiết kế đồng bộ, đội vận hành có thể phát hiện hành vi bất thường và dựng lại diễn biến xác thực mà vẫn giữ được ranh giới tin cậy giữa trình duyệt và backend.
