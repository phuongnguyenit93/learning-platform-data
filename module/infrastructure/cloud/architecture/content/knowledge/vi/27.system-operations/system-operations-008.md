# Quản lý chứng chỉ, tên miền và các phụ thuộc có thời hạn

## 1. Vì sao phụ thuộc có thời hạn là rủi ro vận hành?

Ứng dụng cloud thường phụ thuộc vào nhiều tài nguyên có ngày hết hạn hoặc cần được gia hạn định kỳ: TLS certificate, domain registration, DNS zone, API key, client secret, signing key, token, license, support contract, code-signing certificate và credential của đối tác. Một phụ thuộc có thể hoạt động bình thường nhiều tháng rồi gây outage đột ngột khi hết hạn, bị thu hồi hoặc thay đổi mà hệ thống chưa cập nhật.

Ví dụ, certificate hết hạn có thể khiến client từ chối kết nối HTTPS; domain registration hết hạn có thể làm tên miền bị suspended hoặc mất quyền kiểm soát; API key hết hạn có thể làm worker không gọi được đối tác; signing key bị xoay nhưng consumer chưa nhận public key mới có thể từ chối token hợp lệ. Các lỗi này thường xuất hiện đồng thời ở nhiều service vì chúng dùng chung một tài nguyên.

**Lifecycle management** là quản lý toàn bộ vòng đời của phụ thuộc: tạo, đăng ký, phân phối, sử dụng, giám sát, gia hạn/xoay vòng, thu hồi và loại bỏ. Công việc này cần có inventory, owner, ngày hết hạn, dependency mapping, automation, kiểm tra sau thay đổi và bằng chứng audit.

Trong module **CLOUD_ARCHITECTURE**, quản lý phụ thuộc có thời hạn là một năng lực vận hành bảo vệ tính sẵn sàng, bảo mật và khả năng phục hồi. Mục tiêu là phát hiện trước khi hết hạn, gia hạn có kiểm soát và chứng minh mọi consumer đã chuyển sang phiên bản hợp lệ.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Lập inventory chứng chỉ, domain, secret, token, key và license có thời hạn.
2. Phân biệt expiration, rotation, renewal, revocation và replacement.
3. Thiết kế PKI/TLS certificate lifecycle và tự động gia hạn.
4. Quản lý domain registration, DNS zone, delegation và DNSSEC.
5. Xoay API key, client secret và signing key mà không gây gián đoạn.
6. Xác định owner, consumer, dependency graph và quy trình approval.
7. Đặt alert dựa trên thời gian còn lại và mức độ quan trọng của phụ thuộc.
8. Diễn tập sự cố hết hạn, thu hồi nhầm hoặc xoay vòng thất bại.

## 2. Phân loại phụ thuộc có thời hạn

Không phải mọi thứ có ngày hết hạn đều được gia hạn theo cùng cách. Cần phân loại theo cách xác thực, phạm vi ảnh hưởng, cơ chế thay thế và khả năng tự động hóa.

| Loại | Ví dụ | Hành động trước khi hết hạn |
|---|---|---|
| **TLS/server certificate** | Certificate cho website, API gateway, ingress, service endpoint | Renew, deploy certificate mới, xác minh chain/SAN và reload |
| **Client certificate/mTLS** | Certificate giữa service hoặc partner | Cấp mới, phân phối trust chain, chuyển client/server theo overlap |
| **Signing certificate/key** | JWT/SAML signing, code signing, artifact signing | Publish public key mới, overlap verification, chuyển signer, retire key cũ |
| **Domain registration** | example.com hoặc tên miền sản phẩm | Renew registrar, xác minh payment/contact/lock |
| **DNS delegation/zone** | NS, DS, CNAME, TXT, MX, validation record | Giữ zone/record đúng, cập nhật delegation và DNSSEC |
| **API key/client secret** | Payment provider, email service, SaaS integration | Tạo credential mới, phân phối cho consumer, chuyển và revoke credential cũ |
| **Access token/refresh token** | OAuth token, session token | Renew/refresh theo protocol, thu hồi khi cần |
| **License/subscription** | Database engine, security agent, monitoring platform | Renew hợp đồng/entitlement và kiểm tra enforcement |
| **SSH key/host key** | Automation, bastion, host identity | Rotate public/private key hoặc trust entry có overlap |
| **Support/contract entitlement** | Cloud support plan, partner support | Gia hạn và xác minh account/resource coverage |
| **Trust anchor/root/intermediate CA** | CA hierarchy và trust store | Quản lý key ceremony, cross-sign/rollover, trust-store rollout |

### 2.1. Những mốc thời gian khác nhau

