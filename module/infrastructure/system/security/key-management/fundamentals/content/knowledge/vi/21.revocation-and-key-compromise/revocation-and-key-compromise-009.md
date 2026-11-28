# Ảnh hưởng đến certificate khi khóa bị compromise hoặc bị thu hồi

Một ngày, đội vận hành phát hiện **private key của API Gateway** có thể đã bị lấy khỏi máy chủ qua một bản sao cấu hình không được bảo vệ. Certificate TLS do CA cấp cho gateway **vẫn còn hạn ba tháng**, hostname vẫn đúng, chữ ký CA vẫn hợp lệ và phép toán TLS có thể tiếp tục thành công. Vậy hệ thống đã an toàn chưa?

**Chưa.** Certificate là một **chứng nhận có chữ ký** liên kết public key với identity và những thuộc tính sử dụng nhất định. Nếu private key tương ứng đã lộ, attacker có thể giả mạo endpoint hoặc thực hiện những phép toán mà khóa đó cho phép trong một số điều kiện, **dù certificate chưa hết hạn**. Người quản trị cần **cô lập khóa bị nghi lộ, đánh giá phạm vi, thu hồi certificate, cấp keypair/certificate mới, phân phối trạng thái tin cậy mới và xác minh hành vi thực tế của các bên dựa vào certificate**.

Vấn đề đặc biệt phức tạp vì:

- **Revoke certificate không xóa private key đã bị đánh cắp**.
- **Đăng certificate mới không tự khiến client ngừng tin certificate cũ**.
- **OCSP/CRL có thể được cache**, bị gián đoạn hoặc không được một số clients kiểm tra.
- **Các TLS connections đang mở, resumed sessions hoặc token đã phát** có thể có vòng đời khác với lúc certificate được kiểm tra.
- Nếu khóa bị lộ là **private key của Intermediate CA**, phạm vi có thể lớn hơn một service: attacker có thể tạo certificate giả dưới chuỗi tin cậy bị ảnh hưởng.
- Một chữ ký số tạo trước sự cố có thể còn cần **bằng chứng thời điểm ký và trạng thái tin cậy lịch sử**, không được đánh đồng với việc chấp nhận chữ ký mới sau khi khóa bị compromise.

**Ảnh hưởng đến certificate** trong chương **Revocation và compromise** là bài toán nối **vòng đời khóa, hệ thống PKI/X.509, KMS/HSM, xác thực workload, chữ ký số, kiểm soát truy cập và kiểm toán**. Bài học thuộc mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, nơi quản lý khóa từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng đến thu hồi/hủy; mục tiêu là thiết kế quy trình **phản ứng với sự cố thật, không chỉ cập nhật một cờ status**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích quan hệ giữa **private key, public key, X.509 certificate, issuer CA, trust anchor, certificate chain** và các bên xác minh (**relying parties**).
2. Phân biệt **key compromise, certificate revocation, certificate expiration, certificate renewal, certificate reissuance, key rotation, key disable/destroy**.
3. Phân loại ảnh hưởng khi bị lộ **TLS server private key, mTLS client private key, code/document signing key, Intermediate CA key hoặc Root CA key**.
4. Mô tả quy trình **validate certificate path, identity/SAN, KeyUsage/EKU, thời hạn và revocation status**.
5. Hiểu cách **Certificate Revocation List (CRL)**, **Online Certificate Status Protocol (OCSP)**, **OCSP stapling**, cache và freshness ảnh hưởng đến thời gian thu hồi có hiệu lực.
6. Phân biệt **OCSP good / revoked / unknown** và lựa chọn **fail-open / fail-closed** theo threat model.
7. Thiết kế **incident runbook**: cô lập identity, ngăn lạm dụng KMS/HSM, phát hành keypair/certificate mới, revoke certificate cũ, cập nhật trust stores và kiểm thử.
8. Đánh giá ảnh hưởng của revocation đến **TLS/mTLS, JWT/JWS, chữ ký tài liệu lịch sử, certificate pinning, workload identity, API gateways và backup/DR**.
9. Đọc được ví dụ **Java 17** về policy đánh giá certificate và ví dụ JCA **PKIXRevocationChecker**, biết ranh giới giữa mô phỏng chính sách và kiểm tra chứng thư X.509 thật.

## 2. Certificate thực sự chứng nhận điều gì?

### 2.1. Certificate không phải private key

Một X.509 certificate thường chứa:

| Thành phần | Vai trò | Có cần bí mật? |
|---|---|---|
| **Subject/SAN** | Định danh được CA chứng nhận theo policy | Thường không |
| **Subject public key** | Public key tương ứng private key của chủ thể | Không |
| **Issuer, serial number** | Định danh CA phát hành và certificate trong phạm vi issuer | Không |
| **Validity: notBefore/notAfter** | Khoảng hiệu lực chứng thư | Không |
| **KeyUsage/EKU** | Ràng buộc loại sử dụng theo certificate profile | Không |
| **BasicConstraints, pathLen** | Phân biệt khả năng CA và độ sâu chain | Không |
| **Authority/Subject Key Identifiers** | Hỗ trợ xây/kiểm tra đường dẫn chứng thư | Không |
| **CRL Distribution Points / AIA OCSP** | Gợi ý nguồn status/issuer info cho validator | Không |
| **Signature của issuer CA** | Cho phép kiểm chứng chứng thư được CA ký | Không |
| **Private key tương ứng** | Bí mật dùng chứng minh sở hữu, Sign hoặc giải mã theo thuật toán | **Có, phải bảo vệ** |

Certificate **có thể được công bố công khai**, nhưng public key và metadata phải được xác thực theo **đường dẫn tin cậy** và **đúng danh tính đích**. Private key thường tồn tại riêng ở **service, HSM/TPM hoặc provider key handle**; nó không nằm trong certificate X.509 công khai.

### 2.2. Chuỗi tin cậy

~~~mermaid
flowchart TD
    Root["Root CA / Trust anchor trong trust store"] --> I["Intermediate CA certificate"]
    I --> L["Leaf certificate: api.example.internal"]
    L --> S["Service có private key tương ứng"]
    C["TLS Client / Relying party"] --> V["Path validation + hostname/SAN + EKU + revocation"]
    V --> Root
    V --> I
    V --> L
    S --> H["TLS handshake proof of possession"]
    H --> C
~~~

Một relying party không chỉ hỏi **certificate có chữ ký CA hợp lệ không?** Nó phải hỏi đồng thời:

1. Có **đường dẫn certificate** hợp lệ tới trust anchor mà relying party đã tin không?
2. Certificate có **đúng hostname, URI/SPIFFE identity hoặc subject được mong đợi** không?
3. Có nằm trong **khoảng thời gian hợp lệ**, sử dụng thuật toán và key size được phép không?
4. **KeyUsage, ExtendedKeyUsage (EKU), BasicConstraints, policy constraints, name constraints** có phù hợp theo profile không?
5. Certificate/CA liên quan có **bị revoke hoặc mất tin cậy** theo chính sách không?
6. Peer có thật sự **chứng minh kiểm soát private key** tương ứng trong giao thức không?
7. Sau xác thực, caller có **quyền nghiệp vụ/IAM** truy cập tài nguyên đó không?

Một certificate có SAN **api.example.internal** không được mặc nhiên tin cậy để xác thực **payments.example.internal**. Một mTLS certificate clientAuth cũng không tự trao quyền truy cập mọi tenant hoặc quyền KMS Decrypt.

### 2.3. Chứng thư hợp lệ toán học khác chứng thư đáng tin để sử dụng

Chữ ký CA trên certificate có thể vẫn verify về mặt toán học sau khi certificate bị revoke. **Revocation không thay đổi các bytes chứng thư đã ký**; nó cung cấp thêm thông tin để relying party quyết định **không tiếp tục chấp nhận certificate**.

~~~text
Signature chain mathematically valid?   Có thể CÓ
Certificate within notBefore/notAfter?  Có thể CÓ
Certificate listed as revoked?          Có thể CÓ

=> Trusted for a new TLS connection?    KHÔNG theo policy kiểm tra revocation
~~~

Đó là lý do **chỉ gọi certificate.verify(issuerPublicKey)** không phải toàn bộ PKIX validation và càng không phải một hệ thống quản lý revocation hoàn chỉnh.

## 3. Năm tình huống rất dễ bị nhầm

| Tình huống | Điều xảy ra | Tác động lên certificate | Việc cần làm |
|---|---|---|---|
| **Certificate expiration** | Vượt **notAfter** | Certificate không còn hợp lệ theo thời gian khi dùng mới | Renew/reissue theo policy; verify historical signatures riêng |
| **Certificate revocation** | CA công bố trạng thái không còn được tin trước hạn | Relying party kiểm tra CRL/OCSP/trust policy để từ chối | Revoke đúng issuer/serial, giám sát propagation |
| **Private key compromise** | Private key có khả năng rơi vào tay không được phép | Certificate gắn key đó mất cơ sở tin cậy dù chưa hết hạn | Incident response, keypair mới, revoke certificate, kiểm tra trust |
| **Certificate reissue/renewal** | CA phát hành certificate mới | Certificate cũ vẫn có thể còn hợp lệ nếu không revoke/hết hạn | Chuyển consumers, đánh giá revoke cũ, kiểm tra key reuse |
| **Key rotation** | Tạo/đưa material mới vào dùng | Thường cần CSR/certificate mới nếu public key đổi | Thay keypair/permissions, update service/trust/metadata |

Ngoài ra, **KMS DisableKey/DestroyKey** điều khiển key object hoặc khả năng dùng crypto API trong KMS, **không tự động revoke X.509 certificate** đang được relying party kiểm tra. Chiều ngược lại, revoke certificate **không tự hủy raw private key đã export** hoặc một key object non-exportable vẫn được KMS Sign nếu IAM cho phép.

### 3.1. Khi nào cần keypair mới?

Khi **private key bị lộ hoặc có căn cứ nghi ngờ lộ**, phải ưu tiên **tạo keypair mới độc lập**, không chỉ xin certificate mới cho **cùng public/private key**.

~~~text
Sai khi private key đã lộ:
    Reissue certificate mới bằng cùng public key cũ
    Service vẫn dùng private key cũ

Đúng theo incident policy:
    Generate keypair mới tại boundary được duyệt
    Tạo CSR bằng private key mới
    CA xác thực subject/SAN và issue certificate mới
    Deploy/activate keypair và certificate mới
    Revoke/distrust certificate cũ + chặn IAM/credential cũ
~~~

Reissuance bằng **cùng keypair** có thể có trong một số quy trình renewal thông thường, nhưng **không khắc phục key compromise**.

### 3.2. Certificate bị revoke khác certificate hết hạn

- **Expired:** Certificate vượt thời hạn nêu trong chính certificate. Validator có thể từ chối vì **time validation**, không cần CRL/OCSP.
- **Revoked:** CA hoặc hệ thống tin cậy xác định certificate phải ngừng được chấp nhận **trước notAfter**. Relying party phải nhận biết thông tin revocation theo policy.
- **Suspended/Hold:** Một số PKI có trạng thái treo tạm thời/CRL reason tương ứng; không phải profile hoặc validator nào cũng hỗ trợ hành vi “gỡ hold” như nhau.
- **Locally distrusted:** Một doanh nghiệp có thể loại issuer/public key/certificate khỏi trust store hoặc denylist **độc lập** với việc CA kịp phát hành CRL/OCSP.

**Có certificate mới không chứng minh certificate cũ đã bị revoke.** Trong một khoảng overlap được thiết kế có chủ đích, cả hai có thể còn được chấp nhận. Khi nghi compromise, không nên để overlap như rotation định kỳ bình thường.

## 4. Phạm vi ảnh hưởng phụ thuộc khóa nào bị compromise

### 4.1. Leaf TLS server certificate

Nếu private key của **api.example.internal** bị lộ:

- Attacker có thể sử dụng private key để **chứng minh sở hữu keypair** trong một kết nối giả mạo nếu có thể kiểm soát định tuyến/tên miền/điểm kết nối và client vẫn tin certificate.
- Certificate còn hạn có thể tiếp tục được client chấp nhận **nếu không kiểm tra/nhận biết revocation**.
- Khi dùng các phiên mã và giao thức có **forward secrecy** phù hợp (ví dụ TLS 1.3), việc lấy private signing key sau đó **không tự động giải mã mọi phiên TLS đã ghi lại trước đây**. Tuy nhiên key bị lộ vẫn tạo rủi ro **impersonation hiện tại/tương lai**.
- Nếu hệ thống dùng các phiên bản/cipher suites có cơ chế **static RSA key exchange** cũ, rủi ro giải mã traffic lịch sử có thể khác; phải xem cấu hình TLS thực tế.
- Sessions/resumption có thể tiếp tục theo thiết kế TLS/client và policy mà không kiểm tra certificate từ đầu ở mọi request.

Hành động điển hình: cô lập endpoint và credential liên quan, **new keypair + certificate**, revoke certificate cũ, invalidate/rotate session tickets khi cần, cập nhật certificate pinning/trust, theo dõi CT/logs và thử client behavior.

### 4.2. Leaf mTLS client certificate

Nếu private key của **billing-service** dùng mTLS bị lộ:

- Attacker có thể **giả mạo client workload** ở những endpoints tin issuer/SAN và vẫn chấp nhận certificate đó.
- Nếu mTLS identity được ánh xạ sang **KMS Sign/Decrypt grants**, ảnh hưởng có thể lan từ mạng sang key usage.
- **Revoke certificate** giúp những endpoints thực thi revocation từ chối các kết nối mới; không tự động xóa **token, session, cached DEK** hoặc IAM grants đã được cấp theo identity đó.
- Một sidecar/proxy có thể đã xác thực mTLS ở tầng mạng nhưng application vẫn cần kiểm tra **caller identity → tenant/record/operation authorization**.

Hành động: revoke cert, cấp keypair/cert mới cho workload hợp lệ, dừng/restart compromised instances, revoke/rotate tokens và IAM grants bị ảnh hưởng, kiểm tra KMS data-plane logs và service-to-service sessions.

### 4.3. Code signing / document signing certificate

Nếu private key dùng ký code hoặc tài liệu bị lộ:

- Attacker có thể ký **artifact mới** trông như đến từ publisher.
- Chữ ký số cũ vẫn có thể **verify toán học**, nhưng giá trị tin cậy phụ thuộc bằng chứng **thời điểm ký, certificate status tại thời điểm liên quan, trusted timestamp, revocation information và validation policy**.
- Không nên đánh dấu tự động **mọi artifact đã ký trước đó đều giả**; cũng không nên tin mọi chữ ký có certificate còn hạn nếu khóa đã lộ.
- Key mới cần được công bố tới verifiers và release pipeline; khóa cũ phải ngừng Sign mới, revoke certificate và xử lý artifacts/tokens nghi bị giả.

Với **long-term validation (LTV)**, có thể cần lưu certificate chain, CRL/OCSP evidence, timestamp và chính sách kiểm chứng tại thời điểm ký. **Thời điểm một chữ ký được tạo không được tin chỉ vì nằm trong một trường timestamp do chính người ký khai**.

### 4.4. Intermediate CA compromise

Nếu private key của **Intermediate CA** bị compromise, attacker có thể có khả năng **phát hành certificate giả** trong phạm vi chain/constraints được relying parties chấp nhận. Tác động không còn giới hạn ở một leaf certificate.

Runbook thường nghiêm trọng hơn:

1. Dừng CA issuance/ký mới và cô lập HSM/KMS operator credentials.
2. Phân tích **issuer hierarchy, path constraints, cross-signing và tất cả leaf certificates** do Intermediate đó phát hành.
3. Công bố **revocation của Intermediate** qua issuer tương ứng và phối hợp trust store owners.
4. Tạo Intermediate keypair/certificate mới nếu recovery policy cho phép; reissue leaf certificates cần thiết.
5. Cập nhật chain phân phối, thiết bị/tường lửa/gateways, CRL/OCSP responders, client trust stores.
6. Đối soát **Certificate Transparency** khi phù hợp với public Web PKI, issuer logs và phát hiện mis-issuance.
7. Xem xét emergency distrust/denylist cho clients không xử lý revocation đúng kỳ vọng.

**Không khẳng định mọi leaf certificate thuộc Intermediate bị lộ chắc chắn đã bị giả mạo**; nhưng tổ chức có thể cần **reissuance/distrust trên diện rộng** vì không còn chắc chắn issuer key chỉ được CA hợp pháp sử dụng.

### 4.5. Root CA compromise

Root CA public certificate thường là **trust anchor** đã được cài qua OS/browser/application trust store. Khi **Root CA private key** bị lộ, vấn đề có thể ảnh hưởng rất rộng: các chuỗi certificate dưới root có thể bị giả, tùy các constraints và tập relying parties đang tin root đó.

**Không có cơ chế “CRL của Root CA” phổ quát đủ để giải quyết trust anchor compromise.** Trust anchor thường được cung cấp và quản lý **out-of-band**. Cần:

- Cô lập root key/HSM/recovery/quorum.
- Điều phối **emergency distrust/removal** khỏi trust stores của relying parties.
- Tạo root hierarchy mới, phân phối trust anchors đáng tin, cross-sign/transition khi chính sách cho phép và đánh giá rủi ro.
- Thay các Intermediate và leaf certificates chịu ảnh hưởng; kiểm tra client được cập nhật.
- Kiểm thử thiết bị offline, IoT, mobile, Java truststores tùy chỉnh và pinned roots.

Việc rotate Root CA là **một trust migration**, không chỉ lệnh RotateKey trong KMS.

## 5. Certificate chain và cách revocation ảnh hưởng đường dẫn

~~~mermaid
flowchart LR
    R["Root trust anchor"] --> I1["Intermediate CA v1"]
    R --> I2["Intermediate CA v2"]
    I1 --> L1["Leaf A cũ"]
    I1 --> L2["Leaf B cũ"]
    I2 --> L3["Leaf C mới"]
    X["Intermediate CA v1 bị revoke/distrust"] -.-> I1
    I1 -.-> Y["Các relying parties cần tìm/validate path mới hoặc từ chối"]
~~~

Về nguyên tắc, một relying party phải **validate đường dẫn đầy đủ**, các ràng buộc của CA và revocation theo policy. Tuy nhiên:

- **Không phải mọi trust engine/ứng dụng kiểm tra revocation giống nhau**.
- Một certificate có thể có **nhiều chain khả dĩ** nhờ cross-signing; phải xét issuer, trust anchor, constraints và policy trên path được chọn.
- Nếu Intermediate bị revoke, leaf certificate dưới chain đó có thể không được chấp nhận **qua path bị ảnh hưởng**. Có thể tồn tại chain khác hợp lệ tùy hạ tầng; không giả định tự động.
- Một certificate mà application **pinning** tới public key/CA riêng có thể cần update pin ngay cả khi Web PKI đã có chain mới.
- Thiết bị cũ/offline có thể không tải được CRL hoặc trust store mới, nên **việc CA revoke không đồng nghĩa tất cả clients đã ngừng tin lập tức**.

**Certificate revocation không phải cơ chế xử lý thay thế cho DNS/route isolation, IAM revocation, credential rotation, session termination hoặc business-level authorization.**

## 6. CRL: Certificate Revocation List

### 6.1. CRL hoạt động ra sao?

**Certificate Revocation List (CRL)** là một danh sách được **issuer/CRL issuer ký** để công bố các chứng thư bị thu hồi trong phạm vi của CRL đó. Các trường tiêu biểu:

| Thành phần | Ý nghĩa |
|---|---|
| **Issuer** | Đơn vị phát hành CRL, cần kiểm tra quyền ký CRL và chain |
| **thisUpdate** | Mốc thông tin CRL được công bố/cập nhật |
| **nextUpdate** | Mốc dự kiến có bản cập nhật tiếp theo, dùng đánh giá freshness |
| **Revoked certificate entry** | Serial và thời điểm revocation đối với chứng thư bị thu hồi |
| **Reason code** | Lý do như keyCompromise, cACompromise, superseded, cessationOfOperation... nếu có |
| **CRL Number / Delta CRL Indicator** | Hỗ trợ versioning, delta processing khi profile sử dụng |
| **Signature** | Giúp xác thực CRL không bị sửa, nhưng cần kiểm tra issuer và path |

~~~mermaid
sequenceDiagram
    participant CA as Issuer CA / CRL issuer
    participant P as Publication endpoint
    participant V as Relying party
    CA->>CA: Ghi nhận revocation certificate serial X
    CA->>P: Publish signed CRL mới
    V->>P: Fetch CRL theo policy/CDP/cache
    P-->>V: Signed CRL, thisUpdate, nextUpdate
    V->>V: Verify CRL signature, scope, freshness
    V->>V: Find issuer+serial X
    V-->>V: REVOKED -> từ chối theo policy
~~~

**Serial number không toàn cục**; nó phải được hiểu trong ngữ cảnh **issuer**. Không viết logic “serial X có trong CRL bất kỳ => mọi certificate serial X đều revoked”.

### 6.2. CRL có thể chậm hơn thời điểm quyết định thu hồi

Timeline minh họa:

~~~text
10:00  Security xác nhận private key có khả năng bị lộ
10:02  CA ghi nhận revocation
10:05  CRL mới được ký và publish
10:08  Một số proxy/CDN caches bắt đầu lấy CRL mới
11:00  Một client offline/đang cache bản cũ mới refresh
~~~

Các mốc chỉ minh họa. **Revocation được ghi trong CA database không bảo đảm mọi relying party biết ngay**. Độ trễ phụ thuộc **CRL publication cadence, cache, nextUpdate, endpoint availability, client fetch policy và trust store**.

**CRL đã được ký không có nghĩa CRL còn mới**. Validator cần kiểm tra đúng **issuer/scope, chữ ký, thời gian và delta/indirect CRL semantics nếu sử dụng**.

### 6.3. Delta CRL, partition và indirect CRL

Một PKI quy mô lớn có thể dùng:

- **Full CRL:** snapshot các entries trong phạm vi của một CRL.
- **Delta CRL:** thay đổi bổ sung so với base CRL theo các điều kiện/profile phù hợp.
- **Partitioned CRLs / distribution points:** chia phạm vi certificate/issuer để giảm kích thước.
- **Indirect CRL:** CRL issuer không nhất thiết trùng issuer của certificate; path/authorization phải được xác thực đúng.

**Không tự hợp nhất các CRL bytes như danh sách serial tùy ý**. CRL processing phức tạp hơn một lệnh tải file và tìm chuỗi. Trong production, dùng **PKIX validator/library được bảo trì** và cấu hình policy chuẩn.

### 6.4. Lý do thu hồi certificate

Một số reason codes thường gặp trong X.509 CRL:

| Reason | Ý nghĩa khái quát | Lưu ý |
|---|---|---|
| **keyCompromise** | Có căn cứ private key của subject bị lộ/mất tin cậy | Cần new keypair, không reuse material |
| **cACompromise** | Khóa CA bị compromise | Ảnh hưởng issuance/trust chain rộng hơn |
| **affiliationChanged** | Tổ chức hoặc liên kết danh tính thay đổi | Không mặc nhiên có nghĩa private key lộ |
| **superseded** | Certificate được thay bằng chứng thư khác | Certificate mới không tự làm certificate cũ revoked |
| **cessationOfOperation** | Đơn vị/chức năng ngừng hoạt động | Cần xử lý identities và endpoints liên quan |
| **certificateHold** | Tạm treo theo profile cho phép | Khả năng bỏ hold không phổ quát |
| **privilegeWithdrawn** | Quyền liên quan bị rút | Relying party vẫn phải enforce |
| **removeFromCRL** | Được dùng trong delta CRL để xử lý một số trường hợp gỡ entry | Không coi là thao tác chung “unrevoke” |

Khi có **compromise**, nên ghi nhận **incident time, thời điểm nghi ngờ material mất tin cậy (nếu xác định được), reason và evidence**. Một số PKI dùng **invalidityDate** để chỉ thời điểm key/certificate được cho là không còn tin cậy, có thể khác **revocationDate**; cách đánh giá phụ thuộc PKIX policy và loại chữ ký.

### 6.5. CRL không xử lý được mọi thứ

CRL không:

- Xóa private key đã bị copy ra ngoài.
- Bảo đảm mọi relying party đã tải CRL mới.
- Tự ngắt một TLS session đã tồn tại.
- Ngăn một KMS Sign API tiếp tục hoạt động nếu IAM vẫn cho phép.
- Xác định tính hợp lệ nghiệp vụ của một JWT/hóa đơn đã ký.
- Thay thế việc cập nhật trust anchors khi Root CA compromise.

## 7. OCSP: Kiểm tra trạng thái theo certificate

### 7.1. OCSP request/response

**Online Certificate Status Protocol (OCSP)** cho phép relying party hỏi responder về status của certificate cụ thể, thường được nhận diện bằng **issuer và serial information**.

~~~mermaid
sequenceDiagram
    participant C as TLS Client / Validator
    participant O as Authorized OCSP Responder
    participant CA as Issuer status database
    C->>O: OCSP request issuer+serial
    O->>CA: Lookup revocation data
    CA-->>O: Current status source
    O-->>C: Signed OCSP response + validity times
    C->>C: Verify signer authority, signature, freshness, status
    C->>C: Good / Revoked / Unknown -> policy decision
~~~

Một OCSP response cần được xác thực **đúng responder authorization**, chữ ký, certificate được hỏi, issuer, freshness và policy. Không tin một server tùy ý trả text **good**.

### 7.2. Good, revoked, unknown nghĩa là gì?

| OCSP status | Diễn giải | Không được suy ra |
|---|---|---|
| **good** | Responder không báo certificate đang bị thu hồi trong phạm vi trạng thái đó | Không chứng minh private key chưa lộ; không thay identity/path validation |
| **revoked** | Responder báo certificate bị thu hồi | Không cần thử handshake lại cho đến khi “qua” |
| **unknown** | Responder không xác định được trạng thái certificate | Không được mặc định coi như good |

Ngoài status của certificate còn có **thất bại của OCSP transaction**: response không hợp lệ, signer không đáng tin, quá hạn, timeout, DNS/outage hoặc cache stale. **“Unknown” và “không kết nối được OCSP responder” không phải cùng một điều kiện**, dù chính sách có thể đều chọn từ chối.

### 7.3. Freshness và response caching

Các timestamps quan trọng:

- **producedAt:** thời điểm response được tạo.
- **thisUpdate:** thời điểm trạng thái được biết đúng theo responder.
- **nextUpdate:** thời điểm dự kiến thông tin sẽ được cập nhật; có thể không hiện diện trong mọi profile.
- **revocationTime:** thời điểm certificate được báo revoked; có thể kèm reason.

Validator cần có **giới hạn freshness hợp lý**, clock skew policy và issuer binding. Đừng coi response **good** tạo nhiều ngày trước là bằng chứng đủ cho một high-risk connection mới chỉ vì chữ ký OCSP vẫn còn đúng.

### 7.4. OCSP stapling

Trong **OCSP stapling**, server TLS có thể kèm **OCSP response được ký sẵn** trong quá trình handshake khi client/giao thức hỗ trợ.

~~~text
Không stapling:
  Client -> TLS Server: Handshake
  Client -> OCSP responder: hỏi certificate serial X

Có stapling:
  TLS Server lấy OCSP response định kỳ
  TLS Server -> Client: Certificate + stapled OCSP response
  Client kiểm tra response signature, status, freshness, policy
~~~

Lợi ích có thể gồm giảm phụ thuộc online tới responder, cải thiện độ trễ và quyền riêng tư của client. Nhưng **server có thể gửi response cũ còn trong cache**, nên client vẫn phải đánh giá **freshness**; **stapling không biến một certificate revoked thành certificate hợp lệ**.

**TLS 1.2/TLS 1.3 và các stacks có cơ chế truyền/staple khác nhau**. Không coi “server bật OCSP stapling” là bảo đảm **mọi client đều kiểm tra status**. Một số profile có **TLS Feature/Must-Staple** yêu cầu stapling theo điều kiện hỗ trợ, nhưng cần kiểm tra thực tế client, CA và TLS implementation; không áp dụng như giả định phổ quát.

### 7.5. OCSP và privacy, availability

OCSP online có thể tiết lộ cho responder **certificate nào client đang kiểm tra**. OCSP stapling có thể giảm việc đó. Ngược lại, phụ thuộc hoàn toàn vào live OCSP có thể khiến responder outage gây **TLS connection failures** nếu chính sách fail-closed. Đây là đánh đổi phải được **thiết kế và diễn tập**, không giải quyết bằng việc bỏ mọi revocation check.

