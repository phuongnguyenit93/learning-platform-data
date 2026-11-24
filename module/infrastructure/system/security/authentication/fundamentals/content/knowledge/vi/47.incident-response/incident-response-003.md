# Credential leak — Ứng phó khi credential bị lộ

## 1. Credential leak là gì?

**Credential leak** là sự cố trong đó bí mật hoặc vật liệu xác thực bị tiết lộ cho người không được phép, hoặc được lưu/truyền ở nơi không còn bảo đảm quyền kiểm soát. Credential bị lộ có thể là mật khẩu, TOTP seed, recovery code, API key, client secret, private key, certificate bundle, refresh token, session cookie hoặc dữ liệu khôi phục có khả năng cấp lại quyền truy cập.

Ví dụ: một developer vô tình commit API key vào repository công khai. Dù commit đã bị xóa sau vài phút, key có thể đã được bot quét và sao chép. Xóa dòng code không thu hồi bí mật đã lộ. Đội ứng phó cần xác định key thuộc workload nào, scope và quyền gì, thời điểm có thể bị truy cập, dịch vụ nào đang dùng key, rồi revoke/rotate và điều tra hoạt động trước khi thay thế.

Trong chương **Incident response** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, chủ đề credential leak kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần biết mô hình hóa ranh giới tin cậy, chống phishing, replay và lạm dụng đăng nhập; quan trọng hơn, phải biến phát hiện rò rỉ thành quy trình containment, thu hồi, khôi phục và giảm nguy cơ tái diễn.

**Credential leak không đồng nghĩa mọi lần lộ dữ liệu đều đã bị sử dụng**, nhưng cũng không thể coi một bí mật đã công khai là an toàn chỉ vì chưa thấy đăng nhập bất thường. Xử lý cần dựa trên loại credential, phạm vi quyền, thời gian phơi lộ, khả năng truy cập của attacker và bằng chứng sử dụng.

## 2. Phân biệt exposure, leak, compromise và misuse

Các thuật ngữ này mô tả những mức độ khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Exposure** | Credential xuất hiện ở vị trí hoặc ngữ cảnh có thể không được bảo vệ đúng, nhưng chưa xác định ai đã truy cập. | Secret nằm trong log nội bộ có quyền đọc rộng. |
| **Leak** | Credential đã được tiết lộ ra ngoài phạm vi người được phép hoặc xuất hiện ở nơi không kiểm soát. | API key được push lên repository công khai. |
| **Compromise** | Có bằng chứng hoặc cơ sở đáng tin rằng attacker đã chiếm được khả năng sử dụng credential hoặc quyền liên quan. | Key bị dùng từ workload lạ để gọi API. |
| **Misuse** | Credential được sử dụng trái phép, dù nguồn rò rỉ có thể chưa rõ. | Session hợp lệ truy cập dữ liệu ngoài mục đích. |
| **Credential theft** | Attacker chủ động lấy credential bằng phishing, malware, dump hoặc social engineering. | Người dùng nhập mật khẩu vào trang giả. |

Không cần đợi chứng minh misuse mới containment. Với private key, refresh token hoặc API key có quyền cao đã công khai, khả năng sao chép thường đủ để kích hoạt rotation/revocation theo policy. Với exposure giới hạn trong hệ thống đã kiểm soát, có thể cần xác minh phạm vi trước khi chọn hành động.

## 3. Mục tiêu ứng phó sự cố credential leak

Một quy trình tốt cần đạt các mục tiêu:

1. **Protect people and systems:** bảo vệ người dùng, dữ liệu và dịch vụ đang bị ảnh hưởng.
2. **Contain access:** ngăn credential bị lộ tiếp tục cấp quyền.
3. **Preserve evidence:** giữ chứng cứ cần cho điều tra mà không sao chép thêm secret.
4. **Determine scope:** xác định credential, account, tenant, service, token family và dữ liệu liên quan.
5. **Eradicate persistence:** tìm và loại bỏ session, key, federation link hoặc cơ chế truy cập attacker đã tạo.
6. **Recover safely:** cấp credential thay thế và khôi phục hoạt động theo assurance phù hợp.
7. **Communicate clearly:** thông báo đúng người, đúng mức và không tiết lộ bí mật mới.
8. **Learn and improve:** sửa nguyên nhân gốc, kiểm soát phòng ngừa và khả năng phát hiện.

Ứng phó không chỉ là đổi mật khẩu. Nếu attacker đã dùng credential để tạo session, thêm passkey, phát hành API key khác hoặc thay recovery channel, những đường truy cập đó phải được điều tra và xử lý riêng.

