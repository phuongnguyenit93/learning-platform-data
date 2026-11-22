# InvalidKeyException và lỗi không hỗ trợ thuật toán khi ký, xác minh trong Java 15+

## 1. Tổng quan: thuật toán không tồn tại khác với khóa không hợp lệ

Trong nhóm **Ký và xác minh**, ứng dụng Java cần phân biệt lỗi chọn thuật toán với lỗi chọn khóa. API chuẩn `java.security.Signature` (JCA) yêu cầu chương trình chọn **thuật toán chữ ký** rồi cung cấp **khóa riêng** để ký hoặc **khóa công khai** để xác minh:

~~~java
Signature signer = Signature.getInstance("Ed25519");
signer.initSign(privateKey);

Signature verifier = Signature.getInstance("Ed25519");
verifier.initVerify(publicKey);
~~~

Đây là hai đoạn minh họa, giả sử các biến khóa đã được khai báo. Với JDK Java 15 trở lên, **Ed25519/EdDSA** là thuật toán được hỗ trợ chính thức (JEP 339), vẫn là lựa chọn hợp lệ trong Java hiện đại.

**Khác biệt quan trọng nhất:**

- **`NoSuchAlgorithmException`**: `getInstance(...)` không tìm được triển khai thuật toán trong tập provider sẵn có cho loại dịch vụ được yêu cầu. Vấn đề xảy ra ở bước **lựa chọn thuật toán**.
- **`InvalidKeyException`**: thuật toán đã được chọn, nhưng một khóa đưa vào `initSign(...)` hoặc `initVerify(...)` **không thể được sử dụng** với thuật toán và provider đó. Vấn đề xảy ra ở bước **khởi tạo bằng khóa**.

Không thể chữa `NoSuchAlgorithmException` chỉ bằng cách đưa vào khóa khác. Ngược lại, dùng khóa RSA cho `Signature.getInstance("Ed25519")` **không có nghĩa Java thiếu Ed25519**: đó là khóa sai họ thuật toán và bị `InvalidKeyException`.

Trong bài này, mọi ví dụ dùng API Java SE hiện hành và chương trình chạy độc lập ở Java 17+, không sử dụng thuật toán hoặc API đã bị coi là lỗi thời.

## 2. Quy trình ký và xác minh chuẩn

~~~text
                     KeyPairGenerator("Ed25519")
                                 |
                          KeyPair tạo mới
                            /           \
                     PrivateKey        PublicKey
                         |                 |
Bên ký: Signature("Ed25519")       Bên nhận: Signature("Ed25519")
         initSign(privateKey)                initVerify(publicKey)
         update(messageBytes)                update(messageBytes)
         sign() -> byte[] chữ ký             verify(signatureBytes) -> boolean
~~~

Mỗi phương thức chịu trách nhiệm riêng:

| API | Chức năng | Lỗi cần phân biệt |
| --- | --- | --- |
| `KeyPairGenerator.getInstance("Ed25519")` | Tìm dịch vụ sinh khóa theo thuật toán | `NoSuchAlgorithmException` nếu không có triển khai |
| `KeyPairGenerator.generateKeyPair()` | Sinh `PrivateKey` và `PublicKey` cùng một cặp | Lỗi triển khai/provider cụ thể nếu sinh khóa thất bại |
| `Signature.getInstance("Ed25519")` | Tìm dịch vụ chữ ký | `NoSuchAlgorithmException` nếu không có triển khai |
| `Signature.initSign(privateKey)` | Chọn chế độ ký và kiểm tra private key | `InvalidKeyException` với khóa không dùng được |
| `Signature.initVerify(publicKey)` | Chọn chế độ xác minh và kiểm tra public key | `InvalidKeyException` với khóa không dùng được |
| `Signature.update(byte[])` | Cấp dữ liệu byte của thông điệp | `SignatureException` nếu trạng thái thao tác không hợp lệ |
| `Signature.sign()` | Xuất chữ ký nhị phân | `SignatureException` khi ký không thể hoàn tất |
| `Signature.verify(byte[])` | Kiểm tra chữ ký trên dữ liệu đã cấp | `true`, `false` hoặc `SignatureException` theo tình huống |

