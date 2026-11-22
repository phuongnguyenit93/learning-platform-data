# EdECPublicKey, EdECPrivateKey và biểu diễn khóa (Java 15+)

## Mục tiêu

Hiểu cách Java biểu diễn **khóa công khai và khóa riêng của EdDSA** bằng hai interface **java.security.interfaces.EdECPublicKey** và **EdECPrivateKey**, vì sao hai interface này khác với ECPublicKey/ECPrivateKey và XECKey, và khi nào nên sử dụng **EdECPoint**, **EdECPublicKeySpec**, **EdECPrivateKeySpec**, **X509EncodedKeySpec** hay **PKCS8EncodedKeySpec**.

Sau bài học, bạn có thể:

- Tạo cặp khóa Ed25519/Ed448 bằng **KeyPairGenerator**.
- Truy cập **NamedParameterSpec**, **EdECPoint** và **Optional<byte[]>** của khóa riêng mà không vô tình in ra bí mật.
- Phân biệt **biểu diễn thành phần của khóa (key material)** với **định dạng đóng gói/trao đổi khóa (key encoding)**.
- Tái tạo khóa từ **KeyFactory** rồi xác minh bằng chữ ký EdDSA.
- Nhận biết rủi ro khi xử lý byte[] khóa riêng, khóa không cho xuất dữ liệu và sai lệch EdDSA với ECDSA/X25519.

Các API EdEC này có từ **Java 15** và vẫn được hỗ trợ ở **Java 17 trở lên**. Bài tập biên dịch với **--release 17**, không dùng API đã lỗi thời.

## 1. EdEC là khóa gì?

**EdDSA** (Edwards-curve Digital Signature Algorithm) là họ thuật toán **chữ ký số**, được tiêu chuẩn hóa trong **RFC 8032**. Hai lựa chọn phổ biến của EdDSA là:

| Thuật toán | Đường cong / tham số | Mục đích điển hình | Interface khóa Java |
| --- | --- | --- | --- |
| **Ed25519** | **NamedParameterSpec.ED25519** | Ký và kiểm tra chữ ký | EdECPublicKey / EdECPrivateKey |
| **Ed448** | **NamedParameterSpec.ED448** | Ký và kiểm tra chữ ký | EdECPublicKey / EdECPrivateKey |

Trong Java, tạo khóa bằng **KeyPairGenerator.getInstance("Ed25519")** hoặc **getInstance("Ed448")**; dùng **Signature.getInstance(...)** để ký và xác minh.

**Phân biệt ba họ giao diện khóa**:

- **EdECPublicKey / EdECPrivateKey**: khóa **EdDSA** theo RFC 8032, dùng với chữ ký Ed25519 và Ed448.
- **ECPublicKey / ECPrivateKey**: khóa đường cong elliptic của các thuật toán kiểu **ECDSA** và nhiều ứng dụng EC khác, dùng **ECPoint**, **ECParameterSpec**; không có cùng biểu diễn với EdEC.
- **XECPublicKey / XECPrivateKey**: khóa cho thuật toán theo RFC 7748 như **X25519/X448**, dùng chủ yếu cho **thỏa thuận khóa**; không phải EdDSA. Các tên có số 25519/448 giống nhau **không** làm khóa có thể tráo đổi giữa hai họ.

Một khóa Ed25519 **không được sử dụng như khóa X25519** chỉ bằng cách đổi tên thuật toán, ép kiểu giao diện hoặc đổi chuỗi "Ed25519" thành "X25519". Chúng có quy tắc tạo khóa, biểu diễn và mục đích khác nhau.

## 2. Các interface EdEC trong Java

### 2.1. EdECKey: thông tin tham số

**java.security.interfaces.EdECKey** là interface chung cho EdECPublicKey và EdECPrivateKey. Điểm quan trọng là:

~~~java
NamedParameterSpec params = publicKey.getParams();
String curve = params.getName();
~~~

Đây là đoạn code **minh họa** trong phương thức có biến publicKey kiểu EdECPublicKey. **NamedParameterSpec** chứa tên nhóm tham số được dùng, chẳng hạn "Ed25519" hoặc "Ed448". Trong chương trình thực tế, đừng đoán đường cong chỉ bằng độ dài byte mã hóa, bởi định dạng có thể chứa header hoặc thông tin thuật toán.

