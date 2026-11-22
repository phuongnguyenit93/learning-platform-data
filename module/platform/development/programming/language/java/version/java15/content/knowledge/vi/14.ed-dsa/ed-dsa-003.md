# Ed25519, Ed448 và lựa chọn thuật toán EdDSA trong Java 15+

## 1. EdDSA giải quyết bài toán gì?

**EdDSA (Edwards-curve Digital Signature Algorithm)** là họ thuật toán **chữ ký số khóa công khai** được mô tả trong RFC 8032. Java 15 đưa EdDSA vào các API JCA/JCE chuẩn (JEP 339); các thuật toán **Ed25519** và **Ed448** vẫn là lựa chọn đang được hỗ trợ trong Java hiện hành.

Chữ ký số dùng để kiểm tra hai điều kiện: (1) dữ liệu được ký bằng **khóa riêng** tương ứng với khóa công khai đã biết; (2) nội dung dữ liệu **không bị thay đổi** so với lúc ký. Nó **không mã hóa/giấu nội dung** và không tự chứng minh người sở hữu khóa là ai. Ứng dụng phải có cách đáng tin để phân phối và ràng buộc **khóa công khai với danh tính**.

Ví dụ luồng làm việc:

```text
Bên ký:
  PrivateKey (Ed25519 hoặc Ed448)
  + bytes thông điệp đúng định dạng
  └── Signature.initSign → update → sign
                             |
                             v
                       bytes chữ ký

Bên kiểm tra:
  PublicKey tin cậy của cùng thuật toán
  + bytes thông điệp chính xác
  + bytes chữ ký
  └── Signature.initVerify → update → verify
                             |
                             v
                       true / false
```

**Phân biệt:** Ed25519/Ed448 là thuật toán **ký/xác minh**. X25519/X448 có tên gần giống nhưng là thuật toán **thỏa thuận khóa** (XDH), dùng cho mục tiêu khác. Không tráo đổi khóa EdDSA với khóa XDH chỉ vì cùng họ đường cong.

## 2. Ed25519 và Ed448 khác nhau ở đâu?

Hai biến thể cùng dựa trên cấu trúc chữ ký EdDSA nhưng dùng các tham số và hàm băm nội bộ khác nhau. RFC 8032 đưa ra mức an toàn ước tính **trước máy tính lượng tử quy mô lớn** khoảng **128 bit đối với Ed25519** và **224 bit đối với Ed448**.

| Tiêu chí | Ed25519 | Ed448 |
|---|---|---|
| Mức an toàn cổ điển danh nghĩa | Khoảng **128 bit** | Khoảng **224 bit** |
| Kích thước khóa công khai **thô** theo RFC 8032 | **32 byte** | **57 byte** |
| Kích thước seed khóa riêng thô theo RFC 8032 | **32 byte** | **57 byte** |
| Chữ ký thuần (*pure variant*) | **64 byte** | **114 byte** |
| Hàm băm nội bộ theo RFC 8032 | SHA-512 | SHAKE256 |
| Kích thước và tốc độ | Thường nhỏ hơn, nhanh hơn | Chữ ký lớn hơn và thường tốn chi phí tính toán hơn |
| Ưu tiên thường gặp | Dịch vụ có yêu cầu chuẩn hiện đại, ưu tiên hiệu năng/tương thích | Dịch vụ có yêu cầu **mức an toàn cổ điển cao hơn** và mọi bên đều hỗ trợ |
| Hậu lượng tử | **Không** | **Không** |

Cần đọc bảng chính xác: con số **25519** hoặc **448** trong tên đường cong **không** phải mức an toàn 255 hoặc 448 bit; “128/224 bit” là ước lượng an toàn mật mã cổ điển theo RFC. Cả Ed25519 và Ed448 đều có thể bị phá bởi một máy tính lượng tử đủ lớn; nếu mô hình đe dọa đòi hỏi chữ ký hậu lượng tử, phải xét **một họ chữ ký hậu lượng tử được chuẩn hóa** và mức hỗ trợ thực tế của hệ thống, không chỉ chọn Ed448.