- **Not Before / Not After:** thời điểm certificate bắt đầu và kết thúc hiệu lực.
- **Registration expiry:** thời điểm domain registration cần được gia hạn.
- **Credential expiration:** thời điểm secret/token không còn được chấp nhận.
- **Rotation deadline:** mốc nội bộ yêu cầu thay credential dù chưa hết hạn.
- **Revocation:** vô hiệu hóa trước ngày hết hạn vì compromise hoặc thay đổi trust.
- **Contract renewal date:** ngày gia hạn hợp đồng hoặc license.

Không thể chỉ dựa vào một trường expires_at cho mọi loại phụ thuộc. Cần ghi rõ timezone, nguồn thời gian, semantics của ngày hết hạn và hành động phải thực hiện.

## 3. Inventory và ownership

Không thể quản lý những gì không được phát hiện và ghi nhận. Inventory cần bao gồm cả tài nguyên do cloud platform quản lý, SaaS, registrar, đối tác và credential nằm trong CI/CD.

### 3.1. Trường thông tin tối thiểu

| Trường | Ý nghĩa |
|---|---|
| Asset ID | Định danh duy nhất trong inventory |
| Type | Certificate, domain, secret, key, license... |
| Identifier | Domain/FQDN, ARN/resource ID, certificate fingerprint hoặc logical name |
| Environment | Production, staging, development |
| Owner | Team/người chịu trách nhiệm kỹ thuật |
| Business owner | Người xác nhận tác động nghiệp vụ |
| Issuer/provider | CA, registrar, SaaS hoặc bên phát hành |
| Valid from / expires at | Thời hạn hiệu lực |
| Renewal/rotation method | ACME, API, manual approval, provider workflow |
| Consumers | Service, workload, partner, client sử dụng |
| Dependency criticality | Mức độ ảnh hưởng nếu hết hạn |
| Secret reference | Tham chiếu tới secret manager, không lưu plaintext |
| Runbook | Quy trình gia hạn/xoay vòng/khôi phục |
| Last verified | Lần gần nhất xác minh trạng thái thực tế |
| Evidence | Ticket, audit event, certificate fingerprint hoặc provider receipt |

### 3.2. Owner phải cụ thể

Tên team chung chung như Platform chưa đủ nếu không có người trực hoặc quy trình escalation. Mỗi asset cần owner chính, owner thay thế và business owner. Domain của thương hiệu có thể do marketing/legal sở hữu về mặt đăng ký, trong khi DNS và certificate do platform vận hành.

Không đưa private key, API secret hay refresh token vào inventory. Chỉ lưu secret reference và metadata không nhạy cảm; quyền truy cập giá trị bí mật nằm trong secret manager.

### 3.3. Phát hiện inventory tự động

Có thể kết hợp cloud resource inventory và certificate manager; certificate transparency/hostname discovery trong phạm vi domain được phép quản lý; DNS zone/registrar API và domain portfolio report; secret manager metadata và rotation configuration; CI/CD variables inventory theo quyền truy cập; SaaS admin API, license portal và procurement records; TLS scanner nội bộ kiểm tra endpoint thực tế.

Discovery không thay thế xác nhận owner. Một endpoint tìm thấy có thể là legacy, partner-managed hoặc ngoài phạm vi; cần workflow xác minh và gán owner.

## 4. Dependency graph: biết thứ gì sẽ bị ảnh hưởng

Một certificate hoặc secret thường được nhiều consumer dùng. Chỉ biết certificate sắp hết hạn chưa đủ; phải biết service nào sẽ thất bại nếu nó bị thay hoặc thu hồi.

~~~mermaid
flowchart TD
    CA["Certificate authority"] --> Cert["API certificate"]
    Cert --> Gateway["API gateway"]
    Gateway --> Booking["Booking service"]
    Gateway --> Partner["Partner integration"]
    Cert --> Monitor["Synthetic TLS monitor"]
    Secret["Payment client secret"] --> Booking
    Secret --> Worker["Payment reconciliation worker"]
    Domain["Public domain"] --> DNS["DNS zone / delegation"]
    DNS --> Gateway
    DNS --> Web["Web application"]
~~~

Mỗi edge nên ghi loại dependency:

- **Runtime:** consumer cần credential để xử lý request.
- **Trust:** consumer cần public key/CA để xác minh peer hoặc token.
- **Discovery:** consumer cần DNS, metadata endpoint hoặc JWKS.
- **Control plane:** pipeline cần credential để deploy certificate.
- **Business/contract:** domain hoặc license gắn với thương hiệu/hợp đồng.

Dependency graph cần hỗ trợ truy vấn hai chiều: asset nào sắp hết hạn và consumer nào bị ảnh hưởng; service nào có thể bị outage và các phụ thuộc có thể gây ra lỗi đó.

