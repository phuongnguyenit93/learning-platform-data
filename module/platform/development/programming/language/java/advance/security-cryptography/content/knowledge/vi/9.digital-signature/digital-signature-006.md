# 9.6. Thống nhất dữ liệu ký và tránh băm hai lần khi API đã kết hợp digest

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **thông điệp gốc (message bytes)**, **digest**, **chữ ký số** và **biểu diễn dữ liệu cần ký**; hiểu chính xác chuỗi byte nào được bảo vệ.
2. Giải thích tại sao `Signature.getInstance("SHA256withRSA")` đã thực hiện SHA-256 như một phần thuật toán chữ ký và vì sao gọi `MessageDigest.digest(...)` trước `Signature.update(...)` có thể vô tình **băm hai lần**.
3. Thiết kế một **hợp đồng dữ liệu ký** rõ ràng: thứ tự trường, kiểu dữ liệu, encoding UTF-8, Unicode, số thập phân, ngày giờ, phân tách trường, domain separation, phiên bản, metadata và canonicalization.
4. Dùng Java 17+ để ký và xác minh **đúng cùng chuỗi byte**, kiểm tra dữ liệu bị sửa, minh họa lỗi double hashing và nhận diện khác biệt giữa RSA/PKCS#1 v1.5, RSA-PSS, ECDSA và Ed25519.
5. Tích hợp với đối tác, HSM, KMS hoặc API chỉ nhận digest mà không nhầm **API băm tích hợp** với **API ký digest đã băm trước**, đồng thời tách xác minh chữ ký khỏi tin cậy danh tính, phân quyền và chống phát lại.

**Phạm vi:** Bài học thuộc chủ đề **9. Chữ ký số** trong Java Advance – security-cryptography. Trọng tâm là tính nhất quán đầu vào và ngữ nghĩa của API ký; ví dụ ký bằng khóa mới chỉ minh họa cơ chế, không thay thế PKI hoặc hệ thống tin cậy production.

---

## 1. Chữ ký số thực sự ký dữ liệu nào?

Chữ ký số không ký “một object Java” theo nghĩa trừu tượng. API chữ ký xử lý **một chuỗi byte xác định**. Với thuật toán có digest tích hợp như `SHA256withRSA`, luồng khái niệm là:

```text
Dữ liệu nghiệp vụ (order, payload, file, yêu cầu...)
                         │
                         ▼
          Serialization/canonicalization
                         │
                         ▼
                 Message bytes M
                         │
                         ▼
       Signature("SHA256withRSA").update(M)
                         │
                         ▼
           SHA-256(M)  [nằm trong engine]
                         │
                         ▼
          Cơ chế ký RSA / PKCS#1 v1.5
                         │
                         ▼
                 Signature bytes S

Người nhận: xây lại đúng M → Signature.verify(S) bằng public key
```

Đây là sơ đồ minh họa ngữ nghĩa; provider quản lý chi tiết băm, encoding digest, padding và phép toán ký theo thuật toán cụ thể. Với `SHA256withRSA`, SHA-256 đã nằm trong chữ “SHA256with...”. Với `SHA256withECDSA` hay `RSASSA-PSS` được cấu hình SHA-256, API tương ứng cũng xử lý digest theo scheme. Với `Ed25519`, thuật toán EdDSA có xử lý hash nội bộ **theo chính đặc tả Ed25519**, không có nghĩa bạn được thay thông điệp bằng `SHA-256(M)`.

Điểm quan trọng:

- **Message bytes (`M`)**: byte đã được hai phía thống nhất dùng làm input.
- **Digest (`H(M)`)**: đầu ra của hàm băm như SHA-256, thường dài 32 byte; có thể dùng để kiểm tra fingerprint/so sánh nội dung hoặc nằm *bên trong* signature scheme.
- **Signature (`S`)**: kết quả của thuật toán ký sử dụng private key và input; thông thường người xác minh dùng public key và **chính byte M**.
- **Xác thực danh tính**: chữ ký chỉ chứng minh sự nhất quán với một public key và thuật toán. Để kết luận “ai đã ký”, cần quy trình tin cậy public key/certificate và policy.

Cách sử dụng `Signature` thông thường là **init → update(message bytes) → sign/verify**. Đừng tự băm trước chỉ vì nghe nói chữ ký số dùng hàm băm.

## 2. Băm một lần và băm hai lần khác nhau về ngữ nghĩa

Gọi `H` là SHA-256 và `M` là byte nội dung đã thống nhất.

### 2.1. Đúng khi dùng thuật toán tích hợp digest

```text
Signature("SHA256withRSA").update(M)
           └── engine thực hiện H(M)
           └── tạo chữ ký RSA trên biểu diễn digest theo scheme

Verifier("SHA256withRSA").update(M)
           └── engine thực hiện cùng H(M)
           └── verify chữ ký trên đúng thông điệp M
```

Java:

```java
Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("SHA256withRSA");
verifier.initVerify(publicKey);
verifier.update(messageBytes);
boolean ok = verifier.verify(signature);
```

Đây là **đoạn minh họa chưa độc lập**: cần `import java.security.Signature;`, hai khóa tương ứng và `messageBytes`, cùng xử lý checked exception. Ví dụ độc lập hoàn chỉnh nằm ở mục 6.

### 2.2. Sai khác khi tự băm trước rồi gọi thuật toán có digest

```java
byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(messageBytes);

Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);
signer.update(digest); // Ký H(M) như thể nó là toàn bộ message.
byte[] signature = signer.sign();
```

Đây là **mẫu lỗi cho một giao thức yêu cầu ký M**. Với `SHA256withRSA`, engine tiếp tục tính SHA-256 trên **32 byte digest** được truyền vào, nên chữ ký có hiệu lực đối với `H(H(M))` ở tầng digest nội bộ, thay vì `H(M)` dự kiến.

```text
M ── SHA-256 ──> H(M) ── Signature(SHA256withRSA) ── SHA-256 ──> H(H(M))
^                                                ^
Dữ liệu hai bên muốn ký                           Engine coi H(M) là message
```

Hệ quả thực tế:

- Người nhận truyền **M nguyên bản** vào `SHA256withRSA` sẽ không xác minh được chữ ký gửi từ phía **đã truyền H(M)**.
- Nếu cả hai phía đều vô tình truyền **H(M)** vào `SHA256withRSA`, `verify` có thể trả **true**; **true không chứng minh hai bên thực hiện đúng giao thức mong muốn**.
- Double hashing không tự động có nghĩa attacker lập tức làm giả được RSA; vấn đề trực tiếp là **ký sai thông điệp/ngữ nghĩa, không tương thích giữa các bên, gây nhầm lẫn về bảo vệ dữ liệu**, có thể dẫn tới lỗi hệ thống khi các thành phần áp dụng quy tắc khác nhau.
- Đổi sang `Signature.getInstance("NONEwithRSA")` hoặc `NONEwithECDSA` để “sửa nhanh” là **nguy hiểm**: các mode không băm có hợp đồng, padding/encoding và giới hạn provider riêng; không phải API chung nhận digest rồi lập tức ký theo mọi scheme.

**Quy tắc:** khi `Signature` đã tích hợp digest, truyền **byte dữ liệu chuẩn hóa cần ký**, trừ khi giao thức được thiết kế rõ ràng rằng chính một digest là *thông điệp* cần ký.

### 2.3. Có nên tự tính `MessageDigest` ở đâu?

Có, nếu bạn cần mục đích **khác**:

- Tạo fingerprint để hiển thị, đối chiếu audit hoặc phát hiện nội dung thay đổi.
- Kiểm tính toàn vẹn tải xuống trong một kênh tin cậy với digest đã được xác thực riêng.
- Tích hợp dịch vụ ký **có hợp đồng prehashed input** (ví dụ API HSM/KMS nhận digest chuẩn), khi đó bạn phải biết chính xác byte và cơ chế nhận digest, xem mục 8.
- Ký **một bản manifest chứa các digest** của nhiều file: lúc này manifest chính là thông điệp M được ký; cần cấu trúc/encoding/version rõ ràng. Đây không phải “sửa double hashing” mà là thiết kế giao thức ký manifest.

Băm riêng để log không làm thay đổi byte truyền vào `Signature.update` trong giao thức ký trực tiếp.

## 3. Vì sao cùng “nội dung” nhưng chữ ký lại khác?

Hai phía có thể cùng nhìn thấy một đơn hàng hiển thị “125.50 VND” nhưng tạo ra **mảng byte khác nhau**. Thuật toán chữ ký nhận byte, không hiểu object, field name hay semantics; chỉ cần một byte khác là xác minh thông thường sẽ thất bại.

### 3.1. Những khác biệt hay xuất hiện

| Nguồn dữ liệu | Bên A | Bên B | Vì sao ký khác? |
| --- | --- | --- | --- |
| Encoding | UTF-8 | UTF-16LE hoặc platform default | Mảng byte khác dù text có vẻ giống |
| Unicode | Ký tự có dấu ở dạng NFC | Dạng NFD (ký tự nền + combining mark) | Hiển thị giống nhưng UTF-8 khác |
| Newline | `\n` (LF) | `\r\n` (CRLF) | Byte ký khác |
| BOM | Không có UTF-8 BOM | Có BOM | Byte đầu vào khác |
| JSON | `{"a":1,"b":2}` | `{"b":2,"a":1}` | Thứ tự field khác |
| JSON whitespace | `{"a":1}` | `{ "a": 1 }` | Byte khác; chữ ký không tự bỏ whitespace |
| Decimal | `125.50` | `125.5` hoặc `1.255E2` | Biểu diễn khác |
| Timestamp | UTC `2026-10-31T12:00:00Z` | `2026-10-31T19:00:00+07:00` | Cùng instant nhưng string khác |
| Collection | HashMap không có thứ tự chuẩn | SortedMap/sắp theo schema | Chuỗi serialization khác |
| Boolean/null | `false`/null được ghi rõ | Trường bị bỏ | Schema khác |
| HTTP request | Query param/percent encoding khác | Header whitespace/path khác | Signature input khác |
| File | Byte gốc | Text được parse rồi ghi lại | Parser có thể đổi encoding/newline/định dạng |

**Chú ý:** Không phải mọi hệ thống cần canonicalize để làm giống nhau. Nếu bạn ký **raw file bytes**, mọi byte của file chính là dữ liệu có chủ đích được bảo vệ: không được chuẩn hóa newline/Unicode khi verify, vì làm vậy thay thông điệp đã được tác giả ký.

### 3.2. Canonicalization là một hợp đồng giao thức

Các phía cần chốt **quy tắc biểu diễn dữ liệu** *trước khi ký*: chọn byte nào, thứ tự và định dạng ra sao, chuẩn hóa hay giữ nguyên byte gốc, dùng UTF-8 nào, schema version, xử lý dữ liệu thiếu và các loại số.

Hai lựa chọn khác nhau:

1. **Ký raw bytes:** thích hợp file nhị phân, nội dung HTTP body nguyên bản, firmware. Hai phía giữ nguyên byte; không parse/reserialize.
2. **Ký một biểu diễn canonical của dữ liệu có cấu trúc:** thích hợp đơn hàng, giao dịch, thông điệp nghiệp vụ. Cả hai phải sử dụng **cùng thuật toán canonicalization** để tạo lại đúng byte trước khi verify.

Nếu giao thức yêu cầu ký JSON, đừng dựa vào `Map.toString()`, sự may mắn của thứ tự `HashMap`, cách serializer tùy cấu hình hoặc thứ tự keys “thường gặp”. Có thể tham khảo một chuẩn canonical JSON cụ thể như **RFC 8785 (JCS)** khi phù hợp, cùng hạn chế của chuẩn về dạng số và tập dữ liệu. Java SE 17 **không cung cấp sẵn một API canonical JSON phổ dụng**.

Canonicalization phải được **version hóa**, được test trên các trường hợp Unicode, null/optional, số lớn, escape, time zone và serializer đa ngôn ngữ; không nên chỉ dựa vào một ví dụ JSON đơn giản.

## 4. Thiết kế hợp đồng dữ liệu ký chắc chắn

Một giao thức ký giao dịch nên xác định ít nhất:

| Thành phần | Quy tắc cần ghi rõ |
| --- | --- |
| **Purpose/domain** | Ví dụ `com.example.payment.approve/v1`; phân biệt chữ ký approve với refund/cancel |
| **Message schema/version** | Tên trường, kiểu, trường bắt buộc, optional/null, phiên bản thuật toán serialize |
| **Field order** | Thứ tự cố định hoặc canonical ordering đã định |
| **Binary frame** | Length-prefix, fixed width, endian, phân tách/escape tránh nhập nhằng |
| **Text encoding** | UTF-8; có hay không Unicode NFC/NFD; xử lý newline và BOM |
| **Numbers** | Đơn vị tiền, số chữ số thập phân, bỏ/giữ leading/trailing zero |
| **Date/time** | UTC timestamp format hoặc số epoch với unit rõ ràng |
| **Algorithm** | `SHA256withRSA`/`RSASSA-PSS`/`Ed25519`; tham số PSS, format signature |
| **Key identity** | Key ID/certificate và chính sách tin cậy riêng; không tin keyId do client tự khai |
| **Context** | User/tenant, object ID, action, API version, nonce, expiry hoặc sequence number |
| **Verification** | Lấy *đúng byte đã ký*, kiểm signature, key trust và authorization/replay |

### 4.1. Tránh nối chuỗi không phân ranh giới

Mẫu nguy hiểm:

```text
serialize(a,b) = UTF8(a + b)

("ab", "c") -> "abc"
("a", "bc") -> "abc"
```

Hai cặp trường khác nhau biến thành **cùng message bytes**, do đó **cùng chữ ký hợp lệ** có thể bị diễn giải thành hai giao dịch khác nhau nếu một bên cho phép thay đổi ranh giới trường. Đây là lỗi *ambiguous serialization*, không phải lỗi thuật toán SHA-256.

Một cách rõ ràng hơn:

```text
VERSION || len(field1) || field1 || len(field2) || field2 || ...
```

Trong đó `len` tính theo **byte đã encode**, không theo `String.length()` của Java; dùng fixed-width integer (ví dụ 4 byte big-endian), có giới hạn độ dài cho mỗi trường, thứ tự định sẵn, domain marker và schema version. Người nhận phải parse đúng schema tương ứng và không chấp nhận field trùng hoặc encoding mơ hồ.

### 4.2. Domain separation: chữ ký cho hành động nào?

Giả sử cùng một key dùng cho hai thao tác `approve` và `refund`. Nếu hai API ký cùng một JSON chung không có operation code, một signature có thể bị đem đến endpoint khác (tùy logic từng endpoint) để được hiểu sai nghĩa.

Hãy đưa **domain/purpose** đã thống nhất vào chuỗi byte cần ký, ví dụ:

```text
"com.example.payment/approve/v1" || orderId || amount || currency || tenantId
```

Các field cần encoding/framing không nhập nhằng; đây chỉ là ký hiệu khái niệm. Bên verify phải kiểm đúng **domain** cho endpoint đang xử lý, đúng tenant, đúng action, đúng object và các thuộc tính có thể thay đổi kết quả nghiệp vụ.

Không nên lấy cùng message bytes/signature cho một protocol khác mà không có chủ đích. Domain separation bảo vệ **ý nghĩa** của chữ ký, ngoài integrity byte-level.

### 4.3. Tính thứ tự và đơn vị của tiền/ngày giờ

Đừng ký kiểu `double` cho tiền nếu hai hệ thống cần biểu diễn văn bản độc lập. Chọn `BigDecimal` với scale/rounding rule chính xác hoặc dùng số nguyên đơn vị nhỏ nhất như cent, đồng. Ví dụ `BigDecimal("125.50").setScale(2, RoundingMode.UNNECESSARY).toPlainString()` cho ra `"125.50"`; không dùng locale-dependent `NumberFormat` trong hợp đồng byte.

Ngày giờ nên có một quy ước rõ ràng như epoch milliseconds UTC theo `long`, hoặc ISO-8601 UTC đã cố định độ chính xác và định dạng. `Instant.toString()` trong các trường hợp khác nhau có thể thay độ dài phần fractional; nếu đây là giao thức liên thông, cần test vector, không suy luận mọi string ISO là giống nhau.

### 4.4. Unicode và normalization phải được thống nhất

Trong Java:

```java
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
```

Đây là đoạn minh họa, cần `import java.nio.charset.StandardCharsets;` và `text` đã được định nghĩa. Việc gọi `getBytes()` không tham số phụ thuộc charset mặc định theo phiên bản JDK/môi trường; với protocol cross-platform luôn ghi rõ UTF-8.

Unicode có thể biểu diễn một chuỗi nhìn giống nhau bằng code point khác nhau, ví dụ ký tự được tạo từ một code point dựng sẵn so với ký tự nền kèm dấu kết hợp. Nếu hợp đồng yêu cầu NFC, hai phía phải gọi một quy tắc NFC tương đương **trước khi encode**. Tuy nhiên **không tự chuẩn hóa nội dung raw file hay identifier** nếu giao thức không cho phép: normalization có thể đổi dữ liệu/hành vi định danh.

## 5. Chính xác nên gọi `java.security.Signature` như thế nào?

Với `SHA256withRSA`, quy trình chuẩn là:

1. Chọn thuật toán đã được giao thức/chính sách cho phép.
2. Tạo byte ký **duy nhất** từ canonical serializer hoặc raw bytes.
3. `Signature.getInstance("SHA256withRSA")`.
4. `initSign(privateKey)`, sau đó `update(messageBytes)` rồi `sign()`.
5. Gửi/lưu signature kèm thông tin cần để tìm đúng message/schema/algorithm/key theo format được xác thực.
6. Bên nhận xây lại đúng `messageBytes`, `initVerify(publicKey)`, `update(messageBytes)` và `verify(signature)`.
7. Chỉ sau verify thành công và key identity đáng tin cậy mới áp dụng authorization, thời hạn, replay controls và business policy.

`Signature.update(byte[])` nhận **message bytes**, không phải “digest placeholder”. Kết quả `verify` là boolean; tùy trường hợp chữ ký sai format/provider có thể ném `SignatureException` thay vì trả false, nên cần xử lý lỗi an toàn.

### 5.1. `MessageDigest` là API khác

`MessageDigest.getInstance("SHA-256")` cung cấp hash không khóa, dùng để tính digest/fingerprint của dữ liệu. Nó không chứng minh signer sở hữu private key; bất kỳ ai cũng có thể băm dữ liệu công khai.

```java
byte[] digest = MessageDigest.getInstance("SHA-256")
        .digest(messageBytes);
```

Đoạn này cần `import java.security.MessageDigest;`. Sau khi tính digest cho mục tiêu audit, nếu chữ ký algorithm là `SHA256withRSA`, vẫn đưa **messageBytes** vào `Signature.update`; không đưa `digest` trừ khi giao thức quy định đang ký một **digest-as-message** với ý nghĩa riêng.

