# CRL: Certificate Revocation List và cách kiểm tra chứng thư bị thu hồi

Một API gateway nhận certificate TLS của một service nội bộ. Certificate có chữ ký CA hợp lệ, hostname đúng và vẫn còn hạn. Nhưng private key tương ứng đã bị lộ trong một bản backup cũ. CA đã ghi nhận thu hồi certificate, còn một số client vẫn đang cache danh sách thu hồi từ hôm trước. Nếu chỉ kiểm tra chữ ký certificate và thời hạn, các client đó có thể tiếp tục chấp nhận một danh tính không còn đáng tin.

**Certificate Revocation List (CRL)** là cơ chế PKI dùng để công bố danh sách certificate đã bị thu hồi. CA hoặc một CRL issuer được ủy quyền ký danh sách này; relying party tải CRL, xác minh chữ ký/phạm vi/thời gian và kiểm tra serial của certificate cần xác thực. Nếu certificate nằm trong CRL áp dụng, validator từ chối theo policy.

CRL không phải một danh sách serial đơn giản. Nó có **issuer, thisUpdate, nextUpdate, CRL number, authority key identifier, issuing distribution point, reason codes và chữ ký số**. Một CRL chỉ có ý nghĩa khi đúng issuer, đúng scope, còn mới, có chữ ký hợp lệ và được xử lý theo quy tắc PKIX. Với delta hoặc indirect CRL, validator còn phải ghép đúng base CRL và hiểu issuer của từng entry.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học kết nối certificate/public key với vòng đời khóa, chữ ký số, KMS/HSM, kiểm soát truy cập và kiểm toán. Mục tiêu là hiểu cách CA công bố trạng thái thu hồi và cách ứng dụng quyết định có tiếp tục tin certificate hay không, đặc biệt khi **private key bị compromise, certificate hết hạn, CA bị thu hồi hoặc hệ thống kiểm tra trạng thái gặp sự cố**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **CRL** trong PKI/X.509 và phân biệt CRL với certificate, OCSP, trust store và certificate transparency.
2. Đọc các trường quan trọng trong CRL: **issuer, thisUpdate, nextUpdate, revokedCertificates, CRL number và signature**.
3. Giải thích vì sao serial number phải được đối chiếu cùng **issuer** và CRL scope.
4. Phân biệt **base/full CRL, delta CRL, indirect CRL và partitioned CRL**.
5. Xác minh chữ ký CRL, CRL issuer, KeyUsage cRLSign, Authority Key Identifier và freshness.
6. Hiểu các **CRL Distribution Points (CDP)**, Freshest CRL, reason codes và invalidityDate.
7. Phân biệt **revocationDate, invalidityDate và removeFromCRL**.
8. Đánh giá độ trễ do publication cadence, caching, stale CRL và client behavior.
9. Cấu hình kiểm tra CRL trong Java 17 bằng **PKIXRevocationChecker và CertStore**, hiểu ranh giới với hostname và business authorization.
10. Thiết kế runbook CA revoke/publish, kiểm thử positive/negative, monitoring và audit evidence.

## 2. CRL nằm ở đâu trong PKI?

### 2.1. Certificate và CRL giải quyết hai câu hỏi khác nhau

**X.509 certificate** do CA ký, liên kết public key với identity, validity và usage constraints. **CRL** do issuer/CRL issuer ký, công bố các certificate bị thu hồi trong một phạm vi.

| Đối tượng | Nội dung | Mục đích |
|---|---|---|
| **Certificate** | Subject/SAN, public key, issuer, serial, validity, KeyUsage/EKU, CA signature | Chứng minh liên kết public key với identity theo CA |
| **CRL** | Issuer, thời gian cập nhật, serial bị thu hồi, reason và CRL signature | Công bố certificate không còn được tin |
| **Trust store** | Trust anchors và có thể có trust policy | Xác định CA/path nào được tin |
| **OCSP response** | Trạng thái cho một certificate cụ thể | Hỏi trạng thái online |
| **Certificate Transparency log** | Bằng chứng công khai về issuance trong phạm vi áp dụng | Phát hiện mis-issuance; không phải danh sách revocation |

Một certificate có thể:

- Có chữ ký CA hợp lệ.
- Có hostname/SAN đúng.
- Chưa hết hạn.
- Nhưng vẫn **đã bị revoke**.

Vì vậy, chữ ký certificate và validity period chưa đủ để kết luận certificate được phép sử dụng.

### 2.2. CRL trong chuỗi tin cậy

~~~mermaid
flowchart TD
    R["Root CA / Trust anchor"] --> I["Intermediate CA"]
    I --> L["Leaf certificate"]
    I --> CRL["CRL do issuer hoặc CRL issuer ký"]
    L --> V["Relying party / PKIX validator"]
    CRL --> V
    R --> V
    I --> V
    V --> D{"Path, identity, validity và revocation hợp lệ?"}
    D -->|"Có"| A["Tiếp tục xác thực peer"]
    D -->|"Không"| X["Từ chối theo policy"]
~~~

Relying party cần biết:

1. Certificate thuộc issuer nào?
2. CRL nào áp dụng cho certificate này?
3. CRL có chữ ký hợp lệ và đúng CRL issuer không?
4. CRL còn mới và bao phủ certificate không?
5. Serial có nằm trong revoked entries không?
6. Các critical extensions và scope có được validator hỗ trợ không?

CRL là một phần của **certificate path validation**. Nó không thay thế trust anchor, hostname/SAN, KeyUsage/EKU, thời hạn hay authorization nghiệp vụ.

### 2.3. Vì sao CRL quan trọng với key management?

Khi private key của leaf certificate bị lộ, attacker có thể cố chứng minh sở hữu private key đó. CA cần thu hồi certificate gắn với public key đã bị ảnh hưởng. CRL giúp relying parties biết serial đó không còn được chấp nhận.

Khi private key của **Intermediate CA** bị compromise, việc thu hồi Intermediate certificate có thể ảnh hưởng toàn bộ đường dẫn dưới CA đó. Khi **Root CA** bị compromise, trust anchor thường phải được distrust/cập nhật qua trust store; một CRL thông thường không tự gỡ root khỏi mọi client.

**CRL chỉ truyền thông tin trạng thái.** Nó không xóa private key bị đánh cắp, không tự đóng TLS sessions, không thu hồi KMS grants và không làm mất các bản plaintext đã bị attacker lấy.

## 3. Cấu trúc CRL theo X.509

### 3.1. CertificateList và TBSCertList

Một CRL X.509 có cấu trúc khái quát:

~~~text
CertificateList ::= SEQUENCE {
    tbsCertList          TBSCertList,
    signatureAlgorithm   AlgorithmIdentifier,
    signatureValue       BIT STRING
}

TBSCertList ::= SEQUENCE {
    version              Version OPTIONAL,
    signature             AlgorithmIdentifier,
    issuer                Name,
    thisUpdate            Time,
    nextUpdate            Time OPTIONAL,
    revokedCertificates   SEQUENCE OF revokedCertificate OPTIONAL,
    crlExtensions         Extensions OPTIONAL
}

revokedCertificate ::= SEQUENCE {
    userCertificate      CertificateSerialNumber,
    revocationDate       Time,
    crlEntryExtensions   Extensions OPTIONAL
}
~~~

Đây là sơ đồ ASN.1 giản lược để hiểu các trường. Encoding thực tế dùng DER/ASN.1 theo profile X.509 và RFC áp dụng.

### 3.2. Các trường cấp CRL

| Trường | Ý nghĩa | Cách validator sử dụng |
|---|---|---|
| **version** | Phiên bản CRL; CRL v2 có extensions | Xác định cấu trúc và khả năng xử lý |
| **signature** trong TBSCertList | Thuật toán dùng ký nội dung CRL | Phải phù hợp với signatureAlgorithm bên ngoài |
| **issuer** | Distinguished Name của CRL issuer | Ràng buộc CRL với issuer được tin |
| **thisUpdate** | Thời điểm CRL được phát hành/cập nhật | Đánh giá thời điểm thông tin có hiệu lực |
| **nextUpdate** | Thời điểm dự kiến có CRL tiếp theo, nếu có | Đánh giá freshness/expiry của CRL |
| **revokedCertificates** | Danh sách certificate entries bị thu hồi | Tra cứu issuer + serial trong scope |
| **crlExtensions** | CRL number, AKI, IDP, delta indicator... | Xác định version, signer và scope |
| **signatureAlgorithm** | Thuật toán chữ ký CRL | Kiểm tra thuật toán và policy |
| **signatureValue** | Chữ ký trên TBSCertList | Xác minh CRL không bị sửa và được signer ký |

