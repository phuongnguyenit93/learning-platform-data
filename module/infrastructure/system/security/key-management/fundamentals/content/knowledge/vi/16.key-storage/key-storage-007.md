# HSM — Hardware Security Module trong lưu trữ và quản lý khóa mật mã

## 1. HSM là gì?

**HSM (Hardware Security Module)** là **thiết bị hoặc mô-đun phần cứng chuyên dụng để bảo vệ khóa mật mã và thực hiện các thao tác mật mã trong một ranh giới bảo mật được xác định** (*cryptographic boundary*). Tùy thiết kế và chứng nhận của sản phẩm, HSM có thể cung cấp khả năng tạo khóa, bảo vệ vật liệu khóa, hạn chế xuất khóa, quản lý phiên và vai trò, kiểm soát truy cập, ký số, mã hóa, giải mã, bọc khóa, dẫn xuất khóa hoặc những chức năng mật mã khác.

Thay vì lưu private key trong file cấu hình rồi tải lên bộ nhớ ứng dụng để ký, một hệ thống có thể giữ private key trong HSM và yêu cầu thiết bị **thực hiện phép ký**. Ứng dụng nhận được **chữ ký**, trong khi **private key được thiết kế để không rời khỏi ranh giới HSM ở dạng rõ** khi chính sách và sản phẩm hỗ trợ loại key không xuất được.

Ví dụ, dịch vụ phát hành hóa đơn có private signing key trong HSM. Dịch vụ `invoice-signer` nhận tài liệu đã được phê duyệt, gửi yêu cầu ký tới HSM qua một API và nhận chữ ký ECDSA/RSA-PSS tương ứng. HSM không cần trao raw private key cho tiến trình Java.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, HSM là một thành phần quan trọng của kiến trúc **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy khóa**, liên quan mật thiết đến mật mã đối xứng, bất đối xứng, chữ ký số, KMS, envelope encryption, phân quyền và kiểm toán.

> **Nguyên tắc:** **HSM bảo vệ vật liệu và việc thực thi thao tác mật mã trong phạm vi của nó; nó không tự hiểu mọi quy tắc nghiệp vụ hoặc bảo vệ những bản sao khóa đã đi ra ngoài ranh giới.** Khóa *non-exportable* vẫn có thể bị **lạm dụng qua API có quyền**, và một HSM an toàn không tự biến ứng dụng xung quanh thành an toàn.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích ranh giới bảo mật và các thuộc tính của HSM, không nhầm HSM với keystore hay KMS.
2. Phân biệt **khóa được sinh/lưu trong HSM**, **key handle**, **public key**, **wrapped key** và raw key material.
3. Hiểu các vai trò, key attributes, PKCS#11/JCA, quy tắc export/import và key usage.
4. Thiết kế **DEK/KEK** theo envelope encryption cùng KMS/HSM.
5. Tổ chức vòng đời khóa, key ceremony, dual control, backup/DR, rotation và tiêu hủy an toàn.
6. Phân tích các giới hạn an ninh: **signing oracle, decrypt oracle, IAM, cache plaintext, chứng thư, dữ liệu lịch sử**.
7. Nhận biết cách Java 11+ truy cập HSM qua **PKCS#11 provider** và điều kiện để triển khai thực tế.

## 2. HSM đứng ở đâu trong kiến trúc?

HSM là một **thành phần của hệ thống quản lý khóa**, không phải một hệ thống nghiệp vụ hoàn chỉnh.

