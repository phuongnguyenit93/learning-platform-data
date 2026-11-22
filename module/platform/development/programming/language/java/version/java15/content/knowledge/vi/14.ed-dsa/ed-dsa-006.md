# JCA, provider và khả năng hỗ trợ thuật toán EdDSA trong Java

**EdDSA** (*Edwards-curve Digital Signature Algorithm*) là họ thuật toán **chữ ký số** dựa trên đường cong Edwards, được mô tả trong **RFC 8032**. Java 15 bổ sung triển khai EdDSA theo **JEP 339**. Những API công khai của **Java Cryptography Architecture (JCA)** vẫn được sử dụng trong Java hiện đại: `KeyPairGenerator` tạo cặp khóa, `Signature` ký/xác minh, `KeyFactory` đọc hoặc chuyển đổi biểu diễn khóa, còn **security provider** cung cấp triển khai thực tế.

Điểm quan trọng nhất của chủ đề này: **tên thuật toán được chuẩn hóa không đồng nghĩa với việc mọi JDK, mọi provider hoặc thiết bị bảo mật đều hỗ trợ thuật toán đó**. Trước khi triển khai EdDSA, phải hiểu cách JCA chọn provider, kiểm tra loại dịch vụ cần dùng và thử quy trình ký/xác minh trong chính môi trường chạy thật.

## 1. Phân biệt thuật toán, API JCA và provider

Hình dung ba lớp:

```text
Mã Java của ứng dụng
    |
    |  KeyPairGenerator.getInstance("Ed25519")
    |  Signature.getInstance("Ed25519")
    |  KeyFactory.getInstance("Ed25519")
    v
API tiêu chuẩn JCA trong java.security
    |
    |  Tra cứu đăng ký dịch vụ theo tên thuật toán và ưu tiên
    v
Security Provider
    |
    |  Ví dụ SunEC trong một bản JDK; hoặc provider khác
    v
Triển khai thuật toán trên phần mềm / thiết bị / HSM
```

- **API JCA** đưa ra giao diện chuẩn; ứng dụng không cần trực tiếp gọi mã toán học của thư viện ký số.
- **Provider** (đối tượng `java.security.Provider`) là nơi đăng ký các *services*, ví dụ `Signature.Ed25519` hoặc `KeyPairGenerator.Ed448`.
- **Tên thuật toán** dùng khi yêu cầu `getInstance(...)`, ví dụ `"Ed25519"`. Tên chuẩn là hợp đồng giao tiếp giữa ứng dụng và provider.
- **JDK và cấu hình triển khai** quyết định provider nào được cài đặt, đăng ký, ưu tiên hoặc vô hiệu hóa. Một runtime được tùy biến có thể không mang đầy đủ provider như bộ JDK tiêu chuẩn.
- **Key và khả năng provider** vẫn cần khớp. Việc lấy được `Signature.getInstance("Ed25519")` chưa bảo đảm một private key bất kỳ có thể dùng để ký.

JCA hỗ trợ **provider pluggability**: cùng một đoạn mã Java có thể dùng triển khai phần mềm hoặc triển khai bên thứ ba, miễn provider tương thích và được cấu hình đúng.

## 2. Tên thuật toán EdDSA được Java chuẩn hóa

Theo tài liệu **Java Security Standard Algorithm Names**, những tên cần nhận biết là:

| Tên | Ý nghĩa | Cách dùng điển hình |
| --- | --- | --- |
| `Ed25519` | Biến thể chữ ký EdDSA dùng edwards25519 | `KeyPairGenerator.getInstance("Ed25519")`, `Signature.getInstance("Ed25519")` |
| `Ed448` | Biến thể chữ ký EdDSA dùng edwards448 | `KeyPairGenerator.getInstance("Ed448")`, `Signature.getInstance("Ed448")` |
| `EdDSA` | Tên tổng quát cho họ thuật toán EdDSA | API hỗ trợ chọn biến thể bằng khóa hoặc tham số tương ứng |

Các tên này có thể xuất hiện ở các loại **engine** khác nhau, không chỉ `Signature`:

- `KeyPairGenerator`: tạo public/private key pair.
- `Signature`: ký bằng private key và xác minh bằng public key.
- `KeyFactory`: tạo đối tượng khóa từ key specification hoặc trích xuất specification được hỗ trợ.