**Kích thước thô khác kích thước khóa đã mã hóa.** `PublicKey.getEncoded()` trong Java thường tạo **SubjectPublicKeyInfo (X.509)**, có metadata thuật toán, vì vậy mảng byte thường dài **hơn 32/57 byte**. `PrivateKey.getEncoded()` thường là cấu trúc **PKCS#8**, không đơn thuần là seed 32/57 byte. Đừng lấy độ dài của X.509/PKCS#8 rồi coi đó là sai đặc tả RFC 8032.

## 3. Chọn thuật toán theo tiêu chí thực tế

### 3.1. Khi nào ưu tiên Ed25519?

**Ed25519 là lựa chọn đầu tiên hợp lý** trong nhiều hệ thống mới khi:

- Hợp đồng giao thức, đối tác, HSM, chứng chỉ và các thư viện đều hỗ trợ Ed25519.
- Mức an toàn cổ điển xấp xỉ 128 bit đáp ứng thời hạn bảo vệ và chính sách bảo mật.
- Chữ ký nhỏ gọn và chi phí ký/xác minh quan trọng với throughput, latency hoặc payload nhỏ.
- Cần trao đổi chữ ký với hệ sinh thái đã chuẩn hóa Ed25519, ví dụ một định dạng/protocol cụ thể có khai báo thuật toán rõ ràng.

Điểm cộng **không có nghĩa** mọi giao thức đều tự hỗ trợ Ed25519. Phải kiểm tra **đúng phiên bản chuẩn và profile** của TLS, SSH, chứng chỉ, JWT/JOSE, COSE hoặc API đối tác. Một thư viện có Java `Signature` Ed25519 không đồng nghĩa hệ thống token hoặc chứng chỉ phía đối tác có thể sử dụng nó.

### 3.2. Khi nào chọn Ed448?

Xét **Ed448** khi:

- Chính sách nghiệp vụ/tiêu chuẩn kỹ thuật yêu cầu mức an toàn cổ điển cao hơn Ed25519.
- Các hệ thống ký, xác minh, key store, HSM, protocol/certificate profile đều hỗ trợ Ed448.
- Ngân sách băng thông/CPU có thể chấp nhận chữ ký 114 byte cùng chi phí xử lý cao hơn.

**Không** chọn Ed448 chỉ vì “448 > 25519” — đây không phải phép so sánh có nghĩa. Không chọn Ed448 mà chưa kiểm chứng interoperability; độ mạnh lý thuyết không giúp ích nếu hệ thống phải dùng giải pháp chuyển đổi khóa hoặc thư viện không hỗ trợ chuẩn.

### 3.3. Tiêu chí ra quyết định

| Câu hỏi | Hành động |
|---|---|
| Có yêu cầu tối thiểu của giao thức hoặc tiêu chuẩn không? | Chọn thuật toán **được cho phép**, đúng profile và chính sách phê duyệt |
| Bên nhận và hạ tầng quản lý khóa có hỗ trợ Ed448 không? | Nếu không, ưu tiên Ed25519 hoặc giải pháp khác được giao thức cho phép |
| Mức an toàn cổ điển khoảng 128 bit đã đủ chưa? | Nếu đủ, Ed25519 thường cân bằng kích thước và hiệu năng tốt |
| Mục tiêu là chữ ký số hay trao đổi khóa? | **Ký**: Ed25519/Ed448; **thỏa thuận khóa**: X25519/X448 theo protocol |
| Có yêu cầu chống đối thủ lượng tử không? | Cả hai đều không giải quyết; đánh giá chữ ký hậu lượng tử/hybrid theo hệ sinh thái |
| Có bị ràng buộc môi trường FIPS/compliance không? | Kiểm chứng thuật toán, **provider/module được thẩm định**, cấu hình và quy định áp dụng; tên thuật toán không tự bảo đảm tuân thủ |

Không có thuật toán “tốt nhất mọi nơi”. Quyết định đúng là **mức an toàn đủ + chuẩn trao đổi tương thích + nhà cung cấp có thể triển khai/vận hành đúng**.

## 4. Java JCA: tên thuật toán và tham số chọn đường cong

Trong Java, ba tên chuẩn quan trọng là:

- `"EdDSA"`: tên thuật toán tổng quát thuộc họ EdDSA.
- `"Ed25519"`: chọn cụ thể biến thể đường cong Ed25519.
- `"Ed448"`: chọn cụ thể biến thể đường cong Ed448.

Ví dụ yêu cầu một bộ tạo cặp khóa đúng curve:

