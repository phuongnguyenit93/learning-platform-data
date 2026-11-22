# Java 15 — Phân biệt byte khóa thô với định dạng chứa khóa EdEC

## 1. Mục tiêu bài học và sai lầm cần tránh

Trong Java 15+, các khóa chữ ký số **Ed25519** và **Ed448** thuộc họ **EdEC** (Edwards-Curve). Khi trao đổi hoặc lưu trữ khóa, một lỗi phổ biến là nhìn thấy một mảng byte rồi cho rằng nó có thể dùng ở mọi API. Thực tế cần phân biệt:

1. **Raw public key**: bytes biểu diễn **điểm công khai** theo RFC 8032, không tự kèm tên thuật toán, cấu trúc ASN.1 hay metadata.
2. **Raw private key/seed**: bytes bí mật dùng làm input cho quá trình suy ra khóa và ký EdDSA, không phải public key cũng không phải cấu trúc PKCS#8.
3. **X.509 SubjectPublicKeyInfo (SPKI) DER**: **cấu trúc chứa public key**, bao gồm thông tin thuật toán và giá trị public key.
4. **PKCS#8 PrivateKeyInfo DER** (hoặc cấu trúc `OneAsymmetricKey` liên quan): **cấu trúc chứa private key** và thông tin thuật toán.
5. **PEM**: một cách biểu diễn **Base64 + nhãn mở/đóng**, thường bọc SPKI DER hoặc PKCS#8 DER, **không biến dữ liệu thành dạng raw**.

Các lớp EdEC, EdDSA và `NamedParameterSpec.ED25519`/`ED448` là API chính thức được giới thiệu từ Java 15 (JEP 339) và **vẫn dùng được trên JDK hiện đại**. Đây là trọng tâm bài, không dùng API cũ đã bị loại bỏ.

Sau bài này, bạn sẽ biết vì sao **32 byte Ed25519 raw public key không thể đưa thẳng vào `new X509EncodedKeySpec(...)`**, vì sao `privateKey.getEncoded()` không giống `EdECPrivateKey.getBytes()`, và cách import/export an toàn qua `KeyFactory` với đúng loại `KeySpec`.

## 2. Bảng so sánh những biểu diễn thường gặp

| Kiểu dữ liệu | Nội dung | Ed25519 | Ed448 | Java API phù hợp |
| --- | --- | ---: | ---: | --- |
| Raw public key RFC 8032 | Điểm công khai nén: tọa độ `y` little-endian và một bit cho dấu/parity `x` | **32 byte** | **57 byte** | `EdECPublicKey.getPoint()`, `EdECPoint`, `EdECPublicKeySpec` |
| Raw private key / seed RFC 8032 | Byte bí mật để thuật toán suy ra scalar và khóa công khai | **32 byte** | **57 byte** | `EdECPrivateKey.getBytes()` (nếu xuất được), `EdECPrivateKeySpec` |
| SPKI DER (`X.509` trong Java) | ASN.1 DER: AlgorithmIdentifier + BIT STRING chứa raw public key | **Lớn hơn raw** | **Lớn hơn raw** | `PublicKey.getEncoded()`, `X509EncodedKeySpec` |
| PKCS#8 DER (`PKCS#8` trong Java) | ASN.1 DER: version + thuật toán + OCTET STRING chứa khóa bí mật | **Lớn hơn raw** | **Lớn hơn raw** | `PrivateKey.getEncoded()`, `PKCS8EncodedKeySpec` |
| PEM `PUBLIC KEY` / `PRIVATE KEY` | Base64 của DER với header/footer dạng text | Phụ thuộc độ dài DER | Phụ thuộc độ dài DER | `Base64` + `KeyFactory` / `KeySpec` |
| Certificate X.509 DER/PEM | Chứng chỉ: subject, issuer, validity, signature, SPKI... | Không phải chỉ public key | Không phải chỉ public key | `CertificateFactory`, rồi `getPublicKey()` |

**Quan trọng:** những con số 32/57 byte là kích thước **raw** theo RFC 8032; độ dài của DER phụ thuộc cấu trúc và cách encoding. Với provider tích hợp trong JDK được kiểm thử ở bài, Ed25519 có SPKI **44 byte**, PKCS#8 **48 byte**; Ed448 có SPKI **69 byte**, PKCS#8 **73 byte**. **Không** dùng các con số DER đó để viết parser “bỏ 12 hoặc 16 byte đầu”. Chúng là output quan sát của một provider/encoding cụ thể, không phải lý do để bỏ qua ASN.1.

### 2.1. “Key” không đồng nghĩa “mảng byte”

Một object `java.security.Key` gồm thông tin thuật toán, phương thức `getFormat()` và cách xuất dữ liệu bằng `getEncoded()` **nếu provider cho phép**. Một object khóa do HSM/provider bảo vệ có thể không cho xuất:

- `getEncoded() == null` nếu khóa không hỗ trợ export sang định dạng byte tiêu chuẩn;
- `getFormat() == null` nếu không có format xuất được;
- `EdECPrivateKey.getBytes()` trả `Optional.empty()` nếu implementation không cho lấy raw private bytes.

Không phải cứ object có thể ký là phải được phép trích xuất seed bí mật. **Không** “khắc phục” bằng cách log, reflection hoặc chuyển khóa sang provider khác để buộc xuất secret.

## 3. Raw public key: không có ASN.1, chỉ có điểm công khai

Theo **RFC 8032**, public key của Ed25519 hoặc Ed448 là một điểm trên đường cong Edwards, được biểu diễn gọn dưới dạng mảng byte:

- Ed25519: **32 byte**;
- Ed448: **57 byte**.

Giá trị public key raw được tạo từ **tọa độ `y` theo thứ tự little-endian**; bit cao nhất của byte cuối lưu **tính chẵn/lẻ của `x`** (x-odd/sign bit). Với Ed448, phần lớn các bit còn lại ở byte cuối là bit dành riêng phải bằng 0 trong biểu diễn chuẩn.

Có thể hình dung:

~~~text
Raw Ed25519 public (32 bytes):
[ y little-endian ... ][bit 7 = xOdd, bit 0..6 = y còn lại]

Raw Ed448 public (57 bytes):
[ y little-endian ... ][bit 7 = xOdd, bit 0..6 = 0]
~~~

Đây là sơ đồ về cách **đóng gói điểm**, không phải cách xác minh mọi điểm có nằm trên đường cong hay có bậc phù hợp hay không. Một decoder tự viết chỉ kiểm tra độ dài và bit cao nhất **chưa đủ** làm bước validation mật mã cho input không tin cậy. Với dữ liệu ngoài hệ thống, dùng thư viện/provider cryptography uy tín và kiểm thử negative cases.

