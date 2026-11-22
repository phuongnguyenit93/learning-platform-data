# 8.5 Nhập, xuất khóa công khai X.509 SubjectPublicKeyInfo và khóa riêng PKCS#8

## 1. Mục tiêu và phạm vi

Trong Java Cryptography Architecture (JCA), một cặp khóa bất đối xứng có **khóa công khai** (`PublicKey`) và **khóa riêng** (`PrivateKey`). Khóa công khai có thể được phân phối theo quy trình tin cậy; khóa riêng phải được bảo vệ. Để lưu khóa hoặc trao đổi giữa Java, OpenSSL và các hệ thống khác, cần thống nhất **kiểu cấu trúc ASN.1**, **cách mã hóa DER/PEM** và **thuật toán**.

Java sử dụng hai dạng phổ biến:

- **X.509 SubjectPublicKeyInfo (SPKI):** định dạng chuẩn để biểu diễn *khóa công khai*, dùng với `X509EncodedKeySpec` và `KeyFactory.generatePublic(...)`.
- **PKCS#8 PrivateKeyInfo (hoặc dạng khóa riêng phù hợp mà provider chấp nhận):** định dạng chuẩn để biểu diễn *khóa riêng chưa mã hóa*, dùng với `PKCS8EncodedKeySpec` và `KeyFactory.generatePrivate(...)`.

Đây là bài về **mã hóa biểu diễn và nhập/xuất khóa**. Việc có DER hoặc PEM hợp lệ **không tự xác thực danh tính chủ khóa, độ tin cậy, quyền sử dụng, hay trạng thái thu hồi**. PEM chỉ là biểu diễn văn bản Base64 của các byte cấu trúc; `-----BEGIN PRIVATE KEY-----` **không đồng nghĩa khóa đã được mã hóa bảo vệ bằng password**.

Sau bài này, bạn cần có thể tạo khóa RSA/EC bằng `KeyPairGenerator`, xuất cấu trúc chuẩn bằng `getEncoded()`, khôi phục bằng `KeyFactory`, nhận diện đúng PEM header, tránh nhầm PKCS#1/SEC1/PKCS#12/certificate với SPKI hoặc PKCS#8, và biết cách xử lý `ENCRYPTED PRIVATE KEY`.

## 2. Ba tầng cần tách biệt: thuật toán, định dạng nhị phân, dạng văn bản

Một đối tượng Java như `RSAPublicKey` hoặc `ECPrivateKey` mang thông tin toán học của khóa và có thể có provider-specific implementation. Nếu khóa export được, `key.getEncoded()` trả **mảng byte** trong một định dạng chuẩn và `key.getFormat()` thường cho tên dạng chuẩn:

| Đối tượng Java | Định dạng biểu diễn mặc định khi có encoding | Đơn vị lưu trữ |
| --- | --- | --- |
| `PublicKey` RSA/EC/Ed25519 có thể export | X.509, thực chất cấu trúc `SubjectPublicKeyInfo` | DER bytes |
| `PrivateKey` RSA/EC/Ed25519 có thể export | PKCS#8, thực chất `PrivateKeyInfo` hoặc dạng được hỗ trợ | DER bytes |
| `SecretKey` như AES | `RAW` hoặc định dạng/provider khác | Khóa bí mật đối xứng; không áp dụng SPKI/PKCS#8 |
| Key handle trong HSM/PKCS#11 | Có thể `getEncoded() == null` | Vật liệu không được xuất khỏi provider |

**DER** (Distinguished Encoding Rules) là cách mã hóa nhị phân xác định của ASN.1. **PEM** là lớp bao text: header, Base64 của các byte DER, footer. Thay đổi xuống dòng Base64 không làm thay đổi khóa, miễn là decoder lấy lại đúng byte. Trong JCA, `X509EncodedKeySpec(byte[])` và `PKCS8EncodedKeySpec(byte[])` cần **byte DER**, không nhận trực tiếp `String` PEM hay byte của ký tự `-----BEGIN ...`.

Ví dụ về cấu trúc (sơ đồ khái niệm ASN.1, không phải mã nguồn Java):

```text
SubjectPublicKeyInfo ::= SEQUENCE {
    algorithm        AlgorithmIdentifier,
    subjectPublicKey BIT STRING
}

PrivateKeyInfo ::= SEQUENCE {
    version                   INTEGER,
    privateKeyAlgorithm       AlgorithmIdentifier,
    privateKey                OCTET STRING,
    attributes           [0]  IMPLICIT SET OF Attribute OPTIONAL
}
```

`AlgorithmIdentifier` thường chứa OID (object identifier) và có thể có tham số thuật toán. Với EC, tham số có thể xác định named curve; với RSA, algorithm identifier cho biết dạng RSA và tham số theo quy tắc tương ứng. Không được xem chỉ `BIT STRING` chứa điểm EC hoặc một cặp số RSA là *toàn bộ* SPKI: cấu trúc ngoài còn ghi algorithm và tham số để parser hiểu đúng.

