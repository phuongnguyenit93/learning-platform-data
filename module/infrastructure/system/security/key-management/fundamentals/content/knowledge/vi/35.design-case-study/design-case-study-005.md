# Thiết kế certificate lifecycle

Case study này thiết kế vòng đời chứng thư số cho một nền tảng gồm API gateway, các dịch vụ backend, workload chạy trên Kubernetes, hệ thống quản trị nội bộ và các client tích hợp qua mutual TLS. Mục tiêu là xây dựng quy trình quản lý chứng thư nhất quán từ khi yêu cầu, xác minh danh tính, tạo khóa, cấp phát, phân phối, kích hoạt, gia hạn, xoay vòng, thu hồi đến khi ngừng sử dụng.

Chứng thư số liên kết một danh tính với public key thông qua chữ ký của Certificate Authority (CA). Private key tương ứng chứng minh quyền sở hữu khóa và phải được bảo vệ trong suốt vòng đời. Vì vậy, thiết kế certificate lifecycle là một phần của quản lý khóa mật mã: cần xác định nơi tạo và lưu private key, ai được sử dụng khóa, cách thay thế khóa, cách kiểm tra trạng thái chứng thư và cách xử lý khi khóa hoặc chứng thư bị compromise.

## 1. Mục tiêu của case study

Sau khi hoàn thành case study, bạn có thể:

- Phân tích yêu cầu và threat model của một hệ thống dùng chứng thư số.
- Thiết kế PKI hierarchy, trust boundary và certificate profile.
- Xây dựng inventory và ownership cho chứng thư, khóa và endpoint.
- Thiết kế quy trình enrollment, issuance, deployment, renewal, rotation, revocation và decommission.
- Chọn phương thức enrollment như ACME, EST hoặc quy trình PKI nội bộ.
- Kết hợp CA với KMS/HSM, secret manager, workload identity và automation.
- Xây dựng kiểm soát quyền, audit, monitoring và xử lý sự cố.
- Đề xuất test strategy và tiêu chí nghiệm thu cho toàn bộ vòng đời.

## 2. Bối cảnh doanh nghiệp

Một doanh nghiệp cung cấp nền tảng thương mại điện tử có các thành phần:

- Public API gateway nhận kết nối HTTPS từ trình duyệt và ứng dụng di động.
- Các backend như Order, Payment, Inventory và Customer Profile.
- Workload chạy trên nhiều Kubernetes cluster ở hai vùng triển khai.
- Service mesh dùng mTLS để xác thực service-to-service.
- Nhân viên vận hành truy cập portal quản trị nội bộ.
- Một số đối tác gọi API B2B bằng client certificate.
- Pipeline CI/CD triển khai service, ingress và certificate configuration.

Hiện trạng có nhiều vấn đề: một số chứng thư được cấp thủ công, owner không rõ, ngày hết hạn được theo dõi bằng bảng tính, private key được lưu trong secret khác nhau giữa các cluster, một số service dùng chung certificate và chưa có quy trình thu hồi thống nhất. Khi certificate sắp hết hạn, đội vận hành phải phối hợp nhiều nhóm để tìm endpoint và triển khai thủ công.

Doanh nghiệp muốn chuẩn hóa certificate lifecycle để giảm nguy cơ hết hạn, hạn chế private key bị sao chép, truy vết được mọi lần cấp phát và thay đổi, đồng thời có thể xử lý nhanh khi certificate hoặc private key bị compromise.

## 3. Phạm vi và giả định thiết kế

Case study tập trung vào chứng thư X.509 dùng cho TLS server authentication, TLS client authentication và một số danh tính workload nội bộ. Các chứng thư ký code hoặc ký tài liệu có thể dùng chung nền tảng PKI nhưng cần certificate profile và quy trình phê duyệt riêng.

Các giả định:

- Public endpoint dùng CA công khai được client phổ biến tin cậy.
- Workload nội bộ và mTLS dùng private PKI do doanh nghiệp quản lý.
- Root CA được giữ offline hoặc trong ranh giới kiểm soát cao.
- Issuing CA được bảo vệ bằng HSM hoặc dịch vụ CA có key protection tương đương.
- Workload có thể được xác thực bằng workload identity để enrollment tự động.
- Private key được tạo tại nơi sử dụng hoặc trong HSM/KMS; không gửi private key đến CA.
- Chứng thư có thời hạn hữu hạn và renewal được tự động hóa.
- Mọi certificate phải có owner, purpose, environment và endpoint sử dụng.

Thiết kế cần xác nhận các giả định này với yêu cầu thực tế trước khi triển khai. Nếu nền tảng không hỗ trợ một cơ chế như workload identity, cần có phương án thay thế và đánh giá rủi ro riêng.

## 4. Yêu cầu nghiệp vụ và bảo mật

### 4.1. Yêu cầu chức năng

Hệ thống cần:

1. Đăng ký và quản lý danh tính của service, workload, endpoint và đối tác.
2. Cấp chứng thư theo profile và danh tính đã được xác minh.
3. Phân phối certificate chain và tham chiếu private key đến đúng consumer.
4. Theo dõi ngày bắt đầu, ngày hết hạn, trạng thái và nơi sử dụng.
5. Tự động renewal trước khi chứng thư hết hạn.
6. Hỗ trợ xoay vòng private key khi policy hoặc rủi ro yêu cầu.
7. Thu hồi chứng thư khi private key bị lộ, danh tính không còn hợp lệ hoặc dịch vụ ngừng hoạt động.
8. Kiểm tra certificate status và trust chain theo chính sách client.
9. Lưu audit trail cho enrollment, issuance, deployment, renewal, revocation và thay đổi policy.
10. Cung cấp dashboard và cảnh báo cho owner, vận hành và security.

### 4.2. Yêu cầu bảo mật

- Chỉ CA được ủy quyền mới có thể phát hành chứng thư trong namespace của mình.
- CSR phải được liên kết với danh tính đã xác thực và SAN được phép.
- Private key không xuất hiện trong request gửi CA, log, source code hoặc container image.
- Workload chỉ được đọc hoặc sử dụng private key của chính nó.
- Quyền quản trị CA, quyền phê duyệt và quyền vận hành workload được tách biệt.
- Certificate profile giới hạn key usage, EKU, thuật toán và thời hạn.
- Certificate bị thu hồi phải được xử lý theo chính sách revocation của hệ thống.
- Root CA và issuing CA có quy trình bảo vệ, backup và recovery riêng.
- Có khả năng phát hiện certificate không có owner hoặc endpoint trình certificate ngoài inventory.

### 4.3. Yêu cầu vận hành

Hệ thống phải có khả năng mở rộng đến nhiều cluster và endpoint, chịu được lỗi tạm thời của CA hoặc DNS provider, hỗ trợ triển khai rolling, có cảnh báo trước expiry và cho phép khôi phục khi renewal hoặc deployment thất bại.

## 5. Phân loại certificate và danh tính

Không nên dùng một certificate profile chung cho mọi loại consumer.

| Loại certificate | Subject/SAN điển hình | EKU | Owner |
|---|---|---|---|
| Public TLS server | DNS name của API hoặc website | serverAuth | API/platform team |
| Internal service identity | DNS/SPIFFE URI hoặc danh tính workload theo PKI profile | serverAuth và/hoặc clientAuth theo thiết kế | Service owner |
| mTLS client | Danh tính service hoặc đối tác | clientAuth | Client/application owner |
| Admin endpoint | Tên portal hoặc endpoint quản trị | serverAuth | Platform/security team |
| Device/workload certificate | Device ID hoặc workload identity | Theo profile riêng | Device/platform owner |

Certificate profile cần xác định:

- Subject và SAN được phép.
- CA hoặc issuing CA được phép phát hành.
- Public key algorithm, key size hoặc curve.
- Key Usage và Extended Key Usage.
- Thời hạn hiệu lực tối đa.
- Chính sách private key: nơi tạo, exportability, backup và rotation.
- Cơ chế enrollment và challenge.
- Quyền renewal và thu hồi.
- Quy tắc đặt tên, owner và metadata.

Không dựa vào Common Name để thay thế SAN trong các triển khai TLS hiện đại. Client cần kiểm tra hostname hoặc danh tính theo SAN và chính sách xác minh phù hợp.

## 6. Thiết kế PKI hierarchy

Một kiến trúc tham khảo gồm:

1. **Offline Root CA:** trust anchor của private PKI; chỉ kích hoạt trong quy trình đặc biệt.
2. **Policy hoặc Intermediate CA:** phân tách miền phát hành nếu cần, ví dụ production và non-production.
3. **Issuing CA:** cấp leaf certificate cho service, workload hoặc client theo profile.
4. **Registration Authority (RA):** xác minh danh tính, owner và quyền yêu cầu trước khi CA phát hành.
5. **Certificate repository:** lưu certificate, chain, metadata và trạng thái.
6. **Revocation service:** cung cấp CRL hoặc OCSP theo mô hình hỗ trợ.
7. **Enrollment agents:** ACME client, EST client hoặc agent tích hợp với nền tảng workload.

~~~mermaid
flowchart TD
    A[Offline Root CA] --> B[Intermediate CA]
    B --> C[Production Issuing CA]
    B --> D[Non-production Issuing CA]
    E[Workload identity / RA] --> C
    E --> D
    C --> F[Certificate repository]
    D --> F
    C --> G[CRL / OCSP]
    D --> G
    F --> H[Deployment controller]
    H --> I[Gateway, services, clients]
    I --> J[Monitoring and audit]
    C --> J
    D --> J
~~~

Root CA không nên được dùng để cấp leaf certificate hằng ngày. Tách issuing CA theo môi trường hoặc miền tin cậy giúp giới hạn tác động khi một issuing CA bị compromise. Cần cân bằng số lượng CA với độ phức tạp vận hành và khả năng quản lý trust store.

