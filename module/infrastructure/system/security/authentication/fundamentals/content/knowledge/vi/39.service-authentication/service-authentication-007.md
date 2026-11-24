# Xoay vòng service credential — Quản lý thay mới bí mật xác thực workload an toàn

> **Chương:** Service authentication  
> **Chủ đề:** Xoay vòng service credential  
> **Phạm vi:** Security Authentication Fundamentals — quản lý vòng đời credential giữa service/workload, giảm thời gian credential bị lộ có thể bị lạm dụng, triển khai xoay vòng không gián đoạn, thu hồi credential cũ và kiểm toán toàn bộ quá trình.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt service credential với credential của người dùng và nhận diện các loại secret/certificate/key được workload sử dụng.
2. Lập inventory có owner, purpose, scope, expiry và dependency cho service credential.
3. Thiết kế rotation policy theo mức nhạy cảm, khả năng bị lộ, khả năng thu hồi và giới hạn của hệ thống.
4. Thực hiện rotation theo mô hình tạo mới, triển khai, xác minh, chuyển đổi và thu hồi credential cũ.
5. Dùng secret manager, KMS/HSM, workload identity và short-lived credential để giảm quản lý secret tĩnh.
6. Triển khai dual-key/overlap window an toàn và tránh credential cũ bị duy trì vô thời hạn.
7. Xử lý rotation cho API key, client secret, database password, certificate, signing key và machine identity.
8. Thiết kế rollback, emergency rotation và incident response khi nghi credential bị compromise.
9. Theo dõi audit, phát hiện credential bất thường và kiểm thử quy trình rotation.

## 1. Service credential là gì?

**Service credential** là bằng chứng xác thực mà một service, process, job, agent hoặc workload sử dụng để chứng minh danh tính của chính nó với một hệ thống khác. Nó cho phép machine-to-machine authentication mà không cần người dùng tương tác trong mỗi request.

Ví dụ:

- Service A dùng client secret để lấy access token từ identity provider;
- Backend dùng database password để kết nối PostgreSQL;
- Workload dùng private key và certificate để xác thực mTLS;
- CI runner dùng token ngắn hạn để tải artifact;
- Agent dùng API key để gọi dịch vụ bên ngoài;
- Service ký JWT bằng private key để chứng minh issuer;
- Workload trong cluster nhận credential thông qua service account hoặc workload identity.

Service credential khác password người dùng ở chủ thể, cách sử dụng và vòng đời. Một credential của workload có thể được dùng tự động bởi hàng trăm instance, tồn tại trong secret store, pipeline, container, file cấu hình hoặc biến môi trường. Nếu credential đó bị lộ, attacker có thể giả mạo workload mà không cần chiếm tài khoản của con người.

### Các loại credential thường gặp

| Loại | Ví dụ | Rủi ro khi bị lộ |
| --- | --- | --- |
| Shared secret | API key, client secret, database password | Bất kỳ ai có secret có thể giả mạo client trong scope được cấp |
| Private key | RSA/ECDSA signing key, mTLS key | Giả mạo chữ ký hoặc danh tính certificate |
| Certificate | Client certificate, service certificate | Có thể xác thực workload nếu private key tương ứng còn bị kiểm soát |
| Access token | OAuth bearer token | Truy cập tài nguyên trong scope/audience và thời hạn |
| Refresh token | Token đổi access token | Có thể kéo dài quyền truy cập nếu không bị revoke/rotate đúng |
| Workload identity assertion | SPIFFE SVID hoặc cloud identity token | Có thể đổi lấy quyền hoặc token ở hệ thống tin cậy |
| SSH credential | SSH key/certificate | Truy cập host, repository hoặc automation account |

Certificate công khai không phải secret. Private key đi kèm certificate mới là vật liệu nhạy cảm. Tương tự, key ID, certificate serial hoặc credential reference có thể cần audit nhưng không nên bị nhầm với secret value.

## 2. Xoay vòng credential là gì và vì sao cần?

**Credential rotation** là quá trình thay một credential đang được sử dụng bằng credential mới, triển khai credential mới tới các thành phần hợp lệ, xác minh hoạt động, rồi thu hồi credential cũ.

Rotation giảm khoảng thời gian attacker có thể sử dụng một credential bị sao chép. Nó cũng hỗ trợ:

- Giảm tác động của secret bị lộ trong log, image, backup hoặc repository;
- Thay key theo chu kỳ cryptographic policy;
- Loại bỏ credential của service đã nghỉ hoặc thay owner;
- Xử lý nhân sự/vendor thay đổi quyền quản trị secret;
- Chuyển từ shared static secret sang identity/token ngắn hạn;
- Đáp ứng yêu cầu compliance và chứng minh kiểm soát vòng đời;
- Giảm rủi ro từ credential không rõ nguồn gốc hoặc không còn owner.

Rotation không tự khắc phục một hệ thống đã bị compromise. Nếu attacker đã lấy private key, biết password hoặc có quyền đọc secret manager, tạo credential mới nhưng giữ nguyên quyền truy cập của attacker sẽ không giải quyết nguyên nhân. Cần điều tra nguồn lộ, thu hồi quyền liên quan và kiểm tra persistence.

### Rotation khác với các thao tác khác

| Thao tác | Mục đích |
| --- | --- |
| Rotation | Thay credential hiện tại bằng credential mới theo kế hoạch |
| Renewal | Gia hạn certificate hoặc credential theo chính sách; có thể giữ nguyên key hoặc tạo key mới |
| Revocation | Làm credential không còn được chấp nhận |
| Reissue | Cấp credential thay thế sau mất/lộ/hỏng |
| Re-enrollment | Đăng ký lại workload/credential vào hệ thống trust |
| Decommission | Ngừng service và thu hồi mọi credential liên quan |

