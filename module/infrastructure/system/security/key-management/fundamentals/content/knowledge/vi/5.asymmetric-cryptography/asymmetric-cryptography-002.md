# RSA

> **Chương:** Mật mã bất đối xứng  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. RSA là gì?

**RSA** là một họ thuật toán **mật mã khóa công khai (public-key cryptography)** dựa trên các phép toán số học modulo với số nguyên rất lớn. Tên RSA ghép từ họ của ba tác giả Rivest, Shamir và Adleman. Một thực thể sở hữu **cặp khóa**:

- **Public key (khóa công khai):** có thể phân phối cho những bên cần mã hóa dữ liệu gửi đến chủ khóa hoặc cần xác minh chữ ký của chủ khóa.
- **Private key (khóa riêng):** phải được giữ bí mật, dùng để giải mã trong lược đồ mã hóa RSA phù hợp hoặc tạo chữ ký trong lược đồ ký RSA phù hợp.

RSA có hai nhóm ứng dụng cần phân biệt rõ:

1. **Mã hóa khóa/bí mật nhỏ:** bên gửi dùng **public key của bên nhận** và lược đồ **RSA-OAEP** để bảo vệ một khóa đối xứng hoặc vật liệu bí mật có kích thước phù hợp; bên nhận dùng private key tương ứng để khôi phục.
2. **Chữ ký số:** bên ký dùng **private key** và lược đồ **RSA-PSS** để ký thông điệp; người xác minh dùng **public key** đã được xác thực nguồn gốc để kiểm tra.

**Không dùng “RSA thuần” (textbook RSA) trực tiếp trên dữ liệu.** Phép lũy thừa modulo là thành phần toán học, còn RSA-OAEP và RSA-PSS là các lược đồ đầy đủ với quy tắc đệm, băm và kiểm tra an toàn. Việc lựa chọn lược đồ, tham số, nguồn sinh số ngẫu nhiên và bảo vệ private key quyết định tính an toàn của ứng dụng.

Đối với module **quản lý khóa mật mã**, học RSA không chỉ là hiểu cách mã hóa và ký: quan trọng hơn là **ai tạo cặp khóa, public key có gắn đúng danh tính không, private key đặt ở đâu, quyền sử dụng được kiểm soát thế nào, khi nào xoay vòng và xử lý dữ liệu hoặc chữ ký cũ ra sao**.

## 2. Nguyên lý khóa công khai của RSA

Ở mức khái niệm, quy trình tạo khóa RSA chọn hai số nguyên tố lớn `p`, `q`, tạo modulus `n = p × q`, sau đó chọn số mũ công khai `e` và tìm số mũ riêng `d` thỏa điều kiện toán học để thực hiện các phép biến đổi ngược nhau. Một lựa chọn phổ biến cho `e` là `65537`; thư viện mật mã có trách nhiệm chọn số nguyên tố, kiểm tra điều kiện hợp lệ và tạo khóa.

~~~text
Public key:  (n, e)
Private key: d và những tham số bí mật hỗ trợ tính toán

Phép biến đổi RSA nguyên thủy (chỉ minh họa toán học):
    y = x^e mod n
    x = y^d mod n

Ứng dụng thực tế:
    Mã hóa: RSA-OAEP, không tự dùng x^e mod n trên plaintext
    Ký số:  RSASSA-PSS, không tự ký bằng phép m^d mod n
~~~

Điểm cốt lõi là **biết public key không được phép dẫn tới khả năng thực tế suy ra private key** trong giả định an toàn và kích thước khóa phù hợp. Tuy vậy, việc RSA dùng hai số nguyên tố **không có nghĩa lập trình viên cần tự tìm nguyên tố hay cài đặt phép toán RSA**. Luôn sử dụng thư viện được duy trì, cơ chế sinh khóa an toàn hoặc KMS/HSM.

### Độ dài khóa RSA có ý nghĩa gì?

Độ dài RSA thường được nói theo số bit của **modulus `n`**, không phải kích thước plaintext có thể mã hóa và cũng không phải độ dài khóa AES tương đương.

| Độ dài modulus | Cách hiểu trong thiết kế |
| --- | --- |
| **1024 bit** | Không phù hợp cho hệ thống mới cần bảo mật hiện đại. |
| **2048 bit** | Mốc tối thiểu còn gặp trong nhiều hệ thống truyền thống; phải đối chiếu yêu cầu an toàn và chính sách áp dụng. |
| **3072 bit** | Tham chiếu thường gặp khi hướng tới mức an toàn cổ điển xấp xỉ **128 bit**, với chi phí tính toán lớn hơn 2048 bit. |
| **4096 bit** | Modulus lớn hơn nhưng tăng chi phí tạo khóa, ký/giải mã và kích thước chữ ký; không mặc nhiên là lựa chọn tốt nhất cho mọi ứng dụng. |

