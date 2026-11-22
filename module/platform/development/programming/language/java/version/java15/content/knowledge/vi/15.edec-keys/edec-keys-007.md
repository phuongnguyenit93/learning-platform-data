# KeyFactory và chuyển đổi key specification của khóa EdEC trong Java 15+

## 1. Mục tiêu: cùng một khóa, nhiều cách biểu diễn

**EdEC** là nhóm kiểu khóa Java dùng cho các đường cong Edwards theo RFC 8032, nổi bật là **Ed25519** và **Ed448** của chữ ký số **EdDSA**. Các API `EdECPublicKey`, `EdECPrivateKey`, `EdECPublicKeySpec`, `EdECPrivateKeySpec` và `EdECPoint` được đưa vào Java 15 cùng hỗ trợ EdDSA (JEP 339) và vẫn có ích trong Java hiện hành.

Khi lập trình ứng dụng ký số, một khóa có thể xuất hiện ở nhiều dạng:

- **Đối tượng khóa**: `PublicKey`/`PrivateKey` do provider JCA quản lý. Đối tượng có thể chứa thông tin được bảo vệ trong phần mềm hoặc chỉ là một tay nắm tới khóa trong HSM.
- **Key specification trong suốt (*transparent*)**: `EdECPublicKeySpec` chứa tham số đường cong và điểm EdEC; `EdECPrivateKeySpec` chứa tham số đường cong và byte vật liệu khóa riêng.
- **Key specification mã hóa (*encoded*)**: `X509EncodedKeySpec` chứa byte DER SubjectPublicKeyInfo cho khóa công khai; `PKCS8EncodedKeySpec` chứa byte mã hóa PKCS#8 cho khóa riêng.
- **Bản mã hóa theo giao thức**: PEM, DER, định dạng khóa của key store, JWK/COSE hoặc dữ liệu thô theo một giao thức cụ thể. Các dạng này không phải tự động hoán đổi cho nhau.

`java.security.KeyFactory` là lớp **chuyển giữa key object và key specification phù hợp**; nó không tạo cặp khóa ngẫu nhiên (`KeyPairGenerator` mới làm), không ký (`Signature` mới làm), cũng không bảo đảm có thể xuất mọi khóa riêng.

### Kết quả cần đạt

Sau bài này, bạn có thể giải thích và thực hiện:

1. `KeyFactory.generatePublic(spec)` / `generatePrivate(spec)`: từ **spec** sang **key object**.
2. `KeyFactory.getKeySpec(key, SpecClass.class)`: từ **key object** sang **spec**.
3. Chọn `EdECPublicKeySpec`/`EdECPrivateKeySpec` hay `X509EncodedKeySpec`/`PKCS8EncodedKeySpec` theo mục đích.
4. Dùng `NamedParameterSpec.ED25519` hoặc `NamedParameterSpec.ED448` để không nhầm đường cong.
5. Xác minh bằng chữ ký thật rằng khóa sau chuyển đổi vẫn dùng được, đồng thời hiểu các giới hạn provider và bảo mật.

## 2. Sơ đồ các đường chuyển đổi trong JCA

```text
                  KeyPairGenerator ("EdDSA")
                       initialize(ED25519/ED448)
                               |
                               v
                    PublicKey / PrivateKey
                           /       \
             getKeySpec(...)       getKeySpec(...)
                         /           \
      +---------------------+   +-----------------------+
      | KeySpec encoded     |   | KeySpec transparent   |
      | X509EncodedKeySpec  |   | EdECPublicKeySpec     |
      | PKCS8EncodedKeySpec |   | EdECPrivateKeySpec    |
      +---------------------+   +-----------------------+
                         \           /
            KeyFactory.generatePublic / generatePrivate
                             |
                             v
                       Key object mới
                             |
                             v
                    Signature.initSign /
                    Signature.initVerify
```

`KeyFactory.getInstance("EdDSA")` yêu cầu một factory cho họ khóa EdDSA. Các tên `"Ed25519"`, `"Ed448"` cũng có ý nghĩa khi provider hỗ trợ; với code tổng quát dùng chung hai curve, `"EdDSA"` và spec kèm `NamedParameterSpec` là cách triển khai rõ ràng.

**Tính hai chiều không có nghĩa là luôn đảo được mọi khóa:** tài liệu `KeyFactory` nói factory có thể đổi giữa các dạng spec **tương thích**. Có khóa provider không thể xuất thành `EdECPrivateKeySpec` hoặc `PKCS8EncodedKeySpec` vì private material được giữ bên trong phần cứng/keystore.

## 3. Những kiểu EdEC quan trọng cần phân biệt

| Kiểu | Vai trò | Dữ liệu cần thiết | Lưu ý |
|---|---|---|---|
| `EdECPublicKey` | Interface của **đối tượng khóa công khai** | `getPoint()`, `getParams()` | Đối tượng khóa, không phải `KeySpec`; đừng nhầm với `ECPublicKey` |
| `EdECPrivateKey` | Interface của **đối tượng khóa riêng** | `getBytes(): Optional<byte[]>`, `getParams()` | Có thể không cho xuất bytes; khóa private cần được bảo vệ |
| `EdECPublicKeySpec` | Spec **trong suốt** của khóa công khai | `NamedParameterSpec` + `EdECPoint` | Mô tả điểm Edwards, không chứa DER SPKI |
| `EdECPrivateKeySpec` | Spec **trong suốt** của khóa riêng | `NamedParameterSpec` + `byte[]` | Vật liệu khóa riêng nhạy cảm trong heap |
| `EdECPoint` | Điểm Edwards | `BigInteger y` + `boolean xOdd` | **Không** phải `java.security.spec.ECPoint` của dạng EC truyền thống |
| `NamedParameterSpec` | Tên miền tham số/đường cong | `ED25519` / `ED448` | Chọn đúng curve khi tạo và đọc spec |
| `X509EncodedKeySpec` | Spec chứa byte khóa công khai **SubjectPublicKeyInfo DER** | `byte[]` | Không phải một chứng chỉ X.509 đầy đủ |
| `PKCS8EncodedKeySpec` | Spec chứa byte khóa riêng theo **PKCS#8** | `byte[]` | Không mặc nhiên mã hóa hoặc bảo vệ bằng mật khẩu |

