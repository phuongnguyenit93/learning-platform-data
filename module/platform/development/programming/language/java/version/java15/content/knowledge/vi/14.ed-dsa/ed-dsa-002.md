# EdDSA theo RFC 8032 — Ed25519, Ed448 và API Java 15+

## 1. EdDSA là gì và dùng để làm gì?

**EdDSA (Edwards-curve Digital Signature Algorithm)** là họ thuật toán **chữ ký số bất đối xứng** dựa trên đường cong Edwards, được mô tả trong **RFC 8032 (2017)**. Java 15 bổ sung hỗ trợ EdDSA trong Java Cryptography Architecture (JCA) thông qua **JEP 339**. Các thuật toán và API này **vẫn được sử dụng trong Java hiện hành**, không phải tính năng preview hay legacy.

Một ứng dụng dùng EdDSA để:

1. Sinh cặp khóa: **private key** để ký và **public key** để kiểm tra chữ ký.
2. Ký **đúng dãy byte** của một thông điệp bằng private key.
3. Cho người nhận dùng public key và cùng thông điệp để xác minh tính hợp lệ của chữ ký.

~~~text
Bên ký                                     Bên kiểm tra
PrivateKey ─┐
            ├─ EdDSA.Sign(message) ──► signature
message ────┘                              │
                                         ▼
                                   EdDSA.Verify(
                                       PublicKey,
                                       message,
                                       signature)
                                         │
                                        true / false
~~~

Nếu thông điệp thay đổi, chữ ký không còn xác minh thành công đối với thông điệp mới (trừ khi có tình huống không an toàn ngoài mô hình chuẩn). Nếu dùng sai public key, chữ ký cũng không hợp lệ.

**Giới hạn rất quan trọng:** chữ ký số **không mã hóa dữ liệu** và **không giữ bí mật** nội dung. Việc kiểm tra trả `true` chứng tỏ chữ ký khớp với một public key, nhưng **không tự chứng minh public key đó thuộc về người được tuyên bố**. Public key cần được xác thực bằng chứng chỉ, danh sách khóa đáng tin, fingerprint an toàn hoặc cơ chế thiết lập niềm tin tương ứng.

## 2. Hai bộ tham số chính của RFC 8032

| Thuộc tính | Ed25519 | Ed448 |
| --- | --- | --- |
| Đường cong | `edwards25519` | `edwards448` |
| Mức bảo mật ước lượng | Khoảng 128 bit | Khoảng 224 bit |
| Public key **raw** theo RFC | 32 byte | 57 byte |
| Private seed **raw** theo RFC | 32 byte | 57 byte |
| Chữ ký raw theo RFC | **64 byte** | **114 byte** |
| Hàm băm cốt lõi | SHA-512 | SHAKE256 |
| Tình huống sử dụng | Chữ ký hiệu quả, được hỗ trợ rộng | Nhu cầu mức bảo mật cao hơn, cần kiểm tra tương thích hệ sinh thái |

Độ dài `PublicKey.getEncoded()` trong Java **không nhất thiết bằng** 32 hoặc 57 byte, vì `getEncoded()` thường trả **SubjectPublicKeyInfo DER/X.509**, có header và mã nhận diện thuật toán. Tương tự, `PrivateKey.getEncoded()` thường ở dạng **PKCS#8 DER**, **không phải** private seed raw dài 32/57 byte.

RFC 8032 dùng các phương pháp sinh chữ ký có tính **deterministic**: với **cùng khóa, cùng byte thông điệp, cùng biến thể/context**, chữ ký giống nhau. Vì vậy không cần tự cung cấp một số ngẫu nhiên mới cho **mỗi lần ký** như một số cơ chế chữ ký khác. Tuy nhiên **quá trình sinh khóa vẫn phải dùng nguồn ngẫu nhiên mật mã an toàn**.

**Đừng nhầm:** `Ed25519`/`Ed448` là chữ ký số. `X25519`/`X448` (RFC 7748) là họ thao tác thỏa thuận khóa, **không** dùng thay `Ed25519`/`Ed448` trong `Signature`. Chúng có liên hệ đường cong nhưng vai trò, cách biểu diễn khóa và protocol khác nhau.

## 3. RFC 8032 định nghĩa những biến thể nào?

RFC 8032 không chỉ có hai cái tên Ed25519 và Ed448; còn mô tả **pure**, **context** và **prehash**. Khác biệt này là một phần của **định nghĩa chữ ký**, không chỉ là dữ liệu kèm theo.

