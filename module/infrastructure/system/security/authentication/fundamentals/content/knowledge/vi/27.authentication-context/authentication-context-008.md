# Context thay đổi

**Context thay đổi** là việc ngữ cảnh xung quanh một lần xác thực hoặc một phiên đăng nhập thay đổi theo thời gian: thiết bị chuyển mạng, vị trí ước lượng khác đi, trạng thái bảo mật thiết bị thay đổi, phiên tồn tại lâu hơn, hành vi truy cập khác thường hoặc người dùng bắt đầu một thao tác có mức độ nhạy cảm cao hơn. Hệ thống xác thực cần nhận biết những thay đổi này và đánh giá xem mức bảo đảm hiện tại còn đủ cho request tiếp theo hay cần xác thực tăng cường, giới hạn, từ chối hoặc thu hồi phiên.

Bài học thuộc chương **Authentication context** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Module giúp người học hiểu credential, MFA, passkey, token, session, liên kết danh tính và ranh giới tin cậy. Trong phạm vi này, cần biết phân biệt yếu tố xác thực với tín hiệu ngữ cảnh; đánh giá rủi ro khi context thay đổi; áp dụng step-up authentication đúng lúc; quản lý freshness của thông tin xác thực; và tránh để một phiên đã đăng nhập tiếp tục được tin cậy vô hạn dù điều kiện ban đầu đã thay đổi.

Điểm cốt lõi: **context là thông tin hỗ trợ quyết định bảo mật, không tự động là bằng chứng xác thực danh tính**. Một địa chỉ IP quen thuộc, thiết bị đã thấy trước đây hoặc vị trí có vẻ hợp lý không chứng minh người đang dùng phiên là đúng chủ thể. Hệ thống phải kết hợp context với bằng chứng xác thực, trạng thái account, quyền trên tài nguyên và mức rủi ro của hành động.

## 1. Authentication context là gì?

Authentication context mô tả điều kiện và bằng chứng liên quan tới cách một chủ thể được xác thực. Nó có thể bao gồm phương thức đã sử dụng, thời điểm xác thực gần nhất, mức xác minh của authenticator, độ tin cậy của thiết bị, trạng thái phiên, nguồn request và các tín hiệu rủi ro.

Ví dụ, hai request cùng đến từ account của nhân viên Mai nhưng có context khác nhau:

- Request thứ nhất được gửi từ thiết bị công ty đã quản lý, qua mạng nội bộ, ngay sau khi Mai đăng nhập bằng passkey có user verification.
- Request thứ hai xuất hiện nhiều giờ sau, từ một thiết bị mới, qua mạng ẩn danh, để thay đổi email khôi phục và thêm authenticator mới.

Account và session identifier có thể giống nhau, nhưng rủi ro của hai request không giống nhau. Hệ thống nên đánh giá lại context trước khi cho phép hành động nhạy cảm.

### 1.1. Những thành phần thường gặp

| Thành phần context | Ví dụ | Câu hỏi bảo mật |
| --- | --- | --- |
| **Authentication method** | Password, TOTP, passkey, client certificate. | Bằng chứng nào đã được dùng và có đáp ứng policy không? |
| **Authentication time** | Đăng nhập cách đây 2 phút hay 12 giờ. | Kết quả xác thực còn đủ mới cho hành động hiện tại không? |
| **User verification / assurance** | Passkey có UV, MFA, mức ACR do IdP phát hành. | Hệ thống đã xác minh người dùng ở mức nào? |
| **Device posture** | Thiết bị được quản lý, mã hóa ổ đĩa, OS còn hỗ trợ. | Thiết bị có đáp ứng điều kiện truy cập không? |
| **Network context** | IP, ASN, VPN, proxy, mạng nội bộ. | Request đi qua nguồn mạng nào và tín hiệu này đáng tin đến đâu? |
| **Location estimate** | Quốc gia hoặc vùng ước lượng từ IP. | Có thay đổi bất thường hay dữ liệu không đủ chính xác? |
| **Behavior** | Tần suất request, kiểu thao tác, thời điểm sử dụng. | Hành vi có khác đáng kể so với baseline không? |
| **Session state** | Idle duration, absolute age, token expiry, session revocation. | Phiên còn hiệu lực và còn được phép sử dụng không? |
| **Resource/action sensitivity** | Đọc hồ sơ hay đổi recovery method, cấp role admin. | Mức bảo đảm hiện tại có đủ cho hành động này không? |
| **Threat intelligence** | IP độc hại đã biết, credential compromise signal. | Có tín hiệu bên ngoài làm tăng rủi ro không? |

