# Kiểm chứng tương tác với thư viện hoặc hệ thống khác khi tích hợp chữ ký Java 15+

## 1. Mục tiêu: cùng dữ liệu, cùng khóa, cùng thuật toán phải cho kết quả tương thích

Một dịch vụ Java có thể **ký dữ liệu**, rồi một dịch vụ Node.js, Python, Go, OpenSSL hoặc thư viện của đối tác **xác minh chữ ký**. Điều ngược lại cũng phải hoạt động khi giao thức yêu cầu: chữ ký do bên ngoài tạo được Java xác minh.

Kiểm thử chỉ gồm `Signature.sign()` và `Signature.verify()` trong cùng một chương trình Java **chưa đủ chứng minh tương tác liên nền tảng**: cả hai phía có thể cùng mắc lỗi mã hóa nhưng vẫn tự kiểm tra thành công. Một bộ kiểm thử tương tác tốt cần có **test vector độc lập**, định dạng khóa chuẩn và phép thử với **ít nhất một triển khai khác**.

Bài này nằm trong nhóm **Tích hợp chữ ký** của Java 15. Từ **Java 15**, JEP 339 đưa **EdDSA/Ed25519** vào Java SE như một API chính thức; các lớp `java.security.Signature`, `KeyFactory`, `PKCS8EncodedKeySpec`, `X509EncodedKeySpec` và `java.util.Base64` vẫn áp dụng trên Java hiện đại. Chúng ta sử dụng **Ed25519** làm ví dụ kiểm thử; mã Java chạy với **JDK 17+** và ví dụ phía hệ thống khác dùng **Node.js `node:crypto`** hiện hành.

**Tiêu chí thành công:**

1. Java nhập đúng public/private key ở định dạng chuẩn.
2. Java xác minh đúng chữ ký trong **RFC 8032** không do chương trình Java tự tạo.
3. Java ký cùng dữ liệu và tạo **đúng byte[] chữ ký** theo test vector (Ed25519 chuẩn có kết quả xác định với cùng khóa và thông điệp).
4. Node.js độc lập xác minh chữ ký và ký lại ra đúng những bytes ấy.
5. Mọi biến đổi byte của thông điệp hoặc chữ ký đều bị **từ chối**; quá trình Base64 chỉ thay cách biểu diễn, không thay bytes.

Đừng coi tên thuật toán trùng nhau hoặc chứng minh “hai bên cùng in `true`” là điều kiện đủ. Phải chứng minh **bytes, định dạng khóa, thuật toán/biến thể và trust model** đều nhất quán.

## 2. Hợp đồng tương tác cần thống nhất trước

| Thành phần | Quy ước trong bài | Sai lệch thường gặp |
| --- | --- | --- |
| **Thuật toán chữ ký** | `Ed25519` thuần theo RFC 8032 | Một phía dùng Ed25519ph/Ed448 hoặc ký hash trước, phía kia dùng Ed25519 trực tiếp. |
| **Thông điệp** | Dãy **byte[] chính xác**; test vector dùng một byte `0x72` | Một bên ký chuỗi hai ký tự `"72"` (UTF-8: `0x37 0x32`) thay vì byte `0x72`. |
| **Public key** | `SubjectPublicKeyInfo` (SPKI) mã hóa ASN.1 DER; Java `X509EncodedKeySpec`, Node `type: 'spki'` | Nhầm 32 raw public-key bytes với đối tượng SPKI DER. |
| **Private key** | `PKCS#8` DER của Ed25519; Java `PKCS8EncodedKeySpec`, Node `type: 'pkcs8'` | Nhầm seed Ed25519 32 byte với nguyên file PKCS#8; đưa raw seed trực tiếp vào KeyFactory. |
| **Chữ ký** | Ed25519 `byte[64]` theo RFC 8032 | Nhầm với chữ ký ASN.1 DER của ECDSA hoặc tự chuyển bytes chữ ký sang chuỗi UTF-8. |
| **Mã hóa vận chuyển** | Base64 Basic hoặc Base64URL **đúng cặp encoder/decoder** | Dùng decoder Base64 Basic cho payload có `-`/`_` của Base64URL, hoặc đổi dấu đệm tùy tiện. |
| **Nguồn tin cậy của public key** | Trust store/certificate/pinning hoặc nguồn được xác thực | Nhận public key tùy ý kèm chữ ký rồi cho rằng chữ ký chứng minh danh tính. |

