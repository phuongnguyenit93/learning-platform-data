# Containment khi token hoặc API key bị lộ

Khi token hoặc API key bị lộ, rủi ro không dừng ở việc một chuỗi bí mật xuất hiện sai chỗ. Credential đó có thể cho phép đọc dữ liệu, thay đổi tài nguyên, gọi API thay mặt service, tạo token khác hoặc duy trì quyền truy cập sau khi người dùng đã đăng xuất. Thời gian từ lúc phát hiện đến lúc thu hồi quyền sử dụng credential thường quyết định phạm vi thiệt hại.

Ứng phó cần vừa chặn khả năng tiếp tục sử dụng credential, vừa giữ đủ bằng chứng để xác định ai đã dùng, truy cập tài nguyên nào và liệu có persistence hay không. Hành động cụ thể phụ thuộc loại credential: access token, refresh token, JWT signing key, API key, personal access token, service account secret, mTLS certificate hay webhook secret. Thu hồi một API key không tự động vô hiệu hóa JWT đã phát hành; thay signing key cũng có thể ảnh hưởng nhiều service cùng lúc.

Trong module `SECURITY_API_SECURITY`, bài này tập trung vào containment có thứ tự, theo credential và blast radius. Quy trình phải có owner, quyền thực hiện, tiêu chí xác minh và phương án phục hồi rõ ràng. Không đưa raw secret vào log, ticket hoặc báo cáo sự cố.

## Mục tiêu học tập

Sau bài này, người học có thể:

- Nhận diện dấu hiệu token/API key compromise và phân biệt với credential xuất hiện trong môi trường test.
- Triage loại credential, chủ sở hữu, scope, audience, expiry và nơi credential được sử dụng.
- Chọn hành động revoke, disable, rotate hoặc invalidate phù hợp với từng loại credential.
- Contain access token, refresh token, JWT signing key, API key, service credential, mTLS certificate và webhook secret.
- Đánh giá blast radius qua audit log, API gateway, identity provider và downstream service.
- Bảo toàn evidence mà không phát tán secret thêm.
- Phục hồi consumer/service có kiểm soát và xác minh credential cũ không còn hoạt động.
- Viết timeline, incident record, communication và post-incident actions có thể kiểm tra.

## 1. Khi nào coi là sự cố lộ credential?

### 1.1. Credential compromise

Credential được coi là có khả năng bị compromise khi người không được phép có thể đọc, sao chép hoặc sử dụng nó. Không cần chờ thấy request độc hại mới bắt đầu containment. Các trường hợp thường gặp:

- Access token/API key xuất hiện trong Git repository, commit, issue hoặc pull request công khai.
- Secret nằm trong CI/CD log, build artifact, crash dump, support bundle hoặc terminal recording.
- Token được gửi qua chat/email không đúng kênh hoặc đính kèm trong ticket có nhiều người xem.
- Credential nằm trong mobile/web bundle, source map, JavaScript config hoặc image/container layer.
- Secret bị ghi vào application log, tracing attribute, analytics event hoặc URL query string.
- Laptop, runner, workload hoặc service account có credential bị mất quyền kiểm soát.
- Audit log cho thấy credential được sử dụng từ nguồn, thời điểm hoặc hành vi không phù hợp.
- Refresh token bị replay, API key bị sử dụng ngoài lịch trình hoặc certificate private key bị truy cập trái phép.

Nếu chỉ thấy chuỗi có hình dạng giống token nhưng không xác định được đó là secret thật, vẫn cần xử lý như một lead. Kiểm tra issuer, key ID, credential ID hoặc fingerprint bằng công cụ an toàn; không paste chuỗi vào website kiểm tra token công cộng.

### 1.2. Phân biệt exposure và confirmed misuse

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Suspected exposure | Credential có thể đã lọt ra ngoài trust boundary | Triage nhanh, xác định owner/scope và chuẩn bị revoke |
| Confirmed exposure | Có bằng chứng người không được phép có thể đọc/copy credential | Containment theo mức rủi ro; thường revoke/rotate ngay |
| Confirmed misuse | Có dấu hiệu credential đã được dùng trái phép | Containment khẩn cấp, điều tra blast radius và persistence |
| False positive | Giá trị là dummy/đã hết hiệu lực/không phải credential | Ghi bằng chứng xác minh và đóng lead theo quy trình |

Không trì hoãn revoke chỉ để đạt mức “confirmed misuse” nếu credential có quyền cao và exposure đã rõ. Một secret còn hiệu lực trong public repository nên được coi là compromised kể cả chưa thấy request bất thường.

### 1.3. Dấu hiệu sử dụng trái phép

Các tín hiệu có thể gồm:

- Request từ ASN, network, region hoặc device chưa từng xuất hiện trong baseline.
- API call ngoài giờ hoặc tăng đột biến theo credential ID.
- Endpoint, scope hoặc audience không phù hợp với workload sở hữu key.
- Nhiều lần `401`, introspection failure hoặc refresh token reuse.
- Thay đổi role, permission, webhook destination, OAuth client hoặc service configuration.
- Tạo API key mới, service account mới, token mới hoặc thêm credential vào secret store.
- Download/export dữ liệu lớn, truy cập nhiều tenant/object hoặc enumeration.
- Gọi admin endpoint, billing/payment, user management hoặc key management không theo workflow.

IP bất thường là tín hiệu, không phải kết luận. NAT, proxy, VPN, cloud egress và workload autoscaling có thể làm thay đổi nguồn request. Đối chiếu thêm credential ID, actor, route, scope, device/workload identity, request ID và hành vi nghiệp vụ.

## 2. Nguyên tắc containment

### 2.1. Chặn khả năng sử dụng trước, điều tra song song

