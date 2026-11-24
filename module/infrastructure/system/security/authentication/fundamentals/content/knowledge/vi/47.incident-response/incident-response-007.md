# Thu hồi credential sự cố — Ngăn credential bị lộ tiếp tục được sử dụng

Một nhân viên báo rằng laptop có thể đã bị malware đánh cắp cookie phiên và refresh token. Cùng lúc, hệ thống ghi nhận refresh token cũ được dùng lại từ một thiết bị khác, rồi xuất hiện một lần đăng nhập thành công. Đội vận hành cần ngăn kẻ tấn công tiếp tục truy cập, nhưng tài khoản còn nhiều credential: password, passkey, TOTP, recovery code, session cookie, access token, refresh token và certificate dùng cho API nội bộ. Chỉ đổi mật khẩu có thể không thu hồi các phiên đã cấp; chỉ revoke refresh token có thể không làm JWT access token tự mất hiệu lực; chỉ khóa tài khoản có thể không chặn workload credential đã bị sao chép.

**Thu hồi credential sự cố (incident credential revocation)** là quá trình vô hiệu hóa có kiểm soát các credential, token, phiên và quyền liên quan sau khi có dấu hiệu hoặc bằng chứng compromise. Mục tiêu là chặn khả năng tiếp tục xác thực/ủy quyền của attacker, giới hạn blast radius, giữ bằng chứng điều tra và khôi phục quyền truy cập cho chủ thể hợp lệ. Thu hồi cần theo loại credential, phạm vi ảnh hưởng và khả năng lan truyền trạng thái giữa các hệ thống; một thao tác revoke ở một thành phần không có nghĩa mọi resource server đã ngừng chấp nhận credential đó.

Bài học thuộc chương **Incident response** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối thu hồi credential với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập; đồng thời thiết kế quy trình containment, rotation, revocation, verification và recovery có thể kiểm chứng.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt disable, revoke, expire, rotate, replace, unlink và delete credential.
- Xác định trigger và phạm vi cần thu hồi trong một authentication incident.
- Lập inventory liên kết principal, credential, session, token family, device, workload và downstream resource.
- Chọn thứ tự containment phù hợp để ngăn attacker tiếp tục truy cập mà không phá hủy bằng chứng.
- Thu hồi password, MFA factor, passkey, recovery code, certificate, API key, access/refresh token và session.
- Giải thích giới hạn thu hồi JWT tự xác minh và thiết kế denylist, introspection, session epoch hoặc TTL phù hợp.
- Xử lý revocation propagation trong hệ thống phân tán, cache, replica, gateway và service mesh.
- Phối hợp revoke với rotation, re-enrollment, account recovery và thông báo người dùng.
- Thiết kế rollback/contingency khi revoke nhầm credential của workload hoặc tài khoản sản xuất.
- Xác minh credential cũ thực sự bị từ chối ở mọi validator liên quan.
- Viết runbook, audit evidence và tiêu chí kiểm thử cho incident credential revocation.

## 2. Thu hồi credential là gì và không phải là gì?

Credential là bằng chứng được dùng để xác thực hoặc tiếp tục quyền truy cập: password, passkey/private key, TOTP secret, recovery code, client certificate, API key, client secret, access token, refresh token hoặc session cookie. Khi credential bị lộ, attacker có thể sử dụng nó cho đến khi credential hết hiệu lực hoặc mọi điểm chấp nhận đã ngừng tin cậy nó.

Các thao tác thường bị nhầm lẫn:

| Thao tác | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Disable | Tạm ngăn credential/principal được dùng theo policy; có thể bật lại | Tạm khóa account đang điều tra |
| Revoke | Đánh dấu credential/grant/session không còn được chấp nhận | Revoke refresh token family |
| Expire | Credential tự hết hiệu lực theo thời gian đã định | Access token hết hạn |
| Rotate | Thay credential hiện tại bằng credential mới | Phát API key mới và retire key cũ |
| Replace/re-enroll | Đăng ký credential mới sau khi loại bỏ credential cũ | Xóa passkey bị nghi lộ rồi thêm passkey mới |
| Unlink | Gỡ quan hệ giữa external identity/device và account | Unlink IdP account không còn tin cậy |
| Delete/destroy | Xóa dữ liệu/khóa theo policy và retention | Hủy private key không còn cần |

Revoke không đồng nghĩa xóa ngay bản ghi. Giữ tombstone hoặc trạng thái revoked có thể cần thiết để validator từ chối credential cũ, audit truy vết và ngăn credential được nhập lại từ backup. Disable account cũng không tự động revoke mọi token, certificate hoặc API key đã phát hành cho account/workload.

