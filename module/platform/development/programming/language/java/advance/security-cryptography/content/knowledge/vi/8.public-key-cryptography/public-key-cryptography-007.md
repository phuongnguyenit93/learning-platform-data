# 8.7. RSA-OAEP, giới hạn kích thước bản rõ và mô hình mã hóa lai

RSA là một thuật toán khóa công khai có thể dùng trong nhiều cơ chế khác nhau. Khi muốn mã hóa bằng RSA hiện đại, không lấy phép tính RSA “thuần” hay padding PKCS#1 v1.5 rồi tự áp dụng cho dữ liệu lớn. Cần dùng một **encryption scheme được chuẩn hóa**, điển hình là **RSAES-OAEP (Optimal Asymmetric Encryption Padding)**, với thuật toán băm, MGF1 và nhãn OAEP được xác định rõ.

Tuy nhiên, ngay cả RSA-OAEP đúng chuẩn cũng **không phải công cụ mã hóa trực tiếp tệp hoặc message dài**. Nó giới hạn kích thước bản rõ chỉ vài trăm byte tùy độ dài modulus và hash. Vì vậy mô hình ứng dụng thông dụng là **mã hóa lai (hybrid encryption)**: sinh một khóa đối xứng ngẫu nhiên để mã hóa dữ liệu bằng AEAD (như AES-GCM), rồi dùng RSA-OAEP **mã hóa/gói khóa đối xứng** cho người nhận.

Bài này giúp bạn trả lời bốn câu hỏi thực tế:

1. Vì sao RSA-OAEP chỉ mã hóa được payload ngắn, và tính được giới hạn chính xác?
2. OAEP gồm những tham số nào, tại sao **OAEP hash** và **MGF1 hash** phải được hai bên thống nhất?
3. Trong mã hóa lai, RSA làm gì, AES-GCM làm gì, và định dạng envelope cần lưu gì để bên nhận giải mã?
4. Cách viết Java 17+ sử dụng JCA/JCE chuẩn, xử lý lỗi khi bản rõ quá dài, sai label OAEP hoặc bị sửa ciphertext?

Sau bài học, bạn nên tự tính được `mLen ≤ k − 2hLen − 2`, thiết kế được một hybrid envelope có version/metadata rõ ràng, hiểu sự khác biệt giữa **tính bí mật**, **tính toàn vẹn** và **xác thực người gửi**, cũng như kiểm tra được một luồng encrypt/decrypt thực thi trong Java.

## 1. RSA khóa công khai: cặp khóa và mục đích

RSA dùng một cặp khóa:

- **Public key**: có thể công bố cho bên gửi; trong RSA encryption, dùng để mã hóa khóa hoặc dữ liệu ngắn dành cho người giữ private key.
- **Private key**: phải được bảo vệ; trong RSA decryption, dùng để khôi phục giá trị đã mã hóa bằng public key tương ứng.

Ở tầng toán học, RSA liên quan đến lũy thừa modulo `n`, nhưng một phép toán modular exponentiation **không phải scheme mã hóa an toàn** nếu thiếu encoding/padding và quy tắc kiểm tra phù hợp. Hãy sử dụng **RSAES-OAEP** từ thư viện crypto tin cậy, không tự ghép byte hay tự cài OAEP.

```text
             Recipient
           +--------------+
           | RSA public   |----> chia sẻ sau khi xác minh nguồn/định danh
           | RSA private  |----> lưu bí mật, chỉ môi trường nhận sử dụng
           +--------------+

Sender: data/key -- RSA-OAEP(public) --> RSA ciphertext
Recipient: RSA ciphertext -- RSA-OAEP(private) --> data/key
```

Chỉ vì bạn có một “public key” không có nghĩa nó thực sự thuộc người nhận mong đợi. Nếu đối thủ thay được public key trong quá trình phân phối, họ có thể khiến bạn mã hóa dữ liệu cho **khóa của đối thủ**. Mọi triển khai thật đều phải kiểm tra đường tin cậy: certificate chain và tên máy/chủ thể phù hợp, khóa đã pin có chính sách rotation, hoặc một kênh phân phối khóa công khai đã xác thực.

**RSA encryption khác RSA signature.** RSA-OAEP bảo vệ tính bí mật của plaintext cho người sở hữu private key; không tự tạo một chữ ký để người nhận biết ai đã gửi. Dùng RSA-PSS (hoặc scheme ký phù hợp) khi cần chữ ký số; không coi kết quả RSA-OAEP là “chữ ký ngược”.

## 2. RSA-OAEP là gì?

RSAES-OAEP được mô tả trong **RFC 8017 / PKCS #1 v2.2**. OAEP mã hóa thông điệp đầu vào thành một block có cấu trúc, sử dụng hash, mask generation function (thường là MGF1), seed ngẫu nhiên và một **label** tùy chọn, rồi mới áp dụng RSA public-key operation.

Các thành phần liên quan:

| Thành phần | Vai trò | Điều cần thống nhất |
| --- | --- | --- |
| Modulus RSA `n` | Quy định kích thước block RSA | Public/private key tương ứng, kích cỡ modulus |
| OAEP digest `Hash` | Hash trong OAEP, quyết định `hLen` | Ví dụ `SHA-256` với 32 byte digest |
| Mask generation function | Sinh mặt nạ bên trong OAEP | Thường `MGF1` |
| Digest của MGF1 | Hash dùng bên trong MGF1 | Ví dụ cũng là `SHA-256`, phải cấu hình rõ |
| Label `L` | Chuỗi byte ngữ cảnh tùy chọn | Hai bên dùng chính xác cùng byte label |
| Random seed | Làm mã hóa xác suất | Thư viện sinh ngẫu nhiên phù hợp |
| RSA public/private key | Mã hóa/giải mã | Key phải đúng người nhận |

Một cách nhìn khái niệm:

```text
Message M (byte[≤ max]) + Label L
                 |
          OAEP Encoding
      (Hash, MGF1, random seed)
                 |
     Encoded message EM (k bytes)
                 |
        RSA public operation
                 |
     RSA ciphertext C (k bytes)
                 |
     RSA private operation + OAEP Decoding
                 |
            Message M
```

Sơ đồ trên diễn tả ý tưởng; không dùng để tự implement padding.

### 2.1. OAEP là randomized encryption

Hai lần mã hóa **cùng một plaintext và cùng public key** bằng RSA-OAEP có thể tạo **ciphertext khác nhau** vì OAEP có randomness. Đây là hành vi mong muốn. Đừng kiểm thử RSA-OAEP bằng cách đòi ciphertext hai lần phải bằng nhau.

Bài kiểm tra đúng phải là:
- Sau khi encrypt rồi decrypt bằng đúng private key và tham số OAEP, plaintext khôi phục khớp byte ban đầu.
- Nếu làm sai private key, label hoặc dữ liệu ciphertext, thao tác decryption bị từ chối.
- Bản rõ dài hơn giới hạn sẽ bị từ chối **trước hoặc khi encrypt**, không được cắt bớt dữ liệu.

### 2.2. Label OAEP là gì và có bí mật không?

OAEP nhận một byte string nhãn `L`. Nó có thể để rỗng (một lựa chọn chuẩn) hoặc quy định rõ trong protocol, ví dụ:

```text
L = UTF-8("hybrid-demo:v1|CEK")
```

Label **không cần bí mật**. Nó giúp ràng buộc scheme với một miền sử dụng cụ thể nếu các bên định nghĩa thống nhất. Khi encrypt dùng label `L1`, phía decrypt phải dùng đúng byte `L1`; thay thành `L2` thường khiến kiểm tra OAEP thất bại.

