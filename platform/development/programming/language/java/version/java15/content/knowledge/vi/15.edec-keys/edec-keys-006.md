# EdECPublicKeySpec và EdECPrivateKeySpec trong Java 15+

## 1. Hai lớp KeySpec giải quyết vấn đề gì?

Java 15 chính thức hỗ trợ **Edwards-Curve Digital Signature Algorithm (EdDSA)** theo RFC 8032, trong đó hai tên thuật toán quen thuộc là **Ed25519** và **Ed448**. Khi làm việc với khóa EdDSA, Java cung cấp hai kiểu đặc tả khóa:

- `java.security.spec.EdECPublicKeySpec`: biểu diễn **khóa công khai** bằng **tham số đường cong** và **điểm EdEC**.
- `java.security.spec.EdECPrivateKeySpec`: biểu diễn **khóa riêng** bằng **tham số đường cong** và **mảng byte chứa giá trị khóa riêng**.

Cả hai triển khai giao diện `KeySpec`. Chúng **không phải** `PublicKey` hoặc `PrivateKey` dùng trực tiếp với `Signature`. Muốn tạo đối tượng khóa thực thụ từ các đặc tả này, dùng `KeyFactory.generatePublic(...)` và `KeyFactory.generatePrivate(...)`.

Đây là API chuẩn từ **Java 15**, vẫn được hỗ trợ trong các JDK hiện đại. Không cần bật preview, không dùng API legacy và không cần tự cài đặt thuật toán chữ ký số.

Hình dung luồng dữ liệu:

~~~text
KeyPairGenerator("Ed25519" / "Ed448")
             |
             v
       PublicKey + PrivateKey
             |
             | KeyFactory.getKeySpec(...)
             v
  EdECPublicKeySpec + EdECPrivateKeySpec
       |                     |
       | KeyFactory          | KeyFactory
       | .generatePublic     | .generatePrivate
       v                     v
     PublicKey             PrivateKey
       |                     |
       +--------+------------+
                |
                v
     Signature (verify / sign)
~~~

### Phân biệt EdEC, EdDSA, EC và XEC

| Tên | Mục đích | API thường gặp |
| --- | --- | --- |
| **EdEC** | Kiểu khóa Edwards-curve cho EdDSA. | `EdECPublicKeySpec`, `EdECPrivateKeySpec`, `EdECPoint`. |
| **EdDSA / Ed25519 / Ed448** | **Chữ ký số**: ký và kiểm tra chữ ký. | `KeyPairGenerator`, `KeyFactory`, `Signature`. |
| **EC** theo kiểu đường cong Weierstrass | Những thuật toán khác như ECDSA với các đường cong phù hợp. | `ECPublicKeySpec`, `ECPrivateKeySpec`; **không** thay cho EdEC specs. |
| **XEC / X25519 / X448** | Trao đổi/thỏa thuận khóa theo XDH, không phải chữ ký EdDSA. | `XECPublicKeySpec`, `XECPrivateKeySpec` và `KeyAgreement`. |

**Không nhầm Ed25519 với X25519** chỉ vì tên đều có `25519`. Cặp Ed25519 dùng để ký/xác minh; X25519 dành cho trao đổi khóa. Thư viện và thuật toán sử dụng khác nhau; không ép một `EdECPublicKeySpec` thành `XECPublicKeySpec` hoặc ngược lại.

## 2. `NamedParameterSpec`: đường cong và tập tham số

Hai constructor của EdEC specs đều nhận `NamedParameterSpec`, ví dụ:

~~~java
import java.security.spec.NamedParameterSpec;

NamedParameterSpec curve1 = NamedParameterSpec.ED25519;
NamedParameterSpec curve2 = NamedParameterSpec.ED448;

System.out.println(curve1.getName()); // Ed25519
System.out.println(curve2.getName()); // Ed448
~~~

`NamedParameterSpec.ED25519` và `NamedParameterSpec.ED448` là những hằng chuẩn có từ Java 15. Chúng xác định **bộ tham số thuật toán/đường cong** phù hợp với khóa, không phải giá trị ngẫu nhiên của từng khóa.

Khi tạo khóa bằng provider:

~~~java
import java.security.KeyPairGenerator;
import java.security.spec.NamedParameterSpec;

KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
generator.initialize(NamedParameterSpec.ED25519);
~~~

`generator.generateKeyPair()` sau đó tạo cặp khóa phù hợp với Ed25519. Nếu chuyển sang Ed448 thì đổi **đồng bộ** tên thuật toán và `NamedParameterSpec.ED448`, không chỉ đổi chuỗi một phía.

Một số provider còn hỗ trợ tên chung `"EdDSA"`, nhưng ví dụ sử dụng **tên cụ thể `"Ed25519"` / `"Ed448"`** để thể hiện đúng lựa chọn. Khả năng hỗ trợ thực tế phụ thuộc provider JCA đang được cấu hình; trên JDK phổ biến, `SunEC` là provider cung cấp EdDSA.

**Không chọn khóa bằng kích thước chung chung** như “256-bit” rồi suy ra thuật toán. `Ed25519` và `Ed448` là **tên tập tham số**, không phải cách viết khác của `ECGenParameterSpec` hay `X25519`.

## 3. `EdECPublicKeySpec`: công khai = tham số + điểm Edwards

Chữ ký constructor:

~~~java
public EdECPublicKeySpec(
        NamedParameterSpec params,
        EdECPoint point
)
~~~

Trong đó:

- `params` xác định tập tham số, chẳng hạn `NamedParameterSpec.ED25519`.
- `point` là `java.security.spec.EdECPoint` biểu diễn **điểm khóa công khai** trên đường cong.

`EdECPoint` không giống `java.security.spec.ECPoint` của các đường cong Weierstrass. Nó biểu diễn điểm Edwards bằng:

1. `BigInteger y`: tọa độ **y**.
2. `boolean xOdd`: **bit chẵn/lẻ của tọa độ x**, hay bit thấp nhất của x; giúp phân biệt điểm có cùng tọa độ y.

API:

~~~java
import java.math.BigInteger;
import java.security.spec.EdECPoint;

// Vi du minh hoa cau truc EdECPoint, KHONG phai khoa hop le.
BigInteger exampleY = BigInteger.ONE;
boolean exampleXOdd = false;
EdECPoint point = new EdECPoint(exampleXOdd, exampleY);

System.out.println(point.getY());     // 1
System.out.println(point.isXOdd());   // false
~~~

Đoạn trên **chỉ minh họa cấu trúc dữ liệu**, không phải cách tạo một khóa Ed25519 hợp lệ. Muốn dùng làm khóa công khai, điểm phải thỏa những điều kiện của đường cong và thuật toán; nhà cung cấp `KeyFactory`/`Signature` có thể kiểm tra và từ chối dữ liệu không hợp lệ.

Tạo khóa công khai từ **điểm đã biết là hợp lệ**:

~~~java
// Minh hoa trong ngu canh da co params, point va factory phu hop.
EdECPublicKeySpec publicSpec =
        new EdECPublicKeySpec(params, point);

PublicKey publicKey = factory.generatePublic(publicSpec);
~~~

`getParams()` và `getPoint()` cho phép lấy lại dữ liệu đặc tả:

~~~java
NamedParameterSpec params = publicSpec.getParams();
EdECPoint point = publicSpec.getPoint();
boolean xOdd = point.isXOdd();
BigInteger y = point.getY();
~~~

### 3.1. Đừng tự nhầm thứ tự byte của tọa độ

Theo RFC 8032, khóa công khai Ed25519/Ed448 thường được biểu diễn dưới dạng **điểm nén** (*compressed point*) với cách mã hóa riêng: tọa độ y và một bit dấu/chẵn-lẻ của x. Dữ liệu dạng byte đó **không giống**:

- `BigInteger.toByteArray()` của `point.getY()`: biểu diễn số nguyên `BigInteger` có thể thêm byte dấu và dùng **big-endian**.
- `PublicKey.getEncoded()` của JCA: đối với nhiều provider là **X.509 SubjectPublicKeyInfo** dưới dạng DER, chứa cả thông tin thuật toán và phần khóa công khai.
- Một `EdECPoint`: đối tượng Java nắm y và `xOdd`, không phải `byte[]` đã mã hóa.

Nếu cần nhập một khóa công khai từ giao thức cung cấp **raw compressed point**, phải đọc **đúng chuẩn mã hóa của giao thức đó** rồi xây `EdECPoint`. Không dùng `new BigInteger(rawBytes)` và bỏ qua `xOdd`, vì rất dễ sai endian, bit cao hoặc dấu của số.

Khi nguồn khóa đã ở định dạng **X.509 DER** (`SubjectPublicKeyInfo`), con đường đơn giản hơn là dùng `X509EncodedKeySpec` qua `KeyFactory`, không tự tách điểm trừ khi ứng dụng có lý do cụ thể.

## 4. `EdECPrivateKeySpec`: riêng tư = tham số + byte của khóa

Chữ ký constructor:

~~~java
public EdECPrivateKeySpec(
        NamedParameterSpec params,
        byte[] bytes
)
~~~

Khác khóa công khai được biểu diễn qua `EdECPoint`, đặc tả khóa riêng dùng **mảng byte**. Theo RFC 8032, Ed25519 và Ed448 được xây dựng từ **dữ liệu khóa riêng dạng byte** làm đầu vào cho quá trình tạo scalar và nonce nội bộ. Khi sử dụng JDK provider tương ứng, giá trị này thường được mô tả là **seed/private key bit string**, **không** phải số `BigInteger` tọa độ hay số mũ có thể dùng thay thế tùy ý.

Ví dụ:

~~~java
// Minh hoa: rawPrivateBytes phai la gia tri khoa hop le, can bao mat.
EdECPrivateKeySpec privateSpec = new EdECPrivateKeySpec(
        NamedParameterSpec.ED25519,
        rawPrivateBytes
);

PrivateKey privateKey = KeyFactory.getInstance("Ed25519")
        .generatePrivate(privateSpec);
~~~

Hai biến `rawPrivateBytes` và `privateSpec` ở đoạn trên cần được tạo trong ngữ cảnh thực tế; đây **không phải** ví dụ Java độc lập. Không lấy một mảng byte ngẫu nhiên của khóa **khác thuật toán** rồi cho rằng nó tự động là khóa Ed25519 hợp lệ.

### 4.1. Độ dài thường gặp

Trong cách biểu diễn RFC 8032 được provider JDK hỗ trợ:

| Thuật toán | Kích thước dữ liệu private key trong `EdECPrivateKeySpec` | Ghi chú |
| --- | --- | --- |
| **Ed25519** | **32 byte** | Dữ liệu khóa riêng/seed theo Ed25519. |
| **Ed448** | **57 byte** | Dữ liệu khóa riêng/seed theo Ed448. |