CRL signature bảo vệ tính toàn vẹn và nguồn gốc của nội dung đã ký, nhưng **không tự chứng minh signer có thẩm quyền**. Validator còn phải xác thực CRL issuer, certificate của signer, KeyUsage và path/authorization liên quan.

### 3.3. Các extension quan trọng

| Extension | Mục đích |
|---|---|
| **CRL Number** | Số thứ tự tăng dần để nhận diện CRL phiên bản mới hơn trong phạm vi issuer/scope |
| **Authority Key Identifier (AKI)** | Hỗ trợ xác định public key/certificate của authority ký CRL |
| **Issuing Distribution Point (IDP)** | Xác định scope CRL, ví dụ loại certificate hoặc distribution point |
| **Delta CRL Indicator** | Cho biết CRL là delta và chỉ ra base CRL number cần áp dụng |
| **Freshest CRL** | Có thể chỉ nơi lấy delta CRL cho certificate/CRL theo profile |

CRL v2 extensions có thể chứa critical hoặc non-critical flags. Nếu validator gặp **critical extension không hỗ trợ**, nó không được tùy tiện bỏ qua; path validation phải thất bại theo quy tắc áp dụng.

### 3.4. CRL entry extensions

Mỗi entry thường có:

- **userCertificate:** serial number của certificate bị thu hồi.
- **revocationDate:** thời điểm CA ghi nhận certificate bị thu hồi.
- **reasonCode:** lý do thu hồi, nếu được cung cấp.
- **invalidityDate:** thời điểm private key/certificate được cho là không còn hợp lệ theo evidence, có thể sớm hơn revocationDate.
- **certificateIssuer:** issuer của certificate entry khi sử dụng indirect CRL.

Không được diễn giải serial number một mình như một ID toàn cục. **Serial chỉ có ý nghĩa trong namespace của issuer**; cùng một số serial có thể xuất hiện ở hai CA khác nhau.

## 4. CRL Distribution Points và cách tìm CRL

### 4.1. CRL Distribution Points (CDP)

Certificate có thể chứa extension **CRL Distribution Points** để chỉ nơi relying party có thể lấy CRL áp dụng. URI có thể trỏ tới HTTP, LDAP hoặc scheme được profile/hạ tầng hỗ trợ.

~~~text
Leaf certificate
    |
    +-- CRL Distribution Points extension
            |
            +-- https://pki.example.net/crl/intermediate-01.crl
            |
            +-- ldap://directory.example.net/cn=intermediate-01,...

Relying party:
    1. Đọc CDP từ certificate
    2. Chọn distribution point phù hợp
    3. Fetch CRL
    4. Verify issuer/signature/scope/freshness
    5. Kiểm tra serial trong CRL
~~~

Địa chỉ CDP trong certificate là **metadata được CA ký**, nhưng việc truy cập URI vẫn là một hoạt động mạng. Validator cần bảo vệ khỏi SSRF, URL scheme không mong muốn, redirect nguy hiểm, DNS manipulation, response quá lớn và timeout không giới hạn.

### 4.2. CDP không phải AIA

Hai extension thường bị nhầm:

| Extension | Thường dùng để |
|---|---|
| **CRL Distribution Points (CDP)** | Tìm CRL |
| **Authority Information Access (AIA)** | Tìm issuer certificate hoặc OCSP responder, tùy access method |
| **Freshest CRL** | Tìm delta CRL khi profile sử dụng |

Không dùng AIA OCSP URL như thể nó là CRL URL. OCSP trả response có cấu trúc cho certificate; CRL là danh sách được ký.

### 4.3. Một certificate có thể có nhiều distribution points

Một certificate có thể chỉ nhiều distribution points hoặc scope. Validator cần hiểu:

- Distribution point nào bao phủ certificate.
- Reason flags nào được bao phủ.
- Issuer/IDP nào áp dụng.
- Có cần lấy nhiều CRLs để bao phủ tất cả reason categories không.
- CRL nào thuộc complete/base và CRL nào là delta.

**Không lấy CRL đầu tiên tải được rồi coi nó bao phủ mọi trường hợp.** CRL có thể chỉ chứa một partition hoặc một nhóm reason codes.

### 4.4. CDP không đảm bảo CRL luôn tải được

CRL endpoint có thể:

- Tạm thời không truy cập được.
- Trả CRL cũ do CDN/cache.
- Trả nội dung sai định dạng hoặc bị thay thế.
- Chậm do CRL rất lớn.
- Bị chặn bởi firewall/proxy hoặc client offline.

Ứng dụng cần có **timeout, retry có giới hạn, cache, freshness policy và fail-open/fail-closed decision**. Không tải CRL vô hạn trong TLS handshake.

## 5. Xác minh một CRL hợp lệ

### 5.1. Không chỉ kiểm tra chữ ký

Một validator nên kiểm tra theo scope/policy:

1. **Issuer binding:** CRL issuer phù hợp với issuer của certificate hoặc indirect CRL authorization.
2. **Signature:** Chữ ký CRL verify với public key của signer được tin.
3. **Signer authorization:** Certificate của CRL signer có KeyUsage **cRLSign** khi profile yêu cầu và có path/ủy quyền hợp lệ.
4. **Authority Key Identifier:** phù hợp với authority key được dùng.
5. **Scope:** Issuing Distribution Point, distribution point, certificate class và reason flags bao phủ certificate.
6. **Freshness:** thisUpdate/nextUpdate phù hợp với clock và policy.
7. **CRL versioning:** CRL number/base/delta relationships hợp lệ.
8. **Critical extensions:** validator hiểu các extension bắt buộc.
9. **Entry semantics:** issuer+serial và entry extensions được xử lý đúng.
10. **Algorithm policy:** chữ ký và key size không nằm ngoài policy.

### 5.2. KeyUsage cRLSign

Một CA certificate có thể có KeyUsage cho phép **keyCertSign** để ký certificate và **cRLSign** để ký CRL. Trong một số thiết kế, CRL có thể được ký bởi **delegated CRL issuer** thay vì trực tiếp CA.

Không giả định mọi public key trong chain đều được phép ký CRL. Phải kiểm tra certificate/authorization của signer theo PKI profile.

### 5.3. Issuer và serial phải đi cùng nhau

~~~text
Certificate:
    issuer = CN=Intermediate-01, O=Example
    serial = 0x04A21F

CRL:
    issuer = CN=Intermediate-01, O=Example
    revoked entry = 0x04A21F

=> Entry có thể áp dụng nếu CRL scope, signature, freshness hợp lệ.
~~~

Nếu cùng serial 0x04A21F xuất hiện trong certificate do Intermediate-02 phát hành, entry trên CRL Intermediate-01 **không tự áp dụng** cho certificate đó.

### 5.4. Khi nào absence khỏi CRL có ý nghĩa?

CRL không có một entry **good** cho từng certificate. Validator thường suy ra certificate không bị liệt kê trong một CRL hợp lệ, đầy đủ và bao phủ certificate tại thời điểm đó.

Chỉ có thể dựa vào sự vắng mặt khi:

- Đúng issuer hoặc indirect issuer mapping.
- Đúng distribution point và scope.
- CRL là complete/base hoặc đã ghép delta đúng.
- CRL còn mới và chữ ký/extension hợp lệ.
- Reason coverage đủ theo policy.

Nếu CRL chỉ là một partition không bao phủ certificate, **không thấy serial không có nghĩa certificate good**.

## 6. Các loại CRL

### 6.1. Complete/Base CRL

**Complete CRL** (thường được gọi là full CRL trong vận hành) công bố các revoked entries thuộc scope của nó tại thời điểm phát hành. Một validator có thể dùng CRL này như trạng thái cơ sở nếu:

- Đúng issuer và distribution point.
- Đúng scope/IDP.
- Chữ ký và freshness hợp lệ.
- CRL không phải delta cần base CRL khác.

Complete CRL có thể lớn khi CA phát hành rất nhiều certificate hoặc giữ revocation entries lâu dài. Client phải tải lại toàn bộ danh sách theo cadence và cache policy.

### 6.2. Delta CRL

**Delta CRL** chỉ chứa các thay đổi kể từ một base CRL phù hợp. Nó giúp giảm kích thước và lượng dữ liệu truyền khi danh sách lớn, nhưng validator phải kết hợp đúng base và delta.

~~~mermaid
flowchart TD
    B["Base CRL number 100"] --> M["Current revocation state"]
    D["Delta CRL base=100, number=104"] --> M
    M --> V["Effective CRL view"]
    V --> Q["Check issuer + serial + scope"]
~~~

Các điểm phải kiểm tra:

1. Delta CRL Indicator xác định **base CRL number** mà delta áp dụng.
2. Base và delta phải phù hợp về issuer và các scope/IDP semantics.
3. CRL numbers và thời gian phải được xử lý theo quy tắc versioning, không chọn file chỉ vì tên file mới hơn.
4. Validator cần giữ base CRL còn phù hợp và áp dụng delta đúng cách.
5. Nếu delta không có base phù hợp hoặc không thể xác thực, không tự coi delta là complete CRL.

Một delta CRL có thể chứa entry mới hoặc cập nhật trạng thái, bao gồm **removeFromCRL** trong trường hợp phù hợp. Không được ghép delta bằng cách nối văn bản hoặc chỉ union tất cả serials.

### 6.3. Indirect CRL

Trong **indirect CRL**, CRL issuer có thể khác issuer của certificate bị liệt kê. CRL entry có thể chứa extension **certificateIssuer** để xác định issuer của certificate entry.

Điều này hữu ích khi một CRL issuer được ủy quyền quản lý revocation cho nhiều CA/issuer. Validator phải:

- Xác thực CRL signer và quyền phát hành indirect CRL.
- Xử lý certificateIssuer theo đúng quy tắc kế thừa entry trong CRL.
- So khớp certificate issuer + serial, không chỉ serial.
- Kiểm tra Issuing Distribution Point có chỉ ra indirect CRL theo profile.

Nếu bỏ qua certificateIssuer, một serial có thể bị gán nhầm cho issuer khác.

### 6.4. Partitioned CRL và Issuing Distribution Point

CA lớn có thể chia CRL theo:

- Nhóm certificate/issuer.
- Phạm vi distribution point.
- Loại certificate như user, CA hoặc attribute certificate theo profile.
- Nhóm reason codes được bao phủ.

**Issuing Distribution Point (IDP)** giúp xác định scope của CRL, bao gồm một số loại certificate và reason flags. Client cần xác minh CRL thực sự bao phủ certificate đang kiểm tra.

~~~text
CRL-Partition-A: certificate class / reason subset A
CRL-Partition-B: certificate class / reason subset B
CRL-Partition-C: certificate class / reason subset C

Validator:
    chọn đúng distribution point
    kiểm tra IDP và reason coverage
    không suy diễn absence từ partition không áp dụng
~~~

### 6.5. Bảng so sánh

| Loại CRL | Nội dung | Ưu điểm | Rủi ro/điều kiện |
|---|---|---|---|
| **Complete/Base** | Snapshot entries trong scope | Dễ hiểu, độc lập khi là full CRL hợp lệ | Có thể lớn và tốn bandwidth |
| **Delta** | Thay đổi kể từ base | Giảm tải truyền và lưu trữ | Phải ghép đúng base, issuer, scope và CRL number |
| **Indirect** | CRL do issuer khác phát hành cho entries thuộc issuer khác | Hỗ trợ quản trị phân tán | Cần certificateIssuer mapping và authorization |
| **Partitioned** | Chỉ một phần certificate/reasons | Mở rộng quy mô | Không được coi một partition là toàn bộ trạng thái |

## 7. Reason codes và thời điểm thu hồi

### 7.1. Các reason codes phổ biến

| Reason code | Ý nghĩa khái quát | Gợi ý xử lý |
|---|---|---|
| **unspecified** | Không nêu lý do cụ thể | Xử lý theo trạng thái revoked |
| **keyCompromise** | Private key của subject bị compromise | Sinh keypair mới, revoke certificate, điều tra key exposure |
| **cACompromise** | Khóa CA bị compromise | Xem xét toàn bộ issuance scope và trust hierarchy |
| **affiliationChanged** | Thông tin liên kết/tổ chức thay đổi | Cập nhật identity và certificate |
| **superseded** | Certificate được thay thế | Kiểm tra certificate mới và consumers |
| **cessationOfOperation** | Hoạt động của subject kết thúc | Deprovision workload/identity |
| **certificateHold** | Certificate tạm thời bị giữ/treo theo policy | Có thể có xử lý removeFromCRL phù hợp |
| **privilegeWithdrawn** | Quyền của subject bị rút | Đồng bộ IAM/authorization |
| **aACompromise** | Attribute authority bị compromise | Đánh giá attribute certificate/trust domain |

Reason code cung cấp ngữ cảnh cho relying party và incident response. Nó **không thay thế trạng thái revoked**; một certificate bị liệt kê trong CRL vẫn cần bị xử lý theo policy ngay cả khi reason là unspecified.

### 7.2. revocationDate và invalidityDate

- **revocationDate** là thời điểm ghi trong revoked entry, thường phản ánh thời điểm certificate bị revoke trong CRL.
- **invalidityDate** là entry extension tùy chọn thể hiện thời điểm mà private key/certificate được cho là đã mất hiệu lực hoặc không còn đáng tin; có thể sớm hơn revocationDate.

Ví dụ:

~~~text
Ngày 10: Security phát hiện private key có thể đã bị lấy.
Ngày 03: Forensics tìm được bằng chứng key đã bị copy.
Ngày 10: CA phát hành CRL với revocationDate.
invalidityDate có thể phản ánh ngày 03 nếu policy/evidence cho phép.
~~~

Khi đánh giá chữ ký số lịch sử, không được chỉ nhìn revocationDate rồi kết luận mọi chữ ký trước ngày đó đều đáng tin. Cần xét invalidity evidence, trusted timestamp và policy validation tại thời điểm ký.

### 7.3. removeFromCRL không phải nút undo chung

**removeFromCRL** là một reason code đặc biệt trong CRL entry, thường dùng trong xử lý delta CRL để biểu thị một certificate được loại khỏi CRL theo semantics thích hợp, ví dụ certificate từng ở trạng thái **certificateHold** và được gỡ hold.

Không diễn giải removeFromCRL là:

- Một cách xóa mọi revocation vĩnh viễn.
- Cách đảo ngược keyCompromise hoặc cACompromise tùy ý.
- Bằng chứng certificate tự động được tin lại mà không cần path/status validation.

Việc gỡ hold phải được CA thực hiện đúng quy trình và relying party phải xử lý base/delta CRL theo chuẩn. Certificate đã bị revoke vì private key compromise thường cần **keypair/certificate mới**, không nên tái sử dụng material bị lộ.

### 7.4. Reason flags và scope

CRL distribution point có thể chỉ ra một tập reason flags được bao phủ. Nếu một CRL chỉ bao phủ một phần reasons, việc không tìm thấy serial không chứng minh certificate không bị revoke vì lý do thuộc phần còn lại.

Validator phải tính **coverage** từ distribution points, IDP và reason flags theo quy tắc X.509/PKIX. Đây là một lý do không nên tự viết CRL validator bằng thao tác parse serial đơn giản.

## 8. CRL publication, freshness và cache

### 8.1. CA revoke không đồng nghĩa mọi client biết ngay

Một lifecycle điển hình:

~~~mermaid
sequenceDiagram
    participant S as Security / RA
    participant CA as Issuing CA
    participant P as CRL Publication
    participant C as Cache/CDN/Directory
    participant V as Relying Party
    S->>CA: Request revoke issuer + serial
    CA->>CA: Validate authority and update revocation database
    CA->>P: Generate and sign CRL
    P-->>C: Publish new CRL
    V->>C: Fetch CRL according to refresh policy
    C-->>V: CRL with thisUpdate/nextUpdate
    V->>V: Verify signature, scope, freshness, serial
    V-->>V: Reject certificate if listed