### 2.1. Revoke khác rotate

Rotation tạo credential mới và chuyển hệ thống sang dùng nó. Revocation làm credential cũ mất quyền. Trong incident, thường phải làm cả hai: revoke credential bị lộ, sau đó cấp credential thay thế qua một quy trình đã xác minh. Nếu chỉ rotate mà không revoke bản cũ, attacker vẫn có thể tiếp tục sử dụng nó trong thời gian overlap.

### 2.2. Revoke khác logout

Logout thường kết thúc một session phía client/server theo flow thông thường. Incident revocation cần xử lý mọi session, refresh family, token, device và credential liên quan; đồng thời xác minh trạng thái đã lan tới resource server. Xóa cookie trên browser của người dùng không làm cookie đã bị sao chép mất hiệu lực.

## 3. Khi nào cần thu hồi credential?

Trigger có thể là:

- Người dùng báo mất thiết bị, nghi bị malware hoặc lộ mật khẩu.
- Phát hiện phishing, credential stuffing thành công hoặc account takeover.
- Refresh token reuse hoặc session hijacking được xác nhận.
- Private key, certificate, API key hoặc client secret bị đưa lên repository/log.
- Nhân viên nghỉ việc, vendor kết thúc hợp đồng hoặc workload bị decommission.
- Identity provider, KMS/HSM, secret manager hoặc signing key bị compromise.
- MFA/passkey/recovery method bị thay đổi ngoài ý muốn.
- Phát hiện quyền truy cập trái phép hoặc policy violation từ credential cụ thể.
- Credential vượt quá thời hạn, không còn owner hoặc không đáp ứng baseline.

Không phải mọi anomaly đều yêu cầu revoke toàn bộ account. Hãy đánh giá confidence, loại credential, quyền của principal, bằng chứng sử dụng trái phép và blast radius. Với credential có bằng chứng bị đánh cắp hoặc khóa ký bị lộ, containment cần nhanh và rộng tương xứng.

## 4. Mô hình phạm vi: từ principal tới mọi nơi chấp nhận credential

Một principal có thể có nhiều credential và một credential có thể cấp quyền tới nhiều resource. Trước khi revoke, cần xác định quan hệ:

~~~mermaid
flowchart TD
    P[Principal / workload identity] --> C[Credential inventory]
    C --> PW[Password]
    C --> MFA[MFA factors / passkeys]
    C --> CERT[Certificates / API keys]
    P --> S[Sessions]
    S --> AT[Access tokens]
    S --> RT[Refresh token families]
    C --> F[Federated identities / grants]
    AT --> R[Resource servers]
    RT --> AS[Authorization server]
    CERT --> M[Service mesh / APIs]
    F --> IDP[Identity providers]
~~~

### 4.1. Những câu hỏi phải trả lời

- Principal nào bị ảnh hưởng: một user, nhóm user, service account, tenant hay toàn tổ chức?
- Credential cụ thể nào bị lộ và có thể đã được copy ở đâu?
- Credential có thể tạo credential khác không, ví dụ refresh token hoặc signing key?
- Token/session nào đã được cấp từ credential đó?
- Những resource server, API gateway, service mesh hoặc ứng dụng nào chấp nhận nó?
- Có external identity, delegated grant, workload role hoặc recovery channel nào liên quan?
- Credential có được cache trong browser, mobile device, CI/CD, container image, backup hoặc replica không?
- Có credential dùng chung giữa nhiều principal không? Nếu có, phạm vi revoke có thể lớn hơn dự kiến.

### 4.2. Inventory phải đủ tin cậy

Inventory nên lấy từ identity provider, credential registry, session store, certificate authority, secret manager, API gateway và service owner. Một spreadsheet cũ hoặc danh sách do người dùng tự khai có thể bỏ sót credential orphaned. Nếu không biết một credential đã được phát hành ở đâu, không thể khẳng định incident đã được containment đầy đủ.

## 5. Quy trình xử lý thu hồi trong incident

Một quy trình có thể tổ chức thành các bước:

1. **Declare and scope:** xác nhận loại incident, principal/credential nghi bị ảnh hưởng và mức khẩn cấp.
2. **Preserve evidence:** lưu event/audit, token reference, certificate serial, thời điểm và nguồn phát hiện; không lưu thêm secret thô.
3. **Contain issuance:** ngăn attacker nhận credential mới hoặc refresh quyền từ credential bị compromise.
4. **Revoke active access:** revoke session, refresh family, token, key/certificate và grant liên quan.
5. **Propagate:** truyền trạng thái revoke tới IdP, gateway, resource server, cache và downstream validator.
6. **Verify denial:** thử credential cũ qua các điểm chấp nhận và xác nhận bị từ chối.
7. **Rotate and recover:** cấp credential mới qua kênh đã xác minh; khôi phục account/device/workload.
8. **Monitor:** theo dõi credential cũ, đăng nhập mới, recovery và hành vi sau containment.
9. **Close and learn:** ghi phạm vi, thời gian, ngoại lệ, bằng chứng và cải tiến.

Thứ tự có thể thay đổi theo incident. Nếu signing key hoặc identity provider bị compromise, cần containment authority trước khi tin các token mới. Nếu chỉ một session cookie bị lộ, có thể revoke session cụ thể và kiểm tra các credential đã dùng trong session đó.

### 5.1. Preserve evidence trước khi phá hủy

Ghi nhận credential reference, session/token family ID, certificate serial, key version, issuer, audience, thời gian và validator liên quan. Không sao chép password, OTP, bearer token hay private key vào ticket/chat. Nếu cần forensic capture, dùng quy trình evidence handling riêng, mã hóa và giới hạn người truy cập.

### 5.2. Containment không chờ phân tích hoàn hảo

Khi có bằng chứng rõ credential bị đánh cắp, ưu tiên ngăn attacker tiếp tục dùng credential đó. Có thể revoke trước khi biết toàn bộ blast radius, nhưng cần ghi rõ giả định và theo dõi tác động. Với thao tác có thể làm gián đoạn production diện rộng, phối hợp incident commander/service owner và dùng phương án containment theo từng scope nếu có thể.

## 6. Thu hồi password và credential liên quan

Password không phải token có trạng thái revoked ở mọi hệ thống. Cách thường dùng là vô hiệu hóa verifier cũ bằng password reset/credential version change và yêu cầu người dùng đặt password mới.

### Các bước

- Xác định account và password verifier có khả năng bị lộ.
- Yêu cầu reset qua recovery flow đã xác minh, hoặc đặt trạng thái password-reset-required.
- Tăng password credential version/revocation epoch nếu ứng dụng dùng cơ chế này.
- Thu hồi session/refresh token được cấp trước hoặc sau thời điểm compromise theo policy.
- Vô hiệu hóa reset link cũ và challenge đang chờ.
- Kiểm tra password reuse risk và khuyến nghị thay ở dịch vụ khác nếu người dùng dùng lại.
- Dùng password KDF hiện hành khi tạo verifier mới; không gửi password mới qua email/chat.

Đổi password không tự động kết thúc mọi session. Một số hệ thống chỉ kiểm tra password ở thời điểm login; access token đã phát hành có thể tiếp tục hợp lệ. Vì vậy cần kết hợp session/token revocation và validator policy.

## 7. Thu hồi MFA, passkey và recovery method

Một account takeover có thể bắt đầu từ password nhưng duy trì bằng MFA factor, passkey hoặc recovery method bị attacker thêm vào. Khi xử lý, kiểm tra toàn bộ authenticator chứ không chỉ yếu tố ban đầu.

### 7.1. TOTP và authenticator app

- Revoke/disable TOTP credential hoặc secret bị nghi lộ.
- Hủy challenge/session enrollment đang chờ.
- Yêu cầu đăng ký lại bằng flow đã xác minh.
- Không yêu cầu người dùng gửi seed hoặc mã TOTP cho support.
- Nếu secret backup/sync bị compromise, đánh giá mọi thiết bị chứa secret đó.

### 7.2. Push MFA và security key

- Thu hồi registration/device binding bị compromise.
- Kiểm tra push approval, deny, timeout và number-matching event.
- Gỡ authenticator chỉ sau khi có recovery path đủ tin cậy để tránh khóa chủ tài khoản.
- Yêu cầu re-enrollment từ thiết bị/kênh đã xác minh.
- Kiểm tra liệu attacker đã thêm factor riêng hay chưa.

### 7.3. Passkey/WebAuthn

Passkey thường là public-key credential gắn với RP ID và credential record. Server có thể disable/xóa credential record hoặc đánh dấu revoked theo policy; không thể xóa private key khỏi mọi thiết bị đồng bộ của người dùng. Hướng dẫn người dùng xóa passkey khỏi authenticator/device nếu thiết bị bị mất, đồng thời revoke credential phía server và các session đã tạo.

Kiểm tra credential ID, user handle, authenticator metadata và thời điểm đăng ký. Không dựa vào display name của thiết bị để quyết định credential nào cần revoke.