## 8. Fail-open, fail-closed và soft-fail

### 8.1. Ba cách xử lý khi status không xác định được

| Chính sách | Hành vi khi không lấy được trạng thái tin cậy | Rủi ro |
|---|---|---|
| **Fail-closed (hard fail)** | Không chấp nhận certificate/connection khi thiếu bằng chứng cần thiết | Có thể ảnh hưởng availability khi OCSP/CRL outage |
| **Fail-open (soft fail)** | Cho phép tiếp tục trong một số lỗi truy xuất status | Có thể chấp nhận certificate thực tế đã bị revoked |
| **Fallback có kiểm soát** | Dùng CRL khi OCSP lỗi hoặc ngược lại, theo validator/profile | Phải bảo đảm nguồn, freshness và semantics tương đương chính sách |

**Fail-open** không nên được đồng nhất với “nếu response xác thực rõ ràng là revoked thì vẫn chấp nhận”. Đó là một lỗi kiểm tra nghiêm trọng; soft-fail thường đề cập **lỗi xác định trạng thái** chứ không biến **revoked** thành **good**.

### 8.2. Chọn policy theo mức rủi ro

Ví dụ:

- **mTLS giữa các hệ thống tài chính/quản lý khóa:** cân nhắc fail-closed với **short-lived identities, HA status endpoints, renewal trước hạn, caching được kiểm soát** và đường DR được phê duyệt.
- **Public client truy cập nhiều website:** hành vi thực tế của browser/platform có thể khác nhau; không thể giả định mọi trình duyệt hard-fail OCSP ở mọi tình huống.
- **Offline verifier kiểm tra artifact lịch sử:** cần chính sách riêng về **revocation evidence/timestamp** đã được bảo toàn; không thể lúc nào cũng gọi OCSP live.
- **IoT/embedded clients:** thiết kế cập nhật trust anchors, CRLs, firmware và khả năng clock/trust bootstrap trước khi deployment.

Không có một công tắc duy nhất phù hợp mọi chương trình. Quan trọng là **threat model, thời gian phản ứng mong muốn, thời gian cache hợp lệ và khả năng duy trì xác thực khi phụ thuộc bên ngoài lỗi**.

### 8.3. Freshness và propagation window

~~~text
T0: CA nhận yêu cầu revoke
T1: CA cập nhật CA database
T2: OCSP responder publish revoked status
T3: CRL mới được publish, CDN cache cập nhật
T4: Relying party refresh status
T5: Relying party từ chối kết nối mới
~~~

**Không đồng nhất T0, T1, T2, T3, T4, T5.** Trong incident response, cần đo **effective distrust time** của các relying parties trọng yếu, thay vì chỉ đánh dấu ticket **revoked** khi CA API phản hồi thành công.

### 8.4. Cấu hình revocation trong ứng dụng Java

Không mặc định rằng mọi đường kiểm tra certificate của Java **đều tự bật OCSP/CRL**. Hành vi phụ thuộc cách ứng dụng dùng **JSSE, PKIX, PKIX parameters, trust manager**, provider và system/security properties. Cần test **TLS handshake thực tế** với certificates đã revoke/OCSP unreachable, không suy từ việc code gọi **checkValidity()**.

## 9. TLS/mTLS: Điều gì thay đổi sau khi revoke certificate?

### 9.1. Kết nối mới và kết nối đang mở

| Đối tượng | Ảnh hưởng khi certificate bị revoke | Việc bổ sung có thể cần |
|---|---|---|
| **Full TLS handshake mới** | Có thể bị từ chối nếu validator đã biết revocation và policy enforce | CRL/OCSP/trust-store propagation test |
| **TLS connection đang mở** | Không tự bị đóng vì CA publish CRL | Terminate/drain sessions/connection pools theo incident |
| **TLS resumed session** | Có thể không lặp đầy đủ certificate validation như full handshake | Session ticket/key lifetime, resumption invalidation, restart |
| **HTTP/2/gRPC channel dài hạn** | Một authenticated channel có thể sống sau thời điểm revoke | Disconnect/re-authenticate theo policy |
| **Proxy/mesh sidecar** | Chính proxy có thể quyết định identity/trust | Reload cert/CRL/trust config, mTLS testing |
| **Application access token** | Token issued trước đó có TTL và revocation riêng | Revoke/rotate token, session, IAM grants |
| **KMS/HSM grant** | Không tự bị thu hồi bởi X.509 revoke | Gỡ quyền Sign/Decrypt/Unwrap, kiểm toán |

Một API **200 OK** từ CA hoặc ACME issuance **không chứng minh** tất cả service instances đã tải certificate mới, mọi kết nối cũ đã dừng hoặc các clients đã từ chối certificate cũ.

### 9.2. Forward secrecy và lịch sử TLS traffic

Một nhầm lẫn phổ biến là “TLS private key bị lộ thì mọi traffic trong nhiều năm đều giải mã được”. Tác động chính xác phụ thuộc **TLS version, key exchange, session secrets, transcript và attacker có dữ liệu nào**:

- Với **TLS 1.3** và các suites có key exchange ephemeral được triển khai đúng, lộ server authentication private key sau khi handshake hoàn tất **không tự cho phép giải mã toàn bộ traffic lịch sử đã capture**.
- Nếu **session secrets, ticket encryption keys hoặc host memory** cũng bị lộ, phạm vi khác; không dựa vào forward secrecy để kết luận host compromise vô hại.
- Với **legacy static RSA key exchange**, traffic được record có thể chịu rủi ro cao hơn nếu private RSA key sau đó lộ.
- Bất kể forward secrecy, **impersonation trong các kết nối mới** là rủi ro lớn khi attacker giữ private key và client tiếp tục tin certificate.

Trong incident, cần phân biệt **key compromise**, **host compromise**, **TLS session-key compromise** và **CA compromise**.

### 9.3. mTLS và workload identity

Một mTLS certificate thường chứng minh danh tính **service/workload**. Khi certificate đó bị revoke:

1. Hạ tầng cần **ngừng nhận certificate cũ** theo trust/revocation policy.
2. Workload hợp pháp cần **enroll lại bằng identity bootstrap đáng tin** và keypair mới.
3. Kiểm tra **SAN/URI, EKU clientAuth, issuer/trust domain, certificate validity** khi nhận certificate mới.
4. Thu hồi hoặc đánh giá lại **KMS grants, access tokens, API session** gắn với identity bị ảnh hưởng.
5. Kiểm tra **business tenant/record authorization** sau mTLS, không trao quyền Decrypt chỉ vì kết nối thành công.

Nếu private key nằm trong **HSM/TPM** non-exportable và chỉ service handle bị lạm dụng, cần điều tra **operation oracle** và attacker privilege; không tự kết luận raw private key đã export. Tùy sự cố, vẫn có thể phải revoke cert hoặc rotate workload credentials.

### 9.4. Certificate pinning

Một client **pin leaf certificate**, **pin public key/SPKI** hoặc **pin CA** có tác động rotation khác nhau:

| Kiểu pin | Khi thay keypair/certificate | Nguy cơ |
|---|---|---|
| **Pin leaf certificate bytes** | Reissue cert mới có thể phá kết nối dù key cũ | Gãy dịch vụ khi renewal |
| **Pin SPKI/public key** | New keypair làm pin cũ không còn khớp | Không thể rotate khẩn cấp nếu không có backup pin/update channel |
| **Pin issuer/CA** | CA migration có thể không được client chấp nhận | CA compromise, trust-store transition khó |

Khi có nguy cơ compromise, **không giữ lại keypair đã lộ chỉ để tương thích pin cũ**. Thiết kế trước **backup pins, secure app update, rollout, monitoring và emergency recovery path**.

## 10. Certificate renewal/rotation khi không có sự cố

### 10.1. Tạo certificate mới không làm certificate cũ tự hết hiệu lực

Trong **routine renewal**, một CA phát hành certificate mới với validity window mới. Có thể:

1. **Tái dùng keypair** theo policy nếu khóa chưa bị compromise và quy định cho phép; hoặc
2. **Tạo keypair mới** để hạn chế thời gian sử dụng vật liệu cũ.

Đối với hệ thống có yêu cầu bảo vệ cao, thường có lý do hợp lý để **rotate keypair** cùng certificate, nhưng quyết định phụ thuộc policy, thuật toán, client compatibility và provider.

~~~mermaid
sequenceDiagram
    participant S as Service / Certificate agent
    participant K as HSM/TPM/KMS or local key store
    participant CA as Issuing CA / Enrollment
    participant P as Load balancer / Service mesh
    participant C as Relying party
    S->>K: Generate fresh keypair khi policy yêu cầu
    K-->>S: Key handle / public key
    S->>CA: CSR + authenticated workload identity
    CA->>CA: Verify SAN/EKU/ownership/policy
    CA-->>S: New leaf certificate + chain
    S->>P: Deploy key handle/private key + certificate
    P->>C: New TLS handshake using new certificate
    C->>C: Validate chain, SAN/EKU, validity, status
    S->>CA: Revoke old certificate nếu policy/compromise yêu cầu
~~~

**Một CSR có chữ ký của requester chỉ cho biết proof of possession** đối với private key tương ứng, không tự chứng minh requester được phép yêu cầu SAN **billing.production**. Enrollment server phải ràng buộc subject/SAN với **authenticated workload identity** và approval.

### 10.2. Overlap an toàn cho renewal định kỳ

Trong renewal **không có nghi compromise**, một overlap cũ/mới có thể được phê duyệt để:

- Rollout nhiều pods/regions và certificate endpoints.
- Cho relying parties cập nhật CA chain, trust store hoặc pins.
- Tránh downtime khi cert cũ còn hợp lệ và cert mới đã active.
- Kiểm thử từ client versions khác nhau.

Trong **key compromise**, mục tiêu lại là **cắt ngắn khả năng chấp nhận certificate cũ**. Không dùng cùng một overlap dài như routine renewal nếu điều đó kéo dài cửa sổ impersonation.

### 10.3. Short-lived certificates

Một số hệ thống service mesh/workload identity dùng **certificate có lifetime ngắn**. Lợi ích:

- Giảm thời gian một credential còn hợp lệ nếu bị đánh cắp.
- Có thể giảm một số nhu cầu phụ thuộc vào cơ chế revocation online, nếu hệ thống được thiết kế với TTL, renewal, distribution và risk phù hợp.

Nhưng:

- Certificate ngắn hạn **không vô hiệu hóa ngay private key bị lộ** trong khoảng còn hiệu lực.
- Một số PKI profile/browser có giới hạn/policy riêng về revocation cho short-lived cert; không mặc nhiên coi “ngắn hạn” là miễn kiểm tra.
- **Issuer/CA compromise** vẫn nghiêm trọng; attacker có thể tiếp tục cấp cert mới nếu issuer không bị cô lập.
- **Clock skew, renewal outages, offline devices và session resumption** phải được cân nhắc.

### 10.4. Certificate lifecycle và key lifecycle khác nhau

~~~text
X.509 Certificate:
    issued -> valid -> renewed/revoked/expired

Private key:
    generated -> stored -> used -> rotated/revoked in KMS -> destroyed

Workload identity / authorization:
    enrolled -> role/grants -> token/cert sessions -> deprovisioned
~~~

Ba dòng này **liên quan nhau nhưng không tự cập nhật đồng bộ**. Ví dụ certificate đã revoke nhưng KMS key object còn ở trạng thái enabled; hoặc KMS key đã disable nhưng certificate mTLS còn được client tin.

## 11. Runbook ứng phó lộ private key của leaf certificate

### 11.1. Các mốc quyết định cần phân biệt

| Mốc | Định nghĩa | Cần ghi nhận |
|---|---|---|
| **T_detected** | Phát hiện dấu hiệu hoặc bằng chứng compromise | Alert, nguồn, log và owner |
| **T_suspected_exposure** | Khoảng thời gian key có thể bắt đầu không còn tin cậy | Bằng chứng, mức độ chắc chắn |
| **T_contained** | Credential/service/network đã được cô lập | Host/role/token/actions |
| **T_revocation_requested** | Đã gửi lệnh revoke cho CA | Ticket, issuer, serial, reason |
| **T_status_published** | CA/OCSP/CRL đã công bố thông tin | Responder/CRL, timestamps |
| **T_clients_reject_old** | Những relying parties trọng yếu thực sự từ chối cert cũ | Test evidence từng client |
| **T_new_credential_active** | Service dùng keypair/certificate mới | Deployment/pod/version evidence |
| **T_old_key_disabled** | Provider key/grants cũ đã bị vô hiệu hóa | KMS/HSM audit |

Không đồng nhất **T_revocation_requested = T_clients_reject_old**. Chỉ khi kiểm thử và giám sát mới biết trạng thái đã được lan truyền tới những clients cần bảo vệ.

### 11.2. Runbook tám bước

**Bước 1 — Xác định tài sản và phạm vi.** Ghi **certificate issuer + serial**, SANs, EKUs, key type/fingerprint, nơi private key tồn tại, key holder (HSM/local), endpoints, consumers, owner, trust anchors và các hệ thống dùng certificate.

**Bước 2 — Cô lập và bảo toàn chứng cứ.** Cô lập host/pod hoặc hạn chế network path phù hợp; revoke human/workload sessions, backup credentials, CI access khi cần. Thu thập logs qua kênh an toàn, **không copy private key vào ticket hoặc chat**.

**Bước 3 — Tạo keypair mới độc lập.** Sinh material bằng CSPRNG hoặc provider/HSM được duyệt; không reissue certificate chỉ trên public key cũ khi key private có khả năng bị lộ.

**Bước 4 — Re-enroll certificate.** Xác thực workload identity, SAN/EKU, key usage, issuer hierarchy. Phát hành certificate mới, kiểm tra chain, expiry, revocation distribution endpoints và audit.

**Bước 5 — Revoke certificate cũ.** Yêu cầu đúng issuer/serial, reason **keyCompromise** nếu phù hợp, lưu revocation evidence; cập nhật CRL/OCSP và kế hoạch **emergency distrust** với clients không hỗ trợ status propagation kịp.

**Bước 6 — Cắt đường lạm dụng khác.** Disable/restrict old key handle hoặc KMS Sign permissions, rotate API tokens, session tickets và mTLS trust/grants nếu liên quan. **Revoke X.509 không tự xử lý các thứ này**.

