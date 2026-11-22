# 10.2 DH, ECDH, X25519 và X448 trong mô hình KeyAgreement

## 1. Bài toán: hai bên tạo cùng một bí mật mà không gửi bí mật đó

**Thỏa thuận khóa** (key agreement) cho phép Alice và Bob, mỗi người giữ một **khóa riêng** và trao đổi **khóa công khai**, tính ra **cùng một shared secret** qua mạng. Bên nghe lén có thể thấy khóa công khai và gói tin trao đổi, nhưng không dễ tính được bí mật nếu thuật toán, nhóm toán học, ngẫu nhiên và triển khai đáp ứng yêu cầu bảo mật.

Java Cryptography Architecture / Java Cryptography Extension (JCA/JCE) biểu diễn phép tính này bằng engine `javax.crypto.KeyAgreement`. Bốn biến thể trong bài:

- **DH** (finite-field Diffie–Hellman, thường gọi FFDH): phép lũy thừa modulo với tham số nhóm `p, g`.
- **ECDH** (Elliptic-Curve Diffie–Hellman): phép nhân vô hướng điểm trên một đường cong elliptic, ví dụ `secp256r1`/P-256.
- **X25519**: hàm trao đổi khóa Diffie–Hellman dựa trên Curve25519, thiết kế theo Montgomery ladder; triển khai Java thường dùng JCA algorithm `X25519` hoặc `XDH` với `NamedParameterSpec.X25519`.
- **X448**: tương tự với Curve448 và mức bảo mật nhắm tới cao hơn; JCA algorithm `X448` hoặc `XDH` với tham số `NamedParameterSpec.X448`.

**Điều không được nhầm:** KeyAgreement **không tự mã hóa dữ liệu, không tự xác thực đối tác, không tự cấp chứng thư và không tự tạo khóa AES an toàn theo giao thức**. Sau khi lấy shared secret, cần **KDF** có định danh ngữ cảnh (ví dụ HKDF) để dẫn xuất key cho AES-GCM hoặc key-encryption key (KEK) dùng bọc khóa. Muốn chống người ở giữa (MITM), phải **xác thực khóa công khai, chữ ký transcript hoặc danh tính đối tác**.

Luồng hai bên:

```text
 Alice                                               Bob
 private a                                           private b
 public A                                            public B
    |                                                    |
    |---------------------  A  ------------------------->|
    |<--------------------  B  --------------------------|
    |                                                    |
 DH/ECDH/X25519/X448(private a, B)      DH/ECDH/X25519/X448(private b, A)
    |                                                    |
    +--> shared secret S                    shared secret S <--+
                    |                                  |
             HKDF(salt, S, info)               HKDF(salt, S, info)
                    |                                  |
                session key  <------- bằng nhau ------> session key
                    |                                  |
                      AEAD (chẳng hạn AES-GCM)
```

Các khóa `a` và `b` không bao giờ được gửi đi. Chữ `A`, `B` trong sơ đồ là **khóa công khai được mã hóa đúng định dạng**, không phải raw shared secret.

## 2. So sánh DH, ECDH, X25519 và X448

| Thuật toán | Nhóm toán học / tham số chính | JCA KeyPairGenerator | JCA KeyAgreement | Shared secret trong ví dụ |
| --- | --- | --- | --- | --- |
| DH | Nhóm hữu hạn với `p, g`; ví dụ tham số DH 2048 bit | `"DH"` (alias `"DiffieHellman"`) | `"DH"` | Thường **256 byte** với tham số 2048 bit |
| ECDH | Đường cong EC có tên, ví dụ P-256 (`secp256r1`) | `"EC"` + `ECGenParameterSpec("secp256r1")` | `"ECDH"` | **32 byte** trên P-256 trong provider ví dụ |
| X25519 | X25519/Curve25519, giao thức theo RFC 7748 | `"X25519"` + `NamedParameterSpec("X25519")` | `"X25519"` | **32 byte** |
| X448 | X448/Curve448, theo RFC 7748 | `"X448"` + `NamedParameterSpec("X448")` | `"X448"` | **56 byte** |

Bảng cho biết **độ dài output của phép thỏa thuận**, **không** phải số byte AES key bắt buộc. KDF có thể tạo khóa AES-128 (16 byte) hoặc AES-256 (32 byte) nhưng **độ dài output dài hơn không làm tăng mức an toàn vượt entropy/security strength của đầu vào**. Ví dụ X25519 thường hướng tới mức bảo mật tương đương khoảng 128 bit; việc dẫn xuất AES-256 không tự biến toàn giao thức thành an toàn 256 bit.

### 2.1 DH: nhóm hữu hạn phải giống nhau

Với một nhóm DH hợp lệ có số nguyên tố `p` và phần tử sinh `g`, Alice chọn private exponent `a`, xuất `A = g^a mod p`; Bob chọn `b`, xuất `B = g^b mod p`. Sau khi nhận public của nhau, cả hai tính cùng:

```text
Alice: S = B^a mod p = g^(ab) mod p
Bob:   S = A^b mod p = g^(ab) mod p
```

**Điều kiện:** cả hai phải dùng **cùng nhóm p/g**, có kiểm tra độ an toàn của nhóm và public value. Không được tạo hai `DHParameterSpec` ngẫu nhiên độc lập rồi kỳ vọng DH thành công. Với `KeyPairGenerator("DH")`, có thể lấy tham số từ `((DHPublicKey) alice.getPublic()).getParams()` rồi khởi tạo generator bên còn lại bằng cùng tham số. Trong **hệ thống thực tế**, không chỉ tin một bộ `p,g` bất kỳ do phía mạng đề xuất: ưu tiên nhóm FFDHE chuẩn hóa, đủ mạnh, kiểm tra public key/subgroup và ràng buộc params vào handshake đã xác thực.