Các kiểu `EdECPublicKey`/`EdECPrivateKey` **khác** `ECPublicKey`/`ECPrivateKey` theo mô hình đường cong Weierstrass thông thường; `XECPrivateKey`/`XECPublicKey` lại phục vụ **X25519/X448 key agreement**, không phải EdDSA. Không dùng `ECPrivateKeySpec` hay `XECPublicKeySpec` cho một khóa ký Ed25519 chỉ vì các tên đều chứa “EC”.

### Key object và KeySpec khác nhau

`KeySpec` là một **mô tả dữ liệu của khóa**, dùng khi xây dựng/nhập/xuất/chuyển đổi. `PublicKey` và `PrivateKey` là các **đối tượng khóa** mà `Signature.initVerify` hoặc `Signature.initSign` yêu cầu. Không thể đưa một `EdECPrivateKeySpec` trực tiếp vào `Signature.initSign` như thể đó là `PrivateKey`: hãy gọi `KeyFactory.generatePrivate(privateSpec)` trước.

Tương tự, `EdECPublicKeySpec` không chứa một chữ ký và `EdECPoint` không phải một `PublicKey` hoàn chỉnh. Điểm chỉ có ý nghĩa khi đi cùng đúng tham số đường cong, được provider kiểm tra và chuyển thành key object.

## 4. Đường thứ nhất: X.509/SPKI và PKCS#8

Đây thường là lựa chọn thuận tiện khi **lưu hoặc truyền khóa trong một cấu trúc đã chuẩn hóa**.

```java
// Minh họa bên trong phương thức có KeyPair pair và throws GeneralSecurityException.
KeyFactory factory = KeyFactory.getInstance("EdDSA");

byte[] publicDer = pair.getPublic().getEncoded();
byte[] privateDer = pair.getPrivate().getEncoded();

PublicKey restoredPublic = factory.generatePublic(
        new X509EncodedKeySpec(publicDer));
PrivateKey restoredPrivate = factory.generatePrivate(
        new PKCS8EncodedKeySpec(privateDer));
```

Đoạn này là **minh họa**, không phải chương trình độc lập. Nó giả định khóa có thể xuất bằng `getEncoded()`; với HSM hoặc key store bảo vệ khóa riêng, `privateDer` có thể bằng `null` và không được phép xuất. Code sản xuất phải xét trường hợp đó thay vì gọi constructor với `null`.

Trong demo đầy đủ bên dưới, có thể đi theo API đối xứng khác:

```java
X509EncodedKeySpec publicSpec =
        factory.getKeySpec(pair.getPublic(), X509EncodedKeySpec.class);
PKCS8EncodedKeySpec privateSpec =
        factory.getKeySpec(pair.getPrivate(), PKCS8EncodedKeySpec.class);

PublicKey publicKey = factory.generatePublic(publicSpec);
PrivateKey privateKey = factory.generatePrivate(privateSpec);
```

Cách thứ hai cho thấy một phương thức `getKeySpec` có thể yêu cầu **định dạng mã hóa** mà không cần gọi `getEncoded()` thủ công. Cả hai con đường đều đòi hỏi provider cho phép xuất spec đó.

### Vì sao kích thước X.509/PKCS#8 không bằng raw key?

RFC 8410 định nghĩa các **algorithm identifiers (OID)** cho Ed25519/Ed448 trong cấu trúc khóa X.509:

- Ed25519: **1.3.101.112**.
- Ed448: **1.3.101.113**.

Trong cấu trúc `SubjectPublicKeyInfo`, ngoài raw public key còn có metadata thuật toán; `PKCS#8` cũng có phần mô tả thuật toán/cấu trúc bọc private key. Vì vậy `publicDer.length` **không phải luôn bằng 32 hoặc 57**, và `privateDer.length` **không đơn thuần là 32 hoặc 57**.

Trong RFC 8410, các `AlgorithmIdentifier` tương ứng có **parameters phải vắng mặt**, không tự chèn `NULL` khi tự tạo DER. Đừng tự viết cấu trúc ASN.1 bằng các phép nối byte nếu có API thư viện/provider uy tín xử lý.

**PEM chỉ là một cách đóng gói/văn bản hóa** một cấu trúc DER tương thích với header/footer và Base64. `X509EncodedKeySpec`/ `PKCS8EncodedKeySpec` dùng **byte đã giải mã**, không dùng trực tiếp chuỗi PEM có header/footer. `X509EncodedKeySpec` **không phải** cách parse một chứng chỉ `-----BEGIN CERTIFICATE-----`; chứng chỉ dùng `CertificateFactory` và các bước xác minh tin cậy riêng.

## 5. Đường thứ hai: EdECPublicKeySpec và EdECPrivateKeySpec

Spec EdEC trong suốt mô tả cấu trúc khóa theo ý nghĩa Edwards, thường phù hợp khi mã của bạn đã có **curve và điểm public**, hoặc **vật liệu private** dưới dạng được provider chấp nhận.

### 5.1. Công khai: tham số và `EdECPoint`

```java
// Minh họa trong phương thức có KeyFactory factory và PublicKey pub.
EdECPublicKeySpec spec =
        factory.getKeySpec(pub, EdECPublicKeySpec.class);

NamedParameterSpec curve = spec.getParams();
EdECPoint point = spec.getPoint();
boolean oddX = point.isXOdd();
java.math.BigInteger y = point.getY();

PublicKey reconstructed = factory.generatePublic(
        new EdECPublicKeySpec(curve, new EdECPoint(oddX, y)));
```

