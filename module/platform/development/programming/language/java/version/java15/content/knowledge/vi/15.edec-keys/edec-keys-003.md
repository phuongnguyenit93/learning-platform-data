# EdECKey và tham số đường cong trong Java 15+: Ed25519, Ed448

## 1. EdECKey là gì?

**`java.security.interfaces.EdECKey`** là interface chuẩn của Java cho khóa công khai hoặc khóa riêng thuộc họ **Edwards-curve cryptography theo RFC 8032**, dùng chủ yếu trong chữ ký số **EdDSA**. Nó được bổ sung vào Java 15 theo JEP 339 và **vẫn được hỗ trợ trong Java hiện hành**. `EdECKey` không phải một loại khóa bí mật chung và không đại diện cho toàn bộ mọi đường cong elliptic của Java.

Chức năng cốt lõi của interface rất gọn:

~~~java
import java.security.interfaces.EdECKey;
import java.security.spec.NamedParameterSpec;

NamedParameterSpec params = edecKey.getParams();
~~~

Đây là **đoạn minh họa**, `edecKey` là một đối tượng triển khai `EdECKey` đã được cung cấp. Phương thức `getParams()` mô tả **bộ tham số đã đặt tên** gắn với khóa, ví dụ **Ed25519** hoặc **Ed448**. Nó **không trả về từng hệ số phương trình đường cong**, không trả về private seed, và không trả về nguyên một chữ ký.

Những interface liên quan:

~~~text
                     EdECKey
                   getParams()
                   /         \
                  /           \
        EdECPublicKey      EdECPrivateKey
          getPoint()         getBytes()
            +                 +
         PublicKey         PrivateKey
~~~

Cả `EdECPublicKey` và `EdECPrivateKey` đều có từ **Java 15**. Chúng khác với `ECPublicKey`/`ECPrivateKey` của họ EC dùng trong những API như ECDSA, và khác `XECPublicKey`/`XECPrivateKey` dùng cho X25519/X448 trong cơ chế thỏa thuận khóa XDH.

**Phân biệt rõ mục tiêu:** bài này tập trung vào **tham số đường cong được mang theo khóa, cách truy cập biểu diễn khóa EdEC và khôi phục khóa đúng kiểu**; chữ ký EdDSA chỉ được dùng để kiểm tra khóa sau chuyển đổi còn hoạt động.

## 2. Các bộ tham số đường cong được đặt tên

`java.security.spec.NamedParameterSpec` chứa tên bộ tham số chuẩn. Đối với EdEC, hai hằng số quan trọng là:

~~~java
NamedParameterSpec.ED25519; // getName() == "Ed25519"
NamedParameterSpec.ED448;   // getName() == "Ed448"
~~~

Hai bộ tham số này gắn với đường cong và quy tắc của RFC 8032. Java không yêu cầu ứng dụng tự định nghĩa lại từng hằng số đường cong.

| Thuộc tính | Ed25519 | Ed448 |
| --- | --- | --- |
| Tên chuẩn Java | `"Ed25519"` | `"Ed448"` |
| `NamedParameterSpec` | `ED25519` | `ED448` |
| Đường cong dùng trong EdDSA | edwards25519 | edwards448 |
| Mức bảo mật thiết kế xấp xỉ | 128 bit | 224 bit |
| Public key **raw** theo RFC 8032 | 32 byte | 57 byte |
| Private **seed** raw theo RFC 8032 | 32 byte | 57 byte |
| Chữ ký EdDSA raw | 64 byte | 114 byte |

**Không nhầm độ dài raw với `Key.getEncoded()`.** Public key do provider mã hóa theo X.509/`SubjectPublicKeyInfo` thường dài hơn 32/57 byte vì có phần ASN.1/DER. Private key mã hóa theo PKCS#8 cũng không phải mảng seed raw 32/57 byte.

### 2.1. `getName()` là cách đọc tên tham số

~~~java
NamedParameterSpec expected = NamedParameterSpec.ED25519;
String curveName = expected.getName();  // "Ed25519"
~~~

`NamedParameterSpec` là một **đối tượng mô tả bộ tham số bằng tên**, chứ không phải enum. Có thể tạo:

~~~java
NamedParameterSpec alsoEd25519 = new NamedParameterSpec("Ed25519");

boolean namesMatch = alsoEd25519.getName()
        .equals(NamedParameterSpec.ED25519.getName()); // true
~~~

**So sánh bằng `getName().equals(...)`**, không dựa vào `==` giữa hai đối tượng `NamedParameterSpec`. Đối tượng tạo bằng `new` không phải chính hằng số static và không có lý do để kỳ vọng đồng nhất về tham chiếu.