~~~

Các mốc thời gian khác nhau:

1. **T_detected:** phát hiện compromise.
2. **T_CA_recorded:** CA ghi nhận revocation.
3. **T_CRL_published:** CRL mới được publish.
4. **T_cache_updated:** CDN/proxy/cache nhận CRL mới.
5. **T_client_refreshed:** relying party tải hoặc cập nhật CRL.
6. **T_effective_rejection:** client thực tế từ chối certificate.

Incident response phải theo dõi **effective rejection**, không chỉ trạng thái trong CA database.

### 8.2. thisUpdate và nextUpdate

- **thisUpdate:** thời điểm CRL hiện tại được phát hành/cho biết trạng thái.
- **nextUpdate:** thời điểm dự kiến có bản CRL tiếp theo.

Validator cần áp dụng:

- Maximum CRL age theo threat model.
- Clock skew được cho phép.
- Xử lý nextUpdate không có theo profile/policy.
- Xử lý thisUpdate ở tương lai.
- Phát hiện CRL bị replay hoặc cache quá cũ.

Chữ ký hợp lệ không làm một CRL cũ trở nên mới. Một CRL được ký hôm qua có thể không phản ánh certificate bị revoke sáng nay.

### 8.3. CRL number và chống rollback

CRL Number hỗ trợ phân biệt phiên bản CRL. Validator/CRL cache nên chống việc thay một CRL mới bằng một bản cũ hơn trong cùng issuer/scope khi policy và implementation có thể xác định.

Không so CRL number giữa các issuer khác nhau như một bộ đếm toàn cục. Không so file modification time hoặc tên file để xác định bản CRL mới.

### 8.4. Cache và refresh

Cache giúp giảm bandwidth và latency, đặc biệt khi CRL lớn. Nhưng cache policy phải:

- Tôn trọng thisUpdate/nextUpdate và max-age.
- Refresh trước khi CRL hết hạn.
- Không dùng stale CRL vô hạn khi endpoint lỗi.
- Phân biệt lỗi fetch với trạng thái revoked.
- Có giới hạn dung lượng và kiểm soát cache poisoning.
- Ghi metric cho age, refresh failures và CRL version.

### 8.5. Fail-open và fail-closed

| Tình huống | Fail-closed | Fail-open/soft-fail có kiểm soát |
|---|---|---|
| CRL mới và hợp lệ, serial không bị liệt kê | Có thể tiếp tục nếu các kiểm tra khác pass | Tương tự |
| CRL mới và serial bị liệt kê | **Từ chối** | **Vẫn phải từ chối** |
| CRL hết hạn hoặc stale | Từ chối nếu không có nguồn hợp lệ khác | Có thể tạm chấp nhận theo policy risk |
| CRL endpoint timeout | Từ chối hoặc fallback hợp lệ | Có thể tạm chấp nhận với cảnh báo/giới hạn |
| CRL signature sai | Từ chối | Không được coi response không xác thực là good |
| CRL scope không bao phủ certificate | Không suy ra good; lấy nguồn đúng hoặc từ chối | Không suy ra good; soft-fail không chữa scope mismatch |

**Soft-fail chỉ có thể áp dụng cho một số lỗi xác định trạng thái theo policy**, không override explicit revoked, signature invalid hoặc issuer mismatch. Với mTLS/KMS/admin endpoints nhạy cảm, cân nhắc fail-closed cùng HA, cache mới và short-lived certificates.

### 8.6. CRL không phải cơ chế realtime tuyệt đối

CRL thường được phát hành theo lịch hoặc sau sự kiện, không nhất thiết thay đổi tức thì ở mọi client. Với yêu cầu kiểm tra trạng thái nhanh theo từng certificate, OCSP có thể phù hợp hơn; tuy vậy OCSP cũng có cache, freshness và outage trade-offs. Short-lived certificates có thể giảm một phần nhu cầu revocation nhưng không thay thế incident response.

## 9. CRL so với OCSP và các cơ chế khác

| Tiêu chí | CRL | OCSP | Trust store / distrust | Short-lived certificate |
|---|---|---|---|---|
| Dữ liệu | Danh sách revoked trong scope | Trạng thái cho certificate cụ thể | Trust anchor/policy được cài | Thời hạn ngắn |
| Cách lấy | Download/cache CRL | Query responder hoặc stapled response | Kênh cập nhật cấu hình/OS/app | Issuance và renewal |
| Freshness | thisUpdate/nextUpdate, CRL number | thisUpdate/nextUpdate/producedAt | Version/update cadence | notAfter/clock |
| Privacy | Client tải danh sách; ít lộ query cụ thể hơn OCSP trực tiếp | Query có thể tiết lộ certificate client đang kiểm tra | Phụ thuộc update channel | Không phải status query |
| Scale | CRL lớn có thể tốn bandwidth/storage | Nhiều request responder | Trust-store distribution rộng | Nhiều issuance/renewal |
| Outage | Cache/fallback hoặc fail policy | Responder availability/cache/stapling | Update channel outage | CA/renewal outage |
| Root compromise | Không tự loại trust anchor | Không tự loại trust anchor | Cần distrust root | Không giải quyết root compromise |

### 9.1. CRL không có trạng thái good riêng cho từng certificate

OCSP response có trạng thái **good/revoked/unknown**. CRL là danh sách; validator kiểm tra certificate có entry trong CRL đúng scope hay không. Nếu không có entry, chỉ được suy ra không bị liệt kê khi CRL đầy đủ và bao phủ certificate tại thời điểm hợp lệ.

### 9.2. CRL và OCSP có thể cùng tồn tại

Một relying party có thể ưu tiên OCSP, dùng CRL fallback, hoặc ưu tiên CRL tùy policy/provider. Nhưng không nên tùy tiện trộn dữ liệu nếu:

- Issuer/scope không khớp.
- Status evidence có freshness khác nhau.
- Một nguồn báo revoked và nguồn kia vẫn cache good cũ.
- Provider có quy tắc precedence/fallback riêng.

Với security incident, **evidence revoked đáng tin** phải được xử lý theo policy; không dùng một cache cũ để phủ nhận trạng thái mới.

### 9.3. Root CA và trust anchors

Root CA thường được cấu hình như **trust anchor** ngoài certificate path cần validate. Việc thu hồi root certificate theo CRL không tự động loại root khỏi trust store của tất cả client. Khi root private key bị compromise hoặc root cần distrust, cần **trust-store update/emergency distrust** qua kênh quản trị phù hợp.

## 10. Java 17: Kiểm tra CRL bằng PKIXRevocationChecker

### 10.1. Vì sao không chỉ parse CRL rồi tìm serial?

Đoạn code tự parse serial và gọi hàm contains có thể bỏ sót:

- Chữ ký CRL và quyền của CRL signer.
- Issuer mapping và indirect CRL.
- Issuing Distribution Point và reason coverage.
- Base/delta CRL relationship.
- Freshness, CRL number và critical extensions.
- Certificate path và trust anchor.

Vì vậy, nên dùng **PKIX CertPathValidator** và **PKIXRevocationChecker** từ JCA/JDK, hoặc một validator được duy trì có semantics tương đương. Nếu tự xây parser, cần triển khai đầy đủ các quy tắc X.509/PKIX và kiểm thử kỹ.

### 10.2. Ví dụ PKIX với CRL trong CertStore

Ví dụ dưới đây nhận một CertPath đã được xây theo thứ tự leaf tới intermediate, trust anchors đã được phê duyệt, CRLs đã được lấy từ nguồn tin cậy và certificate của issuer/delegated CRL signer cần thiết. Nó yêu cầu **ưu tiên CRL và không fallback sang OCSP**; không bật SOFT_FAIL.

~~~java
import java.security.GeneralSecurityException;
import java.security.cert.CRL;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertStore;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.PKIXRevocationChecker;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Date;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

public final class CrlPkixValidation {

    private CrlPkixValidation() {}

