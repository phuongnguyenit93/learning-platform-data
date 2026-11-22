# KeyPairGenerator và tạo cặp khóa EdEC trong Java 15+

## 1. Mục tiêu bài học

Từ Java 15, Java hỗ trợ **EdDSA (Edwards-Curve Digital Signature Algorithm)** theo RFC 8032, bao gồm hai biến thể phổ biến là **Ed25519** và **Ed448**. Trong hệ thống Java Cryptography Architecture (JCA), lớp `java.security.KeyPairGenerator` có thể tạo **cặp khóa bất đối xứng EdEC** gồm:

- **Private key (khóa riêng):** chỉ chủ sở hữu giữ, dùng để tạo chữ ký số EdDSA.
- **Public key (khóa công khai):** có thể phân phối tới bên kiểm tra, dùng để xác minh chữ ký.

`KeyPairGenerator` là một *engine class* dùng chung cho nhiều thuật toán, không phải lớp chỉ dành riêng cho EdEC. Đối với EdEC, ta yêu cầu implementation phù hợp thông qua tên thuật toán `"Ed25519"`, `"Ed448"` hoặc `"EdDSA"`, sau đó gọi `generateKeyPair()`.

**Mục tiêu thực hành:** tạo hai cặp khóa Ed25519/Ed448, nhận public/private key, xác minh tham số đường cong, ký thử một thông điệp bằng private key và kiểm tra chữ ký bằng public key. Tất cả được thực hiện bằng API chính thức vẫn còn được hỗ trợ trên Java 17+ và các JDK hiện đại.

## 2. Phân biệt EdEC, EdDSA, Ed25519, Ed448 và XDH

| Thuật ngữ | Ý nghĩa | Sử dụng với JCA |
| --- | --- | --- |
| **EdEC** | Nhóm giao diện khóa trên đường cong Edwards theo RFC 8032 | `EdECPublicKey`, `EdECPrivateKey` |
| **EdDSA** | Họ thuật toán chữ ký số dùng các đường cong Edwards | `KeyPairGenerator.getInstance("EdDSA")`, `Signature.getInstance("EdDSA")` |
| **Ed25519** | Biến thể EdDSA với đường cong edwards25519 | `KeyPairGenerator.getInstance("Ed25519")` |
| **Ed448** | Biến thể EdDSA với đường cong edwards448 | `KeyPairGenerator.getInstance("Ed448")` |
| **X25519/X448** | Thuật toán thỏa thuận khóa theo RFC 7748, không phải thuật toán chữ ký EdDSA | `KeyAgreement` / `KeyPairGenerator` cho `"X25519"`, `"X448"` hoặc `"XDH"` |
| **ECDSA/EC** | Họ chữ ký/khóa elliptic curve khác với giao diện EdEC | `ECPrivateKey`, `ECPublicKey`, `Signature` ECDSA |

**Không nhầm mục tiêu:** Ed25519 và Ed448 dùng để **ký/xác minh**. Nếu bài toán là hai bên thiết lập bí mật chung, cần dùng giao thức và thuật toán key agreement thích hợp, chẳng hạn **X25519**, chứ không tự đem private key Ed25519 vào `KeyAgreement.getInstance("X25519")`. Hai họ khóa và định dạng tham số không thể tùy tiện thay thế cho nhau.

Ed25519 tạo chữ ký có độ dài **64 byte**; Ed448 tạo chữ ký **114 byte** theo biểu diễn RFC 8032. Chúng **không** có nghĩa khóa riêng chứa đúng 64 hoặc 114 byte; hãy phân biệt kích thước chữ ký với khóa và định dạng mã hóa khóa.

## 3. Các lớp Java cần biết

| API | Vai trò |
| --- | --- |
| `java.security.KeyPairGenerator` | Chọn thuật toán/provider và sinh cặp khóa |
| `java.security.KeyPair` | Container chứa `PublicKey` và `PrivateKey` tương ứng |
| `java.security.interfaces.EdECPublicKey` | Giao diện khóa công khai EdEC; có `getParams()`, `getPoint()` |
| `java.security.interfaces.EdECPrivateKey` | Giao diện khóa riêng EdEC; có `getParams()`, `getBytes()` |
| `java.security.spec.NamedParameterSpec` | Biểu diễn bộ tham số bằng tên, có `ED25519`, `ED448` |
| `java.security.Signature` | Tạo và xác minh chữ ký bằng thuật toán EdDSA thích hợp |
| `java.security.KeyFactory` | Tái tạo khóa từ key specification hoặc chuyển giữa representation phù hợp |
| `java.security.SecureRandom` | Nguồn ngẫu nhiên mật mã dùng khi sinh khóa |