**Đừng tự giả định “tích hợp Ed25519” đồng nghĩa định dạng khóa giống nhau.** Các thư viện có thể nhận **raw seed**, **raw public key**, **PKCS#8 DER**, **SPKI DER**, **PEM** hoặc cấu trúc JWK/COSE. API cần được kiểm tra bằng tài liệu của thư viện và **test vector** thực tế.

## 3. Quy tắc về byte[]: text giống mắt nhìn có thể khác bytes

Java ký và xác minh trên **bytes**:

~~~java
byte[] payload = "Đơn hàng 42".getBytes(StandardCharsets.UTF_8);

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(payload);
byte[] signatureBytes = signer.sign();
~~~

Đây là **đoạn minh họa**, giả sử `privateKey` đã có. Đối tác phải sử dụng **đúng `payload`** khi xác minh.

Các lỗi đặc biệt hay gặp khi tương tác:

- **Hex và text:** một chuỗi biểu diễn hex như `"72"` có hai ký tự ASCII; giải mã hex bằng `HexFormat.parseHex("72")` tạo **một byte**. Hai thông điệp hoàn toàn khác nhau.
- **UTF-8:** Java `String` được lập chỉ mục theo UTF-16, nhưng payload truyền qua mạng có thể là UTF-8. Dùng `StandardCharsets.UTF_8` hoặc truyền byte[] nguyên trạng.
- **Dấu tiếng Việt:** `"ắ"` dạng NFC có thể khác bytes với dạng NFD (`a` + dấu breve + dấu sắc). Java `String.equals` không tự chuẩn hóa; thư viện đối tác cũng không có nghĩa vụ tự chuẩn hóa.
- **JSON:** khoảng trắng, thứ tự thuộc tính, cách escape Unicode và cách biểu diễn số có thể làm thay đổi bytes. Nếu hai hệ thống muốn ký cấu trúc JSON, cần **định nghĩa canonicalization** hoặc truyền payload gốc không serialize lại.
- **Xuống dòng:** `LF` và `CRLF` tạo bytes khác nhau. Thêm newline cuối file chỉ ở một phía có thể làm xác minh sai.
- **Hash trước:** `Ed25519` thuần ký trực tiếp **message bytes** trong cơ chế Ed25519. Không tự thực hiện `SHA-256(message)` rồi gọi `Ed25519.sign` nếu giao thức yêu cầu ký message; Ed25519ph là **biến thể khác** với quy tắc riêng, không phải Ed25519 + hash tùy chọn.

Mục tiêu của kiểm thử tương tác là **so sánh dữ liệu ở lớp byte**, không so chỉ đối tượng Java hay chuỗi đã được hiển thị.

## 4. RFC 8032: test vector độc lập để tránh “tự kiểm tra chính mình”

RFC 8032 đưa ra các vector Ed25519 chuẩn. Dùng **test vector thứ hai** có thông điệp một byte:

| Trường | Dữ liệu hex |
| --- | --- |
| Seed private Ed25519 (32 byte) | `4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb` |
| Raw public key (32 byte) | `3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c` |
| Thông điệp (1 byte) | `72` |
| Chữ ký Ed25519 (64 byte) | `92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00` |

Đây là **khóa thử nghiệm công khai**, tuyệt đối **không dùng seed này để ký dữ liệu sản xuất**, vì private seed đã được công bố trong RFC. Không nhầm seed 32 byte với `PrivateKey`/`PKCS8EncodedKeySpec` mà Java nhận.

### 4.1. SPKI DER và PKCS#8 DER

Java `KeyFactory.getInstance("Ed25519")` có thể nhập:

- `X509EncodedKeySpec`: public key chứa **SPKI DER**. Với Ed25519 test vector này, DER dạng tối giản có tiền tố hex `302a300506032b6570032100`, tiếp theo **32 raw public-key bytes**.
- `PKCS8EncodedKeySpec`: private key chứa **PKCS#8 DER**. Với fixture Ed25519 tối giản này, tiền tố hex `302e020100300506032b657004220420`, tiếp theo **32 seed bytes**.

Các prefix này biểu diễn cấu trúc ASN.1 DER cụ thể theo quy tắc RFC 8410; **không phải công thức chung để nối tùy ý vào mọi khóa/tập tham số**. Trong ứng dụng thật, nên **import/export qua KeyFactory/KeyStore/công cụ thư viện đúng chuẩn**, không tự thao tác byte ASN.1 nếu chưa có yêu cầu kiểm thử riêng.

