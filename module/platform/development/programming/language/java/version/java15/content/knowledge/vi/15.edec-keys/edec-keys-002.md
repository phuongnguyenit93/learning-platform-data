# NamedParameterSpec.ED25519 và ED448 — tham số khóa EdEC trong Java 15

> **Mục tiêu:** Phân biệt hai bộ tham số chuẩn **`NamedParameterSpec.ED25519`** và **`NamedParameterSpec.ED448`**, tạo cặp khóa EdEC bằng Java Cryptography Architecture (JCA), ký/xác minh bằng EdDSA, kiểm tra tham số khóa, lưu/đọc khóa đúng định dạng và hiểu những giới hạn khi dùng dữ liệu thực tế. Bài chỉ sử dụng **API Java 15 đã chính thức và vẫn được hỗ trợ trên Java hiện đại**, với ví dụ chạy bằng **Java 17+**, không dùng API preview hay thuật toán lỗi thời.

## 1. Vì sao có Ed25519, Ed448 và NamedParameterSpec?

**EdDSA** (*Edwards-curve Digital Signature Algorithm*) là họ thuật toán **chữ ký số** dựa trên đường cong Edwards, được tiêu chuẩn hóa bởi **RFC 8032**. Java 15 bổ sung hỗ trợ EdDSA tiêu chuẩn qua **JEP 339**, bao gồm hai bộ tham số phổ biến:

- **Ed25519:** dùng đường cong edwards25519; chữ ký theo biến thể Ed25519 tiêu chuẩn có độ dài **64 byte**.
- **Ed448:** dùng đường cong edwards448; chữ ký theo biến thể Ed448 tiêu chuẩn có độ dài **114 byte**.

Các giá trị Java:

~~~java
import java.security.spec.NamedParameterSpec;

NamedParameterSpec a = NamedParameterSpec.ED25519;
NamedParameterSpec b = NamedParameterSpec.ED448;

System.out.println(a.getName()); // Ed25519
System.out.println(b.getName()); // Ed448
~~~

là những **đối tượng mô tả tên bộ tham số**, không phải private key, public key hoặc đối tượng thực hiện ký. Hai hằng này có từ **Java 15**; bản thân class `NamedParameterSpec` có từ Java 11 và còn phục vụ một số bộ tham số đặt tên khác.

**Giải thích tên gọi:**

- **EdEC**: các kiểu khóa theo đường cong Edwards (*Edwards-Curve cryptography*) và API liên quan như `EdECKey`, `EdECPublicKey`, `EdECPrivateKey`.
- **EdDSA**: thuật toán dùng khóa ấy để **ký và xác minh chữ ký số**.
- **`NamedParameterSpec`**: chỉ rõ **bộ tham số nào** (ở đây là Ed25519 hay Ed448), ví dụ khi khởi tạo bộ sinh khóa.
- **`KeyPairGenerator` / `Signature` / `KeyFactory`**: các dịch vụ JCA thực hiện **sinh khóa**, **ký/xác minh**, và **chuyển khóa giữa representation đã mã hóa và object**.

Đừng viết code với giả định rằng chỉ có một hằng `NamedParameterSpec` là đã có cặp khóa. Muốn ký được phải tạo **`KeyPair`** và dùng **`Signature`** với private key; muốn xác minh phải dùng public key phù hợp.

## 2. So sánh Ed25519 và Ed448 theo cách chọn thuật toán

| Thuộc tính | Ed25519 | Ed448 |
| --- | --- | --- |
| Hằng tên trong Java | `NamedParameterSpec.ED25519` | `NamedParameterSpec.ED448` |
| `getName()` | `"Ed25519"` | `"Ed448"` |
| Họ thuật toán | EdDSA trên Edwards curve | EdDSA trên Edwards curve |
| Public key thô theo RFC 8032 | 32 byte | 57 byte |
| Private key seed theo RFC 8032 | 32 byte | 57 byte |
| Chữ ký tiêu chuẩn | **64 byte** | **114 byte** |
| Mức an toàn ước tính của bộ tham số | Khoảng 128 bit | Khoảng 224 bit |
| Hàm băm nội bộ của thiết kế RFC | SHA-512 | SHAKE256 |
| Tên dịch vụ JCA thường dùng | `"Ed25519"` hoặc generic `"EdDSA"` | `"Ed448"` hoặc generic `"EdDSA"` |
| Điểm cần cân nhắc | Phổ biến và thường có hỗ trợ liên thông rộng | Kích thước lớn hơn; kiểm tra rõ hệ sinh thái, giao thức và provider |

**Không suy ra rằng Ed448 tự động tốt hơn cho mọi ứng dụng.** Cần xét yêu cầu an toàn, tính tương thích với bên thứ ba, thư viện/protocol hiện có, định dạng khóa, tốc độ và khả năng quản lý khóa. Với nhiều ứng dụng ký số thông thường, Ed25519 là lựa chọn thực dụng; Ed448 phù hợp khi yêu cầu cụ thể cần bộ tham số đó và mọi thành phần đều hỗ trợ.

Kích thước **public key thô** và **seed** trong bảng là kích thước thông số RFC, **không phải** độ dài trả về bởi `PublicKey.getEncoded()` hay `PrivateKey.getEncoded()`. Hai phương thức Java thường sử dụng **X.509 SubjectPublicKeyInfo** và **PKCS#8**, là cấu trúc mã hóa chứa metadata nên dài hơn raw key material.

