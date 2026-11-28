# Certificate revocation trước destruction — Thu hồi niềm tin trước khi hủy khóa

## 1. Vì sao phải revocation trước destruction?

**Certificate revocation** là việc tổ chức phát hành chứng chỉ hoặc cơ chế trust có thẩm quyền tuyên bố một chứng chỉ **không còn được tin cậy trước thời điểm hết hạn ghi trong certificate**. **Key destruction** là quá trình hủy vật liệu khóa bí mật (hoặc loại bỏ khả năng khôi phục vật liệu đó) theo chính sách. Hai hành động này liên quan nhưng không thay thế nhau:

- **Revocation thay đổi quyết định tin cậy của relying parties** đối với certificate/public key/identity.
- **Destruction loại bỏ private key material** tại những nơi tổ chức kiểm soát.

Ví dụ: một dịch vụ thanh toán dùng **certificate X.509** để xác thực máy chủ và private key trong HSM để thực hiện TLS handshake. Khi private key bị nghi lộ, tổ chức cần **ngừng dùng key cho handshake mới, thu hồi certificate, phát tán trạng thái thu hồi và thay certificate/key**. Nếu hủy private key trước khi ghi nhận bằng chứng, đối chiếu phụ thuộc và triển khai thay thế, có thể mất khả năng điều tra hoặc gây gián đoạn. Nếu chỉ hủy key mà không cập nhật revocation/trust, relying parties có thể vẫn chấp nhận certificate cũ cho tới expiry hoặc cho tới khi họ tự cập nhật trust.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài thuộc chương **Key destruction**. Chủ đề kết nối vòng đời khóa, PKI, chữ ký số, KMS/HSM, kiểm soát truy cập, rotation, revocation, backup/recovery và kiểm toán.

> **Nguyên tắc:** Trước khi hủy private key gắn với certificate, phải xác định certificate đó còn được ai tin, trạng thái thu hồi được công bố bằng cách nào, relying parties đã áp dụng chưa, và bằng chứng lịch sử nào cần giữ. Với key đã bị compromise đang gây nguy cơ, containment phải diễn ra ngay; không trì hoãn chặn sử dụng chỉ để hoàn thành một trình tự giấy tờ.

### 1.1. Bốn khái niệm cần phân biệt

| Khái niệm | Đối tượng | Ý nghĩa |
| --- | --- | --- |
| **Certificate expiry** | Certificate | Hết thời gian hiệu lực notAfter; không nhất thiết do sự cố |
| **Certificate revocation** | Trạng thái tin cậy của certificate | Certificate bị tuyên bố không còn hợp lệ trước expiry |
| **Key disable/retirement** | Operation của key tại KMS/HSM | Ngừng một hoặc nhiều thao tác như Sign/Decrypt/Agree |
| **Key destruction** | Private/secret key material | Hủy vật liệu khóa theo quy trình; có thể không thể phục hồi |

**Certificate không phải private key.** Certificate X.509 thường chứa public key, subject/issuer, validity, key usage, extensions và chữ ký của CA. Hủy private key **không xóa certificate đã phát hành**, không tự cập nhật CRL/OCSP và không khiến tất cả clients biết certificate đã bị thu hồi.

### 1.2. Vì sao “hủy key rồi là xong” sai?

Giả sử attacker đã sao chép private key trước khi tổ chức hủy nó. Attacker vẫn có thể dùng bản sao để ký hoặc thực hiện các phép toán tương ứng bên ngoài hệ thống. Nếu certificate vẫn được relying parties tin, chữ ký hoặc danh tính giả có thể được chấp nhận.

Ngược lại, nếu certificate đã bị revoke nhưng private key vẫn còn trong HSM, một ứng dụng có quyền Sign vẫn có thể tạo chữ ký toán học hợp lệ. **Revocation không xóa key, và destruction không tự thu hồi trust.** Cần thực hiện cả hai theo mục tiêu.

## 2. Mối quan hệ giữa certificate, public key và private key

### 2.1. Thành phần của một certificate X.509

Một certificate thường chứa:

- **Subject:** danh tính hoặc tên chủ thể được chứng nhận.
- **Subject Public Key Info (SPKI):** public key và thuật toán.
- **Issuer:** CA phát hành certificate.
- **Validity:** notBefore và notAfter.
- **Key Usage / Extended Key Usage:** mục đích sử dụng được phép, ví dụ digitalSignature, keyEncipherment, serverAuth hoặc clientAuth.
- **Subject Alternative Name (SAN):** DNS name, URI hoặc danh tính khác theo profile.
- **Serial Number:** số định danh certificate trong phạm vi issuer.
- **Extensions:** chính sách, CRL distribution points, Authority Information Access/OCSP, constraints và các thông tin khác.
- **Issuer Signature:** chữ ký của CA bảo vệ nội dung certificate.

Certificate công bố public key. Private key tương ứng thường được lưu trong **HSM, KMS, keystore hoặc thiết bị được kiểm soát**. Một certificate có thể được copy đến nhiều verifiers; private key không cần được phân phối cho họ.

### 2.2. Revocation tác động lên certificate/identity, không xóa public key

Sau khi certificate bị revoke:

- Public key vẫn có thể được đọc từ certificate.
- Phép Verify chữ ký bằng public key vẫn có thể trả về **true**.
- Relying party phải áp dụng **certificate status/revocation policy** trước khi tin kết quả.
- Private key có thể vẫn tồn tại ở HSM/backup và phải được xử lý riêng.
- Certificate và metadata có thể cần lưu để kiểm toán, xác minh chữ ký lịch sử hoặc điều tra.

Do đó, **cryptographic verification** và **trust validation** là hai lớp. Verify chữ ký thành công không tự chứng minh certificate còn được tin.

### 2.3. Certificate revocation khác key revocation

Trong vận hành, người ta thường nói “revoke key”, nhưng PKI thường công bố trạng thái **certificate**. Một key pair có thể được gắn với nhiều certificate ở các profiles/issuers khác nhau. Thu hồi một certificate không tự động thu hồi mọi certificate dùng cùng public key.

Inventory phải truy vết:

- Key ID/material version trong KMS/HSM.
- Public key fingerprint/SPKI hash.
- Certificate serial number và issuer.
- Những certificate khác có cùng public key.
- Workloads/hosts/clients đang dùng từng certificate.
- Các aliases, backups và private-key copies.

Nếu cùng một private key được tái sử dụng cho nhiều certificate, phải đánh giá **tất cả các certificate và relying parties**; không chỉ revoke serial number đầu tiên.

## 3. Khi nào cần thu hồi certificate?

Certificate revocation thường cần khi một hoặc nhiều giả định về danh tính, quyền sử dụng hoặc bảo vệ private key không còn đúng.

| Nguyên nhân | Ví dụ | Hướng đánh giá |
| --- | --- | --- |
| **Private key compromise** | Private key xuất hiện trong log/public repository | Thu hồi sớm, thay key/certificate, điều tra phạm vi |
| **Unauthorized key use** | Sign/TLS authentication bất thường qua HSM | Revoke khi trust không còn đảm bảo; điều tra API abuse |
| **Identity/subject information sai** | DNS domain hoặc subject không còn thuộc chủ thể | Thu hồi/cấp lại certificate đúng |
| **Subscriber relationship kết thúc** | Đối tác hoặc nhân sự không còn quyền đại diện | Chấm dứt certificate theo policy/contract |
| **CA compromise** | Intermediate CA private key bị lộ | Xử lý certificate subtree/trust theo PKI incident plan |
| **Algorithm/profile không còn phù hợp** | Key size, signature algorithm hoặc extension vi phạm policy mới | Migration, revoke/reissue theo mức rủi ro |
| **Certificate issued in error** | CA cấp nhầm subject/SAN/EKU | Thu hồi và điều tra issuance workflow |
| **Device/service decommission** | Host hoặc thiết bị đã bị loại bỏ | Thu hồi nếu certificate không còn cần và policy yêu cầu |
| **Private key lost** | Không còn kiểm soát key và không thể chứng minh custody | Có thể cần revoke vì không thể bảo đảm quyền sử dụng |

### 3.1. Compromise và routine retirement

**Compromise** cần ưu tiên ngăn attacker tiếp tục dùng key. **Routine retirement** có thể được lên lịch trước expiry, có overlap cho rollout nếu key vẫn an toàn.

Không áp dụng grace period cho private key đã xác nhận lộ chỉ vì clients chưa kịp cập nhật. Nếu availability buộc phải duy trì tương thích, cần incident commander phê duyệt biện pháp bù trừ, scope và deadline rõ ràng.

### 3.2. Certificate hết hạn không giống bị revoke

Khi validity notAfter đã qua, certificate không còn hiệu lực theo validity checking thông thường. Nhưng:

- Certificate có thể bị revoke **trước** ngày hết hạn.
- Một certificate hết hạn không tự tạo CRL entry.
- Historical signature validation có thể cần đánh giá certificate status **tại thời điểm ký**, theo policy và bằng chứng thời gian.
- Không dùng việc chờ expiry như biện pháp xử lý compromise nếu key vẫn đang được tin trong thời gian còn lại.

## 4. CRL: Certificate Revocation List

**CRL** là danh sách được CA/CRL issuer ký, công bố các certificate bị thu hồi trong phạm vi và thời kỳ áp dụng. Relying party có thể tải CRL, xác minh chữ ký và kiểm tra serial number của certificate đang xác thực.

