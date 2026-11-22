# Vector kiểm thử chuẩn và kiểm thử dữ liệu bị sửa khi tích hợp chữ ký số (Java 15)

> **Mục tiêu:** Thiết kế bộ kiểm thử chữ ký số có thể lặp lại, dựa trên **vector chuẩn (known-answer tests, KAT)** và các **negative tests**: sửa thông điệp, sửa/cắt chữ ký, sai khóa công khai, khác chuỗi bytes do Unicode/serialization, khác context hoặc sai thuật toán. Bài đặt trong nhóm **Tích hợp chữ ký** của Java 15, sử dụng **Ed25519 và Ed448 chính thức có từ JDK 15 (JEP 339)**, vector công khai của **RFC 8032 `7**, API JCA ổn định và ví dụ Java 17+ chạy được. Chỉ sử dụng kiến thức còn áp dụng trên Java hiện đại; không dùng thuật toán đã lỗi thời hay provider API nội bộ.

## 1. Vì sao round-trip ký rồi verify vẫn chưa đủ?

Một kiểm thử thường thấy:

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);
signer.update(message);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
verifier.update(message);
boolean ok = verifier.verify(signature); // true
~~~

Đây là **đoạn mã trong một phương thức**, giả định `privateKey`/`publicKey` là cặp khóa phù hợp và `message` là `byte[]`. Kiểm thử này có ích, nhưng **hai phía cùng triển khai sai một cách giống nhau** vẫn có thể ký và xác minh thành công.

Ví dụ: nếu cả signer và verifier cùng dùng nhầm một bước xử lý dữ liệu, kiểm thử round-trip có thể xanh dù **không tương thích RFC 8032 hoặc hệ thống khác**. Vì vậy quy trình tích hợp chữ ký nên có ít nhất ba lớp kiểm thử độc lập:

1. **Known-answer test (KAT):** Với **khóa, message, curve/mode và expected signature cố định do tiêu chuẩn công bố**, chữ ký tạo ra phải **khớp từng byte** với expected signature.
2. **Xác minh vector chuẩn:** Dùng **public key của tiêu chuẩn**, raw message bytes và **signature của tiêu chuẩn** để kiểm tra `Signature.verify(...) == true`; phép kiểm tra này độc lập với việc vừa tự ký.
3. **Negative/tamper tests:** Giữ chữ ký chuẩn nhưng thay đổi **message**, **signature bytes**, **public key**, **context** hoặc format/length; hệ thống phải **không chấp nhận**.

Ngoài ra, cần **integration tests** về bytes được ký, encoding, key provenance, giao thức truyền nhận, cơ chế chống replay và xử lý exception. `verify() == true` chỉ xác nhận chữ ký hợp lệ cho **public key đã chọn và bytes được kiểm tra**; nó **không tự xác thực chủ sở hữu khóa hay sự cho phép của một giao dịch**.

## 2. Phân loại kiểm thử và mục tiêu

| Loại kiểm thử | Dữ liệu đầu vào | Tiêu chí đạt |
| --- | --- | --- |
| **Known-answer signing** | Private seed chuẩn + message chuẩn + mode | `Arrays.equals(actualSignature, expectedSignature) == true` |
| **Known-answer verification** | Public key chuẩn + message chuẩn + signature chuẩn | `Signature.verify(expectedSignature) == true` |
| **Round-trip với khóa mới** | `KeyPairGenerator` tạo cặp khóa, ký và verify | `verify == true`, nhưng **không thay thế KAT** |
| **Message tampering** | Giữ key/signature, sửa 1 byte thông điệp | `verify == false` hoặc từ chối theo hợp đồng |
| **Signature tampering** | Giữ key/message, sửa 1 byte chữ ký | `verify == false` hoặc `SignatureException` do encoding |
| **Truncated signature** | Xóa 1 byte chữ ký chuẩn | **Không chấp nhận**; provider có thể trả false hoặc ném `SignatureException` |
| **Wrong public key** | Giữ signature/message, xác minh bằng public key khác | Không chấp nhận |
| **Wrong curve/mode** | Ed25519 ↔ Ed448; pure ↔ ctx/ph | Không chấp nhận; lỗi khóa/cấu hình có thể ném exception |
| **Context mismatch** | Giữ key/message/signature, đổi context bytes | Không chấp nhận |
| **Serialization mismatch** | Cùng “ý nghĩa” nhưng bytes khác nhau | Không chấp nhận nếu chưa canonicalize theo cùng hợp đồng |
| **Replay / wrong-purpose** | Dùng chữ ký đúng nhưng sai operation/nonce/version | Ứng dụng phải từ chối qua **logic giao thức**, không dựa riêng vào `Signature` |

**Hai nghĩa của “từ chối” cần phân biệt:**

- `Signature.verify(...)` trả **`false`**: đã xử lý yêu cầu xác minh nhưng chữ ký **không hợp lệ** cho dữ liệu/khóa.
- `SignatureException`, `InvalidKeyException`, `InvalidKeySpecException`, `NoSuchAlgorithmException`…: lỗi **format, khóa, cấu hình hoặc provider**. Giao dịch vẫn phải **fail closed**, nhưng hệ thống nên ghi/đo lường loại lỗi phù hợp thay vì đánh đồng tất cả là “tamper”.

Không viết kiểm thử mong mọi chữ ký bị sửa đều **nhất định** cho `false`: một số bytes bị sửa khiến encoding không còn hợp lệ, có thể phát sinh `SignatureException` đúng theo Javadoc.

## 3. Nguồn vector chuẩn: RFC 8032, không lấy từ chính code cần kiểm thử

**RFC 8032 `7** công bố các vector cho **Ed25519**, **Ed25519ctx**, **Ed25519ph**, **Ed448**, **Ed448ph**. Mỗi vector cung cấp:

- **Algorithm/mode**, ví dụ Ed25519 hoặc Ed448.
- **Secret key seed** dạng bytes hex: Ed25519 có 32 bytes; Ed448 có 57 bytes.
- **Public key raw bytes**: Ed25519 32 bytes; Ed448 57 bytes.
- **Message raw bytes**, có thể **rỗng** hoặc có 1 byte/độ dài dài hơn.
- **Context bytes** khi vector có context.
- **Expected signature raw bytes**: Ed25519 64 bytes; Ed448 114 bytes.

Bốn vector dùng trong chương trình mục 6:

| ID vector RFC 8032 | `algorithm` | Message hex | Độ dài seed / public / signature |
| --- | --- | --- | --- |
| `7.1 TEST 1` | Ed25519 | Rỗng, 0 bytes | 32 / 32 / 64 bytes |
| `7.1 TEST 2` | Ed25519 | `72`, 1 byte | 32 / 32 / 64 bytes |
| `7.4 Blank` | Ed448 | Rỗng, 0 bytes | 57 / 57 / 114 bytes |
| `7.4 1 octet` | Ed448 | `03`, 1 byte | 57 / 57 / 114 bytes |

**Lưu ý:** “Message length 0” có nghĩa **một `byte[]` dài 0**, không phải chuỗi văn bản `"0"`, chuỗi chỉ chứa một dấu cách hoặc ký tự xuống dòng. Tương tự, `72` và `03` là **mỗi chuỗi hex biểu diễn một byte**, không phải nội dung văn bản ASCII `"72"` hoặc `"03"`.

### Vì sao vector cố định tốt hơn cặp khóa tạo ngẫu nhiên?

`KeyPairGenerator.generateKeyPair()` cung cấp khóa mới trong mỗi lần chạy; chữ ký ký trên khóa mới không có **expectedSignature** chuẩn để so nguyên văn. Với KAT, các input và expected bytes được **công bố độc lập**, nên phép so khớp không phụ thuộc RNG, không cần lưu lại output ở lần chạy trước.

**Cảnh báo bảo mật:** Các private seeds trong RFC 8032 là **dữ liệu kiểm thử công khai**, không phải khóa bí mật của một ứng dụng. Chỉ dùng trong code test; **không triển khai vào production** để ký giao dịch thật, token hoặc nội dung nhạy cảm.

## 4. Raw bytes, DER và byte order: lỗi tích hợp phổ biến nhất

RFC 8032 cho public key dưới dạng **raw encoded Edwards point**, còn nhiều API Java cho phép lấy key bytes theo **X.509 SubjectPublicKeyInfo** hoặc private key theo **PKCS#8**. Các format không giống nhau:

| Dữ liệu | Thứ được mô tả | Có thể dùng trực tiếp với |
| --- | --- | --- |
| Raw private **seed** của RFC 8032 | Bytes hạt giống Ed25519/Ed448 | `EdECPrivateKeySpec(params, rawSeed)` |
| Raw public key của RFC 8032 | Điểm Edwards được encode thành little-endian y + bit dấu x | Sau khi decode thành `EdECPoint`, dùng `EdECPublicKeySpec` |
| X.509 SubjectPublicKeyInfo DER | ASN.1 wrapper chứa algorithm OID và public key | `KeyFactory.generatePublic(new X509EncodedKeySpec(der))` |
| PKCS#8 DER | ASN.1 wrapper chứa algorithm OID và private key | `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(der))` |
| Raw signature của RFC 8032 | Bytes `R || S` | `Signature.verify(signatureBytes)` |

**Không truyền raw 32-byte Ed25519 public key trực tiếp vào `X509EncodedKeySpec`.** Spec này đòi **DER SubjectPublicKeyInfo**, không phải raw point. Cũng không truyền raw seed trực tiếp vào `PKCS8EncodedKeySpec` rồi mong parser tự đoán format. Java 15+ có **`EdECPrivateKeySpec` và `EdECPublicKeySpec`** để làm việc trực tiếp với thông số khóa EdEC.

### Public key raw EdEC được decode ra sao?

Với Ed25519/Ed448 trong RFC 8032:

1. Byte cuối của public key raw chứa **bit cao** biểu diễn **x là lẻ hay chẵn** (`xOdd`).
2. Phần còn lại encode **tọa độ y ở dạng little-endian**.
3. Bỏ bit dấu của x khỏi byte cuối để lấy y, đảo byte order sang big-endian không dấu cho `BigInteger`.
4. Tạo `new EdECPoint(xOdd, y)`, sau đó `new EdECPublicKeySpec(params, point)` và `KeyFactory.generatePublic(...)`.

Đây là điểm dễ sai nếu dùng `new BigInteger(raw)` trực tiếp: Java `BigInteger` mặc định nhận signed big-endian bytes, không phải unsigned little-endian y. Phải chuyển đổi đúng; nếu không, KAT sẽ phát hiện việc import public key không tương thích.

Trong ứng dụng thực tế, nên dùng key encoding/decoder đáng tin theo giao thức, xác thực **curve, độ dài và format**; không tự tạo parser ASN.1 hoặc decoder điểm nếu thư viện/provider được chọn đã cung cấp API phù hợp. Chương trình bên dưới chỉ triển khai cách chuyển raw public bytes **trong fixture test** dựa trên API chính thức.

## 5. JCA API ổn định cần dùng

| API | Trách nhiệm |
| --- | --- |
| `HexFormat.of().parseHex(...)` | Chuyển vector RFC hex thành **bytes**; API Java 17+ |
| `NamedParameterSpec("Ed25519"/"Ed448")` | Xác định đường cong/tham số của EdEC key |
| `EdECPrivateKeySpec` | Tạo spec khóa riêng từ **raw seed** |
| `EdECPublicKeySpec` + `EdECPoint` | Tạo spec public key từ **encoded Edwards point đã decode** |
| `KeyFactory.getInstance("Ed25519"/"Ed448")` | Tạo key objects từ key specs |
| `Signature.getInstance("Ed25519"/"Ed448")` | Tạo engine JCA ký/xác minh |
| `initSign` / `initVerify` | Chọn private/public key |
| `update(byte[])` | Cấp **đúng bytes message** |
| `sign()` | Tạo raw bytes chữ ký |
| `verify(byte[])` | Xác minh và trả boolean |
| `Arrays.equals(actual, expected)` | So sánh output trong **KAT test** |

`HexFormat` là tiện ích **Java 17+**; bản thân **EdEC/EdDSA** chính thức từ **Java 15**. Dùng `javac --release 17` để minh họa runnable mà không yêu cầu preview.

**Không dùng `Arrays.equals` như phép so sánh bí mật thời gian hằng số trong một protocol bảo mật.** Nó phù hợp để **assert test bytes chữ ký công khai đã biết**; đối với xác minh chữ ký thì phải gọi `Signature.verify`, không chỉ so bằng tay.

## 6. Chương trình đầy đủ: bốn RFC 8032 known-answer vectors

Lưu nguyên chương trình sau thành **Rfc8032VectorDemo.java**. Tất cả private seeds là **khóa test công khai từ RFC**.

~~~java
import java.math.BigInteger;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.EdECPoint;
import java.security.spec.EdECPrivateKeySpec;
import java.security.spec.EdECPublicKeySpec;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import java.util.HexFormat;

public class Rfc8032VectorDemo {
    record Vector(String label, String algorithm, String seed,
                  String publicKey, String message, String expected) {}

