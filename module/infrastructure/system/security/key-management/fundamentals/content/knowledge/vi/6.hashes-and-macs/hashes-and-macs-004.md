# Hash integrity check: kiểm tra tính toàn vẹn bằng hàm băm

## 1. Hash integrity check giải quyết vấn đề gì?

Một hệ thống phân phối ứng dụng Java cung cấp tệp **billing-service.jar** và công bố giá trị SHA-256 của tệp. Sau khi tải, đội vận hành tính SHA-256 trên dữ liệu nhận được rồi so sánh với giá trị được công bố. Nếu hai giá trị khác nhau, tệp đã khác so với bản dùng để tạo giá trị tham chiếu. Đây là một **hash integrity check**: kiểm tra xem một chuỗi byte có khớp với chuỗi byte đã được băm trước đó hay không.

Tuy nhiên, giả sử kẻ tấn công có thể thay **cả tệp JAR lẫn giá trị SHA-256 đặt bên cạnh tệp**. Người tải tính hash mới và vẫn thấy hai giá trị giống nhau. Hàm băm hoạt động đúng, nhưng hệ thống **chưa xác thực nguồn của giá trị hash tham chiếu**. Một hash không có khóa không tự chứng minh ai đã tạo tệp hoặc ai đã công bố giá trị tham chiếu.

Đây là điểm then chốt trong thiết kế bảo vệ khóa và dữ liệu:

> **Hash có thể xác định nội dung có thay đổi so với một digest tham chiếu hay không; mức độ tin cậy của kết luận phụ thuộc vào việc digest tham chiếu có được bảo vệ và xác thực hay không.**

Trong trường hợp cần phát hiện **sửa đổi có chủ đích của kẻ tấn công**, hệ thống thường dùng **HMAC/MAC** với khóa bí mật, **chữ ký số** với private key hoặc một cơ chế **AEAD** có xác thực, tùy yêu cầu chia sẻ và mô hình đe dọa.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích digest, SHA-256, cách tính và so sánh hash của byte dữ liệu.
2. Phân biệt lỗi truyền tải ngẫu nhiên với sửa đổi do kẻ tấn công có khả năng thay nội dung.
3. Phân biệt **hash thường**, **HMAC**, **chữ ký số** và **AEAD authentication tag**.
4. Thiết kế quy trình lấy digest tham chiếu từ nguồn tin cậy, xác thực manifest và kiểm tra artifact.
5. Thực hiện hash/HMAC trên tệp bằng Java 17 theo cách đọc luồng, không cần nạp toàn bộ tệp vào bộ nhớ.
6. Phân tích vòng đời khóa MAC, chữ ký số, KMS/HSM, rotation, thu hồi và nhật ký kiểm toán.
7. Nhận diện các lỗi phổ biến: hash tự công bố cùng tệp không đáng tin, MD5/SHA-1, dùng sai byte, bỏ qua kiểm tra chữ ký, khóa bí mật bị lộ và replay.

## 2. Hàm băm mật mã và digest

Một **cryptographic hash function** nhận dữ liệu có độ dài bất kỳ và tạo ra một giá trị đầu ra có độ dài cố định, gọi là **digest** hoặc hash value.

~~~text
message bytes  ── SHA-256 ──► digest 256 bit (32 byte)

Ví dụ minh họa:
  Data A  ── SHA-256 ──► H(A)
  Data A' ── SHA-256 ──► H(A')

Nếu A và A' khác nhau, H(A) và H(A') gần như chắc chắn khác nhau.
~~~

Digest SHA-256 thường được biểu diễn dưới dạng **64 ký tự hex**; đó chỉ là cách hiển thị 32 byte. Cùng một nội dung byte luôn tạo cùng digest nếu thuật toán và quy tắc nhập dữ liệu không thay đổi.

### 2.1. Các thuộc tính quan trọng

| Thuộc tính | Ý nghĩa thực hành |
| --- | --- |
| **Deterministic** | Cùng byte đầu vào và cùng thuật toán cho cùng digest |
| **Preimage resistance** | Khó tìm một thông điệp phù hợp với một digest cho trước |
| **Second-preimage resistance** | Khi đã biết thông điệp A, khó tìm A' khác A mà có cùng digest |
| **Collision resistance** | Khó tìm bất kỳ hai thông điệp khác nhau có cùng digest |
| **Avalanche effect** | Một thay đổi nhỏ ở đầu vào thường khiến digest thay đổi đáng kể; đây là đặc tính quan sát, không thay thế chứng minh an toàn |
| **Fixed-length output** | SHA-256 cho digest 256 bit bất kể tệp dài bao nhiêu |

Vì digest có độ dài cố định còn tập đầu vào vô hạn, **collision về mặt toán học chắc chắn tồn tại**. Điều quan trọng là **có khả thi để tìm ra một collision** hay không.

Với SHA-256 và giả định hàm hoạt động như mong đợi về mặt mật mã, tìm collision bằng phương pháp tổng quát thường cần khoảng **2^128** công sức, không phải 2^256; đây là hệ quả của hiệu ứng birthday. Mức an toàn đối với preimage của SHA-256 được kỳ vọng ở mức xấp xỉ 2^256 công sức với mô hình tổng quát phù hợp. Không nên từ độ dài digest mà suy ra mọi thuộc tính có cùng mức an toàn.

### 2.2. Thuật toán nên và không nên dùng

| Thuật toán | Digest | Hướng sử dụng |
| --- | --- | --- |
| **SHA-256** | 256 bit | Lựa chọn phổ biến cho integrity check, manifest, hash artifact |
| **SHA-384 / SHA-512** | 384 / 512 bit | Họ SHA-2; chọn theo tiêu chuẩn, giao thức, nền tảng và yêu cầu |
| **SHA3-256 / SHA3-512** | 256 / 512 bit | Họ SHA-3, cấu trúc khác SHA-2; dùng khi giao thức/chính sách hỗ trợ |
| **BLAKE2/BLAKE3** | Phụ thuộc cấu hình | Có ứng dụng hash hiệu năng cao; chỉ dùng khi hệ sinh thái/chuẩn định dạng được thống nhất |
| **SHA-1** | 160 bit | **Không chọn cho kiểm tra toàn vẹn chống kẻ tấn công mới** vì đã có tấn công collision thực tế |
| **MD5** | 128 bit | **Không dùng cho mục tiêu toàn vẹn mật mã** vì đã bị phá về collision; chỉ có thể gặp ở checksum tương thích cũ không mang yêu cầu chống kẻ tấn công |
| **CRC32/Adler-32** | 32 bit | Checksum phát hiện lỗi ngẫu nhiên; **không phải hash mật mã** |

