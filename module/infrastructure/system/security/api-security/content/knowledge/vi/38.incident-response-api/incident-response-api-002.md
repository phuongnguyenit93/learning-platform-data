# Revoke credential và rotate signing key

## 1. Vì sao phải thu hồi credential và xoay signing key?

Credential là bằng chứng mà API dùng để nhận diện caller hoặc xác minh một thông điệp. API key, access token, refresh token, session cookie, client certificate và signing key đều có thể trở thành điểm xâm nhập nếu bị lộ, dùng sai phạm vi hoặc không còn được phép tin cậy.

Khi credential bị lộ, việc xóa secret khỏi một file hoặc đổi mật khẩu ở một hệ thống chưa chắc đã chặn được attacker. Credential có thể đang được dùng ở nhiều service, cache, job, thiết bị hoặc vùng triển khai. Một JWT đã ký có thể tiếp tục được chấp nhận đến khi hết hạn nếu resource server chỉ kiểm tra chữ ký và claim. Một API key có thể vẫn hợp lệ ở node chưa nhận trạng thái revoke. Một refresh token có thể tạo access token mới nếu token family chưa bị thu hồi.

Các tình huống phổ biến:

- API key xuất hiện trong repository, log, CI output hoặc ticket.
- Access token bị lấy từ browser, thiết bị, log hoặc memory dump.
- Refresh token bị đánh cắp và được dùng để duy trì quyền truy cập.
- Service account hoặc client secret bị lộ trong pipeline/deployment.
- Private signing key bị truy cập trái phép.
- Certificate của workload bị lộ hoặc sắp hết hạn.
- Nhân viên, vendor hoặc integration không còn được phép truy cập.
- Credential cũ vẫn được dùng sau khi migration hoặc sunset hoàn tất.

Trong phạm vi **SECURITY_API_SECURITY**, revoke credential và rotate signing key là hoạt động bảo vệ API theo principal, client, tenant, token issuer và luồng nghiệp vụ. Mục tiêu là cắt quyền truy cập có kiểm soát, giới hạn thời gian attacker có thể tiếp tục dùng credential, khôi phục trust chain và chứng minh mọi consumer đã chuyển sang credential mới.

Sau bài học này, người học có thể:

1. Phân biệt credential revocation với signing-key rotation.
2. Xác định credential nào cần revoke và phạm vi ảnh hưởng của nó.
3. Thu hồi API key, OAuth token, session, service account và mTLS certificate.
4. Hiểu giới hạn revoke của JWT self-contained.
5. Xoay signing key theo lịch và trong tình huống compromise.
6. Quản lý `kid`, JWKS, cache và giai đoạn overlap an toàn.
7. Xác minh việc revoke/rotate đã lan tới toàn bộ enforcement point.
8. Viết runbook, audit evidence và kiểm thử credential lifecycle.

## 2. Phân biệt credential, token và signing key

Các khái niệm này liên quan nhưng không thay thế nhau.

| Thành phần | Vai trò | Hành động khi có sự cố |
|---|---|---|
| API key | Nhận diện client/integration và có thể gắn quota/scope | Revoke key cụ thể, cấp key mới, kiểm tra usage |
| Access token | Cho phép truy cập resource trong thời hạn và scope | Revoke/introspect/denylist hoặc chờ expiry theo thiết kế |
| Refresh token | Cấp access token mới | Revoke token hoặc toàn bộ token family/session |
| Session cookie | Tham chiếu tới session đã xác thực | Invalidate session server-side và xóa cookie phía client |
| Client secret | Xác thực OAuth client với authorization server | Rotate secret, vô hiệu secret cũ và kiểm tra client usage |
| mTLS certificate | Xác thực workload/client ở tầng TLS | Revoke certificate/trust mapping và phát hành certificate mới |
| Signing key | Ký JWT hoặc thông điệp để verifier xác minh nguồn gốc | Dừng ký bằng key cũ, chuyển key mới và cập nhật trust ở verifier |
| Encryption key | Mã hóa/giải mã dữ liệu | Rotate/re-wrap theo quy trình key management; không nhầm với signing key |

### 2.1. Revoke credential

Revoke là thay đổi trạng thái tin cậy của một credential hoặc identity. Sau thời điểm có hiệu lực, các request mới dùng credential đó phải bị từ chối tại mọi enforcement point liên quan.

### 2.2. Rotate credential

Rotation thay credential cũ bằng credential mới. Quy trình thường gồm tạo credential mới, phân phối tới consumer, xác minh consumer đã chuyển, rồi revoke credential cũ.

Không phải mọi incident đều có thể chờ overlap. Nếu secret cũ đã bị compromise, thời gian overlap có thể tạo thêm cơ hội cho attacker.

### 2.3. Rotate signing key

Signing-key rotation thay key dùng để ký token/thông điệp. Với chữ ký bất đối xứng, issuer giữ private key để ký còn resource server dùng public key để xác minh. Verifier cần nhận public key mới trước khi token ký bằng key mới xuất hiện.

Signing-key rotation có phạm vi ảnh hưởng lớn hơn một API key riêng lẻ: một key có thể ký token cho nhiều client, user, tenant hoặc service.

### 2.4. Signing key không phải TLS certificate

TLS certificate bảo vệ kênh truyền và xác thực endpoint ở TLS layer. JWT signing key xác minh token ở application layer. Thay TLS certificate không tự động revoke JWT; xoay JWT signing key cũng không thay TLS certificate.

Lập inventory và runbook riêng cho từng loại key.

## 3. Khi nào cần revoke hoặc rotate?

Các trigger thường gặp:

- Secret/token/private key bị lộ hoặc nghi ngờ bị lộ.
- Credential xuất hiện trong public repository, artifact hoặc log.
- Principal hoặc service account bị compromise.
- Nhân viên/vendor rời tổ chức hoặc integration kết thúc.
- Credential hết hạn, vượt scope hoặc không còn owner.
- Signing key có dấu hiệu bị truy cập trái phép.
- Cryptographic algorithm hoặc key size không còn đáp ứng policy.
- Rotation định kỳ theo lịch.
- Phát hiện token replay, refresh-token reuse hoặc client bất thường.
- Thay đổi tenant, issuer, environment hoặc trust boundary.

### 3.1. Mức độ khẩn cấp

| Mức | Ví dụ | Hướng xử lý |
|---|---|---|
| Routine | Đến lịch rotate, owner đã chuẩn bị consumer | Tạo key mới, chuyển consumer, revoke key cũ theo kế hoạch |
| Elevated | Credential bị chia sẻ sai nơi nhưng chưa có bằng chứng dùng trái phép | Xác minh exposure, giới hạn scope, rotate sớm và theo dõi |
| Emergency | Private signing key/API key/token bị xác nhận compromise | Chặn credential/key cũ ngay theo incident plan, rotate, invalidate cache và điều tra usage |
| Administrative | User/service account/vendor không còn quyền | Revoke theo offboarding và audit, kiểm tra credential liên quan |

Không trì hoãn containment khi có bằng chứng key đang bị attacker sử dụng chỉ để duy trì một migration overlap thuận tiện.

### 3.2. Đánh giá phạm vi trước hành động

Xác định:

- Credential ID hoặc `kid` nào liên quan?
- Credential thuộc principal, client, tenant hay service nào?
- Những API, audience, scope và resource nào chấp nhận nó?
- Có bao nhiêu instance/region/cluster validate credential?
- Credential có được cache ở gateway, sidecar, SDK hoặc service không?
- Có token/session được phát hành từ credential đó không?
- Có key backup hoặc replica nào cũng bị ảnh hưởng?
- Consumer nào phụ thuộc credential hiện tại?

Khi chưa xác định hết phạm vi, ưu tiên biện pháp containment có thể thu hẹp blast radius và mở rộng dần theo bằng chứng. Không tự động revoke toàn bộ tenant hoặc toàn bộ issuer nếu một key riêng lẻ có thể được cô lập an toàn.

## 4. Inventory và ownership trước khi revoke

Không thể thu hồi đáng tin cậy một credential mà hệ thống không biết nó tồn tại ở đâu và ai chịu trách nhiệm.

Một credential inventory nên có:

- Credential ID không bí mật.
- Credential type.
- Principal/client/service account owner.
- Tenant hoặc environment.
- Issuer, audience, scope và route được phép.
- Created-at, expiry, last-used-at.
- Trạng thái active, pending rotation, revoked, expired.
- Key version hoặc `kid`.
- Consumer/service sử dụng.
- Storage/secret manager reference.
- Revocation mechanism và propagation SLA.
- Approver/owner và lịch review.

Không đưa raw secret, private key, bearer token hoặc refresh token vào inventory.

### 4.1. Key identifier phải không bí mật

API key thường nên có public identifier và secret riêng. `key_id` dùng tra cứu record; secret dùng chứng minh quyền sở hữu. Khi log/audit, ghi `key_id` hoặc reference đã pseudonymize, không ghi secret.

JWT header `kid` cũng chỉ là identifier chọn public key trong trusted key set; nó không phải bằng chứng key đáng tin và không được dùng để truy cập file/path tùy ý.

### 4.2. Theo dõi last-used-at

Last-used-at giúp tìm consumer còn hoạt động và phát hiện credential cũ vẫn được dùng. Timestamp cần đến từ enforcement point đáng tin, có clock đồng bộ và không bị client tự khai.

Không coi credential không có usage gần đây là an toàn để xóa ngay: có thể là batch job theo tháng/quý hoặc disaster recovery path. Xác nhận với owner trước routine revoke.

### 4.3. Tìm usage trên toàn bộ trust boundary

Kiểm tra gateway, API service, authorization server, secret manager audit, CI/CD, workload, job scheduler, mobile/backend client và integration logs. Một credential có thể được dùng qua private endpoint mà dashboard public không ghi nhận.

## 5. Revoke API key

API key thường được dùng cho machine-to-machine integration, partner API hoặc service client. Vì key có thể sống lâu và được lưu ở nhiều consumer, cần thiết kế revoke ngay từ đầu.

### 5.1. Thiết kế key record

Một record tham khảo:

```json
{
  "keyId": "key_7f31",
  "ownerClientId": "billing-worker",
  "tenantId": "tenant-a",
  "environment": "production",
  "secretHash": "one-way-verifier",
  "scopes": ["invoice.read"],
  "createdAt": "2026-10-01T00:00:00Z",
  "expiresAt": "2027-01-01T00:00:00Z",
  "status": "ACTIVE",
  "lastUsedAt": "2026-11-18T10:00:00Z"
}
```

Đây là schema minh họa; secret hash/verifier phải được tạo và lưu theo thiết kế phù hợp với entropy của key. API key nên có entropy cao, secret chỉ hiển thị một lần khi cấp và không lưu raw secret để tra cứu lại.

### 5.2. Revoke một key cụ thể

Khi revoke:

1. Xác minh key ID và owner.
2. Ghi nhận incident/change reference và người thực hiện.
3. Chuyển trạng thái key thành revoked trong nguồn quản lý trung tâm.
4. Phát sự kiện invalidate tới gateway/service cache nếu có.
5. Đảm bảo mọi node từ chối key đó.
6. Cấp key mới qua secret manager cho consumer hợp lệ.
7. Xác minh consumer chuyển sang key mới.
8. Theo dõi mọi lần thử dùng key cũ.

Không chỉ xóa record khỏi database nếu cache hoặc replica vẫn có thể xác thực key.