## 5. PKI và vòng đời TLS certificate

Certificate TLS liên kết public key với danh tính được CA xác thực theo profile. Trong TLS server authentication, client xác minh certificate chain, thời hạn, hostname/SAN, purpose và các điều kiện trust khác.

### 5.1. Chuỗi certificate

~~~mermaid
flowchart TD
    Root["Trusted root CA"] --> Intermediate["Intermediate CA"]
    Intermediate --> Leaf["Leaf certificate: api.example.com"]
    Leaf --> Endpoint["Load balancer / ingress / service"]
    Client["Client trust store"] -. "validates chain + hostname + time" .-> Endpoint
~~~

Private key của leaf certificate phải được bảo vệ. Public certificate có thể phân phối rộng hơn, nhưng private key không được đưa vào source repository, image công khai, log hoặc ticket.

### 5.2. SAN và hostname

Hostname mà client truy cập phải khớp Subject Alternative Name (SAN) phù hợp trong certificate. Common Name không nên được coi là cách duy nhất để xác minh hostname trong triển khai hiện đại. Wildcard certificate có phạm vi nhất định, ví dụ wildcard cho một label; cần kiểm tra chính sách CA và client behavior trước khi dùng.

Không phát hành một wildcard private key duy nhất cho mọi môi trường nếu blast radius quá lớn. Có thể dùng certificate riêng theo environment/zone/service và tự động phân phối qua certificate manager.

### 5.3. Quy trình certificate lifecycle

1. Xác định hostname, SAN, environment, issuer và consumer.
2. Tạo key pair ở vị trí bảo vệ; ưu tiên key không xuất khỏi HSM/managed key store khi phù hợp.
3. Tạo CSR và gửi CA theo quy trình validation.
4. Nhận certificate, kiểm tra chain, SAN, validity, EKU và fingerprint.
5. Lưu certificate/key trong kho phù hợp; cấp quyền truy cập cho runtime identity.
6. Deploy lên load balancer, ingress hoặc service.
7. Reload/restart theo cách an toàn nếu nền tảng cần.
8. Xác minh TLS handshake từ góc nhìn client thực tế.
9. Theo dõi expiration và tự động renew trước ngưỡng.
10. Thu hồi certificate cũ khi không còn consumer hoặc có sự cố.

## 6. Tự động gia hạn certificate với ACME

ACME là giao thức tự động hóa việc xác thực domain và cấp/phát hành certificate bởi CA hỗ trợ ACME. Client ACME có thể chứng minh quyền kiểm soát domain bằng challenge như HTTP-01, DNS-01 hoặc TLS-ALPN-01 tùy CA và trường hợp sử dụng.

### 6.1. Các challenge thường gặp

| Challenge | Cách xác minh | Phù hợp với |
|---|---|---|
| HTTP-01 | CA yêu cầu token qua HTTP tại đường dẫn well-known | Host public truy cập được qua port phù hợp |
| DNS-01 | Tạo TXT record dưới tên challenge | Wildcard, private service có DNS automation hoặc môi trường không expose HTTP |
| TLS-ALPN-01 | Challenge qua TLS/ALPN trên endpoint | Một số kiến trúc edge/proxy hỗ trợ |

DNS-01 cần quyền ghi DNS đủ hẹp. Không cấp API token quản trị toàn bộ registrar/DNS account cho mọi ACME client nếu provider hỗ trợ token scoped theo zone/record.

### 6.2. Renew không đồng nghĩa deploy thành công

Một ACME client có thể lấy certificate mới nhưng load balancer vẫn đang dùng certificate cũ. Pipeline cần kiểm tra certificate mới đã lưu và đúng hostname chưa; secret/certificate reference trên runtime đã cập nhật chưa; load balancer/ingress đã reload chưa; endpoint bên ngoài có trình certificate mới không; chain có đủ intermediate không; consumer cũ còn pin fingerprint hoặc trust một CA đã thay đổi không.

Phải alert riêng cho renewal failure và deployment/serving failure. Kiểm tra trực tiếp endpoint là bằng chứng quan trọng hơn chỉ xem job renew đã exit 0.

### 6.3. Overlap và certificate rollover

Với mTLS hoặc client certificate, có thể cần giai đoạn trust đồng thời certificate cũ và mới:

1. Phát hành certificate mới.
2. Phân phối public certificate/CA cần tin cậy tới peer.
3. Xác minh peer chấp nhận cả hai.
4. Chuyển client/server sang certificate mới.
5. Quan sát handshake và lỗi xác thực.
6. Thu hồi/gỡ certificate cũ khi tất cả consumer đã chuyển.

Không xóa trust cũ trước khi xác nhận toàn bộ peer đã cập nhật. Ngược lại, không giữ credential cũ vô hạn sau khi rollover hoàn tất.