Các giao diện EdEC và `NamedParameterSpec.ED25519`/`ED448` đã được giới thiệu cùng hỗ trợ EdDSA trong Java 15. Chúng khác với `java.security.interfaces.ECPublicKey`/`ECPrivateKey` vốn dùng cho các thuật toán EC khác; **không ép kiểu một EdEC key thành EC key**.

Hai lời gọi thường dùng:

```java
KeyPairGenerator ed25519 = KeyPairGenerator.getInstance("Ed25519");
KeyPair keyPair = ed25519.generateKeyPair();
```

Sau đó `keyPair.getPublic()` trả về `PublicKey`; `keyPair.getPrivate()` trả về `PrivateKey`. Đây là **hai thành phần của cùng cặp khóa**, phải được giữ cùng nhau khi cần ký và xác minh.

## 4. Cách 1: chọn thuật toán cụ thể ngay từ đầu

Khi đã biết cần Ed25519, cách rõ ràng nhất là:

```java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = generator.generateKeyPair();
```

Đây là đoạn code **minh họa đặt trong method hoặc test**, không phải file Java độc lập. Nó thực hiện:

1. `getInstance("Ed25519")`: yêu cầu JCA tìm provider có khả năng sinh khóa Ed25519.
2. `generateKeyPair()`: tạo cặp public/private key mới dựa trên thông số thuật toán và nguồn ngẫu nhiên thích hợp.
3. `pair.getPublic()`: truy cập khóa công khai.
4. `pair.getPrivate()`: truy cập khóa riêng.

Nếu cần Ed448, đổi thuật toán thành `"Ed448"`. Trong OpenJDK/Oracle JDK hiện đại, provider **SunEC** hỗ trợ cả `Ed25519`, `Ed448` và `EdDSA` cho `KeyPairGenerator` và `Signature`. Tuy vậy, trong một runtime đã thay đổi danh sách security providers hoặc chế độ bảo mật, thuật toán có thể không có: `getInstance(...)` khi đó ném `NoSuchAlgorithmException`.

**Không cần tự gọi `initialize(...)`** khi đã yêu cầu đúng thuật toán `Ed25519` hoặc `Ed448` và dùng mặc định của provider thích hợp.

## 5. Cách 2: chọn EdDSA chung, chỉ định đường cong bằng NamedParameterSpec

Nếu mã nguồn muốn làm việc với tên thuật toán **`EdDSA`** rồi chọn một đường cong bằng tham số:

```java
import java.security.KeyPairGenerator;
import java.security.KeyPair;
import java.security.spec.NamedParameterSpec;

KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(NamedParameterSpec.ED25519);
KeyPair pair = generator.generateKeyPair();
```

Muốn sinh khóa Ed448 theo cùng cách:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(NamedParameterSpec.ED448);
KeyPair pair = generator.generateKeyPair();
```

`NamedParameterSpec.ED25519` và `NamedParameterSpec.ED448` là các tham số chuẩn có từ Java 15. Cách này giúp **chọn rõ đường cong**, thay vì dựa vào mặc định của provider.

Với provider SunEC, nếu `KeyPairGenerator.getInstance("EdDSA")` không được khởi tạo bằng tham số nào, mặc định hiện hành là Ed25519. **Không nên dựa vào mặc định đó trong mã cần tương thích nhiều provider:** hãy yêu cầu tên thuật toán cụ thể hoặc gọi `initialize(NamedParameterSpec.ED25519)` / `initialize(NamedParameterSpec.ED448)`.

`initialize(int keysize)` là API dùng chung, nhưng **không phải cách nên dùng để diễn tả yêu cầu Ed25519/Ed448**. Tránh tự chọn các số 255/256/448 theo cảm tính; `NamedParameterSpec` nêu rõ ý định và tránh lẫn kích thước đường cong, độ bảo mật và số byte chữ ký.

## 6. Ví dụ hoàn chỉnh: sinh cặp khóa, ký và xác minh

Tạo file **`EdECKeyPairDemo.java`** với nội dung sau. Chương trình sẽ sinh khóa mới ở mỗi lần chạy, vì vậy không in khóa thực hoặc chữ ký dạng Base64 (các byte có thể thay đổi). Thay vào đó, stdout chỉ gồm tên tham số, chiều dài chữ ký và kết quả xác minh có thể dự đoán.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.interfaces.EdECPrivateKey;
import java.security.interfaces.EdECPublicKey;
import java.security.spec.NamedParameterSpec;

public class EdECKeyPairDemo {
    public static void main(String[] args) throws GeneralSecurityException {
        demonstrate("Ed25519");
        demonstrate("Ed448");

        KeyPairGenerator generic = KeyPairGenerator.getInstance("EdDSA");
        generic.initialize(NamedParameterSpec.ED25519);
        KeyPair genericPair = generic.generateKeyPair();
        EdECPublicKey genericPublic = (EdECPublicKey) genericPair.getPublic();
        System.out.println("EdDSA explicit curve=" +
                genericPublic.getParams().getName());
    }

    static void demonstrate(String algorithm) throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance(algorithm);
        KeyPair pair = generator.generateKeyPair();

        EdECPublicKey publicKey = (EdECPublicKey) pair.getPublic();
        EdECPrivateKey privateKey = (EdECPrivateKey) pair.getPrivate();
        byte[] message = "hello, EdDSA".getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(privateKey);
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(publicKey);
        verifier.update(message);
        boolean valid = verifier.verify(signature);

        verifier.initVerify(publicKey);
        verifier.update("modified".getBytes(StandardCharsets.UTF_8));
        boolean modifiedValid = verifier.verify(signature);

        System.out.println(algorithm + " publicCurve=" +
                publicKey.getParams().getName()
                + " privateCurve=" + privateKey.getParams().getName()
                + " signatureBytes=" + signature.length
                + " valid=" + valid
                + " modifiedValid=" + modifiedValid);
    }
}
```

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