Public TLS certificate có thể được cấp bởi public CA và không nhất thiết đi qua private PKI hierarchy. Inventory vẫn cần quản lý thống nhất cả public và private certificate.

## 7. Trust boundary và luồng tin cậy

Thiết kế phải xác định ai tin cậy CA nào và vì lý do gì:

- Browser và mobile client tin cậy public root CA trong trust store của nền tảng.
- Internal workload chỉ tin cậy private root/intermediate được phân phối qua kênh quản lý cấu hình.
- B2B partner có thể cần trust private CA hoặc public CA tùy hợp đồng.
- CA chỉ phát hành cho danh tính đã được RA hoặc enrollment policy xác minh.
- Deployment controller chỉ phân phối artifact đến workload có owner và identity phù hợp.

Không đưa private root CA vào trust store của mọi thiết bị chỉ để giải quyết một kết nối nội bộ. Cần giới hạn trust anchor theo domain, môi trường và consumer. Khi thay CA hoặc intermediate, phải có kế hoạch phân phối trust chain và thời gian overlap.

## 8. Certificate inventory và ownership

Inventory là nền tảng của lifecycle. Nếu không biết chứng thư nào đang tồn tại và được dùng ở đâu, renewal và revocation không thể hoàn tất đáng tin cậy.

Mỗi record nên có:

| Trường | Mục đích |
|---|---|
| Certificate ID | Định danh record trong inventory |
| Serial number | Nhận diện certificate do issuer cấp |
| Fingerprint | Đối chiếu certificate cụ thể |
| Subject và SAN | Danh tính được chứng thư bảo vệ |
| Issuer và chain | CA phát hành và trust path |
| Public key algorithm | RSA, EC hoặc thuật toán được policy cho phép |
| Key Usage/EKU | Mục đích sử dụng |
| Not Before/Not After | Thời hạn hiệu lực |
| Private key reference | Tham chiếu đến KMS/HSM/secret store, không lưu key material |
| Owner/service/environment | Trách nhiệm và phạm vi |
| Deployment targets | Endpoint, cluster, node hoặc client sử dụng |
| Renewal method | ACME, EST, CA API hoặc enrollment agent |
| Revocation status | Good, revoked, unknown hoặc trạng thái nội bộ tương ứng |
| Lifecycle state | Pending, active, renewing, retiring, revoked, expired |

Inventory nên được đồng bộ với CA, Kubernetes secret metadata, load balancer, ingress, service mesh và endpoint scan. Cần phát hiện certificate được triển khai ngoài inventory và record không còn endpoint sử dụng.

Private key reference chỉ là định danh hoặc đường dẫn đến nơi quản lý khóa. Không lưu private key hoặc credential trong inventory.

## 9. Thiết kế enrollment và issuance

Enrollment là quá trình một principal yêu cầu chứng thư. Issuance là bước CA phát hành sau khi xác minh yêu cầu.

Luồng đề xuất:

1. Workload được tạo trong hệ thống deployment và nhận workload identity.
2. Owner đăng ký service, environment, SAN và certificate profile.
3. RA kiểm tra principal, owner, namespace, DNS ownership và quyền yêu cầu.
4. Workload hoặc HSM tạo key pair tại ranh giới bảo vệ.
5. CSR được tạo và ký bằng private key tương ứng.
6. Enrollment agent gửi CSR cùng identity proof đến CA.
7. CA kiểm tra profile, SAN, algorithm, key usage và policy.
8. CA phát hành leaf certificate và trả certificate chain.
9. Agent kiểm tra certificate có public key khớp với private key đã tạo.
10. Certificate được ghi vào inventory và chuyển đến deployment workflow.

Private key không được gửi cho CA. CSR chỉ chứa public key và các thuộc tính yêu cầu. CA không nên tin SAN do requester tự khai báo nếu danh tính chưa được phép yêu cầu SAN đó.

## 10. Chọn giao thức enrollment

Phương thức enrollment tùy loại consumer và khả năng của CA:

| Phương thức | Trường hợp phù hợp | Điểm cần kiểm soát |
|---|---|---|
| ACME | Public TLS hoặc workload có thể chứng minh quyền kiểm soát identifier | Account key, challenge, DNS/API credential, rate limit |
| EST | Thiết bị hoặc workload doanh nghiệp cần enrollment qua TLS | Bootstrap identity, CA trust và client authentication |
| SCEP | Một số thiết bị mạng hoặc hệ thống legacy | Challenge password, profile và giới hạn khả năng giao thức |
| CA API nội bộ | Hệ thống tích hợp sâu với IAM/workload identity | Authentication, authorization, schema và audit |
| Manual CSR approval | Trường hợp đặc biệt hoặc thiết bị không tự động hóa | Phê duyệt, xác minh CSR và quy trình vận hành |

Không chọn giao thức chỉ vì client có hỗ trợ. Cần đánh giá khả năng xác minh danh tính, bảo vệ credential, giới hạn SAN, quản lý retry và thu hồi. Đối với ACME DNS-01, credential DNS phải bị giới hạn theo zone và quyền record cần thiết.