### 4.1. Cách CRL hoạt động

~~~mermaid
sequenceDiagram
    participant CA as CA / CRL issuer
    participant DP as CRL Distribution Point
    participant RP as Relying Party
    CA->>CA: Ghi nhận certificate bị revoke
    CA->>CA: Tạo CRL mới và ký CRL
    CA->>DP: Publish CRL
    RP->>DP: Fetch CRL theo certificate extension/config
    DP-->>RP: CRL + issuer/signature metadata
    RP->>RP: Verify CRL signature, issuer, time và scope
    RP->>RP: Tra serial number
    RP-->>RP: Reject hoặc tiếp tục validation theo policy
~~~

Relying party cần kiểm tra tối thiểu:

- CRL được ký bởi **đúng issuer/CRL issuer** và chữ ký hợp lệ.
- CRL nằm trong đúng **scope**, ví dụ CA, distribution point, certificate type hoặc reason coverage.
- thisUpdate và nextUpdate phù hợp với thời gian hiện tại.
- Serial number của certificate có xuất hiện trong danh sách không.
- Nếu dùng delta CRL, đã kết hợp đúng base CRL và delta CRL theo profile.
- Cache/refresh behavior đáp ứng freshness policy.

### 4.2. CRL có thể không cập nhật tức thì

CA có thể chỉ publish CRL theo lịch hoặc sau một khoảng thời gian. Nếu CRL mới chưa được phát hành, relying party dùng CRL cũ có thể **chưa biết** certificate đã bị revoke.

Do đó, sau compromise cần xem:

- CA/issuer có thể publish CRL khẩn cấp không?
- CRL Distribution Point có sẵn sàng ở mọi mạng/vùng không?
- Client cache CRL bao lâu?
- Client có kiểm tra nextUpdate và từ chối CRL quá cũ không?
- Có delta CRL hoặc cơ chế cập nhật trạng thái khác không?
- Những client offline có cách nhận bản cập nhật khi trở lại không?

### 4.3. CRL không phải danh sách private keys bị hủy

CRL thường chứa **certificate serial numbers và revocation metadata**, không chứa private keys. Một certificate serial có thể bị revoke trong khi private key vẫn tồn tại. Ngược lại, private key có thể bị hủy vì hết nhu cầu nhưng certificate không nhất thiết được đưa vào CRL nếu lifecycle/policy chọn cách xử lý khác.

### 4.4. CRL và CA hierarchy

CRL phải được xác minh theo đúng issuer và scope. Với **intermediate CA**, parent CA có thể phát hành CRL thu hồi certificate của intermediate. Với **root CA tự ký**, việc “root tự revoke chính nó” không tự buộc các relying parties xóa trust anchor. Root trust thường được quản lý qua trust-store distribution và governance riêng.

Không suy rằng mọi CA revocation đều có thể xử lý bằng cách thêm một serial number vào CRL duy nhất.

## 5. OCSP: Online Certificate Status Protocol

**OCSP** cho phép relying party hỏi một responder về trạng thái của certificate, thường theo issuer và serial number. Responder trả lời như **good**, **revoked** hoặc **unknown** trong một response có chữ ký và khoảng hiệu lực.

### 5.1. Luồng OCSP cơ bản

~~~mermaid
sequenceDiagram
    participant RP as Relying Party
    participant OR as OCSP Responder
    participant CA as Issuer / PKI
    RP->>OR: OCSP request (issuer + serial)
    OR->>CA: Lấy status từ revocation database/cache
    CA-->>OR: Certificate status và revocation metadata
    OR-->>RP: Signed OCSP response
    RP->>RP: Verify responder authorization/signature
    RP->>RP: Kiểm tra certID, thisUpdate, nextUpdate
    RP-->>RP: Áp dụng status và local policy
~~~

### 5.2. Ý nghĩa của các trạng thái

| OCSP status | Ý nghĩa khái quát | Quyết định |
| --- | --- | --- |
| **good** | Responder không báo certificate đã bị revoke trong phạm vi response | Vẫn cần kiểm tra signature, freshness, issuer và policy |
| **revoked** | Certificate đã bị thu hồi | Từ chối theo validation policy; xem thời điểm/reason |
| **unknown** | Responder không biết hoặc không thể cung cấp trạng thái cho certificate | Không diễn giải thành good; áp dụng fail policy |

**OCSP good không phải một chứng thư độc lập khẳng định mọi khía cạnh của certificate đều hợp lệ.** Vẫn phải xác minh chain, validity, name, key usage, algorithm, issuer và những kiểm tra khác.

### 5.3. OCSP response freshness

Relying party cần kiểm tra:

- Response được ký bởi responder được ủy quyền (ví dụ CA hoặc delegated responder).
- CertID khớp issuer và serial đang kiểm tra.
- thisUpdate, nextUpdate và producedAt phù hợp policy/clock.
- Signature và certificate của responder hợp lệ.
- Response không thuộc một issuer hoặc certificate khác.

Một response cũ có trạng thái good có thể không phản ánh revocation mới. **Cache TTL** phải cân bằng freshness, availability và privacy; không kéo dài vô hạn để tránh gọi responder.

### 5.4. OCSP privacy và availability

OCSP request có thể tiết lộ cho responder website/service mà client đang truy cập. Nó cũng phụ thuộc network và responder availability. Một số hệ thống dùng **OCSP stapling** để server gửi response đã ký trong TLS handshake, giảm truy vấn trực tiếp từ từng client.

Tuy nhiên, stapling cần freshness và policy kiểm tra phù hợp; một response stapled cũ không tự đảm bảo trạng thái hiện tại.

## 6. OCSP stapling và Must-Staple

### 6.1. OCSP stapling

Trong OCSP stapling, server lấy OCSP response hợp lệ cho certificate và gửi kèm trong TLS handshake. Client kiểm tra response thay vì nhất thiết phải truy vấn OCSP responder trực tiếp.

Lợi ích:

- Giảm lượng truy vấn OCSP từ clients.
- Giảm việc client tiết lộ cho responder website đang truy cập.
- Có thể cải thiện hiệu năng và giảm phụ thuộc trực tiếp vào responder tại thời điểm handshake.

Giới hạn:

- Server phải cập nhật response trước khi hết hạn.
- Client phải thực sự kiểm tra signature, issuer và freshness.
- Nếu client **soft-fail** khi không có stapled response, revocation có thể không được cưỡng chế như kỳ vọng.
- Không phải mọi TLS stack/client đều hỗ trợ hoặc áp dụng cùng một policy.

### 6.2. Must-Staple

Một số PKI/TLS profiles hỗ trợ extension yêu cầu server cung cấp OCSP response trong handshake (thường được gọi là **TLS Feature/Must-Staple**). Khi client hỗ trợ và thực thi extension, thiếu response phù hợp có thể làm handshake thất bại.

Must-Staple có thể giảm rủi ro client im lặng bỏ qua revocation status, nhưng tăng yêu cầu availability và vận hành OCSP stapling. Phải kiểm tra **client support, certificate profile và TLS implementation** thực tế.

### 6.3. Không nhầm stapling với certificate replacement

Stapling chỉ phân phối **status evidence**. Nó không thay certificate, không xóa private key và không tự chuyển service sang key mới. Sau khi certificate bị revoke, server vẫn cần **ngừng trình certificate/key cũ** và cài certificate mới theo rollout.

## 7. Revocation reason và thời điểm thu hồi

Certificate revocation không chỉ là một cờ true/false. CRL có thể ghi **reason code**, thời điểm và những extension liên quan để giải thích lý do certificate bị thu hồi.

### 7.1. Một số reason codes thường gặp

| Reason | Ý nghĩa khái quát | Tình huống |
| --- | --- | --- |
| **keyCompromise** | Private key tương ứng bị xâm phạm | Private key xuất hiện ngoài boundary |
| **cACompromise** | Private key của CA bị xâm phạm | Intermediate/CA signing key bị lộ |
| **affiliationChanged** | Quan hệ/tổ chức của chủ thể thay đổi | Subject không còn thuộc tổ chức cũ |
| **superseded** | Certificate bị thay thế | Cấp certificate mới theo rollover |
| **cessationOfOperation** | Hoạt động được certificate hỗ trợ đã dừng | Service/device ngừng hoạt động |
| **certificateHold** | Tạm thời đặt certificate vào trạng thái hold theo profile | Đang điều tra, chưa đưa ra quyết định cuối |
| **privilegeWithdrawn** | Quyền gắn với certificate bị rút | Chủ thể không còn được phép thực hiện hoạt động |
| **aACompromise** | Attribute authority key bị compromise | Hệ thống dùng attribute certificates |
| **unspecified** | Không chỉ rõ reason cụ thể | Policy không yêu cầu hoặc không có reason phù hợp |

Các reason codes và cách sử dụng phải theo **X.509/PKI profile** của hệ thống. Không chọn **certificateHold** cho một private key đã xác nhận compromise chỉ để có thể “bỏ hold” sau này, nếu policy yêu cầu thu hồi vĩnh viễn.

### 7.2. Revocation date và invalidity date

Phải phân biệt:

- **Revocation date:** Thời điểm được ghi nhận trong revocation information theo quy trình issuer.
- **Invalidity date:** Extension có thể chỉ ra thời điểm sớm hơn mà certificate/private key được cho là đã mất hiệu lực hoặc bị compromise.
- **Detection time:** Khi tổ chức phát hiện sự cố.
- **Publication time:** Khi CRL/OCSP/trust update thực sự được phát hành.
- **Enforcement time:** Khi relying parties thực tế bắt đầu từ chối certificate theo policy.

Ví dụ, private key có thể bị copy ngày 10-11, được phát hiện ngày 14-11, certificate được CA ghi nhận revoke ngày 14-11, CRL mới được publish ngày 14-11 và một số clients chỉ tải lại CRL ngày 15-11. **Không gộp các mốc này thành một thời điểm duy nhất.**

### 7.3. Vì sao thời điểm compromise quan trọng?

Với chữ ký lịch sử, thời điểm private key có thể đã bị lộ ảnh hưởng đánh giá liệu chữ ký được tạo trước/sau compromise có đáng tin. Nếu không có trusted timestamp hoặc evidence độc lập, không thể chỉ tin trường signedAt do ứng dụng ghi.

Trong báo cáo incident, hãy ghi **earliest known compromise, earliest observed misuse, detection, revocation publication và consumer enforcement** cùng mức chắc chắn của từng mốc.

## 8. Quy trình certificate revocation trước key destruction

Thứ tự chi tiết phụ thuộc loại key/certificate và tình huống, nhưng cần đảm bảo **trust bị thu hồi và relying parties có thể áp dụng** trước khi kết thúc vòng đời key. Với compromise đang diễn ra, containment phải diễn ra ngay và có thể chạy song song với phát hành revocation.

### 8.1. Planned retirement

1. **Inventory:** Liệt kê key ID/version, certificate serial/issuer, public key fingerprint, hosts, services và relying parties.
2. **Prepare replacement:** Sinh key mới nếu cần, phát hành certificate mới, cập nhật trust/consumers.
3. **Cutover:** Dừng dùng certificate/private key cũ cho handshake/signing mới.
4. **Revoke:** Thu hồi certificate cũ khi policy yêu cầu; publish CRL/OCSP status.
5. **Propagate:** Xác minh các relying parties, caches, proxies và partner systems đã áp dụng.
6. **Preserve evidence:** Lưu certificate/public key, chain, serial, status response, timestamps và audit theo retention.
7. **Disable:** Chặn Sign/Decrypt/Agree bằng private key cũ tại KMS/HSM theo policy.
8. **Dependency review:** Kiểm tra dữ liệu/chữ ký lịch sử, backups, DR và legal hold.
9. **Destroy:** Hủy private key material và bản sao được kiểm soát khi đủ điều kiện.
10. **Verify:** Kiểm tra key không còn sử dụng/khôi phục được trong phạm vi đã định và báo cáo residual copies.

### 8.2. Emergency revocation khi compromise

~~~mermaid
flowchart TD
    A["Phát hiện key/certificate compromise"] --> B["Contain ngay: chặn Sign/handshake mới,<br/>thu hồi credentials/grants cần thiết"]
    B --> C["Bảo toàn evidence và xác định<br/>certificate serial + issuer + key version"]
    C --> D["Yêu cầu CA/issuer revoke certificate"]
    D --> E["Publish CRL/OCSP hoặc trust update"]
    E --> F["Phát hành key/certificate thay thế<br/>và cập nhật relying parties"]
    F --> G["Kiểm tra cache, offline clients,<br/>TLS sessions và consumer acknowledgements"]
    G --> H["Preserve public cert, chain,<br/>revocation evidence và audit"]
    H --> I["Dependency, backup/DR,<br/>legal hold và destruction review"]
    I --> J["Disable/destroy private key cũ<br/>khi đủ điều kiện"]
    J --> K["Negative tests + residual risk report"]
~~~

Trong compromise, không đợi publish CRL rồi mới chặn key ở HSM nếu có thể đang bị sử dụng. **Containment ở key-use boundary và revocation tại PKI** là hai luồng phối hợp, không phải hai bước buộc phải tuần tự.

### 8.3. Vì sao cần giữ public certificate sau destruction?

Private key có thể bị hủy, nhưng public certificate có thể cần lưu để:

- Xác minh chữ ký lịch sử.
- Điều tra key usage và certificate issuance.
- Chứng minh serial/issuer/validity/revocation reason.
- Hỗ trợ long-term validation hoặc dispute resolution.
- Đối chiếu truststore, CRL, OCSP và các phiên bản certificate.

**Không xóa certificate/public key khỏi evidence store chỉ vì private key đã bị destroy.** Public material không phải secret; tuy nhiên hồ sơ vẫn có thể chứa metadata nhạy cảm và cần retention/access policy.

## 9. Certificate revocation không tự lan truyền tới mọi relying party

Đưa certificate vào CRL hoặc cập nhật OCSP là **công bố trạng thái**, nhưng việc các client áp dụng phụ thuộc cấu hình, thời gian cache, network và policy.

### 9.1. Các điểm có thể trì hoãn enforcement

- Client không kiểm tra revocation.
- Client dùng **soft-fail** khi CRL/OCSP unavailable.
- CRL/OCSP cache chưa hết TTL.
- OCSP response stapled vẫn còn trong thời hạn được chấp nhận.
- Client offline hoặc bị chặn truy cập distribution points.
- TLS connection/session đã được thiết lập trước thời điểm revoke.
- Application dùng truststore/JWKS cache riêng ngoài PKIX validator.
- Một region/proxy/partner chưa nhận certificate mới.

### 9.2. Soft-fail và hard-fail

| Policy | Khi không lấy được trạng thái revocation | Đánh đổi |
| --- | --- | --- |
| **Soft-fail** | Có thể tiếp tục validation nếu các kiểm tra khác đạt | Tăng availability, nhưng có thể chấp nhận certificate đã revoke khi status service lỗi |
| **Hard-fail** | Từ chối khi không xác minh được status theo policy | Tăng enforcement, nhưng OCSP/CRL outage có thể làm gián đoạn dịch vụ |

Không có lựa chọn duy nhất cho mọi môi trường. Với **high-risk client authentication hoặc CA trust**, policy có thể yêu cầu hard-fail. Với môi trường khác, cần phân tích availability và biện pháp bù trừ. Quyết định phải được ghi rõ, kiểm thử và phê duyệt.

### 9.3. Đóng các kết nối và session hiện hữu

Revocation check thường diễn ra trong quá trình certificate validation/handshake, không tự động ngắt mọi TLS connection đang mở. Khi certificate bị compromise:

- Xem xét **drain/close existing connections**.
- Vô hiệu hóa session tickets/resumption theo TLS implementation khi cần.
- Thu hồi application sessions/tokens nếu chúng dựa vào identity bị compromise.
- Roll out certificate/key mới tới load balancers, proxies, sidecars và backends.
- Kiểm tra mTLS peer authentication ở cả client và server.

Không giả định thay file certificate trên disk sẽ tự thay certificate của các **SSLContext/connection pools** đã được tạo trước đó.

### 9.4. Đo revocation propagation

Nên có metric:

- Thời điểm CA ghi nhận revoke và publish CRL/OCSP.
- Thời điểm từng region/client tải status mới.
- Tỷ lệ verifier đã từ chối certificate cũ trong negative tests.
- Số client offline/unacknowledged.
- Tỷ lệ handshake vẫn trình certificate serial cũ.
- Cache age và response freshness.

**“CRL đã publish” không tương đương “mọi relying party đã từ chối certificate”.**

## 10. CA certificate revocation và trust anchor removal

Revocation của leaf certificate khác revocation của intermediate/root CA certificate vì **CA nằm trong chuỗi phát hành và có thể ảnh hưởng nhiều certificate con**.

### 10.1. Leaf certificate

Leaf certificate thường đại diện cho server, client, user hoặc service. Khi revoke:

- Issuer đưa serial của leaf vào CRL hoặc OCSP status.
- Relying parties kiểm tra chain và revocation theo policy.
- Service thay certificate/private key và cập nhật endpoint.
- Chữ ký hoặc phiên cũ được đánh giá theo policy thời gian/trust.

### 10.2. Intermediate CA certificate

Intermediate CA được parent CA cấp certificate và dùng private key để ký certificates khác. Nếu intermediate private key compromise:

1. Dừng issuance/CA signing bằng key đó.
2. Parent CA xem xét revoke **intermediate CA certificate**.
3. Công bố status và hướng dẫn relying parties xử lý chain.
4. Đánh giá các certificates do intermediate phát hành.
5. Tạo intermediate/key mới và cập nhật CA hierarchy/trust.
6. Giữ bằng chứng certificate issuance, CRLs, OCSP và các artifacts lịch sử.

Nếu intermediate key bị compromise, các certificate con có thể đã được attacker phát hành ngoài hệ thống CA. Chỉ revoke certificate của một leaf cụ thể là không đủ nếu chưa đánh giá toàn bộ issuance scope.

### 10.3. Root trust anchor

Root CA thường được cấu hình như **trust anchor** ở ngoài đường validation thông thường. Việc root certificate tự xuất hiện trong CRL hoặc tự ký một thông báo revoke **không tự khiến mọi relying party xóa nó khỏi trust store**.

Root key compromise thường đòi:

- Quyết định PKI governance về việc ngừng tin root.
- Phân phối trust-store update/removal tới relying parties.
- Thiết lập root/key mới và certificate hierarchy thay thế.
- Xử lý intermediate/leaf certificates phụ thuộc.
- Kiểm tra thiết bị offline, legacy clients và pinned roots.

### 10.4. CA signing key cần xử lý CRL/OCSP như thế nào?

Một CA thường dùng signing key để ký certificate và có thể ký CRL; OCSP responder có thể dùng key riêng hoặc delegated responder certificate. Khi CA key compromise:

- Không tiếp tục tin CRL/OCSP response mới chỉ vì chữ ký mật mã hợp lệ nếu signer đã mất trust.
- Xác định delegated CRL signer/OCSP responder có bị ảnh hưởng không.
- Dùng parent CA hoặc trust governance để công bố trạng thái phù hợp.
- Xử lý certificate chain và trust anchors theo PKI incident plan.

**Không mặc định CA đã revoke là vẫn có thể dùng chính CA key bị compromise để công bố trạng thái thu hồi đáng tin.**

## 11. Certificate revocation và historical signature validation

Một chữ ký được tạo trước ngày revoke có thể vẫn cần được kiểm tra nhiều năm sau. Vì vậy, **revocation hiện tại** và **đánh giá chữ ký tại thời điểm ký** là hai câu hỏi khác nhau.

### 11.1. Verify chữ ký khác kiểm tra certificate status

Quy trình xác minh chữ ký số có thể gồm:

1. Kiểm tra chữ ký trên đúng message/document bytes bằng public key.
2. Xây dựng và xác minh certificate path tới trust anchor được chấp nhận.
3. Kiểm tra validity, key usage, extended key usage, name constraints và policy.
4. Kiểm tra revocation status theo yêu cầu.
5. Nếu xác minh lịch sử, đánh giá certificate/key **ở thời điểm ký** bằng timestamp và evidence phù hợp.

Một phép Verify trả về true chỉ chứng minh phép toán chữ ký phù hợp với public key và bytes được kiểm tra. Nó không chứng minh certificate chưa bị revoke, signer có thẩm quyền nghiệp vụ hoặc chữ ký được tạo trước compromise.

### 11.2. Trusted timestamp hỗ trợ điều gì?

Một timestamp token từ **Time-Stamp Authority (TSA)** có thể cung cấp bằng chứng rằng một message imprint/signature đã tồn tại không muộn hơn một thời điểm được TSA xác nhận, theo profile và trust policy áp dụng.

Timestamp có thể hỗ trợ phân biệt chữ ký được tạo trước và sau thời điểm compromise, nhưng:

- TSA certificate và timestamp token cũng cần validation/revocation.
- Đồng hồ của ứng dụng hoặc trường signedAt tự khai không thay thế TSA.
- Timestamp không chứng minh người ký đã được business owner phê duyệt.
- Nếu key compromise có thể đã xảy ra trước timestamp, vẫn phải đánh giá evidence và policy.

### 11.3. Lưu public evidence sau private-key destruction

Đối với chữ ký cần xác minh lâu dài, cân nhắc lưu:

- Original signed bytes và signature.
- Certificate và chain liên quan, serial/issuer/fingerprint.
- Public key hoặc trust reference có thể tái dựng.
- CRL/OCSP response và thời điểm thu thập.
- Timestamp token, validation data và thuật toán.
- Audit event về signer principal, key ID/version, request/approval.
- Revocation reason, revocation date và invalidity date khi có.

**Không cần giữ private signing key chỉ để Verify chữ ký lịch sử.** Giữ private key có thể tiếp tục tạo chữ ký mới; public evidence và validation data mới phục vụ việc xác minh.

### 11.4. Revoked certificate vẫn có thể Verify toán học

Sau revocation, một thư viện có thể vẫn thực hiện phép Verify bằng public key trong certificate và trả true. Ứng dụng phải tách kết quả:

| Kiểm tra | Kết quả có thể có | Ý nghĩa |
| --- | --- | --- |
| Signature math | Valid | Chữ ký khớp public key/message |
| Certificate path | Valid/Invalid | Chain có được tin tới trust anchor không |
| Certificate status | Good/Revoked/Unknown | Status evidence theo issuer và policy |
| Time validation | Valid/Invalid/Indeterminate | Có đủ căn cứ cho thời điểm kiểm tra/ký không |
| Business authorization | Allowed/Denied | Người ký/nội dung có được phép không |

Không gộp các kết quả thành một boolean tổng quát nếu ứng dụng cần quyết định pháp lý hoặc thanh toán.

## 12. KMS/HSM: disable, revoke, delete và destroy

KMS/HSM quản lý **key material và quyền thực hiện crypto operations**; PKI quản lý certificate issuance/trust/revocation. Hai control planes phải được phối hợp.

### 12.1. Trạng thái không đồng nghĩa nhau

| Hành động/trạng thái | Ý nghĩa thường gặp | Câu hỏi cần xác minh |
| --- | --- | --- |
| **Disable** | Chặn operation qua backend | Sign/Decrypt/Agree nào bị chặn? Có propagation delay? |
| **Retire** | Ngừng dùng cho operation mới theo policy nội bộ | Có còn quyền Decrypt/Verify/Unwrap lịch sử? |
| **Certificate revoke** | Issuer công bố certificate không còn được tin | CRL/OCSP/trust update đã được relying parties áp dụng? |
| **Schedule deletion** | Lập lịch xóa theo cơ chế provider | Có waiting period/cancel window? |
| **Pending deletion** | Đang chờ xóa | Key material còn có thể khôi phục/disable không? |
| **Destroy** | Material bị hủy theo semantics provider | Backup, replicas, imports và recovery copies nào còn? |

Không suy từ trạng thái **PendingDeletion** rằng key đã bị xóa vĩnh viễn. Không suy từ trạng thái **Disabled** rằng mọi bản sao raw key bên ngoài cũng vô dụng.

### 12.2. Tách certificate lifecycle khỏi key lifecycle

Một quy trình quản lý nên theo dõi hai chuỗi trạng thái:

~~~text
CERTIFICATE:
  ISSUED -> ACTIVE -> REVOKED / EXPIRED -> ARCHIVED

PRIVATE KEY:
  GENERATED -> ACTIVE -> DISABLED/RETIRED
           -> DESTROY_PENDING -> DESTROYED
~~~

Hai chuỗi liên kết bằng **key ID, public key fingerprint, certificate serial/issuer và purpose**. Một private key có thể gắn nhiều certificates; một certificate có thể được thay bằng certificate mới dùng cùng key hoặc key mới. Policy phải ghi rõ tình huống nào được phép.

### 12.3. Không dùng certificate revocation để thay IAM revoke

Nếu attacker có quyền gọi HSM Sign API, revoke certificate có thể làm relying parties từ chối certificate, nhưng **HSM vẫn có thể thực hiện Sign**. Cần thu hồi IAM grant/session, chặn signer workload và disable key operation phù hợp.

Ngược lại, revoke IAM principal không tự làm relying parties ngừng tin certificate cũ nếu private key đã bị copy. Cần công bố revocation/trust update.

### 12.4. Hủy key và bản sao

Trước destruction, phải biết:

- Key material có trong HSM replicas, backup blobs hoặc disaster recovery domains không?
- Có file export, PKCS#12/PEM, keystore, secret manager version hoặc process dump không?
- Provider dùng logical key với nhiều material versions hay resource riêng?
- Delete có propagation và retention period như thế nào?
- Có recovery key/backup domain nào có thể restore lại material không?
- Certificate/public evidence nào phải giữ?

Nếu không thể chứng minh mọi bản copy đã bị hủy, báo cáo phải nêu **phạm vi đã xác minh và residual copies/unknowns**. Không tuyên bố “khóa bị xóa khỏi mọi nơi” dựa trên một API Delete thành công.

## 13. Destruction readiness: điều kiện trước khi hủy private key

Certificate revocation là một điều kiện quan trọng, nhưng không phải điều kiện duy nhất. Một key chỉ đủ điều kiện destruction khi **trust, dependencies, evidence, backup/DR và retention** đã được xử lý.

### 13.1. Checklist trước destruction

1. **Identity:** Xác định đúng key ID/version, public key fingerprint và mọi certificate dùng key đó.
2. **Issuer:** Xác định CA/issuer có thẩm quyền và quy trình revoke tương ứng.
3. **Revocation request:** Yêu cầu đã được CA tiếp nhận và serial/reason/time đúng?
4. **Publication:** CRL/OCSP hoặc trust-store update đã được publish?
5. **Propagation:** Relying parties/regions/partners đã áp dụng hoặc có residual risk được phê duyệt?
6. **Use containment:** HSM/KMS Sign/handshake/operation mới đã bị chặn theo mục tiêu?
7. **Replacement:** Certificate/key mới đã được triển khai nếu service cần tiếp tục hoạt động?
8. **Historical evidence:** Certificate, public key, chain, CRL/OCSP, timestamp và audit đã được giữ?
9. **Data dependencies:** Các encrypted data, signed records hoặc protocol dependencies có cần private key cũ không?
10. **Backups:** Snapshot, replicas, HSM backup domain và exported copies đã được kiểm kê?
11. **Recovery:** Có nhu cầu recovery hợp lệ nào còn tồn tại? Nếu có, đã có phương án an toàn?
12. **Legal/retention:** Legal hold, contract, regulatory retention và evidence requirements đã được kiểm tra?
13. **Approval:** Owner, Security/PKI, Data owner và operator đã phê duyệt theo separation of duties?
14. **Destruction:** Provider operation đã hoàn tất, không còn ở trạng thái pending?
15. **Verification:** Có evidence key không còn dùng/restore được trong phạm vi kiểm soát và có báo cáo residual copies?