### 5.3. Revoke so với delete

Giữ tombstone/revocation record đủ lâu để mọi verifier biết key đã bị thu hồi. Xóa record ngay có thể khiến một cache hoặc replica cũ không phân biệt được key không tồn tại với dữ liệu chưa đồng bộ.

Retention của tombstone cần theo threat model, audit policy và vòng đời cache. Không lưu secret trong tombstone.

### 5.4. Key rotation có overlap

Trong routine rotation:

- Tạo key mới với key ID mới.
- Cấp secret mới cho consumer qua kênh được bảo vệ.
- Cho phép hai key cùng hoạt động trong một khoảng overlap đã định.
- Theo dõi usage key mới và key cũ.
- Xác nhận mọi consumer hợp lệ đã chuyển.
- Revoke key cũ.
- Xóa secret cũ khỏi nơi phân phối theo lifecycle.
- Lưu audit evidence.

Overlap cần có deadline và owner. Không để hai key cùng hoạt động vô thời hạn.

### 5.5. Emergency revoke

Nếu key cũ bị lộ:

- Đánh dấu revoked ngay.
- Invalidate cache và kiểm tra mọi region.
- Không duy trì overlap chỉ để tránh sửa consumer.
- Cấp key mới cho consumer đã xác minh.
- Giới hạn scope/quota trong thời gian khôi phục nếu phù hợp.
- Theo dõi request bị từ chối dùng key cũ.
- Kiểm tra request thành công trước thời điểm revoke để đánh giá data exposure.

## 6. OAuth access token và refresh token

OAuth có nhiều loại token với vòng đời và semantics khác nhau.

### 6.1. Access token

Access token cấp quyền truy cập resource trong phạm vi, audience và thời hạn được quy định. Token có thể là opaque reference token hoặc self-contained JWT.

- Opaque token thường được resource server kiểm tra qua introspection hoặc cơ chế lookup tương đương.
- JWT có thể được xác minh offline bằng chữ ký và claim, không nhất thiết gọi authorization server mỗi request.

Sự khác biệt này ảnh hưởng trực tiếp đến tốc độ và độ tin cậy của revocation.

### 6.2. Refresh token

Refresh token dùng để cấp access token mới. Nếu refresh token bị đánh cắp, attacker có thể duy trì quyền truy cập sau khi access token hiện tại hết hạn.

Nên dùng refresh-token rotation nếu authorization server hỗ trợ: mỗi lần refresh thành công, token cũ bị vô hiệu và token mới được cấp. Phát hiện reuse token cũ có thể là tín hiệu token theft; revoke token family/session liên quan theo policy.

### 6.3. Revoke token theo chuẩn

OAuth Token Revocation (RFC 7009) định nghĩa endpoint để client yêu cầu revoke token. Authorization server cần xác định token type và phạm vi liên quan, ví dụ access token hoặc refresh token. Response của endpoint thường không tiết lộ token có tồn tại hay không nhằm tránh oracle.

Một số authorization server hỗ trợ revoke refresh token sẽ đồng thời vô hiệu hóa access token liên quan; behavior cụ thể phụ thuộc implementation và token model. Đọc contract của provider và kiểm thử thực tế, không giả định mọi token family tự động bị revoke.

### 6.4. Revoke refresh token family

Khi refresh token bị compromise hoặc reuse detection kích hoạt:

- Revoke token đang bị nghi ngờ.
- Revoke token family/session liên quan nếu semantics cho phép.
- Yêu cầu re-authentication.
- Kiểm tra access token đã phát hành từ family đó.
- Thông báo client/device theo flow phù hợp.
- Điều tra IP/device/session và các API operation đã thực hiện.

Không revoke mọi session của một user nếu chỉ một device bị compromise, trừ khi evidence hoặc policy yêu cầu.

## 7. Giới hạn revoke của JWT self-contained

JWT self-contained thường chứa claim và chữ ký. Resource server có thể xác minh token mà không hỏi authorization server. Điều này giúp giảm latency và tăng khả năng hoạt động độc lập, nhưng tạo trade-off: một JWT đã phát hành thường tiếp tục hợp lệ đến `exp` nếu chữ ký và claim vẫn hợp lệ.

### 7.1. Đổi key không phải lúc nào cũng revoke token đúng cách

Nếu issuer có nhiều signing key và verifier vẫn tin public key cũ, token ký bằng key cũ vẫn được chấp nhận. Việc issuer ngừng ký bằng key cũ không tự động vô hiệu token đã phát hành.

Nếu key cũ bị compromise, attacker có thể tự tạo JWT mới có chữ ký hợp lệ bằng private key bị lộ. Chờ token expiry không đủ nếu attacker có thể tạo token với `exp` ở tương lai trong phạm vi validator cho phép.

### 7.2. Các chiến lược revoke JWT

| Chiến lược | Cách hoạt động | Trade-off |
|---|---|---|
| Access token TTL ngắn | Token hết hạn nhanh | Giảm cửa sổ rủi ro nhưng tăng refresh traffic |
| Introspection | Resource server hỏi trạng thái token | Revoke nhanh hơn, phụ thuộc availability/cache của authorization server |
| Denylist theo `jti` | Từ chối token ID cụ thể trước expiry | Cần state và lookup; phải bảo vệ/replicate denylist |
| User/session version | So sánh claim version với trạng thái server-side | Revoke theo user/session, thêm lookup hoặc cache |
| Signing-key removal | Verifier ngừng tin key ID cũ | Có thể ảnh hưởng tất cả token hợp lệ ký bằng key đó |
| Token exchange / sender-constrained token | Giới hạn khả năng replay hoặc đổi token | Thêm protocol và client complexity |

Chọn strategy theo mức độ rủi ro, latency budget và yêu cầu revoke SLA.