SPKI là **cấu trúc chứa khóa công khai**, không tự là một chứng chỉ X.509 hoàn chỉnh. Chuỗi PEM `BEGIN PUBLIC KEY` có thể chứa chính **SPKI DER được Base64 và đặt giữa các dòng đánh dấu**; đây vẫn là cùng key material, chỉ thay vỏ biểu diễn.

### 4.2. Vì sao fixture chuẩn mạnh hơn test tự tạo?

Nếu một chương trình Java tự tạo khóa, tự ký rồi tự xác minh, cả hai phép có thể đồng nhất trong cùng provider nhưng chưa cho thấy khả năng nhập một cấu trúc khóa chuẩn từ bên ngoài. Test vector RFC giúp kiểm tra độc lập:

1. **Import khóa** từ bytes DER đã biết.
2. **Verify** chữ ký đã được RFC công bố.
3. **Sign** và đối chiếu **chính xác từng byte** với chữ ký tham chiếu.
4. Đưa **cùng bytes** cho một thư viện khác và lặp lại.

**Ed25519 thuần cho chữ ký xác định** từ cùng private key và message, nên so sánh byte-for-byte với test vector là hợp lệ. Không suy rộng quy tắc này cho mọi thuật toán chữ ký khác (chẳng hạn các thuật toán dùng randomness hoặc cách mã hóa khác nhau).

## 5. Chương trình Java 17+ độc lập

Tạo file **`Ed25519InteropChecks.java`** (UTF-8). Ví dụ dùng `java.util.HexFormat`, được hỗ trợ từ Java 17, để tránh lỗi tự viết parser hex. Phần ký và xác minh dùng API `Signature` hiện hành, không cần dependency ngoài JDK.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.text.Normalizer;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;

public class Ed25519InteropChecks {
    private static final HexFormat HEX = HexFormat.of();
    private static final String SEED =
            "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb";
    private static final String PUBLIC =
            "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c";
    private static final String MESSAGE = "72";
    private static final String SIGNATURE =
            "92a009a9f0d4cab8720e820b5f642540"
          + "a2b27b5416503f8fb3762223ebdb69d"
          + "a085ac1e43e15996e458f3613d0f11d8"
          + "c387b2eaeb4302aeeb00d291612bb0c00";
    private static int checks;

    private static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError(label);
        checks++;
        System.out.println(label + "=PASS");
    }

    private static boolean verifies(PublicKey key, byte[] message, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(message);
        try {
            return verifier.verify(signature);
        } catch (SignatureException malformed) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] message = HEX.parseHex(MESSAGE);
        byte[] expected = HEX.parseHex(SIGNATURE);
        byte[] publicDer = HEX.parseHex("302a300506032b6570032100" + PUBLIC);
        byte[] privateDer = HEX.parseHex("302e020100300506032b657004220420" + SEED);

        KeyFactory factory = KeyFactory.getInstance("Ed25519");
        PublicKey publicKey = factory.generatePublic(new X509EncodedKeySpec(publicDer));
        PrivateKey privateKey = factory.generatePrivate(new PKCS8EncodedKeySpec(privateDer));

        check("derPublicRoundTrip", Arrays.equals(publicDer, publicKey.getEncoded()));
        check("derPrivateRoundTrip", Arrays.equals(privateDer, privateKey.getEncoded()));
        check("rfcVectorVerify", verifies(publicKey, message, expected));

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(privateKey);
        signer.update(message);
        byte[] generated = signer.sign();
        check("rfcVectorSign", Arrays.equals(expected, generated));
        check("generatedVerify", verifies(publicKey, message, generated));
        check("signature64Bytes", generated.length == 64);

        String base64 = Base64.getEncoder().encodeToString(generated);
        String base64Url = Base64.getUrlEncoder().withoutPadding().encodeToString(generated);
        check("base64Wire", Arrays.equals(generated, Base64.getDecoder().decode(base64)));
        check("base64UrlWire",
                Arrays.equals(generated, Base64.getUrlDecoder().decode(base64Url)));

        byte[] changed = message.clone();
        changed[0] ^= 1;
        check("changedMessageRejected", !verifies(publicKey, changed, generated));

        byte[] changedSig = generated.clone();
        changedSig[0] ^= 1;
        check("changedSignatureRejected", !verifies(publicKey, message, changedSig));

        String nfc = "ắ";
        String nfd = Normalizer.normalize(nfc, Normalizer.Form.NFD);
        check("textBytesCanDiffer",
                !Arrays.equals(nfc.getBytes(StandardCharsets.UTF_8),
                               nfd.getBytes(StandardCharsets.UTF_8)));
        System.out.println("TOTAL_PASS=" + checks);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac --release 17 -encoding UTF-8 Ed25519InteropChecks.java
