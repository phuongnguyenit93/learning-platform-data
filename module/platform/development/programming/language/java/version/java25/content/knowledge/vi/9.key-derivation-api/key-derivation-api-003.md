# Lựa chọn và khởi tạo thuật toán KDF qua hệ thống provider

## 1. Mục tiêu và bối cảnh

Một ứng dụng bảo mật có thể cần nhiều khóa từ cùng một bí mật đầu vào: khóa mã hóa dữ liệu, khóa xác thực thông điệp hoặc khóa cho một phiên giao tiếp. Nếu tự cắt chuỗi byte, nối các giá trị tùy ý rồi băm để tạo khóa, ứng dụng dễ mắc lỗi về entropy, phân tách mục đích và quản lý khóa. **Key Derivation Function (KDF)** giải quyết bài toán dẫn xuất vật liệu khóa theo thuật toán và tham số được xác định rõ.

Java cung cấp **JCA/JCE Provider Architecture** để ứng dụng yêu cầu thuật toán bằng tên chuẩn; provider cung cấp implementation. **KDF API** trong package **javax.crypto** được giới thiệu ở Java 24 dưới dạng preview và được hoàn thiện trong **Java 25 qua JEP 510**. Đây là API chính thức trong Java 25, không cần cờ **--enable-preview**.

Bài **Lựa chọn và khởi tạo thuật toán KDF qua hệ thống provider**, thuộc chương **API dẫn xuất khóa** của lộ trình **JAVA_VERSION_JAVA25**, hướng dẫn:

1. Chọn thuật toán KDF theo tên chuẩn và hiểu vai trò của provider.
2. Khởi tạo KDF bằng **getInstance(...)**, dùng provider mặc định hoặc chỉ định provider cụ thể.
3. Phân biệt lựa chọn provider ngay lúc khởi tạo với **delayed provider selection**.
4. Khám phá các dịch vụ KDF mà runtime thực sự hỗ trợ.
5. Cấu hình **HKDFParameterSpec** cho input keying material, salt và context information.
6. Phân biệt **deriveKey(...)** với **deriveData(...)**, kiểm tra lỗi và xác nhận provider sau khi dẫn xuất.

**Phạm vi thuật toán trong ví dụ:** HKDF theo RFC 5869, với các tên chuẩn **HKDF-SHA256**, **HKDF-SHA384** và **HKDF-SHA512**. JDK Reference Implementation cung cấp các thuật toán này qua **SunJCE**. Provider khác hoặc bản JDK khác có thể có tập thuật toán khác; ứng dụng phải kiểm tra môi trường đích thay vì giả định mọi provider giống nhau.