### 7.4. Recovery code và recovery channel

- Revoke toàn bộ recovery code set đã phát hành nếu nghi bị lộ.
- Tạo bộ code mới sau khi user được xác minh.
- Thu hồi reset token, email verification token và recovery challenge cũ.
- Xác minh email/phone/backup contact không bị attacker thay đổi.
- Kiểm tra support override, recovery request và identity proofing evidence.

Recovery method có thể là đường vào tài khoản mạnh hơn cả password. Nếu email chính bị chiếm, gửi reset link tới chính email đó không phải recovery độc lập.

## 8. Thu hồi session, access token và refresh token

### 8.1. Session

Session store nên hỗ trợ revoke theo session ID/reference, principal, device hoặc thời điểm. Khi session bị revoke, mọi request tiếp theo phải bị từ chối tại nơi kiểm tra session state. Nếu session state được cache, xác định TTL và propagation SLA.

Không ghi session cookie vào audit. Dùng opaque session reference để liên kết sự kiện.

### 8.2. Refresh token family

Refresh token rotation cần giữ trạng thái token family. Khi có dấu hiệu refresh token bị lộ:

- Revoke token đã bị lộ và các descendant trong family theo policy.
- Ngừng cấp access token mới từ family đó.
- Ghi reuse/compromise event.
- Xử lý retry hợp lệ nếu có operation ID/client binding đã xác minh.
- Kiểm tra session/device liên quan và các family khác cùng principal nếu cần.

Chỉ revoke refresh token không nhất thiết làm access token hiện tại mất hiệu lực.

### 8.3. Access token dạng JWT

JWT tự chứa claims có chữ ký thường được resource server xác minh offline. Issuer đánh dấu JWT revoked trong database không tự làm chữ ký mất hiệu lực. Các chiến lược:

- **Short TTL:** giới hạn thời gian token còn có thể dùng.
- **Introspection/reference token:** resource server hỏi authority về trạng thái token.
- **Denylist:** kiểm tra token ID/jti hoặc session reference bị revoke.
- **Revocation epoch:** token mang version/issued-at; resource server so với trạng thái principal/session.
- **Sender constraint:** DPoP/mTLS làm token bị copy riêng lẻ khó sử dụng từ client khác.

Chọn chiến lược theo latency, availability, privacy và mức độ khẩn cấp. Nếu API chỉ kiểm tra chữ ký/expiry và không tra revoke state, phải nói rõ JWT có thể còn hợp lệ tới khi hết hạn.

### 8.4. Refresh không được làm sống lại quyền đã revoke

Refresh endpoint phải kiểm tra account status, grant, token family, credential version và revocation state trước khi cấp token mới. Không chỉ kiểm tra chữ ký refresh token. Nếu principal bị disable hoặc session đã revoke, refresh phải bị từ chối theo policy.

## 9. Thu hồi certificate, API key và client secret

### 9.1. Certificate

- Xác định issuer/CA, serial number, SAN, subject và workload/service đang dùng certificate.
- Revoke certificate tại CA hoặc identity authority.
- Cập nhật CRL/OCSP/trust bundle theo cơ chế thực tế.
- Kiểm tra TLS terminator, gateway, service mesh và client có reload trạng thái không.
- Issue certificate mới với private key mới; không tái sử dụng key bị nghi lộ.
- Xác minh certificate cũ bị từ chối ở mọi validator liên quan.

Một số validator không kiểm tra OCSP/CRL realtime hoặc dùng cache dài. Khi đó cần trust bundle update, denylist serial, ngừng CA/issuer bị compromise hoặc giảm TTL theo kế hoạch. Revoke tại CA mà không kiểm tra validator có thể tạo cảm giác an toàn giả.

### 9.2. API key và client secret

- Disable key cũ ở API gateway/provider/service nhận key.
- Xác định mọi bản sao trong secret manager, CI/CD, environment, container image và backup.
- Tạo key mới riêng cho từng workload/client, scope hẹp và expiry phù hợp.
- Cập nhật consumer theo rollout có kiểm soát.
- Xác minh key cũ bị từ chối; theo dõi request còn dùng key cũ.
- Xóa bản sao không cần theo retention và evidence policy.

Nếu secret dùng chung giữa nhiều service, cần coi toàn bộ nhóm sử dụng là phạm vi ảnh hưởng. Tránh tiếp tục duy trì shared secret sau incident nếu có thể chuyển sang workload identity/federation.

### 9.3. Signing key và issuer compromise