## 4. Ranh giới tin cậy trong xử lý credential leak

Sự cố thường đi qua nhiều thành phần:

~~~mermaid
flowchart TD
    SRC["Nguồn phát hiện<br/>user, scanner, SIEM, provider"]
    TRIAGE["Incident triage<br/>classify + scope"]
    AUTH["Identity / credential authority"]
    SECRETS["Secret manager / KMS / PKI"]
    SESSIONS["Session and token services"]
    DOWN["Downstream APIs / workloads"]
    EVIDENCE[("Evidence store")]
    COMMS["Verified communication"]
    SRC --> TRIAGE
    TRIAGE --> EVIDENCE
    TRIAGE --> AUTH
    AUTH --> SECRETS
    AUTH --> SESSIONS
    SECRETS --> DOWN
    SESSIONS --> DOWN
    TRIAGE --> COMMS
~~~

Incident commander điều phối phạm vi và quyết định theo severity. Identity/credential authority là nơi có thể suspend hoặc revoke credential. Secret manager, KMS và PKI quản lý key/secret tương ứng. Session/token service xử lý các phiên và token đã phát hành. Downstream service phải xác minh trạng thái mới. Evidence store cần tách khỏi môi trường có thể đang bị attacker kiểm soát.

Không để người phát hiện sự cố tự gửi credential bản rõ qua email, chat hoặc ticket. Hãy dùng secret reference, loại credential, vị trí phát hiện và thời gian. Chỉ người/role được phê duyệt mới truy cập evidence cần thiết.

## 5. Nguồn phát hiện credential leak

Sự cố có thể được phát hiện từ nhiều nguồn:

- Secret scanning phát hiện key trong source code, commit, artifact hoặc image.
- Nhà cung cấp cloud/IdP cảnh báo credential được dùng từ nguồn lạ.
- SIEM phát hiện login, token exchange hoặc API usage bất thường.
- Người dùng báo đã nhập mật khẩu vào trang phishing.
- Developer hoặc nhân viên gửi nhầm file chứa secret.
- Log/APM/crash report chứa token hoặc cookie.
- Repository, package registry, object storage hoặc backup bị công khai.
- Endpoint detection phát hiện malware đánh cắp browser/session credential.
- Certificate authority hoặc KMS cảnh báo key export/operation bất thường.
- Nhà cung cấp bên thứ ba thông báo sự cố dữ liệu.

Mỗi nguồn có độ tin cậy và độ trễ khác nhau. Scanner tìm thấy secret không chứng minh key đã bị sử dụng; nhưng repository public có thể đã bị crawl trước lúc phát hiện. Cảnh báo từ provider có thể xác nhận usage nhưng cần kiểm tra đúng account, region và credential.

## 6. Triage: xác định loại credential và mức độ

Thông tin tối thiểu cần thu thập:

- Loại credential và định danh/reference của nó.
- Principal, tenant, application, workload hoặc service owner.
- Quyền, scope, audience và tài nguyên credential có thể truy cập.
- Nơi credential xuất hiện và ai có thể đọc.
- Thời điểm tạo, thời điểm phơi lộ và thời điểm phát hiện.
- Credential còn active hay đã hết hạn/revoke.
- Có bằng chứng sử dụng bất thường hay không.
- Các session, token, key con hoặc liên kết được tạo từ credential.
- Khả năng rotate/revoke và tác động tới dịch vụ.

Không đưa secret bản rõ vào báo cáo triage. Nếu cần xác định một secret cụ thể, dùng credential ID, key version hoặc fingerprint an toàn theo quy trình nội bộ.

### Ma trận severity tham khảo

| Mức | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| **Critical** | Private key/credential đặc quyền bị công khai; xác nhận attacker sử dụng; ảnh hưởng nhiều tenant hoặc control plane. | Incident commander, containment khẩn cấp, revoke và điều tra phạm vi rộng. |
| **High** | Password, refresh token, API key hoặc certificate có quyền nhạy cảm bị lộ ngoài trust boundary. | Suspend/revoke sớm, đánh giá session/token và downstream access. |
| **Medium** | Secret trong vùng nội bộ có quyền đọc rộng hoặc exposure giới hạn, chưa có bằng chứng misuse. | Hạn chế truy cập, xác minh audience, rotation theo risk và theo dõi. |
| **Low** | Placeholder, test credential vô hiệu hoặc dữ liệu không thể dùng để xác thực. | Xác minh không phải secret thật, ghi nhận và sửa nguồn phát. |