### 3.1. Java thể hiện public key bằng `EdECPoint`, không tự trả raw bytes

`java.security.interfaces.EdECPublicKey` công bố:

~~~java
EdECPoint getPoint();
NamedParameterSpec getParams();
~~~

Đây là chữ ký mô tả **các thành viên của interface**, không phải chương trình độc lập. `EdECPoint` có hai thuộc tính cần thiết: `getY()` trả `BigInteger` và `isXOdd()` trả `boolean`. Để chuyển thành raw 32/57 byte theo RFC, phải **tự encoding point theo little-endian với sign bit**, hoặc dùng thư viện tin cậy hỗ trợ đúng raw format.

**Không dùng:**

~~~java
byte[] rawPublic = publicKey.getEncoded(); // Sai tên biến / sai định dạng!
~~~

`getEncoded()` thông thường trả **SPKI DER** khi `getFormat()` là `"X.509"`; nó không trả trực tiếp 32/57 byte raw. Cách đặt tên chính xác:

~~~java
byte[] spkiDer = publicKey.getEncoded();
EdECPoint point = ((EdECPublicKey) publicKey).getPoint();
~~~

Các đoạn code trên là **minh họa bên trong phương thức**, giả sử `publicKey` là khóa EdEC có thể export và đã import `EdECPublicKey`/`EdECPoint`.

### 3.2. Cần biết curve trước khi hiểu raw public bytes

Raw public bytes **không chứa OID** hoặc string `"Ed25519"` / `"Ed448"`. Khi đọc một mảng byte raw, ứng dụng phải biết thuật toán từ **protocol hoặc metadata đã xác thực**. Không đoán algorithm chỉ từ độ dài nếu điều đó có thể dẫn đến algorithm confusion hoặc dữ liệu nằm trong nhiều cấu trúc khác nhau.

`EdECPublicKeySpec` yêu cầu **`NamedParameterSpec` + `EdECPoint`**, nghĩa là người dùng API cung cấp rõ curve:

~~~java
EdECPublicKeySpec spec =
        new EdECPublicKeySpec(NamedParameterSpec.ED25519, point);
PublicKey publicKey = KeyFactory.getInstance("Ed25519")
        .generatePublic(spec);
~~~

Đoạn này **minh họa**, yêu cầu biến `point` hợp lệ. Nó không tạo public key từ một mảng raw bằng cách “truyền thẳng byte[] vào constructor”.

## 4. Raw private key: seed bí mật khác với cấu trúc khóa

Ed25519 dùng **seed 32 byte**; Ed448 dùng **seed 57 byte** theo RFC 8032. Khi ký, thuật toán suy ra scalar và các giá trị phục vụ chữ ký từ seed theo quy tắc EdDSA. Seed **không đồng nghĩa** với public key raw dù hai loại có cùng độ dài theo từng curve.

Đặc biệt:

- **Private seed**: thông tin tuyệt mật, có thể dẫn tới quyền tạo chữ ký; tuyệt đối không log ra stdout, telemetry, URL hay exception message.
- **Public key**: thông tin dùng xác minh chữ ký, có thể phân phối công khai theo protocol.
- **Private expanded scalar / hash intermediate**: là giá trị nội bộ phát sinh từ seed trong thuật toán, **không** tự coi là định dạng raw private seed của Java.
- **PKCS#8**: cấu trúc mang thông tin về thuật toán và key bytes, không giống mảng seed.

`EdECPrivateKey` cung cấp `Optional<byte[]> getBytes()`, không phải `byte[]` chắc chắn luôn có. Tài liệu Javadoc ghi rõ implementation **có thể không cho xuất giá trị private key**, nên phải xử lý `Optional.empty()`. Nếu provider cho xuất, Java trả một bản sao của mảng byte và nên coi nó là dữ liệu cực kỳ nhạy cảm.

Import một seed raw trong Java:

~~~java
EdECPrivateKeySpec rawSpec =
        new EdECPrivateKeySpec(NamedParameterSpec.ED25519, rawSeed);
PrivateKey privateKey = KeyFactory.getInstance("Ed25519")
        .generatePrivate(rawSpec);
~~~

Đây là **mã minh họa trong method**; `rawSeed` phải đến từ nguồn đáng tin, có độ dài và quyền truy cập phù hợp. Không thay `rawSpec` bằng `new PKCS8EncodedKeySpec(rawSeed)`: constructor PKCS#8 chờ **DER container**, không chờ seed.

### 4.1. Vì sao cùng 32 byte vẫn có thể là hai ý nghĩa hoàn toàn khác nhau?

Một Ed25519 public key và một Ed25519 private seed đều có độ dài **32 byte**. Không thể kết luận mảng byte nào là public/private chỉ bằng `bytes.length == 32`. Loại dữ liệu được quyết định bởi **hợp đồng API/protocol và ngữ cảnh bảo mật**.

Ví dụ một hệ thống có hai trường `publicKeyRaw` và `privateSeedRaw` phải giữ chúng **tách biệt**, có validation, quyền lưu trữ và nhãn xuất/nhập khác nhau. Truyền private seed vào vị trí public point không chỉ làm sai kỹ thuật mà còn có thể gây **rò rỉ khóa bí mật**.

## 5. X.509 SubjectPublicKeyInfo (SPKI): public key kèm AlgorithmIdentifier

Trong Java, `PublicKey.getFormat()` của Ed25519/Ed448 thông thường là `"X.509"`. Ở đây, tên format **X.509** được dùng cho **SubjectPublicKeyInfo**, không có nghĩa byte trả về là một chứng chỉ.

Cấu trúc ASN.1 khái niệm (từ RFC 8410):

~~~text
SubjectPublicKeyInfo ::= SEQUENCE {
    algorithm         AlgorithmIdentifier,
    subjectPublicKey  BIT STRING
}

AlgorithmIdentifier ::= SEQUENCE {
    algorithm  OBJECT IDENTIFIER,
    parameters  OPTIONAL (phải vắng mặt với Ed25519/Ed448)
}
~~~

Các OID tiêu chuẩn:

| Thuật toán | OID |
| --- | --- |
| Ed25519 | `1.3.101.112` |
| Ed448 | `1.3.101.113` |
| X25519 (key agreement, **không phải Ed25519**) | `1.3.101.110` |
| X448 (key agreement, **không phải Ed448**) | `1.3.101.111` |