java Ed25519InteropChecks
~~~

**Stdout chính xác**, đã được đối chiếu với JDK 24 khi biên dịch mức Java 17:

~~~text
derPublicRoundTrip=PASS
derPrivateRoundTrip=PASS
rfcVectorVerify=PASS
rfcVectorSign=PASS
generatedVerify=PASS
signature64Bytes=PASS
base64Wire=PASS
base64UrlWire=PASS
changedMessageRejected=PASS
changedSignatureRejected=PASS
textBytesCanDiffer=PASS
TOTAL_PASS=11
~~~

Ý nghĩa kiểm thử:

- **`derPublicRoundTrip` / `derPrivateRoundTrip`:** `KeyFactory` đọc và xuất lại đúng fixture DER tối giản trên provider JDK được kiểm thử. Những provider khác có thể chuẩn hóa lại hình thức ASN.1 hợp lệ theo quy định của chúng; khi đó, điều quan trọng hơn là **khóa cùng giá trị và ký/xác minh được vector**.
- **`rfcVectorVerify`:** Java xác minh thành công chữ ký **không do Java tự tạo**.
- **`rfcVectorSign`:** chữ ký Java tạo trùng đúng **64 byte** của RFC 8032. Đây là kiểm chứng chéo quan trọng của Ed25519.
- **`generatedVerify` / `signature64Bytes`:** bảo đảm chữ ký phát sinh hợp lệ và kích thước đúng.
- **`base64Wire` / `base64UrlWire`:** hai kiểu mã hóa văn bản đều bảo toàn bytes khi dùng đúng decoder.
- **`changedMessageRejected`:** thay một bit của message khiến xác minh thất bại.
- **`changedSignatureRejected`:** sửa chữ ký phải bị từ chối. Hàm helper xử lý cả kết quả `false` lẫn `SignatureException` khi provider không giải mã được chữ ký hỏng.
- **`textBytesCanDiffer`:** chứng minh chữ tiếng Việt dạng NFC và NFD có thể khác byte UTF-8 dù nhìn giống nhau.

Trong ứng dụng thật, **không nên dùng một seed/private key cố định công khai**. Program này chỉ là fixture kiểm thử tương thích, không sinh hoặc quản lý khóa sản xuất.

## 6. Đối chiếu bằng hệ thống khác: Node.js node:crypto

Để tránh phụ thuộc toàn bộ vào JDK, dùng **Node.js `node:crypto`** (API chuẩn) nhập **cùng SPKI/PKCS#8 DER**, xác minh cùng test vector và tạo chữ ký có bytes trùng với Java.

Tạo file **`interop-check.cjs`**:

~~~javascript
const { createPublicKey, createPrivateKey, sign, verify } = require('node:crypto');

const seed = '4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb';
const pub = '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c';
const sig = '92a009a9f0d4cab8720e820b5f642540'
          + 'a2b27b5416503f8fb3762223ebdb69d'
          + 'a085ac1e43e15996e458f3613d0f11d8'
          + 'c387b2eaeb4302aeeb00d291612bb0c00';

const data = Buffer.from('72', 'hex');
const expected = Buffer.from(sig, 'hex');
const publicKey = createPublicKey({
  key: Buffer.from('302a300506032b6570032100' + pub, 'hex'),
  format: 'der', type: 'spki'
});
const privateKey = createPrivateKey({
  key: Buffer.from('302e020100300506032b657004220420' + seed, 'hex'),
  format: 'der', type: 'pkcs8'
});

const results = {
  nodeVerifyVector: verify(null, data, publicKey, expected),
  nodeSignMatchesJavaVector: sign(null, data, privateKey).equals(expected),
  nodeRejectsTamper: !verify(null, Buffer.from('73', 'hex'), publicKey, expected)
};