| Chế độ RFC 8032 | Đường cong | Cách xử lý thông điệp/context |
| --- | --- | --- |
| **Ed25519 (pure)** | edwards25519 | Ký thông điệp theo chế độ thông thường, không có context |
| **Ed25519ctx** | edwards25519 | Có context và phân tách miền (*domain separation*) |
| **Ed25519ph** | edwards25519 | Chế độ **prehash** có phân tách miền, dùng SHA-512 cho tiền băm |
| **Ed448** | edwards448 | Pure Ed448; có cơ chế context (có thể rỗng) |
| **Ed448ph** | edwards448 | Prehash bằng SHAKE256 với thông số của RFC 8032 và context tương ứng |

### 3.1. Pure Ed25519 so với Ed25519ctx

Context là một dãy **byte** có độ dài tối đa **255 byte** nhằm phân tách các mục đích sử dụng một khóa, ví dụ một miền ứng dụng như `"app:invoice:v1"`. Context **không phải** một phần văn bản tự động nối vào message: RFC định nghĩa cách đưa nó vào tính toán mật mã với tiền tố phân tách miền.

Với Ed25519, chế độ **không có context** và chế độ **có context rỗng** không nên bị đánh đồng: API Java phân biệt *không cung cấp context* với *cung cấp byte array rỗng*. Đừng đổi giữa pure Ed25519 và Ed25519ctx một cách ngẫu nhiên.

**Bên ký và bên xác minh phải thống nhất từng byte context**. Nếu bên ký dùng `"app:invoice:v1"`, bên xác minh lại dùng `"app:invoice:v2"` thì kiểm tra sẽ không thành công.

### 3.2. Prehash không giống tự gọi SHA-512 rồi ký pure

`Ed25519ph` và `Ed448ph` dùng cơ chế tiền băm **được quy định trong RFC 8032**, đồng thời thay đổi phần phân tách miền so với pure. Vì vậy:

~~~text
Ed25519ph(message)  ≠  Ed25519(SHA-512(message))
~~~

Không tự viết:

~~~java
// KHÔNG thay Ed25519ph bằng cách tự SHA-512 rồi dùng Ed25519 pure:
// byte[] digest = MessageDigest.getInstance("SHA-512").digest(message);
// signer.update(digest);
~~~

Hãy dùng `EdDSAParameterSpec(true)` với `Signature` được hỗ trợ. Sau đó truyền **message gốc** cho `update(...)`; provider thực hiện tiền băm và domain separation theo đúng biến thể RFC.

Nếu protocol của bạn chỉ yêu cầu **Ed25519 pure**, nên dùng pure; không thêm context hoặc bật prehash tùy tiện vì sẽ phá tương thích với verifier đã triển khai.

## 4. Quy trình ký/xác minh ở mức khái niệm

RFC 8032 quy định đầy đủ phép toán điểm trên đường cong và cách mã hóa; ý tưởng chính:

1. Từ **private seed**, tính thông tin khóa và public point `A`.
2. Dùng giá trị dẫn xuất từ private seed, thông điệp và domain separation để tạo một scalar `r` theo cách **deterministic**, rồi tính điểm `R = [r]B`.
3. Tính một **challenge** phụ thuộc `R`, public key `A` và thông điệp.
4. Tính scalar `S` theo khóa và challenge, tạo chữ ký dạng **`ENC(R) || ENC(S)`**.
5. Verifier giải mã/kiểm tra dữ liệu chữ ký và public key theo RFC, rồi xác minh quan hệ điểm trên đường cong.

`B` là base point, `ENC` là định dạng mã hóa quy định trong RFC, `||` là phép nối byte. Các biến thể Ed25519/Ed448 có hàm băm, prehash và domain separation **khác nhau**; phần mô tả trên là sơ đồ để hiểu, **không phải thuật toán tự cài đặt đầy đủ**.

**Không tự triển khai số học đường cong hoặc xác minh bằng vài phép toán BigInteger trong code nghiệp vụ.** Hãy dùng JCA/JCE và provider được bảo trì, kiểm tra test vector chuẩn và phiên bản runtime. Các chi tiết về canonical encoding, điểm không hợp lệ, scalar range và các kiểm tra chữ ký có tác động trực tiếp đến bảo mật.

## 5. Java 15+ cung cấp những API nào?

Trong JCA, tên thuật toán chuẩn gồm:

| API | Sử dụng | Ví dụ |
| --- | --- | --- |
| `KeyPairGenerator` | Sinh cặp khóa | `getInstance("Ed25519")` hoặc `getInstance("Ed448")` |
| `Signature` | Ký và xác minh | `getInstance("Ed25519")` / `getInstance("Ed448")` |
| `KeyFactory` | Khôi phục khóa từ `KeySpec` | `getInstance("Ed25519")` |
| `NamedParameterSpec` | Chọn tham số của đường cong | `NamedParameterSpec.ED25519`, `NamedParameterSpec.ED448` |
| `EdDSAParameterSpec` | Chọn prehash/context | `new EdDSAParameterSpec(false, context)` |
| `EdECPrivateKeySpec` / `EdECPublicKeySpec` | Dạng spec của khóa EdDSA | Dùng khi thực sự cần chuyển cấu trúc khóa theo RFC |
| `X509EncodedKeySpec` | Khôi phục public key đã encode dạng X.509/SPKI | `KeyFactory.generatePublic(...)` |
| `PKCS8EncodedKeySpec` | Khôi phục private key đã encode dạng PKCS#8 | `KeyFactory.generatePrivate(...)` |

Tên `"EdDSA"` cũng tồn tại để chọn họ thuật toán; với protocol rõ ràng, **ưu tiên `"Ed25519"` hoặc `"Ed448"`** nhằm tránh sự mơ hồ trong lựa chọn đường cong. Hỗ trợ thuật toán có thể phụ thuộc vào JDK/provider, môi trường bảo mật và HSM; ứng dụng cần kiểm tra provider mà mình thực sự sử dụng.

Ví dụ tối giản:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;

KeyPair pair = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
byte[] data = "Hóa đơn #42".getBytes(StandardCharsets.UTF_8);

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(pair.getPrivate());
signer.update(data);
byte[] signatureBytes = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(pair.getPublic());
verifier.update(data);
boolean valid = verifier.verify(signatureBytes);
~~~

Đây là **đoạn mã minh họa có các import nhưng không có class/main độc lập**; chương trình hoàn chỉnh ở mục 8 có thể biên dịch/chạy trực tiếp.

**Lưu ý thời điểm cấu hình:** nếu cần `EdDSAParameterSpec`, hãy cấu hình thống nhất cả phía ký lẫn xác minh. Trong ví dụ Java bên dưới, `Signature.setParameter(params)` được gọi trước `initSign` hoặc `initVerify`, sau đó mới gọi `update` và `sign`/`verify`.

## 6. Dùng `EdDSAParameterSpec` cho context/prehash

### 6.1. Pure Ed25519: không cần setParameter

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(message);
byte[] signature = signer.sign();
~~~

Đoạn này giả định `privateKey` và `message` đã tồn tại, lần ký là pure Ed25519. Không đặt context, không bật prehash.

### 6.2. Ed25519ctx: context cụ thể

~~~java
byte[] context = "app:invoice:v1".getBytes(StandardCharsets.UTF_8);
EdDSAParameterSpec params = new EdDSAParameterSpec(false, context);

Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(params);
signer.initSign(privateKey);
signer.update(message);
byte[] signature = signer.sign();
~~~

Bên kiểm tra phải dùng **chính cùng `EdDSAParameterSpec(false, context)`**. Việc dùng context khác, kể cả chỉ thay một byte, khiến chữ ký không còn hợp lệ theo cấu hình đó.

Context dài tối đa **255 byte**, không phải 255 ký tự Java. Ví dụ một emoji UTF-8 chiếm bốn byte. `EdDSAParameterSpec` sao chép mảng context khi nhận tham số, nhưng ứng dụng vẫn cần lưu/biết đúng context tại bên nhận.

### 6.3. Ed25519ph: bật prehash

~~~java
EdDSAParameterSpec params = new EdDSAParameterSpec(true);

Signature signer = Signature.getInstance("Ed25519");
signer.setParameter(params);
signer.initSign(privateKey);
signer.update(message);  // đưa thông điệp GỐC, không tự SHA-512 trước
byte[] signature = signer.sign();
~~~

`new EdDSAParameterSpec(true)` chọn chế độ prehash. Kết quả không thể được xác minh bằng `Signature.getInstance("Ed25519")` ở pure mode.

**Phân biệt constructor:**

- `new EdDSAParameterSpec(false)`: pure mode, không có context.
- `new EdDSAParameterSpec(false, new byte[0])`: **có context rỗng**; với Ed25519, đó là dạng contextualized, không được coi là mặc nhiên giống pure.
- `new EdDSAParameterSpec(true)`: prehash không cung cấp context.
- `new EdDSAParameterSpec(true, context)`: prehash cộng context.

Một số ứng dụng giao thức không cho phép mọi mode. **Hãy theo tiêu chuẩn protocol ở hai bên**, không bật chế độ chỉ vì JCA hỗ trợ.

