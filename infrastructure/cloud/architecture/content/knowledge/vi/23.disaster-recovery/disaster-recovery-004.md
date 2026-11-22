# Sao lưu dữ liệu, cấu hình, khóa và phụ thuộc cần phục hồi

Một bản backup database tốt chưa chắc đủ để khôi phục một ứng dụng cloud. Sau sự cố mất region, xóa nhầm tài nguyên hoặc compromise tài khoản cloud, nhóm vận hành có thể còn database snapshot nhưng không còn cấu hình triển khai, secret, khóa mã hóa, chứng thư, DNS record, image container, schema migration hay quyền truy cập để khởi chạy hệ thống. Ngược lại, có đủ Terraform và application image nhưng thiếu dữ liệu, transaction log hoặc khóa giải mã thì dịch vụ cũng không trở lại trạng thái hoạt động.

Disaster recovery (DR) vì vậy cần nhìn hệ thống như một tập hợp phụ thuộc có quan hệ với nhau. Đối tượng cần bảo vệ không chỉ là dữ liệu nghiệp vụ mà còn là **khả năng tái tạo môi trường và mở, xác thực, giải mã, kết nối, định tuyến, vận hành dữ liệu đó**. Bài học này hướng dẫn lập phạm vi backup, quản lý cấu hình và key material, bảo vệ phụ thuộc bên ngoài, xác định thứ tự restore và kiểm chứng kết quả.

Bài học thuộc chương **Phục hồi thảm họa** của module **CLOUD_ARCHITECTURE**. Trọng tâm là thiết kế DR từ yêu cầu nghiệp vụ đến tài nguyên hạ tầng, dữ liệu và vận hành, cân bằng độ tin cậy, bảo mật, khả năng mở rộng và chi phí theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao database backup đơn lẻ không đủ khôi phục một dịch vụ cloud.
2. Lập inventory backup cho dữ liệu, cấu hình, mã nguồn, artifact, khóa và phụ thuộc bên ngoài.
3. Phân biệt backup, snapshot, replication, archive và infrastructure as code (IaC).
4. Chọn tần suất, retention, tính nhất quán và vị trí lưu bản sao theo RPO/RTO.
5. Thiết kế cách bảo vệ secret, KMS key, certificate, identity và quyền truy cập trong DR.
6. Xác định dependency graph và thứ tự phục hồi từ control plane đến data plane.
7. Kiểm soát version, integrity, immutability, isolation và khả năng phục hồi khi tài khoản/region chính bị mất.
8. Thực hiện restore test, đối soát dữ liệu và đo thời gian phục hồi thực tế.

## 2. Phục hồi dịch vụ cần nhiều hơn database

### 2.1. Nhìn hệ thống như một tập hợp phụ thuộc

Một ứng dụng đặt chỗ có thể cần các thành phần sau:

~~~mermaid
flowchart TD
    DNS[DNS and domain] --> EDGE[CDN / WAF / Load balancer]
    EDGE --> APP[Application runtime]
    APP --> ID[Identity and authorization]
    APP --> CFG[Configuration and feature flags]
    APP --> DB[(Database and transaction logs)]
    APP --> CACHE[(Cache)]
    APP --> BUS[Queue / event broker]
    APP --> OBJ[(Object storage)]
    APP --> EXT[Payment / email / third-party APIs]
    DB --> KEY[KMS / encryption keys]
    OBJ --> KEY
    APP --> CERT[Certificates and trust material]
    APP --> OBS[Logs / metrics / traces]
    IAC[Infrastructure definitions and artifacts] --> EDGE
    IAC --> APP
    IAC --> DB
~~~

Các thành phần này có thể nằm ở nhiều account, project, subscription hoặc region. Mỗi thành phần có vòng đời backup, quyền truy cập và cách restore khác nhau. Một số dữ liệu có thể tái tạo từ nguồn khác; một số khác không thể tái tạo nếu mất key hoặc metadata.

### 2.2. Câu hỏi kiểm tra khả năng khôi phục

Với từng thành phần, hãy hỏi:

- Nếu mất hoàn toàn, dịch vụ có thể tạo lại từ đâu?
- Dữ liệu nào là nguồn chuẩn, dữ liệu nào là bản sao?
- Bản backup nằm ở đâu và có còn truy cập khi account/region chính gặp sự cố không?
- Ai có quyền restore và ai có quyền giải mã?
- Phiên bản nào của schema, app và config tương thích với bản dữ liệu này?
- Thành phần nào phải sẵn sàng trước để thành phần khác hoạt động?
- Nếu provider hoặc SaaS ngoài ngừng hoạt động, có phương án thay thế không?
- Có thể kiểm chứng bản restore mà không ảnh hưởng production không?

### 2.3. Recovery set

Một **recovery set** là tập artifact và metadata cần thiết để dựng lại một năng lực nghiệp vụ tại một mốc xác định. Ví dụ recovery set cho Booking API có thể gồm database snapshot và log tới thời điểm cần thiết, schema migration, application image, deployment manifest, config version, secret/key references, DNS/certificate, identity policy, network rule và danh sách dependency ngoài.

Không nhất thiết backup mọi thứ theo cùng tần suất. Mục tiêu là bảo đảm có thể tìm đúng phiên bản của từng thành phần và phối hợp chúng thành một môi trường tương thích.

## 3. Phân loại đối tượng cần backup

### 3.1. Ma trận inventory ban đầu