**NamedParameterSpec.ED25519** và **NamedParameterSpec.ED448** là các đối tượng tham số tiện dụng. Khi cần xem tên để lựa chọn luồng xử lý, dùng **getParams().getName()** với điều kiện provider trả về tham số phù hợp; không chỉ dựa vào tên từ một file hoặc thuộc tính không tin cậy.

### 2.2. EdECPublicKey: public key là một EdECPoint

API trọng tâm:

~~~java
EdECPoint point = publicKey.getPoint();
BigInteger y = point.getY();
boolean xOdd = point.isXOdd();
~~~

Đoạn trên là minh họa trong một phương thức đã có publicKey và import java.math.BigInteger, java.security.spec.EdECPoint. Khóa công khai EdDSA được biểu diễn dưới dạng **một điểm trên Edwards curve**.

**EdECPoint** không dùng cặp tọa độ affine x/y như **java.security.spec.ECPoint** của ECDSA. Để mô tả EdEC point theo RFC 8032, Java lưu:

- **y**: tọa độ y là **BigInteger** đại diện một phần tử trường hữu hạn, cần phù hợp tham số đường cong.
- **xOdd**: boolean biểu thị tính **lẻ/chẵn của tọa độ x**; đây là phần thông tin giúp phân biệt lựa chọn điểm tương ứng.

Trong biểu diễn điểm nén của RFC 8032, thông tin về y và bit dấu/tính lẻ của x được mã hóa theo quy tắc của đường cong. Đây **không phải** phép ghép tùy tiện hai chuỗi hay hai byte[].

**Cảnh báo về tính hợp lệ:** khởi tạo **new EdECPoint(xOdd, y)** chỉ tạo đối tượng mang dữ liệu điểm; không có nghĩa mọi BigInteger y đều là điểm công khai hợp lệ. Thành phần cung cấp khóa hoặc xác minh chữ ký có thể từ chối giá trị ngoài trường hoặc không phù hợp thuật toán. Luôn sử dụng **KeyFactory** và provider được tin cậy để kiểm tra.

### 2.3. EdECPrivateKey: private key là bit string

API trọng tâm:

~~~java
Optional<byte[]> maybeSecret = privateKey.getBytes();
~~~

Đây là đoạn minh họa trong phương thức có biến privateKey kiểu EdECPrivateKey và import java.util.Optional.

Theo giao diện Java, private key EdEC được biểu diễn bằng một **bit string** có số bit là bội của 8, có thể tiếp cận như byte[]. **getBytes()** trả **Optional<byte[]>**, không phải byte[] bắt buộc có dữ liệu:

- **Optional có giá trị:** provider cho phép truy xuất bản sao các byte biểu diễn private key.
- **Optional.empty():** provider **không muốn hoặc không thể xuất** giá trị khóa riêng. Điều này có thể xảy ra với khóa nằm ở phần cứng, token bảo mật hoặc một triển khai hạn chế xuất dữ liệu.

Bắt buộc xử lý Optional hợp lệ; đừng gọi **get()** hoặc **orElseThrow()** trong mọi luồng mà không xét chính sách khóa. Khóa không xuất được vẫn có thể hỗ trợ **Signature.initSign(privateKey)** thông qua provider thích hợp.

**Không ghi log privateKey.getBytes(), không chuyển bí mật thành String và không lưu dưới dạng văn bản thuần** chỉ để tiện debug. Những byte ấy là vật liệu mật mã nhạy cảm.

## 3. Hai lớp biểu diễn: thành phần khóa và encoding chuẩn

Đây là nguồn nhầm lẫn phổ biến nhất.

### Lớp A — biểu diễn theo thành phần của thuật toán

| Đối tượng/API | Chứa gì? | Công dụng |
| --- | --- | --- |
| **EdECPublicKey.getPoint()** | **EdECPoint(xOdd, y)** | Xem thành phần điểm công khai |
| **EdECPrivateKey.getBytes()** | **Optional<byte[]>** của private-key bit string | Truy cập vật liệu khóa riêng **nếu provider cho phép** |
| **EdECPublicKeySpec(params, point)** | Tham số EdDSA + điểm công khai | Tạo khóa công khai qua KeyFactory |
| **EdECPrivateKeySpec(params, bytes)** | Tham số EdDSA + private-key bit string | Tạo khóa riêng qua KeyFactory |

