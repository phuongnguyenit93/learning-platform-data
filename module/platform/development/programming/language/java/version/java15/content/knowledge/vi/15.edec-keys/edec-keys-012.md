# Khóa EdEC: kiểm thử khóa sai loại, dữ liệu cắt cụt và encoding sai trong Java 15+

## 1. Mục tiêu của bài

Khi ứng dụng dùng **EdDSA** để ký và xác minh thông điệp, rất nhiều lỗi không nằm ở thuật toán ký mà nằm ở dữ liệu đầu vào: gửi nhầm khóa X25519 thay cho Ed25519, dùng khóa Ed448 cho bộ xác minh Ed25519, cắt mất một byte khi truyền chữ ký, lưu sai định dạng public/private key, hoặc đổi encoding của thông điệp giữa bên ký và bên xác minh.

Java 15 cung cấp các API EdDSA/EdEC chuẩn từ **JEP 339**; Ed25519/Ed448, `java.security.Signature`, `java.security.KeyFactory`, `java.security.interfaces.EdECPublicKey`, `EdECPrivateKey` và các key specification liên quan vẫn còn áp dụng trên JDK hiện đại. Bài tập trung vào **kiểm thử âm tính (negative testing)** và xử lý lỗi an toàn, không dùng API legacy hoặc mẹo sửa byte không có đặc tả.

Sau bài học, bạn có thể:

- Phân biệt **khóa đúng thuật toán**, **khóa đúng đường cong nhưng sai cặp**, và **khóa sai mục đích**.
- Kiểm thử trường hợp `Ed25519` so với `Ed448`, `Ed25519` so với `X25519`, và public key khác cặp.
- Biết `X509EncodedKeySpec` phải nhận **SubjectPublicKeyInfo** của public key; `PKCS8EncodedKeySpec` phải nhận **PKCS#8** của private key, không nhận tùy tiện 32 byte thô.
- Cố ý cắt cụt chữ ký, public/private key DER và xác nhận code **không bao giờ chấp nhận** dữ liệu lỗi.
- Nhận ra sai encoding **Base64 thường/Base64 URL-safe**, **UTF-8/UTF-16LE**, ký tự xuống dòng, Unicode normalization và PEM framing.
- Phân biệt trường hợp `Signature.verify(...)` trả `false` với trường hợp báo `SignatureException`, `InvalidKeyException`, `InvalidKeySpecException` hoặc `IllegalArgumentException`.
- Chạy một chương trình Java 15 độc lập có **15 dòng kết quả đã kiểm chứng thực tế**, không phụ thuộc framework test.

**Phạm vi bảo mật:** Các ca kiểm thử giúp phát hiện lỗi sử dụng khóa/format, **không tự chứng minh public key thuộc đúng danh tính**. Chữ ký EdDSA cung cấp tính toàn vẹn và xác thực theo một public key *đã tin cậy*; cần cơ chế PKI, pinning hoặc phân phối khóa được xác thực để khẳng định danh tính thực.

## 2. Phân loại đúng trước khi kiểm thử

### 2.1. EdDSA và XDH là hai mục đích khác nhau

| Thuật toán | Loại primitive | Java API | Có dùng để xác minh Ed25519 trực tiếp? |
| --- | --- | --- | --- |
| **Ed25519** | Chữ ký EdDSA | `Signature.getInstance("Ed25519")` | **Có**, với đúng Ed25519 public key |
| **Ed448** | Chữ ký EdDSA | `Signature.getInstance("Ed448")` | **Không**, tham số curve/loại khóa khác |
| **X25519** | Thỏa thuận khóa XDH | `KeyAgreement.getInstance("X25519")` | **Không**, đây là key agreement, không phải EdDSA |
| **X448** | Thỏa thuận khóa XDH | `KeyAgreement.getInstance("X448")` | **Không**, đây là key agreement |

Dù cùng số “25519”, **Ed25519 không phải X25519**. Không thể chỉ đổi tên thuật toán rồi đưa `XECPublicKey` vào `Signature.initVerify(...)` của Ed25519. Cũng không thể lấy Ed25519 private signing key làm tham số trực tiếp cho `KeyAgreement` của X25519.

Các thuật toán EdDSA nhận **private key khi ký**, **public key khi xác minh**. Public key của **một cặp Ed25519 khác** vẫn đúng loại và đúng curve, nhưng không tương ứng với chữ ký của cặp gốc: phép xác minh phải thất bại. Đây là một ca kiểm thử khác bản chất với **khóa sai loại**.

### 2.2. EdEC trong Java là gì?

EdEC là các interface/spec cho khóa trên Edwards curves trong JCA:

- `java.security.interfaces.EdECPublicKey`: biểu diễn public key EdDSA; cho phép xem `getParams()` và `getPoint()`.
- `java.security.interfaces.EdECPrivateKey`: biểu diễn private key EdDSA; có `getParams()` và `getBytes()` trả về `Optional<byte[]>`. Không giả định provider hoặc HSM sẽ cho phép xuất seed bí mật.
- `java.security.spec.NamedParameterSpec.ED25519` và `ED448`: định danh các bộ tham số EdDSA; các hằng này được thêm từ Java 15.
- `EdECPublicKeySpec` / `EdECPrivateKeySpec`: mô tả khóa theo **tham số và thành phần toán học**. Không phải parser tổng quát của PKCS#8 hoặc X.509 DER.

Để kiểm tra đúng curve trên một khóa hỗ trợ EdEC interface:

```java
import java.security.interfaces.EdECPublicKey;
import java.security.spec.NamedParameterSpec;

// Đoạn minh họa trong phương thức đã có PublicKey publicKey.
if (!(publicKey instanceof EdECPublicKey)) {
    throw new IllegalArgumentException("Not an EdEC public key");
}
EdECPublicKey ed = (EdECPublicKey) publicKey;
String curve = ed.getParams().getName();
if (!NamedParameterSpec.ED25519.getName().equals(curve)) {
    throw new IllegalArgumentException("Expected Ed25519, got " + curve);
}
```

**Đây là kiểm tra schema/loại khóa, không phải xác thực chữ ký.** Mọi xác minh vẫn phải thực hiện `Signature.verify(...)` trên dữ liệu thực. Nếu dùng provider có đối tượng khóa khác cách triển khai hoặc khóa không xuất được, hãy xem hợp đồng giao diện/provider trước khi ép kiểu; không đánh đồng `getAlgorithm()` dạng chữ với thông tin curve đã kiểm chứng.

## 3. Chọn đúng các lớp JCA khi nhập khóa