~~~mermaid
flowchart TD
    Client[Khách hàng / hệ thống gọi API] --> App[Ứng dụng Java]
    App --> Business[Business authorization: purpose, data scope]
    Business --> Policy[Control plane: key state, IAM, approval]
    Policy --> Api[KMS API / PKCS#11 / HSM client]
    Api --> HSM[HSM: cryptographic boundary]
    HSM --> Operation[Sign / Unwrap / GenerateKey / MAC]
    Operation --> Api
    Api --> App
    Policy --> Audit[Audit và giám sát]
    Api --> Audit
    App --> Data[(Ciphertext, metadata, public cert)]
~~~

Một yêu cầu hợp lệ cần đi qua **nhiều lớp**:

- **Ứng dụng:** xác minh danh tính người yêu cầu và điều kiện nghiệp vụ.
- **IAM/control plane:** xác minh principal được phép dùng **đúng key và operation**.
- **HSM/KMS:** thực thi những hạn chế mà thiết bị và API hỗ trợ.
- **Dữ liệu/metadata:** gắn key ID, phiên bản, thuật toán, mục đích và thông tin cần cho verify/decrypt.
- **Audit:** ghi nhận ai làm gì, trên khóa nào và kết quả ra sao.

### HSM không nhất thiết chứa dữ liệu người dùng

Trong một thiết kế phổ biến, HSM **giữ KEK hoặc private key**, còn cơ sở dữ liệu giữ **ciphertext và wrapped DEK**. Không cần đưa toàn bộ database qua HSM để mã hóa từng record. Có thể xử lý dữ liệu bằng **DEK tạm trong ứng dụng** hoặc bằng cơ chế provider đã phê duyệt, tùy threat model và kiến trúc.

Việc giữ phần lớn dữ liệu ngoài HSM giúp tránh giới hạn dung lượng và thông lượng của thiết bị, nhưng đặt thêm trách nhiệm lên **bảo vệ DEK, nonce, cache và chính sách truy cập dữ liệu**.

## 3. Ranh giới bảo mật (*cryptographic boundary*) là gì?

**Cryptographic boundary** xác định thành phần nào nằm trong phạm vi được bảo vệ/đánh giá của một mô-đun mật mã: phần cứng, firmware, phần mềm và giao diện tương ứng theo tài liệu sản phẩm và hồ sơ xác nhận. Không thể suy ra ranh giới chỉ từ tên marketing “Hardware Security Module”.

Bên trong một HSM, tùy sản phẩm, có thể có:

- Bộ xử lý/firmware chuyên dụng cho mật mã.
- Nguồn entropy và DRBG được thiết kế cho việc tạo khóa.
- Bộ nhớ/khối lưu vật liệu khóa có kiểm soát.
- Cơ chế xác thực operator, role và phiên.
- Bộ phận phát hiện hoặc chống tác động vật lý theo mức bảo đảm.
- Giao diện mạng/PCIe/USB hoặc giao thức điều khiển từ host.

Bên ngoài ranh giới có thể là **Java process, PKCS#11 library, application server, network, API gateway, người quản trị và hệ thống ghi log**. Những thành phần đó **không tự được bảo vệ bởi tính năng phần cứng của HSM**.

### 3.1. Tamper evidence, resistance và response

| Thuộc tính | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Tamper evidence** | Có thể phát hiện dấu hiệu can thiệp vật lý | Không mặc nhiên ngăn can thiệp thành công |
| **Tamper resistance** | Tăng độ khó khi cố truy cập vật liệu khóa bằng biện pháp vật lý | Không cam kết “không thể tấn công” |
| **Tamper detection** | Phát hiện một số điều kiện mở vỏ, cảm biến, môi trường bất thường | Phạm vi cảm biến tùy thiết kế |
| **Tamper response** | Có thể khóa thiết bị, xóa vùng nhạy cảm hoặc thực hiện hành động theo chính sách | Không đảm bảo cùng hành vi ở mọi HSM; có thể ảnh hưởng availability |
| **Secure key storage** | Giới hạn truy cập và vòng đời vật liệu khóa | Không ngăn lỗi IAM hoặc sử dụng sai API |

Một số HSM có thể **zeroize** vật liệu nhạy cảm khi phát hiện tamper. Nhưng **không nên khẳng định mọi HSM đều xóa mọi khóa trong mọi trường hợp bị đụng chạm**. Cần đọc tài liệu về phần cứng, cấu hình, loại vùng nhớ, backup và hành vi phục hồi.

### 3.2. Không coi HSM là lá chắn cho mọi tấn công

HSM không tự giải quyết:

- Application bị chiếm có quyền gọi `Sign` hoặc `Decrypt`.
- Dữ liệu sai nghiệp vụ được đưa tới thiết bị nhưng vẫn đúng định dạng.
- Bản sao plaintext DEK đã đi ra ngoài qua API.
- Lỗi nonce/AAD/tag khi ứng dụng dùng AES-GCM.
- Peer authentication bị thiếu trong ECDH.
- Token JWT/chữ ký đã phát vẫn được một bên nhận tin cậy.
- Lỗi phân quyền, thiếu tenant isolation hoặc hệ thống quản trị HSM bị chiếm.
- Rủi ro vật lý/side-channel nằm ngoài mục tiêu hoặc mức bảo đảm của sản phẩm.

**Bảo đảm của HSM có phạm vi và giả định cụ thể**, không phải tuyên bố an toàn tuyệt đối.

## 4. HSM, KMS, TPM, TEE và keystore khác nhau thế nào?

| Công nghệ | Bản chất | Mục tiêu thường gặp | Điểm cần nhớ |
| --- | --- | --- | --- |
| **HSM** | Mô-đun phần cứng chuyên dụng | Bảo vệ khóa và thực thi phép toán trong boundary đã xác định | Cần kiểm tra product capabilities, certification, IAM và vận hành |
| **Managed KMS** | Dịch vụ quản lý khóa qua API, thường có HSM ở tầng backend tùy sản phẩm | Tạo key resource, IAM, rotation, audit, encryption APIs | API quản trị rộng hơn; khách hàng không nhất thiết vận hành HSM trực tiếp |
| **Cloud HSM / dedicated HSM** | HSM được cung cấp như tài nguyên cloud với mô hình quản trị riêng | Nhu cầu điều khiển trực tiếp partition/PKCS#11/role | Trách nhiệm customer/provider khác managed KMS |
| **TPM** | Mô-đun bảo mật gắn với nền tảng thiết bị | Measured boot, sealed key, attestation, device identity | Không mặc định thay thế HSM server hiệu năng cao |
| **TEE / enclave** | Môi trường thực thi cách ly theo kiến trúc phần cứng/phần mềm | Xử lý code/dữ liệu trong vùng được cô lập | Phạm vi bảo đảm khác HSM; không mặc định có key-management API tương đương |
| **Java KeyStore/PKCS#12** | Định dạng hoặc giao diện lưu/truy xuất key/cert | Quản lý private key, truststore, ứng dụng | Nếu file chứa key được giải mã vào JVM, không có boundary phần cứng tương đương |
| **Secret manager** | Dịch vụ lưu/điều phối bí mật | Credential, API token, password, secret lifecycle | Không tự tương đương phần cứng sinh và dùng khóa non-exportable |

### 4.1. “KMS sử dụng HSM” có phải “có toàn quyền truy cập HSM”?

Không nhất thiết. Một managed KMS có thể dùng HSM nội bộ nhưng chỉ cung cấp các operation và policy đã định sẵn. Khách hàng có thể **không** có PKCS#11, không tự quản lý partition, không chọn mọi thuật toán hay đọc đầy đủ HSM audit của phần cứng.

Ngược lại, dịch vụ **cloud HSM chuyên dụng** có thể cấp quyền quản lý trực tiếp hơn, kèm trách nhiệm về **clustering, token role, availability, backup và policy**.

### 4.2. File keystore được mã hóa có đủ không?

Một file PKCS#12 được bảo vệ bằng password hữu ích cho nhiều ứng dụng, nhưng khi ứng dụng mở khóa và private key có mặt trong **bộ nhớ của JVM/host**, mô hình đe dọa khác với private key không xuất được trong HSM. Không nên gọi file keystore là HSM.

Tuy vậy, **HSM không phải bắt buộc cho mọi khóa**: chọn theo mức độ nhạy cảm, tài sản, yêu cầu tuân thủ, mô hình vận hành và chi phí.

## 5. Phân loại HSM theo cách triển khai

### 5.1. Network-attached HSM

Ứng dụng giao tiếp với HSM qua mạng, thường thông qua client library hoặc dịch vụ trung gian.

**Ưu điểm:** tập trung quản trị, chia sẻ phục vụ nhiều máy, dễ xây cụm và mô hình key custody chung.

**Thách thức:** độ trễ mạng, kết nối, session, throughput, HA, TLS/mTLS, quản lý quyền và khả năng cô lập mạng.

### 5.2. PCIe/thiết bị gắn trực tiếp

HSM được lắp trong host hoặc kết nối gần host.

**Ưu điểm:** có thể giảm một phần phụ thuộc mạng, phù hợp hệ thống có yêu cầu riêng.

**Thách thức:** vòng đời máy chủ, thay thiết bị, driver, quyền host và quy trình DR/backup.

### 5.3. Cloud HSM và managed KMS

Cloud HSM đem lại hạ tầng thiết bị trong trung tâm dữ liệu nhà cung cấp, nhưng kiến trúc **shared tenancy/dedicated partition**, quyền và SLA khác nhau theo dịch vụ. Managed KMS có thể đơn giản hóa lifecycle/HA nhưng giới hạn mức điều khiển trực tiếp.

### 5.4. HSM chuyên biệt cho thanh toán

**Payment HSM** có thể hỗ trợ các giao thức/khối nghiệp vụ chuyên biệt như PIN, card key management hoặc payment cryptography. Không tự suy ra một network HSM PKCS#11 đa dụng có đầy đủ chức năng thanh toán, và ngược lại.

**Chọn HSM theo giao thức và compliance thực tế**, không chỉ dựa vào nhãn “HSM”.

## 6. Tiêu chuẩn và mức bảo đảm: FIPS 140-3 là gì?

Một số tổ chức yêu cầu mô-đun mật mã được đánh giá theo **FIPS 140-3**, một tiêu chuẩn về yêu cầu bảo mật cho cryptographic modules. Trong phạm vi áp dụng, hồ sơ đánh giá và chương trình validation giúp người sử dụng hiểu **đúng mô-đun, phiên bản, cấu hình và mức bảo đảm đã được xác nhận**.

### Không nhầm bốn khẳng định

1. **“Dùng AES-256”**: thuật toán mạnh nhưng **không tự chứng minh** HSM được validation.
2. **“Vendor nói FIPS-compliant”**: tuyên bố marketing có thể khác **hồ sơ validation chính thức**.
3. **“Có một certificate cho dòng sản phẩm”**: chưa chắc đúng **model, firmware, mode of operation và môi trường** đang triển khai.
4. **“Đã dùng HSM validated”**: vẫn **không chứng minh toàn bộ ứng dụng** đáp ứng các yêu cầu tuân thủ khác.

### Những gì nên đối chiếu

- Tên mô-đun, nhà cung cấp, phần cứng/firmware/phần mềm và phạm vi cryptographic boundary.
- Validation certificate, security policy và mức bảo đảm của module áp dụng.
- **Approved mode** và thuật toán/cấu hình được phép trong môi trường vận hành.
- Key management roles, dịch vụ, self-tests, entropy và điều kiện khởi tạo theo hồ sơ.
- Tình trạng cert, các thay đổi firmware/version và hướng dẫn khi xảy ra tamper hoặc lỗi.

**Không gán mặc định một “FIPS level” cho mọi HSM của một nhà cung cấp.** Phải kiểm tra đúng phiên bản và hồ sơ. Chứng nhận là đầu vào đánh giá rủi ro, không thay thế kiểm thử hệ thống và threat modeling.

## 7. HSM bảo quản khóa bằng cách nào?

Trong kiến trúc lý tưởng, **vật liệu khóa bí mật** được tạo hoặc nhập theo quy trình được kiểm soát và sau đó chỉ được dùng trong boundary theo những operation được cho phép.

### Ba dạng thông tin cần phân biệt

| Dạng | Ví dụ | Có thể đưa ra ngoài? |
| --- | --- | --- |
| **Raw key material** | Byte private RSA/EC key, AES KEK, HMAC secret | Chỉ khi chính sách và thiết bị cho phép; với non-exportable key là không |
| **Key handle / object reference** | PKCS#11 object handle, provider key reference | Thường chỉ là tham chiếu, không chứa secret; phạm vi hiệu lực tùy API/session |
| **Public key / certificate** | RSA/EC public key, X.509 certificate | Thường có thể phân phối nhưng **nguồn tin cậy** phải được xác minh |
| **Wrapped key** | DEK được bọc dưới KEK | Có thể lưu/truyền nếu scheme và key policy phù hợp |
| **Ciphertext / MAC / signature** | Kết quả operation | Có thể trả về theo chức năng nhưng không chứng minh request đã được phê duyệt nghiệp vụ |

### 7.1. Sinh khóa trong boundary

Một trong những mô hình bảo vệ mạnh là **generate-in-HSM**: thiết bị sinh vật liệu và trả về key handle/public information. Private key không cần xuất sang ứng dụng.

Điều này giảm rủi ro khi **máy chủ phát sinh khóa bị xâm nhập**, nhưng phải tin cậy RNG/DRBG, thiết bị, firmware, quyền sử dụng và quy trình nhập/xuất/backup.

### 7.2. Import khóa vào HSM

Đôi khi phải nhập một khóa đã tồn tại. Lúc này cần xác định:

- Khóa ban đầu được sinh ở đâu và bằng nguồn entropy nào?
- Raw key có từng xuất hiện ở host/log/backup không?
- Đường import được **mã hóa, xác thực và phê duyệt** bằng cơ chế nào?
- Sau import, có còn các bản sao bên ngoài HSM không?
- Quy tắc key usage/export và trách nhiệm hủy bản sao cũ đã rõ chưa?

**Nhập một khóa yếu hoặc đã bị lộ vào HSM không làm nó trở thành khóa bí mật mạnh trở lại.**

### 7.3. Export và wrapping

Một số HSM cho phép **xuất key dưới dạng được bọc** hoặc sao lưu bảo vệ, tùy loại key và policy. **Non-exportable** không mặc định đồng nghĩa **không thể backup/replicate**: nhiều sản phẩm có các cơ chế backup/HA chuyên dụng với chính sách riêng.

Ngược lại, `C_Export` hoặc thao tác tương tự không nên được giả định tồn tại ở mọi API. Trong **PKCS#11**, khả năng trích xuất/wrap phụ thuộc object attributes, mechanism và token; phải theo API và vendor.

## 8. PKCS#11: mô hình ứng dụng truy cập HSM

**PKCS#11** là một giao diện lập trình thường dùng cho token mật mã, HSM và các triển khai tương thích. Nó cho phép làm việc với **slots, tokens, sessions, objects, mechanisms và operations**.

### Các thành phần

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Slot** | Vị trí/giao diện mà token có thể xuất hiện | Slot 0 hoặc slot mapping của vendor |
| **Token** | Đối tượng thiết bị/partition với các khả năng và objects | Partition khóa ký |
| **Session** | Ngữ cảnh trao đổi và thực hiện operation với token | Phiên đăng nhập của ứng dụng |
| **Object** | Key/certificate/data object có attributes | Private key non-exportable |
| **Handle** | Định danh tạm/phạm vi API cho object/session | Tham chiếu nội bộ, không phải raw secret |
| **Mechanism** | Loại thao tác/thuật toán token hỗ trợ | RSA-PSS, ECDSA, AES-KW tùy thiết bị |
| **Role/Login** | Người dùng/nhà quản trị và trạng thái xác thực | User, Security Officer theo mô hình token |

### 8.1. Các key attributes điển hình

Một số thuộc tính PKCS#11 quan trọng:

| Thuộc tính | Mục đích |
| --- | --- |
| `CKA_CLASS` | Object class: secret/private/public key, certificate... |
| `CKA_KEY_TYPE` | Loại key, ví dụ AES hoặc RSA/EC theo cơ chế |
| `CKA_TOKEN` | Quy định object là token object hay session object |
| `CKA_PRIVATE` | Giới hạn khả năng truy cập object theo trạng thái đăng nhập |
| `CKA_SENSITIVE` | Hạn chế việc bộc lộ một số giá trị nhạy cảm qua API |
| `CKA_EXTRACTABLE` | Có cho phép xuất hoặc wrap key theo rules hay không |
| `CKA_NEVER_EXTRACTABLE` | Thông tin về việc object chưa từng ở trạng thái extractable trong phạm vi được định nghĩa |
| `CKA_ALWAYS_SENSITIVE` | Thông tin về việc object luôn sensitive trong phạm vi được định nghĩa |
| `CKA_SIGN`, `CKA_VERIFY` | Các thao tác chữ ký được cho phép |
| `CKA_ENCRYPT`, `CKA_DECRYPT` | Các thao tác mã hóa/giải mã được cho phép |
| `CKA_WRAP`, `CKA_UNWRAP` | Các thao tác bọc/giải bọc key được cho phép |
| `CKA_DERIVE` | Cho phép dẫn xuất key theo mechanism hỗ trợ |
| `CKA_ID`, `CKA_LABEL` | Thông tin định danh/tìm kiếm object |

**Quan trọng:** `CKA_PRIVATE` **không đồng nghĩa** “private key object” (đó liên quan `CKA_CLASS`) và cũng **không đủ** để chứng minh vật liệu không thể xuất. Phải kết hợp attributes, quyền, mechanism và bảo đảm token.

### 8.2. Không lấy `CKA_LABEL` làm định danh an toàn duy nhất

Label có thể không duy nhất hoặc có thể bị đổi. **Object handle** có thể chỉ có ý nghĩa trong session. Inventory cần gắn với **provider resource ID, key ID/CKA_ID, version, public key fingerprint hoặc định danh được quản lý**, cùng quy trình tránh collision/ambiguity.

### 8.3. API có khả năng khác nhau

Một HSM có thể hỗ trợ `CKM_RSA_PKCS_PSS` nhưng không hỗ trợ cùng tổ hợp hash, key size hoặc mechanism như Java application mong đợi. Một token có AES key nhưng không có AES-GCM operation phù hợp qua PKCS#11.

**Không suy ra hỗ trợ thuật toán chỉ từ tên PKCS#11 hoặc JCA provider.** Xác minh mechanism list, key type, limits và tài liệu vendor trước khi triển khai.

## 9. HSM và Java JCA/JCE: hai lớp giao diện

Trong Java, các API quen thuộc như **`KeyStore`, `KeyPairGenerator`, `Signature`, `Cipher`, `Mac`, `KeyAgreement`** hoạt động thông qua một **JCA/JCE provider**. Provider tương thích có thể ánh xạ operation sang PKCS#11 hoặc API của vendor.

~~~mermaid
flowchart TD
    App[Java business application] --> JCA[JCA/JCE: Signature, KeyStore, Cipher]
    JCA --> Provider[PKCS#11 hoặc vendor provider]
    Provider --> Client[Native PKCS#11 library / driver]
    Client --> Token[HSM token/partition]
    Token --> Result[Signature, ciphertext, MAC hoặc key handle]
    Result --> App
~~~

### Provider selection là quyết định bảo mật

Nếu ứng dụng gọi:

~~~java
Signature signer = Signature.getInstance("SHA256withRSA");
~~~

JCA có thể chọn **provider theo cấu hình ưu tiên**. Đây không phải bằng chứng rằng chữ ký được tạo **trong HSM**.

Muốn kiểm soát rõ, trong một use case phù hợp có thể dùng:

~~~java
Signature signer = Signature.getInstance("SHA256withRSA", pkcs11Provider);
~~~

Khi provider/token hỗ trợ mechanism tương ứng, private key là **key handle của token** và operation được thực thi qua provider HSM. Nhưng phải **kiểm chứng runtime thực tế**, tránh giả định một key nằm trong HSM chỉ vì đã chọn tên provider.

### Không dùng key material dạng byte nếu không cần

Đối với private key không xuất được, `PrivateKey.getEncoded()` có thể trả `null` hoặc bị hạn chế theo provider. **Giá trị `null` đơn lẻ không phải bằng chứng bảo đảm hardware security**. Cần xác minh nguồn key, attributes, token và chính sách bằng khả năng của sản phẩm.

## 10. Java 11+: ví dụ ký với private key đã lưu trong HSM

Ví dụ sau dùng **SunPKCS11 provider có sẵn trong JDK khi được đóng gói/cấu hình** để truy cập một token PKCS#11. Ví dụ giả định **đã có private RSA signing key và chứng thư tương ứng trong token**, được cấp cho mục đích **kiểm thử**.

**Không chạy ví dụ này trên khóa ký production.** Mã chỉ minh họa cách nối JCA với HSM và ký một chuỗi thử. Trong production phải có **business approval, IAM, audit, key version, monitoring và xử lý phiên**.

### 10.1. Tệp cấu hình PKCS#11 minh họa

~~~text
name = TrainingHsm
library = /opt/vendor/pkcs11/libpkcs11.so
slotListIndex = 0
~~~

Đường dẫn thư viện và slot **là placeholder**. Cấu hình thật do nhà cung cấp HSM hướng dẫn; trên Windows, đường dẫn native library sẽ khác.

### 10.2. Mã Java

~~~java
import java.io.Console;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.Provider;
import java.security.Security;
import java.security.Signature;
import java.security.cert.Certificate;
import java.util.Arrays;

public final class HsmPkcs11SigningDemo {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: HsmPkcs11SigningDemo <pkcs11.cfg> <training-key-alias>");
        }

        String configPath = args[0];
        String alias = args[1];

        // Demo cố ý chỉ cho phép alias học tập để tránh ký ngoài ý định.
        if (!alias.startsWith("training-")) {
            throw new SecurityException("Training alias required");
        }

        Provider base = Security.getProvider("SunPKCS11");
        if (base == null) {
            throw new IllegalStateException(
                    "SunPKCS11 provider unavailable in this JDK runtime");
        }

        // Java 11+: tạo provider instance dựa trên file cấu hình token.
        Provider tokenProvider = base.configure(configPath);
        Security.addProvider(tokenProvider);

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                    "Interactive console required for test PIN");
        }

        char[] pin = console.readPassword("Training HSM PIN: ");
        if (pin == null || pin.length == 0) {
            throw new SecurityException("No PIN entered");
        }

        try {
            KeyStore tokenStore = KeyStore.getInstance(
                    "PKCS11", tokenProvider);
            tokenStore.load(null, pin);

            // Alias/key mapping, login và cơ chế truy cập phụ thuộc provider.
            Key key = tokenStore.getKey(alias, null);
            if (!(key instanceof PrivateKey)) {
                throw new IllegalStateException(
                        "Training private key not found");
            }

            Certificate certificate = tokenStore.getCertificate(alias);
            if (certificate == null) {
                throw new IllegalStateException(
                        "Training certificate not found");
            }

            // Giả định key RSA và token hỗ trợ SHA256withRSA.
            // Không dùng chuỗi demo với key ký sản xuất.
            byte[] payload = (
                    "non-production-demo-payload-v1"
            ).getBytes(StandardCharsets.UTF_8);

            Signature signer = Signature.getInstance(
                    "SHA256withRSA", tokenProvider);
            signer.initSign((PrivateKey) key);
            signer.update(payload);
            byte[] signature = signer.sign();

            // Verify bằng public key từ certificate (không cần private key).
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(certificate.getPublicKey());
            verifier.update(payload);
            boolean valid = verifier.verify(signature);

            // Chỉ in metadata/kết quả, KHÔNG in PIN hay key material.
            System.out.println("Token provider: "
                    + tokenProvider.getName());
            System.out.println("Test signature verified: " + valid);
            if (!valid) {
                throw new SecurityException("Signature verification failed");
            }

            // Signature là output; xử lý/lưu/đối chiếu theo chính sách.
        } finally {
            Arrays.fill(pin, '\0');
        }
    }
}
~~~