### 13.2. Khi nào có thể cần giữ key cũ lâu hơn?

Một số **decryption keys** có thể cần giữ để mở dữ liệu lịch sử; một số **CA signing keys** có thể cần để hoàn thành hoạt động CA hoặc phát hành CRL/OCSP trong một kế hoạch chuyển đổi. Với private signing key leaf thông thường, nhu cầu giữ private key chỉ để Verify lịch sử thường không có cơ sở vì public key đủ cho Verify.

Nếu key cũ cần giữ tạm thời cho migration:

- Chỉ cho phép **operation tối thiểu**.
- Tách quyền người vận hành migration khỏi business signer.
- Có time limit, approval và audit.
- Không dùng key bị compromised để tạo chữ ký mới.
- Giữ key trong HSM boundary và lên kế hoạch destruction rõ.

### 13.3. Khi nào phải revoke ngay dù chưa thể destroy?

Nếu private key bị compromise, certificate cần được revoke theo incident policy ngay khi quyết định có thẩm quyền được đưa ra, kể cả khi:

- Dữ liệu lịch sử còn cần xử lý.
- Backup/DR chưa được di chuyển.
- Evidence collection chưa hoàn tất toàn bộ.
- Private key vẫn đang ở HSM vì cần containment/migration.

**Revocation không đòi hỏi phải destroy private key trước.** Có thể revoke trust, disable Sign và bảo toàn key trong boundary để điều tra/migration, rồi destroy khi đủ điều kiện.

## 14. Java 17: policy gate cho certificate status và destruction

Ví dụ sau mô hình hóa hai quyết định riêng:

- **Certificate acceptance:** relying party có thể chấp nhận certificate status evidence hay không?
- **Private-key destruction:** key có đủ điều kiện hủy hay không?

Nó không tự tải CRL/OCSP, không gọi KMS/HSM và không thay PKIX validation. Mục tiêu là thể hiện **revocation status phải được xử lý trước destruction**, còn destruction cần thêm điều kiện.

~~~java
import java.time.Instant;
import java.util.Objects;

public final class CertificateRevocationDestructionPolicy {
    private CertificateRevocationDestructionPolicy() {}

    enum CertificateStatus {
        GOOD, REVOKED, UNKNOWN, UNAVAILABLE
    }

    enum FailureMode {
        HARD_FAIL, SOFT_FAIL
    }

    record StatusEvidence(
            CertificateStatus status,
            boolean issuerVerified,
            boolean signatureVerified,
            Instant thisUpdate,
            Instant nextUpdate,
            Instant revocationTime
    ) {}

    record TrustDecision(boolean accepted, String reason) {}

    record DestructionPrerequisites(
            boolean certificateRevocationRequirementSatisfied,
            boolean relyingPartiesReviewed,
            boolean keyUseDisabled,
            boolean replacementReady,
            boolean publicEvidencePreserved,
            boolean backupAndReplicaReviewed,
            boolean dependenciesResolved,
            boolean retentionAndLegalHoldCleared,
            boolean independentApproval
    ) {}

    record DestructionDecision(boolean allowed, String reason) {}

    static TrustDecision evaluateCertificateStatus(
            StatusEvidence evidence,
            Instant now,
            FailureMode failureMode
    ) {
        Objects.requireNonNull(evidence);
        Objects.requireNonNull(now);
        Objects.requireNonNull(failureMode);

        if (!evidence.issuerVerified() ||
                !evidence.signatureVerified()) {
            return new TrustDecision(false, "STATUS_EVIDENCE_NOT_AUTHENTIC");
        }
        if (evidence.status() == CertificateStatus.REVOKED) {
            return new TrustDecision(false, "CERTIFICATE_REVOKED");
        }
        boolean fresh = evidence.thisUpdate() != null &&
                evidence.nextUpdate() != null &&
                !now.isBefore(evidence.thisUpdate()) &&
                now.isBefore(evidence.nextUpdate());
        if (!fresh || evidence.status() == CertificateStatus.UNKNOWN ||
                evidence.status() == CertificateStatus.UNAVAILABLE) {
            if (failureMode == FailureMode.HARD_FAIL) {
                return new TrustDecision(false, "STATUS_UNKNOWN_OR_STALE");
            }
            return new TrustDecision(false,
                    "SOFT_FAIL_REQUIRES_SEPARATE_LOCAL_RISK_DECISION");
        }
        return new TrustDecision(true, "STATUS_GOOD_AND_FRESH");
    }

    static DestructionDecision evaluateDestruction(
            DestructionPrerequisites p
    ) {
        Objects.requireNonNull(p);
        if (!p.certificateRevocationRequirementSatisfied()) {
            return new DestructionDecision(false, "REVOCATION_REQUIREMENT_NOT_SATISFIED");
        }
        if (!p.relyingPartiesReviewed()) {
            return new DestructionDecision(false, "RELYING_PARTIES_NOT_REVIEWED");
        }
        if (!p.keyUseDisabled()) {
            return new DestructionDecision(false, "KEY_USE_NOT_DISABLED");
        }
        if (!p.replacementReady()) {
            return new DestructionDecision(false, "REPLACEMENT_NOT_READY");
        }
        if (!p.publicEvidencePreserved()) {
            return new DestructionDecision(false, "PUBLIC_EVIDENCE_NOT_PRESERVED");
        }
        if (!p.backupAndReplicaReviewed()) {
            return new DestructionDecision(false, "BACKUPS_NOT_REVIEWED");
        }
        if (!p.dependenciesResolved()) {
            return new DestructionDecision(false, "DEPENDENCIES_REMAIN");
        }
        if (!p.retentionAndLegalHoldCleared()) {
            return new DestructionDecision(false, "RETENTION_OR_LEGAL_HOLD");
        }
        if (!p.independentApproval()) {
            return new DestructionDecision(false, "APPROVAL_MISSING");
        }
        return new DestructionDecision(true, "READY_FOR_CONTROLLED_DESTRUCTION");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-28T10:00:00Z");
        StatusEvidence revoked = new StatusEvidence(
                CertificateStatus.REVOKED, true, true,
                Instant.parse("2026-11-28T09:00:00Z"),
                Instant.parse("2026-11-28T11:00:00Z"),
                Instant.parse("2026-11-28T08:30:00Z"));

        DestructionPrerequisites incomplete =
                new DestructionPrerequisites(
                        true, false, true, true, true,
                        false, false, true, false);

        System.out.println("Certificate accepted: " +
                evaluateCertificateStatus(
                        revoked, now, FailureMode.HARD_FAIL).accepted());
        System.out.println("Destruction allowed: " +
                evaluateDestruction(incomplete).allowed());
        System.out.println("Destruction reason: " +
                evaluateDestruction(incomplete).reason());
    }
}
~~~

Kết quả minh họa:

~~~text
Certificate accepted: false
Destruction allowed: false
Destruction reason: RELYING_PARTIES_NOT_REVIEWED
~~~

### 14.1. Giới hạn của ví dụ

1. **StatusEvidence** là metadata giả lập; production phải xác minh CRL/OCSP signature, issuer, CertID, freshness và chain bằng PKI library/provider.
2. Code xử lý **SOFT_FAIL** như một trạng thái cần quyết định riêng, không tự chấp nhận. Đây là lựa chọn có chủ ý để không biến unavailable thành good.
3. **certificateRevocationRequirementSatisfied** có nghĩa revocation đã được publish khi policy yêu cầu, hoặc có evidence/approval rằng không cần tạo revocation entry; nó không chứng minh mọi clients đã áp dụng.
4. **keyUseDisabled** phải được xác nhận ở HSM/KMS và workload, không chỉ trong application database.
5. Các boolean prerequisites phải lấy từ evidence/approval service có thẩm quyền, không nhận trực tiếp từ client.
6. Code không kiểm tra CA hierarchy, trust anchor removal, certificate path hoặc historical timestamp.
7. Code không thực hiện Destroy; nó chỉ đưa ra quyết định policy trước một operation được kiểm soát.

### 14.2. Khi nào dùng hard-fail?

Với certificate dùng để xác thực **high-risk service identity, administrative access hoặc CA relationships**, việc không lấy được status có thể cần từ chối. Với hệ thống khác, soft-fail có thể được cân nhắc nhưng phải có **risk acceptance, cache freshness, outage handling và monitoring**.

Không cấu hình soft-fail chỉ để tránh downtime mà không ghi rõ attacker có thể tiếp tục được tin certificate bị revoke trong trường hợp nào.

## 15. Java 17: PKIX revocation checking với CRL

Java PKI cung cấp **CertPathValidator** và **PKIXRevocationChecker** để kiểm tra certificate path và revocation status. Ví dụ dưới đây minh họa cấu hình ưu tiên CRL và không fallback sang cơ chế khác.

~~~java
import java.security.GeneralSecurityException;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.PKIXRevocationChecker;
import java.security.cert.TrustAnchor;
import java.util.EnumSet;
import java.util.Set;