**Bước 7 — Kiểm tra tích cực và tiêu cực.** New certificate phải kết nối thành công tới clients hợp pháp; old certificate phải bị từ chối bởi clients trọng yếu; expired/revoked/unknown/stale status phải có hành vi theo policy.

**Bước 8 — Đối soát và hậu kiểm.** Đối soát OCSP/CRL freshness, application trust stores, API logs, những kết nối kéo dài, rollback plan, bản backup có key cũ và nguy cơ issuance khác.

### 11.3. Quy trình xử lý song song

Trong sự cố nghiêm trọng, **không nhất thiết tuần tự chờ CA revoke rồi mới tạo khóa**, hoặc chờ rollout mới rồi mới chặn key bị lộ. Các luồng có thể chạy song song theo mức độ khẩn:

~~~mermaid
flowchart TD
    A["Suspected key compromise"] --> B["Isolate affected workload/credentials"]
    A --> C["CA revoke old issuer+serial"]
    A --> D["Generate new keypair + issue certificate"]
    B --> E["Audit sessions, KMS operations, tokens"]
    C --> F["Verify CRL/OCSP and relying-party distrust"]
    D --> G["Deploy and verify new cert/identity"]
    E --> H["Assess data/signature exposure"]
    F --> I["Revoke/distrust old credential effectively"]
    G --> I
    H --> J["Recovery + monitoring + independent review"]
    I --> J
~~~

Đối với API quan trọng, việc **tắt endpoint** có thể gây downtime; việc **để endpoint tiếp tục dùng private key lộ** kéo dài rủi ro. Incident commander phải chọn phương án theo severity, khả năng cô lập routing và contingency đã duyệt.

### 11.4. RACI và separation of duties

| Vai trò | Công việc | Quyền không nên mặc định |
|---|---|---|
| **Service owner** | Xác định endpoint, downtime, client compatibility và rollout | Issue CA certificate tùy ý |
| **Security/Incident commander** | Xác định severity, containment, revocation deadline | Tự che audit hoặc export root key |
| **PKI/CA operator** | Revoke đúng issuer/serial, verify CRL/OCSP, issue theo policy | Giải mã dữ liệu khách hàng |
| **KMS/HSM operator** | Disable grants, rotate/restore key theo approval | Tự phát hành chứng thư CA trái policy |
| **Identity/IAM operator** | Revoke workload tokens/sessions, rotate service identities | Sử dụng Sign/Decrypt không giới hạn |
| **Platform/SRE** | Rollout cert, reload proxies, terminate sessions, validate clients | Đọc raw private CA key |
| **Independent auditor** | Đối soát evidence, status propagation, impact và approvals | Sửa PKI logs hoặc Sign bằng private key |

**Một CA operator có quyền issue cert và một Security admin có quyền cấp IAM grant** là hai control planes rất nhạy cảm. Cần bảo vệ riêng, audit và approval; không dùng shared admin token tồn tại vĩnh viễn.

## 12. Key material: KMS/HSM và certificate revocation không thay thế nhau

### 12.1. Certificate private key được tạo và lưu ở đâu?

| Vị trí | Lợi ích | Rủi ro cần xử lý |
|---|---|---|
| **HSM/TPM non-exportable** | Giảm khả năng đưa private key raw ra application | Signing/decrypt oracle nếu quyền bị lạm dụng; hardware/provider limits |
| **KMS asymmetric key handle** | IAM, audit, managed key lifecycle | Không phải mọi KMS hỗ trợ TLS handshake/CSR/certificate enrollment |
| **Java KeyStore/PKCS#12 file** | Hỗ trợ nhiều ứng dụng legacy | File/password backup, build artifacts, disk/process compromise |
| **Filesystem PEM** | Đơn giản trong app/proxy | Secret leakage, permissions, logs, image/CI copies |
| **Workload sidecar/agent** | Identity cấp/renew runtime, giảm thao tác app | Sidecar trust, process access, stale sockets, agent compromise |

**Non-exportable private key không đồng nghĩa không thể bị lạm dụng.** Nếu attacker có quyền gọi **Sign** với key handle, họ có thể tạo chữ ký/TLS proof trong điều kiện giao thức phù hợp. Cần **operation scope, workload identity, rate limits, business checks và audit**.

### 12.2. Ba hành động khác nhau

~~~text
Revoke certificate:
    Relying parties được yêu cầu ngừng tin issuer+serial đó.

Disable/rotate private key:
    KMS/HSM/application không tiếp tục sử dụng material cũ.

Revoke session/credential:
    Người/ứng dụng không tiếp tục dùng access tokens/sessions
    được tạo khi credential cũ còn được chấp nhận.
~~~

Chỉ làm một trong ba **không luôn đủ**. Cần chọn theo key role:

- TLS/mTLS: certificate, private key, sessions/identities và authorization.
- Code/document signing: certificate trust, signing key, release pipeline, artifact provenance.
- CA compromise: issuer hierarchy, trust stores, issuance logs và certificates đã cấp.
- Envelope encryption: KEK/DEK compromise và encrypted data dependencies **không tự bị sửa bằng revoke một TLS certificate**.

### 12.3. BYOK/PKCS#11/JCA và thay key mà không mất dữ liệu

Nếu khóa liên quan certificate còn dùng **giải mã dữ liệu lịch sử**, key destruction có thể ảnh hưởng khả năng truy cập. Cần kiểm tra **key usage**:

- **TLS Ed25519/ECDSA signing private key:** thường không cần giữ để **verify chữ ký TLS cũ** sau handshake, nhưng còn có session/resumption/trust evidence cần quản trị.
- **S/MIME/email encryption private key:** có thể cần để giải mã thư cũ; đây là trường hợp phải đánh giá **recovery/retention** trước khi hủy key, đồng thời xử lý compromise.
- **Document signing private key:** không cần để verify chữ ký cũ; public certificate/trust evidence có thể cần tồn tại.
- **CA private key:** cần kiểm soát issuance/CRL signing/OCSP delegation/backup; không hủy vô kế hoạch khiến PKI mất khả năng vận hành.

**Không lấy một runbook chung “destroy mọi private key ngay sau revoke” áp cho mọi purpose**. Việc hủy key phải xét confidentiality, integrity, khả năng khôi phục và retention.

## 13. Phân phối trạng thái tin cậy tới relying parties

### 13.1. CA nói “revoked” chưa đủ

Các relying parties có thể gồm:

- Trình duyệt, hệ điều hành và mobile clients.
- Java truststore **cacerts** hoặc truststore riêng của ứng dụng.
- API gateway, reverse proxy, load balancer và service mesh sidecar.
- HSM/KMS clients, PKCS#11 consumers và hardware security appliances.
- Microservices dùng mTLS/SPKI pinning.
- IoT/offline clients, firmware updaters và certificate pinning trong mobile app.
- Signature validators, document archives và JWT verifiers.

**Mỗi nhóm có trust policy, cache và kênh cập nhật khác nhau**. Cần inventory và kiểm thử đại diện để chứng minh certificate cũ đã bị từ chối.

### 13.2. Trust-store migration khi CA bị lộ

~~~text
CA-v1 compromised / distrusted
    |
    +-- Suspend issuance under CA-v1
    +-- Identify every issued intermediate/leaf and active client
    +-- Publish revocation/distrust data
    +-- Generate CA-v2 keys in approved HSM/quorum
    +-- Distribute trusted CA-v2 anchor/path
    +-- Re-enroll leaf certificates under approved issuer
    +-- Test clients with old-v1 and new-v2 paths
    +-- Remove CA-v1 trust when policy and migration permit
~~~

Nếu một **Root CA** bị lộ, relying parties thường phải **cập nhật trust anchors** bằng kênh quản trị riêng. Một root self-signed certificate cũ không có issuer cao hơn theo đường dẫn PKIX thông thường để chỉ phát CRL rồi hy vọng mọi thiết bị đã ngừng tin.

### 13.3. Kênh phát hành trust anchors cũng là tài sản bảo mật

Nếu attacker kiểm soát **software update channel** dùng phân phối trust store, họ có thể chèn root giả hoặc chặn cập nhật distrust. Do đó:

- Trust-store updates cần **authenticated/signed distribution**.
- Tách quyền quản lý CA, ký update, deploy clients.
- Kiểm tra integrity/version và chống downgrade của trust packages.
- Có **offline/embedded device recovery** và rollout/rollback safety.
- Audit danh sách clients không cập nhật được, cùng compensating controls.

### 13.4. Certificate Transparency (CT) và revocation

**Certificate Transparency** có thể hỗ trợ phát hiện certificate public Web PKI được cấp trái phép và theo dõi issuance. Nhưng **CT log không phải CRL/OCSP**, và một certificate xuất hiện trong CT **không chứng minh nó đang trusted hoặc chưa revoked**. Với **private PKI**, có thể cần issuance transparency/audit khác; không giả định CT công khai bao phủ mọi mTLS cert nội bộ.

### 13.5. Certificate pinning và emergency migration

Với client pin SPKI cũ, một certificate mới dù CA ký đúng vẫn có thể bị từ chối. Vì vậy:

1. Thiết kế **backup pin/approved public keys** trước sự cố nếu phù hợp.
2. Duy trì kênh **secure app/firmware update** độc lập.
3. Test **old leaf rejected**, **new leaf accepted** và kiểm tra cập nhật pin.
4. Không giải quyết bằng cách tắt hostname verification hoặc trust mọi certificate.

**Một thời điểm emergency không phải lý do để cài TrustManager luôn trả true**. Điều đó biến một sự cố private key thành cơ hội MITM dài hạn.

## 14. Chữ ký lịch sử: Certificate revoked có làm mọi chữ ký cũ vô hiệu?

Đây là tình huống quan trọng nhất khi certificate được dùng cho **chữ ký tài liệu, firmware hoặc code signing**, thay vì chỉ cho TLS handshake tức thời.

### 14.1. Hai câu hỏi khác nhau

Một verifier cần tách:

1. **Cryptographic signature verification:** Chữ ký có khớp với thông điệp và **public key** trong certificate không?
2. **Trust validation at relevant time:** Tại thời điểm liên quan, certificate/key/issuer có được tin cậy không, key có bị compromise từ trước không, timestamp/Revocation evidence nào đáng tin?

~~~text
Signer tạo chữ ký trên Document A ở T1.
Certificate bị revoke ở T3 do key compromise.

Ngày T4:
    Signature.verify(documentA, publicKey) -> true

Nhưng:
    “Có được chấp nhận Document A không?”
    -> phụ thuộc vào evidence T1, compromise interval,
       revocation reason, trusted timestamp và validation policy.
~~~

**Một timestamp tự khai trong tài liệu hoặc signed payload không đủ chứng minh chữ ký được tạo trước compromise**. Các giải pháp long-term signatures có thể cần **trusted timestamp authority**, signed validation evidence và policy về thời điểm đánh giá.

### 14.2. Revocation time và invalidity date

CA có thể ghi nhận **revocationDate** là khi revocation được xử lý/công bố. Một số profile/evidence có thể có **invalidityDate** chỉ thời điểm có căn cứ private key thực tế không còn tin cậy. Hai mốc không nhất thiết bằng nhau.

Nếu sự cố được phát hiện **ngày 10** nhưng log cho thấy key có khả năng đã bị lấy **ngày 3**, không thể mặc định mọi chữ ký tạo ngày 8 là đáng tin chỉ vì **revocationDate = ngày 10**.

### 14.3. Long-Term Validation (LTV)

Một hồ sơ lưu trữ dài hạn có thể cần:

| Dữ liệu/evidence | Vai trò |
|---|---|
| **Signed artifact và digest** | Nội dung đã ký và dữ liệu cần xác minh |
| **Signer certificate + chain** | Xây đường dẫn tới trust anchor được tin tại thời điểm liên quan |
| **OCSP/CRL evidence được xác thực** | Kiểm tra certificate status, freshness và thời điểm áp dụng |
| **Trusted timestamp** | Bằng chứng từ bên được tin về sự tồn tại chữ ký tại mốc thời gian |
| **Algorithm policy / archival renewal** | Đánh giá khi algorithm yếu đi theo thời gian |
| **Revocation reason/incident evidence** | Hỗ trợ phân biệt hết hạn, superseded, compromise |
| **Validation policy version** | Giải thích vì sao tại thời điểm review chữ ký được chấp nhận/từ chối |

**Certificate hiện tại đã expired không tự chứng minh chữ ký tài liệu được tạo trong hiệu lực là giả**. Ngược lại, chữ ký verify toán học vẫn có thể bị bác bỏ khi không chứng minh được trust/time hoặc private key đã lộ trước thời điểm ký.

### 14.4. JWT và certificate trust

JWT/JWS có thể sử dụng public key/certificate trong **JWKS**, header **x5c** hoặc các trust representations khác. Một JWT được ký bằng private key đã lộ có thể được attacker tạo cho đến khi verifiers từ chối key và policies được cập nhật.

- **JWT kid/x5c là dữ liệu từ token header chưa tin cậy**, không được tự ý dùng URL hoặc certificate chain tùy ý như trust anchor.
- Verifier phải kiểm tra **issuer, audience, algorithm allowlist, signature, expiry, token type, key trust** và revocation/session theo application.
- **Certificate revocation** có thể ảnh hưởng tới trust của signer, nhưng không nhất thiết **tự revoke mọi JWT đã phát** tại ứng dụng.
- Một certificate cũ cần được Verify token chưa hết hạn theo routine rotation có thể được giữ trong trust store có giới hạn; **compromise** thường yêu cầu xử lý khẩn, không dùng grace window theo thói quen.

### 14.5. Code signing và firmware update

Một private code-signing key bị lộ có thể cho attacker tạo **malicious artifacts với chữ ký cryptographic hợp lệ**. Chỉ revoke certificate là không đủ nếu updater offline không kiểm tra revocation.

Defense in depth:

- Phát hành keypair/code-signing certificate mới.
- Publish **distrust/revocation** tới artifact validators và device trust stores.
- Dùng **signed release metadata, artifact digests, allowlisted publisher identities, monotonic version/counters** khi kiến trúc yêu cầu chống rollback.
- Kiểm tra provenance của builds, CI/CD access, release approvals và audit.
- Có firmware recovery path khi cập nhật trust anchor, tránh làm thiết bị “brick” do key cũ bị revoke trước khi thiết bị tin key mới.

**Chữ ký số chứng minh mối liên hệ khóa–nội dung theo phép toán, không tự chứng minh một release đã được tổ chức cho phép**. Cần kết hợp release governance và certificate trust.