### 5.2. Không có “default signature algorithm”

Java yêu cầu `Signature.getInstance(algorithm)`. Java 17 không có một chế độ ký mặc định phù hợp mọi loại key. Chọn tên theo key type và policy, ví dụ:

| Thuật toán `Signature` | Digest do scheme xử lý? | Đặc điểm quan trọng |
| --- | --- | --- |
| `SHA256withRSA` | **Có**, SHA-256 | RSA PKCS#1 v1.5 signature scheme; thường dùng cho tương thích |
| `RSASSA-PSS` + `PSSParameterSpec` SHA-256 | **Có**, theo cấu hình PSS | MGF1 hash, salt length, trailer phải thống nhất; PSS có ngẫu nhiên trong chữ ký |
| `SHA256withECDSA` | **Có**, SHA-256 | Chữ ký ECDSA, định dạng thường DER theo provider/API; có biến thể P1363 riêng |
| `Ed25519` | Có xử lý hash nội bộ theo EdDSA, **không phải SHA256with...** | Ký trực tiếp message bytes theo Ed25519; không tự băm SHA-256 trước |
| `NONEwithRSA` / `NONEwithECDSA` | Không có digest tích hợp theo cách tên thuật toán quy định | Chỉ dùng khi giao thức/provider xác định chính xác input và encoding; không phải cách sửa tự động |

**Không sử dụng MD5/SHA-1 để tạo chữ ký mới.** Các thuật toán được provider hỗ trợ không mặc nhiên được chính sách bảo mật hiện đại cho phép; xem những danh sách vô hiệu và yêu cầu compliance của môi trường.

## 6. Chương trình Java 17+: chữ ký đúng, double hash sai và Ed25519

Chương trình dưới đây minh họa một giao thức ký **duy nhất** cho yêu cầu phê duyệt thanh toán. Ta xây chuỗi byte từ **domain + orderId + amount + currency**, rồi ký bằng `SHA256withRSA`. Đồng thời chương trình cố tình ký dữ liệu đã được băm trước để cho thấy chữ ký đó chỉ verify khi phía nhận cũng nhầm input theo cùng cách.

**Lưu ý:** RSA-2048 chỉ được tạo trong bộ nhớ để demo; public key được lấy từ cùng cặp khóa. Chương trình chưa giải quyết certificate trust, key storage, authorization, replay, signature envelope versioning hay thanh toán thật. Không có giá trị key/signature cố định được in ra.

Tạo file **`SigningBytesDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.text.Normalizer;
import java.util.Arrays;

public class SigningBytesDemo {
    private static void writeField(DataOutputStream out, String value)
            throws IOException {
        byte[] utf8 = Normalizer.normalize(value, Normalizer.Form.NFC)
                .getBytes(StandardCharsets.UTF_8);
        // Big-endian 4-byte length prefix + UTF-8 data.
        out.writeInt(utf8.length);
        out.write(utf8);
    }

    // Trả về canonical bytes cho một action thuộc domain đã xác định.
    private static byte[] canonicalPayment(
            String orderId, BigDecimal amount, String currency)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        writeField(out, "com.example.payment/approve/v1");
        writeField(out, orderId);
        writeField(out, amount.setScale(2, RoundingMode.UNNECESSARY)
                .toPlainString());
        writeField(out, currency);
        out.flush();
        return bytes.toByteArray();
    }

    private static byte[] sign(PrivateKey key, byte[] message)
            throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(message); // Engine tự thực hiện SHA-256(message).
        return signer.sign();
    }

    private static boolean verify(
            PublicKey key, byte[] message, byte[] signed)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(message);
        return verifier.verify(signed);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] message = canonicalPayment(
                "ORDER-104", new BigDecimal("125.50"), "VND");
        byte[] rebuilt = canonicalPayment(
                "ORDER-104", new BigDecimal("125.5"), "VND");

        byte[] signature = sign(pair.getPrivate(), message);
        System.out.println("canonicalBytesEqual=" +
                Arrays.equals(message, rebuilt));
        System.out.println("signatureValid=" +
                verify(pair.getPublic(), rebuilt, signature));

        // Cùng schema, khác số tiền => bytes khác => verify thất bại.
        byte[] changed = canonicalPayment(
                "ORDER-104", new BigDecimal("125.51"), "VND");
        System.out.println("changedAmountRejected=" +
                !verify(pair.getPublic(), changed, signature));

        // LỖI: gọi SHA-256 bên ngoài rồi lại ký bằng SHA256withRSA.
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(message);
        byte[] doubleHashedSignature = sign(pair.getPrivate(), digest);

        System.out.println("wrongDigestSignatureRejectsOriginal=" +
                !verify(pair.getPublic(), message, doubleHashedSignature));
        System.out.println("wrongDigestSignatureAcceptsDigest=" +
                verify(pair.getPublic(), digest, doubleHashedSignature));
        System.out.println("originalSignatureRejectsDigest=" +
                !verify(pair.getPublic(), digest, signature));

        // Ed25519 cũng nhận canonical message bytes; không prehash.
        KeyPairGenerator edGenerator =
                KeyPairGenerator.getInstance("Ed25519");
        KeyPair edKeys = edGenerator.generateKeyPair();
        Signature edSigner = Signature.getInstance("Ed25519");
        edSigner.initSign(edKeys.getPrivate());
        edSigner.update(message);
        byte[] edSignature = edSigner.sign();

        Signature edVerifier = Signature.getInstance("Ed25519");
        edVerifier.initVerify(edKeys.getPublic());
        edVerifier.update(message);
        System.out.println("ed25519Valid=" +
                edVerifier.verify(edSignature));
    }
}
```

Biên dịch/chạy với JDK 17+ thông dụng hỗ trợ RSA và Ed25519:

```shell
javac SigningBytesDemo.java
java SigningBytesDemo
```

**Stdout kỳ vọng:**

```text
canonicalBytesEqual=true
signatureValid=true
changedAmountRejected=true
wrongDigestSignatureRejectsOriginal=true
wrongDigestSignatureAcceptsDigest=true
originalSignatureRejectsDigest=true
ed25519Valid=true
```

### 6.1. Vì sao các dòng trên ổn định?