Tên tham số phải được provider biết và hỗ trợ: gọi `new NamedParameterSpec("ten-khong-co")` chỉ tạo đối tượng mô tả tên, **không chứng minh** provider có thể tạo/đọc khóa cho tên đó. Khi truyền vào `KeyPairGenerator.initialize(...)` hoặc `KeyFactory`, API/provider sẽ áp dụng các kiểm tra tham số thực tế.

### 2.2. `getParams()` khác `getAlgorithm()`

`EdECKey.getParams().getName()` là cách rõ ràng để xem **tham số Ed25519 hay Ed448** gắn với khóa, khi provider cung cấp chúng. `Key.getAlgorithm()` phản ánh tên thuật toán mà đối tượng khóa trình bày; tùy provider có thể mang tên họ thuật toán `"EdDSA"` hoặc tên cụ thể. Vì thế không thiết kế logic bảo mật chỉ dựa trên giả định mọi `getAlgorithm()` luôn trả đúng tên đường cong.

Một số implementation có thể không cung cấp tham số từ một phương thức `getParams()` mặc định/khả dụng; khi nhận khóa từ provider hoặc phần cứng không quen thuộc, **kiểm tra kết quả trước khi gọi `getName()`**. Ví dụ hoàn chỉnh dùng provider trong JDK 24, nơi hai khóa sinh ra đều trả tham số không rỗng, đã được kiểm chứng.

## 3. Tạo cặp khóa với đúng bộ tham số

### 3.1. Nêu đích danh thuật toán cụ thể

Cách ngắn gọn nhất khi giao thức quy định Ed25519:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;

KeyPair pair = KeyPairGenerator.getInstance("Ed25519")
        .generateKeyPair();
~~~

`KeyPair` chứa `PublicKey` và `PrivateKey`. Trong JDK có provider EdDSA tương thích, chúng có thể được truy cập thông qua `EdECPublicKey` và `EdECPrivateKey`.

**Không tự chọn seed cố định cho khóa sản xuất.** `KeyPairGenerator` dùng nguồn ngẫu nhiên mật mã thích hợp của provider. Ví dụ tạo khóa mới khi chạy để tránh dùng một private key đã công khai.

### 3.2. Dùng bộ tạo EdDSA chung nhưng đặt tham số tường minh

~~~java
import java.security.KeyPairGenerator;
import java.security.spec.NamedParameterSpec;

KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(NamedParameterSpec.ED448);
KeyPair ed448Pair = generator.generateKeyPair();
~~~

Trong ví dụ này, `"EdDSA"` chọn họ chữ ký, còn `NamedParameterSpec.ED448` chọn **bộ tham số Ed448**. Nếu không có chính sách lựa chọn mặc định rõ ràng, **không nên phụ thuộc vào bộ tham số mặc định của `"EdDSA"`**; hãy khởi tạo tường minh hoặc dùng `"Ed25519"`/`"Ed448"` trực tiếp.

Cũng có thể dùng `generator.initialize(NamedParameterSpec.ED25519)` để chọn Ed25519. Đây là những tham số đã có trong Java 15; không cần preview feature.

### 3.3. Kiểm tra tham số của hai khóa trong cặp

~~~java
EdECPublicKey publicKey = (EdECPublicKey) pair.getPublic();
EdECPrivateKey privateKey = (EdECPrivateKey) pair.getPrivate();

String publicCurve = publicKey.getParams().getName();
String privateCurve = privateKey.getParams().getName();
boolean sameCurve = publicCurve.equals(privateCurve);
~~~

Đây là **mã minh họa** có các import `java.security.interfaces.*`, sử dụng `pair` ở ví dụ trước. `sameCurve` phải là `true` cho cặp khóa nhất quán được tạo đúng cách. Trong code tiếp nhận khóa từ nguồn bên ngoài, đừng chỉ kiểm tra cùng tên rồi coi cặp khóa đã chắc chắn tương ứng: muốn chứng minh khóa riêng và khóa công khai khớp nhau, phải có một phép kiểm tra mật mã như **ký rồi xác minh**, hoặc cơ chế tương đương phù hợp.

## 4. Cấu trúc `EdECPublicKey` và `EdECPoint`

`EdECPublicKey` cung cấp:

~~~java
NamedParameterSpec params = publicKey.getParams();
EdECPoint point = publicKey.getPoint();
~~~

Đây là đoạn minh họa dùng `java.security.interfaces.EdECPublicKey` và `java.security.spec.EdECPoint`.