### 7.3. Denylist cần chống replay và race

Nếu dùng denylist theo `jti`:

- Key phải được xác định duy nhất theo issuer và token ID.
- TTL của denylist phải ít nhất đến khi token hết hạn cộng clock skew cần thiết.
- Ghi revoke phải có tính nhất quán phù hợp.
- Resource server phải fail closed hoặc có policy rõ khi không truy cập được denylist.
- Không cho caller tự đặt `jti` trùng gây ảnh hưởng token khác.
- Bảo vệ endpoint ghi/xóa denylist.

Không dùng raw JWT làm key hoặc log entry.

### 7.4. Sender-constrained token

DPoP hoặc mTLS-bound access token có thể ràng buộc token với một key của client, giảm khả năng sử dụng token bị đánh cắp ở thiết bị khác. Chúng không loại bỏ nhu cầu revoke khi private key hoặc client device bị compromise.

## 8. Revoke session và service account

### 8.1. Session cookie

Xóa cookie ở browser chỉ xóa bản sao phía client. Nếu attacker đã sao chép session ID, session vẫn có thể hợp lệ ở server.

Revoke cần:

- Invalidate session trong session store.
- Xóa hoặc rotate session ID.
- Revoke remember-me token nếu có.
- Thu hồi session family/device theo policy.
- Cập nhật cache hoặc distributed session replica.
- Xóa cookie với đúng Domain, Path, Secure và SameSite attributes khi client còn kết nối.
- Kiểm thử session cũ bị từ chối trên mọi node.

Nếu session được lưu trong Redis hoặc database, thao tác invalidation cần có consistency và TTL phù hợp.

### 8.2. Service account/workload identity

Khi workload bị compromise hoặc không còn owner:

1. Disable identity hoặc client registration.
2. Revoke client secret/API key/certificate liên quan.
3. Revoke token family và session.
4. Xóa quyền IAM/cloud role và access tới secret manager.
5. Kiểm tra workload replica, job, sidecar và autoscaling instance.
6. Cấp identity mới cho workload đã được rebuild/khôi phục.
7. Theo dõi credential cũ có tiếp tục được sử dụng không.

Chỉ rotate secret mà giữ service account quyền quá rộng vẫn để lại blast radius lớn.

### 8.3. Offboarding và vendor termination

Offboarding cần có checklist theo identity và integration, không chỉ disable tài khoản đăng nhập. Tìm API key, refresh token, client secret, personal access token, certificate, webhook secret và job credential do người hoặc vendor quản lý.

Giữ audit record về owner, thời điểm revoke, các consumer đã được chuyển và exception còn tồn tại.

## 9. Revoke mTLS certificate

mTLS xác thực client/workload bằng certificate trong TLS handshake. Revoke certificate cần phối hợp PKI, TLS termination point và mapping identity ở application.

### 9.1. Certificate revocation

Các cơ chế phổ biến:

- Certificate Revocation List (CRL).
- Online Certificate Status Protocol (OCSP).
- Trust store/allowlist cập nhật.
- Denylist theo serial number hoặc fingerprint.
- Short-lived certificate và tự động cấp lại.

Không phải TLS stack hoặc proxy nào cũng kiểm tra CRL/OCSP theo cùng cách. Cần xác minh behavior thực tế của load balancer, ingress, service mesh và application.

### 9.2. Connection đã được thiết lập

Certificate thường được kiểm tra ở TLS handshake. Một connection keep-alive hoặc HTTP/2 connection đã được thiết lập có thể tiếp tục tồn tại sau khi certificate bị revoke, tùy tầng TLS và cách triển khai.

Trong emergency response, cần xem xét drain/close connection, restart/rollout proxy hoặc buộc re-handshake theo khả năng hạ tầng. Chỉ cập nhật CRL mà không kiểm tra connection hiện có có thể không cắt quyền ngay.

### 9.3. Identity mapping

Không chỉ tin Common Name. Map identity theo SAN, issuer, serial/fingerprint và trust policy phù hợp. Certificate hợp lệ về PKI vẫn cần authorization theo workload, service, tenant và operation.

## 10. Signing-key lifecycle

Signing key có thể dùng để ký JWT, webhook message, request assertion hoặc artifact. Key lifecycle cần được quản lý riêng với credential của consumer.

Một lifecycle thường gồm:

1. Generate key trong KMS/HSM hoặc môi trường kiểm soát.
2. Gán key ID duy nhất.
3. Publish public key hoặc cấu hình verifier.
4. Kích hoạt key để ký.
5. Theo dõi usage và access audit.
6. Rotate theo lịch hoặc theo trigger.
7. Revoke/disable key cũ.
8. Retain public verification material hoặc metadata cần thiết theo policy.
9. Destroy private material khi hết retention và không còn nhu cầu.

### 10.1. Bảo vệ private signing key

- Lưu private key trong KMS/HSM hoặc secret manager có access control mạnh.
- Không commit vào source, image, config map hoặc log.
- Tách quyền ký khỏi quyền đọc secret và quyền quản trị key nếu nền tảng hỗ trợ.
- Dùng workload identity ngắn hạn để gọi KMS.
- Audit mọi lần sign, export, rotate, disable và delete.
- Giới hạn algorithm và key size theo cryptographic policy.
- Không cho mọi microservice giữ bản sao private key nếu chỉ issuer cần ký.

### 10.2. Asymmetric và symmetric signing

Với asymmetric signing, issuer giữ private key còn resource server chỉ cần public key để verify. Điều này giới hạn số hệ thống có khả năng mint token.

Với symmetric signing, mọi verifier giữ shared secret cũng có khả năng tạo chữ ký hợp lệ. Nếu nhiều resource server cùng dùng HS key, compromise một verifier có thể làm compromise issuer. Cân nhắc asymmetric signing khi có nhiều resource server hoặc trust boundary tách biệt.