Đây **không** phải độ dài của mã hóa PKCS#8. `PKCS#8` chứa thêm cấu trúc ASN.1/DER cùng định danh thuật toán. Không sao chép tùy tiện 32/57 byte đầu từ `PrivateKey.getEncoded()` để tạo `EdECPrivateKeySpec`.

Các constructor `KeySpec` chủ yếu giữ **dữ liệu mô tả**; không xem việc dựng được `EdECPrivateKeySpec` từ một mảng byte là bằng chứng provider đã chấp nhận nó như một khóa riêng hợp lệ. Việc chuyển thành `PrivateKey` đi qua `KeyFactory.generatePrivate`; lỗi có thể được báo ở bước này.

### 4.2. Bảo vệ mảng byte bằng defensive copy

JavaDoc `EdECPrivateKeySpec` quy định:

- Constructor **sao chép** mảng `bytes` đầu vào để việc sửa mảng gốc không tự sửa dữ liệu trong spec.
- Mỗi lần gọi `getBytes()` trả về **một bản sao mới**, không phải mảng nội bộ của spec.

Điều này quan trọng vì `byte[]` có thể thay đổi:

~~~java
byte[] a = privateSpec.getBytes();
byte[] b = privateSpec.getBytes();

boolean differentObjects = a != b; // true
boolean sameContents = java.util.Arrays.equals(a, b); // true

a[0] ^= 1; // Chi sua ban copy a.
boolean protectedSpec =
        java.util.Arrays.equals(b, privateSpec.getBytes()); // true
~~~

Đây là **đoạn minh họa trong ngữ cảnh đã có `privateSpec`**. Dù defensive copy bảo vệ tính bất biến của spec, nó **không tự bảo vệ bí mật** khỏi việc bị ghi log, gửi qua mạng, dump bộ nhớ hoặc giữ trong biến/caches lâu hơn cần thiết.

Thực hành an toàn:

- Không in raw private bytes, không chuyển chúng thành `String` để debug.
- Hạn chế thời gian tồn tại của các bản sao khóa riêng; khi không cần nữa, có thể dùng `Arrays.fill(copy, (byte) 0)` như một bước giảm rủi ro ở mức ứng dụng.
- Xóa bản sao **không bảo đảm** xóa vật liệu khóa trong `KeySpec`, `PrivateKey`, JVM heap, provider hoặc các bản sao do hệ thống khác giữ.
- Nếu khóa nằm trong HSM, secure element hoặc dịch vụ ký, **tránh yêu cầu xuất khóa riêng**. Provider có thể cố ý không cho trích xuất.
- Xem kiểm soát truy cập, bảo quản khóa, rotation và lifecycle là trách nhiệm thiết kế hệ thống, không phải thuộc tính mặc định của `KeySpec`.

## 5. Chương trình Java hoàn chỉnh: KeyPair → KeySpec → KeyPair → ký/xác minh

Ví dụ dưới đây dùng **chỉ API chuẩn từ Java 15**, không cần thư viện ngoài. Mã chạy cả **Ed25519** và **Ed448** bằng cùng một quy trình:

1. Sinh cặp khóa bằng `KeyPairGenerator`.
2. Lấy `EdECPublicKeySpec` và `EdECPrivateKeySpec` qua `KeyFactory.getKeySpec`.
3. Phục hồi đối tượng `PublicKey` và `PrivateKey` bằng `generatePublic` và `generatePrivate`.
4. Dùng `Signature` ký một thông điệp UTF-8.
5. Kiểm tra chữ ký hợp lệ với thông điệp gốc và **không hợp lệ** với thông điệp đã đổi.
6. Chứng minh `EdECPrivateKeySpec.getBytes()` trả bản sao mới.