### 10.3. Những giả định bắt buộc

- JDK có module/provider **`SunPKCS11`**, native library hoạt động và cấu hình slot/token chính xác.
- Token đã được khởi tạo bởi custodian theo quy trình, có key RSA và certificate **trong token** hoặc cách truy xuất certificate phù hợp.
- Thuật toán `SHA256withRSA` được token/provider hỗ trợ cho key đã chọn.
- Login bằng `KeyStore.load(null, pin)` và `getKey(alias, null)` đúng với mapping của provider. **Một số token/provider khác yêu cầu cách login hoặc alias khác**.
- Tên alias bắt đầu `training-` không phải biện pháp bảo mật độc lập; đó chỉ là **cảnh báo ở demo**. Không dùng alias làm authorization hoặc bằng chứng key đã ở HSM.
- `Arrays.fill` giúp giảm thời gian PIN nằm trong mảng Java nhưng **không đảm bảo xóa mọi bản sao trong JVM/native layer**.

### 10.4. Điều đoạn mã chưa làm

Ví dụ **không tạo hoặc provisioning key**, không xác minh FIPS validation, key attributes, certificate chain, EKU/PKI, role độc lập, audit và chính sách khách hàng. Nó cũng **không đảm bảo** các operator và workload khác không thể bypass.