```bash
javac --release 17 EdECKeyPairDemo.java
java EdECKeyPairDemo
```

**Stdout chính xác** (đã được xác minh bằng JDK 24 khi biên dịch ở mức Java 17):

```text
Ed25519 publicCurve=Ed25519 privateCurve=Ed25519 signatureBytes=64 valid=true modifiedValid=false
Ed448 publicCurve=Ed448 privateCurve=Ed448 signatureBytes=114 valid=true modifiedValid=false
EdDSA explicit curve=Ed25519
```

Giải thích:

1. `demonstrate("Ed25519")` sinh một cặp khóa Ed25519 và sử dụng `Signature.getInstance("Ed25519")`; chữ ký dài 64 byte.
2. `demonstrate("Ed448")` thực hiện tương tự cho Ed448; chữ ký dài 114 byte.
3. `getParams().getName()` từ hai giao diện khóa cho biết **cùng đường cong** được sử dụng cho public/private key.
4. `signer.initSign(privateKey)` chọn khóa riêng để ký; `signer.update(message)` đưa dữ liệu vào bộ ký; `signer.sign()` xuất chữ ký.
5. `verifier.initVerify(publicKey)` chọn khóa công khai; khi xác minh cùng `message`, `verify(signature)` là `true`.
6. Thử xác minh chữ ký cũ với nội dung `"modified"` cho kết quả `false`, minh họa chữ ký gắn với **thông điệp**, không chỉ gắn với khóa.
7. Phần cuối tạo `KeyPairGenerator` tên `EdDSA` và chọn `NamedParameterSpec.ED25519` rõ ràng, nên output đường cong là `Ed25519`.

Ví dụ này được kiểm chứng với provider EdDSA tích hợp trong JDK hiện đại. Khi dùng runtime chỉ có một provider tùy chỉnh, cần xác nhận provider đó hỗ trợ cả Ed25519 lẫn Ed448 trước khi chạy nguyên chương trình.

## 7. Hiểu đúng cặp khóa và tính bất đối xứng

`KeyPair` giữ hai đối tượng khác nhau:

```java
PublicKey publicKey = pair.getPublic();
PrivateKey privateKey = pair.getPrivate();
```

Đây là **đoạn code minh họa** được dùng bên trong method, với `pair` đã được tạo trước. Quy tắc sử dụng là:

- **Khóa riêng:** dùng `Signature.initSign(privateKey)` để tạo chữ ký; giữ bí mật và kiểm soát quyền truy cập.
- **Khóa công khai:** dùng `Signature.initVerify(publicKey)` để kiểm tra chữ ký; có thể được phân phối cho các bên cần xác minh.
- **Không thể coi public key là bản sao của private key.** Hai phần có quan hệ toán học nhưng vai trò khác nhau.
- **Không thể dùng private key để “giải mã” một chữ ký hoặc dùng public key để “mã hóa” thông điệp** như cách nhiều ví dụ RSA cũ mô tả. EdDSA là hệ thống **chữ ký số**, không phải cơ chế mã hóa dữ liệu.
- **Xác minh thành công không tự chứng minh danh tính người ký:** bên kiểm tra còn phải tin tưởng rằng public key đang sử dụng thật sự thuộc người/chủ thể mong đợi, qua chứng chỉ, registry, fingerprint được xác thực hoặc cơ chế phân phối khóa đáng tin cậy.