Renew certificate không nhất thiết đồng nghĩa rotate private key. Nếu key có nguy cơ bị lộ, phải tạo key pair mới và revoke/reject key cũ theo quy trình.

## 3. Threat model của service credential

Service credential có thể bị lộ hoặc lạm dụng ở nhiều vị trí:

- Source code, Git history, pull request, issue hoặc package;
- CI/CD variable, build log, artifact và runner;
- Container image, layer, manifest, Helm values;
- File cấu hình, environment variable, crash dump;
- Secret manager, backup, snapshot và export;
- Developer laptop hoặc máy chủ bị compromise;
- Log, tracing, APM, metrics label và support bundle;
- Third-party vendor hoặc SaaS integration;
- Credential bị sao chép giữa staging và production;
- Workload identity trust policy quá rộng.

### Các mục tiêu của attacker

1. Giả mạo service để gọi API hoặc lấy token;
2. Đọc dữ liệu từ database, object storage hoặc message broker;
3. Ký token/JWT hoặc artifact giả;
4. Dùng certificate để thiết lập mTLS với service nội bộ;
5. Tạo persistence bằng credential phụ hoặc key thứ hai;
6. Pivot từ một workload sang workload khác;
7. Vô hiệu hóa rotation, làm lộ secret mới hoặc giữ credential cũ còn hiệu lực.

### Câu hỏi threat model

- Credential có thể bị đọc bởi những principal nào?
- Nó có scope, audience và network boundary nào?
- Attacker có thể dùng nó từ môi trường khác không?
- Credential có thể bị copy hoặc export không?
- Có thể xác định lần dùng cuối và service owner không?
- Có cách thu hồi ngay hay phải đợi expiry?
- Rotation có thể làm service ngừng hoạt động hoặc rollback không?

## 4. Inventory: biết credential nào đang tồn tại

Không thể xoay vòng an toàn nếu không biết credential nào được dùng ở đâu. Bước đầu là lập inventory có thể truy vấn và cập nhật.

### Trường thông tin nên có

| Trường | Nội dung |
| --- | --- |
| credential_id | ID tham chiếu, không phải secret value |
| credential_type | API key, client secret, private key, certificate, token |
| subject/workload | Service hoặc workload sở hữu |
| owner | Nhóm chịu trách nhiệm vận hành |
| consumer | Các service/client đang sử dụng |
| purpose | API, database, signing, mTLS, artifact access |
| environment | dev, test, staging, production |
| scope/audience | Quyền và resource được phép truy cập |
| issued_at / expires_at | Thời điểm cấp và hết hạn |
| last_used_at | Lần sử dụng gần nhất nếu hệ thống hỗ trợ |
| storage_location | Secret manager/KMS/HSM hoặc hệ thống cấp |
| rotation_policy | Chu kỳ, trigger và approval |
| revocation_method | Cách vô hiệu hóa |
| status | active, staged, retiring, revoked, expired |

Không đưa secret plaintext vào inventory. Chỉ lưu reference tới secret manager hoặc certificate registry.

### Tìm credential không được quản lý

Có thể dùng secret scanning trong repository, CI, image và artifact; inventory từ cloud IAM, certificate authority, API gateway và secret manager; đối chiếu với service registry và network telemetry. Phát hiện secret trong code cần tạo incident/remediation để thu hồi, không chỉ xóa chuỗi trong commit mới vì Git history hoặc fork có thể vẫn chứa bản cũ.

### Owner phải rõ ràng

Mỗi credential cần một owner là team hoặc service role có trách nhiệm, không chỉ là tên cá nhân. Khi team đổi tên, vendor kết thúc hoặc workload decommission, inventory cần được cập nhật và credential phải được đánh giá để thu hồi.

## 5. Phân loại và đặt rotation policy

Không phải mọi credential cần cùng một chu kỳ. Policy phụ thuộc vào mức nhạy cảm, thời hạn, khả năng thu hồi và cách sử dụng.

### Các chiều đánh giá

- **Privilege:** credential có quyền admin, ghi/xóa dữ liệu hoặc ký token không?
- **Reachability:** có thể dùng từ Internet hay chỉ từ workload/network được kiểm soát?
- **Lifetime:** credential tồn tại bao lâu và có thể gia hạn không?
- **Exposure:** có đi qua file, env, log, CI hay developer workstation không?
- **Revocability:** có thể revoke ngay và lan truyền tới mọi verifier không?
- **Blast radius:** có bao nhiêu service/resource dùng chung credential?
- **Dependency:** bao nhiêu consumer sẽ bị ảnh hưởng khi rotate?
- **Key strength/algorithm:** thuật toán và độ dài key có còn phù hợp không?

### Policy minh họa

| Credential | Hướng policy |
| --- | --- |
| Short-lived workload token | Tự động cấp mới theo TTL ngắn; không cần rotation thủ công |
| API key của vendor | Lưu secret manager, scope hẹp, rotation theo risk/vendor support |
| Database password | Rotation có overlap hoặc role switch; theo dõi pool và connection lifecycle |
| OAuth client secret | Có thể dùng hai secret đồng thời trong overlap nếu IdP hỗ trợ |
| mTLS client certificate | Cấp certificate mới, rollout trust/identity mapping, rồi revoke certificate cũ |
| JWT signing key | Publish public key mới trước, ký bằng key mới, giữ key cũ để verify token còn hạn rồi retire |
| SSH key/certificate | Thay theo owner, host scope, CA và thời hạn |

Chu kỳ cụ thể phải dựa trên threat model, chuẩn tổ chức, khả năng của issuer và mức rủi ro. Không có một con số ngày phù hợp cho tất cả credential.

## 6. Giảm static secret bằng workload identity

Rotation tốt nhất đôi khi là giảm số secret tĩnh cần quản lý.

### Static credential