- `canonicalBytesEqual=true`: giá trị `125.50` và `125.5` đều trở thành `125.50` nhờ `setScale(2, RoundingMode.UNNECESSARY)`. `writeField` áp dụng cùng quy tắc NFC, UTF-8, thứ tự trường và length-prefix.
- `signatureValid=true`: RSA ký canonical message, và verifier sử dụng chính canonical message được tái tạo; byte giống nhau.
- `changedAmountRejected=true`: thay `125.50` thành `125.51` tạo message khác; chữ ký hợp lệ cho giá trị gốc không xác minh cho nội dung thay đổi.
- `wrongDigestSignatureRejectsOriginal=true`: chữ ký sai cách (ký digest bằng thuật toán đã SHA-256) **không hợp lệ** khi verifier làm đúng và cung cấp original message bytes.
- `wrongDigestSignatureAcceptsDigest=true`: cả hai phía cùng truyền digest như message vào thuật toán `SHA256withRSA`; verify vẫn **true**, minh họa vì sao “test xanh” không chứng minh triển khai khớp giao thức.
- `originalSignatureRejectsDigest=true`: chữ ký chuẩn của message không xác minh khi phía verify đưa digest bytes sai đầu vào.
- `ed25519Valid=true`: Ed25519 nhận đúng canonical message bytes; thuật toán tự thực hiện quy trình nội bộ theo đặc tả, không có bước `MessageDigest("SHA-256")` do ứng dụng áp thêm.

Vì RSA, Ed25519 keypair được sinh ngẫu nhiên mỗi lần chạy, không đưa signature bytes cụ thể vào expected stdout. Những boolean đều có ý nghĩa độc lập với giá trị key và chữ ký thực tế khi JDK/provider triển khai đúng chuẩn.

### 6.2. Bài demo chưa phải canonical protocol production

`writeField` và `canonicalPayment` chỉ là **một format minh họa**. Bản thật cần kiểm tối đa kích thước field, validate kiểu/mã tiền, null/empty, Unicode normalization thống nhất và xử lý phiên bản. Với thanh toán thật phải đưa thêm account/tenant, identifier, action, replay nonce/expiry và mọi trường có ảnh hưởng nghiệp vụ vào dữ liệu ký.

Sử dụng tên domain mẫu không biến một ứng dụng thành hệ thống thanh toán an toàn; phần quyết định còn gồm: ai cấp và tin public key, signing authority, authorization, key storage, chống replay, audit, giới hạn thời hạn và protocol interoperability.

## 7. Xử lý file lớn và streaming với `Signature.update`

Với file lớn, không cần đọc toàn bộ vào RAM và **không cần tự SHA-256 file rồi đưa digest vào `SHA256withRSA`**. Java cho phép gọi `update` nhiều lần trên các phần byte liên tiếp:

```java
Signature signer = Signature.getInstance("SHA256withRSA");
signer.initSign(privateKey);

try (InputStream in = Files.newInputStream(path)) {
    byte[] buffer = new byte[8192];
    int read;
    while ((read = in.read(buffer)) != -1) {
        if (read > 0) {
            signer.update(buffer, 0, read);
        }
    }
}
byte[] signature = signer.sign();
```

Đây là **đoạn minh họa không độc lập**: cần imports `java.security.Signature`, `java.io.InputStream`, `java.nio.file.Files` và biến `privateKey`, `path` hợp lệ trong method xử lý exception. Bên verify mở **chính file byte gốc** và gọi `Signature.update(buffer, 0, read)` theo thứ tự, sau đó `verify(signature)`. Chia thành các chunk 8192 byte hay kích thước khác **không thay đổi** message stream nếu thứ tự/byte identical; engine duy trì trạng thái digest nội bộ khi thuật toán có digest.

Quan trọng khi ký file:

- Không bỏ qua các byte 0, newline, BOM hoặc metadata thực sự nằm trong phạm vi file đã ký.
- Không đọc file một lần để tính hash rồi vô tình đọc một file đã bị thay đổi để ký: nếu có snapshot/concurrency threat, bảo đảm dữ liệu ký là cùng phiên bản với dữ liệu phát hành.
- Không phát hành signature cho file A rồi publish file B có nội dung thay đổi sau khi ký.
- Với file nhị phân, ưu tiên ký raw bytes; nếu ký manifest chứa hash, định nghĩa rõ nội dung manifest và cách xác thực kết quả khi verify.

### 7.1. Ký hash của file trong manifest khác với ký file trực tiếp

Ví dụ bạn có danh sách artifact:

```text
manifestVersion = 1
artifactA.sha256 = H(rawArtifactA)
artifactB.sha256 = H(rawArtifactB)
metadata = product, version, size, path, ...
signature = Sign(canonicalManifestBytes)
```

Ở đây, **canonicalManifestBytes** là message được ký; manifest chứa digest của file. Nếu `Sign` dùng `SHA256withRSA`, nó tiếp tục SHA-256 **manifest**, không phải double hashing lỗi nếu đây đúng là giao thức đã thống nhất.

Người nhận phải: xác minh chữ ký manifest bằng public key tin cậy → parse manifest an toàn → tính lại digest của từng artifact và so sánh → kiểm các ràng buộc đường dẫn, phiên bản, phạm vi và policy. Chỉ verify manifest mà không đối chiếu artifact là chưa hoàn thành quy trình integrity.

## 8. Ngoại lệ thực tế: HSM/KMS hoặc API ký prehashed input

Có những giao diện yêu cầu **message bytes**, cũng có giao diện yêu cầu **digest đã tính trước**. Đặc biệt khi làm việc với PKCS#11, HSM, KMS, API cloud hoặc thư viện bên thứ ba, cần đọc **hợp đồng cụ thể** thay vì đoán theo tên method `sign`.

### 8.1. Hai loại API không được trộn

**Loại A – ký message:**

```text
Input: raw/canonical M
Algorithm: SHA256withRSA (SHA-256 tính bên trong)
Output: chữ ký theo scheme
```

**Loại B – ký digest đã băm trước:**

```text
Input: H(M), độ dài chính xác theo thuật toán
Algorithm/service: API quy định input là PREHASHED DIGEST
Output: chữ ký ứng với M theo scheme xác định
```

Ở loại B, dịch vụ *có thể* xây dựng đúng `DigestInfo`/padding hoặc PSS encoding cho digest mà client gửi, hoặc có contract provider-specific khác; không được suy ra rằng nó đơn giản gọi một `Signature("SHA256withRSA").update(digest)` phía server. Phải xác định **exact digest scheme, digest length, parameter spec, encoding, padding, key type, wire format** và test vector từ nhà cung cấp.