Không phải ứng dụng nào cũng cần thu thập mọi tín hiệu. Chỉ nên dùng dữ liệu cần thiết để quyết định truy cập, có nguồn và độ tin cậy rõ ràng.

### 1.2. Context khác với authentication factor

Yếu tố xác thực là bằng chứng thuộc loại knowledge, possession hoặc inherence. Context là thuộc tính hoặc tín hiệu bổ sung xung quanh request.

Ví dụ:

- Mật khẩu là yếu tố knowledge.
- Passkey sử dụng khóa riêng là bằng chứng possession; user verification có thể bổ sung điều kiện xác minh tại authenticator.
- IP văn phòng là tín hiệu network context, không phải yếu tố possession.
- Device fingerprint là tín hiệu nhận diện/rủi ro, không chứng minh người dùng đang giữ thiết bị.
- Giờ làm việc là tín hiệu hành vi, không phải bằng chứng xác thực.

Không nâng IP, cookie tracking hoặc fingerprint thành “yếu tố thứ hai”. Context có thể giúp phát hiện bất thường nhưng thường có thể thay đổi, giả mạo hoặc bị chia sẻ.

## 2. Vì sao phải đánh giá lại context?

Xác thực thường xảy ra tại một thời điểm, trong khi quyền truy cập kéo dài qua nhiều request. Context lúc đăng nhập có thể không còn đúng sau đó.

Một phiên có thể được tạo sau khi người dùng dùng passkey trên thiết bị đáng tin. Sau vài giờ:

- Thiết bị bị mất hoặc trạng thái quản lý bị thu hồi.
- Người dùng chuyển từ mạng công ty sang Wi-Fi công cộng.
- Session cookie bị sao chép sang browser khác.
- Account bị báo compromise hoặc bị đình chỉ.
- Người dùng yêu cầu tải dữ liệu lớn hoặc thay đổi credential.
- Một refresh token bị reuse hoặc phát hiện hành vi bất thường.

Nếu hệ thống chỉ xác thực một lần rồi tin mọi request cho đến khi cookie/token hết hạn, quyền truy cập có thể tiếp tục trong một context không còn phù hợp.

### 2.1. Context có thể thay đổi mà không có tấn công

Không phải mọi thay đổi đều đáng ngờ. Người dùng hợp lệ có thể:

- Di chuyển giữa mạng di động, Wi-Fi và VPN.
- Dùng laptop ở văn phòng rồi tiếp tục trên điện thoại.
- Cập nhật hệ điều hành hoặc thay đổi trình duyệt.
- Làm việc ngoài giờ do múi giờ hoặc lịch công việc khác nhau.
- Đi công tác khiến IP và vị trí ước lượng thay đổi.

Chính sách không nên khóa account chỉ vì một tín hiệu đơn lẻ. Cần đánh giá mức độ tin cậy, độ mới, mức độ liên quan và nhiều tín hiệu kết hợp; khi không chắc chắn, có thể yêu cầu step-up thay vì kết luận account đã bị chiếm.

### 2.2. Context thay đổi có thể làm giảm assurance

Mức bảo đảm của lần đăng nhập trước không tự tăng chỉ vì người dùng tiếp tục gửi request. Nếu một thao tác yêu cầu xác thực gần đây hoặc authenticator chống phishing, một session cũ chỉ có password có thể không đáp ứng.

Ngược lại, một thiết bị có posture tốt không nâng một lần đăng nhập password yếu thành MFA. Hệ thống phải giữ riêng các thuộc tính:
- Bằng chứng xác thực đã dùng.
- Mức assurance do issuer hoặc policy đáng tin xác định.
- Context của request hiện tại.
- Quyền được cấp cho action/resource.

## 3. Các nhóm context và độ tin cậy của tín hiệu

### 3.1. Device context

Device context có thể gồm thiết bị đã đăng ký, trạng thái quản lý, phiên bản OS, mã hóa ổ đĩa, screen lock, endpoint protection và tín hiệu integrity/attestation nếu nền tảng hỗ trợ.

Cần phân biệt:

- **Known device:** thiết bị từng được thấy hoặc gắn với account.
- **Managed device:** thiết bị được tổ chức quản lý qua MDM/endpoint management.
- **Compliant device:** thiết bị đáp ứng một bộ policy tại thời điểm đánh giá.
- **Attested device state:** có bằng chứng kỹ thuật từ một nguồn/thiết bị được tin cậy về một số thuộc tính.

Một cookie “remember this device” chỉ cho biết browser giữ một dấu hiệu đã cấp trước đó; nó có thể bị sao chép và không chứng minh posture hiện tại. Tín hiệu compliance cũng có thể cũ, nên cần thời điểm đánh giá, nguồn, chữ ký hoặc kênh truyền đáng tin và TTL phù hợp.