**`Signature` là đối tượng có trạng thái.** Không dùng instance chưa khởi tạo để gọi `update`; không coi `initSign` là tương đương `initVerify`. Mỗi lần ký/xác minh nên dùng instance được khởi tạo phù hợp và không chia sẻ trạng thái tùy tiện giữa các thread.

### Dữ liệu được ký là byte[], không phải khái niệm chuỗi

~~~java
byte[] data = "Đơn hàng 42".getBytes(StandardCharsets.UTF_8);
~~~

Phía xác minh phải dùng **chính xác các byte được ký**. Thay `42` bằng `43` làm chữ ký không hợp lệ dù khóa vẫn đúng. Tương tự, CRLF khác LF, Unicode NFC khác NFD hoặc JSON được serialize khác nhau có thể tạo chuỗi byte khác nhau. Không gộp lỗi xác minh dữ liệu vào nhóm lỗi khóa.

## 3. Khi nào gặp InvalidKeyException?

### 3.1. Khóa RSA không dùng với thuật toán Ed25519

~~~java
KeyPairGenerator rsaGen = KeyPairGenerator.getInstance("RSA");
rsaGen.initialize(2048);
KeyPair rsa = rsaGen.generateKeyPair();

Signature edSigner = Signature.getInstance("Ed25519");
edSigner.initSign(rsa.getPrivate()); // InvalidKeyException
~~~

Hoặc:

~~~java
Signature edVerifier = Signature.getInstance("Ed25519");
edVerifier.initVerify(rsa.getPublic()); // InvalidKeyException
~~~

Ở cả hai ví dụ, **Ed25519 có sẵn**, nhưng khóa RSA không phù hợp với cách ký và xác minh Ed25519. Trong chương trình đầy đủ, hai tình huống tương ứng được kiểm thử là `rsaPrivateRejected` và `rsaPublicRejected`.

Các nguyên nhân khác khiến provider từ chối khóa có thể gồm định dạng không được hỗ trợ, thông số khóa hoặc chính sách provider không tương thích. Mỗi provider có thể đưa ra `getMessage()` khác nhau; không nên khẳng định mọi `InvalidKeyException` đều có cùng thông điệp hay cùng nguyên nhân kỹ thuật.

**Phân biệt lỗi biên dịch và lỗi runtime:** `initSign` có tham số kiểu `PrivateKey`; khi truyền một biến chỉ có kiểu `PublicKey` vào `initSign(...)`, mã thường **không biên dịch được** vì sai kiểu tham số. Đó không phải trường hợp Java tự chạy rồi ném `InvalidKeyException`. Muốn kiểm thử `InvalidKeyException`, hãy truyền **đúng loại Java về mặt chữ ký phương thức** nhưng không tương thích về mật mã, ví dụ RSA `PrivateKey` vào bộ ký Ed25519.

### 3.2. Public key cùng thuật toán nhưng khác cặp: thường không ném InvalidKeyException

Giả sử thông điệp được ký bằng Ed25519 private key A, còn bên nhận dùng một **Ed25519 public key B hợp lệ**. `initVerify(publicKeyB)` có thể thành công vì khóa có định dạng và thuật toán hợp lệ. Tuy nhiên, `verify(signatureBytes)` trên thông điệp gốc vẫn trả `false` vì khóa B không thuộc cùng cặp với khóa đã ký.

| Trường hợp | Kết quả cần mong đợi |
| --- | --- |
| Khóa RSA trong `Signature("Ed25519")` | Bị từ chối ngay khi `initSign`/`initVerify` bằng `InvalidKeyException` |
| Ed25519 public key đúng cặp khóa ký | `initVerify` thành công, `verify` trả `true` |
| Ed25519 public key hợp lệ nhưng từ cặp khác | `initVerify` thường thành công, `verify` trả `false` |
| Ed25519 private key hợp lệ ký một message, xác minh trên message đã đổi một byte | `initVerify` thành công với public key đúng, `verify` trả `false` |