```java
// Đoạn minh họa đặt trong method có imports phù hợp.
KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(NamedParameterSpec.ED25519);
KeyPair pair = generator.generateKeyPair();
```

Đổi thành `NamedParameterSpec.ED448` sẽ yêu cầu đường cong Ed448. Có thể dùng trực tiếp `KeyPairGenerator.getInstance("Ed25519")` hoặc `"Ed448"` nếu provider hỗ trợ. Với code cần kết quả dự đoán được, nên **chọn tham số cụ thể**, thay vì dựa vào mặc định của một `KeyPairGenerator` tổng quát.

Để ký, ví dụ lựa chọn rõ ràng:

```java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(pair.getPrivate());
signer.update(messageBytes);
byte[] signature = signer.sign();
```

`messageBytes` là biến `byte[]` được chuẩn bị trước; ví dụ đầy đủ ở phần 6. Nếu `pair` được tạo bằng `ED448`, hãy dùng `Signature.getInstance("Ed448")` và đối tác phải xác minh theo cùng thuật toán. Không viết sai tên kiểu `"SHA256withEd25519"` rồi nghĩ rằng Java sẽ tự dùng Ed25519; tên thuật toán chuẩn EdDSA đã xác định cách băm nội bộ.

### Provider không phải điều hiển nhiên trên mọi Java runtime

Oracle/OpenJDK cung cấp **SunEC** hỗ trợ `KeyPairGenerator`, `KeyFactory`, `Signature` cho Ed25519/Ed448/EdDSA. Nhưng JCA dùng các **security provider** có thể khác giữa các bản phân phối, image jlink tối giản, môi trường FIPS/HSM hoặc nhà cung cấp bên thứ ba. Vì vậy, luôn xử lý `NoSuchAlgorithmException`, `InvalidKeyException`, `InvalidAlgorithmParameterException` và lỗi provider thực tế.

Các tên `"EdDSA"`, `"Ed25519"`, `"Ed448"` có trong **Java Security Standard Algorithm Names**, nhưng việc có tên chuẩn không đồng nghĩa mọi triển khai Java đều có provider thực thi thuật toán đó. Nên kiểm tra môi trường deploy thực thay vì giả định chỉ vì chương trình chạy trên máy phát triển.

## 5. Quá trình ký/xác minh bằng `Signature`

JCA `Signature` có ba bước nền tảng:

1. **Lấy đối tượng và khởi tạo**: `Signature.getInstance(algorithm)`, rồi `initSign(privateKey)` hoặc `initVerify(publicKey)`.
2. **Nạp đúng byte cần ký/xác minh**: `update(byte[])`, có thể nhiều lần; chữ ký ràng buộc vào **chuỗi byte**, không phải đối tượng Java hay văn bản trừu tượng.
3. **Hoàn tất**: `sign()` trả byte chữ ký; `verify(signatureBytes)` kiểm tra và trả boolean khi xử lý bình thường.

Ví dụ ký/xác minh một thông điệp `UTF-8`:

```java
// Minh họa trong phương thức đã có KeyPair pair; có thể cần throws GeneralSecurityException.
byte[] data = "Xin chào".getBytes(StandardCharsets.UTF_8);

Signature signer = Signature.getInstance("Ed25519");
signer.initSign(pair.getPrivate());
signer.update(data);
byte[] signature = signer.sign();

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(pair.getPublic());
verifier.update(data);
boolean valid = verifier.verify(signature);
```

**Điều kiện:** `pair` phải là cặp khóa Ed25519. Một chữ ký hợp lệ chỉ cho biết rằng **đúng khóa riêng tương ứng** đã tham gia ký **đúng byte thông điệp**; nó không tự kiểm tra người chủ khóa, hạn sử dụng khóa, quyền ký, nonce, timestamp hoặc dữ liệu doanh nghiệp có hợp lệ không.

### Nội dung ký phải ổn định ở mức byte

Hai chuỗi nhìn giống nhau đôi khi thành các byte khác nhau do:

- UTF-8 so với charset khác.
- Dấu xuống dòng LF so với CRLF.
- Dạng Unicode tổ hợp/kết hợp khác nhau.
- JSON khác thứ tự trường hoặc khoảng trắng.
- Chuẩn hóa số/thời gian không thống nhất.
- Bên gửi ký **payload gốc**, còn bên nhận lại parse rồi serialize payload trước khi verify.