### 3.2. Network context

IP, ASN, VPN, proxy, Tor exit node hoặc mạng nội bộ có thể giúp phát hiện rủi ro. Nhưng:

- Nhiều người dùng có thể chung một IP NAT.
- VPN doanh nghiệp có thể làm vị trí IP khác vị trí thật.
- IP di động thay đổi thường xuyên.
- Proxy header có thể bị client giả mạo nếu reverse proxy không loại bỏ và ghi lại header tin cậy.
- IP quen thuộc không chứng minh thiết bị hoặc người dùng hợp lệ.

Nếu sử dụng `X-Forwarded-For` hoặc `Forwarded`, chỉ tin giá trị được proxy đáng tin thiết lập sau khi loại bỏ header client tự gửi. Không lấy IP đầu tiên trong chuỗi một cách mù quáng.

### 3.3. Location context

Vị trí từ IP thường chỉ là ước lượng theo vùng/quốc gia, không phải tọa độ chính xác. Một kết luận “impossible travel” dựa trên hai IP có thể sai do VPN, NAT, mạng di động, proxy hoặc dữ liệu GeoIP chậm cập nhật.

Dùng location như một tín hiệu rủi ro có độ bất định. Tránh yêu cầu GPS chính xác nếu không thực sự cần; dữ liệu vị trí nhạy cảm và cần mục đích, thời hạn lưu giữ, quyền truy cập rõ ràng.

### 3.4. Behavioral context

Tín hiệu hành vi có thể gồm tốc độ thao tác, loại endpoint thường gọi, khối lượng dữ liệu, giờ hoạt động hoặc chuỗi hành động. Baseline nên được xây dựng theo vai trò, công việc và lịch sử hợp lệ; người dùng mới hoặc vừa đổi công việc có thể không có baseline đáng tin.

Behavior analytics có false positive và false negative. Không tự động từ chối hoặc cáo buộc người dùng chỉ dựa vào một điểm lệch thống kê. Cần kết hợp mức nhạy cảm của hành động, bằng chứng xác thực và khả năng người dùng giải quyết bước xác minh tăng cường.

### 3.5. Session và token context

Session context gồm thời điểm xác thực, idle time, absolute age, authentication method, device binding, token expiry, refresh history và trạng thái revocation.

Một access token có thể còn `exp` trong tương lai nhưng context đã thay đổi. Nếu API chỉ kiểm chữ ký và expiry, nó có thể tiếp tục chấp nhận quyền cũ. Với thao tác quan trọng, resource server cần kiểm tra trạng thái account/session hoặc policy mới nhất theo kiến trúc.

## 4. Đánh giá context theo rủi ro

Risk-based authentication đánh giá nhiều tín hiệu để chọn hành động phù hợp. Hệ thống có thể tạo một risk level hoặc decision thay vì chỉ trả lời đúng/sai.

Các đầu vào có thể gồm:
- Tính hợp lệ của credential và session.
- Assurance và thời điểm xác thực.
- Device posture và độ tin cậy của nguồn posture.
- Network/location anomaly.
- Hành vi request.
- Tình trạng account, credential và threat intelligence.
- Mức độ nhạy cảm của action/resource.

### 4.1. Kết quả quyết định

| Quyết định | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Allow** | Context và assurance hiện tại đáp ứng policy. | Đọc lịch học trên session hợp lệ. |
| **Allow with limits** | Cho phép nhưng giới hạn phạm vi/tốc độ. | Chỉ đọc dữ liệu, giảm quota hoặc chặn export hàng loạt. |
| **Step-up** | Yêu cầu bằng chứng xác thực bổ sung hoặc gần đây hơn. | Xác thực lại bằng passkey có UV trước khi đổi recovery method. |
| **Deny** | Từ chối request vì policy không đáp ứng hoặc có rủi ro không thể chấp nhận. | Token sai audience, account bị đình chỉ hoặc credential revoked. |
| **Revoke / contain** | Vô hiệu hóa session/credential hoặc hạn chế account theo incident policy. | Refresh token reuse đáng tin cậy hoặc xác nhận session bị đánh cắp. |
| **Review** | Chuyển sang kiểm tra thủ công khi tín hiệu mơ hồ và tác động cao. | Thay IdP của tenant hoặc cấp chứng chỉ production. |

Không nên biến mọi bất thường thành revoke. Mỗi quyết định cần tương ứng với mức tin cậy của tín hiệu, tác động và khả năng phục hồi.

### 4.2. Risk score không phải sự thật tuyệt đối

