# 8.2 Tạo cặp khóa bằng KeyPairGenerator với kích thước hoặc bộ tham số rõ ràng

Khi tạo khóa bất đối xứng trong Java, điều quan trọng không chỉ là gọi `KeyPairGenerator.generateKeyPair()` mà còn **chủ động xác định thuật toán, kích thước hoặc bộ tham số và nguồn ngẫu nhiên thích hợp**. Những lựa chọn đó chi phối sức mạnh mật mã, khả năng tương thích, tốc độ, định dạng khóa và mục đích sử dụng.

Bài này tập trung vào engine `java.security.KeyPairGenerator` trong Java Cryptography Architecture (JCA): cách khởi tạo **RSA**, **EC/secp256r1**, **Ed25519** và **X25519** với tham số rõ ràng, kiểm tra khóa sau khi sinh, phân biệt khóa ký và khóa trao đổi bí mật, và xử lý những sai sót phổ biến.

## 1. `KeyPairGenerator` là gì?

**Cặp khóa** gồm:

- **Public key (`PublicKey`):** có thể phát cho bên cần xác minh chữ ký, mã hóa theo giao thức phù hợp hoặc tham gia trao đổi khóa.
- **Private key (`PrivateKey`):** phải kiểm soát truy cập nghiêm ngặt; dùng ký, giải mã hoặc thực hiện thỏa thuận khóa tùy thuật toán.
- **`KeyPair`:** đối tượng chứa hai thành phần qua `getPublic()` và `getPrivate()`.

Đối với mật mã khóa công khai, Java phân biệt các engine:

| Engine/API | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `KeyPairGenerator` | Sinh **cặp khóa mới** theo thuật toán/tham số. | `KeyPairGenerator.getInstance("RSA")`. |
| `KeyFactory` | Chuyển đổi một biểu diễn khóa đã có thành đối tượng khóa hoặc ngược lại. | Đọc `X509EncodedKeySpec` và `PKCS8EncodedKeySpec`. |
| `Signature` | Tạo/xác minh chữ ký với khóa thích hợp. | `SHA256withECDSA`, `Ed25519`, `RSASSA-PSS`. |
| `KeyAgreement` | Thỏa thuận bí mật chung bằng private/public key và giao thức tương ứng. | `X25519`. |
| `Cipher` | Mã hóa/giải mã khi thuật toán/phương thức cho phép. | RSA-OAEP trong các trường hợp phù hợp. |
| `KeyGenerator` | Sinh **khóa bí mật đối xứng**, không tạo cặp public/private. | `KeyGenerator.getInstance("AES")`. |

`KeyPairGenerator` **không tự tạo chứng chỉ X.509, không tự đưa khóa vào HSM/KeyStore, không xác minh chủ sở hữu public key và không quyết định cách phân phối khóa**. Đây là những phần riêng của thiết kế bảo mật.

Vòng đời tổng quát:

~~~text
Chọn mục tiêu (ký / trao đổi khóa / mã hóa đúng giao thức)
          |
          v
Chọn thuật toán + security strength + tham số rõ ràng
          |
          v
KeyPairGenerator.getInstance(algorithm)
          |
          v
initialize(keysize, SecureRandom)
     hoặc
initialize(AlgorithmParameterSpec, SecureRandom)
          |
          v
generateKeyPair() -> KeyPair
          |
          +--> PublicKey  -> công bố bằng kênh có kiểm chứng danh tính
          |
          +--> PrivateKey -> quản lý, lưu và kiểm soát truy cập an toàn
~~~

## 2. API thiết yếu: ba cách khởi tạo

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");

// Cách A — chỉ rõ kích thước:
generator.initialize(3072, new SecureRandom());

// Cách B — chỉ rõ bộ tham số chuyên biệt cho thuật toán:
generator.initialize(
    new RSAKeyGenParameterSpec(3072, RSAKeyGenParameterSpec.F4),
    new SecureRandom());

// Sau khi đã chọn một cách khởi tạo:
KeyPair pair = generator.generateKeyPair();
~~~

Đây là **đoạn minh họa API**; mã chạy đầy đủ được trình bày ở các phần sau. Trong chương trình thật, chọn **một chính sách khởi tạo phù hợp**, không cần gọi cả cách A và B trên cùng một generator.

