# Theo dõi MFA bypass

## 1. Mục tiêu theo dõi trong hệ thống PAM

Theo dõi MFA bypass là phát hiện và điều tra những trường hợp đường truy cập hoặc thao tác đặc quyền không đáp ứng yêu cầu xác thực nhiều yếu tố đã được tổ chức đặt ra. Trong quản lý truy cập đặc quyền (Privileged Access Management, PAM), phạm vi này bao gồm đăng nhập, kích hoạt quyền, lấy credential, mở phiên quản trị và thay đổi cấu hình nền tảng.

Mục tiêu không phải đếm số lần xuất hiện lời nhắc MFA. Cần xác định **thao tác nào đòi hỏi mức xác thực nào, bằng chứng nào được chấp nhận và hệ thống đã cho phép điều gì xảy ra**.

Sau bài học, người học có thể:

- Phân biệt bỏ qua kiểm soát, ngoại lệ được phê duyệt, tái sử dụng kết quả xác thực hợp lệ và thiếu dữ liệu.
- Lập danh mục các đường có thể dẫn đến quyền đặc biệt, kể cả đường quản trị phụ.
- Liên kết log xác thực với quyết định và phiên sử dụng quyền trong PAM.
- Thiết kế cảnh báo có căn cứ, có cách xử lý log trễ và có hướng điều tra.
- Đánh giá mức bao phủ, kiểm thử phát hiện và kiểm chứng biện pháp khắc phục.

Các trạng thái, field và rule trong bài là mô hình minh họa. Trước khi triển khai, cần ánh xạ chúng sang dữ liệu và ngữ nghĩa của hệ thống thực tế.

## 2. Định nghĩa bypass bằng yêu cầu kiểm soát

Một kết luận về bypass cần dựa trên yêu cầu áp dụng tại thời điểm sự kiện. Ví dụ:

```text
Yêu cầu đã được phê duyệt:
  Nhân sự kích hoạt capability quản trị production phải có
  kết quả xác thực đáp ứng phương thức và độ mới quy định.

Quan sát thực tế:
  PAM cấp capability đó cho một người dùng.

Câu hỏi điều tra:
  Có bằng chứng đáp ứng yêu cầu hoặc ngoại lệ hợp lệ cho
  đúng người, thao tác, tài nguyên và thời điểm này không?
```

Nếu yêu cầu xác thực không được đáp ứng nhưng quyền vẫn được cấp, có thể xác nhận một khoảng hở kiểm soát. Điều đó chưa tự chứng minh kẻ tấn công đã chiếm tài khoản; cần phân biệt sai cấu hình, ngoại lệ sai phạm vi và hành vi xâm nhập.

Một lần đăng nhập thất bại trước khi tới bước MFA cũng không phải bằng chứng đã vượt MFA thành công. Tương tự, một yêu cầu đã được duyệt nhưng chưa được kích hoạt không đồng nghĩa quyền đã được sử dụng.

Theo dõi cần giữ được các cấp độ: thử truy cập, quyết định cho phép, cấp quyền thực tế và hoạt động tại đích. Khi báo cáo ảnh hưởng, chỉ khẳng định đến cấp độ có bằng chứng.

## 3. Những trường hợp dễ bị gọi nhầm là bypass

| Quan sát | Có thể có nghĩa gì? | Điều cần làm rõ |
|---|---|---|
| Không có lời nhắc MFA mới | Kết quả trước đó vẫn được chấp nhận | Phương thức, độ mới và chính sách tại thao tác |
| Log ghi single-factor | Chưa đủ để kết luận toàn bộ ngữ cảnh | Chi tiết xác thực và kết quả trước đó |
| Policy không áp dụng | Không khớp phạm vi hoặc có điều kiện khác | Yêu cầu đã phê duyệt có bao phủ thao tác này không? |
| Đang có ngoại lệ | Có thể hợp lệ hoặc sai phạm vi/hết hạn | Hồ sơ, người duyệt, tài nguyên và thời gian |
| Không tìm thấy log MFA | Log trễ, thiếu liên kết hoặc thiếu thu thập | Chất lượng dữ liệu trước khi kết luận |
| MFA thành công rồi có hoạt động lạ | Có thể có rủi ro phiên hoặc tài khoản | Không giả định mọi hoạt động sau MFA đều đáng tin |