Severity phải dựa trên impact và khả năng khai thác, không chỉ tên loại credential. Một API key chỉ đọc dữ liệu công khai khác với key có quyền quản trị identity; một test token đã bị vô hiệu khác với refresh token production.

## 7. Điều phối và kích hoạt incident response

Khi xác định sự cố đủ nghiêm trọng:

1. Tạo incident ID và chỉ định incident commander.
2. Xác định owner của account/service/credential.
3. Chọn kênh liên lạc out-of-band đã được xác minh.
4. Ghi timeline và các quyết định containment.
5. Phân công nhóm identity, platform, endpoint, cloud, legal/privacy hoặc customer support theo phạm vi.
6. Đặt tiêu chí escalation và thời điểm cập nhật tình hình.
7. Hạn chế quyền truy cập evidence và secret.

Không yêu cầu người dùng gửi mật khẩu, OTP hoặc token để chứng minh bị lộ. Không chia sẻ secret qua ticket/chat để “cùng kiểm tra”. Nếu cần kiểm tra, dùng scanner hoặc thao tác trực tiếp trong secret manager với quyền tối thiểu.

## 8. Bảo toàn chứng cứ trước và trong containment

Containment cần nhanh, nhưng một số bằng chứng có thể biến mất khi revoke hoặc xóa tài nguyên. Thu thập tối thiểu những dữ liệu có giá trị:

- Credential reference, type, owner và status.
- Vị trí phơi lộ, URL/repository/path hoặc system reference.
- Commit ID, artifact digest hoặc object version nếu có.
- Timestamp phát hiện và nguồn phát hiện.
- Audit events về create, read, use, rotate, revoke.
- Login/session/token/API activity trong cửa sổ liên quan.
- KMS/PKI/secret manager access metadata.
- Các thay đổi account, MFA, recovery, role và federation.

Không lưu bản secret lộ vào evidence nếu không cần. Nếu buộc phải giữ để forensic, đặt trong evidence vault được mã hóa, quyền rất hạn chế, access audit và retention có chủ đích. Thường chỉ cần fingerprint, metadata và bản sao đã redact.

### Chain of custody

Với chứng cứ cần bảo toàn:

- Ghi người thu thập, thời điểm, nguồn và phương pháp.
- Tạo hash cho artifact/log export và ghi hash vào evidence manifest.
- Lưu bản gốc read-only; phân tích trên bản sao.
- Ghi mọi lần truy cập, chuyển giao và export.
- Đồng bộ thời gian và giữ cả occurred time lẫn collection time.
- Không sửa log gốc để loại secret; tạo bản redacted riêng.

## 9. Containment: ngăn credential tiếp tục được sử dụng

Containment phụ thuộc loại credential và mức độ compromise. Có thể:

- Suspend hoặc revoke credential tại authority.
- Disable account hoặc tạm hạn chế authentication method bị ảnh hưởng.
- Revoke session, refresh token family và grant liên quan.
- Rotate secret/key và cập nhật consumer.
- Chặn issuer, certificate hoặc API principal bị lạm dụng.
- Giảm scope/quyền tạm thời.
- Chặn nguồn tấn công theo risk policy, không dựa duy nhất vào IP.
- Tạm dừng workflow nhạy cảm trong khi xác minh.

Containment cần được xác nhận ở mọi verifier. Một credential bị revoke ở IdP nhưng resource server dùng cache cũ vẫn có thể chấp nhận token. Hãy xác định propagation SLA và kiểm tra thực tế sau khi thay đổi.

## 10. Password leak

Khi mật khẩu bị lộ:

1. Đánh giá account, tenant, quyền và khả năng password reuse ở dịch vụ khác.
2. Buộc reset password qua luồng chính thức; không yêu cầu người dùng gửi mật khẩu mới cho support.
3. Kiểm tra và revoke session/refresh token theo policy, đặc biệt nếu có dấu hiệu login thành công.
4. Tăng security epoch hoặc logout all sessions nếu cần.
5. Kiểm tra MFA, recovery channel, passkey và email/phone có bị thay đổi không.
6. Kiểm tra credential stuffing hoặc login từ nguồn lạ sau thời điểm lộ.
7. Khuyến nghị password duy nhất và password manager; kiểm tra password bị lộ theo cách bảo vệ privacy.

Đổi mật khẩu không tự thu hồi session đã tạo trước đó. Nếu attacker đã thêm authenticator hoặc thay recovery email, cần xử lý các credential và liên kết đó. Với tài khoản đặc quyền, step-up và xác minh độc lập có thể cần thiết trước khi mở lại.