**2048 bit DH** được dùng trong ví dụ vì dễ triển khai bằng JDK phổ biến; đây là độ dài modulus, không đồng nghĩa mức bảo mật 2048 bit. Các hệ thống có yêu cầu bảo mật cao hơn có thể cần nhóm lớn hơn hoặc chọn thuật toán khác theo chính sách.

### 2.2 ECDH: cùng đường cong, khóa khác nhau

ECDH hoạt động với private scalar `a`/`b` và public points `A=aG`, `B=bG` trên cùng domain parameters. Cả hai tính shared point `abG`; provider chuyển thành byte shared secret theo quy tắc của thuật toán. `ECGenParameterSpec("secp256r1")` tạo key pair trên **P-256**, tên cũng thường gọi `prime256v1` ở nhiều công cụ.

**Không** dùng public P-384 hay khóa X25519 làm peer public cho một `KeyAgreement("ECDH")` khởi tạo từ private P-256. Algorithm, curve và tham số phải tương thích. Một object `KeyPairGenerator("EC")` **không** đồng nghĩa X25519: X25519 nằm trong họ `XDH` với key interfaces và phép tính khác.

### 2.3 X25519 và X448: tên thuật toán rõ ràng

X25519/X448 được chuẩn hóa trong RFC 7748. Chúng cho phép triển khai phép scalar multiplication trên các đường cong Montgomery với quy tắc cụ thể; thiết kế và key format không hoán đổi với `ECGenParameterSpec("secp256r1")`.

Java 17+ với provider hỗ trợ có thể dùng:

```java
// Đoạn minh họa; trong phương thức Java với các import tương ứng.
KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
generator.initialize(new NamedParameterSpec("X25519"), new SecureRandom());
KeyPair myPair = generator.generateKeyPair();
KeyAgreement ka = KeyAgreement.getInstance("X25519");
ka.init(myPair.getPrivate());
ka.doPhase(peerPublicKey, true);
byte[] sharedSecret = ka.generateSecret();
```

`NamedParameterSpec.X25519` và `NamedParameterSpec.X448` là các constant tiêu chuẩn có sẵn; ví dụ dùng constructor chuỗi để áp dụng cùng mã cho cả hai. Provider/phiên bản Java có thể không hỗ trợ một thuật toán/curve nhất định, khi đó cần xử lý `NoSuchAlgorithmException` hoặc `InvalidAlgorithmParameterException` một cách rõ ràng; không tự chuyển xuống nhóm yếu hoặc bỏ xác thực.

X25519 public key trên wire thường được biểu diễn bằng **raw 32 bytes** theo một giao thức cụ thể *hoặc* X.509 SPKI (ví dụ Java `getEncoded()`). X448 raw public value 56 byte. **Không trộn hai encoding**: `X509EncodedKeySpec` cần SPKI DER có ASN.1 header, không phải raw 32/56 byte.

## 3. Vòng đời KeyAgreement trong JCA

Mỗi bên thực hiện bốn bước cơ bản:

```text
KeyAgreement.getInstance(algorithm)
       |
       v
init(ourPrivateKey)
       |
       v
doPhase(peerPublicKey, true)   // lần cuối trong trao đổi 2 bên
       |
       v
generateSecret()               // shared secret byte[]
       |
       v
KDF + context + salt -> symmetric key / KEK
```

- **`getInstance`:** chọn phép thỏa thuận và provider; không tạo cặp khóa.
- **`init(privateKey)`:** cung cấp private key của **chính mình**, khác với public key cần được gửi cho đối tác. Sai key type sẽ ném `InvalidKeyException`.
- **`doPhase(peerPublic, true)`:** tiếp nhận public key của **đối tác**; flag `true` nói đây là pha cuối cùng. Trong giao thức DH **hai bên**, gọi đúng một lần. Các giao thức multi-party có thể có pha trung gian với `false`, không suy diễn rằng mọi thuật toán/provider đều hỗ trợ multi-party.
- **`generateSecret()`:** lấy shared secret **mới trong byte[]** sau khi pha cuối hoàn tất. Hai bên phải dùng khóa/params đúng và byte secret giống nhau. Nếu chưa `init`, chưa `doPhase` hoặc chưa đủ pha, `IllegalStateException` có thể xảy ra.

Theo Javadoc, `generateSecret()` đưa `KeyAgreement` về trạng thái sau lần `init` gần nhất; về mặt API có thể gọi `doPhase` và `generateSecret` lần nữa với cùng private key. **Nhưng** trong giao thức ephemeral, tái sử dụng private key thường là sai chính sách phiên: tốt hơn sinh cặp khóa mới cho mỗi handshake và không chia sẻ `KeyAgreement` stateful giữa thread/request.

Ngoài `generateSecret()` trả `byte[]`, JCA có overload `generateSecret(byte[], offset)` và `generateSecret(String algorithm)`; overload thứ ba phụ thuộc khả năng provider, *không thay thế một KDF có salt/info và nhãn phân tách domain theo giao thức*. **Không lấy các byte shared secret rồi dùng `new SecretKeySpec(secret, "AES")` một cách tùy tiện.** Độ dài có thể trùng kích thước AES nhưng kết quả cần qua KDF, binding ngữ cảnh và chính sách bảo mật giao thức.