Trong Microsoft Entra, một số lần đăng nhập có thể chấp nhận MFA claim đã có từ trước. Tài liệu khuyến nghị không chỉ dựa vào `authenticationRequirement`; chi tiết xác thực lúc đầu cũng có thể chưa đầy đủ cho đến khi được tổng hợp. Vì vậy, một field đơn lẻ hoặc việc không xuất hiện prompt không đủ để xác nhận bypass. [Hướng dẫn đọc sự kiện MFA của Microsoft](https://learn.microsoft.com/en-us/entra/identity/authentication/howto-mfa-reporting).

Ngược lại, có claim nói rằng MFA đã xảy ra cũng chưa đủ cho mọi thao tác. Nếu policy yêu cầu phương thức cụ thể hoặc xác thực mới trong một khoảng thời gian, phải kiểm tra những điều kiện đó. Cần hiểu claim nào được nguồn có thẩm quyền xác minh, không chỉ tìm chuỗi ký tự “mfa” trong dữ liệu.

## 4. Tách bốn kết luận trong quá trình điều tra

Một mô hình phân loại có thể dùng:

- **Đáp ứng yêu cầu:** có bằng chứng xác thực phù hợp hoặc việc tái sử dụng kết quả đáp ứng chính sách.
- **Ngoại lệ hợp lệ:** đúng đối tượng, phạm vi, thời gian và điều kiện của một ngoại lệ được cho phép.
- **Chưa đủ bằng chứng:** thiếu dữ liệu, chưa liên kết được hoặc chưa xác định đúng policy áp dụng.
- **Vi phạm kiểm soát được xác nhận:** quyền hoặc thao tác thành công dù không đáp ứng yêu cầu, không có ngoại lệ hợp lệ.

Ngoài ra, cần theo dõi riêng những tín hiệu liên quan như reset phương thức MFA bất thường, đăng ký credential mới hoặc nghi ngờ chiếm phiên. Chúng có thể dẫn đến truy cập trái phép dù một lần xác thực trông hợp lệ về kỹ thuật.

Trạng thái “chưa đủ bằng chứng” phải có người phụ trách và hạn xử lý. Nó không phải cách đưa những phiên khó điều tra ra khỏi báo cáo. Nếu nguồn log bị mất, cần mở vấn đề về khả năng quan sát và đánh giá rủi ro, thay vì kết luận mọi phiên đều bình thường.

## 5. Lập danh mục đường truy cập cần bao phủ

Theo dõi chỉ cổng đăng nhập web PAM sẽ bỏ sót những đường khác dẫn đến quyền tương đương. Cần bắt đầu từ tài nguyên và quyền cần bảo vệ, rồi đi ngược để xác định các đường truy cập.

| Đường truy cập | Sự kiện cần quan sát | Khoảng hở có thể tồn tại |
|---|---|---|
| IdP → PAM web | Xác thực, federation, đăng nhập PAM | PAM chấp nhận bằng chứng không đủ hoặc sai ngữ cảnh |
| Kích hoạt role/capability JIT | Quyết định và quyền thực tế đã cấp | Chỉ bảo vệ đăng nhập ban đầu, không kiểm tra yêu cầu khi nâng quyền |
| Vault hoặc credential checkout | Lần lấy, tiết lộ hoặc sử dụng bí mật | Người nhận credential dùng đường ngoài PAM |
| Proxy quản trị | Mở phiên, tài khoản đích, thời lượng | Có đường SSH/RDP trực tiếp tương đương |
| Tài khoản quản trị local | Đăng nhập local và hoạt động quản trị | Không đi qua IdP hoặc policy được giám sát |
| CLI/API quản trị | Chủ thể, loại credential, quyền và tác vụ | Dùng token dài hạn thay cho đường có điều kiện xác thực |
| Khôi phục tài khoản | Reset, thêm/xóa phương thức, cấp phương thức tạm | Giảm yêu cầu mà thiếu kiểm tra và bằng chứng |
| Truy cập khẩn cấp | Mọi lần sử dụng cùng hoạt động sau đó | Nhầm tài khoản khẩn cấp với tài khoản được phép dùng thường xuyên |

Tài khoản người dùng, workload và tài khoản khẩn cấp cần được phân loại rõ. Không áp rule “phải có thao tác MFA của người” lên mọi service principal; nhưng cũng không để một tài khoản người dùng được gắn nhãn service account để thoát giám sát.

Đối với đường không hỗ trợ chính sách mong muốn, phải ghi nhận cách chặn, thay thế hoặc kiểm soát bù đắp. Không xem việc không có log IdP là bằng chứng đường đó không tồn tại.

## 6. Đối chiếu policy đã phê duyệt với cấu hình có hiệu lực

Có hai nguồn cần tách biệt:

1. **Yêu cầu được phê duyệt:** mức xác thực tổ chức muốn áp dụng cho loại chủ thể, thao tác và tài nguyên tại thời điểm đó.
2. **Cấu hình thực tế:** policy nào đang bật, đối tượng nào bị loại trừ, điều kiện nào khớp và thành phần nào thực thi.

Nếu chỉ dùng cấu hình hiện tại để xác định yêu cầu, việc tắt một policy có thể khiến công cụ giám sát kết luận rằng “không cần MFA”. Theo dõi cần phát hiện chênh lệch giữa baseline đã được cho phép và cấu hình đang chạy, đồng thời xử lý đúng những thay đổi baseline hợp lệ.

Lưu lịch sử policy, phiên bản, trạng thái bật/tắt, phạm vi người dùng/ứng dụng và thay đổi nhóm loại trừ. Khi điều tra một sự kiện cũ, không lấy cấu hình hôm nay rồi mặc định nó cũng áp dụng lúc sự kiện xảy ra.

Trong Microsoft Entra, `Not Applied` có nghĩa lần đăng nhập không khớp tiêu chí áp dụng policy trong ngữ cảnh được mô tả; report-only dùng để đánh giá tác động trước khi thực thi. Hai trạng thái này cần được đọc cùng phạm vi và yêu cầu thực tế, không xem là bằng chứng độc lập rằng MFA đã được cưỡng chế. [Tài liệu về chi tiết sign-in log](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-sign-in-log-activity-details).

Cũng không đồng nhất “Conditional Access success” với “đã hoàn thành đúng phương thức MFA cần cho thao tác PAM”. Cần kiểm tra policy liên quan và bằng chứng được hệ thống sử dụng.

## 7. Nguồn dữ liệu và trách nhiệm của từng nguồn

Một thiết kế giám sát nên có ít nhất các nhóm dữ liệu sau trong phạm vi đang bảo vệ:

| Nguồn | Dữ liệu đóng góp | Giới hạn cần biết |
|---|---|---|
| Hệ thống danh tính | Phương thức, kết quả, thời điểm và ngữ cảnh xác thực | Có thể tái sử dụng kết quả; không phản ánh mọi tác vụ ở đích |
| Audit cấu hình | Thay đổi policy, nhóm, phương thức và recovery | Thay đổi hợp lệ vẫn cần đối chiếu hồ sơ |
| PAM | Yêu cầu, quyết định, grant, lease, phiên và ngoại lệ | Trạng thái trên giao diện chưa chắc là quyền đã được cấp ở đích |
| Vault/proxy | Sử dụng credential, mở phiên và tài khoản đích | Cần biết loại credential và phạm vi quan sát |
| Hệ thống đích | Đăng nhập và hoạt động quản trị thực tế | Có thể dùng tài khoản chung, cần liên kết lại chủ thể |
| Quản lý công việc | Incident, change, người phụ trách, cửa sổ cho phép | Một mã ticket không tự chứng minh ngoại lệ hợp lệ |
| Pipeline giám sát | Độ trễ, lỗi thu thập, mất sự kiện, thay đổi schema | Thiếu dữ liệu có thể làm rule không hoạt động |

Các nguồn phải được bảo vệ phù hợp với quyền lực của chúng. Nếu một quản trị viên có thể sửa policy và xóa dấu vết thay đổi trong cùng phạm vi mà không có đối chiếu độc lập, khả năng giải thích sự kiện sẽ yếu.

Không đưa mật khẩu, OTP, private key, token đầy đủ hoặc cookie phiên vào SIEM để “dễ điều tra”. Dùng định danh sự kiện, tham chiếu bằng chứng và những thuộc tính tối thiểu cần thiết.

## 8. Mô hình sự kiện chuẩn hóa minh họa

Có thể chuẩn hóa hoạt động đặc quyền để so sánh các đường truy cập khác nhau. Ví dụ sau không phải schema của một nhà cung cấp:

```json
{
  "event_id": "evt-lab-517",
  "occurred_at": "2026-12-01T07:20:00Z",
  "ingested_at": "2026-12-01T07:20:18Z",
  "subject": {
    "issuer_id": "idp-lab",
    "subject_id": "user-an",
    "principal_type": "human"
  },
  "action": "privilege-activated",
  "target_scope": "payment-production-status-read",
  "request_id": "PAM-LAB-517",
  "grant_id": "grant-lab-517",
  "pam_session_id": "session-lab-91",
  "expected_policy_version": "pam-auth-policy-v7",
  "effective_policy_reference": "policy-evaluation-lab-72",
  "authentication_evidence_reference": "auth-event-lab-104",
  "exception_reference": null,
  "outcome": "success"
}
```

Định danh chủ thể nên gồm phạm vi nguồn danh tính, không chỉ tên hiển thị hoặc email có thể thay đổi. Dữ liệu về policy và bằng chứng xác thực phải được lấy từ nguồn đã xác minh, không nhận cờ `mfa_passed: true` do client gửi như một kết luận đáng tin.

Cần lưu riêng thời điểm sự kiện và thời điểm nhận log. Ví dụ này cũng không chứng minh các nguồn sẽ luôn cung cấp một khóa liên kết hoàn hảo; việc ánh xạ phải được kiểm thử và có cách biểu diễn khi chưa chắc chắn.

Không gộp một giá trị correlation ID bất kỳ thành bằng chứng duy nhất. Kết hợp định danh chủ thể, ứng dụng/tài nguyên, phiên, tham chiếu đã xác minh và quan hệ thời gian. Nếu phải dùng cách liên kết theo thời gian, ghi nhận độ tin cậy và nguy cơ ghép nhầm khi có nhiều lần xác thực gần nhau.

## 9. Đánh giá bằng chứng xác thực cho đúng thao tác

Với mỗi hoạt động thuộc phạm vi, cần xác định:

- Policy nào yêu cầu MFA hoặc mức xác thực cụ thể?
- Bằng chứng thuộc đúng chủ thể, nguồn và ngữ cảnh được chấp nhận không?
- Phương thức có đáp ứng yêu cầu, kể cả yêu cầu chống phishing nếu có không?
- Thời điểm xác thực có đáp ứng độ mới tại thao tác đặc quyền không?
- Có ngoại lệ hợp lệ cho chính hoạt động đó không?

Không suy thời điểm xác thực từ thời điểm phát hành một token bất kỳ mà chưa hiểu ngữ nghĩa. Một token mới có thể được phát hành dựa trên phiên đã có; nó không tự chứng minh người dùng vừa hoàn thành MFA mới.

Cũng không yêu cầu mọi lần truy cập phải có một event prompt mới nếu policy cho phép tái sử dụng kết quả. Mục tiêu là tuân thủ yêu cầu xác thực, không tạo cảnh báo cho cơ chế SSO được phép.

Nếu cần hardware key cụ thể hoặc user verification, một cờ MFA tổng quát có thể chưa đủ để xác nhận điều đó. Thiết kế phải chỉ rõ bằng chứng nào dịch vụ danh tính cung cấp và PAM diễn giải nó như thế nào. Khi không đủ dữ liệu để xác định, giữ trạng thái chưa xác minh thay vì đoán.

## 10. Các nhóm rule phát hiện

### 10.1. Hoạt động đặc quyền thành công nhưng bằng chứng không đáp ứng

Bắt đầu từ sự kiện cấp quyền hoặc sử dụng quyền thực tế, sau đó đối chiếu yêu cầu xác thực và ngoại lệ. Phân biệt bằng chứng đã xác nhận không đáp ứng với trường hợp chưa nhận đủ log.

Ưu tiên điều tra tăng theo phạm vi quyền và tác động quan sát được: xem trạng thái lab khác với sửa policy PAM hay lấy credential quản trị hạ tầng nhạy cảm.

### 10.2. Thay đổi làm giảm phạm vi MFA rồi có hoạt động đặc quyền

Theo dõi việc tắt policy, chuyển sang chế độ chỉ quan sát, sửa điều kiện hoặc thêm chủ thể vào nhóm loại trừ. Liên kết thay đổi đó với các lần cấp hoặc dùng quyền sau đó để xác định tác động.

Không chỉ tìm chuỗi “disable MFA”. Một thay đổi thành viên nhóm hoặc ánh xạ ứng dụng cũng có thể làm khác phạm vi áp dụng dù policy vẫn mang trạng thái bật.

### 10.3. Ngoại lệ hết hạn, vượt phạm vi hoặc không có hồ sơ

Ngoại lệ nên có chủ thể, tài nguyên, thao tác, lý do, người hoặc chính sách cho phép, thời điểm bắt đầu/kết thúc và điều kiện bù đắp. Dùng ngoài phạm vi hoặc sau thời hạn cần được đánh giá như một bất thường riêng.

Không đưa toàn bộ tài khoản ngoại lệ vào danh sách bỏ qua cảnh báo vĩnh viễn. Ngoại lệ vẫn là một luồng cần bằng chứng và đối chiếu.

### 10.4. Recovery và thay đổi phương thức trước truy cập nhạy cảm

Reset phương thức, thêm credential mới hoặc thay kênh khôi phục rồi kích hoạt quyền có thể là luồng hỗ trợ hợp lệ, cũng có thể cần điều tra. Đối chiếu hồ sơ hỗ trợ, người thực hiện thay đổi, xác minh danh tính và hoạt động tiếp theo.

Không kết luận đây là bypass chỉ vì phương thức mới được dùng; thay vào đó, đánh giá liệu chuỗi cấp lại và sử dụng có đáp ứng quy trình đã được cho phép hay không.

### 10.5. Đường truy cập ngoài điểm kiểm soát

Đối chiếu đăng nhập và tác vụ đặc quyền ở máy đích với phiên hoặc grant PAM khi chính sách yêu cầu đi qua PAM. Một đường trực tiếp không được phép có thể làm mất cả kiểm soát xác thực lẫn khả năng liên kết danh tính.

Cần kiểm tra những tài khoản được phép đi đường riêng theo thiết kế, như workload hoặc khẩn cấp, trước khi gắn nhãn. Các tài khoản đó vẫn phải có kiểm soát tương ứng, không phải vùng không giám sát.

## 11. Mã giả phân loại sự kiện

Ví dụ dưới đây dành cho thiết kế rule, không phải truy vấn có thể chạy trực tiếp trên log của nhà cung cấp:

```text
for each successfulPrivilegedEvent e:
    expected = approvedRequirementAt(e.subject, e.action, e.scope, e.time)

    if expected is UNKNOWN:
        emit("coverage-gap", e, reason="expected-policy-unresolved")
        continue

    evidence = resolveTrustedAuthenticationEvidence(e)
    exception = resolveApprovedException(e)

    if expected.requiresMFA is false:
        record("outside-this-MFA-rule", e)
        continue

    if exception.coversExactEvent and exception.isValidAt(e.time):
        emitOrRecord("approved-exception-use", e)
        continue

    if evidence.isMissingOrIncomplete:
        queueRecheck(e, reason="authentication-evidence-pending")
        continue

    if evidence.meetsMethodAndFreshness(expected):
        record("requirement-satisfied", e)
    else:
        emit("control-violation-candidate", e,
             reason="evidence-does-not-meet-requirement")
```

`approvedRequirementAt` dùng baseline có lịch sử và phạm vi rõ. `resolveTrustedAuthenticationEvidence` phải kiểm tra quan hệ với chủ thể và hoạt động, không chỉ tìm event gần nhất có cùng địa chỉ IP.

Rule tạo ứng viên điều tra. Để xác nhận vi phạm, cần kiểm tra mapping, ngữ nghĩa dữ liệu và việc quyền hoặc tác vụ thực sự thành công. Ngược lại, không trì hoãn cảnh báo rủi ro cao chỉ vì một nguồn phụ chưa tới; có thể phát cảnh báo sơ bộ với trạng thái bằng chứng rõ ràng rồi cập nhật.

Trường hợp không yêu cầu MFA trong rule này vẫn có thể thuộc rule khác, chẳng hạn thay đổi baseline trái phép hoặc workload dùng credential không được phép. Không coi `outside-this-MFA-rule` là kết luận toàn bộ hoạt động an toàn.

## 12. Log trễ, dữ liệu thiếu và cảnh báo sai

Các nguồn có thể gửi log không cùng lúc, cập nhật chi tiết sau hoặc phát lại sự kiện. Pipeline cần xử lý deduplication, sự kiện đến muộn và việc cập nhật kết luận.

Có thể dùng khoảng chờ đối chiếu cho loại dữ liệu đã biết độ trễ, nhưng giá trị phải dựa trên đo lường thực tế. Khi quá thời hạn mà chưa đủ dữ liệu, tạo hoặc chuyển vấn đề về thiếu bằng chứng; không đổi thành “MFA không xảy ra” một cách tự động.

Nên giám sát heartbeat thu thập, tỷ lệ lỗi parser, số sự kiện không ánh xạ được và độ trễ theo từng nguồn. Một rule không phát cảnh báo trong khi nguồn PAM ngừng gửi log không phải dấu hiệu hệ thống đang an toàn.

Địa chỉ IP, vị trí địa lý hoặc tên thiết bị là dữ liệu ngữ cảnh, không phải khóa nối danh tính tuyệt đối. Nhiều người có thể dùng cùng NAT hoặc VPN, và một người có thể thay đổi địa chỉ. Dùng chúng để hỗ trợ điều tra thay vì chứng minh duy nhất ai đã hoàn thành MFA cho một phiên.

## 13. Theo dõi tài khoản khẩn cấp và ngoại lệ

Tài khoản khẩn cấp có thể được thiết kế với phương thức và phụ thuộc khác tài khoản quản trị thông thường. Không mặc định tên “break-glass” đồng nghĩa không có MFA hoặc được miễn mọi kiểm soát.

Theo dõi mọi lần sử dụng, mục đích kích hoạt, người chịu trách nhiệm và hoạt động sau đăng nhập. Có thể cảnh báo cả lần diễn tập đã lên lịch, sau đó phân loại là kiểm thử được cho phép thay vì làm mất sự kiện trong hệ thống.

Microsoft khuyến nghị giám sát sign-in và audit log của tài khoản emergency access, cảnh báo khi có sử dụng và xem xét sau sự kiện. Chính sách xác thực cụ thể phải theo kiến trúc được chọn; việc là tài khoản khẩn cấp không tự đồng nghĩa phương thức yếu. [Hướng dẫn về tài khoản emergency access](https://learn.microsoft.com/en-us/entra/identity/role-based-access-control/security-emergency-access).

Một hồ sơ ngoại lệ cần đủ để kiểm tra chính hoạt động quan sát được. Chẳng hạn, ngoại lệ cho một tài khoản đọc trạng thái trong cửa sổ xử lý sự cố không tự cho phép tài khoản đó sửa policy xác thực cả ngày.

Sau khi kết thúc, đối chiếu việc đóng ngoại lệ, thu hồi quyền tạm và xử lý credential đã dùng. Không chỉ đóng ticket trong khi cấu hình loại trừ vẫn còn hiệu lực.

## 14. Điều tra và phản ứng theo bằng chứng

Một quy trình điều tra có thể thực hiện theo thứ tự:

1. Xác nhận chủ thể, thao tác, tài nguyên và mức thành công thực tế.
2. Xác định yêu cầu xác thực áp dụng tại thời điểm sự kiện.
3. Thu thập bằng chứng xác thực và kiểm tra cách liên kết.
4. Đối chiếu ngoại lệ, recovery, thay đổi policy và hồ sơ công việc.
5. Đánh giá hoạt động trước/sau, phạm vi quyền và dữ liệu đã tiếp cận.
6. Phân loại nguyên nhân, thực hiện phản ứng theo thẩm quyền và kiểm chứng khắc phục.

Phản ứng phụ thuộc loại rủi ro. Có thể cần tạm dừng grant mới, thu hồi phiên hoặc token, xử lý credential bị lộ, sửa điều kiện policy hay điều tra thiết bị. Không mặc định reset mật khẩu sẽ thu hồi mọi phiên ở mọi hệ thống.

Cũng không tự động vô hiệu hóa tất cả tài khoản chỉ từ một nhánh log thiếu trường. Tự động hóa phản ứng nên có điều kiện đã kiểm thử, phạm vi được cho phép và cách khôi phục. Với cảnh báo mức cao, ưu tiên hạn chế tác động trong khi bảo toàn dữ liệu cần thiết.

Sau khắc phục, thử lại đúng đường truy cập và cùng loại thao tác đã tạo khoảng hở. Chụp ảnh trạng thái “policy enabled” chưa chứng minh rằng đường CLI, phiên cũ hoặc tài khoản local đã được kiểm soát.

## 15. Chỉ số theo dõi và cách diễn giải

Các chỉ số hữu ích có thể gồm:

| Chỉ số | Ý nghĩa cần theo dõi |
|---|---|
| Tỷ lệ hoạt động thuộc phạm vi có bằng chứng phân loại được | Mức bao phủ của giám sát, không phải chỉ tỷ lệ có log |
| Số vi phạm kiểm soát đã xác nhận | Khoảng hở đã có đủ căn cứ; tách khỏi nghi ngờ chưa xác minh |
| Số trường hợp thiếu bằng chứng còn mở | Nợ về thu thập, mapping hoặc khả năng điều tra |
| Sử dụng ngoại lệ theo loại và tài nguyên | Phát hiện ngoại lệ trở thành cách làm thường xuyên |
| Thời gian phát hiện và xử lý | Khả năng phản ứng theo loại mức độ |
| Thay đổi phạm vi policy chưa đối chiếu hồ sơ | Rủi ro drift và quản trị cấu hình |
| Độ trễ, lỗi schema và mất nguồn | Sức khỏe của chính pipeline giám sát |

Mẫu số phải là tập hoạt động được xác định rõ, chẳng hạn các lần kích hoạt quyền thành công của người dùng thuộc policy đang đánh giá. Không chia số vi phạm cho mọi lần đăng nhập của toàn tổ chức rồi dùng tỷ lệ rất nhỏ để kết luận rủi ro thấp.

Hiển thị riêng số ngoại lệ và số chưa đủ bằng chứng. Nếu loại chúng ra khỏi báo cáo mà không nói rõ, tỷ lệ đáp ứng có thể đẹp hơn trong khi phần khó quan sát đang tăng.

Số người đã đăng ký MFA cũng không chứng minh mọi đường truy cập của họ đều bị cưỡng chế MFA. Báo cáo đăng ký, báo cáo thực thi và báo cáo hoạt động đặc quyền phục vụ những câu hỏi khác nhau.

## 16. Bộ kiểm thử phát hiện trong lab

Chỉ kiểm thử với tài khoản, dữ liệu và đường truy cập được cho phép. Dùng môi trường lab hoặc phát lại bộ sự kiện kiểm thử; không tắt MFA production chỉ để xem SIEM có báo hay không.

| Tình huống kiểm thử | Kết quả phân loại mong đợi |
|---|---|
| MFA mới đáp ứng policy, PAM cấp đúng quyền | Đáp ứng yêu cầu |
| Tái sử dụng kết quả còn hợp lệ theo policy | Không báo bypass chỉ vì không có prompt mới |
| Policy yêu cầu xác thực mới nhưng bằng chứng đã quá hạn, grant vẫn thành công | Ứng viên vi phạm, xác minh rồi kết luận theo bằng chứng |
| Log IdP đến sau log PAM trong độ trễ dự kiến | Chờ đối chiếu và cập nhật trạng thái |
| Log IdP không đến sau thời hạn xử lý | Khoảng thiếu bằng chứng, không âm thầm đóng là bình thường |
| Thêm người vào nhóm loại trừ rồi có cấp quyền | Liên kết thay đổi và hoạt động để đánh giá tác động |
| Report-only được nhầm là enforcement | Phát hiện chênh lệch với baseline đã phê duyệt |
| Ngoại lệ hợp lệ dùng đúng phạm vi | Ghi nhận sử dụng ngoại lệ, vẫn lưu bằng chứng |
| Ngoại lệ hết hạn nhưng tiếp tục cấp quyền | Cảnh báo theo điều kiện vi phạm |
| Recovery rồi thêm khóa mới và dùng quyền nhạy cảm | Điều tra chuỗi recovery, không chỉ nhìn lần MFA thành công |
| Đăng nhập thất bại ở bước đầu | Không kết luận bypass thành công |
| Máy đích có hoạt động đặc quyền không nối được PAM | Điều tra đường truy cập và khoảng thiếu liên kết |
| Workload hợp lệ không có prompt của người | Dùng rule theo loại chủ thể, không áp sai rule human MFA |
| Parser bỏ toàn bộ log do schema thay đổi | Cảnh báo sức khỏe pipeline |

Với mỗi phép thử, lưu đầu vào, kỳ vọng, kết quả thực tế, thời điểm phát hiện và cách analyst phân loại. Kiểm thử cả cảnh báo đúng lẫn trường hợp không nên cảnh báo để tránh làm người vận hành bỏ qua một rule quá ồn.

## 17. Bài thực hành xây dựng một rule hoàn chỉnh

Chọn một thao tác PAM trong lab, ví dụ kích hoạt quyền quản trị dịch vụ production giả lập. Xác định baseline xác thực, các ngoại lệ được phép và các nguồn dữ liệu chứng minh quyền đã được cấp.

Thiết kế schema liên kết, rule ứng viên vi phạm và rule thiếu bằng chứng. Mô tả cách xử lý SSO hợp lệ, log đến muộn, thay đổi policy và tài khoản khẩn cấp. Chỉ rõ ai nhận cảnh báo, ai xác minh và ai có quyền thực hiện phản ứng.

Chuẩn bị ba chuỗi sự kiện: một lần đáp ứng yêu cầu, một lần grant thành công khi bằng chứng không đáp ứng và một lần chưa đủ log. Kết quả cần cho thấy hệ thống phân biệt được cả ba, giữ được bằng chứng cho kết luận và kiểm chứng được việc sửa đúng đường truy cập sau điều tra.