Có hai khái niệm dễ nhầm:

1. **Key material**: thành phần toán học/raw bytes của một khóa.
2. **Encoded key**: cấu trúc chứa khóa **và thông tin thuật toán**, theo một encoding được định nghĩa (ví dụ ASN.1 DER).

Trong Java:

```java
KeyPair keyPair = KeyPairGenerator.getInstance("Ed25519")
        .generateKeyPair();

byte[] publicDer = keyPair.getPublic().getEncoded();
byte[] privateDer = keyPair.getPrivate().getEncoded();

KeyFactory factory = KeyFactory.getInstance("Ed25519");
PublicKey importedPublic =
        factory.generatePublic(new X509EncodedKeySpec(publicDer));
PrivateKey importedPrivate =
        factory.generatePrivate(new PKCS8EncodedKeySpec(privateDer));
```

Đây là đoạn **minh họa**, cần các import `java.security.*`, `java.security.spec.*` và nằm trong phương thức xử lý exception. Ví dụ độc lập ở mục 8 kiểm tra kết quả import public/private key đúng format.

| Đối tượng / cách ghi | Định dạng | Có phải chỉ 32 byte raw Ed25519? |
| --- | --- | --- |
| `publicKey.getEncoded()` của JDK provider hỗ trợ xuất | Thường là **X.509 SubjectPublicKeyInfo** (SPKI) | **Không**; chứa phần mô tả thuật toán |
| `privateKey.getEncoded()` của JDK provider hỗ trợ xuất | Thường là **PKCS#8** | **Không**; chứa ASN.1 bọc key |
| `X509EncodedKeySpec(bytes)` | Yêu cầu **SPKI encoding** public key | Không lấy raw public bytes rồi gắn nhãn X.509 |
| `PKCS8EncodedKeySpec(bytes)` | Yêu cầu **PKCS#8 encoding** private key | Không lấy 32-byte seed rồi gắn nhãn PKCS#8 |
| `EdECPublicKeySpec(params, point)` | Thành phần point và curve | Không phải blob DER; phải xây đúng tọa độ/bit |
| `EdECPrivateKeySpec(params, bytes)` | Thông số curve + private key bytes tương ứng | Không phải PKCS#8 ASN.1 container |
| `Base64 string` / PEM | **Lớp chuyển tải/armoring** bên ngoài bytes | Không đồng nghĩa khóa đã hợp lệ |

Theo **RFC 8410**, Ed25519 có OID `1.3.101.112`, Ed448 có `1.3.101.113`; X25519/X448 dùng các OID khác. Thông tin nhận dạng này nằm trong cấu trúc ASN.1 phù hợp. Không tự cắt phần đầu DER theo một độ lệch cố định rồi dùng nó như public key “không cần header”.

**Kết quả quan sát của JDK provider trong bài thử:** public key Ed25519 có `getFormat() == "X.509"`, private key có `getFormat() == "PKCS#8"`, và public/private encoded lần lượt có độ dài **44/48 byte**. Đây là kết quả kiểm chứng với **khóa do provider tạo trong bài**, không phải quy tắc “mọi public key luôn dài 44 byte”. Raw Ed25519 public key chuẩn dài 32 byte, nhưng SPKI **không chỉ** chứa 32 byte đó. Với HSM/non-exportable key, `getEncoded()` còn có thể là `null`.

### Không nhầm X.509 public key với X.509 certificate

Một blob `SubjectPublicKeyInfo` (SPKI) thuộc hệ sinh thái X.509, **không** phải cả tệp chứng thư X.509. Tệp `-----BEGIN CERTIFICATE-----` là đối tượng chứng thư; nếu muốn trích public key từ certificate, phải parse và kiểm tra chứng thư/chain theo nhu cầu rồi gọi `certificate.getPublicKey()`. Không đưa toàn bộ DER của certificate trực tiếp vào `X509EncodedKeySpec` để “import public key”.

Nếu private key được lưu dưới dạng `-----BEGIN ENCRYPTED PRIVATE KEY-----`, dữ liệu bên trong được mã hóa; phải dùng quy trình giải mã được xác thực/cấu hình phù hợp trước khi tạo `PrivateKey`. `PKCS8EncodedKeySpec` **không phải bộ giải mã mật khẩu tự động**.

## 4. Nhóm kiểm thử 1: khóa sai loại và sai cặp

### 4.1. Dùng Ed448 hoặc X25519 key để xác minh Ed25519

`Signature.initVerify(PublicKey)` phải dùng public key tương thích với thuật toán `Signature`. Nếu yêu cầu Ed25519 nhưng truyền public key Ed448 hoặc X25519, provider thông thường ném **`InvalidKeyException`** vì khóa không phù hợp. Không bắt `InvalidKeyException` rồi **thử lại một thuật toán khác cho đến khi thành công**: việc tự đoán thuật toán theo input không tin cậy có thể tạo lỗi thương lượng hoặc sai policy.

Ví dụ lý thuyết:

```java
Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(ed448KeyPair.getPublic()); // InvalidKeyException
```

Đây là **mã minh họa một ca lỗi**, giả sử đã có `ed448KeyPair`; khi chạy thật phải tách test lỗi ra khỏi happy path.

### 4.2. Đúng Ed25519 nhưng sai public key

Giả sử Alice ký bằng `alice.getPrivate()`; Bob lại xác minh bằng `anotherEd25519.getPublic()` của cặp khóa khác. Cả hai public keys đều là Ed25519 hợp lệ. Quá trình `initVerify` vẫn có thể thành công, nhưng chữ ký không khớp thì `verify(signature)` trả về **`false`**.

Đây là test quan trọng để phát hiện:
- Nhầm tenant/user hoặc key-id trong kho khóa.
- Sử dụng khóa từ phiên trước/sau khi xoay vòng khóa.
- Gắn public key đúng thuật toán nhưng sai danh tính.

**Thành công với đúng thuật toán chưa đồng nghĩa đúng người ký**: cần thêm mapping key-id → public key tin cậy, bảo vệ mapping và kiểm soát lifecycle, revocation và rotation.

### 4.3. Nhầm chiều ký/xác minh

- `Signature.initSign(...)` cần `PrivateKey`; `initVerify(...)` cần `PublicKey`.
- Không thể ký hợp lệ bằng public key hoặc xác minh bằng private key chỉ nhờ ép kiểu Java.
- Không chuyển Ed25519 sang X25519 bằng cách cast hay đổi chuỗi `algorithm` trong Java.
- Không xem `getAlgorithm()` là bộ kiểm tra bảo mật duy nhất; hãy kiểm tra loại key, tham số curve, nguồn tin cậy và thao tác ký/xác minh thực.