Với các biểu diễn raw EdDSA theo **RFC 8032**, public key thường có độ dài **32 byte (Ed25519)** hoặc **57 byte (Ed448)**, và private-key seed thường dài **32 byte (Ed25519)** hoặc **57 byte (Ed448)**. **Đừng suy ra** rằng mọi byte[] trả về từ bất kỳ phương thức Java nào đều chính là raw public-key bytes hay seed ở định dạng giao thức đó. Cần xét **loại API và đặc tả định dạng**, không chỉ nhìn độ dài.

### Lớp B — encoding có cấu trúc để trao đổi/lưu trữ

**java.security.Key** có các phương thức:

~~~java
String format = key.getFormat();
byte[] encoded = key.getEncoded();
~~~

Đây là đoạn code minh họa trong phương thức đã có biến key kiểu Key.

Đối với khóa EdEC thuộc provider phần mềm thông thường trong JDK:

- **Khóa công khai:** **getFormat() = "X.509"** và **getEncoded()** trả về **DER SubjectPublicKeyInfo (SPKI)**; dùng **X509EncodedKeySpec** để đọc lại.
- **Khóa riêng:** **getFormat() = "PKCS#8"** và **getEncoded()** trả về **DER PrivateKeyInfo/PKCS#8**; dùng **PKCS8EncodedKeySpec** để đọc lại.

**X.509** ở đây là tên định dạng khóa công khai mà JCA sử dụng, **không có nghĩa** getEncoded() trả về một chứng chỉ X.509 đầy đủ. Nó là cấu trúc **SubjectPublicKeyInfo**, trong đó có thông tin thuật toán và vật liệu khóa công khai.

**PKCS#8** cũng là một cấu trúc chứa thông tin thuật toán và vật liệu khóa riêng; **getEncoded() không tự mã hóa/bảo mật khóa riêng bằng mật khẩu**. Không lưu byte[] PKCS#8 chưa bảo vệ ở vị trí công khai.

Không phải provider nào cũng cho phép xuất khóa: **getFormat() có thể là null**, **getEncoded() có thể là null** đối với khóa opaque hoặc hardware-backed. Một Key không xuất được không phải là khóa “hỏng”.

### So sánh ngắn gọn

| Nguồn dữ liệu | Có header/metadata thuật toán? | Có nên dùng ngay như input của KeyFactory? |
| --- | --- | --- |
| **getPoint()** | Không phải file SPKI | Dùng cùng NamedParameterSpec trong **EdECPublicKeySpec** |
| **getBytes() của EdECPrivateKey** | Private-key bit string, không phải PKCS#8 | Dùng cùng NamedParameterSpec trong **EdECPrivateKeySpec**, nếu được phép xuất |
| **getEncoded() của public key** | Có cấu trúc SPKI/X.509 | **X509EncodedKeySpec(encoded)** |
| **getEncoded() của private key** | Có cấu trúc PKCS#8 | **PKCS8EncodedKeySpec(encoded)** |

Lỗi điển hình: truyền raw **getBytes()** của EdECPrivateKey vào **PKCS8EncodedKeySpec**. Điều đó **không đúng định dạng** vì PKCS#8 yêu cầu cấu trúc DER có metadata, không chỉ private-key bit string.

Ngược lại, không đưa **getEncoded() public SPKI** thẳng vào một chương trình tự phân tích theo format public-key nén 32/57 byte; SPKI chứa lớp wrapper ASN.1/DER bên ngoài.

## 4. Tạo khóa EdEC bằng KeyPairGenerator

Ví dụ phần lõi:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
KeyPair pair = generator.generateKeyPair();

EdECPublicKey publicKey = (EdECPublicKey) pair.getPublic();
EdECPrivateKey privateKey = (EdECPrivateKey) pair.getPrivate();
~~~

Đoạn code trên là minh họa trong phương thức có xử lý **NoSuchAlgorithmException**, với import tương ứng từ java.security và java.security.interfaces.

Thuật toán **Ed25519** hoặc **Ed448** được chỉ định ở KeyPairGenerator, nên không cần gọi **initialize(256)** như cách đôi khi viết cho RSA/ECDSA. Tham số curve là một **tập thông số được xác định bằng tên**, không đơn giản là số bit của khóa.