## 15. Java 17: Mô phỏng certificate decision theo validity, purpose và revocation

Ví dụ sau là một **policy exercise tự chạy với JDK 17**, không tải certificate thật. Nó mô hình hóa dữ liệu validator thường phải đánh giá:

- Đúng **issuer+serial binding** cho evidence.
- Đường dẫn và chữ ký certificate đã được một bộ máy **PKIX thật** xác nhận (trong demo là cờ boolean minh họa).
- Đúng **SAN/expected service identity**, purpose **TLS_SERVER / MTLS_CLIENT / CODE_SIGNING**.
- Đúng **notBefore/notAfter** và peer **proof of possession**.
- Revocation status **GOOD, REVOKED, UNKNOWN** và **UNAVAILABLE**.
- OCSP-like evidence có **responder authorization/signature, thisUpdate và nextUpdate** hợp lệ.
- **Fail-closed** khi status không xác định được; tùy chọn soft-fail mô phỏng chỉ cho **network unavailable**, không cho explicit REVOKED.

**Giới hạn:** Các cờ **chainValidated, peerProvedKeyPossession, responderSignatureValidated** được gán trong source để thực hành policy. Chúng **không phải kết quả kiểm chứng chữ ký/PKIX thật** và tuyệt đối không được nhận từ request body làm bằng chứng security. Certificate status thực tế phải được thu thập qua CA/CRL/OCSP đáng tin và validation library phù hợp.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class CertificateRevocationImpactDemo {

    enum Usage {
        TLS_SERVER, MTLS_CLIENT, CODE_SIGNING
    }

    enum Status {
        GOOD, REVOKED, UNKNOWN
    }

    record CertificateMetadata(
            String issuerId,
            String serialNumber,
            String subjectIdentity,
            Usage usage,
            Instant notBefore,
            Instant notAfter,
            boolean chainValidated,
            boolean peerProvedKeyPossession) {

        CertificateMetadata {
            Objects.requireNonNull(issuerId);
            Objects.requireNonNull(serialNumber);
            Objects.requireNonNull(subjectIdentity);
            Objects.requireNonNull(usage);
            Objects.requireNonNull(notBefore);
            Objects.requireNonNull(notAfter);
            if (issuerId.isBlank()
                    || serialNumber.isBlank()
                    || subjectIdentity.isBlank()
                    || !notAfter.isAfter(notBefore)) {
                throw new IllegalArgumentException(
                        "Invalid certificate metadata");
            }
        }
    }

    // Mô phỏng evidence đã lấy từ OCSP/CA.
    // Không dùng boolean này để thay verify OCSP signature!
    record StatusEvidence(
            String issuerId,
            String serialNumber,
            Status status,
            Instant thisUpdate,
            Instant nextUpdate,
            boolean responderSignatureValidated) {

        StatusEvidence {
            Objects.requireNonNull(issuerId);
            Objects.requireNonNull(serialNumber);
            Objects.requireNonNull(status);
            Objects.requireNonNull(thisUpdate);
            Objects.requireNonNull(nextUpdate);
        }
    }

    record Policy(
            Usage requiredUsage,
            String expectedIdentity,
            Duration maximumEvidenceAge,
            Duration clockSkew,
            boolean failClosedOnUnavailable) {
        Policy {
            Objects.requireNonNull(requiredUsage);
            Objects.requireNonNull(expectedIdentity);
            Objects.requireNonNull(maximumEvidenceAge);
            Objects.requireNonNull(clockSkew);
            if (maximumEvidenceAge.isNegative()
                    || maximumEvidenceAge.isZero()
                    || clockSkew.isNegative()) {
                throw new IllegalArgumentException("Invalid policy");
            }
        }
    }

    record Decision(boolean accepted, String reason) {}

    static Decision validate(
            CertificateMetadata certificate,
            StatusEvidence evidence,
            Policy policy,
            Instant now) {

        Objects.requireNonNull(certificate);
        Objects.requireNonNull(policy);
        Objects.requireNonNull(now);

        if (!certificate.chainValidated()) {
            return new Decision(false, "PATH_OR_SIGNATURE_INVALID");
        }
        if (certificate.usage() != policy.requiredUsage()
                || !certificate.subjectIdentity().equals(
                        policy.expectedIdentity())) {
            return new Decision(false, "IDENTITY_OR_USAGE_MISMATCH");
        }
        if (now.isBefore(certificate.notBefore())
                || !now.isBefore(certificate.notAfter())) {
            return new Decision(false, "CERTIFICATE_NOT_TIME_VALID");
        }
        if (!certificate.peerProvedKeyPossession()) {
            return new Decision(false, "NO_PRIVATE_KEY_PROOF");
        }

        if (evidence == null) {
            return policy.failClosedOnUnavailable()
                    ? new Decision(false, "STATUS_UNAVAILABLE_FAIL_CLOSED")
                    : new Decision(true, "STATUS_UNAVAILABLE_SOFT_FAIL");
        }

        if (!certificate.issuerId().equals(evidence.issuerId())
                || !certificate.serialNumber().equals(
                        evidence.serialNumber())) {
            return new Decision(false, "WRONG_REVOCATION_EVIDENCE");
        }
        if (!evidence.responderSignatureValidated()) {
            return new Decision(false, "UNTRUSTED_STATUS_RESPONSE");
        }

        // Không nhận future thisUpdate vượt clock skew.
        if (evidence.thisUpdate().isAfter(
                now.plus(policy.clockSkew()))) {
            return new Decision(false, "FUTURE_STATUS_RESPONSE");
        }
        if (!evidence.nextUpdate().isAfter(evidence.thisUpdate())
                || !now.isBefore(
                        evidence.nextUpdate().plus(policy.clockSkew()))
                || evidence.thisUpdate().isBefore(
                        now.minus(policy.maximumEvidenceAge()))) {
            return new Decision(false, "STATUS_EVIDENCE_STALE");
        }

        return switch (evidence.status()) {
            case GOOD -> new Decision(true, "GOOD_STATUS_UNDER_POLICY");
            case REVOKED -> new Decision(false, "CERTIFICATE_REVOKED");
            case UNKNOWN -> new Decision(false, "CERTIFICATE_STATUS_UNKNOWN");
        };
    }

    private static StatusEvidence status(
            CertificateMetadata certificate, Status state,
            Instant now) {
        return new StatusEvidence(
                certificate.issuerId(),
                certificate.serialNumber(),
                state,
                now.minus(Duration.ofMinutes(5)),
                now.plus(Duration.ofHours(1)),
                true);
    }

    private static void show(
            String description,
            CertificateMetadata cert,
            StatusEvidence evidence,
            Policy policy,
            Instant now) {
        Decision d = validate(cert, evidence, policy, now);
        System.out.println(description + ": "
                + d.accepted() + " / " + d.reason());
    }

    public static void main(String[] args) {
        // Thời gian cố định để các kết quả minh họa lặp lại.
        Instant now = Instant.parse("2026-11-28T00:00:00Z");

        CertificateMetadata serviceCertificate =
                new CertificateMetadata(
                        "internal-intermediate-ca-v2",
                        "serial-0042",
                        "billing.service.internal",
                        Usage.TLS_SERVER,
                        now.minus(Duration.ofDays(3)),
                        now.plus(Duration.ofDays(4)),
                        true,
                        true);

        Policy highRiskTLS = new Policy(
                Usage.TLS_SERVER,
                "billing.service.internal",
                Duration.ofHours(12),
                Duration.ofMinutes(2),
                true);

        show("Fresh good", serviceCertificate,
                status(serviceCertificate, Status.GOOD, now),
                highRiskTLS, now);
        show("Explicit revoked", serviceCertificate,
                status(serviceCertificate, Status.REVOKED, now),
                highRiskTLS, now);
        show("Unknown status", serviceCertificate,
                status(serviceCertificate, Status.UNKNOWN, now),
                highRiskTLS, now);
        show("OCSP unavailable (hard fail)",
                serviceCertificate, null, highRiskTLS, now);

        Policy softFailDemo = new Policy(
                Usage.TLS_SERVER,
                "billing.service.internal",
                Duration.ofHours(12),
                Duration.ofMinutes(2),
                false);
        show("Network unavailable (soft fail demo)",
                serviceCertificate, null, softFailDemo, now);

        // Soft-fail KHÔNG chấp nhận response REVOKED rõ ràng.
        show("Revoked even with soft-fail policy",
                serviceCertificate,
                status(serviceCertificate, Status.REVOKED, now),
                softFailDemo, now);

        StatusEvidence oldGood = new StatusEvidence(
                serviceCertificate.issuerId(),
                serviceCertificate.serialNumber(),
                Status.GOOD,
                now.minus(Duration.ofDays(2)),
                now.minus(Duration.ofDays(1)),
                true);
        show("Stale good cannot bypass",
                serviceCertificate, oldGood, softFailDemo, now);

        StatusEvidence wrongSerial = new StatusEvidence(
                serviceCertificate.issuerId(),
                "serial-OTHER",
                Status.GOOD,
                now.minus(Duration.ofMinutes(2)),
                now.plus(Duration.ofHours(1)),
                true);
        show("Wrong issuer-serial evidence",
                serviceCertificate, wrongSerial, highRiskTLS, now);

        Policy wrongHost = new Policy(
                Usage.TLS_SERVER,
                "other.service.internal",
                Duration.ofHours(12),
                Duration.ofMinutes(2),
                true);
        show("Wrong expected identity",
                serviceCertificate,
                status(serviceCertificate, Status.GOOD, now),
                wrongHost, now);

        CertificateMetadata expired =
                new CertificateMetadata(
                        serviceCertificate.issuerId(),
                        serviceCertificate.serialNumber(),
                        serviceCertificate.subjectIdentity(),
                        serviceCertificate.usage(),
                        now.minus(Duration.ofDays(10)),
                        now.minus(Duration.ofHours(1)),
                        true,
                        true);
        show("Expired despite good OCSP",
                expired,
                status(expired, Status.GOOD, now),
                highRiskTLS, now);

        CertificateMetadata noKeyProof =
                new CertificateMetadata(
                        serviceCertificate.issuerId(),
                        serviceCertificate.serialNumber(),
                        serviceCertificate.subjectIdentity(),
                        serviceCertificate.usage(),
                        serviceCertificate.notBefore(),
                        serviceCertificate.notAfter(),
                        true,
                        false);
        show("No private-key proof",
                noKeyProof,
                status(noKeyProof, Status.GOOD, now),
                highRiskTLS, now);
    }
}
~~~

Lưu mã trên thành **CertificateRevocationImpactDemo.java** và chạy với JDK 17+:

~~~bash
javac CertificateRevocationImpactDemo.java
java CertificateRevocationImpactDemo
~~~

Kết quả logic dự kiến:

~~~text
Fresh good: true / GOOD_STATUS_UNDER_POLICY
Explicit revoked: false / CERTIFICATE_REVOKED
Unknown status: false / CERTIFICATE_STATUS_UNKNOWN
OCSP unavailable (hard fail): false / STATUS_UNAVAILABLE_FAIL_CLOSED
Network unavailable (soft fail demo): true / STATUS_UNAVAILABLE_SOFT_FAIL
Revoked even with soft-fail policy: false / CERTIFICATE_REVOKED
Stale good cannot bypass: false / STATUS_EVIDENCE_STALE
Wrong issuer-serial evidence: false / WRONG_REVOCATION_EVIDENCE
Wrong expected identity: false / IDENTITY_OR_USAGE_MISMATCH
Expired despite good OCSP: false / CERTIFICATE_NOT_TIME_VALID
No private-key proof: false / NO_PRIVATE_KEY_PROOF
~~~

### 15.1. Những gì ví dụ mô phỏng đúng ở mức policy

| Tình huống | Kết quả | Ý nghĩa |
|---|---|---|
| Certificate đúng identity, purpose, thời hạn; status good và mới | ALLOW | Nhiều kiểm tra cần đồng thời thỏa |
| Responder xác nhận revoked | DENY | Không biến revoked thành good vì soft-fail |
| Status unknown | DENY | Không nhầm unknown với good |
| Không lấy được status, high-risk policy | DENY | Fail-closed |
| Network unavailable, policy có chủ ý soft-fail | ALLOW có cảnh báo | Chấp nhận rủi ro availability/identity |
| Status good nhưng evidence đã quá hạn | DENY | Signature của OCSP không đủ nếu freshness sai |
| Evidence của certificate serial khác | DENY | Không dùng CRL/OCSP info của key khác |
| Host/SAN expected identity khác | DENY | Không chỉ kiểm tra chain |
| Certificate expired dù OCSP good | DENY | Validity và revocation là hai kiểm tra khác nhau |
| Peer không chứng minh private-key possession | DENY | Certificate public không đủ xác thực peer |

### 15.2. Những gì ví dụ không chứng minh

1. **Không parse X.509 thật**. Subject identity ở đây chỉ là chuỗi so sánh chính xác, không phải hostname/SAN validation theo RFC và profile.
2. **Không xác minh CA/OCSP signatures**. Các boolean được gán trực tiếp và không đáng tin nếu đến từ mạng.
3. **Không xây certificate path** với BasicConstraints, name constraints, policy OIDs, KeyUsage/EKU, thuật toán, strength hoặc trust anchors.
4. **Không xử lý CRLs, delta/indirect CRLs, delegated OCSP signing, responder certificates, nonce hoặc OCSP producedAt**.
5. **Không triển khai JSSE/TLS handshake**. Nó không kiểm tra resumed sessions, endpoint identification, session ticket lifetime hay server name indication.
6. **Không quản lý trust-store update/CA compromise** hoặc xử lý cross-signed chains.
7. **Không kiểm tra client app-specific authorization**, tenant/IAM grants và workload tokens.
8. **Không xử lý certificateHold/removeFromCRL, invalidityDate hay long-term signature validation**.
9. **Thời gian và freshness chỉ là policy ví dụ**, không phải ngưỡng được chuẩn bắt buộc cho mọi CA/client.
10. **Không nên bật soft-fail theo mặc định**: demo cho thấy trade-off, không khuyến nghị áp dụng cho high-risk TLS.

**Không triển khai production bằng cách truyền “certificateIsValid=true” từ caller tới function như trong demo.** Dùng **PKIX validator/JSSE trust manager** được cấu hình đúng và xác minh hành vi với chứng thư thật.