Trong production, cần thêm ít nhất:

1. **Key ID/version** được quản lý đáng tin và liên kết với purpose.
2. **Approvals trên payload/digest** trước khi ký; không biến thiết bị thành signing oracle.
3. **IAM/network boundary** để chỉ workload ký hợp lệ được dùng.
4. **Bằng chứng non-exportability** từ key attributes và hồ sơ provider.
5. Quản lý **PIN/credential/token login** bằng biện pháp phù hợp, không hard-code, không lưu log.
6. Retry/idempotency, session management, rate limit, timeout và HA.
7. Log có toàn vẹn, phản ứng khi token offline, khi key bị suspend hoặc chứng thư hết hạn.
8. Kiểm tra public key/trust chain và định dạng chữ ký theo giao thức thật.

## 11. Mô hình khóa và key usage bên trong HSM

HSM thường bảo vệ những loại khóa khác nhau. **Không nên dùng cùng key material cho mọi mục đích** chỉ vì thiết bị có thể thực thi nhiều cơ chế.

| Key type | Mục đích | Operation có thể có | Kiểm soát quan trọng |
| --- | --- | --- | --- |
| **KEK đối xứng** | Bọc/giải bọc DEK | Wrap/Unwrap hoặc API tương đương | Hạn chế export, phân quyền và dependency |
| **Private signing key** | Chữ ký số/PKI/release | Sign | Non-exportable khi phù hợp, content approval |
| **Public key** | Kiểm tra chữ ký | Verify | Trust, key ID, certificate status |
| **HMAC key** | Xác thực thông điệp | Generate/Verify MAC | Secret shared scope, chống replay ở giao thức |
| **RSA OAEP key** | Key transport/wrapping theo thiết kế | Encrypt/Decrypt | Padding, key usage, trust và cross-protocol |
| **EC agreement key** | Tạo shared secret theo ECDH | Derive | Peer public key authentication và KDF |
| **Root/CA signing key** | Ký chứng thư hoặc trust artifacts | Sign theo PKI | Key ceremony, dual control, audit mạnh |
| **Recovery key** | Phục hồi key được bảo vệ | Unwrap/Restore theo chính sách | Approval độc lập, TTL, break-glass |

**Thiết bị hỗ trợ AES không có nghĩa mọi key AES đều được phép `Encrypt` và `Wrap` đồng thời.** Quyền phải gắn với **purpose**, key attributes và principal.

### Key origin và provenance

Phải biết khóa được **sinh trong HSM**, nhập từ bên ngoài hay restored từ backup. `non-exportable` **sau import** không chứng minh key chưa từng bị xuất trước khi đưa vào HSM.

Ghi key origin vào inventory và dùng các bằng chứng/attestation mà vendor cung cấp nếu yêu cầu; không tuyên bố khóa “được HSM sinh” chỉ từ việc hiện tại nó có handle HSM.

## 12. HSM trong envelope encryption: DEK, KEK và wrapped keys

Một mô hình thực tế: ứng dụng mã hóa hồ sơ bằng **DEK đối xứng**, HSM hoặc KMS bảo vệ **KEK** để bọc DEK.

~~~mermaid
sequenceDiagram
    participant Service as Billing service
    participant HSM as KMS/HSM
    participant DB as Database
    Service->>HSM: Xin DEK hoặc vật liệu phù hợp theo policy
    HSM-->>Service: Plaintext DEK tạm + wrapped DEK nếu API hỗ trợ
    Service->>Service: AES-GCM Encrypt (nonce mới, AAD đúng)
    Service->>DB: Ciphertext + nonce + tag + wrapped DEK + key ID
    Note over Service: Giới hạn plaintext DEK trong RAM và cache
    DB-->>Service: Dữ liệu đã mã hóa và key metadata
    Service->>HSM: Unwrap DEK bằng KEK đúng version và quyền
    HSM-->>Service: DEK plaintext nếu API/protocol cho phép
    Service->>Service: AES-GCM Decrypt và xác minh tag
~~~

### 12.1. Những gì HSM bảo vệ

- **KEK** có thể không cần rời khỏi HSM dưới dạng rõ.
- Quyền **Unwrap** được giới hạn theo key ID, principal và policy.
- HSM có thể tạo key material và thực thi operation khi provider hỗ trợ.
- Quản trị KEK có thể dùng dual control và audit.

### 12.2. Những gì HSM không tự bảo vệ

- **Plaintext DEK** đã được trả cho ứng dụng, bao gồm bản sao trong memory, crash dump hoặc cache.
- **Nonce AES-GCM**: ứng dụng vẫn phải bảo đảm không lặp nonce dưới cùng DEK.
- **AAD và authentication tag**: phải gắn đúng bản ghi, tenant, version và xác minh khi giải mã.
- **Authorization dữ liệu**: KMS có thể biết principal được `Unwrap`, nhưng không nhất thiết biết người dùng cuối có được đọc hóa đơn đó.
- **Ciphertext backup**: restore phải tìm đúng wrapped DEK/KEK version.

### 12.3. Khi HSM nằm trên đường dữ liệu

Một số kiến trúc chọn xử lý phép mã hóa trực tiếp trong HSM để raw key không ra ứng dụng. Điều này có thể hợp lý cho dữ liệu/operation nhạy cảm, nhưng HSM có thể bị hạn chế về **khối lượng dữ liệu, latency, throughput, mechanism hoặc chi phí**.

Không có một quy tắc “tất cả AES-GCM phải chạy trong HSM”; hãy chọn điểm đặt HSM theo **key boundary, performance và threat model**.

## 13. Ký số bằng HSM: bảo vệ private key và signing oracle

### 13.1. Signing key trong HSM

HSM là lựa chọn phổ biến để bảo vệ private key dùng cho:

- Phát hành hóa đơn và tài liệu có giá trị.
- Ký phần mềm, firmware, container/manifest hoặc release.
- Ký chứng thư của CA/PKI.
- Ký timestamp token hoặc tài liệu cần chứng cứ lâu dài.
- Ký giao dịch hoặc dữ liệu xác thực cần mức bảo đảm cao.

Private key có thể được đặt **non-exportable**, còn public key/certificate được phân phối qua kênh tin cậy.

### 13.2. Signing oracle là gì?

Nếu một service có quyền gọi `Sign` trên key nhưng không kiểm tra **nội dung nào được phép ký**, attacker có thể gửi digest hoặc payload trái phép và nhận về chữ ký hợp lệ. HSM đã thực hiện đúng phép mật mã, nhưng **chính sách nghiệp vụ đã thất bại**.

~~~mermaid
flowchart TD
    Request[Yêu cầu ký] --> Identity[Identity + permission]
    Identity --> Context[Purpose, tenant, payload type, business approval]
    Context -->|Không đạt| Deny[Từ chối và ghi audit]
    Context -->|Đạt| Version[Kiểm tra key version/state/cryptoperiod]
    Version -->|Đúng| HSM[HSM Sign]
    Version -->|Sai| Deny
    HSM --> Signature[Chữ ký + key ID/cert metadata]
    Signature --> Audit[Audit và kiểm tra downstream]
    Deny --> Audit