**Không thể so sánh trực tiếp** “RSA-256” với “AES-256” theo độ dài bit; hai họ thuật toán có cấu trúc và mức an toàn khác nhau. Hơn nữa, RSA thông thường **không kháng được máy tính lượng tử đủ mạnh**; nếu hệ thống có yêu cầu bảo mật dài hạn trước rủi ro lượng tử, cần đánh giá thêm các cơ chế hậu lượng tử/hybrid phù hợp chính sách.

## 3. RSA dùng để mã hóa: RSA-OAEP

RSA-OAEP (**Optimal Asymmetric Encryption Padding**) là lược đồ mã hóa RSA hiện đại, bổ sung cơ chế encoding ngẫu nhiên và kiểm tra cấu trúc để tránh các điểm yếu của phép RSA nguyên thủy. Với hệ thống mới cần mã hóa bằng RSA, OAEP với bộ tham số băm phù hợp thường là lựa chọn được ưu tiên so với lược đồ mã hóa RSA PKCS#1 v1.5 cũ.

~~~mermaid
sequenceDiagram
    participant S as Bên gửi
    participant R as Bên nhận
    S->>S: Xác thực public key của R
    S->>S: Sinh DEK đối xứng bằng CSPRNG
    S->>S: RSA-OAEP mã hóa DEK bằng public key của R
    S->>S: AES-GCM mã hóa dữ liệu bằng DEK
    S->>R: Wrapped DEK + ciphertext + nonce/tag + metadata
    R->>R: RSA-OAEP giải mã DEK bằng private key
    R->>R: AES-GCM giải mã dữ liệu và xác minh tag
~~~

Sơ đồ cho thấy RSA thường **bảo vệ khóa đối xứng**, còn dữ liệu lớn do AES-GCM hoặc một AEAD đối xứng phù hợp xử lý. Cách kết hợp này được gọi là **hybrid encryption**; khi phân tầng DEK/KEK và cơ chế lưu trữ khóa, nó có thể được tổ chức theo mô hình **envelope encryption**.

### 3.1. Vì sao không dùng RSA để mã hóa cả file?

RSA-OAEP chỉ mã hóa được một thông điệp nhỏ hơn modulus sau khi trừ phần dành cho encoding và hàm băm:

\[
mLen \leq k - 2hLen - 2
\]

Trong đó `k` là độ dài modulus tính theo **byte**, `hLen` là độ dài output của hash OAEP theo byte. Ví dụ, **RSA-2048** có `k = 256` byte; nếu OAEP dùng **SHA-256** với `hLen = 32`, thông điệp tối đa là **190 byte**. Không thể đưa trực tiếp một file vài MB vào một lần RSA-OAEP.

Ngoài giới hạn dung lượng, các phép toán private-key RSA đắt hơn mã hóa đối xứng. Thiết kế thực tế thường:

1. Sinh DEK 256 bit dùng AES-GCM hoặc ChaCha20-Poly1305.
2. Mã hóa dữ liệu bằng DEK và một nonce hợp lệ.
3. Dùng RSA-OAEP bọc DEK cho bên nhận, hoặc dùng dịch vụ KMS để bọc DEK theo chính sách.
4. Lưu/gửi ciphertext, nonce, authentication tag, wrapped DEK, key ID và thông tin định dạng.

**Lưu ý:** chỉ dùng public key để mã hóa **không xác minh được danh tính người gửi**. Bất kỳ ai sở hữu public key có thể tạo ciphertext gửi đến bên nhận. Nếu cần xác thực người gửi, phải bổ sung cơ chế xác thực/chữ ký/giao thức phù hợp; không suy ra điều đó từ RSA-OAEP.

### 3.2. Khai báo đúng tham số OAEP

OAEP có các tham số gồm **hàm băm chính, MGF (Mask Generation Function), hàm băm của MGF1 và label**. Khi dùng Java, không nên cho rằng tên `OAEPWithSHA-256AndMGF1Padding` tự bảo đảm mọi provider chọn hàm băm MGF1 là SHA-256. Nếu cần tính tương thích và định dạng cố định, hãy **truyền rõ `OAEPParameterSpec`** và kiểm thử cả bên mã hóa lẫn bên giải mã.

Không tùy ý đổi từ SHA-256 sang SHA-1, đổi MGF1 digest hoặc thay label giữa hai phía. Sai khác tham số khiến giải mã thất bại; các cấu hình yếu hoặc không đúng chuẩn có thể làm suy giảm bảo đảm an toàn.