Một mô hình có thể gán điểm cho tín hiệu, nhưng điểm số chỉ là đầu vào chính sách. Cần biết:
- Nguồn dữ liệu và độ tin cậy của từng tín hiệu.
- Trọng số và ngưỡng có thể giải thích.
- False positive/negative và cách người dùng khiếu nại.
- Cách xử lý thiếu dữ liệu hoặc dịch vụ đánh giá không khả dụng.
- Ai được quyền thay đổi policy và cách audit thay đổi đó.

Không nên cho phép một client tự gửi `risk_score=0` hoặc `device_trusted=true` để được bỏ qua step-up. Quyết định phải được tạo ở phía server từ nguồn đã xác minh.

## 5. Step-up authentication khi context thay đổi

**Step-up authentication** yêu cầu người dùng cung cấp bằng chứng mạnh hơn hoặc mới hơn trước khi thực hiện hành động. Nó phù hợp khi context hiện tại không đủ assurance cho action, nhưng chưa có lý do chắc chắn để khóa account.

Ví dụ:
- Người dùng đăng nhập bằng password, sau đó muốn thêm passkey mới.
- Session tồn tại lâu, người dùng muốn đổi email khôi phục.
- Thiết bị mới yêu cầu truy cập dữ liệu nhạy cảm.
- Người dùng muốn cấp quyền quản trị hoặc export dữ liệu lớn.
- Context rủi ro tăng, nhưng account vẫn có thể được xác minh bằng authenticator mạnh.

### 5.1. Step-up phải đáp ứng yêu cầu cụ thể

Không phải bất kỳ bước xác minh bổ sung nào cũng đủ. Policy cần xác định:
- Loại authenticator được chấp nhận.
- Có yêu cầu phishing resistance không.
- Có yêu cầu user verification không.
- Thời điểm xác thực tối đa (freshness).
- Có yêu cầu re-authentication bằng yếu tố đã đăng ký trước đó không.
- Step-up có gắn với transaction/action cụ thể không.

Ví dụ, trước khi thay email recovery, hệ thống có thể yêu cầu passkey/WebAuthn có UV đã đăng ký trước đó, sau đó thông báo tới kênh cũ. Cho phép người dùng vừa đăng nhập bằng password rồi tự thêm passkey mới mà không có kiểm tra bổ sung có thể tạo đường chiếm account.

### 5.2. Step-up không phải thêm một prompt bất kỳ

Một push notification không có ngữ cảnh hoặc OTP gửi tới cùng mailbox đang bị nghi compromise có thể không tăng assurance thực tế. Bước tăng cường phải độc lập phù hợp với threat model và ràng buộc người dùng với đúng giao dịch.

Với giao dịch nhạy cảm, có thể hiển thị rõ action, resource, tenant và nội dung cần xác nhận. Nếu người dùng xác thực thành công nhưng transaction đã thay đổi, hết hạn hoặc bị hủy, không được dùng kết quả đó cho hành động khác.

### 5.3. Re-authentication và authentication freshness

Re-authentication yêu cầu người dùng xác thực lại; freshness là độ mới của lần xác thực gần nhất. Một phiên đang active không có nghĩa lần xác thực đã đủ mới cho mọi action.

OIDC có thể cung cấp claim `auth_time` để biểu thị thời điểm người dùng được xác thực; client có thể yêu cầu xác thực mới qua các tham số như `max_age` hoặc các yêu cầu flow phù hợp. Client cần xác minh ID Token và kiểm tra thời điểm thực tế, không chỉ tin giao diện đã hiển thị login prompt.

## 6. Authentication context trong OIDC và federation

Trong OIDC, một số claim có thể truyền thông tin về phương thức hoặc ngữ cảnh xác thực:

| Claim/parameter | Vai trò | Lưu ý |
| --- | --- | --- |
| `acr` | Authentication Context Class Reference trong ID Token. | Giá trị thường phụ thuộc OP/profile; client phải biết ý nghĩa và mapping theo thỏa thuận. |
| `amr` | Authentication Methods References. | Mô tả phương thức được dùng; không phải mọi OP dùng cùng vocabulary. |
| `auth_time` | Thời điểm authentication của người dùng. | Dùng để đánh giá freshness khi policy yêu cầu. |
| `max_age` | Request yêu cầu thời gian tối đa kể từ lần authentication trước. | OP cần thực hiện xác thực lại nếu phiên cũ không đáp ứng. |
| `acr_values` | Client có thể yêu cầu một hoặc nhiều mức context class theo OP/profile. | Không giả định OP sẽ đáp ứng chỉ vì client gửi tham số. |