Đoạn này không độc lập: các biến `factory` và `pub` phải có sẵn; các import `java.security.spec.*`/ `java.security.*` phù hợp. Không cần tính `x` từ `y` trong code minh họa: `EdECPoint` giữ **tọa độ `y` dưới dạng `BigInteger` và bit cho biết tọa độ `x` là lẻ hay chẵn**.

Tại sao không dùng `java.security.spec.ECPoint(x, y)`? Vì đó là biểu diễn điểm cho mô hình **EC truyền thống**, trong khi `EdECPoint` được thiết kế theo cách biểu diễn của RFC 8032 cho đường cong Edwards. Việc dùng sai loại point/spec có thể khiến provider từ chối hoặc không còn mô tả cùng khóa.

**Cảnh báo phạm vi dữ liệu:** constructor `EdECPoint(boolean, BigInteger)` mô tả dữ liệu, không phải lời cam kết rằng mọi `y` đều là điểm hợp lệ. Javadoc cho biết provider có thể từ chối `y` nằm ngoài miền trường `[0, p)`; cũng có thể kiểm tra thêm điều kiện điểm và khóa theo thuật toán. Khi nhập key từ nguồn bên ngoài, phải coi point/curve là dữ liệu **chưa được tin cậy** và để factory/provider thực hiện kiểm tra.

### 5.2. Private: tham số và byte vật liệu khóa

```java
// Minh họa trong phương thức có KeyFactory factory và PrivateKey priv.
EdECPrivateKeySpec spec =
        factory.getKeySpec(priv, EdECPrivateKeySpec.class);
byte[] secretCopy = spec.getBytes();
NamedParameterSpec curve = spec.getParams();
PrivateKey reconstructed = factory.generatePrivate(
        new EdECPrivateKeySpec(curve, secretCopy));
```

`EdECPrivateKeySpec` chứa **byte vật liệu khóa riêng**, không phải public point. Với khóa Ed25519/Ed448 thông dụng tương ứng RFC 8032, raw private key/seed dài **32/57 byte**; code demo kiểm chứng được với SunEC.

`EdECPrivateKeySpec` sao chép `byte[]` khi được khởi tạo và `getBytes()` trả **bản sao mới**. Đó là cơ chế bảo vệ trước sửa đổi mảng ngoài ý muốn, **không** phải mã hóa dữ liệu khóa riêng. Khi đã gọi `getKeySpec(privateKey, EdECPrivateKeySpec.class)`, bạn chủ động yêu cầu **xuất vật liệu bí mật ra heap**; không làm điều đó nếu chỉ cần ký với `PrivateKey` đang được bảo vệ.

Một `EdECPrivateKey` còn có `getBytes(): Optional<byte[]>`. `Optional.empty()` có nghĩa implementation **không sẵn sàng cung cấp byte khóa riêng**; không được diễn giải là khóa trống, khóa không hợp lệ hay mã hóa khác. KeyFactory cũng có thể từ chối cung cấp private spec dù object vẫn được phép dùng để ký.

### 5.3. Raw byte của public point KHÔNG phải BigInteger.toByteArray()

RFC 8032 dùng dạng điểm nén (encoded Edwards point) mà byte của `y` được tổ chức **little-endian**, đồng thời lưu dấu parity của `x` trong bit quy định. `EdECPoint` thì dùng `BigInteger y` và `boolean xOdd`. Trong Java, `BigInteger.toByteArray()` xuất **big-endian, two's complement và có thể có byte dấu**.

Do đó:

- Không truyền `point.getY().toByteArray()` trực tiếp như **raw RFC 8032 public key**.
- Không nối byte tùy ý rồi coi là `X509EncodedKeySpec`: DER SubjectPublicKeyInfo chứa cả metadata ASN.1.
- Không tạo một `EdECPublicKeySpec` chỉ từ `byte[] rawPublic` mà không decode đúng curve, độ dài, byte order và bit parity.
- Khi cần giao tiếp với ứng dụng không dùng Java, nên dùng **SPKI/X.509 DER theo RFC 8410** nếu protocol cho phép, hoặc dùng một decoder RFC 8032 đã được kiểm chứng kỹ cho raw public key.

**Cỡ raw key:** Ed25519: 32 byte public, 32 byte private seed. Ed448: 57 byte public, 57 byte private seed. **Kích thước chữ ký** tương ứng: 64 và 114 byte. Đây là các kích thước ở định dạng thô, không phải kích thước DER/PEM.

## 6. API chính của KeyFactory và ranh giới provider

```java
KeyFactory factory = KeyFactory.getInstance("EdDSA");
```

Các phương thức và ý nghĩa:

| API | Hướng chuyển | Ghi chú |
|---|---|---|
| `generatePublic(KeySpec)` | `KeySpec` → `PublicKey` | Với EdEC, thường nhận `EdECPublicKeySpec` hoặc `X509EncodedKeySpec` khi provider hỗ trợ |
| `generatePrivate(KeySpec)` | `KeySpec` → `PrivateKey` | Với EdEC, thường nhận `EdECPrivateKeySpec` hoặc `PKCS8EncodedKeySpec` khi được phép |
| `getKeySpec(Key, Class<T>)` | `Key` → `T extends KeySpec` | Chọn **kiểu spec cần lấy**; có thể bị từ chối vì khóa/spec/provider không tương thích |
| `translateKey(Key)` | `Key` từ provider/nguồn khác → `Key` do factory đại diện | Chỉ thành công nếu có thể xử lý khóa đầu vào; không bảo đảm vượt cơ chế khóa không xuất được |
| `getInstance(String)` | Chọn `KeyFactory` theo thuật toán | `"EdDSA"`, hoặc biến thể được provider hỗ trợ |
| `getProvider()` | Xác định provider được chọn | Hữu ích khi chẩn đoán tương thích hoặc đáp ứng chính sách provider cụ thể |

