# Containment

> **Chương:** Incident response  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Khoanh vùng sự cố xác thực để chặn khả năng tiếp tục chiếm tài khoản, sử dụng credential bị lộ hoặc lan truyền sang service khác; đồng thời bảo toàn bằng chứng, duy trì dịch vụ thiết yếu và xác minh biện pháp đã có hiệu lực.

## 1. Containment là gì?

**Containment (khoanh vùng)** là giai đoạn phản ứng sự cố nhằm giới hạn phạm vi và tác động của một sự cố đang diễn ra. Với hệ thống xác thực, mục tiêu là ngăn attacker tiếp tục dùng danh tính, credential, session, token, thiết bị hoặc workload đã bị chiếm; chặn đường di chuyển sang các hệ thống tin cậy khác; và tạo điều kiện để điều tra, loại bỏ nguyên nhân rồi khôi phục an toàn.

Ví dụ, đội bảo mật phát hiện một tài khoản nhân viên đăng nhập từ thiết bị lạ, tạo thêm phương thức MFA và truy cập dữ liệu nhạy cảm. Đổi password là chưa đủ: attacker có thể vẫn giữ session cookie, refresh token, passkey vừa đăng ký hoặc quyền truy cập qua ứng dụng OAuth đã được cấp. Containment cần xác định các đường truy cập đó, thu hồi hoặc cô lập chúng theo phạm vi, rồi xác minh mọi điểm thực thi đã từ chối credential cũ.

Containment không chỉ là khóa tài khoản. Một hành động quá hẹp có thể để attacker tiếp tục hoạt động; một hành động quá rộng có thể làm gián đoạn đăng nhập của toàn tổ chức, phá hủy bằng chứng hoặc khiến đội ứng cứu mất quyền truy cập quản trị. Vì vậy, quyết định khoanh vùng phải dựa trên bằng chứng, phạm vi ảnh hưởng, mức độ chắc chắn và hậu quả của từng lựa chọn.

### Kết quả học tập

Sau bài này, người học có thể:

- Giải thích mục tiêu và nguyên tắc của containment trong sự cố authentication.
- Xác định principal, credential, session, token, factor, workload và trust boundary bị ảnh hưởng.
- Chọn hành động khoanh vùng phù hợp với loại compromise.
- Thu hồi quyền truy cập trên nhiều node, region và dependency.
- Bảo toàn audit trail và bằng chứng phục vụ điều tra.
- Kiểm soát nguy cơ attacker quay lại qua recovery, OAuth grant hoặc credential khác.
- Duy trì dịch vụ thiết yếu trong khi giới hạn quyền truy cập.
- Xác minh containment đã có hiệu lực và ghi nhận điều kiện chuyển sang eradication/recovery.

## 2. Mục tiêu và nguyên tắc containment

Containment trong hệ thống xác thực cần đạt các mục tiêu:

1. **Stop active access:** chặn credential hoặc session đang bị lạm dụng.
2. **Limit blast radius:** ngăn principal bị chiếm truy cập thêm tenant, resource, application hoặc workload.
3. **Break persistence:** loại bỏ những đường truy cập attacker có thể duy trì sau khi password được đổi.
4. **Protect trust infrastructure:** bảo vệ IdP, signing key, federation configuration, directory, KMS/HSM và hệ thống cấp credential.
5. **Preserve evidence:** giữ log, token metadata, event timeline và trạng thái cấu hình cần điều tra.
6. **Maintain essential operations:** giữ hoạt động cần thiết bằng phương án có kiểm soát.
7. **Verify effectiveness:** kiểm tra credential đã bị chặn ở mọi nơi cần thiết.

### Nguyên tắc ra quyết định

- Hành động phải có owner, thời điểm, phạm vi và lý do rõ.
- Ưu tiên hành động có thể đảo ngược nếu mức độ rủi ro cho phép.
- Với compromise đang diễn ra hoặc nguy cơ lan rộng, có thể cần hành động khẩn cấp theo quyền đã được phê duyệt.
- Không xóa log, session record hoặc bằng chứng chỉ để làm sạch hệ thống.
- Không gửi thông tin điều tra chi tiết qua kênh attacker có thể đang kiểm soát.
- Không giả định một thao tác ở control plane đã được áp dụng ngay trên mọi data plane.
- Mỗi thay đổi cần có cách xác minh thành công và tiêu chí rollback.

## 3. Vị trí của containment trong incident response

Containment thường nằm sau triage ban đầu và trước eradication/recovery. Các giai đoạn có thể lặp lại khi xuất hiện bằng chứng mới.

~~~mermaid
flowchart LR
    A["Detect and report"] --> B["Triage and scope"]
    B --> C["Contain active access"]
    C --> D["Preserve and analyze evidence"]
    D --> E["Eradicate persistence and root cause"]
    E --> F["Recover services and identities"]
    F --> G["Monitor for recurrence"]
    G --> H["Lessons learned"]
    G -->|New evidence| B