Trong SPKI của EdDSA, trường `subjectPublicKey` chứa **raw public point bytes** trong một BIT STRING ASN.1. Bên ngoài còn có SEQUENCE, AlgorithmIdentifier và độ dài DER. Vì vậy toàn bộ SPKI sẽ dài hơn raw public key và cho phần mềm biết khóa dùng thuật toán nào.

Import/export đúng định dạng:

~~~java
byte[] spkiDer = pair.getPublic().getEncoded();
PublicKey restored = KeyFactory.getInstance("Ed25519")
        .generatePublic(new X509EncodedKeySpec(spkiDer));
~~~

Đoạn code này ở trong method, yêu cầu `pair` chứa khóa Ed25519 exportable. `X509EncodedKeySpec` yêu cầu **SPKI DER hoàn chỉnh**, không chấp nhận raw 32 byte đơn lẻ.

### 5.1. SPKI không phải X.509 certificate

Những điều sau **khác nhau**:

- `certificate.getEncoded()`: DER của **toàn bộ chứng chỉ** X.509, có subject/issuer, thời hạn, signature và nhiều thông tin khác.
- `certificate.getPublicKey().getEncoded()`: cách xuất **key object**, thường ở dạng SPKI DER.
- Raw public point 32/57 byte: chỉ là phần giá trị key, không phải certificate hay SPKI.

Nếu API nhận **chứng chỉ**, dùng `CertificateFactory` để parse certificate. Nếu API nhận **SPKI**, dùng `KeyFactory` + `X509EncodedKeySpec`. Nếu API nhận **raw point**, phải chuyển đúng raw theo curve trước khi dùng `EdECPublicKeySpec` hoặc thư viện phù hợp. Không nhầm lẫn ba loại do cùng có từ “public key”.

## 6. PKCS#8: private seed được đóng trong cấu trúc mang thuật toán

`PrivateKey.getFormat()` của khóa EdEC có thể export trong provider phổ biến là `"PKCS#8"`. Với RFC 8410, private key được đóng gói thành cấu trúc ASN.1 chứa thuật toán và trường private key; private bytes bên trong còn được biểu diễn bởi một OCTET STRING thuật toán cụ thể.

Cấu trúc mô tả khái niệm:

~~~text
PrivateKeyInfo / OneAsymmetricKey ::= SEQUENCE {
    version,
    privateKeyAlgorithm AlgorithmIdentifier,
    privateKey OCTET STRING,    -- chứa CurvePrivateKey đã DER-encode
    ... optional attributes / publicKey (tùy cấu trúc)
}

CurvePrivateKey ::= OCTET STRING  -- raw seed RFC 8032
~~~

Điểm cần nhớ: nếu nhìn DER bằng hex, seed **không đơn giản là “n byte đầu hoặc n byte cuối không có metadata” theo một quy ước vĩnh viễn**. Có độ dài ASN.1, OID và các trường optional trong những biến thể cấu trúc. Nên nhờ `KeyFactory` xử lý container DER thay vì viết substring/hardcoded offset.

Import/export PKCS#8 đúng kiểu:

~~~java
byte[] pkcs8Der = pair.getPrivate().getEncoded();
PrivateKey restored = KeyFactory.getInstance("Ed25519")
        .generatePrivate(new PKCS8EncodedKeySpec(pkcs8Der));
~~~

Đây là code minh họa trong method với `pair` exportable. `PKCS8EncodedKeySpec` nhận **DER PKCS#8**, không nhận seed 32 byte. **Không** đưa PEM text chưa giải Base64 thẳng vào `PKCS8EncodedKeySpec`.

### 6.1. PKCS#8 không tự có nghĩa “được mã hóa bảo mật”

**PKCS#8 không mã hóa (`PRIVATE KEY`)** là cấu trúc chứa thông tin private key, có thể để lộ seed khi bị đọc. **Encrypted PKCS#8 (`ENCRYPTED PRIVATE KEY`)** là dạng khác có lớp mã hóa và thông tin giải mã. Không coi mọi PKCS#8 DER là encrypted.

Hệ thống thực nên ưu tiên kho khóa chuyên dụng, keystore hoặc HSM theo threat model; nếu bắt buộc xuất PKCS#8, cần chính sách bảo vệ khi lưu, phân phối, backup và rotation. Không cho phép plaintext private key xuất hiện trong log hoặc output của bài thực hành.

## 7. Chương trình Java 17+ hoàn chỉnh: so sánh raw, SPKI, PKCS#8 và round-trip

Đây là ví dụ kiểm chứng chính. Mã tạo khóa **mới** cho Ed25519 và Ed448 qua provider JDK, xuất public/private DER, lấy private seed nếu provider cho phép và chuyển point thành raw public đúng theo RFC 8032. Sau đó mã import lại từ **cả hai dạng** bằng đúng `KeySpec`, ký và xác minh chữ ký. Chương trình **không in bất kỳ byte khóa bí mật nào**.

Lưu toàn bộ vào **`EdECKeyFormatsDemo.java`**:

~~~java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.interfaces.EdECPrivateKey;
import java.security.interfaces.EdECPublicKey;
import java.security.spec.EdECPoint;
import java.security.spec.EdECPrivateKeySpec;
import java.security.spec.EdECPublicKeySpec;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.NamedParameterSpec;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;

public class EdECKeyFormatsDemo {
    public static void main(String[] args) throws Exception {
        demonstrate("Ed25519", NamedParameterSpec.ED25519, 32);
        demonstrate("Ed448", NamedParameterSpec.ED448, 57);
    }

    private static void demonstrate(String algorithm,
                                    NamedParameterSpec params,
                                    int rawSize) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance(algorithm);
        generator.initialize(params);
        KeyPair pair = generator.generateKeyPair();

        EdECPublicKey publicKey = (EdECPublicKey) pair.getPublic();
        EdECPrivateKey privateKey = (EdECPrivateKey) pair.getPrivate();

        byte[] rawPublic = toRawPublic(publicKey.getPoint(), rawSize);
        byte[] rawSeed = privateKey.getBytes()
                .orElseThrow(() ->
                        new IllegalStateException("Seed not exportable"));
        byte[] spki = publicKey.getEncoded();
        byte[] pkcs8 = privateKey.getEncoded();
        if (spki == null || pkcs8 == null) {
            throw new IllegalStateException("DER export not supported");
        }