Client không nên so sánh `acr` theo một thứ tự số tự suy diễn nếu OP không định nghĩa thứ tự assurance. Một chuỗi có tên “high” không tự chứng minh mức bảo đảm cao. Cần tài liệu trust agreement, issuer allowlist, mapping và policy rõ ràng.

Tương tự, `amr` chỉ là thông tin do issuer cung cấp. Client phải tin issuer, xác minh chữ ký/audience/issuer và hiểu profile. Không nhận claim từ token không xác minh hoặc từ issuer không được cấu hình.

### 6.1. Ví dụ yêu cầu authentication mới

Một OIDC client có thể yêu cầu xác thực gần đây bằng `max_age` hoặc yêu cầu context class qua `acr_values` nếu OP hỗ trợ. Sau callback, client kiểm tra:
- ID Token signature, issuer, audience và expiry.
- `auth_time` đáp ứng freshness policy.
- `acr` khớp class đã thỏa thuận.
- `amr` có các phương thức cần thiết theo profile.
- State, nonce và PKCE được xác minh đúng flow.

Nếu OP không hỗ trợ hoặc trả context thấp hơn, client phải từ chối action hoặc chọn một phương thức thay thế được policy cho phép. Không tự coi yêu cầu đã được đáp ứng chỉ vì authorization response thành công.

## 7. Context thay đổi trong suốt session

Một session có thể được tạo ở mức assurance phù hợp, nhưng các request sau cần đánh giá theo context hiện tại. Không nhất thiết phải chạy mô hình rủi ro phức tạp ở mọi request; có thể chia theo sự kiện hoặc độ nhạy.

### 7.1. Những sự kiện nên kích hoạt đánh giá lại

- Login từ thiết bị hoặc browser mới.
- Thay đổi IP/ASN hoặc phát hiện proxy/VPN bất thường.
- Device compliance hết hạn hoặc bị thu hồi.
- Thời gian từ lần xác thực gần nhất vượt ngưỡng.
- Request truy cập dữ liệu nhạy cảm, export hoặc quản trị.
- Thay đổi password, MFA, passkey, recovery method hoặc federation link.
- Account đổi trạng thái, tenant membership hoặc role.
- Refresh token reuse, session anomaly hoặc cảnh báo compromise.
- Phiên hoạt động đồng thời từ các context khó giải thích.

### 7.2. Re-evaluation theo request và theo sự kiện

Có hai cách tổ chức phổ biến:

- **Request-time evaluation:** kiểm tra context mỗi lần gọi API hoặc trước action nhạy cảm. Cho phép policy mới có hiệu lực nhanh nhưng tăng độ trễ và phụ thuộc dịch vụ đánh giá.
- **Event-driven evaluation:** nhận sự kiện từ IdP, MDM, threat detection hoặc account lifecycle để cập nhật session/risk state. Giảm truy vấn lặp nhưng cần xử lý event delay, duplicate và delivery failure.

Nhiều hệ thống kết hợp cả hai: event cập nhật trạng thái, còn request-time check xác minh lại các điều kiện quan trọng trước khi cấp quyền.

### 7.3. Không ràng buộc session quá cứng vào IP

Ràng buộc session với IP chính xác có thể làm gián đoạn người dùng hợp lệ khi chuyển mạng, dùng mobile network hoặc VPN. Nó cũng không ngăn attacker dùng chung IP hoặc proxy hợp lệ.

Có thể dùng network change làm tín hiệu tăng rủi ro, kết hợp device/session binding và step-up. Với môi trường có yêu cầu cao, cân nhắc token sender-constrained hoặc proof-of-possession phù hợp, thay vì xem IP là định danh thiết bị.

## 8. Context freshness và dữ liệu đã cũ

Mọi tín hiệu context đều có tuổi. Device posture lúc 08:00 không chắc còn đúng lúc 18:00; membership được cache có thể đã bị thu hồi; GeoIP có thể chậm cập nhật.

Một context record nên có:
- Giá trị và nguồn phát hành.
- Thời điểm quan sát/đánh giá.
- Thời điểm hết hạn hoặc TTL.
- Mức độ tin cậy/attestation nếu có.
- Chủ thể, thiết bị, session và tenant liên quan.
- Phiên bản policy đã áp dụng.

Ví dụ:

```json
{
  "context_id": "ctx-72a",
  "subject_id": "usr-57",
  "session_id": "sess-91",
  "device": {
    "managed": true,
    "compliant": true,
    "assessed_at": "2026-11-22T08:00:00Z",
    "expires_at": "2026-11-22T08:15:00Z",
    "source": "enterprise-device-management"
  },
  "network": {
    "risk": "low",
    "observed_at": "2026-11-22T08:10:00Z",
    "source": "trusted-edge"
  },
  "authentication": {
    "method": ["webauthn"],
    "user_verified": true,
    "auth_time": "2026-11-22T08:05:00Z"
  }
}
```