## 16. Java 17 thực tế: PKIXRevocationChecker và những kiểm tra còn thiếu

### 16.1. Vì sao checkValidity() không đủ?

Một **X509Certificate** trong JCA có thể hỗ trợ:

- **checkValidity(Date):** kiểm tra notBefore/notAfter.
- **getKeyUsage():** đọc KeyUsage bit flags.
- **getExtendedKeyUsage():** đọc EKU OIDs.
- **getSubjectAlternativeNames():** đọc SAN entries.
- **verify(PublicKey):** kiểm tra chữ ký trên certificate bằng issuer public key được cung cấp.

Những thao tác này **không tự ghép thành một trust decision hoàn chỉnh**. Một attacker có thể đưa cho ứng dụng một certificate tự ký cùng private key riêng; **verify** bằng chính public key tự cung cấp có thể thành công toán học nhưng **không có trust anchor được phê duyệt**.

**PKIX path validation** cần kiểm tra chain tới trust anchor, các constraints và trạng thái chứng thư theo chính sách. **Hostname/SAN endpoint identification** và **business IAM** vẫn là những bước riêng.

### 16.2. Ví dụ tích hợp PKIX revocation check

Đây là **một hàm tích hợp** vào hệ thống đã có **CertPath hợp lệ về thứ tự và TrustAnchor được cấu hình an toàn**, không phải chương trình chạy độc lập. Nó cho thấy cách yêu cầu Java PKIX validator dùng revocation checker thay vì chỉ kiểm tra validity.

~~~java
import java.security.GeneralSecurityException;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.PKIXRevocationChecker;
import java.security.cert.TrustAnchor;
import java.util.Date;
import java.util.EnumSet;
import java.util.Set;

public final class PkixRevocationValidation {

    private PkixRevocationValidation() {}

    public static PKIXCertPathValidatorResult validatePath(
            CertPath path,
            Set<TrustAnchor> approvedAnchors,
            Date validationTime)
            throws GeneralSecurityException {

        // Caller phải chuẩn bị path leaf -> intermediates,
        // không tự tin trust anchor lấy từ untrusted network.
        PKIXParameters parameters =
                new PKIXParameters(approvedAnchors);
        parameters.setDate(validationTime);

        // Tắt cơ chế tự chọn mặc định để dùng checker
        // được cấu hình rõ; KHÔNG phải tắt revocation.
        parameters.setRevocationEnabled(false);

        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker revocation =
                (PKIXRevocationChecker) validator.getRevocationChecker();

        // Không bật SOFT_FAIL.
        // Với các provider hỗ trợ PKIXRevocationChecker,
        // empty options thường dùng cơ chế mặc định:
        // ưu tiên OCSP và có thể fallback CRL.
        revocation.setOptions(
                EnumSet.noneOf(
                        PKIXRevocationChecker.Option.class));
        parameters.addCertPathChecker(revocation);

        return (PKIXCertPathValidatorResult)
                validator.validate(path, parameters);
    }
}
~~~

**Các điều kiện để đoạn tích hợp này thực sự dùng được**:

1. **CertPath** đã được xây từ leaf qua intermediates đúng cấu trúc; root trust anchor thường do **approvedAnchors** cung cấp, không nhất thiết nằm trong path.
2. **approvedAnchors** đến từ trust store/config được phê duyệt, không từ certificate chain do server gửi rồi mặc định tin.
3. Provider phải có hỗ trợ **PKIXRevocationChecker**, URL/status infrastructure và/hoặc CRL/OCSP data phù hợp. Hành vi network/config có thể phụ thuộc provider và runtime.
4. Đoạn code **không tự bật hostname/SAN verification**; TLS client phải có **endpoint identification** và/hoặc một hostname verifier thích hợp.
5. Đoạn code **không xác minh clientAuth/serverAuth EKU hoặc authorization của tenant** theo yêu cầu của từng ứng dụng, ngoài những kiểm tra mà validator/profile thực thi.
6. **Không bật SOFT_FAIL** nếu mục tiêu là hard-fail trên lỗi xác định revocation. Nếu tổ chức chủ động bật **Option.SOFT_FAIL**, phải ghi rõ threat model, giám sát và test tương ứng.
7. Đoạn code **không giải quyết CRL/OCSP responder trust endpoint availability**; phải cấu hình/kiểm thử thật.
8. **validationTime** cần nguồn thời gian đáng tin cho kiểm tra hiện tại; không được dùng timestamp từ client để lùi thời gian tùy ý.

### 16.3. Những tùy chọn của PKIXRevocationChecker

Các tùy chọn như:

| Option | Tác động chính | Lưu ý |
|---|---|---|
| **PREFER_CRLS** | Ưu tiên CRL so với OCSP khi checker hỗ trợ | Không bảo đảm CRL luôn mới/được tải |
| **NO_FALLBACK** | Không dùng cơ chế dự phòng sau cơ chế ưu tiên | Có thể tăng hard failures nếu nguồn primary lỗi |
| **SOFT_FAIL** | Cho phép bỏ qua một số lỗi không xác định được trạng thái theo đặc tả của checker | Không có nghĩa chấp nhận certificate có status REVOKED rõ ràng |
| **ONLY_END_ENTITY** | Chỉ kiểm tra revocation ở end-entity certificates theo checker | Không phù hợp nếu threat model cần check Intermediate |

**Không chọn ONLY_END_ENTITY theo thói quen** trong PKI mà compromise của Intermediate CA là một rủi ro quan trọng. Kiểm tra cả chain CA certificates theo policy.

### 16.4. JSSE và hostname verification

Nếu dùng trực tiếp **SSLSocket**, phải bảo đảm TLS client thực hiện **endpoint identification** với hostname được mong đợi. Minh họa ngắn:

~~~java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;

// Socket phải được tạo từ SSLSocketFactory cấu hình
// TrustManager/KeyManager và trust store tin cậy.
static void requireHttpsIdentity(SSLSocket socket) {
    SSLParameters parameters = socket.getSSLParameters();
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(parameters);
    // Sau đó mới bắt đầu handshake trong luồng đúng.
}
~~~

**Hàm này không tự thêm revocation checker cho TLS stack**. Cấu hình **trust manager/PKIX validation, hostname verification, client certificate auth và revocation** phải được xem như một hệ thống thống nhất, rồi test handshake thật.

### 16.5. Không xây TrustManager vô điều kiện

Một cách sửa lỗi nguy hiểm:

~~~text
CA revocation service tạm thời không truy cập được
    -> developer thay X509TrustManager bằng accept-all
    -> mọi certificate đều được chấp nhận
~~~

Lúc này khả năng xác thực **issuer, hostname và revoked status** đều có thể mất. Khi cần availability, xây **HA/approved CRL cache/OCSP stapling/short-lived certs/DR** và đặt rõ soft-fail scope, không bỏ trọn PKIX validation.

## 17. Threat model: Rủi ro về certificate sau compromise/revocation

| Sai lầm / nguy cơ | Hậu quả | Biện pháp |
|---|---|---|
| **Chỉ kiểm tra certificate còn hạn** | Chấp nhận cert đã revoke | Path + revocation + SAN/EKU validation |
| **Chỉ verify chữ ký CA** | Trust sai issuer/identity/policy | Trusted path/anchors, constraints và endpoint identity |
| **Reissue bằng cùng keypair đã lộ** | Attacker vẫn biết private key của cert mới | Sinh keypair mới độc lập |
| **CA đánh dấu revoke nhưng CRL/OCSP chưa publish** | Clients vẫn chấp nhận cert cũ | Theo dõi publication, propagation và negative tests |
| **Tin OCSP good đã quá hạn** | Không nhận ra revoke sau thời điểm cache | thisUpdate/nextUpdate/max-age policy |
| **Coi OCSP unknown là good** | Chấp nhận certificate không có status xác thực | Default deny theo risk |
| **Không kiểm tra OCSP signature/issuer binding** | Attacker đưa response của cert khác | Verify responder authority và issuer+serial |
| **Soft-fail cho mọi lỗi, kể cả revoked** | Vô hiệu hóa mục đích revocation | Chỉ cân nhắc soft-fail cho lỗi xác định status trong policy |
| **Không kiểm tra Intermediate CA revocation** | Leaf chain tới CA compromised vẫn được nhận | PKIX chain checks theo profile |
| **Root CA compromised chỉ publish CRL** | Root còn trong trust anchors | Emergency distrust/trust-store update |
| **Pin leaf/SPKI cũ mà không có rollout path** | Không thể đổi keypair trong khẩn cấp | Backup pins/secure app update |
| **Không ngắt long-lived TLS/gRPC sessions** | Session cũ tiếp tục sau revoke | Session invalidation, restart/drain |
| **Không rotate workload tokens/KMS grants** | mTLS identity cũ còn dùng crypto APIs | IAM revoke + token/session cleanup |
| **KMS key vẫn Sign sau X.509 revoke** | Attacker dùng signing oracle | Disable/restrict key operations và audit |
| **Private key PEM trong image/CI log** | Nhiều bản sao raw material không kiểm soát | HSM/provider handle, secure enrollment, secret hygiene |
| **Tin CSR SAN do caller tự khai** | CA cấp certificate giả service khác | Authenticated enrollment + SAN policy |
| **Browser/client không dùng revocation** | Cert cũ được chấp nhận dù CA publish revoked | Relying party tests + emergency distrust |
| **Certificate mới dùng issuer không có trong trust store cũ** | Outage sau migration | Trusted chain distribution và client compatibility |
| **Tin public key từ JWT header x5c/kid tùy ý** | Algorithm/key substitution | Fixed issuer/trust source, allowlist |
| **Tự tin mọi chữ ký lịch sử sai sau revoke** | Từ chối artifacts hợp lệ, sai xử lý pháp lý | LTV, trusted timestamps, incident time |
| **Tự tin chữ ký lịch sử đúng vì verify toán học** | Chấp nhận chữ ký giả tạo lúc key đã lộ | Revocation/invalidity evidence và signing-time trust |
| **Không chống rollback firmware** | Attacker cài lại artifact cũ hợp lệ | Signed version/anti-rollback policy |
| **Revocation logs chứa private key/dump** | Tạo thêm key exposure | Metadata-only audit, protected forensics |
| **Chỉ test issuance, không test revoked handshake** | Hệ thống âm thầm không check revocation | Positive/negative integration tests |
| **Xóa CA/HSM key không có DR plan** | Không thể phát hành/revoke/verify theo nhu cầu | Key lifecycle, backup quorum và dependency review |
| **Không theo dõi expiry/revocation của mTLS cert** | Gãy toàn bộ service mesh khi hàng loạt cert hết hạn | Short-lived rotation automation/HA |

### 17.1. Vì sao OCSP good chưa đủ?

**GOOD** nghĩa responder **không báo revoked trong phạm vi thông tin đó**; nó không chứng minh:

- Private key chưa từng lộ.
- SAN/hostname được xác minh đúng.
- Certificate chain thuộc trust anchor được phép.
- Certificate có EKU/key usage đúng mục đích.
- Caller có quyền dùng KMS Sign/Decrypt.
- Response đủ mới để áp dụng tại thời điểm hiện tại.

Đặc biệt, một response good có thể được tạo **trước khi CA phát hiện compromise**, sau đó vẫn nằm trong cache. **Revocation latency** là thành phần của threat model.

### 17.2. Vì sao PKIX valid chưa đủ cho authorization?

Một mTLS identity **customer-reader** có thể sở hữu certificate hợp lệ do internal CA cấp. Nhưng certificate đó **không xác định record nào reader được phép Decrypt**. Để tránh confused deputy:

~~~text
TLS/PKIX:
    Identity = customer-reader (trusted)

Application:
    Caller có được xem record tenant-A/invoice-123?

KMS:
    customer-reader có Unwrap grant đúng KEK/tenant?

Audit:
    Identity + recordRef + keyRef + action + decision
~~~

**Certificate là bằng chứng danh tính trong một trust domain, không phải quyền vô hạn với mọi tài nguyên**.

### 17.3. “Thu hồi” có ba mức thời gian

Đối với một cert bị compromise, đo:

1. **Administrative revocation:** CA đã chấp nhận request và ghi status.
2. **Published revocation:** CRL/OCSP có status mới với freshness đúng.
3. **Effective relying-party rejection:** những clients quan trọng thực sự từ chối cert cũ; sessions/tokens liên quan đã được xử lý.

Chỉ có mức 3 mới cung cấp bằng chứng thực tế rằng đường xác thực mục tiêu đã bị chặn tại những clients được kiểm thử. **Không thể chứng minh tuyệt đối mọi thiết bị offline đã cập nhật nếu không có kênh kiểm soát/quan sát thích hợp**.

## 18. Ma trận kiểm thử certificate revocation và compromise

### 18.1. Positive/negative tests cho một TLS server

| Test | Kỳ vọng | Điều được chứng minh |
|---|---|---|
| Valid server cert, đúng SAN, đúng EKU, trusted chain, GOOD status | **ALLOW** | Đường xác thực chuẩn |
| Cert còn hạn nhưng issuer báo REVOKED | **DENY** | Revocation được thực thi |
| Cert đã quá notAfter, OCSP vẫn GOOD | **DENY** | Validity độc lập status |
| Cert chưa tới notBefore | **DENY** | Chưa được phép có hiệu lực |
| Cert có SAN khác hostname mong đợi | **DENY** | Endpoint identification |
| Cert có clientAuth EKU nhưng không đáp ứng server profile | **DENY theo TLS profile** | Purpose/usage |
| Cert ký bởi CA không thuộc approved truststore | **DENY** | Trust anchor |
| Intermediate CA revoked | **DENY theo chain policy** | CA-path revocation |
| OCSP trả UNKNOWN | **DENY theo high-risk policy** | Không nhầm unknown với good |
| OCSP unreachable | **Fail-closed hoặc approved soft-fail** | Tính sẵn sàng vs security |
| OCSP GOOD nhưng response quá hạn | **DENY nếu không còn nguồn status hợp lệ** | Freshness |
| Stapled OCSP response của cert serial khác | **DENY** | Issuer+serial binding |
| CRL signature/issuer không hợp lệ | **DENY/retry nguồn tin cậy** | CRL authenticity |
| Cert revoked nhưng existing HTTP/2 channel còn sống | **Đóng channel theo incident policy** | Session invalidation |
| Cert mới active nhưng client pin SPKI cũ | **Fail trước khi update pin**; sau update phải pass | Pin migration |
| Certificate keypair mới deploy lên một pod, pod cũ vẫn còn | **Phát hiện pod stale** | Fleet-wide rollout |
| Attacker biết key ID/public cert nhưng không có private key | **Không thể chứng minh peer possession** | Proof-of-possession |