## 4. RSA dùng để ký số: RSA-PSS

**RSA-PSS (RSASSA-PSS)** là lược đồ chữ ký số dùng RSA và cơ chế padding có ngẫu nhiên. Bên ký dùng **private key**; bên nhận xác minh bằng **public key** tương ứng:

~~~text
signature = RSASSA-PSS-Sign(privateKey, message)

valid = RSASSA-PSS-Verify(publicKey, message, signature)
~~~

Trong thực tế, lược đồ sử dụng hàm băm mật mã và encoding đặc thù; thư viện tự xử lý các bước này. **Không tự lấy hash rồi gọi RSA raw** vì dễ tạo lỗ hổng chữ ký và làm sai giao thức.

Chữ ký số nhằm cung cấp:

- **Tính toàn vẹn:** thay đổi nội dung thông điệp sau khi ký làm xác minh thất bại với giả định an toàn phù hợp.
- **Tính xác thực nguồn ký:** nếu public key được gắn đáng tin cậy với chủ thể, chữ ký hợp lệ cho thấy thực thể kiểm soát private key đã ký dữ liệu tương ứng.
- **Bằng chứng phục vụ truy vết:** có thể lưu chữ ký, certificate chain, timestamp và nhật ký ký để hỗ trợ kiểm toán, nhưng hiệu lực pháp lý và khả năng chứng minh lịch sử còn phụ thuộc chính sách và hệ thống chứng cứ.

**Chữ ký số không mã hóa thông điệp.** Người kiểm tra chữ ký vẫn có thể đọc nội dung nếu thông điệp không được mã hóa riêng.

### RSA-PSS so với RSA PKCS#1 v1.5 signature

RSA PKCS#1 v1.5 **cho chữ ký** vẫn tồn tại trong nhiều giao thức và hệ thống tương thích. RSA-PSS là lựa chọn hiện đại thường được ưu tiên cho thiết kế ký mới khi nền tảng hỗ trợ. Không được nhầm **PKCS#1 v1.5 encryption** với **PKCS#1 v1.5 signature**: chúng là hai lược đồ khác nhau và có mô hình rủi ro riêng.

Trong PSS, các tham số quan trọng gồm **hash**, **MGF1 hash**, **salt length** và **trailer field**. Hai phía phải thống nhất đúng bộ tham số và định dạng thông điệp trước ký (ví dụ canonical JSON hoặc encoding nhị phân có độ dài trường rõ ràng).

Nếu dùng chung một public key mà không xác minh nguồn gốc, kẻ tấn công có thể thay public key bằng khóa của họ rồi đưa chữ ký hợp lệ theo khóa giả. Vì vậy, **phân phối và xác thực public key** cũng là một phần không thể thiếu của key management.

## 5. Public key đáng tin cậy bằng cách nào? Chứng thư số và PKI

Public key **không bí mật**, nhưng **phải xác thực đúng chủ thể** trong các tình huống cần chống mạo danh.

**Public Key Infrastructure (PKI)** thường sử dụng **chứng thư số X.509** do một tổ chức phát hành chứng thư (CA) ký để gắn danh tính, public key, phạm vi sử dụng và thời hạn chứng thư vào một cấu trúc có thể xác minh.

~~~mermaid
flowchart LR
    Root[CA gốc đáng tin cậy] -->|Ký chứng thư| Intermediate[CA trung gian]
    Intermediate -->|Ký chứng thư| Cert[Chứng thư dịch vụ]
    Cert --> Pub[Public key của dịch vụ]
    Pub --> Verify[Xác minh chữ ký / xác thực đối tác]
    Policy[Hostname, thời hạn, key usage, thu hồi, chính sách] --> Verify
~~~

Khi kiểm tra chứng thư hoặc chữ ký, hệ thống cần xét **chuỗi tin cậy, tên/danh tính đối tượng, thời hạn, mục đích được phép dùng khóa (key usage), thuật toán, trạng thái thu hồi khi áp dụng và chính sách của ứng dụng**. Chỉ kiểm tra chữ ký toán học với một public key chưa rõ nguồn gốc **không chứng minh** danh tính bên gửi.

**Ví dụ TLS 1.3:** server có thể dùng private key RSA phù hợp để **ký xác thực một phần handshake** theo lược đồ được giao thức hỗ trợ; các khóa lưu lượng đối xứng được dẫn xuất qua key schedule (thường có đóng góp từ (EC)DHE). **TLS 1.3 không dùng RSA key transport kiểu RSA key exchange của TLS 1.2 cũ.** Do đó, “chứng thư TLS có khóa RSA” không có nghĩa dữ liệu HTTPS được mã hóa trực tiếp bằng RSA.

