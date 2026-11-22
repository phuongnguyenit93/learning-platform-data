# 9.8 Phân biệt chữ ký sai, dữ liệu sai định dạng và ngoại lệ khi xác minh

Khi xác minh chữ ký số trong Java, **“chữ ký không hợp lệ”**, **“dữ liệu đầu vào sai định dạng”** và **“quá trình xác minh phát sinh ngoại lệ”** là những tình huống khác nhau. Chúng có thể dẫn đến cùng quyết định nghiệp vụ là **không chấp nhận yêu cầu**, nhưng khác nhau về nguyên nhân, vị trí lỗi, cách xử lý, khả năng khắc phục và thông tin cần ghi nhận để vận hành.

Điểm cốt lõi: `java.security.Signature.verify(byte[])` có hai kết quả theo hợp đồng API: **`true`/`false`** khi thực hiện xong phép kiểm tra, hoặc **`SignatureException`** khi engine không thể xác minh như bình thường (ví dụ sai trạng thái, chữ ký sai encoding/loại hoặc provider không xử lý được). Trước khi tới `verify` còn có các lớp parse, giải mã Base64, nạp public key và chọn thuật toán, mỗi lớp có ngoại lệ riêng.

Bài này giúp bạn phân loại lỗi đúng tầng, viết nhánh xử lý an toàn và kiểm chứng hành vi bằng Java 17+.

## 1. Đặt đúng câu hỏi: đã đi tới bước xác minh mật mã chưa?

Quy trình nhận một chữ ký từ bên ngoài thường có nhiều bước:

~~~text
Payload / request từ bên ngoài
  |
  v
[1] Validate request schema, giới hạn kích thước, trường bắt buộc
  |  lỗi -> MALFORMED_INPUT (chưa tới Signature)
  v
[2] Decode Base64/Base64URL/hex/PEM theo contract
  |  lỗi -> MALFORMED_ENCODING (chưa tới Signature)
  v
[3] Nạp public key đúng định dạng, kiểm tra nguồn tin cậy
  |  lỗi parse -> INVALID_KEY_FORMAT
  |  lỗi trust/certificate -> TRUST_FAILURE
  v
[4] Chọn algorithm + parameters và gọi Signature.getInstance(...)
  |  lỗi -> ALGORITHM_OR_CONFIGURATION_ERROR
  v
[5] Signature.initVerify(trustedPublicKey)
  |  lỗi -> INVALID_KEY_OR_PROVIDER_ERROR
  v
[6] Signature.update(EXACT_MESSAGE_BYTES)
  |  lỗi state/processing -> SignatureException
  v
[7] Signature.verify(signatureBytes)
  |
  +-- true  -> VALID_CRYPTOGRAPHIC_SIGNATURE
  +-- false -> NOT_VERIFIED
  +-- SignatureException -> VERIFICATION_PROCESSING_ERROR
                               (có thể liên quan format chữ ký)
~~~

**Không có bảo đảm rằng mọi chữ ký sai định dạng đều bị phát hiện trước `verify`.** Một số định dạng chỉ được provider giải mã trong `verify`. Tùy scheme/provider, đầu vào bất thường có thể cho `false` hoặc ném `SignatureException`. Muốn phân biệt format và sai phép toán mật mã với độ tin cậy cao, cần **contract encoding rõ ràng và kiểm tra những điều kiện cấu trúc có thể kiểm tra an toàn trước khi verify**.

Ngược lại, `verify(...) == true` chỉ chứng minh **chữ ký toán học phù hợp với message bytes, public key và bộ tham số đã dùng**. Nó không tự chứng minh public key thực sự thuộc người dùng mong muốn, chứng chỉ còn hiệu lực hay yêu cầu chưa bị phát lại.

## 2. Phân loại ba nhóm kết quả chính