Tài liệu chính: [JEP 510](https://openjdk.org/jeps/510), [KDF Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html), [JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html).

## 2. KDF làm gì và không làm gì?

KDF nhận **input keying material (IKM)** cùng tham số tùy thuật toán để tạo ra một hoặc nhiều kết quả dẫn xuất. Đầu vào có thể là shared secret từ key agreement/KEM hoặc vật liệu khóa khác có entropy đủ mạnh. Kết quả có thể được trả về dưới dạng **SecretKey** hoặc mảng byte.

~~~mermaid
flowchart LR
    A["Input keying material (IKM)"] --> K["KDF algorithm"]
    B["Salt / optional inputs"] --> K
    C["Context / info / output length"] --> K
    P["JCA Provider implementation"] --> K
    K --> E["Derived encryption key"]
    K --> M["Derived MAC key"]
    K --> D["Other keying material"]
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| **IKM** | Vật liệu khóa đầu vào; với HKDF nên có entropy phù hợp, chẳng hạn shared secret từ một giao thức mật mã. |
| **Salt** | Tham số của bước Extract; thường không cần giữ bí mật. Có thể là giá trị ngẫu nhiên hoặc giá trị do giao thức quy định. |
| **Info** | Context/application-specific information, dùng để phân tách mục đích dẫn xuất. |
| **KDF algorithm** | Thuật toán như HKDF-SHA256, quy định cách tạo vật liệu khóa. |
| **Output algorithm** | Tên thuật toán của SecretKey được tạo, ví dụ AES hoặc HmacSHA256. |
| **Output length** | Số byte cần dẫn xuất, được giới hạn theo thuật toán. |

KDF **không phải**:

- **KeyGenerator**: KeyGenerator tạo khóa mới theo một thuật toán; KDF dẫn xuất khóa từ IKM và tham số.
- **KeyAgreement**: KeyAgreement thiết lập shared secret giữa các bên; KDF có thể tiếp tục dẫn xuất khóa từ shared secret đó.
- **KEM**: Key Encapsulation Mechanism đóng gói/khôi phục secret; KDF là một bước khác trong quy trình mật mã.
- **Password hashing**: HKDF không phải password-based KDF có chủ đích làm chậm hoặc tiêu tốn bộ nhớ để chống dò mật khẩu. Không dùng HKDF thay Argon2id, scrypt hoặc PBKDF2 khi xử lý mật khẩu người dùng.

Trong Java 25, KDF thuộc module **java.base**, package **javax.crypto**. Ứng dụng Java thông thường không cần dependency ngoài JDK chỉ để gọi API KDF tích hợp.

## 3. Provider trong JCA: tên thuật toán và implementation

**Provider** là thành phần đăng ký các dịch vụ mật mã với JCA. Một provider có thể cung cấp Cipher, Mac, Signature, KeyStore, KDF và nhiều engine khác. Ứng dụng gọi API cấp cao thay vì phụ thuộc trực tiếp vào lớp implementation nội bộ.

Ví dụ:

~~~java
KDF kdf = KDF.getInstance("HKDF-SHA256");
~~~

Lời gọi yêu cầu một provider có dịch vụ loại **KDF** và thuật toán **HKDF-SHA256**. Trong JDK Reference Implementation Java 25, **SunJCE** cung cấp HKDF-SHA256, HKDF-SHA384 và HKDF-SHA512. Một JDK vendor khác có thể có danh sách provider hoặc chính sách cấu hình khác.

Một số provider có thể kết nối tới phần cứng hoặc kho khóa, chẳng hạn HSM, smart card hoặc PKCS#11. Khi key material không thể trích xuất khỏi thiết bị, khả năng chọn đúng provider hỗ trợ loại khóa đó rất quan trọng. Đây là một lý do KDF API có cơ chế lựa chọn provider trì hoãn.

### Các lựa chọn khi gọi getInstance

| Cách gọi | Hành vi |
| --- | --- |
| **KDF.getInstance("HKDF-SHA256")** | Để JCA chọn provider theo chính sách ưu tiên và khả năng hỗ trợ. |
| **KDF.getInstance("HKDF-SHA256", "SunJCE")** | Chỉ định provider bằng tên; provider phải được đăng ký trong Security. |
| **KDF.getInstance("HKDF-SHA256", provider)** | Chỉ định đối tượng Provider; đối tượng provider không bắt buộc đã đăng ký trong danh sách toàn cục. |
| **KDF.getInstance(algorithm, kdfParameters)** | Khởi tạo KDF với KDFParameters nếu implementation hỗ trợ. |
| **KDF.getInstance(algorithm, kdfParameters, provider)** | Kết hợp tham số khởi tạo KDF với provider cụ thể. |

**Khuyến nghị:** ứng dụng phổ thông nên bắt đầu bằng **getInstance(algorithm)** để tận dụng provider được cấu hình cho runtime. Chỉ pin provider khi có yêu cầu rõ ràng về compliance, chứng nhận, HSM hoặc tính tương thích đã được kiểm thử. Việc pin SunJCE trong mọi ứng dụng có thể làm giảm tính di động và bỏ qua provider tối ưu/hardware-backed.

## 4. Liệt kê provider đang cung cấp thuật toán KDF

Không nên đoán tên provider hoặc thuật toán dựa trên một máy phát triển. Hãy kiểm tra dịch vụ thực tế trên runtime:

~~~java
import java.security.Provider;
import java.security.Security;

public final class ListKdfProviders {

    public static void main(String[] args) {
        String algorithm = "HKDF-SHA256";

        for (Provider provider : Security.getProviders()) {
            Provider.Service service =
                    provider.getService("KDF", algorithm);

            if (service != null) {
                System.out.printf(
                        "provider=%s, algorithm=%s, class=%s%n",
                        provider.getName(),
                        service.getAlgorithm(),
                        service.getClassName());
            }
        }
    }
}
~~~

Trên JDK Reference Implementation Java 25, kết quả thường có dịch vụ HKDF-SHA256 của SunJCE. Output cụ thể phụ thuộc JDK distribution và cấu hình security provider.

**Ý nghĩa các API:**

- **Security.getProviders()** trả các provider đã đăng ký.
- **Provider.getService("KDF", algorithm)** tìm dịch vụ theo loại engine và tên thuật toán.
- **Provider.Service** mô tả implementation đã đăng ký, gồm loại, thuật toán và lớp triển khai.

Danh sách trên hữu ích để chẩn đoán, nhưng **không nên tự chọn provider đầu tiên từ vòng lặp rồi mặc định đó là provider JCA sẽ chọn**. JDK Reference Implementation có thể sử dụng thuộc tính **jdk.security.provider.preferred** để xác định thứ tự ưu tiên theo thuật toán; thứ tự này có thể khác danh sách Security.getProviders(). Hãy để KDF.getInstance(...) thực hiện lựa chọn hoặc chỉ định provider rõ ràng theo chính sách đã kiểm thử.

## 5. Khởi tạo KDF bằng provider mặc định

Ví dụ tối thiểu:

~~~java
import javax.crypto.KDF;

public final class KdfLookup {
    public static void main(String[] args) throws Exception {
        KDF kdf = KDF.getInstance("HKDF-SHA256");
        System.out.println("algorithm=" + kdf.getAlgorithm());
    }
}
~~~

**getInstance(...)** trả về đối tượng KDF nếu có ít nhất một provider phù hợp với thuật toán và các tham số khởi tạo tùy chọn. Việc lấy được đối tượng chưa đồng nghĩa provider cuối cùng đã được cố định.

KDF API có hai giai đoạn:

1. **Instantiation/initialization:** yêu cầu một KDF theo thuật toán, có thể kèm KDFParameters và provider.
2. **Derivation:** gọi deriveKey(...) hoặc deriveData(...) với AlgorithmParameterSpec mô tả vật liệu đầu vào và kết quả cần tạo.

Với HKDF, thông thường ta khởi tạo bằng **KDF.getInstance("HKDF-SHA256")**, sau đó truyền **HKDFParameterSpec** vào deriveKey hoặc deriveData. Không cần tạo KDFParameters chỉ để truyền IKM, salt và info; các dữ liệu này thuộc HKDFParameterSpec.

## 6. Chỉ định provider bằng tên hoặc đối tượng Provider

### 6.1. Chỉ định bằng tên provider

~~~java
import javax.crypto.KDF;

public final class NamedProviderExample {
    public static void main(String[] args) throws Exception {
        KDF kdf = KDF.getInstance("HKDF-SHA256", "SunJCE");
        System.out.println(kdf.getAlgorithm());
    }
}
~~~

Overload nhận **String provider** yêu cầu provider có tên đó đã được đăng ký trong danh sách Security. Nếu tên không tồn tại, có thể nhận NoSuchProviderException; nếu provider tồn tại nhưng không hỗ trợ thuật toán, nhận NoSuchAlgorithmException.

### 6.2. Chỉ định bằng đối tượng Provider

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.KDF;

public final class ProviderObjectExample {
    public static void main(String[] args) throws Exception {
        Provider provider = Security.getProvider("SunJCE");
        if (provider == null) {
            throw new IllegalStateException("SunJCE chưa được đăng ký");
        }

        KDF kdf = KDF.getInstance("HKDF-SHA256", provider);
        System.out.println(kdf.getAlgorithm());
    }
}
~~~

Overload nhận đối tượng **Provider** không yêu cầu provider phải có mặt trong danh sách đăng ký toàn cục. Điều này hữu ích khi ứng dụng nạp provider theo cấu hình riêng hoặc muốn kiểm soát implementation cụ thể.

**Đánh đổi:** pin provider làm ứng dụng phụ thuộc vào tên và dịch vụ của provider đó. Khi triển khai trên JDK khác, container khác hoặc môi trường HSM, cần kiểm thử lại provider, thuật toán, tham số và loại key material thực tế.

## 7. Delayed provider selection: lựa chọn sau khi có key material

Một đặc điểm quan trọng của **KDF.getInstance(algorithm)** là **delayed provider selection**. Khi ứng dụng không chỉ định provider, JCA có thể trì hoãn việc chọn implementation cho tới khi gọi **deriveKey(...)** hoặc **deriveData(...)**.

Lý do: provider cần biết **key material thực tế** để xác định khả năng hỗ trợ. Ví dụ IKM có thể là một SecretKey không thể trích xuất khỏi HSM; provider phần mềm thông thường có thể không xử lý được, trong khi provider PKCS#11 được cấu hình đúng có thể hỗ trợ.

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng
    participant K as KDF.getInstance
    participant J as JCA Provider Selection
    participant P1 as Provider A
    participant P2 as Provider B
    A->>K: getInstance("HKDF-SHA256")
    K-->>A: KDF object (provider có thể chưa chốt)
    A->>K: deriveKey("AES", derivationSpec)
    K->>J: Tìm provider theo thuật toán, params và key material
    J->>P1: Kiểm tra khả năng hỗ trợ
    P1-->>J: Không hỗ trợ key material này
    J->>P2: Kiểm tra provider kế tiếp
    P2-->>J: Hỗ trợ
    J-->>K: Chọn Provider B
    K-->>A: SecretKey dẫn xuất
~~~

**Hệ quả khi chẩn đoán:** đừng gọi **getProviderName()** hoặc **getParameters()** ngay sau getInstance nếu mục tiêu là để provider được chọn dựa trên key material thật. Các phương thức này có thể làm provider được chọn sớm chỉ dựa trên thuật toán và KDFParameters; provider đó sau đó có thể không hỗ trợ key material được đưa vào deriveKey.

Trình tự khuyến nghị:

1. Gọi KDF.getInstance(algorithm) nếu muốn lựa chọn linh hoạt.
2. Chuẩn bị đúng HKDFParameterSpec/AlgorithmParameterSpec và key material.
3. Gọi deriveKey hoặc deriveData.
4. Sau khi derivation thành công, đọc getProviderName() nếu cần ghi nhận provider đã thực sự được chọn.

Một khi provider đã được chọn cho đối tượng KDF, provider đó không thay đổi. Nếu lần dẫn xuất khác cần provider hoặc loại key material khác, hãy tạo đối tượng KDF mới thay vì kỳ vọng cùng instance tự chuyển provider.

## 8. Phân biệt KDFParameters và HKDFParameterSpec

Hai loại tham số này phục vụ hai lớp khác nhau:

| Loại | Dùng ở đâu | Mục đích |
| --- | --- | --- |
| **KDFParameters** | Một số overload KDF.getInstance(...) và KDF.getParameters() | Tham số khởi tạo riêng của implementation KDF/provider. |
| **AlgorithmParameterSpec** | deriveKey(alg, derivationSpec) và deriveData(derivationSpec) | Mô tả đầu vào và cách thực hiện lần dẫn xuất. |
| **HKDFParameterSpec** | Là một AlgorithmParameterSpec | Cấu hình HKDF Extract, Expand hoặc Extract-then-Expand theo RFC 5869. |

Với HKDF, HKDFParameterSpec được truyền vào bước derive. Nó **không** phải đối số KDFParameters của getInstance. Việc trộn hai loại này thường dẫn đến lỗi chọn overload hoặc hiểu sai thời điểm tham số được áp dụng.

KDFParameters là interface gom nhóm các tham số khởi tạo KDF có kiểu. Một provider có thể không cần tham số khởi tạo riêng và chỉ chấp nhận null; provider khác có thể yêu cầu hoặc bổ sung tham số. Hãy đọc tài liệu provider cụ thể nếu dùng overload có KDFParameters.

## 9. Cấu hình HKDF Extract-then-Expand

HKDF được định nghĩa trong [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869). Quy trình gồm:

1. **Extract:** dùng HMAC để chuyển IKM thành pseudorandom key (PRK), có thể kết hợp salt.
2. **Expand:** dùng PRK cùng info và độ dài đầu ra để sinh keying material theo mục đích ứng dụng.

Java 25 cung cấp **HKDFParameterSpec** trong javax.crypto.spec:

| API | Ý nghĩa |
| --- | --- |
| **HKDFParameterSpec.ofExtract()** | Tạo builder cho Extract hoặc Extract-then-Expand. |
| **addIKM(byte[]) / addIKM(SecretKey)** | Thêm input keying material. Có thể gọi nhiều lần để ghép nhiều thành phần IKM. |
| **addSalt(byte[]) / addSalt(SecretKey)** | Thêm salt; cũng có thể gọi nhiều lần. |
| **extractOnly()** | Tạo tham số chỉ thực hiện Extract. |
| **thenExpand(info, length)** | Tạo tham số thực hiện cả Extract và Expand. |
| **expandOnly(prk, info, length)** | Dùng PRK đã có để chỉ thực hiện Expand. |

Ví dụ tạo tham số:

~~~java
import java.nio.charset.StandardCharsets;
import javax.crypto.spec.HKDFParameterSpec;

byte[] ikm = obtainInputKeyMaterial();
byte[] salt = obtainSalt();
byte[] info = "orders-service/v1/aes-encryption"
        .getBytes(StandardCharsets.UTF_8);

HKDFParameterSpec derivationSpec =
        HKDFParameterSpec.ofExtract()
                .addIKM(ikm)
                .addSalt(salt)
                .thenExpand(info, 32);
~~~

**info** nên mô tả ngữ cảnh và mục đích dẫn xuất, chẳng hạn tên giao thức, phiên bản, hướng truyền hoặc loại khóa. Khi tạo nhiều khóa từ cùng một IKM, dùng info khác nhau để phân tách mục đích thay vì dùng cùng một đầu ra cho cả mã hóa và xác thực.

**salt** thường không phải bí mật. Có thể lưu hoặc truyền nó cùng dữ liệu cần giải mã nếu giao thức yêu cầu hai phía tái tạo cùng key. Không tự nghĩ ra định dạng salt hoặc info nếu đang triển khai một giao thức đã có đặc tả; phải tuân theo đúng quy tắc của giao thức.

## 10. Ví dụ hoàn chỉnh: chọn provider và dẫn xuất AES key

Ví dụ sau dùng JDK 25, HKDF-SHA256 và provider mặc định. IKM và salt được sinh ngẫu nhiên cho mỗi lần chạy; không in khóa hoặc vật liệu bí mật ra console.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import javax.crypto.KDF;
import javax.crypto.SecretKey;
import javax.crypto.spec.HKDFParameterSpec;

public final class HkdfProviderDemo {

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();

        // Ví dụ học tập: trong hệ thống thật, IKM phải đến từ
        // một nguồn key agreement/KEM hoặc kho khóa đáng tin cậy.
        byte[] ikm = new byte[32];
        byte[] salt = new byte[32];
        random.nextBytes(ikm);
        random.nextBytes(salt);

        byte[] info = "shop/v1/order-encryption"
                .getBytes(StandardCharsets.UTF_8);

        HKDFParameterSpec spec =
                HKDFParameterSpec.ofExtract()
                        .addIKM(ikm)
                        .addSalt(salt)
                        .thenExpand(info, 32);

        // Chưa pin provider: JCA lựa chọn provider phù hợp.
        KDF kdf = KDF.getInstance("HKDF-SHA256");

        // Dẫn xuất SecretKey AES 256-bit.
        SecretKey aesKey = kdf.deriveKey("AES", spec);

        // Chỉ kiểm tra metadata, không in key.getEncoded().
        System.out.println("KDF algorithm = " + kdf.getAlgorithm());
        System.out.println("KDF provider = " + kdf.getProviderName());
        System.out.println("Key algorithm = " + aesKey.getAlgorithm());
        System.out.println("Key format = " + aesKey.getFormat());
    }
}
~~~