    public static PKIXCertPathValidatorResult validate(
            CertPath certPath,
            Set<TrustAnchor> approvedTrustAnchors,
            Collection<X509Certificate> issuerAndSignerCertificates,
            Collection<? extends CRL> trustedCrls,
            Date validationTime)
            throws GeneralSecurityException {

        if (certPath == null || approvedTrustAnchors == null
                || approvedTrustAnchors.isEmpty()
                || issuerAndSignerCertificates == null
                || trustedCrls == null || trustedCrls.isEmpty()
                || validationTime == null) {
            throw new IllegalArgumentException(
                    "Missing PKIX validation input");
        }

        // CertStore chỉ chứa certificate/CRL đã lấy từ nguồn
        // được kiểm soát. Không nhận material tùy ý từ caller.
        List<Object> material = new ArrayList<>();
        material.addAll(issuerAndSignerCertificates);
        material.addAll(trustedCrls);

        CertStore store = CertStore.getInstance(
                "Collection",
                new CollectionCertStoreParameters(material));

        PKIXParameters parameters =
                new PKIXParameters(approvedTrustAnchors);
        parameters.setDate(validationTime);
        parameters.addCertStore(store);

        // Dùng checker được cấu hình tường minh bên dưới.
        parameters.setRevocationEnabled(false);

        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();

        // CRL là nguồn ưu tiên; không fallback sang OCSP.
        // Không bật SOFT_FAIL: thiếu CRL phù hợp phải được xử lý
        // theo hard-fail policy của validator.
        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK));

        parameters.addCertPathChecker(checker);

        return (PKIXCertPathValidatorResult)
                validator.validate(certPath, parameters);
    }
}
~~~

Lưu thành **CrlPkixValidation.java**. Đây là helper tích hợp; caller phải cung cấp **CertPath, trust anchors và CRL materials** đã được lấy từ inventory/PKI theo cách tin cậy. Code không tự tải CDP và không tự xây trust anchor từ certificate do peer gửi.

### 10.3. Cách tạo CRL từ file trong môi trường kiểm thử

Đoạn helper ngắn dưới đây đọc một CRL DER/PEM được cấp trong test fixture:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509CRL;

static X509CRL loadTestCrl(Path path) throws Exception {
    CertificateFactory factory =
            CertificateFactory.getInstance("X.509");
    try (InputStream input = Files.newInputStream(path)) {
        return (X509CRL) factory.generateCRL(input);
    }
}
~~~

Việc parse thành X509CRL **không xác minh trust, signer authorization, freshness hay scope**. Hãy đưa CRL vào PKIX validation với chain/trust anchors và certificate signer phù hợp. Không lấy file CRL từ một URL tùy ý rồi tự coi là trusted.

### 10.4. Các option quan trọng

| Option | Ý nghĩa | Khi sử dụng |
|---|---|---|
| **PREFER_CRLS** | Ưu tiên CRL thay vì OCSP | Khi policy yêu cầu CRL là nguồn ưu tiên |
| **NO_FALLBACK** | Không chuyển sang cơ chế khác nếu cơ chế ưu tiên không thực hiện được | Khi cần CRL-only/hard-fail theo thiết kế |
| **SOFT_FAIL** | Cho phép bỏ qua một số lỗi không xác định revocation status theo semantics checker | Chỉ khi có risk acceptance rõ; không override explicit revoked |
| **ONLY_END_ENTITY** | Chỉ kiểm tra end-entity certificate | Chỉ khi policy chấp nhận không kiểm tra revocation của CA certificates |

Không bật **ONLY_END_ENTITY** theo mặc định trong môi trường mà Intermediate CA compromise là threat quan trọng. Cần xác định path certificates nào phải được kiểm tra revocation theo profile.

### 10.5. CRL retrieval và Java runtime

Ví dụ CertStore ở trên dùng **CRLs được cung cấp tường minh**; đây là cách dễ kiểm soát trong test và các hệ thống có CRL distribution service riêng.

Nếu muốn Java tự truy xuất CRL từ CDP, cần kiểm tra cấu hình/runtime/provider. Một số JDK có thuộc tính hệ thống **com.sun.security.enableCRLDP** để bật CRL Distribution Point support. Không giả định mọi runtime, provider hoặc container image đều bật giống nhau; phải cấu hình sớm, kiểm tra outbound network, timeout và integration tests.

**Không để việc fetch CRL chặn vô hạn TLS handshake.** Quản lý cache và prefetch ở một service/agent phù hợp nếu hệ thống cần kiểm soát latency.

### 10.6. PKIX validation không phải hostname validation

PKIX path validation kiểm tra chain/trust và các constraints theo PKIX. Với TLS client, vẫn phải kiểm tra **expected hostname/SAN** bằng endpoint identification trong JSSE hoặc TLS stack.

Ngoài ra, certificate hợp lệ không tự cấp quyền nghiệp vụ. Ứng dụng vẫn phải kiểm tra **workload identity, tenant, record authorization và KMS grants** trước khi trả dữ liệu hoặc thực hiện Sign/Decrypt.

### 10.7. Giới hạn của ví dụ Java

1. Không tự tạo CertPath; path phải được xây đúng và trust anchors phải đến từ cấu hình tin cậy.
2. Không tự fetch CRL từ CDP; caller cung cấp CRLs và signer certificates.
3. Không triển khai delta/indirect CRL parser; việc xử lý phụ thuộc PKIX provider.
4. Không tự cấu hình TLS hostname verification.
5. Không chứng minh OCSP/CRL endpoint availability trong production.
6. Không tự quản lý cache/freshness ngoài các kiểm tra provider thực hiện.
7. Không thay thế kiểm thử với CA/CRL thật, certificates đã revoke và từng TLS client.

## 11. Runbook CA revoke và publish CRL

### 11.1. Trước khi revoke

1. Xác định **issuer, serial, certificate fingerprint, subject/SAN và key purpose**.
2. Xác nhận reason phù hợp: keyCompromise, cACompromise, superseded hoặc reason khác.
3. Nếu có key compromise, xác định **thời điểm nghi lộ** và evidence cho invalidityDate.
4. Xác định certificate là leaf, Intermediate CA hay loại khác; phân tích blast radius.
5. Xác định CRL issuer, CDP, distribution point, base/delta policy và relying parties.
6. Kiểm tra CA signing key/CRL signing key còn an toàn; nếu signer compromise, quy trình phải escalated.
7. Xác định clients nào cần hard-fail và clients nào có controlled fallback.

### 11.2. Revoke và publish

~~~text
T0: Incident/RA validates revocation request.
T1: CA records issuer + serial + reason + effective time.
T2: CA/CRL issuer generates new CRL.
T3: CRL signature is created under authorized cRLSign key.
T4: CRL Number, thisUpdate, nextUpdate and scope are verified.
T5: Publish to configured CDPs and replicate/cache.
T6: Verify downloaded CRL signature, issuer, scope and freshness.
T7: Test relying parties reject the revoked certificate.
T8: Record effective rejection time and evidence.
~~~

### 11.3. Kiểm tra sau publish

- Download CRL từ từng CDP/region được công bố.
- Kiểm tra issuer, signature algorithm, signature, AKI, CRL number.
- Kiểm tra thisUpdate/nextUpdate và IDP/scope.
- Xác nhận serial xuất hiện đúng issuer context và reason.
- Nếu delta CRL, xác nhận base CRL number và kết quả merge.
- Kiểm tra cache/CDN không tiếp tục trả bản stale.
- Kiểm thử certificate revoked trên Java, gateway, service mesh và clients trọng yếu.
- Ghi nhận thời gian từ CA update đến effective client rejection.

### 11.4. Khi CRL publish thất bại

1. Giữ trạng thái incident; không báo relying parties đã được bảo vệ.
2. Xác định lỗi CA signer, HSM, CRL generation, publication endpoint hay replication.
3. Nếu policy cho phép, dùng alternate CRL publication path đã được kiểm thử.
4. Với high-risk service, kích hoạt denylist/emergency distrust hoặc chặn identity ở gateway/IAM theo kế hoạch.
5. Không tạo CRL tự ký bằng key không được ủy quyền.
6. Khôi phục publication, verify CRL và chạy lại negative tests.
7. Ghi rõ client nào chưa nhận được status mới và owner xử lý.

