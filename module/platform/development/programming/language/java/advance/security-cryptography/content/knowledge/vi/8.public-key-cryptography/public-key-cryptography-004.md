# 8.4 Chuyển đổi khóa bằng KeyFactory và KeySpec

Trong Java Cryptography Architecture (JCA), thuật toán bất đối xứng làm việc với `PublicKey` và `PrivateKey`, nhưng khóa có thể xuất hiện dưới nhiều hình thức: đối tượng do provider tạo ra, thành phần toán học (như modulus/exponent của RSA), mảng byte DER, hoặc chuỗi PEM trong tệp cấu hình. **`KeyFactory`** là API dùng để dựng đối tượng khóa từ **`KeySpec`**, lấy một đặc tả phù hợp từ khóa và chuyển khóa giữa các dạng mà provider hỗ trợ. Nắm chắc ranh giới giữa ba thứ — **key object**, **key specification** và **encoding** — giúp tránh nhập sai định dạng, nhầm public/private key, làm lộ khóa riêng hoặc cho rằng việc giải mã DER đã xác thực được nguồn khóa.

Bài học tập trung vào API Java 17+ cho **khóa công khai và khóa riêng bất đối xứng**. Các ví dụ tạo khóa tạm thời trong bộ nhớ để kiểm chứng round-trip bằng RSA, EC, Ed25519 và PEM; phần vận hành giải thích các trường hợp khóa không được phép xuất, chứng chỉ, provider và lỗi đầu vào.

## 1. Bốn loại đối tượng cần phân biệt

| Thành phần | Java API | Vai trò | Điều không nên suy diễn |
| --- | --- | --- | --- |
| **Đối tượng khóa** | `Key`, `PublicKey`, `PrivateKey` | Đối tượng mà `Signature`, `Cipher`, `KeyAgreement` hoặc API khác có thể sử dụng theo thuật toán | Một `Key` không nhất thiết cho phép xuất vật liệu khóa bằng `getEncoded()`. |
| **Đặc tả khóa** | `KeySpec` và các lớp triển khai | Mô tả dữ liệu dùng để dựng khóa hoặc một biểu diễn được trích ra từ khóa | `KeySpec` không đồng nghĩa key đã được provider chấp nhận hay được bảo vệ khỏi đọc. |
| **Bộ chuyển đổi** | `KeyFactory` | `KeySpec → Key`, `Key → KeySpec`, `Key → Key` qua `translateKey` | Không tạo cặp khóa ngẫu nhiên, không thực hiện chữ ký, không kiểm tra danh tính chủ sở hữu. |
| **Bộ sinh cặp khóa** | `KeyPairGenerator` | Sinh cặp `PublicKey`/`PrivateKey` mới từ tham số thuật toán | Không phải công cụ nhập một khóa đã tồn tại từ DER/PEM. |

Luồng dữ liệu hay gặp:

```text
      KeyPairGenerator("RSA")                 tệp/public API
                |                                  |
                v                                  v
        KeyPair(PublicKey, PrivateKey)         DER/PEM bytes
                |                                  |
         getEncoded()                                |
                |                                  v
          DER byte arrays             X509EncodedKeySpec (public)
                |                      PKCS8EncodedKeySpec (private)
                |                                  |
                v                                  v
     X509EncodedKeySpec                     KeyFactory("RSA")
     PKCS8EncodedKeySpec                      generatePublic
                |                            generatePrivate
                +--------------+-------------------+
                               |
                  PublicKey / PrivateKey
                               |
                       Signature / Cipher
```

**Tên thuật toán phải khớp**: `KeyFactory.getInstance("RSA")` xử lý khóa RSA; `KeyFactory.getInstance("EC")` xử lý khóa elliptic curve theo provider hỗ trợ; `KeyFactory.getInstance("Ed25519")` dành cho Ed25519 trên JDK phù hợp. `KeyFactory` không nhận tên phép ký như `SHA256withRSA` hay `SHA256withECDSA`: đó là tên dùng cho `Signature`, không phải tên factory của khóa.

### 1.1 Key khác SecretKey

`Key` là interface chung, nhưng `KeyFactory` thuộc luồng **khóa bất đối xứng** (`PublicKey`/`PrivateKey`). Đối với khóa bí mật có thể dẫn xuất từ các `KeySpec` như `PBEKeySpec`, Java có **`SecretKeyFactory`** và các cơ chế khóa đối xứng riêng. Đừng lấy `KeyFactory.getInstance("AES")` để nhập một mảng byte AES; nếu chính sách cho phép một khóa AES raw, luồng JCE thường dùng `SecretKeySpec` hoặc KeyGenerator/KMS thích hợp.

## 2. API chính của KeyFactory

```java
// Những dòng dưới đây chỉ minh họa chữ ký API và luồng sử dụng;
// key, spec, providerName phải được tạo/nhận trong chương trình thật.
KeyFactory factory = KeyFactory.getInstance("RSA");
PublicKey publicKey = factory.generatePublic(publicKeySpec);
PrivateKey privateKey = factory.generatePrivate(privateKeySpec);
RSAPublicKeySpec rsaSpec =
        factory.getKeySpec(publicKey, RSAPublicKeySpec.class);
Key translated = factory.translateKey(publicKey);
```

Các phương thức cốt lõi:

| Lời gọi | Đầu vào | Đầu ra / ngoại lệ chính |
| --- | --- | --- |
| `KeyFactory.getInstance("RSA")` | Tên thuật toán của **key factory** | `KeyFactory`; có thể ném `NoSuchAlgorithmException` nếu không có implementation. |
| `KeyFactory.getInstance("RSA", "providerName")` | Thuật toán và tên provider đã đăng ký | Có thể ném `NoSuchProviderException` nếu tên provider không tồn tại, hoặc `NoSuchAlgorithmException` nếu provider không hỗ trợ. |
| `generatePublic(KeySpec)` | Đặc tả public key thích hợp | `PublicKey`, hoặc `InvalidKeySpecException`. |
| `generatePrivate(KeySpec)` | Đặc tả private key thích hợp | `PrivateKey`, hoặc `InvalidKeySpecException`. |
| `getKeySpec(Key, Class<T>)` | Đối tượng khóa và **lớp** KeySpec mong muốn | Một `T extends KeySpec`, hoặc `InvalidKeySpecException` nếu không thể biểu diễn/chuyển đổi. |
| `translateKey(Key)` | Đối tượng khóa có thể đến từ provider khác | Đối tượng `Key` do factory/provider xử lý, hoặc `InvalidKeyException`. |
| `getProvider()` | Không có | Provider đang đứng sau factory; hữu ích khi chẩn đoán môi trường. |

Hướng đi chính:

```text
spec  --generatePublic/generatePrivate-->  key
key   --getKeySpec(Class<T>)----------->  spec
key   --translateKey------------------->  key của provider/factory đích
```

`translateKey` **không** biến thuật toán RSA thành EC, không suy ra private key từ public key và không bảo đảm xuất được khóa HSM sang bộ nhớ Java. Nó chỉ chuyển một đối tượng khóa **tương thích** về biểu diễn/provider mà factory hỗ trợ, nếu được phép.

Tùy implementation/provider, có thể tồn tại nhiều `KeySpec` hợp lệ cho cùng một khóa. Việc chọn `X509EncodedKeySpec.class` hoặc `RSAPublicKeySpec.class` nói với factory **hình thức kết quả muốn nhận**, không yêu cầu factory tạo một cặp khóa mới.

## 3. KeySpec có hai nhóm hữu ích

### 3.1 EncodedKeySpec: khóa dưới dạng byte có cấu trúc

Hai lớp thông dụng:

| Lớp | Đầu vào mong đợi | `getFormat()` | Dùng để |
| --- | --- | --- | --- |
| `X509EncodedKeySpec` | DER của **SubjectPublicKeyInfo** (SPKI) trong X.509 | `"X.509"` | Dựng **public key** bằng `generatePublic`. |
| `PKCS8EncodedKeySpec` | DER của **PrivateKeyInfo/PKCS #8** không được mã hóa ở lớp bao ngoài | `"PKCS#8"` | Dựng **private key** bằng `generatePrivate`. |

Cả hai đều triển khai `KeySpec` qua `EncodedKeySpec`. Constructor chấp nhận `byte[]`; **việc tạo spec chưa chứng minh DER đúng**. Provider thường giải mã và kiểm tra tính phù hợp của cấu trúc khi gọi `generatePublic`/`generatePrivate`. Nếu DER không hợp lệ, sai thuật toán hoặc không hỗ trợ, thường nhận `InvalidKeySpecException`.

Một khóa RSA được biểu diễn dưới dạng SPKI (public) có **lớp bao AlgorithmIdentifier** để định danh thuật toán và BIT STRING chứa phần dữ liệu khóa. PKCS #8 cho private key có cấu trúc và metadata thuật toán tương ứng. Vì vậy, dù cả hai đều là byte arrays, **không thể hoán đổi** `X509EncodedKeySpec` và `PKCS8EncodedKeySpec`.

### 3.2 TransparentKeySpec: thành phần toán học

Ví dụ RSA:

- `RSAPublicKeySpec`: số nguyên lớn `modulus` (`n`) và `publicExponent` (`e`), cùng optional algorithm parameters theo API.
- `RSAPrivateKeySpec`: `modulus` (`n`) và `privateExponent` (`d`), có thể không chứa đầy đủ thành phần tối ưu CRT.
- `RSAPrivateCrtKeySpec`: chứa các thông số RSA CRT (`p`, `q`, `dP`, `dQ`, `qInv`...) phục vụ biểu diễn khóa riêng đầy đủ.
- Các thuật toán khác có spec tương ứng, ví dụ `ECPublicKeySpec`, `ECPrivateKeySpec`; những tham số đường cong/điểm phải hợp lệ với thuật toán và provider.

Mô tả toán học hữu ích khi tích hợp định dạng chuyên biệt hoặc đối chiếu thành phần khóa. Tuy nhiên, **các `BigInteger` của khóa riêng là dữ liệu bí mật**. Không in ra log, JSON, exception message hay telemetry; không copy thủ công private key components giữa hệ thống nếu không có lý do và kiểm soát rõ ràng.

### 3.3 Opaque Key và KeySpec

Theo JCA, `Key` có `getAlgorithm()`, `getFormat()`, `getEncoded()`. Nhưng **không phải mọi khóa trả encoding**:

- `getFormat()` có thể trả `null` khi khóa không có định dạng xuất được.
- `getEncoded()` có thể trả `null` (ví dụ khóa nằm trong HSM, smart card hoặc hardware-backed keystore).
- `getKeySpec` cũng có thể **bị từ chối** nếu provider không cho xuất vật liệu khóa tương ứng.
- `translateKey` có thể ném `InvalidKeyException` khi khóa không thể chuyển sang provider đích.

Không dùng `Objects.requireNonNull(privateKey.getEncoded())` rồi tự ghi private key ra tệp như một cách xử lý mặc định. Khi thao tác với HSM/KMS, thường **giữ khóa tại provider** và thực hiện ký/giải mã theo capability được phép. Việc không thể xuất khóa riêng là tính chất bảo mật cần tôn trọng.

## 4. DER, PEM, X.509, PKCS #8 và các dạng dễ nhầm

### 4.1 DER là bytes, PEM là vỏ văn bản

**DER** là cách mã hóa nhị phân xác định của ASN.1. **PEM** thường trình bày DER ở dạng Base64 nằm giữa các nhãn `-----BEGIN ...-----` / `-----END ...-----`. Chuyển PEM sang DER là **bóc header/footer và decode Base64**, không phải giải mã mật mã.