## 7. Byte của khóa và định dạng trao đổi

`KeyPair.getPrivate()` và `getPublic()` trả các đối tượng khóa; byte của một đối tượng khóa do JCA encode thông thường là **ASN.1/DER** theo các cấu trúc khác với biểu diễn raw trong RFC 8032.

~~~java
byte[] publicDer = pair.getPublic().getEncoded();   // thường X.509/SPKI
byte[] privateDer = pair.getPrivate().getEncoded(); // thường PKCS#8

KeyFactory factory = KeyFactory.getInstance("Ed25519");
PublicKey restoredPublic = factory.generatePublic(
        new X509EncodedKeySpec(publicDer));
PrivateKey restoredPrivate = factory.generatePrivate(
        new PKCS8EncodedKeySpec(privateDer));
~~~

Nếu đang trao đổi với SSH, JOSE/COSE, OpenSSH hoặc một thư viện khác, **định dạng key container do protocol quy định** có thể không giống `getEncoded()` của JCA. Đừng mặc định khóa public Ed25519 raw 32 byte là một `X509EncodedKeySpec` hợp lệ, cũng không coi private seed raw 32 byte là PKCS#8.

JCA còn có `EdECPrivateKeySpec` và `EdECPublicKeySpec` để làm việc với các thành phần EdDSA ở dạng đặc thù. Phần chương trình dưới đây dùng cả hai khi kiểm chứng test vector RFC 8032:

- `EdECPrivateKeySpec(NamedParameterSpec.ED25519, seed32)` nhận **raw private seed**.
- `EdECPublicKeySpec` cần một `EdECPoint(xOdd, y)`, trong đó `xOdd` là parity của x và `y` là tọa độ y. Public key nén RFC là định dạng **little-endian**, có bit dấu của x. **Không đưa nguyên 32 byte nén vào `BigInteger` big-endian** nếu chưa đổi đúng format.
- Cách chuyển raw key là thao tác liên thông định dạng **dễ sai**. Trong dự án thông thường nên ưu tiên encode/parse bằng thư viện/provider tương thích chuẩn, với test vector và kiểm tra input nghiêm ngặt.

**Bảo mật khóa riêng:** `privateDer` và raw seed là dữ liệu bí mật. Không ghi log, không commit vào repository, không đưa vào response, không dùng seed test vector làm khóa sản xuất. Với hệ thống thực tế cần khóa được tạo/quản lý trong keystore, secret manager hoặc HSM tùy mô hình đe dọa; đôi khi private key **không xuất được** bằng `getEncoded()`.

## 8. Chương trình hoàn chỉnh: ký, verify, context, prehash và test vector RFC 8032

Lưu đúng file **`EdDSARfc8032Demo.java`**, encoding UTF-8. Chương trình chạy offline, không dùng thư viện bên ngoài, không gửi dữ liệu lên mạng. Đoạn sinh khóa ở đây **chỉ dành cho minh họa**; môi trường sản xuất phải có quản lý key riêng.

Ví dụ thực hiện:

1. Sinh khóa Ed25519, ký message UTF-8, xác minh thành công.
2. Chứng minh sửa message hoặc thay public key làm verify thất bại.
3. Chứng minh cùng khóa + cùng message cho **chữ ký deterministic**.
4. Khôi phục khóa từ X.509/SPKI và PKCS#8 rồi ký/verify lại.
5. Ký Ed25519ctx, thử đúng/sai context.
6. Ký Ed25519ph; kiểm chứng pure verifier không xác minh được chữ ký ph.
7. Ký và verify Ed448, đối chiếu độ dài chữ ký.
8. So khớp chữ ký **Ed25519 test vector với message rỗng** trong RFC 8032 `7.1 và xác minh nó bằng public key raw của chính vector.

~~~java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.*;
import java.util.Arrays;

public class EdDSARfc8032Demo {
    public static void main(String[] args) throws Exception {
        byte[] message = "Xin chào, chữ ký số".getBytes(StandardCharsets.UTF_8);
        KeyPair ed25519 = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();

        byte[] sig = sign("Ed25519", ed25519.getPrivate(), message, null);
        byte[] sigAgain = sign("Ed25519", ed25519.getPrivate(), message, null);
        byte[] changed = "Xin chào, chữ ký so".getBytes(StandardCharsets.UTF_8);
        System.out.println("ed25519SignatureBytes=" + sig.length);
        System.out.println("ed25519Valid=" +
                verify("Ed25519", ed25519.getPublic(), message, sig, null));
        System.out.println("changedMessageValid=" +
                verify("Ed25519", ed25519.getPublic(), changed, sig, null));
        System.out.println("deterministic=" + Arrays.equals(sig, sigAgain));

        KeyPair other = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        System.out.println("wrongPublicKeyValid=" +
                verify("Ed25519", other.getPublic(), message, sig, null));

        KeyFactory keyFactory = KeyFactory.getInstance("Ed25519");
        PublicKey restoredPublic = keyFactory.generatePublic(
                new X509EncodedKeySpec(ed25519.getPublic().getEncoded()));
        PrivateKey restoredPrivate = keyFactory.generatePrivate(
                new PKCS8EncodedKeySpec(ed25519.getPrivate().getEncoded()));
        byte[] sigRestored = sign("Ed25519", restoredPrivate, message, null);
        System.out.println("encodedKeysRoundTrip=" +
                verify("Ed25519", restoredPublic, message, sigRestored, null));

        EdDSAParameterSpec context = new EdDSAParameterSpec(
                false, "app:invoice:v1".getBytes(StandardCharsets.UTF_8));
        EdDSAParameterSpec otherContext = new EdDSAParameterSpec(
                false, "app:invoice:v2".getBytes(StandardCharsets.UTF_8));
        byte[] contextualSig =
                sign("Ed25519", ed25519.getPrivate(), message, context);
        System.out.println("contextVerify=" +
                verify("Ed25519", ed25519.getPublic(), message, contextualSig, context));
        System.out.println("wrongContextVerify=" +
                verify("Ed25519", ed25519.getPublic(), message, contextualSig, otherContext));
        System.out.println("pureVsContextSame=" + Arrays.equals(sig, contextualSig));

        EdDSAParameterSpec prehash = new EdDSAParameterSpec(true);
        byte[] phSig = sign("Ed25519", ed25519.getPrivate(), message, prehash);
        System.out.println("ed25519phValid=" +
                verify("Ed25519", ed25519.getPublic(), message, phSig, prehash));
        System.out.println("ed25519phVerifiedAsPure=" +
                verify("Ed25519", ed25519.getPublic(), message, phSig, null));

        KeyPair ed448 = KeyPairGenerator.getInstance("Ed448").generateKeyPair();
        byte[] ed448Sig = sign("Ed448", ed448.getPrivate(), message, null);
        System.out.println("ed448SignatureBytes=" + ed448Sig.length);
        System.out.println("ed448Valid=" +
                verify("Ed448", ed448.getPublic(), message, ed448Sig, null));

        // Test vector RFC 8032, section 7.1: Ed25519, message empty.
        // Đây là seed PUBLIC trong RFC để KIỂM THỬ, tuyệt đối không dùng production.
        byte[] rfcSeed = hex(
                "9d61b19deffd5a60ba844af492ec2cc4" +
                "4449c5697b326919703bac031cae7f60");
        byte[] rfcPublicCompressed = hex(
                "d75a980182b10ab7d54bfed3c964073a" +
                "0ee172f3daa62325af021a68f707511a");
        byte[] expectedRFCSignature = hex(
                "e5564300c360ac729086e2cc806e828a" +
                "84877f1eb8e5d974d873e06522490155" +
                "5fb8821590a33bacc61e39701cf9b46b" +
                "d25bf5f0595bbe24655141438e7a100b");

        PrivateKey testPrivate = keyFactory.generatePrivate(
                new EdECPrivateKeySpec(NamedParameterSpec.ED25519, rfcSeed));
        PublicKey testPublic = publicKeyFromRFC8032(
                keyFactory, rfcPublicCompressed);
        byte[] rfcActual = sign("Ed25519", testPrivate, new byte[0], null);

        System.out.println("rfc8032EmptyMessageVectorMatches=" +
                Arrays.equals(rfcActual, expectedRFCSignature));
        System.out.println("rfc8032Verify=" +
                verify("Ed25519", testPublic, new byte[0], expectedRFCSignature, null));

        System.out.println("checks=" + (
                sig.length == 64
                && verify("Ed25519", ed25519.getPublic(), message, sig, null)
                && !verify("Ed25519", ed25519.getPublic(), changed, sig, null)
                && Arrays.equals(sig, sigAgain)
                && !verify("Ed25519", other.getPublic(), message, sig, null)
                && verify("Ed25519", restoredPublic, message, sigRestored, null)
                && verify("Ed25519", ed25519.getPublic(), message, contextualSig, context)
                && !verify("Ed25519", ed25519.getPublic(), message, contextualSig, otherContext)
                && !Arrays.equals(sig, contextualSig)
                && verify("Ed25519", ed25519.getPublic(), message, phSig, prehash)
                && !verify("Ed25519", ed25519.getPublic(), message, phSig, null)
                && ed448Sig.length == 114
                && verify("Ed448", ed448.getPublic(), message, ed448Sig, null)
                && Arrays.equals(rfcActual, expectedRFCSignature)
                && verify("Ed25519", testPublic, new byte[0], expectedRFCSignature, null)));
    }

    static byte[] sign(String algorithm, PrivateKey key, byte[] message,
                       EdDSAParameterSpec params) throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        if (params != null) signer.setParameter(params);
        signer.initSign(key);
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(String algorithm, PublicKey key, byte[] message,
                          byte[] signature, EdDSAParameterSpec params) throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        if (params != null) verifier.setParameter(params);
        verifier.initVerify(key);
        verifier.update(message);
        return verifier.verify(signature);
    }

    static PublicKey publicKeyFromRFC8032(KeyFactory factory, byte[] compressed)
            throws Exception {
        byte[] yBigEndian = compressed.clone();
        boolean xOdd = (yBigEndian[yBigEndian.length - 1] & 0x80) != 0;
        yBigEndian[yBigEndian.length - 1] &= 0x7f;
        for (int left = 0, right = yBigEndian.length - 1;
             left < right; left++, right--) {
            byte temp = yBigEndian[left];
            yBigEndian[left] = yBigEndian[right];
            yBigEndian[right] = temp;
        }
        return factory.generatePublic(new EdECPublicKeySpec(
                NamedParameterSpec.ED25519,
                new EdECPoint(xOdd, new BigInteger(1, yBigEndian))));
    }

    static byte[] hex(String value) {
        if ((value.length() & 1) != 0) {
            throw new IllegalArgumentException("odd hex");
        }
        byte[] out = new byte[value.length() / 2];
        for (int i = 0; i < out.length; i++) {
            int high = Character.digit(value.charAt(i * 2), 16);
            int low = Character.digit(value.charAt(i * 2 + 1), 16);
            if (high < 0 || low < 0) {
                throw new IllegalArgumentException("bad hex");
            }
            out[i] = (byte) ((high << 4) | low);
        }
        return out;
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 EdDSARfc8032Demo.java
java EdDSARfc8032Demo
~~~

Chương trình cũng biên dịch thành công với `javac --release 15`. Đầu ra **chính xác**, đã kiểm chứng trên JDK 24 (không in byte khóa, chữ ký sinh ngẫu nhiên hoặc fingerprint biến đổi giữa các lần chạy):

~~~text
ed25519SignatureBytes=64
ed25519Valid=true
changedMessageValid=false
deterministic=true
wrongPublicKeyValid=false
encodedKeysRoundTrip=true
contextVerify=true
wrongContextVerify=false
pureVsContextSame=false
ed25519phValid=true
ed25519phVerifiedAsPure=false
ed448SignatureBytes=114
ed448Valid=true
rfc8032EmptyMessageVectorMatches=true
rfc8032Verify=true
checks=true
~~~

### Hiểu kết quả

- `ed25519SignatureBytes=64` và `ed448SignatureBytes=114` trùng kích thước chữ ký raw của RFC 8032.
- `ed25519Valid=true`, `changedMessageValid=false`, `wrongPublicKeyValid=false`: xác minh đúng message/public key mới thành công.
- `deterministic=true`: cùng khóa, cùng message và cùng mode tạo cùng chữ ký.
- `encodedKeysRoundTrip=true`: X.509/SPKI và PKCS#8 có thể được `KeyFactory` của provider đọc lại trong ví dụ.
- `contextVerify=true` nhưng `wrongContextVerify=false`: context phải giống từng byte.
- `pureVsContextSame=false`: chế độ pure và contextualized không cho chữ ký giống nhau.
- `ed25519phValid=true` và `ed25519phVerifiedAsPure=false`: không thể xác minh chữ ký ph như pure.
- `rfc8032EmptyMessageVectorMatches=true` và `rfc8032Verify=true`: chữ ký và public key của test vector **Ed25519 với thông điệp rỗng** khớp chuẩn RFC 8032 `7.1. Đây là xác minh liên thông quan trọng hơn chỉ kiểm tra signer và verifier của cùng implementation.
- `checks=true`: tất cả các điều kiện kiểm thử trong chương trình đạt.