Một trường `messageType = DIGEST` ở API nào đó chỉ có nghĩa khi tài liệu thật quy định hành vi xử lý digest. Không tự gán tên field đó cho Java `Signature`, vì JCA `update(...)` **không có flag “input đang là digest”**.

### 8.2. Đặc biệt với RSA/PKCS#1 v1.5

RSA signature kiểu PKCS#1 v1.5 với SHA-256 thường có **DigestInfo** bao quanh SHA-256 digest trước khi thực hiện signature primitive. **Raw RSA modular exponentiation của một digest 32 byte không tương đương `SHA256withRSA`**. Tự băm trước rồi chọn một thuật toán `NONEwithRSA` không bảo đảm provider sẽ mã hóa DigestInfo đúng hay tương thích với bên kia.

Cách an toàn trong JCA thường là: **truyền original message bytes vào `SHA256withRSA`**. Khi bắt buộc dùng API nhận digest, giao thức phải nêu rõ SDK có tạo DigestInfo và padding hay không, hoặc phần nào do HSM thực hiện. Đừng tự viết RSA padding hay encoding nếu có thư viện/scheme đã được kiểm chứng.

### 8.3. RSA-PSS: tham số cần đồng nhất

RSA-PSS không chỉ cần biết “SHA-256”. Cả signer và verifier phải thống nhất:

- digest của message, ví dụ SHA-256;
- thuật toán MGF (thường MGF1) và digest MGF1;
- độ dài salt, ví dụ 32 byte;
- trailer field và định dạng ký PSS.

Ví dụ cấu hình Java 17 mang tính minh họa:

```java
PSSParameterSpec spec = new PSSParameterSpec(
        "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);
Signature pss = Signature.getInstance("RSASSA-PSS");
pss.setParameter(spec);
pss.initSign(rsaPrivateKey);
pss.update(canonicalBytes);
byte[] signature = pss.sign();
```

Đây **không phải chương trình độc lập**: cần `java.security.Signature`, `java.security.spec.PSSParameterSpec`, `java.security.spec.MGF1ParameterSpec`, RSA private key và message bytes; provider có thể có yêu cầu về hỗ trợ/thứ tự cấu hình. Đặc biệt, với `RSASSA-PSS` đã cấu hình SHA-256, ứng dụng **không tự băm M trước khi gọi update**. Bên verify dùng `initVerify` và **cùng tham số** với canonical bytes giống hệt.

Hai chữ ký RSA-PSS của cùng message có thể có **signature bytes khác nhau** do salt ngẫu nhiên, trong khi verify đều true. Vì vậy test “chữ ký PSS phải bằng hệt byte ký lần trước” không phải kiểm đúng; test bằng verify và các vector chuẩn có kiểm soát.

### 8.4. ECDSA: cùng digest nhưng encoding signature có thể khác

`SHA256withECDSA` xử lý SHA-256 của message nội bộ theo scheme. Tuy nhiên signature representation có thể dùng **ASN.1 DER** (cặp `r, s` được encode theo DER) hoặc **IEEE P1363 fixed-width** theo tên thuật toán/contract. Hai bên có thể ký cùng M, cùng key và SHA-256 nhưng **khác định dạng signature bytes**.

Khi tích hợp giữa Java, OpenSSL, JWT/JWS, HSM hay các SDK khác, đừng chỉ hỏi “ECDSA SHA256 hay không”; phải kiểm **DER vs P1363/raw `r||s`**, curve, key format và contract. **Không** dùng `NONEwithECDSA` thay cho `SHA256withECDSA` khi không hiểu yêu cầu raw/prehashed của provider.

### 8.5. Ed25519: không tự thêm SHA-256

`Ed25519` là một scheme EdDSA định nghĩa cụ thể cách xử lý message và băm bên trong thuật toán. `Ed25519ph` là biến thể *prehash* có domain separation khác, **không tương đương** việc lấy SHA-256 của M rồi gọi Java `Ed25519.update(digest)`. Java 17 `Signature.getInstance("Ed25519")` thông thường nhận trực tiếp M; nếu giao thức yêu cầu prehashed variant, cần đúng chuẩn/triển khai có hỗ trợ thật, không chế bằng cách gọi `MessageDigest`.

**Câu hỏi bắt buộc cho tích hợp:** API nhận **message** hay **digest**? Thuật toán chính xác, params, prehash variant, signature encoding và byte canonicalization có trùng không?

## 9. Không được tách thuật toán khỏi cấu trúc dữ liệu và quyền kiểm tra

Một chữ ký cần một **verification context** rõ ràng. Tối thiểu, một signed envelope có thể bao gồm:

```text
version
message-type/domain
canonicalization-id
payload or stable payload reference
signature-algorithm and parameters
signing-key-id / certificate chain reference
signature bytes
timestamp / nonce / request-id if protocol requires
```

Các trường bên ngoài có thể cần thiết để chọn cách parse, nhưng **không vì thế mà tự được bảo vệ toàn vẹn**. Nếu attacker có thể sửa `algorithm`, `domain`, `keyId`, `canonicalizationId` hoặc payload reference để đổi cách verify/xử lý, thiết kế phải có **allowlist và ràng buộc xác thực metadata**, thường đưa các trường quan trọng vào chính message cần ký hoặc bảo vệ chúng theo cơ chế định dạng được chuẩn hóa.

### 9.1. Verifier xác minh nhiều hơn chữ ký

Quy trình kiểm chứng đúng:

1. Kiểm cấu trúc packet/giới hạn kích thước và version được chấp nhận, tránh parse ambiguity/DoS.
2. Xác định **domain/action** mong đợi từ endpoint thực, không tin claim “operation=approve” do client tùy ý đổi.
3. Dựng lại **đúng message bytes** theo canonicalization version; xác định mọi field quan trọng có nằm trong input không.
4. Chọn thuật toán và public key theo **server-side policy/allowlist**, xác định keyId/certificate thuộc danh tính được chấp thuận.
5. Gọi `Signature.initVerify`, `update(M)`, `verify(S)`; xử lý mọi sai lệch/exception như verification failure phù hợp.
6. Kiểm **trust chain, validity, certificate usage, revocation policy** khi dùng PKI; chữ ký đúng với một public key vô danh chưa chứng minh ai là người ký.
7. Kiểm business authorization (người ký có quyền approve khoản này không), tenant/object binding, expiry, nonce/sequence/replay control.
8. Chỉ sau các bước thích hợp mới thực hiện side effect/ghi dữ liệu; ghi audit ở mức cần thiết, không tiết lộ private key.