## 11. Passkey và security key bị lộ hoặc mất

Passkey/WebAuthn private key thường được giữ trong authenticator. “Lộ passkey” có thể mang nghĩa thiết bị bị mất, tài khoản sync bị chiếm, authenticator bị điều khiển hoặc credential backup/sync bị compromise.

Ứng phó:

- Xác định credential ID và loại authenticator: device-bound hay syncable.
- Suspend/revoke credential bị ảnh hưởng tại relying party.
- Nếu thiết bị mất, revoke binding/credential và session liên quan theo policy.
- Nếu tài khoản sync của nền tảng bị chiếm, xử lý cả account đó và các thiết bị được đồng bộ.
- Kiểm tra enrollment mới, sign-in và recovery event bất thường.
- Dùng authenticator dự phòng hoặc recovery đủ assurance để đăng ký passkey mới.
- Không cố trích xuất private key hoặc sao chép key không exportable.

Public key đã lưu ở server không phải bí mật; private key hoặc khả năng sử dụng authenticator mới là tài sản cần bảo vệ. Việc thu hồi credential phải dựa trên credential ID và trạng thái ở RP.

## 12. TOTP, push MFA và recovery code

### TOTP secret

Nếu TOTP seed bị lộ, attacker có thể tạo mã hợp lệ. Revoke binding cũ, tạo secret mới sau khi xác minh người dùng và kiểm tra các lần sử dụng bất thường. Không chỉ đổi mật khẩu rồi giữ TOTP secret đã lộ.

### Push authenticator

Nếu thiết bị push bị mất hoặc bị kiểm soát, thu hồi binding và kiểm tra các approval gần thời điểm compromise. Nếu có dấu hiệu MFA fatigue, xem xét login transaction, số push, deny/approve và risk context.

### Recovery code

Nếu recovery code bị lộ, consume/revoke toàn bộ bộ mã còn hiệu lực và cấp bộ mới sau khi xác minh. Trạng thái consumed phải cập nhật nguyên tử để chống hai lần dùng đồng thời. Không gửi bộ mã mới qua email hoặc chat.

### Không hạ assurance khi recovery

Nếu phương thức MFA chính bị compromise, không tự động fallback sang SMS/email yếu chỉ để khôi phục nhanh. Chọn bằng chứng độc lập theo risk và account sensitivity; với tài khoản đặc quyền, cần quy trình dual control hoặc xác minh bổ sung.

## 13. API key và client secret bị lộ

API key/client secret thường có thể được sử dụng ngay bởi bên nắm giữ. Khi phát hiện:

1. Xác định key ID, owner, scope, tenant, environment và consumer.
2. Kiểm tra usage log từ thời điểm sớm nhất có thể bị lộ.
3. Tạo key mới qua secret manager nếu cần duy trì dịch vụ.
4. Cập nhật consumer theo quy trình triển khai an toàn.
5. Xác minh consumer dùng key mới.
6. Revoke key cũ và kiểm tra verifier đã nhận trạng thái.
7. Rà soát key con, token exchange hoặc credential được tạo bằng key cũ.
8. Điều tra dữ liệu đã đọc, sửa, export hoặc xóa.

Không chỉ xóa key khỏi repository. Git history, fork, cache, build artifact, container image và log có thể vẫn chứa secret. Dùng secret scanning trên toàn bộ nơi có thể đã sao chép.

Với workload có nhiều consumer, rotation có thể dùng overlap ngắn có kiểm soát: cấp key mới, chuyển consumer, xác nhận, rồi revoke key cũ. Overlap phải có deadline, monitoring và không áp dụng nếu key cũ đang bị attacker sử dụng tích cực.

## 14. Certificate và private key bị lộ

Certificate công khai không phải secret; private key tương ứng mới là bí mật có thể cho phép ký, xác thực client hoặc giải mã tùy mục đích.

Nếu private key bị compromise:

- Xác định certificate serial, issuer, key usage, subject/SAN và relying parties.
- Revoke certificate tại CA theo PKI policy và công bố trạng thái qua CRL/OCSP hoặc cơ chế tương ứng.
- Tạo key pair mới; không tái sử dụng private key bị lộ.
- Issue certificate mới và cập nhật workload/client.
- Kiểm tra cache trust/revocation ở gateway và downstream.
- Rà soát chữ ký hoặc client authentication được thực hiện trong cửa sổ compromise.
- Nếu là CA signing key, kích hoạt quy trình incident PKI chuyên biệt và đánh giá toàn bộ certificate chain bị ảnh hưởng.