| Nhóm | Ví dụ | Cách bảo vệ thường gặp | Câu hỏi phục hồi |
|---|---|---|---|
| Dữ liệu giao dịch | Database, transaction log, ledger | Snapshot, PITR, export, replica/backup | Có thể restore tới mốc đúng không? |
| File và object | Upload, invoice, attachment | Versioning, replication, immutable copy | Metadata và object có cùng mốc không? |
| Cấu hình | App config, routing, feature flag | Version control, encrypted export, config history | Có biết phiên bản tương thích không? |
| Hạ tầng | Network, IAM, database resource, cluster | IaC, provider backup/export | Có dựng lại được trong account/region sạch không? |
| Mã nguồn và artifact | Source, binary, image, package | Git mirror, artifact registry replication | Artifact có đúng digest và dependency không? |
| Khóa và chứng thư | KMS/HSM key, signing key, TLS cert | Key backup/export nếu hỗ trợ, escrow, managed rotation records | Có thể giải mã và xác thực dữ liệu cũ không? |
| Identity | IdP config, federation, roles, break-glass identity | Config export, recovery account, documented trust | Ai có thể đăng nhập để bắt đầu restore? |
| Messaging | Queue/topic config, DLQ, schema registry | Config export, message archive nếu cần | Có thể replay mà không tạo side effect sai không? |
| DNS và network edge | Zone records, health checks, WAF, CDN | Zone export, IaC, provider config backup | Có thể chuyển traffic an toàn không? |
| Observability | Alert, dashboard, log pipeline | Config as code, export | Có thể nhìn thấy lỗi sau recovery không? |
| SaaS/dependency ngoài | Payment, email, CRM, support | Config/contract/API inventory, data export theo quyền | Credential, webhook và endpoint còn dùng được không? |
| Runbook và tài liệu | ADR, recovery procedures, contact tree | Version control, offline copy | Đội ứng cứu có đọc được khi hệ thống chính mất không? |

Inventory nên có owner, criticality, source of truth, backup method, frequency, retention, encryption, destination, restore procedure và lần kiểm thử gần nhất cho mỗi mục.

### 3.2. Phân loại khả năng tái tạo

Có thể chia tài nguyên thành ba nhóm:

- **Không thể tái tạo nếu mất:** dữ liệu giao dịch, file khách hàng, một số private key hoặc dữ liệu audit bắt buộc.
- **Tái tạo được từ nguồn kiểm soát:** application image từ artifact registry, network và compute từ IaC, schema từ migration repository.
- **Tái tạo hoặc đồng bộ lại được nhưng có chi phí/thời gian:** search index, cache, analytics projection, dashboard tổng hợp hoặc một số event stream.

Nhóm “tái tạo được” vẫn cần kiểm chứng nguồn tạo lại có độc lập với failure domain hay không. Source code trong Git trên cùng identity provider hoặc artifact chỉ nằm trong region bị mất có thể không truy cập được khi cần.

## 4. Dữ liệu database và tính nhất quán của backup

### 4.1. Snapshot, transaction log và point-in-time recovery

**Snapshot** chụp trạng thái dữ liệu tại một thời điểm hoặc theo cơ chế snapshot của dịch vụ. **Transaction log backup** ghi lại thay đổi sau một mốc, cho phép phục hồi tới thời điểm gần hơn. **Point-in-time recovery (PITR)** kết hợp base backup và log theo khả năng của database để khôi phục đến một thời điểm được hỗ trợ trong retention window.

~~~text
T0        T1        T2        T3        T4
|---------|---------|---------|---------|
Snapshot  Log       Log       Failure   Restore target
          segment   segment   event     before bad write
~~~

PITR hữu ích khi có thao tác xóa nhầm, ghi lỗi hoặc corruption được phát hiện sau đó. Nhưng phạm vi thời gian, độ phân giải restore, thời gian giữ log và giới hạn dịch vụ phụ thuộc database/provider. Phải kiểm tra cấu hình thực tế và đo thử.

### 4.2. Crash-consistent và application-consistent

Snapshot ở mức storage có thể chỉ bảo đảm nhất quán kiểu crash-consistent: tương tự trạng thái khi máy bị mất điện, hệ thống cần recovery log khi khởi động. Application-consistent backup phối hợp với ứng dụng/database để đảm bảo dữ liệu ở trạng thái hợp lệ hơn tại thời điểm chụp.

Với database có transaction log và cơ chế recovery phù hợp, crash-consistent snapshot vẫn có thể phục hồi đúng theo tài liệu hệ quản trị. Với hệ thống ghi nhiều file liên quan nhau, cần pause/flush hoặc dùng cơ chế snapshot nhất quán xuyên volume.

### 4.3. Backup nhiều nguồn có nhất quán với nhau không?

Ứng dụng thường lưu dữ liệu liên quan trong database và object storage. Nếu snapshot database ở T1 nhưng object copy ở T2, metadata có thể tham chiếu file chưa có hoặc file mới không còn được tham chiếu.

Các hướng xử lý:

- Dùng version/object ID bất biến và metadata trỏ tới version cụ thể.
- Ghi manifest recovery với snapshot ID, object version và timestamp/cursor.
- Tạm dừng hoặc quiesce ghi trong cửa sổ snapshot nếu yêu cầu nhất quán cao.
- Dùng transaction/outbox hoặc workflow để theo dõi object upload đã hoàn tất.
- Kiểm tra tham chiếu database tới object sau restore.

Không giả định hai dịch vụ cloud độc lập có thể chụp snapshot nguyên tử cùng thời điểm.

### 4.4. Phạm vi database cần lưu

- Primary data và transaction/WAL/binlog/PITR log.
- Schema, migration version, extension và collation cần thiết.
- Stored procedure, trigger, constraint, view và database role khi cần.
- Replication/partition configuration và metadata liên quan.
- Encryption configuration, key ID và key version reference.
- Database parameter/configuration và connection settings.
- Catalog, metadata hoặc sequence cần để ứng dụng hoạt động.

Không lưu password plaintext trong bản dump. Credential cần phục hồi phải nằm trong secret manager hoặc recovery process riêng.

## 5. File, object storage và dữ liệu phi cấu trúc

Object storage thường chứa file upload, invoice, ảnh, export và artifact nghiệp vụ. Backup cần xác định rõ:

- Bucket/container và prefix thuộc ứng dụng/tenant nào.
- Versioning, retention, lifecycle rule và object lock.
- Replication theo vùng và replication lag.
- Metadata, tags, ACL/policy và encryption context.
- Multipart upload dang dở và object chưa được tham chiếu.
- Cách restore object version và sửa lại metadata reference.

