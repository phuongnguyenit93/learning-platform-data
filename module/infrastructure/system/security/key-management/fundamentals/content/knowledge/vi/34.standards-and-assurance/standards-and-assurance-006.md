# ASVS cryptography requirements

Trong chương **Chuẩn và assurance** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích các yêu cầu mật mã của OWASP Application Security Verification Standard (ASVS), cách đọc mã yêu cầu, mức xác minh và cách biến yêu cầu thành bằng chứng kiểm thử. Trọng tâm là chương V11 Cryptography của ASVS 5.0.0: quản lý vòng đời và inventory khóa, triển khai primitive an toàn, mã hóa, hashing, giá trị ngẫu nhiên, mật mã khóa công khai và bảo vệ dữ liệu khi đang xử lý.

ASVS giúp tổ chức xác định kết quả bảo mật cần đạt và cách xác minh ứng dụng. Đây không phải hướng dẫn cấu hình KMS/HSM cho mọi nhà cung cấp, cũng không thay thế một tiêu chuẩn quản lý khóa chuyên biệt. ASVS V11.1.1 yêu cầu có chính sách quản lý khóa và vòng đời khóa dựa trên một chuẩn như NIST SP 800-57; các quy trình cụ thể cần được thiết kế theo loại khóa, dữ liệu, threat model và nền tảng triển khai.

## 1. ASVS là gì?

**OWASP Application Security Verification Standard (ASVS)** là bộ yêu cầu bảo mật có thể xác minh dành cho ứng dụng web và dịch vụ web. ASVS có ba mục đích chính:

- Cung cấp thước đo để đánh giá mức độ tin cậy bảo mật của ứng dụng.
- Hướng dẫn đội phát triển xây dựng các kiểm soát bảo mật có thể kiểm chứng.
- Làm cơ sở đưa yêu cầu bảo mật vào mua sắm, hợp đồng và đánh giá nhà cung cấp.

ASVS mô tả các kết quả bảo mật phải đạt. Nó không buộc mọi hệ thống phải dùng cùng một sản phẩm, kiến trúc hay thư viện. Một ứng dụng có thể đáp ứng yêu cầu bằng KMS, HSM, thư viện mật mã đã được kiểm chứng hoặc tổ hợp các cơ chế phù hợp, miễn là kết quả được chứng minh và đáp ứng tiêu chuẩn áp dụng.

ASVS cũng phân biệt yêu cầu với hướng dẫn triển khai. Ví dụ, một yêu cầu có thể đòi hỏi dùng implementation mật mã đã được kiểm chứng; việc chọn provider Java, cấu hình HSM hay viết test cụ thể cần dựa trên tài liệu kỹ thuật tương ứng.

## 2. Phiên bản và cách tham chiếu yêu cầu

Tại thời điểm biên soạn bài học này, **ASVS 5.0.0 là bản stable**. Nhánh phát triển chính có thể chứa thay đổi đang được xem xét; khi đánh giá tuân thủ hoặc lập báo cáo, nên dùng một bản phát hành cố định thay vì tham chiếu nội dung chưa ổn định.

ASVS 5.0 có thay đổi cấu trúc lớn so với 4.x. Chương mật mã từng mang mã V6 Stored Cryptography trong ASVS 4.0.3; trong ASVS 5.0.0, nội dung này nằm ở **V11 Cryptography**. Không được lấy mã yêu cầu của phiên bản cũ rồi gắn nhãn phiên bản mới nếu chưa đối chiếu mapping.

OWASP khuyến nghị gắn phiên bản vào mã yêu cầu. Ví dụ:

~~~text
v5.0.0-11.1.1
~~~

Mã này chỉ rõ yêu cầu 11.1.1 của ASVS 5.0.0. Khi nâng cấp phiên bản ASVS, cần kiểm tra lại nội dung và mapping vì các major release có thể đổi cấu trúc và số hiệu yêu cầu.

## 3. ASVS verification levels

ASVS có ba mức xác minh. Các yêu cầu ở mức cao hơn bổ sung cho mức thấp hơn; để đạt một mức, ứng dụng cần đáp ứng các yêu cầu áp dụng ở mức đó và các mức bên dưới.

| Mức | Ý nghĩa | Cách sử dụng |
|---|---|---|
| L1 | Nền tảng tối thiểu, tập trung vào rủi ro phổ biến và dễ khai thác | Điểm bắt đầu cho mọi ứng dụng |
| L2 | Mức tiêu chuẩn, bao phủ phần lớn ứng dụng thực tế | Mục tiêu phù hợp với đa số ứng dụng, đặc biệt khi xử lý dữ liệu nhạy cảm |
| L3 | Mức assurance cao, bổ sung các kiểm soát chuyên sâu và defense-in-depth | Ứng dụng quan trọng, dữ liệu có giá trị cao hoặc yêu cầu tin cậy cao |

Mỗi yêu cầu V11 có mức áp dụng riêng. Ví dụ, chỉ dùng cipher/mode được chấp thuận thuộc L1; quản lý inventory khóa thuộc L2; discovery mật mã và một số kiểm soát constant-time thuộc L3.

Không nên chọn level chỉ dựa trên tên ngành. Tổ chức cần đánh giá độ nhạy của dữ liệu, tác động khi mất bí mật/toàn vẹn/khả dụng, đối tượng tấn công, yêu cầu hợp đồng và khả năng assurance. Có thể ưu tiên một yêu cầu L3 sớm hơn nếu threat model yêu cầu.

## 4. Phạm vi của V11 Cryptography

Mục tiêu của V11 là bảo đảm ứng dụng sử dụng mật mã đúng cách, có khả năng thích nghi với thay đổi và có hệ thống quản lý khóa an toàn. Chương này bao gồm:

- Inventory và tài liệu hóa tài sản mật mã.
- Implementation mật mã đã được kiểm chứng và crypto agility.
- Thuật toán mã hóa và bảo vệ tính toàn vẹn.
- Hashing, HMAC và key derivation.
- Sinh giá trị ngẫu nhiên bằng CSPRNG.
- Tạo khóa công khai, chữ ký số và trao đổi khóa.
- Bảo vệ dữ liệu khi đang được xử lý.