for (const [key, value] of Object.entries(results)) {
  console.log(key + '=' + value);
  if (!value) process.exitCode = 1;
}
~~~

Chạy trên **Node.js có hỗ trợ Ed25519**:

~~~bash
node interop-check.cjs
~~~

**Kết quả đã đối chiếu với Node.js 24.19.0:**

~~~text
nodeVerifyVector=true
nodeSignMatchesJavaVector=true
nodeRejectsTamper=true
~~~

Điểm đáng chú ý: với Ed25519 trong `node:crypto`, đối số thuật toán của `sign(algorithm, ...)` và `verify(algorithm, ...)` phải là **`null`** trong cách dùng trên; thuật toán Ed25519 được xác định bởi loại khóa. **Không truyền `'sha256'` như khi ký RSA/ECDSA với hash**, và không tự hash message trước khi gọi hàm. `Buffer.from(..., 'hex')` ở Node tương ứng với `HexFormat.parseHex(...)` trong Java; cả hai đều nhận byte `0x72`, không phải chuỗi ký tự `"72"`.

Vì Java và Node.js đều xác minh chữ ký trong RFC, đồng thời ký ra **cùng bytes**, chúng đã vượt qua kiểm tra tương tác về **thuật toán Ed25519, định dạng khóa và dữ liệu byte** ở test vector này. Kết quả không tự chứng minh mọi cấu hình giao thức/encoding/triển khai ngoài đời đều tương thích; vẫn cần kiểm thử payload và key format của tích hợp thực tế.

## 7. So sánh API Java và Node.js khi tích hợp

| Nhiệm vụ | Java SE | Node.js `node:crypto` |
| --- | --- | --- |
| Import public key SPKI DER | `KeyFactory.getInstance("Ed25519").generatePublic(new X509EncodedKeySpec(bytes))` | `createPublicKey({key: buffer, format: 'der', type: 'spki'})` |
| Import private key PKCS#8 DER | `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(bytes))` | `createPrivateKey({key: buffer, format: 'der', type: 'pkcs8'})` |
| Ký Ed25519 | `Signature.getInstance("Ed25519")` → `initSign` → `update` → `sign()` | `sign(null, buffer, privateKey)` |
| Xác minh Ed25519 | `initVerify` → `update` → `verify(signatureBytes)` | `verify(null, buffer, publicKey, signatureBuffer)` |
| Hex → bytes | `HexFormat.of().parseHex(hex)` (Java 17+) | `Buffer.from(hex, 'hex')` |
| Base64 Basic → bytes | `Base64.getDecoder().decode(text)` | `Buffer.from(text, 'base64')` |
| Bytes → Base64 Basic | `Base64.getEncoder().encodeToString(bytes)` | `buffer.toString('base64')` |

**Không giả định hai runtime có cùng chính sách xử lý input sai.** Một thư viện có thể trả `false` đối với chữ ký không khớp; thư viện khác có thể ném ngoại lệ khi chữ ký có encoding không hợp lệ. Trong hệ thống, cả hai đều dẫn đến **từ chối**, đồng thời giữ nguyên nhân kỹ thuật để điều tra.

Không dùng `new String(signatureBytes, UTF_8)` rồi chuyển lại sang `byte[]`: chữ ký nhị phân có thể không phải UTF-8 hợp lệ. Chuyển chữ ký qua **Base64 hoặc Base64URL**, decode chính xác ở receiver rồi mới gọi `verify`.

## 8. Hợp đồng truyền dữ liệu giữa Java và hệ thống đối tác

Một giao thức JSON có thể định nghĩa envelope dạng sau (đây là **sơ đồ cấu trúc**, không phải chữ ký hợp lệ cố định):

~~~json
{
  "alg": "Ed25519",
  "kid": "active-key-v3",
  "payloadEncoding": "base64url",
  "payload": "cg",
  "signature": "base64url-of-real-signature"
}
~~~

Trong ví dụ này, `payload` là Base64URL không padding của một byte `0x72`: `"cg"`. Trường `signature` ở sơ đồ chỉ minh họa vị trí của **chữ ký thực** mà bên gửi phải tạo; **không đưa chữ ký biểu diễn dạng chữ này vào verifier**.

Một quy trình phía receiver nên làm theo thứ tự:

1. **Giới hạn kích thước** request, từng trường và số byte dự kiến sau giải mã, trước khi phân bổ bộ nhớ lớn.
2. Đọc `alg` và `kid` nhưng **đối chiếu với thuật toán/khóa nằm trong allowlist đã cấu hình**. Các trường do bên gửi tự khai báo **không tự cấp quyền** chọn thuật toán hoặc public key tùy ý.
3. Dùng `Base64.getUrlDecoder()` ở Java hoặc API Base64URL tương ứng để giải mã `payload` và `signature` về **bytes**. Không parse/serialize payload rồi mới verify nếu điều đó làm thay đổi bytes.
4. Lấy public key đáng tin cậy tương ứng `kid` (ví dụ từ certificate/trust store, pinned key hoặc key registry đã xác thực).
5. Khởi tạo `Signature("Ed25519")`, `initVerify(trustedKey)`, `update(payloadBytes)` rồi `verify(sigBytes)`; nếu `false` hoặc lỗi chữ ký không hợp lệ, **từ chối**.
6. Sau khi xác minh, áp dụng chính sách nghiệp vụ: timestamp, nonce, audience, expiry, replay protection và quyền của danh tính người ký.

**Phạm vi chữ ký rất quan trọng:** nếu chỉ ký `payloadBytes`, các trường `alg`, `kid` và timestamp đặt ngoài payload **không tự được bảo vệ bằng chữ ký**. Nếu giao thức cần xác thực các metadata đó, chúng phải được đưa vào một biểu diễn byte **được ký** hoặc được bảo vệ bởi một giao thức có đặc tả ràng buộc phù hợp (ví dụ JWS có protected header theo chuẩn). Không tự thiết kế một envelope thiếu ràng buộc bảo mật rồi nghĩ rằng Base64 khiến thông tin được bảo vệ.

### Base64URL không giống Base64 Basic

- **Base64 Basic:** dùng `+`, `/` và thông thường có `=` ở cuối.
- **Base64URL:** dùng `-`, `_`; có thể bỏ `=` theo hợp đồng.
- Việc một chuỗi ngắn tình cờ được cả hai decoder xử lý **không chứng minh hai biến thể tương đương**. Cần nhất quán encoder/decoder theo giao thức.
- Bỏ hoặc thêm padding không thay đổi giá trị bytes nếu vẫn tuân theo cú pháp được cho phép; nhưng một giao thức yêu cầu **định dạng văn bản chuẩn hóa** có thể cần quy định rõ padding.
- Base64 **không phải mã hóa bí mật** và không thay thế TLS hay chữ ký số.

## 9. Ma trận kiểm thử tương tác nên có trong CI

| Nhóm kiểm thử | Điều kiện đầu vào | Kỳ vọng |
| --- | --- | --- |
| **RFC độc lập** | Bytes message, public key và signature từ RFC 8032 | Java và hệ thống đối tác đều xác minh thành công. |
| **Ký chéo** | Cùng seed test và message bytes | Chữ ký Ed25519 sinh ra khớp test vector byte-for-byte. |
| **Key format** | Import/export SPKI/PKCS#8 và PEM phù hợp | Đối tượng khóa được tạo đúng; raw key không bị nhầm với DER wrapper. |
| **Base64** | Signature/payload qua Basic và Base64URL | Bytes giải mã phải bằng bytes gốc. |
| **Message bị sửa** | Chỉ thay một byte message, giữ chữ ký | Hai bên đều từ chối xác minh. |
| **Chữ ký bị sửa** | Thay một byte chữ ký, giữ message | Hai bên từ chối; bắt được lỗi parsing chữ ký nếu provider ném ngoại lệ. |
| **Public key sai** | Public key không cùng cặp | `initVerify` có thể thành công nhưng `verify` phải thất bại. |
| **Payload Unicode** | UTF-8 tiếng Việt, emoji, NFC/NFD | Các bên xác minh **cùng byte[]**, không tự chuẩn hóa khác nhau. |
| **JSON/serialization** | Đổi thứ tự trường, xuống dòng, định dạng số | Xác minh chỉ thành công với đúng bytes hoặc cùng canonicalization chuẩn. |
| **Ràng buộc giao thức** | Sai `alg`/`kid`, expiry, replay | Từ chối theo chính sách mà không bị downgrade/algorithm confusion. |
| **Provider/runtime** | JDK khác phiên bản, Node.js hoặc thư viện khác | Chạy cùng vector và test sai dữ liệu; ghi nhận version/provider để truy vết. |