**Không chỉ cần một unit test gọi certificate.checkValidity().** Bảo đảm thật cần **TLS handshake** với chain, truststore, status sources và client implementations được hỗ trợ.

### 18.2. Positive/negative tests cho mTLS

| Test | Kỳ vọng |
|---|---|
| Client cert hợp lệ, SAN billing-service, route được cấp quyền | Cho gọi API đúng scope |
| Client cert của analytics-service gọi Billing KMS Sign | Từ chối business/IAM policy |
| Billing client cert bị revoke | Từ chối handshake/credential mới khi revocation enforce |
| Billing service nhận cert mới, token cũ chưa revoke | Phát hiện và xử lý token/session theo incident |
| Client cert có SAN sai tenant/trust domain | Từ chối |
| Certificate hợp lệ nhưng caller yêu cầu đọc record tenant khác | Từ chối trước KMS Unwrap |
| Service mesh giữ connection dài sau revoke | Có cơ chế terminate/drain/re-authenticate |
| Identity issuer CA bị compromised | Cô lập trust domain, không chỉ revoke một leaf |

### 18.3. Tests cho Code/Document Signing

Để kiểm tra chữ ký dài hạn:

1. Artifact ký **trước key compromise**, có trusted timestamp và đầy đủ revocation evidence.
2. Artifact có timestamp **tự khai** nhưng thiếu trusted time evidence.
3. Artifact có chữ ký toán học hợp lệ nhưng signer certificate đã bị revoke do **keyCompromise**, thời điểm compromise được suy ra từ evidence.
4. Artifact được ký bởi key mới và certificate mới được trust store chấp nhận.
5. Artifact mang certificate chain đi tới issuer bị distrust.
6. Legacy verifier không kiểm tra revocation và còn chấp nhận malicious artifact.
7. Firmware updater có **monotonic version** ngăn rollback artifact cũ hợp lệ theo chữ ký.

Kỳ vọng **không phải “mọi chữ ký cũ đều sai” hoặc “mọi chữ ký cũ đều đúng”**; kết quả theo **validation policy, trusted time, revocation/invalidity evidence và mục đích ký**.

### 18.4. Cần kiểm thử những mạng/thiết bị nào?

- Chrome/Firefox/Safari hoặc platform browsers thuộc môi trường hỗ trợ, với hành vi revocation thực tế của chúng.
- Java 17 JSSE client dùng **truststore mặc định** và **truststore doanh nghiệp tùy chỉnh**.
- API gateway, reverse proxy, load balancer, service mesh sidecar.
- Microservices mTLS, gRPC/HTTP2 channels, connection pools.
- Mobile app và IoT devices, có hoặc không có kết nối OCSP live.
- Clients dùng SPKI/CA pinning hoặc đóng gói certificate trong ứng dụng.
- Build/release/signature verifiers và firmware updaters.
- KMS/HSM consumers hoặc agents phụ thuộc một mTLS certificate.

Một tập test nên có cả **certificate đã revoked thật trong test CA**, **OCSP/CRL outage**, **stale GOOD response** và **truststore chưa cập nhật**. Không thử revocation bằng cách tắt đồng hồ hệ thống production hoặc đưa private key thật vào test fixtures.

## 19. Case study: Phát hiện TLS certificate private key bị lộ

### 19.1. Bối cảnh

Một doanh nghiệp có:

~~~text
Internet clients --TLS--> api-gateway.example.net
                              |
                              +--mTLS--> billing-service
                              +--mTLS--> customer-reader

Certificates:
  Gateway leaf: issuer public-intermediate, serial A100
  Billing mTLS leaf: issuer internal-ca-1, serial B500
  Customer mTLS leaf: issuer internal-ca-1, serial C800

Crypto keys:
  Gateway TLS private key in protected volume
  Billing signing private key in HSM
  Customer DEK/KEK in KMS
~~~

Trong một lần debug, developer copy một **PKCS#12 bundle** từ gateway và đính kèm vào hệ thống ticket nội bộ có quyền đọc rộng. Bundle và password cùng nằm trong một file script; đội an ninh phát hiện nó có thể đã bị tải xuống. Certificate Gateway serial A100 còn hạn ba tháng.

### 19.2. Phản ứng sai

~~~text
1. Xin CA cấp certificate mới cho cùng keypair A100.
2. Deploy certificate mới lên gateway.
3. Không revoke A100 vì sợ làm client cũ lỗi.
4. Không thay TLS ticket/session credentials.
5. Đóng ticket với lý do "certificate renewed".
~~~

**Vì sao sai?** Bản private key đã có thể bị lấy. Chứng thư mới trên cùng keypair **không sửa secret compromise**. Certificate A100 còn hạn và không revoked có thể tiếp tục được chấp nhận; long-lived sessions và private key copies chưa được xử lý.

### 19.3. Quy trình đúng hơn

**Giai đoạn 1 — Contain**

- Hạn chế quyền download ticket/artifact, bảo toàn forensic evidence trong nơi an toàn.
- Cô lập gateway key/credential và đánh giá hệ thống/tài khoản đã truy cập bundle.
- Thu hồi session/CI/administrator credentials liên quan nếu có.
- Xem xét traffic capture, DNS/route controls, TLS termination points và session tickets.

**Giai đoạn 2 — Replace**

- Tạo **gateway TLS private key mới độc lập** trong boundary được phê duyệt.
- Tạo CSR, CA xác minh SAN **api-gateway.example.net** và issue leaf mới.
- Deploy certificate mới trên tất cả edge nodes/load balancers; verify chain, SAN, EKU và status.
- Cập nhật key pins/trust consumers nếu có; không tắt hostname checks.

**Giai đoạn 3 — Revoke**

- Gửi yêu cầu revoke **issuer public-intermediate + serial A100**, reason keyCompromise phù hợp với evidence.
- Xác minh CRL/OCSP publish revocation và không còn GOOD evidence hợp lệ cho client kiểm tra theo policy.
- Kiểm tra clients chủ chốt thực sự **từ chối A100**; đánh giá emergency distrust nếu CRL/OCSP không đủ nhanh.

**Giai đoạn 4 — Invalidate and monitor**

- Đóng/recreate connections và TLS sessions theo incident plan.
- Thu hồi hoặc đổi credentials khác có thể bị ảnh hưởng do host compromise.
- Đối soát HSM/KMS grants để chắc chắn Gateway incident **không tự mở quyền dùng Billing Sign hoặc Customer KEK**.
- Audit lỗi handshake, OCSP/CRL cache, cert rotation lag và new certificate success.

### 19.4. Một điều tra khác: Billing mTLS certificate cũng bị lộ

Nếu attacker chỉ lấy private key **Gateway TLS**, **không mặc nhiên** suy ra Billing HSM signing private key đã lộ. Nhưng nếu attacker có thể sử dụng Gateway làm điểm tấn công nội bộ, cần kiểm tra:

- Billing mTLS private key có nằm trong cùng host/volume không?
- Gateway có authority để gọi Billing Sign API hoặc customer Decrypt API không?
- IAM role/KMS grants nào có thể bị lợi dụng?
- Audit có chữ ký hoặc KMS Unwrap ngoài traffic bình thường?
- Các tokens nội bộ có thể đã được Gateway tạo hoặc cache?

**Phải đánh giá scope theo trust boundary và operations thực tế**, không coi tất cả secrets toàn công ty đều cùng bị lộ; cũng không chỉ sửa TLS leaf rồi bỏ qua credential liên quan trên host bị chiếm.

### 19.5. Mở rộng tình huống: Internal Intermediate CA bị compromise

Nếu **internal-ca-1** private key lộ, cả Billing và Customer mTLS trust domain có thể chịu ảnh hưởng. Kế hoạch:

1. Stop certificate issuance từ CA cũ.
2. Revoke/distrust Intermediate certificate theo CA hierarchy và client capabilities.
3. Tạo CA hierarchy hoặc Intermediate mới dưới approved root/key custodian.
4. Re-enroll all affected workload certificates theo authenticated identity, không tin SAN self-asserted.
5. Update service mesh trust bundles, Java truststores, gateway trust stores và offline devices.
6. Test **new CA accepted / old CA denied**, cả new và resumed mTLS sessions.
7. Đánh giá KMS/IAM grants gắn với identity cũ; không để một certificate giả có thể yêu cầu Unwrap/Sign toàn tenant.
8. Rà issuance logs, mis-issued certificates và CT/private-PKI monitoring.

Trong sự cố Intermediate CA, **chỉ revoke một leaf** không đủ để ngăn issuer bị chiếm cấp thêm leaf mới.

## 20. Audit, monitoring và evidence sau revocation

### 20.1. Những sự kiện nên ghi

| Event | Metadata cần ghi | Không ghi |
|---|---|---|
| **Suspected key compromise** | KeyRef, certificate fingerprint, issuer, serial, timestamp, scope | Raw private key, HSM shares |
| **Certificate revocation request** | CA, serial, reason, actor, approval, incident ID | PIN, OCSP responder private key |
| **Revocation published** | CRL number/thisUpdate/nextUpdate, OCSP response metadata, publish time | Full unrelated customer data |
| **Keypair/certificate reissue** | New keyRef/fingerprint, SAN/EKU, issuer, validity, CSR enrollment ID | Raw private key/CSR signing secret |
| **Old key disabled** | KMS/HSM key ID, IAM grants, effective time, request result | Private key export |
| **Trust store update** | Client fleet/version, issuer add/remove, rollout and test results | Unprotected admin credentials |
| **Session invalidation** | Service, ticket/session category, cutoff time, outcome | Sensitive session tokens |
| **Historical signature review** | ArtifactRef, trust policy, timestamp/evidence status | Confidential artifact contents beyond need |
| **Break-glass** | Approvers, scope, expiry, incident ID, post-review | Shared emergency password |

Audit có thể chứa **hostnames, identity, CA topology và certificate serials** nên cần bảo vệ confidentiality/integrity và retention. Người có quyền thay CA policy **không nên tự xóa audit không để lại dấu vết**.

### 20.2. Các chỉ số hữu ích

- **Time to revoke:** từ detect đến CA nhận yêu cầu, từ publish đến client thực sự từ chối.
- **Fleet certificate rollout coverage:** phần trăm endpoints dùng keypair/cert mới.
- **Unrevoked compromised certificates:** các cert còn active nhưng incident cho biết private key đã lộ.
- **CRL/OCSP publication age và response errors**, stale-good rate theo client.
- **PKIX handshake rejects** theo invalid chain, wrong SAN, expired, revoked, status unknown và unreachable.
- **Sessions/long-lived channels chưa được terminate** sau incident cutoff.
- **Trust stores chứa issuer bị distrust** và mức độ cập nhật theo region/device.
- **Certificates nearing expiration** và tỷ lệ renewal failures.
- **Keypairs có thể export raw material** ngoài policy.
- **KMS/HSM operations trên key handles bị ảnh hưởng** trong compromise interval.
- **Documents/artifacts cần historical signature validation**.
- **Orphan certificate/key inventory entries**, thiếu owner, không có renewal/revocation plan.
- **CA issuance anomalies** và số cert được cấp cho SAN không thuộc workload identity.

**Không có OCSP errors không có nghĩa client có bật OCSP checks**. Một client không bao giờ gọi responder có thể tạo ra zero logs nhưng vẫn chấp nhận certificate revoked; cần **negative test thực tế**.

### 20.3. Incident acceptance criteria

Đóng incident chỉ khi có evidence phù hợp:

1. **Old certificate revoked/distrusted** tại nguồn CA và các relying parties trọng yếu.
2. **New keypair/certificate** đã deploy, đúng identity/EKU và kết nối hợp pháp hoạt động.
3. **Old KMS/HSM key and grants** đã bị hạn chế hoặc xử lý theo policy.
4. **Relevant sessions/tokens** đã bị thu hồi/đổi theo phạm vi sự cố.
5. **CRL/OCSP freshness** và caching đã được kiểm tra bằng test cert cũ.
6. **Signer/recipient trust impact** cho documents/JWT/code signing đã được đánh giá.
7. **Remaining offline/pinned clients** được liệt kê rõ và có mitigation/owner.
8. **Root cause** được giải quyết: key export, CI artifacts, credentials, HSM permissions, CA enrollment hoặc host isolation.

## 21. Checklist ảnh hưởng đến certificate trước khi vận hành