Service lưu API key hoặc client secret dài hạn và gửi nó mỗi lần cần xác thực. Cách này đơn giản nhưng tạo secret có giá trị cao, phải phân phối và rotate thủ công hoặc bằng automation.

### Workload identity

Workload được xác định dựa trên môi trường thực thi và trust policy, sau đó nhận token/certificate ngắn hạn. Ví dụ:

- Cloud workload identity;
- Kubernetes service account federation;
- SPIFFE/SPIRE SVID;
- mTLS certificate ngắn hạn;
- OAuth client authentication bằng private_key_jwt hoặc mTLS.

### Lợi ích

- Không phải lưu shared secret dài hạn trong image hoặc config;
- Credential ngắn hạn giới hạn thời gian bị lạm dụng;
- Identity có thể gắn với namespace, service account, workload attributes;
- Issuer có thể cấp lại credential tự động;
- Policy có thể giới hạn audience, scope và trust domain.

### Giới hạn

Workload identity không tự an toàn nếu trust policy quá rộng, node/cluster bị compromise, metadata endpoint bị lạm dụng hoặc workload có quyền lấy identity của workload khác. Cần xác minh issuer, subject, audience, attestation context và quyền của workload.

## 7. Lưu trữ và phân phối credential

Secret cần được lưu và phân phối qua hệ thống quản lý phù hợp với độ nhạy cảm.

### Secret manager

Secret manager cung cấp lưu trữ mã hóa, access policy, audit, versioning và thường có API để workload lấy secret lúc runtime.

Nguyên tắc:

- Không hard-code secret trong source hoặc image;
- Phân quyền theo workload identity, không dùng một master credential chung;
- Giới hạn secret theo environment và service;
- Tách quyền đọc, ghi, rotate và administer;
- Audit mọi lần đọc, thay đổi version và export;
- Có backup/recovery nhưng bảo vệ backup như secret store;
- Tránh in secret ra stdout, log hoặc crash report.

### KMS và HSM

KMS/HSM có thể giữ private key hoặc key encryption key và cung cấp thao tác ký/giải mã mà không xuất private key ra ứng dụng. Điều này giảm nguy cơ key bị copy, nhưng service vẫn cần authorization đúng để gọi thao tác cryptographic.

### Environment variable có phải nơi an toàn?

Environment variable tiện cho deployment, nhưng có thể lộ qua process inspection, diagnostic dump, crash report, debug endpoint hoặc log vô tình. Nếu dùng, cần giới hạn process access, không dump env, tránh secret trong command line và ưu tiên runtime secret injection/identity-based retrieval phù hợp nền tảng.

### Secret version

Secret manager nên hỗ trợ nhiều version và trạng thái active/staged/retired. Consumer phải biết version nào đang dùng mà không cần log value. Việc cập nhật version cần có propagation và xác nhận consumer đã chuyển.

## 8. Quy trình rotation chuẩn

Một quy trình rotation an toàn thường gồm các giai đoạn sau:

1. **Discover:** xác định credential, owner, consumer, scope và dependency;
2. **Prepare:** tạo credential mới, lưu trong secret manager và thiết lập policy;
3. **Stage:** cấu hình consumer chấp nhận credential mới nhưng chưa bỏ credential cũ;
4. **Deploy:** rollout cấu hình/secret version tới từng workload;
5. **Verify:** xác nhận workload đã xác thực thành công bằng credential mới;
6. **Cut over:** chuyển toàn bộ traffic hoặc signing operation sang credential mới;
7. **Observe:** theo dõi lỗi xác thực, usage của credential cũ và các consumer còn sót;
8. **Revoke:** vô hiệu hóa credential cũ sau khi xác minh không còn consumer hợp lệ;
9. **Audit:** ghi lại kết quả, thời điểm, actor, policy và ngoại lệ;
10. **Clean up:** xóa secret cũ khỏi nơi lưu trữ/replica theo retention và incident policy.

### Nguyên tắc quan trọng

- Tạo mới trước khi thu hồi cũ nếu hệ thống hỗ trợ overlap an toàn;
- Không coi rollout hoàn tất chỉ vì secret manager đã có version mới;
- Xác minh từng consumer thực sự đã chuyển;
- Có deadline rõ cho overlap window;
- Thu hồi credential cũ sau khi consumer chuyển xong;
- Nếu credential cũ bị compromise, rút ngắn hoặc bỏ qua overlap theo incident plan;
- Không ghi secret value vào log để chứng minh rotation thành công.

### Sơ đồ vòng đời

`````````mermaid
flowchart TD
    A["Inventory và xác định owner/consumer"] --> B["Tạo credential mới"]
    B --> C["Lưu vào secret manager/KMS"]
    C --> D["Cho consumer chấp nhận credential mới"]
    D --> E["Rollout từng workload"]
    E --> F["Xác minh authentication bằng credential mới"]
    F --> G{"Tất cả consumer đã chuyển?"}
    G -- "Chưa" --> H["Điều tra consumer lỗi hoặc còn dùng bản cũ"]
    H --> E
    G -- "Rồi" --> I["Cut over hoàn toàn"]
    I --> J["Revoke credential cũ"]
    J --> K["Audit và dọn bản sao cũ"]
`````````

## 9. Dual-key và overlap window

Nhiều hệ thống cần một khoảng thời gian mà cả credential cũ và mới cùng hợp lệ để rollout không gián đoạn. Đây thường được gọi là **overlap window** hoặc dual-key rotation.

### Cách hoạt động

- Issuer/provider tạo key hoặc secret mới;
- Verifier/consumer được cấu hình chấp nhận cả bản cũ và bản mới;
- Workload chuyển sang sử dụng bản mới;
- Telemetry xác nhận không còn request hợp lệ dùng bản cũ;
- Operator thu hồi bản cũ;
- Hệ thống xác minh lại rằng chỉ credential mới được chấp nhận.