Ví dụ nhãn PEM:

```text
-----BEGIN PUBLIC KEY-----
(Base64 cua SubjectPublicKeyInfo DER)
-----END PUBLIC KEY-----
```

```text
-----BEGIN PRIVATE KEY-----
(Base64 cua PKCS #8 khong ma hoa)
-----END PRIVATE KEY-----
```

Các ví dụ trên minh họa **cấu trúc nhãn**, không phải khóa thật và không thể mang đi chạy. Nội dung `PRIVATE KEY` vẫn là bí mật **dù được Base64 hóa**, cần bảo vệ như khóa gốc.

| Nhãn/nguồn dữ liệu | Thường đại diện | Có thể đưa trực tiếp vào `X509EncodedKeySpec` hoặc `PKCS8EncodedKeySpec`? |
| --- | --- | --- |
| `BEGIN PUBLIC KEY` | SPKI DER sau Base64 decode | **Có**, `X509EncodedKeySpec` nếu thuật toán phù hợp. |
| `BEGIN PRIVATE KEY` | PKCS #8 private-key DER chưa mã hóa ở lớp bao ngoài | **Có**, `PKCS8EncodedKeySpec` nếu thuật toán phù hợp. |
| `BEGIN RSA PUBLIC KEY` | RSA public key theo cấu trúc PKCS #1 (chỉ `n`, `e`) | **Không trực tiếp** vào X.509 SPKI; cần parser/chuyển đổi cấu trúc. |
| `BEGIN RSA PRIVATE KEY` | RSA private key theo PKCS #1 | **Không trực tiếp** vào `PKCS8EncodedKeySpec`; cần parser/chuyển đổi hợp lệ hoặc công cụ xuất lại thành PKCS #8. |
| `BEGIN EC PRIVATE KEY` | SEC1 `ECPrivateKey` | **Không trực tiếp** vào PKCS #8; cần chuyển định dạng và tham số đường cong đúng. |
| `BEGIN ENCRYPTED PRIVATE KEY` | PKCS #8 **được mã hóa** ở lớp bao ngoài | **Không trực tiếp**. Phải giải mã lớp bảo vệ bằng password/key và API/thư viện phù hợp trước khi dựng private key. |
| `BEGIN CERTIFICATE` | Chứng chỉ X.509 chứa nhiều trường và chữ ký CA, bên trong có SPKI public key | **Không trực tiếp** vào `X509EncodedKeySpec`. Dùng `CertificateFactory` parse certificate rồi lấy `getPublicKey()`; việc **xác thực chain/trust** là bước riêng. |

Cần phân biệt **`X509EncodedKeySpec` và `X509Certificate`**: spec chỉ chứa public-key encoding SPKI; certificate chứa thêm subject, issuer, validity, extensions và chữ ký. Parse public key từ SPKI **không** chứng minh người gửi hay chủ sở hữu khóa là ai.

### 4.2 PKCS #8 không đồng nghĩa khóa đã được mã hóa bảo vệ

Tên `PKCS8EncodedKeySpec` mô tả **cấu trúc private key**, không có nghĩa nó tự mã hóa bằng mật khẩu. Private key trong `BEGIN PRIVATE KEY` thường chỉ được **đóng gói**, không được bảo vệ bằng encryption ở lớp file. `BEGIN ENCRYPTED PRIVATE KEY` là một cấu trúc khác, liên quan `EncryptedPrivateKeyInfo` và quy trình giải mã an toàn.

Vì vậy:

- Không gửi tệp `PRIVATE KEY` qua email/chat/log chỉ vì nó có dạng PEM hoặc Base64.
- Không ghi string PEM private key trong source, cấu hình công khai hoặc artifact build.
- Khi cần lưu khóa lâu dài, cân nhắc Java `KeyStore`, keystore phần cứng, KMS/HSM và quyền truy cập thay vì tự viết parser và lưu private key thô.
- Mật khẩu bảo vệ keyfile không tự bảo đảm chống truy cập trái phép nếu ứng dụng còn lộ khóa sau khi giải mã vào RAM.

## 5. Ví dụ Java 17+: RSA KeyFactory round-trip và KeySpec toán học

Ví dụ sinh cặp RSA 2048 bit bằng `KeyPairGenerator`, xuất **SPKI DER** cho public key và **PKCS #8 DER** cho private key, dựng lại bằng `KeyFactory`, lấy `RSAPublicKeySpec`, rồi ký/xác minh để chứng minh các đối tượng khóa thực sự tương ứng.

Lưu tệp **`RsaKeyConversionDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.*;
import java.security.spec.*;
import java.util.*;

public final class RsaKeyConversionDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair original = generator.generateKeyPair();

        byte[] publicDer = original.getPublic().getEncoded();
        byte[] privateDer = original.getPrivate().getEncoded();

        KeyFactory factory = KeyFactory.getInstance("RSA");
        PublicKey restoredPublic =
                factory.generatePublic(new X509EncodedKeySpec(publicDer));
        PrivateKey restoredPrivate =
                factory.generatePrivate(new PKCS8EncodedKeySpec(privateDer));

        RSAPublicKeySpec math =
                factory.getKeySpec(restoredPublic, RSAPublicKeySpec.class);
        PublicKey fromMath = factory.generatePublic(math);
        Key translated = factory.translateKey(restoredPublic);

        Signature signature = Signature.getInstance("SHA256withRSA");
        byte[] data =
                "KeyFactory lesson".getBytes(StandardCharsets.UTF_8);
        signature.initSign(restoredPrivate);
        signature.update(data);
        byte[] signed = signature.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(fromMath);
        verifier.update(data);

        System.out.println("Public format: "
                + original.getPublic().getFormat());
        System.out.println("Private format: "
                + original.getPrivate().getFormat());
        System.out.println("Public key round-trip: "
                + Arrays.equals(publicDer, restoredPublic.getEncoded()));
        System.out.println("RSA modulus bits: "
                + math.getModulus().bitLength());
        System.out.println("RSA verify: " + verifier.verify(signed));
        System.out.println("Translated algorithm: "
                + translated.getAlgorithm());

        Arrays.fill(privateDer, (byte) 0);
    }
}
```