Nếu certificate hết hạn nhưng private key chưa bị lộ, sự cố có thể chỉ là vận hành. Nếu private key đã công khai, chờ hết hạn không đủ; phải xử lý revocation và downstream trust.

## 15. Token, session cookie và refresh token bị lộ

Bearer token/cookie có thể cho phép attacker truy cập mà không cần biết mật khẩu:

- Xác định token type, issuer, audience, scope, expiry và principal.
- Revoke token hoặc grant nếu hệ thống hỗ trợ.
- Revoke refresh token family để ngăn cấp token mới.
- Invalidate server-side session và security epoch khi cần.
- Kiểm tra token exchange, delegated grant và downstream session được tạo.
- Với JWT tự chứa, kiểm tra resource server có introspection, denylist, version check hoặc expiry ngắn không.
- Kiểm tra cache revocation và propagation ở mọi region.

Xóa cookie trên thiết bị người dùng không vô hiệu hóa bản sao attacker đã lấy. Logout server-side và revocation phải diễn ra tại authority/resource server. Với sender-constrained token, vẫn kiểm tra khóa ràng buộc và trạng thái credential; proof-of-possession không thay thế xử lý key compromise.

## 16. Phạm vi ảnh hưởng và lateral movement

Một credential có thể là điểm khởi đầu cho nhiều đường truy cập. Điều tra cần mở rộng theo quan hệ:

- Account và tenant sở hữu credential.
- Session và refresh token family được tạo.
- API key, certificate hoặc workload identity khác được cấp.
- Passkey/MFA/recovery method được thêm hoặc thay đổi.
- OAuth grant, federation link và delegated permission.
- Role, group, service account và privilege escalation.
- Resource, data set hoặc tenant đã bị truy cập.
- CI/CD pipeline, repository, artifact và secret store nơi key xuất hiện.

Đừng dừng điều tra ở credential đầu tiên. Attacker có thể tạo persistence bằng cách thêm passkey, đổi email recovery, tạo API key mới hoặc cấp OAuth consent. Hãy tìm hành động sau thời điểm compromise và thu hồi cả đường truy cập phát sinh.

## 17. Phân tích timeline và xác định thời gian phơi lộ

Thời gian bắt đầu exposure có thể sớm hơn thời điểm phát hiện:

1. Xác định lần đầu secret được tạo hoặc ghi vào nguồn.
2. Tìm commit, artifact, backup, log hoặc bản sao đầu tiên.
3. Xác định thời điểm repository/storage trở nên public hoặc quyền truy cập thay đổi.
4. Tìm lần đầu có thể bị crawl/download.
5. Tìm các lần sử dụng credential và hoạt động sau xác thực.
6. Xác định thời điểm containment có hiệu lực trên từng verifier.
7. Xác nhận không còn session/token hoặc credential con active trái phép.

Phân biệt occurred time, ingestion time và thời gian provider ghi nhận. Đồng hồ lệch và log đến trễ có thể làm timeline sai. Dùng correlation ID, event version và nhiều nguồn độc lập để xác minh.

## 18. Recovery và cấp lại credential

Sau containment, chỉ khôi phục khi có thể xác định trạng thái đáng tin:

- Xác minh danh tính qua phương thức độc lập còn tin cậy.
- Re-enroll credential mới trên thiết bị/secret store đã kiểm soát.
- Tạo key/secret mới bằng CSPRNG hoặc KMS/HSM phù hợp.
- Gắn credential với đúng principal, tenant, audience và scope.
- Kiểm tra enrollment proof và step-up khi cần.
- Thu hồi credential cũ, session và token liên quan.
- Kiểm tra recovery channel và federation link.
- Thông báo qua kênh đã xác minh trước đó.
- Theo dõi đăng nhập, token exchange và API usage sau recovery.

Không restore credential đã bị compromise từ backup. Backup có thể khôi phục metadata hoặc trạng thái cần thiết, nhưng secret bị lộ phải rotate/reissue. Với private key non-exportable, tạo key mới và cập nhật public key/certificate.

## 19. Truyền thông với người dùng và tổ chức

Thông báo sự cố cần chính xác, hữu ích và không tạo thêm rủi ro:

- Nêu loại hoạt động hoặc credential bị ảnh hưởng ở mức phù hợp.
- Hướng dẫn người dùng hành động qua ứng dụng/website chính thức.
- Không yêu cầu gửi password, OTP, recovery code hoặc token.
- Không đưa secret mới vào email/SMS.
- Nói rõ liệu người dùng cần reset password, re-enroll MFA hoặc revoke session.
- Cung cấp kênh hỗ trợ đã xác minh và cách báo cáo hoạt động lạ.
- Không khẳng định dữ liệu đã bị đánh cắp nếu chưa có bằng chứng.
- Phối hợp legal/privacy/compliance theo nghĩa vụ áp dụng.

