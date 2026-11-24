# Forced factor reset

## 1. Forced factor reset là gì?

Trong module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, forced factor reset là một biện pháp ứng phó sự cố: hệ thống hoặc người vận hành có thẩm quyền vô hiệu hóa những authenticator binding không còn đáng tin và yêu cầu người dùng đi qua quy trình xác minh, đăng ký lại phù hợp.

Mục tiêu là cắt khả năng truy cập của kẻ đang giữ factor hoặc quyền được cấp từ factor đó, đồng thời tạo đường khôi phục có kiểm soát cho chủ tài khoản. Việc xóa một dòng TOTP hoặc passkey trong database mới chỉ là một phần của tác vụ.

NIST mô tả invalidation là loại bỏ binding giữa authenticator và tài khoản; hướng dẫn cũng yêu cầu xử lý kịp thời authenticator bị compromise và đánh giá tính xác thực của yêu cầu thu hồi theo rủi ro. [NIST SP 800-63B-4 — Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/#invalidation).

Trong bài này, “reset” không có nghĩa đặt `mfaEnabled=false` rồi cho tài khoản tiếp tục hoạt động bình thường bằng mật khẩu. Policy yêu cầu mức xác thực nào vẫn cần được thực thi trong suốt quá trình chuyển trạng thái.

Tên trạng thái, field và API bên dưới là mô hình minh họa để học thiết kế. Chúng không khẳng định hệ thống hiện tại đã có một chức năng admin hay runbook tương ứng, và không phải chỉ dẫn thực hiện reset thật trên tài khoản cụ thể.

### 1.1. Phân biệt các thao tác gần nhau

| Thao tác | Ý nghĩa | Điều không tự đạt được |
| --- | --- | --- |
| Suspend factor | Tạm ngừng chấp nhận factor theo policy | Chưa chắc đã loại bỏ hoàn toàn binding |
| Revoke factor | Không còn chấp nhận binding đã thu hồi | Không tự xóa session cũ |
| Require reenrollment | Bắt buộc đăng ký lại trước khi có quyền tương ứng | Không tự chứng minh danh tính caller |
| Revoke sessions | Thu hồi session/token trong phạm vi được chọn | Không tự vô hiệu hóa factor vẫn đăng nhập mới được |
| Rotate recovery codes | Cấp thế hệ mã mới, vô hiệu hóa thế hệ cũ theo policy | Không thay việc kiểm tra factor khác bị lộ |
| Lock or restrict account | Hạn chế quyền tài khoản để containment | Không phải hoàn tất account recovery |

Việc tách các tác động giúp runbook biết mình đã làm gì, còn việc gì đang chờ và bằng chứng nào đủ để khôi phục quyền.

## 2. Khi nào cân nhắc reset bắt buộc?

Các tình huống thường cần phân tích gồm thiết bị xác thực bị mất, TOTP seed bị lộ, passkey binding được đăng ký trái phép, kênh nhận mã bị chiếm, recovery codes bị sao chép hoặc nhân viên hỗ trợ đã thực hiện thay factor không đúng thẩm quyền.

Cũng có sự cố không bắt đầu từ factor: session bị đánh cắp có thể được dùng để đăng ký factor của kẻ tấn công. Khi đó chỉ thu hồi factor gốc của nạn nhân sẽ bỏ sót authenticator mới mà kẻ tấn công đã thêm.

| Tình huống | Phạm vi cần điều tra | Hướng xử lý ban đầu cần cân nhắc |
| --- | --- | --- |
| Mất một thiết bị có authenticator | Những binding thực sự nằm trên thiết bị | Thu hồi binding liên quan, đánh giá session |
| Lộ TOTP seed | Bản sao seed và những account dùng seed đó | Thu hồi seed, tạo secret mới qua quy trình bảo vệ |
| Đăng ký passkey trái phép | Credential mới, phiên đăng ký, actor và proof | Thu hồi binding trái phép, xem xét quyền còn tồn tại |
| Kênh SMS hoặc email bị chiếm | Factor, recovery và thông báo phụ thuộc kênh | Không dùng chính kênh bị chiếm làm bằng chứng duy nhất |
| Recovery codes bị lộ | Thế hệ code, các lần đã sử dụng, grant phát sinh | Vô hiệu hóa code liên quan và kiểm tra tác động tiếp theo |
| Compromise tài khoản admin/IdP | Những account, factor và session admin đã tác động | Phân tích phạm vi rộng hơn một người dùng |
| Báo mất factor chưa được xác minh đầy đủ | Độ tin cậy nguồn báo và nguy cơ tiếp tục lạm dụng | Có thể containment theo policy, chưa cấp quyền đăng ký mới |

Không cần đợi biết toàn bộ nguyên nhân mới thực hiện một biện pháp containment đã được thẩm quyền cho phép. Tuy nhiên, lý do để chặn một factor nghi bị lộ không tự trở thành bằng chứng cho phép caller đăng ký factor thay thế.

### 2.1. Quyền báo mất khác quyền nhận lại tài khoản

Một người có thể báo “thiết bị của tôi bị mất” qua một kênh hạn chế. Policy có thể cho phép tạm chặn authenticator để giảm nguy cơ. Điều đó không đồng nghĩa người báo đã đủ điều kiện nhận recovery grant hoặc thay số điện thoại.

Tách hai quyết định: mức bằng chứng cần để giảm quyền đang có rủi ro, và mức bằng chứng cần để cấp quyền mới. Cách tách này vừa hỗ trợ ứng phó nhanh vừa tránh biến báo mất thành một đường chiếm tài khoản.

## 3. Xác định phạm vi bằng dữ liệu cụ thể

Một lệnh reset cần chỉ rõ tenant, account, incident, những binding bị tác động và điều kiện version. Không dùng tên hiển thị của factor làm định danh duy nhất.

Một kế hoạch minh họa:

```yaml
incidentRef: incident-test-004
operationId: reset-operation-test-001
tenantRef: tenant-test-a
subjectRef: account-test-001
expectedFactorVersion: 12
targetCredentialRefs:
  - credential-test-a
  - credential-test-b
requiredAccountGate: ENROLLMENT_REQUIRED
sessionPolicyRef: incident-session-policy-v1
recoveryMaterialPolicyRef: invalidate-affected-generations-v1
reasonCode: SUSPECTED_AUTHENTICATOR_COMPROMISE
```

Kế hoạch không chứa seed, raw token, mật khẩu, mã recovery hoặc khóa riêng. Các reference cần được tra cứu từ nguồn có kiểm soát và được ràng buộc đúng tenant.

### 3.1. Snapshot không thay thế containment liên tục

Một danh sách credential được chụp tại thời điểm t0 có thể bỏ sót credential kẻ tấn công thêm ở t1. Vì vậy phải xét khả năng đăng ký factor mới trong lúc xử lý.

Có thể cần chặn enrollment ngoài luồng ứng phó, áp dụng account security generation hoặc kiểm tra version tại commit. Nếu snapshot đã cũ, hệ thống nên yêu cầu đánh giá lại thay vì âm thầm áp dụng kế hoạch lên một tập factor khác.

Ngược lại, một worker retry lệnh “xóa mọi factor hiện có” ở t2 có thể xóa cả factor mới của chủ tài khoản đã đăng ký hợp lệ. Scope cần được đóng băng hoặc được diễn giải bằng generation và điều kiện rõ ràng, không tự thay đổi theo thời điểm retry.

### 3.2. Không mặc định reset mọi thứ

Nếu chỉ một binding được xác định có rủi ro và vẫn còn một authenticator độc lập đáng tin, policy có thể giữ đường đó để phục hồi. Nếu nền tảng đồng bộ hoặc control plane đã bị compromise, phạm vi có thể lớn hơn.

Quyết định dựa trên đường tấn công và mối phụ thuộc thật. “Người dùng còn một factor” chưa đủ nếu factor đó nằm trên cùng thiết bị bị kiểm soát hoặc phụ thuộc cùng tài khoản đồng bộ đã bị chiếm.

Đối với tài khoản đặc quyền, workload hoặc emergency access, cần một policy riêng phù hợp. Không áp dụng máy móc luồng khách hàng tự phục vụ cho mọi loại principal.

## 4. Thẩm quyền thực hiện và phòng lạm dụng hỗ trợ

Reset factor là một thao tác có thể chuyển quyền kiểm soát tài khoản. Quyền xem ticket, quyền xem hồ sơ khách hàng và quyền thu hồi/đăng ký factor phải được phân biệt.

Một người vận hành cần có quyền đúng tenant, đúng loại tác động và đúng mức rủi ro. Tài khoản vận hành, thiết bị làm việc và factor dùng phê duyệt cũng phải nằm ngoài phạm vi compromise đang được xử lý, hoặc có cơ chế thay thế đã định.

OWASP khuyến nghị xem thay factor là hành động rủi ro cao, không chỉ tin một session đang hoạt động và thông báo khi factor thay đổi. Khi còn factor đáng tin, tái xác thực thích hợp là một phần quan trọng của kiểm soát. [OWASP Multifactor Authentication Cheat Sheet — Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors).

Nếu không còn factor đáng tin, phải chuyển sang đường recovery/identity verification được thiết kế cho tình huống đó. Không buộc người dùng dùng lại factor đã xác định bị lộ chỉ để thỏa một bước “reauthentication”.

### 4.1. Phê duyệt theo loại tác động

Policy có thể yêu cầu người phê duyệt độc lập cho tài khoản đặc quyền, tác động hàng loạt hoặc override mức rủi ro cao. Đây là lựa chọn kiểm soát của tổ chức, không phải mọi reset đều mặc định cần đúng hai người.

Điều cần rõ là ai có quyền containment khẩn cấp, ai cho phép đăng ký lại, ai có quyền khôi phục quyền đầy đủ và điều kiện nào làm phê duyệt hết hiệu lực.

Một phê duyệt nên ràng buộc tới incident, subject, scope, operation và version/policy. Nếu scope thay đổi từ một factor sang toàn bộ tenant, phê duyệt cũ không được tự mở rộng theo.

### 4.2. Những bằng chứng dễ bị dùng sai

Tên chức danh, lời nói khẩn cấp, email mới do caller cung cấp hoặc việc biết thông tin công khai về nạn nhân không đủ để nhận quyền reset theo mặc định.

Một session có tuổi đời lâu cũng không chắc còn đáng tin; ngược lại, một tín hiệu rủi ro như IP mới không tự chứng minh account đã bị chiếm. Tách dữ kiện, giả thuyết và quyết định policy trong incident record.

Khi support account bị nghi compromise, không để chính phiên support đó phê duyệt enrollment mới. Đường ứng phó cần một gốc tin cậy độc lập phù hợp với hệ thống.

## 5. Giữ bằng chứng và lập kế hoạch tác động

Thu thập dữ liệu tối thiểu cần để hiểu phạm vi: factor inventory, thời điểm enrollment, actor, session liên quan, lịch sử đổi kênh recovery, policy decision và các lần sử dụng bất thường.

Không trì hoãn containment cần thiết chỉ để thu thập một bộ log hoàn hảo. Có thể ghi snapshot tối thiểu, thực hiện chặn rồi tiếp tục điều tra với dấu thời gian và trạng thái đã biết.

| Nhóm dữ liệu | Nội dung nên có | Nội dung tránh ghi trực tiếp |
| --- | --- | --- |
| Incident | ID, owner, reason code, giả thuyết và mức tin cậy | Bí mật xác thực của người dùng |
| Actor | Principal thực hiện, scope quyền, approval reference | Cookie hoặc access token admin |
| Subject | Tenant/account reference, loại account | Hồ sơ cá nhân không cần cho tác vụ |
| Factor | Credential reference, type, version, trạng thái trước/sau | TOTP seed, private key, recovery code |
| Session | Reference, auth epoch, phạm vi cần thu hồi | Session cookie, refresh token plaintext |
| Operation | Idempotency key, scope fingerprint, outcome | Payload bí mật được dump toàn bộ |
| Timeline | Thời điểm yêu cầu, commit, propagation và xác minh | Timestamp không có timezone hoặc không biết nguồn |

Nếu cần lưu chi tiết phục vụ điều tra, đặt trong kho bằng chứng có kiểm soát truy cập và vòng đời rõ ràng. Một comment support thông thường không phải nơi lưu seed hoặc token để “khôi phục lại nếu nhầm”.

Hash của bản ghi giúp đối chiếu thay đổi nhưng không tự chứng minh nguồn dữ liệu là đúng. Cần biết ai thu thập, từ đâu, lúc nào và có những khoảng thiếu quan sát nào.

## 6. Mô hình trạng thái không tạo khoảng trống MFA

Nên tách trạng thái operation ứng phó khỏi trạng thái quyền của account.

```text
Operation:
PLANNED -> AUTHORIZED -> LOCAL_CONTAINMENT_COMMITTED
         -> PROPAGATION_PENDING -> CONTAINMENT_VERIFIED
         -> REENROLLMENT_TRACKED -> CLOSED

Account access:
NORMAL -> RESTRICTED / ENROLLMENT_REQUIRED
       -> RECOVERY_AUTHORIZED
       -> NEW_FACTOR_PROVEN
       -> NORMAL
```

Tên trạng thái chỉ minh họa. Không phải mọi triển khai đều tuần tự hoàn toàn: việc điều tra có thể tiếp tục trong khi containment đã hoạt động, và một operation có thể dừng vì không đủ bằng chứng.

### 6.1. Gate cần được thực thi phía server

Sau khi thu hồi factor cuối cùng, hệ thống không được suy ra rằng “không còn MFA nên chỉ cần mật khẩu”. Account vẫn mang yêu cầu xác thực tương ứng và được chuyển vào trạng thái hạn chế.

Gate phải được áp dụng ở login, token issuance và các API nhạy cảm thích hợp. Một banner “hãy cài lại MFA” ở frontend không ngăn caller gọi thẳng API chuyển tiền, đổi email hoặc thêm admin.

Nếu cấp một session chỉ dùng cho recovery/enrollment, quyền của session đó phải hạn chế rõ: không kế thừa quyền đầy đủ từ account, không thay kênh tùy ý, không tạo API key và không dùng làm bằng chứng cho một recovery khác ngoài phạm vi.

### 6.2. Không công bố hoàn tất khi còn quyền chưa thu hồi

Database local có thể đã đánh dấu factor REVOKED trong khi cache, IdP hoặc resource server chưa nhận thay đổi. Operation nên phân biệt commit nội bộ với propagation và verification.

Nếu một dependency chưa thực thi được việc thu hồi, giữ trạng thái còn việc chờ và áp dụng biện pháp hạn chế thích hợp. Không đổi nhãn thành “an toàn hoàn toàn” chỉ vì job đã được gửi vào queue.

Điều kiện đóng containment cần gắn với yêu cầu cụ thể: những factor nào bị từ chối, session nào không còn truy cập, grant nào bị chặn và đường nào vẫn đang được quan sát.

## 7. Thu hồi factor và chặn quyền đang có rủi ro

Một mô hình transaction nội bộ có thể gồm:

```text
BEGIN
  Xác minh operation/approval còn hiệu lực và scope không đổi
  Kiểm tra tenant, subject và expected factor/security version
  Đánh dấu các binding mục tiêu bị thu hồi
  Đặt account gate theo policy
  Cập nhật security generation nếu thiết kế sử dụng
  Vô hiệu hóa recovery/enrollment grants thuộc phạm vi bị ảnh hưởng
  Ghi ý định thu hồi session và thông báo vào outbox
  Ghi audit/outcome của operation
COMMIT

Thực thi tác động bên ngoài và xác minh kết quả theo từng đích
```

Đây là mã giả, không phải transaction bao trùm mọi hệ thống. Database, session service và IdP bên ngoài có thể có ranh giới commit riêng.

### 7.1. Chặn đường đăng nhập mới

Mọi verifier đang chấp nhận factor mục tiêu cần đọc trạng thái thu hồi hoặc nhận cơ chế invalidation theo thiết kế. Chỉ ẩn factor khỏi màn hình quản lý không ngăn assertion hoặc OTP được gửi trực tiếp.

Một phiên đăng nhập có thể đang ở giữa bước xác minh và cấp session lúc reset xảy ra. Kiểm tra version hoặc authorization phải được thực hiện ở điểm commit/cấp quyền thích hợp, để kết quả từ factor cũ không vượt qua thời điểm thu hồi.

Đối với cache, cần biết TTL, event invalidation và hành vi khi event thất lạc. Nếu yêu cầu chặn tức thời nhưng verifier chỉ dùng cache cũ trong nhiều phút, đó là khoảng trống thiết kế cần được xử lý, không chỉ vấn đề hiển thị tiến độ.

### 7.2. Chặn quyền khôi phục cũ

Recovery token, enrollment ticket, remembered-device token hoặc approval đang chờ có thể đã được cấp dựa trên trạng thái cũ. Phải đánh giá chúng có nằm trong phạm vi compromise không.

Một token một lần còn hạn vẫn có thể không được dùng sau forced reset nếu operation đã vô hiệu hóa thế hệ quyền đó. Validator cần kiểm tra cả trạng thái/generation hiện hành, không chỉ chữ ký và expiry.

Không mặc định mọi token của toàn bộ tenant đều cần bị xóa. Phạm vi thu hồi cần đủ để chặn đường tấn công, có thể kiểm chứng và không tạo tác động lan rộng ngoài quyết định.

## 8. Xử lý từng loại factor

| Loại | Tác động cần xem xét | Điểm dễ hiểu sai |
| --- | --- | --- |
| TOTP/HOTP | Thu hồi binding/secret cũ, chuẩn bị secret mới qua enrollment | Đổi nhãn thiết bị không làm seed bị lộ mất hiệu lực |
| WebAuthn/passkey | Không còn chấp nhận credential binding mục tiêu tại RP | Không đồng nghĩa đã xóa mọi bản sao trên thiết bị hoặc nền tảng đồng bộ |
| Push authenticator | Thu hồi đăng ký thiết bị và quyền xác nhận tương ứng | Hủy notification chưa chắc hủy device binding |
| SMS/voice factor | Chặn binding kênh bị ảnh hưởng, xác minh đường thay thế | Gửi mã mới tới số đang bị chiếm không sửa được compromise |
| Email-based recovery | Đánh giá kênh recovery và proof phát sinh | Đổi mật khẩu ứng dụng không tự bảo vệ mailbox |
| Recovery codes | Vô hiệu hóa thế hệ liên quan, cấp bộ mới sau xác minh | Bộ code mới không được phát cho session nghi bị chiếm |
| Certificate/device credential | Thu hồi binding và xử lý cơ chế tin cậy liên quan | Chỉ xóa record ứng dụng có thể chưa tác động mọi verifier |
| Password | Đánh giá riêng việc bị lộ và yêu cầu thay theo incident | Reset MFA không tự đổi mật khẩu hoặc chặn session cũ |

### 8.1. Passkey và phạm vi credential

Một passkey có thể có nhiều bản sao được đồng bộ cùng credential. Nếu RP không còn chấp nhận credential binding đó, assertion dùng binding bị thu hồi phải bị từ chối bất kể bản sao nào tạo ra.

Điều này là chặn tại phía dịch vụ, không phải bảo đảm remote wipe thiết bị. Với sự cố ảnh hưởng một nền tảng đồng bộ, cần điều tra những credential và account có mối phụ thuộc liên quan thay vì chỉ tên một thiết bị hiển thị.

Không dùng số lần ký hoặc tên model thiết bị như bằng chứng duy nhất để quyết định một binding còn sạch. Những tín hiệu đó có giới hạn và phải được hiểu theo loại authenticator và policy.

### 8.2. TOTP và đăng ký lại

Sau khi seed cũ bị lộ, cần một secret mới nếu người dùng tiếp tục sử dụng TOTP. Việc tăng thời gian chờ, đổi tên factor hoặc yêu cầu nhập thêm một mã từ cùng seed không tạo lại tính bí mật.

Secret mới cần được chuyển và kiểm chứng trong luồng enrollment bảo vệ phù hợp. QR chứa seed không được ghi vào ticket, log, ảnh chụp hỗ trợ hoặc thông báo sự cố.

Nếu enrollment mới bị gián đoạn, trạng thái pending không được tự thành ACTIVE. Luồng cần hết hạn và cleanup theo policy, đồng thời không làm mất dấu factor cũ đã bị thu hồi.

## 9. Session, refresh token và liên kết xác thực

Factor là một đường tạo quyền; session và token là những quyền có thể đã được cấp trước đó. Thu hồi factor không tự làm những quyền này biến mất.

Lập inventory theo loại: cookie session ở ứng dụng, refresh-token family, access token, remembered-device token, session tại IdP và các phiên tại relying party. Với API key hoặc quyền workload được tạo trong thời gian compromise, cần đánh giá riêng theo incident; không mặc định chúng là “MFA session”.

### 9.1. Token tự chứa và độ trễ thu hồi

Nếu resource server chỉ kiểm tra chữ ký và expiry của một access token tự chứa, việc đổi trạng thái factor ở database không tự khiến token đó bị từ chối. Cần cơ chế kiểm tra trạng thái, epoch/version, denylist, gateway containment hoặc biện pháp khác phù hợp với yêu cầu hệ thống.

Một TTL ngắn giới hạn thời gian token còn dùng được, nhưng không tương đương thu hồi tức thời. Khi mô tả containment, cần công bố và kiểm tra khoảng thời gian còn rủi ro theo policy, không gộp hai khái niệm.

RFC 7009 mô tả thu hồi token OAuth và lưu ý về propagation delay. Phản hồi 200 cũng có thể được trả khi token đã không hợp lệ; vì vậy một response thành công không tự chứng minh toàn bộ token/session liên quan ở mọi đích đã bị chặn. [RFC 7009 — Token Revocation và Revocation Response](https://www.rfc-editor.org/rfc/rfc7009.html#section-2).

Không đổi khóa ký dùng chung chỉ để thu hồi một account nếu chưa xác định đó là phạm vi cần thiết. Xoay khóa có thể ảnh hưởng nhiều principal và không thay thế việc hiểu các token đang được verifier chấp nhận.

### 9.2. Phạm vi theo generation hoặc cutoff

Một event thu hồi có thể nhắm tới các session trước một security generation hoặc mốc sự cố xác định. Scope cần được giữ ổn định qua retry và callback muộn.

Nếu sau recovery hợp lệ đã có session mới ở generation sau, bản giao lại của operation cũ không được tự thu hồi phạm vi mới ngoài policy. Ngược lại, nếu policy yêu cầu tiếp tục cô lập toàn account cho tới khi incident owner cho phép, session mới cũng phải chịu gate đó.

Không dùng một phép “đăng xuất tất cả hiện tại” lặp lại vô hạn mà không biết mỗi lần đang tác động ai. Thiết kế phải xác định rõ mục tiêu là một tập quyền đã cấp, mọi quyền trước một thế hệ hay toàn bộ account cho tới khi được mở lại.

### 9.3. Federation và các hệ thống đích

Reset factor tại IdP có thể chưa đóng cookie ở ứng dụng; đóng cookie ứng dụng có thể chưa làm IdP session hết hiệu lực. Một lần chuyển hướng SSO tiếp theo có thể cấp quyền lại nếu IdP vẫn xem phiên cũ là hợp lệ.

Theo dõi từng đích với trạng thái riêng: requested, applied, verified hoặc unknown. Kiểm chứng bằng hành vi bị từ chối ở nơi sử dụng quyền khi có thể, không chỉ dựa vào log “đã gửi lệnh logout”.

Nếu dùng các claim như `acr`, `amr` hoặc thời điểm xác thực, không giữ nguyên mức bảo đảm cũ trong token mới chỉ vì người dùng đã vào được trang enrollment. Những claim đó phải phản ánh quá trình xác thực mà hệ thống thực sự kiểm chứng.

## 10. Xác minh lại danh tính và cấp quyền enrollment có giới hạn

Sau containment, câu hỏi tiếp theo là ai được quyền đăng ký factor thay thế. Câu trả lời cần dựa vào bằng chứng còn đáng tin hoặc quy trình account recovery đã được thiết kế.

Các khả năng có thể gồm một authenticator độc lập còn hợp lệ, recovery code chưa bị compromise, kênh recovery đã chuẩn bị trước hoặc quy trình identity verification/hỗ trợ phù hợp. Không có một danh sách bằng chứng chung áp dụng an toàn cho mọi sản phẩm.

Không coi việc người dùng biết mật khẩu là luôn đủ. Incident có thể bao gồm password phishing, session theft hoặc compromise kênh recovery; yêu cầu proof cần xét đúng những gì đã bị ảnh hưởng.

### 10.1. Bootstrap grant cho đăng ký factor

Nếu cần cấp một quyền tạm để hoàn tất enrollment, grant nên ràng buộc với subject, tenant, incident/reset operation, security generation, purpose và hạn hiệu lực.

Ví dụ quyền khái niệm:

```text
purpose: FACTOR_ENROLLMENT
subject: account-test-001
tenant: tenant-test-a
resetOperation: reset-operation-test-001
securityGeneration: G-new
allowedActions:
  - begin-approved-factor-enrollment
  - prove-possession-for-pending-factor
expiresAt: thời hạn do policy xác định
usage: một lần theo hợp đồng enrollment
```

Grant này không nên trở thành quyền truy cập đầy đủ, quyền đổi contact tùy ý, quyền tạo API key hoặc quyền reset factor của account khác. Người dùng vào được luồng enrollment chưa đồng nghĩa đã hoàn tất authentication ở mức policy yêu cầu.

Nếu grant bị dùng lại sau khi enrollment đã hoàn tất hoặc sau một reset mới, hệ thống cần từ chối theo vòng đời và generation. Chỉ kiểm tra chữ ký cùng expiry là chưa đủ nếu grant đã bị thu hồi.

### 10.2. Chứng minh factor mới

Đối với TOTP, cần kiểm chứng mã từ secret mới trước khi chấp nhận trạng thái active theo policy. Đối với WebAuthn, dùng quy trình registration/verification phù hợp với RP, challenge, origin và các yêu cầu user verification của hệ thống.

Không tự hạ tiêu chuẩn vì đây là luồng “khẩn cấp”. Ví dụ một hệ thống yêu cầu authenticator có đặc tính nhất định cần kiểm tra đúng đặc tính đó, thay vì chấp nhận bất kỳ registration thành công nào.

Nên xác định rõ account gate được gỡ ở bước nào. Nếu chỉ bắt đầu enrollment mà chưa chứng minh factor mới đã đủ để gỡ restriction, caller có thể thoát luồng với factor chưa dùng được hoặc factor của kẻ tấn công.

### 10.3. Khôi phục quyền từ một phiên mới phù hợp

Sau khi factor mới được chấp nhận, có thể cần một bước authentication mới và token/session mới theo policy. Không nâng cấp mọi session cũ của account chỉ bằng cách đổi account state về NORMAL.

Với một phiên cũ có khả năng đã bị đánh cắp, việc cho phiên đó tự lấy lại quyền sẽ làm mất ý nghĩa của containment. Quyền mới phải gắn với các điều kiện xác thực và generation được hệ thống công nhận.

Không gửi raw seed, recovery code hoặc bootstrap grant qua cùng một kênh đã được xác định bị compromise. Việc chọn đường chuyển quyền là một phần của thiết kế recovery, không phải một chi tiết giao diện.

## 11. Race condition, retry và idempotency

Forced reset có thể chạy đồng thời với login, enrollment, recovery completion hoặc một reset khác. Những tình huống này phải được xử lý bằng điều kiện trạng thái đáng tin, không chỉ một cờ frontend.

| Cuộc đua | Nguy cơ | Điều kiện cần bảo vệ |
| --- | --- | --- |
| Login xác minh factor cũ rồi reset commit | Session được cấp từ factor đã bị thu hồi | Kiểm tra generation/trạng thái ở điểm cấp quyền |
| Enrollment bắt đầu trước reset, kết thúc sau | Factor mới gắn bằng grant cũ | Binding grant và account generation tại commit |
| Hai reset operation cùng tác động | Xóa phạm vi mới hoặc tăng epoch không đúng | Idempotency, version và scope cụ thể |
| Worker retry sau khi user đăng ký lại | Thu hồi cả factor mới hợp lệ | Không diễn giải lại scope cũ thành “mọi factor hiện tại” |
| Session revocation event tới muộn | Tác động ngoài cutoff đã phê duyệt | Fencing hoặc phạm vi thu hồi đã đóng băng |
| Proof được phê duyệt rồi bị thu hồi | Cấp enrollment từ proof không còn hiệu lực | Kiểm tra hiệu lực ở điểm policy yêu cầu |

### 11.1. Operation ID ổn định

Một retry kỹ thuật cần giữ operation identity và scope fingerprint. Cùng operation ID nhưng đổi tenant, subject hoặc credential list phải được xử lý như conflict theo hợp đồng, không âm thầm chọn dữ liệu mới.

Một cách xử lý khái niệm:

```text
Xác thực actor và quyền xem/thực thi operation
  -> nếu operation đã có outcome bền vững:
       đối chiếu scope/fingerprint, trả trạng thái đã biết phù hợp
  -> nếu chưa có outcome:
       kiểm tra approval, expected version và điều kiện hiện tại
       commit tác động được phép một lần
  -> theo dõi propagation ở các đích ngoài transaction
```

Không kiểm tra expected version theo cách khiến mọi retry của operation đã thành công bị hiểu thành một reset mới. Tuy vậy, quyền trả outcome cho caller vẫn cần được kiểm soát để tránh rò rỉ thông tin account.

### 11.2. Kết quả chưa rõ không phải thất bại chắc chắn

Nếu client timeout sau khi server đã commit reset, tự thực hiện một reset mới với scope động có thể gây tác động thêm. Cần một đường tra cứu/reconcile bằng operation reference và dữ liệu nguồn chuẩn.

Với dependency bên ngoài, ghi trạng thái chưa rõ khi chưa xác nhận được. Một job bị retry không phải bằng chứng việc thu hồi đã thất bại; một HTTP response thành công cũng cần được hiểu đúng hợp đồng endpoint.

### 11.3. Event cũ và khôi phục từ backup

Replay event, retry từ dead-letter queue hoặc restore database có thể đưa một lệnh reset cũ trở lại. Operation record, version/generation và trạng thái kết thúc cần ngăn việc hồi sinh quyền hoặc thu hồi sai phạm vi.

Nếu backup khôi phục cả binding đã revoked về trạng thái active, cơ chế restore phải giữ hoặc áp lại quyết định thu hồi theo runbook. Không xem rollback dữ liệu là một thao tác vô hại trong quản lý authenticator.

## 12. Runbook thực hành theo từng giai đoạn

Runbook sau là khung học tập để ánh xạ sang hệ thống cụ thể; mọi giá trị account, scope và thẩm quyền phải lấy từ incident đã được xác định.

### 12.1. Xác nhận và containment

1. Ghi incident reference, owner và dữ kiện ban đầu; phân biệt nghi ngờ với đã xác nhận.
2. Xác thực nguồn báo, kiểm tra quyền containment và xác định tenant/subject.
3. Lập inventory factor, session, recovery material và những thay đổi đáng ngờ.
4. Chọn phạm vi thu hồi cùng điều kiện version/generation.
5. Áp dụng gate hoặc biện pháp chặn cần thiết để ngăn quyền tiếp tục được cấp.
6. Commit thu hồi binding và ý định tác động liên quan theo thiết kế.
7. Đo propagation và kiểm tra factor/quyền cũ bị từ chối trong scope.

Không bắt buộc mọi hệ thống phải hoàn thành toàn bộ inventory trước một containment khẩn cấp. Nếu phải chặn sớm, ghi rõ những gì chưa biết và tiếp tục xác định phạm vi sau đó.

### 12.2. Khôi phục có kiểm soát

1. Xác định gốc tin cậy còn phù hợp để chứng minh chủ tài khoản.
2. Kiểm tra điều kiện recovery/identity verification theo mức rủi ro.
3. Cấp quyền enrollment hạn chế nếu luồng cần, có binding và vòng đời rõ.
4. Đăng ký và chứng minh factor mới, xử lý recovery codes liên quan.
5. Cấp authentication/session mới khi policy cho phép.
6. Kiểm tra quyền cũ vẫn bị chặn và các API nhạy cảm thực thi gate đúng.
7. Thông báo, tiếp nhận phản đối và tiếp tục giám sát theo incident.

### 12.3. Hoàn tất và học từ sự cố

Ghi kết quả theo từng target: factor revoked, session revoked, grant invalidated, enrollment completed, notification recorded và các ngoại lệ còn theo dõi.

Không đóng incident chỉ vì người dùng đã đăng nhập lại được. Nếu một session nghi bị chiếm còn truy cập resource server hoặc một factor của attacker vẫn hoạt động, mục tiêu bảo vệ chưa đạt.

Sau khi hoàn tất, xem lại nguyên nhân: support override, session bị lộ, enrollment không có step-up, kênh recovery yếu hoặc việc kiểm tra revocation không nhất quán. Sửa đường cấp quyền gây sự cố thay vì chỉ lặp reset mỗi lần có cảnh báo.

### 12.4. Tác động hàng loạt

Nếu phải reset nhiều account, cần manifest scope, policy version, idempotency theo subject và kết quả từng account. Kiểm tra số lượng, tenant và điều kiện lựa chọn trước khi thực thi.

Có thể dùng các đợt nhỏ và kiểm tra tiến triển nếu phù hợp với mức khẩn cấp. Không lấy sự thành công của vài account làm bằng chứng mọi account đều đã containment, và không để một lỗi khiến job tự mở rộng scope.

Thiếu một dependency hoặc có account ngoại lệ phải được báo theo trạng thái thật. Một phần còn pending không nên bị gộp vào con số completed.

## 13. Thông báo và xử lý phản đối

Thông báo giúp chủ tài khoản phát hiện thay đổi không do họ yêu cầu. NIST mô tả các thông báo độc lập cho những sự kiện như binding và account recovery để hỗ trợ phát hiện gian lận. [NIST SP 800-63B-4 — Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b/events/#account-notifications).

Nội dung nên nêu loại thay đổi, thời điểm, cách vào ứng dụng qua đường tin cậy và cách báo không đồng ý. Không gửi password, TOTP seed, private key hoặc mã recovery trong thông báo sự cố.

Một mẫu nội dung minh họa:

```text
Một phương thức xác thực của tài khoản đã bị vô hiệu hóa để bảo vệ tài khoản.
Bạn có thể được yêu cầu xác minh lại danh tính và đăng ký phương thức mới.

Nếu bạn không nhận biết sự kiện này, hãy mở ứng dụng từ địa chỉ bạn thường dùng
và liên hệ kênh hỗ trợ được công bố trong ứng dụng.
```

Không chỉ dựa vào contact vừa được thay trong cùng transaction nhạy cảm. Kênh thông báo cần được chọn theo dữ liệu và policy đáng tin; nếu kênh cũ bị compromise, cân nhắc đường độc lập và nội dung phù hợp với phạm vi rò rỉ.

### 13.1. Phản đối không tự khôi phục factor cũ

Một nút “không phải tôi” có thể kích hoạt containment bổ sung hoặc điều tra theo policy. Không nên mặc định click vào link thông báo đủ để re-enable một authenticator đã bị xác định bị lộ.

Nếu có tạm đình chỉ và cơ chế khôi phục, quy trình đó phải áp dụng đúng điều kiện. Với binding đã revoke vì compromise, một thao tác khác có thẩm quyền và bằng chứng phù hợp mới được quyết định đường tiếp theo; không hoàn tác bằng việc phục hồi seed cũ từ log.

Thông báo gửi lỗi là một vấn đề cần theo dõi, nhưng không tự làm vô hiệu quyết định containment đã commit. Runbook cần phân biệt trạng thái bảo vệ quyền với trạng thái delivery và khả năng liên hệ người dùng.

## 14. Mẫu hợp đồng kiểm thử Java

Đoạn sau minh họa JUnit 5 cho một policy fixture: factor nghi bị lộ bị revoke, quyền cũ thuộc scope bị thu hồi và account bị hạn chế cho tới khi enrollment hợp lệ hoàn tất. Các interface cần adapter tới hệ thống thật; đây chưa phải test chạy độc lập.

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

abstract class ForcedFactorResetContract {
    record SubjectRef(String tenant, String account) {}
    record FactorRef(String value) {}
    record SessionRef(String value) {}
    record OperationRef(String value) {}
    record EnrollmentRef(String value) {}

    interface Harness extends AutoCloseable {
        SubjectRef isolatedSubject();
        FactorRef enrolledTestFactor(SubjectRef subject);
        SessionRef sessionFromOldSecurityGeneration(SubjectRef subject);

        OperationRef executeApprovedReset(SubjectRef subject, FactorRef factor);
        void awaitContainmentVerified(OperationRef operation, Duration deadline);

        // Tạo proof thật từ dữ liệu test của factor cũ, không dùng proof sai giả.
        boolean oldFactorCanAuthenticate(SubjectRef subject, FactorRef factor);
        boolean oldSessionCanUseSensitiveApi(SessionRef session);
        boolean passwordOnlyCanUseSensitiveApi(SubjectRef subject);

        // Đi qua quy trình proof đã được policy fixture phê duyệt.
        EnrollmentRef beginWithApprovedIndependentRecoveryProof(
                SubjectRef subject, OperationRef operation);

        boolean enrollmentGrantCanUseSensitiveApi(EnrollmentRef enrollment);
        FactorRef registerAndProveNewFactor(EnrollmentRef enrollment);
        boolean freshAuthenticationCanUseSensitiveApi(
                SubjectRef subject, FactorRef factor);

        @Override
        void close();
    }

    protected abstract Harness newHarness();

    @Test
    void revokedFactorDoesNotCreateAPasswordOnlyAccessGap() {
        try (Harness h = newHarness()) {
            SubjectRef subject = h.isolatedSubject();
            FactorRef oldFactor = h.enrolledTestFactor(subject);
            SessionRef oldSession = h.sessionFromOldSecurityGeneration(subject);

            OperationRef operation = h.executeApprovedReset(subject, oldFactor);
            h.awaitContainmentVerified(operation, Duration.ofSeconds(10));

            assertFalse(h.oldFactorCanAuthenticate(subject, oldFactor));
            assertFalse(h.oldSessionCanUseSensitiveApi(oldSession));
            assertFalse(h.passwordOnlyCanUseSensitiveApi(subject));

            EnrollmentRef enrollment =
                    h.beginWithApprovedIndependentRecoveryProof(subject, operation);
            assertFalse(h.enrollmentGrantCanUseSensitiveApi(enrollment));

            FactorRef newFactor = h.registerAndProveNewFactor(enrollment);
            assertTrue(h.freshAuthenticationCanUseSensitiveApi(subject, newFactor));
            assertFalse(h.oldFactorCanAuthenticate(subject, oldFactor));
            assertFalse(h.oldSessionCanUseSensitiveApi(oldSession));
        }
    }
}
```

Fixture phải dùng factor/session tổng hợp đang hợp lệ trước reset và gọi đúng verifier/resource server cần đánh giá. Nếu old factor proof vốn sai mật mã, việc bị từ chối không chứng minh revocation hoạt động.

Để tránh false positive từ lỗi hạ tầng, harness phải phân biệt “bị từ chối vì policy” với timeout hoặc dependency unavailable. Một request không trả lời không phải bằng chứng session đã bị thu hồi đúng.

Hàm `beginWithApprovedIndependentRecoveryProof` phải đi qua cơ chế proof của môi trường test; không tự ghi cờ verified rồi kết luận quy trình xác minh an toàn. Những test riêng cần kiểm tra nguồn proof, expiry, replay và scope của grant.

## 15. Ma trận xác minh và điều kiện hoàn tất

| ID | Tình huống | Bằng chứng cần có |
| --- | --- | --- |
| FFR-01 | Factor mục tiêu đã revoke | Proof hợp lệ của factor cũ bị từ chối ở verifier |
| FFR-02 | Factor cuối bị thu hồi | Account không chuyển thành truy cập đầy đủ chỉ bằng password |
| FFR-03 | Session/refresh quyền cũ trong scope | Bị từ chối ở đúng nơi sử dụng quyền |
| FFR-04 | Resource server còn cache cũ | Propagation và khoảng rủi ro trong cam kết |
| FFR-05 | Login đang chạy khi reset commit | Không cấp session từ trạng thái factor cũ ngoài policy |
| FFR-06 | Enrollment grant được cấp trước reset | Không gắn factor mới bằng grant đã mất hiệu lực |
| FFR-07 | Grant enrollment hạn chế | Không gọi API nhạy cảm hoặc đổi subject/tenant |
| FFR-08 | Enrollment mới chưa chứng minh possession | Account gate chưa bị gỡ sớm |
| FFR-09 | Retry cùng operation | Không tác động lại ngoài scope, không xóa factor mới hợp lệ |
| FFR-10 | Cùng operation ID, payload scope khác | Conflict được xử lý rõ, không mở rộng tác động |
| FFR-11 | Worker timeout sau commit | Reconcile được outcome, không chạy reset mới vô điều kiện |
| FFR-12 | Callback/event session thu hồi tới muộn | Giữ scope generation/cutoff theo policy |
| FFR-13 | Recovery code/token cũ bị ảnh hưởng | Không còn cấp quyền trong thế hệ đã vô hiệu |
| FFR-14 | Actor support thiếu quyền hoặc sai tenant | Không reset hoặc cấp enrollment trái quyền |
| FFR-15 | Phê duyệt hết hạn hoặc scope đổi | Không dùng approval cũ ngoài điều kiện |
| FFR-16 | Provider/IdP thu hồi lỗi | Trạng thái pending/unknown và containment đúng |
| FFR-17 | Notification lỗi hoặc bị phản đối | Không làm hồi sinh factor compromise |
| FFR-18 | Restore/replay operation cũ | Không mở lại binding/quyền cũ hoặc tác động sai phạm vi |
| FFR-19 | Account không thuộc scope | Không bị thu hồi factor/session ngoài manifest |
| FFR-20 | Enrollment và authentication mới hoàn tất | Mức quyền và mức bảo đảm đúng policy, quyền cũ vẫn bị chặn |

“Hoàn tất local transaction” và “hoàn tất ứng phó” có thể là hai mốc khác nhau. Checklist của incident cần cho biết mốc nào đã đạt, chứng cứ nào xác nhận và phần nào còn chưa kiểm chứng.

Một report học tập có thể ghi:

```text
INCIDENT: incident-test-004
OPERATION: reset-operation-test-001
SCOPE: one tenant/account, explicit credential references
LOCAL_COMMIT: report actual outcome
FACTOR_INVALIDATION: report verifier observations
SESSION_CONTAINMENT: report target-by-target result
OLD_RECOVERY_MATERIAL: report affected generations
REENROLLMENT: pending / completed under approved proof
NOTIFICATION: intent and delivery tracked separately
OUTSTANDING_ITEMS: record pending and unknown results
CLOSURE: decide from actual evidence and policy
```

Không điền PASS theo mẫu khi mới viết bài hoặc mới chạy một unit test. Một API admin trả 200, một record revoked hoặc một lần đăng nhập mới thành công chưa đủ để thay thế toàn bộ bằng chứng.

## 16. Sai lầm thường gặp và bài tập

### 16.1. Những sai lầm cần nhận diện

- Xóa factor cuối rồi gỡ yêu cầu MFA trên account.
- Thu hồi factor nhưng giữ refresh token hoặc session nghi bị chiếm.
- Dùng session đang có làm bằng chứng duy nhất cho phép thay factor.
- Gửi enrollment grant tới kênh vừa được caller khai hoặc kênh đã bị chiếm.
- Reset mọi credential hiện tại mỗi lần worker retry.
- Xem việc revoke passkey ở RP như bảo đảm xóa khóa khỏi mọi thiết bị.
- Re-enable seed/factor đã compromise để “rollback nhanh”.
- Đóng incident khi user đăng nhập lại được nhưng chưa kiểm tra quyền của attacker.
- Gộp lỗi delivery thông báo với thất bại containment hoặc ngược lại.
- Dùng restore database mà không giữ các quyết định revocation cần thiết.

### 16.2. Bài tập tình huống

**Tình huống A — Session đã bị đánh cắp.** Attacker dùng session hợp lệ để thêm passkey, sau đó nạn nhân báo mất điện thoại. Xác định inventory cần xem, factor nào có thể bị tác động và vì sao chỉ xóa TOTP trên điện thoại chưa giải quyết đủ sự cố.

**Tình huống B — Mất phản hồi reset.** Admin API đã commit nhưng client timeout. Người vận hành bấm lại sau khi user đăng ký factor mới. Thiết kế operation identity và scope để retry không xóa factor mới ngoài quyết định ban đầu.

**Tình huống C — JWT vẫn còn hiệu lực.** Binding factor đã revoke ở database nhưng một resource server chỉ kiểm tra chữ ký/expiry. Mô tả bằng chứng cho thấy containment còn khoảng trống và các lựa chọn thiết kế phù hợp với yêu cầu thời gian thu hồi.

**Tình huống D — Không còn factor độc lập.** Người dùng mất passkey và TOTP cùng nằm trên thiết bị bị kiểm soát. Mô tả đường recovery được policy chấp nhận, quyền của phiên enrollment và điều kiện cấp session mới.

**Tình huống E — Reset nhầm.** Báo cáo sự cố được xác định là false positive sau khi binding đã revoke. Phân biệt suspension có thể khôi phục theo policy với revocation, và đề xuất một thao tác có thẩm quyền để cấp lại binding phù hợp thay vì phục hồi secret cũ từ log.

Một thiết kế forced factor reset đạt mục tiêu khi cắt được quyền không còn đáng tin, giữ nguyên yêu cầu xác thực trong thời gian khôi phục và chỉ cấp quyền mới sau những bằng chứng mà hệ thống có thể kiểm chứng.