**Quy tắc:** hai bên phải đồng ý một **biểu diễn byte chính xác**. Với JSON, dùng canonicalization/serialization được protocol quy định, hoặc ký trực tiếp những byte được truyền nếu giao thức cho phép. Không tự ý dùng `trim()`, `normalize()`, `replace()` trước verify khi hợp đồng không yêu cầu.

## 6. Chương trình chạy được: Ed25519 và Ed448

Ví dụ dưới đây chạy với **JDK 17+**, các API EdDSA dùng đều là API chính thức từ Java 15 trở đi. Kết quả được thiết kế cố định mặc dù cặp khóa tạo ra là **ngẫu nhiên**: ta chỉ in kích thước, trạng thái xác minh, tính lặp của chữ ký thuần và định dạng mã hóa khóa, không in chính các byte chữ ký/khóa.

Lưu trong tệp **`EdDsaChoiceDemo.java`** (UTF-8):

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.NamedParameterSpec;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;

public class EdDsaChoiceDemo {
    private static byte[] sign(String algorithm, PrivateKey key, byte[] data)
            throws GeneralSecurityException {
        Signature signer = Signature.getInstance(algorithm);
        signer.initSign(key);
        signer.update(data);
        return signer.sign();
    }

    private static boolean verify(String algorithm, PublicKey key,
            byte[] data, byte[] signature) throws GeneralSecurityException {
        Signature verifier = Signature.getInstance(algorithm);
        verifier.initVerify(key);
        verifier.update(data);
        return verifier.verify(signature);
    }

    private static void run(String algorithm, NamedParameterSpec curve)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
        generator.initialize(curve);
        KeyPair pair = generator.generateKeyPair();

        byte[] original = "order=42;status=paid".getBytes(StandardCharsets.UTF_8);
        byte[] changed = "order=42;status=void".getBytes(StandardCharsets.UTF_8);
        byte[] signature = sign(algorithm, pair.getPrivate(), original);
        byte[] signedAgain = sign(algorithm, pair.getPrivate(), original);

        KeyFactory factory = KeyFactory.getInstance("EdDSA");
        PublicKey restoredPublic = factory.generatePublic(
                new X509EncodedKeySpec(pair.getPublic().getEncoded()));
        PrivateKey restoredPrivate = factory.generatePrivate(
                new PKCS8EncodedKeySpec(pair.getPrivate().getEncoded()));

        System.out.println(algorithm + ": signatureBytes=" + signature.length);
        System.out.println(algorithm + ": valid="
                + verify(algorithm, pair.getPublic(), original, signature));
        System.out.println(algorithm + ": changedMessage="
                + verify(algorithm, pair.getPublic(), changed, signature));
        System.out.println(algorithm + ": deterministic="
                + Arrays.equals(signature, signedAgain));
        System.out.println(algorithm + ": decodedKeys="
                + verify(algorithm, restoredPublic, original,
                        sign(algorithm, restoredPrivate, original)));
        System.out.println(algorithm + ": keyFormats="
                + pair.getPublic().getFormat() + "/" + pair.getPrivate().getFormat());
    }

    public static void main(String[] args) throws GeneralSecurityException {
        run("Ed25519", NamedParameterSpec.ED25519);
        run("Ed448", NamedParameterSpec.ED448);
    }
}
```

Lệnh chạy từ thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 EdDsaChoiceDemo.java
java -cp . EdDsaChoiceDemo
```

**Stdout đã kiểm chứng:**

```text
Ed25519: signatureBytes=64
Ed25519: valid=true
Ed25519: changedMessage=false
Ed25519: deterministic=true
Ed25519: decodedKeys=true
Ed25519: keyFormats=X.509/PKCS#8
Ed448: signatureBytes=114
Ed448: valid=true
Ed448: changedMessage=false
Ed448: deterministic=true
Ed448: decodedKeys=true
Ed448: keyFormats=X.509/PKCS#8
```

### Giải thích kết quả

