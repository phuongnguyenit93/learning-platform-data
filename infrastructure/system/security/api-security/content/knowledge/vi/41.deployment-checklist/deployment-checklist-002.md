# Checklist authentication, token, key và secret

Một API có thể chạy đúng chức năng nhưng vẫn chưa sẵn sàng production nếu credential được cấp quá rộng, token được xác minh thiếu claim, signing key nằm trong image, API key dùng chung nhiều service hoặc không thể thu hồi khi có sự cố. Authentication và secret management vì vậy cần được kiểm tra như một phần của release, từ thiết kế identity flow đến build pipeline, deployment, runtime và khả năng rotation/revocation.

Trong module `SECURITY_API_SECURITY`, bảo mật API được đánh giá theo endpoint, object, tenant và luồng nghiệp vụ. Checklist này giúp đội phát triển và vận hành xác nhận ai đang gọi API, token đại diện cho principal nào, service nào được phép gọi service nào, secret được lưu ở đâu, key được rotate ra sao và làm thế nào chứng minh credential cũ không còn được chấp nhận sau khi deploy.

## Mục tiêu và cách sử dụng

Dùng checklist này trong design review, pre-production review, release readiness và sau khi thay đổi identity provider, signing key, API key policy hoặc secret store. Mỗi mục cần được đánh dấu bằng bằng chứng: config revision, test result, deployment reference hoặc owner xác nhận. Không đánh dấu đạt chỉ vì “đã cấu hình” nếu chưa kiểm tra hành vi thực tế.

Trạng thái gợi ý cho từng mục:

| Trạng thái | Ý nghĩa |
|---|---|
| PASS | Có bằng chứng xác nhận kiểm soát hoạt động trong environment mục tiêu |
| FAIL | Kiểm soát thiếu hoặc hành vi thực tế không đạt yêu cầu |
| N/A | Không áp dụng; phải ghi lý do và người xác nhận |
| BLOCKED | Chưa thể kiểm tra do thiếu quyền, dependency hoặc bằng chứng |
| FOLLOW-UP | Có chấp nhận rủi ro tạm thời, owner và deadline rõ ràng |

Không để `N/A` hoặc `FOLLOW-UP` thay cho quyết định rủi ro. Các mục liên quan credential compromise, token validation, secret exposure và least privilege cần được coi là release blocker nếu chưa có biện pháp bù trừ được phê duyệt.

## 1. Identity architecture và trust boundary

### 1.1. Xác định principal và loại client

- [ ] Đã lập danh sách caller của từng API: browser, mobile app, partner, backend service, worker, scheduler và operator.
- [ ] Đã phân biệt user identity, client/application identity và workload/service identity.
- [ ] Mỗi loại caller dùng flow phù hợp; không dùng một shared credential cho user, partner và internal service.
- [ ] Đã xác định issuer/identity provider, resource server/audience và owner của từng trust relationship.
- [ ] Có sơ đồ trust boundary: Internet, edge/gateway, application, service mesh, queue/worker và external provider.
- [ ] Không xem private network, CORS, source IP hoặc HTTPS là bằng chứng identity duy nhất.
- [ ] Đã xác định service nào xác thực token và service nào chịu trách nhiệm authorization trên object/tenant.
- [ ] Có inventory cho endpoint public, internal, admin, management và machine-to-machine.

### 1.2. Phân tách môi trường

- [ ] Development, test, staging và production dùng issuer/client registration/credential riêng khi phù hợp.
- [ ] Token production không được chấp nhận ở staging và ngược lại, trừ trust federation được thiết kế rõ.
- [ ] API key, client secret, signing key, certificate và webhook secret không được dùng chung giữa environment.
- [ ] Test account và synthetic tenant không có quyền truy cập production data.
- [ ] Secret của production không được mount vào developer workstation hoặc CI job không cần thiết.
- [ ] DNS, callback URI, redirect URI và audience được khai báo riêng theo environment.
- [ ] Không có default credential hoặc fallback secret dùng chung khi cấu hình environment bị thiếu.

### 1.3. Authentication không thay authorization