Có thể dùng **KeyPairGenerator.getInstance("EdDSA")** và cấu hình tham số cụ thể bằng **NamedParameterSpec.ED25519 / ED448** ở các provider có hỗ trợ, nhưng khi muốn ví dụ đơn giản, minh bạch và ít phụ thuộc cách chọn mặc định, hãy yêu cầu rõ **"Ed25519"** hoặc **"Ed448"**.

Không ép kiểu interface nếu đối tượng trả về từ provider không triển khai giao diện đó. Trong trường hợp provider tùy biến, có thể dùng **KeyFactory** để chuyển sang khóa thích hợp hoặc chỉ sử dụng giao diện chung **PublicKey/PrivateKey** theo thuật toán được hỗ trợ.

## 5. Tạo lại khóa từ EdECPublicKeySpec và EdECPrivateKeySpec

### Khóa công khai theo điểm

~~~java
EdECPublicKeySpec publicSpec =
        new EdECPublicKeySpec(publicKey.getParams(), publicKey.getPoint());
EdECPublicKey publicCopy = (EdECPublicKey)
        factory.generatePublic(publicSpec);
~~~

Đây là đoạn minh họa trong phương thức có publicKey kiểu EdECPublicKey, factory kiểu KeyFactory và xử lý các lỗi KeySpec.

**EdECPublicKeySpec** kết hợp **NamedParameterSpec** và **EdECPoint**. **KeyFactory.generatePublic()** làm việc với nhà cung cấp thuật toán để xây dựng PublicKey. Không được bỏ thông tin đường cong: cùng hai giá trị xOdd và y chưa tự chỉ rõ Ed25519 hay Ed448.

### Khóa riêng theo bit string

~~~java
EdECPrivateKeySpec privateSpec =
        factory.getKeySpec(privateKey, EdECPrivateKeySpec.class);
EdECPrivateKey privateCopy = (EdECPrivateKey)
        factory.generatePrivate(privateSpec);
~~~

Đây là đoạn minh họa trong phương thức có privateKey và factory phù hợp, với điều kiện **provider cho phép trích xuất key spec**. Một số khóa bảo vệ trong hardware/keystore không xuất được, khiến phép chuyển này không khả dụng.

**EdECPrivateKeySpec.getBytes()** trả về **bản sao mới** của byte[] theo hợp đồng Java. Constructor của EdECPrivateKeySpec cũng sao chép mảng đầu vào; nhưng các đối tượng chứa khóa trong bộ nhớ vẫn cần quản lý vòng đời và an toàn phù hợp. Việc xóa một bản sao byte[] **không xóa** tất cả bản sao trong KeySpec/Key hoặc bộ nhớ provider.

**Không tự suy ra public key từ private seed bằng các phép biến đổi tự chế**, và không cố dùng ECPublicKeySpec/ECPrivateKeySpec của thuật toán Weierstrass. Khi cần lấy khóa tương ứng hoặc tái tạo cặp khóa, hãy dùng API provider, dữ liệu khóa được lưu trữ hợp lệ và các định dạng được đặc tả.

## 6. Tạo lại khóa từ SPKI/X.509 và PKCS#8

Đối với khóa xuất được, cách trao đổi phổ biến là:

~~~java
byte[] publicDer = publicKey.getEncoded();
byte[] privateDer = privateKey.getEncoded();

KeyFactory factory = KeyFactory.getInstance("Ed25519");
PublicKey restoredPublic =
        factory.generatePublic(new X509EncodedKeySpec(publicDer));
PrivateKey restoredPrivate =
        factory.generatePrivate(new PKCS8EncodedKeySpec(privateDer));
~~~

Đây là đoạn code minh họa, **không phải chương trình độc lập**, và yêu cầu kiểm tra null với provider không cho xuất. Nó chỉ phù hợp khi public/private đều thuộc Ed25519; dùng đúng thuật toán tương ứng với key material, không lẫn Ed448.

**Tại sao cần hai lớp KeySpec khác nhau?**