Đối với khóa riêng, `privateKey` nằm trong OCTET STRING của PKCS#8; **bên trong** có thể lại chứa định dạng đặc thù thuật toán (ví dụ RSAPrivateKey hay ECPrivateKey). Vì thế “có byte RSA private key bên trong” **khác** “đang cầm một file PKCS#1 trần”. `KeyFactory.generatePrivate(new PKCS8EncodedKeySpec(bytes))` trông đợi **lớp vỏ PKCS#8 đầy đủ**.

RFC 5958 định nghĩa các cấu trúc đời mới liên quan `OneAsymmetricKey` và có thể chứa phần public key tùy chọn. Không mặc định rằng mọi biến thể tùy chọn, trường mở rộng hay mọi encoding từ provider khác đều được Java/provider đang chạy chấp nhận; hãy kiểm thử trên chính môi trường triển khai.

## 3. Nhận diện PEM header chính xác

Một nội dung PEM hợp lệ thường có các dòng:

```text
-----BEGIN PUBLIC KEY-----
<Base64 của DER SubjectPublicKeyInfo>
-----END PUBLIC KEY-----

-----BEGIN PRIVATE KEY-----
<Base64 của DER PKCS#8 PrivateKeyInfo chưa mã hóa>
-----END PRIVATE KEY-----
```

Dòng nằm giữa là **ký hiệu minh họa**, không phải Base64 hợp lệ để copy chạy. Bảng sau đặc biệt quan trọng khi nhận PEM từ OpenSSL, hệ thống Java cũ hoặc các thư viện ngoài:

| Header / loại dữ liệu | Bản chất | Import trực tiếp bằng spec nào? |
| --- | --- | --- |
| `BEGIN PUBLIC KEY` | X.509 SPKI, DER bọc Base64 | Giải mã PEM → `X509EncodedKeySpec` |
| `BEGIN PRIVATE KEY` | PKCS#8 không mã hóa, DER bọc Base64 | Giải mã PEM → `PKCS8EncodedKeySpec` |
| `BEGIN ENCRYPTED PRIVATE KEY` | PKCS#8 `EncryptedPrivateKeyInfo`, có PBE và ciphertext | Cần giải mã đúng thuật toán/password trước, rồi mới `PKCS8EncodedKeySpec` |
| `BEGIN RSA PUBLIC KEY` | RSA `RSAPublicKey` PKCS#1, không có lớp SPKI | **Không** đưa thẳng vào `X509EncodedKeySpec` |
| `BEGIN RSA PRIVATE KEY` | RSA `RSAPrivateKey` PKCS#1, không có lớp PKCS#8 | **Không** đưa thẳng vào `PKCS8EncodedKeySpec` |
| `BEGIN EC PRIVATE KEY` | EC `ECPrivateKey` SEC1 | Cần chuyển/bao thành PKCS#8 hoặc parser được thiết kế riêng |
| `BEGIN CERTIFICATE` | X.509 certificate bao gồm SPKI và metadata/chữ ký | `CertificateFactory` để parse certificate, sau đó `getPublicKey()` |
| `BEGIN CERTIFICATE REQUEST` | Certificate signing request (CSR) | Không phải raw SPKI hay PKCS#8 |
| `BEGIN OPENSSH PRIVATE KEY` | Định dạng OpenSSH riêng | Cần OpenSSH-compatible parser/converter; không phải PKCS#8 |
| `.p12`/`.pfx` | PKCS#12 container (keystore) | Dùng `KeyStore` và password/quyền thích hợp |

**Chữ “X.509” trong `X509EncodedKeySpec` không có nghĩa đối tượng này là certificate.** Certificate X.509 chứa subject/issuer, thời gian hiệu lực, extensions, chữ ký chứng thư và SPKI. `X509EncodedKeySpec` chỉ đại diện SPKI của khóa công khai; nó không có cơ chế xác thực certificate chain.

Một tệp `.der` hay `.pem` chỉ là gợi ý từ tên; phải xác định cấu trúc thực tế theo hợp đồng dữ liệu và parser. Dùng nhầm PEM header, sao chép thừa header/footer vào Base64, hoặc nhầm **PKCS#1** với **PKCS#8** là nguyên nhân phổ biến của `InvalidKeySpecException`.

## 4. Các API Java cần nhớ

| Công việc | API | Giá trị đầu vào/đầu ra |
| --- | --- | --- |
| Sinh cặp khóa | `KeyPairGenerator.getInstance("RSA")` / `"EC"` | `generateKeyPair()` → `PublicKey`, `PrivateKey` |
| Xuất dữ liệu DER | `key.getEncoded()` | `byte[]` hoặc `null` nếu không export được |
| Xem encoding | `key.getFormat()` | Thường `"X.509"` cho public, `"PKCS#8"` cho private khi export được |
| Dựng public spec | `new X509EncodedKeySpec(spkiDer)` | Các byte DER của **SPKI** |
| Dựng private spec | `new PKCS8EncodedKeySpec(privateKeyInfoDer)` | Các byte DER của **PKCS#8 chưa mã hóa** |
| Import public | `KeyFactory.getInstance("RSA").generatePublic(spec)` | `PublicKey` |
| Import private | `KeyFactory.getInstance("RSA").generatePrivate(spec)` | `PrivateKey` |
| Đóng gói PEM | `Base64.getMimeEncoder(64, new byte[]{'\n'})` | Dòng Base64 tối đa 64 ký tự |
| Mở PEM | Kiểm tra nhãn rồi `Base64.getDecoder().decode(body)` | Byte DER trước khi tạo `KeySpec` |
| Import X.509 certificate | `CertificateFactory.getInstance("X.509")` | `X509Certificate` rồi `getPublicKey()` |
| Nhập encrypted PKCS#8 | `EncryptedPrivateKeyInfo` và PBE `Cipher` | Sau khi giải mã: `PKCS8EncodedKeySpec` |