**Điểm cần quan sát:**

- getInstance("HKDF-SHA256") yêu cầu dịch vụ theo tên chuẩn.
- HKDFParameterSpec định nghĩa IKM, salt, info và độ dài đầu ra 32 byte.
- deriveKey("AES", spec) trả về SecretKey có thuật toán AES.
- getProviderName() được gọi **sau khi derive thành công**, khi provider đã được chọn.
- Chương trình không in IKM, salt hay khóa dẫn xuất. Trong ứng dụng thật, việc quản lý và xóa bản sao byte array cần theo mô hình threat và khả năng của provider; không giả định mọi SecretKey đều có thể trích xuất hoặc xóa vật lý.

Ví dụ này minh họa API, không thay thế thiết kế giao thức mã hóa. Khi dùng AES-GCM, cần quản lý nonce/IV duy nhất theo yêu cầu của GCM, xác thực dữ liệu bổ sung nếu có, và lưu metadata cần thiết để bên nhận tái tạo đúng khóa.

## 11. deriveKey hay deriveData?

KDF cung cấp hai cách lấy kết quả:

~~~java
SecretKey key = kdf.deriveKey("AES", derivationSpec);
byte[] raw = kdf.deriveData(derivationSpec);
~~~

| Phương thức | Kết quả | Nên dùng khi |
| --- | --- | --- |
| **deriveKey(String alg, AlgorithmParameterSpec spec)** | SecretKey với tên thuật toán đầu ra đã chỉ định. | Kết quả sẽ được dùng trực tiếp bởi Cipher, Mac hoặc API nhận SecretKey. |
| **deriveData(AlgorithmParameterSpec spec)** | Mảng byte thô. | Ứng dụng thực sự cần keying material dạng byte, chẳng hạn một định dạng/protocol yêu cầu. |