Không tự động coi OAEP label là hệ thống authorization. Người nhận vẫn phải xác minh key/certificate, envelope version, ai được phép gửi, và những trường metadata nào được xác thực. Nếu dùng label trong giao thức, phải công bố rõ byte/encoding và giữ ổn định theo version.

### 2.3. Hai hash trong OAEP: thông số dễ bị bỏ qua

Khi cấu hình:

```text
OAEP digest:   SHA-256
MGF:           MGF1
MGF1 digest:   SHA-256
Label:         "hybrid-demo:v1|CEK" (UTF-8)
```

đây là **một bộ tham số cụ thể**. Có thể một thư viện dùng OAEP digest SHA-256 nhưng ngầm chọn digest khác cho MGF1 nếu không chỉ định rõ. Hai implementation “cùng RSA-OAEP SHA-256” theo tên gọi nhưng khác MGF1 digest có thể **không giải mã được cho nhau**.

Trong Java 17, dùng `OAEPParameterSpec` để cấu hình minh bạch:

```java
OAEPParameterSpec oaep = new OAEPParameterSpec(
    "SHA-256",
    "MGF1",
    MGF1ParameterSpec.SHA256,
    new PSource.PSpecified(
        "hybrid-demo:v1|CEK".getBytes(StandardCharsets.UTF_8)
    )
);
```

Khi đưa `OAEPParameterSpec` vào `Cipher.init(...)`, cả OAEP digest, MGF1 digest và label được quy định. Mô tả `"RSA/ECB/OAEPPadding"` là tên transformation JCA thường được hỗ trợ; chữ `ECB` ở đây là một thành phần tên transformation của provider, **không có nghĩa RSA đang mã hóa nhiều block ở chế độ ECB như AES**.

Không tự phỏng đoán tham số chỉ dựa vào tên transformation `"RSA/ECB/OAEPWithSHA-256AndMGF1Padding"`. Nếu cần tương thích chéo Java, .NET, OpenSSL hoặc HSM, gửi đầy đủ test vector/schema và so sánh từng tham số.

## 3. Giới hạn kích thước bản rõ RSA-OAEP

Điều quan trọng nhất của bài học là công thức từ RSAES-OAEP (RFC 8017):

\[
\boxed{\text{mLen} \le k - 2\,\text{hLen} - 2}
\]

Trong đó:
- `mLen` là **số byte** của bản rõ muốn mã hóa bằng RSA-OAEP, không phải số ký tự Java `String.length()`.
- `k` là **độ dài RSA modulus tính bằng byte**: `k = ceil(bitLength(n) / 8)`.
- `hLen` là **độ dài kết quả OAEP hash tính bằng byte**. Với SHA-256, `hLen = 32`; SHA-384 là 48; SHA-512 là 64.
- Hai số `2hLen` và `2` là overhead cấu trúc OAEP; không thể lấy toàn bộ `k` byte làm bản rõ.
- MGF1 hash phải được cấu hình thống nhất; trong công thức này `hLen` chỉ kết quả của **OAEP Hash**, không lấy độ dài ciphertext hay key byte để thay.

**Ví dụ RSA-2048 + OAEP SHA-256:**

\[
k = 2048/8 = 256 \text{ byte}
\]

\[
\text{maxM} = 256 - 2(32) - 2 = \boxed{190\text{ byte}}
\]

Nếu input là 191 byte thì **không thể mã hóa trực tiếp** bằng chính cấu hình RSAES-OAEP này. Đây là giới hạn scheme, không phải lỗi “Java không nhận được chuỗi dài”.

### 3.1. Bảng kích thước minh họa

| RSA modulus | `k` (byte) | OAEP hash | `hLen` | Bản rõ tối đa | RSA ciphertext mỗi lần |
| --- | ---: | --- | ---: | ---: | ---: |
| 2048 bit | 256 | SHA-256 | 32 | **190 byte** | 256 byte |
| 3072 bit | 384 | SHA-256 | 32 | **318 byte** | 384 byte |
| 4096 bit | 512 | SHA-256 | 32 | **446 byte** | 512 byte |
| 2048 bit | 256 | SHA-384 | 48 | **158 byte** | 256 byte |
| 2048 bit | 256 | SHA-512 | 64 | **126 byte** | 256 byte |
| 3072 bit | 384 | SHA-512 | 64 | **254 byte** | 384 byte |

Bảng chỉ nói **dung lượng dữ liệu trên một phép mã hóa OAEP**, không đánh giá một khóa RSA đủ mạnh cho mọi threat model. Việc chọn RSA-2048/3072/4096 cần tuân thủ chính sách và độ dài vòng đời dữ liệu; khóa càng lớn cũng ảnh hưởng hiệu năng, ciphertext và độ dài tối đa.

Đặc biệt: khi tăng modulus từ 2048 lên 4096 bit, dung lượng OAEP SHA-256 chỉ tăng từ **190 lên 446 byte**. Nó vẫn rất nhỏ so với tệp ảnh, JSON request hoặc dữ liệu kinh doanh thực tế.

### 3.2. Byte length khác độ dài chuỗi

Trong Java, một chuỗi tiếng Việt có thể nhiều byte UTF-8 cho một ký tự. Ví dụ, `"A"` là 1 byte UTF-8, nhưng nhiều ký tự ngoài ASCII thường cần 2–4 byte. RSA-OAEP xem **byte array**, không thấy “190 ký tự”.

Khi dữ liệu là text:

```java
byte[] plaintext = value.getBytes(StandardCharsets.UTF_8);
int lengthBytes = plaintext.length;
```

Không dùng `value.length()` làm độ dài OAEP. Java `String.length()` đếm UTF-16 code units, còn OAEP limit tính theo byte.

### 3.3. Điều gì xảy ra khi vượt giới hạn?

Một provider JCA thường ném `IllegalBlockSizeException` hoặc một ngoại lệ thuộc `GeneralSecurityException` khi `Cipher.doFinal(...)` nhận OAEP plaintext quá dài. Không được “tự sửa” bằng cách cắt bớt input hoặc biến đổi thành nhiều phép RSA theo kinh nghiệm.

Đoạn logic để tính giới hạn:

```java
int modulusBits = rsaPublicKey.getModulus().bitLength();
int k = (modulusBits + 7) / 8;
int hLen = 32; // SHA-256 output length
int maximumOaepPlaintext = k - 2 * hLen - 2;
```

Nếu `maximumOaepPlaintext` âm, bộ tham số không có đủ chỗ để encode thông điệp, cần chọn key/hash và scheme phù hợp. Không suy ra “RSA key 2048 bit” thì có thể mã hóa 256 byte dữ liệu gốc; **256 byte là chiều dài RSA ciphertext**, không phải giới hạn plaintext OAEP.

## 4. Vì sao không chia tệp thành các khối nhỏ để RSA mã hóa từng khối?

Một cách làm sai thường thấy:

```text
File dài 1 MiB
   |
chia thành khối 190 byte
   |
RSA-OAEP encrypt(block0)
RSA-OAEP encrypt(block1)
...
RSA-OAEP encrypt(blockN)
   |
nối các RSA ciphertext
```

Dù từng block có thể mã hóa hợp lệ, thiết kế này thường **không nên dùng**:

1. **Rất kém hiệu năng:** RSA public-key operations tốn CPU hơn AES trong bulk encryption; giải mã private-key còn đắt hơn. Mã hóa một tệp lớn có thể tạo ra hàng nghìn phép RSA.
2. **Dung lượng phình mạnh:** với RSA-2048 + OAEP SHA-256, mỗi 190 byte plaintext thành 256 byte ciphertext, chưa tính metadata, index và protection.
3. **Thiếu giao thức xác thực tổng thể:** OAEP là scheme mã hóa bất đối xứng, không phải AEAD cho dòng các block. Nếu thiếu cơ chế bổ sung, thay thế/đảo thứ tự/bỏ block có thể không được phát hiện đúng ý nghĩa của toàn bộ tệp.
4. **Không rõ canonical framing:** phải định nghĩa số lượng/độ dài/chỉ số của từng block, chống chèn/tráo/trùng/lặp và xử lý lỗi.
5. **Không có ưu điểm quản lý khóa:** nhiều RSA decrypt vẫn dùng cùng private key; không tận dụng được tốc độ AES và khóa ngẫu nhiên độc lập cho mỗi đối tượng.

Cách đúng cho payload dài là **mã hóa lai**: **RSA-OAEP một lần cho khóa ngẫu nhiên ngắn**, **AEAD cho toàn bộ dữ liệu** theo format chuẩn.

## 5. Mô hình hybrid encryption: khóa phiên + dữ liệu

Tách hai trách nhiệm:

- **RSA-OAEP:** bảo vệ một **content-encryption key (CEK)** ngẫu nhiên. Ví dụ CEK 32 byte để dùng làm AES-256 key. Public key bên nhận mã hóa CEK; private key bên nhận giải mã CEK.
- **AES-GCM:** dùng CEK để mã hóa nội dung với nonce độc lập, tạo **ciphertext và authentication tag**. Bên nhận kiểm tra tag khi giải mã để xác định dữ liệu/AAD/khóa/nonce phù hợp.

```text
BÊN GỬI                                      BÊN NHẬN
---------                                     ---------
Public RSA key đã xác thực                    Private RSA key an toàn
       |                                           |
SecureRandom: CEK 32 byte                           |
       |                                           |
       +---- RSA-OAEP(public, CEK) --> wrappedCEK ---+--> RSA-OAEP(private)
       |                                                  |
       |                                                  +--> CEK 32 byte
       v                                                          |
SecureRandom: nonce 12 byte                                       |
       |                                                          |
AES-256-GCM(CEK, nonce, AAD, plaintext)                            |
       |                                                          |
       +--> ciphertext + tag -----------------------------> AES-GCM decrypt
                         |                                    |
              Hybrid envelope:                             Verify tag
              wrappedCEK                                    |
              nonce                                         v
              ciphertext+tag                        Plaintext (only if valid)
              version, algorithms, keyId, AAD context
```

Một đối tác nhận cần **private key RSA khớp với wrappedCEK**, **các tham số OAEP khớp**, rồi dùng CEK đã giải mã để kiểm tra AES-GCM tag. Nếu password/login hay danh tính người dùng có liên quan, đó là lớp xác thực/quản lý quyền riêng và không thể thay bằng việc mã hóa thành công.

### 5.1. Phân biệt CEK, KEK và RSA key

Trong nhiều tài liệu:
- **CEK/DEK:** khóa đối xứng mã hóa dữ liệu (content/data encryption key).
- **KEK:** khóa mã hóa một khóa khác (key-encryption key); trong mô hình này, RSA public key được dùng trong **scheme key transport/wrapping bằng RSA-OAEP**, không phải một chuỗi 32 byte dùng làm AES KEK.
- **Wrapped key:** bản mã RSA của CEK, không phải chính CEK.

RSA-OAEP wrapping CEK **không phải** thuật toán **RSA-KEM**. Cả hai có thể thuộc họ thiết kế bảo vệ khóa/hybrid, nhưng scheme và cấu trúc byte khác nhau; không gọi RSA-OAEP là RSA-KEM hoặc cho một bên dùng RSA-KEM rồi trông chờ OAEP giải mã được.

### 5.2. Vì sao dùng AES-GCM thay AES-CBC tự thiết kế?

AES-GCM là **AEAD (Authenticated Encryption with Associated Data)**. Nó vừa mã hóa plaintext, vừa cho phép phát hiện sửa đổi ciphertext và dữ liệu AAD. Thay vì tự ghép AES-CBC + padding + MAC theo thứ tự không rõ ràng, dùng AEAD đã chuẩn hóa dễ giảm nhiều lớp lỗi.

Các thông số mẫu của bài học:
- CEK: **32 byte** (AES-256).
- GCM nonce: **12 byte** (96 bit), mới cho mỗi lần encrypt với cùng CEK.
- Tag: **16 byte** (128 bit).
- Ciphertext + tag: với plaintext `N` byte trong JCA demo, thường là `N + 16` byte.
- AAD: byte mô tả ngữ cảnh, ví dụ `"hybrid-demo:v1|AES-256-GCM"`. AAD **được xác thực nhưng không được mã hóa**.

Không được tái sử dụng cùng cặp `(CEK, nonce)` trong AES-GCM. Một CEK mới ngẫu nhiên cho mỗi object giúp cô lập các object, nhưng vẫn cần cơ chế nonce phù hợp và chính sách giới hạn số lần encrypt nếu reuse key. Không dùng salt/password KDF làm nonce một cách tùy tiện.

### 5.3. Authentication tag bảo vệ điều gì?

Ở phía nhận, AES-GCM decryption kiểm tra tag với **khóa, nonce, AAD và ciphertext**. Nếu dữ liệu bị thay đổi, giải mã sẽ từ chối với lỗi tag trong trường hợp điển hình. Tuy nhiên:

- Không được đưa plaintext chưa xác minh vào hệ thống nghiệp vụ.
- Nếu ciphertext bị sửa, key sai, nonce sai hoặc AAD sai, tag có thể đều thất bại; không khẳng định exception chỉ ra nguyên nhân duy nhất.
- Tag đảm bảo tính toàn vẹn trong khuôn khổ CEK; **không chứng minh danh tính người gửi**, vì bất kỳ ai có public key người nhận đều có thể tự sinh CEK mới, tạo AES-GCM ciphertext/tag hợp lệ rồi wrap CEK bằng RSA-OAEP.

Khi cần **xác thực tác giả**, phải tích hợp chữ ký số (ví dụ Ed25519 hoặc RSA-PSS theo chính sách), một MAC đã phân phối khóa có xác thực, hoặc một giao thức bảo mật đã định nghĩa identity binding. Chữ ký nên xác thực **envelope hoặc nội dung ngữ nghĩa đầy đủ** (gồm version, thuật toán, keyId, wrappedKey, nonce, ciphertext/tag và context) theo serialization canonical rõ ràng.

## 6. Định dạng hybrid envelope cần lưu và truyền

Một envelope có thể mô tả logic như sau:

```json
{
  "formatVersion": 1,
  "recipientKeyId": "recipient-key-2026",
  "wrap": {
    "scheme": "RSAES-OAEP",
    "oaepHash": "SHA-256",
    "mgf": "MGF1",
    "mgfHash": "SHA-256",
    "labelEncoding": "UTF-8",
    "label": "hybrid-demo:v1|CEK",
    "wrappedKeyBase64Url": "<base64url-of-rsa-ciphertext>"
  },
  "data": {
    "scheme": "AES-256-GCM",
    "nonceBase64Url": "<base64url-of-12-byte-nonce>",
    "ciphertextAndTagBase64Url": "<base64url-of-ciphertext-plus-tag>"
  },
  "aadProfile": "hybrid-demo:v1|AES-256-GCM"
}
```

Đây là **sơ đồ JSON mô tả**, không phải một wire format được chuẩn hóa hay blob có thể giải mã ngay. Các token đặt trong dấu ngoặc nhọn chỉ là mô tả kiểu dữ liệu, không phải khóa thật. Một giao thức sản xuất phải chỉ định chính xác encoding, parser, quy tắc canonicalization và trường nào được xác thực.

