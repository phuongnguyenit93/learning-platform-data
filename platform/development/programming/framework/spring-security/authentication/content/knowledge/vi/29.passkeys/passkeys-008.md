# Mất thiết bị, thu hồi passkey credential và khôi phục tài khoản mà không tạo đường yếu hơn

## 1. Mục tiêu học tập và tình huống

Passkey là thông tin xác thực sử dụng **WebAuthn/FIDO2**, trong đó authenticator giữ private key và Relying Party (RP, ứng dụng) lưu public key cùng credential ID. Người dùng xác minh trên thiết bị bằng PIN, sinh trắc học hoặc cơ chế user verification (UV) phù hợp. WebAuthn ký một challenge gắn với RP ID/origin, giúp chống nhiều hình thức phishing và password reuse.

Khi người dùng báo **mất điện thoại, mất security key, bị đánh cắp laptop hoặc mất quyền truy cập passkey provider**, câu hỏi quan trọng không chỉ là “làm sao đăng nhập lại?” mà còn là:

- Credential còn trên thiết bị bị mất có thể được dùng hay không?
- Có bản passkey được đồng bộ trên thiết bị khác không?
- Credential nào phải bị thu hồi ở RP? Người dùng còn passkey độc lập nào không?
- Những HTTP session, refresh token hoặc API token đã phát hành trước đó có còn hiệu lực?
- Quy trình hỗ trợ có vô tình cho phép **email/SMS/nhân viên helpdesk** bỏ qua bảo vệ WebAuthn và chiếm tài khoản không?
- Làm sao kiểm chứng việc recovery đã trả quyền kiểm soát tài khoản về đúng chủ thể?

Mục tiêu của bài:

1. Phân biệt **device-bound passkey** và **synced passkey**, trạng thái backup (`BE`/`BS`) và giới hạn nhận biết từng thiết bị từ phía RP.
2. Hiểu thao tác **xóa liên kết credential ID/public key khỏi tài khoản** tại RP; phân biệt nó với xóa passkey khỏi thiết bị và thu hồi session/token.
3. Xây dựng runbook khi **mất thiết bị**, khi **nghi bị chiếm tài khoản**, và khi **mất mọi authenticator**.
4. Thiết kế **recovery có mức bảo đảm tương xứng với giá trị tài khoản**, dùng passkey dự phòng/đã đăng ký, recovery codes được bảo vệ, hoặc identity proofing có kiểm soát.
5. Dùng đúng các API Spring Security WebAuthn (`UserCredentialRepository`, `PublicKeyCredentialUserEntityRepository`, `WebAuthnRegistrationFilter`) và phân quyền cho thao tác thêm/xóa credential.
6. Kiểm thử credential revocation, chống chiếm đoạt qua helpdesk, session invalidation và race condition với các tình huống đa thiết bị, đa node.

Phạm vi: **ứng dụng Spring Security Servlet/WebAuthn**, ví dụ API cụ thể lấy Spring Security 6.5.11 làm baseline; một số package/dependency khác ở Spring Security 7.x. Bài bao gồm Java 17 và một chương trình mô phỏng có thể biên dịch chỉ bằng JDK. Không đồng nhất với **mTLS client certificates**, **OAuth access-token revocation**, hoặc **password reset**.

## 2. Mô hình WebAuthn: RP thật sự lưu và có quyền thu hồi cái gì?

### 2.1. Đăng ký (registration)

Khi tạo passkey, browser gọi WebAuthn `navigator.credentials.create(...)` bằng challenge/creation options của RP. Authenticator tạo cặp khóa phù hợp RP ID. Private key được giữ theo cơ chế của authenticator/passkey provider; RP nhận **credential ID, public key và metadata** đã được xác minh qua registration ceremony.

```text
Người dùng                 Browser / platform              RP backend
   |                              |                              |
   | Yêu cầu thêm passkey          |                              |
   |----------------------------->| POST /webauthn/register/options
   |                              |----------------------------->|
   |                              |<----- challenge, RP ID, ...-|
   | Xác minh bằng device unlock  |                              |
   |<---- navigator.credentials.create() ------------------------|
   |                              | POST attestation result      |
   |                              |----------------------------->|
   |                              |         RP kiểm tra challenge,
   |                              |         origin, RP ID, cấu trúc
   |                              |         rồi lưu credential
   |                              |<------------ 200/4xx --------|
```

Server-side credential record thường bao gồm:

| Trường | Vai trò | Lưu ý khi thu hồi |
| --- | --- | --- |
| `credentialId` | Định danh credential do authenticator tạo | Khóa tìm credential cần từ chối/xóa; **không phải** số serial thiết bị |
| `userHandle / user entity ID` | Khóa liên kết credential với user tại RP | Không lấy username/email do client gửi để định nghĩa lại owner |
| `publicKey` (COSE key) | Xác minh chữ ký assertion về sau | Xóa record khiến RP không còn khóa tin cậy để chấp nhận credential đó |
| `created`, `lastUsed`, user-visible `label` | Quản lý/quan sát credential | Label người dùng đặt có thể sai, không dùng làm bằng chứng sở hữu |
| `signCount` | Theo dõi signature counter khi có ý nghĩa | Với syncable credentials counter có thể bằng 0; **không** kết luận máy không bị clone từ counter=0 |
| `backupEligible` (`BE`) | Authenticator báo credential có thể được backup/sync | Chỉ là tín hiệu từ authenticator; không cho biết passkey có trên bao nhiêu thiết bị |
| `backupState` (`BS`) | Authenticator báo credential đang backed up | Có thể đổi theo thời gian; không thay thế trạng thái thiết bị thực tế |
| `transports`, AAGUID/metadata nếu lưu | Hỗ trợ lựa chọn UX/chính sách | Không dùng label hoặc transport làm yếu tố xác thực người dùng |

**WebAuthn lưu theo credential, không phải đơn vị vật lý “điện thoại A”.** Một synced passkey có thể có cùng credential ID/private key được passkey provider đồng bộ qua nhiều thiết bị. RP thường **không thể** nhìn một credential record và suy ra chính xác bao nhiêu bản sao đang tồn tại.

### 2.2. Đăng nhập (assertion)

Browser lấy authentication options rồi gọi `navigator.credentials.get(...)`. Authenticator ký challenge bằng private key của passkey. RP kiểm tra chữ ký với public key đã đăng ký, đồng thời xác minh challenge, origin, RP ID, flags UP/UV và các điều kiện bảo mật phù hợp.

```text
RP tạo challenge ngẫu nhiên / thời hạn
            |
            v
Browser + authenticator xác nhận người dùng, ký challenge
            |
            v
RP tra credential ID -> public key và owner
            |
            +-- credential không tồn tại/bị thu hồi -> TỪ CHỐI
            |
            +-- signature, challenge, origin, RP ID sai -> TỪ CHỐI
            |
            +-- hợp lệ -> Authentication, sau đó authorization/session
```

Nếu RP đã xóa credential record hoặc đánh dấu credential là revoked và **mọi node** cùng dùng trạng thái tin cậy đó, một assertion mới dựa trên credential ấy phải bị từ chối. Tuy nhiên **session đã tạo trước lúc xóa credential vẫn có thể sống** nếu hệ thống không chủ động hủy session. Điều này phải được giải quyết riêng trong sự cố mất thiết bị.

## 3. “Mất thiết bị” không luôn đồng nghĩa “mất tất cả passkey”

Trước khi chọn hành động, phân loại tình huống:

| Trường hợp | Passkey có thể còn dùng trên thiết bị khác? | Mức rủi ro chính | Hướng xử lý |
| --- | --- | --- | --- |
| Mất **security key vật lý** chứa device-bound passkey | Không có bản copy của chính credential đó; có thể có credential dự phòng khác | Thiết bị bị lấy và attacker biết PIN/UV, hoặc user bị lockout | Dùng passkey dự phòng; thu hồi credential trên key thất lạc, thay key |
| Mất điện thoại có **synced passkey**, provider account vẫn an toàn | Có thể có trên laptop/điện thoại khác đã đăng nhập provider | Thiết bị bị mất có thể vẫn đăng nhập nếu được mở khóa; sync-provider account có thể là mục tiêu | Khóa/xóa thiết bị từ xa theo nhà cung cấp; đánh giá compromise; thu hồi credential ở RP nếu có nguy cơ |
| Thiết bị bị phá hỏng hoàn toàn, private key device-bound không khôi phục | Không, trừ khi có passkey độc lập | Mất khả năng truy cập nhưng chưa nhất thiết có compromise | Dùng authenticator dự phòng hoặc recovery theo policy |
| Mất quyền vào **passkey provider / cloud sync account** | Có thể không bootstrap được thiết bị mới | Quy trình recovery của provider hoặc kẻ chiếm provider account | Ưu tiên passkey dự phòng ở trust domain khác; đánh giá nguy cơ provider bị chiếm |
| Thiết bị nghi có malware, bị lấy cắp cả unlock code | Một credential sync có thể xuất hiện trên nhiều thiết bị | Không biết attacker có khả năng ký assertion hoặc dùng session hiện có | Tạm khóa/thu hồi credentials đáng ngờ, hủy sessions, rà soát account changes |
| Người dùng tự xóa passkey trong settings provider | Tùy hệ sinh thái và sync | RP có thể còn record nhưng private key không còn | Đăng ký credential mới qua xác thực an toàn, rồi xóa record mồ côi |

**Mất thiết bị chưa chắc đồng nghĩa private key bị trích xuất.** Passkey thường có cơ chế bảo vệ khóa. Nhưng khi nhận báo mất cắp, chính sách phải xét khả năng attacker chiếm **phiên đăng nhập đang mở**, mở khóa thiết bị, hoặc lợi dụng phương thức recovery của passkey provider; không mặc nhiên “an toàn tuyệt đối vì có sinh trắc học”.

### 3.1. Device-bound và synced: ưu/nhược điểm liên quan recovery

- **Device-bound**: khóa bị ràng buộc với authenticator, ví dụ FIDO security key không hỗ trợ export. Mất thiết bị có thể mất credential vĩnh viễn. Nếu đã đăng ký **hai security keys** ở hai nơi an toàn, key còn lại cho phép xác thực để thay thế key mất.
- **Synced**: cùng credential có thể được bảo vệ, mã hóa và đồng bộ qua hệ sinh thái provider. Người dùng có thể lấy lại passkey khi đăng nhập provider trên thiết bị mới. Điều này giảm lockout nhưng đưa thêm trust vào bảo mật và **account recovery của sync provider**.
- **Cross-device authentication / hybrid**: có thể dùng điện thoại gần đó để xác thực cho browser trên máy khác mà không phải đưa private key ra khỏi hệ sinh thái theo ý nghĩa copy plaintext. Đây là cách dùng authenticator còn kiểm soát, không phải một phương thức recovery mới nếu mọi passkey đã mất.

Do đó “đăng ký 2 passkeys” chỉ là dự phòng độc lập khi chúng **không cùng một điểm hỏng**. Hai thiết bị cùng sync một credential từ một provider có thể vẫn là cùng một WebAuthn credential. Đối với tài khoản giá trị cao, cân nhắc passkey bổ sung ở **authenticator/security key và vị trí khác** hoặc provider độc lập.

### 3.2. Cờ BE/BS: hiểu đúng, không làm quá

WebAuthn Level 3 định nghĩa `BE` (backup eligible) và `BS` (current backup state) trong authenticator data. Chúng hữu ích để hiển thị “có khả năng đồng bộ” và hỗ trợ chính sách thiết bị. Nhưng:

1. `BE=1` không chứng minh credential đã được sao chép thành công.
2. `BS=1` không chứng minh RP biết danh sách thiết bị có bản sao hoặc nguồn sync an toàn tuyệt đối.
3. `BE=0` thường gợi ý device-bound; không cho phép kết luận mọi thuộc tính phần cứng nếu không có attestation/chính sách xác minh phù hợp.
4. Cờ từ một assertion cũ có thể không phản ánh ngay trạng thái của hệ sinh thái provider hiện tại.
5. Khi một **synced credential ID** bị thu hồi ở RP, **mọi bản sao dùng cùng credential đó** sẽ không còn đăng nhập được ở RP. Không thể “xóa credential chỉ ở điện thoại bị mất” bằng thao tác server-side theo credential ID.

Đừng ghi UI “Thiết bị iPhone X đã bị gỡ khỏi tài khoản” chỉ vì đã xóa một record với label tùy ý; thông báo chính xác hơn là “Passkey được chọn đã bị thu hồi cho tài khoản này”.

## 4. Mô hình đe dọa: kẻ tấn công sẽ nhắm vào đâu?

Một tài khoản passkey có chống phishing mạnh có thể bị suy yếu nếu recovery quá dễ. Những lối tấn công thường gặp:

1. **Helpdesk social engineering**: attacker biết tên/email/số nhân viên, giả báo mất điện thoại, yêu cầu nhân viên reset MFA và thêm passkey của attacker.
2. **Email takeover**: attacker đã vào mailbox, dùng link “forgot passkey” để bypass yêu cầu WebAuthn.
3. **SIM swap / SMS interception**: dùng OTP gửi SMS để thay xác thực bằng khóa mật mã của passkey.
4. **Session hijacking**: attacker có cookie/session từ malware; từ một phiên cũ họ có thể tìm cách thêm passkey hoặc xóa passkey chính.
5. **Password downgrade**: UI hiển thị “Try another way → password” với password cũ/yếu vẫn còn hoạt động, khiến phishing-resistant guarantee bị mất.
6. **Recovery code theft/replay**: mã backup bị lưu cùng máy/drive bị mất, quá ngắn, không giới hạn đoán hoặc không tiêu thụ một lần.
7. **Cross-tenant credential deletion**: backend nhận credential ID và xóa tùy ý mà không kiểm tra owner.
8. **Race condition**: thêm/xóa credential và thay email/role đồng thời làm policy “phải còn một authenticator an toàn” bị vượt qua.
9. **Insider recovery abuse**: một nhân viên hỗ trợ có thể tự phê duyệt khôi phục cho người khác mà không audit/phân quyền tách biệt.
10. **Sync-provider compromise**: attacker chiếm account quản lý passkeys và có thể bootstrap thiết bị mới bằng quy trình recovery của provider.

“Không tạo đường yếu hơn” không có nghĩa không bao giờ hỗ trợ người dùng bị mất mọi thiết bị; nó nghĩa là **mỗi lối khôi phục được thiết kế, giới hạn phạm vi và kiểm chứng bằng bằng chứng tương xứng**, không biến một code email đơn độc thành quyền cấp passkey không giới hạn.

## 5. Phòng ngừa: thiết lập recovery *trước* khi thiết bị bị mất

### 5.1. Đăng ký authenticator dự phòng độc lập

Ngay sau khi người dùng thêm passkey đầu tiên, UI nên khuyến khích:

- Thêm passkey thứ hai trên **authenticator độc lập** hoặc một hardware security key cất an toàn, đặc biệt cho tài khoản admin/tài chính.
- Có thể dùng synced passkey để giảm lockout phổ biến, nhưng đối với high assurance nên có phương án tách khỏi cùng cloud account.
- Xác nhận người dùng đã thực sự kiểm tra đăng nhập bằng phương án dự phòng (không chỉ thấy màn hình “đã lưu”).
- Lưu các thông tin người dùng dễ hiểu: label, ngày tạo, lần dùng gần nhất và chính sách backup mà WebAuthn cho biết; không hiển thị credential ID/public key thô như dữ liệu dùng để xác minh chủ sở hữu.
- Khi thêm passkey mới: yêu cầu **reauthentication/step-up** đủ mới, kiểm tra quyền trên account hiện tại, CSRF, chống đăng ký bởi session bị đánh cắp.

Một phiên tồn tại 30 ngày được đăng nhập bằng password cũ có thể không đủ để gắn passkey mới cho tài khoản yêu cầu phishing-resistant auth. Cần phân biệt `session.isAuthenticated()` với **thời điểm và độ mạnh của authentication vừa dùng**. Có thể dùng `auth_time`, mức AAL/acr, WebAuthn UV và bằng chứng step-up theo cơ chế của ứng dụng.

### 5.2. Đăng ký recovery codes chỉ khi chính sách cho phép

Recovery code không phải passkey, vì là secret có thể bị phishing. Nếu sản phẩm chọn cung cấp:

- Sinh bằng nguồn ngẫu nhiên mật mã; tham khảo NIST SP 800-63B-4: **saved recovery code tối thiểu 64 bit entropy** trong phạm vi yêu cầu của chuẩn đó.
- Chỉ hiển thị một lần và khuyến khích **lưu offline** ở nơi khác với thiết bị/passkey bị mất, ví dụ bản in niêm phong hoặc vault độc lập.
- Lưu bản verifier đã hash theo chính sách, không lưu raw code; token dùng một lần, giới hạn số lần đoán và thời gian thử.
- Khi sử dụng thành công, **tiêu thụ nguyên tử** để chống 2 request cùng dùng.
- Không mặc định một code đơn lẻ đủ để cấp lại quyền cho tài khoản đòi AAL2/AAL3; tuân thủ tổ hợp bằng chứng/re-proofing theo assurance policy.
- Sau khi dùng hoặc cấp lại code, gửi thông báo qua kênh liên hệ đã biết.

**NIST 800-63B-4 ở AAL2** mô tả các tổ hợp recovery cụ thể, chẳng hạn hai code từ hai phương thức khác nhau, hoặc một code kết hợp một authenticator đơn yếu tố đã bind, hoặc lặp lại identity proofing đã có. Đây là yêu cầu của chuẩn trong bối cảnh áp dụng, không phải công thức phổ quát cho mọi ứng dụng. Đọc điều khoản gốc trước khi tuyên bố đạt compliance.

### 5.3. Khóa tài khoản khi mất tất cả bằng chứng

Một hệ thống có thể buộc người dùng thực hiện một quy trình thủ công tương xứng với mức bảo đảm trước khi khôi phục quyền truy cập. **Không tự tạo một “magic email link” luôn đủ quyền đăng ký passkey mới** chỉ vì triển khai nhanh. Nếu không có bằng chứng recovery được chấp thuận, chính sách có thể giữ tài khoản ở trạng thái khóa/chờ xác minh, kể cả khi trải nghiệm kém thuận tiện hơn.

### 5.4. Chuẩn bị kênh cảnh báo độc lập

Khi người dùng thêm/xóa passkey, thay địa chỉ recovery, thay chính sách MFA hoặc khôi phục tài khoản, cần gửi cảnh báo đến **địa chỉ đã được xác minh và lưu từ trước**. Không chỉ thông báo đến địa chỉ email vừa được kẻ tấn công thay đổi trong cùng recovery flow.

## 6. Quy trình khi báo mất thiết bị: ba nhánh khác nhau

### 6.1. Nhánh A — còn passkey đã đăng ký khác và tin cậy

```text
User reports lost device
        |
        v
Authenticate with independent enrolled passkey
        |
        v
Recent step-up / account ownership confirmed
        |
        +--> list relevant credential records
        |
        +--> revoke suspect credential(s) at RP
        |
        +--> invalidate suspicious sessions and refresh tokens as policy
        |
        +--> register and test replacement passkey
        |
        +--> notify out-of-band / audit / monitor
```

Đây thường là đường tốt nhất vì người dùng vẫn chứng minh quyền kiểm soát bằng một authenticator đã bind từ trước. Khi việc mất thiết bị là dấu hiệu compromise, nên xem lại các giao dịch/phiên phát sinh trong khoảng thời gian từ lần sử dụng an toàn gần nhất.

### 6.2. Nhánh B — synced passkey còn trên thiết bị an toàn

Người dùng có thể đăng nhập từ laptop đã gắn cùng passkey provider. Trước khi dùng passkey đó để xử lý sự cố, cần phân biệt:

- Thiết bị chỉ bị rơi/vỡ và provider account vẫn an toàn: có thể cho đăng nhập để thay thiết bị.
- Thiết bị **bị đánh cắp/không khóa/biết mã mở khóa**: cân nhắc thu hồi credential liên quan tại RP, ngay cả khi cùng credential còn trên laptop, và yêu cầu đăng ký credential khác qua bước xác thực đáng tin.
- Provider account có dấu hiệu chiếm quyền: khôi phục/bảo vệ provider theo quy trình của provider; RP cần hạn chế việc các bản synced credential tiếp tục xác thực nếu coi là compromised.

Nếu xóa **một synced credential ở RP**, bản passkey còn trên laptop cùng credential ID cũng không được RP chấp nhận nữa. Vì vậy cần **đảm bảo còn authenticator độc lập** trước khi xóa, nếu có thể; nếu không, đưa tài khoản vào quy trình recovery có kiểm soát, tránh hy sinh bảo mật chỉ để giảm số ticket.

### 6.3. Nhánh C — mọi authenticator đều mất/không truy cập được

Đây là **account recovery** thực sự, không chỉ “add another passkey”. Quy trình mẫu:

1. Nhận yêu cầu recovery, tạo case ID không tiết lộ account existence cho người ngoài.
2. Đặt giao dịch vào **risk review**: lịch sử thay đổi credential, thiết bị, địa lý, phương thức khởi xướng, account sensitivity, dấu hiệu gian lận.
3. Kiểm tra các bằng chứng recovery **đã đăng ký trước khi sự cố**, không dựa vào số điện thoại/email vừa được đổi.
4. Thực hiện tổ hợp recovery code + authenticator còn lại hoặc identity proofing/manual verification theo chính sách bảo đảm tương xứng; không chấp nhận câu hỏi bảo mật dễ đoán, ảnh giấy tờ gửi qua chat không có kiểm chứng, hoặc một nhân viên helpdesk tự ý “bấm reset MFA”.
5. Với account nhạy cảm, dùng phê duyệt tách biệt, thời gian chờ/cooling-off phù hợp, thông báo đến các kênh cũ và cơ chế báo cáo tranh chấp.
6. Sau khi recovery được duyệt, cấp **recovery session quyền hạn giới hạn**: chỉ được đăng ký passkey mới, kiểm tra giao dịch gần đây và reset thông tin khôi phục theo policy; **chưa** được rút tiền, thay payout account, thay admin role hoặc xuất dữ liệu nhạy cảm.
7. Hoàn thành **WebAuthn registration ceremony bình thường** để tạo public/private key mới ở authenticator người dùng đang kiểm soát. Recovery evidence **không** phải là public key hay WebAuthn assertion.
8. Thu hồi credentials bị mất/đáng ngờ, hủy các sessions/tokens có nguy cơ, cấp lại recovery codes khi cần.
9. Gửi thông báo độc lập, lưu audit event với actor/case/timestamp/method, cho phép user khiếu nại và monitor hành vi.

**Khác biệt quan trọng:** một recovery session được cấp sau kiểm chứng **không tự đồng nghĩa với một phiên người dùng đầy đủ**. Hệ thống phải khóa các endpoint nhạy cảm theo scope/authority riêng, và chỉ nâng quyền bình thường sau khi đăng ký/xác thực passkey mới thành công cùng các điều kiện khác đã định nghĩa.

## 7. Thu hồi (revoke) credential ở RP: phạm vi và giới hạn

### 7.1. “Revoke” nghĩa là bỏ binding credential → account

Theo WebAuthn, RP thường xác thực bằng cách tra credential ID để lấy public key/owner. Thu hồi có thể được triển khai bằng:

- **Xóa** credential record trong `UserCredentialRepository`.
- Hoặc dùng trạng thái `REVOKED/SUSPENDED` trong một bảng quản lý credential riêng và sửa verifier/policy để bỏ qua record đó; đây là **custom design**, không mặc định của mọi Spring repository.

Mục tiêu xác minh:

```text
credentialId  ──lookup─► credential record (publicKey + userHandle)
       |
       +-- revoked / missing ──► reject assertion
       |
       +-- active ──► verify signature + challenge + RP/origin/UV ...
```

Nếu dùng delete, phải đảm bảo **mọi node** thực thi authentication nhìn trạng thái đã đổi và không có cache lâu giữ record cũ. Nếu ứng dụng dùng một credential registry nằm memory trên từng node, xóa ở node A không bảo đảm node B đã mất record. Nên có persistence chia sẻ hoặc invalidation event đáng tin.

### 7.2. Thu hồi credential không tự động làm những điều sau