```bash
javac -encoding UTF-8 RsaKeyConversionDemo.java
java RsaKeyConversionDemo
```

Với JDK thông dụng có RSA KeyFactory và `SHA256withRSA`:

```text
Public format: X.509
Private format: PKCS#8
Public key round-trip: true
RSA modulus bits: 2048
RSA verify: true
Translated algorithm: RSA
```

**Phân tích cụ thể:**

1. `KeyPairGenerator` **sinh** khóa mới. `KeyFactory` **phục hồi/chuyển** khóa đã có; hai API khác mục đích.
2. `getEncoded()` trả về DER của khóa mà provider cho phép xuất; ví dụ dùng khóa phần mềm có thể export. Đừng giả định mã private key luôn tồn tại dưới dạng byte.
3. `new X509EncodedKeySpec(publicDer)` và `new PKCS8EncodedKeySpec(privateDer)` chọn **đúng spec cho đúng loại khóa**.
4. `generatePublic`/`generatePrivate` dựng lại key object từ spec. Kết quả kiểm tra ký/xác minh thành công chứng tỏ cặp tương ứng; nó **không** chứng minh khóa đó thuộc về một danh tính bên ngoài.
5. `getKeySpec(restoredPublic, RSAPublicKeySpec.class)` lấy hai thành phần toán học RSA `n` và `e`; `generatePublic(math)` dựng public key từ các thành phần này.
6. `translateKey(restoredPublic)` chuyển key thành đối tượng tương thích với factory đang dùng, ở đây vẫn là RSA. Provider được chọn mặc định nên ví dụ **không** chứng minh chuyển khóa giữa hai provider cụ thể.
7. `Arrays.equals(publicDer,...)` cho kết quả `true` với implementation thử nghiệm, nhưng **không nên dùng việc byte encoding giống hệt** làm contract liên provider cho mọi thuật toán. Chức năng xác minh chữ ký và thông số toán học phù hợp mới phản ánh hành vi khóa cần dùng.
8. `Arrays.fill(privateDer, 0)` xóa **mảng DER do chương trình sở hữu**, không xóa mọi bản sao bên trong `PKCS8EncodedKeySpec`, đối tượng `PrivateKey`, chữ ký hoặc provider. Ví dụ xuất private key chỉ để học; không ghi `privateDer`, modulus bí mật/CRT hay private PEM vào stdout.

**RSA 2048** là cỡ khóa ví dụ để chạy nhanh; cỡ khóa, padding/chế độ chữ ký (ví dụ RSA-PSS với `Signature`), quy tắc chứng chỉ và lifetime phải theo chính sách cụ thể. `KeyFactory` không quyết định liệu thuật toán ký hay cỡ khóa có đáp ứng yêu cầu bảo mật nghiệp vụ.

## 6. `RSAPublicKeySpec` có ích khi nào?

Giả sử một protocol đáng tin cung cấp hai số RSA `n` và `e` dưới dạng chuẩn đã kiểm tra. Có thể dựng một `RSAPublicKeySpec` từ chúng:

```java
// Minh họa trong phương thức đã khai báo throws GeneralSecurityException.
// n và e là BigInteger hợp lệ lấy từ input đã parse/validate.
RSAPublicKeySpec spec = new RSAPublicKeySpec(n, e);
PublicKey publicKey = KeyFactory.getInstance("RSA").generatePublic(spec);
```

Đây là **đoạn minh họa, không phải chương trình độc lập**: `n`, `e` chưa được khai báo. Nó trình bày quan hệ `RSAPublicKeySpec → PublicKey`. Khi tích hợp thực tế:

- Kiểm tra định dạng và giới hạn độ dài serialized input trước khi tạo `BigInteger`; không để input cực lớn làm tăng tiêu thụ bộ nhớ/CPU.
- Kiểm tra modulus, exponent, cỡ khóa và tính hợp lệ theo chính sách. `KeyFactory.generatePublic` có thể từ chối key spec, nhưng provider không thay thế toàn bộ validation/trust policy của giao thức.
- Không nhầm `RSAPublicKeySpec` với chứng chỉ CA, khóa công khai gắn danh tính hoặc chữ ký hợp lệ. Chỉ dựng được key object không đồng nghĩa nguồn key là đáng tin.
- Không copy mẫu với `RSAPrivateKeySpec` rồi lưu `d`, `p`, `q` ra JSON/console. Thành phần RSA private phải được xử lý như vật liệu khóa bí mật.

Nếu input đã là DER SPKI tiêu chuẩn, **ưu tiên `X509EncodedKeySpec`** thay vì tự parse ASN.1 để lấy `n`/`e`. Điều này tránh sai sót về length, thuật toán/parameters và định dạng.

## 7. Ví dụ Java 17+: EC và Ed25519 cũng dùng KeyFactory

`X509EncodedKeySpec` và `PKCS8EncodedKeySpec` là **các lớp bao định dạng**, không chỉ dành cho RSA. Nhiều thuật toán public-key khác có thể dùng chúng nếu implementation JDK/provider hỗ trợ và các byte chứa đúng algorithm identifier.

Ví dụ sau tạo khóa EC với `secp256r1` và Ed25519; dựng lại rồi kiểm tra chữ ký. Nó cũng cố đưa EC public key vào RSA KeyFactory để minh họa **sai thuật toán**.