### Rủi ro khi overlap kéo dài

- Attacker có thêm thời gian sử dụng credential cũ;
- Team quên thu hồi key cũ;
- Credential cũ tiếp tục được dùng bởi consumer không được inventory;
- Hai key cùng quyền khiến blast radius không giảm;
- Rollback trở thành lý do giữ key cũ vô thời hạn.

### Đặt giới hạn

Overlap window cần có:

- Start time và expiry;
- Owner/approver;
- Danh sách consumer;
- Điều kiện cutover;
- Ngưỡng usage của credential cũ;
- Kế hoạch xử lý consumer không chuyển được;
- Điều kiện buộc revoke sớm khi có compromise.

Không đặt thời gian overlap chỉ theo sự thuận tiện. Nó phải đủ cho rollout và quan sát, nhưng ngắn hơn khoảng thời gian attacker có thể lạm dụng credential cũ.

### Không phải credential nào cũng hỗ trợ dual-key

Một số provider chỉ cho phép một API key hoặc database password active tại một thời điểm. Khi đó có thể tạo principal/role mới, triển khai consumer song song rồi chuyển traffic, hoặc dùng proxy/credential broker để kiểm soát cutover. Không giả định provider hỗ trợ hai secret chỉ vì secret manager lưu được nhiều version.

## 10. Rotation API key và vendor secret

API key thường là shared secret do provider cấp. Cần phối hợp cả hai phía: bên phát hành key và bên sử dụng key.

### Quy trình

1. Xác định key ID, account/service, scope và consumer;
2. Kiểm tra provider có hỗ trợ hai key active hay không;
3. Tạo key mới trong account/project đúng;
4. Lưu key mới vào secret manager với version riêng;
5. Rollout consumer theo từng nhóm;
6. Xác minh request mới được xác thực bằng key mới;
7. Quan sát usage của key cũ qua provider audit/metrics;
8. Thu hồi key cũ;
9. Xác minh request bằng key cũ bị từ chối;
10. Xóa bản sao không cần thiết và cập nhật inventory.

### Scope và blast radius

Không nên dùng một API key cho nhiều ứng dụng, environment hoặc service nếu provider hỗ trợ key riêng. Mỗi key nên có scope tối thiểu, quota, audience/resource giới hạn và owner rõ ràng.

Key production không được sao chép sang staging hoặc developer laptop nếu không có lý do được phê duyệt. Dùng key riêng cho từng environment giúp giới hạn tác động khi một môi trường bị compromise.

### Khi provider không hỗ trợ overlap

Có thể tạo integration/account thứ hai, chuyển consumer sang credential mới rồi xóa integration cũ. Nếu không thể tạo song song, cần maintenance window hoặc proxy credential để chuyển đổi có kiểm soát. Ghi rõ downtime/risk đã được chấp nhận và có phương án rollback.

## 11. Rotation database password

Database credential thường được sử dụng bởi connection pool, worker, migration job, reporting service và nhiều bản triển khai. Rotation cần tính đến connection đã mở và transaction đang chạy.

### Mô hình hai principal

Một cách triển khai là tạo database principal mới với quyền tương đương nhưng scope tối thiểu:

1. Tạo role/login mới;
2. Gán đúng grants và ownership cần thiết;
3. Cập nhật secret manager;
4. Rollout ứng dụng để mở connection mới bằng credential mới;
5. Xác minh connection pool đã chuyển;
6. Drain connection cũ theo kế hoạch;
7. Revoke login cũ;
8. Kiểm tra job nền, migration và công cụ vận hành không còn dùng role cũ.

### Lưu ý về connection pool

Đổi password trong secret manager không tự thay password của connection đã được xác thực. Connection đang mở có thể tiếp tục hoạt động cho tới khi bị đóng hoặc server chấm dứt. Vì vậy cần:

- Reload secret mà không log value;
- Tạo pool mới với credential mới;
- Chuyển request sang pool mới;
- Drain pool cũ và chờ transaction hoàn tất;
- Đóng connection cũ;
- Thu hồi principal/password cũ;
- Kiểm tra mọi instance và job.

### Một principal duy nhất

Nếu không thể tạo role thứ hai, database có thể chỉ cho phép một password active. Rotation lúc đó cần coordinated cutover: cập nhật password phía database, đồng thời rollout cấu hình consumer nhanh và có kiểm soát. Đây là mô hình dễ gây downtime hơn, nên cân nhắc role riêng hoặc identity-based database authentication.

### Không dùng superuser cho ứng dụng

Credential của ứng dụng nên có quyền đúng mức cần thiết. Rotation không nên giữ nguyên quyền quá rộng chỉ để tránh thay đổi grants. Tách migration role, runtime role và admin role.

## 12. Rotation OAuth client secret và machine-to-machine token

OAuth client secret thường dùng để xác thực confidential client tại token endpoint. Secret rotation cần phối hợp với identity provider và consumer.

### Khi provider hỗ trợ nhiều secret

- Tạo client secret mới và lưu secret version;
- Cấu hình client để dùng secret mới;
- Xác minh client lấy token thành công;
- Theo dõi token issuance và client authentication failure;
- Thu hồi secret cũ sau overlap window;
- Kiểm tra secret cũ không còn dùng được.

### Khi provider chỉ hỗ trợ một secret

Có thể tạo client registration mới, cấp quyền tương đương có giới hạn, rollout client sang registration mới, rồi disable registration cũ. Cần kiểm tra redirect URI, grant, audience, scope, consent và monitoring trước khi chuyển.

### Ưu tiên phương thức không cần shared secret

Nếu phù hợp, cân nhắc:

- private_key_jwt với signing key được quản lý trong KMS/HSM;
- mTLS client authentication;
- Workload identity federation;
- Short-lived access token với audience/scope tối thiểu.

Việc chuyển phương thức cũng là thay đổi trust configuration; cần rollout verifier và client theo kế hoạch, kiểm thử rollback và audit.

### Token không tự rotate cùng client secret

Thay client secret không nhất thiết thu hồi access token đã phát hành trước đó. Cần hiểu token lifetime, refresh token, revocation endpoint và policy của IdP. Nếu nghi client bị compromise, phải đánh giá token/grant/session hiện có và revoke theo khả năng của hệ thống.

## 13. Rotation certificate và mTLS identity

Certificate rotation liên quan tới CA, trust store, identity mapping và private key. Cần phân biệt certificate renewal với key rotation.

### Quy trình certificate rotation

1. Tạo key pair mới trong KMS/HSM hoặc nơi giữ key an toàn;
2. Tạo CSR với subject/SAN và identity phù hợp;
3. CA xác minh yêu cầu và cấp certificate mới;
4. Cập nhật trust/identity mapping nếu cần;
5. Triển khai certificate và private key mới tới workload;
6. Xác minh mTLS handshake, SAN, EKU, issuer, chain và policy;
7. Theo dõi traffic dùng certificate mới;
8. Thu hồi certificate cũ hoặc để hết hạn theo policy;
9. Cập nhật certificate inventory và audit.

### Trust bundle overlap

Khi thay CA hoặc intermediate CA, verifier có thể cần tin cậy cả chain cũ và mới trong giai đoạn chuyển đổi. Publish trust anchor mới trước khi workload bắt đầu dùng certificate mới. Sau khi mọi client/server chuyển xong, loại bỏ CA cũ khỏi trust bundle.

### Revocation

CRL và OCSP có thể có độ trễ hoặc phụ thuộc vào khả năng truy cập. Với workload nội bộ, có thể cần denylist/identity registry hoặc short-lived certificate để giảm thời gian credential bị compromise có hiệu lực. Phải kiểm tra hành vi thực tế của verifier khi certificate bị revoke.

### Private key không nên copy tùy tiện

Ưu tiên tạo key tại nơi sử dụng hoặc KMS/HSM và chỉ cho phép thao tác ký/handshake phù hợp. Nếu private key được export để phân phối, phải bảo vệ file, kênh truyền, backup và quyền đọc; sau rotation cần xóa bản cũ theo quy trình.

## 14. Rotation JWT signing key

Signing key dùng để ký JWT hoặc token nội bộ thường có nhiều verifier. Nếu rotate không đúng thứ tự, verifier có thể từ chối token mới hoặc chấp nhận token được ký bằng key đã bị compromise.

### Quy trình bình thường

1. Tạo key pair mới và key ID mới;
2. Publish public key mới trong JWKS hoặc trust configuration;
3. Chờ verifier refresh/cập nhật key set;
4. Chuyển issuer sang ký bằng private key mới;
5. Theo dõi token verification và key selection;
6. Giữ public key cũ trong thời gian tối thiểu bằng token lifetime còn lại cộng cache/clock skew theo policy;
7. Sau khi token cũ hết hiệu lực, retire public key cũ;
8. Xóa/disable private key cũ theo retention và recovery policy.

### Khi key cũ bị compromise

Không thể mặc định giữ public key cũ tới hết token lifetime nếu attacker đang ký token giả bằng private key đó. Cần đánh giá khẩn cấp:

- Dừng ký bằng key cũ;
- Publish trạng thái key bị thu hồi hoặc loại khỏi trust set theo khả năng verifier;
- Revoke token/session có thể bị ảnh hưởng;
- Force refresh JWKS/trust cache;
- Kiểm tra token phát hành bất thường;
- Xoay key mới trong KMS/HSM;
- Theo dõi verifier nào chưa cập nhật.

Emergency rotation có thể gây gián đoạn xác thực; cần ưu tiên bảo vệ tài nguyên và truyền thông incident theo quy trình tổ chức.

## 15. Tự động hóa rotation

Automation giúp rotation nhất quán, giảm thao tác thủ công và tránh quên credential cũ. Tuy nhiên, automation cần có state machine, quyền tối thiểu, kiểm soát lỗi và audit.

### Thành phần của rotation controller

- **Scheduler/trigger:** lịch, expiry, policy event hoặc incident;
- **Credential issuer:** tạo API key, password, certificate hoặc token mới;
- **Secret manager:** lưu version mới và kiểm soát quyền đọc;
- **Deployment controller:** cập nhật consumer/workload;
- **Health verifier:** kiểm tra authentication và business health;
- **Revocation controller:** thu hồi credential cũ;
- **Audit pipeline:** ghi actor, policy, version reference và kết quả.

### State machine gợi ý

`````````mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> ROTATION_REQUESTED: Lịch hoặc trigger
    ROTATION_REQUESTED --> NEW_CREATED: Issuer cấp mới
    NEW_CREATED --> STAGED: Lưu version và policy
    STAGED --> ROLLING_OUT: Bắt đầu rollout
    ROLLING_OUT --> VERIFYING: Consumer cập nhật
    VERIFYING --> CUTOVER: Health checks đạt
    VERIFYING --> ROLLBACK: Kiểm tra thất bại
    CUTOVER --> RETIRING_OLD: Chuyển toàn bộ consumer
    RETIRING_OLD --> REVOKED: Revoke credential cũ
    REVOKED --> ACTIVE: Rotation hoàn tất
    ROLLBACK --> ACTIVE: Khôi phục cấu hình an toàn
    ROTATION_REQUESTED --> FAILED: Issuer lỗi
    NEW_CREATED --> FAILED: Không lưu được secret
    FAILED --> ACTIVE: Retry hoặc xử lý thủ công
`````````