`EdECPoint` chứa đúng hai thành phần cần để thể hiện điểm công khai theo quy tắc RFC 8032:

| Phương thức | Kết quả |
| --- | --- |
| `getY()` | Tọa độ y ở dạng `BigInteger` không âm |
| `isXOdd()` | `boolean` cho biết tọa độ x có tính lẻ hay không |
| `getParams()` trên `EdECPublicKey` | Tên bộ tham số đường cong, **không nằm trong `EdECPoint`** |

Với cách nén điểm được RFC 8032 mô tả, không cần xuất trực tiếp cả x và y theo một cấu trúc EC chung: dùng **y và parity của x** là đủ để thể hiện điểm nén theo định dạng đường cong tương ứng. Tuy nhiên, một `EdECPoint` của JCA **không phải** dãy byte public key nén của RFC.

### 4.1. Dạng raw RFC khác dạng đối tượng Java

- Public key Ed25519 raw dài **32 byte**; Ed448 raw dài **57 byte**.
- RFC mã hóa tọa độ theo **little-endian** cùng bit chỉ tính lẻ của x tại vị trí được quy định.
- `BigInteger` trong Java sử dụng biểu diễn số nguyên theo quy tắc của API; nếu tự ghép/parse byte array, rất dễ sai **endianness, bit dấu, chiều dài, padding**.
- Không cast `EdECPoint` thành `ECPoint`: đây là **hai kiểu khác nhau** dành cho những họ API khác nhau.
- Không tự tạo `EdECPoint` từ các số tùy ý rồi coi đó là public key hợp lệ. Hãy để `KeyFactory` hoặc provider kiểm tra dữ liệu theo đúng curve và tiêu chuẩn.

**Ưu tiên `KeyFactory.getKeySpec(...)` để lấy cấu trúc hợp lệ từ một khóa đã có**, thay vì tự sửa byte đầu vào. Phần 6 minh họa cách này.

## 5. `EdECPrivateKey`: private seed có thể không được phép xuất

`EdECPrivateKey` có hai khả năng:

~~~java
NamedParameterSpec params = privateKey.getParams();
Optional<byte[]> seed = privateKey.getBytes();
~~~

Đây là đoạn minh họa sử dụng `java.util.Optional` và `java.security.interfaces.EdECPrivateKey`. `getBytes()` trả **`Optional<byte[]>`**, không phải `byte[]` trực tiếp:

- Khi provider cho phép, `Optional` chứa **bản sao byte của private key theo biểu diễn EdEC**, thường là private seed theo RFC 8032.
- Khi provider **không cho phép xuất private material**, `Optional` có thể **rỗng**. Không coi đây là lỗi thuật toán.
- Dữ liệu trả về là **bí mật**; không in thành hex, không commit, không đưa lên dịch vụ logging/analytics hay gửi trong lỗi HTTP.
- Việc `getBytes()` trả mảng **không có nghĩa** cùng nội dung với `getEncoded()`. `getEncoded()` nếu hỗ trợ thường thuộc một **container PKCS#8**, không phải seed raw.
- `getEncoded()` cũng có thể trả `null` khi key không có định dạng xuất; việc key tồn tại không bảo đảm private material có thể xuất.

Với môi trường HSM hoặc keystore quản lý khóa, thông thường nên **ký ngay trong provider/thiết bị** thay vì cố lấy seed ra bộ nhớ ứng dụng. Nếu cần copy dữ liệu bí mật vào mảng tạm, giảm số bản sao, giới hạn vòng đời và xóa mảng tạm khi xong; việc xóa mảng **không thể bảo đảm** mọi bản sao trong runtime/GC đều đã được xóa ngay.

`NamedParameterSpec` của private key là **tham số đường cong**, không phải private seed. Nhầm hai khái niệm này có thể gây lỗi khi xây dựng `KeySpec` hoặc lưu trữ khóa.

## 6. Chuyển đổi khóa qua `KeyFactory` và các `KeySpec`

`java.security.KeyFactory` hoạt động với những định dạng khóa khác nhau. Đối với EdEC, bốn lớp spec rất dễ bị nhầm:

| Dạng | API | Biểu diễn |
| --- | --- | --- |
| Public key cấu trúc EdEC | `EdECPublicKeySpec(params, point)` | Bộ tham số + `EdECPoint` |
| Private key cấu trúc EdEC | `EdECPrivateKeySpec(params, bytes)` | Bộ tham số + byte private EdEC |
| Public key encode theo X.509/SPKI | `X509EncodedKeySpec(der)` | Mảng DER của SubjectPublicKeyInfo |
| Private key encode theo PKCS#8 | `PKCS8EncodedKeySpec(der)` | Mảng DER của PrivateKeyInfo |