~~~

Với code signing rủi ro cao, phê duyệt có thể phải ràng buộc **exact artifact digest/manifest** và yêu cầu hai người độc lập. Với chữ ký hóa đơn, quyền chỉ nên mở khi **hóa đơn đã chốt và được phê duyệt**.

### 13.3. Chứng thư và chữ ký lịch sử

HSM lưu private key **không thay** được cơ chế PKI. Cần kiểm tra chain, certificate usage, `NotBefore`/`NotAfter`, CRL/OCSP và policy của bên nhận.

Khi thay private signing key, hệ thống thường phải **phân phối public key/chứng thư mới trước khi ký mới**. Chữ ký lịch sử có thể vẫn cần public key, chứng thư và bằng chứng timestamp/LTV. Việc xóa private key không làm chữ ký đã tạo biến mất; việc khóa bị lộ cũng đòi đánh giá chữ ký lịch sử, không chỉ kiểm tra phép `Verify`.

## 14. HSM với HMAC, ECDH, TLS và KDF

### 14.1. HMAC keys

HSM có thể bảo vệ HMAC key và thực hiện `GenerateMac`/`VerifyMac` nếu hỗ trợ. **HMAC dùng cùng secret** cho tạo và xác minh tag, khác chữ ký bất đối xứng. Nếu một bên đối tác phải giữ HMAC secret, HSM của bên phát không thể bảo vệ bản sao bí mật ở phía đối tác.

Chính sách phải xét key version, giao thức xác thực, chống replay, thời hạn thông điệp và quy trình rotation.

### 14.2. Static agreement key / ECDH

Một private ECDH key có thể đặt trong HSM để giảm khả năng xuất. Nhưng **ECDH thuần túy không tự xác thực peer**. Ứng dụng vẫn phải kiểm tra public peer key và dùng **KDF chuẩn**, ràng buộc identity/transcript theo giao thức.

Một số HSM hỗ trợ operation `DeriveKey` và có thể giữ **derived key handle** trong token; các HSM khác có khả năng và semantics khác. Không tự giả định shared secret có thể xuất ra hoặc luôn được giữ trong boundary.

### 14.3. Ephemeral ECDHE/TLS

Một TLS stack thường tự quản lý ephemeral ECDHE keys khi handshake. Dùng HSM để giữ **private authentication key dài hạn** không có nghĩa mọi traffic key hoặc ECDHE private key đều nằm trong HSM.

**Forward secrecy** phụ thuộc giao thức, sự bảo vệ/hủy bí mật tạm và điều kiện xác thực, không xuất hiện tự động vì có HSM.

### 14.4. HKDF và password-derived keys

HSM có thể có các cơ chế dẫn xuất khóa, nhưng **không phải mọi HSM đều hỗ trợ HKDF hoặc Argon2** theo cùng API. Một master key non-exportable có thể dùng dẫn xuất subkey **nếu thiết bị và policy hỗ trợ**.

Với mật khẩu người dùng, không lấy hash đơn giản làm KEK. Cần password-based KDF phù hợp, salt, thông số cost và threat model; HSM có thể bảo vệ recovery root/pepper hoặc KEK theo thiết kế, nhưng không thay được quy trình xác thực và chống đoán mật khẩu.

## 15. Vòng đời khóa trong HSM

HSM cần được tích hợp vào **lifecycle control plane**. Những trạng thái **Pre-activation, Active, Suspended, Deactivated, Compromised, Destroyed** là **mô hình quản trị logic**; trạng thái object/token và API cụ thể không nhất thiết dùng cùng tên.

~~~mermaid
stateDiagram-v2
    [*] --> PreActivation: Generate/import theo policy
    PreActivation --> Active: Approval + key usage/IAM readiness
    PreActivation --> Destroyed: Hủy trước khi dùng
    Active --> Suspended: Cô lập hoặc thay đổi rủi ro
    Suspended --> Active: Đánh giá và phê duyệt resume
    Suspended --> Compromised: Kết luận không còn an toàn
    Active --> Deactivated: Ngừng new-use, chuyển key v2
    Active --> Compromised: Phát hiện compromise
    Deactivated --> Destroyed: Hết phụ thuộc và retention
    Compromised --> Destroyed: Ứng cứu và tiêu hủy
    Destroyed --> [*]
~~~

### 15.1. Generation và pre-activation

Tạo key object, gắn attributes, owner, purpose, key ID/version và policy. **Chưa cấp quyền dùng production** cho đến khi đã kiểm tra:

- Nguồn tạo/import.
- Thuật toán, độ dài/curve và usage.
- Non-exportability nếu yêu cầu.
- IAM/grant/role và khả năng tự nâng quyền.
- Khả năng phân phối public key/chứng thư.
- Backup/DR và phương án rollback.
- Negative tests chứng minh key chưa active **bị chặn đúng thực tế**.

### 15.2. Active

Trong thời gian Active, quyền operation phải gắn đúng workload và purpose. HSM có thể thực thi operation nhưng ứng dụng chịu trách nhiệm ngữ nghĩa dữ liệu, key version và authorization bên ngoài.

### 15.3. Suspended / Disabled

Khi có dấu hiệu lạm dụng, có thể chặn key hoặc principal qua HSM/KMS/IAM. Nhưng:

- `Disabled` ở provider có thể chặn cả **Decrypt/Unwrap** dữ liệu cũ.
- Cached plaintext DEK, session key hoặc chữ ký/token đã phát **không tự biến mất**.
- Một số key objects/session có semantics riêng về khả năng đóng và thu hồi; phải kiểm tra API sản phẩm.
- Cần negative test và giám sát hậu quả availability.

### 15.4. Deactivated

Khóa cũ ngừng dùng để **tạo dữ liệu/chữ ký mới**, nhưng có thể còn cần phục vụ **legacy decrypt/unwrap** hoặc giữ public verification material. Không nhầm trạng thái này với yêu cầu xóa vật liệu ngay lập tức.

### 15.5. Compromised và Destroyed

Nếu private/secret key được xác nhận đã lộ, **không chỉ Enable lại** sau khi vá lỗi. Phải thay vật liệu, đánh giá dữ liệu/chữ ký lịch sử và thu hồi trust/quyền phù hợp.

**Destroyed** yêu cầu kiểm tra vật liệu đã được tiêu hủy trong **phạm vi và cơ chế xác nhận của provider**, cùng backup/replica/archives và điều kiện retention. Xóa label/alias không phải chứng cứ phá hủy key material.

## 16. Key owner, key custodian, dual control và HSM roles

HSM thường có các role quản trị khác nhau. Nhưng **role của thiết bị** và **vai trò quản trị doanh nghiệp** không phải lúc nào cũng trùng tên hoặc trách nhiệm.

| Vai trò | Trách nhiệm | Điều không nên có mặc định |
| --- | --- | --- |
| **Key owner** | Phê duyệt purpose, cryptoperiod, rotation, recovery, hủy và rủi ro | Raw private key hoặc toàn quyền HSM |
| **Key custodian** | Sinh/lưu/bảo trì key, áp dụng policy và vận hành backup/rotation | Quyền `Sign/Decrypt` ngoài nhiệm vụ |
| **HSM Security Officer / admin** | Quản trị token, roles, cấu hình theo thiết bị | Quyền tự cấp key usage mà không cần phê duyệt |
| **Key user / workload** | Gọi phép toán được phép trên key cụ thể | Quyền thay policy, backup/export hoặc hủy key |
| **Security reviewer** | Kiểm tra độc lập thuật toán/IAM/export/incident | Quyền đọc secret để review |
| **Auditor** | Đối soát approval, key metadata, HSM events | Quyền sửa audit hoặc thực thi phép toán |
| **Incident responder** | Cô lập nhanh và bảo toàn bằng chứng | Quyền resume key compromised tùy ý |

### 16.1. Dual control và key ceremony

Một số thao tác quan trọng như **root signing key generation, khôi phục master key, nhập/export vật liệu hoặc hủy key nhạy cảm** có thể yêu cầu **hai người độc lập**, hoặc quorum/M-of-N theo chính sách.

Phân biệt:

- **Dual control:** nhiều người cùng cho phép/tham gia operation.
- **Split knowledge:** không một người giữ đủ thông tin để tự tái tạo secret.
- **M-of-N threshold:** cần ngưỡng share/chủ thể theo cơ chế được thiết kế.
- **Key ceremony:** chuỗi hoạt động có kịch bản, người chứng kiến và bằng chứng.

Không mặc định mọi HSM tự cung cấp 2-of-2 hoặc 3-of-5. Kiểm tra **hỗ trợ bản địa, thuộc tính key và quy trình vận hành**; không tự cắt một chuỗi secret thành hai nửa rồi gọi là secret sharing an toàn.

### 16.2. Ngăn self-escalation

Một admin có thể không có `Decrypt` trực tiếp nhưng lại có quyền **sửa key policy/grant để tự cấp `Decrypt`**. Khi đánh giá separation of duties, phải xét **quyền gián tiếp** và account có thể đổi role/trust/pipeline.