**Lưu file `EdECSpecDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.*;
import java.util.Arrays;

public class EdECSpecDemo {
    private static void demonstrate(String algorithm, NamedParameterSpec curve)
            throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance(algorithm);
        generator.initialize(curve);
        KeyPair pair = generator.generateKeyPair();

        KeyFactory factory = KeyFactory.getInstance(algorithm);
        EdECPublicKeySpec publicSpec = factory.getKeySpec(
                pair.getPublic(), EdECPublicKeySpec.class);
        EdECPrivateKeySpec privateSpec = factory.getKeySpec(
                pair.getPrivate(), EdECPrivateKeySpec.class);

        PublicKey restoredPublic = factory.generatePublic(publicSpec);
        PrivateKey restoredPrivate = factory.generatePrivate(privateSpec);

        byte[] a = privateSpec.getBytes();
        byte[] b = privateSpec.getBytes();
        boolean returnsCopy = a != b;
        a[0] ^= 1;
        boolean protectedContents = Arrays.equals(b, privateSpec.getBytes());

        byte[] message = "Java 15 EdEC KeySpec".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(restoredPrivate);
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(restoredPublic);
        verifier.update(message);
        boolean valid = verifier.verify(signature);

        verifier.initVerify(restoredPublic);
        verifier.update("changed message".getBytes(StandardCharsets.UTF_8));
        boolean changedAccepted = verifier.verify(signature);

        System.out.println(algorithm + ".params=" +
                publicSpec.getParams().getName() + "/" +
                privateSpec.getParams().getName());
        System.out.println(algorithm + ".privateBytes=" +
                privateSpec.getBytes().length);
        System.out.println(algorithm + ".yNonnegative=" +
                (publicSpec.getPoint().getY().signum() >= 0));
        System.out.println(algorithm + ".defensiveCopy=" +
                (returnsCopy && protectedContents));
        System.out.println(algorithm + ".formats=" +
                restoredPublic.getFormat() + "/" +
                restoredPrivate.getFormat());
        System.out.println(algorithm + ".valid=" + valid);
        System.out.println(algorithm + ".modifiedValid=" + changedAccepted);
        Arrays.fill(a, (byte) 0);
        Arrays.fill(b, (byte) 0);
    }

    public static void main(String[] args) throws Exception {
        demonstrate("Ed25519", NamedParameterSpec.ED25519);
        demonstrate("Ed448", NamedParameterSpec.ED448);
    }
}
~~~

Dùng JDK 17+ hoặc JDK hiện đại có provider hỗ trợ EdDSA. Các API sử dụng đã tồn tại ở Java 15. Biên dịch với target Java 15:

~~~bash
javac --release 15 -encoding UTF-8 EdECSpecDemo.java
java EdECSpecDemo
~~~

**Đầu ra đã kiểm chứng trên JDK 24 (biên dịch với `--release 15`):**

~~~text
Ed25519.params=Ed25519/Ed25519
Ed25519.privateBytes=32
Ed25519.yNonnegative=true
Ed25519.defensiveCopy=true
Ed25519.formats=X.509/PKCS#8
Ed25519.valid=true
Ed25519.modifiedValid=false
Ed448.params=Ed448/Ed448
Ed448.privateBytes=57
Ed448.yNonnegative=true
Ed448.defensiveCopy=true
Ed448.formats=X.509/PKCS#8
Ed448.valid=true
Ed448.modifiedValid=false
~~~

**Giải thích đầu ra:**

- `params=Ed25519/Ed25519` hoặc `Ed448/Ed448`: hai spec giữ cùng tập tham số của cặp khóa tương ứng.
- `privateBytes=32` và `57`: độ dài mảng khóa riêng mà provider trả cho hai loại EdDSA trong phép kiểm thử.
- `yNonnegative=true`: tọa độ y của điểm khóa công khai là số không âm. Đây **không phải** phép kiểm tra key hợp lệ toàn diện; ví dụ không in giá trị `xOdd` vì phụ thuộc cặp khóa ngẫu nhiên.
- `defensiveCopy=true`: hai lần gọi `getBytes()` là các mảng khác nhau; sửa bản sao đầu không đổi bytes trong spec.
- `formats=X.509/PKCS#8`: **định dạng mã hóa** đối tượng khóa theo provider mẫu, không phải nội dung trực tiếp của EdEC specs.
- `valid=true`: `Signature.verify` xác minh thành công khi thông điệp, thuật toán và cặp khóa khớp nhau.
- `modifiedValid=false`: chữ ký của thông điệp gốc không hợp lệ đối với chuỗi thông điệp khác. Không cần xem chữ ký hoặc khóa riêng để đưa ra kết luận đó.

Mỗi lần chạy chương trình tạo **các khóa ngẫu nhiên mới**, nên **không in** chữ ký cụ thể hoặc raw key bytes và không kỳ vọng hai lần chạy tạo cùng bytes. Những dòng kết quả thể hiện điều kiện được kiểm chứng bằng API, không dựa vào số ngẫu nhiên cố định.

### 5.1. Chú ý khi chạy với provider khác

`KeyFactory.getKeySpec(key, EdECPrivateKeySpec.class)` trong ví dụ hoạt động với provider JDK đã kiểm thử. Nhưng **không phải mọi khóa riêng đều được phép trích xuất**: khóa bảo vệ bằng phần cứng, `PrivateKey` opaque hoặc provider hạn chế xuất có thể không hỗ trợ loại spec này và ném `InvalidKeySpecException`.

Tương tự, một provider có thể không hỗ trợ `Ed448`, hoặc cách xuất khóa/`getFormat()` khác. Khi viết thư viện dùng nhiều provider:

- Tránh cast tất cả implementation khóa thành `EdECPrivateKey` nếu provider không cam kết.
- Không giả định `getEncoded()` luôn trả bytes: API `Key.getEncoded()` có thể trả `null` nếu key không cho xuất.
- Kiểm tra hỗ trợ bằng các API JCA thực tế và báo lỗi có ý nghĩa.
- Khi chỉ cần **ký**, hãy dùng `Signature.initSign(privateKey)` trực tiếp thay vì buộc phải xuất khóa riêng thành spec. Xuất khóa làm tăng bề mặt rủi ro.

## 6. Chuyển đổi với `EdECPublicKey` và `EdECPrivateKey`

Ngoài `KeyFactory.getKeySpec`, Java 15 có hai interface mô tả đối tượng khóa EdEC thực tế:

- `java.security.interfaces.EdECPublicKey`: có `getPoint()` lấy `EdECPoint`.
- `java.security.interfaces.EdECPrivateKey`: có `getBytes()` lấy `Optional<byte[]>`; có thể **rỗng** nếu provider không muốn lộ private key material.
- `EdECKey` là interface chung, với các tham số được cung cấp theo hợp đồng API.

Có thể xây spec từ khóa hỗ trợ interface:

~~~java
import java.security.interfaces.EdECPublicKey;
import java.security.interfaces.EdECPrivateKey;
import java.security.spec.EdECPublicKeySpec;
import java.security.spec.EdECPrivateKeySpec;
import java.security.spec.NamedParameterSpec;