~~~

Trong thực tế, bảo toàn bằng chứng và containment thường diễn ra song song. Nếu attacker đang truy cập hệ thống, đội ứng cứu không nên trì hoãn hành động khẩn cấp chỉ để hoàn tất mọi phân tích. Tuy nhiên, cần ghi lại trạng thái trước/sau và lưu bằng chứng có thể mất khi session hoặc workload bị chấm dứt.

Containment chưa chứng minh hệ thống sạch. Nó chỉ chứng minh các đường truy cập đã xác định được giới hạn theo biện pháp và phạm vi đã kiểm tra. Eradication phải xử lý persistence và nguyên nhân gốc; recovery đưa dịch vụ trở lại trạng thái vận hành an toàn.

## 4. Triage: xác định cái gì đang bị chiếm

Trước khi chọn hành động, xây dựng một bức tranh tối thiểu về sự cố.

### Các câu hỏi cần trả lời

- Principal nào bị ảnh hưởng: người dùng, quản trị viên, service account, workload hay partner?
- Credential nào có thể đã lộ: password, API key, access token, refresh token, session cookie, passkey, certificate hay private key?
- Attacker có thể đã tạo thêm factor, recovery method, OAuth grant hoặc session mới không?
- Những ứng dụng, tenant, resource và service nào đã được truy cập?
- Sự cố chỉ liên quan một account hay có dấu hiệu compromise IdP/directory?
- Thời điểm bắt đầu và lần hoạt động đáng ngờ gần nhất là khi nào?
- Có bằng chứng token replay, MFA fatigue, phishing, consent abuse hoặc lateral movement không?
- Các node/region nào có thể đang cache trạng thái credential hoặc public key cũ?
- Hành động nào có thể làm mất bằng chứng hoặc ảnh hưởng dịch vụ thiết yếu?

### Phân loại phạm vi

| Phạm vi | Ví dụ | Hướng containment ban đầu |
|---|---|---|
| Một user principal | Password/session của nhân viên bị lộ | Hạn chế account, thu hồi session và credential liên quan |
| Một privileged principal | Admin bị phishing hoặc MFA bypass | Cô lập quyền admin, kiểm tra thay đổi và các principal được quản lý |
| Một factor/credential | API key hoặc passkey cụ thể bị lộ | Thu hồi đúng credential và tìm cách truy cập thay thế |
| Một application/client | OAuth client bị lạm dụng | Disable client/grant hoặc giới hạn audience/scope |
| Một workload/service | Service credential bị lộ | Cô lập workload, rotate identity và secret |
| Identity provider/directory | IdP admin hoặc signing key bị compromise | Kích hoạt quy trình khẩn cấp ở trust infrastructure |
| Nhiều tenant/region | Token hoặc signing key dùng chung bị lộ | Containment diện rộng có phối hợp và kiểm chứng theo từng vùng |

Không thu hẹp phạm vi chỉ vì alert ban đầu chỉ nêu một user. Một principal bị chiếm có thể đã tạo credential khác hoặc truy cập vào nhiều service.

## 5. Ma trận quyết định containment

Hành động phụ thuộc mức độ chắc chắn và hậu quả:

| Tình huống | Hành động có thể phù hợp | Điều cần kiểm tra |
|---|---|---|
| Dấu hiệu yếu, chưa có bằng chứng compromise | Tăng giám sát, step-up, giới hạn tạm thời | Có false positive hoặc hành vi hợp lệ không? |
| Một credential có bằng chứng bị lộ | Revoke credential, chặn sử dụng mới | Credential khác hoặc session liên quan có tồn tại không? |
| Account takeover đang diễn ra | Suspend account, revoke session/token, bảo vệ recovery | Attacker còn đường truy cập nào? |
| Privileged account bị chiếm | Tạm đình chỉ quyền đặc quyền, bảo vệ admin plane | Có thay đổi role, key, IdP config không? |
| Service credential bị lộ | Revoke/rotate, isolate workload, giới hạn network | Downstream service và secret phụ thuộc nào bị ảnh hưởng? |
| Signing key/IdP bị compromise | Emergency trust rotation, distrust key/issuer theo kế hoạch | Cache, federation partner và token đã phát hành còn được chấp nhận ở đâu? |
| Chưa rõ phạm vi, nguy cơ lan rộng cao | Segmentation hoặc chặn đường truy cập có rủi ro cao | Duy trì kênh ứng cứu và dịch vụ tối thiểu thế nào? |

Một quyết định tốt nêu rõ: bằng chứng, confidence, risk, hành động, phạm vi, owner, thời hạn và tiêu chí kết thúc. Không biến mọi cảnh báo login thành khóa account tự động không có cơ chế review.

## 6. Containment cho tài khoản người dùng bị chiếm