Chương trình có một helper **chỉ minh họa cho khóa public Ed25519 raw**. Đừng tái sử dụng `publicKeyFromRFC8032` cho Ed448 không chỉnh sửa; raw public key Ed448 có **57 byte** và những yêu cầu định dạng khác. Trong code sản xuất, xác minh độ dài input, kiểm tra key theo quy chuẩn và ưu tiên parser/provider đã qua kiểm thử.

## 9. Thiết kế giao thức an toàn với EdDSA

### 9.1. Ký đúng byte, không ký “một chuỗi trừu tượng”

`Signature.update(...)` xử lý **byte**. Với văn bản, quy định UTF-8 (hoặc charset theo protocol) trước khi ký:

~~~java
byte[] payload = jsonCanonical.getBytes(StandardCharsets.UTF_8);
// signer.update(payload);
~~~

Câu lệnh dùng `jsonCanonical` là **minh họa**, không phải tên API chuẩn; nếu một protocol ký JSON, cần quy định/tuân theo **canonicalization** cụ thể hoặc ký **chính những byte đã truyền**. Hai chuỗi nhìn giống nhau có thể khác nhau vì thứ tự key JSON, dấu xuống dòng, whitespace, Unicode normalization hoặc encoding — chữ ký sẽ không xác minh được nếu byte khác.