Các overload quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `KeyPairGenerator.getInstance("RSA")` | Tìm dịch vụ `KeyPairGenerator` cho RSA từ các provider JCA phù hợp. |
| `getInstance("RSA", "ProviderName")` | Chỉ định provider theo tên, yêu cầu provider đã đăng ký. |
| `getInstance("RSA", providerObject)` | Chỉ định một đối tượng provider; có thể hoạt động cả khi đối tượng chưa đăng ký. |
| `initialize(int keysize)` | Đặt kích thước **theo ý nghĩa riêng của thuật toán**; nguồn ngẫu nhiên được JCA chọn theo chính sách. |
| `initialize(int keysize, SecureRandom rng)` | Đặt kích thước và nguồn ngẫu nhiên cung cấp. Các tham số khác, nếu cần, có thể do provider quyết định. |
| `initialize(AlgorithmParameterSpec params)` | Khởi tạo bằng **bộ tham số** xác định; JCA cung cấp nguồn ngẫu nhiên mặc định. |
| `initialize(AlgorithmParameterSpec params, SecureRandom rng)` | Chỉ rõ cả tham số và nguồn ngẫu nhiên. |
| `generateKeyPair()` | Tạo cặp mới; gọi lại có thể tạo một cặp mới theo trạng thái/cấu hình hiện có. |
| `getProvider()` | Cho biết provider của generator, hữu ích khi kiểm tra môi trường triển khai. |

Hai lưu ý cốt lõi:

1. **Không gọi `initialize`:** `generateKeyPair()` vẫn có thể hoạt động vì provider phải cung cấp cấu hình mặc định. Tuy nhiên default **có thể khác giữa provider và bản JDK**, nên không nên dựa vào nó khi muốn chứng minh kích thước/bộ tham số của khóa.
2. **Chỉ gọi `initialize(256)`:** số `256` là một metric phụ thuộc thuật toán, **không có nghĩa mọi engine đều chọn cùng đường cong, độ mạnh, công dụng**. Với EC, muốn dùng chính xác `secp256r1` thì truyền tên curve.

`SecureRandom` là API sinh byte khó dự đoán phục vụ mật mã. `new SecureRandom()` là lựa chọn thông dụng trong các ví dụ; không đặt seed từ thời gian/`Random`/PID để “tái hiện” khóa. Khóa production cần nguồn ngẫu nhiên và chính sách vận hành được đánh giá trên nền tảng đang chạy.

## 3. Chọn thuật toán và bộ tham số dựa trên mục đích

| Mục đích | `getInstance(...)` cho KPG | Bộ tham số nên khai báo | Ví dụ engine dùng khóa |
| --- | --- | --- | --- |
| Khóa RSA phục vụ chữ ký/ứng dụng phù hợp | `"RSA"` | `RSAKeyGenParameterSpec(3072, F4)`, hoặc kích thước rõ ràng nếu không cần tùy chỉnh exponent | `Signature`: `RSASSA-PSS` hoặc phương thức được giao thức quy định |
| Chữ ký ECDSA trên đường cong NIST cụ thể | `"EC"` | `ECGenParameterSpec("secp256r1")` | `Signature.getInstance("SHA256withECDSA")` |
| Chữ ký EdDSA (Ed25519) | `"Ed25519"` | `NamedParameterSpec.ED25519` khi muốn nêu rõ tham số | `Signature.getInstance("Ed25519")` |
| Thỏa thuận khóa hiện đại X25519 | `"X25519"` | `NamedParameterSpec.X25519` | `KeyAgreement.getInstance("X25519")` |

**Không so sánh số bit giữa các thuật toán một cách trực tiếp**: RSA 3072 bit, ECDSA P-256 và Ed25519 không có cùng định dạng hay ý nghĩa “độ dài khóa”. Sức mạnh bảo mật ước lượng của chúng phải dựa trên tiêu chuẩn an ninh và tính phù hợp với giao thức, không đơn thuần so 3072 với 256.

Trong Java, việc một thuật toán/curve được hỗ trợ còn phụ thuộc **JDK, provider, chính sách và môi trường phần cứng**. Nếu ứng dụng yêu cầu tính di động, hãy kiểm thử trên môi trường triển khai mục tiêu và ghi nhận provider thực sự được dùng. Tên thuật toán trong ví dụ là các tên API chuẩn/được JDK 17 thông dụng hỗ trợ; không kết luận mọi provider hỗ trợ hết.

### Phân biệt loại khóa qua tính năng