Nếu private signing key dùng để ký JWT/certificate bị lộ, phạm vi nghiêm trọng hơn một token bị đánh cắp: attacker có thể tạo token giả được validator tin. Cần:

- Ngừng ký bằng key bị compromise.
- Xoay key và cập nhật JWKS/trust bundle/certificate chain.
- Xác định validator có cache public key cũ bao lâu.
- Revoke/deny token phát hành bằng key đó theo key ID/issuer policy.
- Nếu cần, buộc re-authentication và phát lại credential.
- Điều tra mọi token/assertion được ký trong khoảng thời gian nghi vấn.

Không chỉ xóa key khỏi KMS mà quên validator vẫn cache public key hoặc trust chain cũ.

## 10. Workload identity, federation và credential CI/CD

Credential của workload có thể tồn tại ngoài user account:

- SPIFFE SVID hoặc workload certificate.
- Cloud managed identity và access token.
- Kubernetes service account token.
- Federated OIDC assertion từ CI/CD.
- Service account key, API key hoặc secret trong pipeline.
- mTLS private key và trust bundle.

Khi workload bị compromise:

1. Suspend hoặc disable identity issuance cho workload/subject bị ảnh hưởng.
2. Revoke SVID/certificate/token hoặc cloud grant theo authority.
3. Chặn workload runtime, pod, VM, node hoặc pipeline bị compromise.
4. Xóa role binding và federation trust condition không còn hợp lệ.
5. Rotate private key/secret và kiểm tra image/build provenance.
6. Re-deploy workload sạch với identity mới nếu cần.
7. Xác minh resource server không còn chấp nhận credential cũ.

Không xóa service account trước khi thu thập identity reference và audit cần thiết. Với Kubernetes/cloud, việc xóa pod/VM không nhất thiết vô hiệu hóa token đã copy ra ngoài.

## 11. Revocation propagation trong hệ thống phân tán

Credential có thể được chấp nhận ở nhiều validator: IdP, API gateway, service mesh, backend, cache, CDN, database proxy và worker. Một revoke command phải lan tới các điểm này theo SLA.

~~~mermaid
flowchart TD
    I[Incident command] --> A[Identity authority / token store]
    A --> E[Revocation event / outbox]
    E --> G[API gateways]
    E --> R[Resource servers]
    E --> M[Service mesh / certificate validators]
    E --> C[Session and token caches]
    G --> V[Verification checks]
    R --> V
    M --> V
    C --> V
    V --> D[Old credential denied]
~~~

### 11.1. Nguồn trạng thái authoritative

Xác định hệ thống nào là nguồn sự thật cho trạng thái revoked. Validator không nên suy đoán từ event do client gửi hoặc cache không có version. Dùng event có integrity, sequence/version và retry bền vững.

### 11.2. Cache invalidation

Cache có thể tiếp tục trả kết quả active sau revoke. Cần:

- TTL giới hạn theo mức rủi ro.
- Push invalidation hoặc polling/version check.
- Cache key gồm issuer, token/session reference, principal và tenant nếu cần.
- Xử lý event duplicate/out-of-order.
- Xóa stale cache khi nhận version mới hơn.
- Metric cho propagation lag và validator acknowledgement.

### 11.3. Fail-open và fail-closed

Nếu revocation service không khả dụng, quyết định phụ thuộc mức nhạy cảm. Resource nhạy cảm có thể fail closed hoặc yêu cầu re-authentication; hệ thống ít nhạy cảm có thể chấp nhận cache còn hạn trong SLA đã phê duyệt. Không để validator mặc định tin credential vô thời hạn khi không truy cập được revocation state.

### 11.4. Revoke propagation SLA

Định nghĩa thời gian tối đa từ lúc revoke được commit tới lúc mọi validator liên quan từ chối credential. Ví dụ, một access token ngắn hạn có thể được giới hạn bằng TTL; session đặc quyền có thể cần push revoke gần realtime. SLA phải đo được, không chỉ là mục tiêu trên tài liệu.

## 12. Thứ tự thu hồi và giới hạn blast radius

Không có thứ tự cố định cho mọi incident. Một trình tự thường dùng:

1. Chặn attacker tiếp tục lấy credential mới: suspend issuance, revoke refresh grant hoặc disable compromised client.
2. Revoke session/token có bằng chứng bị chiếm.
3. Revoke credential gốc bị lộ (password, passkey, key, certificate, API key).
4. Thu hồi downstream grant, role binding và delegated token.
5. Xử lý thiết bị/workload bị compromise.
6. Xoay signing key/CA nếu trust authority bị ảnh hưởng.
7. Xác minh các validator và downstream đã áp dụng.