deriveData có thể ném **UnsupportedOperationException** nếu keying material đầu ra không thể trích xuất. Điều này đặc biệt quan trọng khi provider làm việc với key nằm trong HSM hoặc phần cứng bảo mật. Nếu mục tiêu là tạo khóa để dùng tiếp, ưu tiên deriveKey và truyền SecretKey trực tiếp sang API tiêu thụ khóa; tránh gọi getEncoded() chỉ để lấy byte array rồi dựng lại một khóa khác.

Nếu buộc phải xử lý byte array, hãy giới hạn vòng đời, không log, không ghi vào file tạm và xóa mảng khi không còn cần thiết theo khả năng của ứng dụng. Java không bảo đảm việc ghi đè byte array sẽ xóa mọi bản sao nội bộ do JVM/provider tạo ra.

## 12. Khởi tạo và kiểm tra provider cụ thể

Khi hệ thống có yêu cầu bắt buộc dùng một provider đã được phê duyệt, hãy chọn rõ provider và kiểm tra nó tồn tại:

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.KDF;

public final class ApprovedProviderKdf {

    static KDF createKdf() throws Exception {
        Provider approved = Security.getProvider("SunJCE");
        if (approved == null) {
            throw new IllegalStateException(
                    "Provider được cấu hình không có trong runtime");
        }

        return KDF.getInstance("HKDF-SHA256", approved);
    }
}
~~~