- [ ] Mỗi endpoint yêu cầu authentication phù hợp với mức độ nhạy cảm.
- [ ] Permission được kiểm tra theo action/function, object, tenant và property khi cần.
- [ ] Token hợp lệ nhưng thiếu scope/role bị từ chối.
- [ ] Caller có scope nhưng truy cập object ngoài tenant/owner scope vẫn bị từ chối.
- [ ] Internal service identity không tự động có quyền admin hoặc quyền trên mọi tenant.
- [ ] Authorization được thực hiện tại service sở hữu resource hoặc policy enforcement point có đủ context.

## 2. OAuth 2.0 và OpenID Connect flow

### 2.1. Chọn grant phù hợp

- [ ] Browser/mobile public client dùng Authorization Code Flow với PKCE theo khuyến nghị hiện hành.
- [ ] Confidential backend client bảo vệ client authentication bằng secret/certificate hoặc workload identity.
- [ ] Service-to-service dùng Client Credentials hoặc workload identity/federation phù hợp.
- [ ] Không dùng Resource Owner Password Credentials grant cho hệ thống mới.
- [ ] Không dùng Implicit Flow cho SPA/mobile mới; dùng Authorization Code + PKCE.
- [ ] Device Authorization Grant chỉ dùng cho thiết bị phù hợp và có user code/rate limit/verification URI được bảo vệ.
- [ ] Refresh token chỉ được cấp khi có nhu cầu và có rotation/reuse detection phù hợp.
- [ ] Không tự thiết kế grant hoặc token exchange riêng nếu chưa có threat model và review.

### 2.2. Redirect URI và client registration

- [ ] Redirect URI được allowlist chính xác; không dùng wildcard rộng hoặc prefix matching không an toàn.
- [ ] Redirect URI production dùng HTTPS; custom URI scheme trên mobile được đăng ký và kiểm soát phù hợp.
- [ ] `state` được tạo ngẫu nhiên, ràng buộc với browser session và kiểm tra khi callback.
- [ ] OIDC flow dùng `nonce` và xác minh nonce trong ID token.
- [ ] PKCE dùng `S256`; `code_verifier` được giữ bí mật trong client và không log.
- [ ] Authorization code có thời hạn ngắn, dùng một lần và gắn với client/redirect URI.
- [ ] Client secret không được nhúng vào SPA, mobile binary hoặc source map.
- [ ] Client registration không cho phép user tự thêm redirect URI, scope hoặc grant ngoài policy.

### 2.3. Phân biệt ID token và access token

- [ ] ID token chỉ được dùng để xác nhận authentication event cho client OIDC.
- [ ] Access token được gửi tới resource server có audience phù hợp.
- [ ] API không chấp nhận ID token thay access token.
- [ ] Client không dùng access token như bằng chứng đăng nhập cho một client khác.
- [ ] Claim `aud`, `iss`, `sub`, `exp`, `iat`, `nonce` và `azp` (khi áp dụng) được kiểm tra đúng ngữ cảnh.
- [ ] Không đưa dữ liệu nhạy cảm hoặc permission động quá rộng vào ID token.

## 3. Access token và JWT validation

### 3.1. Quy tắc xác minh JWT

- [ ] Chữ ký được xác minh bằng key thuộc issuer đã cấu hình tin cậy.
- [ ] Algorithm được allowlist theo policy; không chọn thuật toán theo giá trị không tin cậy trong token.
- [ ] Từ chối `alg=none` và algorithm downgrade ngoài policy.
- [ ] `iss` khớp chính xác issuer được cấu hình.
- [ ] `aud` chứa audience của API/resource server hiện tại.
- [ ] `exp` và `nbf` được kiểm tra với clock skew giới hạn.
- [ ] `iat` được kiểm tra khi policy cần giới hạn token quá cũ.
- [ ] `sub`/`client_id` được diễn giải đúng loại principal; không nhầm user với client.
- [ ] `scope`, role hoặc permission được map theo allowlist và action cụ thể.
- [ ] `typ`/token profile được kiểm tra khi hệ thống dùng nhiều loại JWT để tránh token substitution.
- [ ] `kid` chỉ được dùng để chọn key trong JWKS đã tin cậy; không lấy URL/key tùy ý từ token header.
- [ ] Claim tùy chỉnh được validate về kiểu, format, issuer và semantics.
- [ ] Token malformed, signature sai, issuer/audience sai, hết hạn hoặc chưa tới `nbf` đều bị từ chối.