## 7. Domain registration, DNS và delegation

Domain registration là quyền đăng ký và duy trì tên miền qua registrar/registry. DNS zone chứa record ánh xạ tên miền tới địa chỉ hoặc dịch vụ. Hai lớp có liên hệ nhưng không đồng nhất: gia hạn domain không tự sửa record DNS; DNS hoạt động không chứng minh domain registration còn hiệu lực lâu dài.

### 7.1. Thành phần domain

- **Registrar:** nơi quản lý đăng ký, renew, transfer và account contact.
- **Registry:** tổ chức vận hành TLD và dữ liệu đăng ký ở cấp registry.
- **Registrant:** chủ thể đăng ký domain.
- **Authoritative DNS:** nơi trả lời record có thẩm quyền.
- **Nameserver delegation:** record NS chỉ định authoritative DNS.
- **DNSSEC:** cơ chế ký dữ liệu DNS và xây dựng chuỗi xác thực qua DS/DNSKEY.

### 7.2. Các record phổ biến

| Record | Chức năng | Ví dụ use case |
|---|---|---|
| A | Tên tới IPv4 | api.example.com |
| AAAA | Tên tới IPv6 | Dual-stack endpoint |
| CNAME | Alias tới tên khác | app tới managed endpoint |
| NS | Nameserver delegation | Delegate subdomain |
| SOA | Metadata quản lý zone | Serial/authority parameters |
| MX | Mail exchanger | Email domain |
| TXT | Text/verification/policy | ACME DNS-01, SPF, domain verification |
| CAA | Giới hạn CA được phép phát hành certificate | Chỉ cho CA đã chọn |
| DS/DNSKEY | Thành phần DNSSEC | Chain of trust |

### 7.3. Kiểm soát registrar account

Domain quan trọng cần auto-renew bật và payment method còn hiệu lực; thông tin registrant/contact và recovery channel cập nhật; registrar account dùng MFA/phishing-resistant authentication nếu hỗ trợ; domain/transfer lock phù hợp; role tách biệt giữa xem, sửa DNS, renew và transfer; backup thông tin đăng ký, expiry và emergency access; alert tới nhiều người/nhóm, không phụ thuộc một mailbox cá nhân.

Auto-renew không bảo đảm mọi trường hợp renew thành công: payment có thể thất bại, account bị khóa hoặc registry có điều kiện riêng. Phải kiểm tra trạng thái registration sau khi gia hạn.

## 8. DNSSEC và thay đổi trust chain

DNSSEC cung cấp tính xác thực và toàn vẹn cho dữ liệu DNS qua chữ ký số; nó không mã hóa DNS query. Khi bật hoặc đổi DNSSEC, DS record ở parent zone phải khớp với DNSKEY ở child zone theo quy trình rollover. Sai lệch DS/DNSKEY có thể khiến resolver validating từ chối toàn bộ zone.

### Quy trình thay đổi DNSSEC

1. Inventory registrar, parent zone, authoritative nameserver, DNSKEY và DS hiện tại.
2. Lập kế hoạch key rollover và xác định thời gian overlap theo TTL/cache behavior.
3. Publish DNSKEY mới ở authoritative zone.
4. Cập nhật DS tại registrar/parent theo thứ tự đúng của phương pháp rollover.
5. Xác minh qua nhiều validating resolver và authoritative server.
6. Theo dõi SERVFAIL và DNSSEC validation errors.
7. Chỉ retire key cũ khi chain mới hoạt động ổn định.

Không chỉnh DS record theo cảm tính hoặc cùng lúc xóa key cũ và thay DS nếu chưa hiểu quy trình rollover của DNS provider.

## 9. Secret, API key và client secret

Secret thường được cấp theo một consumer và một quyền cụ thể. Vòng đời của chúng gồm issuance, distribution, use, rotation, revocation và audit.

### 9.1. Mô hình xoay vòng không gián đoạn

~~~mermaid
flowchart TD
    Old["Old credential active"] --> Create["Create new credential"]
    Create --> Distribute["Store and distribute new secret"]
    Distribute --> Dual["Allow old + new during overlap"]
    Dual --> Switch["Move consumers to new credential"]
    Switch --> Verify["Verify successful use of new credential"]
    Verify --> Revoke["Revoke old credential"]
    Revoke --> Audit["Audit and remove stale references"]
~~~

Không phải provider nào cũng cho phép hai key cùng hoạt động. Nếu chỉ hỗ trợ một key, cần maintenance window hoặc cơ chế proxy/credential broker để chuyển đổi an toàn.

### 9.2. Quy trình rotation