Khi credential đang có nguy cơ bị khai thác, ưu tiên ngăn request mới được xác thực bằng credential đó. Evidence preservation cần diễn ra song song nếu có thể, nhưng không để việc thu thập log hoặc hoàn thiện báo cáo kéo dài thời gian attacker còn quyền truy cập.

Thứ tự thường dùng:

1. Mở incident record và xác định incident commander/credential owner.
2. Xác minh loại credential và xác định issuer/system có quyền revoke.
3. Chụp metadata và audit context cần thiết mà không sao chép raw secret.
4. Revoke/disable credential hoặc áp biện pháp chặn tạm thời phù hợp.
5. Xác minh credential cũ bị từ chối trên đường xác thực thực tế.
6. Đánh giá request đã xảy ra, resource bị truy cập và persistence.
7. Cấp credential mới theo nguyên tắc least privilege và triển khai cho consumer hợp lệ.
8. Theo dõi lỗi, retry, request tiếp tục dùng credential cũ và dấu hiệu tái xâm nhập.

Với credential cấp cao, đang bị lạm dụng hoặc public exposure, bước revoke có thể phải thực hiện ngay sau khi xác định credential ID/owner, không đợi hoàn tất toàn bộ bước triage.

### 2.2. Thu hồi và xoay vòng là hai hành động khác nhau

- **Revoke/disable:** làm credential hiện tại không còn được chấp nhận.
- **Rotate:** tạo credential mới, chuyển consumer hợp lệ sang credential mới và loại bỏ credential cũ.
- **Invalidate:** làm token/session hoặc chữ ký cũ không còn được chấp nhận theo cơ chế xác minh.
- **Quarantine:** cô lập workload/consumer hoặc route khi chưa thể revoke ngay mà không gây outage lớn.

Tạo key mới mà vẫn để key cũ hoạt động vô thời hạn không phải containment. Revoke key cũ mà không cập nhật consumer có thể làm service outage. Incident plan phải ghi cả hai phần và thứ tự chuyển đổi.

### 2.3. Ưu tiên theo blast radius

Xếp hạng credential theo:

- Privilege: read, write, admin, key management, impersonation.
- Scope/audience: một API hay nhiều service/tenant.
- Thời hạn và khả năng refresh/renew.
- Có thể tạo credential khác hoặc thay đổi trust policy hay không.
- Dữ liệu và workflow có thể truy cập.
- Mức độ exposure: public, internal broad access, restricted channel.
- Bằng chứng misuse và thời gian credential có thể đã bị lộ.

Credential ký JWT hoặc root/service account có thể ảnh hưởng nhiều workload hơn một key chỉ đọc một resource. Nếu chưa xác định được scope, tạm coi theo quyền cao nhất đã cấp cho credential đó cho đến khi có bằng chứng ngược lại.

### 2.4. Một incident, một nguồn điều phối

Chỉ định một incident commander hoặc người điều phối containment. Credential owner, IAM/platform, service owner, SOC và privacy/legal (nếu cần) phối hợp theo role. Tránh nhiều nhóm tự rotate cùng một key hoặc thay đổi trust policy đồng thời mà không có một timeline chung.

Ghi lại người yêu cầu, người phê duyệt, người thực hiện và người xác minh cho các hành động quan trọng. Break-glass access phải được audit và thu hồi sau incident.

## 3. Triage trong những phút đầu

### 3.1. Thu thập metadata trước khi thay đổi

Ghi các trường sau nếu có:

| Trường | Mục đích |
|---|---|
| Credential type | Access/refresh token, API key, signing key, certificate, webhook secret… |
| Credential ID / `kid` / key alias | Xác định đúng credential để revoke |
| Issuer / owner | Identity provider, team hoặc workload chịu trách nhiệm |
| Subject / client ID / service account | Principal mà credential đại diện |
| Audience / resource server | API nào chấp nhận credential |
| Scope / roles / permissions | Quyền thực tế đã cấp |
| Issued at / expiry / last rotation | Thời gian credential có hiệu lực |
| Created/used timestamps | Khoảng thời gian cần điều tra |
| Consumer inventory | Service, job, runner, mobile/web client dùng credential |
| Exposure source | Git, CI log, laptop, support bundle, telemetry… |
| Detection evidence | Alert, audit event, reporter và timestamp |

Không ghi raw token, private key hoặc secret value vào incident ticket. Dùng ID, alias hoặc fingerprint an toàn do hệ thống cấp.

### 3.2. Xác định credential có còn hiệu lực

Kiểm tra qua issuer/secret manager/API management console hoặc metadata registry. Với JWT, có thể xác minh `iss`, `aud`, `sub`, `scope`, `kid`, `iat`, `exp` bằng tooling nội bộ đã được phê duyệt; không gửi token tới decoder website bên ngoài. Không coi việc `exp` còn xa là điều kiện duy nhất: token có thể đã bị revoke, key có thể bị rotation hoặc audience không còn chấp nhận.

Với API key, kiểm tra key ID, status, last-used time, allowed scopes, IP/network restriction và owner. Với certificate, kiểm tra subject/SAN, issuer, serial number, validity và nơi trust bundle được cài.

### 3.3. Xác định exposure window

Ước lượng thời điểm đầu tiên credential có thể bị đọc và thời điểm containment. Ví dụ secret xuất hiện trong commit public lúc 09:00, bị xóa lúc 09:15, nhưng bản clone/fork/cache có thể đã lấy trước đó. Xóa file không làm secret trở lại an toàn.

Nếu không biết exposure start, dùng thời điểm sớm nhất có thể và mở rộng truy vấn audit từ trước mốc đó theo retention. Ghi rõ mức bất định thay vì chọn một mốc chính xác không có bằng chứng.

### 3.4. Chọn mức độ incident