- **RSA key** có thể phù hợp với các giao thức ký, mã hóa hoặc một số giao thức cũ, nhưng phải dùng **transformation/scheme chuẩn** và chính sách hợp lý; không “mã hóa bằng private key” để thay cho chữ ký.
- **EC key** tạo bởi `KeyPairGenerator.getInstance("EC")` với `secp256r1` dùng được cho ECDSA; không mặc định rằng mọi khóa EC của mọi curve đều dùng chung với X25519.
- **Ed25519** dùng **chữ ký số**, không phải ECDH/X25519.
- **X25519** phục vụ **thỏa thuận khóa**, không phải chữ ký. Bí mật chung thô từ `KeyAgreement` thường còn phải qua **KDF và giao thức xác thực** trước khi thành khóa ứng dụng; X25519 một mình không xác thực danh tính đối tác.

## 4. Sinh RSA với kích thước và public exponent rõ ràng

### 4.1. Hai mức chỉ định

Cách đơn giản:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(3072, new SecureRandom());
KeyPair pair = generator.generateKeyPair();
~~~

Cách chặt chẽ hơn khi muốn nêu **public exponent**:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(
    new RSAKeyGenParameterSpec(3072, RSAKeyGenParameterSpec.F4),
    new SecureRandom());
KeyPair pair = generator.generateKeyPair();
~~~

Các đoạn trên là minh họa, không phải tệp Java độc lập.

- `3072` là **modulus size** RSA đo bằng **bit**. RSA-2048 vẫn gặp trong các hệ thống hiện hành, nhưng RSA-3072 cho dư địa bảo mật cao hơn, đổi lại chi phí CPU và kích thước khóa/chữ ký lớn hơn. Số bit được chọn phải theo tuổi thọ bảo mật, yêu cầu tiêu chuẩn và tính tương thích.
- `RSAKeyGenParameterSpec.F4` tương ứng **65537**, public exponent thông dụng. Không tự chọn public exponent kỳ lạ hoặc rất nhỏ vì nghĩ “chạy nhanh hơn”.
- `RSAKeyGenParameterSpec` không phải đối tượng private key; nó chỉ khai báo tham số **đầu vào sinh khóa**.
- **Kích thước modulus không phải kích thước private key mã hóa PKCS#8** và không phải độ dài chữ ký của mọi sơ đồ (RSA signature thường có độ dài bằng modulus khi định dạng chuẩn).
- `generateKeyPair()` dùng ngẫu nhiên để tạo các thành phần bí mật; **không được tái sử dụng private key một cách vô thức cho những nhiệm vụ/giao thức không tương thích**.

### 4.2. Chương trình Java 17+: RSA-3072 và kiểm chứng cặp khóa

Tệp **`RsaParamsDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.RSAKeyGenParameterSpec;

public class RsaParamsDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        RSAKeyGenParameterSpec parameters =
                new RSAKeyGenParameterSpec(3072, RSAKeyGenParameterSpec.F4);
        generator.initialize(parameters, new SecureRandom());
        KeyPair pair = generator.generateKeyPair();

        RSAPublicKey publicKey = (RSAPublicKey) pair.getPublic();
        System.out.println("Algorithm: " + publicKey.getAlgorithm());
        System.out.println("Modulus bits: "
                + publicKey.getModulus().bitLength());
        System.out.println("Public exponent: "
                + publicKey.getPublicExponent());

        byte[] message = "module".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        System.out.println("Signature verifies: "
                + verifier.verify(signature));
    }
}
~~~

Chạy ở thư mục chứa tệp:

~~~bash
javac RsaParamsDemo.java
java RsaParamsDemo
~~~

Đầu ra được kiểm tra:

~~~text
Algorithm: RSA
Modulus bits: 3072
Public exponent: 65537
Signature verifies: true
~~~

Kết quả chứng minh cặp khóa đã được sinh với modulus 3072 bit, public exponent F4, và hai thành phần private/public tương thích để ký/xác minh trong ví dụ. Nó **không chứng minh private key đã được lưu an toàn**, không tạo chứng chỉ và không phải bài kiểm thử toàn diện của một hệ thống PKI.

`SHA256withRSA` ở đây phục vụ kiểm chứng ví dụ nhanh và tương thích. Với thiết kế chữ ký RSA mới, cân nhắc **RSASSA-PSS với `PSSParameterSpec` rõ ràng** theo giao thức được chọn; không tự ý đổi scheme khi trao đổi với hệ thống đã quy định thuật toán khác.

Nếu giao thức cần **RSA-OAEP** để bọc khóa nhỏ, đây là trách nhiệm của `Cipher` với transformation/`OAEPParameterSpec` được chỉ rõ, **không phải nhiệm vụ của `KeyPairGenerator`**. Với dữ liệu lớn, thiết kế hybrid encryption dùng khóa đối xứng/AEAD phù hợp thay vì dùng RSA mã hóa toàn bộ plaintext.

## 5. Sinh khóa EC: chọn đường cong bằng tên, không chỉ bằng số 256

### 5.1. Vì sao `initialize(256)` chưa nói hết cấu hình?

Với `KeyPairGenerator.getInstance("EC")`, lời gọi `initialize(256)` cho biết metric kích thước, nhưng provider quyết định cách ánh xạ sang bộ tham số. Đối với giao thức bắt buộc sử dụng **đường cong NIST P-256**, hãy chỉ định trực tiếp:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
generator.initialize(
    new ECGenParameterSpec("secp256r1"), new SecureRandom());
KeyPair pair = generator.generateKeyPair();
~~~

`"secp256r1"` là tên thông dụng cho đường cong **NIST P-256**; đừng giả định alias như `prime256v1` được mọi provider chấp nhận. Với yêu cầu curve khác (ví dụ `secp384r1`), phải kiểm tra hỗ trợ và khớp giao thức. Không lấy một đối tượng EC ở đường cong A rồi dùng với phía yêu cầu đường cong B.

`ECGenParameterSpec` là bộ tham số dựa vào tên curve, không phải nơi chứa điểm public key hay scalar private key. Khi sinh xong, `ECPublicKey` cho phép đọc các tham số đường cong để kiểm tra. **Field size 256 bit** chỉ là một dấu hiệu, không đủ để chứng minh tên curve đúng nếu không kiểm tra chi tiết tham số/giao thức; chương trình đặt tên curve rõ ngay từ đầu.

### 5.2. Chương trình Java 17+: EC/secp256r1 và ECDSA

Tệp **`EcCurveDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;