Nếu signing key/CA bị compromise, ưu tiên authority trust boundary trước khi phát credential mới. Nếu chỉ một user session bị lộ, không cần revoke toàn bộ tenant trừ khi evidence cho thấy phạm vi rộng.

### 12.1. Blast radius theo loại sự cố

| Sự cố | Phạm vi revoke cần đánh giá |
| --- | --- |
| Password của một user bị lộ | Password verifier, sessions, refresh families, reset challenges, recovery activity |
| Một thiết bị bị mất | Device-bound passkeys/factors, sessions/tokens trên thiết bị, device trust |
| TOTP seed bị lộ | Factor record, pending challenge, recovery codes nếu cùng nguồn lộ |
| Refresh token bị đánh cắp | Token family, session, descendant tokens, access token policy |
| API key của một service bị lộ | Key, workload grants, downstream permissions, mọi consumer dùng chung key |
| mTLS private key bị lộ | Certificate, trust mapping, workload session và key copies |
| IdP signing key bị lộ | Tokens/assertions được ký bằng key, validator trust, federation và downstream grants |
| Workload node bị compromise | Workload identities trên node, credentials cấp từ node, service account/role bindings |

## 13. Rotation và khôi phục quyền truy cập

Sau containment, người dùng hoặc workload hợp lệ cần credential mới. Recovery phải diễn ra qua một trust path còn an toàn.

### 13.1. User recovery

- Xác minh người dùng bằng phương thức độc lập với credential bị lộ.
- Nếu email/phone chính bị nghi compromise, không dùng nó làm kênh xác minh duy nhất.
- Thu hồi credential/factor bị ảnh hưởng và session cũ.
- Đăng ký password/passkey/MFA mới với xác nhận rõ ràng.
- Tạo recovery code mới và vô hiệu hóa bộ cũ.
- Gửi notification qua contact đã xác minh; thông báo thiết bị/session đã revoke.
- Kiểm tra account linking, email, phone, forwarding rule và quyền đã thay đổi.
- Yêu cầu step-up trước hành động nhạy cảm trong giai đoạn recovery nếu risk còn cao.

### 13.2. Workload recovery

- Xác minh image/build artifact và deployment pipeline sạch.
- Tạo key pair mới; private key cũ không được tái sử dụng.
- Cấp workload identity/certificate/token mới từ authority tin cậy.
- Gán role/scope tối thiểu.
- Cập nhật consumer theo rolling deployment.
- Xác minh credential cũ bị từ chối và workload mới hoạt động đúng.

### 13.3. Overlap khi rotation

Overlap có thể cần để rollout không gián đoạn, nhưng trong incident credential cũ đã bị lộ, overlap tạo cửa sổ attacker tiếp tục dùng. Nếu buộc phải overlap:

- Thời gian ngắn, có deadline và owner.
- Ràng buộc credential cũ theo nguồn/client nếu có thể.
- Theo dõi mọi request dùng credential cũ.
- Không cấp thêm quyền cho credential cũ.
- Có kill switch để kết thúc overlap sớm.
- Xác minh sau deadline rằng credential cũ bị từ chối.

## 14. Thông báo, hỗ trợ và bằng chứng

Thông báo cho người dùng cần:

- Nêu loại sự kiện ở mức họ có thể hiểu.
- Hướng dẫn mở ứng dụng/trang chính thức, không nhấp link lạ.
- Nói rõ phiên hoặc phương thức nào đã bị thu hồi nếu có thể xác nhận.
- Hướng dẫn đăng ký lại credential an toàn.
- Không yêu cầu gửi password, OTP, recovery code hoặc private key cho support.
- Cung cấp mã tham chiếu incident opaque.

Đội support cần biết quy trình xác minh danh tính, quyền thực hiện revoke và cách escalate. Support override phải có audit, lý do, người phê duyệt và giới hạn phạm vi. Không dùng câu trả lời bảo mật hoặc thông tin cá nhân làm cách duy nhất xác minh.

### 14.1. Evidence cần lưu

- Incident ID, thời điểm phát hiện và người quyết định.
- Principal/credential/session/token family reference.
- Issuer, audience, key version, certificate serial hoặc workload identity.
- Lệnh revoke và kết quả commit.
- Validator/resource server đã nhận trạng thái.
- Thời điểm credential cũ bị từ chối ở mỗi điểm kiểm tra.
- Credential mới được cấp và recovery method đã xác minh.
- Ngoại lệ, lỗi propagation, rollback và lý do.
- Notification/communication status.

Không lưu raw secret trong incident ticket. Evidence cần integrity, access control, retention và audit.