Vì vậy, **`false` từ `verify` không tự chứng minh khóa sai định dạng**. Nó có thể do sai public key tương ứng, thông điệp đã thay đổi, signature không đúng hoặc sự không khớp thuật toán/giao thức.

### 3.3. Kiểm tra khóa ở đâu?

- `key.getAlgorithm()` cho một dấu hiệu về thuật toán khóa, nhưng **không đủ xác nhận provider sẽ chấp nhận khóa**.
- `KeyFactory` và `KeyStore` giúp quản lý hoặc tái tạo khóa theo kiểu được hỗ trợ. Một khóa được khôi phục thành công chưa đảm bảo ứng dụng đã **tin cậy danh tính** gắn với khóa ấy.
- Khi dùng HSM/KMS hoặc provider chuyên biệt, khóa có thể không xuất được và có giới hạn sử dụng. Chú ý cấu hình provider, loại khóa và chính sách của hệ thống.
- Không in private key trong log để gỡ lỗi. Ghi tên thuật toán, key identifier không nhạy cảm, bước API phát sinh lỗi và loại ngoại lệ là phương án an toàn hơn.

## 4. Khi nào gặp NoSuchAlgorithmException?

### 4.1. Không tìm thấy thuật toán chữ ký

~~~java
Signature.getInstance("NOT_A_REAL_SIGNATURE_2026");
// NoSuchAlgorithmException
~~~

`Signature.getInstance(...)` tìm nhà cung cấp có triển khai **dịch vụ Signature** với tên thuật toán được yêu cầu. Tên trong ví dụ trên cố ý không phải thuật toán chuẩn.

Nếu `Signature.getInstance("Ed25519")` không thành công trong môi trường triển khai, cần kiểm tra JDK, các provider đã cài và được bật, tên thuật toán và chính sách cấu hình. **Đừng tự động hạ cấp sang một thuật toán yếu** chỉ để chương trình không ném ngoại lệ; điều đó tạo nguy cơ *algorithm downgrade* hoặc không tương thích với giao thức.

### 4.2. Tên thuật toán còn gắn với loại dịch vụ JCA

~~~java
KeyPairGenerator.getInstance("NOT_A_REAL_KEYGEN_2026");
// NoSuchAlgorithmException
~~~

Không nên suy luận rằng một tên thuật toán có sẵn trong một service thì cũng có sẵn ở mọi service JCA. Chữ ký, sinh khóa, `KeyFactory`, `Cipher` và các service khác có đăng ký provider riêng. Tương tự, `Signature.getInstance("Ed25519")` không kiểm tra tính hợp lệ của **một khóa cụ thể** cho tới khi gọi `initSign`/`initVerify`.

### 4.3. NoSuchProviderException khác NoSuchAlgorithmException

~~~java
Signature.getInstance("Ed25519", "NOT_A_REAL_PROVIDER_2026");
// NoSuchProviderException
~~~

Với overload nhận **tên provider**, nếu provider đó không tồn tại, Java ném `NoSuchProviderException`. Nếu provider **có tồn tại** nhưng không cung cấp thuật toán chữ ký được yêu cầu, kết quả là `NoSuchAlgorithmException`.

| Yêu cầu | Trạng thái JCA | Lỗi |
| --- | --- | --- |
| `getInstance("Ed25519")` | Không có provider cài đặt dịch vụ Ed25519 Signature | `NoSuchAlgorithmException` |
| `getInstance("Ed25519", "MissingProvider")` | Không có provider mang tên được yêu cầu | `NoSuchProviderException` |
| `getInstance("Ed25519", "InstalledProvider")` | Provider tồn tại nhưng thiếu dịch vụ Ed25519 Signature | `NoSuchAlgorithmException` |
| `getInstance("Ed25519")` | Có provider hỗ trợ | Thành công, **chưa kiểm tra khóa** |