### 5.1. Versioning không đồng nghĩa backup độc lập

Versioning giúp khôi phục phiên bản object cũ khi ghi đè hoặc xóa theo semantics của provider. Nhưng version vẫn có thể nằm trong cùng account, cùng quyền quản trị và cùng failure domain. Nếu kẻ tấn công có quyền xóa cả bucket và version, versioning đơn lẻ có thể không đủ.

Kết hợp versioning với replication, object lock/retention, backup account hoặc archive bất biến tùy yêu cầu. Kiểm tra quyền xóa version và lifecycle policy bằng thử nghiệm.

### 5.2. Object lock và immutable copy

Immutable backup hạn chế khả năng sửa/xóa bản sao trong khoảng thời gian được bảo vệ. Cần kiểm tra mode, retention period, legal hold và quyền override của platform. Bản immutable vẫn phải được bảo vệ bằng mã hóa, IAM và quy trình restore; nó không tự đảm bảo nội dung backup chính xác hoặc dùng được.

### 5.3. Manifest cho dữ liệu file

Một manifest có thể ghi object key/version, checksum, size, tenant scope, source snapshot và thời điểm. Khi restore, đối chiếu manifest với object store để phát hiện object thiếu, sai checksum hoặc thuộc tenant khác.

## 6. Cấu hình ứng dụng, hạ tầng và deployment

### 6.1. Cấu hình runtime

Phải bảo vệ các cấu hình quyết định hành vi ứng dụng:

- Feature flag và entitlement.
- Tenant registry, routing map, shard placement.
- Database endpoint, connection pool và timeout.
- Queue/topic, consumer group và retry/DLQ policy.
- CORS, allowed origins, callback URL và webhook settings.
- Rate limit, quota, autoscaling threshold và circuit breaker policy.
- Locale, timezone, template, notification và integration mapping.

Config cần được version hóa, có schema, owner và audit. Tách cấu hình không nhạy cảm khỏi secret. Nếu config service chính không khả dụng, phải biết ứng dụng có thể khởi động với bản config đã cache hay cần restore control plane trước.

### 6.2. Infrastructure as Code

IaC như Terraform, CloudFormation, Bicep hoặc công cụ tương đương mô tả tài nguyên cần tạo. Bảo vệ:

- Source code IaC và module đã pin version.
- State file và backend configuration.
- Provider version, lock file và dependency.
- Variable template, policy, subnet/CIDR plan.
- Import mapping và resource identifiers cần tham chiếu.
- Pipeline, runner identity và approval rules.

State file có thể chứa tên tài nguyên, endpoint và đôi khi cả secret nhạy cảm tùy provider/module. Phải mã hóa, giới hạn truy cập, versioning và backup state độc lập. Không đưa plaintext secret vào repo hoặc artifact chỉ vì cần tái tạo hạ tầng.

### 6.3. State và drift

Backup state không có nghĩa là hạ tầng thực tế vẫn giống state đó. Có thể tồn tại thay đổi thủ công ngoài IaC (drift). Trước DR, cần so sánh state, plan và resource inventory; quyết định import, recreate hoặc reconcile từng tài nguyên.

Không chạy apply mù quáng trên một account/region mới với state cũ. Có thể vô tình sửa hoặc xóa tài nguyên không thuộc recovery target. Dùng workspace/backend riêng, review plan và kiểm tra account/region trước khi apply.

### 6.4. Mã nguồn và artifact

Source repository nên có mirror hoặc bản sao ở failure domain khác. Artifact production nên bất biến theo digest/version, được scan và ký nếu quy trình yêu cầu. Khôi phục từ artifact đã kiểm chứng giúp tránh phụ thuộc build toolchain hoặc package registry đang lỗi trong sự cố.

Lưu cả:

- Container image digest và registry location.
- Package/binary, SBOM và provenance nếu có.
- Runtime version, base image và migration scripts.
- Deployment manifest, Helm chart hoặc task definition.
- Build pipeline definition và dependency lock.

Không chỉ lưu tag như latest vì tag có thể trỏ sang nội dung khác sau này.

## 7. Secret, encryption key và certificate

### 7.1. Vì sao key là phụ thuộc sống còn?

Một database snapshot có thể chứa ciphertext hoặc dữ liệu được mã hóa bằng envelope encryption. Nếu mất key mã hóa hoặc key-encryption key, bản backup có thể không giải mã được. Nếu mất signing key, token hoặc chữ ký có thể không còn được xác thực. Nếu mất TLS private key/certificate material hoặc trust configuration, client có thể không thiết lập được kết nối.

Vì vậy cần lập inventory key và định nghĩa khả năng phục hồi theo loại key, thay vì chỉ ghi “KMS đã được cấu hình”.

### 7.2. Phân loại key material

| Loại | Vai trò | Cần lưu/khôi phục |
|---|---|---|
| Data encryption key (DEK) | Mã hóa dữ liệu thực tế | Ciphertext, wrapped DEK và cơ chế unwrap |
| Key encryption key (KEK) / KMS key | Bọc hoặc giải mã DEK | Key resource, policy, region/account access và key version |
| Signing key | Ký token, artifact hoặc event | Private key an toàn, public key history và key ID |
| TLS private key | Thiết lập TLS | Certificate/key lifecycle hoặc quy trình cấp lại |
| API credential | Kết nối dependency ngoài | Secret reference, rotation procedure và quyền provider |
| Recovery/break-glass credential | Khôi phục quyền admin | Lưu trữ ngoại tuyến/controlled vault, dual control và audit |

### 7.3. Managed KMS và ranh giới phục hồi

Với KMS/HSM managed service, private key có thể không export được theo thiết kế. Điều cần bảo vệ là:

- Key resource còn tồn tại và không ở trạng thái disabled/destroyed.
- Account/project và principal có quyền sử dụng key trong recovery environment.
- Key policy, IAM policy, grant, alias và key version được cấu hình đúng.
- Region DR có key tương ứng hoặc cơ chế multi-region key được provider hỗ trợ.
- Các key phụ thuộc nhau (KEK, signing, database encryption) có thứ tự khôi phục phù hợp.
- Có contact/escalation cho account recovery và provider support.