Phân loại dựa trên privilege, exposure và misuse:

- **Critical:** signing/root/admin credential, public exposure, confirmed misuse hoặc khả năng impersonate nhiều workload/tenant.
- **High:** credential production có write/admin scope, dữ liệu nhạy cảm hoặc refresh capability.
- **Medium:** credential scope hẹp, read-only, exposure nội bộ giới hạn và chưa có dấu hiệu misuse.
- **Low/Informational:** dummy, revoked/expired trước exposure hoặc không thể dùng để xác thực sau khi đã kiểm tra.

Đây là gợi ý triage, không thay thế severity policy của tổ chức. Khi chưa đủ thông tin, chọn mức tạm thời thận trọng và cập nhật khi có evidence.

## 4. Playbook containment tổng quát

### 4.1. Trong 0–15 phút

1. Mở incident và ghi detection time, reporter, service, environment.
2. Xác định credential ID/alias, owner, issuer và privilege.
3. Xác định nơi secret xuất hiện và ai có thể truy cập nguồn đó.
4. Lấy metadata/audit snapshot tối thiểu trước khi log bị rotate hoặc retention hết.
5. Revoke/disable credential hoặc chặn principal/route theo phương án được phê duyệt.
6. Xác minh request mới dùng credential cũ bị từ chối.
7. Nếu có misuse, cô lập consumer/workload liên quan và giữ runtime evidence theo quy trình.

### 4.2. Trong 15–60 phút

- Lập danh sách consumer, service, job và environment sử dụng credential.
- Tìm lần sử dụng cuối cùng và hoạt động kể từ exposure window.
- Kiểm tra thay đổi quyền, key, user, webhook, secret store và persistence.
- Xác định dữ liệu/object/tenant có thể bị truy cập hoặc thay đổi.
- Rotate credential hoặc signing/certificate material theo loại.
- Cập nhật consumer theo đợt; theo dõi authentication failure và retry.
- Thông báo các service owner bị ảnh hưởng bằng incident channel được phê duyệt.

### 4.3. Trong 1–4 giờ và giai đoạn phục hồi

- Hoàn tất inventory và blast-radius assessment.
- Đối chiếu audit logs, gateway logs, application traces và data access logs.
- Khôi phục service với credential mới, scope tối thiểu và secret injection an toàn.
- Xác minh credential cũ bị từ chối ở mọi verifier/cache/region liên quan.
- Theo dõi dấu hiệu attacker tiếp tục thử key cũ hoặc dùng credential khác.
- Ghi finding, impact đã chứng minh, phần chưa xác định và remediation owner.
- Chuẩn bị post-incident review và regression test.

Mốc thời gian là mục tiêu tham khảo. Incident commander điều chỉnh theo severity, khả năng revoke và tác động availability.

## 5. Containment theo từng loại credential

### 5.1. OAuth access token dạng opaque

Opaque access token thường được resource server xác minh qua introspection hoặc một cơ chế lookup nội bộ. Nếu token bị lộ:

1. Dùng token ID/reference hoặc session record để xác định đúng token, không paste raw token vào ticket.
2. Revoke token tại authorization server hoặc đánh dấu inactive theo cơ chế được hỗ trợ.
3. Nếu token gắn với client/session/device bị compromise, xem xét revoke toàn bộ token liên quan theo policy.
4. Kiểm tra introspection cache và resource server cache; giảm TTL hoặc purge cache nếu revoke chưa phản ánh ngay.
5. Nếu refresh token còn hiệu lực, revoke refresh token hoặc token family tương ứng.
6. Xác minh introspection trả `active=false` và resource server từ chối request mới.

Nếu introspection result được cache quá lâu, token có thể vẫn được chấp nhận trong khoảng cache TTL. Incident record phải ghi thời gian propagation thực tế, không chỉ thời điểm bấm revoke.

### 5.2. JWT access token đã ký

JWT access token thường được xác minh offline bằng public key. Vì vậy, revoke một token riêng lẻ không tự động làm mọi resource server ngừng chấp nhận nó.

Các lựa chọn containment tùy kiến trúc:

- Dùng denylist theo `jti` hoặc token fingerprint cho token bị lộ; cần bảo vệ store và TTL tới hết token expiry.
- Kiểm tra session/token version hoặc user/client status ở mỗi request hoặc qua cache ngắn hạn.
- Revoke refresh token/session để không phát hành access token mới.
- Rút ngắn acceptance window bằng policy hoặc introspection cho route nhạy cảm.
- Nếu signing key bị compromise, xử lý theo playbook signing key, không chỉ revoke một JWT.

Không thể “xóa JWT khỏi client” sau khi phát hành. Nếu resource server chỉ kiểm tra chữ ký và expiry, token đã phát hành vẫn hợp lệ đến `exp` trừ khi có cơ chế revocation/denylist hoặc key invalidation. Ghi rõ giới hạn này trong containment plan.

### 5.3. Refresh token

Refresh token có thể tạo access token mới và thường có tuổi thọ dài hơn access token. Nếu bị lộ:

- Revoke refresh token hoặc toàn bộ token family/session theo semantics của authorization server.
- Với refresh token rotation, kiểm tra reuse detection; một token cũ được dùng lại có thể là dấu hiệu replay.
- Revoke token descendants đã được cấp từ family nếu provider hỗ trợ.
- Buộc re-authentication cho user/client bị ảnh hưởng khi cần.
- Kiểm tra password reset, MFA/session recovery và thay đổi account gần thời điểm exposure.
- Xác minh refresh cũ thất bại và không thể cấp access token mới.

Chỉ revoke access token hiện tại là chưa đủ nếu refresh token vẫn hoạt động.

### 5.4. JWT signing key hoặc private key của issuer