## 3. Hai constant chỉ định tham số, không tự sinh khóa

Cách rõ ràng là khởi tạo dịch vụ generic `EdDSA` bằng bộ tham số:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.spec.NamedParameterSpec;

KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(NamedParameterSpec.ED25519);
KeyPair pair = generator.generateKeyPair();
~~~

Đây là **đoạn mã trong một method** có xử lý `GeneralSecurityException`; chương trình đầy đủ ở mục 6.

Nếu muốn Ed448, đổi thành:

~~~java
generator.initialize(NamedParameterSpec.ED448);
KeyPair ed448Pair = generator.generateKeyPair();
~~~

**Nên chỉ định tham số tường minh.** Khi gọi `KeyPairGenerator.getInstance("EdDSA")` nhưng không khởi tạo bộ tham số, lựa chọn mặc định có thể phụ thuộc **provider**. Đừng dựa vào mặc định khi ứng dụng có hợp đồng cụ thể yêu cầu Ed25519 hoặc Ed448.

Một cách khác là yêu cầu thuật toán cụ thể:

~~~java
KeyPairGenerator generator =
        KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = generator.generateKeyPair();
~~~

Provider hỗ trợ `Ed25519` trực tiếp có thể chọn sẵn bộ tham số tương ứng. Với ứng dụng cần thay đổi giữa Ed25519/Ed448 bằng cấu hình, cách generic `"EdDSA"` + `NamedParameterSpec` có lợi vì giao diện thống nhất; với code cố định cho một thuật toán, tên cụ thể giúp ý định rõ ràng.

### Vì sao không so sánh constant bằng `==` hoặc `equals`?

`NamedParameterSpec` lưu **tên** bộ tham số. Một đối tượng tạo qua `new NamedParameterSpec("Ed25519")` có thể mang **cùng tên** nhưng không phải **cùng object** với hằng:

~~~java
NamedParameterSpec named = new NamedParameterSpec("Ed25519");

System.out.println(
        named.getName().equals(NamedParameterSpec.ED25519.getName())); // true
System.out.println(named.equals(NamedParameterSpec.ED25519));       // false
~~~

Lý do: `NamedParameterSpec` không định nghĩa value-based `equals` theo tên; hành vi thừa hưởng từ `Object` không tự biến hai instance thành bằng nhau. Trong code cần **phân nhánh theo tên**, so sánh `getName()` với hằng tên hoặc dùng cách nhận diện chuẩn được API quy định, chứ không trông đợi object identity.

**Cũng không được tạo tên tùy ý rồi cho rằng provider sẽ hỗ trợ.** Constructor `new NamedParameterSpec("SomeName")` chỉ tạo object mô tả tên; khi truyền vào bộ sinh khóa/thuật toán, provider mới kiểm tra sự hỗ trợ. `NamedParameterSpec.ED25519` và `ED448` là tên chuẩn, nhưng **có tên chuẩn vẫn không đảm bảo mọi provider triển khai thuật toán đó**.

## 4. Không nhầm Ed25519/Ed448 với X25519/X448 và ECDSA

Java còn có:

~~~java
NamedParameterSpec.X25519
NamedParameterSpec.X448
~~~

Đây là các bộ tham số dành cho **XDH key agreement** (thỏa thuận khóa dựa trên Montgomery curves), không phải EdDSA chữ ký số. Tên có phần số giống nhau nhưng mục đích và thuật toán khác nhau:

| Tên | Hướng sử dụng | Dịch vụ điển hình |
| --- | --- | --- |
| `Ed25519`, `Ed448` | **Chữ ký số** EdDSA | `Signature`, `KeyPairGenerator`, `KeyFactory` |
| `X25519`, `X448` | **Thỏa thuận khóa** XDH | `KeyAgreement`, `KeyPairGenerator`, `KeyFactory` |
| `EC` cùng những tên `SHA256withECDSA`... | **ECDSA** dựa trên mô hình EC khác | `Signature` với khóa EC phù hợp |

**Không lấy khóa Ed25519 làm khóa X25519 theo cách ép kiểu hoặc đổi tên `Key.getAlgorithm()`**. Sự chuyển đổi liên quan tới biểu diễn toán học/chính sách giao thức cần thiết kế và kiểm chứng riêng; JCA không tự cho phép dùng lẫn các keys như cùng một loại.

Tương tự, **`EdDSA` không phải `ECDSA`**. Đừng cấu hình `Signature.getInstance("SHA256withECDSA")` rồi đưa khóa Ed25519 vào; đó là những thuật toán và kiểu khóa khác nhau.

## 5. Luồng JCA chuẩn: generate → sign → verify → import/export

~~~text
NamedParameterSpec.ED25519 hoặc ED448
    |
    v
KeyPairGenerator("EdDSA").initialize(spec)
    |
    v
KeyPair { PrivateKey, PublicKey }
    |                  |
    | PrivateKey       | PublicKey
    v                  v
Signature.initSign     Signature.initVerify
Signature.update(...)  Signature.update(...)
Signature.sign()       Signature.verify(signature)
    |                  |
    v                  v
Chữ ký byte[]           true hoặc false
~~~

Những điều quan trọng:

1. **Private key** chỉ dùng ở bên có quyền ký. **Public key** được chia sẻ cho bên xác minh qua cơ chế đáng tin.
2. `Signature.update(...)` nhận **bytes**, không nhận một “chuỗi có ngữ nghĩa” trừu tượng. Khi ký văn bản, thống nhất **UTF-8** hoặc serialization protocol được xác định trước.
3. `Signature.sign()` trả bytes chữ ký. Với mode Ed25519/Ed448 tiêu chuẩn, độ dài lần lượt là **64/114 byte**.
4. `Signature.verify(...)` trả `true` nếu chữ ký hợp lệ cho **cùng dữ liệu, cùng thuật toán/mode/context và public key tương ứng**; trả `false` với chữ ký sai hợp lệ về cú pháp, hoặc có thể ném exception nếu dữ liệu/khóa/signature không được API chấp nhận.
5. Mỗi lần tạo `Signature` rồi `initSign/initVerify` đặt trạng thái vận hành; ví dụ dùng **instance riêng cho từng thao tác** để tránh nhầm lại trạng thái.
6. Không dùng `String.getBytes()` không có charset khi yêu cầu byte-to-byte ổn định; dùng `StandardCharsets.UTF_8`.

### Phân biệt lỗi API với chữ ký không hợp lệ

- **Không có provider hỗ trợ thuật toán:** `NoSuchAlgorithmException` khi gọi `getInstance`.
- **Sai bộ tham số khi khởi tạo generator:** `InvalidAlgorithmParameterException`.
- **Sai loại khóa cho thuật toán:** `InvalidKeyException` lúc `initSign` hoặc `initVerify`.
- **Chữ ký không khớp dữ liệu/khóa/điều kiện mode:** thông thường `verify` trả `false`; những signature encodings sai format có thể bị provider từ chối bằng `SignatureException`.
- **Khóa encoded bị lỗi cấu trúc:** `InvalidKeySpecException` khi dùng `KeyFactory`.

Ứng dụng nên phân biệt **lỗi cấu hình/provider**, **dữ liệu không hợp lệ** và **xác minh thất bại**, thay vì bắt mọi exception rồi kết luận rằng “chữ ký sai”.

## 6. Chương trình đầy đủ Java 17+: hai bộ tham số, sinh khóa và ký/xác minh

Tạo file **EdNamedParametersDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.interfaces.EdECKey;
import java.security.interfaces.EdECPrivateKey;
import java.security.interfaces.EdECPublicKey;
import java.security.spec.NamedParameterSpec;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;

public class EdNamedParametersDemo {
    private static byte[] sign(PrivateKey privateKey, String algorithm,
            byte[] message) throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(privateKey);
        signer.update(message);
        return signer.sign();
    }

    private static boolean verify(PublicKey publicKey, String algorithm,
            byte[] message, byte[] signature) throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(publicKey);
        verifier.update(message);
        return verifier.verify(signature);
    }

    private static void runCurve(NamedParameterSpec spec) throws Exception {
        String algorithm = spec.getName();
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
        generator.initialize(spec);
        KeyPair pair = generator.generateKeyPair();
        byte[] message =
                "Signed message: Java 15+".getBytes(StandardCharsets.UTF_8);
        byte[] altered =
                "Signed message: altered".getBytes(StandardCharsets.UTF_8);

        byte[] signature = sign(pair.getPrivate(), algorithm, message);
        byte[] signatureAgain = sign(pair.getPrivate(), algorithm, message);
        boolean valid = verify(pair.getPublic(), algorithm, message, signature);
        boolean tamperRejected =
                !verify(pair.getPublic(), algorithm, altered, signature);

        KeyFactory keyFactory = KeyFactory.getInstance(algorithm);
        PublicKey importedPublic = keyFactory.generatePublic(
                new X509EncodedKeySpec(pair.getPublic().getEncoded()));
        PrivateKey importedPrivate = keyFactory.generatePrivate(
                new PKCS8EncodedKeySpec(pair.getPrivate().getEncoded()));
        byte[] fromImported = sign(importedPrivate, algorithm, message);
        boolean importedValid =
                verify(importedPublic, algorithm, message, fromImported);

        System.out.println("curve=" + algorithm);
        System.out.println("publicParams="
                + ((EdECKey) pair.getPublic()).getParams().getName());
        System.out.println("privateParams="
                + ((EdECKey) pair.getPrivate()).getParams().getName());
        System.out.println("publicIsEdEC="
                + (pair.getPublic() instanceof EdECPublicKey));
        System.out.println("privateIsEdEC="
                + (pair.getPrivate() instanceof EdECPrivateKey));
        System.out.println("signatureBytes=" + signature.length);
        System.out.println("valid=" + valid);
        System.out.println("tamperRejected=" + tamperRejected);
        System.out.println("repeatSignatureEqual="
                + Arrays.equals(signature, signatureAgain));
        System.out.println("publicFormat=" + pair.getPublic().getFormat());
        System.out.println("privateFormat=" + pair.getPrivate().getFormat());
        System.out.println("importedKeysValid=" + importedValid);
    }

    public static void main(String[] args) throws Exception {
        System.out.println("named25519="
                + NamedParameterSpec.ED25519.getName());
        System.out.println("named448="
                + NamedParameterSpec.ED448.getName());
        System.out.println("xdhIsDifferent="
                + !NamedParameterSpec.ED25519.getName()
                        .equals(NamedParameterSpec.X25519.getName()));

        runCurve(NamedParameterSpec.ED25519);
        runCurve(NamedParameterSpec.ED448);
    }
}
~~~