Những mục tối thiểu cần nhất quán:

| Trường | Mục đích | Bí mật? | Quy tắc quan trọng |
| --- | --- | --- | --- |
| `formatVersion` | Chọn một profile chính xác | Không | Không thử nhiều version tùy tiện |
| `recipientKeyId` | Tra private key theo chính sách tin cậy | Không | Không để client tự buộc thuật toán yếu |
| OAEP hash/MGF1 hash/label | Giải RSA đúng thông số | Không | Giá trị byte phải khớp hoàn toàn |
| `wrappedCEK` | Bảo vệ CEK khi truyền/lưu | Không phải CEK thuần | Ciphertext RSA có độ dài modulus |
| GCM nonce | Tham số AES-GCM | Không | Không trùng với cùng CEK |
| `ciphertextAndTag` | Dữ liệu đã mã hóa + tag | Không cần bí mật riêng nếu crypto đúng | Phải giữ trọn tag; kiểm tra trước sử dụng |
| `AAD` hoặc profile tạo AAD | Ràng buộc metadata/ngữ cảnh | Không | Encrypt/decrypt dùng cùng byte AAD |
| CEK trước/sau unwrap | Khóa đối xứng dùng AES | **Có** | Không ghi plaintext key vào log, JSON, DB |
| RSA private key | Khôi phục CEK | **Có** | Bảo vệ quyền truy cập, lưu/chạy an toàn |

**Không thể chỉ lưu ciphertext rồi bỏ nonce hoặc OAEP parameters**; không có đủ dữ liệu và quy tắc để decrypt sau này. Khi format thay đổi, cần version để phân biệt.

### 6.1. AAD nên bao phủ metadata nào?

Trong ví dụ Java, AAD là hằng `"hybrid-demo:v1|AES-256-GCM"` để dễ kiểm chứng. Trong giao thức thật, nên xây dựng AAD theo một **canonical byte format** ràng buộc đủ những thuộc tính ảnh hưởng đến ý nghĩa dữ liệu, chẳng hạn:
- `formatVersion`, algorithm suite, lựa chọn digest, độ dài tag.
- `recipientKeyId`/id khóa tin cậy, domain của ứng dụng.
- Tenant, resourceId/documentId, loại nội dung, quyền sở hữu logic.
- Các header/framing field cần bảo vệ, gồm wrappedKey hoặc một hash/framing được quy định rõ nếu thiết kế yêu cầu.

Bên nhận phải tự tái tạo **đúng AAD bytes**, không lấy toàn bộ metadata không đáng tin rồi coi nó tự xác thực. Hợp đồng cần tránh ngụy biện “tag đã kiểm tra body” trong khi route, tenant hay algorithm version nằm ngoài miền bảo vệ.

Với protocol nhiều bên nhận, cần thiết kế key-wrap entries, binding recipient và xác thực danh sách các người nhận một cách rõ ràng. Không tự động cho thay thế wrappedKey hoặc chuyển recipient chỉ vì ciphertext data “trông giống”.

### 6.2. Nonce, label và salt không cùng vai trò

Ở đây:
- **OAEP label:** context byte ảnh hưởng đến OAEP decoding, không phải IV và không cần ngẫu nhiên.
- **GCM nonce:** tham số độc lập, với yêu cầu không được lặp dưới cùng AES key.
- **Salt:** thường xuất hiện trong KDF từ password hoặc secret khác; hybrid RSA-OAEP + CEK ngẫu nhiên **không bắt buộc salt KDF**. Đừng thêm salt chỉ vì nhìn thấy nó trong ví dụ password-based encryption.
- **Authentication tag:** thông tin kiểm tra AEAD, không phải một key và không thể bỏ qua để trả plaintext.

Tạo CEK và nonce bằng `SecureRandom`; không dùng `Random` hoặc thời gian hiện tại làm nguồn cho CEK. Không lấy một số từ `System.currentTimeMillis()` để làm “random secret”.

## 7. Java 17+: ví dụ hybrid encryption chạy được

Ví dụ này dùng toàn bộ JDK chuẩn:

- `KeyPairGenerator` sinh RSA key pair **2048 bit cho mục đích demo**.
- `Cipher` với `RSA/ECB/OAEPPadding` và **`OAEPParameterSpec` tường minh**: OAEP digest SHA-256, MGF1 digest SHA-256, label `hybrid-demo:v1|CEK`.
- `SecureRandom` tạo CEK AES-256 32 byte và nonce GCM 12 byte.
- `Cipher` với `AES/GCM/NoPadding`, tag 128 bit, AAD không đổi.
- Một plaintext **2.000 byte** được mã hóa bằng AES-GCM; RSA-OAEP chỉ mã hóa CEK 32 byte.
- Kiểm tra round-trip, phát hiện sửa ciphertext, từ chối sai OAEP label và từ chối RSA-OAEP mã hóa trực tiếp payload quá dài.

Tạo tệp **`HybridEncryptionDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.MGF1ParameterSpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import javax.crypto.spec.SecretKeySpec;

public class HybridEncryptionDemo {
    static final SecureRandom RNG = new SecureRandom();

    static final byte[] AAD =
            "hybrid-demo:v1|AES-256-GCM".getBytes(StandardCharsets.UTF_8);

    static OAEPParameterSpec spec(String label) {
        return new OAEPParameterSpec(
                "SHA-256",
                "MGF1",
                MGF1ParameterSpec.SHA256,
                new PSource.PSpecified(label.getBytes(StandardCharsets.UTF_8))
        );
    }

    static final OAEPParameterSpec OAEP = spec("hybrid-demo:v1|CEK");

    // For a simple demo only: records containing arrays are not immutable.
    record Packet(byte[] wrappedKey, byte[] nonce, byte[] ciphertextAndTag) {}

    static Packet encrypt(PublicKey publicKey, byte[] plaintext)
            throws GeneralSecurityException {
        byte[] cek = new byte[32];      // AES-256 content-encryption key
        byte[] nonce = new byte[12];    // AES-GCM 96-bit nonce

        RNG.nextBytes(cek);
        RNG.nextBytes(nonce);
        try {
            Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
            rsa.init(Cipher.ENCRYPT_MODE, publicKey, OAEP);
            byte[] wrapped = rsa.doFinal(cek);

            Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
            aes.init(
                    Cipher.ENCRYPT_MODE,
                    new SecretKeySpec(cek, "AES"),
                    new GCMParameterSpec(128, nonce)
            );
            aes.updateAAD(AAD);
            byte[] ciphertextAndTag = aes.doFinal(plaintext);
            return new Packet(wrapped, nonce, ciphertextAndTag);
        } finally {
            Arrays.fill(cek, (byte) 0);
        }
    }

    static byte[] decrypt(
            PrivateKey privateKey,
            Packet packet,
            OAEPParameterSpec parameters
    ) throws GeneralSecurityException {
        Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
        rsa.init(Cipher.DECRYPT_MODE, privateKey, parameters);
        byte[] cek = rsa.doFinal(packet.wrappedKey());

        try {
            if (cek.length != 32) {
                throw new GeneralSecurityException("Invalid CEK length");
            }

            Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
            aes.init(
                    Cipher.DECRYPT_MODE,
                    new SecretKeySpec(cek, "AES"),
                    new GCMParameterSpec(128, packet.nonce())
            );
            aes.updateAAD(AAD);
            return aes.doFinal(packet.ciphertextAndTag());
        } finally {
            Arrays.fill(cek, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator gen = KeyPairGenerator.getInstance("RSA");
        gen.initialize(2048, RNG);
        KeyPair recipient = gen.generateKeyPair();

        int modulusBytes =
                (((RSAPublicKey) recipient.getPublic()).getModulus().bitLength() + 7) / 8;
        int oaepMax = modulusBytes - 2 * 32 - 2;

        byte[] plaintext = new byte[2000];
        Arrays.fill(plaintext, (byte) 'A');

        Packet packet = encrypt(recipient.getPublic(), plaintext);
        byte[] recovered = decrypt(recipient.getPrivate(), packet, OAEP);

        System.out.println("RSA modulus bytes: " + modulusBytes);
        System.out.println("OAEP-SHA-256 plaintext limit: " + oaepMax);
        System.out.println("Payload bytes: " + plaintext.length);
        System.out.println("Wrapped CEK bytes: " + packet.wrappedKey().length);
        System.out.println("AES-GCM nonce bytes: " + packet.nonce().length);
        System.out.println("Ciphertext plus tag bytes: " + packet.ciphertextAndTag().length);
        System.out.println("Round trip: " + Arrays.equals(plaintext, recovered));

        byte[] tampered = packet.ciphertextAndTag().clone();
        tampered[0] ^= 1;
        boolean tamperRejected = false;
        try {
            decrypt(
                    recipient.getPrivate(),
                    new Packet(packet.wrappedKey(), packet.nonce(), tampered),
                    OAEP
            );
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        System.out.println("Tampered ciphertext rejected: " + tamperRejected);

        boolean wrongLabelRejected = false;
        try {
            decrypt(recipient.getPrivate(), packet, spec("wrong-context"));
        } catch (GeneralSecurityException expected) {
            wrongLabelRejected = true;
        }
        System.out.println("Wrong OAEP label rejected: " + wrongLabelRejected);

        boolean oversizedRejected = false;
        try {
            Cipher directRsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
            directRsa.init(Cipher.ENCRYPT_MODE, recipient.getPublic(), OAEP);
            directRsa.doFinal(plaintext);
        } catch (GeneralSecurityException expected) {
            oversizedRejected = true;
        }
        System.out.println("Oversized direct RSA rejected: " + oversizedRejected);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac HybridEncryptionDemo.java
java HybridEncryptionDemo
```