| Tài sản | Thu hồi passkey tại RP có tự tác động? | Việc cần làm khi có dấu hiệu compromise |
| --- | --- | --- |
| Private key trên thiết bị bị mất | **Không**; RP không điều khiển khóa bên trong authenticator | Khóa/xóa thiết bị hoặc thu hồi từ provider theo tính năng thực tế, đồng thời block RP credential |
| Cùng credential đã sync trên thiết bị khác | **Có**, với tư cách không còn được RP chấp nhận, nếu credential ID giống nhau | Nhận biết điều này khi hướng dẫn user; đăng ký credential mới độc lập |
| Session cookie đã xác thực | **Không mặc định** | Invalidate sessions liên quan theo session store/registry, rotate security state |
| OAuth access token/refresh token | **Không mặc định** | AS/RS revocation, short TTL, denylist/introspection phù hợp |
| Recovery codes / old reset links | **Không mặc định** | Thu hồi/reissue codes và vô hiệu token recovery chưa sử dụng |
| Passkey ở RP khác | **Không** | Mỗi RP quản lý binding riêng; phối hợp IdP/SSO khi cần |
| Khả năng đăng ký credential mới | **Không mặc định** | Bảo vệ registration với recent WebAuthn step-up hoặc verified recovery scope |

Khi báo mất thiết bị, **chỉ xóa một credential mà không hủy phiên đang mở trên thiết bị** có thể để kẻ tấn công tiếp tục thao tác. Ngược lại, hủy tất cả session không làm một credential bị đánh cắp mất khả năng tạo login mới. Hai bước cần được xét độc lập.

### 7.3. Gỡ một credential và “xóa tài khoản” khác nhau

Không xóa `PublicKeyCredentialUserEntity` hoặc account user chỉ để thu hồi một passkey; nhiều credential có thể cùng gắn với user handle. Trước khi xóa, xác định credential ID thuộc đúng user và chính sách cho phép hay không. Với account còn một credential cuối cùng, có thể từ chối self-service deletion cho tới khi đăng ký passkey mới hoặc đã có phương án recovery hợp lệ, trừ nhánh incident response có quyền khóa account.

## 8. Spring Security 6.5: API cần biết để quản lý credential

Spring Security **6.4+** có WebAuthn support trên **Servlet**; ở **6.5.11** có JDBC persistence và các API quản lý. Cấu trúc tiêu biểu:

| API (Spring Security 6.5) | Trách nhiệm |
| --- | --- |
| `HttpSecurity.webAuthn(...)` | Cấu hình RP ID, allowed origins và WebAuthn login/registration |
| `WebAuthnRegistrationFilter` | Xử lý registration, removal endpoint theo matcher |
| `UserCredentialRepository` | Lưu/tra/xóa `CredentialRecord` theo credential ID/user handle |
| `PublicKeyCredentialUserEntityRepository` | Tìm user handle của tài khoản, không phải kho riêng cho từng passkey |
| `CredentialRecord` | Metadata của credential: ID, user entity ID, public key, created/last used, BE/BS |
| `Bytes` | Wrapper bytes cho credential ID/user handle, Base64 URL helpers |
| `JdbcUserCredentialRepository` | Lưu credential record bằng JDBC trong schema riêng |
| `JdbcPublicKeyCredentialUserEntityRepository` | Lưu user entity bằng JDBC |
| `CredentialRecordOwnerAuthorizationManager` | Spring Security 6.5.10+ kiểm tra credential ID thuộc người dùng authenticated trước khi cho xóa |

**Chi tiết phiên bản đáng chú ý:** Javadoc `WebAuthnRegistrationFilter` phiên bản **6.5.11** nêu request matcher xóa mặc định là **`DELETE /webauthn/register/{id}`**, nhưng **mặc định mọi yêu cầu xóa bị từ chối** cho tới khi cấu hình `AuthorizationManager<Bytes>` thích hợp. Không đọc thấy endpoint `DELETE` rồi giả định nó đã mở cho user hoặc có thể mở bằng `permitAll()`.

`CredentialRecordOwnerAuthorizationManager` được đưa vào 6.5.10; không copy lớp này vào 6.5.0/6.4.x mà không nâng phiên bản. `WebAuthnConfigurer` trong DSL 6.5.11 **không có** method tùy biến `deleteCredentialAuthorizationManager(...)` theo javadoc; muốn dùng built-in deletion filter cần tìm đúng integration point của version hoặc xây một endpoint quản trị đã kiểm tra owner/CSRF/step-up. Đừng tự tạo method API không tồn tại.

### 8.1. Cấu hình WebAuthn Servlet cơ bản

Ví dụ **trích đoạn** trong class `@Configuration` đã có `HttpSecurity` bean và import đúng các kiểu Spring Security:

```java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/error").permitAll()
            .anyRequest().authenticated())
        .webAuthn(webauthn -> webauthn
            .rpId("example.com")
            .allowedOrigins("https://example.com"));
    return http.build();
}
```

Đoạn này minh họa WebAuthn DSL và origin/RP ID, **không phải một project độc lập chạy ngay**: bạn cần webapp cấu hình HTTPS, public domain đúng, user identity source, trang login/registration và dependencies tương thích. Nếu muốn dùng form login để học đăng ký passkey, cần nhớ rằng **password login trở thành một đường xác thực song song**; ứng dụng high assurance không thể khẳng định “passkey-only phishing resistant” khi password fallback vẫn mở cho những tài nguyên nhạy cảm.

WebAuthn challenge và creation/request options phải do framework tạo/lưu/đối chiếu; đừng viết endpoint `login?credentialId=...` rồi coi ID là credential. Credential ID là **public identifier/reference**, không phải mật khẩu.

### 8.2. JDBC persistence cho nhiều node

Trong Spring Security 6.5:

```java
// Trích đoạn bean trong @Configuration, có JdbcOperations được inject.
@Bean
JdbcPublicKeyCredentialUserEntityRepository userEntities(
        JdbcOperations jdbc) {
    return new JdbcPublicKeyCredentialUserEntityRepository(jdbc);
}

@Bean
JdbcUserCredentialRepository passkeyCredentials(JdbcOperations jdbc) {
    return new JdbcUserCredentialRepository(jdbc);
}
```

Import:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.web.webauthn.management.JdbcPublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.JdbcUserCredentialRepository;
```

Spring Security document hướng dẫn các schema ở classpath, trong đó `JdbcUserCredentialRepository` phụ thuộc resource:

```text
classpath:org/springframework/security/user-credentials-schema.sql
```

Trong production, triển khai schema/migration đã kiểm tra dialect trước khi bật JDBC repo; phải dùng storage chung cho các node, có transaction, chỉ mục và kế hoạch invalidation cache nếu có. Đừng dựa vào default in-memory repository cho một cluster.

### 8.3. Đọc và xóa đúng credential trong repository

`UserCredentialRepository` có các method:

```java
CredentialRecord findByCredentialId(Bytes credentialId);
List<CredentialRecord> findByUserId(Bytes userHandle);
void save(CredentialRecord record);
void delete(Bytes credentialId);
```

Đây là **chữ ký rút gọn để giải thích**, không phải một interface tự viết thay Spring Security. `PublicKeyCredentialUserEntityRepository.findByUsername(String)` trả user entity của RP, từ đó lấy `getId()`. `CredentialRecord.getUserEntityUserId()` là khóa liên kết. Bạn cần kiểm tra equality với user handle, không chỉ dựa vào UUID/email label.

Quan trọng: repository `delete(id)` **chỉ thực thi thao tác storage**, tự nó không áp dụng recent authentication, CSRF, owner authorization, kiểm tra last credential, session invalidation hay thông báo người dùng. Gọi repo từ một HTTP controller chưa bảo vệ là lỗi nghiêm trọng.

## 9. Ví dụ Java 17 Spring Security: service kiểm tra ownership trước khi xóa

Ví dụ sau trình bày một **class Spring service có thể biên dịch** với đúng API Spring Security 6.5.11 khi project Servlet đã có `spring-security-web` và WebAuthn dependencies. Nó chỉ làm **repository-level ownership check**; controller phải bảo đảm **reauthentication/step-up gần đây, CSRF, rate limiting, quyền recovery**, và service production cần transaction/atomic conditional delete để không có race khi nhiều request thay đổi liên kết credential đồng thời.

File `src/main/java/demo/passkey/PasskeyCredentialManagement.java`:

```java
package demo.passkey;