1. Xác định tất cả consumer và owner.
2. Tạo credential mới trong provider.
3. Lưu vào secret manager với version mới.
4. Cập nhật consumer theo rollout strategy.
5. Xác minh request thực tế sử dụng credential mới.
6. Theo dõi error rate, authentication failure và usage của key cũ.
7. Revoke key cũ sau overlap đã định.
8. Quét repository/config/log để phát hiện bản sao còn sót.
9. Ghi nhận fingerprint/version, thời điểm và người thực hiện; không lưu giá trị secret.

Nếu provider hỗ trợ key ID hoặc usage log, dùng nó để chứng minh consumer đã chuyển. Không kết luận đã chuyển chỉ vì secret manager có version mới.

### 9.3. Token và refresh token

Access token thường có thời hạn ngắn hơn và được lấy lại theo protocol; refresh token có thể tồn tại lâu hơn và cần bảo vệ nghiêm ngặt. Không tự gia hạn token bằng cách tăng expiration trong ứng dụng. Dùng authorization server, token rotation/reuse detection và revocation theo khả năng protocol/provider.

## 10. Signing key và trust-store rollover

Signing key dùng để ký JWT, SAML response, package, artifact hoặc software release. Thay private key mà không chuẩn bị consumer có thể làm token hoặc artifact mới bị từ chối.

### Chiến lược key rollover

- Tạo key pair mới trong KMS/HSM hoặc key store phù hợp.
- Publish public key mới qua JWKS/metadata/trust store.
- Consumer cập nhật và chấp nhận key mới trong khi vẫn xác minh key cũ.
- Sign dữ liệu mới bằng key mới, kèm key identifier rõ ràng.
- Theo dõi verification failure theo kid/issuer/audience.
- Đợi token/artifact cũ hết vòng đời hoặc theo policy.
- Retire/revoke key cũ và ghi bằng chứng.

Nếu private key compromise, không chờ overlap thông thường: cần emergency revocation/rotation, đánh giá token/artifact đã ký, xác định khả năng reissue và thông báo consumer. Kịch bản compromise khác kịch bản hết hạn bình thường.

## 11. License, subscription và hợp đồng hỗ trợ

Một số dependency không phải credential kỹ thuật nhưng vẫn gây gián đoạn khi hết hạn:

- License database hoặc commercial software.
- Subscription security/monitoring agent.
- Managed service plan hoặc quota entitlement.
- Support contract và escalation entitlement.
- Partner API subscription hoặc quota agreement.

Inventory nên ghi account/tenant, covered product/resource, renewal term, procurement owner, technical owner, payment method, grace period nếu được nhà cung cấp công bố và ảnh hưởng khi hết hạn.

Không giả định grace period tồn tại hoặc hệ thống sẽ tiếp tục hoạt động sau ngày hết hạn. Kiểm tra hợp đồng và điều khoản cụ thể; không lưu thông tin thanh toán nhạy cảm trong file vận hành.

## 12. Lập kế hoạch renewal và rotation theo thời gian còn lại

Không nên chỉ alert vào ngày hết hạn. Cần các mốc đủ sớm cho công việc, approval, phân phối và rollback.

### Ví dụ lịch cho certificate

| Mốc còn lại | Hành động gợi ý |
|---|---|
| 60 ngày | Inventory, xác minh owner/consumer, kiểm tra CA/automation |
| 30 ngày | Renewal thử hoặc staging, kiểm tra chain và endpoint |
| 14 ngày | Escalate nếu chưa renew/deploy; mở incident/task ưu tiên |
| 7 ngày | Xác minh production serving certificate và mọi consumer |
| 72 giờ | Critical alert nếu chưa chuyển; kích hoạt runbook |
| 24 giờ | On-call escalation và business owner notification |
| Hết hạn | Incident; khôi phục certificate hợp lệ và xác minh toàn bộ endpoint |

Các mốc chỉ là ví dụ; certificate lifetime, CA policy, provider và khả năng automation có thể yêu cầu chu kỳ khác.

### Risk-based prioritization

\[
Risk \approx Impact \times Likelihood \times Exposure
\]

Có thể thêm thời gian còn lại, số consumer và khả năng rollback. Một certificate cho public API production dùng bởi hàng triệu client có rủi ro cao hơn credential của test environment dù cùng ngày hết hạn.

## 13. Alerting và dashboard phụ thuộc có thời hạn

Dashboard nên giúp trả lời asset nào sắp hết hạn, owner là ai, consumer nào bị ảnh hưởng, renewal đang ở trạng thái nào và bằng chứng xác minh đã có chưa.

### 13.1. Metric