Khi cần sinh nhiều cặp khóa, gọi `generateKeyPair()` cho mỗi cặp mới. Không dùng cùng một private key cho nhiều danh tính chỉ vì có thể làm vậy về mặt kỹ thuật; chính sách vòng đời, phân phối và thu hồi khóa phải phù hợp hệ thống.

## 8. Kiểm tra tham số và loại khóa EdEC

`KeyPair.getPublic()` có kiểu khai báo `PublicKey`, `getPrivate()` có kiểu `PrivateKey`. Với provider hỗ trợ EdEC theo API chuẩn, ta có thể dùng giao diện chuyên biệt:

```java
EdECPublicKey pub = (EdECPublicKey) pair.getPublic();
EdECPrivateKey priv = (EdECPrivateKey) pair.getPrivate();

String publicCurve = pub.getParams().getName();
String privateCurve = priv.getParams().getName();
```

`getParams()` là API chung của `EdECKey`, trả về `NamedParameterSpec`; `getName()` cho biết tên tham số như `Ed25519` hoặc `Ed448`. Đây là cách phù hợp để kiểm tra đường cong của một khóa EdEC.

Ngoài ra:

- `EdECPublicKey.getPoint()` trả về `EdECPoint` đại diện điểm công khai trên đường cong, không giống dạng điểm từ `ECPublicKey` của ECDSA.
- `EdECPrivateKey.getBytes()` trả `Optional<byte[]>` cho dữ liệu nhạy cảm của private key nếu khóa có thể xuất dạng này. **Không in dữ liệu đó ra log**, không lưu vào báo cáo kiểm thử; đối với một số provider hoặc thiết bị khóa an toàn, thông tin private key có thể không xuất được.
- `Key.getAlgorithm()` chỉ cho biết tên thuật toán theo provider/standard; khi cần xác nhận curve cụ thể của EdEC key, dùng `getParams().getName()`, không suy ra dựa vào số byte hoặc class implementation cụ thể.

Đừng ép kiểu `EdECPublicKey` thành `ECPublicKey`; đây là hai họ giao diện khác nhau.

## 9. Nguồn ngẫu nhiên khi sinh cặp khóa

Tạo khóa EdEC cần nguồn ngẫu nhiên mật mã thích hợp. Khi dùng `KeyPairGenerator.getInstance("Ed25519")` rồi gọi `generateKeyPair()` như ở ví dụ chính, provider chọn nguồn `SecureRandom` thích hợp theo cơ chế JCA.

Nếu môi trường cần truyền nguồn ngẫu nhiên đáp ứng chính sách triển khai, API hỗ trợ overload:

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(NamedParameterSpec.ED25519, new java.security.SecureRandom());
KeyPair pair = generator.generateKeyPair();
```

**Đoạn trên minh họa cách cấu hình trong method**, cần xử lý `GeneralSecurityException` thích hợp. Việc cung cấp `SecureRandom` đúng cách khác với việc dùng `java.util.Random`: `Random` không phải nguồn ngẫu nhiên mật mã dùng để tạo private key.

Trong ứng dụng thực tế:

- Không dùng seed cố định, seed dự đoán được hoặc `Random` thông thường để mong có key pair an toàn.
- Không in seed/private key ra console, log, telemetry hoặc exception message.
- Không mặc định “cùng seed thì cùng khóa” trên mọi provider/JDK: cách sinh khóa là chi tiết của provider và không phải định dạng chuẩn để lưu một khóa.
- Nếu hệ thống yêu cầu HSM/KMS, hãy dùng provider và chính sách khóa không xuất private key; Java API `KeyPairGenerator` là bề mặt chung chứ không cam kết mọi khóa đều có thể trích xuất byte.

## 10. Lưu, tải và phân phối khóa: chọn đúng định dạng

Trong hệ thống thực, sinh được cặp khóa mới chỉ là bước đầu. **Khóa công khai** thường có thể được truyền đi an toàn; **khóa riêng** phải được giữ bí mật, phân quyền và lưu phù hợp mô hình đe dọa.

Trong JCA, các representation thường gặp:

| Đối tượng | `getFormat()` / `getEncoded()` phổ biến | Mục đích |
| --- | --- | --- |
| Public key | `"X.509"` / `SubjectPublicKeyInfo` encoding | Trao đổi khóa công khai |
| Private key | `"PKCS#8"` / private-key encoding | Chuyển/lưu khóa riêng **khi policy cho phép xuất khóa** |

**Đây là các định dạng encoding, không phải đường cong.** Ed25519/Ed448 là thuật toán; X.509 và PKCS#8 mô tả cách mã hóa cấu trúc khóa để lưu hoặc trao đổi.

Nếu một khóa có thể xuất encoded byte, có thể tái tạo qua `KeyFactory`:

```java
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.PrivateKey;
import java.security.spec.X509EncodedKeySpec;
import java.security.spec.PKCS8EncodedKeySpec;