Không chỉ decode JWT rồi đọc claim. Decode không xác minh chữ ký. Không gọi URL `jku`/`x5u` tùy ý từ token header để tải key; key discovery phải theo issuer configuration/JWKS URI đã tin cậy.

### 3.2. Lifetime và clock

- [ ] Access token có lifetime ngắn phù hợp rủi ro và trải nghiệm.
- [ ] Clock của issuer, resource server và workload được đồng bộ.
- [ ] Clock skew tolerance nhỏ, có lý do và được test.
- [ ] Token expiry được kiểm tra tại mỗi request hoặc theo cơ chế cache có giới hạn.
- [ ] Token không được lưu lâu hơn cần thiết trong browser storage, mobile storage, log hoặc crash report.
- [ ] Không dùng `iat` hoặc `exp` do client tự gửi làm quyết định ngoài token đã xác minh.

### 3.3. Scope, audience và tenant context

- [ ] Scope phản ánh action cụ thể như `invoice:read`, `invoice:create`, `file:download`.
- [ ] Token không có wildcard/admin scope nếu use case không cần.
- [ ] Audience giới hạn token cho API đích; token cấp cho service A không mặc nhiên dùng ở service B.
- [ ] Tenant context lấy từ principal/authorization context đã xác minh, không tin `tenantId` trong body/query/header.
- [ ] Service nhận kiểm tra delegation/actor context nếu service trung gian gọi thay user.
- [ ] Scope không thay object-level authorization; resource ownership/relationship vẫn được kiểm tra.

### 3.4. Opaque token và introspection

- [ ] Resource server gọi introspection endpoint được cấu hình tin cậy và xác thực client.
- [ ] Kiểm tra `active`, issuer, audience, scope, subject và expiry theo contract.
- [ ] Introspection cache TTL phù hợp rủi ro revoke; cache invalidation đã được test.
- [ ] Khi identity provider/introspection unavailable, behavior fail-open/closed được quyết định theo endpoint risk.
- [ ] Không log raw opaque token hoặc gửi token tới dịch vụ debug bên ngoài.

## 4. Refresh token, session và browser credential

### 4.1. Refresh token

- [ ] Refresh token chỉ cấp cho client/flow cần duy trì session.
- [ ] Refresh token được lưu trong nơi bảo vệ phù hợp với loại client.
- [ ] Có refresh token rotation hoặc cơ chế tương đương.
- [ ] Reuse detection/replay response được cấu hình và kiểm thử.
- [ ] Revoke token family/session khi phát hiện refresh token reuse theo policy.
- [ ] Refresh token có expiry, inactivity timeout và absolute lifetime phù hợp.
- [ ] Logout/revoke behavior được mô tả; client xóa bản local và server invalidates theo cơ chế.
- [ ] Không giả định đổi password tự động revoke mọi PAT/API key/service token.

### 4.2. Cookie và browser session

- [ ] Session cookie dùng `Secure`, `HttpOnly` và `SameSite` phù hợp.
- [ ] Cookie `Domain`/`Path` được giới hạn; không chia sẻ parent-domain rộng không cần thiết.
- [ ] Session ID được rotate sau login và privilege elevation.
- [ ] CSRF protection được bật cho cookie-authenticated state-changing request.
- [ ] Logout và session timeout invalidate server-side session khi kiến trúc yêu cầu.
- [ ] Không lưu long-lived access/refresh token trong `localStorage` nếu threat model yêu cầu chống XSS token theft.
- [ ] Error page, analytics, URL và browser history không làm lộ authorization code hoặc token.

### 4.3. Mobile và native client

- [ ] Dùng Authorization Code + PKCE và redirect URI đã đăng ký.
- [ ] Token được lưu trong secure storage của platform (Keychain/Keystore) phù hợp.
- [ ] Không nhúng client secret hoặc private signing key trong app binary.
- [ ] Deep link/app link được xác minh ownership và chống interception theo platform.
- [ ] Logout/account removal xử lý token và local cached data theo policy.
- [ ] Crash reporting/analytics không thu thập token, cookie hoặc authorization header.