Biên dịch/chạy với Java 17+:

~~~bash
javac --release 17 -encoding UTF-8 EdNamedParametersDemo.java
java EdNamedParametersDemo
~~~

**Kết quả đã đối chiếu bằng bản chạy thật trên JDK có SunEC:**

~~~text
named25519=Ed25519
named448=Ed448
xdhIsDifferent=true
curve=Ed25519
publicParams=Ed25519
privateParams=Ed25519
publicIsEdEC=true
privateIsEdEC=true
signatureBytes=64
valid=true
tamperRejected=true
repeatSignatureEqual=true
publicFormat=X.509
privateFormat=PKCS#8
importedKeysValid=true
curve=Ed448
publicParams=Ed448
privateParams=Ed448
publicIsEdEC=true
privateIsEdEC=true
signatureBytes=114
valid=true
tamperRejected=true
repeatSignatureEqual=true
publicFormat=X.509
privateFormat=PKCS#8
importedKeysValid=true
~~~

**Vì sao không in khóa/private seed hoặc chữ ký vào stdout?** Chữ ký và public key có thể công khai theo giao thức, nhưng **private key phải được bảo vệ**; bài chỉ in **tên tham số, kiểu object, độ dài chữ ký và trạng thái kiểm tra**, không xuất bản private material. Các bytes khóa tạo bởi mỗi lần chạy là ngẫu nhiên, nên **không có đầu ra khóa cố định** cần so sánh.

### Đọc kết quả theo nhóm

- `named25519` và `named448` là giá trị `NamedParameterSpec.getName()`; hai constant không phải nơi cất khóa.
- `xdhIsDifferent=true` xác nhận ký hiệu tên Ed25519 khác X25519; đừng nhầm EdDSA và XDH.
- `publicParams/privateParams` cho biết **bộ tham số thực sự của khóa tạo ra** qua interface `EdECKey`, không suy từ tên biến.
- `publicIsEdEC/privateIsEdEC=true`: trong provider thử nghiệm, hai object hỗ trợ interfaces `EdECPublicKey` và `EdECPrivateKey`.
- `signatureBytes=64/114` đúng kích thước signature của Ed25519/Ed448 tiêu chuẩn.
- `valid=true`: chữ ký hợp lệ với public key tương ứng và dữ liệu gốc.
- `tamperRejected=true`: đổi nội dung thông điệp khiến xác minh thất bại.
- `repeatSignatureEqual=true`: với cùng khóa, message, mode và thông số, chữ ký EdDSA theo RFC 8032 là deterministic. Điều này **không** có nghĩa private key có thể được tái sử dụng vô hạn hoặc rằng thông điệp không cần ràng buộc ngữ cảnh.
- `publicFormat=X.509`, `privateFormat=PKCS#8` phản ánh định dạng khóa được provider ở thử nghiệm xuất ra. Với provider khác (nhất là hardware-backed), `getEncoded()` có thể trả `null` hoặc không hỗ trợ xuất private key; đừng coi mã minh họa export là cam kết cho mọi môi trường.
- `importedKeysValid=true`: khóa được giải mã lại bằng `KeyFactory` có thể dùng để ký và verify, chứng minh tương thích của **cặp format + algorithm + provider** trong môi trường này.

## 7. EdECKey và các interfaces liên quan đến tên tham số

Các giao diện hữu ích trong `java.security.interfaces`:

| API | Cho biết điều gì? | Ghi chú |
| --- | --- | --- |
| `EdECKey.getParams()` | `NamedParameterSpec` của khóa EdEC | Dùng `getName()` để xác định Ed25519/Ed448 |
| `EdECPublicKey.getPoint()` | `EdECPoint` của public key | Cung cấp tọa độ `y` và bit chẵn/lẻ của `x` theo biểu diễn API |
| `EdECPrivateKey.getBytes()` | `Optional<byte[]>` chứa raw private seed khi có thể xuất | **Có thể là empty**; không log/export nếu không cần |
| `EdECPublicKeySpec` | Spec để tái tạo public key từ `NamedParameterSpec` + `EdECPoint` | Không phải cấu trúc bytes RFC có thể dùng trực tiếp |
| `EdECPrivateKeySpec` | Spec để tái tạo private key từ `NamedParameterSpec` + raw bytes | Cần hiểu rõ nguồn raw key, định dạng và bảo vệ bí mật |

Ví dụ chỉ đọc tên bộ tham số:

~~~java
EdECKey ecKey = (EdECKey) pair.getPublic();
String parameterName = ecKey.getParams().getName();
System.out.println(parameterName); // Ed25519 hoặc Ed448
~~~

Đây là code **trong method** có biến `pair` được tạo đúng thuật toán. Không ép kiểu `EdECKey` với một RSA/ECDSA/XDH key rồi kỳ vọng thành công; chỉ dùng khi implementation và giao thức thực sự là khóa EdEC.

`EdECPublicKey.getPoint()` **không trả về một mảng 32/57 byte thô**; nó trả object biểu diễn điểm. Nếu cần format raw public key của RFC, phải tuân theo chính xác **quy tắc encoding byte order và sign bit** của RFC 8032 hoặc dùng thư viện chuẩn đáng tin, không tự nối bytes từ `BigInteger.toByteArray()` và mong tương thích.