| Nhóm | Ví dụ | Kết quả API điển hình | Ý nghĩa chính xác |
| --- | --- | --- | --- |
| **Chữ ký không khớp** | Sửa nội dung, ký bằng private key của người khác, truyền sai chữ ký hợp lệ về cấu trúc | `Signature.verify(sig) == false` | Phép kiểm tra với **message/key/algorithm/parameters hiện tại** không thành công. |
| **Đầu vào sai định dạng** | Base64 hỏng, JSON/PEM không hợp lệ, public key DER hỏng, chữ ký không đúng representation | `IllegalArgumentException` từ Base64, `InvalidKeySpecException` từ KeyFactory, hoặc `false`/**`SignatureException`** từ Signature | Cần chỉ ra **tầng parse/format** xảy ra lỗi; không gộp tất cả thành `verify == false`. |
| **Ngoại lệ trong quá trình xác minh** | Key không tương thích, engine chưa `initVerify`, thuật toán/provider không có, parameters sai, provider không xử lý được | `InvalidKeyException`, `SignatureException`, `NoSuchAlgorithmException`, `InvalidAlgorithmParameterException`... | Có thể là lỗi cấu hình, input, trạng thái hoặc provider; phân loại theo **API và ngữ cảnh**, không chỉ tên exception. |

**Điểm cần nhớ:** phân loại này mô tả **vị trí và ý nghĩa vận hành**. Không phải ba nhánh loại trừ hoàn toàn ở mức mã nguồn: một chữ ký sai định dạng có thể chính là nguyên nhân khiến `Signature.verify` ném `SignatureException`. Ngoại lệ **không mặc nhiên** chứng minh hệ thống bị lỗi nội bộ; đó cũng có thể là phản ứng hợp lệ trước đầu vào của kẻ tấn công.

### Các câu hỏi chẩn đoán

1. Request có parse được và vượt qua giới hạn kích thước chưa?
2. Chuỗi chữ ký có đúng encoding mà giao thức đã thỏa thuận không?
3. Public key có đúng định dạng, loại khóa và **nguồn tin cậy** không?
4. Engine có được khởi tạo bằng `initVerify` và update đúng byte đã ký không?
5. Với đầu vào đã qua các tầng trên, `verify` trả **`false`** hay phát sinh **exception** nào, tại dòng nào?

## 3. `Signature.verify`: `true`, `false` và `SignatureException`

Chu trình chuẩn khi xác minh:

~~~java
Signature verifier = Signature.getInstance("SHA256withRSA");
verifier.initVerify(trustedPublicKey);
verifier.update(messageBytes);
boolean accepted = verifier.verify(signatureBytes);
~~~

Đây là **đoạn API minh họa**, không chạy độc lập; ví dụ đầy đủ ở mục 5.

- **`true`:** chữ ký phù hợp với **đúng các byte** đã truyền bằng `update`, theo thuật toán và public key đã chọn.
- **`false`:** chữ ký không được xác minh. Đầu vào sai message, sai public key **cùng loại**, chữ ký bị thay đổi hoặc không khớp scheme/parameters có thể dẫn đến `false`.
- **`SignatureException`:** engine gặp lỗi khi xử lý. API nêu các khả năng như engine chưa khởi tạo, signature encoding/loại không hợp lệ hoặc phép xác minh không thể xử lý input. Có thể phải từ chối yêu cầu đồng thời ghi lại lỗi đã được chuẩn hóa ở phía server.

Không xem mọi `SignatureException` là sự cố JVM; cũng **không khẳng định đầu vào có cấu trúc hợp lệ chỉ vì `verify` trả `false`**. Các provider có thể quyết định khác nhau ở biên dữ liệu hỏng.

Ví dụ, RSA 2048-bit có chữ ký dạng byte với độ dài **256 byte** đối với cơ chế chuẩn. Nếu nhận 255 byte, một provider có thể ném `SignatureException` vì sai chiều dài; không được dựa vào việc một provider đã trả exception để kết luận mọi provider sẽ làm như vậy. Một tầng validation có thể kiểm tra độ dài theo public key RSA, nhưng vẫn cần để `Signature` kiểm tra mật mã.

### Phải xác minh trên byte-for-byte cùng thông điệp

~~~text
Ký:       bytes("amount=100", UTF-8) -> signature
Xác minh: bytes("amount=100", UTF-8) -> true (nếu key/scheme khớp)
Xác minh: bytes("amount=900", UTF-8) -> false
Xác minh: bytes("amount=100\n", UTF-8) -> false
~~~

Chữ ký số áp dụng lên **byte**, không áp dụng lên “ý nghĩa logic” của chuỗi. Những thay đổi sau có thể làm chữ ký không khớp dù màn hình hiển thị tương tự:

- JSON đổi thứ tự field, khoảng trắng, cách biểu diễn số hoặc escaping.
- LF và CRLF, UTF-8 và encoding khác.
- Unicode có hai cách biểu diễn tương đương về hiển thị nhưng khác chuỗi byte.
- Dữ liệu đã nén/giải nén, URL-encoding, thay đổi header trong phần thông điệp có ký.
- Xác minh **raw payload** trong khi bên ký đã ký hash/canonical form khác, hoặc ngược lại.

Nếu giao thức yêu cầu canonicalization, hai phía phải dùng **cùng một quy tắc đã chuẩn hóa**. Không tự `trim()`, sắp xếp JSON hoặc chuẩn hóa Unicode khi verify nếu giao thức không quy định: hành động đó có thể làm thay đổi dữ liệu đã ký và gây false hoặc tạo khác biệt ngữ nghĩa khó kiểm soát.

## 4. Kiểm tra input format trước khi vào crypto

### 4.1. Lỗi Base64 và Base64URL

Một giao thức thường gửi chữ ký qua JSON/HTTP dưới dạng văn bản. Phải chọn **một encoding đã thỏa thuận**:

~~~java
// Base64 chuẩn có '+' và '/':
byte[] sigBytes = Base64.getDecoder().decode(signatureText);

// Base64URL có '-' và '_':
byte[] sigUrlBytes = Base64.getUrlDecoder().decode(signatureText);
~~~

Hai dòng trên là hai **lựa chọn khác nhau**, không phải phải gọi cả hai. Nếu text chứa ký tự không hợp lệ, decoder có thể ném `IllegalArgumentException`. Đây là lỗi **input encoding trước xác minh**, không phải `SignatureException`.

Đừng mặc định `Base64.getMimeDecoder()` cho mọi API vì MIME decoder có chính sách bỏ qua một số ký tự ngoài alphabet; nếu giao thức cần encoding chặt chẽ, dùng decoder đúng loại, giới hạn kích thước và cấu trúc trước khi parse. Độ dài chuỗi Base64 không nói được chữ ký hợp lệ về mặt mật mã.

### 4.2. Public key format và certificate format

Một public key RSA được xuất thành DER **SubjectPublicKeyInfo** (SPKI) có thể đọc bằng:

~~~java
byte[] spkiBytes = ...; // Byte DER hợp lệ do nguồn tin cậy cung cấp.
PublicKey publicKey = KeyFactory.getInstance("RSA")
        .generatePublic(new X509EncodedKeySpec(spkiBytes));
~~~

Đây chỉ là mảnh minh họa. Tên `X509EncodedKeySpec` khiến nhiều người nhầm: nó biểu diễn **SPKI public key**, **không phải toàn bộ certificate X.509**. Với certificate X.509 cần `CertificateFactory.getInstance("X.509")` đọc cấu trúc chứng chỉ, sau đó dùng `getPublicKey()` và **xác thực chuỗi tin cậy, hiệu lực, chính sách chứng chỉ, thu hồi** bằng cơ chế phù hợp.

Nếu `spkiBytes` không đúng encoding/algorithm, `KeyFactory.generatePublic` có thể ném **`InvalidKeySpecException`**. Trong khi đó, certificate hỏng có thể ném **`CertificateException`** từ certificate parser. Không gọi những lỗi này là “chữ ký sai” khi chưa có phép `Signature.verify` nào chạy.

### 4.3. Chữ ký nhị phân cũng có định dạng

Không phải mọi chữ ký đều chỉ là mảng byte độ dài tùy ý:

| Signature scheme | Biểu diễn thường gặp qua Java JCA | Hệ quả khi parse/verify |
| --- | --- | --- |
| `SHA256withRSA` (PKCS#1 v1.5) | Chữ ký RSA dạng khối có **độ dài bằng modulus** (ví dụ 256 byte cho RSA-2048) | Chữ ký ngắn/dài bất thường có thể bị từ chối bằng `SignatureException` hoặc kết quả không verify tùy triển khai. |
| `RSASSA-PSS` | Chữ ký RSA cũng có độ dài theo modulus; cần đúng **hash, MGF, saltLength, trailerField** | Khác tham số với phía ký có thể gây fail hoặc lỗi cấu hình. |
| `SHA256withECDSA` | Thường là cấu trúc ASN.1 **DER SEQUENCE của hai INTEGER `r` và `s`** | Chữ ký DER hỏng có thể làm provider báo `SignatureException`; chiều dài DER **không luôn cố định**. |
| `SHA256withECDSAinP1363Format` | Biểu diễn IEEE P1363: byte dạng **`r \|\| s`**, mỗi số có độ rộng cố định | Với P-256, thường 64 byte; **không tương thích byte-for-byte** với DER mặc định. |
| `Ed25519` | Chữ ký Ed25519 thông thường **64 byte** | Đúng chiều dài vẫn chưa chứng minh chữ ký đúng; chỉ verify mới chứng minh được. |

Lưu ý tên thuật toán Java phải khớp với **signature representation**. Ví dụ gọi `SHA256withECDSA` trên một chữ ký `r||s` 64 byte từ thư viện khác thường không hoạt động nếu chưa chuyển định dạng đúng, hoặc dùng đúng thuật toán `...inP1363Format` được provider hỗ trợ. Đừng cắt hoặc thêm byte tùy tiện để “đủ độ dài”.

Đối với RSA chữ ký phải giữ nguyên **byte đầu giá trị 0** nếu có: chuyển qua `BigInteger` rồi serialize tùy tiện có thể làm mất leading zero hoặc tạo byte dấu, khiến đầu vào sai chiều dài.

## 5. Java 17+: phân biệt chữ ký đúng, sai message, sai key và chữ ký bị cắt

Tệp **`SignatureOutcomesDemo.java`** tạo cặp khóa RSA 2048-bit để học, ký chuỗi `"amount=100"`, rồi xác minh các tình huống. Trong ví dụ, **`SHA256withRSA`** là scheme RSA PKCS#1 v1.5 cho mục tiêu quan sát API; với thiết kế chữ ký RSA mới, cân nhắc RSASSA-PSS nếu giao thức cho phép và quy định đầy đủ tham số.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.Arrays;

public class SignatureOutcomesDemo {
    static boolean check(
            PublicKey key, byte[] data, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();
        KeyPair other = generator.generateKeyPair();

        byte[] data = "amount=100".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(data);
        byte[] signed = signer.sign();

        System.out.println("Correct signature: " +
                check(pair.getPublic(), data, signed));

        System.out.println("Changed data: " +
                check(pair.getPublic(),
                        "amount=900".getBytes(StandardCharsets.UTF_8),
                        signed));

        System.out.println("Other RSA key: " +
                check(other.getPublic(), data, signed));

        byte[] truncated = Arrays.copyOf(signed, signed.length - 1);
        boolean rejected;
        try {
            rejected = !check(pair.getPublic(), data, truncated);
        } catch (SignatureException expected) {
            rejected = true;
        }
        System.out.println("Truncated signature rejected: " + rejected);
    }
}
~~~

Chạy bằng Java 17+:

~~~bash
javac SignatureOutcomesDemo.java
java SignatureOutcomesDemo
~~~

Stdout:

~~~text
Correct signature: true
Changed data: false
Other RSA key: false
Truncated signature rejected: true
~~~

Phân tích:
1. Đúng **message bytes + public key + scheme + signature** → `true`.
2. Đổi nội dung thành `amount=900`, giữ chữ ký cũ → `false` (chữ ký không chứng minh message mới).
3. Dùng public key RSA khác, vẫn đúng **loại** khóa → thường `false` vì không khớp private key đã ký.
4. Cắt mất một byte signature RSA → **bị từ chối**. Ví dụ chấp nhận **hai cách provider có thể báo từ chối**: `verify` trả `false` hoặc ném `SignatureException`. Dòng stdout cuối kiểm tra **không chấp nhận**, thay vì gán cố định một loại exception cho mọi JVM.

Ở ví dụ trên, bắt `SignatureException` chỉ để minh họa đối với chữ ký **bị cắt trong thử nghiệm**; dịch vụ thật không nên nuốt mọi ngoại lệ bằng `return false` rồi mất khả năng phân biệt lỗi provider hay lập trình. Tầng service cần ghi nhận loại nguyên nhân nội bộ, còn bên ngoài chỉ thấy kết quả từ chối được chuẩn hóa.

## 6. Java 17+: ngoại lệ trước và trong `verify`

Tệp **`VerificationErrorsDemo.java`** lần lượt tạo những lỗi cố ý tại các tầng khác nhau. Các byte hỏng trong ví dụ **chỉ dùng để kiểm thử parser**, không phải khóa/chữ ký hợp lệ.

~~~java
import java.security.*;
import java.security.spec.*;
import java.util.Base64;

public class VerificationErrorsDemo {
    public static void main(String[] args) throws Exception {
        try {
            Base64.getDecoder().decode("not_base64!!!");
            throw new AssertionError("Base64 should have failed");
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid Base64: IllegalArgumentException");
        }

        try {
            KeyFactory.getInstance("RSA").generatePublic(
                    new X509EncodedKeySpec(new byte[] {0x30, 0x00}));
            throw new AssertionError("Invalid key was accepted");
        } catch (InvalidKeySpecException expected) {
            System.out.println("Invalid public key DER: InvalidKeySpecException");
        }

        KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
        ec.initialize(new ECGenParameterSpec("secp256r1"));
        PublicKey ecKey = ec.generateKeyPair().getPublic();

        try {
            Signature.getInstance("SHA256withRSA").initVerify(ecKey);
            throw new AssertionError("EC key was accepted for RSA");
        } catch (InvalidKeyException expected) {
            System.out.println("Wrong key type: InvalidKeyException");
        }

        try {
            Signature uninitialized = Signature.getInstance("SHA256withRSA");
            uninitialized.verify(new byte[256]);
            throw new AssertionError("Uninitialized verifier was accepted");
        } catch (SignatureException expected) {
            System.out.println("Uninitialized verifier: SignatureException");
        }

        try {
            Signature.getInstance("NotARealSignatureAlgorithm");
            throw new AssertionError("Unsupported algorithm was accepted");
        } catch (NoSuchAlgorithmException expected) {
            System.out.println("Unknown algorithm: NoSuchAlgorithmException");
        }
    }
}
~~~

~~~bash
javac VerificationErrorsDemo.java
java VerificationErrorsDemo
~~~

Stdout trên JDK có các thuật toán chuẩn RSA và EC P-256:

~~~text
Invalid Base64: IllegalArgumentException
Invalid public key DER: InvalidKeySpecException
Wrong key type: InvalidKeyException
Uninitialized verifier: SignatureException
Unknown algorithm: NoSuchAlgorithmException
~~~

**Điểm khác nhau theo từng dòng:**

- `IllegalArgumentException` ở `Base64.decode`: input vận chuyển sai cú pháp; **chưa hề khởi tạo engine `Signature`**.
- `InvalidKeySpecException` ở `KeyFactory.generatePublic`: byte DER public key không chuyển được thành key hợp lệ; không phải `verify == false`.
- `InvalidKeyException` ở `initVerify`: public key EC không tương thích với scheme `SHA256withRSA`. Nếu cung cấp một RSA public key khác nhưng hợp lệ, `initVerify` có thể thành công và `verify` mới trả `false`.
- `SignatureException` ở `verify` khi chưa `initVerify`: **sai vòng đời API của ứng dụng**, khác với chữ ký mật mã sai thông thường.
- `NoSuchAlgorithmException` tại `Signature.getInstance`: tên thuật toán giả không tồn tại; đây là lỗi chọn engine/configuration, không phải kết quả xác minh.

Không mặc định chính xác *thông điệp* exception của provider; log có thể khác theo JDK. Ví dụ chỉ in **tên lớp lỗi** mà đã biết, tránh khóa vào text implementation-specific.

## 7. Bảng ánh xạ lỗi theo API Java

| Giai đoạn/API | Ngoại lệ/kết quả | Ý nghĩa | Hướng xử lý |
| --- | --- | --- | --- |
| Parse JSON/HTTP/request schema | Exception của thư viện parser; lỗi validation | Dữ liệu request thiếu field, kiểu sai, encoding/size sai | Trả lỗi input; không đưa nội dung chưa hợp lệ xuống JCA. |
| `Base64.Decoder.decode` | `IllegalArgumentException` | Chuỗi Base64 không phù hợp loại decoder đã chọn | Từ chối encoding; giới hạn kích thước để chống abuse. |
| Đọc file/key/cert qua stream | `IOException` | Tệp/transport không đọc được | Phân biệt vấn đề I/O với chữ ký không khớp. |
| `KeyFactory.generatePublic` | `InvalidKeySpecException` | Public key encoded format/algorithm không hợp lệ hoặc không được hỗ trợ | Kiểm tra SPKI/DER, thuật toán, nguồn cấp key. |
| `CertificateFactory.generateCertificate` | `CertificateException` | Chứng chỉ parse không hợp lệ | Kiểm tra định dạng cert, sau đó xử lý trust chain riêng. |
| `Signature.getInstance` | `NoSuchAlgorithmException` | Engine/algorithm không được cung cấp | Kiểm tra allowlist, provider và môi trường. |
| `Signature.getInstance(algorithm, name)` | `NoSuchProviderException` | Tên provider yêu cầu chưa được đăng ký | Kiểm tra cấu hình, không tự fallback nếu policy bắt buộc provider. |
| `Signature.initVerify(publicKey)` | `InvalidKeyException` | Key sai loại, format, tham số hoặc không phù hợp provider | Kiểm tra thuật toán/cặp khóa/trust, phân biệt key cùng loại nhưng sai chủ thể. |
| `Signature.setParameter(spec)` | `InvalidAlgorithmParameterException` | Parameters không phù hợp scheme/provider | Kiểm tra PSS hash/MGF/saltLength và yêu cầu giao thức. |
| `Signature.update(data)` | `SignatureException` | Engine sai trạng thái hoặc không thể xử lý input | Kiểm tra lifecycle, provider, input stream và trạng thái. |
| `Signature.verify(signatureBytes)` | **`true`** | Kiểm tra mật mã thành công | Chỉ chấp nhận sau khi kiểm tra khóa tin cậy, policy, context. |
| `Signature.verify(signatureBytes)` | **`false`** | Chữ ký không được xác minh với input hiện tại | Từ chối; không tự động tuyên bố “định dạng hợp lệ”. |
| `Signature.verify(signatureBytes)` | `SignatureException` | Engine không thể xử lý/verify; có thể do state hoặc signature encoding/type | Từ chối; phân tích có kiểm soát vì nguyên nhân phụ thuộc provider. |
| Các API runtime/provider khác | `ProviderException` hay lỗi không kiểm tra | Có thể biểu thị vấn đề provider/hạ tầng | Từ chối và ghi nhận cảnh báo vận hành; không chuyển sang thuật toán yếu. |

Các ngoại lệ được liệt kê là **điển hình**, không phải danh mục tuyệt đối cho mọi thư viện/protocol. Ví dụ certificate chain có thể parse thành công nhưng **không được tin cậy** vì hết hạn, không phù hợp KeyUsage, thiếu chain, bị thu hồi hoặc hostname không hợp lệ; đó là vấn đề **trust/policy**, không nhất thiết là `CertificateException` ở bước parse ban đầu.

### `initVerify` với certificate khác `CertificateFactory`

`Signature.initVerify(Certificate)` là overload có thể lấy public key từ certificate; với chứng chỉ X.509, API có thể kiểm tra ràng buộc KeyUsage liên quan chữ ký số. Tuy nhiên **nó không tự thay thế** quy trình PKIX path validation, kiểm tra chứng chỉ tin cậy và các ràng buộc của giao thức. Phải kiểm chứng trust **trước khi** coi `verify == true` là bằng chứng danh tính.

## 8. RSASSA-PSS: tham số sai có thể trông giống chữ ký sai

Các scheme ký RSA không thể bị coi là tương đương chỉ vì đều dùng RSA public/private key:

- `SHA256withRSA` thường là RSASSA-PKCS1-v1_5 kết hợp SHA-256.
- `RSASSA-PSS` là scheme RSA-PSS cần xác định **digest**, **MGF**, **salt length** và **trailer field**.
- Hai bên phải thống nhất chính xác algorithm + parameters; nếu không sẽ dẫn đến `false` hoặc lỗi khởi tạo/xử lý tùy nguyên nhân và provider.

### Ví dụ Java 17+: ký/xác minh PSS với parameters thống nhất

Tệp **`PssParameterDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.*;

public class PssParameterDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        PSSParameterSpec parameters = new PSSParameterSpec(
                "SHA-256", "MGF1", MGF1ParameterSpec.SHA256, 32, 1);
        byte[] data = "contract=v1".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("RSASSA-PSS");
        signer.setParameter(parameters);
        signer.initSign(pair.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("RSASSA-PSS");
        verifier.setParameter(parameters);
        verifier.initVerify(pair.getPublic());
        verifier.update(data);
        System.out.println("PSS with matching parameters: " +
                verifier.verify(signature));
    }
}
~~~

~~~bash
javac PssParameterDemo.java
java PssParameterDemo
~~~

Stdout:

~~~text
PSS with matching parameters: true
~~~

Ví dụ chọn **SHA-256**, `MGF1(SHA-256)`, **salt length 32 byte** và **trailerField 1**. Đây là các tham số **của chữ ký PSS**, không phải salt mật khẩu. Cần chọn tham số theo giao thức, không chỉ vì demo chạy thành công.

Nếu verifier dùng `PSSParameterSpec` khác với signer, đừng tự suy ra chắc chắn `SignatureException` hay `false`: có thể bị từ chối khi `setParameter/initVerify` hoặc đến `verify` tùy loại khác biệt. **Quy tắc vận hành đúng** là xác minh chính xác danh tính scheme/parameters đã được phê duyệt, không fallback tùy tiện giữa RSA-PSS và PKCS#1 v1.5.

Đầu vào `algorithm` hoặc `saltLength` từ request **không nên được tin cậy và áp dụng trực tiếp**: phải tra từ key policy, phiên bản giao thức hoặc allowlist cố định. Điều này ngăn algorithm-confusion/downgrade.

## 9. Có được dùng “chữ ký sai”, “dữ liệu sai định dạng”, “lỗi server” làm ba response HTTP riêng?

**Quyết định bảo mật bên ngoài thường giống nhau:** không chấp nhận thao tác nhạy cảm nếu chưa xác minh thành công. Nhưng hệ thống cần **phân loại nội bộ rõ ràng** để vận hành, thay vì nuốt hết exception.

Một mô hình xử lý có thể là:

| Trạng thái nội bộ | Tầng phát hiện | Hành động |
| --- | --- | --- |
| `VERIFIED` | `verify` trả `true` | Tiếp tục kiểm tra trust, context, expiry, replay và policy trước khi phê duyệt. |
| `NOT_VERIFIED` | `verify` trả `false` | Từ chối; đếm số lần thất bại và giám sát hành vi bất thường. |
| `MALFORMED_REQUEST` | Parser/schema/size | Từ chối dữ liệu; ghi nhận loại lỗi format, không log payload nhạy cảm. |
| `MALFORMED_ENCODING` | Base64/PEM/DER/key parse | Từ chối; chỉ định nội bộ tầng parse đã lỗi. |
| `VERIFICATION_EXCEPTION` | `Signature.update/verify` ném `SignatureException` | Từ chối; lưu thông tin đã chuẩn hóa (stage/algorithm/provider/loại exception) để chẩn đoán. |
| `SECURITY_CONFIGURATION_ERROR` | Algorithm/provider/key/PSS parameters không hợp lệ | Từ chối; cảnh báo cấu hình, không tự downgrade hoặc bỏ kiểm tra chữ ký. |
| `UNTRUSTED_KEY_OR_CONTEXT` | PKI/key registry/policy | Từ chối ngay cả khi phép toán chữ ký có thể trả `true`. |

### Bảo vệ tính riêng tư và tránh lỗi oracle

Bên ngoài có thể trả lỗi chung kiểu **“Yêu cầu xác thực không hợp lệ”**, với status HTTP phù hợp quy ước API, vì không nên đưa thông điệp provider, chi tiết private key, internal key ID hoặc logic kiểm tra cho đối phương để dò cấu hình. Không phải mọi lỗi đều phải giả làm HTTP 401: request sai cú pháp có thể dùng 400; lỗi cấu hình/hạ tầng có thể dùng 5xx. Mấu chốt là **không chấp nhận yêu cầu** và hạn chế tiết lộ thông tin không cần thiết.

Ở log nội bộ, nên ghi có cấu trúc: `stage`, `outcome`, `algorithm` thuộc allowlist, provider, public-key identifier đã được rút gọn hoặc băm, correlation ID, kiểu ngoại lệ và số byte sau kiểm tra size. Không log private key, token, thông điệp chứa dữ liệu cá nhân hay raw chữ ký trong log phổ thông; tránh dùng exception string không được sanitize làm trường log công khai.

Đừng viết đoạn tương đương:

~~~java
try {
    return verifier.verify(signatureBytes);
} catch (Exception ignored) {
    return true; // cực kỳ nguy hiểm: fail-open
}
~~~

Và đừng **silently** chuyển tất cả exception thành `false` mà không còn log/correlation trong dịch vụ cần chẩn đoán. Nhánh sai định dạng, provider configuration và sai mật mã có nguyên nhân khác nhau; dù đều dẫn đến từ chối, chúng cần tín hiệu vận hành riêng.

## 10. Cách viết luồng verify có kiểm tra chính xác theo tầng

Đây là **pseudocode định hướng**, không phải một tệp Java độc lập, vì parser, key registry, schema và trust-policy là thành phần phụ thuộc ứng dụng:

~~~text
1. validateRequestSizeAndSchema(request)
   -> nếu không hợp lệ: MALFORMED_REQUEST

2. algorithmPolicy = resolveApprovedSignatureSuite(request.context)
   -> không lấy scheme nguy hiểm/trống tùy ý từ request

3. signatureBytes = strictDecode(request.signatureText, contract.encoding)
   -> lỗi decode: MALFORMED_ENCODING

4. trustedPublicKey = trustedKeyRegistry.lookup(request.keyId, context)
   -> không thấy/không tin cậy: UNTRUSTED_KEY_OR_CONTEXT
   -> lỗi key format: MALFORMED_KEY_OR_CONFIG

5. validateKnownFormatConstraints(signatureBytes, trustedPublicKey, algorithmPolicy)
   -> nếu có vi phạm rõ ràng: MALFORMED_SIGNATURE

6. messageBytes = exactSignedBytes(request, contract)
   -> canonicalization/encoding theo giao thức, không làm khác bên ký

7. verifier = Signature.getInstance(algorithmPolicy.algorithm)
   -> nếu cần: verifier.setParameter(algorithmPolicy.parameters)
   verifier.initVerify(trustedPublicKey)
   verifier.update(messageBytes)
   result = verifier.verify(signatureBytes)

8. result == true:
     cần kiểm tra thêm trust, expiry, context, anti-replay... rồi mới ACCEPT
   result == false:
     NOT_VERIFIED -> REJECT
   SignatureException:
     VERIFICATION_EXCEPTION -> REJECT và chẩn đoán có kiểm soát
   key/algorithm/provider/parameter exception:
     SECURITY_CONFIGURATION_ERROR -> REJECT + ALERT
~~~

**Lưu ý khi thiết kế format validation:** chỉ kiểm tra các thuộc tính được đảm bảo bởi **format đã chọn**. RSA signature length bằng kích thước modulus theo byte là ví dụ hợp lý; ECDSA DER là cấu trúc có độ dài biến thiên, không được bắt buộc bằng 64 byte. Không viết một parser DER/PKCS#1/EdDSA tự chế để “phòng lỗi” nếu provider/thư viện đã có API kiểm tra được kiểm toán.

**Lưu ý khi dùng `Signature`:** đây là đối tượng có **trạng thái**. Với mỗi phép xác minh, tạo mới hoặc quản lý riêng instance và lifecycle; không chia sẻ tùy tiện cùng đối tượng `Signature` cho nhiều thread hoặc gọi `update` sau khi đã verify mà giả định state luôn giống ban đầu.

## 11. Case study: vì sao cùng “signature invalid” có nhiều nguyên nhân?

### Case A — byte message thay đổi ở đường truyền

Client ký byte UTF-8 của `{"amount":100}`; server serialize lại JSON thành `{"amount":100.0}` rồi verify. Chuỗi byte khác nên `verify` thường trả `false`, dù ý nghĩa nghiệp vụ có thể tương tự. Cách sửa là định nghĩa dữ liệu cần ký (raw bytes, canonical JSON hoặc structured signing protocol) và kiểm thử nhất quán ở cả hai đầu.

### Case B — Base64URL được decode bằng Base64 chuẩn

Chuỗi có dấu `-` hoặc `_` theo Base64URL nhưng server dùng `Base64.getDecoder()`. Decoder chuẩn có thể ném `IllegalArgumentException`; lỗi xảy ra **trước** `Signature`. Cách sửa là đưa encoding vào hợp đồng giao thức, dùng decoder đúng và validate đầu vào.

### Case C — ECDSA ký ở hệ thống khác bằng P1363, Java chờ DER

Bên ký gửi 64 byte `r||s` của P-256; phía Java dùng `Signature.getInstance("SHA256withECDSA")` mặc định mong representation DER. Dữ liệu bị diễn giải sai, dẫn tới `false` hoặc `SignatureException` tùy provider. Cách sửa là thống nhất algorithm-format, dùng `SHA256withECDSAinP1363Format` khi có hỗ trợ hoặc chuyển representation một cách chuẩn xác qua thư viện tin cậy.

### Case D — Public key RSA khác nhưng vẫn hợp lệ

`initVerify(otherRsaPublicKey)` vẫn có thể thành công vì đúng **loại khóa RSA**. Tuy nhiên signature không tương ứng nên `verify` trả `false`. Điều này khác việc đưa **EC public key** vào RSA verifier, nơi `initVerify` thường ném `InvalidKeyException`.

### Case E — Chứng chỉ hết hạn nhưng signature vẫn verify

Một public key lấy từ certificate đã hết hạn vẫn có thể thực hiện phép RSA/ECDSA verify thành công nếu private key tương ứng đã ký đúng. **Signature.verify không thay thế certificate path validation**. Cần tách “cryptographic signature valid” và “certificate trusted & valid for intended purpose”.

### Case F — RSA-PSS sai saltLength/MGF

Client dùng `RSASSA-PSS` với MGF1/SHA-256, salt 32 byte; server cấu hình khác. Tùy provider và điểm lỗi, phương thức có thể trả false hoặc ném exception. Cách sửa là đồng bộ bộ tham số theo giao thức (như mục 8), không tự thử nhiều cấu hình suy đoán nếu chính sách không cho phép.

### Case G — Đổi khóa nhưng chưa cập nhật key ID

Signature đúng với public key cũ; server dùng public key mới vì bỏ qua phiên bản `kid` được xác thực hoặc xử lý key rotation sai. Kết quả `false` không chứng minh client đã cố ý giả mạo. Cần quản lý key ID, trust binding, rotation và thời gian hiệu lực hợp lý.

## 12. Ma trận kiểm thử nên có

| Test | Input | Kết quả dự kiến theo tầng |
| --- | --- | --- |
| Happy path | Đúng signature, public key, message, scheme/params | `verify == true`; sau đó kiểm tra context/trust. |
| Sửa một byte message | Giữ signature cũ, thay message | `verify == false`. |
| Thay public key RSA cùng loại | Dùng key khác cặp | `verify == false`. |
| Cắt một byte RSA signature | Truncated signature bytes | Bị từ chối; `verify == false` hoặc `SignatureException` tùy provider. |
| Hỏng Base64 | Ký tự không thuộc alphabet cho phép | `IllegalArgumentException` ở decoder; chưa gọi verify. |
| DER public key hỏng | Bytes không đúng SPKI | `InvalidKeySpecException` khi load key. |
| EC key vào RSA verifier | `initVerify(ecPublicKey)` | `InvalidKeyException`. |
| Chưa `initVerify` | Gọi `verify` ở trạng thái chưa chuẩn bị | `SignatureException`. |
| Tên algorithm không tồn tại | `Signature.getInstance("NotARealSignatureAlgorithm")` | `NoSuchAlgorithmException`. |
| Parameters PSS thống nhất | Hai bên cùng hash/MGF/salt/trailer | `verify == true`. |
| ECDSA DER/P1363 mismatch | Bên ký và verify dùng representation khác | Từ chối; có thể `false` hoặc `SignatureException`. |
| Certificate không tin cậy/hết hạn | Chữ ký toán học vẫn đúng | **Trust/policy từ chối** dù `verify` có thể `true`. |
| Metadata ký bị thiếu | AAD/context/claims không hợp lệ theo giao thức | Từ chối ở tầng policy/context, không suy từ chữ ký. |
| Input rất lớn | Request hoặc signature quá kích thước | Từ chối sớm, giới hạn bộ nhớ/CPU, không chạy crypto vô hạn. |

Kiểm thử nên chạy trên **provider thực tế** được dùng ở production, vì cách báo lỗi sai encoding, hỗ trợ tham số và tên thông điệp có thể khác giữa các provider. Không viết test bám vào **chuỗi tiếng Anh** của exception, chỉ dựa trên loại lỗi, vị trí và kết quả được contract bảo đảm.

## 13. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “`verify == false` nghĩa là Base64/DER hợp lệ” | Một số provider có thể trả false ngay cả khi chữ ký có vấn đề format. | Validate format có thể kiểm tra trước; coi false là **not verified**. |
| “Mọi signature hỏng luôn ném `SignatureException`” | Không có bảo đảm đồng nhất giữa scheme/provider. | Xử lý cả false và exception; không phụ thuộc một cách báo lỗi. |
| “Mọi `SignatureException` là chữ ký của hacker” | Có thể sai state, provider không xử lý được, lỗi nội bộ. | Ghi stage và context; phân biệt input với hạ tầng. |
| “Base64 error là `SignatureException`” | Decoder chạy **trước** Signature. | Catch `IllegalArgumentException` đúng tầng. |
| “`X509EncodedKeySpec` chứa cả certificate” | Nó biểu diễn public key SPKI, không phải certificate hoàn chỉnh. | Dùng `CertificateFactory` cho chứng chỉ và PKIX validation cho trust. |
| “`verify == true` là đủ xác nhận người gửi” | Chỉ xác nhận quan hệ toán học giữa message/key/signature. | Xác minh public key identity, policy, expiry, anti-replay. |
| Tự thay đổi JSON trước verify | Byte không còn giống dữ liệu đã ký. | Dùng raw/canonical bytes đúng giao thức. |
| RSA và ECDSA dùng cùng encoding chữ ký | Format khác nhau; ECDSA có DER/P1363. | Cố định algorithm + representation, chuyển đổi qua API tin cậy khi cần. |
| Không cố định tham số RSA-PSS | MGF/hash/salt có thể khác nhau giữa hai phía. | Dùng `PSSParameterSpec` rõ ràng, giao thức thống nhất. |
| Bắt `Exception` rồi trả `true` | **Fail-open**, có thể chấp nhận chữ ký chưa verify. | Mọi lỗi phải từ chối; chỉ chấp nhận khi kiểm tra/policy đều thành công. |
| Bắt hết exception rồi không log | Mất bằng chứng để phân biệt payload hỏng với cấu hình server. | Phân loại stage/status và log có kiểm soát; response công khai phù hợp. |
| Tự fallback từ thuật toán mạnh sang yếu | Gây downgrade/algorithm confusion. | Chọn scheme theo allowlist và key policy, xử lý lỗi rõ ràng. |

## 14. Câu hỏi tự kiểm tra

**1.** `Signature.verify` trả `false`. Có thể kết luận chữ ký chắc chắn đúng định dạng DER không?

**Đáp án:** Không. Tùy format/provider, một chữ ký sai định dạng cũng có thể cho false; chỉ kết luận là **không xác minh thành công**.

**2.** Decoder `Base64.getDecoder()` ném `IllegalArgumentException`. Có phải chữ ký RSA không khớp không?

**Đáp án:** Chưa có phép RSA verify nào xảy ra. Đây là lỗi **transport encoding** và cần từ chối ở tầng decode.

**3.** Khi `KeyFactory.generatePublic(new X509EncodedKeySpec(bytes))` ném `InvalidKeySpecException`, có nên thử `Signature.verify` tiếp không?

**Đáp án:** Không, chưa có public key hợp lệ. Phải sửa nguồn/định dạng key và xác minh trust; không thể chạy phép verify với đối tượng khóa chưa tạo được.

**4.** Đưa một EC public key hợp lệ vào `SHA256withRSA.initVerify` sẽ trả false hay exception?

**Đáp án:** Thường ném **`InvalidKeyException` tại `initVerify`** vì sai loại khóa; không phải `verify == false`. Nếu dùng RSA key khác cặp nhưng hợp lệ thì có thể init thành công rồi verify false.

**5.** Chữ ký ECDSA 64 byte theo `r||s` được gửi sang Java `SHA256withECDSA` mặc định. Có đảm bảo verify được không?

**Đáp án:** Không. JCA thông thường mong DER cho tên này; cần thống nhất dạng P1363 hay DER và scheme tương ứng.

**6.** Một signature verify thành công với public key từ certificate tự ký chưa được tin cậy. Có được cấp quyền luôn không?

**Đáp án:** Không. Cần kiểm tra chain/trust/policy/identity và ngữ cảnh nghiệp vụ. `verify == true` chỉ là bằng chứng mật mã.

**7.** `SignatureException` ở `verify` khi chưa `initVerify` nói điều gì?

**Đáp án:** Đối tượng engine được dùng sai lifecycle; cần sửa luồng lập trình, không quy kết lỗi payload.

**8.** Vì sao service không nên trả toàn bộ exception message của JCA cho client?

**Đáp án:** Có thể tiết lộ tên provider, chi tiết scheme/key/validation và tạo các tín hiệu oracle không cần thiết. Client cần kết quả từ chối rõ, log nội bộ mới chứa stage và mã lỗi để chẩn đoán.

**9.** RSA-PSS giữa signer và verifier khác `PSSParameterSpec` nhưng dùng cùng RSA public/private key. Có bảo đảm chữ ký đúng không?

**Đáp án:** Không. Hash/MGF1/salt length/trailer field phải khớp giao thức; tùy lỗi mà provider có thể trả false hoặc ném exception.

## 15. Tài liệu chính thức

- [Java SE 17 — `Signature` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/Signature.html) — `initVerify`, `update`, `verify` và các ngoại lệ.
- [Java SE 17 — `SignatureSpi` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SignatureSpi.html) — hợp đồng `engineVerify`, sai encoding/type và trạng thái engine.
- [Java SE 17 — `KeyFactory` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyFactory.html) — chuyển đổi public key từ key specification.
- [Java SE 17 — `X509EncodedKeySpec` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html) — DER SubjectPublicKeyInfo, không phải certificate nguyên bản.
- [Java SE 17 — `PSSParameterSpec` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PSSParameterSpec.html) — bộ tham số RSA-PSS.
- [Java 17 Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/17/docs/specs/security/standard-names.html) — thuật toán Signature, RSA, ECDSA DER và `inP1363Format`.
- [Oracle Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-cryptography-architecture-jca-reference-guide.html) — engine, provider và chữ ký số.