Đây là cấu trúc minh họa, không phải schema chuẩn. Khi TTL hết, hệ thống nên đánh dấu tín hiệu stale và đánh giá lại theo policy. Không tự chuyển stale thành “trusted” hoặc tiếp tục sử dụng vô thời hạn.

### 8.1. Fail open hay fail closed?

Nếu dịch vụ device posture hoặc risk engine không khả dụng, hành vi cần được xác định theo mức rủi ro:

- Với tài nguyên công khai hoặc thao tác ít nhạy cảm, có thể dùng policy dự phòng đã định nghĩa.
- Với thao tác quản trị, thay credential hoặc truy cập dữ liệu nhạy cảm, có thể từ chối tạm thời hoặc yêu cầu xác minh thay thế.
- Không bỏ qua kiểm tra chữ ký, issuer, audience, expiry hoặc trạng thái account chỉ vì risk service lỗi.
- Ghi nhận decision source và fallback đã dùng để điều tra sau này.

Không có quy tắc fail-open/fail-closed áp dụng cho mọi context. Điều kiện bắt buộc và tín hiệu bổ trợ phải được phân biệt rõ.

## 9. Ngăn context downgrade và giả mạo tín hiệu

Attacker có thể tìm cách làm hệ thống đánh giá request ít rủi ro hơn thực tế. Ví dụ:
- Tự gửi header `X-Device-Trusted: true`.
- Giả mạo `X-Forwarded-For` để trông như request từ mạng công ty.
- Dùng cookie “known device” bị đánh cắp.
- Gửi claim `acr` hoặc `amr` tự tạo trong token không được xác minh.
- Lợi dụng fallback khi risk engine lỗi.
- Làm mới session bằng một context yếu rồi dùng session đó cho action nhạy cảm.

Biện pháp:
1. Context có ảnh hưởng quyết định phải đến từ nguồn được xác thực, không phải field client tự khai.
2. Proxy/gateway phải loại bỏ header giả và ghi lại header tin cậy.
3. Device posture cần chữ ký/attestation hoặc kênh quản lý đáng tin, kèm timestamp và TTL.
4. Claims từ IdP chỉ được sử dụng sau khi xác minh token và trust mapping.
5. Policy phải quy định assurance tối thiểu cho từng action, không cho context “low risk” ghi đè điều kiện bắt buộc.
6. Fallback khi thiếu dữ liệu phải rõ ràng, có giới hạn và được audit.
7. Không hạ cấp từ phishing-resistant MFA sang password/OTP yếu chỉ vì người dùng gặp khó khăn, trừ khi recovery policy có proofing tương xứng.

### 9.1. Context không được thay thế authorization

Một thiết bị compliant không có nghĩa principal được phép đọc mọi tenant. Một IP thuộc văn phòng không cấp quyền admin. Một lần step-up thành công không làm thay đổi role hoặc ownership của resource.

Authorization vẫn cần kiểm tra subject, actor, tenant, action, resource và policy. Context chỉ bổ sung điều kiện hoặc điều chỉnh quyết định theo chính sách đã định nghĩa.

## 10. Session assurance và quyền truy cập theo mức

Có thể mô hình hóa session với thuộc tính assurance và thời điểm xác thực. Khi context thay đổi, policy quyết định session còn đáp ứng action nào.

Ví dụ ma trận:

| Action | Assurance/context tối thiểu tham khảo | Hành động khi không đạt |
| --- | --- | --- |
| Đọc nội dung công khai | Session hợp lệ hoặc truy cập ẩn danh theo policy. | Không cần step-up. |
| Xem hồ sơ cá nhân | Session active, account active, scope/resource ownership hợp lệ. | Đăng nhập lại nếu session hết hạn. |
| Đổi email hoặc recovery method | Authentication gần đây, authenticator đã đăng ký trước đó, context đủ tin cậy. | Step-up hoặc recovery proofing. |
| Thêm passkey mới | Re-authentication/step-up, xác minh WebAuthn ceremony, notification. | Từ chối hoặc yêu cầu phương thức hiện có. |
| Cấp role tenant admin | Phishing-resistant MFA, approval độc lập, tenant policy và audit. | Review/deny nếu thiếu điều kiện. |
| Xuất dữ liệu nhạy cảm quy mô lớn | Session assurance phù hợp, context/device đủ tin cậy, scope và quota. | Step-up, giới hạn export hoặc review. |

