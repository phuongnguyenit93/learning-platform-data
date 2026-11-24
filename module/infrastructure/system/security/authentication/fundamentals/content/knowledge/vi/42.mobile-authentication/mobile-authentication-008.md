# Mobile recovery

**Mobile recovery** là quá trình khôi phục quyền truy cập và thiết lập lại trạng thái tin cậy khi người dùng mất thiết bị, đổi điện thoại, cài lại ứng dụng, mất authenticator, quên thông tin đăng nhập hoặc nghi ngờ credential trên thiết bị đã bị lộ. Một quy trình recovery an toàn phải xác minh đúng người yêu cầu, xác định account và thiết bị bị ảnh hưởng, cấp lại phương thức xác thực phù hợp, thu hồi credential cũ và khôi phục dữ liệu theo policy.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu nguyên lý xác thực danh tính từ credential, password, MFA, passkey và certificate đến token, session, identity linking và account recovery. Mobile recovery là phần quan trọng của vòng đời đó vì thiết bị thường chứa refresh token, passkey hoặc key reference, dữ liệu local và session có thể tiếp tục hoạt động sau khi thiết bị rời khỏi quyền kiểm soát của chủ sở hữu.

Điểm cốt lõi: **recovery là một luồng bảo mật có thể thay đổi hoặc cấp lại quyền kiểm soát account**. Nó không được trở thành đường tắt yếu hơn authentication thông thường. Việc nhận được SMS ở số điện thoại mới, biết một vài thông tin hồ sơ hoặc cầm được thiết bị đã mở khóa không tự chứng minh người yêu cầu là chủ account. Cần bằng chứng độc lập, policy theo rủi ro, thông báo qua kênh đã tin cậy và khả năng revoke credential/session bị ảnh hưởng.

## 1. Mobile recovery là gì?

Mobile recovery bao gồm những quy trình giúp người dùng tiếp tục hoặc lấy lại quyền truy cập sau khi trạng thái thiết bị hoặc authenticator thay đổi. Tình huống thường gặp:
- Điện thoại bị mất, bị đánh cắp hoặc hỏng.
- Người dùng mua thiết bị mới và muốn chuyển account.
- Ứng dụng bị gỡ rồi cài lại.
- Thiết bị được reset hoặc phục hồi từ backup.
- Người dùng mất passkey, security key, TOTP authenticator hoặc SIM.
- Biometric enrollment thay đổi khiến key cục bộ không còn dùng được.
- Refresh token bị revoke, hết hạn hoặc phát hiện reuse.
- Thiết bị bị root/jailbreak, nhiễm malware hoặc không còn đáp ứng policy.
- Nhân viên rời tổ chức và thiết bị công việc cần được thu hồi.
- Account bị chiếm và attacker đã thêm authenticator hoặc recovery method.

Recovery có thể gồm nhiều hoạt động riêng:
- Khôi phục quyền truy cập account.
- Đăng ký authenticator mới.
- Liên kết thiết bị mới.
- Thu hồi session/token/device cũ.
- Khôi phục dữ liệu local từ backup.
- Khôi phục trust hoặc enrollment của thiết bị doanh nghiệp.

Không nên gộp tất cả thành một thao tác “reset password”. Mỗi tài sản và credential có vòng đời, nguồn tin cậy và cách thu hồi riêng.

### 1.1. Phân biệt recovery với login, re-authentication và restore

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **Login/authentication** | Chứng minh quyền kiểm soát credential đang hoạt động. | Dùng passkey để đăng nhập trên điện thoại hiện tại. |
| **Re-authentication** | Xác minh lại user trước hành động nhạy cảm. | Dùng passkey cũ trước khi đổi recovery email. |
| **Recovery** | Khôi phục quyền truy cập khi phương thức tin cậy bị mất hoặc không dùng được. | Dùng recovery code hoặc proofing có thẩm quyền để enroll lại. |
| **Device migration** | Chuyển cấu hình và dữ liệu được phép sang thiết bị mới. | Đăng nhập trên điện thoại mới và đăng ký passkey mới. |
| **Backup restore** | Phục hồi dữ liệu đã backup. | Khôi phục preference và tài liệu offline. |
| **Credential re-enrollment** | Tạo credential/authenticator mới sau khi xác minh. | Đăng ký TOTP seed hoặc device key mới. |

Backup restore không tự khôi phục trust. Một bản backup có thể chứa dữ liệu cũ, token đã revoke hoặc cấu hình không còn phù hợp. Server phải đánh giá trạng thái hiện tại trước khi cho phép credential được dùng.

## 2. Tài sản và trạng thái cần phục hồi

Trước khi thiết kế recovery, cần xác định những gì tồn tại trên thiết bị và ở backend.

### 2.1. Tài sản phía thiết bị

- Access token, refresh token và session state.
- Private key trong Keychain, Keystore hoặc hardware-backed storage.
- Passkey hoặc reference tới platform credential.
- TOTP seed, recovery code hoặc dữ liệu enrollment.
- Device registration, attestation state và certificate.
- Local database, file offline, cache và nội dung đã tải.
- Pending OAuth/OIDC transaction, state, nonce và PKCE verifier.
- Push notification registration token.
- Account/tenant selection và dữ liệu ứng dụng khác.