Không thể giả định key managed ở region A tự dùng được tại region B. Semantics multi-region key, replication, import/export và deletion khác nhau theo provider. Phải kiểm tra tài liệu và thử decrypt bằng bản sao dữ liệu trong môi trường DR.

### 7.4. Backup key an toàn

Private key có thể export được chỉ nên backup theo quy trình được phê duyệt: mã hóa bằng cơ chế bảo vệ độc lập, chia quyền, giới hạn người truy cập, lưu tách failure domain và ghi audit. Không lưu key plaintext cùng database dump hoặc cùng account mà key đó cần bảo vệ.

Không phải mọi key đều nên backup. Với certificate có thể cấp lại từ CA, quy trình cấp mới và validation có thể an toàn hơn lưu private key lâu dài. Với key không thể tái tạo, cần quy trình escrow/backup phù hợp.

### 7.5. Rotation và khả năng giải mã dữ liệu cũ

Khi rotate key, dữ liệu cũ có thể vẫn được mã hóa bằng key version cũ. Cần giữ khả năng decrypt cho đến khi mọi dữ liệu/backup cần lưu đã được re-encrypt hoặc hết retention.

Lưu metadata như key ID, key version, algorithm, encryption context và thời điểm hiệu lực. Kiểm thử restore với dữ liệu được mã hóa bằng nhiều thế hệ key. Không hủy key cũ chỉ vì key mới đã phát hành.

### 7.6. Secret rotation trong DR

Sau sự cố compromise, có thể cần rotate credential thay vì phục hồi nguyên trạng secret cũ. Runbook nên phân biệt:

- Secret cần phục hồi để đọc dữ liệu/khởi tạo hệ thống.
- Secret cần rotate ngay vì đã bị lộ.
- Secret có thể tái tạo sau khi recovery account hoạt động.
- Token/session cần revoke, không phục hồi.

Không khôi phục một credential đã bị thu hồi hoặc nghi bị xâm phạm chỉ để làm ứng dụng chạy nhanh hơn.

## 8. Identity, quyền truy cập và break-glass

DR có thể thất bại trước khi bắt đầu nếu admin không đăng nhập được vào cloud account, identity provider hoặc secret vault.

Chuẩn bị:

- Recovery identity độc lập với IdP/region đang được bảo vệ khi khả thi.
- Break-glass account được bảo vệ bằng MFA/hardware factor và dual control.
- Quy trình khôi phục federation, SSO, DNS và certificate.
- IAM policy hoặc role tối thiểu để đọc backup, giải mã và provision DR.
- Danh sách approver, escalation contact và phương thức xác minh ngoài hệ thống chính.
- Test định kỳ việc đăng nhập từ recovery workstation/network.

Break-glass credential phải được quản lý như tài sản cực kỳ nhạy cảm: cất giữ an toàn, không dùng thường nhật, cảnh báo mọi lần sử dụng và rotate sau khi diễn tập hoặc sự cố theo policy.

## 9. Dependency bên ngoài cần đưa vào recovery plan

### 9.1. Identity provider

Ứng dụng có thể phụ thuộc SSO, OIDC/SAML, MFA, directory sync và identity federation. Cần lưu configuration export, issuer/metadata, client ID, redirect URI, group mapping, signing/encryption certificate reference và quy trình emergency admin. Client secret/private key được quản lý trong vault.

Nếu IdP chính bị gián đoạn, có cần local recovery admin không? Nếu có, quyền này phải giới hạn, audit và chỉ kích hoạt theo quy trình.

### 9.2. DNS, domain và certificate

Lưu zone file hoặc export DNS, record, TTL, health check, registrar ownership, domain renewal contact, DNSSEC config và certificate issuance procedure. Một DNS record có thể tạo lại, nhưng quyền truy cập registrar hoặc khóa DNSSEC không sẵn sàng có thể làm DR bị trì hoãn.

Hãy xác định TTL và kế hoạch chuyển traffic trước sự cố; không thay NS hoặc DNSSEC vội vàng khi chưa biết trạng thái registrar và authoritative DNS.

### 9.3. Payment, email và SaaS

Ghi inventory dependency với:

- Provider/tenant/account và region.
- API base URL, webhook endpoint và subscription.
- Credential reference, rotation owner và expiry.
- Data export/retention và SLA hỗ trợ.
- Rate limit, quota, allowlist IP và certificate requirement.
- Cơ chế reconcile giao dịch sau khi kết nối lại.

Không phải dependency ngoài nào cũng có thể backup. Một payment provider có thể giữ ledger có thẩm quyền; ứng dụng cần lưu transaction reference, idempotency key và quy trình đối soát thay vì cố sao chép private state của provider.

### 9.4. Network và security perimeter

Khôi phục VPC/VNet, subnet, route, NAT, firewall/security group, private endpoint, peering, transit gateway, VPN/Direct Connect/ExpressRoute, WAF và egress policy. Phải bảo đảm địa chỉ IP allowlist ở đối tác ngoài vẫn cho phép traffic từ DR region nếu thiết kế cần.

### 9.5. Messaging và schema registry

Queue/topic config, retention, DLQ, partition, consumer group, ACL, schema registry và event compatibility có thể là dependency bắt buộc. Nếu message được giữ ở broker chính nhưng broker mất, cần biết có archive/replay source hay không. Đừng giả định mọi queue message được backup tự động; kiểm tra semantics và retention của dịch vụ.

## 10. Thứ tự phục hồi theo dependency graph

### 10.1. Khôi phục từ nền tảng lên ứng dụng

Thứ tự chính xác phụ thuộc kiến trúc, nhưng một chuỗi thường gặp:

1. **Quyền truy cập recovery:** account, identity, MFA, break-glass, audit.
2. **Key và trust:** KMS/HSM access, key policy, certificate, signing trust.
3. **Control plane:** network, IAM roles, IaC backend/state, config service, registry.
4. **Data foundation:** storage, database, transaction log/PITR, schema và replication.
5. **Messaging và dependency:** queue, schema registry, object store, cache hoặc projection.
6. **Runtime:** compute, cluster, container image, application config và secrets.
7. **Edge:** DNS, CDN, WAF, load balancer, certificate và routing.
8. **Validation:** health checks, synthetic transaction, reconciliation và mở traffic theo đợt.

Thứ tự này là khung tham khảo. Ví dụ, database encryption key phải sẵn sàng trước khi restore DB; một số identity service cần network và DNS; workload có thể cần queue trước khi nhận traffic. Hãy derive thứ tự từ dependency graph thực tế.

### 10.2. Dependency graph và critical path

~~~mermaid
flowchart TD
    ACCESS[Recovery identity and account access] --> KEYS[KMS / certificates / trust]
    ACCESS --> NET[Network and IAM baseline]
    KEYS --> DATA[Restore database and object data]
    NET --> CONTROL[Config, registry, deployment control plane]
    CONTROL --> DATA
    DATA --> BUS[Messaging and schema registry]
    DATA --> APP[Application runtime]
    BUS --> APP
    APP --> EDGE[DNS / WAF / load balancer]
    EDGE --> VERIFY[Smoke test and traffic ramp]
~~~

Một thành phần có nhiều dependency sẽ nằm trên critical path. Có thể chạy song song các nhánh độc lập nhưng không được vi phạm quan hệ tiên quyết. Ghi rõ owner và điều kiện hoàn tất của từng node.

### 10.3. Recovery manifest

Manifest giúp chọn đúng phiên bản dữ liệu, config, image và key:

~~~json
{
  "recoveryId": "dr-2026-11-18-01",
  "target": "ap-southeast-2",
  "database": {
    "snapshotId": "snapshot-042",
    "logPosition": "checkpoint-991",
    "schemaVersion": "2026.11.18.3"
  },
  "application": {
    "imageDigest": "sha256:example-digest",
    "release": "booking-api-4.8.2"
  },
  "configuration": {
    "version": 184,
    "tenantRegistryVersion": 72
  },
  "encryption": {
    "keyReferences": ["db-kek-v7", "object-key-v3"]
  }
}
~~~

Đây là cấu trúc minh họa; không điền secret value vào manifest. Manifest nên được ký hoặc lưu ở nơi có integrity control, có người phê duyệt và trỏ tới artifact bất biến.

## 11. Vị trí backup, isolation và khả năng chống phá hoại

### 11.1. Không để backup cùng failure domain

Backup nằm cùng account, cùng role admin và cùng region với production có thể bị mất cùng sự cố hoặc bị xóa cùng lúc. Cân nhắc:

- Cross-region copy cho rủi ro region outage.
- Cross-account/project/subscription cho rủi ro credential compromise.
- Backup vault riêng với policy độc lập.
- Immutable retention hoặc object lock.
- Offline/air-gapped copy cho dữ liệu cực kỳ quan trọng nếu phù hợp.

Mỗi lớp tăng chi phí, egress, độ phức tạp quản lý key và quy trình restore. Chọn theo threat model, RPO/RTO và nghĩa vụ lưu trữ.

### 11.2. 3-2-1 và biến thể

Quy tắc 3-2-1 thường được diễn giải là có nhiều bản sao, trên hơn một loại/vị trí lưu trữ và ít nhất một bản ở ngoài site/failure domain chính. Với cloud, có thể mở rộng tư duy thành:

- Có hơn một bản sao được kiểm chứng.
- Có bản sao ở failure domain độc lập.
- Có ít nhất một bản khó bị sửa/xóa bởi credential production.
- Có bản sao có thể restore mà không phụ thuộc hoàn toàn vào control plane chính.

Con số bản sao không thay thế việc kiểm tra tính nhất quán, retention và restore.

### 11.3. Immutability và least privilege

Backup writer chỉ nên tạo bản sao; delete/retention override dùng identity khác, yêu cầu approval hoặc MFA. Recovery operator chỉ được đọc backup và restore vào target được phép. Mọi thay đổi retention, vault policy, key policy và replication phải audit.

### 11.4. Backup catalog độc lập

Lưu catalog cho biết backup nào tồn tại, thuộc hệ thống nào, mốc thời gian, region, encryption key reference, checksum, retention, owner, trạng thái test và recovery set liên quan. Catalog cần có bản sao độc lập để không mất khả năng tìm backup trong sự cố.

Không lưu secret trong catalog; dùng resource ID và secret reference có thể giải quyết trong recovery environment.

## 12. RPO, RTO và retention quyết định backup strategy

### 12.1. RPO

RPO là lượng mất dữ liệu tối đa tổ chức chấp nhận, thường biểu diễn bằng thời gian trước thời điểm sự cố. RPO 15 phút có nghĩa recovery point phải cách sự cố không quá khoảng 15 phút theo cách đo và phạm vi đã thống nhất.

### 12.2. RTO

RTO là thời gian mục tiêu để khôi phục dịch vụ về mức hoạt động được định nghĩa. RTO không chỉ là thời gian database restore; nó gồm quyền truy cập, key, network, dữ liệu, ứng dụng, DNS, kiểm thử và mở traffic.

### 12.3. Ví dụ chọn chính sách

| Workload | Ví dụ RPO/RTO | Hướng backup/DR có thể xem xét |
|---|---|---|
| Booking/payment core | RPO rất thấp, RTO ngắn | PITR/log backup liên tục, cross-region recovery, runbook và diễn tập thường xuyên |
| Listing/catalog | RPO vài giờ có thể phù hợp tùy nghiệp vụ | Snapshot định kỳ, object versioning, export/replica và rebuild index |
| Search projection | Có thể tái tạo từ source/event | Lưu schema và event replay source; snapshot để rút ngắn rebuild |
| Cache/session | Chấp nhận tái tạo hoặc mất một phần theo policy | Không nhất thiết backup mọi entry; lưu config và source data |
| Audit/compliance | Retention dài, integrity cao | Immutable archive, access log, legal hold và retrieval test |