// Minh hoa, can co publicKey/privateKey EdEC tu provider tuong thich.
EdECPublicKey pub = (EdECPublicKey) publicKey;
EdECPrivateKey priv = (EdECPrivateKey) privateKey;

NamedParameterSpec pubParams = pub.getParams();
EdECPublicKeySpec pubSpec =
        new EdECPublicKeySpec(pubParams, pub.getPoint());

byte[] privateBytes = priv.getBytes().orElseThrow(
        () -> new IllegalStateException("Private key is not extractable")
);
EdECPrivateKeySpec privSpec =
        new EdECPrivateKeySpec(priv.getParams(), privateBytes);
~~~

Đây là **đoạn minh họa không độc lập**, cần có `publicKey` và `privateKey` tương ứng, cùng provider thực sự triển khai các interface. Không cố lấy private bytes nếu khóa được thiết kế không thể xuất.

Điểm dễ nhầm: `EdECPrivateKey.getBytes()` trả **`Optional<byte[]>`** vì key provider có thể giữ bí mật; còn `EdECPrivateKeySpec.getBytes()` trả **`byte[]`** (bản sao của bytes đã đặt trong spec). Hai phương thức cùng tên nhưng **khác chữ ký và mục đích**.

**Không dùng khóa riêng làm dữ liệu log.** Nếu bạn chỉ cần xác minh chữ ký, `EdECPublicKeySpec` hoặc `PublicKey` là đủ; không cần truy cập private key.

## 7. Khi nào dùng raw EdEC specs, khi nào dùng X.509/PKCS#8?

Các dạng dữ liệu dưới đây không đồng nghĩa:

| Dạng | Chứa gì? | API nên dùng |
| --- | --- | --- |
| `EdECPublicKeySpec` | `NamedParameterSpec` + điểm `EdECPoint(y, xOdd)`. | `KeyFactory.generatePublic(spec)`. |
| `EdECPrivateKeySpec` | `NamedParameterSpec` + bit string khóa riêng dạng `byte[]`. | `KeyFactory.generatePrivate(spec)`. |
| **Raw EdDSA public key bytes** | Điểm nén theo quy tắc RFC 8032; phụ thuộc curve và byte order. | Decoder đúng chuẩn → `EdECPoint`, hoặc thư viện chuyển đổi phù hợp. |
| **Raw EdDSA private key bytes/seed** | Dữ liệu khóa riêng theo Ed25519/Ed448. | `EdECPrivateKeySpec` khi biết đúng curve và format. |
| **X.509 SubjectPublicKeyInfo (DER)** | Cấu trúc chứa thuật toán + key công khai. | `X509EncodedKeySpec`. |
| **PKCS#8 PrivateKeyInfo (DER)** | Cấu trúc chứa thuật toán + dữ liệu khóa riêng. | `PKCS8EncodedKeySpec`. |

Khi đã có khóa ở định dạng DER chuẩn, có thể dùng:

~~~java
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.PrivateKey;
import java.security.spec.X509EncodedKeySpec;
import java.security.spec.PKCS8EncodedKeySpec;

// Minh hoa: x509Der/pkcs8Der la byte[] da duoc doc dung dinh dang.
KeyFactory factory = KeyFactory.getInstance("Ed25519");

PublicKey publicKey = factory.generatePublic(
        new X509EncodedKeySpec(x509Der)
);
PrivateKey privateKey = factory.generatePrivate(
        new PKCS8EncodedKeySpec(pkcs8Der)
);
~~~

`x509Der` và `pkcs8Der` là các biến được cung cấp từ file/kho khóa thực tế, không phải tên biến có sẵn. Đây là **mã minh họa không độc lập**.

**Đừng lấy `privateKey.getEncoded()` rồi đưa thẳng vào constructor `EdECPrivateKeySpec`**: mảng PKCS#8 là một **gói cấu trúc mã hóa**, còn spec mong dữ liệu khóa riêng dạng raw bit string. Hai cách trao đổi khóa cần định dạng được quy định rõ từ bên gửi và bên nhận.

Nếu gửi khóa qua JSON/HTTP, cần thống nhất giao thức: loại khóa, curve, dữ liệu là raw hay DER, Base64/Base64URL, và chính sách xác thực. Đừng chỉ lưu `"key": "..."` mà không nêu loại mã hóa.

### 7.1. Chọn công cụ theo nhu cầu

- **Đã có `PublicKey` / `PrivateKey` và chỉ muốn ký/xác minh:** gọi `Signature` trực tiếp; **không cần spec**.
- **Có tọa độ EdEC công khai từ định dạng hợp lệ:** tạo `EdECPublicKeySpec` rồi `KeyFactory.generatePublic`.
- **Có private seed hợp lệ và curve rõ ràng:** tạo `EdECPrivateKeySpec` rồi `KeyFactory.generatePrivate`; bảo vệ bytes cẩn thận.
- **Có DER X.509 hoặc PKCS#8:** dùng `X509EncodedKeySpec` hoặc `PKCS8EncodedKeySpec`.
- **Đang kiểm tra một khóa có thể xuất:** `KeyFactory.getKeySpec` chỉ khi provider hỗ trợ và bạn thực sự cần material.

**Lưu ý:** `KeyFactory.generatePrivate(EdECPrivateKeySpec)` chỉ tạo **private key**; nó không tự trả về `KeyPair` hoặc một `EdECPublicKeySpec` tương ứng. Nếu quy trình cần public key để xác minh, phải quản lý hoặc tái tạo public key theo một cơ chế hợp lệ, không tự “đoán” điểm từ mảng bytes.