### 6.1. Public key: chuyển thành `EdECPublicKeySpec` rồi khôi phục

~~~java
KeyFactory factory = KeyFactory.getInstance("Ed25519");
EdECPublicKeySpec spec =
        factory.getKeySpec(publicKey, EdECPublicKeySpec.class);

PublicKey restored = factory.generatePublic(spec);
~~~

Đây là đoạn minh họa; `publicKey` thuộc Ed25519. Provider lấy bộ tham số và điểm công khai đã được biểu diễn bằng các kiểu đúng của Java. Nếu chỉ cần chuyển **cấu trúc public key** trong cùng môi trường Java, đây là cách tránh lỗi parse raw byte.

Cũng có thể tạo `EdECPublicKeySpec` trực tiếp:

~~~java
EdECPublicKeySpec spec = new EdECPublicKeySpec(
        NamedParameterSpec.ED25519, publicKey.getPoint());
~~~

Nhưng phải chắc chắn `publicKey` dùng **Ed25519** và điểm thực sự hợp lệ trên đường cong đó. **Không** lấy điểm của Ed448 rồi gắn nhãn `ED25519` hay ngược lại.

### 6.2. Private key: dùng `EdECPrivateKeySpec` với byte private nếu xuất được

~~~java
Optional<byte[]> maybeSeed = privateKey.getBytes();
if (maybeSeed.isPresent()) {
    byte[] seed = maybeSeed.orElseThrow();
    try {
        EdECPrivateKeySpec spec = new EdECPrivateKeySpec(
                privateKey.getParams(), seed);
        PrivateKey rebuilt = factory.generatePrivate(spec);
        // Chỉ sử dụng rebuilt cho mục đích tin cậy, tránh ghi lại seed.
    } finally {
        java.util.Arrays.fill(seed, (byte) 0);
    }
}
~~~

Đây là mã minh họa, `factory` phải phù hợp với curve của `privateKey`. **Không gọi `orElseThrow()` vô điều kiện** nếu provider có quyền từ chối xuất seed. Nếu `getParams()` không được cung cấp, cần một nguồn thông tin tham số **đáng tin cậy** và phù hợp với key; không tự đoán curve từ chiều dài mảng rồi coi đó là kiểm chứng mật mã.

`EdECPrivateKeySpec` dùng byte của private key theo RFC/`EdECPrivateKey`, **không nhận PKCS#8 DER**. Đưa nguyên `privateKey.getEncoded()` vào constructor này là nhầm định dạng.

### 6.3. X.509/PKCS#8 khi trao đổi khóa đã encode

~~~java
byte[] spki = publicKey.getEncoded();
byte[] pkcs8 = privateKey.getEncoded();

PublicKey p = factory.generatePublic(new X509EncodedKeySpec(spki));
PrivateKey s = factory.generatePrivate(new PKCS8EncodedKeySpec(pkcs8));
~~~

Đoạn này giả định provider **cho phép xuất** và hai byte array khác `null`. Đây là định dạng Java/provider thường dùng; public key raw 32/57 byte của RFC 8032 **không tự động là** X.509/SPKI, và private seed 32/57 byte **không tự động là** PKCS#8.

Trong thực tế, giao thức có thể yêu cầu OpenSSH, JWK/JOSE, COSE, PEM hoặc định dạng khác. `KeyFactory` không tự diễn dịch mọi định dạng khóa mà không có bước chuyển đổi phù hợp. **Định dạng khóa là hợp đồng**, phải được thống nhất cùng tên curve.

## 7. Phân biệt EdEC, XEC/XDH và EC thông thường

Ba họ interface gần tên nhau nhưng **không hoán đổi**:

| Họ khóa | Interface tiêu biểu | Mục đích phổ biến |
| --- | --- | --- |
| EdEC | `EdECPublicKey`, `EdECPrivateKey` | Ed25519/Ed448, **chữ ký số EdDSA** (RFC 8032) |
| XEC | `XECPublicKey`, `XECPrivateKey` | X25519/X448, **thỏa thuận khóa XDH** (RFC 7748) |
| EC | `ECPublicKey`, `ECPrivateKey` | Các API đường cong Weierstrass, ví dụ ECDSA/ECDH tùy thuật toán |

`NamedParameterSpec` có cả `ED25519`, `ED448`, `X25519`, `X448`; **chúng không cùng họ chỉ vì tên giống nhau**. Public key Ed25519 không thể lấy ra rồi dùng trực tiếp như public key X25519 qua cast hoặc `KeyFactory` khác thuật toán.