**Chữ ký số dài hạn:** khi xác minh hồ sơ đã ký từ nhiều năm trước, không được coi thời hạn chứng thư hiện tại là điều kiện duy nhất. Có thể cần bằng chứng **thời điểm ký đáng tin cậy**, trạng thái chứng thư tại thời điểm tương ứng, dấu thời gian và chính sách xác minh lịch sử.

## 6. Quản lý vòng đời cặp khóa RSA

Một cặp khóa RSA có thể tồn tại qua nhiều phiên TLS, nhiều lần ký hoặc nhiều đợt mã hóa. Vì vậy, quản lý vòng đời cần cụ thể hơn “sinh một cặp khóa rồi lưu PEM”.

| Giai đoạn | Việc cần làm | Rủi ro nếu làm sai |
| --- | --- | --- |
| **Lập chính sách** | Xác định mục đích `ENCRYPT/DECRYPT` hay `SIGN/VERIFY`, chủ sở hữu, mức bảo mật, cryptoperiod, cách phục hồi | Dùng chung khóa nhiều mục đích, không rõ trách nhiệm |
| **Generation** | Sinh cặp khóa bằng thư viện tin cậy/CSPRNG hoặc trong HSM/KMS, với modulus và tham số phù hợp | Số nguyên tố yếu, entropy thấp, khóa dễ bị suy ra |
| **Provisioning** | Cấp quyền dùng private key cho đúng workload; công bố public key/chứng thư qua kênh tin cậy | Lộ private key hoặc bị thay public key |
| **Storage** | Giữ private key trong KMS/HSM/keystore được bảo vệ; hạn chế xuất khóa, backup có kiểm soát | Private key bị lộ qua source, file, image, backup, log |
| **Use** | Phân quyền `Sign` hoặc `Decrypt`, theo dõi key ID, danh tính gọi, kết quả và hạn mức | Lạm dụng ký, giải mã dữ liệu không được phép |
| **Rotation** | Tạo cặp mới, chuyển thao tác mới sang khóa mới, duy trì xử lý dữ liệu/chữ ký cũ khi cần | Không đọc được ciphertext cũ, đứt gãy xác minh |
| **Retire / revoke** | Ngừng ký/mã hóa mới bằng khóa cũ, thu hồi chứng thư/quyền khi cần | Khóa cũ vẫn được tin cậy hoặc tiếp tục dùng |
| **Destroy** | Hủy vật liệu private key khi không còn phụ thuộc và đã hoàn thành yêu cầu lưu giữ | Mất khả năng giải mã hoặc không thể hoàn tất nghĩa vụ lưu trữ |

### 6.1. Tách khóa theo mục đích

Một hệ thống nên cân nhắc dùng **hai cặp khóa RSA riêng** cho **ký số** và **giải mã/unwrap**, thay vì dùng cùng một private key cho mọi tác vụ. Phân tách giúp giới hạn quyền và ngăn việc một luồng nghiệp vụ có quyền ký lại có thể giải mã dữ liệu.

**Private key không nên xuất khỏi HSM/KMS** khi cơ chế và yêu cầu vận hành cho phép. Một dịch vụ cần ký có thể gọi API `Sign` mà không nhận byte private key. Với RSA-OAEP, dịch vụ có thể gọi `Decrypt/Unwrap` theo quyền, còn quyền thay policy và xóa khóa do vai trò khác quản lý.

### 6.2. Rotation phải xét dữ liệu cũ

Giả sử RSA key pair `rsa-wrap-v1` dùng để bọc DEK trong ba tháng. Khi chuyển sang `rsa-wrap-v2`:

1. Dữ liệu và DEK mới được bọc dưới public key `v2`.
2. Wrapped DEK cũ vẫn đòi hỏi khả năng dùng private key `v1`, trừ khi đã được rewrap.
3. Hệ thống cần lưu **key ID, key version, thuật toán OAEP và tham số** để mở bọc đúng.
4. Chỉ ngừng quyền giải mã hoặc hủy `v1` khi đã kiểm tra backup, snapshot và dữ liệu chưa chuyển đổi.

Với khóa **ký số**, ngừng ký bằng private key cũ không có nghĩa xóa public key/chứng thư liên quan: hồ sơ cũ có thể vẫn cần xác minh trong thời gian lưu giữ.

### 6.3. Nếu private key bị lộ