### 10.3. Không tin thuật toán do token tự chọn

Verifier cần cấu hình allowlist algorithm. Không lấy `alg` trong JWT header làm quyết định tự do và không chấp nhận `none` hoặc algorithm ngoài policy. `kid` chỉ được dùng để chọn key trong tập key đã tin cậy; không dùng nó làm path, URL hoặc truy vấn tùy ý.

## 11. Xoay JWT signing key theo lịch

Routine rotation cần tránh phát hành token ký bằng key mới trước khi verifier biết public key tương ứng.

### 11.1. Quy trình overlap an toàn

1. Generate key pair mới trong KMS/HSM.
2. Gán `kid` mới, không tái sử dụng ID của key cũ.
3. Publish public key mới lên JWKS hoặc trust configuration.
4. Chờ verifier refresh JWKS/cache hoặc xác minh mọi region đã nhận key.
5. Chuyển issuer sang ký token mới bằng private key mới.
6. Tiếp tục chấp nhận public key cũ trong khoảng thời gian cần thiết cho token cũ còn hiệu lực.
7. Theo dõi token/usage theo `kid`.
8. Khi mọi token hợp lệ ký bằng key cũ đã hết hạn (cộng clock skew/cache allowance), remove public key cũ khỏi trust set.
9. Disable/destroy private key cũ theo retention và audit policy.

### 11.2. Xác định overlap window

Overlap cần bao phủ:

- Maximum access token lifetime.
- Clock skew được chấp nhận.
- JWKS refresh interval và cache TTL.
- Thời gian rollout verifier qua tất cả region.
- Queue/job có thể giữ token lâu hơn request bình thường.
- Token được phát hành ngay trước khi issuer switch.

Không chọn overlap tùy ý. Nếu token có lifetime 30 phút nhưng một verifier cache JWKS 24 giờ, cần tính cache behavior và có thể điều chỉnh trước khi rotation.

### 11.3. Không giữ key cũ mãi mãi

Sau khi overlap kết thúc, public key cũ nên bị loại khỏi trust set theo policy. Private key cũ cần disable hoặc destroy khi không còn yêu cầu ký/kiểm chứng. Giữ nhiều key cũ không dùng làm tăng bề mặt lỗi cấu hình và nguy cơ compromise.

## 12. Emergency signing-key rotation khi private key bị lộ

Khi private signing key bị compromise, attacker có thể tạo token giả có chữ ký hợp lệ. Đây là incident nghiêm trọng vì verifier có thể tin token đó nếu key ID vẫn được chấp nhận.

Quy trình emergency khác routine rotation:

1. Kích hoạt incident và xác định issuer, `kid`, algorithm, thời điểm nghi compromise.
2. Ngừng mọi hoạt động ký bằng private key bị ảnh hưởng.
3. Generate key pair mới trong KMS/HSM sạch.
4. Publish public key mới và ép refresh JWKS/trust cache ở các verifier.
5. Chuyển issuer sang key mới sau khi xác minh verifier đã nhận public key mới.
6. Loại `kid` bị compromise khỏi trust set hoặc áp dụng deny policy khẩn cấp.
7. Invalidate/revoke access token, refresh token và session có liên quan theo token model.
8. Kiểm tra token giả hoặc request được ký bằng key bị lộ.
9. Xác minh mọi resource server, gateway, region, offline verifier và consumer đã ngừng tin key cũ.
10. Lưu evidence, audit log và timeline; đánh giá data access/side effect.

### 12.1. Vì sao không giữ overlap khi key đã compromise?

Trong routine rotation, overlap giúp token hợp lệ cũ tiếp tục hoạt động. Khi private key cũ bị lộ, attacker cũng có thể tạo token mới với cùng key. Giữ public key cũ trong trust set sẽ tiếp tục cho verifier chấp nhận chữ ký attacker tạo ra.

Nếu cần duy trì một số consumer, cấp token mới ký bằng key mới hoặc dùng một issuer/key độc lập đã xác minh. Không tiếp tục tin key compromise chỉ vì còn token hợp lệ.

### 12.2. Tác động của remove key

Loại public key cũ có thể làm mọi JWT ký bằng key đó bị từ chối, kể cả token hợp lệ chưa hết hạn. Đây có thể là gián đoạn lớn, nhưng là biện pháp cần thiết khi key bị compromise.

Đánh giá scope issuer/audience và các service phụ thuộc để truyền thông, khôi phục và xác minh. Không nới trust trở lại nếu chưa xử lý nguyên nhân lộ key.

### 12.3. Nếu không thể lập tức cập nhật mọi verifier

- Dùng control plane/denylist có thể phân phối nhanh theo `kid`.
- Ép cache refresh hoặc purge cache ở gateway/service mesh.
- Kiểm tra mọi instance/region.
- Tạm disable endpoint hoặc issuer path nếu cần.
- Hạn chế network path tới verifier chưa cập nhật.
- Đặt incident severity cao cho node vẫn chấp nhận key cũ.
- Không tuyên bố containment hoàn tất cho tới khi có bằng chứng từ mọi enforcement point.

## 13. JWKS, kid và cache behavior

JWKS (JSON Web Key Set) cung cấp public key để verifier xác minh token. Quản lý JWKS là một phần của trust distribution.

### 13.1. `kid` phải ổn định và duy nhất

- Mỗi key version có `kid` riêng.
- Không tái sử dụng `kid` cho key material khác.
- Verifier chỉ chọn key trong JWKS/trust source đã cấu hình.
- Unknown `kid` phải thất bại an toàn.
- Không fallback sang key bất kỳ khi `kid` không tìm thấy.
- Không truy cập URL hoặc file path lấy từ token header.