1. **Key identity:** Mỗi certificate có issuer, serial, fingerprint, SAN/EKU, keyRef và owner được kiểm soát?
2. **Public vs private:** Có phân biệt certificate public với private key/KeyStore secret cần bảo vệ?
3. **Trust roots:** Mỗi relying party có danh sách approved trust anchors và cách cập nhật an toàn?
4. **Path validation:** Có kiểm tra issuer chain, signature, BasicConstraints, name constraints và algorithm policy phù hợp?
5. **Hostname/SAN:** Client có thực sự kiểm tra endpoint identity, không chỉ certificate signature?
6. **KeyUsage/EKU:** Certificate chỉ được dùng cho profile TLS server, mTLS client, code signing hoặc document signing đã phê duyệt?
7. **Proof of possession:** Peer phải chứng minh kiểm soát private key tương ứng theo giao thức?
8. **Certificate validity:** notBefore/notAfter được kiểm tra với thời gian tin cậy và clock skew policy?
9. **CRL/OCSP:** Relying party có cơ chế status checking phù hợp với risk, không chỉ check expiry?
10. **Issuer–serial binding:** CRL/OCSP evidence có đúng certificate/issuer và signer authority?
11. **Freshness:** Có giới hạn response age, thisUpdate/nextUpdate, stale cache và fallback?
12. **Revoked vs unknown:** Có phân biệt explicit REVOKED, UNKNOWN, responder unreachable và invalid response?
13. **Soft-fail:** Chỉ được dùng khi threat model cho phép; không chấp nhận explicit revoked?
14. **Stapling:** TLS stack/client có hỗ trợ và kiểm tra stapled status thực tế, không chỉ bật cờ server?
15. **Client inventory:** Biết browsers, Java truststores, API proxies, service mesh, mobile và offline devices nào dùng certificate?
16. **Root compromise:** Có emergency distrust/trust-anchor update plan ngoài CRL/OCSP?
17. **Intermediate compromise:** Có đường reissue leaf và thay issuer hierarchy theo trust constraints?
18. **No key reuse after compromise:** Không reissue certificate mới trên private key đã có thể bị lộ?
19. **HSM/KMS:** Key handle, exportability, KMS Sign grants và provider audit được kiểm tra riêng với X.509 status?
20. **No hardcoded keys:** Không nhúng PKCS#12/PEM/private key vào Git, image, CI logs hoặc ticket?
21. **Enrollment:** CSR SAN/subject có được xác thực dựa trên workload identity chứ không chỉ requester self-asserted?
22. **Routine renewal:** Có overlap/rollout policy mà không kéo dài compromised key acceptance?
23. **Short-lived certs:** Có renewal HA, clock handling và emergency revoke/distrust plan khi key lộ?
24. **TLS sessions:** Long-lived connections, session resumption và ticket secrets được xử lý sau revocation?
25. **mTLS to IAM:** Access tokens, service identity và KMS grants liên quan được thu hồi/đánh giá lại?
26. **Application authorization:** Certificate hợp lệ không tự mở quyền đọc cross-tenant, Sign hoặc Decrypt?
27. **Pinning:** Có backup pins/secure update để thay keypair/CA khi compromise?
28. **Truststore migration:** Đã test CA cũ bị từ chối và CA mới được nhận trên mọi client quan trọng?
29. **CT/issuance audit:** Có giám sát mis-issuance đúng PKI profile, không dùng CT thay OCSP/CRL?
30. **Document signatures:** Có phân biệt crypto verification với trust-at-time, trusted timestamps và revocation evidence?
31. **JWT/JWS:** Không tin key từ header tùy ý; có issuer/audience/expiry/signature/algorithm allowlist?
32. **Code signing:** Artifact/release authenticity có thêm version/anti-rollback và approval policy?
33. **CRL publication:** CA công bố signed CRLs đúng cadence; delta/partition/indirect semantics được validator hỗ trợ?
34. **OCSP publication:** Responder signing authority, freshness, outage behavior được diễn tập?
35. **New certificate test:** Có positive handshake/authentication và certificate mới hoạt động đủ coverage?
36. **Old certificate test:** Có negative handshake thật với certificate revoked cũ, không chỉ API response 200?
37. **Timing evidence:** Có T_detected/T_revocation_requested/T_status_published/T_clients_reject_old?
38. **Compromise reason:** Có phân loại keyCompromise, cACompromise, superseded, certificateHold... đúng hồ sơ?
39. **Invalidity date:** Đã đánh giá compromise interval khi cần xử lý các chữ ký lịch sử?
40. **Backup:** Copies của private key cũ, archived certs, HSM backup/recovery được rà theo policy?
41. **Logs:** Có actor, issuer/serial, keyRef, CA status, effective time, policy revision mà không ghi private key?
42. **Separation of duties:** CA operator, HSM custodian, incident commander và auditor có quyền tách biệt?
43. **DR:** Khi CA/OCSP/IdP outage, có approved HA/DR thay vì accept-all TrustManager?
44. **Certificate inventory:** Có owner, expiry monitoring, issuer/SAN tracking, revocation status và client dependencies?
45. **Final acceptance:** Có bằng chứng **old credential không còn được chấp nhận**, **new credential hoạt động** và **các quyền/tokens phụ thuộc đã được xử lý**?

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Certificate TLS còn hạn nhưng private key đã lộ, liệu có thể coi kết nối an toàn vì chữ ký CA vẫn verify?

**Trả lời:** **Không.** Attacker có thể sử dụng private key để impersonate trong những điều kiện thích hợp. Cần cô lập, keypair/certificate mới, revoke certificate cũ, cập nhật relying parties và kiểm tra sessions.

**Câu 2.** Revoke một certificate có xóa được private key đã bị copy ra ngoài không?

**Trả lời:** **Không.** Revocation là tín hiệu trust tới relying parties, không có khả năng xóa các bản sao raw key. Phải xử lý key material, IAM và credentials riêng.

**Câu 3.** Certificate expiration khác certificate revocation thế nào?

**Trả lời:** Expiration là kết thúc validity ghi trong chứng thư; revocation là việc certificate không còn được tin **trước notAfter** theo issuer/trust policy. Một certificate expired không nhất thiết đã nằm trong CRL.

**Câu 4.** Tại sao không nên reissue certificate mới trên cùng keypair bị compromise?

**Trả lời:** Vì attacker vẫn biết private key. Cần sinh keypair độc lập và enrollment/certificate mới.

**Câu 5.** Certificate có chữ ký CA đúng có tự chứng minh service có hostname mong đợi không?

**Trả lời:** **Không.** Cần kiểm tra SAN/endpoint identification, trust chain, KeyUsage/EKU, thời hạn và trạng thái revocation.

**Câu 6.** OCSP GOOD có chứng minh private key an toàn tuyệt đối không?

**Trả lời:** **Không.** Nó phản ánh trạng thái revocation được responder công bố tại thời điểm liên quan, không phát hiện mọi vụ lộ private key chưa được báo cáo.

**Câu 7.** OCSP UNKNOWN và OCSP responder timeout có giống nhau không?

**Trả lời:** **Không.** UNKNOWN là một trạng thái certificate trả về; timeout là failure không lấy được response đáng tin. Policy có thể đều từ chối nhưng phân loại/audit khác nhau.

**Câu 8.** Có nên chấp nhận OCSP response GOOD đã quá nextUpdate vì chữ ký số OCSP vẫn hợp lệ?

**Trả lời:** **Không nên** nếu freshness policy yêu cầu status mới. OCSP signature chỉ chứng minh response được ký, không làm thông tin hết hạn trở thành mới.

**Câu 9.** OCSP stapling có bảo đảm mọi browser/client thực sự kiểm tra revocation không?

**Trả lời:** **Không.** Cần xác minh TLS stack, client policy, stapled-response validation và cached status.

**Câu 10.** Fail-open nên xử lý thế nào nếu OCSP đã trả về REVOKED một cách xác thực?

**Trả lời:** **Từ chối.** Soft-fail chỉ có thể được cân nhắc cho một số lỗi không xác định status theo policy, không dùng để override explicit revoked.

**Câu 11.** Vì sao Root CA compromise không được giải quyết hoàn toàn bằng một CRL thông thường?

**Trả lời:** Root certificate thường là trust anchor được cài sẵn, không có issuer cao hơn trong path thông thường để revoke root theo cách relying party tự động xử lý. Cần emergency distrust/trust-store migration.

**Câu 12.** Intermediate CA compromise có thể ảnh hưởng những leaf nào?

**Trả lời:** Những certificates/path mà Intermediate đó có thể phát hành và relying parties có thể chấp nhận. Cần xem chain constraints, cross-signing, trust roots và issuance evidence.

**Câu 13.** Revoke mTLS client certificate có tự thu hồi access tokens hoặc KMS Sign/Decrypt grants đã cấp cho service không?

**Trả lời:** **Không.** Token/session/IAM lifecycle độc lập; phải xử lý theo scope sự cố.

**Câu 14.** Một TLS connection đã mở có tự đóng ngay lúc CA publish CRL mới không?

**Trả lời:** **Không nhất thiết.** Session resumption, persistent channels và application identity caching có thể cần terminate/re-authenticate.

**Câu 15.** Lộ private authentication key trong TLS 1.3 có tự giải mã được mọi traffic lịch sử được capture không?

**Trả lời:** **Không tự động.** Khi key exchange bảo đảm forward secrecy và session secrets không lộ, khả năng giải mã traffic lịch sử không xuất hiện chỉ từ private signing key. Nhưng impersonation và host/session compromise vẫn nghiêm trọng.

**Câu 16.** Vì sao PKIX path validation phải kiểm tra EKU và SAN ngoài chữ ký issuer?

**Trả lời:** Certificate có thể được CA ký đúng nhưng dùng cho **mục đích hoặc identity khác**. Trust phải gắn với đúng profile và endpoint.

**Câu 17.** Trong Java, chỉ gọi X509Certificate.checkValidity() có đủ ngăn certificate revoked không?

**Trả lời:** **Không.** checkValidity kiểm tra notBefore/notAfter; cần revocation checker/path validation và endpoint identity theo cấu hình.

**Câu 18.** Nếu CertPathValidator.validate thành công, application có được tự động Decrypt dữ liệu tenant khác không?

**Trả lời:** **Không.** Certificate validation chứng minh identity/trust theo PKI; business resource authorization và KMS IAM vẫn phải kiểm tra riêng.

**Câu 19.** Một certificate mới đã deploy nhưng client vẫn pin public key cũ, chuyện gì có thể xảy ra?

**Trả lời:** Client có thể từ chối kết nối mới. Cần update pins/trust qua kênh an toàn hoặc backup pin được chuẩn bị trước, không tiếp tục dùng compromised key.

**Câu 20.** RevocationDate và InvalidityDate có thể khác nhau không?

**Trả lời:** **Có.** RevocationDate phản ánh thời điểm revocation được ghi; invalidityDate có thể thể hiện thời điểm được cho rằng certificate/key không còn tin cậy. Xử lý chữ ký lịch sử cần xem evidence, không chỉ chọn một mốc thuận tiện.

**Câu 21.** Certificate bị revoke thì tất cả chữ ký tài liệu được tạo từ nhiều năm trước đều sai toán học?

**Trả lời:** **Không.** Signature verification có thể vẫn thành công. Tin cậy pháp lý/nghiệp vụ cần xét thời điểm ký, compromise interval, trusted timestamp, revocation evidence và validation policy.

**Câu 22.** Có thể giữ private signing key cũ để Verify những chữ ký cũ không?

**Trả lời:** Với các scheme chữ ký bất đối xứng phù hợp, **public key** đủ để Verify. Không cần giữ quyền Sign/private key chỉ để xác minh chữ ký lịch sử.

**Câu 23.** Vì sao CA status publish thành công chưa đủ đóng incident?

**Trả lời:** Relying parties có thể cache trạng thái cũ hoặc không kiểm tra revocation, sessions vẫn sống. Cần kiểm chứng **old rejected/new accepted** và xử lý tokens/IAM.

**Câu 24.** Certificate Transparency có tự cho biết một certificate đang revoked không?

**Trả lời:** **Không.** CT hỗ trợ transparency về issuance trong phạm vi phù hợp; revocation cần CRL/OCSP/trust policy và relying-party validation.

**Câu 25.** Short-lived certificate có thay hoàn toàn nhu cầu response khi private key lộ không?

**Trả lời:** **Không.** Nó giảm khoảng thời gian credential còn hợp lệ nhưng không làm private key đã bị đánh cắp biến mất, không chặn issuer compromise và không tự ngắt sessions.

**Câu 26.** Nếu KeyStore PKCS#12 đã được mã hóa bằng password nhưng cả file và password cùng bị lộ, mức rủi ro thế nào?

**Trả lời:** Private key trong bundle có thể bị giải mã; cần đánh giá như **raw private-key exposure** trong scope thực tế, rotate keypair và revoke certificate theo incident procedure.

**Câu 27.** Nếu HSM giữ private key non-exportable, có thể chắc chắn không xảy ra chữ ký giả không?

**Trả lời:** **Không.** Attacker có quyền gọi HSM Sign vẫn có thể lạm dụng như signing oracle. Cần operation grants, business approval và audit.

**Câu 28.** Câu nào đúng: “CA đã revoke” hay “mọi relying party đã từ chối certificate”?

**Trả lời:** Đây là **hai mệnh đề khác nhau**. Để chứng minh thực thi, cần test clients và ghi nhận effective rejection/propagation.

**Câu 29.** Một leaf certificate mới do Intermediate mới ký đã có thể dùng ngay trên IoT offline clients tin Root cũ không?

**Trả lời:** **Chưa chắc.** Phụ thuộc trust anchor/path constraints, cache, firmware, cross-signing và khả năng cập nhật chain/trust store của từng client.

**Câu 30.** Khi PKIX status service outage, có nên thay toàn bộ JSSE TrustManager bằng accept-all để giữ availability?

**Trả lời:** **Không.** Điều đó có thể bỏ qua cả chain/identity/revocation checks. Cần approved HA/cache/fallback hoặc fail-closed theo threat model, không disable trust validation.

## 23. Tổng kết

**Certificate không phải vật chứa private key**, mà là một chứng nhận tin cậy liên kết **public key với identity, issuer, usage và validity**. Khi private key hoặc CA key bị compromise, **certificate vẫn có thể hợp lệ về chữ ký và thời hạn**, nhưng relying parties cần được thông báo và thực sự **ngừng tin credential bị ảnh hưởng** theo security policy.

Những nguyên tắc trọng tâm:

- **Revoke khác rotate, expire và destroy:** revoke làm relying parties ngừng tin certificate; rotate thay material; expire kết thúc validity; disable/destroy KMS key và revoke tokens/sessions có cơ chế riêng.
- **PKI validation là nhiều lớp:** chain/trust anchor, SAN/endpoint identity, KeyUsage/EKU, thời gian, CRL/OCSP freshness và business authorization.
- **Revocation cần kiểm chứng sự lan truyền:** CA publish status chưa chứng minh mọi client, proxy, mesh hoặc session đã ngừng chấp nhận certificate cũ.
- **Compromise scope phụ thuộc loại khóa:** TLS leaf, mTLS client, signing key, Intermediate CA và Root CA có blast radius khác nhau.
- **Chìa khóa mới phải độc lập khi khóa cũ đã lộ:** không reissue trên raw material bị compromise; chuẩn bị trust-store/pinning migration và key separation.
- **Chữ ký lịch sử cần đánh giá theo thời điểm và bằng chứng:** crypto Verify đúng không đồng nghĩa trust-at-time đã đủ; cần timestamp, revocation/invalidity evidence và policy phù hợp.
- **KMS/HSM, IAM và audit bổ trợ PKI:** certificate revocation không tự cắt signing oracle, cached tokens hoặc dữ liệu đã giải mã.

**Điểm cốt lõi:** Khi khóa bị compromise, mục tiêu không chỉ là **đổi certificate trong server**, mà là **đưa các relying parties từ trạng thái tin credential cũ sang tin credential mới một cách kiểm chứng được**, đồng thời thu hồi những quyền và phiên liên quan, điều tra phạm vi lạm dụng và duy trì bằng chứng để kiểm toán.