**Kết quả stdout:** (đã kiểm tra với JDK 24 qua JShell trên API tương thích Java 17; do RSA key pair, CEK và nonce đều sinh ngẫu nhiên nên không in ciphertext cụ thể):

```text
RSA modulus bytes: 256
OAEP-SHA-256 plaintext limit: 190
Payload bytes: 2000
Wrapped CEK bytes: 256
AES-GCM nonce bytes: 12
Ciphertext plus tag bytes: 2016
Round trip: true
Tampered ciphertext rejected: true
Wrong OAEP label rejected: true
Oversized direct RSA rejected: true
```

Trong đó:
- `OAEP-SHA-256 plaintext limit: 190` đến từ công thức `256 − 2 × 32 − 2`.
- `wrappedKey` có **256 byte** vì RSA modulus 2048 bit, dù CEK ban đầu chỉ 32 byte.
- `Ciphertext plus tag bytes: 2016` vì plaintext 2.000 byte và AES-GCM tag 16 byte; đây là output của `Cipher.doFinal` cho một bản tin không có padding thêm.
- `Round trip: true` chứng minh với cùng key pair, OAEP params, nonce/AAD và ciphertext hợp lệ thì nhận lại cùng byte plaintext.
- Sửa một bit của AES-GCM ciphertext dẫn đến **authentication tag không còn hợp lệ**, do đó việc giải mã bị từ chối.
- Dùng OAEP label `wrong-context` trong lúc decrypt không trùng label encrypt và không giải mã được wrapped CEK.
- Thử encrypt **toàn bộ 2.000 byte bằng RSA-OAEP** gây lỗi và được ghi nhận `true` ở dòng cuối. **Không** tự động cắt đầu vào thành 190 byte.

### 7.1. Những điểm Java quan trọng

**Khởi tạo RSA-OAEP với tham số tường minh:**

```java
Cipher rsa = Cipher.getInstance("RSA/ECB/OAEPPadding");
rsa.init(Cipher.ENCRYPT_MODE, publicKey, OAEP);
byte[] wrapped = rsa.doFinal(cek);
```

Hãy giữ cùng cấu hình OAEP khi decrypt. Trong Java, cấu hình bằng `OAEPParameterSpec` rõ ràng giúp tránh nhầm default giữa provider. MGF1-SHA-256 là một tham số độc lập với OAEP SHA-256 dù bài học chọn cùng hash.

**AES-GCM phải có nonce và tag:**

```java
Cipher aes = Cipher.getInstance("AES/GCM/NoPadding");
aes.init(
    Cipher.ENCRYPT_MODE,
    new SecretKeySpec(cek, "AES"),
    new GCMParameterSpec(128, nonce)
);
aes.updateAAD(AAD);
byte[] ciphertextAndTag = aes.doFinal(plaintext);
```

`GCMParameterSpec(128, nonce)` chỉ định **tag length 128 bit**, không chỉ định AES key length. AES-256 tới từ CEK 32 byte. Không nhầm tham số 128 của tag với việc dùng AES-128.

**Private key chỉ dùng ở receiver:**

```java
rsa.init(Cipher.DECRYPT_MODE, privateKey, OAEP);
byte[] cek = rsa.doFinal(packet.wrappedKey());
```

Không gửi private key qua network hoặc ghi cùng envelope. Public key phải được xác thực trước encrypt. Với hệ thống thật, private key có thể nằm trong KeyStore, HSM hoặc KMS và không nhất thiết export được ra byte.

**So sánh lỗi:** nếu OAEP unwrap thất bại, không có CEK để giải AES-GCM. Nếu unwrap thành công nhưng ciphertext/tag/AAD không phù hợp, AEAD sẽ từ chối. Đừng làm API public trả chi tiết có thể tạo padding oracle hoặc lộ thông tin về khả năng giải mã; cần xử lý lỗi và rate limit theo threat model.

### 7.2. Ranh giới demo và production

Ví dụ deliberately tối giản để học đúng hai trách nhiệm RSA-OAEP và AES-GCM; khi đem vào sản phẩm, cần xử lý thêm:

1. **Khóa RSA:** không tạo mỗi lần khởi động rồi mất private key nếu muốn giải mã dữ liệu lưu trữ lâu dài. Dùng keystore/HSM/KMS và chiến lược backup, rotation, hủy khóa theo chính sách.
2. **Chọn kích thước khóa:** 2048 bit nhằm demo nhanh; chọn 3072 bit hoặc profile khác khi chính sách/độ dài an ninh dữ liệu yêu cầu, dựa trên hướng dẫn cập nhật thay vì copy cứng số bit.
3. **Serialization:** `record Packet` mang `byte[]` có thể bị thay đổi từ bên ngoài. Trong hệ thống thật, dùng immutable copies, validate kích thước, encode/decode theo format chuẩn và giới hạn độ dài payload/envelope.
4. **AAD:** bài demo dùng hằng; nếu có header thay đổi (recipientKeyId, tenantId, resourceId), phải đưa vào AAD theo canonical schema hoặc bảo vệ toàn envelope bằng cơ chế tương đương.
5. **Độ dài/tag:** reader cần kiểm tra wrappedKey length khớp `k`, nonce 12 byte theo profile, có tag đủ độ dài, algorithm suite/version allowlist và không giải mã trước xác minh.
6. **Nonce lifecycle:** sinh nonce mới khi encrypt; tránh lặp cùng CEK. Nếu tái sử dụng CEK và gửi nhiều bản tin, quản lý uniqueness có trạng thái hoặc theo chuẩn phù hợp.
7. **Khóa tạm:** `Arrays.fill(cek,(byte)0)` giảm thời gian giữ bản sao mảng do chương trình sở hữu, nhưng không bảo đảm xóa mọi bản sao nằm trong provider/JVM. Không in CEK, plaintext bí mật, private key hoặc dump bộ nhớ vào log.
8. **Authenticated sender:** RSA-OAEP và AES-GCM trong ví dụ **không xác thực người gửi**. Bổ sung chữ ký/protocol với identity binding nếu yêu cầu.
9. **Đối tượng lớn và streaming:** không đưa toàn bộ file nhiều GB vào một mảng; cần API chunking/streaming được thiết kế đúng cho AEAD, giới hạn nonce/sequence, authentication của từng chunk và bảo vệ thứ tự/tổng số chunk. Không tự biến ví dụ một khối thành một scheme streaming không có spec.
10. **Lỗi từ bên ngoài:** validate framing/version/length trước crypto, trả lỗi không tiết lộ nguyên nhân nhạy cảm và không thử fallback xuống RSA PKCS#1 v1.5 chỉ vì OAEP failed.