### 13.2. JWKS cache

Verifier thường cache JWKS để giảm latency và phụ thuộc network. Cache tạo trade-off:

- TTL dài giảm request tới issuer nhưng làm chậm nhận key mới/revoke key cũ.
- TTL ngắn tăng freshness nhưng tăng dependency traffic và nguy cơ issuer outage.
- Unknown `kid` có thể kích hoạt refresh; cần chống refresh storm.
- Negative cache cần TTL hợp lý để không khóa nhầm key mới vừa publish.
- Cache cần có cơ chế refresh khi rotation hoặc emergency.

### 13.3. Cache invalidation trong incident

Khi key compromise:

- Purge/refresh cache theo control plane.
- Kiểm tra mọi instance/region.
- Kiểm tra sidecar, gateway và offline verifier.
- Xác minh thời gian cache cập nhật.
- Ghi nhận node chưa đồng bộ.
- Kiểm thử token cũ bị từ chối sau refresh.

Một JWKS endpoint cập nhật đúng không chứng minh mọi verifier đã tải nội dung mới.

### 13.4. JWKS endpoint và public material

JWKS public chỉ chứa public key material cần cho verification. Không publish private parameters (`d`, `p`, `q` hoặc secret symmetric key) trong JWKS public. Endpoint cần được phục vụ qua kênh tin cậy và có cache header phù hợp.

Không cho token header quyết định JWKS URI. Verifier lấy issuer/JWKS URI từ trusted configuration hoặc metadata đã xác minh.

## 14. Quy trình phối hợp consumer khi rotation thường kỳ

Rotation có thể gây outage nếu consumer không được thông báo hoặc không có khả năng nhận credential mới.

Một rollout nên có:

- Owner cho issuer và từng consumer.
- Deadline và overlap window.
- Secret/key version mới.
- Kênh phân phối an toàn.
- Health check hoặc canary request.
- Metric phân biệt usage key cũ/mới.
- Tiêu chí chuyển trạng thái.
- Revoke deadline và rollback/contingency.

### 14.1. Canary trước khi chuyển toàn bộ

Chuyển một consumer hoặc một tỷ lệ traffic nhỏ sang key mới. Xác minh authentication, authorization, latency, error rate và audit event. Sau đó mở rộng dần.

Không để canary dùng một quyền rộng hơn hoặc môi trường khác với consumer thật; nếu không, kết quả không đại diện.

### 14.2. Consumer không chuyển đúng hạn

Nếu consumer còn dùng key cũ:

1. Xác định owner và last-used evidence.
2. Phân biệt production workload với stale/test traffic.
3. Liên hệ owner qua kênh incident/change đã phê duyệt.
4. Cấp thời hạn migration cuối cùng nếu rủi ro cho phép.
5. Revoke đúng deadline.
6. Theo dõi lỗi và xử lý consumer đã ngừng hỗ trợ.

Trong emergency compromise, không gia hạn chỉ vì chưa liên hệ được owner; dùng containment và business continuity plan.

### 14.3. Rollback không có nghĩa khôi phục key đã lộ

Nếu key mới gây lỗi, rollback ứng dụng có thể dùng key thứ ba hoặc key version khác đã xác minh. Không re-enable private key compromise hoặc secret đã revoke để làm hệ thống hoạt động trở lại.

## 15. Incident runbook: credential bị lộ

Một runbook thực tế nên có các bước sau.

### 15.1. Detect và declare

- Xác nhận loại credential và nguồn phát hiện.
- Ghi thời điểm phát hiện và thời điểm nghi lộ.
- Tạo incident ID.
- Chỉ định incident commander, identity/key owner và service owner.
- Bảo toàn evidence theo policy.
- Đánh giá mức độ nhạy cảm, scope và expiry.

### 15.2. Contain

- Disable/revoke credential bị ảnh hưởng.
- Revoke refresh token/session family nếu có liên quan.
- Chặn `kid` compromise nếu signing key bị lộ.
- Invalidate cache và replica.
- Tạm giới hạn route, scope hoặc client khi cần.
- Bảo đảm consumer hợp lệ không còn dùng credential bị revoke.

### 15.3. Eradicate và recover

- Tìm nơi secret đã bị lộ và loại bỏ nguồn phát tán.
- Rotate credential/key trong KMS/secret manager sạch.
- Rebuild workload nếu host/container có thể bị compromise.
- Cấp lại quyền tối thiểu.
- Chuyển consumer và xác minh canary.
- Khôi phục traffic theo từng bước.

### 15.4. Validate

- Gửi request với credential cũ: phải bị từ chối.
- Gửi request với credential mới: chỉ được phép trong scope đã cấp.
- Kiểm tra mọi region/node/gateway.
- Kiểm tra token/session được phát hành trước incident.
- Kiểm tra refresh/reuse behavior.
- Kiểm tra audit event và alert.
- Xác minh không có cache stale hoặc fallback path chấp nhận credential cũ.

### 15.5. Close và learn

- Xác định root cause và phạm vi ảnh hưởng.
- Đánh giá dữ liệu/object/API operation có thể bị truy cập.
- Xem xét nghĩa vụ thông báo theo policy và quy định.
- Ghi timeline, decision và evidence.
- Cập nhật rotation automation, secret scanning và monitoring.
- Tạo remediation owner/deadline và theo dõi hoàn tất.

## 16. API response và client behavior sau revoke

Khi credential không còn hợp lệ, API cần trả response nhất quán.

| Tình huống | Status thường dùng | Ghi chú |
|---|---|---|
| Access token/API key không hợp lệ hoặc đã revoke | `401 Unauthorized` | Có thể kèm `WWW-Authenticate` phù hợp |
| Credential hợp lệ nhưng thiếu quyền | `403 Forbidden` | Không tiết lộ resource/role nội bộ |
| Rate limit khi client retry | `429 Too Many Requests` | Có thể trả `Retry-After` |
| Service tạm không thể xử lý do incident containment | `503 Service Unavailable` | Chỉ dùng khi đúng semantics và có thể retry |