Đây là ví dụ kiểm tra tên provider có đăng ký trong runtime. Trong môi trường doanh nghiệp, thay SunJCE bằng provider được tổ chức phê duyệt và xác nhận provider đó có đúng KDF algorithm, tham số, loại key material và cơ chế bảo vệ cần thiết.

### Sau khi derive, ghi nhận provider đã dùng

~~~java
KDF kdf = KDF.getInstance("HKDF-SHA256");
SecretKey key = kdf.deriveKey("AES", spec);

String selectedProvider = kdf.getProviderName();
System.out.println("Selected provider: " + selectedProvider);
~~~

Không dùng getProviderName() trước derivation chỉ để "xem thử" provider. Tài liệu API cảnh báo việc gọi sớm có thể kích hoạt lựa chọn dựa trên thuật toán/tham số khởi tạo mà chưa xét key material thật. Nếu ứng dụng cần audit provider, ghi nhận **sau lần derive thành công** cùng tên thuật toán và phiên bản JDK/provider, nhưng không ghi dữ liệu khóa.

## 13. KDF provider SPI: khi cần tích hợp implementation riêng

Một thư viện mật mã hoặc nhà cung cấp phần cứng có thể cung cấp KDF qua **JCA Provider SPI**. KDFSpi là lớp mở rộng dành cho provider muốn đăng ký một implementation KDF. Một implementation cần xử lý các điểm chính:

- Nhận KDFParameters trong constructor SPI nếu thuật toán có tham số khởi tạo.
- Cung cấp engineDeriveKey(...) để trả về SecretKey.
- Cung cấp engineDeriveData(...) nếu implementation cho phép xuất keying material dạng byte.
- Cung cấp engineGetParameters() để mô tả tham số khởi tạo thực tế.
- Đăng ký dịch vụ loại KDF và tên thuật toán qua Provider.

~~~mermaid
flowchart TD
    A["Ứng dụng gọi KDF.getInstance"] --> B["JCA Provider framework"]
    B --> C["Provider đăng ký service type KDF"]
    C --> D["KDFSpi implementation"]
    D --> E["engineDeriveKey"]
    D --> F["engineDeriveData"]
    D --> G["engineGetParameters"]
    E --> H["SecretKey"]
    F --> I["byte[] nếu được phép extract"]
~~~

KDFSpi không phải nơi để tự phát minh thuật toán mật mã cho sản phẩm. Nếu cần provider riêng, nên tích hợp implementation đã được đánh giá độc lập, kiểm tra vector chuẩn, xử lý lỗi, side-channel, quản lý khóa và tương thích HSM. Một thuật toán có thể chạy đúng test chức năng nhưng vẫn không an toàn khi triển khai mật mã.

Tài liệu API: [KDFSpi Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDFSpi.html), [KDFParameters Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDFParameters.html), [JDK Providers](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html).

## 14. Lỗi thường gặp khi chọn provider và khởi tạo KDF

| Triệu chứng/exception | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **NoSuchAlgorithmException** từ getInstance | Không provider nào hỗ trợ tên KDF yêu cầu hoặc provider được pin không có thuật toán. | Kiểm tra tên chuẩn, Security.getProviders() và service KDF. |
| **NoSuchProviderException** | Dùng overload tên provider nhưng provider chưa đăng ký hoặc tên sai. | Xác minh Security.getProvider(name) và cấu hình provider. |
| **InvalidAlgorithmParameterException** | Provider không hỗ trợ KDFParameters hoặc derivation spec có giá trị không hợp lệ. | Kiểm tra đúng loại tham số và giới hạn thuật toán. |
| **NoSuchAlgorithmException** tại deriveKey | Tên thuật toán của khóa đầu ra không được hỗ trợ hoặc không hợp lệ. | Kiểm tra tên AES, HmacSHA256 và provider hỗ trợ. |
| **UnsupportedOperationException** từ deriveData | Provider không cho trích xuất keying material. | Dùng deriveKey nếu API đích nhận SecretKey; không ép extract. |
| getProviderName() sớm trả provider không xử lý được key | Provider đã được chọn trước khi có key material thực. | Không gọi getProviderName()/getParameters() trước derive trong luồng delayed selection. |
| Thuật toán có trên máy dev nhưng thiếu trên production | JDK/vendor/provider configuration khác nhau. | Kiểm tra provider và KDF service trên runtime đích trong CI/deploy. |
| Kết quả dẫn xuất khác giữa hai phía | Khác thuật toán, salt, IKM, info, độ dài hoặc cách mã hóa byte. | Chuẩn hóa encoding và tham số theo protocol; kiểm thử bằng vector chuẩn. |
| Test chạy song song không ổn định | Chia sẻ một đối tượng KDF giữa nhiều thread. | Dùng instance riêng hoặc đồng bộ hóa. |

### KDF object không mặc định thread-safe

Theo API Java SE 25, các phương thức của một đối tượng KDF **không thread-safe**, trừ khi implementation tài liệu hóa khác. Nhiều thread cần dùng đồng thời một instance phải tự đồng bộ. Cách đơn giản và dễ kiểm soát thường là tạo một đối tượng KDF riêng cho mỗi luồng/tác vụ dẫn xuất; không dùng singleton KDF toàn cục rồi gọi đồng thời.

Điều này không đồng nghĩa provider phải được tạo mới mỗi lần. Provider là implementation đã đăng ký trong runtime; còn đối tượng engine KDF là instance có thể mang trạng thái lựa chọn provider/tham số và phải được quản lý theo contract thread-safety.

## 15. Lưu ý mật mã: chọn đúng KDF cho đúng loại đầu vào

### 15.1. HKDF dành cho key material có entropy

HKDF phù hợp để trích xuất và mở rộng vật liệu khóa như shared secret từ key agreement hoặc secret được sinh bởi một giao thức. Nó giúp:

- Chuẩn hóa IKM thành PRK qua Extract.
- Dẫn xuất các khóa độc lập theo info.
- Tạo độ dài đầu ra theo nhu cầu trong giới hạn RFC.
- Hỗ trợ nhiều thành phần IKM/salt, kể cả SecretKey trong provider có thể xử lý key không trích xuất.

HKDF **không tăng entropy của một mật khẩu yếu**. Nếu IKM là mật khẩu do người dùng tự chọn, HKDF không làm việc dò mật khẩu trở nên đắt đỏ theo cách của password hashing KDF.