## 4. Chương trình Java 17+: bốn thuật toán chung một mẫu KeyAgreement

Chương trình tự sinh hai cặp khóa (Alice/Bob) tương thích, mỗi bên gọi `init → doPhase → generateSecret`, so sánh byte bằng `MessageDigest.isEqual` và in kích thước secret. Không in private key hoặc shared secret.

Với **DH**, Bob nhận đúng `DHParameterSpec` (p/g) từ public key Alice trong **phạm vi demo**. Ngoài thực tế, việc trao nhóm DH phải theo chính sách nhóm chuẩn và được xác thực; không tin mù quáng params do người ngoài gửi.

Lưu thành **`KeyAgreementFamiliesDemo.java`**:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.NamedParameterSpec;
import javax.crypto.KeyAgreement;
import javax.crypto.interfaces.DHPublicKey;
import javax.crypto.spec.DHParameterSpec;
import java.util.Arrays;

public final class KeyAgreementFamiliesDemo {
    private static void test(String name, String agreement,
                             KeyPair alice, KeyPair bob) throws Exception {
        KeyAgreement a = KeyAgreement.getInstance(agreement);
        a.init(alice.getPrivate());
        a.doPhase(bob.getPublic(), true);
        byte[] sa = a.generateSecret();

        KeyAgreement b = KeyAgreement.getInstance(agreement);
        b.init(bob.getPrivate());
        b.doPhase(alice.getPublic(), true);
        byte[] sb = b.generateSecret();
        try {
            System.out.println(name + " equal="
                    + MessageDigest.isEqual(sa, sb)
                    + " bytes=" + sa.length);
        } finally {
            Arrays.fill(sa, (byte) 0);
            Arrays.fill(sb, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        KeyPairGenerator dhAliceGen =
                KeyPairGenerator.getInstance("DH");
        dhAliceGen.initialize(2048, random);
        KeyPair aliceDh = dhAliceGen.generateKeyPair();
        DHParameterSpec params =
                ((DHPublicKey) aliceDh.getPublic()).getParams();
        KeyPairGenerator dhBobGen =
                KeyPairGenerator.getInstance("DH");
        dhBobGen.initialize(params, random);
        KeyPair bobDh = dhBobGen.generateKeyPair();
        test("DH", "DH", aliceDh, bobDh);

        KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
        ec.initialize(new ECGenParameterSpec("secp256r1"), random);
        KeyPair aliceEc = ec.generateKeyPair();
        KeyPair bobEc = ec.generateKeyPair();
        test("ECDH-P256", "ECDH", aliceEc, bobEc);

        for (String name : new String[] { "X25519", "X448" }) {
            KeyPairGenerator x = KeyPairGenerator.getInstance(name);
            x.initialize(new NamedParameterSpec(name), random);
            test(name, name, x.generateKeyPair(), x.generateKeyPair());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 KeyAgreementFamiliesDemo.java
java KeyAgreementFamiliesDemo
```

Kết quả đã kiểm tra với runtime OpenJDK hỗ trợ bốn thuật toán:

```text
DH equal=true bytes=256
ECDH-P256 equal=true bytes=32
X25519 equal=true bytes=32
X448 equal=true bytes=56
```

Kết quả `equal=true` nghĩa là **hai phép thỏa thuận với private/public tương ứng đã sinh cùng các byte**, không chứng minh tính xác thực của một peer ngoài mạng. `DH bytes=256` là với modulus DH 2048 bit trong ví dụ; độ dài bytes có thể khác nếu sử dụng nhóm DH khác. `ECDH-P256 bytes=32` là encoding của shared result cho P-256; X25519/X448 có output 32/56 byte theo thuật toán.

**Bộ nhớ:** chương trình dùng `Arrays.fill(sa, (byte) 0)` để giảm lifetime của các mảng secret nó sở hữu, nhưng Java GC, provider, `KeyPair` objects và các bản sao nội bộ có thể tồn tại lâu hơn. Không xem `Arrays.fill` là bảo đảm xóa tuyệt đối mọi bản sao cryptographic secret.

## 5. Khóa công khai trên mạng: cách encode và validate

Để gửi khóa công khai giữa các tiến trình Java, thường dùng `getEncoded()` lấy **DER của X.509 SubjectPublicKeyInfo** rồi gửi kèm metadata thuật toán, version, curve/group, role và handshake ID. Bên nhận dùng `KeyFactory` với đúng thuật toán để tái tạo:

```java
// Đoạn minh họa trong phương thức Java; publicBytes lấy từ bản tin
// đã được parse và giới hạn kích thước, kèm hợp đồng thuật toán rõ ràng.
java.security.PublicKey imported =
        java.security.KeyFactory.getInstance("X25519")
                .generatePublic(new java.security.spec
                        .X509EncodedKeySpec(publicBytes));
```

Đoạn trên cố tình **không độc lập**: `publicBytes` đến từ giao thức. Với ECDH P-256, dùng `KeyFactory("EC")`; với DH dùng `KeyFactory("DH")`; với X448 dùng `KeyFactory("X448")`. Raw X25519/X448 point bytes của RFC 7748 không phải SPKI DER. Nếu wire protocol gửi raw u-coordinate, phải parse bằng API/format đúng (ví dụ provider hỗ trợ `XECPublicKeySpec`), không gắn nhãn X.509 một cách giả tạo.

Đối với khóa riêng: `PrivateKey.getEncoded()` nếu được phép export thường là **PKCS#8 DER**; **không** bao giờ truyền private key giữa Alice/Bob để thực hiện phép DH. Provider phần cứng có thể trả `null` cho `getEncoded()`; dùng key handle tương ứng thay vì ép export.

**Validation public key là ranh giới quan trọng:**

- **DH:** kiểm tra nhóm `p,g` nằm trong danh sách/tiêu chuẩn cho phép, độ mạnh và public DH value thuộc miền hợp lệ; với subgroup cần kiểm tra theo giao thức. Các giá trị `1`, `0`, `p-1` hoặc phần tử nhóm nhỏ có thể gây secret yếu/tấn công tùy cấu trúc nhóm. Không tin cấu hình nhóm do attacker tự đưa.
- **ECDH:** đường cong phải là curve được phép và khớp với private key; điểm công khai hợp lệ trên curve, không phải infinity/điểm sai subgroup (tùy curve/cofactor); dùng provider đáng tin có kiểm tra thích hợp và policy bổ sung khi nhập khóa từ untrusted input.
- **X25519/X448:** cần tuân thủ RFC 7748 và kiểm soát peer keys không hợp lệ/low-order, kể cả việc kiểm tra và từ chối **shared secret toàn số 0** theo yêu cầu giao thức. Một số JDK/provider sẽ từ chối key yếu trong `doPhase`/`generateSecret` bằng `InvalidKeyException`; đừng giả định mọi provider xử lý giống nhau. Không chấp nhận giá trị rỗng/nhóm sai như một secret bình thường.
- Mọi wire format phải có **giới hạn kích thước**, thuật toán/curve được allow-list và parser xử lý lỗi đúng. Public key có thể công khai nhưng vẫn là dữ liệu đầu vào **không đáng tin** đối với parser.

**Nhận diện peer:** ngay cả khi public key hợp lệ về toán học, nó vẫn có thể là khóa của Mallory. Một certificate chain đã xác minh, khóa pinned được phân phối an toàn, chữ ký trên transcript hoặc PSK-based authenticated handshake mới có thể liên kết khóa với danh tính.

## 6. Từ shared secret sang AES key: HKDF với salt và info

JCA `generateSecret()` trả vật liệu chung `S`, không phải format ciphertext. Shared secret của DH/ECDH có cấu trúc và phân bố riêng; không nên lấy `S` trực tiếp làm key AES hoặc lạm dụng `Arrays.copyOf(S, 16)`, `SHA256(S)` không có domain separation. Dùng **HKDF** chuẩn RFC 5869 với PRF như HMAC-SHA256:

```text
IKM  = KeyAgreement.generateSecret()
salt = 32 byte được chia sẻ giữa hai phía, không cần bí mật
PRK  = HKDF-Extract(salt, IKM) = HMAC_SHA256(salt, IKM)
info = protocol label || version || roles || transcript || key-purpose
OKM  = HKDF-Expand(PRK, info, requestedLength)
AES  = SecretKeySpec(OKM, "AES")
```

- **IKM** là input keying material. `PRK` là pseudorandom key. `OKM` là byte khóa đầu ra.
- **Salt** của HKDF không cần bí mật; có thể là một public handshake nonce hoặc một giá trị được hai bên thống nhất. Nếu protocol không cung cấp salt, HKDF còn có quy tắc salt toàn zero theo RFC 5869; **không** biến salt thành một private key thứ hai.
- **Info** ràng buộc *giao thức, phiên bản, hai khóa công khai, vai trò client/server, hướng truyền và mục đích tạo key*. Cả hai bên phải encode giống nhau **theo một chuẩn duy nhất**. Một chuỗi nối thiếu độ dài/ngăn cách có thể mơ hồ; nên dùng length prefixes hoặc format nhị phân có schema.
- Với nhiều khóa phiên, dùng label/info **khác nhau** cho `client→server key`, `server→client key`, nonce-base, key wrapping hoặc exporter secret. Không tái sử dụng cùng output HKDF cho nhiều mục đích.
- AES-256 cần 32 byte **OKM**. Với HMAC-SHA256, nếu chỉ cần 32 byte thì `HKDF-Expand` dùng **một block**: `T(1)=HMAC(PRK, info || 0x01)`. Nếu cần nhiều byte, phải thực hiện vòng lặp `T(i)=HMAC(PRK, T(i-1)||info||i)`, giới hạn tối đa 255 block; **không** dùng mã một-block bên dưới để sinh nhiều key cùng lúc mà không sửa.
- Key agreement không thay đổi tính chất **xác thực nguồn**. HKDF có info là transcript chưa được ký vẫn không chống MITM nếu Mallory thay các public keys và làm hai giao thức riêng.

Chương trình tiếp theo sẽ tự triển khai **trường hợp HKDF một block 32 byte** bằng `Mac.getInstance("HmacSHA256")` để hiểu cơ chế. Trong sản phẩm nên dùng thư viện HKDF được đánh giá, giữ metadata và test vectors, thay vì tự phát triển một KDF tổng quát.

## 7. Chương trình Java 17+: X25519 → HKDF-SHA256 → AES-GCM

Đây là ví dụ **end-to-end trong cùng một JVM** để chứng minh Alice/Bob tạo cùng shared secret, dẫn xuất cùng AES-256 key với **HKDF-Extract + một block HKDF-Expand**, mã hóa/giải mã bằng AES-GCM, và phát hiện sửa ciphertext/tag.

**Cảnh báo mô hình đe dọa:** chương trình chỉ có hai peer tin cậy trong một JVM; nó **chưa** triển khai xác thực peer, chữ ký transcript, certificate/pinning, framing mạng hay replay protection. Không xem đây là giao thức trao đổi khóa hoàn chỉnh có thể chép vào sản phẩm Internet. Khi triển khai thực, ưu tiên dùng TLS 1.3 hoặc một giao thức authenticated key exchange đã được đánh giá.

Lưu thành **`X25519HkdfAesGcmDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

public final class X25519HkdfAesGcmDemo {
    private static byte[] agree(KeyPair ours,
                                java.security.PublicKey theirs) throws Exception {
        KeyAgreement agreement = KeyAgreement.getInstance("X25519");
        agreement.init(ours.getPrivate());
        agreement.doPhase(theirs, true);
        return agreement.generateSecret();
    }

    private static byte[] transcript(byte[] a, byte[] b) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            byte[] domain = "demo-x25519-aes-gcm-v1"
                    .getBytes(StandardCharsets.US_ASCII);
            out.writeInt(domain.length);
            out.write(domain);
            out.writeInt(a.length);
            out.write(a);
            out.writeInt(b.length);
            out.write(b);
        }
        return bytes.toByteArray();
    }

    private static byte[] deriveAes256(
            byte[] shared, byte[] salt, byte[] info) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(salt, "HmacSHA256"));
        byte[] prk = mac.doFinal(shared);  // HKDF-Extract
        try {
            mac.init(new SecretKeySpec(prk, "HmacSHA256"));
            mac.update(info);
            mac.update((byte) 1);          // T(1), 32 bytes for AES-256
            return mac.doFinal();
        } finally {
            Arrays.fill(prk, (byte) 0);
        }
    }

    private static Cipher gcm(int mode, byte[] key, byte[] nonce)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(mode, new SecretKeySpec(key, "AES"),
                new GCMParameterSpec(128, nonce));
        return cipher;
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        KeyPairGenerator generator = KeyPairGenerator.getInstance("X25519");
        generator.initialize(new NamedParameterSpec("X25519"), random);
        KeyPair alice = generator.generateKeyPair();
        KeyPair bob = generator.generateKeyPair();

        byte[] secretA = agree(alice, bob.getPublic());
        byte[] secretB = agree(bob, alice.getPublic());
        byte[] salt = new byte[32];
        random.nextBytes(salt);
        byte[] info = transcript(
                alice.getPublic().getEncoded(),
                bob.getPublic().getEncoded());

        byte[] keyA = null;
        byte[] keyB = null;
        byte[] otherContextKey = null;
        try {
            System.out.println("sharedEqual="
                    + MessageDigest.isEqual(secretA, secretB));

            keyA = deriveAes256(secretA, salt, info);
            keyB = deriveAes256(secretB, salt, info);
            byte[] otherInfo = Arrays.copyOf(info, info.length + 1);
            otherInfo[otherInfo.length - 1] = 1;
            otherContextKey = deriveAes256(secretA, salt, otherInfo);
            System.out.println("derivedEqual="
                    + MessageDigest.isEqual(keyA, keyB));
            System.out.println("contextSeparated="
                    + !MessageDigest.isEqual(keyA, otherContextKey));
            System.out.println("derivedBits=" + (keyA.length * 8));

            byte[] nonce = new byte[12];
            random.nextBytes(nonce);
            byte[] aad = "record:1".getBytes(StandardCharsets.UTF_8);
            byte[] message = "Hello secure channel"
                    .getBytes(StandardCharsets.UTF_8);

            Cipher encrypt = gcm(Cipher.ENCRYPT_MODE, keyA, nonce);
            encrypt.updateAAD(aad);
            byte[] ciphertextAndTag = encrypt.doFinal(message);

            Cipher decrypt = gcm(Cipher.DECRYPT_MODE, keyB, nonce);
            decrypt.updateAAD(aad);
            byte[] recovered = decrypt.doFinal(ciphertextAndTag);
            System.out.println("roundTrip="
                    + Arrays.equals(message, recovered));

            byte[] modified = ciphertextAndTag.clone();
            modified[modified.length - 1] ^= 1;
            try {
                Cipher reject = gcm(Cipher.DECRYPT_MODE, keyB, nonce);
                reject.updateAAD(aad);
                reject.doFinal(modified);
                System.out.println("tamperRejected=false");
            } catch (AEADBadTagException expected) {
                System.out.println("tamperRejected=true");
            }
        } finally {
            Arrays.fill(secretA, (byte) 0);
            Arrays.fill(secretB, (byte) 0);
            if (keyA != null) Arrays.fill(keyA, (byte) 0);
            if (keyB != null) Arrays.fill(keyB, (byte) 0);
            if (otherContextKey != null)
                Arrays.fill(otherContextKey, (byte) 0);
        }
    }
}
```

Biên dịch và chạy độc lập:

```bash
javac --release 17 -encoding UTF-8 X25519HkdfAesGcmDemo.java
java X25519HkdfAesGcmDemo
```

Đầu ra đã xác minh:

```text
sharedEqual=true
derivedEqual=true
contextSeparated=true
derivedBits=256
roundTrip=true
tamperRejected=true
```

### 7.1 Tại sao chương trình cho kết quả này?

`sharedEqual=true`: X25519(private Alice, public Bob) và X25519(private Bob, public Alice) sinh cùng 32 byte. `derivedEqual=true`: HKDF nhận **cùng secret, salt và info**, nên hai phía tạo cùng 32 byte AES-256 material. `contextSeparated=true`: đổi một byte `info` tạo key khác (với xác suất áp đảo), minh họa domain separation.

`transcript(...)` tạo bytes gồm **length-prefixed** protocol label và SPKI DER của Alice/Bob theo một thứ tự cố định. Trong giao thức thật, cả hai phía phải đồng ý **vai trò và thứ tự**, thêm message transcript, algorithm negotiation và session identification, đồng thời **xác thực** nội dung transcript. Bản demo không tự làm việc đó.

`roundTrip=true`: `Cipher("AES/GCM/NoPadding")` nhận key byte từ HKDF, IV ngẫu nhiên 12 byte, tag 128 bit và AAD giống nhau ở phía giải mã. `tamperRejected=true`: thay byte cuối của ciphertext+tag khiến `doFinal` giải mã ném `AEADBadTagException`; không được sử dụng plaintext nếu tag không hợp lệ. `Cipher.updateAAD` phải xảy ra trước phần dữ liệu mã hóa/giải mã theo yêu cầu AEAD.

**IV GCM không được lặp dưới cùng key.** Trong ví dụ chỉ có một phép mã hóa, nên IV mới ngẫu nhiên 12 byte. Đối với phiên thực với hàng triệu bản ghi, cần nonce allocation/sequence number rõ ràng theo thiết kế giao thức và các giới hạn sử dụng AES-GCM. Không chỉ gọi `new SecureRandom` tùy tiện cho từng message khi đã có quy tắc nonce đếm của protocol; tránh tái sử dụng key+IV qua restart và retry.

**Bảo vệ secret:** `Arrays.fill` giảm tồn tại của các mảng do ứng dụng sở hữu, nhưng không đảm bảo xóa toàn bộ bản sao trong `KeyAgreement`/`Mac`/`Cipher`/`SecretKeySpec` hoặc các object khác. Không log raw shared secret, PRK, derived key, private keys hoặc ciphertext nhạy cảm. Chú ý `salt` và `info` trong ví dụ là public và không cần xóa để bảo mật, nhưng phải được truyền đúng giữa hai phía.

## 8. KeyAgreement không chống MITM: xác thực handshake là bắt buộc

Nếu chỉ trao public keys qua kết nối chưa xác thực:

```text
Alice                     Mallory                       Bob
  A ------> [chặn]           M1 -------->                B
  A <------  M2             [chặn] <--------             B
    |                       |                              |
 S_Alice-Mallory      hai shared secrets            S_Mallory-Bob