Không có nghĩa SHA-256 luôn là lựa chọn bắt buộc trong mọi giao thức. Điều cần thiết là **chọn thuật toán được chuẩn hóa và chấp nhận theo chính sách**, đồng thời định nghĩa rõ thuật toán trong metadata/manifest để phía xác minh không thể bị ép dùng thuật toán yếu.

### 2.3. Digest không chứa thông tin về tác giả

Nếu một bên tính:

~~~text
digest = SHA256(fileBytes)
~~~

thì bất kỳ ai có fileBytes cũng có thể tính digest giống hệt. Do đó:

- Hash **không chứng minh** tệp do nhà phát hành hợp lệ tạo ra.
- Hash **không bí mật hóa** nội dung tệp.
- Hash **không chứng minh** tệp còn mới hay không bị phát lại từ một phiên bản cũ.
- Hash **không chặn** kẻ tấn công sửa cả tệp lẫn digest nếu họ kiểm soát nơi lưu cả hai.

Hash chỉ trở thành bằng chứng chống sửa đổi có ý nghĩa khi **digest tham chiếu có nguồn tin cậy độc lập**, hoặc digest nằm trong thông điệp được **MAC/ký số** đúng cách.

## 3. Hash integrity check hoạt động như thế nào?

Quy trình cơ bản:

1. **Nguồn đáng tin** xác định một tệp hoặc thông điệp gốc và tính digest bằng thuật toán đã chọn.
2. Bên nhận lấy **digest tham chiếu đáng tin** theo kênh hoặc cơ chế bảo vệ phù hợp.
3. Bên nhận tính digest từ **đúng chuỗi byte** của tệp đã nhận.
4. Bên nhận so sánh kết quả với digest tham chiếu theo cùng thuật toán và định dạng.
5. Nếu khác, **từ chối** sử dụng tệp; nếu giống, tệp khớp digest tham chiếu trong giới hạn bảo đảm của thuật toán và tính tin cậy nguồn.

~~~mermaid
flowchart TD
    A["Tệp tải xuống"] --> B["Tính SHA-256 trên byte thật"]
    C["Digest tham chiếu từ nguồn được xác thực"] --> D["So sánh digest"]
    B --> D
    D --> E{"Khớp?"}
    E -->|"Không"| F["Từ chối, ghi sự kiện, kiểm tra lại nguồn"]
    E -->|"Có"| G["Tệp khớp bản tham chiếu"]
    G --> H["Tiếp tục kiểm tra phiên bản, chữ ký và quyền dùng theo chính sách"]
~~~

**“Khớp” không tự đồng nghĩa “an toàn để chạy”.** Tệp có thể chứa phần mềm độc hại do chính nguồn phát hành bị xâm nhập tạo ra. Kiểm tra hash là một lớp trong chuỗi xác thực nguồn gốc, chính sách phát hành và quản lý bản vá.

### 3.1. Hai loại rủi ro phải tách biệt

| Tình huống | Hash thường có giúp không? | Kiểm soát bổ sung |
| --- | --- | --- |
| Tệp bị lỗi bit khi truyền hoặc khi lưu | **Có**, nếu digest gốc được lưu đúng | Giám sát, khôi phục từ bản sao đúng |
| Bản tải bị cắt ngắn hoặc ghi không đầy đủ | **Có** | Kiểm tra độ dài và retry an toàn |
| Người dùng tải nhầm phiên bản có digest khác | **Có**, nếu kỳ vọng đúng digest của phiên bản yêu cầu | Kiểm tra version, release channel |
| Kẻ tấn công thay tệp nhưng **không thể sửa digest tham chiếu** | **Có**, nếu SHA-256 vẫn an toàn | Bảo vệ digest và toàn bộ quy trình lấy digest |
| Kẻ tấn công sửa được **cả tệp và digest** trên một máy chủ | **Không đủ** | Chữ ký số hoặc HMAC từ chủ thể tin cậy, được xác minh độc lập |
| Kẻ tấn công phát lại tệp hợp lệ nhưng quá cũ | **Không** | Kiểm tra version, timestamp đáng tin, chính sách chống rollback |
| Kẻ có quyền phát hành ký nhầm một tệp độc hại | Hash/chữ ký có thể vẫn hợp lệ | Kiểm soát quy trình phát hành, review, kiểm tra nguồn và quyền ký |

### 3.2. Tham chiếu tin cậy phải đến từ đâu?

Một số mô hình hợp lệ:

- Digest được nhúng sẵn trong **ứng dụng đã được phân phối và xác thực** hoặc cấu hình có kiểm soát.
- Digest được đưa vào **manifest có chữ ký số** của bên phát hành; client xác minh chữ ký bằng public key đã tin cậy.
- Digest được bảo vệ bằng **HMAC/MAC** với khóa chỉ các thành phần được phép nắm giữ.
- Digest được truyền qua một kênh đã xác thực, có chính sách bảo vệ khỏi bị sửa và kiểm soát nguồn; tùy mô hình đe dọa có thể cần bảo đảm lâu dài bằng chữ ký riêng.

**Trường hợp không đủ:** website chứa file.zip và file.zip.sha256 cùng một thư mục, nhưng kẻ tấn công có quyền ghi vào cả hai. Việc hai tệp khớp nhau chỉ nói rằng **chúng nhất quán**, không nói rằng chúng là bản phát hành đúng.

### 3.3. Thứ tự kiểm tra quan trọng

Với hệ thống phát hành phần mềm, một quy trình hợp lý là:

~~~mermaid
sequenceDiagram
    participant P as Bên phát hành
    participant S as Kho artifact
    participant C as Client / CI/CD
    P->>P: Tính SHA-256 từng artifact
    P->>P: Tạo manifest gồm tên, kích thước, hash, version
    P->>P: Ký manifest bằng signing private key có kiểm soát
    P->>S: Đăng artifact + manifest + chữ ký
    C->>S: Tải artifact, manifest, chữ ký
    S-->>C: Nội dung đã lưu
    C->>C: Xác minh chữ ký với public key tin cậy
    C->>C: Kiểm tra version, artifact ID và chính sách
    C->>C: Tính SHA-256 artifact và so với manifest đã xác thực
    C->>C: Chỉ sử dụng artifact khi toàn bộ điều kiện đạt
~~~

Nếu public key dùng xác minh chữ ký được tải từ chính nguồn **chưa tin cậy** và được chấp nhận tùy ý, kẻ tấn công có thể thay cả khóa lẫn chữ ký. Việc quản lý **trust anchor, key ID, certificate, rotation và revocation** là một phần không thể thiếu của integrity check có bảo vệ chống tấn công.

## 4. Hash thường, HMAC, chữ ký số và AEAD khác nhau ra sao?

Dù tất cả có thể tham gia kiểm tra tính toàn vẹn, chúng có **giả định tin cậy và khả năng xác thực khác nhau**.