## 8. Một ví dụ thiết kế ứng dụng gửi tệp cho người nhận

Giả sử ứng dụng upload một file 10 MiB chỉ người dùng B được đọc.

### 8.1. Quy trình đề xuất

**Bước 1: Xác minh public key của B.** Lấy certificate hoặc public-key mapping từ nguồn đáng tin; kiểm tra identity/keyId và policy. Nếu key bị tráo, tất cả bảo vệ của các bước sau có thể vẫn hoạt động **đối với kẻ tấn công**, không phải B.

**Bước 2: Sinh CEK mới.** Sender dùng CSPRNG tạo 32 byte CEK; không dùng password ngắn hay thời gian để thay CEK.

**Bước 3: Sinh nonce AEAD.** Tạo nonce theo profile AES-GCM; nếu mỗi file có CEK riêng, một nonce ngẫu nhiên 96 bit cho một message là pattern demo hợp lý, nhưng độ bảo đảm uniqueness phải được đánh giá theo số lượng encrypt và chính sách.

**Bước 4: Mã hóa file bằng AES-GCM.** Chọn AAD ràng buộc format version, fileId, chủ sở hữu, context. Nhận ciphertext + tag. Với file lớn, dùng thư viện streaming AEAD có spec phù hợp, không tự mã hóa từng chunk rồi ghép một cách không xác thực.

**Bước 5: Wrap CEK cho B bằng RSA-OAEP.** Khóa cần wrap là 32 byte, thấp hơn giới hạn 190 byte của RSA-2048 OAEP SHA-256. Chuẩn hóa OAEP digest, MGF1 digest và label.

**Bước 6: Lưu một envelope.** Bao gồm metadata cần thiết, wrappedCEK, nonce, ciphertext/tag, version và AAD profile. Không lưu CEK thuần hoặc private key cùng envelope.

**Bước 7: Recipient B giải mã.** B chọn private key đáng tin, unwrap CEK qua RSA-OAEP, decrypt AES-GCM, kiểm tra tag rồi mới sử dụng plaintext. Nếu sai, từ chối; không bỏ qua tag hoặc “thử một cipher khác” tùy tiện.

**Bước 8: Kiểm tra người gửi nếu có yêu cầu.** Nếu ứng dụng còn muốn B biết file thực sự do A gửi, bổ sung chữ ký A trên envelope được canonicalize và xác minh chứng thư/key của A, hoặc tích hợp một giao thức authenticated encryption dành cho nhiều bên theo chuẩn.

### 8.2. Chi phí kích thước

Với file 10 MiB (10 × 1.048.576 byte), AES-GCM với tag 16 byte thêm lượng nhỏ cho một bản tin (chưa tính nonce/header). RSA-OAEP ciphertext wrap một CEK chỉ thêm **256 byte** nếu modulus là 2048 bit.

Ngược lại, chia một file thành các block OAEP 190 byte và encrypt mỗi block sẽ phải tạo rất nhiều RSA ciphertext 256 byte, vừa tốn CPU vừa tăng overhead lớn. Không có lý do vận hành tốt để chọn block-RSA thay cho CEK + AES-GCM trong ứng dụng mã hóa tệp thông thường.

## 9. RSA-OAEP không cung cấp tất cả bảo đảm của một kênh an toàn

### 9.1. Confidentiality không đồng nghĩa sender authentication

RSA-OAEP giúp chỉ private key tương ứng có thể lấy lại CEK (theo giả định an ninh và quản lý khóa đúng). Tuy nhiên ai biết public key đều có thể:
- tự sinh CEK,
- tự mã hóa thông điệp với AES-GCM,
- tự wrap CEK bằng public key,
- gửi một envelope giải mã hợp lệ.

Vì vậy, người nhận không thể suy ra “A chắc chắn đã gửi” chỉ từ việc decrypt thành công. Thêm chữ ký số/cert/identity binding, hoặc sử dụng một protocol hoàn chỉnh có tính xác thực nguồn.

Một hybrid envelope không có chữ ký cũng không phải “bảo đảm chống replay”. Đối thủ có thể lưu lại một envelope hợp lệ rồi gửi lại; phía nhận cần id, timestamp, nonce/replay tracking và policy nghiệp vụ nếu hành động lặp nguy hiểm.

### 9.2. Forward secrecy và lộ private key sau này

Trong mô hình **RSA-OAEP wrap CEK** lưu kèm ciphertext, nếu một ngày RSA private key của B bị lộ, attacker đã thu thập được các wrappedCEK trước đó có thể unwrap CEK rồi giải mã các ciphertext lịch sử. Đây **không phải** một mô hình mặc nhiên có perfect forward secrecy.

Nếu hệ thống cần bảo vệ quá khứ trước việc lộ long-term key, cần một thiết kế **ephemeral key agreement/authenticated KEM** hoặc giao thức có forward secrecy được chứng minh và quản lý vòng đời khóa phù hợp. Không gắn nhãn “PFS” cho RSA-OAEP hybrid chỉ vì CEK ngẫu nhiên mỗi file.

### 9.3. Chống thay thế public key là một yêu cầu riêng

Một attacker làm giả kho public key có thể thay key B bằng key của attacker trước lúc sender encrypt. Khi đó ciphertext được mã hóa đúng bằng một key RSA, AES-GCM vẫn hợp lệ, nhưng attacker chính là người có thể unwrap. Không có phương trình OAEP nào tự kiểm tra tên B. Key authenticity phải đến từ PKI hoặc cơ chế tin cậy ngoài RSA encryption.

### 9.4. RSA-OAEP decryption cần xử lý lỗi kín

Không thiết kế endpoint cho phép người lạ gửi vô hạn wrappedKey rồi quan sát những lỗi quá chi tiết, thời gian phản hồi hoặc việc server có tiếp tục tới AES-GCM hay không. Chỉ dùng provider crypto đã có các biện pháp thích hợp, giới hạn request và thống nhất mức thông tin lỗi trong API public.

Không tự viết RSA raw modular exponentiation để “debug padding” trên input không tin cậy; không chuyển qua `RSA/ECB/PKCS1Padding` khi OAEP thất bại. Các kiểu oracle kiểu Bleichenbacher/padding oracle là lý do phải nghiêm túc với việc dùng API và giao thức phù hợp.

## 10. Các lỗi phổ biến và cách sửa