Các giá trị chỉ minh họa cho cách phân lớp. RPO/RTO phải được chủ nghiệp vụ phê duyệt và được chứng minh bằng thử nghiệm với dữ liệu thực tế.

### 12.4. Retention policy

Retention phải xét:

- RPO và cửa sổ phát hiện corruption/ransomware.
- Thời gian audit, hợp đồng và legal hold.
- Chi phí storage, retrieval và cross-region transfer.
- Thời gian giữ transaction log cho PITR.
- Thời gian giữ key có thể giải mã backup.
- Khả năng restore phiên bản ứng dụng/schema tương ứng.

Backup 90 ngày nhưng key bị hủy sau 30 ngày không phải recovery plan 90 ngày.

## 13. Automation và quy trình backup

### 13.1. Backup as code

Định nghĩa backup policy trong code/config có version: nguồn nào được bảo vệ, schedule, retention, destination vault/account/region, encryption, immutable settings, notification và owner. Review thay đổi backup policy như một thay đổi hạ tầng quan trọng.

### 13.2. Tác vụ sau backup

Một workflow có thể:

1. Tạo snapshot/export.
2. Xác nhận job thành công và backup ID.
3. Kiểm tra kích thước, checksum hoặc metadata theo khả năng dịch vụ.
4. Sao chép sang account/region đích.
5. Áp retention/immutability.
6. Cập nhật backup catalog.
7. Phát cảnh báo khi thiếu bản sao, trễ schedule hoặc quota/storage fail.

Không đánh dấu backup đạt chỉ vì API job trả trạng thái thành công. Cần xác minh bản copy đã hoàn tất và có thể truy xuất ở vị trí phục hồi.

### 13.3. Giám sát backup

Các metric quan trọng:

- Backup success/failure rate.
- Age of latest successful backup.
- PITR log gap và replication lag.
- Cross-region copy completion time.
- Backup bytes, growth và storage capacity.
- Encryption/key availability.
- Immutable retention status.
- Restore test pass rate và measured restore duration.
- Backup catalog drift so với resource inventory.

Alert cần dựa trên RPO: nếu latest recoverable point vượt ngưỡng RPO, phải báo sự cố backup kể cả khi job gần nhất vừa chạy.

## 14. Restore test: bằng chứng quan trọng nhất

### 14.1. Vì sao phải restore thử?

Backup có thể tồn tại nhưng không dùng được do:

- File/dump hỏng hoặc thiếu segment log.
- Key bị disable, xóa hoặc policy không cho decrypt.
- Thiếu schema migration hoặc version ứng dụng tương thích.
- Backup nằm trong account/region không thể truy cập.
- DNS, certificate, identity hoặc secret không thể tái tạo.
- Object metadata lệch với database.
- Restore vượt RTO hoặc tốn capacity không dự kiến.

### 14.2. Các cấp kiểm thử

| Cấp | Thực hiện | Điều chứng minh |
|---|---|---|
| Metadata check | Kiểm tra job, backup ID, size, checksum, retention | Bản sao có mặt và metadata hợp lệ |
| Isolated restore | Restore vào account/network sandbox | Có thể đọc/giải mã và khởi động dữ liệu |
| Application validation | Chạy app và query nghiệp vụ | Schema, config và runtime tương thích |
| DR exercise | Khôi phục dependency đầy đủ, chuyển traffic mô phỏng | Quy trình end-to-end có thể thực hiện |
| Business validation | Đối chiếu giao dịch, báo cáo, owner sign-off | Dữ liệu có ý nghĩa nghiệp vụ và được chấp nhận |

### 14.3. Restore phải kiểm tra key

Một test quan trọng là dùng identity trong recovery environment để:

1. Truy cập backup.
2. Lấy đúng key reference/version.
3. Giải mã snapshot hoặc object sample.
4. Khởi động database và đọc được dữ liệu kiểm tra.
5. Xác thực certificate/signature hoặc token nếu nằm trong phạm vi.

Không chỉ kiểm tra key tồn tại; cần chứng minh principal phục hồi có quyền dùng key và key vẫn có thể giải mã dữ liệu cũ.

### 14.4. Đo RTO thực tế

Ghi thời điểm bắt đầu và kết thúc từng bước: lấy quyền, tạo network, restore database, restore file, deploy app, kiểm tra dependency, DNS cutover và smoke test. Tổng thời gian cùng thời gian chờ approval phải được so với RTO. Nếu vượt mục tiêu, cải tiến runbook hoặc kiến trúc.

## 15. Runbook phục hồi theo kịch bản

### 15.1. Mất region chính

1. Kích hoạt incident command và xác định phạm vi region outage.
2. Xác minh recovery account/identity và quyền truy cập backup vault.
3. Chọn recovery set và point-in-time phù hợp với RPO.
4. Kiểm tra key/KMS, network và config tại region đích.
5. Restore database/object và khôi phục schema, dependency.
6. Deploy artifact bất biến với config tương thích.
7. Smoke test dữ liệu, identity, queue và external integration.
8. Chuyển traffic có kiểm soát; theo dõi lỗi và replication.
9. Ghi nhận RPO/RTO đạt được và giữ source cũ theo policy.

### 15.2. Mất hoặc compromise cloud account

- Dùng recovery identity/account độc lập và xác minh quyền quản trị.
- Truy cập cross-account immutable backup nếu vẫn được bảo vệ.
- Không dùng credential hoặc signing key nghi bị lộ.
- Rotate/reissue secrets, certificates và integration credentials.
- Kiểm tra audit log, resource drift và khả năng persistence của attacker.
- Recreate hạ tầng từ IaC đã kiểm chứng trong account sạch.
- Restore dữ liệu từ bản sao tin cậy sau khi xác định mốc trước compromise.

### 15.3. Xóa nhầm hoặc corruption logic