- **X509EncodedKeySpec** chứa khóa **công khai** theo **SubjectPublicKeyInfo**.
- **PKCS8EncodedKeySpec** chứa khóa **riêng** theo **PKCS#8**.
- **KeyFactory** khôi phục đối tượng khóa theo **thuật toán và provider**.
- Hai khóa có thể được tái tạo thành **đối tượng Java khác** nhưng vẫn biểu diễn cùng vật liệu mật mã và dùng để kiểm tra chữ ký hợp lệ.

Để trao đổi ngoài Java, hãy thỏa thuận **định dạng thực tế**. Một PEM kiểu **BEGIN PUBLIC KEY** thường bọc DER SubjectPublicKeyInfo bằng Base64; **BEGIN PRIVATE KEY** thường bọc PKCS#8 không mã hóa. Phần nhãn và nội dung PEM không đồng nghĩa với byte[] raw Ed25519; cần giải mã đúng lớp wrapper. Việc dùng PEM cũng **không tự bảo vệ** khóa riêng.

### Kích thước và byte order

**EdECPoint.getY()** trả **BigInteger**, không phải byte[] raw public key. **BigInteger.toByteArray()** tạo biểu diễn **big-endian, bù hai có dấu** với độ dài có thể thay đổi, **không phải** trực tiếp 32 byte Ed25519 hoặc 57 byte Ed448 theo RFC 8032.

Trong RFC 8032, điểm công khai được mã hóa dạng nén, dùng y ở **little-endian** cùng một bit thông tin của x theo quy tắc đường cong. Đừng tự viết mã encode/decode điểm bằng một phép đảo mảng hoặc lấy BigInteger.toByteArray() nếu chưa xử lý đúng dấu, padding, giới hạn trường và kiểm tra điểm. Khi ứng dụng chỉ cần lưu và trao đổi khóa, ưu tiên **getEncoded()/X509EncodedKeySpec** hoặc một thư viện triển khai định dạng raw được kiểm thử đầy đủ.

## 7. Chương trình Java 17+ hoàn chỉnh: hai biểu diễn và chữ ký

Ví dụ dưới đây sử dụng cả **Ed25519** và **Ed448**, kiểm tra hai tuyến tạo lại khóa:

1. **Biểu diễn thành phần:** public key thành **EdECPoint + NamedParameterSpec**, private key thành **EdECPrivateKeySpec**, sau đó KeyFactory dựng đối tượng khóa và **ký/xác minh**.
2. **Định dạng tiêu chuẩn:** public **X.509/SPKI**, private **PKCS#8**, sau đó KeyFactory dựng lại khóa và **ký/xác minh**.

Chương trình **không in vật liệu khóa riêng, chữ ký hay private-key seed**. Các giá trị in ra chỉ là metadata và kết quả boolean. Lưu mã thành **EdECRepresentationDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.EdECPrivateKey;
import java.security.interfaces.EdECPublicKey;
import java.security.spec.*;
import java.util.Arrays;
import java.util.Optional;

public class EdECRepresentationDemo {
    private static void check(String curve) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance(curve);
        KeyPair pair = generator.generateKeyPair();

        EdECPublicKey publicKey = (EdECPublicKey) pair.getPublic();
        EdECPrivateKey privateKey = (EdECPrivateKey) pair.getPrivate();
        EdECPoint point = publicKey.getPoint();

        System.out.println("Thuật toán: " + curve);
        System.out.println("Tham số public: " + publicKey.getParams().getName());
        System.out.println("Tham số private: " + privateKey.getParams().getName());
        System.out.println("Y không âm: " + (point.getY().signum() >= 0));
        System.out.println("Định dạng public: " + publicKey.getFormat());
        System.out.println("Định dạng private: " + privateKey.getFormat());

        byte[] x509 = publicKey.getEncoded();
        byte[] pkcs8 = privateKey.getEncoded();
        Optional<byte[]> optionalBytes = privateKey.getBytes();
        System.out.println("Có byte private: " + optionalBytes.isPresent());

        KeyFactory factory = KeyFactory.getInstance(curve);
        EdECPublicKey byPoint = (EdECPublicKey) factory.generatePublic(
                new EdECPublicKeySpec(publicKey.getParams(), point));
        EdECPrivateKeySpec privateSpec =
                factory.getKeySpec(privateKey, EdECPrivateKeySpec.class);
        EdECPrivateKey byBytes =
                (EdECPrivateKey) factory.generatePrivate(privateSpec);