Khi có bằng chứng account takeover, mục tiêu là ngăn attacker tiếp tục sử dụng principal và các đường truy cập gắn với principal đó.

### Các bước thường cần

1. Ghi nhận principal reference, thời điểm, alert và hoạt động đáng ngờ.
2. Suspend hoặc đặt account vào trạng thái hạn chế theo incident policy.
3. Thu hồi toàn bộ session đang hoạt động, gồm web/mobile và phiên ở các region.
4. Thu hồi refresh token, authorization grant hoặc application session có thể tiếp tục cấp access.
5. Đánh giá access token tự chứa còn hiệu lực; dùng introspection, denylist, session version hoặc cơ chế chặn tương đương nếu kiến trúc hỗ trợ.
6. Kiểm tra factor/recovery method vừa được thêm hoặc thay đổi; tạm đình chỉ yếu tố đáng ngờ.
7. Bảo vệ email/phone recovery và các kênh liên kết có thể đã bị chiếm.
8. Kiểm tra role, group membership, delegated access và OAuth consent được tạo trong khoảng sự cố.
9. Sau khi xác minh chủ tài khoản qua quy trình an toàn, reset credential và đăng ký lại factor nếu cần.
10. Theo dõi lần đăng nhập và yêu cầu recovery tiếp theo để phát hiện attacker quay lại.

### Đổi password không đủ

Password reset không tự động thu hồi:

- Session cookie đã phát hành.
- Refresh token và grant.
- Access token JWT còn trong lifetime.
- Passkey hoặc security key attacker đã thêm.
- Recovery code đã bị sao chép.
- OAuth application consent.
- API key hoặc credential được tạo trong account.
- Session của ứng dụng downstream.

Phải xác định session/token architecture và gọi đúng cơ chế revoke cho từng loại. Không báo containment hoàn tất chỉ vì password đã đổi.

## 7. Containment cho password và credential bị lộ

Password có thể bị lộ qua phishing, credential stuffing, malware, log, database hoặc thiết bị bị chiếm.

### Hành động

- Đánh dấu credential bị compromise và yêu cầu đổi password qua kênh đáng tin cậy.
- Chặn password đã biết bị lộ theo password blocklist nếu phù hợp.
- Thu hồi session và refresh token liên quan.
- Kiểm tra password reuse trong các tài khoản khác chỉ qua quy trình bảo mật được phép; không thử đăng nhập vào dịch vụ bên ngoài.
- Kiểm tra MFA/recovery factor, OAuth grant và thay đổi account profile.
- Xác minh password reset không bị attacker kiểm soát qua email hoặc phone recovery.
- Nếu có dấu hiệu database/verifier exposure, bảo vệ kho credential, đánh giá hash parameters và chuẩn bị reset diện rộng theo incident plan.

Không gửi password mới hoặc reset link qua kênh không xác minh. Helpdesk không được yêu cầu người dùng đọc OTP hoặc recovery code cho nhân viên hỗ trợ.

### Credential stuffing diện rộng

Nếu nhiều account bị thử bằng credential rò rỉ:

- Áp dụng rate limit, bot mitigation và risk-based step-up.
- Chặn pattern theo nguồn và tốc độ, tránh chỉ dựa trên một IP.
- Ưu tiên bảo vệ privileged account và tài khoản có quyền nhạy cảm.
- Xác định account có login success đáng ngờ sau chuỗi failure.
- Yêu cầu reset/step-up có mục tiêu theo bằng chứng, tránh khóa hàng loạt thiếu căn cứ.
- Theo dõi tỷ lệ success của nguồn đáng ngờ và hoạt động sau login.

## 8. Containment cho session và token bị đánh cắp

Session và bearer token là credential có thể được dùng lại bởi bất kỳ ai sở hữu chúng.

### Session cookie

- Revoke session ID phía server.
- Invalidate session store entry và cache liên quan.
- Tăng session version hoặc authentication epoch nếu ứng dụng hỗ trợ.
- Xóa cookie ở browser là bước vệ sinh client; không thay thế server-side revocation.
- Thu hồi session của các ứng dụng downstream nếu chúng có session riêng.
- Kiểm tra session fixation hoặc XSS có thể đã làm lộ session.

### Refresh token

- Revoke refresh token family hoặc grant bị compromise.
- Nếu có rotation, kiểm tra reuse detection và revoke family theo policy.
- Xác minh client/application sở hữu token.
- Xem xét thu hồi consent hoặc authorization grant nếu attacker có thể tự cấp lại token.

### Access token dạng JWT

JWT tự chứa thường không thể bị xóa khỏi mọi nơi sau khi phát hành. Việc rotate signing key không tự động làm JWT cũ vô hiệu nếu resource server vẫn tin public key cũ.

Các biện pháp có thể gồm:

- Dùng access token lifetime ngắn theo threat model.
- Kiểm tra denylist theo token ID hoặc principal/session version khi cần emergency revocation.
- Dùng introspection hoặc token status service nếu kiến trúc hỗ trợ.
- Từ chối key ID/issuer bị compromise tại verifier và gateway.
- Thu hồi refresh token để ngăn cấp token mới.
- Cô lập resource server chưa nhận policy thu hồi.

Phải kiểm tra cache và mọi resource server. Nếu một region vẫn chấp nhận token cũ, containment chưa có hiệu lực toàn cục.

### Opaque token

Với opaque token, revoke tại authorization server/introspection store có thể có hiệu lực nhanh hơn, nhưng cache của resource server vẫn có thể giữ trạng thái active. Kiểm tra TTL và invalidation thực tế.

## 9. Containment cho MFA, passkey và recovery factor

Attacker có thể duy trì quyền truy cập bằng cách thêm factor của họ, đánh cắp seed, chiếm thiết bị hoặc lạm dụng helpdesk recovery.

### TOTP và push MFA

- Tạm đình chỉ factor có dấu hiệu bị chiếm.
- Thu hồi seed/credential cũ và đăng ký lại qua quy trình proofing phù hợp.
- Thu hồi recovery code đã lộ; phát bộ mới sau khi xác minh.
- Chặn push challenge bất thường và điều tra MFA fatigue.
- Không chỉ reset password trong khi attacker vẫn kiểm soát authenticator.

### Passkey/WebAuthn

- Liệt kê credential được đăng ký trong khoảng thời gian sự cố.
- Thu hồi credential ID đáng ngờ theo account record và authenticator registry.
- Kiểm tra thay đổi thiết bị, recovery và đồng bộ passkey nếu hệ sinh thái cung cấp tín hiệu.
- Yêu cầu proof-of-control phù hợp trước khi đăng ký passkey mới.
- Không xóa mọi passkey của tổ chức nếu chỉ một credential bị compromise mà chưa có bằng chứng rộng hơn.

### Recovery method

- Xác minh email/phone recovery chưa bị attacker kiểm soát.
- Thu hồi recovery code và reset token còn hiệu lực.
- Đặt cooldown hoặc step-up cho thay đổi recovery method.
- Review yêu cầu helpdesk reset factor gần thời điểm compromise.
- Gửi thông báo qua kênh đã xác minh về factor đã bị thu hồi/thay đổi.

Recovery là một đường authentication khác. Nếu không khoanh vùng recovery, attacker có thể lấy lại quyền truy cập sau khi đội ứng cứu đã revoke session.

## 10. Containment cho OAuth/OIDC và federation

Federation có thể tạo đường truy cập giữa nhiều ứng dụng và tổ chức. Một account bị chiếm có thể đã cấp consent cho ứng dụng độc hại hoặc liên kết identity sai.

### Kiểm tra và hành động

- Revoke authorization grant và refresh token của client đáng ngờ.
- Disable OAuth client hoặc integration nếu client secret/private key bị lộ.
- Thu hồi consent bất thường và kiểm tra scope đã cấp.
- Kiểm tra redirect URI, federation metadata, issuer trust và signing key.
- Kiểm tra identity linking mới, đặc biệt liên kết dựa trên email hoặc thuộc tính không ổn định.
- Kiểm tra service provider đã tạo session downstream từ IdP bị ảnh hưởng.
- Nếu IdP compromise, phối hợp từng relying party để chặn issuer/key theo kế hoạch.

### Không nhầm logout với revoke

Logout tại một ứng dụng thường chỉ kết thúc session cục bộ. Nó không tự động revoke refresh token, consent, session ở ứng dụng khác hoặc token đã phát hành. Containment cần kiểm tra từng loại trạng thái.

## 11. Containment cho API key, client secret và service credential

Service credential thường có quyền truy cập rộng, được lưu trong CI/CD, secret manager, container, function hoặc cấu hình triển khai.

### Hành động

1. Xác định key ID, owner, application, environment, scope và dependency.
2. Revoke key/secret bị lộ hoặc giảm quyền ngay theo incident plan.
3. Cấp credential mới qua secret manager hoặc workload identity.
4. Triển khai thay thế cho consumer hợp lệ theo thứ tự đã kiểm soát.
5. Kiểm tra key cũ bị từ chối ở mọi gateway, region và service.
6. Tìm bản sao trong source repository, build log, artifact, environment variable, ticket và telemetry.
7. Kiểm tra request được thực hiện bằng credential đó trong khoảng compromise.
8. Thu hồi credential downstream mà key bị lộ có thể dùng để tạo.

### Tránh rotation không có kiểm chứng

Tạo key mới không đồng nghĩa key cũ đã bị vô hiệu. Cần xác minh revoke state, propagation, cache, consumer cũ và fallback config. Không để key cũ tiếp tục hoạt động vô thời hạn chỉ để tránh sửa client.