Signing key compromise có blast radius lớn: attacker có thể ký token giả mạo issuer cho mọi audience/resource server tin key đó. Đây là incident cấp identity platform.

Containment:

1. Xác định `kid`, algorithm, issuer, key alias và thời điểm key có thể bị lộ.
2. Dừng sử dụng private key bị compromise để ký token mới.
3. Tạo key pair mới trong HSM/KMS hoặc key management boundary được bảo vệ.
4. Publish public key mới theo JWKS/trust distribution mechanism.
5. Loại public key cũ khỏi tập key được chấp nhận theo emergency policy; xác định cache/refresh behavior ở mọi resource server.
6. Revoke/invalidate token được ký bằng `kid` bị compromise, kể cả token còn `exp` xa.
7. Kiểm tra token giả, issuer/audience bị impersonate và thay đổi identity/role trong exposure window.
8. Xác minh mọi verifier đã từ chối signature từ key cũ.

Trong rotation bình thường, có thể giữ public key cũ trong overlap để verify token đã phát hành. Trong compromise, overlap đó có thể cho attacker tiếp tục ký token giả; quyết định giữ hay loại key phải theo emergency containment, chấp nhận re-authentication hoặc service disruption nếu cần.

Không chỉ xóa private key khỏi filesystem rồi coi incident đã kết thúc. Kiểm tra backup, CI variable, HSM/KMS access, signing service, developer workstation và replica/region.

### 5.5. API key

API key thường đại diện cho client, integration hoặc workload. Key có thể được xác minh trực tiếp, qua database lookup hoặc gateway. Containment nên dựa vào key ID, không dựa vào việc tìm và copy raw value.

1. Xác định key ID, owner, consumer, scopes, environment và last-used timestamp.
2. Disable/revoke key cũ tại nơi xác thực authoritative (API management, gateway hoặc application key registry).
3. Nếu key có thể được dùng ở nhiều region/cache, purge hoặc giảm cache TTL và xác minh propagation.
4. Tạo key mới với scope/resource/network restriction tối thiểu.
5. Cập nhật consumer từ secret manager; không gửi key mới qua chat hoặc ticket.
6. Xác minh consumer hợp lệ hoạt động với key mới và key cũ nhận `401/403` theo contract.
7. Thu hồi key cũ vĩnh viễn sau khi consumer đã chuyển; không giữ overlap ngoài thời hạn được phê duyệt.

Nếu key là master key có quyền tạo/revoke key khác, kiểm tra key descendants và administrative actions. Nếu key không có ID riêng hoặc không thể xác định consumer, cân nhắc revoke toàn bộ key trong namespace bị ảnh hưởng và phối hợp outage plan.

### 5.6. Personal access token (PAT) và developer token

PAT có thể gắn với user và tồn tại lâu. Khi lộ:

- Revoke PAT cụ thể từ identity/developer portal.
- Xác định repositories, packages, APIs và organization scope có thể truy cập.
- Kiểm tra token đã tạo deploy key, webhook, OAuth app hoặc credential mới không.
- Nếu user account có dấu hiệu compromise, xử lý session/password/MFA theo account incident playbook.
- Kiểm tra token còn lại của cùng user nếu chúng có chung nguồn exposure.

Không mặc định đổi password sẽ revoke PAT. Xác minh trạng thái từng loại credential ở issuer.

### 5.7. Service account secret / client secret

Service account/client secret có thể được dùng để lấy access token mới. Containment cần xử lý cả secret gốc lẫn token đã phát hành:

- Disable secret/client credential bị lộ tại identity provider.
- Revoke active sessions/tokens nếu provider hỗ trợ và policy yêu cầu.
- Rotate sang secret mới hoặc chuyển sang workload identity/federation.
- Cập nhật workload, scheduled job, autoscaler và disaster recovery deployment.
- Kiểm tra client có quyền impersonate hoặc cấp credential khác không.
- Xác minh instance cũ, replica và runner không còn dùng secret cũ.

Nếu service account dùng chung cho nhiều service, inventory từng consumer trước khi chuyển để tránh credential mới tiếp tục bị phân phối rộng như cũ.

### 5.8. mTLS certificate và private key

Certificate compromise có thể cho phép client authentication hoặc server impersonation tùy vị trí certificate. Cần phân biệt certificate file bị lộ với private key bị lộ; nếu private key có thể bị copy, coi certificate identity đã compromise.

- Xác định certificate serial, subject/SAN, issuer, EKU, trust store và workload đang dùng.
- Revoke certificate qua CA/OCSP/CRL hoặc trust registry theo kiến trúc.
- Phát hành certificate mới với key pair mới; không tái sử dụng private key đã lộ.
- Cập nhật trust bundle và xác minh verifier thực sự kiểm tra revocation/expiry theo policy.
- Kiểm tra connection pool/long-lived TLS sessions; đóng hoặc drain session có thể tiếp tục được tin.
- Nếu CA/intermediate key bị lộ, xử lý theo phạm vi PKI lớn hơn và phối hợp CA owner.

OCSP/CRL caching và client behavior có thể khiến revocation không có hiệu lực tức thì. Xác minh trên từng verifier/region và ghi propagation delay.

### 5.9. Webhook signing secret

Webhook secret bị lộ có thể cho attacker tạo payload giả có chữ ký hợp lệ hoặc xác minh payload nhận vào. Xác định chiều sử dụng secret:

- Secret dùng để ký outbound webhook: rotate ở sender và cập nhật receiver.
- Secret dùng để verify inbound webhook: rotate ở provider/sender và receiver.
- Secret dùng chung nhiều endpoint/partner: xác định từng consumer và tránh đổi một phía làm mất webhook hợp lệ.