~~~java
KeyPair xdhPair = KeyPairGenerator.getInstance("X25519")
        .generateKeyPair();
boolean isEdEC = xdhPair.getPublic() instanceof EdECKey; // false
~~~

Đừng nhầm `"EdDSA"` với `"XDH"`: EdDSA dùng `Signature` còn XDH dùng `KeyAgreement`; hai chức năng mật mã phục vụ mục đích khác nhau. Cũng không nên dùng `ECGenParameterSpec("secp256r1")` thay cho `NamedParameterSpec.ED25519`: đó là một họ tham số khác.

## 8. Chương trình đầy đủ: xem curve, chuyển đổi spec, ký và xác minh

Chương trình dưới đây chạy **offline** trên Java 15+. Nó kiểm tra:

1. Ed25519 tạo bằng `KeyPairGenerator.getInstance("Ed25519")`.
2. Ed448 tạo bằng `KeyPairGenerator.getInstance("EdDSA")` và `initialize(ED448)`.
3. Tham số curve của hai khóa và `EdECPoint`.
4. Round-trip bằng `EdECPublicKeySpec`, `X509EncodedKeySpec` và `PKCS8EncodedKeySpec`.
5. `EdECPrivateKey.getBytes()`: nếu provider cho xuất seed, kiểm tra round-trip bằng `EdECPrivateKeySpec`; nếu không, bỏ qua thay vì làm lộ khóa.
6. Ký/verify thực sự bằng `Signature` trên đúng thuật toán và phát hiện thông điệp bị sửa.
7. Chứng minh `NamedParameterSpec` là object có tên và `X25519` không phải `EdECKey`.

Lưu tệp đúng tên **`EdECParametersDemo.java`** và dùng encoding UTF-8.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.*;
import java.security.spec.*;
import java.util.Arrays;
import java.util.Optional;

public class EdECParametersDemo {
    public static void main(String[] args) throws Exception {
        byte[] message = "Dữ liệu thử nghiệm 🌱".getBytes(StandardCharsets.UTF_8);

        KeyPair ed25519 = KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
        test("Ed25519", ed25519, message, 64);

        KeyPairGenerator ed448Generator = KeyPairGenerator.getInstance("EdDSA");
        ed448Generator.initialize(NamedParameterSpec.ED448);
        KeyPair ed448 = ed448Generator.generateKeyPair();
        test("Ed448", ed448, message, 114);

        NamedParameterSpec newSpec = new NamedParameterSpec("Ed25519");
        System.out.println("curveNameMatches=" +
                newSpec.getName().equals(NamedParameterSpec.ED25519.getName()));
        System.out.println("distinctSpecObjects=" + (newSpec != NamedParameterSpec.ED25519));

        KeyPair x25519 = KeyPairGenerator.getInstance("X25519").generateKeyPair();
        System.out.println("xdhIsEdEC=" + (x25519.getPublic() instanceof EdECKey));
    }