| Ngộ nhận/thiết kế | Tại sao sai | Hướng đúng |
| --- | --- | --- |
| “RSA-2048 mã hóa trực tiếp 256 byte plaintext” | 256 là ciphertext/modulus byte count; OAEP SHA-256 còn overhead | Dùng `max = k - 2hLen - 2`, ví dụ 190 byte |
| “String có 190 ký tự là dưới giới hạn” | OAEP nhận UTF-8 bytes, không phải Java UTF-16 length | Tính `getBytes(UTF_8).length` |
| “Chia file thành nhiều RSA blocks rồi ghép” | Chậm, phình kích thước, không bảo vệ framing/integrity file đúng cách | RSA-OAEP wrap CEK, AES-GCM encrypt bulk |
| “Dùng raw RSA/no padding cho nhanh” | Không phải encryption scheme an toàn | RSAES-OAEP qua thư viện chuẩn |
| “Hai bên cùng nói SHA-256 OAEP là đủ” | MGF1 digest/label có thể khác | Ghi rõ `OAEPParameterSpec`, test interop |
| “OAEP label là IV ngẫu nhiên” | Label là context công khai; IV/nonce của AEAD là tham số khác | Giữ đúng label byte và nonce riêng |
| “Dùng RSA OAEP encryption để chứng minh A gửi” | Bất cứ ai có public key B đều encrypt được | Dùng chữ ký/identity binding riêng |
| “AES-GCM không cần tag nếu plaintext trông đúng” | Mất kiểm tra toàn vẹn, dễ chấp nhận bản rõ bị sửa | Kiểm tra tag bắt buộc, fail closed |
| “Có GCM tag nên mọi envelope metadata đều an toàn” | Chỉ dữ liệu được bind vào AAD/ciphertext mới được kiểm tra | Canonicalize/bind các field có ý nghĩa |
| “AES-GCM có thể lặp nonce miễn plaintext khác” | Reuse cùng key/nonce là lỗi nghiêm trọng | Enforce nonce uniqueness dưới cùng key |
| “Mã hóa file bằng public key bất kỳ là đủ” | Attacker tráo public key → decrypt được | Xác thực key thuộc người nhận |
| “Tạo key pair mỗi lần chạy vẫn mở được file cũ” | Mất private key → không unwrap được CEK | Persist bảo vệ và backup/rotation theo policy |
| “Sai OAEP thì thử PKCS1 v1.5 fallback” | Làm yếu chính sách, có thể tạo oracle | Từ chối rõ theo version, không downgrade |
| “Random CEK nghĩa là có forward secrecy” | Long-term RSA private key bị lộ có thể unwrap quá khứ | Chọn protocol ephemeral phù hợp nếu cần PFS |
| “WrappedCEK là bí mật không được lưu” | Wrapped key là RSA ciphertext cần lưu/truyền | Lưu wrappedCEK, không lưu CEK thuần |
| “GCMParameterSpec(128) nghĩa là AES-128” | 128 là tag bit length; key length do CEK | Dùng CEK 32 byte cho AES-256 |
| “RSA có thể streaming trực tiếp dữ liệu lớn” | Một OAEP operation chỉ chứa payload rất nhỏ | Streaming/AEAD format chuẩn cho file |
| “Mã hóa lai là RSA-KEM bất kể scheme nào” | OAEP key transport khác RSA-KEM | Gọi đúng scheme, không trộn byte format |

## 11. Các tình huống thực hành để phân loại

**Tình huống A — API payload 8 KiB cần lưu bí mật cho một người nhận.** RSA-2048 OAEP SHA-256 giới hạn 190 byte, nên không encrypt payload trực tiếp. Hãy tạo CEK AES ngẫu nhiên, mã hóa JSON bằng AES-GCM và wrap CEK bằng RSA-OAEP. Bảo vệ AAD của context, xác thực recipient public key.

**Tình huống B — Client muốn gửi khóa AES-256 (32 byte) cho server.** RSA-OAEP có thể encrypt 32 byte CEK vì 32 ≤ 190. Cần đúng OAEP hash/MGF1/label, public key đã xác thực, envelope version và giải AES-GCM an toàn. Nhưng nếu mục đích là truyền API qua mạng thông thường, hãy cân nhắc **TLS được cấu hình đúng** thay vì tự xây application protocol nếu không cần encryption at rest riêng.

**Tình huống C — Sender và recipient đều dùng RSA-OAEP SHA-256 nhưng decryption thất bại.** Hãy kiểm tra MGF1 digest, OAEP label bytes, key pair, ciphertext encoding (hex/Base64/byte length), provider restrictions và format version. Không tự động đổi về SHA-1 hoặc RSA PKCS1 v1.5 để “thử”.

**Tình huống D — Ciphertext GCM bị sửa một byte.** Receiver vẫn có thể unwrap CEK hợp lệ, nhưng AES-GCM tag sẽ không khớp khi decrypt, nên reject. Không dùng plaintext chưa verify; không suy ra chính xác ai đã sửa và khi nào chỉ từ tag.

**Tình huống E — Wrapped CEK bị sửa một byte.** OAEP decryption rất có thể bị từ chối; hoặc nếu nhận được một CEK không phù hợp theo giả định cực hiếm, AES-GCM tag vẫn không khớp. Không nên dựa vào lỗi OAEP chi tiết để trả thông tin về private key cho client.

**Tình huống F — Lộ private key B sau năm năm.** Attacker đã lưu hybrid envelopes cũ có thể giải mã lại các wrappedCEK bằng key đó, nên dữ liệu lịch sử có thể bị ảnh hưởng. Các envelope chỉ dùng RSA-OAEP không tự có forward secrecy.

**Tình huống G — B nhận được một hybrid envelope decrypt hợp lệ, không có chữ ký.** B biết ciphertext/AAD phù hợp với CEK và định dạng, không biết chắc nguồn gửi A; mọi bên có public key B cũng có thể tạo một envelope như vậy.

**Tình huống H — Một file 50 GiB, muốn mã hóa theo chunks.** Không lặp RSA-OAEP cho từng chunk; xây dựng protocol AEAD streaming đã chuẩn hóa, mỗi chunk có nonce/sequence riêng, xác thực thứ tự và điểm kết thúc, rồi wrap một hoặc nhiều CEK theo đúng cấu trúc khóa. Không lấy code demo byte[] làm giải pháp streaming hoàn chỉnh.

## 12. Câu hỏi tự kiểm tra

**1. RSA-2048, OAEP SHA-256, plaintext tối đa là bao nhiêu byte?**  
**Đáp án:** `k=256`, `hLen=32` nên `mLen ≤ 256−64−2 = 190` byte.

**2. RSA-3072 với OAEP SHA-512 thì giới hạn là bao nhiêu?**  
**Đáp án:** `k=384`, `hLen=64`, giới hạn `384−128−2 = 254` byte.

**3. RSA ciphertext của CEK 32 byte dưới RSA-2048 dài bao nhiêu?**  
**Đáp án:** 256 byte; chiều dài ciphertext OAEP theo modulus, không bằng chiều dài CEK.

**4. Vì sao RSA-OAEP không được dùng để encrypt thẳng file 1 MiB?**  
**Đáp án:** Mỗi operation OAEP chỉ chứa payload ngắn, RSA tốn CPU và không thay thế AEAD bảo vệ toàn tệp. Dùng CEK ngẫu nhiên và AES-GCM cho dữ liệu, RSA-OAEP wrap CEK.

**5. Hai bên chọn OAEP hash SHA-256, nhưng sender MGF1-SHA-256 còn receiver MGF1-SHA-1. Có giải mã được không?**  
**Đáp án:** Không theo cùng bộ tham số. OAEP và MGF1 digest cần trùng đúng; chỉ nói “OAEP SHA-256” có thể chưa đủ mô tả interoperable spec.

**6. OAEP label `L` có phải được giữ bí mật?**  
**Đáp án:** Không; nó là context byte tùy chọn. Tuy nhiên encrypt và decrypt phải dùng cùng label và cùng encoding.