`KeyFactory` được chọn theo **thuật toán khóa** (`"RSA"`, `"EC"`, `"Ed25519"`...), không phải theo PEM header. Cả RSA và EC có thể dùng chung nhãn `BEGIN PUBLIC KEY`; bên trong `AlgorithmIdentifier` mới phân biệt. Nếu biết trước hợp đồng là RSA, dùng `KeyFactory.getInstance("RSA")`; nếu nguồn có thể là nhiều loại, phải xác định thuật toán tin cậy từ metadata/schema hoặc ASN.1 qua thư viện an toàn, chứ không đoán theo phần mở rộng file.

Mặc dù `X509EncodedKeySpec` và `PKCS8EncodedKeySpec` sao chép byte vào key spec, constructor **không phải trình kiểm tra đầy đủ thuật toán**; phân tích và validation chính xảy ra khi `KeyFactory.generatePublic/generatePrivate`. Import có thể ném `InvalidKeySpecException` do sai cấu trúc DER, thuật toán không đúng, tham số sai hoặc key data bất hợp lệ.

## 5. Chương trình chạy được: RSA và EC → SPKI/PKCS#8 → PEM → nhập lại

Chương trình Java 17+ dưới đây thực hiện **hai round-trip**:

1. Sinh RSA-2048 và EC với đường cong `secp256r1` (P-256).
2. Gọi `getEncoded()` để nhận **SPKI DER** của khóa công khai và **PKCS#8 DER** của khóa riêng.
3. Đóng gói từng DER thành PEM chuẩn `PUBLIC KEY` hoặc `PRIVATE KEY` bằng Base64 có xuống dòng 64 ký tự.
4. Kiểm tra header/footer, decode PEM trở lại DER và dùng `KeyFactory` + đúng `EncodedKeySpec` để nhập khóa.
5. Ký một thông điệp bằng private key nhập lại, xác minh bằng public key nhập lại.
6. Thử **đưa PKCS#8 private bytes vào `X509EncodedKeySpec`** để minh họa trường hợp sai cấu trúc bị từ chối.

Lưu thành **`KeyEncodingRoundTripDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public final class KeyEncodingRoundTripDemo {
    private static String toPem(String label, byte[] der) {
        String base64 = Base64.getMimeEncoder(
                64, new byte[] { '\n' }).encodeToString(der);
        return "-----BEGIN " + label + "-----\n"
                + base64 + "\n-----END " + label + "-----\n";
    }

    private static byte[] fromPem(String pem, String expectedLabel) {
        String begin = "-----BEGIN " + expectedLabel + "-----";
        String end = "-----END " + expectedLabel + "-----";
        String normalized = pem.replace("\r\n", "\n").trim();
        if (!normalized.startsWith(begin + "\n")
                || !normalized.endsWith("\n" + end)) {
            throw new IllegalArgumentException("Unexpected PEM type");
        }
        String body = normalized.substring(
                begin.length() + 1,
                normalized.length() - end.length() - 1);
        String base64 = body.replace("\n", "");
        return Base64.getDecoder().decode(base64);
    }

    private static void roundTrip(
            String name, String signatureAlgorithm, KeyPair pair)
            throws Exception {
        byte[] publicDer = pair.getPublic().getEncoded();
        byte[] privateDer = pair.getPrivate().getEncoded();
        if (publicDer == null || privateDer == null) {
            throw new IllegalStateException("Key is not exportable");
        }
        try {
            String publicPem = toPem("PUBLIC KEY", publicDer);
            String privatePem = toPem("PRIVATE KEY", privateDer);

            KeyFactory factory = KeyFactory.getInstance(name);
            PublicKey publicKey = factory.generatePublic(
                    new X509EncodedKeySpec(fromPem(publicPem, "PUBLIC KEY")));
            PrivateKey privateKey = factory.generatePrivate(
                    new PKCS8EncodedKeySpec(fromPem(privatePem, "PRIVATE KEY")));

            byte[] message = "signature test".getBytes(StandardCharsets.UTF_8);
            Signature signer = Signature.getInstance(signatureAlgorithm);
            signer.initSign(privateKey);
            signer.update(message);
            byte[] signature = signer.sign();
            Signature verifier = Signature.getInstance(signatureAlgorithm);
            verifier.initVerify(publicKey);
            verifier.update(message);

            System.out.println(name + " publicFormat=" + pair.getPublic().getFormat());
            System.out.println(name + " privateFormat=" + pair.getPrivate().getFormat());
            System.out.println(name + " publicRoundTrip="
                    + Arrays.equals(publicDer, publicKey.getEncoded()));
            System.out.println(name + " privateRoundTrip="
                    + Arrays.equals(privateDer, privateKey.getEncoded()));
            System.out.println(name + " signatureValid=" + verifier.verify(signature));
        } finally {
            Arrays.fill(publicDer, (byte) 0);
            Arrays.fill(privateDer, (byte) 0);
        }
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator rsa = KeyPairGenerator.getInstance("RSA");
        rsa.initialize(2048);
        KeyPair rsaPair = rsa.generateKeyPair();
        roundTrip("RSA", "SHA256withRSA", rsaPair);

        KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
        ec.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair ecPair = ec.generateKeyPair();
        roundTrip("EC", "SHA256withECDSA", ecPair);

        KeyFactory factory = KeyFactory.getInstance("RSA");
        try {
            factory.generatePublic(new X509EncodedKeySpec(
                    rsaPair.getPrivate().getEncoded()));
            System.out.println("wrongContainerRejected=false");
        } catch (InvalidKeySpecException expected) {
            System.out.println("wrongContainerRejected=true");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 KeyEncodingRoundTripDemo.java
java KeyEncodingRoundTripDemo
```