Nếu credential của workload hoặc đối tác bị ảnh hưởng, thông báo owner kỹ thuật và các consumer cần rotate. Không công khai chi tiết có thể giúp attacker tái sử dụng key hoặc xác định hệ thống còn yếu.

## 20. Monitoring sau containment

Sau khi revoke/rotate, tiếp tục theo dõi:

- Thử sử dụng credential cũ.
- Login/token exchange từ session hoặc refresh family đã revoke.
- Credential mới được tạo ngoài quy trình.
- Thay đổi recovery channel, passkey hoặc MFA.
- API usage bất thường sau khi key cũ bị thu hồi.
- Access tới resource/tenant liên quan.
- Revocation propagation delay và cache stale.
- Lỗi dịch vụ do consumer chưa chuyển sang key mới.
- Các bản sao secret còn trong repository, artifact, log hoặc backup.

Không đóng incident ngay sau khi API báo revoke thành công. Xác minh mọi verifier và downstream service từ chối credential cũ, và hệ thống mới hoạt động bằng credential thay thế.

## 21. Mã giả: điều phối containment

Đây là mã giả khái niệm. Hành động thực tế phải đi qua authority có thẩm quyền và approval phù hợp:

~~~text
respondToCredentialLeak(finding):
    incident = openIncident(finding.source, finding.detectedAt)
    credential = resolveCredentialReference(finding.credentialRef)

    require credential.ownerIsKnown
    severity = assessSeverity(
        credential.type,
        credential.scope,
        exposureReachability,
        observedUsage,
        affectedPrincipals
    )

    preserveMinimalEvidence(
        sourceReference = finding.sourceReference,
        credentialReference = credential.auditReference,
        timestamps = finding.timestamps,
        accessEvents = collectRelevantAuditMetadata()
    )

    notifyIncidentCommander(incident, severity)
    require containmentApprovalIfPolicyRequires(severity)

    revokeOrSuspendAtAuthority(credential)
    revokeRelatedSessionsAndTokenFamilies(credential)
    invalidateDownstreamCachesAndGrants(credential)

    scope = investigateDerivedAccess(
        sessions = credential.relatedSessions,
        grants = credential.relatedGrants,
        credentialsCreatedAfterExposure = true,
        resourcesAccessed = true
    )

    rotateOrReissueCredential(credential)
    verifyOldCredentialRejectedEverywhere(credential)
    verifyReplacementWorksForAuthorizedConsumers()
    notifyVerifiedOwners(scope)
    monitorForOldCredentialReuseAndPersistence()
    documentEvidenceDecisionsAndLessons(incident)
~~~

Trong triển khai thật:

- Không truyền secret bản rõ vào incident object, log hoặc notification.
- Dùng credential reference và authority API có authorization.
- Có idempotency cho revoke/rotate để retry không tạo trạng thái mơ hồ.
- Ghi nhận trạng thái từng bước: requested, approved, executed, propagated và verified.
- Nếu revoke service không sẵn sàng, không tuyên bố containment hoàn tất.
- Phân biệt hành động tự động và hành động cần phê duyệt của con người.

## 22. Tình huống thực tế: API key production bị commit công khai

Một nhóm phát triển phát hiện API key production trong commit của repository public. Key thuộc service đồng bộ hồ sơ người dùng, có quyền đọc và cập nhật một số thuộc tính account. Commit được xóa khỏi nhánh chính nhưng vẫn còn trong lịch sử Git.

### Triage

1. Xác định key ID, owner, scope, tenant và tất cả consumer.
2. Xác định commit đầu tiên, thời gian public và các fork/cache có thể tồn tại.
3. Kiểm tra audit/API logs từ thời điểm phơi lộ.
4. Tìm request từ nguồn lạ, volume bất thường, resource export và thay đổi account.
5. Xác định key có thể tạo token hoặc credential con hay không.

### Containment và recovery