Với workload identity, có thể cô lập workload hoặc workload pool, thu hồi certificate/token, cập nhật trust policy và triển khai lại workload từ image/config đã xác minh.

## 12. Containment cho certificate và signing key

Certificate và signing key có thể tạo trust ở quy mô lớn. Compromise private key của một issuer có thể ảnh hưởng nhiều principal và service.

### Client certificate/mTLS

- Xác định certificate, subject/SAN, issuer, serial và workload owner.
- Revoke certificate qua CRL/OCSP hoặc trust mechanism được triển khai.
- Cập nhật trust bundle/deny policy ở verifier.
- Xoay certificate mới cho workload hợp lệ.
- Kiểm tra TLS termination, proxy và backend có cache trạng thái cũ không.
- Cô lập workload nếu chưa thể revoke đồng bộ.

### Token signing key/JWT issuer

1. Xác định key ID, thuật toán, issuer và khoảng thời gian key có thể bị lộ.
2. Ngừng sử dụng private key bị compromise để ký token mới.
3. Phát hành key mới qua quy trình bảo vệ, publish public key đã xác minh.
4. Cập nhật verifier để từ chối key ID bị compromise theo emergency policy.
5. Thu hồi hoặc hạn chế token đã ký bằng key cũ.
6. Kiểm tra JWKS cache, gateway, mobile/backend verifier và federation partner.
7. Điều tra quyền truy cập vào KMS/HSM, backup và pipeline ký.

Không chỉ xóa key khỏi JWKS rồi giả định mọi verifier đã cập nhật. Verifier có thể cache key cũ hoặc dùng stale configuration. Cần đo và xác nhận propagation.

### Phạm vi issuer compromise

Nếu issuer hoặc IdP signing key bị compromise, có thể phải xem mọi token trong khoảng thời gian liên quan là không đáng tin. Phạm vi cần dựa trên key exposure, audit, token lifetime, issuer usage và downstream trust. Phối hợp với relying party trước khi thay đổi diện rộng để tránh tạo outage kéo dài.

## 13. Containment cho Identity Provider và directory

IdP là trust anchor cho nhiều ứng dụng. Compromise tài khoản quản trị IdP, federation config hoặc signing key có thể làm mất tin cậy ở diện rộng.

### Hành động khẩn cấp

- Cô lập hoặc đình chỉ privileged admin principal bị compromise.
- Thu hồi session, refresh token và grant của admin.
- Kiểm tra role assignment, conditional access, MFA policy và authentication method policy vừa thay đổi.
- Kiểm tra ứng dụng OAuth, service principal, client secret và federation trust mới được tạo.
- Bảo vệ tài khoản break-glass và kênh quản trị độc lập.
- Đánh giá directory sync, group membership và account lifecycle changes.
- Nếu signing key bị ảnh hưởng, thực hiện key containment và phối hợp verifier.
- Tạm giới hạn federation hoặc token issuance theo phạm vi cần thiết.

### Giữ kênh ứng cứu độc lập

Đội ứng cứu không nên phụ thuộc hoàn toàn vào IdP đang bị nghi compromise để đăng nhập vào công cụ điều tra hoặc khôi phục. Cần có break-glass access đã được kiểm soát, danh tính cá nhân, xác thực mạnh, phê duyệt, giám sát và kiểm tra định kỳ.

Không dùng tài khoản chia sẻ không audit. Không lưu secret break-glass trong cùng nơi hoặc cùng trust boundary đang bị điều tra.

## 14. Containment ở workload và network boundary

Nếu attacker đã dùng credential để truy cập service, chỉ revoke credential ở IdP có thể chưa chặn process đang chạy hoặc connection đã mở.

Biện pháp:

- Cô lập workload khỏi network hoặc dependency nhạy cảm theo segmentation policy.
- Chặn egress tới endpoint bất thường.
- Giới hạn service-to-service route và audience.
- Thu hồi workload certificate/token và rotate secret.
- Dừng job/worker đang chạy nếu có bằng chứng bị điều khiển.
- Giữ snapshot, memory/disk evidence theo quy trình forensics khi cần.
- Triển khai workload mới từ image/config đã xác minh.
- Kiểm tra service mesh, sidecar, gateway và proxy có giữ credential cache hay connection pool không.

Network isolation có thể làm mất khả năng thu thập bằng chứng hoặc gián đoạn xử lý nghiệp vụ. Cần chọn mức cô lập dựa trên mức độ compromise và yêu cầu bảo toàn dữ liệu.

## 15. Bảo toàn bằng chứng trong khi khoanh vùng

Containment phải hạn chế thiệt hại nhưng không được phá hủy khả năng điều tra.

### Thu thập trước hoặc đồng thời khi có thể