| Metric | Mục đích |
|---|---|
| dependency_expiry_days | Số ngày còn lại tới expiration |
| certificate_not_after_timestamp | Thời điểm certificate hết hạn |
| certificate_renewal_success_total | Số lần renew thành công |
| certificate_deployment_status | Trạng thái deploy certificate mới |
| tls_handshake_failure_total | Lỗi TLS handshake |
| domain_renewal_status | Trạng thái gia hạn domain |
| secret_rotation_age_days | Tuổi credential theo policy |
| old_credential_usage_total | Lượt dùng key cũ sau cutover |
| dependency_owner_missing | Asset không có owner |
| expiry_inventory_coverage | Tỷ lệ asset có expiry và owner |

Không đưa secret value, private key hoặc full token vào metric/log. Label nên giới hạn theo asset type, environment, provider và criticality; asset ID có thể để trong inventory system để drill-down thay vì tạo cardinality không giới hạn trong metric backend.

### 13.2. Alert routing

- Certificate/domain production: platform on-call và owner.
- Payment/API key: integration owner và business operations.
- Signing key/root CA: security/key custodian và service owner.
- License/support: procurement/contract owner và technical owner.
- Asset không owner: governance queue để phân bổ trách nhiệm.

Alert nên có expires-at, days remaining, owner, criticality, impacted consumers, runbook link và renewal status. Không chỉ gửi email certificate expires soon mà không có hành động cụ thể.

## 14. Automation an toàn

Automation giảm lỗi thủ công nhưng cần guardrail:

- Idempotent job có thể chạy lại nếu scheduler retry.
- Credential renew/rotate chỉ có quyền trên đúng asset/zone.
- Approval cho thay đổi có blast radius lớn.
- Staging/test trước production khi có thể.
- Secret mới lưu qua secret manager API, không in ra log.
- Deploy có version/fingerprint và rollback reference.
- Verification kiểm tra từ bên ngoài và từ consumer.
- Old credential chỉ revoke khi gate thành công.
- Có manual recovery nếu CA, registrar hoặc secret provider outage.

### 14.1. State machine tham khảo

~~~text
DISCOVERED
  -> INVENTORIED
  -> RENEWAL_DUE
  -> RENEWED
  -> DISTRIBUTED
  -> DEPLOYED
  -> VERIFIED
  -> OLD_VERSION_RETIRED

Exception:
  -> BLOCKED_APPROVAL
  -> RENEWAL_FAILED
  -> DEPLOYMENT_FAILED
  -> ROLLBACK_REQUIRED
  -> INCIDENT
~~~

Không chuyển trạng thái VERIFIED chỉ vì certificate mới đã được cấp. Verification phải chứng minh consumer thực sự dùng phiên bản mới và traffic/handshake thành công.

## 15. Kiểm tra sau renewal hoặc rotation

Sau thay đổi cần xác minh cả control plane và data plane:

### Certificate

- Check certificate serial/fingerprint và NotAfter trên endpoint thực tế.
- Kiểm tra hostname/SAN, chain, EKU, key algorithm và trust.
- Kiểm tra TLS handshake từ client/runtime đại diện.
- Kiểm tra tất cả region, load balancer, ingress và edge endpoint.
- Kiểm tra certificate cũ không còn được serve sau thời gian chuyển.

### Domain/DNS

- Kiểm tra trạng thái domain tại registrar/registry.
- Query authoritative nameserver và một số recursive resolver.
- Xác minh NS, A/AAAA/CNAME, MX, TXT, CAA và DS nếu liên quan.
- Kiểm tra DNSSEC validation và SERVFAIL.
- Xác minh certificate/domain binding sau thay đổi DNS.

### Secret/API key

- Test auth từ từng consumer.
- Kiểm tra usage log của key mới và cũ.
- Xác minh không còn config/file/image chứa credential cũ.
- Test rollback nếu provider hỗ trợ và policy cho phép.
- Revoke credential cũ sau verification và overlap.

### License

- Kiểm tra entitlement/activation từ runtime.
- Xác minh đúng số instance/node/seat được cấp.
- Kiểm tra support coverage và renewal receipt.

## 16. Incident response khi phụ thuộc hết hạn hoặc bị thu hồi

Khi sự cố xảy ra, ưu tiên khôi phục dịch vụ và giữ lại bằng chứng. Quy trình:

1. Xác định asset hết hạn/bị revoke, issuer/provider và thời điểm.
2. Xác định phạm vi consumer, region, tenant và luồng nghiệp vụ ảnh hưởng.
3. Phân biệt expiry, revoked, invalid chain, wrong hostname, DNS failure, bad secret hoặc quota/license denial.
4. Nếu phù hợp, phát hành/renew credential mới theo runbook khẩn cấp.
5. Phân phối an toàn và chuyển consumer theo rollout có kiểm soát.
6. Xác minh từ client thực tế, business SLI và dependency health.
7. Nếu credential bị compromise, revoke ngay theo incident policy; không giữ overlap an toàn giả tạo.
8. Kiểm tra mọi bản sao/config/cache/session chứa credential bị ảnh hưởng.
9. Thông báo owner/đối tác/khách hàng theo mức độ tác động và nghĩa vụ hợp đồng.
10. Ghi timeline, root cause, thời gian phát hiện/khôi phục và corrective action.