## 5. API key và credential của partner

### 5.1. Thiết kế API key

- [ ] API key đại diện cho client/integration, không được nhầm với user authentication.
- [ ] Mỗi consumer có key riêng; không dùng một key chung cho nhiều partner/service.
- [ ] Key có public identifier/key ID riêng để tra cứu và revoke.
- [ ] Secret value đủ entropy, được tạo bằng CSPRNG và chỉ hiển thị khi cấp mới nếu mô hình yêu cầu.
- [ ] Key được scope theo API, action, tenant, environment và quota cần thiết.
- [ ] Có expiry/rotation policy và owner rõ ràng.
- [ ] Có trạng thái active/disabled/revoked và last-used metadata.
- [ ] Có thể revoke một key mà không phải tắt toàn bộ integration không liên quan.

### 5.2. Lưu trữ và xác minh API key

- [ ] Không lưu raw API key trong database nếu chỉ cần xác minh.
- [ ] Dùng hash/HMAC phù hợp với entropy và kiến trúc; bảo vệ pepper/HMAC key trong KMS/secret manager.
- [ ] So sánh secret theo cách tránh timing leak khi phù hợp.
- [ ] Lookup bằng key ID/prefix không bí mật, sau đó verify secret value.
- [ ] Không log key, query string chứa key hoặc header nguyên bản.
- [ ] Key chỉ được gửi qua TLS và không xuất hiện trong URL.
- [ ] Key không được nhúng trong JavaScript bundle, mobile app hoặc public repository.
- [ ] API key authentication được kết hợp với authorization theo scope/resource/tenant.

### 5.3. Partner onboarding và offboarding

- [ ] Partner được xác minh owner và use case trước khi cấp credential.
- [ ] Contract nêu audience, scope, quota, rate limit, support contact và rotation procedure.
- [ ] Credential sandbox và production tách biệt.
- [ ] Có quy trình thu hồi khi partner chấm dứt hợp đồng hoặc credential compromise.
- [ ] Có alert cho key dùng ngoài baseline, route hoặc region bất thường.
- [ ] Offboarding revoke key, token, webhook secret, certificate và access grant liên quan.

## 6. Service-to-service và workload identity

### 6.1. Workload identity

- [ ] Mỗi service/worker/scheduler có identity riêng hoặc nhóm identity có cùng trust boundary rõ.
- [ ] Ưu tiên workload identity/federation hoặc certificate ngắn hạn thay static shared secret khi nền tảng hỗ trợ.
- [ ] Nếu dùng client credentials, client authentication và secret rotation có owner/runbook.
- [ ] Token service-to-service có audience của service nhận và scope hẹp.
- [ ] mTLS xác minh peer nhưng service nhận vẫn kiểm tra action/object/tenant authorization.
- [ ] Service account không có quyền admin toàn hệ thống chỉ vì chạy trong cluster.
- [ ] Identity và permission của worker khác với user/actor khởi tạo job được lưu tách biệt.

### 6.2. Credential propagation

- [ ] Không forward inbound user token tới mọi downstream service theo mặc định.
- [ ] Token exchange/delegation dùng audience và scope phù hợp cho từng downstream.
- [ ] Không truyền Authorization header tới redirect host hoặc callback ngoài trust boundary.
- [ ] Không copy token vào queue message, log, trace baggage hoặc job payload.
- [ ] Downstream xác minh token/identity độc lập theo trust contract.
- [ ] Network policy và service mesh policy là lớp bổ sung, không thay authentication/authorization.

## 7. Secret management, KMS và HSM

### 7.1. Nguồn lưu trữ secret

- [ ] Secret production được lưu trong secret manager/KMS/HSM hoặc cơ chế quản lý được phê duyệt.
- [ ] Secret không hardcode trong source, Dockerfile, image layer, Helm values public, Terraform state không bảo vệ hoặc config repository.
- [ ] Secret không nằm trong `.env` được commit, sample config có giá trị thật hoặc shell history.
- [ ] Secret không được bake vào container image hoặc build artifact.
- [ ] Secret được mount/inject khi runtime theo identity của workload.
- [ ] Access policy giới hạn theo service, environment, secret path và operation (read/sign/rotate).
- [ ] Quyền đọc secret tách khỏi quyền quản trị policy và quyền xóa audit log khi khả thi.
- [ ] Secret manager audit logging được bật và có retention phù hợp.