    private static final HexFormat HEX = HexFormat.of();

    private static final Vector[] VECTORS = {
        new Vector("Ed25519-empty", "Ed25519",
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
            "",
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            + "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        new Vector("Ed25519-one-byte", "Ed25519",
            "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
            "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
            "72",
            "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
            + "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
        new Vector("Ed448-empty", "Ed448",
            "6c82a562cb808d10d632be89c8513ebf6c929f34ddfa8c9f63c9960ef6e348a3"
            + "528c8a3fcc2f044e39a3fc5b94492f8f032e7549a20098f95b",
            "5fd7449b59b461fd2ce787ec616ad46a1da1342485a70e1f8a0ea75d80e96778"
            + "edf124769b46c7061bd6783df1e50f6cd1fa1abeafe8256180",
            "",
            "533a37f6bbe457251f023c0d88f976ae2dfb504a843e34d2074fd823d41a591f"
            + "2b233f034f628281f2fd7a22ddd47d7828c59bd0a21bfd3980ff0d2028d4b18a"
            + "9df63e006c5d1c2d345b925d8dc00b4104852db99ac5c7cdda8530a113a0f4db"
            + "b61149f05a7363268c71d95808ff2e652600"),
        new Vector("Ed448-one-byte", "Ed448",
            "c4eab05d357007c632f3dbb48489924d552b08fe0c353a0d4a1f00acda2c463a"
            + "fbea67c5e8d2877c5e3bc397a659949ef8021e954e0a12274e",
            "43ba28f430cdff456ae531545f7ecd0ac834a55d9358c0372bfa0c6c6798c086"
            + "6aea01eb00742802b8438ea4cb82169c235160627b4c3a9480",
            "03",
            "26b8f91727bd62897af15e41eb43c377efb9c610d48f2335cb0bd0087810f435"
            + "2541b143c4b981b7e18f62de8ccdf633fc1bf037ab7cd779805e0dbcc0aae1cb"
            + "cee1afb2e027df36bc04dcecbf154336c19f0af7e0a6472905e799f1953d2a0f"
            + "f3348ab21aa4adafd1d234441cf807c03a00")
    };

    static PublicKey importPublic(KeyFactory factory, String algorithm,
                                 byte[] raw) throws Exception {
        int expectedLen = algorithm.equals("Ed25519") ? 32 : 57;
        if (raw.length != expectedLen) {
            throw new IllegalArgumentException(
                    "Unexpected raw public key length");
        }

        byte[] littleEndianY = raw.clone();
        int last = littleEndianY.length - 1;
        boolean xOdd = (littleEndianY[last] & 0x80) != 0;
        littleEndianY[last] &= 0x7f;

        byte[] bigEndianY = new byte[littleEndianY.length];
        for (int i = 0; i < littleEndianY.length; i++) {
            bigEndianY[i] =
                    littleEndianY[littleEndianY.length - 1 - i];
        }
        EdECPoint point = new EdECPoint(
                xOdd, new BigInteger(1, bigEndianY));
        return factory.generatePublic(new EdECPublicKeySpec(
                new NamedParameterSpec(algorithm), point));
    }

    static boolean verifies(String algorithm, PublicKey key,
                            byte[] msg, byte[] sig) throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(key);
        verifier.update(msg);
        return verifier.verify(sig);
    }

    static boolean rejected(String algorithm, PublicKey key,
                            byte[] msg, byte[] sig) throws Exception {
        try {
            return !verifies(algorithm, key, msg, sig);
        } catch (SignatureException invalidSignatureEncoding) {
            return true; // Fail closed in a test; report cause in real systems.
        }
    }