- `signatureBytes=64` hoặc `114` là kích thước chữ ký thuần của đúng biến thể EdDSA.
- `valid=true`: thông điệp gốc, chữ ký và khóa công khai đúng cặp.
- `changedMessage=false`: chỉ đổi `status=paid` thành `status=void` đã làm chữ ký không còn hợp lệ trên nội dung bị sửa.
- `deterministic=true`: **hai lần ký cùng bytes bằng cùng khóa và cùng biến thể pure EdDSA** cho cùng chữ ký. Cặp khóa mới được sinh ngẫu nhiên ở mỗi lần chạy, nên **byte chữ ký thực tế giữa hai lần chạy khác nhau**.
- `decodedKeys=true`: `KeyFactory("EdDSA")` tái tạo khóa từ định dạng `X509EncodedKeySpec` và `PKCS8EncodedKeySpec` trong môi trường demo; chữ ký mới vẫn xác minh được.
- `keyFormats=X.509/PKCS#8`: minh họa **container/định dạng khóa của provider**, không phải kích thước raw key. Không in private key hay giá trị seed trong log.

**Giới hạn quan trọng của demo:** chương trình chọn `Ed25519` hoặc `Ed448` tường minh và dùng SunEC của JDK đang chạy. Trong môi trường key store/HSM, `PrivateKey.getEncoded()` có thể **trả `null` do khóa không cho phép xuất**, hoặc provider không hỗ trợ cùng một cách import/export. Không sao chép đoạn export private key của demo vào code sản xuất mà không có yêu cầu/cơ chế bảo vệ khóa.

## 7. `EdDSA` tổng quát và tên thuật toán cụ thể

Có hai phong cách dùng API:

**Phong cách rõ đường cong:**

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
Signature signer = Signature.getInstance("Ed25519");
```

**Phong cách tổng quát nhưng chọn tham số:**

```java
KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(NamedParameterSpec.ED448);
Signature signer = Signature.getInstance("Ed448");
```

Cả hai đoạn trên **chỉ là ví dụ khởi tạo** trong phạm vi đã import các API, không phải chương trình độc lập. Phong cách tổng quát có lợi khi viết một hàm chọn curve ở runtime. Tuy nhiên **đừng giả định** `"EdDSA"` luôn đồng nghĩa Ed25519: nếu không initialize bằng tham số rõ ràng, default phụ thuộc hợp đồng/provider. Trong một giao thức cần thuật toán cố định, **chỉ định curve ở cả bước tạo khóa và bước ký** để dễ kiểm tra.

`NamedParameterSpec.ED25519` và `NamedParameterSpec.ED448` là các hằng chuẩn có từ Java 15. Đừng thay bằng tên `X25519`, `X448` vì đó là parameter set cho key agreement, không phải cặp khóa ký EdDSA.

Có thể chọn `Signature.getInstance("EdDSA")` với provider hỗ trợ biến thể theo khóa, nhưng khi đặc tả giao thức yêu cầu `Ed25519` hoặc `Ed448` cụ thể, cách viết tên thuật toán cụ thể ít gây nhầm lẫn hơn. Nếu một provider chỉ hỗ trợ một subset, hãy xử lý lỗi thay vì âm thầm chuyển thuật toán.

## 8. Pure EdDSA, context và prehash không đồng nghĩa

RFC 8032 định nghĩa các chế độ:

| Curve | Chế độ thường gặp | Ý nghĩa |
|---|---|---|
| Ed25519 | **Ed25519** | Pure EdDSA, không dùng context |
| Ed25519 | **Ed25519ctx** | Pure EdDSA có context để tách miền sử dụng (*domain separation*) |
| Ed25519 | **Ed25519ph** | Chế độ prehash được RFC 8032 định nghĩa, không đồng nghĩa “tự SHA-256 rồi ký Ed25519” |
| Ed448 | **Ed448** | Pure EdDSA; có thể dùng context theo đặc tả |
| Ed448 | **Ed448ph** | Biến thể prehash |

Java có `java.security.spec.EdDSAParameterSpec` (từ Java 15), cho phép biểu diễn **prehash flag** và **context byte[]**. Theo Javadoc, `new EdDSAParameterSpec(true)` yêu cầu chế độ prehash; `new EdDSAParameterSpec(false, contextBytes)` yêu cầu chế độ có context. **Dùng chung lựa chọn ở bên ký và bên xác minh**, và phải đảm bảo protocol/provider hỗ trợ đúng biến thể.

**Bẫy tương thích:** **không context** và **context rỗng** không luôn tương đương về chế độ. Javadoc cảnh báo rằng chế độ không cung cấp context có thể khác chế độ cung cấp `new byte[0]`. Với Ed25519, cách chọn này có thể phân biệt pure Ed25519 và Ed25519ctx. Khi đưa vào giao thức, phải ghi rõ **mode, context, encoding**, không chỉ ghi mỗi “Ed25519”.

### Không tự prehash rồi coi là Ed25519ph

Lệnh kiểu:

```java
// ĐÂY LÀ MINH HỌA CÁCH KHÔNG ĐÚNG NẾU MUỐN Ed25519ph:
byte[] digest = java.security.MessageDigest
        .getInstance("SHA-256").digest(messageBytes);