## 12. Threat model: Lỗi thường gặp khi dùng CRL

| Nguy cơ | Hậu quả | Kiểm soát |
|---|---|---|
| **Chỉ tìm serial, bỏ qua issuer** | Revocation áp nhầm certificate | So issuer + serial và indirect mapping |
| **Dùng CRL sai scope/partition** | Không phát hiện certificate bị revoke | Kiểm tra CDP, IDP và reason coverage |
| **Chấp nhận stale CRL** | Client tiếp tục tin certificate đã revoke sau lần publish cũ | Freshness/max-age và refresh monitoring |
| **Không verify CRL signature** | Attacker sửa danh sách hoặc chèn entry giả | PKIX CRL signer validation |
| **Không kiểm tra cRLSign authorization** | Tin signer không có quyền ký CRL | Validate signer certificate và KeyUsage |
| **Bỏ qua AKI/issuer binding** | Nhầm CRL signer/key | Kiểm tra authority identity |
| **Dùng delta CRL không có base** | Trạng thái hiệu lực không chính xác | Validate base number và scope |
| **Union mọi delta serials** | Xử lý sai removeFromCRL và update semantics | Dùng PKIX implementation đúng chuẩn |
| **Bỏ qua certificateIssuer trong indirect CRL** | Gán serial sai issuer | Hỗ trợ indirect CRL đúng profile |
| **Không hiểu reason flags** | Suy ra good từ partition thiếu coverage | Kiểm tra reason coverage |
| **CRL endpoint timeout không có policy** | Outage hoặc soft-fail ngoài ý muốn | Timeout, fallback và fail policy |
| **CRL URL gây SSRF** | Validator truy cập endpoint nội bộ nguy hiểm | Scheme/host allowlist, egress controls |
| **CRL quá lớn không giới hạn** | Memory/CPU exhaustion | Response size limits, cache, streaming/provider controls |
| **CRL rollback** | Client nhận bản cũ hơn | CRL Number/version and cache anti-rollback |
| **CA CRL signing key bị lộ** | Attacker có thể tạo CRL giả | HSM, separate cRLSign key, revoke/replace signer |
| **Root CA compromise chỉ xử lý bằng CRL** | Root vẫn nằm trong trust anchors | Out-of-band distrust/trust-store update |
| **Tin absence trong CRL partial** | Certificate bị revoke không được phát hiện | Complete scope coverage |
| **Không test actual TLS stack** | Client âm thầm không enforce CRL | Negative handshake tests |
| **Không terminate sessions** | Kết nối cũ tiếp tục sau revoke | Session/channel invalidation |
| **CRL log chứa secret** | Lộ private key/credentials khi debug | Metadata-only logging |

### 12.1. CRL signer bị compromise

Nếu private key dùng ký CRL bị lộ, attacker có thể tạo CRL giả tùy khả năng và trust của signer:

- Bỏ một certificate đã bị revoke khỏi danh sách.
- Thêm certificate hợp lệ vào danh sách để gây denial of service.
- Tạo CRL có freshness/number giả trong phạm vi signer.

Biện pháp:

1. Bảo vệ CRL signing key trong HSM hoặc boundary phù hợp.
2. Hạn chế key usage chỉ cRLSign khi profile cho phép.
3. Tách quyền quản trị CA và CRL signer.
4. Theo dõi CRL number, publication source và audit.
5. Có kế hoạch thay signer certificate/key và phân phối trust/status mới.

### 12.2. CRL endpoint không đáng tin

CDP URI nằm trong certificate được CA ký nhưng endpoint có thể bị chiếm, redirect hoặc bị thay DNS. **Chữ ký CRL** vẫn là lớp xác minh nội dung; endpoint HTTPS không thay thế CRL signature verification.

Không được coi CRL là hợp lệ chỉ vì tải từ HTTPS. Ngược lại, CRL có chữ ký hợp lệ nhưng quá hạn hoặc sai scope vẫn không đủ để quyết định certificate good.

## 13. Kiểm thử CRL

### 13.1. Ma trận positive/negative

| Test case | Kết quả kỳ vọng | Mục tiêu |
|---|---|---|
| Certificate không bị revoke, CRL complete/fresh/đúng scope | PASS nếu path và identity hợp lệ | Baseline |
| Serial certificate nằm trong CRL | **DENY** | Revocation enforcement |
| Serial giống nhưng issuer khác | Không áp nhầm entry | Issuer binding |
| CRL signature sai | **DENY** | Integrity |
| CRL signer thiếu cRLSign authorization | **DENY** | Signer authority |
| CRL hết nextUpdate | **DENY hoặc fallback hợp lệ theo policy** | Freshness |
| thisUpdate ở tương lai ngoài clock skew | **DENY** | Clock/freshness |
| CRL Number thấp hơn bản đã chấp nhận | Không rollback cache | Versioning |
| IDP không bao phủ certificate | Không suy ra good | Scope |
| Reason flags không đủ coverage | Không suy ra good | Reason coverage |
| Delta thiếu base phù hợp | **DENY** | Delta semantics |
| Delta có removeFromCRL cho certificateHold hợp lệ | Áp dụng đúng merge rules | Hold removal |
| Indirect CRL có certificateIssuer khác | Đối chiếu đúng issuer | Indirect mapping |
| Critical extension không hỗ trợ | **DENY** | Extension handling |
| CRL endpoint timeout | Theo fail policy | Availability |
| CRL response quá lớn | Bị giới hạn/an toàn | DoS resistance |
| CRL endpoint redirect sang private IP không cho phép | **DENY** | SSRF/egress |
| CRL mới publish nhưng cache cũ | Refresh hoặc từ chối theo freshness | Propagation |
| Intermediate CA bị revoke | Path bị ảnh hưởng phải fail | Chain revocation |
| Root CA bị distrust nhưng còn trong local trust store | Client phải được cập nhật/deny | Trust anchor management |

### 13.2. Test cho Java PKIX

- CertPath hợp lệ với CRL fresh và certificate không bị revoke.
- Leaf serial có trong CRL đúng issuer.
- Intermediate CA serial có trong CRL.
- CRL signature sai hoặc CRL signer certificate không trusted.
- CRL không có cRLSign usage theo profile.
- CRL stale hoặc thiếu CRL cho certificate cần kiểm tra.
- Delta CRL với base đúng và base sai.
- Indirect CRL với certificateIssuer mapping.
- Hostname sai dù PKIX path hợp lệ.
- CRL endpoint unreachable khi dùng runtime auto-fetch.

### 13.3. Test hành vi TLS thật

Không chỉ test một hàm parser. Cần chạy handshake trên các client stack thực tế:

- Java 17 JSSE với truststore mặc định và truststore riêng.
- API gateway/reverse proxy/load balancer.
- Service mesh sidecars và mTLS workload clients.
- Mobile/IoT clients nếu nằm trong scope.
- Clients có cache CRL riêng hoặc CRL fetching bị giới hạn.

Kiểm tra **certificate revoked bị từ chối**, certificate hợp lệ vẫn hoạt động, CRL stale không bị chấp nhận vô hạn và outage có hành vi đúng policy.

## 14. Case study: Thu hồi certificate mTLS sau khi private key bị lộ

### 14.1. Bối cảnh

Một nền tảng thanh toán sử dụng internal PKI:

~~~text
Internal Root CA
    |
    +-- Intermediate CA: service-issuing-01
            |
            +-- billing-writer certificate
            +-- billing-reader certificate
            +-- reconciliation-worker certificate

CRL:
    http://pki.internal.example/crl/service-issuing-01.crl

Runtime:
    Java 17 services
    API gateway
    Service mesh sidecars
    KMS-backed signing and wrapping keys
~~~

Một developer phát hiện private key của billing-writer có thể đã bị copy từ một debug archive. Certificate còn hạn 60 ngày. Security yêu cầu revoke ngay, nhưng một số service mesh nodes đang dùng CRL cache cũ.

### 14.2. Các hành động sai cần tránh