```

Mallory có thể tự tạo key pair cho mỗi phía rồi giải mã, đọc/sửa và mã hóa lại dữ liệu. **Thuật toán DH/ECDH/X25519/X448 vẫn tính đúng; thứ bị thiếu là liên kết public key với danh tính peer.** HMAC/HKDF hoặc AES-GCM chỉ xác thực **người biết key đã dẫn xuất**; không giúp Alice biết key đó thuộc Bob nếu Mallory là bên đang thỏa thuận.

Các cách khắc phục phải thuộc **một giao thức authenticated key exchange** rõ ràng:

1. **Xác thực chữ ký khóa/handshake:** peer dùng private signing key dài hạn ký transcript gồm cặp ephemeral keys, roles, algorithm/curve negotiation, random nonces và session context; phía còn lại xác minh bằng signing public key đã gắn danh tính tin cậy.
2. **PKI/certificate:** xác minh certificate chain, trust anchor, hostname/identity, validity, key usage và các ràng buộc giao thức; nhận public signing key từ certificate đã xác minh, không chỉ parse certificate rồi tin ngay.
3. **Pinned key / PSK:** khi có distribution channel đáng tin, dùng cơ chế pinning hoặc authenticated PSK handshake có key confirmation và chống downgrade; không tự nghĩ ra phép ghép MAC thiếu transcript binding.
4. **Giao thức sẵn có:** với truyền thông ứng dụng thực, ưu tiên **TLS 1.3** (hoặc framework/protocol authenticated đã đánh giá). Việc tự xây dựng giao thức trao đổi khóa từ primitive JCA có nhiều rủi ro về replay, reflection, downgrade, context confusion và quản lý phiên.

**Forward secrecy** chỉ đạt được theo điều kiện: dùng ephemeral private keys mới, xác thực handshake đúng, không lộ ephemeral secret trước/sau phiên, và xóa các vật liệu không cần giữ. Static DH có trường hợp sử dụng nhưng không tự có tính chất của ephemeral DH; việc key bị compromise về sau có thể ảnh hưởng phiên cũ theo cấu trúc giao thức.

## 9. Kết nối thỏa thuận khóa với bọc khóa và phiên dữ liệu

Mục “Thỏa thuận và bọc khóa” thường gồm hai bước tách nhau:

1. **Agreement:** Alice và Bob dùng DH/ECDH/XDH sinh shared secret, dẫn xuất khóa theo HKDF.
2. **Protection:** dùng key dẫn xuất làm **key-encryption key (KEK)** để bọc **data-encryption key (DEK)**, hoặc dùng trực tiếp làm key cho AEAD session theo giao thức.

Ví dụ mô hình bọc DEK:

```text
ECDH/X25519/X448 shared secret
          |
          v
 HKDF(info="app/KEK/v1", salt,...)
          |
          v
   256-bit key-encryption key
          |
          +----> AES Key Wrap (theo định dạng/giao thức)
          |      hoặc AES-GCM wrap kèm IV/tag/AAD đúng
          v
    wrapped DEK  --- gửi/lưu ---> bên nhận
                                |
                           cùng KEK hợp lệ
                                |
                            unwrap DEK
                                |
                         dùng DEK cho data