import java.util.List;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.webauthn.api.Bytes;
import org.springframework.security.web.webauthn.api.CredentialRecord;
import org.springframework.security.web.webauthn.api.PublicKeyCredentialUserEntity;
import org.springframework.security.web.webauthn.management.PublicKeyCredentialUserEntityRepository;
import org.springframework.security.web.webauthn.management.UserCredentialRepository;

public final class PasskeyCredentialManagement {

    private final PublicKeyCredentialUserEntityRepository users;
    private final UserCredentialRepository credentials;

    public PasskeyCredentialManagement(
            PublicKeyCredentialUserEntityRepository users,
            UserCredentialRepository credentials) {
        this.users = users;
        this.credentials = credentials;
    }

    public List<CredentialRecord> listForAuthenticatedUser(
            String authenticatedUsername) {
        PublicKeyCredentialUserEntity user =
                users.findByUsername(authenticatedUsername);

        if (user == null) {
            throw new AccessDeniedException("Account not available");
        }
        return credentials.findByUserId(user.getId());
    }

    public void removeOwnedCredential(
            String authenticatedUsername, Bytes credentialId) {

        PublicKeyCredentialUserEntity user =
                users.findByUsername(authenticatedUsername);
        if (user == null || credentialId == null) {
            throw new AccessDeniedException("Not allowed");
        }

        CredentialRecord record =
                credentials.findByCredentialId(credentialId);

        if (record == null ||
                !user.getId().equals(record.getUserEntityUserId())) {
            throw new AccessDeniedException("Not allowed");
        }

        // Security policy phải được kiểm tra TRƯỚC lời gọi này:
        // recent phishing-resistant step-up hoặc verified recovery flow;
        // session/token invalidation nếu là sự cố bị compromise;
        // bảo đảm không tự khóa mình ngoài tài khoản.
        credentials.delete(credentialId);
    }
}
```

**Điều đã được code thực hiện:** chỉ lấy user theo `authenticatedUsername` do server cung cấp, kiểm tra owner theo user handle, từ chối credential không tồn tại/không thuộc user, rồi gọi API `delete`. Để class được Spring DI quản lý, bạn có thể khai báo `@Bean PasskeyCredentialManagement` hoặc đánh dấu `@Service` theo cấu hình project; ví dụ không dùng static global state.

**Điều class cố ý không tự giả định:** một chuỗi username truyền vào là đã có WebAuthn step-up hay chưa; nó không có request/session context để biết. Caller phải lấy username từ `Authentication` do Spring Security xác thực và áp dụng các policy nêu trên. Một HTTP endpoint chỉ gọi class này sau `@PreAuthorize("isAuthenticated()")` **chưa đủ** cho thay đổi security-critical.

**Race condition:** `findByCredentialId` → owner check → `delete` vẫn là hai thao tác. Trong hệ thống nhiều node/tenant, nên dùng transaction và **conditional delete theo credential ID + owner user ID** để tránh TOCTOU; repository generic không hứa một atomic conditional delete cho cả kiểm tra ownership. Nếu không có cơ chế bảo đảm, không tự công bố endpoint này production-ready.

## 10. Chống tự khóa tài khoản và chống thêm passkey bởi kẻ cướp session

### 10.1. Không xóa passkey cuối cùng tùy tiện

Có ít nhất ba chính sách hợp lý tùy sản phẩm:

1. **Self-service normal**: chỉ cho xóa một credential nếu user còn authenticator dự phòng độc lập và đã làm recent step-up. Với một credential cuối cùng, yêu cầu thêm passkey mới trước.
2. **Incident response**: khi credential cuối cùng bị nghi compromise, lập tức suspend/revoke và đưa account vào trạng thái recovery restricted; không giữ credential nguy hiểm chỉ để người dùng còn đăng nhập.
3. **Admin break-glass**: cần proofing/phê duyệt và audit độc lập; không cho helpdesk dùng `permitAll()` hoặc nhúng quyền admin cứng vào UI.

Đếm `credentials.findByUserId(userId).size()` trước khi xóa chỉ là **hiển thị hoặc check sơ bộ**. Hai transaction cùng lúc có thể đều thấy size=2 rồi xóa hai credential khác nhau, để lại 0. Muốn đảm bảo “còn ít nhất một credential” cần serializable/locking/conditional policy ở persistence.

### 10.2. Thêm passkey mới cũng là thao tác có rủi ro cao

Attacker có thể sở hữu session cookie nhưng không sở hữu passkey. Nếu ứng dụng cho phép **POST /webauthn/register/options** và **POST /webauthn/register** chỉ dựa trên một phiên authenticated từ lâu, attacker có thể tạo passkey trên thiết bị của họ. Vì vậy registration/options và credential removal cần:

- Recent, sufficiently strong reauthentication được ghi nhận **server-side** (không tin flag `recent=true` từ client).
- User verification (UV) phù hợp chính sách; không coi `userPresent` đơn lẻ luôn là AAL2.
- CSRF protection cho request thay đổi trạng thái, đặc biệt khi browser dùng cookies.
- Ownership check và giới hạn số/thời gian thao tác, risk scoring khi đổi thiết bị/vùng.
- Thông báo independent out-of-band đến địa chỉ đã đăng ký trước.
- Với recovery restricted session: chỉ cho đăng ký **một credential mới** sau proofing, rồi kiểm tra sử dụng thật, mới mở tiếp các quyền cần thiết.

Một passkey mới được đăng ký thành công **không tự chứng minh recovery evidence trước đó đủ tin cậy**. Nếu một đường email-link dễ bị chiếm đã tạo quyền đăng ký, passkey của attacker có thể trông hoàn toàn hợp lệ về mật mã.

### 10.3. Trình tự thay thế khi user còn passkey an toàn

```text
authenticate with known-good passkey
       |
       v
register NEW passkey on trusted authenticator
       |
       v
VERIFY new credential with a real assertion
       |
       v
revoke lost/compromised credential record(s)
       |
       v
invalidate risky sessions and tokens as needed
       |
       v
notify + audit + recovery-code rotation
```

Nếu có dấu hiệu **attacker đang dùng credential cũ**, thứ tự có thể thay đổi: suspend compromised credential ngay và đưa account vào recovery flow hạn chế. Không trì hoãn revocation cho đến khi attacker dùng xong session, nhưng cũng không mở một bypass yếu để xử lý lockout.

## 11. Session và token lifecycle sau khi thu hồi passkey

Sau khi WebAuthn assertion hợp lệ, Spring Security có thể tạo HTTP session hoặc phát hành application/OAuth tokens. **Verifier credential và session manager là hai state khác nhau**.

Một playbook xử lý nghi compromise thường làm:

1. Đánh dấu credential cần thu hồi trong repository và đảm bảo tất cả auth nodes chặn nó.
2. Invalidate phiên người dùng trên thiết bị đáng ngờ; nếu không xác định phiên nào liên quan hoặc rủi ro cao, invalidate **toàn bộ session** của user theo chính sách.
3. Nếu ứng dụng dùng Spring Session/Redis, xóa session records trong shared store; không chỉ đặt cookie hết hạn trên browser hiện tại.
4. Nếu đã phát OAuth refresh/access tokens, gọi đúng cơ chế revocation ở Authorization Server, điều phối Resource Servers nếu cần; JWT offline vẫn có thể sống đến `exp` nếu không có denylist/introspection.
5. Revoke **remember-me persistent tokens**, recovery tokens/codes và account-change tokens còn hiệu lực khi nghi mất quyền kiểm soát.
6. Cân nhắc session rotation/reauthentication trên thiết bị tốt; tránh vô tình để attacker tiếp tục dùng old session.
7. Audit thời điểm chặn credential, danh tính thực hiện, policy decision, case ID, số session invalidated và kết quả token revoke.

Bảo đảm đầu cuối “attacker không còn truy cập được” phụ thuộc **cả WebAuthn, session, OAuth tokens, session cache và RS enforcement**. Một dòng `userCredentialRepository.delete(...)` không đủ để đưa ra lời cam kết như vậy.

### 11.1. Không lạm dụng “logout all” cho sự cố không nghi compromise

Nếu người dùng chỉ làm hỏng một security key offline không bị ai lấy cắp, mức rủi ro khác với điện thoại mất cắp đang mở khóa. Chính sách có thể giữ những session an toàn sau khi xác minh user, nhưng quyết định phải dựa trên threat model và hành vi thực tế, không dựa một checkbox “lost device” quá mơ hồ.

## 12. Bài tập Java 17 độc lập: state machine thu hồi credential

Để hiểu **credential revocation khác session invalidation**, dưới đây là ví dụ Java 17 thuần (không phụ thuộc Spring). Nó mô phỏng các quy tắc đã định nghĩa mà không thực hiện cryptographic WebAuthn verification hoặc session store thật.

Lưu thành `PasskeyRecoveryModel.java`:

```java
import java.util.LinkedHashSet;
import java.util.Set;