**Không chờ đến lịch rotation.** Cần cô lập danh tính bị chiếm, ngừng sử dụng key sai mục đích, đánh giá nhật ký KMS/HSM, tạo khóa thay thế và chuyển quyền tin cậy:

- **Private key ký bị lộ:** cần xử lý khả năng chữ ký giả, thu hồi chứng thư hoặc trust binding theo cơ chế đang dùng, cập nhật public key tin cậy và điều tra các chữ ký trong khoảng bị ảnh hưởng.
- **Private key giải mã/unwrap bị lộ:** bên tấn công có thể giải mã wrapped DEK mà họ đã thu thập, kể cả từ trước khi rotation. Chỉ rewrap dữ liệu hiện tại **không xóa được các bản sao wrapped DEK đã lộ**; cần đánh giá DEK, ciphertext, phạm vi dữ liệu và cân nhắc thay DEK/mã hóa lại.

Với RSA-OAEP, không coi rotation là cách biến thông tin đã bị lộ thành bí mật trở lại. Một khi attacker có private key và đã lưu các ciphertext được tạo cho public key đó, việc sửa cấu hình hiện tại không khiến bản ghi đã bị thu thập mất khả năng giải mã.

## 7. RSA trong KMS, HSM và envelope encryption

**KMS** cung cấp lớp quản lý danh tính, chính sách quyền, key lifecycle và API thao tác mật mã. **HSM** cung cấp ranh giới phần cứng chuyên dụng để giữ và sử dụng khóa nhạy cảm theo năng lực thiết bị. Một KMS có thể sử dụng HSM ở phía sau nhưng **không phải mọi thuật toán hoặc chế độ RSA đều có mặt trên mọi KMS/HSM**.

Thiết kế tham khảo:

~~~mermaid
flowchart TD
    Owner[Nhóm quản lý khóa] -->|Policy, rotation, audit| KMS[KMS / HSM]
    App[Ứng dụng] -->|Encrypt bằng DEK| Store[(Ciphertext + tag + nonce)]
    App -->|Wrap DEK bằng RSA-OAEP hoặc API KMS| Wrapped[Wrapped DEK]
    Wrapped --> Store
    KMS -->|Giữ private key RSA không xuất| RSA[Khóa giải mã RSA]
    App -->|Yêu cầu unwrap được cấp quyền| KMS
    App -->|Sign theo quyền nghiệp vụ| KMS
    KMS -->|Giữ private key ký riêng| Sign[Khóa RSA-PSS]
    Audit[Hệ thống kiểm toán] <-->|Sự kiện key usage & policy| KMS
~~~

Trong mô hình này, **RSA là một cách bọc DEK**, không phải yêu cầu bắt buộc cho mọi envelope encryption. Nhiều KMS dùng khóa đối xứng KEK để bọc DEK. Lựa chọn giữa RSA-OAEP và AES key wrap/AEAD phù hợp phụ thuộc yêu cầu **bên nhận, khả năng phân phối public key, chính sách truy cập, hiệu năng và năng lực KMS**.

Đối với dữ liệu nhiều tenant:

- Phân quyền ứng dụng quyết định **người dùng nào được xem bản ghi**.
- IAM/KMS policy quyết định **workload nào được ký hoặc giải mã DEK**.
- Metadata được bảo vệ theo giao thức giúp xác định đúng **tenant, key ID, algorithm, version và AAD**.
- Audit ghi được danh tính gọi, loại thao tác, khóa và kết quả; **không ghi private key, DEK hay plaintext**.

Được KMS cho phép `Decrypt` không đồng nghĩa với việc mọi người dùng của ứng dụng được xem mọi dữ liệu.

## 8. Ví dụ Java 17: RSA-OAEP và RSA-PSS

Ví dụ sau minh họa **hai cặp khóa riêng**: một cặp để bọc/khôi phục DEK AES-256 bằng RSA-OAEP, một cặp để ký/xác minh bằng RSA-PSS. Đây là **ví dụ cục bộ** phục vụ học API, chưa bao gồm lưu khóa an toàn, PKI, IAM, KMS hoặc khả năng khôi phục sau sự cố.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.spec.MGF1ParameterSpec;
import java.security.spec.PSSParameterSpec;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;