### Vì sao private seed là `Optional`?

Một khóa riêng có thể được lưu trong HSM, smart card hoặc provider không cho xuất vật liệu bí mật. API `EdECPrivateKey.getBytes()` vì thế trả **`Optional<byte[]>`**: không phải khóa nào cũng cho biết raw seed. Với ứng dụng hiện đại, việc **không thể xuất private key** có thể chính là một yêu cầu bảo mật, chứ không phải lỗi.

Không dựa vào `getBytes().get()` mà không kiểm tra `isPresent()`; tránh sao chép private seed vào log, file tạm hay exception message. Nếu thực sự phải xử lý bytes nhạy cảm, giới hạn phạm vi tồn tại của array và xóa nó khi thích hợp; lưu ý JVM không cam kết đã xóa mọi bản sao nội bộ của khóa.

## 8. Lưu/đọc khóa: X.509 SubjectPublicKeyInfo và PKCS#8

Khi một khóa Ed25519/Ed448 hỗ trợ encoding, `getEncoded()` của public key thường tạo **X.509 SubjectPublicKeyInfo DER** và private key tạo **PKCS#8 DER**:

~~~java
byte[] publicDer = pair.getPublic().getEncoded();
byte[] privateDer = pair.getPrivate().getEncoded();
~~~

Đây là **mã minh họa trong method**, không viết bytes ra file hay hiển thị chúng. `getFormat()` dùng để kiểm tra format được khai báo; `getEncoded()` có thể trả `null` tùy provider. Trong chương trình mục 6, provider cụ thể hỗ trợ cả hai.

Nhập lại:

~~~java
KeyFactory factory = KeyFactory.getInstance("Ed25519");

PublicKey publicKey = factory.generatePublic(
        new X509EncodedKeySpec(publicDer));
PrivateKey privateKey = factory.generatePrivate(
        new PKCS8EncodedKeySpec(privateDer));
~~~

**Những giới hạn cần nêu rõ:**

- `X509EncodedKeySpec` biểu diễn **public key encoding theo SubjectPublicKeyInfo**, không phải DER certificate X.509 đầy đủ.
- `PKCS8EncodedKeySpec` có thể chứa **private key unencrypted bytes**. **Không** dùng plain PKCS#8 như kho lưu private key an toàn; dùng keystore/cơ chế quản lý khóa đáng tin, kiểm soát quyền và encryption at rest khi phù hợp.
- Chỉ biết `publicDer.length` **không** cho biết raw key length; encoding có thêm wrapper/algorithm identifier.
- Private key của hardware-backed provider thường **không thể export**, vì vậy ứng dụng cần thiết kế để ký qua provider mà không lấy raw bytes.
- Import `Ed448` bằng `KeyFactory("Ed25519")` là sai bộ tham số; chọn factory tương ứng hoặc generic `EdDSA` được provider hỗ trợ.
- Khi gửi public key qua hệ thống khác, cần ràng buộc **nguồn tin cậy, thuật toán, key identifier, protocol và format**. Public key hợp lệ về mặt toán học không tự chứng minh ai sở hữu khóa.

### Đừng tự sửa DER hoặc “đoán curve theo số bytes”

Public key raw 32/57 bytes, signature 64/114 bytes; nhưng DER encoding dài hơn raw format. Không nên lấy chuỗi bytes đầu vào mà suy “độ dài 32 nghĩa là Ed25519 PKCS#8”. Sử dụng đúng parser/spec theo giao thức, và xác minh `getParams().getName()` sau khi tạo key object.

## 9. EdDSAParameterSpec: context và prehash là chiều khác với curve

`NamedParameterSpec` chọn **đường cong/bộ tham số khóa**. Nó **không** thay thế `EdDSAParameterSpec` — class mô tả **mode của chữ ký**, gồm:

- **`prehash=false`, không có context:** Ed25519 hoặc Ed448 tiêu chuẩn.
- **`prehash=false`, có context:** Ed25519ctx (với Ed25519) hoặc Ed448 sử dụng context.
- **`prehash=true`:** Ed25519ph hoặc Ed448ph theo RFC 8032; thông điệp được xử lý theo mode prehash của thuật toán, không phải đơn thuần “tự hash rồi ký bình thường”.

Các mode này có trong **Java 15+** và vẫn có hiệu lực ngày nay. `EdDSAParameterSpec(boolean prehash, byte[] context)` nhận context dài **tối đa 255 byte** theo RFC 8032, không phải 255 ký tự Unicode. `context` là **bytes**, và người ký với người xác minh phải dùng **đúng cùng context và mode**.

**Mục đích context:** có thể phân tách miền sử dụng chữ ký, ví dụ ký dữ liệu `orders-v1` tách với `payments-v1` để hạn chế nhầm lẫn giữa các loại thông điệp trong cùng một hệ thống. Nhưng context không tự thay thế một protocol được thiết kế đúng: vẫn cần xác định message format, version, key identifier và validation chính xác.

### Ví dụ thứ hai: context đúng thì verify, sai thì không

Tạo **EdModesDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.security.spec.EdDSAParameterSpec;
import java.security.spec.NamedParameterSpec;