1. Ngừng job hoặc deployment gây hỏng dữ liệu.
2. Xác định thời điểm đầu tiên dữ liệu sai và phạm vi bị ảnh hưởng.
3. Chọn PITR target trước giao dịch lỗi.
4. Restore vào môi trường riêng, không ghi đè production ngay.
5. Trích xuất/so sánh dữ liệu cần sửa và xác minh invariant.
6. Áp dụng repair có phê duyệt hoặc cutover sang bản phục hồi.
7. Đối soát giao dịch phát sinh sau recovery point.

### 15.4. Mất key hoặc certificate

Phân biệt key bị disable tạm thời, policy sai, key bị xóa có thể recover trong deletion window, key bị phá hủy vĩnh viễn và certificate hết hạn. Kiểm tra provider recovery window, replica/backup và key version. Nếu key không thể phục hồi, đánh giá re-encryption, reissue hoặc tác động không thể khôi phục trước khi tuyên bố backup còn dùng được.

## 16. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ backup database | Mất config, key, image và dependency nên app không chạy | Recovery set bao trọn dependency graph |
| Replica được xem là backup | Xóa nhầm/corruption lan sang replica | Backup versioned/immutable và PITR |
| Backup cùng account và quyền admin production | Attacker có thể xóa cả bản sao | Cross-account vault, least privilege, immutability |
| Mất KMS key hoặc policy | Snapshot còn nhưng không giải mã được | Key inventory, policy backup/recovery và decrypt test |
| Config không version hóa | Không dựng lại được hành vi hệ thống tại recovery point | Config as code, version và manifest |
| Chỉ lưu image tag | Tag có thể thay đổi, không biết chính xác binary | Pin digest và giữ artifact bất biến |
| IaC state không được bảo vệ | Không thể cập nhật/reconcile hạ tầng | State backup mã hóa, access control và restore test |
| Không backup DNS/registrar access | Không thể chuyển traffic dù app đã chạy | Zone export, registrar recovery và documented process |
| Certificate/secret hết hạn trong DR | Kết nối hoặc xác thực thất bại | Expiry monitoring, renewal runbook và key inventory |
| Backup job thành công được coi là restore thành công | Phát hiện lỗi quá muộn trong thảm họa | Isolated restore và DR exercise |
| Restore dữ liệu không tương thích app/schema | Runtime lỗi hoặc ghi dữ liệu sai | Recovery manifest và compatibility validation |
| Không xét queue/event replay | Side effect trùng hoặc mất thứ tự | Idempotency, offsets, DLQ và replay policy |
| Không bảo vệ runbook/contact | Đội ứng cứu không thể thực hiện các bước | Offline copy, owner và contact review |

## 17. Ví dụ recovery set cho Booking Service

Giả sử Booking Service chạy ở một region, dùng relational database, object storage, event broker, KMS, identity provider và payment provider.

### 17.1. Inventory

| Thành phần | Nguồn chuẩn | Bản bảo vệ | Điều kiện phục hồi |
|---|---|---|---|
| Booking DB | Primary relational DB | PITR + cross-region snapshot | KMS key và schema tương thích |
| Attachment/invoice | Object bucket | Versioning + immutable cross-account copy | Object version, checksum và metadata |
| Application | Artifact registry | Image digest mirror và source repo mirror | Runtime config và deployment manifest |
| Tenant/config registry | Config/control-plane DB | Snapshot/export versioned | Placement và policy đúng |
| KMS | Managed key service | Key replica/backup khả dụng theo provider | Recovery principal có quyền decrypt |
| Identity | IdP | Federation/config export, break-glass | Issuer, certificate và admin access |
| Messaging | Broker | Topic/schema config và archive nếu yêu cầu | Offset/replay và idempotent consumer |
| DNS/certificate | Registrar/DNS provider/CA | Zone export, IaC, issuance procedure | Quyền quản trị và certificate valid |
| Payment | Provider system of record | Transaction reference và reconciliation log | Credential mới, webhook và idempotency |

### 17.2. Thứ tự phục hồi

~~~mermaid
flowchart TD
    A[Recovery identity and account] --> B[KMS and certificates]
    A --> C[Network and IAM]
    B --> D[Restore Booking DB and objects]
    C --> E[Restore config and deployment control]
    D --> F[Start event broker and schema registry]
    E --> G[Deploy Booking API]
    F --> G
    G --> H[Validate payment and identity integrations]
    H --> I[DNS cutover and traffic ramp]
    I --> J[Reconcile bookings and attachments]
~~~

### 17.3. Tiêu chí hoàn thành

- Database restore đạt recovery point được phê duyệt.
- Application khởi động đúng release và schema version.
- Các record booking có thể đọc/ghi theo invariant đã kiểm tra.
- File tham chiếu tồn tại, checksum hợp lệ và giải mã được.
- Identity, payment webhook và certificate hoạt động.
- Queue consumer bắt đầu từ offset/replay point an toàn và side effect được deduplicate.
- DNS/edge chuyển traffic; error rate và latency trong ngưỡng.
- Business owner đối soát booking, payment reference và số lượng giao dịch.
- RPO/RTO thực tế được ghi nhận.

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Có catalog, owner, version và runbook cho từng recovery dependency không? | Backup as code, inventory, restore exercise; tăng công việc duy trì metadata |
| **Security** | Backup, key và break-glass có độc lập với credential production không? | Cross-account, immutability, least privilege, MFA và audit |
| **Reliability** | Có thể phục hồi dữ liệu và phụ thuộc theo đúng thứ tự trong RTO/RPO không? | PITR, recovery set, dependency graph, test restore và reconciliation |
| **Performance Efficiency** | Restore có đủ IOPS, network, compute và throughput để bắt kịp không? | Capacity plan, parallel restore và traffic ramp; tài nguyên dự phòng tăng chi phí |
| **Cost Optimization** | Có backup trùng lặp, retention quá dài hoặc archive đắt không cần thiết? | Phân lớp dữ liệu, lifecycle policy, compression và review retention |
| **Sustainability** | Có giữ nhiều artifact hoặc copy không còn giá trị và tốn storage/network? | Retention có căn cứ, cleanup có audit và snapshot/rebuild theo mức quan trọng |