### 15.2. Không thay password KDF bằng HKDF

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Dẫn xuất khóa từ shared secret có entropy cao | HKDF qua KDF API. |
| Dẫn xuất nhiều khóa cho các mục đích khác nhau từ master secret | HKDF với info khác nhau cho từng mục đích. |
| Xử lý mật khẩu người dùng để lưu xác thực | Password hashing KDF như Argon2id, scrypt hoặc PBKDF2 theo chính sách và thư viện được phê duyệt. |
| Tạo khóa ngẫu nhiên độc lập | KeyGenerator hoặc nguồn tạo khóa phù hợp. |
| Trao đổi/đóng gói secret | KeyAgreement hoặc KEM, rồi áp dụng KDF theo giao thức nếu cần. |

JDK Java 25 liệt kê các tên chuẩn KDF **HKDF-SHA256**, **HKDF-SHA384** và **HKDF-SHA512** trong [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html). PBKDF2WithHmacSHA256 thuộc nhóm **SecretKeyFactory** trong JCA, không phải một tên thuật toán của KDF engine này.

### 15.3. Domain separation và giới hạn độ dài

Không nên tái sử dụng một key dẫn xuất cho nhiều mục đích. Dùng info phân biệt, ví dụ:

~~~text
shop/v1/aes-gcm/encryption-key
shop/v1/hmac/request-authentication
shop/v1/aes-gcm/backup-key
~~~

Độ dài HKDF-Expand bị giới hạn ở **255 lần độ dài đầu ra của HMAC hash** theo RFC 5869. Với HKDF-SHA256, giới hạn tối đa là 255 × 32 = 8160 byte; giới hạn này không phải khuyến nghị tạo một khóa AES dài như vậy. Hãy chọn độ dài đúng theo thuật toán tiêu thụ, ví dụ 16 hoặc 32 byte cho AES.

Không đưa info có chứa dữ liệu bí mật hoặc thông tin nhận diện cá nhân nếu không cần thiết. Info có thể là dữ liệu context được biết bởi cả hai phía; mục tiêu là phân tách ngữ nghĩa, không phải che giấu dữ liệu.

## 16. Kiểm thử bằng RFC 5869 test vector

Để kiểm tra implementation/provider, dùng test vector công khai thay vì chỉ xác nhận chương trình không ném exception. Ví dụ **RFC 5869, Test Case 1** cho HKDF-SHA256:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import java.util.HexFormat;
import javax.crypto.KDF;
import javax.crypto.spec.HKDFParameterSpec;
import org.junit.jupiter.api.Test;

class HkdfRfc5869Test {

    @Test
    void matchesRfc5869TestCase1() throws Exception {
        HexFormat hex = HexFormat.of();

        byte[] ikm = hex.parseHex("0b".repeat(22));
        byte[] salt = hex.parseHex("000102030405060708090a0b0c");
        byte[] info = hex.parseHex("f0f1f2f3f4f5f6f7f8f9");

        byte[] expected = hex.parseHex(
                "3cb25f25faacd57a90434f64d0362f2a" +
                "2d2d0a90cf1a5a4c5db02d56ecc4c5bf" +
                "34007208d5b887185865");

        HKDFParameterSpec spec =
                HKDFParameterSpec.ofExtract()
                        .addIKM(ikm)
                        .addSalt(salt)
                        .thenExpand(info, 42);

        KDF kdf = KDF.getInstance("HKDF-SHA256");
        byte[] actual = kdf.deriveData(spec);

        assertArrayEquals(expected, actual);
        System.out.println("Provider used: " + kdf.getProviderName());
    }
}
~~~

Test cần JUnit 5 và JDK 25. Nó kiểm tra cả thuật toán, input, salt, info và output length theo vector chuẩn. Không thay vector bằng các giá trị ngẫu nhiên rồi chỉ kiểm tra độ dài; kết quả đúng độ dài không chứng minh thuật toán đúng.

### Kiểm thử provider cụ thể

Nếu hệ thống yêu cầu SunJCE, có thể chạy thêm một test tạo KDF bằng provider đó và so kết quả với cùng vector. Nếu dùng provider HSM, test cần được chạy trên môi trường tích hợp có thiết bị/provider thật; mock provider không chứng minh phần cứng hoặc chính sách key non-extractable hoạt động.

## 17. Quy trình lựa chọn provider cho ứng dụng