V11 không bao quát mọi vấn đề có sử dụng mật mã. ASVS đặt bảo mật truyền thông/TLS trong chương V12 Secure Communication; các yêu cầu giải quyết bài toán riêng như secrets management cũng được đặt ở phần khác của tiêu chuẩn. Vì vậy, khi đánh giá TLS endpoint hoặc secret distribution, cần tham chiếu thêm chương phù hợp thay vì ép mọi kiểm soát vào V11.

## 5. Bản đồ toàn bộ yêu cầu V11

Bảng sau tóm tắt 24 yêu cầu của chương V11 trong ASVS 5.0.0. Mức L1/L2/L3 là mức yêu cầu được gán trong tiêu chuẩn; phần mô tả bên dưới diễn giải mục tiêu để hỗ trợ thiết kế và kiểm thử.

| Mã yêu cầu | Level | Chủ đề cần xác minh |
|---|---:|---|
| 11.1.1 | L2 | Có chính sách quản lý khóa và vòng đời khóa theo chuẩn phù hợp; tránh chia sẻ khóa quá rộng |
| 11.1.2 | L2 | Có inventory cập nhật cho key, algorithm và certificate; ghi rõ phạm vi sử dụng và loại dữ liệu |
| 11.1.3 | L3 | Có cơ chế discovery để tìm mọi nơi sử dụng encryption, hashing và signing |
| 11.1.4 | L3 | Inventory có kế hoạch chuyển đổi sang chuẩn mật mã mới, bao gồm PQC |
| 11.2.1 | L2 | Dùng implementation mật mã đã được kiểm chứng, gồm thư viện và phần cứng tăng tốc |
| 11.2.2 | L2 | Thiết kế crypto agility để thay thuật toán, tham số, key và tái mã hóa dữ liệu |
| 11.2.3 | L2 | Primitive đạt tối thiểu 128-bit security strength theo algorithm, key size và cấu hình |
| 11.2.4 | L3 | Operation mật mã có đặc tính constant-time, tránh nhánh so sánh/tính toán rò rỉ |
| 11.2.5 | L3 | Module mật mã fail securely và xử lý lỗi không tạo oracle hoặc lỗ hổng tương tự |
| 11.3.1 | L1 | Không dùng block mode không an toàn như ECB hoặc padding yếu như PKCS#1 v1.5 trong ngữ cảnh bị cấm |
| 11.3.2 | L1 | Chỉ dùng cipher và mode được chấp thuận, ví dụ AES-GCM |
| 11.3.3 | L2 | Ciphertext được bảo vệ khỏi sửa đổi trái phép bằng AEAD hoặc encryption kết hợp MAC phù hợp |
| 11.3.4 | L3 | Nonce/IV và giá trị dùng một lần không bị tái sử dụng sai; cách sinh phù hợp với thuật toán |
| 11.3.5 | L3 | Nếu kết hợp encryption với MAC, phải dùng encrypt-then-MAC |
| 11.4.1 | L1 | Chỉ dùng hash function được chấp thuận; không dùng MD5 cho mục đích mật mã |
| 11.4.2 | L2 | Lưu password bằng password hashing/KDF đủ tốn kém với tham số theo hướng dẫn hiện hành |
| 11.4.3 | L2 | Hash cho signature, authentication và integrity đạt yêu cầu collision/second-preimage resistance và output length |
| 11.4.4 | L2 | Dùng KDF được chấp thuận và key stretching khi dẫn xuất key từ password |
| 11.5.1 | L2 | Giá trị không thể đoán được được sinh bằng CSPRNG với ít nhất 128 bit entropy |
| 11.5.2 | L3 | Cơ chế random hoạt động an toàn ngay cả khi có nhu cầu lớn |
| 11.6.1 | L2 | Dùng thuật toán được chấp thuận cho key generation/seeding và tạo/xác minh chữ ký số |
| 11.6.2 | L3 | Dùng thuật toán trao đổi khóa được chấp thuận với tham số an toàn |
| 11.7.1 | L3 | Bảo vệ dữ liệu nhạy cảm khi đang sử dụng, gồm full memory encryption theo yêu cầu |
| 11.7.2 | L3 | Giảm thiểu dữ liệu lộ trong xử lý và mã hóa lại ngay sau khi sử dụng hoặc sớm nhất có thể |

## 6. V11.1 — Cryptographic Inventory and Documentation

V11.1 yêu cầu tổ chức biết mình đang dùng mật mã ở đâu, tài sản nào phụ thuộc vào nó và ai chịu trách nhiệm. Không thể quản lý vòng đời khóa nếu không biết key nào tồn tại, đang bảo vệ dữ liệu gì và thành phần nào có quyền sử dụng.

### 11.1.1 — Chính sách quản lý khóa và vòng đời

Ứng dụng cần có chính sách quản lý khóa và vòng đời khóa dựa trên một chuẩn quản lý khóa phù hợp, ví dụ NIST SP 800-57. Chính sách cần mô tả các giai đoạn tạo, cấp phát, lưu trữ, sử dụng, rotation, thu hồi, backup, recovery và destruction.

ASVS nhấn mạnh không chia sẻ key quá rộng. Ví dụ được nêu trong yêu cầu là shared secret không nên được chia sẻ cho hơn hai entity, còn private key không nên được chia sẻ cho hơn một entity. Đây là nguyên tắc giới hạn chủ thể có khả năng tạo MAC/chữ ký hoặc sử dụng bí mật; tổ chức vẫn cần định nghĩa rõ entity, service identity, custody và trường hợp ngoại lệ trong kiến trúc thực tế.

Bằng chứng có thể gồm key management policy, key owner register, access policy, KMS/HSM configuration, rotation record, revocation procedure và approval record.

### 11.1.2 — Cryptographic inventory

Inventory phải bao gồm tất cả key, algorithm và certificate được ứng dụng sử dụng. Với từng tài sản, cần ghi:

- ID, version, loại key và thuật toán.
- Owner, purpose, environment, tenant và mức độ nhạy cảm.
- Nơi key được phép và không được phép sử dụng.
- Loại dữ liệu mà key được phép bảo vệ.
- KMS/HSM/provider, policy và principal được cấp quyền.
- Ngày tạo, cryptoperiod, trạng thái và lịch rotation.
- Consumer, backup, archive và dependency.
- Kế hoạch retirement, recovery và destruction.

Inventory không chỉ là danh sách tên key. Nó phải mô tả ranh giới sử dụng để ngăn một key được dùng sai purpose, chẳng hạn dùng HMAC key làm encryption key hoặc dùng signing key cho một dịch vụ khác.

### 11.1.3 — Cryptographic discovery

Ở L3, tổ chức cần cơ chế discovery để nhận diện mọi vị trí có encryption, hashing hoặc signing. Inventory thủ công có thể bỏ sót code cũ, thư viện nhúng, job batch, microservice, script triển khai, thiết bị hoặc hệ thống bên thứ ba.

Discovery có thể kết hợp:

- Quét source code và dependency để tìm API mật mã.
- Phân tích cấu hình provider, certificate và key store.
- Kiểm tra KMS/HSM audit log và key usage.
- Quan sát runtime telemetry và service dependency.
- Quét artifact, container image và configuration để phát hiện hard-coded secret/key.
- Đối chiếu kết quả discovery với inventory đã được owner xác nhận.

Không nên kết luận rằng không có sử dụng mật mã chỉ vì một lần tìm kiếm source code không thấy lời gọi trực tiếp. Thư viện hoặc service bên ngoài có thể thực hiện operation thay ứng dụng.

### 11.1.4 — Kế hoạch migration sang chuẩn mới và PQC

Ở L3, inventory cần đi cùng kế hoạch chuyển đổi sang chuẩn mật mã mới, bao gồm Post-Quantum Cryptography (PQC). Kế hoạch cần xác định thuật toán đang dùng, dependency, dữ liệu có vòng đời dài, certificate/trust chain và khả năng thay thế key/algorithm.

Kế hoạch PQC không đồng nghĩa phải bật một thuật toán thử nghiệm ngay lập tức. Cần theo dõi chuẩn được phê duyệt, implementation đã được kiểm chứng, khả năng tương tác và yêu cầu của giao thức. Crypto agility ở V11.2.2 là nền tảng để có thể thực hiện migration khi chuẩn mới sẵn sàng.

## 7. V11.2 — Secure Cryptography Implementation

V11.2 tập trung vào chất lượng implementation và khả năng thay đổi mật mã khi threat landscape thay đổi.

### 11.2.1 — Implementation đã được kiểm chứng

Operation mật mã phải dùng implementation được kiểm chứng trong ngành, bao gồm thư viện và implementation tăng tốc bằng phần cứng. Tránh tự viết cipher, hash, MAC, random generator hoặc protocol cryptography.

Trong Java, nên dùng API JCA/JCE cùng provider phù hợp, được duy trì và đánh giá. Nếu dùng HSM/KMS provider, cần xác minh provider thực sự chuyển operation tới thiết bị/dịch vụ đúng cách, thay vì vô tình export key hoặc fallback sang software provider ngoài policy.

Bằng chứng gồm dependency inventory, provider configuration, vendor validation/certification khi áp dụng, version, security advisory review và test vector.

### 11.2.2 — Crypto agility

Crypto agility là khả năng thay đổi thuật toán, key length, rounds, cipher, mode, random generator, authenticated encryption, MAC hoặc hash mà không phải viết lại toàn bộ hệ thống.

Ứng dụng cũng cần hỗ trợ thay key/password và re-encrypt dữ liệu. Nếu thuật toán bị suy yếu hoặc chuẩn mới được yêu cầu, tổ chức phải có thể migrate mà không mất khả năng đọc dữ liệu lịch sử.

Thiết kế hỗ trợ crypto agility thường có:

- Metadata version cho ciphertext và key.
- Algorithm identifier được kiểm soát bằng allowlist.
- Key ID/version tách khỏi code.
- Provider abstraction và configuration được quản lý.
- Quy trình dual-read/controlled-write trong thời gian migration.
- Test fixture cho định dạng cũ và mới.
- Công cụ rewrap/re-encrypt có checkpoint và khả năng phục hồi.

Crypto agility không có nghĩa client được tự chọn thuật toán tùy ý. Server phải quyết định thuật toán được chấp thuận và từ chối downgrade hoặc algorithm identifier không hợp lệ.

### 11.2.3 — Tối thiểu 128-bit security strength

ASVS yêu cầu primitive đạt tối thiểu 128 bit security strength dựa trên thuật toán, key size và cấu hình. Không được nhầm **128-bit security strength** với việc mọi key đều phải dài đúng 128 bit.

Ví dụ được ASVS nêu:

- ECC key 256 bit cung cấp xấp xỉ 128 bit security strength.
- RSA cần key 3072 bit để đạt xấp xỉ 128 bit security strength.

Độ mạnh thực tế còn phụ thuộc tham số, cách sinh key, implementation và thuật toán cụ thể. Hãy dùng bảng khuyến nghị trong Appendix C của đúng phiên bản ASVS và tiêu chuẩn mật mã có thẩm quyền; không tự suy ra security strength chỉ từ số bit ghi trong tên thuật toán.

### 11.2.4 — Constant-time cryptographic operations

Ở L3, operation mật mã cần tránh timing behavior phụ thuộc dữ liệu bí mật. Các phép so sánh, tính toán hoặc nhánh trả về không nên dừng sớm khi gặp byte khác đầu tiên nếu thời gian thực thi có thể làm lộ thông tin.

Ví dụ thường gặp là so sánh MAC/tag bằng phép so sánh constant-time phù hợp thay vì so sánh chuỗi thông thường. Tuy nhiên, constant-time không chỉ là đổi một hàm so sánh; cần dùng implementation mật mã đã được kiểm chứng và đánh giá toàn bộ đường xử lý có thể rò rỉ qua timing.

### 11.2.5 — Fail securely

Module mật mã phải thất bại an toàn. Lỗi không được tạo ra oracle hoặc tiết lộ thông tin giúp attacker suy ra plaintext, padding, key validity hay trạng thái nội bộ.