Kết quả trên OpenJDK hỗ trợ RSA/EC phổ biến:

```text
RSA publicFormat=X.509
RSA privateFormat=PKCS#8
RSA publicRoundTrip=true
RSA privateRoundTrip=true
RSA signatureValid=true
EC publicFormat=X.509
EC privateFormat=PKCS#8
EC publicRoundTrip=true
EC privateRoundTrip=true
EC signatureValid=true
wrongContainerRejected=true
```

Vì mỗi lần chạy sinh khóa mới, **các byte DER và chữ ký thay đổi**, nhưng những phép kiểm tra vẫn cho kết quả trên khi provider hoạt động đúng. Ví dụ chọn RSA-2048 để dễ tương thích; lựa chọn thuật toán/kích thước khóa trong hệ thống mới phải theo yêu cầu bảo mật và thời hạn bảo vệ riêng.

### 5.1 Giải thích các điểm quan trọng của chương trình

**Đúng lớp container:** `toPem("PUBLIC KEY", spkiDer)` đi với `X509EncodedKeySpec`; `toPem("PRIVATE KEY", pkcs8Der)` đi với `PKCS8EncodedKeySpec`. Sai label bị từ chối bởi helper của ví dụ trước khi JCA parse. `wrongContainerRejected=true` đến từ `KeyFactory.generatePublic` không chấp nhận một private-key structure như SPKI.

**PEM helper có phạm vi có chủ đích:** `fromPem` xử lý một PEM block do chính `toPem` tạo ra, dùng newline LF hoặc CRLF, có header/footer chính xác và các dòng Base64 đơn giản. Đây là **parser giáo dục**, không xử lý mọi biến thể PEM thực tế (như nhiều PEM block trong một file, phần comment hoặc metadata lạ, kích thước không giới hạn). Trong sản phẩm, nên dùng parser PEM có kiểm soát về nhãn, số lượng block, encoding, giới hạn byte và validation phù hợp.

**Dấu hiệu encoding:** `getFormat()` thông thường trả `"X.509"` hoặc `"PKCS#8"` cho khóa phần mềm có thể export. Nhưng `getEncoded() == null` vẫn hợp lệ với key handle/provider không cho xuất, và `getFormat()` cũng có thể là `null`. Không lấy provider-specific bytes làm hợp đồng portable nếu không kiểm tra.

**Byte equality vs identity:** khi cùng provider round-trip DER, `Arrays.equals(originalDer, reconstructedKey.getEncoded())` thường cho `true`. Giữa các provider, hai khóa tương đương có thể được mã hóa lại khác nhau về chi tiết hợp lệ; việc *chữ ký tạo bằng private key nhập lại xác minh bằng public key nhập lại* là kiểm tra hành vi có ý nghĩa bổ sung. Đừng dùng phép so byte DER đơn thuần để chứng minh người gửi đáng tin hoặc public key thuộc đúng danh tính.

**Dữ liệu nhạy cảm:** chương trình đưa private bytes vào `byte[]` và PEM `String` trong bộ nhớ để minh họa. `Arrays.fill(privateDer, (byte)0)` chỉ xóa mảng đang giữ, **không thể xóa** mọi bản sao bên trong Java object, PEM `String` và provider. Trong sản phẩm, dùng key handle/kho khóa nếu có, tránh export private key vì mục đích kiểm tra đơn thuần, không in hoặc ghi lại PEM private key.

## 6. Nhập PEM/DER từ file thực

Các phép chuyển đổi cơ bản khi nhận dữ liệu từ file:

```text
public.pem
  -> kiểm tra đúng BEGIN PUBLIC KEY / END PUBLIC KEY
  -> decode Base64 thành DER SubjectPublicKeyInfo
  -> new X509EncodedKeySpec(der)
  -> KeyFactory.getInstance(algorithm).generatePublic(spec)

private.pem
  -> kiểm tra đúng BEGIN PRIVATE KEY / END PRIVATE KEY
  -> decode Base64 thành DER PKCS#8
  -> new PKCS8EncodedKeySpec(der)
  -> KeyFactory.getInstance(algorithm).generatePrivate(spec)

public.der / private.der
  -> dùng byte DER trực tiếp với KeySpec đúng kiểu
```

Ví dụ đọc file bằng thư viện Java chuẩn (đoạn mã **minh họa**, gọi bên trong phương thức đã khai báo exceptions và import):

```java
// public.der chứa đúng SPKI DER, private.der chứa đúng PKCS#8 DER.
byte[] spkiDer = java.nio.file.Files.readAllBytes(
        java.nio.file.Path.of("public.der"));
byte[] privateDer = java.nio.file.Files.readAllBytes(
        java.nio.file.Path.of("private.der"));
try {
    java.security.KeyFactory factory =
            java.security.KeyFactory.getInstance("RSA");

    java.security.PublicKey publicKey = factory.generatePublic(
            new java.security.spec.X509EncodedKeySpec(spkiDer));
    java.security.PrivateKey privateKey = factory.generatePrivate(
            new java.security.spec.PKCS8EncodedKeySpec(privateDer));
    // Dung publicKey/privateKey cho thao tac da duoc phep.
} finally {
    java.util.Arrays.fill(spkiDer, (byte) 0);
    java.util.Arrays.fill(privateDer, (byte) 0);
}
```

`Files.readAllBytes` chỉ thích hợp cho file khóa nhỏ và **đã giới hạn kích thước**. Với file do người dùng cung cấp, giới hạn bytes trước khi đọc, chống file cực lớn và chỉ parse **đúng định dạng**; không tự nhận chuỗi bất kỳ chứa `BEGIN` rồi dùng `replaceAll` xóa tùy tiện. Đối với file PEM, đọc bằng charset ASCII và dùng parser theo header/footer để lấy Base64 body, sau đó mới tạo `KeySpec`; **không** gọi `new PKCS8EncodedKeySpec(Files.readAllBytes("private.pem"))`.

Muốn ghi file DER hay PEM trong ứng dụng thật, phải thiết lập quyền đọc file/private key chặt chẽ **trước khi công bố/đặt vào thư mục có người khác truy cập**. POSIX permissions như `0600` không thể áp dụng y hệt trên Windows; thiết kế bảo vệ file phù hợp ACL, người dùng chạy process và môi trường. Thường nên quản lý private key bằng `KeyStore`, HSM hoặc KMS hơn là plain private.pem.

Nếu nhập **public key từ certificate** thì dùng `CertificateFactory`:

```java
// Đoạn minh họa: certDer là toàn bộ chứng thư DER (không phải SPKI).
java.security.cert.CertificateFactory certificates =
        java.security.cert.CertificateFactory.getInstance("X.509");
java.security.cert.X509Certificate certificate =
        (java.security.cert.X509Certificate) certificates.generateCertificate(
                new java.io.ByteArrayInputStream(certDer));
java.security.PublicKey publicKey = certificate.getPublicKey();
```

**Chỉ parse certificate không tự xác minh niềm tin.** Cần kiểm tra chain, trust anchor, thời gian, constraints, key usage, hostname và revocation theo giao thức sử dụng. `certificate.getPublicKey()` trả khóa công khai từ chứng thư; `certificate.getEncoded()` là encoding **toàn bộ certificate**, không phải SPKI.

## 7. PKCS#8 chưa mã hóa và PKCS#8 đã mã hóa là hai loại khác nhau

`BEGIN PRIVATE KEY` thể hiện **PKCS#8 PrivateKeyInfo chưa mã hóa**. Base64 không làm nó bí mật; bất kỳ ai đọc được file có thể lấy key material.

`BEGIN ENCRYPTED PRIVATE KEY` thể hiện **EncryptedPrivateKeyInfo** có cấu trúc đại ý:

```text
EncryptedPrivateKeyInfo ::= SEQUENCE {
    encryptionAlgorithm AlgorithmIdentifier,
    encryptedData       OCTET STRING
}
```

Để nhập dạng encrypted, phải nhận biết thuật toán PBE và các tham số của nó (ví dụ PBES2, salt, iteration count, cipher parameters), xác thực password theo yêu cầu và giải mã ra **DER PKCS#8 chưa mã hóa**; lúc ấy mới dùng `PKCS8EncodedKeySpec` với `KeyFactory`. Đưa trực tiếp `EncryptedPrivateKeyInfo.getEncoded()` vào `PKCS8EncodedKeySpec` sẽ sai định dạng.

Việc file private-key được bảo vệ bằng password **không đồng nghĩa** có cơ chế xác thực chống sửa hoặc password mạnh. Một số sơ đồ PBE lịch sử yếu, một số sơ đồ PBES2 dùng AES-CBC và phụ thuộc padding/DER validation; cần chính sách thuật toán, password đủ mạnh, kiểm tra định dạng và giới hạn tài nguyên. Password quá yếu có thể bị đoán offline ngay khi kẻ tấn công lấy được bản encrypted PKCS#8.