Không phải mọi tài sản đều nên được backup hoặc chuyển sang thiết bị mới. Refresh token, private key và device-bound credential cần policy riêng.

### 2.2. Trạng thái phía server

Backend có thể quản lý:
- Account status và identity mapping.
- Device inventory và trạng thái trusted/managed/lost/revoked.
- Session và refresh token family.
- Passkey/authenticator credential records.
- Certificate serial/fingerprint và revocation state.
- Recovery method và recovery code verifier.
- Recovery request, challenge, approval và thời hạn.
- Risk signals, incident flags và audit history.
- Tenant membership, role và authorization epoch.

Recovery phải cập nhật trạng thái server có thẩm quyền. Xóa token khỏi app không thu hồi token đã bị sao chép; xóa device record không nhất thiết revoke certificate hoặc refresh token liên quan.

## 3. Phân loại tình huống recovery

Không phải mọi tình huống mất quyền kiểm soát đều có cùng mức rủi ro.

| Tình huống | Rủi ro chính | Hướng xử lý |
| --- | --- | --- |
| **Đổi điện thoại có kiểm soát** | Chuyển credential hoặc token ngoài policy. | Xác thực trên thiết bị cũ hoặc recovery factor độc lập, enroll thiết bị mới, revoke thiết bị cũ sau xác nhận. |
| **Mất điện thoại** | Attacker có thể dùng session/refresh token còn active. | Báo mất, revoke session/token/device binding, kiểm tra hoạt động và recovery trên kênh khác. |
| **Điện thoại bị đánh cắp khi đang mở khóa** | Attacker có thể truy cập app hoặc dùng local session. | Containment khẩn cấp, revoke server-side, đổi credential bị ảnh hưởng và đánh giá dữ liệu đã truy cập. |
| **Cài lại ứng dụng** | Local key hoặc transaction bị mất; backend vẫn giữ session cũ. | Authentication lại, kiểm tra device registration và enroll lại nếu cần. |
| **Mất SIM/số điện thoại** | Không nhận SMS OTP hoặc nguy cơ SIM swap. | Dùng recovery method độc lập; không tự chuyển recovery sang số mới chỉ qua SMS. |
| **Mất passkey hoặc security key** | Mất một authenticator. | Dùng authenticator dự phòng/recovery proofing, revoke credential mất nếu có thể. |
| **Biometric thay đổi** | Key access control có thể bị invalidated. | Re-authentication và tạo key/enrollment mới theo policy. |
| **Account compromise** | Attacker có thể đã thay recovery method hoặc thêm authenticator. | Incident response, freeze thay đổi nhạy cảm, revoke session/grant/credential và proofing độc lập. |
| **Nhân viên rời tổ chức** | Thiết bị và credential công việc còn hoạt động. | Offboarding, MDM action, disable account và revoke credential/token. |

Một thao tác có thể cần nhiều bước. Ví dụ đổi điện thoại có kiểm soát có thể dùng thiết bị cũ để approve thiết bị mới; nhưng khi thiết bị cũ đã mất, phải chuyển sang recovery path khác có mức proofing phù hợp.

## 4. Mô hình bảo đảm cho recovery

Recovery là một lần thay đổi trust. Mức bằng chứng cần thiết phụ thuộc hậu quả nếu attacker chiếm được quy trình.

### 4.1. Recovery assurance

Đánh giá tối thiểu:
- Giá trị account và dữ liệu có thể truy cập.
- Quyền đặc quyền hoặc quyền quản trị.
- Credential đã mất có thể bị attacker sử dụng không.
- Recovery channel còn lại có độc lập với channel bị mất không.
- Có dấu hiệu phishing, SIM swap, malware hoặc account takeover không.
- Có thiết bị đã đăng ký khác đang hoạt động không.
- Thay đổi recovery có thể bị đảo ngược hoặc phát hiện không.
- Tổ chức có nguồn identity proofing có thẩm quyền không.

Với account thông thường, recovery code đã cấp trước có thể là một phương thức hợp lệ nếu được bảo vệ tốt. Với admin hoặc account có dữ liệu nhạy cảm, có thể cần phishing-resistant authenticator khác, approval độc lập hoặc quy trình proofing của tổ chức.

### 4.2. Không dùng cùng một kênh để yêu cầu và xác minh

Nếu người dùng mất SIM và yêu cầu chuyển số điện thoại recovery, gửi OTP tới chính số mới chỉ chứng minh họ kiểm soát số mới. Nó không chứng minh quyền sở hữu account hiện tại.

Tương tự:
- Email mới không tự xác minh account.
- Device ID do app mới tạo không chứng minh người dùng cũ.
- Biometric trên điện thoại mới không chứng minh account backend thuộc người đang cầm máy.
- Thông tin hồ sơ công khai không phải bằng chứng mạnh về identity.

Ưu tiên recovery factor đã đăng ký trước, device đang tin cậy còn kiểm soát, passkey dự phòng, recovery code hoặc proofing độc lập có thẩm quyền.

### 4.3. Risk-based recovery

Có thể kết hợp:
- Step-up từ authenticator còn hoạt động.
- Thiết bị đã đăng ký trước đó.
- Recovery code một lần.
- Email/phone đã xác minh từ trước.
- Manager/helpdesk approval theo quy trình.
- Identity proofing phù hợp với account type.
- Thời gian chờ và thông báo tới kênh cũ.
- Manual review khi có tín hiệu compromise.