Nếu hệ thống hỗ trợ hai secret trong thời gian chuyển tiếp, giới hạn overlap ngắn, ghi rõ key ID/version và loại secret cũ sau khi xác minh. Không chấp nhận payload chỉ vì có header signature; vẫn phải kiểm tra timestamp, replay window, event ID và endpoint binding.

## 6. Kiểm soát cache và propagation sau revoke

### 6.1. Revoke ở issuer chưa chắc đã revoke ở resource server

Một credential có thể được cache ở CDN, API gateway, sidecar, application memory hoặc token introspection layer. Xác định tất cả nơi ra quyết định xác thực và nguồn dữ liệu chúng sử dụng.

Ghi:

- Cache key/credential ID hoặc `kid` bị ảnh hưởng.
- TTL và invalidation mechanism.
- Region/replica/cluster đã nhận invalidation.
- Thời điểm cache purge/refresh.
- Kết quả kiểm thử credential cũ sau propagation.

Không giả định config deploy đã hoàn tất chỉ vì control plane báo success. Kiểm tra data plane bằng request test an toàn qua từng route/region.

### 6.2. JWKS cache và key rotation

Resource server thường cache JWKS. Khi emergency key revoke, cần biết verifier refresh JWKS theo TTL, `Cache-Control`, forced refresh hay deploy. Một số verifier tiếp tục chấp nhận public key cũ trong cache cho đến khi hết TTL.

Nếu cần containment tức thời, dùng deny `kid` ở verifier/policy layer hoặc một emergency denylist đã được phân phối. Kiểm thử rằng token có chữ ký từ key cũ bị từ chối ở mọi region, không chỉ kiểm tra JWKS endpoint đã bỏ key.

### 6.3. Introspection và session cache

Nếu resource server cache `active=true`, revoke có thể chưa phản ánh. Có thể giảm TTL, purge cache hoặc disable client/resource route tạm thời. Đánh giá trade-off availability và identity provider load; tránh xóa toàn bộ cache gây authentication storm mà không có capacity plan.

### 6.4. Long-lived connection và background work

Request đã được authorize trước thời điểm revoke có thể tiếp tục chạy. WebSocket, gRPC stream, database session, queue consumer và background job có thể giữ context cũ. Xác định policy cho in-flight operation: drain, cancel, re-authorize tại bước nhạy cảm hoặc cho hoàn tất nếu an toàn.

Credential revoke không tự động dừng mọi process đã dùng credential để khởi tạo một kết nối hoặc job. Kiểm tra connection pool, worker lease, scheduled job và downstream token exchange.

## 7. Đánh giá blast radius và tìm dấu hiệu persistence

### 7.1. Xác định các lần sử dụng credential

Truy vấn theo credential ID, client ID, subject, key ID, API key ID hoặc certificate serial trong:

- Identity provider authentication/token issuance logs.
- API gateway/WAF access logs.
- Application authorization/audit events.
- Service mesh/egress/proxy logs.
- Database/object storage access logs.
- Cloud control plane and secret manager audit logs.
- CI/CD runner, deployment và repository audit.
- Webhook delivery, queue producer/consumer logs.

Nếu hệ thống không log raw token (đúng policy), dùng token ID, `jti`, key ID, client ID hoặc fingerprint do issuer tạo. Không thêm raw secret vào truy vấn log.

### 7.2. Phạm vi thời gian

Tìm hoạt động từ trước exposure window đến sau revoke/propagation. Với credential không có `iat` hoặc last-used metadata, dựa vào audit retention và các dấu hiệu thay đổi nguồn sử dụng. Ghi rõ khoảng thời gian chưa có log hoặc log đã hết retention.

### 7.3. Hoạt động cần ưu tiên kiểm tra

- Token issuance, refresh, introspection và revoke events.
- Tạo/xóa API key, client secret, user, role hoặc service account.
- Thay đổi OAuth redirect URI, allowed scope, audience hoặc trust policy.
- Đọc/export object, file, report hoặc database record bất thường.
- Thay đổi payment, billing, payout, beneficiary hoặc webhook destination.
- Thêm SSH/deploy key, CI variable, runner hoặc repository integration.
- Tạo scheduled task, queue consumer, access policy hoặc cloud role mới.
- Tắt logging, alert, WAF rule hoặc audit trail.

### 7.4. Kiểm tra persistence

Attacker có thể tạo credential mới trước khi key cũ bị revoke. Sau containment, kiểm tra:

- API key/client secret mới hoặc credential alias lạ.
- OAuth app/consent grant/service principal mới.
- Role binding, group membership, tenant admin hoặc policy thay đổi.
- Webhook URL, callback endpoint hoặc trusted origin bị sửa.
- Deployment image, startup script, CI workflow hoặc secret mount bị thay đổi.
- New token family/session/device registration.
- KMS/HSM policy, signing key alias hoặc certificate enrollment bất thường.

Đừng dừng điều tra ở việc credential cũ không còn hoạt động. Xác minh attacker không còn con đường truy cập độc lập.

### 7.5. Xác định dữ liệu và hành động bị ảnh hưởng

Map request tới resource/action/tenant và data classification. Phân biệt:

- Đã xác nhận truy cập/đọc.
- Đã xác nhận thay đổi hoặc side effect.
- Có request nhưng không biết kết quả do thiếu telemetry.
- Không thấy request trong nguồn log hiện có.

Không kết luận “không có exfiltration” chỉ vì không thấy download event nếu response body, database query hoặc downstream export không được ghi. Nêu rõ visibility gap.

## 8. Bảo toàn evidence mà không phát tán secret

### 8.1. Không copy secret vào incident ticket