        PublicKey byX509 = factory.generatePublic(
                new X509EncodedKeySpec(x509));
        PrivateKey byPkcs8 = factory.generatePrivate(
                new PKCS8EncodedKeySpec(pkcs8));

        byte[] message = "Xin chào EdDSA".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance(curve);
        signer.initSign(byBytes);
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance(curve);
        verifier.initVerify(byPoint);
        verifier.update(message);
        System.out.println("Spec ký và xác minh: " + verifier.verify(signature));

        signer.initSign(byPkcs8);
        signer.update(message);
        byte[] signedWithPkcs8 = signer.sign();
        verifier.initVerify(byX509);
        verifier.update(message);
        System.out.println("X509/PKCS8 ký và xác minh: "
                + verifier.verify(signedWithPkcs8));

        Arrays.fill(x509, (byte) 0);
        Arrays.fill(pkcs8, (byte) 0);
        optionalBytes.ifPresent(bytes -> Arrays.fill(bytes, (byte) 0));
        byte[] privateSpecCopy = privateSpec.getBytes();
        Arrays.fill(privateSpecCopy, (byte) 0);
    }

    public static void main(String[] args) throws Exception {
        check("Ed25519");
        check("Ed448");
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac --release 17 -encoding UTF-8 EdECRepresentationDemo.java
java EdECRepresentationDemo
~~~

**Stdout đã kiểm chứng khi chạy trên JDK 24 (SunEC provider):**

~~~text
Thuật toán: Ed25519
Tham số public: Ed25519
Tham số private: Ed25519
Y không âm: true
Định dạng public: X.509
Định dạng private: PKCS#8
Có byte private: true
Spec ký và xác minh: true
X509/PKCS8 ký và xác minh: true
Thuật toán: Ed448
Tham số public: Ed448
Tham số private: Ed448
Y không âm: true
Định dạng public: X.509
Định dạng private: PKCS#8
Có byte private: true
Spec ký và xác minh: true
X509/PKCS8 ký và xác minh: true
~~~

**Giải thích kết quả:**

- **Ed25519 và Ed448** có thể dùng chung hai interface EdEC; đường cong thực tế nằm trong **NamedParameterSpec**.
- **point.getY().signum() >= 0** là phép kiểm tra y không âm, không in y. Giá trị **isXOdd()** cũng là thành phần quan trọng của điểm, nhưng có thể true hoặc false tùy cặp khóa ngẫu nhiên nên không dùng làm kết quả stdout cố định.
- **getFormat()** trả **X.509** và **PKCS#8** đối với provider được dùng trong phép thử. Một provider khác có thể không cho xuất khóa hoặc không có cùng khả năng chuyển KeySpec.
- **getBytes()** trả Optional có giá trị trên provider phần mềm này. **Không có cam kết mọi provider phải trả true**; mã ứng dụng phải có phương án cho Optional.empty().
- **Spec ký và xác minh: true** chứng tỏ cặp khóa tạo từ EdECPublicKeySpec/EdECPrivateKeySpec có thể làm việc với Signature của đúng đường cong.
- **X509/PKCS8 ký và xác minh: true** chứng tỏ các khóa tạo lại từ định dạng DER tiêu chuẩn có thể ký/xác minh tương ứng.
- **Arrays.fill(...)** cố gắng xóa các **mảng tạm nằm trong tay chương trình**, nhưng **không** xóa được key material đang giữ trong Key objects, KeySpec nội bộ, byte[] do provider tạo hoặc bản sao mà JVM/runtime đã lưu. Đây **không phải** bảo đảm xóa bí mật tuyệt đối khỏi bộ nhớ.

Ví dụ tập trung vào **biểu diễn khóa**. Trong chương trình thật, ưu tiên **giữ private key trong keystore/provider và thực hiện Signature ngay tại đó**, thay vì trích xuất bytes chỉ để tạo lại một bản sao trong heap.

## 8. Bảo mật khi lưu, gửi và xử lý khóa

**Khóa công khai** có thể được phân phối qua SPKI/X.509 DER hoặc định dạng giao thức được đặc tả. Nhưng một public key không tự gắn với danh tính bên gửi: nếu được dùng để xác minh chữ ký từ một bên tin cậy, hệ thống cần **xác thực và phân phối đúng public key**, ví dụ bằng cơ chế trust store, certificate hoặc pinning theo thiết kế.

**Khóa riêng** phải được bảo vệ theo mức độ nhạy cảm. Một số nguyên tắc hiện hành:

1. **Không ghi log** seed, EdECPrivateKey.getBytes(), PKCS#8 DER hay nội dung PEM private.
2. **Không lưu PKCS#8 không mã hóa** trong repository, file cấu hình công khai hoặc cơ sở dữ liệu không được bảo vệ.
3. Dùng **KeyStore** hoặc dịch vụ quản lý khóa/hardware-backed provider khi phù hợp. Chú ý khả năng xuất khóa, thao tác ký và chính sách truy cập khác nhau giữa các provider.
4. Khi cần bảo quản khóa xuất được, dùng cơ chế bảo vệ khóa riêng có xác thực/mã hóa thích hợp, quản lý quyền truy cập và khóa mở giải mã; không tự tạo “mã hóa” bằng Base64 hay XOR.
5. **Xử lý Optional.empty() hoặc getEncoded()==null** một cách hợp lệ. Không ép khóa hardware phải xuất bí mật chỉ để phù hợp với một định dạng JSON tự chế.
6. **Kiểm tra loại thuật toán và tham số** khi nhận khóa từ bên ngoài. Không tự quyết định Ed25519/Ed448 chỉ từ số byte hoặc phần mở rộng file.
7. Không nhầm **seed**, **expanded secret**, **private-key encoding**, **public-key compressed bytes** và **SPKI/PKCS#8** — đó là các biểu diễn có hợp đồng khác nhau.
8. Khi khôi phục khóa từ dữ liệu không tin cậy, để **KeyFactory/Signature/provider** kiểm tra cấu trúc và giá trị; không tắt kiểm tra để “cho qua” khóa không hợp lệ.

Một định dạng dữ liệu còn phải xác định **metadata thuật toán**, **version**, **độ dài** và **cơ chế xác thực nguồn** khi cần; chỉ ghi raw private bytes không mang đủ ngữ cảnh để trao đổi an toàn, ổn định giữa các hệ thống.

## 9. Lỗi thường gặp

1. **Dùng ECPublicKey hoặc ECPoint cho Ed25519.** EdEC có interface và EdECPoint riêng; hai họ biểu diễn không thể thay thế đơn giản.
2. **Nhầm Ed25519 với X25519.** Một bên là EdDSA chữ ký, bên kia thuộc họ XDH thỏa thuận khóa; dùng đúng KeyFactory/Signature/KeyAgreement tương ứng.
3. **Bỏ xOdd khi lưu public point.** Chỉ giữ y chưa mô tả đầy đủ EdECPoint; cần xOdd cùng tham số curve.
4. **Dùng BigInteger.toByteArray() làm raw public-key bytes.** Sai thứ tự byte, độ dài và cách chèn bit dấu theo RFC 8032.
5. **Cho rằng getBytes() luôn trả byte[].** Nó là **Optional<byte[]>** và có thể rỗng khi provider không xuất khóa riêng.
6. **Cho rằng private getEncoded() là raw seed.** Thông thường nó là **PKCS#8 DER**, có cấu trúc; không thể thay trực tiếp vào EdECPrivateKeySpec.
7. **Cho rằng public getEncoded() chỉ có y và xOdd.** Nó thường là **X.509 SubjectPublicKeyInfo**, chứa wrapper thuật toán.
8. **Ghi PKCS#8 DER dưới dạng Base64 và nghĩ đã bảo mật.** Base64 không mã hóa bí mật.
9. **Tạo key với đường cong A nhưng Signature với thuật toán B.** Cần dùng thuật toán khớp tham số và provider; nếu không có thể bị từ chối.
10. **Tự sinh EdECPoint không hợp lệ rồi giả định KeyFactory phải chấp nhận.** Provider có quyền kiểm tra điểm, phạm vi trường và định dạng.
11. **Xóa một bản sao byte[] rồi tuyên bố private key đã bị hủy khỏi RAM.** Có thể còn bản sao trong KeySpec/Key/provider; phải tuân thủ chính sách vòng đời và bảo vệ khóa.
12. **So sánh định dạng bằng kích thước cố định của getEncoded().** SPKI/PKCS#8 có wrapper; các provider có thể biểu diễn khác nhau.
13. **Nghĩ Serializable của Key là phương án lưu trữ khóa mật mã chuẩn.** Cần một định dạng và cơ chế bảo vệ riêng đã được đặc tả; không dùng Java serialization làm mặc định cho trao đổi khóa.
14. **Dùng dữ liệu khóa riêng làm String để dễ truyền tham số.** Chuỗi bất biến khó chủ động xóa, dễ lọt vào log hoặc dump; hạn chế xuất vật liệu khóa khi không cần.
15. **Không xác thực nguồn public key.** Verify(signature) chỉ xác nhận chữ ký so với public key được cung cấp, không tự chứng minh public key ấy thuộc về đúng người hoặc hệ thống mong đợi.

## 10. Câu hỏi tự kiểm tra

**Câu 1:** EdECPublicKey.getPoint() trả kiểu gì?  
**Đáp án:** **EdECPoint**, biểu diễn bởi **BigInteger y** và boolean **xOdd**.

**Câu 2:** EdECPrivateKey.getBytes() trả gì khi provider không muốn xuất private key?  
**Đáp án:** **Optional.empty()**; nên dùng khóa trực tiếp qua provider nếu thao tác mật mã được hỗ trợ.

**Câu 3:** Sự khác nhau giữa EdECPrivateKey.getBytes() và PrivateKey.getEncoded() là gì?  
**Đáp án:** getBytes() đại diện **bit string khóa riêng** nếu được phép xuất; getEncoded() theo provider phần mềm thông thường là cấu trúc **PKCS#8**, có wrapper định dạng và metadata.

**Câu 4:** Dùng lớp nào để khôi phục public DER theo SPKI?  
**Đáp án:** **X509EncodedKeySpec** cùng **KeyFactory** của thuật toán Ed25519 hoặc Ed448 tương ứng.

**Câu 5:** Dùng lớp nào để khôi phục private DER theo PKCS#8?  
**Đáp án:** **PKCS8EncodedKeySpec** cùng **KeyFactory** tương ứng.

**Câu 6:** Khi có y và xOdd nhưng không có curve name, có đủ để mô tả EdDSA public key có ngữ cảnh không?  
**Đáp án:** Chưa. Cần **NamedParameterSpec** đúng đường cong; dùng **EdECPublicKeySpec(params, point)**.

**Câu 7:** Vì sao nhận được chữ ký hợp lệ với một public key chưa chứng minh được danh tính người gửi?  
**Đáp án:** Vì kết quả xác minh chỉ gắn chữ ký với public key đã dùng; hệ thống vẫn phải xác thực nguồn gốc public key theo mô hình tin cậy.

## 11. Ghi nhớ

- **EdECPublicKey = khóa công khai EdDSA**, cung cấp **EdECPoint(xOdd, y)** và tham số curve.
- **EdECPrivateKey = khóa riêng EdDSA**, cung cấp **Optional<byte[]>** cho bit string khi provider cho phép.
- **EdECPublicKeySpec / EdECPrivateKeySpec** dùng để mô tả **thành phần khóa** cho KeyFactory.
- **X509EncodedKeySpec / PKCS8EncodedKeySpec** dùng cho **DER có cấu trúc** khi khóa được xuất ở định dạng tương ứng.
- **Ed25519/Ed448 khác X25519/X448**; không tráo đổi khóa giữa chữ ký và thỏa thuận khóa chỉ bằng đổi nhãn.
- **Không in, lưu trần hoặc tự xử lý raw private key** nếu có thể sử dụng private key trực tiếp trong provider.

## Tài liệu tham khảo chính thức

- Oracle, **EdECPublicKey**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/interfaces/EdECPublicKey.html
- Oracle, **EdECPrivateKey**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html
- Oracle, **EdECPoint**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/EdECPoint.html
- Oracle, **EdECPublicKeySpec**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/EdECPublicKeySpec.html
- Oracle, **EdECPrivateKeySpec**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html
- Oracle, **KeyFactory**, Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyFactory.html
- IETF, **RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)**: https://www.rfc-editor.org/rfc/rfc8032
- IETF, **RFC 8410 — Algorithm Identifiers for Ed25519/Ed448 in X.509**: https://www.rfc-editor.org/rfc/rfc8410