Không cộng điểm cơ học cho nhiều bằng chứng yếu nếu chúng phụ thuộc cùng một nguồn. Ví dụ email và SMS đều có thể bị chiếm qua cùng một account telco hoặc mailbox. Độc lập về nguồn và khả năng kiểm soát quan trọng hơn số lượng yếu tố.

## 5. Recovery code và phương thức dự phòng

Recovery code là một credential dự phòng được cấp trước khi người dùng mất phương thức chính. Nó hữu ích khi không còn passkey hoặc MFA chính, nhưng phải được bảo vệ như một secret.

### 5.1. Cấp recovery code

Một quy trình tốt:
1. User xác thực bằng phương thức đủ mạnh.
2. Server tạo code ngẫu nhiên với entropy phù hợp.
3. Hiển thị code một lần và hướng dẫn lưu ở nơi an toàn.
4. Lưu verifier/hash phù hợp ở server, không lưu plaintext.
5. Ghi thời điểm cấp, account, batch/version và trạng thái.
6. Thông báo đã tạo bộ recovery code qua kênh phù hợp.
7. Khi cấp bộ mới, vô hiệu toàn bộ code cũ theo policy.

Không gửi recovery code qua email hoặc push notification như một bản sao lâu dài. Không ghi code vào log, analytics, clipboard history hoặc screenshot nếu có thể tránh.

### 5.2. Dùng recovery code

Khi người dùng sử dụng code:
- Xác định account và recovery transaction.
- Kiểm tra rate limit và attempt count.
- So sánh verifier an toàn.
- Đánh dấu code đã dùng atomically.
- Không cho hai request đồng thời dùng cùng code.
- Tạo recovery event và yêu cầu enroll phương thức mới.
- Thu hồi code đã dùng; nếu có dấu hiệu lộ batch, revoke toàn bộ batch.

Một code đã dùng không được dùng lại, kể cả request đầu tiên bị timeout sau khi server đã consume. Client cần kiểm tra recovery status hoặc tạo transaction mới theo hướng dẫn server.

### 5.3. Recovery code không phải recovery bypass vô hạn

Không cho phép dùng một code để bỏ qua mọi policy hoặc duy trì quyền admin vô hạn. Có thể giới hạn code vào một mục đích:
- Bắt đầu recovery.
- Đăng ký authenticator mới.
- Xác nhận một lần đăng nhập.
- Khôi phục một account cụ thể.

Sau recovery, yêu cầu người dùng tạo phương thức dự phòng mới và kiểm tra các session/device cũ.

## 6. Passkey recovery và đồng bộ credential

Passkey có thể được đồng bộ trong hệ sinh thái của platform hoặc gắn với authenticator/security key cụ thể. Recovery phụ thuộc loại credential và cơ chế khôi phục account của nhà cung cấp platform.

### 6.1. Synced passkeys

Một số passkey được đồng bộ qua account của platform và có thể xuất hiện trên thiết bị mới sau khi người dùng khôi phục account hệ sinh thái. RP có thể không biết chắc passkey đã được đồng bộ tới bao nhiêu thiết bị.

Cần:
- Giải thích cho user rằng khả năng sync phụ thuộc platform/account settings.
- Bảo vệ account dùng để đồng bộ passkey bằng phương thức mạnh.
- Không coi việc passkey xuất hiện trên máy mới là bằng chứng duy nhất cho recovery account nhạy cảm.
- Cho phép user xem danh sách credential RP đã đăng ký và revoke khi cần.
- Yêu cầu step-up cho thao tác thay đổi recovery hoặc quyền.

### 6.2. Device-bound passkeys và security keys

Credential gắn với một authenticator cụ thể có thể không chuyển được sang thiết bị mới. Nếu thiết bị/key mất:
- Dùng passkey hoặc security key dự phòng đã đăng ký.
- Dùng recovery code hoặc recovery proofing theo policy.
- Revoke credential bị mất khi có thể xác định.
- Đăng ký credential mới sau khi xác minh account.
- Kiểm tra credential cuối cùng để tránh khóa account.

Không giả định mọi passkey là exportable hoặc có thể backup. RP cần có recovery strategy độc lập với một thiết bị duy nhất.

### 6.3. Không link account chỉ dựa trên email

Khi khôi phục passkey qua platform account hoặc IdP, không tự động liên kết account nội bộ chỉ vì email giống nhau. Dùng issuer-subject đã xác minh và yêu cầu proof of control account đích. Nếu có account collision, giữ trạng thái pending và yêu cầu review thay vì tự merge.

## 7. TOTP, push và recovery khi mất authenticator

Mất điện thoại có thể đồng nghĩa mất TOTP app hoặc push authenticator. Cần xử lý riêng từng loại.

### 7.1. TOTP

TOTP seed là bí mật dài hạn; mã OTP chỉ có hiệu lực trong một time step ngắn. Nếu thiết bị chứa seed bị mất:
- Revoke seed/credential cũ theo account policy.
- Không chỉ chờ mã OTP hiện tại hết hạn.
- Recovery bằng phương thức dự phòng đã đăng ký hoặc proofing độc lập.
- Enroll seed mới qua provisioning an toàn.
- Xác minh một mã mới trước khi kích hoạt.
- Thu hồi recovery code cũ nếu đã được dùng.