| Cơ chế | Dữ liệu bí mật cần giữ | Ai có thể tạo bằng chứng hợp lệ? | Ai có thể xác minh? | Ứng dụng điển hình |
| --- | --- | --- | --- | --- |
| **Hash thường (SHA-256)** | Không có khóa | Bất kỳ ai có dữ liệu | Bất kỳ ai có dữ liệu và digest | Phát hiện lỗi, đối chiếu artifact với digest đáng tin |
| **HMAC-SHA256** | Khóa MAC đối xứng | Ai có khóa MAC | Ai có cùng khóa MAC | Xác thực giữa các dịch vụ có chia sẻ bí mật, webhook |
| **Chữ ký số (Ed25519, RSA-PSS, ECDSA)** | Private signing key | Bên có private key hoặc quyền gọi dịch vụ ký | Bên có public key **đã được xác thực** | Phát hành phần mềm, ký manifest, hồ sơ kiểm toán |
| **AEAD authentication tag (AES-GCM)** | Khóa mã hóa đối xứng | Bên có khóa và quyền mã hóa | Bên có khóa và quyền giải mã | Dữ liệu cần **mã hóa + xác thực**, có thể ràng buộc AAD |

### 4.1. HMAC: xác thực một thông điệp bằng khóa bí mật

**HMAC (Hash-based Message Authentication Code)** kết hợp hàm băm mật mã với khóa bí mật theo cấu trúc chuẩn. Về mặt ý tưởng:

~~~text
tag = HMAC-SHA256(secretMacKey, messageBytes)

Verify:
  candidateTag = HMAC-SHA256(secretMacKey, receivedMessageBytes)
  valid = ConstantTimeEqual(candidateTag, receivedTag)
~~~

Nếu kẻ tấn công có thể sửa thông điệp nhưng **không có khóa MAC**, họ không thể dễ dàng tạo tag hợp lệ cho thông điệp đã sửa, với giả định HMAC và độ dài tag được dùng đúng.

**Điểm khác so với hash thường:** HMAC cung cấp xác thực về **quyền sở hữu bí mật chung**. Nó không chứng minh cá nhân nào trong hai bên chia sẻ khóa đã tạo tag, vì cả hai đều có thể tính tag hợp lệ. Nếu cần một bằng chứng có thể được xác minh công khai mà không trao khóa ký bí mật cho người nhận, chữ ký số thường phù hợp hơn.

Không tự xây MAC bằng cách nối **secret || message** rồi băm SHA-256. Một số cấu trúc tự chế dễ mắc lỗi như **length extension** hoặc thiếu phân tách miền, và không có bảo đảm tương đương HMAC. Hãy dùng API **HmacSHA256** chuẩn.

### 4.2. Chữ ký số: kiểm tra integrity với public key

Bên phát hành có private key để ký digest hoặc thông điệp theo **thuật toán chữ ký số chuẩn**; bên nhận xác minh bằng public key được xác thực. Trong thực tế, API chữ ký có thể băm nội dung ở bên trong hoặc dùng cơ chế ký được đặc tả; **không tự tiền băm rồi ký bừa** nếu API/giao thức không quy định.

~~~text
Bên ký:    Sign(privateKey, signedManifestBytes) -> signature
Bên nhận:  Verify(publicKeyTinCay, signedManifestBytes, signature) -> true/false
           SHA256(downloadedArtifactBytes) == digestTrongManifest
~~~

Hai bước **xác minh chữ ký manifest** và **đối chiếu digest của artifact** giải quyết các điều kiện khác nhau: manifest có thuộc về chủ thể được tin cậy không, và artifact có đúng byte được manifest cam kết không.

Chữ ký số không tự bảo đảm manifest **còn mới** hay mô tả bản phát hành **được cho phép dùng**. Cần kiểm tra version, kênh phân phối, timestamp/expiry có ý nghĩa theo chính sách và chống rollback khi thích hợp.

### 4.3. AEAD và associated data

**AES-GCM** và các cơ chế AEAD tương ứng xác thực ciphertext và **AAD (Additional Authenticated Data)** bằng một authentication tag. AAD có thể dùng để ràng buộc tenant ID, record ID, purpose hoặc phiên bản định dạng mà không mã hóa những trường đó.

Ví dụ hệ thống hóa đơn:

~~~text
Encrypt(DEK, nonce, plaintext, AAD=(tenantId, invoiceId, version))
    -> ciphertext + tag

Decrypt(DEK, nonce, ciphertext, tag, expectedAAD)
    -> plaintext hoặc lỗi xác thực
~~~

Điều này khác với hash tự do đặt bên cạnh ciphertext: bên có DEK và bên giải mã dùng cơ chế xác thực mật mã để kiểm tra nội dung **trong đúng ngữ cảnh**. Tuy nhiên, cần kiểm tra quyền ứng dụng riêng, quản lý **nonce duy nhất dưới cùng khóa AES-GCM**, kiểm soát KEK/DEK và không trả plaintext chưa xác thực.

**Không dùng HMAC đơn giản thay cho AEAD** khi cần giữ bí mật dữ liệu. Có thể thiết kế các lược đồ Encrypt-then-MAC chuẩn, nhưng trong ứng dụng mới nên ưu tiên AEAD được thư viện/hệ sinh thái hỗ trợ phù hợp.

## 5. Thiết kế digest/manifest để kiểm tra đúng dữ liệu

Integrity check thường thất bại không phải vì SHA-256 bị phá, mà vì **bên tạo và bên xác minh không tính hash trên cùng một đối tượng**.

### 5.1. Hash byte, không hash “ý nghĩa văn bản”

Các chuỗi có vẻ giống nhau có thể có byte khác nhau:

- File dùng CRLF so với file dùng LF.
- JSON đổi thứ tự trường hoặc thêm khoảng trắng.
- Chuỗi Unicode có hai cách biểu diễn byte khác nhau.
- Tệp nén được tạo lại với header/timestamp khác dù nội dung giải nén giống nhau.
- Một file bị chuyển đổi encoding khi tải lên hoặc tải xuống.

**Với integrity check artifact, nên băm chính xác byte của tệp phát hành** (không tự đọc thành chuỗi rồi chuyển lại UTF-8). Nếu giao thức yêu cầu hash **dữ liệu logic** thay vì byte file, phải quy định canonicalization rõ ràng và nhất quán.

~~~text
Đúng cho artifact:
  SHA256(raw bytes của file.jar)

Không được mặc định tương đương:
  SHA256(UTF8(readAllLines(file.jar)))
~~~

### 5.2. Metadata nào nên nằm trong manifest?

Ví dụ manifest khái niệm:

~~~json
{
  "schemaVersion": 1,
  "release": "2026.11.28",
  "artifact": "billing-service.jar",
  "sizeBytes": 18432000,
  "hashAlgorithm": "SHA-256",
  "digestHex": "<64 hex characters>",
  "signerKeyId": "release-signing-v4"
}
~~~