Hệ thống có thể dùng approval workflow, PAM/JIT, IAM boundaries và audit độc lập để giới hạn quyền vượt phạm vi.

## 17. Backup, replication, high availability và disaster recovery

HSM có thể bảo vệ khóa rất tốt nhưng nếu **mất vật liệu mà không có đường phục hồi**, dữ liệu mã hóa hoặc chữ ký phục vụ nghiệp vụ có thể bị ảnh hưởng lâu dài.

### 17.1. Điều cần xác định

1. **Điều gì được backup?** Raw material, wrapped internal backup, HSM cluster state, key handles, certificate hay metadata?
2. **HSM có non-exportable key không?** Có cơ chế backup/clone/restore bảo vệ riêng không?
3. **Ai kiểm soát backup?** Có dual control, token/quorum, access review và audit?
4. **Restore được ở đâu?** Thiết bị cùng loại/firmware, partition, account/region hay chỉ trong cluster?
5. **Key identity có giữ nguyên không?** Ứng dụng có cần cập nhật key ID, CKA_ID, alias hoặc certificate binding?
6. **Phải restore cái gì cùng nhau?** Key material, key attributes, IAM/role, object metadata, wrapped DEK và data backup.
7. **Bao giờ hủy được backup?** Retention và các bản sao phục hồi có còn phụ thuộc key cũ không?

### 17.2. HA cluster không thay thế backup

Một cụm HSM đồng bộ key có thể tăng **availability**, nhưng lỗi policy, thao tác xóa nhầm, compromise quyền quản trị hoặc cập nhật sai có thể **lan sang các node đồng bộ**. Do đó HA không tự thay thế **backup có kiểm soát và phương án khôi phục sau lỗi logic**.

### 17.3. Restore drill cần kiểm thử dữ liệu thật theo phạm vi cho phép

Không chỉ kiểm tra rằng “thiết bị online”. Cần xác minh bằng dữ liệu thử:

- Sau restore, key ID/attributes và quyền còn đúng không?
- Có thể giải bọc một DEK thử hoặc xác minh chữ ký thử?
- Có chống được việc restore phiên bản key/policy đã bị thu hồi?
- Có audit người thực hiện, thời gian và thiết bị đích?
- Có vô tình tạo thêm bản sao không được kiểm soát?

**Không bao giờ tải toàn bộ secret ra plaintext để làm bằng chứng restore nếu không có yêu cầu và kiểm soát tương ứng.**

## 18. Rotation: thay key vật liệu, không chỉ alias

### 18.1. Rotation KEK

Với envelope encryption, xoay **KEK** có thể là:

1. Sinh `KEK-v2` trong HSM/KMS và cấu hình policy.
2. Cho app/reader hiểu đúng key version mới.
3. Kích hoạt `v2` cho **Wrap DEK mới**, ngừng Wrap mới bằng `v1`.
4. **Rewrap** những DEK đang được bọc bằng `v1` theo kế hoạch.
5. Giữ `v1` cho **Unwrap** legacy nếu còn dữ liệu phụ thuộc và key chưa compromise.
6. Xác nhận backup/DR và tất cả wrapped DEK đã di chuyển.
7. Chỉ hủy `v1` sau khi đạt retention/dependency checks.

**Rewrap không nhất thiết re-encrypt toàn bộ dữ liệu.** DEK có thể giữ nguyên nên ciphertext AES-GCM có thể giữ nguyên.

### 18.2. Rotation DEK

Nếu **DEK bị lộ**, đổi KEK không đủ. Đối thủ có DEK vẫn có thể giải mã ciphertext cũ. Cần **đánh giá thay DEK và re-encrypt dữ liệu** bằng key mới, nonce mới theo quy tắc, cập nhật metadata và tác động dữ liệu lịch sử.

### 18.3. Rotation private signing key

Sinh **private/public pair mới** và phân phối public key/chứng thư trước khi ký mới. Key cũ ngừng Sign nhưng public key/chứng thư có thể còn cần để verify lịch sử.

**Certificate renewal với cùng private key không phải private-key rotation**. Phải biết key pair thực sự đã đổi.

### 18.4. Automatic rotation của managed KMS

Một số KMS tự xoay **backing key material** trong logical key resource, nhưng điều đó **không tự mã hóa lại mọi ciphertext bên ngoài** và **không áp dụng như nhau** cho mọi symmetric/asymmetric/imported key. HSM tự quản lý cũng không mặc định có API tự xoay key theo lịch.

Cần phân biệt **logical resource ID, material version, application key version và alias**; kiểm thử hành vi restore/decrypt của dữ liệu cũ trước khi dựa vào automatic rotation.

## 19. Secure deletion và zeroization

**Zeroization** là việc xóa hoặc làm mất hiệu lực bí mật khỏi phạm vi xác định bằng cơ chế được thiết kế, khác với chỉ xóa một bản ghi metadata.

Trong HSM, quy trình tiêu hủy có thể gồm:

- Đánh dấu key không còn được phép dùng.
- Thu hồi grants/roles và chặn những session mới.
- Hủy object/key material hoặc key handle theo API.
- Đảm bảo trạng thái trên các node/replica liên quan và backup.
- Lưu bằng chứng theo thời gian, người thao tác, key ID và provider outcome.

**Không hứa hẹn hành động “DeleteKey” đồng nghĩa mọi bản sao ở mọi backup đã bị zeroize ngay**. Một managed KMS có thể có giai đoạn **pending deletion**; một HSM có thể có cơ chế backup được mã hóa cần xóa theo quy trình khác.

### Destruction readiness checklist

- Không còn wrapped DEK, ciphertext hoặc backup cần key cũ?
- Không còn chữ ký cần private key cũ để tạo output mới? Public material có được giữ cho verify?
- Có legal hold hoặc retention không cho xóa?
- Có replica/DR instance còn giữ key hoặc bản bọc liên quan?
- Có phê duyệt owner/security và separation of duties khi cần?
- Hành động xóa đã được xác nhận bằng provider event và audit đối chiếu?

**Đình chỉ hoặc đổi alias là hành động có thể đảo ngược hơn; hủy vật liệu khóa có thể gây mất dữ liệu không thể khôi phục.**

## 20. Performance, throughput, session pool và availability

HSM thường là tài nguyên chia sẻ có giới hạn. Thiết kế hệ thống phải tránh biến HSM thành **điểm nghẽn hoặc điểm lỗi đơn**.

### Những yếu tố cần đo

| Yếu tố | Rủi ro | Hướng kiểm soát |
| --- | --- | --- |
| Latency mỗi lần ký/unwrap | Tăng thời gian xử lý API | Async workload phù hợp, tối ưu luồng và số lần gọi |
| Peak signing TPS | Vượt khả năng HSM hoặc quota | Capacity planning, rate limit, HA |
| Session/login limits | Cạn session hoặc timeout | Session pooling theo provider, backoff, tránh leak session |
| Network/driver failure | Sign/Unwrap đồng loạt thất bại | Cụm HA, retry an toàn, health monitoring |
| Thay chứng thư/key version | Service dùng sai key | Versioned routing và preflight |
| Cache DEK | Giảm calls nhưng mở rộng exposure | TTL/hạn mức, zeroization best-effort, compromise runbook |
| Cross-region DR | Chậm hoặc không có key material | Kiểm chứng replication/restore semantics |
| Audit volume | Thiếu log hoặc làm nghẽn hệ thống | Thiết kế pipeline đáng tin, sampling có kiểm soát cho telemetry phụ, không bỏ log bắt buộc |

### Fail closed hay fail open?

Với thao tác mật mã nhạy cảm, khi HSM báo **không thể xác thực quyền, key suspended hoặc policy không rõ**, không nên tự fallback sang **private key lưu trong file**, secret test hoặc key version cũ chưa được phê duyệt. Đó là lỗi **fail open**.

Ứng dụng có thể thiết kế **hàng đợi, retry, báo lỗi rõ và cơ chế HA**; fallback chỉ được phép khi có **phương án dự phòng được quản trị an toàn**.

### Idempotency

Đặc biệt với **chữ ký số**, một retry có thể dẫn tới chữ ký được tạo hai lần hoặc giao dịch được xử lý nhiều lần. Operation có tính quyết định hay không còn tùy thuật toán và provider. Hệ thống phải định nghĩa **transaction ID, request digest, trạng thái xử lý và idempotency ở tầng nghiệp vụ**, không dựa vào chữ ký byte-for-byte giống nhau để nhận biết đã xử lý.

## 21. Case study: Billing sử dụng HSM để ký và bảo vệ DEK

### Bối cảnh

Một nền tảng hóa đơn cần:

- Mã hóa thông tin khách hàng và file hóa đơn.
- Ký hóa đơn số trước khi gửi đối tác.
- Giữ khả năng giải mã hồ sơ sau nhiều năm theo retention.
- Cho phép rotation mà không gián đoạn dịch vụ.
- Cung cấp bằng chứng audit ai dùng khóa, thao tác gì.