// Minh họa trong một method, khi pair đã được tạo và có thể export.
KeyFactory factory = KeyFactory.getInstance("Ed25519");
PublicKey restoredPublic = factory.generatePublic(
        new X509EncodedKeySpec(pair.getPublic().getEncoded()));
PrivateKey restoredPrivate = factory.generatePrivate(
        new PKCS8EncodedKeySpec(pair.getPrivate().getEncoded()));
```

Ví dụ trên mô tả cách dùng API, **không** chủ trương lưu private-key bytes ra file văn bản hoặc log. `getEncoded()` có thể trả `null` với khóa được quản lý bởi HSM/provider không cho xuất, và cần kiểm tra trước khi sử dụng. Việc lưu khóa riêng nên dùng `KeyStore`, KMS hoặc HSM phù hợp, có kiểm soát quyền truy cập, chính sách backup và rotate. Nếu khóa private xuất được, việc bảo vệ byte đã xuất cũng quan trọng như bảo vệ đối tượng khóa gốc.

Nếu chỉ cần đưa public key sang hệ thống khác, có thể phân phối mã hóa X.509 SubjectPublicKeyInfo theo giao thức hệ thống, kèm thông tin thuật toán hoặc key identifier để bên nhận chọn đúng cách xác minh.

## 11. Các lỗi thực tế và cách chẩn đoán

| Lỗi/tình huống | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` khi `getInstance("Ed448")` | Không có provider Ed448 trong runtime | Kiểm tra provider/JDK; dùng provider có hỗ trợ, không đổi tên tùy tiện |
| `InvalidAlgorithmParameterException` khi `initialize` | Tham số không được implementation chấp nhận | Dùng `NamedParameterSpec.ED25519` hoặc `ED448` phù hợp |
| `InvalidKeyException` khi `initSign`/`initVerify` | Khóa không đúng thuật toán/curve hoặc không phù hợp | Kiểm tra key type và `getParams().getName()` |
| `SignatureException` trong `update`/`sign`/`verify` | Lỗi xử lý chữ ký hoặc trạng thái crypto không đúng | Kiểm tra chuỗi `initSign`/update/sign, provider và dữ liệu |
| `verify(signature)` trả `false` | Nội dung, chữ ký hoặc khóa công khai không khớp | So sánh đúng bytes, xác nhận public key thuộc cặp đúng |
| `ClassCastException` sang `ECPublicKey` | Đang dùng giao diện EC không dành cho EdEC | Dùng `EdECPublicKey`/`EdECPrivateKey` |
| `NullPointerException` khi sử dụng `getEncoded()` | Provider không cho export private key | Kiểm tra khả năng export và dùng API khóa không xuất |

Khi debug chữ ký, điều đầu tiên là **so sánh chính xác byte thông điệp**: `"abc"` và `"abc\n"` là hai thông điệp khác nhau. Kết quả `verify=false` không đồng nghĩa provider hỏng. Phải dùng cùng curve, cùng public key tương ứng, cùng chế độ EdDSA và cùng bytes đã ký.

Đừng “sửa” lỗi bằng cách đổi `Ed25519` thành `X25519`. Hai thuật toán có mục đích và key interface khác nhau; ứng dụng bảo mật phải chọn đúng chức năng mật mã.

## 12. Sai lầm phổ biến cần tránh