public class EdModesDemo {
    static byte[] sign(KeyPair pair, byte[] message, byte[] context)
            throws Exception {
        Signature signer = Signature.getInstance("EdDSA");
        signer.setParameter(new EdDSAParameterSpec(false, context));
        signer.initSign(pair.getPrivate());
        signer.update(message);
        return signer.sign();
    }

    static boolean verify(KeyPair pair, byte[] message,
            byte[] context, byte[] signature) throws Exception {
        Signature verifier = Signature.getInstance("EdDSA");
        verifier.setParameter(new EdDSAParameterSpec(false, context));
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        byte[] message = "order=123".getBytes(StandardCharsets.UTF_8);
        byte[] domainA = "orders-v1".getBytes(StandardCharsets.US_ASCII);
        byte[] domainB = "payments-v1".getBytes(StandardCharsets.US_ASCII);

        for (NamedParameterSpec curve :
                new NamedParameterSpec[] {
                    NamedParameterSpec.ED25519, NamedParameterSpec.ED448
                }) {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
            generator.initialize(curve);
            KeyPair pair = generator.generateKeyPair();
            byte[] sig = sign(pair, message, domainA);

            System.out.println("curve=" + curve.getName());
            System.out.println("verifySameContext="
                    + verify(pair, message, domainA, sig));
            System.out.println("verifyDifferentContext="
                    + verify(pair, message, domainB, sig));
            System.out.println("prehashDefault="
                    + new EdDSAParameterSpec(false).isPrehash());
        }

        try {
            new EdDSAParameterSpec(false, new byte[256]);
            System.out.println("oversizeContext=UNEXPECTED");
        } catch (java.security.InvalidParameterException expected) {
            System.out.println("oversizeContext=InvalidParameterException");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EdModesDemo.java
java EdModesDemo
~~~

Kết quả đã kiểm chứng:

~~~text
curve=Ed25519
verifySameContext=true
verifyDifferentContext=false
prehashDefault=false
curve=Ed448
verifySameContext=true
verifyDifferentContext=false
prehashDefault=false
oversizeContext=InvalidParameterException
~~~

**Giải thích:** Mỗi đường cong dùng cùng cấu trúc code nhưng key pairs riêng biệt. Với cùng `pair` và message, verifier dùng `domainA` chấp nhận signature, còn dùng `domainB` từ chối. `EdDSAParameterSpec(false)` có `isPrehash() == false`. Context quá 255 bytes bị từ chối bằng `InvalidParameterException`.

**Cảnh giác liên thông:** Nếu một giao thức bên ngoài chỉ hỗ trợ **pure Ed25519**, chữ ký Ed25519ctx sẽ **không** tự được chấp nhận. Với Ed448, context là một phần của ngữ nghĩa chữ ký. Bên ký và bên xác minh phải thống nhất curve, mode, context và exact message bytes; không mặc định mọi hệ thống hỗ trợ toàn bộ biến thể RFC 8032.

## 10. Cảnh báo về tham số và kiểu khóa không tương thích

`Ed25519` và `Ed448` **không thể thay thế cho nhau** chỉ vì đều là EdDSA. Ví dụ trong provider JDK đã kiểm thử:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
generator.initialize(NamedParameterSpec.ED448);
// InvalidAlgorithmParameterException
~~~

Dùng `Signature.getInstance("Ed25519")` nhưng đưa **Ed448 public key** vào `initVerify` sẽ bị từ chối do khóa không đúng thuật toán, điển hình là **`InvalidKeyException`**. Hai kiểu lỗi khác nhau:

- **`InvalidAlgorithmParameterException`:** cấu hình generator Ed25519 với parameter Ed448 không hợp lệ.
- **`InvalidKeyException`:** đưa một public/private key không tương thích cho một Signature algorithm.

Mọi thứ trong đây đều là những kiểu lỗi hiện hành, không nên “sửa” bằng cách đổi key algorithm name thủ công trong object.

### Kiểm tra khóa theo tham số thực tế

~~~java
String actualCurve =
        ((EdECKey) pair.getPublic()).getParams().getName();

if (!actualCurve.equals("Ed25519")) {
    throw new IllegalArgumentException("Unexpected EdEC curve");
}
~~~

Đây là đoạn **trong method** có `pair` và import `EdECKey`. Khi public key tới từ nguồn ngoài, trước khi xác minh nên kiểm tra **cả algorithm/curve và nguồn tin cậy** theo hợp đồng của hệ thống. Hợp lệ về định dạng hoặc có `getParams()` đúng không đủ chứng minh key được phép xác thực một chủ thể cụ thể.

## 11. Các sai lầm bảo mật và vận hành dễ gặp

1. **Dùng `NamedParameterSpec.ED25519` để thực hiện key agreement.** Sai: Ed25519/Ed448 thuộc EdDSA chữ ký; `X25519`/`X448` và `KeyAgreement` phục vụ XDH.
2. **Dùng `ECDSA` với khóa EdEC.** Hai họ thuật toán không tự tương thích.
3. **Không chỉ định curve khi dùng generic `"EdDSA"`.** Đừng dựa vào provider default nếu giao thức cần tên cụ thể.
4. **So sánh `NamedParameterSpec` bằng object equality.** Dùng `getName()` hoặc quy tắc rõ ràng; hai instance cùng tên không mặc nhiên `equals`.
5. **Cho rằng độ dài `getEncoded()` bằng raw seed/public key length.** Không đúng với X.509/PKCS#8 DER.
6. **Cố export private seed từ mọi provider.** `EdECPrivateKey.getBytes()` là `Optional`; key trong HSM có thể không xuất được.
7. **In private key hoặc PKCS#8 bytes vào log.** Dữ liệu đó có thể làm lộ quyền ký; tránh hoàn toàn.
8. **Ký String mà không xác định encoding/serialization.** Hai bên có thể ký và verify hai dãy bytes khác nhau dù nhìn giống nhau.
9. **Dùng `String.getBytes()` không truyền charset.** Với giao thức liên thông, bắt buộc xác định charset, ví dụ UTF-8.
10. **Tự hash message bằng SHA-512/SHAKE256 rồi ký pure Ed25519/Ed448.** Đây **không** tương đương Ed25519ph/Ed448ph; muốn prehash dùng mode được API chỉ rõ và thống nhất giao thức.
11. **Bật context ở bên ký nhưng quên ở bên xác minh.** Mode/context phải khớp từng byte.
12. **Cho rằng signature deterministic nghĩa là không cần kiểm tra message tampering.** Verify vẫn phải dùng nguyên bytes mà phía ký đã ký.
13. **Để public key từ input người dùng quyết định ai được xác thực.** Verify đúng chỉ chứng minh biết private key tương ứng với **public key đã chọn**, không tự xác thực danh tính người gửi.
14. **Chỉ kiểm tra `verify() == true` mà bỏ qua thuật toán/mục đích key.** Cần ràng buộc algorithm, key id, policy, thời hạn/thu hồi khóa và phiên bản giao thức.
15. **Đọc/ghi private DER plain mà không bảo vệ.** Dùng hệ thống quản lý khóa hoặc keystore phù hợp, quyền truy cập và encryption theo yêu cầu.
16. **Không kiểm tra provider.** `NoSuchAlgorithmException` không phải lỗi do Ed25519 “bị bỏ”; nó có thể do provider JCA hiện tại không triển khai tên đó.
17. **Nhầm chữ ký số với mã hóa dữ liệu.** EdDSA cung cấp xác thực và tính toàn vẹn theo khóa ký, **không giữ bí mật nội dung**; nếu cần confidentiality, phải dùng giải pháp encryption riêng.
18. **Dùng một chữ ký để chứng minh hành động khác mà không ràng buộc domain/format.** Xác định chính xác message và ngữ cảnh ứng dụng; cân nhắc context/protocol version.

## 12. Lựa chọn Ed25519 hay Ed448 cho ứng dụng mới

**Ed25519** thường phù hợp khi ưu tiên hệ sinh thái phổ biến, chữ ký nhỏ và mức an toàn gần 128 bit; **Ed448** phù hợp khi có yêu cầu cụ thể về bộ tham số đó và các bên đều hỗ trợ. Quyết định không nên dựa riêng vào độ dài tên hay tưởng Ed448 “thay thế” Ed25519 trong mọi protocol.

Khi thiết kế hệ thống:

- **Ghi rõ curve ở schema/config**: `"Ed25519"` hoặc `"Ed448"`. Không suy chỉ từ bytes hay loại key wrapper.
- **Kiểm tra provider từ đầu**: đảm bảo `KeyPairGenerator`, `Signature` và `KeyFactory` dùng được trong môi trường triển khai (JDK, provider, HSM).
- **Thiết kế hợp đồng public key format**: X.509 SPKI, JWK hoặc format riêng nếu giao thức có quy định. Không tự mix raw RFC bytes với DER.
- **Định nghĩa mode**: pure EdDSA hay phiên bản context/prehash; khớp với bên xác minh.
- **Định nghĩa message representation**: bytes của JSON canonical, protobuf/CBOR serialization hoặc một dạng byte chính xác khác do protocol quyết định; không ký dạng text hiển thị mơ hồ.
- **Xác định định danh và vòng đời khóa**: nơi lưu private key, quyền dùng, key rotation, rollover, revoke và audit.
- **Có test liên thông**: kiểm chứng chữ ký với một implementation độc lập khi hệ thống đa ngôn ngữ; dùng vector RFC 8032 nếu bài toán liên thông cần.
- **Không tự viết EdDSA primitive**: dùng JCA provider đã được bảo trì và tuân theo RFC thay vì tự triển khai toán học hoặc xử lý seed/point.

## 13. Kiểm thử nên bao phủ những gì?

| Kiểm thử | Mong đợi |
| --- | --- |
| `NamedParameterSpec.ED25519.getName()` | `"Ed25519"` |
| `NamedParameterSpec.ED448.getName()` | `"Ed448"` |
| Generic `EdDSA` + `initialize(ED25519)` | Key params báo Ed25519 |
| Generic `EdDSA` + `initialize(ED448)` | Key params báo Ed448 |
| Ký rồi verify với cùng data/key | `true` |
| Thay một byte message | Verify `false` |
| Dùng wrong public key | Verify `false` hoặc API báo không hợp lệ tùy case |
| Dùng sai algorithm/curve khi `initVerify` | `InvalidKeyException` |
| Export/import X.509 và PKCS#8, nếu provider hỗ trợ | Key objects mới verify/sign được |
| Dùng context đúng | `true` |
| Dùng context khác | `false` |
| Context dài 256 bytes | `InvalidParameterException` |
| Gọi `EdECPrivateKey.getBytes()` | Xử lý cả `Optional.empty()` |
| Provider không hỗ trợ | Có thông báo cấu hình rõ; không âm thầm đổi sang thuật toán khác |

### Không dùng khóa mẫu cố định của bài học trong production

Ví dụ `KeyPairGenerator.generateKeyPair()` được dùng để tạo khóa test mỗi lần chạy. Trong production, yêu cầu bảo mật phải đi kèm **key storage**, quyền truy cập và quy trình rotation. Tránh lưu private DER trong biến môi trường/plain text config hoặc log; nếu cần bảo vệ key bằng password/keystore, phải chọn provider và format đáp ứng môi trường triển khai.

Khi dùng deterministic signatures, hai lần ký **cùng private key + message + mode/context** cho chữ ký giống nhau, nhưng **đây không thay thế kiểm tra tính tin cậy của public key hoặc thiết kế chống replay**. Nếu protocol cần nonce, timestamp hoặc sequence number để chống replay, những thông tin đó phải nằm trong **message bytes được ký** và được phía nhận kiểm chứng.

## 14. Bài luyện tập và tiêu chí đạt

**Bài 1 — Nhận biết tham số.** In `ED25519.getName()` và `ED448.getName()`. **Đạt** khi thu được `Ed25519`, `Ed448` và giải thích đây là **parameter specs**, không phải key pairs.

**Bài 2 — So sánh hai thuật toán.** Chạy `EdNamedParametersDemo` với cả hai curve. **Đạt** khi ký/xác minh thành công, thấy signature lengths **64/114 bytes** và tên params khớp.

**Bài 3 — Kiểm tra tampering.** Thay đổi message nhưng giữ signature cũ. **Đạt** khi verify trả `false`; giải thích chữ ký chỉ áp dụng cho đúng bytes đã ký.

**Bài 4 — Encode/import khóa.** Dùng `X509EncodedKeySpec` và `PKCS8EncodedKeySpec` để nhập lại keys. **Đạt** khi vẫn ký/xác minh được, và nêu rõ DER wrapper không phải raw key length.

**Bài 5 — Không nhầm XDH.** Phân biệt `ED25519` với `X25519`, `ED448` với `X448`. **Đạt** khi chỉ đúng **Signature** so với **KeyAgreement**.

**Bài 6 — Đọc param từ key.** Lấy `EdECKey.getParams().getName()` từ public/private keys. **Đạt** khi tự nhận ra curve của key thay vì đoán từ tên biến.

**Bài 7 — Object equality.** Tạo `new NamedParameterSpec("Ed25519")`, so `equals` với hằng và so `getName`. **Đạt** khi hiểu **cùng tên không đồng nghĩa cùng instance**.

**Bài 8 — Context binding.** Chạy `EdModesDemo`, ký với `"orders-v1"` và verify với `"payments-v1"`. **Đạt** khi hiểu vì sao khác context cho `false`.

**Bài 9 — Key compatibility.** Khởi tạo generator Ed25519 với `ED448`, hoặc dùng Ed448 public key để `initVerify` bằng thuật toán Ed25519. **Đạt** khi phân biệt `InvalidAlgorithmParameterException` và `InvalidKeyException`.

**Bài 10 — Thiết kế giao thức.** Phác thảo hồ sơ chữ ký cho một API thực tế: algorithm, curve, key id, bytes dữ liệu, encoding, context/mode, thời hạn/rotation, xử lý lỗi và cách chống replay. **Đạt** khi các bên có thể ký/xác minh cùng **đúng dữ liệu** mà không cần suy đoán thông số.

## 15. Tài liệu chuẩn, còn áp dụng hiện nay

- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA), JDK 15](https://openjdk.org/jeps/339): triển khai EdDSA trong JCA từ Java 15.
- [Java SE 25 — NamedParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/NamedParameterSpec.html): `ED25519`, `ED448`, `getName()` và các bộ tham số có tên.
- [Java SE 25 — EdDSAParameterSpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html): mode prehash/context và giới hạn context.
- [Java SE 25 — EdECKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECKey.html): `getParams()`, kiểu khóa EdEC.
- [Java SE 25 — EdECPublicKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPublicKey.html) và [EdECPrivateKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html): point của public key, khả năng xuất private seed dạng `Optional`.
- [Java SE 25 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyPairGenerator.html), [Signature](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html) và [KeyFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/KeyFactory.html): vòng đời sinh khóa, ký/xác minh và nhập khóa.
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032): thuật toán, encoding và các biến thể Ed25519/Ed448.
- [Java SE 25 — Security Developer's Guide: SunEC Provider](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html): các tên thuật toán/provider được triển khai.

**Ghi nhớ:** `NamedParameterSpec.ED25519` và `NamedParameterSpec.ED448` là **tên bộ tham số cho khóa EdEC/EdDSA**, không phải khóa hay thao tác ký. Dùng chúng để khởi tạo `KeyPairGenerator("EdDSA")`, sau đó ký và xác minh bằng thuật toán/mode tương ứng. **Không nhầm EdDSA với XDH**, không nhầm raw key bytes với X.509/PKCS#8, không dùng sai curve/context và không tiết lộ private key. Với giao thức nghiêm túc, luôn ký **đúng bytes**, xác nhận **key provenance** và thống nhất thuật toán, mode, encoding giữa các bên.