Ví dụ:

- Không phân biệt quá chi tiết lỗi padding và lỗi MAC ra phía client.
- Không trả plaintext trước khi authentication tag được xác minh.
- Không bỏ qua lỗi xác minh chữ ký hoặc MAC.
- Không tự fallback sang thuật toán yếu khi provider không hỗ trợ thuật toán mới.
- Không log key bytes, password, plaintext hoặc secret khi operation thất bại.

Với authenticated encryption như AES-GCM, chỉ sử dụng plaintext sau khi xác minh tag thành công. Với legacy encryption không có authentication, cần có cơ chế integrity riêng và kế hoạch migration.

## 8. V11.3 — Encryption Algorithms

V11.3 yêu cầu thuật toán và cách sử dụng encryption bảo vệ cả tính bí mật lẫn tính toàn vẹn.

### 11.3.1 — Không dùng mode hoặc padding yếu

Không dùng block mode không an toàn như ECB cho dữ liệu cần bảo mật. ECB mã hóa các block giống nhau thành ciphertext block giống nhau, làm lộ cấu trúc plaintext.

ASVS cũng nêu padding yếu như PKCS#1 v1.5 trong nhóm cần tránh. Cần phân biệt padding của RSA encryption với padding của các giao thức/chữ ký khác; chọn scheme hiện đại theo use case và chuẩn được chấp thuận.

### 11.3.2 — Chỉ dùng cipher và mode được chấp thuận

Chỉ dùng cipher/mode nằm trong danh sách được chấp thuận theo chuẩn áp dụng. ASVS nêu AES-GCM như ví dụ về mode được chấp thuận.

Không chọn thuật toán chỉ vì provider hỗ trợ. Khả năng gọi API thành công không chứng minh thuật toán phù hợp. Cần kiểm tra Appendix C, security policy của tổ chức và khả năng của provider/HSM.

### 11.3.3 — Bảo vệ ciphertext khỏi sửa đổi

Encryption không tự động bảo đảm tính toàn vẹn. Ciphertext cần được bảo vệ khỏi sửa đổi trái phép, ưu tiên authenticated encryption (AEAD) hoặc kết hợp encryption với MAC được chấp thuận.

AEAD như AES-GCM cung cấp confidentiality và integrity/authenticity của ciphertext cùng associated data. AAD không bị mã hóa nhưng được xác thực, phù hợp để ràng buộc tenant ID, record ID hoặc format metadata nếu các giá trị đó được chuẩn hóa và xác minh đúng.

Nếu dùng encryption và MAC riêng, phải xác định rõ cách kết hợp theo yêu cầu 11.3.5. Không tự thiết kế protocol ghép cipher và MAC.

### 11.3.4 — Nonce, IV và giá trị dùng một lần

Nonce/IV phải được tạo theo yêu cầu của thuật toán và không bị tái sử dụng sai với cùng key. Với AES-GCM, tái sử dụng nonce dưới cùng key có thể phá vỡ tính bí mật và tính toàn vẹn.

Test cần xác minh:

- Cách tạo nonce/IV phù hợp với mode.
- Không tái sử dụng nonce theo phạm vi key và dữ liệu.
- Có kiểm soát counter/uniqueness hoặc xác suất va chạm theo giới hạn thuật toán.
- Rotation key không làm reset nonce state theo cách gây reuse với cùng key material.
- Metadata lưu đủ nonce/IV để decrypt.

Không coi việc gọi SecureRandom mỗi lần là bằng chứng đầy đủ về uniqueness ở mọi quy mô. Cần đánh giá volume, nonce size, key lifetime và cách quản lý trạng thái theo đúng yêu cầu của mode.

### 11.3.5 — Encrypt-then-MAC

Nếu hệ thống kết hợp encryption algorithm với MAC algorithm riêng, ASVS yêu cầu sử dụng encrypt-then-MAC. MAC phải xác thực ciphertext và metadata liên quan theo thiết kế đã được đánh giá, trước khi ứng dụng tin hoặc giải mã dữ liệu.

Nếu dùng AEAD đã được chấp thuận, không cần tự thêm một MAC riêng trừ khi protocol có yêu cầu được thiết kế rõ ràng. Tránh các tổ hợp tự chế như MAC-then-encrypt hoặc encrypt-and-MAC nếu không được chuẩn hóa.

## 9. V11.4 — Hashing and Hash-based Functions

Hash được dùng trong chữ ký số, HMAC, KDF, random bit generation và password storage. Hash nhanh không tự động phù hợp cho password storage; password cần KDF chuyên dụng có chi phí tính toán/bộ nhớ.

### 11.4.1 — Hash function được chấp thuận

Chỉ dùng hash function được chấp thuận cho mục đích mật mã. ASVS nêu rõ MD5 không được dùng cho bất kỳ mục đích mật mã nào, kể cả khi code chỉ dùng nó để tạo checksum nhưng checksum đó được dùng như bằng chứng integrity hoặc security.

Phân biệt hash mật mã với checksum phi mật mã dùng để phát hiện lỗi truyền tải. Nếu cần chống attacker sửa dữ liệu, checksum thông thường không đủ.

### 11.4.2 — Password hashing/KDF đủ tốn kém

Password phải được lưu bằng password hashing function/KDF được chấp thuận và cấu hình theo hướng dẫn hiện hành. Mục tiêu là làm cho mỗi lần đoán password của attacker tốn tài nguyên đáng kể, trong khi đăng nhập hợp lệ vẫn đáp ứng hiệu năng.

Các scheme thường được cân nhắc gồm Argon2id, scrypt, bcrypt hoặc PBKDF2 tùy chuẩn, thư viện và yêu cầu tương thích. Cần lưu algorithm, salt và tham số để có thể xác minh và nâng cấp verifier sau này.

Không dùng SHA-256/SHA-512 trực tiếp làm password hashing function. Salt cần riêng cho mỗi password record; pepper nếu dùng là bí mật bổ sung được lưu tách khỏi database.

### 11.4.3 — Collision resistance và output length

Hash dùng trong digital signature, authentication hoặc integrity cần collision resistance phù hợp. ASVS quy định:

- Nếu use case cần collision resistance, output length ít nhất 256 bit.
- Nếu chỉ cần second-preimage resistance, output length ít nhất 128 bit.

Không chọn output length chỉ vì nhỏ hơn giúp lưu trữ tiết kiệm. Cần xác định threat model và thuộc tính cần bảo vệ. Với chữ ký số, lựa chọn hash phải tương thích với signature scheme và chuẩn áp dụng.

### 11.4.4 — KDF và key stretching

Khi dẫn xuất secret key từ password, dùng KDF được chấp thuận và tham số key stretching phù hợp. Password thường có entropy thấp hơn key ngẫu nhiên; KDF làm chậm quá trình thử đoán.

KDF parameters cần được benchmark trên môi trường thực tế, có versioning và giới hạn đầu vào. Không để metadata do attacker kiểm soát buộc server chạy KDF với memory/time cost cực lớn gây denial of service.

## 10. V11.5 — Random Values

Key, nonce, salt, token và các giá trị không thể đoán cần nguồn ngẫu nhiên mật mã phù hợp.

### 11.5.1 — CSPRNG và entropy tối thiểu

Giá trị ngẫu nhiên cần được sinh bằng cryptographically secure pseudo-random number generator (CSPRNG) và có ít nhất 128 bit entropy nếu mục tiêu là không thể đoán. ASVS lưu ý UUID không đáp ứng điều kiện này.

Trong Java, SecureRandom là API chuẩn để lấy dữ liệu ngẫu nhiên mật mã:

~~~java
import java.security.SecureRandom;

public final class KeyMaterialGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static byte[] generateAes256KeyMaterial() {
        byte[] keyMaterial = new byte[32];
        RANDOM.nextBytes(keyMaterial);
        return keyMaterial;
    }
}
~~~

Ví dụ chỉ minh họa CSPRNG và 32 byte key material. Trong production, nên để KMS/HSM tạo và giữ key nếu kiến trúc yêu cầu key không exportable; không cần đưa raw key bytes vào heap ứng dụng chỉ để đáp ứng ví dụ.

Không dùng Math.random(), timestamp, counter, username, UUID hoặc giá trị tự tạo làm nguồn key material. Cũng không tự seed SecureRandom bằng timestamp hoặc dữ liệu có thể đoán.

### 11.5.2 — Hoạt động an toàn dưới tải cao

Ở L3, cơ chế random phải duy trì an toàn khi tải lớn. Cần kiểm tra cách provider lấy entropy, cách hệ thống xử lý concurrency, khởi động đồng thời, container clone/snapshot và các failure mode của entropy source.

Không tự triển khai PRNG hoặc cache random bytes kéo dài mà không đánh giá. Cần dùng provider và nền tảng được kiểm chứng, quan sát lỗi entropy và kiểm thử dưới tải thực tế.

## 11. V11.6 — Public Key Cryptography

V11.6 đề cập key generation, chữ ký số và key exchange trong các use case không phải TLS. ASVS chỉ rõ yêu cầu TLS nằm trong chương Secure Communication.

### 11.6.1 — Key generation và digital signature

Chỉ dùng thuật toán và mode được chấp thuận cho key generation, seeding và tạo/xác minh chữ ký số. Key generation phải tránh tạo key yếu có thể bị tấn công đã biết, ví dụ RSA key có prime factors quá gần nhau khiến dễ bị factorization.

Bằng chứng có thể gồm:

- Thuật toán, key size và parameter profile.
- Provider/KMS/HSM được dùng để tạo key.
- Kiểm tra public key và key pair consistency.
- Signature test vectors và negative tests.
- Policy cấm export private key nếu không cần.
- Quyền ký tách khỏi quyền xác minh khi dùng asymmetric cryptography.

Với chữ ký số bất đối xứng, private key chỉ được giữ bởi signer được ủy quyền; verifier có thể dùng public key. Với HMAC, bên có shared secret cũng có khả năng tạo MAC, nên không thể coi HMAC verification là xác minh công khai.

### 11.6.2 — Key exchange

Key exchange như Diffie-Hellman hoặc ECDH cần thuật toán được chấp thuận và tham số an toàn. Cần xác minh group/curve, key size, public key validation, transcript binding và cách dẫn xuất session key.

Mục tiêu là ngăn adversary-in-the-middle, key substitution và các lỗi thiết lập khóa. Không tự chọn group hoặc tham số yếu chỉ vì client cũ yêu cầu tương thích.

Yêu cầu 11.6.2 trong V11 dành cho key exchange ngoài TLS; TLS protocol, cipher suite và certificate validation được đánh giá thêm theo V12 Secure Communication.

## 12. V11.7 — In-Use Data Cryptography

V11.7 quan tâm dữ liệu nhạy cảm khi đang nằm trong bộ nhớ hoặc đang được xử lý. Encryption at rest và encryption in transit không tự bảo vệ dữ liệu sau khi ứng dụng đã giải mã để sử dụng.

### 11.7.1 — Full memory encryption

Ở L3, ASVS yêu cầu xác minh có full memory encryption bảo vệ dữ liệu nhạy cảm khi đang sử dụng, nhằm giảm khả năng người hoặc process không được phép đọc dữ liệu trong bộ nhớ.

Tùy nền tảng, kiểm soát này có thể liên quan tới memory encryption của CPU/hardware, confidential computing hoặc cơ chế bảo vệ bộ nhớ tương ứng. Cần xác minh phạm vi bảo vệ, threat model và giới hạn của công nghệ; memory encryption không tự ngăn một process hợp lệ nhưng bị chiếm quyền đọc dữ liệu mà process được phép truy cập.

### 11.7.2 — Data minimization và mã hóa sau khi sử dụng

Chỉ đưa dữ liệu nhạy cảm vào bộ nhớ khi cần thiết, giới hạn số bản sao và thời gian tồn tại. Mã hóa dữ liệu ngay sau khi sử dụng hoặc sớm nhất có thể theo kiến trúc.

Các biện pháp hỗ trợ:

- Không giữ plaintext lâu hơn thời gian xử lý cần thiết.
- Hạn chế heap dump, core dump và diagnostic snapshot.
- Không log secret, private key, DEK hoặc plaintext.
- Xóa/clear buffer khi phù hợp với runtime và giới hạn thực tế của garbage collector.
- Tách process và workload theo quyền tối thiểu.
- Tránh nhân bản dữ liệu nhạy cảm qua cache, queue hoặc tracing.

Việc clear một byte array trong Java giúp giảm thời gian giữ bản sao có thể kiểm soát, nhưng không chứng minh mọi bản sao trong heap/provider đã được zeroize. Cần đánh giá toàn bộ runtime và nơi key material được xử lý.

## 13. Mapping V11 sang key management lifecycle

V11 bao phủ các khía cạnh khác nhau của key management. Bảng dưới đây liên kết yêu cầu với các hoạt động trong vòng đời khóa:

| Hoạt động key management | ASVS V11 liên quan | Bằng chứng điển hình |
|---|---|---|
| Governance và policy | 11.1.1 | Key management policy, lifecycle standard, owner và approval |
| Inventory và discovery | 11.1.2, 11.1.3 | Key inventory, certificate inventory, discovery scan và owner review |
| Crypto agility/PQC planning | 11.1.4, 11.2.2 | Migration roadmap, algorithm registry, versioned ciphertext format |
| Key generation | 11.2.1, 11.2.3, 11.5.1, 11.5.2, 11.6.1 | Provider evidence, CSPRNG, key size/profile và key generation test |
| Key storage và access | 11.1.1, 11.1.2, 11.2.1 | KMS/HSM policy, IAM/grant, non-exportable setting và access audit |
| Encryption/decryption | 11.2.1, 11.2.3, 11.3.1–11.3.5 | Cipher/mode configuration, AEAD tests, nonce controls và error handling |
| Hashing, MAC và password KDF | 11.2.4, 11.2.5, 11.4.1–11.4.4 | Algorithm allowlist, KDF parameters, constant-time compare và negative tests |
| Signing và key exchange | 11.2.1–11.2.5, 11.6.1, 11.6.2 | Key pair profile, signature test, key exchange parameter review |
| Rotation và migration | 11.1.1, 11.1.4, 11.2.2 | Rotation records, old-key decrypt tests, rewrap/re-encrypt evidence |
| Backup và recovery | 11.1.1, 11.2.2, 11.2.5 | Backup/restore test, key recovery evidence và failure-safe behavior |
| Retire, revoke và destroy | 11.1.1, 11.1.2, 11.2.2 | Dependency review, revocation record, destruction evidence |
| Runtime protection | 11.2.4, 11.2.5, 11.7.1, 11.7.2 | Constant-time review, fail-secure tests, memory protection và data minimization |

Mapping này giúp xây dựng chương trình assurance; không có nghĩa một yêu cầu ASVS đơn lẻ chứng minh toàn bộ hoạt động lifecycle đã an toàn.

## 14. ASVS và NIST SP 800-57

ASVS 5.0.0 V11.1.1 yêu cầu chính sách quản lý khóa và lifecycle dựa trên chuẩn như NIST SP 800-57. NIST SP 800-57 cung cấp hướng dẫn chuyên sâu hơn về quản lý keying material, bao gồm:

- Loại khóa và purpose.
- Key lifecycle và cryptoperiod.
- Bảo vệ, phân phối, backup và recovery.
- Compromise, revocation, archival và destruction.
- Quản trị và trách nhiệm đối với key.

ASVS xác định yêu cầu cần được xác minh trong ứng dụng; NIST SP 800-57 giúp thiết kế chính sách và quy trình quản lý khóa sâu hơn. Không nên xem việc có một tài liệu NIST là bằng chứng ứng dụng đã thực thi đúng; cần đối chiếu policy với cấu hình, code, operation và audit thực tế.

## 15. ASVS và KMS/HSM

ASVS không yêu cầu mọi ứng dụng bắt buộc dùng một nhà cung cấp KMS hoặc HSM cụ thể. KMS/HSM có thể là một phần của giải pháp để đáp ứng các mục tiêu như bảo vệ key material, kiểm soát operation, audit và phân tách quyền.

Khi dùng KMS/HSM, cần xác minh:

- Key được tạo và lưu ở đâu; có exportable không.
- Provider/implementation được đánh giá và cấu hình đúng không.
- Key policy, IAM policy và grant giới hạn principal/action/resource/context ra sao.
- Rotation có giữ khả năng decrypt dữ liệu lịch sử không.
- Audit log ghi nhận operation và thay đổi policy đầy đủ không.
- Backup/replica/recovery có thể hoạt động khi KMS/HSM hoặc region gặp sự cố không.
- Ứng dụng có fallback sang software key hoặc provider yếu hơn khi KMS lỗi không.

Non-exportable key không tự động chứng minh hệ thống an toàn. Principal có quyền decrypt hoặc sign vẫn có thể lạm dụng operation qua API nếu authorization và context không được giới hạn.

## 16. Xây dựng evidence cho đánh giá ASVS

Mỗi yêu cầu cần có tiêu chí pass/fail và bằng chứng phù hợp. Không phải yêu cầu nào cũng có thể chứng minh chỉ bằng penetration test; policy, inventory và architecture thường cần document review hoặc source/configuration review.

| Loại bằng chứng | Ví dụ |
|---|---|
| Policy/document | Key management policy, crypto standard, owner matrix, PQC migration plan |
| Inventory | Key ID/version, algorithm, certificate, purpose, data scope, dependency |
| Source/configuration | JCA/JCE usage, provider config, cipher transformation, algorithm allowlist |
| KMS/HSM evidence | Key attributes, policy, grants, rotation state, audit events |
| Automated test | Known-answer tests, nonce uniqueness tests, AEAD tampering, signature tests |
| Integration test | Old-key decryption, KMS authorization, backup restore, provider compatibility |
| Runtime evidence | Crypto discovery, operation telemetry, alert, memory protection settings |
| Review/approval | Exception, change record, risk acceptance, remediation deadline |