Các mức này chỉ là ví dụ; tổ chức cần xác định policy theo tài sản và threat model. Không biến bảng thành thứ bậc assurance phổ quát nếu các phương thức không được đánh giá theo cùng một tiêu chuẩn.

## 11. Threat model khi context thay đổi

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Stale context** | Dùng posture, membership hoặc risk result cũ. | Request tiếp tục được cho phép sau khi điều kiện đã thay đổi. | TTL, event update, re-evaluation trước action nhạy cảm. |
| **Context spoofing** | Client tự khai trusted device/IP/assurance. | Policy đánh giá rủi ro thấp giả tạo. | Nguồn server-side, signed attestation, proxy trust boundary. |
| **Session hijacking** | Cookie/token bị sao chép sang context khác. | Attacker sử dụng phiên đã xác thực. | Session protection, rotation, anomaly detection, revocation và step-up. |
| **Context downgrade** | Fallback yếu hoặc policy hạ yêu cầu assurance. | Action nhạy cảm được thực hiện với bằng chứng không đủ. | Minimum assurance per action, deny/review và audit fallback. |
| **False positive lockout** | IP/vị trí/behavior thay đổi hợp lệ bị coi là tấn công. | Người dùng hợp lệ bị khóa hoặc gián đoạn. | Tín hiệu kết hợp, ngưỡng theo rủi ro, step-up và appeal path. |
| **Risk engine outage** | Dịch vụ đánh giá không khả dụng. | Quyết định không nhất quán hoặc fail-open nguy hiểm. | Fallback theo resource sensitivity, monitoring và runbook. |
| **Header trust abuse** | Tin X-Forwarded-For hoặc device header từ client. | Attacker giả mạo nguồn hoặc posture. | Trusted proxy chain, strip/rewrite header, authenticated telemetry. |
| **Concurrent context race** | Context thay đổi giữa lúc đánh giá và thực thi. | Action dùng quyết định cũ hoặc transaction bị thay đổi. | Bind decision to request, short TTL, recheck/atomic authorization. |
| **Privacy over-collection** | Thu thập vị trí, hành vi hoặc fingerprint quá mức. | Rò rỉ dữ liệu cá nhân và giám sát không cần thiết. | Data minimization, retention, access control và transparency. |

## 12. Tình huống thực hành: session hợp lệ nhưng context đã đổi

**Bối cảnh:** Nhân viên Linh đăng nhập vào nền tảng bằng passkey có user verification trên laptop được quản lý. Server tạo session 8 giờ. Sau 3 giờ, thiết bị bị MDM đánh dấu non-compliant do phát hiện phần mềm bảo mật bị tắt. Linh vẫn có cookie session hợp lệ và muốn export danh sách người học của tenant.

**Phân tích:**

1. Passkey đã chứng minh quyền kiểm soát credential tại thời điểm đăng nhập; cookie session chứng minh browser đang trình bày session ID hợp lệ.
2. Trạng thái thiết bị đã thay đổi sau đăng nhập; context ban đầu không còn mới.
3. Export dữ liệu là hành động nhạy cảm, nên policy cần đánh giá device posture hiện tại và assurance.
4. Nếu API chỉ kiểm cookie/session expiry, request có thể được chấp nhận dù device policy không còn đạt.
5. Nếu hệ thống chỉ khóa account ngay khi posture đổi, có thể gây gián đoạn cả thao tác ít rủi ro và làm tăng false positive.

**Thiết kế lại:**

- MDM phát sự kiện posture change gắn với device ID/session liên quan.
- Session/risk service đánh dấu context cũ và cập nhật trạng thái device.
- API export kiểm tra context mới nhất trước khi thực thi.
- Policy có thể chặn export, giới hạn dữ liệu hoặc yêu cầu step-up trên thiết bị compliant khác.
- Các thao tác ít nhạy cảm có thể vẫn được phép theo policy, nhưng không được bỏ qua account/session validity.
- Ghi audit nguồn posture, thời điểm, policy version và quyết định; tránh lưu dữ liệu thiết bị không cần thiết.

**Bài tập:** Nếu Linh chuyển sang mạng di động nhưng laptop vẫn compliant, có nên thu hồi session không? Không nhất thiết. Thay đổi mạng là tín hiệu cần đánh giá; policy có thể tiếp tục cho phép hoặc step-up tùy action, kết hợp các tín hiệu khác thay vì coi IP mới là bằng chứng compromise.

## 13. Checklist thiết kế context-aware authentication