Client cần xử lý 401 bằng flow refresh/re-auth phù hợp, không retry cùng credential vô hạn. Với 403, client không nên tự refresh token liên tục nếu lỗi là thiếu permission. Với 429, tuân thủ `Retry-After` và backoff có jitter.

Không trả chi tiết “key ID tồn tại nhưng đã revoke” cho public caller nếu điều đó tạo credential enumeration oracle.

## 17. Audit, logging và monitoring

Revoke/rotation phải có bằng chứng ai làm, làm gì, lúc nào và kết quả ra sao.

### 17.1. Audit event

Một event có thể gồm:

```json
{
  "event": "CREDENTIAL_REVOKED",
  "timestamp": "2026-11-18T13:20:00Z",
  "incidentId": "INC-2026-1042",
  "credentialType": "API_KEY",
  "credentialRef": "key_7f31",
  "ownerClient": "billing-worker",
  "environment": "production",
  "reason": "SUSPECTED_EXPOSURE",
  "actor": "security-operator",
  "result": "SUCCESS",
  "propagationStatus": "VERIFIED_ALL_REGIONS"
}
```

Không ghi raw credential, private key, bearer token hoặc secret manager value. Audit log cần integrity protection, access control, retention và correlation với change/incident record.

### 17.2. Metric hữu ích

- Credential revoke requests và success/failure.
- Thời gian từ revoke tới enforcement trên mọi node.
- Request bị từ chối do revoked key/token/`kid`.
- Unknown `kid` và JWKS refresh failure.
- JWKS cache age và refresh latency.
- Token refresh failure/reuse detection.
- API key usage theo key reference.
- Certificate validation/revocation failures.
- Consumer vẫn dùng credential cũ sau deadline.
- Rotation completion theo issuer/region/consumer.

### 17.3. Không tạo alert storm

Một credential compromise có thể tạo hàng nghìn request bị từ chối. Group theo incident, credential reference, issuer và client; giữ count và sample evidence. Alert cho việc credential cũ vẫn được chấp nhận có severity cao hơn việc credential cũ bị từ chối đúng như mong đợi.

## 18. Kiểm thử revoke và signing-key rotation

Kiểm thử cần xác nhận behavior ở mọi verifier, không chỉ kiểm tra database record đã đổi trạng thái.

### 18.1. API key

- Key active được chấp nhận trong scope đúng.
- Key revoked bị từ chối.
- Key hết hạn bị từ chối.
- Key thuộc tenant/client khác không truy cập được.
- Cache stale không tiếp tục chấp nhận key.
- Rotation overlap hoạt động đúng và có deadline.
- Key cũ bị từ chối sau deadline.
- Unknown key không tiết lộ record tồn tại.

### 18.2. OAuth token

- Opaque token bị từ chối sau introspection/revoke.
- JWT còn hạn vẫn bị xử lý theo revocation policy đã chọn.
- Refresh token bị revoke không cấp access token mới.
- Reuse refresh token cũ kích hoạt detection/family revoke theo policy.
- Token sai issuer/audience/expiry bị từ chối.
- Denylist lookup failure có behavior fail-safe đã định.
- Re-authentication cấp token mới đúng scope.

### 18.3. Signing key và JWKS

- Token ký bằng key mới được chấp nhận sau khi public key được publish.
- Token ký bằng key cũ được chấp nhận trong routine overlap.
- Token ký bằng key cũ bị từ chối sau khi overlap kết thúc.
- Unknown `kid` bị từ chối.
- Không có fallback sang key tùy ý.
- JWKS cache refresh nhận key mới.
- Emergency removal của compromised `kid` lan tới mọi verifier.
- Verifier không chấp nhận algorithm ngoài allowlist.
- JWKS public không chứa private key material.

### 18.4. Session và mTLS

- Session ID cũ bị từ chối trên mọi node sau invalidate.
- Remember-me/session family được revoke theo policy.
- Certificate hết hạn hoặc revoked bị từ chối ở TLS termination point.
- Connection cũ được drain/close theo emergency policy.
- Certificate mới được map đúng principal và scope.
- Workload không thể dùng identity đã disable.

### 18.5. Kiểm thử propagation và failure

- Một region mất kết nối control plane.
- Cache không refresh được.
- JWKS endpoint tạm unavailable.
- Một instance giữ config cũ.
- Consumer retry với credential cũ.
- Revoke event bị duplicate hoặc đến sai thứ tự.
- Key rotation đang diễn ra khi pod restart/scale.
- Audit sink tạm unavailable.
- Rollback ứng dụng sau khi key cũ đã revoke.

Mỗi test cần xác nhận security decision, response, audit event, cleanup và propagation time.

## 19. Ví dụ cấu hình JWT Resource Server trong Spring Security