### 7.2. Least privilege và separation of duties

- [ ] Developer không mặc nhiên đọc được production signing key hoặc database credential.
- [ ] CI build job không có quyền đọc secret production nếu chỉ cần build artifact.
- [ ] Deployment identity chỉ đọc secret cần cho workload/environment tương ứng.
- [ ] Application runtime chỉ được đọc secret; không được export private key nếu có thể dùng KMS sign/decrypt API.
- [ ] Quyền tạo key, ký token, rotate key và thay trust policy được phân tách phù hợp.
- [ ] Break-glass access có approval, thời hạn, audit và review sau sử dụng.

### 7.3. KMS/HSM và key material

- [ ] Signing/encryption key được tạo và lưu trong KMS/HSM khi rủi ro yêu cầu.
- [ ] Private key không được export nếu use case cho phép ký qua KMS/HSM.
- [ ] Key policy giới hạn principal, operation, region và environment.
- [ ] Key alias/version/owner/purpose/algorithm được inventory.
- [ ] Backup, disaster recovery và key deletion có quy trình được kiểm soát.
- [ ] Key rotation không phá khả năng decrypt dữ liệu cũ nếu encryption key được dùng cho data-at-rest; có re-encryption plan riêng.
- [ ] Key deletion có retention/grace period phù hợp và không thể bị một operator đơn lẻ xóa ngoài policy.

### 7.4. Secret format và metadata

- [ ] Secret có owner, purpose, consumer, environment, created_at, last_rotated_at và expiry/rotation target.
- [ ] Secret version được quản lý; workload đọc version rõ ràng hoặc alias theo rollout plan.
- [ ] Không đặt secret value trong tên resource, label, annotation, tag hoặc metric.
- [ ] Không dùng một secret cho nhiều mục đích không liên quan.
- [ ] Secret không được copy vào support bundle, crash dump hoặc debug endpoint.

## 8. Rotation, revocation và emergency response

### 8.1. Rotation thông thường

- [ ] Có lịch rotation theo loại credential và mức độ rủi ro.
- [ ] Có inventory consumer trước khi rotate.
- [ ] Quy trình tạo credential mới, cập nhật consumer, xác minh và revoke credential cũ được tài liệu hóa.
- [ ] Nếu cần overlap, thời gian overlap có giới hạn, owner và deadline.
- [ ] Consumer được kiểm tra bằng key ID/version mới; không in raw secret để xác minh.
- [ ] Credential cũ bị revoke sau khi migration hoàn tất.
- [ ] Có test multi-region, replica, scheduled job và disaster recovery consumer.

### 8.2. Revocation behavior

- [ ] Có cách revoke access token/opaque token/session theo kiến trúc.
- [ ] Refresh token family/reuse behavior được định nghĩa.
- [ ] JWT revocation strategy được nêu rõ: short expiry, denylist, session version, introspection hoặc key invalidation.
- [ ] API key có endpoint/console/automation để disable theo key ID.
- [ ] Certificate revocation và trust bundle update có quy trình.
- [ ] Webhook signing secret có key version/overlap policy.
- [ ] JWKS, introspection, session và gateway cache TTL được biết và kiểm thử.
- [ ] Long-lived connections và background jobs có policy khi credential bị revoke.

### 8.3. Emergency rotation drill

- [ ] Có runbook cho lộ API key, client secret, refresh token, signing key và certificate.
- [ ] Incident commander/credential owner/platform owner được xác định.
- [ ] Có quyền revoke khẩn cấp nhưng vẫn audit.
- [ ] Có cách xác minh credential cũ bị từ chối ở mọi verifier/region.
- [ ] Có kế hoạch xử lý outage nếu signing key hoặc shared client credential phải invalidate ngay.
- [ ] Có quy trình tìm usage, data access và persistence trong exposure window.
- [ ] Có diễn tập định kỳ bằng sentinel/test credential, không dùng secret production thật.