public class EcCurveDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
        generator.initialize(
                new ECGenParameterSpec("secp256r1"),
                new SecureRandom());
        KeyPair pair = generator.generateKeyPair();

        ECPublicKey publicKey = (ECPublicKey) pair.getPublic();
        System.out.println("Algorithm: " + publicKey.getAlgorithm());
        System.out.println("Field bits: "
                + publicKey.getParams().getCurve()
                        .getField().getFieldSize());

        byte[] message = "module".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(pair.getPublic());
        verifier.update(message);
        System.out.println("Signature verifies: "
                + verifier.verify(signature));
    }
}
~~~

~~~bash
javac EcCurveDemo.java
java EcCurveDemo
~~~

Stdout:

~~~text
Algorithm: EC
Field bits: 256
Signature verifies: true
~~~

`Signature` sử dụng private key để ký và public key để verify; `KeyPairGenerator` chỉ sinh hai khóa. Chữ ký ECDSA chứa ngẫu nhiên hoặc nonce nội bộ tùy triển khai, nên **không in hoặc giả định byte chữ ký cố định**. Dùng API chữ ký chuẩn, không tự lập trình nonce chữ ký.

Lưu ý cấu hình curve của provider có thể thay đổi khả năng tương thích với HSM/FIPS. Nếu môi trường không hỗ trợ `secp256r1`, đừng tự động chọn curve bất kỳ để “chạy được”; cần quyết định dựa trên yêu cầu bảo mật và đối tác.

## 6. Ed25519 và X25519: `NamedParameterSpec` thay cho một số bit mơ hồ

Với những thuật toán đặt tên cụ thể, Java 17 cung cấp `java.security.spec.NamedParameterSpec`, gồm các hằng:

- `NamedParameterSpec.ED25519` — bộ tham số **Ed25519**, dùng cho chữ ký.
- `NamedParameterSpec.X25519` — bộ tham số **X25519**, dùng cho trao đổi khóa.
- Các hằng khác như `ED448` và `X448` được định nghĩa nhưng chỉ dùng khi provider/giao thức hỗ trợ.

Ví dụ:

~~~java
KeyPairGenerator ed = KeyPairGenerator.getInstance("Ed25519");
ed.initialize(NamedParameterSpec.ED25519, new SecureRandom());
KeyPair signingKeys = ed.generateKeyPair();

KeyPairGenerator x = KeyPairGenerator.getInstance("X25519");
x.initialize(NamedParameterSpec.X25519, new SecureRandom());
KeyPair agreementKeys = x.generateKeyPair();
~~~

Đoạn trên là minh họa API, không phải toàn bộ chương trình. Khi thuật toán đã có tên cụ thể như `"Ed25519"` hay `"X25519"`, provider có thể có default phù hợp nếu không gọi `initialize`; ở đây ta **nêu tham số tường minh** để thể hiện điều kiện mong muốn và kiểm thử provider có hỗ trợ chúng.