Không yêu cầu người dùng gửi QR enrollment secret hoặc TOTP seed cho helpdesk.

### 7.2. Push authenticator

Nếu mất thiết bị nhận push:
- Hủy device registration/push binding cũ.
- Thu hồi session/token liên quan.
- Đăng ký thiết bị mới qua authentication/recovery đủ mạnh.
- Kiểm tra push approval bất thường trước và sau thời điểm mất.
- Không gửi challenge approval tới thiết bị mới trước khi hoàn tất enrollment.

Push token của dịch vụ notification không phải credential xác thực độc lập. Cần server-side challenge và xác minh user intent.

### 7.3. SMS và SIM swap

Số điện thoại có thể được chuyển sang SIM/eSIM khác, tái cấp hoặc bị chiếm qua social engineering với nhà mạng. SMS OTP không nên là recovery proof duy nhất cho account có giá trị cao.

Nếu nghi SIM swap:
- Tạm ngừng recovery qua SMS.
- Dùng kênh độc lập đã đăng ký.
- Liên hệ nhà mạng qua kênh chính thức nếu phù hợp.
- Kiểm tra thay đổi số điện thoại và recovery method.
- Thu hồi session/token nếu có dấu hiệu takeover.
- Không cập nhật số mới chỉ dựa trên OTP gửi tới số đó.

## 8. Mất thiết bị: containment trước, recovery sau

Khi thiết bị bị mất hoặc bị đánh cắp, ưu tiên hạn chế khả năng attacker tiếp tục sử dụng credential còn hoạt động. Recovery account và containment có thể diễn ra song song nhưng phải có trạng thái rõ.

### 8.1. Các bước containment

1. Ghi nhận thời điểm mất, thiết bị, account và phạm vi dữ liệu.
2. Đánh dấu device record là lost/suspected compromised.
3. Revoke refresh token family, application session và device-bound credential theo policy.
4. Thu hồi certificate hoặc key registration nếu có.
5. Đánh giá access token đã phát hành; dùng introspection, state check hoặc lifetime giới hạn để thu hẹp cửa sổ.
6. Chặn push approval tới thiết bị cũ.
7. Kiểm tra login, token exchange, account modification và recovery events bất thường.
8. Thông báo qua kênh độc lập đã xác minh.
9. Nếu có dữ liệu công ty, kích hoạt MDM/incident response phù hợp.

Không dựa vào remote wipe là biện pháp duy nhất. Thiết bị có thể offline, bị tắt hoặc không nhận lệnh. Revoke server-side phải được thực hiện ngay khi có thẩm quyền.

### 8.2. Access token đã phát hành

Revoke refresh token không nhất thiết làm mọi access token JWT đã phát hành mất hiệu lực tức thì. Resource server có thể tiếp tục xác minh offline tới exp nếu không có trạng thái bổ sung.

Cần biết:
- Access token lifetime.
- Có introspection hoặc denylist không.
- Có account/session version không.
- Resource nào kiểm tra trạng thái online.
- Thời gian propagation tới gateway và API.
- Token có sender constraint không.

Với action nhạy cảm, dùng state check hoặc revocation mechanism phù hợp. Không hứa rằng mọi request sẽ bị chặn ngay nếu kiến trúc không bảo đảm điều đó.

## 9. Đổi điện thoại có kiểm soát

Khi người dùng còn giữ thiết bị cũ, có thể dùng nó để xác nhận thiết bị mới. Đây thường là luồng thuận tiện hơn recovery sau mất thiết bị, nhưng vẫn cần ràng buộc transaction.

### 9.1. Quy trình device migration

1. User đăng nhập trên thiết bị mới qua OIDC/native flow hoặc authentication hiện có.
2. Server tạo pending device enrollment với challenge và transaction ID.
3. Thiết bị cũ nhận thông báo hoặc yêu cầu approval.
4. User xem thông tin thiết bị mới, thời điểm, vị trí khái quát và mục đích.
5. Thiết bị cũ xác nhận bằng authenticator phù hợp.
6. Thiết bị mới tạo key pair trong Keychain/Keystore hoặc enroll passkey.
7. Server xác minh proof of possession/attestation theo policy.
8. Thiết bị mới được đánh dấu active sau khi hoàn tất.
9. User chọn giữ hoặc revoke thiết bị cũ; policy có thể tự revoke sau thời gian overlap.
10. Ghi audit và thông báo tới kênh đã xác minh.

### 9.2. Không approve mù

Không hiển thị nút “Approve new device” mà không có context. Người dùng cần thấy:
- Tên/loại thiết bị ở mức đáng tin.
- App và account đang được liên kết.
- Thời gian và transaction reference.
- Thông tin môi trường hoặc vị trí khái quát nếu có.
- Hành động sẽ cấp quyền gì.
- Cách từ chối hoặc báo cáo yêu cầu không mong muốn.

Approval phải gắn với đúng challenge và thiết bị; không dùng một push approval chung có thể replay cho enrollment khác.

### 9.3. Overlap và thu hồi thiết bị cũ