public final class PkixCrlValidation {
    private PkixCrlValidation() {}

    public static PKIXCertPathValidatorResult validate(
            CertPath certificatePath,
            Set<TrustAnchor> approvedTrustAnchors
    ) throws GeneralSecurityException {
        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");

        PKIXParameters parameters =
                new PKIXParameters(approvedTrustAnchors);
        parameters.setRevocationEnabled(true);

        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();
        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK
        ));
        parameters.addCertPathChecker(checker);

        return (PKIXCertPathValidatorResult)
                validator.validate(certificatePath, parameters);
    }
}
~~~

### 15.1. Cách đọc ví dụ

- **Trust anchors** phải đến từ trust store được phê duyệt; không lấy trực tiếp từ certificate do peer gửi.
- **CertPath** cần được xây dựng từ đúng certificate chain; trust anchor thường được cung cấp riêng.
- **PREFER_CRLS** yêu cầu checker ưu tiên CRL.
- **NO_FALLBACK** ngăn fallback sang cơ chế revocation khác khi CRL không dùng được.
- Revocation checker thực tế phụ thuộc **JDK provider, CRL distribution points, cấu hình và nguồn status**.
- Khi validation thất bại, ứng dụng phải phân biệt **revoked, status unavailable, invalid chain, expired certificate và lỗi cấu hình** trong xử lý/log.

### 15.2. Những điều production phải cấu hình thêm

1. Trust store và trust anchor được bảo vệ, cập nhật theo governance.
2. CRL distribution point có thể truy cập từ môi trường chạy, hoặc CRLs được cung cấp qua nguồn offline được kiểm chứng.
3. CRL signature, issuer, scope, thisUpdate/nextUpdate được kiểm tra.
4. Cache/refresh, network timeout và stale status có policy rõ.
5. Audit không ghi private key, credentials hoặc dữ liệu handshake nhạy cảm.
6. Unit/integration tests có certificate revoked, certificate good, CRL stale, CRL sai issuer và CRL unavailable.
7. Nếu dùng OCSP, phải cấu hình và kiểm thử riêng; không suy từ một CRL example rằng OCSP đã được kiểm tra.

**Không dùng SOFT_FAIL như một cách sửa lỗi kết nối OCSP/CRL** nếu security policy yêu cầu hard-fail. Mọi ngoại lệ soft-fail cần risk acceptance và telemetry.

## 16. Certificate renewal, reissue và rekey trước destruction

Trước khi hủy private key cũ, cần xác định certificate thay thế có dùng **key material mới** hay chỉ phát hành lại certificate với cùng public key.

| Hành động | Certificate | Public/private key | Ý nghĩa |
| --- | --- | --- | --- |
| **Renew/reissue với cùng key** | Certificate mới, serial/validity có thể khác | Key pair không đổi | Không đáp ứng policy yêu cầu thay key material |
| **Rekey** | Certificate mới | Sinh key pair mới | Chuyển identity/certificate sang public key mới |
| **Replace issuer/CA** | Chain hoặc issuer thay đổi | Có thể thay leaf và/hoặc CA keys | Migration trust hierarchy |
| **Revoke old certificate** | Old serial bị đánh dấu revoked | Key có thể vẫn tồn tại | Relying parties cần cập nhật status |
| **Destroy old private key** | Certificate/public evidence vẫn có thể được lưu | Private material bị hủy | Ngăn dùng lại key trong boundary đã kiểm soát |

### 16.1. Rủi ro reissue cùng key sau compromise

Nếu private key đã bị lộ, việc xin certificate mới với **cùng public key** không khắc phục compromise. Attacker vẫn giữ private key tương ứng và có thể dùng certificate mới nếu issuer cấp lại.

Trong compromise, cần **rekey thật**: sinh key pair mới, phát certificate mới với public key mới, cập nhật clients và thu hồi certificate cũ. Kiểm tra SPKI fingerprint để xác minh key đã thay.

### 16.2. Khi nào có thể reissue cùng key?

Một số tình huống routine có thể reissue cùng key nếu:

- Private key vẫn được bảo vệ và chưa vượt cryptoperiod.
- Chỉ cần thay thông tin certificate hoặc validity theo policy.
- PKI profile/algorithm và risk assessment cho phép.
- Không có yêu cầu bắt buộc rekey theo thời gian hoặc sự cố.

Không nhầm **certificate renewal** với **key rotation** trong inventory và báo cáo.

### 16.3. Thay key cần kiểm tra downstream

Khi rekey:

- Cập nhật certificate trên load balancer, ingress, proxy, sidecar và service.
- Cập nhật trust/pinning ở clients nếu có.
- Cập nhật mTLS peer configurations hai chiều.
- Kiểm tra HSM key alias/version và workload IAM.
- Drain connection pools hoặc TLS sessions theo yêu cầu.
- Giữ public certificate cũ để Verify lịch sử khi cần.

## 17. Hủy private key theo loại certificate

### 17.1. TLS server/client authentication key

Khi leaf certificate bị revoke:

1. Ngừng trình certificate/private key cũ cho handshake mới.
2. Revoke certificate và publish status.
3. Triển khai certificate/key mới.
4. Cập nhật session/cache và kiểm tra mTLS peers.
5. Giữ certificate chain/status evidence.
6. Disable/destroy private key cũ sau dependency/backup review.

TLS traffic keys của những session đã thiết lập là **session-specific keys**, không phải private key của certificate. Xử lý session resumption/connection draining riêng.

### 17.2. Code-signing key

Code-signing certificate bị revoke có thể ảnh hưởng đến khả năng OS, package manager hoặc deployment pipeline tin artifact đã ký. Cần:

- Ngừng ký release mới bằng key/certificate cũ.
- Revoke certificate và cập nhật trust/status theo nền tảng phân phối.
- Kiểm kê artifact đã ký, timestamp và release provenance.
- Tạo signer mới trong HSM/signing service.
- Xác định cách xử lý artifact cũ: tiếp tục tin, chặn hoặc re-sign theo chính sách phát hành.
- Destroy private key sau evidence/backup review.

**Re-sign artifact cũ** không xóa việc artifact từng được ký bằng key cũ; phải giữ provenance và lịch sử release.

### 17.3. Document/electronic signing key

Với chữ ký tài liệu, certificate revocation có thể ảnh hưởng đến đánh giá chữ ký ở hiện tại và lịch sử. Cần giữ:

- Original document và signature container.
- Certificate chain, OCSP/CRL evidence.
- Trusted timestamp và validation material nếu profile yêu cầu.
- Quyết định revocation và mốc thời gian.

Không xóa private key trước khi giữ những bằng chứng cần thiết, nhưng cũng **không giữ private signer chỉ để Verify**. Public key đủ cho phép toán xác minh; trust evaluation cần evidence riêng.

### 17.4. Intermediate CA signing key

Khi intermediate key bị retire/compromise:

- Parent CA xử lý certificate của intermediate theo PKI policy.
- Đánh giá các leaf certificates do intermediate phát hành.
- Chuyển issuance sang intermediate mới.
- Đảm bảo CRL/OCSP responder và certificate status còn đáng tin.
- Giữ CA database, serial allocation, audit và signed artifacts cần thiết.
- Hủy private key cũ sau khi hoàn tất migration/retention và có approval.

### 17.5. Root CA signing key

Root key thường offline và có quy trình riêng. Khi retire:

- Tạo root hierarchy mới và phân phối trust anchor qua kênh governance.
- Lập kế hoạch cross-sign/transition nếu profile cho phép.
- Thông báo relying parties và xử lý thiết bị không thể cập nhật tự động.
- Giữ root certificate, policy, ceremony evidence và certificate chain lịch sử.
- Hủy root private key theo key ceremony và quorum.

Nếu root key compromise, **trust anchor removal/replacement** là quyết định governance rộng hơn việc thu hồi một leaf certificate. Không dùng CRL đơn lẻ làm cơ chế duy nhất.

## 18. Case study: thu hồi certificate của Payments API trước khi hủy key

Một nền tảng thanh toán Java có **Payments API** dùng certificate X.509 cho mTLS. Private key được giữ trong HSM; certificate do enterprise intermediate CA phát hành. Các đối tác có thể cache chain và OCSP response.

### 18.1. Phát hiện

Security scanner phát hiện private key đã được export vào một build artifact có quyền truy cập rộng. Chưa có bằng chứng đối tác đã tải artifact, nhưng key đã xuất hiện ngoài boundary được duyệt.

**Kết luận ban đầu:** Private key exposure được xác nhận ở artifact; việc bên ngoài đã đọc hoặc sử dụng key chưa được xác nhận. Certificate cần được đánh giá như compromised theo incident policy.

### 18.2. Containment và revocation

1. Chặn build artifact download và giữ bản evidence trong kho được kiểm soát.
2. Thu hồi credentials/grants của pipeline có liên quan.
3. Ngừng sử dụng private key/certificate cũ cho handshake mới.
4. Yêu cầu intermediate CA revoke certificate serial cũ với reason phù hợp.
5. Publish CRL/OCSP update và xác minh response/CRL signature, issuer, freshness.
6. Tạo key pair mới trong HSM, xin certificate mới và triển khai tới Payments API.
7. Thông báo partners, kiểm tra OCSP cache và client adoption.

### 18.3. Evidence và destruction

Trước khi destroy private key cũ, nhóm kiểm tra:

- Certificate serial, issuer, SPKI fingerprint và tất cả endpoints dùng key.
- CRL/OCSP đã publish và partners đã xác nhận áp dụng.
- HSM đã disable Sign/TLS operation bằng key cũ.
- Connection pools/session tickets được xử lý theo runbook.
- Artifact/backup copies đã được kiểm kê và hạn chế truy cập.
- Public certificate, chain, revocation response và timeline được lưu.
- Không còn dependency hợp lệ cần private key cũ.
- Destruction được owner/Security/KMS operator phê duyệt.

Sau đó HSM thực hiện destruction theo semantics provider; audit ghi key reference, thời điểm và kết quả. Báo cáo vẫn ghi **không thể chứng minh mọi bản sao ngoài tổ chức đã bị xóa**, nếu không có evidence.

### 18.4. Điều gì xảy ra nếu chỉ hủy key?

Nếu private key bị hủy nhưng certificate không bị revoke, một attacker giữ bản copy vẫn có thể dùng key với certificate cũ trong những clients chưa biết trạng thái thu hồi. Hủy trong HSM chỉ loại bỏ bản material ở boundary đó.

### 18.5. Điều gì xảy ra nếu chỉ revoke certificate?

Nếu certificate đã revoke nhưng private key vẫn tồn tại và HSM vẫn cho phép Sign/handshake, service cũ có thể tiếp tục tạo hoạt động mật mã bằng key đó. Relying parties được cấu hình tốt sẽ từ chối certificate, nhưng private-key usage vẫn là một rủi ro vận hành và forensic.

**Phải phối hợp PKI revocation, HSM key-use disable, replacement rollout và destruction có kiểm soát.**

## 19. Khi nào revocation không phải bước bắt buộc?

Tiêu đề bài nhấn mạnh **certificate revocation trước destruction**, nhưng policy phải dựa vào trạng thái và mục đích certificate thực tế. Không phải mọi lần hủy private key đều cần phát hành một revocation event mới.

### 19.1. Những trường hợp thường cần revoke

- Certificate vẫn còn trong validity và còn được relying parties tin, nhưng key/identity không còn an toàn.
- Private key bị compromise hoặc có dấu hiệu mất custody.
- Certificate cấp sai, chủ thể không còn quyền hoặc key usage không còn được phép.
- CA/intermediate key có sự cố và trust hierarchy cần cập nhật.
- Policy/contract yêu cầu revoke khi decommission trước expiry.

### 19.2. Những trường hợp có thể chỉ cần archive/retire

- Certificate đã hết hạn và không còn được dùng; policy không yêu cầu ghi thêm revocation entry.
- Certificate test chưa từng được đưa vào trust domain bên ngoài.
- Key được thay trong một môi trường nội bộ có trust registry riêng, không dùng CRL/OCSP.
- Certificate chưa từng được phát hành hoặc chưa có relying party nào tin.

Ngay cả khi không tạo revocation entry, vẫn phải **ghi nhận trạng thái lifecycle, dừng sử dụng, giữ evidence cần thiết và xử lý private key**. Với compromise, không dùng expiry trong tương lai làm lý do trì hoãn trust update.

### 19.3. CertificateHold và thu hồi vĩnh viễn

Một số PKI profiles hỗ trợ trạng thái hold tạm thời; trong các điều kiện phù hợp, hold có thể được gỡ bằng quy trình cập nhật CRL. Đây không phải cách mặc định để xử lý private key đã xác nhận compromise. **keyCompromise/cACompromise** thường đòi hỏi quyết định thu hồi nghiêm túc và thay key/certificate; việc phục hồi trust cần đánh giá độc lập.

## 20. Kiểm toán và bằng chứng cho revocation/destruction

Một lần revoke và một lần destroy cần có **bằng chứng khác nhau**. CRL/OCSP chứng minh status được issuer công bố; HSM/KMS audit chứng minh operation key lifecycle đã được thực hiện theo backend.

### 20.1. Revocation evidence

Nên lưu:

- Certificate DER/PEM hoặc reference bất biến, serial number, issuer và fingerprint.
- Revocation request, người phê duyệt, reason code và thời điểm.
- CRL đã ký hoặc OCSP response đã ký, kèm thisUpdate/nextUpdate.
- Certificate của CRL issuer/OCSP responder và chain cần để xác minh response.
- Bằng chứng distribution point/responder đã publish.
- Relying-party acknowledgements, cache age và negative-test results.
- Mốc containment, replacement và effective enforcement.

### 20.2. Key destruction evidence

Nên lưu:

- Key ID/material version, provider, HSM partition/security domain.
- Key state trước/sau, operation và request/reference ID.
- Người yêu cầu, approver, operator và witness theo policy.
- Dependency/backup/replica/retention review.
- Thời điểm schedule deletion, pending period và destruction completion.
- Bằng chứng key không còn được dùng hoặc restore trong phạm vi đã kiểm.
- Residual copies/unknowns và quyết định chấp nhận rủi ro.

**Không lưu private key bytes hoặc HSM PIN trong audit record.** Certificate/public key thường có thể được lưu, nhưng vẫn cần phân loại metadata, tenant identity và thông tin hệ thống.

### 20.3. Không nhầm publish với enforcement

Một CRL file có thể được publish nhưng:

- Distribution point không truy cập được từ một số clients.
- Client không refresh hoặc dùng cache quá lâu.
- Client soft-fail khi status unavailable.
- TLS session cũ chưa bị đóng.
- Trust anchor hoặc pinning riêng vẫn cho phép kết nối.

Vì vậy audit phải ghi **publication evidence** và **consumer enforcement evidence** riêng.

### 20.4. Không nhầm API delete với destruction toàn cục

Một KMS DeleteKey success có thể chứng minh backend đã thực hiện thao tác theo semantics provider. Nó không tự chứng minh:

- Không còn HSM backup blob hoặc replica.
- Không còn exported private-key files.
- Không còn bản key trong process dumps hoặc old images.
- Attacker không giữ raw key.
- Certificate đã bị revoke ở tất cả relying parties.

Hãy mô tả **phạm vi destruction đã xác minh**, không tuyên bố quá mức.

## 21. Ma trận kiểm thử revocation trước destruction

### 21.1. Certificate status và PKI

| Test case | Kết quả mong đợi |
| --- | --- |
| Certificate status good, response signed đúng issuer và còn fresh | Có thể tiếp tục validation nếu các kiểm tra khác đạt |
| Certificate status revoked | Relying party từ chối theo policy |
| OCSP status unknown | Không diễn giải thành good |
| CRL hết hạn/nextUpdate đã qua | Không chấp nhận như status fresh |
| CRL signature sai | Từ chối CRL |
| CRL issuer không đúng scope | Từ chối hoặc không dùng response đó |
| OCSP CertID không khớp issuer/serial | Từ chối response |
| OCSP response signed bởi responder không được ủy quyền | Từ chối response |
| OCSP response stale | Áp dụng failure policy, không coi là good |
| CRL/OCSP endpoint unavailable | Hard/soft-fail theo policy đã phê duyệt |
| Certificate serial nằm trong CRL | Revoked được nhận diện |
| CertificateHold được gỡ | Chỉ chấp nhận nếu profile và issuer policy cho phép |
| Leaf certificate revoked | Chain validation từ chối leaf theo policy |
| Intermediate CA certificate revoked | Chain phụ thuộc intermediate bị đánh giá lại |
| Root trust anchor bị compromise | Trust store update/removal, không chỉ CRL lookup |

### 21.2. Key use và destruction

| Test case | Kết quả mong đợi |
| --- | --- |
| Certificate revoked nhưng HSM Sign vẫn bật | Security control phát hiện; chặn key use theo incident policy |
| IAM principal bị revoke nhưng raw key copy tồn tại | Không tuyên bố raw copy đã mất; đánh giá replacement/residual risk |
| Private key bị destroy nhưng CRL chưa cập nhật | Test cho thấy relying party có thể vẫn tin; quy trình phải xử lý trust |
| CRL đã publish nhưng client cache cũ | Client adoption/negative test phát hiện propagation gap |
| Key đã disable nhưng backup còn restore được | Không báo destruction complete |
| Key ở PendingDeletion | Chưa báo destroyed |
| HSM backup của key đã revoked được restore | Restore workflow từ chối hoặc giữ key inactive theo policy |
| Certificate renewal dùng cùng SPKI sau compromise | Kiểm tra phát hiện chưa rekey thật |
| Key-v2 được deploy nhưng một proxy vẫn trình cert-v1 | Telemetry/canary phát hiện old serial |
| TLS connection đã mở trước revoke | Session/connection policy xử lý theo incident plan |
| Public certificate cũ cần Verify lịch sử | Verify dùng public evidence mà không cần private key |
| Legal hold còn hiệu lực | Destruction gate từ chối |
| Backup/replica chưa kiểm kê | Destruction gate từ chối |
| Relying parties chưa được xem xét | Destruction gate từ chối hoặc exception có phê duyệt |
| CA key compromise và CRL ký bằng key đó | Không tự tin response; dùng parent/trust recovery plan |

### 21.3. Kiểm thử end-to-end

Một đợt diễn tập nên đi từ **revoke request → CRL/OCSP publication → relying-party rejection → key-use disable → replacement deployment → public evidence preservation → backup/retention review → destruction**. Mỗi bước phải có correlation ID và người chịu trách nhiệm.