Các giá trị chỉ minh họa. Đối tượng được **ký** là byte manifest theo định dạng/chuẩn đã xác định; chữ ký thường được lưu riêng. Trường **signerKeyId** chỉ giúp chọn khóa **trong tập đã tin cậy**, không làm danh tính trở nên đáng tin nếu nguồn khóa được lấy tùy ý từ request.

Một manifest có thể mô tả nhiều tệp. Cần kiểm tra:

- **Tên hoặc artifact ID:** tệp được kiểm tra đúng bản cần dùng.
- **Độ dài và thuật toán:** kiểm tra từ metadata đã được xác thực, tránh bị ép dùng hash yếu.
- **Digest:** phải khớp byte tệp thực tế.
- **Phiên bản và kênh phát hành:** đúng phiên bản tối thiểu hoặc chính sách hệ thống.
- **Chữ ký hoặc MAC:** manifest đến từ nguồn được phép phát hành.
- **Quy tắc đường dẫn:** tránh trích xuất/gói dữ liệu qua các đường dẫn bất thường hoặc path traversal khi tải/gỡ nén.

### 5.3. Không băm một file rồi sau đó mở lại file đã bị thay

Nếu phần mềm kiểm tra hash trên tệp A nhưng sau đó một tiến trình khác thay nội dung trong cùng đường dẫn trước khi cài đặt, hành động **verify-then-use** bị lỗi *time-of-check/time-of-use* (TOCTOU).

Ví dụ thiết kế an toàn hơn: tải tệp xuống vùng staging do tiến trình đáng tin kiểm soát, xác minh chữ ký và digest, rồi dùng **chính nội dung đã được xác minh** để cài đặt; nếu phải mở lại, cần thiết kế chống thay thế/race và phân quyền tệp phù hợp.

Hash đúng ở thời điểm kiểm tra không tự khóa cứng nội dung cho mọi lần sử dụng sau đó.

## 6. Ví dụ Java 17: kiểm tra SHA-256 và HMAC-SHA256 của tệp

Đoạn Java dưới đây dùng **MessageDigest** để hash tệp theo luồng và **Mac** để tạo/kiểm tra HMAC. Mã hoàn chỉnh nhằm minh họa, không phụ thuộc thư viện ngoài.