## 5. Nhóm kiểm thử 2: dữ liệu cắt cụt hoặc sai cấu trúc

Có ba lớp dữ liệu khác nhau có thể bị cắt cụt:

| Dữ liệu bị cắt | Dấu hiệu | Cơ chế kiểm tra đúng |
| --- | --- | --- |
| **Signature** Ed25519 | Mất byte cuối/giữa, chữ ký không đủ cấu trúc hoặc không xác minh được | `Signature.verify` trả `false` **hoặc ném `SignatureException`** với chữ ký malformed |
| **Public key SPKI** | ASN.1 DER bị thiếu byte, length field không khớp, OID/bit string hỏng | `KeyFactory.generatePublic(new X509EncodedKeySpec(...))` thường ném `InvalidKeySpecException` |
| **Private key PKCS#8** | Thiếu byte payload, cấu trúc ASN.1 bị hỏng | `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(...))` thường ném `InvalidKeySpecException` |
| **Message bytes** | Thiếu phần thông điệp mà chữ ký đã bao phủ | Nếu bytes mới khác bytes đã ký, `verify` phải thất bại; về xác suất mật mã, không có lý do gì để chấp nhận chữ ký cũ |

### 5.1. Trường hợp chữ ký dài sai

Theo RFC 8032, chữ ký Ed25519 chuẩn có **64 byte**, chữ ký Ed448 chuẩn có **114 byte**. Tuy nhiên lỗi length không phải loại lỗi duy nhất: một chữ ký **đúng 64 byte** vẫn có thể sai, và một chuỗi dài 64 byte ngẫu nhiên không chứng minh đã được ký hợp lệ.

Javadoc `Signature.verify(...)` cho phép:
- Trả **`true`** khi chữ ký đúng.
- Trả **`false`** khi dữ liệu và chữ ký không xác minh được.
- Ném **`SignatureException`** nếu chữ ký không đúng encoding/loại hoặc provider không xử lý được dữ liệu.

Vì thế trong negative test “cắt một byte chữ ký”, **điều kiện pass là input bị từ chối**, không bắt buộc provider nào cũng phải ném đúng `SignatureException`. Bài demo dùng một hàm hỗ trợ coi cả kết quả `false` lẫn `SignatureException` là **không chấp nhận**.

Trong production, nếu input có format contract cố định, có thể kiểm tra size trước khi gọi provider để báo lỗi giao thức rõ ràng; **không được chỉ dựa vào size thay thế `verify`**.

### 5.2. Trường hợp key DER bị cắt

Mã ví dụ để dựng dữ liệu bị hỏng:

```java
byte[] truncatedPublic =
        Arrays.copyOf(publicDer, publicDer.length - 1);
byte[] truncatedPrivate =
        Arrays.copyOf(privateDer, privateDer.length - 1);
```

Đây là đoạn trong phương thức có sẵn `publicDer`, `privateDer` và import `java.util.Arrays`. Các bytes sau khi cắt thiếu trường cuối/length ASN.1, không còn là khóa DER hợp lệ của ví dụ.

Phải **thử import** bằng đúng định dạng:
- Public: `KeyFactory.getInstance("Ed25519").generatePublic(new X509EncodedKeySpec(truncatedPublic))`.
- Private: `KeyFactory.getInstance("Ed25519").generatePrivate(new PKCS8EncodedKeySpec(truncatedPrivate))`.

Các trường hợp cắt một byte của byte-array do provider trong demo phát ra đã được kiểm tra và bị từ chối bằng `InvalidKeySpecException`. Một parser/provider khác có thể báo chi tiết lỗi khác; giữ nguyên nguyên tắc **không sử dụng khóa lỗi** và **không tự bù những byte còn thiếu**.

### 5.3. Không lấy raw 32-byte Ed25519 public key làm SPKI

Trong demo, ta trích 32 byte cuối của public DER đã sinh rồi cố đưa vào `X509EncodedKeySpec`. Những bytes đó là phần raw public key của trường hợp mẫu, **không có ASN.1 SubjectPublicKeyInfo wrapper**, nên JDK provider từ chối.

Cần tránh suy từ ví dụ rằng “cứ bỏ 12 byte đầu là có một raw key dùng được”. Trong môi trường thật, phải parse encoding ASN.1 đúng chuẩn hoặc dùng API EdEC chuyên biệt theo format nguồn; **không tự bóc DER bằng độ lệch giả định**.

### 5.4. Không tự sửa dữ liệu hỏng

Khi nhận key/signature cắt cụt, không:
- Nối thêm byte `0` cho đủ độ dài.
- Bỏ bớt byte cuối “cho vừa 32/64 byte”.
- Bỏ qua lỗi `KeyFactory` và thử thêm format khác không do protocol cho phép.
- Chấp nhận chữ ký chỉ vì header, curve name hay size trông hợp lệ.
- Cho phép xử lý tiếp một thông điệp chưa xác minh như dữ liệu đã tin cậy.

Từ chối rõ ràng và báo **lý do ở mức ứng dụng an toàn**; không công khai toàn bộ khóa bí mật, raw DER nhạy cảm, thông điệp cá nhân hoặc nội dung lỗi nội bộ ra log công cộng.

## 6. Nhóm kiểm thử 3: encoding sai

Từ **encoding** có ít nhất ba nghĩa cần tách biệt:

1. **Character encoding của thông điệp** (UTF-8, UTF-16LE...) quyết định **bytes được ký**.
2. **Textual transport encoding** (Base64, Base64URL, hex, PEM armor) quyết định cách chuyển bytes thành chuỗi để lưu/truyền.
3. **Key structure encoding** (X.509 SPKI, PKCS#8 DER, raw key material) quyết định **ý nghĩa của byte-array sau khi giải mã vận chuyển**.

Một đoạn mã có thể giải mã Base64 thành công nhưng vẫn đưa bytes **không phải SPKI** cho `X509EncodedKeySpec`. Ngược lại, một public key đúng SPKI có thể bị truyền sai Base64 alphabet hoặc cắt chuỗi khi lưu làm parser không nhận được dữ liệu ban đầu.

### 6.1. Sai charset của thông điệp

EdDSA ký **byte sequence**, không ký khái niệm “một String nhìn giống nhau”:

```java
String message = "Xin chao, Viet Nam";
byte[] utf8 = message.getBytes(StandardCharsets.UTF_8);
byte[] utf16le = message.getBytes(StandardCharsets.UTF_16LE);
```

Vì `utf8` khác `utf16le`, chữ ký tạo từ `utf8` không thể được xác minh như thể ký `utf16le`. Ví dụ đầy đủ in:

```text
UTF-16LE reinterpretation accepted: false
```

Không dùng `text.getBytes()` không chỉ định charset, hoặc `new String(bytes)` không chỉ định charset khi cần tính nhất quán giao thức. Hãy dùng encoding được hai bên thống nhất **tường minh**, thường là `StandardCharsets.UTF_8`.

Với Unicode, ngoài charset còn có các vấn đề:
- Các chuỗi nhìn giống nhau có thể có **normalization khác nhau** (ví dụ ký tự dựng sẵn so với chữ + combining mark).
- Line ending `\n` so với `\r\n`, BOM có/không có, khoảng trắng cuối dòng, thêm dấu xuống dòng khi serialize, JSON có cách escape khác nhau.
- Nếu protocol ký dữ liệu văn bản đã chuẩn hóa, **phải đặc tả bước chuẩn hóa trước khi ký** và áp dụng cùng một quy tắc ở hai phía. Đừng âm thầm `trim()`, `strip()`, `replace(...)` trong luồng xác minh nếu bên ký không dùng cùng bước đó.

Tốt nhất là ký **chính xác bytes đã đóng gói theo định dạng canonical được protocol quy định**, không ký “String sau khi tự đoán lại”. Với dữ liệu JSON, XML, HTTP headers hoặc request body, cần quy tắc serialization/canonicalization chính xác; EdDSA không tự canonicalize chúng.

### 6.2. Base64 chuẩn và Base64URL

Java cung cấp các codec khác nhau:

```java
Base64.getEncoder();
Base64.getDecoder();

Base64.getUrlEncoder();
Base64.getUrlDecoder();
```

Base64 chuẩn dùng các ký tự `+` và `/`. Dạng URL-safe thay bằng `-` và `_`. Không mặc định hai alphabet có thể dùng cùng một decoder.

Ví dụ có kết quả **xác định** vì chọn bytes cố ý tạo ký tự đặc biệt:

```java
byte[] sample = {(byte) 0xfb, (byte) 0xff};
String basic = Base64.getEncoder().encodeToString(sample);
String url = Base64.getUrlEncoder().encodeToString(sample);

System.out.println(basic); // +/8=
System.out.println(url);   // -_8=
```

`Base64.getDecoder().decode("-_8=")` ném **`IllegalArgumentException`**. Nhưng với **những bytes ngẫu nhiên khác**, hai bảng chữ cái có thể vô tình tạo cùng một chuỗi nếu chuỗi đó không sử dụng `+ / - _`; do đó **test “nhầm decoder chắc chắn thất bại” phải chọn dữ liệu có ký tự phân biệt**, hoặc kiểm tra protocol chỉ chấp nhận alphabet được quy định.

Một điểm khác: Base64 decoder chuẩn trong Java **có thể chấp nhận chuỗi thiếu padding `=`** ở một số dạng hợp lệ. Vì vậy không dùng cách “bỏ dấu `=` cuối để chắc chắn có exception” làm negative test. Chọn input lỗi một cách xác định, hoặc dùng validation về canonical form theo hợp đồng hệ thống.

### 6.3. PEM và DER

Các nhãn PEM phổ biến:

| PEM label | Nội dung bên trong (sau Base64 decode) |
| --- | --- |
| `-----BEGIN PUBLIC KEY-----` | Thường là X.509 SPKI, có thuật toán và public key |
| `-----BEGIN PRIVATE KEY-----` | Thường là PKCS#8 private key không mã hóa |
| `-----BEGIN ENCRYPTED PRIVATE KEY-----` | PKCS#8/related private key container được mã hóa, cần giải mã đúng |
| `-----BEGIN CERTIFICATE-----` | X.509 certificate, **không** phải chỉ SPKI |

Không đưa nguyên văn dòng `-----BEGIN PUBLIC KEY-----` vào `KeyFactory.generatePublic(new X509EncodedKeySpec(...))`. Trước hết parser PEM cần kiểm tra header/footer, loại xuống dòng đúng chuẩn, Base64 decode thành DER rồi mới gọi `KeyFactory`. Không nên dùng `Base64.getMimeDecoder()` trên toàn bộ text PEM một cách mù quáng: MIME decoder có chính sách bỏ qua ký tự ngoài bảng chữ cái, dễ làm bạn bỏ qua dữ liệu/framing không hợp lệ. Ưu tiên một PEM parser đã được kiểm tra hoặc parser chặt chẽ có validation rõ ràng.

**Base64 không phải mã hóa bí mật (encryption)**; chuyển private key thành Base64 không bảo vệ nó. Không ghi private key, seed EdEC hoặc PKCS#8 bytes vào log, console, URL hoặc file không được bảo vệ.

## 7. Bản đồ lỗi và chiến lược fail-closed

| Đầu vào lỗi | Chỗ phát hiện phổ biến | Kết quả nên xử lý |
| --- | --- | --- |
| Ed448/X25519 public key đưa vào Ed25519 verifier | `Signature.initVerify` | Thường là `InvalidKeyException` → từ chối |
| Public key Ed25519 khác cặp | `Signature.verify` | `false` → từ chối, không thử ký lại |
| Signature bị sửa/cắt thiếu byte | `Signature.verify` | `false` **hoặc** `SignatureException` → từ chối |
| X.509 DER không hợp lệ | `KeyFactory.generatePublic` | `InvalidKeySpecException` → từ chối |
| PKCS#8 DER không hợp lệ | `KeyFactory.generatePrivate` | `InvalidKeySpecException` → từ chối |
| Base64 alphabet sai / ký tự lỗi | `Base64.Decoder.decode` | `IllegalArgumentException` → từ chối |
| Đã decode Base64, nhưng bên trong là raw bytes thay vì DER | `KeyFactory` | `InvalidKeySpecException` → từ chối |
| Dữ liệu ký bằng UTF-8 nhưng kiểm chứng bằng UTF-16LE | `Signature.verify` | `false` nếu dữ liệu bytes khác |
| Thuật toán không được cấu hình trong JCA provider | `KeyPairGenerator` / `Signature` / `KeyFactory` | `NoSuchAlgorithmException` → báo cấu hình, không downgrade tự động |

**Phân biệt lỗi hình thức và lỗi mật mã:** `InvalidKeySpecException` là vấn đề parse/import key, `InvalidKeyException` là vấn đề key dùng sai ở một thao tác, `SignatureException` có thể là lỗi ký/xác minh hoặc chữ ký malformed, còn `verify == false` nghĩa chữ ký không khớp. Không gom tất cả thành “public key không đúng” khi cần debug nội bộ; nhưng API ngoài có thể trả lỗi tổng quát để không lộ thông tin nhạy cảm.

Một hàm kiểm chứng tốt trả về “không hợp lệ” **hoặc phát lỗi được xử lý an toàn** khi gặp dữ liệu sai; không có đường nào dùng dữ liệu đã bị từ chối như đã xác minh.

**Không dùng `catch (Exception e) { return true; }`**, không thử fallback sang thuật toán yếu, và không bỏ qua signature verification chỉ vì parser đã đọc được public key.

## 8. Chương trình kiểm thử đầy đủ, chạy được với Java 15

Chương trình tạo khóa Ed25519, Ed448 và X25519 **ở runtime**, không ghi private key ra stdout. Nó kiểm tra:

1. Chữ ký Ed25519 đúng.
2. Khóa Ed25519 khác cặp và thông điệp bị sửa.
3. UTF-8 so với UTF-16LE.
4. Ed448/X25519 public keys đưa nhầm vào Ed25519 verifier.
5. Chữ ký bị cắt một byte.
6. Import lại SPKI/PKCS#8 đúng, rồi thử hai dạng DER bị cắt và raw public bytes bị gắn nhãn X.509.
7. Base64 round-trip đúng; một ca cố ý dùng sai decoder.

Lưu tệp đúng tên **`EdEcNegativeTests.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.InvalidKeyException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public final class EdEcNegativeTests {
    public static void main(String[] args) throws Exception {
        KeyPair id = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        KeyPair other = KeyPairGenerator.getInstance("Ed25519")
                .generateKeyPair();
        KeyPair ed448 = KeyPairGenerator.getInstance("Ed448")
                .generateKeyPair();
        KeyPair x25519 = KeyPairGenerator.getInstance("X25519")
                .generateKeyPair();

        byte[] message = "Xin chao, Viet Nam"
                .getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(id.getPrivate());
        signer.update(message);
        byte[] signed = signer.sign();

        System.out.println("Ed25519 valid: "
                + verify(id.getPublic(), message, signed));
        System.out.println("other Ed25519 public key accepted: "
                + verify(other.getPublic(), message, signed));
        System.out.println("modified message accepted: "
                + verify(id.getPublic(),
                        "Xin chao, Viet Nam?"
                                .getBytes(StandardCharsets.UTF_8),
                        signed));
        System.out.println("UTF-16LE reinterpretation accepted: "
                + verify(id.getPublic(),
                        "Xin chao, Viet Nam"
                                .getBytes(StandardCharsets.UTF_16LE),
                        signed));

        System.out.println("Ed448 key rejected by Ed25519: "
                + wrongKeyRejected(ed448.getPublic(), message, signed));
        System.out.println("X25519 key rejected by Ed25519: "
                + wrongKeyRejected(x25519.getPublic(), message, signed));
        System.out.println("truncated signature rejected: "
                + !verify(id.getPublic(), message,
                        Arrays.copyOf(signed, signed.length - 1)));

        byte[] publicDer = id.getPublic().getEncoded();
        byte[] privateDer = id.getPrivate().getEncoded();
        KeyFactory factory = KeyFactory.getInstance("Ed25519");

        PublicKey restored = factory.generatePublic(
                new X509EncodedKeySpec(publicDer));
        factory.generatePrivate(new PKCS8EncodedKeySpec(privateDer));

        System.out.println("X.509 key roundtrip: "
                + verify(restored, message, signed));
        System.out.println("truncated X.509 rejected: "
                + badPublicKeyRejected(factory,
                        Arrays.copyOf(publicDer, publicDer.length - 1)));
        System.out.println("truncated PKCS#8 rejected: "
                + badPrivateKeyRejected(factory,
                        Arrays.copyOf(privateDer, privateDer.length - 1)));
        System.out.println("raw public bytes not X.509: "
                + badPublicKeyRejected(factory,
                        Arrays.copyOfRange(publicDer,
                                publicDer.length - 32, publicDer.length)));

        String base64 = Base64.getEncoder().encodeToString(publicDer);
        System.out.println("Base64 key roundtrip: "
                + verify(factory.generatePublic(new X509EncodedKeySpec(
                        Base64.getDecoder().decode(base64))), message, signed));

        byte[] sentinel = {(byte) 0xfb, (byte) 0xff};
        String standard = Base64.getEncoder().encodeToString(sentinel);
        String urlSafe = Base64.getUrlEncoder().encodeToString(sentinel);
        System.out.println("standard Base64 alphabet: " + standard);
        System.out.println("URL Base64 alphabet: " + urlSafe);

        boolean wrongAlphabetRejected;
        try {
            Base64.getDecoder().decode(urlSafe);
            wrongAlphabetRejected = false;
        } catch (IllegalArgumentException ex) {
            wrongAlphabetRejected = true;
        }
        System.out.println("URL Base64 with basic decoder rejected: "
                + wrongAlphabetRejected);
    }

    private static boolean verify(PublicKey key, byte[] data, byte[] sig)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(data);
        try {
            return verifier.verify(sig);
        } catch (SignatureException malformedSignature) {
            // Dữ liệu chữ ký sai: từ chối, không coi là thành công.
            return false;
        }
    }

    private static boolean wrongKeyRejected(
            PublicKey key, byte[] data, byte[] sig)
            throws GeneralSecurityException {
        try {
            return !verify(key, data, sig);
        } catch (InvalidKeyException ex) {
            return true;
        }
    }

    private static boolean badPublicKeyRejected(KeyFactory factory, byte[] data) {
        try {
            factory.generatePublic(new X509EncodedKeySpec(data));
            return false;
        } catch (InvalidKeySpecException expected) {
            return true;
        }
    }

    private static boolean badPrivateKeyRejected(KeyFactory factory, byte[] data) {
        try {
            factory.generatePrivate(new PKCS8EncodedKeySpec(data));
            return false;
        } catch (InvalidKeySpecException expected) {
            return true;
        }
    }
}
```

**Biên dịch và chạy** (không cần thư viện ngoài, với JDK hỗ trợ Java 15):

```bash
javac --release 15 EdEcNegativeTests.java
java EdEcNegativeTests
```

**Stdout chính xác của chương trình trên JDK đã kiểm thử:**

```text
Ed25519 valid: true
other Ed25519 public key accepted: false
modified message accepted: false
UTF-16LE reinterpretation accepted: false
Ed448 key rejected by Ed25519: true
X25519 key rejected by Ed25519: true
truncated signature rejected: true
X.509 key roundtrip: true
truncated X.509 rejected: true
truncated PKCS#8 rejected: true
raw public bytes not X.509: true
Base64 key roundtrip: true
standard Base64 alphabet: +/8=
URL Base64 alphabet: -_8=
URL Base64 with basic decoder rejected: true
```

Chương trình đã được **biên dịch với `javac --release 15` và thực thi thực tế trên JDK hiện đại**; toàn bộ 15 dòng kết quả được kiểm tra. Public/private key, chữ ký và signature bytes được sinh ngẫu nhiên nhưng chương trình **không in chúng**, chỉ in các kết quả boolean và hai Base64 strings cố định, nên output ổn định.

### 8.1. Vì sao các helper không nuốt lỗi theo hướng nguy hiểm?

- `verify(...)` chỉ biến **`SignatureException` liên quan xử lý signature** thành `false`. Nếu public key không hợp lệ ở `initVerify`, `InvalidKeyException` vẫn được truyền ra cho caller. Điều này giúp phân biệt sai chữ ký với sai key type trong bài kiểm thử.
- `wrongKeyRejected(...)` bắt riêng `InvalidKeyException` và coi input sai loại **bị từ chối**. Với provider trả `false` thay vì ném một lỗi do key không thích hợp, phép kiểm cũng không đánh dấu nó là hợp lệ.
- `badPublicKeyRejected(...)`/`badPrivateKeyRejected(...)` chỉ đánh dấu pass khi KeyFactory **thực sự từ chối bytes lỗi**. Nếu parser lại chấp nhận bytes bị sửa/cắt, bài test sẽ in `false` và cần điều tra.
- `Arrays.copyOf(...)` dựng test data **không sửa mảng khóa/chữ ký gốc**. Điều đó giúp đối chiếu happy path và negative path độc lập.
- `Base64.getDecoder()` được dùng đúng khi mã hóa bằng `Base64.getEncoder()`. Ca sai decoder dùng bytes cố tình sinh ký tự `+ / - _` để kết quả chắc chắn phân biệt.

**Vì sao không in private key vào console để kiểm tra?** In khóa bí mật làm rò rỉ key material. Dù đây là chương trình demo, thay vì đối chiếu bytes khóa bí mật, ta dùng **hành vi ký/xác minh và key import** để kiểm tra tương thích.

### 8.2. Tại sao ca chữ ký cắt cụt không in loại ngoại lệ cụ thể?

Theo hợp đồng JCA, provider được báo `SignatureException` với chữ ký sai encoding/type. Một số đường xác minh có thể trả `false`. Hàm `verify(...)` chấp nhận cả hai kết quả theo nguyên tắc **fail closed**: không bao giờ kết luận dữ liệu bị cắt là hợp lệ. Nếu hệ thống của bạn cần phân biệt phục vụ telemetry, hãy ghi lý do lỗi an toàn ở tầng riêng mà không tiết lộ dữ liệu nhạy cảm; **không viết test phụ thuộc vào một exception message hoặc class nội bộ của provider**.

### 8.3. Vì sao có cả wrong key type và wrong public key?

- `wrongKeyRejected(ed448.getPublic(), ...)` / `wrongKeyRejected(x25519.getPublic(), ...)`: sai **loại/đường cong**.
- `verify(other.getPublic(), ...)`: **đúng loại Ed25519**, nhưng public key **không khớp với private key ký**. Đây là hai lớp lỗi khác nhau, và cần cả hai loại test trong hệ thống đa người dùng hoặc xoay vòng khóa.

Không được “chữa” lỗi loại 2 bằng cách thử lần lượt mọi public key trong hệ thống để tìm một key nhận chữ ký rồi tự động gắn danh tính: cần phân định key-id, ownership, trust và chính sách xử lý theo application protocol.

## 9. Áp dụng trong API thật: pipeline tiếp nhận an toàn

Một pipeline import và verify có thể tổ chức:

```text
Nhận request (size limit, content type, version, key-id)
             |
             v
Kiểm tra length / framing / định dạng truyền tải
             |
             v
Base64 hoặc Base64URL decode đúng chuẩn giao thức
             |
             v
Nếu có key bytes: parse bằng KeyFactory + đúng spec (SPKI/PKCS#8)
             |
             v
Xác minh thuật toán/curve và chọn trusted public key theo key-id
             |
             v
Canonical bytes của message theo protocol (UTF-8, serialization...)
             |
             v
Signature.getInstance("Ed25519") -> initVerify -> update -> verify
             |
        +----+----+
        |         |
      true       false / exception
        |         |
   Chấp nhận      Từ chối
   nếu đủ         không dùng dữ liệu
   quyền          như đã xác thực
```

**Khuyến nghị triển khai:**

- Đặt giới hạn kích thước cho **request, base64 string, DER blob và message** trước khi cấp phát bộ nhớ lớn; phát hiện chiều dài bất thường. Với Ed25519, signature chuẩn là 64 byte nhưng **key DER không bị ràng buộc bởi ngưỡng 32 byte**.
- Tách **lỗi parse** khỏi **lỗi verify** để vận hành nội bộ, nhưng API ngoài có thể trả thông báo chung nhằm tránh lộ thông tin về danh tính/key registry.
- Chọn thuật toán từ **policy đã cho phép** (ví dụ phiên bản giao thức cố định là Ed25519), không tin trường `"alg"` trong input mà tự động dùng thuật toán bất kỳ.
- Dùng một **trusted public-key registry**; kiểm soát key-id, người sở hữu, vòng đời, expiration, rotation và revocation. Nếu đầu vào tự cung cấp cả message, chữ ký và “public key để kiểm tra”, `verify == true` **không chứng minh danh tính được mong đợi**.
- Trong hệ thống có nhiều cách serialization, xác định canonical bytes rõ ràng trước khi ký hoặc xác minh. Không thay đổi bytes bằng thao tác “sửa cho giống” sau khi xác minh thất bại.
- Không log private signing key, seed, PKCS#8, bí mật HSM, token hay thông điệp nhạy cảm. Với public key cũng cần cân nhắc chính sách dữ liệu và danh tính liên quan.
- Luôn có **happy path** và **negative path** trong CI: kiểm tra key đúng, key sai curve, key khác cặp, chữ ký sai/truncated, key DER malformed, Base64 sai alphabet, nội dung sai charset.
- Sử dụng test độc lập theo JDK/provider thực tế, nhất là khi tích hợp HSM hoặc provider bên thứ ba; cùng một input xấu có thể dẫn tới **các kiểu lỗi khác nhau**, nhưng không được đi qua nhánh xác minh thành công.

## 10. Đối chiếu các biến thể EdEC và encoding thường thấy

### Ed25519 và Ed448

- Ed25519 và Ed448 đều thuộc EdDSA nhưng dùng **parameter sets khác nhau**, không hoán đổi public/private key.
- Chữ ký chuẩn: **Ed25519 = 64 byte**, **Ed448 = 114 byte**. Kích thước này áp dụng cho **raw signature bytes**, không áp dụng cho mọi bản ghi PEM/ASN.1 bao quanh.
- Để kiểm tra Ed448, dùng `KeyPairGenerator.getInstance("Ed448")`, `Signature.getInstance("Ed448")` và đúng public key Ed448. Không dùng `Signature.getInstance("Ed25519")` rồi cố tự rút/ngắt signature Ed448 thành 64 byte.
- Các biến thể domain/context/prehash (nếu protocol có quy định) phải được xử lý đúng specification và cấu hình EdDSA tương ứng, không tự hash bằng SHA-256 rồi coi đó là Ed25519ph.

### EdEC so với XEC

- `EdECPublicKey` / `EdECPrivateKey` dành cho **EdDSA**.
- `XECPublicKey` / `XECPrivateKey` dành cho họ **XDH/X25519/X448**, không phải verifier của Ed25519.
- `NamedParameterSpec.ED25519`, `ED448` dùng cho EdEC; `X25519`, `X448` cho XDH. Các tên gần nhau không có nghĩa key exchange và signature là hai cách diễn giải cùng một public key object.
- Không viết converter thủ công từ EdEC point sang XEC point rồi tin rằng key tương ứng hoặc mô hình an toàn không thay đổi. Nếu một giao thức đặc biệt yêu cầu chuyển đổi được chuẩn hóa, đó là một vấn đề độc lập cần đặc tả và test vector riêng.

### Kiểu lỗi Java thường nhìn thấy

| API/đối tượng | Lỗi thường gặp | Điểm cần kiểm tra |
| --- | --- | --- |
| `KeyPairGenerator.getInstance("Ed25519")` | `NoSuchAlgorithmException` | Provider/algorithm registry của runtime |
| `Signature.initSign(privateKey)` | `InvalidKeyException` | Loại private key, curve, policy |
| `Signature.initVerify(publicKey)` | `InvalidKeyException` | Loại public key, curve và provider |
| `Signature.verify(signature)` | `false` hoặc `SignatureException` | Message bytes, signature bytes, encoding |
| `KeyFactory.generatePublic(X509EncodedKeySpec)` | `InvalidKeySpecException` | SPKI DER, OID, length, key format |
| `KeyFactory.generatePrivate(PKCS8EncodedKeySpec)` | `InvalidKeySpecException` | PKCS#8 DER, OID, length, quyền xuất khóa |
| `Base64.Decoder.decode(...)` | `IllegalArgumentException` | Alphabet, ký tự, padding, delimiter |
| `new String(bytes, charset)` / `String.getBytes(charset)` | Có thể không ném nhưng đổi bytes | Charset, normalization, BOM, newline |
| `EdECPrivateKey.getBytes()` | `Optional.empty()` có thể xuất hiện | Provider không cho phép xuất key material |

Những ngoại lệ này là **hợp đồng API còn phù hợp**, không phải một bảng “mọi provider luôn ném chính xác lỗi đó cho mọi byte lỗi”. Khi viết test portable, ưu tiên kiểm tra **đầu vào không được chấp nhận** và tách lỗi người dùng khỏi lỗi cấu hình/hệ thống.

## 11. Những hiểu nhầm phổ biến

1. **“Ed25519 và X25519 cùng là 25519 nên dùng chung public key.”** Sai: một cái dành cho chữ ký, một cái dành cho key agreement; các interface và phép toán khác nhau.
2. **“Ed448 có public key tương tự Ed25519 nên chỉ đổi tên cho verifier.”** Sai: bộ tham số/độ dài/thuật toán khác, phải dùng đúng cặp.
3. **“Một public key Ed25519 hợp lệ thì xác minh mọi chữ ký Ed25519.”** Sai: phải là public key **tương ứng** với private key đã ký.
4. **“Chữ ký sai độ dài chắc chắn ném đúng một exception cụ thể.”** Sai: `verify` có thể trả `false` hoặc ném `SignatureException` cho dữ liệu không đúng chuẩn.
5. **“Chỉ cần đủ 64 byte là chữ ký hợp lệ.”** Sai: kích thước đúng chỉ là điều kiện hình thức, phải verify trên message và trusted public key.
6. **“Raw Ed25519 public bytes chính là X.509 DER.”** Sai: `X509EncodedKeySpec` cần SubjectPublicKeyInfo.
7. **“PKCS#8 private key có đúng 32 byte.”** Sai: phần seed có thể là 32 byte nhưng PKCS#8 là cấu trúc có thuật toán/ASN.1 bao quanh.
8. **“Base64 decode xong là key chắc chắn đúng.”** Sai: Base64 chỉ khôi phục bytes, chưa kiểm tra DER/key validity.
9. **“Base64 và Base64URL luôn thay thế được.”** Sai: bảng ký tự khác, có những input bị decoder kia từ chối.
10. **“Bỏ một dấu `=` padding chắc chắn làm decode lỗi.”** Sai: một số chuỗi không cần padding vẫn được decoder Java chấp nhận.
11. **“UTF-8 và UTF-16LE của cùng String cho cùng chữ ký.”** Sai: bytes khác, EdDSA xác minh trên bytes.
12. **“Một String nhìn giống nhau sau Unicode normalization thì chữ ký vẫn giống.”** Không được bảo đảm: nếu bytes khác, verification không khớp. Phải chuẩn hóa theo contract hai phía.
13. **“X.509 SPKI chính là X.509 certificate.”** Sai: SPKI là cấu trúc public key; certificate còn có nhiều trường và chữ ký CA.
14. **“Dữ liệu cắt cụt có thể bù 0 để chữa rồi thử verify.”** Không: việc tự sửa không có hợp đồng làm thay đổi thông điệp/khóa và có thể mở đường chấp nhận sai.
15. **“Bắt exception rồi trả true để không làm gián đoạn request.”** Tuyệt đối sai: lỗi chữ ký/key phải đóng luồng xác thực, không bật quyền truy cập.
16. **“Signature.verify true xác nhận đúng người ký ngay cả khi lấy public key từ request.”** Chưa đủ: phải ràng buộc public key với danh tính đã được xác thực.

## 12. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** Cặp `KeyPairGenerator.getInstance("X25519")` tạo ra key. Gọi `Signature.getInstance("Ed25519").initVerify(xPublic)` có đúng không?

**Đáp án:** **Không.** X25519 là khóa thỏa thuận XDH, không phải Ed25519 verifying key. Provider phải từ chối key sai mục đích, thường bằng `InvalidKeyException`.

**Câu 2.** Một chữ ký Ed25519 dài 63 byte. Có nên kết luận “không thể verify” mà không chạy provider không?

**Đáp án:** Theo định dạng chuẩn, Ed25519 chữ ký hợp lệ dài **64 byte**, nên 63 byte là malformed. Ở tầng API, có thể từ chối sớm theo length contract, hoặc để provider từ chối. **Không dự đoán cứng** mọi provider sẽ ném loại exception nào; `verify` có thể trả `false` hoặc ném `SignatureException`.

**Câu 3.** Key DER public Ed25519 có 44 byte trong môi trường thử. Có thể lấy 32 byte cuối và bọc trong `X509EncodedKeySpec`?

**Đáp án:** **Không.** X509EncodedKeySpec cần **toàn bộ SPKI** có AlgorithmIdentifier và BIT STRING. Truyền raw 32 bytes bị coi là sai format. Không giả định mọi DER có cấu trúc/độ dài đúng 44 byte; hãy dùng parser/spec phù hợp.

**Câu 4.** Chữ ký tạo trên bytes UTF-8 của `"Xin chao"`; bên nhận kiểm chứng trên UTF-16LE bytes của String giống nhau. Kết quả mong đợi?

**Đáp án:** **Không xác minh được** vì byte sequences khác nhau. Cần thống nhất canonical message encoding ở hai phía, thường dùng UTF-8 được chỉ định tường minh.

**Câu 5.** Base64URL của hai byte `0xfb 0xff` là gì, và Base64 chuẩn của chúng là gì?

**Đáp án:** URL-safe là `-_8=`; chuẩn là `+/8=`. Dùng `Base64.getDecoder()` để giải mã `-_8=` sẽ nhận `IllegalArgumentException`.

**Câu 6.** `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(...))` từ chối bytes bị cắt cụt. Có nên đoán phần bytes còn thiếu từ chiều dài của khóa không?

**Đáp án:** **Không.** Khóa đã bị lỗi cấu trúc; từ chối, lấy lại dữ liệu từ nguồn đáng tin và kiểm tra bước truyền/serialization. Không tạo key giả bằng padding.

**Câu 7.** Có hai public Ed25519 khác nhau A và B, cả hai parse hợp lệ. Một chữ ký được tạo bởi private A. Dùng public B xác minh phải như thế nào?

**Đáp án:** **Thất bại**: đúng thuật toán không có nghĩa đúng cặp. Đây là ca khác với truyền public Ed448/X25519 vào Ed25519 verifier.

**Câu 8.** Nếu verify chữ ký thành công với public key được lấy trực tiếp từ chính request của người lạ, có thể gắn hành động vào danh tính một người dùng nội bộ không?

**Đáp án:** **Không** nếu chưa có cơ chế tin cậy ràng buộc public key với danh tính đó. Verification chứng minh tính tương ứng của chữ ký và public key đã cung cấp, không tự kiểm tra trust/identity.

**Câu 9.** Bên ký và bên nhận đều UTF-8 nhưng bên nhận tự `trim()` body trước `Signature.update(...)`. An toàn không?

**Đáp án:** Chỉ đúng nếu **protocol đã quy định chính xác** việc canonicalize như thế và bên ký cũng dùng đúng bytes sau cùng. Tự sửa whitespace ở một phía làm bytes khác, có thể gây verify fail hoặc sai nghĩa dữ liệu.

**Tiêu chí đạt:** Bạn phân loại được sai **key type / key pair / key serialization / signature length / message bytes / transport encoding**, dùng JCA/EdEC đúng mục đích và **không bao giờ** coi exception hoặc key import thành công là chữ ký hợp lệ.

## 13. Nguồn chuẩn còn áp dụng với Java hiện đại

- [OpenJDK JEP 339 – Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): Ed25519/Ed448 được chuẩn hóa trong Java 15, các interface EdEC và tên thuật toán.
- [Java SE 15 – `EdECPublicKey`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/interfaces/EdECPublicKey.html): `getParams()`, `getPoint()`, quan hệ với public key.
- [Java SE 15 – `EdECPrivateKey`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html): `getParams()` và `getBytes()` dạng `Optional`.
- [Java SE 15 – `NamedParameterSpec`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/NamedParameterSpec.html): các hằng `ED25519`/`ED448` và `X25519`/`X448`.
- [Java SE 25 – `Signature`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): `initSign`, `initVerify`, `update`, `sign`, `verify` và `SignatureException`.
- [Java SE 25 – `KeyFactory`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyFactory.html): `generatePublic`/`generatePrivate` và lỗi `InvalidKeySpecException`.
- [Java SE 25 – `X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): yêu cầu `SubjectPublicKeyInfo` của public key.
- [Java SE 25 – `PKCS8EncodedKeySpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html): encoded private key theo PKCS#8.
- [Java SE 25 – `Base64.Decoder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Base64.Decoder.html): decoder variants, padding được chấp nhận và `IllegalArgumentException`.
- [RFC 8032 – Ed25519 và Ed448](https://www.rfc-editor.org/rfc/rfc8032): cấu trúc và kích thước chữ ký, quy tắc EdDSA.
- [RFC 8410 – Ed25519/Ed448/X25519/X448 Key Encodings](https://www.rfc-editor.org/rfc/rfc8410): OID, SubjectPublicKeyInfo, PKCS#8 và các lỗi format khi import.
- [RFC 4648 – Base64/Base64URL](https://www.rfc-editor.org/rfc/rfc4648): hai bảng ký tự dùng để truyền binary qua text.

**Ghi nhớ:** **Kiểm tra đúng loại EdEC, đúng public key, đúng message bytes và đúng encoding** là bốn yêu cầu độc lập. **Cắt cụt hoặc sai format phải bị từ chối**, cho dù lỗi hiện ra dưới dạng `false` hay exception. Bài kiểm thử tốt đánh giá hành vi **fail closed** và không bao giờ nâng dữ liệu chưa được xác minh thành thông tin đáng tin cậy.