## 8. Kiểm tra dữ liệu đầu vào và xử lý lỗi

Một API tiếp nhận EdEC keys từ bên ngoài cần thực hiện cả hai tầng kiểm tra: **đặc tả dữ liệu** và **tính hợp lệ mật mã**.

### 8.1. Kiểm tra trước `KeyFactory`

Trước khi tạo spec, xác định:

1. Thuật toán và curve đã được chọn rõ: `Ed25519` hoặc `Ed448`.
2. Chuỗi raw/DER sử dụng đúng encoding, không mập mờ.
3. Kích thước dữ liệu và định dạng phù hợp với loại key đang dùng.
4. Không có thao tác tự đảo endian hoặc bỏ bit sign mà không dựa trên đặc tả giao thức.
5. Với private bytes: dữ liệu lấy từ nguồn tin cậy và đã bảo vệ khi lưu trữ/truyền tải.

Ví dụ kiểm tra độ dài đầu vào **Ed25519 raw private seed** trước khi tạo spec:

~~~java
// Minh hoa trong ngu canh rawPrivateBytes do ung dung da nhan.
if (rawPrivateBytes.length != 32) {
    throw new IllegalArgumentException("Expected 32 Ed25519 private bytes");
}

EdECPrivateKeySpec spec = new EdECPrivateKeySpec(
        NamedParameterSpec.ED25519,
        rawPrivateBytes
);

PrivateKey key = KeyFactory.getInstance("Ed25519")
        .generatePrivate(spec);
~~~

Kiểm tra độ dài là **điều kiện cần**, không phải bằng chứng dữ liệu đúng định dạng, tương ứng với public key mong muốn hay đến từ nguồn đáng tin. `KeyFactory.generatePrivate` phải được phép từ chối key spec không hợp lệ.

### 8.2. Những lỗi bạn có thể gặp

| Exception / tình huống | Nguyên nhân khả dĩ | Xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Provider hiện tại không hỗ trợ `Ed25519` / `Ed448` ở API tương ứng. | Chọn runtime/provider phù hợp và kiểm tra cấu hình JCA. |
| `InvalidAlgorithmParameterException` | Tham số khởi tạo `KeyPairGenerator` không hợp lệ cho thuật toán/provider. | Kiểm tra curve và tên thuật toán đồng nhất. |
| `InvalidKeySpecException` | `KeyFactory` từ chối dữ liệu, curve hoặc không hỗ trợ xuất đặc tả từ key. | Xác định format, curve, độ dài và chính sách provider. |
| `InvalidKeyException` | `Signature.initSign/initVerify` không chấp nhận key. | Kiểm tra loại khóa, thuật toán, provider và phạm vi sử dụng. |
| `SignatureException` | Xử lý chữ ký có vấn đề, dữ liệu đầu vào hoặc key không được chấp nhận trong quá trình ký/xác minh. | Xử lý như lỗi nghiệp vụ/kỹ thuật, không nuốt exception. |
| `Signature.verify(...) == false` | Chữ ký không xác thực đối với thông điệp và public key đã chọn. | Từ chối thông điệp/chữ ký, không xem là exception bình thường. |
| `ClassCastException` khi cast key interface | Provider trả implementation khác với điều ứng dụng giả định. | Dùng `KeyFactory` hoặc kiểm tra `instanceof` trước khi cast. |
| `getBytes().isEmpty()` ở `EdECPrivateKey` | Provider không muốn cho phép xuất private bytes. | Dùng key trực tiếp cho `Signature`; không tìm cách ép xuất trái chính sách. |

Các constructor `EdECPublicKeySpec` và `EdECPrivateKeySpec` sẽ từ chối tham số `null` theo hợp đồng API. Tuy nhiên, **khởi tạo được một Java object `KeySpec` chưa đảm bảo dữ liệu mật mã hợp lệ**; phải để `KeyFactory` và provider kiểm tra tại ranh giới tạo khóa, đồng thời kiểm tra chữ ký thực tế khi cần.

### 8.3. Không tự dùng công thức đường cong để “sửa” public key

EdEC point có `y` và `xOdd` vì cách biểu diễn điểm nén cần thêm thông tin để xác định tọa độ. Tự tính x từ y trên trường hữu hạn, quản lý bit dấu, kiểm tra điểm có thuộc curve và kiểm tra encoding canonical đều là những thao tác rất dễ sai.

Ở phần lớn ứng dụng, hãy ưu tiên các dạng **X.509/PKCS#8 được provider hỗ trợ** hoặc dùng thư viện mã hóa raw point **đã được kiểm định**, thay vì tự viết phép biến đổi EdECPoint/byte[] từ đầu.

## 9. Lựa chọn thuật toán và điều không nên suy ra từ một chữ ký thành công

Ed25519/Ed448 là EdDSA signatures được thiết kế theo RFC 8032. Trong Java:

~~~java
Signature signature = Signature.getInstance("Ed25519");
// signature.initSign(privateKey);
// signature.update(messageBytes);
// byte[] signed = signature.sign();
~~~

Các lời gọi dấu comment ở trên cần những biến được tạo thực tế. Với Ed448, chọn `Signature.getInstance("Ed448")` và key Ed448 tương ứng.

**Không dùng EdEC key để mã hóa/giải mã như `Cipher`**, vì mục đích EdDSA là ký và xác minh. Không dùng cùng key material cho những chức năng mật mã khác với thiết kế đã cam kết.