Có thể giữ hai thiết bị active trong khoảng chuyển đổi ngắn nếu policy cho phép. Cần giới hạn:
- Thời điểm bắt đầu/kết thúc.
- Quyền và resource được phép.
- Credential nào được dùng.
- Cách xử lý khi enrollment mới thất bại.
- Điều kiện revoke thiết bị cũ.
- Cảnh báo nếu thiết bị cũ tiếp tục hoạt động sau migration.

Với thiết bị bị mất hoặc compromise, không dùng overlap thông thường; containment cần revoke sớm.

## 10. Cài lại ứng dụng, backup và restore

Ứng dụng được cài lại có thể mất local storage, nhưng server có thể vẫn giữ session hoặc device registration. Backup có thể phục hồi dữ liệu không còn được tin cậy.

### 10.1. Phân loại dữ liệu backup

| Dữ liệu | Hướng xử lý tham khảo |
| --- | --- |
| Theme, locale, preference | Có thể backup nếu không nhạy cảm. |
| Cache nội dung công khai | Có thể backup theo policy. |
| Dữ liệu offline cá nhân | Mã hóa, giới hạn retention và kiểm tra account sau restore. |
| Access token | Thường không cần backup; có thể lấy mới sau authentication. |
| Refresh token | Loại khỏi backup/migration trừ khi có thiết kế và platform protection rõ. |
| Private key device-bound | Không export/backup nếu policy yêu cầu gắn với thiết bị. |
| Pending PKCE verifier/state | Không khôi phục transaction cũ như một login mới; hết TTL thì hủy. |
| TOTP seed/recovery code | Không đưa vào backup ứng dụng thông thường. |

### 10.2. Restore không khôi phục session tự động

Sau restore:
- Kiểm tra account status và device registration.
- Xác định key có tồn tại và còn được OS bảo vệ không.
- Xác minh token nếu có; không tin cache client.
- Re-authenticate nếu device binding hoặc token không còn hợp lệ.
- Enroll key/passkey mới nếu credential cũ không chuyển được.
- Xóa pending transaction hết hạn.
- Không khôi phục session đã revoke.

### 10.3. Mã hóa dữ liệu local

Dữ liệu offline nhạy cảm nên được mã hóa bằng key được giữ trong secure storage. Cần tính đến:
- Key invalidation khi biometric/passcode thay đổi.
- Backup/restore và key availability.
- Xóa account và xóa dữ liệu local.
- File cache, thumbnail, database journal và temporary file.
- Screenshot/app switcher snapshot.
- Log và crash report.

Xóa một record trong database không đảm bảo mọi bản sao trong cache, backup hoặc filesystem đã biến mất. Cần data lifecycle và retention policy rõ.

## 11. Recovery qua helpdesk và identity proofing

Khi người dùng mất mọi authenticator, có thể cần quy trình hỗ trợ. Đây là đường có rủi ro cao vì con người và quy trình vận hành có thể bị social engineering.

### 11.1. Helpdesk không nên dựa vào dữ liệu dễ biết

Không dùng riêng:
- Họ tên, ngày sinh hoặc địa chỉ.
- Số nhân viên có thể tìm thấy.
- Email/số điện thoại do requester vừa cung cấp.
- Ảnh chụp màn hình app hoặc thiết bị.
- Thông tin từ mạng xã hội.
- Caller ID hoặc tên hiển thị cuộc gọi.

Những dữ liệu này có thể bị lộ, giả mạo hoặc tái sử dụng. Cần proofing phù hợp với loại account và policy tổ chức.

### 11.2. Quy trình hỗ trợ an toàn

- Xác định account và yêu cầu qua kênh hỗ trợ chính thức.
- Kiểm tra trạng thái account, tenant, incident và recovery history.
- Dùng phương thức proofing độc lập được phê duyệt.
- Tách requester, verifier và approver cho account đặc quyền.
- Ghi ticket, reason code và evidence reference; không ghi secret.
- Đặt pending recovery với TTL và giới hạn hành động.
- Thông báo tới kênh cũ đã xác minh nếu còn khả dụng.
- Sau approval, cho phép enrollment authenticator mới theo transaction.
- Revoke credential/session cũ và kiểm tra downstream token.
- Audit mọi thao tác admin và cung cấp kênh khiếu nại.

Helpdesk không được yêu cầu user đọc password, OTP, recovery code hoặc private key. Không gửi temporary password qua email thường hoặc chat không xác thực.

### 11.3. Dual control và delay

Với account admin, tài khoản tài chính hoặc dữ liệu nhạy cảm, có thể yêu cầu hai người độc lập phê duyệt. Delay có thể tạo thời gian để chủ account phát hiện recovery trái phép. Tuy nhiên delay không thay proofing và không phù hợp khi cần containment khẩn cấp.

Policy cần định nghĩa:
- Hành động nào cần dual control.
- Approver nào có thẩm quyền.
- Thời gian chờ và điều kiện hủy.
- Cách xử lý khi có incident flag.
- Thông báo và escalation.
- Audit và review sau recovery.

## 12. Recovery state machine

Recovery request nên có trạng thái tường minh. Client không được tự chuyển request sang trạng thái approved hoặc completed.