**7. RSA-OAEP + AES-GCM có chứng minh A là người gửi không?**  
**Đáp án:** Không. Người có public key B bất kỳ cũng tạo được envelope cho B. Muốn sender authentication cần ký/chứng thực nguồn hoặc protocol phù hợp.

**8. Mất GCM nonce nhưng còn private RSA key và wrapped CEK, có giải mã được file không?**  
**Đáp án:** Không thể khôi phục đúng bằng quy trình chuẩn nếu thiếu nonce cần cho GCM decryption; phải lưu nonce/metadata cần thiết.

**9. Nếu RSA private key bị lộ trong tương lai, dữ liệu cũ có PFS chỉ vì mỗi file dùng CEK mới không?**  
**Đáp án:** Không. WrappedCEK cũ được encrypt bằng cùng RSA public key có thể bị unwrap bởi private key bị lộ; cần ephemeral protocol phù hợp nếu yêu cầu forward secrecy.

**10. Trong Java, tại sao `GCMParameterSpec(128, nonce)` không nói rằng AES-128 đang được dùng?**  
**Đáp án:** `128` là độ dài tag tính bằng bit. Khóa AES được quyết định bởi số byte CEK; CEK 32 byte nghĩa là AES-256.

**11. Nếu encrypt cùng CEK với cùng GCM nonce cho hai plaintext khác nhau thì sao?**  
**Đáp án:** Vi phạm nghiêm trọng yêu cầu nonce uniqueness của GCM và có thể làm suy yếu tính bí mật/toàn vẹn; cần thiết kế quản lý nonce đúng.

**12. Có thể đổi algorithm từ OAEP sang PKCS#1 v1.5 nếu một bản tin giải mã thất bại không?**  
**Đáp án:** Không. Hợp đồng algorithm/version phải cố định, có allowlist, chống downgrade và xử lý lỗi an toàn.

## 13. Checklist triển khai RSA-OAEP hybrid trước khi phát hành

### Bên gửi

- [ ] Đã xác thực public key thuộc đúng recipient, kiểm tra vòng đời/thu hồi/algorithm policy.
- [ ] Đã thống nhất RSA modulus, OAEP hash, MGF1 digest, label encoding và version.
- [ ] Dùng `SecureRandom` tạo **CEK ngẫu nhiên 32 byte** hoặc key size theo cipher được phép.
- [ ] Dùng AEAD phù hợp (ví dụ AES-GCM) với nonce policy an toàn, AAD đã ràng buộc context.
- [ ] RSA-OAEP chỉ encrypt CEK/payload ngắn trong giới hạn `k - 2hLen - 2`.
- [ ] Lưu/truyền wrappedCEK, nonce, ciphertext, tag, version, keyId và metadata cần thiết.
- [ ] Không log CEK/private data; xóa bản sao mảng byte có thể xóa theo best effort.
- [ ] Nếu cần biết tác giả, đã có chữ ký/identity binding bên ngoài confidentiality.

### Bên nhận

- [ ] Áp allowlist version/cipher/keyId, kích thước envelope, và không downgrade khi lỗi.
- [ ] Lấy đúng private key đã cấp phép từ KeyStore/KMS/HSM, không nhận private key từ payload.
- [ ] Kiểm tra đúng OAEP digest + MGF1 digest + label; xem xét opaque error responses.
- [ ] Unwrap CEK, kiểm tra key length và data encryption algorithm đúng profile.
- [ ] Kiểm tra nonce, AAD và authentication tag; không dùng plaintext khi tag chưa hợp lệ.
- [ ] Kiểm tra sender/tenant/resource/authorization/replay theo yêu cầu nghiệp vụ.
- [ ] Không trả lỗi giải mã quá chi tiết tạo oracle hoặc rò rỉ metadata nhạy cảm.
- [ ] Có kế hoạch key rotation, backup và khả năng giải mã dữ liệu lịch sử theo quyền.

### Kiểm thử liên thông và security regression

- [ ] RSA 2048 OAEP SHA-256: encrypt CEK 32 byte thành công; thử plaintext 190 byte thành công, 191 byte bị từ chối.
- [ ] Wrong label / wrong MGF1 digest / wrong private key / malformed wrappedKey bị từ chối.
- [ ] Sai/cắt tag AES-GCM, thay đổi AAD/nonce/ciphertext bị từ chối.
- [ ] Cùng plaintext encrypt hai lần có thể tạo ciphertext khác do randomness.
- [ ] Key rotation và giải mã dữ liệu lưu trữ xử lý đúng version/keyId.
- [ ] JSON/CBOR/binary encoding, Base64URL, byte order, nonce/tag lengths có golden vectors giữa hai bên.
- [ ] Kiểm tra flow danh tính, quyền, key substitution và replay riêng khỏi việc cryptography “pass test”.
- [ ] Kiểm tra giới hạn file, streaming/chunk framing, áp lực memory/CPU và side-channel/error behavior.

## 14. Ghi nhớ bằng một sơ đồ

```text
                  RSA-OAEP SHA-256 (RSA-2048)
                  max plaintext = 190 bytes
                          |
                     CEK 32 bytes  <---- SecureRandom
                          |
         +----------------+--------------------+
         |                                     |
    RSA-OAEP(public)                       AES-256-GCM
         |                              + nonce 12 bytes
    wrappedCEK 256 bytes                 + AAD + plaintext
         |                                     |
         +----------------+--------------------+
                          |
                   Hybrid envelope
               [wrappedCEK, nonce,
                ciphertext+tag, metadata]
                          |
               RSA-OAEP(private) -> CEK
                          |
              AES-GCM decrypt + verify tag
                          |
                       Plaintext

  Key principle:
  RSA protects a short symmetric key;
  AEAD protects large data and authenticates ciphertext/AAD.
  Neither alone proves who sent the message.
```

**Kết luận:** RSA-OAEP có giới hạn bản rõ nhỏ và được dùng đúng nhất cho **thông điệp ngắn hoặc khóa đối xứng**, không phải để mã hóa hàng nghìn khối dữ liệu trực tiếp. Với RSA-2048/OAEP SHA-256, giới hạn là **190 byte**, đủ để wrap một CEK AES-256 dài 32 byte. Mã hóa lai kết hợp **RSA-OAEP cho khóa** và **AEAD cho dữ liệu** giải quyết tốt yêu cầu dung lượng, hiệu năng và toàn vẹn. Một thiết kế hoàn chỉnh còn phải có **định dạng, tham số OAEP, trust của public key, binding metadata, quản lý nonce và chính sách xác thực/ngăn replay** rõ ràng.

### Tài liệu tham khảo

- RFC 8017, *PKCS #1: RSA Cryptography Specifications Version 2.2* — RSAES-OAEP, công thức `mLen ≤ k−2hLen−2` và encoding: https://www.rfc-editor.org/rfc/rfc8017
- NIST SP 800-56B Rev. 2 — các phương pháp thiết lập khóa dựa trên integer-factorization cryptography: https://csrc.nist.gov/pubs/sp/800/56/b/r2/final
- NIST SP 800-38D — GCM/GMAC, AEAD nonce và tag: https://csrc.nist.gov/pubs/sp/800/38/d/final
- NIST SP 800-57 Part 1 Rev. 5 — quản lý khóa và ước lượng độ mạnh khóa: https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- Java SE 17, `OAEPParameterSpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/OAEPParameterSpec.html
- Java SE 17, `MGF1ParameterSpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html
- Java SE 17, `Cipher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Cipher.html
- Java SE 17, `GCMParameterSpec`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/spec/GCMParameterSpec.html
- Java SE 17, `SecureRandom`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html