**Các ngoại lệ cần biết:**

- `NoSuchAlgorithmException`: không có `KeyFactory` theo tên yêu cầu ở các provider khả dụng.
- `InvalidKeySpecException`: spec sai loại, không hợp lệ hoặc không thể chuyển thành khóa; cũng có thể xảy ra khi `getKeySpec` với khóa không xuất được.
- `InvalidKeyException`: `translateKey` từ chối khóa nguồn không xử lý được.
- `InvalidAlgorithmParameterException`: tham số/curve không phù hợp ở `KeyPairGenerator.initialize` (đây không phải ngoại lệ đặc trưng của `KeyFactory.getKeySpec`).
- `InvalidKeyException` ở `Signature.initSign/initVerify`: khóa object không phù hợp thuật toán/provider của chữ ký.

Đừng bắt mọi lỗi rồi **tự đổi Ed448 về Ed25519**, hoặc dùng khóa khác, vì điều đó phá vỡ chính sách thuật toán của giao thức. Nếu provider không hỗ trợ, hãy báo lỗi cấu hình rõ ràng.

### `getKeySpec` không phải phép chuyển tùy ý giữa các algorithm

`EdEC` dùng Ed25519/Ed448 cho EdDSA. **X25519/X448** là nhóm XEC cho trao đổi khóa (XDH). Sự gần giống tên không biến chúng thành cặp khóa ký dùng được bằng `KeyFactory("EdDSA")`. Cũng không thể dùng `EdECPrivateKeySpec(ED448, bytesEd25519)` để “nâng cấp bảo mật” khóa; curve phải đúng với vật liệu khóa gốc.

**Chuyển đổi spec** giúp biểu diễn lại một khóa tương thích, **không thay đổi thuật toán, không đổi bản chất private key và không sinh khóa có entropy mạnh hơn**.

## 7. Ví dụ Java hoàn chỉnh: hai đường chuyển đổi, hai đường cong

Ví dụ sau chạy với **Java 17+**, sử dụng các API EdEC có từ Java 15. Đây là chương trình độc lập biên dịch/chạy được, **không phụ thuộc thư viện ngoài** trong JDK Oracle/OpenJDK phổ biến có provider SunEC. Nếu môi trường dùng HSM, chế độ FIPS hay JDK tối giản, việc xuất khóa private có thể bị cấm; khi đó ví dụ sẽ không chạy nguyên trạng vì nó cố ý trình diễn thao tác xuất key spec.

Tệp: **`EdECKeySpecDemo.java`** (lưu UTF-8).

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.interfaces.EdECPublicKey;
import java.security.spec.EdECPoint;
import java.security.spec.EdECPrivateKeySpec;
import java.security.spec.EdECPublicKeySpec;
import java.security.spec.NamedParameterSpec;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;

public class EdECKeySpecDemo {
    private static byte[] sign(String algorithm, PrivateKey key, byte[] message)
            throws GeneralSecurityException {
        Signature s = Signature.getInstance(algorithm);
        s.initSign(key);
        s.update(message);
        return s.sign();
    }

    private static boolean verify(String algorithm, PublicKey key,
            byte[] message, byte[] signature) throws GeneralSecurityException {
        Signature s = Signature.getInstance(algorithm);
        s.initVerify(key);
        s.update(message);
        return s.verify(signature);
    }

    private static void check(String algorithm, NamedParameterSpec curve)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
        generator.initialize(curve);
        KeyPair original = generator.generateKeyPair();
        KeyFactory factory = KeyFactory.getInstance("EdDSA");

        X509EncodedKeySpec x509 = factory.getKeySpec(
                original.getPublic(), X509EncodedKeySpec.class);
        PKCS8EncodedKeySpec pkcs8 = factory.getKeySpec(
                original.getPrivate(), PKCS8EncodedKeySpec.class);
        PublicKey derPublic = factory.generatePublic(x509);
        PrivateKey derPrivate = factory.generatePrivate(pkcs8);

        EdECPublicKeySpec publicSpec = factory.getKeySpec(
                original.getPublic(), EdECPublicKeySpec.class);
        EdECPrivateKeySpec privateSpec = factory.getKeySpec(
                original.getPrivate(), EdECPrivateKeySpec.class);
        PublicKey specPublic = factory.generatePublic(publicSpec);
        PrivateKey specPrivate = factory.generatePrivate(privateSpec);

        EdECPoint point = publicSpec.getPoint();
        EdECPublicKeySpec manualPublic = new EdECPublicKeySpec(
                curve, new EdECPoint(point.isXOdd(), point.getY()));
        EdECPrivateKeySpec manualPrivate = new EdECPrivateKeySpec(
                curve, privateSpec.getBytes());
        PublicKey reconstructedPublic = factory.generatePublic(manualPublic);
        PrivateKey reconstructedPrivate = factory.generatePrivate(manualPrivate);

        byte[] message = "Đơn hàng: 42".getBytes(StandardCharsets.UTF_8);
        byte[] tampered = "Đơn hàng: 43".getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(algorithm, original.getPrivate(), message);

        byte[] firstCopy = privateSpec.getBytes();
        byte[] secondCopy = privateSpec.getBytes();
        boolean defensiveCopies = firstCopy != secondCopy
                && Arrays.equals(firstCopy, secondCopy);
        Arrays.fill(firstCopy, (byte) 0);
        defensiveCopies &= Arrays.equals(secondCopy, privateSpec.getBytes());
        Arrays.fill(secondCopy, (byte) 0);

        EdECPoint restoredPoint = ((EdECPublicKey) specPublic).getPoint();
        boolean samePoint = point.isXOdd() == restoredPoint.isXOdd()
                && point.getY().equals(restoredPoint.getY());