1. Nếu có thể, tạo key mới trong secret manager và cập nhật consumer được kiểm soát.
2. Xác nhận consumer dùng key mới, sau đó revoke key cũ; nếu đang bị khai thác, ưu tiên revoke ngay và chấp nhận gián đoạn có kiểm soát.
3. Invalidate cache/API gateway credential state.
4. Tìm session, token hoặc credential được tạo bằng key cũ và thu hồi theo policy.
5. Rà soát dữ liệu đã đọc/sửa và các account bị ảnh hưởng.
6. Quét toàn bộ Git history, fork, CI logs, artifacts, container images và backup.
7. Xóa secret khỏi nguồn phát để tránh lặp lại, nhưng coi key cũ đã compromise cho tới khi revoke được xác minh.
8. Cập nhật secret scanning, pre-commit/CI controls và quyền repository.

### Tiêu chí đóng incident

- Key cũ bị từ chối ở mọi verifier.
- Consumer hợp lệ đã chuyển sang key mới.
- Không còn session/token hoặc credential con không rõ nguồn gốc.
- Đã xác định phạm vi dữ liệu và account bị truy cập.
- Các bản sao secret đã được xử lý theo khả năng và policy.
- Có bằng chứng, timeline, owner và hành động phòng ngừa.

## 23. Các lỗi ứng phó thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ xóa secret khỏi source | Bản sao trong history, fork, artifact vẫn dùng được. | Revoke/rotate trước, sau đó dọn các bản sao. |
| Chỉ đổi password | Session, refresh token, MFA hoặc passkey attacker thêm vẫn active. | Kiểm tra toàn bộ access path và revoke liên quan. |
| Không xác định scope key | Key thay thế có thể thiếu quyền hoặc quá quyền; bỏ sót consumer. | Inventory owner, scope, audience và consumer. |
| Revoke nhưng không kiểm tra propagation | Cache/downstream vẫn chấp nhận credential cũ. | Verify rejection tại mọi verifier. |
| Gửi secret qua ticket/chat | Tạo thêm bản sao và người có thể truy cập. | Dùng reference, secret manager và evidence vault. |
| Restore secret đã lộ từ backup | Credential compromise sống lại. | Reissue key/secret mới; giữ tombstone/revocation state. |
| Xóa log trước khi thu thập | Mất timeline và bằng chứng misuse. | Preserve metadata/evidence theo chain of custody. |
| Chờ có misuse mới xử lý key public | Attacker có thể sử dụng trước khi phát hiện. | Risk-based containment ngay khi leak được xác nhận. |
| Thu hồi mọi credential không phân biệt | Gián đoạn rộng, mất khả năng recovery. | Scope theo quan hệ và risk; có thứ tự ưu tiên. |
| Thông báo chứa link/token bí mật | Notification trở thành đường chiếm tài khoản. | Link chính thức, token one-time và không log URL. |
| Không tìm credential con/persistence | Attacker giữ quyền sau khi key gốc bị revoke. | Tìm session, grant, key mới, recovery và role changes. |

## 24. Kiểm thử playbook credential leak

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Password bị phishing | Reset qua luồng tin cậy; session/token và recovery changes được rà soát. |
| API key trong repository public | Key được xác định owner/scope, revoke/rotate và xác minh từ chối. |
| Refresh token bị lấy | Token family bị revoke; reuse và session downstream được điều tra. |
| Session cookie bị đánh cắp | Server-side session bị revoke; xóa cookie phía client không được coi là đủ. |
| TOTP secret bị lộ | Binding cũ bị revoke và secret mới được enroll sau xác minh. |
| Recovery code bị lộ | Bộ mã cũ bị consume/revoke nguyên tử; bộ mới cấp sau recovery. |
| Passkey device bị mất | Credential/binding cụ thể bị revoke; credential dự phòng dùng để re-enroll. |
| Private key certificate bị lộ | Certificate revoke, key pair mới và downstream trust cập nhật. |
| Secret bị lộ trong log/APM | Log access bị giới hạn, bản sao được xử lý, credential rotate và pipeline được sửa. |
| Attacker đã thêm passkey | Credential lạ, session, recovery và notification event được nối để điều tra. |
| Revoke service timeout | Incident chưa được đánh dấu contained; retry/alternate control được kích hoạt. |
| Cache vẫn active sau revoke | Alert propagation; verifier không được coi containment hoàn tất. |
| Consumer key rotation bị lỗi | Theo dõi consumer chưa chuyển; không để key cũ active vô thời hạn. |
| Snapshot backup cũ chứa key revoked | Tombstone/revocation state thắng; không restore key thành active. |
| Evidence export | Hash, provenance, owner và chain of custody được ghi. |
| Thông báo người dùng | Không chứa secret; gửi qua kênh đã xác minh và nội dung rõ ràng. |

### Diễn tập định kỳ