Các trạng thái phải có transition hợp lệ và actor rõ. Không cho scheduler tự đánh dấu REVOKED nếu chưa xác nhận consumer đã chuyển.

### Idempotent automation

Job rotation có thể retry do timeout hoặc worker restart. Mỗi rotation cần operation ID và trạng thái bền vững:

- Cùng operation ID không tạo vô hạn credential mới;
- Nếu issuer đã tạo credential nhưng response bị mất, controller có cách tìm lại theo request reference;
- Không ghi secret vào job log;
- Retry không thu hồi credential đang hoạt động;
- Revoke chỉ chạy khi điều kiện cutover đã được chứng minh;
- Có lock/lease để hai controller không rotate cùng credential đồng thời.

### Phân quyền

Rotation controller chỉ được tạo/đọc/đổi/revoke credential thuộc phạm vi được giao. Quyền đọc secret và quyền revoke nên tách biệt nếu kiến trúc cho phép. Quyền quản trị secret manager không nên được cấp cho mọi workload chỉ vì chúng cần một secret cụ thể.

## 16. Rollout, health check và rollback

Rotation có thể làm service mất kết nối nếu credential mới sai scope, sai audience, chưa được publish hoặc consumer chưa reload.

### Rollout theo giai đoạn

1. Canary một instance hoặc một consumer không critical;
2. Xác minh authentication với credential mới;
3. Kiểm tra business operation, latency và error rate;
4. Mở rộng theo batch;
5. Theo dõi toàn bộ consumer;
6. Cutover hoàn toàn;
7. Revoke credential cũ.

### Health check

Không chỉ kiểm tra secret manager đã cấp version mới. Cần xác minh:

- Consumer lấy được secret mới bằng workload identity hợp lệ;
- Credential mới được issuer/provider chấp nhận;
- Scope/audience/role đúng và không quá rộng;
- Database connection pool hoặc TLS handshake hoạt động;
- Token được cấp đúng issuer/audience;
- Không có spike authentication failure;
- Không còn request hợp lệ dùng credential cũ;
- Background job, batch và failover replica đã chuyển.

### Rollback

Rollback phải được xác định trước khi bắt đầu:

- Có thể quay lại credential cũ trong overlap window không?
- Ai được phê duyệt rollback?
- Credential cũ còn an toàn hay đã bị compromise?
- Có thể rollback cấu hình mà không đưa secret cũ vào log/artifact?
- Nếu credential cũ đã revoke, có cần cấp một credential mới khác thay thế không?

Nếu rotation là phản ứng với credential bị lộ, không rollback về secret cũ. Khi đó rollback chỉ được áp dụng cho deployment/configuration, còn credential cần tiếp tục ở trạng thái revoked.

## 17. Emergency rotation khi credential bị compromise

Emergency rotation khác rotation theo lịch. Mục tiêu là cắt quyền sử dụng của attacker càng sớm càng tốt, đồng thời xác định phạm vi ảnh hưởng.

### Trigger

- Secret xuất hiện trong public repository hoặc log không kiểm soát;
- Alert từ secret scanning hoặc provider;
- Private key bị mất hoặc nghi bị export;
- Credential được dùng từ source/device bất thường;
- Nhân sự/vendor có quyền truy cập rời tổ chức;
- Secret manager hoặc CI runner bị compromise;
- Có bằng chứng attacker dùng credential để truy cập tài nguyên.

### Quy trình ứng phó

1. Xác định credential reference, owner, scope, consumer và thời điểm lộ;
2. Mở incident và phân công incident commander/owner;
3. Đánh giá liệu attacker còn sử dụng credential hoặc đã tạo persistence;
4. Tạo credential thay thế ở môi trường kiểm soát;
5. Cập nhật consumer ưu tiên theo mức ảnh hưởng;
6. Revoke credential cũ ngay khi cần, không chờ overlap thông thường nếu nguy cơ cao;
7. Thu hồi token/session/grant được tạo bằng credential bị lộ nếu có thể;
8. Kiểm tra audit của secret manager, IdP, API gateway, database và workload;
9. Tìm credential phụ, account/service principal mới hoặc quyền được cấp thêm;
10. Xác minh service hoạt động bằng credential mới;
11. Thông báo stakeholder và lưu evidence;
12. Rà soát nguyên nhân gốc và bổ sung kiểm soát để tránh tái diễn.

### Giảm downtime khi phải revoke ngay

Có thể dùng credential dự phòng đã được chuẩn bị và bảo vệ riêng, failover principal, workload identity hoặc service broker. Không để một credential dự phòng dùng chung vô thời hạn; nó cũng cần owner, scope, expiry, audit và rotation policy.

## 18. Revocation và xác minh credential cũ không còn hiệu lực

Rotation chỉ hoàn tất khi credential cũ không còn được chấp nhận ở mọi verifier liên quan.

### Cần xác minh

- Provider/API gateway từ chối API key cũ;
- Database từ chối principal/password cũ;
- Token endpoint từ chối client secret cũ;
- mTLS verifier không còn tin certificate/key cũ theo policy;
- JWT verifier đã retire public key cũ đúng thời điểm hoặc đã block key bị compromise;
- SSH CA/host không còn chấp nhận key/certificate cũ;
- Workload identity trust policy không còn cấp token cho subject đã decommission;
- Refresh token/session được revoke hoặc hết hạn theo yêu cầu.

### Revocation propagation

Trong hệ thống phân tán, revoke có thể mất thời gian do cache, replica, gateway hoặc verifier offline. Inventory cần ghi:

- Thời điểm revoke tại issuer;
- Thời điểm mỗi verifier nhận thay đổi;
- Cache TTL và refresh behavior;
- Last-seen usage của credential cũ;
- Kết quả kiểm thử từ chối credential cũ.