Cũng cần phân biệt:

- `Signature.verify == true` chứng minh **chữ ký khớp với thông điệp, public key và thuật toán được dùng**. Nó không tự xác minh danh tính chủ sở hữu khóa.
- Cần có cách **tin cậy public key**: chứng chỉ, kho khóa, fingerprint đã xác thực, key pinning hoặc phương thức phân phối khóa phù hợp.
- Đừng ký dữ liệu chưa định nghĩa rõ encoding và cấu trúc. Cả hai phía phải đồng ý **cùng chuỗi byte**; `"xin chào"` trong UTF-8 khác bytes nếu đổi encoding hoặc chuẩn hóa văn bản khác nhau.
- Không tự “hash trước bằng SHA-256” rồi coi kết quả là hoàn toàn tương đương với mọi chế độ EdDSA. `Signature` của provider quản lý cách ký theo đúng thuật toán/chế độ đã chọn.

Khi truyền chữ ký qua wire format, phải thống nhất cách đóng gói (ví dụ Base64), khóa xác minh và độ dài dữ liệu; không tự suy luận độ dài chữ ký từ độ dài `EdECPrivateKeySpec.getBytes()`.

## 10. Kiểm thử và bảo mật trong dự án thật

Một bộ test tốt cho workflow EdEC specs gồm:

1. **Round-trip trên từng curve:** `KeyPairGenerator` → `getKeySpec` → `generatePublic/generatePrivate` → ký/xác minh.
2. **Negative verify:** chữ ký hợp lệ của thông điệp A không được xác minh với thông điệp B.
3. **Sai curve:** không chấp nhận private/public data được gắn nhầm `Ed25519` và `Ed448`. Provider có thể ném exception tùy điểm kiểm tra; không ép một loại dùng cho loại kia.
4. **Sai encoding:** dùng PKCS#8 bytes như raw `EdECPrivateKeySpec` phải bị chặn bởi validation/KeyFactory; không tự cố bỏ header bằng offset.
5. **Kiểm tra bản sao:** sửa mảng `getBytes()` không thay đổi spec; test không phải in raw key ra console.
6. **Provider không cho xuất:** business logic phải chấp nhận việc private bytes không thể trích xuất; thao tác ký trực tiếp có thể vẫn hợp lệ.
7. **Test thông điệp byte-for-byte:** chuẩn hóa UTF-8, serialization, canonicalization ở giao thức để tránh khác bytes không mong muốn.
8. **Test mã hóa và provider trên JDK đích:** những interface/spec này đã chuẩn từ Java 15, nhưng cấu hình provider và hỗ trợ thuật toán cần được kiểm chứng nơi triển khai.

### Bảo vệ khóa riêng

- Sinh khóa bằng `KeyPairGenerator` của provider phù hợp, dùng nguồn ngẫu nhiên an toàn mà provider quản lý; không tự dùng `java.util.Random` để sinh raw private bytes.
- Không hard-code khóa thật trong source code, test fixtures công khai hoặc file README.
- Không log `privateSpec.getBytes()`, `privateKey.getEncoded()`, key trong exception message hoặc fingerprint không cần thiết của private material.
- Dùng kho khóa/secret-management/HSM phù hợp với mức rủi ro ứng dụng; chỉ cấp quyền ký cho thành phần cần ký.
- Nếu có thể, **giữ khóa riêng không thể xuất** và đưa dữ liệu tới provider để ký thay vì sao chép raw bytes.
- Xóa các bản copy mảng khi không còn dùng; nhớ rằng JVM có thể có các bản copy khác, vì vậy đây chỉ là một biện pháp giảm rủi ro chứ không bảo đảm xóa bí mật triệt để.
- Thiết kế rotation, thu hồi khóa, kiểm soát truy cập, audit và quy trình xử lý sự cố.

## 11. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai? | Cách làm đúng |
| --- | --- | --- |
| Dùng `ECPublicKeySpec` cho Ed25519. | EC kiểu Weierstrass và EdEC là những key spec khác nhau. | Sử dụng `EdECPublicKeySpec` và `EdECPoint`. |
| Dùng `XECPublicKeySpec` cho Ed448. | XEC thuộc trao đổi khóa XDH, không phải EdDSA signing. | Chọn EdEC API với Ed25519/Ed448 phù hợp. |
| Đưa mảng bytes nén public key trực tiếp vào `EdECPublicKeySpec`. | Constructor cần `EdECPoint` chứ không phải `byte[]`. | Giải mã đúng thành `EdECPoint(y, xOdd)` hoặc dùng X.509 nếu có. |
| Chỉ lấy `y` và bỏ `xOdd`. | Hai trường hợp điểm có thể khác nhau về chẵn/lẻ x. | Giữ cả y và bit parity. |
| Tự dùng `new BigInteger(rawPublicBytes)`. | BigInteger và RFC 8032 raw point có quy ước endian/bit khác. | Dùng decoder đúng chuẩn hoặc định dạng chuẩn được JCA hỗ trợ. |
| Dùng PKCS#8 bytes để tạo `EdECPrivateKeySpec`. | PKCS#8 là cấu trúc DER, không phải private seed raw. | Dùng `PKCS8EncodedKeySpec`. |
| Dùng X.509 DER để tạo `EdECPoint` trực tiếp. | DER chứa thuật toán và định dạng bọc, không chỉ raw compressed point. | Dùng `X509EncodedKeySpec`. |
| Gọi `Signature` trực tiếp bằng `EdECPrivateKeySpec`. | Spec không phải đối tượng `PrivateKey`. | `KeyFactory.generatePrivate` trước, hoặc dùng `PrivateKey` sẵn có. |
| Xem `new EdECPrivateKeySpec` là “đã xác minh khóa”. | Constructor là bước mô tả dữ liệu, không phải chữ ký/mật mã validation. | Cho `KeyFactory` và provider kiểm tra, kiểm thử sign/verify. |
| In private bytes để xác nhận kết quả. | Lộ bí mật trong logs, CI và terminal. | In thuộc tính không nhạy cảm, ví dụ tên curve và cờ kết quả. |
| Tin rằng `getBytes()` luôn xuất được ở mọi provider. | Khóa riêng có thể opaque hoặc không cho export. | Kiểm tra hỗ trợ, ưu tiên ký trực tiếp bằng key. |
| Trộn key Ed25519 với `Signature("Ed448")`. | Thuật toán và curve không tương thích. | Chọn `Signature` và khóa theo cùng `NamedParameterSpec`. |
| Xác minh thành công thì tin ngay người gửi. | Verify chỉ gắn chữ ký với public key. | Cần chuỗi tin cậy và chính sách phân phối khóa riêng. |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `EdECPublicKeySpec` lưu public key bằng gì? Có phải chỉ là mảng `byte[]`?