| Trạng thái | Ý nghĩa | Chuyển tiếp hợp lệ |
| --- | --- | --- |
| **initiated** | Người dùng bắt đầu recovery. | verifying hoặc cancelled. |
| **verifying** | Kiểm tra account, evidence và risk. | pending_approval, approved hoặc rejected. |
| **pending_approval** | Chờ approver có thẩm quyền. | approved, rejected hoặc expired. |
| **approved** | Evidence và policy đạt yêu cầu. | enrollment_pending hoặc completed. |
| **enrollment_pending** | User đang đăng ký authenticator mới. | completed, failed hoặc expired. |
| **completed** | Credential mới đã kích hoạt, trạng thái cũ được xử lý. | Request mới nếu cần. |
| **rejected** | Recovery không đạt policy. | Request mới với bằng chứng hợp lệ. |
| **expired** | Challenge/approval hết TTL. | Tạo request mới. |
| **cancelled** | Request được hủy trước khi hoàn tất. | Tạo request mới. |
| **failed** | Lỗi kỹ thuật hoặc enrollment thất bại. | Retry có giới hạn hoặc request mới. |

Mỗi transition cần actor, timestamp, reason, request ID và điều kiện. Challenge và approval nên dùng một lần, gắn với account/device/action cụ thể.

### 12.1. Ràng buộc transaction

Recovery challenge cần gắn với:
- Account ID ổn định.
- Request ID và trạng thái hiện tại.
- Thiết bị mới hoặc credential mới.
- Action được phép thực hiện.
- TTL, nonce và one-time consumption.
- Approval snapshot nếu có.
- Policy version và risk result.

Nếu người dùng thay đổi target device hoặc credential sau approval, phải xác minh/duyệt lại. Không dùng approval cho một thiết bị để enroll thiết bị khác.

### 12.2. Idempotency và concurrency

Nhiều request recovery có thể đến đồng thời do retry, nhiều tab hoặc helpdesk và user cùng thao tác. Dùng idempotency key, version/ETag và transaction để tránh:
- Một recovery code được tiêu thụ hai lần.
- Hai thiết bị cùng được thêm ngoài ý muốn.
- Request cũ ghi đè trạng thái mới.
- Approval được replay.
- Refresh token được cấp lại sau khi revoke.
- Account bị mở lại khi incident vẫn đang active.

## 13. Sau recovery: rotate, revoke và kiểm tra account

Recovery hoàn tất không chỉ là “đăng nhập lại được”. Cần đánh giá credential và session cũ có còn đáng tin không.

### 13.1. Credential rotation

Tùy sự cố:
- Enroll passkey mới và revoke credential mất.
- Cấp TOTP seed mới, revoke seed cũ.
- Tạo recovery code batch mới và consume/revoke batch cũ.
- Cấp device certificate mới và revoke certificate cũ.
- Tạo device key mới và gỡ public key cũ.
- Đổi password nếu có nguy cơ lộ.
- Cập nhật push/device registration.

Không rotate mọi credential một cách máy móc nếu không có rủi ro hoặc yêu cầu; nhưng phải xác định rõ credential nào bị ảnh hưởng và vì sao được giữ lại.

### 13.2. Session và token revocation

Thu hồi:
- Browser/application sessions liên quan.
- Refresh token family.
- OAuth grants nếu có dấu hiệu bị cấp trái phép.
- Device binding và certificate.
- Access token theo cơ chế revoke/introspection/state check hoặc lifetime.
- Session ở các service downstream khi policy yêu cầu.

Nếu API xác minh JWT offline, token đã phát hành có thể còn được chấp nhận đến expiry. Cần biết propagation và giới hạn của kiến trúc; không tuyên bố revoke tức thì nếu resource server chưa nhận trạng thái.

### 13.3. Kiểm tra thay đổi trái phép

Sau recovery, rà soát:
- Email/phone/login identifier.
- Recovery methods.
- Passkey, TOTP, security key và certificate.
- OAuth app consent và linked IdP.
- Role, group, tenant membership.
- Session/device inventory.
- API key hoặc credential được tạo gần đây.
- Login, token exchange và giao dịch sau thời điểm compromise.

Nếu phát hiện thay đổi trái phép, mở incident và xử lý cả dữ liệu đã truy cập, không chỉ reset credential.

## 14. Enterprise mobile recovery và MDM

Trong môi trường doanh nghiệp, thiết bị có thể được quản lý bởi Mobile Device Management (MDM) hoặc Enterprise Mobility Management (EMM). Recovery cần phối hợp identity lifecycle với device lifecycle.

### 14.1. Thiết bị công việc bị mất

Tổ chức có thể:
- Đánh dấu thiết bị lost trong MDM.
- Khóa hoặc wipe thiết bị theo policy và quyền quản lý.
- Revoke certificate/device identity.
- Disable managed app hoặc work profile.
- Thu hồi session/token và account access.
- Kiểm tra dữ liệu doanh nghiệp đã đồng bộ.
- Cấp thiết bị thay thế và enroll lại.

Remote wipe có thể xóa dữ liệu cá nhân ngoài ý muốn nếu thiết bị không được phân vùng đúng. Phải dùng cơ chế quản lý phù hợp ownership và policy.

### 14.2. Work profile và BYOD

Với Bring Your Own Device (BYOD), tổ chức có thể chỉ quản lý work profile/container. Recovery cần phân biệt dữ liệu cá nhân và dữ liệu doanh nghiệp:
- Thu hồi work credential và app session.
- Xóa hoặc retire dữ liệu doanh nghiệp theo policy.
- Không tự ý xóa dữ liệu cá nhân ngoài phạm vi được phép.
- Cấp lại device certificate và app configuration.
- Kiểm tra consent, privacy notice và audit.