        KeyFactory factory = KeyFactory.getInstance(algorithm);
        var publicFromSpki =
                factory.generatePublic(new X509EncodedKeySpec(spki));
        var privateFromPkcs8 =
                factory.generatePrivate(new PKCS8EncodedKeySpec(pkcs8));

        EdECPoint point = fromRawPublic(rawPublic, rawSize);
        var publicFromRaw = factory.generatePublic(
                new EdECPublicKeySpec(params, point));
        var privateFromRaw = factory.generatePrivate(
                new EdECPrivateKeySpec(params, rawSeed));

        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(privateFromRaw);
        signer.update("data integrity".getBytes(StandardCharsets.UTF_8));
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(publicFromRaw);
        verifier.update("data integrity".getBytes(StandardCharsets.UTF_8));
        boolean verified = verifier.verify(signature);

        boolean derRoundTrip =
                Arrays.equals(spki, publicFromSpki.getEncoded())
                && Arrays.equals(pkcs8, privateFromPkcs8.getEncoded());
        boolean rawRoundTrip =
                Arrays.equals(rawPublic, toRawPublic(
                        ((EdECPublicKey) publicFromRaw).getPoint(), rawSize))
                && Arrays.equals(rawSeed, ((EdECPrivateKey) privateFromRaw)
                        .getBytes().orElseThrow());

        boolean publicRejectsRaw;
        boolean privateRejectsRaw;
        try {
            factory.generatePublic(new X509EncodedKeySpec(rawPublic));
            publicRejectsRaw = false;
        } catch (InvalidKeySpecException expected) {
            publicRejectsRaw = true;
        }
        try {
            factory.generatePrivate(new PKCS8EncodedKeySpec(rawSeed));
            privateRejectsRaw = false;
        } catch (InvalidKeySpecException expected) {
            privateRejectsRaw = true;
        }

        System.out.println(algorithm + " formats="
                + publicKey.getFormat() + "/" + privateKey.getFormat());
        System.out.println(algorithm
                + " lengths(rawPub,rawSeed,SPKI,PKCS8)="
                + rawPublic.length + "," + rawSeed.length + ","
                + spki.length + "," + pkcs8.length);
        System.out.println(algorithm + " derRoundTrip=" + derRoundTrip);
        System.out.println(algorithm + " rawRoundTrip=" + rawRoundTrip);
        System.out.println(algorithm + " verifies=" + verified);
        System.out.println(algorithm + " rejectRawAsDER="
                + (publicRejectsRaw && privateRejectsRaw));

        Arrays.fill(rawSeed, (byte) 0);
        Arrays.fill(pkcs8, (byte) 0);
        Arrays.fill(signature, (byte) 0);
    }

    private static byte[] toRawPublic(EdECPoint point, int size) {
        BigInteger y = point.getY();
        int maximumBits = size == 32 ? 255 : 448;
        if (y.signum() < 0 || y.bitLength() > maximumBits) {
            throw new IllegalArgumentException("Public point out of range");
        }
        byte[] littleEndian = new byte[size];
        for (int i = 0; i < size; i++) {
            littleEndian[i] = y.byteValue();
            y = y.shiftRight(8);
        }
        if (size == 57 && littleEndian[56] != 0) {
            throw new IllegalArgumentException(
                    "Noncanonical Ed448 public point");
        }
        if (point.isXOdd()) {
            littleEndian[size - 1] |= (byte) 0x80;
        }
        return littleEndian;
    }

    private static EdECPoint fromRawPublic(byte[] raw, int size) {
        if (raw.length != size) {
            throw new IllegalArgumentException(
                    "Incorrect public key length");
        }
        byte[] littleEndian = raw.clone();
        boolean xOdd = (littleEndian[size - 1] & 0x80) != 0;
        littleEndian[size - 1] &= 0x7f;
        if (size == 57 && littleEndian[56] != 0) {
            throw new IllegalArgumentException(
                    "Ed448 reserved bits not zero");
        }
        byte[] bigEndian = new byte[size];
        for (int i = 0; i < size; i++) {
            bigEndian[size - i - 1] = littleEndian[i];
        }
        BigInteger y = new BigInteger(1, bigEndian);
        BigInteger prime = size == 32
                ? BigInteger.ONE.shiftLeft(255)
                        .subtract(BigInteger.valueOf(19))
                : BigInteger.ONE.shiftLeft(448)
                        .subtract(BigInteger.ONE.shiftLeft(224))
                        .subtract(BigInteger.ONE);
        if (y.compareTo(prime) >= 0) {
            throw new IllegalArgumentException(
                    "Public y not canonical");
        }
        return new EdECPoint(xOdd, y);
    }
}
~~~

Biên dịch và chạy trong thư mục có tệp nguồn:

~~~bash
javac --release 17 -Xlint:all EdECKeyFormatsDemo.java
java EdECKeyFormatsDemo
~~~

**Stdout chính xác trên provider EdEC mặc định của JDK được kiểm thử:**

~~~text
Ed25519 formats=X.509/PKCS#8
Ed25519 lengths(rawPub,rawSeed,SPKI,PKCS8)=32,32,44,48
Ed25519 derRoundTrip=true
Ed25519 rawRoundTrip=true
Ed25519 verifies=true
Ed25519 rejectRawAsDER=true
Ed448 formats=X.509/PKCS#8
Ed448 lengths(rawPub,rawSeed,SPKI,PKCS8)=57,57,69,73
Ed448 derRoundTrip=true
Ed448 rawRoundTrip=true
Ed448 verifies=true
Ed448 rejectRawAsDER=true
~~~

### 7.1. Những kết luận thực sự có thể rút ra từ output

- **`formats=X.509/PKCS#8`**: `getEncoded()` được export thành DER **container tiêu chuẩn** với provider được kiểm thử.
- **`rawPub` và `rawSeed` đều 32 hoặc 57**: độ dài bằng nhau theo từng curve **không có nghĩa nội dung giống nhau**.
- **SPKI 44/69 và PKCS#8 48/73**: provider trả về một kiểu đóng gói cụ thể lớn hơn raw. Đây là **kết quả kiểm thử**, không yêu cầu mọi provider luôn xuất byte-identical DER.
- **`derRoundTrip=true`**: `X509EncodedKeySpec`/`PKCS8EncodedKeySpec` tương thích với DER xuất bởi provider trong chương trình này.
- **`rawRoundTrip=true`**: khi chuyển raw public point thành `EdECPoint` rồi đưa vào `EdECPublicKeySpec`, và raw private seed vào `EdECPrivateKeySpec`, ta nhận lại khóa cùng giá trị với nguồn.
- **`verifies=true`**: chữ ký tạo từ private key import **raw** được public key import **raw** xác minh thành công. Việc ký/xác minh thể hiện khóa khớp nhau, không chỉ so sánh số byte.
- **`rejectRawAsDER=true`**: `KeyFactory` được kiểm thử từ chối mảng raw khi nó bị gói sai vào `X509EncodedKeySpec` hoặc `PKCS8EncodedKeySpec`.