### 7.1 Chương trình chạy được: bảo vệ và khôi phục PKCS#8 bằng PBE/PBES2

Ví dụ Java 17+ này dùng provider phổ biến có `PBEWithHmacSHA256AndAES_256`, salt ngẫu nhiên và 210.000 vòng lặp **để minh họa API**, không coi đây là tham số bảo mật chuẩn cho mọi tình huống. Thuật toán/`AlgorithmParameters` thực tế phụ thuộc provider; ví dụ làm rõ lớp `PBES2` bên ngoài để `EncryptedPrivateKeyInfo` nhận ASN.1 AlgorithmIdentifier đúng.

Lưu thành **`EncryptedPkcs8Demo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.AlgorithmParameters;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.EncryptedPrivateKeyInfo;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.PBEParameterSpec;

public final class EncryptedPkcs8Demo {
    private static final String PBE = "PBEWithHmacSHA256AndAES_256";

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();
        byte[] original = pair.getPrivate().getEncoded();
        char[] password = "demo-password-only".toCharArray();
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        PBEKeySpec passwordSpec = new PBEKeySpec(password);

        try {
            SecretKeyFactory keyFactory = SecretKeyFactory.getInstance(PBE);
            SecretKey pbeKey = keyFactory.generateSecret(passwordSpec);

            Cipher encrypt = Cipher.getInstance(PBE);
            encrypt.init(Cipher.ENCRYPT_MODE, pbeKey,
                    new PBEParameterSpec(salt, 210_000));
            byte[] ciphertext = encrypt.doFinal(original);

            AlgorithmParameters pbes2 = AlgorithmParameters.getInstance("PBES2");
            pbes2.init(encrypt.getParameters().getEncoded());
            EncryptedPrivateKeyInfo container =
                    new EncryptedPrivateKeyInfo(pbes2, ciphertext);
            EncryptedPrivateKeyInfo parsed =
                    new EncryptedPrivateKeyInfo(container.getEncoded());

            Cipher decrypt = Cipher.getInstance(PBE);
            decrypt.init(Cipher.DECRYPT_MODE, pbeKey,
                    parsed.getAlgParameters());
            PKCS8EncodedKeySpec plain = parsed.getKeySpec(decrypt);
            PrivateKey restored = KeyFactory.getInstance("RSA")
                    .generatePrivate(plain);

            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(restored);
            signer.update("signed data".getBytes(StandardCharsets.UTF_8));
            byte[] signature = signer.sign();

            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(pair.getPublic());
            verifier.update("signed data".getBytes(StandardCharsets.UTF_8));

            System.out.println("encryptedContainerParsed=true");
            System.out.println("restoredMatches="
                    + Arrays.equals(original, restored.getEncoded()));
            System.out.println("signatureValid=" + verifier.verify(signature));
            Arrays.fill(ciphertext, (byte) 0);
        } finally {
            passwordSpec.clearPassword();
            Arrays.fill(password, '\0');
            Arrays.fill(salt, (byte) 0);
            Arrays.fill(original, (byte) 0);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 EncryptedPkcs8Demo.java
java EncryptedPkcs8Demo
```

```text
encryptedContainerParsed=true
restoredMatches=true
signatureValid=true
```

**Điểm học được:** `EncryptedPrivateKeyInfo` chứa metadata của sơ đồ bảo vệ và ciphertext. `getKeySpec(decrypt)` chỉ tạo `PKCS8EncodedKeySpec` **sau khi Cipher giải mã**. Đến `KeyFactory.generatePrivate` ta mới nhận `PrivateKey` có thể sử dụng. Không truyền private key trong phần hiển thị hoặc log; các biểu thức `Arrays.equals(...)` ở đây chỉ kiểm tra dữ liệu nội bộ.

**Giới hạn của ví dụ:** password cứng trong code chỉ là demo; sử dụng input mật khẩu an toàn và chính sách chống đoán thật. Phần `PBES2` + `PBEWithHmacSHA256AndAES_256` được kiểm thử với OpenJDK hỗ trợ các tên này; provider/phiên bản khác có thể cần bộ mã hóa PKCS#8 từ thư viện đã đánh giá hoặc `KeyStore`/KMS. `PBEWithHmacSHA256AndAES_256` mô tả KDF PRF HMAC-SHA256 và AES encryption; **không có nghĩa ciphertext có HMAC xác thực độc lập**. Với file khóa có độ nhạy cao, cân nhắc kho khóa được bảo vệ đúng chính sách, không tự thiết kế private-key file encryption protocol.

## 8. Chuyển đổi từ các định dạng phổ biến bằng công cụ chuyên dụng