### 9.2. Khóa, thuật toán, mode, context phải có cùng hợp đồng

Nên thống nhất và lưu trong protocol:

- Tên thuật toán **Ed25519** hoặc **Ed448** và phiên bản/định dạng khóa.
- Chế độ **pure**, **ctx** hoặc **ph** theo RFC.
- Context chính xác ở dạng byte khi sử dụng, với giới hạn 255 byte.
- Định dạng message bytes, định dạng chữ ký và encoding truyền tải (raw, base64, base64url, v.v.).
- Cách xác định/kiểm tra public key đáng tin (ví dụ key ID → chứng chỉ/khóa được quản lý).
- Version và thời gian hiệu lực để hỗ trợ **key rotation** và chống replay theo giao thức.

**Chữ ký hợp lệ không tự chống replay.** Nếu thông điệp cho phép thực hiện hành động, cần ID giao dịch, nonce ứng dụng, timestamp hoặc cơ chế quản lý trạng thái có xác thực theo đặc tả, rồi **ký cả thông tin này**. “EdDSA không cần random nonce khi ký” không đồng nghĩa ứng dụng không bao giờ cần nonce chống replay.

### 9.3. Không dùng một private key cho tất cả mục đích

Context giúp phân tách miền theo RFC, nhưng không thay thế quản lý quyền hạn hoặc chính sách khóa. Với hệ thống phức tạp, **nên tách cặp khóa cho các nhiệm vụ độc lập**, có kiểm soát vòng đời/rotation/revocation và audit; tránh dùng chung khóa ký với thao tác key agreement.

Không cố **chuyển thẳng** khóa Ed25519 thành khóa X25519 bằng cast hoặc phép đổi tên thuật toán trong JCA. Các framework có thể có phép chuyển đổi toán học riêng, nhưng đó không phải tính năng hoán đổi an toàn của hai định dạng khóa/protocol.

### 9.4. Quản lý lỗi và provider

Các phép `KeyPairGenerator.getInstance`, `Signature.getInstance`, `KeyFactory` có thể ném exception khi thuật toán/provider không hỗ trợ. `initSign`/`initVerify` kiểm tra kiểu khóa; `setParameter` kiểm tra tham số. `verify` trả `false` khi kiểm tra chữ ký không đạt đối với đầu vào thường gặp, nhưng với signature/key/format không hợp lệ **cũng có thể ném exception** tùy nguyên nhân/provider. Do đó, code sản xuất cần xử lý phân biệt **chữ ký không hợp lệ** với **lỗi vận hành hoặc input sai định dạng**.

`Signature` là một đối tượng có trạng thái `init → update → sign/verify`; không dùng chung một instance để ký/xác minh đồng thời trên nhiều thread nếu không có quản lý đồng bộ rõ ràng. Trong ví dụ này, mỗi lời gọi `sign/verify` đều tạo một `Signature` mới.

### 9.5. Mức độ bảo mật và giới hạn

EdDSA là lựa chọn hiện đại cho **chữ ký cổ điển dựa trên giả định toán học elliptic curve**, không phải chữ ký **hậu lượng tử**. Nếu ứng dụng có yêu cầu bảo mật hậu lượng tử hoặc yêu cầu tuân thủ chuẩn chuyên ngành, cần đánh giá các thuật toán và profile hiện hành thích hợp thay vì cho rằng Ed25519/Ed448 tự đáp ứng mọi chính sách.