## 9. CI/CD và build pipeline

### 9.1. Source và dependency checks

- [ ] Secret scanning chạy trên commit/PR và repository history theo policy.
- [ ] Pipeline fail hoặc tạo approval gate khi phát hiện secret có khả năng hoạt động.
- [ ] Không echo environment, credential file hoặc toàn bộ runtime config trong build log.
- [ ] Shell tracing/debug mode bị tắt cho command có secret.
- [ ] Test fixture dùng dummy credential; không dùng production token để chạy integration test.
- [ ] Secret scan có test sentinel để xác minh scanner và masking hoạt động.

### 9.2. Build artifact

- [ ] Container image, source map, frontend bundle, package và debug symbol không chứa secret.
- [ ] Build artifact không chứa `.env`, private key, service account JSON hoặc token cache.
- [ ] Image layer history không còn secret bị xóa ở layer sau.
- [ ] Artifact registry access được giới hạn và audit.
- [ ] Build output và SBOM/provenance không chứa credential hoặc secret-bearing environment values.

### 9.3. Deployment identity

- [ ] CI deploy dùng identity riêng và scope tối thiểu.
- [ ] Ưu tiên OIDC/workload federation từ CI sang cloud thay static cloud access key dài hạn khi khả thi.
- [ ] Token federation có issuer, subject/repository/branch/environment condition và audience giới hạn.
- [ ] Pull request từ fork/untrusted branch không được đọc production secrets.
- [ ] Production deploy có approval/branch protection phù hợp.
- [ ] Rollback pipeline không cần tái sử dụng credential đã bị revoke hoặc secret cũ.

## 10. Deployment configuration và startup behavior

### 10.1. Cấu hình resource server

- [ ] Issuer URI, audience, JWKS/introspection endpoint lấy từ config được quản lý, không từ request.
- [ ] Allowed algorithms, clock skew và token profile được cấu hình tường minh.
- [ ] TLS verification bật cho issuer, JWKS, introspection và secret manager.
- [ ] Không có `permitAll` hoặc fallback authentication cho route production ngoài policy.
- [ ] Startup/readiness fail nếu trust configuration bắt buộc bị thiếu hoặc sai.
- [ ] Không in token, secret hoặc private config khi startup validation fail.
- [ ] Key/JWKS refresh có timeout, retry/backoff và cache limit.

### 10.2. Secret injection và rotation runtime

- [ ] Workload nhận đúng secret version cho environment.
- [ ] File mount/volume có permission tối thiểu; không world-readable.
- [ ] Secret không được expose qua environment dump, actuator/config endpoint hoặc diagnostics.
- [ ] Nếu secret rotation cần restart/reload, cơ chế và thời gian propagation được biết.
- [ ] Application không giữ secret cũ vô thời hạn sau rotation.
- [ ] Secret manager outage behavior được quyết định: startup fail, use cached version có TTL hay degrade theo risk.
- [ ] Không ghi secret value trong health/readiness output.

### 10.3. Không có insecure fallback

- [ ] Không dùng development signing key hoặc default API key khi JWKS/secret manager không truy cập được.
- [ ] Không tắt signature validation để khôi phục availability.
- [ ] Không chấp nhận `alg=none`, token thiếu audience hoặc issuer unknown trong fallback mode.
- [ ] Không chuyển từ mTLS sang plaintext hoặc anonymous service call khi certificate lỗi.
- [ ] Fallback chỉ áp dụng cho endpoint/use case được phê duyệt, có giới hạn và alert.

## 11. Pre-deployment verification

### 11.1. Test authentication negative cases

- [ ] Không có credential: `401` hoặc response theo contract.
- [ ] Credential malformed/empty: từ chối an toàn.
- [ ] Token hết hạn hoặc chưa có hiệu lực: từ chối.
- [ ] JWT signature sai hoặc key unknown: từ chối.
- [ ] Issuer/audience sai: từ chối.
- [ ] Token loại sai (ID token thay access token): từ chối.
- [ ] Scope thiếu: từ chối theo contract.
- [ ] API key revoked/expired: từ chối.
- [ ] Refresh token reuse: kích hoạt policy phát hiện/revoke family.
- [ ] Certificate expired/revoked/wrong SAN: handshake hoặc auth bị từ chối.