### 7.2. Điều kiện và giới hạn của mã thử nghiệm

Đây là chương trình đào tạo trên provider tích hợp của JDK, cho phép xuất khóa. Trên HSM/provider khác, `EdECPrivateKey.getBytes()` có thể rỗng, `getEncoded()` có thể trả `null`, thuật toán `Ed448` có thể không được provider hỗ trợ, hoặc byte DER có thể được serialize khác dù khóa hợp lệ. Chương trình cố ý thông báo rõ khi export không được hỗ trợ.

Hai hàm `toRawPublic` và `fromRawPublic` minh họa **biểu diễn RFC 8032** của public point: little-endian `y`, bit x-odd, độ dài và kiểm tra `y < p`/bit reserved. **Không coi chúng là thư viện xác thực public key không tin cậy hoàn chỉnh**. Phần lớn ứng dụng nên giữ khóa ở dạng `PublicKey`/`PrivateKey`, dùng `KeyFactory` hoặc thư viện có parser raw-key được kiểm thử, thay vì tự xử lý ASN.1 hay toán học đường cong.

`Arrays.fill(rawSeed, 0)` và xóa `pkcs8` cuối ví dụ giảm thời gian sống của **một số mảng byte do ứng dụng giữ**, nhưng không thể đảm bảo xóa mọi bản sao/đối tượng khóa/provider state khỏi memory. Hạn chế tối đa việc export private seed, không lưu bản sao ở `String` hoặc biến toàn cục, và dùng giải pháp quản lý khóa phù hợp khi sản phẩm cần mức bảo vệ cao.

## 8. Import/export đúng định dạng bằng `KeyFactory` và `KeySpec`

Đây là sơ đồ lựa chọn API:

~~~text
ĐẦU VÀO PUBLIC KEY
  32/57 bytes raw RFC 8032
       --> decode point (xOdd, y), biết curve
       --> EdECPublicKeySpec(params, point)
       --> KeyFactory.generatePublic(...)

  DER X.509 SubjectPublicKeyInfo
       --> X509EncodedKeySpec(der)
       --> KeyFactory.generatePublic(...)

  PEM "-----BEGIN PUBLIC KEY-----"
       --> bỏ armor + Base64 decode --> SPKI DER
       --> X509EncodedKeySpec(der)
       --> KeyFactory.generatePublic(...)

ĐẦU VÀO PRIVATE KEY
  32/57 bytes raw EdDSA seed (nếu được phép export/import)
       --> EdECPrivateKeySpec(params, seed)
       --> KeyFactory.generatePrivate(...)

  DER PKCS#8 không mã hóa
       --> PKCS8EncodedKeySpec(der)
       --> KeyFactory.generatePrivate(...)

  PEM "-----BEGIN PRIVATE KEY-----"
       --> bỏ armor + Base64 decode --> PKCS#8 DER
       --> PKCS8EncodedKeySpec(der)

  PEM "-----BEGIN ENCRYPTED PRIVATE KEY-----"
       --> giải mã đúng chuẩn bằng công cụ thích hợp
       --> PKCS#8 DER đã được giải mã
       --> PKCS8EncodedKeySpec(der)
~~~

**Điều kiện chung:** tên algorithm/curve phải phù hợp với vật liệu khóa. Ví dụ `KeyFactory.getInstance("Ed25519")` dùng cho Ed25519, không tự diễn giải một mảng 57 byte là Ed448 hoặc một khóa X25519.

### 8.1. Cấu trúc dữ liệu “raw” không bao gồm tên thuật toán

Nếu một API yêu cầu nhập `raw public key`, phải có thông tin rõ ràng nó là **Ed25519 hay Ed448**. Nếu metadata được truyền cùng input, cần kiểm tra nó không thể bị thay đổi nhằm ép hệ thống dùng sai thuật toán. Trong nhiều giao thức, việc gắn algorithm với key là trách nhiệm của envelope/protocol hoặc cách định nghĩa schema.

Đừng xem `Ed25519`, `Ed448`, `X25519` và `X448` như những tên có thể đổi cho nhau: Ed25519/Ed448 là thuật toán **chữ ký số EdDSA**; X25519/X448 thuộc họ **trao đổi khóa Diffie–Hellman**. Dù một số thuật toán có số byte tương tự, ý nghĩa và API khác nhau.

### 8.2. Khi nào nên giữ nguyên DER, khi nào cần raw?

**Giữ DER SPKI/PKCS#8** nếu làm việc với Java `KeyFactory`, kho khóa, chuẩn X.509/PKCS#8, tệp PEM tiêu chuẩn hoặc API đã yêu cầu container. DER chứa AlgorithmIdentifier giúp thư viện biết rõ khóa.

**Chuyển sang raw** chỉ khi giao thức đích **quy định cụ thể** raw Ed25519/Ed448, chẳng hạn một định dạng gọn cho public key. Việc chuyển đổi phải bảo đảm algorithm/curve, thứ tự byte, quy tắc sign bit và validation phù hợp. Một hệ thống không nên tự bỏ header DER theo offset cứng để tiết kiệm vài byte.

## 9. PEM: armor của DER, không phải “chuỗi raw”

PEM thường là Base64 của DER với một cặp dòng marker:

~~~text
-----BEGIN PUBLIC KEY-----
[Base64 của SPKI DER]
-----END PUBLIC KEY-----
~~~

Dấu ngoặc vuông trên chỉ là **ký hiệu minh họa**, không phải một khóa thực. Khi decode, `Base64` trả lại **DER SPKI**, không trả raw 32/57 byte. Chú ý nhãn:

| PEM label | Ý nghĩa thường gặp | API Java sau khi decode |
| --- | --- | --- |
| `BEGIN PUBLIC KEY` | SPKI DER | `X509EncodedKeySpec` |
| `BEGIN PRIVATE KEY` | PKCS#8 DER không mã hóa | `PKCS8EncodedKeySpec` |
| `BEGIN ENCRYPTED PRIVATE KEY` | PKCS#8 đã mã hóa | Phải **giải mã** trước khi tạo `PKCS8EncodedKeySpec` |
| `BEGIN CERTIFICATE` | Certificate X.509 | `CertificateFactory`, không đưa thẳng vào `X509EncodedKeySpec` |
| `BEGIN OPENSSH PRIVATE KEY` | Định dạng private key riêng OpenSSH | Không phải PKCS#8; cần parser/interop phù hợp |