    public static void main(String[] args) throws Exception {
        for (Vector v : VECTORS) {
            KeyFactory factory = KeyFactory.getInstance(v.algorithm());
            NamedParameterSpec params = new NamedParameterSpec(v.algorithm());
            PrivateKey privateKey = factory.generatePrivate(
                    new EdECPrivateKeySpec(params, HEX.parseHex(v.seed())));
            PublicKey publicKey = importPublic(
                    factory, v.algorithm(), HEX.parseHex(v.publicKey()));
            byte[] msg = HEX.parseHex(v.message());
            byte[] expected = HEX.parseHex(v.expected());

            Signature signer = Signature.getInstance(v.algorithm());
            signer.initSign(privateKey);
            signer.update(msg);
            byte[] actual = signer.sign();

            boolean kat = Arrays.equals(actual, expected);
            boolean verify = verifies(v.algorithm(), publicKey, msg, expected);

            byte[] changedMessage = msg.length == 0
                    ? new byte[] {1} : msg.clone();
            if (msg.length != 0) changedMessage[0] ^= 1;

            byte[] modifiedSignature = expected.clone();
            modifiedSignature[0] ^= 1;

            boolean tamperMessageRejected =
                    rejected(v.algorithm(), publicKey,
                            changedMessage, expected);
            boolean tamperSignatureRejected =
                    rejected(v.algorithm(), publicKey,
                            msg, modifiedSignature);
            boolean truncatedSignatureRejected =
                    rejected(v.algorithm(), publicKey,
                            msg, Arrays.copyOf(expected, expected.length - 1));

            System.out.println(v.label() + ": seedBytes="
                    + HEX.parseHex(v.seed()).length
                    + " publicBytes=" + HEX.parseHex(v.publicKey()).length
                    + " messageBytes=" + msg.length
                    + " signatureBytes=" + expected.length);
            System.out.println("katMatches=" + kat);
            System.out.println("knownSignatureVerifies=" + verify);
            System.out.println("modifiedMessageRejected=" + tamperMessageRejected);
            System.out.println("modifiedSignatureRejected="
                    + tamperSignatureRejected);
            System.out.println("truncatedSignatureRejected="
                    + truncatedSignatureRejected);

            if (!kat || !verify || !tamperMessageRejected
                    || !tamperSignatureRejected || !truncatedSignatureRejected) {
                throw new AssertionError("Vector or negative check failed: "
                        + v.label());
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 Rfc8032VectorDemo.java
java Rfc8032VectorDemo
~~~

**Stdout thực tế đã kiểm chứng (JDK có provider EdDSA/Ed25519/Ed448):**

~~~text
Ed25519-empty: seedBytes=32 publicBytes=32 messageBytes=0 signatureBytes=64
katMatches=true
knownSignatureVerifies=true
modifiedMessageRejected=true
modifiedSignatureRejected=true
truncatedSignatureRejected=true
Ed25519-one-byte: seedBytes=32 publicBytes=32 messageBytes=1 signatureBytes=64
katMatches=true
knownSignatureVerifies=true
modifiedMessageRejected=true
modifiedSignatureRejected=true
truncatedSignatureRejected=true
Ed448-empty: seedBytes=57 publicBytes=57 messageBytes=0 signatureBytes=114
katMatches=true
knownSignatureVerifies=true
modifiedMessageRejected=true
modifiedSignatureRejected=true
truncatedSignatureRejected=true
Ed448-one-byte: seedBytes=57 publicBytes=57 messageBytes=1 signatureBytes=114
katMatches=true
knownSignatureVerifies=true
modifiedMessageRejected=true
modifiedSignatureRejected=true
truncatedSignatureRejected=true
~~~

## 7. Giải thích chương trình: vì sao là KAT thực sự?

### 7.1. Import khóa RFC thay vì tạo khóa ngẫu nhiên

~~~java
PrivateKey privateKey = factory.generatePrivate(
        new EdECPrivateKeySpec(params, HEX.parseHex(v.seed())));

PublicKey publicKey = importPublic(
        factory, v.algorithm(), HEX.parseHex(v.publicKey()));
~~~

`EdECPrivateKeySpec` nhận **raw seed** của RFC; `EdECPublicKeySpec` nhận **điểm public** đã decode từ raw RFC bytes. Hai khóa đến từ **fixture chuẩn**, không phải một `KeyPairGenerator` vừa tạo cặp ngẫu nhiên.

Nếu vô tình tạo một private key khác nhưng vẫn dùng public vector, chữ ký do signer tạo sẽ **không** khớp expected. Nếu import sai raw public point, `verify` với expected signature cũng thất bại hoặc key construction báo lỗi.

### 7.2. Hai assertion quan trọng không trùng nhau

~~~java
boolean kat = Arrays.equals(actual, expected);
boolean verify = verifies(v.algorithm(), publicKey, msg, expected);
~~~

- **`kat`:** engine ký Java tạo **chính xác** chữ ký mà RFC công bố cho cùng seed + message + algorithm/mode.
- **`verify`:** engine xác minh Java chấp nhận **chữ ký độc lập được RFC công bố**, không dùng lại `actual` vừa tự ký.

**Nếu chỉ dùng `verifies(public, msg, actual)` thì chưa đủ** để phát hiện trường hợp cả hai phía của cùng implementation tuân theo cùng một quy tắc sai. Hai assertion giúp tăng chất lượng kiểm thử liên thông.

### 7.3. Sửa message và signature có mục đích

~~~java
byte[] changedMessage = msg.length == 0
        ? new byte[] {1} : msg.clone();
if (msg.length != 0) changedMessage[0] ^= 1;

byte[] modifiedSignature = expected.clone();
modifiedSignature[0] ^= 1;
~~~

Thay đổi message rỗng thành **một byte 0x01**, hoặc đổi một bit của byte đầu với message không rỗng, đảm bảo input kiểm thử **thực sự khác**. Nếu test chỉ viết `changedMessage = msg` rồi sửa trực tiếp, có thể **vô tình sửa luôn fixture gốc**, khiến kết quả mất giá trị. `clone()` giữ input gốc nguyên vẹn.

Trong negative signature test, thay đổi một bit của chữ ký có thể khiến chữ ký sai toán học hoặc bytes không còn biểu diễn điểm hợp lệ. `rejected` bắt riêng `SignatureException` để coi đây là **không chấp nhận chữ ký**, nhưng trong hệ thống thật nên **phân biệt kết quả `false` với exception do encoding hoặc provider** trong telemetry. Chỉ bắt `SignatureException`, **không nuốt mọi `Exception`** rồi cho rằng kiểm thử pass.

### 7.4. Chữ ký bị cắt ngắn và yêu cầu fail-closed

~~~java
Arrays.copyOf(expected, expected.length - 1)
~~~

biến chữ ký Ed25519 64 bytes thành 63 bytes, hoặc Ed448 114 thành 113. Một chữ ký như vậy **không thể được chấp nhận là chữ ký chuẩn hoàn chỉnh** cho vector đang thử. Provider có thể từ chối bằng `false` hoặc bằng `SignatureException` cho cấu trúc không hợp lệ.

**Không kiểm tra negative test chỉ bằng `throws SignatureException`**, vì nhiều provider có thể xử lý việc bytes không khớp bằng cách trả `false` mà vẫn tuân theo hợp đồng. Điều phải thống nhất là **không chấp nhận một chữ ký sai**, đồng thời giữ thông tin nguyên nhân nếu cần vận hành.

## 8. Message là bytes: Unicode và serialization có thể thay đổi chữ ký

Một lỗi tích hợp rất phổ biến: phía ký và phía nhận nghĩ họ dùng “cùng thông điệp”, nhưng thực tế **hai dãy bytes khác nhau**.

Ví dụ hai biểu diễn hiển thị tương tự của chữ **é**:

~~~java
String composed = "\u00e9";   // U+00E9
String decomposed = "e\u0301"; // U+0065 + U+0301

byte[] a = composed.getBytes(StandardCharsets.UTF_8);
byte[] b = decomposed.getBytes(StandardCharsets.UTF_8);

// a và b là hai dãy bytes khác nhau.
~~~

Theo UTF-8, `a` là `C3 A9`, còn `b` là `65 CC 81`. **Ký `a` rồi verify `b` phải thất bại** với cùng key/signature, dù nhiều font hiển thị chúng rất giống nhau.

Nếu giao thức **đã định nghĩa** chuẩn hóa Unicode NFC, cả bên ký và bên xác minh cần thực hiện **cùng** thao tác trước khi chuyển chuỗi sang UTF-8:

~~~java
String canonical = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);

byte[] canonicalBytes = canonical.getBytes(StandardCharsets.UTF_8);
~~~

**Không tùy tiện normalize dữ liệu đã ký sau khi nhận** nếu protocol yêu cầu ký **raw payload bytes**. Chỉ canonicalize khi **đó là hợp đồng của giao thức** đã được mọi thành phần chấp thuận. Tự sửa bytes trước khi verify có thể làm thay đổi ý nghĩa việc xác minh: chữ ký có thể xác thực một representation khác với dữ liệu gốc được truyền.

Các khác biệt khác cần đưa vào integration test:

- JSON object có **thứ tự key khác** dù cùng dữ liệu logic.
- Khoảng trắng, xuống dòng `LF` vs `CRLF`, BOM UTF-8.
- Encoding `UTF-8` so với UTF-16, hoặc mặc định nền tảng.
- `BigDecimal`/số có biểu diễn `1.0` khác `1`, timestamp hoặc timezone khác.
- Header/prefix có/không có `content-type`, phiên bản hoặc đường dẫn API.
- Binary serialization thay đổi field order/default values hoặc unknown fields.
- Khác biệt canonicalization giữa các thư viện và phiên bản giao thức.

**Quy tắc:** Định nghĩa **message-to-bytes contract**, test trực tiếp bytes hoặc digest của bytes trong môi trường kiểm thử, rồi mới kiểm tra chữ ký. `Signature.update(...)` chỉ làm việc trên **bytes**, không hiểu cấu trúc JSON, Unicode hay nghiệp vụ.

## 9. Chương trình tích hợp thứ hai: thử Unicode, sai khóa và context

Tạo **SignatureIntegrationDemo.java**. Chương trình dùng cặp khóa mới cho mỗi lần chạy để chứng minh **negative tests vẫn cần thiết ngoài các KAT cố định**. Chữ ký biến đổi theo key nên chương trình in các **boolean ổn định**, không in signature cụ thể.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.EdDSAParameterSpec;
import java.security.spec.NamedParameterSpec;
import java.text.Normalizer;
import java.util.Arrays;

public class SignatureIntegrationDemo {
    static byte[] utf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    static byte[] sign(KeyPair pair, byte[] data) throws Exception {
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(data);
        return signer.sign();
    }

    static boolean verify(PublicKey key, byte[] data, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    static byte[] signInContext(KeyPair pair, byte[] data, byte[] context)
            throws Exception {
        Signature signer = Signature.getInstance("EdDSA");
        signer.setParameter(new EdDSAParameterSpec(false, context));
        signer.initSign(pair.getPrivate());
        signer.update(data);
        return signer.sign();
    }

    static boolean verifyInContext(PublicKey key, byte[] data,
                                  byte[] signature, byte[] context)
            throws Exception {
        Signature verifier = Signature.getInstance("EdDSA");
        verifier.setParameter(new EdDSAParameterSpec(false, context));
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
        generator.initialize(NamedParameterSpec.ED25519);
        KeyPair first = generator.generateKeyPair();
        KeyPair second = generator.generateKeyPair();

        String composed = "\u00e9";
        String decomposed = "e\u0301";
        byte[] signedBytes = utf8(composed);
        byte[] differentBytes = utf8(decomposed);
        byte[] signature = sign(first, signedBytes);
        byte[] mutatedSignature = signature.clone();
        mutatedSignature[0] ^= 1;

        System.out.println("utf8BytesDifferent="
                + !Arrays.equals(signedBytes, differentBytes));
        System.out.println("originalPasses="
                + verify(first.getPublic(), signedBytes, signature));
        System.out.println("decomposedFails="
                + !verify(first.getPublic(), differentBytes, signature));
        System.out.println("normalizeThenPasses="
                + verify(first.getPublic(),
                    utf8(Normalizer.normalize(decomposed, Normalizer.Form.NFC)),
                    signature));
        System.out.println("wrongKeyFails="
                + !verify(second.getPublic(), signedBytes, signature));

        try {
            boolean accepted =
                    verify(first.getPublic(), signedBytes, mutatedSignature);
            System.out.println("changedSignatureRejected=" + !accepted);
        } catch (SignatureException invalidEncoding) {
            System.out.println("changedSignatureRejected=true");
        }

        byte[] contextA = utf8("orders-v1");
        byte[] contextB = utf8("refunds-v1");
        byte[] contextSig = signInContext(first, signedBytes, contextA);
        System.out.println("contextPasses="
                + verifyInContext(first.getPublic(),
                    signedBytes, contextSig, contextA));
        System.out.println("otherContextFails="
                + !verifyInContext(first.getPublic(),
                    signedBytes, contextSig, contextB));

        byte[] domainA = utf8("orders-v1|invoice:42");
        byte[] domainB = utf8("refunds-v1|invoice:42");
        byte[] domainSignature = sign(first, domainA);
        System.out.println("domainSeparated="
                + !verify(first.getPublic(), domainB, domainSignature));
        System.out.println("signatureBytes=" + signature.length);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 SignatureIntegrationDemo.java
java SignatureIntegrationDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
utf8BytesDifferent=true
originalPasses=true
decomposedFails=true
normalizeThenPasses=true
wrongKeyFails=true
changedSignatureRejected=true
contextPasses=true
otherContextFails=true
domainSeparated=true
signatureBytes=64
~~~

### Ba điểm diễn giải quan trọng

**Một — bytes khác nhau thì chữ ký không hợp lệ.** `decomposedFails=true` không chỉ là kiểm tra có dấu tiếng Việt; nó minh họa **chữ ký bảo vệ chính dãy bytes**, không tự nhận “hai chuỗi gần giống nhau” là tương đương.

**Hai — verify đúng chữ ký không tự tin cậy key.** `wrongKeyFails=true` chứng minh key A không thay bằng key B. Nhưng trong production, hệ thống phải ràng buộc public key với một danh tính/quyền đã được tin cậy (certificate, key registry, JWKS, KMS metadata hoặc một trust model tương đương). **Dùng public key do chính attacker gửi** để verify chữ ký của attacker không chứng minh attacker có quyền thực hiện giao dịch.

**Ba — context là thành phần giao thức.** `EdDSAParameterSpec(false, contextA)` cấu hình mode có context; `contextPasses=true` và `otherContextFails=true` cho thấy bên nhận phải dùng **chính xác context bytes**. `domainSeparated=true` minh họa cách khác: đưa **domain/version/purpose** vào **message bytes đã ký**. Hai cơ chế không đồng nhất, và phải thống nhất loại nào được protocol sử dụng.

## 10. Context và prehash: không dùng nhầm vector

RFC 8032 có nhiều bộ vector:

| Tên | Chế độ | Điều khác biệt |
| --- | --- | --- |
| **Ed25519** | Pure Ed25519 | Không có context và không prehash |
| **Ed25519ctx** | Context Ed25519 | Context được đưa vào domain separation |
| **Ed25519ph** | Prehash Ed25519 | Có bước prehash theo RFC và context tùy chọn |
| **Ed448** | Pure Ed448 | Không prehash; cách domain separation do Ed448 quy định |
| **Ed448ph** | Prehash Ed448 | Mode prehash riêng |

Trong JCA Java 15+, có `EdDSAParameterSpec`:

~~~java
byte[] context = "orders-v1".getBytes(StandardCharsets.US_ASCII);
Signature signer = Signature.getInstance("EdDSA");
signer.setParameter(new EdDSAParameterSpec(false, context));
signer.initSign(privateKey);
signer.update(messageBytes);
byte[] signature = signer.sign();
~~~

Đây là **code trong method** có `privateKey`/`messageBytes` phù hợp và import các classes cần thiết. `false` có nghĩa **không prehash**. Context tối đa **255 bytes**, không phải 255 Unicode characters.

**Không dùng vector Ed25519ctx để kiểm tra pure Ed25519**, hoặc vector Ed25519ph khi code chỉ dùng `Signature.getInstance("Ed25519")` mà không cấu hình mode. Nếu vector có context, test phải truyền **đúng context bytes**, ví dụ RFC ghi `666f6f` nghĩa là ASCII `"foo"`. **Context khác một byte** phải làm chữ ký không khớp.

**Không tự làm `SHA-512(message)` rồi coi đó là Ed25519ph.** Việc prehash theo RFC ảnh hưởng đến domain separation và cách ký, không chỉ là “hash trước rồi chạy pure Ed25519 trên digest”. Dùng mode chính thức từ JCA/provider, và kiểm thử với vector của chính mode đó.

## 11. Các trường hợp sai khóa và sai thuật toán

Những negative cases quan trọng khác:

### Sai public key

Giữ message và signature của key A nhưng dùng public key B **cùng curve**. Lúc này key object có thể hợp lệ về mặt cấu trúc, nên `Signature.initVerify(B)` thành công nhưng `verify(signatureA)` trả **`false`**. Đây là kết quả mật mã không khớp, không nhất thiết là exception.

### Sai curve (Ed25519 so với Ed448)

Nếu `Signature.getInstance("Ed25519")` nhận public key Ed448 ở `initVerify`, provider thường từ chối bằng **`InvalidKeyException`** vì key không đúng thuật toán. KAT Ed448 phải dùng `Signature("Ed448")` hoặc `Signature("EdDSA")` được cấu hình/khớp đúng tham số.

### Sai algorithm/mode

Một chữ ký tạo bằng `Ed25519ctx` không được xem là chữ ký pure Ed25519 chỉ vì cùng 64-byte signature length và cùng public key. Điều kiện xác minh không chỉ gồm kích thước, mà gồm **curve, mode, context, message bytes và key**.

### Khóa DER bị hỏng

Nếu hệ thống nhập khóa qua `KeyFactory.generatePublic(new X509EncodedKeySpec(der))` hoặc `generatePrivate(new PKCS8EncodedKeySpec(der))`, DER sai cấu trúc hoặc OID không tương thích có thể gây **`InvalidKeySpecException`**. Không đi vào `Signature.verify` rồi giả định đó chỉ là một negative signature case. Kiểm tra key format riêng.

**Tách hai lớp xác nhận:** Khóa được parser chấp nhận **không** chứng minh khóa đó là *trusted key*. Sau khi import, vẫn phải xác định **ai sở hữu và được phép sử dụng khóa**.

## 12. Thiết kế ma trận thử nghiệm dữ liệu bị sửa

Một ma trận thực dụng cho **mỗi curve/mode**:

| Nhóm | Tác động lên input gốc | Tiêu chí dự kiến |
| --- | --- | --- |
| Baseline | Không sửa bất cứ byte nào | Verify true |
| Message first byte | XOR bit `0x01` ở byte đầu | Verify false |
| Message last byte | XOR bit `0x01` ở byte cuối | Verify false |
| Empty/nonempty | Empty → `{0x01}` hoặc ngược lại | Verify false |
| Signature first byte | XOR bit `0x01` trong signature | False hoặc SignatureException |
| Signature last byte | XOR bit trong signature | False hoặc SignatureException |
| Truncated signature | Bỏ 1 byte | False hoặc SignatureException |
| Appended signature | Thêm 1 byte | Không chấp nhận |
| Wrong public key | Dùng key khác cùng curve | Verify false |
| Wrong curve | Dùng Ed448 key với verifier Ed25519 | InvalidKeyException hoặc từ chối |
| Wrong context | Thay một byte context | Verify false |
| Wrong prehash mode | Pure so với ph | Không chấp nhận |
| Encoding difference | NFC so với decomposed, LF so với CRLF | Verify false nếu bytes khác |
| Wrong domain | `orders` so với `refunds` | Verify false nếu domain là bytes đã ký |
| Replay | Dùng lại message+signature hợp lệ ở giao dịch khác | **Protocol layer** phải từ chối, không trông đợi `Signature.verify` false |

**Không khẳng định toán học rằng thay bit nào cũng luôn chỉ tạo ra signature sai mà không có lỗi encoding.** Đây là lý do tiêu chí “không chấp nhận” được dùng cho signature tampering, còn nhóm message mutation với bytes hợp lệ thường kỳ vọng `verify=false`.

Trong test code, **copy fixture trước khi sửa**, đối chiếu length và xác nhận mutation thực sự tạo bytes khác. Nếu không, test có thể cho kết quả sai do aliasing hoặc vô tình sửa original.

## 13. Đừng kiểm thử chỉ bằng độ dài chữ ký

Ed25519 signature dài 64 bytes và Ed448 signature dài 114 bytes trong các mode chuẩn. Nhưng **đúng độ dài không có nghĩa hợp lệ**:

- Attacker có thể đưa 64 bytes ngẫu nhiên; độ dài đủ nhưng không qua `Signature.verify`.
- Chữ ký đúng curve nhưng sai message vẫn thất bại.
- Chữ ký đúng key/message nhưng sai context/mode vẫn thất bại.
- Chữ ký bị sửa 1 byte có thể vẫn đúng độ dài, nhưng không hợp lệ.
- Một chữ ký cũ có thể hoàn toàn hợp lệ cho message cũ — **replay defense không nằm trong `Signature`**.

Kiểm tra length từ đầu để tiết kiệm tài nguyên và tạo thông báo format phù hợp **có thể hữu ích**, nhưng không được thay phép xác minh mật mã. Nếu hệ thống hỗ trợ nhiều scheme, không dùng chỉ độ dài để đoán algorithm; **algorithm ID và key ID phải được ràng buộc bởi giao thức tin cậy**.

## 14. Kiểm thử được lặp lại và môi trường chạy

### Java version

Các API `EdECPrivateKeySpec`, `EdECPublicKeySpec`, `EdECPoint`, `NamedParameterSpec.ED25519/ED448` và `EdDSAParameterSpec` đã là phần ổn định trong Java hiện đại. `HexFormat` và `record` dùng trong ví dụ là API/ngôn ngữ ổn định với target **Java 17**, vì vậy chạy:

~~~bash
javac --release 17 -encoding UTF-8 Rfc8032VectorDemo.java
java Rfc8032VectorDemo
~~~

**Không cần preview**. Với môi trường Java thấp hơn 17, có thể thay `HexFormat` bằng decoder hex tự viết đã kiểm thử và `record` bằng class thường; đây là **điều chỉnh mã demo**, không phải vì EdDSA trở nên legacy.

### Provider

JCA là kiến trúc provider-based: `Signature.getInstance("Ed25519")` hoặc `KeyFactory.getInstance("Ed448")` có thể ném `NoSuchAlgorithmException` nếu runtime/provider chưa hỗ trợ. Khi chạy CI, nên kiểm tra rõ **JDK version, provider, policy** và **không âm thầm fallback sang thuật toán không tương đương**.

### Thứ tự chạy test

Nên có hai nhóm:

1. **Unit/KAT test** nhanh và xác định: cùng vectors, không phụ thuộc mạng, không dùng khóa production, pass/fail rõ.
2. **Integration/interoperability test**: chạy với provider thực, định dạng khóa/serialized bytes và bên đối tác (hoặc implementation độc lập), có môi trường fixture quản lý.

Nếu thay đổi provider/JDK, chạy lại **cả KAT và negative matrix**. Kiểm thử chỉ `sign+verify` trên một provider chưa đủ để đảm bảo liên thông giữa hai bên.

### Test log

Có thể log **vector ID, algorithm, JDK/provider, expected/actual equality, outcome, exception type**, nhưng tránh log private key, seed hoặc private DER. Riêng **RFC public test seeds** được công bố rộng rãi vẫn nên giữ trong **test fixtures**, không trộn với cấu hình prod hoặc log keys thật.

## 15. Xử lý lỗi theo nguyên tắc fail-closed

Một hàm xác minh ở ranh giới API có thể tách kết quả:

~~~java
public enum VerificationStatus {
    VALID,
    INVALID_SIGNATURE,
    MALFORMED_SIGNATURE,
    INVALID_KEY,
    CRYPTO_UNAVAILABLE
}
~~~

Đây là **mã minh họa một enum**, không phải kết quả đầy đủ của chương trình và không bao hàm mọi loại exception. Tùy thiết kế, có thể ánh xạ:

- `verify(...) == true` → chữ ký hợp lệ về mặt toán học (vẫn cần authorization/trust checks).
- `verify(...) == false` → INVALID_SIGNATURE.
- `SignatureException` do chữ ký sai cấu trúc → MALFORMED_SIGNATURE.
- `InvalidKeyException` → INVALID_KEY.
- `NoSuchAlgorithmException` hoặc provider/configuration failure → CRYPTO_UNAVAILABLE.
- `InvalidKeySpecException` khi parse khóa → lỗi import/format khóa, không phải một chữ ký đã được verify và sai.

**Fail-closed nghĩa là:** chỉ chấp nhận khi mọi bước bắt buộc thành công, gồm parse, algorithm/key trust policy, signature verify, kiểm tra context/version/replay. Nhưng **không bắt mọi `Exception` rồi trả kết quả hợp lệ**, cũng không dùng exception như một cách xác minh thành công.

Với input do bên ngoài gửi, nên giới hạn kích thước dữ liệu, xác định tối đa signature/key format, xử lý malformed payload và log an toàn; tránh trả cho attacker những chi tiết có thể gây lộ thông tin nội bộ không cần thiết.

## 16. Sai lầm dễ mắc khi dùng vector chuẩn

1. **Dùng chữ ký vừa tự tạo làm expected signature.** Đây chỉ là round-trip, không phải known-answer test độc lập.
2. **Dùng `KeyPairGenerator` tạo private key thay vì seed công bố.** Chữ ký khác vector và phép so byte không có ý nghĩa.
3. **Nhập raw public point vào `X509EncodedKeySpec`.** Sai format; public vector RFC là raw Edwards point, không phải SubjectPublicKeyInfo DER.
4. **Nhập raw seed vào `PKCS8EncodedKeySpec`.** Sai format; dùng `EdECPrivateKeySpec` hoặc PKCS#8 DER hợp lệ.
5. **Decode raw public key bằng `BigInteger(raw)`.** Sai signedness/endian/sign bit; phải xử lý theo RFC.
6. **Nhầm empty message với `new byte[]{0}`.** Một thông điệp dài 0 khác một thông điệp chứa byte 0x00.
7. **Nhầm hex `"72"` với bytes UTF-8 của hai ký tự `7` và `2`.** RFC `72` là một byte 0x72.
8. **Nhầm Ed25519 với Ed25519ctx/Ed25519ph.** Context/prehash là thành phần của mode, không tự tương đương.
9. **Nhầm Ed448 với X448.** Ed448 là chữ ký EdDSA; X448 là thỏa thuận khóa XDH.
10. **Chỉ assert verify thành công, không làm negative tests.** Có thể bỏ sót tamper, wrong key, wrong context hoặc parser fail-open.
11. **Với signature tampering, chỉ chấp nhận case ném exception.** Provider cũng có thể trả false hợp lệ; quan trọng là không chấp nhận.
12. **Bắt `Exception` quá rộng rồi cho rằng test pass.** Có thể che giấu lỗi không có thuật toán/provider hoặc sai thiết lập test.
13. **Thay đổi fixture gốc vì dùng alias `changed = original`.** Dùng `clone()`/copy trước khi sửa.
14. **Cho rằng `verify=true` chứng minh thông điệp không bị replay.** Chữ ký cũ cho message cũ vẫn xác minh đúng; phải kiểm tra nonce/sequence/timestamp theo giao thức.
15. **Bỏ qua Unicode normalization và serialization.** Hai JSON/chuỗi “giống nhau” có thể được encode ra bytes khác.
16. **Cho rằng public key hợp lệ bằng chứng danh tính.** Phải ràng buộc key với trusted identity/authorization.
17. **Dùng RFC test private seeds trong production.** Các seeds ấy là dữ liệu công khai; sử dụng làm khóa thật sẽ làm lộ quyền ký.
18. **So sánh lengths thay vì cryptographic verify.** Độ dài đúng không tạo ra chữ ký hợp lệ.
19. **Dùng KAT Ed25519 nhưng production dùng Ed448.** Mỗi curve/mode cần vectors và tests riêng.
20. **Không phân biệt verification false với exception.** Quan trọng cho vận hành và kiểm tra việc fail closed đúng cách.

## 17. Checklist cho pipeline CI/CD về chữ ký

| Câu hỏi | Yêu cầu kiểm tra |
| --- | --- |
| Chữ ký chạy đúng RFC đã chọn? | KAT ký **expected signature bytes** và verify **RFC signature** |
| Có đủ Ed25519 và Ed448 nếu hệ thống hỗ trợ cả hai? | Chạy vectors tương ứng từng thuật toán |
| Có nhiều độ dài input? | Ít nhất empty và nonempty, thêm dữ liệu lớn theo nhu cầu |
| Các bytes đến từ đúng encoding? | Hex decode đúng; UTF-8/serialization theo spec |
| Mọi negative cases bị từ chối? | Tampered message/signature, truncated, wrong key/context/algorithm |
| Có phụ thuộc provider không? | Ghi JDK/provider được hỗ trợ, test trên môi trường triển khai |
| Có ràng buộc public key trust không? | Authenticated key registry/certificate/key id hoặc trust model rõ ràng |
| Signature mode/context khớp không? | Tests cho pure/ctx/ph tùy protocol |
| Có dữ liệu nhiều ngôn ngữ không? | Test NFC/NFD, newline, BOM, JSON canonicalization nếu cần |
| Có chống replay ở protocol không? | Nonce/timestamp/sequence/idempotency policy |
| Có trộn khóa test và khóa production? | Ngăn test seeds đi vào cấu hình production |
| Có báo lỗi hữu ích mà không rò key? | Log vector ID/outcome/exception type, không log secret |
| Đổi JDK/provider có bắt buộc test lại? | Chạy KAT + integration/negative regression |
| Có so sánh với implementation độc lập? | Cross-provider/cross-language interoperability tests |

## 18. Bài luyện tập và tiêu chí đạt

**Bài 1 — Hiểu vector RFC.** Giải thích `Ed25519 TEST 1` với message rỗng và `TEST 2` với message `72`. **Đạt** khi phân biệt 0-byte message với một byte 0x72, biết signature Ed25519 dài 64 bytes.

**Bài 2 — KAT ký.** Dùng `EdECPrivateKeySpec` từ seed công khai, ký bằng `Signature("Ed25519")`. **Đạt** khi `Arrays.equals(actual, expected) == true` cho TEST 1 và TEST 2.

**Bài 3 — KAT verify độc lập.** Import raw public key qua `EdECPublicKeySpec`, kiểm tra chữ ký **của RFC**, không dùng chữ ký vừa tạo. **Đạt** khi `verify == true` cho cả hai Ed25519 vectors.

**Bài 4 — Ed448.** Chạy vector Ed448 Blank và 1 octet. **Đạt** khi thấy 57-byte private seed/public key, 114-byte signatures, cả KAT và verify đều pass.

**Bài 5 — Mutation.** Giữ expected signature của vector nhưng sửa 1 byte message, sửa 1 bit signature, cắt 1 byte signature. **Đạt** khi mọi trường hợp không được chấp nhận; hiểu `false` và `SignatureException` khác nhau.

**Bài 6 — Key mismatch.** Với chữ ký của key A, dùng public key B cùng curve. **Đạt** khi verify không chấp nhận, đồng thời giải thích một public key do attacker tự cung cấp không chứng minh danh tính.

**Bài 7 — Unicode.** Ký `"\u00e9"` rồi verify `"e\u0301"`. **Đạt** khi không khớp trước khi có canonicalization được protocol xác định, và khớp sau khi chuẩn hóa NFC ở cả hai phía.

**Bài 8 — Context.** Ký với EdDSA context `orders-v1` và xác minh với `refunds-v1`. **Đạt** khi context đúng cho true, context sai cho false; không nhầm context với việc nối một prefix vào message.

**Bài 9 — Raw vs DER.** Phân biệt `EdECPrivateKeySpec`/`EdECPublicKeySpec` với `PKCS8EncodedKeySpec`/`X509EncodedKeySpec`. **Đạt** khi biết raw 32/57 bytes không phải PKCS#8/X.509 DER.

**Bài 10 — JSON API.** Ký một object có keys `a` và `b`, thay thứ tự keys, whitespace hoặc số format. **Đạt** khi biết cần xác định **serialized bytes contract** hoặc canonicalization trước khi assert verify.

**Bài 11 — Fail-closed.** Mô tả cách API trả lỗi riêng cho false, malformed signature và provider unavailable. **Đạt** khi không biến các trường hợp lỗi thành authorization success.

**Bài 12 — Replay.** Dùng lại một chữ ký hợp lệ cho request cũ. **Đạt** khi giải thích tại sao `Signature.verify` vẫn có thể true nhưng protocol phải kiểm tra nonce/sequence/timestamp để từ chối request trùng.

## 19. Tài liệu chính thức và còn hiệu lực

- [RFC 8032 — `7 Test Vectors for Ed25519 and Ed448](https://www.rfc-editor.org/rfc/rfc8032.html#section-7): nguồn **public known-answer vectors**, bao gồm `7.1` và `7.4` được dùng nguyên giá trị trong bài.
- [RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, X448](https://www.rfc-editor.org/rfc/rfc8410.html): phân biệt raw key với định dạng key X.509/PKCS#8, OID và encoding.
- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA), JDK 15](https://openjdk.org/jeps/339): hỗ trợ Ed25519/Ed448 trong JCA.
- [Oracle Java SE 25 — Signature](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html): `initSign`, `initVerify`, `update`, `sign`, `verify`, phân biệt false và exceptions.
- [Oracle Java SE 25 — EdECPrivateKeySpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html) và [EdECPublicKeySpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPublicKeySpec.html): mô hình key specs cho raw EdEC keys.
- [Oracle Java SE 25 — EdECPoint](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPoint.html): tọa độ y và thông tin parity của x.
- [Oracle Java SE 25 — NamedParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/NamedParameterSpec.html) và [EdDSAParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): lựa chọn curve, context và prehash mode.
- [Oracle Java SE 25 — KeyFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyFactory.html): import/export theo key spec.
- [Oracle Java SE 25 — HexFormat](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HexFormat.html): hex decoding trong ví dụ Java 17+.

**Ghi nhớ:** Một hệ thống ký số đáng tin phải chứng minh **(1) tạo chữ ký đúng vector chuẩn độc lập**, **(2) xác minh đúng chữ ký chuẩn**, và **(3) từ chối các thay đổi message, signature, key, context và protocol bytes**. KAT bảo vệ tính đúng đắn của thuật toán; negative tests bảo vệ hành vi từ chối; trust/authorization/replay checks bảo vệ **ý nghĩa nghiệp vụ**. Không dùng seed công khai của RFC làm khóa thật, và luôn xác định **đúng bytes được ký**.