Evidence cần có nguồn, thời gian, phiên bản ứng dụng/provider và phạm vi đánh giá. Screenshot đơn lẻ hoặc một dòng cấu hình không đủ nếu không thể chứng minh cấu hình đang có hiệu lực trong production.

## 17. Thiết kế test plan theo yêu cầu

Một test plan cho V11 có thể được tổ chức theo nhóm:

1. **Inventory tests:** đối chiếu key, certificate và algorithm trong inventory với discovery/runtime evidence.
2. **Implementation tests:** xác nhận thư viện/provider đã được phê duyệt và version còn được hỗ trợ.
3. **Strength tests:** kiểm tra algorithm, key size, mode và parameter theo Appendix C.
4. **Encryption tests:** positive decrypt, wrong key, tampered ciphertext, wrong AAD và nonce policy.
5. **Hash/KDF tests:** algorithm allowlist, password hashing parameters, KDF output và timing-safe comparison.
6. **Randomness tests:** kiểm tra nguồn CSPRNG, entropy assumptions, concurrency và startup behavior.
7. **Public-key tests:** key generation, signature verification, key exchange parameter và invalid public key.
8. **Failure tests:** provider unavailable, key disabled, malformed ciphertext, authentication failure và permission denied.
9. **Lifecycle tests:** rotation, old-key decryption, rewrap/re-encrypt, backup restore và destruction guard.
10. **Runtime tests:** memory protection, data minimization và kiểm soát plaintext/secret trong log hoặc dump.

Mỗi test case nên gắn requirement ID theo phiên bản, môi trường, precondition, expected result, actual result và evidence reference.

## 18. Ví dụ test cho yêu cầu encryption và fail-secure

Với một service dùng AES-GCM, test suite có thể kiểm tra:

| Test | Input/điều kiện | Kết quả mong đợi | V11 liên quan |
|---|---|---|---|
| Valid decrypt | Ciphertext, key, nonce và AAD đúng | Plaintext đúng sau khi tag xác minh | 11.3.2, 11.3.3 |
| Tampered ciphertext | Thay một byte ciphertext | Decrypt thất bại, không trả plaintext | 11.2.5, 11.3.3 |
| Wrong AAD | Dùng context khác | Authentication failure | 11.3.3 |
| Nonce reuse control | Tạo nhiều message cùng key | Không tái sử dụng nonce theo policy | 11.3.4 |
| Invalid key state | Key disabled/revoked | Operation bị từ chối | 11.1.1, 11.2.5 |
| Provider unavailable | Provider/KMS không khả dụng | Fail closed; không fallback ngoài policy | 11.2.1, 11.2.5 |
| Legacy fixture | Ciphertext trước rotation | Giải mã đúng bằng old key path | 11.1.1, 11.2.2 |

Kết quả test không được ghi plaintext, raw key, nonce state bí mật hoặc key bytes vào log. Chỉ lưu fixture ID, key ID/version, test ID, result và correlation reference.

## 19. Đánh giá password hashing theo V11.4

V11.4.2 và V11.4.4 thường bị nhầm với việc chỉ dùng một hash function mạnh. Đối với password, mục tiêu là làm cho mỗi lần đoán mật khẩu tốn tài nguyên.

Một bài đánh giá nên kiểm tra:

- Có dùng password hashing/KDF được chấp thuận không.
- Salt có ngẫu nhiên và riêng cho mỗi password record không.
- Parameters có được benchmark và cập nhật theo policy không.
- Verifier có lưu algorithm/parameter version để nâng cấp không.
- Có rate limit và MFA hỗ trợ chống tấn công online không.
- Secret bổ sung như pepper có được giữ ngoài database không.
- Không có plaintext password hoặc raw pepper trong log, dump hay source.

ASVS V11.4 không có nghĩa mọi ứng dụng phải dùng cùng một iteration count hoặc memory cost. Tham số cần theo hướng dẫn hiện hành, threat model và năng lực hệ thống; không dùng con số cố định trong tài liệu mẫu làm chuẩn bất biến.

## 20. Crypto agility và kiểm soát thay đổi

Crypto agility cần được thể hiện trong kiến trúc và kiểm thử:

- Ciphertext envelope lưu format version và algorithm identifier.
- Key inventory liên kết key với purpose và data class.
- Ứng dụng có thể đọc format cũ trong giai đoạn migration.
- Writer có thể chuyển sang thuật toán/key version mới theo policy.
- Có công cụ rewrap/re-encrypt, checkpoint và integrity verification.
- Có kế hoạch retire thuật toán/key cũ và kiểm tra backup/archive.
- Có test cross-version và khả năng phục hồi sau migration lỗi.

Không nên cho phép algorithm negotiation không giới hạn. Crypto agility cần có allowlist và policy trung tâm; nếu attacker có thể ép ứng dụng chọn cipher yếu, khả năng đổi thuật toán trở thành downgrade vulnerability.

## 21. Những nhầm lẫn thường gặp khi áp dụng ASVS

- **Dùng mã V6 của ASVS 4.0.3 cho ASVS 5.0.0:** V11 mới là chương Cryptography của 5.0.0.
- **Cho rằng V11 là toàn bộ key management standard:** V11.1.1 tham chiếu chuẩn quản lý khóa như NIST SP 800-57; quy trình chi tiết cần được xây dựng thêm.
- **Đánh đồng key length với security strength:** cần xét thuật toán và tham số, không chỉ số bit của key.
- **Cho rằng encryption tự bảo vệ integrity:** cần AEAD hoặc encryption kết hợp MAC đúng cách.
- **Dùng hash nhanh cho password:** password cần KDF/password hashing function có chi phí phù hợp.
- **Cho rằng UUID là đủ entropy:** ASVS 11.5.1 nêu UUID không đáp ứng điều kiện CSPRNG với 128-bit entropy.
- **Coi KMS/HSM là bằng chứng tự động đạt chuẩn:** vẫn phải đánh giá policy, principal, operation, audit và application integration.
- **Chỉ chạy black-box test:** inventory, policy, crypto agility và nhiều yêu cầu L2/L3 cần tài liệu, source hoặc cấu hình.
- **Gộp TLS vào V11.6.2:** V11.6.2 áp dụng key exchange ngoài TLS; TLS nằm ở V12.
- **Coi test pass là bằng chứng đủ để destroy key cũ:** cần inventory và dependency evidence, backup/restore cùng retention review.
- **Dùng master branch thay stable release làm baseline mà không ghi rõ:** requirement IDs và nội dung có thể thay đổi.