Không hard-code provider name nếu không có lý do yêu cầu triển khai cụ thể. Trường hợp cần cố định provider, phải xác minh cấu hình đó có sẵn trong môi trường chạy thật.

## 5. Đừng nhầm lỗi khóa với key specification, tham số hay chữ ký

### InvalidKeySpecException ở bước tái tạo khóa

`KeyFactory.getInstance("Ed25519").generatePublic(...)` nhận một `KeySpec` tương thích. Với public key được xuất qua `getEncoded()`, lựa chọn chuẩn thường là `X509EncodedKeySpec` tương ứng **SubjectPublicKeyInfo (SPKI)**:

~~~java
String encoded = Base64.getEncoder()
        .encodeToString(publicKey.getEncoded());

byte[] transmittedBytes = Base64.getDecoder().decode(encoded);
PublicKey decoded = KeyFactory.getInstance("Ed25519")
        .generatePublic(new X509EncodedKeySpec(transmittedBytes));
~~~

Đây là ví dụ minh họa; `publicKey` giả định là Ed25519 public key có thể xuất. `X509EncodedKeySpec` yêu cầu bytes SPKI đầy đủ, **không phải chỉ 32 raw bytes public key Ed25519**. Nếu truyền bytes không đúng cấu trúc, `generatePublic` ném **`InvalidKeySpecException`**. Sau khi đã có một `PublicKey`, `Signature.initVerify` lại có thể ném **`InvalidKeyException`** nếu khóa không dùng được với phép xác minh.

Bảng chuỗi xử lý:

| Bước | Dữ liệu đầu vào | Lỗi thường gặp |
| --- | --- | --- |
| `Base64.getDecoder().decode(text)` | Văn bản Base64 | `IllegalArgumentException` nếu Base64 sai cú pháp |
| `KeyFactory.generatePublic(X509EncodedKeySpec)` | Bytes biểu diễn SPKI | `InvalidKeySpecException` nếu spec/encoding không hợp lệ |
| `Signature.initVerify(publicKey)` | Đối tượng khóa | `InvalidKeyException` nếu khóa không được provider chấp nhận |
| `Signature.verify(signatureBytes)` | Bytes chữ ký trên dữ liệu đã cấp | `false` hoặc `SignatureException` tùy kết quả/xử lý |

**Bảo mật:** Base64 **không xác thực nguồn khóa**. Nếu attacker có thể gửi cả thông điệp, chữ ký và public key giả rồi ứng dụng tự tin dùng public key đó, việc `verify` trả `true` không có ý nghĩa xác nhận danh tính. Cần cơ chế cung cấp và kiểm soát public key đáng tin cậy (chứng chỉ, pinned key, kho cấu hình khóa xác thực, v.v.).

### InvalidAlgorithmParameterException không đồng nghĩa thiếu thuật toán

Một số API nhận tham số thuật toán như `AlgorithmParameterSpec`. Khi thuật toán có nhưng **tham số không hợp lệ**, các API tương ứng có thể ném `InvalidAlgorithmParameterException`. Đừng đổi hướng chẩn đoán thành `NoSuchAlgorithmException` chỉ vì lỗi có chữ “Algorithm”.

### SignatureException khi gọi sai trạng thái hoặc chữ ký hỏng

`Signature` cần `initSign` hay `initVerify` trước `update` và `sign`/`verify`. Nếu dùng sai trình tự, `SignatureException` có thể xảy ra. Tương tự, chữ ký có độ dài/encoding không hợp lệ có thể dẫn đến `SignatureException` thay vì `false`.

Trong kiểm thử với provider Ed25519 của JDK 24, một chữ ký chỉ có **ba byte** đã bị `Signature.verify` từ chối bằng `SignatureException`. Provider khác có thể báo khác ở một số dữ liệu lỗi; nghiệp vụ phải **từ chối cả kết quả `false` và chữ ký không thể xử lý**, không coi lỗi là thành công.