- Chạy tabletop exercise cho password, API key, passkey và certificate leak.
- Diễn tập revoke trên nhiều region và xác minh propagation.
- Thử key rotation khi một số consumer offline.
- Kiểm tra secret scanning trên Git history, artifacts, logs và backup.
- Đo thời gian detect, contain, rotate và verify.
- Rà soát false positive để không tạo rotation hàng loạt không cần thiết.
- Kiểm tra runbook, on-call, escalation và quyền truy cập evidence.

## 25. Checklist ứng phó credential leak

- [ ] Ghi incident ID, owner, thời điểm phát hiện và nguồn phát hiện.
- [ ] Xác định loại credential, principal, tenant, scope, audience và consumer.
- [ ] Phân biệt exposure, leak, compromise và misuse.
- [ ] Đánh giá severity theo khả năng truy cập và impact.
- [ ] Không đưa secret bản rõ vào chat, ticket, log hoặc notification.
- [ ] Bảo toàn audit metadata, source reference và chain of custody.
- [ ] Xác định thời điểm đầu tiên có thể bị truy cập, không chỉ thời điểm phát hiện.
- [ ] Suspend/revoke credential tại authority có thẩm quyền.
- [ ] Thu hồi session, refresh token family, grant và credential con liên quan.
- [ ] Kiểm tra propagation/cache tại mọi verifier và downstream service.
- [ ] Rotate/reissue key mới; không tái sử dụng secret đã compromise.
- [ ] Điều tra account, tenant, resource, data access và persistence.
- [ ] Kiểm tra recovery channel, passkey/MFA, federation link và role change.
- [ ] Thông báo qua kênh đã xác minh, không gửi secret.
- [ ] Xác minh consumer hợp lệ đã chuyển sang credential mới.
- [ ] Quét repository history, artifact, image, log, backup và fork.
- [ ] Theo dõi reuse của credential cũ và hành vi bất thường sau containment.
- [ ] Ghi nguyên nhân gốc, timeline, impact và hành động phòng ngừa.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao xóa API key khỏi repository chưa đủ xử lý credential leak?

**Gợi ý:** Secret có thể còn trong Git history, fork, artifact, cache hoặc đã bị sao chép. Phải revoke/rotate và xác minh verifier từ chối key cũ.

**Câu 2.** Đổi mật khẩu có tự thu hồi session đã được tạo trước đó không?

**Gợi ý:** Không mặc định. Cần session/token revocation hoặc security epoch theo policy và xác minh propagation.

**Câu 3.** Vì sao cần điều tra credential được tạo sau thời điểm leak?

**Gợi ý:** Attacker có thể tạo passkey, API key, OAuth grant hoặc recovery channel để duy trì persistence.

**Câu 4.** Khi private key của certificate bị lộ, có thể tiếp tục dùng key cũ sau khi cấp certificate mới không?

**Gợi ý:** Không. Cần key pair mới, revoke certificate cũ và cập nhật trust/revocation ở relying party.

**Câu 5.** Vì sao không nên gửi secret bản rõ trong incident ticket?

**Gợi ý:** Ticket có thể được chia sẻ, index, export và lưu lâu; nó tạo thêm bản sao và mở rộng số người có thể truy cập.

**Câu 6.** Khi nào có thể coi containment hoàn tất?

**Gợi ý:** Khi credential cũ bị từ chối ở mọi verifier, session/token liên quan được xử lý, consumer đã chuyển và không còn đường truy cập trái phép chưa được kiểm soát.

**Câu 7.** Backup có thể được dùng để khôi phục một API key đã lộ không?

**Gợi ý:** Không nên. Backup có thể khôi phục metadata, nhưng secret đã compromise cần rotate/reissue; revocation tombstone phải thắng snapshot cũ.

## 27. Ghi nhớ

**Credential leak là sự cố về quyền kiểm soát danh tính, không chỉ là một chuỗi bí mật xuất hiện sai chỗ.** Ứng phó cần xác định loại credential, owner, scope, thời gian phơi lộ và các đường truy cập phát sinh; bảo toàn chứng cứ; revoke/suspend tại authority; xử lý session, refresh token, grant, passkey, MFA và credential con; sau đó rotate/reissue và xác minh mọi verifier từ chối credential cũ. Không gửi secret qua ticket/chat, không coi xóa source là containment và không restore credential đã compromise từ backup. Incident chỉ có thể đóng khi phạm vi được đánh giá, quyền truy cập cũ đã bị vô hiệu hóa, hoạt động hợp lệ được khôi phục và nguyên nhân gốc có biện pháp phòng ngừa.