**Chữ ký không tự chống replay**: cùng một message và signature hợp lệ có thể được gửi lại. Việc đưa timestamp/nonce vào payload ký phải đi cùng **kiểm tra thời hạn và trạng thái chưa dùng** phía verifier.

### 9.2. Chữ ký không mã hóa dữ liệu

Chữ ký kiểm tính toàn vẹn/xác thực sở hữu private key, **không bảo mật nội dung message**. Một payload JSON đã ký vẫn có thể đọc được nếu truyền công khai. Nếu cần confidentiality, dùng TLS hoặc encryption/AEAD phù hợp, tách biệt với signature.

## 10. Tích hợp ký HTTP request/JSON: hợp đồng cụ thể

Một giao thức HTTP signing có thể ký:

```text
METHOD + "\n" +
CANONICAL_PATH + "\n" +
CANONICAL_QUERY + "\n" +
CANONICAL_HEADERS + "\n" +
BODY_DIGEST + "\n" +
TIMESTAMP + "\n" +
NONCE
```

**Đây là ví dụ cấu trúc khái niệm, không phải tiêu chuẩn HTTP signature để dùng trực tiếp.** Protocol cần xác định rõ canonical path, percent-encoding, query key sorting, duplicate query params, cách trim header, host, newline, charset, method case, chữ ký trên body bytes hay digest, giới hạn timestamp, nonce và header nào được bảo vệ.

Nếu protocol **đã định nghĩa `BODY_DIGEST = SHA256(rawBody)` là một field**, ký canonical request có field này bằng `SHA256withRSA` là hợp lệ: signer ký **request canonical bytes**, engine SHA-256 toàn bộ request. Điều này **khác** với việc lấy `SHA256(canonicalRequest)` rồi truyền digest vào một engine đã SHA-256.

Tương tự, nếu đã thống nhất ký JSON canonical theo RFC 8785, signer và verifier cần cùng chuẩn/phiên bản và đặc biệt thận trọng với dữ liệu số ngoài phạm vi JSON number mà chuẩn hỗ trợ. Với dữ liệu tài chính, có thể nên ký schema bytes riêng với money ở dạng decimal string/đơn vị nhỏ nhất, thay vì áp canonical JSON chung không xem xét giới hạn.

### 10.1. Đồng bộ test vector xuyên hệ thống

Để kiểm hệ thống Java ↔ JavaScript/Python/Go/HSM, chuẩn bị bộ test vector đã thống nhất gồm:

- **Input business fields** và ý nghĩa của từng trường.
- **Canonical bytes** dưới dạng hex/Base64 và chiều dài byte.
- **Digest của canonical bytes** dưới dạng hex chỉ để chẩn đoán, không làm input cho combined `Signature`.
- **Algorithm/key/public key/cert** test cố định, tham số RSA-PSS hoặc encoding ECDSA nếu có.
- **Expected signature** khi scheme deterministic và điều kiện phù hợp, hoặc **expected verification result** với scheme có randomness.
- Trường hợp negative: khác 1 byte, khác order/amount/tenant/domain, Unicode NFC vs NFD, LF vs CRLF, null/empty, JSON key order, timestamp format, unknown version, altered keyId, replay.

Khi mismatch, so sánh **canonical bytes trước**, sau đó algorithm/params/key và signature format. Đừng tốn thời gian nghi ngờ provider khi một bên ký UTF-8 LF còn bên kia ký UTF-16LE CRLF.

## 11. Các lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Cần kiểm | Nguyên nhân điển hình |
| --- | --- | --- |
| Java ký xong tự verify true, hệ thống khác false | Canonical byte array của **hai phía**, algorithm/params, signature encoding | Mỗi bên ký byte khác nhau hoặc bên này prehash, bên kia không |
| `SHA256withRSA` nhận 32 byte digest và verify phía khác thất bại | Ai đã gọi `MessageDigest` trước `Signature.update`? | Double hashing/inconsistent input |
| Cùng payload hiển thị, verify sai | UTF-8, Unicode NFC, newline, BOM, số/date, JSON ordering | Nội dung hiển thị giống nhưng byte khác |
| Chữ ký ECDSA không verify | Signature DER hay P1363; curve/format/key | Signature wire format khác nhau |
| RSA-PSS báo sai chữ ký | Digest, MGF1 hash, salt length, trailer, provider | PSS params không trùng hoặc ký sai input |
| Ed25519 trong Java không khớp phía khác | Ed25519 thuần hay Ed25519ph? Có tự SHA-256 trước không? | Nhầm scheme/prehash variant |
| `InvalidKeyException` | Loại private/public key và algorithm được chọn | RSA key với ECDSA algorithm hoặc key/provider không phù hợp |
| `NoSuchAlgorithmException` | Runtime/provider và tên thuật toán | Provider không hỗ trợ tên thuật toán cụ thể |
| `SignatureException` khi verify | Signature bytes, length, format/provider | Dữ liệu ký sai format hoặc signature encoding sai |
| Verify true nhưng nghiệp vụ sai | Các field đã ký và quyền người ký | Bỏ sót amount, tenant, action, expired request, replay |
| Thử sửa một field mà verify vẫn true | Field đó có thực sự nằm trong canonical bytes? | Ký thiếu dữ liệu nghiệp vụ quan trọng |
| Test so sánh hai chữ ký PSS/ECDSA thành false | Thuật toán có randomness trong nonce/salt ký | Nên test verify, không so signature bytes |
| Chữ ký hợp lệ với một key lạ | Trust store/PKI, binding key↔identity | Chưa xác thực public key thuộc chủ thể có quyền |

### 11.1. Cách debug hiệu quả

1. In **byte length** của canonical message ở hai phía, và hash fingerprint của canonical bytes **chỉ trong môi trường kiểm soát**. Đừng log plaintext nhạy cảm, secret/key/token.
2. Khi debug trong test, so sánh canonical bytes dạng hex/Base64 hoặc binary diff để xác định byte đầu tiên sai; dữ liệu test cần vô hại.
3. Kiểm tên `Signature.getAlgorithm()`, `getProvider()` và `PSSParameterSpec` khi áp dụng.
4. Kiểm kiểu public key, curve, certificate chain và signature encoding.
5. Viết negative tests cho các field ảnh hưởng nghiệp vụ để bảo đảm chúng thật sự nằm trong dữ liệu ký.
6. Nếu chỉ lỗi với dữ liệu Unicode hoặc số thập phân, kiểm normalization, encoding và canonical schema trước khi đổi thuật toán.