- Authentication/security audit events.
- Login, MFA, session issuance/revocation và recovery events.
- Token metadata cần thiết như issuer, audience, key ID, token ID đã pseudonymize; không lưu raw token.
- IdP/admin configuration changes.
- Group, role, consent và federation changes.
- API key/certificate issuance, rotation và revocation history.
- Gateway, WAF, DNS, network flow và workload logs.
- KMS/HSM audit và secret manager access.
- Host time synchronization state và clock offset.
- Incident timeline, operator action và approval record.

### Bảo toàn

- Ghi timestamp UTC, source, collector, owner và cách thu thập.
- Giữ bản gốc hoặc bản sao bất biến theo chính sách evidence.
- Kiểm soát quyền truy cập và ghi lại mọi lần xem/xuất dữ liệu.
- Dùng hash/checksum để kiểm tra tính toàn vẹn của bản evidence khi phù hợp.
- Ghi rõ dữ liệu nào chưa có, bị mất hoặc đã bị overwrite.
- Không chụp màn hình hoặc export chứa token/secret rồi đưa vào ticket thông thường.

Nếu phải revoke ngay để ngăn attacker, hãy ghi trạng thái credential/session và thời điểm trước/sau nếu có thể. Không trì hoãn containment nguy cấp chỉ vì chưa thu thập được mọi log.

## 16. Ngăn attacker quay lại

Sau khi chặn đường truy cập đã biết, cần tìm và loại bỏ persistence:

- Factor, passkey, recovery email/phone hoặc recovery code mới.
- Refresh token family, OAuth consent và application grant.
- API key, client secret, service account hoặc workload identity mới.
- Role/group assignment, privileged account hoặc admin consent bất thường.
- Federation trust, redirect URI, signing key hoặc certificate mới.
- Session downstream và token exchange/delegation grant.
- Scheduled job, automation, deployment pipeline hoặc script có thể tự cấp lại credential.
- Email forwarding rule hoặc mailbox session nếu email là recovery channel.
- Helpdesk ticket hoặc quy trình reset MFA bị lạm dụng.

Không kết thúc containment khi chỉ thấy login bất thường đã dừng. Cần xác định attacker còn khả năng tái tạo credential hoặc nhận recovery notification hay không.

## 17. Duy trì dịch vụ và tránh containment quá mức

Một biện pháp containment có thể ảnh hưởng đến nhiều người dùng và hệ thống phụ thuộc. Hãy chọn phạm vi nhỏ nhất vẫn chặn được rủi ro đã xác định.

### Các lựa chọn

- Revoke một credential cụ thể thay vì disable toàn bộ principal khi các factor khác vẫn đáng tin.
- Suspend một privileged role thay vì khóa toàn bộ account nếu cần giữ khả năng điều tra.
- Cô lập một workload/tenant/region khi có thể chứng minh ranh giới.
- Tăng step-up hoặc giảm scope tạm thời khi dấu hiệu rủi ro chưa đủ để revoke toàn bộ.
- Giữ read-only mode cho chức năng nghiệp vụ trong khi tạm dừng thao tác nhạy cảm.
- Dùng break-glass được kiểm soát để duy trì quản trị và khôi phục.

### Khi nào cần containment diện rộng?

- Signing key hoặc issuer trust bị compromise.
- IdP admin plane không còn đáng tin.
- Nhiều tenant/region cùng chấp nhận credential giả.
- Attacker có khả năng cấp token/role mới ở quy mô lớn.
- Không thể xác định phạm vi credential bị lộ và nguy cơ lan rộng rất cao.

Containment diện rộng cần incident commander, owner của hệ thống phụ thuộc, kế hoạch truyền thông và thứ tự phục hồi. Ghi lại lý do chọn phạm vi rộng và tiêu chí để thu hẹp.

## 18. Truyền thông trong giai đoạn containment

Thông tin sự cố cần đi qua kênh được xác minh và chỉ tới người cần biết.

Thông điệp nội bộ nên nêu:

- Hệ thống hoặc nhóm principal bị ảnh hưởng.
- Hành động người dùng cần làm, nếu có.
- Dịch vụ nào đang bị giới hạn.
- Kênh hỗ trợ chính thức.
- Thời điểm cập nhật tiếp theo.

Không gửi raw IOC, credential, token, tên account đặc quyền hoặc chi tiết kỹ thuật nhạy cảm qua kênh rộng. Không thông báo cho attacker biết chính xác detection rule hoặc cách né containment.

Với người dùng bị ảnh hưởng, hướng dẫn rõ cách đổi credential, xác minh factor và nhận biết thông báo hợp lệ. Không yêu cầu họ gửi password, OTP, private key hoặc recovery code cho đội hỗ trợ.

## 19. Xác minh containment đã có hiệu lực

Một thao tác API trả success không chứng minh mọi verifier đã ngừng chấp nhận credential cũ.

### Kiểm tra theo lớp