## 11. Tạo và bảo vệ private key

Private key cần được tạo gần nơi sử dụng hoặc trong thiết bị bảo vệ khóa. Phương án tham khảo:

- Public web endpoint: key pair tạo trên host hoặc secret/certificate controller được bảo vệ.
- Workload quan trọng: key pair tạo trong HSM/KMS nếu tích hợp hỗ trợ TLS signing hoặc key operation.
- Kubernetes workload: dùng CSI driver hoặc certificate agent lấy private key từ provider và mount vào pod theo policy.
- B2B client: private key tạo trong client keystore, HSM hoặc thiết bị của đối tác.

Các yêu cầu:

1. Dùng CSPRNG hoặc key generation function của KMS/HSM.
2. Chọn RSA/EC theo policy và khả năng tương thích.
3. Giới hạn exportability; ưu tiên non-exportable key khi nền tảng hỗ trợ.
4. Không commit key vào Git, không đóng gói vào container image và không gửi qua ticket.
5. Phân quyền đọc key cho đúng process hoặc workload.
6. Bảo vệ backup và recovery theo chính sách riêng.
7. Ghi metadata key ID, algorithm, purpose, owner và version.

Certificate có thể công khai, nhưng private key phải luôn được xem là secret có mức nhạy cảm cao.

## 12. Kiểm tra certificate trước khi kích hoạt

Certificate mới phải được xác minh trước khi triển khai:

- Issuer nằm trong danh sách CA được phê duyệt.
- Chain có thể xây dựng đến trust anchor đúng.
- SAN khớp chính xác danh tính endpoint.
- Not Before/Not After phù hợp và đồng hồ hệ thống đồng bộ.
- Key Usage và EKU đúng certificate profile.
- Algorithm và key size/curve đáp ứng policy.
- Public key trong certificate khớp key pair đang giữ.
- Basic Constraints và extension liên quan đúng vai trò leaf certificate.
- Serial number và fingerprint được ghi vào inventory.
- Trạng thái revocation và policy kiểm tra phù hợp với loại certificate.

Nếu một kiểm tra bắt buộc thất bại, không thay certificate đang hoạt động. Giữ artifact mới ở trạng thái rejected hoặc quarantined, ghi lý do và thông báo owner.

## 13. Phân phối và triển khai

Sau validation, certificate chain và private key reference được phân phối đến endpoint theo cách an toàn.

Một quy trình triển khai:

1. Tạo phiên bản secret hoặc certificate bundle mới.
2. Kiểm tra owner, file permission, format và key/certificate match.
3. Cập nhật tham chiếu của ingress, gateway, service mesh hoặc server.
4. Dùng rolling deployment hoặc canary cho hệ thống nhiều replica.
5. Reload graceful hoặc restart theo cơ chế của consumer.
6. Kiểm tra certificate fingerprint thực tế đang được trình ra.
7. Chạy TLS handshake và health check.
8. Xác nhận mọi endpoint/region đã chuyển sang phiên bản mới.
9. Cập nhật inventory và audit state thành active.

Không đánh dấu certificate là active chỉ vì file đã được ghi vào secret store. Cần kiểm tra từ phía client hoặc endpoint thực tế để xác nhận chứng thư đã được nạp và sử dụng.

## 14. Renewal và lịch gia hạn

Renewal tạo chứng thư mới để tiếp tục duy trì danh tính và dịch vụ. Scheduler theo dõi Not After và bắt đầu renewal trước khi chứng thư hết hạn.

Thời điểm renewal cần có khoảng đệm cho:

- CA xử lý order hoặc phê duyệt.
- DNS propagation hoặc challenge.
- Retry khi mạng hoặc provider gặp sự cố.
- Phân phối tới nhiều cluster và endpoint.
- Reload và xác minh dịch vụ.
- Xử lý ngoại lệ hoặc cần owner can thiệp.

Không dùng một ngưỡng duy nhất cho mọi certificate. Public certificate, internal service certificate và certificate thiết bị có thời hạn, khả năng enrollment và mức độ sẵn sàng khác nhau. Policy có thể dùng số ngày còn lại hoặc tỷ lệ lifetime.

Scheduler cần idempotent, tránh tạo nhiều order cho cùng certificate và có jitter để không dồn renewal vào cùng một thời điểm.

## 15. Renewal có giữ private key hay tạo key pair mới?

Renewal có thể tái sử dụng key pair hiện tại hoặc tạo key pair mới. Quyết định này cần được ghi rõ trong certificate profile.

| Lựa chọn | Lợi ích | Rủi ro/chi phí |
|---|---|---|
| Giữ key pair | Ít thay đổi, giảm yêu cầu phối hợp với consumer | Private key tồn tại lâu hơn; nếu đã lộ thì renewal không khắc phục compromise |
| Tạo key pair mới | Thực hiện key rotation đồng thời, giảm thời gian sử dụng key cũ | Cần phân phối private key mới, cập nhật pinning/trust và kiểm tra consumer |