Tên chuẩn hóa giúp viết mã **không ràng buộc một provider cụ thể**. Tuy nhiên, chương trình nên chọn **`Ed25519` hoặc `Ed448` rõ ràng** khi giao thức đã quy định một biến thể. Dùng `EdDSA` tổng quát đòi hỏi quản lý nhất quán biến thể qua khóa/tham số và khả năng provider.

**Không đánh đồng các thuật toán:**

- `Ed25519`/`Ed448` là các biến thể **chữ ký EdDSA**.
- `ECDSA` là một họ chữ ký khác, không phải alias tương đương EdDSA.
- `X25519` và `X448` thuộc nhóm **key agreement XDH**, không phải tên thuật toán để ký bằng `Signature`.
- EdDSA dùng các bước băm bên trong theo RFC 8032; **đừng tự lấy SHA-256 của dữ liệu rồi cho rằng đó là cùng một quy trình ký Ed25519**. Khi hệ thống cần biến thể *prehash* hay *context*, hai bên phải thống nhất giao thức và tham số thực sự được hỗ trợ.

## 3. Provider nào có thể cung cấp EdDSA?

Trong **JDK tham chiếu của Oracle/OpenJDK**, provider **`SunEC`** có các dịch vụ:

| JCA engine | Dịch vụ EdDSA được tài liệu SunEC liệt kê |
| --- | --- |
| `KeyPairGenerator` | `Ed25519`, `Ed448`, `EdDSA` |
| `Signature` | `Ed25519`, `Ed448`, `EdDSA` |
| `KeyFactory` | `Ed25519`, `Ed448`, `EdDSA` |

`SunEC` thường nằm trong module **`jdk.crypto.ec`** của các bản JDK có module này. Một bản runtime được đóng gói bằng `jlink` hoặc một bản Java của nhà phân phối khác có thể có cấu hình module/provider khác. Provider của HSM/PKCS#11 hoặc sản phẩm bên thứ ba cũng không nhất thiết cung cấp những dịch vụ EdDSA giống `SunEC`.

Vì thế, câu nói **“Java 15 có EdDSA”** nên hiểu chính xác là **JDK 15 đã bổ sung API/tên thuật toán và triển khai EdDSA trong JDK tham chiếu**, chứ không phải bất kỳ provider nào cũng có mọi biến thể, mọi dịch vụ, mọi tùy chọn hay cùng chính sách sử dụng khóa.

Các sản phẩm có yêu cầu tuân thủ hoặc phần cứng bảo mật còn cần kiểm tra **chính sách được phép sử dụng thuật toán**, chứng nhận của provider, cách cung cấp khóa và cấu hình ở môi trường triển khai thực tế. Tên thuật toán có mặt trong danh sách không chứng minh một triển khai đã được chứng nhận cho nhu cầu cụ thể.

## 4. JCA chọn provider như thế nào?

Thông thường, không cần khóa cứng tên provider:

```java
import java.security.KeyPairGenerator;
import java.security.Signature;

KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
Signature signer = Signature.getInstance("Ed25519");
```

Các lời gọi `getInstance(String algorithm)` tìm một triển khai hỗ trợ engine và tên thuật toán theo cơ chế ưu tiên provider của JCA. Nếu không có triển khai phù hợp, chúng ném **`NoSuchAlgorithmException`**.

Provider được chọn có thể kiểm tra bằng:

```java
String keyGeneratorProvider = generator.getProvider().getName();
String signatureProvider = signer.getProvider().getName();
```

Đây là **đoạn minh họa** chạy tiếp sau khi hai biến đã được tạo. Không kết luận hai provider phải giống nhau: engine `KeyPairGenerator` và `Signature` có thể dùng hai triển khai khác nhau. Với `Signature`, việc chọn provider còn có thể phụ thuộc thời điểm khởi tạo với key vì một số triển khai JCA sử dụng lựa chọn trì hoãn; hãy kiểm tra provider thực tế **sau `initSign`/`initVerify`** nếu cần chẩn đoán hành vi.

Nếu yêu cầu nhà cung cấp cụ thể:

```java
Signature signer = Signature.getInstance("Ed25519", "SunEC");
```

Lời gọi trên **không còn trung lập với provider**. Nó chỉ phù hợp khi ứng dụng thật sự phụ thuộc một triển khai đã được kiểm soát và môi trường chắc chắn đăng ký provider đó. Nếu tên provider không được đăng ký, có thể xảy ra `NoSuchProviderException`; nếu provider có tồn tại nhưng không cung cấp dịch vụ đã yêu cầu, có thể xảy ra `NoSuchAlgorithmException`.