**Tránh `initialize(255)`** với ý nghĩ 255 là kích thước tùy ý tương đương RSA `initialize(3072)`. Ed25519 và X25519 xác định cấu trúc theo bộ tham số tên; cách yêu cầu bằng số bit không phải hợp đồng di động giữa các provider.

### Chương trình Java 17+: ký Ed25519 và thỏa thuận X25519

Tệp **`NamedKeysDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.NamedParameterSpec;
import java.util.Arrays;
import javax.crypto.KeyAgreement;

public class NamedKeysDemo {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator ed =
                KeyPairGenerator.getInstance("Ed25519");
        ed.initialize(NamedParameterSpec.ED25519, new SecureRandom());
        KeyPair signingPair = ed.generateKeyPair();

        byte[] data = "module".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(signingPair.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(signingPair.getPublic());
        verifier.update(data);
        System.out.println("Ed25519 signature verifies: "
                + verifier.verify(signature));

        KeyPairGenerator x = KeyPairGenerator.getInstance("X25519");
        x.initialize(NamedParameterSpec.X25519, new SecureRandom());
        KeyPair a = x.generateKeyPair();
        KeyPair b = x.generateKeyPair();

        KeyAgreement sideA = KeyAgreement.getInstance("X25519");
        sideA.init(a.getPrivate());
        sideA.doPhase(b.getPublic(), true);
        byte[] secretA = sideA.generateSecret();

        KeyAgreement sideB = KeyAgreement.getInstance("X25519");
        sideB.init(b.getPrivate());
        sideB.doPhase(a.getPublic(), true);
        byte[] secretB = sideB.generateSecret();

        System.out.println("X25519 secrets equal: "
                + Arrays.equals(secretA, secretB));
        System.out.println("X25519 raw secret bytes: "
                + secretA.length);

        Arrays.fill(secretA, (byte) 0);
        Arrays.fill(secretB, (byte) 0);
    }
}
~~~

~~~bash
javac NamedKeysDemo.java
java NamedKeysDemo
~~~

Stdout:

~~~text
Ed25519 signature verifies: true
X25519 secrets equal: true
X25519 raw secret bytes: 32
~~~

Cả hai phía X25519 có cùng **shared secret thô** nhờ sử dụng private key của mình và public key của bên kia. **Không dùng `secretA` trực tiếp thành khóa AES hoặc session key của một giao thức tự chế**; hệ thống thực cần KDF, liên kết transcript/context, xác thực peer và kiểm tra khả năng chống MITM theo giao thức đã được thẩm định. Demo này không xác thực danh tính bên A hay B và không chứa toàn bộ handshake như TLS.

## 7. Xác minh rằng tham số đã được áp dụng

Một số chỉ số nên kiểm tra sau `generateKeyPair()`:

| Loại khóa | Kiểm tra API | Điều muốn chứng minh |
| --- | --- | --- |
| RSA | `RSAPublicKey.getModulus().bitLength()` | Độ dài modulus thực tế khớp chính sách (ví dụ 3072 bit). |
| RSA | `RSAPublicKey.getPublicExponent()` | Exponent thực tế phù hợp `RSAKeyGenParameterSpec.F4` (65537). |
| EC | `ECPublicKey.getParams()` | Bộ tham số đường cong thực tế phù hợp curve/giao thức mong muốn; field size chỉ là một kiểm tra sơ bộ. |
| Ed25519 | Thuật toán key + phép ký/xác minh `Signature("Ed25519")` | Khóa phục vụ chữ ký đúng cơ chế. |
| X25519 | Phép thỏa thuận hai phía qua `KeyAgreement("X25519")` | Hai key pair có thể tạo cùng secret theo đúng giao thức. |
| Mọi loại | `generator.getProvider().getName()` | Provider được JCA chọn, phục vụ kiểm tra môi trường và policy. |

**Không coi phép thử ký/xác minh một thông điệp là toàn bộ kiểm toán bảo mật khóa.** Nó chỉ kiểm tra tương thích chức năng. Hệ thống còn cần tính đúng đắn của nguồn entropy, xử lý private key, quản lý danh tính public key và vòng đời rotation.

### Phân biệt kích thước bit và mức an toàn

- RSA `3072` là **bit length của modulus**, không tương đương “3072 bit security”.
- EC `secp256r1` có field gần 256 bit; sức mạnh bảo mật ước tính thấp hơn 256 bit vì tính chất bài toán logarit rời rạc.
- Ed25519 có bộ tham số riêng, không biến thành “RSA-255” hay “ECDSA với curve mặc định”.
- X25519 thuộc họ trao đổi khóa; so trực tiếp độ dài shared secret với số bit modulus RSA không giúp chọn thuật toán đúng.

Để bảo vệ một hệ thống có thời hạn dài, cần tham chiếu chính sách tổ chức, tiêu chuẩn được chấp nhận và mức tương thích của các bên. **Không mặc định RSA mạnh hơn EC chỉ vì 3072 lớn hơn 256.**

## 8. Khi nào nên truyền `SecureRandom`?

Hai dạng phổ biến:

~~~java
// Dùng nguồn ngẫu nhiên do JCA lựa chọn:
generator.initialize(3072);

// Truyền nguồn CSPRNG rõ ràng:
generator.initialize(3072, new SecureRandom());
~~~

Nếu cần kiểm toán lựa chọn nguồn entropy, truyền đối tượng `SecureRandom` có thể thể hiện policy rõ hơn. Tuy nhiên **truyền `new SecureRandom()` không tự bảo đảm toàn bộ nền tảng đạt FIPS/hardware-backed**; nếu có yêu cầu cụ thể, phải cấu hình và xác minh provider/cơ chế được phép.

Không làm các việc sau:

- Dùng `java.util.Random` hoặc `Math.random()` để tự tạo private exponent/seed và lắp khóa bằng tay.
- Gọi `random.setSeed(System.currentTimeMillis())` với suy nghĩ tăng độ an toàn; giá trị dự đoán được không cải thiện chất lượng CSPRNG và việc cố làm key generation tái hiện là nguy hiểm.
- Tự nhúng private key vào mã nguồn, config Git hoặc bản ghi log để tiết kiệm bước triển khai.
- Tái sử dụng cùng cặp khóa mà không có chính sách: phân biệt signing key, agreement key, key wrapping, tuổi thọ và key rotation.

`SecureRandom.getInstanceStrong()` có thể phù hợp khi chính sách yêu cầu, nhưng có thể khác theo provider và hệ điều hành, thậm chí có đặc tính chờ entropy không phù hợp đường xử lý request. Không coi nó là lựa chọn bắt buộc cho mọi ứng dụng nếu chưa đánh giá.

## 9. Private key, public key, encoding và KeyStore

### 9.1. Public key không đồng nghĩa danh tính đã được xác minh

Public key thường có thể phân phối công khai. Nhưng nếu ứng dụng lấy public key từ một endpoint không xác thực, đối phương có thể **thay key** và giả mạo danh tính. Vì vậy cần cơ chế chứng chỉ, key pinning, signed metadata, trust store hoặc giao thức xác thực phù hợp. `KeyPairGenerator` chỉ tạo **cặp giá trị mật mã**, không chứng minh ai sở hữu chúng.

### 9.2. Các định dạng thường gặp

- Public key dạng `SubjectPublicKeyInfo` / `X.509`: thường `publicKey.getFormat()` trả `"X.509"` và `getEncoded()` trả bytes theo encoding phù hợp.
- Private key dạng `PKCS#8`: với software key exportable, `privateKey.getFormat()` thường là `"PKCS#8"` và `getEncoded()` có thể cung cấp encoding dạng PKCS#8.
- **Không phải mọi private key đều exportable**. Nếu key nằm trong HSM/token bảo mật, `getEncoded()` có thể trả `null`; cần dùng API/provider/keystore thích hợp.
- Base64/PEM **chỉ mã hóa thành văn bản**, không tự bảo vệ private key; xuất private key dạng base64 hoặc raw PKCS#8 vào log/disk vẫn gây lộ.
- `KeyFactory` dùng để đọc/khôi phục biểu diễn khóa khi chính sách cho phép, với `X509EncodedKeySpec` cho public và `PKCS8EncodedKeySpec` cho private. Đây là thao tác **import/export**, không phải sinh cặp khóa mới.
- `KeyStore` hoặc HSM/KMS giúp quản lý/lưu khóa tùy provider và hệ thống, nhưng khả năng export, certificate chain, password và chính sách sử dụng có yêu cầu riêng.