        System.out.println(algorithm + ": curve=" + publicSpec.getParams().getName());
        System.out.println(algorithm + ": privateBytes=" + privateSpec.getBytes().length);
        System.out.println(algorithm + ": formats="
                + original.getPublic().getFormat() + "/"
                + original.getPrivate().getFormat());
        System.out.println(algorithm + ": derRoundTrip="
                + verify(algorithm, derPublic, message, sign(algorithm, derPrivate, message)));
        System.out.println(algorithm + ": specRoundTrip="
                + verify(algorithm, specPublic, message, sign(algorithm, specPrivate, message)));
        System.out.println(algorithm + ": manualRoundTrip="
                + verify(algorithm, reconstructedPublic, message,
                        sign(algorithm, reconstructedPrivate, message)));
        System.out.println(algorithm + ": pointPreserved=" + samePoint);
        System.out.println(algorithm + ": deterministic="
                + Arrays.equals(signature, sign(algorithm, specPrivate, message)));
        System.out.println(algorithm + ": changedMessage="
                + verify(algorithm, original.getPublic(), tampered, signature));
        System.out.println(algorithm + ": defensiveCopy=" + defensiveCopies);
        System.out.println(algorithm + ": signatureBytes=" + signature.length);
    }

    public static void main(String[] args) throws GeneralSecurityException {
        check("Ed25519", NamedParameterSpec.ED25519);
        check("Ed448", NamedParameterSpec.ED448);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 EdECKeySpecDemo.java
java -cp . EdECKeySpecDemo
```

**Stdout chính xác đã kiểm thử** (không in byte khóa/chữ ký ngẫu nhiên):

```text
Ed25519: curve=Ed25519
Ed25519: privateBytes=32
Ed25519: formats=X.509/PKCS#8
Ed25519: derRoundTrip=true
Ed25519: specRoundTrip=true
Ed25519: manualRoundTrip=true
Ed25519: pointPreserved=true
Ed25519: deterministic=true
Ed25519: changedMessage=false
Ed25519: defensiveCopy=true
Ed25519: signatureBytes=64
Ed448: curve=Ed448
Ed448: privateBytes=57
Ed448: formats=X.509/PKCS#8
Ed448: derRoundTrip=true
Ed448: specRoundTrip=true
Ed448: manualRoundTrip=true
Ed448: pointPreserved=true
Ed448: deterministic=true
Ed448: changedMessage=false
Ed448: defensiveCopy=true
Ed448: signatureBytes=114
```

### Phân tích từng nhóm kết quả

**`curve=...` và `privateBytes=...`:** spec mang `NamedParameterSpec` đúng đường cong, và byte private Ed25519/Ed448 có độ dài thô 32/57 trong ví dụ SunEC. Không suy diễn rằng `pair.getPrivate().getEncoded()` cũng dài đúng như vậy; cái sau là PKCS#8.

**`formats=X.509/PKCS#8`:** provider của ví dụ cho phép mã hóa khóa; các giá trị này do `getFormat()` trả. Với một private key không xuất được, `getFormat()` hoặc `getEncoded()` có thể là `null`, và `getKeySpec(PrivateKey, PKCS8EncodedKeySpec.class)` có thể không thành công.

**`derRoundTrip=true`:** khóa từ `X509EncodedKeySpec` và `PKCS8EncodedKeySpec` có thể ký/xác minh đúng với thông điệp.

**`specRoundTrip=true`:** chuyển sang **spec EdEC trong suốt** rồi tái tạo khóa vẫn giữ quan hệ public/private cần thiết để kiểm tra chữ ký.

**`manualRoundTrip=true`:** tự dựng các đối tượng spec từ **curve + điểm public** hoặc **curve + copy private bytes** cũng tái tạo được cặp khóa có hành vi tương đương. Đây chỉ là tái dựng từ **vật liệu đã biết đúng**, không phải sinh khóa mới độc lập.

**`pointPreserved=true`:** so sánh `y` và parity của `x` cho thấy thông tin điểm trong spec được giữ khi tái tạo public key. Không in `y` để làm expected output vì cặp khóa mỗi lần chạy khác nhau.

**`deterministic=true`:** pure Ed25519/Ed448 khi ký cùng thông điệp bằng cùng vật liệu private tạo chữ ký giống nhau; không phải chứng cứ rằng signature bytes cố định qua các lần **sinh khóa khác nhau**. Các biến thể EdDSA có mode context/prehash cần được thống nhất riêng nếu sử dụng.

**`changedMessage=false`:** dù chỉ đổi ký tự `42` thành `43`, chữ ký của thông điệp cũ không còn hợp lệ. Điều được ký là **byte UTF-8**, không phải ý nghĩa của chuỗi.

**`defensiveCopy=true`:** `EdECPrivateKeySpec.getBytes()` trả các mảng khác nhau và sửa một mảng không sửa nội dung gốc của spec. **Không đồng nghĩa dữ liệu private đã bị xóa khỏi bộ nhớ:** `privateSpec`, key object và các mảng khác vẫn chứa thông tin bí mật. `Arrays.fill` chỉ giảm thời gian tồn tại của **các bản sao do ta trực tiếp kiểm soát**, không bảo đảm mọi bản sao trong heap/JIT đã bị xóa.

**`signatureBytes=64/114`:** chữ ký thuần Ed25519 dài 64 byte, Ed448 dài 114 byte; con số này độc lập với kích thước `PKCS#8` và không phải byte public key.

## 8. `getKeySpec` so với thao tác trực tiếp trên EdECKey

Nếu đối tượng khóa hỗ trợ các interface EdEC, có thể đọc các trường chuyên biệt:

```java
// Minh họa khi pair là KeyPair được provider EdDSA hỗ trợ:
java.security.interfaces.EdECPublicKey pub =
        (java.security.interfaces.EdECPublicKey) pair.getPublic();
java.security.spec.EdECPoint point = pub.getPoint();

java.security.interfaces.EdECPrivateKey priv =
        (java.security.interfaces.EdECPrivateKey) pair.getPrivate();
java.util.Optional<byte[]> maybeSecret = priv.getBytes();
```

Cách này thường giúp quan sát trực tiếp cấu trúc EdEC, nhưng **không bảo đảm mọi provider** sẽ trả key object triển khai đúng interface Java đó, đặc biệt với phần cứng/remote HSM. Cũng không nên gọi `maybeSecret.get()` khi `Optional` rỗng.

`KeyFactory.getKeySpec` có lợi khi bạn cần **một định dạng spec đã chọn** hoặc muốn chuyển qua một provider hiểu đặc tả đó. Nếu provider không cho xuất secret, hãy thực hiện `Signature.initSign(privateKey)` trực tiếp qua provider hỗ trợ, không cố “vượt” bảo vệ bằng reflection, `getEncoded()`, `getBytes()` hoặc chuyển provider tùy tiện.

`KeyFactory.translateKey(key)` là API phù hợp khi đã có `Key` của một nguồn/provider và muốn có đối tượng tương đương cho provider của factory **nếu hỗ trợ**. Nó có thể ném `InvalidKeyException`, và không tự chuyển đổi khóa không xuất được thành khóa có byte private. Khi interoperability quan trọng, hãy thử trên đúng provider và loại khóa được dùng trong môi trường thật.

## 9. Cách chuyển spec khi nhận dữ liệu từ bên ngoài

### 9.1. Nhận public key theo DER SPKI

Một API nhận dữ liệu public key dạng SPKI có thể:

```java
// Đoạn minh họa trong method có byte[] spkiDer và throws GeneralSecurityException.
KeyFactory factory = KeyFactory.getInstance("EdDSA");
PublicKey publicKey = factory.generatePublic(
        new X509EncodedKeySpec(spkiDer));
```

Sau đó nên ràng buộc thuật toán/curve theo chính sách giao thức và dùng `Signature.initVerify` với đúng key. `KeyFactory` chỉ parse và tạo đối tượng khóa; **nó không xác thực ai sở hữu khóa**. Public key cần đến từ chứng chỉ/registry/nguồn được xác minh danh tính theo cơ chế trust của ứng dụng.

Nếu nhận **certificate X.509**, không truyền toàn bộ DER certificate vào `X509EncodedKeySpec`. Hãy dùng `CertificateFactory` để đọc chứng chỉ và thực hiện **xác minh chuỗi tin cậy/quyền sử dụng** theo hợp đồng hệ thống; public key lấy từ chứng chỉ mới là key object dùng cho `Signature.initVerify`.

### 9.2. Nhận private key theo DER PKCS#8

```java
// Đoạn minh họa trong method có byte[] pkcs8Der và throws GeneralSecurityException.
KeyFactory factory = KeyFactory.getInstance("EdDSA");
PrivateKey privateKey = factory.generatePrivate(
        new PKCS8EncodedKeySpec(pkcs8Der));
```

Code trên giả định `pkcs8Der` đã được cấp phép/giải mã và lưu trữ an toàn. `PKCS8EncodedKeySpec` nhận **cấu trúc private key chưa được mã hóa ở định dạng phù hợp**, không tự giải mật khẩu cho PEM encrypted/PKCS#8 encrypted. Đừng lưu nguyên mảng `pkcs8Der` hoặc private key trong log, crash report hay telemetry.

### 9.3. Nhận point hoặc raw private seed từ giao thức riêng

Nếu protocol gửi **`NamedParameterSpec` + `EdECPoint`** đã được decode đúng, bạn có thể dùng `new EdECPublicKeySpec(params, point)` và `generatePublic`. Nếu protocol gửi **`NamedParameterSpec` + private bytes** thuộc đúng dạng mà provider EdEC hiểu, dùng `EdECPrivateKeySpec` và `generatePrivate`.

Không trộn **curve** hoặc tự đoán curve chỉ từ độ dài bytes: byte lengths trùng lặp và định dạng có thể khác giữa raw key/DER/PEM. Một spec Ed25519 tạo từ raw private Ed448 không hợp lệ; nếu provider bác bỏ, phải báo lỗi thay vì tự fallback.

**Lưu ý:** không phải mọi byte array dài 32/57 đều tạo một public key hợp lệ; public point cần được giải mã đúng (little-endian y, parity x) và kiểm tra theo curve. Không nên tự xây dựng parser khóa trừ khi có yêu cầu protocol và test vectors chuẩn.

## 10. Định dạng/curve phải thống nhất khi ký và xác minh

Bài toán không kết thúc tại `generatePublic` trả object mà không ném lỗi. **Bảo toàn ngữ nghĩa** cần được kiểm chứng qua hành vi:

- Có thể tạo chữ ký với `Signature.getInstance("Ed25519")` trên **Ed25519 private key** sau chuyển.
- Có thể xác minh bằng **Ed25519 public key** sau chuyển.
- Dữ liệu thay đổi phải làm `verify` trả false (hoặc báo lỗi rõ khi input chữ ký không hợp lệ).
- Với Ed448 phải dùng **Ed448 ở cả hai phía** và mode/context tương ứng nếu giao thức quy định.
- Nếu JCA provider khác nhau giữa máy gửi và nhận, hai phía phải thống nhất **định dạng key, tên curve, signature algorithm, thông điệp byte, prehash/context**.

**Ed25519 ≠ Ed448** và **EdDSA ≠ XDH**. Không dùng một giá trị string tự chọn từ payload không tin cậy để quyết định toàn bộ thuật toán mà không có allowlist: cần chống tình huống sai loại khóa, downgrade hoặc nhầm trách nhiệm thuật toán.

### Thuật toán EdDSA và context/prehash

RFC 8032 có các biến thể pure/context/prehash; `EdDSAParameterSpec` trong Java hỗ trợ các tham số liên quan. Việc chuyển **key specification** không tự chuyển đổi chế độ ký; sử dụng cùng một curve vẫn có thể verify thất bại nếu bên ký và bên nhận chọn **mode/context khác nhau**.

Nếu đang dùng pure Ed25519/Ed448 theo ví dụ, đừng tự dùng `MessageDigest` để hash message rồi coi đó là **Ed25519ph/Ed448ph**: prehash mode có ngữ nghĩa xác định của RFC, không chỉ là ký một digest tùy ý.

## 11. Lỗi phổ biến và cách chẩn đoán

| Vấn đề quan sát | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `NoSuchAlgorithmException` khi `KeyFactory.getInstance("EdDSA")` | Runtime không có provider hỗ trợ | Kiểm tra JDK/provider/image jlink/HSM và thuật toán được phép; không tự chuyển sang algorithm khác |
| `InvalidKeySpecException` khi `generatePublic` | Spec public không đúng định dạng hoặc điểm/curve không hợp lệ | Kiểm tra DER SPKI, OID và `EdECPoint` theo RFC 8032, không tự giải mã bằng big-endian |
| `InvalidKeySpecException` khi `generatePrivate` | Private spec/PKCS#8 sai, không hợp lệ hoặc bị provider từ chối | Kiểm tra đúng loại spec, curve, byte encoding và quyền nhập key |
| `InvalidKeySpecException` khi `getKeySpec` | Provider không thể xuất spec được yêu cầu hoặc key không tương thích | Thử spec khác **nếu được phép**; ưu tiên ký trong provider thay vì export private |
| `EdECPrivateKey.getBytes()` trả `Optional.empty()` | Implementation không công bố private bytes | Xử lý đường không xuất được, không gọi `get()` không kiểm tra |
| `getEncoded()` hoặc `getFormat()` là `null` | Key object không có primary encoding để xuất | Không giả định PKCS#8 luôn sẵn; thiết kế API theo key handle/provider |
| `ClassCastException` khi cast sang `EdECPrivateKey` | Key object không triển khai interface đó | Dùng API `PrivateKey`/provider hoặc đường `KeyFactory` phù hợp, không ép kiểu vô điều kiện |
| `InvalidKeyException` khi `translateKey` | Provider không xử lý được nguồn khóa | Kiểm tra khả năng tương tác hai provider, tính xuất được của khóa |
| `Signature.initSign` báo khóa không hợp lệ | Dùng private key sai curve/algorithm/provider | Ràng buộc `Ed25519` hoặc `Ed448` đúng policy |
| Chữ ký không verify dù chuyển đổi không lỗi | Sai key pair, bytes thông điệp, mode/context hoặc public key bị thay | Xác nhận byte chính xác, key ID, algorithm và signed payload |
| Public key 44 byte thay vì 32 | Đang cầm **SPKI DER** (ví dụ Ed25519), không phải raw public | Phân biệt `X509EncodedKeySpec` với `EdECPublicKeySpec` và RFC 8032 |
| Private key 48 byte thay vì 32 | Đang cầm **PKCS#8 DER** (ví dụ Ed25519), không phải private seed | Không so sánh kích thước DER với raw seed |
| `BigInteger.toByteArray()` làm verify lỗi | Big-endian/two's complement khác raw Edwards encoding little-endian | Dùng parser/encoder RFC 8032 đã kiểm chứng hoặc SPKI DER |
| `InvalidAlgorithmParameterException` lúc sinh khóa | Named parameter không tương thích generator/provider | `NamedParameterSpec.ED25519/ED448` và provider hỗ trợ |
| `getKeySpec(..., EdECPrivateKeySpec.class)` thất bại với HSM | Khóa private bị bảo vệ chống xuất | Ký bằng key handle, tuyệt đối không tìm cách bỏ bảo vệ |

**Không tạo một private spec từ mảng byte “tùy ý” chỉ để xem có ký được không.** Việc provider chấp nhận một cấu trúc key object không tự chứng minh nguồn gốc/key ownership/trust phù hợp với nghiệp vụ. Các exception cần được báo có ngữ cảnh và không làm lộ bytes của private key.

## 12. Bảo mật vật liệu khóa và vòng đời

### 12.1. Khi nào nên xuất private key?

**Chỉ khi thật sự cần** cho một chức năng đã được phê duyệt (ví dụ migration khóa giữa các hệ thống có chính sách bảo vệ tương đương). Nếu ứng dụng chỉ cần ký, giữ `PrivateKey` dưới dạng object do KeyStore/HSM/KMS quản lý và gọi provider `Signature` là cách thường an toàn hơn. Không xuất chỉ để biến đổi sang một `EdECPrivateKeySpec` rồi tạo lại key object mà không có lý do.

### 12.2. Tránh những lỗi vật liệu khóa trong heap

- Không log `privateSpec.getBytes()`, `privateKey.getEncoded()`, chuỗi Base64 của private key hay PEM private key.
- Hạn chế thời gian tồn tại của các mảng byte private ngoài provider; dùng `Arrays.fill(buffer, (byte) 0)` sau khi hoàn tất nếu đã chủ động tạo mảng sao, nhưng hiểu rằng **JVM vẫn có thể có các bản sao khác**. Nó không phải giải pháp xóa bí mật tuyệt đối.
- `EdECPrivateKeySpec` sao chép dữ liệu để bảo vệ khỏi sửa đổi, không giúp loại bỏ mọi bản sao; mọi `getBytes()` mới tạo thêm một byte array chứa secret.
- `PKCS8EncodedKeySpec` là **container**, không đồng nghĩa private key đã được mã hóa ở trạng thái lưu. Nếu phải lưu, cần format/encryption/access control và quy trình rotation thích hợp.
- Public key không phải bí mật, nhưng phải được **xác thực nguồn gốc**. Kẻ tấn công thay public key trong kho verify có thể khiến hệ thống chấp nhận chữ ký của kẻ tấn công.

### 12.3. Chọn provider và tuân thủ chính sách

Không nên chỉ kiểm tra tên `"EdDSA"` rồi khẳng định môi trường đã đáp ứng FIPS/compliance hoặc yêu cầu HSM. Cần xác định **provider/module được phê duyệt**, thuật toán/độ dài/mode được cho phép, vòng đời khóa, quyền export/import và khả năng tương tác trên **môi trường triển khai thật**.

Một provider có thể hỗ trợ Ed25519 mà không hỗ trợ Ed448, hoặc hỗ trợ ký bằng key handle nhưng không cho xuất raw private spec. Trường hợp đó là **thiết kế quyền và khả năng provider**, không phải lý do để hạ chuẩn bảo vệ bí mật.

## 13. Kiểm thử chức năng và tương thích

Checklist trước khi phát hành:

1. **Tạo khóa** đúng curve `ED25519` và/hoặc `ED448`; đảm bảo provider có support.
2. **DER round-trip**: `KeyFactory.getKeySpec`/ `generatePublic`/ `generatePrivate` bằng `X509EncodedKeySpec` và `PKCS8EncodedKeySpec` khi export được.
3. **Transparent round-trip**: `EdECPublicKeySpec` và `EdECPrivateKeySpec` từ khóa do provider tạo.
4. **Curve metadata**: `getParams().getName()` đúng curve và không có fallback âm thầm.
5. **Public point**: `y` và `isXOdd()` giữ nguyên sau chuyển đổi; không dựa vào một chuỗi `toString()` của point.
6. **Chữ ký**: ký bằng private key sau chuyển, verify bằng public key tương ứng; đổi byte message → không hợp lệ.
7. **Định dạng khóa**: phân biệt raw 32/57 bytes với SPKI/PKCS#8, kiểm thử import/export liên provider/protocol nếu có.
8. **Lỗi**: test nhận dạng sai spec, sai curve, byte input không hợp lệ, key không xuất được và những lỗi provider.
9. **Bảo mật**: không log private bytes, có policy bảo vệ/rotation và trusted public key distribution.
10. **Tương thích môi trường**: CI với JDK/provider thực tế, kiểm tra HSM/key store và phiên bản protocol; không dựa vào kết quả một máy dev.

Khi test lỗi nhập khóa không hợp lệ, không nên hard-code “chắc chắn ném exception loại X tại thời điểm Y” cho mọi provider: một số provider kiểm tra point ngay trong `generatePublic`, số khác có thể kiểm tra muộn hơn. Điều bất biến cần yêu cầu là **khóa không hợp lệ không được được chấp nhận để xác minh/ký theo sai hợp đồng**, và lỗi phải được xử lý an toàn.

## 14. Quy tắc chọn nhanh

| Bạn đang có | Bạn muốn | Dùng |
|---|---|---|
| `X509EncodedKeySpec` chứa DER SPKI hợp lệ | `PublicKey` để verify | `KeyFactory("EdDSA").generatePublic(spec)` |
| `PKCS8EncodedKeySpec` chứa DER private hợp lệ/được phép nhập | `PrivateKey` để sign | `KeyFactory("EdDSA").generatePrivate(spec)` |
| `PublicKey` có thể xuất | Spec public theo curve/point | `getKeySpec(key, EdECPublicKeySpec.class)` |
| `PrivateKey` được phép xuất vật liệu | Spec private theo curve/bytes | `getKeySpec(key, EdECPrivateKeySpec.class)` |
| `PublicKey` và muốn lưu/truyền chuẩn DER | `X509EncodedKeySpec` | `getKeySpec(key, X509EncodedKeySpec.class)` |
| `PrivateKey` **xuất được** và nghiệp vụ cho phép lưu/di chuyển | `PKCS8EncodedKeySpec` | `getKeySpec(key, PKCS8EncodedKeySpec.class)` + bảo vệ secret |
| `EdECPoint` và `NamedParameterSpec` đã parse/kiểm tra đúng | Public key object | `new EdECPublicKeySpec(params, point)` rồi `generatePublic` |
| Byte private material và curve đúng, được phép import | Private key object | `new EdECPrivateKeySpec(params, bytes)` rồi `generatePrivate` |
| Key của provider khác | Key trong factory provider đích | `translateKey(key)` **nếu provider chấp nhận** |
| Key private chỉ sống trong HSM/keystore | Tạo chữ ký | **Không export**; dùng `Signature.initSign(privateKey)` qua provider phù hợp |

**Kết luận:** `KeyFactory` là chiếc cầu giữa **đối tượng khóa JCA** và **biểu diễn KeySpec tương thích**, chứ không phải phép chuyển đổi mật mã tùy ý. Với EdEC, cần luôn mang theo đúng `NamedParameterSpec`, phân biệt `EdECPoint`/`EdECPrivateKeySpec` với X.509/PKCS#8, và thử lại **hành vi ký/xác minh** sau chuyển đổi. Khi chạm tới vật liệu private, việc **được phép xuất hay không** quan trọng không kém việc API có biên dịch được hay không.

### Tài liệu chuẩn còn áp dụng

- [Oracle Java SE 26 — `KeyFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyFactory.html).
- [Oracle Java SE 26 — `EdECPublicKeySpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/EdECPublicKeySpec.html), [`EdECPrivateKeySpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/EdECPrivateKeySpec.html), [`EdECPoint`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/EdECPoint.html).
- [Oracle Java SE 26 — `EdECPublicKey`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/interfaces/EdECPublicKey.html), [`EdECPrivateKey`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/interfaces/EdECPrivateKey.html).
- [Oracle Java SE 26 — `X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html), [`PKCS8EncodedKeySpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html).
- [RFC 8032 — Edwards-Curve Digital Signature Algorithm](https://www.rfc-editor.org/rfc/rfc8032.html); [RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, and X448](https://www.rfc-editor.org/rfc/rfc8410.html).
- [JEP 339 — EdDSA](https://openjdk.org/jeps/339): tính năng đưa vào Java 15 và vẫn được hỗ trợ hiện nay.