```

**Không** lấy raw shared secret làm DEK/KEK một cách trực tiếp chỉ vì mảng có độ dài 32 byte. Nếu bọc bằng AES-GCM, cần authenticated ciphertext, IV duy nhất và dữ liệu AAD phù hợp. Nếu dùng AES-KW, dùng transformation/format phù hợp nhà cung cấp và kiểm tra quy tắc độ dài, integrity của AES-KW. Tách nhãn `"KEK"` và `"AEAD session key"` bằng `info` trong HKDF; không dùng **cùng raw key cho mọi vai trò**.

Bản ghi lưu/truyền nên chỉ rõ: algorithm suite, curve/group, ephemeral public keys, salt/KDF version/info schema, IV/nonce, ciphertext+tag hoặc wrapped key, key ID/session ID và các trường đã được xác thực. Việc chứa public key, salt và IV trong metadata **không cần giữ bí mật**, nhưng phải bảo đảm integrity của những metadata quan trọng để tránh bị thay đổi trong handshake.

## 10. Bảo mật và lỗi triển khai thường gặp

| Lỗi / hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `InvalidKeyException` ở `init` / `doPhase` | Dùng public thay private, sai algorithm/curve, peer key không hợp lệ hoặc weak public key | Validate type/algorithm, nhóm và public key; dùng đúng private/public |
| `InvalidAlgorithmParameterException` | Key generator nhận curve/param không hợp lệ hoặc provider không chấp nhận | Dùng named curve/group allow-list, kiểm tra khả năng hỗ trợ |
| `NoSuchAlgorithmException` | Provider không có `ECDH`/`X25519`/`X448` | Kiểm tra Java/provider; không tự fallback nhóm yếu |
| `IllegalStateException` ở `generateSecret` | Chưa `init`, chưa đủ pha, hoặc dùng state sai | Theo đúng thứ tự `init → doPhase(..., true) → generateSecret` |
| DH tính bí mật không khớp / lỗi phase | Hai bên khởi tạo `DHParameterSpec` khác nhau | Chia sẻ cùng nhóm **đã xác thực**, kiểm tra p/g |
| Không khớp output HKDF dù shared secret trùng | Salt, info, role order hoặc encoding transcript khác nhau | Xác định wire format dài/byte order/labels một cách duy nhất |
| Dùng ECDH P-256 với peer public X25519 | Đây là hai thuật toán/curve không tương thích | Dùng EC/P-256 cho ECDH, XDH/X25519 cho X25519 |
| Gửi private key/`generateSecret()` qua mạng | Nhầm shared secret với public key | Chỉ gửi **public** material theo giao thức |
| Dùng `SecretKeySpec(shared, "AES")` ngay | Không có KDF/domain separation | HKDF với salt + context; derive key cho đúng mục đích |
| Không xác thực public key | MITM tạo 2 phiên agreement riêng | Dùng TLS/authenticated handshake/PKI/pinning |
| Chia sẻ cùng `KeyAgreement` giữa threads | Engine state bị trộn giữa nhiều session | Tạo engine theo mỗi handshake |
| Reuse ephemeral private key quá lâu | Ảnh hưởng forward secrecy và unlinkability | Sinh mới per session theo protocol và xóa vật liệu cũ |
| Dùng lại nonce AES-GCM với cùng key | Phá vỡ bảo mật AEAD | Nonce allocation không trùng và lifecycle theo protocol |
| Không kiểm tra shared secret toàn zero XDH | Peer input không hợp lệ/low-order có thể tạo bí mật yếu | Tuân thủ RFC/provider validation; không chấp nhận all-zero |
| Chỉ xem `equal=true` là đã an toàn | Chưa có xác thực danh tính hoặc KDF/AEAD | Bổ sung authentication, KDF, replay protection |
| Tự xây handshake không có transcript binding | Downgrade, reflection, role confusion, unknown key-share | Dùng giao thức đã được đánh giá, ký/bind toàn transcript |

**Lưu ý output length:** X25519 trả 32 byte, X448 56 byte; **không** cho rằng 56 byte là AES-448 key. AES chỉ nhận 16, 24 hoặc 32 byte và security strength của toàn hệ thống là mức yếu nhất trong các thành phần liên quan (group, KDF, AEAD, authentication, RNG, quản lý khóa).

**Khi gặp lỗi cryptographic:** không tiếp tục dùng shared secret/key chưa hoàn chỉnh hoặc plaintext AEAD chưa xác thực. Xóa/vô hiệu phiên, trả thông báo thất bại nhất quán cho tầng trên; tránh để lỗi chi tiết trở thành oracle giúp kẻ tấn công đoán private state. Không log bí mật, đừng “tạm chuyển” sang cipher không xác thực.

## 11. Hướng dẫn lựa chọn thuật toán

- **Ứng dụng mới cần trao đổi khóa:** thường ưu tiên **X25519** nếu toàn bộ hạ tầng/protocol hỗ trợ. Nó có API rõ ràng và cơ chế trao đổi khóa hiện đại; vẫn cần authentication + KDF + AEAD.
- **Liên thông với hệ thống EC/NIST:** **ECDH P-256** là lựa chọn phổ biến với `ECGenParameterSpec("secp256r1")`, thường được hỗ trợ tốt bởi PKI và hardware/enterprise systems.
- **Yêu cầu profile 448-bit curve:** **X448** cho mức bảo mật nhắm tới cao hơn nhưng tiêu tốn tài nguyên hơn, có thể hỗ trợ kém hơn; chọn khi protocol và tương thích peer yêu cầu.
- **Liên thông DH hữu hạn truyền thống:** **DH/FFDHE** với nhóm chuẩn tin cậy, tối thiểu độ dài theo chính sách (tránh nhóm yếu/khóa ngắn). Không dùng params nhận tùy tiện từ phía chưa xác thực; FFDHE-2048 có mức security strength thấp hơn X25519/P-256.
- **Ứng dụng có dữ liệu cần giữ bí mật dài hạn trước máy tính lượng tử:** DH, ECDH, X25519, X448 đều là key agreement **cổ điển**, không chống được máy tính lượng tử có quy mô đủ lớn. Cần đánh giá giao thức **hybrid post-quantum KEM + classical agreement** theo tiêu chuẩn tương ứng; không thể chỉ tăng độ dài HKDF hay thay AES-256 để khắc phục.

Dù chọn thuật toán nào, hệ thống vẫn cần test liên thông hai endpoint, kiểm tra key validation, xác thực transcript, xử lý replay/downgrade, nonce uniqueness và key rotation. Đừng benchmark chỉ phép `generateSecret()` mà bỏ qua key generation, serialization, network latency và provider overhead.

## 12. Tự kiểm tra kiến thức

1. **DH/ECDH/X25519/X448 truyền thứ gì qua mạng?** Khóa **công khai**, không truyền private key hay shared secret.
2. **Bên Alice gọi `KeyAgreement.init` với khóa nào?** Private key của **Alice**; `doPhase` với public key của **Bob**.
3. **Vì sao `doPhase(peer, true)` dùng `true`?** Đây là **pha cuối** của thỏa thuận hai bên, có thể gọi `generateSecret()` sau đó.
4. **Hai bên DH có thể tự tạo độc lập hai nhóm p/g khác nhau không?** Không; phải dùng **cùng nhóm phù hợp** và có validation.
5. **`ECDH` P-256 có phải X25519 không?** Không. Thuật toán, đường cong và API tham số khác nhau.
6. **X25519 và X448 shared secret dài bao nhiêu?** Lần lượt **32 byte** và **56 byte**.
7. **`generateSecret()` trả về AES key đã xác thực chưa?** Chưa; đây là raw shared secret, cần **KDF + protocol context + authentication**.
8. **Dùng HKDF với cùng IKM/salt nhưng khác info thì điều gì xảy ra?** Đầu ra khác (với xác suất áp đảo), hỗ trợ phân tách domain/key purpose.
9. **Vì sao người trung gian vẫn có thể đọc khi DH tính đúng?** Vì public keys **chưa được xác thực**, attacker thay bằng khóa của mình và duy trì hai secret.
10. **X25519 + HKDF + AES-GCM tự thành TLS an toàn không?** Không; còn thiếu authentication, transcript binding, replay/downgrade protection, quản lý phiên và giao thức đầy đủ.
11. **Sau `generateSecret()` KeyAgreement có thể tái sử dụng object không?** JCA API đưa về trạng thái sau `init`, nhưng với **ephemeral DH** nên dùng private key và engine mới cho từng handshake.
12. **GCM nhận key 56 byte của X448 trực tiếp như AES-448 không?** Không; derive ra AES-128/192/256 key qua KDF.
13. **DH hữu hạn dùng nhóm 2048 bit có tương đương 2048-bit security không?** Không; modulus length không bằng security strength.
14. **Muốn bọc DEK sau ECDH nên lấy khóa nào?** Derive một **KEK** bằng HKDF với purpose label và dùng cơ chế wrap có xác thực theo protocol, không dùng shared secret thô.
15. **Dùng private ephemeral mới có tự bảo đảm forward secrecy hoàn chỉnh không?** Chưa: cần authenticated handshake, key erasure và tránh lộ secret theo threat model.

## Tài liệu chuẩn và API chính thức

- [KeyAgreement, Java SE 21: init, doPhase, generateSecret và vòng đời reset](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KeyAgreement.html)
- [KeyPairGenerator, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyPairGenerator.html)
- [DHParameterSpec và DHPublicKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/spec/DHParameterSpec.html)
- [ECGenParameterSpec, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/ECGenParameterSpec.html)
- [NamedParameterSpec: X25519 và X448](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/NamedParameterSpec.html)
- [Mac, Java SE 21: HmacSHA256](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Mac.html)
- [Cipher: AES/GCM/NoPadding](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/Cipher.html)
- [RFC 7748: Elliptic Curves for Security (X25519, X448)](https://www.rfc-editor.org/rfc/rfc7748.html)
- [RFC 5869: HMAC-based Extract-and-Expand Key Derivation Function (HKDF)](https://www.rfc-editor.org/rfc/rfc5869.html)
- [RFC 7919: Negotiated Finite Field Diffie-Hellman Ephemeral Parameters for TLS](https://www.rfc-editor.org/rfc/rfc7919.html)
- [RFC 8446: TLS 1.3 và authenticated key exchange](https://www.rfc-editor.org/rfc/rfc8446.html)