Spring Security Resource Server có thể dùng issuer URI để cấu hình decoder và lấy metadata/JWKS theo cấu hình tin cậy. Ví dụ application configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/issuer
```

Với yêu cầu audience cụ thể, thêm validator thay vì chỉ tin chữ ký/issuer:

```java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder = JwtDecoders.fromIssuerLocation(
        "https://id.example.test/issuer"
    );

    OAuth2TokenValidator<Jwt> issuerValidator =
        JwtValidators.createDefaultWithIssuer(
            "https://id.example.test/issuer"
        );

    OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Invalid audience", null)
            );

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerValidator,
            audienceValidator
        )
    );

    return decoder;
}
```

Ví dụ minh họa validator issuer/audience. Cấu hình production còn cần algorithm allowlist, clock skew, key source tin cậy, token profile và error handling phù hợp. Signing-key emergency revoke cần một cơ chế phân phối deny `kid` hoặc cập nhật trust set tới mọi decoder; đổi issuer URI hoặc ngừng ký bằng key cũ không tự động vô hiệu token đã phát hành.

## 20. Những lỗi thiết kế thường gặp

1. **Chỉ xóa secret ở nơi phát hiện.** Consumer khác vẫn có thể sử dụng credential.
2. **Chỉ đổi API key mà không revoke key cũ.** Cả hai tiếp tục hoạt động không thời hạn.
3. **Giữ overlap sau khi key đã compromise.** Attacker vẫn có thể dùng credential cũ.
4. **Cho rằng JWT tự revoke khi logout.** Token self-contained có thể còn hiệu lực tới expiry.
5. **Ngừng ký bằng key cũ nhưng verifier vẫn trust public key cũ.** Token cũ vẫn được chấp nhận.
6. **Remove key khỏi một JWKS server nhưng không purge cache.** Một số node vẫn trust key compromise.
7. **Tái sử dụng `kid`.** Cache và verifier có thể map nhầm key material.
8. **Lấy JWKS URI từ JWT header.** Token không tin cậy có thể điều khiển key lookup.
9. **Cho algorithm do token tự chọn.** Verifier có thể chấp nhận algorithm ngoài policy.
10. **Chỉ revoke refresh token mà bỏ qua access token đã phát hành.** Access token vẫn có thể được dùng.
11. **Xóa session cookie phía browser nhưng giữ session server-side.** Session ID bị đánh cắp vẫn hợp lệ.
12. **Chỉ revoke certificate trong CA nhưng không kiểm tra TLS termination point.** Proxy có thể vẫn trust hoặc giữ connection cũ.
13. **Không inventory consumer và owner.** Credential cũ bị bỏ sót hoặc outage không có người xử lý.
14. **Không đo revoke propagation.** Không biết node nào còn chấp nhận credential.
15. **Log raw key/token trong audit.** Audit store trở thành nguồn lộ credential.
16. **Dùng cùng signing key ở mọi service không cần thiết.** Một compromise ảnh hưởng toàn bộ trust domain.
17. **Không kiểm tra token audience/scope.** Key rotation đúng nhưng token vẫn có quyền rộng.
18. **Re-enable key compromise khi rollback.** Khôi phục availability bằng cách mở lại đường xâm nhập.
19. **Không test failure mode của JWKS/control plane.** Verifier có thể fail-open hoặc gây outage.
20. **Tuyên bố incident đã đóng khi chưa kiểm tra mọi region/verifier.** Containment chưa được chứng minh.

## 21. Checklist revoke và rotate

Trước khi kết thúc incident hoặc rotation, xác nhận:

- [ ] Credential type, ID, owner, issuer, audience và scope đã được xác định.
- [ ] Phạm vi consumer, service, region và cache đã được inventory.
- [ ] Incident severity, owner, approver và timeline đã được ghi.
- [ ] Credential bị lộ đã bị disable/revoke tại nguồn trung tâm.
- [ ] Revoke đã lan tới gateway, service, replica và cache.
- [ ] API key mới được cấp qua secret manager và scope tối thiểu.
- [ ] Access token/refresh token/session family được xử lý theo token model.
- [ ] JWT revocation limitation đã được đánh giá.
- [ ] Signing key mới được tạo trong KMS/HSM và có `kid` mới.
- [ ] Public key mới được publish trước khi issuer ký bằng key mới.
- [ ] Verifier đã refresh JWKS/trust set.
- [ ] Routine overlap có deadline và chỉ giữ key cũ khi key chưa compromise.
- [ ] Emergency compromise đã loại key cũ khỏi trust set và invalidate cache.
- [ ] mTLS certificate revocation và existing connection behavior đã được xác minh.
- [ ] Consumer đã chuyển và request dùng credential cũ bị từ chối.
- [ ] Token/session được phát hành trước incident đã được đánh giá.
- [ ] Không còn private key/secret cũ trong nơi lưu trữ hoặc deployment cần thu hồi.
- [ ] Audit log không chứa secret và có incident/change reference.
- [ ] Metric/alert theo dõi revoke propagation và stale credential usage.
- [ ] Kiểm thử mọi region, node, gateway và offline verifier đã pass.
- [ ] Có evidence cho containment, recovery và owner sign-off.
- [ ] Root cause/remediation có owner và deadline.

## 22. Kết luận

Revoke credential và rotate signing key là hai hành động khác nhau nhưng thường phải phối hợp trong incident API. Revoke chặn một credential hoặc identity cụ thể; rotation thay credential/key material để hệ thống tiếp tục hoạt động bằng trust mới. API key, OAuth token, session và mTLS certificate có semantics revoke riêng, còn JWT self-contained có thể tiếp tục hợp lệ tới expiry nếu verifier không có state hoặc deny policy.

Routine signing-key rotation cần publish public key mới trước khi ký bằng private key mới, duy trì overlap đủ cho token cũ và loại key cũ sau deadline. Khi private signing key bị compromise, không giữ overlap cho key đó: dừng ký, publish key mới, loại `kid` compromise khỏi trust set, purge cache và xác minh mọi verifier đã ngừng chấp nhận token cũ.

Một incident chỉ được xem là contained khi credential cũ bị từ chối trên toàn bộ enforcement point, consumer hợp lệ đã chuyển sang credential mới, token/session liên quan đã được xử lý và audit evidence đầy đủ. Inventory, ownership, propagation monitoring, automated tests và runbook rõ ràng giúp giảm thời gian attacker giữ quyền truy cập mà vẫn kiểm soát được tác động tới người dùng và dịch vụ hợp lệ.