Khi có thể, nên tổ chức **fixture byte[] cố định** trong repository kiểm thử (không dùng private key sản xuất), để Java, Node.js và các triển khai khác đọc cùng đầu vào và ghi nhận cùng kết quả. Đừng chỉ viết test “Java tự ký thì Java tự verify”: test đó thiếu chứng cứ về định dạng liên hệ giữa hệ thống.

## 10. Các sai lầm chẩn đoán thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Cùng thuật toán `Ed25519` thì mọi mã khóa đều tương thích | Còn phải cùng **SPKI/PKCS#8/raw/PEM** theo hợp đồng, và khóa phải đúng cặp. |
| Seed 32 byte là nội dung đưa thẳng vào `PKCS8EncodedKeySpec` | Không. `PKCS8EncodedKeySpec` cần **bytes DER PKCS#8**, không phải raw seed. |
| SPKI DER là chứng chỉ X.509 | SPKI chứa public key, không phải chứng chỉ đầy đủ với chủ thể/chữ ký CA. |
| Chuỗi `"72"` tương đương một byte `0x72` | UTF-8 `"72"` gồm hai byte `0x37 0x32`; test vector dùng một byte. |
| Bên Java verify cùng chữ ký Java ký nên chắc chắn tương tác được với Node | Cần **test vector độc lập** và phép thử ở Node/đối tác. |
| Chữ ký Ed25519 cần mã hóa DER như ECDSA | Theo RFC 8032, signature Ed25519 là **64 bytes** theo cấu trúc chuẩn, không phải ECDSA DER sequence. |
| Ed25519 được gọi với SHA-256 ở mọi thư viện | Ed25519 thuần không nhận hash ngoài như một tùy chọn tự do; **Ed25519ph** là biến thể khác. |
| Java String/JSON được hai bên đọc giống mắt nhìn thì bytes chắc giống nhau | Unicode normalization, charset, CRLF, JSON serialization có thể làm bytes khác. |
| `Signature.verify` chỉ có thể trả `true`/`false` | Java còn có thể ném `SignatureException` nếu signature malformed. |
| Base64 làm payload đáng tin hoặc bí mật | Base64 chỉ mã hóa biểu diễn. Trust phụ thuộc khóa công khai và quy trình xác minh. |
| Chữ ký đúng chứng minh ngay người gửi là ai | Chỉ khi **public key được ràng buộc với danh tính đáng tin**. |
| Có thể tự động fallback sang thuật toán yếu nếu Ed25519 không khả dụng | Không; cần sửa cấu hình/provider hoặc nâng cấp giao thức có kiểm soát. |

## 11. Nguồn chuẩn và API hiện hành

- [RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032): quy tắc Ed25519 và **test vector thứ hai** dùng ở bài.
- [RFC 8410 — Algorithm Identifiers for Ed25519 and Ed448](https://www.rfc-editor.org/rfc/rfc8410): cấu trúc và OID cho Ed25519 trong SPKI/PKCS#8.
- [RFC 4648 — Base64 and Base64URL](https://www.rfc-editor.org/rfc/rfc4648): bảng ký tự, padding và biểu diễn chuẩn.
- [JEP 339 — Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): hỗ trợ EdDSA chính thức trong Java 15.
- [Java SE 26 — java.security.Signature](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): `getInstance`, `initSign`, `initVerify`, `update`, `sign`, `verify`.
- [Java SE 26 — KeyFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyFactory.html): nhập khóa từ `KeySpec`.
- [Java SE 26 — X509EncodedKeySpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): public key SPKI.
- [Java SE 26 — PKCS8EncodedKeySpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html): private key PKCS#8.
- [Java SE 26 — Base64](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html): encoder/decoder Basic, URL-safe.
- [Node.js — Crypto API, sign and verify](https://nodejs.org/api/crypto.html): `node:crypto`, Ed25519 signatures và nhập khóa DER.

**Kết luận:** tích hợp chữ ký với thư viện hay hệ thống khác chỉ đáng tin khi **cùng byte[] thông điệp, thuật toán/biến thể, định dạng khóa và public key đã xác thực**. Dùng test vector RFC 8032 và kiểm thử Java ↔ Node.js là bằng chứng chéo quan trọng; sau đó kiểm tra riêng hợp đồng truyền tải, Unicode, Base64, metadata được ký và các trường hợp dữ liệu bị sửa.