`Base64` chỉ thay đổi cách biểu diễn dữ liệu, **không mã hóa bảo mật**. Một PEM `PRIVATE KEY` chưa mã hóa có độ nhạy tương đương dữ liệu private key ở bên trong.

### 9.1. Ví dụ độc lập: PEM public key Ed25519 round-trip

Ví dụ sau chỉ xuất **public key**, không in dữ liệu bí mật. Lưu file **`EdECPemPublicDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public class EdECPemPublicDemo {
    public static void main(String[] args) throws Exception {
        PublicKey publicKey =
                KeyPairGenerator.getInstance("Ed25519")
                        .generateKeyPair().getPublic();
        byte[] spki = publicKey.getEncoded();
        if (spki == null) {
            throw new IllegalStateException("Not exportable");
        }

        String body = Base64.getMimeEncoder(
                64, new byte[] {'\n'}).encodeToString(spki);
        String pem = "-----BEGIN PUBLIC KEY-----\n"
                + body + "\n-----END PUBLIC KEY-----\n";

        String stripped = pem.replace(
                "-----BEGIN PUBLIC KEY-----", "")
                .replace("-----END PUBLIC KEY-----", "");
        byte[] parsedDer =
                Base64.getMimeDecoder().decode(stripped);

        PublicKey restored = KeyFactory.getInstance("Ed25519")
                .generatePublic(new X509EncodedKeySpec(parsedDer));

        System.out.println("header=" +
                pem.lines().findFirst().orElse(""));
        System.out.println("decodedDerMatches=" +
                Arrays.equals(spki, parsedDer));
        System.out.println("restoredFormat=" + restored.getFormat());
        System.out.println("sameEncoding=" +
                Arrays.equals(spki, restored.getEncoded()));
    }
}
~~~

~~~bash
javac --release 17 -Xlint:all EdECPemPublicDemo.java
java EdECPemPublicDemo
~~~

**Stdout chính xác với provider được kiểm thử:**

~~~text
header=-----BEGIN PUBLIC KEY-----
decodedDerMatches=true
restoredFormat=X.509
sameEncoding=true
~~~

Sau khi bóc nhãn PEM và Base64 decode, `parsedDer` **khớp toàn bộ `spki`** (có AlgorithmIdentifier), và `KeyFactory` import lại bằng `X509EncodedKeySpec`. Ví dụ **không in raw point** và không giả định byte public key cố định vì keypair được tạo ngẫu nhiên.

**Giới hạn của cách parse PEM này:** chương trình tự tạo một PEM đơn giản với nhãn chính xác. Trong production, dùng parser PEM/ASN.1 có kiểm tra marker, header, kích thước, số block, encoding và format; không dùng `String.replace` đơn giản để xử lý PEM đến từ nguồn không tin cậy.

## 10. Vì sao không thể “đổi tên `KeySpec`” khi có mảng byte?

`KeySpec` nói cho `KeyFactory` **cách hiểu dữ liệu**. Nếu dữ liệu là raw, phải dùng kiểu spec cho raw; nếu dữ liệu là DER container, phải dùng kiểu spec cho DER.

| Dữ liệu thực tế | Spec đúng | Spec sai thường gặp |
| --- | --- | --- |
| Ed25519 raw seed 32 byte | `EdECPrivateKeySpec(ED25519, seed)` | `PKCS8EncodedKeySpec(seed)` |
| Ed448 raw seed 57 byte | `EdECPrivateKeySpec(ED448, seed)` | `PKCS8EncodedKeySpec(seed)` |
| Ed25519 raw public point 32 byte | `EdECPublicKeySpec(ED25519, point)` sau decode point | `X509EncodedKeySpec(rawPointBytes)` |
| Ed448 raw public point 57 byte | `EdECPublicKeySpec(ED448, point)` sau decode point | `X509EncodedKeySpec(rawPointBytes)` |
| Ed25519/Ed448 SPKI DER | `X509EncodedKeySpec(spkiDer)` | `EdECPublicKeySpec` chưa chuyển DER thành point |
| Ed25519/Ed448 PKCS#8 DER | `PKCS8EncodedKeySpec(pkcs8Der)` | `EdECPrivateKeySpec` chưa giải mã seed |
| PEM public key text | Base64 decode → SPKI DER → `X509EncodedKeySpec` | Dùng bytes của chính văn bản PEM làm DER |
| Certificate DER | `CertificateFactory` | `X509EncodedKeySpec(certDer)` |

Trong ví dụ chính, hai phép nhập sai `new X509EncodedKeySpec(rawPublic)` và `new PKCS8EncodedKeySpec(rawSeed)` bị provider từ chối bằng `InvalidKeySpecException`. Đừng dựa vào một exception message cụ thể vì provider/version có thể khác nhau; **phân biệt loại dữ liệu từ hợp đồng trước khi gọi API**.

## 11. Tương tác với định dạng khác: OpenSSH, JWK và chứng chỉ

**OpenSSH `ssh-ed25519 ...`:** dòng public key SSH chứa một blob theo protocol SSH, trong đó có **tên loại khóa** và raw public bytes. Chuỗi Base64 sau `ssh-ed25519` **không phải SPKI DER**. Nếu muốn dùng trong Java `KeyFactory`, cần decoder SSH đúng cấu trúc rồi ánh xạ sang `EdECPoint`/`EdECPublicKeySpec`, hoặc thư viện liên thông SSH phù hợp.

**OpenSSH private key:** `BEGIN OPENSSH PRIVATE KEY` không đồng nghĩa `BEGIN PRIVATE KEY`; format đóng gói và chính sách mã hóa khác. Không đưa byte sau Base64 decode vào `PKCS8EncodedKeySpec` mà chưa chuyển đúng.

**JSON Web Key (JWK) cho Ed25519/Ed448:** mô hình `kty="OKP"`, `crv="Ed25519"` hoặc `"Ed448"`; trường `x` là Base64url của **raw public key**, và `d` (nếu có) chứa material bí mật ở dạng raw seed tương ứng theo profile. JWK **không phải SPKI/PKCS#8 DER**. Đặc biệt, không serialize/log `d` khi chỉ cần public key.

**Chứng chỉ X.509:** `CertificateFactory.getInstance("X.509")` đọc certificate DER/PEM, còn `getPublicKey()` cho ra một đối tượng `PublicKey` có thể export dạng SPKI. Chứng chỉ cung cấp thêm danh tính, chữ ký CA, thời hạn và chính sách tin cậy; **public key đơn thuần không tự chứng minh danh tính**.

**Tránh đánh đồng interop với trust:** có thể parse được SPKI hoặc JWK **không chứng minh khóa thuộc về người dùng/đối tác nào**. Quy trình xác minh certificate chain, trust anchor, pinning hoặc quản lý định danh khóa cần được thiết kế riêng theo giao thức.

## 12. Bảo vệ khóa bí mật khi làm việc với raw/PKCS#8

Việc xuất seed bằng `getBytes()` hoặc xuất PKCS#8 bằng `getEncoded()` đưa **vật liệu bí mật vào bộ nhớ ứng dụng**. Những yêu cầu cần cân nhắc:

- **Không ghi log secret:** kể cả để debug lỗi import, chỉ log algorithm, format, độ dài (nếu được phép) và mã lỗi; không in seed, private DER, private PEM hoặc full exception payload nhạy cảm.
- **Hạn chế export:** nếu provider/HSM giữ khóa không export được, hãy ký/xác minh qua provider trực tiếp; đừng đổi provider chỉ để lấy seed.
- **Chính sách lưu trữ và truyền:** dùng cơ chế quản lý khóa, ACL, encryption at rest, backup/rotation và kênh truyền phù hợp; Base64/PEM không cung cấp bảo mật.
- **Không đưa private byte[] vào `String`:** chuỗi immutable khó kiểm soát vòng đời và xóa dữ liệu; nếu phải xử lý bytes, hạn chế copies và đặt phạm vi sử dụng ngắn.
- **Cân nhắc `Arrays.fill` cho buffer riêng:** có thể xóa một số byte[] do ứng dụng sở hữu sau khi dùng; không có bảo đảm xóa toàn bộ bản sao trong provider, GC, native memory hoặc JIT.
- **Không lưu raw seed bên cạnh public key trong cùng phản hồi API:** phân tách quyền truy cập, DTO và đường dữ liệu rõ ràng.
- **Có xác thực đầu vào cryptographic:** kiểm tra algorithm, độ dài, encoding chuẩn và ràng buộc giao thức; không chỉ dựa vào việc DER parser không ném lỗi.
- **Chữ ký cần xác minh trên đúng thông điệp và đúng algorithm:** tạo được object `PublicKey` không tự bảo đảm nguồn khóa đáng tin.

**Ghi nhớ:** raw/DER/PEM là câu chuyện **định dạng**; an toàn hay không phụ thuộc vào quyền truy cập khóa, thuật toán, trust model và cách quản lý secret.

## 13. Lỗi thường gặp, nguyên nhân và cách sửa

**Lỗi 1 — “`getEncoded()` trả raw public 32 byte.”**  
Sai với `EdECPublicKey` của provider thông thường: `getFormat() == "X.509"` và bytes là **SPKI DER**. Nếu protocol cần raw, chuyển `getPoint()` sang RFC 8032 representation đúng cách.

**Lỗi 2 — “`getEncoded()` và `getBytes()` của EdECPrivateKey giống nhau.”**  
Sai: `getEncoded()` có thể trả **PKCS#8 DER**, `getBytes()` (nếu có) trả **raw seed**. Cả hai chứa dữ liệu bí mật nhưng có cấu trúc khác.

**Lỗi 3 — “32 byte là Ed25519 public hay private tùy ý.”**  
Sai. Public point và private seed có cùng độ dài nhưng ý nghĩa và quyền hoàn toàn khác. Phải xác định loại từ schema/protocol.

**Lỗi 4 — “Cắt 12 byte đầu SPKI là cách chuyển đổi chuẩn.”**  
Không. Đó là giả định về một bản DER hiện quan sát được, không phải parser ASN.1. Chọn KeyFactory hoặc thư viện chuẩn, không hardcode offset.

**Lỗi 5 — “`X509EncodedKeySpec` có thể nhận certificate DER.”**  
Không. Nó dùng cho **SPKI DER**, còn chứng chỉ phải được parse bằng `CertificateFactory`.

**Lỗi 6 — “PEM là raw key sau Base64 decode.”**  
Không. Với nhãn `PUBLIC KEY` hoặc `PRIVATE KEY` thông thường, Base64 decode cho **DER container** tương ứng.

**Lỗi 7 — “PKCS#8 luôn có mật khẩu.”**  
Sai. `BEGIN PRIVATE KEY` thường là PKCS#8 **không mã hóa**. `BEGIN ENCRYPTED PRIVATE KEY` phải giải mã đúng quy trình trước khi import.

**Lỗi 8 — “Không export được seed nghĩa là khóa không dùng được.”**  
Sai. Provider có thể cho ký bằng private key nhưng không cho xuất private material; đây thường là chính sách bảo vệ.

**Lỗi 9 — “Ed25519 có thể thay bằng X25519 vì cùng curve và 32 byte.”**  
Sai. Ed25519 là chữ ký EdDSA, X25519 là trao đổi khóa; key format, algorithm identifiers và cách dùng khác.

**Lỗi 10 — “Có raw point là KeyFactory phải chấp nhận mọi byte.”**  
Sai. Point cần encoding hợp lệ và có thể cần kiểm tra giá trị/canonicality/các điều kiện bảo mật theo provider/protocol.

**Lỗi 11 — “Chỉ cần so sánh byte[] của hai DER để chứng minh khóa giống nhau trên mọi provider.”**  
Không nhất thiết. Hai định dạng hợp lệ có thể khác metadata/encoding; với interop, kiểm tra key material, đối chiếu thuật toán và dùng chữ ký test nếu thích hợp. `Arrays.equals(...)` trong bài chỉ kiểm chứng provider được dùng.

**Lỗi 12 — “Đưa private PEM lên bug tracker để tái hiện.”**  
Không. Chỉ dùng khóa demo sinh mới và không bao giờ đưa secret production vào log, ticket, chat hoặc file công khai.

**Lỗi 13 — “Từ `getY()` BigInteger có thể viết thẳng `toByteArray()` làm raw.”**  
Không. `BigInteger.toByteArray()` mặc định **big-endian có sign byte**, trong khi RFC 8032 raw public dùng **little-endian với x-odd bit ở byte cuối**. Cần encode đúng chiều, đúng độ dài và đúng sign bit.

## 14. Bài tập tự kiểm tra

**Câu 1.** Public key Ed25519 raw có 32 byte. Gọi `new X509EncodedKeySpec(rawBytes)` có đúng không?  
**Đáp án:** Không. `X509EncodedKeySpec` yêu cầu **SPKI DER**. Raw phải được giải mã thành `EdECPoint` và đi với `NamedParameterSpec.ED25519`/`EdECPublicKeySpec` hoặc qua thư viện phù hợp.

**Câu 2.** Khóa Ed448 private seed và public key raw đều có bao nhiêu byte?  
**Đáp án:** **57 byte**, nhưng đó là hai giá trị và mục đích sử dụng khác nhau.

**Câu 3.** `EdECPrivateKey.getBytes()` có chắc trả về raw seed hay không?  
**Đáp án:** Không chắc: trả `Optional<byte[]>` và có thể rỗng nếu implementation không cho export.

**Câu 4.** DER SPKI có chứa tên thuật toán không?  
**Đáp án:** Có thông tin thuật toán dạng **ASN.1 AlgorithmIdentifier/OID**, ví dụ `1.3.101.112` cho Ed25519.

**Câu 5.** PEM `BEGIN PUBLIC KEY` sau Base64 decode thành gì?  
**Đáp án:** **SPKI DER**, không phải raw point 32/57 byte.

**Câu 6.** `BEGIN CERTIFICATE` có thể nhập như `PUBLIC KEY` SPKI không?  
**Đáp án:** Không. Certificate là cấu trúc lớn hơn, parse bằng `CertificateFactory`.

**Câu 7.** Dùng `BigInteger.toByteArray()` để export Ed25519 raw point có vấn đề gì?  
**Đáp án:** Byte order và sign byte có thể sai; raw yêu cầu little-endian, độ dài cố định, x-odd bit ở cuối.

**Câu 8.** Vì sao không lưu raw seed dưới dạng Base64 trong log?  
**Đáp án:** Base64 không mã hóa bảo mật, khôi phục lại seed rất dễ và có thể dẫn tới giả mạo chữ ký.

**Câu 9.** Có thể import private key PKCS#8 DER bằng `EdECPrivateKeySpec` trực tiếp không?  
**Đáp án:** Không. Dùng `PKCS8EncodedKeySpec` cho DER; nếu cần raw seed phải giải mã đúng định dạng trước.

**Câu 10.** Vì sao stdout `rejectRawAsDER=true` hữu ích?  
**Đáp án:** Nó minh họa provider phát hiện việc nhầm **raw key bytes** với **ASN.1 DER container**, thay vì chỉ suy luận từ độ dài.

**Câu 11.** Public key trong SSH `ssh-ed25519 AAAA...` có phải Base64 SPKI DER không?  
**Đáp án:** Không. SSH dùng format wire riêng, cần decoder hoặc thư viện interop phù hợp.

**Câu 12.** Một public key import thành công có chứng minh người gửi là ai không?  
**Đáp án:** Không. Cần gắn key với danh tính/trust policy của giao thức, certificate chain/pinning khi áp dụng.

## 15. Checklist khi xây hệ thống import/export khóa EdEC

- [ ] Tài liệu interface/API ghi **rõ input là raw, SPKI DER, PKCS#8 DER, PEM, certificate, SSH hay JWK**.
- [ ] Đã phân biệt `Ed25519` và `Ed448`, không lấy `X25519`/`X448` thay cho EdDSA.
- [ ] Nếu raw public: có curve parameter, độ dài 32/57, quy tắc point encoding/canonicality và parser tin cậy.
- [ ] Nếu raw private: có chính sách bảo vệ seed, độ dài 32/57, API `EdECPrivateKeySpec` khi thực sự cần import.
- [ ] Nếu SPKI: dùng `X509EncodedKeySpec`, không cắt header DER thủ công.
- [ ] Nếu PKCS#8: dùng `PKCS8EncodedKeySpec` cho dạng đã giải mã; không coi mọi PKCS#8 là encrypted.
- [ ] Nếu PEM: kiểm tra nhãn, Base64 decode, giới hạn kích thước, sau đó mới parse đúng cấu trúc DER.
- [ ] Nếu certificate: dùng `CertificateFactory` và thực hiện kiểm tra trust đúng ứng dụng.
- [ ] Xử lý được `getEncoded() == null` và `EdECPrivateKey.getBytes().isEmpty()` khi provider không export.
- [ ] Không log raw seed, PKCS#8 private DER, private PEM hoặc JWK có `d`.
- [ ] Có test round-trip tạo khóa → export/import → ký/xác minh trên JDK/provider thực tế.
- [ ] Có negative test: raw bị nhầm là DER, sai algorithm, sai length, PEM label sai, điểm không hợp lệ, dữ liệu bị sửa.
- [ ] Không gắn trust vào “parse được khóa”; có policy xác định chủ sở hữu khóa, nguồn tin cậy, rotation.
- [ ] Đối với ứng dụng quan trọng, ưu tiên provider/keystore/HSM và thư viện ASN.1 được duy trì thay vì viết decoder tự chế.

## 16. Tài liệu chuẩn còn áp dụng

- [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): Java 15 bổ sung Ed25519/Ed448 và các API tương ứng.
- [Java SE 25 — `EdECPrivateKey`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html): `getBytes()` trả `Optional<byte[]>`, có thể không export được seed.
- [Java SE 25 — `EdECPublicKey`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPublicKey.html): `getPoint()` và thông tin curve cho khóa công khai.
- [Java SE 25 — `EdECPrivateKeySpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html): spec chứa raw private key material và named parameters.
- [Java SE 25 — `EdECPublicKeySpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPublicKeySpec.html): spec biểu diễn public key bằng `EdECPoint`.
- [Java SE 25 — `Key.getEncoded()/getFormat()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Key.html): khái niệm encoded form, `"X.509"`/`"PKCS#8"` và trường hợp không export được.
- [Java SE 25 — `X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html) và [`PKCS8EncodedKeySpec`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html): import cấu trúc DER, không phải raw bytes.
- [RFC 8032 — EdDSA: Ed25519 and Ed448](https://www.rfc-editor.org/rfc/rfc8032): kích thước raw seed/public, point encoding và quy tắc chữ ký.
- [RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, X448](https://www.rfc-editor.org/rfc/rfc8410): OID, SubjectPublicKeyInfo, private key ASN.1 và cách biểu diễn X.509/PKCS#8.