## 15. Pseudocode: điều phối thu hồi credential

Ví dụ khái niệm cho một incident coordinator:

~~~ts
async function containCompromisedPrincipal(incident, principalRef) {
  const scope = await inventory.resolveCredentialGraph(principalRef);

  await incidentStore.recordScope({
    incidentId: incident.id,
    principalRef,
    credentialRefs: scope.credentialRefs,
    sessionRefs: scope.sessionRefs,
    tokenFamilyRefs: scope.tokenFamilyRefs,
    workloadRefs: scope.workloadRefs
  });

  // Ngăn cấp thêm quyền từ refresh/grant bị compromise.
  await identityAuthority.suspendRiskyIssuance({
    principalRef,
    incidentId: incident.id
  });

  const revokeResults = await revocationCoordinator.revoke({
    principalRef,
    sessionRefs: scope.sessionRefs,
    tokenFamilyRefs: scope.tokenFamilyRefs,
    credentialRefs: scope.compromisedCredentialRefs,
    grantRefs: scope.grantRefs,
    reason: "SECURITY_INCIDENT"
  });

  await propagation.waitForRequiredValidators({
    revocationRefs: revokeResults.references,
    deadline: incident.revocationSla
  });

  const verification = await verifierProbe.checkOldCredentials({
    references: revokeResults.references,
    validators: scope.acceptingValidators
  });

  if (!verification.allDenied) {
    await incidentStore.escalate({
      incidentId: incident.id,
      reason: "REVOCATION_PROPAGATION_INCOMPLETE",
      pendingValidators: verification.pendingValidators
    });
    return { status: "CONTAINMENT_INCOMPLETE" };
  }

  return { status: "CONTAINED", evidenceRef: verification.evidenceRef };
}
~~~

Đây là pseudocode, không phải API production. Cần kiểm tra authorization của người/automation gọi revoke, idempotency, partial failure, event outbox, rate limit, retry và audit. Không xóa inventory/evidence trước khi có xác nhận. Nếu một validator chưa nhận revoke, không báo incident đã containment hoàn tất.

## 16. Runbook mẫu: nghi lộ refresh token của một người dùng

**Tình huống:** refresh token cũ đã consumed xuất hiện lại từ context khác; chưa rõ đây là retry hợp lệ hay attacker.

### Triage

1. Lấy event từ authorization server, xác minh producer và token family state.
2. Kiểm tra operation ID, client binding, thời gian và lịch sử refresh để loại trừ retry hợp lệ.
3. Xác định user, session, device và access token đã được cấp từ family.
4. Kiểm tra account privilege, recovery method, MFA/passkey changes và sensitive actions.

### Containment

1. Nếu reuse không giải thích được, revoke refresh family và grant liên quan.
2. Revoke session/device liên quan theo policy.
3. Chặn access token hiện tại qua introspection/denylist/session epoch nếu được hỗ trợ; nếu không, ghi rõ TTL còn lại và tăng kiểm soát.
4. Nếu có bằng chứng credential gốc bị lộ, reset password hoặc revoke authenticator tương ứng.
5. Gửi notification qua contact đã xác minh và yêu cầu recovery nếu cần.

### Verification

1. Gửi lại refresh token cũ tới token endpoint trong môi trường kiểm thử/verification an toàn và xác nhận bị từ chối.
2. Kiểm tra descendant token không thể refresh.
3. Kiểm tra API/resource server từ chối session/access token theo SLA.
4. Kiểm tra cache/gateway/replica đã nhận revoke.
5. Theo dõi request tiếp tục dùng credential cũ.

### Recovery và closure

1. Xác minh user qua phương thức độc lập.
2. Cấp session và credential mới.
3. Kiểm tra passkey/MFA/recovery method và account linking.
4. Ghi audit, thời gian propagation và mọi ngoại lệ.
5. Đóng incident khi bằng chứng containment và recovery đầy đủ.