1. **Control plane:** trạng thái account, key, grant hoặc certificate đã chuyển đúng.
2. **Propagation:** mọi region, replica, cache và downstream đã nhận thay đổi.
3. **Data plane:** request thử với credential bị revoke bị từ chối ở từng resource server.
4. **Persistence:** attacker không còn factor, recovery path, consent hoặc credential thay thế.
5. **Monitoring:** không còn access thành công từ principal/credential đã bị chặn; alert mới được xử lý.
6. **Service health:** chức năng hợp lệ vẫn hoạt động theo phạm vi duy trì đã thống nhất.

### Kiểm thử có kiểm soát

- Dùng credential test đã revoke, không dùng lại secret thật trong test log.
- Thử từ nhiều region và client path.
- Kiểm tra session/token cũ, refresh token và grant.
- Kiểm tra JWKS/cache và certificate trust propagation.
- Xác minh account/factor không thể tự khôi phục bằng recovery path đã bị chiếm.
- Kiểm tra alert khi có request dùng credential cũ.

Không gửi credential bị compromise vào hệ thống bên ngoài để thử. Dùng môi trường và endpoint kiểm thử được phê duyệt.

## 20. Tiêu chí kết thúc containment

Chỉ chuyển sang eradication/recovery khi có bằng chứng đủ cho phạm vi đã xác định:

- Credential/session đang bị lạm dụng đã bị chặn hoặc cô lập.
- Đường cấp lại credential đáng ngờ đã bị giới hạn.
- Quyền và grant mới phát sinh trong khoảng sự cố đã được review.
- Trust infrastructure liên quan có biện pháp bảo vệ tạm thời.
- Evidence cần thiết đã được giữ và có owner.
- Các node/region/downstream cần thiết đã xác nhận policy thu hồi.
- Dịch vụ thiết yếu có trạng thái vận hành rõ.
- Rủi ro còn lại, giả định và giới hạn containment được ghi nhận.
- Incident commander hoặc owner có thẩm quyền chấp thuận bước tiếp theo.

Containment không yêu cầu mọi nguyên nhân gốc đã được loại bỏ. Việc đó thuộc eradication. Nhưng phải có đủ kiểm soát để attacker không thể tiếp tục sử dụng đường truy cập đã biết trong khi đội ứng cứu xử lý nguyên nhân.

## 21. Tình huống thực hành: tài khoản quản trị bị chiếm

**Bối cảnh:** Một quản trị viên nhận nhiều push MFA, cuối cùng chấp thuận một prompt không do mình khởi tạo. Sau đó có login từ vị trí bất thường, một passkey mới được đăng ký và một OAuth application được cấp quyền đọc dữ liệu.

### Kế hoạch containment

1. Mở incident, chỉ định incident commander và lưu mốc thời gian.
2. Suspend privileged principal hoặc tạm bỏ role admin theo emergency procedure.
3. Revoke tất cả session, refresh token và grant có liên quan.
4. Chặn passkey mới và factor/recovery change đáng ngờ.
5. Revoke OAuth consent/client grant mới, kiểm tra scope và token đã phát hành.
6. Kiểm tra các thay đổi IdP admin, role, group, federation và ứng dụng trong khoảng sự cố.
7. Xác minh email/phone recovery và mailbox session không bị chiếm.
8. Thu thập audit, sign-in log, MFA events, token metadata và admin activity.
9. Kiểm tra các relying party và downstream app đã tạo session từ IdP.
10. Xác minh request dùng session/token cũ bị từ chối trên mọi region.
11. Sau proofing độc lập, reset password, đăng ký factor mới và cấp lại role qua approval.
12. Theo dõi login, consent và factor changes để phát hiện tái xâm nhập.

### Vì sao chỉ đổi password là chưa đủ?

Attacker có thể vẫn giữ session cookie, refresh token, passkey mới hoặc OAuth grant. Nếu email cũng bị chiếm, attacker có thể reset password lần nữa. Containment phải xử lý mọi đường duy trì quyền truy cập, không chỉ credential đầu tiên.

## 22. Mẫu incident containment record

Ví dụ JSON minh họa một record hành động. Không đưa raw credential hoặc secret vào record.

~~~json
{
  "incident_id": "IR-2026-0142",
  "action_id": "ACT-003",
  "action_type": "revoke_sessions",
  "scope": {
    "principal_ref": "pseudonymous-7f31",
    "applications": ["admin-portal", "reporting-api"],
    "regions": ["region-a", "region-b"]
  },
  "reason": "suspected_account_takeover",
  "owner": "identity-response",
  "approved_by": "incident-commander",
  "started_at": "2026-11-22T09:15:00Z",
  "completed_at": "2026-11-22T09:17:30Z",
  "verification": {
    "old_session_rejected": true,
    "refresh_token_revoked": true,
    "downstream_confirmed": true
  },
  "status": "contained"
}
~~~