### 11.2. Test authorization và identity boundary

- [ ] User đúng tenant truy cập resource của mình thành công.
- [ ] User khác tenant không đọc/sửa object ngoài scope.
- [ ] Service identity đúng nhưng thiếu action scope bị từ chối.
- [ ] Service có scope nhưng resource/tenant không hợp lệ vẫn bị từ chối.
- [ ] Header giả `X-User-Id`, `X-Tenant-Id`, `X-Internal-Caller` không thay principal.
- [ ] Token cấp cho API A không dùng được tại API B.
- [ ] Internal route không bypass auth khi gọi direct origin.
- [ ] Admin action có permission riêng, audit và approval nếu cần.

### 11.3. Test rotation/revocation

- [ ] Key mới được chấp nhận sau rollout.
- [ ] Key cũ bị từ chối sau thời điểm revoke.
- [ ] JWKS/cache ở mọi region cập nhật đúng.
- [ ] Token ký bằng signing key cũ bị xử lý theo emergency policy.
- [ ] Refresh token cũ không cấp access token mới sau revoke.
- [ ] Consumer/worker/scheduler không còn dùng credential cũ.
- [ ] Rotation không làm credential environment khác bị thay đổi.

### 11.4. Test secret exposure

- [ ] Secret sentinel không xuất hiện trong application/gateway/CI logs.
- [ ] Secret không xuất hiện trong container image, source map hoặc artifact.
- [ ] Actuator/debug/health endpoint không trả secret/config nhạy cảm.
- [ ] Exception, trace attribute, baggage và analytics không chứa token/cookie.
- [ ] Support bundle/crash report không chứa credential ngoài policy.

## 12. Rollout, canary và rollback

### 12.1. Rollout theo đợt

- [ ] Deploy trust configuration/key set mới trước khi chuyển issuer/consumer theo đúng protocol.
- [ ] Canary xác minh token mới, route nhạy cảm và downstream service.
- [ ] Theo dõi `401/403`, token validation error, JWKS refresh, secret fetch failure và latency.
- [ ] Xác minh cả region/replica/worker và scheduled job.
- [ ] Có owner và thời gian theo dõi sau rollout.
- [ ] Revoke credential cũ đúng thời điểm, không để overlap không giới hạn.

### 12.2. Rollback an toàn

- [ ] Rollback application không làm khôi phục secret đã compromise.
- [ ] Rollback config không đưa signing key cũ trở lại trust set nếu key đã bị lộ.
- [ ] Có kế hoạch tương thích token/key version giữa các release.
- [ ] Nếu cần tạm chấp nhận key cũ trong migration bình thường, có deadline và approval; emergency compromise phải dùng policy khác.
- [ ] Không rollback bằng cách tắt authentication, signature validation hoặc authorization.
- [ ] Nếu không thể khôi phục an toàn, disable route/feature có rủi ro và thông báo owner.

## 13. Runtime monitoring và alert

- [ ] Theo dõi authentication success/failure theo route, client và credential ID.
- [ ] Theo dõi token issuer/audience/scope mismatch.
- [ ] Alert khi revoked key/token vẫn được thử hoặc còn request thành công sau revoke.
- [ ] Theo dõi refresh token reuse, client secret failure và certificate revocation event.
- [ ] Theo dõi secret manager/KMS read, sign, decrypt, policy change và unusual principal.
- [ ] Alert khi tạo API key/client secret/service account ngoài workflow.
- [ ] Theo dõi key rotation age, expiry sắp tới và certificate expiration.
- [ ] Theo dõi auth failure spike, brute force, credential stuffing và unusual geography/network.
- [ ] Theo dõi service-to-service call từ workload không nằm trong allowlist.
- [ ] Log event có request ID/trace ID và credential ID; tuyệt đối không log raw secret.
- [ ] Metrics không dùng token, user ID hoặc raw key làm label có cardinality vô hạn.
- [ ] Có runbook gắn với alert và owner chịu trách nhiệm.

## 14. Release evidence và ownership

Mỗi release nên lưu evidence tối thiểu:

| Evidence | Nội dung cần có |
|---|---|
| Identity design | Principal/client/workload, issuer, audience, flow và trust boundary |
| Token validation tests | Positive/negative cases, algorithm/issuer/audience/scope/expiry |
| Authorization tests | User/service, tenant/object/property và expected decision |
| Secret inventory | Credential ID/alias, owner, consumer, environment, expiry/rotation target; không có value |
| Rotation evidence | Key version cũ/mới, rollout time, revoke verification và cache propagation |
| CI/CD scan | Secret scan result, artifact inspection và pipeline identity |
| Deployment config | Revision/fingerprint và config validation result; không đính kèm secret |
| Runtime smoke test | Authentication, authorization và downstream call sau deploy |
| Monitoring | Dashboard/alert owner, test alert và runbook link |
| Approval | Service owner/security/platform sign-off và risk exception nếu có |

Đặt owner cụ thể cho mỗi follow-up, deadline và cách xác minh. Không lưu raw token/API key trong release evidence. Dùng key ID, secret version, certificate serial hoặc fingerprint an toàn.

## 15. Checklist nhanh trước khi bật production traffic

- [ ] Trust boundary, caller inventory và identity owner đã rõ.
- [ ] OAuth/OIDC flow đúng loại client; redirect URI, state, nonce và PKCE đã test.
- [ ] Resource server xác minh chữ ký, issuer, audience, expiry, token type và scope.
- [ ] API không chấp nhận ID token thay access token.
- [ ] Access/refresh token lifetime, rotation và revocation có policy.
- [ ] API key riêng theo consumer, scope hẹp, có key ID và revoke path.
- [ ] Workload identity/service account riêng, không dùng shared admin secret.
- [ ] Secret nằm trong secret manager/KMS/HSM, không nằm trong source/image/log/artifact.
- [ ] CI/CD identity least privilege; untrusted PR không đọc production secret.
- [ ] JWKS/introspection/cache/secret refresh behavior đã test.
- [ ] Key rotation và emergency revoke đã có owner/runbook.
- [ ] Negative authn/authz tests pass; cross-tenant và direct-origin đã được kiểm tra.
- [ ] Secret sentinel không xuất hiện trong log/trace/CI artifact.
- [ ] Canary rollout, monitoring và rollback plan đã sẵn sàng.
- [ ] Credential cũ/temporary credential được revoke sau migration.
- [ ] Release evidence và risk exception được lưu ở nơi có access control.

## 16. Quyết định release

Trước khi mở traffic production, người chịu trách nhiệm cần xác nhận:

| Câu hỏi | Điều kiện để chấp thuận |
|---|---|
| Ai có thể gọi API? | Principal và client identity được xác minh; không có shared credential ngoài thiết kế |
| Token có dành cho API này? | Issuer, audience, signature, time và token profile được kiểm tra |
| Caller được làm gì? | Scope/function/object/tenant authorization có test |
| Secret được bảo vệ ra sao? | Secret store, least privilege, no source/image/log exposure |
| Có thể rotate/revoke không? | Owner, runbook, cache propagation và verification đã rõ |
| Nếu credential lộ thì sao? | Incident path, evidence, blast-radius query và recovery đã sẵn sàng |
| Release có quan sát được không? | Logs/metrics/alerts có credential ID và request correlation nhưng không chứa secret |

Nếu câu trả lời chưa rõ, đánh dấu BLOCKED hoặc ghi risk exception có người phê duyệt, phạm vi, biện pháp bù trừ và hạn chót. Không coi việc deploy thành công là bằng chứng authentication và secret management an toàn.

## Kết luận

Authentication, token, key và secret phải được kiểm tra xuyên suốt vòng đời triển khai: thiết kế flow, xác minh token, cấp scope, lưu secret, build artifact, inject runtime, rotate/revoke và giám sát sau deploy. Một release chỉ sẵn sàng khi credential có owner và scope rõ, verifier kiểm tra đúng issuer/audience/signature, secret không bị phát tán, credential cũ có thể bị vô hiệu hóa và các đường gọi thực tế đã được kiểm thử. Checklist này cần được lưu cùng release evidence để lần triển khai tiếp theo có thể xác minh lại thay vì dựa vào giả định.