## 22. Quy trình assessment ASVS V11

Một assessment thực tế có thể đi theo trình tự:

1. Chọn phiên bản ASVS cố định, ghi rõ level mục tiêu và phạm vi ứng dụng.
2. Liệt kê data classification, trust boundary và use case mật mã.
3. Thu thập key/certificate/algorithm inventory và discovery result.
4. Đối chiếu key management policy với NIST SP 800-57 hoặc chuẩn được chọn.
5. Review provider, algorithm, mode, key size, random source và KDF parameters.
6. Kiểm tra KMS/HSM policy, access control, rotation, backup và recovery.
7. Chạy test positive/negative cho encryption, MAC, hashing, signature và key exchange.
8. Kiểm tra fail-secure, constant-time và xử lý lỗi theo level yêu cầu.
9. Đánh giá crypto agility, old-key decryption và migration/PQC plan.
10. Ghi pass/fail, evidence, gap, risk owner và remediation deadline cho từng requirement.

Một requirement chỉ được đánh dấu pass khi có bằng chứng cho đúng phạm vi và đúng điều kiện. Nếu requirement không áp dụng, cần ghi rõ lý do và người phê duyệt; không tự bỏ qua vì chưa có test.

## 23. Ví dụ bảng đánh giá

| Requirement | Kết quả | Bằng chứng cần có | Ví dụ gap |
|---|---|---|---|
| v5.0.0-11.1.1 | Pass/Fail | Key policy, lifecycle, access scope và review | Không có owner hoặc không có quy trình compromise |
| v5.0.0-11.1.2 | Pass/Fail | Inventory đầy đủ key, algorithm, certificate và purpose | Key trong batch job không có trong inventory |
| v5.0.0-11.2.1 | Pass/Fail | Provider/library version và validation evidence | Tự viết primitive hoặc dùng library không được duy trì |
| v5.0.0-11.2.2 | Pass/Fail | Algorithm/key migration design và cross-version tests | Ciphertext không có format version |
| v5.0.0-11.3.3 | Pass/Fail | AEAD/MAC design và tampering tests | Dữ liệu mã hóa nhưng không có integrity protection |
| v5.0.0-11.5.1 | Pass/Fail | CSPRNG source, entropy design và code/config review | Dùng UUID hoặc timestamp làm key material |
| v5.0.0-11.6.1 | Pass/Fail | Key generation profile và signature tests | RSA key generation không theo profile an toàn |
| v5.0.0-11.7.2 | Pass/Fail | Data flow, memory handling và log review | Plaintext/secret tồn tại lâu hoặc xuất hiện trong log |

Bảng này là mẫu tổ chức evidence, không phải kết quả đánh giá của một ứng dụng cụ thể. Mỗi requirement cần được kiểm tra theo đúng wording và level trong bản ASVS đã chọn.

## 24. Tài liệu tham chiếu và cách giữ nội dung cập nhật

Khi cần tra cứu chi tiết, dùng nguồn chính thức và giữ version trong hồ sơ:

- OWASP ASVS 5.0.0 — trang dự án và tải bản stable: https://asvs.owasp.org/
- ASVS 5.0.0 — chương V11 Cryptography: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x20-V11-Cryptography.md
- ASVS 5.0.0 — cách sử dụng, levels và cách tham chiếu requirement: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x03-What-is-the-ASVS.md
- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- OWASP Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

Nếu ASVS phát hành phiên bản mới, hãy đối chiếu requirement mapping và nội dung thay đổi trước khi cập nhật checklist hoặc báo cáo. Không âm thầm thay số hiệu trong hồ sơ cũ vì điều đó có thể làm mất khả năng truy vết.

## 25. Checklist áp dụng ASVS cryptography requirements

- [ ] Ghi rõ ASVS version và verification level mục tiêu.
- [ ] Dùng requirement ID có version, ví dụ v5.0.0-11.1.1.
- [ ] Có key management policy và lifecycle dựa trên chuẩn phù hợp.
- [ ] Inventory gồm key, algorithm, certificate, purpose, owner và dependency.
- [ ] Có discovery cho encryption, hashing và signing.
- [ ] Có crypto agility và migration plan, bao gồm PQC readiness.
- [ ] Dùng implementation mật mã đã được kiểm chứng.
- [ ] Security strength đạt tối thiểu 128 bit theo algorithm và configuration.
- [ ] Không dùng mode/padding yếu; cipher/mode được allowlist.
- [ ] Ciphertext có integrity protection và nonce/IV được quản lý đúng.
- [ ] Hash, password KDF và key derivation đáp ứng yêu cầu.
- [ ] Non-guessable values được tạo bằng CSPRNG với entropy phù hợp.
- [ ] Key generation, signature và key exchange dùng algorithm/parameters được chấp thuận.
- [ ] Crypto operation constant-time và module fail securely theo level.
- [ ] Có kiểm soát dữ liệu trong memory và data minimization khi xử lý.
- [ ] Có test old-key decryption, backup restore, rotation và migration.
- [ ] Có audit evidence, owner, gap và remediation deadline cho từng requirement.
- [ ] TLS và secrets management được đánh giá thêm ở phần ASVS tương ứng.

ASVS V11 biến các nguyên tắc mật mã thành yêu cầu có thể xác minh: biết và quản lý mọi tài sản mật mã, dùng implementation và primitive được chấp thuận, bảo vệ ciphertext, sinh randomness an toàn, quản lý password/key derivation, dùng public-key cryptography đúng cách và giảm phơi lộ dữ liệu khi xử lý. Khi gắn từng requirement với policy, inventory, cấu hình, test và audit evidence, tổ chức có thể đánh giá mức assurance một cách nhất quán và duy trì khả năng thay đổi thuật toán/key khi tiêu chuẩn hoặc threat landscape thay đổi.