1. **“Ed25519 và X25519 chỉ là hai tên giống nhau.”** Sai: Ed25519 là chữ ký số, X25519 dùng cho thỏa thuận khóa.
2. **“Có `KeyPairGenerator` là đủ để mã hóa thông điệp.”** Sai: EdDSA tạo chữ ký; muốn mã hóa cần giao thức và thuật toán mã hóa riêng.
3. **“Mọi `EdECPrivateKey` đều đọc được private bytes.”** Sai: khả năng export phụ thuộc API/provider và chính sách khóa, nên `getBytes()` là `Optional`.
4. **“`KeyPairGenerator.getInstance("EdDSA")` luôn chọn curve giống nhau ở mọi provider.”** Không nên giả định; khai báo `NamedParameterSpec` hoặc tên curve cụ thể.
5. **“Thấy tên `Ed25519` là có thể dùng `ECPublicKey`.”** Sai: dùng `EdECPublicKey`, khác EC truyền thống.
6. **“Public key có thể được tin tưởng chỉ vì nó được truyền qua mạng.”** Sai: cần cơ chế xác thực nguồn khóa công khai.
7. **“Chữ ký dài 64 byte tức khóa riêng có định dạng dài 64 byte.”** Sai: chữ ký, seed/private-key material và encoding PKCS#8 là các khái niệm khác nhau.
8. **“Tạo key pair với seed cố định là an toàn vì test chạy lặp lại được.”** Sai trong hệ thống thật; private key cần ngẫu nhiên mật mã khó dự đoán.
9. **“Lưu private key Base64 trong source code không sao.”** Sai: mã hóa Base64 không phải mã hóa bảo mật; private key cần được bảo vệ.
10. **“`Signature.verify` thành công nghĩa đã xác thực danh tính đối tác.”** Chỉ đúng khi public key đã được tin cậy và gắn với danh tính đúng qua quy trình phân phối đáng tin cậy.

## 13. Checklist khi triển khai cặp khóa EdEC

Trước khi đưa tính năng vào ứng dụng, kiểm tra:

- Bài toán cần **chữ ký EdDSA** hay **key agreement XDH**? Đừng trộn Ed25519 với X25519.
- Cả bên ký và bên xác minh có hỗ trợ cùng curve Ed25519/Ed448?
- Dùng `KeyPairGenerator.getInstance("Ed25519")`/`"Ed448"`, hoặc `"EdDSA"` với `NamedParameterSpec` tường minh?
- Private key có được tạo từ nguồn `SecureRandom` thích hợp và không lộ qua log?
- Key pair có nằm trong keystore/KMS/HSM theo chính sách bảo mật, thay vì chuỗi hardcode?
- Bên xác minh có xác thực nguồn public key trước khi tin chữ ký?
- Thông điệp được ký/xác minh có cùng **byte encoding**, chẳng hạn UTF-8, và cùng dữ liệu nguyên vẹn?
- Có xử lý trường hợp runtime/provider không hỗ trợ Ed448 hoặc không cho export private key không?
- Unit test có kiểm tra chữ ký đúng và phép xác minh thất bại khi thông điệp bị thay đổi không?

**Ghi nhớ:** `KeyPairGenerator` tạo khóa EdEC; `KeyPair` giữ public/private key; `NamedParameterSpec` chỉ định đường cong; `Signature` dùng private key để ký và public key để xác minh. Đây là API Java 15+ chính thức, vẫn áp dụng trong Java hiện đại.

## Tài liệu chính thức còn hiệu lực

- [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): tính năng EdDSA được đưa vào Java 15.
- [Oracle Java SE 27 — JDK Security Providers, SunEC](https://docs.oracle.com/en/java/javase/27/security/oracle-providers.html): bảng tên thuật toán `KeyPairGenerator`, `Signature` và mặc định EdDSA của SunEC.
- [Oracle Java SE 27 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/KeyPairGenerator.html): tạo đối tượng sinh cặp khóa, khởi tạo tham số và `generateKeyPair()`.
- [Oracle Java SE 27 — EdECPublicKey](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/interfaces/EdECPublicKey.html): giao diện public key và đường cong EdEC.
- [Oracle Java SE 27 — EdECPrivateKey](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html): giao diện private key và dữ liệu nhạy cảm.
- [Oracle Java SE 26 — NamedParameterSpec](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/NamedParameterSpec.html): `ED25519`, `ED448` và `getName()`.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html): tên chuẩn cho các engine JCA, Ed25519, Ed448, EdDSA và XDH.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): định nghĩa thuật toán và biểu diễn chữ ký.

Bài này chỉ đề cập các API và thực hành còn áp dụng đến hiện nay, tránh phương thức không còn được khuyến nghị và không sử dụng mã preview hoặc legacy.