Khi nhận key RSA ở `BEGIN RSA PRIVATE KEY` (PKCS#1) hoặc EC ở `BEGIN EC PRIVATE KEY` (SEC1), **không** thay tên header thành `BEGIN PRIVATE KEY` rồi giữ nguyên Base64: đổi header không đổi cấu trúc ASN.1. Phải tạo **lớp vỏ PKCS#8** bằng công cụ/thư viện hiểu thuật toán.

Ví dụ lệnh OpenSSL (lệnh minh họa cho môi trường có OpenSSL cài sẵn; hãy thay tên đường dẫn và bảo vệ tệp khóa riêng theo chính sách):

```bash
# Chuyển khóa riêng RSA PKCS#1 hoặc EC SEC1 sang PKCS#8 chưa mã hóa.
openssl pkcs8 -topk8 -nocrypt -in legacy-private.pem -out private-pkcs8.pem

# Xuất public SPKI từ một private key được OpenSSL nhận diện.
openssl pkey -in private-pkcs8.pem -pubout -out public-spki.pem

# Kiểm tra nội dung cấu trúc mà không in khóa riêng ra log:
openssl pkey -in private-pkcs8.pem -noout -text_pub
```

Lệnh chuyển sang `-nocrypt` tạo **private key chưa mã hóa**, rất nhạy cảm: dùng vị trí tạm được giới hạn quyền, xóa có kiểm soát theo mô hình lưu trữ và ưu tiên chuyển đổi ở môi trường an toàn. Tùy phiên bản OpenSSL, option `-text_pub` có thể không hỗ trợ trong tổ hợp trên; kiểm tra `openssl pkey -help` cho phiên bản cụ thể. Để tạo encrypted PKCS#8, cần công cụ cấu hình PBE an toàn và chính sách password phù hợp; việc dùng `-nocrypt` là **mở khóa thô**.

**Không** nghĩ rằng mọi lệnh xuất `openssl rsa -pubout` hay `openssl pkey -pubout` sẽ luôn tạo PEM có cùng nhãn trong mọi chế độ/phiên bản/flag; hãy **đọc header thực tế** và xác nhận cấu trúc SPKI. Các loại `RSA PUBLIC KEY` truyền thống là PKCS#1, khác `PUBLIC KEY` SPKI.

Nếu muốn trao đổi cặp khóa trong một container bảo vệ, Java `KeyStore` với PKCS12 có thể phù hợp hơn file PEM riêng rẽ; định dạng PKCS#12 bao gồm nhiều entry, certificate chain và cơ chế bảo vệ, **không phải byte PKCS#8** để đưa trực tiếp vào `PKCS8EncodedKeySpec`.

## 9. Những lỗi dễ gặp khi nhập hoặc xuất khóa

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `InvalidKeySpecException`: cannot parse key | Đưa PKCS#1, SEC1, certificate, CSR hoặc sai DER vào X.509/PKCS#8 spec | Xác định cấu trúc thật; convert đúng định dạng trước |
| `InvalidKeySpecException`: algorithm mismatch | `KeyFactory("RSA")` nhận khóa EC/Ed25519, hoặc OID/params không phù hợp | Chọn algorithm từ giao thức/metadata đáng tin và provider hỗ trợ |
| `IllegalArgumentException` khi decode Base64 | Copy header/footer cùng body, ký tự lạ, thiếu Base64 | Parse PEM đúng label, decode body, áp dụng giới hạn kích thước |
| `getEncoded() == null` | Key không export được (HSM/token/provider) | Dùng `Key` trực tiếp trong provider, không tạo bytes giả |
| `NoSuchAlgorithmException` | Runtime/provider không có `RSA`/`EC`/PBE algorithm | Kiểm tra provider, JDK, tên thuật toán và tương thích triển khai |
| `InvalidKeyException` hoặc `SignatureException` khi ký | Khóa sai loại, sai chế độ, tham số signature không tương thích | Dùng đúng private/public, signature algorithm và tham số |
| `BadPaddingException` / lỗi giải mã encrypted PKCS#8 | Password, cipher parameters hoặc ciphertext sai | Từ chối khóa, xử lý lỗi thống nhất, không trả ra raw secret |
| Import certificate dưới dạng public DER | `certificate.getEncoded()` là toàn bộ X.509 certificate | Dùng `CertificateFactory` rồi `cert.getPublicKey()` |
| Nhập `BEGIN OPENSSH PRIVATE KEY` bằng PKCS#8 | OpenSSH container khác ASN.1 PKCS#8 | Convert hoặc parser đúng OpenSSH |
| Có private key DER nhưng không biết key type | PEM `PRIVATE KEY` là nhãn chung | Dựa vào ASN.1 algorithm identifier / contract, không đoán tên file |
| Chữ ký được tạo nhưng kiểm tra không hợp lệ | Key pair không cùng cặp, message khác, encoding khác hoặc signature params khác | Kiểm tra dữ liệu ký/verify byte-for-byte và đúng key |

**Không dùng việc parser đọc thành công làm bằng chứng tin cậy.** Với public key nhận từ người khác, cần quy trình gắn khóa với danh tính: certificate chain, fingerprint đã xác thực qua kênh khác, pinned public key, hoặc cơ chế định danh của giao thức. Với private key, cần kiểm tra người/ứng dụng được phép truy cập, backup, rotation, nhật ký truy cập và bảo vệ lưu trữ. Đọc file khóa riêng do người khác cung cấp luôn cần giới hạn kích thước, parse errors nhất quán và không tiết lộ dữ liệu nhạy cảm.

## 10. Những hiểu lầm quan trọng

- **“Có X.509 public key là đã có X.509 certificate.”** Không. SPKI chỉ là cấu trúc chứa public key và algorithm identifier; certificate còn có identity, issuer, validity và chữ ký.
- **“PKCS#8 là thuật toán khóa riêng.”** Không. Nó là **container** cho nhiều thuật toán; RSA/EC/Ed25519 là các thuật toán khác nhau.
- **“PEM đã mã hóa.”** Không mặc định. `BEGIN PRIVATE KEY` là unencrypted PKCS#8; `BEGIN ENCRYPTED PRIVATE KEY` mới nói tới lớp bảo vệ encrypted PKCS#8.
- **“Bỏ header Base64 rồi gọi KeyFactory với mọi loại private key.”** Không. Decode chỉ trả bytes của format gốc, không chuyển PKCS#1/SEC1 thành PKCS#8.
- **“Vì có Base64, tôi dùng String.getBytes() để tạo KeySpec.”** Không. Phải Base64 decode thành bytes DER gốc.
- **“Cứ RSA thì `KeyFactory("RSA")` có thể đọc certificate/PKCS#1 tùy ý.”** Không. Algorithm và container format đều phải phù hợp.
- **“Lưu PEM private key ở file ứng dụng là luôn an toàn.”** Không. Cần quản lý quyền truy cập, mã hóa bảo vệ khi phù hợp, KMS/HSM và chính sách vòng đời.
- **“getEncoded() luôn có bytes.”** Không. Provider có thể giữ key không thể export; `null` là trường hợp API hợp lệ.
- **“Đổi nhãn PKCS#1 thành PKCS#8 là đủ.”** Không. Phải chuyển cấu trúc ASN.1 bằng converter phù hợp.
- **“Import được public key là có thể tin và sử dụng ngay.”** Không. Nguồn khóa và danh tính cần được xác minh theo giao thức.

## 11. Câu hỏi tự kiểm tra

1. `X509EncodedKeySpec` chứa đối tượng ASN.1 nào? **`SubjectPublicKeyInfo`**, bao gồm algorithm identifier và public key bits.
2. `PKCS8EncodedKeySpec` thường dùng byte của dạng nào? **PKCS#8 PrivateKeyInfo chưa mã hóa**.
3. `BEGIN RSA PRIVATE KEY` là PKCS#8 không? **Không**; thường là PKCS#1 RSA private structure.
4. `BEGIN PUBLIC KEY` và `BEGIN CERTIFICATE` có thay thế trực tiếp cho nhau không? **Không**; một là SPKI, một là certificate đầy đủ.
5. PEM khác DER thế nào? **PEM là text armor Base64 + nhãn; DER là bytes ASN.1**.
6. Muốn import RSA public DER SPKI, hai API chính là gì? **`new X509EncodedKeySpec(der)` và `KeyFactory.getInstance("RSA").generatePublic(...)`**.
7. Nếu private key ở dạng `ENCRYPTED PRIVATE KEY`, có dùng `PKCS8EncodedKeySpec` ngay không? **Không**; phải parse/decrypt `EncryptedPrivateKeyInfo` trước.
8. `getEncoded() == null` có phải key hỏng không? **Không**; có thể là key không cho phép export.
9. Vì sao import public key thành công chưa chứng minh danh tính? Vì **key bytes không tự mang quan hệ tin cậy với người sở hữu**; cần certificate/chain/pinning/quy trình xác thực.
10. Một private key RSA PKCS#1 chuyển thành PKCS#8 bằng cách đổi PEM header có hợp lệ không? **Không**; cần chuyển cấu trúc DER thực sự.
11. Test `Arrays.equals(original.getEncoded(), restored.getEncoded())` thành công có đủ chứng minh mọi thứ? **Không**; còn cần test cryptographic operations, nguồn key, storage và provider.
12. Khi xuất PEM private key, điều cần kiểm soát đầu tiên là gì? **Không rò rỉ private key**, bảo vệ quyền file/memory, tránh log/backup ngoài ý muốn và quản lý vòng đời.

## Tài liệu chuẩn và API Java SE 21

- [X509EncodedKeySpec: SubjectPublicKeyInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html)
- [PKCS8EncodedKeySpec](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html)
- [KeyFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyFactory.html)
- [KeyPairGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyPairGenerator.html)
- [Key.getEncoded/getFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Key.html)
- [EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html)
- [CertificateFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertificateFactory.html)
- [Java KeyStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html)
- [RFC 5280: X.509 Public Key Infrastructure, SubjectPublicKeyInfo](https://www.rfc-editor.org/rfc/rfc5280.html)
- [RFC 5958: Asymmetric Key Packages / PKCS#8](https://www.rfc-editor.org/rfc/rfc5958.html)
- [RFC 7468: PKIX Textual Encodings (PEM)](https://www.rfc-editor.org/rfc/rfc7468.html)