Lưu thành **`EcEdKeyConversionDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.*;

public final class EcEdKeyConversionDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        byte[] data =
                "Open standard key formats".getBytes(StandardCharsets.UTF_8);

        KeyPairGenerator ecGen = KeyPairGenerator.getInstance("EC");
        ecGen.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair ecPair = ecGen.generateKeyPair();

        KeyFactory ecFactory = KeyFactory.getInstance("EC");
        PublicKey ecPublic = ecFactory.generatePublic(
                new X509EncodedKeySpec(ecPair.getPublic().getEncoded()));
        PrivateKey ecPrivate = ecFactory.generatePrivate(
                new PKCS8EncodedKeySpec(ecPair.getPrivate().getEncoded()));

        Signature ecSigner = Signature.getInstance("SHA256withECDSA");
        ecSigner.initSign(ecPrivate);
        ecSigner.update(data);
        byte[] ecSignature = ecSigner.sign();
        ecSigner.initVerify(ecPublic);
        ecSigner.update(data);
        System.out.println("EC round-trip verify: "
                + ecSigner.verify(ecSignature));

        KeyPairGenerator edGen = KeyPairGenerator.getInstance("Ed25519");
        KeyPair edPair = edGen.generateKeyPair();
        KeyFactory edFactory = KeyFactory.getInstance("Ed25519");
        PublicKey edPublic = edFactory.generatePublic(
                new X509EncodedKeySpec(edPair.getPublic().getEncoded()));
        PrivateKey edPrivate = edFactory.generatePrivate(
                new PKCS8EncodedKeySpec(edPair.getPrivate().getEncoded()));

        Signature edSigner = Signature.getInstance("Ed25519");
        edSigner.initSign(edPrivate);
        edSigner.update(data);
        byte[] edSignature = edSigner.sign();
        edSigner.initVerify(edPublic);
        edSigner.update(data);
        System.out.println("Ed25519 round-trip verify: "
                + edSigner.verify(edSignature));

        boolean rejected = false;
        try {
            KeyFactory.getInstance("RSA").generatePublic(
                    new X509EncodedKeySpec(
                            ecPair.getPublic().getEncoded()));
        } catch (InvalidKeySpecException expected) {
            rejected = true;
        }
        System.out.println("Wrong key algorithm rejected: " + rejected);
    }
}
```

```bash
javac -encoding UTF-8 EcEdKeyConversionDemo.java
java EcEdKeyConversionDemo
```

Stdout trên JDK 17+ thông dụng hỗ trợ EC/secp256r1 và Ed25519:

```text
EC round-trip verify: true
Ed25519 round-trip verify: true
Wrong key algorithm rejected: true
```

**Nhận xét:**

- EC dùng `KeyPairGenerator("EC")`, `ECGenParameterSpec("secp256r1")`, `KeyFactory("EC")` và chữ ký `SHA256withECDSA`. Tên curve là **tham số của thuật toán EC**, không phải tên của KeyFactory.
- Ed25519 có `KeyPairGenerator("Ed25519")`, `KeyFactory("Ed25519")` và `Signature("Ed25519")`. Không tự đổi Ed25519 thành ECDSA hoặc RSA bằng cách đổi string factory.
- Raw Ed25519 public key 32 byte **không phải** DER SPKI; raw seed/secret bytes cũng **không phải** PKCS #8 DER. Muốn nhập raw key cần KeySpec/API hoặc parser tương ứng, không ép byte[] vào `X509EncodedKeySpec`.
- `InvalidKeySpecException` ở case cuối cho thấy việc parse **đúng dạng SPKI** vẫn phải dùng **đúng thuật toán**. Nó khác `NoSuchAlgorithmException` khi Java không tìm được implementation của chính `KeyFactory`.
- Nếu ứng dụng dùng provider/HSM không hỗ trợ xuất khóa hoặc curve cụ thể, `getEncoded()` có thể không dùng được; không fallback sang một thuật toán khác khi chính sách yêu cầu Ed25519/EC cụ thể.

## 8. Ví dụ Java 17+: nhập public key PEM

API `KeyFactory` nhận **DER bytes**, không nhận trực tiếp chuỗi có `-----BEGIN PUBLIC KEY-----`. Ta cần kiểm tra envelope PEM, decode Base64, rồi dựng `X509EncodedKeySpec`.

Ví dụ dưới đây chỉ hỗ trợ **một public key SPKI PEM do chương trình tạo**. Nó không nhận chứng chỉ, private PEM, PKCS #1 RSA key, nhiều PEM block hoặc mọi cách ghi PEM trên thế giới. Parser production nên có giới hạn kích thước trước decode, chính sách input nghiêm ngặt và dùng thư viện tin cậy nếu phải hỗ trợ nhiều loại format.

Lưu thành **`PublicPemImportDemo.java`**:

```java
import java.security.*;
import java.security.spec.*;
import java.util.*;

public final class PublicPemImportDemo {
    private static String toPem(PublicKey key) {
        String base64 =
                Base64.getMimeEncoder(64, new byte[]{(byte)'\n'})
                        .encodeToString(key.getEncoded());
        return "-----BEGIN PUBLIC KEY-----\n" + base64
                + "\n-----END PUBLIC KEY-----\n";
    }

    private static PublicKey fromPem(String pem, String algorithm)
            throws GeneralSecurityException {
        String header = "-----BEGIN PUBLIC KEY-----";
        String footer = "-----END PUBLIC KEY-----";
        String value = pem.replace("\r\n", "\n").strip();
        if (!value.startsWith(header) || !value.endsWith(footer)) {
            throw new IllegalArgumentException("Expected PUBLIC KEY PEM");
        }
        String base64 = value.substring(
                header.length(), value.length() - footer.length())
                .replaceAll("\\s", "");
        byte[] der = Base64.getDecoder().decode(base64);
        return KeyFactory.getInstance(algorithm)
                .generatePublic(new X509EncodedKeySpec(der));
    }

    public static void main(String[] args) throws GeneralSecurityException {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        PublicKey key = g.generateKeyPair().getPublic();
        PublicKey restored = fromPem(toPem(key), "RSA");

        System.out.println("PEM import matches: "
                + Arrays.equals(key.getEncoded(), restored.getEncoded()));

        boolean rejected = false;
        try {
            fromPem("-----BEGIN CERTIFICATE-----\nAAA=\n"
                    + "-----END CERTIFICATE-----", "RSA");
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("Certificate header rejected: " + rejected);
    }
}
```