Record thực tế cần được lưu trong incident system có access control, retention và audit phù hợp. Các giá trị trong ví dụ chỉ là dữ liệu giả lập.

## 23. Kiểm thử containment

Kiểm thử trong tabletop, lab hoặc môi trường được phép với credential giả lập:

| Tình huống | Kết quả mong đợi |
|---|---|
| User account bị takeover | Account/session bị hạn chế theo policy |
| Chỉ đổi password nhưng session cũ còn | Test phát hiện session chưa bị revoke |
| Refresh token bị lộ | Token family/grant bị thu hồi theo policy |
| JWT cũ sau signing key rotation | Verifier từ chối key/credential bị compromise theo emergency policy |
| Một region chưa nhận revoke | Containment chưa được đánh dấu toàn cục |
| Passkey lạ được thêm | Credential bị review và thu hồi sau xác minh |
| Recovery email bị chiếm | Recovery channel được cô lập và xác minh lại |
| OAuth consent bất thường | Grant/client bị revoke và scope được điều tra |
| API key bị lộ | Key cũ bị từ chối ở mọi gateway/region |
| Client certificate bị compromise | Trust/deny policy áp dụng tại mọi verifier |
| Workload credential bị lộ | Workload được cô lập, credential mới được cấp qua trust path |
| IdP admin bị compromise | Admin plane và các thay đổi trust được kiểm tra |
| Signing key bị lộ | Issuer ngừng ký bằng key cũ và verifier chặn key đó |
| Directory lookup unavailable | Không fail-open hoặc cấp role từ dữ liệu chưa xác minh |
| Clock skew giữa các node | Revoke/expiry được kiểm tra theo policy thống nhất |
| Cache giữ trạng thái credential cũ | Invalidation/TTL được xác minh |
| Attacker tạo factor thay thế | Persistence path được phát hiện và thu hồi |
| Evidence collection đang diễn ra | Log và trạng thái cần thiết được giữ nguyên |
| Network isolation workload | Evidence được giữ và service impact được đánh giá |
| Break-glass access | Có owner, approval, expiry và audit |
| Containment diện rộng | Có incident commander, dependency owner và recovery sequence |
| Credential cũ được dùng lại | Request bị từ chối và detection tạo alert |

## 24. Checklist containment cho authentication incident

- [ ] Có incident owner/commander và scope được ghi nhận.
- [ ] Xác định principal, credential, factor, session, token và trust boundary bị ảnh hưởng.
- [ ] Xác định application, tenant, workload, region và downstream dependency.
- [ ] Ghi bằng chứng và timeline trước/sau hành động khi có thể.
- [ ] Chọn containment theo confidence, risk và service impact.
- [ ] Suspend/restrict principal bị chiếm theo incident policy.
- [ ] Revoke session cookie và server-side session ở mọi region.
- [ ] Revoke refresh token, grant, consent và downstream session liên quan.
- [ ] Đánh giá access token tự chứa và cơ chế emergency deny.
- [ ] Review passkey, MFA factor, recovery code và recovery channel mới.
- [ ] Rotate/revoke API key, client secret, certificate hoặc workload identity bị lộ.
- [ ] Nếu signing key/IdP bị compromise, phối hợp key/issuer containment với mọi verifier.
- [ ] Review role/group/federation/client changes trong khoảng sự cố.
- [ ] Bảo vệ email, helpdesk và các đường recovery có thể bị chiếm.
- [ ] Cô lập workload/network khi credential đã dẫn tới execution hoặc lateral movement.
- [ ] Bảo toàn audit, KMS/HSM, gateway, IdP và workload evidence.
- [ ] Không ghi raw token/password/OTP/private key vào incident record.
- [ ] Xác minh revoke propagation qua control plane, cache và data plane.
- [ ] Kiểm tra credential cũ bị từ chối ở mọi region/downstream.
- [ ] Duy trì break-glass và dịch vụ thiết yếu có kiểm soát.
- [ ] Theo dõi persistence, factor replacement và re-entry.
- [ ] Ghi rõ residual risk, tiêu chí kết thúc và phê duyệt chuyển giai đoạn.

## Ghi nhớ

Containment trong authentication incident phải chặn khả năng tiếp tục truy cập và ngăn attacker quay lại qua mọi đường credential liên quan. Đổi password hoặc khóa một account không đủ nếu session, refresh token, passkey, recovery method, OAuth grant, API key hoặc workload identity vẫn còn hiệu lực.

Chọn phạm vi theo bằng chứng và blast radius; bảo toàn audit/evidence; xác minh revoke propagation trên mọi node, cache và downstream; duy trì kênh ứng cứu độc lập. Chỉ chuyển sang eradication/recovery khi các đường truy cập đã biết được giới hạn, trạng thái còn lại được ghi nhận và owner có thẩm quyền chấp thuận.