Không khôi phục bằng cách tắt TLS verification, bỏ qua hostname validation hoặc dùng certificate/secret không xác minh nguồn gốc. Đây là cách biến lỗi sẵn sàng thành lỗ hổng bảo mật.

## 17. Case study: quản lý certificate và secret cho nền tảng đặt phòng

**Bối cảnh:** một nền tảng đặt phòng có website, public API, partner API, payment integration và nhiều internal service chạy mTLS. Website/API dùng certificate managed; partner kết nối bằng client certificate; Payment API dùng client secret; token nội bộ được ký bằng key có rotation định kỳ. Một số dependency do team khác hoặc đối tác quản lý.

### 17.1. Inventory ban đầu

| Asset | Owner | Consumer | Expiry/rotation | Criticality |
|---|---|---|---|---|
| www domain | Business/legal + platform DNS | Website, email | Registrar renewal | Critical |
| api TLS certificate | Platform team | Mobile/web clients, partners | Auto renew + deploy verification | Critical |
| Partner mTLS certificate | Integration team | Partner gateway | Coordinated rollover | High |
| Payment client secret | Payment team | Booking API, reconciliation worker | Provider rotation | Critical |
| JWT signing key | Security/platform | Internal APIs, token consumers | Key rollover | Critical |
| Monitoring license | Operations/procurement | Observability agents | Contract renewal | Medium |

### 17.2. Thiết kế vận hành

1. Inventory lấy certificate metadata từ cloud manager, DNS/registrar report và secret metadata từ vault.
2. Mỗi asset có primary owner, backup owner, business owner, impacted consumers và runbook.
3. Certificate public API dùng ACME/managed renewal; alert riêng cho renew và deployment.
4. Partner mTLS có lịch overlap; partner xác nhận trust bundle trước khi chuyển client certificate.
5. Payment secret tạo version mới, phân phối qua vault, rollout Booking API/worker, kiểm tra usage rồi revoke key cũ.
6. JWT signing key publish JWKS key mới trước khi signer dùng key mới; consumer refresh key và xác minh token.
7. Domain auto-renew bật, registrar account bảo vệ MFA/lock, expiry được theo dõi độc lập với DNS health.
8. License được gắn procurement owner và technical owner; renewal được xác nhận bằng entitlement check.

### 17.3. Kiểm thử và tiêu chí nghiệm thu

- Không có production asset critical thiếu owner hoặc expiration metadata.
- Public endpoint phục vụ certificate đúng SAN/chain và còn thời hạn.
- Tất cả partner chấp nhận certificate mới trước khi certificate cũ bị retire.
- Payment consumer dùng secret version mới; key cũ không còn usage rồi mới revoke.
- JWT consumer xác minh được key mới và token cũ trong overlap theo policy.
- DNS/registrar renewal được xác nhận qua provider status và query thực tế.
- Alert tới đúng owner với đủ lead time; runbook đã được diễn tập.
- Không có secret/private key trong repo, log hoặc dashboard.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ lưu ngày hết hạn trong calendar cá nhân | Không có owner thay thế, dễ bỏ sót | Inventory tập trung và alert đa kênh |
| Renew certificate nhưng không deploy | Endpoint vẫn serve certificate cũ | Verify fingerprint/NotAfter trên endpoint |
| Chỉ theo dõi expiry, không theo consumer | Consumer chưa cập nhật khi key cũ bị revoke | Dependency graph và consumer verification |
| Xoay secret và revoke key cũ ngay | Service chưa chuyển bị outage | Overlap, rollout, verify rồi revoke |
| Dùng chung một certificate/private key quá nhiều nơi | Blast radius lớn khi lộ key | Tách identity/environment và scope |
| Cấp DNS token toàn quyền cho ACME client | Compromise client có thể sửa toàn zone | Scoped token và least privilege |
| Cho rằng auto-renew luôn thành công | Payment/account/validation lỗi không được phát hiện | Kiểm tra renewal status và external endpoint |
| Xóa key cũ trước khi consumer refresh JWKS | Token hợp lệ bị từ chối | Publish key mới, overlap cache, retire có kiểm soát |
| Chuyển DNSSEC DS/DNSKEY sai thứ tự | Resolver trả SERVFAIL | Kế hoạch rollover và validating-resolver checks |
| Bỏ qua domain registrar vì DNS vẫn đang hoạt động | Mất quyền kiểm soát domain khi hết registration | Theo dõi registrar status độc lập |
| Log secret để debug auth failure | Credential bị lộ trong telemetry | Redaction và log metadata/fingerprint |
| Tắt TLS verification để chữa cháy | Mất xác thực peer, mở đường MITM | Cấp certificate hợp lệ và sửa trust chain |
| Không diễn tập renewal failure | Runbook không đủ quyền hoặc thiếu bước | Staging rehearsal và emergency drill |