Trong môi trường cần chứng chỉ TLS/chữ ký doanh nghiệp, quy trình có thể là **sinh private key trong HSM**, tạo certificate signing request (CSR) hoặc định danh khóa rồi nhận chứng chỉ từ CA. Chứng chỉ được cấp là một **đối tượng khác**, không tự xuất hiện sau `generateKeyPair()`.

### 9.3. Vòng đời khóa cần chính sách

1. **Tạo** theo thuật toán và tham số được duyệt; ghi nhận metadata `keyId`, mục đích, thời điểm/phiên bản.
2. **Lưu** private key trong vùng kiểm soát truy cập, hạn chế export, mã hóa at rest và backup theo chính sách.
3. **Phân phối** public key kèm xác minh danh tính/nguồn tin cậy.
4. **Sử dụng** đúng mục đích và algorithm suite, kiểm tra provider/khả năng thao tác.
5. **Xoay vòng** (rotation) và xử lý khóa cũ có bản mã/chữ ký còn cần xác minh; không xóa khóa cũ trước khi kiểm kê phụ thuộc.
6. **Thu hồi/hủy** đúng quy trình, cập nhật chứng chỉ/khóa tin cậy và trạng thái truy cập; không chỉ loại bỏ reference trong code.

**Không log nội dung private key**, kể cả trong tình huống “debug tạm” hoặc gửi vào hệ thống theo dõi lỗi. Với demo Java, tốt nhất chỉ in thuật toán và các thuộc tính **public** có thể kiểm chứng.