**Khuyến nghị cho mã ứng dụng thông thường:** dùng overload chỉ có **tên thuật toán** và để JCA chọn provider. Chỉ chỉ định tên `SunEC` hoặc provider của HSM khi có lý do triển khai, tương thích hoặc tuân thủ rõ ràng.

## 5. Kiểm tra dịch vụ trước khi sử dụng

Java cung cấp API để kiểm tra **những dịch vụ được các provider đã đăng ký quảng bá**:

```java
import java.security.Provider;
import java.security.Security;

Provider[] providers = Security.getProviders("Signature.Ed25519");
boolean registered = providers != null && providers.length > 0;
```

Chú ý chuỗi truy vấn có dạng **`ServiceType.Algorithm`**. Một vài loại truy vấn hữu ích:

```java
Security.getProviders("Signature.Ed25519");
Security.getProviders("Signature.Ed448");
Security.getProviders("KeyPairGenerator.Ed25519");
Security.getProviders("KeyFactory.Ed25519");
```

Các lời gọi trả về `Provider[]` nếu có kết quả; **có thể trả `null` khi không có provider phù hợp**. Không gọi `.length` mà quên kiểm tra `null`.

Để liệt kê tất cả các tên thuật toán đã đăng ký cho một engine:

```java
import java.security.Security;
import java.util.Set;

Set<String> available = Security.getAlgorithms("Signature");
System.out.println(available);
```

Danh sách này được **trích từ các provider đã đăng ký**, có thể khác nhau theo hệ điều hành/JDK/cấu hình, và không nên được sử dụng làm stdout cố định trong bài kiểm tra. Tên dịch vụ trong listing có thể được chuẩn hóa kiểu chữ/alias; khi so sánh cần tuân theo quy ước tên thuật toán của JCA.

Một cách liệt kê theo từng provider:

```java
import java.security.Provider;
import java.security.Security;

for (Provider provider : Security.getProviders()) {
    Provider.Service service =
            provider.getService("Signature", "Ed25519");
    if (service != null) {
        System.out.println(provider.getName() + ": " + service.getAlgorithm());
    }
}
```

Cần ghi nhớ rằng **được quảng bá là có service chưa bảo đảm thực hiện được mọi thao tác**: provider có thể yêu cầu một loại key nhất định, một token phần cứng đang kết nối, tham số hợp lệ hoặc chính sách bảo mật cụ thể. Kiểm tra thực tế phải bao gồm **`initSign`, `sign`, `initVerify`, `verify`** với khóa đúng kiểu, trong môi trường được triển khai.

## 6. Ví dụ Java 17+ đầy đủ: kiểm tra provider, ký và xác minh Ed25519

Ví dụ sau dùng JCA để tạo khóa, ký một thông điệp, xác minh chữ ký, kiểm tra thông điệp bị sửa đổi và chuyển đổi khóa qua các specification chuẩn. Dùng `Ed25519` tường minh để tránh phụ thuộc biến thể mặc định của `EdDSA` tổng quát.

Để giữ ví dụ dễ chạy, chương trình dùng một JDK hỗ trợ **`Ed25519` qua `KeyPairGenerator`, `Signature`, `KeyFactory`**, và **khóa phần mềm có thể xuất mã hóa**. Nếu ứng dụng dùng hardware key store/HSM, private key có thể không cho phép `getEncoded()`, nên phần xuất/nhập khóa cần một thiết kế khác; không in hoặc gửi private key ra ngoài.

Lưu tên file **`EdDsaProviderDemo.java`** dưới dạng UTF-8:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Provider;
import java.security.Security;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

public class EdDsaProviderDemo {
    private static boolean hasService(String type, String algorithm) {
        Provider[] providers = Security.getProviders(type + "." + algorithm);
        return providers != null && providers.length > 0;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Ed25519_keygen=" +
                hasService("KeyPairGenerator", "Ed25519"));
        System.out.println("Ed25519_signature=" +
                hasService("Signature", "Ed25519"));
        System.out.println("Ed448_signature=" +
                hasService("Signature", "Ed448"));

        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = generator.generateKeyPair();

        byte[] message = "Java 15 EdDSA".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        System.out.println("verified=" + verifier.verify(signature));