## 6. Chương trình Java 17+ có kiểm tra ngoại lệ đúng loại

Chương trình sau dùng một Ed25519 key pair hợp lệ và một RSA key pair (RSA chỉ phục vụ kiểm thử khóa sai thuật toán). Hàm `expect` xác nhận **đúng loại ngoại lệ**; nếu không có ngoại lệ hoặc nhận sai loại, nó ném `AssertionError`.

Tạo file **`SigningErrorDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.InvalidKeyException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.security.NoSuchProviderException;
import java.security.PublicKey;
import java.security.Signature;
import java.security.SignatureException;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

public class SigningErrorDemo {
    private static int passed = 0;

    @FunctionalInterface
    interface CheckedAction { void run() throws Exception; }

    private static void check(String label, boolean condition) {
        if (!condition) throw new AssertionError(label);
        passed++;
        System.out.println(label + "=PASS");
    }

    private static void expect(String label,
            Class<? extends Exception> expected, CheckedAction action) throws Exception {
        try {
            action.run();
        } catch (Exception ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(label + ": unexpected " + ex.getClass().getName(), ex);
            }
            passed++;
            System.out.println(label + "=" + expected.getSimpleName());
            return;
        }
        throw new AssertionError(label + ": expected " + expected.getSimpleName());
    }

    private static boolean verify(byte[] data, byte[] signature, PublicKey publicKey)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(publicKey);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        byte[] data = "Đơn hàng 42".getBytes(StandardCharsets.UTF_8);
        KeyPairGenerator edGenerator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair ed = edGenerator.generateKeyPair();

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(ed.getPrivate());
        signer.update(data);
        byte[] signature = signer.sign();

        check("validSignature", verify(data, signature, ed.getPublic()));
        byte[] changed = "Đơn hàng 43".getBytes(StandardCharsets.UTF_8);
        check("changedMessageRejected", !verify(changed, signature, ed.getPublic()));
        check("otherEdKeyRejected", !verify(data, signature,
                edGenerator.generateKeyPair().getPublic()));

        String encodedPublic = Base64.getEncoder().encodeToString(ed.getPublic().getEncoded());
        PublicKey decodedPublic = KeyFactory.getInstance("Ed25519")
                .generatePublic(new X509EncodedKeySpec(Base64.getDecoder().decode(encodedPublic)));
        check("decodedPublicKeyWorks", verify(data, signature, decodedPublic));

        KeyPairGenerator rsaGen = KeyPairGenerator.getInstance("RSA");
        rsaGen.initialize(2048);
        KeyPair rsa = rsaGen.generateKeyPair();

        expect("rsaPrivateRejected", InvalidKeyException.class, () -> {
            Signature wrong = Signature.getInstance("Ed25519");
            wrong.initSign(rsa.getPrivate());
        });
        expect("rsaPublicRejected", InvalidKeyException.class, () -> {
            Signature wrong = Signature.getInstance("Ed25519");
            wrong.initVerify(rsa.getPublic());
        });
        expect("missingSignatureAlgorithm", NoSuchAlgorithmException.class,
                () -> Signature.getInstance("NOT_A_REAL_SIGNATURE_2026"));
        expect("missingKeyGeneratorAlgorithm", NoSuchAlgorithmException.class,
                () -> KeyPairGenerator.getInstance("NOT_A_REAL_KEYGEN_2026"));
        expect("missingProvider", NoSuchProviderException.class,
                () -> Signature.getInstance("Ed25519", "NOT_A_REAL_PROVIDER_2026"));
        expect("badPublicKeyEncoding", InvalidKeySpecException.class,
                () -> KeyFactory.getInstance("Ed25519")
                        .generatePublic(new X509EncodedKeySpec(new byte[]{1, 2, 3})));
        expect("updateBeforeInit", SignatureException.class, () -> {
            Signature state = Signature.getInstance("Ed25519");
            state.update(data);
        });
        expect("malformedSignatureLength", SignatureException.class, () -> {
            Signature verifier = Signature.getInstance("Ed25519");
            verifier.initVerify(ed.getPublic());
            verifier.update(data);
            verifier.verify(new byte[]{1, 2, 3});
        });

        System.out.println("TOTAL_PASS=" + passed);
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 SigningErrorDemo.java
java SigningErrorDemo
~~~

**Stdout chính xác** (đã kiểm tra trên JDK 24 sau khi biên dịch `--release 17`):

~~~text
validSignature=PASS
changedMessageRejected=PASS
otherEdKeyRejected=PASS
decodedPublicKeyWorks=PASS
rsaPrivateRejected=InvalidKeyException
rsaPublicRejected=InvalidKeyException
missingSignatureAlgorithm=NoSuchAlgorithmException
missingKeyGeneratorAlgorithm=NoSuchAlgorithmException
missingProvider=NoSuchProviderException
badPublicKeyEncoding=InvalidKeySpecException
updateBeforeInit=SignatureException
malformedSignatureLength=SignatureException
TOTAL_PASS=12
~~~

### Ý nghĩa từng phép thử

1. **`validSignature`:** khóa riêng và khóa công khai đúng cặp; Ed25519 ký và xác minh thành công.
2. **`changedMessageRejected`:** chỉ đổi dữ liệu từ `42` sang `43` mà giữ chữ ký thì xác minh bị từ chối.
3. **`otherEdKeyRejected`:** public key Ed25519 hợp lệ từ một cặp khóa khác không xác minh được chữ ký.
4. **`decodedPublicKeyWorks`:** mảng byte SPKI của public key, sau truyền bằng Base64 và tái tạo bằng `KeyFactory`, vẫn xác minh được.
5. **`rsaPrivateRejected`:** Ed25519 `initSign` từ chối RSA private key với `InvalidKeyException`.
6. **`rsaPublicRejected`:** Ed25519 `initVerify` từ chối RSA public key với `InvalidKeyException`.
7. **`missingSignatureAlgorithm`:** `Signature.getInstance` với thuật toán giả ném `NoSuchAlgorithmException`.
8. **`missingKeyGeneratorAlgorithm`:** `KeyPairGenerator.getInstance` với thuật toán giả cũng ném `NoSuchAlgorithmException`.
9. **`missingProvider`:** chỉ định provider không tồn tại ném `NoSuchProviderException`.
10. **`badPublicKeyEncoding`:** bytes không phải SPKI Ed25519 hợp lệ ném `InvalidKeySpecException` ở bước tái tạo khóa.
11. **`updateBeforeInit`:** gọi `Signature.update` trước `initSign`/`initVerify` ném `SignatureException`.
12. **`malformedSignatureLength`:** chữ ký Ed25519 có độ dài không hợp lệ bị provider từ chối bằng `SignatureException`.

Chương trình cố ý **không in private key hoặc signature ngẫu nhiên**, và không phụ thuộc `-ea`, nên kết quả mong đợi có thể đọc bằng mắt. Với provider khác, một số thông điệp/chi tiết lỗi khi dữ liệu nhị phân sai có thể khác; hãy chạy bài trên **JDK/provider của dự án**.

## 7. Chẩn đoán theo vị trí API, không theo phỏng đoán

Khi lỗi mật mã xuất hiện, nên tra theo thứ tự:

| Bước | Câu hỏi | Hành động |
| --- | --- | --- |
| **1. Chọn thuật toán** | `Signature.getInstance(algorithm)` có `NoSuchAlgorithmException`? | Kiểm tra service type, tên thuật toán chuẩn, provider đã đăng ký, JDK và chính sách bảo mật. |
| **2. Chọn provider** | Overload có provider ném `NoSuchProviderException`? | Kiểm tra tên provider và cách cài/đăng ký; không tự tin rằng provider luôn tồn tại. |
| **3. Đọc/giải mã khóa** | `KeyFactory.generatePublic` ném `InvalidKeySpecException`? | Kiểm tra Base64, SPKI và định dạng bytes trước khi xây khóa. |
| **4. Khởi tạo bằng khóa** | `initSign`/`initVerify` ném `InvalidKeyException`? | Kiểm tra loại khóa, thuật toán, provider và điều kiện sử dụng khóa. |
| **5. Xử lý dữ liệu** | `update`/`verify` ném `SignatureException`? | Kiểm tra chế độ đã init, cấu trúc chữ ký, trình tự cập nhật và provider. |
| **6. Chữ ký không khớp** | `verify` trả `false`? | So sánh byte[] được ký/xác minh, public key tin cậy, phiên bản khóa và giao thức; **từ chối** thông điệp. |

Một nhánh xử lý lỗi (chỉ là đoạn minh họa, không phải file độc lập):

~~~java
try {
    Signature verifier = Signature.getInstance("Ed25519");
    verifier.initVerify(trustedPublicKey);
    verifier.update(payloadBytes);
    boolean accepted = verifier.verify(signatureBytes);
    // accepted=false: từ chối thông điệp.
} catch (NoSuchAlgorithmException ex) {
    // Runtime không cung cấp thuật toán chữ ký được yêu cầu.
} catch (InvalidKeyException ex) {
    // Public key không dùng được cho thuật toán và provider.
} catch (SignatureException ex) {
    // Sai trạng thái/định dạng chữ ký hoặc lỗi xử lý chữ ký.
}
~~~

Đoạn này giả sử `trustedPublicKey`, `payloadBytes` và `signatureBytes` đã có. Trong ứng dụng thật, cần xử lý rõ ràng theo chính sách lỗi (từ chối, log an toàn, cảnh báo vận hành); **không được mặc định chấp nhận yêu cầu ở bất kỳ nhánh catch nào**.

## 8. Quy tắc bảo mật và lỗi phổ biến

- **Không fallback sang thuật toán yếu hơn vì `NoSuchAlgorithmException`.** Thuật toán phải được thỏa thuận trong giao thức và được cho phép theo chính sách; việc “thử cho tới khi chạy được” có thể gây lỗi downgrade.
- **Không dùng `InvalidKeyException` như dấu hiệu chữ ký đã bị giả mạo.** Lỗi này thuộc giai đoạn khởi tạo bằng khóa. Chữ ký giả mạo thường bị `verify` từ chối trên payload/public key đã được cấu hình đúng.
- **Không dùng public key người gửi tự khai báo nếu chưa xác thực nguồn.** Xác minh chữ ký thành công bằng public key do attacker cung cấp không ràng buộc chữ ký với danh tính tin cậy.
- **Không nhầm SPKI với raw key bytes.** `X509EncodedKeySpec` cần định dạng được tài liệu API quy định; Base64 chỉ là chuyển dữ liệu bytes sang văn bản.
- **Không dùng `String.getBytes()` mơ hồ khi ký văn bản.** Quy định UTF-8 hoặc chuẩn byte của giao thức. Unicode normalization, JSON serialization, xuống dòng đều có thể ảnh hưởng đến bytes được ký.
- **Không chia sẻ một `Signature` instance tùy tiện giữa các thread.** Instance có trạng thái; mỗi tác vụ ký/xác minh cần quản lý vòng đời riêng.
- **Không log khóa bí mật để điều tra.** Đủ thông tin thường là algorithm, provider, key identifier không nhạy cảm, tên thao tác và loại exception; tránh tiết lộ private key hoặc dữ liệu nhạy cảm.
- **Không coi một `SignatureException` giống hệt `false` trong mọi hệ thống.** Cả hai dẫn đến từ chối xác minh, nhưng nguyên nhân vận hành khác nhau; phân loại để điều tra đúng.
- **Không tự động sửa thuật toán theo tên `key.getAlgorithm()` mà client gửi.** Giao thức phải xác định thuật toán được phép và quản lý tương ứng public key/algorithm từ nguồn tin cậy.

### Lỗi thường gặp và cách sửa ngắn

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `NoSuchAlgorithmException` là do khóa RSA không được Ed25519 chấp nhận | Khóa sai họ dẫn đến `InvalidKeyException` ở `initSign`/`initVerify`, **không phải thiếu thuật toán**. |
| Public key Ed25519 khác cặp phải gây `InvalidKeyException` | Nó vẫn có thể là khóa hợp lệ; `verify` sẽ không khớp chữ ký. |
| Provider không tồn tại và thuật toán không tồn tại là một lỗi | `NoSuchProviderException` và `NoSuchAlgorithmException` khác nhau. |
| Bytes X509EncodedKeySpec lỗi phải gây InvalidKeyException ngay | `KeyFactory.generatePublic` thường ném `InvalidKeySpecException` ở bước xây khóa. |
| `Signature.getInstance` thành công nghĩa là toàn bộ thao tác ký đã hợp lệ | Khóa chỉ được kiểm tra khi `initSign`/`initVerify`, dữ liệu/chữ ký còn được xử lý sau đó. |
| Gọi `verify` khi chưa init không có vấn đề | Có thể ném `SignatureException` do sai trạng thái. |
| Khi thuật toán mới thiếu thì chọn MD5/SHA-1 tùy tiện để thay | Không; cần khắc phục provider hoặc thay đổi giao thức một cách được kiểm soát. |
| Base64 là lớp bảo mật đủ để truyền chữ ký và public key | Base64 chỉ mã hóa biểu diễn; cần xác thực public key và bảo vệ kênh/payload theo yêu cầu. |

## 9. Checklist thực hành và tài liệu chuẩn

Trước khi chốt một luồng ký/xác minh:

1. Xác định chính xác **algorithm/service** phải được hỗ trợ.
2. Kiểm tra runtime/provider, không tự hạ cấp thuật toán.
3. Nạp khóa theo **đúng định dạng và loại** (public/private).
4. Dùng `initSign` hoặc `initVerify` đúng mục đích; xử lý `InvalidKeyException` tách biệt lỗi tìm thuật toán.
5. Chuẩn hóa **bytes được ký** theo giao thức, không thay đổi payload khi xác minh.
6. Xác minh bằng public key **đã tin cậy**, không chỉ cùng tên thuật toán.
7. Từ chối chữ ký sai và malformed; ghi lại loại lỗi phù hợp để điều tra.
8. Kiểm thử ca **khóa RSA trong Ed25519, khóa Ed25519 khác cặp, thuật toán giả, provider giả, SPKI sai, thao tác sai trạng thái**, ngoài ca thành công.

**Tài liệu còn hiệu lực:**

- [Java SE 26 — `Signature` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html) — `getInstance`, `initSign`, `initVerify`, `update`, `sign` và `verify`.
- [Java SE 26 — `InvalidKeyException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/InvalidKeyException.html) — khóa không phù hợp với thao tác mật mã.
- [Java SE 26 — `NoSuchAlgorithmException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/NoSuchAlgorithmException.html) — thuật toán/service không khả dụng.
- [Java SE 26 — `NoSuchProviderException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/NoSuchProviderException.html) — provider được yêu cầu không có.
- [Java SE 26 — `KeyFactory` và `X509EncodedKeySpec`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyFactory.html) — tái tạo đối tượng khóa và phân biệt `InvalidKeySpecException`.
- [Java SE 26 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html) — tên chuẩn `Ed25519` của các service tương ứng.
- [JEP 339 — EdDSA](https://openjdk.org/jeps/339) — hỗ trợ Ed25519 chính thức từ Java 15.

**Kết luận:** `NoSuchAlgorithmException` giúp nhận biết **thiếu triển khai thuật toán**, `InvalidKeyException` cho biết **khóa không thể dùng cho thao tác đã chọn**. `NoSuchProviderException`, `InvalidKeySpecException`, `SignatureException` và `verify(false)` phản ánh những tầng lỗi khác, cần được xử lý riêng để giữ tính chính xác và an toàn cho hệ thống.