## 10. Provider, khả năng tương thích và lỗi thường gặp

### 10.1. Provider quyết định những gì?

`getInstance("EC")` yêu cầu JCA lấy một engine theo tên. `initialize(new ECGenParameterSpec("secp256r1"))` yêu cầu engine dùng curve cụ thể. Một provider có thể hỗ trợ thuật toán `"EC"` nhưng không hỗ trợ curve cần thiết.

Trong ứng dụng phổ thông, để JCA tự chọn provider thường tăng tính di động. Nếu hệ thống phải sinh khóa **trong HSM/PKCS#11 hoặc provider tuân thủ chính sách cụ thể**, hãy chỉ định/configure provider theo thiết kế và kiểm tra private key được tạo tại đúng nơi. Chỉ định provider theo tên chưa tự đảm bảo private key không thể export; điều đó phụ thuộc triển khai và cấu hình thực tế.

`KeyPairGenerator.getInstance("RSA", "SomeProvider")` dùng **đúng provider đã đăng ký** theo tên; nếu tên không tồn tại sẽ có `NoSuchProviderException`. Không âm thầm fallback sang software provider nếu policy yêu cầu HSM.

### 10.2. Bảng lỗi và cách xử lý

| Vấn đề | Biểu hiện thường gặp | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Thuật toán keygen không có | `NoSuchAlgorithmException` từ `getInstance` | Kiểm tra tên thuật toán, bản JDK và provider được cài. |
| Chỉ định provider theo tên không có | `NoSuchProviderException` | Kiểm tra đăng ký provider, chính sách Java security và tên chính xác. |
| `initialize(int)` có keysize sai/không hỗ trợ | `InvalidParameterException` | Kiểm tra kích thước được provider/thuật toán hỗ trợ. |
| `initialize(AlgorithmParameterSpec)` không phù hợp | `InvalidAlgorithmParameterException` | Dùng đúng loại spec, curve name và cấu hình nhà cung cấp. |
| Đã tạo `GCMParameterSpec` để khởi tạo `KeyPairGenerator` | Không phải loại tham số phù hợp; có thể bị từ chối | GCM là tham số cho mã hóa đối xứng, không phải sinh cặp RSA/EC. |
| `initialize(256)` nhưng đối tác đòi `secp256r1` | Provider có thể chọn curve khác hoặc không hỗ trợ | Dùng `ECGenParameterSpec("secp256r1")`. |
| `initialize(3072)` cho `"Ed25519"` | Metric không tương thích/không hỗ trợ | Dùng `NamedParameterSpec.ED25519` hoặc default được quy định. |
| RSA 1024 bit cho dữ liệu mới | Không đáp ứng chuẩn an ninh hiện đại phổ biến | Chọn RSA 2048/3072+ theo policy; cân nhắc chi phí và thời hạn. |
| Tạo khóa X25519 rồi đưa vào `Signature` | Sai mục đích thuật toán | Dùng Ed25519 cho chữ ký, X25519 cho key agreement. |
| Log private key hay lưu base64 không mã hóa | Có thể lộ private key | Dùng keystore/HSM và bảo vệ theo policy, không log secret. |
| Dùng public key tải từ nguồn chưa tin cậy | Có thể bị MITM hoặc thay thế khóa | Xác minh danh tính và nguồn tin cậy public key/chứng chỉ. |
| `getEncoded()` trả `null` | Key có thể không export được | Không ép cast/đọc raw key; dùng provider/HSM API theo mục đích. |
| `KeyPairGenerator` được dùng đồng thời ở nhiều thread | Engine có state, không nên dựa vào thread safety | Tạo generator riêng theo operation/worker hoặc đồng bộ đúng cách. |
| Tự chọn provider fallback sau lỗi | Có thể rời khỏi HSM/FIPS hoặc sai policy | Quản lý lỗi rõ ràng, không lặng lẽ thay provider. |