### 14.3. Offboarding

Khi nhân viên rời tổ chức:
- Disable identity/account theo nguồn có thẩm quyền.
- Revoke mobile sessions, refresh tokens, certificates và device bindings.
- Xóa managed account/work profile theo policy.
- Thu hồi quyền cloud/API và app grants.
- Kiểm tra thiết bị đã trả lại hoặc được retire.
- Giữ audit evidence theo retention.
- Không chỉ dựa vào việc xóa ứng dụng khỏi điện thoại.

## 15. Threat model cho mobile recovery

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Recovery channel takeover** | Attacker chiếm email/SIM rồi yêu cầu reset. | Chiếm account qua đường recovery. | Kênh độc lập, proofing, delay và notification tới channel cũ. |
| **SIM swap** | Nhà mạng bị social engineering để chuyển số. | Attacker nhận SMS OTP/recovery. | Không dùng SMS làm proof duy nhất; xác minh độc lập. |
| **Helpdesk social engineering** | Attacker giả danh nhân viên để yêu cầu reset MFA. | Bypass authenticator. | Proofing, ticket, dual control và audit. |
| **Recovery code theft** | Code lưu trong ảnh, email hoặc cloud note bị lộ. | Attacker dùng code lấy account. | Hiển thị một lần, hash verifier, one-time consume và revoke batch. |
| **Device loss with active token** | Thiết bị mất vẫn giữ refresh token/session. | Attacker duy trì truy cập. | Server-side revoke, device inventory và short lifetime. |
| **Stale JWT after revoke** | API xác minh token offline. | Access token cũ còn hiệu lực. | Introspection/state check, version hoặc TTL phù hợp. |
| **Passkey sync account compromise** | Account platform dùng để sync passkey bị chiếm. | Attacker có thể khôi phục credential đồng bộ. | Bảo vệ account platform, RP recovery controls và credential review. |
| **Callback/recovery replay** | Challenge hoặc approval cũ được dùng lại. | Enroll credential không được duyệt. | TTL, nonce, one-time consume và transaction binding. |
| **Device enrollment injection** | Thêm thiết bị mới mà không có approval đúng. | Attacker tạo đường truy cập bền vững. | Proof of control, device context, approval và audit. |
| **Biometric fallback downgrade** | Recovery chuyển sang fallback yếu hơn. | Giảm assurance của account. | Minimum assurance policy và review. |
| **Backup credential resurrection** | Restore đưa token/secret cũ trở lại. | Credential đã revoke được dùng lại. | Exclude secret, re-authentication và server state check. |
| **Account linking confusion** | Tự link identity mới theo email trùng. | Link nhầm hoặc takeover. | Issuer-subject mapping và proof of control account đích. |
| **Recovery race** | Nhiều transaction cùng thay đổi account. | Trạng thái credential/session không nhất quán. | State machine, version, idempotency và atomic update. |
| **False device trust** | Tin device ID hoặc attestation boolean từ client. | Thiết bị giả được chấp nhận. | Server-side attestation verification và challenge freshness. |

## 16. Tình huống thực hành: mất điện thoại và mất luôn SIM

**Bối cảnh:** Nhân viên Huy dùng ứng dụng nội bộ trên điện thoại Android. App giữ refresh token trong Android Keystore-backed storage, push authenticator và một device key. Huy làm mất điện thoại cùng SIM. Một người lạ có thể cầm thiết bị khi màn hình chưa khóa. Huy vẫn truy cập được email công ty từ laptop đã đăng ký.

**Phân tích:**

1. Không thể dùng SMS tới số cũ làm recovery proof vì SIM đã mất và có thể bị chuyển sang thiết bị khác.
2. Email công ty trên laptop có thể là một kênh, nhưng cần xác minh session/device đó vẫn đáng tin và không bị compromise.
3. Refresh token có thể tiếp tục hoạt động dù app trên điện thoại không còn được chủ account kiểm soát.
4. Local biometric/Keystore protection giảm một số rủi ro nhưng không bảo đảm thiết bị bị mất không thể sử dụng.
5. Device ID không đủ để nhận diện chính xác credential cần revoke.

**Quy trình xử lý:**

- Huy báo mất qua cổng hỗ trợ chính thức từ laptop hoặc kênh đã xác minh.
- Security team xác minh account và trạng thái thiết bị, đánh dấu thiết bị lost.
- Backend revoke refresh token family, app session và device binding; thu hồi certificate/key registration nếu có.
- Chặn push approval tới thiết bị cũ và tạm ngừng recovery qua SMS.
- Kiểm tra login history, token exchange, recovery method và account modification từ thời điểm mất.
- Huy hoàn tất proofing qua phương thức độc lập được tổ chức phê duyệt.
- Thiết bị mới được enroll bằng key pair mới; app nhận token mới sau authentication.
- Cấp lại SIM qua nhà mạng không tự động mở lại recovery; số mới phải được xác minh và cập nhật qua transaction riêng.
- Gửi notification tới kênh đã tin cậy, giữ audit reference và kiểm tra token/access window còn lại.