### Kiến trúc gợi ý

| Tài sản | Nơi sử dụng/lưu | Quy tắc |
| --- | --- | --- |
| **DEK AES-GCM** | Tạo per object/shard theo thiết kế, chỉ tồn tại ngắn trong app; wrapped DEK lưu cùng dữ liệu | Không log DEK, nonce không lặp dưới cùng key |
| **KEK** | HSM/KMS key riêng với `Wrap/Unwrap` | IAM service cụ thể, rotation/backup/DR |
| **Private invoice-signing key** | HSM non-exportable nếu được hỗ trợ | Chỉ `Sign` sau business approval |
| **Public verification key/cert** | Kho trust và thông tin hóa đơn | Phân phối được xác thực, kiểm tra chain/usage |
| **Key inventory** | Control plane đáng tin | Purpose, key ID/version, owner, cryptoperiod, dependencies |
| **Audit** | Hệ thống log có quyền và retention riêng | Ghi principal, operation, kết quả, policy revision |
| **Recovery** | Quy trình quản trị riêng | Phê duyệt độc lập, restore thử và kiểm tra dữ liệu |

### Luồng nghiệp vụ

~~~mermaid
sequenceDiagram
    participant User as Billing API
    participant App as Java Billing service
    participant KMS as KMS/HSM
    participant Data as Data store
    participant Audit as Security audit
    User->>App: Hóa đơn đã được phê duyệt
    App->>App: Kiểm tra identity, invoice state, tenant
    App->>KMS: Generate/wrap DEK theo policy
    KMS-->>App: DEK tạm + wrapped DEK (nếu hỗ trợ)
    App->>Data: Lưu AES-GCM ciphertext, tag, nonce, key IDs
    App->>KMS: Sign canonical invoice digest bằng key ký
    KMS-->>App: Signature
    App->>Data: Lưu chữ ký, cert/key version
    KMS-->>Audit: Operation logs theo khả năng provider
    App-->>Audit: Business approval + request correlation
~~~

### Tình huống 1 — Bị lộ credential gọi `Sign`

- Cô lập service credential/grant và có thể suspend signing key theo quy trình.
- Điều tra những chữ ký được HSM tạo: HSM **không tự xác nhận hóa đơn được chốt hợp lệ**.
- Xác định private key có lộ thực sự không; `non-exportable` giảm một số đường lộ nhưng không xóa nguy cơ ký trái phép.
- Khi thay khóa ký, phát public key/chứng thư mới và xử lý niềm tin của chữ ký cũ.

### Tình huống 2 — KEK có grant `Unwrap` quá rộng

- Thu hồi grant hoặc cô lập key theo mức rủi ro.
- Đánh giá những DEK plaintext có thể đã được trả ra.
- Nếu **DEK đã lộ**, chỉ rewrap không đủ; cần xem xét re-encrypt dữ liệu.
- Disable KEK có thể làm nhiều record không đọc được khi service phải unwrap mới.
- Phối hợp cache invalidation và availability; **cached DEK không tự bị xóa khi khóa KEK bị disable**.

### Tình huống 3 — Thiết bị HSM bị mất hoặc không khả dụng

- Chuyển sang cụm/region dự phòng **theo quy trình đã được thử nghiệm**.
- Nếu key material non-exportable chỉ tồn tại trên một thiết bị không có backup/replication, hệ thống có thể mất khả năng ký hoặc giải bọc dữ liệu.
- Không khôi phục bằng cách lưu một bản private key plaintext ngoài KMS “cho chắc” mà không được phê duyệt.
- Rà soát thiết kế HA, DR, quyền key custodian và bằng chứng restore.

## 22. Case study: HSM bảo vệ khóa ký phần mềm

Một pipeline phát hành phần mềm sử dụng private key `release-signing-v3` trong HSM. Build system tạo artifact, nhưng signing workflow là bước có rủi ro cao vì chữ ký có thể khiến hàng nghìn thiết bị tin và cài đặt một bản phát hành.

### Quy trình an toàn hơn

1. Build tạo artifact từ source được quản trị, có manifest và digest.
2. **Release owner** phê duyệt exact manifest/digest và version/channel.
3. **Security approver độc lập** kiểm tra provenance, điều kiện phát hành và key usage.
4. **Signing service** xác thực approval, khóa payload bất biến, kiểm tra trạng thái key.
5. HSM thực thi `Sign` trên **đúng digest đã duyệt** bằng private key non-exportable.
6. Kết quả gồm signature, key/cert identifier, manifest và audit correlation.
7. Consumer kiểm tra signature, trust, version/policy và cơ chế chống rollback phù hợp.
8. Khi rotate key, phân phối public verification key trước cutover và duy trì thông tin xác minh artifact lịch sử.

### Một lỗi nghiêm trọng có thể vẫn xảy ra

Nếu `Sign` API của HSM được cấp cho toàn bộ CI service account và workflow phê duyệt chỉ là giao diện không cưỡng chế, attacker chiếm CI có thể gọi trực tiếp HSM để ký artifact độc hại.

**HSM đã bảo vệ private key nhưng chưa bảo vệ quy trình cấp phép nội dung ký.** Cần kiểm soát **đường gọi provider, IAM/grant và nội dung được phép ký**.

## 23. HSM và xử lý sự cố

### 23.1. Phân biệt những loại compromise

| Tình huống | Điều có thể đã bị lộ | Hướng xử lý |
| --- | --- | --- |
| App service credential bị lấy | Quyền gọi các API HSM/KMS được cấp | Thu hồi credential/grant, điều tra Sign/Decrypt/Unwrap |
| Private key xuất được đã bị lấy | Raw private key có thể ở ngoài HSM | Thay khóa/chứng thư, thu hồi trust và đánh giá chữ ký lịch sử |
| HSM tamper alarm | Không biết ngay vật liệu đã lộ hay đã zeroize | Cô lập, theo hướng dẫn vendor, bảo toàn log, đánh giá DR |
| KEK có policy sai | Khả năng Unwrap rộng hơn mục đích | Chặn quyền, xác định DEK/ciphertext bị ảnh hưởng |
| Plaintext DEK cache bị truy cập | Raw DEK ngoài boundary | Thay DEK/re-encrypt tùy phạm vi; đổi KEK không đủ |
| Signing oracle | Chữ ký hợp lệ trên nội dung không được phê duyệt | Điều tra artifact/token/chữ ký và đường phát hành |
| HSM credential của admin bị lộ | Có thể sửa policy, key state hoặc tạo grant | Cô lập role, rà soát self-escalation, audit |
| HSM mất hoàn toàn | Mất khả năng dùng khóa hoặc vật liệu | DR/backup/replica, phục hồi có kiểm soát |

### 23.2. Runbook cơ bản

1. **Nhận diện:** Key ID/version, role, principal, HSM partition, environment và thời điểm.
2. **Cô lập:** Chặn credential/grant hoặc key operation theo phạm vi cần thiết; đánh giá dữ liệu đang được phục vụ.
3. **Bảo toàn chứng cứ:** Provider logs, application audit, approval, key metadata, các request liên quan.
4. **Xác định loại lộ:** Raw material hay chỉ quyền API? Có plaintext DEK/cache không?
5. **Đánh giá ảnh hưởng lịch sử:** Ciphertext, DEK, wrapped key, chữ ký, JWT, HMAC, ECDH sessions và backups.
6. **Sinh và kích hoạt key mới** từ nguồn tin cậy khi cần, cùng chính sách IAM phù hợp.
7. **Di chuyển/thu hồi trust:** Rewrap, re-encrypt, JWKS/certificate updates, partner notification.
8. **Kiểm thử và kiểm toán:** Negative tests, restore/DR, trạng thái provider và dữ liệu cũ.
9. **Tiêu hủy/đóng sự cố** theo dependency, retention và phê duyệt; không làm mất chứng cứ.

### 23.3. Suspend không phục hồi bí mật đã lộ

Một private key đã bị sao chép ở ngoài HSM **không trở lại bí mật** nhờ `DisableKey`. Một raw DEK bị lộ **không an toàn trở lại** nhờ được wrap bằng KEK khác. HSM hỗ trợ giảm rủi ro, nhưng không thể thay đổi sự thật rằng đối thủ đã có bản sao.

## 24. Audit và monitoring cho HSM

### Bản ghi audit minh họa

~~~yaml
eventType: "HSM_SIGN_REQUEST"
requestId: "req-2030-0941"
keyId: "billing-invoice-signing-v2"
keyVersion: "v2"
purpose: "INVOICE_SIGNATURE"
principal: "billing-invoice-signer"
environment: "production"
operation: "Sign"
businessApprovalRef: "invoice-approval-id"
keyPolicyRevision: "hsm-policy-v12"
providerResult: "SUCCESS"
occurredAtUtc: "2030-06-10T10:14:03Z"
auditCorrelationId: "corr-7fa2"
~~~

Đây là **cấu trúc ví dụ**, không phải một schema sự kiện HSM chung. Tùy sản phẩm, log provider có thể thiếu một số thông tin business context; ứng dụng phải ghi **event riêng có correlation ID** để nối với quyết định nghiệp vụ.