- Chỉ xóa file private key khỏi pod hiện tại và cho rằng bản sao cũ đã biến mất.
- Phát hành certificate mới bằng chính private key đã lộ.
- Ghi serial vào một file denylist tự tạo nhưng không cập nhật CRL/PKI.
- Publish CRL mới nhưng không kiểm tra CDN/cache hoặc client behavior.
- Chỉ test CRL parser, không test mTLS handshake thật.
- Nghĩ certificate revoke sẽ tự thu hồi KMS grants và tokens đã cấp cho workload.

### 14.3. Quy trình xử lý

**Bước 1 — Xác định certificate.** Ghi issuer, serial, fingerprint, SAN/URI identity, EKU clientAuth, validity, CDP và service instances dùng certificate.

**Bước 2 — Contain.** Cô lập workload/pod nghi bị lộ, bảo toàn debug archive làm evidence, thu hồi credential và sessions liên quan theo incident scope.

**Bước 3 — Tạo keypair mới.** Sinh private key mới trong boundary được phê duyệt, tạo CSR, CA xác minh workload identity và issue certificate mới. Không reuse key đã nghi lộ.

**Bước 4 — Revoke certificate cũ.** CA ghi nhận issuer + serial, reason keyCompromise nếu phù hợp, và invalidityDate nếu có evidence đủ tin cậy.

**Bước 5 — Publish CRL.** CRL issuer tạo CRL mới, ký bằng key được ủy quyền cRLSign, cập nhật CRL number/thisUpdate/nextUpdate và publish tới CDP.

**Bước 6 — Verify distribution.** Download CRL từ từng endpoint/region; kiểm tra signature, issuer, scope, serial và freshness. Kiểm tra cache/CDN không trả bản cũ.

**Bước 7 — Update service mesh.** Đảm bảo sidecars và Java trust managers thực sự refresh CRL hoặc nhận status update qua cơ chế được phê duyệt.

**Bước 8 — Test old/new identities.** Certificate cũ phải bị từ chối trên các clients trọng yếu; certificate mới phải kết nối thành công với đúng trust domain.

**Bước 9 — Revoke related access.** Kiểm tra KMS grants, API tokens, service sessions và signing permissions gắn với billing-writer. CRL không thay thế IAM revocation.

**Bước 10 — Audit.** Ghi T_detected, T_CA_recorded, T_CRL_published, T_cache_updated và T_effective_rejection.

### 14.4. Nếu CRL endpoint chưa cập nhật được

Nếu một nhóm clients không thể lấy CRL mới:

1. Không tuyên bố toàn bộ fleet đã từ chối certificate cũ.
2. Chặn identity/certificate cũ ở gateway hoặc service mesh theo emergency policy.
3. Cô lập clients có CRL stale hoặc không hỗ trợ revocation.
4. Dùng alternate CRL publication/cache path đã được kiểm thử nếu có.
5. Theo dõi từng client group cho tới khi có evidence effective rejection.
6. Ghi ngoại lệ, owner và thời hạn xử lý.

### 14.5. Điều tra phạm vi key management

Certificate mTLS bị lộ không mặc nhiên chứng minh KEK/DEK đã lộ. Nhưng cần kiểm tra workload identity có quyền:

- Gọi KMS Sign/Decrypt/Unwrap.
- Lấy access token hoặc assume role.
- Đọc secret/config từ các service khác.
- Truy cập debug archives, heap dumps hoặc environment variables.

Nếu attacker dùng workload identity để gọi KMS, phải xem **KMS audit log** và revoke grants/tokens. Nếu plaintext DEK đã bị lấy, chỉ revoke certificate sẽ không thu hồi khả năng giải mã ciphertext mà attacker giữ.

## 15. Audit, monitoring và CRL inventory

### 15.1. Các sự kiện cần ghi

| Event | Metadata cần có | Không ghi |
|---|---|---|
| **Revocation request** | Incident ID, issuer, serial, fingerprint, reason, requester | Private key, PIN |
| **CA status update** | CA ID, serial, effective time, operator, approval | CA signing secret |
| **CRL generation** | CRL issuer, CRL number, thisUpdate, nextUpdate, scope | CRL signer private key |
| **CRL signing** | HSM keyRef, algorithm, operation ID, result | Raw signing key |
| **CRL publication** | CDP, region, object version, publish time, checksum | Admin credential |
| **CRL fetch/cache** | Client group, CRL number, age, endpoint, result | Customer payload |
| **Validation decision** | Certificate issuer/serial, path result, reason, policy revision | Session secrets |
| **TLS rejection** | Service/client group, certificate ref, failure category, time | Raw certificate private key |
| **Trust update** | Client fleet/version, issuer changes, rollout status | Trust-store admin token |

### 15.2. Metrics hữu ích

- **CRL age** so với thisUpdate/nextUpdate và policy maximum age.
- **CRL publication lag** từ CA database tới từng CDP/region.
- **CRL fetch success/failure** theo client group.
- **CRL number drift** giữa publication endpoints/caches.
- **Revoked certificate acceptance attempts** và actual handshake outcomes.
- **Unknown issuer/scope mismatch** errors.
- **CRL signature validation failures**.
- **Delta CRL base mismatch** và merge failures.
- **CRL size, parse time, memory consumption**.
- **Clients không kiểm tra revocation** hoặc không cập nhật status.
- **Thời gian từ revoke request tới effective rejection**.
- **Intermediate/Root distrust rollout coverage**.

Không có fetch error không chứng minh client đã kiểm tra CRL. Một client không fetch CRL có thể đơn giản là không bật revocation checking. Cần đối chiếu **configuration inventory và negative handshake tests**.

### 15.3. CRL inventory

Với mỗi issuer/PKI profile, quản lý:

- Issuer identity, keyRef và CRL signer identity.
- CDP/Freshest CRL locations.
- Full/base/delta/indirect/partitioned behavior.
- CRL Number và publication cadence.
- thisUpdate/nextUpdate policy.
- Supported reason codes và reason coverage.
- Clients/validators phụ thuộc CRL.
- Cache/replication topology.
- Key backup/rotation/revocation của CRL signer.
- Owner, incident contact và DR publication path.

## 16. Checklist triển khai CRL

1. **Issuer binding:** CRL issuer được xác định và xác thực đúng với certificate/path?
2. **Serial:** Revocation lookup dùng issuer + serial, không chỉ serial?
3. **Signature:** CRL signature được verify bằng public key signer được tin?
4. **Signer authorization:** Signer có cRLSign usage/ủy quyền theo profile?
5. **AKI:** Authority Key Identifier được xử lý đúng?
6. **Scope:** Issuing Distribution Point và CRL Distribution Point bao phủ certificate?
7. **Reason coverage:** Reason flags đủ để suy luận trạng thái theo policy?
8. **Freshness:** thisUpdate/nextUpdate, clock skew và max age được kiểm tra?
9. **Version:** CRL Number được dùng đúng trong issuer/scope; cache không rollback?
10. **Base/delta:** Delta CRL có base tương ứng và được merge theo PKIX?
11. **Indirect:** certificateIssuer mapping được hỗ trợ nếu profile sử dụng indirect CRL?
12. **Critical extensions:** Extension quan trọng không hỗ trợ dẫn tới validation failure?
13. **Entry semantics:** reasonCode, revocationDate, invalidityDate và removeFromCRL được hiểu đúng?
14. **CDP retrieval:** URI/scheme/redirect/timeout/size limits được kiểm soát?
15. **AIA separation:** Không nhầm AIA OCSP với CRL Distribution Points?
16. **Caching:** Cache refresh trước expiry, không giữ stale CRL vô hạn?
17. **Publication:** Tất cả CDP/region có cùng trạng thái/version theo kế hoạch?
18. **Signer security:** CRL signing key được bảo vệ, ưu tiên HSM/least privilege?
19. **CA compromise:** Có emergency distrust path cho Intermediate/Root khi CRL không đủ?
20. **Root trust anchor:** Không giả định root tự bị loại khỏi trust store qua CRL?
21. **Fail policy:** Explicit revoked luôn bị từ chối; stale/unavailable/unknown có policy riêng?
22. **Java PKIX:** PKIXRevocationChecker/CertStore được cấu hình và test đúng provider?
23. **Hostname:** TLS endpoint identification được kiểm tra riêng với path validation?
24. **IAM:** Certificate revoked được đồng bộ với workload sessions, tokens và KMS grants?
25. **Session:** Long-lived TLS/gRPC channels có quy trình terminate/re-authenticate?
26. **Tests:** Có revoked, stale, bad signature, wrong issuer, wrong scope, delta mismatch và outage cases?
27. **Monitoring:** Có CRL age, publication lag, fetch failures và effective rejection metrics?
28. **Audit:** Ghi issuer/serial, CRL number, actor, timestamps và decision mà không log secrets?
29. **Inventory:** Mỗi issuer có owner, cadence, CDP, clients và recovery plan?
30. **Final acceptance:** Có bằng chứng clients trọng yếu từ chối certificate revoked và vẫn chấp nhận certificate hợp lệ?