signer.update(digest);
```

Đây **không** phải thuật toán **Ed25519ph** theo RFC 8032: bộ ký plain Ed25519 đang ký **32 byte digest do ứng dụng tạo**, khác quy tắc prehash và domain separation của chế độ ph chuẩn. Dùng `EdDSAParameterSpec` và một protocol được thiết kế rõ, hoặc dùng chế độ pure khi phù hợp. Đoạn trên có biến giả định `messageBytes` và `signer`, chỉ để cảnh báo, không phải code hoàn chỉnh.

Với Ed25519, mã thuần thường không cần bạn gọi `SHA-512` ngoài JCA; với Ed448 cũng không cần tự thực hiện `SHAKE256`. Provider EdDSA xử lý các bước băm **nội bộ theo mode**.

## 9. Xuất/nhập khóa và tương thích định dạng

Java thường biểu diễn khóa bằng các interface `PrivateKey`, `PublicKey`, còn việc mã hóa bằng các container có chuẩn:

- **Public key:** `pair.getPublic().getEncoded()` thường là DER **SubjectPublicKeyInfo/X.509**. Dùng `new X509EncodedKeySpec(bytes)` khi import.
- **Private key:** `pair.getPrivate().getEncoded()` thường là DER **PKCS#8**. Dùng `new PKCS8EncodedKeySpec(bytes)` khi import.
- **`KeyFactory`** có thể dùng `KeyFactory.getInstance("EdDSA")`, hoặc thuật toán cụ thể khi provider hỗ trợ.
- **PEM** là hình thức trình bày Base64 có header/footer cho một đối tượng DER; Java `getEncoded()` không tự tạo văn bản PEM. `X509EncodedKeySpec` không dùng để đọc một chứng chỉ X.509 nguyên vẹn.
- **RFC 8410** quy định các algorithm identifiers của Ed25519/Ed448 trong một số cấu trúc X.509 và cách biểu diễn; metadata thuật toán phải được giữ, không tự đoán curve chỉ theo số byte.

**Bảo vệ private key:** PKCS#8 **không mặc nhiên được mã hóa khi lưu**. Trong production, ưu tiên KeyStore, HSM/KMS hoặc cơ chế bảo vệ bí mật phù hợp; hạn chế quyền truy cập, log, backup và export. Không hard-code private key trong source; không tái dùng cùng key pair cho **ký** và **thỏa thuận khóa** qua phép chuyển đổi tự tạo.

Public key được phân phối qua một nguồn **xác thực** (certificate chain, key registry đã ký, cấu hình pinning, API trust store…). Nếu kẻ tấn công có thể thay key công khai trong lúc verify, một chữ ký hợp lệ trên khóa do kẻ tấn công tạo **không chứng minh nội dung đến từ đối tượng tin cậy**.

## 10. Chữ ký số không giải quyết toàn bộ bảo mật ứng dụng

### 10.1. Xác minh chữ ký khác xác thực quyền

Bên nhận không chỉ hỏi `verify(...) == true`. Còn phải kiểm tra:

- Khóa công khai có gắn đúng **người ký/dịch vụ** không?
- Khóa có được phép ký **loại thông điệp** này không?
- Thuật toán được nhận có nằm trong **allowlist** của giao thức không?
- Thông điệp có đúng **context, version, purpose** của giao dịch không?
- Dữ liệu có còn hiệu lực, có bị phát lại (**replay**) hay không?
- Nếu nhận certificate, chuỗi tin cậy, thời gian hiệu lực, chính sách và các kiểm tra liên quan có được xác minh không?

Đừng cho caller chọn tự do tên thuật toán từ payload rồi dùng nó để verify mà không áp chính sách. Đây là nhóm lỗi **algorithm confusion/downgrade** ở tầng protocol, không phải lỗi của phép toán EdDSA.

### 10.2. Đảm bảo domain separation và chống replay

Một chữ ký trên `"42"` không nói rõ số 42 là gì. Một hệ thống có nhiều mục đích nên ký dữ liệu đã ràng buộc với **loại thông điệp, phiên bản giao thức, môi trường, đối tượng nhận và dữ liệu nghiệp vụ**. Có thể dùng context theo RFC nếu mọi bên hỗ trợ đúng mode, hoặc cấu trúc payload được phiên bản hóa/canonical hóa theo protocol. **Domain separation không tự động thay thế replay protection**: cần timestamp, nonce, request ID hay cơ chế nghiệp vụ phù hợp.

### 10.3. Deterministic signing không loại bỏ mọi yêu cầu ngẫu nhiên

Pure Ed25519/Ed448 tạo chữ ký xác định theo khóa và thông điệp, tránh phải tạo **nonce ngẫu nhiên mới cho mỗi lần ký** theo cách một số thuật toán chữ ký khác cần. Tuy nhiên:

- Việc sinh khóa ban đầu vẫn phải dùng nguồn ngẫu nhiên mật mã đủ mạnh.
- Chất lượng và bảo mật private key vẫn mang tính quyết định.
- Cài đặt/provider và phần cứng cần được đánh giá về side-channel, lỗi thực thi và bảo vệ khóa.
- Không lưu kết quả chữ ký/khóa riêng trong log chỉ để chứng minh tính lặp.

### 10.4. Không mặc định hỗ trợ mọi protocol

Ví dụ Ed25519/Ed448 trong JCA **không có nghĩa** mọi máy chủ TLS, JSON Web Signature, SSH key, X.509 certificate profile hoặc dịch vụ ký tài liệu đều sẽ chấp nhận một chữ ký JCA thô. Bên ngoài có thể yêu cầu **OID, canonicalized bytes, algorithm identifier, encoding, key usage hoặc cấu trúc container** cụ thể.

## 11. Các lỗi hay gặp trong Java

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `NoSuchAlgorithmException` | Runtime/provider không hỗ trợ `Ed25519`, `Ed448` hay `EdDSA` | Kiểm tra JDK/provider lúc deploy, chọn tên chuẩn, cấu hình hoặc báo không hỗ trợ |
| `InvalidAlgorithmParameterException` khi `initialize` | Parameter set không phù hợp bộ tạo khóa/provider | Dùng `NamedParameterSpec.ED25519` hoặc `ED448` đúng cấu hình |
| `InvalidKeyException` khi `initSign/initVerify` | Khóa không thuộc thuật toán/curve đúng, hoặc provider từ chối | Kiểm tra thuật toán, định dạng, nguồn khóa và provider |
| `verify(...)` trả `false` | Dữ liệu, chữ ký, khóa hoặc biến thể không khớp | So sánh byte thông điệp, key ID, mode, context, version |
| `SignatureException` khi verify | Chữ ký sai định dạng hoặc provider không thể xử lý | Phân biệt lỗi định dạng với chữ ký hợp lệ; bắt lỗi có ngữ cảnh |
| Thông điệp nhìn giống nhưng verify sai | Khác UTF-8, LF/CRLF, JSON serialization hoặc Unicode normalization | Định nghĩa rõ canonicalization và kiểm tra **byte[] thực** |
| Ed25519ph không tương thích bên kia | Một bên ký plain Ed25519 trên hash thủ công, bên kia chờ mode ph chuẩn | Dùng mode/prehash/context theo RFC 8032, kiểm thử test vector |
| Key public có 44 byte thay vì 32 | Đang nhìn X.509/SPKI DER, không phải raw public key | Phân biệt container encoding và raw key; dùng `KeyFactory` |
| `getEncoded()` của private key là `null` | Provider HSM/keystore không cho xuất khóa | Ký qua key handle/provider; không ép private key rời HSM |
| Chữ ký Ed448 không bằng 64 byte | Ed448 dùng **114 byte** chữ ký thuần | Không hard-code 64 cho mọi EdDSA |
| Thuật toán chấp nhận local nhưng đối tác từ chối | Protocol/profile phía đối tác không hỗ trợ curve/mode/encoding | Kiểm tra tiêu chuẩn và negotiate/allowlist trước khi triển khai |
| Nhầm `X25519` với `Ed25519` | Trộn key agreement và chữ ký | Dùng riêng loại khóa/thuật toán theo nhiệm vụ |

**Gợi ý xử lý lỗi:** các ngoại lệ từ `Signature` và `KeyFactory` nên được phân nhóm theo lỗi cấu hình, sai khóa, sai encoding hoặc dữ liệu sai; không bắt toàn bộ `GeneralSecurityException` rồi trả `true`, không fallback im lặng sang thuật toán khác.

## 12. Kiểm thử cần có trước khi phát hành

Bộ kiểm thử cho từng thuật toán/curve nên bao gồm:

1. **Positive:** cùng khóa, cùng byte thông điệp, cùng mode → `verify == true`.
2. **Tampered message:** đổi một byte thông điệp → `verify == false` trong trường hợp chữ ký vẫn hợp lệ về định dạng.
3. **Wrong key:** tạo cặp khóa khác cùng curve, dùng public key mới → không xác minh được chữ ký cũ.
4. **Wrong curve/mode:** thử sai thuật toán, prehash hoặc context → không được xem là hợp lệ; lỗi có thể xuất hiện dưới dạng `InvalidKeyException`, `SignatureException`, `InvalidAlgorithmParameterException` hoặc kết quả false theo tình huống/provider.
5. **Encoding:** chuyển public key X.509 và private key PKCS#8 qua `KeyFactory` nếu hệ thống cho phép export; kết quả vẫn dùng được.
6. **Size:** kiểm tra chữ ký thuần Ed25519 đúng **64 byte**, Ed448 đúng **114 byte**, nhưng không nhầm kích thước **key container**.
7. **Cross-provider/interoperability:** kiểm thử cả bên Java và thư viện/protocol ngoài Java, đặc biệt nếu phải ký/xác minh trên HSM, KMS hoặc JDK khác.
8. **Version/metadata:** kiểm thử policy thuật toán/curve và key ID; từ chối thuật toán không được phép, mode không nhận diện được hoặc nội dung vượt chính sách.
9. **Operational:** đảm bảo private key không bị ghi log và bảo vệ export/backup theo quy trình.

Ví dụ ở phần 6 chứng minh được các bất biến xác định (độ dài, verify và key import), không dùng một chuỗi hex chữ ký cố định vì key pair sinh ngẫu nhiên mỗi lần. Khi cần test **test vectors cố định**, dùng các vector RFC 8032 với khóa/message chuẩn, hoặc bộ vector từ nguồn tin cậy tương thích đúng mode.

## 13. Kết luận: chọn đúng biến thể, không chỉ chọn tên thuật toán

- **Ed25519**: lựa chọn cân bằng tốt khi yêu cầu **~128-bit an toàn cổ điển**, chữ ký 64 byte, hiệu năng và tương thích thực tế.
- **Ed448**: phù hợp khi cần **~224-bit an toàn cổ điển**, chấp nhận chữ ký 114 byte và xác nhận mọi đầu cuối hỗ trợ.
- **Cả hai**: chữ ký số EdDSA, không phải mã hóa, key agreement hoặc bảo vệ hậu lượng tử.
- **Trong Java**: chọn rõ `NamedParameterSpec.ED25519/ED448`, tạo khóa đúng curve, ký và verify với `Signature` tương ứng; quản lý encoding/khóa bí mật đúng hợp đồng.
- **Trong giao thức**: điều quan trọng không chỉ là toán học; **trusted public key**, đúng **message bytes**, đúng **mode/context**, allowlist thuật toán và khả năng interoperability quyết định một triển khai có an toàn và vận hành được hay không.

### Tài liệu chính thức còn áp dụng

- [RFC 8032 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://www.rfc-editor.org/rfc/rfc8032.html): Ed25519, Ed448, các mode và test vectors.
- [RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, X448](https://www.rfc-editor.org/rfc/rfc8410.html): định dạng khóa/chứng chỉ và OID.
- [Oracle Java SE 26 — `Signature`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html), [`KeyPairGenerator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyPairGenerator.html), [`KeyFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyFactory.html).
- [Oracle Java SE 26 — `NamedParameterSpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/NamedParameterSpec.html), [`EdDSAParameterSpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/spec/EdDSAParameterSpec.html).
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên thuật toán JCA.
- [JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): tính năng được đưa vào Java 15, vẫn được hỗ trợ hiện nay.