```bash
javac -encoding UTF-8 PublicPemImportDemo.java
java PublicPemImportDemo
```

Stdout:

```text
PEM import matches: true
Certificate header rejected: true
```

**Vì sao không dùng `Base64.getMimeDecoder()` rồi bỏ qua toàn bộ ký tự ngoài alphabet?** Một decoder quá dễ dãi có thể nuốt những ký tự không mong đợi trong input; ở đây parser chủ động kiểm tra header/footer và bỏ **whitespace** trong phần thân trước khi dùng `Base64.getDecoder()`. Dù vậy, ví dụ chỉ minh họa một envelope SPKI hợp lệ và không thay thế parser PEM đã harden với toàn bộ quy tắc RFC 7468, giới hạn kích thước và kiểm tra nhiều block.

Nếu đầu vào là `-----BEGIN CERTIFICATE-----`, cách đúng là dùng `CertificateFactory.getInstance("X.509")` đọc certificate và lấy `certificate.getPublicKey()` sau đó thực hiện **xác thực certificate chain/trust** theo chính sách ứng dụng. Đừng chỉ đổi header từ `CERTIFICATE` thành `PUBLIC KEY`: byte DER vẫn là certificate, không phải SPKI.

## 9. Đặc tả khóa và định dạng phải khớp cả thuật toán, loại khóa và provider

Một quy trình nhập khóa đúng không chỉ có `Base64.decode` và `getInstance`. Nên xác định các điều kiện sau:

1. **Nguồn khóa là gì?** Có thể là file public SPKI, private PKCS #8, certificate, JWK, keystore alias hoặc HSM handle. Mỗi loại cần parser API phù hợp.
2. **Thuật toán khóa là gì?** RSA, EC, Ed25519, X25519... `KeyFactory` cần được chọn theo thuật toán; không dùng tên cipher/signature để thay thế.
3. **Loại khóa là gì?** Public key chỉ được đưa qua `generatePublic`, private key qua `generatePrivate`. Spec toán học cũng phải đúng loại.
4. **Encoding có đúng không?** DER SPKI, DER PKCS #8, PEM bao Base64, PKCS #1, SEC1 hoặc encrypted PKCS #8 không thể thay nhau chỉ bằng tên tệp.
5. **Provider có khả năng và cho phép không?** Khóa non-exportable không thể buộc `getEncoded()` trả bytes; `translateKey` có thể bị từ chối.
6. **Key có phù hợp chính sách bảo mật không?** Kiểm tra cỡ khóa, curve, algorithm parameters và usage; không chấp nhận key yếu vì parser nhận được.
7. **Nguồn key có đáng tin không?** Parse được một public key **không** xác thực chủ sở hữu. Cần certificate chain, pinned fingerprint đáng tin, trust store hoặc quá trình trao đổi khóa xác thực.
8. **Quyền xuất và lưu private key ra sao?** Không expose riêng tư do tiện debugging; sử dụng keystore/KMS/HSM và key lifecycle được duyệt.

### 9.1 KeyStore và CertificateFactory không thay thế cho KeyFactory

`KeyStore` giữ/tra cứu khóa và chứng chỉ theo alias với khả năng bảo vệ tương ứng; `CertificateFactory` đọc dạng chứng chỉ; `KeyFactory` chuyển đổi biểu diễn khóa. Có thể dùng chúng cùng nhau:

```text
Trusted KeyStore  --> Certificate --> getPublicKey() --> PublicKey
KeyStore alias    --> getKey(password) ----------------> PrivateKey/SecretKey
DER SPKI          --> X509EncodedKeySpec --> KeyFactory --> PublicKey
DER PKCS #8       --> PKCS8EncodedKeySpec --> KeyFactory --> PrivateKey
```

Việc `KeyStore.getKey` trả đối tượng `PrivateKey` **không đòi hỏi** tiếp tục export rồi gọi `KeyFactory.generatePrivate`. Nếu provider cho phép thao tác ký ngay bằng key handle, hãy dùng key trực tiếp với `Signature`. Export/import vô ích có thể phá vỡ boundary bảo mật của phần cứng.

### 9.2 Chứng chỉ và trust

Giả sử một đối tác gửi public key SPKI; bạn import bằng `KeyFactory.generatePublic` thành công. Điều đó chứng minh DER hợp lệ và provider hiểu thuật toán, **chưa chứng minh đối tác thật sự sở hữu khóa**. Một attacker cũng có thể tạo key RSA hợp lệ để lừa ứng dụng xác minh chữ ký do chính attacker tạo. Cần gắn key với danh tính qua kênh xác thực, certificate verification, pinning hoặc trust framework được xác định rõ.

Tránh coi `PublicKey.getEncoded()` như một chuỗi định danh tự thân cho mọi ngữ cảnh. Nếu dùng fingerprint, chuẩn hóa rõ loại encoding, thuật toán hash và nguồn/điểm tin cậy. Sự tương đương về toán học không nhất thiết kéo theo mọi provider xuất **mảng byte DER giống hệt nhau**.

## 10. Xử lý ngoại lệ đúng loại