public class RsaKeyManagementDemo {
    private static final OAEPParameterSpec OAEP_SHA256 =
            new OAEPParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    PSource.PSpecified.DEFAULT);

    private static final PSSParameterSpec PSS_SHA256 =
            new PSSParameterSpec(
                    "SHA-256", "MGF1", MGF1ParameterSpec.SHA256,
                    32, PSSParameterSpec.TRAILER_FIELD_BC);

    static KeyPair newRsaKeyPair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072); // Demo: modulus 3072 bit.
        return generator.generateKeyPair();
    }

    public static void main(String[] args) throws Exception {
        // Hai key pair phục vụ mục đích khác nhau.
        KeyPair wrappingKey = newRsaKeyPair();
        KeyPair signingKey = newRsaKeyPair();

        KeyGenerator aes = KeyGenerator.getInstance("AES");
        aes.init(256);
        SecretKey dek = aes.generateKey();

        // Bọc DEK bằng public key; dùng rõ OAEP SHA-256 / MGF1 SHA-256.
        Cipher wrap = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        wrap.init(Cipher.ENCRYPT_MODE, wrappingKey.getPublic(), OAEP_SHA256);
        byte[] wrappedDek = wrap.doFinal(dek.getEncoded());

        // Chỉ chủ thể có private key và quyền phù hợp mới mở bọc được.
        Cipher unwrap = Cipher.getInstance(
                "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
        unwrap.init(Cipher.DECRYPT_MODE, wrappingKey.getPrivate(), OAEP_SHA256);
        byte[] restoredDek = unwrap.doFinal(wrappedDek);
        if (!MessageDigest.isEqual(dek.getEncoded(), restoredDek)) {
            throw new IllegalStateException("DEK mismatch");
        }

        byte[] message = "Don hang: 123|amount=500"
                .getBytes(StandardCharsets.UTF_8);

        // Tạo chữ ký bằng private key chỉ dành cho ký số.
        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(PSS_SHA256);
        signer.initSign(signingKey.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        // Bên kiểm tra cần public key thật, đã xác thực nguồn gốc.
        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(PSS_SHA256);
        verifier.initVerify(signingKey.getPublic());
        verifier.update(message);
        if (!verifier.verify(signature)) {
            throw new IllegalStateException("Invalid signature");
        }

        // Đổi thông điệp sau ký: xác minh phải thất bại.
        verifier.initVerify(signingKey.getPublic());
        verifier.update("Don hang: 123|amount=900"
                .getBytes(StandardCharsets.UTF_8));
        if (verifier.verify(signature)) {
            throw new AssertionError("Tampered message accepted");
        }
        System.out.println("RSA-OAEP and RSA-PSS: OK");
    }
}
~~~

### Những điểm bắt buộc khi đưa ví dụ vào hệ thống thật

1. **Không tự giữ private key dài hạn trong mã nguồn hay file cấu hình.** KMS/HSM hoặc keystore được bảo vệ nên quản lý vòng đời và quyền khi phù hợp.
2. **Không coi public key từ request là đáng tin.** Cần cơ chế phân phối tin cậy như PKI, fingerprint được quản lý hoặc trust store phù hợp.
3. **Bọc khóa nhỏ, mã hóa dữ liệu lớn bằng AEAD.** Mẫu này bọc DEK, chưa thể hiện bước AES-GCM mã hóa payload và quản lý nonce/tag.
4. **Truyền đúng tham số OAEP/PSS ở mọi thành phần.** Khác nhau ở hash, MGF1 hash, PSS salt length hoặc định dạng message sẽ gây lỗi tương thích.
5. **Xử lý lỗi giải mã/ký theo chính sách.** Không trả chi tiết lỗi có thể tạo oracle, không thử giải mã bằng lược đồ yếu như cơ chế fallback không được phê duyệt.
6. **Định dạng thông điệp trước khi ký phải ổn định.** Với JSON, định nghĩa canonicalization/encoding rõ ràng, tránh ký chuỗi tùy tiện rồi xác minh trên chuỗi được serialize khác.
7. **Lưu key ID, phiên bản và algorithm parameters** cạnh wrapped DEK hoặc chữ ký để hỗ trợ rotation và xác minh lịch sử.
8. **Giới hạn và audit thao tác private key** như `Sign` và `Decrypt` theo workload, tenant, hạn mức và rủi ro.

## 9. Rủi ro và sai lầm thường gặp

| Sai lầm | Hậu quả | Biện pháp phù hợp |
| --- | --- | --- |
| Dùng textbook RSA, tự padding hoặc tự xử lý byte | Có thể mất tính an toàn của mã hóa và chữ ký | Dùng RSA-OAEP/RSA-PSS qua thư viện chuẩn |
| Dùng RSA để mã hóa cả payload lớn | Vượt giới hạn kích thước, tốn tài nguyên | Hybrid/envelope encryption: RSA bảo vệ DEK, AEAD mã hóa dữ liệu |
| Chỉ cần public key có chữ ký hợp lệ là đủ tin danh tính | Có thể xác minh chữ ký của kẻ giả mạo | Xác thực certificate chain/trust binding và danh tính |
| Lưu private key dạng rõ vào Git, image, backup không bảo vệ | Ai đọc được bản sao có thể ký hoặc giải mã | KMS/HSM, least privilege, backup kiểm soát |
| Cùng một private key cho mọi mục đích | Mở rộng phạm vi ảnh hưởng khi bị lộ | Tách khóa ký và khóa unwrap, tách môi trường/tenant khi thích hợp |
| Thay khóa nhưng quên wrapped DEK cũ | Mất khả năng đọc dữ liệu hoặc restore backup | Lưu key ID/version, duy trì quyền cũ có kiểm soát, rewrap |
| Chỉ đổi KEK khi private key cũ bị lộ | Bản sao ciphertext/wrapped DEK cũ có thể vẫn bị giải mã | Đánh giá lộ DEK, re-encrypt khi cần và xử lý sự cố |
| Ký dữ liệu không canonical hoặc thiếu ngữ cảnh | Chữ ký có thể không bao phủ đúng mục đích giao dịch | Định dạng có version, tách domain và ngữ cảnh ký |
| Bỏ qua chứng thư hết hạn/thu hồi khi xác minh | Tin nhầm danh tính hoặc chứng từ không còn hợp lệ | Xây dựng chính sách PKI và xác minh theo thời điểm |
| Dùng RSA 1024 hoặc tham số cũ chỉ vì tương thích | Mức an toàn không đáp ứng yêu cầu hiện nay | Đánh giá độ dài modulus, lược đồ, cryptoperiod, lộ trình nâng cấp |
| Tin rằng chữ ký số mã hóa nội dung | Rò rỉ thông tin rõ trong bản tin đã ký | Mã hóa riêng nếu cần tính bí mật |
| Không kiểm toán thao tác ký/giải mã | Khó phát hiện lạm dụng private key | Phân quyền, log sự kiện và cảnh báo bất thường |

## 10. Tình huống thực tế: ký hóa đơn và bảo vệ dữ liệu

Một dịch vụ phát hành hóa đơn cần **ký hóa đơn điện tử** và **mã hóa dữ liệu khách hàng** khi lưu trữ. Kiến trúc dùng hai cơ chế tách biệt:

- **RSA-PSS signing key:** private key nằm trong HSM/KMS hoặc vùng bảo vệ tương đương; dịch vụ phát hành có quyền gọi `Sign` cho dữ liệu đã được nghiệp vụ phê duyệt. Public key/chứng thư dùng để xác minh chữ ký.
- **DEK đối xứng + KEK:** dữ liệu khách hàng được mã hóa bằng AES-GCM; DEK được bảo vệ bằng KMS hoặc RSA-OAEP theo thiết kế được duyệt.

**Khi phát hành hóa đơn:** ứng dụng kiểm tra quyền người dùng, chuẩn hóa dữ liệu cần ký (mã hóa byte cố định), đưa hash/thông điệp vào quy trình ký theo API, lưu chữ ký cùng key ID, định dạng dữ liệu và chứng cứ cần thiết. Người nhận kiểm tra chữ ký **và** xác thực public key/chứng thư theo chính sách.

**Khi đọc hồ sơ khách hàng:** ứng dụng kiểm tra quyền truy cập bản ghi, mở bọc DEK nếu được phép, xác minh tag AEAD và chỉ đưa plaintext vào luồng nghiệp vụ hợp lệ. Quyền `Sign` không được mặc nhiên cấp quyền `Decrypt`, và ngược lại.

**Khi rotation khóa ký:** dịch vụ bắt đầu ký hóa đơn mới bằng private key mới; public key/chứng thư của phiên bản cũ được giữ để xác minh hồ sơ lịch sử theo thời hạn và chính sách chứng cứ. Nếu private key ký cũ bị lộ, cần đánh giá các chữ ký có nguy cơ giả mạo và kích hoạt quy trình thu hồi/tái phát hành chứng thư khi áp dụng.

**Khi rotation khóa bọc DEK:** dữ liệu mới dùng KEK mới. Đối với wrapped DEK cũ, cần kiểm tra khả năng rewrap và phục hồi backup trước khi vô hiệu hóa private key cũ. Nếu private key bị lộ, phải cân nhắc khả năng attacker đã thu thập wrapped DEK cũ, chứ không chỉ đổi key alias ở ứng dụng.

Tình huống này nhấn mạnh mối liên hệ giữa **mật mã bất đối xứng, chữ ký số, mã hóa đối xứng, KMS/HSM, envelope encryption, phân quyền và kiểm toán** trong một hệ thống thực tế.

## 11. Checklist thiết kế RSA an toàn

- [ ] RSA được dùng cho **OAEP bọc khóa** hay **PSS ký số**, có tách khóa theo mục đích không?
- [ ] Modulus, thuật toán, tham số hash/MGF1/salt và cryptoperiod đáp ứng chính sách áp dụng không?
- [ ] Cặp khóa được sinh bằng CSPRNG hoặc trong KMS/HSM/keystore tin cậy?
- [ ] Private key không xuất hoặc không lưu dưới dạng rõ ngoài khu vực được phê duyệt?
- [ ] Public key/chứng thư có cơ chế xác thực danh tính, chain, thời hạn, key usage và thu hồi không?
- [ ] Dữ liệu lớn dùng AEAD với DEK, thay vì mã hóa trực tiếp bằng RSA?
- [ ] Có key ID/version và metadata thuật toán đủ để mở dữ liệu cũ, xác minh chữ ký lịch sử?
- [ ] IAM/KMS phân tách rõ quyền `Sign`, `Decrypt/Unwrap`, quản trị policy và quyền nghiệp vụ?
- [ ] Rotation có xét backup, wrapped DEK cũ, chứng thư và nhu cầu xác minh lịch sử?
- [ ] Có quy trình xử lý private key bị lộ, điều tra chữ ký bất thường và dữ liệu có thể bị giải mã?
- [ ] Audit theo dõi thao tác nhạy cảm mà không ghi private key, DEK hay plaintext?
- [ ] Có đánh giá yêu cầu dài hạn và lộ trình mật mã hậu lượng tử khi cần?

## 12. Câu hỏi tự kiểm tra

**1. RSA có bắt buộc dùng private key để mã hóa và public key để giải mã không?**  
Không. Trong **RSA-OAEP**, bên gửi dùng **public key của bên nhận để mã hóa**; bên nhận dùng private key để giải mã. Trong **RSA-PSS**, bên ký dùng private key để ký và bên kiểm tra dùng public key để xác minh. Hai quy trình có lược đồ và mục tiêu khác nhau.

**2. Có thể mã hóa trực tiếp một file 10 MB bằng RSA-OAEP không?**  
Không. RSA-OAEP giới hạn kích thước thông điệp theo modulus và hash. Hệ thống nên dùng AEAD để mã hóa file bằng DEK, rồi bọc DEK bằng RSA-OAEP/KMS.

**3. Vì sao xác minh chữ ký thành công chưa đủ kết luận danh tính người ký?**  
Vì xác minh chỉ chứng minh chữ ký tương ứng với một public key. Cần có nguồn tin cậy gắn public key với danh tính và chính sách sử dụng khóa.

**4. RSA-OAEP có thay cho RSA-PSS để ký không?**  
Không. RSA-OAEP là lược đồ mã hóa, RSA-PSS là lược đồ chữ ký số; không được thay thế tùy ý.

**5. Tại sao cần lưu key ID/version khi RSA key pair được xoay vòng?**  
Vì wrapped DEK cũ có thể cần private key phiên bản cũ để giải mã và chữ ký cũ cần public key đúng phiên bản để xác minh.

**6. Chỉ rewrap DEK sau khi private key RSA cũ lộ đã đủ an toàn chưa?**  
Chưa chắc. Nếu attacker đã có private key và wrapped DEK cũ, họ có thể giải mã DEK và bản mã đã thu thập. Phải đánh giá dữ liệu bị ảnh hưởng và cân nhắc thay DEK, mã hóa lại.

**7. TLS 1.3 dùng chứng thư RSA thì dữ liệu HTTPS được mã hóa bằng RSA đúng không?**  
Không. Khóa RSA có thể dùng ký để xác thực handshake; lưu lượng được bảo vệ bằng traffic key đối xứng dẫn xuất từ key schedule TLS.

## Ghi nhớ

**RSA là mật mã khóa công khai với hai ứng dụng cốt lõi: RSA-OAEP để bảo vệ bí mật nhỏ/khóa đối xứng và RSA-PSS để ký số.** Một hệ thống an toàn phải dùng lược đồ và tham số đúng, xác thực public key, bảo vệ private key, phân quyền theo mục đích, quản lý phiên bản và cryptoperiod, xoay vòng/thu hồi có kế hoạch, kiểm toán thao tác và bảo toàn khả năng đọc dữ liệu hoặc xác minh chữ ký cũ. Trong ứng dụng thực tế, RSA thường kết hợp **AEAD đối xứng, KMS/HSM và envelope encryption** thay vì trực tiếp xử lý mọi dữ liệu.