Nếu có nghi ngờ private key bị lộ, phải tạo key pair mới. Cấp certificate mới nhưng tiếp tục dùng private key cũ không xử lý được nguyên nhân compromise.

## 16. Rotation và cutover

Rotation thay private key hoặc chuyển sang key version mới. Cutover là thời điểm endpoint bắt đầu sử dụng certificate/private key mới.

Một quy trình ít gián đoạn:

1. Tạo key pair mới.
2. Tạo CSR và xin certificate mới.
3. Validate certificate, chain và key match.
4. Phân phối bundle mới đến một nhóm canary.
5. Kiểm tra handshake, mTLS và health.
6. Mở rộng triển khai tới các endpoint còn lại.
7. Xác minh fingerprint tại tất cả target.
8. Cập nhật inventory và ghi nhận thời điểm cutover.
9. Thu hồi hoặc retire certificate cũ theo policy.

Trong giai đoạn chuyển tiếp, một số consumer có thể cần chấp nhận cả trust chain cũ và mới. Overlap phải có thời hạn và theo dõi; không để trust cũ tồn tại vô thời hạn.

## 17. Revocation và kiểm tra trạng thái

Certificate cần được thu hồi khi:

- Private key bị lộ hoặc nghi bị lộ.
- Certificate được cấp sai SAN, purpose hoặc danh tính.
- Owner hoặc workload không còn hợp lệ.
- Thiết bị hoặc client bị mất quyền kiểm soát.
- Issuing CA hoặc trust relationship bị compromise.
- Certificate không còn cần thiết và policy yêu cầu thu hồi.

Hai cơ chế thường gặp:

- **CRL:** CA công bố danh sách serial number đã bị thu hồi. Client tải và kiểm tra danh sách theo cơ chế hỗ trợ.
- **OCSP:** client hoặc responder truy vấn trạng thái của một certificate cụ thể.

Không giả định mọi client kiểm tra revocation theo cùng cách. Một số client có thể soft-fail khi OCSP không khả dụng; một số môi trường dùng stapling hoặc cache. Thiết kế phải xác định hành vi khi status là revoked, unknown hoặc responder unavailable.

Revocation không xóa private key khỏi mọi nơi và không đảm bảo mọi client lập tức ngừng tin cậy certificate. Cần kết hợp triển khai certificate mới, loại bỏ certificate cũ khỏi endpoint, cập nhật trust và xử lý cache.

## 18. Decommission và thu hồi tài nguyên

Khi service hoặc endpoint ngừng hoạt động:

1. Owner xác nhận service đã ngừng và không còn consumer phụ thuộc.
2. Ngừng renewal tự động và enrollment binding.
3. Gỡ certificate khỏi endpoint, load balancer, secret store hoặc trust configuration.
4. Thu hồi certificate nếu policy hoặc rủi ro yêu cầu.
5. Thu hồi workload identity và quyền đọc private key.
6. Xử lý private key theo retention và destruction policy.
7. Cập nhật inventory thành retired/revoked/destroyed theo trạng thái thực tế.
8. Lưu audit record và change reference.

Không xóa inventory record ngay khi service bị xóa. Record lịch sử cần được giữ trong thời hạn audit để điều tra và chứng minh certificate đã được xử lý.

## 19. KMS/HSM và CA key protection

CA private key là tài sản có tác động rất lớn: nếu issuing CA key bị lộ, attacker có thể phát hành certificate giả trong phạm vi CA đó. Root CA key còn nhạy cảm hơn vì ảnh hưởng đến toàn bộ trust hierarchy.

Thiết kế bảo vệ:

- Root CA key được giữ offline hoặc trong HSM với quy trình kích hoạt đặc biệt.
- Issuing CA key được bảo vệ trong HSM hoặc dịch vụ CA có security boundary phù hợp.
- CA signing operation được giới hạn theo role và certificate policy.
- Backup/restore CA key có dual control hoặc quorum nếu yêu cầu.
- Audit cho mọi lần ký, thay đổi CA config, backup, restore và administrator access.
- Tách quyền vận hành CA khỏi quyền quản trị host và quyền phê duyệt enrollment.

KMS có thể quản lý một số key operation hoặc secret liên quan, nhưng không phải mọi KMS đều cung cấp đầy đủ chức năng CA. Cần xác định ranh giới giữa CA software, HSM, KMS và enrollment service.

## 20. RBAC và separation of duties

Các vai trò tham khảo:

| Vai trò | Quyền chính | Giới hạn |
|---|---|---|
| PKI Administrator | Quản lý CA hierarchy, profile và cấu hình | Không tự phê duyệt mọi enrollment hoặc xuất CA key |
| Registration Authority | Xác minh owner, identity và SAN request | Không trực tiếp truy cập private key của CA |
| Certificate Operator | Theo dõi issuance, renewal và deployment | Không thay đổi root trust hoặc cấp quyền ngoài scope |
| Workload Identity | Yêu cầu và sử dụng certificate của chính workload | Không yêu cầu SAN tùy ý hoặc đọc private key của workload khác |
| Security Approver | Phê duyệt thay đổi nhạy cảm và ngoại lệ | Không tự phê duyệt yêu cầu do chính mình khởi tạo |
| Auditor | Đọc inventory, policy và audit log | Không ký, thu hồi hoặc thay đổi policy |
| Incident Responder | Giới hạn quyền, thu hồi hoặc kích hoạt quy trình khẩn cấp | Quyền tạm thời, có cảnh báo và hậu kiểm |