- [ ] Phân biệt authentication factor, authentication assurance, request context và authorization.
- [ ] Liệt kê context cần thiết: method, auth time, device, network, behavior, session, resource/action.
- [ ] Xác định nguồn, độ tin cậy, timestamp và TTL cho từng tín hiệu.
- [ ] Không coi IP, GPS, device fingerprint hoặc known-device cookie là yếu tố xác thực.
- [ ] Chỉ tin proxy header do proxy đáng tin thiết lập; loại bỏ header client tự gửi.
- [ ] Gắn context với đúng subject, device, session, tenant và request.
- [ ] Đánh giá lại khi context đổi hoặc trước hành động nhạy cảm.
- [ ] Định nghĩa allow, limit, step-up, deny, revoke và manual review.
- [ ] Yêu cầu step-up đáp ứng rõ phương thức, phishing resistance, UV và freshness.
- [ ] Với OIDC, xác minh issuer/audience/signature và hiểu đúng acr, amr, auth_time, max_age.
- [ ] Không tự suy thứ bậc assurance từ tên ACR hoặc chuỗi AMR chưa được thỏa thuận.
- [ ] Có TTL/freshness và xử lý context stale hoặc risk service outage theo mức rủi ro.
- [ ] Không ràng buộc session cứng vào IP nếu không có lý do và đánh giá tác động.
- [ ] Ngăn context downgrade và giả mạo header/claim/client field.
- [ ] Kiểm tra lại authorization trên subject, tenant, resource, action và business policy.
- [ ] Bảo vệ quyền riêng tư: thu thập tối thiểu, giới hạn retention và access.
- [ ] Audit quyết định với nguồn tín hiệu và policy version, không log credential/token.
- [ ] Kiểm thử false positive, session hijack, context spoofing, race condition và fallback.

## 14. Câu hỏi tự kiểm tra

**1. Context thay đổi trong authentication là gì?**  
Là thay đổi ở điều kiện xung quanh request/session như thiết bị, mạng, vị trí ước lượng, hành vi, thời điểm xác thực hoặc độ nhạy của action, có thể làm thay đổi quyết định truy cập.

**2. IP văn phòng có phải yếu tố xác thực thứ hai không?**  
Không. IP là tín hiệu network context, có thể dùng chung hoặc bị thay đổi/giả mạo; nó không chứng minh người dùng đang kiểm soát một authenticator.

**3. Mọi context change có phải khóa account không?**  
Không. Thay đổi hợp lệ xảy ra thường xuyên. Cần đánh giá tín hiệu, độ tin cậy và action; có thể allow, limit, step-up, deny hoặc review.

**4. Step-up authentication được dùng khi nào?**  
Khi session hiện tại chưa có assurance đủ mới hoặc đủ mạnh cho action, nhưng vẫn có cách xác minh hợp lệ bằng authenticator phù hợp.

**5. Vì sao cần context freshness?**  
Vì posture, membership và risk signals có thể thay đổi. Dữ liệu cũ không phản ánh trạng thái hiện tại và có thể khiến policy cấp quyền sai.

**6. Các claim acr, amr và auth_time trong OIDC có ý nghĩa gì?**  
Chúng lần lượt mô tả context class, phương thức xác thực và thời điểm xác thực theo issuer/profile. Client phải xác minh token và hiểu mapping đã thỏa thuận.

**7. Có nên khóa session vào một IP duy nhất không?**  
Không nên mặc định. IP có thể đổi hợp lệ và không phải định danh thiết bị. Dùng nó như tín hiệu kết hợp, trừ khi threat model yêu cầu một ràng buộc mạng cụ thể.

**8. Nếu risk engine không khả dụng thì sao?**  
Áp dụng fallback đã định nghĩa theo độ nhạy tài nguyên; không bỏ qua các kiểm tra bắt buộc như chữ ký, issuer, audience, expiry và trạng thái account.

**9. Context thấp rủi ro có thể thay thế authorization không?**  
Không. Context không cấp role hay quyền trên object. API vẫn phải kiểm tra subject, tenant, resource, action và policy.

**10. Vì sao cần gắn step-up với transaction cụ thể?**  
Để kết quả xác thực tăng cường không bị dùng lại cho action khác hoặc request đã thay đổi sau khi người dùng xác nhận.

**Ghi nhớ:** Context thay đổi khiến mức tin cậy của một request có thể khác với thời điểm đăng nhập. Hãy dùng tín hiệu có nguồn và độ mới rõ ràng, không nhầm context với factor hoặc authorization, đánh giá lại trước hành động nhạy cảm và chọn allow/limit/step-up/deny/revoke theo policy. Context-aware authentication tốt bảo vệ cả tính an toàn lẫn trải nghiệm bằng cách phản ứng theo rủi ro thực tế, không dựa vào một tín hiệu đơn lẻ.