## 17. Câu hỏi tự kiểm tra

**Câu 1.** CRL là gì?

**Trả lời:** CRL là danh sách X.509 do CA hoặc CRL issuer được ủy quyền ký, chứa các certificate bị thu hồi trong một scope xác định.

**Câu 2.** Vì sao CRL cần issuer và serial?

**Trả lời:** Serial number không phải ID toàn cục; nó chỉ có ý nghĩa trong phạm vi issuer. Phải đối chiếu issuer + serial và CRL scope.

**Câu 3.** Chữ ký CRL hợp lệ có đủ để tin CRL không?

**Trả lời:** **Không.** Cần xác minh signer authority, cRLSign, issuer/AKI, scope, freshness, critical extensions và policy.

**Câu 4.** thisUpdate và nextUpdate có ý nghĩa gì?

**Trả lời:** thisUpdate cho biết thời điểm CRL được phát hành/cập nhật; nextUpdate cho biết thời điểm dự kiến có bản mới. Chúng hỗ trợ đánh giá freshness.

**Câu 5.** CRL không có entry của certificate có luôn nghĩa certificate good không?

**Trả lời:** **Không.** Chỉ có ý nghĩa khi CRL đúng issuer, đầy đủ, còn mới, đúng scope và bao phủ certificate/reasons cần kiểm tra.

**Câu 6.** CRL Number dùng để làm gì?

**Trả lời:** Nhận diện/versioning CRL trong issuer/scope và hỗ trợ phát hiện rollback; không so như bộ đếm toàn cục giữa CA khác nhau.

**Câu 7.** Base CRL và delta CRL khác nhau thế nào?

**Trả lời:** Base/full CRL là snapshot trong scope; delta chỉ chứa thay đổi kể từ base phù hợp. Validator phải ghép đúng base và delta.

**Câu 8.** Có thể chỉ tải delta CRL rồi dùng như full CRL không?

**Trả lời:** **Không.** Delta cần base CRL tương ứng và merge theo quy tắc PKIX.

**Câu 9.** Indirect CRL là gì?

**Trả lời:** CRL do một CRL issuer khác issuer của certificate phát hành; entry có thể dùng certificateIssuer để xác định issuer thật.

**Câu 10.** Issuing Distribution Point giúp gì?

**Trả lời:** Xác định scope CRL, có thể giới hạn certificate class, distribution point hoặc reason coverage.

**Câu 11.** CDP và AIA khác nhau thế nào?

**Trả lời:** CDP chỉ nơi lấy CRL; AIA thường chỉ issuer certificate hoặc OCSP responder. Không dùng chúng thay thế nhau.

**Câu 12.** KeyUsage cRLSign có vai trò gì?

**Trả lời:** Chỉ ra public key/certificate được phép ký CRL theo profile. Validator phải xác thực quyền của CRL signer.

**Câu 13.** revocationDate và invalidityDate có thể khác nhau không?

**Trả lời:** **Có.** invalidityDate có thể chỉ thời điểm key/certificate được cho là mất tin cậy, sớm hơn lúc CA ghi nhận revocation.

**Câu 14.** removeFromCRL có nghĩa gì?

**Trả lời:** Entry đặc biệt dùng trong CRL processing, thường cho việc gỡ certificateHold trong delta CRL theo semantics phù hợp; không phải nút undo chung cho key compromise.

**Câu 15.** Nếu CRL endpoint timeout, có thể coi certificate good không?

**Trả lời:** **Không mặc định.** Phải áp dụng fail-open/fail-closed policy và risk acceptance. Lỗi fetch không phải bằng chứng good.

**Câu 16.** Nếu CRL báo certificate revoked rõ ràng, soft-fail có được bỏ qua không?

**Trả lời:** **Không.** Soft-fail không được override explicit revoked status đã xác thực.

**Câu 17.** CRL có tự đóng TLS connection đang mở không?

**Trả lời:** **Không.** Cần terminate/drain sessions hoặc buộc re-authenticate theo incident policy.

**Câu 18.** CRL có thay thế IAM revoke KMS grants không?

**Trả lời:** **Không.** Certificate trust và KMS authorization là các control plane khác nhau.

**Câu 19.** Root CA compromise có thể chỉ publish CRL để mọi client ngừng tin root không?

**Trả lời:** **Không.** Root thường là trust anchor cài sẵn; cần distrust/update trust store qua kênh quản trị riêng.

**Câu 20.** Java X509Certificate.checkValidity() có kiểm tra CRL không?

**Trả lời:** **Không.** Nó kiểm tra notBefore/notAfter. Revocation cần PKIX checker hoặc cơ chế tương ứng.

**Câu 21.** Parse CRL thành X509CRL có chứng minh chữ ký CRL hợp lệ không?

**Trả lời:** **Không.** Parse chỉ đọc cấu trúc. Cần verify chữ ký và signer authorization, hoặc dùng PKIX validation.

**Câu 22.** PKIX path validation có tự kiểm tra hostname không?

**Trả lời:** **Không nên giả định.** TLS endpoint identification/SAN validation cần được cấu hình trong TLS client.

**Câu 23.** CRL signer private key bị lộ có thể gây hậu quả gì?

**Trả lời:** Attacker có thể tạo CRL giả trong phạm vi signer, bỏ entry revoked hoặc thêm entry để gây DoS. Cần bảo vệ signer key và xử lý compromise.

**Câu 24.** Vì sao cần test actual TLS handshake sau khi publish CRL?

**Trả lời:** Vì client có thể không bật CRL checking, cache stale, không hỗ trợ extension hoặc xử lý fallback khác. Chỉ handshake test chứng minh hành vi thực tế của stack được hỗ trợ.

## 18. Tổng kết

**CRL** là cơ chế PKI công bố các certificate đã bị thu hồi, giúp relying parties ngừng tin certificate trước khi hết hạn. Một CRL hợp lệ cần được kiểm tra **issuer, signature, signer authorization, scope, freshness, version và entries**. Việc chỉ tải một file và tìm serial không đủ bảo đảm certificate status đúng.

Những nguyên tắc cần nhớ:

- **Issuer + serial:** không coi serial là định danh toàn cục.
- **Signature + authorization:** xác minh CRL signer và quyền cRLSign.
- **Scope:** kiểm tra CDP, IDP, reason flags và indirect issuer mapping.
- **Base/delta:** ghép delta với base đúng; không dùng delta như full CRL.
- **Freshness:** thisUpdate, nextUpdate, CRL Number và cache phải được quản lý; chữ ký hợp lệ không làm CRL cũ trở nên mới.
- **Reason semantics:** hiểu keyCompromise, cACompromise, certificateHold, invalidityDate và removeFromCRL.
- **Client enforcement:** CA publish không chứng minh mọi client đã nhận status; cần negative TLS/mTLS tests.
- **PKI và IAM:** CRL không xóa private key, không thu hồi KMS grants và không đóng session hiện tại.
- **Trust anchor:** Root CA compromise cần emergency distrust/trust-store update, không chỉ CRL.

**Điểm cốt lõi:** CRL chỉ bảo vệ hệ thống khi relying party xác minh đúng **nguồn phát hành, chữ ký, phạm vi, thời gian và trạng thái certificate**, rồi thực sự từ chối credential đã bị thu hồi. Kết hợp **PKIX validation, CRL publication đáng tin, cache/freshness policy, monitoring và kiểm thử TLS thực tế** giúp quá trình revocation có hiệu lực và kiểm chứng được.