**Câu hỏi:** Nếu Huy đăng nhập được trên laptop, có nên lập tức thêm số điện thoại mới và passkey mới không? Không tự động. Laptop session phải được đánh giá về freshness và trust; thao tác recovery cần step-up/approval phù hợp, xác minh giá trị mới và xử lý credential trên điện thoại bị mất.

## 17. Checklist thiết kế mobile recovery

- [ ] Phân loại tình huống: đổi thiết bị, mất thiết bị, reinstall, mất authenticator, compromise hay offboarding.
- [ ] Inventory credential, session, device binding, certificate, recovery method và dữ liệu local.
- [ ] Đánh giá recovery assurance theo giá trị account, quyền và dấu hiệu compromise.
- [ ] Dùng recovery factor đã đăng ký trước hoặc proofing độc lập; không tự xác minh bằng kênh mới.
- [ ] Không dùng SMS/SIM hoặc thông tin hồ sơ công khai làm proof duy nhất cho account nhạy cảm.
- [ ] Cấp recovery code entropy cao, chỉ hiển thị một lần, lưu verifier và consume atomically.
- [ ] Khi cấp batch recovery code mới, revoke batch cũ theo policy.
- [ ] Có phương thức authenticator dự phòng và tránh khóa account khi xóa credential cuối cùng.
- [ ] Hiểu khác biệt synced passkey và device-bound credential; không giả định mọi passkey chuyển được.
- [ ] Ràng buộc device enrollment với challenge, transaction, account và approval cụ thể.
- [ ] Khi mất thiết bị, ưu tiên containment: revoke session/token/device key/certificate và push binding.
- [ ] Hiểu access token JWT có thể còn hiệu lực sau refresh token revoke; xác định state/revocation window.
- [ ] Không backup refresh token, private key, TOTP seed hoặc pending transaction ngoài policy.
- [ ] Sau restore, kiểm tra account/device state và re-authenticate hoặc re-enroll khi cần.
- [ ] Helpdesk dùng proofing, ticket, separation of duties và dual control cho account rủi ro cao.
- [ ] Có recovery state machine với TTL, one-time challenge, approval snapshot và idempotency.
- [ ] Sau recovery, rà soát authenticator, recovery method, OAuth grants, role, session và hoạt động bất thường.
- [ ] Phối hợp MDM/EMM cho thiết bị công việc, BYOD, wipe và offboarding.
- [ ] Thông báo qua kênh cũ đã xác minh; cung cấp cách phản đối recovery không được yêu cầu.
- [ ] Audit actor, target, evidence reference, policy, decision và kết quả; không log secret.
- [ ] Kiểm thử SIM swap, helpdesk social engineering, recovery replay, token resurrection, race và device loss.

## 18. Câu hỏi tự kiểm tra

**1. Mobile recovery là gì?**  
Là quy trình khôi phục quyền truy cập và trust khi người dùng mất thiết bị, authenticator, session hoặc nghi credential đã bị lộ.

**2. Recovery khác login như thế nào?**  
Login dùng credential đang hoạt động; recovery thay thế hoặc thiết lập lại đường xác thực khi phương thức cũ không còn dùng được, vì vậy cần proofing và kiểm soát riêng.

**3. Vì sao OTP gửi tới số điện thoại mới không đủ để khôi phục account?**  
Nó chỉ chứng minh quyền truy cập số mới, không chứng minh quyền kiểm soát account hiện tại.

**4. Recovery code cần có đặc tính gì?**  
Entropy cao, cấp an toàn, hiển thị một lần, lưu verifier/hash, consume atomically và không dùng lại.

**5. Synced passkey có nghĩa RP biết mọi thiết bị đang chứa credential không?**  
Không. RP thường không có cái nhìn đầy đủ về mọi thiết bị nhận passkey đồng bộ; cần credential management và recovery controls riêng.

**6. Mất điện thoại có cần revoke refresh token không?**  
Có, khi thiết bị/token có thể bị người khác sử dụng. Cần revoke token family và session/device binding theo phạm vi.

**7. Revoke refresh token có chắc access token JWT cũ mất hiệu lực ngay không?**  
Không. Resource server có thể tiếp tục chấp nhận JWT tới exp nếu không có introspection, state check hoặc revocation mechanism.

**8. Biometric trên điện thoại mới có chứng minh chủ account không?**  
Không. Nó xác minh user cục bộ trên thiết bị theo OS policy; account recovery vẫn cần bằng chứng độc lập.

**9. Vì sao helpdesk recovery cần dual control?**  
Vì nhân viên hỗ trợ có thể bị social engineering; tách requester, verifier và approver giảm khả năng một người tự bypass quy trình.

**10. Sau recovery cần kiểm tra gì?**  
Credential/authenticator mới và cũ, session/token, device binding, recovery method, OAuth grants, role/tenant changes và hoạt động từ thời điểm compromise.

**Ghi nhớ:** Mobile recovery là một thay đổi trust có rủi ro cao. Hãy xác minh bằng chứng độc lập, không dùng kênh mới tự chứng minh chính nó, containment thiết bị mất bằng revoke server-side, cấp lại authenticator theo transaction có ràng buộc và kiểm tra token/session cũ. Backup hoặc biometric local không tự khôi phục quyền truy cập server; trạng thái account và policy phía backend mới quyết định recovery đã an toàn hay chưa.