Không chỉ test API trả thành công. Cần chứng minh **client thực tế từ chối certificate cũ** và **key cũ không còn thực hiện operation mới**.

## 22. Anti-patterns khi revocation và destruction

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| **Destroy private key rồi mới nghĩ tới revocation** | Attacker giữ bản sao vẫn có thể được tin | Contain, revoke/trust update, rồi destroy theo gate |
| **Revoke certificate rồi cho HSM tiếp tục Sign** | Service vẫn tạo chữ ký mới bằng key mất trust | Revoke IAM/key-use và disable operation |
| **Chỉ xóa certificate khỏi server** | Clients có cache/trust riêng vẫn tin cert cũ | CRL/OCSP/trust update và consumer verification |
| **Đổi certificate nhưng giữ cùng private key đã lộ** | Attacker vẫn có key tương ứng | Sinh key pair mới và xác minh SPKI khác |
| **Chỉ chờ certificate hết hạn** | Attacker có thể sử dụng trong thời gian còn hiệu lực | Revoke ngay khi risk/policy yêu cầu |
| **Coi OCSP good là certificate hoàn toàn hợp lệ** | Bỏ qua chain, name, usage, algorithm và validity | Thực hiện đầy đủ PKIX validation |
| **Coi OCSP unknown là good** | Bỏ qua trạng thái không xác định | Áp dụng hard/soft-fail policy rõ |
| **Dùng OCSP response cũ vô thời hạn** | Không nhận biết revocation mới | Kiểm tra freshness và cache TTL |
| **Publish CRL rồi tuyên bố mọi client đã áp dụng** | Bỏ sót offline clients/cache/soft-fail | Đo consumer enforcement |
| **Tin client nào cũng kiểm tra revocation** | Một số stack bỏ qua hoặc soft-fail | Inventory/test từng relying party |
| **Không xử lý TLS sessions cũ** | Kết nối đã xác thực có thể tiếp tục | Drain/close/resumption policy khi cần |
| **Revoke root CA bằng CRL đơn lẻ** | Trust anchor có thể vẫn tồn tại trong stores | Governance và trust-store removal/rollover |
| **Dùng CA key đã compromise ký CRL mới** | Status response có thể không còn đáng tin | Parent CA/delegated trusted responder plan |
| **Destroy ngay sau API schedule deletion** | Key có thể vẫn pending/cancelable | Xác nhận provider destruction state |
| **Xóa public certificate cùng private key** | Mất evidence Verify lịch sử/forensics | Giữ public material và validation evidence |
| **Giữ private key chỉ để Verify chữ ký cũ** | Duy trì khả năng ký mới không cần thiết | Giữ public key/certificate/evidence |
| **Không kiểm tra mọi certificate dùng chung key** | Bỏ sót serial/issuer khác | Map SPKI fingerprint tới toàn bộ certificates |
| **Không kiểm kê HSM backup/replicas** | Key có thể được restore sau destruction | Dependency graph và backup review |
| **Không phân biệt revoked và expired** | Báo cáo sai trạng thái, xử lý sai historical validation | Theo dõi status và validity riêng |
| **Coi soft-fail là mặc định an toàn** | Status outage có thể cho cert bị revoke tiếp tục được tin | Risk acceptance, telemetry và hard-fail khi cần |
| **Chỉ test bằng một Java client** | Bỏ sót proxy, mobile, partner và legacy clients | Consumer matrix và end-to-end tests |
| **Không ghi revocation publication/enforcement time** | Không biết khoảng trễ thực tế | Ghi từng mốc UTC riêng |
| **Báo “đã xóa khỏi mọi nơi” sau một Delete API** | Tuyên bố vượt evidence | Ghi phạm vi backend/copies đã kiểm và residual risk |

## 23. Checklist vận hành certificate revocation trước destruction

1. **Certificate identity:** Có serial, issuer, subject/SAN, fingerprint, validity và key usage?
2. **Key mapping:** Có key ID/version và SPKI fingerprint tương ứng?
3. **Shared key use:** Có certificate khác dùng cùng public key không?
4. **Reason:** Revocation reason phù hợp là keyCompromise, cACompromise, superseded, cessationOfOperation hay reason khác?
5. **Time:** Có revocation date, invalidity date, detection time và publication time riêng?
6. **Authority:** Đúng CA/issuer có thẩm quyền đã tiếp nhận yêu cầu?
7. **CRL:** Đúng issuer, scope, signature, thisUpdate/nextUpdate và serial?
8. **OCSP:** Đúng CertID, responder authorization, signature và freshness?
9. **Stapling:** Server có response mới; clients có kiểm tra và áp dụng?
10. **Must-Staple:** Certificate/client support có đúng profile và được test?
11. **Failure policy:** Soft-fail/hard-fail được phê duyệt cho từng client/risk domain?
12. **CA hierarchy:** Leaf, intermediate hay root? Có cần parent revoke hoặc trust-anchor removal?
13. **Trust distribution:** CRL/OCSP/truststore/JWKS/pinning đã được cập nhật?
14. **Consumer adoption:** Có acknowledgements và negative tests cho partners/offline clients?
15. **Session handling:** TLS connections, tickets, tokens và application sessions có cần drain/revoke?
16. **Replacement:** Key pair/certificate mới đã được tạo và triển khai?
17. **Rekey verification:** Nếu compromise, SPKI fingerprint mới khác key cũ?
18. **Key use:** HSM/KMS Sign/Agree/Decrypt operations đã bị chặn đúng scope?
19. **Public evidence:** Certificate, public key, chain, CRL/OCSP, timestamps và audit được lưu?
20. **Dependencies:** Không còn dữ liệu/protocol/operations hợp lệ cần private key cũ?
21. **Backups:** HSM backup, replicas, snapshots, keystores, exports và secret versions đã được kiểm kê?
22. **Recovery:** Key bị revoke không thể được restore và kích hoạt lại từ backup cũ?
23. **Retention:** Legal hold, contract, audit và historical validation obligations đã được xử lý?
24. **Approval:** Owner, Security/PKI, Data owner và operator phê duyệt độc lập?
25. **Destruction:** Backend đã xác nhận destroyed, không chỉ scheduled/pending?
26. **Copies:** Báo cáo rõ những bản sao đã xác minh và những bản copy ngoài kiểm soát còn unknown?
27. **Audit:** Có change/incident ID, operation result, approvers, UTC timestamps và provider references?
28. **Post-check:** Old cert bị từ chối, new cert được chấp nhận, old key không tạo operation mới?
29. **Historical verification:** Chữ ký cũ còn kiểm tra được bằng public evidence và trust policy phù hợp?
30. **Closure:** Residual risk, consumer lag và follow-up owners được ghi rõ?

## 24. Ghi nhớ

- **Certificate revocation và private-key destruction là hai hành động khác nhau.** Revocation thay đổi trust decision; destruction loại bỏ key material trong phạm vi kiểm soát.
- **Hủy private key không tự thu hồi certificate.** Attacker giữ bản copy vẫn có thể dùng key nếu relying parties tiếp tục tin certificate.
- **Revoke certificate không tự chặn HSM Sign/Decrypt.** Phải thu hồi IAM/key-use và disable operation tương ứng.
- **CRL và OCSP là status mechanisms**, có scope, freshness, issuer/responder signature và cache behavior cần kiểm tra.
- **OCSP good không thay thế toàn bộ PKIX validation.** Unknown/unavailable không tự có nghĩa good; soft-fail/hard-fail phải theo risk policy.
- **OCSP stapling phân phối status response**, không thay certificate/key và không đảm bảo mọi client kiểm tra.
- **Revocation publication không đồng nghĩa enforcement toàn cục.** Cache, offline clients, TLS sessions và soft-fail có thể kéo dài khoảng trust.
- **Leaf, intermediate và root CA có cách xử lý khác nhau.** Root trust anchor thường cần trust-store governance, không chỉ CRL.
- **Renew/reissue cùng key không phải rekey.** Nếu private key compromise, phải sinh key pair mới và cập nhật public trust.
- **Chữ ký lịch sử không cần private key để Verify.** Giữ public certificate, chain, CRL/OCSP, timestamp và signed evidence theo retention.
- **Không destroy key trước dependency, backup/DR, evidence và legal review.** Với compromise đang diễn ra, containment/revocation phải được thực hiện ngay, còn destruction theo gate.
- **Pending deletion không phải destroyed.** Xác minh semantics provider, replicas, backups và residual copies.
- **Kết quả cuối cần evidence:** certificate cũ bị relying parties từ chối, key cũ không còn tạo operation mới, replacement hoạt động và public evidence lịch sử được bảo toàn.

Trước khi hủy private key gắn với certificate, hãy hỏi: **“Ai còn tin certificate này và họ nhận revocation status bằng cách nào?”, “Key cũ đã bị chặn sử dụng và các phụ thuộc/backup đã được xử lý chưa?”, “Bằng chứng nào cho thấy chữ ký lịch sử vẫn có thể được đánh giá mà không cần giữ private key?”** Khi có câu trả lời được xác minh bằng **PKI status, HSM/KMS audit, consumer tests, dependency inventory và destruction evidence**, việc hủy mới hoàn tất mà không để lại một certificate vẫn được tin hoặc làm mất dữ liệu/bằng chứng cần thiết.