Áp dụng least privilege theo CA, profile, namespace, environment và operation. Thay đổi trust anchor, cấp SAN wildcard, export CA key hoặc revoke diện rộng cần quy trình phê duyệt riêng.

## 21. Monitoring và cảnh báo

Các tín hiệu cần theo dõi:

| Metric/tín hiệu | Mục đích | Điều kiện cảnh báo |
|---|---|---|
| Certificate remaining lifetime | Phát hiện sắp hết hạn | Vào renewal window nhưng chưa có order |
| Renewal success rate | Đánh giá chất lượng automation | Giảm dưới ngưỡng vận hành |
| Pending order age | Phát hiện enrollment bị treo | Vượt thời gian xử lý dự kiến |
| Deployment coverage | Xác nhận mọi target đã cập nhật | Một hoặc nhiều target còn certificate cũ |
| Endpoint fingerprint drift | Phát hiện endpoint trình sai certificate | Fingerprint khác inventory sau cutover |
| Revocation status | Theo dõi trạng thái chứng thư | Certificate bị revoke vẫn được endpoint sử dụng |
| Unknown certificate | Phát hiện certificate ngoài inventory | Endpoint trình certificate chưa đăng ký |
| CA signing activity | Theo dõi hoạt động phát hành | Tăng đột biến hoặc profile/SAN bất thường |
| Private key access | Theo dõi truy cập khóa | Principal hoặc nguồn truy cập lạ |
| CA/HSM health | Đảm bảo khả năng cấp và ký | HSM unavailable, audit gap hoặc quorum issue |

Alert phải có certificate ID, SAN, issuer, owner, environment, endpoint và thời gian còn lại. Cần gắn với runbook và người chịu trách nhiệm.

## 22. Audit trail

Audit trail cần ghi lại:

- Ai hoặc workload nào yêu cầu enrollment.
- Danh tính, SAN, profile và CA được chọn.
- CSR fingerprint và public key metadata; không ghi private key.
- Ai phê duyệt và căn cứ phê duyệt.
- CA phát hành serial number và fingerprint nào.
- Khi nào certificate được phân phối, kích hoạt và xác minh.
- Renewal, rotation, revocation và decommission do ai thực hiện.
- Key ID/version hoặc HSM reference liên quan.
- Lỗi, retry, rollback và trạng thái cuối.

Audit store cần được tách quyền với CA administration, có kiểm soát truy cập, bảo vệ tính toàn vẹn và retention phù hợp. Không ghi private key, ACME account secret, DNS token hoặc credential vào log.

## 23. Threat model và tình huống sự cố

| Mối đe dọa | Tác động | Kiểm soát |
|---|---|---|
| Private key của leaf certificate bị lộ | Giả mạo server/client trong phạm vi chứng thư | Key rotation, certificate revocation, điều tra endpoint |
| Issuing CA key bị lộ | Phát hành certificate giả | Cô lập CA, revoke/replace CA chain, cập nhật trust |
| Root CA key bị lộ | Trust hierarchy bị ảnh hưởng nghiêm trọng | Incident cấp cao, xây trust anchor mới và migration trust |
| SAN request bị giả mạo | Cấp certificate cho danh tính ngoài quyền | RA, workload identity và SAN allowlist |
| DNS challenge credential bị lộ | Chiếm quyền xác minh domain hoặc thay DNS | Thu hồi token, giới hạn zone, audit DNS |
| Renewal automation bị chiếm | Phát hành hoặc triển khai certificate trái phép | Workload identity, RBAC, approval và audit |
| Certificate hết hạn | TLS/mTLS gián đoạn | Inventory, renewal automation và alert |
| Revocation không được client kiểm tra | Certificate bị thu hồi vẫn được chấp nhận | Client policy, OCSP/CRL testing và emergency block |
| Certificate ngoài inventory | Không có owner và không được giám sát | Endpoint discovery, inventory reconciliation |

### 23.1. Kịch bản: private key của API gateway bị lộ

Một cảnh báo phát hiện private key TLS production xuất hiện trong artifact registry có quyền đọc rộng.

Phản ứng:

1. Mở incident và xác định certificate serial, SAN, fingerprint, owner và endpoint.
2. Bảo toàn bằng chứng về artifact, quyền truy cập và thời điểm phát hiện.
3. Thu hồi credential hoặc quyền truy cập registry có liên quan.
4. Tạo key pair mới trong môi trường bảo vệ, tạo CSR và xin certificate mới.
5. Validate certificate và triển khai theo canary/rolling.
6. Xác minh mọi gateway endpoint đang trình fingerprint mới.
7. Revoke certificate cũ và kiểm tra trạng thái revocation theo client policy.
8. Tìm nơi artifact bị tải xuống và đánh giá khả năng key đã bị sử dụng.
9. Cập nhật inventory, audit record và khắc phục pipeline đã làm lộ private key.