## 19. Checklist review lifecycle

### Inventory và dependency

- [ ] Tất cả certificate, domain, DNS, key, secret, token, license và contract critical đều được inventory.
- [ ] Asset có owner kỹ thuật, business owner, backup owner và runbook.
- [ ] Expires-at, renewal method, issuer/provider và evidence được ghi rõ.
- [ ] Dependency graph xác định đầy đủ consumer và blast radius.
- [ ] Inventory được phát hiện tự động và reconciliation định kỳ.

### Renewal và rotation

- [ ] Certificate renewal có kiểm tra SAN, chain, validity và endpoint serving.
- [ ] ACME/DNS challenge dùng quyền tối thiểu.
- [ ] Registrar auto-renew, payment/contact, MFA và domain lock được kiểm tra.
- [ ] DNSSEC rollover có quy trình DS/DNSKEY và kiểm tra validating resolver.
- [ ] Secret/signing key rotation có overlap, rollout, consumer verification và revoke.
- [ ] License/contract có procurement và technical owner.
- [ ] Automation idempotent, có approval/rollback và không log secret.

### Monitoring và incident

- [ ] Alert theo days remaining, criticality, consumer và owner.
- [ ] Có alert riêng cho renewed, deployed, served và verified state.
- [ ] Theo dõi key cũ còn được sử dụng sau rollover.
- [ ] Có runbook cho expiration, revocation, DNSSEC failure và provider outage.
- [ ] Đã diễn tập renewal/rotation và emergency compromise scenario.
- [ ] Không cần tắt TLS validation hoặc nới policy để khôi phục.

## 20. Bài tập thực hành

**Bối cảnh:** một hệ thống đặt phòng có domain chính sẽ hết hạn sau 35 ngày; public API certificate hết hạn sau 18 ngày; payment client secret sẽ bị provider thu hồi sau 12 ngày; hai partner đang pin client certificate cũ; JWT signing key mới đã tạo nhưng một số consumer cache JWKS trong nhiều giờ. Inventory hiện thiếu owner của một subdomain.

Hãy lập kế hoạch:

1. Xếp hạng rủi ro theo impact, likelihood, exposure, thời gian còn lại và số consumer.
2. Gán owner/business owner và bổ sung inventory/dependency graph.
3. Lập lịch domain renewal, kiểm tra payment/contact/registrar lock.
4. Renew và deploy public API certificate; xác minh endpoint và chain.
5. Lập rollover mTLS phối hợp partner với overlap và xác nhận cutover.
6. Xoay payment secret qua secret manager, rollout hai consumer, quan sát usage rồi revoke key cũ.
7. Publish JWKS key mới, điều chỉnh cache/refresh và xác minh consumer trước khi retire key cũ.
8. Đặt alert theo mốc 30/14/7/3 ngày phù hợp criticality và lead time.
9. Xây runbook khi renewal job thất bại hoặc credential cũ bị compromise.
10. Định nghĩa tiêu chí nghiệm thu và evidence cho từng asset.

**Gợi ý tự kiểm tra:** Domain registration và DNS health là hai trạng thái riêng. Certificate được renew không có nghĩa endpoint đã serve certificate mới. Partner pinning và JWKS cache cần tính vào overlap. Khi secret bị compromise, quy trình khẩn cấp ưu tiên revocation và khôi phục trust; không duy trì key cũ chỉ để tránh thay đổi.

## 21. Ghi nhớ

Phụ thuộc có thời hạn là tài sản vận hành cần owner, inventory, consumer map và quy trình lifecycle. Certificate, domain, DNS, secret, signing key và license có cơ chế hết hạn/renewal khác nhau; không thể quản lý tất cả bằng một lịch nhắc đơn giản.

Renewal thành công phải được xác minh ở nơi sử dụng thực tế. Certificate mới cần được serve; DNSSEC cần chain hợp lệ; secret mới phải được mọi consumer sử dụng trước khi revoke key cũ; signing key mới phải được consumer tin cậy; domain registration cần được xác nhận tại registrar. Automation, overlap, staged rollout, least privilege, alert theo lead time và runbook diễn tập giúp ngăn expiry biến thành outage hoặc biến rotation thành sự cố bảo mật.