Một backup chỉ có giá trị khi đúng dữ liệu, còn key, truy cập được trong failure domain cần thiết và có thể restore trong thời gian được nghiệp vụ chấp nhận.

## 19. Bài tập áp dụng

### Bài tập A — Snapshot không có key

Nhóm có snapshot database ở region dự phòng nhưng KMS key nằm trong account production đã bị khóa.

**Câu hỏi:** Vì sao backup chưa đủ? Cần bổ sung bằng chứng gì?

**Gợi ý:** Cần xác định key recovery/replica và policy, identity có thể dùng key, key version tương thích, và thực hiện decrypt/restore test từ account dự phòng. Chỉ thấy key ID trong metadata không chứng minh có thể giải mã.

### Bài tập B — Config drift

IaC repository có cấu hình cũ, nhưng production đã đổi route, security group và database parameter bằng thao tác thủ công.

**Câu hỏi:** Dựng DR trực tiếp từ repo có an toàn không?

**Gợi ý:** Chưa. Cần inventory và drift reconciliation, chọn trạng thái mong muốn được phê duyệt, cập nhật IaC rồi test plan trong account/region đích. Không apply state cũ mù quáng.

### Bài tập C — Database và object lệch mốc

Snapshot DB ở 10:00 tham chiếu object upload mới chỉ replicate lúc 10:07. Recovery chỉ có object backup tới 10:05.

**Câu hỏi:** Có thể công bố restore hoàn chỉnh không?

**Gợi ý:** Không nếu record ở 10:00 tham chiếu object chưa có. Cần object versioning/manifest hoặc đồng bộ consistency group, đối soát reference và chấp nhận/repair dữ liệu thiếu theo policy.

### Bài tập D — Credential bị lộ

Sau ransomware, nhóm muốn phục hồi nguyên secret API và signing key từ backup để tiết kiệm thời gian.

**Câu hỏi:** Rủi ro và hướng xử lý?

**Gợi ý:** Secret có thể đã bị attacker biết. Phục hồi quyền giải mã dữ liệu cần thiết nhưng rotate/revoke credential bị ảnh hưởng, cấp lại signing key có kế hoạch overlap public key/token và kiểm tra integration.

### Bài tập E — RTO bị vượt

Backup database restore trong 45 phút nhưng cần thêm 90 phút để dựng network, identity, DNS và application.

**Câu hỏi:** RTO của dịch vụ là bao nhiêu và cải thiện ở đâu?

**Gợi ý:** RTO end-to-end gồm toàn bộ thời gian tới khi dịch vụ đạt tiêu chí phục vụ, không chỉ database. Tối ưu control plane, IaC, recovery identity, automation, pre-provisioned capacity và dependency critical path.

### Bài tập F — Replay queue

Sau restore, nhóm replay mọi message từ broker archive nhưng consumer gửi email xác nhận booking lần nữa.

**Câu hỏi:** Cần thiết kế gì trước khi replay?

**Gợi ý:** Event ID, inbox/idempotency, offset/sequence, replay window, filter loại side effect và chế độ dry-run. Phân biệt cập nhật projection với hành động không thể lặp như email hoặc payment.

## 20. Checklist trước khi phê duyệt backup và recovery plan

- [ ] Recovery set và dependency graph được lập cho từng dịch vụ quan trọng.
- [ ] Mỗi thành phần có owner, source of truth, backup method, retention và restore procedure.
- [ ] Database có snapshot/PITR/log retention phù hợp RPO.
- [ ] Schema, migration, extension, metadata và sequence cần thiết được bảo vệ.
- [ ] Object storage có version, replication/immutable copy và manifest/checksum khi cần.
- [ ] Runtime config, feature flag, tenant routing và entitlement được version hóa.
- [ ] IaC source, state, provider lock, module và pipeline được bảo vệ riêng.
- [ ] Source code, image digest, package và deployment manifest có mirror/artifact bất biến.
- [ ] KMS, HSM, DEK/KEK reference, signing key, certificate và rotation history có recovery plan.
- [ ] Recovery identity, break-glass, MFA, dual control và IAM policy đã được thử.
- [ ] DNS, registrar, WAF, CDN, network, IP allowlist và trust dependency có inventory.
- [ ] SaaS/payment/email/IdP có endpoint, credential reference, quota, contact và reconciliation procedure.
- [ ] Queue/topic, schema registry, DLQ, offsets và replay policy được xác định.
- [ ] Backup nằm ở failure domain độc lập, có immutability/access control phù hợp.
- [ ] Backup catalog độc lập có snapshot ID, time, key reference, checksum, retention và owner.
- [ ] Restore sequencing phản ánh dependency graph và critical path.
- [ ] Recovery manifest ghép đúng data, schema, application, config và key version.
- [ ] Có isolated restore, application validation và DR exercise theo lịch.
- [ ] Đo được RPO/RTO thực tế gồm approvals và dependency restore.
- [ ] Có runbook cho region loss, account compromise, corruption, key failure và queue replay.
- [ ] Có quy trình rotate/revoke secret sau compromise và bảo vệ audit evidence.

**Điểm cốt lõi:** DR không chỉ khôi phục dữ liệu mà phải khôi phục toàn bộ khả năng vận hành dịch vụ. Database, object, cấu hình, IaC, artifact, identity, DNS, secret, key và dependency ngoài phải có owner, phiên bản, bản sao và cách restore rõ ràng. Dependency graph quyết định thứ tự khôi phục; recovery manifest ghép các phiên bản tương thích; restore test chứng minh key, quyền, dữ liệu và ứng dụng thực sự hoạt động. Chỉ khi đo được RPO/RTO end-to-end, tổ chức mới có bằng chứng rằng kế hoạch có thể đáp ứng nhu cầu nghiệp vụ.