| Lỗi | Điểm xuất hiện | Diễn giải và xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | `KeyFactory.getInstance("RSA" / "EC" / "Ed25519")` | Thuật toán không có implementation ở các provider khả dụng. Kiểm tra JDK/provider và chính sách deployment; không giả định cứ cài thư viện là tương thích. |
| `NoSuchProviderException` | Overload `getInstance(algorithm, "providerName")` | Tên provider chưa được đăng ký. Kiểm tra provider registration và cấu hình. |
| `InvalidKeySpecException` | `generatePublic`, `generatePrivate`, `getKeySpec` | Spec không phù hợp loại khóa, DER sai/không được hỗ trợ, thuật toán sai hoặc không thể xuất spec. |
| `InvalidKeyException` | `translateKey` | Provider/factory không thể chuyển key object được cung cấp. |
| `IllegalArgumentException` | Parser PEM / `Base64.getDecoder().decode` và một số validation API | Input không đúng envelope/base64 hoặc tham số ứng dụng sai. Không khẳng định tất cả API KeyFactory dùng cùng ngoại lệ. |
| `NullPointerException` | Đầu vào null tại các constructor/phương thức có yêu cầu non-null | Lỗi hợp đồng đầu vào; kiểm tra input trước khi vào crypto API. |
| Lỗi khi dùng khóa sau import | `Signature.initSign/initVerify` hoặc `Cipher.init` | Một key object parse được vẫn có thể không phù hợp cho operation, provider, scheme, key usage hoặc chính sách. |

Gợi ý phân lớp:

- **Khi startup:** nạp thuật toán/provider/khóa cấu hình; phát hiện thiếu capability hoặc key sai; fail fast và giữ `cause` trong log an toàn.
- **Khi nhận key từ bên ngoài:** giới hạn kích thước trước decode; phân biệt PEM syntax/Base64 với DER/spec và policy/chain validation. Trả thông báo lỗi input phù hợp, không trả stack trace nhạy cảm.
- **Khi khóa riêng bị khóa trong HSM:** không yêu cầu `getKeySpec(privateKey, RSAPrivateCrtKeySpec.class)` để “debug”. Dùng các operation được provider cho phép.
- **Khi định dạng bản ghi thay đổi:** lưu version + algorithm identifier, có migration rõ ràng; tránh thử ngẫu nhiên nhiều parser/thuật toán khiến lỗi khó truy vết.
- **Khi provider thay đổi:** đánh giá khả năng `getKeySpec`/`translateKey` từ môi trường thật; không suy diễn rằng mọi provider có thể chuyển khóa qua lại.

### 10.1 Một mẫu xử lý lỗi không nên dùng

```java
// Anti-pattern: làm mất nguyên nhân và có thể tạo null ở tầng sau.
try {
    return KeyFactory.getInstance("RSA")
            .generatePrivate(new PKCS8EncodedKeySpec(bytes));
} catch (Exception ex) {
    return null;
}
```

Đây là **mã minh họa bên trong một phương thức** (chưa khai báo biến `bytes` và kiểu trả về), **không phải chương trình Java độc lập**. Cách đúng là kiểm tra input, phân loại lỗi parse với lỗi cấu hình, giữ `cause` để điều tra và không trả `null` mơ hồ. Cũng không nên âm thầm chuyển sang key algorithm khác để “chạy được”.

## 11. Các giới hạn an toàn cần nhớ khi xuất, nhập khóa riêng

**Bản chất của khóa riêng:** Nếu `privateKey.getEncoded()` trả bytes PKCS #8, bất cứ ai đọc được bytes tương ứng có thể có khả năng sử dụng private key. Base64, PEM, `PKCS8EncodedKeySpec` hay một `byte[]` trong JVM không làm nó tự được mã hóa.

**Bộ nhớ:** `PKCS8EncodedKeySpec` sao chép bytes khi dựng và có thể sao chép khi gọi `getEncoded()`. Xóa một `byte[]` ban đầu không có nghĩa các bản sao trong heap, key object hay provider đã biến mất. Với yêu cầu cao, ưu tiên key non-extractable trong HSM/KMS, giới hạn lifetime và các cơ chế bảo vệ nền tảng.

**Khóa có thể được đóng gói:** `Key.getEncoded()` có thể trả `null`. Đây thường là dấu hiệu dạng khóa không được phép/không thể export, không nên chữa bằng reflection hoặc serialized object provider-specific.

**Khác biệt provider:** Một số provider nhận cùng DER nhưng đưa ra key object khác; một số chỉ hỗ trợ subset `KeySpec`; một số yêu cầu algorithm parameters cụ thể. Luôn thử đúng target runtime và xử lý `InvalidKeySpecException`/`InvalidKeyException` rõ ràng.

**Khả năng trust:** Chuyển đổi là biến đổi **biểu diễn**. Nó không kiểm tra chủ sở hữu key, không thu hồi chứng chỉ, không tự giải mã encrypted PKCS #8 và không xác nhận một key được cấp đúng mục đích.

## 12. Tự kiểm tra kiến thức qua tình huống

**Tình huống A.** Nhận chuỗi `-----BEGIN PUBLIC KEY-----` nhưng truyền nguyên cả chuỗi vào `new X509EncodedKeySpec(pem.getBytes())`. Vì sao sai?  
**Giải:** Spec cần **DER bytes**, không phải chữ Base64 kèm header/footer. Phải xác nhận loại PEM, decode Base64 lấy SPKI DER trước rồi mới gọi `generatePublic`.

**Tình huống B.** File có nhãn `-----BEGIN CERTIFICATE-----`. Có thể dùng `X509EncodedKeySpec` không?  
**Giải:** Không trực tiếp; đó là **certificate DER** chứ không phải SPKI DER. Dùng `CertificateFactory` đọc chứng chỉ, lấy `getPublicKey()`, và kiểm tra trust/chain theo chính sách.