Không bắt toàn bộ `Exception` rồi chuyển sang thuật toán/kích thước yếu hơn chỉ để thành công. Các hạn chế provider và security policy là điều kiện vận hành cần được xử lý bằng cấu hình/quy trình, không phải được vượt qua bằng fallback ngầm.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Tạo `KeyPairGenerator.getInstance("EC")` rồi `initialize(256)` đã chứng minh chắc chắn khóa dùng `secp256r1` chưa?

**Đáp án:** **Chưa.** Số 256 là kích thước thuật toán định nghĩa; bộ tham số có thể là mặc định provider. Muốn yêu cầu curve cụ thể, dùng `ECGenParameterSpec("secp256r1")` và kiểm tra khóa sinh ra.

**Câu 2.** Với RSA, `new RSAKeyGenParameterSpec(3072, RSAKeyGenParameterSpec.F4)` xác định những gì?

**Đáp án:** Modulus 3072 bit và public exponent 65537. Bộ tham số không chứa private key, không tự sinh cặp.

**Câu 3.** Khóa có `getAlgorithm()` trả `"EC"` và field size 256 có đủ để chứng minh đúng curve và mục đích không?

**Đáp án:** Chưa đủ. Cần kiểm tra bộ tham số curve thực và giao thức dùng khóa; field size một mình không xác minh danh tính curve hoặc yêu cầu sử dụng.

**Câu 4.** Có thể lấy `KeyPair` Ed25519 và dùng ngay với `KeyAgreement.getInstance("X25519")` không?

**Đáp án:** Không. Ed25519 là chữ ký, X25519 là key agreement; tham số, key format và cách dùng khác nhau.

**Câu 5.** Hai phía X25519 tính ra cùng 32 byte secret. Giao thức đã chống man-in-the-middle chưa?

**Đáp án:** **Chưa.** Chỉ chứng minh phép toán agreement hoạt động; cần xác thực peer, transcript/KDF và giao thức đầy đủ.

**Câu 6.** Nếu không gọi `initialize`, `KeyPairGenerator.generateKeyPair()` sẽ luôn tạo RSA-3072?

**Đáp án:** Không. Mặc định do provider xác định; muốn chính sách kích thước rõ ràng phải gọi `initialize` thích hợp.

**Câu 7.** Vì sao `PublicKey` được công bố nhưng vẫn phải xác minh nguồn?

**Đáp án:** Public key không bí mật, nhưng **danh tính gắn với public key** là điều phải xác minh. Khóa bị tráo có thể dẫn đến giả mạo hoặc MITM.

**Câu 8.** `privateKey.getEncoded()` trả mảng byte thì có thể in Base64 để debug không?

**Đáp án:** Không. Base64 không mã hóa bí mật; đó có thể là PKCS#8 chứa private key. Không log hoặc công bố giá trị này.

**Câu 9.** Nguồn `SecureRandom` đã đủ để kết luận keygen đáp ứng FIPS/HSM chưa?

**Đáp án:** Chưa. Cần kiểm tra provider, cơ chế phần cứng, thông số, chính sách triển khai và bằng chứng vận hành liên quan.

## 12. Tài liệu tham khảo

- [Java SE 17 — KeyPairGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPairGenerator.html): overload `getInstance`, khởi tạo theo kích thước/bộ tham số, mặc định provider.
- [Java SE 17 — KeyPair](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyPair.html): biểu diễn cặp `PrivateKey` và `PublicKey`.
- [Java SE 17 — RSAKeyGenParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/RSAKeyGenParameterSpec.html): modulus size, public exponent và `F4`.
- [Java SE 17 — ECGenParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/ECGenParameterSpec.html): tham số đường cong EC đặt tên.
- [Java SE 17 — NamedParameterSpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/NamedParameterSpec.html): `ED25519`, `X25519` và các tham số đặt tên.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn ngẫu nhiên mật mã.
- [Java SE 17 — KeyAgreement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyAgreement.html): trao đổi bí mật bằng khóa công khai.
- [JDK 17 Providers Documentation](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): hỗ trợ, hạn chế và default theo provider.