        verifier.initVerify(pair.getPublic());
        verifier.update("modified".getBytes(StandardCharsets.UTF_8));
        System.out.println("tamperedVerified=" + verifier.verify(signature));

        System.out.println("signatureBytes=" + signature.length);
        System.out.println("keygenProviderSelected=" +
                (generator.getProvider() != null));
        System.out.println("signatureProviderSelected=" +
                (signer.getProvider() != null));

        KeyFactory factory = KeyFactory.getInstance("Ed25519");
        var decodedPublic = factory.generatePublic(
                new X509EncodedKeySpec(pair.getPublic().getEncoded()));
        var decodedPrivate = factory.generatePrivate(
                new PKCS8EncodedKeySpec(pair.getPrivate().getEncoded()));

        System.out.println("decodedKeys=" +
                (decodedPublic != null && decodedPrivate != null));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 EdDsaProviderDemo.java
java EdDsaProviderDemo
```

**Đầu ra chính xác trên JDK thử nghiệm OpenJDK 24 có SunEC và đầy đủ ba dịch vụ**:

```text
Ed25519_keygen=true
Ed25519_signature=true
Ed448_signature=true
verified=true
tamperedVerified=false
signatureBytes=64
keygenProviderSelected=true
signatureProviderSelected=true
decodedKeys=true
```

Giải thích:

- Ba dòng đầu phản ánh **dịch vụ đã đăng ký** ở môi trường thử nghiệm; riêng `Ed448_signature` **có thể là `false`** ở một runtime khác mà chương trình vẫn sử dụng Ed25519 thành công.
- `KeyPairGenerator.getInstance("Ed25519")` tạo cặp khóa gồm private key để ký và public key để xác minh. Không cần `initialize(255)` khi dùng tên `Ed25519` tường minh với provider hỗ trợ.
- `Signature.update(message)` đưa **byte chính xác** của thông điệp vào thuật toán; `StandardCharsets.UTF_8` bảo đảm cách mã hóa text nhất quán.
- `verified=true` chứng minh chữ ký hợp lệ đối với đúng public key và thông điệp ấy.
- `tamperedVerified=false` chứng minh cùng chữ ký không hợp lệ nếu nội dung thông điệp bị đổi.
- Chữ ký Ed25519 dạng RFC 8032 có kích thước **64 byte**. Đây là độ dài chữ ký thô, **không phải** độ dài của object key hay file mã hóa.
- Hai kiểm tra `ProviderSelected` xác nhận JCA trả về provider; không buộc một tên nhà cung cấp cố định.
- `X509EncodedKeySpec` dùng cho **public key** dạng SubjectPublicKeyInfo, `PKCS8EncodedKeySpec` dùng cho **private key** dạng PKCS#8 trong ví dụ phần mềm. Đây không phải 32-byte seed/key raw của Ed25519. Một private key trong HSM có thể không export được nên không nên mặc định dùng cách này ở môi trường sản xuất.

Mã này không in private key, chữ ký cụ thể hay tên provider nên phần stdout ổn định trên cấu hình thử nghiệm. Chương trình có thể ném ngoại lệ nếu runtime không hỗ trợ Ed25519, không thể dùng private key theo cách yêu cầu hoặc không hỗ trợ xuất mã hóa khóa. Khi đó phải **chẩn đoán provider/khóa**, không xem đó là lý do để tự chuyển sang một thuật toán không có trong giao thức.

## 7. Ed25519, Ed448 và tên EdDSA tổng quát

**Ed25519** và **Ed448** đều là thuật toán chữ ký EdDSA được mô tả trong RFC 8032, nhưng **không thể thay thế trực tiếp cho nhau** khi dữ liệu, khóa và protocol đã quy định một biến thể.

| Tiêu chí | Ed25519 | Ed448 |
| --- | --- | --- |
| Đường cong | edwards25519 | edwards448 |
| Tên JCA cụ thể | `"Ed25519"` | `"Ed448"` |
| Độ dài chữ ký RFC 8032 | **64 byte** | **114 byte** |
| Private/public key | Khóa thuộc biến thể Ed25519 | Khóa thuộc biến thể Ed448 |
| Có thể dùng với `Signature.getInstance("Ed25519")`? | Với key Ed25519 tương thích | **Không**, key Ed448 không tự chuyển thành key Ed25519 |

Tên tổng quát `"EdDSA"` cho phép provider hỗ trợ nhiều biến thể tùy key/parameter. Trong **SunEC**, `KeyPairGenerator.getInstance("EdDSA")` khi chưa chọn tham số có mặc định **Ed25519** theo tài liệu provider. Đó là **quy ước của SunEC**, không nên giả định mọi provider dùng mặc định hệt nhau.

Khi cần chỉ rõ tham số cho một bộ sinh khóa tổng quát, một provider có thể hỗ trợ:

```java
import java.security.KeyPairGenerator;
import java.security.spec.NamedParameterSpec;

KeyPairGenerator generator = KeyPairGenerator.getInstance("EdDSA");
generator.initialize(NamedParameterSpec.ED448);
var keyPair = generator.generateKeyPair();
```

Đây là **ví dụ phụ thuộc provider**: không phải bằng chứng mọi provider có hỗ trợ `Ed448` hay chấp nhận `NamedParameterSpec` này. Cách ít mơ hồ hơn trong chương trình theo một giao thức cụ thể là yêu cầu đúng tên `Ed448` ngay từ đầu.

Đặc biệt, `X25519` và `X448` dành cho **key agreement**; không dùng chúng như thuật toán `Signature` chỉ vì tên có số giống EdDSA. EdDSA cũng không phải `ECDSA`.

## 8. Provider selection, key compatibility và tính portable

Giả sử ứng dụng có hai provider:

```text
Provider A: Signature.Ed25519
Provider B: KeyPairGenerator.Ed25519, KeyFactory.Ed25519
```

Cấu hình ấy cho thấy JCA có thể sử dụng các engine do các provider **khác nhau** cung cấp. Nhưng điều đó không bảo đảm provider A có thể dùng mọi private key do provider B sinh, nhất là khi khóa nằm trong phần cứng, được đóng gói theo kiểu riêng hoặc không thể xuất ra.

Một vài trường hợp:

1. **Phần mềm thông thường:** cặp khóa có định dạng chuẩn và các provider hỗ trợ thường có thể tương tác, nhưng vẫn cần thử `initSign`/`initVerify`.
2. **HSM/PKCS#11:** private key có thể chỉ tồn tại trong token; `getEncoded()` có thể trả `null`. Provider ký phải biết cách làm việc với key handle phù hợp, và thao tác ký có thể thất bại nếu token không sẵn sàng.
3. **Chỉ có dịch vụ Signature nhưng thiếu KeyPairGenerator:** chương trình có thể **xác minh** chữ ký bằng một public key có sẵn nếu có cách nạp khóa tương thích; không nhất thiết sinh được khóa mới.
4. **Có KeyPairGenerator nhưng thiếu Signature:** sinh được cặp khóa không chứng minh có thể ký bằng JCA provider đang đăng ký.
5. **Provider bị thay đổi thứ tự hoặc bị loại:** kết quả `getInstance(...)` có thể đổi; không viết logic phụ thuộc tên provider từ một máy phát triển.
6. **Custom runtime/jlink:** cần kiểm tra module bảo mật và provider đóng gói có tồn tại trong runtime cuối cùng.

**Chính sách lựa chọn provider:** JCA có thứ tự ưu tiên provider đã đăng ký, và bản triển khai JDK có thể dùng những chính sách ưu tiên riêng như `jdk.security.provider.preferred`. Do đó, `Security.getProviders()` hữu ích để kiểm kê, nhưng không nhất thiết phản ánh duy nhất cách mà mọi lời gọi `Signature.getInstance` sẽ chọn triển khai. Hãy ghi nhận **provider thật của engine sau khi khởi tạo** khi cần hỗ trợ vận hành.

## 9. Ngoại lệ liên quan đến khả năng hỗ trợ

| Lỗi/ngoại lệ | Hoàn cảnh thường gặp | Cách xử lý |
| --- | --- | --- |
| `NoSuchAlgorithmException` | Không provider nào cung cấp engine/thuật toán, hoặc provider chỉ định không hỗ trợ | Kiểm tra đúng tên chuẩn, provider thực tế, JDK/module và cấu hình |
| `NoSuchProviderException` | Gọi `getInstance("Ed25519", "ProviderName")` nhưng provider đó chưa đăng ký | Kiểm tra tên, cách đăng ký và runtime; không hard-code nếu không cần |
| `InvalidKeyException` | `initSign`/`initVerify` nhận key sai biến thể, sai kiểu hoặc không được provider chấp nhận | Kiểm tra loại key, nguồn key, provider/HSM và protocol |
| `InvalidAlgorithmParameterException` | Bộ tạo khóa không chấp nhận tham số `initialize(...)` | Dùng tham số/biến thể phù hợp và xem khả năng provider |
| `InvalidKeySpecException` | Dùng `KeyFactory` để nhập định dạng key không hợp lệ hoặc không tương thích | Kiểm tra SPKI/PKCS#8, biến thể và định dạng dữ liệu |
| `SignatureException` | Thao tác ký/xác minh không thành công vì trạng thái, dữ liệu hoặc lỗi SPI | Kiểm tra thứ tự `initSign/update/sign` hoặc `initVerify/update/verify` |
| `ProviderException` | Triển khai provider gặp lỗi runtime, thiết bị hoặc trạng thái không phù hợp | Ghi nhận nguyên nhân và kiểm tra provider/token thay vì âm thầm chuyển thuật toán |
| `verify(...) == false` | Chữ ký không khớp public key/thông điệp trong trường hợp verify hợp lệ | **Không** chấp nhận dữ liệu; báo xác minh thất bại theo nghiệp vụ |

`NoSuchAlgorithmException` tại `getInstance` không có nghĩa bản thân thuật toán EdDSA là lỗi thời; nó cho biết **triển khai hoặc policy được yêu cầu không khả dụng trong môi trường đó**. Và `verify=false` **không phải lỗi cài provider** nếu quá trình xác minh đã thực hiện bình thường.

Mọi hệ thống cần xử lý rõ ba trạng thái: **không hỗ trợ thuật toán**, **không chấp nhận khóa/tham số**, và **chữ ký không hợp lệ**. Trộn chúng thành một thông báo chung làm khó chẩn đoán và có thể che những lỗi vận hành quan trọng.

## 10. Checklist kiểm tra JCA/provider trước khi triển khai

- [ ] Chọn thuật toán theo giao thức: **Ed25519 hay Ed448**; không để tên tổng quát `EdDSA` làm thay đổi biến thể ngoài ý muốn.
- [ ] Xác định những JCA engine thật sự cần: `Signature`, `KeyPairGenerator`, `KeyFactory` và những yêu cầu lưu key.
- [ ] Kiểm tra **provider đã đăng ký** trên runtime triển khai bằng `Security.getProviders(...)` hoặc `getAlgorithms(...)`.
- [ ] Thử được `getInstance(...)` cho từng engine; không giả định mọi JDK đều có cùng provider.
- [ ] Thử `generateKeyPair` hoặc nạp **public/private key thật** từ hệ thống lưu trữ.
- [ ] Thử ký/xác minh **cùng dữ liệu byte**; thêm tình huống thông điệp bị sửa phải trả kết quả không hợp lệ.
- [ ] Nếu có HSM, thử trường hợp token ngắt kết nối, key non-exportable và tương thích provider.
- [ ] Kiểm tra deployment image sau khi tối giản bằng `jlink`, cũng như các chính sách compliance/FIPS nếu tổ chức yêu cầu.
- [ ] Quản lý private key an toàn: tránh log, tránh xuất vào file tùy tiện, dùng keystore/HSM theo chính sách.
- [ ] Khi trao đổi khóa và chữ ký qua mạng, thống nhất **thuật toán, byte encoding, format key và protocol** với bên nhận.
- [ ] Có kiểm thử tích hợp ở runtime đích, không chỉ ở máy phát triển.
- [ ] Ghi nhận tên thuật toán/provider/engine và nguyên nhân lỗi phù hợp nhưng **không log private key hay bí mật**.

**Lưu ý bảo mật:** EdDSA là chữ ký số để bảo đảm tính xác thực và toàn vẹn khi public key được tin cậy. Nó **không mã hóa dữ liệu** và không tự xác lập niềm tin đối với một public key nhận từ bên ngoài. Ứng dụng phải có cơ chế phân phối/kiểm chứng public key, danh tính hoặc chứng chỉ riêng.

## 11. Những nhầm lẫn phổ biến

| Nhầm lẫn | Thực tế |
| --- | --- |
| Java 15 có EdDSA tức mọi runtime Java đều ký được Ed448 | Chức năng thực tế phụ thuộc provider/module/chính sách |
| `getInstance("Ed25519")` luôn chọn `SunEC` | JCA có thể chọn provider khác phù hợp và ưu tiên hơn |
| Có `Signature.Ed25519` tức có `KeyPairGenerator.Ed25519` | Hai engine đăng ký dịch vụ độc lập |
| Có tên thuật toán trong danh sách tức mọi private key đều ký được | Provider có thể từ chối key không tương thích hoặc key của HSM khác |
| `Key.getAlgorithm()` luôn trả đúng tên đã yêu cầu lúc tạo generator | Biểu diễn tên có thể dùng tên họ `EdDSA`; không dùng so sánh tên đơn giản để kết luận biến thể |
| `EdDSA`, `ECDSA`, `X25519` là cùng một thuật toán | Chữ ký và key agreement là các giao thức khác nhau |
| Có thể dùng khóa Ed448 cho `Signature("Ed25519")` | Key không cùng biến thể sẽ không tương thích |
| `X509EncodedKeySpec` là public key Ed25519 raw 32 byte | Nó chứa biểu diễn **SubjectPublicKeyInfo**, không phải raw key |
| `PKCS8EncodedKeySpec` có thể áp dụng cho mọi HSM key | Private key phần cứng có thể không export được |
| `verify=false` nghĩa là provider không hỗ trợ thuật toán | Provider đã thực hiện verify; kết quả báo chữ ký không hợp lệ |
| In private key để debug là vô hại | Private key phải được bảo vệ; không xuất hoặc log tùy tiện |

## 12. Bài tập và đáp án

**Tình huống 1.** Một chương trình Java 17 gọi `Signature.getInstance("Ed25519")` thành công, nhưng `KeyPairGenerator.getInstance("Ed25519")` ném `NoSuchAlgorithmException`. Có mâu thuẫn không?

**Tình huống 2.** Hai môi trường dùng cùng code `Signature.getInstance("Ed25519")`, nhưng báo tên provider khác nhau. Chúng có chắc là lỗi không?

**Tình huống 3.** Một hệ thống yêu cầu chuẩn **Ed448**. Nhà phát triển chọn `KeyPairGenerator.getInstance("EdDSA")` mà không truyền tham số và cho rằng chắc chắn nhận được Ed448. Điều gì chưa đúng?

**Tình huống 4.** `verify(signature)` trả `false` sau khi message bị thay đổi. Có nên tự động chuyển sang `Signature.getInstance("EdDSA")` và thử tiếp để tìm một variant khác không?

**Tình huống 5.** Provider HSM hỗ trợ Ed25519 nhưng `privateKey.getEncoded() == null`. Có nhất thiết private key đã hỏng không?

**Đáp án:**

1. Không. `Signature` và `KeyPairGenerator` là các **dịch vụ riêng**. Một provider có thể triển khai chỉ một trong hai hoặc cấu hình chỉ cho phép một loại thao tác.
2. Không. JCA cho phép nhiều provider, thứ tự và chính sách ưu tiên khác nhau; phải thử tương thích thực tế và kiểm tra yêu cầu bảo mật của hệ thống.
3. Không có bảo đảm chung rằng generic `EdDSA` mặc định Ed448. Trong `SunEC`, mặc định generator tổng quát là Ed25519 nếu chưa đặt tham số. Nên gọi tên `Ed448` rõ ràng.
4. Không. Cần dùng đúng thuật toán và public key mà **giao thức đã thỏa thuận**. Chuyển thuật toán tùy tiện khi xác minh thất bại là một lỗi thiết kế bảo mật.
5. Không. Key trong HSM có thể **non-exportable** theo thiết kế. Hãy để provider của HSM thực hiện thao tác ký hoặc dùng API được cho phép, không cố xuất private key.

## Tài liệu tham khảo hiện hành

- [OpenJDK JEP 339 — Edwards-Curve Digital Signature Algorithm (EdDSA)](https://openjdk.org/jeps/339): tính năng EdDSA được đưa vào JDK 15.
- [Oracle Java SE 26 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html): tên chuẩn `EdDSA`, `Ed25519`, `Ed448` theo từng JCA engine.
- [Oracle Java SE 26 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html): provider `SunEC`, các dịch vụ và giới hạn thuật toán.
- [Oracle Java SE 26 — Signature API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html): chọn provider, khởi tạo, ký và xác minh.
- [Oracle Java SE 26 — Security API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Security.html): kiểm kê provider, dịch vụ và algorithm.
- [RFC 8032 — EdDSA](https://www.rfc-editor.org/rfc/rfc8032): đặc tả Ed25519/Ed448 và kích thước chữ ký.