**Tình huống C.** Một file `BEGIN RSA PRIVATE KEY` được đưa vào `PKCS8EncodedKeySpec`; xuất hiện `InvalidKeySpecException`. Có phải RSA bị thiếu?  
**Giải:** Chưa chắc. Đó thường là **PKCS #1**, khác PKCS #8. Cần chuyển đổi định dạng với parser/công cụ tin cậy trước khi dựng khóa. Chỉ khi `KeyFactory.getInstance("RSA")` thất bại mới nghi ngờ không có factory.

**Tình huống D.** Code dùng `KeyFactory.getInstance("SHA256withRSA")`.  
**Giải:** Sai loại tên thuật toán: `SHA256withRSA` dành cho `Signature`. Để dựng khóa RSA dùng `KeyFactory.getInstance("RSA")`.

**Tình huống E.** `PrivateKey` lấy từ HSM có `getEncoded() == null`. Làm sao “khắc phục”?  
**Giải:** Không cố export. Xác minh key handle và quyền sử dụng, thực hiện `Signature.initSign(privateKey)` hoặc thao tác cho phép qua provider. Không phải mọi private key đều có PKCS #8 để lấy ra.

**Tình huống F.** `KeyFactory.getKeySpec(publicKey, RSAPublicKeySpec.class)` lấy được `n`, `e`. Từ đó tạo private key được không?  
**Giải:** Không. Public components không chứa đủ thông tin của private key. `KeyFactory` không giải bài toán khôi phục private key từ public key.

**Tình huống G.** RSA private key import thành công, nhưng verify chữ ký từ đối tác vẫn không hợp lệ.  
**Giải:** Import đúng key **không** bảo đảm đó là key đúng đối tác, cũng không bảo đảm `Signature` đang dùng cùng scheme/dữ liệu/canonicalization. Kiểm tra danh tính public key, thuật toán ký, parameters và bytes được ký, không quy mọi lỗi vào `KeyFactory`.

**Tình huống H.** Muốn dựng khóa EC bằng `X509EncodedKeySpec` chứa Ed25519 public key. `KeyFactory.getInstance("EC")` có tự hiểu không?  
**Giải:** Không. Ed25519 là thuật toán có tên factory riêng; cần chọn đúng KeyFactory/provider, không coi mọi khóa elliptic curve là ECDSA/EC.

**Tình huống I.** Công cụ tạo `ENCRYPTED PRIVATE KEY`, nhưng Java gọi thẳng `generatePrivate(new PKCS8EncodedKeySpec(bytes))`.  
**Giải:** `PKCS8EncodedKeySpec` cần PKCS #8 private-key structure chưa được mã hóa ở lớp bao ngoài. Phải dùng quy trình giải mã encrypted PKCS #8 phù hợp trước, đồng thời bảo vệ password và memory.

## 13. Checklist áp dụng trong ứng dụng thật

1. **Biết format**: public SPKI/X.509, private PKCS #8, certificate, PKCS #1, SEC1 hay provider handle; có mã hóa lớp bao hay không.
2. **Chọn đúng thuật toán KeyFactory**: `RSA`, `EC`, `Ed25519`... dựa trên contract đã xác thực, không dựa vào chuỗi tự do từ người dùng.
3. **Dùng đúng spec**: `X509EncodedKeySpec` cho SPKI public; `PKCS8EncodedKeySpec` cho unencrypted PKCS #8 private; spec toán học khi thực sự cần.
4. **Kiểm tra trust**: nguồn public key, certificate chain/pinning, key usage và hạn sử dụng; parse thành công không chứng minh danh tính.
5. **Giới hạn input**: độ dài file, số block PEM, Base64/DER structure, cỡ khóa, thuật toán và parameters theo policy.
6. **Bảo vệ private key**: không log/commit/export tùy tiện; ưu tiên `KeyStore`, KMS/HSM và quyền hạn thích hợp.
7. **Kiểm thử với provider thật**: cả `getEncoded()` trả `null`, `getKeySpec`/ `translateKey` bị từ chối, thuật toán không có và key spec sai.
8. **Kiểm chứng chức năng**: ví dụ sign/verify cho keypair dự kiến; test mẫu hợp lệ/sai format/nhầm key, nhưng không sao chép key bí mật test vào production.
9. **Duy trì khả năng tương tác**: định nghĩa rõ DER/PEM, algorithm identifier, curve, key format và phiên bản khi trao đổi giữa Java/OpenSSL/đối tác.

## Tài liệu Java chính thức

- [Java SE 21 — `KeyFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyFactory.html): hướng chuyển Key/KeySpec, provider, `generatePublic`, `generatePrivate`, `getKeySpec`, `translateKey`.
- [Java SE 21 — `Key`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Key.html): `getAlgorithm`, `getFormat` và `getEncoded`, bao gồm khả năng không xuất được encoding.
- [Java SE 21 — `X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): ASN.1 SubjectPublicKeyInfo public-key encoding.
- [Java SE 21 — `PKCS8EncodedKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html): private-key encoding theo PKCS #8.
- [Java SE 21 — `RSAPublicKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/RSAPublicKeySpec.html) và [`RSAPrivateCrtKeySpec`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/spec/RSAPrivateCrtKeySpec.html): thành phần toán học RSA.
- [Java SE 21 — `CertificateFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertificateFactory.html) và [`KeyStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/KeyStore.html): phân biệt certificate parsing và key storage.
- [RFC 7468 — Textual Encodings of PKIX Structures](https://www.rfc-editor.org/rfc/rfc7468.html): envelope PEM cho public/private key/certificate.

**Ghi nhớ:** `KeyFactory` giúp **chuyển biểu diễn** của khóa bất đối xứng, với `KeySpec` là đầu vào hoặc đầu ra của chuyển đổi. Đúng định dạng **SPKI/PKCS #8**, đúng thuật toán và đúng provider là điều kiện để dựng khóa; **trust, bảo vệ private key và quyền sử dụng** vẫn phải được kiểm soát riêng.