Không coi trạng thái revoked trong secret manager là bằng chứng tất cả resource server đã từ chối credential. Cần đo propagation latency và xác minh tại nơi ra quyết định.

## 19. Audit, monitoring và detection

Rotation cần audit để trả lời ai đã yêu cầu, ai phê duyệt, credential nào được thay, consumer nào đã chuyển và credential cũ bị revoke lúc nào.

### Event gợi ý

| Event | Trường gợi ý |
| --- | --- |
| service.credential.inventory.updated | Credential reference, owner, consumer, source |
| service.credential.rotation.requested | Operation ID, trigger, policy version, actor |
| service.credential.created | New reference, type, issuer, expiry |
| service.credential.staged | Secret version/reference, target consumer |
| service.credential.rollout.started/completed | Workload batch, deployment version, result |
| service.credential.validation.failed | Consumer, reason code, provider |
| service.credential.cutover.completed | New credential reference, consumer coverage |
| service.credential.revoked | Old reference, actor, issuer confirmation |
| service.credential.rollback | Operation ID, reason, approver |
| service.credential.emergency_rotation | Incident ID, scope, timeline |
| service.credential.read | Workload principal, secret reference, result |

Không ghi secret value, private key, full token hoặc password vào event. Dùng credential reference, key ID, certificate serial, version ID và reason code.

### Chỉ số vận hành

- Credential có owner và expiry rõ ràng;
- Credential quá hạn hoặc không có rotation policy;
- Rotation success/failure theo loại credential;
- Rotation duration và số consumer đã chuyển;
- Overlap window thực tế so với policy;
- Credential cũ còn usage sau cutover;
- Revocation propagation latency;
- Số secret read bất thường hoặc từ principal không mong đợi;
- Số emergency rotation và nguyên nhân;
- Authentication failure sau mỗi rollout;
- Credential không dùng nhưng vẫn active;
- Rotation job retry, lock contention và orphaned credential.

### Detection

Alert khi:

- Credential được đọc bởi workload ngoài inventory;
- Secret được export hoặc truy cập từ environment lạ;
- Credential cũ tiếp tục được dùng sau cutover;
- Một principal tạo nhiều credential bất thường;
- Rotation bị disable hoặc overlap window bị gia hạn;
- Private key operation tăng đột biến;
- Certificate sắp hết hạn nhưng owner không phản hồi;
- Service tiếp tục dùng credential của workload đã decommission.

## 20. Tình huống thiết kế: rotate credential của payment service

Một payment service dùng database password và OAuth client secret tĩnh. Nhiều replica chạy trên hai cluster; connection pool giữ kết nối lâu. Secret được lưu trong secret manager nhưng deployment chỉ đọc secret lúc khởi động.

### Thiết kế ban đầu có vấn đề

1. Operator ghi đè secret hiện tại trước khi rollout replica;
2. Replica cũ vẫn giữ connection pool và client secret cũ;
3. Provider chỉ cho phép một client secret nên replica cũ bắt đầu lỗi token;
4. Job batch chạy ở cluster phụ chưa được inventory;
5. Không có metric về lần dùng cuối của secret cũ;
6. Operator rollback deployment nhưng secret cũ đã bị revoke;
7. Log debug in response từ token endpoint chứa thông tin nhạy cảm.

### Thiết kế lại

1. Inventory mọi replica, batch job, cluster và consumer; gắn owner cho từng credential.
2. Kiểm tra provider hỗ trợ hai client secret hay cần client registration mới.
3. Tạo client secret mới, lưu version riêng; không ghi value vào log.
4. Rollout client mới theo batch và xác minh token issuance/audience/scope.
5. Với database, tạo role mới có grants tối thiểu, cập nhật secret và mở pool mới.
6. Drain pool cũ sau khi transaction đang chạy hoàn tất.
7. Xác minh cả cluster phụ và batch job đã chuyển.
8. Theo dõi usage của secret/role cũ và lỗi authentication.
9. Revoke credential cũ sau khi đủ điều kiện cutover.
10. Gửi request thử bằng credential cũ để xác minh provider/database từ chối.
11. Ghi audit, cập nhật inventory và xóa bản sao secret cũ theo policy.

### Kết quả mong đợi

- Không có replica hoặc batch job bị bỏ sót;
- Consumer chuyển sang credential mới trước khi credential cũ bị revoke;
- Connection pool cũ được drain có kiểm soát;
- Credential cũ thực sự bị từ chối;
- Không có secret plaintext trong log;
- Có thể chứng minh rotation bằng event, reference và health check.

## 21. Bộ kiểm thử chấp nhận