Chỉ phát hành certificate mới mà không thay private key sẽ không xử lý được sự cố.

### 23.2. Kịch bản: issuing CA có dấu hiệu compromise

Nếu issuing CA key hoặc hệ thống ký bị nghi xâm phạm, phạm vi có thể bao gồm mọi certificate do CA đó phát hành. Đội ứng phó cần cô lập issuing CA, ngừng issuance, bảo toàn audit và xác định thời điểm sớm nhất có thể bị compromise.

Sau khi đánh giá, tổ chức có thể phải tạo issuing CA mới, ký chain mới từ intermediate/root đáng tin cậy, phát hành lại leaf certificate, cập nhật trust bundle và thu hồi certificate do CA cũ phát hành. Việc chuyển đổi cần kế hoạch phối hợp client/server vì trust store có thể cache chain và trạng thái.

## 24. Kế hoạch triển khai theo giai đoạn

Không nên chuyển toàn bộ certificate cùng lúc nếu inventory và automation chưa được kiểm chứng.

| Giai đoạn | Phạm vi | Kết quả |
|---|---|---|
| 1. Discover | Thu thập certificate từ CA, endpoint, cluster, gateway và secret store | Inventory ban đầu, owner và khoảng trống |
| 2. Standardize | Định nghĩa CA hierarchy, profile, naming, owner và policy | Chuẩn phát hành và trust boundary |
| 3. Protect | Chuyển CA key và private key quan trọng vào HSM/KMS hoặc store phù hợp | Key protection và RBAC |
| 4. Automate pilot | Chọn một nhóm service ít rủi ro, tích hợp enrollment và renewal | Quy trình tự động đã kiểm chứng |
| 5. Expand | Mở rộng sang production, mTLS và partner certificate | Phủ inventory và automation |
| 6. Enforce | Áp dụng policy, revoke certificate cũ và xử lý ngoại lệ | Chuẩn vận hành thống nhất |
| 7. Optimize | Tối ưu alert, latency, quota, renewal window và recovery | Vòng đời được giám sát liên tục |

Trong pilot, cần kiểm tra cả happy path và failure path: CA unavailable, DNS challenge chậm, secret store lỗi, node offline, certificate sai SAN, reload thất bại và revocation responder không khả dụng.

## 25. Test strategy và tiêu chí nghiệm thu

### 25.1. Kiểm thử chức năng

- Enrollment tạo CSR và certificate có đúng SAN/profile.
- Certificate chain xác minh được tới trust anchor mong muốn.
- Certificate được triển khai và endpoint trình đúng fingerprint.
- Renewal diễn ra trước expiry và không tạo order trùng.
- Rotation thay private key khi policy yêu cầu.
- Revocation cập nhật trạng thái và được client xử lý theo policy.
- Decommission gỡ certificate, thu hồi identity và cập nhật inventory.

### 25.2. Kiểm thử bảo mật

- Principal không có quyền không thể yêu cầu SAN ngoài scope.
- Workload A không thể lấy private key hoặc certificate của workload B.
- CA private key không export nếu policy yêu cầu non-exportable.
- Credential DNS chỉ có quyền trên zone cần thiết.
- Certificate sai EKU, issuer, SAN hoặc key algorithm bị từ chối.
- Certificate revoked hoặc expired bị xử lý đúng theo client policy.
- Audit log không chứa private key hoặc enrollment credential.

### 25.3. Kiểm thử khả năng phục hồi

- Renewal tiếp tục được sau controller restart.
- Retry không phát hành hoặc triển khai certificate trùng lặp.
- Một node offline không làm đánh dấu toàn bộ deployment thành công.
- Rollback không quay về certificate/private key đã compromise.
- CA/HSM outage có cảnh báo và quy trình phục hồi.
- Restore CA/key backup theo dual control và xác minh audit.

### 25.4. Tiêu chí nghiệm thu

Thiết kế được xem là sẵn sàng khi:

1. Tất cả certificate production có owner, purpose, expiry và deployment target.
2. CA hierarchy và certificate profile được phê duyệt.
3. Private key được tạo/lưu theo policy và không xuất hiện trong log hoặc repository.
4. Enrollment xác minh danh tính và SAN.
5. Renewal hoàn tất trước expiry với đủ thời gian dự phòng.
6. Tất cả endpoint được xác minh sau deployment.
7. Revocation behavior được kiểm thử trên các client thực tế.
8. Rotation và incident runbook đã được diễn tập.
9. Audit trail có thể truy vấn theo certificate ID, serial, fingerprint, principal và thời gian.
10. Không còn certificate production không có owner hoặc endpoint không được quản lý, trừ ngoại lệ có phê duyệt và thời hạn.