**Không** “sửa verify false” bằng cách băm thêm một lần ở phía nhận cho đến khi verify true. Việc đó có thể che giấu một sai lệch giao thức. Thay vào đó, xác định input chuẩn mà giao thức muốn bảo vệ, rồi sửa cả signing/verification contract cho đồng nhất.

## 12. Câu hỏi tự kiểm tra và đáp án

**1. Với `Signature("SHA256withRSA")`, `update` phải nhận message hay digest?**  
Trong sử dụng thông thường, nhận **message bytes nguyên bản/canonical**, vì engine đã xử lý SHA-256. Chỉ truyền digest nếu digest thực sự được định nghĩa là message cần ký, hoặc API riêng có contract prehash rõ ràng; không tự coi `Signature.update` là prehash API.

**2. Nếu signer và verifier cùng gọi `SHA256(M)` rồi dùng `SHA256withRSA`, verify true có chứng minh đúng không?**  
Không. Hai bên có thể nhất quán trong việc ký `H(M)` như message và do đó nhận `H(H(M))` ở tầng digest nội bộ, nhưng trái với hợp đồng ký M nếu hợp đồng yêu cầu như vậy.

**3. Vì sao không được nối `orderId + amount + currency` rồi ký?**  
Ranh giới trường có thể nhập nhằng, định dạng số không cố định; cần thứ tự, length-prefix/escaping, schema và representation rõ ràng.

**4. Có nên ký JSON text từ `HashMap.toString()` không?**  
Không. Dựa vào cách hiển thị object và thứ tự Map không tạo giao thức serialization ổn định. Chọn canonical serializer hoặc ký raw bytes theo hợp đồng.

**5. Hai timestamp cùng instant nhưng khác offset có verify được cùng signature không?**  
Không nếu hai chuỗi ký byte khác nhau. Muốn tương đương phải định nghĩa canonical time representation trước khi ký.

**6. `RSASSA-PSS` với SHA-256 có cần `MessageDigest.digest(M)` riêng không?**  
Không khi dùng Java `Signature("RSASSA-PSS")` với `PSSParameterSpec` quy định SHA-256; engine xử lý digest theo PSS scheme.

**7. Ed25519 có phải `SHA256withEd25519` không?**  
Không. Ed25519 là scheme riêng với xử lý nội bộ; không tự hash SHA-256 trước khi gọi `Signature("Ed25519")`.

**8. Chữ ký đúng với public key lấy từ request có chứng minh người gửi được tin không?**  
Không. Cần xác thực key/cert binding và authorization; nếu attacker tự tạo keypair rồi gửi public key của họ, verify vẫn true cho chữ ký họ tự tạo.

**9. Chữ ký có chống replay không?**  
Không. Cần ký nonce/timestamp/sequence và kiểm trạng thái/thời gian ở phía nhận.

**10. Ký manifest chứa file hashes có phải luôn là double hashing sai?**  
Không. Manifest là thông điệp M khác; digest của file là **data field** trong manifest. Đừng đánh đồng ký manifest với truyền SHA256(manifest) vào API có digest tích hợp.

**11. Vì sao cùng payload nhưng ký PSS hai lần có signature bytes khác nhau?**  
PSS dùng salt/ngẫu nhiên trong quá trình ký. So sánh raw signature bytes không phải test đúng; verify theo cùng thuật toán/params/key/message.

**12. Nếu cần ký digest qua HSM thì dùng `NONEwithRSA` luôn được chứ?**  
Không. Phải tuân hợp đồng HSM/PKCS#11 cụ thể về message hay digest, padding/DigestInfo/PSS encoding, độ dài digest và thuật toán. Dùng SDK chuẩn và test vector của provider.

## 13. Checklist đưa chữ ký số vào production

1. **Định nghĩa chính xác M:** raw bytes hay canonical schema? Test vector xác định byte length, hex và encoding.
2. **Ký đủ ngữ cảnh:** domain/purpose, version, user/tenant, action, resource, amount, timestamp, nonce/expiry nếu cần.
3. **Không nhập nhằng serialization:** tránh nối string đơn giản; quy định field order, type, numeric/time format, Unicode và length-prefix.
4. **Khớp thuật toán với key:** `SHA256withRSA`, `RSASSA-PSS`, `SHA256withECDSA`, `Ed25519` và params/encoding phù hợp.
5. **Không băm hai lần ngoài ý muốn:** với API `Signature` tích hợp digest, truyền message bytes; đừng đưa `MessageDigest.digest(M)` vào `update`.
6. **Không dùng raw signature scheme như shortcut:** prehashed APIs phải có hợp đồng rõ về padding/encoding và test vector.
7. **Xác minh signer identity:** trust public key/certificate, algorithm allowlist, keyId binding, validity/revocation policy và authorization.
8. **Chống replay:** sign nonce/time/sequence và thực thi policy kiểm tra ở verifier.
9. **An toàn khi vận hành:** bảo vệ private key, ưu tiên keystore/KMS/HSM theo nhu cầu; không log key/message nhạy cảm, không tạo digest debug như dữ liệu công khai nếu payload cần bí mật.
10. **Kiểm thử xuyên hệ thống:** success, sửa 1 byte, đổi domain/tenant/amount, sai key, sai params, Unicode, newline, JSON ordering, replay và downgrade.

## Tài liệu tham khảo chính thống

- [Java SE 17 – Signature](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html): các giai đoạn `initSign/initVerify → update → sign/verify`, tên thuật toán và trạng thái engine.
- [Java SE 17 – MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): hash độc lập và các phép `digest/update`.
- [Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html): provider, engine, chữ ký/digest và mô hình API Java.
- [Java SE 17 – PSSParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html) và [MGF1ParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html): các tham số cần thống nhất với RSA-PSS.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html): tên `SHA256withRSA`, `SHA256withECDSA`, `RSASSA-PSS`, `Ed25519` và các biến thể.
- [RFC 8017 – PKCS #1 v2.2](https://www.rfc-editor.org/rfc/rfc8017): các signature schemes RSA và quy tắc EMSA encoding.
- [RFC 8032 – Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032): Ed25519, Ed25519ph và quy định prehash/domain separation.
- [RFC 8785 – JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785): một cách xác định canonical JSON, kèm phạm vi áp dụng và ràng buộc biểu diễn.