Trong **demo**, digest và tag tham chiếu được tạo từ tệp ban đầu để chứng minh kết quả kiểm tra. Trong hệ thống thật, **digest đáng tin phải đến từ manifest/kênh đã xác thực**, còn MAC phải được tạo bởi chủ thể nắm giữ **khóa bí mật được cấp phát an toàn**. Không được tự đọc digest nằm cùng kho tệp do attacker kiểm soát rồi coi đó là bằng chứng nguồn gốc.

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HashIntegrityCheckDemo {
    private static final int BUFFER_SIZE = 8192;
    private static final SecureRandom RNG = new SecureRandom();

    // Băm byte của tệp, không tự chuyển thành String.
    public static byte[] sha256File(Path file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[BUFFER_SIZE];

        try (InputStream input = Files.newInputStream(file)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (count > 0) {
                    digest.update(buffer, 0, count);
                }
            }
        }
        return digest.digest();
    }

    // HMAC tạo integrity tag khi phía tạo và kiểm tra có khóa chung.
    public static byte[] hmacSha256File(Path file, byte[] secret)
            throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));

        byte[] buffer = new byte[BUFFER_SIZE];
        try (InputStream input = Files.newInputStream(file)) {
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (count > 0) {
                    mac.update(buffer, 0, count);
                }
            }
        }
        return mac.doFinal();
    }

    public static boolean matchesSha256(
            Path file, byte[] trustedDigest) throws Exception {
        if (trustedDigest == null || trustedDigest.length != 32) {
            throw new IllegalArgumentException("Invalid SHA-256 digest");
        }
        return MessageDigest.isEqual(trustedDigest, sha256File(file));
    }

    public static boolean matchesHmac(
            Path file, byte[] secret, byte[] expectedTag) throws Exception {
        if (expectedTag == null || expectedTag.length != 32) {
            return false; // Full-length HMAC-SHA256 tag in this format.
        }
        byte[] computed = hmacSha256File(file, secret);
        try {
            return MessageDigest.isEqual(expectedTag, computed);
        } finally {
            Arrays.fill(computed, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        Path demoFile = Files.createTempFile("hash-integrity-", ".txt");
        byte[] macKey = new byte[32];
        RNG.nextBytes(macKey);

        try {
            Files.write(demoFile,
                "invoice=154;amount=250".getBytes(StandardCharsets.UTF_8));

            // Chỉ trong demo: bản gốc là tham chiếu đáng tin.
            byte[] originalHash = sha256File(demoFile);
            byte[] originalMac = hmacSha256File(demoFile, macKey);

            System.out.println("Original SHA-256 matches: "
                + matchesSha256(demoFile, originalHash));
            System.out.println("Original HMAC matches: "
                + matchesHmac(demoFile, macKey, originalMac));

            // Mô phỏng tệp bị sửa sau khi tham chiếu đã được tạo.
            Files.write(demoFile,
                "invoice=154;amount=999".getBytes(StandardCharsets.UTF_8));

            System.out.println("Modified SHA-256 matches: "
                + matchesSha256(demoFile, originalHash));
            System.out.println("Modified HMAC matches: "
                + matchesHmac(demoFile, macKey, originalMac));
        } finally {
            Arrays.fill(macKey, (byte) 0);
            Files.deleteIfExists(demoFile);
        }
    }
}
~~~

Kết quả dự kiến:

~~~text
Original SHA-256 matches: true
Original HMAC matches: true
Modified SHA-256 matches: false
Modified HMAC matches: false
~~~

### 6.1. Giải thích cách triển khai

1. **Đọc luồng:** dùng bộ đệm 8192 byte để xử lý tệp lớn mà không nạp cả tệp vào RAM.
2. **Không chuyển byte sang chuỗi:** digest của tệp phải tính trên byte đúng như manifest đã cam kết.
3. **So sánh:** MessageDigest.isEqual giúp so sánh mảng byte theo cách phù hợp hơn phép so sánh từng byte tự viết khi làm việc với dữ liệu xác thực nhạy cảm; điều kiện đầu vào như độ dài vẫn phải được kiểm tra.
4. **Khóa HMAC:** mã demo dùng SecureRandom tạo 32 byte để minh họa. Production cần cấp khóa qua **KMS/HSM hoặc cơ chế quản lý bí mật thích hợp**, dùng đúng phạm vi và mục đích.
5. **Tệp tạm:** ví dụ xóa tệp khi kết thúc. Trong quy trình thật, không sử dụng lại tệp do bên không tin cậy có thể thay thế sau khi kiểm tra.
6. **Giới hạn xóa khóa:** Arrays.fill giảm thời gian mảng khóa tồn tại ở dạng rõ; **SecretKeySpec, Mac provider và JVM có thể giữ bản sao khác**, nên việc xóa mảng không đảm bảo mọi vật liệu được xóa khỏi bộ nhớ.

Nếu viết công cụ xác minh manifest thực tế, còn phải triển khai: lấy digest từ manifest **đã xác thực**, phân tích/kiểm tra hex đúng định dạng, xác minh chữ ký hoặc MAC của manifest, kiểm tra artifact ID/version, chống path traversal và ngăn thay tệp sau khi xác minh. Ví dụ chủ ý không gộp các bước đó thành một công cụ giả lập hoàn chỉnh.

### 6.2. Dùng kiểm tra chữ ký số thay cho HMAC khi nhiều bên cần xác minh

Nếu bên phát hành ký manifest bằng **Ed25519** hoặc một thuật toán chữ ký chuẩn khác, mỗi client chỉ cần **public key đã xác thực** để xác minh. Private signing key nên nằm trong ranh giới bảo vệ riêng (có thể qua KMS/HSM và quyền ký được kiểm soát), và người dùng tải xuống không cần được cấp khóa bí mật như ở HMAC.

Lựa chọn HMAC hay chữ ký số phụ thuộc mô hình chia sẻ bí mật và yêu cầu chứng minh nguồn phát hành. **Không phát khóa HMAC cho mọi client công khai**, vì một client bất kỳ sở hữu khóa đó có thể tạo MAC hợp lệ cho nội dung giả.

## 7. HMAC, khóa MAC và vòng đời key management

Khóa HMAC là **symmetric secret key**. Một HMAC mạnh về mặt thuật toán vẫn có thể bị giả mạo nếu kẻ tấn công lấy được khóa hoặc chiếm một workload có quyền gọi API tạo MAC.

| Giai đoạn | Thực hành cần có | Rủi ro nếu làm sai |
| --- | --- | --- |
| **Sinh khóa** | Tạo khóa HMAC ngẫu nhiên đủ mạnh với CSPRNG/KMS; định danh và gán mục đích | Khóa yếu, dùng mật khẩu dễ đoán thay khóa |
| **Cấp phát** | Chỉ cấp cho đúng principal/workload; kênh bảo vệ phù hợp | Lộ qua Git, CI/CD, file cấu hình hoặc người không cần biết |
| **Lưu trữ** | Secret manager, KMS/HSM có API MAC hoặc ranh giới tương đương | Key bị đọc cùng dữ liệu hoặc xuất tùy tiện |
| **Sử dụng** | HMAC chuẩn, key separation, kiểm tra toàn bộ message bytes và context | Tag hợp lệ với sai loại thông điệp, thiếu trường quan trọng |
| **Rotation** | Gắn key ID/version, thay khóa phát hành MAC mới, có cửa sổ xác minh cũ được giới hạn | Webhook, artifact hoặc thông điệp tồn đọng không còn xác minh được |
| **Thu hồi** | Chặn quyền tạo MAC, vô hiệu hóa hoặc thay khóa bị lộ, đánh giá tag đã phát hành | Kẻ chiếm quyền tiếp tục tạo tag giả |
| **Hủy** | Giữ khóa cũ đúng thời hạn xác minh cần thiết rồi hủy có kiểm soát | Mất khả năng xác minh nội dung cũ hoặc giữ khóa quá lâu |
| **Audit** | Ghi sự kiện CreateMac/VerifyMac, key ID, principal, kết quả và thay policy | Không phát hiện lạm dụng; log vô tình làm lộ khóa |

### 7.1. Kiểm soát quyền tạo MAC khác quyền kiểm tra MAC

Với HMAC thông thường, việc **biết khóa** cho phép cả tạo và kiểm tra tag. Do đó người có khóa để Verify cũng có thể giả lập việc tạo tag mới nếu được truy cập trực tiếp vật liệu khóa.

Một số dịch vụ KMS/HSM cho phép giữ HMAC key **không xuất được** và cấp quyền **GenerateMac** riêng với **VerifyMac** thông qua API. Cách phân tách quyền này giảm nguy cơ dùng khóa trực tiếp khi hạ tầng và chính sách hỗ trợ, nhưng vẫn phải kiểm soát loại thông điệp và mục đích sử dụng ở tầng ứng dụng.

Ví dụ vai trò:

- **event-publisher:** quyền tạo MAC cho đúng loại sự kiện và miền dữ liệu.
- **event-consumer:** quyền xác minh MAC trong phạm vi được cấp; không tự có quyền tạo MAC.
- **key-admin:** quyền quản trị vòng đời, không mặc nhiên được đọc payload nhạy cảm hoặc tạo MAC.
- **auditor:** quyền xem metadata và log, không cần vật liệu khóa.

Hệ thống phải giới hạn **key ID, resource, environment, purpose và principal**. Nếu mọi service đều gọi GenerateMac với cùng một khóa, lỗi tại một service có thể khiến mọi hệ thống tin vào tag giả.

### 7.2. Rotation khi các bên phải xác minh nội dung cũ

Giả sử nhà cung cấp webhook chuyển từ **mac-key-v1** sang **mac-key-v2**:

1. Tạo khóa v2 trong kho bảo vệ, khai báo key ID và chính sách.
2. Cấp quyền cho phía gửi và phía xác minh trong thời điểm chuyển đổi được thống nhất.
3. Bên gửi chuyển sang tạo tag bằng v2; thông điệp có metadata key ID đã được ràng buộc đúng trong thông điệp được xác thực.
4. Phía nhận chấp nhận tag v1 của những thông điệp tồn đọng trong **khoảng thời gian có giới hạn**, kiểm tra timestamp/nonce/event ID chống replay.
5. Hết thời hạn cho phép, tắt đường xác minh v1 theo chính sách; đánh giá việc lưu trữ chứng cứ lịch sử nếu cần.

Nếu **khóa v1 đã bị lộ**, việc tiếp tục chấp nhận MAC v1 trong cửa sổ chuyển đổi bình thường có thể bị lợi dụng để phát hành sự kiện giả. Phải kích hoạt quy trình thu hồi khẩn cấp, đánh giá thông điệp đã nhận và kế hoạch thay khóa.

Không để client tự gửi key URL hoặc key ID rồi bắt server tải **khóa chưa tin cậy**. Key ID chỉ được phép chọn trong **tập khóa do server đã cấu hình và cấp quyền**.

## 8. Integrity check trong envelope encryption và lưu trữ dữ liệu

Hệ thống lưu trữ thường dùng **envelope encryption**:

- **DEK (Data Encryption Key)** mã hóa bản ghi/tệp bằng AES-GCM.
- **KEK (Key Encryption Key)** được quản lý trong KMS/HSM để wrap/unwrap DEK.
- **Nonce, authentication tag, wrapped DEK, key ID/version** được lưu với ciphertext theo định dạng.
- **AAD** ràng buộc bản mã với tenant, record ID, purpose hoặc schema version khi cần.
- **IAM, chính sách KMS và kiểm tra quyền nghiệp vụ** quyết định ai được tạo/mở DEK.

~~~mermaid
flowchart TD
    A["Dữ liệu gốc + AAD đáng tin"] --> G["AES-GCM với DEK"]
    D["DEK"] --> G
    G --> C["Ciphertext + nonce + authentication tag"]
    D --> W["Wrap DEK bằng KEK"]
    K["KEK trong KMS/HSM"] --> W
    W --> E["Wrapped DEK"]
    C --> S["Kho dữ liệu"]
    E --> S
    S --> R["Giải mã: xác thực tag + AAD trước khi dùng plaintext"]
~~~

**Không cần thay authentication tag của AES-GCM bằng SHA-256 của ciphertext.** SHA-256 không có khóa, vì thế kẻ sửa ciphertext có thể tính digest mới nếu tham chiếu không được bảo vệ. AES-GCM đã cung cấp kiểm tra toàn vẹn/xác thực cho ciphertext và AAD theo khóa/nonce/tag khi được triển khai đúng.

Tuy nhiên, một hệ thống backup cũng có thể duy trì **hash của tệp backup** để phát hiện lỗi truyền hoặc lỗi lưu trữ ngoài cơ chế mã hóa. Đây là lớp kiểm tra phụ trợ; không thay thế khả năng giải mã và xác thực của AEAD.

### 8.1. Rotation DEK/KEK ảnh hưởng integrity check ra sao?

| Thao tác | Tác động |
| --- | --- |
| **Rotate KEK** | Có thể thay KEK dùng cho wrapped DEK mới; ciphertext của dữ liệu cũ không tự đổi |
| **Rewrap DEK** | Thay lớp bảo vệ của cùng DEK, ciphertext dữ liệu có thể giữ nguyên |
| **Re-encrypt bằng DEK mới** | Ciphertext, nonce và tag thường thay; digest của bản mã lưu trữ cũng thay |
| **Thay AAD/schema version** | Phải tái tạo đúng AAD của bản ghi cũ hoặc di chuyển dữ liệu |
| **Hủy KEK/DEK** | Có thể mất đường giải mã dù hash của ciphertext vẫn khớp |

Hash khớp trên một bản backup **không chứng minh backup có thể phục hồi**: còn phải giữ đúng key version, wrapped DEK, nonce/tag, context cần thiết và quyền truy cập KMS, đồng thời thử khôi phục định kỳ.

### 8.2. Hash kiểm tra tính toàn vẹn của khóa?

Một số hệ thống có thể dùng fingerprint (digest của **public key**) để đối chiếu khóa công khai qua kênh xác thực. Fingerprint giúp nhận ra khóa bị thay, nhưng **không tạo ra ràng buộc danh tính** nếu fingerprint cũng đến từ cùng nguồn bị chiếm.

Đối với **private key, symmetric DEK, KEK hoặc HMAC key**, không nên công bố hash đơn giản của khóa như một phương tiện xác thực: việc làm lộ thông tin về khóa, khả năng thử đoán và lợi ích kiểm tra phụ thuộc mô hình đe dọa. Nên dùng **key ID, KMS/HSM metadata, quyền và cơ chế kiểm tra nội bộ được thiết kế an toàn** thay cho việc công bố fingerprint của vật liệu bí mật.

## 9. Tệp lớn, Merkle tree và kiểm tra theo khối

Với tệp lớn hoặc hệ thống phân tán, có thể không muốn đọc toàn bộ tệp mỗi lần xác minh một mảnh. **Merkle tree** tổ chức digest của các khối dữ liệu thành cây hash.

~~~text
                   Root hash (được xác thực)
                         |
                Hash(nodeL || nodeR)
                    /         \
              Hash(L1,L2)    Hash(L3,L4)
                 /   \          /   \
               H(C1) H(C2)    H(C3) H(C4)
~~~

Một **Merkle proof** cho phép kiểm tra rằng một khối thuộc tập dữ liệu được cam kết bởi root hash mà không phải tải mọi khối. Nhưng điều đó chỉ bảo vệ chống tấn công khi **root hash được tin cậy và xác thực**, chẳng hạn nằm trong manifest ký số hoặc một sổ ghi đã được kiểm soát.

Khi thiết kế Merkle tree thực tế cần xác định chính xác:

- Thuật toán hash và cách phân biệt **leaf hash** với **internal node hash** (domain separation).
- Cách phân chia khối và xử lý số khối lẻ.
- Thứ tự trái/phải, cách nối byte, độ dài và định dạng của từng nút.
- Phạm vi dữ liệu, version và root hash đáng tin.
- Quy tắc cập nhật, chống rollback và giới hạn kích thước.

**Merkle root công khai không tự chứng minh ai đã tạo dữ liệu.** Kẻ tấn công kiểm soát cả cây và root có thể tính lại tất cả digest; hệ thống vẫn cần một nguồn root đáng tin.

### Khi nào dùng streaming, khi nào dùng cây hash?

| Nhu cầu | Phương án phù hợp |
| --- | --- |
| Tải một artifact, xác minh một lần trước khi chạy | SHA-256 đọc theo luồng + digest tham chiếu được xác thực |
| Xác minh webhook giữa hai dịch vụ | HMAC hoặc chữ ký số theo giao thức, kiểm tra đầy đủ header/body và chống replay |
| Kiểm tra một khối trong tập dữ liệu cực lớn | Merkle proof với root đã được xác thực |
| Kiểm tra backup lưu trữ lâu dài | Digest để phát hiện hỏng byte + kiểm tra khóa/AEAD + thử restore |
| Xác minh nguồn phát hành phần mềm cho nhiều client | Manifest ký số, public key được quản lý vòng đời và chính sách chống rollback |

## 10. Những lỗi bảo mật hay gặp

### 10.1. Tin SHA-256 được phát hành cùng tệp từ nguồn không tin cậy

**Sai lầm:** tải file.jar và SHA256SUMS từ cùng một máy chủ bị chiếm rồi kiểm tra thấy khớp.

**Vấn đề:** kẻ tấn công có thể thay cả hai.

**Cách xử lý:** lấy digest thông qua nguồn đáng tin hoặc **xác minh chữ ký số trên manifest** trước khi so sánh hash. Kiểm tra public key dùng Verify đã được gắn với đúng nhà phát hành.

### 10.2. Sử dụng MD5 hoặc SHA-1 cho mục tiêu chống kẻ tấn công

**Sai lầm:** vẫn dùng MD5 hoặc SHA-1 để xác minh artifact quan trọng vì hệ thống cũ hỗ trợ.

**Vấn đề:** khả năng tìm collision thực tế làm mất bảo đảm chống giả mạo trong các quy trình có thể bị tấn công qua collision.

**Cách xử lý:** chuyển sang SHA-256 hoặc một lựa chọn được chính sách/chuẩn chấp nhận; ký manifest, quản lý định dạng và bảo đảm phía xác minh không chấp nhận thuật toán yếu do đầu vào yêu cầu.

### 10.3. Tự thiết kế MAC từ SHA-256 và secret

**Sai lầm:** tính SHA256(secret || message) như “chữ ký nhẹ”.

**Vấn đề:** xây dựng tự chế có thể chịu **length-extension attack** hoặc những lỗi giao thức khác tùy cấu trúc. Việc nối thêm dấu phân cách hoặc chỉ băm lại không tạo một MAC đã được kiểm chứng.

**Cách xử lý:** dùng **HmacSHA256** hoặc cơ chế MAC chuẩn; ràng buộc purpose, message type, timestamp/nonce theo giao thức và giới hạn quyền sử dụng khóa.

### 10.4. Chỉ hash body nhưng quên context

**Sai lầm:** API webhook tạo HMAC cho body nhưng server lại sử dụng tenant ID và loại sự kiện từ header **không nằm trong thông điệp được xác thực**.

**Vấn đề:** kẻ tấn công có thể giữ body/tag hợp lệ nhưng sửa header không được bảo vệ để thay đổi cách xử lý.

**Cách xử lý:** định nghĩa chính xác **signed/MACed bytes** bao gồm các trường an ninh cần thiết, với canonical encoding không nhập nhằng; kiểm tra tenant và quyền nghiệp vụ riêng.

### 10.5. Không chống replay

**Sai lầm:** HMAC hoặc chữ ký hợp lệ thì chuyển tiền ngay, không kiểm tra ID sự kiện hoặc thời hạn.

**Vấn đề:** kẻ tấn công có thể phát lại **nguyên thông điệp + tag hợp lệ**. Tính toàn vẹn không tự chứng minh tính mới.

**Cách xử lý:** timestamp trong cửa sổ hợp lệ, event ID/idempotency key, nonce hoặc sequence number với kiểm tra trạng thái theo giao thức. Các trường này phải được bảo vệ bằng MAC/chữ ký khi có ý nghĩa bảo mật.

### 10.6. Thiếu quản lý khóa xác thực

**Sai lầm:** lưu HMAC key trong repository hoặc cho mọi ứng dụng gọi GenerateMac không giới hạn.

**Vấn đề:** kẻ nắm khóa hoặc quyền gọi MAC có thể tạo tag hợp lệ; thuật toán HMAC vẫn mạnh nhưng ranh giới tin cậy đã bị phá.

**Cách xử lý:** dùng KMS/HSM hoặc secret manager phù hợp, tách quyền, rotation, revoke, logging và kiểm tra quyền nghiệp vụ theo principal.

## 11. Tình huống thực tế: kiểm tra bản phát hành Java trong CI/CD

Một tổ chức có hệ thống CI xây dựng **billing-service.jar**. Hệ thống vận hành cần chắc chắn rằng artifact được cài là **đúng phiên bản đã được phê duyệt** và chưa bị sửa khi truyền từ kho artifact tới máy chủ.

**Mô hình khuyến nghị:**

1. **Build stage:** tạo artifact bất biến; tính SHA-256 trên byte artifact.
2. **Release metadata:** tạo manifest có artifact ID, version, size, SHA-256 và tên thuật toán.
3. **Signing stage:** dịch vụ ký có quyền giới hạn **Sign** ký manifest với private key được bảo vệ; không cấp quyền ký rộng cho mọi job build.
4. **Distribution:** đưa artifact, manifest và chữ ký vào repository. Có thể phân phối công khai vì bí mật không nằm trong digest hay public key.
5. **Verification:** agent triển khai lấy public key/CA từ trust configuration đã được xác thực; kiểm tra chữ ký manifest, phiên bản được phép, tên tệp, digest và kích thước.
6. **Deployment:** sử dụng đúng nội dung artifact đã xác minh, kiểm soát race giữa verify và use.
7. **Audit:** ghi release ID, artifact digest, signing key ID/version, kết quả kiểm tra và principal triển khai; không ghi private key hoặc access token.
8. **Rotation:** đưa public key mới tới verifier trước khi chuyển signer sang private key mới; duy trì hoặc loại bỏ khóa cũ theo chính sách phiên bản, chống rollback và thời hạn lưu trữ.
9. **Incident response:** nếu signing key bị lộ, thu hồi quyền, đánh giá các manifest/release bị ảnh hưởng, thay khóa và tái phát hành các artifact tin cậy theo quy trình.

~~~mermaid
flowchart LR
    B["CI Build"] --> H["SHA-256 artifact"]
    H --> M["Release manifest"]
    K["Private signing key trong KMS/HSM"] --> S["Sign manifest"]
    M --> S
    S --> R["Artifact repository"]
    B --> R
    R --> V["Deploy agent: Verify signature + SHA-256 + version"]
    T["Public key / trust anchor đã xác thực"] --> V
    V --> D{"Tất cả điều kiện đạt?"}
    D -->|Có| A["Deploy artifact đã kiểm tra"]
    D -->|Không| X["Từ chối / điều tra"]
~~~

**Một chữ ký hợp lệ cũng không thay thế kiểm tra pipeline:** nếu attacker chiếm được chính bước ký hoặc có thể yêu cầu ký artifact chưa được phê duyệt, agent vẫn có thể thấy chữ ký đúng. Cần tách trách nhiệm, chính sách ký, bảo vệ CI/CD và provenance của bản phát hành.

## 12. Audit, giám sát và ứng phó sự cố

Một quy trình integrity check có giá trị khi lỗi được **xử lý nhất quán**. Không nên bỏ qua kết quả so sánh hash chỉ vì artifact vẫn chạy được.

Những sự kiện cần quan sát:

- SHA-256 không khớp digest đã xác thực.
- Chữ ký manifest sai, public key không tin cậy hoặc signing certificate bị thu hồi.
- Có nỗ lực đổi thuật toán xác minh sang loại bị cấm.
- Nhiều lần xác minh HMAC lỗi, request replay hoặc key ID không tồn tại.
- Quyền GenerateMac/Sign được cấp mới, chính sách khóa bị thay, rotation hoặc disable bất thường.
- Artifact có cùng version nhưng nhiều digest khác nhau mà không có chính sách phát hành phù hợp.
- Backup có digest khớp nhưng kiểm thử giải mã/restore thất bại vì mất DEK/KEK hoặc metadata.

**Log an toàn** nên chứa request/build ID, artifact digest hoặc prefix/định danh phù hợp, key ID, loại thuật toán, trạng thái xác minh, nguồn yêu cầu và timestamp. Không ghi private signing key, HMAC secret, DEK rõ, token, nội dung payload bí mật hoặc dữ liệu nhạy cảm chỉ để dễ debug.

Nếu phát hiện artifact có hash không khớp:

1. **Cách ly artifact**, không triển khai/chạy thử trên môi trường production.
2. Xác nhận digest tham chiếu hoặc chữ ký manifest thực sự đáng tin và đúng phiên bản.
3. Kiểm tra lỗi truyền/lưu trữ, khả năng file bị thay thế và các dấu hiệu xâm nhập.
4. Nếu nghi ngờ signing key hoặc MAC key bị lộ, thu hồi quyền, thay khóa và xác định phạm vi nội dung đã được ký/MAC.
5. Khôi phục từ artifact/bản sao đã được xác minh, lưu bằng chứng điều tra và đánh giá ảnh hưởng tới hệ thống liên quan.

## 13. Checklist thiết kế hash integrity check

1. **Mục tiêu:** phát hiện lỗi ngẫu nhiên hay chống sửa đổi có chủ đích?
2. **Đối tượng:** kiểm tra đúng byte tệp, bản ghi hay thông điệp canonical?
3. **Thuật toán:** đã sử dụng SHA-256/SHA-2/SHA-3 hoặc lựa chọn được cho phép, tránh MD5/SHA-1 trong thiết kế chống tấn công chưa?
4. **Digest đáng tin:** nguồn của digest tham chiếu có độc lập và đã được xác thực không?
5. **Nguồn phát hành:** có cần HMAC hoặc chữ ký số trên manifest không; public key/secret được quản lý thế nào?
6. **Metadata:** tên, version, size, hash algorithm, purpose và context có nằm trong dữ liệu được ký/MAC không?
7. **Chống replay/rollback:** có chính sách kiểm tra phiên bản, freshness và event ID khi cần không?
8. **Phân tích byte:** có kiểm soát encoding, newline, canonicalization và cách mở tệp nhất quán không?
9. **Verify-before-use:** có ngăn tệp bị thay giữa bước kiểm tra và sử dụng không?
10. **Khóa:** HMAC/signing key được tạo, cấp quyền, lưu, sử dụng, rotation, revoke và hủy trong KMS/HSM hoặc kho tin cậy phù hợp không?
11. **Key separation:** khóa MAC có tách theo purpose, workload, môi trường và tenant khi cần không?
12. **Kiểm toán:** log có ghi trạng thái xác minh và sự kiện thay khóa mà không làm lộ secret không?
13. **Dữ liệu mã hóa:** AEAD tag, AAD, nonce, DEK/KEK có được kiểm tra và quản lý riêng với hash của bản backup không?
14. **Phục hồi:** nếu digest không khớp hoặc khóa xác thực bị lộ, có đường cô lập, khôi phục, re-sign và đánh giá dữ liệu ảnh hưởng không?

### Câu hỏi tự kiểm tra

**Câu 1.** Hệ thống tải file.zip và file.zip.sha256 từ cùng một máy chủ. Hai giá trị khớp. Có thể kết luận tệp không bị kẻ tấn công sửa không?

**Đáp án:** Chưa. Nếu kẻ tấn công thay được cả tệp và file digest, họ có thể tính lại SHA-256. Cần digest từ nguồn đáng tin hoặc manifest có chữ ký/MAC được xác minh.

**Câu 2.** Hash SHA-256 có khóa bí mật không? Nó có thể xác thực ai tạo thông điệp không?

**Đáp án:** Không có khóa bí mật và không tự xác thực tác giả. Bất kỳ ai có dữ liệu đều tính được SHA-256; xác thực nguồn cần cơ chế khác như HMAC hoặc chữ ký số.

**Câu 3.** Vì sao HMAC-SHA256 thường phù hợp hơn SHA256(secret || message)?

**Đáp án:** HMAC là cấu trúc MAC chuẩn có phân tích bảo mật và chống các sai lầm của cách ghép hash tự chế, trong đó có nguy cơ length extension đối với một số cấu trúc naïve.

**Câu 4.** Một webhook có HMAC hợp lệ nhưng đã được gửi thành công hôm qua. Có nên xử lý lại giao dịch hôm nay không?

**Đáp án:** Không tự động. HMAC xác thực nội dung và khóa tạo MAC, không chứng minh tính mới. Cần kiểm tra timestamp, event ID, nonce hoặc trạng thái idempotency theo giao thức.

**Câu 5.** Vì sao dùng HMAC có thể không phù hợp cho công bố artifact cho hàng triệu người dùng bên ngoài?

**Đáp án:** Người xác minh HMAC thường phải có cùng secret; cấp cho mọi người dùng đồng nghĩa họ cũng có thể tạo MAC giả. Chữ ký số cho phép xác minh bằng public key không bí mật.

**Câu 6.** Backup có SHA-256 khớp bản gốc, nhưng KEK của bản backup đã bị hủy. Có khôi phục được bản rõ không?

**Đáp án:** Không bảo đảm, thậm chí có thể không thể khôi phục. Hash chỉ xác nhận byte backup không khác; phải có DEK/KEK và metadata đủ để giải mã, xác thực AEAD và kiểm thử restore.

**Câu 7.** Nếu kẻ tấn công chiếm được tài khoản được phép yêu cầu HSM Sign, private key không xuất được có đủ để bảo đảm artifact không bị ký giả không?

**Đáp án:** Không. Kẻ tấn công có thể lợi dụng quyền Sign để yêu cầu HSM tạo chữ ký hợp lệ trên manifest trái phép. Cần IAM least privilege, kiểm soát phê duyệt release, nhật ký kiểm toán và phát hiện lạm dụng.

## Kết luận

**Hash integrity check** là cách hiệu quả để kiểm tra một chuỗi byte có khớp với digest tham chiếu hay không. Với SHA-256, lỗi truyền tải hoặc sửa tệp thường khiến digest khác và có thể được phát hiện. Nhưng **hash không có khóa không tự xác thực nguồn**: nếu attacker kiểm soát cả dữ liệu và digest, phép so sánh vẫn có thể cho kết quả khớp.

Để bảo vệ dữ liệu và artifact trong hệ thống thật, cần xác định rõ mô hình đe dọa và kết hợp hash với **HMAC hoặc chữ ký số khi cần xác thực nguồn**, **AEAD khi cần mã hóa có xác thực**, cùng quy trình **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy khóa** qua KMS/HSM, IAM và audit. **Tính toán đúng digest mới là nửa đầu của bài toán; nửa còn lại là chứng minh digest tham chiếu và quyền sử dụng khóa thực sự đáng tin.**