## 26. Ví dụ policy certificate profile

Một profile minh họa cho internal service TLS:

~~~yaml
profile:
  name: internal-service-tls
  issuer: internal-production-issuing-ca
  identifiers:
    allowed_types:
      - dns
      - uri
    dns_scope:
      - svc.cluster.local
  key:
    algorithms:
      - ECDSA
    curves:
      - P-256
    exportable: false
    provider: approved-hsm-or-workload-key-provider
  usage:
    key_usage:
      - digitalSignature
    extended_key_usage:
      - serverAuth
      - clientAuth
  validity:
    maximum: 30d
  renewal:
    before_expiry: 10d
    rotate_key: true
  authorization:
    require_workload_identity: true
    require_owner: true
    san_from_identity: true
~~~

Đây là policy khái niệm, không phải cấu hình dùng trực tiếp cho một CA hoặc ACME client cụ thể. Cần ánh xạ sang certificate template, profile hoặc policy syntax của nền tảng được chọn. Thời hạn và thuật toán phải theo chuẩn hiện hành, khả năng tương thích và chính sách nội bộ.

## 27. Quyết định thiết kế và trade-off

| Quyết định | Phương án đề xuất | Trade-off cần chấp nhận |
|---|---|---|
| CA hierarchy | Offline root và issuing CA tách theo trust domain | Tăng vận hành nhưng giới hạn blast radius |
| Enrollment | Tự động cho workload, approval cho trường hợp đặc biệt | Cần quản lý identity và automation credential |
| Private key | Tạo tại consumer/HSM, non-exportable khi khả thi | Có thể tăng độ phức tạp tích hợp và recovery |
| Renewal | Tự động, bắt đầu sớm, có retry và alert | Cần inventory chính xác và quản lý quota CA |
| Key rotation | Tạo key pair mới theo profile hoặc risk trigger | Cần phối hợp endpoint và trust cache |
| Revocation | CRL/OCSP theo khả năng client, kết hợp emergency controls | Client behavior khác nhau, cần kiểm thử thực tế |
| Deployment | Versioned secret và rolling rollout | Cần theo dõi trạng thái từng node |
| Audit | Tập trung ở vùng riêng và bảo vệ toàn vẹn | Tăng chi phí lưu trữ và vận hành |

Không có một cấu hình duy nhất phù hợp mọi môi trường. Thiết kế cần cân bằng mức bảo vệ, khả năng tương thích, độ sẵn sàng, chi phí và năng lực vận hành của tổ chức.

## 28. Checklist thiết kế certificate lifecycle

- [ ] Đã phân loại public, internal, mTLS, device và certificate đặc biệt.
- [ ] Có PKI hierarchy, trust boundary và owner cho từng CA.
- [ ] Root CA được bảo vệ riêng; issuing CA key nằm trong ranh giới bảo vệ phù hợp.
- [ ] Mỗi certificate profile xác định SAN, EKU, Key Usage, algorithm và validity.
- [ ] Enrollment xác minh workload/user identity và quyền yêu cầu SAN.
- [ ] Private key được tạo an toàn, tách khỏi CSR và không gửi đến CA.
- [ ] Certificate được validate chain, SAN, key match và thời hạn trước deployment.
- [ ] Inventory có serial, fingerprint, issuer, owner, expiry và deployment target.
- [ ] Renewal tự động có khoảng đệm, idempotency, retry và jitter.
- [ ] Rotation xác định rõ có thay private key hay không.
- [ ] Deployment có rolling/canary và kiểm tra fingerprint ở endpoint.
- [ ] Revocation behavior được kiểm thử với client thực tế.
- [ ] Decommission thu hồi identity, certificate và quyền truy cập key.
- [ ] RBAC tách CA administration, RA, operator, workload và auditor.
- [ ] Audit và monitoring theo dõi issuance, renewal, rotation, revocation và CA activity.
- [ ] Có runbook cho leaf key compromise và CA compromise.
- [ ] Backup/restore CA key và trust migration được diễn tập.
- [ ] Có test cho lỗi CA, DNS, HSM, secret store, node offline và rollout.

## Kết luận

Thiết kế certificate lifecycle cần quản lý đồng thời danh tính, chứng thư, private key, CA, endpoint và quy trình vận hành. Một kiến trúc tốt có PKI hierarchy và trust boundary rõ ràng, certificate profile giới hạn đúng SAN và mục đích, enrollment xác minh danh tính, private key được bảo vệ trong KMS/HSM hoặc key provider phù hợp, cùng inventory có owner và endpoint đầy đủ. Renewal, rotation, revocation và decommission phải là các trạng thái được điều phối và xác minh đến tận consumer. Monitoring, audit, test và incident runbook giúp phát hiện certificate bất thường, xử lý compromise và khôi phục dịch vụ. Khi mọi bước được liên kết bằng metadata và bằng chứng, chứng thư không còn là file cấu hình được gia hạn thủ công mà trở thành tài sản có vòng đời được quản trị xuyên suốt.