    private static void test(String expected, KeyPair pair, byte[] message,
                             int signatureSize) throws Exception {
        EdECPublicKey publicKey = (EdECPublicKey) pair.getPublic();
        EdECPrivateKey privateKey = (EdECPrivateKey) pair.getPrivate();
        NamedParameterSpec publicParams = publicKey.getParams();
        NamedParameterSpec privateParams = privateKey.getParams();

        System.out.println(expected + ".publicCurve=" + publicParams.getName());
        System.out.println(expected + ".privateCurve=" + privateParams.getName());
        System.out.println(expected + ".curvesAgree=" +
                publicParams.getName().equals(privateParams.getName()));

        EdECPoint point = publicKey.getPoint();
        System.out.println(expected + ".publicPointHasY=" +
                (point.getY() != null && point.getY().signum() >= 0));

        KeyFactory factory = KeyFactory.getInstance(expected);
        EdECPublicKeySpec publicSpec =
                factory.getKeySpec(publicKey, EdECPublicKeySpec.class);
        EdECPublicKey restoredFromPoint = (EdECPublicKey)
                factory.generatePublic(publicSpec);

        boolean pointRoundTrip =
                point.isXOdd() == restoredFromPoint.getPoint().isXOdd()
                && point.getY().equals(restoredFromPoint.getPoint().getY());
        System.out.println(expected + ".pointRoundTrip=" + pointRoundTrip);

        PublicKey restoredEncodedPublic = factory.generatePublic(
                new X509EncodedKeySpec(publicKey.getEncoded()));
        PrivateKey restoredEncodedPrivate = factory.generatePrivate(
                new PKCS8EncodedKeySpec(privateKey.getEncoded()));

        byte[] signature = sign(expected, privateKey, message);
        boolean valid = verify(expected, publicKey, message, signature);
        System.out.println(expected + ".signatureBytes=" + signature.length);
        System.out.println(expected + ".valid=" + valid);
        System.out.println(expected + ".encodedKeysWork=" +
                verify(expected, restoredEncodedPublic, message,
                       sign(expected, restoredEncodedPrivate, message)));
        System.out.println(expected + ".publicSpecWorks=" +
                verify(expected, restoredFromPoint, message, signature));

        byte[] changed = message.clone();
        changed[0] ^= 1;
        System.out.println(expected + ".tamperedValid=" +
                verify(expected, publicKey, changed, signature));

        Optional<byte[]> optionalSeed = privateKey.getBytes();
        System.out.println(expected + ".seedExportable=" + optionalSeed.isPresent());
        if (optionalSeed.isPresent()) {
            byte[] seed = optionalSeed.orElseThrow();
            try {
                EdECPrivateKeySpec privateSpec =
                        new EdECPrivateKeySpec(privateParams, seed);
                PrivateKey rebuilt = factory.generatePrivate(privateSpec);
                System.out.println(expected + ".privateSpecWorks=" +
                        verify(expected, publicKey, message,
                               sign(expected, rebuilt, message)));
            } finally {
                Arrays.fill(seed, (byte) 0);
            }
        } else {
            System.out.println(expected + ".privateSpecWorks=not-exportable");
        }
        System.out.println(expected + ".checks=" + (
                expected.equals(publicParams.getName())
                && expected.equals(privateParams.getName())
                && pointRoundTrip && valid && signature.length == signatureSize
                && !verify(expected, publicKey, changed, signature)));
    }

    private static byte[] sign(String algorithm, PrivateKey key, byte[] data)
            throws Exception {
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(key);
        signer.update(data);
        return signer.sign();
    }