## 17. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Password của user bị compromise | Password cũ không còn xác thực; session/token liên quan được xử lý theo policy |
| User đổi password nhưng session cũ còn | Session cũ bị revoke hoặc thời hạn/giới hạn còn lại được nêu rõ và kiểm soát |
| Refresh token consumed xuất hiện lại | Family reuse policy kích hoạt; không cấp token mới từ credential cũ |
| Access JWT bị revoke nhưng API chỉ kiểm tra chữ ký | Test chứng minh giới hạn; TTL/introspection/denylist/epoch được áp dụng theo SLA |
| TOTP seed bị lộ | Factor cũ bị vô hiệu hóa; seed mới được đăng ký qua recovery đã xác minh |
| Passkey trên thiết bị mất | Credential record phía server bị revoke; session liên quan bị xử lý; user được hướng dẫn xóa bản đồng bộ nếu cần |
| Recovery code bị lộ | Bộ code cũ bị vô hiệu hóa; bộ mới được cấp sau xác minh |
| Certificate private key bị lộ | Certificate cũ bị revoke/deny ở mọi validator; key pair mới được tạo |
| API key dùng chung bị lộ | Tất cả consumer đã biết được inventory; key cũ bị từ chối và key mới có owner/scope riêng |
| IdP signing key bị compromise | Issuance dừng/rotate; validator trust và token ký bằng key cũ được xử lý |
| Workload node bị compromise | Workload identity/credential liên quan bị revoke; workload sạch được deploy lại |
| Revocation event bị duplicate | Xử lý idempotent, không tạo trạng thái mâu thuẫn |
| Revocation event đến trễ hoặc sai thứ tự | Version/sequence ngăn trạng thái cũ ghi đè trạng thái revoked |
| Một validator offline | Incident không được đánh dấu contained cho tới khi validator xác minh hoặc có biện pháp thay thế được phê duyệt |
| Cache vẫn trả credential active | Invalidation/TTL/epoch đưa cache về trạng thái từ chối trong SLA |
| Rotation overlap còn hiệu lực | Có owner/deadline/monitoring; credential cũ bị retire đúng hạn |
| Recovery qua email bị nghi compromise | Dùng kênh proofing độc lập; không gửi reset link làm bằng chứng duy nhất |
| Revoke nhầm workload credential | Có phương án cấp lại từ authority tin cậy, audit và khôi phục service |
| Alert báo revoke thành công nhưng resource vẫn accept | Phát hiện verification failure; containment chưa hoàn tất |
| Incident đóng | Có inventory, revoke result, propagation evidence, recovery record và owner |

### Chỉ số vận hành

Theo dõi thời gian từ phát hiện tới revoke commit, thời gian propagation tới validator cuối cùng, tỷ lệ validator xác nhận, số credential cũ tiếp tục được thử, số session/token family bị thu hồi, số credential mới được cấp, lỗi rotation, số orphaned credential và thời gian recovery. Đo riêng SLA cho user session, privileged account, workload credential và signing authority.

## 18. Bài tập tự kiểm tra

Một nhân viên báo laptop bị mất sau khi đăng nhập vào hệ thống. Identity provider ghi nhận refresh token reuse; tài khoản có password, hai passkey, TOTP, recovery code và nhiều session. Nhân viên này cũng có quyền truy cập ứng dụng nội bộ qua một workload integration. API sử dụng JWT access token sống ngắn và service mesh dùng mTLS.

Hãy:

1. Xác định credential/session/token inventory cần thu thập.
2. Phân biệt bằng chứng cần giữ với secret tuyệt đối không đưa vào ticket.
3. Lập thứ tự containment và giải thích vì sao chỉ đổi password là chưa đủ.
4. Thiết kế revoke refresh family, session, access JWT và passkey liên quan.
5. Xác định khi nào cần revoke TOTP/recovery code và khi nào giữ authenticator còn tin cậy.
6. Kiểm tra integration/workload credential có bị ảnh hưởng từ thiết bị hoặc token bị lộ không.
7. Thiết kế propagation verification cho gateway, API và service mesh.
8. Lập recovery flow và thông báo người dùng qua kênh đã xác minh.
9. Viết test case cho cache outage, validator offline, retry duplicate và revoke nhầm.

**Gợi ý đánh giá:** lời giải tốt phải có inventory theo quan hệ credential-session-token, containment theo evidence, hiểu giới hạn JWT, xác minh revoke ở từng validator, rotation bằng credential mới và recovery độc lập. Không đánh dấu hoàn tất chỉ dựa trên việc identity provider trả về success cho lệnh revoke.

---

**Ghi nhớ:** thu hồi credential sự cố là quá trình chặn credential bị compromise ở mọi nơi có thể chấp nhận nó. Hãy xác định principal và credential graph, giữ bằng chứng an toàn, ngăn issuance/refresh mới, revoke session/token/factor/key/grant liên quan, truyền trạng thái tới validator và **kiểm tra credential cũ thực sự bị từ chối**. Sau containment mới khôi phục bằng credential mới qua kênh đã xác minh. Đổi password, xóa cookie hoặc đánh dấu token revoked tại một service riêng lẻ không chứng minh toàn hệ thống đã an toàn.