**Đáp án:** Không. Nó lưu `NamedParameterSpec` và `EdECPoint`; điểm mang tọa độ `y` dạng `BigInteger` và bit `xOdd`. Raw compressed bytes và X.509 DER là những định dạng khác.

**Câu 2.** `EdECPrivateKeySpec.getBytes()` có trả chính mảng nội bộ để ứng dụng sửa khóa ngay trong spec không?

**Đáp án:** Không. Theo JavaDoc, constructor sao chép đầu vào và `getBytes()` tạo bản sao mới mỗi lần. Nhưng các bản sao vẫn là dữ liệu nhạy cảm cần bảo vệ.

**Câu 3.** Có thể đưa trực tiếp `PrivateKey.getEncoded()` vào `new EdECPrivateKeySpec(params, encoded)` không?

**Đáp án:** Không, nếu `getEncoded()` trả PKCS#8 DER. `EdECPrivateKeySpec` chờ raw private key bit string, còn PKCS#8 cần `PKCS8EncodedKeySpec`.

**Câu 4.** Có thể sinh một khóa Ed25519 rồi ký bằng `Signature("Ed448")` không?

**Đáp án:** Không nên và provider phải kiểm soát tính tương thích; Ed25519 và Ed448 là hai tập tham số/thuật toán khác nhau.

**Câu 5.** Nếu `EdECPrivateKey.getBytes()` trả `Optional.empty()`, có nghĩa không thể ký không?

**Đáp án:** Không. Provider có thể không cho xuất raw private bytes nhưng vẫn hỗ trợ `Signature.initSign(privateKey)` để ký mà không lộ khóa.

**Câu 6.** `Signature.verify == true` có đủ để xác thực danh tính người ký không?

**Đáp án:** Không. Nó xác minh chữ ký với public key và message bytes đã chọn; cần xác minh public key đáng tin và thuộc đúng chủ thể.

## Ghi nhớ

- **`EdECPublicKeySpec` = `NamedParameterSpec` + `EdECPoint(y, xOdd)`.**
- **`EdECPrivateKeySpec` = `NamedParameterSpec` + `byte[]` private key material.** Constructor và `getBytes()` sao chép dữ liệu, nhưng không thay thế kiểm soát bí mật.
- Dùng **`KeyFactory.generatePublic/generatePrivate`** để chuyển spec thành đối tượng khóa dùng được với `Signature`.
- **Ed25519/Ed448 là EdDSA signatures**, khác X25519/X448 dành cho XDH và khác EC key specs của ECDSA.
- **Raw keys ≠ X.509/PKCS#8 DER**: chọn đúng `KeySpec` theo định dạng thực tế.
- Ký/xác minh phải cùng curve, thuật toán và message bytes; luôn bảo vệ khóa riêng và xác thực nguồn public key.
- Các API này **vẫn đang được sử dụng trong Java hiện đại** và được cung cấp từ Java 15, không phải cú pháp preview hay cơ chế lỗi thời.

### Tài liệu chính thức còn hiệu lực

- [Java SE 15 – EdECPublicKeySpec](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/EdECPublicKeySpec.html): constructor và getters cho EdEC public key spec.
- [Java SE 15 – EdECPrivateKeySpec](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html): constructor, defensive copy và `getBytes()`.
- [Java SE 15 – EdECPoint](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/EdECPoint.html): biểu diễn `y` và `xOdd`.
- [Java SE 15 – NamedParameterSpec](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/spec/NamedParameterSpec.html): `ED25519`, `ED448`.
- [Java SE 15 – EdECPrivateKey](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html): `Optional<byte[]> getBytes()` và chính sách khóa không cho xuất.
- [Java SE 15 – EdECPublicKey](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/security/interfaces/EdECPublicKey.html): `getPoint()`.
- [OpenJDK JEP 339 – Edwards-Curve Digital Signature Algorithm](https://openjdk.org/jeps/339): đặc tả và API EdDSA trong Java 15.
- [RFC 8032 – Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032): cấu trúc Ed25519, Ed448 và cách mã hóa public/private keys.