Ghi credential ID, key alias, issuer, scope, expiry và source location. Nếu cần xác định một secret cụ thể, dùng secret manager metadata hoặc HMAC fingerprint trong tooling nội bộ. Không paste raw token/private key vào Slack, email, issue tracker, terminal output hoặc chat với đội ứng phó.

Nếu secret đã nằm trong log, hạn chế quyền truy cập log artifact, giữ bản forensic theo policy và tạo bản redacted để chia sẻ. Xóa khỏi nguồn hiển thị rộng sau khi đã ghi nhận vị trí, thời điểm và quyền truy cập; việc xóa không thay thế revoke.

### 8.2. Bảo toàn log và timeline

Ghi lại:

- Detection time và người phát hiện.
- Exposure source, URL/path/commit/job ID hoặc artifact ID.
- Credential alias/ID và owner.
- Revoke/disable request time, operator và approval.
- Thời điểm propagation hoàn tất ở issuer, gateway và verifier.
- Request ID/trace ID/audit event IDs liên quan.
- Snapshot/hash của log/evidence quan trọng.
- Các thay đổi config, deployment hoặc cache purge.

Ưu tiên export log bằng cơ chế read-only, ghi nguồn và timezone. Không thay đổi log gốc để che dấu exposure. Nếu cần redact, giữ bản gốc trong restricted evidence store theo retention policy và ghi lại transform.

### 8.3. Phân quyền evidence

Chỉ người tham gia incident và người có nhu cầu điều tra được truy cập raw evidence. Tách quyền xem evidence khỏi quyền rotate/revoke credential khi có thể. Dùng storage mã hóa, access audit và retention phù hợp; xóa bản tạm trong runner/workstation sau khi evidence được lưu an toàn.

## 9. Recovery và cấp credential mới

### 9.1. Cấp mới theo least privilege

Credential mới nên:

- Có owner rõ và inventory record.
- Chỉ có scope/audience cần thiết.
- Có expiry/rotation policy.
- Được giới hạn theo environment, resource, network hoặc workload identity khi khả thi.
- Được lưu trong secret manager/KMS/HSM hoặc identity provider phù hợp.
- Có audit event cho issuance, use, rotation và revoke.
- Không được tái sử dụng private key/secret value cũ.

Đừng tạo credential mới với quyền rộng hơn chỉ để khôi phục service nhanh. Nếu cần temporary elevation, đặt expiry ngắn, approval và alert riêng.

### 9.2. Chuyển consumer có kiểm soát

Inventory tất cả consumer trước khi rotate. Triển khai credential mới theo thứ tự: secret store, workload config, canary instance, remaining instances, scheduled jobs và disaster recovery environment. Xác minh consumer dùng credential mới qua key ID/identity metadata, không in secret value.

Nếu provider hỗ trợ overlap, ghi start/end time và owner của overlap. Khi hết overlap, revoke credential cũ và test từ một consumer test để chứng minh key cũ bị từ chối.

### 9.3. Theo dõi authentication failure

Sau rotation, theo dõi:

- `401/403` tăng ở service/route liên quan.
- Secret version mismatch hoặc workload không mount được secret.
- Token refresh failure, `invalid_client`, `invalid_grant` hoặc certificate validation failure.
- Consumer còn dùng credential cũ.
- Retry storm, queue backlog hoặc latency do identity provider bị quá tải.

Không rollback bằng cách bật lại credential đã compromise chỉ để hết lỗi. Sửa consumer hoặc cấp credential mới có scope phù hợp.

### 9.4. Re-enable service

Chỉ đưa service/route trở lại bình thường khi:

- Credential cũ đã bị revoke/invalidate ở authoritative issuer.
- Cache/region/verifier liên quan đã cập nhật hoặc có compensating deny.
- Credential mới đã triển khai và test qua positive control.
- Audit/logging đang hoạt động.
- Không còn persistence chưa xử lý có thể dùng cùng trust path.
- Owner chấp nhận residual risk và incident commander ghi quyết định.

## 10. Kịch bản cụ thể theo nguồn lộ

### 10.1. Secret lộ trong Git repository

1. Revoke/rotate credential ngay; không đợi rewrite Git history.
2. Xác định repository visibility, fork, clone, mirror, package và CI integration có thể truy cập.
3. Kiểm tra commit, pull request, code review, secret scanning alert và repository audit.
4. Xóa secret khỏi working tree và history theo quy trình repository sau khi credential đã vô hiệu hóa.
5. Kiểm tra artifact/build cache/source map chứa bản cũ.
6. Tìm usage theo credential ID từ thời điểm commit public/internal exposure.
7. Thêm secret scanning/pre-commit/CI guard và kiểm thử lại.

Rewrite history chỉ giảm exposure tiếp tục; không thể thu hồi bản clone hoặc cache đã được người khác lấy. Revoke mới là hành động làm credential mất khả năng sử dụng.

### 10.2. Secret lộ trong CI/CD log hoặc artifact

- Disable job/runner nếu có dấu hiệu runner compromise.
- Revoke credential xuất hiện trong log/artifact.
- Xác định log retention, ai có quyền xem, artifact download access và forked pipeline.
- Kiểm tra command echo, shell tracing, debug mode và environment dump.
- Xóa/rotate artifact có secret theo retention và evidence policy.
- Chuyển secret sang protected variable/secret store hoặc workload federation.
- Bổ sung log masking nhưng không dựa hoàn toàn vào masking regex.

CI masking có thể không bắt được encoding, substring, multiline hoặc biến thể secret. Không coi dấu `***` trong log là bằng chứng raw value chưa từng được phát ra ở nơi khác.

### 10.3. Secret lộ trong browser/mobile client

Nếu key được nhúng trong JavaScript bundle, mobile binary, source map hoặc config public, coi đó là public credential. Không có cách giữ bí mật một API key trong client mà người dùng kiểm soát.