    private static boolean verify(String algorithm, PublicKey key,
                                  byte[] data, byte[] signature) throws Exception {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac --release 17 -encoding UTF-8 EdECParametersDemo.java
java EdECParametersDemo
~~~

Đây là chương trình Java 15+; đã biên dịch thành công với `javac --release 15` và `--release 17` trên JDK 24. Đầu ra **đã kiểm chứng khi dùng provider mặc định của JDK 24**:

~~~text
Ed25519.publicCurve=Ed25519
Ed25519.privateCurve=Ed25519
Ed25519.curvesAgree=true
Ed25519.publicPointHasY=true
Ed25519.pointRoundTrip=true
Ed25519.signatureBytes=64
Ed25519.valid=true
Ed25519.encodedKeysWork=true
Ed25519.publicSpecWorks=true
Ed25519.tamperedValid=false
Ed25519.seedExportable=true
Ed25519.privateSpecWorks=true
Ed25519.checks=true
Ed448.publicCurve=Ed448
Ed448.privateCurve=Ed448
Ed448.curvesAgree=true
Ed448.publicPointHasY=true
Ed448.pointRoundTrip=true
Ed448.signatureBytes=114
Ed448.valid=true
Ed448.encodedKeysWork=true
Ed448.publicSpecWorks=true
Ed448.tamperedValid=false
Ed448.seedExportable=true
Ed448.privateSpecWorks=true
Ed448.checks=true
curveNameMatches=true
distinctSpecObjects=true
xdhIsEdEC=false
~~~

**Cách hiểu kết quả:**

- `publicCurve/privateCurve`: tên curve được đọc từ `EdECKey.getParams().getName()`, không đoán từ độ dài chữ ký.
- `pointRoundTrip=true`: `EdECPublicKeySpec` giữ nguyên `y` và `xOdd`, cho phép phục dựng public key tương đương.
- `signatureBytes=64/114`: khớp kích thước chữ ký Ed25519/Ed448 theo RFC 8032; đây **không phải kích thước `getEncoded()` của khóa**.
- `encodedKeysWork=true`: các khóa SPKI/PKCS#8 được provider JDK kiểm chứng đọc lại và ký/verify.
- `publicSpecWorks=true`: public key được tạo lại từ `EdECPublicKeySpec` xác minh chữ ký gốc.
- `seedExportable=true` trong **provider mặc định của JDK dùng để kiểm chứng**. Với hardware key hay provider khác có thể nhận `false`; chương trình sẽ in `privateSpecWorks=not-exportable`. Đó là khả năng hợp lệ, không phải vi phạm RFC.
- `tamperedValid=false`: thay đổi một byte làm chữ ký không còn hợp lệ đối với message mới.
- `curveNameMatches=true` đồng thời `distinctSpecObjects=true`: hai mô tả có cùng tên chuẩn nhưng là **hai đối tượng khác nhau**.
- `xdhIsEdEC=false`: cặp khóa tạo bằng X25519 không thuộc interface EdEC.
- `checks=true` ở mỗi curve chứng thực những điều kiện quan trọng: curve đúng, point round-trip, signature đúng kích thước và verifier từ chối byte bị sửa.

`Signature` trong chương trình dùng Ed25519/Ed448 **pure mode**, không thêm context hoặc prehash; nếu protocol dùng Ed25519ctx, Ed25519ph hay Ed448ph, hai phía phải cấu hình `EdDSAParameterSpec` tương ứng. Việc chọn curve qua `NamedParameterSpec` **khác** việc chọn context/prehash của một chữ ký; không trộn hai lớp cấu hình.

## 9. Những ranh giới và lỗi thường gặp

### 9.1. Không xem tên curve là kiểm chứng toàn bộ khóa

`getParams().getName().equals("Ed25519")` chỉ cho biết đối tượng khóa khai báo gắn với curve Ed25519. Nó **không xác thực danh tính chủ sở hữu public key**, không khẳng định private và public key tương ứng với nhau và không thay thế kiểm tra bytecode/serialization khi nhập từ nguồn không đáng tin. Nếu đang thiết lập khóa tin cậy cho giao thức, cần xác thực public key/certificate theo chính sách ứng dụng.

### 9.2. Không parse thẳng seed raw thành PKCS#8

~~~text
Private seed raw (Ed25519: 32 byte)  ≠  PKCS#8 DER
Public point raw (Ed25519: 32 byte)  ≠  X.509/SPKI DER
~~~

Chọn đúng `EdECPrivateKeySpec` hoặc `EdECPublicKeySpec` khi làm với cấu trúc EdEC; chọn `PKCS8EncodedKeySpec`/`X509EncodedKeySpec` khi mảng byte **thực sự thuộc container tương ứng**. Không dùng length=32/57 làm quy tắc nhận dạng duy nhất của định dạng.

### 9.3. Không lẫn EdEC với ECPublicKey hoặc XEC

Một khóa `X25519` có `NamedParameterSpec.X25519` nhưng **không thể** cast nó thành `EdECKey`. Đối với XDH, dùng `XECKey` và `KeyAgreement`; đối với EdDSA, dùng `EdECKey` và `Signature`. Không sử dụng lời hứa “chuyển đổi Ed25519 thành X25519” như một phép cast/rename trong Java.

### 9.4. Không xem private seed luôn có thể xuất

`EdECPrivateKey.getBytes()` là `Optional`. Provider có thể từ chối trả raw seed; phần mềm vẫn có thể ký bằng private key qua `Signature.initSign(privateKey)` mà không cần biết seed. Khi `getEncoded()` trả `null`, không tự phát minh byte thay thế.

### 9.5. Không tự tin vào tham số thiếu hoặc không rõ nguồn

Với API nhận dữ liệu untrusted, cần kiểm tra curve theo giao thức, định dạng key, cách parse, độ dài, điểm công khai, các ngoại lệ của `KeyFactory` và hỗ trợ provider. Nếu `getParams()` là `null` ở một implementation, cần xác định đúng curve từ metadata/protocol đáng tin trước khi tạo `KeySpec`; không suy đoán từ tên class hay chuyển kiểu mù quáng.

### 9.6. Hệ sinh thái có thể khác nhau

SunEC/JDK provider có hỗ trợ JCA EdDSA thông thường, nhưng HSM, provider tùy biến, môi trường tuân thủ và thư viện đối tác có thể giới hạn thuật toán, khả năng export key hoặc kiểu `KeySpec`. Những trường hợp như `NoSuchAlgorithmException`, `InvalidKeySpecException` và `InvalidKeyException` cần được xử lý như **lỗi cấu hình hoặc dữ liệu**. Không biến lỗi này thành `verify(...) == false` một cách tùy tiện.

### 9.7. Đừng nhầm tên tham số với mức độ an toàn tuyệt đối

Ed25519/Ed448 là thuật toán ký dựa trên đường cong elliptic hiện hành, **không phải chữ ký hậu lượng tử**. Quyết định lựa chọn curve còn phụ thuộc yêu cầu bảo mật, hỗ trợ hệ sinh thái, chính sách, thời gian sống của khóa và tương thích giao thức. Không chọn Ed448 chỉ vì số 448 lớn hơn; phải đánh giá nhu cầu và khả năng triển khai thực tế.

## 10. Checklist khi thiết kế API quản lý khóa EdEC

| Câu hỏi | Quy tắc |
| --- | --- |
| Đầu vào thật sự là EdDSA? | Kiểm tra đúng họ `EdECKey` và thuật toán được giao thức cho phép |
| Curve nào? | Ưu tiên `NamedParameterSpec.ED25519`/`ED448`, dùng `getParams().getName()` để xác nhận |
| Hai khóa cùng curve? | Kiểm tra tham số, rồi kiểm chứng mối quan hệ bằng ký/verify nếu cần |
| Chỉ cần dùng public key? | Giữ `EdECPublicKey` hoặc đổi sang `EdECPublicKeySpec` / SPKI hợp lệ |
| Muốn lấy private seed? | Kiểm tra `Optional`, cân nhắc nguy cơ xuất bí mật; ưu tiên ký trong provider |
| Dữ liệu là raw hay DER? | Xác nhận định dạng trước khi chọn `EdEC...Spec` hay `X509/PKCS8...Spec` |
| Có điểm công khai tự nhập? | Kiểm tra curve, point, bit xOdd/y và để provider kiểm tra đầu vào |
| Giao thức dùng Ed25519ctx/ph? | Phân biệt **curve** với **mode chữ ký**; cấu hình `EdDSAParameterSpec` riêng |
| Provider không có tham số hoặc export? | Xử lý tình huống thay vì ép cast, tự đoán curve hoặc in private material |
| Cần tích hợp với X25519? | Đây là họ **XDH**, không hoán đổi khóa/chữ ký qua cast |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `EdECKey.getParams()` trả về private seed hay tên tham số đường cong?  
**Đáp án:** đối tượng `NamedParameterSpec` cho tham số đường cong, chẳng hạn Ed25519 hoặc Ed448. Private seed là một khái niệm khác.

**Câu 2.** Với `NamedParameterSpec p = new NamedParameterSpec("Ed25519");`, biểu thức `p == NamedParameterSpec.ED25519` có đúng không?  
**Đáp án:** không. So sánh tên bằng `p.getName().equals(NamedParameterSpec.ED25519.getName())`.

**Câu 3.** `EdECPublicKey.getPoint()` mang dữ liệu gì?  
**Đáp án:** `EdECPoint` với tọa độ `y` và bit `xOdd`; cần kết hợp curve và quy tắc mã hóa RFC để chuyển thành raw key bytes.

**Câu 4.** Nếu `EdECPrivateKey.getBytes()` trả `Optional.empty()`, phải chăng khóa không dùng để ký được?  
**Đáp án:** không. Một provider có thể cấm xuất seed nhưng vẫn cho dùng `Signature.initSign(key)`.

**Câu 5.** Có thể dùng `X509EncodedKeySpec` trên dãy 32 byte raw Ed25519 lấy từ RFC 8032 không?  
**Đáp án:** không trực tiếp. Spec đó đòi byte trong container X.509/SPKI đúng chuẩn, không phải raw point.

**Câu 6.** Vì sao `KeyPairGenerator.getInstance("EdDSA").initialize(NamedParameterSpec.ED448)` tốt hơn việc dựa vào default trong chương trình cần Ed448?  
**Đáp án:** vì tên tham số thể hiện **rõ đường cong theo hợp đồng**, không phụ thuộc lựa chọn mặc định của provider.

## Tài liệu chính thức còn áp dụng

- Oracle Java SE 25, **`EdECKey`** (Since: 15, `getParams`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECKey.html
- Oracle Java SE 25, **`EdECPublicKey`** (`getPoint`, `getParams`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPublicKey.html
- Oracle Java SE 25, **`EdECPrivateKey`** (`getBytes` trả Optional, `getParams`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html
- Oracle Java SE 25, **`NamedParameterSpec`** (`ED25519`, `ED448`, `getName`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/NamedParameterSpec.html
- Oracle Java SE 25, **`EdECPoint`** (tọa độ y, `xOdd`): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPoint.html
- Oracle Java SE 25, **`EdECPublicKeySpec` / `EdECPrivateKeySpec`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPublicKeySpec.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html
- OpenJDK, **JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)**, chính thức từ Java 15: https://openjdk.org/jeps/339
- IETF, **RFC 8032 — EdDSA**, Ed25519 và Ed448: https://www.rfc-editor.org/rfc/rfc8032