Không tự kết luận chỉ dựa trên tên thuật toán: việc chấp nhận/đánh dấu trusted một chữ ký còn phụ thuộc **chất lượng khóa, nguồn public key, tính đúng đắn của message bytes và quy tắc nghiệp vụ**.

## 10. Lỗi phổ biến và câu hỏi tự kiểm tra

| Lỗi | Cách đúng |
| --- | --- |
| Dùng `X25519` để tạo chữ ký Ed25519 | `X25519` dành cho key agreement; dùng `Ed25519` với `Signature` |
| Coi Ed25519ph là SHA-512(message) rồi dùng pure Ed25519 | Dùng `EdDSAParameterSpec(true)` để provider làm đúng prehash + domain separation |
| Ký với context `v1`, verify với `v2` | Hai phía phải có **cùng context bytes** |
| Coi context rỗng luôn giống không có context | Đặc biệt với Ed25519, chế độ ctx rỗng và pure là khác nhau |
| Nhầm `getEncoded()` của public key là 32/57 byte raw | `getEncoded()` thường là X.509/SPKI DER |
| Nhầm private seed raw là `PKCS8EncodedKeySpec` | Dùng đúng container PKCS#8 hoặc spec EdEC theo định dạng |
| Tự in private key ra log để debug | Bảo vệ/không tiết lộ material khóa; chỉ dùng test vector công khai khi học |
| Dùng `String.getBytes()` không khai báo charset ở ranh giới giao thức | Quy định và dùng UTF-8/charset theo hợp đồng |
| Thay message nhưng vẫn verify được do không cập nhật dữ liệu | Ký và verify **chính cùng dãy byte**; test trường hợp sửa dữ liệu |
| Cho rằng verify true là đã biết chắc danh tính người gửi | Xác thực **nguồn public key**, chống tráo khóa |
| Cho rằng signature tự chống replay | Ký nonce/id/timestamp hoặc dữ liệu chống replay theo protocol |
| Coi EdDSA là encryption hoặc hậu lượng tử | EdDSA là chữ ký số dựa trên ECC, không mã hóa và không phải post-quantum |

**Câu hỏi 1:** Ed25519 có public key raw dài bao nhiêu? Chữ ký dài bao nhiêu?  
**Đáp án:** public raw **32 byte**, signature **64 byte**.

**Câu hỏi 2:** Vì sao một chữ ký Ed25519ph không xác minh được bằng Ed25519 pure?  
**Đáp án:** RFC 8032 dùng **prehash và domain separation khác**; không phải chỉ thêm bước băm bên ngoài.

**Câu hỏi 3:** Nếu chữ ký Ed25519 hợp lệ với public key nhập từ một URL không xác thực, đã chắc đúng người ký chưa?  
**Đáp án:** **Chưa**. Cần chứng minh public key đáng tin theo protocol.

**Câu hỏi 4:** Tại sao chương trình so test vector Ed25519 message rỗng ngoài việc chỉ chạy signer/verifier?  
**Đáp án:** signer và verifier cùng một implementation có thể cùng mắc lỗi; test vector RFC cung cấp **đáp án chuẩn độc lập** để kiểm chứng liên thông.

**Câu hỏi 5:** Có nên dùng seed `9d61...` trong ví dụ để ký dữ liệu thật?  
**Đáp án:** **Không**. Seed đó được công bố trong RFC; bất kỳ ai cũng biết private key tương ứng.

## 11. Tài liệu chính thức và tiêu chuẩn hiện hành

- **RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)**; mô tả Ed25519, Ed25519ctx, Ed25519ph, Ed448, Ed448ph, công thức và test vector `7.1: https://www.rfc-editor.org/rfc/rfc8032
- **OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)**, hỗ trợ được đưa vào Java 15: https://openjdk.org/jeps/339
- **Oracle Java SE 25 — Java Security Standard Algorithm Names**, `EdDSA`, `Ed25519`, `Ed448`: https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html
- **Oracle Java SE 25 — EdDSAParameterSpec**, chọn mode và context (Since: 15): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html
- **Oracle Java SE 25 — NamedParameterSpec**, `ED25519` và `ED448`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/NamedParameterSpec.html
- **Oracle Java SE 25 — EdECPrivateKeySpec**, raw EdEC seed: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html
- **Oracle Java SE 25 — EdECPublicKeySpec / EdECPoint**, biểu diễn public point: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPublicKeySpec.html
- **Oracle Java 15 — JDK Providers Documentation**, hỗ trợ pure/prehash/context trong EdDSA provider: https://docs.oracle.com/en/java/javase/15/security/oracle-providers.html