| Trường hợp | Cách thử | Kết quả kỳ vọng |
| --- | --- | --- |
| Inventory đầy đủ | Đối chiếu credential với workload/provider | Có owner, consumer, purpose, scope và expiry |
| Credential không owner | Tạo entry không có owner | Bị cảnh báo và yêu cầu xử lý |
| Secret scanning | Đưa test secret vào repository mẫu | Phát hiện; quy trình thu hồi được kích hoạt |
| Secret manager access | Workload A yêu cầu secret của workload B | Bị từ chối |
| Environment separation | Staging thử đọc production secret | Bị từ chối |
| Rotation tạo mới | Khởi tạo rotation operation | Credential mới được tạo đúng issuer/type |
| Dual-key overlap | Consumer dùng credential mới trong overlap | Cả hai được chấp nhận theo policy |
| Consumer rollout | Rollout một batch | Health check xác nhận credential mới |
| Consumer chưa chuyển | Giữ một batch dùng key cũ | Cutover không được đánh dấu hoàn tất |
| Overlap expiry | Để quá thời hạn overlap | Có cảnh báo/escalation, không tự gia hạn vô hạn |
| Old credential revoke | Revoke sau cutover | Provider/verifier từ chối key cũ |
| Old credential reuse | Gửi request bằng key cũ sau revoke | Authentication thất bại |
| API key scope | Dùng key mới gọi resource ngoài scope | Bị từ chối |
| Database pool | Chuyển sang role mới | Pool mới hoạt động, pool cũ drain |
| Background job | Chạy job ở cluster phụ sau rotation | Dùng credential mới |
| OAuth client | Lấy token bằng secret mới | Token đúng audience/scope |
| Old OAuth secret | Lấy token bằng secret đã revoke | Token endpoint từ chối |
| Certificate rotation | mTLS bằng certificate mới | Handshake và identity mapping hợp lệ |
| Old certificate | Dùng certificate cũ sau revoke/retire | Verifier từ chối theo policy |
| JWT signing rotation | Issuer ký bằng key mới | Verifier lấy được public key mới |
| JWT old key | Token cũ còn hạn trong planned rotation | Verify theo overlap policy; key bị compromise thì block khẩn cấp |
| KMS/HSM non-exportability | Thử export private key | Bị từ chối theo key policy |
| Automation retry | Retry cùng operation ID | Không tạo credential ngoài dự kiến |
| Concurrent rotation | Hai controller rotate cùng credential | Chỉ một operation sở hữu lease/lock |
| Issuer timeout | Credential tạo thành công nhưng response bị mất | Controller reconcile được trạng thái, không tạo trùng vô hạn |
| Rollout failure | Health check thất bại | Dừng rollout và thực hiện rollback an toàn |
| Emergency rotation | Đánh dấu credential compromised | Revoke theo incident policy, không chờ overlap bình thường |
| Revocation propagation | Kiểm tra nhiều verifier/node | Có metric và đáp ứng SLA/policy |
| Audit redaction | Kiểm tra log, trace, event | Không có secret value/private key/token thô |
| Decommission | Xóa workload khỏi registry | Credential liên quan được revoke và inventory đóng |

Kiểm thử cần bao gồm issuer, secret manager, deployment controller, mọi consumer, verifier và nơi thực thi quyền. Unit test cho rotation function không chứng minh consumer production đã chuyển hoặc credential cũ đã bị thu hồi.

## 22. Checklist triển khai Service credential rotation

- **Inventory:** Có danh sách credential, owner, consumer, purpose, scope, environment và expiry?
- **Classification:** Rotation policy dựa trên privilege, exposure, lifetime, blast radius và revocability?
- **Secret storage:** Secret nằm trong secret manager/KMS/HSM phù hợp, không hard-code trong source/image?
- **Workload identity:** Có thể thay secret tĩnh bằng identity/token/certificate ngắn hạn?
- **Least privilege:** Mỗi workload chỉ đọc credential của chính nó và có scope tối thiểu?
- **Preparation:** Credential mới được tạo và kiểm tra trước khi cutover?
- **Overlap:** Dual-key có expiry, owner, consumer coverage và điều kiện revoke rõ?
- **Rollout:** Tất cả replica, batch job, failover và environment liên quan được cập nhật?
- **Health checks:** Xác minh authentication, scope/audience và business health?
- **Rollback:** Có phương án phù hợp; không rollback về credential đã compromise?
- **Revocation:** Credential cũ bị từ chối tại mọi verifier và propagation được đo?
- **Database:** Connection pool cũ được drain và role mới có grants tối thiểu?
- **Certificate:** Key pair, SAN, trust bundle, expiry và revocation được kiểm soát?
- **Signing key:** Public key được publish trước; verifier cache và token lifetime được tính đến?
- **Automation:** State machine, idempotency, lock/lease, retry và audit đầy đủ?
- **Emergency:** Có quy trình rotate ngay khi lộ secret và tìm persistence?
- **Monitoring:** Có alert cho secret read bất thường, old-key usage và rotation failure?
- **Audit/privacy:** Không ghi secret plaintext; event có reference, actor, policy và timestamp?
- **Decommission:** Credential của workload đã ngừng được thu hồi?
- **Testing:** Đã thử consumer bỏ sót, issuer timeout, race, rollback, old credential và verifier cache?

### Câu hỏi tự kiểm tra

1. Service credential khác credential người dùng ở chủ thể và vòng đời thế nào?
2. Vì sao rotation không giải quyết được compromise nếu attacker còn quyền đọc secret manager?
3. Inventory cần những trường nào để không bỏ sót consumer?
4. Overlap window giúp giảm downtime nhưng tạo thêm rủi ro gì?
5. Vì sao database password rotation phải tính đến connection pool?
6. Certificate renewal khác private key rotation ra sao?
7. Tại sao JWT signing key cần publish public key mới trước khi issuer ký bằng key mới?
8. Khi nào emergency rotation cần bỏ qua overlap thông thường?
9. Vì sao trạng thái revoked trong secret manager chưa chứng minh mọi verifier đã từ chối credential?
10. Automation cần idempotency và lock/lease để tránh lỗi nào?

## Kết luận

**Xoay vòng service credential là một quy trình thay đổi trust có kiểm soát: tạo credential mới, triển khai tới mọi consumer, xác minh, chuyển đổi rồi thu hồi credential cũ.** Muốn làm việc này an toàn cần inventory chính xác, owner rõ, scope tối thiểu, secret manager/KMS/HSM và policy phù hợp với từng loại API key, database password, client secret, certificate hoặc signing key. Overlap window giúp rollout không gián đoạn nhưng phải có expiry và điều kiện kết thúc. Automation cần state machine, idempotency, health check, rollback và audit; emergency rotation phải ưu tiên cắt quyền của attacker và thu hồi token/session liên quan. Chỉ khi credential cũ bị từ chối tại mọi verifier, mọi consumer đã chuyển và dấu vết được kiểm tra, rotation mới thực sự hoàn tất.