### Những event nên giám sát

- `GenerateKey`, `ImportKey`, thay key attributes và policy/grant.
- `Sign`, `Decrypt`, `Unwrap`, `DeriveKey` bất thường theo key/version/principal.
- Đăng nhập admin, thất bại xác thực, role elevation và phiên quản trị.
- Lệnh export/backup/restore và key ceremony.
- Tamper event, hardware fault, entropy/DRBG self-test và health degradation.
- Key activation, suspend, rotate, schedule deletion và destruction completed.
- Sai lệch giữa application key inventory và provider key resources.
- Số request bị chặn, retries, session exhaustion, throughput/latency và HA failover.

### Audit phải đủ nhưng không tiết lộ bí mật

**Không log:** private key, raw AES/HMAC key, DEK plaintext, PRK/master, HSM PIN, recovery secret, sensitive payload hoặc thông tin khách hàng không cần thiết.

Đối với digest dùng để ràng buộc approval, cần xác định **hash của dữ liệu gì, có liên kết đến nội dung nhạy cảm hay không, trust source và quyền đọc audit**. Một digest public của dữ liệu có không gian đoán nhỏ cũng có thể làm lộ thông tin qua dò đoán; không coi hash luôn vô hại.

## 25. Những sai lầm thường gặp khi sử dụng HSM

| Sai lầm | Tại sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Nghĩ HSM làm toàn bộ hệ thống an toàn | App/IAM vẫn có thể bị lạm dụng | Defense in depth, business approval |
| Có private key trong HSM nên cấp `Sign` cho mọi workload | Signing oracle và chữ ký trái phép | Purpose, exact digest, least privilege |
| Tin key non-exportable nghĩa là không thể có bản sao | Khóa import/backup cũ có thể tồn tại | Key provenance, kiểm soát import/export/DR |
| Coi FIPS 140-3 của một model là chứng nhận cho mọi deployment | Sai boundary/version/mode | Xác minh đúng certificate và security policy |
| Gọi JCA mặc định rồi cho rằng dùng HSM | Provider có thể là software | Chỉ định provider, xác minh runtime |
| Dựa vào `Key.getEncoded()==null` để chứng minh key trong phần cứng | Chỉ là hành vi API | Kiểm tra token/object attributes và provenance |
| Đổi label/alias để “rotate” | Vật liệu khóa có thể không đổi | Sinh material mới và xác minh key/version |
| Ghi PIN hoặc raw key vào file cấu hình | Tăng khả năng lộ bí mật | Credential delivery an toàn, no logging |
| Coi HSM backup như file plaintext copy | Bỏ qua cơ chế được hỗ trợ | Protected backup/restore theo vendor |
| Không thử restore/DR | Thiết bị hỏng dẫn đến mất khóa | DR drills với key test và data sample |
| Dùng HSM KEK mã hóa trực tiếp mọi record | Latency cao, trộn trách nhiệm | DEK/KEK envelope encryption khi thích hợp |
| Disable KEK rồi tưởng mọi dữ liệu ngừng giải mã | Cached plaintext DEK có thể còn | Quản lý cache, cô lập workload |
| Xóa KEK khi vẫn có wrapped DEK/backup cũ | Mất dữ liệu không thể khôi phục | Dependency inventory trước Destroy |
| Chỉ rewrap khi DEK đã lộ | DEK bị lấy vẫn giải mã ciphertext | Thay DEK, re-encrypt và ứng cứu |
| Dùng lại EC key cho ECDSA và ECDH không kiểm soát | Trộn purpose/key usage | Tách cặp khóa theo giao thức |
| Tin HSM tự chống MITM ở ECDH | HSM không thay peer authentication | Xác thực public peer key và transcript |
| Không giới hạn phiên/grant HSM | Cạn session và mở rộng quyền | Pool, timeout, least privilege |
| Thiếu log giữa ứng dụng và KMS/HSM | Không liên kết chữ ký với hóa đơn nào | Correlation ID, audit hai lớp |
| Để một admin tự sửa policy và dùng khóa | Self-escalation | SoD, dual control, PAM và audit |
| Bỏ qua HA cluster và network latency | Điểm lỗi tập trung | Capacity planning, HA/DR và fail closed |
| Tưởng hủy alias đồng nghĩa xóa vật liệu | Key material có thể vẫn tồn tại | Provider deletion/destruction evidence |

## 26. Checklist triển khai HSM trong production

1. **Mục đích:** HSM bảo vệ loại khóa nào (KEK, signing, HMAC, static ECDH, CA, recovery) và tại sao cần hardware boundary?
2. **Threat model:** Đối thủ nào cần chống: admin hệ điều hành, malware host, người nội bộ, kẻ có thiết bị vật lý, credential KMS bị lộ?
3. **Product assurance:** Đã xác minh model, firmware, FIPS 140-3 validation/mode và các bảo đảm liên quan trong đúng phạm vi cần?
4. **Key generation:** Key được sinh trong HSM bằng entropy/DRBG phù hợp hay import từ nguồn đã được kiểm chứng?
5. **Key provenance:** Inventory ghi đúng generated/imported/restored; key material có từng tồn tại ngoài HSM không?
6. **Attributes:** Non-exportability, sensitivity, allowed operations, token persistence, roles và supported mechanisms được đặt đúng?
7. **Provider/API:** PKCS#11/JCA hoặc KMS API hỗ trợ thuật toán, key size, signature scheme, key wrapping và session?
8. **Không xuất raw secret:** Có kiểm tra đường export/import/backup và không log private key/DEK/HMAC secret/PIN?
9. **IAM/SoD:** Key owner, custodian, key user, security reviewer và auditor có quyền riêng; admin có tự nâng quyền được không?
10. **Key ceremony:** Với root/recovery/CA critical key, đã đánh giá dual control/M-of-N và bằng chứng thao tác?
11. **Pre-activation:** Khóa mới chưa được phép dùng production trước phê duyệt; có negative test thực tế?
12. **Sign policy:** Workload ký chỉ đúng key/version/purpose; nội dung/digest đã có business approval?
13. **PKI:** Public key, certificate chain, key usage, revocation, timestamp/LTV và retention có được xem xét?
14. **Envelope encryption:** DEK và KEK tách biệt, wrapped DEK + key metadata đủ để decrypt; AES-GCM nonce không lặp?
15. **Plaintext DEK:** Nếu app nhận DEK từ KMS, có giới hạn memory/cache, logging và quy trình cô lập khi lộ?
16. **HMAC/ECDH:** Shared secrets có phạm vi đúng; ECDH có peer authentication, KDF và key lifecycle riêng?
17. **Cryptoperiod:** Key state, rotation schedule/trigger, new-use vs legacy operations và dependency đều được ghi?
18. **Rotation:** Có cutover, rewrap/re-encrypt, rollback, audit và kiểm thử reader/verifier?
19. **Suspension:** Có thể chặn đúng operation/principal, kể cả đường gọi API trực tiếp, và hiểu tác động cache/session?
20. **Backup/DR:** Có HA và backup được hỗ trợ, kiểm thử restore, key identity, quyền recovery và dữ liệu lịch sử?
21. **Deletion:** Chỉ hủy khi hết dependency/retention; đối soát backup và bằng chứng zeroization theo provider?
22. **Operational capacity:** Có đo latency, TPS, session limits, fault tolerance, network isolation và upgrade/patch strategy?
23. **Audit:** Có log HSM/KMS + business audit với correlation ID, quyền đọc độc lập và retention?
24. **Incident response:** Runbook phân biệt lộ credential, raw KEK/DEK/private key, signing oracle và physical tamper?
25. **Negative tests:** Workload sai tenant/sai purpose/suspended key có bị từ chối; quản trị viên có thể bypass workflow không?
26. **Review:** Có đánh giá thường kỳ certificate, firmware, key policy, quyền export, orphan keys và recovery paths?

### Ghi nhớ

**HSM** là **mô-đun phần cứng bảo vệ khóa mật mã và thực thi các thao tác trong cryptographic boundary được xác định**. Nó hữu ích cho **private signing key, KEK, root/CA/recovery keys, HMAC và key agreement** tùy khả năng sản phẩm, đồng thời hỗ trợ kiểm soát **key generation, non-exportability, key usage, operator roles, backup và audit**. Nhưng HSM **không thay thế KMS/control plane, IAM, kiểm tra nội dung nghiệp vụ, PKI, nonce/AAD của AES-GCM hay quản lý dữ liệu lịch sử**. Trong **envelope encryption**, KEK có thể ở HSM trong khi DEK tạm dùng ở ứng dụng; vì vậy **DEK plaintext cache vẫn là rủi ro cần xử lý**. Một thiết kế an toàn phải gắn HSM với **key owner/custodian, dual control khi cần, quản lý trạng thái, rotation, backup/DR, thu hồi và hủy có bằng chứng**, và luôn đối chiếu khả năng thực tế của HSM thay vì dựa vào tên gọi hoặc tuyên bố marketing.