public class PasskeyRecoveryModel {

    static final class Account {
        final Set<String> credentialIds = new LinkedHashSet<>();
        boolean sessionActive = true;
        boolean recoveryApproved = false;

        Account(String... initialIds) {
            for (String id : initialIds) {
                credentialIds.add(id);
            }
        }

        boolean canAuthenticate(String credentialId) {
            return credentialIds.contains(credentialId);
        }

        void revoke(String credentialId) {
            credentialIds.remove(credentialId);
        }

        void invalidateSession() {
            sessionActive = false;
        }

        boolean enrollReplacement(String id) {
            if (!recoveryApproved || id == null || id.isBlank()) {
                return false;
            }
            credentialIds.add(id);
            recoveryApproved = false; // consume restricted recovery approval
            return true;
        }
    }

    public static void main(String[] args) {
        Account alice = new Account("synced-A", "security-key-B");

        System.out.println("before A: " + alice.canAuthenticate("synced-A"));
        alice.revoke("synced-A");
        System.out.println("after A: " + alice.canAuthenticate("synced-A"));
        System.out.println("old session: " + alice.sessionActive);

        alice.invalidateSession();
        System.out.println("session after invalidate: " + alice.sessionActive);

        System.out.println("enroll without proof: "
                + alice.enrollReplacement("replacement-C"));

        // Chỉ mô phỏng: policy engine đã phê duyệt recovery.
        alice.recoveryApproved = true;
        System.out.println("enroll with proof: "
                + alice.enrollReplacement("replacement-C"));
        System.out.println("new credential: "
                + alice.canAuthenticate("replacement-C"));
        System.out.println("replay approval: "
                + alice.enrollReplacement("attacker-D"));
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac PasskeyRecoveryModel.java
java PasskeyRecoveryModel
```

Stdout **chính xác**:

```text
before A: true
after A: false
old session: true
session after invalidate: false
enroll without proof: false
enroll with proof: true
new credential: true
replay approval: false
```

Bài tập cho thấy:

- Credential A bị thu hồi thì `canAuthenticate("synced-A")` chuyển từ true sang false.
- Old session **vẫn true** cho tới khi gọi thao tác invalidate độc lập.
- Recovery approval là một quyền có hạn và đã được consume, không phải một flag tồn tại mãi.
- `recoveryApproved=true` ở ví dụ là dữ liệu test có kiểm soát; **không được** lấy từ parameter/query của client trong ứng dụng thật.

Ví dụ không có WebAuthn signature, không có lock/transaction, không có expiry/CSRF/identity proofing; dùng để học state boundary, **không** làm mẫu endpoint recovery production.

## 13. Thiết kế recovery code an toàn và race condition

Nếu sản phẩm hỗ trợ saved recovery codes, một thiết kế server-side cần đảm bảo:

| Khía cạnh | Hợp đồng mong muốn |
| --- | --- |
| Sinh | CSPRNG, entropy theo mức assurance; ví dụ tối thiểu 64 bit theo NIST saved code và có thể chọn cao hơn |
| Lưu | Chỉ lưu verifier hash có salt/khoá phù hợp; mã thô chỉ hiển thị một lần; bảo vệ DB backup |
| Kiểm tra | Rate limit theo account/IP/risk, thông báo lỗi chung không lộ mã nào hợp lệ |
| Tiêu thụ | **Atomic mark-used/delete**, đúng một request thắng khi cùng code gửi đồng thời |
| Scope | Không biến code thành session quyền đầy đủ nếu chính sách yêu cầu thêm proof |
| Expiry | Áp dụng policy phù hợp saved/issued code; không tự coi mọi mã vô thời hạn |
| Notify | Cảnh báo kênh đăng ký cũ cho recovery attempt, success, thêm/xóa credential |
| Rotate | Sau recovery cần phát mã mới và thu hồi mã cũ/đã dùng |
| Audit | Lưu kết quả/risk/case ID, không lưu raw code hay passkey private key |

Ví dụ **SQL giả định** cho một bảng recovery code do ứng dụng tự thiết kế (PostgreSQL dialect), không phải schema Spring Security:

```sql
-- Một request chỉ được thắng nếu code còn chưa tiêu thụ.
UPDATE account_recovery_codes
SET used_at = CURRENT_TIMESTAMP
WHERE account_id = :account_id
  AND code_hash = :code_hash
  AND used_at IS NULL
  AND revoked_at IS NULL
RETURNING code_id;
```

Khi có expiry, bổ sung điều kiện `expires_at > CURRENT_TIMESTAMP` theo schema/policy. Phải xác nhận **1 row affected** mới coi code được dùng hợp lệ. Hash lookup và transaction/uniqueness cần phù hợp triển khai; không tách `SELECT unused` rồi `UPDATE used` ngoài transaction. Nếu chỉ dựa vào one-time code là thấp hơn assurance hiện hành, **vẫn phải áp dụng những bằng chứng bổ sung** trước khi cho phép enrolment.

### 13.1. Những race khác phải kiểm tra

- Hai thao tác xóa hai credential cuối cùng cùng lúc.
- Recovery approval bị dùng đồng thời ở hai tab để đăng ký hai passkeys, trong đó một passkey của attacker.
- Một request xóa credential và một request đang xác thực bằng credential đó; định nghĩa thời điểm hiệu lực ở storage/cache.
- Một request thay email recovery và một request khởi động recovery; thông tin liên hệ dùng để xác minh phải được **snapshot từ trước** hoặc có risk policy.
- Session invalidation event đến sau khi credential revoke; cần kiểm tra cửa sổ nguy cơ và độ trễ lan truyền.

## 14. Bề mặt hỗ trợ (helpdesk) và anti-social-engineering

Một nhân viên hỗ trợ thường có kiến thức nội bộ nhưng **không thể chứng minh quyền sở hữu tài khoản chỉ bằng việc thấy ticket/email**. Quy trình phải giảm quyền của helpdesk và đặt bằng chứng độc lập.

### 14.1. Chính sách đề xuất

- Helpdesk có thể **tạo yêu cầu, đánh dấu tài khoản bị nghi compromise và yêu cầu review**; không tự bypass WebAuthn hoặc tự phát full session.
- Với yêu cầu high assurance, ít nhất có **tách vai trò đề nghị/phê duyệt** phù hợp risk; có thể kèm thời gian chờ hoặc liên hệ qua kênh đã đăng ký trước.
- Nếu sản phẩm đã identity-proofed user lúc onboarding, recovery có thể yêu cầu **reproofing** tương xứng; không nhận một ảnh giấy tờ vô danh qua chat rồi coi đã xác minh.
- Chỉ cho phép phát một recovery session scope hẹp; phải đăng ký WebAuthn passkey mới và xác minh bằng assertion thực trước khi cho các quyền nhạy cảm.
- Quyết định recovery phải gắn case ID, actor, proof type, timestamps, approvals và kết quả. Audit chống sửa/xóa tùy tiện.
- Dùng thông báo out-of-band và cơ chế báo cáo “không phải tôi”, nhất là trước/sau khi thay email/số điện thoại của account.
- Không tiết lộ “account có tồn tại/đã bật passkey nào” trong endpoint công khai thông qua status/latency khác biệt rõ.

### 14.2. Các đường yếu cần loại bỏ

```text
BAD: "I lost my passkey"
  -> send a 6-digit SMS to a newly supplied phone
  -> allow full login and add new passkey
```

```text
BAD: "I have a browser session"
  -> change account recovery email
  -> send magic link to that new email
  -> register an attacker's passkey
```

```text
GOOD: lost all authenticators
  -> verified pre-enrolled recovery methods / identity proofing
  -> restricted recovery state + audit + independent notification
  -> normal WebAuthn registration + real assertion
  -> revoke compromised credentials/sessions
  -> restore necessary privileges under risk policy
```

“GOOD” là mô hình tổng quát; **không** có một số bước đơn giản cố định đủ đạt mọi AAL/IAL. Với tài khoản tài chính hoặc admin, cần đọc quy định assurance và yêu cầu pháp lý tương ứng.

## 15. UX và thông điệp chính xác với người dùng

Các trạng thái UI cần tránh gây hiểu lầm:

| Hành động | Copy được phép hiển thị | Không nên nói |
| --- | --- | --- |
| Đăng ký passkey | “Passkey đã được thêm vào tài khoản này.” | “Điện thoại đã an toàn vĩnh viễn.” |
| Thu hồi credential | “Passkey này không còn được chấp nhận để đăng nhập tài khoản này.” | “Khóa riêng đã bị xóa khỏi mọi thiết bị.” |
| Hủy session | “Các phiên đã chọn đã bị đăng xuất.” | “Mọi OAuth token đã bị thu hồi.” khi chưa kiểm chứng |
| Mất synced passkey | “Nếu provider account còn an toàn, bạn có thể khôi phục khả năng sử dụng trên thiết bị khác.” | “Đã xóa trên điện thoại mất cắp nhưng laptop vẫn dùng cùng passkey như cũ.” |
| Không còn authenticator | “Bắt đầu khôi phục với các phương thức đã đăng ký.” | “Chỉ cần email/SMS mới là có toàn quyền.” |
| Recovery approved | “Bạn có thể đăng ký phương thức đăng nhập mới trong phiên khôi phục giới hạn.” | “Mọi thao tác tài khoản đã mở khóa.” |
| Thêm/xóa credential nhạy cảm | “Thay đổi đã được ghi nhận. Nếu không phải bạn, hãy báo cáo.” | Hiển thị raw credential ID/private key làm bằng chứng |

Một trang **Manage passkeys** nên hiển thị danh sách credential records với label, created/last used, trạng thái nếu chính sách có, cảnh báo backup theo tín hiệu; cung cấp nút rename/delete có CSRF và recent step-up. Khi người dùng xóa một **synced credential**, giải thích nó có thể ngừng hoạt động **ở mọi thiết bị có cùng passkey**.

### 15.1. Hỗ trợ người dùng không am hiểu sync

Không bắt người dùng phải biết “WebAuthn BE bit” là gì. Hỏi theo tình huống: “Bạn còn máy khác đang dùng cùng passkey provider không?”, “Bạn có security key dự phòng không?”, “Thiết bị bị mất có khả năng bị người khác mở khóa không?”. UI dùng câu dễ hiểu; backend vẫn phải áp chính sách bảo mật dựa trên bằng chứng, không chỉ dựa khai báo của người dùng.

## 16. Kiểm thử bảo mật: không chỉ test nút Delete trả 200

Dưới đây là ma trận kiểm thử cho ứng dụng thực tế:

| Test | Điều kiện | Kết quả cần đạt |
| --- | --- | --- |
| T1. Revoke đúng credential | User có A, B; thu hồi A sau step-up | Assertion bằng A bị từ chối; B vẫn đăng nhập được |
| T2. Revoke synced credential | A synced ở hai thiết bị | Cả hai bản của A bị RP từ chối; không diễn giải như revoke riêng một thiết bị |
| T3. Revoke sai owner | Alice gọi DELETE với ID credential của Bob | 403/404 theo policy, credential Bob vẫn active |
| T4. Gọi DELETE unauthenticated/CSRF | Không có session hoặc token CSRF | Bị từ chối, registry không đổi |
| T5. Session cũ sau revoke | Có session được tạo trước khi xóa A | Được hủy nếu incident policy yêu cầu; test riêng với token cũ |
| T6. Xóa credential cuối cùng | User chỉ có A, không có recovery | Self-service phải bị chặn/đi vào flow kiểm soát, không âm thầm lockout |
| T7. Hai DELETE đồng thời | User có A, B; mỗi request xóa một ID | Database policy ngăn trạng thái không có đường truy cập nếu policy yêu cầu |
| T8. Thêm passkey từ session bị đánh cắp | Session cũ, không có recent WebAuthn step-up | Không cấp phép registration mới |
| T9. Email/SMS bypass | Attacker chỉ sở hữu email/SMS đã chiếm | Không được nâng thành full WebAuthn account nếu policy cao hơn |
| T10. Recovery code replay | Gửi cùng code từ hai requests | Đúng một claim thành công; không có hai recovery sessions |
| T11. Recovery code brute force | Sai nhiều lần từ IP/tài khoản | Rate limit/risk escalation, không tiết lộ account/code |
| T12. Recovery contact mới đổi | Attacker đổi email rồi yêu cầu recovery | Không sử dụng thông tin mới để bypass proofing |
| T13. Device-bound lost | A trên key bị mất, B trên key dự phòng | Dùng B để revoke A, đăng ký và test C |
| T14. Synced provider compromised | Provider bị chiếm, user còn B independent | Thu hồi credential thuộc provider, invalid sessions, test B và re-enrolment |
| T15. Multi-node | Revoke A ở node 1, login A ở node 2 | Node 2 từ chối sau ngưỡng propagation được định nghĩa |
| T16. Session/token cleanup failure | Credential revoke OK, Redis/AS revoke lỗi | Không tuyên bố toàn bộ incident đã resolved; retry/audit/escalation |
| T17. Support impersonation | Operator nhập ticket không có proof | Không thể tự phê duyệt/đổi passkey, audit rõ |
| T18. No registered authenticator | Người dùng mất hết passkeys | Recovery theo assurance policy, không chuyển sang password yếu mặc định |
| T19. Passkey label spoofing | User đặt label giống thiết bị khác | Backend dùng credential ID/owner, không dùng label để xác thực |
| T20. Backup flags | Credential BE=1/BS=1, BE=0 | UX/risk phù hợp; không giả định biết danh sách bản sao |
| T21. WebAuthn origin mismatch | Assertion từ origin/RP ID không đúng | Bị từ chối, không bypass trong recovery |
| T22. Notifications | Recovery success / credential added/deleted | Gửi tới kênh đã đăng ký, không chứa secret/private key |

**Lưu ý với test Spring Security:** `MockMvc` và `spring-security-test` có thể kiểm tra authorization/CSRF/session của controller. Muốn chứng minh WebAuthn ceremony thật, cần browser hỗ trợ WebAuthn/virtual authenticator và backend validator thật, không chỉ mock `Authentication`. Kiểm thử cross-device, synced provider và mất thiết bị cần môi trường riêng hoặc mô phỏng ranh giới rõ ràng.

### 16.1. Kịch bản end-to-end tiêu biểu

```text
Setup:
  Enroll A trên phone (synced), B trên hardware key (independent).
  Login bằng A -> tạo RP session S.

Incident:
  Báo phone bị đánh cắp; giả định attacker có thể dùng S.
  Đăng nhập an toàn bằng B, xác minh step-up.
  Revoke A trong RP repository.
  Invalidate S và các sessions rủi ro; thu hồi tokens theo kiến trúc.
  Register C trên thiết bị mới và xác minh assertion C.

Assertions:
  A -> login rejected.
  B -> login accepted.
  C -> login accepted sau khi được lưu.
  S -> không còn được dùng nếu incident policy yêu cầu invalidate.
  Raw private key -> không xuất hiện ở RP.
  Credential A trên provider -> có thể còn được lưu nhưng RP không chấp nhận.
```

Với high assurance, test thêm **recovery không có B**: chỉ các chứng cứ proofing theo policy mới dẫn đến restricted recovery session, rồi credential C; một email một bước không được bypass. Kết quả phải có audit và notification.

## 17. Vận hành, incident response và trách nhiệm thực tế

### 17.1. Phân công trách nhiệm

| Vai trò | Trách nhiệm |
| --- | --- |
| RP application | Lưu public keys/credential IDs, xác minh WebAuthn, revoke binding, thực thi authorization/step-up |
| Session/Identity backend | Theo dõi session, token và active credential state, hỗ trợ toàn bộ cluster |
| Passkey provider | Bảo vệ/đồng bộ private key theo chính sách; hỗ trợ khóa/xóa thiết bị và recovery provider account |
| User | Thông báo mất thiết bị, giữ backup authenticator/code an toàn, xác minh thông báo |
| Helpdesk | Tiếp nhận case và xử lý theo quyền, không bypass proofing |
| Security/Identity team | Risk policy, recovery approval, audit, alerts, incident containment |
| OAuth AS/RS (nếu có) | Revoke token, kiểm tra active/expiry theo hợp đồng, không suy từ WebAuthn credential deletion |

### 17.2. Audit log tối thiểu

Một audit event cần nêu:

- Stable account ID (không nhất thiết email), tenant ID khi có.
- Actor type (self-service, recovery operator, automated risk response).
- Action (`PASSKEY_ADDED`, `PASSKEY_REVOKED`, `RECOVERY_STARTED`, `RECOVERY_APPROVED`, `SESSIONS_INVALIDATED`).
- Timestamp, case/correlation ID, phương thức step-up/proofing, result/reason code.
- Credential reference được bảo vệ (nếu phải log, cân nhắc hash/pseudonymous id; credential ID thô là dữ liệu nhận diện không nên phát tán).
- Trạng thái propagate tới các authentication nodes/token stores khi cần.

**Không log** raw recovery codes, password, WebAuthn private key (RP không có), full signed assertion, session cookies hoặc OAuth tokens. Giới hạn quyền đọc và thời gian retention của audit logs phù hợp chính sách riêng tư.

### 17.3. Phương thức hỗ trợ khóa thiết bị từ xa

Hệ điều hành/passkey provider có thể cho người dùng khóa hoặc wipe thiết bị từ xa. Đây là bước **bên ngoài** RP, có thể làm giảm rủi ro sử dụng credential, nhưng không được xem là thay thế revoke credential tại RP trong sự cố đáng ngờ; trạng thái thực thi lệnh wipe có thể không chắc chắn (thiết bị offline). Khi ngược lại, RP revoke rồi, provider có thể vẫn giữ passkey local/synced cho tới khi có cơ chế xóa.

### 17.4. Đồng bộ trạng thái trong ứng dụng phân tán

Trong môi trường đa node:

- Dùng shared credential registry/persistence, update/revocation có tính nguyên tử.
- Nếu cache records cho authentication, định nghĩa tối đa độ trễ cache invalidation; ưu tiên fail closed khi không xác định được trạng thái.
- Có cảnh báo khi DB writes/session deletion/token revocation thất bại hoặc trạng thái chưa lan tới node khác.
- Test rollback, schema migration, backup restore: không cho backup cũ “hồi sinh” credential đã revoked. Có thể dùng tombstone/revocation ledger để hỗ trợ kiểm soát này.
- Thực hiện thao tác xóa credential và thay đổi “recovery restricted” theo transaction hoặc workflow có trạng thái rõ; không lẫn partial success với hoàn thành.

## 18. Checklist triển khai trước production

1. **Inventory:** RP lưu danh sách `credentialId → userHandle → publicKey`, trạng thái created/last used/BE/BS khi phù hợp; người dùng xem và quản lý credentials trong một trang an toàn.
2. **Pre-enroll:** khuyến khích đăng ký ít nhất hai phương thức độc lập, có thể là security key dự phòng; tránh hai “dự phòng” cùng một synced credential/provider bị chiếm.
3. **Step-up:** thêm/xóa passkey và đổi recovery settings cần recent authentication đủ mạnh, UV theo policy, CSRF và authorization theo owner.
4. **Deletion:** ở Spring Security 6.5.11 built-in `DELETE /webauthn/register/{id}` mặc định denied; phải cấu hình authorizer phù hợp hoặc tự triển khai endpoint bảo vệ. Không dùng `permitAll()`.
5. **Revoke semantics:** credential bị xóa không được RP chấp nhận trên mọi node; không hứa remote deletion khỏi thiết bị hoặc tự revoke session/token.
6. **Device loss:** có runbook cho stolen, damaged, device-bound, synced-provider compromise và lost-all; xác định khi nào suspend ngay, khi nào user có thể dùng passkey an toàn khác để thay thế.
7. **Recovery assurance:** chỉ dùng saved codes/issued codes/contact/identity proofing theo policy và risk. Không để password/SMS/email-link thấp hơn mức bảo vệ của account tự động trở thành full login.
8. **Restricted recovery:** chỉ cho phép đăng ký credential mới sau proofing, tiêu thụ quyền một lần, xác minh assertion mới và xử lý thêm/xóa credentials khác theo chính sách.
9. **Session lifecycle:** invalidate suspicious sessions, remember-me và OAuth tokens riêng; test RS/session store.
10. **Concurrency:** conditional delete, claim recovery code atomic, xử lý last credential và cluster consistency.
11. **Notifications:** cảnh báo qua kênh đã đăng ký trước cho recovery/credential changes, có cách báo cáo giao dịch không hợp lệ.
12. **Operational security:** permission tách biệt của helpdesk, case approval/audit, anti-enumeration, rate limiting, monitoring, breach playbooks.
13. **Versioning:** xác minh dependencies/DSL của Spring Security version thực tế: 6.5 dùng `spring-security-web` + WebAuthn4J, còn 7.x có `spring-security-webauthn`; không copy cấu hình không tương thích.
14. **Tests:** có negative tests cho owner, CSRF, recent step-up, BE/BS, revoked synced credentials, cluster cache, recovery code replay, session invalidation và fake-helpdesk requests.

Quy tắc thiết kế: **thu hồi passkey tại RP chỉ chấm dứt quyền dùng credential ID/public key đó để xác thực mới.** Quy trình xử lý mất thiết bị phải bảo vệ cả phiên, token, phương thức recovery và quyền đăng ký passkey mới. Tài khoản chỉ an toàn bằng **đường yếu nhất mà attacker có thể dùng để lấy lại hoặc thay authenticator**.

## 19. Tài liệu chính thức và khuyến nghị

- [Spring Security 6.5 – Passkeys / WebAuthn (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html): DSL, endpoints registration/authentication, repository in-memory/JDBC.
- [Spring Security 6.5 – UserCredentialRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/UserCredentialRepository.html): `findByCredentialId`, `findByUserId`, `delete`.
- [Spring Security 6.5 – PublicKeyCredentialUserEntityRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/PublicKeyCredentialUserEntityRepository.html): user handle mapping.
- [Spring Security 6.5.11 – WebAuthnRegistrationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/registration/WebAuthnRegistrationFilter.html): deletion matcher và `setDeleteCredentialAuthorizationManager`, mặc định delete denied.
- [Spring Security 6.5.11 – CredentialRecordOwnerAuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/CredentialRecordOwnerAuthorizationManager.html): owner-based authorization, có từ 6.5.10.
- [Spring Security 6.5 – JdbcUserCredentialRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/webauthn/management/JdbcUserCredentialRepository.html): persistence và schema.
- [WebAuthn Level 3 – W3C Recommendation (25/08/2026)](https://www.w3.org/TR/2026/REC-webauthn-3-20260825/): WebAuthn ceremony, origin/RP ID, credential record, `BE`/`BS` và client signals.
- [NIST SP 800-63B-4 (2025) – Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b.html#authenticator-event-management): binding, invalidation, loss/theft, account recovery và notifications.
- [NIST SP 800-63B-4 – Account Recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#recovery): saved/issued recovery codes, combinations theo AAL và recovery notification.
- [NIST SP 800-63B-4 – Syncable Authenticators](https://pages.nist.gov/800-63-4/sp800-63b.html#syncable-authenticators): sync fabric và rủi ro cloud recovery.
- [FIDO Alliance – Synced Passkey Deployment: Emerging Practices](https://fidoalliance.org/wp-content/uploads/2024/05/Synced-Passkey-Deployment_-Emerging-Practices-for-Consumer-Use-Cases_2024-Final.pdf): mất thiết bị, BE/BS, dự phòng và UX.
- [FIDO Alliance – Displace Password + OTP Authentication with Passkeys](https://fidoalliance.org/white-paper-displace-password-otp-authentication-with-passkeys/): risk-based recovery, tránh recovery yếu hơn authenticator.
- [OWASP – Passkey Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Passkey_Security_Cheat_Sheet.html): revoke credential, account recovery, step-up và hạn chế fallback yếu.
- [OWASP – Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): account recovery sau nghi compromise, session invalidation và kênh notification.