1. **Xác định đầu vào:** IKM là shared secret, secret key trong HSM, hay dữ liệu mật khẩu? Không chọn KDF trước khi biết loại vật liệu.
2. **Chọn thuật toán chuẩn:** ví dụ HKDF-SHA256 nếu giao thức và yêu cầu bảo mật quy định; không tự chọn thuật toán chỉ vì provider có sẵn.
3. **Kiểm tra runtime:** liệt kê provider/service KDF, xác nhận thuật toán và parameter support trên JDK đích.
4. **Quyết định provider:** để JCA tự chọn khi có thể; pin provider khi compliance/hardware/interop yêu cầu.
5. **Khởi tạo KDF:** gọi getInstance(...); tránh gọi sớm getProviderName() khi muốn delayed selection.
6. **Tạo derivation spec:** cấu hình IKM, salt, info và output length bằng HKDFParameterSpec.
7. **Dẫn xuất:** ưu tiên deriveKey(...) khi cần SecretKey; chỉ dùng deriveData(...) khi thật sự cần byte thô.
8. **Ghi nhận provider:** sau lần derive thành công, ghi tên thuật toán/provider và version môi trường mà không log key material.
9. **Kiểm thử:** chạy RFC vector, test lỗi tham số, test provider thiếu và test trên môi trường triển khai.
10. **Đánh giá bảo mật:** xác nhận key separation, salt/info protocol, key lifecycle, quyền truy cập provider và khả năng không extract key.

## 18. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập

**Bài A — Liệt kê provider:** viết chương trình tìm provider cung cấp KDF.HKDF-SHA256, KDF.HKDF-SHA384 và KDF.HKDF-SHA512. Ghi lại sự khác nhau giữa các JDK vendor nếu có.

**Bài B — So sánh cách chọn provider:** tạo KDF bằng getInstance(algorithm), bằng tên provider và bằng đối tượng Provider. Xử lý NoSuchAlgorithmException và NoSuchProviderException; chỉ ghi provider đã chọn sau khi derive thành công.

**Bài C — Dẫn xuất khóa:** dùng HKDF-SHA256 để tạo SecretKey AES 256-bit từ IKM, salt và info. Không in key; ghi thuật toán và provider.

**Bài D — Phân tách mục đích:** từ cùng IKM, dẫn xuất hai khóa với info khác nhau (encryption và authentication). Xác nhận output khác nhau; giải thích vì sao không tái sử dụng cùng key cho cả hai mục đích.

**Bài E — Kiểm thử chuẩn:** chạy RFC 5869 Test Case 1 bằng deriveData. Nếu provider không hỗ trợ, ghi rõ provider/algorithm/exception và kiểm tra provider khác đã được phê duyệt.

**Bài F — Mô phỏng key không extractable:** tìm hiểu provider/HSM hỗ trợ SecretKey không thể lấy getEncoded(). So sánh deriveKey và deriveData, xác định API nào phù hợp cho khóa cần giữ trong thiết bị.

### Câu hỏi tự kiểm tra

1. Provider trong JCA/JCE có vai trò gì đối với KDF?
2. getInstance(algorithm) khác getInstance(algorithm, provider) ở điểm nào?
3. Vì sao KDF API có delayed provider selection?
4. Tại sao không nên gọi getProviderName() trước lần derive đầu tiên trong trường hợp dùng key material từ HSM?
5. KDFParameters khác HKDFParameterSpec như thế nào?
6. deriveKey và deriveData khác nhau ở kiểu kết quả và khả năng extract ra sao?
7. Vì sao HKDF không phải lựa chọn thích hợp để hash mật khẩu người dùng?
8. info giúp phân tách khóa theo mục đích như thế nào?
9. Tại sao không nên chia sẻ một instance KDF cho nhiều thread đồng thời?
10. Khi provider có trên máy phát triển nhưng thiếu trên production, cần kiểm tra những gì?

## 19. Tài liệu chính thức

- [JEP 510 — Key Derivation Function API](https://openjdk.org/jeps/510) — trạng thái API trong Java 25.
- [KDF — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDF.html) — factory, derive methods và delayed provider selection.
- [KDFParameters — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDFParameters.html) — tham số khởi tạo KDF.
- [KDFSpi — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/KDFSpi.html) — SPI cho provider triển khai KDF.
- [HKDFParameterSpec — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/HKDFParameterSpec.html) — tham số Extract/Expand.
- [Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html) — tên thuật toán KDF chuẩn.
- [Oracle JDK Providers](https://docs.oracle.com/en/java/javase/25/security/oracle-providers.html) — dịch vụ mật mã của provider tích hợp, gồm SunJCE.
- [JCA Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html) — kiến trúc lựa chọn provider và API mật mã.
- [RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function](https://www.rfc-editor.org/rfc/rfc5869) — đặc tả HKDF và test vectors.

**Ghi chú tính hiện hành:** KDF API là preview trong JDK 24 (JEP 478), nhưng được hoàn thiện trong Java 25 (JEP 510). Các ví dụ của bài dùng API chính thức Java 25 và không cần preview flags. Luôn xác minh thuật toán/provider có trên đúng JDK và thiết bị triển khai; tên chuẩn được Java định nghĩa không đồng nghĩa mọi provider đều phải cung cấp cùng implementation.

**Kết quả cần nộp:** chương trình liệt kê provider KDF, ví dụ getInstance với provider mặc định và provider chỉ định, chương trình HKDF tạo SecretKey, test vector RFC 5869, cùng bảng ghi nhận provider thực tế và các lỗi đã xử lý. Qua đó, bạn biết cách khởi tạo KDF qua hệ thống provider của Java 25 và kiểm chứng implementation trước khi đưa vào một quy trình bảo vệ khóa thực tế.