- Revoke key và kiểm tra usage.
- Xác định key có được dùng để gọi privileged API hay chỉ là public identifier.
- Chuyển thao tác privileged sang backend; cấp user/session token có scope, audience và expiry phù hợp.
- Dùng app attestation/rate limit như tín hiệu bổ sung, không coi chúng là secret storage.
- Nếu key chỉ định danh project/public client, giới hạn API, quota, origin/app restrictions và abuse monitoring.

Không phát hành key mới có cùng privilege vào bundle khác rồi coi đã xử lý.

### 10.4. Secret lộ trong log/trace/support bundle

- Xác định mọi sink: application log, gateway log, tracing backend, analytics, APM, support archive, backup và export.
- Revoke credential trước khi dọn log.
- Hạn chế quyền đọc, export và retention của artifact chứa secret.
- Tạo bản redacted cho điều tra rộng; giữ raw evidence riêng theo policy.
- Sửa instrumentation, exception mapping, HTTP wire logging và redaction filter.
- Kiểm tra log pipeline không decode/rehydrate secret sau redaction.

Redaction cần được test bằng sentinel secret trong môi trường test. Không đưa secret thật vào test chỉ để kiểm tra masking.

### 10.5. Laptop/workstation hoặc runner bị mất

Xác định credential nào được lưu/cached trên thiết bị, session/SSH/VPN/device certificate nào có thể dùng và thời điểm thiết bị mất quyền kiểm soát. Revoke device session, PAT, SSH/deploy key, cloud session và runner registration theo inventory. Cô lập thiết bị/runner theo endpoint security policy và điều tra local secret store, shell history, build cache và mounted workspace.

Không chỉ đổi password người dùng nếu thiết bị có workload credential hoặc long-lived token riêng.

## 11. Communication và phối hợp

### 11.1. Thông tin cần có trong incident update

Một update ngắn nên nêu:

- Incident ID, severity tạm thời và service/credential alias bị ảnh hưởng.
- Điều đã biết và điều chưa xác định.
- Containment đã thực hiện, thời điểm và kết quả xác minh.
- Service/consumer có thể bị gián đoạn.
- Owner đang xử lý rotation/recovery.
- Mốc cập nhật tiếp theo và kênh liên lạc chính thức.

Không đưa raw token, private key, secret URL hoặc dữ liệu khách hàng vào update. Không gửi thông tin chi tiết về cách truy cập trái phép tới audience không cần biết.

### 11.2. Phân công trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander | Ưu tiên, quyết định containment, điều phối và timeline |
| Credential owner | Xác định owner/consumer, rotate và xác minh use |
| IAM/API platform | Revoke token/key, update issuer/JWKS/introspection và policy |
| Service owner | Cập nhật workload, test business function và recovery |
| SOC/security | Triage, threat hunting, evidence và impact assessment |
| SRE/operations | Traffic, cache, region, availability và rollback plan |
| Privacy/legal/compliance | Đánh giá nghĩa vụ thông báo theo policy/pháp luật khi có dữ liệu liên quan |

Một người có thể giữ nhiều vai trò ở team nhỏ, nhưng quyết định và người thực hiện vẫn cần được ghi lại.

### 11.3. Khi nào cần thông báo bên ngoài

Việc thông báo khách hàng, partner, regulator hoặc provider phụ thuộc loại dữ liệu, hợp đồng, khu vực pháp lý và mức độ ảnh hưởng đã xác minh. Chuyển đánh giá cho privacy/legal/compliance theo quy trình tổ chức. Không tự suy luận nghĩa vụ thông báo chỉ từ việc token xuất hiện trong repository.

## 12. Monitoring sau containment

### 12.1. Tạo detection theo credential ID

Theo dõi credential cũ sau revoke:

- Attempt dùng key/token đã revoke.
- Token `jti` hoặc `kid` bị deny.
- API key ID cũ tiếp tục xuất hiện trong gateway.
- Refresh token reuse hoặc client secret authentication failure.
- Certificate serial đã revoked vẫn xuất hiện trong handshake.
- Webhook signature từ key version cũ.

Các attempt này có thể là consumer chưa cập nhật hoặc attacker tiếp tục thử. Phân loại theo source/consumer và không tự động kết luận tất cả là malicious.

### 12.2. Theo dõi credential mới

Alert khi credential mới được tạo ngoài workflow, scope tăng bất thường, owner thay đổi, secret được đọc từ nơi lạ hoặc key rotation bị rollback. Giám sát secret manager/KMS access và identity provider administrative events.

### 12.3. Chất lượng telemetry

Đảm bảo audit event có credential ID, actor/client, audience, scope, result, timestamp UTC, request ID/trace ID và source metadata đã xác minh. Không log raw credential. Nếu log bị sampling hoặc retention gap, ghi rõ để tránh kết luận sai.

### 12.4. Tiêu chí đóng containment

Containment chỉ được coi là đạt khi:

- Credential cũ bị từ chối tại issuer/verifier có thẩm quyền.
- Cache/region/long-lived connection đã được xử lý hoặc có risk acceptance rõ.
- Consumer hợp lệ chuyển sang credential mới hoặc service bị tắt an toàn.
- Không còn token/key descendants chưa xử lý.
- Audit search không thấy usage thành công sau mốc revoke; mọi ngoại lệ được giải thích.
- Persistence và unauthorized changes đã được kiểm tra theo visibility hiện có.
- Evidence và residual risk được ghi lại.

## 13. Post-incident review và phòng ngừa

### 13.1. Root cause

Điều tra vì sao credential xuất hiện ở nơi không được phép:

- Secret được lưu trong source code/config hoặc client bundle.
- CI job echo environment hoặc bật debug tracing.
- Logging middleware ghi Authorization/header/body.
- Quyền repository, artifact hoặc log quá rộng.
- Credential dùng chung giữa nhiều service/tenant.
- Token/key sống quá lâu hoặc scope quá rộng.
- Không có owner/inventory/rotation schedule.
- Secret manager access hoặc workload identity thiếu isolation.
- Revocation không propagate tới verifier/cache.

Phân biệt nguyên nhân trực tiếp (ví dụ debug log in token) với yếu tố góp phần (ví dụ token có quyền admin và không có expiry ngắn).

### 13.2. Hành động khắc phục

- Chuyển static secret sang workload identity/federation khi khả thi.
- Giảm scope, audience và lifetime.
- Áp dụng API key per consumer, key ID và revoke endpoint rõ ràng.
- Dùng refresh token rotation/reuse detection.
- Dùng signing key trong HSM/KMS và tách quyền ký khỏi quyền đọc private key.
- Thiết lập secret scanning trong IDE, pre-commit và CI.
- Redact Authorization/Cookie/secret fields ở log/trace và kiểm thử bằng sentinel.
- Inventory credential owner, consumer, expiry, last-used và rotation procedure.
- Kiểm tra cache/revocation propagation bằng integration test định kỳ.
- Tạo runbook và diễn tập revoke/rotate theo loại credential.

### 13.3. Game day và tabletop exercise

Diễn tập bằng credential giả trong staging:

1. Đưa sentinel API key vào test repository private.
2. Tạo alert giả lập và mở incident.
3. Revoke key, rotate và cập nhật consumer test.
4. Xác minh key cũ bị từ chối qua gateway và application.
5. Tìm usage trong audit logs và hoàn tất evidence package.
6. Đo thời gian detect, revoke, propagation và recovery.

Không dùng credential production thật trong diễn tập. Ghi rõ điểm nghẽn: thiếu owner, không biết consumer, không có revoke API, cache TTL dài hoặc test chưa phủ multi-region.

## 14. Template incident record

```yaml
incident_id: INC-API-2026-0042
title: Suspected API credential exposure
severity: high
status: contained
detected_at: "2026-11-18T13:45:22Z"
credential:
  type: api_key
  id: key-prod-files-17
  owner: files-platform
  issuer: api-key-registry
  audience: files-api
  scopes:
    - file:read
  expires_at: "2027-01-01T00:00:00Z"
exposure:
  source: ci-artifact
  first_possible_exposure: "2026-11-18T12:00:00Z"
  confirmed_misuse: unknown
containment:
  revoke_requested_at: "2026-11-18T13:48:00Z"
  revoke_verified_at: "2026-11-18T13:49:12Z"
  replacement_credential_id: key-prod-files-18
  old_credential_rejected: true
impact:
  successful_unauthorized_requests: under-investigation
  affected_resources: synthetic-and-production-scope-review-pending
evidence:
  - ci-job-id: build-4821
  - audit-query-id: audit-search-993
  - request-id: req-opaque-example
residual_risk:
  - consumer inventory is still being confirmed
```

Các giá trị trên là ví dụ. Incident record thực tế phải dùng timestamp, ID và status quan sát được; không đưa raw secret vào YAML/ticket. Nếu chưa biết misuse, ghi `unknown` thay vì `false`.

## 15. Checklist containment khi token/API key bị lộ

- [ ] Mở incident, chỉ định commander và credential owner.
- [ ] Xác định loại credential, ID/alias, issuer, subject/client và owner.
- [ ] Xác định audience, scope, privilege, expiry và consumer inventory.
- [ ] Ghi exposure source/window và mức độ xác nhận.
- [ ] Bảo toàn metadata/audit evidence mà không copy raw secret.
- [ ] Revoke/disable credential hoặc áp compensating deny phù hợp.
- [ ] Xác minh credential cũ bị từ chối tại verifier thực tế.
- [ ] Xử lý introspection/JWKS/session cache, region và long-lived connection.
- [ ] Revoke refresh token/family hoặc descendants khi liên quan.
- [ ] Nếu signing key compromise, thay key pair và invalidate token ký bằng key cũ.
- [ ] Nếu API key/service secret, rotate theo consumer và revoke key cũ.
- [ ] Nếu certificate compromise, revoke serial và thay private key/certificate.
- [ ] Nếu webhook secret compromise, rotate hai phía và giới hạn overlap.
- [ ] Tìm token/key issuance, usage, data access và administrative changes trong exposure window.
- [ ] Kiểm tra persistence: key mới, role, OAuth app, webhook, runner, policy.
- [ ] Đánh giá dữ liệu/tenant/side effect bị ảnh hưởng và visibility gap.
- [ ] Cấp credential mới least privilege qua secret manager/identity platform.
- [ ] Xác minh consumer hợp lệ hoạt động và key cũ không còn dùng được.
- [ ] Theo dõi auth failure, retry storm, revoked credential attempts và key creation.
- [ ] Ghi timeline, operator, approval, evidence references và residual risk.
- [ ] Hoàn thành root cause, regression test, rotation exercise và action owner.

## Kết luận

Containment khi token hoặc API key bị lộ cần xác định đúng credential, chặn khả năng sử dụng, xử lý cache/verifier và chuyển consumer sang credential mới có scope tối thiểu. Access token, refresh token, JWT signing key, API key, service secret, certificate và webhook secret có cơ chế revoke khác nhau; không thể dùng một thao tác rotate chung cho tất cả. Sau khi credential cũ bị vô hiệu hóa, tiếp tục điều tra usage, dữ liệu bị truy cập và persistence. Incident chỉ được đóng khi khả năng sử dụng credential cũ đã được xác minh là bị chặn, service được phục hồi an toàn và residual risk được ghi rõ.
